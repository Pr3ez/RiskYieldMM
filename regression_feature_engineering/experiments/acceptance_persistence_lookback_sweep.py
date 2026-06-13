"""Sweep acceptance/persistence lookback sets without rewriting feature roots."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import polars as pl

_REPO_BOOTSTRAP_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_BOOTSTRAP_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_BOOTSTRAP_ROOT))

from regression_feature_engineering.core.alignment import (  # noqa: E402
    DEFAULT_TIMEFRAMES,
    OHLCV_COLUMNS,
    join_all_closed_bar_context,
    normalize_timeframes,
)
from regression_feature_engineering.core.paths import canonical_ohlcv_path, regression_label_root  # noqa: E402
from regression_feature_engineering.features.acceptance_persistence import (  # noqa: E402
    DEFAULT_ACCEPT_LOOKBACKS,
    add_acceptance_persistence_features,
    enrich_acceptance_persistence_sources,
    feature_columns as acceptance_feature_columns,
    source_columns as acceptance_source_columns,
)
from regression_feature_engineering.validate_features import (  # noqa: E402
    DERIVED_TARGETS,
    TARGET_COLUMNS,
    _feature_bin_spreads,
    _feature_target_correlations,
    _valid_joined_rows,
)
from scripts.feature_engineering.htf_asset_registry import normalize_htf_asset_id  # noqa: E402
from scripts.htf_backtest.catboost.stage1_multiasset_dataset import STAGE1_MULTIASSET_ROOT_LAYOUTS  # noqa: E402
from scripts.project_paths import ensure_project_root_on_path  # noqa: E402


PROJECT_ROOT = ensure_project_root_on_path(Path(__file__))
MEAN_DIRECTION_TARGETS = (
    "target_reg_distance_up_mean_high_hvol_v2",
    "target_reg_distance_down_mean_low_hvol_v2",
    "target_mean_up_minus_down",
)
DIRECTION_TARGETS = (
    "target_extreme_up_minus_down",
    "target_mean_up_minus_down",
    "target_extreme_up_down_ratio",
)
INDIVIDUAL_TARGETS = TARGET_COLUMNS


@dataclass(frozen=True)
class AcceptanceLookbackSweepResult:
    """Summary for one acceptance/persistence lookback set."""

    asset_id: str
    root_key: str
    root_id: str
    lookbacks: tuple[int, ...]
    rows: int
    valid_rows: int
    feature_count: int
    null_feature_count: int
    duplicate_count: int
    max_abs_mean_direction_spearman: float | None
    max_abs_direction_spearman: float | None
    max_abs_individual_spearman: float | None
    best_mean_direction_feature: str | None
    best_mean_direction_target: str | None
    best_direction_feature: str | None
    best_direction_target: str | None


def parse_lookback_sets(raw: str) -> tuple[tuple[int, ...], ...]:
    """Parse semicolon-separated lookback sets such as `4,16,48;8,24,72`."""

    sets: list[tuple[int, ...]] = []
    for chunk in raw.split(";"):
        values = tuple(int(part.strip()) for part in chunk.split(",") if part.strip())
        if not values:
            continue
        if any(value <= 0 for value in values):
            raise ValueError("Lookback values must be positive integers")
        sets.append(tuple(dict.fromkeys(values)))
    if not sets:
        raise ValueError("At least one lookback set is required")
    return tuple(sets)


def run_acceptance_persistence_lookback_sweep(
    *,
    project_root: Path,
    asset_id: str,
    root_key: str,
    timeframes: tuple[str, ...] = DEFAULT_TIMEFRAMES,
    lookback_sets: tuple[tuple[int, ...], ...] = (DEFAULT_ACCEPT_LOOKBACKS,),
    output_dir: Path | None = None,
    batch_limit: int | None = None,
) -> list[AcceptanceLookbackSweepResult]:
    """Run a report-only acceptance/persistence lookback sweep."""

    data_root = project_root / "data"
    asset_id = normalize_htf_asset_id(asset_id)
    layout = STAGE1_MULTIASSET_ROOT_LAYOUTS[root_key]
    timeframes = normalize_timeframes(timeframes)
    output_dir = output_dir or project_root / "test_output/regression_feature_engineering_acceptance_sweeps"
    output_dir.mkdir(parents=True, exist_ok=True)
    root_output = output_dir / f"{asset_id.lower()}_{layout.root_id}"
    root_output.mkdir(parents=True, exist_ok=True)

    rows = _read_label_rows(data_root, asset_id=asset_id, label_root=layout.label_root, root_id=layout.root_id, batch_limit=batch_limit)
    bars_by_timeframe = _read_canonical_bars(data_root, asset_id=asset_id, timeframes=timeframes)
    results: list[AcceptanceLookbackSweepResult] = []
    for lookbacks in lookback_sets:
        result = _run_one_set(
            rows=rows,
            bars_by_timeframe=bars_by_timeframe,
            asset_id=asset_id,
            root_key=root_key,
            root_id=layout.root_id,
            timeframes=timeframes,
            lookbacks=lookbacks,
            output_dir=root_output,
        )
        results.append(result)

    _write_sweep_index(root_output, results)
    return results


def _run_one_set(
    *,
    rows: pl.DataFrame,
    bars_by_timeframe: dict[str, pl.DataFrame],
    asset_id: str,
    root_key: str,
    root_id: str,
    timeframes: tuple[str, ...],
    lookbacks: tuple[int, ...],
    output_dir: Path,
) -> AcceptanceLookbackSweepResult:
    slug = "l" + "_".join(str(value) for value in lookbacks)
    enriched = {
        timeframe: enrich_acceptance_persistence_sources(bars, lookbacks=lookbacks)
        for timeframe, bars in bars_by_timeframe.items()
    }
    source_columns = tuple(dict.fromkeys((*OHLCV_COLUMNS, *acceptance_source_columns(lookbacks=lookbacks))))
    aligned = join_all_closed_bar_context(
        rows,
        enriched,
        timeframes=timeframes,
        include_source_ohlcv=True,
        source_columns=source_columns,
    )
    out = add_acceptance_persistence_features(aligned, timeframes=timeframes, lookbacks=lookbacks)
    feature_cols = acceptance_feature_columns(timeframes=timeframes, lookbacks=lookbacks)
    duplicate_count = out.select(["timestamp", "batch_id"]).height - out.select(["timestamp", "batch_id"]).unique().height
    null_feature_count = int(
        out.select(pl.sum_horizontal([pl.col(col).is_null().cast(pl.Int64) for col in feature_cols]).sum()).item()
    )
    valid_df = _valid_joined_rows(out.lazy(), feature_cols)
    correlations = _feature_target_correlations(valid_df, feature_cols)
    bin_spreads = _feature_bin_spreads(valid_df, feature_cols)

    set_output = output_dir / slug
    set_output.mkdir(parents=True, exist_ok=True)
    correlations.write_csv(set_output / "feature_target_correlations.csv")
    correlations.write_parquet(set_output / "feature_target_correlations.parquet")
    bin_spreads.write_csv(set_output / "feature_bin_spreads.csv")
    bin_spreads.write_parquet(set_output / "feature_bin_spreads.parquet")

    mean_direction_best = _best_row(correlations, MEAN_DIRECTION_TARGETS)
    direction_best = _best_row(correlations, DIRECTION_TARGETS)
    individual_best = _best_row(correlations, INDIVIDUAL_TARGETS)
    result = AcceptanceLookbackSweepResult(
        asset_id=asset_id,
        root_key=root_key,
        root_id=root_id,
        lookbacks=lookbacks,
        rows=out.height,
        valid_rows=valid_df.height,
        feature_count=len(feature_cols),
        null_feature_count=null_feature_count,
        duplicate_count=int(duplicate_count),
        max_abs_mean_direction_spearman=_row_float(mean_direction_best, "abs_spearman"),
        max_abs_direction_spearman=_row_float(direction_best, "abs_spearman"),
        max_abs_individual_spearman=_row_float(individual_best, "abs_spearman"),
        best_mean_direction_feature=_row_str(mean_direction_best, "feature"),
        best_mean_direction_target=_row_str(mean_direction_best, "target"),
        best_direction_feature=_row_str(direction_best, "feature"),
        best_direction_target=_row_str(direction_best, "target"),
    )
    (set_output / "summary.json").write_text(json.dumps(asdict(result), indent=2, default=str) + "\n")
    return result


def _read_label_rows(
    data_root: Path,
    *,
    asset_id: str,
    label_root: str,
    root_id: str,
    batch_limit: int | None,
) -> pl.DataFrame:
    label_dir = regression_label_root(data_root, asset_id, label_root)
    paths = sorted(label_dir.glob("batch_*.parquet"))
    if batch_limit is not None:
        paths = paths[: int(batch_limit)]
    if not paths:
        raise FileNotFoundError(f"No regression target batches found in {label_dir}")
    required = {
        "timestamp",
        "batch_id",
        "close",
        "tb_volatility_pct",
        "target_reg_distance_valid_v2",
        *TARGET_COLUMNS,
    }
    schema = pl.read_parquet(paths[0], n_rows=0).schema
    missing = required - set(schema)
    if missing:
        raise ValueError(f"Regression target rows missing columns: {sorted(missing)}")
    return (
        pl.read_parquet([str(path) for path in paths])
        .select(["timestamp", "batch_id", "close", "tb_volatility_pct", "target_reg_distance_valid_v2", *TARGET_COLUMNS])
        .sort(["batch_id", "timestamp"])
        .with_columns([pl.lit(asset_id).alias("asset_id"), pl.lit(root_id).alias("root_id")])
    )


def _read_canonical_bars(
    data_root: Path,
    *,
    asset_id: str,
    timeframes: tuple[str, ...],
) -> dict[str, pl.DataFrame]:
    bars: dict[str, pl.DataFrame] = {}
    for timeframe in timeframes:
        path = canonical_ohlcv_path(data_root, asset_id, timeframe)
        if not path.exists():
            raise FileNotFoundError(f"Canonical {timeframe} OHLCV not found: {path}")
        bars[timeframe] = pl.read_parquet(path).sort("timestamp")
    return bars


def _best_row(correlations: pl.DataFrame, targets: tuple[str, ...]) -> dict[str, Any] | None:
    rows = (
        correlations.filter(pl.col("target").is_in(targets))
        .sort("abs_spearman", descending=True, nulls_last=True)
        .head(1)
        .to_dicts()
    )
    return rows[0] if rows else None


def _row_float(row: dict[str, Any] | None, key: str) -> float | None:
    if not row or row.get(key) is None:
        return None
    return float(row[key])


def _row_str(row: dict[str, Any] | None, key: str) -> str | None:
    if not row or row.get(key) is None:
        return None
    return str(row[key])


def _write_sweep_index(output_dir: Path, results: list[AcceptanceLookbackSweepResult]) -> None:
    rows = []
    for result in results:
        row = asdict(result)
        row["lookbacks"] = ",".join(str(value) for value in result.lookbacks)
        rows.append(row)
    df = pl.DataFrame(rows)
    df.write_csv(output_dir / "lookback_sweep_summary.csv")
    (output_dir / "lookback_sweep_summary.json").write_text(json.dumps(rows, indent=2, default=str) + "\n")
    (output_dir / "lookback_sweep_summary.md").write_text(_markdown_summary(rows))


def _markdown_summary(rows: list[dict[str, Any]]) -> str:
    columns = [
        "lookbacks",
        "feature_count",
        "max_abs_mean_direction_spearman",
        "best_mean_direction_feature",
        "best_mean_direction_target",
        "max_abs_direction_spearman",
        "best_direction_feature",
        "best_direction_target",
    ]
    return "# Acceptance/Persistence Lookback Sweep\n\n" + _markdown_table(rows, columns) + "\n"


def _markdown_table(rows: list[dict[str, Any]], columns: list[str]) -> str:
    def fmt(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, float):
            return f"{value:.6g}"
        if isinstance(value, (tuple, list)):
            return ",".join(str(item) for item in value)
        return str(value)

    lines = ["| " + " | ".join(columns) + " |", "| " + " | ".join(["---"] * len(columns)) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(fmt(row.get(column)) for column in columns) + " |")
    return "\n".join(lines)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sweep acceptance/persistence lookback sets.")
    parser.add_argument("--asset", default="BTCUSDT")
    parser.add_argument("--root", default="8h/B", choices=sorted(STAGE1_MULTIASSET_ROOT_LAYOUTS))
    parser.add_argument("--timeframes", default=",".join(DEFAULT_TIMEFRAMES))
    parser.add_argument("--lookback-sets", default="2,4,8;4,8,16;4,16,48;8,24,72;16,48,144")
    parser.add_argument(
        "--batch-limit",
        type=int,
        default=200,
        help="Number of earliest batches to use for the report-only sweep. Defaults to 200 to avoid full-root OOM.",
    )
    parser.add_argument(
        "--full-root",
        action="store_true",
        help="Disable the default bounded batch sample and sweep the full root. This can require substantial RAM.",
    )
    parser.add_argument("--output-dir", default="test_output/regression_feature_engineering_acceptance_sweeps")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    results = run_acceptance_persistence_lookback_sweep(
        project_root=PROJECT_ROOT,
        asset_id=args.asset,
        root_key=args.root,
        timeframes=normalize_timeframes(args.timeframes),
        lookback_sets=parse_lookback_sets(args.lookback_sets),
        output_dir=PROJECT_ROOT / args.output_dir,
        batch_limit=None if args.full_root else args.batch_limit,
    )
    for result in results:
        print(
            f"{result.asset_id} {result.root_key} lookbacks={','.join(str(v) for v in result.lookbacks)} "
            f"features={result.feature_count} rows={result.rows:,} valid={result.valid_rows:,} "
            f"mean_direction={result.max_abs_mean_direction_spearman} "
            f"direction={result.max_abs_direction_spearman}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
