from __future__ import annotations

import polars as pl
import pytest

from regression_feature_engineering.walkforward.rank_signal_row_rule_bank import (
    RowRule,
    RowRuleEligibilityConfig,
    RowRuleReliabilityConfig,
    binary_auc_score,
    build_forward_folds,
    chronological_source_blocks,
    compare_fold_summary_with_raw,
    compare_overall_summary_with_raw,
    filter_eligible_row_rules,
    limit_rules_per_candidate,
    replay_rules_union,
    recent_shadow_history_rows,
    row_rule_eligibility_row,
    row_selection_score,
    rule_reliability_rows,
    row_rule_feature_family,
    select_prequential_reliable_rules,
    train_feature_auc,
    train_row_rules,
)


def test_chronological_source_blocks_sorts_offsets_to_latest() -> None:
    frame = pl.DataFrame({"source_block": ["latest", "offset240", "middle", "offset360"]})

    assert chronological_source_blocks(frame) == ["offset360", "offset240", "middle", "latest"]


def test_chronological_source_blocks_sorts_router_block_labels() -> None:
    frame = pl.DataFrame({"source_block": ["block002", "block000", "block001"]})

    assert chronological_source_blocks(frame) == ["block000", "block001", "block002"]


def test_build_forward_folds_uses_prior_blocks_only() -> None:
    folds = build_forward_folds(
        ["offset360", "offset240", "middle", "latest"],
        min_train_blocks=1,
        rolling_train_blocks=1,
    )

    assert folds == [
        (0, ["offset360"], "offset240"),
        (1, ["offset240"], "middle"),
        (2, ["middle"], "latest"),
    ]


def test_row_rule_eligibility_rejects_weak_rule() -> None:
    rule = _rule(train_accepted_rows=4, train_tp=2, train_fp=2, train_precision=0.5, train_lift=1.0)
    config = RowRuleEligibilityConfig(
        min_train_signals=5,
        min_train_precision=0.65,
        min_train_precision_lcb=0.4,
        min_train_lift=1.2,
        max_train_false_discovery_rate=0.35,
        max_train_accepted_rate=0.5,
        lcb_z=1.0,
    )

    row = row_rule_eligibility_row(rule, config)

    assert row["rule_eligible"] is False
    assert "low_train_signals" in row["rule_reject_reasons"]
    assert "low_train_precision" in row["rule_reject_reasons"]
    assert "high_train_fdr" in row["rule_reject_reasons"]


def test_train_row_rules_finds_higher_good_feature() -> None:
    train = pl.DataFrame(
        [
            _row("middle", 1, 0.9, True),
            _row("middle", 2, 0.8, True),
            _row("middle", 3, 0.7, True),
            _row("middle", 4, 0.1, False),
            _row("middle", 5, 0.2, False),
            _row("middle", 6, 0.3, False),
        ]
    )

    rules = train_row_rules(
        train,
        feature_columns=["score"],
        fold_idx=0,
        train_blocks=["middle"],
        test_block="latest",
        quantiles=(0.5,),
        min_train_tp_rows=2,
        min_train_fp_rows=2,
    )

    best = rules[0]
    assert best.feature == "score"
    assert best.direction == "higher_good"
    assert best.train_precision > 0.5


def test_replay_rules_union_deduplicates_rows() -> None:
    test = pl.DataFrame(
        [
            _row("latest", 1, 0.9, True),
            _row("latest", 2, 0.8, False),
        ]
    )
    rules = [
        _rule(feature="score", direction="higher_good", threshold=0.5),
        _rule(feature="score", direction="higher_good", threshold=0.7),
    ]

    accepted = replay_rules_union(test, rules)

    assert accepted.height == 2
    assert int(accepted["signal_tp"].sum()) == 1
    assert int(accepted["signal_fp"].sum()) == 1


def test_filter_eligible_row_rules_keeps_strong_rule() -> None:
    weak = _rule(feature="weak", train_accepted_rows=5, train_tp=2, train_fp=3, train_precision=0.4, train_lift=0.8)
    strong = _rule(feature="strong", train_accepted_rows=10, train_tp=8, train_fp=2, train_precision=0.8, train_lift=1.6)
    eligible, audit = filter_eligible_row_rules(
        [weak, strong],
        RowRuleEligibilityConfig(
            min_train_signals=5,
            min_train_precision=0.65,
            min_train_precision_lcb=0.3,
            min_train_lift=1.2,
            max_train_false_discovery_rate=0.35,
            max_train_accepted_rate=0.8,
            lcb_z=1.0,
        ),
    )

    assert [rule.feature for rule in eligible] == ["strong"]
    assert {row["feature"]: row["rule_eligible"] for row in audit} == {"weak": False, "strong": True}


