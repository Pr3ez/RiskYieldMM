from __future__ import annotations

import json
import math
import sys
from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ANALYST_ROOT = (
    Path(__file__).resolve().parents[1] / "Risk_Yield_Meta_Model_Analyst_0_0_1"
)
if str(ANALYST_ROOT) not in sys.path:
    sys.path.insert(0, str(ANALYST_ROOT))

from trade_ml import (  # noqa: E402
    META_FEATURE_NAMES,
    BarrierConfig,
    BarrierOutcome,
    BarrierTracker,
    MinuteBar,
    TradeSide,
    activate_barrier_plan,
    build_feature_snapshot,
    cancel_barrier_plan,
    evaluate_barriers,
)

BASE = datetime(2026, 1, 2, 12, 0, tzinfo=timezone.utc)


def _plan(
    side: TradeSide = TradeSide.LONG,
    *,
    timeout_target_bars: int = 3,
    target_interval_seconds: int = 60,
):
    return activate_barrier_plan(
        setup_id=f"setup-{side.value.lower()}",
        side=side,
        fill_price=100.0,
        risk_unit=2.0,
        activated_at=BASE,
        config=BarrierConfig(
            stop_risk_units=1.0,
            target_risk_units=2.0,
            timeout_target_bars=timeout_target_bars,
            target_interval_seconds=target_interval_seconds,
        ),
    )


def _bar(
    minute: int,
    *,
    open: float = 100.0,
    high: float = 101.0,
    low: float = 99.0,
    close: float = 100.0,
) -> MinuteBar:
    return MinuteBar(
        timestamp=BASE + timedelta(minutes=minute),
        open=open,
        high=high,
        low=low,
        close=close,
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("stop_risk_units", 0.0),
        ("stop_risk_units", math.inf),
        ("target_risk_units", -1.0),
        ("target_risk_units", math.nan),
        ("timeout_target_bars", 0),
        ("timeout_target_bars", True),
        ("timeout_target_bars", 2.5),
        ("target_interval_seconds", 0),
        ("target_interval_seconds", True),
        ("target_interval_seconds", 2.5),
    ],
)
def test_barrier_config_is_frozen_validated_and_json_stable(field, value) -> None:
    kwargs = {
        "stop_risk_units": 1.0,
        "target_risk_units": 2.0,
        "timeout_target_bars": 3,
        "target_interval_seconds": 60,
    }
    kwargs[field] = value
    with pytest.raises(ValueError):
        BarrierConfig(**kwargs)

    config = BarrierConfig(timeout_target_bars=3, target_interval_seconds=60)
    json.dumps(config.as_dict(), allow_nan=False)
    assert (
        config.digest()
        == BarrierConfig(
            timeout_target_bars=3,
            target_interval_seconds=60,
        ).digest()
    )
    assert config.as_dict()["timeout_clock"] == "accepted_finalized_target_bars"
    with pytest.raises(FrozenInstanceError):
        config.timeout_target_bars = 4  # type: ignore[misc]


def test_barriers_activate_from_actual_fill_for_both_sides_and_are_immutable() -> None:
    long_plan = _plan(TradeSide.LONG)
    short_plan = _plan(TradeSide.SHORT)

    assert (long_plan.stop_price, long_plan.target_price) == (98.0, 104.0)
    assert (short_plan.stop_price, short_plan.target_price) == (102.0, 96.0)
    assert long_plan.as_dict()["activated_at"] == "2026-01-02T12:00:00Z"
    json.dumps(long_plan.as_dict(), allow_nan=False)
    with pytest.raises(FrozenInstanceError):
        long_plan.stop_price = 90.0  # type: ignore[misc]


def test_persisted_barrier_contracts_require_exact_current_schema_version() -> None:
    config = BarrierConfig(timeout_target_bars=3, target_interval_seconds=60)
    plan = _plan()
    evaluation = evaluate_barriers(
        plan,
        [_bar(1, open=100.0, high=105.0, low=99.0, close=104.0)],
    )
    assert evaluation is not None

    persisted_contracts = (
        (BarrierConfig.from_dict, config.as_dict()),
        (type(plan).from_dict, plan.as_dict()),
        (type(evaluation).from_dict, evaluation.as_dict()),
    )
    for restore, payload in persisted_contracts:
        assert restore(payload).as_dict() == payload
        for stale_version in (None, "legacy_contract_v1"):
            stale = dict(payload)
            if stale_version is None:
                stale.pop("schema_version")
            else:
                stale["schema_version"] = stale_version
            with pytest.raises(ValueError, match="unsupported .* schema_version"):
                restore(stale)


