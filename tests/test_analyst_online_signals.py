from __future__ import annotations

import copy
import hashlib
import json
import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import polars as pl
import pytest

ANALYST_ROOT = (
    Path(__file__).resolve().parents[1] / "Risk_Yield_Meta_Model_Analyst_0_0_1"
)
if str(ANALYST_ROOT) not in sys.path:
    sys.path.insert(0, str(ANALYST_ROOT))

import chart_export as chart_export_module  # noqa: E402
import live_signal_service as live_service_module  # noqa: E402
from chart_config import (  # noqa: E402
    CANONICAL_SOURCE,
    CORE_ASSETS,
    build_chart_manifest,
    resolve_ohlcv_files,
    timeframe_seconds,
)
from chart_export import (  # noqa: E402
    INDICATOR_ONLINE_REGIME,
    INDICATOR_VOLATILITY_SCALED_TREND,
    _trend_markers,
    build_lightweight_charts_payload,
)
from live_signal_service import (  # noqa: E402
    SESSION_GAP_TOLERANCE_SECONDS,
    LiveSignalService,
    UnsupportedLiveSignalSelection,
    build_online_signal_config,
)
from online_signals import (  # noqa: E402
    OnlineSignalConfig,
    OnlineSignalEngine,
    RevisionRequired,
    compute_online_signal_frame,
)


def _bar(
    timestamp: datetime,
    close: float,
    *,
    high_multiplier: float = 1.002,
    low_multiplier: float = 0.998,
) -> dict[str, object]:
    return {
        "timestamp": timestamp,
        "open": close * 0.999,
        "high": close * high_multiplier,
        "low": close * low_multiplier,
        "close": close,
        "volume": 100.0,
    }


def _frame(rows: int = 420) -> pl.DataFrame:
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    values = []
    price = 100.0
    for idx in range(rows):
        increment = 0.0012 + 0.002 * math.sin(idx / 13.0)
        price *= math.exp(increment)
        values.append(_bar(start + timedelta(hours=idx), price))
    return pl.DataFrame(values)


def _update(
    engine: OnlineSignalEngine,
    row: dict[str, object],
    *,
    scheduled_gap: bool = False,
) -> dict[str, object]:
    return engine.update(
        timestamp=row["timestamp"],  # type: ignore[arg-type]
        open_value=row["open"],  # type: ignore[arg-type]
        high=row["high"],  # type: ignore[arg-type]
        low=row["low"],  # type: ignore[arg-type]
        close=row["close"],  # type: ignore[arg-type]
        volume=row["volume"],  # type: ignore[arg-type]
        is_final=True,
        scheduled_gap=scheduled_gap,
    )


def _rechecksum(snapshot: dict[str, object]) -> None:
    payload = dict(snapshot)
    payload.pop("checksum", None)
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    snapshot["checksum"] = hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def test_constant_return_stream_uses_prior_volatility_and_next_bar_time() -> None:
    engine = OnlineSignalEngine()
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    last = None
    for idx in range(260):
        close = 100.0 * math.exp(0.001 * idx)
        last = _update(engine, _bar(start + timedelta(hours=idx), close))

    assert last is not None
    assert last["source_timestamp"] == start + timedelta(hours=259)
    assert last["timestamp"] == start + timedelta(hours=260)
    assert last["earliest_execution_at"] == last["timestamp"]
    assert last["availability"] == "post_close_usable_next_bar"
    assert last["trend_z_fast"] == pytest.approx(math.sqrt(12.0))
    assert last["trend_z_medium"] == pytest.approx(math.sqrt(48.0))
    assert last["trend_z_slow"] == pytest.approx(8.0)
    assert last["trend_state"] == "Bullish aligned"
    assert last["regime_label"] == "Bull trend"
    probabilities = [
        last["regime_probability_bull"],
        last["regime_probability_bear"],
        last["regime_probability_range"],
        last["regime_probability_transition"],
    ]
    assert all(math.isfinite(float(value)) for value in probabilities)
    assert math.fsum(float(value) for value in probabilities) == pytest.approx(1.0)
    predictive = float(last["regime_predictive_state_probability"])
    assert 0.0 <= predictive <= 1.0
    assert last["regime_transition_probability"] == predictive


