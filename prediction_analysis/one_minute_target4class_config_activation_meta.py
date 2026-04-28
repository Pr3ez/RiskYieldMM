#!/usr/bin/env python3
"""Production pipeline for risk-safe directional routing on 1m/target_4class (24 configs).

Phases:
1. Dataset contract + causality guard
2. Per-config activation models with lookback optimization
3. Global router model over (batch, config) rows
4. Threshold operating-point selection under risk/cadence constraints
5. Untouched holdout gate + baseline/context benchmarking
"""

from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
import warnings

try:
    from catboost import CatBoostRanker, Pool as CatBoostPool
except Exception:
    CatBoostRanker = None
    CatBoostPool = None


DEFAULT_UNIT_DIR = "data/htf_backtest_results/stage1_catboost_live/catboost/1m/target_4class"
DEFAULT_OUTPUT_DIR = "prediction_analysis/one_minute_target4class_pattern_outputs"
DEFAULT_STRICT_CONTEXT = (
    "prediction_analysis/multitimeframe_cross_target_outputs/"
    "20260225_203425_full3500_strict_winner_011059_live/summary.json"
)
DEFAULT_DUAL_CONTEXT = (
    "prediction_analysis/multitimeframe_cross_target_outputs/"
    "20260226_011654_full3500_dual_diversity_141257_live/summary.json"
)

DIR_UP = 1
DIR_DOWN = 0
DIR_HOLD = 2
ACTION_KEY_RE = re.compile(r"^f(?P<f>\d+)_v(?P<v>\d+)_t(?P<t>\d+)$")

PER_CONFIG_FEATURE_COLS = [
    "conf_margin_mean",
    "p_dir_max_mean",
    "prob_up_mean",
    "prob_down_mean",
    "pred_up_rate",
    "pred_down_rate",
    "pred_up_centered",
    "conf_margin_rank",
    "p_dir_max_rank",
    "fold_count",
    "val_batches",
    "train_batches",
    "train_val_ratio",
    "train_minus_val",
    "lag_hit_1",
    "lag_dir_acc_1",
    "hit_rate_10",
    "hit_rate_20",
    "dir_acc_mean_10",
    "dir_acc_mean_20",
]

ROUTER_FEATURE_COLS = [
    "p_hit_cfg",
    "p_hit_cfg_rank",
    "p_hit_gap_to_best",
    "conf_margin_mean",
    "p_dir_max_mean",
    "prob_up_mean",
    "prob_down_mean",
    "pred_up_rate",
    "pred_down_rate",
    "pred_up_centered",
    "conf_margin_rank",
    "p_dir_max_rank",
    "fold_count",
    "val_batches",
    "train_batches",
    "train_val_ratio",
    "train_minus_val",
    "agree_with_majority",
    "disagree_with_majority",
    "lag_dir_acc_1",
    "lag_hit_1",
    "dir_acc_roll_25",
    "dir_acc_roll_50",
    "dir_acc_roll_100",
    "hit_roll_25",
    "hit_roll_50",
    "hit_roll_100",
    "dir_acc_drift_25_100",
    "hit_drift_25_100",
    "conf_margin_z",
    "p_dir_max_z",
]

SRSR_BATCH_FEATURE_COLS = [
    "top1_score",
    "topk_score_mean",
    "topk_score_std",
    "topk_score_gap",
    "topk_set_mean",
    "topk_correct_mean",
    "topk_opp_mean",
    "topk_expected_utility",
    "topk_vote_margin",
    "topk_up_share",
    "topk_agree_all",
    "topk_n",
]


@dataclass(frozen=True)
class Inputs:
    project_root: Path
    unit_dir: Path
    output_dir: Path
    output_tag: str
    mode: str
    batches_tail: int
    max_batches: int
    holdout_batches: int
    target_diracc_threshold: float
    lookback_grid: tuple[int, ...]
    router_lookback_grid: tuple[int, ...]
    router_models: tuple[str, ...]
    consensus_k_grid: tuple[int, ...]
    set_recall_k: int
    gate_selection_mode: str
    conformal_delta: float
    conformal_calibration_batches: int
    conformal_class_conditional: bool
    conformal_shift_weighting: str
    conformal_decay_halflife_batches: int
    router_target: str
    router_cost_opposite_penalty: float
    rank_positive_weight: float
    utility_correct_reward: float
    utility_opposite_penalty: float
    selective_hold_cost: float
    safety_margin_opposite_weight: float
    router_shift_weighting: str
    router_shift_halflife_batches: int
    shift_router_retrieval_upgrade: bool
    shift_router_retrieval_blend: float
    shift_router_retrieval_pair_weight: float
    shift_router_retrieval_rank_weight: float
    coverage_regularization_target: float
    coverage_regularization_weight: float
    anti_collapse_min_active_coverage: float
    use_online_policy_pool: bool
    online_policy_eta_grid: tuple[float, ...]
    online_policy_hold_loss_grid: tuple[float, ...]
    online_policy_topn_grid: tuple[int, ...]
    online_policy_warmup_frac: float
    online_policy_min_warmup_batches: int
    retrain_every: int
    router_retrain_every: int
    min_train_rows: int
    objective: str
    activation_threshold: float
    activation_threshold_grid: tuple[float, ...]
    use_directional_thresholds: bool
    directional_threshold_grid: tuple[float, ...]
    target_cadence_min: float
    target_cadence_max: float
    gate_method: str
    rolling_quantile_grid: tuple[float, ...]
    rolling_quantile_lookback: int
    rolling_quantile_min_history: int
    coverage_selection_min: float
    coverage_selection_max: float
    selection_objective: str
    compat_mode: str
    primal_dual_iters: int
    primal_dual_step: float
    primal_dual_utility_mode: str
    max_opposite_fp_active: float
    max_opposite_fp_covered: float
    min_safe_accuracy: float
    strict_context_summary: Path | None
    dual_context_summary: Path | None
    seed: int
    linear_issue_url: str
    notion_page_url: str
    verbose: bool


@dataclass(frozen=True)
class PredictRecord:
    pred_batch: int
    train_max_batch: int
    source: str


def _parse_int_grid(raw: str, name: str, min_v: int = 2) -> tuple[int, ...]:
    vals: list[int] = []
    for token in str(raw).split(","):
        t = token.strip()
        if not t:
            continue
        v = int(t)
        if v < min_v:
            raise ValueError(f"{name} must be >= {min_v}, got {v}")
        vals.append(v)
    if not vals:
        raise ValueError(f"{name} is empty")
    return tuple(sorted(set(vals)))


def _parse_float_grid(raw: str, name: str) -> tuple[float, ...]:
    vals: list[float] = []
    for token in str(raw).split(","):
        t = token.strip()
        if not t:
            continue
        v = float(t)
        if not (0.0 <= v <= 1.0):
            raise ValueError(f"{name} values must be in [0,1], got {v}")
        vals.append(v)
    if not vals:
        raise ValueError(f"{name} is empty")
    return tuple(sorted(set(vals)))


def _parse_positive_float_grid(raw: str, name: str) -> tuple[float, ...]:
    vals: list[float] = []
    for token in str(raw).split(","):
        t = token.strip()
        if not t:
            continue
        v = float(t)
        if v <= 0.0:
            raise ValueError(f"{name} values must be > 0, got {v}")
        vals.append(v)
    if not vals:
        raise ValueError(f"{name} is empty")
    return tuple(sorted(set(vals)))


def _parse_router_models(raw: str) -> tuple[str, ...]:
    allowed = {"logit", "gbm", "catboost_ltr"}
    vals = [x.strip().lower() for x in str(raw).split(",") if x.strip()]
    if not vals:
        raise ValueError("router-models is empty")
    bad = sorted(set(vals) - allowed)
    if bad:
        raise ValueError(f"Unsupported router models: {bad}; allowed={sorted(allowed)}")
    return tuple(dict.fromkeys(vals).keys())


def _utility_neutral_threshold(correct_reward: float, opposite_penalty: float) -> float:
    denom = float(correct_reward + opposite_penalty)
    if denom <= 0.0:
        return 0.5
    return float(opposite_penalty / denom)


def parse_args() -> Inputs:
    p = argparse.ArgumentParser(description="Production routing pipeline for 1m/target_4class (24 configs).")
    p.add_argument("--project-root", type=str, default=".")
    p.add_argument("--unit-dir", type=str, default=DEFAULT_UNIT_DIR)
    p.add_argument("--output-dir", type=str, default=DEFAULT_OUTPUT_DIR)
    p.add_argument("--output-tag", type=str, default="cfg24_risk_safe_prod")

    p.add_argument("--mode", type=str, default="full_pipeline", choices=["per_config", "global_router", "full_pipeline"])

    p.add_argument("--batches-tail", type=int, default=3500)
    p.add_argument("--max-batches", type=int, default=0)
    p.add_argument("--holdout-batches", type=int, default=500)

    p.add_argument("--target-diracc-threshold", type=float, default=0.70)
    p.add_argument("--lookback-grid", type=str, default="32,64,128,256,512")
    p.add_argument("--router-lookback-grid", type=str, default="128,256,512,768")
    p.add_argument("--router-models", type=str, default="logit,gbm")
    p.add_argument("--consensus-k-grid", type=str, default="1")
    p.add_argument("--set-recall-k", type=int, default=5)
    p.add_argument("--gate-selection-mode", type=str, default="empirical", choices=["empirical", "conformal_risk"])
    p.add_argument("--conformal-delta", type=float, default=0.10)
    p.add_argument("--conformal-calibration-batches", type=int, default=500)
    p.add_argument("--conformal-class-conditional", action="store_true")
    p.add_argument("--conformal-shift-weighting", type=str, default="none", choices=["none", "exp_recent"])
    p.add_argument("--conformal-decay-halflife-batches", type=int, default=250)
    p.add_argument(
        "--router-target",
        type=str,
        default="hit",
        choices=[
            "hit",
            "dir_acc",
            "utility",
            "rank_utility",
            "selective_binary",
            "selective_utility",
            "safety_margin",
            "dual_calibrated_utility",
            "shift_reject_utility",
            "dual_head_constrained",
            "pairwise_rank_utility",
            "topk_set_utility",
            "groupwise_ltr_utility",
            "srsr_set_router",
        ],
    )
    p.add_argument("--router-cost-opposite-penalty", type=float, default=0.0)
    p.add_argument("--rank-positive-weight", type=float, default=8.0)
    p.add_argument("--utility-correct-reward", type=float, default=1.0)
    p.add_argument("--utility-opposite-penalty", type=float, default=2.0)
    p.add_argument("--selective-hold-cost", type=float, default=0.10)
    p.add_argument("--safety-margin-opposite-weight", type=float, default=2.0)
    p.add_argument(
        "--router-shift-weighting",
        type=str,
        default="none",
        choices=["none", "exp_recent", "exp_recent_similarity"],
    )
    p.add_argument("--router-shift-halflife-batches", type=int, default=250)
    p.add_argument("--shift-router-retrieval-upgrade", action="store_true")
    p.add_argument("--shift-router-retrieval-blend", type=float, default=0.35)
    p.add_argument("--shift-router-retrieval-pair-weight", type=float, default=0.60)
    p.add_argument("--shift-router-retrieval-rank-weight", type=float, default=0.40)
    p.add_argument("--coverage-regularization-target", type=float, default=0.08)
    p.add_argument("--coverage-regularization-weight", type=float, default=0.0)
    p.add_argument("--anti-collapse-min-active-coverage", type=float, default=0.05)
    p.add_argument("--use-online-policy-pool", action="store_true")
    p.add_argument("--online-policy-eta-grid", type=str, default="0.25,0.50,1.00,2.00")
    p.add_argument("--online-policy-hold-loss-grid", type=str, default="0.05,0.10,0.20")
    p.add_argument("--online-policy-topn-grid", type=str, default="6,12,24")
    p.add_argument("--online-policy-warmup-frac", type=float, default=0.60)
    p.add_argument("--online-policy-min-warmup-batches", type=int, default=120)

    p.add_argument("--retrain-every", type=int, default=25)
    p.add_argument("--router-retrain-every", type=int, default=25)
    p.add_argument("--min-train-rows", type=int, default=64)
    p.add_argument("--objective", type=str, default="brier", choices=["brier", "logloss"])

    # Backward compatibility option.
    p.add_argument("--activation-threshold", type=float, default=0.55)
    p.add_argument("--activation-threshold-grid", type=str, default="0.50,0.55,0.60,0.65,0.70,0.75,0.80,0.85,0.90")
    p.add_argument("--use-directional-thresholds", action="store_true")
    p.add_argument("--directional-threshold-grid", type=str, default="")
    p.add_argument("--gate-method", type=str, default="absolute", choices=["absolute", "rolling_quantile"])
    p.add_argument("--rolling-quantile-grid", type=str, default="0.85,0.88,0.90,0.92,0.95")
    p.add_argument("--rolling-quantile-lookback", type=int, default=300)
    p.add_argument("--rolling-quantile-min-history", type=int, default=80)
    p.add_argument("--coverage-selection-min", type=float, default=-1.0)
    p.add_argument("--coverage-selection-max", type=float, default=-1.0)
    p.add_argument("--selection-objective", type=str, default="default", choices=["default", "primal_dual"])
    p.add_argument("--compat-mode", type=str, default="none", choices=["none", "legacy_safe_first"])
    p.add_argument("--primal-dual-iters", type=int, default=500)
    p.add_argument("--primal-dual-step", type=float, default=0.5)
    p.add_argument("--primal-dual-utility-mode", type=str, default="utility", choices=["utility", "coverage_safe"])

    p.add_argument("--target-cadence-min", type=float, default=10.0)
    p.add_argument("--target-cadence-max", type=float, default=15.0)
    p.add_argument("--max-opposite-fp-active", type=float, default=0.25)
    p.add_argument("--max-opposite-fp-covered", type=float, default=0.03)
    p.add_argument("--min-safe-accuracy", type=float, default=0.70)

    p.add_argument("--strict-context-summary", type=str, default=DEFAULT_STRICT_CONTEXT)
    p.add_argument("--dual-context-summary", type=str, default=DEFAULT_DUAL_CONTEXT)

    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--linear-issue-url", type=str, default="")
    p.add_argument("--notion-page-url", type=str, default="")
    p.add_argument("--verbose", action="store_true")

    a = p.parse_args()

    project_root = Path(a.project_root).expanduser().resolve()
    unit_dir = (project_root / a.unit_dir).resolve()
    output_dir = (project_root / a.output_dir).resolve()

    lookback_grid = _parse_int_grid(a.lookback_grid, "lookback-grid")
    router_lookback_grid = _parse_int_grid(a.router_lookback_grid, "router-lookback-grid")
    router_models = _parse_router_models(a.router_models)
    if "catboost_ltr" in router_models and (CatBoostRanker is None or CatBoostPool is None):
        raise ImportError("catboost is required for --router-models catboost_ltr")
    consensus_k_grid = _parse_int_grid(a.consensus_k_grid, "consensus-k-grid", min_v=1)
    if max(consensus_k_grid) > 24:
        raise ValueError("--consensus-k-grid values cannot exceed 24 for this pipeline")
    if int(a.set_recall_k) < 1 or int(a.set_recall_k) > 24:
        raise ValueError("--set-recall-k must be in [1, 24]")

    threshold_grid = list(_parse_float_grid(a.activation_threshold_grid, "activation-threshold-grid"))
    activation_threshold = float(a.activation_threshold)
    if 0.0 <= activation_threshold <= 1.0 and activation_threshold not in threshold_grid:
        threshold_grid.append(activation_threshold)
    threshold_grid = sorted(set(threshold_grid))
    directional_threshold_grid = (
        list(_parse_float_grid(a.directional_threshold_grid, "directional-threshold-grid"))
        if str(a.directional_threshold_grid).strip()
        else list(threshold_grid)
    )
    if not directional_threshold_grid:
        directional_threshold_grid = list(threshold_grid)
    directional_threshold_grid = sorted(set(float(x) for x in directional_threshold_grid))
    rolling_quantile_grid = list(_parse_float_grid(a.rolling_quantile_grid, "rolling-quantile-grid"))
    online_policy_eta_grid = _parse_positive_float_grid(a.online_policy_eta_grid, "online-policy-eta-grid")
    online_policy_hold_loss_grid = _parse_float_grid(a.online_policy_hold_loss_grid, "online-policy-hold-loss-grid")
    online_policy_topn_grid = _parse_int_grid(a.online_policy_topn_grid, "online-policy-topn-grid", min_v=1)
    if max(online_policy_topn_grid) > 24:
        raise ValueError("--online-policy-topn-grid values cannot exceed 24")

    strict_context = (project_root / a.strict_context_summary).resolve() if str(a.strict_context_summary).strip() else None
    dual_context = (project_root / a.dual_context_summary).resolve() if str(a.dual_context_summary).strip() else None

    if int(a.batches_tail) < 100:
        raise ValueError("--batches-tail must be >= 100")
    if int(a.max_batches) < 0:
        raise ValueError("--max-batches must be >= 0")
    if int(a.holdout_batches) < 0:
        raise ValueError("--holdout-batches must be >= 0")
    if int(a.retrain_every) < 1 or int(a.router_retrain_every) < 1:
        raise ValueError("retrain intervals must be >= 1")
    if float(a.router_cost_opposite_penalty) < 0.0:
        raise ValueError("--router-cost-opposite-penalty must be >= 0")
    if float(a.rank_positive_weight) < 1.0:
        raise ValueError("--rank-positive-weight must be >= 1.0")
    if not (0.0 < float(a.conformal_delta) < 1.0):
        raise ValueError("--conformal-delta must be in (0,1)")
    if int(a.conformal_calibration_batches) < 50:
        raise ValueError("--conformal-calibration-batches must be >= 50")
    if int(a.conformal_decay_halflife_batches) < 20:
        raise ValueError("--conformal-decay-halflife-batches must be >= 20")
    if float(a.utility_correct_reward) <= 0.0:
        raise ValueError("--utility-correct-reward must be > 0")
    if float(a.utility_opposite_penalty) <= 0.0:
        raise ValueError("--utility-opposite-penalty must be > 0")
    if float(a.selective_hold_cost) < 0.0:
        raise ValueError("--selective-hold-cost must be >= 0")
    if float(a.safety_margin_opposite_weight) <= 0.0:
        raise ValueError("--safety-margin-opposite-weight must be > 0")
    if int(a.router_shift_halflife_batches) < 20:
        raise ValueError("--router-shift-halflife-batches must be >= 20")
    if not (0.0 <= float(a.shift_router_retrieval_blend) <= 1.0):
        raise ValueError("--shift-router-retrieval-blend must be in [0,1]")
    if float(a.shift_router_retrieval_pair_weight) < 0.0:
        raise ValueError("--shift-router-retrieval-pair-weight must be >= 0")
    if float(a.shift_router_retrieval_rank_weight) < 0.0:
        raise ValueError("--shift-router-retrieval-rank-weight must be >= 0")
    if float(a.shift_router_retrieval_pair_weight + a.shift_router_retrieval_rank_weight) <= 0.0:
        raise ValueError(
            "--shift-router-retrieval-pair-weight + --shift-router-retrieval-rank-weight must be > 0"
        )
    if str(a.router_target).strip().lower() == "groupwise_ltr_utility" and "catboost_ltr" not in router_models:
        raise ValueError("--router-target groupwise_ltr_utility requires --router-models catboost_ltr")
    if str(a.router_target).strip().lower() != "groupwise_ltr_utility" and "catboost_ltr" in router_models:
        raise ValueError("--router-models catboost_ltr is only supported with --router-target groupwise_ltr_utility")
    if bool(a.shift_router_retrieval_upgrade) and str(a.router_target).strip().lower() != "shift_reject_utility":
        raise ValueError("--shift-router-retrieval-upgrade requires --router-target shift_reject_utility")
    if not (0.0 <= float(a.coverage_regularization_target) <= 1.0):
        raise ValueError("--coverage-regularization-target must be in [0,1]")
    if float(a.coverage_regularization_weight) < 0.0:
        raise ValueError("--coverage-regularization-weight must be >= 0")
    if not (0.0 <= float(a.anti_collapse_min_active_coverage) <= 1.0):
        raise ValueError("--anti-collapse-min-active-coverage must be in [0,1]")
    if str(a.router_target).strip().lower() == "utility":
        neutral = _utility_neutral_threshold(float(a.utility_correct_reward), float(a.utility_opposite_penalty))
        if neutral not in threshold_grid:
            threshold_grid.append(neutral)
            threshold_grid = sorted(set(threshold_grid))
    if int(a.min_train_rows) < 20:
        raise ValueError("--min-train-rows must be >= 20")
    if bool(a.use_online_policy_pool) and bool(a.use_directional_thresholds):
        raise ValueError("--use-online-policy-pool cannot be combined with --use-directional-thresholds in this version")
    if str(a.gate_method).strip().lower() == "rolling_quantile" and bool(a.use_directional_thresholds):
        raise ValueError("--gate-method rolling_quantile cannot be combined with --use-directional-thresholds")
    if bool(a.use_online_policy_pool) and str(a.gate_method).strip().lower() != "absolute":
        raise ValueError("--use-online-policy-pool currently requires --gate-method absolute")
    if not (0.10 <= float(a.online_policy_warmup_frac) <= 0.90):
        raise ValueError("--online-policy-warmup-frac must be in [0.10, 0.90]")
    if int(a.online_policy_min_warmup_batches) < 25:
        raise ValueError("--online-policy-min-warmup-batches must be >= 25")
    if float(a.target_cadence_min) <= 0 or float(a.target_cadence_max) <= 0:
        raise ValueError("cadence bounds must be > 0")
    if float(a.target_cadence_min) > float(a.target_cadence_max):
        raise ValueError("target-cadence-min cannot exceed target-cadence-max")
    if int(a.rolling_quantile_lookback) < 30:
        raise ValueError("--rolling-quantile-lookback must be >= 30")
    if int(a.rolling_quantile_min_history) < 20:
        raise ValueError("--rolling-quantile-min-history must be >= 20")
    if int(a.primal_dual_iters) < 10:
        raise ValueError("--primal-dual-iters must be >= 10")
    if float(a.primal_dual_step) <= 0.0:
        raise ValueError("--primal-dual-step must be > 0")

    cov_sel_min_raw = float(a.coverage_selection_min)
    cov_sel_max_raw = float(a.coverage_selection_max)
    cov_sel_min = cov_sel_min_raw if cov_sel_min_raw >= 0.0 else (1.0 / float(a.target_cadence_max))
    cov_sel_max = cov_sel_max_raw if cov_sel_max_raw >= 0.0 else (1.0 / float(a.target_cadence_min))
    if not (0.0 <= cov_sel_min <= 1.0):
        raise ValueError("--coverage-selection-min must be in [0,1] or -1 for auto")
    if not (0.0 <= cov_sel_max <= 1.0):
        raise ValueError("--coverage-selection-max must be in [0,1] or -1 for auto")
    if cov_sel_min > cov_sel_max:
        raise ValueError("effective coverage selection min cannot exceed max")

    return Inputs(
        project_root=project_root,
        unit_dir=unit_dir,
        output_dir=output_dir,
        output_tag=str(a.output_tag).strip(),
        mode=str(a.mode),
        batches_tail=int(a.batches_tail),
        max_batches=int(a.max_batches),
        holdout_batches=int(a.holdout_batches),
        target_diracc_threshold=float(a.target_diracc_threshold),
        lookback_grid=lookback_grid,
        router_lookback_grid=router_lookback_grid,
        router_models=router_models,
        consensus_k_grid=consensus_k_grid,
        set_recall_k=int(a.set_recall_k),
        gate_selection_mode=str(a.gate_selection_mode).strip().lower(),
        conformal_delta=float(a.conformal_delta),
        conformal_calibration_batches=int(a.conformal_calibration_batches),
        conformal_class_conditional=bool(a.conformal_class_conditional),
        conformal_shift_weighting=str(a.conformal_shift_weighting).strip().lower(),
        conformal_decay_halflife_batches=int(a.conformal_decay_halflife_batches),
        router_target=str(a.router_target).strip().lower(),
        router_cost_opposite_penalty=float(a.router_cost_opposite_penalty),
        rank_positive_weight=float(a.rank_positive_weight),
        utility_correct_reward=float(a.utility_correct_reward),
        utility_opposite_penalty=float(a.utility_opposite_penalty),
        selective_hold_cost=float(a.selective_hold_cost),
        safety_margin_opposite_weight=float(a.safety_margin_opposite_weight),
        router_shift_weighting=str(a.router_shift_weighting).strip().lower(),
        router_shift_halflife_batches=int(a.router_shift_halflife_batches),
        shift_router_retrieval_upgrade=bool(a.shift_router_retrieval_upgrade),
        shift_router_retrieval_blend=float(a.shift_router_retrieval_blend),
        shift_router_retrieval_pair_weight=float(a.shift_router_retrieval_pair_weight),
        shift_router_retrieval_rank_weight=float(a.shift_router_retrieval_rank_weight),
        coverage_regularization_target=float(a.coverage_regularization_target),
        coverage_regularization_weight=float(a.coverage_regularization_weight),
        anti_collapse_min_active_coverage=float(a.anti_collapse_min_active_coverage),
        use_online_policy_pool=bool(a.use_online_policy_pool),
        online_policy_eta_grid=online_policy_eta_grid,
        online_policy_hold_loss_grid=online_policy_hold_loss_grid,
        online_policy_topn_grid=online_policy_topn_grid,
        online_policy_warmup_frac=float(a.online_policy_warmup_frac),
        online_policy_min_warmup_batches=int(a.online_policy_min_warmup_batches),
        retrain_every=int(a.retrain_every),
        router_retrain_every=int(a.router_retrain_every),
        min_train_rows=int(a.min_train_rows),
        objective=str(a.objective),
        activation_threshold=activation_threshold,
        activation_threshold_grid=tuple(threshold_grid),
        use_directional_thresholds=bool(a.use_directional_thresholds),
        directional_threshold_grid=tuple(directional_threshold_grid),
        target_cadence_min=float(a.target_cadence_min),
        target_cadence_max=float(a.target_cadence_max),
        gate_method=str(a.gate_method).strip().lower(),
        rolling_quantile_grid=tuple(sorted(set(float(x) for x in rolling_quantile_grid))),
        rolling_quantile_lookback=int(a.rolling_quantile_lookback),
        rolling_quantile_min_history=int(a.rolling_quantile_min_history),
        coverage_selection_min=float(cov_sel_min),
        coverage_selection_max=float(cov_sel_max),
        selection_objective=str(a.selection_objective).strip().lower(),
        compat_mode=str(a.compat_mode).strip().lower(),
        primal_dual_iters=int(a.primal_dual_iters),
        primal_dual_step=float(a.primal_dual_step),
        primal_dual_utility_mode=str(a.primal_dual_utility_mode).strip().lower(),
        max_opposite_fp_active=float(a.max_opposite_fp_active),
        max_opposite_fp_covered=float(a.max_opposite_fp_covered),
        min_safe_accuracy=float(a.min_safe_accuracy),
        strict_context_summary=strict_context,
        dual_context_summary=dual_context,
        seed=int(a.seed),
        linear_issue_url=str(a.linear_issue_url),
        notion_page_url=str(a.notion_page_url),
        verbose=bool(a.verbose),
    )