def test_gap_through_uses_open_for_long_stop_and_short_target() -> None:
    long_result = evaluate_barriers(
        _plan(TradeSide.LONG),
        [_bar(1, open=97.0, high=100.0, low=96.0, close=99.0)],
    )
    short_result = evaluate_barriers(
        _plan(TradeSide.SHORT),
        [_bar(1, open=95.0, high=97.0, low=94.0, close=96.0)],
    )

    assert long_result is not None
    assert long_result.outcome is BarrierOutcome.STOP
    assert long_result.exit_price == 97.0
    assert long_result.gap_through is True
    assert long_result.default_binary_label == 0
    assert short_result is not None
    assert short_result.outcome is BarrierOutcome.TARGET
    assert short_result.exit_price == 95.0
    assert short_result.gap_through is True
    assert short_result.default_binary_label == 1


def test_single_bar_both_touch_is_ambiguous_with_stop_first_primary() -> None:
    result = evaluate_barriers(
        _plan(),
        [_bar(1, open=100.0, high=105.0, low=97.0, close=101.0)],
    )

    assert result is not None
    assert result.outcome is BarrierOutcome.AMBIGUOUS
    assert result.primary_outcome is BarrierOutcome.STOP
    assert result.optimistic_outcome is BarrierOutcome.TARGET
    assert result.exit_price == 98.0
    assert result.optimistic_exit_price == 104.0
    assert result.same_bar_ambiguous is True
    assert result.optimistic_target_possible is True
    assert result.default_binary_label == 0


def test_normal_first_touch_target_has_target_binary_label() -> None:
    result = evaluate_barriers(
        _plan(),
        [
            _bar(1),
            _bar(2, open=101.0, high=104.5, low=100.0, close=104.0),
        ],
    )

    assert result is not None
    assert result.outcome is BarrierOutcome.TARGET
    assert result.primary_outcome is BarrierOutcome.TARGET
    assert result.exit_price == 104.0
    assert result.observed_bars == 2
    assert result.default_binary_label == 1
    assert result.occurred_at == BASE + timedelta(minutes=2)
    assert result.label_known_at == BASE + timedelta(minutes=3)


def test_timeout_counts_only_accepted_finalized_target_bars() -> None:
    plan = _plan(timeout_target_bars=2, target_interval_seconds=300)
    tracker = BarrierTracker(plan)

    # Five execution minutes do not consume the vertical horizon themselves.
    for minute in range(5):
        assert tracker.update(_bar(minute)) is None
    assert tracker.target_bars_elapsed == 0

    assert (
        tracker.advance_target_bar(
            bar_open=BASE,
            close_price=100.0,
            observed_at=BASE + timedelta(minutes=5),
        )
        is None
    )
    assert tracker.target_bars_elapsed == 1

    # The second accepted 5-minute candle closes the two-target-bar horizon.
    for minute in range(5, 10):
        assert tracker.update(_bar(minute)) is None
    result = tracker.advance_target_bar(
        bar_open=BASE + timedelta(minutes=5),
        close_price=101.0,
        observed_at=BASE + timedelta(minutes=10, seconds=7),
    )
    assert result is not None
    assert result.outcome is BarrierOutcome.TIMEOUT
    assert result.exit_price == 101.0
    assert result.observed_bars == 10
    assert result.default_binary_label == 0
    assert result.occurred_at == BASE + timedelta(minutes=10)
    assert result.label_known_at == BASE + timedelta(minutes=10, seconds=7)
    assert tracker.target_bars_elapsed == 2


