from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

_REPO_BOOTSTRAP_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_BOOTSTRAP_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_BOOTSTRAP_ROOT))

from scripts.analysis.materialize_stage1_target_variants import (  # noqa: E402
    ROOT_BACKTEST_DIRS,
    compute_prediction_time_indicators,
    parse_roots,
)
from scripts.feature_engineering.htf_asset_registry import normalize_htf_asset_id  # noqa: E402
from scripts.htf_backtest.catboost.stage1_multiasset_dataset import (  # noqa: E402
    REG_DISTANCE_HORIZON_VOL_V2_LABEL_SUFFIX as STAGE1_REG_DISTANCE_HORIZON_VOL_V2_LABEL_SUFFIX,
    REG_DISTANCE_HORIZON_VOL_V2_TARGET_COLS,
    REG_DISTANCE_VOL_V1_LABEL_SUFFIX,
    REG_DISTANCE_VOL_V1_TARGET_COLS,
    STAGE1_MULTIASSET_ROOT_LAYOUTS,
    parse_stage1_target_assets,
)
from scripts.project_paths import ensure_project_root_on_path  # noqa: E402


PROJECT_ROOT = ensure_project_root_on_path(Path(__file__))

REGRESSION_VARIANT = "distance_vol_v1"
VALID_COL = "target_reg_distance_valid_v1"
REASON_COL = "target_reg_distance_reason_v1"
FUTURE_BARS_COL = "target_reg_distance_future_bars_v1"
UP_EXTREME_COL = "target_reg_distance_up_extreme_vol_v1"
UP_MEAN_HIGH_COL = "target_reg_distance_up_mean_high_vol_v1"
DOWN_MEAN_LOW_COL = "target_reg_distance_down_mean_low_vol_v1"
DOWN_EXTREME_COL = "target_reg_distance_down_extreme_vol_v1"
TARGET_COLS = (
    UP_EXTREME_COL,
    UP_MEAN_HIGH_COL,
    DOWN_MEAN_LOW_COL,
    DOWN_EXTREME_COL,
)
if set(TARGET_COLS) != set(REG_DISTANCE_VOL_V1_TARGET_COLS):
    raise RuntimeError("Regression target columns are out of sync with Stage-1 mapping")

RAW_DISTANCE_COLS = (
    "target_reg_distance_up_extreme_pct_v1",
    "target_reg_distance_up_mean_high_pct_v1",
    "target_reg_distance_down_mean_low_pct_v1",
    "target_reg_distance_down_extreme_pct_v1",
)
EXTREME_METADATA_COLS = (
    "target_reg_distance_max_high_offset_v1",
    "target_reg_distance_max_high_ts_v1",
    "target_reg_distance_min_low_offset_v1",
    "target_reg_distance_min_low_ts_v1",
)
REPORT_QUANTILE_COLS = (
    *TARGET_COLS,
    *RAW_DISTANCE_COLS,
    "tb_volatility_pct",
    "tb_atr_pct_14",
    "tb_realized_vol_120",
)


@dataclass(frozen=True)
class RegressionTargetSummary:
    asset_id: str
    root_key: str
    variant: str
    output_dir: Path
    rows: int
    eligible_rows: int
    valid_rows: int
    invalid_ratio: float
    all_row_null_ratio: float
    diagnostics: dict[str, Any]


@dataclass(frozen=True)
class RegressionVariantSpec:
    variant: str
    label_suffix: str
    target_cols: tuple[str, ...]
    raw_distance_cols: tuple[str, ...]
    valid_col: str
    reason_col: str
    future_bars_col: str
    extreme_metadata_cols: tuple[str, ...]
    variant_col: str
    policy_col: str
    horizon_minutes_col: str | None = None
    horizon_vol_col: str | None = None


REGRESSION_VARIANT_HORIZON_VOL_V2 = "distance_horizon_vol_v2"
REG_DISTANCE_HORIZON_VOL_V2_LABEL_SUFFIX = "reg_distance_horizon_vol_v2"
if REG_DISTANCE_HORIZON_VOL_V2_LABEL_SUFFIX != STAGE1_REG_DISTANCE_HORIZON_VOL_V2_LABEL_SUFFIX:
    raise RuntimeError("Horizon-vol regression label suffix is out of sync with Stage-1 mapping")
