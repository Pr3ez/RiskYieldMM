from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import polars as pl
import pytest

from regression_feature_engineering.walkforward.rank_signal_router import (
    CANDIDATE_SET_PRUNED_RELIABILITY_V1,
    ROW_RULE_GATE_OUTPUT_ACTIVE_CANDIDATE,
    ROW_RULE_GATE_OUTPUT_ACTIVE_DOWN_CANDIDATE,
    ROW_RULE_GATE_PREQUENTIAL_RELIABILITY_V1,
    SELECTION_CONTEXT_RULE_V1,
    SELECTION_PREQUENTIAL_RELIABILITY_V1,
    SPECIALIST_ENTRY_DOWN_NONE_VALIDATION_QUIET_V1,
    SPECIALIST_ENTRY_OFF,
    CandidateSpec,
    ContextRule,
    ReliabilityConfig,
    RouterGateConfig,
    build_candidate_set,
    build_row_rule_active_outputs,
    candidate_selection_audit_rows,
    conflict_diagnostics,
    filter_row_rules_by_family,
    filter_candidates_by_name_allowlist,
    load_context_rules,
    parse_candidate_name_allowlist,
    reliability_state_for_candidate,
    resolve_effective_router_outputs,
    row_rule_gate_signal_frame,
    row_rule_gate_source_block_map,
    select_candidate,
    select_router_candidate,
    specialist_entry_passed,
    validation_gate_result,
    validation_metrics_with_batch_consistency,
    wilson_lower_bound,
    write_router_report,
)
from regression_feature_engineering.walkforward.rank_signal import RankTrialConfig
from regression_feature_engineering.walkforward.rank_signal_row_rule_bank import RowRule
from regression_feature_engineering.walkforward.windows import RPFWindow


def test_validation_gate_result_requires_lift_and_enough_signals() -> None:
    gates = RouterGateConfig()
    ok = {
        "predicted_positive_count": 4,
        "precision_lift": 1.25,
        "false_discovery_rate": 0.25,
        "active_window_rate": 0.2,
        "zero_signal_window_rate": 0.8,
    }
    bad = {
        "predicted_positive_count": 1,
        "precision_lift": 0.9,
        "false_discovery_rate": 0.8,
        "active_window_rate": 0.0,
        "zero_signal_window_rate": 1.0,
    }

    assert validation_gate_result(ok, gates) == (True, [])
    passed, reasons = validation_gate_result(bad, gates)

    assert passed is False
    assert "low_validation_signal_count" in reasons
    assert "low_validation_precision_lift" in reasons
    assert "high_validation_false_discovery_rate" in reasons


def test_validation_gate_result_uses_batch_consistency_metrics() -> None:
    gates = RouterGateConfig(
        min_validation_signal_count=3,
        min_validation_precision_lift=1.1,
        max_validation_false_discovery_rate=0.6,
        min_validation_active_window_rate=0.1,
        max_validation_zero_signal_window_rate=0.9,
        min_validation_active_batch_count=3,
        min_validation_lift_positive_batch_rate=0.75,
        min_validation_median_active_precision_lift=1.2,
        max_validation_median_active_false_discovery_rate=0.4,
    )
    aggregate = {
        "predicted_positive_count": 10,
        "precision_lift": 1.4,
        "false_discovery_rate": 0.4,
        "active_window_rate": 0.8,
        "zero_signal_window_rate": 0.2,
    }
    weak_batches = [
        {"active_window": True, "precision_lift": 1.5, "false_discovery_rate": 0.2},
        {"active_window": True, "precision_lift": 0.8, "false_discovery_rate": 0.7},
        {"active_window": False, "precision_lift": 0.0, "false_discovery_rate": 1.0},
    ]

    metrics = validation_metrics_with_batch_consistency(aggregate, weak_batches, gates)
    passed, reasons = validation_gate_result(metrics, gates)

    assert passed is False
    assert metrics["active_batch_count"] == 2
    assert metrics["lift_positive_batch_rate"] == pytest.approx(0.5)
    assert "low_validation_active_batch_count" in reasons
    assert "low_validation_lift_positive_batch_rate" in reasons
    assert "low_validation_median_active_precision_lift" in reasons
    assert "high_validation_median_active_false_discovery_rate" in reasons


def test_select_candidate_uses_validation_only_and_tie_breaks_by_simplicity() -> None:
    complex_candidate = {
        "passed": True,
        "sequence_feature_count": 96,
        "validation_metrics": {
            "ranked_signal_quality": 1.0,
            "precision_lift": 1.5,
            "false_discovery_rate": 0.25,
        },
    }
    simple_candidate = {
        "passed": True,
        "sequence_feature_count": 0,
        "validation_metrics": {
            "ranked_signal_quality": 1.0,
            "precision_lift": 1.5,
            "false_discovery_rate": 0.25,
        },
    }
    high_prediction_but_failed_validation = {
        "passed": False,
        "sequence_feature_count": 0,
        "validation_metrics": {
            "ranked_signal_quality": 10.0,
            "precision_lift": 5.0,
            "false_discovery_rate": 0.0,
        },
        "prediction_precision": 1.0,
    }

    selected = select_candidate([complex_candidate, simple_candidate, high_prediction_but_failed_validation])

    assert selected is simple_candidate


