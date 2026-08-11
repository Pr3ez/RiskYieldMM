"""Causal Market Context v1 diagnostics for finalized OHLCV bars.

The three families in this module are deliberately descriptive rather than
trade instructions:

* prior structure uses strictly shifted 4/16/48-observation channels;
* comparable volatility uses Rogers--Satchell range variance and causal EWMs;
* participation compares volume with prior occurrences of the same market
  phase.

Input rows must represent finalized bars.  Channel levels use only earlier
rows and are therefore stamped at the source bar open.  Any classification or
measurement that uses the source bar's OHLCV is stamped at the next actionable
observed bar (or at the nominal bar close when no later observation is present).
Synthetic/no-trade rows, known open-session gap fills, and explicitly partial
rows are reported as data-quality states instead of silently being interpreted
as ordinary inactivity.
"""

from __future__ import annotations

import math
import statistics
from bisect import bisect_left, bisect_right, insort
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from typing import Any

import polars as pl

MARKET_CONTEXT_VERSION = "market_context_v1"

PRIOR_STRUCTURE_ID = "prior_structure"
COMPARABLE_VOLATILITY_ID = "comparable_volatility"
PHASE_ADJUSTED_PARTICIPATION_ID = "phase_adjusted_participation"
MARKET_CONTEXT_IDS = (
    PRIOR_STRUCTURE_ID,
    COMPARABLE_VOLATILITY_ID,
    PHASE_ADJUSTED_PARTICIPATION_ID,
)

STRUCTURE_LOOKBACKS = (4, 16, 48)
STRUCTURE_DEFAULT_LOOKBACK = 48
STRUCTURE_SIGMA_HALF_LIFE = 48
STRUCTURE_NEAR_SIGMA = 0.5

RS_FAST_HALF_LIFE = 12
RS_SLOW_HALF_LIFE = 48
VOLATILITY_PERCENTILE_LOOKBACK = 192

PARTICIPATION_REFERENCE_OCCURRENCES = 20
PARTICIPATION_MIN_OCCURRENCES = 10

_CONTINUOUS_ASSETS = frozenset({"BTCUSDT", "ETHUSDT"})
_USABLE_SOURCE_QUALITIES = frozenset({"observed", "observed_with_constituent_gap_fill"})
_REQUIRED_COLUMNS = frozenset({"timestamp", "open", "high", "low", "close", "volume"})
_SIGNIFICANT_STRUCTURE_STATES = frozenset(
    {
        "closed_above_prior_channel",
        "closed_below_prior_channel",
        "tested_high_rejected",
        "tested_low_rejected",
        "gap_beyond_prior_level",
    }
)


def timeframe_seconds(timeframe: str) -> int:
    """Parse a positive minute/hour/day timeframe into nominal seconds."""

    value = str(timeframe).strip().lower()
    if len(value) < 2 or value[-1] not in {"m", "h", "d"}:
        raise ValueError(f"Unsupported timeframe duration: {timeframe!r}")
    try:
        amount = int(value[:-1])
    except ValueError as exc:
        raise ValueError(f"Unsupported timeframe duration: {timeframe!r}") from exc
    if amount <= 0:
        raise ValueError(f"Unsupported timeframe duration: {timeframe!r}")
    return amount * {"m": 60, "h": 3_600, "d": 86_400}[value[-1]]


