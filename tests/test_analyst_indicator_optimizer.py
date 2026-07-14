from __future__ import annotations

import json
import math
import sys
from dataclasses import asdict, is_dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import polars as pl
import pytest

ANALYST_ROOT = (
    Path(__file__).resolve().parents[1] / "Risk_Yield_Meta_Model_Analyst_0_0_1"
)
if str(ANALYST_ROOT) not in sys.path:
    sys.path.insert(0, str(ANALYST_ROOT))

import indicator_optimizer as optimizer  # noqa: E402


def _minute_frame(rows: int) -> pl.DataFrame:
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    values = []
    price = 100.0
    for index in range(rows):
        price *= math.exp(0.0001 + 0.00005 * math.sin(index / 17.0))
        values.append(
            {
                "timestamp": start + timedelta(minutes=index),
                "open": price * 0.999,
                "high": price * 1.001,
                "low": price * 0.998,
                "close": price,
                "volume": 100.0,
            }
        )
    return pl.DataFrame(values)


def _strategy_values(strategy: Any) -> dict[str, Any]:
    if hasattr(strategy, "as_dict"):
        return dict(strategy.as_dict())
    if is_dataclass(strategy):
        return asdict(strategy)
    return dict(vars(strategy))


def _cost_values(costs: Any) -> dict[str, Any]:
    if hasattr(costs, "as_dict"):
        return dict(costs.as_dict())
    if is_dataclass(costs):
        return asdict(costs)
    return dict(costs)


def _score(strategy: Any) -> float:
    values = _strategy_values(strategy)
    score = 0.50
    if values["cusum_sensitivity"] == "Balanced (Swing)":
        score += 0.20
    elif values["cusum_sensitivity"] == "Slow (Trend)":
        score += 0.10
    if tuple(values["horizons"]) == (12, 48, 192):
        score += 0.15
    if values["enable_experimental_prototype_regime_gate"] is True:
        score += 0.10
    if values["max_fast_slow_ratio"] == pytest.approx(1.75):
        score += 0.05
    return score


def _successful_replay_stub(calls: list[dict[str, Any]]):
    def run(
        frame: pl.DataFrame,
        *,
        asset: str,
        timeframe: str,
        strategy: Any,
        costs: Any,
        evaluation_start: datetime | None = None,
        replay_clock: datetime | None = None,
        event_limit: int = 5_000,
        capture_series: bool = True,
    ) -> dict[str, Any]:
        score = _score(strategy)
        calls.append(
            {
                "rows": frame.height,
                "asset": asset,
                "timeframe": timeframe,
                "strategy": _strategy_values(strategy),
                "costs": _cost_values(costs),
                "evaluation_start": evaluation_start,
                "replay_clock": replay_clock,
                "event_limit": event_limit,
                "capture_series": capture_series,
            }
        )
        return {
            "metrics": {
                "net_sharpe": score,
                "net_return": 0.01 + score / 100.0,
                "max_drawdown": 0.10,
                "fill_count": 8,
            },
            "equity": [{"time": evaluation_start, "value": 1.01}],
            "fills": [],
            "signals": [],
            "metadata": {"research_only": True},
        }

    return run


