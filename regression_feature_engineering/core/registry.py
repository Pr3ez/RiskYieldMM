"""Feature registry contracts for future regression features."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FeatureDefinition:
    """Metadata that every promoted regression feature must provide."""

    name: str
    family: str
    target_intent: tuple[str, ...]
    source_timeframes: tuple[str, ...]
    source_columns: tuple[str, ...]
    availability: str
    normalization: str


@dataclass(frozen=True)
class FeatureFamilyDefinition:
    """Formula-free implementation contract for one feature family."""

    family_id: str
    phase: int
    title: str
    status: str
    source_inputs: tuple[str, ...]
    availability_rule: str
    output_prefix: str
    target_intent: tuple[str, ...]
    validation_focus: tuple[str, ...]


FEATURE_FAMILIES: tuple[str, ...] = (
    "foundation_alignment",
    "volatility_state",
    "structural_room",
    "acceptance_persistence",
    "temporal_memory_transforms",
    "rejection_chop",
    "spike_breakout",
    "liquidity_volume_pressure",
    "regime_calendar_state",
    "interaction_confluence",
    "cross_asset_context",
    "unsupervised_factor_layer",
    "sequence_embedding_layer",
)


FEATURE_FAMILY_REGISTRY: tuple[FeatureFamilyDefinition, ...] = (
    FeatureFamilyDefinition(
        family_id="foundation_alignment",
        phase=1,
        title="Foundation And Alignment",
        status="engineering_validated",
        source_inputs=("canonical_ohlcv", "regression_labels"),
        availability_rule="closed_bar_asof_only",
        output_prefix="rpf_align_",
        target_intent=("alignment", "temporal_safety", "safe_math"),
        validation_focus=("asof_availability", "row_authority", "no_model_features"),
    ),
    FeatureFamilyDefinition(
        family_id="volatility_state",
        phase=2,
        title="Volatility State",
        status="engineering_validated_not_promoted",
        source_inputs=("canonical_ohlcv", "regression_labels"),
        availability_rule="closed_bar_asof_only",
        output_prefix="rpf_vol_",
        target_intent=("all_targets", "denominator_quality", "range_expansion"),
        validation_focus=("target_scale", "tail_quantiles", "chronological_stability"),
    ),
    FeatureFamilyDefinition(
        family_id="structural_room",
        phase=3,
        title="Structural Room",
        status="engineering_validated_not_promoted",
        source_inputs=("canonical_ohlcv",),
        availability_rule="previous_closed_levels_only",
        output_prefix="rpf_room_",
        target_intent=("up_extreme", "down_extreme", "room_asymmetry"),
        validation_focus=("previous_level_usage", "extreme_target_relationship"),
    ),
    FeatureFamilyDefinition(
        family_id="acceptance_persistence",
        phase=4,
        title="Acceptance And Persistence",
        status="engineering_validated_not_promoted",
        source_inputs=("canonical_ohlcv", "ta_flags_optional"),
        availability_rule="closed_bar_asof_only",
        output_prefix="rpf_accept_",
        target_intent=("up_mean_high", "down_mean_low", "accepted_path_pressure"),
        validation_focus=("mean_target_relationship", "persistence_vs_spike"),
    ),
    FeatureFamilyDefinition(
        family_id="temporal_memory_transforms",
        phase=5,
        title="Temporal Memory Transforms",
        status="engineering_validated_not_promoted",
        source_inputs=("validated_regression_features", "canonical_ohlcv"),
        availability_rule="prior_rows_only_or_closed_bar_asof_only",
        output_prefix="rpf_mem_",
        target_intent=("lags", "ewm_state", "slope", "percentile_rank"),
        validation_focus=("past_only_windows", "non_duplicate_signal", "chronological_stability"),
    ),
    FeatureFamilyDefinition(
        family_id="rejection_chop",
        phase=6,
        title="Rejection And Chop",
        status="engineering_validated_not_promoted",
        source_inputs=("canonical_ohlcv",),
        availability_rule="closed_bar_asof_only",
        output_prefix="rpf_chop_",
        target_intent=("rejection", "two_sided_path_risk", "persistence_suppression"),
        validation_focus=("extreme_vs_mean_separation", "non_duplicate_signal"),
    ),
    FeatureFamilyDefinition(
        family_id="spike_breakout",
        phase=7,
        title="Spike And Breakout",
        status="engineering_validated_not_promoted",
        source_inputs=("canonical_ohlcv", "ta_flags_optional"),
        availability_rule="previous_closed_levels_only",
        output_prefix="rpf_spike_",
        target_intent=("up_extreme", "down_extreme", "tail_reach"),
        validation_focus=("tail_ranking", "breakout_temporal_safety"),
    ),
    FeatureFamilyDefinition(
        family_id="liquidity_volume_pressure",
        phase=8,
        title="Liquidity And Volume Pressure",
        status="engineering_validated_not_promoted",
        source_inputs=("canonical_ohlcv",),
        availability_rule="closed_bar_asof_only",
        output_prefix="rpf_liq_",
        target_intent=("impulse_confirmation", "participation", "volume_pressure"),
        validation_focus=("volume_null_safety", "session_asset_behavior"),
    ),
    FeatureFamilyDefinition(
        family_id="regime_calendar_state",
        phase=9,
        title="Regime Calendar State",
        status="engineering_validated_not_promoted",
        source_inputs=("canonical_calendar_metadata", "canonical_ohlcv"),
        availability_rule="known_at_prediction_time",
        output_prefix="rpf_regime_",
        target_intent=("volatility_regime", "trend_range_regime", "session_state"),
        validation_focus=("session_asset_behavior", "calendar_known_in_advance", "regime_ablation"),
    ),
    FeatureFamilyDefinition(
        family_id="interaction_confluence",
        phase=10,
        title="Interaction And Confluence",
        status="engineering_validated_not_promoted",
        source_inputs=("validated_regression_features", "ta_flags_optional"),
        availability_rule="derived_from_causal_inputs_only",
        output_prefix="rpf_conf_",
        target_intent=("feature_interactions", "signal_confluence", "conditional_context"),
        validation_focus=("interaction_value_over_components", "sparsity", "no_future_diagnostics"),
    ),
    FeatureFamilyDefinition(
        family_id="cross_asset_context",
        phase=11,
        title="Cross-Asset Context",
        status="engineering_validated_not_promoted",
        source_inputs=("canonical_ohlcv", "context_assets"),
        availability_rule="exact_timestamp_or_closed_bar_asof_only",
        output_prefix="rpf_xasset_",
        target_intent=("relative_pressure", "risk_context", "common_volatility"),
        validation_focus=("no_raw_foreign_prices", "context_availability", "ablation_by_pair"),
    ),
    FeatureFamilyDefinition(
        family_id="unsupervised_factor_layer",
        phase=12,
        title="Unsupervised Factor Layer",
        status="engineering_validated_not_promoted",
        source_inputs=("validated_regression_features",),
        availability_rule="train_window_only_fit_or_prior_rolling_fit",
        output_prefix="rpf_factor_",
        target_intent=("derived_context", "path_regime", "anomaly_state"),
        validation_focus=("train_only_fit", "factor_stability", "no_label_authority"),
    ),
    FeatureFamilyDefinition(
        family_id="sequence_embedding_layer",
        phase=13,
        title="Sequence Embedding Layer",
        status="engineering_validated_not_promoted",
        source_inputs=("validated_regression_features", "canonical_ohlcv"),
        availability_rule="train_window_only_fit_or_prior_window_encoder",
        output_prefix="rpf_seq_",
        target_intent=("sequence_shape", "local_path_embedding", "cnn_or_encoder_context"),
        validation_focus=("train_only_fit", "embedding_stability", "walkforward_ablation"),
    ),
)


def feature_family_registry() -> tuple[FeatureFamilyDefinition, ...]:
    """Return the formula-free feature family implementation registry."""

    return FEATURE_FAMILY_REGISTRY
