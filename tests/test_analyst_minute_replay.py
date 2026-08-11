from __future__ import annotations

import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import polars as pl
import pytest

ANALYST_ROOT = (
    Path(__file__).resolve().parents[1] / "Risk_Yield_Meta_Model_Analyst_0_0_1"
)
if str(ANALYST_ROOT) not in sys.path:
    sys.path.insert(0, str(ANALYST_ROOT))

from minute_replay import (  # noqa: E402
    CausalCandleBuilder,
    IndicatorStrategyConfig,
    ProtectedReplayConfig,
    ReplayCostConfig,
    _desired_position,
    _ExecutionLedger,
    meta_label_policy_digest,
    run_minute_replay,
    target_bar_is_complete,
)
from trade_ml.artifact import build_coefficient_artifact  # noqa: E402
from trade_ml.features import META_FEATURE_NAMES  # noqa: E402
from trade_ml.model import fit_logistic_baseline  # noqa: E402


def _minute_row(
    timestamp: datetime, open_value: float, close: float
) -> dict[str, object]:
    return {
        "timestamp": timestamp,
        "open": open_value,
        "high": max(open_value, close) + 0.25,
        "low": min(open_value, close) - 0.25,
        "close": close,
        "volume": 10.0,
        "is_synthetic_no_trade": False,
        "is_session_open_bar": False,
    }


def _trending_frame(rows: int = 1_200) -> pl.DataFrame:
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    output = []
    price = 100.0
    for idx in range(rows):
        increment = 0.0012 + 0.0007 * math.sin(idx / 7.0)
        if idx >= rows * 2 // 3:
            increment = -0.0015 + 0.0005 * math.sin(idx / 9.0)
        open_value = price
        close = price * math.exp(increment)
        output.append(_minute_row(start + timedelta(minutes=idx), open_value, close))
        price = close
    return pl.DataFrame(output)


def _fast_strategy() -> IndicatorStrategyConfig:
    return IndicatorStrategyConfig(
        cusum_sensitivity="Fast (Day Trade)",
        horizons=(2, 4, 8),
        aligned_score=0.05,
        aligned_quality=0.05,
        developing_score=0.01,
        change_risk_threshold=1.0,
        max_fast_slow_ratio=10.0,
        minimum_path_quality=0.01,
    )


def _protected_ledger(
    start: datetime,
    *,
    timeout_target_bars: int = 10,
) -> _ExecutionLedger:
    return _ExecutionLedger(
        costs=ReplayCostConfig(
            fee_bps=0.0,
            slippage_bps=0.0,
            spread_bps=0.0,
            execution_latency_minutes=0,
        ),
        evaluation_start=start,
        display_stride_minutes=1,
        event_limit=20,
        capture_series=True,
        protection=ProtectedReplayConfig(
            enabled=True,
            risk_unit_volatility_multiplier=1.0,
            stop_risk_units=1.0,
            target_risk_units=2.0,
            timeout_target_bars=timeout_target_bars,
        ),
        timeframe="1m",
    )


def _protected_order(
    timestamp: datetime,
    *,
    signal_id: str = "setup-1",
    target: float = 1.0,
    risk_unit: float = 10.0,
) -> dict[str, object]:
    return {
        "order_id": f"order-{signal_id}",
        "signal_id": signal_id,
        "eligible_at": timestamp,
        "desired_position": target,
        "reason": "test_protected_entry",
        "protected_risk_unit": risk_unit,
    }


