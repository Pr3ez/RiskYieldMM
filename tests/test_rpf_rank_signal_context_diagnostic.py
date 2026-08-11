from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest

from regression_feature_engineering.walkforward.rank_signal_context_diagnostic import (
    OUTCOME_COLUMNS,
    build_context_diagnostic,
)


def test_context_diagnostic_separates_safe_context_from_outcomes(tmp_path: Path) -> None:
    good_run = tmp_path / "good_router"
    bad_run = tmp_path / "bad_router"
    _write_router_fixture(
        good_run,
        offset=0,
        block_idx=4,
        predicted_positive_count=5,
        true_positive_count=4,
        false_positive_count=1,
        positive_count=20,
        rows=100,
        feature="row_rpf_vol_mean_abs",
        direction="higher_good",
        train_lift=2.0,
    )
    _write_router_fixture(
        bad_run,
        offset=480,
        block_idx=4,
        predicted_positive_count=5,
        true_positive_count=1,
        false_positive_count=4,
        positive_count=25,
        rows=100,
        feature="row_rpf_rejection_chop_mean_abs",
        direction="higher_good",
        train_lift=1.3,
    )

    context, outcomes, comparison = build_context_diagnostic(
        router_runs=(good_run, bad_run),
        side="down",
        candidate_name="down_rocket_16_diag_v1",
        include_zero_signal_blocks=False,
        good_min_precision=0.60,
        good_min_precision_lift=1.20,
        bad_max_false_discovery_rate=0.50,
    )

    assert context.height == 2
    assert outcomes.height == 2
    assert comparison.height > 0
    assert not (set(context.columns) & OUTCOME_COLUMNS)
    assert "feature_family" in context.columns
    assert "train_lift" in context.columns

    labels = {row["source_block"]: row for row in outcomes.to_dicts()}
    assert labels["latest"]["good_block"] is True
    assert labels["latest"]["bad_block"] is False
    assert labels["offset480"]["good_block"] is False
    assert labels["offset480"]["bad_block"] is True

    numeric = comparison.filter((pl.col("comparison_type") == "numeric") & (pl.col("feature") == "train_lift"))
    assert numeric.height == 1
    assert numeric.row(0, named=True)["delta_good_minus_bad"] == pytest.approx(0.7)


def test_context_diagnostic_can_exclude_zero_signal_blocks(tmp_path: Path) -> None:
    run = tmp_path / "router"
    _write_router_fixture(
        run,
        offset=0,
        block_idx=1,
        predicted_positive_count=0,
        true_positive_count=0,
        false_positive_count=0,
        positive_count=10,
        rows=100,
        feature="row_rpf_vol_mean_abs",
        direction="higher_good",
        train_lift=1.5,
    )

    context, outcomes, _ = build_context_diagnostic(
        router_runs=(run,),
        side="down",
        candidate_name="down_rocket_16_diag_v1",
        include_zero_signal_blocks=False,
        good_min_precision=0.60,
        good_min_precision_lift=1.20,
        bad_max_false_discovery_rate=0.50,
    )

    assert context.is_empty()
    assert outcomes.is_empty()

    context, outcomes, _ = build_context_diagnostic(
        router_runs=(run,),
        side="down",
        candidate_name="down_rocket_16_diag_v1",
        include_zero_signal_blocks=True,
        good_min_precision=0.60,
        good_min_precision_lift=1.20,
        bad_max_false_discovery_rate=0.50,
    )

    assert context.height == 1
    assert outcomes.row(0, named=True)["block_label"] == "inactive"


