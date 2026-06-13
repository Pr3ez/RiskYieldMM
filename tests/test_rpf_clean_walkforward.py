from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import polars as pl
import pytest

import regression_feature_engineering.walkforward.optimize as optimize_module
from regression_feature_engineering.walkforward.classify import (
    TARGET_BINARY_DOWN_2X_UP,
    TARGET_BINARY_UP_2X_DOWN,
    binary_metrics,
    binary_target_expr,
    classification_objective,
    select_decision_threshold,
)
from regression_feature_engineering.walkforward.ablation import select_ablation_features
from regression_feature_engineering.walkforward.config import CleanWalkForwardConfig, merge_config
from regression_feature_engineering.walkforward.data import (
    build_batch_index,
    build_label_window_index,
    load_joined_batches,
    load_rpf_manifest,
    resolve_context,
)
from regression_feature_engineering.walkforward.metrics import objective_score, regression_metrics
from regression_feature_engineering.walkforward.model import CatBoostConfig, build_catboost_params
from regression_feature_engineering.walkforward.optimize import STAGES, run_optuna_stage, run_readiness, suggest_stage_config
from regression_feature_engineering.walkforward.panel_select import build_candidate_pool
from regression_feature_engineering.walkforward.policy import (
    ALL_MANIFEST_FEATURES,
    FROZEN_PANEL,
    TARGET_SPECIFIC_V2,
    FeaturePolicyConfig,
    select_features,
)
from regression_feature_engineering.walkforward.windows import build_windows, read_windows, write_windows


TARGET = "target_reg_direction_extreme_up_share_hvol_v2"


def _ts(batch: int, row: int) -> datetime:
    return datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(hours=batch * 8, minutes=row)


def _write_fixture(project: Path, *, batches: int = 5, rows: int = 4, label_overlap: bool = False) -> None:
    feature_root = project / "data/htf_multiasset/btcusdt/regression_path_features_v1/8h_b/1m"
    label_root = project / "data/htf_multiasset/btcusdt/htf_4class_labels_reg_distance_horizon_vol_v2/1m"
    feature_root.mkdir(parents=True)
    label_root.mkdir(parents=True)
    feature_cols = ("rpf_signal", "rpf_noise")
    (feature_root / "manifest.json").write_text(
        json.dumps(
            {
                "feature_set": "regression_path_features_v1",
                "root_id": "8h_b",
                "row_count": batches * rows,
                "feature_count": len(feature_cols),
                "feature_columns": list(feature_cols),
                "duplicate_count": 0,
                "null_feature_count": 0,
                "source_fingerprint": "fixture",
            }
        )
    )
    for batch in range(1, batches + 1):
        timestamps = [_ts(batch, row) for row in range(rows)]
        signal = [batch * 0.1 + row * 0.01 for row in range(rows)]
        target = [min(max(value, 0.0), 1.0) for value in signal]
        pl.DataFrame(
            {
                "timestamp": timestamps,
                "batch_id": [batch] * rows,
                "asset_id": ["BTCUSDT"] * rows,
                "root_id": ["8h_b"] * rows,
                "feature_set": ["regression_path_features_v1"] * rows,
                "rpf_align_15m_has_closed_bar": [True] * rows,
                "rpf_signal": signal,
                "rpf_noise": [float(row % 2) for row in range(rows)],
            }
        ).write_parquet(feature_root / f"batch_{batch:04d}.parquet")
        pl.DataFrame(
            {
                "timestamp": timestamps,
                "batch_id": [batch] * rows,
                "target_reg_distance_valid_v2": [True] * rows,
                TARGET: target,
                "label_window_start": [_ts(batch, rows)] * rows,
                "label_window_end": [_ts(batch + 1 if label_overlap else batch, rows)] * rows,
                "label_window_batch_id": [batch + 1 if label_overlap else batch] * rows,
                "target_reg_distance_horizon_minutes_v2": [240.0] * rows,
            }
        ).write_parquet(label_root / f"batch_{batch:04d}.parquet")


