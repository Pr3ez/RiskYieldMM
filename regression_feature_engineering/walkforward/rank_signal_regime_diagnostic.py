"""Regime and change-risk diagnostics for ranked-signal router runs.

This command is diagnostic-only.  It consumes completed ``rank_signal_router``
runs and builds prediction-time-safe regime context rows, past-only latent
state assignments, online change alarms, and post-hoc signal-quality summaries.

The intended use is to answer whether UP/DOWN ranker quality is conditional on
market/context regimes before wiring any regime logic into the live router.
Current prediction labels are never written into ``regime_context.parquet``.
They appear only in outcome/quality artifacts.
"""

from __future__ import annotations

import argparse
import bisect
import json
import math
import warnings
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl
from sklearn.decomposition import PCA
from sklearn.mixture import GaussianMixture
from sklearn.preprocessing import StandardScaler

from regression_feature_engineering.walkforward.ablation import FAMILY_PREFIXES
from regression_feature_engineering.walkforward.config import (
    DEFAULT_CONFIG_PATH,
    load_clean_config,
)
from regression_feature_engineering.walkforward.data import (
    available_batch_ids,
    resolve_context,
)
from regression_feature_engineering.walkforward.policy import load_panel_features
from regression_feature_engineering.walkforward.rank_signal import write_rows_parquet
from regression_feature_engineering.walkforward.rank_signal_transfer_diagnostic import (
    markdown_value,
)
from regression_feature_engineering.walkforward.reports import (
    append_event,
    write_json,
    write_stage_status,
)
from scripts.project_paths import ensure_project_root_on_path

PROJECT_ROOT = ensure_project_root_on_path(Path(__file__))
OUTPUT_ROOT = PROJECT_ROOT / "test_output" / "rpf_ranked_signal_regime_diagnostic"

SIDES = ("up", "down", "both")
PREDICTION_SOURCES = (
    "candidate_shadow",
    "router_selected",
    "row_rule_active",
    "effective_selected",
)
REGIME_CONTEXT_MODES = (
    "router_context",
    "market_context",
    "combined",
    "live_router_context",
    "live_combined",
)
HMM_SELECTION_MODES = ("fixed", "bic_v1")
HMM_FILTER_MODES = ("causal_forward_v1",)
CUSUM_STANDARDIZATIONS = ("rolling_robust_z_v1", "rolling_mean_std_v1")
CHANGE_FEATURE_SETS = ("auto", "router_context", "market_context", "combined")
CHANGE_DETECTOR_ALIASES = {
    "cusum": "market_context_zshift_v1",
}
CHANGE_DETECTORS = (
    "cusum",
    "market_context_zshift_v1",
    "market_context_recursive_cusum_v1",
    "hmm_transition_cusum_v1",
    "page_hinkley",
)
MARKET_CHANGE_DETECTORS = (
    "market_context_zshift_v1",
    "market_context_recursive_cusum_v1",
    "page_hinkley",
)
HMM_TRANSITION_DETECTOR = "hmm_transition_cusum_v1"
HMM_STATE_CHANGE_MARKER = "hmm_state_change_marker"
MARKET_CONTEXT_PREFIX = "market_"
DEFAULT_MARKET_REGIME_FAMILIES = (
    "volatility_state",
    "temporal_memory_transforms",
    "regime_calendar_state",
    "rejection_chop",
    "liquidity_volume_pressure",
    "structural_room",
)
MARKET_BATCH_METRICS = ("mean", "std", "abs_mean", "q10", "q50", "q90", "finite_rate")
MARKET_MODEL_METRICS = ("mean", "std", "abs_mean", "q10", "q50", "q90")
MARKET_MODEL_SUFFIXES = tuple(
    f"_{metric}_{suffix}"
    for metric in MARKET_MODEL_METRICS
    for suffix in ("last", "lookback_mean", "lookback_std", "last_z")
)
MARKET_CONTEXT_META_COLUMNS = {
    "market_context_lookback_batches",
    "market_context_include_current_batch",
    "market_context_history_batch_count",
    "market_context_last_batch_id",
}
MARKET_CONTEXT_META_TOKENS = (
    "_feature_count",
    "_row_count",
    "_batch_count",
    "_finite_rate",
)
REGIME_IDENTITY_COLUMNS = {
    "source_run",
    "source_idx",
    "window_end_offset_steps",
    "outer_window_count",
    "selection_mode",
    "candidate_set",
    "side",
    "candidate_name",
    "step_idx",
    "pred_batch_id",
}

CURRENT_OUTCOME_COLUMNS = {
    "rows",
    "positive_count",
    "negative_count",
    "predicted_positive_count",
    "true_positive_count",
    "false_positive_count",
    "false_negative_count",
    "true_negative_count",
    "precision",
    "recall",
    "false_positive_rate",
    "false_discovery_rate",
    "predicted_positive_rate",
    "base_positive_rate",
    "precision_lift",
    "decision_cost",
    "decision_cost_per_row",
    "decision_cost_per_signal",
    "positive_rate",
    "high_target_window",
    "active_window",
    "captured_high_target_window",
    "missed_high_target_window",
    "high_false_positive_window",
    "offline_topk_precision",
    "offline_topk_recall",
    "prediction_batch_positive_rate",
}

SAFE_NUMERIC_COLUMNS = (
    "candidate_passed_validation",
    "selected_feature_count",
    "threshold",
    "threshold_quantile",
    "max_signals_per_batch",
    "score_mean",
    "score_std",
    "validation_threshold_score",
    "batch_state_gate_probability",
    "batch_state_gate_passed",
    "batch_state_gate_prefix_rows",
    "validation_ranked_signal_quality",
    "validation_precision",
    "validation_precision_lift",
    "validation_false_discovery_rate",
    "validation_predicted_positive_count",
    "validation_active_window_rate",
    "validation_zero_signal_window_rate",
    "validation_batch_count",
    "validation_active_batch_count",
    "validation_lift_positive_batch_rate",
    "validation_median_active_precision_lift",
    "validation_median_active_false_discovery_rate",
    "validation_high_target_window_capture_rate",
    "validation_missed_high_target_window_rate",
    "sequence_feature_count",
    "reliability_score",
    "history_windows",
    "signal_count",
    "active_windows",
    "precision_lift_lcb",
    "precision_lcb",
    "selected_window_row_lift",
    "selected_window_row_lift_lcb",
    "selected_window_false_discovery_rate",
    "past_20_batch_positive_rate_mean",
    "past_20_batch_positive_rate_std",
    "past_60_batch_positive_rate_mean",
    "past_60_batch_positive_rate_std",
    "recent_candidate_precision_lift",
    "recent_candidate_precision_lift_lcb",
    "recent_candidate_window_selection_lift",
    "recent_candidate_selected_window_row_lift",
    "recent_candidate_selected_window_row_lift_lcb",
    "recent_candidate_false_discovery_rate",
    "current_validation_positive_rate",
    "current_validation_signal_rate",
)

# These fields are label-free, but they summarize the current prediction batch
# after it has been scored.  That is useful for diagnostics, but it is not
# available at the first live row of the batch, so strict live replay excludes
# them from regime/change-state inputs.
CURRENT_PREDICTION_BATCH_CONTEXT_COLUMNS = {
    "score_mean",
    "score_std",
    "batch_state_gate_probability",
    "batch_state_gate_passed",
    "batch_state_gate_prefix_rows",
}

LIVE_SAFE_NUMERIC_COLUMNS = tuple(
    col
    for col in SAFE_NUMERIC_COLUMNS
    if col not in CURRENT_PREDICTION_BATCH_CONTEXT_COLUMNS
)

CHANGE_FEATURES = (
    "score_mean",
    "score_std",
    "current_validation_positive_rate",
    "current_validation_signal_rate",
    "past_20_batch_positive_rate_mean",
    "past_60_batch_positive_rate_mean",
    "recent_candidate_false_discovery_rate",
)


@dataclass(frozen=True)
class RegimeConfig:
    state_count: int
    state_count_choices: tuple[int, ...]
    pca_components: int
    min_history_windows: int
    lookback_windows: int
    refit_interval_windows: int
    random_seed: int
    model_mode: str
    selection_mode: str = "fixed"
    filter_mode: str = "causal_forward_v1"


@dataclass
class RegimeModelPackage:
    status: str
    model_name: str | None = None
    medians: np.ndarray | None = None
    keep_mask: np.ndarray | None = None
    scaler: StandardScaler | None = None
    pca: PCA | None = None
    model: Any | None = None
    train_states: np.ndarray | None = None
    last_train_vector: np.ndarray | None = None
    train_model_sequence: np.ndarray | None = None
    state_mapping: dict[int, int] | None = None
    selected_state_count: int | None = None
    log_likelihood: float | None = None
    aic: float | None = None
    bic: float | None = None
    transition_matrix: np.ndarray | None = None
    expected_durations: np.ndarray | None = None
    model_selection_rows: list[dict[str, Any]] | None = None
    filter_mode: str | None = None


@dataclass(frozen=True)
class ChangeConfig:
    lookback_windows: int
    cusum_z: float
    page_hinkley_delta: float
    page_hinkley_threshold: float
    recursive_cusum_k: float = 0.50
    recursive_cusum_h: float = 5.0
    feature_set: str = "auto"
    change_detectors: tuple[str, ...] = CHANGE_DETECTORS
    cusum_standardization: str = "rolling_robust_z_v1"
    target_event_rate_min: float = 0.05
    target_event_rate_max: float = 0.25


@dataclass(frozen=True)
class TargetMatchConfig:
    favorable_min_signals: int
    favorable_min_lift: float
    favorable_max_fdr: float
    avoid_min_signals: int
    avoid_max_lift: float
    avoid_min_fdr: float


@dataclass(frozen=True)
class RegimeGateConfig:
    min_context_windows: int = 20
    min_context_signals: int = 20
    min_precision_lift: float = 1.10
    max_fdr: float = 0.58
    avoid_max_lift: float = 1.00
    avoid_min_fdr: float = 0.60


