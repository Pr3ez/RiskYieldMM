from __future__ import annotations

import copy
import json
import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pytest

ANALYST_ROOT = (
    Path(__file__).resolve().parents[1] / "Risk_Yield_Meta_Model_Analyst_0_0_1"
)
if str(ANALYST_ROOT) not in sys.path:
    sys.path.insert(0, str(ANALYST_ROOT))

import forward_paper.stream as stream_module  # noqa: E402
from forward_paper.service import (  # noqa: E402
    FORWARD_META_ARTIFACT_ENV,
    ForwardPaperConfig,
    ForwardPaperCoordinator,
)
from forward_paper.stream import ForwardPaperStream  # noqa: E402
from minute_replay import (  # noqa: E402
    IndicatorStrategyConfig,
    ProtectedReplayConfig,
    ReplayCostConfig,
    meta_label_policy_digest,
)
from trade_ml.artifact import build_coefficient_artifact  # noqa: E402
from trade_ml.features import META_FEATURE_NAMES  # noqa: E402
from trade_ml.model import fit_logistic_baseline  # noqa: E402
from trade_ml.shadow import ShadowEventBook  # noqa: E402


def _fast_strategy() -> IndicatorStrategyConfig:
    return IndicatorStrategyConfig(
        cusum_sensitivity="Fast (Day Trade)",
        horizons=(2, 4, 8),
        aligned_score=0.03,
        aligned_quality=0.01,
        developing_score=0.005,
        change_risk_threshold=1.0,
        max_fast_slow_ratio=100.0,
        minimum_path_quality=0.0,
        require_cusum_agreement=False,
        minimum_volatility_scale=1.0,
    )


def _minutes(rows: int = 260) -> list[dict[str, object]]:
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    output: list[dict[str, object]] = []
    price = 100.0
    for idx in range(rows):
        close = price * math.exp(0.001 + 0.0003 * math.sin(idx / 5.0))
        output.append(
            {
                "timestamp": start + timedelta(minutes=idx),
                "open": price,
                "high": max(price, close) * 1.0005,
                "low": min(price, close) * 0.9995,
                "close": close,
                "volume": 100.0 + idx,
                "is_session_open_bar": False,
            }
        )
        price = close
    return output


