from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import polars as pl
import pytest

ANALYST_ROOT = (
    Path(__file__).resolve().parents[1] / "Risk_Yield_Meta_Model_Analyst_0_0_1"
)
if str(ANALYST_ROOT) not in sys.path:
    sys.path.insert(0, str(ANALYST_ROOT))

import chart_server  # noqa: E402
from forward_paper.chart_overlay import (  # noqa: E402
    LiveChartOverlayError,
    read_meta_shadow_chart_overlay,
)
from forward_paper.event_store import (  # noqa: E402
    EventInput,
    EventStore,
    RunInput,
)
from forward_paper.runtime import atomic_write_json  # noqa: E402

UTC = timezone.utc


def _create_run(store: EventStore, run_id: str, created_at: datetime) -> None:
    store.create_run(
        RunInput(
            run_id=run_id,
            created_at=created_at,
            metadata={"source_vintage": "append_only_first_seen"},
        )
    )


def _prediction(
    run_id: str,
    occurred_at: datetime,
    *,
    event_id: str,
    asset: str = "BTCUSDT",
    timeframe: str = "1h",
    shadow_event_id: str = "shadow-1",
    probability: float | None = 0.72,
    available: bool = True,
    score_reason: str | None = None,
    counterfactual_reason: str | None = None,
) -> EventInput:
    return EventInput(
        event_id=event_id,
        stream_id=f"{run_id}:{asset}|{timeframe}",
        event_type="meta_shadow_prediction",
        occurred_at=occurred_at,
        observed_at=occurred_at,
        payload={
            "asset": asset,
            "timeframe": timeframe,
            "shadow_event_id": shadow_event_id,
            "decision_at": occurred_at.isoformat(),
            "side": "LONG",
            "available": available,
            "probability": probability,
            "counterfactual_accepted": bool(available and probability is not None),
            "score_reason": score_reason
            or ("accepted" if available else "artifact_not_found"),
            "counterfactual_reason": counterfactual_reason
            or ("accepted" if available else "artifact_not_found"),
            "artifact_checksum": "model-digest-123",
            "policy_digest": "policy-digest-456",
            # These sensitive/raw fields prove the chart export is allowlist-only.
            "feature_snapshot": {"secret_feature": 42.0},
            "model_path": "/private/model/artifact.json",
            "coefficients": [1.0, 2.0],
        },
    )


def _label(
    run_id: str,
    known_at: datetime,
    *,
    event_id: str,
    shadow_event_id: str = "shadow-1",
    touch_at: datetime | None = None,
    observed_at: datetime | None = None,
    asset: str = "BTCUSDT",
    timeframe: str = "1h",
    reason: str = "target_touched",
) -> EventInput:
    touch = touch_at or known_at - timedelta(minutes=15)
    return EventInput(
        event_id=event_id,
        stream_id=f"{run_id}:{asset}|{timeframe}",
        event_type="meta_shadow_label",
        occurred_at=known_at,
        observed_at=observed_at or known_at,
        payload={
            "asset": asset,
            "timeframe": timeframe,
            "shadow_event_id": shadow_event_id,
            "label_known_at": known_at.isoformat(),
            "outcome": "TARGET",
            "outcome_occurred_at": touch.isoformat(),
            "economic_binary_target": 1,
            "reason": reason,
            "artifact_checksum": "model-digest-123",
            "policy_digest": "policy-digest-456",
            "shadow_record": {"candidate": {"side": "long"}},
        },
    )


def _other_event(run_id: str, occurred_at: datetime) -> EventInput:
    return EventInput(
        event_id="paper-mark",
        stream_id=f"{run_id}:BTCUSDT|1h",
        event_type="paper_mark",
        occurred_at=occurred_at,
        payload={"asset": "BTCUSDT", "timeframe": "1h"},
    )


