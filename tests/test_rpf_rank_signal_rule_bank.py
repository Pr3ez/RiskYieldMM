from __future__ import annotations

from argparse import Namespace
from pathlib import Path

import polars as pl
import pytest

from regression_feature_engineering.walkforward.rank_signal_meta_router_simulator import CandidateRule
from regression_feature_engineering.walkforward.rank_signal_rule_bank import (
    RuleEligibilityConfig,
    build_forward_folds,
    build_side_rule_eligibility,
    filter_eligible_rules,
    joined_safe_context_with_labels,
    parse_block_runs,
    rule_eligibility_row,
    wilson_lower_bound,
)


def test_build_forward_folds_uses_prior_blocks_only() -> None:
    folds = build_forward_folds(
        ["b0", "b1", "b2", "b3"],
        min_train_blocks=1,
        rolling_train_blocks=0,
    )

    assert folds == [
        (0, ["b0"], "b1"),
        (1, ["b0", "b1"], "b2"),
        (2, ["b0", "b1", "b2"], "b3"),
    ]


def test_build_forward_folds_can_use_rolling_train_blocks() -> None:
    folds = build_forward_folds(
        ["b0", "b1", "b2", "b3"],
        min_train_blocks=2,
        rolling_train_blocks=1,
    )

    assert folds == [
        (0, ["b1"], "b2"),
        (1, ["b2"], "b3"),
    ]


def test_parse_block_runs_requires_named_existing_paths(tmp_path: Path) -> None:
    run = tmp_path / "router_run"
    run.mkdir()

    blocks = parse_block_runs([f"older.block={run}", f"latest={run}"])

    assert [block.source_block for block in blocks] == ["older_block", "latest"]
    assert all(block.source_role == "chronological_block" for block in blocks)

    with pytest.raises(ValueError, match="name=path"):
        parse_block_runs([str(run)])


def test_joined_safe_context_excludes_current_labels_but_adds_train_labels() -> None:
    transfer = pl.DataFrame(
        [
            {
                "source_block": "b0",
                "source_role": "chronological_block",
                "source_run": "run",
                "side": "up",
                "candidate_name": "up_none_v1",
                "router_step_idx": 1,
                "router_pred_batch_id": 101,
                "score_mean": 0.1,
                "threshold": 0.2,
                "predicted_positive_count": 2,
                "true_positive_count": 2,
                "false_positive_count": 0,
                "positive_count": 4,
                "negative_count": 6,
                "rows": 10,
                "precision": 1.0,
                "false_discovery_rate": 0.0,
                "precision_lift": 2.5,
                "base_positive_rate": 0.4,
                "candidate_active": True,
                "candidate_good": True,
                "candidate_bad": False,
                "candidate_good_reason": "fixture",
            }
        ]
    )

    joined = joined_safe_context_with_labels(transfer)

    assert "score_mean" in joined.columns
    assert "precision" in joined.columns
    safe_label_leaks = {"precision", "true_positive_count", "rows"} & set(
        transfer.select(["score_mean", "threshold"]).columns
    )
    assert not safe_label_leaks
    assert joined["candidate_good"].to_list() == [True]


def test_rule_eligibility_rejects_weak_train_rule() -> None:
    rule = _candidate_rule(train_signals=8, train_precision=0.5, train_lift=1.1, train_fdr=0.5)
    config = RuleEligibilityConfig(
        min_train_signals=10,
        min_train_precision=0.65,
        min_train_precision_lcb=0.5,
        min_train_lift=1.4,
        max_train_false_discovery_rate=0.35,
        max_train_active_rate=0.2,
        lcb_z=1.0,
    )

    row = rule_eligibility_row(rule, config)

    assert row["rule_eligible"] is False
    assert "low_train_signals" in row["rule_reject_reasons"]
    assert "low_train_precision" in row["rule_reject_reasons"]
    assert "high_train_fdr" in row["rule_reject_reasons"]


def test_filter_eligible_rules_keeps_only_conservative_rule() -> None:
    weak = _candidate_rule(candidate_name="weak", train_signals=8, train_precision=0.5, train_lift=1.1, train_fdr=0.5)
    strong = _candidate_rule(
        candidate_name="strong",
        train_signals=30,
        train_precision=0.8,
        train_lift=1.8,
        train_fdr=0.2,
        train_windows=120,
        train_accepted_windows=8,
    )
    config = RuleEligibilityConfig(
        min_train_signals=10,
        min_train_precision=0.65,
        min_train_precision_lcb=0.5,
        min_train_lift=1.4,
        max_train_false_discovery_rate=0.35,
        max_train_active_rate=0.2,
        lcb_z=1.0,
    )

    eligible, rows = filter_eligible_rules([weak, strong], config)

    assert [rule.candidate_name for rule in eligible] == ["strong"]
    assert len(rows) == 2
    assert {row["candidate_name"]: row["rule_eligible"] for row in rows} == {"weak": False, "strong": True}