def test_optimizer_uses_prefix_folds_locks_holdout_and_selects_fixed_grid(
    tmp_path: Path, monkeypatch
) -> None:
    frame = _minute_frame(500)
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(optimizer, "run_minute_replay", _successful_replay_stub(calls))
    registry = tmp_path / "trials.jsonl"

    result = optimizer.optimize_indicator_strategy(
        frame,
        "BTCUSDT",
        "1m",
        {"fee_bps": 1.0, "slippage_bps": 2.0, "execution_latency_minutes": 1},
        trial_registry_path=registry,
    )

    assert result["status"] == "accepted_for_paper_trading"
    assert result["profitability_guaranteed"] is False
    assert result["research_only"] is True
    assert result["trials"]["candidate_count"] == 24
    assert result["trials"]["fold_evaluations"] == 72
    assert result["split"]["development_folds"] == 3
    assert result["split"]["holdout_bars"] == 100
    assert result["split"]["holdout_fraction_actual"] == pytest.approx(0.20)

    best = result["best_config"]
    assert best["cusum_sensitivity"] == "Balanced (Swing)"
    assert best["horizons"] == [12, 48, 192]
    assert best["change_risk_threshold"] == pytest.approx(0.55)
    assert best["enable_experimental_prototype_regime_gate"] is True
    assert best["max_fast_slow_ratio"] == pytest.approx(1.75)
    assert best["position_step"] == pytest.approx(0.10)
    assert result["development"]["objective"] == pytest.approx(1.0)
    assert all(result["acceptance_gates"].values())

    development_calls = calls[:72]
    assert {call["rows"] for call in development_calls} == {262, 331, 400}
    assert all(call["rows"] <= 400 for call in development_calls)
    assert all(call["costs"]["fee_bps"] == 2.0 for call in development_calls)
    assert all(call["costs"]["slippage_bps"] == 4.0 for call in development_calls)
    assert all(call["costs"]["execution_latency_minutes"] == 1 for call in calls)
    assert all(call["event_limit"] == 0 for call in calls[:-1])
    assert all(call["capture_series"] is False for call in calls[:-1])

    holdout_start = frame["timestamp"][400]
    assert calls[-2]["rows"] == frame.height
    assert calls[-2]["evaluation_start"] == holdout_start
    assert calls[-2]["costs"]["fee_bps"] == 2.0
    assert calls[-2]["strategy"]["enable_experimental_prototype_regime_gate"] is True
    assert calls[-1]["rows"] == frame.height
    assert calls[-1]["evaluation_start"] == holdout_start
    assert calls[-1]["costs"]["fee_bps"] == 1.0
    assert calls[-1]["strategy"]["enable_experimental_prototype_regime_gate"] is True
    assert calls[-1]["event_limit"] == 5_000
    assert calls[-1]["capture_series"] is True

    records = [json.loads(line) for line in registry.read_text().splitlines()]
    assert len(records) == 74
    assert [record["event"] for record in records[-2:]] == [
        "untouched_holdout",
        "final_holdout_replay",
    ]
    assert all(len(record["record_hash"]) == 64 for record in records)
    json.dumps(result, allow_nan=False)


