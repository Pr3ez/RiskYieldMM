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

from scripts.feature_engineering.htf_asset_registry import normalize_htf_asset_id  # noqa: E402
from scripts.htf_backtest.catboost.stage1_multiasset_dataset import (  # noqa: E402
    STAGE1_MULTIASSET_ROOT_LAYOUTS,
    parse_stage1_target_assets,
)
from scripts.project_paths import ensure_project_root_on_path  # noqa: E402


PROJECT_ROOT = ensure_project_root_on_path(Path(__file__))

TARGET_CLASS_NAMES = {
    -1: "INVALID",
    0: "DOWN_BALANCED",
    1: "DOWN_EXPANSION",
    2: "UP_BALANCED",
    3: "UP_EXPANSION",
}

TB_ATR_PERIOD = 14
TB_REALIZED_VOL_PERIOD = 120
TB_BB_PERIOD = 20
TB_BB_STD = 2.0
TB_KELTNER_EMA_PERIOD = 20
TB_KELTNER_ATR_MULT = 2.0
TB_K_UP = 2.0
TB_K_DOWN = 1.5
TB_TERMINAL_THETA = 0.25
TB_MIN_VOLATILITY_PCT = 0.0005
TB_MIN_BARRIER_PCT = 0.0005
TB_MAX_BARRIER_PCT = 0.05
VARIANT_SPECS: dict[str, dict[str, Any]] = {
    "tb_atr_v1": {
        "barrier_mode": "atr",
        "k_up": TB_K_UP,
        "k_down": TB_K_DOWN,
        "terminal_theta": TB_TERMINAL_THETA,
        "description": "Initial asymmetric ATR baseline from the research brief.",
    },
    "tb_bollinger_v1": {
        "barrier_mode": "bollinger",
        "k_up": TB_K_UP,
        "k_down": TB_K_DOWN,
        "terminal_theta": TB_TERMINAL_THETA,
        "description": "ATR baseline clipped to valid prediction-time Bollinger bands.",
    },
    "tb_keltner_v1": {
        "barrier_mode": "keltner",
        "k_up": TB_K_UP,
        "k_down": TB_K_DOWN,
        "terminal_theta": TB_TERMINAL_THETA,
        "description": "ATR baseline clipped to valid prediction-time Keltner bands.",
    },
    "tb_atr_wide_v2": {
        "barrier_mode": "atr",
        "k_up": 15.0,
        "k_down": 15.0,
        "terminal_theta": 0.0,
        "description": (
            "Wider symmetric ATR candidate introduced after BTCUSDT 8h/B sanity "
            "showed v1 barriers collapsed almost all eligible rows into expansion classes."
        ),
    },
}
SUPPORTED_VARIANTS = tuple(VARIANT_SPECS)

SANITY_INVALID_MAX = 0.35
SANITY_SAME_BAR_MAX = 0.10
SANITY_MIN_CLASS_SHARE = 0.05

ROOT_BACKTEST_DIRS = {
    "8h/B": ("htf_backtest", "htf_backtest_shift4h"),
    "8h/C": ("htf_backtest_shift4h", "htf_backtest"),
    "24h/B": ("htf_backtest_24h", "htf_backtest_24h_shift12h"),
    "24h/C": ("htf_backtest_24h_shift12h", "htf_backtest_24h"),
    "7d/B": ("htf_backtest_7d", "htf_backtest_7d_shift84h"),
    "7d/C": ("htf_backtest_7d_shift84h", "htf_backtest_7d"),
}


@dataclass(frozen=True)
class TargetVariantSummary:
    asset_id: str
    root_key: str
    variant: str
    target_col: str
    output_dir: Path
    rows: int
    eligible_rows: int
    non_entry_rows: int
    valid_rows: int
    invalid_ratio: float
    all_row_invalid_ratio: float
    same_bar_both_hit_ratio: float
    class_share: dict[int, float]
    model_ready: bool
    model_ready_reasons: tuple[str, ...]
    diagnostics: dict[str, Any]


def target_col_for_variant(variant: str) -> str:
    """Return the Stage-1 target column for one experimental variant."""
    variant = normalize_variant(variant)
    return f"target_4class_{variant}"


def normalize_variant(variant: str) -> str:
    variant = str(variant).strip().lower()
    if variant not in SUPPORTED_VARIANTS:
        raise ValueError(
            f"Unknown target variant {variant!r}; expected one of: "
            f"{', '.join(SUPPORTED_VARIANTS)}"
        )
    return variant


