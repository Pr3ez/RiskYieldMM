"""
Stage-1 Correlation Risk Model (CatBoost)
=========================================

Build a live-safe bad-regime detector from Stage-1 combo-correlation artifacts.

Design goals:
- inference features use only combo prediction-agreement structure
- no winner-knowledge leakage into feature columns
- deterministic threshold policy: maximize recall under flagged-rate budget
- offline holdout + strict walk-forward out-of-sample evaluation
"""

from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import numpy as np
import polars as pl
from catboost import CatBoostClassifier, CatBoostError, Pool


@dataclass(frozen=True)
class RiskModelArtifacts:
    feature_table_parquet: str
    feature_table_csv: str
    feature_columns_json: str
    feature_provenance_parquet: str
    feature_provenance_csv: str
    feature_leakage_audit_json: str
    train_predictions_parquet: str
    train_predictions_csv: str
    holdout_predictions_parquet: str
    holdout_predictions_csv: str
    threshold_grid_train_parquet: str
    threshold_grid_train_csv: str
    threshold_grid_holdout_parquet: str
    threshold_grid_holdout_csv: str
    walkforward_predictions_parquet: str
    walkforward_predictions_csv: str
    operating_policy_json: str
    summary_json: str


_BASE_NUMERIC_TYPES = {
    pl.Float32,
    pl.Float64,
    pl.Int8,
    pl.Int16,
    pl.Int32,
    pl.Int64,
    pl.UInt8,
    pl.UInt16,
    pl.UInt32,
    pl.UInt64,
}

_LABEL_META_COLUMNS = {
    "pred_batch",
    "winner_accuracy",
    "winner_combo_key",
    "is_bad_regime",
    "is_good_regime",
    "winner_accuracy_decile",
    "risk_bin",
    "risk_score_calibrated",
    "confidence_bin",
    "confidence_score_calibrated",
}

_FORBIDDEN_SUBSTRINGS = ("correct", "complementarity")
_FORBIDDEN_PREFIXES = ("w_", "risk_raw", "confidence_raw")
_SAFE_FEATURE_PREFIXES = (
    "all12_",
    "pairwise_",
    "pair_same_pred_rate_",
    "pair_same_direction_rate_",
    "pair_disagreement_rate_",
    "n_combos_present_",
)

_TEMPORAL_SUFFIXES = (
    "_lag1",
    "_lag2",
    "_lag3",
    "_delta1",
    "_roll3_mean",
    "_roll3_std",
    "_roll6_mean",
    "_roll6_std",
)


def _safe_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
    except Exception:
        return None
    if not math.isfinite(f):
        return None
    return f


def _binary_auc(y_true: np.ndarray, scores: np.ndarray) -> float | None:
    y = np.asarray(y_true, dtype=np.int32)
    s = np.asarray(scores, dtype=np.float64)
    mask = ~np.isnan(s)
    y = y[mask]
    s = s[mask]
    n_pos = int((y == 1).sum())
    n_neg = int((y == 0).sum())
    if n_pos == 0 or n_neg == 0:
        return None
    s_pos = s[y == 1]
    s_neg = s[y == 0]
    gt = (s_pos[:, None] > s_neg[None, :]).sum()
    eq = (s_pos[:, None] == s_neg[None, :]).sum()
    return float((float(gt) + 0.5 * float(eq)) / float(n_pos * n_neg))


def _binary_ap(y_true: np.ndarray, scores: np.ndarray) -> float | None:
    y = np.asarray(y_true, dtype=np.int32)
    s = np.asarray(scores, dtype=np.float64)
    mask = ~np.isnan(s)
    y = y[mask]
    s = s[mask]
    n_pos = int((y == 1).sum())
    if n_pos == 0:
        return None
    order = np.argsort(-s, kind="mergesort")
    y_sorted = y[order]
    tp = np.cumsum((y_sorted == 1).astype(np.int32))
    fp = np.cumsum((y_sorted == 0).astype(np.int32))
    precision = tp / np.maximum(tp + fp, 1)
    recall = tp / n_pos
    recall_prev = np.concatenate([[0.0], recall[:-1]])
    return float(np.sum((recall - recall_prev) * precision))


def _div(num: float, den: float) -> float:
    return float(num / den) if float(den) > 0.0 else 0.0


def _evaluate_binary_metrics(
    *,
    y_true: np.ndarray,
    y_pred_label: np.ndarray,
    y_score: np.ndarray | None = None,
) -> dict[str, float | None]:
    y_true = np.asarray(y_true, dtype=np.int32)
    y_pred_label = np.asarray(y_pred_label, dtype=np.int32)
    tp = int(np.sum((y_true == 1) & (y_pred_label == 1)))
    fp = int(np.sum((y_true == 0) & (y_pred_label == 1)))
    tn = int(np.sum((y_true == 0) & (y_pred_label == 0)))
    fn = int(np.sum((y_true == 1) & (y_pred_label == 0)))

    precision = _div(tp, tp + fp)
    recall = _div(tp, tp + fn)
    f1 = _div(2.0 * precision * recall, precision + recall)
    flagged_rate = _div(tp + fp, len(y_true))
    base_bad_rate = float(np.mean(y_true == 1)) if y_true.size > 0 else 0.0
    false_alarm_rate = _div(fp, fp + tn)
    kept_bad_rate = _div(fn, fn + tn)
    precision_lift = _div(precision, base_bad_rate) if base_bad_rate > 0 else 0.0

    out: dict[str, float | None] = {
        "rows": float(int(len(y_true))),
        "tp": float(tp),
        "fp": float(fp),
        "tn": float(tn),
        "fn": float(fn),
        "precision": float(precision),
        "recall": float(recall),
        "f1": float(f1),
        "flagged_rate": float(flagged_rate),
        "base_bad_rate": float(base_bad_rate),
        "false_alarm_rate": float(false_alarm_rate),
        "kept_bad_rate": float(kept_bad_rate),
        "precision_lift_vs_base": float(precision_lift),
        "auc": None,
        "pr_auc": None,
    }
    if y_score is not None:
        y_score = np.asarray(y_score, dtype=np.float64)
        out["auc"] = _safe_float(_binary_auc(y_true, y_score))
        out["pr_auc"] = _safe_float(_binary_ap(y_true, y_score))
    return out


