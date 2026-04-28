"""
Optimize Rolling Distance Feature Windows (HTF)
==============================================

Find the best rolling window length (per timeframe) for distance-based features
that are analogous to the forward-looking target distance metrics, but computed
causally on *past* bars only.

Outputs per timeframe:
- distance_window_ic_{tf}.parquet: IC scores per window/feature
- distance_window_best_{tf}.json: best window per feature (macro_abs_ic)

Usage:
    from scripts.feature_engineering.optimize_distance_windows import (
        DistanceWindowConfig, optimize_distance_windows
    )

    config = DistanceWindowConfig(
        timeframes=["5m", "15m"],
        target="target_8class",
        windows_by_tf={"5m": [24, 48, 96, 192], "15m": [8, 16, 32, 64]},
    )
    results = optimize_distance_windows(config)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import polars as pl
from numba import njit
from scipy.stats import spearmanr


@dataclass
class DistanceWindowConfig:
    project_root: Path = field(
        default_factory=lambda: Path(__file__).parent.parent.parent
    )
    timeframes: list[str] = field(default_factory=lambda: ["5m", "15m"])
    target: str = "target_8class"
    n_classes: int = 8
    outlier_percentile: float = 0.05
    windows_by_tf: dict[str, list[int]] = field(
        default_factory=lambda: {"5m": [24, 48, 96, 192], "15m": [8, 16, 32, 64]}
    )
    reset_on_batch: bool = True
    save_results: bool = True

    @property
    def htf_backtest_dir(self) -> Path:
        return self.project_root / "data" / "htf_backtest"

    @property
    def htf_labels_dir(self) -> Path:
        return self.project_root / "data" / "htf_8class_labels"

    @property
    def output_dir(self) -> Path:
        return self.project_root / "data" / "htf_distance_window_analysis"


@njit
def compute_past_distance_metrics(
    close: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    bar_pos: np.ndarray,
    window: int,
    outlier_pct: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Compute distance metrics using *past* window only (causal)."""
    n = len(close)
    dist_avg_high = np.full(n, np.nan, dtype=np.float64)
    dist_avg_low = np.full(n, np.nan, dtype=np.float64)
    dist_top5_high = np.full(n, np.nan, dtype=np.float64)
    dist_bot5_low = np.full(n, np.nan, dtype=np.float64)

    top_n = max(1, int(window * outlier_pct))

    for i in range(n):
        # Match production HTF feature semantics: distance windows should use
        # continuous causal history, not reset at every batch boundary.
        if i < window:
            continue

        start = i - window
        entry = close[i]
        if entry == 0:
            continue

        highs = high[start:i]
        lows = low[start:i]

        avg_high = np.mean(highs)
        avg_low = np.mean(lows)

        sorted_highs = np.sort(highs)
        sorted_lows = np.sort(lows)

        avg_top_high = np.mean(sorted_highs[-top_n:])
        avg_bot_low = np.mean(sorted_lows[:top_n])

        dist_avg_high[i] = 100.0 * (avg_high - entry) / entry
        dist_avg_low[i] = 100.0 * (entry - avg_low) / entry
        dist_top5_high[i] = 100.0 * (avg_top_high - entry) / entry
        dist_bot5_low[i] = 100.0 * (entry - avg_bot_low) / entry

    return dist_avg_high, dist_avg_low, dist_top5_high, dist_bot5_low


def _load_labels_combined(labels_dir: Path, tf: str) -> pl.DataFrame:
    """Load labels for a timeframe; prefer combined file if present."""
    combined = labels_dir / f"{tf}_8class_labels.parquet"
    if combined.exists():
        return pl.read_parquet(combined)

    # Fallback: concat batch files
    batch_files = sorted((labels_dir / tf).glob("batch_*.parquet"))
    if not batch_files:
        raise FileNotFoundError(f"No label files found in {labels_dir / tf}")
    return pl.concat([pl.read_parquet(f) for f in batch_files])