VALID_COL_V2 = "target_reg_distance_valid_v2"
REASON_COL_V2 = "target_reg_distance_reason_v2"
FUTURE_BARS_COL_V2 = "target_reg_distance_future_bars_v2"
HORIZON_MINUTES_COL_V2 = "target_reg_distance_horizon_minutes_v2"
HORIZON_VOL_COL_V2 = "target_reg_distance_horizon_vol_pct_v2"
UP_EXTREME_HVOL_V2_COL = "target_reg_distance_up_extreme_hvol_v2"
UP_MEAN_HIGH_HVOL_V2_COL = "target_reg_distance_up_mean_high_hvol_v2"
DOWN_MEAN_LOW_HVOL_V2_COL = "target_reg_distance_down_mean_low_hvol_v2"
DOWN_EXTREME_HVOL_V2_COL = "target_reg_distance_down_extreme_hvol_v2"
EXTREME_UP_SHARE_HVOL_V2_COL = "target_reg_direction_extreme_up_share_hvol_v2"
MEAN_UP_SHARE_HVOL_V2_COL = "target_reg_direction_mean_up_share_hvol_v2"
TARGET_COLS_HVOL_V2 = (
    UP_EXTREME_HVOL_V2_COL,
    UP_MEAN_HIGH_HVOL_V2_COL,
    DOWN_MEAN_LOW_HVOL_V2_COL,
    DOWN_EXTREME_HVOL_V2_COL,
    EXTREME_UP_SHARE_HVOL_V2_COL,
    MEAN_UP_SHARE_HVOL_V2_COL,
)
if set(TARGET_COLS_HVOL_V2) != set(REG_DISTANCE_HORIZON_VOL_V2_TARGET_COLS):
    raise RuntimeError("Horizon-vol regression target columns are out of sync with Stage-1 mapping")
RAW_DISTANCE_COLS_HVOL_V2 = (
    "target_reg_distance_up_extreme_pct_v2",
    "target_reg_distance_up_mean_high_pct_v2",
    "target_reg_distance_down_mean_low_pct_v2",
    "target_reg_distance_down_extreme_pct_v2",
)
EXTREME_METADATA_COLS_HVOL_V2 = (
    "target_reg_distance_max_high_offset_v2",
    "target_reg_distance_max_high_ts_v2",
    "target_reg_distance_min_low_offset_v2",
    "target_reg_distance_min_low_ts_v2",
)

REGRESSION_VARIANT_SPECS = {
    REGRESSION_VARIANT: RegressionVariantSpec(
        variant=REGRESSION_VARIANT,
        label_suffix=REG_DISTANCE_VOL_V1_LABEL_SUFFIX,
        target_cols=TARGET_COLS,
        raw_distance_cols=RAW_DISTANCE_COLS,
        valid_col=VALID_COL,
        reason_col=REASON_COL,
        future_bars_col=FUTURE_BARS_COL,
        extreme_metadata_cols=EXTREME_METADATA_COLS,
        variant_col="target_reg_distance_variant_v1",
        policy_col="target_reg_distance_window_policy_v1",
    ),
    REGRESSION_VARIANT_HORIZON_VOL_V2: RegressionVariantSpec(
        variant=REGRESSION_VARIANT_HORIZON_VOL_V2,
        label_suffix=REG_DISTANCE_HORIZON_VOL_V2_LABEL_SUFFIX,
        target_cols=TARGET_COLS_HVOL_V2,
        raw_distance_cols=RAW_DISTANCE_COLS_HVOL_V2,
        valid_col=VALID_COL_V2,
        reason_col=REASON_COL_V2,
        future_bars_col=FUTURE_BARS_COL_V2,
        extreme_metadata_cols=EXTREME_METADATA_COLS_HVOL_V2,
        variant_col="target_reg_distance_variant_v2",
        policy_col="target_reg_distance_window_policy_v2",
        horizon_minutes_col=HORIZON_MINUTES_COL_V2,
        horizon_vol_col=HORIZON_VOL_COL_V2,
    ),
}


def normalize_variant(variant: str) -> str:
    variant = str(variant).strip().lower()
    if variant not in REGRESSION_VARIANT_SPECS:
        known = ", ".join(sorted(REGRESSION_VARIANT_SPECS))
        raise ValueError(f"Unknown regression target variant {variant!r}; expected one of: {known}")
    return variant