def test_reader_filters_run_storage_stream_and_redacts_raw_model_fields(
    tmp_path: Path,
) -> None:
    database = tmp_path / "forward_paper.sqlite3"
    status = tmp_path / "status.json"
    base = datetime(2026, 7, 13, 10, 0, tzinfo=UTC)
    with EventStore(database) as store:
        _create_run(store, "old-run", base - timedelta(days=1))
        store.append_batch(
            "old-run",
            [_prediction("old-run", base, event_id="old-prediction")],
        )
        _create_run(store, "active-run", base)
        store.append_batch(
            "active-run",
            [
                _prediction(
                    "active-run", base + timedelta(hours=1), event_id="prediction"
                ),
                _prediction(
                    "active-run",
                    base + timedelta(hours=1),
                    event_id="wrong-stream",
                    timeframe="4h",
                ),
                _other_event("active-run", base + timedelta(hours=1)),
                _label(
                    "active-run",
                    base + timedelta(hours=2),
                    event_id="label",
                    touch_at=base + timedelta(hours=1, minutes=20),
                ),
            ],
        )
        atomic_write_json(status, {"run_id": "active-run", "status": "running"})

        overlay = read_meta_shadow_chart_overlay(
            asset="BTCUSDT",
            timeframe="1h",
            database_path=database,
            status_path=status,
            as_of=base + timedelta(hours=3),
        ).payload

    assert overlay["run_id"] == "active-run"
    assert overlay["stream_id"] == "active-run:BTCUSDT|1h"
    assert overlay["counts"] == {
        "events": 2,
        "predictions": 1,
        "available_scores": 1,
        "unavailable_predictions": 0,
        "accepted": 1,
        "rejected": 0,
        "labels": 1,
    }
    assert overlay["scores"] == [
        {
            "time": int((base + timedelta(hours=1)).timestamp()),
            "value": 0.72,
            "shadow_event_id": "shadow-1",
            "side": "LONG",
            "accepted": True,
            "reason": "accepted",
            "model_digest": "model-digest-123",
            "policy_digest": "policy-digest-456",
        }
    ]
    marker = overlay["outcome_markers"][0]
    assert marker["time"] == int((base + timedelta(hours=2)).timestamp())
    assert marker["label_known_at"] == "2026-07-13T12:00:00Z"
    assert marker["time_semantics"] == "known_at"
    encoded = json.dumps(overlay, sort_keys=True)
    for forbidden in (
        "feature_snapshot",
        "secret_feature",
        "model_path",
        "coefficients",
        "outcome_occurred_at",
        "/private/model",
    ):
        assert forbidden not in encoded
    assert {item["event_type"] for item in overlay["audit"]} == {
        "meta_shadow_prediction",
        "meta_shadow_label",
    }


def test_free_form_meta_reasons_are_redacted_before_chart_export(
    tmp_path: Path,
) -> None:
    database = tmp_path / "forward_paper.sqlite3"
    base = datetime(2026, 7, 13, 10, 0, tzinfo=UTC)
    private_path = "/private/model/candidate.artifact.json"
    with EventStore(database) as store:
        _create_run(store, "run", base)
        store.append_batch(
            "run",
            [
                _prediction(
                    "run",
                    base,
                    event_id="prediction",
                    score_reason=f"failed to read {private_path}",
                    counterfactual_reason=f"exception at {private_path}",
                ),
                _label(
                    "run",
                    base + timedelta(hours=1),
                    event_id="label",
                    reason=f"resolver failed at {private_path}",
                ),
            ],
        )
        payload = read_meta_shadow_chart_overlay(
            asset="BTCUSDT",
            timeframe="1h",
            database_path=database,
            run_id="run",
            as_of=base + timedelta(hours=2),
        ).payload

    encoded = json.dumps(payload, sort_keys=True)
    assert private_path not in encoded
    reasons = {
        item.get("availability_reason")
        or item.get("acceptance_reason")
        or item.get("label_reason")
        for item in payload["audit"]
    }
    assert reasons == {"redacted_unrecognized_reason"}


