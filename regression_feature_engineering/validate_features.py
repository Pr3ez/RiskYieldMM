"""Validate generated regression path features against regression targets.

The validator is report-only. It does not modify feature or label artifacts.
It is meant to be run after `regression_feature_engineering.materialize_features`
so each asset/root receives the same temporal-safety and signal-quality checks.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import polars as pl

_REPO_BOOTSTRAP_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_BOOTSTRAP_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_BOOTSTRAP_ROOT))

from regression_feature_engineering.core.alignment import DEFAULT_TIMEFRAMES, normalize_timeframes  # noqa: E402
from regression_feature_engineering.core.paths import (  # noqa: E402
    FEATURE_SET,
    TARGET_VARIANT,
    regression_feature_root,
    regression_label_root,
)
from scripts.feature_engineering.htf_asset_registry import normalize_htf_asset_id  # noqa: E402
from scripts.htf_backtest.catboost.stage1_multiasset_dataset import (  # noqa: E402
    STAGE1_MULTIASSET_ROOT_LAYOUTS,
    parse_stage1_target_assets,
)
from scripts.project_paths import ensure_project_root_on_path  # noqa: E402


PROJECT_ROOT = ensure_project_root_on_path(Path(__file__))
DISTANCE_TARGET_COLUMNS = (
    "target_reg_distance_up_extreme_hvol_v2",
    "target_reg_distance_up_mean_high_hvol_v2",
    "target_reg_distance_down_mean_low_hvol_v2",
    "target_reg_distance_down_extreme_hvol_v2",
)
DIRECTION_SHARE_TARGET_COLUMNS = (
    "target_reg_direction_extreme_up_share_hvol_v2",
    "target_reg_direction_mean_up_share_hvol_v2",
)
TARGET_COLUMNS = (*DISTANCE_TARGET_COLUMNS, *DIRECTION_SHARE_TARGET_COLUMNS)
DERIVED_TARGETS = (
    "target_extreme_total",
    "target_mean_total",
    "target_extreme_up_minus_down",
    "target_mean_up_minus_down",
    "target_extreme_up_down_ratio",
)


@dataclass(frozen=True)
class FeatureValidationSummary:
    """High-level result for one asset/root validation."""

    asset_id: str
    root_key: str
    root_id: str
    report_path: Path
    joined_rows: int
    valid_rows: int
    feature_count: int
    duplicate_count: int
    null_feature_count: int
    infinite_feature_count: int
    future_close_violations: int
    strongest_abs_spearman: float | None


def validate_regression_feature_roots(
    *,
    project_root: Path,
    assets: tuple[str, ...],
    roots: tuple[str, ...],
    timeframes: tuple[str, ...] = DEFAULT_TIMEFRAMES,
    output_dir: Path | None = None,
    signal_sample_rows: int = 25_000,
    diagnostic_feature_prefix: str | None = None,
    max_diagnostic_columns: int = 80,
    allow_wide_diagnostics: bool = False,
) -> list[FeatureValidationSummary]:
    """Validate generated feature roots for selected assets and roots."""

    data_root = project_root / "data"
    output_dir = output_dir or project_root / "test_output/regression_feature_engineering"
    timeframes = normalize_timeframes(timeframes)
    summaries: list[FeatureValidationSummary] = []
    for asset_id in assets:
        asset_id = normalize_htf_asset_id(asset_id)
        for root_key in roots:
            summaries.append(
                _validate_one_root(
                    data_root=data_root,
                    output_dir=output_dir,
                    asset_id=asset_id,
                    root_key=root_key,
                    timeframes=timeframes,
                    signal_sample_rows=int(signal_sample_rows),
                    diagnostic_feature_prefix=diagnostic_feature_prefix,
                    max_diagnostic_columns=int(max_diagnostic_columns),
                    allow_wide_diagnostics=bool(allow_wide_diagnostics),
                )
            )
    _write_index(output_dir, summaries)
    return summaries


def _validate_one_root(
    *,
    data_root: Path,
    output_dir: Path,
    asset_id: str,
    root_key: str,
    timeframes: tuple[str, ...],
    signal_sample_rows: int,
    diagnostic_feature_prefix: str | None,
    max_diagnostic_columns: int,
    allow_wide_diagnostics: bool,
) -> FeatureValidationSummary:
    layout = STAGE1_MULTIASSET_ROOT_LAYOUTS[root_key]
    feature_dir = regression_feature_root(data_root, asset_id, layout.root_id)
    label_dir = regression_label_root(data_root, asset_id, layout.label_root)
    manifest_path = feature_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Missing regression feature manifest: {manifest_path}")
    if not list(feature_dir.glob("batch_*.parquet")):
        raise FileNotFoundError(f"Missing regression feature batches in {feature_dir}")
    if not list(label_dir.glob("batch_*.parquet")):
        raise FileNotFoundError(f"Missing regression label batches in {label_dir}")

    manifest = json.loads(manifest_path.read_text())
    feature_cols = tuple(manifest["feature_columns"])
    diagnostic_feature_cols = _diagnostic_feature_columns(
        feature_cols,
        diagnostic_feature_prefix,
        max_diagnostic_columns=max_diagnostic_columns,
        allow_wide_diagnostics=allow_wide_diagnostics,
    )
    align_cols = _alignment_columns(timeframes)
    family_slug = _family_slug(manifest.get("families", ()))
    output = output_dir / f"{family_slug}_{asset_id.lower()}_{layout.root_id}"
    output.mkdir(parents=True, exist_ok=True)

    exact = _exact_batch_validation(
        feature_dir=feature_dir,
        label_dir=label_dir,
        diagnostic_feature_cols=diagnostic_feature_cols,
        align_cols=tuple(align_cols),
        timeframes=timeframes,
        manifest_row_count=int(manifest.get("row_count") or 0),
        signal_sample_rows=max(0, int(signal_sample_rows)),
    )
    base = exact["base"]
    base["null_feature_count"] = int(manifest.get("null_feature_count", base["diagnostic_null_feature_count"]))
    align = exact["align"]
    target_df = exact["target_df"]
    valid_df = exact["diagnostic_df"]
    joined_rows = int(exact["joined_rows"])
    valid_rows = int(exact["valid_rows"])
    target_summary = _target_summary(target_df)
    correlations = _feature_target_correlations(valid_df, diagnostic_feature_cols)
    bin_spreads = _feature_bin_spreads(valid_df, diagnostic_feature_cols)
    feature_quality = _feature_quality(valid_df, diagnostic_feature_cols)
    cross_timeframe = _cross_timeframe_summary(valid_df, timeframes) if _has_cross_timeframe_columns(valid_df, timeframes) else _empty_cross_timeframe_summary()

    target_summary.write_csv(output / "target_summary.csv")
    correlations.write_parquet(output / "feature_target_correlations.parquet")
    correlations.write_csv(output / "feature_target_correlations.csv")
    bin_spreads.write_parquet(output / "feature_bin_spreads.parquet")
    bin_spreads.write_csv(output / "feature_bin_spreads.csv")
    feature_quality.write_parquet(output / "feature_quality.parquet")
    feature_quality.write_csv(output / "feature_quality.csv")
    cross_timeframe.write_csv(output / "cross_timeframe_summary.csv")

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "asset": asset_id,
        "root_key": root_key,
        "root_id": layout.root_id,
        "feature_set": FEATURE_SET,
        "target_variant": TARGET_VARIANT,
        "families": manifest.get("families", []),
        "feature_root": str(feature_dir),
        "label_root": str(label_dir),
        "feature_rows_manifest": manifest.get("row_count"),
        "joined_rows": joined_rows,
        "valid_rows": valid_rows,
        "signal_sample_rows": valid_df.height,
        "signal_sample_requested_rows": int(signal_sample_rows),
        "feature_count": len(feature_cols),
        "diagnostic_feature_prefix": diagnostic_feature_prefix or "",
        "diagnostic_feature_count": len(diagnostic_feature_cols),
        "duplicate_timestamp_batch": base["duplicate_timestamp_batch"],
        "null_feature_count": base["null_feature_count"],
        "infinite_feature_count": base["infinite_feature_count"],
        "alignment_violations": align,
        "target_summary": target_summary.to_dicts(),
        "cross_timeframe_summary": cross_timeframe.to_dicts(),
        "top_abs_spearman": correlations.head(20).to_dicts(),
        "top_bin_spreads": bin_spreads.head(20).to_dicts(),
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2, default=str) + "\n")
    report_path = output / "summary.md"
    report_path.write_text(_markdown_report(summary, target_summary, correlations, bin_spreads, cross_timeframe))

    strongest = correlations.get_column("abs_spearman").drop_nulls().max() if "abs_spearman" in correlations.columns else None
    future_violations = sum(value for key, value in align.items() if key.endswith("_future_close_violations"))
    return FeatureValidationSummary(
        asset_id=asset_id,
        root_key=root_key,
        root_id=layout.root_id,
        report_path=report_path,
        joined_rows=joined_rows,
        valid_rows=valid_rows,
        feature_count=len(feature_cols),
        duplicate_count=base["duplicate_timestamp_batch"],
        null_feature_count=base["null_feature_count"],
        infinite_feature_count=base["infinite_feature_count"],
        future_close_violations=int(future_violations),
        strongest_abs_spearman=None if strongest is None else float(strongest),
    )


def _alignment_columns(timeframes: tuple[str, ...]) -> list[str]:
    columns: list[str] = []
    for timeframe in timeframes:
        columns.extend(
            [
                f"rpf_align_{timeframe}_bar_open_ts",
                f"rpf_align_{timeframe}_bar_close_ts",
                f"rpf_align_{timeframe}_has_closed_bar",
            ]
        )
    return columns


def _diagnostic_feature_columns(
    feature_cols: tuple[str, ...],
    prefix: str | None,
    *,
    max_diagnostic_columns: int,
    allow_wide_diagnostics: bool,
) -> tuple[str, ...]:
    """Select model-facing columns used for expensive signal diagnostics."""

    if not prefix:
        selected = feature_cols
    else:
        selected = tuple(col for col in feature_cols if col.startswith(prefix))
        if not selected:
            raise ValueError(f"No feature columns match diagnostic prefix: {prefix}")
    if max_diagnostic_columns > 0 and len(selected) > max_diagnostic_columns and not allow_wide_diagnostics:
        hint = (
            "Use a narrower --diagnostic-feature-prefix such as rpf_accept_15m_ or rpf_mem_vol_15m_, "
            "lower --signal-sample-rows, or pass --allow-wide-diagnostics when "
            "you intentionally want a high-memory run."
        )
        raise ValueError(
            f"Selected {len(selected)} diagnostic feature columns, above "
            f"--max-diagnostic-columns={max_diagnostic_columns}. {hint}"
        )
    return selected


def _alignment_stats(joined: pl.LazyFrame, timeframes: tuple[str, ...]) -> dict[str, int]:
    expressions = []
    for timeframe in timeframes:
        close_col = f"rpf_align_{timeframe}_bar_close_ts"
        has_col = f"rpf_align_{timeframe}_has_closed_bar"
        expressions.extend(
            [
                (
                    pl.col(has_col)
                    & pl.col(close_col).is_not_null()
                    & (pl.col(close_col) > pl.col("timestamp"))
                )
                .sum()
                .alias(f"{timeframe}_future_close_violations"),
                (pl.col(has_col) & pl.col(close_col).is_null()).sum().alias(f"{timeframe}_closed_missing_close_ts"),
                ((~pl.col(has_col)) & pl.col(close_col).is_not_null())
                .sum()
                .alias(f"{timeframe}_not_closed_has_close_ts"),
            ]
        )
    row = joined.select(expressions).collect().to_dicts()[0]
    return {key: int(value) for key, value in row.items()}


def _exact_batch_validation(
    *,
    feature_dir: Path,
    label_dir: Path,
    diagnostic_feature_cols: tuple[str, ...],
    align_cols: tuple[str, ...],
    timeframes: tuple[str, ...],
    manifest_row_count: int,
    signal_sample_rows: int,
) -> dict[str, Any]:
    """Run exact safety/target checks by reading one feature batch at a time."""

    feature_paths = sorted(feature_dir.glob("batch_*.parquet"))
    duplicate_count = 0
    diagnostic_null_feature_count = 0
    diagnostic_infinite_feature_count = 0
    joined_rows = 0
    valid_rows = 0
    valid_seen = 0
    diagnostic_parts: list[pl.DataFrame] = []
    align = _empty_alignment_stats(timeframes)
    label_columns = ["timestamp", "batch_id", "target_reg_distance_valid_v2", *DISTANCE_TARGET_COLUMNS]
    sample_stride = max(1, int(manifest_row_count / signal_sample_rows)) if signal_sample_rows > 0 and manifest_row_count > signal_sample_rows else 1

    for feature_path in feature_paths:
        label_path = label_dir / feature_path.name
        if not label_path.exists():
            raise FileNotFoundError(f"Missing matching label batch for {feature_path.name}: {label_path}")
        features = pl.read_parquet(feature_path, columns=["timestamp", "batch_id", *align_cols, *diagnostic_feature_cols])
        labels = _read_label_batch_with_targets(label_path, label_columns)
        duplicate_count += int(features.select(pl.struct(["timestamp", "batch_id"]).is_duplicated().sum()).item())
        if diagnostic_feature_cols:
            diagnostic_null_feature_count += int(
                features.select(pl.sum_horizontal([pl.col(col).is_null().cast(pl.Int64) for col in diagnostic_feature_cols]).sum()).item()
            )
            diagnostic_infinite_feature_count += int(
                features.select(pl.sum_horizontal([pl.col(col).is_infinite().cast(pl.Int64) for col in diagnostic_feature_cols]).sum()).item()
            )
        _accumulate_alignment_stats(align, features, timeframes)
        joined = features.select(["timestamp", "batch_id"]).join(labels, on=["timestamp", "batch_id"], how="inner")
        joined_rows += joined.height
        valid = _valid_target_frame(joined)
        if valid.height:
            valid_rows += valid.height
            if signal_sample_rows <= 0 or _diagnostic_sample_height(diagnostic_parts) < signal_sample_rows:
                diagnostic_joined = features.select(["timestamp", "batch_id", *diagnostic_feature_cols]).join(
                    labels,
                    on=["timestamp", "batch_id"],
                    how="inner",
                )
                diagnostic_valid = _valid_diagnostic_frame(diagnostic_joined, diagnostic_feature_cols)
                if diagnostic_valid.height:
                    sampled = (
                        diagnostic_valid.with_row_index("_rpf_valid_idx")
                        .filter(((pl.col("_rpf_valid_idx") + int(valid_seen)) % int(sample_stride)) == 0)
                        .drop("_rpf_valid_idx")
                    )
                    remaining = None if signal_sample_rows <= 0 else max(0, int(signal_sample_rows) - _diagnostic_sample_height(diagnostic_parts))
                    if remaining is None or remaining > 0:
                        diagnostic_parts.append(sampled if remaining is None else sampled.head(remaining))
            valid_seen += valid.height

    diagnostic_df = pl.concat(diagnostic_parts, how="vertical") if diagnostic_parts else _empty_diagnostic_frame(diagnostic_feature_cols)
    return {
        "base": {
            "duplicate_timestamp_batch": int(duplicate_count),
            "diagnostic_null_feature_count": int(diagnostic_null_feature_count),
            "infinite_feature_count": int(diagnostic_infinite_feature_count),
        },
        "align": align,
        "joined_rows": int(joined_rows),
        "valid_rows": int(valid_rows),
        "target_df": diagnostic_df.select(["timestamp", "batch_id", *TARGET_COLUMNS, *DERIVED_TARGETS]),
        "diagnostic_df": diagnostic_df,
    }


def _empty_alignment_stats(timeframes: tuple[str, ...]) -> dict[str, int]:
    stats: dict[str, int] = {}
    for timeframe in timeframes:
        stats[f"{timeframe}_future_close_violations"] = 0
        stats[f"{timeframe}_closed_missing_close_ts"] = 0
        stats[f"{timeframe}_not_closed_has_close_ts"] = 0
    return stats


def _accumulate_alignment_stats(stats: dict[str, int], features: pl.DataFrame, timeframes: tuple[str, ...]) -> None:
    for timeframe in timeframes:
        close_col = f"rpf_align_{timeframe}_bar_close_ts"
        has_col = f"rpf_align_{timeframe}_has_closed_bar"
        row = features.select(
            (
                pl.col(has_col)
                & pl.col(close_col).is_not_null()
                & (pl.col(close_col) > pl.col("timestamp"))
            )
            .sum()
            .alias("future"),
            (pl.col(has_col) & pl.col(close_col).is_null()).sum().alias("closed_missing"),
            ((~pl.col(has_col)) & pl.col(close_col).is_not_null()).sum().alias("not_closed_has_close"),
        ).to_dicts()[0]
        stats[f"{timeframe}_future_close_violations"] += int(row["future"])
        stats[f"{timeframe}_closed_missing_close_ts"] += int(row["closed_missing"])
        stats[f"{timeframe}_not_closed_has_close_ts"] += int(row["not_closed_has_close"])


def _valid_target_frame(joined: pl.DataFrame) -> pl.DataFrame:
    """Return exact valid target rows with derived targets for one batch."""

    return (
        joined.lazy()
        .filter(_valid_target_expr())
        .with_columns(_derived_target_exprs())
        .select(["timestamp", "batch_id", *TARGET_COLUMNS, *DERIVED_TARGETS])
        .collect()
    )


def _read_label_batch_with_targets(label_path: Path, base_columns: list[str]) -> pl.DataFrame:
    available = set(pl.read_parquet(label_path, n_rows=0).columns)
    missing_base = [column for column in base_columns if column not in available]
    if missing_base:
        raise ValueError(f"{label_path} is missing required label columns: {missing_base}")
    optional_share_columns = [column for column in DIRECTION_SHARE_TARGET_COLUMNS if column in available]
    labels = pl.read_parquet(label_path, columns=[*base_columns, *optional_share_columns])
    missing_share_columns = [column for column in DIRECTION_SHARE_TARGET_COLUMNS if column not in labels.columns]
    if not missing_share_columns:
        return labels
    exprs: list[pl.Expr] = []
    if "target_reg_direction_extreme_up_share_hvol_v2" in missing_share_columns:
        exprs.append(
            _up_share_expr(
                "target_reg_distance_up_extreme_hvol_v2",
                "target_reg_distance_down_extreme_hvol_v2",
                "target_reg_direction_extreme_up_share_hvol_v2",
            )
        )
    if "target_reg_direction_mean_up_share_hvol_v2" in missing_share_columns:
        exprs.append(
            _up_share_expr(
                "target_reg_distance_up_mean_high_hvol_v2",
                "target_reg_distance_down_mean_low_hvol_v2",
                "target_reg_direction_mean_up_share_hvol_v2",
            )
        )
    return labels.with_columns(exprs)


def _valid_diagnostic_frame(joined: pl.DataFrame, feature_cols: tuple[str, ...]) -> pl.DataFrame:
    return (
        joined.lazy()
        .filter(_valid_target_expr())
        .with_columns(_derived_target_exprs())
        .select(["timestamp", "batch_id", *feature_cols, *TARGET_COLUMNS, *DERIVED_TARGETS])
        .collect()
    )


def _diagnostic_sample_height(parts: list[pl.DataFrame]) -> int:
    return sum(part.height for part in parts)


def _empty_target_frame() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "timestamp": pl.Datetime(time_zone="UTC"),
            "batch_id": pl.Int64,
            **{target: pl.Float64 for target in (*TARGET_COLUMNS, *DERIVED_TARGETS)},
        }
    )


def _empty_diagnostic_frame(feature_cols: tuple[str, ...]) -> pl.DataFrame:
    schema = {
        "timestamp": pl.Datetime(time_zone="UTC"),
        "batch_id": pl.Int64,
        **{feature: pl.Float64 for feature in feature_cols},
        **{target: pl.Float64 for target in (*TARGET_COLUMNS, *DERIVED_TARGETS)},
    }
    return pl.DataFrame(schema=schema)


def _sample_target_rows(target_df: pl.DataFrame, *, sample_rows: int) -> pl.DataFrame:
    """Return a deterministic stride sample of valid target rows."""

    if sample_rows <= 0 or target_df.height <= sample_rows:
        return target_df
    stride = max(1, target_df.height // int(sample_rows))
    return target_df.with_row_index("_rpf_valid_idx").filter((pl.col("_rpf_valid_idx") % stride) == 0).limit(sample_rows).drop(
        "_rpf_valid_idx"
    )


def _valid_joined_rows(joined: pl.LazyFrame, feature_cols: tuple[str, ...]) -> pl.DataFrame:
    """Collect valid joined rows for in-memory experiment helpers."""

    return (
        joined.filter(_valid_target_expr())
        .with_columns(_derived_target_exprs())
        .select(["timestamp", "batch_id", *feature_cols, *TARGET_COLUMNS, *DERIVED_TARGETS])
        .collect()
    )


def _sample_feature_diagnostics(
    *,
    feature_dir: Path,
    target_sample: pl.DataFrame,
    feature_cols: tuple[str, ...],
    feature_chunk_size: int,
) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    """Compute feature diagnostics on a deterministic target-row sample."""

    correlations: list[pl.DataFrame] = []
    bin_spreads: list[pl.DataFrame] = []
    quality: list[pl.DataFrame] = []
    for feature_chunk in _feature_chunks(feature_cols, feature_chunk_size=feature_chunk_size):
        sample = _collect_sample_features(feature_dir=feature_dir, target_sample=target_sample, feature_cols=feature_chunk)
        correlations.append(_feature_target_correlations(sample, feature_chunk))
        bin_spreads.append(_feature_bin_spreads(sample, feature_chunk))
        quality.append(_feature_quality(sample, feature_chunk))
    return (
        pl.concat(correlations, how="vertical").sort("abs_spearman", descending=True, nulls_last=True) if correlations else pl.DataFrame(),
        pl.concat(bin_spreads, how="vertical").sort("high_minus_low", descending=True, nulls_last=True) if bin_spreads else pl.DataFrame(),
        pl.concat(quality, how="vertical") if quality else pl.DataFrame(),
    )


def _sample_cross_timeframe_summary(*, feature_dir: Path, target_sample: pl.DataFrame, timeframes: tuple[str, ...]) -> pl.DataFrame:
    cols: list[str] = []
    for suffix in ("range_to_tb_vol", "abs_ret_to_tb_vol", "range_efficiency_bnd"):
        cols.extend(f"rpf_vol_{timeframe}_{suffix}" for timeframe in timeframes)
    available = [col for col in cols if _feature_exists(feature_dir, col)]
    if not available:
        return pl.DataFrame(
            schema={
                "suffix": pl.Utf8,
                "mean_abs_spearman": pl.Float64,
                "max_abs_spearman": pl.Float64,
                "min_abs_spearman": pl.Float64,
            }
        )
    sample = _collect_sample_features(feature_dir=feature_dir, target_sample=target_sample, feature_cols=tuple(available))
    return _cross_timeframe_summary(sample, timeframes)


def _has_cross_timeframe_columns(df: pl.DataFrame, timeframes: tuple[str, ...]) -> bool:
    for timeframe in timeframes:
        for suffix in ("range_to_tb_vol", "abs_ret_to_tb_vol", "range_efficiency_bnd"):
            if f"rpf_vol_{timeframe}_{suffix}" in df.columns:
                return True
    return False


def _empty_cross_timeframe_summary() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "suffix": pl.Utf8,
            "mean_abs_spearman": pl.Float64,
            "max_abs_spearman": pl.Float64,
            "min_abs_spearman": pl.Float64,
        }
    )


def _feature_chunks(feature_cols: tuple[str, ...], *, feature_chunk_size: int) -> list[tuple[str, ...]]:
    return [tuple(feature_cols[idx : idx + int(feature_chunk_size)]) for idx in range(0, len(feature_cols), int(feature_chunk_size))]


def _collect_sample_features(*, feature_dir: Path, target_sample: pl.DataFrame, feature_cols: tuple[str, ...]) -> pl.DataFrame:
    """Collect sampled target rows plus a small feature-column subset."""

    if not feature_cols or target_sample.is_empty():
        return target_sample
    sample_parts: list[pl.DataFrame] = []
    for key, keys in target_sample.partition_by("batch_id", as_dict=True, maintain_order=True).items():
        batch_id = key[0] if isinstance(key, tuple) else key
        feature_path = feature_dir / f"batch_{int(batch_id):04d}.parquet"
        if not feature_path.exists():
            continue
        features = pl.read_parquet(feature_path, columns=["timestamp", "batch_id", *feature_cols])
        sample_parts.append(keys.join(features, on=["timestamp", "batch_id"], how="inner"))
    return pl.concat(sample_parts, how="vertical") if sample_parts else target_sample.select(["timestamp", "batch_id", *TARGET_COLUMNS, *DERIVED_TARGETS])


def _feature_exists(feature_dir: Path, feature_col: str) -> bool:
    first = next(iter(sorted(feature_dir.glob("batch_*.parquet"))), None)
    if first is None:
        return False
    return feature_col in pl.read_parquet(first, n_rows=0).columns


def _valid_target_expr() -> pl.Expr:
    """Return the common v2 target-validity predicate."""

    valid_expr = pl.col("target_reg_distance_valid_v2")
    for column in TARGET_COLUMNS:
        valid_expr = valid_expr & pl.col(column).is_not_null() & pl.col(column).is_finite()
    return valid_expr


def _up_share_expr(up_col: str, down_col: str, alias: str) -> pl.Expr:
    total = pl.col(up_col) + pl.col(down_col)
    share = pl.col(up_col) / total
    bounded = pl.min_horizontal(pl.max_horizontal(share, pl.lit(0.0)), pl.lit(1.0))
    return pl.when(total > 0.0).then(bounded).otherwise(0.5).alias(alias)


def _derived_target_exprs() -> list[pl.Expr]:
    """Return derived target expressions used for diagnostics."""

    return [
        (pl.col("target_reg_distance_up_extreme_hvol_v2") + pl.col("target_reg_distance_down_extreme_hvol_v2")).alias(
            "target_extreme_total"
        ),
        (pl.col("target_reg_distance_up_mean_high_hvol_v2") + pl.col("target_reg_distance_down_mean_low_hvol_v2")).alias(
            "target_mean_total"
        ),
        (pl.col("target_reg_distance_up_extreme_hvol_v2") - pl.col("target_reg_distance_down_extreme_hvol_v2")).alias(
            "target_extreme_up_minus_down"
        ),
        (pl.col("target_reg_distance_up_mean_high_hvol_v2") - pl.col("target_reg_distance_down_mean_low_hvol_v2")).alias(
            "target_mean_up_minus_down"
        ),
        pl.when(pl.col("target_reg_distance_down_extreme_hvol_v2") > 0)
        .then(pl.col("target_reg_distance_up_extreme_hvol_v2") / pl.col("target_reg_distance_down_extreme_hvol_v2"))
        .otherwise(None)
        .alias("target_extreme_up_down_ratio"),
    ]


def _target_summary(df: pl.DataFrame) -> pl.DataFrame:
    rows: list[dict[str, Any]] = []
    for target in (*TARGET_COLUMNS, *DERIVED_TARGETS):
        series = df.get_column(target).drop_nulls()
        quantiles = [_quantile(series, value) for value in (0.0, 0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99, 1.0)]
        rows.append(
            {
                "target": target,
                "count": series.len(),
                "nulls": df.height - series.len(),
                "mean": _float_or_none(series.mean()),
                "std": _float_or_none(series.std()),
                "zero_count": int((series == 0).sum()) if series.len() else 0,
                "zero_rate": float((series == 0).sum() / series.len()) if series.len() else None,
                "q00": quantiles[0],
                "q01": quantiles[1],
                "q05": quantiles[2],
                "q25": quantiles[3],
                "q50": quantiles[4],
                "q75": quantiles[5],
                "q95": quantiles[6],
                "q99": quantiles[7],
                "q100": quantiles[8],
            }
        )
    return pl.DataFrame(rows)


def _feature_target_correlations(df: pl.DataFrame, feature_cols: tuple[str, ...]) -> pl.DataFrame:
    rows: list[dict[str, Any]] = []
    for feature in feature_cols:
        for target in (*TARGET_COLUMNS, *DERIVED_TARGETS):
            pair = df.select([feature, target]).drop_nulls()
            pearson = _corr(pair, feature, target, "pearson")
            spearman = _corr(pair, feature, target, "spearman")
            rows.append(
                {
                    "feature": feature,
                    "target": target,
                    "pearson": pearson,
                    "spearman": spearman,
                    "abs_spearman": None if spearman is None else abs(spearman),
                    "rows": pair.height,
                }
            )
    return pl.DataFrame(rows).sort("abs_spearman", descending=True, nulls_last=True)


def _feature_bin_spreads(df: pl.DataFrame, feature_cols: tuple[str, ...]) -> pl.DataFrame:
    rows: list[dict[str, Any]] = []
    primary_targets = ("target_extreme_total", "target_mean_total", "target_extreme_up_minus_down", "target_mean_up_minus_down")
    for feature in feature_cols:
        series = df.get_column(feature).drop_nulls()
        if series.len() < 20:
            continue
        q20 = series.quantile(0.2)
        q80 = series.quantile(0.8)
        if q20 is None or q80 is None or q20 == q80:
            continue
        low = df.filter(pl.col(feature) <= q20)
        high = df.filter(pl.col(feature) >= q80)
        for target in primary_targets:
            low_mean = low.get_column(target).mean()
            high_mean = high.get_column(target).mean()
            rows.append(
                {
                    "feature": feature,
                    "target": target,
                    "q20": float(q20),
                    "q80": float(q80),
                    "low_mean": _float_or_none(low_mean),
                    "high_mean": _float_or_none(high_mean),
                    "high_minus_low": _float_or_none(None if low_mean is None or high_mean is None else high_mean - low_mean),
                    "low_rows": low.height,
                    "high_rows": high.height,
                }
            )
    schema = {
        "feature": pl.Utf8,
        "target": pl.Utf8,
        "q20": pl.Float64,
        "q80": pl.Float64,
        "low_mean": pl.Float64,
        "high_mean": pl.Float64,
        "high_minus_low": pl.Float64,
        "low_rows": pl.Int64,
        "high_rows": pl.Int64,
    }
    if not rows:
        return pl.DataFrame(schema=schema)
    return pl.DataFrame(rows, schema=schema).sort("high_minus_low", descending=True, nulls_last=True)


def _cross_timeframe_summary(df: pl.DataFrame, timeframes: tuple[str, ...]) -> pl.DataFrame:
    rows: list[dict[str, Any]] = []
    for suffix in ("range_to_tb_vol", "abs_ret_to_tb_vol", "range_efficiency_bnd"):
        values: list[float] = []
        cols = [f"rpf_vol_{timeframe}_{suffix}" for timeframe in timeframes]
        for left_idx, left in enumerate(cols):
            for right in cols[left_idx + 1 :]:
                pair = df.select([left, right]).drop_nulls()
                value = _corr(pair, left, right, "spearman")
                if value is not None:
                    values.append(abs(value))
        rows.append(
            {
                "suffix": suffix,
                "mean_abs_spearman": float(sum(values) / len(values)) if values else None,
                "max_abs_spearman": float(max(values)) if values else None,
                "min_abs_spearman": float(min(values)) if values else None,
            }
        )
    return pl.DataFrame(rows)


def _feature_quality(df: pl.DataFrame, feature_cols: tuple[str, ...]) -> pl.DataFrame:
    rows: list[dict[str, Any]] = []
    for feature in feature_cols:
        series = df.get_column(feature)
        nonnull = series.drop_nulls()
        rows.append(
            {
                "feature": feature,
                "nulls": int(series.is_null().sum()),
                "nonfinite": int(series.is_infinite().sum() + series.is_nan().sum()),
                "n_unique": int(nonnull.n_unique()),
                "zero_rate": float((nonnull == 0).sum() / nonnull.len()) if nonnull.len() else None,
                "min": _float_or_none(nonnull.min()) if nonnull.len() else None,
                "q01": _quantile(nonnull, 0.01),
                "q50": _quantile(nonnull, 0.5),
                "q99": _quantile(nonnull, 0.99),
                "max": _float_or_none(nonnull.max()) if nonnull.len() else None,
            }
        )
    return pl.DataFrame(rows)


def _corr(df: pl.DataFrame, left: str, right: str, method: str) -> float | None:
    if df.height < 3:
        return None
    value = df.select(pl.corr(left, right, method=method)).item()
    return _float_or_none(value)


def _quantile(series: pl.Series, value: float) -> float | None:
    if not series.len():
        return None
    return _float_or_none(series.quantile(value, interpolation="nearest"))


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    out = float(value)
    if math.isnan(out) or math.isinf(out):
        return None
    return out


def _markdown_report(
    summary: dict[str, Any],
    target_summary: pl.DataFrame,
    correlations: pl.DataFrame,
    bin_spreads: pl.DataFrame,
    cross_timeframe: pl.DataFrame,
) -> str:
    alignment_rows = [{"check": key, "value": value} for key, value in summary["alignment_violations"].items()]
    target_rows = target_summary.select(["target", "count", "zero_rate", "mean", "q50", "q95", "q99", "q100"]).to_dicts()
    corr_rows = correlations.head(12).select(["feature", "target", "spearman", "pearson", "rows"]).to_dicts()
    spread_rows = bin_spreads.head(12).select(["feature", "target", "low_mean", "high_mean", "high_minus_low"]).to_dicts()
    cross_rows = cross_timeframe.to_dicts()
    family_text = ", ".join(summary.get("families", [])) if summary.get("families") else "unknown"
    return f"""# Regression Feature Validation: {summary['asset']} {summary['root_key']}

