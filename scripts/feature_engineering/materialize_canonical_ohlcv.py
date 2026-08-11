#!/usr/bin/env python3
"""Materialize derived canonical OHLCV timeframes from local canonical 1m bars."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
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
    CANONICAL_BAR_COLUMNS,
    CANONICAL_DERIVED_TIMEFRAMES,
    aggregate_canonical_ohlcv,
    canonicalize_ohlcv,
    normalize_canonical_timeframe,
)

DEFAULT_SOURCE_START_DATE = "2021-01-01"


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


def _parse_cli_datetime(value: str | None) -> datetime | None:
    """Parse optional CLI datetimes into UTC-aware datetimes."""
    if value is None:
        return None
    raw = str(value).strip()
    if raw == "" or raw.lower() in {"none", "all"}:
        return None
    if raw.lower() in {"now", "today"}:
        return datetime.now(timezone.utc)
    normalized = raw.replace("Z", "+00:00")
    if len(normalized) == 10 and normalized[4] == "-" and normalized[7] == "-":
        dt = datetime.strptime(normalized, "%Y-%m-%d")
    else:
        dt = datetime.fromisoformat(normalized)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _naive_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


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
            raise ValueError(
                "1m is the source timeframe and is not derived by this command"
            )
        if tf not in normalized:
            normalized.append(tf)
    return tuple(normalized)


def _raw_scan_for_timeframe(
    *,
    project_root: Path,
    asset_id: str,
    timeframe: str,
) -> tuple[pl.LazyFrame | None, list[Path], list[dict[str, Any]]]:
    """Return raw provider scan and metadata for one asset/timeframe."""
    spec = get_htf_asset_spec(asset_id)
    scans: list[pl.LazyFrame] = []
    raw_files: list[Path] = []
    group_meta: list[dict[str, Any]] = []
    for group in spec.groups_for_timeframe(timeframe):
        files = group.files(project_root, timeframe, spec.slug)
        group_meta.append(
            {
                "provider": group.provider,
                "priority": int(group.priority),
                "directory": str(group.directory(project_root, timeframe)),
                "files": int(len(files)),
            }
        )
        if not files:
            continue
        raw_files.extend(files)
        scans.append(
            pl.scan_parquet([str(path) for path in files]).with_columns(
                [
                    pl.lit(group.provider).alias("_source_provider"),
                    pl.lit(group.priority).cast(pl.Int32).alias("_source_priority"),
                ]
            )
        )
    if not scans:
        return None, [], group_meta
    return pl.concat(scans, how="diagonal_relaxed"), sorted(set(raw_files)), group_meta


def _filter_raw_scan(
    lf: pl.LazyFrame,
    *,
    start_date: datetime | None,
    end_date: datetime | None,
) -> pl.LazyFrame:
    lf = lf.with_columns(
        pl.col("timestamp").dt.replace_time_zone(None).alias("ts_norm")
    )
    start_cmp = _naive_utc(start_date)
    end_cmp = _naive_utc(end_date)
    if start_cmp is not None:
        lf = lf.filter(pl.col("ts_norm") >= start_cmp)
    if end_cmp is not None:
        lf = lf.filter(pl.col("ts_norm") < end_cmp)
    return lf


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


def refresh_1m_from_raw(
    *,
    project_root: Path,
    asset_id: str,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    dry_run: bool = False,
) -> MaterializeResult:
    """Canonicalize one asset's raw 1m provider files into canonical 1m OHLCV."""
    spec = get_htf_asset_spec(asset_id)
    output_path = canonical_ohlcv_path(project_root, asset_id, "1m")
    meta_path = canonical_meta_path(output_path)
    raw_scan_base, raw_files, raw_group_meta = _raw_scan_for_timeframe(
        project_root=project_root,
        asset_id=asset_id,
        timeframe="1m",
    )
    if raw_scan_base is None or not raw_files:
        return MaterializeResult(
            asset_id=asset_id,
            timeframe="1m",
            source_path=project_root,
            output_path=output_path,
            meta_path=meta_path,
            status="missing_raw",
            detail=f"Raw 1m files not found; searched={raw_group_meta}",
        )

    raw = _filter_raw_scan(
        raw_scan_base,
        start_date=start_date,
        end_date=end_date,
    ).collect()
    if raw.is_empty():
        return MaterializeResult(
            asset_id=asset_id,
            timeframe="1m",
            source_path=project_root,
            output_path=output_path,
            meta_path=meta_path,
            status="empty_raw",
            detail=(
                "No raw 1m rows available after filters "
                f"start={start_date} end={end_date}"
            ),
        )

    required_raw_cols = {"timestamp", "open", "high", "low", "close"}
    missing_raw_cols = sorted(required_raw_cols - set(raw.columns))
    if missing_raw_cols:
        raise ValueError(
            f"Raw files for asset={asset_id} 1m are missing columns: {missing_raw_cols}"
        )
    if "volume" not in raw.columns:
        raw = raw.with_columns(pl.lit(None).cast(pl.Float64).alias("volume"))

    rows_before_dedup = len(raw)
    raw = raw.sort(["ts_norm", "_source_priority"]).unique(
        subset=["ts_norm"],
        keep="last",
        maintain_order=True,
    )
    duplicate_rows_removed = rows_before_dedup - len(raw)

    if dry_run:
        rows, min_ts, max_ts = _scan_output(output_path)
        return MaterializeResult(
            asset_id=asset_id,
            timeframe="1m",
            source_path=project_root,
            output_path=output_path,
            meta_path=meta_path,
            status="would_write" if output_path.exists() else "would_create",
            rows=rows,
            min_ts=min_ts,
            max_ts=max_ts,
            detail=(
                f"raw_files={len(raw_files)} raw_rows_after_dedup={len(raw)} "
                f"duplicates_removed={duplicate_rows_removed}"
            ),
        )

    canonical, summary = canonicalize_ohlcv(
        raw.with_columns(pl.col("ts_norm").alias("timestamp")),
        asset_id=spec.asset_id,
        calendar_id=spec.calendar_id,
        timeframe="1m",
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    canonical.select(CANONICAL_BAR_COLUMNS).write_parquet(output_path)
    payload = {
        **summary.as_dict(),
        "source_timeframe": "raw_1m",
        "source_paths": raw_files,
        "source_groups": raw_group_meta,
        "output_path": output_path,
        "meta_path": meta_path,
        "rows": int(len(canonical)),
        "raw_rows_after_dedup": int(len(raw)),
        "duplicate_rows_removed": int(duplicate_rows_removed),
        "source_start_date": start_date,
        "source_end_date": end_date,
        "timestamp_semantics": (
            "bar_open; model features from this bar are available only after "
            "timestamp + timeframe"
        ),
    }
    meta_path.write_text(json.dumps(payload, indent=2, default=_json_default) + "\n")
    return MaterializeResult(
        asset_id=asset_id,
        timeframe="1m",
        source_path=project_root,
        output_path=output_path,
        meta_path=meta_path,
        status="written",
        rows=int(len(canonical)),
        min_ts=payload["min_ts"],
        max_ts=payload["max_ts"],
    )


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
        detail = (
            "" if rows > 0 else f"Derived canonical file has no rows: {output_path}"
        )
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
    return (
        CORE_HTF_ASSET_IDS
        if raw.strip().lower() == "core"
        else htf_asset_ids_from_csv(raw)
    )


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
        description=(
            "Refresh canonical 1m OHLCV from raw sources and/or derive "
            "multi-timeframe OHLCV bars from local canonical 1m data."
        ),
    )
    parser.add_argument(
        "--assets", default="core", help="core or comma-separated asset ids"
    )
    parser.add_argument(
        "--timeframes",
        default=",".join(CANONICAL_DERIVED_TIMEFRAMES),
        help="Comma-separated derived timeframes. 24h is accepted as an alias for 1d.",
    )
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument(
        "--refresh-1m-from-raw",
        action="store_true",
        help="Refresh canonical 1m OHLCV from configured raw provider files before deriving.",
    )
    parser.add_argument(
        "--start-date",
        default=DEFAULT_SOURCE_START_DATE,
        help="Raw 1m source start filter for --refresh-1m-from-raw. Empty/none disables.",
    )
    parser.add_argument(
        "--end-date",
        default="",
        help="Optional exclusive raw 1m source end filter for --refresh-1m-from-raw.",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Report planned writes only"
    )
    parser.add_argument(
        "--status", action="store_true", help="Validate existing outputs"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run canonical OHLCV materialization or status validation."""
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    assets = _asset_ids(args.assets)
    timeframes = normalize_timeframes(args.timeframes)
    project_root = args.project_root.resolve()
    start_date = _parse_cli_datetime(args.start_date)
    end_date = _parse_cli_datetime(args.end_date)

    results: list[MaterializeResult] = []
    if args.refresh_1m_from_raw and not args.status:
        for asset_id in assets:
            results.append(
                refresh_1m_from_raw(
                    project_root=project_root,
                    asset_id=asset_id,
                    start_date=start_date,
                    end_date=end_date,
                    dry_run=args.dry_run,
                )
            )
        source_failures = {"missing_raw", "empty_raw"}
        if any(result.status in source_failures for result in results):
            print_results(results)
            return 1

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
        "missing_raw",
        "empty_raw",
        "missing_output",
        "empty_output",
    }
    return 1 if any(result.status in failing for result in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