def _test_meta_artifact(
    *,
    strategy: IndicatorStrategyConfig,
    costs: ReplayCostConfig,
    protection: ProtectedReplayConfig,
    created_at: datetime,
):
    row_count = 24
    feature_count = len(META_FEATURE_NAMES)
    matrix = np.asarray(
        [
            [
                math.sin((row_index + 1) * (column_index + 1) / 17.0)
                for column_index in range(feature_count)
            ]
            for row_index in range(row_count)
        ],
        dtype=float,
    )
    target = np.asarray([row_index % 2 for row_index in range(row_count)])
    fitted = fit_logistic_baseline(
        matrix,
        target,
        feature_names=META_FEATURE_NAMES,
    )
    trained_through = created_at - timedelta(days=2)
    return build_coefficient_artifact(
        fitted,
        model_version="test-meta-v1",
        policy_digest=meta_label_policy_digest(
            strategy=strategy,
            costs=costs,
            protection=protection,
            timeframe="1m",
        ),
        assets=("BTCUSDT",),
        timeframes=("1m",),
        trained_through=trained_through,
        label_mature_through=created_at - timedelta(days=1),
        created_at=created_at,
        decision_threshold=0.01,
    )


def test_untrained_prototype_risk_does_not_veto_execution_by_default() -> None:
    online = {
        "status": "ok",
        "trend_state_code": 2,
        "path_quality": 0.8,
        "fast_slow_ratio": 1.0,
        "regime_risk_active": True,
        "regime_state": 0,
    }
    cusum = {"regime": 1}

    desired, reason = _desired_position(
        online=online,
        cusum=cusum,
        strategy=IndicatorStrategyConfig(),
    )
    experimental, experimental_reason = _desired_position(
        online=online,
        cusum=cusum,
        strategy=IndicatorStrategyConfig(
            enable_experimental_prototype_regime_gate=True
        ),
    )

    assert desired > 0.0
    assert reason == "long_indicator_agreement"
    assert experimental == 0.0
    assert experimental_reason == "flat_prototype_change_risk"


def test_causal_candle_builder_uses_fixed_utc_boundary_and_ohlcv_rules() -> None:
    start = datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc)
    rows = [
        _minute_row(start, 100.0, 101.0),
        _minute_row(start + timedelta(minutes=1), 101.0, 99.0),
        _minute_row(start + timedelta(minutes=2), 99.0, 102.0),
    ]
    rows[1]["volume"] = 20.0
    rows[2]["volume"] = 30.0
    builder = CausalCandleBuilder("15m")

    for row in rows:
        assert builder.advance_to(row["timestamp"]) is None
        builder.add(row)

    assert builder.advance_to(start + timedelta(minutes=14, seconds=59)) is None
    closed = builder.advance_to(start + timedelta(minutes=15))

    assert closed is not None
    assert closed["timestamp"] == start
    assert closed["available_at"] == start + timedelta(minutes=15)
    assert closed["open"] == 100.0
    assert closed["high"] == pytest.approx(102.25)
    assert closed["low"] == pytest.approx(98.75)
    assert closed["close"] == 102.0
    assert closed["volume"] == 60.0
    assert closed["source_minute_count"] == 3
    assert target_bar_is_complete(closed, asset="ES", timeframe="15m") is False


def test_session_target_bar_requires_full_bucket_without_authoritative_calendar() -> (
    None
):
    start = datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc)
    builder = CausalCandleBuilder("15m")
    for offset in range(15):
        builder.add(_minute_row(start + timedelta(minutes=offset), 100.0, 100.0))
    closed = builder.advance_to(start + timedelta(minutes=15))

    assert closed is not None
    assert target_bar_is_complete(closed, asset="ES", timeframe="15m") is True


@pytest.mark.parametrize("timeframe", ["1m", "15m", "1h", "4h", "8h", "12h", "1d"])
def test_candle_builder_supports_every_canonical_timeframe(timeframe: str) -> None:
    builder = CausalCandleBuilder(timeframe)
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    row = _minute_row(start, 100.0, 101.0)

    builder.add(row)
    assert builder.advance_to(start + timedelta(seconds=builder.interval_seconds))


