"""Per-window training loop for RPF binary classification."""

from __future__ import annotations

import time
from typing import Any

import numpy as np
import polars as pl

from regression_feature_engineering.walkforward.classification.data import (
    classification_numpy_with_extra,
    classification_numpy_with_meta,
    classification_score_rows,
    load_joined_classification_batches,
)
from regression_feature_engineering.walkforward.classification.metrics import (
    binary_metrics_from_predictions,
    classification_objective,
    is_live_safe_decision_policy,
    flatten_metrics,
    select_decision_threshold,
    signal_predictions,
    stable_signal_quality_score,
    stable_prediction_quality_score,
    window_stability_constraints_reason,
    window_stability_metrics,
)
from regression_feature_engineering.walkforward.classification.model import (
    fit_classifier,
    fit_prediction_classifier,
    model_diagnostics,
    model_feature_rows,
    prediction_probability,
    validation_probability,
)
from regression_feature_engineering.walkforward.classification.sequence import (
    SequenceEmbeddingConfig,
    append_causal_sequence_embeddings,
    sequence_feature_names,
)
from regression_feature_engineering.walkforward.ema_regime import filter_frame_to_ema_regime
from regression_feature_engineering.walkforward.policy import (
    ALL_MANIFEST_FEATURES,
    ELASTICNET_LOGISTIC_V1,
    FeaturePolicyConfig,
    FeaturePolicyResult,
    select_features,
)
from regression_feature_engineering.walkforward.data import RPFDataContext
from regression_feature_engineering.walkforward.windows import RPFWindow


SELECTOR_REFIT_VALIDATION_MASK = "validation_mask"
SELECTOR_REFIT_TRAIN_VAL_RESELECT = "train_val_reselect"
SELECTOR_REFIT_MODES = (
    SELECTOR_REFIT_VALIDATION_MASK,
    SELECTOR_REFIT_TRAIN_VAL_RESELECT,
)