def test_select_candidate_returns_fallback_when_all_fail() -> None:
    weak = {
        "passed": False,
        "sequence_feature_count": 0,
        "validation_metrics": {
            "ranked_signal_quality": -1.0,
            "precision_lift": 0.9,
            "false_discovery_rate": 0.8,
        },
    }
    less_weak = {
        "passed": False,
        "sequence_feature_count": 0,
        "validation_metrics": {
            "ranked_signal_quality": 0.0,
            "precision_lift": 1.0,
            "false_discovery_rate": 0.6,
        },
    }

    selected = select_candidate([weak, less_weak])

    assert selected["selected_no_pass"] is True
    assert selected["validation_metrics"]["ranked_signal_quality"] == pytest.approx(0.0)


def test_conflict_diagnostics_resolves_by_margin() -> None:
    rows = [
        {
            "side": "up",
            "pred_batch_id": 10,
            "timestamp": "2026-01-01T00:00:00Z",
            "decision": 1,
            "rank_score": 0.8,
            "threshold": 0.5,
            "margin": 0.3,
            "selected_candidate": "up_rocket_32_v1",
        },
        {
            "side": "down",
            "pred_batch_id": 10,
            "timestamp": "2026-01-01T00:00:00Z",
            "decision": 1,
            "rank_score": 0.7,
            "threshold": 0.6,
            "margin": 0.1,
            "selected_candidate": "down_none_v1",
        },
    ]

    conflicts = conflict_diagnostics(rows)

    assert len(conflicts) == 1
    assert conflicts[0]["combined_winner"] == "up"


def test_pruned_reliability_candidate_set_contains_only_kept_candidates() -> None:
    candidates = build_candidate_set(
        CANDIDATE_SET_PRUNED_RELIABILITY_V1,
        fp_cost=5.0,
        fn_cost=1.0,
        high_target_positive_rate_threshold=0.2,
        high_false_positive_rate_threshold=0.3,
        include_diagnostic_candidates=False,
    )

    assert [candidate.name for candidate in candidates] == [
        "up_none_v1",
        "up_rocket_64_v1",
        "down_none_v1",
        "down_rocket_16_diag_v1",
    ]


def test_pruned_reliability_candidate_set_can_include_optional_down_rocket_64() -> None:
    candidates = build_candidate_set(
        CANDIDATE_SET_PRUNED_RELIABILITY_V1,
        fp_cost=5.0,
        fn_cost=1.0,
        high_target_positive_rate_threshold=0.2,
        high_false_positive_rate_threshold=0.3,
        include_diagnostic_candidates=True,
    )

    assert "down_rocket_64_diag_v1" in {candidate.name for candidate in candidates}


def test_candidate_name_allowlist_filters_fixed_candidate_set() -> None:
    candidates = build_candidate_set(
        CANDIDATE_SET_PRUNED_RELIABILITY_V1,
        fp_cost=5.0,
        fn_cost=1.0,
        high_target_positive_rate_threshold=0.2,
        high_false_positive_rate_threshold=0.3,
        include_diagnostic_candidates=False,
    )
    allowlist = parse_candidate_name_allowlist("up_none_v1,down_rocket_16_diag_v1,up_none_v1")

    filtered = filter_candidates_by_name_allowlist(candidates, allowlist)

    assert allowlist == ("up_none_v1", "down_rocket_16_diag_v1")
    assert [candidate.name for candidate in filtered] == ["up_none_v1", "down_rocket_16_diag_v1"]


def test_candidate_name_allowlist_rejects_unknown_candidate() -> None:
    candidates = build_candidate_set(
        CANDIDATE_SET_PRUNED_RELIABILITY_V1,
        fp_cost=5.0,
        fn_cost=1.0,
        high_target_positive_rate_threshold=0.2,
        high_false_positive_rate_threshold=0.3,
        include_diagnostic_candidates=False,
    )

    with pytest.raises(ValueError, match="Unknown --candidate-name-allowlist entries"):
        filter_candidates_by_name_allowlist(candidates, ("missing_candidate",))


def test_row_rule_gate_source_block_map_uses_chronological_router_order() -> None:
    windows = [
        RPFWindow(step_idx=0, pred_pos=100, pred_batch_id=100, train_batch_ids=(), val_batch_ids=()),
        RPFWindow(step_idx=1, pred_pos=101, pred_batch_id=101, train_batch_ids=(), val_batch_ids=()),
        RPFWindow(step_idx=2, pred_pos=102, pred_batch_id=102, train_batch_ids=(), val_batch_ids=()),
    ]

    mapping = row_rule_gate_source_block_map(windows, block_size=2)

    assert mapping == {100: "block000", 101: "block000", 102: "block001"}


