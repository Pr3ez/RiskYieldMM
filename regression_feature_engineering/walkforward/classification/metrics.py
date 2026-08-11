"""Decision-first metrics and threshold selection for RPF classification."""

from __future__ import annotations

import math
from typing import Any

import numpy as np


DECISION_POLICY_THRESHOLD_ONLY = "threshold_only"
DECISION_POLICY_CAUSAL_SIGNAL_BUDGET = "causal_signal_budget"
DECISION_POLICY_BATCH_TOPK_OFFLINE = "batch_topk_offline"
DECISION_POLICIES = (
    DECISION_POLICY_THRESHOLD_ONLY,
    DECISION_POLICY_CAUSAL_SIGNAL_BUDGET,
    DECISION_POLICY_BATCH_TOPK_OFFLINE,
)
LIVE_SAFE_DECISION_POLICIES = (
    DECISION_POLICY_THRESHOLD_ONLY,
    DECISION_POLICY_CAUSAL_SIGNAL_BUDGET,
)


def binary_metrics(
    y_true: np.ndarray,
    prob: np.ndarray,
    *,
    threshold: float = 0.5,
    fp_cost: float = 1.0,
    fn_cost: float = 1.0,
    tp_reward: float = 0.0,
    fbeta_beta: float = 1.0,
) -> dict[str, Any]:
    y_true = np.asarray(y_true, dtype=int)
    prob = np.asarray(prob, dtype=float)
    mask = np.isfinite(prob)
    y_true = y_true[mask]
    prob = np.clip(prob[mask], 1e-9, 1.0 - 1e-9)
    pred = (prob >= float(threshold)).astype(int)
    positives = y_true == 1
    negatives = y_true == 0
    tp = int(np.sum((pred == 1) & positives))
    tn = int(np.sum((pred == 0) & negatives))
    fp = int(np.sum((pred == 1) & negatives))
    fn = int(np.sum((pred == 0) & positives))
    tpr = safe_div(tp, tp + fn)
    tnr = safe_div(tn, tn + fp)
    precision = safe_div(tp, tp + fp)
    recall = tpr
    f1 = None if precision is None or recall is None or precision + recall == 0 else float(2 * precision * recall / (precision + recall))
    beta_sq = float(fbeta_beta) ** 2
    fbeta = (
        None
        if precision is None or recall is None or (beta_sq * precision + recall) == 0
        else float((1.0 + beta_sq) * precision * recall / (beta_sq * precision + recall))
    )
    false_positive_rate = safe_div(fp, fp + tn)
    false_negative_rate = safe_div(fn, fn + tp)
    false_discovery_rate = safe_div(fp, fp + tp)
    positive_rate = float(np.mean(y_true)) if len(y_true) else None
    signal_count = int(tp + fp)
    precision_lift = None if precision is None or positive_rate in (None, 0.0) else float(precision / positive_rate)
    decision_cost = float(fp_cost * fp + fn_cost * fn - tp_reward * tp)
    decision_cost_per_row = None if len(y_true) == 0 else float(decision_cost / len(y_true))
    utility = float(tp_reward * tp - fp_cost * fp - fn_cost * fn)
    return {
        "rows": int(len(y_true)),
        "threshold": float(threshold),
        "positive_rate": positive_rate,
        "predicted_positive_rate": float(np.mean(pred)) if len(pred) else None,
        "signal_count": signal_count,
        "prob_mean": float(np.mean(prob)) if len(prob) else None,
        "prob_std": float(np.std(prob)) if len(prob) else None,
        "prob_unique": int(len(np.unique(np.round(prob, 8)))) if len(prob) else 0,
        "accuracy": float(np.mean(pred == y_true)) if len(y_true) else None,
        "balanced_accuracy": None if tpr is None or tnr is None else float((tpr + tnr) / 2.0),
        "precision": precision,
        "precision_lift": precision_lift,
        "recall": recall,
        "f1": f1,
        "fbeta": fbeta,
        "mcc": matthews_corrcoef(tp=tp, tn=tn, fp=fp, fn=fn),
        "false_positive_rate": false_positive_rate,
        "false_negative_rate": false_negative_rate,
        "false_discovery_rate": false_discovery_rate,
        "specificity": tnr,
        "decision_cost": decision_cost,
        "decision_cost_per_row": decision_cost_per_row,
        "utility": utility,
        "utility_per_row": None if len(y_true) == 0 else float(utility / len(y_true)),
        "logloss": float(-np.mean(y_true * np.log(prob) + (1 - y_true) * np.log(1 - prob))) if len(y_true) else None,
        "brier": float(np.mean((prob - y_true) ** 2)) if len(y_true) else None,
        "auc": auc_rank(y_true, prob),
        "pr_auc": pr_auc_average_precision(y_true, prob),
        "tp": tp,
        "tn": tn,
        "fp": fp,
        "fn": fn,
    }