def run_classification_windows(
    *,
    context: RPFDataContext,
    windows: list[RPFWindow],
    target_col: str,
    feature_columns: tuple[str, ...],
    policy: FeaturePolicyConfig,
    model_updates: dict[str, Any],
    model_family: str,
    task_type: str,
    thread_count: int,
    threshold_mode: str,
    fixed_threshold: float,
    threshold_grid: tuple[float, ...],
    max_signals_grid: tuple[int, ...],
    decision_policy: str,
    objective_metric: str,
    trial_objective_split: str,
    fp_cost: float,
    fn_cost: float,
    tp_reward: float,
    fbeta_beta: float,
    min_validation_recall: float,
    min_validation_precision: float,
    min_validation_predicted_positive_rate: float,
    max_validation_false_positive_rate: float,
    min_threshold_pass_rate: float,
    max_prediction_zero_positive_window_rate: float,
    max_prediction_all_positive_window_rate: float,
    prediction_all_positive_rate_threshold: float,
    max_prediction_high_fpr_window_rate: float,
    max_prediction_window_false_positive_rate: float,
    max_prediction_high_cost_window_rate: float,
    max_prediction_window_decision_cost_per_row: float,
    prediction_high_target_positive_rate_threshold: float,
    min_prediction_high_target_window_recall: float,
    min_prediction_high_target_window_signal_rate: float,
    max_prediction_missed_high_target_window_rate: float,
    prediction_low_target_positive_rate_threshold: float,
    max_prediction_low_target_all_positive_window_rate: float,
    selector_refit_mode: str,
    log_every_windows: int,
    sequence_config: SequenceEmbeddingConfig | None = None,
    sequence_feature_columns: tuple[str, ...] | None = None,
    ema_regime_filter: Any | None = None,
) -> dict[str, Any]:
    val_true: list[np.ndarray] = []
    val_prob: list[np.ndarray] = []
    val_pred_labels: list[np.ndarray] = []
    pred_true: list[np.ndarray] = []
    pred_prob: list[np.ndarray] = []
    pred_pred_labels: list[np.ndarray] = []
    selected_counts: list[int] = []
    window_payloads: list[dict[str, Any]] = []
    skipped_window_metrics: list[dict[str, Any]] = []
    validation_scores: list[dict[str, Any]] = []
    prediction_scores: list[dict[str, Any]] = []
    selected_feature_rows: list[dict[str, Any]] = []
    log_every = max(0, int(log_every_windows))
    sequence_config = sequence_config or SequenceEmbeddingConfig()
    sequence_feature_columns = tuple(sequence_feature_columns or ())
    load_feature_columns = tuple(dict.fromkeys((*feature_columns, *sequence_feature_columns)))
    selector_refit_mode = str(selector_refit_mode)
    if selector_refit_mode not in SELECTOR_REFIT_MODES:
        raise ValueError(f"Unsupported selector_refit_mode={selector_refit_mode!r}; expected one of {SELECTOR_REFIT_MODES}")
    for window_idx, window in enumerate(windows, start=1):
        window_started = time.perf_counter()
        if log_every and (window_idx == 1 or window_idx == len(windows) or window_idx % log_every == 0):
            print(
                "[rpf-cls] window_start "
                f"{window_idx}/{len(windows)} pred_batch={int(window.pred_batch_id)}",
                flush=True,
            )
        load_started = time.perf_counter()
        train = load_joined_classification_batches(
            context,
            window.train_batch_ids,
            feature_columns=load_feature_columns,
            target_col=target_col,
        )
        val = load_joined_classification_batches(
            context,
            window.val_batch_ids,
            feature_columns=load_feature_columns,
            target_col=target_col,
        )
        pred = load_joined_classification_batches(
            context,
            (window.pred_batch_id,),
            feature_columns=load_feature_columns,
            target_col=target_col,
        )
        load_elapsed = time.perf_counter() - load_started
        train_rows_raw = int(train.height)
        val_rows_raw = int(val.height)
        pred_rows_raw = int(pred.height)
        if ema_regime_filter is not None:
            train = filter_frame_to_ema_regime(train, ema_regime_filter, allow_empty=True)
            val = filter_frame_to_ema_regime(val, ema_regime_filter, allow_empty=True)
            pred = filter_frame_to_ema_regime(pred, ema_regime_filter, allow_empty=True)
        skip_reason = skip_window_reason(train, val, pred)
        if skip_reason is not None:
            skipped_window_metrics.append(skipped_window_row(window, skip_reason, train, val, pred, train_rows_raw, val_rows_raw, pred_rows_raw))
            continue
        validation_select_started = time.perf_counter()
        policy_result = select_features(train, target_col=target_col, feature_columns=feature_columns, config=policy)
        selected = policy_result.selected_features
        validation_select_elapsed = time.perf_counter() - validation_select_started
        if policy.policy != ALL_MANIFEST_FEATURES:
            selected_feature_rows.extend(
                selection_detail_rows(
                    detail=policy_result.detail,
                    target_col=target_col,
                    step_idx=int(window.step_idx),
                    pred_batch_id=int(window.pred_batch_id),
                    policy_name=policy.policy,
                    selection_phase="validation_train",
                )
        )
        if sequence_feature_columns and sequence_config.enabled:
            X_train, X_seq_train, y_train, _ = classification_numpy_with_extra(
                train,
                target_col=target_col,
                features=selected,
                extra_features=sequence_feature_columns,
            )
            X_val, X_seq_val, y_val, val_meta = classification_numpy_with_extra(
                val,
                target_col=target_col,
                features=selected,
                extra_features=sequence_feature_columns,
            )
        else:
            X_train, y_train, _ = classification_numpy_with_meta(train, target_col=target_col, features=selected)
            X_val, y_val, val_meta = classification_numpy_with_meta(val, target_col=target_col, features=selected)
            X_seq_train = None
            X_seq_val = None
        skip_reason = skip_validation_model_arrays_reason(y_train, y_val)
        if skip_reason is not None:
            skipped_window_metrics.append(
                skipped_model_array_row(
                    window,
                    skip_reason,
                    len(selected),
                    y_train,
                    y_val,
                    np.asarray([], dtype=int),
                    train_rows_raw,
                    val_rows_raw,
                    pred_rows_raw,
                )
            )
            continue
        X_train, X_val, _, validation_transform_diagnostics = apply_policy_feature_transform(
            policy=policy,
            policy_result=policy_result,
            selected=selected,
            X_train=X_train,
            X_val=X_val,
            X_pred=X_val,
        )
        if X_seq_train is not None and X_seq_val is not None:
            X_seq_train, X_seq_val = train_only_standardize_pair(X_seq_train, X_seq_val)
        X_train, X_val, validation_sequence_diagnostics = append_causal_sequence_embeddings(
            X_train=X_train,
            y_train=y_train,
            X_future=X_val,
            config=sequence_config,
            X_sequence_train=X_seq_train,
            X_sequence_future=X_seq_val,
        )
        validation_feature_names = tuple(selected) + sequence_feature_names(sequence_config)
        validation_fit_started = time.perf_counter()
        validation_fit = fit_classifier(
            X_train,
            y_train,
            X_val,
            y_val,
            model_family=model_family,
            feature_names=validation_feature_names,
            model_updates=model_updates,
            task_type=task_type,
            thread_count=thread_count,
        )
        validation_fit_elapsed = time.perf_counter() - validation_fit_started
        val_p = validation_probability(validation_fit, X_val)
        threshold_result = select_decision_threshold(
            y_val,
            val_p,
            threshold_mode=threshold_mode,
            fixed_threshold=fixed_threshold,
            threshold_grid=threshold_grid,
            max_signals_grid=max_signals_grid,
            decision_policy=decision_policy,
            objective_metric=objective_metric,
            fp_cost=fp_cost,
            fn_cost=fn_cost,
            tp_reward=tp_reward,
            fbeta_beta=fbeta_beta,
            min_recall=min_validation_recall,
            min_precision=min_validation_precision,
            min_predicted_positive_rate=min_validation_predicted_positive_rate,
            max_false_positive_rate=max_validation_false_positive_rate,
        )
        threshold = float(threshold_result["threshold"])
        max_signals = int(threshold_result.get("max_signals", 0))
        selected_decision_policy = str(threshold_result.get("decision_policy", decision_policy))
        decision_policy_live_safe = bool(
            threshold_result.get("decision_policy_live_safe", is_live_safe_decision_policy(selected_decision_policy))
        )

        train_val = pl.concat([train, val], how="vertical")
        prediction_select_started = time.perf_counter()
        if policy.policy == ELASTICNET_LOGISTIC_V1 and selector_refit_mode == SELECTOR_REFIT_VALIDATION_MASK:
            prediction_policy_result = fixed_selected_policy_result(
                train_val,
                selected=selected,
                validation_detail=policy_result.detail,
            )
        else:
            prediction_policy_result = select_features(
                train_val,
                target_col=target_col,
                feature_columns=feature_columns,
                config=policy,
            )
        prediction_selected = prediction_policy_result.selected_features
        prediction_select_elapsed = time.perf_counter() - prediction_select_started
        mask_overlap = selected_feature_overlap(selected, prediction_selected)
        selected_counts.append(len(prediction_selected))
        if policy.policy != ALL_MANIFEST_FEATURES:
            selected_feature_rows.extend(
                selection_detail_rows(
                    detail=prediction_policy_result.detail,
                    target_col=target_col,
                    step_idx=int(window.step_idx),
                    pred_batch_id=int(window.pred_batch_id),
                    policy_name=policy.policy,
                    selection_phase="prediction_train_val",
                )
            )
        if sequence_feature_columns and sequence_config.enabled:
            X_train_val, X_seq_train_val, y_train_val, _ = classification_numpy_with_extra(
                train_val,
                target_col=target_col,
                features=prediction_selected,
                extra_features=sequence_feature_columns,
            )
            X_pred, X_seq_pred, y_pred, pred_meta = classification_numpy_with_extra(
                pred,
                target_col=target_col,
                features=prediction_selected,
                extra_features=sequence_feature_columns,
            )
        else:
            X_train_val, y_train_val, _ = classification_numpy_with_meta(
                train_val,
                target_col=target_col,
                features=prediction_selected,
            )
            X_pred, y_pred, pred_meta = classification_numpy_with_meta(
                pred,
                target_col=target_col,
                features=prediction_selected,
            )
            X_seq_train_val = None
            X_seq_pred = None
        skip_reason = skip_model_arrays_reason(y_train_val, y_val, y_pred)
        if skip_reason is not None:
            skipped_window_metrics.append(
                skipped_model_array_row(
                    window,
                    skip_reason,
                    len(prediction_selected),
                    y_train_val,
                    y_val,
                    y_pred,
                    train_rows_raw,
                    val_rows_raw,
                    pred_rows_raw,
                )
            )
            continue
        X_train_val, _, X_pred, prediction_transform_diagnostics = apply_policy_feature_transform(
            policy=policy,
            policy_result=prediction_policy_result,
            selected=prediction_selected,
            X_train=X_train_val,
            X_val=X_pred,
            X_pred=X_pred,
        )
        if X_seq_train_val is not None and X_seq_pred is not None:
            X_seq_train_val, X_seq_pred = train_only_standardize_pair(X_seq_train_val, X_seq_pred)
        X_train_val, X_pred, prediction_sequence_diagnostics = append_causal_sequence_embeddings(
            X_train=X_train_val,
            y_train=y_train_val,
            X_future=X_pred,
            config=sequence_config,
            X_sequence_train=X_seq_train_val,
            X_sequence_future=X_seq_pred,
        )
        prediction_feature_names = tuple(prediction_selected) + sequence_feature_names(sequence_config)
        prediction_fit_started = time.perf_counter()
        model = fit_prediction_classifier(
            X_train_val,
            y_train_val,
            validation_fit=validation_fit,
            model_family=model_family,
            feature_names=prediction_feature_names,
            model_updates=model_updates,
            task_type=task_type,
            thread_count=thread_count,
        )
        prediction_fit_elapsed = time.perf_counter() - prediction_fit_started
        pred_p = prediction_probability(model, X_pred)
        val_pred_label = signal_predictions(
            val_p,
            threshold=threshold,
            max_signals=max_signals,
            decision_policy=selected_decision_policy,
        )
        pred_pred_label = signal_predictions(
            pred_p,
            threshold=threshold,
            max_signals=max_signals,
            decision_policy=selected_decision_policy,
        )
        elapsed = time.perf_counter() - window_started
        if log_every and (window_idx == 1 or window_idx == len(windows) or window_idx % log_every == 0):
            print(
                "[rpf-cls] window_done "
                f"{window_idx}/{len(windows)} pred_batch={int(window.pred_batch_id)} "
                f"val_features={len(selected)} pred_features={len(prediction_selected)} "
                f"mask_jaccard={mask_overlap['jaccard']:.3g} "
                f"threshold={threshold:.4g} max_signals={max_signals} decision_policy={selected_decision_policy} "
                f"elapsed_s={elapsed:.2f} "
                f"load_s={load_elapsed:.2f} val_select_s={validation_select_elapsed:.2f} "
                f"val_fit_s={validation_fit_elapsed:.2f} pred_select_s={prediction_select_elapsed:.2f} "
                f"pred_fit_s={prediction_fit_elapsed:.2f}",
                flush=True,
            )
        selected_feature_rows.extend(
            model_feature_rows(
                model,
                target_col=target_col,
                step_idx=int(window.step_idx),
                pred_batch_id=int(window.pred_batch_id),
            )
        )
        val_true.append(y_val)
        val_prob.append(val_p)
        val_pred_labels.append(val_pred_label)
        pred_true.append(y_pred)
        pred_prob.append(pred_p)
        pred_pred_labels.append(pred_pred_label)
        window_payloads.append(
            {
                "step_idx": int(window.step_idx),
                "pred_batch_id": int(window.pred_batch_id),
                "window_status": "ok",
                "skip_reason": None,
                "selected_feature_count": len(selected),
                "train_rows_raw": train_rows_raw,
                "val_rows_raw": val_rows_raw,
                "pred_rows_raw": pred_rows_raw,
                "train_rows": int(len(y_train)),
                "val_rows": int(len(y_val)),
                "pred_rows": int(len(y_pred)),
                "train_val_rows": int(len(y_train_val)),
                "train_positive_rate": float(np.mean(y_train)),
                "train_val_positive_rate": float(np.mean(y_train_val)),
                "validation_selected_feature_count": len(selected),
                "prediction_selected_feature_count": len(prediction_selected),
                "selector_refit_mode": selector_refit_mode,
                "selected_feature_overlap_count": mask_overlap["overlap"],
                "selected_feature_union_count": mask_overlap["union"],
                "selected_feature_jaccard": mask_overlap["jaccard"],
                "validation_model_feature_count": int(X_train.shape[1]),
                "prediction_model_feature_count": int(X_train_val.shape[1]),
                "timing_load_s": float(load_elapsed),
                "timing_validation_select_s": float(validation_select_elapsed),
                "timing_validation_fit_s": float(validation_fit_elapsed),
                "timing_prediction_select_s": float(prediction_select_elapsed),
                "timing_prediction_fit_s": float(prediction_fit_elapsed),
                "timing_total_s": float(elapsed),
                "y_val": y_val,
                "val_prob": val_p,
                "val_pred_label": val_pred_label,
                "val_meta": val_meta,
                "y_pred": y_pred,
                "pred_prob": pred_p,
                "pred_pred_label": pred_pred_label,
                "pred_meta": pred_meta,
                "selected_threshold": threshold,
                "selected_max_signals": max_signals,
                "decision_policy": selected_decision_policy,
                "decision_policy_live_safe": decision_policy_live_safe,
                "threshold_constraints_pass": bool(threshold_result["constraints_pass"]),
                "threshold_constraints_reason": str(threshold_result["constraints_reason"]),
                **model_diagnostics(model),
                **prefixed_transform_diagnostics(validation_transform_diagnostics, "validation"),
                **prefixed_transform_diagnostics(prediction_transform_diagnostics, "prediction"),
                **prefixed_transform_diagnostics(validation_sequence_diagnostics, "validation"),
                **prefixed_transform_diagnostics(prediction_sequence_diagnostics, "prediction"),
                "feature_transform_policy": prediction_transform_diagnostics["feature_transform_policy"],
                "feature_scaler_fit_rows": prediction_transform_diagnostics["feature_scaler_fit_rows"],
                "feature_scaler_selected_count": prediction_transform_diagnostics["feature_scaler_selected_count"],
            }
        )
    if not val_true or not pred_true:
        raise ValueError(
            "No executable classification windows after filtering; "
            f"attempted={len(windows)} skipped={len(skipped_window_metrics)}"
        )
    y_val_all = np.concatenate(val_true)
    val_prob_all = np.concatenate(val_prob)
    val_pred_all = np.concatenate(val_pred_labels)
    y_pred_all = np.concatenate(pred_true)
    pred_prob_all = np.concatenate(pred_prob)
    pred_pred_all = np.concatenate(pred_pred_labels)
    window_metrics: list[dict[str, Any]] = list(skipped_window_metrics)
    threshold_values_used: list[float] = []
    max_signals_values_used: list[int] = []
    threshold_passes: list[bool] = []
    threshold_reasons: list[str] = []
    for payload in window_payloads:
        val_y = payload.pop("y_val")
        val_p = payload.pop("val_prob")
        val_pred_label = payload.pop("val_pred_label")
        val_meta = payload.pop("val_meta")
        pred_y = payload.pop("y_pred")
        pred_p = payload.pop("pred_prob")
        pred_pred_label = payload.pop("pred_pred_label")
        pred_meta = payload.pop("pred_meta")
        threshold = float(payload["selected_threshold"])
        max_signals = int(payload["selected_max_signals"])
        selected_decision_policy = str(payload["decision_policy"])
        decision_policy_live_safe = bool(payload["decision_policy_live_safe"])
        threshold_values_used.append(threshold)
        max_signals_values_used.append(max_signals)
        threshold_passes.append(bool(payload["threshold_constraints_pass"]))
        threshold_reasons.append(str(payload["threshold_constraints_reason"]))
        validation_scores.extend(
            classification_score_rows(
                meta=val_meta,
                y_true=val_y,
                prob=val_p,
                threshold=threshold,
                pred=val_pred_label,
                max_signals=max_signals,
                decision_policy=selected_decision_policy,
                decision_policy_live_safe=decision_policy_live_safe,
                target_col=target_col,
                step_idx=int(payload["step_idx"]),
                pred_batch_id=int(payload["pred_batch_id"]),
                split="validation",
            )
        )
        prediction_scores.extend(
            classification_score_rows(
                meta=pred_meta,
                y_true=pred_y,
                prob=pred_p,
                threshold=threshold,
                pred=pred_pred_label,
                max_signals=max_signals,
                decision_policy=selected_decision_policy,
                decision_policy_live_safe=decision_policy_live_safe,
                target_col=target_col,
                step_idx=int(payload["step_idx"]),
                pred_batch_id=int(payload["pred_batch_id"]),
                split="prediction",
            )
        )
        val_m = binary_metrics_from_predictions(
            val_y,
            val_p,
            val_pred_label,
            threshold=threshold,
            fp_cost=fp_cost,
            fn_cost=fn_cost,
            tp_reward=tp_reward,
            fbeta_beta=fbeta_beta,
        )
        pred_m = binary_metrics_from_predictions(
            pred_y,
            pred_p,
            pred_pred_label,
            threshold=threshold,
            fp_cost=fp_cost,
            fn_cost=fn_cost,
            tp_reward=tp_reward,
            fbeta_beta=fbeta_beta,
        )
        window_metrics.append(
            {
                **payload,
                "selected_threshold": threshold,
                "selected_max_signals": max_signals,
                "decision_policy": selected_decision_policy,
                "decision_policy_live_safe": decision_policy_live_safe,
                **flatten_metrics(val_m, "validation"),
                **flatten_metrics(pred_m, "prediction"),
            }
        )
    validation_metrics = binary_metrics_from_predictions(
        y_val_all,
        val_prob_all,
        val_pred_all,
        threshold=None,
        fp_cost=fp_cost,
        fn_cost=fn_cost,
        tp_reward=tp_reward,
        fbeta_beta=fbeta_beta,
    )
    prediction_metrics = binary_metrics_from_predictions(
        y_pred_all,
        pred_prob_all,
        pred_pred_all,
        threshold=None,
        fp_cost=fp_cost,
        fn_cost=fn_cost,
        tp_reward=tp_reward,
        fbeta_beta=fbeta_beta,
    )
    prediction_window_stability = window_stability_metrics(
        window_metrics,
        split="prediction",
        all_positive_rate_threshold=float(prediction_all_positive_rate_threshold),
        high_false_positive_rate_threshold=float(max_prediction_window_false_positive_rate),
        high_decision_cost_per_row_threshold=float(max_prediction_window_decision_cost_per_row),
        high_target_positive_rate_threshold=float(prediction_high_target_positive_rate_threshold),
        min_high_target_window_recall=float(min_prediction_high_target_window_recall),
        min_high_target_window_signal_rate=float(min_prediction_high_target_window_signal_rate),
        low_target_positive_rate_threshold=float(prediction_low_target_positive_rate_threshold),
    )
    prediction_window_stability_reason = window_stability_constraints_reason(
        prediction_window_stability,
        max_zero_positive_window_rate=float(max_prediction_zero_positive_window_rate),
        max_all_positive_window_rate=float(max_prediction_all_positive_window_rate),
        max_high_fpr_window_rate=float(max_prediction_high_fpr_window_rate),
        max_high_cost_window_rate=float(max_prediction_high_cost_window_rate),
        max_missed_high_target_window_rate=float(max_prediction_missed_high_target_window_rate),
        max_low_target_all_positive_window_rate=float(max_prediction_low_target_all_positive_window_rate),
    )
    prediction_window_stability_pass = prediction_window_stability_reason == "pass"
    threshold_pass_rate = float(np.mean(threshold_passes)) if threshold_passes else 0.0
    if str(objective_metric) == "stable_prediction_quality":
        objective_direction = "maximize"
        score_components = stable_prediction_quality_score(
            prediction_metrics,
            prediction_window_stability,
            threshold_pass_rate=threshold_pass_rate,
            selected_feature_count_mean=float(np.mean(selected_counts)) if selected_counts else 0.0,
        )
        objective_value = float(score_components["score"])
    elif str(objective_metric) == "stable_signal_quality":
        objective_direction = "maximize"
        score_components = stable_signal_quality_score(
            prediction_metrics,
            prediction_window_stability,
            threshold_pass_rate=threshold_pass_rate,
            selected_feature_count_mean=float(np.mean(selected_counts)) if selected_counts else 0.0,
        )
        objective_value = float(score_components["score"])
    else:
        objective_metrics = prediction_metrics if str(trial_objective_split) == "prediction" else validation_metrics
        objective_direction, objective_value = classification_objective(objective_metrics, objective_metric)
        score_components = {}
    threshold_constraints_pass = threshold_pass_rate >= float(min_threshold_pass_rate)
    threshold_constraints_reason = (
        "pass"
        if threshold_constraints_pass
        else (
            f"threshold_pass_rate_below_min:{threshold_pass_rate:.6g}<"
            f"{float(min_threshold_pass_rate):.6g};"
            + (",".join(sorted({reason for reason in threshold_reasons if reason != "pass"})) or "threshold_constraint_failed")
        )
    )
    if should_force_bad_objective(
        objective_metric=str(objective_metric),
        threshold_constraints_pass=threshold_constraints_pass,
        prediction_window_stability_pass=prediction_window_stability_pass,
    ):
        objective_value = 1e9 if objective_direction == "minimize" else -1e9
    return {
        "validation_metrics": validation_metrics,
        "prediction_metrics": prediction_metrics,
        "objective_metric": objective_metric,
        "trial_objective_split": str(trial_objective_split),
        "objective_direction": objective_direction,
        "objective_value": objective_value,
        "objective_components": score_components,
        "selected_threshold": float(np.mean(threshold_values_used)) if threshold_values_used else None,
        "selected_threshold_min": float(np.min(threshold_values_used)) if threshold_values_used else None,
        "selected_threshold_max": float(np.max(threshold_values_used)) if threshold_values_used else None,
        "selected_max_signals": float(np.mean(max_signals_values_used)) if max_signals_values_used else None,
        "selected_max_signals_min": int(np.min(max_signals_values_used)) if max_signals_values_used else None,
        "selected_max_signals_max": int(np.max(max_signals_values_used)) if max_signals_values_used else None,
        "decision_policy": str(decision_policy),
        "decision_policy_live_safe": bool(is_live_safe_decision_policy(decision_policy)),
        "threshold_constraints_pass": bool(threshold_constraints_pass),
        "threshold_constraints_pass_rate": threshold_pass_rate,
        "min_threshold_pass_rate": float(min_threshold_pass_rate),
        "threshold_constraints_reason": threshold_constraints_reason,
        "prediction_window_stability_pass": bool(prediction_window_stability_pass),
        "prediction_window_stability_reason": prediction_window_stability_reason,
        "prediction_window_stability": prediction_window_stability,
        "selected_feature_count_min": min(selected_counts) if selected_counts else 0,
        "selected_feature_count_mean": float(np.mean(selected_counts)) if selected_counts else 0.0,
        "attempted_window_count": len(windows),
        "executed_window_count": len(window_payloads),
        "skipped_window_count": len(skipped_window_metrics),
        "skipped_window_rate": float(len(skipped_window_metrics) / len(windows)) if windows else 0.0,
        "window_metrics": window_metrics,
        "validation_scores": validation_scores,
        "prediction_scores": prediction_scores,
        "selected_feature_rows": selected_feature_rows,
    }