def variant_spec(variant: str) -> dict[str, Any]:
    """Return immutable-style parameter metadata for one target variant."""
    return dict(VARIANT_SPECS[normalize_variant(variant)])


def parse_variants(raw: str | None) -> tuple[str, ...]:
    if raw is None or not raw.strip():
        return ("tb_atr_v1",)
    if raw.strip().lower() == "all":
        return SUPPORTED_VARIANTS
    variants = [normalize_variant(part) for part in raw.split(",") if part.strip()]
    return tuple(dict.fromkeys(variants))


def parse_roots(raw: list[str] | None) -> tuple[str, ...]:
    if not raw:
        return ("8h/B",)
    roots = tuple(dict.fromkeys(raw))
    unknown = sorted(set(roots) - set(STAGE1_MULTIASSET_ROOT_LAYOUTS))
    if unknown:
        known = ", ".join(sorted(STAGE1_MULTIASSET_ROOT_LAYOUTS))
        raise ValueError(f"Unknown roots {unknown}; expected one of: {known}")
    return roots


def compute_prediction_time_indicators(rows: pl.DataFrame) -> pl.DataFrame:
    """Add causal volatility/band inputs used to construct target barriers."""
    true_range = pl.max_horizontal(
        (pl.col("high") - pl.col("low")).abs(),
        (pl.col("high") - pl.col("close").shift(1)).abs(),
        (pl.col("low") - pl.col("close").shift(1)).abs(),
    )
    return (
        rows.sort("timestamp")
        .with_columns(
            [
                true_range.alias("_tb_true_range"),
                ((pl.col("close") / pl.col("close").shift(1)) - 1.0).alias(
                    "_tb_return_1m"
                ),
                pl.col("close")
                .rolling_mean(window_size=TB_BB_PERIOD, min_samples=TB_BB_PERIOD)
                .alias("_tb_bb_middle"),
                pl.col("close")
                .rolling_std(window_size=TB_BB_PERIOD, min_samples=TB_BB_PERIOD)
                .alias("_tb_bb_std"),
                pl.col("close")
                .ewm_mean(span=TB_KELTNER_EMA_PERIOD, adjust=False)
                .alias("_tb_keltner_middle"),
            ]
        )
        .with_columns(
            [
                pl.col("_tb_true_range")
                .rolling_mean(window_size=TB_ATR_PERIOD, min_samples=TB_ATR_PERIOD)
                .alias("_tb_atr"),
                pl.col("_tb_return_1m")
                .rolling_std(
                    window_size=TB_REALIZED_VOL_PERIOD,
                    min_samples=TB_REALIZED_VOL_PERIOD,
                )
                .alias("_tb_realized_vol"),
            ]
        )
        .with_columns(
            [
                (pl.col("_tb_atr") / pl.col("close")).alias("tb_atr_pct_14"),
                pl.col("_tb_realized_vol").alias("tb_realized_vol_120"),
                (pl.col("_tb_bb_middle") + TB_BB_STD * pl.col("_tb_bb_std")).alias(
                    "_tb_bb_upper"
                ),
                (pl.col("_tb_bb_middle") - TB_BB_STD * pl.col("_tb_bb_std")).alias(
                    "_tb_bb_lower"
                ),
                (
                    pl.col("_tb_keltner_middle")
                    + TB_KELTNER_ATR_MULT * pl.col("_tb_atr")
                ).alias("_tb_keltner_upper"),
                (
                    pl.col("_tb_keltner_middle")
                    - TB_KELTNER_ATR_MULT * pl.col("_tb_atr")
                ).alias("_tb_keltner_lower"),
            ]
        )
        .with_columns(
            [
                pl.max_horizontal("tb_atr_pct_14", "tb_realized_vol_120")
                .clip(lower_bound=TB_MIN_VOLATILITY_PCT)
                .alias("tb_volatility_pct"),
            ]
        )
    )