def test_shock_trend_z_uses_prior_not_same_bar_ewma_variance() -> None:
    engine = OnlineSignalEngine(OnlineSignalConfig(trend_z_clip=100.0))
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    close = 100.0
    for idx in range(260):
        if idx > 0:
            close *= math.exp(0.001)
        _update(engine, _bar(start + timedelta(hours=idx), close))

    prior_variance = float(engine.variances["fast"])
    shock_close = close * math.exp(0.005)
    shock = _update(engine, _bar(start + timedelta(hours=260), shock_close))
    net_return = math.fsum(list(engine.returns)[-12:])
    expected_prior_z = net_return / (math.sqrt(prior_variance) * math.sqrt(12.0))
    same_bar_variance = float(engine.variances["fast"])
    leaked_z = net_return / (math.sqrt(same_bar_variance) * math.sqrt(12.0))

    assert shock["trend_z_fast"] == pytest.approx(expected_prior_z)
    assert float(shock["trend_z_fast"]) != pytest.approx(leaked_z)


def test_filtered_switch_probability_matches_pairwise_hmm_mass() -> None:
    engine = OnlineSignalEngine()
    rows = _frame(260).to_dicts()
    for row in rows[:-1]:
        _update(engine, row)
    previous = list(engine.posterior)
    output = _update(engine, rows[-1])
    observation = (
        float(output["trend_score"]),
        float(output["path_quality"]),
        float(output["volatility_pressure"]),
        float(output["range_pressure"]),
    )
    likelihoods = []
    for means, stds in zip(engine._EMISSION_MEANS, engine._EMISSION_STDS):
        log_likelihood = math.fsum(
            -0.5 * (((value - mean) / std) ** 2) - math.log(std)
            for value, mean, std in zip(observation, means, stds)
        )
        likelihoods.append(math.exp(log_likelihood))
    pairwise = [
        previous[prior] * engine._TRANSITION[prior][current] * likelihoods[current]
        for prior in range(4)
        for current in range(4)
    ]
    normalizer = math.fsum(pairwise)
    expected_switch = (
        math.fsum(
            previous[prior] * engine._TRANSITION[prior][current] * likelihoods[current]
            for prior in range(4)
            for current in range(4)
            if prior != current
        )
        / normalizer
    )

    actual_switch = float(output["regime_filtered_switch_probability"])
    assert actual_switch == pytest.approx(expected_switch)
    assert 0.0 <= actual_switch <= 1.0
    assert output["regime_change_risk"] == pytest.approx(
        max(actual_switch, float(output["regime_probability_transition"]))
    )


def test_trend_warmup_boundaries_are_exact() -> None:
    engine = OnlineSignalEngine(OnlineSignalConfig(horizons=(2, 3, 4)))
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    outputs = []
    for idx in range(5):
        outputs.append(
            _update(
                engine,
                _bar(start + timedelta(hours=idx), 100.0 * math.exp(0.001 * idx)),
            )
        )

    assert outputs[1]["trend_z_fast"] is None
    assert outputs[2]["trend_z_fast"] is not None
    assert outputs[2]["trend_z_medium"] is None
    assert outputs[3]["trend_z_medium"] is not None
    assert outputs[3]["trend_z_slow"] is None
    assert outputs[4]["trend_z_slow"] is not None
    assert outputs[4]["status"] == "ok"


def test_snapshot_restore_matches_uninterrupted_stream_exactly() -> None:
    rows = _frame(460).to_dicts()
    uninterrupted = OnlineSignalEngine()
    expected = [_update(uninterrupted, row) for row in rows]

    split = 273
    first = OnlineSignalEngine()
    for row in rows[:split]:
        _update(first, row)
    snapshot = json.loads(json.dumps(first.snapshot(), allow_nan=False))
    restored = OnlineSignalEngine.restore(snapshot)
    assert restored.snapshot() == snapshot

    duplicate_snapshot = restored.snapshot()
    assert _update(restored, rows[split - 1]) == expected[split - 1]
    assert restored.snapshot() == duplicate_snapshot

    actual = [_update(restored, row) for row in rows[split:]]
    assert actual == expected[split:]
    assert restored.snapshot() == uninterrupted.snapshot()