def _evaluate_threshold_grid(
    *,
    y_true: np.ndarray,
    y_score: np.ndarray,
    thresholds: np.ndarray,
) -> pl.DataFrame:
    y_true = np.asarray(y_true, dtype=np.int32)
    y_score = np.asarray(y_score, dtype=np.float64)
    thresholds = np.asarray(thresholds, dtype=np.float64)

    pred = (y_score[:, None] >= thresholds[None, :])
    y_bad = (y_true == 1)[:, None]
    y_good = ~y_bad

    tp = np.sum(pred & y_bad, axis=0).astype(np.int32, copy=False)
    fp = np.sum(pred & y_good, axis=0).astype(np.int32, copy=False)
    fn = np.sum((~pred) & y_bad, axis=0).astype(np.int32, copy=False)
    tn = np.sum((~pred) & y_good, axis=0).astype(np.int32, copy=False)

    precision = np.divide(tp, tp + fp, out=np.zeros_like(tp, dtype=np.float64), where=(tp + fp) > 0)
    recall = np.divide(tp, tp + fn, out=np.zeros_like(tp, dtype=np.float64), where=(tp + fn) > 0)
    f1 = np.divide(
        2.0 * precision * recall,
        precision + recall,
        out=np.zeros_like(precision),
        where=(precision + recall) > 0,
    )
    flagged_rate = np.divide(tp + fp, max(1, len(y_true)))
    false_alarm = np.divide(fp, fp + tn, out=np.zeros_like(precision), where=(fp + tn) > 0)
    kept_bad = np.divide(fn, fn + tn, out=np.zeros_like(precision), where=(fn + tn) > 0)
    base_bad = float(np.mean(y_true == 1)) if len(y_true) > 0 else 0.0
    precision_lift = np.divide(
        precision,
        base_bad if base_bad > 0 else 1.0,
        out=np.zeros_like(precision),
        where=base_bad > 0,
    )
    return pl.DataFrame(
        {
            "threshold": thresholds,
            "tp": tp,
            "fp": fp,
            "tn": tn,
            "fn": fn,
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "flagged_rate": flagged_rate,
            "false_alarm_rate": false_alarm,
            "kept_bad_rate": kept_bad,
            "base_bad_rate": np.full_like(precision, base_bad),
            "precision_lift_vs_base": precision_lift,
        }
    )


def _select_threshold_max_recall_under_budget(
    *,
    threshold_grid_df: pl.DataFrame,
    flag_budget: float,
) -> dict[str, Any]:
    feasible = threshold_grid_df.filter(pl.col("flagged_rate") <= float(flag_budget))
    constraints_relaxed = False
    if feasible.is_empty():
        feasible = threshold_grid_df
        constraints_relaxed = True

    best = (
        feasible.sort(
            ["recall", "precision", "f1", "flagged_rate", "threshold"],
            descending=[True, True, True, False, False],
        )
        .head(1)
        .to_dicts()[0]
    )
    best["constraints_relaxed"] = bool(constraints_relaxed)
    best["selection_rule"] = (
        "maximize_recall_under_flag_budget"
        if not constraints_relaxed
        else "maximize_recall_constraints_relaxed"
    )
    return best


def _build_threshold_grid(
    *,
    y_score: np.ndarray,
    step: float,
) -> np.ndarray:
    base = np.arange(0.0, 1.0 + float(step) * 0.5, float(step), dtype=np.float64)
    merged = np.concatenate([base, np.asarray(y_score, dtype=np.float64)])
    merged = np.clip(merged, 0.0, 1.0)
    return np.unique(np.round(merged, 10))


def resolve_combo_match_run_dir(
    *,
    project_root: Path,
    run_id: str,
    unit: str,
    combo_match_run_dir: str | Path | None,
) -> Path:
    tf, target = str(unit).split("/", 1)
    unit_dir = (
        project_root
        / "data"
        / "htf_backtest_results"
        / str(run_id)
        / "catboost"
        / tf
        / target
    )
    if not unit_dir.exists():
        raise FileNotFoundError(f"Unit directory not found: {unit_dir}")
    combo_root = unit_dir / "combo_match_analysis"
    if not combo_root.exists():
        raise FileNotFoundError(f"combo_match_analysis directory not found: {combo_root}")

    if combo_match_run_dir is None:
        runs = sorted([p for p in combo_root.glob("*") if p.is_dir()])
        if not runs:
            raise FileNotFoundError(f"No combo-match runs found in {combo_root}")
        return runs[-1]

    maybe = Path(combo_match_run_dir)
    if maybe.exists():
        return maybe
    child = combo_root / str(combo_match_run_dir)
    if child.exists():
        return child
    raise FileNotFoundError(
        f"Combo-match run not found from '{combo_match_run_dir}'. "
        f"Checked '{maybe}' and '{child}'."
    )


def load_combo_match_inputs(
    *,
    combo_match_run_dir: Path,
    bad_threshold: float,
    bad_condition: str = "le",
) -> tuple[pl.DataFrame, pl.DataFrame]:
    batch_path = combo_match_run_dir / "winner12_batch_consensus_signals.parquet"
    pair_path = combo_match_run_dir / "winner12_combo_pairwise_agreement_stepwise.parquet"
    if not batch_path.exists():
        raise FileNotFoundError(f"Missing batch consensus file: {batch_path}")
    if not pair_path.exists():
        raise FileNotFoundError(f"Missing pairwise stepwise file: {pair_path}")

    batch_df = pl.read_parquet(batch_path).sort("pred_batch")
    pair_df = pl.read_parquet(pair_path).sort(["pred_batch", "combo_a", "combo_b"])

    if batch_df.is_empty():
        raise ValueError("winner12_batch_consensus_signals.parquet is empty")
    if pair_df.is_empty():
        raise ValueError("winner12_combo_pairwise_agreement_stepwise.parquet is empty")
    if "winner_accuracy" not in batch_df.columns:
        raise ValueError("winner_accuracy column missing in batch consensus table")

    cond = str(bad_condition).strip().lower()
    if cond not in {"le", "ge"}:
        raise ValueError(f"bad_condition must be 'le' or 'ge', got {bad_condition!r}")

    # Always recompute label from requested bad_threshold so scenario runs
    # do not accidentally reuse stale labels persisted by prior analysis cells.
    if cond == "le":
        expr = pl.col("winner_accuracy") <= float(bad_threshold)
    else:
        expr = pl.col("winner_accuracy") >= float(bad_threshold)
    batch_df = batch_df.with_columns(expr.alias("is_bad_regime"))
    return batch_df, pair_df