def _prepare_merged_data(config: DistanceWindowConfig, tf: str) -> pl.DataFrame:
    """Load OHLCV + target, align, and sort by batch/timestamp."""
    ohlcv_path = config.htf_backtest_dir / f"{tf}_HTF_combined.parquet"
    if not ohlcv_path.exists():
        raise FileNotFoundError(f"Missing OHLCV: {ohlcv_path}")

    df_ohlcv = pl.read_parquet(ohlcv_path)
    df_labels = _load_labels_combined(config.htf_labels_dir, tf)

    # Keep only needed columns
    df_labels = df_labels.select(["timestamp", "batch_id", config.target])

    df = df_ohlcv.join(df_labels, on=["timestamp", "batch_id"], how="inner")
    df = df.sort(["batch_id", "timestamp"])

    # Filter invalid labels
    df = df.filter(pl.col(config.target) >= 0)

    if config.reset_on_batch:
        df = df.with_columns(
            (pl.cum_count("timestamp").over("batch_id") - 1).alias("bar_pos")
        )
    else:
        df = df.with_columns(pl.arange(0, df.height).alias("bar_pos"))

    return df


def _spearman_ic(feature: np.ndarray, y: np.ndarray, n_classes: int) -> dict:
    """Compute per-class Spearman IC + aggregates for multiclass."""
    mask = ~np.isnan(feature)
    x = feature[mask]
    y = y[mask]

    if len(x) < 10:
        return {"macro_ic": 0.0, "macro_abs_ic": 0.0, "per_class": [0.0] * n_classes}

    per_class = []
    for c in range(n_classes):
        y_bin = (y == c).astype(np.int8)
        if y_bin.sum() == 0 or y_bin.sum() == len(y_bin):
            per_class.append(0.0)
            continue
        ic = spearmanr(x, y_bin, nan_policy="omit").correlation
        if ic is None or np.isnan(ic):
            ic = 0.0
        per_class.append(float(ic))

    macro_ic = float(np.mean(per_class))
    macro_abs_ic = float(np.mean([abs(v) for v in per_class]))

    return {
        "macro_ic": macro_ic,
        "macro_abs_ic": macro_abs_ic,
        "per_class": per_class,
    }


def optimize_distance_windows(config: DistanceWindowConfig) -> dict[str, pl.DataFrame]:
    """Run IC analysis for all timeframes and windows."""
    results: dict[str, pl.DataFrame] = {}
    config.output_dir.mkdir(parents=True, exist_ok=True)

    for tf in config.timeframes:
        print(f"\n{'=' * 60}")
        print(f"Distance window optimization: {tf}")
        print(f"{'=' * 60}")

        df = _prepare_merged_data(config, tf)
        y = df[config.target].to_numpy().astype(int)
        close = df["close"].to_numpy()
        high = df["high"].to_numpy()
        low = df["low"].to_numpy()
        bar_pos = df["bar_pos"].to_numpy().astype(np.int32)

        # Use configured n_classes to keep class set stable even if some are missing
        n_classes = config.n_classes

        rows = []
        windows = config.windows_by_tf.get(tf, [])
        if not windows:
            print(f"  No windows configured for {tf}, skipping")
            continue

        for window in windows:
            print(f"  Evaluating window={window}")
            d_avg_high, d_avg_low, d_top5_high, d_bot5_low = compute_past_distance_metrics(
                close, high, low, bar_pos, window, config.outlier_percentile
            )

            for name, vec in [
                ("dist_avg_high", d_avg_high),
                ("dist_avg_low", d_avg_low),
                ("dist_top5_high", d_top5_high),
                ("dist_bot5_low", d_bot5_low),
            ]:
                stats = _spearman_ic(vec, y, n_classes)
                rows.append(
                    {
                        "timeframe": tf,
                        "window": window,
                        "feature": name,
                        "macro_ic": stats["macro_ic"],
                        "macro_abs_ic": stats["macro_abs_ic"],
                        "per_class_ic": stats["per_class"],
                        "n_samples": int(np.sum(~np.isnan(vec))),
                    }
                )

        result_df = pl.DataFrame(rows)
        results[tf] = result_df

        if config.save_results:
            out_file = config.output_dir / f"distance_window_ic_{tf}.parquet"
            result_df.write_parquet(out_file, compression="zstd")

            # Best window per feature
            best = (
                result_df.sort("macro_abs_ic", descending=True)
                .group_by("feature")
                .first()
            )
            best_map = {
                row["feature"]: {
                    "window": int(row["window"]),
                    "macro_abs_ic": float(row["macro_abs_ic"]),
                }
                for row in best.to_dicts()
            }

            summary = {
                "timeframe": tf,
                "target": config.target,
                "outlier_percentile": config.outlier_percentile,
                "windows": windows,
                "best_windows": best_map,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            with open(
                config.output_dir / f"distance_window_best_{tf}.json", "w"
            ) as f:
                json.dump(summary, f, indent=2)

    return results


if __name__ == "__main__":
    cfg = DistanceWindowConfig()
    optimize_distance_windows(cfg)
