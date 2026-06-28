from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest

from regression_feature_engineering.walkforward.rank_signal_transfer_diagnostic import (
    CURRENT_LABEL_COLUMNS,
    DiagnosticInput,
    active_window_comparison_from_transfer_table,
    build_candidate_transfer_table,
    aggregate_prior_rpf_context,
    normalize_selected_feature_context,
    normalize_validation_score_context,
    normalize_validation_window_context,
    prior_batch_ids,
    safe_context_features_from_transfer_table,
    select_prior_rpf_context_features,
    summarize_transfer_table,
)


def test_safe_context_excludes_current_prediction_labels() -> None:
    transfer = pl.DataFrame(
        [
            {
                "source_block": "older",
                "source_role": "comparison_train",
                "source_run": "run",
                "side": "down",
                "candidate_name": "down_none_v1",
                "router_pred_batch_id": 10,
                "validation_precision_lift": 1.4,
                "batch_state_gate_probability": 0.8,
                "predicted_positive_count": 3,
                "true_positive_count": 3,
                "false_positive_count": 0,
                "precision": 1.0,
                "precision_lift": 2.0,
                "candidate_active": True,
                "candidate_good": True,
                "candidate_bad": False,
            }
        ]
    )

    safe = safe_context_features_from_transfer_table(transfer)

    assert "validation_precision_lift" in safe.columns
    assert "batch_state_gate_probability" in safe.columns
    assert not (CURRENT_LABEL_COLUMNS & set(safe.columns))


def test_transfer_labels_and_active_comparison(tmp_path: Path) -> None:
    older = tmp_path / "older"
    latest = tmp_path / "latest"
    _write_router_fixture(
        older,
        block_batch=100,
        predicted_positive_count=3,
        true_positive_count=3,
        false_positive_count=0,
        positive_count=6,
        rows=10,
    )
    _write_router_fixture(
        latest,
        block_batch=200,
        predicted_positive_count=3,
        true_positive_count=0,
        false_positive_count=3,
        positive_count=1,
        rows=10,
    )

    transfer = build_candidate_transfer_table(
        [
            DiagnosticInput(older, "older", "comparison_train"),
            DiagnosticInput(latest, "latest", "comparison_test"),
        ],
        candidate_names=("down_none_v1",),
        good_precision_lift=1.2,
        good_max_false_discovery_rate=0.5,
        bad_min_false_discovery_rate=0.6,
    )
    active = active_window_comparison_from_transfer_table(transfer)
    summary = summarize_transfer_table(transfer)

    older_row = transfer.filter(pl.col("source_block") == "older").row(0, named=True)
    latest_row = transfer.filter(pl.col("source_block") == "latest").row(0, named=True)

    assert older_row["candidate_active"] is True
    assert older_row["candidate_good"] is True
    assert older_row["candidate_bad"] is False
    assert latest_row["candidate_active"] is True
    assert latest_row["candidate_good"] is False
    assert latest_row["candidate_bad"] is True
    assert active.height == 2
    assert "validation_score_q95" in transfer.columns
    assert "validation_margin_positive_rate" in transfer.columns
    assert "validation_batch_base_rate_range" in transfer.columns
    assert "selected_top1_abs_coef_share" in transfer.columns
    safe = safe_context_features_from_transfer_table(transfer)
    assert "validation_score_q95" in safe.columns
    assert "validation_batch_base_rate_range" in safe.columns
    assert "selected_top1_abs_coef_share" in safe.columns
    assert not (CURRENT_LABEL_COLUMNS & set(safe.columns))
    summary_by_block = {row["source_block"]: row for row in summary["candidate_summary"]}
    assert summary_by_block["older"]["good_windows"] == 1
    assert summary_by_block["latest"]["bad_windows"] == 1


