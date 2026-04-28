"""
5-Minute Timeframe Optimizer for HTF LightGBM Backtest
======================================================

Self-contained 5m optimization with:
- 5m-specific configuration
- 5m-specific search spaces
- Full optimization logic
"""

from dataclasses import dataclass
import hashlib
from pathlib import Path

import lightgbm as lgb
import numpy as np
import optuna
import polars as pl
from sklearn.metrics import balanced_accuracy_score, f1_score, log_loss

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
    3. Optimize model hyperparameters (LightGBM params)
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

    def load_available_batches(self, train_end: int) -> pl.DataFrame:
        """Load batches within lookback range up to train_end."""
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
            params = self.config.lgb_base_params.copy()
            params.update(
                {
                    "learning_rate": trial.suggest_float(
                        "lr",
                        self.model_space.learning_rate_min,
                        self.model_space.learning_rate_max,
                        log=True,
                    ),
                    "num_leaves": trial.suggest_int(
                        "num_leaves",
                        self.model_space.num_leaves_min,
                        self.model_space.num_leaves_max,
                    ),
                    "max_depth": trial.suggest_int(
                        "max_depth",
                        self.model_space.max_depth_min,
                        self.model_space.max_depth_max,
                    ),
                    "min_child_samples": trial.suggest_int(
                        "min_child_samples",
                        self.model_space.min_child_samples_min,
                        self.model_space.min_child_samples_max,
                    ),
                    "reg_lambda": trial.suggest_float(
                        "reg_lambda",
                        self.model_space.reg_lambda_min,
                        self.model_space.reg_lambda_max,
                        log=True,
                    ),
                    "reg_alpha": trial.suggest_float(
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
                    "colsample_bytree": trial.suggest_float(
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

            train_ds = lgb.Dataset(X_train, label=y_train, weight=sample_weights)
            val_ds = lgb.Dataset(X_val, label=y_val, reference=train_ds)

            try:
                model = lgb.train(
                    params,
                    train_ds,
                    num_boost_round=num_boost_round,
                    valid_sets=[val_ds],
                    callbacks=[
                        lgb.early_stopping(50, verbose=False),
                        lgb.log_evaluation(0),
                    ],
                )
            except Exception as e:
                # Always try CPU fallback (handles missing OpenCL/GPU)
                params_cpu = params.copy()
                params_cpu["device"] = "cpu"
                params_cpu.pop("gpu_platform_id", None)
                params_cpu.pop("gpu_device_id", None)
                try:
                    model = lgb.train(
                        params_cpu,
                        train_ds,
                        num_boost_round=num_boost_round,
                        valid_sets=[val_ds],
                        callbacks=[
                            lgb.early_stopping(50, verbose=False),
                            lgb.log_evaluation(0),
                        ],
                    )
                    trial.set_user_attr("cpu_fallback", True)
                except Exception as e2:
                    trial.set_user_attr(
                        "train_fail",
                        f"gpu_error={e}; cpu_error={e2}",
                    )
                    raise optuna.TrialPruned(f"train failed on CPU: {e2}")

            pred_raw = np.asarray(model.predict(X_val))
            if pred_raw.ndim == 1:
                pred_pos = np.clip(pred_raw, 1e-9, 1.0 - 1e-9)
                pred_proba = np.column_stack([1.0 - pred_pos, pred_pos])
                y_pred = (pred_pos >= 0.5).astype(int)
            else:
                pred_proba = pred_raw
                y_pred = pred_proba.argmax(axis=1)
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

        lgb_params = self.config.lgb_base_params.copy()
        lgb_params.update(
            {
                "learning_rate": best["lr"],
                "num_leaves": best["num_leaves"],
                "max_depth": best["max_depth"],
                "min_child_samples": best["min_child_samples"],
                "reg_lambda": best["reg_lambda"],
                "reg_alpha": best["reg_alpha"],
                "subsample": best["subsample"],
                "colsample_bytree": best["colsample_bytree"],
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
            "lgb_params": lgb_params,
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

    def train_model(self, train_end: int, opt_result: dict) -> lgb.Booster:
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
        required_classes = [
            int(c)
            for c in opt_result.get("active_class_ids", list(range(self.config.n_classes)))
            if 0 <= int(c) < self.config.n_classes
        ]
        if not required_classes:
            required_classes = list(range(self.config.n_classes))
        min_val_active = max(
            1, int(opt_result.get("min_val_samples_per_active_class", 1))
        )
        missing_train = [c for c in required_classes if int(train_counts[c]) <= 0]
        missing_val = [c for c in required_classes if int(val_counts[c]) < min_val_active]

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

        train_ds = lgb.Dataset(X_train, label=y_train, weight=sample_weights)
        val_ds = lgb.Dataset(X_val, label=y_val, reference=train_ds)

        try:
            model = lgb.train(
                opt_result["lgb_params"],
                train_ds,
                num_boost_round=opt_result["num_boost_round"],
                valid_sets=[val_ds],
                callbacks=[lgb.early_stopping(50, verbose=False), lgb.log_evaluation(0)],
            )
        except Exception as e:
            # Always try CPU fallback (handles missing OpenCL/GPU)
            params_cpu = opt_result["lgb_params"].copy()
            params_cpu["device"] = "cpu"
            params_cpu.pop("gpu_platform_id", None)
            params_cpu.pop("gpu_device_id", None)
            try:
                model = lgb.train(
                    params_cpu,
                    train_ds,
                    num_boost_round=opt_result["num_boost_round"],
                    valid_sets=[val_ds],
                    callbacks=[
                        lgb.early_stopping(50, verbose=False),
                        lgb.log_evaluation(0),
                    ],
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