def binary_metrics_from_predictions(
    y_true: np.ndarray,
    prob: np.ndarray,
    pred: np.ndarray,
    *,
    threshold: float | None,
    fp_cost: float = 1.0,
    fn_cost: float = 1.0,
    tp_reward: float = 0.0,
    fbeta_beta: float = 1.0,
) -> dict[str, Any]:
    y_true = np.asarray(y_true, dtype=int)
    prob = np.asarray(prob, dtype=float)
    pred = np.asarray(pred, dtype=int)
    mask = np.isfinite(prob)
    y_true = y_true[mask]
    prob = np.clip(prob[mask], 1e-9, 1.0 - 1e-9)
    pred = pred[mask]
    positives = y_true == 1
    negatives = y_true == 0
    tp = int(np.sum((pred == 1) & positives))
    tn = int(np.sum((pred == 0) & negatives))
    fp = int(np.sum((pred == 1) & negatives))
    fn = int(np.sum((pred == 0) & positives))
    tpr = safe_div(tp, tp + fn)
    tnr = safe_div(tn, tn + fp)
    precision = safe_div(tp, tp + fp)
    recall = tpr
    f1 = None if precision is None or recall is None or precision + recall == 0 else float(2 * precision * recall / (precision + recall))
    beta_sq = float(fbeta_beta) ** 2
    fbeta = (
        None
        if precision is None or recall is None or (beta_sq * precision + recall) == 0
        else float((1.0 + beta_sq) * precision * recall / (beta_sq * precision + recall))
    )
    false_positive_rate = safe_div(fp, fp + tn)
    false_negative_rate = safe_div(fn, fn + tp)
    false_discovery_rate = safe_div(fp, fp + tp)
    positive_rate = float(np.mean(y_true)) if len(y_true) else None
    signal_count = int(tp + fp)
    precision_lift = None if precision is None or positive_rate in (None, 0.0) else float(precision / positive_rate)
    decision_cost = float(fp_cost * fp + fn_cost * fn - tp_reward * tp)
    utility = float(tp_reward * tp - fp_cost * fp - fn_cost * fn)
    return {
        "rows": int(len(y_true)),
        "threshold": threshold,
        "positive_rate": positive_rate,
        "predicted_positive_rate": float(np.mean(pred)) if len(pred) else None,
        "signal_count": signal_count,
        "prob_mean": float(np.mean(prob)) if len(prob) else None,
        "prob_std": float(np.std(prob)) if len(prob) else None,
        "prob_unique": int(len(np.unique(np.round(prob, 8)))) if len(prob) else 0,
        "accuracy": float(np.mean(pred == y_true)) if len(y_true) else None,
        "balanced_accuracy": None if tpr is None or tnr is None else float((tpr + tnr) / 2.0),
        "precision": precision,
        "precision_lift": precision_lift,
        "recall": recall,
        "f1": f1,
        "fbeta": fbeta,
        "mcc": matthews_corrcoef(tp=tp, tn=tn, fp=fp, fn=fn),
        "false_positive_rate": false_positive_rate,
        "false_negative_rate": false_negative_rate,
        "false_discovery_rate": false_discovery_rate,
        "specificity": tnr,
        "decision_cost": decision_cost,
        "decision_cost_per_row": None if len(y_true) == 0 else float(decision_cost / len(y_true)),
        "utility": utility,
        "utility_per_row": None if len(y_true) == 0 else float(utility / len(y_true)),
        "logloss": float(-np.mean(y_true * np.log(prob) + (1 - y_true) * np.log(1 - prob))) if len(y_true) else None,
        "brier": float(np.mean((prob - y_true) ** 2)) if len(y_true) else None,
        "auc": auc_rank(y_true, prob),
        "pr_auc": pr_auc_average_precision(y_true, prob),
        "tp": tp,
        "tn": tn,
        "fp": fp,
        "fn": fn,
    }


def select_decision_threshold(
    y_true: np.ndarray,
    prob: np.ndarray,
    *,
    threshold_mode: str,
    fixed_threshold: float,
    threshold_grid: tuple[float, ...],
    objective_metric: str,
    fp_cost: float,
    fn_cost: float,
    tp_reward: float,
    fbeta_beta: float,
    min_recall: float,
    min_precision: float,
    min_predicted_positive_rate: float,
    max_false_positive_rate: float,
    max_signals_grid: tuple[int, ...] = (0,),
    decision_policy: str = DECISION_POLICY_THRESHOLD_ONLY,
) -> dict[str, Any]:
    decision_policy = validate_decision_policy(decision_policy)
    live_safe = is_live_safe_decision_policy(decision_policy)
    signal_grid = decision_policy_max_signals_grid(decision_policy, max_signals_grid)
    if threshold_mode == "fixed":
        max_signals = signal_grid[0]
        pred = signal_predictions(
            prob,
            threshold=float(fixed_threshold),
            max_signals=max_signals,
            decision_policy=decision_policy,
        )
        metrics = binary_metrics_from_predictions(
            y_true,
            prob,
            pred,
            threshold=float(fixed_threshold),
            fp_cost=fp_cost,
            fn_cost=fn_cost,
            tp_reward=tp_reward,
            fbeta_beta=fbeta_beta,
        )
        return {
            "threshold": float(fixed_threshold),
            "max_signals": int(max_signals),
            "decision_policy": decision_policy,
            "decision_policy_live_safe": live_safe,
            "constraints_pass": threshold_constraints_pass(
                metrics,
                min_recall=min_recall,
                min_precision=min_precision,
                min_predicted_positive_rate=min_predicted_positive_rate,
                max_false_positive_rate=max_false_positive_rate,
            ),
            "constraints_reason": threshold_constraints_reason(
                metrics,
                min_recall=min_recall,
                min_precision=min_precision,
                min_predicted_positive_rate=min_predicted_positive_rate,
                max_false_positive_rate=max_false_positive_rate,
            ),
            "metrics": metrics,
        }
    if threshold_mode != "validation_sweep":
        raise ValueError(f"Unsupported threshold mode: {threshold_mode}")
    candidates: list[dict[str, Any]] = []
    threshold_objective_metric = str(objective_metric)
    for threshold in threshold_grid:
        for max_signals in signal_grid:
            pred = signal_predictions(
                prob,
                threshold=float(threshold),
                max_signals=max_signals,
                decision_policy=decision_policy,
            )
            metrics = binary_metrics_from_predictions(
                y_true,
                prob,
                pred,
                threshold=float(threshold),
                fp_cost=fp_cost,
                fn_cost=fn_cost,
                tp_reward=tp_reward,
                fbeta_beta=fbeta_beta,
            )
            direction, value = classification_objective(metrics, threshold_objective_metric)
            constraints_pass = threshold_constraints_pass(
                metrics,
                min_recall=min_recall,
                min_precision=min_precision,
                min_predicted_positive_rate=min_predicted_positive_rate,
                max_false_positive_rate=max_false_positive_rate,
            )
            candidates.append(
                {
                    "threshold": float(threshold),
                    "max_signals": int(max_signals),
                    "decision_policy": decision_policy,
                    "decision_policy_live_safe": live_safe,
                    "metrics": metrics,
                    "objective_direction": direction,
                    "objective_value": value,
                    "constraints_pass": constraints_pass,
                    "constraints_reason": threshold_constraints_reason(
                        metrics,
                        min_recall=min_recall,
                        min_precision=min_precision,
                        min_predicted_positive_rate=min_predicted_positive_rate,
                        max_false_positive_rate=max_false_positive_rate,
                    ),
                }
            )
    if not candidates:
        raise ValueError("Threshold grid is empty")
    passing = [candidate for candidate in candidates if candidate["constraints_pass"]]
    pool = passing if passing else candidates
    direction = str(pool[0]["objective_direction"])
    key = lambda candidate: float(candidate["objective_value"])
    best = min(pool, key=key) if direction == "minimize" else max(pool, key=key)
    if not passing:
        best = {**best, "constraints_pass": False, "constraints_reason": "no_threshold_satisfied_constraints"}
    return best