def test_validation_score_context_uses_score_shape_only() -> None:
    frame = pl.DataFrame(
        [
            {
                "side": "down",
                "candidate_name": "down_none_v1",
                "router_pred_batch_id": 10,
                "rank_score": 0.10,
                "threshold": 0.15,
            },
            {
                "side": "down",
                "candidate_name": "down_none_v1",
                "router_pred_batch_id": 10,
                "rank_score": 0.20,
                "threshold": 0.15,
            },
            {
                "side": "down",
                "candidate_name": "down_none_v1",
                "router_pred_batch_id": 10,
                "rank_score": 0.30,
                "threshold": 0.15,
            },
        ]
    )

    out = normalize_validation_score_context(frame).row(0, named=True)

    assert out["validation_score_rows"] == 3
    assert out["validation_score_mean"] == pytest.approx(0.2)
    assert out["validation_margin_positive_rate"] == pytest.approx(2 / 3)
    assert out["validation_score_tail_spread_q95_q50"] is not None


def test_validation_window_context_captures_batch_stability() -> None:
    frame = pl.DataFrame(
        [
            {
                "side": "down",
                "candidate_name": "down_none_v1",
                "router_pred_batch_id": 10,
                "base_positive_rate": 0.2,
                "predicted_positive_rate": 0.01,
                "precision_lift": 2.0,
                "false_discovery_rate": 0.1,
                "active_window": True,
                "high_false_positive_window": False,
            },
            {
                "side": "down",
                "candidate_name": "down_none_v1",
                "router_pred_batch_id": 10,
                "base_positive_rate": 0.6,
                "predicted_positive_rate": 0.02,
                "precision_lift": 0.8,
                "false_discovery_rate": 0.7,
                "active_window": True,
                "high_false_positive_window": True,
            },
        ]
    )

    out = normalize_validation_window_context(frame).row(0, named=True)

    assert out["validation_batch_count_observed"] == 2
    assert out["validation_batch_base_rate_range"] == pytest.approx(0.4)
    assert out["validation_batch_active_rate_observed"] == 1.0
    assert out["validation_batch_high_fpr_rate"] == 0.5


def test_selected_feature_context_summarizes_train_only_selector_profile() -> None:
    frame = pl.DataFrame(
        [
            {
                "side": "down",
                "candidate_name": "down_none_v1",
                "router_pred_batch_id": 10,
                "abs_coefficient": 2.0,
                "feature_std_train": 0.5,
                "final_status": "selected",
            },
            {
                "side": "down",
                "candidate_name": "down_none_v1",
                "router_pred_batch_id": 10,
                "abs_coefficient": 1.0,
                "feature_std_train": 0.25,
                "final_status": "selected",
            },
        ]
    )

    out = normalize_selected_feature_context(frame).row(0, named=True)

    assert out["selected_feature_rows"] == 2
    assert out["selected_abs_coef_sum"] == 3.0
    assert out["selected_top1_abs_coef_share"] == pytest.approx(2.0 / 3.0)
    assert out["selected_feature_train_std_max"] == 0.5


def test_prior_rpf_context_feature_selection_uses_family_prefixes() -> None:
    selected = select_prior_rpf_context_features(
        (
            "rpf_vol_a",
            "rpf_vol_b",
            "rpf_room_a",
            "rpf_liq_a",
            "unrelated_feature",
        ),
        max_features_per_family=1,
    )

    assert selected["volatility_state"] == ("rpf_vol_a",)
    assert selected["structural_room"] == ("rpf_room_a",)
    assert selected["liquidity_volume_pressure"] == ("rpf_liq_a",)
    assert "unrelated_feature" not in {feature for values in selected.values() for feature in values}