def compute_market_context_frame(
    frame: pl.DataFrame,
    *,
    asset: str,
    timeframe: str,
) -> pl.DataFrame:
    """Compute all Market Context v1 families in one chronological pass.

    The returned rows remain keyed by the source bar's open ``timestamp``.
    ``next_action_timestamp`` records when post-close fields may first be used.
    The function never reads a future price or volume.  Looking at the next
    timestamp is used only to align a completed observation with the next bar
    that actually exists on the chart.
    """

    missing = sorted(_REQUIRED_COLUMNS - set(frame.columns))
    if missing:
        raise ValueError(f"OHLCV frame missing columns: {missing}")

    normalized_asset = str(asset).strip().upper()
    interval_seconds = timeframe_seconds(timeframe)
    projected_columns = [
        column
        for column in (
            "timestamp",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "is_synthetic_no_trade",
            "is_open_session_gap_fill",
            "is_session_open_bar",
            "session_bar_pos",
            "is_bar_final",
            "is_final",
            "bar_final",
        )
        if column in frame.columns
    ]
    source = (
        frame.select(projected_columns)
        .unique(subset=["timestamp"], keep="last")
        .sort("timestamp")
    )
    if source.is_empty():
        return pl.DataFrame()

    source_rows = source.to_dicts()
    timestamps = [_utc(row["timestamp"]) for row in source_rows]
    typed_rows = [_typed_ohlcv(row) for row in source_rows]
    valid_ohlc_flags = [_valid_typed_ohlc(row) for row in typed_rows]
    source_qualities = [
        _source_quality(row, interval_seconds=interval_seconds) for row in source_rows
    ]
    observed_flags = [
        quality in _USABLE_SOURCE_QUALITIES and valid
        for quality, valid in zip(source_qualities, valid_ohlc_flags)
    ]
    invalid_or_partial_prefix = [0]
    degraded_prefix = [0]
    for valid, quality in zip(valid_ohlc_flags, source_qualities):
        invalid_or_partial_prefix.append(
            invalid_or_partial_prefix[-1]
            + int(not valid or quality == "partial_bar_excluded")
        )
        degraded_prefix.append(degraded_prefix[-1] + int(quality != "observed"))
    phase_basis = _phase_basis(source, normalized_asset)

    rolling_highs: dict[int, deque[tuple[int, float]]] = {
        lookback: deque() for lookback in STRUCTURE_LOOKBACKS
    }
    rolling_lows: dict[int, deque[tuple[int, float]]] = {
        lookback: deque() for lookback in STRUCTURE_LOOKBACKS
    }

    structure_variance: float | None = None
    structure_variance_count = 0
    previous_observed_close: float | None = None
    previous_actionable_structure_state: str | None = None

    rs_fast_variance: float | None = None
    rs_slow_variance: float | None = None
    close_slow_variance: float | None = None
    rs_observation_count = 0
    close_return_count = 0
    prior_rs_slow: deque[float] = deque()
    sorted_prior_rs_slow: list[float] = []

    phase_history: defaultdict[int, deque[float]] = defaultdict(
        lambda: deque(maxlen=PARTICIPATION_REFERENCE_OCCURRENCES)
    )
    output_columns: dict[str, list[Any]] | None = None

    structure_decay = _decay(STRUCTURE_SIGMA_HALF_LIFE)
    rs_fast_decay = _decay(RS_FAST_HALF_LIFE)
    rs_slow_decay = _decay(RS_SLOW_HALF_LIFE)

    for index, row in enumerate(source_rows):
        timestamp = timestamps[index]
        nominal_close = timestamp + timedelta(seconds=interval_seconds)
        next_observed = timestamps[index + 1] if index + 1 < len(timestamps) else None
        next_action = (
            max(nominal_close, next_observed)
            if next_observed is not None
            else nominal_close
        )
        source_quality = source_qualities[index]
        valid_ohlc = valid_ohlc_flags[index]
        observed = observed_flags[index]
        typed = typed_rows[index]

        result: dict[str, Any] = {
            "timestamp": timestamp,
            "next_action_timestamp": next_action,
            "next_action_observed": next_observed is not None,
            "source_quality": source_quality,
            "bar_valid": bool(valid_ohlc),
            "phase_basis": phase_basis,
            "known_session_gap": bool(row.get("is_session_open_bar") is True),
        }

        if index:
            prior_index = index - 1
            prior_typed = typed_rows[prior_index]
            prior_high = prior_typed["high"]
            prior_low = prior_typed["low"]
            if prior_high is not None and prior_low is not None:
                for lookback in STRUCTURE_LOOKBACKS:
                    high_queue = rolling_highs[lookback]
                    low_queue = rolling_lows[lookback]
                    while high_queue and high_queue[-1][1] <= prior_high:
                        high_queue.pop()
                    high_queue.append((prior_index, prior_high))
                    while low_queue and low_queue[-1][1] >= prior_low:
                        low_queue.pop()
                    low_queue.append((prior_index, prior_low))

        for lookback in STRUCTURE_LOOKBACKS:
            window_start = index - lookback
            high_queue = rolling_highs[lookback]
            low_queue = rolling_lows[lookback]
            while high_queue and high_queue[0][0] < window_start:
                high_queue.popleft()
            while low_queue and low_queue[0][0] < window_start:
                low_queue.popleft()
            complete = (
                window_start >= 0
                and invalid_or_partial_prefix[index]
                - invalid_or_partial_prefix[window_start]
                == 0
            )
            result[f"structure_mature_{lookback}"] = bool(complete)
            result[f"prior_high_{lookback}"] = (
                high_queue[0][1] if complete and high_queue else None
            )
            result[f"prior_low_{lookback}"] = (
                low_queue[0][1] if complete and low_queue else None
            )

        prior_sigma = (
            math.sqrt(max(structure_variance, 0.0))
            if structure_variance is not None
            and structure_variance_count >= STRUCTURE_SIGMA_HALF_LIFE
            else None
        )
        structure = _structure_state(
            typed=typed,
            valid_ohlc=valid_ohlc,
            source_quality=source_quality,
            upper=result[f"prior_high_{STRUCTURE_DEFAULT_LOOKBACK}"],
            lower=result[f"prior_low_{STRUCTURE_DEFAULT_LOOKBACK}"],
            prior_sigma=prior_sigma,
            prior_degraded=(
                index >= STRUCTURE_DEFAULT_LOOKBACK
                and degraded_prefix[index]
                - degraded_prefix[index - STRUCTURE_DEFAULT_LOOKBACK]
                > 0
            ),
        )
        result.update(structure)
        state = str(structure["structure_state"])
        actionable_state = state != "warmup_or_flat"
        result["structure_mature"] = bool(actionable_state)
        changed = actionable_state and state != previous_actionable_structure_state
        result["structure_state_changed"] = bool(changed)
        if actionable_state:
            previous_actionable_structure_state = state

        current_return = None
        if (
            observed
            and previous_observed_close is not None
            and typed["close"] is not None
        ):
            current_return = _positive_log_ratio(
                typed["close"], previous_observed_close
            )
        result["gap_return"] = (
            _positive_log_ratio(float(typed["open"]), previous_observed_close)
            if result["known_session_gap"]
            and observed
            and typed["open"] is not None
            and previous_observed_close is not None
            else None
        )

        rs_value = _rogers_satchell_typed(typed) if observed else None
        prior_slow_sigma = (
            math.sqrt(max(rs_slow_variance, 0.0))
            if rs_slow_variance is not None
            else None
        )
        if rs_value is not None:
            rs_fast_variance = _ewm_update(rs_fast_variance, rs_value, rs_fast_decay)
            rs_slow_variance = _ewm_update(rs_slow_variance, rs_value, rs_slow_decay)
            rs_observation_count += 1
        if current_return is not None:
            close_slow_variance = _ewm_update(
                close_slow_variance,
                current_return * current_return,
                rs_slow_decay,
            )
            close_return_count += 1

        rs_fast = (
            math.sqrt(max(rs_fast_variance, 0.0))
            if rs_fast_variance is not None
            else None
        )
        rs_slow = (
            math.sqrt(max(rs_slow_variance, 0.0))
            if rs_slow_variance is not None
            else None
        )
        fast_slow_ratio = _positive_ratio(rs_fast, rs_slow)
        range_shock_ratio = _positive_ratio(
            math.sqrt(max(rs_value, 0.0)) if rs_value is not None else None,
            prior_slow_sigma,
        )
        close_slow = (
            math.sqrt(max(close_slow_variance, 0.0))
            if close_slow_variance is not None
            else None
        )
        rs_to_close = _positive_ratio(rs_slow, close_slow)
        percentile = _prior_percentile_sorted(rs_slow, sorted_prior_rs_slow)
        volatility_mature = (
            observed
            and rs_observation_count >= RS_SLOW_HALF_LIFE
            and close_return_count >= RS_SLOW_HALF_LIFE
            and len(prior_rs_slow) >= VOLATILITY_PERCENTILE_LOOKBACK
            and percentile is not None
        )
        result.update(
            {
                "rs_variance": rs_value,
                "rs_fast": rs_fast,
                "rs_slow": rs_slow,
                "rs_fast_slow_ratio": fast_slow_ratio,
                "rs_fast_slow_ratio_score": _log_ratio_score(fast_slow_ratio),
                "rs_percentile": percentile,
                "range_shock_ratio": range_shock_ratio,
                "range_shock_score": _log_ratio_score(range_shock_ratio),
                "rs_to_close_vol_ratio": rs_to_close,
                "volatility_mature": bool(volatility_mature),
                "volatility_quality": _volatility_quality(
                    source_quality=source_quality,
                    valid_ohlc=valid_ohlc,
                    rs_value=rs_value,
                    reference_count=len(prior_rs_slow),
                    mature=bool(volatility_mature),
                ),
                "volatility_reference_count": len(prior_rs_slow),
            }
        )
        if observed and rs_slow is not None:
            if len(prior_rs_slow) >= VOLATILITY_PERCENTILE_LOOKBACK:
                expired = prior_rs_slow.popleft()
                expired_index = bisect_left(sorted_prior_rs_slow, expired)
                sorted_prior_rs_slow.pop(expired_index)
            prior_rs_slow.append(rs_slow)
            insort(sorted_prior_rs_slow, rs_slow)

        phase = _phase_for_row(
            row,
            timestamp=timestamp,
            phase_basis=phase_basis,
            interval_seconds=interval_seconds,
        )
        references = phase_history[phase] if phase is not None else deque()
        reference_count = len(references)
        expected_volume = (
            float(statistics.median(references))
            if reference_count >= PARTICIPATION_MIN_OCCURRENCES
            else None
        )
        volume = typed["volume"]
        participation_mature = (
            observed
            and volume is not None
            and phase is not None
            and reference_count >= PARTICIPATION_REFERENCE_OCCURRENCES
            and expected_volume is not None
            and expected_volume > 0.0
        )
        rvol = (
            volume / expected_volume
            if observed
            and volume is not None
            and expected_volume is not None
            and expected_volume > 0.0
            else None
        )
        clipped_log_rvol = _clipped_log_rvol(rvol)
        result.update(
            {
                "participation_phase": phase,
                "participation_expected_volume": expected_volume,
                "participation_reference_count": reference_count,
                "participation_rvol": rvol,
                "participation_log_rvol": clipped_log_rvol,
                "participation_score": (
                    math.tanh(clipped_log_rvol)
                    if clipped_log_rvol is not None
                    else None
                ),
                "participation_mature": bool(participation_mature),
                "participation_quality": _participation_quality(
                    source_quality=source_quality,
                    valid_ohlc=valid_ohlc,
                    volume=volume,
                    phase=phase,
                    reference_count=reference_count,
                    expected_volume=expected_volume,
                ),
            }
        )
        if observed and volume is not None and phase is not None:
            phase_history[phase].append(volume)

        if current_return is not None:
            structure_variance = _ewm_update(
                structure_variance,
                current_return * current_return,
                structure_decay,
            )
            structure_variance_count += 1
        if observed and typed["close"] is not None:
            previous_observed_close = typed["close"]

        if output_columns is None:
            output_columns = {key: [value] for key, value in result.items()}
        else:
            for key, values in output_columns.items():
                values.append(result[key])

    return pl.DataFrame(output_columns or {}, infer_schema_length=None)