def test_manifest_loader_uses_feature_columns_and_excludes_diagnostics(tmp_path: Path) -> None:
    _write_fixture(tmp_path)
    manifest = load_rpf_manifest(
        tmp_path / "data/htf_multiasset/btcusdt/regression_path_features_v1/8h_b/1m/manifest.json"
    )

    assert manifest.feature_columns == ("rpf_signal", "rpf_noise")
    assert not any(col.startswith("rpf_align_") for col in manifest.feature_columns)


def test_feature_label_join_is_exact_on_timestamp_batch(tmp_path: Path) -> None:
    _write_fixture(tmp_path)
    context = resolve_context(project_root=tmp_path, asset="BTCUSDT", root="8h/B", target_col=TARGET)
    joined = load_joined_batches(context, [1])

    assert joined.height == 4
    assert {"timestamp", "batch_id", TARGET, "rpf_signal", "rpf_noise"}.issubset(joined.columns)


def test_sparse_windows_use_available_positions_not_numeric_continuity(tmp_path: Path) -> None:
    index = pl.DataFrame(
        {
            "rpf_available_pos": [0, 1, 2],
            "batch_id": [10, 11, 20],
            "batch_start_ts": [_ts(1, 0), _ts(2, 0), _ts(3, 0)],
            "batch_end_ts": [_ts(1, 1), _ts(2, 1), _ts(3, 1)],
            "valid_row_count": [4, 4, 4],
        }
    )

    windows = build_windows(index, lookback_batches=1, val_batches=1, n_steps=1)

    assert windows[0].pred_batch_id == 20
    assert windows[0].train_batch_ids == (10,)
    assert windows[0].val_batch_ids == (11,)


def test_batch_index_ignores_extra_feature_columns(tmp_path: Path) -> None:
    _write_fixture(tmp_path)
    path = tmp_path / "data/htf_multiasset/btcusdt/regression_path_features_v1/8h_b/1m/batch_0002.parquet"
    frame = pl.read_parquet(path).with_columns(pl.lit(1.0).alias("unexpected_extra_feature"))
    frame.write_parquet(path)
    context = resolve_context(project_root=tmp_path, asset="BTCUSDT", root="8h/B", target_col=TARGET)

    index = build_batch_index(context)

    assert index.height == 5
    assert index["batch_id"].to_list() == [1, 2, 3, 4, 5]


def test_frozen_windows_roundtrip(tmp_path: Path) -> None:
    _write_fixture(tmp_path)
    context = resolve_context(project_root=tmp_path, asset="BTCUSDT", root="8h/B", target_col=TARGET)
    windows = build_windows(build_batch_index(context), lookback_batches=2, val_batches=1, n_steps=1)
    path = write_windows(tmp_path / "frozen_windows.parquet", windows)

    assert read_windows(path) == windows
    frame = pl.read_parquet(path)
    assert {"train_start_ts", "val_start_ts", "pred_start_ts", "train_valid_row_count"}.issubset(frame.columns)


def test_feature_selection_uses_train_signal_only() -> None:
    frame = pl.DataFrame(
        {
            TARGET: [0.1, 0.2, 0.3, 0.4, 0.5],
            "rpf_signal": [0.1, 0.2, 0.3, 0.4, 0.5],
            "rpf_noise": [1.0, 0.0, 1.0, 0.0, 1.0],
        }
    )

    result = select_features(
        frame,
        target_col=TARGET,
        feature_columns=("rpf_signal", "rpf_noise"),
        config=FeaturePolicyConfig(
            policy=TARGET_SPECIFIC_V2,
            max_features=1,
            min_selected_features=1,
            min_abs_spearman=0.01,
        ),
    )

    assert result.selected_features == ("rpf_signal",)
    assert result.clip_bounds["rpf_signal"][0] <= 0.1


def test_all_manifest_policy_uses_every_feature_without_clip_bounds() -> None:
    frame = pl.DataFrame(
        {
            TARGET: [0.1, 0.2, 0.3],
            "rpf_signal": [1.0, 2.0, 3.0],
            "rpf_noise": [3.0, 2.0, 1.0],
        }
    )

    result = select_features(
        frame,
        target_col=TARGET,
        feature_columns=("rpf_signal", "rpf_noise"),
        config=FeaturePolicyConfig(policy=ALL_MANIFEST_FEATURES),
    )

    assert result.selected_features == ("rpf_signal", "rpf_noise")
    assert result.clip_bounds == {}
    assert result.detail["final_status"].to_list() == ["selected_all_manifest", "selected_all_manifest"]