def variant_spec(variant: str = REGRESSION_VARIANT) -> RegressionVariantSpec:
    return REGRESSION_VARIANT_SPECS[normalize_variant(variant)]


def target_cols_for_variant(variant: str = REGRESSION_VARIANT) -> tuple[str, ...]:
    return variant_spec(variant).target_cols


def all_target_cols() -> tuple[str, ...]:
    cols: list[str] = []
    for spec in REGRESSION_VARIANT_SPECS.values():
        cols.extend(spec.target_cols)
    return tuple(cols)


def _bounded_up_share(up_value: float, down_value: float) -> float:
    """Return bounded upside share; neutral when both sides have zero reach."""

    up = max(float(up_value), 0.0)
    down = max(float(down_value), 0.0)
    total = up + down
    if total <= 0.0:
        return 0.5
    return min(max(up / total, 0.0), 1.0)


def compute_distance_regression_targets(
    rows: pl.DataFrame,
    window_15m: pl.DataFrame,
    *,
    variant: str = REGRESSION_VARIANT,
) -> pl.DataFrame:
    """Compute volatility-normalized future excursion targets.

    The volatility inputs are computed from prediction-time rows only. Future
    15m windows are used only to create label columns and diagnostics.
    """
    spec = variant_spec(variant)
    rows = compute_prediction_time_indicators(rows)
    windows = _build_window_lookup(window_15m)
    out = scan_distance_regression_targets(rows, windows, variant=variant)

    return rows.with_columns(
        [
            *[
                pl.Series(col, out[col], dtype=pl.Float64)
                for col in spec.target_cols
            ],
            *[
                pl.Series(col, out[col], dtype=pl.Float64)
                for col in spec.raw_distance_cols
            ],
            pl.Series(spec.valid_col, out[spec.valid_col], dtype=pl.Boolean),
            pl.Series(spec.reason_col, out[spec.reason_col], dtype=pl.Utf8),
            pl.Series(spec.future_bars_col, out[spec.future_bars_col], dtype=pl.Int32),
            pl.Series(spec.extreme_metadata_cols[0], out[spec.extreme_metadata_cols[0]], dtype=pl.Int32),
            pl.Series(spec.extreme_metadata_cols[1], out[spec.extreme_metadata_cols[1]]),
            pl.Series(spec.extreme_metadata_cols[2], out[spec.extreme_metadata_cols[2]], dtype=pl.Int32),
            pl.Series(spec.extreme_metadata_cols[3], out[spec.extreme_metadata_cols[3]]),
            *(
                [
                    pl.Series(spec.horizon_minutes_col, out[spec.horizon_minutes_col], dtype=pl.Float64),
                    pl.Series(spec.horizon_vol_col, out[spec.horizon_vol_col], dtype=pl.Float64),
                ]
                if spec.horizon_minutes_col and spec.horizon_vol_col
                else []
            ),
            pl.lit(spec.variant).alias(spec.variant_col),
            pl.lit("opposite_family_first_half").alias(spec.policy_col),
        ]
    )


