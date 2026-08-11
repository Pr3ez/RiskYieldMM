from __future__ import annotations

import copy
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import polars as pl
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ANALYST_ROOT = PROJECT_ROOT / "Risk_Yield_Meta_Model_Analyst_0_0_1"
if str(ANALYST_ROOT) not in sys.path:
    sys.path.insert(0, str(ANALYST_ROOT))

from chart_config import timeframe_seconds  # noqa: E402
from minute_replay import (  # noqa: E402
    IndicatorStrategyConfig,
    ProtectedReplayConfig,
    ReplayCostConfig,
    meta_label_policy_digest,
)
from trade_ml import (  # noqa: E402
    BarrierConfig,
    BarrierOutcome,
    ShadowCandidate,
    ShadowEventBook,
    TradeSide,
    build_feature_snapshot,
)
from trade_ml.artifact import load_artifact  # noqa: E402
from trade_ml.features import META_FEATURE_NAMES  # noqa: E402
from trade_ml.splits import ExpandingWalkForwardConfig  # noqa: E402

from scripts.analysis.train_analyst_cusum_meta_model import (  # noqa: E402
    CollectedDataset,
    MetaTrainingRow,
    build_training_report,
    collect_canonical_replay_rows,
    extract_mature_replay_rows,
    fit_candidate_model,
    persist_candidate_outputs,
)

BASE = datetime(2025, 1, 1, tzinfo=timezone.utc)
POLICY_DIGEST = "a" * 64


def _candidate(
    event_id: str,
    *,
    asset: str = "BTCUSDT",
    timeframe: str = "15m",
    decision_at: datetime = BASE,
    eligible_minute: int = 1,
    timeout_bars: int = 5,
    policy_digest: str = POLICY_DIGEST,
) -> ShadowCandidate:
    setup_id = f"setup-{event_id}"
    config = BarrierConfig(
        stop_risk_units=1.0,
        target_risk_units=2.0,
        timeout_target_bars=timeout_bars,
        target_interval_seconds=timeframe_seconds(timeframe),
    )
    snapshot = build_feature_snapshot(
        setup_id=setup_id,
        side=TradeSide.LONG,
        decision_at=decision_at,
        online={
            "source_timestamp": decision_at,
            "available_at": decision_at,
            "status": "ok",
            "log_return": 0.01,
            "trend_score": 0.5,
            "trend_agreement": 0.7,
            "path_quality": 0.6,
            "ewma_vol_slow_pct": 1.0,
        },
        cusum={
            "timestamp": decision_at,
            "available_at": decision_at,
            "status": "ok",
            "regime": 1,
            "bull_start": True,
            "bear_start": False,
            "scale_ready": True,
            "residual": 1.0,
            "res_std": 1.0,
        },
        entry_reference=100.0,
        risk_unit=1.0,
        stop_risk_units=1.0,
        target_risk_units=2.0,
        timeout_target_bars=timeout_bars,
        target_interval_seconds=timeframe_seconds(timeframe),
        estimated_roundtrip_cost_bps=2.0,
    )
    return ShadowCandidate(
        event_id=event_id,
        setup_id=setup_id,
        asset=asset,
        timeframe=timeframe,
        decision_at=decision_at,
        eligible_at=decision_at + timedelta(minutes=eligible_minute),
        side=TradeSide.LONG,
        entry_reference=100.0,
        risk_unit=1.0,
        features=snapshot,
        barrier_config=config,
        policy_digest=policy_digest,
        estimated_roundtrip_cost_bps=2.0,
    )


def _minute(
    minute: int,
    *,
    asset: str = "BTCUSDT",
    decision_at: datetime = BASE,
    high: float = 100.5,
    low: float = 99.5,
    is_real: bool = True,
) -> dict[str, object]:
    return {
        "asset": asset,
        "timestamp": decision_at + timedelta(minutes=minute),
        "open": 100.0,
        "high": high,
        "low": low,
        "close": 100.0,
        "is_real": is_real,
    }


