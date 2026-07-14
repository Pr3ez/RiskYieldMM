"""Protected-trade and CUSUM meta-label foundations.

This package is intentionally isolated from replay and live execution.  Its
contracts can therefore be integrated into both paths without either path
silently defining different labels, feature order, or barrier semantics.
"""

from .contracts import (
    CONTRACT_SCHEMA_VERSION,
    BarrierConfig,
    BarrierOutcome,
    BarrierPlan,
    TradeSide,
    activate_barrier_plan,
)
from .features import (
    FEATURE_SCHEMA_VERSION,
    META_FEATURE_NAMES,
    FeatureSnapshot,
    build_feature_snapshot,
)
from .labeling import (
    LABEL_SCHEMA_VERSION,
    TRACKER_SCHEMA_VERSION,
    BarrierEvaluation,
    BarrierTracker,
    MinuteBar,
    cancel_barrier_plan,
    evaluate_barriers,
)
from .shadow import (
    EXECUTION_BAR_INTERVAL_SECONDS,
    SHADOW_CANDIDATE_SCHEMA_VERSION,
    SHADOW_RECORD_SCHEMA_VERSION,
    SHADOW_SCHEMA_VERSION,
    ShadowBookCapacityError,
    ShadowCandidate,
    ShadowEventBook,
    ShadowEventRecord,
    ShadowEventState,
    ShadowExecutionMinute,
    ShadowFill,
    ShadowGapPolicy,
)

__all__ = [
    "CONTRACT_SCHEMA_VERSION",
    "FEATURE_SCHEMA_VERSION",
    "LABEL_SCHEMA_VERSION",
    "TRACKER_SCHEMA_VERSION",
    "EXECUTION_BAR_INTERVAL_SECONDS",
    "META_FEATURE_NAMES",
    "SHADOW_CANDIDATE_SCHEMA_VERSION",
    "SHADOW_RECORD_SCHEMA_VERSION",
    "SHADOW_SCHEMA_VERSION",
    "BarrierConfig",
    "BarrierEvaluation",
    "BarrierOutcome",
    "BarrierPlan",
    "BarrierTracker",
    "FeatureSnapshot",
    "MinuteBar",
    "ShadowBookCapacityError",
    "ShadowCandidate",
    "ShadowEventBook",
    "ShadowEventRecord",
    "ShadowEventState",
    "ShadowExecutionMinute",
    "ShadowFill",
    "ShadowGapPolicy",
    "TradeSide",
    "activate_barrier_plan",
    "build_feature_snapshot",
    "cancel_barrier_plan",
    "evaluate_barriers",
]
