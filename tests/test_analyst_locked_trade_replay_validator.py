from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/analysis/validate_analyst_locked_trade_replay.py"
SPEC = importlib.util.spec_from_file_location("locked_trade_replay_validator", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
validator = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = validator
SPEC.loader.exec_module(validator)


def _row(net: float, sharpe: float, drawdown: float, breakeven: float) -> dict:
    metrics = {
        "total_return_pct": net,
        "annualized_sharpe": sharpe,
        "max_drawdown_pct": drawdown,
        "breakeven_all_in_cost_bps": breakeven,
        "fill_count": 25,
        "round_trip_count": 10,
    }
    return {
        "status": "ok",
        "metrics": metrics,
        "gates": validator.selection_gates(metrics),
        "data_quality": {
            "excluded_synthetic_minutes": 2,
            "suppressed_incomplete_target_bars": 1,
        },
    }


def test_locked_protocol_matches_forward_paper_defaults() -> None:
    assert validator.LOCKED_STRATEGY == validator.IndicatorStrategyConfig()
    assert validator.LOCKED_COSTS.fee_bps == pytest.approx(1.0)
    assert validator.LOCKED_COSTS.slippage_bps == pytest.approx(1.0)
    assert validator.LOCKED_COSTS.spread_bps == pytest.approx(0.0)
    assert validator.LOCKED_COSTS.execution_latency_minutes == 1


def test_selection_gates_are_descriptive_and_strict() -> None:
    passing = _row(2.0, 0.5, 10.0, 5.0)
    failing = _row(0.0, 0.0, 20.1, 4.0)

    assert all(passing["gates"].values())
    assert failing["gates"] == {
        "minimum_fills": True,
        "net_return_positive": False,
        "annualized_sharpe_positive": False,
        "drawdown_at_most_20pct": False,
        "gross_edge_exceeds_2x_cost_scenario": False,
    }


def test_aggregate_counts_failures_without_hiding_them() -> None:
    rows = [
        _row(2.0, 0.5, 10.0, 5.0),
        _row(-1.0, -0.2, 5.0, -1.0),
        {"status": "error", "error": "fixture"},
    ]

    result = validator.aggregate(rows)

    assert result["selection_count"] == 3
    assert result["completed_count"] == 2
    assert result["failure_count"] == 1
    assert result["positive_net_return_rate"] == pytest.approx(0.5)
    assert result["all_descriptive_gates_rate"] == pytest.approx(0.5)
    assert result["total_fills"] == 50
    assert result["total_round_trips"] == 20
    assert result["total_excluded_synthetic_minutes"] == 4
    assert result["total_suppressed_incomplete_target_bars"] == 2