def build_market_context_overlays(
    frame: pl.DataFrame,
    *,
    asset: str,
    timeframe: str,
    visible_start: str | datetime | None = None,
    visible_end: str | datetime | None = None,
) -> dict[str, dict[str, Any]]:
    """Return JSON-safe chart overlays for all three Market Context families.

    ``visible_start`` and ``visible_end`` trim emitted series without removing
    their hidden calculation history.  Structure channel points are source
    stamped; post-close series are action stamped.
    """

    computed = compute_market_context_frame(
        frame,
        asset=asset,
        timeframe=timeframe,
    )
    if computed.is_empty():
        return _empty_overlays(asset=asset, timeframe=timeframe)

    start = _optional_utc(visible_start) or _utc(computed["timestamp"][0])
    end = _optional_utc(visible_end) or _utc(computed["timestamp"][-1])
    if start > end:
        raise ValueError(f"visible_start {start!s} is after visible_end {end!s}")
    interval = timedelta(seconds=timeframe_seconds(timeframe))
    source_window = computed.filter(
        (pl.col("timestamp") >= start) & (pl.col("timestamp") <= end)
    )
    channel_columns = [
        "timestamp",
        *[
            f"prior_{side}_{lookback}"
            for lookback in STRUCTURE_LOOKBACKS
            for side in ("high", "low")
        ],
    ]
    source_rows = source_window.select(channel_columns).to_dicts()
    action_columns = (
        "timestamp",
        "next_action_timestamp",
        "next_action_observed",
        "structure_state",
        "structure_side",
        "structure_state_changed",
        "structure_quality",
        "channel_position",
        "up_room_sigma",
        "down_room_sigma",
        "rs_percentile",
        "rs_fast_slow_ratio_score",
        "range_shock_score",
        "rs_fast_slow_ratio",
        "range_shock_ratio",
        "rs_to_close_vol_ratio",
        "participation_score",
        "participation_rvol",
    )
    action_rows = (
        computed.filter(
            (pl.col("timestamp") <= end)
            & (pl.col("next_action_timestamp") >= start)
            & (pl.col("next_action_timestamp") <= end + interval)
        )
        .select(action_columns)
        .to_dicts()
    )
    last = source_window.tail(1).to_dicts()[0] if not source_window.is_empty() else None

    channels = {
        str(lookback): {
            "upper": _source_series(source_rows, f"prior_high_{lookback}"),
            "lower": _source_series(source_rows, f"prior_low_{lookback}"),
            "maturity_required_prior_bars": lookback,
        }
        for lookback in STRUCTURE_LOOKBACKS
    }
    structure_overlay = {
        "id": PRIOR_STRUCTURE_ID,
        "label": "Prior Structure",
        "version": MARKET_CONTEXT_VERSION,
        "status": _last_status(last, "structure"),
        "diagnostic_only": True,
        "calibrated": False,
        "usable_as_trading_gate": False,
        "availability": {
            "channels": "known_at_source_bar_open_from_strictly_prior_bars",
            "classifications": "post_close_usable_at_next_observed_bar",
        },
        "default_lookback": STRUCTURE_DEFAULT_LOOKBACK,
        "lookbacks": list(STRUCTURE_LOOKBACKS),
        "near_level_threshold_sigma": STRUCTURE_NEAR_SIGMA,
        "scale": {"channel_position": [0.0, 1.0]},
        "channels": channels,
        "channel_position": _action_series(action_rows, "channel_position"),
        "up_room_sigma": _action_series(action_rows, "up_room_sigma"),
        "down_room_sigma": _action_series(action_rows, "down_room_sigma"),
        "markers": _structure_markers(action_rows),
        "last": _structure_last(last),
        "limitations": (
            "Location and rejection context, not a directional trade command. "
            "Session and continuous-futures roll provenance are not inferred."
        ),
    }

    volatility_overlay = {
        "id": COMPARABLE_VOLATILITY_ID,
        "label": "Comparable Volatility",
        "version": MARKET_CONTEXT_VERSION,
        "status": _last_status(last, "volatility"),
        "diagnostic_only": True,
        "calibrated": False,
        "usable_as_trading_gate": False,
        "availability": "post_close_usable_at_next_observed_bar",
        "estimator": "rogers_satchell_ohlc_range_variance",
        "unit": "log_return_sigma_per_bar",
        "half_lives_bars": {"fast": RS_FAST_HALF_LIFE, "slow": RS_SLOW_HALF_LIFE},
        "percentile_reference_prior_observations": VOLATILITY_PERCENTILE_LOOKBACK,
        "gap_treatment": (
            "Rogers-Satchell measures intrabar range only. gap_return is reported "
            "separately only when is_session_open_bar is explicitly true."
        ),
        "scale": {
            "volatility_percentile": [0.0, 1.0],
            "ratio_scores": [-1.0, 1.0],
        },
        "volatility_percentile": _action_series(action_rows, "rs_percentile"),
        "fast_slow_ratio_score": _action_series(
            action_rows, "rs_fast_slow_ratio_score"
        ),
        "range_shock_score": _action_series(action_rows, "range_shock_score"),
        "fast_slow_ratio": _action_series(action_rows, "rs_fast_slow_ratio"),
        "range_shock_ratio": _action_series(action_rows, "range_shock_ratio"),
        "rs_to_close_vol_ratio": _action_series(action_rows, "rs_to_close_vol_ratio"),
        "last": _volatility_last(last),
        "comparability_warning": (
            "Use percentile and ratios within one asset/timeframe. Raw sigma-per-bar "
            "levels are not directly comparable across different bar durations."
        ),
    }

    phase_basis = str(
        last["phase_basis"] if last is not None else computed["phase_basis"][-1]
    )
    participation_overlay = {
        "id": PHASE_ADJUSTED_PARTICIPATION_ID,
        "label": "Phase-Adjusted Participation",
        "version": MARKET_CONTEXT_VERSION,
        "status": _last_status(last, "participation"),
        "diagnostic_only": True,
        "calibrated": False,
        "usable_as_trading_gate": False,
        "availability": "finalized_bar_only_usable_at_next_observed_bar",
        "phase_basis": phase_basis,
        "reference": {
            "method": "prior_only_median_of_comparable_phase",
            "occurrences": PARTICIPATION_REFERENCE_OCCURRENCES,
            "minimum_for_provisional_value": PARTICIPATION_MIN_OCCURRENCES,
            "full_maturity_required": PARTICIPATION_REFERENCE_OCCURRENCES,
        },
        "scale": {"rvol_score": [-1.0, 1.0]},
        "rvol_score": _action_series(action_rows, "participation_score"),
        "rvol": _action_series(action_rows, "participation_rvol"),
        "last": _participation_last(last),
        "volume_semantics": (
            "Dimensionless within-stream relative volume. Crypto volume is base-asset "
            "quantity; futures and FX proxies may be contracts or provider-specific."
        ),
        "limitations": (
            "Partial target bars are excluded. Synthetic/no-trade and known gap-fill "
            "rows do not update the phase reference."
        ),
    }

    return {
        PRIOR_STRUCTURE_ID: structure_overlay,
        COMPARABLE_VOLATILITY_ID: volatility_overlay,
        PHASE_ADJUSTED_PARTICIPATION_ID: participation_overlay,
    }