def test_replay_signals_are_filled_no_earlier_than_next_real_minute_open() -> None:
    frame = _trending_frame()
    start = frame["timestamp"].min()
    clock = frame["timestamp"].max() + timedelta(minutes=1)

    result = run_minute_replay(
        frame,
        asset="BTCUSDT",
        timeframe="5m",
        strategy=_fast_strategy(),
        costs=ReplayCostConfig(fee_bps=1.0, slippage_bps=1.0),
        evaluation_start=start + timedelta(minutes=250),
        replay_clock=clock,
    )

    assert result["fills"]
    signals = {row["signal_id"]: row for row in result["signals"]}
    source_opens = set(frame["timestamp"].dt.epoch("s").to_list())
    for fill in result["fills"]:
        signal = signals[fill["signal_id"]]
        eligible = datetime.fromisoformat(signal["eligible_at"].replace("Z", "+00:00"))
        assert fill["time"] >= int(eligible.timestamp())
        assert fill["time"] in source_opens
        assert fill["time"] > int(
            datetime.fromisoformat(
                signal["source_bar_open"].replace("Z", "+00:00")
            ).timestamp()
        )


def test_replay_excludes_synthetic_minutes_from_signals_and_fills() -> None:
    frame = _trending_frame(600)
    synthetic_timestamp = frame["timestamp"][400]
    frame = frame.with_columns(
        (pl.col("timestamp") == synthetic_timestamp).alias("is_synthetic_no_trade")
    )

    result = run_minute_replay(
        frame,
        asset="BTCUSDT",
        timeframe="1m",
        strategy=_fast_strategy(),
        evaluation_start=frame["timestamp"][200],
        replay_clock=frame["timestamp"].max() + timedelta(minutes=1),
    )

    assert result["metadata"]["excluded_synthetic_minutes"] == 1
    # The explicit replay clock is an observation cutoff. The last nominally
    # closed minute is still inside the declared five-second ingestion lag.
    assert result["metadata"]["processed_real_source_minutes"] == frame.height - 2
    assert result["metadata"]["replay_clock_semantics"] == ("actual_observation_cutoff")
    assert int(synthetic_timestamp.timestamp()) not in {
        fill["time"] for fill in result["fills"]
    }


def test_future_append_and_mutation_do_not_rewrite_prefix_signals_or_fills() -> None:
    frame = _trending_frame(1_400)
    start = frame["timestamp"].min()
    prefix_clock = start + timedelta(minutes=900)
    kwargs = {
        "asset": "BTCUSDT",
        "timeframe": "5m",
        "strategy": _fast_strategy(),
        "evaluation_start": start + timedelta(minutes=250),
        "replay_clock": prefix_clock,
    }
    prefix = run_minute_replay(frame, **kwargs)
    mutated = frame.with_columns(
        pl.when(pl.col("timestamp") >= prefix_clock)
        .then(pl.col("close") * 10.0)
        .otherwise(pl.col("close"))
        .alias("close")
    )
    mutated_prefix = run_minute_replay(mutated, **kwargs)

    assert mutated_prefix["signals"] == prefix["signals"]
    assert mutated_prefix["fills"] == prefix["fills"]
    assert mutated_prefix["metrics"] == prefix["metrics"]


def test_explicit_costs_reduce_equity_without_changing_signal_path() -> None:
    frame = _trending_frame()
    start = frame["timestamp"].min()
    common = {
        "asset": "BTCUSDT",
        "timeframe": "5m",
        "strategy": _fast_strategy(),
        "evaluation_start": start + timedelta(minutes=250),
        "replay_clock": frame["timestamp"].max() + timedelta(minutes=1),
    }
    free = run_minute_replay(
        frame,
        costs=ReplayCostConfig(fee_bps=0.0, slippage_bps=0.0),
        **common,
    )
    costed = run_minute_replay(
        frame,
        costs=ReplayCostConfig(fee_bps=5.0, slippage_bps=5.0),
        **common,
    )

    assert [row["signal_id"] for row in free["signals"]] == [
        row["signal_id"] for row in costed["signals"]
    ]
    assert [row["to_position"] for row in free["fills"]] == [
        row["to_position"] for row in costed["fills"]
    ]
    assert costed["metrics"]["final_equity"] < free["metrics"]["final_equity"]
    assert costed["metrics"]["total_cost_pct_of_initial"] > 0.0