def normalize_max_signals_grid(values: tuple[int, ...]) -> tuple[int, ...]:
    cleaned = tuple(sorted(set(int(value) for value in values if int(value) >= 0)))
    return cleaned or (0,)


def decision_policy_max_signals_grid(decision_policy: str, values: tuple[int, ...]) -> tuple[int, ...]:
    decision_policy = validate_decision_policy(decision_policy)
    if decision_policy == DECISION_POLICY_THRESHOLD_ONLY:
        return (0,)
    return normalize_max_signals_grid(values)


def validate_decision_policy_signal_grid(decision_policy: str, values: tuple[int, ...]) -> tuple[int, ...]:
    decision_policy = validate_decision_policy(decision_policy)
    signal_grid = normalize_max_signals_grid(values)
    if decision_policy == DECISION_POLICY_THRESHOLD_ONLY and any(value > 0 for value in signal_grid):
        raise ValueError(
            "--max-signals-grid contains positive caps, but --decision-policy threshold_only "
            "ignores caps. Use --decision-policy causal_signal_budget for live-safe capped "
            "signals, use --decision-policy batch_topk_offline for offline diagnostics, or set "
            "--max-signals-grid 0."
        )
    return signal_grid


def validate_decision_policy(decision_policy: str) -> str:
    policy = str(decision_policy)
    if policy not in DECISION_POLICIES:
        raise ValueError(f"Unsupported decision policy: {decision_policy}")
    return policy


def is_live_safe_decision_policy(decision_policy: str) -> bool:
    return validate_decision_policy(decision_policy) in LIVE_SAFE_DECISION_POLICIES


def signal_predictions(
    prob: np.ndarray,
    *,
    threshold: float,
    max_signals: int = 0,
    decision_policy: str = DECISION_POLICY_THRESHOLD_ONLY,
) -> np.ndarray:
    decision_policy = validate_decision_policy(decision_policy)
    prob = np.asarray(prob, dtype=float)
    eligible = np.flatnonzero(np.isfinite(prob) & (prob >= float(threshold)))
    pred = np.zeros(len(prob), dtype=int)
    cap = int(max_signals)

    if decision_policy == DECISION_POLICY_THRESHOLD_ONLY or cap <= 0:
        ranked = eligible
    elif decision_policy == DECISION_POLICY_CAUSAL_SIGNAL_BUDGET:
        ranked = eligible[:cap]
    elif eligible.size > cap:
        ranked = eligible[np.argsort(-prob[eligible], kind="mergesort")[:cap]]
    else:
        ranked = eligible
    pred[ranked] = 1
    return pred


def classification_objective(metrics: dict[str, Any], objective_metric: str) -> tuple[str, float]:
    metric = str(objective_metric)
    if metric == "stable_prediction_quality":
        return "maximize", stable_prediction_quality_score(metrics, {}).get("score", -1e9)
    if metric == "stable_signal_quality":
        return "maximize", stable_signal_quality_score(metrics, {}).get("score", -1e9)
    if metric == "validation_logloss":
        return "minimize", none_to_bad(metrics.get("logloss"), minimize=True)
    if metric == "validation_decision_cost":
        return "minimize", none_to_bad(metrics.get("decision_cost_per_row"), minimize=True)
    if metric == "validation_false_positive_rate":
        return "minimize", none_to_bad(metrics.get("false_positive_rate"), minimize=True)
    if metric == "validation_precision":
        return "maximize", none_to_bad(metrics.get("precision"), minimize=False)
    if metric == "validation_precision_lift":
        return "maximize", none_to_bad(metrics.get("precision_lift"), minimize=False)
    if metric == "validation_fbeta":
        return "maximize", none_to_bad(metrics.get("fbeta"), minimize=False)
    if metric == "validation_balanced_accuracy":
        return "maximize", none_to_bad(metrics.get("balanced_accuracy"), minimize=False)
    if metric == "validation_pr_auc":
        return "maximize", none_to_bad(metrics.get("pr_auc"), minimize=False)
    if metric == "validation_mcc":
        return "maximize", none_to_bad(metrics.get("mcc"), minimize=False)
    raise ValueError(f"Unsupported classification objective metric: {objective_metric}")