def compute_variant_barriers(rows: pl.DataFrame, *, variant: str) -> pl.DataFrame:
    """Construct prediction-time upper/lower barriers for one variant."""
    variant = normalize_variant(variant)
    spec = variant_spec(variant)
    k_up = float(spec["k_up"])
    k_down = float(spec["k_down"])
    mode = str(spec["barrier_mode"])
    base = rows.with_columns(
        [
            (k_up * pl.col("tb_volatility_pct"))
            .clip(TB_MIN_BARRIER_PCT, TB_MAX_BARRIER_PCT)
            .alias("_tb_upper_distance_base"),
            (k_down * pl.col("tb_volatility_pct"))
            .clip(TB_MIN_BARRIER_PCT, TB_MAX_BARRIER_PCT)
            .alias("_tb_lower_distance_base"),
        ]
    ).with_columns(
        [
            (pl.col("close") * (1.0 + pl.col("_tb_upper_distance_base"))).alias(
                "_tb_upper_atr"
            ),
            (pl.col("close") * (1.0 - pl.col("_tb_lower_distance_base"))).alias(
                "_tb_lower_atr"
            ),
        ]
    )

    if mode == "atr":
        upper_expr = pl.col("_tb_upper_atr")
        lower_expr = pl.col("_tb_lower_atr")
    elif mode == "bollinger":
        upper_expr = (
            pl.when(
                pl.col("_tb_bb_upper").is_not_null()
                & (pl.col("_tb_bb_upper") > pl.col("close") * (1.0 + TB_MIN_BARRIER_PCT))
            )
            .then(pl.min_horizontal("_tb_upper_atr", "_tb_bb_upper"))
            .otherwise(pl.col("_tb_upper_atr"))
        )
        lower_expr = (
            pl.when(
                pl.col("_tb_bb_lower").is_not_null()
                & (pl.col("_tb_bb_lower") < pl.col("close") * (1.0 - TB_MIN_BARRIER_PCT))
            )
            .then(pl.max_horizontal("_tb_lower_atr", "_tb_bb_lower"))
            .otherwise(pl.col("_tb_lower_atr"))
        )
    elif mode == "keltner":
        upper_expr = (
            pl.when(
                pl.col("_tb_keltner_upper").is_not_null()
                & (
                    pl.col("_tb_keltner_upper")
                    > pl.col("close") * (1.0 + TB_MIN_BARRIER_PCT)
                )
            )
            .then(pl.min_horizontal("_tb_upper_atr", "_tb_keltner_upper"))
            .otherwise(pl.col("_tb_upper_atr"))
        )
        lower_expr = (
            pl.when(
                pl.col("_tb_keltner_lower").is_not_null()
                & (
                    pl.col("_tb_keltner_lower")
                    < pl.col("close") * (1.0 - TB_MIN_BARRIER_PCT)
                )
            )
            .then(pl.max_horizontal("_tb_lower_atr", "_tb_keltner_lower"))
            .otherwise(pl.col("_tb_lower_atr"))
        )
    else:  # pragma: no cover - normalize_variant guards this.
        raise ValueError(f"Unsupported barrier mode for {variant}: {mode}")

    return base.with_columns(
        [
            upper_expr.alias("tb_upper_barrier"),
            lower_expr.alias("tb_lower_barrier"),
        ]
    ).with_columns(
        [
            ((pl.col("tb_upper_barrier") - pl.col("close")) / pl.col("close")).alias(
                "tb_upper_distance_pct"
            ),
            ((pl.col("close") - pl.col("tb_lower_barrier")) / pl.col("close")).alias(
                "tb_lower_distance_pct"
            ),
        ]
    )


def compute_triple_barrier_targets(
    rows: pl.DataFrame,
    window_15m: pl.DataFrame,
    *,
    variant: str,
) -> pl.DataFrame:
    """Assign four-class triple-barrier labels from future label-window bars."""
    variant = normalize_variant(variant)
    spec = variant_spec(variant)
    rows = compute_variant_barriers(
        compute_prediction_time_indicators(rows),
        variant=variant,
    )
    windows = _build_window_lookup(window_15m)
    out = _scan_barriers(
        rows,
        windows,
        terminal_theta=float(spec["terminal_theta"]),
    )
    target_col = target_col_for_variant(variant)
    name_col = f"{target_col}_name"
    return rows.with_columns(
        [
            pl.Series(target_col, out["target"]).cast(pl.Int32),
            pl.Series(name_col, out["target_name"]),
            pl.Series("tb_first_hit", out["first_hit"]),
            pl.Series("tb_hit_bar_offset", out["hit_bar_offset"]).cast(pl.Int32),
            pl.Series("tb_same_bar_both_hit", out["same_bar_both_hit"]),
            pl.Series("tb_terminal_return", out["terminal_return"]),
            pl.Series("tb_terminal_z", out["terminal_z"]),
            pl.Series("tb_mfe_pct", out["mfe_pct"]),
            pl.Series("tb_mae_pct", out["mae_pct"]),
            pl.Series("tb_remaining_bars", out["remaining_bars"]).cast(pl.Int32),
            pl.Series("tb_label_reason", out["label_reason"]),
            pl.lit(str(spec["barrier_mode"])).alias("tb_barrier_mode"),
            pl.lit(variant).alias("tb_label_version"),
        ]
    )