def test_snapshot_rejects_config_mismatch_and_corrupted_state() -> None:
    engine = OnlineSignalEngine()
    for row in _frame(20).to_dicts():
        _update(engine, row)
    snapshot = json.loads(json.dumps(engine.snapshot(), allow_nan=False))

    with pytest.raises(ValueError, match="expected config"):
        OnlineSignalEngine.restore(
            snapshot,
            expected_config=OnlineSignalConfig(expected_interval_seconds=300),
        )

    checksum_corruption = copy.deepcopy(snapshot)
    checksum_corruption["bars_seen"] += 1
    with pytest.raises(ValueError, match="checksum mismatch"):
        OnlineSignalEngine.restore(checksum_corruption)

    semantic_corruption = copy.deepcopy(snapshot)
    semantic_corruption["posterior"] = [0.5, 0.5, 0.5, 0.5]
    _rechecksum(semantic_corruption)
    with pytest.raises(ValueError, match="posterior mass"):
        OnlineSignalEngine.restore(semantic_corruption)


def test_forming_and_duplicate_bars_do_not_advance_state() -> None:
    engine = OnlineSignalEngine()
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    first_row = _bar(start, 100.0)
    first = _update(engine, first_row)
    snapshot = engine.snapshot()

    forming = engine.update(
        timestamp=start + timedelta(hours=1),
        open_value=100.0,
        high=101.0,
        low=99.0,
        close=100.5,
        volume=100.0,
        is_final=False,
    )
    assert forming["status"] == "forming_bar_not_processed"
    assert engine.snapshot() == snapshot

    assert _update(engine, first_row) == first
    assert engine.snapshot() == snapshot


def test_same_timestamp_revision_and_older_history_require_replay() -> None:
    engine = OnlineSignalEngine()
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    _update(engine, _bar(start, 100.0))

    with pytest.raises(RevisionRequired, match="current timestamp"):
        _update(engine, _bar(start, 101.0))
    with pytest.raises(RevisionRequired, match="predates"):
        _update(engine, _bar(start - timedelta(hours=1), 99.0))


def test_cadence_gap_fails_closed_and_restarts_warmup() -> None:
    engine = OnlineSignalEngine()
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    _update(engine, _bar(start, 100.0))
    gap = _update(engine, _bar(start + timedelta(hours=2), 101.0))

    assert gap["status"] == "cadence_gap_reset_7200s"
    assert gap["trend_score"] is None
    assert gap["regime_state"] is None
    assert list(engine.returns) == []


def test_warmed_gap_clears_all_signal_state_and_fractional_gap_is_not_rounded() -> None:
    engine = OnlineSignalEngine()
    rows = _frame(260).to_dicts()
    for row in rows:
        _update(engine, row)
    assert engine.regime_state is not None
    assert engine.previous_trend_state is not None

    last_timestamp = rows[-1]["timestamp"]
    last_close = float(rows[-1]["close"])
    gap = _update(
        engine,
        _bar(last_timestamp + timedelta(hours=2, milliseconds=500), last_close),
    )

    assert gap["status"] == "cadence_gap_reset_7200.5s"
    assert engine.previous_close == last_close
    assert all(value is None for value in engine.variances.values())
    assert list(engine.returns) == []
    assert engine.previous_trend_state is None
    assert engine.posterior == list(engine._INITIAL_POSTERIOR)
    assert engine.regime_state is None
    assert engine.regime_duration == 0
    assert engine.risk_active is False