def test_filter_eligible_row_rules_can_restrict_rule_direction() -> None:
    higher = _rule(feature="higher", direction="higher_good")
    lower = _rule(feature="lower", direction="lower_good")

    eligible, audit = filter_eligible_row_rules(
        [higher, lower],
        RowRuleEligibilityConfig(
            min_train_signals=5,
            min_train_precision=0.65,
            min_train_precision_lcb=0.3,
            min_train_lift=1.2,
            max_train_false_discovery_rate=0.35,
            max_train_accepted_rate=0.8,
            allowed_directions=("higher_good",),
        ),
    )

    assert [rule.feature for rule in eligible] == ["higher"]
    reasons = {row["feature"]: row["rule_reject_reasons"] for row in audit}
    assert reasons["higher"] == ""
    assert "direction_not_allowed" in reasons["lower"]


def test_limit_rules_per_candidate_keeps_top_scoring_rule() -> None:
    lower = _rule(feature="lower", train_precision=0.7, train_lift=1.4)
    higher = _rule(feature="higher", train_precision=0.9, train_lift=1.8)
    higher = RowRule(**{**higher.__dict__, "rule_score": 10.0})
    lower = RowRule(**{**lower.__dict__, "rule_score": 1.0})

    selected = limit_rules_per_candidate([lower, higher], max_rules_per_candidate=1)

    assert [rule.feature for rule in selected] == ["higher"]


def test_binary_auc_score_handles_directional_separation() -> None:
    y = pl.Series([False, False, True, True]).to_numpy()
    values = pl.Series([0.1, 0.2, 0.8, 0.9]).to_numpy()

    assert binary_auc_score(y, values) == 1.0
    assert binary_auc_score(y, -values) == 0.0


def test_train_row_rules_records_feature_auc_direction() -> None:
    train = pl.DataFrame(
        [
            _row("middle", 1, 0.9, True),
            _row("middle", 2, 0.8, True),
            _row("middle", 3, 0.2, False),
            _row("middle", 4, 0.1, False),
        ]
    )

    auc = train_feature_auc(train, ["score"], train["signal_tp"].to_numpy())
    rules = train_row_rules(
        train,
        feature_columns=["score"],
        fold_idx=0,
        train_blocks=["middle"],
        test_block="latest",
        quantiles=(0.5,),
        min_train_tp_rows=2,
        min_train_fp_rows=2,
    )

    assert auc["score"] == (1.0, 1.0, "higher_good")
    assert rules[0].feature_auc == 1.0
    assert rules[0].feature_auc_direction == "higher_good"
    assert rules[0].direction_agreement is True


def test_directional_lcb_selection_penalizes_feature_direction_disagreement() -> None:
    narrow_disagree = RowRule(
        **{
            **_rule(feature="narrow").__dict__,
            "rule_score": 10.0,
            "feature_auc_abs": 0.60,
            "feature_auc_direction": "lower_good",
            "direction_agreement": False,
            "directional_lcb_score": 0.20,
        }
    )
    broader_agree = RowRule(
        **{
            **_rule(feature="broader").__dict__,
            "rule_score": 1.0,
            "feature_auc_abs": 0.60,
            "feature_auc_direction": "higher_good",
            "direction_agreement": True,
            "directional_lcb_score": 0.80,
        }
    )

    selected = limit_rules_per_candidate(
        [narrow_disagree, broader_agree],
        max_rules_per_candidate=1,
        selection_score="directional_lcb_v1",
    )

    assert row_selection_score(selected[0], "directional_lcb_v1") == 0.80
    assert [rule.feature for rule in selected] == ["broader"]