def test_frozen_panel_policy_uses_panel_features_only(tmp_path: Path) -> None:
    panel_path = tmp_path / "selected_panel.json"
    panel_path.write_text(json.dumps({"selected_features": ["rpf_signal"]}))
    frame = pl.DataFrame(
        {
            TARGET: [0.1, 0.2, 0.3],
            "rpf_signal": [1.0, 2.0, 3.0],
            "rpf_noise": [3.0, 2.0, 1.0],
        }
    )

    result = select_features(
        frame,
        target_col=TARGET,
        feature_columns=("rpf_signal", "rpf_noise"),
        config=FeaturePolicyConfig(policy=FROZEN_PANEL, frozen_panel_path=str(panel_path)),
    )

    assert result.selected_features == ("rpf_signal",)
    assert result.clip_bounds == {}
    assert result.detail.filter(pl.col("feature") == "rpf_noise")["drop_reason"].item() == "not_in_frozen_panel"


def test_panel_candidate_pool_uses_existing_diagnostic_scores(tmp_path: Path) -> None:
    report_root = tmp_path / "test_output/regression_feature_engineering_btcusdt_8h_b_screen"
    report_dir = report_root / "family_btcusdt_8h_b"
    report_dir.mkdir(parents=True)
    pl.DataFrame(
        {
            "feature": ["rpf_room_a", "rpf_room_b", "rpf_vol_a"],
            "target": ["target_extreme_up_minus_down"] * 3,
            "pearson": [0.10, 0.01, 0.03],
            "spearman": [0.20, 0.01, -0.06],
            "abs_spearman": [0.20, 0.01, 0.06],
            "rows": [100, 100, 100],
        }
    ).write_parquet(report_dir / "feature_target_correlations.parquet")
    pl.DataFrame(
        {
            "feature": ["rpf_room_a", "rpf_vol_a"],
            "target": ["target_extreme_up_minus_down", "target_extreme_up_minus_down"],
            "q20": [0.0, 0.0],
            "q80": [1.0, 1.0],
            "low_mean": [0.1, 0.2],
            "high_mean": [0.4, 0.5],
            "high_minus_low": [0.3, 0.3],
            "low_rows": [20, 20],
            "high_rows": [20, 20],
        }
    ).write_parquet(report_dir / "feature_bin_spreads.parquet")

    candidates, _ = build_candidate_pool(
        diagnostics_root=tmp_path / "test_output",
        asset="BTCUSDT",
        root_id="8h_b",
        manifest_features=("rpf_room_a", "rpf_room_b", "rpf_vol_a"),
        candidate_targets=("target_extreme_up_minus_down",),
        candidate_limit=10,
        per_family_limit=10,
        min_abs_spearman=0.02,
        min_bin_spread_abs=0.0,
    )

    assert candidates["feature"].to_list() == ["rpf_room_a", "rpf_vol_a"]


def test_constant_prediction_reports_null_reason() -> None:
    metrics = regression_metrics(np.array([0.1, 0.2, 0.3]), np.array([0.2, 0.2, 0.2]))

    assert metrics["spearman"] is None
    assert metrics["spearman_null_reason"] == "constant_prediction"


def test_binary_up_2x_down_target_rule() -> None:
    frame = pl.DataFrame(
        {
            "target_reg_distance_up_extreme_hvol_v2": [0.0, 1.0, 2.0, 3.0, 1.0],
            "target_reg_distance_down_extreme_hvol_v2": [0.0, 0.0, 1.1, 1.0, 3.0],
        }
    ).with_columns(
        binary_target_expr(TARGET_BINARY_UP_2X_DOWN),
        binary_target_expr(TARGET_BINARY_DOWN_2X_UP),
    )

    assert frame[TARGET_BINARY_UP_2X_DOWN].to_list() == [0, 1, 0, 1, 0]
    assert frame[TARGET_BINARY_DOWN_2X_UP].to_list() == [0, 0, 0, 0, 1]


