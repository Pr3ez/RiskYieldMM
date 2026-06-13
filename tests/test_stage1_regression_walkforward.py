from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import polars as pl
import pytest

from scripts.analysis.htf_stage1_regression_grid_search import iter_grid
from scripts.analysis.htf_stage1_regression_walkforward import (
    FEATURE_POLICY_TARGET_SPECIFIC_V1,
    FEATURE_POLICY_TARGET_SPECIFIC_V2,
    FEATURE_SOURCE_HTF_ONLY,
    FEATURE_SOURCE_HTF_PLUS_REGRESSION,
    FEATURE_SOURCE_REGRESSION_ONLY,
    FeaturePolicyConfig,
    FeatureSourceConfig,
    RegressionStep,
    RegressionDataset,
    build_regression_run_id,
    build_catboost_params,
    CatBoostModelConfig,
    load_regression_steps_from_index,
    load_regression_feature_frame,
    plan_regression_steps,
    prepare_regression_frame,
    regression_steps_to_frame,
    regression_metrics,
    select_target_specific_features,
)


def _timestamps(rows: int) -> list[datetime]:
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    return [start + timedelta(minutes=i) for i in range(rows)]


def test_sparse_regression_steps_use_dense_available_positions() -> None:
    batch_index = pl.DataFrame(
        {
            "stage1_available_pos": [0, 1, 2, 3],
            "batch_id": [10, 11, 20, 30],
            "valid_row_count": [5, 5, 5, 5],
        }
    )

    steps = plan_regression_steps(
        batch_index,
        n_steps=1,
        lookback_batches=2,
        val_batches=1,
        embargo_batches=0,
    )

    assert len(steps) == 1
    assert steps[0].pred_batch_id == 30
    assert steps[0].train_batch_ids == (10, 11)
    assert steps[0].val_batch_ids == (20,)


def test_regression_steps_apply_embargo_by_available_position() -> None:
    batch_index = pl.DataFrame(
        {
            "stage1_available_pos": [0, 1, 2, 3, 4],
            "batch_id": [10, 20, 30, 40, 50],
            "valid_row_count": [5, 5, 5, 5, 5],
        }
    )

    steps = plan_regression_steps(
        batch_index,
        n_steps=1,
        lookback_batches=2,
        val_batches=1,
        embargo_batches=1,
    )

    assert steps[0].pred_batch_id == 50
    assert steps[0].train_batch_ids == (10, 20)
    assert steps[0].val_batch_ids == (30,)


def test_regression_steps_round_trip_explicit_batch_lists(tmp_path) -> None:
    steps = [
        RegressionStep(
            step_idx=0,
            pred_pos=10,
            pred_batch_id=30,
            train_batch_ids=(10, 11),
            val_batch_ids=(20,),
        )
    ]
    path = tmp_path / "frozen_steps.parquet"

    regression_steps_to_frame(steps).write_parquet(path)
    loaded = load_regression_steps_from_index(path)

    assert loaded == steps


def test_catboost_param_builder_validates_conditional_params() -> None:
    with pytest.raises(ValueError, match="subsample requires"):
        build_catboost_params(
            CatBoostModelConfig(bootstrap_type="Bayesian", subsample=0.8),
            task_type="GPU",
            thread_count=-1,
        )


def test_prepare_regression_frame_filters_null_targets_and_excludes_target_columns() -> None:
    df = pl.DataFrame(
        {
            "timestamp": _timestamps(3),
            "batch_id": [1, 1, 1],
            "T_BTCUSDT__close": [100.0, 101.0, 102.0],
            "target_4class": [0, 1, 2],
            "target_reg_distance_up_extreme_vol_v1": [1.0, None, 3.0],
        }
    )

    X, y, feature_cols, meta = prepare_regression_frame(
        df,
        "target_reg_distance_up_extreme_vol_v1",
    )

    assert feature_cols == ["T_BTCUSDT__close"]
    assert X.shape == (2, 1)
    assert y.tolist() == [1.0, 3.0]
    assert meta["timestamp"].to_list() == [df["timestamp"][0], df["timestamp"][2]]