def test_replay_payload_is_explicitly_current_revision_and_not_profit_claim() -> None:
    frame = _trending_frame(500)
    result = run_minute_replay(
        frame,
        asset="ES",
        timeframe="15m",
        strategy=_fast_strategy(),
        evaluation_start=frame["timestamp"][200],
        replay_clock=frame["timestamp"].max() + timedelta(minutes=1),
    )

    metadata = result["metadata"]
    assert metadata["validation_safe"] is False
    assert metadata["as_was_live_journal"] is False
    assert metadata["profitability_guaranteed"] is False
    assert metadata["normalized_economic_proxy"] is True
    assert "not an as-was-live" in metadata["validation_warning"]


@pytest.mark.parametrize("latency_minutes", [1, 2, 5])
def test_one_minute_replay_keeps_pending_order_until_latency_fill(
    latency_minutes: int,
) -> None:
    frame = _trending_frame(700)
    start = frame["timestamp"].min()

    result = run_minute_replay(
        frame,
        asset="BTCUSDT",
        timeframe="1m",
        strategy=_fast_strategy(),
        costs=ReplayCostConfig(
            fee_bps=0.0,
            slippage_bps=0.0,
            execution_latency_minutes=latency_minutes,
        ),
        evaluation_start=start + timedelta(minutes=200),
        replay_clock=frame["timestamp"].max() + timedelta(minutes=1),
    )

    assert result["metrics"]["fill_count"] > 0
    assert result["metrics"]["order_suppressed_pending_count"] > 0
    assert all(
        fill["time"]
        >= int(
            datetime.fromisoformat(
                fill["eligible_at"].replace("Z", "+00:00")
            ).timestamp()
        )
        for fill in result["fills"]
    )


def test_continuous_market_incomplete_target_bar_is_never_signaled() -> None:
    frame = _trending_frame(600)
    missing_timestamp = frame["timestamp"][302]
    frame = frame.filter(pl.col("timestamp") != missing_timestamp)
    start = frame["timestamp"].min()

    result = run_minute_replay(
        frame,
        asset="BTCUSDT",
        timeframe="5m",
        strategy=_fast_strategy(),
        evaluation_start=start + timedelta(minutes=200),
        replay_clock=frame["timestamp"].max() + timedelta(minutes=1),
    )

    assert result["metadata"]["continuous_source_gap_count"] == 1
    assert result["metadata"]["missing_continuous_source_minutes"] == 1
    assert result["metadata"]["suppressed_incomplete_target_bars"] == 1
    assert (
        result["metadata"]["target_bar_completeness_counts"]["continuous_incomplete"]
        == 1
    )
    assert all(signal["source_minute_count"] == 5 for signal in result["signals"])


def test_replay_event_evidence_is_bounded_without_changing_metrics() -> None:
    frame = _trending_frame(900)
    start = frame["timestamp"].min()
    common = {
        "asset": "BTCUSDT",
        "timeframe": "1m",
        "strategy": _fast_strategy(),
        "evaluation_start": start + timedelta(minutes=200),
        "replay_clock": frame["timestamp"].max() + timedelta(minutes=1),
    }

    retained = run_minute_replay(
        frame,
        event_limit=3,
        capture_series=True,
        **common,
    )
    metrics_only = run_minute_replay(
        frame,
        event_limit=0,
        capture_series=False,
        **common,
    )

    assert retained["metrics"] == metrics_only["metrics"]
    assert len(retained["signals"]) <= 3
    assert len(retained["orders"]) <= 3
    assert len(retained["fills"]) <= 3
    assert len(retained["markers"]) <= 3
    assert retained["metadata"]["event_retention"]["signals"]["truncated"]
    assert retained["metadata"]["event_retention"]["fills"]["truncated"]
    assert metrics_only["signals"] == []
    assert metrics_only["orders"] == []
    assert metrics_only["fills"] == []
    assert metrics_only["equity"] == []
    assert metrics_only["metadata"]["series_retention"]["captured"] is False