def _git_commit_hash(project_root: Path) -> str:
    try:
        out = subprocess.check_output(["git", "-C", str(project_root), "rev-parse", "HEAD"], text=True)
        return out.strip()
    except Exception:
        return ""


def _safe_logloss(y_true: np.ndarray, y_prob: np.ndarray) -> float:
    p = np.clip(y_prob, 1e-8, 1 - 1e-8)
    return float(np.mean(-(y_true * np.log(p) + (1.0 - y_true) * np.log(1.0 - p))))


def _safe_auc(y_true: np.ndarray, y_prob: np.ndarray) -> float:
    if y_true.size == 0 or len(np.unique(y_true)) < 2:
        return float("nan")
    return float(roc_auc_score(y_true, y_prob))


def _parse_action_key(action_key: str) -> tuple[int, int, int] | None:
    m = ACTION_KEY_RE.match(str(action_key))
    if not m:
        return None
    return int(m.group("f")), int(m.group("v")), int(m.group("t"))


def _load_and_aggregate(inp: Inputs) -> tuple[pl.DataFrame, dict[str, Any]]:
    payload_paths = sorted(inp.unit_dir.glob("batch_*/stage1/stage1_pred_batch_predictions.parquet"))
    if not payload_paths:
        raise FileNotFoundError(f"No payload parquet found in {inp.unit_dir}")

    required_cols = {
        "scope",
        "batch_id",
        "action_key",
        "y_true",
        "y_pred",
        "prob_class_0",
        "prob_class_1",
        "prob_class_2",
        "prob_class_3",
    }

    schema = pl.read_parquet(str(payload_paths[0]), n_rows=0).schema
    missing_cols = sorted(required_cols - set(schema.keys()))

    lf = (
        pl.scan_parquet([str(p) for p in payload_paths])
        .filter(pl.col("scope") == "pred_batch")
        .select(
            [
                "batch_id",
                "action_key",
                "y_true",
                "y_pred",
                "prob_class_0",
                "prob_class_1",
                "prob_class_2",
                "prob_class_3",
            ]
        )
    )

    dir_true = pl.col("y_true").is_in([2, 3]).cast(pl.Int8)
    dir_pred = pl.col("y_pred").is_in([2, 3]).cast(pl.Int8)
    p_up = pl.col("prob_class_2") + pl.col("prob_class_3")
    p_down = pl.col("prob_class_0") + pl.col("prob_class_1")

    agg = (
        lf.group_by(["batch_id", "action_key"])
        .agg(
            [
                pl.len().alias("rows"),
                (dir_true == dir_pred).cast(pl.Int32).sum().alias("dir_correct"),
                dir_true.mean().alias("true_up_rate"),
                dir_pred.mean().alias("pred_up_rate"),
                p_up.mean().alias("prob_up_mean"),
                p_down.mean().alias("prob_down_mean"),
                (p_up - p_down).abs().mean().alias("conf_margin_mean"),
                pl.max_horizontal(p_up, p_down).mean().alias("p_dir_max_mean"),
            ]
        )
        .with_columns(
            [
                (pl.col("dir_correct") / pl.col("rows")).alias("dir_acc"),
                (1.0 - pl.col("pred_up_rate")).alias("pred_down_rate"),
            ]
        )
        .sort(["batch_id", "action_key"])
        .collect()
    )

    batch_order = agg["batch_id"].unique().sort().to_list()
    batch_monotonic = batch_order == sorted(batch_order)

    # Keep selected tail.
    selected_batches = batch_order[-inp.batches_tail :]
    if inp.max_batches > 0:
        selected_batches = selected_batches[-inp.max_batches :]

    agg = agg.filter(pl.col("batch_id").is_in(selected_batches)).sort(["batch_id", "action_key"])

    # Add static geometry from action_key.
    geom_rows = []
    for ak in agg["action_key"].unique().sort().to_list():
        triplet = _parse_action_key(ak)
        if triplet is None:
            f, v, t = (None, None, None)
            ratio = None
            tv_diff = None
        else:
            f, v, t = triplet
            ratio = (float(t) / float(v)) if v and v > 0 else None
            tv_diff = int(t - v)
        geom_rows.append(
            {
                "action_key": ak,
                "fold_count": f,
                "val_batches": v,
                "train_batches": t,
                "train_val_ratio": ratio,
                "train_minus_val": tv_diff,
            }
        )
    geom = pl.DataFrame(geom_rows)
    agg = agg.join(geom, on="action_key", how="left")

    # Per-batch ranks and majority direction stats.
    agg = agg.with_columns(
        [
            pl.col("conf_margin_mean").rank(method="average", descending=True).over("batch_id").alias("conf_margin_rank"),
            pl.col("p_dir_max_mean").rank(method="average", descending=True).over("batch_id").alias("p_dir_max_rank"),
            pl.col("pred_up_rate").mean().over("batch_id").alias("batch_pred_up_mean"),
        ]
    ).with_columns((pl.col("pred_up_rate") - pl.col("batch_pred_up_mean")).alias("pred_up_centered"))

    # Config-level predicted direction for the batch.
    agg = agg.with_columns(
        pl.when(pl.col("pred_up_rate") > 0.5)
        .then(pl.lit(DIR_UP))
        .when(pl.col("pred_up_rate") < 0.5)
        .then(pl.lit(DIR_DOWN))
        .otherwise(pl.lit(DIR_HOLD))
        .alias("config_pred_dir")
    )

    # Batch-level truth direction by majority row direction.
    batch_truth = (
        agg.group_by("batch_id")
        .agg(pl.col("true_up_rate").mean().alias("truth_up_rate_batch"))
        .with_columns(
            pl.when(pl.col("truth_up_rate_batch") > 0.5)
            .then(pl.lit(DIR_UP))
            .when(pl.col("truth_up_rate_batch") < 0.5)
            .then(pl.lit(DIR_DOWN))
            .otherwise(pl.lit(DIR_HOLD))
            .alias("truth_dir")
        )
    )
    agg = agg.join(batch_truth, on="batch_id", how="left")

    agg = agg.with_columns((pl.col("dir_acc") >= inp.target_diracc_threshold).cast(pl.Int8).alias("hit"))

    # Dataset contract report.
    batch_contract = (
        agg.group_by("batch_id")
        .agg(
            [
                pl.len().alias("cfg_count"),
                pl.min("rows").alias("rows_min"),
                pl.max("rows").alias("rows_max"),
                pl.n_unique("action_key").alias("cfg_unique"),
            ]
        )
        .sort("batch_id")
    )

    bad_cfg = batch_contract.filter((pl.col("cfg_count") != 24) | (pl.col("cfg_unique") != 24))["batch_id"].to_list()
    bad_rows = batch_contract.filter((pl.col("rows_min") != 240) | (pl.col("rows_max") != 240))["batch_id"].to_list()

    action_key_count = agg["action_key"].n_unique()

    contract = {
        "pass": bool(
            len(missing_cols) == 0
            and batch_monotonic
            and len(bad_cfg) == 0
            and len(bad_rows) == 0
            and action_key_count == 24
        ),
        "missing_required_columns": missing_cols,
        "batch_monotonic": bool(batch_monotonic),
        "batch_count": int(len(selected_batches)),
        "batch_id_first": int(min(selected_batches)) if selected_batches else None,
        "batch_id_last": int(max(selected_batches)) if selected_batches else None,
        "config_count_unique": int(action_key_count),
        "bad_cfg_count_batches": [int(x) for x in bad_cfg],
        "bad_row_count_batches": [int(x) for x in bad_rows],
        "required_cfg_per_batch": 24,
        "required_rows_per_batch_config": 240,
        "payload_files": int(len(payload_paths)),
    }

    return agg, contract


def _build_per_config_frame(df: pl.DataFrame, action_key: str) -> pl.DataFrame:
    cdf = df.filter(pl.col("action_key") == action_key).sort("batch_id")
    hits = cdf["hit"].to_numpy().astype(np.float64)
    dir_acc = cdf["dir_acc"].to_numpy().astype(np.float64)

    lag_hit_1 = np.concatenate([[0.5], hits[:-1]])
    lag_dir_acc_1 = np.concatenate([[0.5], dir_acc[:-1]])

    def rolling_mean(arr: np.ndarray, w: int, fallback: float) -> np.ndarray:
        out = np.full(arr.shape[0], fallback, dtype=np.float64)
        csum = np.cumsum(np.insert(arr, 0, 0.0))
        for i in range(arr.size):
            l = max(0, i - w)
            r = i
            n = r - l
            if n > 0:
                out[i] = float((csum[r] - csum[l]) / n)
        return out

    cdf = cdf.with_columns(
        [
            pl.Series("lag_hit_1", lag_hit_1),
            pl.Series("lag_dir_acc_1", lag_dir_acc_1),
            pl.Series("hit_rate_10", rolling_mean(hits, 10, 0.5)),
            pl.Series("hit_rate_20", rolling_mean(hits, 20, 0.5)),
            pl.Series("dir_acc_mean_10", rolling_mean(dir_acc, 10, 0.5)),
            pl.Series("dir_acc_mean_20", rolling_mean(dir_acc, 20, 0.5)),
        ]
    )
    return cdf


def _build_logit(seed: int) -> Pipeline:
    return Pipeline(
        steps=[
            ("scaler", StandardScaler()),
            (
                "clf",
                LogisticRegression(
                    random_state=seed,
                    class_weight="balanced",
                    max_iter=500,
                    solver="lbfgs",
                ),
            ),
        ]
    )


def _fit_model(
    model_name: str,
    X: np.ndarray,
    y: np.ndarray,
    seed: int,
    sample_weight: np.ndarray | None = None,
):
    uniq = np.unique(y)
    if uniq.size < 2:
        prior = float((float(y.sum()) + 1.0) / (float(len(y)) + 2.0))
        return None, prior

    if model_name == "logit":
        model = _build_logit(seed=seed)
    elif model_name == "gbm":
        model = HistGradientBoostingClassifier(
            max_depth=4,
            learning_rate=0.05,
            max_iter=200,
            random_state=seed,
        )
    else:
        raise ValueError(f"Unsupported model: {model_name}")

    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=ConvergenceWarning)
        if model_name == "logit" and sample_weight is not None:
            model.fit(X, y, clf__sample_weight=sample_weight)
        elif sample_weight is not None:
            model.fit(X, y, sample_weight=sample_weight)
        else:
            model.fit(X, y)
    return model, None


def _predict_model(model, prior: float | None, X: np.ndarray) -> np.ndarray:
    if model is None:
        p = float(0.5 if prior is None else prior)
        return np.full(X.shape[0], p, dtype=np.float64)
    if hasattr(model, "predict_proba"):
        return model.predict_proba(X)[:, 1].astype(np.float64)
    # Fallback should not happen for current model set.
    pred = model.predict(X)
    return np.clip(pred.astype(np.float64), 0.0, 1.0)


def _fit_regression_model(
    model_name: str,
    X: np.ndarray,
    y: np.ndarray,
    seed: int,
    sample_weight: np.ndarray | None = None,
):
    if y.size == 0:
        return None, 0.5

    prior = float(np.clip(np.mean(y), 0.0, 1.0))
    if float(np.nanmax(y) - np.nanmin(y)) < 1e-12:
        return None, prior

    if model_name == "logit":
        model = Pipeline(
            steps=[
                ("scaler", StandardScaler()),
                ("reg", Ridge(alpha=1.0)),
            ]
        )
    elif model_name == "gbm":
        model = HistGradientBoostingRegressor(
            max_depth=4,
            learning_rate=0.05,
            max_iter=200,
            random_state=seed,
        )
    else:
        raise ValueError(f"Unsupported model: {model_name}")

    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=ConvergenceWarning)
        if model_name == "logit" and sample_weight is not None:
            model.fit(X, y.astype(np.float64), reg__sample_weight=sample_weight)
        elif sample_weight is not None:
            model.fit(X, y.astype(np.float64), sample_weight=sample_weight)
        else:
            model.fit(X, y.astype(np.float64))
    return model, None


def _predict_regression_model(model, prior: float | None, X: np.ndarray) -> np.ndarray:
    if model is None:
        p = float(0.5 if prior is None else prior)
        return np.full(X.shape[0], p, dtype=np.float64)
    pred = model.predict(X).astype(np.float64)
    return np.clip(pred, 0.0, 1.0)


def _fit_groupwise_ltr_model(
    X: np.ndarray,
    y: np.ndarray,
    group_id: np.ndarray,
    seed: int,
    sample_weight: np.ndarray | None = None,
):
    if CatBoostRanker is None or CatBoostPool is None:
        raise RuntimeError("catboost is not available for groupwise LTR")
    if X.shape[0] == 0:
        return None
    # Need at least two queries and non-degenerate target to train ranking.
    if np.unique(group_id).size < 2:
        return None
    if float(np.nanmax(y) - np.nanmin(y)) < 1e-12:
        return None

    # YetiRankPairwise ignores object-level weights; keep pool unweighted for deterministic behavior.
    pool = CatBoostPool(
        data=X,
        label=y.astype(np.float64),
        group_id=group_id.astype(np.int64),
        weight=None,
    )
    model = CatBoostRanker(
        loss_function="YetiRankPairwise",
        iterations=80,
        learning_rate=0.05,
        depth=4,
        l2_leaf_reg=8.0,
        random_seed=seed,
        verbose=False,
    )
    model.fit(pool)
    return model


def _rank_scores_to_prob(scores: np.ndarray) -> np.ndarray:
    """Map per-batch ranker scores to calibrated-like confidence in [0,1]."""
    s = np.nan_to_num(scores.astype(np.float64), nan=0.0, posinf=0.0, neginf=0.0)
    if s.size == 0:
        return s
    mu = float(np.mean(s))
    sigma = float(np.std(s))
    z = (s - mu) / (sigma + 1e-6)
    p = 1.0 / (1.0 + np.exp(-z))
    return np.clip(p, 0.0, 1.0)


def _normalize_weights(w: np.ndarray | None) -> np.ndarray | None:
    if w is None:
        return None
    arr = np.clip(np.nan_to_num(w.astype(np.float64), nan=1.0, posinf=1.0, neginf=1.0), 1e-6, None)
    mean_v = float(np.mean(arr))
    if mean_v <= 0.0:
        return None
    return arr / mean_v


def _combine_sample_weights(primary: np.ndarray | None, secondary: np.ndarray | None) -> np.ndarray | None:
    if primary is None and secondary is None:
        return None
    if primary is None:
        return _normalize_weights(secondary)
    if secondary is None:
        return _normalize_weights(primary)
    return _normalize_weights(primary * secondary)


def _router_shift_weights(
    hist_df: pl.DataFrame,
    X_hist: np.ndarray,
    feature_cols: list[str],
    mode: str,
    halflife_batches: int,
    cur_df: pl.DataFrame | None = None,
) -> np.ndarray | None:
    if mode == "none" or hist_df.height == 0:
        return None

    batch_hist = hist_df["batch_id"].to_numpy().astype(np.int64)
    max_batch = int(np.max(batch_hist))
    age = (max_batch - batch_hist).astype(np.float64)
    tau = float(halflife_batches) / math.log(2.0)
    w_time = np.exp(-age / max(1e-9, tau))

    if mode == "exp_recent":
        return _normalize_weights(w_time)

    if mode == "exp_recent_similarity":
        if cur_df is None or cur_df.height == 0:
            return _normalize_weights(w_time)
        X_cur = np.nan_to_num(cur_df.select(feature_cols).to_numpy().astype(np.float64), nan=0.0, posinf=0.0, neginf=0.0)
        cur_center = np.mean(X_cur, axis=0)
        scale = np.std(X_hist, axis=0)
        scale = np.where(scale < 1e-6, 1.0, scale)
        z = (X_hist - cur_center.reshape(1, -1)) / scale.reshape(1, -1)
        dist = np.sqrt(np.mean(z * z, axis=1))
        w_sim = np.exp(-dist)
        return _normalize_weights(w_time * w_sim)

    return None


def _fit_platt_scaler(
    p_raw: np.ndarray,
    y_true: np.ndarray,
    seed: int,
) -> tuple[LogisticRegression | None, float]:
    y = y_true.astype(np.int32)
    prior = float((float(y.sum()) + 1.0) / (float(y.size) + 2.0)) if y.size > 0 else 0.5
    if y.size < 20 or np.unique(y).size < 2:
        return None, prior

    p = np.clip(np.nan_to_num(p_raw.astype(np.float64), nan=0.5, posinf=1.0, neginf=0.0), 1e-6, 1.0 - 1e-6)
    x = np.log(p / (1.0 - p)).reshape(-1, 1)

    model = LogisticRegression(
        random_state=seed,
        max_iter=300,
        solver="lbfgs",
    )
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=ConvergenceWarning)
        model.fit(x, y)
    return model, prior


def _apply_platt_scaler(
    model: LogisticRegression | None,
    prior: float | None,
    p_raw: np.ndarray,
) -> np.ndarray:
    p = np.clip(np.nan_to_num(p_raw.astype(np.float64), nan=0.5, posinf=1.0, neginf=0.0), 1e-6, 1.0 - 1e-6)
    if model is None:
        if prior is None:
            return p
        return np.full(p.shape[0], float(prior), dtype=np.float64)
    x = np.log(p / (1.0 - p)).reshape(-1, 1)
    return model.predict_proba(x)[:, 1].astype(np.float64)


def _fit_dual_head_with_calibration(
    model_name: str,
    X_hist: np.ndarray,
    y_hist_correct: np.ndarray,
    y_hist_opp: np.ndarray,
    seed: int,
    min_train_rows: int,
    sample_weight: np.ndarray | None = None,
) -> tuple[
    Any,
    float | None,
    Any,
    float | None,
    LogisticRegression | None,
    float | None,
    LogisticRegression | None,
    float | None,
]:
    n_hist = int(X_hist.shape[0])
    cal_size = max(64, int(round(0.20 * n_hist)))
    can_calibrate = (
        n_hist >= max(128, 2 * int(min_train_rows))
        and cal_size < n_hist
        and (n_hist - cal_size) >= int(min_train_rows)
    )

    if can_calibrate:
        split = n_hist - cal_size
        X_fit = X_hist[:split]
        X_cal = X_hist[split:]
        y_fit_correct = y_hist_correct[:split]
        y_fit_opp = y_hist_opp[:split]
        y_cal_correct = y_hist_correct[split:]
        y_cal_opp = y_hist_opp[split:]
        w_fit = sample_weight[:split] if sample_weight is not None and sample_weight.shape[0] == n_hist else sample_weight
    else:
        X_fit = X_hist
        X_cal = None
        y_fit_correct = y_hist_correct
        y_fit_opp = y_hist_opp
        y_cal_correct = None
        y_cal_opp = None
        w_fit = sample_weight

    model_correct, prior_correct = _fit_model(
        model_name=model_name,
        X=X_fit,
        y=y_fit_correct.astype(np.int32),
        seed=seed,
        sample_weight=w_fit,
    )
    model_opposite, prior_opposite = _fit_model(
        model_name=model_name,
        X=X_fit,
        y=y_fit_opp.astype(np.int32),
        seed=seed + 991,
        sample_weight=w_fit,
    )

    cal_correct_model: LogisticRegression | None = None
    cal_correct_prior: float | None = None
    cal_opp_model: LogisticRegression | None = None
    cal_opp_prior: float | None = None

    if X_cal is not None and y_cal_correct is not None and y_cal_opp is not None:
        p_cal_correct = _predict_model(model_correct, prior_correct, X_cal)
        p_cal_opp = _predict_model(model_opposite, prior_opposite, X_cal)
        cal_correct_model, cal_correct_prior = _fit_platt_scaler(
            p_raw=p_cal_correct,
            y_true=y_cal_correct.astype(np.int32),
            seed=seed + 123,
        )
        cal_opp_model, cal_opp_prior = _fit_platt_scaler(
            p_raw=p_cal_opp,
            y_true=y_cal_opp.astype(np.int32),
            seed=seed + 124,
        )

    return (
        model_correct,
        prior_correct,
        model_opposite,
        prior_opposite,
        cal_correct_model,
        cal_correct_prior,
        cal_opp_model,
        cal_opp_prior,
    )


def _fit_dual_head_constrained_models(
    model_name: str,
    X_hist: np.ndarray,
    hist_df: pl.DataFrame,
    seed: int,
    base_weight: np.ndarray | None,
    rank_positive_weight: float,
    utility_opposite_penalty: float,
    coverage_target: float,
) -> tuple[Any, float | None, Any, float | None, Any, float | None]:
    """Fit rank/accept/opposite heads with risk-sensitive weighting.

    Head outputs:
    - rank: P(this config is the per-batch winner)
    - accept: P(this config should be active)
    - opposite: P(this config is opposite-direction mistake)
    """
    n = int(X_hist.shape[0])
    if n == 0:
        return None, 0.5, None, 0.5, None, 0.5

    y_rank = hist_df["rank_label"].to_numpy().astype(np.int32)
    y_accept = hist_df["selective_binary_label"].to_numpy().astype(np.int32)
    y_opp = hist_df["is_opposite_direction"].to_numpy().astype(np.int32)

    if base_weight is None:
        w_base = np.ones(n, dtype=np.float64)
    else:
        w_base = np.clip(np.nan_to_num(base_weight.astype(np.float64), nan=1.0, posinf=1.0, neginf=1.0), 1e-6, None)

    # Rank head: emphasize true winner rows.
    w_rank = w_base.copy()
    w_rank[y_rank == 1] *= max(1.0, float(rank_positive_weight))

    # Accept head: keep active coverage from collapsing while still downweighting risky rows.
    w_accept = w_base.copy()
    pos_rate = float(np.mean(y_accept)) if y_accept.size else 0.0
    cov_target = float(np.clip(coverage_target, 0.01, 0.60))
    pos_boost = max(1.0, cov_target / max(1e-6, pos_rate))
    w_accept[y_accept == 1] *= pos_boost
    w_accept[y_opp == 1] *= max(2.0, float(1.0 + 2.0 * utility_opposite_penalty))

    # Opposite head: sharpen rare opposite mistakes.
    w_opp = w_base.copy()
    w_opp[y_opp == 1] *= max(2.0, float(1.0 + utility_opposite_penalty))

    rank_model, rank_prior = _fit_model(
        model_name=model_name,
        X=X_hist,
        y=y_rank,
        seed=seed,
        sample_weight=w_rank,
    )
    accept_model, accept_prior = _fit_model(
        model_name=model_name,
        X=X_hist,
        y=y_accept,
        seed=seed + 193,
        sample_weight=w_accept,
    )
    opposite_model, opposite_prior = _fit_model(
        model_name=model_name,
        X=X_hist,
        y=y_opp,
        seed=seed + 991,
        sample_weight=w_opp,
    )
    return rank_model, rank_prior, accept_model, accept_prior, opposite_model, opposite_prior


def _fit_topk_set_utility_heads(
    model_name: str,
    X_hist: np.ndarray,
    hist_df: pl.DataFrame,
    seed: int,
    base_weight: np.ndarray | None,
    rank_positive_weight: float,
    utility_opposite_penalty: float,
) -> tuple[Any, float | None, Any, float | None, Any, float | None]:
    """Fit P0 heads: set-recall + direction utility decomposition.

    Head outputs:
    - set: P(config belongs to top-K utility set in batch)
    - correct: P(config predicts correct directional class)
    - opposite: P(config predicts opposite directional class)
    """
    n = int(X_hist.shape[0])
    if n == 0:
        return None, 0.5, None, 0.5, None, 0.5

    y_set = hist_df["set_recall_label"].to_numpy().astype(np.int32)
    y_correct = hist_df["is_correct_direction"].to_numpy().astype(np.int32)
    y_opp = hist_df["is_opposite_direction"].to_numpy().astype(np.int32)

    if base_weight is None:
        w_base = np.ones(n, dtype=np.float64)
    else:
        w_base = np.clip(np.nan_to_num(base_weight.astype(np.float64), nan=1.0, posinf=1.0, neginf=1.0), 1e-6, None)

    # Set-recall head: push positive set members up, but keep opposite rows expensive.
    w_set = w_base.copy()
    w_set[y_set == 1] *= max(1.0, float(rank_positive_weight))
    w_set[y_opp == 1] *= max(1.0, float(1.0 + utility_opposite_penalty))

    # Correct-direction head: emphasize true directional wins.
    w_correct = w_base.copy()
    w_correct[y_correct == 1] *= max(1.0, float(rank_positive_weight))
    w_correct[y_opp == 1] *= max(1.0, float(1.0 + utility_opposite_penalty))

    # Opposite-direction head: sharpen high-cost mistakes.
    w_opp = w_base.copy()
    w_opp[y_opp == 1] *= max(2.0, float(1.0 + utility_opposite_penalty))

    model_set, prior_set = _fit_model(
        model_name=model_name,
        X=X_hist,
        y=y_set,
        seed=seed,
        sample_weight=w_set,
    )
    model_correct, prior_correct = _fit_model(
        model_name=model_name,
        X=X_hist,
        y=y_correct,
        seed=seed + 193,
        sample_weight=w_correct,
    )
    model_opp, prior_opp = _fit_model(
        model_name=model_name,
        X=X_hist,
        y=y_opp,
        seed=seed + 991,
        sample_weight=w_opp,
    )
    return model_set, prior_set, model_correct, prior_correct, model_opp, prior_opp