def stable_prediction_quality_score(
    metrics: dict[str, Any],
    stability: dict[str, Any],
    *,
    threshold_pass_rate: float = 1.0,
    selected_feature_count_mean: float = 0.0,
    min_signal_rate: float = 0.01,
    max_signal_rate: float = 0.50,
) -> dict[str, float]:
    """Score prediction-batch trading usefulness with explicit collapse penalties.

    The score is intentionally prediction-surface oriented. Positive terms
    reward base-rate-adjusted decision quality; penalties reject the failure
    modes observed in RPF binary experiments: zero-positive windows,
    whole-batch-positive windows, unstable thresholds, and excessive feature
    complexity.
    """

    rows = int(metrics.get("rows") or 0)
    if rows <= 0:
        return {
            "score": -1e9,
            "quality": 0.0,
            "penalty": 1e9,
            "reason_code": 1.0,
        }

    positive_rate = finite_or_default(metrics.get("positive_rate"), 0.0)
    predicted_positive_rate = finite_or_default(metrics.get("predicted_positive_rate"), 0.0)
    pr_auc = finite_or_default(metrics.get("pr_auc"), positive_rate)
    precision_lift = finite_or_default(metrics.get("precision_lift"), 0.0)
    recall = finite_or_default(metrics.get("recall"), 0.0)
    fbeta = finite_or_default(metrics.get("fbeta"), 0.0)
    mcc = finite_or_default(metrics.get("mcc"), 0.0)
    brier = finite_or_default(metrics.get("brier"), 1.0)
    decision_cost_per_row = finite_or_default(metrics.get("decision_cost_per_row"), 1.0)

    pr_auc_lift = pr_auc - positive_rate
    precision_lift_gain = max(-1.0, min(2.0, precision_lift - 1.0))
    quality = (
        2.0 * pr_auc_lift
        + 0.50 * precision_lift_gain
        + 0.35 * recall
        + 0.75 * fbeta
        + 0.50 * mcc
        - 0.50 * brier
        - 0.25 * decision_cost_per_row
    )

    zero_window_rate = finite_or_default(stability.get("zero_positive_window_rate"), 0.0)
    all_window_rate = finite_or_default(stability.get("all_positive_window_rate"), 0.0)
    high_fpr_rate = finite_or_default(stability.get("high_fpr_window_rate"), 0.0)
    high_cost_rate = finite_or_default(stability.get("high_cost_window_rate"), 0.0)
    missed_high_target_rate = finite_or_default(stability.get("missed_high_target_window_rate"), 0.0)
    low_target_all_positive_rate = finite_or_default(stability.get("low_target_all_positive_window_rate"), 0.0)

    low_signal_penalty = max(0.0, float(min_signal_rate) - predicted_positive_rate) * 20.0
    high_signal_penalty = max(0.0, predicted_positive_rate - float(max_signal_rate)) * 4.0
    threshold_penalty = max(0.0, 1.0 - float(threshold_pass_rate))
    feature_penalty = max(0.0, float(selected_feature_count_mean)) / 10000.0
    stability_penalty = (
        1.50 * zero_window_rate
        + 1.50 * all_window_rate
        + 1.00 * high_fpr_rate
        + 1.00 * high_cost_rate
        + 1.75 * missed_high_target_rate
        + 1.50 * low_target_all_positive_rate
    )
    penalty = low_signal_penalty + high_signal_penalty + threshold_penalty + feature_penalty + stability_penalty
    score = quality - penalty
    return {
        "score": float(score),
        "quality": float(quality),
        "penalty": float(penalty),
        "pr_auc_lift": float(pr_auc_lift),
        "precision_lift_gain": float(precision_lift_gain),
        "recall": float(recall),
        "fbeta": float(fbeta),
        "mcc": float(mcc),
        "brier": float(brier),
        "decision_cost_per_row": float(decision_cost_per_row),
        "zero_positive_window_rate": float(zero_window_rate),
        "all_positive_window_rate": float(all_window_rate),
        "high_fpr_window_rate": float(high_fpr_rate),
        "high_cost_window_rate": float(high_cost_rate),
        "missed_high_target_window_rate": float(missed_high_target_rate),
        "low_target_all_positive_window_rate": float(low_target_all_positive_rate),
        "low_signal_penalty": float(low_signal_penalty),
        "high_signal_penalty": float(high_signal_penalty),
        "threshold_penalty": float(threshold_penalty),
        "feature_penalty": float(feature_penalty),
        "stability_penalty": float(stability_penalty),
    }