def _structure_state(
    *,
    typed: dict[str, float | None],
    valid_ohlc: bool,
    source_quality: str,
    upper: float | None,
    lower: float | None,
    prior_sigma: float | None,
    prior_degraded: bool,
) -> dict[str, Any]:
    empty = {
        "structure_state": "warmup_or_flat",
        "structure_side": "neutral",
        "channel_position": None,
        "up_room_sigma": None,
        "down_room_sigma": None,
        "up_break_sigma": None,
        "down_break_sigma": None,
    }
    if source_quality not in _USABLE_SOURCE_QUALITIES:
        return {**empty, "structure_quality": source_quality}
    if not valid_ohlc:
        return {**empty, "structure_quality": "invalid_ohlc"}
    if upper is None or lower is None:
        return {**empty, "structure_quality": "channel_warmup"}
    if upper <= lower:
        return {**empty, "structure_quality": "flat_prior_channel"}
    if prior_sigma is None or prior_sigma <= 0.0:
        return {**empty, "structure_quality": "volatility_scale_warmup_or_zero"}

    open_value = typed["open"]
    high = typed["high"]
    low = typed["low"]
    close = typed["close"]
    assert None not in {open_value, high, low, close}
    open_value = float(open_value)
    high = float(high)
    low = float(low)
    close = float(close)

    position = min(
        1.0,
        max(0.0, math.log(close / lower) / math.log(upper / lower)),
    )
    up_room = max(0.0, math.log(upper / close)) / prior_sigma
    down_room = max(0.0, math.log(close / lower)) / prior_sigma
    up_break = max(0.0, math.log(close / upper)) / prior_sigma
    down_break = max(0.0, math.log(lower / close)) / prior_sigma

    side = "neutral"
    if open_value > upper:
        state, side = "gap_beyond_prior_level", "above"
    elif open_value < lower:
        state, side = "gap_beyond_prior_level", "below"
    elif close > upper:
        state, side = "closed_above_prior_channel", "above"
    elif close < lower:
        state, side = "closed_below_prior_channel", "below"
    else:
        tested_high = high >= upper
        tested_low = low <= lower
        if tested_high and not tested_low:
            state, side = "tested_high_rejected", "above"
        elif tested_low and not tested_high:
            state, side = "tested_low_rejected", "below"
        elif up_room <= STRUCTURE_NEAR_SIGMA:
            state, side = "near_prior_high", "above"
        elif down_room <= STRUCTURE_NEAR_SIGMA:
            state, side = "near_prior_low", "below"
        else:
            state = "inside_range"

    quality = (
        "observed_with_constituent_gap_fill"
        if source_quality == "observed_with_constituent_gap_fill"
        else ("degraded_prior_synthetic_or_gap" if prior_degraded else "mature")
    )
    return {
        "structure_state": state,
        "structure_side": side,
        "channel_position": position,
        "up_room_sigma": up_room,
        "down_room_sigma": down_room,
        "up_break_sigma": up_break,
        "down_break_sigma": down_break,
        "structure_quality": quality,
    }