def test_filter_eligible_rules_can_use_side_specific_gates() -> None:
    up_rule = _candidate_rule(
        side="up",
        candidate_name="up_sparse",
        train_signals=3,
        train_precision=1.0,
        train_lift=2.0,
        train_fdr=0.0,
        train_accepted_windows=3,
    )
    down_rule = _candidate_rule(
        side="down",
        candidate_name="down_too_sparse",
        train_signals=3,
        train_precision=1.0,
        train_lift=2.0,
        train_fdr=0.0,
        train_accepted_windows=3,
    )
    default_config = RuleEligibilityConfig(
        min_train_signals=3,
        min_train_precision=0.65,
        min_train_precision_lcb=0.35,
        min_train_lift=1.4,
        max_train_false_discovery_rate=0.35,
        max_train_active_rate=0.5,
        lcb_z=1.0,
    )
    down_config = RuleEligibilityConfig(
        min_train_signals=10,
        min_train_precision=0.65,
        min_train_precision_lcb=0.5,
        min_train_lift=1.4,
        max_train_false_discovery_rate=0.35,
        max_train_active_rate=0.5,
        lcb_z=1.0,
    )

    eligible, rows = filter_eligible_rules(
        [up_rule, down_rule],
        default_config,
        side_configs={"down": down_config},
    )

    assert [rule.candidate_name for rule in eligible] == ["up_sparse"]
    by_name = {row["candidate_name"]: row for row in rows}
    assert by_name["up_sparse"]["rule_eligible"] is True
    assert by_name["down_too_sparse"]["rule_eligible"] is False
    assert by_name["down_too_sparse"]["rule_min_train_signals"] == 10
    assert "low_train_signals" in by_name["down_too_sparse"]["rule_reject_reasons"]


def test_build_side_rule_eligibility_uses_global_defaults_for_unspecified_fields() -> None:
    default_config = RuleEligibilityConfig(
        min_train_signals=3,
        min_train_precision=0.65,
        min_train_precision_lcb=0.35,
        min_train_lift=1.4,
        max_train_false_discovery_rate=0.35,
        max_train_active_rate=0.5,
        lcb_z=1.0,
    )
    args = Namespace(
        up_rule_min_train_signals=None,
        up_rule_min_train_precision=None,
        up_rule_min_train_precision_lcb=None,
        up_rule_min_train_lift=None,
        up_rule_max_train_fdr=None,
        up_rule_max_train_active_rate=None,
        up_rule_lcb_z=None,
        down_rule_min_train_signals=10,
        down_rule_min_train_precision=None,
        down_rule_min_train_precision_lcb=0.5,
        down_rule_min_train_lift=None,
        down_rule_max_train_fdr=None,
        down_rule_max_train_active_rate=None,
        down_rule_lcb_z=None,
    )

    configs = build_side_rule_eligibility(args, default_config)

    assert set(configs) == {"down"}
    assert configs["down"].min_train_signals == 10
    assert configs["down"].min_train_precision == pytest.approx(default_config.min_train_precision)
    assert configs["down"].min_train_precision_lcb == pytest.approx(0.5)
    assert configs["down"].max_train_active_rate == pytest.approx(default_config.max_train_active_rate)


def test_wilson_lower_bound_matches_reference_value() -> None:
    assert wilson_lower_bound(8, 10, z=1.0) == pytest.approx(0.6490775, rel=1e-5)
    assert wilson_lower_bound(0, 0, z=1.0) is None


def _candidate_rule(
    *,
    side: str = "up",
    candidate_name: str = "candidate",
    train_signals: int,
    train_precision: float,
    train_lift: float,
    train_fdr: float,
    train_windows: int = 100,
    train_accepted_windows: int = 10,
) -> CandidateRule:
    return CandidateRule(
        side=side,
        candidate_name=candidate_name,
        feature="score_mean",
        direction="higher_good",
        threshold=0.1,
        train_score=1.0,
        train_windows=train_windows,
        train_good_rows=2,
        train_bad_rows=2,
        train_accepted_windows=train_accepted_windows,
        train_signals=train_signals,
        train_precision=train_precision,
        train_lift=train_lift,
        train_false_discovery_rate=train_fdr,
        separator_best_auc=0.7,
        separator_score=0.5,
    )
