#!/usr/bin/env python3
"""Materialize derived canonical OHLCV timeframes from local canonical 1m bars."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import polars as pl

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.feature_engineering.htf_asset_registry import (  # noqa: E402
    CORE_HTF_ASSET_IDS,
    get_htf_asset_spec,
    htf_asset_ids_from_csv,
)
from scripts.feature_engineering.htf_trading_calendar import (  # noqa: E402
    CANONICAL_DERIVED_TIMEFRAMES,
    aggregate_canonical_ohlcv,
    normalize_canonical_timeframe,
)


@dataclass(frozen=True)
class MaterializeResult:
    """One asset/timeframe materialization or validation result."""

    asset_id: str
    timeframe: str
    source_path: Path
    output_path: Path
    meta_path: Path
    status: str
    rows: int = 0
    min_ts: datetime | None = None
    max_ts: datetime | None = None
    detail: str = ""


def _json_default(value: Any) -> str:
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def canonical_ohlcv_path(project_root: Path, asset_id: str, timeframe: str) -> Path:
    """Return the canonical OHLCV parquet path for one asset/timeframe."""
    spec = get_htf_asset_spec(asset_id)
    tf = normalize_canonical_timeframe(timeframe)
    return (
        project_root
        / "data"
        / "htf_multiasset"
        / spec.slug
        / "htf_canonical_ohlcv"
        / tf
        / f"{spec.slug}_{tf}_canonical.parquet"
    )


def canonical_meta_path(output_path: Path) -> Path:
    """Return the sidecar metadata path for a canonical OHLCV parquet file."""
    return output_path.with_name(f"{output_path.stem}_meta.json")


def normalize_timeframes(raw: str | tuple[str, ...] | list[str]) -> tuple[str, ...]:
    """Parse, normalize, and deduplicate requested derived timeframes."""
    parts: list[str]
    if isinstance(raw, str):
        parts = [part.strip() for part in raw.split(",") if part.strip()]
    else:
        parts = [str(part).strip() for part in raw if str(part).strip()]
    if not parts:
        parts = list(CANONICAL_DERIVED_TIMEFRAMES)
    normalized: list[str] = []
    for part in parts:
        tf = normalize_canonical_timeframe(part)
        if tf == "1m":
            raise ValueError("1m is the source timeframe and is not derived by this command")
        if tf not in normalized:
            normalized.append(tf)
    return tuple(normalized)


def _scan_output(path: Path) -> tuple[int, datetime | None, datetime | None]:
    if not path.exists():
        return 0, None, None
    row = (
        pl.scan_parquet(str(path))
        .select(
            [
                pl.len().alias("rows"),
                pl.col("timestamp").min().alias("min_ts"),
                pl.col("timestamp").max().alias("max_ts"),
            ]
        )
        .collect()
        .to_dicts()[0]
    )
    return int(row["rows"]), row["min_ts"], row["max_ts"]


def materialize_one(
    *,
    project_root: Path,
    asset_id: str,
    timeframe: str,
    dry_run: bool = False,
) -> MaterializeResult:
    """Derive one canonical timeframe from that asset's canonical 1m parquet."""
    tf = normalize_canonical_timeframe(timeframe)
    source_path = canonical_ohlcv_path(project_root, asset_id, "1m")
    output_path = canonical_ohlcv_path(project_root, asset_id, tf)
    meta_path = canonical_meta_path(output_path)
    if not source_path.exists():
        return MaterializeResult(
            asset_id=asset_id,
            timeframe=tf,
            source_path=source_path,
            output_path=output_path,
            meta_path=meta_path,
            status="missing_source_1m",
            detail=f"Missing source canonical 1m file: {source_path}",
        )

    if dry_run:
        rows, min_ts, max_ts = _scan_output(output_path)
        return MaterializeResult(
            asset_id=asset_id,
            timeframe=tf,
            source_path=source_path,
            output_path=output_path,
            meta_path=meta_path,
            status="would_write" if output_path.exists() else "would_create",
            rows=rows,
            min_ts=min_ts,
            max_ts=max_ts,
        )

    df_1m = pl.read_parquet(source_path)
    derived, metadata = aggregate_canonical_ohlcv(df_1m, target_timeframe=tf)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    derived.write_parquet(output_path)
    payload = {
        **metadata,
        "asset_id": get_htf_asset_spec(asset_id).asset_id,
        "source_timeframe": "1m",
        "source_path": source_path,
        "output_path": output_path,
        "meta_path": meta_path,
        "source_rows": int(len(df_1m)),
        "rows": int(len(derived)),
        "min_ts": derived["timestamp"].min() if len(derived) else None,
        "max_ts": derived["timestamp"].max() if len(derived) else None,
        "timestamp_semantics": (
            "bar_open; model features from this bar are available only after "
            "timestamp + timeframe"
        ),
    }
    meta_path.write_text(json.dumps(payload, indent=2, default=_json_default) + "\n")
    return MaterializeResult(
        asset_id=asset_id,
        timeframe=tf,
        source_path=source_path,
        output_path=output_path,
        meta_path=meta_path,
        status="written",
        rows=int(len(derived)),
        min_ts=payload["min_ts"],
        max_ts=payload["max_ts"],
    )