def test_row_rule_gate_signal_frame_keeps_only_requested_candidate_decisions(tmp_path: Path) -> None:
    windows = [
        RPFWindow(step_idx=0, pred_pos=100, pred_batch_id=100, train_batch_ids=(), val_batch_ids=()),
        RPFWindow(step_idx=1, pred_pos=101, pred_batch_id=101, train_batch_ids=(), val_batch_ids=()),
    ]
    rows = [
        _candidate_score_row(100, "down_rocket_16_diag_v1", decision=1, target_binary=1),
        _candidate_score_row(100, "down_rocket_16_diag_v1", decision=0, target_binary=1),
        _candidate_score_row(101, "down_none_v1", decision=1, target_binary=0),
        _candidate_score_row(101, "down_rocket_16_diag_v1", decision=1, target_binary=0),
    ]

    frame = row_rule_gate_signal_frame(
        rows,
        selected_outer_windows=windows,
        run_root=tmp_path,
        side="down",
        candidate_name="down_rocket_16_diag_v1",
        block_size=1,
    )

    assert frame.height == 2
    assert frame["source_block"].to_list() == ["block000", "block001"]
    assert frame["signal_tp"].to_list() == [True, False]
    assert frame["signal_fp"].to_list() == [False, True]


def test_row_rule_family_filter_can_block_bad_family() -> None:
    rejection = _row_rule("row_rpf_rejection_chop_mean_abs")
    liquidity = _row_rule("row_rpf_liquidity_volume_pressure_mean")

    kept, audit = filter_row_rules_by_family(
        [rejection, liquidity],
        allowed_families=(),
        blocked_families=("rejection_chop",),
    )

    assert [rule.feature for rule in kept] == ["row_rpf_liquidity_volume_pressure_mean"]
    assert len(audit) == 1
    assert audit[0]["feature"] == "row_rpf_rejection_chop_mean_abs"
    assert audit[0]["family_filter_feature_family"] == "rejection_chop"
    assert audit[0]["selection_reject_reasons"] == "family_blocked"


def test_row_rule_active_outputs_preserve_full_candidate_rows_and_filter_decisions() -> None:
    windows = [
        RPFWindow(step_idx=0, pred_pos=100, pred_batch_id=100, train_batch_ids=(), val_batch_ids=()),
        RPFWindow(step_idx=1, pred_pos=101, pred_batch_id=101, train_batch_ids=(), val_batch_ids=()),
    ]
    rows = [
        _candidate_score_row(100, "down_rocket_16_diag_v1", decision=1, target_binary=1, timestamp=1001),
        _candidate_score_row(100, "down_rocket_16_diag_v1", decision=1, target_binary=0, timestamp=1002),
        _candidate_score_row(101, "down_rocket_16_diag_v1", decision=1, target_binary=1, timestamp=1011),
        _candidate_score_row(101, "down_none_v1", decision=1, target_binary=1, timestamp=1012),
    ]
    accepted = [
        {
            "router_pred_batch_id": 100,
            "pred_batch_id": 100,
            "timestamp": 1001,
            "batch_id": 100,
        }
    ]
    args = SimpleNamespace(
        row_rule_gate_output_mode=ROW_RULE_GATE_OUTPUT_ACTIVE_DOWN_CANDIDATE,
        row_rule_gate_mode=ROW_RULE_GATE_PREQUENTIAL_RELIABILITY_V1,
        row_rule_gate_side="down",
        row_rule_gate_candidate_name="down_rocket_16_diag_v1",
        row_rule_gate_block_size=1,
        evaluation_block_size=1,
    )

    out = build_row_rule_active_outputs(
        rows,
        row_rule_gate_decisions=accepted,
        selected_outer_windows=windows,
        args=args,
        fp_cost=5.0,
        fn_cost=1.0,
        high_target_positive_rate_threshold=0.2,
        high_false_positive_rate_threshold=0.3,
    )

    assert len(out["score_rows"]) == 3
    assert len(out["decision_rows"]) == 1
    assert {row["candidate_name"] for row in out["score_rows"]} == {"down_rocket_16_diag_v1"}
    assert [row["decision"] for row in out["score_rows"]] == [1, 0, 0]
    assert [row["raw_candidate_decision"] for row in out["score_rows"]] == [1, 1, 1]
    assert out["side_summary"]["down"]["predicted_positive_count"] == 1
    assert out["side_summary"]["down"]["true_positive_count"] == 1
    assert out["side_summary"]["down"]["precision"] == pytest.approx(1.0)