def stable_signal_quality_score(
    metrics: dict[str, Any],
    stability: dict[str, Any],
    *,
    threshold_pass_rate: float = 1.0,
    selected_feature_count_mean: float = 0.0,
    min_signal_rate: float = 0.0025,
    max_signal_rate: float = 0.35,
) -> dict[str, float]:
    """Score sparse high-precision specialist signals.

    This objective is intentionally different from ordinary classification
    quality. It rewards precision lift, low false-positive rate, and repeated
    active prediction batches. Recall is included only as a weak anti-dead-model
    term because these RPF binary models are used as signal detectors.
    """

    rows = int(metrics.get("rows") or 0)
    if rows <= 0:
        return {
            "score": -1e9,
            "quality": 0.0,
            "penalty": 1e9,
            "reason_code": 1.0,
        }

    predicted_positive_rate = finite_or_default(metrics.get("predicted_positive_rate"), 0.0)
    precision_lift = finite_or_default(metrics.get("precision_lift"), 0.0)
    precision = finite_or_default(metrics.get("precision"), 0.0)
    false_positive_rate = finite_or_default(metrics.get("false_positive_rate"), 1.0)
    false_discovery_rate = finite_or_default(metrics.get("false_discovery_rate"), 1.0)
    recall = finite_or_default(metrics.get("recall"), 0.0)
    mcc = finite_or_default(metrics.get("mcc"), 0.0)
    decision_cost_per_row = finite_or_default(metrics.get("decision_cost_per_row"), 1.0)

    active_rate = finite_or_default(stability.get("active_signal_window_rate"), 0.0)
    repeated_rate = finite_or_default(stability.get("repeated_active_signal_window_rate"), 0.0)
    churn_rate = finite_or_default(stability.get("signal_churn_rate"), 1.0)
    active_precision = finite_or_default(stability.get("active_signal_window_precision_mean"), precision)
    repeated_precision = finite_or_default(stability.get("repeated_active_signal_window_precision_mean"), active_precision)
    high_fpr_rate = finite_or_default(stability.get("high_fpr_window_rate"), 0.0)
    high_cost_rate = finite_or_default(stability.get("high_cost_window_rate"), 0.0)
    all_window_rate = finite_or_default(stability.get("all_positive_window_rate"), 0.0)
    low_target_all_positive_rate = finite_or_default(stability.get("low_target_all_positive_window_rate"), 0.0)

    precision_lift_gain = max(-1.0, min(3.0, precision_lift - 1.0))
    repeat_quality = 0.5 * active_rate + 1.25 * repeated_rate - 0.75 * churn_rate
    quality = (
        1.75 * precision_lift_gain
        + 0.85 * precision
        + 0.60 * active_precision
        + 0.90 * repeated_precision
        + 0.20 * recall
        + 0.35 * mcc
        + repeat_quality
        - 2.00 * false_positive_rate
        - 0.60 * false_discovery_rate
        - 0.20 * decision_cost_per_row
    )

    low_signal_penalty = max(0.0, float(min_signal_rate) - predicted_positive_rate) * 25.0
    high_signal_penalty = max(0.0, predicted_positive_rate - float(max_signal_rate)) * 6.0
    no_repeat_penalty = 0.75 if active_rate > 0.0 and repeated_rate <= 0.0 else 0.0
    no_active_penalty = 2.0 if active_rate <= 0.0 else 0.0
    threshold_penalty = max(0.0, 1.0 - float(threshold_pass_rate))
    feature_penalty = max(0.0, float(selected_feature_count_mean)) / 12000.0
    stability_penalty = (
        1.50 * high_fpr_rate
        + 1.00 * high_cost_rate
        + 1.50 * all_window_rate
        + 1.50 * low_target_all_positive_rate
    )
    penalty = (
        low_signal_penalty
        + high_signal_penalty
        + no_repeat_penalty
        + no_active_penalty
        + threshold_penalty
        + feature_penalty
        + stability_penalty
    )
    score = quality - penalty
    return {
        "score": float(score),
        "quality": float(quality),
        "penalty": float(penalty),
        "precision": float(precision),
        "precision_lift_gain": float(precision_lift_gain),
        "false_positive_rate": float(false_positive_rate),
        "false_discovery_rate": float(false_discovery_rate),
        "recall": float(recall),
        "mcc": float(mcc),
        "decision_cost_per_row": float(decision_cost_per_row),
        "active_signal_window_rate": float(active_rate),
        "repeated_active_signal_window_rate": float(repeated_rate),
        "signal_churn_rate": float(churn_rate),
        "active_signal_window_precision_mean": float(active_precision),
        "repeated_active_signal_window_precision_mean": float(repeated_precision),
        "low_signal_penalty": float(low_signal_penalty),
        "high_signal_penalty": float(high_signal_penalty),
        "no_repeat_penalty": float(no_repeat_penalty),
        "no_active_penalty": float(no_active_penalty),
        "threshold_penalty": float(threshold_penalty),
        "feature_penalty": float(feature_penalty),
        "stability_penalty": float(stability_penalty),
    }