def scan_distance_regression_targets(
    rows: pl.DataFrame,
    windows: dict[int, dict[str, Any]],
    *,
    variant: str = REGRESSION_VARIANT,
) -> dict[str, list[Any]]:
    """Scan future 15m windows and return nullable regression target arrays."""
    spec = variant_spec(variant)
    n = len(rows)
    out: dict[str, list[Any]] = {
        col: [None] * n
        for col in (
            *spec.target_cols,
            *spec.raw_distance_cols,
            *spec.extreme_metadata_cols,
            spec.valid_col,
            spec.reason_col,
            spec.future_bars_col,
            *(tuple() if spec.horizon_minutes_col is None else (spec.horizon_minutes_col,)),
            *(tuple() if spec.horizon_vol_col is None else (spec.horizon_vol_col,)),
        )
    }
    out[spec.valid_col] = [False] * n
    out[spec.reason_col] = ["invalid_inputs"] * n
    out[spec.future_bars_col] = [0] * n
    if spec.horizon_minutes_col:
        out[spec.horizon_minutes_col] = [None] * n
    if spec.horizon_vol_col:
        out[spec.horizon_vol_col] = [None] * n

    close = rows["close"].to_numpy().astype("float64")
    vol = rows["tb_volatility_pct"].to_numpy().astype("float64")
    label_batch = rows["label_window_batch_id"].fill_null(-1).to_numpy().astype("int64")
    is_label_half = (
        rows["is_label_half"].fill_null(False).to_numpy()
        if "is_label_half" in rows.columns
        else np.ones(n, dtype=bool)
    )

    for i in range(n):
        entry_close = close[i]
        volatility = vol[i]
        if not bool(is_label_half[i]):
            out[spec.reason_col][i] = "not_label_half"
            continue
        if not _finite_positive(entry_close):
            out[spec.reason_col][i] = "invalid_close"
            continue
        if not _finite_positive(volatility):
            out[spec.reason_col][i] = "invalid_volatility"
            continue

        window = windows.get(int(label_batch[i]))
        if window is None:
            out[spec.reason_col][i] = "missing_label_window"
            continue

        highs = window["high"]
        lows = window["low"]
        timestamps = window["timestamp"]
        if len(highs) == 0:
            out[spec.reason_col][i] = "empty_label_window"
            continue
        if not np.isfinite(highs).all() or not np.isfinite(lows).all():
            out[spec.reason_col][i] = "invalid_window_prices"
            continue

        up_pct = np.maximum((highs - entry_close) / entry_close, 0.0)
        down_pct = np.maximum((entry_close - lows) / entry_close, 0.0)
        up_extreme_pct = float(np.max(up_pct))
        up_mean_high_pct = float(np.mean(up_pct))
        down_mean_low_pct = float(np.mean(down_pct))
        down_extreme_pct = float(np.max(down_pct))
        max_high_offset = int(np.argmax(highs))
        min_low_offset = int(np.argmin(lows))
        denominator = volatility
        if spec.horizon_minutes_col and spec.horizon_vol_col:
            horizon_minutes = float(len(highs) * 15)
            denominator = float(volatility * math.sqrt(horizon_minutes))
            out[spec.horizon_minutes_col][i] = horizon_minutes
            out[spec.horizon_vol_col][i] = denominator

        out[spec.raw_distance_cols[0]][i] = up_extreme_pct
        out[spec.raw_distance_cols[1]][i] = up_mean_high_pct
        out[spec.raw_distance_cols[2]][i] = down_mean_low_pct
        out[spec.raw_distance_cols[3]][i] = down_extreme_pct
        out[spec.target_cols[0]][i] = up_extreme_pct / denominator
        out[spec.target_cols[1]][i] = up_mean_high_pct / denominator
        out[spec.target_cols[2]][i] = down_mean_low_pct / denominator
        out[spec.target_cols[3]][i] = down_extreme_pct / denominator
        if EXTREME_UP_SHARE_HVOL_V2_COL in spec.target_cols:
            out[EXTREME_UP_SHARE_HVOL_V2_COL][i] = _bounded_up_share(up_extreme_pct, down_extreme_pct)
        if MEAN_UP_SHARE_HVOL_V2_COL in spec.target_cols:
            out[MEAN_UP_SHARE_HVOL_V2_COL][i] = _bounded_up_share(up_mean_high_pct, down_mean_low_pct)
        out[spec.extreme_metadata_cols[0]][i] = max_high_offset
        out[spec.extreme_metadata_cols[1]][i] = timestamps[max_high_offset]
        out[spec.extreme_metadata_cols[2]][i] = min_low_offset
        out[spec.extreme_metadata_cols[3]][i] = timestamps[min_low_offset]
        out[spec.future_bars_col][i] = int(len(highs))
        out[spec.valid_col][i] = True
        out[spec.reason_col][i] = "ok"

    return out


def materialize_regression_targets(
    *,
    project_root: Path,
    assets: tuple[str, ...],
    roots: tuple[str, ...],
    variant: str = REGRESSION_VARIANT,
    batch_id_min: int | None = None,
    batch_id_max: int | None = None,
    batch_limit: int | None = None,
    write_sanity_report: bool = False,
) -> list[RegressionTargetSummary]:
    normalize_variant(variant)
    summaries: list[RegressionTargetSummary] = []
    for asset_id in assets:
        asset_id = normalize_htf_asset_id(asset_id)
        for root_key in roots:
            summaries.append(
                _materialize_asset_root(
                    project_root=project_root,
                    asset_id=asset_id,
                    root_key=root_key,
                    variant=variant,
                    batch_id_min=batch_id_min,
                    batch_id_max=batch_id_max,
                    batch_limit=batch_limit,
                )
            )
    if write_sanity_report:
        _write_sanity_report(project_root=project_root, summaries=summaries)
    return summaries


