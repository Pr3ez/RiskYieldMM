"""
5-Minute Timeframe Optimizer for HTF CatBoost Backtest
======================================================

Self-contained 5m optimization with:
- 5m-specific configuration
- 5m-specific search spaces
- Full optimization logic
"""

from dataclasses import dataclass, field
import hashlib
from pathlib import Path
import time

from catboost import CatBoostClassifier
import numpy as np
import optuna
import polars as pl
from sklearn.metrics import balanced_accuracy_score, confusion_matrix, f1_score, log_loss

from ..utils import (
    BaseOptimizerConfig,
    FeatureSearchSpace,
    ModelSearchSpace,
    WindowSearchSpace,
    apply_sample_weights,
    balanced_resample_indices,
    compute_class_counts_up_to,
    compute_directional_accuracy,
    compute_directional_precision,
    compute_cross_direction_error_rate,
    compute_directional_macro_f1,
    compute_class_weights,
    drop_correlated_features,
    estimate_lookback_and_split,
    get_feature_columns,
    load_batch,
    load_batches_range,
    prepare_features_target,
    select_features_by_mi,
    stratified_split_indices,
    weights_to_sample_weights,
)


# ============================================================================
# 5M-SPECIFIC CONFIGURATION
# ============================================================================
@dataclass
class Config5m(BaseOptimizerConfig):
    """
    5m-specific configuration.

    5m has:
    - 96 bars per 8h batch (vs 32 for 15m)
    - More noise, requires more regularization
    - Larger sample sizes, can use larger windows
    """

    # More trials for 5m due to noisier data
    optuna_trials: int = 30
    optuna_timeout: int = 180
    cb_base_params: dict = field(
        default_factory=lambda: {
            "loss_function": "MultiClass",
            "eval_metric": "MultiClass",
            "task_type": "GPU",
            "devices": "0",
            "random_seed": 42,
            "allow_writing_files": False,
            "verbose": False,
            "thread_count": -1,
            "bootstrap_type": "Bernoulli",
        }
    )

    def __post_init__(self) -> None:
        if not isinstance(self.cb_base_params, dict):
            self.cb_base_params = dict(self.cb_base_params)


@dataclass
class WindowSpace5m(WindowSearchSpace):
    """
    5m window search space.

    5m has 96 rows per batch, so even small lookback gives many samples.
    """

    lookback_min: int = 150  # ~14,400 rows minimum
    lookback_max: int = 500  # ~48,000 rows maximum

    # 5m is noisier, recent data more important
    decay_min: float = 0.98
    decay_max: float = 0.9999

    min_samples_per_class: int = 100


@dataclass
class FeatureSpace5m(FeatureSearchSpace):
    """
    5m feature search space.

    5m has more features available, can be more selective.
    """

    feature_k_min: int = 30
    feature_k_max: int = 120

    # 5m features tend to be more correlated
    corr_threshold_min: float = 0.75
    corr_threshold_max: float = 0.95

    var_threshold_min: float = 0.0005
    var_threshold_max: float = 0.01


@dataclass
class ModelSpace5m(ModelSearchSpace):
    """
    5m model search space.

    5m needs more regularization due to noise.
    """

    # More conservative learning rate for noisy data
    learning_rate_min: float = 0.005
    learning_rate_max: float = 0.15

    # Smaller trees to avoid overfitting
    num_leaves_min: int = 16
    num_leaves_max: int = 96

    max_depth_min: int = 3
    max_depth_max: int = 10

    # More samples per leaf for stability
    min_child_samples_min: int = 20
    min_child_samples_max: int = 150

    # Stronger regularization
    reg_lambda_min: float = 1e-4
    reg_lambda_max: float = 50.0

    reg_alpha_min: float = 1e-4
    reg_alpha_max: float = 50.0

    # More aggressive sampling to reduce overfitting
    subsample_min: float = 0.4
    subsample_max: float = 0.9

    colsample_bytree_min: float = 0.4
    colsample_bytree_max: float = 0.9

    feature_fraction_bynode_min: float = 0.4
    feature_fraction_bynode_max: float = 0.9

    # Fewer rounds, rely on early stopping
    num_boost_round_min: int = 100
    num_boost_round_max: int = 800


