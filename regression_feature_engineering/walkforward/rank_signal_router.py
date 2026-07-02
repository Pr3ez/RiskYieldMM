"""Adaptive RPF ranked-signal router.

The router evaluates a small fixed candidate pool for each side on validation
batches only, selects the best passing candidate, then scores the next unseen
prediction batch.  It is intentionally separate from the Optuna-style
``rank_signal`` runner.
"""

from __future__ import annotations

import argparse
import json
import math
import time
import traceback
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

from regression_feature_engineering.walkforward.ablation import select_ablation_features
from regression_feature_engineering.walkforward.classification.sequence import SEQUENCE_NONE
from regression_feature_engineering.walkforward.classification.targets import DOWN_EXTREME, UP_EXTREME
from regression_feature_engineering.walkforward.config import load_clean_config
from regression_feature_engineering.walkforward.data import resolve_context
from regression_feature_engineering.walkforward.policy import load_panel_features
from regression_feature_engineering.walkforward.rank_signal import (
    BATCH_STATE_GATE_MODES,
    BATCH_STATE_GATE_OFF,
    BatchStateGateConfig,
    SEQUENCE_CAUSAL_ROCKET_V1,
    SIDE_DOWN,
    SIDE_UP,
    DecisionConfig,
    ElasticNetRelevanceConfig,
    RankModelConfig,
    RankTrialConfig,
    RocketConfig,
    aggregate_prediction_metrics,
    binary_decision_metrics,
    binary_col,
    failed_payload,
    finite,
    run_rank_fold,
    select_window_block,
    simple_window_metric_row,
    trial_config_payload,
    write_rows_parquet,
)
from regression_feature_engineering.walkforward.rank_signal_row_diagnostic import (
    add_signal_outcome_labels,
    build_row_rpf_context,
    safe_row_context_features,
)
from regression_feature_engineering.walkforward.rank_signal_row_rule_bank import (
    RowRuleEligibilityConfig,
    RowRuleReliabilityConfig,
    build_forward_folds as build_row_rule_forward_folds,
    chronological_source_blocks as chronological_row_rule_blocks,
    compare_fold_summary_with_raw,
    compare_overall_summary_with_raw,
    filter_eligible_row_rules,
    parse_float_tuple,
    parse_optional_csv,
    replay_rules,
    replay_rules_union,
    recent_shadow_history_rows,
    row_rule_feature_family,
    rule_reliability_rows,
    safe_numeric_feature_columns as safe_row_rule_numeric_feature_columns,
    select_prequential_reliable_rules,
    summarize_acceptance,
    train_row_rules,
)
from regression_feature_engineering.walkforward.reports import append_event, write_json, write_markdown, write_stage_status
from regression_feature_engineering.walkforward.windows import RPFWindow, build_windows, read_windows
from scripts.project_paths import ensure_project_root_on_path


PROJECT_ROOT = ensure_project_root_on_path(Path(__file__))
OUTPUT_ROOT = PROJECT_ROOT / "test_output" / "rpf_ranked_signal_router"
SIDES = (SIDE_UP, SIDE_DOWN)
SELECTION_VALIDATION_ONLY = "validation_only"
SELECTION_PREQUENTIAL_RELIABILITY_V1 = "prequential_reliability_v1"
SELECTION_CONTEXT_RULE_V1 = "context_rule_v1"
CANDIDATE_SET_DEFAULT_V1 = "default_v1"
CANDIDATE_SET_PRUNED_RELIABILITY_V1 = "pruned_reliability_v1"
WARMUP_NO_SIGNAL = "no_signal"
SPECIALIST_ENTRY_OFF = "off"
SPECIALIST_ENTRY_DOWN_NONE_VALIDATION_QUIET_V1 = "down_none_validation_quiet_v1"
SPECIALIST_ENTRY_MODES = (SPECIALIST_ENTRY_OFF, SPECIALIST_ENTRY_DOWN_NONE_VALIDATION_QUIET_V1)
ROW_RULE_GATE_OFF = "off"
ROW_RULE_GATE_PREQUENTIAL_RELIABILITY_V1 = "prequential_reliability_v1"
ROW_RULE_GATE_MODES = (ROW_RULE_GATE_OFF, ROW_RULE_GATE_PREQUENTIAL_RELIABILITY_V1)
ROW_RULE_GATE_OUTPUT_SHADOW = "shadow"
ROW_RULE_GATE_OUTPUT_ACTIVE_CANDIDATE = "active_candidate"
ROW_RULE_GATE_OUTPUT_ACTIVE_DOWN_CANDIDATE = "active_down_candidate"
ROW_RULE_GATE_OUTPUT_MODES = (
    ROW_RULE_GATE_OUTPUT_SHADOW,
    ROW_RULE_GATE_OUTPUT_ACTIVE_CANDIDATE,
    ROW_RULE_GATE_OUTPUT_ACTIVE_DOWN_CANDIDATE,
)


@dataclass(frozen=True)
class RouterGateConfig:
    min_validation_signal_count: int = 3
    min_validation_precision_lift: float = 1.10
    max_validation_false_discovery_rate: float = 0.60
    min_validation_active_window_rate: float = 0.10
    max_validation_zero_signal_window_rate: float = 0.90
    min_validation_active_batch_count: int = 0
    min_validation_lift_positive_batch_rate: float = 0.0
    min_validation_median_active_precision_lift: float = 0.0
    max_validation_median_active_false_discovery_rate: float = 1.0


@dataclass(frozen=True)
class ReliabilityConfig:
    lookback_windows: int = 60
    min_history_windows: int = 20
    min_signals: int = 20
    min_active_windows: int = 5
    min_precision_lift_lcb: float = 1.05
    min_window_selection_lift: float = 1.0
    min_selected_window_row_lift_lcb: float = 1.05
    max_false_discovery_rate: float = 0.60
    lcb_z: float = 1.0
    warmup_policy: str = WARMUP_NO_SIGNAL
    up_min_precision_lift_lcb: float | None = None
    down_min_precision_lift_lcb: float | None = None
    up_min_selected_window_row_lift_lcb: float | None = None
    down_min_selected_window_row_lift_lcb: float | None = None


@dataclass(frozen=True)
class ContextRule:
    side: str
    candidate_name: str
    feature: str
    direction: str
    threshold: float
    train_score: float
    train_precision: float | None = None
    train_lift: float | None = None
    train_signals: int | None = None


@dataclass(frozen=True)
class CandidateSpec:
    name: str
    side: str
    config: RankTrialConfig
    diagnostic: bool = False