def window_stability_metrics(
    window_metrics: list[dict[str, Any]],
    *,
    split: str,
    all_positive_rate_threshold: float,
    high_false_positive_rate_threshold: float,
    high_decision_cost_per_row_threshold: float,
    high_target_positive_rate_threshold: float = 0.70,
    min_high_target_window_recall: float = 0.05,
    min_high_target_window_signal_rate: float = 0.01,
    low_target_positive_rate_threshold: float = 0.35,
) -> dict[str, Any]:
    prefix = f"{split}_"
    ok_rows = [row for row in window_metrics if row.get("window_status") == "ok"]
    positive_rates = [
        float(row[f"{prefix}positive_rate"])
        for row in ok_rows
        if row.get(f"{prefix}positive_rate") is not None
        and math.isfinite(float(row[f"{prefix}positive_rate"]))
    ]
    pos_rates = [
        float(row[f"{prefix}predicted_positive_rate"])
        for row in ok_rows
        if row.get(f"{prefix}predicted_positive_rate") is not None
        and math.isfinite(float(row[f"{prefix}predicted_positive_rate"]))
    ]
    fprs = [
        float(row[f"{prefix}false_positive_rate"])
        for row in ok_rows
        if row.get(f"{prefix}false_positive_rate") is not None
        and math.isfinite(float(row[f"{prefix}false_positive_rate"]))
    ]
    costs = [
        float(row[f"{prefix}decision_cost_per_row"])
        for row in ok_rows
        if row.get(f"{prefix}decision_cost_per_row") is not None
        and math.isfinite(float(row[f"{prefix}decision_cost_per_row"]))
    ]
    window_count = len(ok_rows)
    high_target_rows = [
        row
        for row in ok_rows
        if row.get(f"{prefix}positive_rate") is not None
        and math.isfinite(float(row[f"{prefix}positive_rate"]))
        and float(row[f"{prefix}positive_rate"]) >= float(high_target_positive_rate_threshold)
    ]
    low_target_rows = [
        row
        for row in ok_rows
        if row.get(f"{prefix}positive_rate") is not None
        and math.isfinite(float(row[f"{prefix}positive_rate"]))
        and float(row[f"{prefix}positive_rate"]) <= float(low_target_positive_rate_threshold)
    ]
    missed_high_target_rows = [
        row
        for row in high_target_rows
        if (
            row.get(f"{prefix}predicted_positive_rate") is None
            or not math.isfinite(float(row[f"{prefix}predicted_positive_rate"]))
            or float(row[f"{prefix}predicted_positive_rate"]) < float(min_high_target_window_signal_rate)
            or row.get(f"{prefix}recall") is None
            or not math.isfinite(float(row[f"{prefix}recall"]))
            or float(row[f"{prefix}recall"]) < float(min_high_target_window_recall)
        )
    ]
    low_target_all_positive_rows = [
        row
        for row in low_target_rows
        if row.get(f"{prefix}predicted_positive_rate") is not None
        and math.isfinite(float(row[f"{prefix}predicted_positive_rate"]))
        and float(row[f"{prefix}predicted_positive_rate"]) >= float(all_positive_rate_threshold)
    ]
    high_target_recalls = [
        float(row[f"{prefix}recall"])
        for row in high_target_rows
        if row.get(f"{prefix}recall") is not None
        and math.isfinite(float(row[f"{prefix}recall"]))
    ]
    high_target_signal_rates = [
        float(row[f"{prefix}predicted_positive_rate"])
        for row in high_target_rows
        if row.get(f"{prefix}predicted_positive_rate") is not None
        and math.isfinite(float(row[f"{prefix}predicted_positive_rate"]))
    ]
    sorted_ok_rows = sorted(ok_rows, key=lambda row: int(row.get("pred_batch_id") or row.get("step_idx") or 0))
    active_flags = []
    active_precisions = []
    for row in sorted_ok_rows:
        rate = row.get(f"{prefix}predicted_positive_rate")
        active = rate is not None and math.isfinite(float(rate)) and float(rate) > 0.0
        active_flags.append(active)
        precision = row.get(f"{prefix}precision")
        active_precisions.append(
            float(precision)
            if active and precision is not None and math.isfinite(float(precision))
            else None
        )
    active_count = int(sum(active_flags))
    active_run_lengths = []
    current_run = 0
    for active in active_flags:
        if active:
            current_run += 1
        elif current_run:
            active_run_lengths.append(current_run)
            current_run = 0
    if current_run:
        active_run_lengths.append(current_run)
    repeated_indexes = {
        idx
        for idx, active in enumerate(active_flags)
        if active
        and (
            (idx > 0 and active_flags[idx - 1])
            or (idx + 1 < len(active_flags) and active_flags[idx + 1])
        )
    }
    isolated_indexes = {idx for idx, active in enumerate(active_flags) if active and idx not in repeated_indexes}
    transition_count = int(
        sum(1 for idx in range(1, len(active_flags)) if bool(active_flags[idx]) != bool(active_flags[idx - 1]))
    )
    repeated_precisions = [
        active_precisions[idx]
        for idx in sorted(repeated_indexes)
        if active_precisions[idx] is not None
    ]
    isolated_precisions = [
        active_precisions[idx]
        for idx in sorted(isolated_indexes)
        if active_precisions[idx] is not None
    ]
    active_precision_values = [value for value in active_precisions if value is not None]
    zero_positive_count = int(sum(rate <= 0.0 for rate in pos_rates))
    all_positive_count = int(sum(rate >= float(all_positive_rate_threshold) for rate in pos_rates))
    high_fpr_count = int(sum(rate > float(high_false_positive_rate_threshold) for rate in fprs))
    high_cost_count = int(sum(cost > float(high_decision_cost_per_row_threshold) for cost in costs))
    return {
        "window_count": int(window_count),
        "zero_positive_window_count": zero_positive_count,
        "zero_positive_window_rate": safe_div(zero_positive_count, window_count) if window_count else None,
        "all_positive_window_count": all_positive_count,
        "all_positive_window_rate": safe_div(all_positive_count, window_count) if window_count else None,
        "all_positive_rate_threshold": float(all_positive_rate_threshold),
        "high_fpr_window_count": high_fpr_count,
        "high_fpr_window_rate": safe_div(high_fpr_count, window_count) if window_count else None,
        "high_fpr_threshold": float(high_false_positive_rate_threshold),
        "high_cost_window_count": high_cost_count,
        "high_cost_window_rate": safe_div(high_cost_count, window_count) if window_count else None,
        "high_cost_threshold": float(high_decision_cost_per_row_threshold),
        "positive_rate_min": float(np.min(positive_rates)) if positive_rates else None,
        "positive_rate_mean": float(np.mean(positive_rates)) if positive_rates else None,
        "positive_rate_std": float(np.std(positive_rates)) if positive_rates else None,
        "positive_rate_max": float(np.max(positive_rates)) if positive_rates else None,
        "predicted_positive_rate_min": float(np.min(pos_rates)) if pos_rates else None,
        "predicted_positive_rate_mean": float(np.mean(pos_rates)) if pos_rates else None,
        "predicted_positive_rate_std": float(np.std(pos_rates)) if pos_rates else None,
        "predicted_positive_rate_max": float(np.max(pos_rates)) if pos_rates else None,
        "false_positive_rate_max": float(np.max(fprs)) if fprs else None,
        "decision_cost_per_row_max": float(np.max(costs)) if costs else None,
        "high_target_positive_rate_threshold": float(high_target_positive_rate_threshold),
        "high_target_window_count": int(len(high_target_rows)),
        "high_target_window_rate": safe_div(len(high_target_rows), window_count) if window_count else None,
        "missed_high_target_window_count": int(len(missed_high_target_rows)),
        "missed_high_target_window_rate": safe_div(len(missed_high_target_rows), len(high_target_rows))
        if high_target_rows
        else 0.0,
        "min_high_target_window_recall": float(min_high_target_window_recall),
        "min_high_target_window_signal_rate": float(min_high_target_window_signal_rate),
        "high_target_recall_mean": float(np.mean(high_target_recalls)) if high_target_recalls else None,
        "high_target_predicted_positive_rate_mean": float(np.mean(high_target_signal_rates)) if high_target_signal_rates else None,
        "active_signal_window_count": int(active_count),
        "active_signal_window_rate": safe_div(active_count, window_count) if window_count else None,
        "active_signal_run_count": int(len(active_run_lengths)),
        "active_signal_run_length_mean": float(np.mean(active_run_lengths)) if active_run_lengths else 0.0,
        "active_signal_run_length_max": int(max(active_run_lengths)) if active_run_lengths else 0,
        "repeated_active_signal_window_count": int(len(repeated_indexes)),
        "repeated_active_signal_window_rate": safe_div(len(repeated_indexes), window_count) if window_count else None,
        "isolated_active_signal_window_count": int(len(isolated_indexes)),
        "isolated_active_signal_window_rate": safe_div(len(isolated_indexes), window_count) if window_count else None,
        "signal_churn_count": transition_count,
        "signal_churn_rate": safe_div(transition_count, max(window_count - 1, 1)) if window_count else None,
        "active_signal_window_precision_mean": float(np.mean(active_precision_values)) if active_precision_values else None,
        "repeated_active_signal_window_precision_mean": float(np.mean(repeated_precisions)) if repeated_precisions else None,
        "isolated_active_signal_window_precision_mean": float(np.mean(isolated_precisions)) if isolated_precisions else None,
        "low_target_positive_rate_threshold": float(low_target_positive_rate_threshold),
        "low_target_window_count": int(len(low_target_rows)),
        "low_target_window_rate": safe_div(len(low_target_rows), window_count) if window_count else None,
        "low_target_all_positive_window_count": int(len(low_target_all_positive_rows)),
        "low_target_all_positive_window_rate": safe_div(len(low_target_all_positive_rows), len(low_target_rows))
        if low_target_rows
        else 0.0,
    }