def _build_window_lookup(window_15m: pl.DataFrame) -> dict[int, dict[str, np.ndarray]]:
    required = {"batch_id", "timestamp", "high", "low", "close"}
    missing = required - set(window_15m.columns)
    if missing:
        raise ValueError(f"Window 15m frame missing columns: {sorted(missing)}")
    if "is_label_half" in window_15m.columns:
        window_15m = window_15m.filter(pl.col("is_label_half"))
    pos_col = "family_bar_pos" if "family_bar_pos" in window_15m.columns else "timestamp"
    windows: dict[int, dict[str, np.ndarray]] = {}
    for batch_id, part in window_15m.sort(["batch_id", pos_col]).partition_by(
        "batch_id",
        as_dict=True,
        maintain_order=True,
    ).items():
        key = int(batch_id[0] if isinstance(batch_id, tuple) else batch_id)
        windows[key] = {
            "high": part["high"].to_numpy().astype("float64"),
            "low": part["low"].to_numpy().astype("float64"),
            "close": part["close"].to_numpy().astype("float64"),
        }
    return windows


def _scan_barriers(
    rows: pl.DataFrame,
    windows: dict[int, dict[str, np.ndarray]],
    *,
    terminal_theta: float = TB_TERMINAL_THETA,
) -> dict[str, Any]:
    n = len(rows)
    target = np.full(n, -1, dtype=np.int32)
    hit_offset = np.full(n, -1, dtype=np.int32)
    remaining_bars = np.zeros(n, dtype=np.int32)
    same_bar = np.zeros(n, dtype=bool)
    terminal_return = np.full(n, np.nan, dtype=np.float64)
    terminal_z = np.full(n, np.nan, dtype=np.float64)
    mfe_pct = np.full(n, np.nan, dtype=np.float64)
    mae_pct = np.full(n, np.nan, dtype=np.float64)
    first_hit = np.full(n, "invalid", dtype=object)
    label_reason = np.full(n, "invalid_inputs", dtype=object)

    close = rows["close"].to_numpy().astype("float64")
    close_end = (
        rows["close_end"].to_numpy().astype("float64")
        if "close_end" in rows.columns
        else np.full(n, np.nan, dtype=np.float64)
    )
    upper = rows["tb_upper_barrier"].to_numpy().astype("float64")
    lower = rows["tb_lower_barrier"].to_numpy().astype("float64")
    vol = rows["tb_volatility_pct"].to_numpy().astype("float64")
    label_batch = rows["label_window_batch_id"].fill_null(-1).to_numpy().astype("int64")
    is_label_half = (
        rows["is_label_half"].fill_null(False).to_numpy()
        if "is_label_half" in rows.columns
        else np.ones(n, dtype=bool)
    )

    for i in range(n):
        entry_close = close[i]
        batch_id = int(label_batch[i])
        window = windows.get(batch_id)
        if (
            not bool(is_label_half[i])
            or window is None
            or not _finite_positive(entry_close)
            or not _finite_positive(upper[i])
            or not _finite_positive(lower[i])
            or not _finite_positive(vol[i])
            or upper[i] <= entry_close
            or lower[i] >= entry_close
        ):
            continue

        highs = window["high"]
        lows = window["low"]
        closes = window["close"]
        if len(highs) == 0:
            continue
        remaining_bars[i] = int(len(highs))
        mfe_pct[i] = (float(np.nanmax(highs)) - entry_close) / entry_close
        mae_pct[i] = (float(np.nanmin(lows)) - entry_close) / entry_close

        assigned = False
        for offset, (high, low) in enumerate(zip(highs, lows, strict=True)):
            up_hit = bool(np.isfinite(high) and high >= upper[i])
            down_hit = bool(np.isfinite(low) and low <= lower[i])
            if up_hit and down_hit:
                same_bar[i] = True
                first_hit[i] = "both_same_bar"
                label_reason[i] = "same_bar_both_hit"
                hit_offset[i] = int(offset)
                assigned = True
                break
            if up_hit:
                target[i] = 3
                first_hit[i] = "upper"
                label_reason[i] = "upper_hit_first"
                hit_offset[i] = int(offset)
                assigned = True
                break
            if down_hit:
                target[i] = 1
                first_hit[i] = "lower"
                label_reason[i] = "lower_hit_first"
                hit_offset[i] = int(offset)
                assigned = True
                break
        if assigned:
            continue

        end_close = close_end[i] if np.isfinite(close_end[i]) else closes[-1]
        terminal_return[i] = (end_close - entry_close) / entry_close
        terminal_z[i] = terminal_return[i] / vol[i]
        if terminal_z[i] >= terminal_theta:
            target[i] = 2
            first_hit[i] = "terminal"
            label_reason[i] = "terminal_up"
        elif terminal_z[i] <= -terminal_theta:
            target[i] = 0
            first_hit[i] = "terminal"
            label_reason[i] = "terminal_down"
        else:
            first_hit[i] = "terminal"
            label_reason[i] = "terminal_neutral_invalid"

    return {
        "target": target,
        "target_name": np.array([TARGET_CLASS_NAMES[int(v)] for v in target], dtype=object),
        "first_hit": first_hit,
        "hit_bar_offset": hit_offset,
        "same_bar_both_hit": same_bar,
        "terminal_return": terminal_return,
        "terminal_z": terminal_z,
        "mfe_pct": mfe_pct,
        "mae_pct": mae_pct,
        "remaining_bars": remaining_bars,
        "label_reason": label_reason,
    }