def main() -> int:
    args = parse_args()
    config = load_clean_config(args.config)
    asset = str(args.asset or config.asset)
    root = str(args.root or config.root)
    run_root = run_root_for_args(asset=asset, root=root)
    run_root.mkdir(parents=True, exist_ok=True)
    events_path = run_root / "events.jsonl"
    append_event(events_path, "stage_start", command="rank_signal_router", asset=asset, root=root)

    base_run = Path(args.base_run)
    base_windows = read_windows(base_run / "frozen_windows.parquet")
    batch_index_path = base_run / "batch_index.parquet"
    batch_index = pl.read_parquet(batch_index_path) if batch_index_path.exists() else None
    if batch_index is None:
        raise ValueError("rank_signal_router requires batch_index.parquet in --base-run")

    selected_outer_windows = select_window_block(
        base_windows,
        n_steps=int(args.outer_window_count),
        window_end_offset_steps=int(args.window_end_offset_steps),
    )
    if not selected_outer_windows:
        raise ValueError("No outer windows selected")

    contexts = {
        SIDE_UP: resolve_context(project_root=PROJECT_ROOT, asset=asset, root=root, target_col=UP_EXTREME),
        SIDE_DOWN: resolve_context(project_root=PROJECT_ROOT, asset=asset, root=root, target_col=DOWN_EXTREME),
    }
    side_features = {
        SIDE_UP: side_feature_columns(contexts[SIDE_UP], args.up_tabular_panel_path, args.feature_ablation),
        SIDE_DOWN: side_feature_columns(contexts[SIDE_DOWN], args.down_tabular_panel_path, args.feature_ablation),
    }
    side_sequence_features = {
        SIDE_UP: side_sequence_columns(contexts[SIDE_UP], args.up_sequence_panel_path),
        SIDE_DOWN: side_sequence_columns(contexts[SIDE_DOWN], args.down_sequence_panel_path),
    }
    candidates = build_candidate_set(
        str(args.candidate_set),
        fp_cost=float(args.fp_cost),
        fn_cost=float(args.fn_cost),
        high_target_positive_rate_threshold=float(args.high_target_positive_rate_threshold),
        high_false_positive_rate_threshold=float(args.high_false_positive_rate_threshold),
        include_diagnostic_candidates=bool(args.include_diagnostic_candidates),
    )
    candidate_name_allowlist = parse_candidate_name_allowlist(str(args.candidate_name_allowlist))
    candidates = filter_candidates_by_name_allowlist(candidates, candidate_name_allowlist)
    candidates = apply_batch_state_gate_overrides(
        candidates,
        BatchStateGateConfig(
            mode=str(args.batch_state_gate_mode),
            prefix_rows=int(args.batch_state_gate_prefix_rows),
            min_positive_rate=float(args.batch_state_gate_min_positive_rate),
            probability_threshold=float(args.batch_state_gate_probability_threshold),
            c=float(args.batch_state_gate_c),
            max_iter=int(args.batch_state_gate_max_iter),
            min_train_batches=int(args.batch_state_gate_min_train_batches),
            min_positive_batches=int(args.batch_state_gate_min_positive_batches),
            min_negative_batches=int(args.batch_state_gate_min_negative_batches),
        ),
    )
    validate_candidate_inputs(candidates, side_sequence_features)

    candidate_window_maps = {
        (candidate.config.train_batches, candidate.config.val_batches): windows_by_pred_batch(
            batch_index,
            train_batches=int(candidate.config.train_batches),
            val_batches=int(candidate.config.val_batches),
        )
        for candidate in candidates
    }
    gates = RouterGateConfig(
        min_validation_signal_count=int(args.min_validation_signal_count),
        min_validation_precision_lift=float(args.min_validation_precision_lift),
        max_validation_false_discovery_rate=float(args.max_validation_false_discovery_rate),
        min_validation_active_window_rate=float(args.min_validation_active_window_rate),
        max_validation_zero_signal_window_rate=float(args.max_validation_zero_signal_window_rate),
        min_validation_active_batch_count=int(args.min_validation_active_batch_count),
        min_validation_lift_positive_batch_rate=float(args.min_validation_lift_positive_batch_rate),
        min_validation_median_active_precision_lift=float(args.min_validation_median_active_precision_lift),
        max_validation_median_active_false_discovery_rate=float(args.max_validation_median_active_false_discovery_rate),
    )
    reliability_config = ReliabilityConfig(
        lookback_windows=int(args.reliability_lookback_windows),
        min_history_windows=int(args.reliability_min_history_windows),
        min_signals=int(args.reliability_min_signals),
        min_active_windows=int(args.reliability_min_active_windows),
        min_precision_lift_lcb=float(args.reliability_min_precision_lift_lcb),
        min_window_selection_lift=float(args.reliability_min_window_selection_lift),
        min_selected_window_row_lift_lcb=float(args.reliability_min_selected_window_row_lift_lcb),
        max_false_discovery_rate=float(args.reliability_max_false_discovery_rate),
        lcb_z=float(args.reliability_lcb_z),
        warmup_policy=str(args.reliability_warmup_policy),
        up_min_precision_lift_lcb=args.up_reliability_min_precision_lift_lcb,
        down_min_precision_lift_lcb=args.down_reliability_min_precision_lift_lcb,
        up_min_selected_window_row_lift_lcb=args.up_reliability_min_selected_window_row_lift_lcb,
        down_min_selected_window_row_lift_lcb=args.down_reliability_min_selected_window_row_lift_lcb,
    )
    selection_mode = str(args.selection_mode)
    specialist_entry_mode = str(args.specialist_entry_mode)
    context_rules = load_context_rules(args.context_rule_path) if args.context_rule_path else {}
    if selection_mode == SELECTION_CONTEXT_RULE_V1 and not context_rules:
        raise ValueError("--context-rule-path is required when --selection-mode context_rule_v1")

    router_config = {
        "asset": asset,
        "root": root,
        "candidate_set": str(args.candidate_set),
        "candidate_name_allowlist": list(candidate_name_allowlist),
        "selection_mode": selection_mode,
        "specialist_entry_mode": specialist_entry_mode,
        "context_rule_path": str(args.context_rule_path) if args.context_rule_path else None,
        "context_rules": [context_rule_config_row(rule) for rule in context_rules.values()],
        "outer_window_count": int(args.outer_window_count),
        "window_end_offset_steps": int(args.window_end_offset_steps),
        "evaluation_block_size": int(args.evaluation_block_size),
        "gates": gates.__dict__,
        "reliability": reliability_config.__dict__,
        "row_rule_gate": row_rule_gate_config_row(args),
        "candidates": [candidate_config_row(candidate) for candidate in candidates],
    }
    write_json(run_root / "router_config.json", router_config)

    print(
        "[rpf-router] start "
        f"asset={asset} root={root} windows={len(selected_outer_windows)} "
        f"candidates={len(candidates)} run={run_root}",
        flush=True,
    )

    validation_rows: list[dict[str, Any]] = []
    selected_rows: list[dict[str, Any]] = []
    window_rows: list[dict[str, Any]] = []
    score_rows: list[dict[str, Any]] = []
    validation_score_rows: list[dict[str, Any]] = []
    validation_window_rows: list[dict[str, Any]] = []
    selected_feature_rows: list[dict[str, Any]] = []
    sequence_rows: list[dict[str, Any]] = []
    candidate_prediction_window_rows: list[dict[str, Any]] = []
    candidate_prediction_score_rows_out: list[dict[str, Any]] = []
    reliability_state_rows: list[dict[str, Any]] = []
    selection_audit_rows: list[dict[str, Any]] = []
    batch_regime_rows: list[dict[str, Any]] = []

    log_every = max(0, int(args.log_every_windows))
    for window_idx, outer_window in enumerate(selected_outer_windows, start=1):
        if log_every and (window_idx == 1 or window_idx == len(selected_outer_windows) or window_idx % log_every == 0):
            print(f"[rpf-router] window_start {window_idx}/{len(selected_outer_windows)} pred_batch={outer_window.pred_batch_id}", flush=True)
        for side in SIDES:
            side_candidates = [candidate for candidate in candidates if candidate.side == side]
            candidate_results = []
            for candidate in side_candidates:
                pred_map = candidate_window_maps[(candidate.config.train_batches, candidate.config.val_batches)]
                candidate_window = pred_map.get(int(outer_window.pred_batch_id))
                if candidate_window is None:
                    result = failed_candidate_result(candidate, outer_window, "missing_candidate_window")
                else:
                    result = evaluate_candidate(
                        candidate=candidate,
                        context=contexts[side],
                        window=candidate_window,
                        feature_columns=side_features[side],
                        sequence_feature_columns=side_sequence_features[side] if candidate.config.sequence.mode != SEQUENCE_NONE else (),
                        task_type=str(args.task_type),
                        thread_count=int(args.thread_count),
                        gates=gates,
                    )
                validation_rows.append(candidate_validation_row(result))
                validation_score_rows.extend(candidate_validation_score_rows(result))
                validation_window_rows.extend(candidate_validation_window_rows(result))
                selected_feature_rows.extend(candidate_selected_feature_rows(result))
                sequence_rows.append(candidate_sequence_row(result))
                candidate_results.append(result)

            reliability_by_candidate = {
                result["candidate"].name: reliability_state_for_candidate(
                    candidate=result["candidate"],
                    history_rows=candidate_prediction_window_rows,
                    config=reliability_config,
                )
                for result in candidate_results
            }
            reliability_state_rows.extend(
                {
                    "side": side,
                    "router_step_idx": int(outer_window.step_idx),
                    "router_pred_batch_id": int(outer_window.pred_batch_id),
                    **state,
                }
                for state in reliability_by_candidate.values()
            )
            selected = select_router_candidate(
                candidate_results,
                reliability_by_candidate=reliability_by_candidate,
                selection_mode=selection_mode,
                reliability_config=reliability_config,
                specialist_entry_mode=specialist_entry_mode,
                context_rules=context_rules,
            )
            selected_rows.append(selected_candidate_row(selected, outer_window, side))
            selection_audit_rows.extend(
                candidate_selection_audit_rows(
                    candidate_results,
                    selected=selected,
                    reliability_by_candidate=reliability_by_candidate,
                    reliability_config=reliability_config,
                    selection_mode=selection_mode,
                    outer_window=outer_window,
                    context_rules=context_rules,
                )
            )
            routed = routed_prediction_payload(selected, outer_window, side)
            batch_regime_rows.append(
                batch_regime_diagnostic_row(
                    side=side,
                    outer_window=outer_window,
                    selected=selected,
                    routed_window_metric=routed["window_metric"],
                    prior_window_rows=window_rows,
                    reliability_by_candidate=reliability_by_candidate,
                )
            )
            window_rows.append(routed["window_metric"])
            score_rows.extend(routed["scores"])
            current_prediction_window_rows = [candidate_prediction_window_row(result) for result in candidate_results]
            candidate_prediction_window_rows.extend(current_prediction_window_rows)
            if bool(args.write_candidate_prediction_scores) or row_rule_gate_enabled(args):
                for result in candidate_results:
                    candidate_prediction_score_rows_out.extend(candidate_prediction_score_rows(result))
        if log_every and (window_idx == 1 or window_idx == len(selected_outer_windows) or window_idx % log_every == 0):
            print(f"[rpf-router] window_done {window_idx}/{len(selected_outer_windows)} pred_batch={outer_window.pred_batch_id}", flush=True)

    decision_rows = [row for row in score_rows if int(row.get("decision", 0)) == 1]
    row_rule_gate_outputs = build_row_rule_gate_outputs(
        candidate_prediction_score_rows_out,
        context=contexts[str(args.row_rule_gate_side)],
        selected_outer_windows=selected_outer_windows,
        run_root=run_root,
        args=args,
    )
    row_rule_active_outputs = build_row_rule_active_outputs(
        candidate_prediction_score_rows_out,
        row_rule_gate_decisions=row_rule_gate_outputs.get("decision_rows", []),
        selected_outer_windows=selected_outer_windows,
        args=args,
        fp_cost=float(args.fp_cost),
        fn_cost=float(args.fn_cost),
        high_target_positive_rate_threshold=float(args.high_target_positive_rate_threshold),
        high_false_positive_rate_threshold=float(args.high_false_positive_rate_threshold),
    )
    block_rows, side_summary = summarize_router_outputs(
        score_rows,
        window_rows,
        block_size=int(args.evaluation_block_size),
        fp_cost=float(args.fp_cost),
        fn_cost=float(args.fn_cost),
    )
    conflicts = conflict_diagnostics(score_rows)

    write_rows_parquet(run_root / "candidate_validation_metrics.parquet", validation_rows)
    write_rows_parquet(run_root / "candidate_validation_scores.parquet", validation_score_rows)
    write_rows_parquet(run_root / "candidate_validation_window_metrics.parquet", validation_window_rows)
    write_rows_parquet(run_root / "selected_features.parquet", selected_feature_rows)
    write_rows_parquet(run_root / "sequence_diagnostics.parquet", sequence_rows)
    write_rows_parquet(run_root / "candidate_prediction_window_metrics.parquet", candidate_prediction_window_rows)
    write_rows_parquet(run_root / "candidate_reliability_state.parquet", reliability_state_rows)
    write_rows_parquet(run_root / "candidate_selection_audit.parquet", selection_audit_rows)
    write_rows_parquet(run_root / "batch_regime_diagnostics.parquet", batch_regime_rows)
    write_rows_parquet(
        run_root / "candidate_prediction_scores.parquet",
        candidate_prediction_score_rows_out if bool(args.write_candidate_prediction_scores) or row_rule_gate_enabled(args) else [],
    )
    write_rows_parquet(run_root / "selected_candidates.parquet", selected_rows)
    write_rows_parquet(run_root / "router_window_metrics.parquet", window_rows)
    write_rows_parquet(run_root / "router_prediction_scores.parquet", score_rows)
    write_rows_parquet(run_root / "router_decisions.parquet", decision_rows)
    write_rows_parquet(run_root / "block_summary.parquet", block_rows)
    write_rows_parquet(run_root / "row_rule_gate_signal_rows.parquet", row_rule_gate_outputs.get("signal_rows", []))
    write_rows_parquet(run_root / "row_rule_gate_rule_candidates.parquet", row_rule_gate_outputs.get("candidate_rows", []))
    write_rows_parquet(run_root / "row_rule_gate_rules.parquet", row_rule_gate_outputs.get("rule_rows", []))
    write_rows_parquet(run_root / "row_rule_gate_rule_acceptance.parquet", row_rule_gate_outputs.get("rule_acceptance_rows", []))
    write_rows_parquet(run_root / "row_rule_gate_shadow_rule_acceptance.parquet", row_rule_gate_outputs.get("shadow_rule_acceptance_rows", []))
    write_rows_parquet(run_root / "row_rule_gate_rule_reliability.parquet", row_rule_gate_outputs.get("reliability_snapshot_rows", []))
    write_rows_parquet(run_root / "row_rule_gate_selection_audit.parquet", row_rule_gate_outputs.get("selection_audit_rows", []))
    write_rows_parquet(run_root / "row_rule_gate_decisions.parquet", row_rule_gate_outputs.get("decision_rows", []))
    write_rows_parquet(run_root / "row_rule_gate_fold_summary.parquet", row_rule_gate_outputs.get("fold_summary", []))
    write_rows_parquet(run_root / "row_rule_gate_overall_summary.parquet", row_rule_gate_outputs.get("overall_summary", []))
    write_rows_parquet(run_root / "row_rule_gate_fold_comparison.parquet", row_rule_gate_outputs.get("fold_comparison", []))
    write_rows_parquet(run_root / "row_rule_gate_overall_comparison.parquet", row_rule_gate_outputs.get("overall_comparison", []))
    write_rows_parquet(run_root / "row_rule_active_prediction_scores.parquet", row_rule_active_outputs.get("score_rows", []))
    write_rows_parquet(run_root / "row_rule_active_decisions.parquet", row_rule_active_outputs.get("decision_rows", []))
    write_rows_parquet(run_root / "row_rule_active_window_metrics.parquet", row_rule_active_outputs.get("window_rows", []))
    write_rows_parquet(run_root / "row_rule_active_block_summary.parquet", row_rule_active_outputs.get("block_rows", []))
    write_json(run_root / "row_rule_active_side_summary.json", row_rule_active_outputs.get("side_summary", {}))
    effective_outputs = resolve_effective_router_outputs(
        score_rows=score_rows,
        decision_rows=decision_rows,
        window_rows=window_rows,
        block_rows=block_rows,
        side_summary=side_summary,
        row_rule_active_outputs=row_rule_active_outputs,
        args=args,
    )
    write_rows_parquet(run_root / "effective_prediction_scores.parquet", effective_outputs["score_rows"])
    write_rows_parquet(run_root / "effective_decisions.parquet", effective_outputs["decision_rows"])
    write_rows_parquet(run_root / "effective_window_metrics.parquet", effective_outputs["window_rows"])
    write_rows_parquet(run_root / "effective_block_summary.parquet", effective_outputs["block_rows"])
    write_json(run_root / "effective_side_summary.json", effective_outputs["side_summary"])
    write_json(
        run_root / "effective_artifact_source.json",
        {
            "prediction_source": effective_outputs["prediction_source"],
            "requested_output_mode": str(args.row_rule_gate_output_mode),
            "row_rule_gate_mode": str(args.row_rule_gate_mode),
            "row_rule_active_score_rows": len(row_rule_active_outputs.get("score_rows", [])),
            "row_rule_active_decision_rows": len(row_rule_active_outputs.get("decision_rows", [])),
        },
    )
    effective_conflicts = conflict_diagnostics(effective_outputs["score_rows"])
    write_rows_parquet(
        run_root / "reliability_block_summary.parquet",
        reliability_block_summary(candidate_prediction_window_rows, block_size=int(args.evaluation_block_size)),
    )
    write_rows_parquet(run_root / "conflict_diagnostics.parquet", conflicts)
    write_rows_parquet(run_root / "effective_conflict_diagnostics.parquet", effective_conflicts)
    write_json(run_root / "side_summary.json", side_summary)
    write_router_report(
        run_root,
        router_config=router_config,
        side_summary=side_summary,
        effective_side_summary=effective_outputs["side_summary"],
        effective_prediction_source=str(effective_outputs["prediction_source"]),
    )
    write_stage_status(
        run_root / "stage_status.json",
        stage="rank_signal_router",
        status="complete",
        summary={
            "asset": asset,
            "root": root,
            "outer_window_count": len(selected_outer_windows),
            "candidate_validation_rows": len(validation_rows),
            "candidate_validation_score_rows": len(validation_score_rows),
            "candidate_validation_window_rows": len(validation_window_rows),
            "selected_feature_rows": len(selected_feature_rows),
            "candidate_prediction_window_rows": len(candidate_prediction_window_rows),
            "candidate_reliability_state_rows": len(reliability_state_rows),
            "candidate_selection_audit_rows": len(selection_audit_rows),
            "batch_regime_diagnostic_rows": len(batch_regime_rows),
            "decision_rows": len(decision_rows),
            "conflict_rows": len(conflicts),
            "effective_conflict_rows": len(effective_conflicts),
            "row_rule_gate_mode": str(args.row_rule_gate_mode),
            "row_rule_gate_signal_rows": len(row_rule_gate_outputs.get("signal_rows", [])),
            "row_rule_gate_decision_rows": len(row_rule_gate_outputs.get("decision_rows", [])),
            "row_rule_gate_output_mode": str(args.row_rule_gate_output_mode),
            "row_rule_active_decision_rows": len(row_rule_active_outputs.get("decision_rows", [])),
            "effective_prediction_source": effective_outputs["prediction_source"],
            "effective_score_rows": len(effective_outputs["score_rows"]),
            "effective_decision_rows": len(effective_outputs["decision_rows"]),
        },
    )
    append_event(events_path, "stage_done", run=str(run_root))
    print(f"[rpf-router] done run={run_root}", flush=True)
    return 0


def side_feature_columns(context: Any, panel_path: str | None, feature_ablation: str) -> tuple[str, ...]:
    columns = select_ablation_features(context.manifest.feature_columns, str(feature_ablation))
    return load_panel_features(panel_path, columns) if panel_path else columns


def side_sequence_columns(context: Any, panel_path: str | None) -> tuple[str, ...]:
    return load_panel_features(panel_path, context.manifest.feature_columns) if panel_path else ()


def build_candidate_set(
    candidate_set: str,
    *,
    fp_cost: float,
    fn_cost: float,
    high_target_positive_rate_threshold: float,
    high_false_positive_rate_threshold: float,
    include_diagnostic_candidates: bool,
) -> list[CandidateSpec]:
    if candidate_set == CANDIDATE_SET_DEFAULT_V1:
        return candidate_set_default_v1(
            fp_cost=fp_cost,
            fn_cost=fn_cost,
            high_target_positive_rate_threshold=high_target_positive_rate_threshold,
            high_false_positive_rate_threshold=high_false_positive_rate_threshold,
        )
    if candidate_set == CANDIDATE_SET_PRUNED_RELIABILITY_V1:
        return candidate_set_pruned_reliability_v1(
            fp_cost=fp_cost,
            fn_cost=fn_cost,
            high_target_positive_rate_threshold=high_target_positive_rate_threshold,
            high_false_positive_rate_threshold=high_false_positive_rate_threshold,
            include_diagnostic_candidates=include_diagnostic_candidates,
        )
    raise ValueError(f"Unsupported candidate set: {candidate_set}")


def parse_candidate_name_allowlist(raw: str | None) -> tuple[str, ...]:
    return tuple(dict.fromkeys(item.strip() for item in str(raw or "").split(",") if item.strip()))


def filter_candidates_by_name_allowlist(candidates: list[CandidateSpec], allowlist: tuple[str, ...]) -> list[CandidateSpec]:
    if not allowlist:
        return candidates
    available = {candidate.name for candidate in candidates}
    requested = set(allowlist)
    missing = sorted(requested - available)
    if missing:
        raise ValueError(
            "Unknown --candidate-name-allowlist entries: "
            f"{missing}; available candidates: {sorted(available)}"
        )
    filtered = [candidate for candidate in candidates if candidate.name in requested]
    if not filtered:
        raise ValueError("--candidate-name-allowlist removed every candidate")
    return filtered


def load_context_rules(path: str | Path | None) -> dict[tuple[str, str], ContextRule]:
    if path is None or str(path) == "":
        return {}
    rule_path = Path(path)
    if rule_path.is_dir():
        rule_path = rule_path / "meta_router_rules.parquet"
    if not rule_path.exists():
        raise FileNotFoundError(f"--context-rule-path does not exist: {rule_path}")
    if rule_path.suffix != ".parquet":
        raise ValueError(f"--context-rule-path must point to a parquet rule file or run directory: {rule_path}")
    frame = pl.read_parquet(rule_path)
    required = {"side", "candidate_name", "feature", "direction", "threshold", "train_score"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"Context rule file missing required columns: {missing}")
    rules: dict[tuple[str, str], ContextRule] = {}
    for row in frame.to_dicts():
        rule = ContextRule(
            side=str(row["side"]),
            candidate_name=str(row["candidate_name"]),
            feature=str(row["feature"]),
            direction=str(row["direction"]),
            threshold=float(row["threshold"]),
            train_score=float(row.get("train_score") or 0.0),
            train_precision=optional_float(row.get("train_precision")),
            train_lift=optional_float(row.get("train_lift")),
            train_signals=optional_int(row.get("train_signals")),
        )
        key = (rule.side, rule.candidate_name)
        if key in rules:
            raise ValueError(f"Duplicate context rule for {key}")
        if rule.direction not in {"higher_good", "lower_good"}:
            raise ValueError(f"Unsupported context rule direction for {key}: {rule.direction}")
        rules[key] = rule
    return rules


def optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        out = float(value)
    except Exception:
        return None
    return out if math.isfinite(out) else None


def optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except Exception:
        return None


def context_rule_config_row(rule: ContextRule) -> dict[str, Any]:
    return {
        "side": rule.side,
        "candidate_name": rule.candidate_name,
        "feature": rule.feature,
        "direction": rule.direction,
        "threshold": float(rule.threshold),
        "train_score": float(rule.train_score),
        "train_precision": rule.train_precision,
        "train_lift": rule.train_lift,
        "train_signals": rule.train_signals,
    }


def apply_batch_state_gate_overrides(candidates: list[CandidateSpec], gate: BatchStateGateConfig) -> list[CandidateSpec]:
    if str(gate.mode) == BATCH_STATE_GATE_OFF:
        return candidates
    return [
        replace(candidate, config=replace(candidate.config, batch_state_gate=gate))
        for candidate in candidates
    ]