def test_target_specific_feature_policy_is_train_only_and_drops_bad_features() -> None:
    rows = 400
    ts = _timestamps(rows)
    target = np.linspace(0.0, 1.0, rows)
    good_up = target + 0.01
    good_down = 1.0 - target
    df = pl.DataFrame(
        {
            "timestamp": ts,
            "batch_id": [1] * rows,
            "T_BTCUSDT__M_good_up": good_up.tolist(),
            "T_BTCUSDT__M_good_down": good_down.tolist(),
            "T_BTCUSDT__open": np.linspace(100.0, 101.0, rows).tolist(),
            "T_BTCUSDT__constant": [3.0] * rows,
            "T_BTCUSDT__near_constant": [0.0] * (rows - 1) + [1.0],
            "T_BTCUSDT__bad_inf": [1.0] * (rows - 1) + [float("inf")],
            "T_BTCUSDT__huge_ou_zscore": [0.1] * (rows - 1) + [2_000_000.0],
            "T_BTCUSDT__target_future_debug": target.tolist(),
            "T_BTCUSDT__rpf_align_15m_has_closed_bar": [True] * rows,
            "target_reg_distance_up_extreme_vol_v1": target.tolist(),
        }
    )
    feature_cols = [col for col in df.columns if col.startswith("T_BTCUSDT__")]

    result = select_target_specific_features(
        df,
        "target_reg_distance_up_extreme_vol_v1",
        feature_cols,
        config=FeaturePolicyConfig(
            policy=FEATURE_POLICY_TARGET_SPECIFIC_V1,
            max_features=2,
            min_abs_spearman=0.01,
            dedupe_corr_threshold=0.995,
            clip_quantiles=(0.1, 0.9),
        ),
    )

    assert "T_BTCUSDT__M_good_up" in result.selected_features
    assert "T_BTCUSDT__open" not in result.selected_features
    assert "T_BTCUSDT__target_future_debug" not in result.selected_features
    reasons = {
        row["feature"]: row["drop_reason"]
        for row in result.detail.select(["feature", "drop_reason"]).to_dicts()
    }
    assert reasons["T_BTCUSDT__open"] == "raw_ohlcv_unscaled"
    assert reasons["T_BTCUSDT__constant"] == "constant"
    assert reasons["T_BTCUSDT__near_constant"] == "near_constant"
    assert reasons["T_BTCUSDT__bad_inf"] == "null_or_nonfinite"
    assert reasons["T_BTCUSDT__huge_ou_zscore"] == "extreme_abs_ge_1e6"
    assert reasons["T_BTCUSDT__target_future_debug"] == "leakage_name_pattern"
    assert reasons["T_BTCUSDT__rpf_align_15m_has_closed_bar"] == "regression_feature_metadata"
    assert result.clip_bounds["T_BTCUSDT__M_good_up"][0] == pytest.approx(float(np.quantile(good_up, 0.1)))


def test_target_specific_feature_policy_handles_many_static_drops_before_scores() -> None:
    rows = 80
    target = np.linspace(0.0, 1.0, rows)
    data = {
        "timestamp": _timestamps(rows),
        "batch_id": [1] * rows,
        "T_BTCUSDT__good_signal": target.tolist(),
        "target_reg_distance_up_extreme_hvol_v2": target.tolist(),
    }
    for idx in range(140):
        data[f"T_BTCUSDT__target_future_debug_{idx}"] = target.tolist()
    df = pl.DataFrame(data)
    feature_cols = [col for col in df.columns if col.startswith("T_BTCUSDT__")]

    result = select_target_specific_features(
        df,
        "target_reg_distance_up_extreme_hvol_v2",
        feature_cols,
        config=FeaturePolicyConfig(
            policy=FEATURE_POLICY_TARGET_SPECIFIC_V2,
            max_features=1,
            min_selected_features=1,
            min_abs_spearman=0.01,
            dedupe_corr_threshold=0.995,
            stability_segments=2,
            clip_quantiles=(0.1, 0.9),
        ),
    )

    assert result.selected_features == ("T_BTCUSDT__good_signal",)
    assert result.detail.height == len(feature_cols)
    reasons = {
        row["feature"]: row["drop_reason"]
        for row in result.detail.select(["feature", "drop_reason"]).to_dicts()
    }
    assert reasons["T_BTCUSDT__target_future_debug_139"] == "leakage_name_pattern"


def test_regression_metrics_report_error_and_rank_quality() -> None:
    y_true = np.array([1.0, 2.0, 3.0, 4.0])
    y_pred = np.array([1.1, 2.1, 2.9, 3.8])

    metrics = regression_metrics(y_true, y_pred)

    assert metrics["rows"] == 4
    assert metrics["mae"] == pytest.approx(0.125)
    assert metrics["rmse"] == pytest.approx(np.sqrt(0.0175))
    assert metrics["spearman"] == pytest.approx(1.0)
    assert metrics["spearman_null_reason"] is None
    assert metrics["pearson"] is not None
    assert metrics["target_std"] == pytest.approx(np.std(y_true))
    assert metrics["pred_std"] == pytest.approx(np.std(y_pred))
    assert metrics["target_unique"] == 4
    assert metrics["pred_unique"] == 4
    assert metrics["p95_coverage_ratio"] is not None
    assert metrics["tail_rows"] == 1
    assert metrics["tail_mae"] == pytest.approx(0.2)