def should_force_bad_objective(
    *,
    objective_metric: str,
    threshold_constraints_pass: bool,
    prediction_window_stability_pass: bool,
) -> bool:
    if str(objective_metric) in {"stable_prediction_quality", "stable_signal_quality"}:
        return False
    return not bool(threshold_constraints_pass) or not bool(prediction_window_stability_pass)


def selected_feature_overlap(validation_selected: tuple[str, ...], prediction_selected: tuple[str, ...]) -> dict[str, Any]:
    validation_set = set(validation_selected)
    prediction_set = set(prediction_selected)
    overlap = len(validation_set & prediction_set)
    union = len(validation_set | prediction_set)
    return {
        "overlap": int(overlap),
        "union": int(union),
        "jaccard": float(overlap / union) if union else 1.0,
    }


def fixed_selected_policy_result(
    frame: pl.DataFrame,
    *,
    selected: tuple[str, ...],
    validation_detail: pl.DataFrame,
) -> FeaturePolicyResult:
    if not selected:
        raise ValueError("Cannot refit prediction model with an empty validation-selected feature mask")
    missing = [feature for feature in selected if feature not in frame.columns]
    if missing:
        raise ValueError(f"Validation-selected features are missing from train+validation frame: {missing[:5]}")
    stats = frame.select(
        [
            pl.col(feature).cast(pl.Float64).mean().alias(f"{feature}__mean")
            for feature in selected
        ]
        + [
            pl.col(feature).cast(pl.Float64).std(ddof=0).alias(f"{feature}__std")
            for feature in selected
        ]
    ).row(0, named=True)
    validation_rows: dict[str, dict[str, Any]] = {}
    if not validation_detail.is_empty() and "feature" in validation_detail.columns:
        validation_rows = {str(row["feature"]): dict(row) for row in validation_detail.iter_rows(named=True)}
    detail_rows: list[dict[str, Any]] = []
    for feature in selected:
        base = dict(validation_rows.get(feature, {}))
        mean_value = stats.get(f"{feature}__mean")
        std_value = stats.get(f"{feature}__std")
        if mean_value is None or std_value is None or not np.isfinite(float(mean_value)) or not np.isfinite(float(std_value)):
            raise ValueError(f"Invalid train+validation scaler stats for validation-selected feature: {feature}")
        if float(std_value) <= 1e-12:
            raise ValueError(f"Constant train+validation selected feature after validation-mask freeze: {feature}")
        base.update(
            {
                "feature": feature,
                "feature_mean_train": float(mean_value),
                "feature_std_train": float(std_value),
                "final_status": "selected",
                "drop_reason": None,
            }
        )
        detail_rows.append(base)
    return FeaturePolicyResult(
        selected_features=tuple(selected),
        clip_bounds={},
        detail=pl.DataFrame(detail_rows, infer_schema_length=None),
    )