def _source_quality(row: dict[str, Any], *, interval_seconds: int = 60) -> str:
    finality = _optional_flag(row, ("is_bar_final", "is_final", "bar_final"))
    if finality is False:
        return "partial_bar_excluded"
    if _optional_flag(row, ("is_synthetic_no_trade",)) is True:
        return "synthetic_no_trade"
    if _optional_flag(row, ("is_open_session_gap_fill",)) is True:
        return (
            "known_open_session_gap_fill"
            if interval_seconds <= 60
            else "observed_with_constituent_gap_fill"
        )
    return "observed"


def _valid_ohlc(row: dict[str, Any]) -> bool:
    return _valid_typed_ohlc(_typed_ohlcv(row))


def _valid_typed_ohlc(typed: dict[str, float | None]) -> bool:
    open_value = typed["open"]
    high = typed["high"]
    low = typed["low"]
    close = typed["close"]
    if None in {open_value, high, low, close}:
        return False
    return bool(
        high >= max(open_value, close) and low <= min(open_value, close) and high >= low
    )


def _typed_ohlcv(row: dict[str, Any]) -> dict[str, float | None]:
    result: dict[str, float | None] = {}
    for column in ("open", "high", "low", "close"):
        value = _finite_float(row.get(column))
        result[column] = value if value is not None and value > 0.0 else None
    volume = _finite_float(row.get("volume"))
    result["volume"] = volume if volume is not None and volume >= 0.0 else None
    return result