def window_stability_constraints_reason(
    stability: dict[str, Any],
    *,
    max_zero_positive_window_rate: float,
    max_all_positive_window_rate: float,
    max_high_fpr_window_rate: float,
    max_high_cost_window_rate: float,
    max_missed_high_target_window_rate: float = 1.0,
    max_low_target_all_positive_window_rate: float = 1.0,
) -> str:
    zero_rate = stability.get("zero_positive_window_rate")
    all_rate = stability.get("all_positive_window_rate")
    high_fpr_rate = stability.get("high_fpr_window_rate")
    high_cost_rate = stability.get("high_cost_window_rate")
    missed_high_target_rate = stability.get("missed_high_target_window_rate")
    low_target_all_positive_rate = stability.get("low_target_all_positive_window_rate")
    if zero_rate is None:
        return "missing_window_stability"
    if float(max_zero_positive_window_rate) < 1.0 and float(zero_rate) > float(max_zero_positive_window_rate):
        return "too_many_zero_positive_windows"
    if all_rate is None:
        return "missing_window_stability"
    if float(max_all_positive_window_rate) < 1.0 and float(all_rate) > float(max_all_positive_window_rate):
        return "too_many_all_positive_windows"
    if high_fpr_rate is None:
        return "missing_window_stability"
    if float(max_high_fpr_window_rate) < 1.0 and float(high_fpr_rate) > float(max_high_fpr_window_rate):
        return "too_many_high_fpr_windows"
    if high_cost_rate is None:
        return "missing_window_stability"
    if float(max_high_cost_window_rate) < 1.0 and float(high_cost_rate) > float(max_high_cost_window_rate):
        return "too_many_high_cost_windows"
    if missed_high_target_rate is None:
        return "missing_window_stability"
    if float(max_missed_high_target_window_rate) < 1.0 and float(missed_high_target_rate) > float(
        max_missed_high_target_window_rate
    ):
        return "too_many_missed_high_target_windows"
    if low_target_all_positive_rate is None:
        return "missing_window_stability"
    if float(max_low_target_all_positive_window_rate) < 1.0 and float(low_target_all_positive_rate) > float(
        max_low_target_all_positive_window_rate
    ):
        return "too_many_low_target_all_positive_windows"
    return "pass"