def skip_window_reason(train: pl.DataFrame, val: pl.DataFrame, pred: pl.DataFrame) -> str | None:
    if train.is_empty():
        return "empty_train_after_regime_filter"
    if val.is_empty():
        return "empty_validation_after_regime_filter"
    if pred.is_empty():
        return "empty_prediction_after_regime_filter"
    return None


def skip_model_arrays_reason(y_train: np.ndarray, y_val: np.ndarray, y_pred: np.ndarray) -> str | None:
    validation_skip = skip_validation_model_arrays_reason(y_train, y_val)
    if validation_skip is not None:
        return validation_skip
    if len(y_pred) == 0:
        return "empty_prediction_after_model_matrix_filter"
    return None


def skip_validation_model_arrays_reason(y_train: np.ndarray, y_val: np.ndarray) -> str | None:
    if len(y_train) == 0:
        return "empty_train_after_model_matrix_filter"
    if len(y_val) == 0:
        return "empty_validation_after_model_matrix_filter"
    if len(np.unique(y_train)) < 2:
        return "single_class_train"
    return None


def apply_policy_feature_transform(
    *,
    policy: FeaturePolicyConfig,
    policy_result: FeaturePolicyResult,
    selected: tuple[str, ...],
    X_train: np.ndarray,
    X_val: np.ndarray,
    X_pred: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict[str, Any]]:
    if policy.policy != ELASTICNET_LOGISTIC_V1:
        return (
            X_train,
            X_val,
            X_pred,
            {
                "feature_transform_policy": "materialized_rpf",
                "feature_scaler_fit_rows": None,
                "feature_scaler_selected_count": None,
                "feature_scaler_std_min": None,
                "feature_scaler_std_median": None,
            },
        )
    means, stds = elasticnet_selector_scaler_stats(policy_result, selected)
    X_train_scaled = scale_matrix_with_train_stats(X_train, means, stds)
    X_val_scaled = scale_matrix_with_train_stats(X_val, means, stds)
    X_pred_scaled = scale_matrix_with_train_stats(X_pred, means, stds)
    return (
        X_train_scaled,
        X_val_scaled,
        X_pred_scaled,
        {
            "feature_transform_policy": "elasticnet_train_standardize",
            "feature_scaler_fit_rows": int(X_train.shape[0]),
            "feature_scaler_selected_count": int(len(selected)),
            "feature_scaler_std_min": float(np.min(stds)) if len(stds) else None,
            "feature_scaler_std_median": float(np.median(stds)) if len(stds) else None,
        },
    )