def test_row_rule_active_outputs_support_generic_up_candidate() -> None:
    windows = [
        RPFWindow(step_idx=0, pred_pos=100, pred_batch_id=100, train_batch_ids=(), val_batch_ids=()),
    ]
    rows = [
        _candidate_score_row(
            100,
            "up_rocket_64_v1",
            decision=1,
            target_binary=1,
            timestamp=1001,
            side="up",
        ),
        _candidate_score_row(
            100,
            "down_rocket_16_diag_v1",
            decision=1,
            target_binary=1,
            timestamp=1002,
            side="down",
        ),
    ]
    accepted = [
        {
            "router_pred_batch_id": 100,
            "pred_batch_id": 100,
            "timestamp": 1001,
            "batch_id": 100,
        }
    ]
    args = SimpleNamespace(
        row_rule_gate_output_mode=ROW_RULE_GATE_OUTPUT_ACTIVE_CANDIDATE,
        row_rule_gate_mode=ROW_RULE_GATE_PREQUENTIAL_RELIABILITY_V1,
        row_rule_gate_side="up",
        row_rule_gate_candidate_name="up_rocket_64_v1",
        row_rule_gate_block_size=1,
        evaluation_block_size=1,
    )

    out = build_row_rule_active_outputs(
        rows,
        row_rule_gate_decisions=accepted,
        selected_outer_windows=windows,
        args=args,
        fp_cost=5.0,
        fn_cost=1.0,
        high_target_positive_rate_threshold=0.2,
        high_false_positive_rate_threshold=0.3,
    )

    assert len(out["score_rows"]) == 1
    assert len(out["decision_rows"]) == 1
    assert out["score_rows"][0]["side"] == "up"
    assert out["score_rows"][0]["row_rule_gate_output_mode"] == ROW_RULE_GATE_OUTPUT_ACTIVE_CANDIDATE
    assert out["window_rows"][0]["row_rule_gate_output_mode"] == ROW_RULE_GATE_OUTPUT_ACTIVE_CANDIDATE
    assert out["side_summary"]["up"]["predicted_positive_count"] == 1
    assert out["side_summary"]["up"]["precision"] == pytest.approx(1.0)


def test_effective_router_outputs_prefer_row_rule_active_when_enabled() -> None:
    args = SimpleNamespace(row_rule_gate_output_mode=ROW_RULE_GATE_OUTPUT_ACTIVE_CANDIDATE)
    out = resolve_effective_router_outputs(
        score_rows=[{"side": "up", "decision": 1, "target_binary": 0}],
        decision_rows=[{"side": "up", "decision": 1, "target_binary": 0}],
        window_rows=[{"side": "up", "predicted_positive_count": 1, "true_positive_count": 0}],
        block_rows=[{"side": "up", "block_idx": 0}],
        side_summary={"up": {"predicted_positive_count": 1, "precision": 0.0}},
        row_rule_active_outputs={
            "score_rows": [{"side": "up", "decision": 1, "target_binary": 1}],
            "decision_rows": [{"side": "up", "decision": 1, "target_binary": 1}],
            "window_rows": [{"side": "up", "predicted_positive_count": 1, "true_positive_count": 1}],
            "block_rows": [{"side": "up", "block_idx": 0}],
            "side_summary": {"up": {"predicted_positive_count": 1, "precision": 1.0}},
        },
        args=args,
    )

    assert out["prediction_source"] == "row_rule_active"
    assert out["score_rows"][0]["target_binary"] == 1
    assert out["score_rows"][0]["prediction_source"] == "row_rule_active"
    assert out["window_rows"][0]["prediction_source"] == "row_rule_active"
    assert out["side_summary"]["up"]["precision"] == pytest.approx(1.0)
    assert out["side_summary"]["up"]["prediction_source"] == "row_rule_active"


def test_effective_router_outputs_fall_back_to_router_selected_without_active_rows() -> None:
    args = SimpleNamespace(row_rule_gate_output_mode=ROW_RULE_GATE_OUTPUT_ACTIVE_CANDIDATE)
    out = resolve_effective_router_outputs(
        score_rows=[{"side": "down", "decision": 1, "target_binary": 1}],
        decision_rows=[{"side": "down", "decision": 1, "target_binary": 1}],
        window_rows=[{"side": "down", "predicted_positive_count": 1, "true_positive_count": 1}],
        block_rows=[{"side": "down", "block_idx": 0}],
        side_summary={"down": {"predicted_positive_count": 1, "precision": 1.0}},
        row_rule_active_outputs={
            "score_rows": [],
            "decision_rows": [],
            "window_rows": [],
            "block_rows": [],
            "side_summary": {},
        },
        args=args,
    )

    assert out["prediction_source"] == "router_selected"
    assert out["score_rows"][0]["prediction_source"] == "router_selected"
    assert out["side_summary"]["down"]["prediction_source"] == "router_selected"


