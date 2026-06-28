from __future__ import annotations

import numpy as np
import polars as pl
import pytest

from regression_feature_engineering.walkforward.rank_signal import (
    BATCH_STATE_GATE_LOGISTIC_PREFIX_V1,
    SIDE_DOWN,
    SIDE_UP,
    BatchStateGateConfig,
    ElasticNetRelevanceConfig,
    RankTrialConfig,
    apply_batch_state_gate_to_decisions,
    binary_decision_metrics,
    binary_expr,
    causal_lag_matrix,
    causal_signal_budget_decisions,
    make_rocket_kernels,
    ranked_signal_quality,
    offline_topk_diagnostic_metrics,
    relevance_expr,
    select_window_block,
    select_elasticnet_relevance_features,
    causal_rocket_transform,
    trial_config_from_payload,
    trial_config_payload,
)
from regression_feature_engineering.walkforward.windows import RPFWindow


def test_ranked_signal_relevance_and_binary_labels_are_side_specific() -> None:
    frame = pl.DataFrame(
        {
            "target_reg_distance_up_extreme_hvol_v2": [4.0, 1.0, 0.0],
            "target_reg_distance_down_extreme_hvol_v2": [1.0, 3.0, 2.0],
        }
    )

    out = frame.with_columns(
        relevance_expr(SIDE_UP).alias("up_rel"),
        relevance_expr(SIDE_DOWN).alias("down_rel"),
        binary_expr(SIDE_UP).alias("up_bin"),
        binary_expr(SIDE_DOWN).alias("down_bin"),
    )

    assert out["up_rel"].to_list() == pytest.approx([0.8, 0.25, 0.0])
    assert out["down_rel"].to_list() == pytest.approx([0.2, 0.75, 1.0])
    assert out["up_bin"].to_list() == [1, 0, 0]
    assert out["down_bin"].to_list() == [0, 1, 1]


def test_causal_signal_budget_uses_timestamp_order_not_score_sort() -> None:
    scores = np.asarray([0.60, 0.95, 0.80, 0.70], dtype=float)
    group_id = np.asarray([10, 10, 10, 10])
    timestamps = [3, 1, 2, 4]

    decisions = causal_signal_budget_decisions(
        scores,
        group_id,
        timestamps,
        threshold=0.65,
        max_signals=2,
    )

    # Timestamp order is row 1, row 2, row 0, row 3. Rows 1 and 2 fire first.
    # A future-aware top-score policy would have selected rows 1 and 2 here by
    # coincidence, so also verify row 3 is suppressed even though it passes.
    assert decisions.tolist() == [0, 1, 1, 0]


def test_causal_signal_budget_differs_from_future_top_score_sort() -> None:
    scores = np.asarray([0.60, 0.70, 0.95, 0.90], dtype=float)
    group_id = np.asarray([10, 10, 10, 10])
    timestamps = [1, 2, 3, 4]

    decisions = causal_signal_budget_decisions(
        scores,
        group_id,
        timestamps,
        threshold=0.50,
        max_signals=2,
    )

    assert decisions.tolist() == [1, 1, 0, 0]


def test_batch_state_gate_suppresses_failed_groups_and_prefix_rows() -> None:
    raw = np.asarray([1, 1, 1, 1, 1, 1], dtype=np.int8)
    groups = np.asarray([10, 10, 10, 20, 20, 20])

    gated = apply_batch_state_gate_to_decisions(
        raw,
        groups,
        {10: True, 20: False},
        prefix_rows=1,
        mode=BATCH_STATE_GATE_LOGISTIC_PREFIX_V1,
    )

    assert gated.tolist() == [0, 1, 1, 0, 0, 0]


def test_rank_trial_config_round_trips_batch_state_gate() -> None:
    config = RankTrialConfig(
        batch_state_gate=BatchStateGateConfig(
            mode=BATCH_STATE_GATE_LOGISTIC_PREFIX_V1,
            prefix_rows=30,
            min_positive_rate=0.25,
            probability_threshold=0.6,
        )
    )

    payload = trial_config_payload(config)
    restored = trial_config_from_payload(payload)

    assert payload["batch_state_gate"]["mode"] == BATCH_STATE_GATE_LOGISTIC_PREFIX_V1
    assert restored.batch_state_gate.prefix_rows == 30
    assert restored.batch_state_gate.min_positive_rate == pytest.approx(0.25)
    assert restored.batch_state_gate.probability_threshold == pytest.approx(0.6)


