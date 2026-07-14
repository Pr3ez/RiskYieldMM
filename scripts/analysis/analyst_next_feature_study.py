"""Fixed, causal diagnostics for the Analyst's next context features.

This module is a research harness, not a strategy optimizer.  It computes a
small predeclared feature set from completed canonical OHLCV bars and measures
descriptive chronological associations with returns that start at the next
bar's open.  No feature is selected, tuned, or promoted by this script.

The feature families are deliberately narrow:

* prior 48-bar channel location, breakout distance, and available room;
* close-to-close EWMA state and Parkinson/Rogers-Satchell range estimates;
* volume relative to a prior-only session/UTC-phase baseline.

Every feature at row ``t`` uses rows ``<= t``.  Rolling reference levels and
normalization baselines exclude row ``t`` where the meaning is explicitly
"prior".  Evaluation labels begin at ``open[t + 1]`` and are never exported as
live inputs.
"""

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
import pandas as pd
import polars as pl
from scipy import stats

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ANALYST_ROOT = PROJECT_ROOT / "Risk_Yield_Meta_Model_Analyst_0_0_1"
if str(ANALYST_ROOT) not in sys.path:
    sys.path.insert(0, str(ANALYST_ROOT))

from chart_config import (  # noqa: E402
    BYBIT_ASSETS,
    CANONICAL_SOURCE,
    CANONICAL_TIMEFRAMES,
    CORE_ASSETS,
    resolve_ohlcv_files,
    timeframe_seconds,
)

STUDY_VERSION = "analyst_next_feature_study_v1"
CHANNEL_LOOKBACK = 48
VOLATILITY_REFERENCE_LOOKBACK = 192
VOLUME_REFERENCE_OCCURRENCES = 20
TREND_HORIZONS = (12, 48, 192)
EVALUATION_HORIZONS = (1, 3, 12)
DEFAULT_MAX_BARS = 50_000
DEFAULT_FOLDS = 4
MIN_FOLD_ROWS = 100

DIRECTION_FEATURES = (
    "trend_score",
    "channel_position_signed",
    "breakout_balance_vol",
    "room_balance",
)
MAGNITUDE_FEATURES = (
    "volatility_level_log",
    "parkinson_to_close_vol",
    "rogers_satchell_to_close_vol",
    "relative_volume_phase_log",
    "relative_volume_unconditioned_log",
)
CANDIDATE_COLUMNS = DIRECTION_FEATURES + MAGNITUDE_FEATURES


@dataclass(frozen=True)
class Selection:
    """One canonical asset/timeframe research unit."""

    asset: str
    timeframe: str