def _consume(
    stream: ForwardPaperStream,
    rows: list[dict[str, object]],
    *,
    mode: str = "forward",
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for row in rows:
        observed_at = row["timestamp"] + timedelta(minutes=1, seconds=5)  # type: ignore[operator]
        events.extend(
            stream.consume(
                row,
                observed_at=observed_at,
                mode=mode,  # type: ignore[arg-type]
            )
        )
    return events


def _compatible_artifact(
    *,
    strategy: IndicatorStrategyConfig,
    costs: ReplayCostConfig,
    protection: ProtectedReplayConfig,
):
    row_count = 12
    column_count = len(META_FEATURE_NAMES)
    X = np.linspace(-1.0, 1.0, row_count * column_count).reshape(
        row_count, column_count
    )
    y = np.asarray([0, 1] * (row_count // 2), dtype=int)
    fitted = fit_logistic_baseline(X, y, feature_names=META_FEATURE_NAMES)
    return build_coefficient_artifact(
        fitted,
        model_version="forward-shadow-test-v1",
        policy_digest=meta_label_policy_digest(
            strategy=strategy,
            costs=costs,
            protection=protection,
            timeframe="1m",
        ),
        assets=("BTCUSDT",),
        timeframes=("1m",),
        trained_through="2024-01-01T00:00:00Z",
        label_mature_through="2024-01-02T00:00:00Z",
        created_at="2024-01-03T00:00:00Z",
        decision_threshold=0.5,
    )


def test_missing_artifact_collects_shadow_labels_without_changing_paper_orders() -> (
    None
):
    rows = _minutes()
    strategy = _fast_strategy()
    baseline = ForwardPaperStream(asset="BTCUSDT", timeframe="1m", strategy=strategy)
    shadow = ForwardPaperStream(
        asset="BTCUSDT",
        timeframe="1m",
        strategy=strategy,
        meta_shadow_protection=ProtectedReplayConfig(enabled=True),
        meta_artifact_reason="artifact_not_found",
    )

    baseline_events = _consume(baseline, rows)
    shadow_events = _consume(shadow, rows)
    paper_events = [
        event
        for event in shadow_events
        if not str(event["event_type"]).startswith("meta_shadow_")
    ]
    predictions = [
        event
        for event in shadow_events
        if event["event_type"] == "meta_shadow_prediction"
    ]
    labels = [
        event for event in shadow_events if event["event_type"] == "meta_shadow_label"
    ]

    assert paper_events == baseline_events
    assert predictions
    assert labels
    assert all(event["available"] is False for event in predictions)
    assert all(event["score_reason"] == "artifact_not_found" for event in predictions)
    assert all(event["candidate_scheduled"] is True for event in predictions)
    assert all(
        event["required_probability"] == event["static_threshold_with_margin"]
        for event in predictions
    )
    assert all(
        event["static_threshold_with_margin"]
        == event["decision_static_stop_break_even_probability"]
        + event["break_even_safety_margin"]
        for event in predictions
    )
    assert all(event["counterfactual_accepted"] is False for event in predictions)
    assert all(event["affects_orders"] is False for event in predictions)
    assert all(event["affects_positions"] is False for event in labels)
    assert all(event["occurred_at"] == event["label_known_at"] for event in labels)
    assert all(event["observed_at"] >= event["label_known_at"] for event in labels)


def test_compatible_artifact_scores_once_and_shadow_state_restores_exactly() -> None:
    rows = _minutes()
    strategy = _fast_strategy()
    costs = ReplayCostConfig(execution_latency_minutes=1)
    protection = ProtectedReplayConfig(enabled=True)
    artifact = _compatible_artifact(
        strategy=strategy,
        costs=costs,
        protection=protection,
    )
    original = ForwardPaperStream(
        asset="BTCUSDT",
        timeframe="1m",
        strategy=strategy,
        costs=costs,
        meta_shadow_protection=protection,
        meta_artifact=artifact,
        meta_artifact_reason="ok",
    )

    prefix_events = _consume(original, rows[:34])
    assert (
        sum(event["event_type"] == "meta_shadow_prediction" for event in prefix_events)
        == 1
    )
    snapshot = original.snapshot()
    encoded = json.dumps(snapshot, allow_nan=False)
    assert "coefficients" not in encoded
    assert artifact.checksum in encoded
    restored = ForwardPaperStream.restore(
        copy.deepcopy(snapshot),
        meta_shadow_protection=protection,
        meta_artifact=artifact,
        meta_artifact_reason="ok",
    )

    original_tail = _consume(original, rows[34:])
    restored_tail = _consume(restored, rows[34:])
    all_events = [*prefix_events, *original_tail]
    predictions = [
        event for event in all_events if event["event_type"] == "meta_shadow_prediction"
    ]

    assert restored_tail == original_tail
    assert restored.snapshot() == original.snapshot()
    assert len(predictions) == 1
    assert predictions[0]["available"] is True
    assert predictions[0]["probability"] is not None
    assert predictions[0]["artifact_checksum"] == artifact.checksum
    assert predictions[0]["candidate_scheduled"] is True
    assert predictions[0]["required_probability"] == max(
        predictions[0]["decision_threshold"],
        predictions[0]["static_threshold_with_margin"],
    )
    assert predictions[0]["counterfactual_accepted"] is (
        predictions[0]["probability"] > predictions[0]["required_probability"]
    )


def test_catchup_warms_indicators_without_shadow_predictions_or_candidates() -> None:
    stream = ForwardPaperStream(
        asset="BTCUSDT",
        timeframe="1m",
        strategy=_fast_strategy(),
        meta_shadow_protection=ProtectedReplayConfig(enabled=True),
        meta_artifact_reason="artifact_not_found",
    )

    events = _consume(stream, _minutes(120), mode="catchup")
    shadow_view = stream.meta_shadow_book.view(resolved_limit=0)  # type: ignore[union-attr]

    assert not any(
        str(event["event_type"]).startswith("meta_shadow_") for event in events
    )
    assert shadow_view["total_scheduled"] == 0
    assert shadow_view["total_filled"] == 0
    assert shadow_view["total_resolved"] == 0


def test_catchup_matures_restored_candidate_without_scheduling_new_setups() -> None:
    rows = _minutes(45)
    stream = ForwardPaperStream(
        asset="BTCUSDT",
        timeframe="1m",
        strategy=_fast_strategy(),
        meta_shadow_protection=ProtectedReplayConfig(
            enabled=True,
            stop_risk_units=5.0,
            target_risk_units=5.0,
            timeout_target_bars=2,
        ),
        meta_artifact_reason="artifact_not_found",
    )
    _consume(stream, rows[:34])
    assert stream.meta_shadow_book is not None
    before = stream.meta_shadow_book.view(resolved_limit=0)
    assert before["active_count"] == 1

    catchup_events = _consume(stream, rows[34:36], mode="catchup")
    after = stream.meta_shadow_book.view(resolved_limit=10)

    assert not any(
        event["event_type"] == "meta_shadow_prediction" for event in catchup_events
    )
    label = next(
        event for event in catchup_events if event["event_type"] == "meta_shadow_label"
    )
    assert label["outcome"] == "TIMEOUT"
    assert after["total_scheduled"] == before["total_scheduled"]
    assert after["total_resolved"] == 1


def test_final_constituent_touch_wins_before_target_bar_timeout() -> None:
    rows = _minutes(45)
    stream = ForwardPaperStream(
        asset="BTCUSDT",
        timeframe="1m",
        strategy=_fast_strategy(),
        meta_shadow_protection=ProtectedReplayConfig(
            enabled=True,
            stop_risk_units=5.0,
            target_risk_units=5.0,
            timeout_target_bars=2,
        ),
        meta_artifact_reason="artifact_not_found",
    )
    _consume(stream, rows[:34])
    final_constituent = dict(rows[34])
    final_constituent["high"] = float(final_constituent["open"]) * 2.0

    events = _consume(stream, [final_constituent])
    label = next(
        event for event in events if event["event_type"] == "meta_shadow_label"
    )

    assert label["outcome"] == "TARGET"
    assert label["reason"] == "target_touched"


def test_timeout_precedes_first_minute_of_next_target_bar_and_uses_observation_clock() -> (
    None
):
    rows = _minutes(45)
    stream = ForwardPaperStream(
        asset="BTCUSDT",
        timeframe="1m",
        strategy=_fast_strategy(),
        meta_shadow_protection=ProtectedReplayConfig(
            enabled=True,
            stop_risk_units=5.0,
            target_risk_units=5.0,
            timeout_target_bars=2,
        ),
        meta_artifact_reason="artifact_not_found",
    )
    _consume(stream, rows[:35])
    next_target_first_minute = dict(rows[35])
    next_target_first_minute["high"] = float(next_target_first_minute["open"]) * 2.0

    events = _consume(stream, [next_target_first_minute])
    label = next(
        event for event in events if event["event_type"] == "meta_shadow_label"
    )

    assert label["outcome"] == "TIMEOUT"
    assert label["reason"] == "maximum_finalized_target_bars_reached"
    assert label["outcome_occurred_at"] == "2025-01-01T00:35:00Z"
    assert label["label_known_at"] == "2025-01-01T00:36:05Z"
    assert label["observed_at"] == label["label_known_at"]


def test_forward_gap_cancels_active_continuous_shadow_without_training_label() -> None:
    rows = _minutes(50)
    stream = ForwardPaperStream(
        asset="BTCUSDT",
        timeframe="1m",
        strategy=_fast_strategy(),
        meta_shadow_protection=ProtectedReplayConfig(enabled=True),
        meta_artifact_reason="artifact_not_found",
    )

    _consume(stream, rows[:34])
    assert stream.meta_shadow_book is not None
    active_view = stream.meta_shadow_book.view(resolved_limit=0)
    assert active_view["active_count"] == 1
    active_candidate = active_view["active"][0]["candidate"]
    assert (
        active_candidate["features"]["cusum_available_at"]
        == active_candidate["decision_at"]
    )
    gap_events = _consume(stream, [rows[35]])
    label = next(
        event for event in gap_events if event["event_type"] == "meta_shadow_label"
    )

    assert label["outcome"] == "CANCELLED"
    assert label["default_binary_label"] is None
    assert label["economic_binary_target"] is None
    assert label["reason"] == "continuous_market_data_gap_unknown_path"
    assert label["occurred_at"] == label["label_known_at"]


def test_model_failure_is_sanitized_and_does_not_change_baseline_paper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = _minutes(40)
    strategy = _fast_strategy()
    costs = ReplayCostConfig(execution_latency_minutes=1)
    protection = ProtectedReplayConfig(enabled=True)
    artifact = _compatible_artifact(
        strategy=strategy,
        costs=costs,
        protection=protection,
    )
    baseline = ForwardPaperStream(
        asset="BTCUSDT", timeframe="1m", strategy=strategy, costs=costs
    )
    shadow = ForwardPaperStream(
        asset="BTCUSDT",
        timeframe="1m",
        strategy=strategy,
        costs=costs,
        meta_shadow_protection=protection,
        meta_artifact=artifact,
        meta_artifact_reason="ok",
    )

    def fail_score(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("model failed at /private/model/location")

    monkeypatch.setattr(stream_module, "score_features", fail_score)
    baseline_events = _consume(baseline, rows)
    shadow_events = _consume(shadow, rows)
    faults = [
        event
        for event in shadow_events
        if event["event_type"] == "meta_shadow_processing_failed"
    ]

    assert [
        event
        for event in shadow_events
        if not str(event["event_type"]).startswith("meta_shadow_")
    ] == baseline_events
    assert len(faults) == 1
    assert faults[0]["phase"] == "candidate_score_and_schedule"
    assert faults[0]["error_class"] == "RuntimeError"
    assert len(faults[0]["error_digest"]) == 64
    assert "/private/model/location" not in json.dumps(faults[0], sort_keys=True)
    assert shadow.meta_shadow_failure_count == 1
    assert shadow.meta_shadow_book is not None
    assert shadow.meta_shadow_book.view(resolved_limit=0)["total_scheduled"] == 0

    snapshot = shadow.snapshot()
    restored = ForwardPaperStream.restore(
        copy.deepcopy(snapshot),
        meta_shadow_protection=protection,
        meta_artifact=artifact,
        meta_artifact_reason="ok",
    )
    assert restored.meta_shadow_failure_count == 1
    assert restored.last_meta_shadow_failure == shadow.last_meta_shadow_failure


def test_schedule_failure_is_copy_on_write_and_baseline_continues(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = _minutes(40)
    strategy = _fast_strategy()
    baseline = ForwardPaperStream(asset="BTCUSDT", timeframe="1m", strategy=strategy)
    shadow = ForwardPaperStream(
        asset="BTCUSDT",
        timeframe="1m",
        strategy=strategy,
        meta_shadow_protection=ProtectedReplayConfig(enabled=True),
        meta_artifact_reason="artifact_not_found",
    )

    def fail_schedule(_book: ShadowEventBook, _candidate: object) -> None:
        raise RuntimeError("capacity failure at /private/shadow/book")

    monkeypatch.setattr(ShadowEventBook, "schedule", fail_schedule)
    baseline_events = _consume(baseline, rows)
    shadow_events = _consume(shadow, rows)
    fault = next(
        event
        for event in shadow_events
        if event["event_type"] == "meta_shadow_processing_failed"
    )

    assert [
        event
        for event in shadow_events
        if not str(event["event_type"]).startswith("meta_shadow_")
    ] == baseline_events
    assert fault["phase"] == "candidate_score_and_schedule"
    assert "/private/shadow/book" not in json.dumps(fault, sort_keys=True)
    assert shadow.meta_shadow_book is not None
    assert shadow.meta_shadow_book.view(resolved_limit=0)["total_scheduled"] == 0


def test_minute_update_failure_retains_shadow_cursor_and_baseline_continues(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = _minutes(40)
    strategy = _fast_strategy()
    baseline = ForwardPaperStream(asset="BTCUSDT", timeframe="1m", strategy=strategy)
    shadow = ForwardPaperStream(
        asset="BTCUSDT",
        timeframe="1m",
        strategy=strategy,
        meta_shadow_protection=ProtectedReplayConfig(enabled=True),
        meta_artifact_reason="artifact_not_found",
    )
    _consume(baseline, rows[:34])
    _consume(shadow, rows[:34])
    assert shadow.meta_shadow_book is not None
    cursor_before = shadow.meta_shadow_book.view(resolved_limit=0)["cursor_by_asset"]

    def fail_update(_book: ShadowEventBook, _minute: object) -> None:
        raise RuntimeError("minute failure at /private/source/file")

    monkeypatch.setattr(ShadowEventBook, "update", fail_update)
    baseline_events = _consume(baseline, [rows[34]])
    shadow_events = _consume(shadow, [rows[34]])
    fault = next(
        event
        for event in shadow_events
        if event["event_type"] == "meta_shadow_processing_failed"
    )

    assert [
        event
        for event in shadow_events
        if not str(event["event_type"]).startswith("meta_shadow_")
    ] == baseline_events
    assert fault["phase"] == "execution_minute_update"
    assert shadow.meta_shadow_book.view(resolved_limit=0)["cursor_by_asset"] == (
        cursor_before
    )
    assert "/private/source/file" not in json.dumps(fault, sort_keys=True)


def test_target_bar_advance_failure_does_not_block_minute_or_baseline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = _minutes(40)
    strategy = _fast_strategy()
    protection = ProtectedReplayConfig(
        enabled=True,
        stop_risk_units=5.0,
        target_risk_units=5.0,
        timeout_target_bars=2,
    )
    baseline = ForwardPaperStream(asset="BTCUSDT", timeframe="1m", strategy=strategy)
    shadow = ForwardPaperStream(
        asset="BTCUSDT",
        timeframe="1m",
        strategy=strategy,
        meta_shadow_protection=protection,
        meta_artifact_reason="artifact_not_found",
    )
    _consume(baseline, rows[:34])
    _consume(shadow, rows[:34])

    def fail_advance(_book: ShadowEventBook, **_kwargs: Any) -> None:
        raise RuntimeError("target failure at /private/target/state")

    monkeypatch.setattr(ShadowEventBook, "advance_target_bar", fail_advance)
    baseline_events = _consume(baseline, [rows[34]])
    shadow_events = _consume(shadow, [rows[34]])
    fault = next(
        event
        for event in shadow_events
        if event["event_type"] == "meta_shadow_processing_failed"
    )

    assert [
        event
        for event in shadow_events
        if not str(event["event_type"]).startswith("meta_shadow_")
    ] == baseline_events
    assert fault["phase"] == "accepted_target_bar_advance"
    assert "/private/target/state" not in json.dumps(fault, sort_keys=True)
    assert shadow.meta_shadow_book is not None
    active = shadow.meta_shadow_book.view(resolved_limit=0)["active"]
    assert active[0]["target_bars_elapsed"] == 0


def test_service_env_path_is_server_only_and_missing_artifact_does_not_abort(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    missing_artifact = tmp_path / "server-only" / "missing-model.json"
    monkeypatch.setenv(FORWARD_META_ARTIFACT_ENV, str(missing_artifact))
    config = ForwardPaperConfig(
        assets=("BTCUSDT",),
        timeframes=("1m",),
        state_dir=tmp_path / "state",
        poll_interval_seconds=5,
    )
    started = datetime(2026, 7, 13, tzinfo=timezone.utc)
    coordinator = ForwardPaperCoordinator(
        config,
        source_router=object(),  # type: ignore[arg-type]
        bootstrap_loader=lambda *_args: [],
        anchor_loader=lambda *_args: None,
        started_at=started,
    )
    try:
        manifest_text = json.dumps(coordinator.manifest, sort_keys=True)
        meta_contract = coordinator.manifest["engine_contract"]["meta_shadow"]
        status = coordinator._publish_status(status="running")

        assert config.meta_shadow_enabled is True
        assert str(missing_artifact) not in manifest_text
        assert meta_contract["enabled"] is True
        assert meta_contract["artifact_identity"]["reason"] == "artifact_not_found"
        assert meta_contract["label_clock"] == (
            "max_nominal_close_and_first_seen_observation"
        )
        assert meta_contract["timeout_clock"] == (
            "accepted_finalized_selected_timeframe_bars"
        )
        assert meta_contract["shadow_failure_policy"] == (
            "copy_on_write_fail_open_baseline_unchanged"
        )
        assert meta_contract["affects_orders"] is False
        shadow_status = status["streams"]["BTCUSDT|1m"]["meta_shadow"]
        assert shadow_status["enabled"] is True
        assert shadow_status["failure_count"] == 0
        assert shadow_status["last_failure"] is None
        assert coordinator.streams["BTCUSDT|1m"].meta_artifact is None
        saved_run_id = coordinator.run_id
    finally:
        coordinator.close()

    restored = ForwardPaperCoordinator(
        config,
        source_router=object(),  # type: ignore[arg-type]
        bootstrap_loader=lambda *_args: pytest.fail("must restore the stream snapshot"),
        anchor_loader=lambda *_args: pytest.fail("must restore the source checkpoint"),
        started_at=started + timedelta(hours=1),
    )
    try:
        assert restored.run_id == saved_run_id
        assert restored.streams["BTCUSDT|1m"].meta_shadow_book is not None
        restored_snapshot_text = json.dumps(
            restored.streams["BTCUSDT|1m"].snapshot(), sort_keys=True
        )
        assert str(missing_artifact) not in restored_snapshot_text
    finally:
        restored.close()