def status_one(project_root: Path, asset_id: str, timeframe: str) -> MaterializeResult:
    """Validate that one derived canonical file exists and report its range."""
    tf = normalize_canonical_timeframe(timeframe)
    source_path = canonical_ohlcv_path(project_root, asset_id, "1m")
    output_path = canonical_ohlcv_path(project_root, asset_id, tf)
    meta_path = canonical_meta_path(output_path)
    if not source_path.exists():
        status = "missing_source_1m"
        detail = f"Missing source canonical 1m file: {source_path}"
        rows, min_ts, max_ts = 0, None, None
    elif not output_path.exists():
        status = "missing_output"
        detail = f"Missing derived canonical file: {output_path}"
        rows, min_ts, max_ts = 0, None, None
    else:
        rows, min_ts, max_ts = _scan_output(output_path)
        status = "ok" if rows > 0 else "empty_output"
        detail = "" if rows > 0 else f"Derived canonical file has no rows: {output_path}"
    return MaterializeResult(
        asset_id=asset_id,
        timeframe=tf,
        source_path=source_path,
        output_path=output_path,
        meta_path=meta_path,
        status=status,
        rows=rows,
        min_ts=min_ts,
        max_ts=max_ts,
        detail=detail,
    )


def _asset_ids(raw: str) -> tuple[str, ...]:
    return CORE_HTF_ASSET_IDS if raw.strip().lower() == "core" else htf_asset_ids_from_csv(raw)


def print_results(results: list[MaterializeResult]) -> None:
    """Print a compact human-readable result table."""
    print("| Asset | TF | Status | Rows | Range UTC |")
    print("|---|---:|---|---:|---|")
    for result in results:
        if result.min_ts is None or result.max_ts is None:
            rng = "-"
        else:
            rng = f"{result.min_ts} -> {result.max_ts}"
        print(
            f"| {result.asset_id} | {result.timeframe} | {result.status} | "
            f"{result.rows} | {rng} |"
        )
        if result.detail:
            print(f"  detail: {result.detail}")


def build_arg_parser() -> argparse.ArgumentParser:
    """Create the canonical OHLCV materializer CLI."""
    parser = argparse.ArgumentParser(
        description="Derive canonical multi-timeframe OHLCV bars from local canonical 1m data.",
    )
    parser.add_argument("--assets", default="core", help="core or comma-separated asset ids")
    parser.add_argument(
        "--timeframes",
        default=",".join(CANONICAL_DERIVED_TIMEFRAMES),
        help="Comma-separated derived timeframes. 24h is accepted as an alias for 1d.",
    )
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--dry-run", action="store_true", help="Report planned writes only")
    parser.add_argument("--status", action="store_true", help="Validate existing outputs")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run canonical OHLCV materialization or status validation."""
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    assets = _asset_ids(args.assets)
    timeframes = normalize_timeframes(args.timeframes)
    project_root = args.project_root.resolve()

    results: list[MaterializeResult] = []
    for asset_id in assets:
        for tf in timeframes:
            if args.status:
                results.append(status_one(project_root, asset_id, tf))
            else:
                results.append(
                    materialize_one(
                        project_root=project_root,
                        asset_id=asset_id,
                        timeframe=tf,
                        dry_run=args.dry_run,
                    )
                )
    print_results(results)
    failing = {
        "missing_source_1m",
        "missing_output",
        "empty_output",
    }
    return 1 if any(result.status in failing for result in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