def test_explicit_forward_gap_tolerance_preserves_warm_state_only_when_aligned() -> (
    None
):
    config = OnlineSignalConfig(
        horizons=(2, 3, 4),
        expected_interval_seconds=3600,
        max_gap_seconds=4 * 24 * 3600,
    )
    engine = OnlineSignalEngine(config)
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    close = 100.0
    for idx in range(10):
        close *= math.exp(0.001)
        latest = _update(engine, _bar(start + timedelta(hours=idx), close))
    assert latest["status"] == "ok"
    warmed_snapshot = engine.snapshot()

    close *= math.exp(0.001)
    tolerated = _update(
        engine,
        _bar(start + timedelta(hours=9 + 73), close),
        scheduled_gap=True,
    )
    assert tolerated["status"] == "ok"
    assert tolerated["trend_score"] is not None
    assert len(engine.returns) == 4

    unflagged = OnlineSignalEngine.restore(warmed_snapshot)
    reset = _update(
        unflagged,
        _bar(start + timedelta(hours=9 + 73), close),
    )
    assert reset["status"] == "cadence_gap_reset_262800s"
    assert list(unflagged.returns) == []

    misaligned = OnlineSignalEngine.restore(warmed_snapshot)
    misaligned_result = _update(
        misaligned,
        _bar(
            start + timedelta(hours=9 + 73, milliseconds=500),
            close,
        ),
        scheduled_gap=True,
    )
    assert misaligned_result["status"] == "cadence_gap_reset_262800.5s"
    assert list(misaligned.returns) == []


@pytest.mark.parametrize(
    ("invalid_kind", "expected_status"),
    (("close", "invalid_close_reset"), ("range", "invalid_ohlc_reset")),
)
def test_invalid_finalized_bar_fails_closed_and_requires_fresh_seed(
    invalid_kind: str,
    expected_status: str,
) -> None:
    engine = OnlineSignalEngine()
    rows = _frame(260).to_dicts()
    for row in rows:
        _update(engine, row)
    assert engine.regime_state is not None

    timestamp = rows[-1]["timestamp"] + timedelta(hours=1)
    close = float(rows[-1]["close"])
    invalid = _bar(timestamp, close)
    if invalid_kind == "close":
        invalid["close"] = 0.0
    else:
        invalid["high"] = close * 0.99
    result = _update(engine, invalid)

    assert result["status"] == expected_status
    assert engine.previous_close is None
    assert all(value is None for value in engine.variances.values())
    assert list(engine.returns) == []
    assert engine.previous_trend_state is None
    assert engine.posterior == list(engine._INITIAL_POSTERIOR)
    assert engine.regime_state is None
    assert engine.regime_duration == 0
    assert engine.risk_active is False

    seeded = _update(engine, _bar(timestamp + timedelta(hours=1), close))
    assert seeded["status"] == "seed_close"
    assert seeded["trend_score"] is None


def test_bounded_replay_applies_five_second_finality_lag_without_state_mismatch() -> (
    None
):
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    frame = pl.DataFrame([_bar(start, 100.0)])

    protected, protected_engine = compute_online_signal_frame(
        frame,
        now=start + timedelta(hours=1, seconds=4),
    )
    assert protected.is_empty()
    assert protected_engine.bars_seen == 0

    closed, closed_engine = compute_online_signal_frame(
        frame,
        now=start + timedelta(hours=1, seconds=5),
    )
    assert closed.height == 1
    assert closed_engine.bars_seen == closed.height
    assert closed["source_timestamp"][0] == closed_engine.last_timestamp
    assert closed_engine.last_output is not None


def test_prefix_and_future_mutation_cannot_change_earlier_outputs() -> None:
    frame = _frame(420)
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    full, _ = compute_online_signal_frame(frame, now=now)
    prefix_frame = frame.head(300)
    prefix, _ = compute_online_signal_frame(prefix_frame, now=now)

    assert full.head(prefix.height).to_dicts() == prefix.to_dicts()

    mutated = (
        frame.with_row_index("row_idx")
        .with_columns(
            pl.when(pl.col("row_idx") >= 300)
            .then(pl.col("close") * 1.5)
            .otherwise(pl.col("close"))
            .alias("close")
        )
        .drop("row_idx")
    )
    mutated_outputs, _ = compute_online_signal_frame(mutated, now=now)
    assert mutated_outputs.head(300).to_dicts() == full.head(300).to_dicts()