def test_binary_classification_metrics_are_computed() -> None:
    metrics = binary_metrics(np.array([0, 0, 1, 1]), np.array([0.1, 0.4, 0.7, 0.9]))

    assert metrics["accuracy"] == 1.0
    assert metrics["balanced_accuracy"] == 1.0
    assert metrics["auc"] == 1.0
    assert metrics["logloss"] < 0.4


def test_binary_metrics_include_cost_and_threshold() -> None:
    metrics = binary_metrics(
        np.array([0, 0, 1, 1]),
        np.array([0.2, 0.8, 0.4, 0.9]),
        threshold=0.5,
        fp_cost=5.0,
        fn_cost=1.0,
    )

    assert metrics["tp"] == 1
    assert metrics["fp"] == 1
    assert metrics["fn"] == 1
    assert metrics["false_positive_rate"] == pytest.approx(0.5)
    assert metrics["false_negative_rate"] == pytest.approx(0.5)
    assert metrics["decision_cost"] == pytest.approx(6.0)
    assert metrics["decision_cost_per_row"] == pytest.approx(1.5)


def test_validation_threshold_sweep_selects_low_cost_threshold() -> None:
    result = select_decision_threshold(
        np.array([0, 0, 1, 1]),
        np.array([0.2, 0.8, 0.4, 0.9]),
        threshold_mode="validation_sweep",
        fixed_threshold=0.5,
        threshold_grid=(0.3, 0.5, 0.85),
        objective_metric="validation_decision_cost",
        fp_cost=5.0,
        fn_cost=1.0,
        tp_reward=0.0,
        fbeta_beta=0.5,
        min_recall=0.0,
        min_precision=0.0,
        min_predicted_positive_rate=0.0,
        max_false_positive_rate=1.0,
    )

    assert result["threshold"] == pytest.approx(0.85)
    assert result["metrics"]["fp"] == 0
    assert result["metrics"]["fn"] == 1
    assert result["metrics"]["decision_cost"] == pytest.approx(1.0)


def test_classification_objective_supports_minimize_and_maximize() -> None:
    metrics = {"logloss": 0.4, "decision_cost_per_row": 0.2, "precision": 0.8}

    assert classification_objective(metrics, "validation_logloss") == ("minimize", 0.4)
    assert classification_objective(metrics, "validation_decision_cost") == ("minimize", 0.2)
    assert classification_objective(metrics, "validation_precision") == ("maximize", 0.8)


def test_optuna_objective_prefers_lower_validation_rmse() -> None:
    better = objective_score({"rmse": 0.10, "spearman": -0.5})
    worse = objective_score({"rmse": 0.20, "spearman": 0.9})

    assert better < worse
    assert objective_score({"rmse": None}) == 1e9


def test_baseline_rmse_formula_matches_direct_numpy() -> None:
    y = np.array([0.0, 0.5, 1.0])

    expected = float(np.sqrt(np.mean((y - 0.5) ** 2)))

    assert optimize_module._rmse_against_constant(y, 0.5) == pytest.approx(expected)
    assert optimize_module._rmse_against_constant(y, None) is None


def test_window_collapse_summary_and_gate() -> None:
    rows = [
        {
            "prediction_window_collapsed": True,
            "prediction_pred_unique": 1,
            "prediction_pred_std": 0.0,
            "prediction_to_target_std_ratio_window": 0.0,
        },
        {
            "prediction_window_collapsed": False,
            "prediction_pred_unique": 20,
            "prediction_pred_std": 0.2,
            "prediction_to_target_std_ratio_window": 0.5,
        },
    ]

    summary = optimize_module._aggregate_collapse_metrics(
        rows,
        {"pred_std": 0.05, "target_std": 1.0, "pred_mean": 0.4, "target_mean": 0.6},
    )

    assert summary["collapsed_window_count"] == 1
    assert summary["collapsed_window_rate"] == 0.5
    assert summary["prediction_pred_unique_min"] == 1
    assert summary["prediction_mean_bias"] == pytest.approx(-0.2)
    assert (
        optimize_module.window_collapse_reason(
            summary,
            max_collapsed_window_rate=0.25,
            min_prediction_to_target_std_ratio=0.10,
        )
        == "high_collapsed_window_rate"
    )