def test_last_constituent_barrier_touch_wins_before_target_bar_timeout() -> None:
    tracker = BarrierTracker(_plan(timeout_target_bars=1, target_interval_seconds=300))
    for minute in range(4):
        assert tracker.update(_bar(minute)) is None

    target = tracker.update(
        _bar(4, high=104.5, close=104.0),
        observed_at=BASE + timedelta(minutes=5),
    )
    assert target is not None
    assert target.outcome is BarrierOutcome.TARGET

    # The target timeframe candle is counted only after all constituent minute
    # touches have been evaluated, so it cannot overwrite the first touch.
    assert (
        tracker.advance_target_bar(
            bar_open=BASE,
            close_price=104.0,
            observed_at=BASE + timedelta(minutes=5),
        )
        is target
    )


def test_label_known_at_uses_delayed_observation_clock() -> None:
    tracker = BarrierTracker(_plan())
    observed_at = BASE + timedelta(minutes=2, seconds=37)
    result = tracker.update(
        _bar(1, high=104.5, close=104.0),
        observed_at=observed_at,
    )

    assert result is not None
    assert result.occurred_at == BASE + timedelta(minutes=1)
    assert result.label_known_at == observed_at
    restored = BarrierTracker.from_snapshot(tracker.snapshot())
    assert restored.terminal is not None
    assert restored.terminal.label_known_at == observed_at


def test_label_availability_respects_explicit_bar_interval() -> None:
    result = evaluate_barriers(
        _plan(),
        [_bar(1, open=100.0, high=104.5, low=99.0, close=104.0)],
        bar_interval_seconds=300,
    )
    assert result is not None
    assert result.label_known_at == result.occurred_at + timedelta(minutes=5)
    with pytest.raises(ValueError, match="positive integer"):
        evaluate_barriers(_plan(), [], bar_interval_seconds=0)


def test_incremental_tracker_matches_batch_and_restores_without_rescan() -> None:
    plan = _plan()
    bars = [
        _bar(1),
        _bar(2, open=101.0, high=104.5, low=100.0, close=104.0),
    ]
    batch = evaluate_barriers(plan, bars)

    tracker = BarrierTracker(plan)
    assert tracker.update(bars[0]) is None
    snapshot = tracker.snapshot()
    json.dumps(snapshot, allow_nan=False)
    restored = BarrierTracker.from_snapshot(snapshot)
    incremental = restored.update(bars[1])

    assert batch is not None
    assert incremental is not None
    assert incremental.as_dict() == batch.as_dict()
    assert restored.observed_bars == 2
    assert restored.last_timestamp == bars[1].timestamp
    assert restored.terminal is incremental
    assert restored.update(_bar(3)) is incremental

    tampered = dict(snapshot)
    tampered["observed_bars"] = 2
    with pytest.raises(ValueError, match="checksum"):
        BarrierTracker.from_snapshot(tampered)


def test_cancelled_plan_is_explicit_and_excluded_from_binary_training_label() -> None:
    result = cancel_barrier_plan(
        _plan(),
        cancelled_at=BASE + timedelta(seconds=30),
        observed_at=BASE + timedelta(minutes=2),
        reason="entry_order_voided",
    )

    assert result.outcome is BarrierOutcome.CANCELLED
    assert result.primary_outcome is BarrierOutcome.CANCELLED
    assert result.exit_price is None
    assert result.default_binary_label is None
    assert result.label_known_at == BASE + timedelta(minutes=2)
    json.dumps(result.as_dict(), allow_nan=False)
    assert result.digest() == result.digest()


def test_bar_evaluation_rejects_pre_activation_or_unordered_bars() -> None:
    plan = _plan()
    with pytest.raises(ValueError, match="precedes"):
        evaluate_barriers(
            plan,
            [MinuteBar(BASE - timedelta(minutes=1), 100.0, 101.0, 99.0, 100.0)],
        )
    with pytest.raises(ValueError, match="strictly increasing"):
        evaluate_barriers(plan, [_bar(2), _bar(1)])


