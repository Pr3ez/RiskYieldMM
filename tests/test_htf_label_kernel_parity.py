from __future__ import annotations

import numpy as np

from scripts.feature_engineering.htf_kernels import (
    _compute_hybrid_distance_metrics_reference,
    compute_hybrid_distance_metrics,
)


def _assert_metric_tuple_equal(actual, expected) -> None:
    assert len(actual) == len(expected) == 5
    for actual_arr, expected_arr in zip(actual[:4], expected[:4], strict=True):
        np.testing.assert_allclose(actual_arr, expected_arr, rtol=0.0, atol=0.0, equal_nan=True)
    np.testing.assert_array_equal(actual[4], expected[4])


def test_opposite_family_hybrid_distance_fast_path_matches_reference() -> None:
    close_entry = np.array(
        [100.0, 101.0, 102.0, 103.0, 104.0, 200.0, 201.0, 202.0, 300.0, 400.0],
        dtype=np.float64,
    )
    batch_id_entry = np.array([1, 1, 1, 1, 1, 2, 2, 2, 3, -1], dtype=np.int64)
    bar_pos_15m_for_entry = np.full(len(close_entry), -1, dtype=np.int32)

    high_15m = np.array(
        [110.0, 111.0, np.nan, 113.0, 210.0, 211.0, 212.0, 310.0],
        dtype=np.float64,
    )
    low_15m = np.array(
        [90.0, 91.0, 92.0, np.nan, 190.0, 191.0, 192.0, 290.0],
        dtype=np.float64,
    )
    batch_id_15m = np.array([1, 1, 1, 1, 2, 2, 2, 3], dtype=np.int64)
    bar_pos_15m = np.array([0, 1, 2, 3, 0, 1, 2, 0], dtype=np.int32)

    actual = compute_hybrid_distance_metrics(
        close_entry,
        batch_id_entry,
        bar_pos_15m_for_entry,
        high_15m,
        low_15m,
        batch_id_15m,
        bar_pos_15m,
        min_remaining=2,
        outlier_pct=0.05,
    )
    expected = _compute_hybrid_distance_metrics_reference(
        close_entry,
        batch_id_entry,
        bar_pos_15m_for_entry,
        high_15m,
        low_15m,
        batch_id_15m,
        bar_pos_15m,
        min_remaining=2,
        outlier_pct=0.05,
    )

    _assert_metric_tuple_equal(actual, expected)


def test_hybrid_distance_falls_back_when_entry_bar_positions_are_specific() -> None:
    close_entry = np.array([100.0, 101.0, 102.0, 103.0], dtype=np.float64)
    batch_id_entry = np.array([1, 1, 1, 1], dtype=np.int64)
    bar_pos_15m_for_entry = np.array([0, 0, 1, 1], dtype=np.int32)
    high_15m = np.array([110.0, 111.0, 112.0], dtype=np.float64)
    low_15m = np.array([90.0, 91.0, 92.0], dtype=np.float64)
    batch_id_15m = np.array([1, 1, 1], dtype=np.int64)
    bar_pos_15m = np.array([0, 1, 2], dtype=np.int32)

    actual = compute_hybrid_distance_metrics(
        close_entry,
        batch_id_entry,
        bar_pos_15m_for_entry,
        high_15m,
        low_15m,
        batch_id_15m,
        bar_pos_15m,
        min_remaining=1,
        outlier_pct=0.05,
    )
    expected = _compute_hybrid_distance_metrics_reference(
        close_entry,
        batch_id_entry,
        bar_pos_15m_for_entry,
        high_15m,
        low_15m,
        batch_id_15m,
        bar_pos_15m,
        min_remaining=1,
        outlier_pct=0.05,
    )

    _assert_metric_tuple_equal(actual, expected)