def _finite_positive(value: float) -> bool:
    return bool(np.isfinite(value) and value > 0.0)


def materialize_target_variants(
    *,
    project_root: Path,
    assets: tuple[str, ...],
    roots: tuple[str, ...],
    variants: tuple[str, ...],
    batch_id_min: int | None = None,
    batch_id_max: int | None = None,
    batch_limit: int | None = None,
    write_sanity_report: bool = False,
) -> list[TargetVariantSummary]:
    summaries: list[TargetVariantSummary] = []
    for asset_id in assets:
        asset_id = normalize_htf_asset_id(asset_id)
        for root_key in roots:
            summaries.extend(
                _materialize_asset_root_variants(
                    project_root=project_root,
                    asset_id=asset_id,
                    root_key=root_key,
                    variants=variants,
                    batch_id_min=batch_id_min,
                    batch_id_max=batch_id_max,
                    batch_limit=batch_limit,
                )
            )
    if write_sanity_report:
        _write_sanity_report(project_root=project_root, summaries=summaries)
    return summaries


def _materialize_asset_root_variants(
    *,
    project_root: Path,
    asset_id: str,
    root_key: str,
    variants: tuple[str, ...],
    batch_id_min: int | None,
    batch_id_max: int | None,
    batch_limit: int | None,
) -> list[TargetVariantSummary]:
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
    summaries: list[TargetVariantSummary] = []
    for variant in variants:
        variant = normalize_variant(variant)
        output_dir = asset_root / f"{layout.label_root}_{variant}" / "1m"
        output_dir.mkdir(parents=True, exist_ok=True)
        for stale in output_dir.glob("batch_*.parquet"):
            stale.unlink()

        labeled = compute_triple_barrier_targets(rows, window, variant=variant)
        target_col = target_col_for_variant(variant)
        name_col = f"{target_col}_name"
        output_cols = _ordered_output_columns(labeled, target_col=target_col, name_col=name_col)
        for batch_id, batch in labeled.partition_by(
            "batch_id",
            as_dict=True,
            maintain_order=True,
        ).items():
            key = int(batch_id[0] if isinstance(batch_id, tuple) else batch_id)
            batch.select(output_cols).write_parquet(output_dir / f"batch_{key:04d}.parquet")

        summary = _summarize_variant(
            labeled,
            asset_id=asset_id,
            root_key=root_key,
            variant=variant,
            target_col=target_col,
            output_dir=output_dir,
        )
        summaries.append(summary)
        _write_variant_meta(
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
    return summaries


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


def _batch_id(path: Path) -> int:
    return int(path.stem.removeprefix("batch_"))


def _ordered_output_columns(
    df: pl.DataFrame,
    *,
    target_col: str,
    name_col: str,
) -> list[str]:
    preferred = [
        "timestamp",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "batch_id",
        target_col,
        name_col,
        "target_4class",
        "target_name",
        "target_breakfree",
        "label_window_policy",
        "label_entry_family",
        "label_window_family",
        "label_window_batch_id",
        "label_window_start",
        "label_window_end",
        "tb_first_hit",
        "tb_hit_bar_offset",
        "tb_same_bar_both_hit",
        "tb_upper_barrier",
        "tb_lower_barrier",
        "tb_upper_distance_pct",
        "tb_lower_distance_pct",
        "tb_volatility_pct",
        "tb_atr_pct_14",
        "tb_realized_vol_120",
        "tb_terminal_return",
        "tb_terminal_z",
        "tb_mfe_pct",
        "tb_mae_pct",
        "tb_remaining_bars",
        "tb_label_reason",
        "tb_barrier_mode",
        "tb_label_version",
    ]
    ordered = [col for col in preferred if col in df.columns]
    ordered.extend(col for col in df.columns if col not in set(ordered) and not col.startswith("_tb_"))
    return ordered


def _summarize_variant(
    df: pl.DataFrame,
    *,
    asset_id: str,
    root_key: str,
    variant: str,
    target_col: str,
    output_dir: Path,
) -> TargetVariantSummary:
    rows = len(df)
    eligible = df.filter(pl.col("is_label_half")) if "is_label_half" in df.columns else df
    eligible_rows = len(eligible)
    non_entry_rows = int(rows - eligible_rows)
    valid = eligible.filter(pl.col(target_col) >= 0)
    valid_rows = len(valid)
    invalid_ratio = 1.0 - (valid_rows / eligible_rows if eligible_rows else 0.0)
    all_valid_rows = int(df.filter(pl.col(target_col) >= 0).height)
    all_row_invalid_ratio = 1.0 - (all_valid_rows / rows if rows else 0.0)
    same_bar_ratio = (
        float(eligible["tb_same_bar_both_hit"].sum()) / eligible_rows
        if eligible_rows
        else 0.0
    )
    counts = (
        valid.group_by(target_col).len().sort(target_col)
        if valid_rows
        else pl.DataFrame({target_col: [], "len": []})
    )
    class_share = {class_id: 0.0 for class_id in range(4)}
    for row in counts.iter_rows(named=True):
        class_share[int(row[target_col])] = float(row["len"]) / float(valid_rows)

    reasons: list[str] = []
    if invalid_ratio > SANITY_INVALID_MAX:
        reasons.append(f"invalid_ratio>{SANITY_INVALID_MAX:.0%}")
    if same_bar_ratio > SANITY_SAME_BAR_MAX:
        reasons.append(f"same_bar_both_hit_ratio>{SANITY_SAME_BAR_MAX:.0%}")
    weak_classes = [
        class_id
        for class_id, share in class_share.items()
        if share < SANITY_MIN_CLASS_SHARE
    ]
    if weak_classes:
        reasons.append(f"class_share<{SANITY_MIN_CLASS_SHARE:.0%}:{weak_classes}")

    return TargetVariantSummary(
        asset_id=asset_id,
        root_key=root_key,
        variant=variant,
        target_col=target_col,
        output_dir=output_dir,
        rows=rows,
        eligible_rows=eligible_rows,
        non_entry_rows=non_entry_rows,
        valid_rows=valid_rows,
        invalid_ratio=invalid_ratio,
        all_row_invalid_ratio=all_row_invalid_ratio,
        same_bar_both_hit_ratio=same_bar_ratio,
        class_share=class_share,
        model_ready=not reasons,
        model_ready_reasons=tuple(reasons),
        diagnostics=_build_sanity_diagnostics(eligible, target_col=target_col),
    )


def _build_sanity_diagnostics(df: pl.DataFrame, *, target_col: str) -> dict[str, Any]:
    numeric_cols = [
        "tb_terminal_return",
        "tb_terminal_z",
        "tb_mfe_pct",
        "tb_mae_pct",
        "tb_hit_bar_offset",
        "tb_upper_distance_pct",
        "tb_lower_distance_pct",
    ]
    available = [col for col in numeric_cols if col in df.columns]
    clean = df.with_columns([pl.col(col).fill_nan(None) for col in available])
    valid = clean.filter(pl.col(target_col) >= 0)

    class_metrics: dict[str, dict[str, float | int | None]] = {}
    if not valid.is_empty():
        agg_exprs = [pl.len().alias("rows")]
        for col in [
            "tb_terminal_return",
            "tb_terminal_z",
            "tb_mfe_pct",
            "tb_mae_pct",
            "tb_hit_bar_offset",
        ]:
            if col in valid.columns:
                agg_exprs.extend(
                    [
                        pl.col(col).mean().alias(f"{col}_mean"),
                        pl.col(col).median().alias(f"{col}_median"),
                    ]
                )
        grouped = valid.group_by(target_col).agg(agg_exprs).sort(target_col)
        for row in grouped.iter_rows(named=True):
            class_id = int(row[target_col])
            class_metrics[str(class_id)] = {
                key: _json_number(value)
                for key, value in row.items()
                if key != target_col
            }

    barrier_quantiles: dict[str, dict[str, float | None]] = {}
    for col in ["tb_upper_distance_pct", "tb_lower_distance_pct"]:
        if col not in clean.columns:
            continue
        series = clean.get_column(col).drop_nulls()
        if series.is_empty():
            barrier_quantiles[col] = {"p05": None, "p50": None, "p95": None}
            continue
        barrier_quantiles[col] = {
            "p05": _json_number(series.quantile(0.05)),
            "p50": _json_number(series.quantile(0.50)),
            "p95": _json_number(series.quantile(0.95)),
        }

    hit_distribution = {}
    if "tb_first_hit" in clean.columns:
        hit_distribution = {
            str(row["tb_first_hit"]): int(row["len"])
            for row in clean.group_by("tb_first_hit").len().iter_rows(named=True)
        }

    return {
        "class_metrics": class_metrics,
        "barrier_quantiles": barrier_quantiles,
        "first_hit_distribution": hit_distribution,
    }


def _json_number(value: Any) -> float | int | None:
    if value is None:
        return None
    if isinstance(value, (int, np.integer)):
        return int(value)
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value):
        return None
    return value


