#!/usr/bin/env python3
"""Diagnose canonical TA flag activation, conflicts, and overlap.

The diagnostics are intentionally read-only for generated TA inputs. Reports are
written under ``test_output/ta_signal_diagnostics`` so default/raw and compact
signals can be inspected before parameter optimization.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from TA_backtest_optimization.materialize_ta_flags import (  # noqa: E402
    TA_SIGNAL_SET_ALL,
    TA_SIGNAL_SET_RAW,
    parse_ta_signal_sets,
    parse_ta_timeframes,
    project_root_from_cwd,
    ta_flag_columns,
    ta_flags_path,
)
from scripts.feature_engineering.htf_asset_registry import (  # noqa: E402
    CORE_HTF_ASSET_IDS,
    htf_asset_ids_from_csv,
)


@dataclass(frozen=True)
class TADiagnosticConfig:
    """TA diagnostics configuration."""

    project_root: Path
    assets: tuple[str, ...]
    timeframes: tuple[str, ...]
    signal_sets: tuple[str, ...]
    output_dir: Path
    always_on_threshold: float = 0.95
    high_overlap_threshold: float = 0.80


def _asset_ids(raw: str) -> tuple[str, ...]:
    return CORE_HTF_ASSET_IDS if raw.strip().lower() == "core" else htf_asset_ids_from_csv(raw)


def _flag_family(column: str) -> str:
    for suffix in ("_long", "_short"):
        if column.endswith(suffix):
            return column[: -len(suffix)]
    return column


def _flag_side(column: str) -> str | None:
    if column.endswith("_long"):
        return "long"
    if column.endswith("_short"):
        return "short"
    return None


def _write_frame(df: pl.DataFrame, output_dir: Path, stem: str) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    df.write_csv(output_dir / f"{stem}.csv")
    df.write_parquet(output_dir / f"{stem}.parquet")


def _diagnose_one(
    *,
    project_root: Path,
    asset_id: str,
    timeframe: str,
    signal_set: str,
    always_on_threshold: float,
    high_overlap_threshold: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    path = ta_flags_path(project_root, asset_id, timeframe, signal_set=signal_set)
    if not path.exists():
        return [], [], [], {
            "asset_id": asset_id,
            "timeframe": timeframe,
            "signal_set": signal_set,
            "status": "missing_output",
            "path": str(path),
        }

    schema = pl.scan_parquet(path).collect_schema().names()
    flag_cols = ta_flag_columns(schema, timeframe)
    if not flag_cols:
        return [], [], [], {
            "asset_id": asset_id,
            "timeframe": timeframe,
            "signal_set": signal_set,
            "status": "no_flag_columns",
            "path": str(path),
        }

    df = pl.read_parquet(path, columns=["timestamp", *flag_cols]).sort("timestamp")
    row_count = len(df)
    if row_count == 0:
        return [], [], [], {
            "asset_id": asset_id,
            "timeframe": timeframe,
            "signal_set": signal_set,
            "status": "empty_output",
            "path": str(path),
        }

    sums = df.select([pl.col(col).fill_null(0).sum().alias(col) for col in flag_cols]).row(0, named=True)
    activation_rows: list[dict[str, Any]] = []
    for col in flag_cols:
        active_rows = int(sums[col])
        rate = active_rows / row_count
        activation_rows.append(
            {
                "asset_id": asset_id,
                "timeframe": timeframe,
                "signal_set": signal_set,
                "flag": col,
                "rows": row_count,
                "active_rows": active_rows,
                "activation_rate": rate,
                "is_dead": active_rows == 0,
                "is_always_on": rate >= always_on_threshold,
            }
        )

    conflict_rows: list[dict[str, Any]] = []
    by_family: dict[str, dict[str, str]] = {}
    for col in flag_cols:
        side = _flag_side(col)
        if side is None:
            continue
        by_family.setdefault(_flag_family(col), {})[side] = col
    for family, sides in by_family.items():
        if "long" not in sides or "short" not in sides:
            continue
        both = int(
            df.select(
                (
                    (pl.col(sides["long"]).fill_null(0) > 0)
                    & (pl.col(sides["short"]).fill_null(0) > 0)
                ).sum().alias("both")
            )["both"][0]
        )
        if both:
            conflict_rows.append(
                {
                    "asset_id": asset_id,
                    "timeframe": timeframe,
                    "signal_set": signal_set,
                    "family": family,
                    "long_flag": sides["long"],
                    "short_flag": sides["short"],
                    "conflict_rows": both,
                    "conflict_rate": both / row_count,
                }
            )

    matrix = df.select(flag_cols).fill_null(0).to_numpy().astype(bool)
    active_counts = matrix.sum(axis=0)
    overlap_rows: list[dict[str, Any]] = []
    for i, left in enumerate(flag_cols):
        if active_counts[i] == 0:
            continue
        for j in range(i + 1, len(flag_cols)):
            if active_counts[j] == 0:
                continue
            both = int(np.logical_and(matrix[:, i], matrix[:, j]).sum())
            if not both:
                continue
            union = int(np.logical_or(matrix[:, i], matrix[:, j]).sum())
            jaccard = both / union if union else 0.0
            if jaccard >= high_overlap_threshold:
                overlap_rows.append(
                    {
                        "asset_id": asset_id,
                        "timeframe": timeframe,
                        "signal_set": signal_set,
                        "flag_a": left,
                        "flag_b": flag_cols[j],
                        "both_active_rows": both,
                        "jaccard": jaccard,
                    }
                )

    summary = {
        "asset_id": asset_id,
        "timeframe": timeframe,
        "signal_set": signal_set,
        "status": "ok",
        "path": str(path),
        "rows": row_count,
        "flag_columns": len(flag_cols),
        "dead_flags": sum(1 for row in activation_rows if row["is_dead"]),
        "always_on_flags": sum(1 for row in activation_rows if row["is_always_on"]),
        "conflict_pairs": len(conflict_rows),
        "high_overlap_pairs": len(overlap_rows),
        "timestamp_min": df["timestamp"].min(),
        "timestamp_max": df["timestamp"].max(),
    }
    return activation_rows, conflict_rows, overlap_rows, summary


def run_diagnostics(config: TADiagnosticConfig) -> dict[str, Path]:
    """Run TA diagnostics and write report files."""
    activation: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    overlaps: list[dict[str, Any]] = []
    summary: list[dict[str, Any]] = []

    for asset_id in config.assets:
        for timeframe in config.timeframes:
            for signal_set in config.signal_sets:
                rows, conflict_rows, overlap_rows, summary_row = _diagnose_one(
                    project_root=config.project_root,
                    asset_id=asset_id,
                    timeframe=timeframe,
                    signal_set=signal_set,
                    always_on_threshold=config.always_on_threshold,
                    high_overlap_threshold=config.high_overlap_threshold,
                )
                activation.extend(rows)
                conflicts.extend(conflict_rows)
                overlaps.extend(overlap_rows)
                summary.append(summary_row)

    output_dir = config.output_dir
    _write_frame(pl.DataFrame(summary), output_dir, "summary")
    _write_frame(pl.DataFrame(activation) if activation else pl.DataFrame(), output_dir, "activation")
    _write_frame(pl.DataFrame(conflicts) if conflicts else pl.DataFrame(), output_dir, "conflicts")
    _write_frame(pl.DataFrame(overlaps) if overlaps else pl.DataFrame(), output_dir, "high_overlap")
    manifest_path = output_dir / "manifest.json"
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "assets": list(config.assets),
        "timeframes": list(config.timeframes),
        "signal_sets": list(config.signal_sets),
        "always_on_threshold": config.always_on_threshold,
        "high_overlap_threshold": config.high_overlap_threshold,
        "outputs": {
            "summary": str(output_dir / "summary.csv"),
            "activation": str(output_dir / "activation.csv"),
            "conflicts": str(output_dir / "conflicts.csv"),
            "high_overlap": str(output_dir / "high_overlap.csv"),
        },
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, default=str) + "\n")
    return {
        "summary": output_dir / "summary.csv",
        "activation": output_dir / "activation.csv",
        "conflicts": output_dir / "conflicts.csv",
        "high_overlap": output_dir / "high_overlap.csv",
        "manifest": manifest_path,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Diagnose canonical TA signal flags.")
    parser.add_argument("--assets", default="core", help="core or comma-separated asset ids")
    parser.add_argument(
        "--timeframes",
        default="15m,1h,4h,8h,12h,1d",
        help="Comma-separated canonical TA timeframes.",
    )
    parser.add_argument(
        "--signal-set",
        default=TA_SIGNAL_SET_RAW,
        choices=(TA_SIGNAL_SET_RAW, "compact", TA_SIGNAL_SET_ALL),
        help="Signal set to diagnose: raw, compact, or all.",
    )
    parser.add_argument("--project-root", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--always-on-threshold", type=float, default=0.95)
    parser.add_argument("--high-overlap-threshold", type=float, default=0.80)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    project_root = Path(args.project_root).resolve() if args.project_root else project_root_from_cwd()
    run_id = datetime.now().strftime("ta_signal_diagnostics_%Y%m%d_%H%M%S")
    output_dir = (
        Path(args.output_dir).resolve()
        if args.output_dir
        else project_root / "test_output" / "ta_signal_diagnostics" / run_id
    )
    outputs = run_diagnostics(
        TADiagnosticConfig(
            project_root=project_root,
            assets=_asset_ids(args.assets),
            timeframes=parse_ta_timeframes(args.timeframes),
            signal_sets=parse_ta_signal_sets(args.signal_set),
            output_dir=output_dir,
            always_on_threshold=float(args.always_on_threshold),
            high_overlap_threshold=float(args.high_overlap_threshold),
        )
    )
    for name, path in outputs.items():
        print(f"{name}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