@pytest.mark.parametrize(
    "reason",
    [
        "barrier_invalid_at_actual_shadow_fill",
        "continuous_market_data_gap_before_entry",
        "continuous_market_non_real_minute_before_entry",
        "maximum_finalized_target_bars_reached",
    ],
)
def test_v2_shadow_terminal_reason_codes_are_safe_for_chart_export(
    tmp_path: Path,
    reason: str,
) -> None:
    database = tmp_path / "forward_paper.sqlite3"
    base = datetime(2026, 7, 13, 10, 0, tzinfo=UTC)
    with EventStore(database) as store:
        _create_run(store, "run", base)
        store.append_batch(
            "run",
            [_label("run", base, event_id="label", reason=reason)],
        )
        payload = read_meta_shadow_chart_overlay(
            asset="BTCUSDT",
            timeframe="1h",
            database_path=database,
            run_id="run",
            as_of=base,
        ).payload

    assert payload["audit"][0]["label_reason"] == reason
    assert reason in json.dumps(payload, sort_keys=True)


def test_as_of_start_end_and_row_limit_never_reveal_future_label(
    tmp_path: Path,
) -> None:
    database = tmp_path / "forward_paper.sqlite3"
    base = datetime(2026, 7, 13, 10, 0, tzinfo=UTC)
    with EventStore(database) as store:
        _create_run(store, "run", base)
        store.append_batch(
            "run",
            [
                _prediction("run", base, event_id="prediction"),
                _label(
                    "run",
                    base + timedelta(hours=2),
                    event_id="future-label",
                    touch_at=base + timedelta(minutes=30),
                ),
            ],
        )
        before_known = read_meta_shadow_chart_overlay(
            asset="BTCUSDT",
            timeframe="1h",
            database_path=database,
            run_id="run",
            as_of=base + timedelta(hours=1),
        ).payload
        label_only = read_meta_shadow_chart_overlay(
            asset="BTCUSDT",
            timeframe="1h",
            database_path=database,
            run_id="run",
            as_of=base + timedelta(hours=3),
            start=base + timedelta(hours=2),
            end=base + timedelta(hours=2),
        ).payload
        bounded = read_meta_shadow_chart_overlay(
            asset="BTCUSDT",
            timeframe="1h",
            database_path=database,
            run_id="run",
            as_of=base + timedelta(hours=3),
            max_rows=1,
        ).payload

    assert before_known["counts"]["labels"] == 0
    assert before_known["outcome_markers"] == []
    assert label_only["counts"]["predictions"] == 0
    assert label_only["outcome_markers"][0]["side"] == "LONG"
    assert bounded["rows_truncated"] is True
    assert bounded["counts"]["events"] == 1
    assert bounded["audit"][0]["event_type"] == "meta_shadow_label"


def test_current_run_without_meta_shadow_is_empty_unavailable_not_error(
    tmp_path: Path,
) -> None:
    database = tmp_path / "forward_paper.sqlite3"
    status = tmp_path / "status.json"
    now = datetime(2026, 7, 13, 10, 0, tzinfo=UTC)
    with EventStore(database) as store:
        _create_run(store, "disabled-run", now)
    atomic_write_json(status, {"run_id": "disabled-run", "status": "running"})

    payload = read_meta_shadow_chart_overlay(
        asset="BTCUSDT",
        timeframe="1h",
        database_path=database,
        status_path=status,
        as_of=now,
    ).payload

    assert payload["available"] is False
    assert payload["status"] == "no_meta_shadow_events"
    assert payload["reason"] == "meta_shadow_not_enabled_or_no_signals_for_selection"
    assert payload["run_id"] == "disabled-run"
    assert payload["scores"] == []
    assert payload["outcome_markers"] == []
    assert payload["audit"] == []


def test_as_of_excludes_event_not_yet_observed_by_the_journal(tmp_path: Path) -> None:
    database = tmp_path / "forward_paper.sqlite3"
    base = datetime(2026, 7, 13, 10, 0, tzinfo=UTC)
    with EventStore(database) as store:
        _create_run(store, "run", base)
        store.append_batch(
            "run",
            [
                _label(
                    "run",
                    base + timedelta(minutes=30),
                    observed_at=base + timedelta(hours=2),
                    event_id="late-journal-label",
                )
            ],
        )
        before_observation = read_meta_shadow_chart_overlay(
            asset="BTCUSDT",
            timeframe="1h",
            database_path=database,
            run_id="run",
            as_of=base + timedelta(hours=1),
        ).payload

    assert before_observation["counts"]["events"] == 0
    assert before_observation["outcome_markers"] == []