def candidate_set_default_v1(
    *,
    fp_cost: float,
    fn_cost: float,
    high_target_positive_rate_threshold: float,
    high_false_positive_rate_threshold: float,
) -> list[CandidateSpec]:
    up_none = RankTrialConfig(
        train_batches=40,
        val_batches=5,
        elasticnet=ElasticNetRelevanceConfig(alpha=0.03, l1_ratio=0.5, max_features=40, min_features=5, prefilter_features=80),
        sequence=RocketConfig(mode=SEQUENCE_NONE),
        model=RankModelConfig(rank_loss="YetiRank", iterations=100, depth=3, learning_rate=0.01, l2_leaf_reg=30.0, random_strength=1.0),
        decision=DecisionConfig(0.975, 3, fp_cost, fn_cost, high_target_positive_rate_threshold, high_false_positive_rate_threshold),
    )
    up_rocket_base = RankTrialConfig(
        train_batches=40,
        val_batches=5,
        elasticnet=ElasticNetRelevanceConfig(alpha=0.01, l1_ratio=0.5, max_features=20, min_features=5, prefilter_features=160),
        sequence=RocketConfig(mode=SEQUENCE_CAUSAL_ROCKET_V1, sequence_length=16, n_kernels=32),
        model=RankModelConfig(rank_loss="YetiRank", iterations=50, depth=2, learning_rate=0.01, l2_leaf_reg=100.0, random_strength=1.0),
        decision=DecisionConfig(0.95, 2, fp_cost, fn_cost, high_target_positive_rate_threshold, high_false_positive_rate_threshold),
    )
    down_none = RankTrialConfig(
        train_batches=80,
        val_batches=10,
        elasticnet=ElasticNetRelevanceConfig(alpha=0.01, l1_ratio=0.5, max_features=40, min_features=5, prefilter_features=80),
        sequence=RocketConfig(mode=SEQUENCE_NONE),
        model=RankModelConfig(rank_loss="YetiRank", iterations=50, depth=3, learning_rate=0.03, l2_leaf_reg=100.0, random_strength=1.0),
        decision=DecisionConfig(0.95, 3, fp_cost, fn_cost, high_target_positive_rate_threshold, high_false_positive_rate_threshold),
    )
    out = [CandidateSpec("up_none_v1", SIDE_UP, up_none)]
    for kernels in (16, 32, 64):
        cfg = replace_sequence_kernels(up_rocket_base, kernels)
        out.append(CandidateSpec(f"up_rocket_{kernels}_v1", SIDE_UP, cfg))
    out.append(CandidateSpec("down_none_v1", SIDE_DOWN, down_none))
    for kernels in (16, 32, 64):
        cfg = RankTrialConfig(
            train_batches=80,
            val_batches=10,
            elasticnet=down_none.elasticnet,
            sequence=RocketConfig(mode=SEQUENCE_CAUSAL_ROCKET_V1, sequence_length=16, n_kernels=kernels),
            model=down_none.model,
            decision=down_none.decision,
        )
        out.append(CandidateSpec(f"down_rocket_{kernels}_diag_v1", SIDE_DOWN, cfg, diagnostic=True))
    return out


def candidate_set_pruned_reliability_v1(
    *,
    fp_cost: float,
    fn_cost: float,
    high_target_positive_rate_threshold: float,
    high_false_positive_rate_threshold: float,
    include_diagnostic_candidates: bool = False,
) -> list[CandidateSpec]:
    default = candidate_set_default_v1(
        fp_cost=fp_cost,
        fn_cost=fn_cost,
        high_target_positive_rate_threshold=high_target_positive_rate_threshold,
        high_false_positive_rate_threshold=high_false_positive_rate_threshold,
    )
    keep = {
        "up_none_v1",
        "up_rocket_64_v1",
        "down_none_v1",
        "down_rocket_16_diag_v1",
    }
    if include_diagnostic_candidates:
        keep.add("down_rocket_64_diag_v1")
    return [candidate for candidate in default if candidate.name in keep]


def replace_sequence_kernels(config: RankTrialConfig, kernels: int) -> RankTrialConfig:
    return RankTrialConfig(
        train_batches=config.train_batches,
        val_batches=config.val_batches,
        elasticnet=config.elasticnet,
        sequence=RocketConfig(
            mode=config.sequence.mode,
            sequence_length=config.sequence.sequence_length,
            n_kernels=int(kernels),
            seed=config.sequence.seed,
            cnn_embedding_dim=config.sequence.cnn_embedding_dim,
            cnn_conv_channels=config.sequence.cnn_conv_channels,
            cnn_kernel_size=config.sequence.cnn_kernel_size,
            cnn_epochs=config.sequence.cnn_epochs,
            cnn_batch_size=config.sequence.cnn_batch_size,
            cnn_max_train_rows=config.sequence.cnn_max_train_rows,
            cnn_device=config.sequence.cnn_device,
        ),
        model=config.model,
        decision=config.decision,
    )


def validate_candidate_inputs(candidates: list[CandidateSpec], side_sequence_features: dict[str, tuple[str, ...]]) -> None:
    for candidate in candidates:
        if candidate.config.sequence.mode != SEQUENCE_NONE and not side_sequence_features[candidate.side]:
            raise ValueError(f"{candidate.name} requires --{candidate.side}-sequence-panel-path")


def windows_by_pred_batch(batch_index: pl.DataFrame, *, train_batches: int, val_batches: int) -> dict[int, RPFWindow]:
    windows = build_windows(
        batch_index,
        lookback_batches=int(train_batches),
        val_batches=int(val_batches),
        embargo_batches=0,
        n_steps=0,
    )
    return {int(window.pred_batch_id): window for window in windows}


def evaluate_candidate(
    *,
    candidate: CandidateSpec,
    context: Any,
    window: RPFWindow,
    feature_columns: tuple[str, ...],
    sequence_feature_columns: tuple[str, ...],
    task_type: str,
    thread_count: int,
    gates: RouterGateConfig,
) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        fold = run_rank_fold(
            context=context,
            window=window,
            side=candidate.side,
            feature_columns=feature_columns,
            sequence_feature_columns=sequence_feature_columns,
            config=candidate.config,
            task_type=task_type,
            thread_count=thread_count,
            started=started,
        )
        validation_metrics = validation_metrics_with_batch_consistency(
            fold["validation_metrics"],
            fold.get("validation_window_metrics") or [],
            gates,
        )
        passed, reasons = validation_gate_result(validation_metrics, gates)
        return {
            "status": "ok",
            "candidate": candidate,
            "window": window,
            "fold": fold,
            "validation_metrics": validation_metrics,
            "passed": passed,
            "fail_reasons": reasons,
            "sequence_feature_count": int(fold["sequence_diagnostics"].get("sequence_feature_count") or 0),
            "elapsed_s": time.perf_counter() - started,
        }
    except Exception as exc:
        return {
            "status": "error",
            "candidate": candidate,
            "window": window,
            "fold": failed_payload(exc),
            "validation_metrics": {},
            "passed": False,
            "fail_reasons": [type(exc).__name__],
            "sequence_feature_count": int(candidate.config.sequence.n_kernels) * 3 if candidate.config.sequence.mode != SEQUENCE_NONE else 0,
            "elapsed_s": time.perf_counter() - started,
            "error_type": type(exc).__name__,
            "error_message": str(exc),
            "error_traceback": traceback.format_exc(),
        }


def failed_candidate_result(candidate: CandidateSpec, outer_window: RPFWindow, reason: str) -> dict[str, Any]:
    return {
        "status": "error",
        "candidate": candidate,
        "window": outer_window,
        "fold": {},
        "validation_metrics": {},
        "passed": False,
        "fail_reasons": [reason],
        "sequence_feature_count": int(candidate.config.sequence.n_kernels) * 3 if candidate.config.sequence.mode != SEQUENCE_NONE else 0,
        "elapsed_s": 0.0,
        "error_type": reason,
        "error_message": reason,
    }


def validation_gate_result(metrics: dict[str, Any], gates: RouterGateConfig) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if finite(metrics.get("predicted_positive_count"), 0.0) < float(gates.min_validation_signal_count):
        reasons.append("low_validation_signal_count")
    if finite(metrics.get("precision_lift"), 0.0) < float(gates.min_validation_precision_lift):
        reasons.append("low_validation_precision_lift")
    if finite(metrics.get("false_discovery_rate"), 1.0) > float(gates.max_validation_false_discovery_rate):
        reasons.append("high_validation_false_discovery_rate")
    if finite(metrics.get("active_window_rate"), 0.0) < float(gates.min_validation_active_window_rate):
        reasons.append("low_validation_active_window_rate")
    if finite(metrics.get("zero_signal_window_rate"), 1.0) > float(gates.max_validation_zero_signal_window_rate):
        reasons.append("high_validation_zero_signal_window_rate")
    if finite(metrics.get("active_batch_count"), 0.0) < float(gates.min_validation_active_batch_count):
        reasons.append("low_validation_active_batch_count")
    if finite(metrics.get("lift_positive_batch_rate"), 0.0) < float(gates.min_validation_lift_positive_batch_rate):
        reasons.append("low_validation_lift_positive_batch_rate")
    if finite(metrics.get("median_active_precision_lift"), 0.0) < float(gates.min_validation_median_active_precision_lift):
        reasons.append("low_validation_median_active_precision_lift")
    if finite(metrics.get("median_active_false_discovery_rate"), 1.0) > float(gates.max_validation_median_active_false_discovery_rate):
        reasons.append("high_validation_median_active_false_discovery_rate")
    return not reasons, reasons


def validation_metrics_with_batch_consistency(
    metrics: dict[str, Any],
    validation_window_metrics: list[dict[str, Any]],
    gates: RouterGateConfig,
) -> dict[str, Any]:
    active = [row for row in validation_window_metrics if bool(row.get("active_window"))]
    active_lifts = [finite(row.get("precision_lift"), 0.0) for row in active]
    active_fdrs = [finite(row.get("false_discovery_rate"), 1.0) for row in active]
    lift_positive_count = sum(
        1 for value in active_lifts if value >= float(gates.min_validation_precision_lift)
    )
    active_count = len(active)
    out = dict(metrics)
    out.update(
        {
            "validation_batch_count": int(len(validation_window_metrics)),
            "active_batch_count": int(active_count),
            "lift_positive_batch_count": int(lift_positive_count),
            "lift_positive_batch_rate": float(lift_positive_count / active_count) if active_count else 0.0,
            "median_active_precision_lift": float(np.median(active_lifts)) if active_lifts else 0.0,
            "median_active_false_discovery_rate": float(np.median(active_fdrs)) if active_fdrs else 1.0,
        }
    )
    return out


def select_candidate(results: list[dict[str, Any]]) -> dict[str, Any]:
    passing = [result for result in results if bool(result.get("passed"))]
    if passing:
        return max(passing, key=candidate_sort_key)
    fallback = max(results, key=candidate_sort_key) if results else {}
    if fallback:
        fallback = {**fallback, "selected_no_pass": True}
    return fallback


def select_router_candidate(
    results: list[dict[str, Any]],
    *,
    reliability_by_candidate: dict[str, dict[str, Any]],
    selection_mode: str,
    reliability_config: ReliabilityConfig,
    specialist_entry_mode: str = SPECIALIST_ENTRY_OFF,
    context_rules: dict[tuple[str, str], ContextRule] | None = None,
) -> dict[str, Any]:
    if selection_mode == SELECTION_VALIDATION_ONLY:
        selected = select_candidate(results)
        return {
            **selected,
            "final_selection_passed": bool(selected.get("passed")),
            "selection_mode": selection_mode,
            "specialist_entry_mode": specialist_entry_mode,
            "specialist_entry_passed": False,
            "specialist_entry_reason": None,
            "reliability": reliability_by_candidate.get(candidate_name(selected), empty_reliability_state()),
            "selection_rejected_reason": None if selected.get("passed") else "validation_failed",
        }
    if selection_mode == SELECTION_CONTEXT_RULE_V1:
        return select_context_rule_candidate(
            results,
            reliability_by_candidate=reliability_by_candidate,
            context_rules=context_rules or {},
            specialist_entry_mode=specialist_entry_mode,
        )
    if selection_mode != SELECTION_PREQUENTIAL_RELIABILITY_V1:
        raise ValueError(f"Unsupported router selection mode: {selection_mode}")

    eligible = [
        result
        for result in results
        if bool(result.get("passed"))
        and bool(reliability_by_candidate.get(candidate_name(result), {}).get("reliability_passed"))
    ]
    specialist_eligible = [
        result
        for result in results
        if specialist_entry_passed(result, specialist_entry_mode)
    ]
    eligible_by_name = {candidate_name(result): result for result in [*eligible, *specialist_eligible]}
    eligible = list(eligible_by_name.values())
    if eligible:
        selected = max(
            eligible,
            key=lambda result: reliability_candidate_sort_key(result, reliability_by_candidate[candidate_name(result)]),
        )
        specialist_passed = specialist_entry_passed(selected, specialist_entry_mode)
        return {
            **selected,
            "final_selection_passed": True,
            "selection_mode": selection_mode,
            "specialist_entry_mode": specialist_entry_mode,
            "specialist_entry_passed": specialist_passed,
            "specialist_entry_reason": (
                SPECIALIST_ENTRY_DOWN_NONE_VALIDATION_QUIET_V1
                if specialist_passed and not bool(selected.get("passed"))
                else None
            ),
            "reliability": reliability_by_candidate[candidate_name(selected)],
            "selection_rejected_reason": None,
        }

    fallback = max(results, key=lambda result: reliability_fallback_sort_key(result, reliability_by_candidate.get(candidate_name(result), {}))) if results else {}
    if not fallback:
        return {}
    state = reliability_by_candidate.get(candidate_name(fallback), empty_reliability_state())
    rejected_reason = prequential_rejection_reason(fallback, state, reliability_config)
    return {
        **fallback,
        "passed": False,
        "final_selection_passed": False,
        "selected_no_pass": True,
        "selection_mode": selection_mode,
        "specialist_entry_mode": specialist_entry_mode,
        "specialist_entry_passed": False,
        "specialist_entry_reason": None,
        "reliability": state,
        "selection_rejected_reason": rejected_reason,
    }


def select_context_rule_candidate(
    results: list[dict[str, Any]],
    *,
    reliability_by_candidate: dict[str, dict[str, Any]],
    context_rules: dict[tuple[str, str], ContextRule],
    specialist_entry_mode: str,
) -> dict[str, Any]:
    evaluated = [
        {
            **result,
            "context_rule": context_rule_evaluation(
                result,
                reliability_by_candidate.get(candidate_name(result), empty_reliability_state()),
                context_rules,
            ),
        }
        for result in results
    ]
    eligible = [
        result
        for result in evaluated
        if result.get("status") == "ok" and bool((result.get("context_rule") or {}).get("passed"))
    ]
    if eligible:
        selected = max(eligible, key=context_rule_candidate_sort_key)
        rule_eval = selected.get("context_rule") or {}
        return {
            **selected,
            "final_selection_passed": True,
            "selection_mode": SELECTION_CONTEXT_RULE_V1,
            "specialist_entry_mode": specialist_entry_mode,
            "specialist_entry_passed": False,
            "specialist_entry_reason": None,
            "reliability": reliability_by_candidate.get(candidate_name(selected), empty_reliability_state()),
            "selection_rejected_reason": None,
            "context_rule_passed": True,
            "context_rule_feature": rule_eval.get("feature"),
            "context_rule_direction": rule_eval.get("direction"),
            "context_rule_threshold": rule_eval.get("threshold"),
            "context_rule_value": rule_eval.get("value"),
            "context_rule_margin": rule_eval.get("margin"),
            "context_rule_train_score": rule_eval.get("train_score"),
        }
    fallback = max(evaluated, key=context_rule_fallback_sort_key) if evaluated else {}
    if not fallback:
        return {}
    rule_eval = fallback.get("context_rule") or {}
    return {
        **fallback,
        "passed": False,
        "final_selection_passed": False,
        "selected_no_pass": True,
        "selection_mode": SELECTION_CONTEXT_RULE_V1,
        "specialist_entry_mode": specialist_entry_mode,
        "specialist_entry_passed": False,
        "specialist_entry_reason": None,
        "reliability": reliability_by_candidate.get(candidate_name(fallback), empty_reliability_state()),
        "selection_rejected_reason": str(rule_eval.get("rejected_reason") or "context_rule_failed"),
        "context_rule_passed": False,
        "context_rule_feature": rule_eval.get("feature"),
        "context_rule_direction": rule_eval.get("direction"),
        "context_rule_threshold": rule_eval.get("threshold"),
        "context_rule_value": rule_eval.get("value"),
        "context_rule_margin": rule_eval.get("margin"),
        "context_rule_train_score": rule_eval.get("train_score"),
    }