def test_ranked_signal_quality_rewards_precision_lift_and_stability() -> None:
    good = {
        "precision": 0.75,
        "precision_lift": 2.0,
        "active_window_rate": 0.5,
        "high_target_window_capture_rate": 0.5,
        "false_discovery_rate": 0.25,
        "zero_signal_window_rate": 0.5,
        "missed_high_target_window_rate": 0.5,
        "high_false_positive_window_rate": 0.1,
        "selected_feature_count_mean": 80,
    }
    bad = {
        "precision": 0.25,
        "precision_lift": 0.8,
        "active_window_rate": 0.1,
        "high_target_window_capture_rate": 0.0,
        "false_discovery_rate": 0.75,
        "zero_signal_window_rate": 0.9,
        "missed_high_target_window_rate": 1.0,
        "high_false_positive_window_rate": 0.5,
        "selected_feature_count_mean": 160,
    }

    assert ranked_signal_quality(good) > ranked_signal_quality(bad)


def test_binary_decision_metrics_report_precision_lift() -> None:
    metrics = binary_decision_metrics(
        np.asarray([1, 1, 0, 0]),
        np.asarray([1, 0, 1, 0]),
        fp_cost=5.0,
        fn_cost=1.0,
    )

    assert metrics["precision"] == pytest.approx(0.5)
    assert metrics["base_positive_rate"] == pytest.approx(0.5)
    assert metrics["precision_lift"] == pytest.approx(1.0)
    assert metrics["decision_cost_per_row"] == pytest.approx(1.5)


def test_binary_decision_metrics_allow_undefined_precision_and_fpr() -> None:
    no_signal = binary_decision_metrics(
        np.asarray([1, 0, 1, 0]),
        np.asarray([0, 0, 0, 0]),
        fp_cost=5.0,
        fn_cost=1.0,
    )
    no_negatives = binary_decision_metrics(
        np.asarray([1, 1, 1]),
        np.asarray([1, 0, 1]),
        fp_cost=5.0,
        fn_cost=1.0,
    )

    assert no_signal["precision"] is None
    assert no_signal["precision_lift"] is None
    assert no_signal["false_positive_rate"] == pytest.approx(0.0)
    assert no_negatives["false_positive_rate"] is None


def test_offline_topk_metrics_are_marked_diagnostic_only() -> None:
    metrics = offline_topk_diagnostic_metrics(
        np.asarray([1, 0, 1, 0]),
        np.asarray([0.2, 0.9, 0.8, 0.1]),
        k=2,
    )

    assert metrics["offline_topk_diagnostic_only"] is True
    assert metrics["offline_topk_precision"] == pytest.approx(0.5)
    assert metrics["offline_topk_recall"] == pytest.approx(0.5)


def test_elasticnet_relevance_selector_uses_continuous_relevance() -> None:
    rng = np.random.default_rng(42)
    signal = np.linspace(0.0, 1.0, 80)
    noise = rng.normal(0.0, 1.0, 80)
    X = np.column_stack([signal, noise, np.ones(80)]).astype("float32")

    result = select_elasticnet_relevance_features(
        X,
        signal.astype("float32"),
        ("rpf_signal", "rpf_noise", "rpf_constant"),
        ElasticNetRelevanceConfig(
            alpha=0.001,
            l1_ratio=0.75,
            max_features=2,
            min_features=1,
            coef_eps=1e-8,
            prefilter_features=2,
            max_iter=5000,
        ),
    )

    assert result.selected_features[0] == "rpf_signal"
    assert "rpf_constant" not in result.selected_features


def test_causal_lag_matrix_and_rocket_are_deterministic_and_causal() -> None:
    values = np.asarray([1.0, 2.0, 3.0, 4.0], dtype="float32")
    lags = causal_lag_matrix(values, np.asarray([0, 2, 3]), sequence_length=3)

    assert np.allclose(lags, np.asarray([[0.0, 0.0, 1.0], [1.0, 2.0, 3.0], [2.0, 3.0, 4.0]]))

    X = np.column_stack([values, values * 2.0]).astype("float32")
    kernels = make_rocket_kernels(input_features=2, n_kernels=4, sequence_length=3, seed=7)
    first = causal_rocket_transform(X, np.asarray([1, 2, 3]), kernels, sequence_length=3)
    second = causal_rocket_transform(X, np.asarray([1, 2, 3]), kernels, sequence_length=3)

    assert first.shape == (3, 12)
    assert np.allclose(first, second)


def test_select_window_block_supports_historical_end_offset() -> None:
    windows = [
        RPFWindow(step_idx=idx, pred_pos=idx, pred_batch_id=100 + idx, train_batch_ids=(1,), val_batch_ids=(2,))
        for idx in range(10)
    ]

    latest = select_window_block(windows, n_steps=3, window_end_offset_steps=0)
    older = select_window_block(windows, n_steps=3, window_end_offset_steps=2)

    assert [window.pred_batch_id for window in latest] == [107, 108, 109]
    assert [window.pred_batch_id for window in older] == [105, 106, 107]

    with pytest.raises(ValueError):
        select_window_block(windows, n_steps=3, window_end_offset_steps=-1)