def _materialize_asset_root(
    *,
    project_root: Path,
    asset_id: str,
    root_key: str,
    variant: str,
    batch_id_min: int | None,
    batch_id_max: int | None,
    batch_limit: int | None,
) -> RegressionTargetSummary:
    spec = variant_spec(variant)
    layout = STAGE1_MULTIASSET_ROOT_LAYOUTS[root_key]
    entry_backtest_root, window_backtest_root = ROOT_BACKTEST_DIRS[root_key]
    asset_root = project_root / "data" / "htf_multiasset" / asset_id.lower()
    source_label_dir = asset_root / layout.label_root / "1m"
    window_path = asset_root / window_backtest_root / "15m_HTF_combined.parquet"
    if not source_label_dir.exists():
        raise FileNotFoundError(f"Source label directory not found: {source_label_dir}")
    if not window_path.exists():
        raise FileNotFoundError(f"Opposite-family 15m window file not found: {window_path}")

    rows = _read_label_rows(
        source_label_dir,
        batch_id_min=batch_id_min,
        batch_id_max=batch_id_max,
        batch_limit=batch_limit,
    )
    window = pl.read_parquet(window_path)
    labeled = compute_distance_regression_targets(rows, window, variant=variant)

    output_dir = asset_root / f"{layout.label_root}_{spec.label_suffix}" / "1m"
    output_dir.mkdir(parents=True, exist_ok=True)
    for stale in output_dir.glob("batch_*.parquet"):
        stale.unlink()

    output_cols = _ordered_output_columns(labeled)
    for batch_id, batch in labeled.partition_by(
        "batch_id",
        as_dict=True,
        maintain_order=True,
    ).items():
        key = int(batch_id[0] if isinstance(batch_id, tuple) else batch_id)
        batch.select(output_cols).write_parquet(output_dir / f"batch_{key:04d}.parquet")

    summary = _summarize_targets(
        labeled,
        asset_id=asset_id,
        root_key=root_key,
        variant=variant,
        output_dir=output_dir,
    )
    _write_meta(
        output_dir=output_dir,
        summary=summary,
        source_label_dir=source_label_dir,
        window_path=window_path,
        entry_backtest_root=entry_backtest_root,
        window_backtest_root=window_backtest_root,
        batch_id_min=batch_id_min,
        batch_id_max=batch_id_max,
        batch_limit=batch_limit,
    )
    return summary


def _read_label_rows(
    source_label_dir: Path,
    *,
    batch_id_min: int | None,
    batch_id_max: int | None,
    batch_limit: int | None,
) -> pl.DataFrame:
    paths = sorted(source_label_dir.glob("batch_*.parquet"))
    if batch_id_min is not None:
        paths = [path for path in paths if _batch_id(path) >= int(batch_id_min)]
    if batch_id_max is not None:
        paths = [path for path in paths if _batch_id(path) <= int(batch_id_max)]
    if batch_limit is not None:
        paths = paths[: int(batch_limit)]
    if not paths:
        raise FileNotFoundError(f"No selected batch_*.parquet files in {source_label_dir}")

    required = {
        "timestamp",
        "batch_id",
        "open",
        "high",
        "low",
        "close",
        "label_window_batch_id",
        "is_label_half",
    }
    schema = pl.read_parquet(paths[0], n_rows=0).schema
    missing = required - set(schema)
    if missing:
        raise ValueError(f"Source labels missing required columns: {sorted(missing)}")

    rows = pl.read_parquet([str(path) for path in paths]).sort(["batch_id", "timestamp"])
    if len(rows) != rows.select(["timestamp", "batch_id"]).unique().height:
        raise ValueError(f"Duplicate timestamp,batch_id rows in {source_label_dir}")
    return rows


