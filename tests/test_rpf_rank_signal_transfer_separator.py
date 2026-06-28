from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest

from regression_feature_engineering.walkforward.rank_signal_transfer_separator import (
    auc_score,
    load_joined_separator_frame,
    safe_numeric_feature_columns,
    separator_results,
)


def test_auc_score_handles_direction_and_ties() -> None:
    assert auc_score(values=pl.Series([3.0, 2.0, 1.0, 0.0]).to_numpy(), labels=pl.Series([1, 1, 0, 0]).to_numpy()) == 1.0
    assert auc_score(values=pl.Series([0.0, 1.0, 2.0, 3.0]).to_numpy(), labels=pl.Series([1, 1, 0, 0]).to_numpy()) == 0.0
    assert auc_score(values=pl.Series([1.0, 1.0]).to_numpy(), labels=pl.Series([1, 0]).to_numpy()) == 0.5


def test_safe_numeric_feature_columns_excludes_identity_and_labels() -> None:
    frame = pl.DataFrame(
        [
            {
                "source_block": "older",
                "side": "down",
                "candidate_name": "down_none_v1",
                "router_pred_batch_id": 1,
                "validation_precision_lift": 1.4,
                "batch_state_gate_passed": True,
                "precision": 1.0,
                "candidate_good": True,
            }
        ]
    )

    cols = safe_numeric_feature_columns(frame)

    assert "validation_precision_lift" in cols
    assert "batch_state_gate_passed" in cols
    assert "precision" not in cols
    assert "candidate_good" not in cols
    assert "router_pred_batch_id" not in cols


def test_separator_results_rank_good_bad_features() -> None:
    frame = pl.DataFrame(
        [
            {"side": "down", "candidate_name": "down_none_v1", "candidate_good": True, "candidate_bad": False, "good_high": 0.9, "bad_high": 0.1},
            {"side": "down", "candidate_name": "down_none_v1", "candidate_good": True, "candidate_bad": False, "good_high": 0.8, "bad_high": 0.2},
            {"side": "down", "candidate_name": "down_none_v1", "candidate_good": False, "candidate_bad": True, "good_high": 0.2, "bad_high": 0.9},
            {"side": "down", "candidate_name": "down_none_v1", "candidate_good": False, "candidate_bad": True, "good_high": 0.1, "bad_high": 0.8},
        ]
    )

    rows = separator_results(
        frame,
        feature_columns=["good_high", "bad_high"],
        min_good_rows=2,
        min_bad_rows=2,
    )

    by_feature = {row.feature: row for row in rows if row.group_scope == "candidate"}
    assert by_feature["good_high"].auc_good_high == pytest.approx(1.0)
    assert by_feature["good_high"].direction == "higher_good"
    assert by_feature["bad_high"].auc_good_high == pytest.approx(0.0)
    assert by_feature["bad_high"].direction == "lower_good"


def test_load_joined_separator_frame_rejects_safe_context_label_leak(tmp_path: Path) -> None:
    run = tmp_path / "diag"
    run.mkdir()
    pl.DataFrame(
        [
            {
                "source_block": "older",
                "source_role": "comparison_train",
                "source_run": "run",
                "side": "down",
                "candidate_name": "down_none_v1",
                "router_step_idx": 1,
                "router_pred_batch_id": 1,
                "validation_precision_lift": 1.2,
                "precision": 1.0,
            }
        ]
    ).write_parquet(run / "safe_context_features.parquet")
    pl.DataFrame(
        [
            {
                "source_block": "older",
                "source_role": "comparison_train",
                "source_run": "run",
                "side": "down",
                "candidate_name": "down_none_v1",
                "router_step_idx": 1,
                "router_pred_batch_id": 1,
                "candidate_good": True,
                "candidate_bad": False,
            }
        ]
    ).write_parquet(run / "candidate_transfer_table.parquet")

    with pytest.raises(ValueError, match="current-label columns"):
        load_joined_separator_frame(run)