def test_flat_round_trip_basis_includes_entry_and_exit_costs() -> None:
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    ledger = _ExecutionLedger(
        costs=ReplayCostConfig(
            fee_bps=10.0,
            slippage_bps=0.0,
            spread_bps=0.0,
            execution_latency_minutes=0,
        ),
        evaluation_start=start,
        display_stride_minutes=1,
        event_limit=10,
        capture_series=True,
    )
    opening_order = {
        "order_id": "open",
        "signal_id": "signal-open",
        "eligible_at": start,
        "desired_position": 1.0,
        "reason": "test_open",
    }
    closing_order = {
        "order_id": "close",
        "signal_id": "signal-close",
        "eligible_at": start + timedelta(minutes=1),
        "desired_position": 0.0,
        "reason": "test_close",
    }

    assert (
        ledger.process_minute(
            row=_minute_row(start, 100.0, 100.0),
            pending_signal=opening_order,
        )
        is None
    )
    assert ledger.entry_equity == pytest.approx(1.0)
    assert (
        ledger.process_minute(
            row=_minute_row(start + timedelta(minutes=1), 100.0, 100.0),
            pending_signal=closing_order,
        )
        is None
    )

    metrics = ledger.result()["metrics"]
    assert metrics["final_equity"] == pytest.approx(0.998001)
    assert metrics["gross_total_return_pct"] == pytest.approx(0.0)
    assert metrics["round_trip_count"] == 1
    assert metrics["round_trip_win_rate_pct"] == pytest.approx(0.0)


def test_protected_replay_uses_stop_first_for_ambiguous_minute() -> None:
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    ledger = _protected_ledger(start)

    assert (
        ledger.process_minute(
            row={
                "timestamp": start,
                "open": 100.0,
                "high": 105.0,
                "low": 95.0,
                "close": 100.0,
            },
            pending_signal=_protected_order(start),
        )
        is None
    )
    ledger.process_minute(
        row={
            "timestamp": start + timedelta(minutes=1),
            "open": 100.0,
            "high": 125.0,
            "low": 85.0,
            "close": 110.0,
        },
        pending_signal=None,
    )

    result = ledger.result()
    assert result["metrics"]["protected_ambiguous_count"] == 1
    assert result["metrics"]["protected_target_count"] == 0
    assert result["metrics"]["open_position"] == 0.0
    assert result["metrics"]["final_equity"] == pytest.approx(0.9)
    evaluation = result["barrier_evaluations"][0]
    assert evaluation["outcome"] == "AMBIGUOUS"
    assert evaluation["primary_outcome"] == "STOP"
    assert evaluation["optimistic_outcome"] == "TARGET"
    assert evaluation["label_known_at"] == "2025-01-01T00:02:00Z"
    assert result["fills"][-1]["exit_reason"] == "protected_stop"


def test_existing_gap_stop_cancels_same_minute_reversal_order() -> None:
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    ledger = _protected_ledger(start)
    ledger.process_minute(
        row={
            "timestamp": start,
            "open": 100.0,
            "high": 105.0,
            "low": 95.0,
            "close": 100.0,
        },
        pending_signal=_protected_order(start),
    )
    reversal = _protected_order(
        start + timedelta(minutes=1),
        signal_id="setup-2",
        target=-1.0,
    )
    assert (
        ledger.process_minute(
            row={
                "timestamp": start + timedelta(minutes=1),
                "open": 85.0,
                "high": 87.0,
                "low": 80.0,
                "close": 82.0,
            },
            pending_signal=reversal,
        )
        is None
    )

    result = ledger.result()
    assert result["metrics"]["protected_stop_count"] == 1
    assert result["metrics"]["open_position"] == 0.0
    assert result["metrics"]["final_equity"] == pytest.approx(0.85)
    assert reversal["order_status"] == "cancelled_protective_exit"
    assert result["barrier_evaluations"][0]["gap_through"] is True