def _aggregate_pairwise_features(pair_df: pl.DataFrame) -> pl.DataFrame:
    metrics = ["same_pred_rate", "same_direction_rate", "disagreement_rate"]
    missing = [c for c in ["pred_batch"] + metrics if c not in pair_df.columns]
    if missing:
        raise ValueError(f"Missing required pairwise columns: {missing}")

    exprs: list[pl.Expr] = []
    for col in metrics:
        exprs.extend(
            [
                pl.col(col).mean().alias(f"pair_{col}_mean"),
                pl.col(col).std(ddof=1).fill_null(0.0).alias(f"pair_{col}_std"),
                pl.col(col).quantile(0.10).alias(f"pair_{col}_p10"),
                pl.col(col).quantile(0.50).alias(f"pair_{col}_p50"),
                pl.col(col).quantile(0.90).alias(f"pair_{col}_p90"),
            ]
        )
    return pair_df.group_by("pred_batch").agg(exprs).sort("pred_batch")


def _add_temporal_features(
    *,
    df: pl.DataFrame,
    temporal_base_cols: list[str],
) -> pl.DataFrame:
    out = df
    exprs: list[pl.Expr] = []
    for col in temporal_base_cols:
        if col not in out.columns:
            continue
        prev = pl.col(col).shift(1)
        exprs.extend(
            [
                prev.alias(f"{col}_lag1"),
                pl.col(col).shift(2).alias(f"{col}_lag2"),
                pl.col(col).shift(3).alias(f"{col}_lag3"),
                (pl.col(col) - prev).alias(f"{col}_delta1"),
                prev.rolling_mean(window_size=3, min_samples=1).alias(f"{col}_roll3_mean"),
                prev.rolling_std(window_size=3, min_samples=2).fill_null(0.0).alias(f"{col}_roll3_std"),
                prev.rolling_mean(window_size=6, min_samples=1).alias(f"{col}_roll6_mean"),
                prev.rolling_std(window_size=6, min_samples=2).fill_null(0.0).alias(f"{col}_roll6_std"),
            ]
        )
    out = out.with_columns(exprs)

    temporal_cols = [
        c
        for c in out.columns
        if c.endswith("_lag1")
        or c.endswith("_lag2")
        or c.endswith("_lag3")
        or c.endswith("_delta1")
        or c.endswith("_roll3_mean")
        or c.endswith("_roll3_std")
        or c.endswith("_roll6_mean")
        or c.endswith("_roll6_std")
    ]
    if temporal_cols:
        out = out.with_columns([pl.col(c).fill_null(0.0).alias(c) for c in temporal_cols])
    return out


def build_live_safe_feature_table(
    *,
    batch_df: pl.DataFrame,
    pair_df: pl.DataFrame,
) -> pl.DataFrame:
    base_cols = [
        "pred_batch",
        "winner_accuracy",
        "winner_combo_key",
        "is_bad_regime",
        "all12_same_prediction_rate",
        "all12_same_direction_rate",
        "pairwise_same_prediction_rate",
        "pairwise_same_direction_rate",
        "w_same_class_pair_rate_mean",
        "w_same_direction_pair_rate_mean",
        "w_class_entropy_norm_mean",
        "w_direction_entropy_norm_mean",
        "w_class_margin_mean",
        "w_direction_margin_mean",
        "risk_raw_mean",
        "risk_raw_std",
        "risk_raw_p10",
        "risk_raw_p50",
        "risk_raw_p90",
        "confidence_raw_mean",
        "confidence_raw_std",
        "confidence_raw_p10",
        "confidence_raw_p50",
        "confidence_raw_p90",
        "n_combos_present_mean",
        "n_combos_present_min",
        "n_combos_present_max",
    ]
    missing = [c for c in base_cols if c not in batch_df.columns]
    if missing:
        raise ValueError(f"Missing required batch columns for risk model: {missing}")

    base_df = batch_df.select(base_cols).sort("pred_batch")
    pair_agg_df = _aggregate_pairwise_features(pair_df)
    feat_df = base_df.join(pair_agg_df, on="pred_batch", how="left")
    pair_cols = [c for c in feat_df.columns if c.startswith("pair_")]
    if pair_cols:
        feat_df = feat_df.with_columns([pl.col(c).fill_null(0.0).alias(c) for c in pair_cols])

    temporal_base_cols = [
        "all12_same_prediction_rate",
        "all12_same_direction_rate",
        "pairwise_same_prediction_rate",
        "pairwise_same_direction_rate",
        "w_same_class_pair_rate_mean",
        "w_same_direction_pair_rate_mean",
        "w_class_entropy_norm_mean",
        "w_direction_entropy_norm_mean",
        "w_class_margin_mean",
        "w_direction_margin_mean",
        "risk_raw_mean",
        "risk_raw_std",
        "confidence_raw_mean",
        "confidence_raw_std",
        "pair_same_pred_rate_mean",
        "pair_same_direction_rate_mean",
        "pair_disagreement_rate_mean",
    ]
    feat_df = _add_temporal_features(df=feat_df, temporal_base_cols=temporal_base_cols)
    return feat_df.sort("pred_batch")


def _strip_temporal_suffix(feature_name: str) -> str:
    for suf in _TEMPORAL_SUFFIXES:
        if feature_name.endswith(suf):
            return feature_name[: -len(suf)]
    return feature_name


def _infer_feature_source(base_name: str) -> tuple[str, list[str]]:
    if base_name.startswith("pair_"):
        return (
            "winner12_combo_pairwise_agreement_stepwise.parquet",
            [base_name.replace("pair_", "", 1)],
        )
    return ("winner12_batch_consensus_signals.parquet", [base_name])