def _write_variant_meta(
    *,
    output_dir: Path,
    summary: TargetVariantSummary,
    source_label_dir: Path,
    window_path: Path,
    entry_backtest_root: str,
    window_backtest_root: str,
    batch_id_min: int | None,
    batch_id_max: int | None,
    batch_limit: int | None,
) -> None:
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "asset_id": summary.asset_id,
        "root": summary.root_key,
        "variant": summary.variant,
        "target_col": summary.target_col,
        "source_label_dir": str(source_label_dir),
        "window_15m_path": str(window_path),
        "entry_backtest_root": entry_backtest_root,
        "window_backtest_root": window_backtest_root,
        "batch_id_min": batch_id_min,
        "batch_id_max": batch_id_max,
        "batch_limit": batch_limit,
        "rows": summary.rows,
        "eligible_rows": summary.eligible_rows,
        "non_entry_rows": summary.non_entry_rows,
        "valid_rows": summary.valid_rows,
        "eligible_invalid_ratio": summary.invalid_ratio,
        "all_row_invalid_ratio": summary.all_row_invalid_ratio,
        "same_bar_both_hit_ratio": summary.same_bar_both_hit_ratio,
        "class_share": summary.class_share,
        "model_ready": summary.model_ready,
        "model_ready_reasons": list(summary.model_ready_reasons),
        "diagnostics": summary.diagnostics,
        "parameters": {
            **variant_spec(summary.variant),
            "atr_period": TB_ATR_PERIOD,
            "realized_vol_period": TB_REALIZED_VOL_PERIOD,
            "min_volatility_pct": TB_MIN_VOLATILITY_PCT,
            "min_barrier_pct": TB_MIN_BARRIER_PCT,
            "max_barrier_pct": TB_MAX_BARRIER_PCT,
            "same_bar_policy": "ambiguous_to_invalid",
        },
    }
    (output_dir / "_target_variant_meta.json").write_text(json.dumps(payload, indent=2))