def test_regression_metrics_explain_constant_prediction_spearman_null() -> None:
    y_true = np.array([0.1, 0.2, 0.3, 0.4])
    y_pred = np.array([0.25, 0.25, 0.25, 0.25])

    metrics = regression_metrics(y_true, y_pred)

    assert metrics["spearman"] is None
    assert metrics["spearman_null_reason"] == "constant_prediction"
    assert metrics["target_std"] > 0
    assert metrics["pred_std"] == 0
    assert metrics["pred_unique"] == 1


def test_regression_feature_source_joins_target_features(tmp_path) -> None:
    features_dir = tmp_path / "merged" / "features"
    labels_dir = tmp_path / "merged" / "labels"
    feat_batch_dir = features_dir / "1m" / "target_4class"
    label_batch_dir = labels_dir / "1m"
    feat_batch_dir.mkdir(parents=True)
    label_batch_dir.mkdir(parents=True)
    ts = _timestamps(3)
    pl.DataFrame(
        {
            "timestamp": ts,
            "batch_id": [1, 1, 1],
            "T_BTCUSDT__htf_feature": [0.1, 0.2, 0.3],
            "target_4class": [0, 1, 2],
        }
    ).write_parquet(feat_batch_dir / "batch_0001.parquet")
    pl.DataFrame(
        {
            "timestamp": ts,
            "batch_id": [1, 1, 1],
            "target_reg_distance_up_extreme_hvol_v2": [1.0, 2.0, 3.0],
        }
    ).write_parquet(label_batch_dir / "batch_0001.parquet")

    rpf_dir = tmp_path / "data" / "htf_multiasset" / "btcusdt" / "regression_path_features_v1" / "8h_b" / "1m"
    rpf_dir.mkdir(parents=True)
    pl.DataFrame(
        {
            "timestamp": ts,
            "batch_id": [1, 1, 1],
            "asset_id": ["BTCUSDT"] * 3,
            "root_id": ["8h_b"] * 3,
            "feature_set": ["regression_path_features_v1"] * 3,
            "rpf_vol_signal": [10.0, 11.0, 12.0],
            "rpf_align_15m_has_closed_bar": [True, True, True],
            "rpf_align_15m_bar_close_ts": ts,
        }
    ).write_parquet(rpf_dir / "batch_0001.parquet")
    (rpf_dir / "manifest.json").write_text('{"feature_columns": ["rpf_vol_signal"]}\n')
    dataset = RegressionDataset(
        target_asset="BTCUSDT",
        context_assets=(),
        context_hash="self",
        root_key="8h/B",
        root_id="8h_b",
        target_col="target_reg_distance_up_extreme_hvol_v2",
        feature_target_col="target_4class",
        features_dir=features_dir,
        labels_dir=labels_dir,
        manifest_path=tmp_path / "manifest.json",
        batch_index_path=tmp_path / "stage1_batch_index.parquet",
    )

    htf_plus = load_regression_feature_frame(
        dataset,
        (1,),
        feature_source_config=FeatureSourceConfig(
            mode=FEATURE_SOURCE_HTF_PLUS_REGRESSION,
            data_root=tmp_path / "data",
        ),
    )
    assert "T_BTCUSDT__htf_feature" in htf_plus.columns
    assert "T_BTCUSDT__rpf_vol_signal" in htf_plus.columns
    assert "T_BTCUSDT__rpf_align_15m_bar_close_ts" not in htf_plus.columns
    assert "T_BTCUSDT__rpf_align_15m_has_closed_bar" not in htf_plus.columns

    regression_only = load_regression_feature_frame(
        dataset,
        (1,),
        feature_source_config=FeatureSourceConfig(
            mode=FEATURE_SOURCE_REGRESSION_ONLY,
            data_root=tmp_path / "data",
        ),
    )
    assert "T_BTCUSDT__htf_feature" not in regression_only.columns
    assert regression_only["target_reg_distance_up_extreme_hvol_v2"].to_list() == [1.0, 2.0, 3.0]
    assert regression_only["T_BTCUSDT__rpf_vol_signal"].to_list() == [10.0, 11.0, 12.0]
    assert "T_BTCUSDT__rpf_align_15m_has_closed_bar" not in regression_only.columns


def test_regression_run_id_includes_feature_source_and_suffix(tmp_path) -> None:
    dataset = RegressionDataset(
        target_asset="BTCUSDT",
        context_assets=(),
        context_hash="self",
        root_key="8h/B",
        root_id="8h_b",
        target_col="target_reg_distance_up_extreme_hvol_v2",
        feature_target_col="target_4class",
        features_dir=tmp_path,
        labels_dir=tmp_path,
        manifest_path=tmp_path / "manifest.json",
        batch_index_path=tmp_path / "batch_index.parquet",
    )

    run_id = build_regression_run_id(
        dataset,
        feature_source_config=FeatureSourceConfig(mode=FEATURE_SOURCE_HTF_PLUS_REGRESSION),
        run_suffix="lb120-val20-mf150",
    )

    assert "feat_htf_plus_regression" in run_id
    assert run_id.endswith("lb120_val20_mf150")