def _classify_feature(
    *,
    feature_name: str,
    dtype: pl.DataType,
    feature_policy: str,
) -> dict[str, Any]:
    base_name = _strip_temporal_suffix(feature_name)
    source_file, source_columns = _infer_feature_source(base_name)

    depends_on_y_true = (
        "correct" in feature_name or "complementarity" in feature_name
    )
    depends_on_future_steps = (
        feature_name.startswith(_FORBIDDEN_PREFIXES)
        or base_name.startswith(_FORBIDDEN_PREFIXES)
    )

    drop_reason: str | None = None
    if dtype not in _BASE_NUMERIC_TYPES:
        drop_reason = "non_numeric"
    elif feature_name in _LABEL_META_COLUMNS:
        drop_reason = "label_or_meta"
    elif feature_policy != "strict_live_safe_v1":
        drop_reason = "unsupported_feature_policy"
    elif depends_on_y_true:
        drop_reason = "depends_on_y_true"
    elif depends_on_future_steps:
        drop_reason = "depends_on_future_steps"
    elif any(tok in feature_name for tok in _FORBIDDEN_SUBSTRINGS):
        drop_reason = "forbidden_family"
    elif not (
        feature_name.startswith(_SAFE_FEATURE_PREFIXES)
        or base_name.startswith(_SAFE_FEATURE_PREFIXES)
    ):
        drop_reason = "not_in_live_safe_allowlist"

    available_at_prediction = drop_reason is None
    return {
        "feature_name": feature_name,
        "dtype": str(dtype),
        "feature_policy": str(feature_policy),
        "source_file": source_file,
        "source_columns": source_columns,
        "depends_on_y_true": bool(depends_on_y_true),
        "depends_on_future_steps": bool(depends_on_future_steps),
        "available_at_prediction": bool(available_at_prediction),
        "drop_reason": drop_reason,
    }


def build_feature_provenance(
    *,
    feature_df: pl.DataFrame,
    feature_policy: Literal["strict_live_safe_v1"] = "strict_live_safe_v1",
) -> pl.DataFrame:
    rows = [
        _classify_feature(
            feature_name=c,
            dtype=dtype,
            feature_policy=str(feature_policy),
        )
        for c, dtype in zip(feature_df.columns, feature_df.dtypes, strict=True)
    ]
    return (
        pl.DataFrame(rows)
        .with_columns(
            [
                pl.col("source_columns").cast(pl.List(pl.Utf8)),
                pl.col("drop_reason").cast(pl.Utf8),
            ]
        )
        .sort("feature_name")
    )


def select_live_safe_feature_columns(
    *,
    feature_df: pl.DataFrame,
    feature_policy: Literal["strict_live_safe_v1"] = "strict_live_safe_v1",
) -> tuple[list[str], pl.DataFrame]:
    provenance_df = build_feature_provenance(
        feature_df=feature_df,
        feature_policy=feature_policy,
    )
    selected = provenance_df.filter(pl.col("available_at_prediction")).select(
        "feature_name"
    )
    feature_cols = selected["feature_name"].to_list()
    if not feature_cols:
        raise ValueError(
            "No live-safe numeric feature columns selected "
            f"(policy={feature_policy})."
        )
    return feature_cols, provenance_df


def assert_no_lookahead_features(
    *,
    provenance_df: pl.DataFrame,
    selected_feature_cols: list[str],
    strict_leakage_guard: bool,
) -> dict[str, Any]:
    selected_df = provenance_df.filter(
        pl.col("feature_name").is_in(selected_feature_cols)
    )
    leak_df = selected_df.filter(
        pl.col("depends_on_y_true")
        | pl.col("depends_on_future_steps")
        | (~pl.col("available_at_prediction"))
    )
    leakage_guard_passed = bool(leak_df.is_empty())

    dropped_df = provenance_df.filter(~pl.col("available_at_prediction"))
    dropped_by_reason: dict[str, int] = {}
    if not dropped_df.is_empty():
        for row in (
            dropped_df.group_by("drop_reason")
            .len()
            .sort("drop_reason")
            .to_dicts()
        ):
            dropped_by_reason[str(row["drop_reason"])] = int(row["len"])

    forbidden_patterns_present = [
        c
        for c in selected_feature_cols
        if c in _LABEL_META_COLUMNS
        or any(tok in c for tok in _FORBIDDEN_SUBSTRINGS)
        or c.startswith(_FORBIDDEN_PREFIXES)
    ]

    audit = {
        "strict_leakage_guard": bool(strict_leakage_guard),
        "leakage_guard_passed": bool(leakage_guard_passed),
        "selected_feature_count": int(len(selected_feature_cols)),
        "dropped_feature_count": int(len(provenance_df) - len(selected_feature_cols)),
        "dropped_by_reason": dropped_by_reason,
        "forbidden_patterns_in_selected": sorted(forbidden_patterns_present),
        "selected_leak_rows": leak_df.to_dicts(),
    }

    if strict_leakage_guard and not leakage_guard_passed:
        raise ValueError(
            "Leakage guard failed: selected features contain lookahead/leaky fields. "
            f"Examples: {audit['selected_leak_rows'][:5]}"
        )
    return audit


def fit_catboost_binary(
    *,
    X_train: np.ndarray,
    y_train: np.ndarray,
    feature_names: list[str],
    random_seed: int,
    use_gpu: bool,
    gpu_devices: str | None,
    verbose: bool,
    model_label: str,
) -> tuple[CatBoostClassifier, dict[str, Any], dict[str, Any]]:
    params: dict[str, Any] = {
        "loss_function": "Logloss",
        "eval_metric": "AUC",
        "iterations": 450,
        "depth": 4,
        "learning_rate": 0.03,
        "l2_leaf_reg": 8.0,
        "bootstrap_type": "Bernoulli",
        "subsample": 0.9,
        "random_seed": int(random_seed),
        "auto_class_weights": "Balanced",
        "allow_writing_files": False,
        "verbose": False,
    }
    if bool(use_gpu):
        params["task_type"] = "GPU"
        # Avoid repeated CatBoost GPU warning spam ("AUC not implemented for GPU").
        params["eval_metric"] = "Logloss"
        if gpu_devices is not None and str(gpu_devices).strip():
            params["devices"] = str(gpu_devices).strip()

    model = CatBoostClassifier(**params)
    train_pool = Pool(
        data=np.asarray(X_train, dtype=np.float32),
        label=np.asarray(y_train, dtype=np.int32),
        feature_names=feature_names,
    )

    fit_meta = {
        "task_type_requested": "GPU" if bool(use_gpu) else "CPU",
        "task_type_used": "GPU" if bool(use_gpu) else "CPU",
        "gpu_fallback": False,
        "gpu_fallback_reason": None,
    }
    try:
        model.fit(train_pool)
    except CatBoostError as exc:
        if not bool(use_gpu):
            raise
        fit_meta["gpu_fallback"] = True
        fit_meta["gpu_fallback_reason"] = str(exc)
        fit_meta["task_type_used"] = "CPU"
        if verbose:
            print(
                f"[RiskModel][{model_label}] GPU training failed, "
                "falling back to CPU once: "
                f"{exc}"
            )
        cpu_params = dict(params)
        cpu_params.pop("task_type", None)
        cpu_params.pop("devices", None)
        model = CatBoostClassifier(**cpu_params)
        model.fit(train_pool)
        params = cpu_params
    return model, params, fit_meta