def main() -> int:
    args = parse_args()
    router_runs = tuple(Path(item) for item in args.router_run)
    if not router_runs:
        raise ValueError("At least one --router-run is required")

    run_root = run_root_for_args()
    run_root.mkdir(parents=True, exist_ok=True)
    events_path = run_root / "events.jsonl"
    append_event(events_path, "stage_start", command="rank_signal_regime_diagnostic")

    side_filter = parse_sides(args.side)
    candidate_filter = parse_candidate_names(args.candidate_names)
    raw = load_router_runs(
        router_runs,
        side_filter=side_filter,
        candidate_filter=candidate_filter,
        prediction_source=str(args.prediction_source),
    )
    if raw.is_empty():
        raise ValueError(
            "No router rows matched the regime diagnostic inputs. "
            f"prediction_source={args.prediction_source!r}, "
            f"side={args.side!r}, candidate_names={args.candidate_names!r}. "
            "For effective_selected diagnostics, omit candidate names unless they "
            "exist in selected_candidate/candidate_name. For per-candidate regime "
            "research, use --prediction-source candidate_shadow."
        )
    regime_context_mode = str(args.regime_context_mode)
    live_context = regime_context_mode.startswith("live_")
    normalized_context_mode = regime_context_mode.removeprefix("live_")
    router_context = safe_regime_context(raw, live_safe=live_context)
    market_context = pl.DataFrame()
    if normalized_context_mode in {"market_context", "combined"}:
        market_context = build_market_regime_context(
            router_context,
            args=args,
            router_runs=router_runs,
        )
    context = combine_regime_context(
        router_context,
        market_context,
        mode=str(args.regime_context_mode),
    )
    if context.is_empty():
        raise ValueError(
            "Regime context is empty after context construction. Check "
            f"regime_context_mode={args.regime_context_mode!r}, "
            f"prediction_source={args.prediction_source!r}, and candidate filters."
        )
    selected_regime_feature_cols = usable_feature_columns(context)
    regime_input_features = regime_input_feature_audit(
        context, selected_features=selected_regime_feature_cols
    )

    regime_config = RegimeConfig(
        state_count=int(args.state_count),
        state_count_choices=parse_int_csv(args.hmm_state_count_choices),
        pca_components=int(args.pca_components),
        min_history_windows=int(args.regime_min_history_windows),
        lookback_windows=int(args.regime_lookback_windows),
        refit_interval_windows=int(args.regime_refit_interval_windows),
        random_seed=int(args.random_seed),
        model_mode=str(args.model_mode),
        selection_mode=str(args.hmm_selection_mode),
        filter_mode=str(args.hmm_filter_mode),
    )
    if normalized_context_mode == "market_context":
        regime = assign_past_only_market_regimes(context, config=regime_config)
    else:
        regime = assign_past_only_regimes(context, config=regime_config)
    if (
        "regime_status" in regime.columns
        and regime.filter(pl.col("regime_status") == "ok").is_empty()
    ):
        raise ValueError(
            "No HMM/GMM regime states were assigned. The usual cause is too few "
            "chronological windows for --regime-min-history-windows. Increase "
            "--outer-window-count in the router run or lower "
            "--regime-min-history-windows for smoke testing."
        )

    requested_change_detectors = tuple(parse_csv(args.change_detectors))
    change_detectors = normalize_change_detectors(requested_change_detectors)
    change_config = ChangeConfig(
        lookback_windows=int(args.change_lookback_windows),
        cusum_z=float(args.cusum_z),
        recursive_cusum_k=float(args.recursive_cusum_k),
        recursive_cusum_h=float(args.recursive_cusum_h),
        page_hinkley_delta=float(args.page_hinkley_delta),
        page_hinkley_threshold=float(args.page_hinkley_threshold),
        feature_set=str(args.change_feature_set),
        change_detectors=change_detectors,
        cusum_standardization=str(args.cusum_standardization),
        target_event_rate_min=float(args.cusum_target_event_rate_min),
        target_event_rate_max=float(args.cusum_target_event_rate_max),
    )
    if normalized_context_mode == "market_context":
        changes = detect_market_change_events(context, config=change_config)
    else:
        changes = detect_change_events(context, config=change_config)
    hmm_transition_events = (
        detect_hmm_transition_events(regime, config=change_config)
        if HMM_TRANSITION_DETECTOR in change_detectors
        else pl.DataFrame()
    )
    all_changes = concat_nonempty((changes, hmm_transition_events))
    quality = regime_signal_quality(raw, regime)
    state_metrics = state_quality_summary(quality)
    change_flags = change_flags_by_window(all_changes, detectors=change_detectors)
    regime_change_metrics = regime_change_quality_summary(quality, change_flags)
    change_metrics = change_quality_summary(quality, change_flags)
    target_match_config = TargetMatchConfig(
        favorable_min_signals=int(args.target_match_favorable_min_signals),
        favorable_min_lift=float(args.target_match_favorable_min_lift),
        favorable_max_fdr=float(args.target_match_favorable_max_fdr),
        avoid_min_signals=int(args.target_match_avoid_min_signals),
        avoid_max_lift=float(args.target_match_avoid_max_lift),
        avoid_min_fdr=float(args.target_match_avoid_min_fdr),
    )
    gate_config = RegimeGateConfig(
        min_context_windows=int(args.gate_min_context_windows),
        min_context_signals=int(args.gate_min_context_signals),
        min_precision_lift=float(args.gate_min_precision_lift),
        max_fdr=float(args.gate_max_fdr),
        avoid_max_lift=float(args.gate_avoid_max_lift),
        avoid_min_fdr=float(args.gate_avoid_min_fdr),
    )
    regime_target_match = label_target_match(
        state_metrics, context_type="regime_state", config=target_match_config
    )
    regime_change_target_match = label_target_match(
        regime_change_metrics,
        context_type="regime_state_change_flag",
        config=target_match_config,
    )
    change_risk_target_match = label_target_match(
        change_metrics,
        context_type="change_flag",
        config=target_match_config,
    )
    suppression_candidates = suppression_candidates_from_matches(
        regime_target_match,
        regime_change_target_match,
        change_risk_target_match,
    )
    state_profile_labels = label_state_profiles(regime)
    regime_gate_simulation = simulate_regime_gate(
        quality_with_change_flags(quality, change_flags),
        config=gate_config,
    )
    regime_gate_context_metrics = regime_gate_context_metrics_from_simulation(
        regime_gate_simulation
    )
    regime_gate_decisions = regime_gate_decisions_from_simulation(
        regime_gate_simulation
    )
    hmm_filter_diagnostics = hmm_filter_diagnostics_artifact(regime)
    hmm_model_selection = hmm_model_selection_artifact(regime)
    hmm_transition_matrix = hmm_transition_matrix_artifact(regime)
    cusum_calibration = cusum_calibration_artifact(
        context,
        changes,
        hmm_transition_events,
        config=change_config,
    )

    write_rows_parquet(run_root / "regime_context.parquet", regime.to_dicts())
    write_rows_parquet(
        run_root / "regime_input_features.parquet",
        regime_input_features.to_dicts(),
    )
    write_rows_parquet(
        run_root / "market_regime_context.parquet", market_context.to_dicts()
    )
    write_rows_parquet(run_root / "change_point_events.parquet", changes.to_dicts())
    write_rows_parquet(
        run_root / "hmm_transition_events.parquet", hmm_transition_events.to_dicts()
    )
    write_rows_parquet(run_root / "regime_signal_quality.parquet", quality.to_dicts())
    write_rows_parquet(run_root / "hmm_state_metrics.parquet", state_metrics.to_dicts())
    write_rows_parquet(
        run_root / "state_profile_labels.parquet", state_profile_labels.to_dicts()
    )
    write_rows_parquet(
        run_root / "regime_target_match.parquet", regime_target_match.to_dicts()
    )
    write_rows_parquet(
        run_root / "regime_change_target_match.parquet",
        regime_change_target_match.to_dicts(),
    )
    write_rows_parquet(
        run_root / "change_risk_target_match.parquet",
        change_risk_target_match.to_dicts(),
    )
    write_rows_parquet(
        run_root / "regime_suppression_candidates.parquet",
        suppression_candidates.to_dicts(),
    )
    write_rows_parquet(
        run_root / "regime_gate_simulation.parquet",
        regime_gate_simulation.to_dicts(),
    )
    write_rows_parquet(
        run_root / "regime_gate_context_metrics.parquet",
        regime_gate_context_metrics.to_dicts(),
    )
    write_rows_parquet(
        run_root / "regime_gate_decisions.parquet",
        regime_gate_decisions.to_dicts(),
    )
    write_rows_parquet(
        run_root / "hmm_filter_diagnostics.parquet",
        hmm_filter_diagnostics.to_dicts(),
    )
    write_rows_parquet(
        run_root / "hmm_model_selection.parquet",
        hmm_model_selection.to_dicts(),
    )
    write_rows_parquet(
        run_root / "hmm_transition_matrix.parquet",
        hmm_transition_matrix.to_dicts(),
    )
    write_rows_parquet(
        run_root / "cusum_calibration.parquet",
        cusum_calibration.to_dicts(),
    )
    write_regime_report(
        run_root / "regime_transfer_report.md",
        router_runs=router_runs,
        context=regime,
        changes=changes,
        hmm_transition_events=hmm_transition_events,
        state_metrics=state_metrics,
        state_profile_labels=state_profile_labels,
        regime_target_match=regime_target_match,
        change_risk_target_match=change_risk_target_match,
        suppression_candidates=suppression_candidates,
        regime_gate_simulation=regime_gate_simulation,
        hmm_filter_diagnostics=hmm_filter_diagnostics,
        hmm_model_selection=hmm_model_selection,
        cusum_calibration=cusum_calibration,
    )
    write_json(
        run_root / "regime_diagnostic_config.json",
        {
            "router_runs": [str(path) for path in router_runs],
            "side": str(args.side),
            "prediction_source": str(args.prediction_source),
            "candidate_names": sorted(candidate_filter) if candidate_filter else [],
            "regime_context_mode": str(args.regime_context_mode),
            "live_safe_context": bool(live_context),
            "state_count": int(args.state_count),
            "hmm_selection_mode": str(args.hmm_selection_mode),
            "hmm_state_count_choices": parse_int_csv(args.hmm_state_count_choices),
            "hmm_filter_mode": str(args.hmm_filter_mode),
            "pca_components": int(args.pca_components),
            "regime_min_history_windows": int(args.regime_min_history_windows),
            "regime_lookback_windows": int(args.regime_lookback_windows),
            "regime_refit_interval_windows": int(args.regime_refit_interval_windows),
            "model_mode": str(args.model_mode),
            "change_lookback_windows": int(args.change_lookback_windows),
            "change_feature_set": str(args.change_feature_set),
            "requested_change_detectors": list(requested_change_detectors),
            "change_detectors": list(change_detectors),
            "cusum_z": float(args.cusum_z),
            "recursive_cusum_k": float(args.recursive_cusum_k),
            "recursive_cusum_h": float(args.recursive_cusum_h),
            "cusum_standardization": str(args.cusum_standardization),
            "cusum_target_event_rate_min": float(args.cusum_target_event_rate_min),
            "cusum_target_event_rate_max": float(args.cusum_target_event_rate_max),
            "page_hinkley_delta": float(args.page_hinkley_delta),
            "page_hinkley_threshold": float(args.page_hinkley_threshold),
            "market_regime": {
                "asset": str(args.asset or ""),
                "root": str(args.root or ""),
                "config": str(args.config),
                "base_run": str(args.base_run or ""),
                "panel_path": str(args.market_regime_panel_path or ""),
                "families": parse_csv(args.market_regime_families),
                "max_features_per_family": int(
                    args.market_regime_max_features_per_family
                ),
                "lookback_batches": int(args.market_regime_lookback_batches),
                "include_current_batch": bool(args.market_regime_include_current_batch),
                "context_rows": market_context.height,
            },
            "target_match": target_match_config.__dict__,
            "regime_gate": gate_config.__dict__,
            "safe_numeric_columns": [
                col for col in SAFE_NUMERIC_COLUMNS if col in context.columns
            ],
            "live_safe_numeric_columns": [
                col for col in LIVE_SAFE_NUMERIC_COLUMNS if col in context.columns
            ],
            "excluded_current_prediction_batch_context_columns": sorted(
                CURRENT_PREDICTION_BATCH_CONTEXT_COLUMNS
            ),
            "market_numeric_columns": sorted(
                col for col in context.columns if col.startswith(MARKET_CONTEXT_PREFIX)
            ),
            "regime_input_feature_columns": selected_regime_feature_cols,
            "excluded_current_outcome_columns": sorted(CURRENT_OUTCOME_COLUMNS),
        },
    )
    write_stage_status(
        run_root / "stage_status.json",
        stage="rank_signal_regime_diagnostic",
        status="complete",
        summary=summarize_stage(regime, all_changes, state_metrics)
        | {
            "regime_context_mode": str(args.regime_context_mode),
            "market_context_rows": market_context.height,
            "regime_input_features": len(selected_regime_feature_cols),
            "market_change_events": changes.height,
            "hmm_transition_events": hmm_transition_events.height,
            "state_profile_labels": state_profile_labels.height,
            "regime_gate_simulation_rows": regime_gate_simulation.height,
            "hmm_filter_diagnostics_rows": hmm_filter_diagnostics.height,
            "hmm_model_selection_rows": hmm_model_selection.height,
            "hmm_transition_matrix_rows": hmm_transition_matrix.height,
            "cusum_calibration_rows": cusum_calibration.height,
            "suppression_candidates": suppression_candidates.height,
            "favorable_regime_matches": count_match_status(
                regime_target_match, "favorable"
            ),
            "avoid_regime_matches": count_match_status(regime_target_match, "avoid"),
        },
    )
    append_event(events_path, "stage_done", run=str(run_root))
    print(f"[rpf-regime] done run={run_root}", flush=True)
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Diagnose regime/change-risk transfer for ranked-signal router runs."
    )
    parser.add_argument("--router-run", action="append", required=True)
    parser.add_argument("--side", choices=SIDES, default="both")
    parser.add_argument(
        "--prediction-source", choices=PREDICTION_SOURCES, default="effective_selected"
    )
    parser.add_argument("--candidate-names", default="")
    parser.add_argument(
        "--regime-context-mode", choices=REGIME_CONTEXT_MODES, default="router_context"
    )
    parser.add_argument("--asset", default="")
    parser.add_argument("--root", default="")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    parser.add_argument("--base-run", default="")
    parser.add_argument("--market-regime-panel-path", default="")
    parser.add_argument(
        "--market-regime-families", default=",".join(DEFAULT_MARKET_REGIME_FAMILIES)
    )
    parser.add_argument("--market-regime-max-features-per-family", type=int, default=64)
    parser.add_argument("--market-regime-lookback-batches", type=int, default=20)
    parser.add_argument("--market-regime-include-current-batch", action="store_true")
    parser.add_argument("--state-count", type=int, default=3)
    parser.add_argument(
        "--hmm-selection-mode", choices=HMM_SELECTION_MODES, default="fixed"
    )
    parser.add_argument("--hmm-state-count-choices", default="2,3,4")
    parser.add_argument(
        "--hmm-filter-mode",
        choices=HMM_FILTER_MODES,
        default="causal_forward_v1",
    )
    parser.add_argument("--pca-components", type=int, default=5)
    parser.add_argument("--regime-min-history-windows", type=int, default=80)
    parser.add_argument("--regime-lookback-windows", type=int, default=240)
    parser.add_argument("--regime-refit-interval-windows", type=int, default=1)
    parser.add_argument(
        "--model-mode", choices=("auto", "hmm", "gmm_markov"), default="auto"
    )
    parser.add_argument("--change-lookback-windows", type=int, default=60)
    parser.add_argument(
        "--change-feature-set", choices=CHANGE_FEATURE_SETS, default="auto"
    )
    parser.add_argument("--change-detectors", default=",".join(CHANGE_DETECTORS))
    parser.add_argument("--cusum-z", type=float, default=3.0)
    parser.add_argument("--recursive-cusum-k", type=float, default=0.50)
    parser.add_argument("--recursive-cusum-h", type=float, default=5.0)
    parser.add_argument(
        "--cusum-standardization",
        choices=CUSUM_STANDARDIZATIONS,
        default="rolling_robust_z_v1",
    )
    parser.add_argument("--cusum-target-event-rate-min", type=float, default=0.05)
    parser.add_argument("--cusum-target-event-rate-max", type=float, default=0.25)
    parser.add_argument("--page-hinkley-delta", type=float, default=0.01)
    parser.add_argument("--page-hinkley-threshold", type=float, default=3.0)
    parser.add_argument("--target-match-favorable-min-signals", type=int, default=80)
    parser.add_argument("--target-match-favorable-min-lift", type=float, default=1.10)
    parser.add_argument("--target-match-favorable-max-fdr", type=float, default=0.58)
    parser.add_argument("--target-match-avoid-min-signals", type=int, default=80)
    parser.add_argument("--target-match-avoid-max-lift", type=float, default=1.00)
    parser.add_argument("--target-match-avoid-min-fdr", type=float, default=0.60)
    parser.add_argument("--gate-min-context-windows", type=int, default=20)
    parser.add_argument("--gate-min-context-signals", type=int, default=20)
    parser.add_argument("--gate-min-precision-lift", type=float, default=1.10)
    parser.add_argument("--gate-max-fdr", type=float, default=0.58)
    parser.add_argument("--gate-avoid-max-lift", type=float, default=1.00)
    parser.add_argument("--gate-avoid-min-fdr", type=float, default=0.60)
    parser.add_argument("--random-seed", type=int, default=17)
    return parser.parse_args()


def parse_sides(value: str) -> set[str]:
    side = str(value)
    if side == "both":
        return {"up", "down"}
    return {side}


def parse_candidate_names(value: str | None) -> set[str]:
    return {part.strip() for part in str(value or "").split(",") if part.strip()}


def parse_csv(value: str | None) -> list[str]:
    return [part.strip() for part in str(value or "").split(",") if part.strip()]


def parse_int_csv(value: str | None) -> tuple[int, ...]:
    out: list[int] = []
    for part in parse_csv(value):
        item = int(part)
        if item > 0 and item not in out:
            out.append(item)
    return tuple(out) or (3,)


def normalize_change_detectors(
    values: tuple[str, ...] | list[str] | None,
) -> tuple[str, ...]:
    raw = tuple(values or CHANGE_DETECTORS)
    normalized: list[str] = []
    unknown: list[str] = []
    for item in raw:
        detector = CHANGE_DETECTOR_ALIASES.get(str(item), str(item))
        if detector not in CHANGE_DETECTORS:
            unknown.append(str(item))
            continue
        if detector not in normalized:
            normalized.append(detector)
    if unknown:
        raise ValueError(f"Unsupported change detectors: {sorted(unknown)}")
    return tuple(normalized)


def concat_nonempty(frames: tuple[pl.DataFrame, ...] | list[pl.DataFrame]) -> pl.DataFrame:
    usable = [frame for frame in frames if not frame.is_empty()]
    return pl.concat(usable, how="diagonal_relaxed") if usable else pl.DataFrame()


def first_router_config(router_runs: tuple[Path, ...]) -> dict[str, Any]:
    for run in router_runs:
        path = run / "router_config.json"
        if path.exists():
            try:
                return json.loads(path.read_text())
            except json.JSONDecodeError:
                continue
    return {}


def combine_regime_context(
    router_context: pl.DataFrame, market_context: pl.DataFrame, *, mode: str
) -> pl.DataFrame:
    live_safe = str(mode).startswith("live_")
    normalized_mode = str(mode).removeprefix("live_")
    if normalized_mode == "router_context" or market_context.is_empty():
        return router_context
    join_keys = [
        col
        for col in ("source_idx", "pred_batch_id")
        if col in router_context.columns and col in market_context.columns
    ]
    if not join_keys:
        raise ValueError(
            "Cannot attach market context: missing source_idx/pred_batch_id join keys"
        )
    joined = router_context.join(market_context, on=join_keys, how="left")
    if normalized_mode == "combined":
        return safe_regime_context(joined, live_safe=live_safe)
    if normalized_mode == "market_context":
        identity = [
            col
            for col in (
                "source_run",
                "source_idx",
                "window_end_offset_steps",
                "outer_window_count",
                "selection_mode",
                "candidate_set",
                "side",
                "candidate_name",
                "step_idx",
                "pred_batch_id",
            )
            if col in joined.columns
        ]
        market_cols = sorted(
            col for col in joined.columns if col.startswith(MARKET_CONTEXT_PREFIX)
        )
        return joined.select(list(dict.fromkeys([*identity, *market_cols])))
    raise ValueError(f"Unsupported regime context mode: {mode}")


def build_market_regime_context(
    router_context: pl.DataFrame,
    *,
    args: argparse.Namespace,
    router_runs: tuple[Path, ...],
) -> pl.DataFrame:
    if router_context.is_empty():
        return pl.DataFrame()
    clean_config = load_clean_config(Path(args.config))
    router_config = first_router_config(router_runs)
    asset = str(args.asset or router_config.get("asset") or clean_config.asset)
    root = str(args.root or router_config.get("root") or clean_config.root)
    context = resolve_context(
        project_root=PROJECT_ROOT,
        asset=asset,
        root=root,
        target_col=clean_config.target_col,
    )
    family_columns = market_feature_columns(
        context.manifest.feature_columns,
        panel_path=str(args.market_regime_panel_path or ""),
        families=parse_csv(args.market_regime_families),
        max_features_per_family=int(args.market_regime_max_features_per_family),
    )
    if not any(family_columns.values()):
        raise ValueError("Market regime context selected zero RPF features")

    available_ids = ordered_available_batch_ids(
        context, Path(args.base_run) if args.base_run else None
    )
    pred_rows = (
        router_context.select(
            [
                col
                for col in ("source_idx", "pred_batch_id")
                if col in router_context.columns
            ]
        )
        .unique()
        .sort(["source_idx", "pred_batch_id"])
        .to_dicts()
    )
    lookback = int(args.market_regime_lookback_batches)
    include_current = bool(args.market_regime_include_current_batch)
    needed: set[int] = set()
    histories: dict[tuple[int, int], list[int]] = {}
    for row in pred_rows:
        pred_batch_id = int(row["pred_batch_id"])
        history = prior_available_batches(
            available_ids,
            pred_batch_id,
            lookback=lookback,
            include_current=include_current,
        )
        histories[(int(row.get("source_idx", 0)), pred_batch_id)] = history
        needed.update(history)

    per_batch = compute_market_batch_stats(
        feature_root=context.feature_root,
        batch_ids=tuple(sorted(needed)),
        family_columns=family_columns,
    )
    rows: list[dict[str, Any]] = []
    for row in pred_rows:
        source_idx = int(row.get("source_idx", 0))
        pred_batch_id = int(row["pred_batch_id"])
        history = histories.get((source_idx, pred_batch_id), [])
        payload: dict[str, Any] = {
            "source_idx": source_idx,
            "pred_batch_id": pred_batch_id,
            "market_context_lookback_batches": int(lookback),
            "market_context_include_current_batch": bool(include_current),
            "market_context_history_batch_count": int(len(history)),
            "market_context_last_batch_id": int(history[-1]) if history else None,
        }
        payload.update(aggregate_market_history(history, per_batch, family_columns))
        rows.append(payload)
    return pl.DataFrame(rows, infer_schema_length=None) if rows else pl.DataFrame()


def ordered_available_batch_ids(context: Any, base_run: Path | None) -> tuple[int, ...]:
    if base_run:
        path = base_run / "batch_index.parquet"
        if path.exists():
            frame = pl.read_parquet(path)
            if "batch_id" in frame.columns:
                return tuple(int(value) for value in frame["batch_id"].to_list())
    return available_batch_ids(context.feature_root, context.label_root)


def prior_available_batches(
    available_ids: tuple[int, ...],
    pred_batch_id: int,
    *,
    lookback: int,
    include_current: bool,
) -> list[int]:
    if lookback <= 0:
        return []
    end = (
        bisect.bisect_right(available_ids, int(pred_batch_id))
        if include_current
        else bisect.bisect_left(available_ids, int(pred_batch_id))
    )
    start = max(0, end - int(lookback))
    return [int(value) for value in available_ids[start:end]]


def market_feature_columns(
    manifest_features: tuple[str, ...],
    *,
    panel_path: str,
    families: list[str],
    max_features_per_family: int,
) -> dict[str, tuple[str, ...]]:
    allowed = (
        tuple(load_panel_features(panel_path, manifest_features))
        if panel_path
        else tuple(manifest_features)
    )
    allowed_set = set(allowed)
    selected: dict[str, tuple[str, ...]] = {}
    for family in families:
        if family not in FAMILY_PREFIXES:
            known = ", ".join(sorted(FAMILY_PREFIXES))
            raise ValueError(
                f"Unknown market regime family {family!r}; expected one of: {known}"
            )
        prefixes = FAMILY_PREFIXES[family]
        cols = [
            feature
            for feature in manifest_features
            if feature in allowed_set and feature.startswith(prefixes)
        ]
        if max_features_per_family > 0:
            cols = cols[: int(max_features_per_family)]
        selected[family] = tuple(cols)
    return selected


def compute_market_batch_stats(
    *,
    feature_root: Path,
    batch_ids: tuple[int, ...],
    family_columns: dict[str, tuple[str, ...]],
) -> dict[int, dict[str, float | int | None]]:
    all_columns = tuple(
        dict.fromkeys(col for cols in family_columns.values() for col in cols)
    )
    out: dict[int, dict[str, float | int | None]] = {}
    if not all_columns:
        return out
    for batch_id in batch_ids:
        path = feature_root / f"batch_{int(batch_id):04d}.parquet"
        if not path.exists():
            continue
        schema = set(pl.read_parquet_schema(path))
        present = [col for col in all_columns if col in schema]
        if not present:
            continue
        frame = pl.read_parquet(path, columns=present)
        row: dict[str, float | int | None] = {"batch_id": int(batch_id)}
        for family, columns in family_columns.items():
            present_family_cols = [col for col in columns if col in frame.columns]
            row.update(family_batch_stats(family, frame, present_family_cols))
        out[int(batch_id)] = row
    return out