def test_payload_renders_trend_and_online_regime_at_next_bar() -> None:
    frame = _frame(420)
    payload = build_lightweight_charts_payload(
        frame,
        {
            "asset": "BTCUSDT",
            "timeframe": "1h",
            "source": "canonical",
            "provider": "test",
            "description": "test bars",
        },
        indicators=(
            INDICATOR_VOLATILITY_SCALED_TREND,
            INDICATOR_ONLINE_REGIME,
        ),
        calculation_now=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )

    trend = payload["overlays"][INDICATOR_VOLATILITY_SCALED_TREND]
    regime = payload["overlays"][INDICATOR_ONLINE_REGIME]
    assert trend["status"] == "ok"
    assert trend["availability"] == "post_close_usable_next_bar"
    assert trend["plotted_at"] == "earliest_next_bar_execution_time"
    assert trend["horizons_bars"] == {"fast": 12, "medium": 48, "slow": 192}
    assert regime["status"] == "ok"
    assert regime["filter_mode"] == "one_step_forward_only"
    assert regime["trained_model"] is False
    assert regime["diagnostic_only"] is True
    last_candle_time = payload["candles"][-1]["time"]
    assert trend["score"][-1]["time"] == last_candle_time + 3600
    assert regime["change_risk"][-1]["time"] == last_candle_time + 3600
    assert trend["last"]["source_as_of"] == last_candle_time
    assert trend["last"]["as_of"] == last_candle_time + 3600


def test_nondefault_asset_and_timeframe_render_bounded_online_signals() -> None:
    frame = _frame(240)
    frame = frame.with_columns(
        (
            pl.lit(datetime(2025, 1, 1, tzinfo=timezone.utc))
            + pl.int_range(0, pl.len(), dtype=pl.Int64) * pl.duration(minutes=15)
        ).alias("timestamp")
    )
    payload = build_lightweight_charts_payload(
        frame,
        {
            "asset": "ETHUSDT",
            "timeframe": "15m",
            "source": "canonical",
            "provider": "test",
        },
        indicators=INDICATOR_ONLINE_REGIME,
        calculation_now=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )

    regime = payload["overlays"][INDICATOR_ONLINE_REGIME]
    assert regime["status"] == "ok"
    assert regime["state_band"]
    assert regime["bull"]
    assert regime["last"]["status"] in {
        "Bull trend",
        "Bear trend",
        "Range / chop",
        "Transition risk",
    }
    assert payload["metadata"]["online_signal"]["validation_safe"] is False


def test_raw_debug_chart_uses_bounded_replay_without_persistent_source_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected_live_service(**_: object) -> tuple[pl.DataFrame, dict[str, object]]:
        raise AssertionError(
            "raw debug selections must not enter persistent live service"
        )

    monkeypatch.setattr(
        chart_export_module,
        "get_live_signal_frame",
        unexpected_live_service,
    )
    payload = build_lightweight_charts_payload(
        _frame(240),
        {
            "asset": "BTCUSDT",
            "timeframe": "1h",
            "source": "raw",
            "provider": "test",
        },
        indicators=(
            INDICATOR_VOLATILITY_SCALED_TREND,
            INDICATOR_ONLINE_REGIME,
        ),
        use_live_signal_service=True,
        calculation_now=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )

    assert payload["overlays"][INDICATOR_VOLATILITY_SCALED_TREND]["status"] == "ok"
    assert payload["overlays"][INDICATOR_ONLINE_REGIME]["status"] == "ok"
    assert (
        payload["metadata"]["online_signal"]["signal_vintage"]
        == "current_source_replay"
    )


def test_session_debug_source_uses_explicit_unverified_gap_inference() -> None:
    base = _frame(260)
    timestamps: list[datetime] = []
    current = datetime(2025, 1, 1, tzinfo=timezone.utc)
    for index in range(base.height):
        if index > 0:
            current += timedelta(days=2) if index % 90 == 0 else timedelta(minutes=15)
        timestamps.append(current)
    frame = base.with_columns(pl.Series("timestamp", timestamps))

    payload = build_lightweight_charts_payload(
        frame,
        {
            "asset": "ES",
            "timeframe": "15m",
            "source": "raw",
            "provider": "test",
        },
        indicators=(
            INDICATOR_VOLATILITY_SCALED_TREND,
            INDICATOR_ONLINE_REGIME,
        ),
        use_live_signal_service=True,
        calculation_now=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )

    assert payload["overlays"][INDICATOR_VOLATILITY_SCALED_TREND]["status"] == "ok"
    assert payload["overlays"][INDICATOR_ONLINE_REGIME]["status"] == "ok"
    assert (
        payload["metadata"]["online_signal"]["session_gap_policy"]
        == "bounded_timestamp_gap_inference_debug_only"
    )