def run_walkforward_oos(
    *,
    feature_df: pl.DataFrame,
    feature_cols: list[str],
    random_seed: int,
    flag_budget: float,
    threshold_grid_step: float,
    wf_warmup_steps: int,
    wf_retrain_every_steps: int,
    use_gpu: bool,
    gpu_devices: str | None,
    verbose: bool,
    progress_every_steps: int,
) -> tuple[pl.DataFrame, dict[str, float | None]]:
    X = feature_df.select(feature_cols).to_numpy().astype(np.float32, copy=False)
    y = feature_df["is_bad_regime"].cast(pl.Int8).to_numpy().astype(np.int32, copy=False)
    pred_batches = feature_df["pred_batch"].to_numpy().astype(np.int32, copy=False)
    n = int(len(y))
    warm = int(wf_warmup_steps)
    if warm < 20:
        raise ValueError("wf_warmup_steps must be >= 20")
    if warm >= n:
        raise ValueError("wf_warmup_steps must be < total rows")

    retrain_every = int(max(1, wf_retrain_every_steps))
    rows: list[dict[str, Any]] = []
    curr_model: CatBoostClassifier | None = None
    curr_threshold: float | None = None
    curr_selected: dict[str, Any] | None = None
    gpu_enabled = bool(use_gpu)
    progress_every = int(max(1, progress_every_steps))
    total_steps = int(n - warm)
    start_ts = time.time()
    if verbose:
        print(
            f"[RiskModel][WF] start: steps={total_steps}, warmup={warm}, "
            f"retrain_every={retrain_every}, use_gpu={gpu_enabled}, devices={gpu_devices}"
        )

    for i in range(warm, n):
        step_no = int(i - warm + 1)
        should_refit = curr_model is None or ((i - warm) % retrain_every == 0)
        if should_refit:
            curr_model, _, fit_meta = fit_catboost_binary(
                X_train=X[:i],
                y_train=y[:i],
                feature_names=feature_cols,
                random_seed=int(random_seed),
                use_gpu=gpu_enabled,
                gpu_devices=gpu_devices,
                verbose=verbose,
                model_label="WF",
            )
            if gpu_enabled and bool(fit_meta.get("gpu_fallback")):
                gpu_enabled = False
            train_score = curr_model.predict_proba(X[:i])[:, 1].astype(np.float64, copy=False)
            grid = _build_threshold_grid(y_score=train_score, step=float(threshold_grid_step))
            grid_df = _evaluate_threshold_grid(
                y_true=y[:i],
                y_score=train_score,
                thresholds=grid,
            )
            curr_selected = _select_threshold_max_recall_under_budget(
                threshold_grid_df=grid_df,
                flag_budget=float(flag_budget),
            )
            curr_threshold = float(curr_selected["threshold"])

        assert curr_model is not None
        assert curr_selected is not None
        assert curr_threshold is not None

        p_i = float(curr_model.predict_proba(X[i : i + 1])[:, 1][0])
        pred_i = int(p_i >= curr_threshold)
        rows.append(
            {
                "pred_batch": int(pred_batches[i]),
                "wf_step_idx": int(step_no),
                "train_rows_used": int(i),
                "score_bad": float(p_i),
                "is_bad_regime": int(y[i]),
                "pred_bad_regime": int(pred_i),
                "threshold_used": float(curr_threshold),
                "train_threshold_recall": float(curr_selected["recall"]),
                "train_threshold_precision": float(curr_selected["precision"]),
                "train_threshold_f1": float(curr_selected["f1"]),
                "train_threshold_flagged_rate": float(curr_selected["flagged_rate"]),
                "constraints_relaxed": bool(curr_selected["constraints_relaxed"]),
            }
        )
        if verbose and (step_no == 1 or step_no % progress_every == 0 or step_no == total_steps):
            elapsed = float(time.time() - start_ts)
            rate = float(step_no / elapsed) if elapsed > 0 else 0.0
            remaining = int(total_steps - step_no)
            eta = float(remaining / rate) if rate > 0 else float("nan")
            print(
                f"[RiskModel][WF] step {step_no}/{total_steps} "
                f"pred_batch={int(pred_batches[i])} "
                f"retrain={int(bool(should_refit))} "
                f"threshold={float(curr_threshold):.4f} "
                f"score={float(p_i):.4f} "
                f"elapsed={elapsed:.1f}s "
                f"eta={eta:.1f}s"
            )

    wf_df = pl.DataFrame(rows).sort("pred_batch")
    wf_metrics = _evaluate_binary_metrics(
        y_true=wf_df["is_bad_regime"].to_numpy().astype(np.int32, copy=False),
        y_pred_label=wf_df["pred_bad_regime"].to_numpy().astype(np.int32, copy=False),
        y_score=wf_df["score_bad"].to_numpy().astype(np.float64, copy=False),
    )
    return wf_df, wf_metrics