def test_regression_grid_skips_invalid_val_windows() -> None:
    class Args:
        feature_source_modes = "htf_plus_regression"
        lookback_grid = "10,20"
        val_grid = "10,15"
        max_features_grid = "50"
        min_abs_spearman_grid = "0.03"
        dedupe_corr_grid = "0.98"
        iterations_grid = "100"
        depth_grid = "4"
        learning_rate_grid = "0.05"

    rows = iter_grid(Args())

    assert len(rows) == 2
    assert {(row["lookback_batches"], row["val_batches"]) for row in rows} == {
        (20, 10),
        (20, 15),
    }


def test_regression_grid_interleaves_feature_source_modes() -> None:
    class Args:
        feature_source_modes = "htf_only,regression_only,htf_plus_regression"
        lookback_grid = "20,40"
        val_grid = "10"
        max_features_grid = "50"
        min_abs_spearman_grid = "0.03"
        dedupe_corr_grid = "0.98"
        iterations_grid = "100"
        depth_grid = "4"
        learning_rate_grid = "0.05"

    rows = iter_grid(Args())

    assert [row["feature_source_mode"] for row in rows[:3]] == [
        FEATURE_SOURCE_HTF_ONLY,
        FEATURE_SOURCE_REGRESSION_ONLY,
        FEATURE_SOURCE_HTF_PLUS_REGRESSION,
    ]
    assert [row["lookback_batches"] for row in rows[:3]] == [20, 20, 20]
    assert [row["feature_source_mode"] for row in rows[3:6]] == [
        FEATURE_SOURCE_HTF_ONLY,
        FEATURE_SOURCE_REGRESSION_ONLY,
        FEATURE_SOURCE_HTF_PLUS_REGRESSION,
    ]
    assert [row["lookback_batches"] for row in rows[3:6]] == [40, 40, 40]


def test_target_specific_v2_does_not_fallback_to_noisy_features() -> None:
    rows = 200
    rng = np.random.default_rng(42)
    df = pl.DataFrame(
        {
            "timestamp": _timestamps(rows),
            "batch_id": [1] * rows,
            "T_BTCUSDT__noise_0": rng.normal(size=rows).tolist(),
            "T_BTCUSDT__noise_1": rng.normal(size=rows).tolist(),
            "target_reg_distance_up_extreme_hvol_v2": np.linspace(0.0, 1.0, rows).tolist(),
        }
    )

    with pytest.raises(ValueError, match="too few train-only eligible features"):
        select_target_specific_features(
            df,
            "target_reg_distance_up_extreme_hvol_v2",
            ["T_BTCUSDT__noise_0", "T_BTCUSDT__noise_1"],
            config=FeaturePolicyConfig(
                policy=FEATURE_POLICY_TARGET_SPECIFIC_V2,
                max_features=2,
                min_abs_spearman=0.95,
                min_selected_features=2,
            ),
        )


def test_target_specific_v2_prefers_signed_stable_features() -> None:
    rows = 300
    y = np.linspace(0.0, 1.0, rows)
    stable = y + 0.001
    sign_flipper = y.copy()
    sign_flipper[rows // 2 :] = 1.0 - sign_flipper[rows // 2 :]
    df = pl.DataFrame(
        {
            "timestamp": _timestamps(rows),
            "batch_id": [1] * rows,
            "T_BTCUSDT__stable": stable.tolist(),
            "T_BTCUSDT__sign_flipper": sign_flipper.tolist(),
            "target_reg_distance_up_extreme_hvol_v2": y.tolist(),
        }
    )

    result = select_target_specific_features(
        df,
        "target_reg_distance_up_extreme_hvol_v2",
        ["T_BTCUSDT__stable", "T_BTCUSDT__sign_flipper"],
        config=FeaturePolicyConfig(
            policy=FEATURE_POLICY_TARGET_SPECIFIC_V2,
            max_features=1,
            min_abs_spearman=0.01,
            min_selected_features=1,
            dedupe_corr_threshold=0.999,
        ),
    )

    assert result.selected_features == ("T_BTCUSDT__stable",)
    detail = {
        row["feature"]: row
        for row in result.detail.select(
            ["feature", "sign_consistency", "stability_score", "tail_spread_score"]
        ).to_dicts()
    }
    assert detail["T_BTCUSDT__stable"]["sign_consistency"] == pytest.approx(1.0)
    assert detail["T_BTCUSDT__stable"]["stability_score"] > detail["T_BTCUSDT__sign_flipper"]["stability_score"]