def test_protected_unknown_source_path_is_cancelled_flattened_and_invalidated() -> None:
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    ledger = _protected_ledger(start)
    ledger.process_minute(
        row=_minute_row(start, 100.0, 100.0),
        pending_signal=_protected_order(start),
    )

    ledger.process_minute(
        row=_minute_row(start + timedelta(minutes=2), 101.0, 101.0),
        pending_signal=None,
        observed_at=start + timedelta(minutes=3),
        unknown_path_gap_at=start + timedelta(minutes=1),
    )

    result = ledger.result()
    metrics = result["metrics"]
    assert metrics["protected_cancel_count"] == 1
    assert metrics["protected_unknown_path_gap_count"] == 1
    assert metrics["protected_performance_path_valid"] is False
    assert metrics["open_position"] == pytest.approx(0.0)
    evaluation = result["barrier_evaluations"][0]
    assert evaluation["outcome"] == "CANCELLED"
    assert evaluation["reason"] == "protected_market_data_gap_unknown_path"
    assert evaluation["occurred_at"] == "2025-01-01T00:01:00Z"
    assert evaluation["label_known_at"] == "2025-01-01T00:03:00Z"
    assert result["fills"][-1]["exit_reason"] == (
        "protected_data_gap_reconciliation_flatten"
    )
    assert result["fills"][-1]["performance_path_valid"] is False


def test_protected_timeout_counts_finalized_selected_timeframe_bars() -> None:
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    ledger = _protected_ledger(start, timeout_target_bars=2)
    ledger.process_minute(
        row={
            "timestamp": start,
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.0,
        },
        pending_signal=_protected_order(start),
    )
    ledger.advance_protected_target_bar(
        bar={"timestamp": start, "close": 100.0},
        observed_at=start + timedelta(minutes=1),
    )
    ledger.process_minute(
        row={
            "timestamp": start + timedelta(minutes=1),
            "open": 100.0,
            "high": 102.0,
            "low": 99.0,
            "close": 101.0,
        },
        pending_signal=None,
    )
    ledger.advance_protected_target_bar(
        bar={"timestamp": start + timedelta(minutes=1), "close": 101.0},
        observed_at=start + timedelta(minutes=2),
    )

    result = ledger.result()
    assert result["metrics"]["protected_timeout_count"] == 1
    assert result["metrics"]["open_position"] == 0.0
    assert result["metrics"]["final_equity"] == pytest.approx(1.01)
    evaluation = result["barrier_evaluations"][0]
    assert evaluation["outcome"] == "TIMEOUT"
    assert evaluation["label_known_at"] == "2025-01-01T00:02:00Z"
    assert result["fills"][-1]["timestamp"] == "2025-01-01T00:02:00Z"


def test_meta_shadow_scores_only_with_an_artifact_available_at_event_time() -> None:
    frame = _trending_frame(900)
    start = frame["timestamp"].min()
    strategy = _fast_strategy()
    costs = ReplayCostConfig()
    protection = ProtectedReplayConfig(enabled=True)
    artifact = _test_meta_artifact(
        strategy=strategy,
        costs=costs,
        protection=protection,
        created_at=start - timedelta(days=1),
    )

    replay = run_minute_replay(
        frame,
        asset="BTCUSDT",
        timeframe="1m",
        strategy=strategy,
        costs=costs,
        protection=protection,
        meta_filter_mode="shadow",
        meta_artifact=artifact,
        evaluation_start=start + timedelta(minutes=200),
        replay_clock=frame["timestamp"].max() + timedelta(minutes=1),
        event_limit=200,
    )

    assert replay["metrics"]["meta_candidate_count"] > 0
    assert replay["metrics"]["meta_scored_count"] > 0
    assert replay["metrics"]["meta_unavailable_count"] == 0
    assert replay["meta_scores"]
    assert all(0.0 <= point["value"] <= 1.0 for point in replay["meta_scores"])
    meta_records = [
        record
        for key in ("pending", "active", "resolved")
        for record in replay["meta_label_book"][key]
    ]
    assert meta_records
    assert all(
        record["candidate"]["features"]["cusum_available_at"]
        == record["candidate"]["decision_at"]
        for record in meta_records
    )
    assert all(
        event["stored_at_event_time"] is True
        and event["model_version"] == "test-meta-v1"
        for event in replay["meta_score_events"]
    )
    meta_config = replay["config"]["meta_filter"]
    assert meta_config["artifact_status"] == "loaded_compatible"
    assert meta_config["artifact_checksum"] == artifact.checksum
    assert meta_config["decision_threshold"] == artifact.decision_threshold
    assert meta_config["trained_through"].endswith("Z")
    assert meta_config["label_mature_through"].endswith("Z")
    assert meta_config["entry_gate_rule"] == (
        "strictly_above_max_model_and_static_stop_threshold_with_margin"
    )
    assert meta_config["break_even_safety_margin"] == pytest.approx(0.05)