Generated: {summary['generated_at']}

## Scope

- Feature set: `{summary['feature_set']}`
- Families: `{family_text}`
- Target variant: `{summary['target_variant']}`
- Feature rows from manifest: {summary['feature_rows_manifest']:,}
- Joined rows: {summary['joined_rows']:,}
- Valid regression rows: {summary['valid_rows']:,}
- Signal diagnostic sample rows: {summary['signal_sample_rows']:,}
- Feature columns: {summary['feature_count']}
- Diagnostic feature prefix: `{summary['diagnostic_feature_prefix']}`
- Diagnostic feature columns: {summary['diagnostic_feature_count']}
- Duplicate `timestamp,batch_id`: {summary['duplicate_timestamp_batch']}
- Null feature cells: {summary['null_feature_count']}
- Infinite feature cells: {summary['infinite_feature_count']}

## Alignment Checks

Closed higher-timeframe bars must never have `bar_close_ts > timestamp`.

{_markdown_table(alignment_rows, ['check', 'value'])}

## Target Distribution

{_markdown_table(target_rows, ['target', 'count', 'zero_rate', 'mean', 'q50', 'q95', 'q99', 'q100'])}

## Strongest Feature/Target Rank Signals

{_markdown_table(corr_rows, ['feature', 'target', 'spearman', 'pearson', 'rows'])}