def elasticnet_selector_scaler_stats(
    policy_result: FeaturePolicyResult,
    selected: tuple[str, ...],
) -> tuple[np.ndarray, np.ndarray]:
    if not selected:
        raise ValueError("Cannot scale an empty ElasticNet-selected feature panel")
    required = {"feature", "feature_mean_train", "feature_std_train"}
    missing = required.difference(policy_result.detail.columns)
    if missing:
        raise ValueError(f"ElasticNet selector detail is missing scaler columns: {sorted(missing)}")
    rows = policy_result.detail.filter(pl.col("feature").is_in(selected)).select(
        ["feature", "feature_mean_train", "feature_std_train"]
    )
    stats = {
        str(row["feature"]): (float(row["feature_mean_train"]), float(row["feature_std_train"]))
        for row in rows.iter_rows(named=True)
    }
    missing_selected = [feature for feature in selected if feature not in stats]
    if missing_selected:
        raise ValueError(f"ElasticNet selector detail is missing selected feature stats: {missing_selected[:5]}")
    means = np.asarray([stats[feature][0] for feature in selected], dtype=float)
    stds = np.asarray([stats[feature][1] for feature in selected], dtype=float)
    valid = np.isfinite(means) & np.isfinite(stds) & (stds > 1e-12)
    if not bool(valid.all()):
        bad = [selected[idx] for idx in np.flatnonzero(~valid)[:5]]
        raise ValueError(f"ElasticNet-selected features have invalid train scaler stats: {bad}")
    return means, stds