def test_rule_reliability_rows_aggregate_prior_shadow_per_feature_direction() -> None:
    rows = [
        _shadow_rule_row("row_rpf_a_mean", "higher_good", True, fold_idx=0),
        _shadow_rule_row("row_rpf_a_mean", "higher_good", True, fold_idx=0),
        _shadow_rule_row("row_rpf_a_mean", "higher_good", False, fold_idx=0),
        _shadow_rule_row("row_rpf_b_mean", "lower_good", False, fold_idx=0),
    ]

    reliability = rule_reliability_rows(rows, RowRuleReliabilityConfig(min_signals=1))

    by_key = {(row["feature"], row["direction"]): row for row in reliability}
    assert by_key[("row_rpf_a_mean", "higher_good")]["signals"] == 3
    assert by_key[("row_rpf_a_mean", "higher_good")]["tp"] == 2
    assert by_key[("row_rpf_a_mean", "higher_good")]["fp"] == 1
    assert by_key[("row_rpf_b_mean", "lower_good")]["tp"] == 0


def test_recent_shadow_history_rows_keeps_last_matured_folds_only() -> None:
    rows = [
        _shadow_rule_row("row_rpf_a_mean", "higher_good", True, fold_idx=0),
        _shadow_rule_row("row_rpf_a_mean", "higher_good", False, fold_idx=1),
        _shadow_rule_row("row_rpf_a_mean", "higher_good", True, fold_idx=2),
        _shadow_rule_row("row_rpf_b_mean", "lower_good", True, fold_idx=2),
        _shadow_rule_row("row_rpf_a_mean", "higher_good", False, fold_idx=3),
    ]

    recent = recent_shadow_history_rows(rows, lookback_folds=2)

    assert [int(row["fold_idx"]) for row in recent] == [2, 2, 3]
    assert recent_shadow_history_rows(rows, lookback_folds=0) == rows


def test_prequential_reliability_no_signal_without_history() -> None:
    rules = [_rule(feature="score")]

    selected, audit = select_prequential_reliable_rules(
        rules,
        reliability_rows=[],
        config=RowRuleReliabilityConfig(warmup_mode="no_signal"),
        max_rules_per_candidate=1,
        fallback_selection_score="directional_lcb_v1",
    )

    assert selected == []
    assert audit[0]["selected"] is False
    assert "no_reliability_history" in audit[0]["selection_reject_reasons"]


def test_prequential_reliability_selects_prior_reliable_feature_direction() -> None:
    reliable = _rule(feature="row_rpf_reliable_mean", direction="higher_good")
    unreliable = _rule(feature="row_rpf_unreliable_mean", direction="higher_good")
    history = [
        _shadow_rule_row("row_rpf_reliable_mean", "higher_good", True, fold_idx=0),
        _shadow_rule_row("row_rpf_reliable_mean", "higher_good", True, fold_idx=0),
        _shadow_rule_row("row_rpf_reliable_mean", "higher_good", True, fold_idx=0),
        _shadow_rule_row("row_rpf_reliable_mean", "higher_good", False, fold_idx=0),
        _shadow_rule_row("row_rpf_unreliable_mean", "higher_good", False, fold_idx=0),
        _shadow_rule_row("row_rpf_unreliable_mean", "higher_good", False, fold_idx=0),
        _shadow_rule_row("row_rpf_unreliable_mean", "higher_good", True, fold_idx=0),
        _shadow_rule_row("row_rpf_unreliable_mean", "higher_good", False, fold_idx=0),
    ]
    reliability = rule_reliability_rows(
        history,
        RowRuleReliabilityConfig(min_signals=1, min_precision_lcb=0.0, max_false_discovery_rate=1.0),
    )

    selected, audit = select_prequential_reliable_rules(
        [unreliable, reliable],
        reliability_rows=reliability,
        config=RowRuleReliabilityConfig(min_signals=4, min_precision_lcb=0.0, max_false_discovery_rate=0.5),
        max_rules_per_candidate=1,
        fallback_selection_score="directional_lcb_v1",
    )

    assert [rule.feature for rule in selected] == ["row_rpf_reliable_mean"]
    assert {row["feature"]: row["selected"] for row in audit} == {
        "row_rpf_unreliable_mean": False,
        "row_rpf_reliable_mean": True,
    }


def test_row_rule_feature_family_strips_summary_suffix() -> None:
    assert row_rule_feature_family("row_rpf_cross_asset_context_mean_abs") == "cross_asset_context"
    assert row_rule_feature_family("rank_score") == "rank_score"