def specialist_entry_passed(result: dict[str, Any], specialist_entry_mode: str) -> bool:
    if specialist_entry_mode == SPECIALIST_ENTRY_OFF:
        return False
    if specialist_entry_mode != SPECIALIST_ENTRY_DOWN_NONE_VALIDATION_QUIET_V1:
        raise ValueError(f"Unsupported specialist entry mode: {specialist_entry_mode}")
    candidate: CandidateSpec | None = result.get("candidate")
    if candidate is None or candidate.side != SIDE_DOWN or candidate.name != "down_none_v1":
        return False
    if result.get("status") != "ok":
        return False
    metrics = result.get("validation_metrics") or {}
    if int(finite(metrics.get("predicted_positive_count"), 0.0)) != 0:
        return False
    fold = result.get("fold") or {}
    prediction_window_metric = fold.get("prediction_window_metric") or {}
    if prediction_window_metric.get("batch_state_gate_mode") == BATCH_STATE_GATE_OFF:
        return False
    return bool(prediction_window_metric.get("batch_state_gate_passed"))


def candidate_name(result: dict[str, Any]) -> str:
    candidate: CandidateSpec | None = result.get("candidate")
    return candidate.name if candidate else ""


def context_rule_evaluation(
    result: dict[str, Any],
    reliability: dict[str, Any],
    context_rules: dict[tuple[str, str], ContextRule],
) -> dict[str, Any]:
    candidate: CandidateSpec | None = result.get("candidate")
    if candidate is None:
        return {"passed": False, "rejected_reason": "missing_candidate"}
    rule = context_rules.get((candidate.side, candidate.name))
    if rule is None:
        return {"passed": False, "rejected_reason": "missing_context_rule"}
    context = context_rule_feature_context(result, reliability)
    if rule.feature not in context:
        return {
            "passed": False,
            "rejected_reason": "missing_context_rule_feature",
            **context_rule_payload(rule, value=None, margin=None),
        }
    value = optional_float(context.get(rule.feature))
    if value is None:
        return {
            "passed": False,
            "rejected_reason": "nonfinite_context_rule_feature",
            **context_rule_payload(rule, value=None, margin=None),
        }
    margin = context_rule_margin(value, rule)
    return {
        "passed": margin >= 0.0,
        "rejected_reason": None if margin >= 0.0 else "context_rule_failed",
        **context_rule_payload(rule, value=value, margin=margin),
    }


def context_rule_payload(rule: ContextRule, *, value: float | None, margin: float | None) -> dict[str, Any]:
    return {
        "feature": rule.feature,
        "direction": rule.direction,
        "threshold": float(rule.threshold),
        "value": value,
        "margin": margin,
        "train_score": float(rule.train_score),
        "train_precision": rule.train_precision,
        "train_lift": rule.train_lift,
        "train_signals": rule.train_signals,
    }


def context_rule_margin(value: float, rule: ContextRule) -> float:
    if rule.direction == "higher_good":
        return float(value) - float(rule.threshold)
    if rule.direction == "lower_good":
        return float(rule.threshold) - float(value)
    raise ValueError(f"Unsupported context rule direction: {rule.direction}")


def context_rule_feature_context(result: dict[str, Any], reliability: dict[str, Any]) -> dict[str, Any]:
    candidate: CandidateSpec = result["candidate"]
    fold = result.get("fold") or {}
    prediction = fold.get("prediction_window_metric") or {}
    validation = result.get("validation_metrics") or {}
    out: dict[str, Any] = {
        "side": candidate.side,
        "candidate_name": candidate.name,
        "diagnostic": bool(candidate.diagnostic),
        "status": result.get("status"),
        "candidate_passed_validation": bool(result.get("passed")),
        "candidate_fail_reasons": ",".join(result.get("fail_reasons") or []),
        "selected_feature_count": prediction.get("selected_feature_count"),
        "threshold": prediction.get("threshold"),
        "threshold_quantile": prediction.get("threshold_quantile"),
        "max_signals_per_batch": prediction.get("max_signals_per_batch"),
        "score_mean": prediction.get("score_mean"),
        "score_std": prediction.get("score_std"),
        "validation_threshold_score": prediction.get("validation_threshold_score"),
        "batch_state_gate_mode": prediction.get("batch_state_gate_mode"),
        "batch_state_gate_status": prediction.get("batch_state_gate_status"),
        "batch_state_gate_probability": prediction.get("batch_state_gate_probability"),
        "batch_state_gate_passed": prediction.get("batch_state_gate_passed"),
        "validation_status": result.get("status"),
        "validation_passed": bool(result.get("passed")),
        "validation_fail_reasons": ",".join(result.get("fail_reasons") or []),
        "validation_ranked_signal_quality": validation.get("ranked_signal_quality"),
        "validation_precision": validation.get("precision"),
        "validation_precision_lift": validation.get("precision_lift"),
        "validation_false_discovery_rate": validation.get("false_discovery_rate"),
        "validation_predicted_positive_count": validation.get("predicted_positive_count"),
        "validation_active_window_rate": validation.get("active_window_rate"),
        "validation_zero_signal_window_rate": validation.get("zero_signal_window_rate"),
        "validation_batch_count": validation.get("validation_batch_count"),
        "validation_active_batch_count": validation.get("active_batch_count"),
        "validation_lift_positive_batch_count": validation.get("lift_positive_batch_count"),
        "validation_lift_positive_batch_rate": validation.get("lift_positive_batch_rate"),
        "validation_median_active_precision_lift": validation.get("median_active_precision_lift"),
        "validation_median_active_false_discovery_rate": validation.get("median_active_false_discovery_rate"),
        "validation_high_target_window_capture_rate": validation.get("high_target_window_capture_rate"),
        "validation_missed_high_target_window_rate": validation.get("missed_high_target_window_rate"),
        "sequence_feature_count": result.get("sequence_feature_count"),
        "current_validation_positive_rate": validation.get("base_positive_rate"),
        "current_validation_signal_rate": validation.get("predicted_positive_rate"),
        "recent_candidate_precision_lift": reliability.get("precision_lift"),
        "recent_candidate_precision_lift_lcb": reliability.get("precision_lift_lcb"),
        "recent_candidate_window_selection_lift": reliability.get("window_selection_lift"),
        "recent_candidate_selected_window_row_lift": reliability.get("selected_window_row_lift"),
        "recent_candidate_selected_window_row_lift_lcb": reliability.get("selected_window_row_lift_lcb"),
        "recent_candidate_false_discovery_rate": reliability.get("false_discovery_rate"),
    }
    out.update(
        {
            f"reliability_{key}": value
            for key, value in reliability.items()
            if key not in {"side", "candidate_name", "diagnostic"}
        }
    )
    return out


def context_rule_candidate_sort_key(result: dict[str, Any]) -> tuple[float, float, float, float, float, float, str]:
    rule_eval = result.get("context_rule") or {}
    metrics = result.get("validation_metrics") or {}
    return (
        finite(rule_eval.get("margin"), -1e9),
        finite(rule_eval.get("train_score"), -1e9),
        finite(metrics.get("ranked_signal_quality"), -1e9),
        finite(metrics.get("precision_lift"), 0.0),
        -finite(metrics.get("false_discovery_rate"), 1.0),
        -float(result.get("sequence_feature_count") or 0),
        str(candidate_name(result)),
    )


def context_rule_fallback_sort_key(result: dict[str, Any]) -> tuple[float, float, float, float, str]:
    rule_eval = result.get("context_rule") or {}
    metrics = result.get("validation_metrics") or {}
    return (
        finite(rule_eval.get("margin"), -1e9),
        finite(rule_eval.get("train_score"), -1e9),
        finite(metrics.get("ranked_signal_quality"), -1e9),
        -float(result.get("sequence_feature_count") or 0),
        str(candidate_name(result)),
    )


def candidate_sort_key(result: dict[str, Any]) -> tuple[float, float, float, float]:
    metrics = result.get("validation_metrics", {})
    return (
        finite(metrics.get("ranked_signal_quality"), -1e9),
        finite(metrics.get("precision_lift"), 0.0),
        -finite(metrics.get("false_discovery_rate"), 1.0),
        -float(result.get("sequence_feature_count") or 0),
    )


def reliability_candidate_sort_key(result: dict[str, Any], reliability: dict[str, Any]) -> tuple[float, float, float, float, float, float, str]:
    metrics = result.get("validation_metrics", {})
    return (
        finite(reliability.get("reliability_score"), -1e9),
        finite(reliability.get("selected_window_row_lift_lcb"), 0.0),
        finite(reliability.get("window_selection_lift"), 0.0),
        finite(metrics.get("ranked_signal_quality"), -1e9),
        finite(metrics.get("precision_lift"), 0.0),
        -float(result.get("sequence_feature_count") or 0),
        str(candidate_name(result)),
    )


def reliability_fallback_sort_key(result: dict[str, Any], reliability: dict[str, Any]) -> tuple[float, float, float, float, float, float, str]:
    metrics = result.get("validation_metrics", {})
    return (
        finite(reliability.get("reliability_score"), -1e9),
        finite(reliability.get("selected_window_row_lift_lcb"), 0.0),
        finite(reliability.get("window_selection_lift"), 0.0),
        finite(reliability.get("precision_lift_lcb"), 0.0),
        finite(metrics.get("ranked_signal_quality"), -1e9),
        -float(result.get("sequence_feature_count") or 0),
        str(candidate_name(result)),
    )


def prequential_rejection_reason(result: dict[str, Any], reliability: dict[str, Any], config: ReliabilityConfig) -> str:
    if not bool(result.get("passed")):
        return "validation_failed"
    reasons = str(reliability.get("reliability_fail_reasons") or "")
    if reasons:
        return reasons
    if str(config.warmup_policy) == WARMUP_NO_SIGNAL and not bool(reliability.get("reliability_passed")):
        return "reliability_warmup_or_failed"
    return "reliability_failed"


def empty_reliability_state() -> dict[str, Any]:
    return {
        "reliability_status": "empty",
        "reliability_passed": False,
        "reliability_fail_reasons": "no_reliability_state",
        "reliability_score": None,
        "history_windows": 0,
        "signal_count": 0,
        "active_windows": 0,
        "precision": None,
        "base_rate": None,
        "precision_lift": None,
        "precision_lift_lcb": None,
        "precision_lcb": None,
        "false_discovery_rate": None,
        "active_window_rate": 0.0,
        "zero_signal_window_rate": 1.0,
        "high_false_positive_window_rate": 0.0,
        "active_window_count": 0,
        "active_window_positive_count": 0,
        "active_window_rows": 0,
        "active_window_base_rate": None,
        "window_selection_lift": None,
        "selected_window_precision": None,
        "selected_window_precision_lcb": None,
        "selected_window_row_lift": None,
        "selected_window_row_lift_lcb": None,
        "selected_window_false_discovery_rate": None,
    }


def reliability_state_for_candidate(
    *,
    candidate: CandidateSpec,
    history_rows: list[dict[str, Any]],
    config: ReliabilityConfig,
) -> dict[str, Any]:
    rows = [
        row
        for row in history_rows
        if row.get("side") == candidate.side and row.get("candidate_name") == candidate.name and row.get("status") == "ok"
    ]
    rows = rows[-max(0, int(config.lookback_windows)) :]
    windows = len(rows)
    active_windows = sum(1 for row in rows if bool(row.get("active_window")))
    signal_count = int(sum(int(row.get("predicted_positive_count") or 0) for row in rows))
    tp = int(sum(int(row.get("true_positive_count") or 0) for row in rows))
    fp = int(sum(int(row.get("false_positive_count") or 0) for row in rows))
    positives = int(sum(int(row.get("positive_count") or 0) for row in rows))
    total_rows = int(sum(int(row.get("rows") or 0) for row in rows))
    active_rows = [row for row in rows if bool(row.get("active_window"))]
    active_positive_count = int(sum(int(row.get("positive_count") or 0) for row in active_rows))
    active_total_rows = int(sum(int(row.get("rows") or 0) for row in active_rows))
    precision = safe_ratio(tp, signal_count)
    base_rate = safe_ratio(positives, total_rows)
    precision_lift = safe_ratio(precision, base_rate) if precision is not None and base_rate and base_rate > 0 else None
    precision_lcb = wilson_lower_bound(tp, signal_count, z=float(config.lcb_z))
    precision_lift_lcb = safe_ratio(precision_lcb, base_rate) if base_rate and base_rate > 0 else None
    active_window_base_rate = safe_ratio(active_positive_count, active_total_rows)
    window_selection_lift = (
        safe_ratio(active_window_base_rate, base_rate)
        if active_window_base_rate is not None and base_rate and base_rate > 0
        else None
    )
    selected_window_row_lift = (
        safe_ratio(precision, active_window_base_rate)
        if precision is not None and active_window_base_rate and active_window_base_rate > 0
        else None
    )
    selected_window_row_lift_lcb = (
        safe_ratio(precision_lcb, active_window_base_rate)
        if precision_lcb is not None and active_window_base_rate and active_window_base_rate > 0
        else None
    )
    fdr = safe_ratio(fp, signal_count)
    active_rate = safe_ratio(active_windows, windows) or 0.0
    zero_rate = 1.0 - active_rate
    high_fp_rate = safe_ratio(sum(1 for row in rows if bool(row.get("high_false_positive_window"))), windows) or 0.0
    score = reliability_score(
        precision_lift_lcb=precision_lift_lcb,
        selected_window_row_lift_lcb=selected_window_row_lift_lcb,
        window_selection_lift=window_selection_lift,
        active_window_rate=active_rate,
        false_discovery_rate=fdr,
        zero_signal_window_rate=zero_rate,
        high_false_positive_window_rate=high_fp_rate,
    )
    min_precision_lift_lcb = side_override(
        candidate.side,
        up_value=config.up_min_precision_lift_lcb,
        down_value=config.down_min_precision_lift_lcb,
        default_value=config.min_precision_lift_lcb,
    )
    min_selected_window_row_lift_lcb = side_override(
        candidate.side,
        up_value=config.up_min_selected_window_row_lift_lcb,
        down_value=config.down_min_selected_window_row_lift_lcb,
        default_value=config.min_selected_window_row_lift_lcb,
    )
    reasons: list[str] = []
    if windows < int(config.min_history_windows):
        reasons.append("insufficient_reliability_history")
    if signal_count < int(config.min_signals):
        reasons.append("low_reliability_signal_count")
    if active_windows < int(config.min_active_windows):
        reasons.append("low_reliability_active_windows")
    if finite(precision_lift_lcb, 0.0) < float(min_precision_lift_lcb):
        reasons.append("low_reliability_precision_lift_lcb")
    if finite(window_selection_lift, 0.0) < float(config.min_window_selection_lift):
        reasons.append("low_reliability_window_selection_lift")
    if finite(selected_window_row_lift_lcb, 0.0) < float(min_selected_window_row_lift_lcb):
        reasons.append("low_reliability_selected_window_row_lift_lcb")
    if finite(fdr, 1.0) > float(config.max_false_discovery_rate):
        reasons.append("high_reliability_false_discovery_rate")
    return {
        "candidate_name": candidate.name,
        "side": candidate.side,
        "diagnostic": bool(candidate.diagnostic),
        "reliability_status": "pass" if not reasons else "fail",
        "reliability_passed": not reasons,
        "reliability_fail_reasons": ",".join(reasons),
        "reliability_score": score,
        "history_windows": int(windows),
        "signal_count": int(signal_count),
        "active_windows": int(active_windows),
        "true_positive_count": int(tp),
        "false_positive_count": int(fp),
        "positive_count": int(positives),
        "rows": int(total_rows),
        "precision": precision,
        "base_rate": base_rate,
        "precision_lift": precision_lift,
        "precision_lift_lcb": precision_lift_lcb,
        "precision_lcb": precision_lcb,
        "false_discovery_rate": fdr,
        "active_window_rate": active_rate,
        "zero_signal_window_rate": zero_rate,
        "high_false_positive_window_rate": high_fp_rate,
        "active_window_count": int(active_windows),
        "active_window_positive_count": int(active_positive_count),
        "active_window_rows": int(active_total_rows),
        "active_window_base_rate": active_window_base_rate,
        "window_selection_lift": window_selection_lift,
        "selected_window_precision": precision,
        "selected_window_precision_lcb": precision_lcb,
        "selected_window_row_lift": selected_window_row_lift,
        "selected_window_row_lift_lcb": selected_window_row_lift_lcb,
        "selected_window_false_discovery_rate": fdr,
    }