def _build_window_lookup(window_15m: pl.DataFrame) -> dict[int, dict[str, Any]]:
    required = {"batch_id", "timestamp", "high", "low"}
    missing = required - set(window_15m.columns)
    if missing:
        raise ValueError(f"Window 15m frame missing columns: {sorted(missing)}")
    if "is_label_half" in window_15m.columns:
        window_15m = window_15m.filter(pl.col("is_label_half"))
    pos_col = "family_bar_pos" if "family_bar_pos" in window_15m.columns else "timestamp"

    windows: dict[int, dict[str, Any]] = {}
    for batch_id, part in window_15m.sort(["batch_id", pos_col]).partition_by(
        "batch_id",
        as_dict=True,
        maintain_order=True,
    ).items():
        key = int(batch_id[0] if isinstance(batch_id, tuple) else batch_id)
        windows[key] = {
            "high": part["high"].to_numpy().astype("float64"),
            "low": part["low"].to_numpy().astype("float64"),
            "timestamp": part["timestamp"].to_list(),
        }
    return windows


def _batch_id(path: Path) -> int:
    return int(path.stem.removeprefix("batch_"))


def _finite_positive(value: float) -> bool:
    return bool(np.isfinite(value) and value > 0.0)


def _ordered_output_columns(df: pl.DataFrame) -> list[str]:
    target_cols = [col for col in all_target_cols() if col in df.columns]
    spec = next(
        (item for item in REGRESSION_VARIANT_SPECS.values() if any(col in df.columns for col in item.target_cols)),
        REGRESSION_VARIANT_SPECS[REGRESSION_VARIANT],
    )
    preferred = [
        "timestamp",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "batch_id",
        *target_cols,
        spec.valid_col,
        spec.reason_col,
        spec.future_bars_col,
        *(tuple() if spec.horizon_minutes_col is None else (spec.horizon_minutes_col,)),
        *(tuple() if spec.horizon_vol_col is None else (spec.horizon_vol_col,)),
        *spec.raw_distance_cols,
        *spec.extreme_metadata_cols,
        "tb_volatility_pct",
        "tb_atr_pct_14",
        "tb_realized_vol_120",
        spec.variant_col,
        spec.policy_col,
        "target_4class",
        "target_name",
        "target_breakfree",
        "label_window_policy",
        "label_entry_family",
        "label_window_family",
        "label_window_batch_id",
        "label_window_start",
        "label_window_end",
    ]
    ordered = [col for col in preferred if col in df.columns]
    ordered.extend(col for col in df.columns if col not in set(ordered) and not col.startswith("_tb_"))
    return ordered


def _summarize_targets(
    df: pl.DataFrame,
    *,
    asset_id: str,
    root_key: str,
    variant: str,
    output_dir: Path,
) -> RegressionTargetSummary:
    spec = variant_spec(variant)
    rows = len(df)
    eligible = df.filter(pl.col("is_label_half")) if "is_label_half" in df.columns else df
    eligible_rows = len(eligible)
    valid = eligible.filter(pl.col(spec.valid_col))
    valid_rows = len(valid)
    invalid_ratio = 1.0 - (valid_rows / eligible_rows if eligible_rows else 0.0)
    all_valid_rows = int(df.filter(pl.col(spec.valid_col)).height)
    all_row_null_ratio = 1.0 - (all_valid_rows / rows if rows else 0.0)
    report_cols = (
        *spec.target_cols,
        *spec.raw_distance_cols,
        "tb_volatility_pct",
        "tb_atr_pct_14",
        "tb_realized_vol_120",
        *(tuple() if spec.horizon_minutes_col is None else (spec.horizon_minutes_col,)),
        *(tuple() if spec.horizon_vol_col is None else (spec.horizon_vol_col,)),
    )
    diagnostics = {
        "reason_counts": _reason_counts(eligible, reason_col=spec.reason_col),
        "quantiles": _quantiles(valid, report_cols),
        "batch_summary": _batch_summary(df),
    }
    return RegressionTargetSummary(
        asset_id=asset_id,
        root_key=root_key,
        variant=variant,
        output_dir=output_dir,
        rows=rows,
        eligible_rows=eligible_rows,
        valid_rows=valid_rows,
        invalid_ratio=invalid_ratio,
        all_row_null_ratio=all_row_null_ratio,
        diagnostics=diagnostics,
    )


