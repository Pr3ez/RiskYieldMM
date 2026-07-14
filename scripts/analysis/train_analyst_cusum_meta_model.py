#!/usr/bin/env python3
"""Train a candidate-only CUSUM TP-before-SL meta-label baseline.

The primary signal remains the Analyst CUSUM setup.  This command constructs
one immutable, decision-time feature row per fresh CUSUM setup, labels it only
after the protected target/stop/timeout question is known, and evaluates a
fixed L2-logistic baseline with strictly past, label-mature walk-forward folds.

Outputs are research candidates.  This command never changes environment
variables, promotes a model, enables a chart gate, or routes an order.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ANALYST_ROOT = PROJECT_ROOT / "Risk_Yield_Meta_Model_Analyst_0_0_1"
if str(ANALYST_ROOT) not in sys.path:
    sys.path.insert(0, str(ANALYST_ROOT))

from chart_config import CANONICAL_TIMEFRAMES, CORE_ASSETS  # noqa: E402
from minute_replay import (  # noqa: E402
    INGESTION_SAFETY_LAG_SECONDS,
    IndicatorStrategyConfig,
    ProtectedReplayConfig,
    ReplayCostConfig,
    load_canonical_minute_window,
    meta_label_policy_digest,
    run_minute_replay,
)
from trade_ml.artifact import (  # noqa: E402
    LogisticCoefficientArtifact,
    build_coefficient_artifact,
    write_artifact,
)
from trade_ml.contracts import (  # noqa: E402
    BarrierOutcome,
    as_utc_datetime,
    stable_digest,
)
from trade_ml.features import META_FEATURE_NAMES  # noqa: E402
from trade_ml.model import (  # noqa: E402
    LogisticBaselineConfig,
    WalkForwardEvaluation,
    evaluate_walk_forward,
    fit_logistic_baseline,
    probability_metrics,
)
from trade_ml.shadow import ShadowEventRecord, ShadowEventState  # noqa: E402
from trade_ml.splits import ExpandingWalkForwardConfig  # noqa: E402

REPORT_VERSION = "analyst_cusum_meta_candidate_training_v2"
DEFAULT_REPLAY_DAYS = 180
DEFAULT_EVENT_LIMIT = 100_000
DEFAULT_MIN_TRAIN_ROWS = 200
DEFAULT_VALIDATION_ROWS = 100
DEFAULT_DECISION_THRESHOLD = 0.50
DEFAULT_HISTORICAL_LABEL_EMBARGO_HOURS = 24.0
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "models" / "analyst_cusum_meta"
_MODEL_VERSION_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_TRAINABLE_OUTCOMES = frozenset(
    {
        BarrierOutcome.TARGET,
        BarrierOutcome.STOP,
        BarrierOutcome.TIMEOUT,
        BarrierOutcome.AMBIGUOUS,
    }
)


def _utc(value: datetime | str, *, name: str) -> datetime:
    return as_utc_datetime(value, name=name)


def _iso(value: datetime) -> str:
    return _utc(value, name="timestamp").isoformat().replace("+00:00", "Z")


def _json_safe(value: Any) -> Any:
    """Return a finite, plain-JSON copy or raise on an unsafe report value."""

    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("report contains a non-finite float")
        return float(value)
    if isinstance(value, datetime):
        return _iso(value)
    if isinstance(value, Mapping):
        output: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("report mapping keys must be strings")
            output[key] = _json_safe(item)
        return output
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return _json_safe(float(value))
    raise ValueError(f"unsupported report value: {type(value).__name__}")


@dataclass(frozen=True, slots=True)
class MetaTrainingRow:
    """One resolved setup whose features predate its mature barrier label."""

    asset: str
    timeframe: str
    event_id: str
    decision_at: datetime
    label_known_at: datetime
    outcome: BarrierOutcome
    economic_binary_target: int
    feature_values: tuple[float | None, ...]
    policy_digest: str

    def __post_init__(self) -> None:
        asset = str(self.asset).strip().upper()
        timeframe = str(self.timeframe).strip().lower()
        event_id = str(self.event_id).strip()
        policy_digest = str(self.policy_digest).strip()
        if not asset or not timeframe or not event_id:
            raise ValueError("training row identity fields must not be empty")
        if len(policy_digest) != 64 or any(
            character not in "0123456789abcdef" for character in policy_digest
        ):
            raise ValueError("policy_digest must be a lowercase SHA-256 digest")
        decision = _utc(self.decision_at, name="decision_at")
        label_known = _utc(self.label_known_at, name="label_known_at")
        if label_known < decision:
            raise ValueError("label_known_at cannot precede decision_at")
        outcome = (
            self.outcome
            if isinstance(self.outcome, BarrierOutcome)
            else BarrierOutcome(self.outcome)
        )
        if outcome not in _TRAINABLE_OUTCOMES:
            raise ValueError("training row outcome is not a trainable barrier result")
        if isinstance(self.economic_binary_target, bool) or (
            self.economic_binary_target not in (0, 1)
        ):
            raise ValueError("economic_binary_target must be binary")
        values = tuple(self.feature_values)
        if len(values) != len(META_FEATURE_NAMES):
            raise ValueError("feature_values do not match META_FEATURE_NAMES")
        normalized: list[float | None] = []
        for value in values:
            if value is None:
                normalized.append(None)
                continue
            if isinstance(value, bool):
                raise ValueError("feature values must be numeric or None")
            number = float(value)
            if not math.isfinite(number):
                raise ValueError("feature values must be finite or None")
            normalized.append(number)
        object.__setattr__(self, "asset", asset)
        object.__setattr__(self, "timeframe", timeframe)
        object.__setattr__(self, "event_id", event_id)
        object.__setattr__(self, "decision_at", decision)
        object.__setattr__(self, "label_known_at", label_known)
        object.__setattr__(self, "outcome", outcome)
        object.__setattr__(self, "feature_values", tuple(normalized))
        object.__setattr__(self, "policy_digest", policy_digest)


@dataclass(frozen=True, slots=True)
class ExtractedReplayRows:
    rows: tuple[MetaTrainingRow, ...]
    counts: dict[str, Any]


@dataclass(frozen=True, slots=True)
class CollectedDataset:
    rows: tuple[MetaTrainingRow, ...]
    policy_digest: str
    assets: tuple[str, ...]
    timeframes: tuple[str, ...]
    selection_reports: tuple[dict[str, Any], ...]
    counts: dict[str, Any]


@dataclass(frozen=True, slots=True)
class FittedCandidate:
    artifact: LogisticCoefficientArtifact
    evaluation: dict[str, Any]
    dataset: dict[str, Any]


def _book_counter(book: Mapping[str, Any], key: str) -> int:
    value = book.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"meta-label counter {key} must be a non-negative integer")
    return value


def extract_mature_replay_rows(
    replay: Mapping[str, Any],
    *,
    expected_asset: str,
    expected_timeframe: str,
    replay_clock: datetime | str,
) -> ExtractedReplayRows:
    """Validate and extract only fully retained, mature, economic labels."""

    asset = str(expected_asset).strip().upper()
    timeframe = str(expected_timeframe).strip().lower()
    clock = _utc(replay_clock, name="replay_clock")
    book = replay.get("meta_label_book")
    if not isinstance(book, Mapping):
        raise ValueError("protected replay did not return a meta_label_book")
    resolved_payload = book.get("resolved")
    if not isinstance(resolved_payload, list):
        raise ValueError("meta_label_book.resolved must be a list")

    truncated = _book_counter(book, "resolved_truncated_count")
    returned = _book_counter(book, "resolved_returned_count")
    total_resolved = _book_counter(book, "total_resolved")
    if truncated != 0:
        raise ValueError(
            "meta-label history was truncated; increase --event-limit before training"
        )
    if returned != len(resolved_payload) or total_resolved != len(resolved_payload):
        raise ValueError("meta-label retention counters disagree with resolved rows")

    rows: list[MetaTrainingRow] = []
    outcomes: Counter[str] = Counter()
    event_ids: set[str] = set()
    cancelled = 0
    for payload in resolved_payload:
        if not isinstance(payload, Mapping):
            raise ValueError("resolved meta-label record must be an object")
        record = ShadowEventRecord.from_dict(payload)
        if record.state is not ShadowEventState.RESOLVED:
            raise ValueError("meta-label dataset may contain only resolved records")
        candidate = record.candidate
        if candidate.asset != asset or candidate.timeframe != timeframe:
            raise ValueError("meta-label candidate scope disagrees with replay scope")
        if candidate.event_id in event_ids:
            raise ValueError("duplicate event_id in resolved meta-label history")
        event_ids.add(candidate.event_id)
        if record.outcome is None or record.label_known_at is None:
            raise ValueError("resolved record is missing its mature outcome clock")
        outcomes[record.outcome.value] += 1
        if record.label_known_at > clock:
            raise ValueError("resolved label was not known by the replay clock")
        if record.outcome is BarrierOutcome.CANCELLED:
            cancelled += 1
            if record.economic_binary_target is not None:
                raise ValueError("cancelled record must not carry a training target")
            continue
        if record.outcome not in _TRAINABLE_OUTCOMES:
            raise ValueError(f"unsupported trainable outcome: {record.outcome.value}")
        if record.economic_binary_target not in (0, 1):
            raise ValueError("resolved barrier record lacks an economic target")
        if candidate.features.feature_names != META_FEATURE_NAMES:
            raise ValueError(
                "resolved feature schema does not match META_FEATURE_NAMES"
            )
        rows.append(
            MetaTrainingRow(
                asset=candidate.asset,
                timeframe=candidate.timeframe,
                event_id=candidate.event_id,
                decision_at=candidate.decision_at,
                label_known_at=record.label_known_at,
                outcome=record.outcome,
                economic_binary_target=record.economic_binary_target,
                feature_values=candidate.features.values,
                policy_digest=candidate.policy_digest,
            )
        )

    raw_outcomes = book.get("outcome_counts")
    if not isinstance(raw_outcomes, Mapping):
        raise ValueError("meta-label outcome_counts must be an object")
    declared_outcomes = Counter()
    for outcome in BarrierOutcome:
        declared_outcomes[outcome.value] = _book_counter(raw_outcomes, outcome.value)
    if set(raw_outcomes) != {outcome.value for outcome in BarrierOutcome}:
        raise ValueError("meta-label outcome_counts keys are invalid")
    if declared_outcomes != outcomes:
        raise ValueError("meta-label outcome counters disagree with resolved rows")

    pending = _book_counter(book, "pending_count")
    active = _book_counter(book, "active_count")
    total_scheduled = _book_counter(book, "total_scheduled")
    if total_scheduled != total_resolved + pending + active:
        raise ValueError("meta-label scheduled/open/resolved counters are inconsistent")
    return ExtractedReplayRows(
        rows=tuple(rows),
        counts={
            "total_scheduled": total_scheduled,
            "total_resolved": total_resolved,
            "eligible_mature_rows": len(rows),
            "cancelled_excluded": cancelled,
            "pending_censored_excluded": pending,
            "active_censored_excluded": active,
            "outcome_counts": dict(sorted(outcomes.items())),
        },
    )


def _normalize_scope(
    values: Sequence[str], *, allowed: Sequence[str], field: str
) -> tuple[str, ...]:
    normalized_values = [
        str(value).strip().upper() if field == "assets" else str(value).strip().lower()
        for value in values
    ]
    if not normalized_values or any(not value for value in normalized_values):
        raise ValueError(f"{field} must not be empty")
    unknown = sorted(set(normalized_values) - set(allowed))
    if unknown:
        raise ValueError(f"unknown {field}: {', '.join(unknown)}")
    selected = set(normalized_values)
    return tuple(value for value in allowed if value in selected)


def collect_canonical_replay_rows(
    *,
    assets: Sequence[str],
    timeframes: Sequence[str],
    end: datetime | str,
    replay_days: int,
    strategy: IndicatorStrategyConfig,
    costs: ReplayCostConfig,
    protection: ProtectedReplayConfig,
    event_limit: int = DEFAULT_EVENT_LIMIT,
    min_rows_per_selection: int = 1,
    collection_clock: datetime | None = None,
    loader: Callable[..., tuple[pl.DataFrame, dict[str, Any]]] = (
        load_canonical_minute_window
    ),
    replayer: Callable[..., dict[str, Any]] = run_minute_replay,
    progress: Callable[[str], None] | None = None,
) -> CollectedDataset:
    """Replay every requested canonical matrix cell under one locked policy."""

    normalized_assets = _normalize_scope(assets, allowed=CORE_ASSETS, field="assets")
    normalized_timeframes = _normalize_scope(
        timeframes,
        allowed=CANONICAL_TIMEFRAMES,
        field="timeframes",
    )
    if (
        isinstance(replay_days, bool)
        or not isinstance(replay_days, int)
        or replay_days < 1
    ):
        raise ValueError("replay_days must be a positive integer")
    if (
        isinstance(event_limit, bool)
        or not isinstance(event_limit, int)
        or event_limit < 1
    ):
        raise ValueError("event_limit must be a positive integer")
    if (
        isinstance(min_rows_per_selection, bool)
        or not isinstance(min_rows_per_selection, int)
        or min_rows_per_selection < 0
    ):
        raise ValueError("min_rows_per_selection must be non-negative")
    if not protection.enabled:
        raise ValueError("candidate dataset collection requires protected replay")

    finished_at = _utc(end, name="end")
    started_at = finished_at - timedelta(days=replay_days)
    observed_now = _utc(
        collection_clock or datetime.now(timezone.utc), name="collection_clock"
    )
    safe_clock = observed_now - timedelta(seconds=INGESTION_SAFETY_LAG_SECONDS)
    if finished_at > safe_clock:
        raise ValueError("end must be no later than the safely closed collection clock")

    expected_policy_by_timeframe = {
        timeframe: meta_label_policy_digest(
            strategy=strategy,
            costs=costs,
            protection=protection,
            timeframe=timeframe,
        )
        for timeframe in normalized_timeframes
    }
    policy_digests = set(expected_policy_by_timeframe.values())
    if len(policy_digests) != 1:
        raise ValueError(
            "requested timeframes do not share one meta-label policy digest; "
            "pooling is forbidden"
        )
    policy_digest = next(iter(policy_digests))

    rows: list[MetaTrainingRow] = []
    selection_reports: list[dict[str, Any]] = []
    aggregate_counts: Counter[str] = Counter()
    aggregate_outcomes: Counter[str] = Counter()
    identities: set[tuple[str, str, str]] = set()
    for asset in normalized_assets:
        for timeframe in normalized_timeframes:
            if progress is not None:
                progress(f"collecting {asset}/{timeframe}")
            frame, source_metadata = loader(
                asset=asset,
                timeframe=timeframe,
                start=started_at,
                end=finished_at,
                replay_days=replay_days,
                now=observed_now,
            )
            replay = replayer(
                frame,
                asset=asset,
                timeframe=timeframe,
                strategy=strategy,
                costs=costs,
                protection=protection,
                meta_filter_mode="off",
                meta_artifact=None,
                evaluation_start=started_at,
                replay_clock=finished_at,
                event_limit=event_limit,
                capture_series=False,
            )
            replay_policy = (
                replay.get("config", {}).get("meta_filter", {}).get("policy_digest")
                if isinstance(replay.get("config"), Mapping)
                else None
            )
            expected_policy = expected_policy_by_timeframe[timeframe]
            if replay_policy != expected_policy:
                raise ValueError(f"{asset}/{timeframe} replay policy digest mismatch")
            extracted = extract_mature_replay_rows(
                replay,
                expected_asset=asset,
                expected_timeframe=timeframe,
                replay_clock=finished_at,
            )
            if progress is not None:
                progress(
                    f"resolved {asset}/{timeframe}: {len(extracted.rows)} mature rows"
                )
            if len(extracted.rows) < min_rows_per_selection:
                raise ValueError(
                    f"{asset}/{timeframe} produced {len(extracted.rows)} mature rows; "
                    f"minimum is {min_rows_per_selection}"
                )
            for row in extracted.rows:
                if row.policy_digest != policy_digest:
                    raise ValueError("candidate row policy digest changed within pool")
                identity = (row.asset, row.timeframe, row.event_id)
                if identity in identities:
                    raise ValueError(
                        "duplicate candidate identity across replay selections"
                    )
                identities.add(identity)
                rows.append(row)
            for key, value in extracted.counts.items():
                if key == "outcome_counts":
                    aggregate_outcomes.update(value)
                else:
                    aggregate_counts[key] += int(value)
            replay_metadata = replay.get("metadata")
            selection_reports.append(
                {
                    "asset": asset,
                    "timeframe": timeframe,
                    "policy_digest": expected_policy,
                    "counts": extracted.counts,
                    "source": _json_safe(source_metadata),
                    "replay_data_quality": (
                        {
                            key: replay_metadata.get(key)
                            for key in (
                                "input_source_rows",
                                "processed_real_source_minutes",
                                "excluded_synthetic_minutes",
                                "invalid_source_rows",
                                "continuous_source_gap_count",
                                "missing_continuous_source_minutes",
                                "unverified_session_source_gap_count",
                                "missing_unverified_session_source_minutes",
                                "suppressed_incomplete_target_bars",
                                "target_bar_completeness_counts",
                                "signal_vintage",
                                "as_was_live_journal",
                            )
                        }
                        if isinstance(replay_metadata, Mapping)
                        else None
                    ),
                }
            )

    ordered_rows = tuple(
        sorted(
            rows,
            key=lambda row: (
                row.decision_at,
                row.asset,
                row.timeframe,
                row.event_id,
            ),
        )
    )
    counts = dict(sorted(aggregate_counts.items()))
    counts["outcome_counts"] = dict(sorted(aggregate_outcomes.items()))
    counts["requested_selection_count"] = len(normalized_assets) * len(
        normalized_timeframes
    )
    counts["training_row_count"] = len(ordered_rows)
    return CollectedDataset(
        rows=ordered_rows,
        policy_digest=policy_digest,
        assets=normalized_assets,
        timeframes=normalized_timeframes,
        selection_reports=tuple(selection_reports),
        counts=counts,
    )


def _feature_matrix(rows: Sequence[MetaTrainingRow]) -> np.ndarray:
    return np.asarray(
        [
            [np.nan if value is None else value for value in row.feature_values]
            for row in rows
        ],
        dtype=float,
    )


def _fold_report(evaluation: WalkForwardEvaluation) -> list[dict[str, Any]]:
    return [
        {
            "fold_index": fold.fold_index,
            "status": fold.status,
            "reason": fold.reason,
            "train_rows": fold.train_rows,
            "validation_rows": fold.validation_rows,
            "training_positive_rows": fold.training_positive_rows,
            "training_prevalence": fold.training_prevalence,
            "validation_decision_start": _iso(fold.validation_decision_start),
            "validation_decision_end": _iso(fold.validation_decision_end),
            "training_label_known_through": _iso(fold.training_label_known_through),
            "metrics": fold.metrics,
            "causal_base_rate_metrics": fold.base_rate_metrics,
        }
        for fold in evaluation.fold_evaluations
    ]


def _is_positive(value: Any) -> bool:
    return value is not None and math.isfinite(float(value)) and float(value) > 0.0


def _subgroup_probability_reports(
    rows: Sequence[MetaTrainingRow],
    y: np.ndarray,
    evaluation: WalkForwardEvaluation,
) -> dict[str, dict[str, Any]]:
    """Report OOF quality by scope without fitting or tuning subgroup models."""

    model_probability = np.asarray(
        [
            np.nan if value is None else float(value)
            for value in evaluation.oof_probabilities
        ],
        dtype=float,
    )
    base_probability = np.asarray(
        [
            np.nan if value is None else float(value)
            for value in evaluation.oof_base_rate_probabilities
        ],
        dtype=float,
    )
    group_keys = {
        "asset": [row.asset for row in rows],
        "timeframe": [row.timeframe for row in rows],
        "selection": [f"{row.asset}/{row.timeframe}" for row in rows],
    }
    reports: dict[str, dict[str, Any]] = {}
    for dimension, values in group_keys.items():
        dimension_report: dict[str, Any] = {}
        for group in sorted(set(values)):
            indices = np.asarray(
                [
                    index
                    for index, value in enumerate(values)
                    if value == group and math.isfinite(model_probability[index])
                ],
                dtype=int,
            )
            if indices.size == 0:
                continue
            model_metrics = probability_metrics(y[indices], model_probability[indices])
            base_metrics = probability_metrics(y[indices], base_probability[indices])
            dimension_report[group] = {
                "model_metrics": model_metrics,
                "causal_base_rate_metrics": base_metrics,
                "brier_improvement_vs_causal_base_rate": (
                    float(base_metrics["brier"]) - float(model_metrics["brier"])
                ),
                "log_loss_improvement_vs_causal_base_rate": (
                    float(base_metrics["log_loss"]) - float(model_metrics["log_loss"])
                ),
            }
        reports[dimension] = dimension_report
    return reports


def fit_candidate_model(
    rows: Sequence[MetaTrainingRow],
    *,
    assets: Sequence[str],
    timeframes: Sequence[str],
    policy_digest: str,
    model_version: str,
    decision_threshold: float,
    split_config: ExpandingWalkForwardConfig,
    model_config: LogisticBaselineConfig | None = None,
    created_at: datetime | None = None,
    historical_label_embargo: timedelta = timedelta(
        hours=DEFAULT_HISTORICAL_LABEL_EMBARGO_HOURS
    ),
) -> FittedCandidate:
    """Evaluate out of sample, then fit one candidate on all mature rows."""

    ordered_rows = tuple(
        sorted(
            rows,
            key=lambda row: (
                row.decision_at,
                row.asset,
                row.timeframe,
                row.event_id,
            ),
        )
    )
    if not ordered_rows:
        raise ValueError("no mature meta-label rows are available")
    if any(row.policy_digest != policy_digest for row in ordered_rows):
        raise ValueError("training rows do not share the requested policy digest")
    asset_scope = {str(value).strip().upper() for value in assets}
    timeframe_scope = {str(value).strip().lower() for value in timeframes}
    if not asset_scope or not timeframe_scope:
        raise ValueError("artifact asset and timeframe scopes must not be empty")
    if any(
        row.asset not in asset_scope or row.timeframe not in timeframe_scope
        for row in ordered_rows
    ):
        raise ValueError("training row falls outside the requested artifact scope")
    if not _MODEL_VERSION_PATTERN.fullmatch(str(model_version)):
        raise ValueError("model_version is not a safe immutable filename component")
    if not math.isfinite(decision_threshold) or not 0.0 < decision_threshold < 1.0:
        raise ValueError("decision_threshold must be strictly within (0, 1)")
    identities = {(row.asset, row.timeframe, row.event_id) for row in ordered_rows}
    if len(identities) != len(ordered_rows):
        raise ValueError("duplicate training candidate identity")
    embargo_seconds = historical_label_embargo.total_seconds()
    if not math.isfinite(embargo_seconds) or embargo_seconds < 0.0:
        raise ValueError("historical_label_embargo must be finite and non-negative")

    X = _feature_matrix(ordered_rows)
    y = np.asarray([row.economic_binary_target for row in ordered_rows], dtype=int)
    decisions = [row.decision_at for row in ordered_rows]
    nominal_label_known = [row.label_known_at for row in ordered_rows]
    label_known = [value + historical_label_embargo for value in nominal_label_known]
    evaluation = evaluate_walk_forward(
        X,
        y,
        decisions,
        label_known,
        split_config=split_config,
        feature_names=META_FEATURE_NAMES,
        model_config=model_config,
    )
    fitted = fit_logistic_baseline(
        X,
        y,
        feature_names=META_FEATURE_NAMES,
        config=model_config,
    )
    controls = evaluation.controls
    research_gates = {
        "brier_improves_on_causal_base_rate": _is_positive(
            controls.get("brier_improvement_vs_causal_base_rate")
        ),
        "log_loss_improves_on_causal_base_rate": _is_positive(
            controls.get("log_loss_improvement_vs_causal_base_rate")
        ),
        "pr_auc_exceeds_oof_prevalence": _is_positive(
            controls.get("pr_auc_lift_over_prevalence")
        )
        and float(controls["pr_auc_lift_over_prevalence"]) > 1.0,
    }
    research_gates["all_probability_gates_pass"] = all(research_gates.values())
    evaluation_report = {
        "method": "strict_nominal_label_clock_plus_embargo_expanding_walk_forward",
        "split_config": {
            "min_train_rows": split_config.min_train_rows,
            "validation_rows": split_config.validation_rows,
            "step_rows": split_config.resolved_step_rows,
            "drop_incomplete_validation": split_config.drop_incomplete_validation,
            "historical_label_maturity_embargo_seconds": embargo_seconds,
        },
        "model_metrics": evaluation.metrics,
        "causal_base_rate_metrics": evaluation.base_rate_metrics,
        "controls": controls,
        "research_gates": research_gates,
        "subgroups": _subgroup_probability_reports(
            ordered_rows,
            y,
            evaluation,
        ),
        "folds": _fold_report(evaluation),
        "threshold_role": "declared_runtime_candidate_not_tuned_on_oof",
        "calibration": "none_logistic_native_probability_candidate",
        "deployment_eligible": False,
    }
    outcome_counts = Counter(row.outcome.value for row in ordered_rows)
    per_selection = Counter((row.asset, row.timeframe) for row in ordered_rows)
    dataset_report = {
        "rows": len(ordered_rows),
        "positive_rows": int(np.sum(y)),
        "positive_rate": float(np.mean(y)),
        "decision_first": _iso(min(decisions)),
        "decision_last": _iso(max(decisions)),
        "nominal_label_known_last": _iso(max(nominal_label_known)),
        "embargoed_label_mature_last": _iso(max(label_known)),
        "outcome_counts": dict(sorted(outcome_counts.items())),
        "rows_by_selection": {
            f"{asset}/{timeframe}": count
            for (asset, timeframe), count in sorted(per_selection.items())
        },
        "feature_names": list(META_FEATURE_NAMES),
        "policy_digest": policy_digest,
    }
    creation = _utc(created_at or datetime.now(timezone.utc), name="created_at")
    if creation < max(label_known):
        raise ValueError("created_at cannot precede the latest mature label")
    artifact_walk_forward = {
        key: value for key, value in evaluation_report.items() if key != "folds"
    }
    artifact_walk_forward["fold_count"] = len(evaluation_report["folds"])
    artifact_walk_forward["fitted_fold_count"] = sum(
        fold["status"] == "fitted" for fold in evaluation_report["folds"]
    )
    artifact = build_coefficient_artifact(
        fitted,
        model_version=model_version,
        policy_digest=policy_digest,
        assets=assets,
        timeframes=timeframes,
        trained_through=max(decisions),
        label_mature_through=max(label_known),
        decision_threshold=decision_threshold,
        evaluation_metrics={
            "report_version": REPORT_VERSION,
            "walk_forward": artifact_walk_forward,
            "dataset": dataset_report,
            "candidate_only": True,
            "auto_promoted": False,
            "deployment_scope": {"eligible_selections": []},
        },
        created_at=creation,
    )
    return FittedCandidate(
        artifact=artifact,
        evaluation=evaluation_report,
        dataset=dataset_report,
    )


def build_training_report(
    *,
    collected: CollectedDataset,
    fitted: FittedCandidate,
    strategy: IndicatorStrategyConfig,
    costs: ReplayCostConfig,
    protection: ProtectedReplayConfig,
    evaluation_start: datetime,
    evaluation_end: datetime,
    artifact_path: Path,
) -> dict[str, Any]:
    """Build the durable JSON report accompanying one immutable candidate."""

    protocol = {
        "report_version": REPORT_VERSION,
        "evaluation_start": _iso(evaluation_start),
        "evaluation_end": _iso(evaluation_end),
        "assets": list(collected.assets),
        "timeframes": list(collected.timeframes),
        "strategy": strategy.as_dict(),
        "strategy_digest": strategy.digest(),
        "costs": costs.as_dict(),
        "cost_digest": costs.digest(),
        "protected_bracket": protection.as_dict(),
        "protected_bracket_digest": protection.digest(),
        "meta_label_policy_digest": collected.policy_digest,
        "source": "canonical_1m_current_revision",
        "meta_filter_mode_during_collection": "off",
        "feature_sampling": "fresh_cusum_setup_decision_time_only",
        "label_sampling": "resolved_target_stop_timeout_ambiguous_only",
        "label_clock": ("canonical_nominal_bar_close_plus_fixed_5_second_scenario"),
        "historical_label_maturity_embargo_seconds": fitted.evaluation["split_config"][
            "historical_label_maturity_embargo_seconds"
        ],
        "deployment_label_clock": "journaled_actual_first_seen_at_required",
        "timeout_clock": "accepted_finalized_selected_timeframe_bars",
        "cost_accounting": "adverse_entry_embedded_once_then_nonembedded_costs",
        "protected_position_ownership": "immutable_bracket_until_terminal",
        "cancelled_and_open_events": "excluded_and_counted",
    }
    protocol["protocol_digest"] = stable_digest(protocol)
    report = {
        "report_version": REPORT_VERSION,
        "created_at": _iso(fitted.artifact.created_at),
        "status": "CANDIDATE_ONLY_NOT_PROMOTED",
        "protocol": protocol,
        "collection": {
            "counts": collected.counts,
            "selections": list(collected.selection_reports),
        },
        "training_dataset": fitted.dataset,
        "walk_forward_evaluation": fitted.evaluation,
        "artifact": {
            "path": str(artifact_path),
            "model_version": fitted.artifact.model_version,
            "checksum": fitted.artifact.checksum,
            "scope_digest": fitted.artifact.scope_digest,
            "decision_threshold": fitted.artifact.decision_threshold,
            "training_rows": fitted.artifact.training_rows,
            "positive_rows": fitted.artifact.positive_rows,
        },
        "deployment": {
            "auto_promoted": False,
            "environment_variable_changed": False,
            "chart_gate_enabled": False,
            "live_order_routing_enabled": False,
            "next_allowed_stage": "explicit_offline_review_then_live_shadow_only",
        },
        "limitations": [
            "No profitability claim or guarantee is made.",
            "Current canonical files lack first-seen and revision timestamps, so this is not an as-was-live historical dataset.",
            "Historical label maturity uses a declared nominal-close-plus-5-second scenario followed by a conservative research embargo; it is not actual first-seen evidence.",
            "The normalized cost proxy omits complete instrument-specific funding, rolls, multipliers, spread history and market impact.",
            "The decision threshold is declared, not optimized on these OOF predictions.",
            "The logistic probability is not separately calibrated; calibration requires later strictly held-out data.",
            "This pooled numeric baseline has no asset/timeframe categorical encoding or cross-timeframe concurrency/uniqueness weights; subgroup and overlap ablations remain required.",
            "No nonlinear comparison, untouched final holdout, or delayed live-shadow performance gate is included in this candidate artifact.",
        ],
    }
    return _json_safe(report)


def render_markdown_report(report: Mapping[str, Any]) -> str:
    evaluation = report["walk_forward_evaluation"]
    model = evaluation["model_metrics"]
    base = evaluation["causal_base_rate_metrics"]
    controls = evaluation["controls"]
    artifact = report["artifact"]
    dataset = report["training_dataset"]
    gates = evaluation["research_gates"]

    def metric(value: Any) -> str:
        return "n/a" if value is None else f"{float(value):.6f}"

    lines = [
        "# Analyst CUSUM meta-label candidate",
        "",
        f"Status: **{report['status']}**",
        "",
        "This artifact is an offline research candidate. It was not promoted and cannot enable live order routing by itself.",
        "",
        "## Dataset",
        "",
        f"- Mature rows: {dataset['rows']}",
        f"- Economic targets: {dataset['positive_rows']} ({dataset['positive_rate']:.4f})",
        f"- Decision range: {dataset['decision_first']} to {dataset['decision_last']}",
        f"- Latest nominal label observation: {dataset['nominal_label_known_last']}",
        f"- Latest embargoed research maturity: {dataset['embargoed_label_mature_last']}",
        f"- Policy digest: `{dataset['policy_digest']}`",
        "",
        "## Strict walk-forward probability evaluation",
        "",
        "| Metric | Logistic | Causal train-prevalence baseline |",
        "|---|---:|---:|",
        f"| Brier | {metric(model['brier'])} | {metric(base['brier'])} |",
        f"| Log loss | {metric(model['log_loss'])} | {metric(base['log_loss'])} |",
        f"| PR-AUC | {metric(model['pr_auc'])} | {metric(base['pr_auc'])} |",
        "",
        f"Scored rows: {controls['scored_rows']} across {controls['fitted_folds']} fitted folds.",
        f"All descriptive probability gates pass: **{gates['all_probability_gates_pass']}**. This is not a deployment gate.",
        "",
        "## Candidate artifact",
        "",
        f"- Model version: `{artifact['model_version']}`",
        f"- Path: `{artifact['path']}`",
        f"- Checksum: `{artifact['checksum']}`",
        f"- Declared threshold: {artifact['decision_threshold']:.4f}",
        "",
        "## Required next stage",
        "",
        "Review the OOF controls and selection coverage, then explicitly opt into live shadow scoring. Keep order routing and gating off until a forward-paper sample is label-mature and reviewed.",
        "",
        "## Limitations",
        "",
        *[f"- {item}" for item in report["limitations"]],
        "",
    ]
    return "\n".join(lines)


def _write_immutable_text(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            descriptor = -1
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        if descriptor >= 0:
            os.close(descriptor)
        path.unlink(missing_ok=True)
        raise
    return path


def persist_candidate_outputs(
    *,
    output_dir: Path,
    fitted: FittedCandidate,
    report_builder: Callable[[Path], dict[str, Any]],
) -> dict[str, Path]:
    """Create immutable artifact, JSON report, and Markdown report paths."""

    version = fitted.artifact.model_version
    if not _MODEL_VERSION_PATTERN.fullmatch(version):
        raise ValueError("unsafe model_version")
    artifact_path = output_dir / f"{version}.artifact.json"
    json_path = output_dir / f"{version}.report.json"
    markdown_path = output_dir / f"{version}.report.md"
    for path in (artifact_path, json_path, markdown_path):
        if path.exists() or path.is_symlink():
            raise FileExistsError(f"refusing to replace immutable output: {path}")
    report = report_builder(artifact_path)
    encoded = json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n"
    markdown = render_markdown_report(report)
    write_artifact(artifact_path, fitted.artifact)
    _write_immutable_text(json_path, encoded)
    _write_immutable_text(markdown_path, markdown)
    return {
        "artifact": artifact_path,
        "json_report": json_path,
        "markdown_report": markdown_path,
    }


def _parse_datetime(raw: str) -> datetime:
    try:
        return _utc(raw, name="end")
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _default_model_version(now: datetime | None = None) -> str:
    timestamp = _utc(now or datetime.now(timezone.utc), name="now")
    return f"cusum-meta-logistic-{timestamp.strftime('%Y%m%dT%H%M%SZ')}"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--end",
        type=_parse_datetime,
        required=True,
        help="Fixed UTC replay end (required for a reproducible dataset).",
    )
    parser.add_argument("--replay-days", type=int, default=DEFAULT_REPLAY_DAYS)
    parser.add_argument("--assets", nargs="+", default=list(CORE_ASSETS))
    parser.add_argument("--timeframes", nargs="+", default=list(CANONICAL_TIMEFRAMES))
    parser.add_argument("--event-limit", type=int, default=DEFAULT_EVENT_LIMIT)
    parser.add_argument("--min-rows-per-selection", type=int, default=1)
    parser.add_argument("--min-train-rows", type=int, default=DEFAULT_MIN_TRAIN_ROWS)
    parser.add_argument("--validation-rows", type=int, default=DEFAULT_VALIDATION_ROWS)
    parser.add_argument("--step-rows", type=int)
    parser.add_argument("--include-incomplete-validation", action="store_true")
    parser.add_argument(
        "--historical-label-embargo-hours",
        type=float,
        default=DEFAULT_HISTORICAL_LABEL_EMBARGO_HOURS,
        help=(
            "Research-only delay added to nominal canonical label maturity; "
            "journaled first_seen_at remains mandatory for deployment evidence."
        ),
    )
    parser.add_argument(
        "--decision-threshold", type=float, default=DEFAULT_DECISION_THRESHOLD
    )
    parser.add_argument("--logistic-c", type=float, default=1.0)
    parser.add_argument("--logistic-max-iter", type=int, default=2_000)
    parser.add_argument("--fee-bps", type=float, default=1.0)
    parser.add_argument("--slippage-bps", type=float, default=1.0)
    parser.add_argument("--spread-bps", type=float, default=0.0)
    parser.add_argument("--execution-latency-minutes", type=int, default=1)
    parser.add_argument("--risk-volatility-multiplier", type=float, default=2.0)
    parser.add_argument("--stop-risk-units", type=float, default=1.0)
    parser.add_argument("--target-risk-units", type=float, default=2.0)
    parser.add_argument("--timeout-target-bars", type=int, default=20)
    parser.add_argument("--break-even-safety-margin", type=float, default=0.05)
    parser.add_argument("--model-version")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    run_started_at = datetime.now(timezone.utc)
    model_version = args.model_version or _default_model_version(run_started_at)
    strategy = IndicatorStrategyConfig()
    costs = ReplayCostConfig(
        fee_bps=args.fee_bps,
        slippage_bps=args.slippage_bps,
        spread_bps=args.spread_bps,
        execution_latency_minutes=args.execution_latency_minutes,
    )
    protection = ProtectedReplayConfig(
        enabled=True,
        risk_unit_volatility_multiplier=args.risk_volatility_multiplier,
        stop_risk_units=args.stop_risk_units,
        target_risk_units=args.target_risk_units,
        timeout_target_bars=args.timeout_target_bars,
        break_even_safety_margin=args.break_even_safety_margin,
    )
    split_config = ExpandingWalkForwardConfig(
        min_train_rows=args.min_train_rows,
        validation_rows=args.validation_rows,
        step_rows=args.step_rows,
        drop_incomplete_validation=not args.include_incomplete_validation,
    )
    model_config = LogisticBaselineConfig(
        C=args.logistic_c,
        max_iter=args.logistic_max_iter,
    )
    collected = collect_canonical_replay_rows(
        assets=args.assets,
        timeframes=args.timeframes,
        end=args.end,
        replay_days=args.replay_days,
        strategy=strategy,
        costs=costs,
        protection=protection,
        event_limit=args.event_limit,
        min_rows_per_selection=args.min_rows_per_selection,
        collection_clock=run_started_at,
        progress=lambda message: print(message, file=sys.stderr, flush=True),
    )
    fitted = fit_candidate_model(
        collected.rows,
        assets=collected.assets,
        timeframes=collected.timeframes,
        policy_digest=collected.policy_digest,
        model_version=model_version,
        decision_threshold=args.decision_threshold,
        split_config=split_config,
        model_config=model_config,
        created_at=datetime.now(timezone.utc),
        historical_label_embargo=timedelta(hours=args.historical_label_embargo_hours),
    )
    evaluation_start = _utc(args.end, name="end") - timedelta(days=args.replay_days)
    outputs = persist_candidate_outputs(
        output_dir=args.output_dir,
        fitted=fitted,
        report_builder=lambda artifact_path: build_training_report(
            collected=collected,
            fitted=fitted,
            strategy=strategy,
            costs=costs,
            protection=protection,
            evaluation_start=evaluation_start,
            evaluation_end=_utc(args.end, name="end"),
            artifact_path=artifact_path,
        ),
    )
    summary = {
        "status": "CANDIDATE_ONLY_NOT_PROMOTED",
        "training_rows": fitted.artifact.training_rows,
        "positive_rows": fitted.artifact.positive_rows,
        "oof_metrics": fitted.evaluation["model_metrics"],
        "causal_base_rate_metrics": fitted.evaluation["causal_base_rate_metrics"],
        "research_gates": fitted.evaluation["research_gates"],
        "outputs": {key: str(value) for key, value in outputs.items()},
        "live_order_routing_enabled": False,
    }
    print(json.dumps(summary, indent=2, allow_nan=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