def scale_matrix_with_train_stats(X: np.ndarray, means: np.ndarray, stds: np.ndarray) -> np.ndarray:
    scaled = (np.asarray(X, dtype=float) - means) / stds
    return np.nan_to_num(scaled, copy=False, nan=0.0, posinf=0.0, neginf=0.0)


def train_only_standardize_pair(X_train: np.ndarray, X_future: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    train = np.asarray(X_train, dtype=float)
    future = np.asarray(X_future, dtype=float)
    means = np.nanmean(train, axis=0)
    stds = np.nanstd(train, axis=0)
    valid = np.isfinite(means) & np.isfinite(stds) & (stds > 1e-12)
    means = np.where(np.isfinite(means), means, 0.0)
    stds = np.where(valid, stds, 1.0)
    return (
        scale_matrix_with_train_stats(train, means, stds).astype("float32", copy=False),
        scale_matrix_with_train_stats(future, means, stds).astype("float32", copy=False),
    )


def prefixed_transform_diagnostics(diagnostics: dict[str, Any], prefix: str) -> dict[str, Any]:
    return {f"{prefix}_{key}": value for key, value in diagnostics.items()}


def skipped_window_row(
    window: RPFWindow,
    skip_reason: str,
    train: pl.DataFrame,
    val: pl.DataFrame,
    pred: pl.DataFrame,
    train_rows_raw: int,
    val_rows_raw: int,
    pred_rows_raw: int,
) -> dict[str, Any]:
    return {
        "step_idx": int(window.step_idx),
        "pred_batch_id": int(window.pred_batch_id),
        "window_status": "skipped",
        "skip_reason": skip_reason,
        "selected_feature_count": 0,
        "train_rows_raw": train_rows_raw,
        "val_rows_raw": val_rows_raw,
        "pred_rows_raw": pred_rows_raw,
        "train_rows": int(train.height),
        "val_rows": int(val.height),
        "pred_rows": int(pred.height),
        "train_positive_rate": None,
        "validation_rows": int(val.height),
        "prediction_rows": int(pred.height),
    }


def skipped_model_array_row(
    window: RPFWindow,
    skip_reason: str,
    selected_feature_count: int,
    y_train: np.ndarray,
    y_val: np.ndarray,
    y_pred: np.ndarray,
    train_rows_raw: int,
    val_rows_raw: int,
    pred_rows_raw: int,
) -> dict[str, Any]:
    return {
        "step_idx": int(window.step_idx),
        "pred_batch_id": int(window.pred_batch_id),
        "window_status": "skipped",
        "skip_reason": skip_reason,
        "selected_feature_count": selected_feature_count,
        "train_rows_raw": train_rows_raw,
        "val_rows_raw": val_rows_raw,
        "pred_rows_raw": pred_rows_raw,
        "train_rows": int(len(y_train)),
        "val_rows": int(len(y_val)),
        "pred_rows": int(len(y_pred)),
        "train_positive_rate": float(np.mean(y_train)) if len(y_train) else None,
        "validation_rows": int(len(y_val)),
        "prediction_rows": int(len(y_pred)),
    }


def selection_detail_rows(
    *,
    detail: pl.DataFrame,
    target_col: str,
    step_idx: int,
    pred_batch_id: int,
    policy_name: str,
    selection_phase: str,
) -> list[dict[str, Any]]:
    if detail.is_empty() or "final_status" not in detail.columns:
        return []
    selected = detail.filter(pl.col("final_status") == "selected")
    rows: list[dict[str, Any]] = []
    for idx, row in enumerate(selected.iter_rows(named=True), start=1):
        rows.append(
            {
                "target_col": target_col,
                "step_idx": int(step_idx),
                "pred_batch_id": int(pred_batch_id),
                "feature_policy": policy_name,
                "selection_phase": str(selection_phase),
                "selected_rank": int(idx),
                **row,
            }
        )
    return rows