def _build_srsr_batch_table(
    batch_id: np.ndarray,
    row_score: np.ndarray,
    p_set: np.ndarray,
    p_correct: np.ndarray,
    p_opp: np.ndarray,
    cfg_dir: np.ndarray,
    topk: int,
    utility_correct_reward: float,
    utility_opposite_penalty: float,
    truth_dir: np.ndarray | None = None,
    set_recall_label: np.ndarray | None = None,
    row_weight: np.ndarray | None = None,
) -> pl.DataFrame:
    """Build batch-level SRSR features from per-config predictions.

    Uses only causal row-level quantities at inference time, and optionally
    attaches supervision labels during training.
    """
    if batch_id.size == 0:
        schema = {c: pl.Float64 for c in SRSR_BATCH_FEATURE_COLS}
        schema.update(
            {
                "batch_id": pl.Int64,
                "batch_weight": pl.Float64,
                "srsr_label_good": pl.Int8,
                "srsr_label_opposite": pl.Int8,
                "srsr_pred_dir": pl.Int8,
            }
        )
        return pl.DataFrame(schema=schema)

    topk_n = int(max(1, topk))
    batches = np.unique(batch_id.astype(np.int64))
    rows: list[dict[str, Any]] = []
    for b in batches:
        idx = np.where(batch_id == b)[0]
        if idx.size == 0:
            continue
        local_score = np.nan_to_num(row_score[idx].astype(np.float64), nan=0.0, posinf=0.0, neginf=0.0)
        order = np.argsort(-local_score, kind="mergesort")
        take = idx[order[: min(topk_n, idx.size)]]
        s = np.nan_to_num(row_score[take].astype(np.float64), nan=0.0, posinf=0.0, neginf=0.0)
        p_s = np.nan_to_num(p_set[take].astype(np.float64), nan=0.5, posinf=1.0, neginf=0.0)
        p_c = np.nan_to_num(p_correct[take].astype(np.float64), nan=0.5, posinf=1.0, neginf=0.0)
        p_o = np.nan_to_num(p_opp[take].astype(np.float64), nan=0.5, posinf=1.0, neginf=0.0)
        d = cfg_dir[take].astype(np.int8)

        up_share = float(np.mean(d == DIR_UP)) if d.size > 0 else 0.5
        vote_margin = float(abs(2.0 * up_share - 1.0))
        pred_dir = int(DIR_UP if up_share >= 0.5 else DIR_DOWN)
        agree_all = float(1.0 if np.unique(d).size == 1 else 0.0)

        top1 = float(s[0]) if s.size > 0 else 0.5
        top2 = float(s[1]) if s.size > 1 else top1
        row = {
            "batch_id": int(b),
            "top1_score": top1,
            "topk_score_mean": float(np.mean(s)) if s.size else 0.5,
            "topk_score_std": float(np.std(s)) if s.size else 0.0,
            "topk_score_gap": float(top1 - top2),
            "topk_set_mean": float(np.mean(p_s)) if p_s.size else 0.5,
            "topk_correct_mean": float(np.mean(p_c)) if p_c.size else 0.5,
            "topk_opp_mean": float(np.mean(p_o)) if p_o.size else 0.5,
            "topk_expected_utility": float(
                utility_correct_reward * (float(np.mean(p_c)) if p_c.size else 0.5)
                - utility_opposite_penalty * (float(np.mean(p_o)) if p_o.size else 0.5)
            ),
            "topk_vote_margin": vote_margin,
            "topk_up_share": up_share,
            "topk_agree_all": agree_all,
            "topk_n": float(take.size),
            "batch_weight": float(np.mean(row_weight[idx])) if row_weight is not None else 1.0,
            "srsr_label_good": 0,
            "srsr_label_opposite": 0,
            "srsr_pred_dir": pred_dir,
        }
        if truth_dir is not None:
            td = int(truth_dir[idx[0]])
            has_hit_in_set = bool(np.any(set_recall_label[take] == 1)) if set_recall_label is not None else True
            row["srsr_label_good"] = int(has_hit_in_set and pred_dir == td)
            row["srsr_label_opposite"] = int(pred_dir != td)
        rows.append(row)

    if not rows:
        return pl.DataFrame(
            schema={
                "batch_id": pl.Int64,
                **{c: pl.Float64 for c in SRSR_BATCH_FEATURE_COLS},
                "batch_weight": pl.Float64,
                "srsr_label_good": pl.Int8,
                "srsr_label_opposite": pl.Int8,
                "srsr_pred_dir": pl.Int8,
            }
        )
    return pl.DataFrame(rows).sort("batch_id")


def _fit_srsr_set_heads(
    model_name: str,
    srsr_batch_df: pl.DataFrame,
    seed: int,
    rank_positive_weight: float,
    utility_opposite_penalty: float,
    coverage_target: float,
) -> tuple[Any, float | None, Any, float | None]:
    """Fit set-level utility heads for SRSR."""
    if srsr_batch_df.height == 0:
        return None, 0.5, None, 0.5

    X = np.nan_to_num(srsr_batch_df.select(SRSR_BATCH_FEATURE_COLS).to_numpy().astype(np.float64), nan=0.0, posinf=0.0, neginf=0.0)
    y_good = srsr_batch_df["srsr_label_good"].to_numpy().astype(np.int32)
    y_opp = srsr_batch_df["srsr_label_opposite"].to_numpy().astype(np.int32)
    w_base = np.clip(
        np.nan_to_num(srsr_batch_df["batch_weight"].to_numpy().astype(np.float64), nan=1.0, posinf=1.0, neginf=1.0),
        1e-6,
        None,
    )

    # Good head: favor set-level correctness while preventing coverage collapse.
    w_good = w_base.copy()
    pos_rate = float(np.mean(y_good)) if y_good.size else 0.0
    cov_target = float(np.clip(coverage_target, 0.01, 0.80))
    pos_boost = max(1.0, cov_target / max(1e-6, pos_rate))
    w_good[y_good == 1] *= max(float(rank_positive_weight), pos_boost)
    w_good[y_opp == 1] *= max(1.0, float(1.0 + utility_opposite_penalty))

    # Opposite-risk head: sharpen high-cost wrong-direction detection.
    w_opp = w_base.copy()
    w_opp[y_opp == 1] *= max(2.0, float(1.0 + utility_opposite_penalty))

    model_good, prior_good = _fit_model(
        model_name=model_name,
        X=X,
        y=y_good,
        seed=seed,
        sample_weight=w_good,
    )
    model_opp, prior_opp = _fit_model(
        model_name=model_name,
        X=X,
        y=y_opp,
        seed=seed + 157,
        sample_weight=w_opp,
    )
    return model_good, prior_good, model_opp, prior_opp