def _reason_counts(df: pl.DataFrame, *, reason_col: str = REASON_COL) -> dict[str, int]:
    if df.is_empty():
        return {}
    counts = df.group_by(reason_col).len().sort("len", descending=True)
    return {str(row[reason_col]): int(row["len"]) for row in counts.iter_rows(named=True)}


def _quantiles(df: pl.DataFrame, columns: tuple[str, ...]) -> dict[str, dict[str, float | None]]:
    out: dict[str, dict[str, float | None]] = {}
    for col in columns:
        if col not in df.columns:
            continue
        series = df[col].drop_nulls()
        if series.is_empty():
            out[col] = {key: None for key in ("min", "p25", "p50", "p75", "p95", "p99", "max", "mean")}
            continue
        out[col] = {
            "min": _safe_float(series.min()),
            "p25": _safe_float(series.quantile(0.25)),
            "p50": _safe_float(series.quantile(0.50)),
            "p75": _safe_float(series.quantile(0.75)),
            "p95": _safe_float(series.quantile(0.95)),
            "p99": _safe_float(series.quantile(0.99)),
            "max": _safe_float(series.max()),
            "mean": _safe_float(series.mean()),
        }
    return out


def _batch_summary(df: pl.DataFrame) -> dict[str, Any]:
    spec = next(
        (item for item in REGRESSION_VARIANT_SPECS.values() if item.valid_col in df.columns),
        REGRESSION_VARIANT_SPECS[REGRESSION_VARIANT],
    )
    if df.is_empty():
        return {"batch_count": 0, "valid_rows_min": 0, "valid_rows_median": 0, "valid_rows_max": 0}
    by_batch = (
        df.group_by("batch_id")
        .agg(
            [
                pl.len().alias("rows"),
                pl.col(spec.valid_col).sum().alias("valid_rows"),
            ]
        )
        .sort("batch_id")
    )
    valid_rows = by_batch["valid_rows"]
    return {
        "batch_count": int(by_batch.height),
        "first_batch_id": int(by_batch["batch_id"].min()),
        "last_batch_id": int(by_batch["batch_id"].max()),
        "valid_rows_min": int(valid_rows.min()),
        "valid_rows_median": _safe_float(valid_rows.median()),
        "valid_rows_max": int(valid_rows.max()),
    }


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    value = float(value)
    if math.isnan(value) or math.isinf(value):
        return None
    return value


def _write_meta(
    *,
    output_dir: Path,
    summary: RegressionTargetSummary,
    source_label_dir: Path,
    window_path: Path,
    entry_backtest_root: str,
    window_backtest_root: str,
    batch_id_min: int | None,
    batch_id_max: int | None,
    batch_limit: int | None,
) -> None:
    spec = variant_spec(summary.variant)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "asset_id": summary.asset_id,
        "root": summary.root_key,
        "variant": summary.variant,
        "target_columns": list(spec.target_cols),
        "valid_column": spec.valid_col,
        "reason_column": spec.reason_col,
        "label_root_suffix": spec.label_suffix,
        "source_label_dir": str(source_label_dir),
        "window_15m_path": str(window_path),
        "entry_backtest_root": entry_backtest_root,
        "window_backtest_root": window_backtest_root,
        "batch_id_min": batch_id_min,
        "batch_id_max": batch_id_max,
        "batch_limit": batch_limit,
        "rows": summary.rows,
        "eligible_rows": summary.eligible_rows,
        "valid_rows": summary.valid_rows,
        "invalid_ratio": summary.invalid_ratio,
        "all_row_null_ratio": summary.all_row_null_ratio,
        "diagnostics": summary.diagnostics,
    }
    (output_dir / f"{summary.variant}_meta.json").write_text(
        json.dumps(payload, indent=2, default=str)
    )