def family_batch_stats(
    family: str, frame: pl.DataFrame, columns: list[str]
) -> dict[str, float | int | None]:
    prefix = f"{MARKET_CONTEXT_PREFIX}{family}"
    out: dict[str, float | int | None] = {
        f"{prefix}_feature_count": int(len(columns)),
        f"{prefix}_row_count": int(frame.height),
    }
    if not columns or frame.is_empty():
        for metric in MARKET_BATCH_METRICS:
            out[f"{prefix}_{metric}"] = None
        return out
    values = frame.select(columns).to_numpy().astype("float64", copy=False)
    finite_mask = np.isfinite(values)
    finite_values = values[finite_mask]
    total_cells = int(values.size)
    out[f"{prefix}_finite_rate"] = (
        float(finite_values.size / total_cells) if total_cells else None
    )
    if finite_values.size == 0:
        for metric in ("mean", "std", "abs_mean", "q10", "q50", "q90"):
            out[f"{prefix}_{metric}"] = None
        return out
    out[f"{prefix}_mean"] = float(np.mean(finite_values))
    out[f"{prefix}_std"] = float(np.std(finite_values))
    out[f"{prefix}_abs_mean"] = float(np.mean(np.abs(finite_values)))
    out[f"{prefix}_q10"] = float(np.quantile(finite_values, 0.10))
    out[f"{prefix}_q50"] = float(np.quantile(finite_values, 0.50))
    out[f"{prefix}_q90"] = float(np.quantile(finite_values, 0.90))
    return out


def aggregate_market_history(
    history: list[int],
    per_batch: dict[int, dict[str, float | int | None]],
    family_columns: dict[str, tuple[str, ...]],
) -> dict[str, float | int | None]:
    out: dict[str, float | int | None] = {}
    for family, columns in family_columns.items():
        prefix = f"{MARKET_CONTEXT_PREFIX}{family}"
        rows = [per_batch[batch_id] for batch_id in history if batch_id in per_batch]
        out[f"{prefix}_batch_count"] = int(len(rows))
        out[f"{prefix}_feature_count"] = int(len(columns))
        for metric in MARKET_BATCH_METRICS:
            values = numeric_values(row.get(f"{prefix}_{metric}") for row in rows)
            last = values[-1] if values else None
            mean = float(np.mean(values)) if values else None
            std = float(np.std(values)) if values else None
            out[f"{prefix}_{metric}_last"] = last
            out[f"{prefix}_{metric}_lookback_mean"] = mean
            out[f"{prefix}_{metric}_lookback_std"] = std
            if (
                last is not None
                and mean is not None
                and std is not None
                and std > 1e-12
            ):
                out[f"{prefix}_{metric}_last_z"] = float((last - mean) / std)
            else:
                out[f"{prefix}_{metric}_last_z"] = None
    return out


def numeric_values(values: Any) -> list[float]:
    out: list[float] = []
    for value in values:
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if np.isfinite(number):
            out.append(number)
    return out


def load_router_runs(
    router_runs: tuple[Path, ...],
    *,
    side_filter: set[str],
    candidate_filter: set[str],
    prediction_source: str = "effective_selected",
) -> pl.DataFrame:
    frames: list[pl.DataFrame] = []
    router_side_candidates = single_candidate_by_side(candidate_filter)
    for source_idx, run in enumerate(sort_router_runs_chronologically(router_runs)):
        frame = load_router_run(
            run,
            source_idx=source_idx,
            prediction_source=prediction_source,
            router_side_candidates=router_side_candidates,
        )
        if side_filter:
            frame = frame.filter(pl.col("side").is_in(sorted(side_filter)))
        if (
            frame_prediction_source(frame, fallback=prediction_source)
            in {"router_selected", "row_rule_active"}
            and "rows" in frame.columns
        ):
            frame = frame.filter(pl.col("rows").fill_null(0) > 0)
        if candidate_filter:
            frame = frame.filter(
                pl.col("candidate_name").is_in(sorted(candidate_filter))
            )
        if not frame.is_empty():
            frames.append(frame)
    return pl.concat(frames, how="diagonal_relaxed") if frames else pl.DataFrame()


def frame_prediction_source(frame: pl.DataFrame, *, fallback: str) -> str:
    if "prediction_source" not in frame.columns or frame.is_empty():
        return fallback
    value = frame["prediction_source"][0]
    return str(value) if value is not None else fallback