def test_compare_fold_summary_with_raw_computes_lift_and_retention() -> None:
    raw = pl.DataFrame(
        [
            _row("latest", 1, 0.9, True),
            _row("latest", 2, 0.8, True),
            _row("latest", 3, 0.7, False),
            _row("latest", 4, 0.6, False),
        ]
    )
    fold_summary = [
        {
            "fold_idx": 0,
            "train_blocks": "middle",
            "test_block": "latest",
            "side": "down",
            "candidate_name": "down_rocket_16_diag_v1",
            "signals": 2,
            "tp": 2,
            "fp": 0,
            "precision": 1.0,
            "false_discovery_rate": 0.0,
        }
    ]

    comparison = compare_fold_summary_with_raw(raw, fold_summary)

    assert comparison[0]["raw_signals"] == 4
    assert comparison[0]["raw_precision"] == pytest.approx(0.5)
    assert comparison[0]["precision_lift_vs_raw"] == pytest.approx(2.0)
    assert comparison[0]["signal_retention_vs_raw"] == pytest.approx(0.5)


def test_compare_overall_summary_with_raw_uses_only_selected_test_blocks() -> None:
    raw = pl.DataFrame(
        [
            _row("middle", 1, 0.9, True),
            _row("middle", 2, 0.8, False),
            _row("latest", 3, 0.7, True),
            _row("latest", 4, 0.6, True),
            _row("ignored", 5, 0.1, False),
            _row("ignored", 6, 0.2, False),
        ]
    )
    fold_summary = [
        {
            "fold_idx": 0,
            "train_blocks": "middle",
            "test_block": "latest",
            "side": "down",
            "candidate_name": "down_rocket_16_diag_v1",
            "signals": 1,
            "tp": 1,
            "fp": 0,
            "precision": 1.0,
            "false_discovery_rate": 0.0,
        }
    ]
    overall_summary = [
        {
            "side": "down",
            "candidate_name": "down_rocket_16_diag_v1",
            "signals": 1,
            "tp": 1,
            "fp": 0,
            "precision": 1.0,
            "false_discovery_rate": 0.0,
        }
    ]

    comparison = compare_overall_summary_with_raw(raw, fold_summary, overall_summary)

    assert comparison[0]["raw_signals"] == 2
    assert comparison[0]["raw_precision"] == pytest.approx(1.0)
    assert comparison[0]["raw_baseline_blocks"] == "latest"


def _row(block: str, row_id: int, score: float, tp: bool) -> dict[str, object]:
    return {
        "source_run": "run",
        "source_block": block,
        "side": "down",
        "candidate_name": "down_rocket_16_diag_v1",
        "router_step_idx": 1,
        "router_pred_batch_id": 1,
        "timestamp": row_id,
        "batch_id": 1,
        "score": score,
        "signal_tp": bool(tp),
        "signal_fp": not bool(tp),
    }


def _shadow_rule_row(feature: str, direction: str, tp: bool, *, fold_idx: int) -> dict[str, object]:
    return {
        "fold_idx": fold_idx,
        "side": "down",
        "candidate_name": "down_rocket_16_diag_v1",
        "feature": feature,
        "feature_family": row_rule_feature_family(feature),
        "direction": direction,
        "signal_tp": bool(tp),
        "signal_fp": not bool(tp),
    }


def _rule(
    *,
    feature: str = "score",
    direction: str = "higher_good",
    threshold: float = 0.5,
    train_accepted_rows: int = 10,
    train_tp: int = 8,
    train_fp: int = 2,
    train_precision: float = 0.8,
    train_lift: float = 1.6,
) -> RowRule:
    return RowRule(
        fold_idx=0,
        train_blocks="middle",
        test_block="latest",
        side="down",
        candidate_name="down_rocket_16_diag_v1",
        feature=feature,
        direction=direction,
        threshold=threshold,
        train_rows=20,
        train_accepted_rows=train_accepted_rows,
        train_tp=train_tp,
        train_fp=train_fp,
        train_precision=train_precision,
        train_base_precision=0.5,
        train_lift=train_lift,
        train_false_discovery_rate=train_fp / train_accepted_rows,
        train_precision_lcb=0.6,
        train_accepted_rate=train_accepted_rows / 20,
        rule_score=1.0,
    )