def test_prior_rpf_context_excludes_current_prediction_batch() -> None:
    assert prior_batch_ids((8, 9, 10, 11), pred_batch_id=10, lookback=3) == (8, 9)

    context = aggregate_prior_rpf_context(
        pred_batch_ids=(10,),
        all_batch_ids=(8, 9, 10, 11),
        batch_summaries={
            8: {"volatility_state__feature_count": 2, "volatility_state__mean_abs": 1.0, "volatility_state__mean": 0.1},
            9: {"volatility_state__feature_count": 2, "volatility_state__mean_abs": 2.0, "volatility_state__mean": 0.2},
            10: {
                "volatility_state__feature_count": 2,
                "volatility_state__mean_abs": 100.0,
                "volatility_state__mean": 10.0,
            },
        },
        lookbacks=(20,),
        families=("volatility_state",),
    ).row(0, named=True)

    assert context["router_pred_batch_id"] == 10
    assert context["prior_rpf_l20_volatility_state_available_batches"] == 2
    assert context["prior_rpf_l20_volatility_state_mean_abs"] == pytest.approx(1.5)
    assert context["prior_rpf_l20_volatility_state_mean"] == pytest.approx(0.15)


def test_transfer_diagnostic_handles_inactive_windows(tmp_path: Path) -> None:
    run = tmp_path / "run"
    _write_router_fixture(
        run,
        block_batch=300,
        predicted_positive_count=0,
        true_positive_count=0,
        false_positive_count=0,
        positive_count=5,
        rows=10,
    )

    transfer = build_candidate_transfer_table(
        [DiagnosticInput(run, "only", "comparison_test")],
        candidate_names=("down_none_v1",),
    )
    row = transfer.row(0, named=True)

    assert row["candidate_active"] is False
    assert row["candidate_good"] is False
    assert row["candidate_bad"] is False
    assert active_window_comparison_from_transfer_table(transfer).height == 0