def _mixed_book() -> ShadowEventBook:
    book = ShadowEventBook(max_open_events=10, max_resolved_records=10)
    for event_id, eligible in (
        ("target", 1),
        ("stop", 2),
        ("cancel", 3),
    ):
        book.schedule(_candidate(event_id, eligible_minute=eligible))
    book.update(_minute(1, high=103.0))
    book.update(_minute(2, low=98.0))
    book.update(_minute(3, is_real=False))
    later_decision = BASE + timedelta(minutes=3)
    book.schedule(
        _candidate(
            "active",
            decision_at=later_decision,
            eligible_minute=1,
        )
    )
    book.schedule(
        _candidate(
            "pending",
            decision_at=later_decision,
            eligible_minute=2,
        )
    )
    book.update(_minute(4))
    return book


def test_extraction_keeps_only_mature_economic_rows_and_counts_censoring() -> None:
    replay = {"meta_label_book": _mixed_book().view(resolved_limit=10)}

    extracted = extract_mature_replay_rows(
        replay,
        expected_asset="BTCUSDT",
        expected_timeframe="15m",
        replay_clock=BASE + timedelta(minutes=10),
    )

    assert [row.outcome for row in extracted.rows] == [
        BarrierOutcome.TARGET,
        BarrierOutcome.STOP,
    ]
    assert [row.economic_binary_target for row in extracted.rows] == [1, 0]
    assert extracted.counts == {
        "total_scheduled": 5,
        "total_resolved": 3,
        "eligible_mature_rows": 2,
        "cancelled_excluded": 1,
        "pending_censored_excluded": 1,
        "active_censored_excluded": 1,
        "outcome_counts": {"CANCELLED": 1, "STOP": 1, "TARGET": 1},
    }

    truncated = copy.deepcopy(replay)
    truncated["meta_label_book"]["resolved_truncated_count"] = 1
    with pytest.raises(ValueError, match="truncated"):
        extract_mature_replay_rows(
            truncated,
            expected_asset="BTCUSDT",
            expected_timeframe="15m",
            replay_clock=BASE + timedelta(minutes=10),
        )


def test_collection_runs_every_requested_scope_with_filter_and_routing_off() -> None:
    strategy = IndicatorStrategyConfig()
    costs = ReplayCostConfig()
    protection = ProtectedReplayConfig(enabled=True)
    end = BASE + timedelta(days=30)
    calls: list[dict[str, object]] = []

    def fake_loader(**kwargs):
        return pl.DataFrame({"placeholder": [1]}), {"source_rows": 1, **kwargs}

    def fake_replayer(frame, **kwargs):
        del frame
        calls.append(kwargs)
        asset = str(kwargs["asset"])
        timeframe = str(kwargs["timeframe"])
        decision = end - timedelta(hours=2)
        policy = meta_label_policy_digest(
            strategy=kwargs["strategy"],
            costs=kwargs["costs"],
            protection=kwargs["protection"],
            timeframe=timeframe,
        )
        book = ShadowEventBook()
        book.schedule(
            _candidate(
                f"{asset}-{timeframe}",
                asset=asset,
                timeframe=timeframe,
                decision_at=decision,
                policy_digest=policy,
            )
        )
        book.update(_minute(1, asset=asset, decision_at=decision, high=103.0))
        return {
            "config": {"meta_filter": {"policy_digest": policy}},
            "metadata": {"signal_vintage": "current_canonical_replay"},
            "meta_label_book": book.view(),
        }

    collected = collect_canonical_replay_rows(
        assets=("ETHUSDT", "BTCUSDT"),
        timeframes=("15m", "1m"),
        end=end,
        replay_days=20,
        strategy=strategy,
        costs=costs,
        protection=protection,
        collection_clock=end + timedelta(hours=1),
        loader=fake_loader,
        replayer=fake_replayer,
    )

    assert collected.assets == ("BTCUSDT", "ETHUSDT")
    assert collected.timeframes == ("1m", "15m")
    assert len(collected.rows) == 4
    assert len({row.policy_digest for row in collected.rows}) == 1
    assert collected.counts["requested_selection_count"] == 4
    assert all(call["meta_filter_mode"] == "off" for call in calls)
    assert all(call["meta_artifact"] is None for call in calls)
    assert all(call["capture_series"] is False for call in calls)
    assert all(call["protection"].enabled is True for call in calls)