def test_router_report_names_effective_summary(tmp_path: Path) -> None:
    write_router_report(
        tmp_path,
        router_config={
            "asset": "BTCUSDT",
            "root": "8h/B",
            "candidate_set": "pruned_reliability_v1",
            "selection_mode": "prequential_reliability_v1",
            "outer_window_count": 10,
        },
        side_summary={"up": {"precision": 0.1}},
        effective_side_summary={"up": {"precision": 0.9, "prediction_source": "row_rule_active"}},
        effective_prediction_source="row_rule_active",
    )

    text = (tmp_path / "report.md").read_text()
    assert "Effective Selected Summary" in text
    assert "Base Router Summary" in text
    assert "row_rule_active" in text
    assert "`effective_*` artifacts are the canonical selected output" in text


def test_load_context_rules_accepts_simulator_rule_directory(tmp_path: Path) -> None:
    run = tmp_path / "sim"
    run.mkdir()
    pl.DataFrame(
        [
            {
                "side": "up",
                "candidate_name": "up_rocket_64_v1",
                "feature": "score_mean",
                "direction": "lower_good",
                "threshold": -0.01,
                "train_score": 1.5,
                "train_precision": 1.0,
                "train_lift": 2.0,
                "train_signals": 4,
            }
        ]
    ).write_parquet(run / "meta_router_rules.parquet")

    rules = load_context_rules(run)

    rule = rules[("up", "up_rocket_64_v1")]
    assert rule.feature == "score_mean"
    assert rule.direction == "lower_good"
    assert rule.threshold == pytest.approx(-0.01)


def test_context_rule_selection_can_pass_failed_validation_and_reliability() -> None:
    candidate = CandidateSpec("up_rocket_64_v1", "up", RankTrialConfig())
    result = {
        "status": "ok",
        "candidate": candidate,
        "passed": False,
        "fail_reasons": ["low_validation_precision_lift"],
        "validation_metrics": {"ranked_signal_quality": -2.0, "precision_lift": 0.5, "false_discovery_rate": 1.0},
        "fold": {"prediction_window_metric": {"score_mean": -0.02, "threshold": 0.1}},
        "sequence_feature_count": 192,
    }
    reliability = {
        "reliability_status": "fail",
        "reliability_passed": False,
        "reliability_fail_reasons": "low_reliability_precision_lift_lcb",
    }
    rules = {
        ("up", "up_rocket_64_v1"): ContextRule(
            side="up",
            candidate_name="up_rocket_64_v1",
            feature="score_mean",
            direction="lower_good",
            threshold=-0.01,
            train_score=1.5,
        )
    }

    selected = select_router_candidate(
        [result],
        reliability_by_candidate={"up_rocket_64_v1": reliability},
        selection_mode=SELECTION_CONTEXT_RULE_V1,
        reliability_config=ReliabilityConfig(),
        context_rules=rules,
    )

    assert selected["final_selection_passed"] is True
    assert selected["passed"] is False
    assert selected["context_rule_passed"] is True
    assert selected["context_rule_feature"] == "score_mean"
    assert selected["context_rule_margin"] == pytest.approx(0.01)


def test_context_rule_selection_emits_no_signal_when_rule_fails() -> None:
    candidate = CandidateSpec("up_rocket_64_v1", "up", RankTrialConfig())
    result = {
        "status": "ok",
        "candidate": candidate,
        "passed": True,
        "fail_reasons": [],
        "validation_metrics": {"ranked_signal_quality": 2.0, "precision_lift": 2.0, "false_discovery_rate": 0.0},
        "fold": {"prediction_window_metric": {"score_mean": 0.0}},
        "sequence_feature_count": 192,
    }
    rules = {
        ("up", "up_rocket_64_v1"): ContextRule(
            side="up",
            candidate_name="up_rocket_64_v1",
            feature="score_mean",
            direction="lower_good",
            threshold=-0.01,
            train_score=1.5,
        )
    }

    selected = select_router_candidate(
        [result],
        reliability_by_candidate={"up_rocket_64_v1": {}},
        selection_mode=SELECTION_CONTEXT_RULE_V1,
        reliability_config=ReliabilityConfig(),
        context_rules=rules,
    )

    assert selected["final_selection_passed"] is False
    assert selected["selection_rejected_reason"] == "context_rule_failed"
    assert selected["context_rule_passed"] is False