def _indicator_inputs() -> tuple[dict[str, object], dict[str, object]]:
    online: dict[str, object] = {
        "source_timestamp": BASE,
        "timestamp": BASE + timedelta(minutes=1),
        "available_at": BASE + timedelta(minutes=1),
        "earliest_execution_at": BASE + timedelta(minutes=1),
        "status": "ok",
        "log_return": 0.01,
        "trend_score": 0.6,
        "trend_agreement": 1.0,
        "trend_state_code": 2,
        "path_quality": 0.8,
        "trend_z_fast": 1.5,
        "trend_z_medium": 1.0,
        "trend_z_slow": 0.5,
        "path_efficiency_fast": 0.7,
        "path_efficiency_medium": 0.6,
        "path_efficiency_slow": 0.5,
        "trend_component_fast": 0.7,
        "trend_component_medium": 0.5,
        "trend_component_slow": 0.3,
        "ewma_vol_fast_pct": 1.2,
        "ewma_vol_medium_pct": 1.0,
        "ewma_vol_slow_pct": 0.8,
        "fast_slow_ratio": 1.5,
        "volatility_pressure": 0.4,
        "range_pressure": 0.3,
        "regime_change_risk": 0.2,
        "regime_entropy": 0.25,
        "regime_state_duration_bars": 7,
        "regime_probability_bull": 0.7,
        "regime_probability_bear": 0.1,
        "regime_probability_range": 0.15,
        "regime_probability_transition": 0.05,
        "regime_confidence": 0.7,
    }
    cusum: dict[str, object] = {
        "timestamp": BASE,
        "available_at": BASE + timedelta(minutes=1),
        "status": "ok",
        "residual": 2.0,
        "res_std": 0.5,
        "bull_pressure": 0.7,
        "bear_pressure": 0.2,
        "pressure_pct": 75.0,
        "regime": 1,
        "bull_start": True,
        "bear_start": False,
        "scale_ready": True,
    }
    return online, cusum


def test_feature_snapshot_is_causal_ordered_side_aware_and_json_safe() -> None:
    online, cusum = _indicator_inputs()
    decision = BASE + timedelta(minutes=1)
    long_snapshot = build_feature_snapshot(
        setup_id="long-candidate",
        side=TradeSide.LONG,
        decision_at=decision,
        online=online,
        cusum=cusum,
    )
    short_snapshot = build_feature_snapshot(
        setup_id="short-candidate",
        side=TradeSide.SHORT,
        decision_at=decision,
        online=online,
        cusum=cusum,
    )
    long_features = long_snapshot.feature_map()
    short_features = short_snapshot.feature_map()

    assert long_snapshot.feature_names == META_FEATURE_NAMES
    assert tuple(long_features) == META_FEATURE_NAMES
    assert long_features["trend_score_directional"] == pytest.approx(0.6)
    assert short_features["trend_score_directional"] == pytest.approx(-0.6)
    assert long_features["cusum_regime_alignment"] == pytest.approx(1.0)
    assert short_features["cusum_regime_alignment"] == pytest.approx(-1.0)
    assert long_features["cusum_standardized_residual_directional"] == 4.0
    assert short_features["cusum_standardized_residual_directional"] == -4.0
    assert long_features["cusum_pressure_balance_directional"] == pytest.approx(0.5)
    assert short_features["cusum_pressure_balance_directional"] == pytest.approx(-0.5)
    assert long_features["cusum_pressure_fraction"] == 0.75
    assert long_features["cusum_same_side_start"] == 1.0
    assert short_features["cusum_same_side_start"] == 0.0
    assert not any(name.startswith("regime_") for name in META_FEATURE_NAMES)

    payload = long_snapshot.as_dict()
    json.dumps(payload, allow_nan=False)
    assert payload["feature_names"] == list(META_FEATURE_NAMES)
    assert list(payload["features"]) == list(META_FEATURE_NAMES)
    assert long_snapshot.cusum_source_timestamp == BASE
    assert long_snapshot.cusum_available_at == decision
    assert payload["cusum_available_at"] == decision.isoformat().replace("+00:00", "Z")
    assert (
        long_snapshot.digest()
        == build_feature_snapshot(
            setup_id="long-candidate",
            side=TradeSide.LONG,
            decision_at=decision,
            online=online,
            cusum=cusum,
        ).digest()
    )

    # The fixed prototype HMM is a chart diagnostic, not money confidence.
    # Its outputs must not change or invalidate the first meta-model snapshot.
    prototype_mutation = dict(online)
    prototype_mutation.update(
        {
            "regime_change_risk": math.nan,
            "regime_entropy": math.nan,
            "regime_state_duration_bars": -100,
            "regime_probability_bull": math.nan,
            "regime_probability_bear": math.nan,
            "regime_probability_range": math.nan,
            "regime_probability_transition": math.nan,
            "regime_confidence": math.nan,
        }
    )
    assert (
        long_snapshot.digest()
        == build_feature_snapshot(
            setup_id="long-candidate",
            side=TradeSide.LONG,
            decision_at=decision,
            online=prototype_mutation,
            cusum=cusum,
        ).digest()
    )