def _write_sanity_report(
    *,
    project_root: Path,
    summaries: list[RegressionTargetSummary],
) -> Path:
    today = datetime.now(timezone.utc).date().isoformat()
    report_dir = project_root / "docs" / "research"
    report_dir.mkdir(parents=True, exist_ok=True)
    if len(summaries) == 1:
        summary = summaries[0]
        report_path = (
            report_dir
            / f"reg-distance-target-sanity-{summary.variant}-{summary.root_key.lower().replace('/', '-')}-{summary.asset_id.lower()}-{today}.md"
        )
    else:
        variants = "_".join(sorted({summary.variant for summary in summaries}))
        report_path = report_dir / f"reg-distance-target-sanity-{variants}-{today}.md"

    lines = [
        "# Volatility-Normalized Distance Target Sanity",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        "These targets are label-only research artifacts. They are normalized by",
        "prediction-time volatility and must not be joined as model features.",
        "",
        "| Asset | Root | Rows | Eligible | Valid | Invalid Ratio | Output |",
        "|---|---|---:|---:|---:|---:|---|",
    ]
    for summary in summaries:
        lines.append(
            "| "
            f"{summary.asset_id} | {summary.root_key} | {summary.rows:,} | "
            f"{summary.eligible_rows:,} | {summary.valid_rows:,} | "
            f"{summary.invalid_ratio:.2%} | `{summary.output_dir}` |"
        )

    for summary in summaries:
        spec = variant_spec(summary.variant)
        lines.extend(
            [
                "",
                f"## {summary.asset_id} {summary.root_key}",
                "",
                "Reason counts:",
                "",
            ]
        )
        for reason, count in summary.diagnostics["reason_counts"].items():
            lines.append(f"- `{reason}`: {count:,}")
        lines.extend(["", "Target quantiles:", "", "| Column | P50 | P95 | P99 | Max | Mean |", "|---|---:|---:|---:|---:|---:|"])
        for col in spec.target_cols:
            q = summary.diagnostics["quantiles"].get(col, {})
            lines.append(
                f"| `{col}` | {_fmt(q.get('p50'))} | {_fmt(q.get('p95'))} | "
                f"{_fmt(q.get('p99'))} | {_fmt(q.get('max'))} | {_fmt(q.get('mean'))} |"
            )
        vol = summary.diagnostics["quantiles"].get("tb_volatility_pct", {})
        hvol = summary.diagnostics["quantiles"].get(spec.horizon_vol_col or "", {})
        lines.extend(
            [
                "",
                "Prediction-time volatility:",
                "",
                f"- p50: {_fmt(vol.get('p50'))}",
                f"- p95: {_fmt(vol.get('p95'))}",
                f"- max: {_fmt(vol.get('max'))}",
            ]
        )
        if spec.horizon_vol_col:
            lines.extend(
                [
                    "",
                    "Horizon-adjusted volatility:",
                    "",
                    f"- p50: {_fmt(hvol.get('p50'))}",
                    f"- p95: {_fmt(hvol.get('p95'))}",
                    f"- max: {_fmt(hvol.get('max'))}",
                ]
            )

    report_path.write_text("\n".join(lines) + "\n")
    return report_path


def _fmt(value: Any) -> str:
    if value is None:
        return "-"
    return f"{float(value):.6g}"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Materialize experimental Stage-1 volatility-normalized distance "
            "regression targets from existing HTF label rows."
        )
    )
    parser.add_argument("--assets", default="BTCUSDT", help="Asset selector, e.g. BTCUSDT or core.")
    parser.add_argument("--roots", nargs="*", default=["8h/B"], help="Stage-1 roots, e.g. 8h/B.")
    parser.add_argument(
        "--variant",
        default=REGRESSION_VARIANT,
        choices=sorted(REGRESSION_VARIANT_SPECS),
        help="Regression target variant to materialize.",
    )
    parser.add_argument("--batch-id-min", type=int, default=None)
    parser.add_argument("--batch-id-max", type=int, default=None)
    parser.add_argument("--batch-limit", type=int, default=None)
    parser.add_argument("--write-sanity-report", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    summaries = materialize_regression_targets(
        project_root=PROJECT_ROOT,
        assets=parse_stage1_target_assets(args.assets),
        roots=parse_roots(args.roots),
        variant=normalize_variant(args.variant),
        batch_id_min=args.batch_id_min,
        batch_id_max=args.batch_id_max,
        batch_limit=args.batch_limit,
        write_sanity_report=bool(args.write_sanity_report),
    )
    for summary in summaries:
        print(
            f"{summary.asset_id} {summary.root_key} {summary.variant}: "
            f"rows={summary.rows:,} eligible={summary.eligible_rows:,} "
            f"valid={summary.valid_rows:,} invalid={summary.invalid_ratio:.2%} "
            f"output={summary.output_dir}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