def test_invalid_prediction_decision_timestamp_fails_closed(tmp_path: Path) -> None:
    database = tmp_path / "forward_paper.sqlite3"
    now = datetime(2026, 7, 13, 10, 0, tzinfo=UTC)
    invalid = _prediction("run", now, event_id="invalid")
    assert isinstance(invalid.payload, dict)
    invalid.payload["decision_at"] = (now - timedelta(minutes=1)).isoformat()
    with EventStore(database) as store:
        _create_run(store, "run", now)
        store.append_batch("run", [invalid])
        with pytest.raises(
            LiveChartOverlayError,
            match="occurred_at must equal immutable decision_at",
        ):
            read_meta_shadow_chart_overlay(
                asset="BTCUSDT",
                timeframe="1h",
                database_path=database,
                run_id="run",
                as_of=now + timedelta(minutes=1),
            )


def test_chart_helper_uses_live_run_and_visible_chart_bounds(monkeypatch: Any) -> None:
    base = datetime(2026, 7, 13, 10, 0, tzinfo=UTC)
    calls: list[dict[str, Any]] = []

    def fake_reader(**kwargs: Any) -> SimpleNamespace:
        calls.append(kwargs)
        return SimpleNamespace(payload={"scores": [], "outcome_markers": []})

    monkeypatch.setattr(chart_server, "read_meta_shadow_chart_overlay", fake_reader)
    frame = pl.DataFrame(
        {
            "timestamp": [base, base + timedelta(hours=1)],
            "open": [1.0, 1.0],
            "high": [1.0, 1.0],
            "low": [1.0, 1.0],
            "close": [1.0, 1.0],
            "volume": [1.0, 1.0],
        },
        schema_overrides={"timestamp": pl.Datetime("us", "UTC")},
    )
    result = chart_server._forward_meta_shadow_for_chart(
        frame=frame,
        metadata={
            "asset": "BTCUSDT",
            "timeframe": "1h",
            "source": "canonical",
            "live_overlay": {"run_id": "selected-run"},
        },
        as_of=base + timedelta(hours=4),
    )

    assert result == {"scores": [], "outcome_markers": []}
    assert calls == [
        {
            "asset": "BTCUSDT",
            "timeframe": "1h",
            "run_id": "selected-run",
            "as_of": base + timedelta(hours=4),
            "start": base,
            "end": base + timedelta(hours=2),
        }
    ]


def test_chart_helper_does_not_expose_overlay_exception_details(
    monkeypatch: Any,
) -> None:
    base = datetime(2026, 7, 13, 10, 0, tzinfo=UTC)
    frame = pl.DataFrame(
        {
            "timestamp": [base],
            "open": [1.0],
            "high": [1.0],
            "low": [1.0],
            "close": [1.0],
            "volume": [1.0],
        },
        schema_overrides={"timestamp": pl.Datetime("us", "UTC")},
    )

    def fail_reader(**_kwargs: Any) -> None:
        raise LiveChartOverlayError("failed at /private/forward/status.json")

    monkeypatch.setattr(chart_server, "read_meta_shadow_chart_overlay", fail_reader)
    result = chart_server._forward_meta_shadow_for_chart(
        frame=frame,
        metadata={
            "asset": "BTCUSDT",
            "timeframe": "1h",
            "source": "canonical",
        },
        as_of=base + timedelta(hours=1),
    )

    assert result["status"] == "overlay_error"
    assert result["reason"] == "forward_meta_shadow_journal_read_failed"
    assert result["error_type"] == "LiveChartOverlayError"
    assert "/private" not in json.dumps(result)