def _write_router_fixture(
    run: Path,
    *,
    block_batch: int,
    predicted_positive_count: int,
    true_positive_count: int,
    false_positive_count: int,
    positive_count: int,
    rows: int,
) -> None:
    run.mkdir(parents=True, exist_ok=True)
    precision = true_positive_count / predicted_positive_count if predicted_positive_count else None
    fdr = false_positive_count / predicted_positive_count if predicted_positive_count else None
    base_rate = positive_count / rows if rows else None
    lift = precision / base_rate if precision is not None and base_rate else None
    pl.DataFrame(
        [
            {
                "side": "down",
                "candidate_name": "down_none_v1",
                "diagnostic": False,
                "status": "ok",
                "candidate_passed_validation": True,
                "candidate_fail_reasons": "",
                "router_step_idx": block_batch,
                "router_pred_batch_id": block_batch,
                "rows": rows,
                "positive_count": positive_count,
                "negative_count": rows - positive_count,
                "predicted_positive_count": predicted_positive_count,
                "true_positive_count": true_positive_count,
                "false_positive_count": false_positive_count,
                "false_negative_count": max(0, positive_count - true_positive_count),
                "true_negative_count": max(0, rows - positive_count - false_positive_count),
                "precision": precision,
                "false_discovery_rate": fdr,
                "base_positive_rate": base_rate,
                "precision_lift": lift,
                "active_window": predicted_positive_count > 0,
                "selected_feature_count": 40,
                "threshold": 0.1,
                "threshold_quantile": 0.95,
                "max_signals_per_batch": 3,
                "score_mean": 0.01,
                "score_std": 0.02,
                "batch_state_gate_probability": 0.8,
                "batch_state_gate_passed": True,
            }
        ],
        infer_schema_length=None,
    ).write_parquet(run / "candidate_prediction_window_metrics.parquet")
    pl.DataFrame(
        [
            {
                "side": "down",
                "candidate_name": "down_none_v1",
                "diagnostic": False,
                "status": "ok",
                "passed_validation": True,
                "fail_reasons": "",
                "step_idx": block_batch,
                "pred_batch_id": block_batch,
                "validation_ranked_signal_quality": 1.0,
                "validation_precision_lift": 1.5,
                "validation_false_discovery_rate": 0.2,
                "validation_predicted_positive_count": 3,
                "sequence_feature_count": 0,
                "candidate_config_json": "{}",
            }
        ],
        infer_schema_length=None,
    ).write_parquet(run / "candidate_validation_metrics.parquet")
    pl.DataFrame(
        [
            {
                "side": "down",
                "candidate_name": "down_none_v1",
                "diagnostic": False,
                "candidate_status": "ok",
                "candidate_passed_validation": True,
                "candidate_fail_reasons": "",
                "router_step_idx": block_batch,
                "router_pred_batch_id": block_batch,
                "rank_score": 0.05,
                "threshold": 0.10,
            },
            {
                "side": "down",
                "candidate_name": "down_none_v1",
                "diagnostic": False,
                "candidate_status": "ok",
                "candidate_passed_validation": True,
                "candidate_fail_reasons": "",
                "router_step_idx": block_batch,
                "router_pred_batch_id": block_batch,
                "rank_score": 0.20,
                "threshold": 0.10,
            },
        ],
        infer_schema_length=None,
    ).write_parquet(run / "candidate_validation_scores.parquet")
    pl.DataFrame(
        [
            {
                "side": "down",
                "candidate_name": "down_none_v1",
                "diagnostic": False,
                "candidate_status": "ok",
                "candidate_passed_validation": True,
                "candidate_fail_reasons": "",
                "router_step_idx": block_batch,
                "router_pred_batch_id": block_batch,
                "base_positive_rate": 0.2,
                "predicted_positive_rate": 0.01,
                "precision_lift": 2.0,
                "false_discovery_rate": 0.0,
                "active_window": True,
                "high_false_positive_window": False,
            },
            {
                "side": "down",
                "candidate_name": "down_none_v1",
                "diagnostic": False,
                "candidate_status": "ok",
                "candidate_passed_validation": True,
                "candidate_fail_reasons": "",
                "router_step_idx": block_batch,
                "router_pred_batch_id": block_batch,
                "base_positive_rate": 0.6,
                "predicted_positive_rate": 0.02,
                "precision_lift": 0.8,
                "false_discovery_rate": 0.5,
                "active_window": True,
                "high_false_positive_window": True,
            },
        ],
        infer_schema_length=None,
    ).write_parquet(run / "candidate_validation_window_metrics.parquet")
    pl.DataFrame(
        [
            {
                "side": "down",
                "candidate_name": "down_none_v1",
                "diagnostic": False,
                "candidate_status": "ok",
                "candidate_passed_validation": True,
                "candidate_fail_reasons": "",
                "router_step_idx": block_batch,
                "router_pred_batch_id": block_batch,
                "feature": "f1",
                "abs_coefficient": 2.0,
                "feature_std_train": 0.5,
                "final_status": "selected",
            },
            {
                "side": "down",
                "candidate_name": "down_none_v1",
                "diagnostic": False,
                "candidate_status": "ok",
                "candidate_passed_validation": True,
                "candidate_fail_reasons": "",
                "router_step_idx": block_batch,
                "router_pred_batch_id": block_batch,
                "feature": "f2",
                "abs_coefficient": 1.0,
                "feature_std_train": 0.25,
                "final_status": "selected",
            },
        ],
        infer_schema_length=None,
    ).write_parquet(run / "selected_features.parquet")
    pl.DataFrame(
        [
            {
                "side": "down",
                "candidate_name": "down_none_v1",
                "router_pred_batch_id": block_batch,
                "selection_mode": "prequential_reliability_v1",
                "selection_rejected_reason": None,
                "reliability_precision_lift": 1.3,
                "reliability_false_discovery_rate": 0.2,
            }
        ],
        infer_schema_length=None,
    ).write_parquet(run / "candidate_selection_audit.parquet")
    pl.DataFrame(
        [
            {
                "side": "down",
                "pred_batch_id": block_batch,
                "past_20_batch_positive_rate_mean": 0.3,
                "past_60_batch_positive_rate_mean": 0.4,
                "current_validation_positive_rate": 0.25,
                "current_validation_signal_rate": 0.05,
                "prediction_batch_positive_rate": base_rate,
            }
        ],
        infer_schema_length=None,
    ).write_parquet(run / "batch_regime_diagnostics.parquet")
