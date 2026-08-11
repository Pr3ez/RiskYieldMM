from __future__ import annotations

import polars as pl

from regression_feature_engineering.walkforward.rank_signal_regime_suppression_simulator import (
    build_prequential_suppression_windows,
    context_keys,
    diagnostic_prediction_source,
    suppression_summary,
    suppression_window_row,
    write_suppression_report,
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


def test_prequential_suppression_uses_prior_windows_only(tmp_path) -> None:
    regime_run = tmp_path / "regime"
    regime_run.mkdir()
    quality_rows = []
    for idx in range(5):
        quality_rows.append(
            {
                "source_run": "run_a",
                "side": "down",
                "candidate_name": "down_rocket_16_diag_v1",
                "step_idx": idx,
                "pred_batch_id": 100 + idx,
                "rows": 100,
                "positive_count": 50,
                "predicted_positive_count": 10,
                "true_positive_count": 2,
                "false_positive_count": 8,
                "regime_state": 1,
            }
        )
    quality_rows.append(
        {
            "source_run": "run_a",
            "side": "down",
            "candidate_name": "down_rocket_16_diag_v1",
            "step_idx": 5,
            "pred_batch_id": 105,
            "rows": 100,
            "positive_count": 50,
            "predicted_positive_count": 10,
            "true_positive_count": 10,
            "false_positive_count": 0,
            "regime_state": 2,
        }
    )
    pl.DataFrame(quality_rows).write_parquet(regime_run / "regime_signal_quality.parquet")
    pl.DataFrame().write_parquet(regime_run / "change_point_events.parquet")

    windows, audit = build_prequential_suppression_windows(
        regime_run,
        context_types={"regime_state"},
        min_history_windows=3,
        lookback_windows=5,
        min_signals=20,
        avoid_max_lift=1.0,
        avoid_min_fdr=0.60,
    )

    rows = windows.sort("pred_batch_id").to_dicts()
    assert rows[0]["suppressed"] is False
    assert rows[1]["suppressed"] is False
    assert rows[2]["suppressed"] is False
    assert rows[3]["suppressed"] is True
    assert rows[4]["suppressed"] is True
    assert rows[5]["suppressed"] is False
    assert not audit.is_empty()
    assert audit["pred_batch_id"].min() == 103


def test_prequential_change_context_ignores_false_change_flags() -> None:
    row = {
        "side": "up",
        "candidate_name": "up_rocket_64_v1",
        "regime_state": 2,
        "has_cusum": False,
        "has_page_hinkley": True,
    }

    keys = context_keys(
        row,
        context_types={"regime_state", "change_flag", "regime_state_change_flag"},
    )

    assert ("regime_state", 2, None, None) in keys
    assert ("change_flag", None, "has_page_hinkley", True) in keys
    assert ("regime_state_change_flag", 2, "has_page_hinkley", True) in keys
    assert ("change_flag", None, "has_cusum", False) not in keys
    assert ("regime_state_change_flag", 2, "has_cusum", False) not in keys


def test_diagnostic_prediction_source_reads_regime_config(tmp_path) -> None:
    regime_run = tmp_path / "regime"
    regime_run.mkdir()
    (regime_run / "regime_diagnostic_config.json").write_text('{"prediction_source": "router_selected"}')

    assert diagnostic_prediction_source(regime_run) == "router_selected"


def test_diagnostic_prediction_source_prefers_resolved_quality_source(tmp_path) -> None:
    regime_run = tmp_path / "regime"
    regime_run.mkdir()
    (regime_run / "regime_diagnostic_config.json").write_text('{"prediction_source": "effective_selected"}')
    pl.DataFrame({"prediction_source": ["row_rule_active", "row_rule_active"]}).write_parquet(
        regime_run / "regime_signal_quality.parquet"
    )

    assert diagnostic_prediction_source(regime_run) == "row_rule_active"


def test_suppression_report_names_prediction_source(tmp_path) -> None:
    path = tmp_path / "report.md"
    summary = pl.DataFrame(
        [
            {
                "scope": "overall",
                "side": "up",
                "candidate_name": "up_rocket_64_v1",
                "windows": 1,
                "suppressed_windows": 0,
                "signals_before": 1,
                "signals_after": 1,
                "precision_before": 1.0,
                "precision_after": 1.0,
                "lift_before": 2.0,
                "lift_after": 2.0,
                "fdr_before": 0.0,
                "fdr_after": 0.0,
                "fp_reduction": 0.0,
            }
        ]
    )

    write_suppression_report(
        path,
        regime_run=tmp_path / "regime",
        summary=summary,
        simulation_mode="prequential",
        prediction_source="router_selected",
    )

    assert "prediction source: `router_selected`" in path.read_text()