def test_candidate_selection_audit_rows_include_per_candidate_rejection_reason() -> None:
    weak_candidate = CandidateSpec("up_none_v1", "up", RankTrialConfig())
    strong_candidate = CandidateSpec("up_rocket_64_v1", "up", RankTrialConfig())
    weak = {
        "status": "ok",
        "candidate": weak_candidate,
        "passed": False,
        "fail_reasons": ["low_validation_precision_lift"],
        "validation_metrics": {
            "ranked_signal_quality": -1.0,
            "precision_lift": 0.8,
            "false_discovery_rate": 0.7,
        },
        "sequence_feature_count": 0,
    }
    strong = {
        "status": "ok",
        "candidate": strong_candidate,
        "passed": True,
        "fail_reasons": [],
        "validation_metrics": {
            "ranked_signal_quality": 1.0,
            "precision_lift": 1.5,
            "false_discovery_rate": 0.2,
        },
        "sequence_feature_count": 64,
    }
    reliability = {
        "up_none_v1": {
            "reliability_passed": False,
            "reliability_fail_reasons": "insufficient_reliability_history",
        },
        "up_rocket_64_v1": {
            "reliability_passed": True,
            "reliability_fail_reasons": "",
        },
    }
    selected = {
        **strong,
        "final_selection_passed": True,
        "selection_mode": SELECTION_PREQUENTIAL_RELIABILITY_V1,
        "selection_rejected_reason": None,
    }

    rows = candidate_selection_audit_rows(
        [weak, strong],
        selected=selected,
        reliability_by_candidate=reliability,
        reliability_config=ReliabilityConfig(),
        selection_mode=SELECTION_PREQUENTIAL_RELIABILITY_V1,
        outer_window=RPFWindow(
            step_idx=1,
            pred_pos=101,
            pred_batch_id=101,
            train_batch_ids=(),
            val_batch_ids=(),
        ),
    )
    by_name = {row["candidate_name"]: row for row in rows}

    assert by_name["up_none_v1"]["candidate_passed_selection"] is False
    assert by_name["up_none_v1"]["candidate_rejected_reason"] == "validation_failed"
    assert by_name["up_rocket_64_v1"]["candidate_passed_selection"] is True
    assert by_name["up_rocket_64_v1"]["candidate_rejected_reason"] is None
    assert by_name["up_rocket_64_v1"]["selected_candidate_name"] == "up_rocket_64_v1"


def test_wilson_lower_bound_matches_reference_value() -> None:
    # 8 successes from 10 trials, z=1.0.
    assert wilson_lower_bound(8, 10, z=1.0) == pytest.approx(0.6490775, rel=1e-5)
    assert wilson_lower_bound(0, 0, z=1.0) is None


def test_reliability_state_uses_only_supplied_prior_history() -> None:
    candidate = CandidateSpec("up_none_v1", "up", RankTrialConfig())
    config = ReliabilityConfig(
        lookback_windows=10,
        min_history_windows=2,
        min_signals=2,
        min_active_windows=1,
        min_precision_lift_lcb=0.1,
        max_false_discovery_rate=1.0,
        lcb_z=1.0,
    )
    prior = [
        {
            "side": "up",
            "candidate_name": "up_none_v1",
            "status": "ok",
            "rows": 10,
            "positive_count": 5,
            "predicted_positive_count": 1,
            "true_positive_count": 1,
            "false_positive_count": 0,
            "active_window": True,
            "high_false_positive_window": False,
        },
        {
            "side": "up",
            "candidate_name": "up_none_v1",
            "status": "ok",
            "rows": 10,
            "positive_count": 5,
            "predicted_positive_count": 1,
            "true_positive_count": 1,
            "false_positive_count": 0,
            "active_window": True,
            "high_false_positive_window": False,
        },
    ]
    current_perfect_window = {
        "side": "up",
        "candidate_name": "up_none_v1",
        "status": "ok",
        "rows": 10,
        "positive_count": 10,
        "predicted_positive_count": 10,
        "true_positive_count": 10,
        "false_positive_count": 0,
        "active_window": True,
        "high_false_positive_window": False,
    }

    state_before_current = reliability_state_for_candidate(candidate=candidate, history_rows=prior, config=config)
    state_after_current = reliability_state_for_candidate(candidate=candidate, history_rows=[*prior, current_perfect_window], config=config)

    assert state_before_current["history_windows"] == 2
    assert state_before_current["signal_count"] == 2
    assert state_after_current["history_windows"] == 3
    assert state_after_current["signal_count"] == 12


def test_reliability_state_splits_window_selection_from_row_lift() -> None:
    candidate = CandidateSpec("down_rocket_16_diag_v1", "down", RankTrialConfig())
    config = ReliabilityConfig(
        lookback_windows=10,
        min_history_windows=3,
        min_signals=4,
        min_active_windows=2,
        min_precision_lift_lcb=0.1,
        min_window_selection_lift=1.1,
        min_selected_window_row_lift_lcb=1.05,
        max_false_discovery_rate=1.0,
        lcb_z=1.0,
    )
    history = [
        {
            "side": "down",
            "candidate_name": "down_rocket_16_diag_v1",
            "status": "ok",
            "rows": 10,
            "positive_count": 1,
            "predicted_positive_count": 0,
            "true_positive_count": 0,
            "false_positive_count": 0,
            "active_window": False,
            "high_false_positive_window": False,
        },
        {
            "side": "down",
            "candidate_name": "down_rocket_16_diag_v1",
            "status": "ok",
            "rows": 10,
            "positive_count": 8,
            "predicted_positive_count": 2,
            "true_positive_count": 1,
            "false_positive_count": 1,
            "active_window": True,
            "high_false_positive_window": False,
        },
        {
            "side": "down",
            "candidate_name": "down_rocket_16_diag_v1",
            "status": "ok",
            "rows": 10,
            "positive_count": 8,
            "predicted_positive_count": 2,
            "true_positive_count": 1,
            "false_positive_count": 1,
            "active_window": True,
            "high_false_positive_window": False,
        },
    ]

    state = reliability_state_for_candidate(candidate=candidate, history_rows=history, config=config)

    assert state["base_rate"] == pytest.approx(17 / 30)
    assert state["active_window_base_rate"] == pytest.approx(16 / 20)
    assert state["window_selection_lift"] == pytest.approx((16 / 20) / (17 / 30))
    assert state["selected_window_row_lift"] == pytest.approx(0.5 / 0.8)
    assert state["reliability_passed"] is False
    assert "low_reliability_selected_window_row_lift_lcb" in state["reliability_fail_reasons"]