def _rogers_satchell_typed(typed: dict[str, float | None]) -> float | None:
    if not _valid_typed_ohlc(typed):
        return None
    open_value = float(typed["open"])
    high = float(typed["high"])
    low = float(typed["low"])
    close = float(typed["close"])
    high_open = math.log(high / open_value)
    low_open = math.log(low / open_value)
    close_open = math.log(close / open_value)
    value = high_open * (high_open - close_open) + low_open * (low_open - close_open)
    if value < -1e-15:
        return None
    return max(0.0, value)


def _phase_basis(frame: pl.DataFrame, asset: str) -> str:
    if asset in _CONTINUOUS_ASSETS:
        return "utc_slot_of_day"
    if (
        "session_bar_pos" in frame.columns
        and frame["session_bar_pos"].is_not_null().any()
    ):
        return "session_bar_pos"
    return "utc_slot_fallback_missing_session_bar_pos"


def _phase_for_row(
    row: dict[str, Any],
    *,
    timestamp: datetime,
    phase_basis: str,
    interval_seconds: int,
) -> int | None:
    if phase_basis == "session_bar_pos":
        value = _finite_float(row.get("session_bar_pos"))
        return int(value) if value is not None and value >= 0.0 else None
    seconds = timestamp.hour * 3_600 + timestamp.minute * 60 + timestamp.second
    return seconds // interval_seconds


def _volatility_quality(
    *,
    source_quality: str,
    valid_ohlc: bool,
    rs_value: float | None,
    reference_count: int,
    mature: bool,
) -> str:
    if source_quality not in _USABLE_SOURCE_QUALITIES:
        return source_quality
    if not valid_ohlc or rs_value is None:
        return "invalid_ohlc_or_rs"
    suffix = (
        "_with_constituent_gap_fill"
        if source_quality == "observed_with_constituent_gap_fill"
        else ""
    )
    if mature:
        return f"mature{suffix}"
    return (
        f"reference_warmup_{reference_count}_of_"
        f"{VOLATILITY_PERCENTILE_LOOKBACK}{suffix}"
    )


def _participation_quality(
    *,
    source_quality: str,
    valid_ohlc: bool,
    volume: float | None,
    phase: int | None,
    reference_count: int,
    expected_volume: float | None,
) -> str:
    if source_quality not in _USABLE_SOURCE_QUALITIES:
        return source_quality
    if not valid_ohlc:
        return "invalid_ohlc"
    if volume is None:
        return "invalid_volume"
    if phase is None:
        return "missing_phase"
    if reference_count < PARTICIPATION_MIN_OCCURRENCES:
        return (
            f"reference_warmup_{reference_count}_of_"
            f"{PARTICIPATION_REFERENCE_OCCURRENCES}"
        )
    if expected_volume is None or expected_volume <= 0.0:
        return "nonpositive_expected_volume"
    if volume == 0.0:
        return "observed_zero_volume"
    if reference_count < PARTICIPATION_REFERENCE_OCCURRENCES:
        return (
            f"provisional_reference_{reference_count}_of_"
            f"{PARTICIPATION_REFERENCE_OCCURRENCES}"
        )
    return (
        "mature_with_constituent_gap_fill"
        if source_quality == "observed_with_constituent_gap_fill"
        else "mature"
    )