# ============================================================================
# 5M STEP OPTIMIZER
# ============================================================================
class StepOptimizer5m:
    """
    Optimizer for a single walk-forward step (5m timeframe).

    Workflow:
    1. Estimate lookback + train/val split from class-distribution matching
    2. Optimize feature selection
    3. Optimize model hyperparameters (CatBoost params)
    4. Optimize class weighting
    """

    TIMEFRAME = "5m"

    def __init__(
        self,
        config: Config5m,
        window_space: WindowSpace5m,
        feature_space: FeatureSpace5m,
        model_space: ModelSpace5m,
    ):
        self.config = config
        self.window_space = window_space
        self.feature_space = feature_space
        self.model_space = model_space

    def _stage1_resolve_embargo(self) -> tuple[int, int]:
        """Resolve train/val and val/pred embargo values for stage-1 fold CV."""
        mode = str(getattr(self.window_space, "embargo_mode", "none"))
        tv = getattr(self.window_space, "embargo_train_val_batches", None)
        vp = getattr(self.window_space, "embargo_val_pred_batches", None)
        if mode == "none":
            return 0, 0
        if mode == "fixed":
            return int(max(0, tv or 0)), int(max(0, vp or 0))
        # auto_tf defaults (same intent as deterministic solver path)
        return int(max(0, tv if tv is not None else 1)), int(
            max(0, vp if vp is not None else 1)
        )

    def _stage1_val_batch_values(self) -> list[int]:
        """Resolve validation-window candidates (batches per fold) for stage-1."""
        fixed_val = int(max(1, getattr(self.window_space, "stage1_val_batches_per_fold", 1)))
        val_min = int(max(1, getattr(self.window_space, "stage1_val_batches_min", fixed_val)))
        val_max = int(
            max(
                val_min,
                getattr(self.window_space, "stage1_val_batches_max", val_min),
            )
        )
        val_grid = getattr(self.window_space, "stage1_val_batches_grid", None)
        if val_grid:
            vals = sorted(
                {
                    int(v)
                    for v in val_grid
                    if val_min <= int(v) <= val_max and int(v) >= 1
                }
            )
        else:
            vals = list(range(val_min, val_max + 1))
        return vals or [fixed_val]

    def _stage1_train_batch_values(self, val_batches_per_fold: int) -> list[int]:
        """Resolve train-window candidates for a given validation-window length."""
        train_min = int(max(1, self.window_space.stage1_train_batches_min))
        train_max = int(max(train_min, self.window_space.stage1_train_batches_max))

        multiplier_grid = getattr(self.window_space, "stage1_train_multiplier_grid", None)
        if multiplier_grid:
            vals = sorted(
                {
                    int(val_batches_per_fold) * int(m)
                    for m in multiplier_grid
                    if int(m) >= 1
                    and train_min
                    <= int(val_batches_per_fold) * int(m)
                    <= train_max
                }
            )
            if vals:
                return vals

        train_grid = (
            sorted(
                {
                    int(v)
                    for v in (self.window_space.stage1_train_batches_grid or [])
                    if train_min <= int(v) <= train_max
                }
            )
            if self.window_space.stage1_train_batches_grid
            else None
        )
        return train_grid or list(range(train_min, train_max + 1))

    def _stage1_combo_grid(self) -> tuple[list[int], list[tuple[int, int]], list[tuple[int, int, int]]]:
        """Return fold values, (val,train) pairs, and full (fold,val,train) combos."""
        folds_min = int(max(1, self.window_space.stage1_folds_min))
        folds_max = int(max(folds_min, self.window_space.stage1_folds_max))
        fold_values = list(range(folds_min, folds_max + 1))
        val_values = self._stage1_val_batch_values()
        pair_values = sorted(
            {
                (int(v), int(t))
                for v in val_values
                for t in self._stage1_train_batch_values(v)
            }
        )
        all_combos = [(int(f), int(v), int(t)) for f in fold_values for v, t in pair_values]
        return fold_values, pair_values, all_combos

    def _metric_score(
        self,
        y_true: np.ndarray,
        y_pred: np.ndarray,
        pred_proba: np.ndarray,
    ) -> float:
        """Compute objective score based on configured optuna_metric."""
        from sklearn.metrics import accuracy_score as acc_score

        metric = self.config.optuna_metric
        if metric == "accuracy":
            return float(acc_score(y_true, y_pred))
        if metric == "log_loss":
            return float(
                log_loss(
                    y_true,
                    pred_proba,
                    labels=list(range(self.config.n_classes)),
                )
            )
        if metric == "balanced_accuracy":
            return float(balanced_accuracy_score(y_true, y_pred))
        if metric == "macro_f1":
            return float(f1_score(y_true, y_pred, average="macro", zero_division=0))
        if metric == "macro_f1_up":
            return float(
                compute_directional_macro_f1(
                    y_true, y_pred, list(self.config.class_names), direction=1
                )
            )
        if metric == "macro_f1_down":
            return float(
                compute_directional_macro_f1(
                    y_true, y_pred, list(self.config.class_names), direction=0
                )
            )
        if metric == "directional_accuracy":
            return float(
                compute_directional_accuracy(
                    y_true, y_pred, list(self.config.class_names)
                )
            )
        if metric == "directional_precision_up":
            return float(
                compute_directional_precision(
                    y_true, y_pred, list(self.config.class_names), direction=1
                )
            )
        if metric == "directional_precision_down":
            return float(
                compute_directional_precision(
                    y_true, y_pred, list(self.config.class_names), direction=0
                )
            )
        if metric == "cross_direction_error":
            return float(
                compute_cross_direction_error_rate(
                    y_true, y_pred, list(self.config.class_names)
                )
            )
        raise ValueError(f"Unknown optuna_metric: {metric}")

    def _fit_catboost_with_fallback(
        self,
        params: dict,
        iterations: int,
        X_train: np.ndarray,
        y_train: np.ndarray,
        X_val: np.ndarray,
        y_val: np.ndarray,
    ) -> tuple[CatBoostClassifier, bool]:
        """Train CatBoost with GPU first, then CPU fallback."""
        def _is_unseen_val_class_error(exc: Exception) -> bool:
            msg = str(exc)
            return (
                "contains class label" in msg
                and "not present in the learn dataset" in msg
            )

        def _fit_once(fit_params: dict, use_eval: bool) -> CatBoostClassifier:
            model = CatBoostClassifier(**fit_params, iterations=iterations)
            if use_eval:
                model.fit(
                    X_train,
                    y_train,
                    eval_set=(X_val, y_val),
                    use_best_model=True,
                    early_stopping_rounds=50,
                    verbose=False,
                )
            else:
                # Fallback for folds where validation has unseen classes.
                model.fit(
                    X_train,
                    y_train,
                    use_best_model=False,
                    verbose=False,
                )
            return model

        try:
            return _fit_once(params, use_eval=True), False
        except Exception as gpu_err:
            if _is_unseen_val_class_error(gpu_err):
                try:
                    return _fit_once(params, use_eval=False), False
                except Exception:
                    pass

            params_cpu = params.copy()
            params_cpu["task_type"] = "CPU"
            params_cpu.pop("devices", None)

            try:
                return _fit_once(params_cpu, use_eval=True), True
            except Exception as cpu_err:
                if _is_unseen_val_class_error(cpu_err):
                    return _fit_once(params_cpu, use_eval=False), True
                raise

    def _to_full_class_proba_and_pred(
        self,
        model: CatBoostClassifier,
        raw_pred: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Map model probabilities to full class space [0..n_classes-1]."""
        pred = np.asarray(raw_pred)
        if pred.ndim == 1:
            pred_pos = np.clip(pred, 1e-9, 1.0 - 1e-9)
            pred = np.column_stack([1.0 - pred_pos, pred_pos])

        classes = getattr(model, "classes_", None)
        if classes is None:
            classes_arr = np.arange(pred.shape[1], dtype=int)
        else:
            classes_arr = np.asarray(classes)
            if classes_arr.shape[0] != pred.shape[1]:
                classes_arr = np.arange(pred.shape[1], dtype=int)

        full = np.full((pred.shape[0], self.config.n_classes), 1e-12, dtype=np.float64)
        for src_idx, cls in enumerate(classes_arr):
            try:
                cls_idx = int(cls)
            except Exception:
                continue
            if 0 <= cls_idx < self.config.n_classes:
                full[:, cls_idx] = np.clip(pred[:, src_idx], 1e-12, 1.0)

        row_sum = full.sum(axis=1, keepdims=True)
        row_sum[row_sum <= 0] = 1.0
        full = full / row_sum
        y_pred = full.argmax(axis=1).astype(int)
        return full, y_pred

    def _build_stage1_batch_cache(
        self,
        df_all: pl.DataFrame,
        all_feature_cols: list[str],
    ) -> dict[int, tuple[np.ndarray, np.ndarray]]:
        """Prepare per-batch arrays once for fast stage-1 fold evaluation."""
        cache: dict[int, tuple[np.ndarray, np.ndarray]] = {}
        # partition_by avoids O(N * n_batches) repeated filtering cost.
        for df_b in df_all.partition_by("batch_id", maintain_order=True):
            if len(df_b) == 0:
                continue
            bid = int(df_b["batch_id"][0])
            X_b, y_b, _, _ = prepare_features_target(
                df_b, all_feature_cols, self.config.target
            )
            if X_b is None or len(y_b) == 0:
                continue
            X_b = np.nan_to_num(X_b, nan=0.0, posinf=0.0, neginf=0.0)
            cache[int(bid)] = (X_b, y_b)
        return cache

    def _build_stage1_fold_windows(
        self,
        train_end: int,
        fold_count: int,
        train_batches_per_fold: int,
        val_batches_per_fold: int,
        min_batch: int,
        available_batches: list[int] | None = None,
        batch_positions: dict[int, int] | None = None,
        pred_pos: int | None = None,
    ) -> list[dict]:
        """
        Build rolling fold windows:
        - fold 0 validates on the closest contiguous window before prediction
        - each next fold moves validation earlier by `val_batches_per_fold`
        """
        embargo_tv, embargo_vp = self._stage1_resolve_embargo()
        windows: list[dict] = []
        val_batches_per_fold = int(max(1, val_batches_per_fold))
        if available_batches is not None:
            available = [int(b) for b in available_batches if int(b) <= int(train_end)]
            if not available:
                return []
            local_pos = {int(batch_id): idx for idx, batch_id in enumerate(available)}
            global_pos = {
                int(k): int(v)
                for k, v in (batch_positions or local_pos).items()
            }
            pred_pos_value = (
                int(pred_pos)
                if pred_pos is not None
                else int(global_pos.get(int(available[-1]), len(available) - 1)) + 1
            )
            first_val_end_pos = len(available) - 1 - int(embargo_vp)
            for i in range(int(fold_count)):
                val_end_pos = first_val_end_pos - i * val_batches_per_fold
                val_start_pos = val_end_pos - val_batches_per_fold + 1
                train_end_pos = val_start_pos - int(embargo_tv) - 1
                train_start_pos = train_end_pos - int(train_batches_per_fold) + 1
                if min(train_start_pos, train_end_pos, val_start_pos, val_end_pos) < 0:
                    return []
                train_ids = [int(v) for v in available[train_start_pos : train_end_pos + 1]]
                val_ids = [int(v) for v in available[val_start_pos : val_end_pos + 1]]
                if len(train_ids) != int(train_batches_per_fold):
                    return []
                if len(val_ids) != int(val_batches_per_fold):
                    return []
                train_start_batch = int(train_ids[0])
                train_end_batch = int(train_ids[-1])
                val_start_batch = int(val_ids[0])
                val_end_batch = int(val_ids[-1])
                train_sparse = (train_end_batch - train_start_batch + 1) != len(train_ids)
                val_sparse = (val_end_batch - val_start_batch + 1) != len(val_ids)
                windows.append(
                    {
                        "fold_id": int(i + 1),
                        "val_start_batch": val_start_batch,
                        "val_end_batch": val_end_batch,
                        # Backward-compatible alias used by downstream consumers.
                        "val_batch": val_end_batch,
                        "train_start_batch": train_start_batch,
                        "train_end_batch": train_end_batch,
                        "train_start_pos": int(global_pos.get(train_start_batch, train_start_pos)),
                        "train_end_pos": int(global_pos.get(train_end_batch, train_end_pos)),
                        "val_start_pos": int(global_pos.get(val_start_batch, val_start_pos)),
                        "val_end_pos": int(global_pos.get(val_end_batch, val_end_pos)),
                        "pred_pos": int(pred_pos_value),
                        "train_batch_ids": train_ids,
                        "val_batch_ids": val_ids,
                        "train_batch_count": int(len(train_ids)),
                        "val_batch_count": int(len(val_ids)),
                        "window_is_sparse": bool(train_sparse or val_sparse),
                    }
                )
            return windows

        first_val_end_batch = int(train_end) - int(embargo_vp)
        for i in range(int(fold_count)):
            val_end_batch = first_val_end_batch - i * val_batches_per_fold
            val_start_batch = val_end_batch - val_batches_per_fold + 1
            train_end_batch = val_start_batch - int(embargo_tv) - 1
            train_start_batch = train_end_batch - int(train_batches_per_fold) + 1
            if val_start_batch < min_batch:
                return []
            if train_start_batch < min_batch:
                return []
            if train_end_batch < train_start_batch:
                return []
            windows.append(
                {
                    "fold_id": int(i + 1),
                    "val_start_batch": int(val_start_batch),
                    "val_end_batch": int(val_end_batch),
                    # Backward-compatible alias used by downstream consumers.
                    "val_batch": int(val_end_batch),
                    "train_start_batch": int(train_start_batch),
                    "train_end_batch": int(train_end_batch),
                    "train_batch_ids": list(range(int(train_start_batch), int(train_end_batch) + 1)),
                    "val_batch_ids": list(range(int(val_start_batch), int(val_end_batch) + 1)),
                    "train_batch_count": int(train_end_batch - train_start_batch + 1),
                    "val_batch_count": int(val_end_batch - val_start_batch + 1),
                    "window_is_sparse": False,
                }
            )
        return windows

    def _stage1_metric_from_predictions(
        self,
        metric: str,
        y_true: np.ndarray,
        y_pred: np.ndarray,
        pred_proba: np.ndarray,
    ) -> float | None:
        """Compute a metric value from prediction outputs for stage-1 selection."""
        metric = str(metric).strip().lower()
        if metric == "accuracy":
            return float((y_true == y_pred).mean())
        if metric == "macro_f1":
            return float(f1_score(y_true, y_pred, average="macro", zero_division=0))
        if metric == "macro_f1_up":
            return float(
                compute_directional_macro_f1(
                    y_true, y_pred, list(self.config.class_names), direction=1
                )
            )
        if metric == "macro_f1_down":
            return float(
                compute_directional_macro_f1(
                    y_true, y_pred, list(self.config.class_names), direction=0
                )
            )
        if metric == "log_loss":
            return float(
                log_loss(
                    y_true,
                    pred_proba,
                    labels=list(range(self.config.n_classes)),
                )
            )
        if metric == "balanced_accuracy":
            return float(balanced_accuracy_score(y_true, y_pred))
        if metric == "directional_accuracy":
            return float(
                compute_directional_accuracy(
                    y_true, y_pred, list(self.config.class_names)
                )
            )
        if metric == "directional_precision_up":
            return float(
                compute_directional_precision(
                    y_true, y_pred, list(self.config.class_names), direction=1
                )
            )
        if metric == "directional_precision_down":
            return float(
                compute_directional_precision(
                    y_true, y_pred, list(self.config.class_names), direction=0
                )
            )
        if metric == "cross_direction_error":
            return float(
                compute_cross_direction_error_rate(
                    y_true, y_pred, list(self.config.class_names)
                )
            )
        return None

    def _optimize_stage1_fold_cv_fast(
        self,
        train_end: int,
        df_all: pl.DataFrame,
        all_feature_cols: list[str],
    ) -> dict:
        """
        Fast deterministic stage-1 full-grid evaluation.

        Evaluates every (fold_count, val_batches_per_fold, train_batches_per_fold)
        combination without
        Optuna trial storage overhead, while still returning full per-combo and
        per-fold diagnostics for offline analysis.
        """
        if len(df_all) == 0:
            raise ValueError("No rows available in stage1_fold_cv window")
        if int(df_all["batch_id"].max()) > int(train_end):
            raise ValueError("leakage guard failed: optimization data exceeds train_end")

        stage_t0 = time.perf_counter()
        timing: dict[str, float] = {
            "batch_cache_build_s": 0.0,
            "compact_build_s": 0.0,
            "pred_batch_load_s": 0.0,
            "combo_loop_s": 0.0,
            "combo_window_build_s": 0.0,
            "fold_slice_s": 0.0,
            "fold_train_s": 0.0,
            "fold_val_predict_s": 0.0,
            "fold_metric_s": 0.0,
            "fold_pred_diag_s": 0.0,
            "combo_aggregate_s": 0.0,
            "selection_s": 0.0,
        }
        combo_count_processed = 0
        combo_count_failed = 0
        fold_windows_total = 0
        fold_windows_evaluated = 0

        batch_cache_t0 = time.perf_counter()
        batch_cache = self._build_stage1_batch_cache(df_all, all_feature_cols)
        timing["batch_cache_build_s"] += time.perf_counter() - batch_cache_t0
        if not batch_cache:
            raise ValueError("No batch cache entries available for stage1_fold_cv")
        available_batches = sorted(batch_cache.keys())
        min_batch = int(available_batches[0])
        max_batch = int(available_batches[-1])
        if max_batch < int(train_end):
            raise ValueError(
                f"Missing latest train batches in cache: max_batch={max_batch}, train_end={train_end}"
            )

        _, _, all_combos = self._stage1_combo_grid()
        stage1_default_val_batches_per_fold = int(
            max(1, getattr(self.window_space, "stage1_val_batches_per_fold", 1))
        )
        if not all_combos:
            raise ValueError("stage1_fold_cv has empty fold/val/train grid")

        # Build one contiguous matrix and slice by batch ranges to avoid repeated
        # np.vstack/np.concatenate inside the combo/fold loops.
        compact_t0 = time.perf_counter()
        batch_bounds: dict[int, tuple[int, int]] = {}
        x_chunks: list[np.ndarray] = []
        y_chunks: list[np.ndarray] = []
        cursor = 0
        for bid in available_batches:
            X_b, y_b = batch_cache[int(bid)]
            n_rows = int(len(y_b))
            if n_rows <= 0:
                continue
            batch_bounds[int(bid)] = (cursor, cursor + n_rows)
            x_chunks.append(X_b)
            y_chunks.append(y_b)
            cursor += n_rows
        if not x_chunks:
            raise ValueError("No valid rows available in stage1 batch cache")
        X_all_compact = np.vstack(x_chunks)
        y_all_compact = np.concatenate(y_chunks)
        # Free intermediate per-batch containers early to reduce peak memory.
        x_chunks.clear()
        y_chunks.clear()
        batch_cache.clear()
        available_batch_set = set(batch_bounds.keys())
        range_cache: dict[tuple[int, int], tuple[np.ndarray, np.ndarray]] = {}
        timing["compact_build_s"] += time.perf_counter() - compact_t0
        range_cache_hits = 0
        range_cache_misses = 0

        def _slice_batch_range(
            start_batch: int,
            end_batch: int,
        ) -> tuple[tuple[np.ndarray, np.ndarray] | None, str | None]:
            nonlocal range_cache_hits, range_cache_misses
            key = (int(start_batch), int(end_batch))
            cached = range_cache.get(key)
            if cached is not None:
                range_cache_hits += 1
                return cached, None
            range_cache_misses += 1
            missing = [b for b in range(key[0], key[1] + 1) if b not in available_batch_set]
            if missing:
                return None, "missing_batch_in_cache:" + ",".join(str(b) for b in missing)
            start_idx = int(batch_bounds[key[0]][0])
            end_idx = int(batch_bounds[key[1]][1])
            arrays = (X_all_compact[start_idx:end_idx], y_all_compact[start_idx:end_idx])
            range_cache[key] = arrays
            return arrays, None

        stability_lambda = float(max(0.0, self.window_space.stage1_stability_lambda))
        base_params = self.config.cb_base_params.copy()
        baseline_iterations = int(max(10, self.model_space.num_boost_round_min))
        objective_direction = self.config.optuna_direction()

        selection_mode = str(
            getattr(self.window_space, "stage1_trial_selection_mode", "objective")
        ).strip().lower()
        if selection_mode not in {"objective", "prediction_batch"}:
            selection_mode = "objective"
        configured_pred_metric = getattr(
            self.window_space, "stage1_prediction_metric", None
        )
        selection_metric = str(
            configured_pred_metric or self.config.optuna_metric
        ).strip().lower()
        pred_metric_direction: dict[str, str] = {
            "accuracy": "maximize",
            "macro_f1": "maximize",
            "macro_f1_up": "maximize",
            "macro_f1_down": "maximize",
            "log_loss": "minimize",
            "balanced_accuracy": "maximize",
            "directional_accuracy": "maximize",
            "directional_precision_up": "maximize",
            "directional_precision_down": "maximize",
            "cross_direction_error": "minimize",
        }

        # Optional diagnostics on the prediction batch (informational only).
        pred_X = None
        pred_y = None
        pred_batch = int(train_end) + 1
        pred_load_t0 = time.perf_counter()
        try:
            pred_df = load_batch(
                self.config.features_dir,
                self.config.labels_dir,
                self.TIMEFRAME,
                pred_batch,
                target_col=self.config.target,
                feature_target_col=(self.config.feature_target or self.config.target),
                exclude_tail_pct=self.config.exclude_tail_pct,
            )
            pred_df = pred_df.filter(pred_df[self.config.target] >= 0)
            if len(pred_df) > 0:
                pred_X, pred_y, _, _ = prepare_features_target(
                    pred_df, all_feature_cols, self.config.target
                )
                pred_X = np.nan_to_num(pred_X, nan=0.0, posinf=0.0, neginf=0.0)
        except Exception:
            pred_X = None
            pred_y = None
        timing["pred_batch_load_s"] += time.perf_counter() - pred_load_t0

        combo_records: list[dict] = []
        combo_fold_records: list[dict] = []
        # Cache fold evaluations across combinations so repeated fold windows
        # are trained once and reused (major speedup for stage1 full-grid).
        fold_eval_cache: dict[tuple[int, int, int, int], dict] = {}
        fold_cache_hits = 0
        fold_cache_misses = 0
        fold_trains = 0
        train_model_cache: dict[tuple[int, int], CatBoostClassifier] = {}
        train_model_cache_hits = 0
        train_model_cache_misses = 0

        combo_loop_t0 = time.perf_counter()
        for combo_idx, (fold_count, val_batches_per_fold, train_batches) in enumerate(
            all_combos
        ):
            combo_count_processed += 1
            combo_t0 = time.perf_counter()
            base_rec = {
                "trial_number": int(combo_idx),
                "fold_count": int(fold_count),
                "val_batches_per_fold": int(val_batches_per_fold),
                "train_batches_per_fold": int(train_batches),
                "stage1_execution_mode": "fast_grid",
                "objective_metric": str(self.config.optuna_metric),
                "objective_direction": str(objective_direction),
                "selection_metric": str(selection_metric),
            }
            window_t0 = time.perf_counter()
            windows = self._build_stage1_fold_windows(
                train_end=train_end,
                fold_count=fold_count,
                train_batches_per_fold=train_batches,
                val_batches_per_fold=val_batches_per_fold,
                min_batch=min_batch,
            )
            timing["combo_window_build_s"] += time.perf_counter() - window_t0
            if len(windows) < int(fold_count):
                combo_count_failed += 1
                combo_records.append(
                    {
                        **base_rec,
                        "status": "failed",
                        "fail_reason": "not_enough_history_for_requested_folds",
                        "combo_runtime_s": float(time.perf_counter() - combo_t0),
                    }
                )
                continue

            fold_scores: list[float] = []
            fold_accs: list[float] = []
            fold_cross_errs: list[float] = []
            train_rows_total = 0
            val_rows_total = 0
            nearest_pred_diag: dict | None = None
            nearest_window = None
            fail_reason = None

            fold_windows_total += int(len(windows))
            for w in windows:
                val_start_batch = int(w["val_start_batch"])
                val_end_batch = int(w["val_end_batch"])
                train_start_batch = int(w["train_start_batch"])
                train_end_batch = int(w["train_end_batch"])
                if any(
                    b > int(train_end)
                    for b in (
                        train_start_batch,
                        train_end_batch,
                        val_start_batch,
                        val_end_batch,
                    )
                ):
                    fail_reason = "leakage_guard_fold_batch_exceeds_train_end"
                    break

                fold_key = (
                    train_start_batch,
                    train_end_batch,
                    val_start_batch,
                    val_end_batch,
                )
                fold_cached = fold_eval_cache.get(fold_key)
                if fold_cached is None:
                    fold_cache_misses += 1
                    slice_t0 = time.perf_counter()
                    train_arrays, train_fail = _slice_batch_range(
                        train_start_batch, train_end_batch
                    )
                    if train_fail is not None:
                        timing["fold_slice_s"] += time.perf_counter() - slice_t0
                        fold_cached = {
                            "status": "failed",
                            "fail_reason": f"{train_fail}:train",
                        }
                        fold_eval_cache[fold_key] = fold_cached
                    else:
                        val_arrays, val_fail = _slice_batch_range(
                            val_start_batch, val_end_batch
                        )
                        timing["fold_slice_s"] += time.perf_counter() - slice_t0
                        if val_fail is not None:
                            fold_cached = {
                                "status": "failed",
                                "fail_reason": f"{val_fail}:val",
                            }
                            fold_eval_cache[fold_key] = fold_cached
                        else:
                            X_train, y_train = train_arrays
                            X_val, y_val = val_arrays
                            if len(y_train) < 50 or len(y_val) < 5:
                                fold_cached = {
                                    "status": "failed",
                                    "fail_reason": "insufficient_fold_samples",
                                }
                                fold_eval_cache[fold_key] = fold_cached
                            elif len(np.unique(y_train)) < 2:
                                fold_cached = {
                                    "status": "failed",
                                    "fail_reason": "insufficient_class_diversity_in_fold_train",
                                }
                                fold_eval_cache[fold_key] = fold_cached
                            else:
                                train_key = (train_start_batch, train_end_batch)
                                model = train_model_cache.get(train_key)
                                if model is None:
                                    train_model_cache_misses += 1
                                    try:
                                        train_t0 = time.perf_counter()
                                        model, _ = self._fit_catboost_with_fallback(
                                            params=base_params,
                                            iterations=baseline_iterations,
                                            X_train=X_train,
                                            y_train=y_train,
                                            X_val=X_val,
                                            y_val=y_val,
                                        )
                                        timing["fold_train_s"] += (
                                            time.perf_counter() - train_t0
                                        )
                                    except Exception as e:
                                        fold_cached = {
                                            "status": "failed",
                                            "fail_reason": f"fold_train_failed:{e}",
                                        }
                                        fold_eval_cache[fold_key] = fold_cached
                                        model = None
                                    else:
                                        fold_trains += 1
                                        train_model_cache[train_key] = model
                                else:
                                    train_model_cache_hits += 1

                                if model is not None:
                                    val_pred_t0 = time.perf_counter()
                                    pred_proba, y_pred = self._to_full_class_proba_and_pred(
                                        model, model.predict_proba(X_val)
                                    )
                                    timing["fold_val_predict_s"] += (
                                        time.perf_counter() - val_pred_t0
                                    )
                                    metric_t0 = time.perf_counter()
                                    fold_score = float(
                                        self._metric_score(y_val, y_pred, pred_proba)
                                    )
                                    fold_acc = float((y_pred == y_val).mean())
                                    fold_cross = float(
                                        compute_cross_direction_error_rate(
                                            y_val, y_pred, list(self.config.class_names)
                                        )
                                    )
                                    conf = confusion_matrix(
                                        y_val,
                                        y_pred,
                                        labels=list(range(self.config.n_classes)),
                                    )
                                    true_prob = np.clip(
                                        pred_proba[np.arange(len(y_val)), y_val],
                                        1e-12,
                                        1.0,
                                    )
                                    nll_sum = float((-np.log(true_prob)).sum())
                                    timing["fold_metric_s"] += (
                                        time.perf_counter() - metric_t0
                                    )
                                    pred_diag = None
                                    if (
                                        int(w["fold_id"]) == 1
                                        and pred_X is not None
                                        and pred_y is not None
                                    ):
                                        pred_diag_t0 = time.perf_counter()
                                        pred_proba_pred, pred_labels_pred = (
                                            self._to_full_class_proba_and_pred(
                                                model, model.predict_proba(pred_X)
                                            )
                                        )
                                        pred_n_local = int(len(pred_y))
                                        pred_acc_local = float(
                                            (pred_labels_pred == pred_y).mean()
                                        )
                                        pred_macro_f1_local = float(
                                            f1_score(
                                                pred_y,
                                                pred_labels_pred,
                                                average="macro",
                                                zero_division=0,
                                            )
                                        )
                                        pred_cross_local = float(
                                            compute_cross_direction_error_rate(
                                                pred_y,
                                                pred_labels_pred,
                                                list(self.config.class_names),
                                            )
                                        )
                                        pred_conf_local = confusion_matrix(
                                            pred_y,
                                            pred_labels_pred,
                                            labels=list(range(self.config.n_classes)),
                                        )
                                        pred_true_prob_local = np.clip(
                                            pred_proba_pred[np.arange(len(pred_y)), pred_y],
                                            1e-12,
                                            1.0,
                                        )
                                        pred_nll_sum_local = float(
                                            (-np.log(pred_true_prob_local)).sum()
                                        )
                                        pred_log_loss_local = float(
                                            pred_nll_sum_local / max(1, pred_n_local)
                                        )
                                        if selection_metric == "accuracy":
                                            pred_metric_value_local = pred_acc_local
                                        elif selection_metric == "macro_f1":
                                            pred_metric_value_local = pred_macro_f1_local
                                        elif selection_metric == "cross_direction_error":
                                            pred_metric_value_local = pred_cross_local
                                        elif selection_metric == "log_loss":
                                            pred_metric_value_local = pred_log_loss_local
                                        else:
                                            pred_metric_value_local = (
                                                self._stage1_metric_from_predictions(
                                                    selection_metric,
                                                    pred_y,
                                                    pred_labels_pred,
                                                    pred_proba_pred,
                                                )
                                            )
                                        pred_diag = {
                                            "pred_n": pred_n_local,
                                            "pred_accuracy": pred_acc_local,
                                            "pred_macro_f1": pred_macro_f1_local,
                                            "pred_cross_direction_error": pred_cross_local,
                                            "pred_log_loss": pred_log_loss_local,
                                            "pred_confusion_flat": [
                                                int(v)
                                                for v in pred_conf_local.reshape(-1).tolist()
                                            ],
                                            "pred_nll_sum": pred_nll_sum_local,
                                            "pred_metric_value": (
                                                float(pred_metric_value_local)
                                                if pred_metric_value_local is not None
                                                else None
                                            ),
                                        }
                                        timing["fold_pred_diag_s"] += (
                                            time.perf_counter() - pred_diag_t0
                                        )

                                    fold_cached = {
                                        "status": "ok",
                                        "n_train_samples": int(len(y_train)),
                                        "n_val_samples": int(len(y_val)),
                                        "fold_score": float(fold_score),
                                        "fold_accuracy": float(fold_acc),
                                        "fold_cross_direction_error": float(fold_cross),
                                        "confusion_flat": [
                                            int(v) for v in conf.reshape(-1).tolist()
                                        ],
                                        "nll_sum": float(nll_sum),
                                        "pred_diag": pred_diag,
                                    }
                                    fold_eval_cache[fold_key] = fold_cached
                else:
                    fold_cache_hits += 1

                if fold_cached.get("status") != "ok":
                    fail_reason = str(fold_cached.get("fail_reason") or "fold_eval_failed")
                    break

                fold_windows_evaluated += 1
                fold_scores.append(float(fold_cached["fold_score"]))
                fold_accs.append(float(fold_cached["fold_accuracy"]))
                fold_cross_errs.append(float(fold_cached["fold_cross_direction_error"]))
                train_rows_total += int(fold_cached["n_train_samples"])
                val_rows_total += int(fold_cached["n_val_samples"])
                combo_fold_records.append(
                    {
                        "trial_number": int(combo_idx),
                        "fold_count": int(fold_count),
                        "val_batches_per_fold": int(val_batches_per_fold),
                        "train_batches_per_fold": int(train_batches),
                        "fold_id": int(w["fold_id"]),
                        "train_start_batch": int(w["train_start_batch"]),
                        "train_end_batch": int(w["train_end_batch"]),
                        "val_start_batch": int(val_start_batch),
                        "val_end_batch": int(val_end_batch),
                        "val_batch": int(val_end_batch),
                        "n_train_samples": int(fold_cached["n_train_samples"]),
                        "n_val_samples": int(fold_cached["n_val_samples"]),
                        "fold_score": float(fold_cached["fold_score"]),
                        "fold_accuracy": float(fold_cached["fold_accuracy"]),
                        "fold_cross_direction_error": float(
                            fold_cached["fold_cross_direction_error"]
                        ),
                        "n_classes": int(self.config.n_classes),
                        "confusion_flat": [
                            int(v) for v in fold_cached["confusion_flat"]
                        ],
                        "nll_sum": float(fold_cached["nll_sum"]),
                    }
                )
                if int(w["fold_id"]) == 1:
                    nearest_window = dict(w)
                    nearest_pred_diag = fold_cached.get("pred_diag")

            if fail_reason is not None or not fold_scores:
                combo_records.append(
                    {
                        **base_rec,
                        "status": "failed",
                        "fail_reason": fail_reason or "no_valid_folds",
                        "combo_runtime_s": float(time.perf_counter() - combo_t0),
                    }
                )
                combo_count_failed += 1
                continue

            aggregate_t0 = time.perf_counter()
            score_mean = float(np.mean(fold_scores))
            score_std = float(np.std(fold_scores))
            objective_score = (
                score_mean + stability_lambda * score_std
                if objective_direction == "minimize"
                else score_mean - stability_lambda * score_std
            )
            train_total = max(1, train_rows_total + val_rows_total)
            train_split = float(train_rows_total / train_total)
            val_ratio = float(val_rows_total / train_total)

            pred_acc = None
            pred_macro_f1 = None
            pred_macro_f1_up = None
            pred_macro_f1_down = None
            pred_bal_acc = None
            pred_log_loss = None
            pred_dir_acc = None
            pred_dir_prec_up = None
            pred_dir_prec_down = None
            pred_cross_err = None
            pred_conf_flat = None
            pred_nll_sum = None
            pred_n = None
            pred_metric_value = None
            if nearest_pred_diag is not None:
                pred_n = int(nearest_pred_diag.get("pred_n"))
                pred_acc = nearest_pred_diag.get("pred_accuracy")
                pred_macro_f1 = nearest_pred_diag.get("pred_macro_f1")
                pred_cross_err = nearest_pred_diag.get("pred_cross_direction_error")
                pred_log_loss = nearest_pred_diag.get("pred_log_loss")
                pred_conf_flat = nearest_pred_diag.get("pred_confusion_flat")
                pred_nll_sum = nearest_pred_diag.get("pred_nll_sum")
                pred_metric_value = nearest_pred_diag.get("pred_metric_value")

            combo_records.append(
                {
                    **base_rec,
                    "status": "complete",
                    "optuna_score": float(objective_score),
                    "fold_score_mean": float(score_mean),
                    "fold_score_std": float(score_std),
                    "fold_accuracy_mean": float(np.mean(fold_accs)),
                    "cross_direction_error": float(np.mean(fold_cross_errs)),
                    "n_train_samples": int(train_rows_total),
                    "n_val_samples": int(val_rows_total),
                    "train_val_split": float(train_split),
                    "val_ratio": float(val_ratio),
                    "stage1_fold_scores": [float(v) for v in fold_scores],
                    "stage1_fold_windows": [
                        {
                            "fold_id": int(w["fold_id"]),
                            "train_start_batch": int(w["train_start_batch"]),
                            "train_end_batch": int(w["train_end_batch"]),
                            "val_start_batch": int(w["val_start_batch"]),
                            "val_end_batch": int(w["val_end_batch"]),
                            "val_batch": int(w["val_batch"]),
                        }
                        for w in windows
                    ],
                    "pred_batch": int(pred_batch) if pred_n is not None else None,
                    "pred_n": pred_n,
                    "pred_accuracy": pred_acc,
                    "pred_macro_f1": pred_macro_f1,
                    "pred_macro_f1_up": pred_macro_f1_up,
                    "pred_macro_f1_down": pred_macro_f1_down,
                    "pred_balanced_accuracy": pred_bal_acc,
                    "pred_log_loss": pred_log_loss,
                    "pred_directional_accuracy": pred_dir_acc,
                    "pred_directional_precision_up": pred_dir_prec_up,
                    "pred_directional_precision_down": pred_dir_prec_down,
                    "pred_cross_direction_error": pred_cross_err,
                    "pred_metric_value": (
                        float(pred_metric_value) if pred_metric_value is not None else None
                    ),
                    "pred_confusion_flat": pred_conf_flat,
                    "pred_nll_sum": pred_nll_sum,
                    "leakage_guard": "pass",
                    "combo_runtime_s": float(time.perf_counter() - combo_t0),
                }
            )
            timing["combo_aggregate_s"] += time.perf_counter() - aggregate_t0

        timing["combo_loop_s"] += time.perf_counter() - combo_loop_t0
        complete_records = [r for r in combo_records if r.get("status") == "complete"]
        if not complete_records:
            fail_reasons: dict[str, int] = {}
            for r in combo_records:
                reason = str(r.get("fail_reason") or "unknown")
                fail_reasons[reason] = fail_reasons.get(reason, 0) + 1
            raise ValueError(
                f"No completed stage1 combinations for {self.TIMEFRAME} train_end={train_end}. "
                f"Fail summary: {fail_reasons}"
            )

        def _best_by(records: list[dict], key: str, direction: str) -> dict:
            if direction == "minimize":
                return min(records, key=lambda r: float(r[key]))
            return max(records, key=lambda r: float(r[key]))

        selection_t0 = time.perf_counter()
        best = _best_by(complete_records, "optuna_score", objective_direction)
        selected_by = "objective"
        selection_attr = "optuna_score"
        selection_value = float(best["optuna_score"])

        if selection_mode == "prediction_batch":
            pred_direction = pred_metric_direction.get(selection_metric)
            if pred_direction is not None:
                pred_candidates = [
                    r for r in complete_records if r.get("pred_metric_value") is not None
                ]
                if pred_candidates:
                    best = _best_by(pred_candidates, "pred_metric_value", pred_direction)
                    selected_by = "prediction_batch"
                    selection_attr = f"pred_metric_value[{selection_metric}]"
                    selection_value = float(best["pred_metric_value"])
                else:
                    selected_by = "objective_fallback_no_pred_metric"
            else:
                selected_by = "objective_fallback_invalid_metric"
        timing["selection_s"] += time.perf_counter() - selection_t0

        stage_total_s = time.perf_counter() - stage_t0
        combos_per_second = float(len(all_combos) / stage_total_s) if stage_total_s > 0 else None
        trains_per_second = float(fold_trains / stage_total_s) if stage_total_s > 0 else None
        slowest_combos = sorted(
            (r for r in combo_records if r.get("combo_runtime_s") is not None),
            key=lambda r: float(r["combo_runtime_s"]),
            reverse=True,
        )[:10]
        slowest_combo_summary = [
            {
                "trial_number": int(r.get("trial_number", -1)),
                "status": str(r.get("status")),
                "fold_count": int(r.get("fold_count", 0)),
                "val_batches_per_fold": int(r.get("val_batches_per_fold", 0)),
                "train_batches_per_fold": int(r.get("train_batches_per_fold", 0)),
                "combo_runtime_s": float(r.get("combo_runtime_s", 0.0)),
            }
            for r in slowest_combos
        ]

        windows = list(best.get("stage1_fold_windows") or [])
        if not windows:
            windows = self._build_stage1_fold_windows(
                train_end=train_end,
                fold_count=int(best["fold_count"]),
                train_batches_per_fold=int(best["train_batches_per_fold"]),
                val_batches_per_fold=int(
                    best.get(
                        "val_batches_per_fold",
                        stage1_default_val_batches_per_fold,
                    )
                ),
                min_batch=min_batch,
            )
        if not windows:
            raise ValueError("stage1_fold_cv best combo produced invalid fold plan")

        nearest = windows[0]
        tv_embargo, vp_embargo = self._stage1_resolve_embargo()
        lookback_batches = int(
            int(best["train_batches_per_fold"])
            + int(best["fold_count"])
            * int(
                best.get(
                    "val_batches_per_fold",
                    stage1_default_val_batches_per_fold,
                )
            )
            + tv_embargo
            + vp_embargo
        )
        split_from_trial = float(best.get("train_val_split", 0.8))
        val_from_trial = float(best.get("val_ratio", 0.2))
        if not (0.0 < split_from_trial < 1.0):
            split_from_trial = 0.8
        if not (0.0 < val_from_trial < 1.0):
            val_from_trial = 0.2

        return {
            "best_score": float(selection_value),
            "best_objective_score": float(best["optuna_score"]),
            "optuna_metric": self.config.optuna_metric,
            "optuna_direction": objective_direction,
            "best_accuracy": float(best.get("fold_accuracy_mean", 0.0)),
            "directional_accuracy": None,
            "directional_precision_up": None,
            "directional_precision_down": None,
            "cross_direction_error": (
                float(best["cross_direction_error"])
                if best.get("cross_direction_error") is not None
                else None
            ),
            "cb_params": base_params.copy(),
            "num_boost_round": baseline_iterations,
            "lookback_batches": int(lookback_batches),
            "window_selection_mode": "stage1_fold_cv_v1",
            "decay_weight": 1.0,
            "class_weight_method": "none",
            "train_val_split": float(split_from_trial),
            "val_ratio": float(val_from_trial),
            "window_distribution_score": float(best["optuna_score"]),
            "train_start_batch": int(nearest["train_start_batch"]),
            "train_end_batch": int(nearest["train_end_batch"]),
            "val_start_batch": int(nearest["val_start_batch"]),
            "val_end_batch": int(nearest["val_end_batch"]),
            "embargo_train_val_batches": int(tv_embargo),
            "embargo_val_pred_batches": int(vp_embargo),
            "reference_distribution_mode": "stage1_fold_cv",
            "recent_ref_batches": 0,
            "recent_ref_weight": 0.0,
            "active_class_min_frac": 0.0,
            "min_val_samples_per_active_class": 0,
            "active_class_ids": list(range(self.config.n_classes)),
            "reference_distribution": [],
            "recent_class_counts": [],
            "window_class_counts": [],
            "train_class_counts": [],
            "val_class_counts": [],
            "total_class_counts": [],
            "distribution_mse_train": 0.0,
            "distribution_mse_val": 0.0,
            "distribution_mse_window": 0.0,
            "distribution_mse_train_val": 0.0,
            "missing_classes_train": 0,
            "missing_classes_val": 0,
            "selected_features": all_feature_cols,
            "n_features": len(all_feature_cols),
            "study": None,
            "per_class_accuracy": {},
            "per_class_count": {},
            "log_loss": None,
            "n_train_samples": int(best.get("n_train_samples", 0)),
            "n_val_samples": int(best.get("n_val_samples", 0)),
            "leakage_guard": str(best.get("leakage_guard", "pass")),
            "stage1_fold_count": int(best["fold_count"]),
            "stage1_val_batches_per_fold": int(
                best.get(
                    "val_batches_per_fold",
                    stage1_default_val_batches_per_fold,
                )
            ),
            "stage1_train_batches_per_fold": int(best["train_batches_per_fold"]),
            "stage1_fold_score_mean": float(best.get("fold_score_mean", 0.0)),
            "stage1_fold_score_std": float(best.get("fold_score_std", 0.0)),
            "stage1_stability_lambda": float(stability_lambda),
            "stage1_fold_scores": list(best.get("stage1_fold_scores", [])),
            "stage1_fold_windows": list(best.get("stage1_fold_windows", [])),
            "stage1_pred_batch": best.get("pred_batch"),
            "stage1_pred_n": best.get("pred_n"),
            "stage1_pred_accuracy": best.get("pred_accuracy"),
            "stage1_pred_macro_f1": best.get("pred_macro_f1"),
            "stage1_pred_macro_f1_up": best.get("pred_macro_f1_up"),
            "stage1_pred_macro_f1_down": best.get("pred_macro_f1_down"),
            "stage1_pred_log_loss": best.get("pred_log_loss"),
            "stage1_pred_directional_accuracy": best.get("pred_directional_accuracy"),
            "stage1_pred_directional_precision_up": best.get(
                "pred_directional_precision_up"
            ),
            "stage1_pred_directional_precision_down": best.get(
                "pred_directional_precision_down"
            ),
            "stage1_pred_cross_direction_error": best.get(
                "pred_cross_direction_error"
            ),
            "stage1_combo_count_total": int(len(all_combos)),
            "stage1_combo_count_completed": int(len(complete_records)),
            "stage1_combo_count_missing": int(len(all_combos) - len(complete_records)),
            "stage1_all_combos_evaluated": bool(len(complete_records) == len(all_combos)),
            "stage1_fold_cache_hits": int(fold_cache_hits),
            "stage1_fold_cache_misses": int(fold_cache_misses),
            "stage1_fold_cache_unique_windows": int(len(fold_eval_cache)),
            "stage1_fold_train_count": int(fold_trains),
            "stage1_train_model_cache_hits": int(train_model_cache_hits),
            "stage1_train_model_cache_misses": int(train_model_cache_misses),
            "stage1_train_model_cache_unique": int(len(train_model_cache)),
            "stage1_range_cache_hits": int(range_cache_hits),
            "stage1_range_cache_misses": int(range_cache_misses),
            "stage1_combo_processed": int(combo_count_processed),
            "stage1_combo_failed": int(combo_count_failed),
            "stage1_fold_windows_total": int(fold_windows_total),
            "stage1_fold_windows_evaluated": int(fold_windows_evaluated),
            "stage1_runtime_s": float(stage_total_s),
            "stage1_combos_per_second": (
                float(combos_per_second) if combos_per_second is not None else None
            ),
            "stage1_trains_per_second": (
                float(trains_per_second) if trains_per_second is not None else None
            ),
            "stage1_timing": {
                **{k: float(v) for k, v in timing.items()},
                "total_s": float(stage_total_s),
            },
            "stage1_slowest_combos": slowest_combo_summary,
            "stage1_execution_mode": "fast_grid",
            "stage1_trial_selection_mode": selection_mode,
            "stage1_prediction_metric": selection_metric,
            "stage1_selected_by": selected_by,
            "stage1_selection_attr": selection_attr,
            "stage1_selected_trial_number": int(best["trial_number"]),
            "stage1_selection_value": float(selection_value),
            "stage1_pred_confusion_flat": best.get("pred_confusion_flat"),
            "stage1_pred_nll_sum": best.get("pred_nll_sum"),
            "stage1_combo_metrics": combo_records,
            "stage1_combo_fold_metrics": combo_fold_records,
        }

    def _optimize_stage1_fold_cv(
        self,
        train_end: int,
        df_all: pl.DataFrame,
        all_feature_cols: list[str],
        n_trials: int,
        timeout: int,
        study_storage_path: Path | None,
        study_name: str | None,
    ) -> dict:
        """Stage-1 optimization: tune fold_count, val_batches_per_fold, and train_batches_per_fold."""
        execution_mode = str(
            getattr(self.window_space, "stage1_execution_mode", "fast_grid")
        ).strip().lower()
        if execution_mode != "optuna":
            return self._optimize_stage1_fold_cv_fast(
                train_end=train_end,
                df_all=df_all,
                all_feature_cols=all_feature_cols,
            )

        if len(df_all) == 0:
            raise ValueError("No rows available in stage1_fold_cv window")
        if int(df_all["batch_id"].max()) > int(train_end):
            raise ValueError("leakage guard failed: optimization data exceeds train_end")

        batch_cache = self._build_stage1_batch_cache(df_all, all_feature_cols)
        if not batch_cache:
            raise ValueError("No batch cache entries available for stage1_fold_cv")
        available_batches = sorted(batch_cache.keys())
        min_batch = int(available_batches[0])
        max_batch = int(available_batches[-1])
        if max_batch < int(train_end):
            raise ValueError(
                f"Missing latest train batches in cache: max_batch={max_batch}, train_end={train_end}"
            )

        fold_values, pair_values, all_combos = self._stage1_combo_grid()
        if not all_combos:
            raise ValueError("stage1_fold_cv has empty fold/val/train grid")
        folds_min = int(min(fold_values))
        folds_max = int(max(fold_values))
        pair_labels = [f"{int(v)}:{int(t)}" for v, t in pair_values]
        stability_lambda = float(max(0.0, self.window_space.stage1_stability_lambda))
        base_params = self.config.cb_base_params.copy()
        baseline_iterations = int(max(10, self.model_space.num_boost_round_min))
        direction = self.config.optuna_direction()

        # Optional prediction-batch diagnostics for every stage-1 combination.
        # This is strictly informational and never used as optimization objective.
        pred_X = None
        pred_y = None
        pred_batch = int(train_end) + 1
        try:
            pred_df = load_batch(
                self.config.features_dir,
                self.config.labels_dir,
                self.TIMEFRAME,
                pred_batch,
                target_col=self.config.target,
                feature_target_col=(self.config.feature_target or self.config.target),
                exclude_tail_pct=self.config.exclude_tail_pct,
            )
            pred_df = pred_df.filter(pred_df[self.config.target] >= 0)
            if len(pred_df) > 0:
                pred_X, pred_y, _, _ = prepare_features_target(
                    pred_df, all_feature_cols, self.config.target
                )
                pred_X = np.nan_to_num(pred_X, nan=0.0, posinf=0.0, neginf=0.0)
        except Exception:
            pred_X = None
            pred_y = None

        def objective(trial: optuna.Trial) -> float:
            fold_count = trial.suggest_int("fold_count", folds_min, folds_max)
            combo_key = trial.suggest_categorical("val_train_combo", pair_labels)
            val_batches_per_fold, train_batches = [
                int(v) for v in str(combo_key).split(":", maxsplit=1)
            ]

            windows = self._build_stage1_fold_windows(
                train_end=train_end,
                fold_count=fold_count,
                train_batches_per_fold=train_batches,
                val_batches_per_fold=val_batches_per_fold,
                min_batch=min_batch,
            )
            if len(windows) < fold_count:
                raise optuna.TrialPruned("not enough history for requested folds")

            fold_scores: list[float] = []
            fold_accs: list[float] = []
            fold_cross_errs: list[float] = []
            fold_metrics_detailed: list[dict] = []
            train_rows_total = 0
            val_rows_total = 0
            nearest_model = None
            nearest_window = None
            for w in windows:
                val_start_batch = int(w["val_start_batch"])
                val_end_batch = int(w["val_end_batch"])
                val_batches_range = list(range(val_start_batch, val_end_batch + 1))
                train_batches_range = list(
                    range(int(w["train_start_batch"]), int(w["train_end_batch"]) + 1)
                )
                if any(
                    b > int(train_end)
                    for b in train_batches_range + val_batches_range
                ):
                    raise optuna.TrialPruned("leakage guard: fold batch exceeds train_end")
                missing_val_batches = [
                    b for b in val_batches_range if b not in batch_cache
                ]
                if missing_val_batches:
                    raise optuna.TrialPruned(
                        "missing val batch in cache: "
                        + ",".join(str(b) for b in missing_val_batches)
                    )
                train_arrays = [batch_cache[b] for b in train_batches_range if b in batch_cache]
                if len(train_arrays) != len(train_batches_range):
                    raise optuna.TrialPruned("missing train batch in cache")
                X_train = np.vstack([a[0] for a in train_arrays])
                y_train = np.concatenate([a[1] for a in train_arrays])
                val_arrays = [batch_cache[b] for b in val_batches_range]
                X_val = np.vstack([a[0] for a in val_arrays])
                y_val = np.concatenate([a[1] for a in val_arrays])
                if len(y_train) < 50 or len(y_val) < 5:
                    raise optuna.TrialPruned("insufficient fold samples")
                if len(np.unique(y_train)) < 2:
                    raise optuna.TrialPruned("insufficient class diversity in fold train")

                train_rows_total += int(len(y_train))
                val_rows_total += int(len(y_val))
                try:
                    model, cpu_fallback = self._fit_catboost_with_fallback(
                        params=base_params,
                        iterations=baseline_iterations,
                        X_train=X_train,
                        y_train=y_train,
                        X_val=X_val,
                        y_val=y_val,
                    )
                except Exception as e:
                    trial.set_user_attr("train_fail", str(e))
                    raise optuna.TrialPruned(f"fold train failed: {e}")
                if cpu_fallback:
                    trial.set_user_attr("cpu_fallback", True)

                pred_proba, y_pred = self._to_full_class_proba_and_pred(
                    model, model.predict_proba(X_val)
                )
                score = self._metric_score(y_val, y_pred, pred_proba)
                fold_acc = float((y_pred == y_val).mean())
                fold_cross = float(
                    compute_cross_direction_error_rate(
                        y_val, y_pred, list(self.config.class_names)
                    )
                )
                fold_scores.append(float(score))
                fold_accs.append(fold_acc)
                fold_cross_errs.append(fold_cross)
                fold_conf = confusion_matrix(
                    y_val, y_pred, labels=list(range(self.config.n_classes))
                )
                fold_true_prob = np.clip(
                    pred_proba[np.arange(len(y_val)), y_val],
                    1e-12,
                    1.0,
                )
                fold_nll_sum = float((-np.log(fold_true_prob)).sum())
                fold_metrics_detailed.append(
                    {
                        "fold_id": int(w["fold_id"]),
                        "train_start_batch": int(w["train_start_batch"]),
                        "train_end_batch": int(w["train_end_batch"]),
                        "val_start_batch": int(val_start_batch),
                        "val_end_batch": int(val_end_batch),
                        "val_batch": int(val_end_batch),
                        "n_train_samples": int(len(y_train)),
                        "n_val_samples": int(len(y_val)),
                        "fold_score": float(score),
                        "fold_accuracy": fold_acc,
                        "fold_macro_f1": float(
                            f1_score(y_val, y_pred, average="macro", zero_division=0)
                        ),
                        "fold_directional_accuracy": float(
                            compute_directional_accuracy(
                                y_val, y_pred, list(self.config.class_names)
                            )
                        ),
                        "fold_directional_precision_up": float(
                            compute_directional_precision(
                                y_val, y_pred, list(self.config.class_names), direction=1
                            )
                        ),
                        "fold_directional_precision_down": float(
                            compute_directional_precision(
                                y_val, y_pred, list(self.config.class_names), direction=0
                            )
                        ),
                        "fold_cross_direction_error": fold_cross,
                        "n_classes": int(self.config.n_classes),
                        "confusion_flat": [
                            int(v) for v in fold_conf.reshape(-1).tolist()
                        ],
                        "nll_sum": float(fold_nll_sum),
                    }
                )
                if int(w["fold_id"]) == 1:
                    nearest_model = model
                    nearest_window = dict(w)

            if not fold_scores:
                raise optuna.TrialPruned("no valid folds")

            score_mean = float(np.mean(fold_scores))
            score_std = float(np.std(fold_scores))
            if direction == "minimize":
                objective_score = score_mean + stability_lambda * score_std
            else:
                objective_score = score_mean - stability_lambda * score_std

            train_total = max(1, train_rows_total + val_rows_total)
            trial.set_user_attr("optuna_metric", self.config.optuna_metric)
            trial.set_user_attr("optuna_score", float(objective_score))
            trial.set_user_attr("fold_count", int(fold_count))
            trial.set_user_attr("val_batches_per_fold", int(val_batches_per_fold))
            trial.set_user_attr("train_batches_per_fold", int(train_batches))
            trial.set_user_attr("val_train_combo", str(combo_key))
            trial.set_user_attr("fold_scores", [float(v) for v in fold_scores])
            trial.set_user_attr("fold_score_mean", float(score_mean))
            trial.set_user_attr("fold_score_std", float(score_std))
            trial.set_user_attr("fold_accuracy_mean", float(np.mean(fold_accs)))
            trial.set_user_attr(
                "cross_direction_error", float(np.mean(fold_cross_errs))
            )
            trial.set_user_attr("n_train_samples", int(train_rows_total))
            trial.set_user_attr("n_val_samples", int(val_rows_total))
            trial.set_user_attr(
                "train_val_split", float(train_rows_total / train_total)
            )
            trial.set_user_attr("val_ratio", float(val_rows_total / train_total))
            trial.set_user_attr("n_features_final", int(len(all_feature_cols)))
            trial.set_user_attr("selected_features", all_feature_cols)
            trial.set_user_attr("selected_features_count", int(len(all_feature_cols)))
            trial.set_user_attr("window_selection_mode", "stage1_fold_cv_v1")
            trial.set_user_attr("stage1_stability_lambda", float(stability_lambda))
            trial.set_user_attr(
                "stage1_fold_windows",
                [
                    {
                        "fold_id": int(w["fold_id"]),
                        "train_start_batch": int(w["train_start_batch"]),
                        "train_end_batch": int(w["train_end_batch"]),
                        "val_start_batch": int(w["val_start_batch"]),
                        "val_end_batch": int(w["val_end_batch"]),
                        "val_batch": int(w["val_batch"]),
                    }
                    for w in windows
                ],
            )
            trial.set_user_attr(
                "stage1_fold_metrics_detailed",
                fold_metrics_detailed,
            )
            if nearest_window is not None:
                trial.set_user_attr("stage1_nearest_window", nearest_window)
            if pred_X is not None and pred_y is not None and nearest_model is not None:
                pred_proba, pred_labels = self._to_full_class_proba_and_pred(
                    nearest_model, nearest_model.predict_proba(pred_X)
                )
                pred_acc = float((pred_labels == pred_y).mean())
                pred_macro_f1 = float(
                    f1_score(pred_y, pred_labels, average="macro", zero_division=0)
                )
                pred_macro_f1_up = float(
                    compute_directional_macro_f1(
                        pred_y, pred_labels, list(self.config.class_names), direction=1
                    )
                )
                pred_macro_f1_down = float(
                    compute_directional_macro_f1(
                        pred_y, pred_labels, list(self.config.class_names), direction=0
                    )
                )
                pred_dir_acc = float(
                    compute_directional_accuracy(
                        pred_y, pred_labels, list(self.config.class_names)
                    )
                )
                pred_dir_prec_up = float(
                    compute_directional_precision(
                        pred_y, pred_labels, list(self.config.class_names), direction=1
                    )
                )
                pred_dir_prec_down = float(
                    compute_directional_precision(
                        pred_y, pred_labels, list(self.config.class_names), direction=0
                    )
                )
                pred_cross_err = float(
                    compute_cross_direction_error_rate(
                        pred_y, pred_labels, list(self.config.class_names)
                    )
                )
                pred_conf = confusion_matrix(
                    pred_y, pred_labels, labels=list(range(self.config.n_classes))
                )
                pred_true_prob = np.clip(
                    pred_proba[np.arange(len(pred_y)), pred_y],
                    1e-12,
                    1.0,
                )
                pred_nll_sum = float((-np.log(pred_true_prob)).sum())
                pred_ll = float(
                    log_loss(
                        pred_y,
                        pred_proba,
                        labels=list(range(self.config.n_classes)),
                    )
                )
                trial.set_user_attr("stage1_pred_batch", int(pred_batch))
                trial.set_user_attr("stage1_pred_n", int(len(pred_y)))
                trial.set_user_attr("stage1_pred_accuracy", pred_acc)
                trial.set_user_attr("stage1_pred_macro_f1", pred_macro_f1)
                trial.set_user_attr("stage1_pred_macro_f1_up", pred_macro_f1_up)
                trial.set_user_attr("stage1_pred_macro_f1_down", pred_macro_f1_down)
                trial.set_user_attr("stage1_pred_log_loss", pred_ll)
                trial.set_user_attr("stage1_pred_directional_accuracy", pred_dir_acc)
                trial.set_user_attr("stage1_pred_directional_precision_up", pred_dir_prec_up)
                trial.set_user_attr(
                    "stage1_pred_directional_precision_down", pred_dir_prec_down
                )
                trial.set_user_attr("stage1_pred_cross_direction_error", pred_cross_err)
                trial.set_user_attr(
                    "stage1_pred_confusion_flat",
                    [int(v) for v in pred_conf.reshape(-1).tolist()],
                )
                trial.set_user_attr("stage1_pred_nll_sum", pred_nll_sum)
            trial.set_user_attr("leakage_guard", "pass")
            return float(objective_score)

        if study_name is None:
            study_name = f"htf_5m_train_end_{train_end}"
        if study_storage_path:
            study_storage_path.parent.mkdir(parents=True, exist_ok=True)
            storage = f"sqlite:///{study_storage_path}"
            study = optuna.create_study(
                direction=direction,
                storage=storage,
                study_name=study_name,
                load_if_exists=True,
            )
        else:
            study = optuna.create_study(direction=direction, study_name=study_name)

        complete_before = [
            t for t in study.trials if t.state == optuna.trial.TrialState.COMPLETE
        ]
        complete_combo_keys = {
            (
                int(t.params.get("fold_count")),
                int(t.params.get("train_batches_per_fold")),
            )
            for t in complete_before
            if (
                "fold_count" in t.params
                and "train_batches_per_fold" in t.params
                and t.user_attrs.get("stage1_fold_metrics_detailed") is not None
            )
        }
        missing_combos = [c for c in all_combos if c not in complete_combo_keys]

        for f_count, t_batches in missing_combos:
            study.enqueue_trial(
                {
                    "fold_count": int(f_count),
                    "train_batches_per_fold": int(t_batches),
                }
            )

        # Stage-1 must evaluate all configured combinations for robust comparison.
        if missing_combos:
            study.optimize(
                objective,
                n_trials=len(missing_combos),
                timeout=None,
                show_progress_bar=False,
            )
        complete_trials = [
            t for t in study.trials if t.state == optuna.trial.TrialState.COMPLETE
        ]
        if not complete_trials:
            raise ValueError(
                f"No completed trials for {self.TIMEFRAME} train_end={train_end}. "
                "All trials were pruned or failed."
            )
        selection_mode = str(
            getattr(self.window_space, "stage1_trial_selection_mode", "objective")
        ).strip().lower()
        if selection_mode not in {"objective", "prediction_batch"}:
            selection_mode = "objective"

        configured_pred_metric = getattr(
            self.window_space, "stage1_prediction_metric", None
        )
        selection_metric = str(
            configured_pred_metric or self.config.optuna_metric
        ).strip().lower()

        pred_metric_map: dict[str, tuple[str, str]] = {
            "accuracy": ("stage1_pred_accuracy", "maximize"),
            "macro_f1": ("stage1_pred_macro_f1", "maximize"),
            "macro_f1_up": ("stage1_pred_macro_f1_up", "maximize"),
            "macro_f1_down": ("stage1_pred_macro_f1_down", "maximize"),
            "log_loss": ("stage1_pred_log_loss", "minimize"),
            "directional_accuracy": ("stage1_pred_directional_accuracy", "maximize"),
            "directional_precision_up": (
                "stage1_pred_directional_precision_up",
                "maximize",
            ),
            "directional_precision_down": (
                "stage1_pred_directional_precision_down",
                "maximize",
            ),
            "cross_direction_error": (
                "stage1_pred_cross_direction_error",
                "minimize",
            ),
        }

        def _best_by_objective(
            trials: list[optuna.trial.FrozenTrial],
        ) -> optuna.trial.FrozenTrial:
            return (
                min(trials, key=lambda t: float(t.value))
                if direction == "minimize"
                else max(trials, key=lambda t: float(t.value))
            )

        best_trial = _best_by_objective(complete_trials)
        selected_by = "objective"
        selection_attr = "optuna_score"
        selection_value = float(best_trial.value)

        if selection_mode == "prediction_batch":
            metric_spec = pred_metric_map.get(selection_metric)
            if metric_spec is not None:
                pred_attr, pred_direction = metric_spec
                pred_trials = [
                    t for t in complete_trials if t.user_attrs.get(pred_attr) is not None
                ]
                if pred_trials:
                    best_trial = (
                        min(pred_trials, key=lambda t: float(t.user_attrs[pred_attr]))
                        if pred_direction == "minimize"
                        else max(pred_trials, key=lambda t: float(t.user_attrs[pred_attr]))
                    )
                    selected_by = "prediction_batch"
                    selection_attr = pred_attr
                    selection_value = float(best_trial.user_attrs[pred_attr])
                else:
                    selected_by = "objective_fallback_no_pred_metric"
            else:
                selected_by = "objective_fallback_invalid_metric"

        fold_count = int(best_trial.user_attrs.get("fold_count", folds_min))
        val_batches_per_fold = int(
            best_trial.user_attrs.get(
                "val_batches_per_fold",
                getattr(self.window_space, "stage1_val_batches_per_fold", 1),
            )
        )
        train_batches = int(
            best_trial.user_attrs.get(
                "train_batches_per_fold",
                int(max(1, self.window_space.stage1_train_batches_min)),
            )
        )
        windows = self._build_stage1_fold_windows(
            train_end=train_end,
            fold_count=fold_count,
            train_batches_per_fold=train_batches,
            val_batches_per_fold=val_batches_per_fold,
            min_batch=min_batch,
        )
        if not windows:
            raise ValueError("stage1_fold_cv best trial produced invalid fold plan")

        combo_records = []
        combo_fold_records = []
        for t in complete_trials:
            rec = {
                "trial_number": int(t.number),
                "fold_count": (
                    int(t.params["fold_count"])
                    if "fold_count" in t.params
                    else int(t.user_attrs.get("fold_count", 0))
                ),
                "val_batches_per_fold": (
                    int(t.user_attrs["val_batches_per_fold"])
                    if t.user_attrs.get("val_batches_per_fold") is not None
                    else int(
                        getattr(self.window_space, "stage1_val_batches_per_fold", 1)
                    )
                ),
                "train_batches_per_fold": (
                    int(t.params["train_batches_per_fold"])
                    if "train_batches_per_fold" in t.params
                    else int(t.user_attrs.get("train_batches_per_fold", 0))
                ),
                "optuna_score": float(t.value),
                "fold_score_mean": (
                    float(t.user_attrs["fold_score_mean"])
                    if t.user_attrs.get("fold_score_mean") is not None
                    else None
                ),
                "fold_score_std": (
                    float(t.user_attrs["fold_score_std"])
                    if t.user_attrs.get("fold_score_std") is not None
                    else None
                ),
                "fold_accuracy_mean": (
                    float(t.user_attrs["fold_accuracy_mean"])
                    if t.user_attrs.get("fold_accuracy_mean") is not None
                    else None
                ),
                "cross_direction_error": (
                    float(t.user_attrs["cross_direction_error"])
                    if t.user_attrs.get("cross_direction_error") is not None
                    else None
                ),
                "n_train_samples": (
                    int(t.user_attrs["n_train_samples"])
                    if t.user_attrs.get("n_train_samples") is not None
                    else None
                ),
                "n_val_samples": (
                    int(t.user_attrs["n_val_samples"])
                    if t.user_attrs.get("n_val_samples") is not None
                    else None
                ),
                "pred_batch": (
                    int(t.user_attrs["stage1_pred_batch"])
                    if t.user_attrs.get("stage1_pred_batch") is not None
                    else None
                ),
                "pred_n": (
                    int(t.user_attrs["stage1_pred_n"])
                    if t.user_attrs.get("stage1_pred_n") is not None
                    else None
                ),
                "pred_accuracy": (
                    float(t.user_attrs["stage1_pred_accuracy"])
                    if t.user_attrs.get("stage1_pred_accuracy") is not None
                    else None
                ),
                "pred_macro_f1": (
                    float(t.user_attrs["stage1_pred_macro_f1"])
                    if t.user_attrs.get("stage1_pred_macro_f1") is not None
                    else None
                ),
                "pred_macro_f1_up": (
                    float(t.user_attrs["stage1_pred_macro_f1_up"])
                    if t.user_attrs.get("stage1_pred_macro_f1_up") is not None
                    else None
                ),
                "pred_macro_f1_down": (
                    float(t.user_attrs["stage1_pred_macro_f1_down"])
                    if t.user_attrs.get("stage1_pred_macro_f1_down") is not None
                    else None
                ),
                "pred_log_loss": (
                    float(t.user_attrs["stage1_pred_log_loss"])
                    if t.user_attrs.get("stage1_pred_log_loss") is not None
                    else None
                ),
                "pred_directional_accuracy": (
                    float(t.user_attrs["stage1_pred_directional_accuracy"])
                    if t.user_attrs.get("stage1_pred_directional_accuracy") is not None
                    else None
                ),
                "pred_directional_precision_up": (
                    float(t.user_attrs["stage1_pred_directional_precision_up"])
                    if t.user_attrs.get("stage1_pred_directional_precision_up") is not None
                    else None
                ),
                "pred_directional_precision_down": (
                    float(t.user_attrs["stage1_pred_directional_precision_down"])
                    if t.user_attrs.get("stage1_pred_directional_precision_down")
                    is not None
                    else None
                ),
                "pred_cross_direction_error": (
                    float(t.user_attrs["stage1_pred_cross_direction_error"])
                    if t.user_attrs.get("stage1_pred_cross_direction_error") is not None
                    else None
                ),
                "pred_confusion_flat": (
                    list(t.user_attrs["stage1_pred_confusion_flat"])
                    if t.user_attrs.get("stage1_pred_confusion_flat") is not None
                    else None
                ),
                "pred_nll_sum": (
                    float(t.user_attrs["stage1_pred_nll_sum"])
                    if t.user_attrs.get("stage1_pred_nll_sum") is not None
                    else None
                ),
                "stage1_execution_mode": "optuna",
                "objective_metric": str(self.config.optuna_metric),
                "objective_direction": str(direction),
                "selection_metric": str(selection_metric),
            }
            combo_records.append(rec)
            for fr in t.user_attrs.get("stage1_fold_metrics_detailed", []):
                combo_fold_records.append(
                    {
                        "trial_number": int(t.number),
                        "fold_count": int(rec["fold_count"]),
                        "val_batches_per_fold": int(rec["val_batches_per_fold"]),
                        "train_batches_per_fold": int(rec["train_batches_per_fold"]),
                        "optuna_score": float(rec["optuna_score"]),
                        "fold_id": int(fr.get("fold_id", 0)),
                        "train_start_batch": (
                            int(fr["train_start_batch"])
                            if fr.get("train_start_batch") is not None
                            else None
                        ),
                        "train_end_batch": (
                            int(fr["train_end_batch"])
                            if fr.get("train_end_batch") is not None
                            else None
                        ),
                        "val_start_batch": (
                            int(fr["val_start_batch"])
                            if fr.get("val_start_batch") is not None
                            else (
                                int(fr["val_batch"])
                                if fr.get("val_batch") is not None
                                else None
                            )
                        ),
                        "val_end_batch": (
                            int(fr["val_end_batch"])
                            if fr.get("val_end_batch") is not None
                            else (
                                int(fr["val_batch"])
                                if fr.get("val_batch") is not None
                                else None
                            )
                        ),
                        "val_batch": (
                            int(fr["val_batch"])
                            if fr.get("val_batch") is not None
                            else None
                        ),
                        "n_train_samples": (
                            int(fr["n_train_samples"])
                            if fr.get("n_train_samples") is not None
                            else None
                        ),
                        "n_val_samples": (
                            int(fr["n_val_samples"])
                            if fr.get("n_val_samples") is not None
                            else None
                        ),
                        "fold_score": (
                            float(fr["fold_score"])
                            if fr.get("fold_score") is not None
                            else None
                        ),
                        "fold_accuracy": (
                            float(fr["fold_accuracy"])
                            if fr.get("fold_accuracy") is not None
                            else None
                        ),
                        "fold_macro_f1": (
                            float(fr["fold_macro_f1"])
                            if fr.get("fold_macro_f1") is not None
                            else None
                        ),
                        "fold_directional_accuracy": (
                            float(fr["fold_directional_accuracy"])
                            if fr.get("fold_directional_accuracy") is not None
                            else None
                        ),
                        "fold_directional_precision_up": (
                            float(fr["fold_directional_precision_up"])
                            if fr.get("fold_directional_precision_up") is not None
                            else None
                        ),
                        "fold_directional_precision_down": (
                            float(fr["fold_directional_precision_down"])
                            if fr.get("fold_directional_precision_down") is not None
                            else None
                        ),
                        "fold_cross_direction_error": (
                            float(fr["fold_cross_direction_error"])
                            if fr.get("fold_cross_direction_error") is not None
                            else None
                        ),
                        "n_classes": (
                            int(fr["n_classes"])
                            if fr.get("n_classes") is not None
                            else None
                        ),
                        "confusion_flat": (
                            list(fr["confusion_flat"])
                            if fr.get("confusion_flat") is not None
                            else None
                        ),
                        "nll_sum": (
                            float(fr["nll_sum"])
                            if fr.get("nll_sum") is not None
                            else None
                        ),
                    }
                )

        nearest = windows[0]
        tv_embargo, vp_embargo = self._stage1_resolve_embargo()
        lookback_batches = int(
            train_batches + fold_count * val_batches_per_fold + tv_embargo + vp_embargo
        )
        split_from_trial = float(best_trial.user_attrs.get("train_val_split", 0.8))
        val_from_trial = float(best_trial.user_attrs.get("val_ratio", 0.2))
        if not (0.0 < split_from_trial < 1.0):
            split_from_trial = 0.8
        if not (0.0 < val_from_trial < 1.0):
            val_from_trial = 0.2

        return {
            "best_score": float(selection_value),
            "best_objective_score": float(best_trial.value),
            "optuna_metric": self.config.optuna_metric,
            "optuna_direction": direction,
            "best_accuracy": best_trial.user_attrs.get("fold_accuracy_mean"),
            "directional_accuracy": None,
            "directional_precision_up": None,
            "directional_precision_down": None,
            "cross_direction_error": best_trial.user_attrs.get(
                "cross_direction_error"
            ),
            "cb_params": base_params.copy(),
            "num_boost_round": baseline_iterations,
            "lookback_batches": lookback_batches,
            "window_selection_mode": "stage1_fold_cv_v1",
            "decay_weight": 1.0,
            "class_weight_method": "none",
            "train_val_split": split_from_trial,
            "val_ratio": val_from_trial,
            "window_distribution_score": float(best_trial.user_attrs.get("optuna_score", 0.0)),
            "train_start_batch": int(nearest["train_start_batch"]),
            "train_end_batch": int(nearest["train_end_batch"]),
            "val_start_batch": int(nearest["val_start_batch"]),
            "val_end_batch": int(nearest["val_end_batch"]),
            "embargo_train_val_batches": int(tv_embargo),
            "embargo_val_pred_batches": int(vp_embargo),
            "reference_distribution_mode": "stage1_fold_cv",
            "recent_ref_batches": 0,
            "recent_ref_weight": 0.0,
            "active_class_min_frac": 0.0,
            "min_val_samples_per_active_class": 0,
            "active_class_ids": list(range(self.config.n_classes)),
            "reference_distribution": [],
            "recent_class_counts": [],
            "window_class_counts": [],
            "train_class_counts": [],
            "val_class_counts": [],
            "total_class_counts": [],
            "distribution_mse_train": 0.0,
            "distribution_mse_val": 0.0,
            "distribution_mse_window": 0.0,
            "distribution_mse_train_val": 0.0,
            "missing_classes_train": 0,
            "missing_classes_val": 0,
            "selected_features": all_feature_cols,
            "n_features": len(all_feature_cols),
            "study": study,
            "per_class_accuracy": {},
            "per_class_count": {},
            "log_loss": None,
            "n_train_samples": best_trial.user_attrs.get("n_train_samples"),
            "n_val_samples": best_trial.user_attrs.get("n_val_samples"),
            "leakage_guard": str(best_trial.user_attrs.get("leakage_guard", "pass")),
            "stage1_fold_count": fold_count,
            "stage1_val_batches_per_fold": val_batches_per_fold,
            "stage1_train_batches_per_fold": train_batches,
            "stage1_fold_score_mean": best_trial.user_attrs.get("fold_score_mean"),
            "stage1_fold_score_std": best_trial.user_attrs.get("fold_score_std"),
            "stage1_stability_lambda": stability_lambda,
            "stage1_fold_scores": list(best_trial.user_attrs.get("fold_scores", [])),
            "stage1_fold_windows": best_trial.user_attrs.get("stage1_fold_windows", []),
            "stage1_pred_batch": best_trial.user_attrs.get("stage1_pred_batch"),
            "stage1_pred_n": best_trial.user_attrs.get("stage1_pred_n"),
            "stage1_pred_accuracy": best_trial.user_attrs.get("stage1_pred_accuracy"),
            "stage1_pred_macro_f1": best_trial.user_attrs.get("stage1_pred_macro_f1"),
            "stage1_pred_macro_f1_up": best_trial.user_attrs.get(
                "stage1_pred_macro_f1_up"
            ),
            "stage1_pred_macro_f1_down": best_trial.user_attrs.get(
                "stage1_pred_macro_f1_down"
            ),
            "stage1_pred_log_loss": best_trial.user_attrs.get("stage1_pred_log_loss"),
            "stage1_pred_directional_accuracy": best_trial.user_attrs.get(
                "stage1_pred_directional_accuracy"
            ),
            "stage1_pred_directional_precision_up": best_trial.user_attrs.get(
                "stage1_pred_directional_precision_up"
            ),
            "stage1_pred_directional_precision_down": best_trial.user_attrs.get(
                "stage1_pred_directional_precision_down"
            ),
            "stage1_pred_cross_direction_error": best_trial.user_attrs.get(
                "stage1_pred_cross_direction_error"
            ),
            "stage1_combo_count_total": int(len(all_combos)),
            "stage1_combo_count_completed": int(len(combo_records)),
            "stage1_combo_count_missing": int(max(0, len(all_combos) - len(combo_records))),
            "stage1_all_combos_evaluated": bool(len(combo_records) >= len(all_combos)),
            "stage1_execution_mode": "optuna",
            "stage1_trial_selection_mode": selection_mode,
            "stage1_prediction_metric": selection_metric,
            "stage1_selected_by": selected_by,
            "stage1_selection_attr": selection_attr,
            "stage1_selected_trial_number": int(best_trial.number),
            "stage1_selection_value": float(selection_value),
            "stage1_pred_confusion_flat": best_trial.user_attrs.get(
                "stage1_pred_confusion_flat"
            ),
            "stage1_pred_nll_sum": best_trial.user_attrs.get("stage1_pred_nll_sum"),
            "stage1_combo_metrics": combo_records,
            "stage1_combo_fold_metrics": combo_fold_records,
        }

    def load_available_batches(self, train_end: int) -> pl.DataFrame:
        """Load batches within lookback range up to train_end."""
        mode = str(getattr(self.window_space, "window_selection_mode", "legacy_grid"))
        if mode == "stage1_fold_cv":
            embargo_tv, embargo_vp = self._stage1_resolve_embargo()
            required = int(
                max(
                    self.window_space.lookback_max,
                    self.window_space.stage1_train_batches_max
                    + self.window_space.stage1_folds_max
                    + embargo_tv
                    + embargo_vp,
                )
            )
            start = max(1, train_end - required + 1)
        else:
            start = max(1, train_end - self.window_space.lookback_max + 1)
        return load_batches_range(
            self.config.features_dir,
            self.config.labels_dir,
            self.TIMEFRAME,
            start,
            train_end + 1,
            target_col=self.config.target,
            feature_target_col=(self.config.feature_target or self.config.target),
            exclude_tail_pct=self.config.exclude_tail_pct,
        )

    def create_objective(
        self,
        df_all: pl.DataFrame,
        all_feature_cols: list[str],
        window_plan: dict,
        train_end: int,
    ):
        """Create Optuna objective function for this step."""
        def objective(trial: optuna.Trial) -> float:
            from sklearn.metrics import accuracy_score as acc_score

            # PHASE 1: WINDOW SIZE (distribution-estimated, no Optuna grid search)
            lookback = int(window_plan["lookback_batches"])
            decay = trial.suggest_float(
                "decay_weight", self.window_space.decay_min, self.window_space.decay_max
            )

            min_batch = int(window_plan["window_start_batch"])
            max_batch = int(window_plan["window_end_batch"])
            df_window = df_all.filter(
                (pl.col("batch_id") >= min_batch) & (pl.col("batch_id") <= max_batch)
            )
            if getattr(self.config, "shuffle_batches", False):
                rng = np.random.default_rng(self.config.shuffle_batches_seed)
                ordered = df_window["batch_id"].unique().to_list()
                rng.shuffle(ordered)
                df_window = pl.concat(
                    [df_window.filter(pl.col("batch_id") == bid) for bid in ordered]
                )
            if len(df_window) == 0:
                raise optuna.TrialPruned("empty window after filtering")
            if int(df_window["batch_id"].max()) > int(train_end):
                raise optuna.TrialPruned("leakage guard: window exceeds train_end")

            # PHASE 2: FEATURE SELECTION
            feature_k = trial.suggest_int(
                "feature_k",
                self.feature_space.feature_k_min,
                min(self.feature_space.feature_k_max, len(all_feature_cols)),
            )
            corr_threshold = trial.suggest_float(
                "corr_threshold",
                self.feature_space.corr_threshold_min,
                self.feature_space.corr_threshold_max,
            )

            X_all, y_all, _, _ = prepare_features_target(
                df_window, all_feature_cols, self.config.target
            )

            if X_all is None or len(y_all) < 200:
                raise optuna.TrialPruned("not enough samples")

            total_counts = np.bincount(y_all, minlength=self.config.n_classes)
            min_required = self.window_space.min_samples_per_class
            if min_required and (total_counts < min_required).any():
                raise optuna.TrialPruned(
                    f"insufficient class samples (min_required={min_required})"
                )
            trial.set_user_attr("total_class_counts", total_counts.tolist())
            trial.set_user_attr(
                "window_selection_mode",
                str(window_plan.get("window_selection_mode", "legacy_grid_v1")),
            )
            trial.set_user_attr("lookback_batches", lookback)
            trial.set_user_attr("window_start_batch", int(window_plan["window_start_batch"]))
            trial.set_user_attr("window_end_batch", int(window_plan["window_end_batch"]))
            trial.set_user_attr("train_end_batch", int(window_plan["train_end_batch"]))
            trial.set_user_attr("train_start_batch", int(window_plan["train_start_batch"]))
            trial.set_user_attr("val_start_batch", int(window_plan["val_start_batch"]))
            trial.set_user_attr("val_end_batch", int(window_plan["val_end_batch"]))
            trial.set_user_attr(
                "embargo_train_val_batches",
                int(window_plan.get("embargo_train_val_batches", 0)),
            )
            trial.set_user_attr(
                "embargo_val_pred_batches",
                int(window_plan.get("embargo_val_pred_batches", 0)),
            )
            trial.set_user_attr(
                "reference_distribution_mode",
                str(window_plan.get("reference_distribution_mode", "all_history")),
            )
            trial.set_user_attr(
                "recent_ref_batches",
                int(window_plan.get("recent_ref_batches", 0)),
            )
            trial.set_user_attr(
                "recent_ref_weight",
                float(window_plan.get("recent_ref_weight", 0.0)),
            )
            trial.set_user_attr(
                "active_class_min_frac",
                float(window_plan.get("active_class_min_frac", 0.0)),
            )
            trial.set_user_attr(
                "min_val_samples_per_active_class",
                int(window_plan.get("min_val_samples_per_active_class", 0)),
            )
            trial.set_user_attr(
                "active_class_ids",
                window_plan.get("active_class_ids", []),
            )
            trial.set_user_attr("window_distribution_score", float(window_plan["score"]))
            trial.set_user_attr(
                "window_missing_classes_train",
                int(window_plan["missing_classes_train"]),
            )
            trial.set_user_attr(
                "window_missing_classes_val",
                int(window_plan["missing_classes_val"]),
            )

            selected_features = select_features_by_mi(
                X_all, y_all, all_feature_cols, feature_k
            )
            feat_indices = [all_feature_cols.index(f) for f in selected_features]
            X_selected = X_all[:, feat_indices]

            kept_features = drop_correlated_features(
                X_selected, selected_features, corr_threshold
            )
            feat_indices = [selected_features.index(f) for f in kept_features]
            X_final = X_selected[:, feat_indices]

            if X_final.shape[1] < 10:
                raise optuna.TrialPruned("too few features after filtering")

            # Track selected features for trial analysis
            feat_sig = "|".join(kept_features)
            trial.set_user_attr("selected_features", kept_features)
            trial.set_user_attr(
                "selected_features_hash", hashlib.md5(feat_sig.encode()).hexdigest()
            )
            trial.set_user_attr("selected_features_count", int(len(kept_features)))

            # PHASE 3: CLASS WEIGHTING
            weight_choices = list(
                getattr(
                    self.config,
                    "class_weight_choices",
                    ("none", "balanced", "sqrt"),
                )
            )
            if not weight_choices:
                raise optuna.TrialPruned("class_weight_choices is empty")
            weight_method = trial.suggest_categorical(
                "class_weight_method", weight_choices
            )
            class_weights = compute_class_weights(y_all, weight_method)

            # PHASE 4: MODEL HYPERPARAMETERS
            params = self.config.cb_base_params.copy()
            params.update(
                {
                    "learning_rate": trial.suggest_float(
                        "lr",
                        self.model_space.learning_rate_min,
                        self.model_space.learning_rate_max,
                        log=True,
                    ),
                    "depth": trial.suggest_int(
                        "max_depth",
                        self.model_space.max_depth_min,
                        self.model_space.max_depth_max,
                    ),
                    "min_data_in_leaf": trial.suggest_int(
                        "min_child_samples",
                        self.model_space.min_child_samples_min,
                        self.model_space.min_child_samples_max,
                    ),
                    "l2_leaf_reg": trial.suggest_float(
                        "reg_lambda",
                        self.model_space.reg_lambda_min,
                        self.model_space.reg_lambda_max,
                        log=True,
                    ),
                    "random_strength": trial.suggest_float(
                        "reg_alpha",
                        self.model_space.reg_alpha_min,
                        self.model_space.reg_alpha_max,
                        log=True,
                    ),
                    "subsample": trial.suggest_float(
                        "subsample",
                        self.model_space.subsample_min,
                        self.model_space.subsample_max,
                    ),
                    "rsm": trial.suggest_float(
                        "colsample_bytree",
                        self.model_space.colsample_bytree_min,
                        self.model_space.colsample_bytree_max,
                    ),
                }
            )

            num_boost_round = trial.suggest_int(
                "num_boost_round",
                self.model_space.num_boost_round_min,
                self.model_space.num_boost_round_max,
            )

            # TRAIN / VALIDATE
            train_start_batch = int(window_plan["train_start_batch"])
            train_end_batch = int(window_plan["train_end_batch"])
            val_start_batch = int(window_plan["val_start_batch"])
            val_end_batch = int(window_plan["val_end_batch"])

            df_train = df_window.filter(
                (pl.col("batch_id") >= train_start_batch)
                & (pl.col("batch_id") <= train_end_batch)
            )
            df_val = df_window.filter(
                (pl.col("batch_id") >= val_start_batch)
                & (pl.col("batch_id") <= val_end_batch)
            )
            if len(df_train) == 0 or len(df_val) == 0:
                raise optuna.TrialPruned("empty train/val window")
            if int(df_train["batch_id"].max()) > int(train_end):
                raise optuna.TrialPruned("leakage guard: train exceeds train_end")
            if int(df_val["batch_id"].max()) > int(train_end):
                raise optuna.TrialPruned("leakage guard: val exceeds train_end")

            X_train, y_train, _, _ = prepare_features_target(
                df_train, kept_features, self.config.target
            )
            X_val, y_val, _, _ = prepare_features_target(
                df_val, kept_features, self.config.target
            )
            X_train = np.nan_to_num(X_train, nan=0.0, posinf=0.0, neginf=0.0)
            X_val = np.nan_to_num(X_val, nan=0.0, posinf=0.0, neginf=0.0)

            raw_n_train = int(len(y_train))
            raw_n_val = int(len(y_val))
            # Split ratios should reflect the effective train/val rows used by
            # this trial (same feature set), not the broader all-feature window.
            raw_total = max(1, raw_n_train + raw_n_val)
            raw_train_ratio = float(raw_n_train / raw_total)
            raw_val_ratio = float(raw_n_val / raw_total)

            train_counts = np.bincount(y_train, minlength=self.config.n_classes)
            val_counts = np.bincount(y_val, minlength=self.config.n_classes)
            active_class_ids = [
                int(c)
                for c in window_plan.get("active_class_ids", list(range(self.config.n_classes)))
                if 0 <= int(c) < self.config.n_classes
            ]
            if not active_class_ids:
                active_class_ids = list(range(self.config.n_classes))
            min_val_active = max(
                1, int(window_plan.get("min_val_samples_per_active_class", 1))
            )
            missing_train_active = [c for c in active_class_ids if int(train_counts[c]) <= 0]
            missing_val_active = [
                c for c in active_class_ids if int(val_counts[c]) < min_val_active
            ]
            if missing_train_active:
                raise optuna.TrialPruned(
                    f"missing active class in train split: {missing_train_active}"
                )
            if missing_val_active:
                raise optuna.TrialPruned(
                    "insufficient active class samples in val split: "
                    f"{missing_val_active} (min={min_val_active})"
                )
            trial.set_user_attr("train_class_counts", train_counts.tolist())
            trial.set_user_attr("val_class_counts", val_counts.tolist())
            trial.set_user_attr("active_missing_train", missing_train_active)
            trial.set_user_attr("active_missing_val", missing_val_active)
            trial.set_user_attr("leakage_guard", "pass")

            if getattr(self.config, "balance_strategy", "none") != "none":
                strategy = self.config.balance_strategy
                apply_to = self.config.balance_apply_to
                if apply_to in {"train", "train_val"}:
                    idx = balanced_resample_indices(
                        y_train, strategy, seed=self.config.shuffle_seed
                    )
                    X_train, y_train = X_train[idx], y_train[idx]
                if apply_to == "train_val":
                    idx = balanced_resample_indices(
                        y_val, strategy, seed=self.config.shuffle_seed + 1
                    )
                    X_val, y_val = X_val[idx], y_val[idx]

            decay_weights = apply_sample_weights(len(y_train), decay)
            if class_weights:
                class_sample_weights = weights_to_sample_weights(y_train, class_weights)
                sample_weights = decay_weights * class_sample_weights
            else:
                sample_weights = decay_weights

            try:
                model = CatBoostClassifier(
                    **params,
                    iterations=num_boost_round,
                )
                model.fit(
                    X_train,
                    y_train,
                    sample_weight=sample_weights,
                    eval_set=(X_val, y_val),
                    use_best_model=True,
                    early_stopping_rounds=50,
                    verbose=False,
                )
            except Exception as e:
                # Always try CPU fallback (handles missing GPU/CUDA runtime)
                params_cpu = params.copy()
                params_cpu["task_type"] = "CPU"
                params_cpu.pop("devices", None)
                try:
                    model = CatBoostClassifier(
                        **params_cpu,
                        iterations=num_boost_round,
                    )
                    model.fit(
                        X_train,
                        y_train,
                        sample_weight=sample_weights,
                        eval_set=(X_val, y_val),
                        use_best_model=True,
                        early_stopping_rounds=50,
                        verbose=False,
                    )
                    trial.set_user_attr("cpu_fallback", True)
                except Exception as e2:
                    trial.set_user_attr(
                        "train_fail",
                        f"gpu_error={e}; cpu_error={e2}",
                    )
                    raise optuna.TrialPruned(f"train failed on CPU: {e2}")

            pred_proba, y_pred = self._to_full_class_proba_and_pred(
                model, model.predict_proba(X_val)
            )
            accuracy = acc_score(y_val, y_pred)
            val_log_loss = float(
                log_loss(
                    y_val,
                    pred_proba,
                    labels=list(range(self.config.n_classes)),
                )
            )

            metric = self.config.optuna_metric
            if metric == "accuracy":
                score = accuracy
            elif metric == "log_loss":
                score = val_log_loss
            elif metric == "balanced_accuracy":
                score = balanced_accuracy_score(y_val, y_pred)
            elif metric == "macro_f1":
                score = f1_score(y_val, y_pred, average="macro", zero_division=0)
            elif metric == "macro_f1_up":
                score = compute_directional_macro_f1(
                    y_val, y_pred, list(self.config.class_names), direction=1
                )
            elif metric == "macro_f1_down":
                score = compute_directional_macro_f1(
                    y_val, y_pred, list(self.config.class_names), direction=0
                )
            elif metric == "directional_accuracy":
                score = compute_directional_accuracy(
                    y_val, y_pred, list(self.config.class_names)
                )
            elif metric == "directional_precision_up":
                score = compute_directional_precision(
                    y_val, y_pred, list(self.config.class_names), direction=1
                )
            elif metric == "directional_precision_down":
                score = compute_directional_precision(
                    y_val, y_pred, list(self.config.class_names), direction=0
                )
            elif metric == "cross_direction_error":
                score = compute_cross_direction_error_rate(
                    y_val, y_pred, list(self.config.class_names)
                )
            else:
                raise ValueError(f"Unknown optuna_metric: {metric}")

            dir_acc = compute_directional_accuracy(
                y_val, y_pred, list(self.config.class_names)
            )
            dir_prec_up = compute_directional_precision(
                y_val, y_pred, list(self.config.class_names), direction=1
            )
            dir_prec_down = compute_directional_precision(
                y_val, y_pred, list(self.config.class_names), direction=0
            )
            dir_cross_err = compute_cross_direction_error_rate(
                y_val, y_pred, list(self.config.class_names)
            )

            trial.set_user_attr("optuna_metric", metric)
            trial.set_user_attr("optuna_score", float(score))
            trial.set_user_attr("val_accuracy", float(accuracy))
            trial.set_user_attr("log_loss", val_log_loss)
            trial.set_user_attr("directional_accuracy", float(dir_acc))
            trial.set_user_attr("directional_precision_up", float(dir_prec_up))
            trial.set_user_attr("directional_precision_down", float(dir_prec_down))
            trial.set_user_attr("cross_direction_error", float(dir_cross_err))
            trial.set_user_attr("n_train_samples", len(y_train))
            trial.set_user_attr("n_val_samples", len(y_val))
            trial.set_user_attr("n_features_final", X_final.shape[1])
            # Save split ratios before any optional class balancing.
            trial.set_user_attr("train_val_split", raw_train_ratio)
            trial.set_user_attr("val_ratio", raw_val_ratio)
            trial.set_user_attr(
                "macro_f1_up",
                compute_directional_macro_f1(
                    y_val, y_pred, list(self.config.class_names), direction=1
                ),
            )
            trial.set_user_attr(
                "macro_f1_down",
                compute_directional_macro_f1(
                    y_val, y_pred, list(self.config.class_names), direction=0
                ),
            )
            trial.set_user_attr(
                "distribution_mse_train",
                float(window_plan.get("distribution_mse_train", 0.0)),
            )
            trial.set_user_attr(
                "distribution_mse_val",
                float(window_plan.get("distribution_mse_val", 0.0)),
            )
            trial.set_user_attr(
                "distribution_mse_window",
                float(window_plan.get("distribution_mse_window", 0.0)),
            )
            trial.set_user_attr(
                "distribution_mse_train_val",
                float(window_plan.get("distribution_mse_train_val", 0.0)),
            )

            for c in range(self.config.n_classes):
                mask = y_val == c
                if mask.sum() > 0:
                    class_acc = (y_pred[mask] == c).mean()
                    trial.set_user_attr(f"class_{c}_accuracy", float(class_acc))
                    trial.set_user_attr(f"class_{c}_count", int(mask.sum()))

            return score

        return objective

    def optimize(
        self,
        train_end: int,
        n_trials: int = 30,
        timeout: int = 180,
        study_storage_path: Path | None = None,
        study_name: str | None = None,
    ) -> dict:
        """Run full optimization for this step."""
        # Silence Optuna's per-trial INFO logs for cleaner output
        optuna.logging.set_verbosity(optuna.logging.WARNING)

        df_all = self.load_available_batches(train_end)
        if len(df_all) == 0:
            raise ValueError("No rows available in optimization window")
        if int(df_all["batch_id"].max()) > int(train_end):
            raise ValueError("leakage guard failed: optimization window exceeds train_end")
        all_feature_cols = get_feature_columns(df_all, self.config.target)
        mode = str(getattr(self.window_space, "window_selection_mode", "legacy_grid"))
        if mode == "stage1_fold_cv":
            return self._optimize_stage1_fold_cv(
                train_end=train_end,
                df_all=df_all,
                all_feature_cols=all_feature_cols,
                n_trials=n_trials,
                timeout=timeout,
                study_storage_path=study_storage_path,
                study_name=study_name,
            )

        ref_counts = compute_class_counts_up_to(
            labels_dir=self.config.labels_dir,
            tf=self.TIMEFRAME,
            target_col=self.config.target,
            n_classes=self.config.n_classes,
            train_end=train_end,
        )
        window_plan = estimate_lookback_and_split(
            df=df_all,
            target_col=self.config.target,
            n_classes=self.config.n_classes,
            lookback_min=self.window_space.lookback_min,
            lookback_max=self.window_space.lookback_max,
            lookback_grid=self.window_space.lookback_grid,
            min_samples_per_class=self.window_space.min_samples_per_class,
            preferred_train_split=self.config.train_val_split,
            reference_class_counts=ref_counts,
            window_selection_mode=self.window_space.window_selection_mode,
            train_share_min=self.window_space.train_share_min,
            train_share_max=self.window_space.train_share_max,
            embargo_mode=self.window_space.embargo_mode,
            embargo_train_val_batches=self.window_space.embargo_train_val_batches,
            embargo_val_pred_batches=self.window_space.embargo_val_pred_batches,
            solver_step_batches=self.window_space.solver_step_batches,
            reference_distribution_mode=self.window_space.reference_distribution_mode,
            recent_ref_batches=self.window_space.recent_ref_batches,
            recent_ref_weight=self.window_space.recent_ref_weight,
            active_class_min_frac=self.window_space.active_class_min_frac,
            min_val_samples_per_active_class=self.window_space.min_val_samples_per_active_class,
        )

        objective = self.create_objective(
            df_all,
            all_feature_cols,
            window_plan,
            train_end=train_end,
        )

        if study_name is None:
            study_name = f"htf_5m_train_end_{train_end}"

        if study_storage_path:
            study_storage_path.parent.mkdir(parents=True, exist_ok=True)
            storage = f"sqlite:///{study_storage_path}"
            study = optuna.create_study(
                direction=self.config.optuna_direction(),
                storage=storage,
                study_name=study_name,
                load_if_exists=True,
            )
        else:
            study = optuna.create_study(
                direction=self.config.optuna_direction(),
                study_name=study_name,
            )

        study.optimize(
            objective, n_trials=n_trials, timeout=timeout, show_progress_bar=False
        )

        complete_trials = [
            t
            for t in study.trials
            if t.state == optuna.trial.TrialState.COMPLETE
        ]
        if not complete_trials:
            raise ValueError(
                f"No completed trials for {self.TIMEFRAME} train_end={train_end}. "
                "All trials were pruned or failed."
            )
        if self.config.optuna_direction() == "minimize":
            best_trial = min(complete_trials, key=lambda t: float(t.value))
        else:
            best_trial = max(complete_trials, key=lambda t: float(t.value))
        best = best_trial.params

        # Reconstruct selected features with best params
        lookback_best = int(best_trial.user_attrs.get("lookback_batches", window_plan["lookback_batches"]))
        min_batch = int(best_trial.user_attrs.get("window_start_batch", window_plan["window_start_batch"]))
        max_batch = int(best_trial.user_attrs.get("window_end_batch", window_plan["window_end_batch"]))
        df_window = df_all.filter(
            (pl.col("batch_id") >= min_batch) & (pl.col("batch_id") <= max_batch)
        )
        if getattr(self.config, "shuffle_batches", False):
            rng = np.random.default_rng(self.config.shuffle_batches_seed)
            ordered = df_window["batch_id"].unique().to_list()
            rng.shuffle(ordered)
            df_window = pl.concat(
                [df_window.filter(pl.col("batch_id") == bid) for bid in ordered]
            )

        X_all, y_all, _, _ = prepare_features_target(
            df_window, all_feature_cols, self.config.target
        )
        X_all = np.nan_to_num(X_all, nan=0.0, posinf=0.0, neginf=0.0)

        selected_features = select_features_by_mi(
            X_all, y_all, all_feature_cols, best["feature_k"]
        )
        feat_indices = [all_feature_cols.index(f) for f in selected_features]
        X_selected = X_all[:, feat_indices]

        kept_features = drop_correlated_features(
            X_selected, selected_features, best["corr_threshold"]
        )

        cb_params = self.config.cb_base_params.copy()
        cb_params.update(
            {
                "learning_rate": best["lr"],
                "depth": best["max_depth"],
                "min_data_in_leaf": best["min_child_samples"],
                "l2_leaf_reg": best["reg_lambda"],
                "random_strength": best["reg_alpha"],
                "subsample": best["subsample"],
                "rsm": best["colsample_bytree"],
            }
        )

        per_class_accuracy = {}
        per_class_count = {}
        for c in range(self.config.n_classes):
            acc_key = f"class_{c}_accuracy"
            count_key = f"class_{c}_count"
            if acc_key in best_trial.user_attrs:
                per_class_accuracy[c] = best_trial.user_attrs[acc_key]
            if count_key in best_trial.user_attrs:
                per_class_count[c] = best_trial.user_attrs[count_key]

        split_from_trial = float(
            best_trial.user_attrs.get("train_val_split", window_plan["train_val_split"])
        )
        if not (0.0 < split_from_trial < 1.0):
            split_from_trial = float(window_plan["train_val_split"])
        val_from_trial = float(
            best_trial.user_attrs.get("val_ratio", 1.0 - split_from_trial)
        )
        if not (0.0 < val_from_trial < 1.0):
            val_from_trial = 1.0 - split_from_trial
        if abs((split_from_trial + val_from_trial) - 1.0) > 0.05:
            val_from_trial = 1.0 - split_from_trial

        return {
            "best_score": float(best_trial.value),
            "optuna_metric": self.config.optuna_metric,
            "optuna_direction": self.config.optuna_direction(),
            "best_accuracy": best_trial.user_attrs.get("val_accuracy"),
            "directional_accuracy": best_trial.user_attrs.get("directional_accuracy"),
            "directional_precision_up": best_trial.user_attrs.get(
                "directional_precision_up"
            ),
            "directional_precision_down": best_trial.user_attrs.get(
                "directional_precision_down"
            ),
            "cross_direction_error": best_trial.user_attrs.get(
                "cross_direction_error"
            ),
            "cb_params": cb_params,
            "num_boost_round": best["num_boost_round"],
            "lookback_batches": lookback_best,
            "window_selection_mode": best_trial.user_attrs.get(
                "window_selection_mode",
                window_plan.get("window_selection_mode"),
            ),
            "decay_weight": best["decay_weight"],
            "class_weight_method": best["class_weight_method"],
            "train_val_split": split_from_trial,
            "val_ratio": val_from_trial,
            "window_distribution_score": float(
                best_trial.user_attrs.get("window_distribution_score", window_plan["score"])
            ),
            "train_start_batch": int(
                best_trial.user_attrs.get(
                    "train_start_batch", window_plan["train_start_batch"]
                )
            ),
            "train_end_batch": int(
                best_trial.user_attrs.get(
                    "train_end_batch", window_plan["train_end_batch"]
                )
            ),
            "val_start_batch": int(
                best_trial.user_attrs.get(
                    "val_start_batch", window_plan["val_start_batch"]
                )
            ),
            "val_end_batch": int(
                best_trial.user_attrs.get(
                    "val_end_batch", window_plan["val_end_batch"]
                )
            ),
            "embargo_train_val_batches": int(
                best_trial.user_attrs.get(
                    "embargo_train_val_batches",
                    window_plan.get("embargo_train_val_batches", 0),
                )
            ),
            "embargo_val_pred_batches": int(
                best_trial.user_attrs.get(
                    "embargo_val_pred_batches",
                    window_plan.get("embargo_val_pred_batches", 0),
                )
            ),
            "reference_distribution_mode": str(
                best_trial.user_attrs.get(
                    "reference_distribution_mode",
                    window_plan.get("reference_distribution_mode", "all_history"),
                )
            ),
            "recent_ref_batches": int(
                best_trial.user_attrs.get(
                    "recent_ref_batches",
                    window_plan.get("recent_ref_batches", 0),
                )
            ),
            "recent_ref_weight": float(
                best_trial.user_attrs.get(
                    "recent_ref_weight",
                    window_plan.get("recent_ref_weight", 0.0),
                )
            ),
            "active_class_min_frac": float(
                best_trial.user_attrs.get(
                    "active_class_min_frac",
                    window_plan.get("active_class_min_frac", 0.0),
                )
            ),
            "min_val_samples_per_active_class": int(
                best_trial.user_attrs.get(
                    "min_val_samples_per_active_class",
                    window_plan.get("min_val_samples_per_active_class", 0),
                )
            ),
            "active_class_ids": list(
                best_trial.user_attrs.get(
                    "active_class_ids",
                    window_plan.get("active_class_ids", []),
                )
            ),
            "reference_distribution": list(
                window_plan.get("reference_distribution", [])
            ),
            "recent_class_counts": list(window_plan.get("recent_class_counts", [])),
            "window_class_counts": list(window_plan.get("window_class_counts", [])),
            "train_class_counts": list(
                best_trial.user_attrs.get(
                    "train_class_counts",
                    window_plan.get("train_class_counts", []),
                )
            ),
            "val_class_counts": list(
                best_trial.user_attrs.get(
                    "val_class_counts",
                    window_plan.get("val_class_counts", []),
                )
            ),
            "total_class_counts": list(
                best_trial.user_attrs.get("total_class_counts", [])
            ),
            "distribution_mse_train": float(
                best_trial.user_attrs.get(
                    "distribution_mse_train",
                    window_plan.get("distribution_mse_train", 0.0),
                )
            ),
            "distribution_mse_val": float(
                best_trial.user_attrs.get(
                    "distribution_mse_val",
                    window_plan.get("distribution_mse_val", 0.0),
                )
            ),
            "distribution_mse_window": float(
                best_trial.user_attrs.get(
                    "distribution_mse_window",
                    window_plan.get("distribution_mse_window", 0.0),
                )
            ),
            "distribution_mse_train_val": float(
                best_trial.user_attrs.get(
                    "distribution_mse_train_val",
                    window_plan.get("distribution_mse_train_val", 0.0),
                )
            ),
            "missing_classes_train": int(
                best_trial.user_attrs.get(
                    "window_missing_classes_train",
                    window_plan.get("missing_classes_train", 0),
                )
            ),
            "missing_classes_val": int(
                best_trial.user_attrs.get(
                    "window_missing_classes_val",
                    window_plan.get("missing_classes_val", 0),
                )
            ),
            "selected_features": kept_features,
            "n_features": len(kept_features),
            "study": study,
            "per_class_accuracy": per_class_accuracy,
            "per_class_count": per_class_count,
            "log_loss": best_trial.user_attrs.get("log_loss"),
            "n_train_samples": best_trial.user_attrs.get("n_train_samples"),
            "n_val_samples": best_trial.user_attrs.get("n_val_samples"),
            "leakage_guard": str(best_trial.user_attrs.get("leakage_guard", "pass")),
        }


# ============================================================================
# 5M OPTIMIZER CLASS
# ============================================================================
class Optimizer5m:
    """
    5-minute timeframe optimizer.

    Wraps StepOptimizer5m with 5m-specific search spaces.
    """

    TIMEFRAME = "5m"

    def __init__(
        self,
        config: Config5m | None = None,
        window_space: WindowSpace5m | None = None,
        feature_space: FeatureSpace5m | None = None,
        model_space: ModelSpace5m | None = None,
    ):
        self.config = config or Config5m()
        self.window_space = window_space or WindowSpace5m()
        self.feature_space = feature_space or FeatureSpace5m()
        self.model_space = model_space or ModelSpace5m()

    def create_step_optimizer(self) -> StepOptimizer5m:
        """Create StepOptimizer5m with 5m search spaces."""
        return StepOptimizer5m(
            config=self.config,
            window_space=self.window_space,
            feature_space=self.feature_space,
            model_space=self.model_space,
        )

    def optimize_step(
        self,
        train_end: int,
        n_trials: int | None = None,
        timeout: int | None = None,
        study_storage_path: Path | None = None,
        study_name: str | None = None,
    ) -> dict:
        """
        Optimize for a single walk-forward step.

        Args:
            train_end: Last batch index to include in training
            n_trials: Override optuna trials (default: config.optuna_trials)
            timeout: Override optuna timeout (default: config.optuna_timeout)
            study_storage_path: Path to store SQLite study (optional)
            study_name: Custom study name (optional)

        Returns:
            dict with optimized params and metrics
        """
        optimizer = self.create_step_optimizer()
        return optimizer.optimize(
            train_end=train_end,
            n_trials=n_trials or self.config.optuna_trials,
            timeout=timeout or self.config.optuna_timeout,
            study_storage_path=study_storage_path,
            study_name=study_name,
        )

    def train_model(self, train_end: int, opt_result: dict):
        """Train model with optimized parameters."""
        X = None
        y = None
        train_start = opt_result.get("train_start_batch")
        train_end_batch = opt_result.get("train_end_batch")
        val_start = opt_result.get("val_start_batch")
        val_end = opt_result.get("val_end_batch")

        if all(v is not None for v in [train_start, train_end_batch, val_start, val_end]):
            range_start = int(min(train_start, val_start))
            range_end = int(max(train_end_batch, val_end))
            df = load_batches_range(
                self.config.features_dir,
                self.config.labels_dir,
                self.TIMEFRAME,
                range_start,
                range_end + 1,
                target_col=self.config.target,
                feature_target_col=(self.config.feature_target or self.config.target),
                exclude_tail_pct=self.config.exclude_tail_pct,
            )
            if int(df["batch_id"].max()) > int(train_end):
                raise ValueError("leakage guard failed: final train/val data exceeds train_end")
            df_train = df.filter(
                (pl.col("batch_id") >= int(train_start))
                & (pl.col("batch_id") <= int(train_end_batch))
            )
            df_val = df.filter(
                (pl.col("batch_id") >= int(val_start))
                & (pl.col("batch_id") <= int(val_end))
            )
            if len(df_train) == 0 or len(df_val) == 0:
                raise ValueError("empty deterministic train/val split for final training")
            X_train, y_train, _, _ = prepare_features_target(
                df_train, opt_result["selected_features"], self.config.target
            )
            X_val, y_val, _, _ = prepare_features_target(
                df_val, opt_result["selected_features"], self.config.target
            )
            X_train = np.nan_to_num(X_train, nan=0.0, posinf=0.0, neginf=0.0)
            X_val = np.nan_to_num(X_val, nan=0.0, posinf=0.0, neginf=0.0)
        else:
            lookback = opt_result["lookback_batches"]
            start = max(1, train_end - lookback + 1)
            df = load_batches_range(
                self.config.features_dir,
                self.config.labels_dir,
                self.TIMEFRAME,
                start,
                train_end + 1,
                target_col=self.config.target,
                feature_target_col=(self.config.feature_target or self.config.target),
                exclude_tail_pct=self.config.exclude_tail_pct,
            )
            if getattr(self.config, "shuffle_batches", False):
                rng = np.random.default_rng(self.config.shuffle_batches_seed)
                ordered = df["batch_id"].unique().to_list()
                rng.shuffle(ordered)
                df = pl.concat([df.filter(pl.col("batch_id") == bid) for bid in ordered])
            X, y, _, _ = prepare_features_target(
                df, opt_result["selected_features"], self.config.target
            )
            X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)

            effective_train_split = float(
                opt_result.get("train_val_split", self.config.train_val_split)
            )
            effective_val_ratio = float(opt_result.get("val_ratio", 1.0 - effective_train_split))
            if not (0.0 < effective_train_split < 1.0):
                effective_train_split = float(self.config.train_val_split)
            if not (0.0 < effective_val_ratio < 1.0):
                effective_val_ratio = float(1.0 - effective_train_split)
            if abs((effective_train_split + effective_val_ratio) - 1.0) > 0.05:
                effective_val_ratio = float(1.0 - effective_train_split)

            if getattr(self.config, "shuffle_split", False):
                val_ratio = (
                    self.config.shuffle_val_ratio
                    if self.config.shuffle_val_ratio is not None
                    else effective_val_ratio
                )
                train_idx, val_idx = stratified_split_indices(
                    y, val_ratio, seed=self.config.shuffle_seed
                )
                X_train, X_val = X[train_idx], X[val_idx]
                y_train, y_val = y[train_idx], y[val_idx]
            else:
                split_idx = int(len(X) * effective_train_split)
                split_idx = max(1, min(split_idx, len(X) - 1))
                X_train, X_val = X[:split_idx], X[split_idx:]
                y_train, y_val = y[:split_idx], y[split_idx:]

        train_counts = np.bincount(y_train, minlength=self.config.n_classes)
        val_counts = np.bincount(y_val, minlength=self.config.n_classes)
        window_mode = str(opt_result.get("window_selection_mode", ""))
        is_stage1_mode = window_mode.startswith("stage1_fold_cv")

        if is_stage1_mode:
            # Keep final fit consistent with Stage-1 objective constraints:
            # do not require full active-class coverage on short fold windows.
            if len(np.unique(y_train)) < 2:
                raise ValueError(
                    "stage1 final training requires at least 2 classes in train split"
                )
            if len(y_val) < 5:
                raise ValueError(
                    "stage1 final training requires at least 5 samples in val split"
                )
        else:
            required_classes = [
                int(c)
                for c in opt_result.get(
                    "active_class_ids", list(range(self.config.n_classes))
                )
                if 0 <= int(c) < self.config.n_classes
            ]
            if not required_classes:
                required_classes = list(range(self.config.n_classes))
            min_val_active = max(
                1, int(opt_result.get("min_val_samples_per_active_class", 1))
            )
            missing_train = [c for c in required_classes if int(train_counts[c]) <= 0]
            missing_val = [
                c for c in required_classes if int(val_counts[c]) < min_val_active
            ]

            # Final safety fallback: if shuffle split yields uncovered classes, retry
            # with chronological split before failing.
            if (len(missing_train) > 0 or len(missing_val) > 0) and getattr(
                self.config, "shuffle_split", False
            ) and X is not None:
                split_idx = int(len(X) * effective_train_split)
                split_idx = max(1, min(split_idx, len(X) - 1))
                X_train, X_val = X[:split_idx], X[split_idx:]
                y_train, y_val = y[:split_idx], y[split_idx:]
                train_counts = np.bincount(y_train, minlength=self.config.n_classes)
                val_counts = np.bincount(y_val, minlength=self.config.n_classes)
                missing_train = [
                    c for c in required_classes if int(train_counts[c]) <= 0
                ]
                missing_val = [
                    c for c in required_classes if int(val_counts[c]) < min_val_active
                ]

            if len(missing_train) > 0:
                raise ValueError(
                    "missing required class in train split for final training: "
                    f"{missing_train}"
                )
            if len(missing_val) > 0:
                raise ValueError(
                    "insufficient required class samples in val split for final training: "
                    f"{missing_val} (min={min_val_active})"
                )

        if getattr(self.config, "balance_strategy", "none") != "none":
            strategy = self.config.balance_strategy
            apply_to = self.config.balance_apply_to
            if apply_to in {"train", "train_val"}:
                idx = balanced_resample_indices(
                    y_train, strategy, seed=self.config.shuffle_seed
                )
                X_train, y_train = X_train[idx], y_train[idx]
            if apply_to == "train_val":
                idx = balanced_resample_indices(
                    y_val, strategy, seed=self.config.shuffle_seed + 1
                )
                X_val, y_val = X_val[idx], y_val[idx]

        decay_weights = apply_sample_weights(len(y_train), opt_result["decay_weight"])
        class_weights = compute_class_weights(
            y_train, opt_result["class_weight_method"]
        )

        if class_weights:
            class_sample_weights = weights_to_sample_weights(y_train, class_weights)
            sample_weights = decay_weights * class_sample_weights
        else:
            sample_weights = decay_weights

        try:
            model = CatBoostClassifier(
                **opt_result["cb_params"],
                iterations=opt_result["num_boost_round"],
            )
            model.fit(
                X_train,
                y_train,
                sample_weight=sample_weights,
                eval_set=(X_val, y_val),
                use_best_model=True,
                early_stopping_rounds=50,
                verbose=False,
            )
        except Exception as e:
            # Always try CPU fallback (handles missing GPU/CUDA runtime)
            params_cpu = opt_result["cb_params"].copy()
            params_cpu["task_type"] = "CPU"
            params_cpu.pop("devices", None)
            try:
                model = CatBoostClassifier(
                    **params_cpu,
                    iterations=opt_result["num_boost_round"],
                )
                model.fit(
                    X_train,
                    y_train,
                    sample_weight=sample_weights,
                    eval_set=(X_val, y_val),
                    use_best_model=True,
                    early_stopping_rounds=50,
                    verbose=False,
                )
            except Exception as e2:
                raise RuntimeError(f"train failed: {e}; cpu fallback failed: {e2}") from e2

        return model


# ============================================================================
# CONVENIENCE FUNCTION
# ============================================================================
def optimize_5m_step(train_end: int, n_trials: int = 30, timeout: int = 180) -> dict:
    """Quick function to optimize a single 5m step."""
    opt = Optimizer5m()
    return opt.optimize_step(train_end, n_trials, timeout)