def single_candidate_by_side(candidate_filter: set[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for side in ("up", "down"):
        candidates = sorted(
            candidate
            for candidate in candidate_filter
            if candidate.startswith(f"{side}_")
        )
        if len(candidates) == 1:
            out[side] = candidates[0]
    return out


def sort_router_runs_chronologically(router_runs: tuple[Path, ...]) -> list[Path]:
    """Return older router blocks first, independent of CLI argument order.

    ``window_end_offset_steps`` is larger for older slices because offset 0 is
    the latest selected window block.  Regime fitting uses previous rows as
    history, so chronological order matters.
    """

    keyed: list[tuple[int, str, Path]] = []
    for run in router_runs:
        config_path = run / "router_config.json"
        if not config_path.exists():
            keyed.append((0, str(run), run))
            continue
        try:
            config = json.loads(config_path.read_text())
        except json.JSONDecodeError:
            keyed.append((0, str(run), run))
            continue
        keyed.append((int(config.get("window_end_offset_steps", 0)), str(run), run))
    return [run for _, _, run in sorted(keyed, key=lambda item: (-item[0], item[1]))]


def load_router_run(
    run: Path,
    *,
    source_idx: int,
    prediction_source: str = "effective_selected",
    router_side_candidates: dict[str, str] | None = None,
) -> pl.DataFrame:
    if not run.exists():
        raise FileNotFoundError(f"Router run does not exist: {run}")
    prediction_path = run / "candidate_prediction_window_metrics.parquet"
    router_prediction_path = run / "router_window_metrics.parquet"
    row_rule_active_path = run / "row_rule_active_window_metrics.parquet"
    effective_prediction_path = run / "effective_window_metrics.parquet"
    validation_path = run / "candidate_validation_metrics.parquet"
    reliability_path = run / "candidate_reliability_state.parquet"
    batch_regime_path = run / "batch_regime_diagnostics.parquet"
    config_path = run / "router_config.json"
    if prediction_source not in PREDICTION_SOURCES:
        raise ValueError(f"Unsupported prediction source: {prediction_source}")
    config = json.loads(config_path.read_text()) if config_path.exists() else {}
    resolved_prediction_source = resolve_prediction_source(
        requested=prediction_source,
        router_window_path=router_prediction_path,
        row_rule_active_path=row_rule_active_path,
        effective_window_path=effective_prediction_path,
        config=config,
    )
    if (
        resolved_prediction_source == "candidate_shadow"
        and not prediction_path.exists()
    ):
        raise FileNotFoundError(f"Missing required artifact: {prediction_path}")
    if (
        resolved_prediction_source == "router_selected"
        and not router_prediction_path.exists()
    ):
        raise FileNotFoundError(f"Missing required artifact: {router_prediction_path}")
    if (
        resolved_prediction_source == "row_rule_active"
        and not row_rule_active_path.exists()
    ):
        raise FileNotFoundError(f"Missing required artifact: {row_rule_active_path}")
    if (
        resolved_prediction_source == "effective_selected"
        and not effective_prediction_path.exists()
    ):
        raise FileNotFoundError(
            f"Missing required artifact: {effective_prediction_path}"
        )

    source_columns = [
        pl.lit(str(run)).alias("source_run"),
        pl.lit(int(source_idx)).alias("source_idx"),
        pl.lit(int(config.get("window_end_offset_steps", 0))).alias(
            "window_end_offset_steps"
        ),
        pl.lit(int(config.get("outer_window_count", 0))).alias("outer_window_count"),
        pl.lit(str(config.get("selection_mode", ""))).alias("selection_mode"),
        pl.lit(str(config.get("candidate_set", ""))).alias("candidate_set"),
        pl.lit(str(prediction_source)).alias("requested_prediction_source"),
        pl.lit(str(resolved_prediction_source)).alias("prediction_source"),
    ]
    source_columns_without_prediction_source = source_columns[:-1]
    if resolved_prediction_source == "candidate_shadow":
        prediction = pl.read_parquet(prediction_path).with_columns(*source_columns)
    elif resolved_prediction_source == "router_selected":
        side_candidates = router_side_candidates or {}
        frame = pl.read_parquet(router_prediction_path)
        side_candidate_expr = pl.lit("__no_selected_candidate__")
        for side, candidate in sorted(side_candidates.items()):
            side_candidate_expr = (
                pl.when(pl.col("side") == side)
                .then(pl.lit(candidate))
                .otherwise(side_candidate_expr)
            )
        prediction = frame.with_columns(
            pl.when(pl.col("selected_candidate").is_not_null())
            .then(pl.col("selected_candidate"))
            .otherwise(side_candidate_expr)
            .alias("candidate_name"),
            *source_columns,
        )
    elif resolved_prediction_source == "effective_selected":
        frame = pl.read_parquet(effective_prediction_path)
        source = frame_prediction_source(frame, fallback="effective_selected")
        prediction = frame.with_columns(*source_columns_without_prediction_source)
        if "prediction_source" not in prediction.columns:
            prediction = prediction.with_columns(
                pl.lit(source).alias("prediction_source")
            )
        if (
            "candidate_name" not in prediction.columns
            and "selected_candidate" in prediction.columns
        ):
            prediction = prediction.with_columns(
                pl.col("selected_candidate").alias("candidate_name")
            )
    else:
        prediction = pl.read_parquet(row_rule_active_path).with_columns(*source_columns)

    out = prediction
    if resolved_prediction_source in {
        "router_selected",
        "row_rule_active",
        "effective_selected",
    }:
        return out.sort(["source_idx", "side", "candidate_name", "pred_batch_id"])
    if validation_path.exists():
        validation = pl.read_parquet(validation_path).select(
            [
                col
                for col in pl.read_parquet(validation_path).columns
                if col not in {"diagnostic", "status"}
            ]
        )
        out = out.join(
            validation,
            on=["side", "candidate_name", "step_idx", "pred_batch_id"],
            how="left",
            suffix="_validation",
        )

    if reliability_path.exists():
        reliability = (
            pl.read_parquet(reliability_path)
            .rename(
                {"router_step_idx": "step_idx", "router_pred_batch_id": "pred_batch_id"}
            )
            .select(
                [
                    col
                    for col in pl.read_parquet(reliability_path)
                    .rename(
                        {
                            "router_step_idx": "step_idx",
                            "router_pred_batch_id": "pred_batch_id",
                        }
                    )
                    .columns
                    if col not in {"diagnostic"}
                ]
            )
        )
        out = out.join(
            reliability,
            on=["side", "candidate_name", "step_idx", "pred_batch_id"],
            how="left",
            suffix="_reliability",
        )

    if batch_regime_path.exists():
        batch_regime = pl.read_parquet(batch_regime_path).rename(
            {"pred_batch_id": "batch_regime_pred_batch_id"}
        )
        out = out.join(
            batch_regime,
            left_on=["side", "pred_batch_id"],
            right_on=["side", "batch_regime_pred_batch_id"],
            how="left",
            suffix="_batch_regime",
        )

    return out.sort(["source_idx", "side", "candidate_name", "pred_batch_id"])


def resolve_prediction_source(
    *,
    requested: str,
    router_window_path: Path,
    row_rule_active_path: Path,
    effective_window_path: Path | None = None,
    config: dict[str, Any],
) -> str:
    if requested != "effective_selected":
        return requested
    if effective_window_path is not None and effective_window_path.exists():
        try:
            if (
                pl.scan_parquet(effective_window_path).select(pl.len()).collect().item()
                > 0
            ):
                return "effective_selected"
        except Exception:
            return "effective_selected"
    row_rule = config.get("row_rule_gate") if isinstance(config, dict) else None
    output_mode = str((row_rule or {}).get("output_mode", ""))
    if output_mode.startswith("active") and row_rule_active_path.exists():
        try:
            if (
                pl.scan_parquet(row_rule_active_path).select(pl.len()).collect().item()
                > 0
            ):
                return "row_rule_active"
        except Exception:
            return "row_rule_active"
    if router_window_path.exists():
        return "router_selected"
    return "row_rule_active" if row_rule_active_path.exists() else "router_selected"


def safe_regime_context(df: pl.DataFrame, *, live_safe: bool = False) -> pl.DataFrame:
    if df.is_empty():
        return pl.DataFrame()
    required = [
        "source_run",
        "source_idx",
        "window_end_offset_steps",
        "outer_window_count",
        "selection_mode",
        "candidate_set",
        "side",
        "candidate_name",
        "step_idx",
        "pred_batch_id",
    ]
    keep = [col for col in required if col in df.columns]
    numeric_columns = LIVE_SAFE_NUMERIC_COLUMNS if live_safe else SAFE_NUMERIC_COLUMNS
    for col in numeric_columns:
        if col in df.columns and col not in CURRENT_OUTCOME_COLUMNS:
            keep.append(col)
    for col in df.columns:
        if col.startswith(MARKET_CONTEXT_PREFIX) and col not in CURRENT_OUTCOME_COLUMNS:
            keep.append(col)
    out = df.select(list(dict.fromkeys(keep)))
    leaked = CURRENT_OUTCOME_COLUMNS & set(out.columns)
    if leaked:
        raise ValueError(
            f"Regime context contains current prediction outcome columns: {sorted(leaked)}"
        )
    if live_safe:
        leaked_prediction_context = CURRENT_PREDICTION_BATCH_CONTEXT_COLUMNS & set(
            out.columns
        )
        if leaked_prediction_context:
            raise ValueError(
                "Live regime context contains current prediction-batch context columns: "
                f"{sorted(leaked_prediction_context)}"
            )
    return out.sort(
        [
            col
            for col in ["source_idx", "side", "candidate_name", "pred_batch_id"]
            if col in out.columns
        ]
    )


def assign_past_only_regimes(df: pl.DataFrame, *, config: RegimeConfig) -> pl.DataFrame:
    if df.is_empty():
        return df
    feature_cols = usable_feature_columns(df)
    rows: list[dict[str, Any]] = []
    for _key, group in df.group_by(["side", "candidate_name"], maintain_order=True):
        group_rows = group.sort(["source_idx", "pred_batch_id"]).to_dicts()
        history: list[dict[str, Any]] = []
        previous_state: int | None = None
        cached_model: RegimeModelPackage | None = None
        rows_since_refit = max(1, int(config.refit_interval_windows))
        for row in group_rows:
            payload = dict(row)
            if len(history) < config.min_history_windows or not feature_cols:
                payload.update(
                    empty_regime_fields(
                        "insufficient_history"
                        if feature_cols
                        else "no_safe_numeric_features"
                    )
                )
            else:
                train_rows = (
                    history[-config.lookback_windows :]
                    if config.lookback_windows > 0
                    else history
                )
                if int(config.refit_interval_windows) <= 1:
                    assignment = fit_predict_regime_state(
                        train_rows,
                        row,
                        feature_cols,
                        config,
                        previous_state=previous_state,
                    )
                else:
                    if cached_model is None or rows_since_refit >= int(
                        config.refit_interval_windows
                    ):
                        cached_model = fit_regime_model_package(
                            train_rows, feature_cols, config
                        )
                        rows_since_refit = 0
                    assignment = predict_regime_state_from_package(
                        cached_model,
                        row,
                        feature_cols,
                        previous_state=previous_state,
                    )
                    rows_since_refit += 1
                payload.update(assignment)
                if assignment.get("regime_state") is not None:
                    previous_state = int(assignment["regime_state"])
            rows.append(payload)
            history.append(row)
    return pl.DataFrame(rows, infer_schema_length=None) if rows else df


def assign_past_only_market_regimes(
    df: pl.DataFrame, *, config: RegimeConfig
) -> pl.DataFrame:
    """Assign one causal market regime per prediction window, then copy to rows.

    Market regimes should describe the market window, not the candidate branch.
    The input can contain multiple side/candidate rows per ``pred_batch_id``.
    This function deduplicates those rows before fitting HMM/GMM history and
    then joins the resulting state back to every side/candidate row for outcome
    analysis.
    """

    if df.is_empty():
        return df
    market = unique_market_context_rows(df)
    if market.is_empty():
        return df
    model_input = market.with_columns(
        pl.lit("__market__").alias("side"),
        pl.lit("__market_context__").alias("candidate_name"),
    )
    assigned = assign_past_only_regimes(model_input, config=config)
    regime_cols = regime_assignment_columns(assigned)
    join_cols = [col for col in ["source_idx", "pred_batch_id"] if col in df.columns]
    if not join_cols or not regime_cols:
        return df
    assignment = assigned.select(list(dict.fromkeys([*join_cols, *regime_cols])))
    overlap = [col for col in regime_cols if col in df.columns]
    base = df.drop(overlap) if overlap else df
    return base.join(assignment, on=join_cols, how="left")


def unique_market_context_rows(df: pl.DataFrame) -> pl.DataFrame:
    market_cols = sorted(
        col for col in df.columns if col.startswith(MARKET_CONTEXT_PREFIX)
    )
    identity_cols = [
        col
        for col in (
            "source_run",
            "source_idx",
            "window_end_offset_steps",
            "outer_window_count",
            "selection_mode",
            "candidate_set",
            "step_idx",
            "pred_batch_id",
        )
        if col in df.columns
    ]
    cols = list(dict.fromkeys([*identity_cols, *market_cols]))
    if not market_cols or not {"source_idx", "pred_batch_id"}.issubset(set(df.columns)):
        return pl.DataFrame()
    return (
        df.select(cols)
        .unique(subset=["source_idx", "pred_batch_id"], keep="first")
        .sort(["source_idx", "pred_batch_id"])
    )


def regime_assignment_columns(df: pl.DataFrame) -> list[str]:
    return [
        col
        for col in df.columns
        if col.startswith("regime_")
        or col
        in {
            "hmm_state",
            "hmm_status",
        }
    ]


def market_context_family(column: str) -> str | None:
    for family in DEFAULT_MARKET_REGIME_FAMILIES:
        if column.startswith(f"{MARKET_CONTEXT_PREFIX}{family}_"):
            return family
    return None


def market_context_excluded_reason(column: str) -> str | None:
    if not column.startswith(MARKET_CONTEXT_PREFIX):
        return None
    if column in MARKET_CONTEXT_META_COLUMNS:
        return "market_context_meta_control"
    if any(token in column for token in MARKET_CONTEXT_META_TOKENS):
        return "market_context_count_or_quality_control"
    if market_context_family(column) is None:
        return "market_context_unknown_family"
    if not column.endswith(MARKET_MODEL_SUFFIXES):
        return "market_context_not_model_metric"
    return None


def is_market_model_feature(column: str) -> bool:
    return (
        column.startswith(MARKET_CONTEXT_PREFIX)
        and market_context_excluded_reason(column) is None
    )


def regime_input_feature_audit(
    df: pl.DataFrame, *, selected_features: list[str]
) -> pl.DataFrame:
    selected = set(selected_features)
    rows: list[dict[str, Any]] = []
    for col in sorted(df.columns):
        if col in REGIME_IDENTITY_COLUMNS:
            continue
        family = market_context_family(col)
        included = col in selected
        reason: str | None = None
        if col in CURRENT_OUTCOME_COLUMNS:
            reason = "current_prediction_outcome"
        elif col in CURRENT_PREDICTION_BATCH_CONTEXT_COLUMNS and not included:
            reason = "current_prediction_batch_context_excluded"
        elif col.startswith(MARKET_CONTEXT_PREFIX):
            reason = market_context_excluded_reason(col)
        elif col not in SAFE_NUMERIC_COLUMNS and col not in LIVE_SAFE_NUMERIC_COLUMNS:
            reason = "not_regime_input_candidate"
        if included:
            reason = None
        elif reason is None:
            reason = "not_selected_or_non_informative"
        rows.append(
            {
                "feature_name": col,
                "feature_family": family or ("router_context" if col in SAFE_NUMERIC_COLUMNS else None),
                "included": included,
                "excluded_reason": reason,
            }
        )
    return pl.DataFrame(rows, infer_schema_length=None) if rows else pl.DataFrame()


def usable_feature_columns(df: pl.DataFrame) -> list[str]:
    cols: list[str] = []
    candidates = [
        *SAFE_NUMERIC_COLUMNS,
        *sorted(col for col in df.columns if is_market_model_feature(col)),
    ]
    for col in candidates:
        if col not in df.columns:
            continue
        values = df[col].cast(pl.Float64, strict=False).to_numpy()
        finite = values[np.isfinite(values)]
        if finite.size and float(np.nanstd(finite)) > 1e-12:
            cols.append(col)
    return cols


def fit_predict_regime_state(
    train_rows: list[dict[str, Any]],
    current_row: dict[str, Any],
    feature_cols: list[str],
    config: RegimeConfig,
    *,
    previous_state: int | None,
) -> dict[str, Any]:
    x_train = rows_to_matrix(train_rows, feature_cols)
    x_current = rows_to_matrix([current_row], feature_cols)
    x_train, x_current = keep_informative_columns(x_train, x_current)
    if x_train.shape[1] == 0:
        return empty_regime_fields("no_informative_safe_numeric_features")
    if x_train.shape[0] < max(max(candidate_state_counts(config)) * 5, 20):
        return empty_regime_fields("insufficient_fit_rows")

    scaler = StandardScaler()
    x_train_scaled = scaler.fit_transform(x_train)
    x_current_scaled = scaler.transform(x_current)
    pca_dim = min(
        config.pca_components,
        x_train_scaled.shape[1],
        max(1, x_train_scaled.shape[0] - 1),
    )
    if pca_dim < x_train_scaled.shape[1]:
        pca = PCA(n_components=pca_dim, random_state=config.random_seed)
        x_train_model = pca.fit_transform(x_train_scaled)
        x_current_model = pca.transform(x_current_scaled)
    else:
        x_train_model = x_train_scaled
        x_current_model = x_current_scaled

    if config.model_mode in {"auto", "hmm"}:
        hmm_result = try_hmm_state(
            x_train_model, x_current_model, config, previous_state=previous_state
        )
        if hmm_result is not None:
            return hmm_result
        if config.model_mode == "hmm":
            return empty_regime_fields("hmmlearn_unavailable_or_failed")

    state_count = int(config.state_count)
    gmm = GaussianMixture(
        n_components=state_count,
        covariance_type="diag",
        random_state=config.random_seed,
        reg_covar=1e-6,
        n_init=3,
    )
    gmm.fit(x_train_model)
    raw_train_states = gmm.predict(x_train_model)
    raw_posterior = gmm.predict_proba(x_current_model)[0]
    mapping = canonical_state_mapping(x_train_model, raw_train_states, state_count)
    train_states = remap_state_array(raw_train_states, mapping)
    posterior = remap_posterior(raw_posterior, mapping)
    state = remap_state(int(np.argmax(raw_posterior)), mapping)
    return regime_payload(
        model="gmm_markov_proxy",
        state=state,
        posterior=posterior,
        train_states=train_states,
        previous_state=previous_state,
        selected_state_count=state_count,
    )


def fit_regime_model_package(
    train_rows: list[dict[str, Any]],
    feature_cols: list[str],
    config: RegimeConfig,
) -> RegimeModelPackage:
    x_train = raw_rows_to_matrix(train_rows, feature_cols)
    if x_train.size == 0 or x_train.shape[1] == 0:
        return RegimeModelPackage(status="no_safe_numeric_features")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        medians = np.nanmedian(np.where(np.isfinite(x_train), x_train, np.nan), axis=0)
    medians = np.where(np.isfinite(medians), medians, 0.0)
    x_train = impute_with_medians(x_train, medians)
    keep_mask = informative_column_mask(x_train)
    if not np.any(keep_mask):
        return RegimeModelPackage(
            status="no_informative_safe_numeric_features",
            medians=medians,
            keep_mask=keep_mask,
        )
    x_train = x_train[:, keep_mask]
    if x_train.shape[0] < max(max(candidate_state_counts(config)) * 5, 20):
        return RegimeModelPackage(
            status="insufficient_fit_rows", medians=medians, keep_mask=keep_mask
        )

    scaler = StandardScaler()
    x_train_scaled = scaler.fit_transform(x_train)
    pca_dim = min(
        config.pca_components,
        x_train_scaled.shape[1],
        max(1, x_train_scaled.shape[0] - 1),
    )
    if pca_dim < x_train_scaled.shape[1]:
        pca: PCA | None = PCA(n_components=pca_dim, random_state=config.random_seed)
        x_train_model = pca.fit_transform(x_train_scaled)
    else:
        pca = None
        x_train_model = x_train_scaled

    if config.model_mode in {"auto", "hmm"}:
        hmm_package = try_hmm_package(
            x_train_model,
            config,
            medians=medians,
            keep_mask=keep_mask,
            scaler=scaler,
            pca=pca,
        )
        if hmm_package is not None:
            return hmm_package
        if config.model_mode == "hmm":
            return RegimeModelPackage(
                status="hmmlearn_unavailable_or_failed",
                medians=medians,
                keep_mask=keep_mask,
            )

    state_count = int(config.state_count)
    gmm = GaussianMixture(
        n_components=state_count,
        covariance_type="diag",
        random_state=config.random_seed,
        reg_covar=1e-6,
        n_init=3,
    )
    gmm.fit(x_train_model)
    raw_train_states = gmm.predict(x_train_model)
    mapping = canonical_state_mapping(x_train_model, raw_train_states, state_count)
    train_states = remap_state_array(raw_train_states, mapping)
    return RegimeModelPackage(
        status="ok",
        model_name="gmm_markov_proxy",
        medians=medians,
        keep_mask=keep_mask,
        scaler=scaler,
        pca=pca,
        model=gmm,
        train_states=train_states,
        last_train_vector=x_train_model[-1:].copy(),
        train_model_sequence=x_train_model.copy(),
        state_mapping=mapping,
        selected_state_count=state_count,
    )


def predict_regime_state_from_package(
    package: RegimeModelPackage,
    current_row: dict[str, Any],
    feature_cols: list[str],
    *,
    previous_state: int | None,
) -> dict[str, Any]:
    if package.status != "ok":
        return empty_regime_fields(package.status)
    if (
        package.medians is None
        or package.keep_mask is None
        or package.scaler is None
        or package.model is None
    ):
        return empty_regime_fields("invalid_regime_model_package")
    x_current = raw_rows_to_matrix([current_row], feature_cols)
    x_current = impute_with_medians(x_current, package.medians)[:, package.keep_mask]
    if x_current.shape[1] == 0:
        return empty_regime_fields("no_informative_safe_numeric_features")
    x_current_model = package.scaler.transform(x_current)
    if package.pca is not None:
        x_current_model = package.pca.transform(x_current_model)

    train_states = np.asarray(
        package.train_states if package.train_states is not None else [], dtype=int
    )
    model_name = str(package.model_name or "gmm_markov_proxy")
    if model_name == "gaussian_hmm":
        if package.train_model_sequence is None:
            return empty_regime_fields("invalid_hmm_package")
        filter_sequence = np.vstack([package.train_model_sequence, x_current_model])
        raw_posterior = package.model.predict_proba(filter_sequence)[-1]
        current_log_likelihood = current_sequence_log_likelihood(
            package.model, package.train_model_sequence, x_current_model
        )
        package.train_model_sequence = filter_sequence
    else:
        raw_posterior = package.model.predict_proba(x_current_model)[0]
        current_log_likelihood = None
    mapping = package.state_mapping or {idx: idx for idx in range(len(raw_posterior))}
    posterior = remap_posterior(raw_posterior, mapping)
    state = remap_state(int(np.argmax(raw_posterior)), mapping)
    return regime_payload(
        model=model_name,
        state=state,
        posterior=posterior,
        train_states=train_states,
        previous_state=previous_state,
        selected_state_count=package.selected_state_count,
        log_likelihood=package.log_likelihood,
        aic=package.aic,
        bic=package.bic,
        current_log_likelihood=current_log_likelihood,
        transition_matrix=package.transition_matrix,
        expected_durations=package.expected_durations,
        model_selection_rows=package.model_selection_rows,
        filter_mode=package.filter_mode,
    )


def try_hmm_package(
    x_train: np.ndarray,
    config: RegimeConfig,
    *,
    medians: np.ndarray,
    keep_mask: np.ndarray,
    scaler: StandardScaler,
    pca: PCA | None,
) -> RegimeModelPackage | None:
    try:
        from hmmlearn.hmm import GaussianHMM  # type: ignore
    except Exception:
        return None
    selected = select_hmm_candidate(GaussianHMM, x_train, config)
    if selected is None:
        return None
    model = selected["model"]
    state_count = int(selected["state_count"])
    raw_train_states = model.predict(x_train)
    mapping = canonical_state_mapping(x_train, raw_train_states, state_count)
    train_states = remap_state_array(raw_train_states, mapping)
    transition_matrix = remap_transition_matrix(model.transmat_, mapping)
    expected_durations = expected_state_durations(transition_matrix)
    return RegimeModelPackage(
        status="ok",
        model_name="gaussian_hmm",
        medians=medians,
        keep_mask=keep_mask,
        scaler=scaler,
        pca=pca,
        model=model,
        train_states=train_states,
        last_train_vector=x_train[-1:].copy(),
        train_model_sequence=x_train.copy(),
        state_mapping=mapping,
        selected_state_count=state_count,
        log_likelihood=float(selected["log_likelihood"]),
        aic=float(selected["aic"]),
        bic=float(selected["bic"]),
        transition_matrix=transition_matrix,
        expected_durations=expected_durations,
        model_selection_rows=selected["selection_rows"],
        filter_mode=config.filter_mode,
    )


def try_hmm_state(
    x_train: np.ndarray,
    x_current: np.ndarray,
    config: RegimeConfig,
    *,
    previous_state: int | None,
) -> dict[str, Any] | None:
    try:
        from hmmlearn.hmm import GaussianHMM  # type: ignore
    except Exception:
        return None
    selected = select_hmm_candidate(GaussianHMM, x_train, config)
    if selected is None:
        return None
    model = selected["model"]
    state_count = int(selected["state_count"])
    raw_train_states = model.predict(x_train)
    filter_sequence = np.vstack([x_train, x_current])
    raw_posterior = model.predict_proba(filter_sequence)[-1]
    mapping = canonical_state_mapping(x_train, raw_train_states, state_count)
    train_states = remap_state_array(raw_train_states, mapping)
    posterior = remap_posterior(raw_posterior, mapping)
    state = remap_state(int(np.argmax(raw_posterior)), mapping)
    transition_matrix = remap_transition_matrix(model.transmat_, mapping)
    expected_durations = expected_state_durations(transition_matrix)
    return regime_payload(
        model="gaussian_hmm",
        state=state,
        posterior=posterior,
        train_states=train_states,
        previous_state=previous_state,
        selected_state_count=state_count,
        log_likelihood=float(selected["log_likelihood"]),
        aic=float(selected["aic"]),
        bic=float(selected["bic"]),
        current_log_likelihood=current_sequence_log_likelihood(
            model, x_train, x_current
        ),
        transition_matrix=transition_matrix,
        expected_durations=expected_durations,
        model_selection_rows=selected["selection_rows"],
        filter_mode=config.filter_mode,
    )


def candidate_state_counts(config: RegimeConfig) -> tuple[int, ...]:
    if config.selection_mode == "fixed":
        return (int(config.state_count),)
    choices = tuple(int(item) for item in config.state_count_choices if int(item) > 0)
    return choices or (int(config.state_count),)


def select_hmm_candidate(
    hmm_cls: Any, x_train: np.ndarray, config: RegimeConfig
) -> dict[str, Any] | None:
    selection_rows: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    feature_count = int(x_train.shape[1]) if x_train.ndim == 2 else 0
    sample_count = int(x_train.shape[0]) if x_train.ndim == 2 else 0
    for state_count in candidate_state_counts(config):
        if sample_count < max(int(state_count) * 5, 20):
            selection_rows.append(
                {
                    "candidate_state_count": int(state_count),
                    "restart": None,
                    "status": "insufficient_fit_rows",
                    "log_likelihood": None,
                    "aic": None,
                    "bic": None,
                    "selected": False,
                }
            )
            continue
        best_for_state: dict[str, Any] | None = None
        for restart in range(3):
            seed = int(config.random_seed) + restart
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", category=RuntimeWarning)
                    model = hmm_cls(
                        n_components=int(state_count),
                        covariance_type="diag",
                        n_iter=100,
                        random_state=seed,
                        min_covar=1e-6,
                    )
                    model.fit(x_train)
                    log_likelihood = float(model.score(x_train))
                param_count = hmm_parameter_count(int(state_count), feature_count)
                aic = float(-2.0 * log_likelihood + 2.0 * param_count)
                bic = float(
                    -2.0 * log_likelihood
                    + math.log(max(sample_count, 1)) * param_count
                )
                row = {
                    "candidate_state_count": int(state_count),
                    "restart": int(restart),
                    "status": "ok",
                    "log_likelihood": log_likelihood,
                    "aic": aic,
                    "bic": bic,
                    "selected": False,
                }
                selection_rows.append(row)
                candidate = row | {"model": model, "state_count": int(state_count)}
                if best_for_state is None or log_likelihood > float(
                    best_for_state["log_likelihood"]
                ):
                    best_for_state = candidate
            except Exception as exc:
                selection_rows.append(
                    {
                        "candidate_state_count": int(state_count),
                        "restart": int(restart),
                        "status": f"failed:{type(exc).__name__}",
                        "log_likelihood": None,
                        "aic": None,
                        "bic": None,
                        "selected": False,
                    }
                )
        if best_for_state is not None:
            candidates.append(best_for_state)
    if not candidates:
        return None
    if config.selection_mode == "bic_v1":
        selected = min(candidates, key=lambda item: float(item["bic"]))
    else:
        selected = max(candidates, key=lambda item: float(item["log_likelihood"]))
    for row in selection_rows:
        row["selected"] = bool(
            row.get("status") == "ok"
            and int(row["candidate_state_count"]) == int(selected["state_count"])
            and row.get("restart") == selected.get("restart")
        )
        row["selection_mode"] = str(config.selection_mode)
    return selected | {"selection_rows": selection_rows}


def hmm_parameter_count(state_count: int, feature_count: int) -> int:
    states = int(state_count)
    features = int(feature_count)
    start_params = max(states - 1, 0)
    transition_params = states * max(states - 1, 0)
    emission_params = 2 * states * max(features, 1)
    return int(start_params + transition_params + emission_params)


def remap_transition_matrix(
    matrix: np.ndarray, mapping: dict[int, int]
) -> np.ndarray | None:
    raw = np.asarray(matrix, dtype=float)
    if raw.ndim != 2 or raw.shape[0] != raw.shape[1]:
        return None
    out = np.full_like(raw, np.nan, dtype=float)
    for raw_from in range(raw.shape[0]):
        mapped_from = remap_state(raw_from, mapping)
        for raw_to in range(raw.shape[1]):
            mapped_to = remap_state(raw_to, mapping)
            if 0 <= mapped_from < out.shape[0] and 0 <= mapped_to < out.shape[1]:
                out[mapped_from, mapped_to] = float(raw[raw_from, raw_to])
    return out


def expected_state_durations(matrix: np.ndarray | None) -> np.ndarray | None:
    if matrix is None:
        return None
    out: list[float] = []
    for idx in range(matrix.shape[0]):
        stay_prob = float(matrix[idx, idx])
        if not math.isfinite(stay_prob) or stay_prob >= 1.0:
            out.append(float("inf"))
        else:
            out.append(float(1.0 / max(1.0 - stay_prob, 1e-12)))
    return np.asarray(out, dtype=float)


def current_sequence_log_likelihood(
    model: Any, train_sequence: np.ndarray, x_current: np.ndarray
) -> float | None:
    try:
        previous = float(model.score(train_sequence))
        current = float(model.score(np.vstack([train_sequence, x_current])))
        return float(current - previous)
    except Exception:
        return None


def canonical_state_mapping(
    x_train_model: np.ndarray, train_states: np.ndarray, state_count: int
) -> dict[int, int]:
    states = np.asarray(train_states, dtype=int)
    if x_train_model.ndim != 2 or x_train_model.shape[0] == 0:
        return {idx: idx for idx in range(int(state_count))}
    keys: list[tuple[tuple[float, ...], int]] = []
    feature_count = min(3, x_train_model.shape[1])
    for raw_state in range(int(state_count)):
        state_rows = x_train_model[states == raw_state]
        if state_rows.size == 0:
            centroid = tuple(float("inf") for _ in range(feature_count))
        else:
            centroid_values = np.nanmean(state_rows[:, :feature_count], axis=0)
            centroid = tuple(
                float(value) if np.isfinite(value) else float("inf")
                for value in centroid_values
            )
        keys.append(((*centroid, float(raw_state)), raw_state))
    ordered_raw_states = [
        raw_state for _, raw_state in sorted(keys, key=lambda item: item[0])
    ]
    return {
        int(raw_state): int(canonical_state)
        for canonical_state, raw_state in enumerate(ordered_raw_states)
    }


def remap_state_array(states: np.ndarray, mapping: dict[int, int]) -> np.ndarray:
    return np.asarray(
        [remap_state(int(state), mapping) for state in np.asarray(states, dtype=int)],
        dtype=int,
    )


def remap_state(state: int, mapping: dict[int, int]) -> int:
    return int(mapping.get(int(state), int(state)))


def remap_posterior(posterior: np.ndarray, mapping: dict[int, int]) -> np.ndarray:
    raw = np.asarray(posterior, dtype=float)
    out = np.zeros_like(raw)
    for raw_state, probability in enumerate(raw):
        canonical_state = remap_state(raw_state, mapping)
        if 0 <= canonical_state < out.size:
            out[canonical_state] = float(probability)
    return out


def regime_payload(
    *,
    model: str,
    state: int,
    posterior: np.ndarray,
    train_states: np.ndarray,
    previous_state: int | None,
    selected_state_count: int | None = None,
    log_likelihood: float | None = None,
    aic: float | None = None,
    bic: float | None = None,
    current_log_likelihood: float | None = None,
    transition_matrix: np.ndarray | None = None,
    expected_durations: np.ndarray | None = None,
    model_selection_rows: list[dict[str, Any]] | None = None,
    filter_mode: str | None = None,
) -> dict[str, Any]:
    posterior = np.asarray(posterior, dtype=float)
    max_prob = float(np.nanmax(posterior)) if posterior.size else None
    entropy = posterior_entropy(posterior)
    transition = transition_summary(
        train_states,
        previous_state,
        state,
        transition_matrix=transition_matrix,
    )
    duration = None
    if expected_durations is not None and 0 <= int(state) < len(expected_durations):
        value = float(expected_durations[int(state)])
        duration = value if math.isfinite(value) else None
    selected_count = int(selected_state_count) if selected_state_count is not None else None
    state_key = f"k{selected_count}_s{int(state)}" if selected_count is not None else None
    max_self_transition_probability = None
    max_expected_state_duration = None
    if transition_matrix is not None and transition_matrix.size:
        diagonal = np.diag(np.asarray(transition_matrix, dtype=float))
        finite_diagonal = diagonal[np.isfinite(diagonal)]
        if finite_diagonal.size:
            max_self_transition_probability = float(np.max(finite_diagonal))
    if expected_durations is not None:
        finite_durations = np.asarray(expected_durations, dtype=float)
        finite_durations = finite_durations[np.isfinite(finite_durations)]
        if finite_durations.size:
            max_expected_state_duration = float(np.max(finite_durations))
    hmm_degenerate = (
        (
            max_self_transition_probability is not None
            and max_self_transition_probability >= 0.995
        )
        or (
            max_expected_state_duration is not None
            and max_expected_state_duration > 4.0 * max(1, len(train_states))
        )
    )
    out: dict[str, Any] = {
        "regime_model": model,
        "regime_status": "ok",
        "regime_state": state,
        "regime_selected_state_count": selected_count,
        "regime_state_key": state_key,
        "regime_filter_mode": filter_mode,
        "regime_log_likelihood": log_likelihood,
        "regime_aic": aic,
        "regime_bic": bic,
        "regime_current_log_likelihood": current_log_likelihood,
        "regime_posterior_max": max_prob,
        "regime_posterior_confidence": max_prob,
        "regime_entropy": entropy,
        "regime_changed_from_previous": previous_state is not None
        and int(previous_state) != int(state),
        "regime_transition_probability": transition["probability"],
        "regime_transition_count": transition["count"],
        "regime_expected_duration": duration,
        "regime_max_self_transition_probability": max_self_transition_probability,
        "regime_max_expected_state_duration": max_expected_state_duration,
        "regime_hmm_degenerate_flag": bool(hmm_degenerate),
        "regime_train_state_count": int(len({int(v) for v in train_states})),
        "regime_model_selection_json": json.dumps(model_selection_rows or []),
        "regime_transition_matrix_json": transition_matrix_json(transition_matrix),
    }
    for idx, value in enumerate(posterior):
        out[f"regime_posterior_state_{idx}"] = float(value)
    if expected_durations is not None:
        for idx, value in enumerate(expected_durations):
            out[f"regime_expected_duration_state_{idx}"] = (
                float(value) if math.isfinite(float(value)) else None
            )
    if transition_matrix is not None:
        for from_state in range(transition_matrix.shape[0]):
            for to_state in range(transition_matrix.shape[1]):
                out[f"regime_transition_prob_{from_state}_{to_state}"] = float(
                    transition_matrix[from_state, to_state]
                )
    return out


def transition_summary(
    train_states: np.ndarray,
    previous_state: int | None,
    current_state: int,
    *,
    transition_matrix: np.ndarray | None = None,
) -> dict[str, Any]:
    if previous_state is None or train_states.size < 2:
        return {"probability": None, "count": 0}
    if (
        transition_matrix is not None
        and 0 <= int(previous_state) < transition_matrix.shape[0]
        and 0 <= int(current_state) < transition_matrix.shape[1]
    ):
        return {
            "probability": float(
                transition_matrix[int(previous_state), int(current_state)]
            ),
            "count": None,
        }
    total = 0
    count = 0
    for left, right in zip(train_states[:-1], train_states[1:]):
        if int(left) == int(previous_state):
            total += 1
            if int(right) == int(current_state):
                count += 1
    return {"probability": float(count / total) if total else None, "count": int(count)}


def transition_matrix_json(matrix: np.ndarray | None) -> str:
    if matrix is None:
        return "[]"
    return json.dumps(
        [
            [
                float(value) if math.isfinite(float(value)) else None
                for value in row
            ]
            for row in np.asarray(matrix, dtype=float)
        ]
    )


def posterior_entropy(posterior: np.ndarray) -> float | None:
    finite = posterior[np.isfinite(posterior) & (posterior > 0)]
    if finite.size == 0:
        return None
    return float(-(finite * np.log(finite)).sum())


def empty_regime_fields(status: str) -> dict[str, Any]:
    return {
        "regime_model": None,
        "regime_status": status,
        "regime_state": None,
        "regime_selected_state_count": None,
        "regime_state_key": None,
        "regime_filter_mode": None,
        "regime_log_likelihood": None,
        "regime_aic": None,
        "regime_bic": None,
        "regime_current_log_likelihood": None,
        "regime_posterior_max": None,
        "regime_posterior_confidence": None,
        "regime_entropy": None,
        "regime_changed_from_previous": None,
        "regime_transition_probability": None,
        "regime_transition_count": None,
        "regime_expected_duration": None,
        "regime_max_self_transition_probability": None,
        "regime_max_expected_state_duration": None,
        "regime_hmm_degenerate_flag": None,
        "regime_train_state_count": None,
        "regime_model_selection_json": "[]",
        "regime_transition_matrix_json": "[]",
    }


def rows_to_matrix(rows: list[dict[str, Any]], feature_cols: list[str]) -> np.ndarray:
    matrix = np.array(
        [[to_float(row.get(col)) for col in feature_cols] for row in rows], dtype=float
    )
    if matrix.size == 0:
        return matrix.reshape((len(rows), 0))
    finite = np.where(np.isfinite(matrix), matrix, np.nan)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        med = np.nanmedian(finite, axis=0)
    med = np.where(np.isfinite(med), med, 0.0)
    inds = np.where(~np.isfinite(matrix))
    if inds[0].size:
        matrix[inds] = med[inds[1]]
    return matrix


def raw_rows_to_matrix(
    rows: list[dict[str, Any]], feature_cols: list[str]
) -> np.ndarray:
    matrix = np.array(
        [[to_float(row.get(col)) for col in feature_cols] for row in rows], dtype=float
    )
    if matrix.size == 0:
        return matrix.reshape((len(rows), 0))
    return matrix


def impute_with_medians(matrix: np.ndarray, medians: np.ndarray) -> np.ndarray:
    out = np.array(matrix, dtype=float, copy=True)
    inds = np.where(~np.isfinite(out))
    if inds[0].size:
        out[inds] = medians[inds[1]]
    return out


def informative_column_mask(x_train: np.ndarray) -> np.ndarray:
    if x_train.size == 0 or x_train.shape[1] == 0:
        return np.zeros((x_train.shape[1] if x_train.ndim == 2 else 0,), dtype=bool)
    std = np.nanstd(x_train, axis=0)
    return np.isfinite(std) & (std > 1e-12)


def keep_informative_columns(
    x_train: np.ndarray, x_current: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    if x_train.size == 0 or x_train.shape[1] == 0:
        return x_train, x_current
    keep = informative_column_mask(x_train)
    if not np.any(keep):
        return x_train[:, :0], x_current[:, :0]
    return x_train[:, keep], x_current[:, keep]


def detect_change_events(df: pl.DataFrame, *, config: ChangeConfig) -> pl.DataFrame:
    if df.is_empty():
        return pl.DataFrame()
    detectors = set(normalize_change_detectors(config.change_detectors))
    market_detectors = detectors & set(MARKET_CHANGE_DETECTORS)
    use_zshift = "market_context_zshift_v1" in market_detectors
    use_recursive_cusum = "market_context_recursive_cusum_v1" in market_detectors
    use_page_hinkley = "page_hinkley" in detectors
    rows: list[dict[str, Any]] = []
    for _key, group in df.group_by(["side", "candidate_name"], maintain_order=True):
        group_rows = group.sort(["source_idx", "pred_batch_id"]).to_dicts()
        feature_columns = change_feature_columns(group, config.feature_set)
        ph_state = (
            {
                feature: {"mean": 0.0, "count": 0, "cum": 0.0, "min_cum": 0.0}
                for feature in feature_columns
            }
            if use_page_hinkley
            else {}
        )
        recursive_state = (
            {
                feature: {"s_pos": 0.0, "s_neg": 0.0}
                for feature in feature_columns
            }
            if use_recursive_cusum
            else {}
        )
        history: list[dict[str, Any]] = []
        recursive_window_severity_history: list[float] = []
        for row in group_rows:
            recursive_required_severity = recursive_required_severity_from_history(
                recursive_window_severity_history,
                config=config,
            )
            recursive_window_max_severity = 0.0
            for feature in feature_columns:
                if feature not in row:
                    continue
                value = to_float(row.get(feature))
                if value is None:
                    continue
                prior = (
                    history[-config.lookback_windows :]
                    if config.lookback_windows > 0
                    else history
                )
                prior_values = np.array(
                    [to_float(item.get(feature)) for item in prior], dtype=object
                )
                prior_values = np.array(
                    [
                        float(item)
                        for item in prior_values
                        if item is not None and np.isfinite(float(item))
                    ]
                )
                if (use_zshift or use_recursive_cusum) and prior_values.size >= max(
                    10, min(config.lookback_windows, 20)
                ):
                    mean, std, z = rolling_standardized_value(
                        prior_values,
                        value,
                        standardization=str(config.cusum_standardization),
                    )
                else:
                    mean = None
                    std = None
                    z = None
                zshift_alarm = bool(
                    use_zshift and z is not None and abs(z) >= float(config.cusum_z)
                )
                recursive_alarm = False
                recursive_direction = None
                recursive_s_pos = None
                recursive_s_neg = None
                recursive_raw_severity = None
                if use_recursive_cusum and z is not None:
                    (
                        raw_recursive_alarm,
                        recursive_direction,
                        recursive_s_pos,
                        recursive_s_neg,
                        recursive_raw_severity,
                    ) = recursive_cusum_step(
                        recursive_state[feature],
                        z,
                        k=float(config.recursive_cusum_k),
                        h=float(config.recursive_cusum_h),
                    )
                    recursive_window_max_severity = max(
                        recursive_window_max_severity,
                        float(recursive_raw_severity or 0.0),
                    )
                    recursive_alarm = bool(
                        raw_recursive_alarm
                        and float(recursive_raw_severity or 0.0)
                        >= recursive_required_severity
                    )
                ph_alarm = (
                    page_hinkley_update(ph_state[feature], value, config)
                    if use_page_hinkley
                    else False
                )
                base_change_row = {
                    "source_run": row.get("source_run"),
                    "source_idx": row.get("source_idx"),
                    "side": row.get("side"),
                    "candidate_name": row.get("candidate_name"),
                    "step_idx": row.get("step_idx"),
                    "pred_batch_id": row.get("pred_batch_id"),
                    "feature": feature,
                    "value": value,
                    "prior_mean": mean,
                    "prior_std": std,
                    "zscore": z,
                    "change_alarm": True,
                }
                if zshift_alarm:
                    rows.append(
                        {
                            **base_change_row,
                            "detector_name": "market_context_zshift_v1",
                            "cusum_alarm": True,
                            "market_context_zshift_v1_alarm": True,
                            "market_context_recursive_cusum_v1_alarm": False,
                            "recursive_cusum_direction": None,
                            "recursive_cusum_s_pos": None,
                            "recursive_cusum_s_neg": None,
                            "page_hinkley_alarm": False,
                        }
                    )
                if recursive_alarm:
                    rows.append(
                        {
                            **base_change_row,
                            "detector_name": "market_context_recursive_cusum_v1",
                            "cusum_alarm": False,
                            "market_context_zshift_v1_alarm": False,
                            "market_context_recursive_cusum_v1_alarm": True,
                            "recursive_cusum_direction": recursive_direction,
                            "recursive_cusum_s_pos": recursive_s_pos,
                            "recursive_cusum_s_neg": recursive_s_neg,
                            "recursive_cusum_raw_severity": recursive_raw_severity,
                            "recursive_cusum_required_severity": (
                                recursive_required_severity
                            ),
                            "recursive_cusum_calibration_history_windows": len(
                                recursive_window_severity_history
                            ),
                            "cusum_standardization": str(config.cusum_standardization),
                            "cusum_target_event_rate_min": float(
                                config.target_event_rate_min
                            ),
                            "cusum_target_event_rate_max": float(
                                config.target_event_rate_max
                            ),
                            "page_hinkley_alarm": False,
                        }
                    )
                if ph_alarm:
                    rows.append(
                        {
                            **base_change_row,
                            "detector_name": "page_hinkley",
                            "cusum_alarm": False,
                            "market_context_zshift_v1_alarm": False,
                            "market_context_recursive_cusum_v1_alarm": False,
                            "recursive_cusum_direction": None,
                            "recursive_cusum_s_pos": None,
                            "recursive_cusum_s_neg": None,
                            "page_hinkley_alarm": True,
                        }
                    )
            history.append(row)
            if use_recursive_cusum:
                recursive_window_severity_history.append(
                    float(recursive_window_max_severity)
                )
    return pl.DataFrame(rows, infer_schema_length=None) if rows else pl.DataFrame()


def detect_market_change_events(
    df: pl.DataFrame, *, config: ChangeConfig
) -> pl.DataFrame:
    """Detect market-context changes once per window and copy alarms to rows."""

    if df.is_empty():
        return pl.DataFrame()
    market = unique_market_context_rows(df)
    if market.is_empty():
        return pl.DataFrame()
    detector_input = market.with_columns(
        pl.lit("__market__").alias("side"),
        pl.lit("__market_context__").alias("candidate_name"),
    )
    detected = detect_change_events(detector_input, config=config)
    if detected.is_empty():
        return detected
    identity_cols = [
        col
        for col in [
            "source_run",
            "source_idx",
            "side",
            "candidate_name",
            "step_idx",
            "pred_batch_id",
        ]
        if col in df.columns
    ]
    identities = df.select(identity_cols).unique()
    event_cols = [
        col
        for col in detected.columns
        if col
        not in {
            "source_run",
            "side",
            "candidate_name",
            "step_idx",
        }
    ]
    return identities.join(
        detected.select(event_cols),
        on=["source_idx", "pred_batch_id"],
        how="inner",
    )


def detect_hmm_transition_events(
    regime: pl.DataFrame, *, config: ChangeConfig
) -> pl.DataFrame:
    if regime.is_empty() or "regime_status" not in regime.columns:
        return pl.DataFrame()
    market = unique_regime_assignment_rows(regime)
    if market.is_empty():
        return pl.DataFrame()
    detector_rows: list[dict[str, Any]] = []
    feature_names = [
        "hmm_uncertainty",
        "hmm_entropy",
        "hmm_transition_rarity",
        "hmm_state_changed_numeric",
        "hmm_observation_surprise",
    ]
    state = {feature: {"s_pos": 0.0, "s_neg": 0.0} for feature in feature_names}
    history: list[dict[str, Any]] = []
    recursive_window_severity_history: list[float] = []
    for row in market.sort(["source_idx", "pred_batch_id"]).to_dicts():
        recursive_required_severity = recursive_required_severity_from_history(
            recursive_window_severity_history,
            config=config,
        )
        recursive_window_max_severity = 0.0
        if row.get("regime_status") != "ok":
            history.append(row)
            recursive_window_severity_history.append(recursive_window_max_severity)
            continue
        values = hmm_transition_feature_values(row)
        state_changed = bool(row.get("regime_changed_from_previous") is True)
        for feature in feature_names:
            value = values.get(feature)
            if value is None or not math.isfinite(float(value)):
                continue
            prior = (
                history[-config.lookback_windows :]
                if config.lookback_windows > 0
                else history
            )
            prior_values = np.array(
                [
                    float(item)
                    for prior_row in prior
                    for item in [hmm_transition_feature_values(prior_row).get(feature)]
                    if item is not None and math.isfinite(float(item))
                ],
                dtype=float,
            )
            if prior_values.size < max(10, min(config.lookback_windows, 20)):
                continue
            mean, std, z = rolling_standardized_value(
                prior_values,
                float(value),
                standardization=str(config.cusum_standardization),
            )
            (
                raw_alarm,
                direction,
                s_pos,
                s_neg,
                raw_severity,
            ) = recursive_cusum_step(
                state[feature],
                z,
                k=float(config.recursive_cusum_k),
                h=float(config.recursive_cusum_h),
            )
            recursive_window_max_severity = max(
                recursive_window_max_severity,
                float(raw_severity),
            )
            alarm = bool(raw_alarm and raw_severity >= recursive_required_severity)
            base_event = {
                "source_run": row.get("source_run"),
                "source_idx": row.get("source_idx"),
                "side": "__market__",
                "candidate_name": "__hmm_transition__",
                "step_idx": row.get("step_idx"),
                "pred_batch_id": row.get("pred_batch_id"),
                "feature": feature,
                "value": float(value),
                "prior_mean": mean,
                "prior_std": std,
                "zscore": z,
                "hmm_transition_direction": direction,
                "hmm_transition_cusum_raw_severity": raw_severity,
                "hmm_transition_cusum_required_severity": (
                    recursive_required_severity
                ),
                "hmm_transition_cusum_calibration_history_windows": len(
                    recursive_window_severity_history
                ),
                "cusum_standardization": str(config.cusum_standardization),
                "cusum_target_event_rate_min": float(config.target_event_rate_min),
                "cusum_target_event_rate_max": float(config.target_event_rate_max),
                "change_alarm": True,
            }
            if alarm:
                detector_rows.append(
                    {
                        **base_event,
                        "detector_name": HMM_TRANSITION_DETECTOR,
                        "hmm_transition_cusum_v1_alarm": True,
                        "hmm_transition_cusum_s_pos": s_pos,
                        "hmm_transition_cusum_s_neg": s_neg,
                        "hmm_state_change_alarm": False,
                    }
                )
            if state_changed and feature == "hmm_state_changed_numeric":
                detector_rows.append(
                    {
                        **base_event,
                        "detector_name": HMM_STATE_CHANGE_MARKER,
                        "hmm_transition_cusum_v1_alarm": False,
                        "hmm_transition_cusum_s_pos": s_pos,
                        "hmm_transition_cusum_s_neg": s_neg,
                        "hmm_state_change_alarm": True,
                    }
                )
        history.append(row)
        recursive_window_severity_history.append(recursive_window_max_severity)
    detected = (
        pl.DataFrame(detector_rows, infer_schema_length=None)
        if detector_rows
        else pl.DataFrame()
    )
    if detected.is_empty():
        return detected
    identity_cols = [
        col
        for col in [
            "source_run",
            "source_idx",
            "side",
            "candidate_name",
            "step_idx",
            "pred_batch_id",
        ]
        if col in regime.columns
    ]
    identities = regime.select(identity_cols).unique()
    event_cols = [
        col
        for col in detected.columns
        if col
        not in {
            "source_run",
            "side",
            "candidate_name",
            "step_idx",
        }
    ]
    return identities.join(
        detected.select(event_cols),
        on=["source_idx", "pred_batch_id"],
        how="inner",
    )


def unique_regime_assignment_rows(regime: pl.DataFrame) -> pl.DataFrame:
    regime_cols = [
        col
        for col in [
            "regime_status",
            "regime_state",
            "regime_selected_state_count",
            "regime_state_key",
            "regime_posterior_max",
            "regime_posterior_confidence",
            "regime_entropy",
            "regime_changed_from_previous",
            "regime_transition_probability",
            "regime_transition_count",
            "regime_current_log_likelihood",
            "regime_expected_duration",
            "regime_max_self_transition_probability",
            "regime_max_expected_state_duration",
            "regime_hmm_degenerate_flag",
            "regime_train_state_count",
        ]
        if col in regime.columns
    ]
    posterior_cols = sorted(
        col for col in regime.columns if col.startswith("regime_posterior_state_")
    )
    identity_cols = [
        col
        for col in (
            "source_run",
            "source_idx",
            "window_end_offset_steps",
            "outer_window_count",
            "selection_mode",
            "candidate_set",
            "step_idx",
            "pred_batch_id",
        )
        if col in regime.columns
    ]
    cols = list(dict.fromkeys([*identity_cols, *regime_cols, *posterior_cols]))
    if not {"source_idx", "pred_batch_id"}.issubset(set(regime.columns)):
        return pl.DataFrame()
    return (
        regime.select(cols)
        .unique(subset=["source_idx", "pred_batch_id"], keep="first")
        .sort(["source_idx", "pred_batch_id"])
    )


def hmm_transition_feature_values(row: dict[str, Any]) -> dict[str, float | None]:
    posterior_max = to_float(row.get("regime_posterior_max"))
    entropy = to_float(row.get("regime_entropy"))
    transition_probability = to_float(row.get("regime_transition_probability"))
    current_log_likelihood = to_float(row.get("regime_current_log_likelihood"))
    state_changed = 1.0 if row.get("regime_changed_from_previous") is True else 0.0
    return {
        "hmm_uncertainty": None if posterior_max is None else 1.0 - posterior_max,
        "hmm_entropy": entropy,
        "hmm_transition_rarity": None
        if transition_probability is None
        else 1.0 - transition_probability,
        "hmm_state_changed_numeric": state_changed,
        "hmm_observation_surprise": None
        if current_log_likelihood is None
        else -float(current_log_likelihood),
    }


def change_feature_columns(df: pl.DataFrame, feature_set: str) -> list[str]:
    router_features = [feature for feature in CHANGE_FEATURES if feature in df.columns]
    market_features = [
        col
        for col in sorted(df.columns)
        if is_market_model_feature(col)
        and (col.endswith("_last_z") or col.endswith("_lookback_mean"))
    ]
    if feature_set == "router_context":
        return router_features
    if feature_set == "market_context":
        return market_features
    if feature_set == "combined":
        return [*router_features, *market_features]
    if feature_set == "auto":
        return (
            [*router_features, *market_features] if market_features else router_features
        )
    raise ValueError(f"Unsupported change feature set: {feature_set}")


def recursive_cusum_update(
    state: dict[str, float], zscore: float, *, k: float, h: float
) -> tuple[bool, str | None]:
    alarm, direction, _s_pos, _s_neg, _severity = recursive_cusum_step(
        state, zscore, k=k, h=h
    )
    return alarm, direction


def recursive_cusum_step(
    state: dict[str, float], zscore: float, *, k: float, h: float
) -> tuple[bool, str | None, float, float, float]:
    s_pos = max(0.0, float(state.get("s_pos", 0.0)) + float(zscore) - k)
    s_neg = min(0.0, float(state.get("s_neg", 0.0)) + float(zscore) + k)
    severity = max(abs(s_pos), abs(s_neg)) / max(float(h), 1e-12)
    if s_pos > h:
        state["s_pos"] = 0.0
        state["s_neg"] = s_neg
        return True, "positive", float(s_pos), float(s_neg), float(severity)
    if abs(s_neg) > h:
        state["s_pos"] = s_pos
        state["s_neg"] = 0.0
        return True, "negative", float(s_pos), float(s_neg), float(severity)
    state["s_pos"] = s_pos
    state["s_neg"] = s_neg
    return False, None, float(s_pos), float(s_neg), float(severity)


def rolling_standardized_value(
    prior_values: np.ndarray, value: float, *, standardization: str
) -> tuple[float, float, float]:
    finite = np.asarray(
        [float(item) for item in prior_values if np.isfinite(float(item))],
        dtype=float,
    )
    if finite.size == 0:
        return 0.0, 1.0, 0.0
    if standardization == "rolling_robust_z_v1":
        center = float(np.median(finite))
        mad = float(np.median(np.abs(finite - center)))
        scale = 1.4826 * mad
        if not math.isfinite(scale) or scale <= 1e-12:
            scale = float(np.std(finite)) or 1e-12
    else:
        center = float(np.mean(finite))
        scale = float(np.std(finite)) or 1e-12
    return center, scale, float((float(value) - center) / max(scale, 1e-12))


def recursive_required_severity_from_history(
    severity_history: list[float], *, config: ChangeConfig
) -> float:
    finite = np.asarray(
        [float(item) for item in severity_history if math.isfinite(float(item))],
        dtype=float,
    )
    if finite.size < max(10, min(int(config.lookback_windows), 20)):
        return 1.0
    lookback = finite[-int(config.lookback_windows) :] if config.lookback_windows > 0 else finite
    quantile = 1.0 - min(max(float(config.target_event_rate_max), 0.01), 0.95)
    threshold = float(np.quantile(lookback, quantile))
    return max(1.0, threshold)


def page_hinkley_update(
    state: dict[str, float], value: float, config: ChangeConfig
) -> bool:
    state["count"] += 1
    count = state["count"]
    state["mean"] += (value - state["mean"]) / count
    state["cum"] += value - state["mean"] - float(config.page_hinkley_delta)
    state["min_cum"] = min(state["min_cum"], state["cum"])
    alarm = bool(
        (state["cum"] - state["min_cum"]) > float(config.page_hinkley_threshold)
    )
    if alarm:
        state["cum"] = 0.0
        state["min_cum"] = 0.0
    return alarm


def regime_signal_quality(raw: pl.DataFrame, regime: pl.DataFrame) -> pl.DataFrame:
    if raw.is_empty() or regime.is_empty():
        return pl.DataFrame()
    join_keys = [
        col
        for col in ["source_run", "side", "candidate_name", "step_idx", "pred_batch_id"]
        if col in raw.columns and col in regime.columns
    ]
    state_cols = [
        col
        for col in [
            "source_run",
            "side",
            "candidate_name",
            "step_idx",
            "pred_batch_id",
            "regime_model",
            "regime_status",
            "regime_state",
            "regime_selected_state_count",
            "regime_state_key",
            "regime_posterior_max",
            "regime_posterior_confidence",
            "regime_entropy",
            "regime_changed_from_previous",
            "regime_transition_probability",
            "regime_expected_duration",
            "regime_max_self_transition_probability",
            "regime_max_expected_state_duration",
            "regime_hmm_degenerate_flag",
        ]
        if col in regime.columns
    ]
    outcome_cols = [
        col
        for col in [
            "source_run",
            "requested_prediction_source",
            "prediction_source",
            "side",
            "candidate_name",
            "step_idx",
            "pred_batch_id",
            "rows",
            "positive_count",
            "predicted_positive_count",
            "true_positive_count",
            "false_positive_count",
            "precision",
            "false_discovery_rate",
            "base_positive_rate",
            "precision_lift",
            "positive_rate",
            "active_window",
            "high_false_positive_window",
        ]
        if col in raw.columns
    ]
    out = raw.select(outcome_cols).join(
        regime.select(state_cols), on=join_keys, how="left"
    )
    return out


def state_quality_summary(df: pl.DataFrame) -> pl.DataFrame:
    if df.is_empty() or "regime_state_key" not in df.columns:
        return pl.DataFrame()
    state_df = df.filter(pl.col("regime_status") == "ok")
    if state_df.is_empty():
        return pl.DataFrame()
    health_aggs: list[pl.Expr] = []
    if "regime_hmm_degenerate_flag" in state_df.columns:
        health_aggs.append(
            pl.col("regime_hmm_degenerate_flag")
            .fill_null(False)
            .max()
            .alias("hmm_degenerate_flag")
        )
    if "regime_max_self_transition_probability" in state_df.columns:
        health_aggs.append(
            pl.col("regime_max_self_transition_probability")
            .max()
            .alias("max_self_transition_probability")
        )
    if "regime_max_expected_state_duration" in state_df.columns:
        health_aggs.append(
            pl.col("regime_max_expected_state_duration")
            .max()
            .alias("max_expected_state_duration")
        )
    grouped = (
        state_df.group_by(
            [
                "side",
                "candidate_name",
                "regime_model",
                "regime_selected_state_count",
                "regime_state",
                "regime_state_key",
            ]
        )
        .agg(
            pl.len().alias("windows"),
            pl.col("predicted_positive_count").fill_null(0).sum().alias("signals"),
            pl.col("true_positive_count").fill_null(0).sum().alias("true_positives"),
            pl.col("false_positive_count").fill_null(0).sum().alias("false_positives"),
            pl.col("positive_count").fill_null(0).sum().alias("positives"),
            pl.col("rows").fill_null(0).sum().alias("rows"),
            pl.col("regime_posterior_max").mean().alias("posterior_max_mean"),
            pl.col("regime_entropy").mean().alias("entropy_mean"),
            *health_aggs,
        )
        .with_columns(
            (pl.col("signals") > 0).alias("has_signals"),
            (pl.col("true_positives") / pl.col("signals")).alias("precision"),
            (pl.col("false_positives") / pl.col("signals")).alias(
                "false_discovery_rate"
            ),
            (pl.col("positives") / pl.col("rows")).alias("base_rate"),
            (
                (pl.col("true_positives") / pl.col("signals"))
                / (pl.col("positives") / pl.col("rows"))
            ).alias("precision_lift"),
        )
        .sort(["side", "candidate_name", "regime_state_key"])
    )
    return grouped


def change_flags_by_window(
    changes: pl.DataFrame, *, detectors: tuple[str, ...] = CHANGE_DETECTORS
) -> pl.DataFrame:
    if changes.is_empty():
        return pl.DataFrame()
    detector_set = set(normalize_change_detectors(detectors))
    aggregations: list[pl.Expr] = [pl.len().alias("change_event_count")]
    flags: list[pl.Expr] = [(pl.col("change_event_count") > 0).alias("has_any_change")]
    if "market_context_zshift_v1" in detector_set and "cusum_alarm" in changes.columns:
        if "market_context_zshift_v1_alarm" in changes.columns:
            aggregations.append(
                pl.col("market_context_zshift_v1_alarm")
                .fill_null(False)
                .sum()
                .alias("market_context_zshift_v1_count")
            )
        else:
            aggregations.append(
                pl.col("cusum_alarm")
                .fill_null(False)
                .sum()
                .alias("market_context_zshift_v1_count")
            )
        flags.append(
            (pl.col("market_context_zshift_v1_count") > 0).alias(
                "has_market_context_zshift_v1"
            )
        )
    if (
        "market_context_recursive_cusum_v1" in detector_set
        and "market_context_recursive_cusum_v1_alarm" in changes.columns
    ):
        aggregations.append(
            pl.col("market_context_recursive_cusum_v1_alarm")
            .fill_null(False)
            .sum()
            .alias("market_context_recursive_cusum_v1_count")
        )
        flags.append(
            (pl.col("market_context_recursive_cusum_v1_count") > 0).alias(
                "has_market_context_recursive_cusum_v1"
            )
        )
    if (
        HMM_TRANSITION_DETECTOR in detector_set
        and "hmm_transition_cusum_v1_alarm" in changes.columns
    ):
        aggregations.append(
            pl.col("hmm_transition_cusum_v1_alarm")
            .fill_null(False)
            .sum()
            .alias("hmm_transition_cusum_v1_count")
        )
        flags.append(
            (pl.col("hmm_transition_cusum_v1_count") > 0).alias(
                "has_hmm_transition_cusum_v1"
            )
        )
    if "hmm_state_change_alarm" in changes.columns:
        aggregations.append(
            pl.col("hmm_state_change_alarm")
            .fill_null(False)
            .sum()
            .alias("hmm_state_change_count")
        )
        flags.append(
            (pl.col("hmm_state_change_count") > 0).alias("has_hmm_state_change")
        )
    if "page_hinkley" in detector_set and "page_hinkley_alarm" in changes.columns:
        aggregations.append(
            pl.col("page_hinkley_alarm").sum().alias("page_hinkley_count")
        )
        flags.append((pl.col("page_hinkley_count") > 0).alias("has_page_hinkley"))
    return (
        changes.group_by(
            ["source_run", "side", "candidate_name", "step_idx", "pred_batch_id"]
        )
        .agg(*aggregations)
        .with_columns(*flags)
    )


def change_flag_columns(frame: pl.DataFrame) -> tuple[str, ...]:
    return tuple(
        flag
        for flag in (
            "has_any_change",
            "has_market_context_zshift_v1",
            "has_market_context_recursive_cusum_v1",
            "has_hmm_transition_cusum_v1",
            "has_hmm_state_change",
            "has_page_hinkley",
        )
        if flag in frame.columns
    )


def regime_change_quality_summary(
    quality: pl.DataFrame, change_flags: pl.DataFrame
) -> pl.DataFrame:
    if quality.is_empty() or "regime_state" not in quality.columns:
        return pl.DataFrame()
    joined = quality_with_change_flags(quality, change_flags).filter(
        pl.col("regime_status") == "ok"
    )
    if joined.is_empty():
        return pl.DataFrame()
    rows: list[pl.DataFrame] = []
    for flag in change_flag_columns(joined):
        summary = aggregate_quality(
            joined,
            group_cols=[
                "side",
                "candidate_name",
                "regime_model",
                "regime_selected_state_count",
                "regime_state",
                "regime_state_key",
                flag,
            ],
        )
        if not summary.is_empty():
            summary = summary.rename({flag: "change_flag_value"}).with_columns(
                pl.lit(flag).alias("change_flag")
            )
            rows.append(summary)
    return pl.concat(rows, how="diagonal_relaxed") if rows else pl.DataFrame()


def change_quality_summary(
    quality: pl.DataFrame, change_flags: pl.DataFrame
) -> pl.DataFrame:
    if quality.is_empty():
        return pl.DataFrame()
    joined = quality_with_change_flags(quality, change_flags)
    rows: list[pl.DataFrame] = []
    for flag in change_flag_columns(joined):
        summary = aggregate_quality(joined, group_cols=["side", "candidate_name", flag])
        if not summary.is_empty():
            summary = summary.rename({flag: "change_flag_value"}).with_columns(
                pl.lit(flag).alias("change_flag")
            )
            rows.append(summary)
    return pl.concat(rows, how="diagonal_relaxed") if rows else pl.DataFrame()


def quality_with_change_flags(
    quality: pl.DataFrame, change_flags: pl.DataFrame
) -> pl.DataFrame:
    if change_flags.is_empty():
        return quality.with_columns(
            pl.lit(0).alias("change_event_count"),
            pl.lit(False).alias("has_any_change"),
        )
    join_keys = [
        col
        for col in ["source_run", "side", "candidate_name", "step_idx", "pred_batch_id"]
        if col in quality.columns and col in change_flags.columns
    ]
    joined = quality.join(change_flags, on=join_keys, how="left")
    fill_exprs: list[pl.Expr] = []
    for col in (
        "change_event_count",
        "market_context_zshift_v1_count",
        "market_context_recursive_cusum_v1_count",
        "hmm_transition_cusum_v1_count",
        "hmm_state_change_count",
        "page_hinkley_count",
    ):
        if col in joined.columns:
            fill_exprs.append(pl.col(col).fill_null(0))
    for col in (
        "has_any_change",
        "has_market_context_zshift_v1",
        "has_market_context_recursive_cusum_v1",
        "has_hmm_transition_cusum_v1",
        "has_hmm_state_change",
        "has_page_hinkley",
    ):
        if col in joined.columns:
            fill_exprs.append(pl.col(col).fill_null(False))
    return joined.with_columns(*fill_exprs) if fill_exprs else joined


def aggregate_quality(df: pl.DataFrame, *, group_cols: list[str]) -> pl.DataFrame:
    if df.is_empty():
        return pl.DataFrame()
    grouped = (
        df.group_by(group_cols)
        .agg(
            pl.len().alias("windows"),
            pl.col("predicted_positive_count").fill_null(0).sum().alias("signals"),
            pl.col("true_positive_count").fill_null(0).sum().alias("true_positives"),
            pl.col("false_positive_count").fill_null(0).sum().alias("false_positives"),
            pl.col("positive_count").fill_null(0).sum().alias("positives"),
            pl.col("rows").fill_null(0).sum().alias("rows"),
        )
        .with_columns(
            (pl.col("signals") > 0).alias("has_signals"),
            (pl.col("true_positives") / pl.col("signals")).alias("precision"),
            (pl.col("false_positives") / pl.col("signals")).alias(
                "false_discovery_rate"
            ),
            (pl.col("positives") / pl.col("rows")).alias("base_rate"),
            (
                (pl.col("true_positives") / pl.col("signals"))
                / (pl.col("positives") / pl.col("rows"))
            ).alias("precision_lift"),
        )
    )
    return grouped.sort([col for col in group_cols if col in grouped.columns])


def label_target_match(
    df: pl.DataFrame, *, context_type: str, config: TargetMatchConfig
) -> pl.DataFrame:
    if df.is_empty():
        return pl.DataFrame()
    out = df.with_columns(pl.lit(context_type).alias("context_type"))
    favorable = (
        (pl.col("signals").fill_null(0) >= int(config.favorable_min_signals))
        & (pl.col("precision_lift").fill_null(0.0) >= float(config.favorable_min_lift))
        & (
            pl.col("false_discovery_rate").fill_null(1.0)
            <= float(config.favorable_max_fdr)
        )
    )
    avoid = (pl.col("signals").fill_null(0) >= int(config.avoid_min_signals)) & (
        (pl.col("precision_lift").fill_null(0.0) < float(config.avoid_max_lift))
        | (pl.col("false_discovery_rate").fill_null(1.0) >= float(config.avoid_min_fdr))
    )
    return out.with_columns(
        pl.when(favorable)
        .then(pl.lit("favorable"))
        .when(avoid)
        .then(pl.lit("avoid"))
        .otherwise(pl.lit("neutral"))
        .alias("target_match_status"),
        (
            (pl.col("precision_lift").fill_null(0.0) - 1.0)
            + (0.60 - pl.col("false_discovery_rate").fill_null(1.0))
        ).alias("target_match_score"),
    ).sort(
        ["side", "candidate_name", "target_match_status", "target_match_score"],
        descending=[False, False, False, True],
    )


def suppression_candidates_from_matches(*frames: pl.DataFrame) -> pl.DataFrame:
    usable = [frame for frame in frames if not frame.is_empty()]
    if not usable:
        return pl.DataFrame()
    combined = pl.concat(usable, how="diagonal_relaxed")
    avoid = combined.filter(pl.col("target_match_status") == "avoid")
    if avoid.is_empty():
        return pl.DataFrame()
    for col in ("regime_state", "regime_state_key", "change_flag", "change_flag_value"):
        if col not in avoid.columns:
            avoid = avoid.with_columns(pl.lit(None).alias(col))
    avoid = avoid.filter(
        pl.col("change_flag").is_null()
        | ~pl.col("change_flag").is_in(
            ["has_any_change", "has_market_context_zshift_v1"]
        )
    )
    avoid = avoid.filter(
        ~pl.col("context_type").is_in(["change_flag", "regime_state_change_flag"])
        | (pl.col("change_flag_value") == True)  # noqa: E712 - Polars expression requires literal comparison.
    )
    if avoid.is_empty():
        return pl.DataFrame()
    return avoid.with_columns(
        pl.concat_str(
            [
                pl.col("context_type").cast(pl.Utf8),
                pl.lit(":"),
                pl.col("regime_state_key").cast(pl.Utf8).fill_null(""),
                pl.lit(":"),
                pl.col("change_flag").cast(pl.Utf8).fill_null(""),
                pl.lit("="),
                pl.col("change_flag_value").cast(pl.Utf8).fill_null(""),
            ]
        ).alias("suppression_context"),
        (
            pl.when((1.0 - pl.col("precision_lift").fill_null(0.0)) > 0.0)
            .then(1.0 - pl.col("precision_lift").fill_null(0.0))
            .otherwise(0.0)
            + pl.when((pl.col("false_discovery_rate").fill_null(0.0) - 0.60) > 0.0)
            .then(pl.col("false_discovery_rate").fill_null(0.0) - 0.60)
            .otherwise(0.0)
        ).alias("suppression_score"),
    ).sort(
        ["side", "candidate_name", "suppression_score"], descending=[False, False, True]
    )


def label_state_profiles(regime: pl.DataFrame) -> pl.DataFrame:
    if regime.is_empty() or "regime_state_key" not in regime.columns:
        return pl.DataFrame()
    market_cols = sorted(
        col
        for col in regime.columns
        if is_market_model_feature(col) and col.endswith("_last_z")
    )
    if not market_cols:
        return pl.DataFrame()
    market = regime.filter(pl.col("regime_status") == "ok")
    if market.is_empty():
        return pl.DataFrame()
    unique_market = (
        market.select(
            [
                "source_idx",
                "pred_batch_id",
                "regime_selected_state_count",
                "regime_state",
                "regime_state_key",
                *market_cols,
            ]
        )
        .unique(subset=["source_idx", "pred_batch_id"], keep="first")
        .sort(["source_idx", "pred_batch_id"])
    )
    if unique_market.is_empty():
        return pl.DataFrame()
    means = unique_market.group_by(
        ["regime_selected_state_count", "regime_state", "regime_state_key"]
    ).agg(
        *[pl.col(col).mean().alias(col) for col in market_cols],
        pl.len().alias("windows"),
    )
    rows: list[dict[str, Any]] = []
    for row in means.sort("regime_state_key").to_dicts():
        scores = {
            "volatility_score": profile_family_score(row, "market_volatility_state_"),
            "memory_score": profile_family_score(
                row, "market_temporal_memory_transforms_"
            ),
            "chop_score": max(
                profile_family_score(row, "market_rejection_chop_"),
                profile_family_score(row, "market_structural_room_"),
            ),
            "liquidity_score": profile_family_score(
                row, "market_liquidity_volume_pressure_"
            ),
        }
        label = propose_state_label(scores)
        strongest = sorted(scores.items(), key=lambda item: abs(item[1]), reverse=True)[0]
        rows.append(
            {
                "regime_selected_state_count": row.get("regime_selected_state_count"),
                "regime_state": row.get("regime_state"),
                "regime_state_key": row.get("regime_state_key"),
                "state_profile_label": label,
                "windows": row.get("windows"),
                "dominant_profile_component": strongest[0],
                "dominant_profile_score": strongest[1],
                **scores,
            }
        )
    return pl.DataFrame(rows, infer_schema_length=None)


def profile_family_score(row: dict[str, Any], prefix: str) -> float:
    values = [
        float(value)
        for key, value in row.items()
        if key.startswith(prefix)
        and value is not None
        and isinstance(value, (int, float))
        and math.isfinite(float(value))
    ]
    return float(np.mean(values)) if values else 0.0


def propose_state_label(scores: dict[str, float]) -> str:
    volatility = scores.get("volatility_score", 0.0)
    memory = scores.get("memory_score", 0.0)
    chop = scores.get("chop_score", 0.0)
    liquidity = scores.get("liquidity_score", 0.0)
    if volatility <= -0.15 and memory <= -0.15 and liquidity <= 0.10:
        return "quiet_compressed"
    if chop >= 0.15 or (abs(memory) >= 0.25 and volatility < 0.15):
        return "transition_chop"
    if volatility >= 0.15 or liquidity >= 0.15:
        return "expanded_pressure"
    return "unlabeled"


def simulate_regime_gate(
    quality: pl.DataFrame, *, config: RegimeGateConfig
) -> pl.DataFrame:
    if quality.is_empty() or "regime_state_key" not in quality.columns:
        return pl.DataFrame()
    rows: list[dict[str, Any]] = []
    sort_cols = [
        col
        for col in ["source_idx", "pred_batch_id", "side", "candidate_name"]
        if col in quality.columns
    ]
    frame = quality.sort(sort_cols) if sort_cols else quality
    for _key, group in frame.group_by(["side", "candidate_name"], maintain_order=True):
        history: list[dict[str, Any]] = []
        for row in group.to_dicts():
            context_candidates: list[dict[str, Any]] = []
            for context in gate_contexts_for_row(row):
                prior = [
                    item
                    for item in history
                    if item.get("regime_status") == "ok"
                    and gate_context_matches_row(item, context)
                ]
                prior_stats = aggregate_prior_quality(prior)
                action = gate_action_from_prior(prior_stats, config=config)
                context_candidates.append(
                    {
                        **context,
                        "action": action,
                        "prior": prior_stats,
                    }
                )
            selected_context = select_gate_context(context_candidates)
            action = str(selected_context.get("action", "no_history"))
            prior_stats = selected_context.get("prior") or aggregate_prior_quality([])
            before_signals = int(row.get("predicted_positive_count") or 0)
            before_tp = int(row.get("true_positive_count") or 0)
            before_fp = int(row.get("false_positive_count") or 0)
            if action == "allow":
                after_signals = before_signals
                after_tp = before_tp
                after_fp = before_fp
            else:
                after_signals = 0
                after_tp = 0
                after_fp = 0
            rows.append(
                {
                    "source_run": row.get("source_run"),
                    "source_idx": row.get("source_idx"),
                    "side": row.get("side"),
                    "candidate_name": row.get("candidate_name"),
                    "step_idx": row.get("step_idx"),
                    "pred_batch_id": row.get("pred_batch_id"),
                    "regime_selected_state_count": row.get(
                        "regime_selected_state_count"
                    ),
                    "regime_state": row.get("regime_state"),
                    "regime_state_key": row.get("regime_state_key"),
                    "context_type": selected_context.get("context_type"),
                    "context_key": selected_context.get("context_key"),
                    "change_flag": selected_context.get("change_flag"),
                    "change_flag_value": selected_context.get("change_flag_value"),
                    "gate_action": action,
                    "prior_context_windows": prior_stats["windows"],
                    "prior_context_signals": prior_stats["signals"],
                    "prior_context_precision": prior_stats["precision"],
                    "prior_context_base_rate": prior_stats["base_rate"],
                    "prior_context_precision_lift": prior_stats["precision_lift"],
                    "prior_context_false_discovery_rate": prior_stats["fdr"],
                    "rows": row.get("rows"),
                    "positive_count": row.get("positive_count"),
                    "signals_before": before_signals,
                    "true_positives_before": before_tp,
                    "false_positives_before": before_fp,
                    "signals_after": after_signals,
                    "true_positives_after": after_tp,
                    "false_positives_after": after_fp,
                }
            )
            history.append(row)
    out = pl.DataFrame(rows, infer_schema_length=None) if rows else pl.DataFrame()
    if out.is_empty():
        return out
    return out.with_columns(
        (pl.col("true_positives_before") / pl.col("signals_before")).alias(
            "precision_before"
        ),
        (pl.col("false_positives_before") / pl.col("signals_before")).alias(
            "false_discovery_rate_before"
        ),
        (pl.col("true_positives_after") / pl.col("signals_after")).alias(
            "precision_after"
        ),
        (pl.col("false_positives_after") / pl.col("signals_after")).alias(
            "false_discovery_rate_after"
        ),
    )


def gate_contexts_for_row(row: dict[str, Any]) -> list[dict[str, Any]]:
    state_key = row.get("regime_state_key")
    contexts: list[dict[str, Any]] = []
    if state_key is not None:
        contexts.append(
            {
                "context_type": "regime_state_key",
                "context_key": str(state_key),
                "change_flag": None,
                "change_flag_value": None,
            }
        )
    for flag, context_type in (
        ("has_market_context_recursive_cusum_v1", "recursive_cusum"),
        ("has_hmm_transition_cusum_v1", "hmm_transition_cusum"),
    ):
        if flag not in row:
            continue
        value = bool(row.get(flag))
        contexts.append(
            {
                "context_type": context_type,
                "context_key": f"{flag}={str(value).lower()}",
                "change_flag": flag,
                "change_flag_value": value,
            }
        )
        if state_key is not None:
            contexts.append(
                {
                    "context_type": f"regime_state_key+{context_type}",
                    "context_key": f"{state_key}|{flag}={str(value).lower()}",
                    "change_flag": flag,
                    "change_flag_value": value,
                }
            )
    return contexts


def gate_context_matches_row(row: dict[str, Any], context: dict[str, Any]) -> bool:
    context_type = str(context.get("context_type") or "")
    if context_type == "regime_state_key":
        return str(row.get("regime_state_key")) == str(context.get("context_key"))
    flag = context.get("change_flag")
    value = context.get("change_flag_value")
    if not flag:
        return False
    flag_matches = bool(row.get(str(flag))) is bool(value)
    if context_type.startswith("regime_state_key+"):
        state_key = str(context.get("context_key") or "").split("|", 1)[0]
        return str(row.get("regime_state_key")) == state_key and flag_matches
    return flag_matches


def select_gate_context(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    if not candidates:
        return {
            "context_type": None,
            "context_key": None,
            "change_flag": None,
            "change_flag_value": None,
            "action": "no_history",
            "prior": aggregate_prior_quality([]),
        }
    allowed = [item for item in candidates if item.get("action") == "allow"]
    if allowed:
        return sorted(
            allowed,
            key=lambda item: (
                float((item.get("prior") or {}).get("precision_lift") or 0.0),
                int((item.get("prior") or {}).get("signals") or 0),
                str(item.get("context_type") or ""),
            ),
            reverse=True,
        )[0]
    suppressed = [item for item in candidates if item.get("action") == "suppress"]
    if suppressed:
        return sorted(
            suppressed,
            key=lambda item: (
                float((item.get("prior") or {}).get("fdr") or 0.0),
                int((item.get("prior") or {}).get("signals") or 0),
                str(item.get("context_type") or ""),
            ),
            reverse=True,
        )[0]
    return candidates[0] | {"action": "no_history"}


def aggregate_prior_quality(rows: list[dict[str, Any]]) -> dict[str, Any]:
    windows = len(rows)
    signals = sum(int(row.get("predicted_positive_count") or 0) for row in rows)
    tp = sum(int(row.get("true_positive_count") or 0) for row in rows)
    fp = sum(int(row.get("false_positive_count") or 0) for row in rows)
    positives = sum(int(row.get("positive_count") or 0) for row in rows)
    total_rows = sum(int(row.get("rows") or 0) for row in rows)
    precision = float(tp / signals) if signals else None
    base_rate = float(positives / total_rows) if total_rows else None
    return {
        "windows": windows,
        "signals": signals,
        "precision": precision,
        "base_rate": base_rate,
        "precision_lift": float(precision / base_rate)
        if precision is not None and base_rate not in (None, 0.0)
        else None,
        "fdr": float(fp / signals) if signals else None,
    }


def gate_action_from_prior(
    stats: dict[str, Any], *, config: RegimeGateConfig
) -> str:
    if int(stats.get("windows") or 0) < int(config.min_context_windows):
        return "no_history"
    if int(stats.get("signals") or 0) < int(config.min_context_signals):
        return "no_history"
    lift = stats.get("precision_lift")
    fdr = stats.get("fdr")
    if lift is None or fdr is None:
        return "no_history"
    if lift >= float(config.min_precision_lift) and fdr <= float(config.max_fdr):
        return "allow"
    if lift < float(config.avoid_max_lift) or fdr >= float(config.avoid_min_fdr):
        return "suppress"
    return "neutral_suppress"


def regime_gate_context_metrics_from_simulation(frame: pl.DataFrame) -> pl.DataFrame:
    if frame.is_empty():
        return pl.DataFrame()
    return (
        frame.group_by(["side", "candidate_name", "context_type", "context_key"])
        .agg(
            pl.len().alias("windows"),
            pl.col("signals_before").sum().alias("signals_before"),
            pl.col("true_positives_before").sum().alias("true_positives_before"),
            pl.col("false_positives_before").sum().alias("false_positives_before"),
            pl.col("signals_after").sum().alias("signals_after"),
            pl.col("true_positives_after").sum().alias("true_positives_after"),
            pl.col("false_positives_after").sum().alias("false_positives_after"),
        )
        .with_columns(
            (pl.col("true_positives_before") / pl.col("signals_before")).alias(
                "precision_before"
            ),
            (pl.col("true_positives_after") / pl.col("signals_after")).alias(
                "precision_after"
            ),
            (pl.col("false_positives_before") / pl.col("signals_before")).alias(
                "false_discovery_rate_before"
            ),
            (pl.col("false_positives_after") / pl.col("signals_after")).alias(
                "false_discovery_rate_after"
            ),
        )
        .sort(["side", "candidate_name", "context_type", "context_key"])
    )


def regime_gate_decisions_from_simulation(frame: pl.DataFrame) -> pl.DataFrame:
    if frame.is_empty():
        return pl.DataFrame()
    cols = [
        col
        for col in [
            "source_run",
            "source_idx",
            "side",
            "candidate_name",
            "step_idx",
            "pred_batch_id",
            "regime_state_key",
            "context_type",
            "context_key",
            "change_flag",
            "change_flag_value",
            "gate_action",
            "prior_context_windows",
            "prior_context_signals",
            "prior_context_precision_lift",
            "prior_context_false_discovery_rate",
            "signals_before",
            "signals_after",
        ]
        if col in frame.columns
    ]
    return frame.select(cols)


def hmm_filter_diagnostics_artifact(regime: pl.DataFrame) -> pl.DataFrame:
    if regime.is_empty() or "regime_status" not in regime.columns:
        return pl.DataFrame()
    cols = [
        col
        for col in [
            "source_run",
            "source_idx",
            "step_idx",
            "pred_batch_id",
            "regime_model",
            "regime_status",
            "regime_state",
            "regime_selected_state_count",
            "regime_state_key",
            "regime_filter_mode",
            "regime_log_likelihood",
            "regime_aic",
            "regime_bic",
            "regime_current_log_likelihood",
            "regime_posterior_max",
            "regime_posterior_confidence",
            "regime_entropy",
            "regime_changed_from_previous",
            "regime_transition_probability",
            "regime_expected_duration",
            "regime_max_self_transition_probability",
            "regime_max_expected_state_duration",
            "regime_hmm_degenerate_flag",
            "regime_train_state_count",
        ]
        if col in regime.columns
    ]
    posterior_cols = sorted(
        col for col in regime.columns if col.startswith("regime_posterior_state_")
    )
    if not {"source_idx", "pred_batch_id"}.issubset(set(regime.columns)):
        return pl.DataFrame()
    return (
        regime.select([*cols, *posterior_cols])
        .unique(subset=["source_idx", "pred_batch_id"], keep="first")
        .sort(["source_idx", "pred_batch_id"])
    )


def hmm_model_selection_artifact(regime: pl.DataFrame) -> pl.DataFrame:
    if regime.is_empty() or "regime_model_selection_json" not in regime.columns:
        return pl.DataFrame()
    rows: list[dict[str, Any]] = []
    identity_cols = [
        col
        for col in ["source_run", "source_idx", "step_idx", "pred_batch_id"]
        if col in regime.columns
    ]
    unique_rows = (
        regime.select([*identity_cols, "regime_model_selection_json"])
        .unique(subset=["source_idx", "pred_batch_id"], keep="first")
        .sort(["source_idx", "pred_batch_id"])
        .to_dicts()
    )
    for row in unique_rows:
        try:
            entries = json.loads(str(row.get("regime_model_selection_json") or "[]"))
        except json.JSONDecodeError:
            entries = []
        for entry in entries:
            rows.append(
                {
                    **{col: row.get(col) for col in identity_cols},
                    "candidate_state_count": entry.get("candidate_state_count"),
                    "restart": entry.get("restart"),
                    "selection_mode": entry.get("selection_mode"),
                    "status": entry.get("status"),
                    "log_likelihood": entry.get("log_likelihood"),
                    "aic": entry.get("aic"),
                    "bic": entry.get("bic"),
                    "selected": entry.get("selected"),
                }
            )
    return pl.DataFrame(rows, infer_schema_length=None) if rows else pl.DataFrame()


def hmm_transition_matrix_artifact(regime: pl.DataFrame) -> pl.DataFrame:
    if regime.is_empty() or "regime_transition_matrix_json" not in regime.columns:
        return pl.DataFrame()
    rows: list[dict[str, Any]] = []
    identity_cols = [
        col
        for col in [
            "source_run",
            "source_idx",
            "step_idx",
            "pred_batch_id",
            "regime_selected_state_count",
            "regime_state",
            "regime_state_key",
        ]
        if col in regime.columns
    ]
    unique_rows = (
        regime.select([*identity_cols, "regime_transition_matrix_json"])
        .unique(subset=["source_idx", "pred_batch_id"], keep="first")
        .sort(["source_idx", "pred_batch_id"])
        .to_dicts()
    )
    for row in unique_rows:
        try:
            matrix = json.loads(str(row.get("regime_transition_matrix_json") or "[]"))
        except json.JSONDecodeError:
            matrix = []
        for from_state, values in enumerate(matrix):
            if not isinstance(values, list):
                continue
            for to_state, probability in enumerate(values):
                stay_probability = (
                    probability
                    if from_state == to_state and probability is not None
                    else None
                )
                expected_duration = None
                if stay_probability is not None and float(stay_probability) < 1.0:
                    expected_duration = 1.0 / max(
                        1.0 - float(stay_probability), 1e-12
                    )
                rows.append(
                    {
                        **{col: row.get(col) for col in identity_cols},
                        "from_state": int(from_state),
                        "to_state": int(to_state),
                        "transition_probability": probability,
                        "expected_duration_from_state": expected_duration,
                    }
                )
    return pl.DataFrame(rows, infer_schema_length=None) if rows else pl.DataFrame()


def cusum_calibration_artifact(
    context: pl.DataFrame,
    changes: pl.DataFrame,
    hmm_transition_events: pl.DataFrame,
    *,
    config: ChangeConfig,
) -> pl.DataFrame:
    if context.is_empty() or "pred_batch_id" not in context.columns:
        return pl.DataFrame()
    if "source_idx" in context.columns:
        total_windows = context.select(["source_idx", "pred_batch_id"]).unique().height
    else:
        total_windows = context.select(["pred_batch_id"]).unique().height
    rows: list[dict[str, Any]] = []
    detector_specs = [
        (
            "market_context_zshift_v1",
            changes,
            "market_context_zshift_v1_alarm",
            None,
        ),
        (
            "market_context_recursive_cusum_v1",
            changes,
            "market_context_recursive_cusum_v1_alarm",
            "event_rate_targeted",
        ),
        (
            "hmm_transition_cusum_v1",
            hmm_transition_events,
            "hmm_transition_cusum_v1_alarm",
            None,
        ),
    ]
    for detector, frame, alarm_col, calibration_mode in detector_specs:
        if frame.is_empty() or alarm_col not in frame.columns:
            event_rows = 0
            event_windows = 0
        else:
            alarms = frame.filter(pl.col(alarm_col).fill_null(False))
            event_rows = alarms.height
            event_windows = alarms.select(["source_idx", "pred_batch_id"]).unique().height
        event_rate = event_windows / total_windows if total_windows else None
        status = "diagnostic"
        if detector == "market_context_recursive_cusum_v1" and event_rate is not None:
            status = (
                "pass"
                if float(config.target_event_rate_min)
                <= event_rate
                <= float(config.target_event_rate_max)
                else "outside_target"
            )
        rows.append(
            {
                "detector_name": detector,
                "event_rows": event_rows,
                "event_windows": event_windows,
                "total_windows": total_windows,
                "event_window_rate": event_rate,
                "target_event_rate_min": float(config.target_event_rate_min),
                "target_event_rate_max": float(config.target_event_rate_max),
                "cusum_standardization": str(config.cusum_standardization),
                "recursive_cusum_k": float(config.recursive_cusum_k),
                "recursive_cusum_h": float(config.recursive_cusum_h),
                "calibration_mode": calibration_mode,
                "calibration_status": status,
            }
        )
    return pl.DataFrame(rows, infer_schema_length=None)


def count_match_status(df: pl.DataFrame, status: str) -> int:
    if df.is_empty() or "target_match_status" not in df.columns:
        return 0
    return int(df.filter(pl.col("target_match_status") == status).height)


def event_window_count(df: pl.DataFrame) -> int:
    if df.is_empty() or "pred_batch_id" not in df.columns:
        return 0
    keys = [col for col in ("source_idx", "pred_batch_id") if col in df.columns]
    return int(df.select(keys).unique().height) if keys else 0


def write_regime_report(
    path: Path,
    *,
    router_runs: tuple[Path, ...],
    context: pl.DataFrame,
    changes: pl.DataFrame,
    hmm_transition_events: pl.DataFrame,
    state_metrics: pl.DataFrame,
    state_profile_labels: pl.DataFrame,
    regime_target_match: pl.DataFrame,
    change_risk_target_match: pl.DataFrame,
    suppression_candidates: pl.DataFrame,
    regime_gate_simulation: pl.DataFrame,
    hmm_filter_diagnostics: pl.DataFrame,
    hmm_model_selection: pl.DataFrame,
    cusum_calibration: pl.DataFrame,
) -> None:
    lines = [
        "# RPF Ranked Signal Regime Diagnostic",
        "",
        "## Purpose",
        "",
        "Diagnose whether ranked-signal quality is conditional on prediction-safe latent regimes and change-risk alarms.",
        "",
        "## Inputs",
        "",
    ]
    lines.extend([f"- `{run}`" for run in router_runs])
    lines.extend(
        [
            "",
            "## Artifact Contract",
            "",
            "- `regime_context.parquet` contains prediction-time-safe context and past-only regime assignments.",
            "- `regime_signal_quality.parquet` joins matured outcomes for analysis only.",
            "- `change_point_events.parquet` contains CUSUM/Page-Hinkley style change alarms from safe context features.",
            "- `hmm_state_metrics.parquet` summarizes signal quality by inferred state.",
            "- `regime_target_match.parquet` labels states as favorable/neutral/avoid for each target side.",
            "- `change_risk_target_match.parquet` labels change-risk flags by side.",
            "- `regime_suppression_candidates.parquet` lists contexts that should be tested as false-positive suppressors.",
            "",
            "## Summary",
            "",
            f"- context rows: `{context.height}`",
            f"- market change event rows: `{changes.height}`",
            f"- market change event windows: `{event_window_count(changes)}`",
            f"- HMM transition event rows: `{hmm_transition_events.height}`",
            f"- HMM transition event windows: `{event_window_count(hmm_transition_events)}`",
            f"- HMM filter diagnostics: `{hmm_filter_diagnostics.height}`",
            f"- HMM model-selection rows: `{hmm_model_selection.height}`",
            f"- CUSUM calibration rows: `{cusum_calibration.height}`",
            f"- state metric rows: `{state_metrics.height}`",
            f"- suppression candidates: `{suppression_candidates.height}`",
            f"- regime gate simulation rows: `{regime_gate_simulation.height}`",
            "",
            "## HMM/CUSUM Health",
            "",
        ]
    )
    if not cusum_calibration.is_empty():
        lines.extend(
            [
                "| Detector | Event Windows | Event Rate | Target Min | Target Max | Status |",
                "|---|---:|---:|---:|---:|---|",
            ]
        )
        for row in cusum_calibration.to_dicts():
            lines.append(
                "| {detector_name} | {event_windows} | {event_window_rate} | "
                "{target_event_rate_min} | {target_event_rate_max} | "
                "{calibration_status} |".format(
                    **{key: markdown_value(value) for key, value in row.items()}
                )
            )
    else:
        lines.append("- No CUSUM calibration rows were written.")
    lines.append("")
    if not hmm_model_selection.is_empty() and "selected" in hmm_model_selection.columns:
        selected = hmm_model_selection.filter(pl.col("selected") == True)  # noqa: E712
        if not selected.is_empty():
            counts = (
                selected.group_by("candidate_state_count")
                .agg(pl.len().alias("selected_windows"))
                .sort("candidate_state_count")
            )
            lines.extend(
                [
                    "| Selected State Count | Windows |",
                    "|---:|---:|",
                ]
            )
            for row in counts.to_dicts():
                lines.append(
                    "| {candidate_state_count} | {selected_windows} |".format(
                        **{key: markdown_value(value) for key, value in row.items()}
                    )
                )
            lines.append("")
    lines.extend(
        [
            "## State Profile Labels",
            "",
            "| State Key | K | State | Label | Windows | Dominant Component | Score | Volatility | Memory | Chop | Liquidity |",
            "|---|---:|---:|---|---:|---|---:|---:|---:|---:|---:|",
        ]
    )
    for row in state_profile_labels.to_dicts():
        lines.append(
            "| {regime_state_key} | {regime_selected_state_count} | {regime_state} | {state_profile_label} | {windows} | {dominant_profile_component} | "
            "{dominant_profile_score} | {volatility_score} | {memory_score} | {chop_score} | {liquidity_score} |".format(
                **{key: markdown_value(value) for key, value in row.items()}
            )
        )
    lines.extend(
        [
            "",
            "## State Quality",
            "",
            "| Side | Candidate | Model | State Key | K | State | Windows | Signals | TP | FP | Precision | Base | Lift | FDR |",
            "|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in state_metrics.to_dicts():
        lines.append(
            "| {side} | {candidate_name} | {regime_model} | {regime_state_key} | {regime_selected_state_count} | {regime_state} | {windows} | {signals} | "
            "{true_positives} | {false_positives} | {precision} | {base_rate} | {precision_lift} | "
            "{false_discovery_rate} |".format(
                **{key: markdown_value(value) for key, value in row.items()}
            )
        )
    lines.extend(
        [
            "",
            "## Regime Target Match",
            "",
            "| Side | Candidate | State Key | Status | Signals | Precision | Base | Lift | FDR | Score |",
            "|---|---|---|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in regime_target_match.to_dicts():
        lines.append(
            "| {side} | {candidate_name} | {regime_state_key} | {target_match_status} | {signals} | "
            "{precision} | {base_rate} | {precision_lift} | {false_discovery_rate} | {target_match_score} |".format(
                **{key: markdown_value(value) for key, value in row.items()}
            )
        )
    lines.extend(
        [
            "",
            "## Change-Risk Target Match",
            "",
            "| Side | Candidate | Flag | Value | Status | Signals | Precision | Base | Lift | FDR |",
            "|---|---|---|---|---|---:|---:|---:|---:|---:|",
        ]
    )
    for row in change_risk_target_match.to_dicts():
        lines.append(
            "| {side} | {candidate_name} | {change_flag} | {change_flag_value} | {target_match_status} | "
            "{signals} | {precision} | {base_rate} | {precision_lift} | {false_discovery_rate} |".format(
                **{key: markdown_value(value) for key, value in row.items()}
            )
        )
    lines.extend(
        [
            "",
            "## Suppression Candidates",
            "",
            "| Side | Candidate | Context | Signals | Lift | FDR | Suppression Score |",
            "|---|---|---|---:|---:|---:|---:|",
        ]
    )
    for row in suppression_candidates.to_dicts()[:30]:
        lines.append(
            "| {side} | {candidate_name} | {suppression_context} | {signals} | "
            "{precision_lift} | {false_discovery_rate} | {suppression_score} |".format(
                **{key: markdown_value(value) for key, value in row.items()}
            )
        )
    gate_summary = gate_simulation_summary(regime_gate_simulation)
    lines.extend(
        [
            "",
            "## Prequential Regime Gate Simulation",
            "",
            "| Side | Candidate | Windows | Signals Before | Signals After | Precision Before | Precision After | FDR Before | FDR After |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in gate_summary.to_dicts():
        lines.append(
            "| {side} | {candidate_name} | {windows} | {signals_before} | {signals_after} | "
            "{precision_before} | {precision_after} | {false_discovery_rate_before} | {false_discovery_rate_after} |".format(
                **{key: markdown_value(value) for key, value in row.items()}
            )
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- A useful regime layer should show materially different precision/lift/FDR by state.",
            "- High regime entropy or frequent change alarms should be treated as risk context, not as a signal by itself.",
            "- Favorable/avoid labels are diagnostic; use them for the next shadow suppression replay before changing live routing.",
            "- This command does not modify router decisions; promotion requires a separate walk-forward router mode.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n")


def gate_simulation_summary(frame: pl.DataFrame) -> pl.DataFrame:
    if frame.is_empty():
        return pl.DataFrame()
    return (
        frame.group_by(["side", "candidate_name"])
        .agg(
            pl.len().alias("windows"),
            pl.col("signals_before").sum().alias("signals_before"),
            pl.col("true_positives_before").sum().alias("true_positives_before"),
            pl.col("false_positives_before").sum().alias("false_positives_before"),
            pl.col("signals_after").sum().alias("signals_after"),
            pl.col("true_positives_after").sum().alias("true_positives_after"),
            pl.col("false_positives_after").sum().alias("false_positives_after"),
        )
        .with_columns(
            (pl.col("true_positives_before") / pl.col("signals_before")).alias(
                "precision_before"
            ),
            (pl.col("true_positives_after") / pl.col("signals_after")).alias(
                "precision_after"
            ),
            (pl.col("false_positives_before") / pl.col("signals_before")).alias(
                "false_discovery_rate_before"
            ),
            (pl.col("false_positives_after") / pl.col("signals_after")).alias(
                "false_discovery_rate_after"
            ),
        )
        .sort(["side", "candidate_name"])
    )


def summarize_stage(
    context: pl.DataFrame, changes: pl.DataFrame, state_metrics: pl.DataFrame
) -> dict[str, Any]:
    return {
        "context_rows": context.height,
        "change_events": changes.height,
        "state_metric_rows": state_metrics.height,
        "sides": sorted(context["side"].unique().to_list())
        if "side" in context.columns and not context.is_empty()
        else [],
        "candidates": sorted(context["candidate_name"].unique().to_list())
        if "candidate_name" in context.columns and not context.is_empty()
        else [],
    }


def to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return float(value)
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def run_root_for_args() -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return OUTPUT_ROOT / f"{timestamp}_rank_signal_regime_diagnostic"


if __name__ == "__main__":
    raise SystemExit(main())