def run_stage1_correlation_risk_model(
    *,
    project_root: str | Path,
    run_id: str,
    unit: str,
    combo_match_run_dir: str | Path | None = None,
    bad_threshold: float = 0.30,
    bad_condition: str = "le",
    flag_budget: float = 0.20,
    holdout_steps: int = 200,
    wf_warmup_steps: int = 120,
    wf_retrain_every_steps: int = 1,
    threshold_grid_step: float = 0.005,
    random_seed: int = 42,
    use_gpu: bool = False,
    gpu_devices: str | None = "0",
    wf_progress_every_steps: int = 10,
    feature_policy: Literal["strict_live_safe_v1"] = "strict_live_safe_v1",
    strict_leakage_guard: bool = True,
    save_feature_provenance: bool = True,
    verbose: bool = True,
) -> dict[str, Any]:
    project_root_path = Path(project_root)
    combo_dir = resolve_combo_match_run_dir(
        project_root=project_root_path,
        run_id=run_id,
        unit=unit,
        combo_match_run_dir=combo_match_run_dir,
    )

    batch_df, pair_df = load_combo_match_inputs(
        combo_match_run_dir=combo_dir,
        bad_threshold=float(bad_threshold),
        bad_condition=str(bad_condition),
    )
    feature_df = build_live_safe_feature_table(batch_df=batch_df, pair_df=pair_df)
    feature_cols, feature_provenance_df = select_live_safe_feature_columns(
        feature_df=feature_df,
        feature_policy=feature_policy,
    )
    leakage_audit = assert_no_lookahead_features(
        provenance_df=feature_provenance_df,
        selected_feature_cols=feature_cols,
        strict_leakage_guard=bool(strict_leakage_guard),
    )
    if verbose:
        print(
            f"[RiskModel] features prepared: rows={len(feature_df)}, "
            f"cols={len(feature_cols)}"
        )
        print(
            "[RiskModel] feature policy: "
            f"{feature_policy} | leakage_guard_passed={leakage_audit['leakage_guard_passed']} "
            f"| dropped={leakage_audit['dropped_feature_count']}"
        )

    n = int(len(feature_df))
    holdout = int(holdout_steps)
    if holdout <= 0:
        raise ValueError("holdout_steps must be > 0")
    if n <= holdout:
        raise ValueError(f"holdout_steps={holdout} must be < rows={n}")

    split_idx = int(n - holdout)
    train_df = feature_df.head(split_idx)
    holdout_df = feature_df.tail(holdout)

    X_train = train_df.select(feature_cols).to_numpy().astype(np.float32, copy=False)
    y_train = train_df["is_bad_regime"].cast(pl.Int8).to_numpy().astype(np.int32, copy=False)
    X_holdout = holdout_df.select(feature_cols).to_numpy().astype(np.float32, copy=False)
    y_holdout = holdout_df["is_bad_regime"].cast(pl.Int8).to_numpy().astype(np.int32, copy=False)

    if verbose:
        print(
            "[RiskModel] fitting static model "
            f"(train_rows={split_idx}, holdout_rows={holdout}, "
            f"use_gpu={bool(use_gpu)}, devices={gpu_devices})"
        )
    model, model_params, static_fit_meta = fit_catboost_binary(
        X_train=X_train,
        y_train=y_train,
        feature_names=feature_cols,
        random_seed=int(random_seed),
        use_gpu=bool(use_gpu),
        gpu_devices=gpu_devices,
        verbose=verbose,
        model_label="STATIC",
    )
    p_train = model.predict_proba(X_train)[:, 1].astype(np.float64, copy=False)
    p_holdout = model.predict_proba(X_holdout)[:, 1].astype(np.float64, copy=False)

    threshold_grid = _build_threshold_grid(y_score=p_train, step=float(threshold_grid_step))
    grid_train_df = _evaluate_threshold_grid(
        y_true=y_train,
        y_score=p_train,
        thresholds=threshold_grid,
    ).sort("threshold")
    selected = _select_threshold_max_recall_under_budget(
        threshold_grid_df=grid_train_df,
        flag_budget=float(flag_budget),
    )
    selected_threshold = float(selected["threshold"])

    grid_holdout_df = _evaluate_threshold_grid(
        y_true=y_holdout,
        y_score=p_holdout,
        thresholds=threshold_grid,
    ).sort("threshold")
    pred_train = (p_train >= selected_threshold).astype(np.int32, copy=False)
    pred_holdout = (p_holdout >= selected_threshold).astype(np.int32, copy=False)

    train_metrics = _evaluate_binary_metrics(
        y_true=y_train,
        y_pred_label=pred_train,
        y_score=p_train,
    )
    holdout_metrics = _evaluate_binary_metrics(
        y_true=y_holdout,
        y_pred_label=pred_holdout,
        y_score=p_holdout,
    )

    wf_df, wf_metrics = run_walkforward_oos(
        feature_df=feature_df,
        feature_cols=feature_cols,
        random_seed=int(random_seed),
        flag_budget=float(flag_budget),
        threshold_grid_step=float(threshold_grid_step),
        wf_warmup_steps=int(wf_warmup_steps),
        wf_retrain_every_steps=int(wf_retrain_every_steps),
        use_gpu=bool(use_gpu and static_fit_meta.get("task_type_used") == "GPU"),
        gpu_devices=gpu_devices,
        verbose=verbose,
        progress_every_steps=int(wf_progress_every_steps),
    )

    train_max_pred_batch = int(train_df["pred_batch"].max())
    holdout_min_pred_batch = int(holdout_df["pred_batch"].min())
    split_monotonic = bool(train_max_pred_batch < holdout_min_pred_batch)

    wf_align_df = wf_df.join(
        feature_df.select("pred_batch").with_row_index("row_idx"),
        on="pred_batch",
        how="left",
    ).with_columns((pl.col("row_idx") - pl.col("train_rows_used")).alias("idx_diff"))
    wf_alignment_all_zero = bool(wf_align_df["idx_diff"].eq(0).all())
    wf_alignment_nonzero_count = int(
        wf_align_df.filter(pl.col("idx_diff") != 0).height
    )
    temporal_integrity_checks = {
        "train_holdout_split_monotonic": bool(split_monotonic),
        "train_max_pred_batch": int(train_max_pred_batch),
        "holdout_min_pred_batch": int(holdout_min_pred_batch),
        "walkforward_idx_alignment_all_zero": bool(wf_alignment_all_zero),
        "walkforward_idx_alignment_nonzero_count": int(wf_alignment_nonzero_count),
    }
    if bool(strict_leakage_guard) and (
        (not split_monotonic) or (not wf_alignment_all_zero)
    ):
        raise ValueError(
            "Temporal integrity check failed under strict leakage guard: "
            f"{temporal_integrity_checks}"
        )

    importance = model.get_feature_importance(Pool(X_train, y_train, feature_names=feature_cols))
    feature_importance_df = (
        pl.DataFrame(
            {
                "feature": feature_cols,
                "importance": np.asarray(importance, dtype=np.float64),
            }
        )
        .sort("importance", descending=True)
    )

    out_dir = combo_dir / "risk_model" / datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    out_dir.mkdir(parents=True, exist_ok=True)

    artifacts = RiskModelArtifacts(
        feature_table_parquet=str(out_dir / "risk_model_feature_table.parquet"),
        feature_table_csv=str(out_dir / "risk_model_feature_table.csv"),
        feature_columns_json=str(out_dir / "risk_model_feature_columns.json"),
        feature_provenance_parquet=str(out_dir / "risk_model_feature_provenance.parquet"),
        feature_provenance_csv=str(out_dir / "risk_model_feature_provenance.csv"),
        feature_leakage_audit_json=str(out_dir / "risk_model_feature_leakage_audit.json"),
        train_predictions_parquet=str(out_dir / "risk_model_train_predictions.parquet"),
        train_predictions_csv=str(out_dir / "risk_model_train_predictions.csv"),
        holdout_predictions_parquet=str(out_dir / "risk_model_holdout_predictions.parquet"),
        holdout_predictions_csv=str(out_dir / "risk_model_holdout_predictions.csv"),
        threshold_grid_train_parquet=str(out_dir / "risk_model_threshold_grid_train.parquet"),
        threshold_grid_train_csv=str(out_dir / "risk_model_threshold_grid_train.csv"),
        threshold_grid_holdout_parquet=str(out_dir / "risk_model_threshold_grid_holdout.parquet"),
        threshold_grid_holdout_csv=str(out_dir / "risk_model_threshold_grid_holdout.csv"),
        walkforward_predictions_parquet=str(out_dir / "risk_model_walkforward_predictions.parquet"),
        walkforward_predictions_csv=str(out_dir / "risk_model_walkforward_predictions.csv"),
        operating_policy_json=str(out_dir / "risk_model_operating_policy.json"),
        summary_json=str(out_dir / "risk_model_summary.json"),
    )

    feature_df.write_parquet(artifacts.feature_table_parquet)
    feature_df.write_csv(artifacts.feature_table_csv)
    with open(artifacts.feature_columns_json, "w") as f:
        json.dump({"feature_columns": feature_cols}, f, indent=2)
    if bool(save_feature_provenance):
        feature_provenance_df.write_parquet(artifacts.feature_provenance_parquet)
        feature_provenance_df.with_columns(
            pl.col("source_columns").list.join("|").alias("source_columns")
        ).write_csv(artifacts.feature_provenance_csv)
    with open(artifacts.feature_leakage_audit_json, "w") as f:
        json.dump(
            {
                **leakage_audit,
                "temporal_integrity_checks": temporal_integrity_checks,
            },
            f,
            indent=2,
        )

    train_pred_df = train_df.select(["pred_batch", "winner_accuracy", "is_bad_regime"]).with_columns(
        [
            pl.Series("score_bad", p_train),
            pl.Series("pred_bad_regime", pred_train),
            pl.lit(float(selected_threshold)).alias("threshold_used"),
        ]
    )
    holdout_pred_df = holdout_df.select(["pred_batch", "winner_accuracy", "is_bad_regime"]).with_columns(
        [
            pl.Series("score_bad", p_holdout),
            pl.Series("pred_bad_regime", pred_holdout),
            pl.lit(float(selected_threshold)).alias("threshold_used"),
        ]
    )
    train_pred_df.write_parquet(artifacts.train_predictions_parquet)
    train_pred_df.write_csv(artifacts.train_predictions_csv)
    holdout_pred_df.write_parquet(artifacts.holdout_predictions_parquet)
    holdout_pred_df.write_csv(artifacts.holdout_predictions_csv)

    grid_train_df.write_parquet(artifacts.threshold_grid_train_parquet)
    grid_train_df.write_csv(artifacts.threshold_grid_train_csv)
    grid_holdout_df.write_parquet(artifacts.threshold_grid_holdout_parquet)
    grid_holdout_df.write_csv(artifacts.threshold_grid_holdout_csv)
    wf_df.write_parquet(artifacts.walkforward_predictions_parquet)
    wf_df.write_csv(artifacts.walkforward_predictions_csv)

    operating_policy = {
        "selection_rule": selected["selection_rule"],
        "constraints_relaxed": bool(selected["constraints_relaxed"]),
        "flag_budget": float(flag_budget),
        "selected_threshold": float(selected_threshold),
        "selected_train_metrics": {
            "precision": float(selected["precision"]),
            "recall": float(selected["recall"]),
            "f1": float(selected["f1"]),
            "flagged_rate": float(selected["flagged_rate"]),
            "kept_bad_rate": float(selected["kept_bad_rate"]),
            "precision_lift_vs_base": float(selected["precision_lift_vs_base"]),
        },
    }
    with open(artifacts.operating_policy_json, "w") as f:
        json.dump(operating_policy, f, indent=2)

    summary = {
        "run_id": str(run_id),
        "unit": str(unit),
        "combo_match_run_dir": str(combo_dir),
        "config": {
            "bad_threshold": float(bad_threshold),
            "bad_condition": str(bad_condition),
            "flag_budget": float(flag_budget),
            "holdout_steps": int(holdout_steps),
            "wf_warmup_steps": int(wf_warmup_steps),
            "wf_retrain_every_steps": int(wf_retrain_every_steps),
            "threshold_grid_step": float(threshold_grid_step),
            "random_seed": int(random_seed),
            "use_gpu": bool(use_gpu),
            "gpu_devices": None if gpu_devices is None else str(gpu_devices),
            "wf_progress_every_steps": int(wf_progress_every_steps),
            "feature_policy": str(feature_policy),
            "strict_leakage_guard": bool(strict_leakage_guard),
            "save_feature_provenance": bool(save_feature_provenance),
        },
        "dataset": {
            "rows_total": int(n),
            "rows_train": int(split_idx),
            "rows_holdout": int(holdout),
            "rows_walkforward": int(len(wf_df)),
            "positive_share_total": float(feature_df["is_bad_regime"].mean()),
            "positive_share_train": float(train_df["is_bad_regime"].mean()),
            "positive_share_holdout": float(holdout_df["is_bad_regime"].mean()),
        },
        "features": {
            "count": int(len(feature_cols)),
            "columns": feature_cols,
            "feature_counts": {
                "total_candidates": int(len(feature_provenance_df)),
                "allowed": int(len(feature_cols)),
                "dropped": int(len(feature_provenance_df) - len(feature_cols)),
            },
            "dropped_by_reason": leakage_audit["dropped_by_reason"],
            "leakage_guard_passed": bool(leakage_audit["leakage_guard_passed"]),
            "top_importance": feature_importance_df.head(30).to_dicts(),
        },
        "leakage_audit": {
            "forbidden_patterns_in_selected": leakage_audit[
                "forbidden_patterns_in_selected"
            ],
            "selected_leak_rows": leakage_audit["selected_leak_rows"],
        },
        "temporal_integrity_checks": temporal_integrity_checks,
        "model_params": model_params,
        "fit_runtime": {
            "static_fit": static_fit_meta,
        },
        "selected_threshold": float(selected_threshold),
        "threshold_selection": {
            "constraints_relaxed": bool(selected["constraints_relaxed"]),
            "rule": selected["selection_rule"],
            "train_point": {
                "precision": float(selected["precision"]),
                "recall": float(selected["recall"]),
                "f1": float(selected["f1"]),
                "flagged_rate": float(selected["flagged_rate"]),
                "kept_bad_rate": float(selected["kept_bad_rate"]),
                "precision_lift_vs_base": float(selected["precision_lift_vs_base"]),
            },
        },
        "metrics": {
            "train": train_metrics,
            "holdout": holdout_metrics,
            "walkforward": wf_metrics,
        },
        "artifacts": {
            "risk_model_feature_table_parquet": artifacts.feature_table_parquet,
            "risk_model_feature_table_csv": artifacts.feature_table_csv,
            "risk_model_feature_columns_json": artifacts.feature_columns_json,
            "risk_model_feature_provenance_parquet": artifacts.feature_provenance_parquet,
            "risk_model_feature_provenance_csv": artifacts.feature_provenance_csv,
            "risk_model_feature_leakage_audit_json": artifacts.feature_leakage_audit_json,
            "risk_model_train_predictions_parquet": artifacts.train_predictions_parquet,
            "risk_model_train_predictions_csv": artifacts.train_predictions_csv,
            "risk_model_holdout_predictions_parquet": artifacts.holdout_predictions_parquet,
            "risk_model_holdout_predictions_csv": artifacts.holdout_predictions_csv,
            "risk_model_threshold_grid_train_parquet": artifacts.threshold_grid_train_parquet,
            "risk_model_threshold_grid_train_csv": artifacts.threshold_grid_train_csv,
            "risk_model_threshold_grid_holdout_parquet": artifacts.threshold_grid_holdout_parquet,
            "risk_model_threshold_grid_holdout_csv": artifacts.threshold_grid_holdout_csv,
            "risk_model_walkforward_predictions_parquet": artifacts.walkforward_predictions_parquet,
            "risk_model_walkforward_predictions_csv": artifacts.walkforward_predictions_csv,
            "risk_model_operating_policy_json": artifacts.operating_policy_json,
            "risk_model_summary_json": artifacts.summary_json,
        },
        "created_at": datetime.now().isoformat(),
    }
    with open(artifacts.summary_json, "w") as f:
        json.dump(summary, f, indent=2)

    if verbose:
        print("Stage1 correlation risk model")
        print(f"  Run: {run_id} | Unit: {unit}")
        print(f"  Combo-match source: {combo_dir}")
        print(
            f"  Rows: total={n}, train={split_idx}, holdout={holdout}, "
            f"walkforward={len(wf_df)}"
        )
        print(f"  Features: {len(feature_cols)}")
        print(
            f"  Selected threshold={selected_threshold:.4f} "
            f"(budget={float(flag_budget):.3f}, relaxed={bool(selected['constraints_relaxed'])})"
        )
        print(
            "  Leakage guard: "
            f"policy={feature_policy}, "
            f"passed={bool(leakage_audit['leakage_guard_passed'])}, "
            f"dropped={int(leakage_audit['dropped_feature_count'])}"
        )
        print(f"  Dropped by reason: {leakage_audit['dropped_by_reason']}")
        print(
            "  Temporal checks: "
            f"split_monotonic={temporal_integrity_checks['train_holdout_split_monotonic']}, "
            f"wf_idx_alignment={temporal_integrity_checks['walkforward_idx_alignment_all_zero']}"
        )
        print(
            "  Holdout: "
            f"precision={holdout_metrics['precision']:.4f}, "
            f"recall={holdout_metrics['recall']:.4f}, "
            f"f1={holdout_metrics['f1']:.4f}, "
            f"flagged_rate={holdout_metrics['flagged_rate']:.4f}, "
            f"lift={holdout_metrics['precision_lift_vs_base']:.3f}, "
            f"auc={holdout_metrics['auc']}, pr_auc={holdout_metrics['pr_auc']}"
        )
        print(
            "  Walk-forward: "
            f"precision={wf_metrics['precision']:.4f}, "
            f"recall={wf_metrics['recall']:.4f}, "
            f"f1={wf_metrics['f1']:.4f}, "
            f"flagged_rate={wf_metrics['flagged_rate']:.4f}, "
            f"lift={wf_metrics['precision_lift_vs_base']:.3f}, "
            f"auc={wf_metrics['auc']}, pr_auc={wf_metrics['pr_auc']}"
        )
        print("  Artifacts:")
        print(f"    {artifacts.summary_json}")

    return {
        "summary": summary,
        "artifacts": summary["artifacts"],
        "selected_threshold": float(selected_threshold),
        "feature_importance_top": feature_importance_df.head(30).to_dicts(),
    }