def test_optimizer_returns_insufficient_evidence_without_replay_for_short_history(
    tmp_path: Path, monkeypatch
) -> None:
    def fail_if_called(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise AssertionError("short history must not be replayed")

    monkeypatch.setattr(optimizer, "run_minute_replay", fail_if_called)
    registry = tmp_path / "insufficient.jsonl"

    result = optimizer.optimize_indicator_strategy(
        _minute_frame(300),
        "BTCUSDT",
        "1m",
        {"fee_bps": 1.0, "slippage_bps": 1.0},
        trial_registry_path=registry,
    )

    assert result["status"] == "insufficient_evidence"
    assert result["best_config"] is None
    assert "Insufficient target-timeframe research history" in result["reason"]
    record = json.loads(registry.read_text())
    assert record["event"] == "insufficient_evidence"


def test_optimizer_rejects_candidates_that_fail_minimum_fill_constraint(
    tmp_path: Path, monkeypatch
) -> None:
    def sparse_replay(
        _frame: pl.DataFrame,
        **_kwargs: Any,
    ) -> dict[str, Any]:
        return {
            "metrics": {
                "net_sharpe": 4.0,
                "net_return": 0.50,
                "max_drawdown": 0.01,
                "fill_count": 1,
            },
            "equity": [],
            "fills": [],
            "signals": [],
            "metadata": {},
        }

    monkeypatch.setattr(optimizer, "run_minute_replay", sparse_replay)
    registry = tmp_path / "sparse.jsonl"

    result = optimizer.optimize_indicator_strategy(
        _minute_frame(500),
        "ETHUSDT",
        "1m",
        {"fee_bps": 1.0, "slippage_bps": 1.0},
        trial_registry_path=registry,
        minimum_fills_per_fold=5,
    )

    assert result["status"] == "insufficient_evidence"
    assert result["best_config"] is None
    assert result["trials"]["candidate_count"] == 24
    assert result["trials"]["eligible_candidate_count"] == 0
    assert result["trials"]["fold_evaluations"] == 72
    assert len(registry.read_text().splitlines()) == 72


def test_pre_research_rows_warm_state_without_enlarging_holdout(
    tmp_path: Path, monkeypatch
) -> None:
    frame = _minute_frame(700)
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(optimizer, "run_minute_replay", _successful_replay_stub(calls))
    research_start = frame["timestamp"][200]

    result = optimizer.optimize_indicator_strategy(
        frame,
        "BTCUSDT",
        "1m",
        {"fee_bps": 1.0, "slippage_bps": 1.0},
        research_start=research_start.isoformat(),
        trial_registry_path=tmp_path / "warmup.jsonl",
    )

    assert result["split"]["target_timeframe_bars"] == 700
    assert result["split"]["research_bars"] == 500
    assert result["split"]["pre_research_warmup_bars"] == 200
    assert result["split"]["research_bars_used_for_additional_warmup"] == 0
    assert result["split"]["holdout_bars"] == 100
    assert result["split"]["holdout_fraction_actual"] == pytest.approx(0.20)
    assert {call["rows"] for call in calls[:72]} == {334, 467, 600}
    assert calls[-2]["evaluation_start"] == frame["timestamp"][600]


def test_robust_objective_penalizes_fold_dispersion_and_hashes_are_stable() -> None:
    assert optimizer._robust_objective([1.0, 2.0, 3.0]) == pytest.approx(1.5)
    assert len(optimizer._candidate_specs()) == 24
    assert optimizer._candidate_specs() == optimizer._candidate_specs()
    payload = {"config": optimizer._candidate_specs()[0], "fold": 1}
    assert optimizer._digest(payload) == optimizer._digest(payload)


def test_strategy_config_serialization_round_trip_preserves_every_field() -> None:
    strategy = optimizer.IndicatorStrategyConfig(
        cusum_sensitivity="Fast (Day Trade)",
        horizons=(7, 29, 113),
        trend_z_clip=6.5,
        aligned_score=0.31,
        aligned_quality=0.41,
        developing_score=0.12,
        change_risk_threshold=0.62,
        max_fast_slow_ratio=1.44,
        minimum_path_quality=0.22,
        trade_developing_trends=False,
        require_cusum_agreement=False,
        enable_experimental_prototype_regime_gate=True,
        require_regime_direction=True,
        maximum_exposure=0.80,
        minimum_volatility_scale=0.33,
        position_step=0.20,
    )
    specification = {"horizon_template": "round_trip_audit"}
    serialized = optimizer._strategy_as_dict(strategy, specification)

    restored_specification = optimizer._specification_from_config(serialized)
    restored = optimizer._make_strategy_config(restored_specification)

    assert restored == strategy
    assert set(serialized) == set(strategy.as_dict()) | {"horizon_template"}
    assert restored_specification["horizons"] == strategy.horizons


def test_strategy_config_round_trip_rejects_missing_or_unknown_fields() -> None:
    serialized = optimizer._strategy_as_dict(
        optimizer.IndicatorStrategyConfig(),
        {"horizon_template": "balanced"},
    )
    missing = dict(serialized)
    missing.pop("position_step")
    with pytest.raises(KeyError, match="position_step"):
        optimizer._specification_from_config(missing)

    unknown = dict(serialized)
    unknown["unrecognized_gate"] = True
    with pytest.raises(TypeError, match="unrecognized_gate"):
        optimizer._specification_from_config(unknown)

    candidate = dict(optimizer._candidate_specs()[0])
    candidate["unrecognized_gate"] = True
    with pytest.raises(TypeError, match="unrecognized_gate"):
        optimizer._make_strategy_config(candidate)


def test_metric_adapter_matches_minute_replay_metric_contract() -> None:
    metrics = optimizer._extract_metrics(
        {
            "metrics": {
                "annualized_sharpe": 1.25,
                "total_return_pct": 3.5,
                "max_drawdown_pct": 7.0,
                "fill_count": 12,
            },
            "fills": [],
        }
    )

    assert metrics == {
        "net_sharpe": 1.25,
        "net_return": pytest.approx(0.035),
        "max_drawdown": pytest.approx(0.07),
        "fill_count": 12,
        "complete": True,
    }


@pytest.mark.parametrize(
    ("timeframe", "seconds"),
    [
        ("1m", 60),
        ("15m", 900),
        ("1h", 3_600),
        ("4h", 14_400),
        ("8h", 28_800),
        ("12h", 43_200),
        ("1d", 86_400),
    ],
)
def test_optimizer_supports_every_canonical_timeframe(
    timeframe: str, seconds: int
) -> None:
    assert optimizer._timeframe_seconds(timeframe) == seconds


def test_optimizer_bucket_inventory_excludes_forming_target_candle() -> None:
    frame = _minute_frame(61)
    start = frame["timestamp"][0]

    starts = optimizer._target_bucket_starts(
        frame,
        "1h",
        replay_clock=start + timedelta(hours=1),
    )

    assert starts == [0, 60]


def test_target_bucket_count_excludes_synthetic_no_trade_minutes() -> None:
    frame = _minute_frame(5).with_columns(
        pl.Series("is_synthetic_no_trade", [False, True, False, True, False])
    )

    starts = optimizer._target_bucket_starts(frame, "1m")

    assert starts == [0, 2, 4, 5]