def _prior_percentile_sorted(value: float | None, history: list[float]) -> float | None:
    if value is None or len(history) < VOLATILITY_PERCENTILE_LOOKBACK:
        return None
    less = bisect_left(history, value)
    equal = bisect_right(history, value) - less
    return (less + (0.5 * equal)) / float(len(history))


def _source_series(rows: list[dict[str, Any]], column: str) -> list[dict[str, Any]]:
    return _series(rows, column, time_column="timestamp")


def _action_series(rows: list[dict[str, Any]], column: str) -> list[dict[str, Any]]:
    return _series(rows, column, time_column="next_action_timestamp")


def _series(
    rows: list[dict[str, Any]],
    column: str,
    *,
    time_column: str,
) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []
    for row in rows:
        value = _finite_float(row.get(column))
        if value is None:
            continue
        points.append({"time": int(_utc(row[time_column]).timestamp()), "value": value})
    return points


def _structure_markers(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    styles = {
        "closed_above_prior_channel": (
            "belowBar",
            "#22c55e",
            "arrowUp",
            "48 close break",
        ),
        "closed_below_prior_channel": (
            "aboveBar",
            "#ef4444",
            "arrowDown",
            "48 close break",
        ),
        "tested_high_rejected": ("aboveBar", "#f59e0b", "circle", "48 high rejected"),
        "tested_low_rejected": ("belowBar", "#38bdf8", "circle", "48 low rejected"),
    }
    markers: list[dict[str, Any]] = []
    for row in rows:
        state = str(row.get("structure_state"))
        if (
            not row.get("structure_state_changed")
            or state not in _SIGNIFICANT_STRUCTURE_STATES
            or not row.get("next_action_observed")
            or row.get("structure_quality") != "mature"
        ):
            continue
        if state == "gap_beyond_prior_level":
            side = str(row.get("structure_side"))
            position = "belowBar" if side == "above" else "aboveBar"
            color = "#a78bfa"
            shape = "square"
            text = f"48 gap {side} prior level"
        else:
            position, color, shape, text = styles[state]
        markers.append(
            {
                "time": int(_utc(row["next_action_timestamp"]).timestamp()),
                "position": position,
                "color": color,
                "shape": shape,
                "text": text,
                "indicator": PRIOR_STRUCTURE_ID,
                "state": state,
                "source_time": int(_utc(row["timestamp"]).timestamp()),
            }
        )
    return markers


def _structure_last(row: dict[str, Any] | None) -> dict[str, Any]:
    if row is None:
        return _empty_last("empty_window")
    return {
        **_common_last(row, family="structure"),
        "state": row.get("structure_state"),
        "side": row.get("structure_side"),
        "channel_position": _finite_float(row.get("channel_position")),
        "up_room_sigma": _finite_float(row.get("up_room_sigma")),
        "down_room_sigma": _finite_float(row.get("down_room_sigma")),
        "room_up_sigma": _finite_float(row.get("up_room_sigma")),
        "room_down_sigma": _finite_float(row.get("down_room_sigma")),
        "up_break_sigma": _finite_float(row.get("up_break_sigma")),
        "down_break_sigma": _finite_float(row.get("down_break_sigma")),
        "prior_high": _finite_float(
            row.get(f"prior_high_{STRUCTURE_DEFAULT_LOOKBACK}")
        ),
        "prior_low": _finite_float(row.get(f"prior_low_{STRUCTURE_DEFAULT_LOOKBACK}")),
    }


def _volatility_last(row: dict[str, Any] | None) -> dict[str, Any]:
    if row is None:
        return _empty_last("empty_window")
    return {
        **_common_last(row, family="volatility"),
        "volatility_percentile": _finite_float(row.get("rs_percentile")),
        "rs_percentile": _finite_float(row.get("rs_percentile")),
        "rs_fast_pct_per_bar": _percent(row.get("rs_fast")),
        "rs_slow_pct_per_bar": _percent(row.get("rs_slow")),
        "fast_slow_ratio": _finite_float(row.get("rs_fast_slow_ratio")),
        "rs_fast_slow_ratio": _finite_float(row.get("rs_fast_slow_ratio")),
        "range_shock_ratio": _finite_float(row.get("range_shock_ratio")),
        "rs_to_close_vol_ratio": _finite_float(row.get("rs_to_close_vol_ratio")),
        "reference_count": int(row.get("volatility_reference_count") or 0),
        "known_session_gap": bool(row.get("known_session_gap")),
        "gap_return_pct": _percent(row.get("gap_return")),
    }


def _participation_last(row: dict[str, Any] | None) -> dict[str, Any]:
    if row is None:
        return _empty_last("empty_window")
    return {
        **_common_last(row, family="participation"),
        "phase": row.get("participation_phase"),
        "phase_basis": row.get("phase_basis"),
        "expected_volume": _finite_float(row.get("participation_expected_volume")),
        "reference_count": int(row.get("participation_reference_count") or 0),
        "rvol": _finite_float(row.get("participation_rvol")),
        "log_rvol_clipped": _finite_float(row.get("participation_log_rvol")),
        "rvol_score": _finite_float(row.get("participation_score")),
        "participation_score": _finite_float(row.get("participation_score")),
    }


def _common_last(row: dict[str, Any], *, family: str) -> dict[str, Any]:
    maturity_key = {
        "structure": "structure_mature",
        "volatility": "volatility_mature",
        "participation": "participation_mature",
    }[family]
    quality_key = {
        "structure": "structure_quality",
        "volatility": "volatility_quality",
        "participation": "participation_quality",
    }[family]
    return {
        "status": _last_status(row, family),
        "mature": bool(row.get(maturity_key)),
        "quality": str(row.get(quality_key) or "unknown"),
        "source_quality": str(row.get("source_quality") or "unknown"),
        "source_as_of": _iso(row.get("timestamp")),
        "as_of": _iso(row.get("next_action_timestamp")),
        "availability": "post_close_usable_at_next_observed_bar",
    }


def _last_status(row: dict[str, Any] | None, family: str) -> str:
    if row is None:
        return "empty_window"
    quality = str(
        row.get(
            {
                "structure": "structure_quality",
                "volatility": "volatility_quality",
                "participation": "participation_quality",
            }[family]
        )
        or "unknown"
    )
    if quality == "mature":
        return "ok"
    if "warmup" in quality or "provisional" in quality:
        return "warmup"
    return "data_quality"


def _empty_overlays(*, asset: str, timeframe: str) -> dict[str, dict[str, Any]]:
    common = {
        "version": MARKET_CONTEXT_VERSION,
        "status": "empty_window",
        "diagnostic_only": True,
        "calibrated": False,
        "usable_as_trading_gate": False,
        "asset": str(asset).strip().upper(),
        "timeframe": str(timeframe).strip().lower(),
        "last": _empty_last("empty_window"),
    }
    return {
        PRIOR_STRUCTURE_ID: {
            **common,
            "id": PRIOR_STRUCTURE_ID,
            "label": "Prior Structure",
            "channels": {
                str(item): {"upper": [], "lower": []} for item in STRUCTURE_LOOKBACKS
            },
            "markers": [],
        },
        COMPARABLE_VOLATILITY_ID: {
            **common,
            "id": COMPARABLE_VOLATILITY_ID,
            "label": "Comparable Volatility",
            "volatility_percentile": [],
            "fast_slow_ratio_score": [],
            "range_shock_score": [],
        },
        PHASE_ADJUSTED_PARTICIPATION_ID: {
            **common,
            "id": PHASE_ADJUSTED_PARTICIPATION_ID,
            "label": "Phase-Adjusted Participation",
            "rvol_score": [],
            "rvol": [],
        },
    }


def _empty_last(status: str) -> dict[str, Any]:
    return {
        "status": status,
        "mature": False,
        "quality": status,
        "source_as_of": None,
        "as_of": None,
    }


def _optional_flag(row: dict[str, Any], names: tuple[str, ...]) -> bool | None:
    for name in names:
        if name in row and row[name] is not None:
            return bool(row[name])
    return None


def _finite_float(value: Any) -> float | None:
    try:
        typed = float(value)
    except (TypeError, ValueError):
        return None
    return typed if math.isfinite(typed) else None


def _positive_log_ratio(numerator: float, denominator: float) -> float | None:
    if numerator <= 0.0 or denominator <= 0.0:
        return None
    return math.log(numerator / denominator)


def _positive_ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator <= 0.0:
        return None
    value = numerator / denominator
    return value if math.isfinite(value) and value >= 0.0 else None


def _decay(half_life: int) -> float:
    return math.exp(-math.log(2.0) / float(half_life))


def _ewm_update(previous: float | None, value: float, decay: float) -> float:
    return value if previous is None else (decay * previous) + ((1.0 - decay) * value)


def _log_ratio_score(value: float | None) -> float | None:
    if value is None:
        return None
    if value == 0.0:
        return -1.0
    return math.tanh(max(-8.0, min(8.0, math.log(value))))


def _clipped_log_rvol(value: float | None) -> float | None:
    if value is None:
        return None
    if value == 0.0:
        return -8.0
    if value < 0.0:
        return None
    return max(-8.0, min(8.0, math.log(value)))


def _percent(value: Any) -> float | None:
    typed = _finite_float(value)
    return None if typed is None else typed * 100.0


def _utc(value: Any) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _optional_utc(value: str | datetime | None) -> datetime | None:
    return None if value in {None, ""} else _utc(value)


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    return _utc(value).isoformat().replace("+00:00", "Z")
