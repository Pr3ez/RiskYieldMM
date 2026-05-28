from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import polars as pl
import pytest

from scripts.analysis.htf_stage1_regression_walkforward import (
    FEATURE_POLICY_TARGET_SPECIFIC_V1,
    FeaturePolicyConfig,
    plan_regression_steps,
    prepare_regression_frame,
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
    assert result.clip_bounds["T_BTCUSDT__M_good_up"][0] == pytest.approx(float(np.quantile(good_up, 0.1)))


def test_regression_metrics_report_error_and_rank_quality() -> None:
    y_true = np.array([1.0, 2.0, 3.0, 4.0])
    y_pred = np.array([1.1, 2.1, 2.9, 3.8])

    metrics = regression_metrics(y_true, y_pred)

    assert metrics["rows"] == 4
    assert metrics["mae"] == pytest.approx(0.125)
    assert metrics["rmse"] == pytest.approx(np.sqrt(0.0175))
    assert metrics["spearman"] == pytest.approx(1.0)
    assert metrics["pearson"] is not None