def test_short_debug_source_shows_partial_trend_and_clear_regime_warmup() -> None:
    frame = _frame(92).with_columns(
        (
            pl.lit(datetime(2025, 1, 1, tzinfo=timezone.utc))
            + pl.int_range(0, pl.len(), dtype=pl.Int64) * pl.duration(minutes=15)
        ).alias("timestamp")
    )
    payload = build_lightweight_charts_payload(
        frame,
        {
            "asset": "ES",
            "timeframe": "15m",
            "source": "raw_yfinance",
            "provider": "test",
        },
        indicators=(
            INDICATOR_VOLATILITY_SCALED_TREND,
            INDICATOR_ONLINE_REGIME,
        ),
        calculation_now=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )

    trend = payload["overlays"][INDICATOR_VOLATILITY_SCALED_TREND]
    regime = payload["overlays"][INDICATOR_ONLINE_REGIME]
    assert trend["status"] == "partial_warmup"
    assert any("value" in point for point in trend["fast"])
    assert any("value" in point for point in trend["medium"])
    assert all("value" not in point for point in trend["slow"])
    assert "193 closed bars" in trend["reason"]
    assert regime["status"] == "warmup_or_no_overlap"
    assert "193 closed bars" in regime["reason"]


def test_persistent_service_rejects_raw_before_resolving_thousands_of_files(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected_resolve(**_: object) -> object:
        raise AssertionError("raw source resolution should be skipped")

    monkeypatch.setattr(live_service_module, "resolve_ohlcv_files", unexpected_resolve)
    with pytest.raises(UnsupportedLiveSignalSelection, match="canonical-only"):
        LiveSignalService().get(
            asset="ES",
            timeframe="1m",
            source="raw_databento_es_backup",
        )


def test_live_service_appends_and_replays_after_historical_revision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frames = [_frame(300)]

    def fake_read_stable_source(
        **_: object,
    ) -> tuple[pl.DataFrame, tuple[tuple[str, int, int], ...]]:
        frame = frames[-1]
        snapshot = (("synthetic.parquet", frame.height, frame.height),)
        return frame, snapshot

    monkeypatch.setattr(
        live_service_module,
        "_read_stable_source",
        fake_read_stable_source,
    )
    service = LiveSignalService()
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    first, first_meta = service.get(
        asset="BTCUSDT", timeframe="1h", source="canonical", now=now
    )
    assert first_meta["replayed"] is True

    appended_source = pl.concat(
        [
            frames[-1],
            pl.DataFrame(
                [
                    _bar(
                        frames[-1]["timestamp"].max() + timedelta(hours=1),
                        float(frames[-1]["close"].tail(1)[0]) * 1.001,
                    )
                ]
            ),
        ],
        how="vertical_relaxed",
    )
    frames.append(appended_source)
    appended, appended_meta = service.get(
        asset="BTCUSDT", timeframe="1h", source="canonical", now=now
    )
    assert appended_meta["replayed"] is False
    assert appended_meta["appended_bars"] == 1
    assert appended.head(first.height).to_dicts() == first.to_dicts()

    revision_timestamp = appended_source["timestamp"][200]
    revised_rows = appended_source.to_dicts()
    revised_close = float(revised_rows[200]["close"]) * 1.2
    revised_rows[200]["close"] = revised_close
    revised_rows[200]["high"] = revised_close * 1.002
    revised_rows[200]["low"] = revised_close * 0.998
    revised_rows[200]["open"] = revised_close * 0.999
    revised = pl.DataFrame(revised_rows)
    frames.append(revised)
    replayed, replay_meta = service.get(
        asset="BTCUSDT", timeframe="1h", source="canonical", now=now
    )
    assert replay_meta["replayed"] is True
    assert replay_meta["replay_from"] == revision_timestamp.isoformat().replace(
        "+00:00", "Z"
    )
    assert replayed.head(200).to_dicts() == appended.head(200).to_dicts()
    assert (
        replayed.tail(replayed.height - 200).to_dicts()
        != appended.tail(appended.height - 200).to_dicts()
    )


def test_paginated_payloads_share_identical_action_time_boundary_points() -> None:
    full_frame = _frame(520)
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    signal_frame, _ = compute_online_signal_frame(full_frame, now=now)
    metadata = {
        "asset": "BTCUSDT",
        "timeframe": "1h",
        "source": "canonical",
        "provider": "test",
    }
    first_page = build_lightweight_charts_payload(
        full_frame.head(260),
        metadata,
        indicators=(INDICATOR_VOLATILITY_SCALED_TREND, INDICATOR_ONLINE_REGIME),
        live_signal_frame=signal_frame,
        live_signal_metadata={
            "status": "ok",
            "mode": "full_origin_stream_replay",
            "algorithm_version": "online_signal_v2",
        },
        calculation_now=now,
    )
    second_page = build_lightweight_charts_payload(
        full_frame.tail(260),
        metadata,
        indicators=(INDICATOR_VOLATILITY_SCALED_TREND, INDICATOR_ONLINE_REGIME),
        live_signal_frame=signal_frame,
        live_signal_metadata={
            "status": "ok",
            "mode": "full_origin_stream_replay",
            "algorithm_version": "online_signal_v2",
        },
        calculation_now=now,
    )

    first_scores = {
        point["time"]: point.get("value")
        for point in first_page["overlays"][INDICATOR_VOLATILITY_SCALED_TREND]["score"]
    }
    second_scores = {
        point["time"]: point.get("value")
        for point in second_page["overlays"][INDICATOR_VOLATILITY_SCALED_TREND]["score"]
    }
    shared_times = set(first_scores) & set(second_scores)
    assert shared_times
    assert all(first_scores[time] == second_scores[time] for time in shared_times)


def test_all_canonical_assets_and_timeframes_produce_current_signals() -> None:
    manifest = build_chart_manifest()
    selections = [
        (asset_entry["asset"], timeframe_entry["timeframe"])
        for asset_entry in manifest["assets"]
        for source_entry in asset_entry["sources"]
        if source_entry["source"] == CANONICAL_SOURCE
        for timeframe_entry in source_entry["timeframes"]
    ]
    assert len(selections) == len(CORE_ASSETS) * 7 == 56

    now = datetime(2030, 1, 1, tzinfo=timezone.utc)
    failures: list[str] = []
    for asset, timeframe in selections:
        resolution = resolve_ohlcv_files(asset, timeframe, CANONICAL_SOURCE)
        frame = (
            pl.scan_parquet(resolution.files[0])
            .select(
                "timestamp",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "is_session_open_bar",
            )
            .tail(260)
            .collect()
        )
        config = build_online_signal_config(asset=asset, timeframe=timeframe)
        signals, _ = compute_online_signal_frame(frame, config=config, now=now)
        valid = signals.filter(
            pl.col("trend_score").is_not_null() & pl.col("regime_state").is_not_null()
        )
        if valid.is_empty():
            failures.append(f"{asset} {timeframe}: no warmed signal")
            continue
        last = valid.tail(1).to_dicts()[0]
        weights = [
            float(last["regime_probability_bull"]),
            float(last["regime_probability_bear"]),
            float(last["regime_probability_range"]),
            float(last["regime_probability_transition"]),
        ]
        if not math.isclose(math.fsum(weights), 1.0, abs_tol=1e-12):
            failures.append(f"{asset} {timeframe}: prototype weights do not sum to one")
        expected_action_time = last["source_timestamp"] + timedelta(
            seconds=timeframe_seconds(timeframe)
        )
        if last["timestamp"] != expected_action_time:
            failures.append(f"{asset} {timeframe}: action timestamp mismatch")

        payload = build_lightweight_charts_payload(
            frame,
            {
                "asset": asset,
                "timeframe": timeframe,
                "source": CANONICAL_SOURCE,
                "provider": "canonical",
                "description": "matrix validation",
            },
            indicators=(
                INDICATOR_VOLATILITY_SCALED_TREND,
                INDICATOR_ONLINE_REGIME,
            ),
            live_signal_frame=signals,
            live_signal_metadata={
                "status": "ok",
                "mode": "bounded_selection_stream_replay",
                "timeframe": timeframe,
                "algorithm_version": "online_signal_v2",
                "config_digest": config.digest(),
                "signal_vintage": "current_canonical_replay",
                "validation_safe": False,
            },
            calculation_now=now,
        )
        trend_overlay = payload["overlays"][INDICATOR_VOLATILITY_SCALED_TREND]
        regime_overlay = payload["overlays"][INDICATOR_ONLINE_REGIME]
        if trend_overlay["status"] != "ok" or not trend_overlay["score"]:
            failures.append(f"{asset} {timeframe}: trend pane is blank")
        if regime_overlay["status"] != "ok" or not regime_overlay["change_risk"]:
            failures.append(f"{asset} {timeframe}: regime pane is blank")

    assert failures == []


def test_live_service_accepts_every_canonical_asset_timeframe_selection() -> None:
    service = LiveSignalService()
    manifest = build_chart_manifest()
    now = datetime(2030, 1, 1, tzinfo=timezone.utc)
    checked = 0
    for asset_entry in manifest["assets"]:
        asset = asset_entry["asset"]
        canonical = next(
            source
            for source in asset_entry["sources"]
            if source["source"] == CANONICAL_SOURCE
        )
        for timeframe_entry in canonical["timeframes"]:
            timeframe = timeframe_entry["timeframe"]
            resolution = resolve_ohlcv_files(asset, timeframe, CANONICAL_SOURCE)
            frame = (
                pl.scan_parquet(resolution.files[0])
                .select(
                    "timestamp",
                    "open",
                    "high",
                    "low",
                    "close",
                    "volume",
                    "is_session_open_bar",
                )
                .tail(260)
                .collect()
            )
            signals, metadata = service.get(
                asset=asset,
                timeframe=timeframe,
                source=CANONICAL_SOURCE,
                now=now,
                replay_frame=frame,
                visible_start=frame["timestamp"].min(),
            )
            assert metadata["status"] == "ok"
            assert metadata["asset"] == asset
            assert metadata["timeframe"] == timeframe
            assert metadata["signal_vintage"] == "current_canonical_replay"
            assert metadata["validation_safe"] is False
            assert metadata["trained_model"] is False
            assert metadata["expected_interval_seconds"] == timeframe_seconds(timeframe)
            if asset in {"BTCUSDT", "ETHUSDT"}:
                assert metadata["maximum_tolerated_gap_seconds"] == timeframe_seconds(
                    timeframe
                )
            else:
                assert (
                    metadata["maximum_tolerated_gap_seconds"]
                    == SESSION_GAP_TOLERANCE_SECONDS
                )
            assert signals["trend_score"].drop_nulls().len() > 0
            assert signals["regime_state"].drop_nulls().len() > 0
            checked += 1

    assert checked == 56


def test_session_close_signal_marker_moves_to_first_executable_candle() -> None:
    friday = datetime(2025, 1, 3, 23, tzinfo=timezone.utc)
    saturday_availability = friday + timedelta(hours=1)
    monday = datetime(2025, 1, 6, 23, tzinfo=timezone.utc)
    signal_frame = pl.DataFrame(
        {
            "time": [int(saturday_availability.timestamp())],
            "trend_bull_start": [True],
            "trend_bear_start": [False],
        }
    )
    candle_frame = pl.DataFrame(
        {
            "timestamp": [friday, monday],
        }
    )

    markers = _trend_markers(signal_frame, candle_frame)

    assert len(markers) == 1
    assert markers[0]["time"] == int(monday.timestamp())


@pytest.mark.parametrize("invalid", ["0m", "-1h", "1w", "m1", "1.5h", ""])
def test_timeframe_parser_rejects_invalid_durations(invalid: str) -> None:
    with pytest.raises(ValueError, match="Unsupported timeframe"):
        timeframe_seconds(invalid)