def side_override(side: str, *, up_value: float | None, down_value: float | None, default_value: float) -> float:
    if side == SIDE_UP and up_value is not None:
        return float(up_value)
    if side == SIDE_DOWN and down_value is not None:
        return float(down_value)
    return float(default_value)


def wilson_lower_bound(successes: int, trials: int, *, z: float) -> float | None:
    n = int(trials)
    if n <= 0:
        return None
    p = float(successes) / float(n)
    z2 = float(z) * float(z)
    denominator = 1.0 + z2 / n
    centre = p + z2 / (2.0 * n)
    margin = float(z) * math.sqrt((p * (1.0 - p) + z2 / (4.0 * n)) / n)
    return max(0.0, float((centre - margin) / denominator))


def reliability_score(
    *,
    precision_lift_lcb: float | None,
    selected_window_row_lift_lcb: float | None = None,
    window_selection_lift: float | None = None,
    active_window_rate: float | None,
    false_discovery_rate: float | None,
    zero_signal_window_rate: float | None,
    high_false_positive_window_rate: float | None,
) -> float:
    lift_lcb = finite(precision_lift_lcb, 0.0)
    row_lift_lcb = finite(selected_window_row_lift_lcb, 0.0)
    selection_lift = finite(window_selection_lift, 0.0)
    active = finite(active_window_rate, 0.0)
    fdr = finite(false_discovery_rate, 1.0)
    zero = finite(zero_signal_window_rate, 1.0)
    high_fp = finite(high_false_positive_window_rate, 1.0)
    return float(
        2.0 * max(0.0, lift_lcb - 1.0)
        + 1.5 * max(0.0, row_lift_lcb - 1.0)
        + 0.5 * max(0.0, selection_lift - 1.0)
        + 0.5 * active
        - 1.5 * fdr
        - 0.5 * zero
        - 0.5 * high_fp
    )


def safe_ratio(numerator: float | int | None, denominator: float | int | None) -> float | None:
    if denominator is None or float(denominator) == 0.0:
        return None
    if numerator is None:
        return None
    return float(numerator) / float(denominator)


def routed_prediction_payload(selected: dict[str, Any], outer_window: RPFWindow, side: str) -> dict[str, Any]:
    candidate: CandidateSpec | None = selected.get("candidate")
    fold = selected.get("fold") or {}
    candidate_name = candidate.name if candidate else None
    passed = bool(selected.get("final_selection_passed", selected.get("passed")))
    validation_passed = bool(selected.get("passed"))
    fallback_name = candidate_name if selected.get("selected_no_pass") else None
    if fold and "prediction_scores" in fold:
        scores = [dict(row) for row in fold["prediction_scores"]]
        if not passed:
            for row in scores:
                row["decision"] = 0
        y = np.asarray([int(row["target_binary"]) for row in scores], dtype=int)
        decision = np.asarray([int(row["decision"]) for row in scores], dtype=int)
    else:
        scores = []
        y = np.asarray([], dtype=int)
        decision = np.asarray([], dtype=int)
    if y.size:
        metric = simple_window_metric_row(
            y,
            decision,
            fp_cost=float(candidate.config.decision.fp_cost if candidate else 5.0),
            fn_cost=float(candidate.config.decision.fn_cost if candidate else 1.0),
            high_target_positive_rate_threshold=float(candidate.config.decision.high_target_positive_rate_threshold if candidate else 0.2),
            high_false_positive_rate_threshold=float(candidate.config.decision.high_false_positive_rate_threshold if candidate else 0.3),
        )
    else:
        metric = binary_decision_metrics(y, decision, fp_cost=5.0, fn_cost=1.0)
        metric.update({"positive_rate": 0.0, "high_target_window": False, "active_window": False})
    metric.update(
        {
            "split": "prediction",
            "side": side,
            "step_idx": int(outer_window.step_idx),
            "pred_batch_id": int(outer_window.pred_batch_id),
            "selected_feature_count": fold.get("selected_feature_count"),
            "threshold": fold.get("threshold"),
            "max_signals_per_batch": fold.get("max_signals"),
            "selected_candidate": candidate_name if passed else None,
            "diagnostic_candidate": fallback_name,
            "candidate_passed_validation": validation_passed,
            "candidate_passed_selection": passed,
            "selection_mode": selected.get("selection_mode"),
            "validation_fail_reasons": ",".join(selected.get("fail_reasons") or []),
            "validation_ranked_signal_quality": (selected.get("validation_metrics") or {}).get("ranked_signal_quality"),
            "specialist_entry_mode": selected.get("specialist_entry_mode"),
            "specialist_entry_passed": bool(selected.get("specialist_entry_passed")),
            "specialist_entry_reason": selected.get("specialist_entry_reason"),
            **selected_context_rule_metric_fields(selected),
            **selected_reliability_metric_fields(selected),
        }
    )
    for row in scores:
        row.update(
            {
                "selected_candidate": candidate_name if passed else None,
                "diagnostic_candidate": fallback_name,
                "candidate_passed_validation": validation_passed,
                "candidate_passed_selection": passed,
                "router_decision_policy": "selected_candidate" if passed else "no_signal_no_candidate_passed",
                "selection_mode": selected.get("selection_mode"),
                "specialist_entry_mode": selected.get("specialist_entry_mode"),
                "specialist_entry_passed": bool(selected.get("specialist_entry_passed")),
                "specialist_entry_reason": selected.get("specialist_entry_reason"),
                **selected_context_rule_metric_fields(selected),
                "margin": float(row["rank_score"]) - float(row["threshold"]),
            }
        )
    return {"window_metric": metric, "scores": scores}


def candidate_validation_row(result: dict[str, Any]) -> dict[str, Any]:
    candidate: CandidateSpec = result["candidate"]
    window: RPFWindow = result["window"]
    metrics = result.get("validation_metrics", {})
    return {
        "side": candidate.side,
        "candidate_name": candidate.name,
        "diagnostic": bool(candidate.diagnostic),
        "status": result.get("status"),
        "passed_validation": bool(result.get("passed")),
        "fail_reasons": ",".join(result.get("fail_reasons") or []),
        "step_idx": int(window.step_idx),
        "pred_batch_id": int(window.pred_batch_id),
        "validation_ranked_signal_quality": metrics.get("ranked_signal_quality"),
        "validation_precision": metrics.get("precision"),
        "validation_precision_lift": metrics.get("precision_lift"),
        "validation_false_discovery_rate": metrics.get("false_discovery_rate"),
        "validation_predicted_positive_count": metrics.get("predicted_positive_count"),
        "validation_active_window_rate": metrics.get("active_window_rate"),
        "validation_zero_signal_window_rate": metrics.get("zero_signal_window_rate"),
        "validation_batch_count": metrics.get("validation_batch_count"),
        "validation_active_batch_count": metrics.get("active_batch_count"),
        "validation_lift_positive_batch_count": metrics.get("lift_positive_batch_count"),
        "validation_lift_positive_batch_rate": metrics.get("lift_positive_batch_rate"),
        "validation_median_active_precision_lift": metrics.get("median_active_precision_lift"),
        "validation_median_active_false_discovery_rate": metrics.get("median_active_false_discovery_rate"),
        "validation_high_target_window_capture_rate": metrics.get("high_target_window_capture_rate"),
        "validation_missed_high_target_window_rate": metrics.get("missed_high_target_window_rate"),
        "sequence_feature_count": result.get("sequence_feature_count"),
        "elapsed_s": result.get("elapsed_s"),
        "error_type": result.get("error_type"),
        "error_message": result.get("error_message"),
        "candidate_config_json": json.dumps(trial_config_payload(candidate.config), sort_keys=True),
    }


def candidate_validation_score_rows(result: dict[str, Any]) -> list[dict[str, Any]]:
    fold = result.get("fold") or {}
    return tagged_candidate_rows(result, fold.get("validation_scores") or [])


def candidate_validation_window_rows(result: dict[str, Any]) -> list[dict[str, Any]]:
    fold = result.get("fold") or {}
    return tagged_candidate_rows(result, fold.get("validation_window_metrics") or [])


def candidate_selected_feature_rows(result: dict[str, Any]) -> list[dict[str, Any]]:
    fold = result.get("fold") or {}
    return tagged_candidate_rows(result, fold.get("selected_features") or [])


def candidate_sequence_row(result: dict[str, Any]) -> dict[str, Any]:
    fold = result.get("fold") or {}
    rows = tagged_candidate_rows(result, [fold.get("sequence_diagnostics") or {}])
    return rows[0] if rows else {}


def candidate_prediction_window_row(result: dict[str, Any]) -> dict[str, Any]:
    candidate: CandidateSpec = result["candidate"]
    window: RPFWindow = result["window"]
    fold = result.get("fold") or {}
    metric = dict(fold.get("prediction_window_metric") or {})
    if not metric:
        metric = {
            "rows": 0,
            "positive_count": 0,
            "negative_count": 0,
            "predicted_positive_count": 0,
            "true_positive_count": 0,
            "false_positive_count": 0,
            "false_negative_count": 0,
            "true_negative_count": 0,
            "precision": None,
            "false_discovery_rate": None,
            "precision_lift": None,
            "positive_rate": None,
            "active_window": False,
            "high_false_positive_window": False,
        }
    return {
        "side": candidate.side,
        "candidate_name": candidate.name,
        "diagnostic": bool(candidate.diagnostic),
        "status": result.get("status"),
        "candidate_passed_validation": bool(result.get("passed")),
        "candidate_fail_reasons": ",".join(result.get("fail_reasons") or []),
        "router_step_idx": int(window.step_idx),
        "router_pred_batch_id": int(window.pred_batch_id),
        **metric,
    }


def candidate_prediction_score_rows(result: dict[str, Any]) -> list[dict[str, Any]]:
    fold = result.get("fold") or {}
    return tagged_candidate_rows(result, fold.get("prediction_scores") or [])


def candidate_selection_audit_rows(
    results: list[dict[str, Any]],
    *,
    selected: dict[str, Any],
    reliability_by_candidate: dict[str, dict[str, Any]],
    reliability_config: ReliabilityConfig,
    selection_mode: str,
    outer_window: RPFWindow,
    context_rules: dict[tuple[str, str], ContextRule] | None = None,
) -> list[dict[str, Any]]:
    selected_name = candidate_name(selected)
    rows: list[dict[str, Any]] = []
    for result in results:
        candidate: CandidateSpec = result["candidate"]
        metrics = result.get("validation_metrics") or {}
        reliability = reliability_by_candidate.get(candidate.name, empty_reliability_state())
        rule_eval = context_rule_evaluation(result, reliability, context_rules or {})
        final_selected = bool(selected.get("final_selection_passed", selected.get("passed"))) and candidate.name == selected_name
        validation_passed = bool(result.get("passed"))
        reliability_passed = bool(reliability.get("reliability_passed"))
        if final_selected:
            rejected_reason = None
        elif selection_mode == SELECTION_CONTEXT_RULE_V1:
            rejected_reason = (
                "validation_failed"
                if not validation_passed
                else str(rule_eval.get("rejected_reason") or "context_rule_failed")
            )
        elif selection_mode == SELECTION_PREQUENTIAL_RELIABILITY_V1:
            rejected_reason = prequential_rejection_reason(
                result, reliability, reliability_config
            )
        else:
            rejected_reason = None if validation_passed else "validation_failed"
        rows.append(
            {
                "side": candidate.side,
                "candidate_name": candidate.name,
                "diagnostic": bool(candidate.diagnostic),
                "selection_mode": selection_mode,
                "router_step_idx": int(outer_window.step_idx),
                "router_pred_batch_id": int(outer_window.pred_batch_id),
                "candidate_status": result.get("status"),
                "candidate_passed_validation": validation_passed,
                "candidate_passed_reliability": reliability_passed,
                "candidate_passed_selection": final_selected,
                "candidate_fail_reasons": ",".join(result.get("fail_reasons") or []),
                "selected_candidate_name": selected_name if final_selected else None,
                "selected_candidate": final_selected,
                "diagnostic_candidate": bool(selected.get("selected_no_pass")) and candidate.name == selected_name,
                "candidate_rejected_reason": rejected_reason,
                "selection_rejected_reason": rejected_reason,
                "specialist_entry_mode": selected.get("specialist_entry_mode"),
                "specialist_entry_candidate": bool(selected.get("specialist_entry_passed")) and candidate.name == selected_name,
                "specialist_entry_reason": selected.get("specialist_entry_reason") if candidate.name == selected_name else None,
                "context_rule_passed": bool(rule_eval.get("passed")),
                "context_rule_rejected_reason": rule_eval.get("rejected_reason"),
                "context_rule_feature": rule_eval.get("feature"),
                "context_rule_direction": rule_eval.get("direction"),
                "context_rule_threshold": rule_eval.get("threshold"),
                "context_rule_value": rule_eval.get("value"),
                "context_rule_margin": rule_eval.get("margin"),
                "context_rule_train_score": rule_eval.get("train_score"),
                "validation_ranked_signal_quality": metrics.get("ranked_signal_quality"),
                "validation_precision_lift": metrics.get("precision_lift"),
                "validation_false_discovery_rate": metrics.get("false_discovery_rate"),
                "sequence_feature_count": result.get("sequence_feature_count"),
                **{f"reliability_{key}": value for key, value in reliability.items() if key not in {"side", "candidate_name", "diagnostic"}},
            }
        )
    return rows


