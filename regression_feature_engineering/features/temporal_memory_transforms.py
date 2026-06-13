"""Temporal memory transforms for curated regression path features.

This family turns selected causal base features into prior-row memory signals.
It is intentionally stateful so chunked materialization can stay memory bounded
without resetting lags or EWM state at chunk boundaries.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Iterable

import polars as pl


FEATURE_FAMILY = "temporal_memory_transforms"
TARGET_INTENT = (
    "lags",
    "ewm_state",
    "slope",
    "percentile_rank_position",
)
DEFAULT_MEMORY_LAGS: tuple[int, ...] = (1, 16)
DEFAULT_MEMORY_EWM_SPANS: tuple[int, ...] = (16, 64)
DEFAULT_MEMORY_RANK_WINDOWS: tuple[int, ...] = (64,)
DEFAULT_MEMORY_DIFF_LAGS: tuple[int, ...] = (16,)


def parse_positive_ints(raw: str | tuple[int, ...] | list[int] | None, *, default: tuple[int, ...], name: str) -> tuple[int, ...]:
    """Parse positive integer transform parameters."""

    if raw is None:
        values = default
    elif isinstance(raw, str):
        values = tuple(int(part.strip()) for part in raw.split(",") if part.strip())
    else:
        values = tuple(int(value) for value in raw)
    if not values or any(value <= 0 for value in values):
        raise ValueError(f"{name} must contain positive integers")
    return tuple(dict.fromkeys(values))


def selected_source_columns(
    available_columns: Iterable[str],
    *,
    timeframes: tuple[str, ...],
    room_lookbacks: tuple[int, ...],
    accept_lookbacks: tuple[int, ...],
) -> tuple[str, ...]:
    """Select a curated source list from already generated base features.

    The list is intentionally small. Phase 5 should describe memory in the most
    useful volatility, room, and acceptance signals, not blindly transform every
    column produced by previous families.
    """

    available = set(available_columns)
    room_lookback = _preferred_lookback(room_lookbacks, preferred=16)
    accept_lookback = _preferred_lookback(accept_lookbacks, preferred=16)
    candidates: list[str] = [
        "rpf_vol_atr_std_dominance_bnd",
        "rpf_vol_atr_std_log_ratio",
        "rpf_accept_tf_direction_agreement_bnd",
    ]
    candidates.extend(sorted(col for col in available if col.startswith("rpf_vol_tb_vol_z_l")))
    candidates.extend(sorted(col for col in available if col.startswith("rpf_vol_tb_vol_rel_median_l")))

    for timeframe in timeframes:
        candidates.extend(
            [
                f"rpf_vol_{timeframe}_range_to_tb_vol",
                f"rpf_vol_{timeframe}_range_efficiency_bnd",
                f"rpf_room_{timeframe}_room_balance_l{room_lookback}_vol",
                f"rpf_room_{timeframe}_donchian_pos_l{room_lookback}_bnd",
                f"rpf_room_{timeframe}_value_dist_l{room_lookback}_vol",
                f"rpf_accept_{timeframe}_close_loc_balance_l{accept_lookback}_bnd",
                f"rpf_accept_{timeframe}_return_persist_l{accept_lookback}_bnd",
                f"rpf_accept_{timeframe}_value_accept_balance_l{accept_lookback}_bnd",
                f"rpf_accept_{timeframe}_trend_eff_l{accept_lookback}_bnd",
            ]
        )
    return tuple(dict.fromkeys(col for col in candidates if col in available))


def feature_columns(
    *,
    source_columns: tuple[str, ...],
    lags: tuple[int, ...] = DEFAULT_MEMORY_LAGS,
    ewm_spans: tuple[int, ...] = DEFAULT_MEMORY_EWM_SPANS,
    rank_windows: tuple[int, ...] = DEFAULT_MEMORY_RANK_WINDOWS,
    diff_lags: tuple[int, ...] = DEFAULT_MEMORY_DIFF_LAGS,
) -> tuple[str, ...]:
    """Return model-facing temporal-memory feature columns."""

    columns: list[str] = []
    for source in source_columns:
        slug = _source_slug(source)
        for lag in lags:
            columns.append(f"rpf_mem_{slug}_lag{lag}")
        for span in ewm_spans:
            columns.extend(
                [
                    f"rpf_mem_{slug}_ewm{span}",
                    f"rpf_mem_{slug}_ewm{span}_slope",
                    f"rpf_mem_{slug}_ewm{span}_resid",
                ]
            )
        for window in rank_windows:
            columns.append(f"rpf_mem_{slug}_rankpos{window}_bnd")
        for lag in diff_lags:
            columns.extend(
                [
                    f"rpf_mem_{slug}_diff{lag}",
                    f"rpf_mem_{slug}_diff2_{lag}",
                ]
            )
    return tuple(columns)


@dataclass
class TemporalMemoryState:
    """Streaming prior-row transform state for one asset/root materialization."""

    source_columns: tuple[str, ...]
    lags: tuple[int, ...] = DEFAULT_MEMORY_LAGS
    ewm_spans: tuple[int, ...] = DEFAULT_MEMORY_EWM_SPANS
    rank_windows: tuple[int, ...] = DEFAULT_MEMORY_RANK_WINDOWS
    diff_lags: tuple[int, ...] = DEFAULT_MEMORY_DIFF_LAGS
    _history: dict[str, deque[float]] = field(default_factory=dict, init=False)
    _ewm_state: dict[tuple[str, int], float | None] = field(default_factory=dict, init=False)
    _ewm_history: dict[tuple[str, int], deque[float]] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        max_history = max(
            [1, *self.lags, *self.rank_windows, *((lag * 2) + 1 for lag in self.diff_lags)]
        )
        for source in self.source_columns:
            self._history[source] = deque(maxlen=max_history)
            for span in self.ewm_spans:
                key = (source, int(span))
                self._ewm_state[key] = None
                self._ewm_history[key] = deque(maxlen=max(1, int(span)))

    def transform_frame(self, df: pl.DataFrame) -> pl.DataFrame:
        """Return temporal-memory features for `df` and advance state.

        All returned values are based on rows observed before the current row.
        The current row updates state only after its features are emitted.
        """

        missing = [source for source in self.source_columns if source not in df.columns]
        if missing:
            raise ValueError(f"Temporal memory source columns missing from frame: {missing}")

        output: dict[str, list[float]] = {
            name: [] for name in feature_columns(
                source_columns=self.source_columns,
                lags=self.lags,
                ewm_spans=self.ewm_spans,
                rank_windows=self.rank_windows,
                diff_lags=self.diff_lags,
            )
        }
        values_by_source = {source: [_clean_value(value) for value in df.get_column(source).to_list()] for source in self.source_columns}

        for row_idx in range(df.height):
            for source in self.source_columns:
                slug = _source_slug(source)
                history = self._history[source]
                current = values_by_source[source][row_idx]
                previous = history[-1] if history else 0.0

                for lag in self.lags:
                    output[f"rpf_mem_{slug}_lag{lag}"].append(_history_value(history, int(lag)))

                for span in self.ewm_spans:
                    span = int(span)
                    key = (source, span)
                    state = self._ewm_state[key]
                    ewm_value = 0.0 if state is None else state
                    prior_states = self._ewm_history[key]
                    slope_base = prior_states[0] if len(prior_states) == prior_states.maxlen else ewm_value
                    output[f"rpf_mem_{slug}_ewm{span}"].append(ewm_value)
                    output[f"rpf_mem_{slug}_ewm{span}_slope"].append(ewm_value - slope_base)
                    output[f"rpf_mem_{slug}_ewm{span}_resid"].append(previous - ewm_value)

                for window in self.rank_windows:
                    output[f"rpf_mem_{slug}_rankpos{int(window)}_bnd"].append(_rank_position(history, int(window)))

                for lag in self.diff_lags:
                    lag = int(lag)
                    prev_lag = _history_value(history, lag + 1)
                    prev_2lag = _history_value(history, (lag * 2) + 1)
                    output[f"rpf_mem_{slug}_diff{lag}"].append(previous - prev_lag)
                    output[f"rpf_mem_{slug}_diff2_{lag}"].append(previous - (2.0 * prev_lag) + prev_2lag)

                self._update_ewm(source, current)
                history.append(current)

        return pl.DataFrame(output)

    def _update_ewm(self, source: str, value: float) -> None:
        for span in self.ewm_spans:
            span = int(span)
            key = (source, span)
            old_state = self._ewm_state[key]
            alpha = 2.0 / (span + 1.0)
            new_state = value if old_state is None else (alpha * value) + ((1.0 - alpha) * old_state)
            self._ewm_state[key] = new_state
            self._ewm_history[key].append(new_state)


def _preferred_lookback(values: tuple[int, ...], *, preferred: int) -> int:
    if preferred in values:
        return preferred
    ordered = sorted(int(value) for value in values)
    return ordered[len(ordered) // 2]


def _source_slug(source: str) -> str:
    return source.removeprefix("rpf_")


def _clean_value(value: object) -> float:
    try:
        out = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0
    if out != out or out in (float("inf"), float("-inf")):
        return 0.0
    return out


def _history_value(history: deque[float], lag: int) -> float:
    if lag <= 0 or len(history) < lag:
        return 0.0
    return history[-lag]


def _rank_position(history: deque[float], window: int) -> float:
    if not history:
        return 0.5
    selected = list(history)[-int(window):]
    if not selected:
        return 0.5
    value = selected[-1]
    low = min(selected)
    high = max(selected)
    if high <= low:
        return 0.5
    return max(0.0, min(1.0, (value - low) / (high - low)))