def test_feature_family_ablation_masks_manifest_features() -> None:
    features = ("rpf_vol_a", "rpf_room_a", "rpf_accept_a")

    assert select_ablation_features(features, "all") == features
    assert select_ablation_features(features, "only_volatility_state") == ("rpf_vol_a",)
    assert select_ablation_features(features, "group_volatility_state+structural_room") == ("rpf_vol_a", "rpf_room_a")
    assert select_ablation_features(features, "minus_volatility_state") == ("rpf_room_a", "rpf_accept_a")


def test_catboost_param_builder_rejects_invalid_sampling_combo() -> None:
    with pytest.raises(ValueError, match="bagging_temperature"):
        build_catboost_params(
            CatBoostConfig(bootstrap_type="Bernoulli", bagging_temperature=1.0),
            task_type="CPU",
        )


def test_stage_config_keeps_locked_window_for_core_model() -> None:
    optuna = pytest.importorskip("optuna")
    base = CleanWalkForwardConfig(lookback_batches=222, val_batches=11)
    trial = optuna.trial.FixedTrial(
        {
            "iterations": 100,
            "depth": 3,
            "learning_rate": 0.03,
            "l2_leaf_reg": 10.0,
            "early_stopping_rounds": 20,
            "od_wait": 20,
        }
    )
    args = SimpleNamespace(
        iterations_choices="100",
        depth_choices="3",
        learning_rate_choices="0.03",
        l2_leaf_reg_choices="10",
        early_stopping_rounds_choices="20",
        od_wait_choices="20",
    )

    out = suggest_stage_config(trial, "core_model", base, args)

    assert out.lookback_batches == 222
    assert out.val_batches == 11
    assert out.model.iterations == 100


def test_finite_categorical_stages_use_grid_sampler() -> None:
    optuna = pytest.importorskip("optuna")
    args = SimpleNamespace(
        seed=42,
        lookback_choices="80,120",
        val_choices="8,10",
        embargo_choices="0",
        iterations_choices="400",
        depth_choices="4",
        learning_rate_choices="0.01",
        l2_leaf_reg_choices="100",
        early_stopping_rounds_choices="100",
        od_wait_choices="100",
    )

    assert type(optimize_module._sampler_for_stage(optuna, "geometry", args)).__name__ == "GridSampler"
    assert type(optimize_module._sampler_for_stage(optuna, "baseline_probe", args)).__name__ == "GridSampler"
    assert type(optimize_module._sampler_for_stage(optuna, "core_model", args)).__name__ == "GridSampler"
    assert type(optimize_module._sampler_for_stage(optuna, "confirmation", args)).__name__ == "TPESampler"


def test_trial_config_columns_are_flat_for_audit() -> None:
    config = merge_config(
        CleanWalkForwardConfig(),
        lookback_batches=180,
        val_batches=12,
        feature_ablation="all",
        model={"iterations": 800, "depth": 4, "learning_rate": 0.01, "l2_leaf_reg": 200},
    )

    row = optimize_module._trial_config_columns(config)

    assert row["feature_count_mode"] == "all"
    assert row["max_collapsed_window_rate"] == 0.25
    assert row["min_prediction_to_target_std_ratio"] == 0.10
    assert row["lookback_batches"] == 180
    assert row["val_batches"] == 12
    assert row["iterations"] == 800
    assert row["learning_rate"] == 0.01
    assert row["l2_leaf_reg"] == 200.0


def test_clean_rpf_stages_do_not_tune_feature_policy() -> None:
    assert "feature_policy" not in STAGES
    assert "geometry" in STAGES
    assert "core_model" in STAGES
    assert "sampling" in STAGES