## High-Low Quintile Spreads

Positive spread means target is larger when the feature is in its top quintile
than bottom quintile.

{_markdown_table(spread_rows, ['feature', 'target', 'low_mean', 'high_mean', 'high_minus_low'])}

## Cross-Timeframe Volatility Signal Correlation

{_markdown_table(cross_rows, ['suffix', 'mean_abs_spearman', 'max_abs_spearman', 'min_abs_spearman'])}

## Interpretation

This validation checks whether generated regression feature families are
finite, temporally safe, and related to the current regression targets in the
expected direction.

Root acceptance still requires walk-forward ablation; these reports are
feature-quality and signal-shape evidence, not model-promotion evidence.
"""


def _family_slug(families: Any) -> str:
    values = [str(value) for value in families if str(value) != "foundation_alignment"]
    if not values:
        return "foundation_alignment"
    slug = "_".join(values)
    if len(slug) <= 96:
        return slug
    digest = hashlib.sha1(slug.encode()).hexdigest()[:12]
    return f"families{len(values)}_{digest}"


def _markdown_table(rows: list[dict[str, Any]], columns: list[str]) -> str:
    def fmt(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, float):
            return f"{value:.6g}"
        return str(value)

    lines = ["| " + " | ".join(columns) + " |", "| " + " | ".join(["---"] * len(columns)) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(fmt(row.get(column)) for column in columns) + " |")
    return "\n".join(lines)


def _write_index(output_dir: Path, summaries: list[FeatureValidationSummary]) -> None:
    if not summaries:
        return
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = [
        {
            "asset_id": summary.asset_id,
            "root_key": summary.root_key,
            "root_id": summary.root_id,
            "report_path": str(summary.report_path),
            "joined_rows": summary.joined_rows,
            "valid_rows": summary.valid_rows,
            "feature_count": summary.feature_count,
            "duplicate_count": summary.duplicate_count,
            "null_feature_count": summary.null_feature_count,
            "infinite_feature_count": summary.infinite_feature_count,
            "future_close_violations": summary.future_close_violations,
            "strongest_abs_spearman": summary.strongest_abs_spearman,
        }
        for summary in summaries
    ]
    pl.DataFrame(rows).write_csv(output_dir / "validation_index.csv")
    (output_dir / "validation_index.json").write_text(json.dumps(rows, indent=2, default=str) + "\n")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate regression path feature roots.")
    parser.add_argument("--assets", default="BTCUSDT")
    parser.add_argument("--roots", nargs="*", default=["8h/B"], choices=sorted(STAGE1_MULTIASSET_ROOT_LAYOUTS))
    parser.add_argument("--timeframes", default=",".join(DEFAULT_TIMEFRAMES))
    parser.add_argument("--output-dir", default="test_output/regression_feature_engineering")
    parser.add_argument("--signal-sample-rows", type=int, default=25_000)
    parser.add_argument("--diagnostic-feature-prefix", default="")
    parser.add_argument("--max-diagnostic-columns", type=int, default=80)
    parser.add_argument("--allow-wide-diagnostics", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    summaries = validate_regression_feature_roots(
        project_root=PROJECT_ROOT,
        assets=parse_stage1_target_assets(args.assets),
        roots=tuple(args.roots),
        timeframes=normalize_timeframes(args.timeframes),
        output_dir=PROJECT_ROOT / args.output_dir,
        signal_sample_rows=max(0, int(args.signal_sample_rows)),
        diagnostic_feature_prefix=args.diagnostic_feature_prefix or None,
        max_diagnostic_columns=max(0, int(args.max_diagnostic_columns)),
        allow_wide_diagnostics=bool(args.allow_wide_diagnostics),
    )
    for summary in summaries:
        print(
            f"{summary.asset_id} {summary.root_key}: rows={summary.joined_rows:,} "
            f"valid={summary.valid_rows:,} features={summary.feature_count:,} "
            f"dup={summary.duplicate_count:,} null={summary.null_feature_count:,} "
            f"future_close_violations={summary.future_close_violations:,} "
            f"strongest_abs_spearman={summary.strongest_abs_spearman} "
            f"report={summary.report_path}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