def test_chart_helper_moves_outcome_to_first_candle_after_label_maturity(
    monkeypatch: Any,
) -> None:
    base = datetime(2026, 7, 13, 10, 0, tzinfo=UTC)
    frame = pl.DataFrame(
        {
            "timestamp": [base, base + timedelta(hours=1)],
            "open": [1.0, 1.0],
            "high": [1.0, 1.0],
            "low": [1.0, 1.0],
            "close": [1.0, 1.0],
            "volume": [1.0, 1.0],
        },
        schema_overrides={"timestamp": pl.Datetime("us", "UTC")},
    )
    known_at = base + timedelta(minutes=15)
    after_last = base + timedelta(hours=1, minutes=15)
    raw_payload = {
        "scores": [],
        "outcome_markers": [
            {
                "time": int(known_at.timestamp()),
                "known_at": known_at.isoformat(),
                "outcome": "TARGET",
            },
            {
                "time": int(after_last.timestamp()),
                "known_at": after_last.isoformat(),
                "outcome": "STOP",
            },
        ],
    }
    monkeypatch.setattr(
        chart_server,
        "read_meta_shadow_chart_overlay",
        lambda **_kwargs: SimpleNamespace(payload=raw_payload),
    )

    result = chart_server._forward_meta_shadow_for_chart(
        frame=frame,
        metadata={
            "asset": "BTCUSDT",
            "timeframe": "1h",
            "source": "canonical",
        },
        as_of=base + timedelta(hours=2),
    )

    assert result["outcome_markers"] == [
        {
            "time": int((base + timedelta(hours=1)).timestamp()),
            "known_at": known_at.isoformat(),
            "known_at_epoch": int(known_at.timestamp()),
            "outcome": "TARGET",
            "time_semantics": "first_candle_at_or_after_known_at",
        }
    ]


def test_chart_response_exposes_forward_meta_shadow_as_separate_payload_field(
    monkeypatch: Any,
) -> None:
    base = datetime(2026, 7, 13, 10, 0, tzinfo=UTC)
    frame = pl.DataFrame(
        {
            "timestamp": [base],
            "open": [1.0],
            "high": [1.0],
            "low": [1.0],
            "close": [1.0],
            "volume": [1.0],
        },
        schema_overrides={"timestamp": pl.Datetime("us", "UTC")},
    )
    metadata = {
        "asset": "BTCUSDT",
        "timeframe": "1h",
        "source": "canonical",
        "requested_end": None,
    }
    expected_overlay = {"scores": [{"time": int(base.timestamp()), "value": 0.6}]}
    monkeypatch.setattr(
        chart_server,
        "load_ohlcv_window",
        lambda **_kwargs: (frame, metadata),
    )
    monkeypatch.setattr(
        chart_server,
        "_apply_live_chart_overlay",
        lambda **_kwargs: (frame, metadata, None),
    )
    monkeypatch.setattr(
        chart_server,
        "build_lightweight_charts_payload",
        lambda **_kwargs: {
            "metadata": metadata,
            "candles": [{"time": int(base.timestamp())}],
        },
    )
    monkeypatch.setattr(
        chart_server,
        "_forward_meta_shadow_for_chart",
        lambda **_kwargs: expected_overlay,
    )

    payload = chart_server._build_chart_response(
        "asset=BTCUSDT&timeframe=1h&source=canonical"
    )

    assert payload["forward_meta_shadow"] is expected_overlay


def test_browser_contract_has_fixed_probability_pane_and_known_time_markers() -> None:
    app_path = ANALYST_ROOT / "web" / "app.js"
    html_path = ANALYST_ROOT / "web" / "index.html"
    app = app_path.read_text(encoding="utf-8")
    html = html_path.read_text(encoding="utf-8")

    assert "priceRange: { minValue: 0, maxValue: 1 }" in app
    assert 'ensureIndicatorPane("forward_meta_shadow"' in app
    assert "forward_meta_shadow_score" in app
    assert "forwardMetaOutcomeMarkersForLoadedChart" in app
    assert "first_candle_at_or_after_known_at" in app
    assert "function mergeForwardMetaShadow" in app
    assert app.count("historyState.forwardMetaShadow = mergeForwardMetaShadow(") == 2
    assert "forward_meta_shadow" in app
    assert 'id="forward-meta-shadow-legend"' in html
    assert "outcome known" in html
    subprocess.run(["node", "--check", str(app_path)], check=True)