def test_stale_base_run_feature_policy_is_overridden_by_current_config() -> None:
    stale = merge_config(
        CleanWalkForwardConfig(),
        lookback_batches=222,
        feature_policy=TARGET_SPECIFIC_V2,
        policy={"policy": TARGET_SPECIFIC_V2, "max_features": 300},
        model={"depth": 5},
    )
    current = merge_config(
        CleanWalkForwardConfig(),
        feature_policy=ALL_MANIFEST_FEATURES,
        policy={"policy": ALL_MANIFEST_FEATURES, "max_features": 0},
    )

    out = optimize_module._apply_current_fixed_contract(stale, current)

    assert out.feature_policy == ALL_MANIFEST_FEATURES
    assert out.policy.policy == ALL_MANIFEST_FEATURES
    assert out.policy.max_features == 0
    assert out.lookback_batches == 222
    assert out.model.depth == 5


def test_readiness_stage_writes_expected_artifacts(tmp_path: Path) -> None:
    _write_fixture(tmp_path)
    context = resolve_context(project_root=tmp_path, asset="BTCUSDT", root="8h/B", target_col=TARGET)
    config = merge_config(CleanWalkForwardConfig(), policy={"min_selected_features": 1})
    run_root = tmp_path / "out"
    args = SimpleNamespace(lookback_batches=2, val_batches=1, embargo_batches=0, n_steps=1)

    run_readiness(context, config, run_root, run_root / "events.jsonl", args)

    assert (run_root / "readiness.json").exists()
    assert (run_root / "frozen_windows.parquet").exists()
    assert (run_root / "stage_status.json").exists()
    assert (run_root / "trials.parquet").exists()
    assert (run_root / "best_config.json").exists()
    assert (run_root / "label_window_index.parquet").exists()
    assert (run_root / "window_metrics.parquet").exists()
    readiness = json.loads((run_root / "readiness.json").read_text())
    assert readiness["feature_integrity"]["family_counts"]["unmapped"] == 2
    assert "zero_rate" in readiness["target_summary"]
    window_metrics = pl.read_parquet(run_root / "window_metrics.parquet")
    assert "target_mean_drift_pred_minus_train" in window_metrics.columns


def test_readiness_detects_label_window_overlap(tmp_path: Path) -> None:
    _write_fixture(tmp_path, batches=5, rows=4, label_overlap=True)
    context = resolve_context(project_root=tmp_path, asset="BTCUSDT", root="8h/B", target_col=TARGET)
    config = merge_config(CleanWalkForwardConfig(), policy={"min_selected_features": 1})
    args = SimpleNamespace(lookback_batches=2, val_batches=1, embargo_batches=0, n_steps=1)

    with pytest.raises(ValueError, match="label-window safety failed"):
        run_readiness(context, config, tmp_path / "out", tmp_path / "out" / "events.jsonl", args)


def test_label_window_safety_passes_self_contained_windows(tmp_path: Path) -> None:
    _write_fixture(tmp_path, batches=5, rows=4)
    context = resolve_context(project_root=tmp_path, asset="BTCUSDT", root="8h/B", target_col=TARGET)
    windows = build_windows(build_batch_index(context), lookback_batches=2, val_batches=1, n_steps=1)
    summary, rows = optimize_module._label_window_safety(windows, build_label_window_index(context), embargo_batches=0)

    assert summary["status"] == "pass"
    assert summary["violation_count"] == 0
    assert rows[0]["label_window_violation"] is False