def test_feature_snapshot_rejects_future_or_nonfinite_input() -> None:
    online, cusum = _indicator_inputs()
    online["earliest_execution_at"] = BASE + timedelta(minutes=2)
    with pytest.raises(ValueError, match="not available"):
        build_feature_snapshot(
            setup_id="future",
            side=TradeSide.LONG,
            decision_at=BASE + timedelta(minutes=1),
            online=online,
            cusum=cusum,
        )

    online, cusum = _indicator_inputs()
    online["trend_score"] = math.nan
    with pytest.raises(ValueError, match="finite"):
        build_feature_snapshot(
            setup_id="nonfinite",
            side=TradeSide.LONG,
            decision_at=BASE + timedelta(minutes=1),
            online=online,
            cusum=cusum,
        )


def test_feature_snapshot_requires_explicit_indicator_availability() -> None:
    online, cusum = _indicator_inputs()
    online.pop("available_at")
    with pytest.raises(ValueError, match="online requires.*available_at"):
        build_feature_snapshot(
            setup_id="missing-online-availability",
            side=TradeSide.LONG,
            decision_at=BASE + timedelta(minutes=1),
            online=online,
            cusum=cusum,
        )

    online, cusum = _indicator_inputs()
    cusum.pop("available_at")
    with pytest.raises(ValueError, match="cusum requires.*available_at"):
        build_feature_snapshot(
            setup_id="missing-cusum-availability",
            side=TradeSide.LONG,
            decision_at=BASE + timedelta(minutes=1),
            online=online,
            cusum=cusum,
        )


def test_feature_snapshot_rejects_availability_outside_causal_interval() -> None:
    online, cusum = _indicator_inputs()
    cusum["available_at"] = BASE - timedelta(seconds=1)
    with pytest.raises(ValueError, match="cusum availability precedes"):
        build_feature_snapshot(
            setup_id="cusum-available-before-source",
            side=TradeSide.LONG,
            decision_at=BASE + timedelta(minutes=1),
            online=online,
            cusum=cusum,
        )

    online, cusum = _indicator_inputs()
    cusum["available_at"] = BASE + timedelta(minutes=1, seconds=1)
    with pytest.raises(ValueError, match="not available at decision_at"):
        build_feature_snapshot(
            setup_id="cusum-available-after-decision",
            side=TradeSide.LONG,
            decision_at=BASE + timedelta(minutes=1),
            online=online,
            cusum=cusum,
        )


def test_feature_snapshot_includes_decision_known_trade_geometry_and_cost() -> None:
    online, cusum = _indicator_inputs()
    snapshot = build_feature_snapshot(
        setup_id="geometry",
        side=TradeSide.LONG,
        decision_at=BASE + timedelta(minutes=1),
        online=online,
        cusum=cusum,
        entry_reference=100.0,
        risk_unit=2.0,
        stop_risk_units=1.0,
        target_risk_units=2.5,
        timeout_target_bars=20,
        target_interval_seconds=900,
        estimated_roundtrip_cost_bps=4.5,
    )
    features = snapshot.feature_map()
    assert features["risk_unit_fraction"] == pytest.approx(0.02)
    assert features["stop_risk_units"] == 1.0
    assert features["target_risk_units"] == 2.5
    assert features["timeout_horizon_minutes_log1p"] == pytest.approx(
        math.log1p(20 * 15)
    )
    assert features["estimated_roundtrip_cost_bps"] == 4.5

    with pytest.raises(ValueError, match="positive"):
        build_feature_snapshot(
            setup_id="bad-geometry",
            side=TradeSide.LONG,
            decision_at=BASE + timedelta(minutes=1),
            online=online,
            cusum=cusum,
            entry_reference=0.0,
        )
