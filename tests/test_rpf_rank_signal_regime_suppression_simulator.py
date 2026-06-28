from __future__ import annotations

import polars as pl

from regression_feature_engineering.walkforward.rank_signal_regime_suppression_simulator import (
    suppression_summary,
    suppression_window_row,
)


def test_suppression_window_row_suppresses_matching_state_and_flag() -> None:
    row = {
        "side": "down",
        "candidate_name": "down_rocket_16_diag_v1",
        "regime_state": 0,
        "has_cusum": True,
        "predicted_positive_count": 5,
        "true_positive_count": 2,
        "false_positive_count": 3,
    }

    out = suppression_window_row(
        row,
        up_states={2},
        down_states={0},
        up_change_flags={"has_page_hinkley"},
        down_change_flags={"has_cusum"},
    )

    assert out["suppressed"] is True
    assert out["predicted_positive_count_after"] == 0
    assert out["true_positive_count_after"] == 0
    assert out["false_positive_count_after"] == 0
    assert out["suppressed_signal_count"] == 5
    assert "regime_state=0" in out["suppression_reason"]
    assert "has_cusum=true" in out["suppression_reason"]


def test_suppression_window_row_keeps_non_matching_context() -> None:
    row = {
        "side": "up",
        "candidate_name": "up_rocket_64_v1",
        "regime_state": 1,
        "has_page_hinkley": False,
        "predicted_positive_count": 4,
        "true_positive_count": 3,
        "false_positive_count": 1,
    }

    out = suppression_window_row(
        row,
        up_states={2},
        down_states={0},
        up_change_flags={"has_page_hinkley"},
        down_change_flags={"has_cusum"},
    )

    assert out["suppressed"] is False
    assert out["predicted_positive_count_after"] == 4
    assert out["true_positive_count_after"] == 3
    assert out["false_positive_count_after"] == 1


def test_suppression_summary_reports_precision_improvement() -> None:
    windows = pl.DataFrame(
        [
            {
                "source_run": "run_a",
                "side": "down",
                "candidate_name": "down_rocket_16_diag_v1",
                "suppressed": True,
                "rows": 100,
                "positive_count": 40,
                "predicted_positive_count_before": 5,
                "true_positive_count_before": 1,
                "false_positive_count_before": 4,
                "predicted_positive_count_after": 0,
                "true_positive_count_after": 0,
                "false_positive_count_after": 0,
                "suppressed_signal_count": 5,
                "suppressed_true_positive_count": 1,
                "suppressed_false_positive_count": 4,
            },
            {
                "source_run": "run_a",
                "side": "down",
                "candidate_name": "down_rocket_16_diag_v1",
                "suppressed": False,
                "rows": 100,
                "positive_count": 40,
                "predicted_positive_count_before": 5,
                "true_positive_count_before": 4,
                "false_positive_count_before": 1,
                "predicted_positive_count_after": 5,
                "true_positive_count_after": 4,
                "false_positive_count_after": 1,
                "suppressed_signal_count": 0,
                "suppressed_true_positive_count": 0,
                "suppressed_false_positive_count": 0,
            },
        ]
    )

    summary = suppression_summary(windows).filter(pl.col("scope") == "overall").to_dicts()[0]

    assert summary["signals_before"] == 10
    assert summary["signals_after"] == 5
    assert summary["precision_before"] == 0.5
    assert summary["precision_after"] == 0.8
    assert summary["fp_reduction"] == 0.8