def test_baseline_probe_stage_writes_artifacts_without_stage1_merged_root(tmp_path: Path) -> None:
    pytest.importorskip("optuna")
    pytest.importorskip("catboost")
    _write_fixture(tmp_path, batches=5, rows=4)
    context = resolve_context(project_root=tmp_path, asset="BTCUSDT", root="8h/B", target_col=TARGET)
    config = merge_config(
        CleanWalkForwardConfig(min_prediction_unique=0),
        lookback_batches=2,
        val_batches=1,
        n_steps=1,
        policy={"policy": TARGET_SPECIFIC_V2, "max_features": 1, "min_selected_features": 1, "min_abs_spearman": 0.01},
        model={"iterations": 5, "depth": 2, "early_stopping_rounds": 2, "od_wait": 2},
    )
    base_run = tmp_path / "readiness"
    args_ready = SimpleNamespace(lookback_batches=2, val_batches=1, embargo_batches=0, n_steps=1)
    run_readiness(context, config, base_run, base_run / "events.jsonl", args_ready)
    args = SimpleNamespace(
        stage="baseline_probe",
        base_run=base_run,
        n_steps=1,
        n_trials=1,
        timeout=None,
        seed=42,
        task_type="CPU",
        thread_count=-1,
        iterations_choices="5",
        depth_choices="2",
        learning_rate_choices="0.03",
        l2_leaf_reg_choices="10",
        early_stopping_rounds_choices="2",
        od_wait_choices="2",
    )
    run_root = tmp_path / "baseline"

    run_optuna_stage(context, config, run_root, run_root / "events.jsonl", args)

    assert (run_root / "frozen_windows.parquet").exists()
    assert (run_root / "trials.parquet").exists()
    assert (run_root / "best_config.json").exists()
    assert (run_root / "stage_status.json").exists()
    assert (run_root / "window_metrics.parquet").exists()
    trials = pl.read_parquet(run_root / "trials.parquet")
    assert trials["objective_metric"].to_list() == ["validation_rmse"]
    assert trials["objective_direction"].to_list() == ["minimize"]
    for col in (
        "validation_baseline_train_target_mean_rmse",
        "prediction_baseline_train_target_mean_rmse",
        "collapsed_window_rate",
        "prediction_pred_unique_min",
        "ablation_feature_count",
    ):
        assert col in trials.columns
    windows = pl.read_parquet(run_root / "window_metrics.parquet")
    assert "prediction_baseline_constant_0p5_rmse" in windows.columns
    assert "prediction_window_collapsed" in windows.columns


def test_non_geometry_stage_reuses_frozen_windows_without_batch_index_scan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pytest.importorskip("optuna")
    _write_fixture(tmp_path, batches=5, rows=4)
    context = resolve_context(project_root=tmp_path, asset="BTCUSDT", root="8h/B", target_col=TARGET)
    config = merge_config(CleanWalkForwardConfig(min_prediction_unique=0), lookback_batches=2, val_batches=1, n_steps=1)
    base_run = tmp_path / "readiness"
    args_ready = SimpleNamespace(lookback_batches=2, val_batches=1, embargo_batches=0, n_steps=1)
    run_readiness(context, config, base_run, base_run / "events.jsonl", args_ready)

    def explode_batch_index(*_args: object, **_kwargs: object) -> pl.DataFrame:
        raise AssertionError("non-geometry stages must not rebuild batch index")

    def fake_run_windows(*_args: object, **_kwargs: object) -> dict[str, object]:
        return {
            "validation_metrics": {
                "rows": 4,
                "spearman": 0.1,
                "pearson": 0.1,
                "r2": 0.0,
                "rmse": 0.2,
                "balanced_direction_accuracy_0p5": 0.5,
            },
            "prediction_metrics": {
                "rows": 4,
                "pred_unique": 11,
                "pred_std": 0.2,
                "spearman_null_reason": None,
            },
            "baseline_metrics": {
                "validation_baseline_train_target_mean_rmse": 0.2,
                "prediction_baseline_train_target_mean_rmse": 0.2,
            },
            "collapse_metrics": {
                "collapsed_window_rate": 0.0,
                "prediction_to_target_std_ratio": 0.5,
                "prediction_pred_unique_min": 11,
            },
            "selected_feature_count_min": 20,
            "window_metrics": [{"step_idx": 0, "prediction_rmse": 0.2}],
        }

    monkeypatch.setattr(optimize_module, "build_batch_index", explode_batch_index)
    monkeypatch.setattr(optimize_module, "run_windows", fake_run_windows)
    args = SimpleNamespace(
        stage="baseline_probe",
        base_run=base_run,
        n_steps=1,
        n_trials=1,
        timeout=None,
        seed=42,
        task_type="CPU",
        thread_count=-1,
        iterations_choices="5",
        depth_choices="2",
        learning_rate_choices="0.03",
        l2_leaf_reg_choices="10",
        early_stopping_rounds_choices="2",
        od_wait_choices="2",
    )

    run_optuna_stage(context, config, tmp_path / "baseline", tmp_path / "baseline" / "events.jsonl", args)

    assert (tmp_path / "baseline" / "trials.parquet").exists()
    assert (tmp_path / "baseline" / "window_metrics.parquet").exists()
