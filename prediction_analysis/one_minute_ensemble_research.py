#!/usr/bin/env python3
"""
1m-only cross-target ensemble research harness.

Purpose:
- Reuse core walk-forward logic from multitimeframe_cross_target_ensemble_search.py
- Restrict candidate predictors to 1m units only:
    - 1m/target_breakfree
    - 1m/target_4class
- Compare method/rule combinations under the same truth mapping used in production
  (truth anchored from 15m target labels).
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl


DEFAULT_OUTPUT_DIR = "prediction_analysis/multitimeframe_cross_target_validation"
DEFAULT_UNITS = ["1m/target_breakfree", "1m/target_4class"]


@dataclass
class ComboResult:
    method_row: dict[str, Any]
    batch_rows: list[dict[str, Any]]
    calib_rows: list[dict[str, Any]]
    selection_rows: list[dict[str, Any]]
    final_predictions: pl.DataFrame | None
    head_metrics: dict[str, Any]


def _parse_csv_list(raw: str) -> list[str]:
    vals = [x.strip() for x in str(raw).split(",") if x.strip()]
    out: list[str] = []
    for v in vals:
        if v not in out:
            out.append(v)
    return out


def _load_core_module(project_root: Path):
    mod_path = (project_root / "prediction_analysis" / "multitimeframe_cross_target_ensemble_search.py").resolve()
    spec = importlib.util.spec_from_file_location("ctes_mod", mod_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module spec: {mod_path}")
    mod = importlib.util.module_from_spec(spec)
    # Required for dataclass type resolution inside imported module.
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _resolve_ensemble_run_dir(project_root: Path, arg: str, mod) -> Path:
    return mod._resolve_ensemble_run_dir(project_root, arg)


def _build_candidate_meta(candidate_sets: dict[str, Any], units: list[str]) -> pl.DataFrame:
    rows: list[dict[str, Any]] = []
    for unit in units:
        meta = candidate_sets.get(unit)
        if meta is None:
            raise KeyError(f"Unit not found in candidate sets: {unit}")
        tf, target = unit.split("/", 1)
        wins = {str(k): int(v) for k, v in (meta.get("winner_wins", {}) or {}).items()}
        action_keys = [str(v) for v in (meta.get("action_keys", []) or [])]
        if not action_keys:
            raise ValueError(f"No candidates for unit: {unit}")
        for action_key in action_keys:
            rows.append(
                {
                    "candidate_id": f"{unit}::{action_key}",
                    "unit": unit,
                    "timeframe": tf,
                    "target": target,
                    "action_key": action_key,
                    "winner_wins": int(wins.get(action_key, 0)),
                }
            )
    return pl.DataFrame(rows).sort(["unit", "action_key"])


def _progress(msg: str, verbose: bool) -> None:
    if verbose:
        print(msg, flush=True)


def _build_selection_schedule(
    *,
    data,
    mod,
    mode: str,
    warmup_batches: int,
    recalibrate_every: int,
    selection_mode: str,
    min_candidates_per_unit: int,
    max_prune_iterations: int,
    verbose: bool,
) -> tuple[dict[int, tuple[np.ndarray, np.ndarray]], list[dict[str, Any]]]:
    schedule: dict[int, tuple[np.ndarray, np.ndarray]] = {}
    logs: list[dict[str, Any]] = []

    idx_all = np.arange(len(data.candidate_ids), dtype=np.int32)
    idx_b = idx_all[data.candidate_targets == mod.TARGET_BREAKFREE]
    idx_4 = idx_all[data.candidate_targets == mod.TARGET_4CLASS]

    if selection_mode == "all_candidates":
        for i, batch in enumerate(data.batch_order):
            if i < int(warmup_batches):
                continue
            if i == int(warmup_batches) or (((i - int(warmup_batches)) % int(recalibrate_every)) == 0):
                schedule[int(batch)] = (idx_b.copy(), idx_4.copy())
                logs.append(
                    {
                        "alignment_mode": mode,
                        "pred_batch": int(batch),
                        "history_start_anchor": 0,
                        "history_end_anchor": int(data.batch_ranges[int(batch)][0]),
                        "lookback_requested": -1,
                        "lookback_effective": int(data.batch_ranges[int(batch)][0]),
                        "selected_break_count": int(idx_b.size),
                        "selected_4dir_count": int(idx_4.size),
                        "selection_mode": "all_candidates",
                    }
                )
        return schedule, logs

    # Hybrid staged (history-only, full-history lookback).
    for i, batch in enumerate(data.batch_order):
        if i < int(warmup_batches):
            continue
        if i == int(warmup_batches) or (((i - int(warmup_batches)) % int(recalibrate_every)) == 0):
            history_end = int(data.batch_ranges[int(batch)][0])
            sb, s4, prune_logs = mod._hybrid_staged_selection(
                data=data,
                history_start=0,
                history_end=history_end,
                min_per_unit=int(min_candidates_per_unit),
                max_prune_iterations=int(max_prune_iterations),
                verbose=False,
            )
            schedule[int(batch)] = (sb, s4)
            logs.append(
                {
                    "alignment_mode": mode,
                    "pred_batch": int(batch),
                    "history_start_anchor": 0,
                    "history_end_anchor": int(history_end),
                    "lookback_requested": -1,
                    "lookback_effective": int(history_end),
                    "selected_break_count": int(sb.size),
                    "selected_4dir_count": int(s4.size),
                    "selection_mode": "hybrid_staged",
                    "prune_ops_count": int(len(prune_logs)),
                }
            )
            if verbose:
                _progress(
                    f"[selection/{mode}] batch={int(batch)} break={int(sb.size)} dir4={int(s4.size)} "
                    f"prune_ops={len(prune_logs)}",
                    verbose,
                )
    return schedule, logs


def _rank_method_table(method_df: pl.DataFrame) -> pl.DataFrame:
    if method_df.is_empty():
        return method_df

    # Per-combo metric extraction may already include local rank columns.
    drop_cols = [c for c in ["rank", "rank_risk"] if c in method_df.columns]
    if drop_cols:
        method_df = method_df.drop(drop_cols)

    ranked = (
        method_df.sort(
            [
                "directional_active_accuracy",
                "opposite_fp_rate_active",
                "opposite_fp_rate_covered",
                "directional_fp_rate_covered",
                "hold_side_cross_error_rate_covered",
                "macro_f1",
                "custom_mean_cost",
                "directional_active_coverage",
                "coverage",
                "alignment_mode",
                "weight_method",
                "final_rule",
            ],
            descending=[True, False, False, False, False, True, False, True, True, False, False, False],
        ).with_row_index("rank", offset=1)
    )

    risk_rank = (
        method_df.sort(
            [
                "directional_fp_risk_score",
                "opposite_fp_rate_active",
                "opposite_fp_rate_covered",
                "directional_fp_rate_covered",
                "hold_side_cross_error_rate_covered",
                "directional_active_accuracy",
                "custom_mean_cost",
                "directional_active_coverage",
                "coverage",
                "alignment_mode",
                "weight_method",
                "final_rule",
            ],
            descending=[False, False, False, False, False, True, False, True, True, False, False, False],
        )
        .with_row_index("rank_risk", offset=1)
        .select(["alignment_mode", "weight_method", "final_rule", "rank_risk"])
    )

    return ranked.join(
        risk_rank,
        on=["alignment_mode", "weight_method", "final_rule"],
        how="left",
    ).sort("rank")


def _run_combo(
    *,
    mod,
    data,
    schedule: dict[int, tuple[np.ndarray, np.ndarray]],
    mode: str,
    breakfree_weight_method: str,
    dir4_weight_method: str,
    final_rule: str,
    args: argparse.Namespace,
    ) -> ComboResult:
    if breakfree_weight_method == dir4_weight_method:
        target_df, final_df, calib = mod._run_walkforward_combo(
            data=data,
            selection_schedule=schedule,
            weight_method=breakfree_weight_method,
            final_rule=final_rule,
            tau_grid=mod._parse_hold_band_grid(str(args.hold_band_grid)),
            ova_threshold_grid=mod._parse_hold_band_grid(str(args.ova_threshold_grid)),
            tau_objective=str(args.tau_objective),
            tau_fp_penalty=float(args.tau_fp_penalty),
            tau_opposite_fp_penalty=float(args.tau_opposite_fp_penalty),
            tau_hold_side_penalty=float(args.tau_hold_side_penalty),
            tau_opposite_active_penalty=float(args.tau_opposite_active_penalty),
            tau_min_active_coverage=float(args.tau_min_active_coverage),
            specialist_min_support=int(args.specialist_min_support),
            specialist_min_safe_accuracy=float(args.specialist_min_safe_accuracy),
            specialist_max_opposite_rate=float(args.specialist_max_opposite_rate),
            specialist_min_votes=int(args.specialist_min_votes),
            specialist_recency_decay=float(args.specialist_recency_decay),
            kalman_process_noise=float(args.kalman_process_noise),
            kalman_measurement_noise=float(args.kalman_measurement_noise),
            dma_forgetting_factor=float(args.dma_forgetting_factor),
            dma_fixed_share_alpha=float(args.dma_fixed_share_alpha),
            ewaf_brier_eta=float(args.ewaf_brier_eta),
            warmup_batches=int(args.wf_warmup_batches),
            recalibrate_every=int(args.wf_recalibrate_every),
            progress_every_batches=int(args.progress_every_batches),
            verbose=bool(args.inner_verbose),
            progress_log_path=None,
        )
        weight_method_label = breakfree_weight_method
    else:
        target_df, final_df, calib = _run_walkforward_combo_split_methods(
            mod=mod,
            data=data,
            selection_schedule=schedule,
            breakfree_weight_method=breakfree_weight_method,
            dir4_weight_method=dir4_weight_method,
            final_rule=final_rule,
            tau_grid=mod._parse_hold_band_grid(str(args.hold_band_grid)),
            ova_threshold_grid=mod._parse_hold_band_grid(str(args.ova_threshold_grid)),
            tau_objective=str(args.tau_objective),
            tau_fp_penalty=float(args.tau_fp_penalty),
            tau_opposite_fp_penalty=float(args.tau_opposite_fp_penalty),
            tau_hold_side_penalty=float(args.tau_hold_side_penalty),
            tau_opposite_active_penalty=float(args.tau_opposite_active_penalty),
            tau_min_active_coverage=float(args.tau_min_active_coverage),
            specialist_min_support=int(args.specialist_min_support),
            specialist_min_safe_accuracy=float(args.specialist_min_safe_accuracy),
            specialist_max_opposite_rate=float(args.specialist_max_opposite_rate),
            specialist_min_votes=int(args.specialist_min_votes),
            specialist_recency_decay=float(args.specialist_recency_decay),
            kalman_process_noise=float(args.kalman_process_noise),
            kalman_measurement_noise=float(args.kalman_measurement_noise),
            dma_forgetting_factor=float(args.dma_forgetting_factor),
            dma_fixed_share_alpha=float(args.dma_fixed_share_alpha),
            ewaf_brier_eta=float(args.ewaf_brier_eta),
            warmup_batches=int(args.wf_warmup_batches),
            recalibrate_every=int(args.wf_recalibrate_every),
            progress_every_batches=int(args.progress_every_batches),
            verbose=bool(args.inner_verbose),
        )
        weight_method_label = f"split:{breakfree_weight_method}|{dir4_weight_method}"

    method_df, _, _, batch_df = mod._metrics_from_predictions(final_df, seed=int(args.seed))
    if method_df.height != 1:
        raise RuntimeError(
            f"Expected one method row for combo ({mode}, {weight_method_label}, {final_rule}), got {method_df.height}"
        )
    # Per-head diagnostics (separate target ensembling quality before final fusion).
    yb = target_df["truth_breakfree"].to_numpy().astype(np.int16)
    pb = target_df["pred_breakfree"].to_numpy().astype(np.int16)
    y4 = target_df["truth_4dir"].to_numpy().astype(np.int16)
    p4 = target_df["pred_4dir"].to_numpy().astype(np.int16)

    b_metrics = mod._compute_standard_metrics(yb, pb)
    b_covered = pb != mod.NO_SIGNAL
    b_dir_truth = (yb == mod.UP) | (yb == mod.DOWN)
    b_dir_active = b_dir_truth & ((pb == mod.UP) | (pb == mod.DOWN))
    b_dir_acc_active = (
        float(np.mean(pb[b_dir_active] == yb[b_dir_active])) if np.any(b_dir_active) else 0.0
    )

    d_covered = p4 != mod.NO_SIGNAL
    d_acc_cov = float(np.mean(p4[d_covered] == y4[d_covered])) if np.any(d_covered) else 0.0
    d_bal = mod._compute_standard_metrics(y4[d_covered], p4[d_covered]) if np.any(d_covered) else {
        "accuracy_covered": 0.0,
        "coverage": 0.0,
        "precision_up": 0.0,
        "precision_down": 0.0,
        "recall_up": 0.0,
        "recall_down": 0.0,
        "f1_up": 0.0,
        "f1_down": 0.0,
        "macro_f1": 0.0,
        "balanced_accuracy": 0.0,
        "directional_balanced_recall": 0.0,
    }

    head_metrics = {
        "alignment_mode": mode,
        "weight_method": weight_method_label,
        "final_rule": final_rule,
        "breakfree_accuracy_covered": float(b_metrics["accuracy_covered"]),
        "breakfree_macro_f1": float(b_metrics["macro_f1"]),
        "breakfree_balanced_accuracy": float(b_metrics["balanced_accuracy"]),
        "breakfree_directional_balanced_recall": float(b_metrics["directional_balanced_recall"]),
        "breakfree_directional_active_accuracy": float(b_dir_acc_active),
        "breakfree_directional_active_coverage": float(np.mean(b_dir_active)) if b_dir_active.size else 0.0,
        "breakfree_pred_up_count": int(np.sum(pb == mod.UP)),
        "breakfree_pred_down_count": int(np.sum(pb == mod.DOWN)),
        "breakfree_pred_hold_count": int(np.sum(pb == mod.HOLD)),
        "breakfree_pred_nosignal_count": int(np.sum(pb == mod.NO_SIGNAL)),
        "dir4_accuracy_covered": float(d_acc_cov),
        "dir4_macro_f1": float(d_bal["macro_f1"]),
        "dir4_balanced_accuracy": float(d_bal["balanced_accuracy"]),
        "dir4_directional_balanced_recall": float(d_bal["directional_balanced_recall"]),
        "dir4_pred_up_count": int(np.sum(p4 == mod.UP)),
        "dir4_pred_down_count": int(np.sum(p4 == mod.DOWN)),
        "dir4_pred_nosignal_count": int(np.sum(p4 == mod.NO_SIGNAL)),
    }

    method_row = method_df.to_dicts()[0]
    method_row["breakfree_weight_method"] = breakfree_weight_method
    method_row["dir4_weight_method"] = dir4_weight_method
    method_row["weight_method"] = weight_method_label

    batch_rows = batch_df.to_dicts()
    for r in batch_rows:
        r["breakfree_weight_method"] = breakfree_weight_method
        r["dir4_weight_method"] = dir4_weight_method
        r["weight_method"] = weight_method_label

    head_metrics["breakfree_weight_method"] = breakfree_weight_method
    head_metrics["dir4_weight_method"] = dir4_weight_method
    head_metrics["weight_method"] = weight_method_label

    return ComboResult(
        method_row=method_row,
        batch_rows=batch_rows,
        calib_rows=calib,
        selection_rows=[],
        final_predictions=final_df if bool(args.save_combo_predictions) else None,
        head_metrics=head_metrics,
    )


def _run_walkforward_combo_split_methods(
    *,
    mod,
    data,
    selection_schedule: dict[int, tuple[np.ndarray, np.ndarray]],
    breakfree_weight_method: str,
    dir4_weight_method: str,
    final_rule: str,
    tau_grid: np.ndarray,
    ova_threshold_grid: np.ndarray,
    tau_objective: str,
    tau_fp_penalty: float,
    tau_opposite_fp_penalty: float,
    tau_hold_side_penalty: float,
    tau_opposite_active_penalty: float,
    tau_min_active_coverage: float,
    specialist_min_support: int,
    specialist_min_safe_accuracy: float,
    specialist_max_opposite_rate: float,
    specialist_min_votes: int,
    specialist_recency_decay: float,
    kalman_process_noise: float,
    kalman_measurement_noise: float,
    dma_forgetting_factor: float,
    dma_fixed_share_alpha: float,
    ewaf_brier_eta: float,
    warmup_batches: int,
    recalibrate_every: int,
    progress_every_batches: int,
    verbose: bool,
) -> tuple[pl.DataFrame, pl.DataFrame, list[dict[str, Any]]]:
    batch_order = data.batch_order
    if warmup_batches >= len(batch_order):
        raise ValueError(
            f"warmup_batches={warmup_batches} must be < total_batches={len(batch_order)}"
        )

    method_label = f"split:{breakfree_weight_method}|{dir4_weight_method}"
    rows_final: list[dict[str, Any]] = []
    rows_target: list[dict[str, Any]] = []
    calib_logs: list[dict[str, Any]] = []

    current_weights_b = np.zeros(len(data.candidate_ids), dtype=np.float64)
    current_weights_4 = np.zeros(len(data.candidate_ids), dtype=np.float64)
    current_specialist_up = np.zeros(len(data.candidate_ids), dtype=np.float64)
    current_specialist_down = np.zeros(len(data.candidate_ids), dtype=np.float64)
    current_selected_union = np.empty(0, dtype=np.int32)
    current_tau = float(tau_grid[0])
    current_tau_up = float(ova_threshold_grid[0])
    current_tau_down = float(ova_threshold_grid[0])
    last_calib_batch = None
    current_selected_break = np.empty(0, dtype=np.int32)
    current_selected_4dir = np.empty(0, dtype=np.int32)
    wf_t0 = time.perf_counter()
    pred_total = max(int(len(batch_order) - warmup_batches), 1)

    for i, batch in enumerate(batch_order):
        start, end = data.batch_ranges[int(batch)]
        if i < warmup_batches:
            continue

        if int(batch) in selection_schedule:
            current_selected_break, current_selected_4dir = selection_schedule[int(batch)]
            current_selected_union = np.sort(
                np.unique(np.concatenate([current_selected_break, current_selected_4dir]))
            )

        hist_end = start
        should_calib = (i == warmup_batches) or (((i - warmup_batches) % recalibrate_every) == 0)
        pred_idx = int(i - warmup_batches + 1)

        if should_calib:
            current_weights_b = mod._compute_method_weights(
                data=data,
                target_mode=mod.TARGET_BREAKFREE,
                selected_idx=current_selected_break,
                history_end=hist_end,
                method=breakfree_weight_method,
                kalman_process_noise=float(kalman_process_noise),
                kalman_measurement_noise=float(kalman_measurement_noise),
                dma_forgetting_factor=float(dma_forgetting_factor),
                dma_fixed_share_alpha=float(dma_fixed_share_alpha),
                ewaf_brier_eta=float(ewaf_brier_eta),
            )
            current_weights_4 = mod._compute_method_weights(
                data=data,
                target_mode=mod.TARGET_4CLASS,
                selected_idx=current_selected_4dir,
                history_end=hist_end,
                method=dir4_weight_method,
                kalman_process_noise=float(kalman_process_noise),
                kalman_measurement_noise=float(kalman_measurement_noise),
                dma_forgetting_factor=float(dma_forgetting_factor),
                dma_fixed_share_alpha=float(dma_fixed_share_alpha),
                ewaf_brier_eta=float(ewaf_brier_eta),
            )

            if final_rule in {
                "weighted_band",
                "breakfree_gate_weighted",
                "strict_agreement_margin",
                "dual_ova_thresholds",
                "specialist_rare_gate",
            }:
                hb_pred_b, hb_up_b, hb_dn_b, _ = mod._ensemble_target(
                    data=data,
                    anchor_slice=slice(0, hist_end),
                    selected_idx=current_selected_break,
                    base_weights=current_weights_b,
                    target_mode=mod.TARGET_BREAKFREE,
                )
                hb_pred_4, hb_up_4, hb_dn_4, _ = mod._ensemble_target(
                    data=data,
                    anchor_slice=slice(0, hist_end),
                    selected_idx=current_selected_4dir,
                    base_weights=current_weights_4,
                    target_mode=mod.TARGET_4CLASS,
                )
                truth_hist = data.anchors["truth_breakfree"].to_numpy()[:hist_end].astype(np.int16)
                truth_hist_4 = data.anchors["truth_4dir"].to_numpy()[:hist_end].astype(np.int16)
                if final_rule == "dual_ova_thresholds":
                    current_tau_up, current_tau_down = mod._select_dual_thresholds(
                        prob_up_break=hb_up_b,
                        prob_down_break=hb_dn_b,
                        prob_up_4=hb_up_4,
                        prob_down_4=hb_dn_4,
                        pred_break=hb_pred_b,
                        pred_4=hb_pred_4,
                        truth_breakfree=truth_hist,
                        truth_4dir=truth_hist_4,
                        ova_threshold_grid=ova_threshold_grid,
                        tau_objective=tau_objective,
                        tau_fp_penalty=float(tau_fp_penalty),
                        tau_opposite_fp_penalty=float(tau_opposite_fp_penalty),
                        tau_hold_side_penalty=float(tau_hold_side_penalty),
                        tau_opposite_active_penalty=float(tau_opposite_active_penalty),
                        tau_min_active_coverage=float(tau_min_active_coverage),
                    )
                    current_tau = 0.0
                elif final_rule == "specialist_rare_gate":
                    current_specialist_up, current_specialist_down = mod._fit_specialist_quality(
                        data=data,
                        history_end=hist_end,
                        selected_idx=current_selected_union,
                        min_support=int(specialist_min_support),
                        min_safe_accuracy=float(specialist_min_safe_accuracy),
                        max_opposite_rate=float(specialist_max_opposite_rate),
                        recency_decay=float(specialist_recency_decay),
                    )
                    sp_up_hist, sp_down_hist, _, _ = mod._score_specialist_slice(
                        data=data,
                        anchor_slice=slice(0, hist_end),
                        selected_idx=current_selected_union,
                        quality_up=current_specialist_up,
                        quality_down=current_specialist_down,
                        min_votes=int(specialist_min_votes),
                    )
                    current_tau = mod._select_tau(
                        score_break=hb_up_b - hb_dn_b,
                        score_4=hb_up_4 - hb_dn_4,
                        pred_break=hb_pred_b,
                        pred_4=hb_pred_4,
                        truth_breakfree=truth_hist,
                        truth_4dir=truth_hist_4,
                        tau_grid=tau_grid,
                        final_rule=final_rule,
                        tau_objective=tau_objective,
                        tau_fp_penalty=float(tau_fp_penalty),
                        tau_opposite_fp_penalty=float(tau_opposite_fp_penalty),
                        tau_hold_side_penalty=float(tau_hold_side_penalty),
                        tau_opposite_active_penalty=float(tau_opposite_active_penalty),
                        tau_min_active_coverage=float(tau_min_active_coverage),
                        specialist_up=sp_up_hist,
                        specialist_down=sp_down_hist,
                    )
                    current_tau_up = float(current_tau)
                    current_tau_down = float(current_tau)
                else:
                    current_tau = mod._select_tau(
                        score_break=hb_up_b - hb_dn_b,
                        score_4=hb_up_4 - hb_dn_4,
                        pred_break=hb_pred_b,
                        pred_4=hb_pred_4,
                        truth_breakfree=truth_hist,
                        truth_4dir=truth_hist_4,
                        tau_grid=tau_grid,
                        final_rule=final_rule,
                        tau_objective=tau_objective,
                        tau_fp_penalty=float(tau_fp_penalty),
                        tau_opposite_fp_penalty=float(tau_opposite_fp_penalty),
                        tau_hold_side_penalty=float(tau_hold_side_penalty),
                        tau_opposite_active_penalty=float(tau_opposite_active_penalty),
                        tau_min_active_coverage=float(tau_min_active_coverage),
                    )
                    current_tau_up = float(current_tau)
                    current_tau_down = float(current_tau)
            else:
                current_tau = float(tau_grid[0])
                current_tau_up = float(current_tau)
                current_tau_down = float(current_tau)

            last_calib_batch = int(batch)
            calib_logs.append(
                {
                    "alignment_mode": data.mode,
                    "weight_method": method_label,
                    "breakfree_weight_method": breakfree_weight_method,
                    "dir4_weight_method": dir4_weight_method,
                    "final_rule": final_rule,
                    "calib_batch": int(batch),
                    "history_end_anchor": int(hist_end),
                    "history_max_batch": int(batch_order[i - 1]) if i > 0 else None,
                    "tau": float(current_tau),
                    "tau_up": float(current_tau_up),
                    "tau_down": float(current_tau_down),
                    "selected_break_count": int(current_selected_break.size),
                    "selected_4dir_count": int(current_selected_4dir.size),
                    "specialist_active_up_count": int(np.sum(current_specialist_up > 0)),
                    "specialist_active_down_count": int(np.sum(current_specialist_down > 0)),
                }
            )

        pb, ub, db, _ = mod._ensemble_target(
            data=data,
            anchor_slice=slice(start, end),
            selected_idx=current_selected_break,
            base_weights=current_weights_b,
            target_mode=mod.TARGET_BREAKFREE,
        )
        p4, u4, d4, _ = mod._ensemble_target(
            data=data,
            anchor_slice=slice(start, end),
            selected_idx=current_selected_4dir,
            base_weights=current_weights_4,
            target_mode=mod.TARGET_4CLASS,
        )

        score_b = ub - db
        score_4 = u4 - d4

        specialist_up_slice: np.ndarray | None = None
        specialist_down_slice: np.ndarray | None = None
        specialist_up_votes = np.zeros(end - start, dtype=np.int16)
        specialist_down_votes = np.zeros(end - start, dtype=np.int16)
        if final_rule == "specialist_rare_gate":
            specialist_up_slice, specialist_down_slice, specialist_up_votes, specialist_down_votes = mod._score_specialist_slice(
                data=data,
                anchor_slice=slice(start, end),
                selected_idx=current_selected_union,
                quality_up=current_specialist_up,
                quality_down=current_specialist_down,
                min_votes=int(specialist_min_votes),
            )

        final_pred, score_final = mod._compose_final(
            rule=final_rule,
            pred_breakfree=pb,
            pred_4dir=p4,
            score_breakfree=score_b,
            score_4dir=score_4,
            tau=current_tau,
            tau_up=current_tau_up,
            tau_down=current_tau_down,
            prob_up_break=specialist_up_slice if final_rule == "specialist_rare_gate" else ub,
            prob_down_break=specialist_down_slice if final_rule == "specialist_rare_gate" else db,
            prob_up_4=u4,
            prob_down_4=d4,
        )

        truth_b = data.anchors["truth_breakfree"].to_numpy()[start:end].astype(np.int16)
        truth_4 = data.anchors["truth_4dir"].to_numpy()[start:end].astype(np.int16)
        truth4 = mod._compose_truth4_labels(truth_b, truth_4)
        anchor_ts = data.anchors["anchor_15m_ts"].to_list()[start:end]

        for j in range(end - start):
            rows_target.append(
                {
                    "alignment_mode": data.mode,
                    "weight_method": method_label,
                    "breakfree_weight_method": breakfree_weight_method,
                    "dir4_weight_method": dir4_weight_method,
                    "final_rule": final_rule,
                    "pred_batch": int(batch),
                    "anchor_15m_ts": anchor_ts[j],
                    "truth_breakfree": int(truth_b[j]),
                    "truth_4dir": int(truth_4[j]),
                    "pred_breakfree": int(pb[j]),
                    "pred_4dir": int(p4[j]),
                    "score_breakfree": float(score_b[j]) if np.isfinite(score_b[j]) else None,
                    "score_4dir": float(score_4[j]) if np.isfinite(score_4[j]) else None,
                    "tau": float(current_tau),
                    "tau_up": float(current_tau_up),
                    "tau_down": float(current_tau_down),
                    "calib_batch": int(last_calib_batch) if last_calib_batch is not None else None,
                    "selected_break_count": int(current_selected_break.size),
                    "selected_4dir_count": int(current_selected_4dir.size),
                    "specialist_up_votes": int(specialist_up_votes[j]),
                    "specialist_down_votes": int(specialist_down_votes[j]),
                }
            )

            rows_final.append(
                {
                    "alignment_mode": data.mode,
                    "weight_method": method_label,
                    "breakfree_weight_method": breakfree_weight_method,
                    "dir4_weight_method": dir4_weight_method,
                    "final_rule": final_rule,
                    "pred_batch": int(batch),
                    "anchor_15m_ts": anchor_ts[j],
                    "truth_final": int(truth_b[j]),
                    "truth_final4": int(truth4[j]),
                    "truth_breakfree": int(truth_b[j]),
                    "truth_4dir": int(truth_4[j]),
                    "pred_final": int(final_pred[j]),
                    "pred_breakfree": int(pb[j]),
                    "pred_4dir": int(p4[j]),
                    "score_final": float(score_final[j]) if np.isfinite(score_final[j]) else None,
                    "tau": float(current_tau),
                    "tau_up": float(current_tau_up),
                    "tau_down": float(current_tau_down),
                    "calib_batch": int(last_calib_batch) if last_calib_batch is not None else None,
                    "selected_break_count": int(current_selected_break.size),
                    "selected_4dir_count": int(current_selected_4dir.size),
                    "specialist_up_votes": int(specialist_up_votes[j]),
                    "specialist_down_votes": int(specialist_down_votes[j]),
                }
            )

        if verbose and int(progress_every_batches) > 0:
            should_heartbeat = (
                pred_idx == 1
                or pred_idx == pred_total
                or (pred_idx % int(progress_every_batches) == 0)
            )
            if should_heartbeat:
                elapsed = float(time.perf_counter() - wf_t0)
                rate = elapsed / max(pred_idx, 1)
                eta = rate * max(pred_total - pred_idx, 0)
                print(
                    (
                        f"[wf/{data.mode}/{method_label}/{final_rule}] "
                        f"batch={int(batch)} pred_idx={pred_idx}/{pred_total} "
                        f"tau={float(current_tau):.4f} tau_up={float(current_tau_up):.4f} "
                        f"tau_down={float(current_tau_down):.4f} elapsed={elapsed:.1f}s eta={eta:.1f}s"
                    ),
                    flush=True,
                )

    return pl.DataFrame(rows_target), pl.DataFrame(rows_final), calib_logs


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="1m-only cross-target ensemble research harness.")
    p.add_argument("--project-root", type=str, default=".")
    p.add_argument("--ensemble-run-dir", type=str, default="")
    p.add_argument("--output-dir", type=str, default=DEFAULT_OUTPUT_DIR)
    p.add_argument("--output-tag", type=str, default="one_minute_research")
    p.add_argument(
        "--units",
        type=str,
        default=",".join(DEFAULT_UNITS),
        help="Comma-separated unit list; default: 1m/target_breakfree,1m/target_4class",
    )
    p.add_argument(
        "--alignment-mode",
        type=str,
        default="same_period_close",
        choices=["same_period_close", "anchor_mean"],
    )
    p.add_argument(
        "--weight-methods",
        type=str,
        default="winner_history_blend,diversity_weighted,history_acc_ewma,history_brier_ewma,acc_logloss_blend,dma_logscore,ewaf_brier_share",
        help=(
            "Shared method list used for both heads when split lists are not provided."
        ),
    )
    p.add_argument(
        "--breakfree-weight-methods",
        type=str,
        default="",
        help="Optional breakfree-head method list (comma-separated).",
    )
    p.add_argument(
        "--dir4-weight-methods",
        type=str,
        default="",
        help="Optional 4dir-head method list (comma-separated).",
    )
    p.add_argument(
        "--final-rules",
        type=str,
        default="strict_agreement_margin,dual_ova_thresholds",
    )
    p.add_argument("--wf-warmup-batches", type=int, default=120)
    p.add_argument("--wf-recalibrate-every", type=int, default=5)
    p.add_argument(
        "--candidate-selection-mode",
        type=str,
        default="hybrid_staged",
        choices=["hybrid_staged", "all_candidates"],
    )
    p.add_argument("--min-candidates-per-unit", type=int, default=4)
    p.add_argument("--max-prune-iterations", type=int, default=200)
    p.add_argument("--hold-band-grid", type=str, default="0.00:0.20:0.01")
    p.add_argument("--ova-threshold-grid", type=str, default="0.45:0.80:0.02")
    p.add_argument("--tau-objective", type=str, default="risk_aware", choices=["macro_f1", "risk_aware"])
    p.add_argument("--tau-fp-penalty", type=float, default=0.75)
    p.add_argument("--tau-opposite-fp-penalty", type=float, default=1.50)
    p.add_argument("--tau-hold-side-penalty", type=float, default=1.00)
    p.add_argument("--tau-opposite-active-penalty", type=float, default=0.0)
    p.add_argument("--tau-min-active-coverage", type=float, default=0.0)
    p.add_argument("--specialist-min-support", type=int, default=20)
    p.add_argument("--specialist-min-safe-accuracy", type=float, default=0.65)
    p.add_argument("--specialist-max-opposite-rate", type=float, default=0.15)
    p.add_argument("--specialist-min-votes", type=int, default=2)
    p.add_argument("--specialist-recency-decay", type=float, default=0.995)
    p.add_argument("--kalman-process-noise", type=float, default=0.005)
    p.add_argument("--kalman-measurement-noise", type=float, default=0.05)
    p.add_argument("--dma-forgetting-factor", type=float, default=0.995)
    p.add_argument("--dma-fixed-share-alpha", type=float, default=0.01)
    p.add_argument("--ewaf-brier-eta", type=float, default=4.0)
    p.add_argument("--progress-every-batches", type=int, default=100)
    p.add_argument(
        "--inner-verbose",
        action="store_true",
        help="Enable very verbose inner walk-forward calibration/batch logs from core module.",
    )
    p.add_argument("--save-combo-predictions", action="store_true")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--verbose", action="store_true")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    project_root = Path(args.project_root).expanduser().resolve()
    mod = _load_core_module(project_root)

    units = _parse_csv_list(str(args.units))
    if not units:
        raise ValueError("units cannot be empty")
    for unit in units:
        if not unit.startswith("1m/"):
            raise ValueError(f"This harness is 1m-only; invalid unit: {unit}")

    weight_methods = _parse_csv_list(str(args.weight_methods))
    break_methods = _parse_csv_list(str(args.breakfree_weight_methods))
    dir4_methods = _parse_csv_list(str(args.dir4_weight_methods))
    final_rules = _parse_csv_list(str(args.final_rules))
    if not final_rules:
        raise ValueError("weight-methods and final-rules cannot be empty")
    if not break_methods:
        break_methods = weight_methods
    if not dir4_methods:
        dir4_methods = weight_methods
    if not break_methods or not dir4_methods:
        raise ValueError("No head methods resolved")

    ensemble_run_dir = _resolve_ensemble_run_dir(project_root, str(args.ensemble_run_dir), mod)
    unit_rows_path = ensemble_run_dir / "unit_prediction_rows_dedup.parquet"
    candidate_sets_path = ensemble_run_dir / "candidate_sets_by_unit.json"
    if not unit_rows_path.exists() or not candidate_sets_path.exists():
        raise FileNotFoundError("Missing required ensemble inputs")

    now = datetime.now(timezone.utc)
    out_name = now.strftime("%Y%m%d_%H%M%S") + (f"_{args.output_tag}" if args.output_tag else "")
    out_dir = (project_root / str(args.output_dir) / out_name).resolve()
    out_dir.mkdir(parents=True, exist_ok=False)

    _progress("1m-only ensemble research", bool(args.verbose))
    _progress(f"  ensemble_run_dir: {ensemble_run_dir}", bool(args.verbose))
    _progress(f"  output_dir: {out_dir}", bool(args.verbose))
    _progress(f"  units: {units}", bool(args.verbose))
    _progress(f"  breakfree_weight_methods: {break_methods}", bool(args.verbose))
    _progress(f"  dir4_weight_methods: {dir4_methods}", bool(args.verbose))
    _progress(f"  final_rules: {final_rules}", bool(args.verbose))

    unit_rows_all = pl.read_parquet(unit_rows_path)
    candidate_sets = json.loads(candidate_sets_path.read_text(encoding="utf-8"))
    candidate_meta = _build_candidate_meta(candidate_sets, units)
    candidate_set = set(candidate_meta["candidate_id"].to_list())

    # Keep prediction rows only for selected 1m candidates, but keep full rows for truth table.
    unit_rows_pred = (
        unit_rows_all.with_columns(
            pl.concat_str([pl.col("unit"), pl.lit("::"), pl.col("action_key")]).alias("candidate_id")
        ).filter(pl.col("candidate_id").is_in(list(candidate_set)))
    )

    anchor_truth = mod._prepare_truth_table(unit_rows_all)
    mode = str(args.alignment_mode)
    mode_df = mod._build_anchor_candidate_probs(unit_rows_pred, mode)
    mode_df = mode_df.join(
        anchor_truth.select(["pred_batch", "anchor_15m_ts"]),
        on=["pred_batch", "anchor_15m_ts"],
        how="inner",
    )
    mode_df = mode_df.with_columns(
        pl.concat_str([pl.col("unit"), pl.lit("::"), pl.col("action_key")]).alias("candidate_id")
    ).filter(pl.col("candidate_id").is_in(list(candidate_set)))

    data = mod._build_alignment_data(
        aligned_df=mode_df,
        candidate_meta=candidate_meta,
        anchor_truth=anchor_truth,
        mode=mode,
    )
    schedule, selection_logs = _build_selection_schedule(
        data=data,
        mod=mod,
        mode=mode,
        warmup_batches=int(args.wf_warmup_batches),
        recalibrate_every=int(args.wf_recalibrate_every),
        selection_mode=str(args.candidate_selection_mode),
        min_candidates_per_unit=int(args.min_candidates_per_unit),
        max_prune_iterations=int(args.max_prune_iterations),
        verbose=bool(args.verbose),
    )

    all_method_rows: list[dict[str, Any]] = []
    all_batch_rows: list[dict[str, Any]] = []
    all_calib_rows: list[dict[str, Any]] = []
    all_head_rows: list[dict[str, Any]] = []
    combo_summaries: list[dict[str, Any]] = []
    combo_predictions_paths: list[dict[str, Any]] = []

    combos = [(bm, dm, fr) for bm in break_methods for dm in dir4_methods for fr in final_rules]
    combo_total = len(combos)
    t0 = time.perf_counter()
    for idx, (bm, dm, fr) in enumerate(combos, start=1):
        combo_t0 = time.perf_counter()
        _progress(
            f"[combo {idx}/{combo_total}] start break={bm} dir4={dm} rule={fr}",
            bool(args.verbose),
        )
        res = _run_combo(
            mod=mod,
            data=data,
            schedule=schedule,
            mode=mode,
            breakfree_weight_method=bm,
            dir4_weight_method=dm,
            final_rule=fr,
            args=args,
        )
        all_method_rows.append(res.method_row)
        all_batch_rows.extend(res.batch_rows)
        all_calib_rows.extend(res.calib_rows)
        all_head_rows.append(res.head_metrics)

        elapsed_combo = float(time.perf_counter() - combo_t0)
        combo_summaries.append(
            {
                "alignment_mode": mode,
                "breakfree_weight_method": bm,
                "dir4_weight_method": dm,
                "weight_method": f"split:{bm}|{dm}" if bm != dm else bm,
                "final_rule": fr,
                "elapsed_s": elapsed_combo,
                "directional_active_accuracy": float(res.method_row["directional_active_accuracy"]),
                "directional_active_coverage": float(res.method_row["directional_active_coverage"]),
                "opposite_fp_rate_active": float(res.method_row["opposite_fp_rate_active"]),
                "opposite_fp_rate_covered": float(res.method_row["opposite_fp_rate_covered"]),
                "directional_safe_accuracy": float(res.method_row["directional_safe_accuracy"]),
                "custom_mean_cost": float(res.method_row["custom_mean_cost"]),
            }
        )

        if res.final_predictions is not None:
            combo_pred_name = (
                f"final_predictions__break_{bm}__dir4_{dm}__{fr}.parquet"
                .replace("/", "_")
                .replace("|", "_")
            )
            combo_pred_path = out_dir / combo_pred_name
            res.final_predictions.write_parquet(combo_pred_path)
            combo_predictions_paths.append(
                {
                    "breakfree_weight_method": bm,
                    "dir4_weight_method": dm,
                    "weight_method": f"split:{bm}|{dm}" if bm != dm else bm,
                    "final_rule": fr,
                    "path": str(combo_pred_path),
                    "rows": int(res.final_predictions.height),
                }
            )

        elapsed_all = float(time.perf_counter() - t0)
        rate = elapsed_all / max(idx, 1)
        eta = rate * max(combo_total - idx, 0)
        _progress(
            (
                f"[combo {idx}/{combo_total}] done break={bm} dir4={dm} rule={fr} "
                f"dir_acc={float(res.method_row['directional_active_accuracy']):.4f} "
                f"opp_active={float(res.method_row['opposite_fp_rate_active']):.4f} "
                f"coverage={float(res.method_row['directional_active_coverage']):.4f} "
                f"elapsed={elapsed_combo:.1f}s eta={eta:.1f}s"
            ),
            bool(args.verbose),
        )

    method_df = pl.DataFrame(all_method_rows)
    method_df = _rank_method_table(method_df)
    batch_df = pl.DataFrame(all_batch_rows)
    calib_df = pl.DataFrame(all_calib_rows)
    head_df = pl.DataFrame(all_head_rows)
    selection_df = pl.DataFrame(selection_logs)
    combo_df = pl.DataFrame(combo_summaries).sort("directional_active_accuracy", descending=True)

    method_csv = out_dir / "method_comparison_table.csv"
    method_parquet = out_dir / "method_comparison_table.parquet"
    batch_csv = out_dir / "evaluation_by_batch.csv"
    batch_parquet = out_dir / "evaluation_by_batch.parquet"
    calib_csv = out_dir / "calibration_provenance.csv"
    calib_parquet = out_dir / "calibration_provenance.parquet"
    head_csv = out_dir / "target_head_method_comparison.csv"
    head_parquet = out_dir / "target_head_method_comparison.parquet"
    selection_csv = out_dir / "selection_schedule.csv"
    combo_csv = out_dir / "combo_runtime_summary.csv"

    method_df.write_csv(method_csv)
    method_df.write_parquet(method_parquet)
    batch_df.write_csv(batch_csv)
    batch_df.write_parquet(batch_parquet)
    calib_df.write_csv(calib_csv)
    calib_df.write_parquet(calib_parquet)
    head_df.write_csv(head_csv)
    head_df.write_parquet(head_parquet)
    selection_df.write_csv(selection_csv)
    combo_df.write_csv(combo_csv)

    best = method_df.sort("rank_risk").head(1).to_dicts()[0] if not method_df.is_empty() else {}
    summary = {
        "created_utc": now.isoformat(),
        "ensemble_run_dir": str(ensemble_run_dir),
        "units": units,
        "alignment_mode": mode,
        "selection_mode": str(args.candidate_selection_mode),
        "wf_warmup_batches": int(args.wf_warmup_batches),
        "wf_recalibrate_every": int(args.wf_recalibrate_every),
        "breakfree_weight_methods": break_methods,
        "dir4_weight_methods": dir4_methods,
        "final_rules": final_rules,
        "combos_total": int(combo_total),
        "candidate_counts_by_unit": (
            candidate_meta.group_by("unit").len().sort("unit").to_dicts()
        ),
        "best_by_rank_risk": best,
        "artifact_paths": {
            "method_comparison_table_csv": str(method_csv),
            "method_comparison_table_parquet": str(method_parquet),
            "evaluation_by_batch_csv": str(batch_csv),
            "evaluation_by_batch_parquet": str(batch_parquet),
            "calibration_provenance_csv": str(calib_csv),
            "calibration_provenance_parquet": str(calib_parquet),
            "target_head_method_comparison_csv": str(head_csv),
            "target_head_method_comparison_parquet": str(head_parquet),
            "selection_schedule_csv": str(selection_csv),
            "combo_runtime_summary_csv": str(combo_csv),
            "combo_prediction_files": combo_predictions_paths,
        },
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    if bool(args.verbose):
        print("\nBest by risk rank:", flush=True)
        for k in [
            "weight_method",
            "final_rule",
            "directional_active_accuracy",
            "directional_active_coverage",
            "opposite_fp_rate_active",
            "opposite_fp_rate_covered",
            "directional_safe_accuracy",
            "custom_mean_cost",
            "rank_risk",
        ]:
            if k in best:
                print(f"  {k}: {best[k]}", flush=True)
        print(f"\nSaved: {out_dir}", flush=True)


if __name__ == "__main__":
    main()