def _write_sanity_report(
    *,
    project_root: Path,
    summaries: list[TargetVariantSummary],
) -> Path:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    report_path = project_root / "docs" / "research" / f"tb-label-sanity-8h-b-btcusdt-{today}.md"
    lines = [
        "# Triple-Barrier Label Sanity Report",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        "Acceptance gates are evaluated on label-eligible entry-window rows only: "
        "eligible invalid ratio <= 35%, same-bar both-hit ratio <= 10%, "
        "and each valid class share >= 5%. Non-entry rows remain `-1` by design "
        "and are filtered out by Stage-1 before training.",
        "",
        "## Summary",
        "",
        "| Asset | Root | Variant | Rows | Eligible | Valid Eligible | Eligible Invalid % | All-Row Invalid % | Same-Bar Both-Hit % | Model Ready | Reasons |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---|---|",
    ]
    for summary in summaries:
        reasons = ", ".join(summary.model_ready_reasons) if summary.model_ready_reasons else "-"
        lines.append(
            f"| {summary.asset_id} | {summary.root_key} | {summary.variant} | "
            f"{summary.rows:,} | {summary.eligible_rows:,} | {summary.valid_rows:,} | "
            f"{summary.invalid_ratio:.2%} | {summary.all_row_invalid_ratio:.2%} | "
            f"{summary.same_bar_both_hit_ratio:.2%} | "
            f"{'yes' if summary.model_ready else 'no'} | {reasons} |"
        )
    lines.extend(["", "## Class Share", ""])
    for summary in summaries:
        lines.extend(
            [
                f"### {summary.asset_id} {summary.root_key} {summary.variant}",
                "",
                "| Class | Name | Share |",
                "|---:|---|---:|",
            ]
        )
        for class_id in range(4):
            lines.append(
                f"| {class_id} | {TARGET_CLASS_NAMES[class_id]} | "
                f"{summary.class_share.get(class_id, 0.0):.2%} |"
            )
        lines.append("")
    lines.extend(["", "## Class Diagnostics", ""])
    for summary in summaries:
        lines.extend(
            [
                f"### {summary.asset_id} {summary.root_key} {summary.variant}",
                "",
                "| Class | Rows | Mean Terminal Return | Median Terminal Z | Mean MFE | Mean MAE | Median Hit Offset |",
                "|---:|---:|---:|---:|---:|---:|---:|",
            ]
        )
        class_metrics = summary.diagnostics.get("class_metrics", {})
        for class_id in range(4):
            metrics = class_metrics.get(str(class_id), {})
            lines.append(
                f"| {class_id} | {int(metrics.get('rows') or 0):,} | "
                f"{_fmt_metric(metrics.get('tb_terminal_return_mean'))} | "
                f"{_fmt_metric(metrics.get('tb_terminal_z_median'))} | "
                f"{_fmt_metric(metrics.get('tb_mfe_pct_mean'))} | "
                f"{_fmt_metric(metrics.get('tb_mae_pct_mean'))} | "
                f"{_fmt_metric(metrics.get('tb_hit_bar_offset_median'))} |"
            )
        lines.extend(["", "Barrier distance quantiles:", ""])
        lines.append("| Metric | p05 | p50 | p95 |")
        lines.append("|---|---:|---:|---:|")
        for metric, quantiles in summary.diagnostics.get("barrier_quantiles", {}).items():
            lines.append(
                f"| {metric} | {_fmt_metric(quantiles.get('p05'))} | "
                f"{_fmt_metric(quantiles.get('p50'))} | "
                f"{_fmt_metric(quantiles.get('p95'))} |"
            )
        lines.extend(["", "First-hit distribution:", ""])
        hit_dist = summary.diagnostics.get("first_hit_distribution", {})
        lines.append(
            ", ".join(f"{key}={value:,}" for key, value in sorted(hit_dist.items()))
            or "-"
        )
        lines.append("")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines) + "\n")
    return report_path