def _positive_log_ratio(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    valid = (numerator > 0.0) & (denominator > 0.0)
    out = pd.Series(np.nan, index=numerator.index, dtype=float)
    out.loc[valid] = np.log(numerator.loc[valid] / denominator.loc[valid])
    return out


def _ewma_variance(values: pd.Series, *, half_life: int) -> pd.Series:
    decay = math.exp(-math.log(2.0) / float(half_life))
    return values.pow(2).ewm(alpha=1.0 - decay, adjust=False).mean()


def _trend_features(log_return: pd.Series) -> tuple[pd.Series, pd.Series]:
    components: list[pd.Series] = []
    qualities: list[pd.Series] = []
    squared = log_return.pow(2)
    for horizon in TREND_HORIZONS:
        decay = math.exp(-math.log(2.0) / float(horizon))
        prior_sigma = (
            squared.ewm(alpha=1.0 - decay, adjust=False)
            .mean()
            .shift(1)
            .clip(lower=0.0)
            .pow(0.5)
        )
        net = log_return.rolling(horizon, min_periods=horizon).sum()
        path = log_return.abs().rolling(horizon, min_periods=horizon).sum()
        z_value = (net / (prior_sigma * math.sqrt(float(horizon)))).clip(-8.0, 8.0)
        quality = (net.abs() / path.replace(0.0, np.nan)).clip(0.0, 1.0)
        components.append(quality * np.tanh(z_value / 2.0))
        qualities.append(quality)
    component_frame = pd.concat(components, axis=1)
    quality_frame = pd.concat(qualities, axis=1)
    complete = component_frame.notna().all(axis=1)
    trend_score = component_frame.mean(axis=1).where(complete)
    path_quality = quality_frame.mean(axis=1).where(complete)
    return trend_score, path_quality


def _volume_phase(
    frame: pd.DataFrame,
    *,
    asset: str,
    timeframe: str,
) -> pd.Series:
    if asset in BYBIT_ASSETS:
        timestamps = pd.to_datetime(frame["timestamp"], utc=True)
        seconds_in_day = (
            timestamps.dt.hour.astype(np.int64) * 3_600
            + timestamps.dt.minute.astype(np.int64) * 60
            + timestamps.dt.second.astype(np.int64)
        )
        # The first fixed study normalizes the 24-hour activity curve.  A
        # weekday/weekend split would multiply the history requirement by
        # seven and belongs in a later, explicitly ablated calendar feature.
        return (seconds_in_day // timeframe_seconds(timeframe)).astype("int64")

    if "session_bar_pos" in frame.columns:
        phase = pd.to_numeric(frame["session_bar_pos"], errors="coerce")
        if phase.notna().any():
            return phase.fillna(-1).astype("int64")

    timestamps = pd.to_datetime(frame["timestamp"], utc=True)
    seconds_in_day = (
        timestamps.dt.hour.astype(np.int64) * 3_600
        + timestamps.dt.minute.astype(np.int64) * 60
        + timestamps.dt.second.astype(np.int64)
    )
    return (seconds_in_day // timeframe_seconds(timeframe)).astype("int64")


def _prior_group_median(
    values: pd.Series,
    phase: pd.Series,
    *,
    occurrences: int = VOLUME_REFERENCE_OCCURRENCES,
) -> pd.Series:
    minimum = max(5, occurrences // 2)
    grouped = values.groupby(phase, sort=False, dropna=False)
    return grouped.transform(
        lambda group: group.shift(1).rolling(occurrences, min_periods=minimum).median()
    )


def build_candidate_frame(
    frame: pl.DataFrame | pd.DataFrame,
    *,
    asset: str,
    timeframe: str,
) -> pd.DataFrame:
    """Return fixed causal features plus research-only forward outcomes."""

    if isinstance(frame, pl.DataFrame):
        source = frame.to_pandas()
    else:
        source = frame.copy()
    required = {"timestamp", "open", "high", "low", "close", "volume"}
    missing = required - set(source.columns)
    if missing:
        raise ValueError(f"Canonical frame missing columns: {sorted(missing)}")

    source["timestamp"] = pd.to_datetime(source["timestamp"], utc=True)
    source = (
        source.drop_duplicates(subset=["timestamp"], keep="last")
        .sort_values("timestamp")
        .reset_index(drop=True)
    )
    for column in ("open", "high", "low", "close", "volume"):
        source[column] = pd.to_numeric(source[column], errors="coerce")

    valid_ohlc = (
        (source[["open", "high", "low", "close"]] > 0.0).all(axis=1)
        & (source["high"] >= source[["open", "close"]].max(axis=1))
        & (source["low"] <= source[["open", "close"]].min(axis=1))
        & (source["high"] >= source["low"])
    )
    source.loc[~valid_ohlc, ["open", "high", "low", "close"]] = np.nan

    log_return = _positive_log_ratio(source["close"], source["close"].shift(1))
    trend_score, path_quality = _trend_features(log_return)
    slow_variance = _ewma_variance(log_return, half_life=TREND_HORIZONS[-1])
    prior_slow_sigma = slow_variance.shift(1).clip(lower=0.0).pow(0.5)
    fast_close_variance = _ewma_variance(log_return, half_life=TREND_HORIZONS[1])

    prior_high = (
        source["high"]
        .shift(1)
        .rolling(CHANNEL_LOOKBACK, min_periods=CHANNEL_LOOKBACK)
        .max()
    )
    prior_low = (
        source["low"]
        .shift(1)
        .rolling(CHANNEL_LOOKBACK, min_periods=CHANNEL_LOOKBACK)
        .min()
    )
    channel_width = prior_high - prior_low
    channel_position = (
        (source["close"] - prior_low) / channel_width.replace(0.0, np.nan)
    ).clip(0.0, 1.0)

    upward_break = _positive_log_ratio(source["close"], prior_high).clip(lower=0.0)
    downward_break = _positive_log_ratio(prior_low, source["close"]).clip(lower=0.0)
    upward_room = _positive_log_ratio(prior_high, source["close"]).clip(lower=0.0)
    downward_room = _positive_log_ratio(source["close"], prior_low).clip(lower=0.0)
    volatility_scale = prior_slow_sigma.replace(0.0, np.nan)
    breakout_balance = ((upward_break - downward_break) / volatility_scale).clip(
        -8.0, 8.0
    )
    room_total = upward_room + downward_room
    room_balance = (
        (upward_room - downward_room) / room_total.replace(0.0, np.nan)
    ).clip(-1.0, 1.0)

    prior_volatility_median = (
        prior_slow_sigma.shift(1)
        .rolling(
            VOLATILITY_REFERENCE_LOOKBACK,
            min_periods=VOLATILITY_REFERENCE_LOOKBACK // 2,
        )
        .median()
    )
    volatility_level = _positive_log_ratio(
        prior_slow_sigma, prior_volatility_median
    ).clip(-8.0, 8.0)

    log_high_low = _positive_log_ratio(source["high"], source["low"])
    parkinson_variance = log_high_low.pow(2) / (4.0 * math.log(2.0))
    log_high_open = _positive_log_ratio(source["high"], source["open"])
    log_high_close = _positive_log_ratio(source["high"], source["close"])
    log_low_open = _positive_log_ratio(source["low"], source["open"])
    log_low_close = _positive_log_ratio(source["low"], source["close"])
    rogers_satchell_variance = (
        log_high_open * log_high_close + log_low_open * log_low_close
    )
    # A materially negative RS value indicates invalid OHLC ordering or a
    # numerical problem.  It is missing evidence, not a variance to abs().
    rogers_satchell_variance = rogers_satchell_variance.where(
        rogers_satchell_variance >= -1e-15
    ).clip(lower=0.0)
    decay = math.exp(-math.log(2.0) / float(TREND_HORIZONS[1]))
    alpha = 1.0 - decay
    close_sigma_fast = fast_close_variance.clip(lower=0.0).pow(0.5).replace(0.0, np.nan)
    parkinson_sigma = (
        parkinson_variance.ewm(alpha=alpha, adjust=False)
        .mean()
        .clip(lower=0.0)
        .pow(0.5)
    )
    rogers_satchell_sigma = (
        rogers_satchell_variance.ewm(alpha=alpha, adjust=False)
        .mean()
        .clip(lower=0.0)
        .pow(0.5)
    )

    phase = _volume_phase(source, asset=asset, timeframe=timeframe)
    volume = source["volume"].clip(lower=0.0)
    phase_median = _prior_group_median(volume, phase)
    ordinary_median = (
        volume.shift(1)
        .rolling(
            CHANNEL_LOOKBACK,
            min_periods=CHANNEL_LOOKBACK // 2,
        )
        .median()
    )
    relative_volume_phase = _positive_log_ratio(volume, phase_median).clip(-8.0, 8.0)
    relative_volume_ordinary = _positive_log_ratio(volume, ordinary_median).clip(
        -8.0, 8.0
    )

    result = pd.DataFrame(
        {
            "timestamp": source["timestamp"],
            "trend_score": trend_score,
            "path_quality": path_quality,
            "channel_position_signed": (2.0 * channel_position - 1.0).clip(-1.0, 1.0),
            "breakout_balance_vol": breakout_balance,
            "room_balance": room_balance,
            "volatility_level_log": volatility_level,
            "parkinson_to_close_vol": (parkinson_sigma / close_sigma_fast).clip(
                0.0, 20.0
            ),
            "rogers_satchell_to_close_vol": (
                rogers_satchell_sigma / close_sigma_fast
            ).clip(0.0, 20.0),
            "relative_volume_phase_log": relative_volume_phase,
            "relative_volume_unconditioned_log": relative_volume_ordinary,
            "prior_slow_sigma": prior_slow_sigma,
            "volume_phase": phase,
        }
    )
    entry_open = source["open"].shift(-1)
    for horizon in EVALUATION_HORIZONS:
        raw_return = _positive_log_ratio(source["close"].shift(-horizon), entry_open)
        normalized = raw_return / (
            prior_slow_sigma.replace(0.0, np.nan) * math.sqrt(float(horizon))
        )
        result[f"forward_return_{horizon}_vol"] = normalized.clip(-20.0, 20.0)
        result[f"forward_abs_return_{horizon}_vol"] = normalized.abs().clip(0.0, 20.0)

    if "session_id" in source.columns:
        result["session_id"] = source["session_id"]
    if "is_synthetic_no_trade" in source.columns:
        result["is_synthetic_no_trade"] = source["is_synthetic_no_trade"]
    result["volume"] = volume
    return result


def _finite_arrays(*series: pd.Series) -> tuple[np.ndarray, ...]:
    arrays = [item.to_numpy(dtype=float, copy=False) for item in series]
    mask = np.logical_and.reduce([np.isfinite(item) for item in arrays])
    return tuple(item[mask] for item in arrays)


def _spearman(x: np.ndarray, y: np.ndarray) -> float | None:
    if len(x) < MIN_FOLD_ROWS or np.nanstd(x) <= 0.0 or np.nanstd(y) <= 0.0:
        return None
    value = stats.spearmanr(x, y, nan_policy="omit").statistic
    return float(value) if np.isfinite(value) else None


def _partial_spearman(
    x: np.ndarray, y: np.ndarray, baseline: np.ndarray
) -> float | None:
    if len(x) < MIN_FOLD_ROWS:
        return None
    ranked = [stats.rankdata(values, method="average") for values in (x, y, baseline)]
    x_rank, y_rank, baseline_rank = ranked
    design = np.column_stack([np.ones(len(baseline_rank)), baseline_rank])
    x_residual = x_rank - design @ np.linalg.lstsq(design, x_rank, rcond=None)[0]
    y_residual = y_rank - design @ np.linalg.lstsq(design, y_rank, rcond=None)[0]
    return _spearman(x_residual, y_residual)


def _fold_metric(
    feature: pd.Series,
    target: pd.Series,
    *,
    folds: int,
    baseline: pd.Series | None = None,
) -> dict[str, Any]:
    if baseline is None:
        x, y = _finite_arrays(feature, target)
        z = None
    else:
        x, y, z = _finite_arrays(feature, target, baseline)
    if len(x) < folds * MIN_FOLD_ROWS:
        return {
            "rows": int(len(x)),
            "fold_rho": [],
            "median_rho": None,
            "same_sign_fold_fraction": None,
            "fold_partial_rho": [],
            "median_partial_rho": None,
        }

    fold_rhos: list[float] = []
    fold_partial: list[float] = []
    for indices in np.array_split(np.arange(len(x)), folds):
        rho = _spearman(x[indices], y[indices])
        if rho is not None:
            fold_rhos.append(rho)
        if z is not None:
            partial = _partial_spearman(x[indices], y[indices], z[indices])
            if partial is not None:
                fold_partial.append(partial)

    median_rho = float(np.median(fold_rhos)) if fold_rhos else None
    if median_rho is None or median_rho == 0.0:
        sign_fraction = None
    else:
        expected_sign = math.copysign(1.0, median_rho)
        sign_fraction = float(
            np.mean([math.copysign(1.0, value) == expected_sign for value in fold_rhos])
        )
    return {
        "rows": int(len(x)),
        "fold_rho": fold_rhos,
        "median_rho": median_rho,
        "same_sign_fold_fraction": sign_fraction,
        "fold_partial_rho": fold_partial,
        "median_partial_rho": (
            float(np.median(fold_partial)) if fold_partial else None
        ),
    }


def _selection_metrics(
    features: pd.DataFrame,
    *,
    selection: Selection,
    folds: int,
) -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    for horizon in EVALUATION_HORIZONS:
        direction_target = features[f"forward_return_{horizon}_vol"]
        magnitude_target = features[f"forward_abs_return_{horizon}_vol"]
        for feature in DIRECTION_FEATURES:
            metrics[f"{feature}__return_h{horizon}"] = _fold_metric(
                features[feature],
                direction_target,
                folds=folds,
                baseline=(
                    None if feature == "trend_score" else features["trend_score"]
                ),
            )
        for feature in MAGNITUDE_FEATURES:
            metrics[f"{feature}__abs_return_h{horizon}"] = _fold_metric(
                features[feature],
                magnitude_target,
                folds=folds,
                baseline=(
                    None
                    if feature == "volatility_level_log"
                    else features["volatility_level_log"]
                ),
            )

    overlaps = {}
    for left, right in (
        ("channel_position_signed", "trend_score"),
        ("breakout_balance_vol", "trend_score"),
        ("parkinson_to_close_vol", "rogers_satchell_to_close_vol"),
        ("relative_volume_phase_log", "relative_volume_unconditioned_log"),
    ):
        x, y = _finite_arrays(features[left], features[right])
        overlaps[f"{left}__{right}"] = _spearman(x, y)

    session_count = (
        int(features["session_id"].nunique(dropna=True))
        if "session_id" in features.columns
        else None
    )
    synthetic_share = (
        float(
            pd.to_numeric(features["is_synthetic_no_trade"], errors="coerce")
            .fillna(0)
            .mean()
        )
        if "is_synthetic_no_trade" in features.columns
        else None
    )
    return {
        "asset": selection.asset,
        "timeframe": selection.timeframe,
        "rows": int(len(features)),
        "start": features["timestamp"].min().isoformat(),
        "end": features["timestamp"].max().isoformat(),
        "zero_volume_rate": float((features["volume"].fillna(0.0) <= 0.0).mean()),
        "phase_volume_coverage": float(
            features["relative_volume_phase_log"].notna().mean()
        ),
        "rogers_satchell_coverage": float(
            features["rogers_satchell_to_close_vol"].notna().mean()
        ),
        "session_count": session_count,
        "prior_session_levels_supported": bool(
            selection.asset not in BYBIT_ASSETS
            and session_count is not None
            and session_count > 1
        ),
        "synthetic_no_trade_share": synthetic_share,
        "overlap_spearman": overlaps,
        "metrics": metrics,
    }


def _finite_summary(values: list[float | None]) -> dict[str, Any]:
    finite = np.asarray(
        [float(value) for value in values if value is not None and np.isfinite(value)],
        dtype=float,
    )
    if finite.size == 0:
        return {
            "count": 0,
            "min": None,
            "q25": None,
            "median": None,
            "q75": None,
            "max": None,
        }
    return {
        "count": int(finite.size),
        "min": float(np.min(finite)),
        "q25": float(np.quantile(finite, 0.25)),
        "median": float(np.median(finite)),
        "q75": float(np.quantile(finite, 0.75)),
        "max": float(np.max(finite)),
    }


def _aggregate(selections: list[dict[str, Any]]) -> dict[str, Any]:
    metric_keys = sorted(
        {key for selection in selections for key in selection.get("metrics", {})}
    )
    metrics: dict[str, Any] = {}
    for key in metric_keys:
        rows = [
            selection["metrics"][key]
            for selection in selections
            if key in selection["metrics"]
        ]
        metrics[key] = {
            "median_rho": _finite_summary([row.get("median_rho") for row in rows]),
            "median_partial_rho": _finite_summary(
                [row.get("median_partial_rho") for row in rows]
            ),
            "same_sign_fold_fraction": _finite_summary(
                [row.get("same_sign_fold_fraction") for row in rows]
            ),
            "rows": _finite_summary([float(row.get("rows", 0)) for row in rows]),
        }

    overlap_keys = sorted(
        {
            key
            for selection in selections
            for key in selection.get("overlap_spearman", {})
        }
    )
    overlaps = {
        key: _finite_summary(
            [selection["overlap_spearman"].get(key) for selection in selections]
        )
        for key in overlap_keys
    }
    return {
        "selection_count": len(selections),
        "rows": int(sum(selection["rows"] for selection in selections)),
        "zero_volume_rate_by_selection": _finite_summary(
            [selection["zero_volume_rate"] for selection in selections]
        ),
        "phase_volume_coverage_by_selection": _finite_summary(
            [selection["phase_volume_coverage"] for selection in selections]
        ),
        "rogers_satchell_coverage_by_selection": _finite_summary(
            [selection["rogers_satchell_coverage"] for selection in selections]
        ),
        "prior_session_supported_count": int(
            sum(selection["prior_session_levels_supported"] for selection in selections)
        ),
        "overlap_spearman": overlaps,
        "metrics": metrics,
    }


def _load_selection(selection: Selection, *, max_bars: int) -> pl.DataFrame:
    resolution = resolve_ohlcv_files(
        selection.asset,
        selection.timeframe,
        CANONICAL_SOURCE,
    )
    columns = [
        "timestamp",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "session_id",
        "session_bar_pos",
        "is_synthetic_no_trade",
    ]
    schema = pl.scan_parquet(resolution.files[0]).collect_schema()
    available = [column for column in columns if column in schema]
    return pl.read_parquet(resolution.files[0], columns=available).tail(max_bars)


def run_study(
    *, max_bars: int = DEFAULT_MAX_BARS, folds: int = DEFAULT_FOLDS
) -> dict[str, Any]:
    """Run the fixed 8-asset x 7-timeframe study."""

    if max_bars < 1_000:
        raise ValueError("max_bars must be at least 1000")
    if folds < 2:
        raise ValueError("folds must be at least 2")
    selection_results: list[dict[str, Any]] = []
    for asset in CORE_ASSETS:
        for timeframe in CANONICAL_TIMEFRAMES:
            selection = Selection(asset=asset, timeframe=timeframe)
            frame = _load_selection(selection, max_bars=max_bars)
            features = build_candidate_frame(
                frame,
                asset=selection.asset,
                timeframe=selection.timeframe,
            )
            selection_results.append(
                _selection_metrics(features, selection=selection, folds=folds)
            )
            print(
                f"{selection.asset:8s} {selection.timeframe:3s} "
                f"rows={len(features):6d}",
                flush=True,
            )

    return {
        "study_version": STUDY_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": {
            "assets": list(CORE_ASSETS),
            "timeframes": list(CANONICAL_TIMEFRAMES),
            "max_bars_per_selection": max_bars,
            "chronological_folds": folds,
            "channel_lookback_bars": CHANNEL_LOOKBACK,
            "volatility_reference_lookback_bars": VOLATILITY_REFERENCE_LOOKBACK,
            "volume_reference_occurrences": VOLUME_REFERENCE_OCCURRENCES,
            "evaluation_horizons_bars": list(EVALUATION_HORIZONS),
            "execution_timing": "feature_at_closed_t_then_entry_at_open_t_plus_1",
        },
        "interpretation_guardrails": [
            "descriptive_fixed-feature_screen_not_strategy_optimization",
            "no_transaction_costs_or_fill_model",
            "no_profitability_or_production_promotion_claim",
            "selection_level_aggregation_not_pooled_row_significance",
            "autocorrelation_aware_inference_requires_later_locked_walkforward",
        ],
        "aggregate": _aggregate(selection_results),
        "selections": selection_results,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-bars", type=int, default=DEFAULT_MAX_BARS)
    parser.add_argument("--folds", type=int, default=DEFAULT_FOLDS)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    result = run_study(max_bars=args.max_bars, folds=args.folds)
    payload = json.dumps(result, indent=2, sort_keys=True)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
        print(
            json.dumps(
                {
                    "output": str(args.output),
                    "study_version": result["study_version"],
                    "selection_count": result["aggregate"]["selection_count"],
                    "rows": result["aggregate"]["rows"],
                },
                indent=2,
            )
        )
    else:
        print(payload)


if __name__ == "__main__":
    main()
