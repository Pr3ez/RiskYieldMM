"""Leakage-safe event-time expanding walk-forward splits.

The splitter works with the two clocks that matter for meta-label training:

``decision_ts``
    When the feature snapshot and proposed trade were available.
``label_known_ts``
    When the target/stop/timeout outcome became observable.

A row is eligible for a fold's training set only when both its decision and its
label are strictly earlier than the first validation decision.  Validation
blocks are grouped by decision timestamp so simultaneous events across assets
cannot leak into one another through an arbitrary input ordering.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone

TimestampLike = datetime | str


@dataclass(frozen=True)
class ExpandingWalkForwardConfig:
    """Geometry for non-overlapping, expanding validation windows."""

    min_train_rows: int
    validation_rows: int
    step_rows: int | None = None
    drop_incomplete_validation: bool = True

    def __post_init__(self) -> None:
        if int(self.min_train_rows) < 1:
            raise ValueError("min_train_rows must be at least 1")
        if int(self.validation_rows) < 1:
            raise ValueError("validation_rows must be at least 1")
        step_rows = self.validation_rows if self.step_rows is None else self.step_rows
        if int(step_rows) < int(self.validation_rows):
            raise ValueError(
                "step_rows must be at least validation_rows so OOF windows do not overlap"
            )

    @property
    def resolved_step_rows(self) -> int:
        return int(self.validation_rows if self.step_rows is None else self.step_rows)


@dataclass(frozen=True)
class WalkForwardFold:
    """Original-row indices and observable-time boundaries for one fold."""

    fold_index: int
    train_indices: tuple[int, ...]
    validation_indices: tuple[int, ...]
    validation_decision_start: datetime
    validation_decision_end: datetime
    training_decision_through: datetime
    training_label_known_through: datetime


def build_expanding_walk_forward(
    decision_times: Sequence[TimestampLike],
    label_known_times: Sequence[TimestampLike],
    *,
    config: ExpandingWalkForwardConfig,
) -> tuple[WalkForwardFold, ...]:
    """Build strictly past-only folds using original input row indices.

    Training sets expand as validation time advances.  Rows whose label has not
    matured strictly before a validation block begins are purged from that
    fold.  No row at or after the validation decision time can enter training.
    """

    if len(decision_times) != len(label_known_times):
        raise ValueError("decision_times and label_known_times must have equal length")
    if len(decision_times) == 0:
        return ()

    decisions = tuple(
        _as_utc_timestamp(value, field="decision_ts") for value in decision_times
    )
    label_known = tuple(
        _as_utc_timestamp(value, field="label_known_ts") for value in label_known_times
    )
    for row_index, (decision_ts, known_ts) in enumerate(
        zip(decisions, label_known, strict=True)
    ):
        if known_ts < decision_ts:
            raise ValueError(
                f"label_known_ts cannot precede decision_ts (row_index={row_index})"
            )

    ordered_indices = tuple(
        sorted(range(len(decisions)), key=lambda idx: (decisions[idx], idx))
    )
    groups = _decision_groups(ordered_indices, decisions)
    folds: list[WalkForwardFold] = []
    validation_group_index = 0

    while validation_group_index < len(groups):
        validation_start = groups[validation_group_index][0]
        train_indices = tuple(
            idx
            for idx in ordered_indices
            if decisions[idx] < validation_start and label_known[idx] < validation_start
        )
        if len(train_indices) < int(config.min_train_rows):
            validation_group_index += 1
            continue

        validation_group_end = _group_end_for_minimum_rows(
            groups,
            start_group=validation_group_index,
            minimum_rows=int(config.validation_rows),
        )
        validation_indices = tuple(
            idx
            for _, group_indices in groups[validation_group_index:validation_group_end]
            for idx in group_indices
        )
        if (
            len(validation_indices) < int(config.validation_rows)
            and config.drop_incomplete_validation
        ):
            break
        if not validation_indices:
            break

        fold = WalkForwardFold(
            fold_index=len(folds),
            train_indices=train_indices,
            validation_indices=validation_indices,
            validation_decision_start=validation_start,
            validation_decision_end=max(decisions[idx] for idx in validation_indices),
            training_decision_through=max(decisions[idx] for idx in train_indices),
            training_label_known_through=max(label_known[idx] for idx in train_indices),
        )
        assert_fold_temporal_integrity(
            fold,
            decision_times=decisions,
            label_known_times=label_known,
        )
        folds.append(fold)

        validation_group_index = _group_end_for_minimum_rows(
            groups,
            start_group=validation_group_index,
            minimum_rows=config.resolved_step_rows,
        )

    return tuple(folds)


def assert_fold_temporal_integrity(
    fold: WalkForwardFold,
    *,
    decision_times: Sequence[TimestampLike],
    label_known_times: Sequence[TimestampLike],
) -> None:
    """Raise if a frozen fold violates decision-time or label-maturity rules."""

    decisions = tuple(
        _as_utc_timestamp(value, field="decision_ts") for value in decision_times
    )
    label_known = tuple(
        _as_utc_timestamp(value, field="label_known_ts") for value in label_known_times
    )
    if len(decisions) != len(label_known):
        raise ValueError("decision_times and label_known_times must have equal length")
    if not fold.train_indices or not fold.validation_indices:
        raise ValueError(
            "walk-forward folds require non-empty train and validation sets"
        )

    validation_start = min(decisions[idx] for idx in fold.validation_indices)
    if validation_start != fold.validation_decision_start:
        raise ValueError("validation_decision_start does not match validation indices")
    if any(decisions[idx] >= validation_start for idx in fold.train_indices):
        raise ValueError("training decision is not strictly before validation")
    if any(label_known[idx] >= validation_start for idx in fold.train_indices):
        raise ValueError("training label was not known strictly before validation")
    if set(fold.train_indices).intersection(fold.validation_indices):
        raise ValueError("training and validation indices overlap")


def _decision_groups(
    ordered_indices: Sequence[int],
    decisions: Sequence[datetime],
) -> tuple[tuple[datetime, tuple[int, ...]], ...]:
    groups: list[tuple[datetime, tuple[int, ...]]] = []
    current_time: datetime | None = None
    current_indices: list[int] = []
    for idx in ordered_indices:
        decision = decisions[idx]
        if current_time is None or decision == current_time:
            current_time = decision
            current_indices.append(idx)
            continue
        groups.append((current_time, tuple(current_indices)))
        current_time = decision
        current_indices = [idx]
    if current_time is not None:
        groups.append((current_time, tuple(current_indices)))
    return tuple(groups)


def _group_end_for_minimum_rows(
    groups: Sequence[tuple[datetime, tuple[int, ...]]],
    *,
    start_group: int,
    minimum_rows: int,
) -> int:
    row_count = 0
    group_index = int(start_group)
    while group_index < len(groups) and row_count < int(minimum_rows):
        row_count += len(groups[group_index][1])
        group_index += 1
    return group_index


def _as_utc_timestamp(value: TimestampLike, *, field: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        text = value.strip()
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError as exc:
            raise ValueError(f"{field} must be an ISO-8601 timestamp") from exc
    else:
        raise TypeError(f"{field} must be datetime or ISO-8601 string")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


__all__ = [
    "ExpandingWalkForwardConfig",
    "TimestampLike",
    "WalkForwardFold",
    "assert_fold_temporal_integrity",
    "build_expanding_walk_forward",
]