def _fmt_metric(value: Any) -> str:
    if value is None:
        return "-"
    try:
        value = float(value)
    except (TypeError, ValueError):
        return "-"
    if not math.isfinite(value):
        return "-"
    return f"{value:.6f}"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Materialize experimental Stage-1 target label variants."
    )
    parser.add_argument("--assets", default="BTCUSDT", help="Asset selector or comma-separated ids.")
    parser.add_argument(
        "--roots",
        nargs="*",
        choices=sorted(STAGE1_MULTIASSET_ROOT_LAYOUTS),
        default=["8h/B"],
        help="Regime/family roots to materialize. Default: 8h/B.",
    )
    parser.add_argument(
        "--variants",
        default="tb_atr_v1",
        help="Comma-separated variants or 'all'.",
    )
    parser.add_argument("--batch-min", type=int, default=None)
    parser.add_argument("--batch-max", type=int, default=None)
    parser.add_argument("--batch-limit", type=int, default=None)
    parser.add_argument("--write-sanity-report", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    summaries = materialize_target_variants(
        project_root=PROJECT_ROOT,
        assets=parse_stage1_target_assets(args.assets),
        roots=parse_roots(args.roots),
        variants=parse_variants(args.variants),
        batch_id_min=args.batch_min,
        batch_id_max=args.batch_max,
        batch_limit=args.batch_limit,
        write_sanity_report=bool(args.write_sanity_report),
    )
    for summary in summaries:
        print(
            f"{summary.asset_id} {summary.root_key} {summary.variant}: "
            f"rows={summary.rows:,} eligible={summary.eligible_rows:,} "
            f"valid_eligible={summary.valid_rows:,} "
            f"eligible_invalid={summary.invalid_ratio:.2%} "
            f"same_bar={summary.same_bar_both_hit_ratio:.2%} "
            f"ready={summary.model_ready} output={summary.output_dir}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