def _write_router_fixture(
    run: Path,
    *,
    offset: int,
    block_idx: int,
    predicted_positive_count: int,
    true_positive_count: int,
    false_positive_count: int,
    positive_count: int,
    rows: int,
    feature: str,
    direction: str,
    train_lift: float,
) -> None:
    run.mkdir(parents=True, exist_ok=True)
    precision = true_positive_count / predicted_positive_count if predicted_positive_count else None
    fdr = false_positive_count / predicted_positive_count if predicted_positive_count else None
    base_rate = positive_count / rows if rows else None
    lift = precision / base_rate if precision is not None and base_rate else None
    test_block = f"block{block_idx:03d}"
    (run / "router_config.json").write_text(
        """{
          "window_end_offset_steps": %d,
          "outer_window_count": 960,
          "selection_mode": "prequential_reliability_v1",
          "candidate_set": "pruned_reliability_v1",
          "row_rule_gate": {
            "mode": "prequential_reliability_v1",
            "output_mode": "active_down_candidate",
            "side": "down",
            "candidate_name": "down_rocket_16_diag_v1",
            "block_size": 60,
            "key": "feature_direction",
            "allowed_directions": ["higher_good"],
            "rule_selection_score": "directional_lcb_v1",
            "max_rules_per_candidate": 1,
            "reliability": {
              "min_history_folds": 1,
              "min_signals": 8,
              "min_precision_lcb": 0.55,
              "max_false_discovery_rate": 0.35,
              "lookback_folds": 3
            }
          }
        }"""
        % offset
    )
    pl.DataFrame(
        [
            {
                "side": "down",
                "block_idx": block_idx,
                "pred_batch_start": 1000 + block_idx * 60,
                "pred_batch_end": 1059 + block_idx * 60,
                "rows": rows,
                "positive_count": positive_count,
                "negative_count": rows - positive_count,
                "predicted_positive_count": predicted_positive_count,
                "true_positive_count": true_positive_count,
                "false_positive_count": false_positive_count,
                "false_negative_count": max(0, positive_count - true_positive_count),
                "true_negative_count": max(0, rows - positive_count - false_positive_count),
                "precision": precision,
                "recall": true_positive_count / positive_count if positive_count else None,
                "false_positive_rate": false_positive_count / (rows - positive_count) if rows > positive_count else None,
                "false_discovery_rate": fdr,
                "predicted_positive_rate": predicted_positive_count / rows if rows else None,
                "base_positive_rate": base_rate,
                "precision_lift": lift,
                "decision_cost": 5 * false_positive_count + max(0, positive_count - true_positive_count),
                "selected_feature_count_mean": 40.0,
                "ranked_signal_quality": 1.0,
            }
        ],
        infer_schema_length=None,
    ).write_parquet(run / "row_rule_active_block_summary.parquet")
    pl.DataFrame(
        [
            {
                "fold_idx": block_idx - 1,
                "train_blocks": "block000",
                "test_block": test_block,
                "side": "down",
                "candidate_name": "down_rocket_16_diag_v1",
                "feature": feature,
                "direction": direction,
                "threshold": 0.1,
                "train_rows": 1000,
                "train_accepted_rows": 20,
                "train_tp": 15,
                "train_fp": 5,
                "train_precision": 0.75,
                "train_base_precision": 0.30,
                "train_lift": train_lift,
                "train_false_discovery_rate": 0.25,
                "train_precision_lcb": 0.60,
                "train_accepted_rate": 0.02,
                "rule_score": 1.5,
                "feature_auc": 0.7,
                "feature_auc_abs": 0.7,
                "feature_auc_direction": direction,
                "direction_agreement": True,
                "directional_lcb_score": 1.2,
                "selected": True,
                "row_rule_selection_mode": "prequential_reliability_v1",
                "selection_score": 1.2,
                "selection_reject_reasons": "",
                "reliability_key_mode": "family_direction",
                "reliability_history_folds": 2,
                "reliability_signals": 12,
                "reliability_tp": 8,
                "reliability_fp": 4,
                "reliability_precision": 0.66,
                "reliability_precision_lcb": 0.50,
                "reliability_false_discovery_rate": 0.33,
                "reliability_score": 1.0,
                "reliability_feature_family": None,
            }
        ],
        infer_schema_length=None,
    ).write_parquet(run / "row_rule_gate_selection_audit.parquet")
    pl.DataFrame(
        [
            {
                "fold_idx": block_idx - 1,
                "train_blocks": "block000",
                "test_block": test_block,
                "side": "down",
                "candidate_name": "down_rocket_16_diag_v1",
                "signals": predicted_positive_count,
                "tp": true_positive_count,
                "fp": false_positive_count,
                "precision": precision,
                "false_discovery_rate": fdr,
                "raw_signals": predicted_positive_count + 5,
                "raw_tp": true_positive_count + 1,
                "raw_fp": false_positive_count + 4,
                "raw_precision": 0.3,
                "raw_false_discovery_rate": 0.7,
                "precision_lift_vs_raw": None,
                "signal_retention_vs_raw": None,
                "tp_retention_vs_raw": None,
                "fp_retention_vs_raw": None,
            }
        ],
        infer_schema_length=None,
    ).write_parquet(run / "row_rule_gate_fold_comparison.parquet")
