"""Bounded, chronological research optimizer for the Analyst indicators.

This module deliberately optimizes a small, fixed strategy grid.  Every
development evaluation is a prefix replay with an explicit evaluation start,
so indicator state is warmed only from information that existed before the
fold.  The latest 20% of target-timeframe buckets is kept untouched until one
configuration has been selected on the development folds.

Results are research evidence, not a promise of future profitability.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import math
import os
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, fields, is_dataclass, replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from statistics import median
from typing import Any

import polars as pl
from forward_paper.runtime import default_state_dir
from minute_replay import (
    IndicatorStrategyConfig,
    ReplayCostConfig,
    run_minute_replay,
)

OPTIMIZER_VERSION = "indicator_optimizer_v1"
DEFAULT_TRIAL_REGISTRY_PATH = default_state_dir() / "optimizer_trials.jsonl"
DISCLAIMER = (
    "Historical optimization is research evidence only and does not guarantee "
    "future profitability."
)

_CUSUM_SENSITIVITIES = (
    "Fast (Day Trade)",
    "Balanced (Swing)",
    "Slow (Trend)",
)
_HORIZON_TEMPLATES = (
    {
        "name": "responsive",
        "horizons": (8, 32, 128),
        "aligned_score": 0.16,
        "aligned_quality": 0.20,
        "developing_score": 0.06,
    },
    {
        "name": "balanced",
        "horizons": (12, 48, 192),
        "aligned_score": 0.20,
        "aligned_quality": 0.25,
        "developing_score": 0.08,
    },
)
_EXPERIMENTAL_PROTOTYPE_GATE_OPTIONS = (False, True)
_FIXED_CHANGE_RISK_THRESHOLD = 0.55
_FAST_SLOW_VOLATILITY_GATES = (1.50, 1.75)
_COST_FIELD_TOKENS = (
    "fee",
    "commission",
    "slippage",
    "spread",
    "impact",
    "funding",
    "borrow",
)


@dataclass(frozen=True)
class _Fold:
    index: int
    start_row: int
    end_row: int
    start_time: datetime
    end_time: datetime


def optimize_indicator_strategy(
    frame: pl.DataFrame,
    asset: str,
    timeframe: str,
    costs: ReplayCostConfig | Mapping[str, Any],
    *,
    research_start: str | datetime | None = None,
    trial_registry_path: str | Path = DEFAULT_TRIAL_REGISTRY_PATH,
    holdout_fraction: float = 0.20,
    development_folds: int = 3,
    minimum_warmup_bars: int = 193,
    minimum_fold_bars: int = 48,
    minimum_holdout_bars: int = 48,
    minimum_fills_per_fold: int = 5,
    maximum_drawdown: float = 0.35,
    positive_fold_ratio: float = 0.60,
    replay_clock: datetime | None = None,
) -> dict[str, Any]:
    """Select one bounded indicator configuration using causal walk-forward replay.

    The latest ``holdout_fraction`` of target-timeframe buckets is not passed to
    any development trial.  Parameters are selected from a fixed 24-candidate
    grid using median fold net Sharpe under doubled trading costs minus half the
    interquartile range.  The returned object is JSON serializable.
    """

    registry = Path(trial_registry_path)
    base = _base_result(asset=asset, timeframe=timeframe, registry=registry)
    problem = _validate_request(
        frame=frame,
        asset=asset,
        timeframe=timeframe,
        holdout_fraction=holdout_fraction,
        development_folds=development_folds,
        minimum_warmup_bars=minimum_warmup_bars,
        minimum_fold_bars=minimum_fold_bars,
        minimum_holdout_bars=minimum_holdout_bars,
        minimum_fills_per_fold=minimum_fills_per_fold,
        maximum_drawdown=maximum_drawdown,
        positive_fold_ratio=positive_fold_ratio,
    )
    if problem is not None:
        return _insufficient_result(base, registry, problem)

    try:
        normalized_costs = _coerce_costs(costs)
    except (TypeError, ValueError) as exc:
        return _insufficient_result(base, registry, f"Invalid replay costs: {exc}")

    ordered = frame.sort("timestamp")
    if ordered["timestamp"].n_unique() != ordered.height:
        return _insufficient_result(
            base,
            registry,
            "Duplicate minute timestamps make the replay path ambiguous.",
        )

    try:
        bucket_starts = _target_bucket_starts(
            ordered,
            timeframe,
            replay_clock=replay_clock,
        )
        parsed_research_start = _parse_datetime(research_start)
        research_start_bucket = _research_bucket_index(
            ordered,
            bucket_starts=bucket_starts,
            timeframe=timeframe,
            research_start=parsed_research_start,
        )
    except ValueError as exc:
        return _insufficient_result(base, registry, str(exc))

    split = _build_splits(
        ordered,
        bucket_starts=bucket_starts,
        research_start_bucket=research_start_bucket,
        research_start_requested=parsed_research_start,
        holdout_fraction=holdout_fraction,
        development_folds=development_folds,
        minimum_warmup_bars=minimum_warmup_bars,
        minimum_fold_bars=minimum_fold_bars,
        minimum_holdout_bars=minimum_holdout_bars,
    )
    if isinstance(split, str):
        return _insufficient_result(base, registry, split)
    folds, holdout_start_row, split_metadata = split

    stressed_costs, stressed_fields = _scale_costs(normalized_costs, 2.0)
    data_descriptor = {
        "rows": ordered.height,
        "first_timestamp": ordered["timestamp"][0],
        "last_timestamp": ordered["timestamp"][-1],
        "columns": ordered.columns,
        "split": split_metadata,
    }
    optimization_hash = _digest(
        {
            "version": OPTIMIZER_VERSION,
            "asset": asset,
            "timeframe": timeframe,
            "data": data_descriptor,
            "costs_2x": stressed_costs,
            "grid": _candidate_specs(),
        }
    )

    registry_hashes: list[str] = []
    candidate_results: list[dict[str, Any]] = []
    fold_evaluations = 0
    replay_failures = 0

    for specification in _candidate_specs():
        strategy = _make_strategy_config(specification)
        config = _strategy_as_dict(strategy, specification)
        config_hash = _digest(config)
        fold_summaries: list[dict[str, Any]] = []

        for fold in folds:
            prefix = ordered.slice(0, fold.end_row)
            result, summary, error = _execute_replay(
                prefix,
                asset=asset,
                timeframe=timeframe,
                strategy=strategy,
                costs=stressed_costs,
                evaluation_start=fold.start_time,
                replay_clock=replay_clock,
            )
            fold_evaluations += 1
            if error is not None:
                replay_failures += 1
            constrained = _fold_passes_constraints(
                summary,
                minimum_fills=minimum_fills_per_fold,
                maximum_drawdown=maximum_drawdown,
            )
            fold_summary = {
                "fold": fold.index,
                "start": fold.start_time,
                "end": fold.end_time,
                "prefix_rows": fold.end_row,
                "metrics": summary,
                "constraints_passed": constrained,
                "error": error,
            }
            fold_summaries.append(fold_summary)
            record_hash = _append_registry(
                registry,
                {
                    "schema_version": 1,
                    "optimizer_version": OPTIMIZER_VERSION,
                    "event": "development_fold",
                    "optimization_hash": optimization_hash,
                    "asset": asset,
                    "timeframe": timeframe,
                    "config_hash": config_hash,
                    "config": config,
                    "fold": fold_summary,
                    "cost_multiplier": 2.0,
                    "costs": stressed_costs,
                    "result_hash": _digest(
                        {"summary": summary, "error": error, "result": result}
                    ),
                },
            )
            registry_hashes.append(record_hash)

        sharpes = [item["metrics"]["net_sharpe"] for item in fold_summaries]
        eligible = all(item["constraints_passed"] for item in fold_summaries)
        objective = _robust_objective(sharpes) if eligible else None
        candidate_results.append(
            {
                "config_hash": config_hash,
                "config": config,
                "eligible": eligible,
                "objective": objective,
                "folds": fold_summaries,
            }
        )

    eligible_candidates = [
        candidate
        for candidate in candidate_results
        if candidate["eligible"] and candidate["objective"] is not None
    ]
    eligible_candidates.sort(
        key=lambda item: (-float(item["objective"]), str(item["config_hash"]))
    )
    if not eligible_candidates:
        base.update(
            {
                "status": "insufficient_evidence",
                "reason": (
                    "No candidate produced complete fold metrics while meeting "
                    "the minimum-fill and drawdown constraints."
                ),
                "split": split_metadata,
                "trials": _trial_summary(
                    candidate_results,
                    registry=registry,
                    registry_hashes=registry_hashes,
                    fold_evaluations=fold_evaluations,
                    replay_failures=replay_failures,
                ),
            }
        )
        return _json_safe(base)

    selected = eligible_candidates[0]
    best_specification = _specification_from_config(selected["config"])
    best_strategy = _make_strategy_config(best_specification)
    holdout_start = _as_datetime(ordered["timestamp"][holdout_start_row])

    holdout_result, holdout_metrics, holdout_error = _execute_replay(
        ordered,
        asset=asset,
        timeframe=timeframe,
        strategy=best_strategy,
        costs=stressed_costs,
        evaluation_start=holdout_start,
        replay_clock=replay_clock,
    )
    holdout_constraints = _fold_passes_constraints(
        holdout_metrics,
        minimum_fills=minimum_fills_per_fold,
        maximum_drawdown=maximum_drawdown,
    )
    registry_hashes.append(
        _append_registry(
            registry,
            {
                "schema_version": 1,
                "optimizer_version": OPTIMIZER_VERSION,
                "event": "untouched_holdout",
                "optimization_hash": optimization_hash,
                "asset": asset,
                "timeframe": timeframe,
                "config_hash": selected["config_hash"],
                "config": selected["config"],
                "evaluation_start": holdout_start,
                "cost_multiplier": 2.0,
                "costs": stressed_costs,
                "metrics": holdout_metrics,
                "constraints_passed": holdout_constraints,
                "error": holdout_error,
                "result_hash": _digest(holdout_result),
            },
        )
    )

    final_replay, final_metrics, final_error = _execute_replay(
        ordered,
        asset=asset,
        timeframe=timeframe,
        strategy=best_strategy,
        costs=normalized_costs,
        evaluation_start=holdout_start,
        replay_clock=replay_clock,
        capture_output=True,
    )
    registry_hashes.append(
        _append_registry(
            registry,
            {
                "schema_version": 1,
                "optimizer_version": OPTIMIZER_VERSION,
                "event": "final_holdout_replay",
                "optimization_hash": optimization_hash,
                "asset": asset,
                "timeframe": timeframe,
                "config_hash": selected["config_hash"],
                "config": selected["config"],
                "evaluation_start": holdout_start,
                "cost_multiplier": 1.0,
                "costs": normalized_costs,
                "metrics": final_metrics,
                "error": final_error,
                "result_hash": _digest(final_replay),
            },
        )
    )

    development_metrics = _development_metrics(selected["folds"], selected["objective"])
    gates = _acceptance_gates(
        development=development_metrics,
        holdout=holdout_metrics,
        holdout_error=holdout_error,
        holdout_constraints=holdout_constraints,
        positive_fold_ratio=positive_fold_ratio,
        stressed_fields=stressed_fields,
        final_replay_error=final_error,
    )
    accepted = all(bool(value) for value in gates.values())

    base.update(
        {
            "status": "accepted_for_paper_trading" if accepted else "rejected",
            "reason": (
                "All predeclared research gates passed; forward paper trading is "
                "still required."
                if accepted
                else "The selected configuration failed one or more research gates."
            ),
            "optimization_hash": optimization_hash,
            "split": split_metadata,
            "cost_stress": {
                "multiplier": 2.0,
                "scaled_fields": stressed_fields,
                "costs": stressed_costs,
            },
            "best_config": selected["config"],
            "best_config_hash": selected["config_hash"],
            "trials": _trial_summary(
                candidate_results,
                registry=registry,
                registry_hashes=registry_hashes,
                fold_evaluations=fold_evaluations,
                replay_failures=replay_failures,
            ),
            "development": development_metrics,
            "holdout": {
                "evaluation_start": holdout_start,
                "metrics_2x_cost": holdout_metrics,
                "constraints_passed": holdout_constraints,
                "error": holdout_error,
            },
            "acceptance_gates": gates,
            "final_replay": final_replay,
            "final_replay_error": final_error,
        }
    )
    return _json_safe(base)


def _base_result(*, asset: str, timeframe: str, registry: Path) -> dict[str, Any]:
    return {
        "optimizer_version": OPTIMIZER_VERSION,
        "asset": str(asset).upper(),
        "timeframe": str(timeframe),
        "status": "insufficient_evidence",
        "reason": None,
        "research_only": True,
        "profitability_guaranteed": False,
        "disclaimer": DISCLAIMER,
        "best_config": None,
        "best_config_hash": None,
        "split": None,
        "trials": {
            "candidate_count": 0,
            "fold_evaluations": 0,
            "eligible_candidate_count": 0,
            "replay_failures": 0,
            "registry_path": str(registry),
            "registry_record_hashes": [],
            "candidates": [],
        },
        "development": None,
        "holdout": None,
        "acceptance_gates": {},
        "final_replay": None,
        "final_replay_error": None,
    }


def _validate_request(
    *,
    frame: pl.DataFrame,
    asset: str,
    timeframe: str,
    holdout_fraction: float,
    development_folds: int,
    minimum_warmup_bars: int,
    minimum_fold_bars: int,
    minimum_holdout_bars: int,
    minimum_fills_per_fold: int,
    maximum_drawdown: float,
    positive_fold_ratio: float,
) -> str | None:
    if not isinstance(frame, pl.DataFrame) or frame.is_empty():
        return "A non-empty Polars minute frame is required."
    if "timestamp" not in frame.columns:
        return "The minute frame must contain a timestamp column."
    if not str(asset).strip() or not str(timeframe).strip():
        return "Asset and timeframe are required."
    if not 0.0 < holdout_fraction < 0.5:
        return "holdout_fraction must be between zero and 0.5."
    if development_folds < 3:
        return "At least three chronological development folds are required."
    if min(minimum_warmup_bars, minimum_fold_bars, minimum_holdout_bars) <= 0:
        return "Warm-up, fold, and holdout bar requirements must be positive."
    if minimum_fills_per_fold < 0:
        return "minimum_fills_per_fold must be non-negative."
    if not math.isfinite(maximum_drawdown) or maximum_drawdown <= 0.0:
        return "maximum_drawdown must be positive and finite."
    if not 0.5 <= positive_fold_ratio <= 1.0:
        return "positive_fold_ratio must be between 0.5 and 1.0."
    return None


def _timeframe_seconds(timeframe: str) -> int:
    raw = str(timeframe).strip().lower()
    aliases = {
        "1": 60,
        "1m": 60,
        "5": 300,
        "5m": 300,
        "15": 900,
        "15m": 900,
        "30": 1_800,
        "30m": 1_800,
        "60": 3_600,
        "1h": 3_600,
        "240": 14_400,
        "4h": 14_400,
        "480": 28_800,
        "8h": 28_800,
        "720": 43_200,
        "12h": 43_200,
        "d": 86_400,
        "1d": 86_400,
        "w": 604_800,
        "1w": 604_800,
    }
    if raw not in aliases:
        raise ValueError(f"Unsupported optimizer timeframe: {timeframe!r}")
    return aliases[raw]


def _target_bucket_starts(
    frame: pl.DataFrame,
    timeframe: str,
    *,
    replay_clock: datetime | None = None,
) -> list[int]:
    step_seconds = _timeframe_seconds(timeframe)
    epochs = frame["timestamp"].dt.epoch(time_unit="s").to_list()
    if not epochs or any(value is None for value in epochs):
        raise ValueError("Minute timestamps must be finite UTC datetimes.")
    synthetic = (
        frame["is_synthetic_no_trade"].fill_null(False).to_list()
        if "is_synthetic_no_trade" in frame.columns
        else [False] * frame.height
    )
    starts: list[int] = []
    previous_bucket: int | None = None
    for index, (raw_epoch, is_synthetic) in enumerate(zip(epochs, synthetic)):
        if bool(is_synthetic):
            continue
        bucket = int(raw_epoch) // step_seconds
        if previous_bucket is not None and bucket < previous_bucket:
            raise ValueError("Minute timestamps must be chronological.")
        if bucket != previous_bucket:
            starts.append(index)
            previous_bucket = bucket
    if not starts:
        raise ValueError("Minute frame contains no real target-timeframe buckets.")
    effective_clock = replay_clock or (
        _as_datetime(frame["timestamp"][-1]) + timedelta(minutes=1)
    )
    parsed_clock = _parse_datetime(effective_clock)
    assert parsed_clock is not None
    clock_epoch = int(parsed_clock.timestamp())
    complete_count = 0
    for row_index in starts:
        row_epoch = int(frame["timestamp"][row_index].timestamp())
        bucket_epoch = (row_epoch // step_seconds) * step_seconds
        if bucket_epoch + step_seconds > clock_epoch:
            break
        complete_count += 1
    if complete_count == 0:
        raise ValueError("Minute frame contains no complete target-timeframe buckets.")
    sentinel = starts[complete_count] if complete_count < len(starts) else frame.height
    return [*starts[:complete_count], sentinel]


def _research_bucket_index(
    frame: pl.DataFrame,
    *,
    bucket_starts: Sequence[int],
    timeframe: str,
    research_start: datetime | None,
) -> int:
    if research_start is None:
        return 0
    step_seconds = _timeframe_seconds(timeframe)
    requested_epoch = int(research_start.timestamp())
    for bucket_index, row_index in enumerate(bucket_starts[:-1]):
        row_epoch = int(frame["timestamp"][row_index].timestamp())
        bucket_epoch = (row_epoch // step_seconds) * step_seconds
        if bucket_epoch >= requested_epoch:
            return bucket_index
    raise ValueError("research_start is after the last complete research bucket.")


def _build_splits(
    frame: pl.DataFrame,
    *,
    bucket_starts: list[int],
    research_start_bucket: int,
    research_start_requested: datetime | None,
    holdout_fraction: float,
    development_folds: int,
    minimum_warmup_bars: int,
    minimum_fold_bars: int,
    minimum_holdout_bars: int,
) -> tuple[list[_Fold], int, dict[str, Any]] | str:
    bucket_count = len(bucket_starts) - 1
    research_bars = bucket_count - research_start_bucket
    holdout_bars = max(
        minimum_holdout_bars, math.ceil(research_bars * holdout_fraction)
    )
    development_bars = research_bars - holdout_bars
    warmup_inside_research = max(0, minimum_warmup_bars - research_start_bucket)
    required_development = (
        warmup_inside_research + development_folds * minimum_fold_bars
    )
    if holdout_bars >= research_bars or development_bars < required_development:
        return (
            f"Insufficient target-timeframe research history: {research_bars} bars "
            f"available at/after research_start; need at least "
            f"{required_development + minimum_holdout_bars}."
        )

    evaluation_bars = development_bars - warmup_inside_research
    base_width, remainder = divmod(evaluation_bars, development_folds)
    widths = [
        base_width + (1 if index < remainder else 0)
        for index in range(development_folds)
    ]
    if min(widths) < minimum_fold_bars:
        return "Insufficient history to form the requested chronological folds."

    folds: list[_Fold] = []
    start_bucket = research_start_bucket + warmup_inside_research
    for index, width in enumerate(widths):
        end_bucket = start_bucket + width
        start_row = bucket_starts[start_bucket]
        end_row = bucket_starts[end_bucket]
        folds.append(
            _Fold(
                index=index,
                start_row=start_row,
                end_row=end_row,
                start_time=_as_datetime(frame["timestamp"][start_row]),
                end_time=_as_datetime(frame["timestamp"][end_row - 1]),
            )
        )
        start_bucket = end_bucket

    holdout_start_bucket = research_start_bucket + development_bars
    holdout_start_row = bucket_starts[holdout_start_bucket]
    actual_research_start_row = bucket_starts[research_start_bucket]
    metadata = {
        "method": "chronological_expanding_prefix_walk_forward",
        "shuffled": False,
        "target_timeframe_bars": bucket_count,
        "research_start_requested": research_start_requested,
        "research_start": _as_datetime(frame["timestamp"][actual_research_start_row]),
        "research_bars": research_bars,
        "pre_research_warmup_bars": research_start_bucket,
        "development_bars": development_bars,
        "minimum_warmup_bars": minimum_warmup_bars,
        "research_bars_used_for_additional_warmup": warmup_inside_research,
        "development_folds": development_folds,
        "folds": [
            {
                "fold": fold.index,
                "start": fold.start_time,
                "end": fold.end_time,
                "prefix_rows": fold.end_row,
            }
            for fold in folds
        ],
        "holdout_fraction_requested": holdout_fraction,
        "holdout_bars": holdout_bars,
        "holdout_fraction_actual": holdout_bars / research_bars,
        "holdout_start": _as_datetime(frame["timestamp"][holdout_start_row]),
        "holdout_rows": frame.height - holdout_start_row,
    }
    return folds, holdout_start_row, metadata


def _candidate_specs() -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for sensitivity in _CUSUM_SENSITIVITIES:
        for template in _HORIZON_TEMPLATES:
            for prototype_gate in _EXPERIMENTAL_PROTOTYPE_GATE_OPTIONS:
                for volatility_gate in _FAST_SLOW_VOLATILITY_GATES:
                    candidates.append(
                        {
                            "horizon_template": template["name"],
                            "cusum_sensitivity": sensitivity,
                            "horizons": tuple(template["horizons"]),
                            "aligned_score": template["aligned_score"],
                            "aligned_quality": template["aligned_quality"],
                            "developing_score": template["developing_score"],
                            "change_risk_threshold": _FIXED_CHANGE_RISK_THRESHOLD,
                            "enable_experimental_prototype_regime_gate": (
                                prototype_gate
                            ),
                            "max_fast_slow_ratio": volatility_gate,
                        }
                    )
    return candidates


def _make_strategy_config(specification: Mapping[str, Any]) -> IndicatorStrategyConfig:
    supported = _constructor_fields(IndicatorStrategyConfig)
    if supported is not None:
        unsupported = set(specification) - supported - {"horizon_template"}
        if unsupported:
            raise TypeError(
                "Unsupported IndicatorStrategyConfig fields: "
                + ", ".join(sorted(unsupported))
            )
    kwargs = {
        key: value
        for key, value in specification.items()
        if key != "horizon_template" and (supported is None or key in supported)
    }
    required = {
        "cusum_sensitivity",
        "horizons",
        "aligned_score",
        "aligned_quality",
        "developing_score",
        "change_risk_threshold",
        "enable_experimental_prototype_regime_gate",
        "max_fast_slow_ratio",
    }
    if supported is not None and not required.issubset(supported):
        missing = sorted(required - supported)
        raise TypeError(
            "IndicatorStrategyConfig does not expose optimizer fields: "
            + ", ".join(missing)
        )
    return IndicatorStrategyConfig(**kwargs)


def _constructor_fields(cls: type[Any]) -> set[str] | None:
    signature = inspect.signature(cls)
    if any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD
        for parameter in signature.parameters.values()
    ):
        return None
    return set(signature.parameters)


def _strategy_as_dict(
    strategy: IndicatorStrategyConfig,
    specification: Mapping[str, Any],
) -> dict[str, Any]:
    if hasattr(strategy, "as_dict"):
        values = dict(strategy.as_dict())
    elif is_dataclass(strategy):
        values = asdict(strategy)
    else:
        values = dict(vars(strategy))
    values["horizon_template"] = specification["horizon_template"]
    return _json_safe(values)


def _specification_from_config(config: Mapping[str, Any]) -> dict[str, Any]:
    strategy_fields = tuple(fields(IndicatorStrategyConfig))
    strategy_field_names = {field.name for field in strategy_fields}
    missing = strategy_field_names - set(config)
    if "horizon_template" not in config:
        missing.add("horizon_template")
    if missing:
        raise KeyError(
            "Serialized strategy configuration is missing fields: "
            + ", ".join(sorted(missing))
        )

    unsupported = set(config) - strategy_field_names - {"horizon_template"}
    if unsupported:
        raise TypeError(
            "Serialized strategy configuration contains unsupported fields: "
            + ", ".join(sorted(unsupported))
        )

    specification: dict[str, Any] = {"horizon_template": config["horizon_template"]}
    for field in strategy_fields:
        value = config[field.name]
        # JSON-safe strategy records encode tuple-valued constructor fields as
        # lists.  Recover the constructor type from the dataclass default so a
        # recorded configuration is evaluated exactly as it was selected.
        if isinstance(field.default, tuple) and not isinstance(value, tuple):
            value = tuple(value)
        specification[field.name] = value
    return specification


def _scale_costs(
    costs: ReplayCostConfig | Mapping[str, Any], factor: float
) -> tuple[ReplayCostConfig | Mapping[str, Any], list[str]]:
    if factor <= 0.0 or not math.isfinite(factor):
        raise ValueError("Cost factor must be positive and finite")
    if isinstance(costs, Mapping):
        scaled = dict(costs)
        field_names: list[str] = []
        for key, value in costs.items():
            if _is_cost_field(key, value):
                scaled[key] = float(value) * factor
                field_names.append(str(key))
        return scaled, sorted(field_names)
    if not is_dataclass(costs):
        raise TypeError("costs must be ReplayCostConfig or a mapping")
    updates: dict[str, Any] = {}
    for field in fields(costs):
        value = getattr(costs, field.name)
        if _is_cost_field(field.name, value):
            updates[field.name] = float(value) * factor
    return replace(costs, **updates), sorted(updates)


def _coerce_costs(
    costs: ReplayCostConfig | Mapping[str, Any],
) -> ReplayCostConfig:
    if isinstance(costs, ReplayCostConfig):
        return costs
    if not isinstance(costs, Mapping):
        raise TypeError("costs must be ReplayCostConfig or a mapping")
    supported = _constructor_fields(ReplayCostConfig)
    unknown = set(costs) - supported if supported is not None else set()
    if unknown:
        raise ValueError("unsupported fields: " + ", ".join(sorted(unknown)))
    return ReplayCostConfig(**dict(costs))


def _is_cost_field(name: str, value: Any) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and any(token in str(name).lower() for token in _COST_FIELD_TOKENS)
    )


def _execute_replay(
    frame: pl.DataFrame,
    *,
    asset: str,
    timeframe: str,
    strategy: IndicatorStrategyConfig,
    costs: ReplayCostConfig | Mapping[str, Any],
    evaluation_start: datetime,
    replay_clock: datetime | None,
    capture_output: bool = False,
) -> tuple[dict[str, Any] | None, dict[str, Any], str | None]:
    try:
        result = run_minute_replay(
            frame,
            asset=asset,
            timeframe=timeframe,
            strategy=strategy,
            costs=costs,
            evaluation_start=evaluation_start,
            replay_clock=replay_clock,
            event_limit=5_000 if capture_output else 0,
            capture_series=capture_output,
        )
        if not isinstance(result, Mapping):
            raise TypeError("run_minute_replay must return a mapping")
        safe_result = _json_safe(dict(result))
        return safe_result, _extract_metrics(result), None
    except Exception as exc:  # one failed trial must not erase the full registry
        return None, _empty_metrics(), f"{type(exc).__name__}: {exc}"


def _extract_metrics(result: Mapping[str, Any]) -> dict[str, Any]:
    metrics_value = result.get("metrics", {})
    metrics = metrics_value if isinstance(metrics_value, Mapping) else {}
    combined = dict(result)
    combined.update(metrics)
    net_sharpe = _first_finite(
        combined,
        ("net_sharpe", "annualized_sharpe", "sharpe", "sharpe_ratio"),
    )
    net_return = _return_metric(combined)
    max_drawdown = _drawdown_metric(combined)
    fill_count = _fill_count(combined, result)
    return {
        "net_sharpe": net_sharpe,
        "net_return": net_return,
        "max_drawdown": max_drawdown,
        "fill_count": fill_count,
        "complete": all(
            value is not None
            for value in (net_sharpe, net_return, max_drawdown, fill_count)
        ),
    }


def _first_finite(values: Mapping[str, Any], names: Sequence[str]) -> float | None:
    for name in names:
        raw = values.get(name)
        if isinstance(raw, bool):
            continue
        try:
            value = float(raw)
        except (TypeError, ValueError):
            continue
        if math.isfinite(value):
            return value
    return None


def _return_metric(values: Mapping[str, Any]) -> float | None:
    for name in ("net_return", "total_return", "return", "net_pnl", "total_pnl"):
        value = _first_finite(values, (name,))
        if value is not None:
            return value
    value = _first_finite(values, ("net_return_pct", "total_return_pct", "return_pct"))
    return None if value is None else value / 100.0


def _drawdown_metric(values: Mapping[str, Any]) -> float | None:
    value = _first_finite(values, ("max_drawdown", "maximum_drawdown", "drawdown"))
    if value is not None:
        return abs(value)
    value = _first_finite(values, ("max_drawdown_pct", "maximum_drawdown_pct"))
    return None if value is None else abs(value) / 100.0


def _fill_count(values: Mapping[str, Any], result: Mapping[str, Any]) -> int | None:
    for name in ("fill_count", "fills_count", "trade_count", "trades"):
        raw = values.get(name)
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            continue
        if math.isfinite(float(raw)) and float(raw) >= 0.0:
            return int(raw)
    fills = result.get("fills")
    if isinstance(fills, Sequence) and not isinstance(fills, (str, bytes)):
        return len(fills)
    return None


def _empty_metrics() -> dict[str, Any]:
    return {
        "net_sharpe": None,
        "net_return": None,
        "max_drawdown": None,
        "fill_count": None,
        "complete": False,
    }


def _fold_passes_constraints(
    summary: Mapping[str, Any], *, minimum_fills: int, maximum_drawdown: float
) -> bool:
    return bool(
        summary.get("complete")
        and int(summary["fill_count"]) >= minimum_fills
        and float(summary["max_drawdown"]) <= maximum_drawdown
    )


def _robust_objective(sharpes: Sequence[float | None]) -> float | None:
    if not sharpes or any(value is None for value in sharpes):
        return None
    values = [float(value) for value in sharpes if value is not None]
    if not all(math.isfinite(value) for value in values):
        return None
    iqr = _percentile(values, 0.75) - _percentile(values, 0.25)
    return median(values) - 0.5 * iqr


def _percentile(values: Sequence[float], quantile: float) -> float:
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def _development_metrics(
    fold_summaries: Sequence[Mapping[str, Any]], objective: float
) -> dict[str, Any]:
    sharpes = [float(item["metrics"]["net_sharpe"]) for item in fold_summaries]
    returns = [float(item["metrics"]["net_return"]) for item in fold_summaries]
    drawdowns = [float(item["metrics"]["max_drawdown"]) for item in fold_summaries]
    return {
        "objective": float(objective),
        "objective_definition": "median_net_sharpe_2x_cost_minus_half_iqr",
        "median_net_sharpe_2x_cost": median(sharpes),
        "net_sharpe_iqr_2x_cost": _percentile(sharpes, 0.75)
        - _percentile(sharpes, 0.25),
        "median_net_return_2x_cost": median(returns),
        "positive_fold_ratio": sum(value > 0.0 for value in returns) / len(returns),
        "worst_max_drawdown": max(drawdowns),
        "folds": list(fold_summaries),
    }


def _acceptance_gates(
    *,
    development: Mapping[str, Any],
    holdout: Mapping[str, Any],
    holdout_error: str | None,
    holdout_constraints: bool,
    positive_fold_ratio: float,
    stressed_fields: Sequence[str],
    final_replay_error: str | None,
) -> dict[str, bool]:
    return {
        "chronological_unshuffled_prefix_replay": True,
        "all_development_fold_constraints": True,
        "development_objective_positive": float(development["objective"]) > 0.0,
        "development_median_net_return_positive": float(
            development["median_net_return_2x_cost"]
        )
        > 0.0,
        "development_positive_fold_ratio": float(development["positive_fold_ratio"])
        >= positive_fold_ratio,
        "cost_stress_applied": bool(stressed_fields),
        "holdout_replay_succeeded": holdout_error is None,
        "holdout_constraints": holdout_constraints,
        "holdout_net_return_positive_2x_cost": (
            holdout.get("net_return") is not None and float(holdout["net_return"]) > 0.0
        ),
        "holdout_net_sharpe_positive_2x_cost": (
            holdout.get("net_sharpe") is not None and float(holdout["net_sharpe"]) > 0.0
        ),
        "final_replay_succeeded": final_replay_error is None,
    }


def _trial_summary(
    candidates: Sequence[Mapping[str, Any]],
    *,
    registry: Path,
    registry_hashes: Sequence[str],
    fold_evaluations: int,
    replay_failures: int,
) -> dict[str, Any]:
    ranked = sorted(
        candidates,
        key=lambda item: (
            item.get("objective") is None,
            -float(item["objective"]) if item.get("objective") is not None else 0.0,
            str(item["config_hash"]),
        ),
    )
    return {
        "candidate_count": len(candidates),
        "fold_evaluations": fold_evaluations,
        "eligible_candidate_count": sum(bool(item["eligible"]) for item in candidates),
        "replay_failures": replay_failures,
        "registry_path": str(registry),
        "registry_record_hashes": list(registry_hashes),
        "candidates": list(ranked),
    }


def _insufficient_result(
    base: dict[str, Any], registry: Path, reason: str
) -> dict[str, Any]:
    record_hash = _append_registry(
        registry,
        {
            "schema_version": 1,
            "optimizer_version": OPTIMIZER_VERSION,
            "event": "insufficient_evidence",
            "asset": base["asset"],
            "timeframe": base["timeframe"],
            "reason": reason,
        },
    )
    base["status"] = "insufficient_evidence"
    base["reason"] = reason
    base["trials"]["registry_record_hashes"] = [record_hash]
    return _json_safe(base)


def _append_registry(path: Path, record: Mapping[str, Any]) -> str:
    safe = _json_safe(dict(record))
    record_hash = _digest(safe)
    safe["record_hash"] = record_hash
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(safe, sort_keys=True, separators=(",", ":"), allow_nan=False)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return record_hash


def _digest(value: Any) -> str:
    encoded = json.dumps(
        _json_safe(value),
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, pl.DataFrame):
        return [_json_safe(row) for row in value.to_dicts()]
    if isinstance(value, pl.Series):
        return [_json_safe(item) for item in value.to_list()]
    if is_dataclass(value):
        return _json_safe(asdict(value))
    if hasattr(value, "as_dict") and callable(value.as_dict):
        return _json_safe(value.as_dict())
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [_json_safe(item) for item in value]
    return str(value)


def _as_datetime(value: Any) -> datetime:
    if not isinstance(value, datetime):
        raise ValueError("Replay timestamps must be datetimes")
    return value


def _parse_datetime(value: str | datetime | None) -> datetime | None:
    if value is None or value == "":
        return None
    parsed = (
        value
        if isinstance(value, datetime)
        else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    )
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


__all__ = [
    "DEFAULT_TRIAL_REGISTRY_PATH",
    "DISCLAIMER",
    "OPTIMIZER_VERSION",
    "optimize_indicator_strategy",
]