def test_reliability_state_can_pass_when_selected_rows_beat_active_window_base() -> None:
    candidate = CandidateSpec("down_rocket_16_diag_v1", "down", RankTrialConfig())
    config = ReliabilityConfig(
        lookback_windows=10,
        min_history_windows=3,
        min_signals=4,
        min_active_windows=2,
        min_precision_lift_lcb=0.1,
        min_window_selection_lift=0.5,
        min_selected_window_row_lift_lcb=1.05,
        max_false_discovery_rate=1.0,
        lcb_z=1.0,
    )
    history = [
        {
            "side": "down",
            "candidate_name": "down_rocket_16_diag_v1",
            "status": "ok",
            "rows": 10,
            "positive_count": 5,
            "predicted_positive_count": 0,
            "true_positive_count": 0,
            "false_positive_count": 0,
            "active_window": False,
            "high_false_positive_window": False,
        },
        {
            "side": "down",
            "candidate_name": "down_rocket_16_diag_v1",
            "status": "ok",
            "rows": 10,
            "positive_count": 2,
            "predicted_positive_count": 4,
            "true_positive_count": 3,
            "false_positive_count": 1,
            "active_window": True,
            "high_false_positive_window": False,
        },
        {
            "side": "down",
            "candidate_name": "down_rocket_16_diag_v1",
            "status": "ok",
            "rows": 10,
            "positive_count": 2,
            "predicted_positive_count": 4,
            "true_positive_count": 3,
            "false_positive_count": 1,
            "active_window": True,
            "high_false_positive_window": False,
        },
    ]

    state = reliability_state_for_candidate(candidate=candidate, history_rows=history, config=config)

    assert state["precision"] == pytest.approx(0.75)
    assert state["active_window_base_rate"] == pytest.approx(0.2)
    assert state["selected_window_row_lift"] == pytest.approx(3.75)
    assert state["selected_window_row_lift_lcb"] > 1.05
    assert state["reliability_passed"] is True


def test_prequential_selection_prefers_reliable_candidate_over_high_validation_candidate() -> None:
    unreliable = CandidateSpec("up_none_v1", "up", RankTrialConfig())
    reliable = CandidateSpec("up_rocket_64_v1", "up", RankTrialConfig())
    results = [
        {
            "candidate": unreliable,
            "passed": True,
            "sequence_feature_count": 0,
            "validation_metrics": {
                "ranked_signal_quality": 10.0,
                "precision_lift": 3.0,
                "false_discovery_rate": 0.0,
            },
            "prediction_precision": 1.0,
        },
        {
            "candidate": reliable,
            "passed": True,
            "sequence_feature_count": 192,
            "validation_metrics": {
                "ranked_signal_quality": 1.0,
                "precision_lift": 1.2,
                "false_discovery_rate": 0.3,
            },
        },
    ]
    reliability = {
        "up_none_v1": {
            "reliability_passed": False,
            "reliability_score": 10.0,
            "precision_lift_lcb": 0.5,
            "reliability_fail_reasons": "low_reliability_precision_lift_lcb",
        },
        "up_rocket_64_v1": {
            "reliability_passed": True,
            "reliability_score": 0.5,
            "precision_lift_lcb": 1.2,
            "reliability_fail_reasons": "",
        },
    }

    selected = select_router_candidate(
        results,
        reliability_by_candidate=reliability,
        selection_mode=SELECTION_PREQUENTIAL_RELIABILITY_V1,
        reliability_config=ReliabilityConfig(),
    )

    assert selected["candidate"] is reliable
    assert selected["final_selection_passed"] is True