def _training_rows(rows: int = 90) -> tuple[MetaTrainingRow, ...]:
    output = []
    for index in range(rows):
        target = index % 2
        signal = 1.0 if target else -1.0
        values = tuple(
            signal * (1.0 + column / max(len(META_FEATURE_NAMES), 1))
            + 0.01 * (index % 5)
            for column in range(len(META_FEATURE_NAMES))
        )
        decision = BASE + timedelta(hours=index)
        output.append(
            MetaTrainingRow(
                asset="BTCUSDT",
                timeframe="1h",
                event_id=f"event-{index:03d}",
                decision_at=decision,
                label_known_at=decision + timedelta(hours=2),
                outcome=(BarrierOutcome.TARGET if target else BarrierOutcome.STOP),
                economic_binary_target=target,
                feature_values=values,
                policy_digest=POLICY_DIGEST,
            )
        )
    return tuple(output)


def test_candidate_fit_and_reports_are_immutable_and_never_promoted(tmp_path) -> None:
    rows = _training_rows()
    fitted = fit_candidate_model(
        rows,
        assets=("BTCUSDT",),
        timeframes=("1h",),
        policy_digest=POLICY_DIGEST,
        model_version="cusum-meta-test-v1",
        decision_threshold=0.55,
        split_config=ExpandingWalkForwardConfig(
            min_train_rows=20,
            validation_rows=10,
        ),
        created_at=BASE + timedelta(days=10),
    )
    collected = CollectedDataset(
        rows=rows,
        policy_digest=POLICY_DIGEST,
        assets=("BTCUSDT",),
        timeframes=("1h",),
        selection_reports=(),
        counts={"training_row_count": len(rows)},
    )
    strategy = IndicatorStrategyConfig()
    costs = ReplayCostConfig()
    protection = ProtectedReplayConfig(enabled=True)
    outputs = persist_candidate_outputs(
        output_dir=tmp_path,
        fitted=fitted,
        report_builder=lambda artifact_path: build_training_report(
            collected=collected,
            fitted=fitted,
            strategy=strategy,
            costs=costs,
            protection=protection,
            evaluation_start=BASE,
            evaluation_end=BASE + timedelta(days=5),
            artifact_path=artifact_path,
        ),
    )

    artifact = load_artifact(outputs["artifact"])
    report = json.loads(outputs["json_report"].read_text())
    markdown = outputs["markdown_report"].read_text()
    assert artifact.feature_names == META_FEATURE_NAMES
    assert artifact.evaluation_metrics["candidate_only"] is True
    assert artifact.evaluation_metrics["deployment_scope"] == {
        "eligible_selections": []
    }
    assert fitted.evaluation["controls"]["scored_rows"] > 0
    selection_metrics = fitted.evaluation["subgroups"]["selection"]["BTCUSDT/1h"]
    assert selection_metrics["model_metrics"]["rows"] > 0
    assert selection_metrics["causal_base_rate_metrics"]["rows"] > 0
    assert report["status"] == "CANDIDATE_ONLY_NOT_PROMOTED"
    assert report["protocol"]["label_clock"] == (
        "canonical_nominal_bar_close_plus_fixed_5_second_scenario"
    )
    assert report["protocol"]["historical_label_maturity_embargo_seconds"] == (
        24.0 * 60.0 * 60.0
    )
    assert report["protocol"]["deployment_label_clock"] == (
        "journaled_actual_first_seen_at_required"
    )
    assert report["deployment"] == {
        "auto_promoted": False,
        "chart_gate_enabled": False,
        "environment_variable_changed": False,
        "live_order_routing_enabled": False,
        "next_allowed_stage": "explicit_offline_review_then_live_shadow_only",
    }
    assert "not promoted" in markdown.lower()
    with pytest.raises(FileExistsError, match="immutable"):
        persist_candidate_outputs(
            output_dir=tmp_path,
            fitted=fitted,
            report_builder=lambda _: report,
        )