def threshold_constraints_pass(
    metrics: dict[str, Any],
    *,
    min_recall: float,
    min_precision: float,
    min_predicted_positive_rate: float,
    max_false_positive_rate: float,
) -> bool:
    return threshold_constraints_reason(
        metrics,
        min_recall=min_recall,
        min_precision=min_precision,
        min_predicted_positive_rate=min_predicted_positive_rate,
        max_false_positive_rate=max_false_positive_rate,
    ) == "pass"


def threshold_constraints_reason(
    metrics: dict[str, Any],
    *,
    min_recall: float,
    min_precision: float,
    min_predicted_positive_rate: float,
    max_false_positive_rate: float,
) -> str:
    recall = metrics.get("recall")
    precision = metrics.get("precision")
    predicted_positive_rate = metrics.get("predicted_positive_rate")
    false_positive_rate = metrics.get("false_positive_rate")
    if float(min_recall) > 0.0 and (recall is None or float(recall) < float(min_recall)):
        return "low_recall"
    if float(min_precision) > 0.0 and (precision is None or float(precision) < float(min_precision)):
        return "low_precision"
    if float(min_predicted_positive_rate) > 0.0 and (
        predicted_positive_rate is None or float(predicted_positive_rate) < float(min_predicted_positive_rate)
    ):
        return "low_predicted_positive_rate"
    if float(max_false_positive_rate) < 1.0 and (
        false_positive_rate is None or float(false_positive_rate) > float(max_false_positive_rate)
    ):
        return "high_false_positive_rate"
    return "pass"


def none_to_bad(value: Any, *, minimize: bool) -> float:
    if value is None:
        return 1e9 if minimize else -1e9
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 1e9 if minimize else -1e9
    if not math.isfinite(number):
        return 1e9 if minimize else -1e9
    return number


def finite_or_default(value: Any, default: float) -> float:
    if value is None:
        return float(default)
    try:
        number = float(value)
    except (TypeError, ValueError):
        return float(default)
    if not math.isfinite(number):
        return float(default)
    return number


def positive_probability(model: Any, X: np.ndarray) -> np.ndarray:
    proba = np.asarray(model.predict_proba(X), dtype=float)
    return proba[:, 1]


def matthews_corrcoef(*, tp: int, tn: int, fp: int, fn: int) -> float | None:
    denominator = float((tp + fp) * (tp + fn) * (tn + fp) * (tn + fn))
    if denominator <= 0.0:
        return None
    return float((tp * tn - fp * fn) / math.sqrt(denominator))


def pr_auc_average_precision(y_true: np.ndarray, score: np.ndarray) -> float | None:
    y_true = np.asarray(y_true, dtype=int)
    score = np.asarray(score, dtype=float)
    mask = np.isfinite(score)
    y_true = y_true[mask]
    score = score[mask]
    positives = int(np.sum(y_true == 1))
    if len(y_true) == 0 or positives == 0:
        return None
    order = np.argsort(-score, kind="mergesort")
    sorted_true = y_true[order]
    tp_cum = np.cumsum(sorted_true == 1)
    rank = np.arange(1, len(sorted_true) + 1, dtype=float)
    precision_at_k = tp_cum / rank
    return float(np.sum(precision_at_k[sorted_true == 1]) / positives)


def auc_rank(y_true: np.ndarray, score: np.ndarray) -> float | None:
    y_true = np.asarray(y_true, dtype=int)
    score = np.asarray(score, dtype=float)
    pos = y_true == 1
    neg = y_true == 0
    n_pos = int(pos.sum())
    n_neg = int(neg.sum())
    if n_pos == 0 or n_neg == 0:
        return None
    ranks = rankdata_average(score)
    rank_sum_pos = float(ranks[pos].sum())
    return float((rank_sum_pos - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg))


def rankdata_average(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    order = np.argsort(values, kind="mergesort")
    ranks = np.empty(len(values), dtype=float)
    sorted_values = values[order]
    start = 0
    while start < len(values):
        end = start + 1
        while end < len(values) and sorted_values[end] == sorted_values[start]:
            end += 1
        rank = (start + end - 1) / 2.0 + 1.0
        ranks[order[start:end]] = rank
        start = end
    return ranks


def safe_div(numerator: float, denominator: float) -> float | None:
    if denominator == 0:
        return None
    return float(numerator / denominator)


def flatten_metrics(metrics: dict[str, Any], prefix: str) -> dict[str, Any]:
    return {f"{prefix}_{key}": value for key, value in metrics.items()}


def fmt_metric(value: Any) -> str:
    if value is None:
        return "-"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if not math.isfinite(number):
        return "-"
    return f"{number:.6g}"


def threshold_values(*, threshold_mode: str, decision_threshold: float, threshold_grid: str) -> tuple[float, ...]:
    if str(threshold_mode) == "fixed":
        return (float(decision_threshold),)
    values = tuple(sorted(set(parse_floats(str(threshold_grid)))))
    if not values:
        raise ValueError("--threshold-grid produced no thresholds")
    bad = [value for value in values if value <= 0.0 or value >= 1.0]
    if bad:
        raise ValueError(f"Thresholds must be between 0 and 1 exclusive: {bad}")
    return values


def parse_ints(raw: str) -> list[int]:
    return [int(value.strip()) for value in str(raw).split(",") if value.strip()]


def parse_floats(raw: str) -> list[float]:
    return [float(value.strip()) for value in str(raw).split(",") if value.strip()]
