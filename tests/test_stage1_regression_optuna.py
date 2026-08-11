from __future__ import annotations

from types import SimpleNamespace

import pytest

optuna = pytest.importorskip("optuna")

from scripts.analysis.htf_stage1_regression_optuna import (  # noqa: E402
    STAGE_CORE_MODEL,
    STAGE_FEATURE_POLICY,
    STAGE_GEOMETRY,
    default_effective_config,
    suggest_trial_config,
    _trial_suffix,
    _trial_step_callback,
    validation_objective_score,
)
from scripts.analysis.htf_stage1_regression_walkforward import (  # noqa: E402
    FEATURE_SOURCE_HTF_PLUS_REGRESSION,
    FEATURE_SOURCE_REGRESSION_ONLY,
    CatBoostModelConfig,
    build_catboost_params,
)


def _args(**overrides):
    values = {
        "feature_source_modes": "htf_only,regression_only,htf_plus_regression",
        "optimization_stage": STAGE_FEATURE_POLICY,
        "lookback_choices": "80,120",
        "val_choices": "10,20,200",
        "embargo_choices": "0",
        "max_features_choices": "100,300",
        "min_abs_spearman_choices": "0.02,0.05",
        "min_selected_features_choices": "20",
        "dedupe_corr_choices": "0.98,0.995",
        "clip_quantiles_choices": "0.001,0.999",
        "stability_segments_choices": "5",
        "tail_quantile_choices": "0.8",
        "iterations_choices": "100,200",
        "depth_choices": "4,6",
        "learning_rate_choices": "0.03,0.05",
        "l2_leaf_reg_choices": "3,10",
        "early_stopping_rounds_choices": "50",
        "od_wait_choices": "50",
        "random_strength_choices": "1,5",
        "bootstrap_type_choices": "None,Bayesian,Bernoulli",
        "bagging_temperature_choices": "0.5,1.0",
        "subsample_choices": "0.8,0.9",
        "mvs_reg_choices": "0.1,1.0",
        "border_count_choices": "64,128",
        "grow_policy_choices": "None,Depthwise,Lossguide",
        "min_data_in_leaf_choices": "20,50",
        "max_leaves_choices": "31,63",
        "leaf_estimation_method_choices": "Newton,Gradient",
        "leaf_estimation_iterations_choices": "1,3",
        "task_type": "GPU",
        "objective_metric": "validation_composite",
        "weight_spearman": 1.0,
        "weight_pearson": 0.15,
        "weight_r2": 0.20,
        "weight_rmse": 0.25,
        "weight_mae": 0.0,
        "weight_tail_rmse": 0.10,
        "weight_p95_coverage": 0.20,
        "weight_bias": 0.05,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_optuna_trial_config_keeps_validation_window_before_prediction() -> None:
    trial = optuna.trial.FixedTrial(
        {
            "lookback_batches": 80,
            "val_batches": 20,
            "embargo_batches": 0,
        }
    )

    config = suggest_trial_config(trial, _args(optimization_stage=STAGE_GEOMETRY))

    assert config["window"]["lookback_batches"] == 80
    assert config["window"]["val_batches"] < config["window"]["lookback_batches"]
    assert config["feature"]["feature_source_mode"] == FEATURE_SOURCE_REGRESSION_ONLY


def test_optuna_trial_suffix_stays_short_for_long_direction_share_target() -> None:
    config = default_effective_config()
    suffix = _trial_suffix(
        STAGE_GEOMETRY,
        "btcusdt_8h_b_reg_direction_extreme_up_share_hvol_v2",
        0,
        config,
    )

    assert len(suffix) < 140
    assert suffix.startswith("opt_geo_")
    assert "_t0000_" in suffix
    assert "_lb120_val20_" in suffix


def test_optuna_trial_config_prunes_when_no_valid_validation_width() -> None:
    trial = optuna.trial.FixedTrial({"lookback_batches": 10})

    with pytest.raises(optuna.TrialPruned):
        suggest_trial_config(
            trial,
            _args(optimization_stage=STAGE_GEOMETRY, lookback_choices="10", val_choices="10,20"),
        )


def test_feature_policy_stage_keeps_locked_window_and_model() -> None:
    trial = optuna.trial.FixedTrial(
        {
            "feature_source_mode": FEATURE_SOURCE_HTF_PLUS_REGRESSION,
            "max_features": 100,
            "min_abs_spearman": 0.02,
            "min_selected_features": 20,
            "dedupe_corr_threshold": 0.98,
            "clip_quantiles": "0.001,0.999",
            "stability_segments": 5,
            "tail_quantile": 0.8,
        }
    )
    base = default_effective_config()
    base["window"]["lookback_batches"] = 180
    base["model"]["depth"] = 4

    config = suggest_trial_config(trial, _args(optimization_stage=STAGE_FEATURE_POLICY), base)

    assert config["window"]["lookback_batches"] == 180
    assert config["model"]["depth"] == 4
    assert config["feature"]["feature_source_mode"] == FEATURE_SOURCE_HTF_PLUS_REGRESSION


def test_core_model_stage_keeps_locked_feature_source() -> None:
    trial = optuna.trial.FixedTrial(
        {
            "iterations": 100,
            "depth": 4,
            "learning_rate": 0.03,
            "l2_leaf_reg": 3.0,
            "early_stopping_rounds": 50,
            "od_wait": 50,
        }
    )
    base = default_effective_config()
    base["feature"]["feature_source_mode"] = FEATURE_SOURCE_HTF_PLUS_REGRESSION

    config = suggest_trial_config(trial, _args(optimization_stage=STAGE_CORE_MODEL), base)

    assert config["feature"]["feature_source_mode"] == FEATURE_SOURCE_HTF_PLUS_REGRESSION
    assert config["model"]["iterations"] == 100
    assert config["model"]["l2_leaf_reg"] == 3.0


def test_validation_objective_prefers_rank_and_tail_coverage() -> None:
    args = _args()
    good = {
        "spearman": 0.30,
        "pearson": 0.25,
        "r2": 0.10,
        "rmse": 0.70,
        "mae": 0.45,
        "tail_rmse": 0.90,
        "p95_coverage_ratio": 0.95,
        "bias": 0.05,
    }
    poor_tail = {**good, "spearman": 0.20, "p95_coverage_ratio": 0.20, "tail_rmse": 1.40}

    assert validation_objective_score(good, args) > validation_objective_score(poor_tail, args)


def test_validation_objective_can_use_simple_metric_modes() -> None:
    metrics = {"spearman": 0.25, "rmse": 0.7}

    assert validation_objective_score(metrics, _args(objective_metric="validation_spearman")) == 0.25
    assert validation_objective_score(metrics, _args(objective_metric="validation_rmse_negative")) == -0.7


def test_catboost_param_builder_rejects_invalid_conditionals() -> None:
    with pytest.raises(ValueError, match="bagging_temperature"):
        build_catboost_params(
            CatBoostModelConfig(bootstrap_type="Bernoulli", bagging_temperature=1.0),
            task_type="GPU",
            thread_count=-1,
        )


def test_catboost_param_builder_records_time_order_by_default() -> None:
    params = build_catboost_params(
        CatBoostModelConfig(bootstrap_type="Bayesian", bagging_temperature=0.5),
        task_type="GPU",
        thread_count=-1,
    )

    assert params["has_time"] is True
    assert params["bootstrap_type"] == "Bayesian"
    assert params["bagging_temperature"] == 0.5


def test_pruner_callback_reports_validation_only_score() -> None:
    class FakeTrial:
        def __init__(self) -> None:
            self.reports = []

        def report(self, score, step):
            self.reports.append((score, step))

        def should_prune(self):
            return False

    trial = FakeTrial()
    callback = _trial_step_callback(trial, _args(pruner="median"))
    assert callback is not None

    callback(3, {"spearman": 0.2, "rmse": 0.7, "p95_coverage_ratio": 1.0}, None)

    assert trial.reports
    assert trial.reports[0][1] == 3