def test_strategy_reversal_cannot_override_an_active_protected_bracket() -> None:
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    ledger = _protected_ledger(start)
    ledger.process_minute(
        row={
            "timestamp": start,
            "open": 100.0,
            "high": 105.0,
            "low": 95.0,
            "close": 101.0,
        },
        pending_signal=_protected_order(start),
    )
    reversal = _protected_order(
        start + timedelta(minutes=1),
        signal_id="opposite-setup",
        target=-1.0,
    )

    returned = ledger.process_minute(
        row={
            "timestamp": start + timedelta(minutes=1),
            "open": 101.0,
            "high": 106.0,
            "low": 96.0,
            "close": 102.0,
        },
        pending_signal=reversal,
    )

    assert returned is None
    assert reversal["order_status"] == "suppressed_active_protected_bracket"
    assert ledger.position == pytest.approx(1.0)
    assert ledger.active_barrier is not None
    assert ledger.result()["metrics"]["protected_cancel_count"] == 0


def test_meta_policy_family_is_timeframe_invariant_but_rejects_unknown_timeframe() -> (
    None
):
    strategy = _fast_strategy()
    costs = ReplayCostConfig()
    protection = ProtectedReplayConfig(enabled=True)

    digests = {
        meta_label_policy_digest(
            strategy=strategy,
            costs=costs,
            protection=protection,
            timeframe=timeframe,
        )
        for timeframe in ("1m", "15m", "1h", "4h", "8h", "12h", "1d")
    }

    assert len(digests) == 1
    with pytest.raises(ValueError, match="Unsupported timeframe"):
        meta_label_policy_digest(
            strategy=strategy,
            costs=costs,
            protection=protection,
            timeframe="7m",
        )


def test_meta_shadow_refuses_to_rescore_history_with_future_artifact() -> None:
    frame = _trending_frame(600)
    start = frame["timestamp"].min()
    strategy = _fast_strategy()
    costs = ReplayCostConfig()
    protection = ProtectedReplayConfig(enabled=True)
    artifact = _test_meta_artifact(
        strategy=strategy,
        costs=costs,
        protection=protection,
        created_at=start + timedelta(days=30),
    )

    replay = run_minute_replay(
        frame,
        asset="BTCUSDT",
        timeframe="1m",
        strategy=strategy,
        costs=costs,
        protection=protection,
        meta_filter_mode="shadow",
        meta_artifact=artifact,
        evaluation_start=start + timedelta(minutes=200),
        replay_clock=frame["timestamp"].max() + timedelta(minutes=1),
        event_limit=200,
    )

    assert replay["metrics"]["meta_candidate_count"] > 0
    assert replay["metrics"]["meta_scored_count"] == 0
    assert replay["meta_scores"] == []
    assert {event["reason"] for event in replay["meta_score_events"]} == {
        "artifact_created_after_decision"
    }