def _build_pairwise_winner_rest_dataset(
    hist_df: pl.DataFrame,
    feature_cols: list[str],
    base_weight: np.ndarray | None,
    utility_opposite_penalty: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Build winner-vs-rest pairwise samples for ranking.

    For each batch, pairs the best utility config with all other configs, and adds
    both directions: (winner - loser, y=1) and (loser - winner, y=0).
    """
    if hist_df.height == 0:
        return np.empty((0, len(feature_cols)), dtype=np.float64), np.empty((0,), dtype=np.int32), np.empty((0,), dtype=np.float64)

    x_all = np.nan_to_num(hist_df.select(feature_cols).to_numpy().astype(np.float64), nan=0.0, posinf=0.0, neginf=0.0)
    batch_ids = hist_df["batch_id"].to_numpy().astype(np.int64)
    utility = hist_df["utility_raw"].to_numpy().astype(np.float64)
    rank_label = hist_df["rank_label"].to_numpy().astype(np.int8)
    is_opp = hist_df["is_opposite_direction"].to_numpy().astype(np.int8)
    if base_weight is None:
        w_base = np.ones(hist_df.height, dtype=np.float64)
    else:
        w_base = np.clip(np.nan_to_num(base_weight.astype(np.float64), nan=1.0, posinf=1.0, neginf=1.0), 1e-6, None)

    x_pairs: list[np.ndarray] = []
    y_pairs: list[int] = []
    w_pairs: list[float] = []

    # hist_df is already time sorted before this function is called.
    uniq_batches = np.unique(batch_ids)
    for b in uniq_batches:
        idx = np.where(batch_ids == b)[0]
        if idx.size < 2:
            continue
        # Winner row (rank_label if available, else highest utility).
        winner_local = np.where(rank_label[idx] == 1)[0]
        if winner_local.size > 0:
            i_win = idx[int(winner_local[0])]
        else:
            i_win = idx[int(np.argmax(utility[idx]))]

        x_win = x_all[i_win]
        util_win = float(utility[i_win])
        w_win = float(w_base[i_win])
        for j in idx:
            if int(j) == int(i_win):
                continue
            x_lose = x_all[j]
            margin = max(1e-6, abs(util_win - float(utility[j])))
            w_pair = 0.5 * (w_win + float(w_base[j])) * (1.0 + margin)
            if int(is_opp[j]) == 1:
                w_pair *= max(1.0, float(1.0 + utility_opposite_penalty))

            diff = x_win - x_lose
            x_pairs.append(diff)
            y_pairs.append(1)
            w_pairs.append(w_pair)

            x_pairs.append(-diff)
            y_pairs.append(0)
            w_pairs.append(w_pair)

    if not x_pairs:
        return np.empty((0, len(feature_cols)), dtype=np.float64), np.empty((0,), dtype=np.int32), np.empty((0,), dtype=np.float64)

    return (
        np.vstack(x_pairs).astype(np.float64),
        np.asarray(y_pairs, dtype=np.int32),
        np.asarray(w_pairs, dtype=np.float64),
    )


def _predict_pairwise_batch_scores(
    model: Any,
    prior: float | None,
    x_batch: np.ndarray,
) -> np.ndarray:
    """Estimate per-candidate rank score from pairwise win probabilities."""
    n = int(x_batch.shape[0])
    if n <= 1:
        return np.full((n,), 0.5, dtype=np.float64)
    win_sum = np.zeros(n, dtype=np.float64)
    for i in range(n):
        mask = np.ones(n, dtype=bool)
        mask[i] = False
        diffs = x_batch[i : i + 1] - x_batch[mask]
        p_win = _predict_model(model, prior, diffs)
        win_sum[i] = float(np.mean(p_win))
    return np.clip(win_sum, 0.0, 1.0)


def _fit_shift_router_retrieval_heads(
    model_name: str,
    X_hist: np.ndarray,
    hist_df: pl.DataFrame,
    seed: int,
    base_weight: np.ndarray | None,
    rank_positive_weight: float,
    utility_opposite_penalty: float,
    min_train_rows: int,
) -> tuple[Any, float | None, Any, float | None]:
    """Auxiliary retrieval heads for shift_reject_utility.

    - rank head: winner-vs-rest per-row probability (rank_label)
    - pair head: pairwise winner-rest utility ranking
    """
    n = int(X_hist.shape[0])
    if n == 0:
        return None, 0.5, None, 0.5

    rank_lbl = hist_df["rank_label"].to_numpy().astype(np.int32)
    if base_weight is None:
        w_rank = np.ones(n, dtype=np.float64)
    else:
        w_rank = np.clip(
            np.nan_to_num(base_weight.astype(np.float64), nan=1.0, posinf=1.0, neginf=1.0),
            1e-6,
            None,
        )
    w_rank[rank_lbl == 1] *= max(1.0, float(rank_positive_weight))
    rank_model, rank_prior = _fit_model(
        model_name=model_name,
        X=X_hist,
        y=rank_lbl,
        seed=seed + 401,
        sample_weight=w_rank,
    )

    x_pair, y_pair, w_pair = _build_pairwise_winner_rest_dataset(
        hist_df=hist_df,
        feature_cols=ROUTER_FEATURE_COLS,
        base_weight=base_weight,
        utility_opposite_penalty=utility_opposite_penalty,
    )
    if y_pair.size >= max(64, int(min_train_rows)) and np.unique(y_pair).size >= 2:
        pair_model, pair_prior = _fit_model(
            model_name=model_name,
            X=x_pair,
            y=y_pair,
            seed=seed + 557,
            sample_weight=w_pair,
        )
    else:
        pair_model, pair_prior = None, 0.5
    return rank_model, rank_prior, pair_model, pair_prior


def _blend_shift_router_scores(
    p_base: np.ndarray,
    p_rank: np.ndarray,
    p_pair: np.ndarray,
    retrieval_blend: float,
    pair_weight: float,
    rank_weight: float,
) -> tuple[np.ndarray, np.ndarray]:
    pair_w = max(0.0, float(pair_weight))
    rank_w = max(0.0, float(rank_weight))
    denom = max(1e-9, pair_w + rank_w)
    p_retrieval = np.clip((pair_w * p_pair + rank_w * p_rank) / denom, 0.0, 1.0)
    blend = float(np.clip(retrieval_blend, 0.0, 1.0))
    p_final = np.clip((1.0 - blend) * p_base + blend * p_retrieval, 0.0, 1.0)
    return p_final, p_retrieval


def _router_sample_weight(
    hist_df: pl.DataFrame,
    router_target: str,
    opposite_penalty: float,
    rank_positive_weight: float,
    utility_opposite_penalty: float,
) -> np.ndarray | None:
    if hist_df.height == 0:
        return None

    w = np.ones(hist_df.height, dtype=np.float64)

    pred = hist_df["config_pred_dir"].to_numpy().astype(np.int8)
    truth = hist_df["truth_dir"].to_numpy().astype(np.int8)
    opposite = ((pred == DIR_UP) & (truth == DIR_DOWN)) | ((pred == DIR_DOWN) & (truth == DIR_UP))

    if opposite_penalty > 0.0:
        w[opposite] += float(opposite_penalty)

    if router_target in {"rank_utility", "pairwise_rank_utility"}:
        if "rank_label" in hist_df.columns:
            rank_label = hist_df["rank_label"].to_numpy().astype(np.int8)
            w[rank_label == 1] *= float(rank_positive_weight)
        # Keep opposite-direction mistakes expensive in the ranking objective.
        opp_mult = max(1.0, float(1.0 + utility_opposite_penalty))
        w[opposite] *= opp_mult
    elif router_target in {
        "selective_binary",
        "selective_utility",
        "safety_margin",
        "dual_calibrated_utility",
        "shift_reject_utility",
        "dual_head_constrained",
        "topk_set_utility",
        "srsr_set_router",
    }:
        if "is_correct_direction" in hist_df.columns:
            correct = hist_df["is_correct_direction"].to_numpy().astype(np.int8)
        else:
            correct = np.zeros(hist_df.height, dtype=np.int8)
        neutral = (correct == 0) & (~opposite)
        # Reject-aware emphasis: punish opposite-direction heavily, avoid boosting positives.
        w[opposite] *= max(2.0, float(1.0 + 2.0 * utility_opposite_penalty))
        w[neutral] *= max(1.0, float(1.0 + 0.25 * utility_opposite_penalty))

    if np.allclose(w, 1.0):
        return None
    return w


def _simulate_per_config(
    cdf: pl.DataFrame,
    lookback_batches: int,
    min_train_rows: int,
    retrain_every: int,
    model_name: str,
    seed: int,
) -> tuple[np.ndarray, np.ndarray, dict[str, Any], list[PredictRecord]]:
    feature_cols = PER_CONFIG_FEATURE_COLS

    X = np.nan_to_num(cdf.select(feature_cols).to_numpy().astype(np.float64), nan=0.0, posinf=0.0, neginf=0.0)
    y = cdf["hit"].to_numpy().astype(np.int32)
    batches = cdf["batch_id"].to_numpy().astype(int)

    n = X.shape[0]
    p = np.full(n, np.nan, dtype=np.float64)
    mask = np.zeros(n, dtype=bool)

    model = None
    prior = None
    last_fit_i = -10**9
    fit_count = 0
    fallback_count = 0
    pred_records: list[PredictRecord] = []

    start_i = max(lookback_batches, min_train_rows)
    for i in range(start_i, n):
        hist_l = i - lookback_batches
        hist_r = i
        X_hist = X[hist_l:hist_r]
        y_hist = y[hist_l:hist_r]

        train_max_batch = int(batches[hist_r - 1])
        pred_batch = int(batches[i])

        needs_fit = model is None or (i - last_fit_i) >= retrain_every
        if needs_fit:
            model, prior = _fit_model(model_name=model_name, X=X_hist, y=y_hist, seed=seed)
            last_fit_i = i
            fit_count += 1

        cur = _predict_model(model, prior, X[i : i + 1])
        if model is None:
            fallback_count += 1
        p[i] = float(cur[0])
        mask[i] = True
        pred_records.append(PredictRecord(pred_batch=pred_batch, train_max_batch=train_max_batch, source="per_config"))

    y_eval = y[mask].astype(np.float64)
    p_eval = p[mask]

    if y_eval.size == 0:
        metrics = {
            "rows_scored": 0,
            "brier": float("nan"),
            "logloss": float("nan"),
            "auc": float("nan"),
            "event_rate": float("nan"),
            "fit_count": int(fit_count),
            "fallback_count": int(fallback_count),
        }
    else:
        metrics = {
            "rows_scored": int(y_eval.size),
            "brier": float(np.mean((p_eval - y_eval) ** 2.0)),
            "logloss": _safe_logloss(y_eval, p_eval),
            "auc": _safe_auc(y_eval, p_eval),
            "event_rate": float(np.mean(y_eval)),
            "fit_count": int(fit_count),
            "fallback_count": int(fallback_count),
        }

    return p, mask, metrics, pred_records


def _pick_best(rows: list[dict[str, Any]], objective: str) -> dict[str, Any]:
    def _key(r: dict[str, Any]):
        auc_filled = r["auc"] if np.isfinite(r["auc"]) else -1.0
        if objective == "brier":
            return (r["brier"], r["logloss"], -auc_filled, r["lookback"])
        return (r["logloss"], r["brier"], -auc_filled, r["lookback"])

    return sorted(rows, key=_key)[0]


def _run_per_config_phase(
    df: pl.DataFrame,
    train_batches: list[int],
    holdout_batches: list[int],
    inp: Inputs,
) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame, list[PredictRecord]]:
    train_set = set(int(b) for b in train_batches)

    all_score_rows: list[dict[str, Any]] = []
    chosen_rows: list[dict[str, Any]] = []
    pred_rows: list[dict[str, Any]] = []
    leakage_records: list[PredictRecord] = []

    for idx, action_key in enumerate(df["action_key"].unique().sort().to_list(), start=1):
        cdf = _build_per_config_frame(df, action_key)
        cdf_train = cdf.filter(pl.col("batch_id").is_in(train_batches)).sort("batch_id")

        lookback_rows: list[dict[str, Any]] = []
        lookback_predictions_train: dict[int, np.ndarray] = {}

        for lb in inp.lookback_grid:
            p_train, mask_train, met, recs = _simulate_per_config(
                cdf=cdf_train,
                lookback_batches=int(lb),
                min_train_rows=inp.min_train_rows,
                retrain_every=inp.retrain_every,
                model_name="logit",
                seed=inp.seed,
            )
            leakage_records.extend(recs)

            row = {
                "action_key": action_key,
                "model": "logit",
                "lookback": int(lb),
                **met,
            }
            lookback_rows.append(row)
            all_score_rows.append(row)
            lookback_predictions_train[int(lb)] = p_train

        best = _pick_best(lookback_rows, inp.objective)
        best_lb = int(best["lookback"])

        # Refit once on pre-holdout tail for frozen holdout inference.
        feature_cols = PER_CONFIG_FEATURE_COLS

        cdf_all = cdf.sort("batch_id")
        X_all = np.nan_to_num(cdf_all.select(feature_cols).to_numpy().astype(np.float64), nan=0.0, posinf=0.0, neginf=0.0)
        y_all = cdf_all["hit"].to_numpy().astype(np.int32)
        batches_all = cdf_all["batch_id"].to_numpy().astype(int)
        train_batch_arr = cdf_train["batch_id"].to_numpy().astype(int)
        train_idx_map = {int(b): int(i) for i, b in enumerate(train_batch_arr.tolist())}

        train_idx = np.where(np.isin(batches_all, np.array(train_batches, dtype=int)))[0]
        hold_idx = np.where(np.isin(batches_all, np.array(holdout_batches, dtype=int)))[0]

        hold_pred = np.full(cdf_all.height, np.nan, dtype=np.float64)

        if hold_idx.size > 0 and train_idx.size > 0:
            hist_end = train_idx[-1] + 1
            hist_start = max(0, hist_end - best_lb)
            X_hist = X_all[hist_start:hist_end]
            y_hist = y_all[hist_start:hist_end]
            model, prior = _fit_model("logit", X_hist, y_hist, seed=inp.seed)
            X_hold = X_all[hold_idx]
            hold_probs = _predict_model(model, prior, X_hold)
            hold_pred[hold_idx] = hold_probs

            train_max_batch = int(batches_all[hist_end - 1])
            for hi in hold_idx:
                leakage_records.append(
                    PredictRecord(pred_batch=int(batches_all[hi]), train_max_batch=train_max_batch, source="per_config_holdout")
                )

        p_train_best = lookback_predictions_train[best_lb]
        for i in range(cdf_all.height):
            pb = int(batches_all[i])
            if pb in train_set:
                val = p_train_best[train_idx_map[pb]]
            else:
                val = hold_pred[i]
            pred_rows.append(
                {
                    "batch_id": pb,
                    "action_key": action_key,
                    "p_hit": float(val) if np.isfinite(val) else None,
                    "actual_hit": int(y_all[i]),
                    "actual_dir_acc": float(cdf_all["dir_acc"][i]),
                    "selected_lookback": best_lb,
                    "selected_model": "logit",
                    "config_pred_dir": int(cdf_all["config_pred_dir"][i]),
                    "truth_dir": int(cdf_all["truth_dir"][i]),
                }
            )

        chosen_rows.append(
            {
                "action_key": action_key,
                "selected_model": "logit",
                "selected_lookback": best_lb,
                "selection_objective": inp.objective,
                "selected_brier": float(best["brier"]),
                "selected_logloss": float(best["logloss"]),
                "selected_auc": float(best["auc"]),
                "rows_scored": int(best["rows_scored"]),
                "fit_count": int(best["fit_count"]),
                "fallback_count": int(best["fallback_count"]),
            }
        )

        if inp.verbose and (idx % 4 == 0 or idx == 24):
            print(f"[per_config {idx}/24] {action_key} -> lb={best_lb} brier={best['brier']:.5f}")

    scores_df = pl.DataFrame(all_score_rows).sort(["action_key", "lookback"])
    chosen_df = pl.DataFrame(chosen_rows).sort("action_key")
    pred_schema = {
        "batch_id": pl.Int64,
        "action_key": pl.Utf8,
        "p_hit": pl.Float64,
        "actual_hit": pl.Int8,
        "actual_dir_acc": pl.Float64,
        "selected_lookback": pl.Int64,
        "selected_model": pl.Utf8,
        "config_pred_dir": pl.Int8,
        "truth_dir": pl.Int8,
    }
    pred_df = pl.DataFrame(pred_rows, schema=pred_schema).sort(["batch_id", "action_key"])
    return scores_df, chosen_df, pred_df, leakage_records


def _build_router_table(
    base_df: pl.DataFrame,
    per_cfg_pred: pl.DataFrame,
    utility_correct_reward: float,
    utility_opposite_penalty: float,
    selective_hold_cost: float,
    set_recall_k: int,
) -> pl.DataFrame:
    df = base_df.join(
        per_cfg_pred.select(["batch_id", "action_key", "p_hit"]).rename({"p_hit": "p_hit_cfg"}),
        on=["batch_id", "action_key"],
        how="left",
    )

    batch_major = (
        df.group_by("batch_id")
        .agg(pl.col("config_pred_dir").mode().first().alias("batch_majority_pred_dir"))
        .sort("batch_id")
    )

    df = (
        df.sort(["action_key", "batch_id"])
        .with_columns(
            [
                pl.col("p_hit_cfg").fill_null(0.5).alias("p_hit_cfg"),
                pl.col("p_hit_cfg").rank(method="average", descending=True).over("batch_id").alias("p_hit_cfg_rank"),
                (pl.col("p_hit_cfg").max().over("batch_id") - pl.col("p_hit_cfg")).alias("p_hit_gap_to_best"),
                pl.col("dir_acc").shift(1).over("action_key").fill_null(0.5).alias("lag_dir_acc_1"),
                pl.col("hit").cast(pl.Float64).shift(1).over("action_key").fill_null(0.0).alias("lag_hit_1"),
                pl.col("dir_acc").shift(1).rolling_mean(window_size=25).over("action_key").fill_null(0.5).alias("dir_acc_roll_25"),
                pl.col("dir_acc").shift(1).rolling_mean(window_size=50).over("action_key").fill_null(0.5).alias("dir_acc_roll_50"),
                pl.col("dir_acc").shift(1).rolling_mean(window_size=100).over("action_key").fill_null(0.5).alias("dir_acc_roll_100"),
                pl.col("hit").cast(pl.Float64).shift(1).rolling_mean(window_size=25).over("action_key").fill_null(0.0).alias("hit_roll_25"),
                pl.col("hit").cast(pl.Float64).shift(1).rolling_mean(window_size=50).over("action_key").fill_null(0.0).alias("hit_roll_50"),
                pl.col("hit").cast(pl.Float64).shift(1).rolling_mean(window_size=100).over("action_key").fill_null(0.0).alias("hit_roll_100"),
                pl.col("conf_margin_mean").mean().over("batch_id").alias("batch_conf_margin_mean"),
                pl.col("conf_margin_mean").std().over("batch_id").fill_null(0.0).alias("batch_conf_margin_std"),
                pl.col("p_dir_max_mean").mean().over("batch_id").alias("batch_p_dir_max_mean"),
                pl.col("p_dir_max_mean").std().over("batch_id").fill_null(0.0).alias("batch_p_dir_max_std"),
            ]
        )
        .join(batch_major, on="batch_id", how="left")
        .with_columns(
            [
                (pl.col("config_pred_dir") == pl.col("batch_majority_pred_dir")).cast(pl.Int8).alias("agree_with_majority"),
                (pl.col("config_pred_dir") != pl.col("batch_majority_pred_dir")).cast(pl.Int8).alias("disagree_with_majority"),
                (pl.col("dir_acc_roll_25") - pl.col("dir_acc_roll_100")).alias("dir_acc_drift_25_100"),
                (pl.col("hit_roll_25") - pl.col("hit_roll_100")).alias("hit_drift_25_100"),
                (
                    (pl.col("conf_margin_mean") - pl.col("batch_conf_margin_mean"))
                    / (pl.col("batch_conf_margin_std") + pl.lit(1e-6))
                ).alias("conf_margin_z"),
                (
                    (pl.col("p_dir_max_mean") - pl.col("batch_p_dir_max_mean"))
                    / (pl.col("batch_p_dir_max_std") + pl.lit(1e-6))
                ).alias("p_dir_max_z"),
            ]
        )
        .with_columns(
            [
                (
                    ((pl.col("config_pred_dir") == pl.lit(DIR_UP)) & (pl.col("truth_dir") == pl.lit(DIR_DOWN)))
                    | ((pl.col("config_pred_dir") == pl.lit(DIR_DOWN)) & (pl.col("truth_dir") == pl.lit(DIR_UP)))
                ).cast(pl.Int8).alias("is_opposite_direction"),
                (
                    (pl.col("config_pred_dir") == pl.col("truth_dir"))
                    & pl.col("config_pred_dir").is_in([DIR_UP, DIR_DOWN])
                ).cast(pl.Int8).alias("is_correct_direction"),
            ]
        )
        .with_columns(
            [
                pl.when(pl.col("is_correct_direction") == 1)
                .then(pl.lit(float(utility_correct_reward)))
                .when(pl.col("is_opposite_direction") == 1)
                .then(pl.lit(-float(utility_opposite_penalty)))
                .otherwise(pl.lit(0.0))
                .alias("utility_raw"),
                pl.when(pl.col("is_correct_direction") == 1)
                .then(pl.lit(float(utility_correct_reward)))
                .when(pl.col("is_opposite_direction") == 1)
                .then(pl.lit(-float(utility_opposite_penalty)))
                .otherwise(pl.lit(-float(selective_hold_cost)))
                .alias("selective_utility_raw"),
            ]
        )
        .with_columns(
            (
                (pl.col("utility_raw") + pl.lit(float(utility_opposite_penalty)))
                / pl.lit(float(utility_correct_reward + utility_opposite_penalty))
            )
            .clip(0.0, 1.0)
            .alias("utility_score"),
        )
        .with_columns(
            [
                (
                    (pl.col("selective_utility_raw") + pl.lit(float(utility_opposite_penalty)))
                    / pl.lit(float(utility_correct_reward + utility_opposite_penalty))
                )
                .clip(0.0, 1.0)
                .alias("selective_utility_score"),
                (pl.col("selective_utility_raw") > 0.0).cast(pl.Int8).alias("selective_binary_label"),
            ]
        )
        .drop(["batch_conf_margin_mean", "batch_conf_margin_std", "batch_p_dir_max_mean", "batch_p_dir_max_std"])
    )

    # Phase-A ranking target: one winner per batch based on realized utility (tie-broken by dir_acc, then confidence).
    batch_best = (
        df.group_by("batch_id")
        .agg(
            pl.col("action_key")
            .sort_by(
                [
                    pl.col("utility_raw"),
                    pl.col("dir_acc"),
                    pl.col("p_dir_max_mean"),
                    pl.col("action_key"),
                ],
                descending=[True, True, True, False],
            )
            .first()
            .alias("batch_best_action_key")
        )
        .sort("batch_id")
    )

    df = (
        df.join(batch_best, on="batch_id", how="left")
        .with_columns((pl.col("action_key") == pl.col("batch_best_action_key")).cast(pl.Int8).alias("rank_label"))
        .drop("batch_best_action_key")
    )

    # P0 Top-K set-recall target: positive if config is in per-batch top-K utility set.
    k_set = int(max(1, set_recall_k))
    batch_topk = (
        df.group_by("batch_id")
        .agg(
            pl.col("action_key")
            .sort_by(
                [
                    pl.col("utility_raw"),
                    pl.col("dir_acc"),
                    pl.col("p_dir_max_mean"),
                    pl.col("action_key"),
                ],
                descending=[True, True, True, False],
            )
            .head(k_set)
            .alias("topk_action_key")
        )
        .explode("topk_action_key")
        .rename({"topk_action_key": "action_key"})
        .with_columns(pl.lit(1).cast(pl.Int8).alias("set_recall_label"))
    )
    df = (
        df.join(batch_topk.select(["batch_id", "action_key", "set_recall_label"]), on=["batch_id", "action_key"], how="left")
        .with_columns(pl.col("set_recall_label").fill_null(0).cast(pl.Int8))
    )

    return df.sort(["batch_id", "action_key"])


def _simulate_router_candidate(
    router_df: pl.DataFrame,
    train_batches: list[int],
    model_name: str,
    router_target: str,
    router_cost_opposite_penalty: float,
    rank_positive_weight: float,
    utility_correct_reward: float,
    utility_opposite_penalty: float,
    set_recall_k: int,
    safety_margin_opposite_weight: float,
    router_shift_weighting: str,
    router_shift_halflife_batches: int,
    shift_router_retrieval_upgrade: bool,
    shift_router_retrieval_blend: float,
    shift_router_retrieval_pair_weight: float,
    shift_router_retrieval_rank_weight: float,
    coverage_regularization_target: float,
    lookback_batches: int,
    min_train_rows: int,
    retrain_every: int,
    seed: int,
) -> tuple[pl.DataFrame, dict[str, Any], list[PredictRecord]]:
    feature_cols = ROUTER_FEATURE_COLS
    if router_target == "hit":
        target_col = "hit"
    elif router_target == "rank_utility":
        target_col = "rank_label"
    elif router_target == "pairwise_rank_utility":
        target_col = "rank_label"
    elif router_target == "selective_binary":
        target_col = "selective_binary_label"
    elif router_target == "dir_acc":
        target_col = "dir_acc"
    elif router_target == "selective_utility":
        target_col = "selective_utility_score"
    elif router_target == "shift_reject_utility":
        target_col = "selective_utility_score"
    elif router_target == "dual_head_constrained":
        target_col = "selective_binary_label"
    elif router_target == "topk_set_utility":
        target_col = "set_recall_label"
    elif router_target == "groupwise_ltr_utility":
        target_col = "rank_label"
    elif router_target == "srsr_set_router":
        target_col = "selective_binary_label"
    elif router_target in {"safety_margin", "dual_calibrated_utility"}:
        target_col = "utility_score"
    else:
        target_col = "utility_score"
    is_classifier_target = router_target in {
        "hit",
        "rank_utility",
        "pairwise_rank_utility",
        "selective_binary",
        "dual_head_constrained",
        "topk_set_utility",
        "groupwise_ltr_utility",
        "srsr_set_router",
    }

    train_df = router_df.filter(pl.col("batch_id").is_in(train_batches)).sort(["batch_id", "action_key"])
    all_batches = sorted(train_df["batch_id"].unique().to_list())

    pred_rows: list[dict[str, Any]] = []
    leakage_records: list[PredictRecord] = []

    model = None
    prior = None
    model_opposite = None
    prior_opposite = None
    model_cal_correct = None
    prior_cal_correct = None
    model_cal_opposite = None
    prior_cal_opposite = None
    model_set_good = None
    prior_set_good = None
    model_set_opp = None
    prior_set_opp = None
    model_rank_cls = None
    prior_rank_cls = None
    model_pair = None
    prior_pair = None
    model_retrieval_rank = None
    prior_retrieval_rank = None
    model_retrieval_pair = None
    prior_retrieval_pair = None
    model_retrieval_rank = None
    prior_retrieval_rank = None
    model_retrieval_pair = None
    prior_retrieval_pair = None
    last_fit_pos = -10**9

    row_brier: list[float] = []
    row_logloss: list[float] = []

    for pos, b in enumerate(all_batches):
        if pos < 2:
            continue

        hist_batches = all_batches[max(0, pos - lookback_batches) : pos]
        hist_df = train_df.filter(pl.col("batch_id").is_in(hist_batches))
        cur_df = train_df.filter(pl.col("batch_id") == int(b))

        if hist_df.height < min_train_rows:
            continue

        X_hist = np.nan_to_num(hist_df.select(feature_cols).to_numpy().astype(np.float64), nan=0.0, posinf=0.0, neginf=0.0)
        y_hist = hist_df[target_col].to_numpy()
        w_hist = _router_sample_weight(
            hist_df=hist_df,
            router_target=router_target,
            opposite_penalty=router_cost_opposite_penalty,
            rank_positive_weight=rank_positive_weight,
            utility_opposite_penalty=utility_opposite_penalty,
        )
        w_shift = _router_shift_weights(
            hist_df=hist_df,
            X_hist=X_hist,
            feature_cols=feature_cols,
            mode=router_shift_weighting,
            halflife_batches=router_shift_halflife_batches,
            cur_df=cur_df,
        )
        w_hist_final = _combine_sample_weights(w_hist, w_shift)

        needs_fit = model is None or (pos - last_fit_pos) >= retrain_every
        if needs_fit:
            if router_target == "safety_margin":
                y_hist_correct = hist_df["is_correct_direction"].to_numpy().astype(np.int32)
                y_hist_opp = hist_df["is_opposite_direction"].to_numpy().astype(np.int32)
                model, prior = _fit_model(
                    model_name=model_name,
                    X=X_hist,
                    y=y_hist_correct,
                    seed=seed,
                    sample_weight=w_hist_final,
                )
                model_opposite, prior_opposite = _fit_model(
                    model_name=model_name,
                    X=X_hist,
                    y=y_hist_opp,
                    seed=seed + 991,
                    sample_weight=w_hist_final,
                )
                model_cal_correct = None
                prior_cal_correct = None
                model_cal_opposite = None
                prior_cal_opposite = None
            elif router_target == "dual_calibrated_utility":
                y_hist_correct = hist_df["is_correct_direction"].to_numpy().astype(np.int32)
                y_hist_opp = hist_df["is_opposite_direction"].to_numpy().astype(np.int32)
                (
                    model,
                    prior,
                    model_opposite,
                    prior_opposite,
                    model_cal_correct,
                    prior_cal_correct,
                    model_cal_opposite,
                    prior_cal_opposite,
                ) = _fit_dual_head_with_calibration(
                    model_name=model_name,
                    X_hist=X_hist,
                    y_hist_correct=y_hist_correct,
                    y_hist_opp=y_hist_opp,
                    seed=seed,
                    min_train_rows=min_train_rows,
                    sample_weight=w_hist_final,
                )
            elif router_target == "dual_head_constrained":
                (
                    model,
                    prior,
                    model_cal_correct,
                    prior_cal_correct,
                    model_opposite,
                    prior_opposite,
                ) = _fit_dual_head_constrained_models(
                    model_name=model_name,
                    X_hist=X_hist,
                    hist_df=hist_df,
                    seed=seed,
                    base_weight=w_hist_final,
                    rank_positive_weight=rank_positive_weight,
                    utility_opposite_penalty=utility_opposite_penalty,
                    coverage_target=coverage_regularization_target,
                )
                model_cal_opposite = None
                prior_cal_opposite = None
            elif router_target == "pairwise_rank_utility":
                x_pair, y_pair, w_pair = _build_pairwise_winner_rest_dataset(
                    hist_df=hist_df,
                    feature_cols=feature_cols,
                    base_weight=w_hist_final,
                    utility_opposite_penalty=utility_opposite_penalty,
                )
                if y_pair.size >= max(64, min_train_rows) and np.unique(y_pair).size >= 2:
                    model, prior = _fit_model(
                        model_name=model_name,
                        X=x_pair,
                        y=y_pair,
                        seed=seed,
                        sample_weight=w_pair,
                    )
                else:
                    model, prior = None, 0.5
                model_opposite = None
                prior_opposite = None
                model_cal_correct = None
                prior_cal_correct = None
                model_cal_opposite = None
                prior_cal_opposite = None
            elif router_target == "topk_set_utility":
                (
                    model,
                    prior,
                    model_cal_correct,
                    prior_cal_correct,
                    model_opposite,
                    prior_opposite,
                ) = _fit_topk_set_utility_heads(
                    model_name=model_name,
                    X_hist=X_hist,
                    hist_df=hist_df,
                    seed=seed,
                    base_weight=w_hist_final,
                    rank_positive_weight=rank_positive_weight,
                    utility_opposite_penalty=utility_opposite_penalty,
                )
                model_cal_opposite = None
                prior_cal_opposite = None
                model_set_good = None
                prior_set_good = None
                model_set_opp = None
                prior_set_opp = None
                model_rank_cls = None
                prior_rank_cls = None
                model_pair = None
                prior_pair = None
            elif router_target == "srsr_set_router":
                (
                    model,
                    prior,
                    model_cal_correct,
                    prior_cal_correct,
                    model_opposite,
                    prior_opposite,
                ) = _fit_topk_set_utility_heads(
                    model_name=model_name,
                    X_hist=X_hist,
                    hist_df=hist_df,
                    seed=seed,
                    base_weight=w_hist_final,
                    rank_positive_weight=rank_positive_weight,
                    utility_opposite_penalty=utility_opposite_penalty,
                )
                p_set_hist = _predict_model(model, prior, X_hist)
                p_correct_hist = _predict_model(model_cal_correct, prior_cal_correct, X_hist)
                p_opp_hist = _predict_model(model_opposite, prior_opposite, X_hist)
                util_hist = (
                    float(utility_correct_reward) * p_correct_hist
                    - float(utility_opposite_penalty) * p_opp_hist
                )
                p_util_hist = np.clip(
                    (util_hist + float(utility_opposite_penalty))
                    / max(1e-9, float(utility_correct_reward + utility_opposite_penalty)),
                    0.0,
                    1.0,
                )
                row_score_hist = np.clip(p_set_hist * p_util_hist, 0.0, 1.0)
                srsr_hist_df = _build_srsr_batch_table(
                    batch_id=hist_df["batch_id"].to_numpy().astype(np.int64),
                    row_score=row_score_hist,
                    p_set=p_set_hist,
                    p_correct=p_correct_hist,
                    p_opp=p_opp_hist,
                    cfg_dir=hist_df["config_pred_dir"].to_numpy().astype(np.int8),
                    topk=int(max(1, set_recall_k)),
                    utility_correct_reward=utility_correct_reward,
                    utility_opposite_penalty=utility_opposite_penalty,
                    truth_dir=hist_df["truth_dir"].to_numpy().astype(np.int8),
                    set_recall_label=hist_df["set_recall_label"].to_numpy().astype(np.int8),
                    row_weight=w_hist_final,
                )
                # Use set-level heads as utility gate over the per-config retrieval scores.
                (
                    model_set_good,
                    prior_set_good,
                    model_set_opp,
                    prior_set_opp,
                ) = _fit_srsr_set_heads(
                    model_name=model_name,
                    srsr_batch_df=srsr_hist_df,
                    seed=seed + 313,
                    rank_positive_weight=rank_positive_weight,
                    utility_opposite_penalty=utility_opposite_penalty,
                    coverage_target=coverage_regularization_target,
                )
                rank_lbl = hist_df["rank_label"].to_numpy().astype(np.int32)
                if w_hist_final is None:
                    w_rank_cls = np.ones(hist_df.height, dtype=np.float64)
                else:
                    w_rank_cls = np.clip(
                        np.nan_to_num(w_hist_final.astype(np.float64), nan=1.0, posinf=1.0, neginf=1.0),
                        1e-6,
                        None,
                    )
                w_rank_cls[rank_lbl == 1] *= max(1.0, float(rank_positive_weight))
                model_rank_cls, prior_rank_cls = _fit_model(
                    model_name=model_name,
                    X=X_hist,
                    y=rank_lbl,
                    seed=seed + 401,
                    sample_weight=w_rank_cls,
                )
                x_pair, y_pair, w_pair = _build_pairwise_winner_rest_dataset(
                    hist_df=hist_df,
                    feature_cols=feature_cols,
                    base_weight=w_hist_final,
                    utility_opposite_penalty=utility_opposite_penalty,
                )
                if y_pair.size >= max(64, min_train_rows) and np.unique(y_pair).size >= 2:
                    model_pair, prior_pair = _fit_model(
                        model_name=model_name,
                        X=x_pair,
                        y=y_pair,
                        seed=seed + 557,
                        sample_weight=w_pair,
                    )
                else:
                    model_pair, prior_pair = None, 0.5
                model_cal_opposite = None
                prior_cal_opposite = None
            elif router_target == "shift_reject_utility" and bool(shift_router_retrieval_upgrade):
                model, prior = _fit_regression_model(
                    model_name=model_name,
                    X=X_hist,
                    y=y_hist.astype(np.float64),
                    seed=seed,
                    sample_weight=w_hist_final,
                )
                (
                    model_retrieval_rank,
                    prior_retrieval_rank,
                    model_retrieval_pair,
                    prior_retrieval_pair,
                ) = _fit_shift_router_retrieval_heads(
                    model_name=model_name,
                    X_hist=X_hist,
                    hist_df=hist_df,
                    seed=seed,
                    base_weight=w_hist_final,
                    rank_positive_weight=rank_positive_weight,
                    utility_opposite_penalty=utility_opposite_penalty,
                    min_train_rows=min_train_rows,
                )
                model_opposite = None
                prior_opposite = None
                model_cal_correct = None
                prior_cal_correct = None
                model_cal_opposite = None
                prior_cal_opposite = None
            elif router_target == "groupwise_ltr_utility":
                y_rank_util = hist_df["utility_score"].to_numpy().astype(np.float64)
                g_rank = hist_df["batch_id"].to_numpy().astype(np.int64)
                model = _fit_groupwise_ltr_model(
                    X=X_hist,
                    y=y_rank_util,
                    group_id=g_rank,
                    seed=seed,
                    sample_weight=w_hist_final,
                )
                prior = None
                model_opposite = None
                prior_opposite = None
                model_cal_correct = None
                prior_cal_correct = None
                model_cal_opposite = None
                prior_cal_opposite = None
            elif is_classifier_target:
                model, prior = _fit_model(
                    model_name=model_name,
                    X=X_hist,
                    y=y_hist.astype(np.int32),
                    seed=seed,
                    sample_weight=w_hist_final,
                )
            else:
                model, prior = _fit_regression_model(
                    model_name=model_name,
                    X=X_hist,
                    y=y_hist.astype(np.float64),
                    seed=seed,
                    sample_weight=w_hist_final,
                )
            last_fit_pos = pos

        X_cur = np.nan_to_num(cur_df.select(feature_cols).to_numpy().astype(np.float64), nan=0.0, posinf=0.0, neginf=0.0)
        y_cur = cur_df[target_col].to_numpy()
        if router_target == "safety_margin":
            p_correct_cur = _predict_model(model, prior, X_cur)
            p_opposite_cur = _predict_model(model_opposite, prior_opposite, X_cur)
            score = p_correct_cur - float(safety_margin_opposite_weight) * p_opposite_cur
            p_cur = np.clip((score + float(safety_margin_opposite_weight)) / (1.0 + float(safety_margin_opposite_weight)), 0.0, 1.0)
        elif router_target == "dual_calibrated_utility":
            p_correct_raw = _predict_model(model, prior, X_cur)
            p_opposite_raw = _predict_model(model_opposite, prior_opposite, X_cur)
            p_correct_cur = _apply_platt_scaler(model_cal_correct, prior_cal_correct, p_correct_raw)
            p_opposite_cur = _apply_platt_scaler(model_cal_opposite, prior_cal_opposite, p_opposite_raw)
            utility = (
                float(utility_correct_reward) * p_correct_cur
                - float(utility_opposite_penalty) * p_opposite_cur
            )
            p_cur = np.clip(
                (utility + float(utility_opposite_penalty))
                / max(1e-9, float(utility_correct_reward + utility_opposite_penalty)),
                0.0,
                1.0,
            )
        elif router_target == "dual_head_constrained":
            p_rank_cur = _predict_model(model, prior, X_cur)
            p_accept_cur = _predict_model(model_cal_correct, prior_cal_correct, X_cur)
            p_opposite_cur = _predict_model(model_opposite, prior_opposite, X_cur)
            p_cur = np.clip(p_rank_cur * p_accept_cur * (1.0 - p_opposite_cur), 0.0, 1.0)
        elif router_target == "pairwise_rank_utility":
            p_cur = _predict_pairwise_batch_scores(model=model, prior=prior, x_batch=X_cur)
        elif router_target == "topk_set_utility":
            p_set_cur = _predict_model(model, prior, X_cur)
            p_correct_cur = _predict_model(model_cal_correct, prior_cal_correct, X_cur)
            p_opposite_cur = _predict_model(model_opposite, prior_opposite, X_cur)
            utility_cur = (
                float(utility_correct_reward) * p_correct_cur
                - float(utility_opposite_penalty) * p_opposite_cur
            )
            p_utility_cur = np.clip(
                (utility_cur + float(utility_opposite_penalty))
                / max(1e-9, float(utility_correct_reward + utility_opposite_penalty)),
                0.0,
                1.0,
            )
            p_cur = np.clip(p_set_cur * p_utility_cur, 0.0, 1.0)
        elif router_target == "srsr_set_router":
            p_set_cur = _predict_model(model, prior, X_cur)
            p_correct_cur = _predict_model(model_cal_correct, prior_cal_correct, X_cur)
            p_opposite_cur = _predict_model(model_opposite, prior_opposite, X_cur)
            p_rank_cls_cur = _predict_model(model_rank_cls, prior_rank_cls, X_cur)
            p_pair_cur = _predict_pairwise_batch_scores(model=model_pair, prior=prior_pair, x_batch=X_cur)
            utility_cur = (
                float(utility_correct_reward) * p_correct_cur
                - float(utility_opposite_penalty) * p_opposite_cur
            )
            p_utility_cur = np.clip(
                (utility_cur + float(utility_opposite_penalty))
                / max(1e-9, float(utility_correct_reward + utility_opposite_penalty)),
                0.0,
                1.0,
            )
            retrieval_cur = np.clip(0.55 * p_pair_cur + 0.45 * p_rank_cls_cur, 0.0, 1.0)
            row_score_cur = np.clip(retrieval_cur * p_set_cur * p_utility_cur, 0.0, 1.0)
            srsr_cur_df = _build_srsr_batch_table(
                batch_id=cur_df["batch_id"].to_numpy().astype(np.int64),
                row_score=row_score_cur,
                p_set=p_set_cur,
                p_correct=p_correct_cur,
                p_opp=p_opposite_cur,
                cfg_dir=cur_df["config_pred_dir"].to_numpy().astype(np.int8),
                topk=int(max(1, set_recall_k)),
                utility_correct_reward=utility_correct_reward,
                utility_opposite_penalty=utility_opposite_penalty,
            )
            X_set = np.nan_to_num(
                srsr_cur_df.select(SRSR_BATCH_FEATURE_COLS).to_numpy().astype(np.float64),
                nan=0.0,
                posinf=0.0,
                neginf=0.0,
            )
            p_set_good_cur = _predict_model(model_set_good, prior_set_good, X_set)
            p_set_opp_cur = _predict_model(model_set_opp, prior_set_opp, X_set)
            set_gate = float(np.clip(p_set_good_cur[0] * (1.0 - p_set_opp_cur[0]), 0.0, 1.0))
            p_cur = np.clip(row_score_cur * set_gate, 0.0, 1.0)
        elif router_target == "shift_reject_utility" and bool(shift_router_retrieval_upgrade):
            p_base_cur = _predict_regression_model(model, prior, X_cur)
            p_rank_cur = _predict_model(model_retrieval_rank, prior_retrieval_rank, X_cur)
            p_pair_cur = _predict_pairwise_batch_scores(
                model=model_retrieval_pair,
                prior=prior_retrieval_pair,
                x_batch=X_cur,
            )
            p_cur, _ = _blend_shift_router_scores(
                p_base=p_base_cur,
                p_rank=p_rank_cur,
                p_pair=p_pair_cur,
                retrieval_blend=float(shift_router_retrieval_blend),
                pair_weight=float(shift_router_retrieval_pair_weight),
                rank_weight=float(shift_router_retrieval_rank_weight),
            )
        elif router_target == "groupwise_ltr_utility":
            if model is None:
                p_cur = np.full(X_cur.shape[0], 0.5, dtype=np.float64)
            else:
                s_cur = model.predict(X_cur).astype(np.float64)
                p_cur = _rank_scores_to_prob(s_cur)
        elif is_classifier_target:
            p_cur = _predict_model(model, prior, X_cur)
        else:
            p_cur = _predict_regression_model(model, prior, X_cur)

        # row-wise probabilistic metrics
        row_brier.append(float(np.mean((p_cur - y_cur.astype(float)) ** 2.0)))
        if is_classifier_target:
            row_logloss.append(_safe_logloss(y_cur.astype(float), p_cur))
        else:
            row_logloss.append(float(np.mean(np.abs(p_cur - y_cur.astype(float)))))

        action_keys = cur_df["action_key"].to_list()
        cfg_dirs = cur_df["config_pred_dir"].to_list()
        truth_dirs = cur_df["truth_dir"].to_list()
        hit_vals = cur_df["hit"].to_list()
        rank_vals = cur_df["rank_label"].to_list()
        dir_acc_vals = cur_df["dir_acc"].to_list()
        util_vals = cur_df["utility_score"].to_list()
        sel_bin_vals = cur_df["selective_binary_label"].to_list()
        sel_util_vals = cur_df["selective_utility_score"].to_list()
        set_vals = cur_df["set_recall_label"].to_list()
        if router_target in {"safety_margin", "dual_calibrated_utility"}:
            p_correct_vals = p_correct_cur.tolist()
            p_opp_vals = p_opposite_cur.tolist()
        elif router_target == "dual_head_constrained":
            p_correct_vals = p_accept_cur.tolist()
            p_opp_vals = p_opposite_cur.tolist()
        elif router_target in {"topk_set_utility", "srsr_set_router"}:
            p_correct_vals = p_correct_cur.tolist()
            p_opp_vals = p_opposite_cur.tolist()
        else:
            p_correct_vals = [float("nan")] * cur_df.height
            p_opp_vals = [float("nan")] * cur_df.height

        for i in range(cur_df.height):
            pred_rows.append(
                {
                    "batch_id": int(b),
                    "action_key": str(action_keys[i]),
                    "p_hit_router": float(p_cur[i]),
                    "actual_hit": int(hit_vals[i]),
                    "actual_rank_label": int(rank_vals[i]),
                    "actual_dir_acc": float(dir_acc_vals[i]),
                    "actual_utility_score": float(util_vals[i]),
                    "actual_selective_binary_label": int(sel_bin_vals[i]),
                    "actual_selective_utility_score": float(sel_util_vals[i]),
                    "actual_set_recall_label": int(set_vals[i]),
                    "p_correct_router": float(p_correct_vals[i]),
                    "p_opposite_router": float(p_opp_vals[i]),
                    "config_pred_dir": int(cfg_dirs[i]),
                    "truth_dir": int(truth_dirs[i]),
                    "model": model_name,
                    "lookback": int(lookback_batches),
                }
            )

        train_max_batch = int(max(hist_batches))
        leakage_records.append(PredictRecord(pred_batch=int(b), train_max_batch=train_max_batch, source=f"router_{model_name}"))

    pred_df = pl.DataFrame(pred_rows).sort(["batch_id", "action_key"])

    if pred_df.height > 0:
        if router_target == "hit":
            y_all = pred_df["actual_hit"].to_numpy().astype(float)
        elif router_target == "rank_utility":
            y_all = pred_df["actual_rank_label"].to_numpy().astype(float)
        elif router_target == "pairwise_rank_utility":
            y_all = pred_df["actual_rank_label"].to_numpy().astype(float)
        elif router_target == "selective_binary":
            y_all = pred_df["actual_selective_binary_label"].to_numpy().astype(float)
        elif router_target == "dir_acc":
            y_all = pred_df["actual_dir_acc"].to_numpy().astype(float)
        elif router_target == "selective_utility":
            y_all = pred_df["actual_selective_utility_score"].to_numpy().astype(float)
        elif router_target == "shift_reject_utility":
            y_all = pred_df["actual_selective_utility_score"].to_numpy().astype(float)
        elif router_target == "dual_head_constrained":
            y_all = pred_df["actual_selective_binary_label"].to_numpy().astype(float)
        elif router_target == "topk_set_utility":
            y_all = pred_df["actual_set_recall_label"].to_numpy().astype(float)
        elif router_target == "srsr_set_router":
            y_all = pred_df["actual_selective_binary_label"].to_numpy().astype(float)
        elif router_target == "groupwise_ltr_utility":
            y_all = pred_df["actual_rank_label"].to_numpy().astype(float)
        elif router_target in {"safety_margin", "dual_calibrated_utility"}:
            y_all = pred_df["actual_utility_score"].to_numpy().astype(float)
        else:
            y_all = pred_df["actual_utility_score"].to_numpy().astype(float)
        p_all = pred_df["p_hit_router"].to_numpy().astype(float)
    else:
        y_all = np.array([], dtype=float)
        p_all = np.array([], dtype=float)

    metrics = {
        "model": model_name,
        "router_target": router_target,
        "router_cost_opposite_penalty": float(router_cost_opposite_penalty),
        "utility_correct_reward": float(utility_correct_reward),
        "utility_opposite_penalty": float(utility_opposite_penalty),
        "router_shift_weighting": str(router_shift_weighting),
        "router_shift_halflife_batches": int(router_shift_halflife_batches),
        "shift_router_retrieval_upgrade": bool(shift_router_retrieval_upgrade),
        "shift_router_retrieval_blend": float(shift_router_retrieval_blend),
        "shift_router_retrieval_pair_weight": float(shift_router_retrieval_pair_weight),
        "shift_router_retrieval_rank_weight": float(shift_router_retrieval_rank_weight),
        "lookback": int(lookback_batches),
        "rows_scored": int(pred_df.height),
        "brier": float(np.mean((p_all - y_all) ** 2.0)) if y_all.size > 0 else float("nan"),
        "logloss": (
            _safe_logloss(y_all, p_all)
            if (y_all.size > 0 and is_classifier_target)
            else (float(np.mean(np.abs(p_all - y_all))) if y_all.size > 0 else float("nan"))
        ),
        "auc": _safe_auc(y_all, p_all) if (y_all.size > 0 and is_classifier_target) else float("nan"),
        "batch_count_scored": int(pred_df["batch_id"].n_unique()) if pred_df.height > 0 else 0,
    }
    return pred_df, metrics, leakage_records


def _select_router_candidate(rows: list[dict[str, Any]], objective: str) -> dict[str, Any]:
    def _k(r: dict[str, Any]):
        score = float(
            r.get(
                "selection_score",
                r["brier"] if objective == "brier" else r["logloss"],
            )
        )
        auc_filled = r["auc"] if np.isfinite(r["auc"]) else -1.0
        if objective == "brier":
            return (score, r["brier"], r["logloss"], -auc_filled, r["lookback"], r["model"])
        return (score, r["logloss"], r["brier"], -auc_filled, r["lookback"], r["model"])

    return sorted(rows, key=_k)[0]


def _fit_predict_router_holdout(
    router_df: pl.DataFrame,
    train_batches: list[int],
    holdout_batches: list[int],
    model_name: str,
    router_target: str,
    router_cost_opposite_penalty: float,
    rank_positive_weight: float,
    utility_correct_reward: float,
    utility_opposite_penalty: float,
    set_recall_k: int,
    safety_margin_opposite_weight: float,
    router_shift_weighting: str,
    router_shift_halflife_batches: int,
    shift_router_retrieval_upgrade: bool,
    shift_router_retrieval_blend: float,
    shift_router_retrieval_pair_weight: float,
    shift_router_retrieval_rank_weight: float,
    coverage_regularization_target: float,
    lookback: int,
    min_train_rows: int,
    seed: int,
) -> tuple[pl.DataFrame, list[PredictRecord]]:
    feature_cols = ROUTER_FEATURE_COLS
    if router_target == "hit":
        target_col = "hit"
    elif router_target == "rank_utility":
        target_col = "rank_label"
    elif router_target == "pairwise_rank_utility":
        target_col = "rank_label"
    elif router_target == "selective_binary":
        target_col = "selective_binary_label"
    elif router_target == "dir_acc":
        target_col = "dir_acc"
    elif router_target == "selective_utility":
        target_col = "selective_utility_score"
    elif router_target == "shift_reject_utility":
        target_col = "selective_utility_score"
    elif router_target == "dual_head_constrained":
        target_col = "selective_binary_label"
    elif router_target == "topk_set_utility":
        target_col = "set_recall_label"
    elif router_target == "groupwise_ltr_utility":
        target_col = "rank_label"
    elif router_target == "srsr_set_router":
        target_col = "selective_binary_label"
    elif router_target in {"safety_margin", "dual_calibrated_utility"}:
        target_col = "utility_score"
    else:
        target_col = "utility_score"
    is_classifier_target = router_target in {
        "hit",
        "rank_utility",
        "pairwise_rank_utility",
        "selective_binary",
        "dual_head_constrained",
        "topk_set_utility",
        "groupwise_ltr_utility",
        "srsr_set_router",
    }

    train_df = router_df.filter(pl.col("batch_id").is_in(train_batches)).sort(["batch_id", "action_key"])
    hold_df = router_df.filter(pl.col("batch_id").is_in(holdout_batches)).sort(["batch_id", "action_key"])

    if hold_df.height == 0:
        return pl.DataFrame(
            schema={
                "batch_id": pl.Int64,
                "action_key": pl.Utf8,
                "p_hit_router": pl.Float64,
                "actual_hit": pl.Int8,
                "actual_rank_label": pl.Int8,
                "actual_dir_acc": pl.Float64,
                "actual_utility_score": pl.Float64,
                "actual_selective_binary_label": pl.Int8,
                "actual_selective_utility_score": pl.Float64,
                "actual_set_recall_label": pl.Int8,
                "p_correct_router": pl.Float64,
                "p_opposite_router": pl.Float64,
                "config_pred_dir": pl.Int8,
                "truth_dir": pl.Int8,
                "model": pl.Utf8,
                "lookback": pl.Int64,
            }
        ), []

    batches_sorted = sorted(train_df["batch_id"].unique().to_list())
    if not batches_sorted:
        raise RuntimeError("No training batches available for holdout router fit.")

    # Train final frozen model on tail lookback from pre-holdout history.
    train_tail_batches = batches_sorted[max(0, len(batches_sorted) - lookback) :]
    fit_df = train_df.filter(pl.col("batch_id").is_in(train_tail_batches))
    X_fit = np.nan_to_num(fit_df.select(feature_cols).to_numpy().astype(np.float64), nan=0.0, posinf=0.0, neginf=0.0)
    y_fit = fit_df[target_col].to_numpy()
    w_fit = _router_sample_weight(
        hist_df=fit_df,
        router_target=router_target,
        opposite_penalty=router_cost_opposite_penalty,
        rank_positive_weight=rank_positive_weight,
        utility_opposite_penalty=utility_opposite_penalty,
    )
    last_batch_id = int(max(train_tail_batches))
    cur_df_ref = fit_df.filter(pl.col("batch_id") == last_batch_id)
    w_shift = _router_shift_weights(
        hist_df=fit_df,
        X_hist=X_fit,
        feature_cols=feature_cols,
        mode=router_shift_weighting,
        halflife_batches=router_shift_halflife_batches,
        cur_df=cur_df_ref,
    )
    w_fit_final = _combine_sample_weights(w_fit, w_shift)
    model_set_good = None
    prior_set_good = None
    model_set_opp = None
    prior_set_opp = None
    model_rank_cls = None
    prior_rank_cls = None
    model_pair = None
    prior_pair = None
    if router_target == "safety_margin":
        y_fit_correct = fit_df["is_correct_direction"].to_numpy().astype(np.int32)
        y_fit_opp = fit_df["is_opposite_direction"].to_numpy().astype(np.int32)
        model, prior = _fit_model(
            model_name=model_name,
            X=X_fit,
            y=y_fit_correct,
            seed=seed,
            sample_weight=w_fit_final,
        )
        model_opposite, prior_opposite = _fit_model(
            model_name=model_name,
            X=X_fit,
            y=y_fit_opp,
            seed=seed + 991,
            sample_weight=w_fit_final,
        )
        model_cal_correct = None
        prior_cal_correct = None
        model_cal_opposite = None
        prior_cal_opposite = None
    elif router_target == "dual_calibrated_utility":
        y_fit_correct = fit_df["is_correct_direction"].to_numpy().astype(np.int32)
        y_fit_opp = fit_df["is_opposite_direction"].to_numpy().astype(np.int32)
        (
            model,
            prior,
            model_opposite,
            prior_opposite,
            model_cal_correct,
            prior_cal_correct,
            model_cal_opposite,
            prior_cal_opposite,
        ) = _fit_dual_head_with_calibration(
            model_name=model_name,
            X_hist=X_fit,
            y_hist_correct=y_fit_correct,
            y_hist_opp=y_fit_opp,
            seed=seed,
            min_train_rows=min_train_rows,
            sample_weight=w_fit_final,
        )
    elif router_target == "dual_head_constrained":
        (
            model,
            prior,
            model_cal_correct,
            prior_cal_correct,
            model_opposite,
            prior_opposite,
        ) = _fit_dual_head_constrained_models(
            model_name=model_name,
            X_hist=X_fit,
            hist_df=fit_df,
            seed=seed,
            base_weight=w_fit_final,
            rank_positive_weight=rank_positive_weight,
            utility_opposite_penalty=utility_opposite_penalty,
            coverage_target=coverage_regularization_target,
        )
        model_cal_opposite = None
        prior_cal_opposite = None
    elif router_target == "pairwise_rank_utility":
        x_pair, y_pair, w_pair = _build_pairwise_winner_rest_dataset(
            hist_df=fit_df,
            feature_cols=feature_cols,
            base_weight=w_fit_final,
            utility_opposite_penalty=utility_opposite_penalty,
        )
        if y_pair.size >= max(64, min_train_rows) and np.unique(y_pair).size >= 2:
            model, prior = _fit_model(
                model_name=model_name,
                X=x_pair,
                y=y_pair,
                seed=seed,
                sample_weight=w_pair,
            )
        else:
            model, prior = None, 0.5
        model_opposite, prior_opposite = None, None
        model_cal_correct = None
        prior_cal_correct = None
        model_cal_opposite = None
        prior_cal_opposite = None
    elif router_target == "topk_set_utility":
        (
            model,
            prior,
            model_cal_correct,
            prior_cal_correct,
            model_opposite,
            prior_opposite,
        ) = _fit_topk_set_utility_heads(
            model_name=model_name,
            X_hist=X_fit,
            hist_df=fit_df,
            seed=seed,
            base_weight=w_fit_final,
            rank_positive_weight=rank_positive_weight,
            utility_opposite_penalty=utility_opposite_penalty,
        )
        model_cal_opposite = None
        prior_cal_opposite = None
    elif router_target == "srsr_set_router":
        (
            model,
            prior,
            model_cal_correct,
            prior_cal_correct,
            model_opposite,
            prior_opposite,
        ) = _fit_topk_set_utility_heads(
            model_name=model_name,
            X_hist=X_fit,
            hist_df=fit_df,
            seed=seed,
            base_weight=w_fit_final,
            rank_positive_weight=rank_positive_weight,
            utility_opposite_penalty=utility_opposite_penalty,
        )
        p_set_fit = _predict_model(model, prior, X_fit)
        p_correct_fit = _predict_model(model_cal_correct, prior_cal_correct, X_fit)
        p_opp_fit = _predict_model(model_opposite, prior_opposite, X_fit)
        util_fit = (
            float(utility_correct_reward) * p_correct_fit
            - float(utility_opposite_penalty) * p_opp_fit
        )
        p_util_fit = np.clip(
            (util_fit + float(utility_opposite_penalty))
            / max(1e-9, float(utility_correct_reward + utility_opposite_penalty)),
            0.0,
            1.0,
        )
        row_score_fit = np.clip(p_set_fit * p_util_fit, 0.0, 1.0)
        srsr_fit_df = _build_srsr_batch_table(
            batch_id=fit_df["batch_id"].to_numpy().astype(np.int64),
            row_score=row_score_fit,
            p_set=p_set_fit,
            p_correct=p_correct_fit,
            p_opp=p_opp_fit,
            cfg_dir=fit_df["config_pred_dir"].to_numpy().astype(np.int8),
            topk=int(max(1, set_recall_k)),
            utility_correct_reward=utility_correct_reward,
            utility_opposite_penalty=utility_opposite_penalty,
            truth_dir=fit_df["truth_dir"].to_numpy().astype(np.int8),
            set_recall_label=fit_df["set_recall_label"].to_numpy().astype(np.int8),
            row_weight=w_fit_final,
        )
        (
            model_set_good,
            prior_set_good,
            model_set_opp,
            prior_set_opp,
        ) = _fit_srsr_set_heads(
            model_name=model_name,
            srsr_batch_df=srsr_fit_df,
            seed=seed + 313,
            rank_positive_weight=rank_positive_weight,
            utility_opposite_penalty=utility_opposite_penalty,
            coverage_target=coverage_regularization_target,
        )
        rank_lbl = fit_df["rank_label"].to_numpy().astype(np.int32)
        if w_fit_final is None:
            w_rank_cls = np.ones(fit_df.height, dtype=np.float64)
        else:
            w_rank_cls = np.clip(
                np.nan_to_num(w_fit_final.astype(np.float64), nan=1.0, posinf=1.0, neginf=1.0),
                1e-6,
                None,
            )
        w_rank_cls[rank_lbl == 1] *= max(1.0, float(rank_positive_weight))
        model_rank_cls, prior_rank_cls = _fit_model(
            model_name=model_name,
            X=X_fit,
            y=rank_lbl,
            seed=seed + 401,
            sample_weight=w_rank_cls,
        )
        x_pair, y_pair, w_pair = _build_pairwise_winner_rest_dataset(
            hist_df=fit_df,
            feature_cols=feature_cols,
            base_weight=w_fit_final,
            utility_opposite_penalty=utility_opposite_penalty,
        )
        if y_pair.size >= max(64, min_train_rows) and np.unique(y_pair).size >= 2:
            model_pair, prior_pair = _fit_model(
                model_name=model_name,
                X=x_pair,
                y=y_pair,
                seed=seed + 557,
                sample_weight=w_pair,
            )
        else:
            model_pair, prior_pair = None, 0.5
        model_cal_opposite = None
        prior_cal_opposite = None
    elif router_target == "shift_reject_utility" and bool(shift_router_retrieval_upgrade):
        model, prior = _fit_regression_model(
            model_name=model_name,
            X=X_fit,
            y=y_fit.astype(np.float64),
            seed=seed,
            sample_weight=w_fit_final,
        )
        (
            model_retrieval_rank,
            prior_retrieval_rank,
            model_retrieval_pair,
            prior_retrieval_pair,
        ) = _fit_shift_router_retrieval_heads(
            model_name=model_name,
            X_hist=X_fit,
            hist_df=fit_df,
            seed=seed,
            base_weight=w_fit_final,
            rank_positive_weight=rank_positive_weight,
            utility_opposite_penalty=utility_opposite_penalty,
            min_train_rows=min_train_rows,
        )
        model_opposite, prior_opposite = None, None
        model_cal_correct = None
        prior_cal_correct = None
        model_cal_opposite = None
        prior_cal_opposite = None
    elif router_target == "groupwise_ltr_utility":
        y_rank_util = fit_df["utility_score"].to_numpy().astype(np.float64)
        g_rank = fit_df["batch_id"].to_numpy().astype(np.int64)
        model = _fit_groupwise_ltr_model(
            X=X_fit,
            y=y_rank_util,
            group_id=g_rank,
            seed=seed,
            sample_weight=w_fit_final,
        )
        prior = None
        model_opposite, prior_opposite = None, None
        model_cal_correct = None
        prior_cal_correct = None
        model_cal_opposite = None
        prior_cal_opposite = None
    elif is_classifier_target:
        model, prior = _fit_model(
            model_name=model_name,
            X=X_fit,
            y=y_fit.astype(np.int32),
            seed=seed,
            sample_weight=w_fit_final,
        )
        model_opposite, prior_opposite = None, None
        model_cal_correct = None
        prior_cal_correct = None
        model_cal_opposite = None
        prior_cal_opposite = None
    else:
        model, prior = _fit_regression_model(
            model_name=model_name,
            X=X_fit,
            y=y_fit.astype(np.float64),
            seed=seed,
            sample_weight=w_fit_final,
        )
        model_opposite, prior_opposite = None, None
        model_cal_correct = None
        prior_cal_correct = None
        model_cal_opposite = None
        prior_cal_opposite = None

    X_hold = np.nan_to_num(hold_df.select(feature_cols).to_numpy().astype(np.float64), nan=0.0, posinf=0.0, neginf=0.0)
    if router_target == "safety_margin":
        p_correct_hold = _predict_model(model, prior, X_hold)
        p_opposite_hold = _predict_model(model_opposite, prior_opposite, X_hold)
        score = p_correct_hold - float(safety_margin_opposite_weight) * p_opposite_hold
        p_hold = np.clip((score + float(safety_margin_opposite_weight)) / (1.0 + float(safety_margin_opposite_weight)), 0.0, 1.0)
    elif router_target == "dual_calibrated_utility":
        p_correct_raw = _predict_model(model, prior, X_hold)
        p_opposite_raw = _predict_model(model_opposite, prior_opposite, X_hold)
        p_correct_hold = _apply_platt_scaler(model_cal_correct, prior_cal_correct, p_correct_raw)
        p_opposite_hold = _apply_platt_scaler(model_cal_opposite, prior_cal_opposite, p_opposite_raw)
        utility = (
            float(utility_correct_reward) * p_correct_hold
            - float(utility_opposite_penalty) * p_opposite_hold
        )
        p_hold = np.clip(
            (utility + float(utility_opposite_penalty))
            / max(1e-9, float(utility_correct_reward + utility_opposite_penalty)),
            0.0,
            1.0,
        )
    elif router_target == "dual_head_constrained":
        p_rank_hold = _predict_model(model, prior, X_hold)
        p_accept_hold = _predict_model(model_cal_correct, prior_cal_correct, X_hold)
        p_opposite_hold = _predict_model(model_opposite, prior_opposite, X_hold)
        p_hold = np.clip(p_rank_hold * p_accept_hold * (1.0 - p_opposite_hold), 0.0, 1.0)
        p_correct_hold = p_accept_hold
    elif router_target == "pairwise_rank_utility":
        hold_batches_sorted = sorted(hold_df["batch_id"].unique().to_list())
        p_hold = np.full((hold_df.height,), 0.5, dtype=np.float64)
        p_correct_hold = np.full((hold_df.height,), np.nan, dtype=np.float64)
        p_opposite_hold = np.full((hold_df.height,), np.nan, dtype=np.float64)
        h_batch = hold_df["batch_id"].to_numpy().astype(np.int64)
        for b in hold_batches_sorted:
            idx = np.where(h_batch == int(b))[0]
            if idx.size == 0:
                continue
            p_hold[idx] = _predict_pairwise_batch_scores(model=model, prior=prior, x_batch=X_hold[idx])
    elif router_target == "topk_set_utility":
        p_set_hold = _predict_model(model, prior, X_hold)
        p_correct_hold = _predict_model(model_cal_correct, prior_cal_correct, X_hold)
        p_opposite_hold = _predict_model(model_opposite, prior_opposite, X_hold)
        utility = (
            float(utility_correct_reward) * p_correct_hold
            - float(utility_opposite_penalty) * p_opposite_hold
        )
        p_utility_hold = np.clip(
            (utility + float(utility_opposite_penalty))
            / max(1e-9, float(utility_correct_reward + utility_opposite_penalty)),
            0.0,
            1.0,
        )
        p_hold = np.clip(p_set_hold * p_utility_hold, 0.0, 1.0)
    elif router_target == "srsr_set_router":
        p_set_hold = _predict_model(model, prior, X_hold)
        p_correct_hold = _predict_model(model_cal_correct, prior_cal_correct, X_hold)
        p_opposite_hold = _predict_model(model_opposite, prior_opposite, X_hold)
        p_rank_cls_hold = _predict_model(model_rank_cls, prior_rank_cls, X_hold)
        utility = (
            float(utility_correct_reward) * p_correct_hold
            - float(utility_opposite_penalty) * p_opposite_hold
        )
        p_utility_hold = np.clip(
            (utility + float(utility_opposite_penalty))
            / max(1e-9, float(utility_correct_reward + utility_opposite_penalty)),
            0.0,
            1.0,
        )
        p_pair_hold = np.full(p_set_hold.shape[0], 0.5, dtype=np.float64)
        h_batch = hold_df["batch_id"].to_numpy().astype(np.int64)
        hold_batches_sorted = sorted(np.unique(h_batch).tolist())
        for b in hold_batches_sorted:
            idx = np.where(h_batch == int(b))[0]
            if idx.size == 0:
                continue
            p_pair_hold[idx] = _predict_pairwise_batch_scores(
                model=model_pair,
                prior=prior_pair,
                x_batch=X_hold[idx],
            )
        retrieval_hold = np.clip(0.55 * p_pair_hold + 0.45 * p_rank_cls_hold, 0.0, 1.0)
        row_score_hold = np.clip(retrieval_hold * p_set_hold * p_utility_hold, 0.0, 1.0)
        p_hold = np.full(row_score_hold.shape[0], 0.5, dtype=np.float64)
        for b in hold_batches_sorted:
            idx = np.where(h_batch == int(b))[0]
            if idx.size == 0:
                continue
            srsr_hold_df = _build_srsr_batch_table(
                batch_id=h_batch[idx],
                row_score=row_score_hold[idx],
                p_set=p_set_hold[idx],
                p_correct=p_correct_hold[idx],
                p_opp=p_opposite_hold[idx],
                cfg_dir=hold_df["config_pred_dir"].to_numpy().astype(np.int8)[idx],
                topk=int(max(1, set_recall_k)),
                utility_correct_reward=utility_correct_reward,
                utility_opposite_penalty=utility_opposite_penalty,
            )
            X_set = np.nan_to_num(
                srsr_hold_df.select(SRSR_BATCH_FEATURE_COLS).to_numpy().astype(np.float64),
                nan=0.0,
                posinf=0.0,
                neginf=0.0,
            )
            p_set_good = _predict_model(model_set_good, prior_set_good, X_set)
            p_set_opp = _predict_model(model_set_opp, prior_set_opp, X_set)
            gate = float(np.clip(p_set_good[0] * (1.0 - p_set_opp[0]), 0.0, 1.0))
            p_hold[idx] = np.clip(row_score_hold[idx] * gate, 0.0, 1.0)
    elif router_target == "shift_reject_utility" and bool(shift_router_retrieval_upgrade):
        p_base_hold = _predict_regression_model(model, prior, X_hold)
        p_rank_hold = _predict_model(model_retrieval_rank, prior_retrieval_rank, X_hold)
        p_pair_hold = np.full(p_base_hold.shape[0], 0.5, dtype=np.float64)
        h_batch = hold_df["batch_id"].to_numpy().astype(np.int64)
        hold_batches_sorted = sorted(np.unique(h_batch).tolist())
        for b in hold_batches_sorted:
            idx = np.where(h_batch == int(b))[0]
            if idx.size == 0:
                continue
            p_pair_hold[idx] = _predict_pairwise_batch_scores(
                model=model_retrieval_pair,
                prior=prior_retrieval_pair,
                x_batch=X_hold[idx],
            )
        p_hold, _ = _blend_shift_router_scores(
            p_base=p_base_hold,
            p_rank=p_rank_hold,
            p_pair=p_pair_hold,
            retrieval_blend=float(shift_router_retrieval_blend),
            pair_weight=float(shift_router_retrieval_pair_weight),
            rank_weight=float(shift_router_retrieval_rank_weight),
        )
        p_correct_hold = np.full(p_hold.shape[0], np.nan, dtype=np.float64)
        p_opposite_hold = np.full(p_hold.shape[0], np.nan, dtype=np.float64)
    elif router_target == "groupwise_ltr_utility":
        if model is None:
            p_hold = np.full(X_hold.shape[0], 0.5, dtype=np.float64)
        else:
            s_hold = model.predict(X_hold).astype(np.float64)
            p_hold = _rank_scores_to_prob(s_hold)
        p_correct_hold = np.full(p_hold.shape[0], np.nan, dtype=np.float64)
        p_opposite_hold = np.full(p_hold.shape[0], np.nan, dtype=np.float64)
    elif is_classifier_target:
        p_hold = _predict_model(model, prior, X_hold)
        p_correct_hold = np.full(p_hold.shape[0], np.nan, dtype=np.float64)
        p_opposite_hold = np.full(p_hold.shape[0], np.nan, dtype=np.float64)
    else:
        p_hold = _predict_regression_model(model, prior, X_hold)
        p_correct_hold = np.full(p_hold.shape[0], np.nan, dtype=np.float64)
        p_opposite_hold = np.full(p_hold.shape[0], np.nan, dtype=np.float64)

    out = hold_df.select(
        [
            "batch_id",
            "action_key",
            "hit",
            "rank_label",
            "dir_acc",
            "utility_score",
            "selective_binary_label",
            "selective_utility_score",
            "set_recall_label",
            "config_pred_dir",
            "truth_dir",
        ]
    ).rename(
        {
            "hit": "actual_hit",
            "rank_label": "actual_rank_label",
            "dir_acc": "actual_dir_acc",
            "utility_score": "actual_utility_score",
            "selective_binary_label": "actual_selective_binary_label",
            "selective_utility_score": "actual_selective_utility_score",
            "set_recall_label": "actual_set_recall_label",
        }
    ).with_columns(
        [
            pl.Series("p_hit_router", p_hold),
            pl.Series("p_correct_router", p_correct_hold),
            pl.Series("p_opposite_router", p_opposite_hold),
            pl.lit(model_name).alias("model"),
            pl.lit(int(lookback)).alias("lookback"),
        ]
    )

    train_max_batch = int(max(train_tail_batches))
    leakage = [
        PredictRecord(pred_batch=int(b), train_max_batch=train_max_batch, source=f"router_holdout_{model_name}")
        for b in sorted(hold_df["batch_id"].unique().to_list())
    ]
    return out.sort(["batch_id", "action_key"]), leakage


def _candidate_max_active_coverage(
    pred_df: pl.DataFrame,
    gate_method: str,
    threshold_grid: tuple[float, ...],
    rolling_quantile_grid: tuple[float, ...],
    rolling_quantile_lookback: int,
    rolling_quantile_min_history: int,
    consensus_k_grid: tuple[int, ...],
    use_directional_thresholds: bool,
    directional_threshold_grid: tuple[float, ...],
) -> tuple[float, int]:
    if pred_df.height == 0:
        return 0.0, 0

    max_cov = 0.0
    max_active = 0

    for ck in consensus_k_grid:
        if gate_method == "rolling_quantile":
            threshold_pairs = [(float(q), float(q)) for q in rolling_quantile_grid]
        elif use_directional_thresholds:
            threshold_pairs = [
                (float(up), float(down))
                for up in directional_threshold_grid
                for down in directional_threshold_grid
            ]
        else:
            threshold_pairs = [(float(th), float(th)) for th in threshold_grid]

        for th_up, th_down in threshold_pairs:
            if gate_method == "rolling_quantile":
                sel = _selection_by_batch_rolling_quantile(
                    pred_df=pred_df,
                    prob_col="p_hit_router",
                    quantile=float(th_up),
                    lookback=int(rolling_quantile_lookback),
                    consensus_k=int(ck),
                    init_history_scores=None,
                    min_history=int(rolling_quantile_min_history),
                )
            elif use_directional_thresholds:
                sel = _selection_by_batch_directional_threshold(
                    pred_df,
                    prob_col="p_hit_router",
                    threshold_up=th_up,
                    threshold_down=th_down,
                    consensus_k=int(ck),
                )
            else:
                sel = _selection_by_batch(
                    pred_df,
                    prob_col="p_hit_router",
                    threshold=th_up,
                    consensus_k=int(ck),
                )

            if sel.height == 0:
                continue
            active = int((sel["pred_dir"] != DIR_HOLD).sum())
            cov = float(active / max(1, sel.height))
            if cov > max_cov or (math.isclose(cov, max_cov) and active > max_active):
                max_cov = cov
                max_active = active

    return float(max_cov), int(max_active)


def _build_batch_selection_base(pred_df: pl.DataFrame, prob_col: str, consensus_k: int = 1) -> pl.DataFrame:
    k = int(max(1, consensus_k))
    return (
        pred_df.group_by("batch_id")
        .agg(
            [
                pl.col("action_key").sort_by(pl.col(prob_col), descending=True).first().alias("selected_action_key"),
                pl.col(prob_col).max().alias("selected_p_hit"),
                pl.col("config_pred_dir").sort_by(pl.col(prob_col), descending=True).head(k).alias("topk_dirs"),
            ]
        )
        .join(
            pred_df.select(["batch_id", "action_key", "config_pred_dir", "truth_dir", "actual_hit"]).rename(
                {
                    "action_key": "selected_action_key",
                    "config_pred_dir": "selected_config_pred_dir",
                    "truth_dir": "truth_dir",
                    "actual_hit": "selected_actual_hit",
                }
            ),
            on=["batch_id", "selected_action_key"],
            how="left",
        )
        .with_columns(
            [
                pl.col("topk_dirs").list.len().alias("topk_n"),
                pl.col("topk_dirs").list.n_unique().alias("topk_unique_dirs"),
                pl.col("topk_dirs").list.first().alias("topk_consensus_dir"),
            ]
        )
        .with_columns(
            (
                (pl.col("topk_n") >= k)
                & (pl.col("topk_unique_dirs") == 1)
                & pl.col("topk_consensus_dir").is_in([DIR_UP, DIR_DOWN])
            ).alias("consensus_ok")
        )
        .sort("batch_id")
    )


def _selection_by_batch_rolling_quantile(
    pred_df: pl.DataFrame,
    prob_col: str,
    quantile: float,
    lookback: int,
    consensus_k: int = 1,
    init_history_scores: list[float] | None = None,
    min_history: int = 80,
) -> pl.DataFrame:
    base = _build_batch_selection_base(pred_df=pred_df, prob_col=prob_col, consensus_k=consensus_k)
    if base.height == 0:
        return base.with_columns(
            [
                pl.lit(float(quantile)).alias("rolling_quantile"),
                pl.lit(int(lookback)).alias("rolling_quantile_lookback"),
                pl.lit(DIR_HOLD).alias("pred_dir"),
                pl.lit(float("nan")).alias("rolling_threshold"),
                pl.lit(int(consensus_k)).alias("consensus_k"),
                pl.lit(float(quantile)).alias("activation_threshold"),
            ]
        )

    history = [float(x) for x in (init_history_scores or []) if np.isfinite(x)]
    lookback_n = max(30, int(lookback))
    min_hist = max(20, int(min_history))

    selected_p = base["selected_p_hit"].to_numpy().astype(np.float64)
    consensus_ok = base["consensus_ok"].to_numpy().astype(bool)
    topk_dir = base["topk_consensus_dir"].to_numpy().astype(np.int8)

    pred_dir = np.full(base.height, DIR_HOLD, dtype=np.int8)
    threshold_arr = np.full(base.height, np.nan, dtype=np.float64)

    for i in range(base.height):
        hist = history[-lookback_n:] if len(history) > lookback_n else history
        if len(hist) >= min_hist:
            thr = float(np.quantile(np.asarray(hist, dtype=np.float64), float(quantile)))
        elif len(hist) > 0:
            # Soft bootstrap before full history is available.
            q_boot = min(float(quantile), 0.90)
            thr = float(np.quantile(np.asarray(hist, dtype=np.float64), q_boot))
        else:
            thr = float("inf")
        threshold_arr[i] = thr

        if consensus_ok[i] and np.isfinite(selected_p[i]) and selected_p[i] >= thr and topk_dir[i] in (DIR_UP, DIR_DOWN):
            pred_dir[i] = int(topk_dir[i])
        else:
            pred_dir[i] = DIR_HOLD

        # Causal threshold update with current batch score after decision.
        if consensus_ok[i] and np.isfinite(selected_p[i]):
            history.append(float(selected_p[i]))

    return base.with_columns(
        [
            pl.Series("pred_dir", pred_dir),
            pl.Series("rolling_threshold", threshold_arr),
            pl.lit(float(quantile)).alias("rolling_quantile"),
            pl.lit(int(lookback_n)).alias("rolling_quantile_lookback"),
            pl.lit(int(consensus_k)).alias("consensus_k"),
            pl.lit(float(quantile)).alias("activation_threshold"),
        ]
    )


def _selection_by_batch(pred_df: pl.DataFrame, prob_col: str, threshold: float, consensus_k: int = 1) -> pl.DataFrame:
    k = int(max(1, consensus_k))
    # one selected config per batch (highest score), with optional top-k directional consensus gate.
    selected = (
        pred_df.group_by("batch_id")
        .agg(
            [
                pl.col("action_key").sort_by(pl.col(prob_col), descending=True).first().alias("selected_action_key"),
                pl.col(prob_col).max().alias("selected_p_hit"),
                pl.col("config_pred_dir").sort_by(pl.col(prob_col), descending=True).head(k).alias("topk_dirs"),
            ]
        )
        .join(
            pred_df.select(["batch_id", "action_key", "config_pred_dir", "truth_dir", "actual_hit"]).rename(
                {
                    "action_key": "selected_action_key",
                    "config_pred_dir": "selected_config_pred_dir",
                    "truth_dir": "truth_dir",
                    "actual_hit": "selected_actual_hit",
                }
            ),
            on=["batch_id", "selected_action_key"],
            how="left",
        )
        .with_columns(
            [
                pl.col("topk_dirs").list.len().alias("topk_n"),
                pl.col("topk_dirs").list.n_unique().alias("topk_unique_dirs"),
                pl.col("topk_dirs").list.first().alias("topk_consensus_dir"),
            ]
        )
        .with_columns(
            (
                (pl.col("topk_n") >= k)
                & (pl.col("topk_unique_dirs") == 1)
                & pl.col("topk_consensus_dir").is_in([DIR_UP, DIR_DOWN])
            ).alias("consensus_ok")
        )
        .with_columns(
            [
                pl.when((pl.col("selected_p_hit") >= float(threshold)) & pl.col("consensus_ok"))
                .then(pl.col("topk_consensus_dir").cast(pl.Int8))
                .otherwise(pl.lit(DIR_HOLD))
                .alias("pred_dir"),
                pl.lit(float(threshold)).alias("activation_threshold"),
                pl.lit(int(k)).alias("consensus_k"),
            ]
        )
        .sort("batch_id")
    )
    return selected


def _selection_by_batch_directional_threshold(
    pred_df: pl.DataFrame,
    prob_col: str,
    threshold_up: float,
    threshold_down: float,
    consensus_k: int = 1,
) -> pl.DataFrame:
    k = int(max(1, consensus_k))
    selected = (
        pred_df.group_by("batch_id")
        .agg(
            [
                pl.col("action_key").sort_by(pl.col(prob_col), descending=True).first().alias("selected_action_key"),
                pl.col(prob_col).max().alias("selected_p_hit"),
                pl.col("config_pred_dir").sort_by(pl.col(prob_col), descending=True).head(k).alias("topk_dirs"),
            ]
        )
        .join(
            pred_df.select(["batch_id", "action_key", "config_pred_dir", "truth_dir", "actual_hit"]).rename(
                {
                    "action_key": "selected_action_key",
                    "config_pred_dir": "selected_config_pred_dir",
                    "truth_dir": "truth_dir",
                    "actual_hit": "selected_actual_hit",
                }
            ),
            on=["batch_id", "selected_action_key"],
            how="left",
        )
        .with_columns(
            [
                pl.col("topk_dirs").list.len().alias("topk_n"),
                pl.col("topk_dirs").list.n_unique().alias("topk_unique_dirs"),
                pl.col("topk_dirs").list.first().alias("topk_consensus_dir"),
            ]
        )
        .with_columns(
            (
                (pl.col("topk_n") >= k)
                & (pl.col("topk_unique_dirs") == 1)
                & pl.col("topk_consensus_dir").is_in([DIR_UP, DIR_DOWN])
            ).alias("consensus_ok")
        )
        .with_columns(
            [
                pl.when(
                    pl.col("consensus_ok")
                    & (pl.col("topk_consensus_dir") == pl.lit(DIR_UP))
                    & (pl.col("selected_p_hit") >= float(threshold_up))
                )
                .then(pl.lit(DIR_UP))
                .when(
                    pl.col("consensus_ok")
                    & (pl.col("topk_consensus_dir") == pl.lit(DIR_DOWN))
                    & (pl.col("selected_p_hit") >= float(threshold_down))
                )
                .then(pl.lit(DIR_DOWN))
                .otherwise(pl.lit(DIR_HOLD))
                .alias("pred_dir"),
                pl.lit(float(threshold_up)).alias("activation_threshold_up"),
                pl.lit(float(threshold_down)).alias("activation_threshold_down"),
                pl.lit(float(0.5 * (threshold_up + threshold_down))).alias("activation_threshold"),
                pl.lit(int(k)).alias("consensus_k"),
            ]
        )
        .sort("batch_id")
    )
    return selected


def _metrics_from_selection(sel_df: pl.DataFrame, cadence_min: float, cadence_max: float) -> dict[str, Any]:
    if sel_df.height == 0:
        return {
            "batch_count": 0,
            "active_batches": 0,
            "coverage": 0.0,
            "batches_per_signal": float("inf"),
            "cadence_target_hit": False,
            "directional_active_safe_accuracy": 0.0,
            "opposite_fp_rate_active": 0.0,
            "opposite_fp_rate_covered": 0.0,
            "opposite_fp_count": 0,
        }

    pred = sel_df["pred_dir"].to_numpy().astype(int)
    truth = sel_df["truth_dir"].to_numpy().astype(int)
    n = pred.size

    active = pred != DIR_HOLD
    active_n = int(active.sum())

    opposite = ((pred == DIR_UP) & (truth == DIR_DOWN)) | ((pred == DIR_DOWN) & (truth == DIR_UP))
    opposite_n = int(opposite.sum())

    correct_active = active & (pred == truth) & (truth != DIR_HOLD)
    safe_acc = float(correct_active.sum() / max(1, active_n)) if active_n > 0 else 0.0

    batches_per_signal = float(n / active_n) if active_n > 0 else float("inf")
    cadence_hit = bool(cadence_min <= batches_per_signal <= cadence_max)

    return {
        "batch_count": int(n),
        "active_batches": int(active_n),
        "coverage": float(active_n / max(1, n)),
        "batches_per_signal": float(batches_per_signal),
        "cadence_target_hit": cadence_hit,
        "directional_active_safe_accuracy": float(safe_acc),
        "opposite_fp_rate_active": float(opposite_n / max(1, active_n)) if active_n > 0 else 0.0,
        "opposite_fp_rate_covered": float(opposite_n / max(1, n)),
        "opposite_fp_count": int(opposite_n),
    }


def _score_operating_point(m: dict[str, Any], inp: Inputs) -> tuple[bool, float, dict[str, float]]:
    v1 = max(0.0, m["opposite_fp_rate_active"] - inp.max_opposite_fp_active)
    v2 = max(0.0, m["opposite_fp_rate_covered"] - inp.max_opposite_fp_covered)
    v3 = max(0.0, inp.min_safe_accuracy - m["directional_active_safe_accuracy"])

    bps = m["batches_per_signal"]
    if not np.isfinite(bps):
        v4 = 1.0
    elif bps < inp.target_cadence_min:
        v4 = (inp.target_cadence_min - bps) / max(1e-9, inp.target_cadence_min)
    elif bps > inp.target_cadence_max:
        v4 = (bps - inp.target_cadence_max) / max(1e-9, inp.target_cadence_max)
    else:
        v4 = 0.0

    cov = float(m.get("coverage", 0.0))
    if cov < inp.coverage_selection_min:
        v5 = (inp.coverage_selection_min - cov) / max(1e-9, inp.coverage_selection_min)
    elif cov > inp.coverage_selection_max:
        v5 = (cov - inp.coverage_selection_max) / max(1e-9, inp.coverage_selection_max)
    else:
        v5 = 0.0

    feasible = (v1 == 0.0 and v2 == 0.0 and v3 == 0.0 and v4 == 0.0 and v5 == 0.0)
    # Weighted violation score.
    score = 4.0 * v1 + 3.0 * v2 + 3.0 * v3 + 1.0 * v4 + 2.0 * v5
    return feasible, float(score), {"opp_active": v1, "opp_covered": v2, "safe_acc": v3, "cadence": v4, "coverage": v5}


def _hoeffding_radius(n: int, delta: float) -> float:
    if n <= 0:
        return float("inf")
    return float(math.sqrt(math.log(1.0 / max(1e-12, float(delta))) / (2.0 * float(n))))


def _effective_n_from_weights(weights: np.ndarray) -> float:
    if weights.size == 0:
        return 0.0
    s1 = float(np.sum(weights))
    s2 = float(np.sum(weights**2))
    if s1 <= 0.0 or s2 <= 0.0:
        return 0.0
    return float((s1 * s1) / s2)


def _build_conformal_batch_weights(batch_ids: np.ndarray, inp: Inputs) -> np.ndarray:
    if batch_ids.size == 0:
        return np.array([], dtype=np.float64)
    if inp.conformal_shift_weighting == "none":
        return np.ones(batch_ids.size, dtype=np.float64)
    # exp_recent: newer calibration batches get more weight (covariate-shift proxy).
    max_b = int(np.max(batch_ids))
    age = (max_b - batch_ids.astype(np.int64)).astype(np.float64)
    tau = float(inp.conformal_decay_halflife_batches) / math.log(2.0)
    w = np.exp(-age / max(1e-9, tau))
    return np.clip(w.astype(np.float64), 1e-6, None)


def _rate_hat_ucb(
    num_mask: np.ndarray,
    den_mask: np.ndarray,
    weights: np.ndarray,
    delta: float,
) -> tuple[float, float, float, float]:
    if weights.size == 0:
        return 0.0, float("inf"), 0.0, float("inf")
    w_num = float(np.sum(weights[num_mask]))
    w_den = float(np.sum(weights[den_mask]))
    if w_den <= 0.0:
        return 0.0, float("inf"), 0.0, float("inf")
    hat = float(w_num / w_den)
    n_eff = _effective_n_from_weights(weights[den_mask])
    rad = _hoeffding_radius(int(max(1, math.floor(n_eff))), delta)
    ucb = min(1.0, hat + rad) if np.isfinite(rad) else float("inf")
    return hat, float(ucb), float(n_eff), float(rad)


def _safe_hat_lcb(
    correct_mask: np.ndarray,
    den_mask: np.ndarray,
    weights: np.ndarray,
    delta: float,
) -> tuple[float, float, float, float]:
    if weights.size == 0:
        return 0.0, 0.0, 0.0, float("inf")
    w_num = float(np.sum(weights[correct_mask]))
    w_den = float(np.sum(weights[den_mask]))
    if w_den <= 0.0:
        return 0.0, 0.0, 0.0, float("inf")
    hat = float(w_num / w_den)
    n_eff = _effective_n_from_weights(weights[den_mask])
    rad = _hoeffding_radius(int(max(1, math.floor(n_eff))), delta)
    lcb = max(0.0, hat - rad) if np.isfinite(rad) else 0.0
    return float(hat), float(lcb), float(n_eff), float(rad)


def _conformal_risk_stats(sel_df: pl.DataFrame, inp: Inputs) -> dict[str, Any]:
    if sel_df.height == 0:
        return {
            "opp_active_hat": 0.0,
            "opp_active_ucb": float("inf"),
            "opp_covered_hat": 0.0,
            "opp_covered_ucb": float("inf"),
            "safe_acc_hat": 0.0,
            "safe_acc_lcb": 0.0,
            "n_eff_total": 0.0,
            "n_eff_active": 0.0,
            "n_eff_up": 0.0,
            "n_eff_down": 0.0,
        }

    batch_ids = sel_df["batch_id"].to_numpy().astype(np.int64)
    pred = sel_df["pred_dir"].to_numpy().astype(np.int8)
    truth = sel_df["truth_dir"].to_numpy().astype(np.int8)
    weights = _build_conformal_batch_weights(batch_ids, inp)

    active = pred != DIR_HOLD
    up = pred == DIR_UP
    down = pred == DIR_DOWN
    opposite_up = up & (truth == DIR_DOWN)
    opposite_down = down & (truth == DIR_UP)
    opposite = opposite_up | opposite_down
    correct_active = active & (pred == truth) & np.isin(truth, [DIR_UP, DIR_DOWN])
    total = np.ones_like(active, dtype=bool)

    opp_active_hat, opp_active_ucb, n_eff_active, rad_active = _rate_hat_ucb(
        opposite,
        active,
        weights,
        inp.conformal_delta,
    )
    opp_cov_hat, opp_cov_ucb, n_eff_total, rad_total = _rate_hat_ucb(
        opposite,
        total,
        weights,
        inp.conformal_delta,
    )
    safe_hat, safe_lcb, _, _ = _safe_hat_lcb(
        correct_active,
        active,
        weights,
        inp.conformal_delta,
    )

    up_hat, up_ucb, n_eff_up, _ = _rate_hat_ucb(opposite_up, up, weights, inp.conformal_delta)
    down_hat, down_ucb, n_eff_down, _ = _rate_hat_ucb(opposite_down, down, weights, inp.conformal_delta)
    up_cov_hat, up_cov_ucb, _, _ = _rate_hat_ucb(opposite_up, total, weights, inp.conformal_delta)
    down_cov_hat, down_cov_ucb, _, _ = _rate_hat_ucb(opposite_down, total, weights, inp.conformal_delta)

    if inp.conformal_class_conditional:
        active_ucb_candidates: list[float] = []
        cov_ucb_candidates: list[float] = []
        if n_eff_up > 0.0:
            active_ucb_candidates.append(float(up_ucb))
            cov_ucb_candidates.append(float(up_cov_ucb))
        if n_eff_down > 0.0:
            active_ucb_candidates.append(float(down_ucb))
            cov_ucb_candidates.append(float(down_cov_ucb))
        # If one class is absent in selected actives, do not force an infinite bound from that class.
        opp_active_ucb_used = max(active_ucb_candidates) if active_ucb_candidates else float(opp_active_ucb)
        opp_cov_ucb_used = max(cov_ucb_candidates) if cov_ucb_candidates else float(opp_cov_ucb)
    else:
        opp_active_ucb_used = opp_active_ucb
        opp_cov_ucb_used = opp_cov_ucb

    return {
        "opp_active_hat": float(opp_active_hat),
        "opp_active_ucb": float(opp_active_ucb_used),
        "opp_covered_hat": float(opp_cov_hat),
        "opp_covered_ucb": float(opp_cov_ucb_used),
        "safe_acc_hat": float(safe_hat),
        "safe_acc_lcb": float(safe_lcb),
        "n_eff_total": float(n_eff_total),
        "n_eff_active": float(n_eff_active),
        "n_eff_up": float(n_eff_up),
        "n_eff_down": float(n_eff_down),
        "rad_active": float(rad_active),
        "rad_total": float(rad_total),
        "class_up_opp_hat": float(up_hat),
        "class_up_opp_ucb": float(up_ucb),
        "class_down_opp_hat": float(down_hat),
        "class_down_opp_ucb": float(down_ucb),
        "class_up_cov_hat": float(up_cov_hat),
        "class_up_cov_ucb": float(up_cov_ucb),
        "class_down_cov_hat": float(down_cov_hat),
        "class_down_cov_ucb": float(down_cov_ucb),
    }


def _score_operating_point_conformal(
    m: dict[str, Any],
    inp: Inputs,
    *,
    opposite_fp_rate_active_ucb: float,
    opposite_fp_rate_covered_ucb: float,
    safe_accuracy_lcb: float,
) -> tuple[bool, float, dict[str, float]]:
    v1 = max(0.0, float(opposite_fp_rate_active_ucb) - inp.max_opposite_fp_active)
    v2 = max(0.0, float(opposite_fp_rate_covered_ucb) - inp.max_opposite_fp_covered)
    v3 = max(0.0, inp.min_safe_accuracy - float(safe_accuracy_lcb))

    bps = float(m["batches_per_signal"])
    if not np.isfinite(bps):
        v4 = 1.0
    elif bps < inp.target_cadence_min:
        v4 = (inp.target_cadence_min - bps) / max(1e-9, inp.target_cadence_min)
    elif bps > inp.target_cadence_max:
        v4 = (bps - inp.target_cadence_max) / max(1e-9, inp.target_cadence_max)
    else:
        v4 = 0.0

    cov = float(m.get("coverage", 0.0))
    if cov < inp.coverage_selection_min:
        v5 = (inp.coverage_selection_min - cov) / max(1e-9, inp.coverage_selection_min)
    elif cov > inp.coverage_selection_max:
        v5 = (cov - inp.coverage_selection_max) / max(1e-9, inp.coverage_selection_max)
    else:
        v5 = 0.0

    feasible = (v1 == 0.0 and v2 == 0.0 and v3 == 0.0 and v4 == 0.0 and v5 == 0.0)
    score = 4.0 * v1 + 3.0 * v2 + 3.0 * v3 + 1.0 * v4 + 2.0 * v5
    return feasible, float(score), {"opp_active": v1, "opp_covered": v2, "safe_acc": v3, "cadence": v4, "coverage": v5}


def _pick_operating_point(sweep_rows: list[dict[str, Any]], inp: Inputs) -> dict[str, Any]:
    if inp.compat_mode == "legacy_safe_first":
        safefirst_rows = [r for r in sweep_rows if float(r.get("directional_active_safe_accuracy", 0.0)) >= float(inp.min_safe_accuracy)]
        if safefirst_rows:
            best = sorted(
                safefirst_rows,
                key=lambda r: (
                    -float(r.get("directional_active_safe_accuracy", 0.0)),
                    -int(r.get("active_batches", 0)),
                    float(r.get("opposite_fp_rate_active", 1.0)),
                    float(r.get("opposite_fp_rate_covered", 1.0)),
                    -int(r.get("consensus_k", 1)),
                    r.get("activation_threshold_up", r["activation_threshold"]),
                    r.get("activation_threshold_down", r["activation_threshold"]),
                    r["activation_threshold"],
                ),
            )[0]
            best["selection_status"] = "compat_legacy_safe_first"
            best["selection_objective"] = "compat_legacy_safe_first"
            return best

    if inp.selection_objective == "primal_dual":
        return _pick_operating_point_primal_dual(sweep_rows, inp)

    feasible_rows = [r for r in sweep_rows if r["feasible"]]
    if feasible_rows:
        best = sorted(
            feasible_rows,
            key=lambda r: (
                -r["active_batches"],
                -r["directional_active_safe_accuracy"],
                r["opposite_fp_rate_active"],
                r["opposite_fp_rate_covered"],
                -int(r.get("consensus_k", 1)),
                r.get("activation_threshold_up", r["activation_threshold"]),
                r.get("activation_threshold_down", r["activation_threshold"]),
                r["activation_threshold"],
            ),
        )[0]
        best["selection_status"] = "feasible"
        return best

    best = sorted(
        sweep_rows,
        key=lambda r: (
            r["violation_score"],
            -r["directional_active_safe_accuracy"],
            r["opposite_fp_rate_active"],
            r["opposite_fp_rate_covered"],
            -r["active_batches"],
            -int(r.get("consensus_k", 1)),
            r.get("activation_threshold_up", r["activation_threshold"]),
            r.get("activation_threshold_down", r["activation_threshold"]),
        ),
    )[0]
    best["selection_status"] = "best_near_feasible"
    return best


def _pd_reward(row: dict[str, Any], mode: str) -> float:
    safe = float(row.get("directional_active_safe_accuracy", 0.0))
    cov = float(row.get("coverage", 0.0))
    opp_cov = float(row.get("opposite_fp_rate_covered", 0.0))
    opp_active = float(row.get("opposite_fp_rate_active", 0.0))
    if mode == "coverage_safe":
        return float(cov + 0.25 * safe - opp_cov - 0.10 * opp_active)
    # utility mode: expected covered directional quality net of opposite-direction covered errors.
    return float(safe * cov - opp_cov)


def _pd_constraints(row: dict[str, Any], inp: Inputs) -> np.ndarray:
    safe = float(row.get("directional_active_safe_accuracy", 0.0))
    cov = float(row.get("coverage", 0.0))
    opp_active = float(row.get("opposite_fp_rate_active", 0.0))
    opp_cov = float(row.get("opposite_fp_rate_covered", 0.0))
    return np.array(
        [
            opp_active - float(inp.max_opposite_fp_active),
            opp_cov - float(inp.max_opposite_fp_covered),
            float(inp.min_safe_accuracy) - safe,
            float(inp.coverage_selection_min) - cov,
            cov - float(inp.coverage_selection_max),
        ],
        dtype=np.float64,
    )


def _pick_operating_point_primal_dual(sweep_rows: list[dict[str, Any]], inp: Inputs) -> dict[str, Any]:
    if not sweep_rows:
        raise RuntimeError("empty sweep_rows for primal-dual selection")

    rewards = np.array([_pd_reward(r, inp.primal_dual_utility_mode) for r in sweep_rows], dtype=np.float64)
    g = np.stack([_pd_constraints(r, inp) for r in sweep_rows], axis=0)
    feasible_mask = np.all(g <= 0.0, axis=1)

    if np.any(feasible_mask):
        feasible_idx = np.where(feasible_mask)[0].tolist()
        idx = sorted(
            feasible_idx,
            key=lambda i: (
                -float(rewards[i]),
                -float(sweep_rows[i].get("active_batches", 0)),
                float(sweep_rows[i].get("opposite_fp_rate_active", 1.0)),
                float(sweep_rows[i].get("opposite_fp_rate_covered", 1.0)),
            ),
        )[0]
        best = dict(sweep_rows[idx])
        best["selection_status"] = "primal_dual_feasible"
        best["selection_objective"] = "primal_dual"
        best["primal_dual_reward"] = float(rewards[idx])
        best["primal_dual_iters"] = int(inp.primal_dual_iters)
        best["primal_dual_step"] = float(inp.primal_dual_step)
        best["primal_dual_utility_mode"] = inp.primal_dual_utility_mode
        best["primal_dual_lambda"] = {
            "opp_active": 0.0,
            "opp_covered": 0.0,
            "safe_acc": 0.0,
            "coverage_min": 0.0,
            "coverage_max": 0.0,
        }
        return best

    lam = np.zeros(5, dtype=np.float64)
    choose_counts = np.zeros(len(sweep_rows), dtype=np.int64)
    g_plus = np.maximum(g, 0.0)

    for _ in range(int(inp.primal_dual_iters)):
        scores = rewards - (g_plus @ lam)
        idx = int(np.argmax(scores))
        choose_counts[idx] += 1
        lam = np.maximum(0.0, lam + float(inp.primal_dual_step) * g[idx])

    final_scores = rewards - (g_plus @ lam)
    idx = sorted(
        range(len(sweep_rows)),
        key=lambda i: (
            -float(final_scores[i]),
            float(sweep_rows[i].get("violation_score", 1e9)),
            -float(rewards[i]),
            -int(choose_counts[i]),
            -float(sweep_rows[i].get("active_batches", 0)),
        ),
    )[0]

    best = dict(sweep_rows[idx])
    best["selection_status"] = "primal_dual_near_feasible"
    best["selection_objective"] = "primal_dual"
    best["primal_dual_reward"] = float(rewards[idx])
    best["primal_dual_final_score"] = float(final_scores[idx])
    best["primal_dual_selected_count"] = int(choose_counts[idx])
    best["primal_dual_iters"] = int(inp.primal_dual_iters)
    best["primal_dual_step"] = float(inp.primal_dual_step)
    best["primal_dual_utility_mode"] = inp.primal_dual_utility_mode
    best["primal_dual_lambda"] = {
        "opp_active": float(lam[0]),
        "opp_covered": float(lam[1]),
        "safe_acc": float(lam[2]),
        "coverage_min": float(lam[3]),
        "coverage_max": float(lam[4]),
    }
    return best


def _policy_loss(pred_dir: int, truth_dir: int, hold_loss: float) -> float:
    if pred_dir == DIR_HOLD:
        return float(hold_loss)
    if pred_dir == truth_dir and truth_dir in (DIR_UP, DIR_DOWN):
        return 0.0
    if (pred_dir == DIR_UP and truth_dir == DIR_DOWN) or (pred_dir == DIR_DOWN and truth_dir == DIR_UP):
        return 1.0
    return float(hold_loss)


def _build_policy_cache(
    router_pred_df: pl.DataFrame,
    policy_keys: list[tuple[int, float]],
) -> dict[tuple[int, float], pl.DataFrame]:
    cache: dict[tuple[int, float], pl.DataFrame] = {}
    for ck, th in policy_keys:
        cache[(int(ck), float(th))] = _selection_by_batch(
            router_pred_df,
            prob_col="p_hit_router",
            threshold=float(th),
            consensus_k=int(ck),
        ).select(
            [
                "batch_id",
                "selected_action_key",
                "selected_p_hit",
                "pred_dir",
                "truth_dir",
                "consensus_k",
                "activation_threshold",
            ]
        ).sort("batch_id")
    return cache


def _run_online_policy_pool(
    policy_cache: dict[tuple[int, float], pl.DataFrame],
    policy_keys: list[tuple[int, float]],
    warmup_batches: list[int],
    eval_batches: list[int],
    eta: float,
    hold_loss: float,
    source_tag: str,
) -> tuple[pl.DataFrame, list[PredictRecord]]:
    if not policy_keys:
        return pl.DataFrame(), []

    all_batches = sorted(set(int(x) for x in warmup_batches + eval_batches))
    eval_batch_set = set(int(x) for x in eval_batches)
    if not all_batches:
        return pl.DataFrame(), []

    truth_by_batch: dict[int, int] = {}
    policy_rows: dict[tuple[int, float], dict[int, tuple[str | None, float, int]]] = {}
    for key in policy_keys:
        sel = policy_cache[key].filter(pl.col("batch_id").is_in(all_batches))
        rows: dict[int, tuple[str | None, float, int]] = {}
        for row in sel.iter_rows(named=True):
            b = int(row["batch_id"])
            rows[b] = (
                str(row["selected_action_key"]) if row["selected_action_key"] is not None else None,
                float(row["selected_p_hit"]),
                int(row["pred_dir"]),
            )
            truth_by_batch[b] = int(row["truth_dir"])
        policy_rows[key] = rows

    n_policies = len(policy_keys)
    log_w = np.zeros(n_policies, dtype=np.float64)
    out_rows: list[dict[str, Any]] = []
    leakage: list[PredictRecord] = []
    last_observed_batch = int(max(warmup_batches)) if warmup_batches else int(min(all_batches) - 1)

    for b in all_batches:
        b_int = int(b)
        truth = int(truth_by_batch.get(b_int, DIR_HOLD))

        losses = np.zeros(n_policies, dtype=np.float64)
        for i, key in enumerate(policy_keys):
            pred_dir = int(policy_rows[key].get(b_int, (None, 0.0, DIR_HOLD))[2])
            losses[i] = _policy_loss(pred_dir=pred_dir, truth_dir=truth, hold_loss=float(hold_loss))

        if b_int in eval_batch_set:
            best_i = int(np.argmax(log_w))
            best_key = policy_keys[best_i]
            selected_action_key, selected_p_hit, pred_dir = policy_rows[best_key].get(b_int, (None, 0.0, DIR_HOLD))

            weights = np.exp(log_w - np.max(log_w))
            weights = weights / max(1e-12, float(np.sum(weights)))

            out_rows.append(
                {
                    "batch_id": b_int,
                    "selected_action_key": selected_action_key,
                    "selected_p_hit": float(selected_p_hit),
                    "pred_dir": int(pred_dir),
                    "truth_dir": truth,
                    "consensus_k": int(best_key[0]),
                    "activation_threshold": float(best_key[1]),
                    "policy_eta": float(eta),
                    "policy_hold_loss": float(hold_loss),
                    "policy_pool_size": int(n_policies),
                    "selected_policy_weight": float(weights[best_i]),
                }
            )
            leakage.append(
                PredictRecord(
                    pred_batch=b_int,
                    train_max_batch=int(last_observed_batch),
                    source=source_tag,
                )
            )

        log_w = log_w - float(eta) * losses
        log_w = log_w - float(np.max(log_w))
        last_observed_batch = b_int

    out_df = pl.DataFrame(out_rows).sort("batch_id") if out_rows else pl.DataFrame()
    return out_df, leakage


def _build_leakage_report(records: list[PredictRecord]) -> dict[str, Any]:
    violations = [r for r in records if r.train_max_batch >= r.pred_batch]
    return {
        "checks": int(len(records)),
        "violations": int(len(violations)),
        "pass": bool(len(violations) == 0),
        "first_violations": [
            {
                "source": v.source,
                "pred_batch": int(v.pred_batch),
                "train_max_batch": int(v.train_max_batch),
            }
            for v in violations[:20]
        ],
    }


def _extract_context_metrics(path: Path | None) -> dict[str, Any]:
    if path is None or (not path.exists()):
        return {"available": False}
    try:
        j = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"available": False}

    bm = j.get("best_metrics_risk_guard") or j.get("best_metrics") or {}
    out = {
        "available": True,
        "path": str(path),
    }
    for k in [
        "directional_active_safe_accuracy",
        "opposite_fp_rate_active",
        "opposite_fp_rate_covered",
        "directional_active_coverage",
        "custom_mean_cost",
    ]:
        if k in bm:
            out[k] = bm[k]
    return out


def main() -> None:
    inp = parse_args()

    out_dir = inp.output_dir / f"{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{inp.output_tag}"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Phase 0: contract
    df, contract = _load_and_aggregate(inp)
    (out_dir / "dataset_contract.json").write_text(json.dumps(contract, indent=2), encoding="utf-8")

    if not contract["pass"]:
        summary = {
            "status": "failed_dataset_contract",
            "dataset_contract": contract,
            "output_dir": str(out_dir),
        }
        (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(json.dumps(summary, indent=2))
        raise SystemExit(2)

    all_batches = sorted(df["batch_id"].unique().to_list())
    if len(all_batches) < 500:
        raise RuntimeError("Need at least 500 batches after filtering.")

    holdout_n = int(min(inp.holdout_batches, max(0, len(all_batches) - 200)))
    train_batches = all_batches[:-holdout_n] if holdout_n > 0 else all_batches
    holdout_batches = all_batches[-holdout_n:] if holdout_n > 0 else []

    if inp.verbose:
        print(f"Batches total={len(all_batches)} train={len(train_batches)} holdout={len(holdout_batches)}")

    # Phase 1
    per_scores, per_selected, per_pred, leak_records_cfg = _run_per_config_phase(
        df=df,
        train_batches=train_batches,
        holdout_batches=holdout_batches,
        inp=inp,
    )

    per_scores.write_parquet(out_dir / "per_config_lookback_scores.parquet")
    per_scores.write_csv(out_dir / "per_config_lookback_scores.csv")
    per_selected.write_parquet(out_dir / "selected_lookback_by_config.parquet")
    per_selected.write_csv(out_dir / "selected_lookback_by_config.csv")
    per_pred.write_parquet(out_dir / "per_config_best_probabilities.parquet")
    per_pred.write_csv(out_dir / "per_config_best_probabilities.csv")

    if inp.mode == "per_config":
        leak = _build_leakage_report(leak_records_cfg)
        (out_dir / "leakage_guard_report.json").write_text(json.dumps({"per_config": leak, "global_router": None}, indent=2), encoding="utf-8")

        summary = {
            "status": "ok_per_config_only",
            "dataset_contract": contract,
            "counts": {
                "batches_total": len(all_batches),
                "batches_train": len(train_batches),
                "batches_holdout": len(holdout_batches),
                "configs": int(df["action_key"].n_unique()),
            },
            "artifacts": {
                "per_config_lookback_scores_csv": str((out_dir / "per_config_lookback_scores.csv").resolve()),
                "selected_lookback_by_config_csv": str((out_dir / "selected_lookback_by_config.csv").resolve()),
                "per_config_best_probabilities_parquet": str((out_dir / "per_config_best_probabilities.parquet").resolve()),
                "dataset_contract_json": str((out_dir / "dataset_contract.json").resolve()),
                "leakage_guard_report_json": str((out_dir / "leakage_guard_report.json").resolve()),
            },
        }
        (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

        tracking_context = {
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "linear_issue_url": inp.linear_issue_url,
            "notion_page_url": inp.notion_page_url,
            "run_command": " ".join(sys.argv),
            "git_commit_hash": _git_commit_hash(inp.project_root),
        }
        (out_dir / "tracking_context.json").write_text(json.dumps(tracking_context, indent=2), encoding="utf-8")

        print(f"Done (per_config). Output: {out_dir}")
        return

    # Phase 2: global router
    router_tbl = _build_router_table(
        df,
        per_pred,
        utility_correct_reward=inp.utility_correct_reward,
        utility_opposite_penalty=inp.utility_opposite_penalty,
        selective_hold_cost=inp.selective_hold_cost,
        set_recall_k=inp.set_recall_k,
    )

    candidate_rows: list[dict[str, Any]] = []
    candidate_predictions: dict[tuple[str, int], pl.DataFrame] = {}
    leak_records_router: list[PredictRecord] = []

    for model_name in inp.router_models:
        for lb in inp.router_lookback_grid:
            pred_df, met, recs = _simulate_router_candidate(
                router_df=router_tbl,
                train_batches=train_batches,
                model_name=model_name,
                router_target=inp.router_target,
                router_cost_opposite_penalty=inp.router_cost_opposite_penalty,
                rank_positive_weight=inp.rank_positive_weight,
                utility_correct_reward=inp.utility_correct_reward,
                utility_opposite_penalty=inp.utility_opposite_penalty,
                set_recall_k=inp.set_recall_k,
                safety_margin_opposite_weight=inp.safety_margin_opposite_weight,
                router_shift_weighting=inp.router_shift_weighting,
                router_shift_halflife_batches=inp.router_shift_halflife_batches,
                shift_router_retrieval_upgrade=inp.shift_router_retrieval_upgrade,
                shift_router_retrieval_blend=inp.shift_router_retrieval_blend,
                shift_router_retrieval_pair_weight=inp.shift_router_retrieval_pair_weight,
                shift_router_retrieval_rank_weight=inp.shift_router_retrieval_rank_weight,
                coverage_regularization_target=inp.coverage_regularization_target,
                lookback_batches=int(lb),
                min_train_rows=inp.min_train_rows,
                retrain_every=inp.router_retrain_every,
                seed=inp.seed,
            )
            max_cov, max_active = _candidate_max_active_coverage(
                pred_df=pred_df,
                gate_method=inp.gate_method,
                threshold_grid=inp.activation_threshold_grid,
                rolling_quantile_grid=inp.rolling_quantile_grid,
                rolling_quantile_lookback=inp.rolling_quantile_lookback,
                rolling_quantile_min_history=inp.rolling_quantile_min_history,
                consensus_k_grid=inp.consensus_k_grid,
                use_directional_thresholds=inp.use_directional_thresholds,
                directional_threshold_grid=inp.directional_threshold_grid,
            )
            base_objective_score = float(met["brier"] if inp.objective == "brier" else met["logloss"])
            cov_shortfall = max(0.0, float(inp.coverage_regularization_target) - float(max_cov))
            cov_penalty = float(inp.coverage_regularization_weight) * float(cov_shortfall**2.0)
            selection_score = float(base_objective_score + cov_penalty)
            met = {
                **met,
                "base_objective_score": float(base_objective_score),
                "coverage_shortfall": float(cov_shortfall),
                "coverage_regularization_penalty": float(cov_penalty),
                "coverage_regularization_target": float(inp.coverage_regularization_target),
                "coverage_regularization_weight": float(inp.coverage_regularization_weight),
                "selection_score": float(selection_score),
                "anti_collapse_max_active_coverage": float(max_cov),
                "anti_collapse_max_active_batches": int(max_active),
                "anti_collapse_min_active_coverage_required": float(inp.anti_collapse_min_active_coverage),
                "anti_collapse_pass": bool(max_cov >= inp.anti_collapse_min_active_coverage),
            }
            candidate_rows.append(met)
            candidate_predictions[(model_name, int(lb))] = pred_df
            leak_records_router.extend(recs)
            if inp.verbose:
                print(
                    "[router-candidate] "
                    f"model={model_name} lb={lb} rows={met['rows_scored']} "
                    f"brier={met['brier']:.5f} sel_score={met['selection_score']:.5f} "
                    f"anti_collapse_cov={met['anti_collapse_max_active_coverage']:.4f} "
                    f"pass={met['anti_collapse_pass']}"
                )

    candidate_df = pl.DataFrame(candidate_rows).sort(["model", "lookback"])
    candidate_df.write_csv(out_dir / "global_router_model_selection.csv")

    anti_collapse_pass_rows = [r for r in candidate_rows if bool(r.get("anti_collapse_pass", False))]
    anti_collapse_enforced = bool(len(anti_collapse_pass_rows) > 0)
    best_router = _select_router_candidate(anti_collapse_pass_rows if anti_collapse_enforced else candidate_rows, inp.objective)
    best_key = (str(best_router["model"]), int(best_router["lookback"]))
    if inp.verbose and not anti_collapse_enforced:
        print(
            "[anti-collapse] No router candidate met minimum active coverage; "
            "falling back to unconstrained objective ranking."
        )

    router_train_pred = candidate_predictions[best_key]
    router_hold_pred, hold_leak = _fit_predict_router_holdout(
        router_df=router_tbl,
        train_batches=train_batches,
        holdout_batches=holdout_batches,
        model_name=best_key[0],
        router_target=inp.router_target,
        router_cost_opposite_penalty=inp.router_cost_opposite_penalty,
        rank_positive_weight=inp.rank_positive_weight,
        utility_correct_reward=inp.utility_correct_reward,
        utility_opposite_penalty=inp.utility_opposite_penalty,
        set_recall_k=inp.set_recall_k,
        safety_margin_opposite_weight=inp.safety_margin_opposite_weight,
        router_shift_weighting=inp.router_shift_weighting,
        router_shift_halflife_batches=inp.router_shift_halflife_batches,
        shift_router_retrieval_upgrade=inp.shift_router_retrieval_upgrade,
        shift_router_retrieval_blend=inp.shift_router_retrieval_blend,
        shift_router_retrieval_pair_weight=inp.shift_router_retrieval_pair_weight,
        shift_router_retrieval_rank_weight=inp.shift_router_retrieval_rank_weight,
        coverage_regularization_target=inp.coverage_regularization_target,
        lookback=best_key[1],
        min_train_rows=inp.min_train_rows,
        seed=inp.seed,
    )
    leak_records_router.extend(hold_leak)

    router_cols = [
        "batch_id",
        "action_key",
        "p_hit_router",
        "actual_hit",
        "actual_rank_label",
        "actual_dir_acc",
        "actual_utility_score",
        "actual_selective_binary_label",
        "actual_selective_utility_score",
        "actual_set_recall_label",
        "p_correct_router",
        "p_opposite_router",
        "config_pred_dir",
        "truth_dir",
        "model",
        "lookback",
    ]
    router_all_pred = pl.concat(
        [router_train_pred.select(router_cols), router_hold_pred.select(router_cols)],
        how="vertical_relaxed",
    ).sort(["batch_id", "action_key"])
    router_all_pred.write_parquet(out_dir / "router_selection_by_batch.parquet")
    router_all_pred.write_csv(out_dir / "router_selection_by_batch.csv")

    online_policy_grid_df: pl.DataFrame | None = None
    online_policy_best: dict[str, Any] | None = None
    online_policy_hold_sel: pl.DataFrame | None = None
    online_policy_keys: list[tuple[int, float]] = []
    online_leak_records: list[PredictRecord] = []

    # Phase 3: threshold sweep on train (empirical) or calibration tail (conformal risk).
    sweep_source_pred = router_train_pred
    calibration_batches_used: list[int] = []
    if inp.gate_selection_mode == "conformal_risk":
        max_cal = max(50, len(train_batches) - 100)
        cal_n = min(int(inp.conformal_calibration_batches), max_cal)
        calibration_batches_used = train_batches[-cal_n:]
        sweep_source_pred = router_train_pred.filter(pl.col("batch_id").is_in(calibration_batches_used))
        if sweep_source_pred.height == 0:
            raise RuntimeError("Conformal calibration slice is empty; reduce --conformal-calibration-batches or increase training span.")
        cal_weights = _build_conformal_batch_weights(np.array(calibration_batches_used, dtype=np.int64), inp)
        cal_w_df = pl.DataFrame(
            {
                "batch_id": [int(b) for b in calibration_batches_used],
                "calibration_weight": [float(w) for w in cal_weights.tolist()],
            }
        ).sort("batch_id")
        cal_w_df.write_csv(out_dir / "conformal_calibration_weights_by_batch.csv")

    sweep_rows: list[dict[str, Any]] = []
    for ck in inp.consensus_k_grid:
        if inp.gate_method == "rolling_quantile":
            threshold_pairs = [(float(q), float(q)) for q in inp.rolling_quantile_grid]
        else:
            threshold_pairs = (
                [(float(u), float(d)) for u in inp.directional_threshold_grid for d in inp.directional_threshold_grid]
                if inp.use_directional_thresholds
                else [(float(th), float(th)) for th in inp.activation_threshold_grid]
            )
        for th_up, th_down in threshold_pairs:
            if inp.gate_method == "rolling_quantile":
                sel_train = _selection_by_batch_rolling_quantile(
                    pred_df=sweep_source_pred,
                    prob_col="p_hit_router",
                    quantile=float(th_up),
                    lookback=inp.rolling_quantile_lookback,
                    consensus_k=int(ck),
                    init_history_scores=None,
                    min_history=inp.rolling_quantile_min_history,
                )
            elif inp.use_directional_thresholds:
                sel_train = _selection_by_batch_directional_threshold(
                    sweep_source_pred,
                    prob_col="p_hit_router",
                    threshold_up=float(th_up),
                    threshold_down=float(th_down),
                    consensus_k=int(ck),
                )
            else:
                sel_train = _selection_by_batch(
                    sweep_source_pred,
                    prob_col="p_hit_router",
                    threshold=float(th_up),
                    consensus_k=int(ck),
                )
            m = _metrics_from_selection(sel_train, cadence_min=inp.target_cadence_min, cadence_max=inp.target_cadence_max)
            cstats = _conformal_risk_stats(sel_train, inp)

            if inp.gate_selection_mode == "conformal_risk":
                feasible, vscore, vparts = _score_operating_point_conformal(
                    m,
                    inp,
                    opposite_fp_rate_active_ucb=float(cstats["opp_active_ucb"]),
                    opposite_fp_rate_covered_ucb=float(cstats["opp_covered_ucb"]),
                    safe_accuracy_lcb=float(cstats["safe_acc_lcb"]),
                )
            else:
                feasible, vscore, vparts = _score_operating_point(m, inp)
            sweep_rows.append(
                {
                    "consensus_k": int(ck),
                    "activation_threshold": float(0.5 * (th_up + th_down)),
                    "activation_threshold_up": float(th_up),
                    "activation_threshold_down": float(th_down),
                    "gate_method": inp.gate_method,
                    "rolling_quantile": (float(th_up) if inp.gate_method == "rolling_quantile" else None),
                    "rolling_quantile_lookback": (int(inp.rolling_quantile_lookback) if inp.gate_method == "rolling_quantile" else None),
                    "selection_mode": inp.gate_selection_mode,
                    "selection_batches": int(m["batch_count"]),
                    **m,
                    "opp_active_ucb": float(cstats["opp_active_ucb"]),
                    "opp_covered_ucb": float(cstats["opp_covered_ucb"]),
                    "safe_acc_lcb": float(cstats["safe_acc_lcb"]),
                    "opp_active_weighted_hat": float(cstats["opp_active_hat"]),
                    "opp_covered_weighted_hat": float(cstats["opp_covered_hat"]),
                    "safe_acc_weighted_hat": float(cstats["safe_acc_hat"]),
                    "n_eff_total": float(cstats["n_eff_total"]),
                    "n_eff_active": float(cstats["n_eff_active"]),
                    "n_eff_up": float(cstats["n_eff_up"]),
                    "n_eff_down": float(cstats["n_eff_down"]),
                    "class_up_opp_ucb": float(cstats["class_up_opp_ucb"]),
                    "class_down_opp_ucb": float(cstats["class_down_opp_ucb"]),
                    "class_up_cov_ucb": float(cstats["class_up_cov_ucb"]),
                    "class_down_cov_ucb": float(cstats["class_down_cov_ucb"]),
                    "conformal_delta": float(inp.conformal_delta),
                    "conformal_class_conditional": bool(inp.conformal_class_conditional),
                    "conformal_shift_weighting": inp.conformal_shift_weighting,
                    "feasible": bool(feasible),
                    "violation_score": float(vscore),
                    "viol_opp_active": float(vparts["opp_active"]),
                    "viol_opp_covered": float(vparts["opp_covered"]),
                    "viol_safe_acc": float(vparts["safe_acc"]),
                    "viol_cadence": float(vparts["cadence"]),
                    "viol_coverage": float(vparts["coverage"]),
                }
            )

    sweep_df = pl.DataFrame(sweep_rows).sort(["consensus_k", "activation_threshold"])
    sweep_df.write_parquet(out_dir / "router_threshold_sweep.parquet")
    sweep_df.write_csv(out_dir / "router_threshold_sweep.csv")

    conformal_report = {
        "gate_selection_mode": inp.gate_selection_mode,
        "conformal_delta": inp.conformal_delta,
        "conformal_calibration_batches_requested": inp.conformal_calibration_batches,
        "conformal_calibration_batches_used": len(calibration_batches_used),
        "conformal_calibration_batch_id_first": int(min(calibration_batches_used)) if calibration_batches_used else None,
        "conformal_calibration_batch_id_last": int(max(calibration_batches_used)) if calibration_batches_used else None,
        "conformal_class_conditional": bool(inp.conformal_class_conditional),
        "conformal_shift_weighting": inp.conformal_shift_weighting,
        "conformal_decay_halflife_batches": inp.conformal_decay_halflife_batches,
    }
    (out_dir / "conformal_gate_calibration.json").write_text(json.dumps(conformal_report, indent=2), encoding="utf-8")

    op = _pick_operating_point(sweep_rows, inp)
    if inp.use_online_policy_pool:
        selection_batches_for_online = (
            list(calibration_batches_used)
            if calibration_batches_used
            else sorted(sweep_source_pred["batch_id"].unique().to_list())
        )
        if len(selection_batches_for_online) >= (inp.online_policy_min_warmup_batches + 25):
            policy_rank_rows = sorted(
                sweep_rows,
                key=lambda r: (
                    r["violation_score"],
                    -r["directional_active_safe_accuracy"],
                    r["opposite_fp_rate_active"],
                    r["opposite_fp_rate_covered"],
                    -r["active_batches"],
                    -int(r["consensus_k"]),
                    r["activation_threshold"],
                ),
            )
            min_active_for_pool = max(
                5,
                int(round(len(selection_batches_for_online) / max(1.0, float(inp.target_cadence_max * 2.0)))),
            )
            active_filtered = [r for r in policy_rank_rows if int(r.get("active_batches", 0)) >= min_active_for_pool]
            if active_filtered:
                policy_rank_rows = active_filtered
            ordered_policy_keys = []
            seen_policy_keys = set()
            for r in policy_rank_rows:
                key = (int(r["consensus_k"]), float(r["activation_threshold"]))
                if key not in seen_policy_keys:
                    ordered_policy_keys.append(key)
                    seen_policy_keys.add(key)

            policy_cache = _build_policy_cache(router_all_pred, ordered_policy_keys)
            warmup_n = max(
                int(len(selection_batches_for_online) * inp.online_policy_warmup_frac),
                int(inp.online_policy_min_warmup_batches),
            )
            warmup_n = min(max(1, warmup_n), len(selection_batches_for_online) - 1)
            warmup_batches = selection_batches_for_online[:warmup_n]
            tune_batches = selection_batches_for_online[warmup_n:]

            pool_rows: list[dict[str, Any]] = []
            for topn in inp.online_policy_topn_grid:
                n_use = int(min(topn, len(ordered_policy_keys)))
                if n_use <= 0:
                    continue
                candidate_keys = ordered_policy_keys[:n_use]
                for eta in inp.online_policy_eta_grid:
                    for hold_loss in inp.online_policy_hold_loss_grid:
                        sel_tune, _ = _run_online_policy_pool(
                            policy_cache=policy_cache,
                            policy_keys=candidate_keys,
                            warmup_batches=warmup_batches,
                            eval_batches=tune_batches,
                            eta=float(eta),
                            hold_loss=float(hold_loss),
                            source_tag="online_policy_tune",
                        )
                        if sel_tune.height == 0:
                            continue
                        m = _metrics_from_selection(sel_tune, cadence_min=inp.target_cadence_min, cadence_max=inp.target_cadence_max)
                        cstats = _conformal_risk_stats(sel_tune, inp)
                        if inp.gate_selection_mode == "conformal_risk":
                            feasible, vscore, vparts = _score_operating_point_conformal(
                                m,
                                inp,
                                opposite_fp_rate_active_ucb=float(cstats["opp_active_ucb"]),
                                opposite_fp_rate_covered_ucb=float(cstats["opp_covered_ucb"]),
                                safe_accuracy_lcb=float(cstats["safe_acc_lcb"]),
                            )
                        else:
                            feasible, vscore, vparts = _score_operating_point(m, inp)
                        pool_rows.append(
                            {
                                "pool_topn": int(n_use),
                                "policy_eta": float(eta),
                                "policy_hold_loss": float(hold_loss),
                                "selection_mode": "online_policy_pool",
                                "selection_batches": int(m["batch_count"]),
                                **m,
                                "opp_active_ucb": float(cstats["opp_active_ucb"]),
                                "opp_covered_ucb": float(cstats["opp_covered_ucb"]),
                                "safe_acc_lcb": float(cstats["safe_acc_lcb"]),
                                "opp_active_weighted_hat": float(cstats["opp_active_hat"]),
                                "opp_covered_weighted_hat": float(cstats["opp_covered_hat"]),
                                "safe_acc_weighted_hat": float(cstats["safe_acc_hat"]),
                                "n_eff_total": float(cstats["n_eff_total"]),
                                "n_eff_active": float(cstats["n_eff_active"]),
                                "n_eff_up": float(cstats["n_eff_up"]),
                                "n_eff_down": float(cstats["n_eff_down"]),
                                "feasible": bool(feasible),
                                "violation_score": float(vscore),
                                "viol_opp_active": float(vparts["opp_active"]),
                                "viol_opp_covered": float(vparts["opp_covered"]),
                                "viol_safe_acc": float(vparts["safe_acc"]),
                                "viol_cadence": float(vparts["cadence"]),
                                "viol_coverage": float(vparts["coverage"]),
                            }
                        )

            if pool_rows:
                online_policy_grid_df = pl.DataFrame(pool_rows).sort(["pool_topn", "policy_eta", "policy_hold_loss"])
                online_policy_grid_df.write_parquet(out_dir / "online_policy_pool_grid.parquet")
                online_policy_grid_df.write_csv(out_dir / "online_policy_pool_grid.csv")

                online_policy_best = _pick_operating_point(pool_rows, inp)
                n_use = int(online_policy_best["pool_topn"])
                online_policy_keys = ordered_policy_keys[:n_use]
                online_policy_hold_sel, online_leak_records = _run_online_policy_pool(
                    policy_cache=policy_cache,
                    policy_keys=online_policy_keys,
                    warmup_batches=selection_batches_for_online,
                    eval_batches=holdout_batches,
                    eta=float(online_policy_best["policy_eta"]),
                    hold_loss=float(online_policy_best["policy_hold_loss"]),
                    source_tag="online_policy_holdout",
                )
                if online_policy_hold_sel.height > 0:
                    online_policy_hold_sel.write_parquet(out_dir / "online_policy_pool_holdout_selection.parquet")
                    online_policy_hold_sel.write_csv(out_dir / "online_policy_pool_holdout_selection.csv")

                op = {
                    **online_policy_best,
                    "selection_mode": "online_policy_pool",
                    "router_model": best_key[0],
                    "router_lookback": int(best_key[1]),
                    "pool_policy_count": int(len(online_policy_keys)),
                    "pool_policy_keys": [
                        {"consensus_k": int(k), "activation_threshold": float(th)}
                        for k, th in online_policy_keys
                    ],
                }

    (out_dir / "final_operating_point.json").write_text(json.dumps(op, indent=2), encoding="utf-8")

    # Phase 4: holdout gate
    hold_metrics: dict[str, Any]
    if holdout_batches:
        if inp.use_online_policy_pool and online_policy_hold_sel is not None and online_policy_hold_sel.height > 0:
            sel_hold = online_policy_hold_sel.select(["batch_id", "pred_dir", "truth_dir", "consensus_k", "activation_threshold"])
        else:
            if inp.gate_method == "rolling_quantile":
                train_base = _build_batch_selection_base(
                    pred_df=sweep_source_pred,
                    prob_col="p_hit_router",
                    consensus_k=int(op.get("consensus_k", 1)),
                )
                init_hist = (
                    train_base
                    .filter(pl.col("consensus_ok"))
                    .select("selected_p_hit")
                    .to_series()
                    .to_list()
                )
                sel_hold = _selection_by_batch_rolling_quantile(
                    pred_df=router_hold_pred,
                    prob_col="p_hit_router",
                    quantile=float(op.get("rolling_quantile", op["activation_threshold"])),
                    lookback=int(inp.rolling_quantile_lookback),
                    consensus_k=int(op.get("consensus_k", 1)),
                    init_history_scores=[float(x) for x in init_hist if x is not None and np.isfinite(x)],
                    min_history=int(inp.rolling_quantile_min_history),
                )
            elif inp.use_directional_thresholds:
                sel_hold = _selection_by_batch_directional_threshold(
                    router_hold_pred,
                    prob_col="p_hit_router",
                    threshold_up=float(op.get("activation_threshold_up", op["activation_threshold"])),
                    threshold_down=float(op.get("activation_threshold_down", op["activation_threshold"])),
                    consensus_k=int(op.get("consensus_k", 1)),
                )
            else:
                sel_hold = _selection_by_batch(
                    router_hold_pred,
                    prob_col="p_hit_router",
                    threshold=float(op["activation_threshold"]),
                    consensus_k=int(op.get("consensus_k", 1)),
                )
        hold_metrics = _metrics_from_selection(sel_hold, cadence_min=inp.target_cadence_min, cadence_max=inp.target_cadence_max)
        hold_cstats = _conformal_risk_stats(sel_hold, inp)
        if inp.gate_selection_mode == "conformal_risk":
            pass_hold, vscore_hold, vparts_hold = _score_operating_point_conformal(
                hold_metrics,
                inp,
                opposite_fp_rate_active_ucb=float(hold_cstats["opp_active_ucb"]),
                opposite_fp_rate_covered_ucb=float(hold_cstats["opp_covered_ucb"]),
                safe_accuracy_lcb=float(hold_cstats["safe_acc_lcb"]),
            )
        else:
            pass_hold, vscore_hold, vparts_hold = _score_operating_point(hold_metrics, inp)
        hold_metrics = {
            **hold_metrics,
            "pass_production_gate": bool(pass_hold),
            "violation_score": float(vscore_hold),
            "viol_opp_active": float(vparts_hold["opp_active"]),
            "viol_opp_covered": float(vparts_hold["opp_covered"]),
            "viol_safe_acc": float(vparts_hold["safe_acc"]),
            "viol_cadence": float(vparts_hold["cadence"]),
            "viol_coverage": float(vparts_hold["coverage"]),
            "opp_active_ucb": float(hold_cstats["opp_active_ucb"]),
            "opp_covered_ucb": float(hold_cstats["opp_covered_ucb"]),
            "safe_acc_lcb": float(hold_cstats["safe_acc_lcb"]),
            "opp_active_weighted_hat": float(hold_cstats["opp_active_hat"]),
            "opp_covered_weighted_hat": float(hold_cstats["opp_covered_hat"]),
            "safe_acc_weighted_hat": float(hold_cstats["safe_acc_hat"]),
            "n_eff_total": float(hold_cstats["n_eff_total"]),
            "n_eff_active": float(hold_cstats["n_eff_active"]),
            "n_eff_up": float(hold_cstats["n_eff_up"]),
            "n_eff_down": float(hold_cstats["n_eff_down"]),
            "activation_threshold": (
                float(op["activation_threshold"]) if "activation_threshold" in op else None
            ),
            "activation_threshold_up": (
                float(op["activation_threshold_up"]) if "activation_threshold_up" in op else None
            ),
            "activation_threshold_down": (
                float(op["activation_threshold_down"]) if "activation_threshold_down" in op else None
            ),
            "rolling_quantile": (
                float(op["rolling_quantile"]) if "rolling_quantile" in op and op["rolling_quantile"] is not None else None
            ),
            "rolling_quantile_lookback": int(inp.rolling_quantile_lookback) if inp.gate_method == "rolling_quantile" else None,
            "consensus_k": int(op["consensus_k"]) if "consensus_k" in op else None,
            "router_model": best_key[0],
            "router_lookback": int(best_key[1]),
            "gate_selection_mode": inp.gate_selection_mode,
            "gate_method": inp.gate_method,
            "selection_objective": inp.selection_objective,
            "conformal_delta": float(inp.conformal_delta),
            "conformal_class_conditional": bool(inp.conformal_class_conditional),
            "conformal_shift_weighting": inp.conformal_shift_weighting,
            "selection_mode": str(op.get("selection_mode", "threshold")),
        }
        if inp.use_online_policy_pool and online_policy_best is not None:
            hold_metrics["policy_eta"] = float(online_policy_best["policy_eta"])
            hold_metrics["policy_hold_loss"] = float(online_policy_best["policy_hold_loss"])
            hold_metrics["policy_pool_size"] = int(online_policy_best["pool_topn"])
    else:
        hold_metrics = {
            "pass_production_gate": False,
            "reason": "no_holdout_batches",
        }

    (out_dir / "holdout_metrics.json").write_text(json.dumps(hold_metrics, indent=2), encoding="utf-8")

    # Phase 5: baselines
    train_df = df.filter(pl.col("batch_id").is_in(train_batches)).sort(["batch_id", "action_key"])
    hold_df = df.filter(pl.col("batch_id").is_in(holdout_batches)).sort(["batch_id", "action_key"])

    if hold_df.height > 0:
        fixed_tbl = (
            train_df.group_by("action_key")
            .agg(pl.col("hit").mean().alias("hit_rate"))
            .sort(["hit_rate", "action_key"], descending=[True, False])
        )
        fixed_cfg = str(fixed_tbl.row(0)[0]) if fixed_tbl.height > 0 else None
    else:
        fixed_cfg = None

    fixed_metrics = None
    if fixed_cfg is not None:
        fixed_sel = hold_df.filter(pl.col("action_key") == str(fixed_cfg)).select(["batch_id", "config_pred_dir", "truth_dir"]).rename(
            {"config_pred_dir": "pred_dir"}
        )
        fixed_metrics = _metrics_from_selection(fixed_sel, cadence_min=inp.target_cadence_min, cadence_max=inp.target_cadence_max)
        fixed_metrics["selected_action_key"] = str(fixed_cfg)

    # Existing per-config-only router baseline with its own threshold on train.
    per_train_pred = per_pred.filter(pl.col("batch_id").is_in(train_batches) & pl.col("p_hit").is_not_null())
    per_hold_pred = per_pred.filter(pl.col("batch_id").is_in(holdout_batches) & pl.col("p_hit").is_not_null())

    per_sweep = []
    for th in inp.activation_threshold_grid:
        sel = _selection_by_batch(
            per_train_pred.rename({"p_hit": "p_hit_router"}),
            prob_col="p_hit_router",
            threshold=float(th),
            consensus_k=1,
        )
        m = _metrics_from_selection(sel, cadence_min=inp.target_cadence_min, cadence_max=inp.target_cadence_max)
        feasible, vscore, _ = _score_operating_point(m, inp)
        per_sweep.append({"consensus_k": 1, "activation_threshold": float(th), **m, "feasible": bool(feasible), "violation_score": float(vscore)})
    per_op = _pick_operating_point(per_sweep, inp)

    per_hold_metrics = None
    if per_hold_pred.height > 0:
        sel = _selection_by_batch(
            per_hold_pred.rename({"p_hit": "p_hit_router"}),
            prob_col="p_hit_router",
            threshold=float(per_op["activation_threshold"]),
            consensus_k=1,
        )
        per_hold_metrics = _metrics_from_selection(sel, cadence_min=inp.target_cadence_min, cadence_max=inp.target_cadence_max)
        per_hold_metrics["activation_threshold"] = float(per_op["activation_threshold"])
        per_hold_metrics["consensus_k"] = int(per_op.get("consensus_k", 1))

    strict_ctx = _extract_context_metrics(inp.strict_context_summary)
    dual_ctx = _extract_context_metrics(inp.dual_context_summary)

    # leakage report
    leak_cfg = _build_leakage_report(leak_records_cfg)
    leak_router = _build_leakage_report(leak_records_router)
    leak_online = _build_leakage_report(online_leak_records) if online_leak_records else {"checks": 0, "violations": 0, "pass": True, "first_violations": []}
    leak_report = {
        "per_config": leak_cfg,
        "global_router": leak_router,
        "online_policy_pool": leak_online,
        "pass": bool(leak_cfg["pass"] and leak_router["pass"] and leak_online["pass"]),
    }
    (out_dir / "leakage_guard_report.json").write_text(json.dumps(leak_report, indent=2), encoding="utf-8")

    # summary
    comparison = {}
    if isinstance(hold_metrics, dict) and "directional_active_safe_accuracy" in hold_metrics:
        if isinstance(fixed_metrics, dict):
            comparison["vs_fixed_best_config"] = {
                "safe_accuracy_delta": float(hold_metrics["directional_active_safe_accuracy"] - fixed_metrics["directional_active_safe_accuracy"]),
                "opposite_fp_active_delta": float(hold_metrics["opposite_fp_rate_active"] - fixed_metrics["opposite_fp_rate_active"]),
                "opposite_fp_covered_delta": float(hold_metrics["opposite_fp_rate_covered"] - fixed_metrics["opposite_fp_rate_covered"]),
                "cadence_delta": float(hold_metrics["batches_per_signal"] - fixed_metrics["batches_per_signal"]),
                "active_batches_delta": int(hold_metrics["active_batches"] - fixed_metrics["active_batches"]),
            }
        if isinstance(per_hold_metrics, dict):
            comparison["vs_per_config_router"] = {
                "safe_accuracy_delta": float(hold_metrics["directional_active_safe_accuracy"] - per_hold_metrics["directional_active_safe_accuracy"]),
                "opposite_fp_active_delta": float(hold_metrics["opposite_fp_rate_active"] - per_hold_metrics["opposite_fp_rate_active"]),
                "opposite_fp_covered_delta": float(hold_metrics["opposite_fp_rate_covered"] - per_hold_metrics["opposite_fp_rate_covered"]),
                "cadence_delta": float(hold_metrics["batches_per_signal"] - per_hold_metrics["batches_per_signal"]),
                "active_batches_delta": int(hold_metrics["active_batches"] - per_hold_metrics["active_batches"]),
            }

    summary = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "ok" if hold_metrics.get("pass_production_gate", False) else "not_production_ready",
        "mode": inp.mode,
        "inputs": {
            "mode": inp.mode,
            "unit_dir": str(inp.unit_dir),
            "batches_tail": int(inp.batches_tail),
            "max_batches": int(inp.max_batches),
            "holdout_batches": int(inp.holdout_batches),
            "lookback_grid": [int(x) for x in inp.lookback_grid],
            "router_lookback_grid": [int(x) for x in inp.router_lookback_grid],
            "router_models": list(inp.router_models),
            "consensus_k_grid": [int(x) for x in inp.consensus_k_grid],
            "set_recall_k": int(inp.set_recall_k),
            "gate_selection_mode": inp.gate_selection_mode,
            "conformal_delta": inp.conformal_delta,
            "conformal_calibration_batches": inp.conformal_calibration_batches,
            "conformal_class_conditional": inp.conformal_class_conditional,
            "conformal_shift_weighting": inp.conformal_shift_weighting,
            "conformal_decay_halflife_batches": inp.conformal_decay_halflife_batches,
            "router_target": inp.router_target,
            "router_cost_opposite_penalty": inp.router_cost_opposite_penalty,
            "rank_positive_weight": inp.rank_positive_weight,
            "utility_correct_reward": inp.utility_correct_reward,
            "utility_opposite_penalty": inp.utility_opposite_penalty,
            "selective_hold_cost": inp.selective_hold_cost,
            "safety_margin_opposite_weight": inp.safety_margin_opposite_weight,
            "router_shift_weighting": inp.router_shift_weighting,
            "router_shift_halflife_batches": inp.router_shift_halflife_batches,
            "shift_router_retrieval_upgrade": inp.shift_router_retrieval_upgrade,
            "shift_router_retrieval_blend": inp.shift_router_retrieval_blend,
            "shift_router_retrieval_pair_weight": inp.shift_router_retrieval_pair_weight,
            "shift_router_retrieval_rank_weight": inp.shift_router_retrieval_rank_weight,
            "coverage_regularization_target": inp.coverage_regularization_target,
            "coverage_regularization_weight": inp.coverage_regularization_weight,
            "anti_collapse_min_active_coverage": inp.anti_collapse_min_active_coverage,
            "use_online_policy_pool": inp.use_online_policy_pool,
            "online_policy_eta_grid": [float(x) for x in inp.online_policy_eta_grid],
            "online_policy_hold_loss_grid": [float(x) for x in inp.online_policy_hold_loss_grid],
            "online_policy_topn_grid": [int(x) for x in inp.online_policy_topn_grid],
            "online_policy_warmup_frac": inp.online_policy_warmup_frac,
            "online_policy_min_warmup_batches": inp.online_policy_min_warmup_batches,
            "objective": inp.objective,
            "activation_threshold_grid": [float(x) for x in inp.activation_threshold_grid],
            "use_directional_thresholds": inp.use_directional_thresholds,
            "directional_threshold_grid": [float(x) for x in inp.directional_threshold_grid],
            "gate_method": inp.gate_method,
            "rolling_quantile_grid": [float(x) for x in inp.rolling_quantile_grid],
            "rolling_quantile_lookback": inp.rolling_quantile_lookback,
            "rolling_quantile_min_history": inp.rolling_quantile_min_history,
            "selection_objective": inp.selection_objective,
            "compat_mode": inp.compat_mode,
            "primal_dual_iters": inp.primal_dual_iters,
            "primal_dual_step": inp.primal_dual_step,
            "primal_dual_utility_mode": inp.primal_dual_utility_mode,
            "constraints": {
                "target_cadence_min": inp.target_cadence_min,
                "target_cadence_max": inp.target_cadence_max,
                "coverage_selection_min": inp.coverage_selection_min,
                "coverage_selection_max": inp.coverage_selection_max,
                "max_opposite_fp_active": inp.max_opposite_fp_active,
                "max_opposite_fp_covered": inp.max_opposite_fp_covered,
                "min_safe_accuracy": inp.min_safe_accuracy,
            },
        },
        "dataset_contract": contract,
        "counts": {
            "batches_total": len(all_batches),
            "batches_train": len(train_batches),
            "batches_holdout": len(holdout_batches),
            "configs": int(df["action_key"].n_unique()),
            "router_train_rows_scored": int(router_train_pred.height),
            "router_holdout_rows_scored": int(router_hold_pred.height),
        },
        "selected_router_candidate": best_router,
        "router_candidate_selection": {
            "anti_collapse_constraint_enforced": bool(anti_collapse_enforced),
            "anti_collapse_min_active_coverage": float(inp.anti_collapse_min_active_coverage),
            "anti_collapse_candidates_passing": int(len(anti_collapse_pass_rows)),
            "anti_collapse_candidates_total": int(len(candidate_rows)),
            "coverage_regularization_target": float(inp.coverage_regularization_target),
            "coverage_regularization_weight": float(inp.coverage_regularization_weight),
            "selection_objective": inp.selection_objective,
            "compat_mode": inp.compat_mode,
        },
        "final_operating_point": op,
        "holdout_metrics": hold_metrics,
        "baseline_fixed_best_config": fixed_metrics,
        "baseline_per_config_router": per_hold_metrics,
        "comparison_deltas": comparison,
        "context_reference": {
            "strict_summary": strict_ctx,
            "dual_summary": dual_ctx,
        },
        "leakage_checks": leak_report,
        "artifacts": {
            "dataset_contract_json": str((out_dir / "dataset_contract.json").resolve()),
            "per_config_lookback_scores_csv": str((out_dir / "per_config_lookback_scores.csv").resolve()),
            "selected_lookback_by_config_csv": str((out_dir / "selected_lookback_by_config.csv").resolve()),
            "global_router_model_selection_csv": str((out_dir / "global_router_model_selection.csv").resolve()),
            "router_selection_by_batch_parquet": str((out_dir / "router_selection_by_batch.parquet").resolve()),
            "router_threshold_sweep_csv": str((out_dir / "router_threshold_sweep.csv").resolve()),
            "online_policy_pool_grid_csv": (
                str((out_dir / "online_policy_pool_grid.csv").resolve())
                if (out_dir / "online_policy_pool_grid.csv").exists()
                else None
            ),
            "online_policy_pool_holdout_selection_csv": (
                str((out_dir / "online_policy_pool_holdout_selection.csv").resolve())
                if (out_dir / "online_policy_pool_holdout_selection.csv").exists()
                else None
            ),
            "conformal_gate_calibration_json": str((out_dir / "conformal_gate_calibration.json").resolve()),
            "conformal_calibration_weights_csv": (
                str((out_dir / "conformal_calibration_weights_by_batch.csv").resolve())
                if (out_dir / "conformal_calibration_weights_by_batch.csv").exists()
                else None
            ),
            "final_operating_point_json": str((out_dir / "final_operating_point.json").resolve()),
            "holdout_metrics_json": str((out_dir / "holdout_metrics.json").resolve()),
            "leakage_guard_report_json": str((out_dir / "leakage_guard_report.json").resolve()),
            "summary_json": str((out_dir / "summary.json").resolve()),
        },
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    tracking_context = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "linear_issue_url": inp.linear_issue_url,
        "notion_page_url": inp.notion_page_url,
        "run_command": " ".join(sys.argv),
        "git_commit_hash": _git_commit_hash(inp.project_root),
    }
    (out_dir / "tracking_context.json").write_text(json.dumps(tracking_context, indent=2), encoding="utf-8")

    print(f"Done. Output: {out_dir.resolve()}")
    print(json.dumps({"status": summary["status"], "holdout_metrics": hold_metrics}, indent=2))


if __name__ == "__main__":
    main()