def batch_regime_diagnostic_row(
    *,
    side: str,
    outer_window: RPFWindow,
    selected: dict[str, Any],
    routed_window_metric: dict[str, Any],
    prior_window_rows: list[dict[str, Any]],
    reliability_by_candidate: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    side_prior = [row for row in prior_window_rows if row.get("side") == side]
    selected_state = reliability_by_candidate.get(candidate_name(selected), empty_reliability_state())
    validation = selected.get("validation_metrics") or {}
    return {
        "side": side,
        "step_idx": int(outer_window.step_idx),
        "pred_batch_id": int(outer_window.pred_batch_id),
        "selected_candidate": candidate_name(selected) if selected.get("final_selection_passed", selected.get("passed")) else None,
        "diagnostic_candidate": candidate_name(selected) if selected.get("selected_no_pass") else None,
        "past_20_batch_positive_rate_mean": rolling_mean(side_prior, "positive_rate", 20),
        "past_20_batch_positive_rate_std": rolling_std(side_prior, "positive_rate", 20),
        "past_60_batch_positive_rate_mean": rolling_mean(side_prior, "positive_rate", 60),
        "past_60_batch_positive_rate_std": rolling_std(side_prior, "positive_rate", 60),
        "recent_candidate_precision_lift": selected_state.get("precision_lift"),
        "recent_candidate_precision_lift_lcb": selected_state.get("precision_lift_lcb"),
        "recent_candidate_window_selection_lift": selected_state.get("window_selection_lift"),
        "recent_candidate_selected_window_row_lift": selected_state.get("selected_window_row_lift"),
        "recent_candidate_selected_window_row_lift_lcb": selected_state.get("selected_window_row_lift_lcb"),
        "recent_candidate_false_discovery_rate": selected_state.get("false_discovery_rate"),
        "current_validation_positive_rate": validation.get("base_positive_rate"),
        "current_validation_signal_rate": validation.get("predicted_positive_rate"),
        "prediction_batch_positive_rate": routed_window_metric.get("positive_rate"),
    }


def rolling_mean(rows: list[dict[str, Any]], key: str, count: int) -> float | None:
    values = [row.get(key) for row in rows[-max(0, int(count)) :]]
    values = [float(value) for value in values if value is not None and np.isfinite(float(value))]
    return float(np.mean(values)) if values else None


def rolling_std(rows: list[dict[str, Any]], key: str, count: int) -> float | None:
    values = [row.get(key) for row in rows[-max(0, int(count)) :]]
    values = [float(value) for value in values if value is not None and np.isfinite(float(value))]
    return float(np.std(values)) if values else None


def tagged_candidate_rows(result: dict[str, Any], rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidate: CandidateSpec = result["candidate"]
    window: RPFWindow = result["window"]
    passed = bool(result.get("passed"))
    out: list[dict[str, Any]] = []
    for row in rows:
        out.append(
            {
                "side": candidate.side,
                "candidate_name": candidate.name,
                "diagnostic": bool(candidate.diagnostic),
                "candidate_status": result.get("status"),
                "candidate_passed_validation": passed,
                "candidate_fail_reasons": ",".join(result.get("fail_reasons") or []),
                "router_step_idx": int(window.step_idx),
                "router_pred_batch_id": int(window.pred_batch_id),
                **dict(row),
            }
        )
    return out


def selected_candidate_row(selected: dict[str, Any], outer_window: RPFWindow, side: str) -> dict[str, Any]:
    candidate: CandidateSpec | None = selected.get("candidate")
    metrics = selected.get("validation_metrics") or {}
    final_passed = bool(selected.get("final_selection_passed", selected.get("passed")))
    validation_passed = bool(selected.get("passed"))
    return {
        "side": side,
        "step_idx": int(outer_window.step_idx),
        "pred_batch_id": int(outer_window.pred_batch_id),
        "selected_candidate": candidate.name if candidate and final_passed else None,
        "diagnostic_candidate": candidate.name if candidate and selected.get("selected_no_pass") else None,
        "candidate_passed_validation": validation_passed,
        "candidate_passed_selection": final_passed,
        "selection_mode": selected.get("selection_mode"),
        "selection_reason": (
            selected.get("specialist_entry_reason")
            if final_passed and selected.get("specialist_entry_reason")
            else ("passed_selection" if final_passed else "no_candidate_passed")
        ),
        "fail_reasons": ",".join(selected.get("fail_reasons") or []),
        "validation_ranked_signal_quality": metrics.get("ranked_signal_quality"),
        "validation_precision_lift": metrics.get("precision_lift"),
        "validation_false_discovery_rate": metrics.get("false_discovery_rate"),
        "specialist_entry_mode": selected.get("specialist_entry_mode"),
        "specialist_entry_passed": bool(selected.get("specialist_entry_passed")),
        "specialist_entry_reason": selected.get("specialist_entry_reason"),
        "candidate_rejected_reason": selected.get("selection_rejected_reason"),
        "selection_rejected_reason": selected.get("selection_rejected_reason"),
        **selected_context_rule_metric_fields(selected),
        **selected_reliability_metric_fields(selected),
    }


def selected_context_rule_metric_fields(selected: dict[str, Any]) -> dict[str, Any]:
    return {
        "context_rule_passed": selected.get("context_rule_passed"),
        "context_rule_feature": selected.get("context_rule_feature"),
        "context_rule_direction": selected.get("context_rule_direction"),
        "context_rule_threshold": selected.get("context_rule_threshold"),
        "context_rule_value": selected.get("context_rule_value"),
        "context_rule_margin": selected.get("context_rule_margin"),
        "context_rule_train_score": selected.get("context_rule_train_score"),
    }


def selected_reliability_metric_fields(selected: dict[str, Any]) -> dict[str, Any]:
    reliability = selected.get("reliability") or {}
    return {
        "reliability_status": reliability.get("reliability_status"),
        "reliability_score": reliability.get("reliability_score"),
        "reliability_history_windows": reliability.get("history_windows"),
        "reliability_signal_count": reliability.get("signal_count"),
        "reliability_precision": reliability.get("precision"),
        "reliability_base_rate": reliability.get("base_rate"),
        "reliability_precision_lift": reliability.get("precision_lift"),
        "reliability_precision_lift_lcb": reliability.get("precision_lift_lcb"),
        "reliability_precision_lcb": reliability.get("precision_lcb"),
        "reliability_false_discovery_rate": reliability.get("false_discovery_rate"),
        "reliability_active_window_rate": reliability.get("active_window_rate"),
        "reliability_zero_signal_window_rate": reliability.get("zero_signal_window_rate"),
        "reliability_active_window_base_rate": reliability.get("active_window_base_rate"),
        "reliability_window_selection_lift": reliability.get("window_selection_lift"),
        "reliability_selected_window_precision": reliability.get("selected_window_precision"),
        "reliability_selected_window_precision_lcb": reliability.get("selected_window_precision_lcb"),
        "reliability_selected_window_row_lift": reliability.get("selected_window_row_lift"),
        "reliability_selected_window_row_lift_lcb": reliability.get("selected_window_row_lift_lcb"),
        "reliability_selected_window_false_discovery_rate": reliability.get("selected_window_false_discovery_rate"),
    }


def summarize_router_outputs(
    score_rows: list[dict[str, Any]],
    window_rows: list[dict[str, Any]],
    *,
    block_size: int,
    fp_cost: float,
    fn_cost: float,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    block_rows: list[dict[str, Any]] = []
    side_summary: dict[str, Any] = {}
    for side in SIDES:
        side_scores = [row for row in score_rows if row.get("side") == side]
        side_windows = [row for row in window_rows if row.get("side") == side]
        side_summary[side] = aggregate_score_window_rows(side_scores, side_windows, fp_cost=fp_cost, fn_cost=fn_cost)
        pred_batches = sorted({int(row["pred_batch_id"]) for row in side_windows})
        for block_idx, start in enumerate(range(0, len(pred_batches), max(1, int(block_size)))):
            block_batches = set(pred_batches[start : start + max(1, int(block_size))])
            b_scores = [row for row in side_scores if int(row["pred_batch_id"]) in block_batches]
            b_windows = [row for row in side_windows if int(row["pred_batch_id"]) in block_batches]
            metrics = aggregate_score_window_rows(b_scores, b_windows, fp_cost=fp_cost, fn_cost=fn_cost)
            block_rows.append(
                {
                    "side": side,
                    "block_idx": int(block_idx),
                    "pred_batch_start": min(block_batches) if block_batches else None,
                    "pred_batch_end": max(block_batches) if block_batches else None,
                    **metrics,
                }
            )
    return block_rows, side_summary


def reliability_block_summary(candidate_window_rows: list[dict[str, Any]], *, block_size: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    keys = sorted({(str(row.get("side")), str(row.get("candidate_name"))) for row in candidate_window_rows})
    for side, candidate_name_ in keys:
        candidate_rows = [
            row
            for row in candidate_window_rows
            if row.get("side") == side and row.get("candidate_name") == candidate_name_ and row.get("status") == "ok"
        ]
        pred_batches = sorted({int(row["router_pred_batch_id"]) for row in candidate_rows})
        for block_idx, start in enumerate(range(0, len(pred_batches), max(1, int(block_size)))):
            block_batches = set(pred_batches[start : start + max(1, int(block_size))])
            block_candidate_rows = [row for row in candidate_rows if int(row["router_pred_batch_id"]) in block_batches]
            metrics = aggregate_window_count_rows(block_candidate_rows)
            rows.append(
                {
                    "side": side,
                    "candidate_name": candidate_name_,
                    "block_idx": int(block_idx),
                    "pred_batch_start": min(block_batches) if block_batches else None,
                    "pred_batch_end": max(block_batches) if block_batches else None,
                    **metrics,
                }
            )
    return rows


def row_rule_gate_enabled(args: argparse.Namespace) -> bool:
    return str(getattr(args, "row_rule_gate_mode", ROW_RULE_GATE_OFF)) != ROW_RULE_GATE_OFF


def row_rule_gate_config_row(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "mode": str(getattr(args, "row_rule_gate_mode", ROW_RULE_GATE_OFF)),
        "output_mode": str(getattr(args, "row_rule_gate_output_mode", ROW_RULE_GATE_OUTPUT_SHADOW)),
        "side": str(getattr(args, "row_rule_gate_side", SIDE_DOWN)),
        "candidate_name": str(getattr(args, "row_rule_gate_candidate_name", "down_rocket_16_diag_v1")),
        "block_size": int(getattr(args, "row_rule_gate_block_size", 60)),
        "rpf_max_features_per_family": int(getattr(args, "row_rule_gate_rpf_max_features_per_family", 24)),
        "key": str(getattr(args, "row_rule_gate_key", "feature_direction")),
        "rule_quantiles": str(getattr(args, "row_rule_gate_quantiles", "0.2,0.3,0.4,0.5,0.6,0.7,0.75,0.8,0.85,0.9")),
        "rule_selection_score": str(getattr(args, "row_rule_gate_rule_selection_score", "directional_lcb_v1")),
        "allowed_directions": list(parse_optional_csv(str(getattr(args, "row_rule_gate_allowed_directions", "")))),
        "allowed_families": list(parse_optional_csv(str(getattr(args, "row_rule_gate_allowed_families", "")))),
        "blocked_families": list(parse_optional_csv(str(getattr(args, "row_rule_gate_blocked_families", "")))),
        "max_rules_per_candidate": int(getattr(args, "row_rule_gate_max_rules_per_candidate", 1)),
        "min_train_tp_rows": int(getattr(args, "row_rule_gate_min_train_tp_rows", 2)),
        "min_train_fp_rows": int(getattr(args, "row_rule_gate_min_train_fp_rows", 2)),
        "eligibility": {
            "min_train_signals": int(getattr(args, "row_rule_gate_min_train_signals", 8)),
            "min_train_precision": float(getattr(args, "row_rule_gate_min_train_precision", 0.65)),
            "min_train_precision_lcb": float(getattr(args, "row_rule_gate_min_train_precision_lcb", 0.45)),
            "min_train_lift": float(getattr(args, "row_rule_gate_min_train_lift", 1.25)),
            "max_train_false_discovery_rate": float(getattr(args, "row_rule_gate_max_train_fdr", 0.35)),
            "max_train_accepted_rate": float(getattr(args, "row_rule_gate_max_train_accepted_rate", 0.35)),
        },
        "reliability": {
            "min_history_folds": int(getattr(args, "row_rule_gate_reliability_min_history_folds", 1)),
            "min_signals": int(getattr(args, "row_rule_gate_reliability_min_signals", 8)),
            "min_precision_lcb": float(getattr(args, "row_rule_gate_reliability_min_precision_lcb", 0.45)),
            "max_false_discovery_rate": float(getattr(args, "row_rule_gate_reliability_max_fdr", 0.50)),
            "lookback_folds": int(getattr(args, "row_rule_gate_reliability_lookback_folds", 0)),
        },
    }


def empty_row_rule_gate_outputs() -> dict[str, list[dict[str, Any]]]:
    keys = (
        "signal_rows",
        "candidate_rows",
        "rule_rows",
        "rule_acceptance_rows",
        "shadow_rule_acceptance_rows",
        "reliability_snapshot_rows",
        "selection_audit_rows",
        "decision_rows",
        "fold_summary",
        "overall_summary",
        "fold_comparison",
        "overall_comparison",
    )
    return {key: [] for key in keys}


def build_row_rule_gate_outputs(
    candidate_score_rows: list[dict[str, Any]],
    *,
    context: Any,
    selected_outer_windows: list[RPFWindow],
    run_root: Path,
    args: argparse.Namespace,
) -> dict[str, list[dict[str, Any]]]:
    if not row_rule_gate_enabled(args):
        return empty_row_rule_gate_outputs()
    raw = row_rule_gate_signal_frame(
        candidate_score_rows,
        selected_outer_windows=selected_outer_windows,
        run_root=run_root,
        side=str(args.row_rule_gate_side),
        candidate_name=str(args.row_rule_gate_candidate_name),
        block_size=int(args.row_rule_gate_block_size),
    )
    if raw.is_empty():
        return empty_row_rule_gate_outputs()
    keys = raw.select(["timestamp", "batch_id"]).unique()
    rpf_context = build_row_rpf_context(
        context,
        keys,
        max_features_per_family=int(args.row_rule_gate_rpf_max_features_per_family),
    )
    if rpf_context.is_empty():
        return empty_row_rule_gate_outputs() | {"signal_rows": raw.to_dicts()}
    enriched = raw.join(rpf_context, on=["timestamp", "batch_id"], how="left")
    safe = safe_row_context_features(enriched)
    join_keys = [
        col
        for col in [
            "source_run",
            "source_block",
            "side",
            "candidate_name",
            "router_step_idx",
            "router_pred_batch_id",
            "timestamp",
            "batch_id",
        ]
        if col in safe.columns and col in enriched.columns
    ]
    frame = safe.join(
        enriched.select([*join_keys, "signal_tp", "signal_fp"]),
        on=join_keys,
        how="inner",
    )
    if frame.is_empty():
        return empty_row_rule_gate_outputs() | {"signal_rows": enriched.to_dicts()}
    feature_columns = safe_row_rule_numeric_feature_columns(frame)
    blocks = chronological_row_rule_blocks(frame)
    folds = build_row_rule_forward_folds(blocks, min_train_blocks=1, rolling_train_blocks=1)
    eligibility = RowRuleEligibilityConfig(
        min_train_signals=int(args.row_rule_gate_min_train_signals),
        min_train_precision=float(args.row_rule_gate_min_train_precision),
        min_train_precision_lcb=float(args.row_rule_gate_min_train_precision_lcb),
        min_train_lift=float(args.row_rule_gate_min_train_lift),
        max_train_false_discovery_rate=float(args.row_rule_gate_max_train_fdr),
        max_train_accepted_rate=float(args.row_rule_gate_max_train_accepted_rate),
        lcb_z=float(args.row_rule_gate_lcb_z),
        min_feature_auc_abs=float(args.row_rule_gate_min_feature_auc_abs),
        require_feature_direction_agreement=bool(args.row_rule_gate_require_feature_direction_agreement),
        allowed_directions=parse_optional_csv(str(args.row_rule_gate_allowed_directions)),
    )
    reliability = RowRuleReliabilityConfig(
        min_history_folds=int(args.row_rule_gate_reliability_min_history_folds),
        min_signals=int(args.row_rule_gate_reliability_min_signals),
        min_precision_lcb=float(args.row_rule_gate_reliability_min_precision_lcb),
        max_false_discovery_rate=float(args.row_rule_gate_reliability_max_fdr),
        lcb_z=float(args.row_rule_gate_reliability_lcb_z),
        key_mode=str(args.row_rule_gate_key),
        warmup_mode=str(args.row_rule_gate_reliability_warmup_mode),
        lookback_folds=int(args.row_rule_gate_reliability_lookback_folds),
    )
    quantiles = parse_float_tuple(str(args.row_rule_gate_quantiles))

    candidate_rows: list[dict[str, Any]] = []
    rule_rows: list[dict[str, Any]] = []
    rule_acceptance_rows: list[dict[str, Any]] = []
    shadow_rule_acceptance_rows: list[dict[str, Any]] = []
    reliability_snapshot_rows: list[dict[str, Any]] = []
    selection_audit_rows: list[dict[str, Any]] = []
    shadow_history_rows: list[dict[str, Any]] = []
    union_frames: list[pl.DataFrame] = []
    for fold_idx, train_blocks, test_block in folds:
        train = frame.filter(pl.col("source_block").is_in(train_blocks))
        test = frame.filter(pl.col("source_block") == test_block)
        if train.is_empty() or test.is_empty():
            continue
        raw_rules = train_row_rules(
            train,
            feature_columns=feature_columns,
            fold_idx=fold_idx,
            train_blocks=train_blocks,
            test_block=test_block,
            quantiles=quantiles,
            min_train_tp_rows=int(args.row_rule_gate_min_train_tp_rows),
            min_train_fp_rows=int(args.row_rule_gate_min_train_fp_rows),
            lcb_z=float(eligibility.lcb_z),
        )
        eligible_rules, audit_rows = filter_eligible_row_rules(raw_rules, eligibility)
        eligible_rules, family_audit_rows = filter_row_rules_by_family(
            eligible_rules,
            allowed_families=parse_optional_csv(str(args.row_rule_gate_allowed_families)),
            blocked_families=parse_optional_csv(str(args.row_rule_gate_blocked_families)),
        )
        shadow_rows = replay_rules(test, eligible_rules, rule_level=True)
        shadow_rule_acceptance_rows.extend([row | {"shadow_rule": True} for row in shadow_rows])
        reliability_source_rows = recent_shadow_history_rows(shadow_history_rows, reliability.lookback_folds)
        reliability_rows = rule_reliability_rows(reliability_source_rows, reliability)
        reliability_snapshot_rows.extend(
            [row | {"fold_idx": int(fold_idx), "test_block": str(test_block)} for row in reliability_rows]
        )
        selected_rules, audit = select_prequential_reliable_rules(
            eligible_rules,
            reliability_rows=reliability_rows,
            config=reliability,
            max_rules_per_candidate=int(args.row_rule_gate_max_rules_per_candidate),
            fallback_selection_score=str(args.row_rule_gate_rule_selection_score),
        )
        candidate_rows.extend(audit_rows)
        selection_audit_rows.extend(family_audit_rows)
        selection_audit_rows.extend(audit)
        rule_rows.extend([row_rule_with_eligibility(rule, eligibility) for rule in selected_rules])
        rule_acceptance_rows.extend(replay_rules(test, selected_rules, rule_level=True))
        union = replay_rules_union(test, selected_rules)
        if not union.is_empty():
            union_frames.append(union)
        shadow_history_rows.extend(shadow_rows)

    union_acceptance = pl.concat(union_frames, how="diagonal_relaxed") if union_frames else pl.DataFrame()
    fold_summary = summarize_acceptance(union_acceptance, by=["fold_idx", "train_blocks", "test_block", "side", "candidate_name"])
    overall_summary = summarize_acceptance(union_acceptance, by=["side", "candidate_name"])
    fold_comparison = compare_fold_summary_with_raw(frame, fold_summary)
    overall_comparison = compare_overall_summary_with_raw(frame, fold_summary, overall_summary)
    return {
        "signal_rows": frame.to_dicts(),
        "candidate_rows": candidate_rows,
        "rule_rows": rule_rows,
        "rule_acceptance_rows": rule_acceptance_rows,
        "shadow_rule_acceptance_rows": shadow_rule_acceptance_rows,
        "reliability_snapshot_rows": reliability_snapshot_rows,
        "selection_audit_rows": selection_audit_rows,
        "decision_rows": union_acceptance.to_dicts(),
        "fold_summary": fold_summary,
        "overall_summary": overall_summary,
        "fold_comparison": fold_comparison,
        "overall_comparison": overall_comparison,
    }


def filter_row_rules_by_family(
    rules: list[Any],
    *,
    allowed_families: tuple[str, ...],
    blocked_families: tuple[str, ...],
) -> tuple[list[Any], list[dict[str, Any]]]:
    allowed = {str(item) for item in allowed_families if str(item)}
    blocked = {str(item) for item in blocked_families if str(item)}
    if not allowed and not blocked:
        return list(rules), []
    kept: list[Any] = []
    audit_rows: list[dict[str, Any]] = []
    for rule in rules:
        family = row_rule_feature_family(str(rule.feature))
        reasons: list[str] = []
        if allowed and family not in allowed:
            reasons.append("family_not_allowed")
        if blocked and family in blocked:
            reasons.append("family_blocked")
        if reasons:
            audit_rows.append(row_rule_family_filter_audit_row(rule, family=family, reasons=reasons))
        else:
            kept.append(rule)
    return kept, audit_rows


def row_rule_family_filter_audit_row(rule: Any, *, family: str, reasons: list[str]) -> dict[str, Any]:
    from dataclasses import asdict, is_dataclass

    payload = asdict(rule) if is_dataclass(rule) else dict(vars(rule))
    payload.update(
        {
            "selected": False,
            "row_rule_selection_mode": "family_filter",
            "selection_score": None,
            "selection_reject_reasons": ",".join(reasons),
            "family_filter_feature_family": str(family),
        }
    )
    return payload


def row_rule_with_eligibility(rule: Any, config: RowRuleEligibilityConfig) -> dict[str, Any]:
    from dataclasses import asdict

    from regression_feature_engineering.walkforward.rank_signal_row_rule_bank import row_rule_eligibility_row

    return asdict(rule) | row_rule_eligibility_row(rule, config)


def row_rule_gate_signal_frame(
    candidate_score_rows: list[dict[str, Any]],
    *,
    selected_outer_windows: list[RPFWindow],
    run_root: Path,
    side: str,
    candidate_name: str,
    block_size: int,
) -> pl.DataFrame:
    if not candidate_score_rows:
        return pl.DataFrame()
    frame = pl.DataFrame(candidate_score_rows, infer_schema_length=None)
    if frame.is_empty():
        return frame
    if "candidate_name" not in frame.columns and "selected_candidate" in frame.columns:
        frame = frame.rename({"selected_candidate": "candidate_name"})
    if "router_pred_batch_id" not in frame.columns and "pred_batch_id" in frame.columns:
        frame = frame.with_columns(pl.col("pred_batch_id").alias("router_pred_batch_id"))
    if "pred_batch_id" not in frame.columns and "router_pred_batch_id" in frame.columns:
        frame = frame.with_columns(pl.col("router_pred_batch_id").alias("pred_batch_id"))
    needed = {"side", "candidate_name", "decision", "timestamp", "batch_id", "target_binary", "router_pred_batch_id"}
    missing = sorted(needed - set(frame.columns))
    if missing:
        raise ValueError(f"Row-rule gate candidate scores missing columns: {missing}")
    block_map = row_rule_gate_source_block_map(selected_outer_windows, block_size=block_size)
    out = frame.filter(
        (pl.col("side") == str(side))
        & (pl.col("candidate_name") == str(candidate_name))
        & (pl.col("decision").fill_null(0).cast(pl.Int8) == 1)
    )
    if out.is_empty():
        return out
    return add_signal_outcome_labels(
        out.with_columns(
            pl.lit(str(run_root)).alias("source_run"),
            pl.col("router_pred_batch_id")
            .cast(pl.Int64)
            .map_elements(lambda value: block_map.get(int(value), "unknown"), return_dtype=pl.String)
            .alias("source_block"),
            pl.lit("router_shadow_candidate_prediction_scores").alias("score_source"),
        )
    ).sort(["source_block", "side", "candidate_name", "router_pred_batch_id", "timestamp"])


def row_rule_gate_source_block_map(selected_outer_windows: list[RPFWindow], *, block_size: int) -> dict[int, str]:
    block = max(1, int(block_size))
    return {
        int(window.pred_batch_id): f"block{idx // block:03d}"
        for idx, window in enumerate(selected_outer_windows)
    }


def empty_row_rule_active_outputs() -> dict[str, Any]:
    return {
        "score_rows": [],
        "decision_rows": [],
        "window_rows": [],
        "block_rows": [],
        "side_summary": {},
    }


def resolve_effective_router_outputs(
    *,
    score_rows: list[dict[str, Any]],
    decision_rows: list[dict[str, Any]],
    window_rows: list[dict[str, Any]],
    block_rows: list[dict[str, Any]],
    side_summary: dict[str, Any],
    row_rule_active_outputs: dict[str, Any],
    args: argparse.Namespace,
) -> dict[str, Any]:
    output_mode = str(getattr(args, "row_rule_gate_output_mode", ROW_RULE_GATE_OUTPUT_SHADOW))
    row_rule_score_rows = list(row_rule_active_outputs.get("score_rows", []))
    row_rule_window_rows = list(row_rule_active_outputs.get("window_rows", []))
    use_row_rule_active = (
        output_mode in {ROW_RULE_GATE_OUTPUT_ACTIVE_CANDIDATE, ROW_RULE_GATE_OUTPUT_ACTIVE_DOWN_CANDIDATE}
        and (bool(row_rule_score_rows) or bool(row_rule_window_rows))
    )
    if use_row_rule_active:
        source = "row_rule_active"
        return {
            "prediction_source": source,
            "score_rows": rows_with_prediction_source(row_rule_score_rows, source),
            "decision_rows": rows_with_prediction_source(list(row_rule_active_outputs.get("decision_rows", [])), source),
            "window_rows": rows_with_prediction_source(row_rule_window_rows, source),
            "block_rows": rows_with_prediction_source(list(row_rule_active_outputs.get("block_rows", [])), source),
            "side_summary": side_summary_with_prediction_source(dict(row_rule_active_outputs.get("side_summary", {})), source),
        }
    source = "router_selected"
    return {
        "prediction_source": source,
        "score_rows": rows_with_prediction_source(list(score_rows), source),
        "decision_rows": rows_with_prediction_source(list(decision_rows), source),
        "window_rows": rows_with_prediction_source(list(window_rows), source),
        "block_rows": rows_with_prediction_source(list(block_rows), source),
        "side_summary": side_summary_with_prediction_source(dict(side_summary), source),
    }


def rows_with_prediction_source(rows: list[dict[str, Any]], source: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        item = {**row, "prediction_source": source}
        if "candidate_name" not in item and item.get("selected_candidate") is not None:
            item["candidate_name"] = item.get("selected_candidate")
        out.append(item)
    return out


def side_summary_with_prediction_source(summary: dict[str, Any], source: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in summary.items():
        if isinstance(value, dict):
            out[key] = {**value, "prediction_source": source}
        else:
            out[key] = value
    if "prediction_source" not in out:
        out["prediction_source"] = source
    return out


def build_row_rule_active_outputs(
    candidate_score_rows: list[dict[str, Any]],
    *,
    row_rule_gate_decisions: list[dict[str, Any]],
    selected_outer_windows: list[RPFWindow],
    args: argparse.Namespace,
    fp_cost: float,
    fn_cost: float,
    high_target_positive_rate_threshold: float,
    high_false_positive_rate_threshold: float,
) -> dict[str, Any]:
    output_mode = str(getattr(args, "row_rule_gate_output_mode", ROW_RULE_GATE_OUTPUT_SHADOW))
    if output_mode not in {ROW_RULE_GATE_OUTPUT_ACTIVE_CANDIDATE, ROW_RULE_GATE_OUTPUT_ACTIVE_DOWN_CANDIDATE}:
        return empty_row_rule_active_outputs()
    if not row_rule_gate_enabled(args):
        raise ValueError(f"--row-rule-gate-output-mode {output_mode} requires --row-rule-gate-mode")
    if output_mode == ROW_RULE_GATE_OUTPUT_ACTIVE_DOWN_CANDIDATE and str(args.row_rule_gate_side) != SIDE_DOWN:
        raise ValueError("active_down_candidate is intentionally DOWN-only in v1")
    if not candidate_score_rows:
        return empty_row_rule_active_outputs()
    frame = pl.DataFrame(candidate_score_rows, infer_schema_length=None)
    if frame.is_empty():
        return empty_row_rule_active_outputs()
    if "candidate_name" not in frame.columns and "selected_candidate" in frame.columns:
        frame = frame.rename({"selected_candidate": "candidate_name"})
    if "router_pred_batch_id" not in frame.columns and "pred_batch_id" in frame.columns:
        frame = frame.with_columns(pl.col("pred_batch_id").alias("router_pred_batch_id"))
    if "pred_batch_id" not in frame.columns and "router_pred_batch_id" in frame.columns:
        frame = frame.with_columns(pl.col("router_pred_batch_id").alias("pred_batch_id"))
    needed = {"side", "candidate_name", "timestamp", "batch_id", "target_binary", "router_pred_batch_id"}
    missing = sorted(needed - set(frame.columns))
    if missing:
        raise ValueError(f"Row-rule active candidate scores missing columns: {missing}")
    active = frame.filter(
        (pl.col("side") == str(args.row_rule_gate_side))
        & (pl.col("candidate_name") == str(args.row_rule_gate_candidate_name))
    )
    if active.is_empty():
        return empty_row_rule_active_outputs()
    accepted_keys = row_rule_active_decision_keys(row_rule_gate_decisions)
    block_map = row_rule_gate_source_block_map(selected_outer_windows, block_size=int(args.row_rule_gate_block_size))
    rows: list[dict[str, Any]] = []
    for row in active.to_dicts():
        key = row_rule_active_key(row)
        raw_decision = int(row.get("decision") or 0)
        decision = 1 if key in accepted_keys else 0
        row.update(
            {
                "raw_candidate_decision": raw_decision,
                "decision": decision,
                "row_rule_active_candidate": str(args.row_rule_gate_candidate_name),
                "row_rule_gate_output_mode": str(args.row_rule_gate_output_mode),
                "row_rule_gate_mode": str(args.row_rule_gate_mode),
                "source_block": block_map.get(int(row["router_pred_batch_id"]), "unknown"),
                "score_source": "row_rule_active_candidate_prediction_scores",
            }
        )
        rows.append(row)
    decision_rows = [row for row in rows if int(row.get("decision", 0)) == 1]
    window_rows = row_rule_active_window_metrics(
        rows,
        fp_cost=fp_cost,
        fn_cost=fn_cost,
        high_target_positive_rate_threshold=high_target_positive_rate_threshold,
        high_false_positive_rate_threshold=high_false_positive_rate_threshold,
        output_mode=output_mode,
    )
    block_rows, side_summary = summarize_router_outputs(
        rows,
        window_rows,
        block_size=int(args.evaluation_block_size),
        fp_cost=fp_cost,
        fn_cost=fn_cost,
    )
    return {
        "score_rows": rows,
        "decision_rows": decision_rows,
        "window_rows": window_rows,
        "block_rows": block_rows,
        "side_summary": side_summary,
    }


def row_rule_active_decision_keys(rows: list[dict[str, Any]]) -> set[tuple[int, str, int]]:
    return {row_rule_active_key(row) for row in rows}


def row_rule_active_key(row: dict[str, Any]) -> tuple[int, str, int]:
    pred_batch = row.get("router_pred_batch_id", row.get("pred_batch_id"))
    return (int(pred_batch), str(row["timestamp"]), int(row["batch_id"]))


def row_rule_active_window_metrics(
    score_rows: list[dict[str, Any]],
    *,
    fp_cost: float,
    fn_cost: float,
    high_target_positive_rate_threshold: float,
    high_false_positive_rate_threshold: float,
    output_mode: str,
) -> list[dict[str, Any]]:
    if not score_rows:
        return []
    frame = pl.DataFrame(score_rows, infer_schema_length=None)
    rows: list[dict[str, Any]] = []
    for item in frame.select(["side", "candidate_name", "router_pred_batch_id"]).unique().sort(["side", "candidate_name", "router_pred_batch_id"]).to_dicts():
        pred_batch_id = int(item["router_pred_batch_id"])
        batch = frame.filter(
            (pl.col("side") == item["side"])
            & (pl.col("candidate_name") == item["candidate_name"])
            & (pl.col("router_pred_batch_id") == pred_batch_id)
        )
        y = batch["target_binary"].fill_null(0).cast(pl.Int8).to_numpy().astype(int)
        decision = batch["decision"].fill_null(0).cast(pl.Int8).to_numpy().astype(int)
        metric = simple_window_metric_row(
            y,
            decision,
            fp_cost=float(fp_cost),
            fn_cost=float(fn_cost),
            high_target_positive_rate_threshold=float(high_target_positive_rate_threshold),
            high_false_positive_rate_threshold=float(high_false_positive_rate_threshold),
        )
        metric.update(
            {
                "split": "prediction",
                "side": str(item["side"]),
                "candidate_name": str(item["candidate_name"]),
                "selected_candidate": str(item["candidate_name"]),
                "step_idx": int(batch["router_step_idx"][0]) if "router_step_idx" in batch.columns else None,
                "pred_batch_id": pred_batch_id,
                "router_pred_batch_id": pred_batch_id,
                "row_rule_gate_output_mode": output_mode,
            }
        )
        rows.append(metric)
    return rows


def aggregate_window_count_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total_rows = int(sum(int(row.get("rows") or 0) for row in rows))
    positive_count = int(sum(int(row.get("positive_count") or 0) for row in rows))
    negative_count = int(sum(int(row.get("negative_count") or 0) for row in rows))
    signals = int(sum(int(row.get("predicted_positive_count") or 0) for row in rows))
    tp = int(sum(int(row.get("true_positive_count") or 0) for row in rows))
    fp = int(sum(int(row.get("false_positive_count") or 0) for row in rows))
    fn = int(sum(int(row.get("false_negative_count") or 0) for row in rows))
    tn = int(sum(int(row.get("true_negative_count") or 0) for row in rows))
    precision = safe_ratio(tp, signals)
    base = safe_ratio(positive_count, total_rows)
    active_windows = sum(1 for row in rows if bool(row.get("active_window")))
    high_fp = sum(1 for row in rows if bool(row.get("high_false_positive_window")))
    active_rows = [row for row in rows if bool(row.get("active_window"))]
    active_positive_count = int(sum(int(row.get("positive_count") or 0) for row in active_rows))
    active_total_rows = int(sum(int(row.get("rows") or 0) for row in active_rows))
    active_base = safe_ratio(active_positive_count, active_total_rows)
    precision_lcb = wilson_lower_bound(tp, signals, z=1.0)
    return {
        "windows": int(len(rows)),
        "rows": total_rows,
        "positive_count": positive_count,
        "negative_count": negative_count,
        "predicted_positive_count": signals,
        "true_positive_count": tp,
        "false_positive_count": fp,
        "false_negative_count": fn,
        "true_negative_count": tn,
        "precision": precision,
        "base_positive_rate": base,
        "precision_lift": safe_ratio(precision, base) if precision is not None and base and base > 0 else None,
        "precision_lift_lcb": safe_ratio(precision_lcb, base) if precision_lcb is not None and base and base > 0 else None,
        "false_discovery_rate": safe_ratio(fp, signals),
        "active_window_rate": safe_ratio(active_windows, len(rows)) or 0.0,
        "zero_signal_window_rate": 1.0 - (safe_ratio(active_windows, len(rows)) or 0.0),
        "high_false_positive_window_rate": safe_ratio(high_fp, len(rows)) or 0.0,
        "active_window_count": int(active_windows),
        "active_window_positive_count": active_positive_count,
        "active_window_rows": active_total_rows,
        "active_window_base_rate": active_base,
        "window_selection_lift": safe_ratio(active_base, base) if active_base is not None and base and base > 0 else None,
        "selected_window_precision_lcb": precision_lcb,
        "selected_window_row_lift": safe_ratio(precision, active_base) if precision is not None and active_base and active_base > 0 else None,
        "selected_window_row_lift_lcb": (
            safe_ratio(precision_lcb, active_base) if precision_lcb is not None and active_base and active_base > 0 else None
        ),
        "selected_window_false_discovery_rate": safe_ratio(fp, signals),
    }


def aggregate_score_window_rows(
    score_rows: list[dict[str, Any]],
    window_rows: list[dict[str, Any]],
    *,
    fp_cost: float,
    fn_cost: float,
) -> dict[str, Any]:
    if not score_rows:
        return {"status": "empty"}
    y = np.asarray([int(row["target_binary"]) for row in score_rows], dtype=int)
    decision = np.asarray([int(row["decision"]) for row in score_rows], dtype=int)
    selected_mean = float(np.mean([finite(row.get("selected_feature_count"), 0.0) for row in window_rows])) if window_rows else 0.0
    return aggregate_prediction_metrics(
        y,
        decision,
        window_rows,
        fp_cost=float(fp_cost),
        fn_cost=float(fn_cost),
        selected_feature_count_mean=selected_mean,
    )


def conflict_diagnostics(score_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    up = {
        (int(row["pred_batch_id"]), str(row["timestamp"])): row
        for row in score_rows
        if row.get("side") == SIDE_UP and int(row.get("decision", 0)) == 1
    }
    down = {
        (int(row["pred_batch_id"]), str(row["timestamp"])): row
        for row in score_rows
        if row.get("side") == SIDE_DOWN and int(row.get("decision", 0)) == 1
    }
    rows: list[dict[str, Any]] = []
    for key in sorted(set(up) & set(down)):
        up_row = up[key]
        down_row = down[key]
        up_margin = float(up_row.get("margin") or 0.0)
        down_margin = float(down_row.get("margin") or 0.0)
        if abs(up_margin - down_margin) <= 1e-12:
            winner = "suppressed_equal_margin"
        else:
            winner = SIDE_UP if up_margin > down_margin else SIDE_DOWN
        rows.append(
            {
                "pred_batch_id": key[0],
                "timestamp": key[1],
                "up_candidate": up_row.get("selected_candidate"),
                "down_candidate": down_row.get("selected_candidate"),
                "up_rank_score": up_row.get("rank_score"),
                "down_rank_score": down_row.get("rank_score"),
                "up_threshold": up_row.get("threshold"),
                "down_threshold": down_row.get("threshold"),
                "up_margin": up_margin,
                "down_margin": down_margin,
                "combined_winner": winner,
            }
        )
    return rows


def candidate_config_row(candidate: CandidateSpec) -> dict[str, Any]:
    return {
        "name": candidate.name,
        "side": candidate.side,
        "diagnostic": bool(candidate.diagnostic),
        "config": trial_config_payload(candidate.config),
    }


def write_router_report(
    run_root: Path,
    *,
    router_config: dict[str, Any],
    side_summary: dict[str, Any],
    effective_side_summary: dict[str, Any],
    effective_prediction_source: str,
) -> None:
    write_markdown(
        run_root / "report.md",
        title="RPF Ranked Signal Router Report",
        sections={
            "Scope": {
                "asset": router_config["asset"],
                "root": router_config["root"],
                "candidate_set": router_config["candidate_set"],
                "selection_mode": router_config["selection_mode"],
                "outer_window_count": router_config["outer_window_count"],
            },
            "Effective Selected Summary": {
                "prediction_source": effective_prediction_source,
                "summary": effective_side_summary,
            },
            "Base Router Summary": side_summary,
            "Decision Contract": [
                "`effective_*` artifacts are the canonical selected output for this run.",
                "`router_*` artifacts are the base router stream.",
                "`row_rule_active_*` artifacts are the active row-rule stream when row-rule active output mode is enabled.",
                "Validation-only mode selects candidates from validation metrics only.",
                "Prequential reliability mode selects candidates from prior matured prediction-window reliability after current validation sanity checks.",
                "Context-rule mode selects candidates by prediction-safe candidate-specific rules loaded from a simulator artifact.",
                "Prediction metrics are outer evaluation and never choose a candidate.",
                "If no candidate passes the active selection contract, the side emits no signals for that prediction batch.",
                "Diagnostic artifacts include validation row scores, validation batch metrics, selected features, and sequence diagnostics.",
            ],
        },
    )


def run_root_for_args(*, asset: str, root: str) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    root_id = str(root).lower().replace("/", "_")
    return OUTPUT_ROOT / f"{timestamp}_rank_signal_router_{asset.lower()}_{root_id}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asset", default=None)
    parser.add_argument("--root", default=None)
    parser.add_argument("--base-run", required=True)
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--feature-ablation", default="all")
    parser.add_argument("--up-tabular-panel-path", required=True)
    parser.add_argument("--up-sequence-panel-path", required=True)
    parser.add_argument("--down-tabular-panel-path", required=True)
    parser.add_argument("--down-sequence-panel-path", required=True)
    parser.add_argument(
        "--candidate-set",
        choices=(CANDIDATE_SET_DEFAULT_V1, CANDIDATE_SET_PRUNED_RELIABILITY_V1),
        default=CANDIDATE_SET_DEFAULT_V1,
    )
    parser.add_argument(
        "--selection-mode",
        choices=(SELECTION_VALIDATION_ONLY, SELECTION_PREQUENTIAL_RELIABILITY_V1, SELECTION_CONTEXT_RULE_V1),
        default=SELECTION_VALIDATION_ONLY,
    )
    parser.add_argument(
        "--context-rule-path",
        default=None,
        help="Path to meta_router_rules.parquet or a simulator run directory for --selection-mode context_rule_v1.",
    )
    parser.add_argument("--specialist-entry-mode", choices=SPECIALIST_ENTRY_MODES, default=SPECIALIST_ENTRY_OFF)
    parser.add_argument("--include-diagnostic-candidates", action="store_true")
    parser.add_argument(
        "--candidate-name-allowlist",
        default="",
        help="Comma-separated candidate names to keep after --candidate-set expansion.",
    )
    parser.add_argument("--outer-window-count", type=int, default=20)
    parser.add_argument("--window-end-offset-steps", type=int, default=0)
    parser.add_argument("--evaluation-block-size", type=int, default=20)
    parser.add_argument("--fp-cost", type=float, default=5.0)
    parser.add_argument("--fn-cost", type=float, default=1.0)
    parser.add_argument("--high-target-positive-rate-threshold", type=float, default=0.20)
    parser.add_argument("--high-false-positive-rate-threshold", type=float, default=0.30)
    parser.add_argument("--batch-state-gate-mode", choices=BATCH_STATE_GATE_MODES, default=BATCH_STATE_GATE_OFF)
    parser.add_argument("--batch-state-gate-prefix-rows", type=int, default=60)
    parser.add_argument("--batch-state-gate-min-positive-rate", type=float, default=0.20)
    parser.add_argument("--batch-state-gate-probability-threshold", type=float, default=0.55)
    parser.add_argument("--batch-state-gate-c", type=float, default=0.5)
    parser.add_argument("--batch-state-gate-max-iter", type=int, default=1000)
    parser.add_argument("--batch-state-gate-min-train-batches", type=int, default=20)
    parser.add_argument("--batch-state-gate-min-positive-batches", type=int, default=3)
    parser.add_argument("--batch-state-gate-min-negative-batches", type=int, default=3)
    parser.add_argument("--min-validation-signal-count", type=int, default=3)
    parser.add_argument("--min-validation-precision-lift", type=float, default=1.10)
    parser.add_argument("--max-validation-false-discovery-rate", type=float, default=0.60)
    parser.add_argument("--min-validation-active-window-rate", type=float, default=0.10)
    parser.add_argument("--max-validation-zero-signal-window-rate", type=float, default=0.90)
    parser.add_argument("--min-validation-active-batch-count", type=int, default=0)
    parser.add_argument("--min-validation-lift-positive-batch-rate", type=float, default=0.0)
    parser.add_argument("--min-validation-median-active-precision-lift", type=float, default=0.0)
    parser.add_argument("--max-validation-median-active-false-discovery-rate", type=float, default=1.0)
    parser.add_argument("--reliability-lookback-windows", type=int, default=60)
    parser.add_argument("--reliability-min-history-windows", type=int, default=20)
    parser.add_argument("--reliability-min-signals", type=int, default=20)
    parser.add_argument("--reliability-min-active-windows", type=int, default=5)
    parser.add_argument("--reliability-min-precision-lift-lcb", type=float, default=1.05)
    parser.add_argument("--reliability-min-window-selection-lift", type=float, default=1.0)
    parser.add_argument("--reliability-min-selected-window-row-lift-lcb", type=float, default=1.05)
    parser.add_argument("--reliability-max-false-discovery-rate", type=float, default=0.60)
    parser.add_argument("--reliability-lcb-z", type=float, default=1.0)
    parser.add_argument("--reliability-warmup-policy", choices=(WARMUP_NO_SIGNAL,), default=WARMUP_NO_SIGNAL)
    parser.add_argument("--up-reliability-min-precision-lift-lcb", type=float, default=None)
    parser.add_argument("--down-reliability-min-precision-lift-lcb", type=float, default=None)
    parser.add_argument("--up-reliability-min-selected-window-row-lift-lcb", type=float, default=None)
    parser.add_argument("--down-reliability-min-selected-window-row-lift-lcb", type=float, default=None)
    parser.add_argument("--write-candidate-prediction-scores", action="store_true")
    parser.add_argument("--row-rule-gate-mode", choices=ROW_RULE_GATE_MODES, default=ROW_RULE_GATE_OFF)
    parser.add_argument("--row-rule-gate-output-mode", choices=ROW_RULE_GATE_OUTPUT_MODES, default=ROW_RULE_GATE_OUTPUT_SHADOW)
    parser.add_argument("--row-rule-gate-side", choices=SIDES, default=SIDE_DOWN)
    parser.add_argument("--row-rule-gate-candidate-name", default="down_rocket_16_diag_v1")
    parser.add_argument("--row-rule-gate-block-size", type=int, default=60)
    parser.add_argument("--row-rule-gate-rpf-max-features-per-family", type=int, default=24)
    parser.add_argument("--row-rule-gate-key", choices=("feature_direction", "family_direction"), default="feature_direction")
    parser.add_argument("--row-rule-gate-quantiles", default="0.2,0.3,0.4,0.5,0.6,0.7,0.75,0.8,0.85,0.9")
    parser.add_argument("--row-rule-gate-min-train-tp-rows", type=int, default=2)
    parser.add_argument("--row-rule-gate-min-train-fp-rows", type=int, default=2)
    parser.add_argument("--row-rule-gate-min-train-signals", type=int, default=8)
    parser.add_argument("--row-rule-gate-min-train-precision", type=float, default=0.65)
    parser.add_argument("--row-rule-gate-min-train-precision-lcb", type=float, default=0.45)
    parser.add_argument("--row-rule-gate-min-train-lift", type=float, default=1.25)
    parser.add_argument("--row-rule-gate-max-train-fdr", type=float, default=0.35)
    parser.add_argument("--row-rule-gate-max-train-accepted-rate", type=float, default=0.35)
    parser.add_argument("--row-rule-gate-lcb-z", type=float, default=1.0)
    parser.add_argument("--row-rule-gate-min-feature-auc-abs", type=float, default=0.0)
    parser.add_argument("--row-rule-gate-require-feature-direction-agreement", action="store_true")
    parser.add_argument(
        "--row-rule-gate-allowed-directions",
        default="",
        help="Optional comma-separated row-rule directions to keep, e.g. higher_good. Empty keeps both directions.",
    )
    parser.add_argument(
        "--row-rule-gate-allowed-families",
        default="",
        help="Optional comma-separated row-rule feature families to keep. Empty keeps all families not blocked.",
    )
    parser.add_argument(
        "--row-rule-gate-blocked-families",
        default="",
        help="Optional comma-separated row-rule feature families to suppress, e.g. rejection_chop.",
    )
    parser.add_argument("--row-rule-gate-rule-selection-score", choices=("rule_score", "directional_lcb_v1"), default="directional_lcb_v1")
    parser.add_argument("--row-rule-gate-max-rules-per-candidate", type=int, default=1)
    parser.add_argument("--row-rule-gate-reliability-min-history-folds", type=int, default=1)
    parser.add_argument("--row-rule-gate-reliability-min-signals", type=int, default=8)
    parser.add_argument("--row-rule-gate-reliability-min-precision-lcb", type=float, default=0.45)
    parser.add_argument("--row-rule-gate-reliability-max-fdr", type=float, default=0.50)
    parser.add_argument("--row-rule-gate-reliability-lcb-z", type=float, default=1.0)
    parser.add_argument("--row-rule-gate-reliability-warmup-mode", choices=("no_signal", "static"), default="no_signal")
    parser.add_argument(
        "--row-rule-gate-reliability-lookback-folds",
        type=int,
        default=0,
        help="Use only the last N matured row-rule folds for reliability; 0 keeps all prior history.",
    )
    parser.add_argument("--task-type", choices=("CPU", "GPU"), default="CPU")
    parser.add_argument("--thread-count", type=int, default=8)
    parser.add_argument("--log-every-windows", type=int, default=1)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