def test_prequential_selection_emits_no_signal_when_reliability_is_warming_up() -> None:
    candidate = CandidateSpec("down_none_v1", "down", RankTrialConfig())
    result = {
        "candidate": candidate,
        "passed": True,
        "sequence_feature_count": 0,
        "validation_metrics": {
            "ranked_signal_quality": 2.0,
            "precision_lift": 2.0,
            "false_discovery_rate": 0.1,
        },
    }

    selected = select_router_candidate(
        [result],
        reliability_by_candidate={
            "down_none_v1": {
                "reliability_passed": False,
                "reliability_score": None,
                "precision_lift_lcb": None,
                "reliability_fail_reasons": "insufficient_reliability_history",
            }
        },
        selection_mode=SELECTION_PREQUENTIAL_RELIABILITY_V1,
        reliability_config=ReliabilityConfig(),
    )

    assert selected["candidate"] is candidate
    assert selected["final_selection_passed"] is False
    assert selected["selection_rejected_reason"] == "insufficient_reliability_history"


def test_specialist_entry_selects_down_none_quiet_validation_with_prediction_safe_gate() -> None:
    candidate = CandidateSpec("down_none_v1", "down", RankTrialConfig())
    result = {
        "status": "ok",
        "candidate": candidate,
        "passed": False,
        "fail_reasons": ["low_validation_signal_count"],
        "sequence_feature_count": 0,
        "validation_metrics": {
            "predicted_positive_count": 0,
            "ranked_signal_quality": -1.0,
            "precision_lift": 0.0,
            "false_discovery_rate": 0.0,
        },
        "fold": {
            "prediction_window_metric": {
                "batch_state_gate_mode": "logistic_prefix_v1",
                "batch_state_gate_passed": True,
            }
        },
    }

    selected = select_router_candidate(
        [result],
        reliability_by_candidate={
            "down_none_v1": {
                "reliability_passed": False,
                "reliability_score": None,
                "precision_lift_lcb": None,
                "selected_window_row_lift_lcb": None,
                "window_selection_lift": None,
                "reliability_fail_reasons": "insufficient_reliability_history",
            }
        },
        selection_mode=SELECTION_PREQUENTIAL_RELIABILITY_V1,
        reliability_config=ReliabilityConfig(),
        specialist_entry_mode=SPECIALIST_ENTRY_DOWN_NONE_VALIDATION_QUIET_V1,
    )

    assert specialist_entry_passed(result, SPECIALIST_ENTRY_DOWN_NONE_VALIDATION_QUIET_V1) is True
    assert selected["candidate"] is candidate
    assert selected["passed"] is False
    assert selected["final_selection_passed"] is True
    assert selected["specialist_entry_passed"] is True
    assert selected["specialist_entry_reason"] == SPECIALIST_ENTRY_DOWN_NONE_VALIDATION_QUIET_V1


def test_specialist_entry_requires_prediction_safe_batch_gate() -> None:
    candidate = CandidateSpec("down_none_v1", "down", RankTrialConfig())
    result = {
        "status": "ok",
        "candidate": candidate,
        "passed": False,
        "validation_metrics": {"predicted_positive_count": 0},
        "fold": {
            "prediction_window_metric": {
                "batch_state_gate_mode": "logistic_prefix_v1",
                "batch_state_gate_passed": False,
            }
        },
    }

    assert specialist_entry_passed(result, SPECIALIST_ENTRY_OFF) is False
    assert specialist_entry_passed(result, SPECIALIST_ENTRY_DOWN_NONE_VALIDATION_QUIET_V1) is False


def _candidate_score_row(
    pred_batch_id: int,
    candidate_name: str,
    *,
    decision: int,
    target_binary: int,
    timestamp: int | None = None,
    side: str = "down",
) -> dict[str, object]:
    return {
        "side": side,
        "candidate_name": candidate_name,
        "diagnostic": True,
        "candidate_status": "ok",
        "candidate_passed_validation": True,
        "candidate_fail_reasons": "",
        "router_step_idx": pred_batch_id,
        "router_pred_batch_id": pred_batch_id,
        "pred_batch_id": pred_batch_id,
        "timestamp": pred_batch_id * 1000 if timestamp is None else timestamp,
        "batch_id": pred_batch_id,
        "target_binary": target_binary,
        "target_relevance": float(target_binary),
        "rank_score": 0.1,
        "threshold": 0.0,
        "margin": 0.1,
        "decision": decision,
    }


def _row_rule(feature: str) -> RowRule:
    return RowRule(
        fold_idx=0,
        train_blocks="block000",
        test_block="block001",
        side="down",
        candidate_name="down_rocket_16_diag_v1",
        feature=feature,
        direction="higher_good",
        threshold=0.1,
        train_rows=100,
        train_accepted_rows=10,
        train_tp=8,
        train_fp=2,
        train_precision=0.8,
        train_base_precision=0.4,
        train_lift=2.0,
        train_false_discovery_rate=0.2,
        train_precision_lcb=0.6,
        train_accepted_rate=0.1,
        rule_score=1.0,
        feature_auc=0.7,
        feature_auc_abs=0.7,
        feature_auc_direction="higher_good",
        direction_agreement=True,
        directional_lcb_score=1.2,
    )
