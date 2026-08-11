"""Provider-graded finalized-1m ingestion and forward-paper coordination.

This service never routes real orders.  It journals the first version of each
finalized minute that it actually observed, fans that minute into independent
asset/timeframe paper streams, and persists enough immutable information to
recover without replaying today's revised canonical files.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import threading
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import polars as pl
from chart_config import (
    BYBIT_ASSETS,
    CANONICAL_TIMEFRAMES,
    CORE_ASSETS,
    normalize_asset,
    normalize_timeframe,
    resolve_ohlcv_files,
    timeframe_seconds,
)
from minute_replay import (
    EXECUTION_MODEL_VERSION,
    IndicatorStrategyConfig,
    ProtectedReplayConfig,
    ReplayCostConfig,
    meta_label_policy_digest,
)
from trade_ml.artifact import (
    ArtifactLoadResult,
    LogisticCoefficientArtifact,
    load_artifact_safe,
)
from trade_ml.features import META_FEATURE_NAMES

from .event_store import (
    EventInput,
    EventStore,
    RunInput,
    ServiceStateInput,
    SnapshotInput,
)
from .runtime import (
    as_utc,
    atomic_write_json,
    default_state_dir,
    iso_utc,
    parse_utc,
    utc_now,
)
from .sources import (
    BybitFinalizedMinuteSource,
    FinalizedMinuteBatch,
    FinalizedMinuteSourceRouter,
    YahooFinalizedMinuteSource,
    stable_row_fingerprint,
)
from .stream import (
    FORWARD_PAPER_STREAM_VERSION,
    PAPER_EVENT_VERSION,
    PAPER_FILL_SCHEMA_VERSION,
    PAPER_LEDGER_VERSION,
    PAPER_ORDER_SCHEMA_VERSION,
    ForwardPaperStream,
)
from .supervisor import status_path

FORWARD_PAPER_SERVICE_VERSION = "forward_paper_service_v3"
SERVICE_ID = "riskyield-forward-paper"
DATABASE_FILENAME = "forward_paper.sqlite3"
BOOTSTRAP_TARGET_BARS = 400
RECENT_FINGERPRINT_LIMIT = 8
DEFAULT_SOURCE_TAIL_ROWS = 1_000
DEFAULT_POLL_INTERVAL_SECONDS = 60.0
MIN_POLL_INTERVAL_SECONDS = 5.0
MAX_POLL_INTERVAL_SECONDS = 3_600.0
FORWARD_META_ARTIFACT_ENV = "RISKYIELDMM_FORWARD_META_ARTIFACT"

BootstrapLoader = Callable[[str, str, datetime], list[dict[str, Any]]]
AnchorLoader = Callable[[str, datetime], datetime | None]


def _configured_meta_artifact_path() -> Path | None:
    raw = os.environ.get(FORWARD_META_ARTIFACT_ENV, "").strip()
    return None if not raw else Path(raw).expanduser().resolve()


@dataclass(frozen=True)
class ForwardPaperConfig:
    """Frozen paper-cohort and service settings."""

    assets: tuple[str, ...] = CORE_ASSETS
    timeframes: tuple[str, ...] = CANONICAL_TIMEFRAMES
    strategy: IndicatorStrategyConfig = field(default_factory=IndicatorStrategyConfig)
    costs: ReplayCostConfig = field(
        default_factory=lambda: ReplayCostConfig(execution_latency_minutes=1)
    )
    meta_shadow_protection: ProtectedReplayConfig = field(
        default_factory=lambda: ProtectedReplayConfig(enabled=True)
    )
    meta_shadow_artifact_path: Path | None = field(
        default_factory=_configured_meta_artifact_path,
        repr=False,
    )
    state_dir: Path = field(default_factory=default_state_dir)
    poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS
    max_source_tail_rows: int = DEFAULT_SOURCE_TAIL_ROWS
    require_live_feeds: bool = False
    research_status: str = "historical_optimizer_rejected_observe_only"

    def __post_init__(self) -> None:
        assets = tuple(dict.fromkeys(normalize_asset(asset) for asset in self.assets))
        timeframes = tuple(
            dict.fromkeys(normalize_timeframe(value) for value in self.timeframes)
        )
        unknown_timeframes = [
            timeframe
            for timeframe in timeframes
            if timeframe not in CANONICAL_TIMEFRAMES
        ]
        if unknown_timeframes:
            raise ValueError(
                "Forward paper supports canonical timeframes only: "
                + ", ".join(unknown_timeframes)
            )
        if not assets or not timeframes:
            raise ValueError("At least one asset and timeframe are required")
        poll = float(self.poll_interval_seconds)
        if not math.isfinite(poll) or not (
            MIN_POLL_INTERVAL_SECONDS <= poll <= MAX_POLL_INTERVAL_SECONDS
        ):
            raise ValueError(
                f"poll_interval_seconds must be between "
                f"{MIN_POLL_INTERVAL_SECONDS:g} and "
                f"{MAX_POLL_INTERVAL_SECONDS:g}"
            )
        if (
            isinstance(self.max_source_tail_rows, bool)
            or not 3 <= self.max_source_tail_rows <= 1_000
        ):
            raise ValueError("max_source_tail_rows must be between 3 and 1000")
        if not self.research_status.strip():
            raise ValueError("research_status cannot be empty")
        if not isinstance(self.meta_shadow_protection, ProtectedReplayConfig):
            raise TypeError("meta_shadow_protection must be a ProtectedReplayConfig")
        artifact_path = self.meta_shadow_artifact_path
        if artifact_path is not None:
            if not self.meta_shadow_protection.enabled:
                raise ValueError(
                    "Configured meta shadow artifact requires enabled protection"
                )
            artifact_path = Path(artifact_path).expanduser().resolve()
        if self.require_live_feeds and any(
            asset not in BYBIT_ASSETS for asset in assets
        ):
            delayed = ", ".join(asset for asset in assets if asset not in BYBIT_ASSETS)
            raise ValueError(
                "Trading-grade live feeds are unavailable for the selected assets "
                f"without Databento Live entitlement: {delayed}"
            )
        object.__setattr__(self, "assets", assets)
        object.__setattr__(self, "timeframes", timeframes)
        object.__setattr__(
            self, "state_dir", Path(self.state_dir).expanduser().resolve()
        )
        object.__setattr__(self, "poll_interval_seconds", poll)
        object.__setattr__(self, "meta_shadow_artifact_path", artifact_path)

    @property
    def meta_shadow_enabled(self) -> bool:
        """Whether the server was explicitly configured for shadow scoring."""

        return self.meta_shadow_artifact_path is not None

    def meta_shadow_contract(
        self, *, artifact_identity: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Return public shadow-only digests without the server-side path."""

        if not self.meta_shadow_enabled:
            return {
                "enabled": False,
                "mode": "disabled",
                "artifact_identity": dict(artifact_identity),
                "affects_orders": False,
                "affects_positions": False,
                "real_order_routing": False,
            }
        protection = self.meta_shadow_protection
        return {
            "enabled": True,
            "mode": "shadow_only_no_order_effect",
            "artifact_identity": dict(artifact_identity),
            "protection_config_digest": protection.digest(),
            "barrier_config_digests": {
                timeframe: protection.barrier_config(timeframe).digest()
                for timeframe in self.timeframes
            },
            "policy_digests": {
                timeframe: meta_label_policy_digest(
                    strategy=self.strategy,
                    costs=self.costs,
                    protection=protection,
                    timeframe=timeframe,
                )
                for timeframe in self.timeframes
            },
            "event_sampling": "fresh_cusum_bull_or_bear_start_once",
            "entry_model": "first_exact_eligible_real_1m_open",
            "label_clock": "max_nominal_close_and_first_seen_observation",
            "timeout_clock": "accepted_finalized_selected_timeframe_bars",
            "strategy_exit_policy": "ignored_after_shadow_fill_until_terminal",
            "shadow_failure_policy": "copy_on_write_fail_open_baseline_unchanged",
            "durable_journal_failure_policy": "fail_closed",
            "affects_orders": False,
            "affects_positions": False,
            "real_order_routing": False,
        }

    def engine_contract(
        self, *, artifact_identity: Mapping[str, Any] | None = None
    ) -> dict[str, Any]:
        """Return the immutable execution and evidence contract for this cohort."""

        resolved_artifact_identity = (
            {
                "available": False,
                "reason": (
                    "artifact_identity_not_loaded"
                    if self.meta_shadow_enabled
                    else "disabled"
                ),
                "model_version": None,
                "checksum": None,
            }
            if artifact_identity is None
            else dict(artifact_identity)
        )

        return {
            "service_version": FORWARD_PAPER_SERVICE_VERSION,
            "stream_version": FORWARD_PAPER_STREAM_VERSION,
            "ledger_version": PAPER_LEDGER_VERSION,
            "event_version": PAPER_EVENT_VERSION,
            "execution_model_version": EXECUTION_MODEL_VERSION,
            "order_schema_version": PAPER_ORDER_SCHEMA_VERSION,
            "fill_schema_version": PAPER_FILL_SCHEMA_VERSION,
            "strategy": self.strategy.as_dict(),
            "strategy_digest": self.strategy.digest(),
            "costs": self.costs.as_dict(),
            "cost_digest": self.costs.digest(),
            "source_vintage": "append_only_first_seen",
            "execution_timing": ("first_real_1m_open_at_or_after_signal_eligibility"),
            "execution_model": (
                "first_eligible_real_minute_open_after_actual_observation"
            ),
            "fill_model": "deterministic_full_fill_at_adverse_open_scenario",
            "spread_model": "fixed_half_quoted_spread_per_changed_side",
            "slippage_model": "fixed_adverse_bps_per_changed_side",
            "fee_model": "fixed_bps_per_changed_notional",
            "partial_fills": False,
            "portfolio_aggregation": False,
            "experiment_role": "independent_shadow_experiment",
            "meta_shadow": self.meta_shadow_contract(
                artifact_identity=resolved_artifact_identity
            ),
            "limitations": {
                "historical_spread_series": False,
                "market_impact": False,
                "margin_and_liquidation": False,
                "funding_and_borrow": False,
                "futures_multiplier_and_roll": False,
                "shared_portfolio_capital": False,
            },
        }

    def cohort_manifest(
        self,
        *,
        code_digest: str,
        artifact_identity: Mapping[str, Any],
    ) -> dict[str, Any]:
        return {
            "service_version": FORWARD_PAPER_SERVICE_VERSION,
            "assets": list(self.assets),
            "timeframes": list(self.timeframes),
            "strategy": self.strategy.as_dict(),
            "strategy_digest": self.strategy.digest(),
            "costs": self.costs.as_dict(),
            "cost_digest": self.costs.digest(),
            "engine_contract": self.engine_contract(
                artifact_identity=artifact_identity
            ),
            "research_status": self.research_status,
            "source_contract": {
                "bar_timeframe": "1m",
                "source_vintage": "append_only_first_seen",
                "crypto_provider": "bybit",
                "multiasset_fallback": "yfinance_delayed",
                "actual_observation_time_controls_eligibility": True,
            },
            "real_order_routing": False,
            "normalized_economic_proxy": True,
            "profitability_guaranteed": False,
            "code_digest": code_digest,
        }


class ForwardPaperCoordinator:
    """Own one durable paper cohort across orderly process restarts."""

    def __init__(
        self,
        config: ForwardPaperConfig | None = None,
        *,
        source_router: FinalizedMinuteSourceRouter | None = None,
        bootstrap_loader: BootstrapLoader | None = None,
        anchor_loader: AnchorLoader | None = None,
        started_at: datetime | None = None,
    ) -> None:
        self.config = config or ForwardPaperConfig()
        self.started_at = as_utc(started_at or utc_now())
        self.config.state_dir.mkdir(parents=True, exist_ok=True)
        self.database_path = self.config.state_dir / DATABASE_FILENAME
        self.store = EventStore(self.database_path)
        self.source_router = source_router or FinalizedMinuteSourceRouter(
            bybit=BybitFinalizedMinuteSource(
                max_tail_rows=self.config.max_source_tail_rows
            ),
            yahoo=YahooFinalizedMinuteSource(
                max_tail_rows=self.config.max_source_tail_rows
            ),
        )
        self.bootstrap_loader = bootstrap_loader or load_canonical_target_bootstrap
        self.anchor_loader = anchor_loader or latest_canonical_real_minute
        self.meta_artifact_load = _load_meta_artifact(self.config)
        self.meta_artifact_identity = _artifact_identity(self.meta_artifact_load)
        self.code_digest = _service_code_digest()
        self.manifest = self.config.cohort_manifest(
            code_digest=self.code_digest,
            artifact_identity=self.meta_artifact_identity,
        )
        self.manifest_hash = _sha256_json(self.manifest)
        self.streams: dict[str, ForwardPaperStream] = {}
        self.activities: dict[str, dict[str, Any]] = {}
        self.source_states: dict[str, dict[str, Any]] = {}
        self.feeds: dict[str, dict[str, Any]] = {}
        self.activated_assets: set[str] = set()
        self.last_poll_started_at: datetime | None = None
        self.last_poll_completed_at: datetime | None = None
        self.last_poll_duration_seconds: float | None = None
        self.last_verified_at: datetime | None = None
        self.closed = False

        latest_state = self.store.latest_service_state(SERVICE_ID)
        if (
            latest_state is not None
            and isinstance(latest_state.payload, dict)
            and latest_state.payload.get("manifest_hash") == self.manifest_hash
        ):
            self.run_id = latest_state.run_id
            self._restore(latest_state.payload)
            self._append_control_event("service_restarted", snapshot_all=False)
        else:
            self.run_id = _sha256_text(
                f"{self.manifest_hash}|{iso_utc(self.started_at)}"
            )
            self.store.create_run(
                RunInput(
                    run_id=self.run_id,
                    created_at=self.started_at,
                    metadata=self.manifest,
                )
            )
            self._initialize_new_cohort()
            self._append_control_event("service_started", snapshot_all=True)
            self.store.verify_chain(self.run_id)
            self.last_verified_at = self.started_at
        self._publish_status(status="running")

    def __enter__(self) -> ForwardPaperCoordinator:
        return self

    def __exit__(self, *_exc: Any) -> None:
        self.close()

    def poll_once(self, *, now: datetime | None = None) -> dict[str, Any]:
        """Fetch and atomically journal one bounded provider pass."""

        self._require_open()
        explicit_clock = None if now is None else as_utc(now)
        self.last_poll_started_at = explicit_clock or utc_now()
        monotonic_start = time.monotonic()
        for asset in self.config.assets:
            if not self._asset_poll_due(asset, self.last_poll_started_at):
                continue
            source_state = self.source_states[asset]
            after_timestamp = parse_utc(source_state.get("last_timestamp"))
            try:
                batch = self.source_router.fetch(
                    asset,
                    after_timestamp=after_timestamp,
                    now=explicit_clock,
                )
            except Exception as exc:
                self._record_fetch_failure(
                    asset, exc, observed_at=explicit_clock or utc_now()
                )
                continue
            self._process_batch(batch)

        self.last_poll_completed_at = explicit_clock or utc_now()
        self.last_poll_duration_seconds = time.monotonic() - monotonic_start
        payload = self._publish_status(status="running")
        return payload

    def _asset_poll_due(self, asset: str, poll_clock: datetime) -> bool:
        """Respect a delayed provider's native cadence while heartbeating each minute."""

        feed = self.feeds[asset]
        if feed.get("quality") != "delayed" or feed.get("status") == "fetch_error":
            return True
        last_attempt = parse_utc(feed.get("last_attempt_at"))
        minimum_interval = float(feed.get("expected_delay_seconds") or 600)
        if (
            last_attempt is None
            or (poll_clock - last_attempt).total_seconds() >= minimum_interval
        ):
            return True
        next_attempt = last_attempt + timedelta(seconds=minimum_interval)
        feed["status"] = "waiting_delayed_provider_interval"
        feed["next_attempt_at"] = iso_utc(next_attempt)
        return False

    def run_forever(self, stop_event: threading.Event | None = None) -> None:
        """Poll until an external stop event is set."""

        stop = stop_event or threading.Event()
        while not stop.is_set():
            self.poll_once()
            if stop.is_set():
                break
            delay = self._next_poll_delay()
            stop.wait(delay)

    def close(self) -> None:
        if self.closed:
            return
        try:
            self._append_control_event("service_stopped", snapshot_all=True)
            self._publish_status(status="stopped")
        finally:
            self.closed = True
            self.store.close()

    def _initialize_new_cohort(self) -> None:
        for asset in self.config.assets:
            anchor = self.anchor_loader(asset, self.started_at)
            self.source_states[asset] = {
                "last_timestamp": iso_utc(anchor),
                "recent_fingerprints": {},
                "seen_revision_ids": [],
                "seen_late_ids": [],
            }
            self.feeds[asset] = {
                "status": "not_polled",
                "quality": "live" if asset in BYBIT_ASSETS else "delayed",
                "provider": "bybit" if asset in BYBIT_ASSETS else "yfinance",
                "expected_delay_seconds": 5 if asset in BYBIT_ASSETS else 600,
                "last_attempt_at": None,
                "last_success_at": None,
                "last_source_timestamp": iso_utc(anchor),
                "last_observed_at": None,
                "next_attempt_at": None,
                "measured_lag_seconds": None,
                "consecutive_failures": 0,
                "error": None,
                "continuity_status": "not_observed",
                "source_gap_count": 0,
                "continuous_gap_count": 0,
                "session_gap_count": 0,
                "last_gap_seconds": None,
                "last_gap_at": None,
            }
            for timeframe in self.config.timeframes:
                stream = ForwardPaperStream(
                    asset=asset,
                    timeframe=timeframe,
                    strategy=self.config.strategy,
                    costs=self.config.costs,
                    meta_shadow_protection=(
                        self.config.meta_shadow_protection
                        if self.config.meta_shadow_enabled
                        else None
                    ),
                    meta_artifact=self.meta_artifact_load.artifact,
                    meta_artifact_reason=self.meta_artifact_load.reason,
                )
                rows = self.bootstrap_loader(asset, timeframe, self.started_at)
                stream.bootstrap_target_bars(rows)
                self.streams[_stream_key(asset, timeframe)] = stream
                self.activities[_stream_key(asset, timeframe)] = {
                    "last_signal": None,
                    "last_order": None,
                    "last_fill": None,
                    "last_meta_shadow_prediction": None,
                    "last_meta_shadow_label": None,
                    "last_meta_shadow_failure": None,
                }

    def _restore(self, state: Mapping[str, Any]) -> None:
        run = self.store.get_run(self.run_id)
        if run is None or not isinstance(run.metadata, dict):
            raise RuntimeError("Forward paper checkpoint references an absent run")
        if _sha256_json(run.metadata) != self.manifest_hash:
            raise RuntimeError("Forward paper run manifest does not match checkpoint")
        self.store.verify_chain(self.run_id)
        self.last_verified_at = self.started_at
        raw_sources = state.get("source_states")
        raw_feeds = state.get("feeds")
        if not isinstance(raw_sources, dict) or not isinstance(raw_feeds, dict):
            raise RuntimeError("Forward paper service checkpoint is incomplete")
        self.source_states = {
            asset: _restore_source_state(raw_sources.get(asset))
            for asset in self.config.assets
        }
        self.feeds = {
            asset: _restore_feed_state(raw_feeds.get(asset), asset=asset)
            for asset in self.config.assets
        }
        raw_activities = state.get("activities", {})
        if not isinstance(raw_activities, dict):
            raise RuntimeError("Forward paper activity checkpoint is invalid")
        activated = state.get("activated_assets", [])
        if not isinstance(activated, list):
            raise RuntimeError("Forward paper activated asset checkpoint is invalid")
        self.activated_assets = {
            normalize_asset(asset)
            for asset in activated
            if normalize_asset(asset) in self.config.assets
        }

        snapshot_sequences: dict[str, int] = {}
        for asset in self.config.assets:
            for timeframe in self.config.timeframes:
                key = _stream_key(asset, timeframe)
                storage_id = self._storage_stream_id(key)
                stored = self.store.latest_snapshot(storage_id)
                if stored is None or stored.run_id != self.run_id:
                    raise RuntimeError(
                        f"Forward paper stream snapshot is missing for {key}"
                    )
                if not isinstance(stored.payload, dict):
                    raise RuntimeError(f"Forward paper snapshot is invalid for {key}")
                stream = ForwardPaperStream.restore(
                    stored.payload,
                    meta_shadow_protection=(
                        self.config.meta_shadow_protection
                        if self.config.meta_shadow_enabled
                        else None
                    ),
                    meta_artifact=self.meta_artifact_load.artifact,
                    meta_artifact_reason=self.meta_artifact_load.reason,
                )
                if stream.asset != asset or stream.timeframe != timeframe:
                    raise RuntimeError(
                        f"Forward paper snapshot selection mismatch: {key}"
                    )
                self.streams[key] = stream
                activity = raw_activities.get(key, {})
                self.activities[key] = (
                    dict(activity) if isinstance(activity, dict) else {}
                )
                snapshot_sequences[key] = stored.after_sequence_no or 0
        self._replay_sources_after_snapshots(snapshot_sequences)

    def _replay_sources_after_snapshots(
        self, snapshot_sequences: Mapping[str, int]
    ) -> None:
        earliest = min(snapshot_sequences.values(), default=0)
        for event in self.store.events(self.run_id, after_sequence_no=earliest):
            if event.event_type != "source_bar_observed" or not isinstance(
                event.payload, dict
            ):
                continue
            asset = str(event.payload.get("asset", ""))
            if asset not in self.config.assets:
                continue
            row = _row_from_payload(event.payload.get("row"))
            mode = str(event.payload.get("processing_mode", "catchup"))
            if mode not in {"bootstrap", "catchup", "forward"}:
                raise RuntimeError("Journaled source event has invalid processing mode")
            for timeframe in self.config.timeframes:
                key = _stream_key(asset, timeframe)
                if event.sequence_no <= snapshot_sequences[key]:
                    continue
                replayed_events = self.streams[key].consume(
                    row,
                    observed_at=event.observed_at,
                    mode=mode,  # type: ignore[arg-type]
                )
                self._update_activity(key, replayed_events)

    def _process_batch(self, batch: FinalizedMinuteBatch) -> None:
        asset = normalize_asset(batch.asset)
        if asset not in self.config.assets:
            raise ValueError(f"Source returned unselected asset {asset}")
        feed = self.feeds[asset]
        feed.update(
            {
                "status": "ok" if batch.rows else "idle_no_new_finalized_bar",
                "quality": batch.quality,
                "provider": batch.provider,
                "expected_delay_seconds": batch.expected_delay_seconds,
                "last_attempt_at": iso_utc(batch.observed_at),
                "last_success_at": iso_utc(batch.observed_at),
                "last_observed_at": iso_utc(batch.observed_at),
                "next_attempt_at": None,
                "consecutive_failures": 0,
                "error": None,
            }
        )
        state = self.source_states[asset]
        events: list[EventInput] = []
        important_stream_event = False
        latest_event_id: str | None = None
        latest_new_timestamp: datetime | None = None

        for row in batch.rows:
            timestamp = as_utc(row["timestamp"])  # type: ignore[arg-type]
            fingerprint = stable_row_fingerprint(asset, row)
            action, incident_id = _classify_source_row(
                state,
                timestamp=timestamp,
                fingerprint=fingerprint,
            )
            if action == "duplicate":
                continue
            if action == "revision":
                event_id = _sha256_text(
                    f"revision|{asset}|{iso_utc(timestamp)}|{fingerprint}"
                )
                if incident_id in state["seen_revision_ids"]:
                    continue
                state["seen_revision_ids"] = _bounded_strings(
                    [*state["seen_revision_ids"], incident_id]
                )
                event = EventInput(
                    event_id=event_id,
                    stream_id=f"source:{asset}",
                    event_type="source_revision_observed",
                    occurred_at=batch.observed_at,
                    observed_at=batch.observed_at,
                    payload={
                        "asset": asset,
                        "source_bar_open": iso_utc(timestamp),
                        "revision_fingerprint": fingerprint,
                        "retained_fingerprint": state["recent_fingerprints"].get(
                            iso_utc(timestamp)
                        ),
                        "provider": batch.provider,
                        "quality": batch.quality,
                        "state_mutated": False,
                    },
                )
                events.append(event)
                latest_event_id = event.event_id
                continue
            if action == "late":
                event_id = _sha256_text(
                    f"late|{asset}|{iso_utc(timestamp)}|{fingerprint}"
                )
                if incident_id in state["seen_late_ids"]:
                    continue
                state["seen_late_ids"] = _bounded_strings(
                    [*state["seen_late_ids"], incident_id]
                )
                event = EventInput(
                    event_id=event_id,
                    stream_id=f"source:{asset}",
                    event_type="late_source_bar_observed",
                    occurred_at=batch.observed_at,
                    observed_at=batch.observed_at,
                    payload={
                        "asset": asset,
                        "source_bar_open": iso_utc(timestamp),
                        "fingerprint": fingerprint,
                        "provider": batch.provider,
                        "quality": batch.quality,
                        "state_mutated": False,
                    },
                )
                events.append(event)
                latest_event_id = event.event_id
                continue

            mode = (
                "catchup"
                if asset not in self.activated_assets
                or timestamp + timedelta(minutes=1) <= self.started_at
                else "forward"
            )
            prior_source_timestamp = parse_utc(state.get("last_timestamp"))
            gap_seconds = (
                None
                if prior_source_timestamp is None
                else (timestamp - prior_source_timestamp).total_seconds()
            )
            scheduled_session_gap = bool(
                asset not in BYBIT_ASSETS
                and gap_seconds is not None
                and gap_seconds > 60.0
            )
            if gap_seconds is not None and gap_seconds > 60.0:
                feed["source_gap_count"] = int(feed.get("source_gap_count", 0)) + 1
                feed["last_gap_seconds"] = gap_seconds
                feed["last_gap_at"] = iso_utc(batch.observed_at)
                if scheduled_session_gap:
                    feed["session_gap_count"] = (
                        int(feed.get("session_gap_count", 0)) + 1
                    )
                    feed["continuity_status"] = "session_gap_observed_unverified"
                else:
                    feed["continuous_gap_count"] = (
                        int(feed.get("continuous_gap_count", 0)) + 1
                    )
                    feed["continuity_status"] = "continuous_source_gap_detected"
                    feed["status"] = "degraded_source_gap"
                gap_event_id = _sha256_text(
                    f"source-gap|{asset}|{iso_utc(prior_source_timestamp)}|"
                    f"{iso_utc(timestamp)}"
                )
                gap_event = EventInput(
                    event_id=gap_event_id,
                    stream_id=f"source:{asset}",
                    event_type="source_gap_observed",
                    occurred_at=batch.observed_at,
                    observed_at=batch.observed_at,
                    payload={
                        "asset": asset,
                        "provider": batch.provider,
                        "quality": batch.quality,
                        "prior_source_bar_open": iso_utc(prior_source_timestamp),
                        "source_bar_open": iso_utc(timestamp),
                        "gap_seconds": gap_seconds,
                        "missing_minute_count": max(0, int(gap_seconds // 60) - 1),
                        "scheduled_session_gap": scheduled_session_gap,
                        "classification": (
                            "session_gap_observed_unverified"
                            if scheduled_session_gap
                            else "continuous_source_gap"
                        ),
                    },
                )
                events.append(gap_event)
                latest_event_id = gap_event_id
            elif gap_seconds == 60.0:
                feed["continuity_status"] = "continuous"
            stream_row = dict(row)
            if scheduled_session_gap:
                # This flag is causal: the service learns that a session gap
                # ended only when the first later real bar is actually seen.
                stream_row["is_session_open_bar"] = True
            source_event_id = _sha256_text(
                f"source|{asset}|{iso_utc(timestamp)}|{fingerprint}"
            )
            source_event = EventInput(
                event_id=source_event_id,
                stream_id=f"source:{asset}",
                event_type="source_bar_observed",
                occurred_at=timestamp + timedelta(minutes=1),
                observed_at=batch.observed_at,
                payload={
                    "asset": asset,
                    "provider": batch.provider,
                    "quality": batch.quality,
                    "expected_delay_seconds": batch.expected_delay_seconds,
                    "fingerprint": fingerprint,
                    "processing_mode": mode,
                    "gap_seconds": gap_seconds,
                    "scheduled_session_gap": scheduled_session_gap,
                    "row": _row_payload(stream_row),
                },
            )
            events.append(source_event)
            latest_event_id = source_event_id
            latest_new_timestamp = timestamp

            for timeframe in self.config.timeframes:
                key = _stream_key(asset, timeframe)
                stream_events = self.streams[key].consume(
                    stream_row, observed_at=batch.observed_at, mode=mode
                )
                self._update_activity(key, stream_events)
                has_fill = any(
                    item.get("event_type") == "paper_fill" for item in stream_events
                )
                for item in stream_events:
                    event_type = str(item["event_type"])
                    if event_type == "paper_mark" and not (
                        timestamp.minute == 0 or has_fill
                    ):
                        continue
                    event = _stream_event_input(
                        item, storage_stream_id=self._storage_stream_id(key)
                    )
                    events.append(event)
                    latest_event_id = event.event_id
                    important_stream_event = important_stream_event or event_type in {
                        "paper_fill",
                        "paper_stream_incident",
                        "target_bar_rejected_incomplete",
                        "meta_shadow_prediction",
                        "meta_shadow_label",
                        "meta_shadow_processing_failed",
                    }
            _advance_source_state(state, timestamp=timestamp, fingerprint=fingerprint)

        activated_now = asset not in self.activated_assets
        if activated_now:
            self.activated_assets.add(asset)
            activation_id = _sha256_text(
                f"activate|{self.run_id}|{asset}|{iso_utc(batch.observed_at)}"
            )
            activation_event = EventInput(
                event_id=activation_id,
                stream_id="service",
                event_type="asset_forward_activated",
                occurred_at=batch.observed_at,
                observed_at=batch.observed_at,
                payload={
                    "asset": asset,
                    "activation_observed_at": iso_utc(batch.observed_at),
                    "backlog_signals_suppressed": True,
                    "next_signals_use_actual_observation_time": True,
                },
            )
            events.append(activation_event)
            latest_event_id = activation_id

        last_timestamp = parse_utc(state.get("last_timestamp"))
        if last_timestamp is not None:
            feed["last_source_timestamp"] = iso_utc(last_timestamp)
            feed["measured_lag_seconds"] = max(
                0.0,
                (
                    batch.observed_at - (last_timestamp + timedelta(minutes=1))
                ).total_seconds(),
            )

        should_snapshot = (
            activated_now
            or important_stream_event
            or (latest_new_timestamp is not None and latest_new_timestamp.minute == 0)
        )
        if not events:
            return
        assert latest_event_id is not None
        captured_at = batch.observed_at
        snapshots = (
            self._snapshot_inputs(
                keys=[_stream_key(asset, tf) for tf in self.config.timeframes],
                captured_at=captured_at,
                after_event_id=latest_event_id,
            )
            if should_snapshot
            else []
        )
        checkpoint = self._service_state_input(
            recorded_at=captured_at,
            after_event_id=latest_event_id,
        )
        self.store.append_batch(
            self.run_id,
            events,
            snapshots=snapshots,
            service_states=[checkpoint],
        )

    def _record_fetch_failure(
        self, asset: str, error: Exception, *, observed_at: datetime
    ) -> None:
        feed = self.feeds[asset]
        feed.update(
            {
                "status": "fetch_error",
                "last_attempt_at": iso_utc(observed_at),
                "next_attempt_at": None,
                "consecutive_failures": int(feed.get("consecutive_failures", 0)) + 1,
                "error": f"{error.__class__.__name__}: {error}",
                "last_error_at": iso_utc(observed_at),
                "continuity_status": "fetch_error",
            }
        )
        event_id = _sha256_text(
            f"fetch-error|{self.run_id}|{asset}|{iso_utc(observed_at)}|{feed['error']}"
        )
        event = EventInput(
            event_id=event_id,
            stream_id=f"source:{asset}",
            event_type="source_fetch_failed",
            occurred_at=observed_at,
            observed_at=observed_at,
            payload={
                "asset": asset,
                "provider": feed.get("provider"),
                "quality": feed.get("quality"),
                "consecutive_failures": feed["consecutive_failures"],
                "error": feed["error"],
            },
        )
        checkpoint = self._service_state_input(
            recorded_at=observed_at,
            after_event_id=event_id,
        )
        self.store.append_batch(
            self.run_id,
            [event],
            service_states=[checkpoint],
        )

    def _append_control_event(self, event_type: str, *, snapshot_all: bool) -> None:
        observed_at = utc_now()
        event_id = _sha256_text(
            f"{event_type}|{self.run_id}|{iso_utc(observed_at)}|{os.getpid()}"
        )
        event = EventInput(
            event_id=event_id,
            stream_id="service",
            event_type=event_type,
            occurred_at=observed_at,
            observed_at=observed_at,
            payload={
                "service_version": FORWARD_PAPER_SERVICE_VERSION,
                "manifest_hash": self.manifest_hash,
                "pid": os.getpid(),
                "real_order_routing": False,
            },
        )
        snapshots = (
            self._snapshot_inputs(
                keys=list(self.streams),
                captured_at=observed_at,
                after_event_id=event_id,
            )
            if snapshot_all
            else []
        )
        checkpoint = self._service_state_input(
            recorded_at=observed_at,
            after_event_id=event_id,
        )
        self.store.append_batch(
            self.run_id,
            [event],
            snapshots=snapshots,
            service_states=[checkpoint],
        )

    def _snapshot_inputs(
        self,
        *,
        keys: Iterable[str],
        captured_at: datetime,
        after_event_id: str,
    ) -> list[SnapshotInput]:
        snapshots: list[SnapshotInput] = []
        for key in keys:
            payload = self.streams[key].snapshot()
            snapshot_id = _sha256_text(
                f"snapshot|{self.run_id}|{key}|{after_event_id}|"
                f"{payload.get('checksum')}"
            )
            snapshots.append(
                SnapshotInput(
                    snapshot_id=snapshot_id,
                    run_id=self.run_id,
                    stream_id=self._storage_stream_id(key),
                    captured_at=captured_at,
                    after_event_id=after_event_id,
                    payload=payload,
                )
            )
        return snapshots

    def _service_state_input(
        self, *, recorded_at: datetime, after_event_id: str
    ) -> ServiceStateInput:
        payload = self._checkpoint_payload()
        checkpoint_id = _sha256_text(
            f"checkpoint|{self.run_id}|{after_event_id}|{iso_utc(recorded_at)}|"
            f"{_sha256_json(payload)}"
        )
        return ServiceStateInput(
            checkpoint_id=checkpoint_id,
            run_id=self.run_id,
            service_id=SERVICE_ID,
            recorded_at=recorded_at,
            after_event_id=after_event_id,
            payload=payload,
        )

    def _checkpoint_payload(self) -> dict[str, Any]:
        return {
            "service_version": FORWARD_PAPER_SERVICE_VERSION,
            "manifest_hash": self.manifest_hash,
            "activated_assets": sorted(self.activated_assets),
            "source_states": self.source_states,
            "feeds": self.feeds,
            "activities": self.activities,
        }

    def _storage_stream_id(self, key: str) -> str:
        return f"{self.run_id}:{key}"

    def _publish_status(self, *, status: str) -> dict[str, Any]:
        streams: dict[str, Any] = {}
        for key, stream in self.streams.items():
            ledger = stream.ledger
            meta_shadow_status: dict[str, Any]
            if stream.meta_shadow_book is None:
                meta_shadow_status = {
                    "enabled": False,
                    "mode": "disabled",
                    "failure_count": stream.meta_shadow_failure_count,
                    "last_failure": stream.last_meta_shadow_failure,
                    "affects_orders": False,
                    "affects_positions": False,
                }
            else:
                shadow_view = stream.meta_shadow_book.view(resolved_limit=0)
                meta_shadow_status = {
                    "enabled": True,
                    "mode": "shadow_only_no_order_effect",
                    "artifact_identity": stream._meta_artifact_identity(),
                    "policy_digest": stream.meta_shadow_policy_digest,
                    "protection_config_digest": (
                        None
                        if stream.meta_shadow_protection is None
                        else stream.meta_shadow_protection.digest()
                    ),
                    "total_scheduled": shadow_view["total_scheduled"],
                    "total_filled": shadow_view["total_filled"],
                    "total_resolved": shadow_view["total_resolved"],
                    "outcome_counts": shadow_view["outcome_counts"],
                    "pending_count": shadow_view["pending_count"],
                    "active_count": shadow_view["active_count"],
                    "resolved_retained_count": shadow_view["resolved_retained_count"],
                    "failure_count": stream.meta_shadow_failure_count,
                    "last_failure": stream.last_meta_shadow_failure,
                    "affects_orders": False,
                    "affects_positions": False,
                    "real_order_routing": False,
                }
            streams[key] = {
                "stream_id": stream.stream_id,
                "asset": stream.asset,
                "timeframe": stream.timeframe,
                "experiment_role": "independent_shadow_experiment",
                "portfolio_aggregation": False,
                "strategy": stream.strategy.as_dict(),
                "strategy_digest": stream.strategy.digest(),
                "costs": stream.costs.as_dict(),
                "cost_digest": stream.costs.digest(),
                "execution_model_version": EXECUTION_MODEL_VERSION,
                "evidence_status": (
                    "collecting_unaccepted_baseline"
                    if self.config.research_status
                    == "historical_optimizer_rejected_observe_only"
                    else "collecting"
                ),
                "last_source_timestamp": (
                    None if stream.cursor is None else iso_utc(stream.cursor.timestamp)
                ),
                "last_observed_at": (
                    None
                    if stream.cursor is None
                    else iso_utc(stream.cursor.observed_at)
                ),
                "pending_order": stream.pending_order,
                "meta_shadow": meta_shadow_status,
                **self.activities.get(key, {}),
                "risk": {
                    "real_order_routing": False,
                    "normalized_position_min": -stream.strategy.maximum_exposure,
                    "normalized_position_max": stream.strategy.maximum_exposure,
                    "shared_portfolio_capital": False,
                    "partial_fills": False,
                    "instrument_costs_complete": False,
                },
                "continuity": {
                    "source_gap_count": stream.source_gap_count,
                    "rejected_incomplete_target_count": (
                        stream.rejected_incomplete_target_count
                    ),
                    "accepted_partial_session_target_count": (
                        stream.accepted_partial_session_target_count
                    ),
                    "suppressed_catchup_minutes": ledger.suppressed_minutes,
                    "forward_minutes_marked": ledger.forward_minutes_marked,
                },
                "metrics": ledger.metrics(),
            }
        payload = {
            "schema_version": 1,
            "status": status,
            "service_version": FORWARD_PAPER_SERVICE_VERSION,
            "pid": os.getpid(),
            "run_id": self.run_id,
            "manifest_hash": self.manifest_hash,
            "engine_contract": self.config.engine_contract(
                artifact_identity=self.meta_artifact_identity
            ),
            "started_at": iso_utc(self.started_at),
            "heartbeat_at": iso_utc(utc_now()),
            "last_poll_started_at": iso_utc(self.last_poll_started_at),
            "last_poll_completed_at": iso_utc(self.last_poll_completed_at),
            "last_poll_duration_seconds": self.last_poll_duration_seconds,
            "poll_interval_seconds": self.config.poll_interval_seconds,
            "research_status": self.config.research_status,
            "journal_integrity": (
                f"verified_at_{iso_utc(self.last_verified_at)}"
                if self.last_verified_at is not None
                else "new_chain"
            ),
            "source_vintage": "append_only_first_seen",
            "real_order_routing": False,
            "normalized_economic_proxy": True,
            "instrument_costs_complete": False,
            "profitability_guaranteed": False,
            "live_asset_count": sum(
                feed.get("quality") == "live" for feed in self.feeds.values()
            ),
            "delayed_asset_count": sum(
                feed.get("quality") == "delayed" for feed in self.feeds.values()
            ),
            "healthy_live_asset_count": sum(
                feed.get("quality") == "live"
                and feed.get("status") not in {"fetch_error", "degraded_source_gap"}
                for feed in self.feeds.values()
            ),
            "failed_asset_count": sum(
                feed.get("status") == "fetch_error" for feed in self.feeds.values()
            ),
            "degraded_asset_count": sum(
                feed.get("status") == "degraded_source_gap"
                for feed in self.feeds.values()
            ),
            "feeds": self.feeds,
            "streams": streams,
        }
        atomic_write_json(status_path(self.config.state_dir), payload)
        return payload

    def _update_activity(self, key: str, events: Iterable[Mapping[str, Any]]) -> None:
        activity = self.activities.setdefault(
            key,
            {
                "last_signal": None,
                "last_order": None,
                "last_fill": None,
                "last_meta_shadow_prediction": None,
                "last_meta_shadow_label": None,
                "last_meta_shadow_failure": None,
            },
        )
        field_by_type = {
            "signal_issued": "last_signal",
            "paper_order_created": "last_order",
            "paper_fill": "last_fill",
            "meta_shadow_prediction": "last_meta_shadow_prediction",
            "meta_shadow_label": "last_meta_shadow_label",
            "meta_shadow_processing_failed": "last_meta_shadow_failure",
        }
        for event in events:
            event_type = str(event.get("event_type"))
            field = field_by_type.get(event_type)
            if field is not None:
                activity[field] = dict(event)
            if event_type == "paper_fill":
                prior_order = activity.get("last_order")
                if isinstance(prior_order, dict) and prior_order.get(
                    "order_id"
                ) == event.get("order_id"):
                    activity["last_order"] = {
                        **prior_order,
                        "order_status": "filled",
                        "fill_id": event.get("fill_id"),
                        "filled_at": event.get("fill_minute_open"),
                    }
            elif event_type == "paper_order_suppressed_catchup":
                prior_order = activity.get("last_order")
                if isinstance(prior_order, dict) and prior_order.get(
                    "order_id"
                ) == event.get("order_id"):
                    activity["last_order"] = {
                        **prior_order,
                        "order_status": "canceled",
                        "canceled_at": event.get("observed_at"),
                        "cancellation_reason": event.get("reason"),
                    }

    def _next_poll_delay(self) -> float:
        if math.isclose(self.config.poll_interval_seconds, 60.0):
            current = time.time()
            next_boundary = (int(current) // 60 + 1) * 60 + 5
            return max(0.25, next_boundary - current)
        return self.config.poll_interval_seconds

    def _require_open(self) -> None:
        if self.closed:
            raise RuntimeError("Forward paper coordinator is closed")


def load_canonical_target_bootstrap(
    asset: str,
    timeframe: str,
    now: datetime,
    *,
    max_bars: int = BOOTSTRAP_TARGET_BARS,
) -> list[dict[str, Any]]:
    """Load only safely closed target bars for indicator seeding."""

    resolution = resolve_ohlcv_files(
        asset=asset,
        timeframe=timeframe,
        source="canonical",
    )
    lazy = pl.scan_parquet([str(path) for path in resolution.files])
    schema = set(lazy.collect_schema().names())
    required = {"timestamp", "open", "high", "low", "close", "volume"}
    missing = required - schema
    if missing:
        raise ValueError(
            "Canonical bootstrap source is missing: " + ", ".join(sorted(missing))
        )
    expressions = [
        pl.col("timestamp"),
        pl.col("open").cast(pl.Float64),
        pl.col("high").cast(pl.Float64),
        pl.col("low").cast(pl.Float64),
        pl.col("close").cast(pl.Float64),
        pl.col("volume").cast(pl.Float64),
    ]
    for optional in ("is_session_open_bar", "is_synthetic_no_trade"):
        if optional in schema:
            expressions.append(pl.col(optional))
    cutoff = as_utc(now) - timedelta(seconds=5)
    frame = (
        lazy.select(expressions)
        # Canonical files are materialized in ascending timestamp order.  Tail
        # before the uniqueness/sort pass so service startup does not rescan
        # multi-million-row 1m histories for every stream.
        .tail(max_bars * 4)
        .filter(
            pl.col("timestamp") + pl.duration(seconds=timeframe_seconds(timeframe))
            <= pl.lit(cutoff)
        )
        .unique(subset=["timestamp"], keep="last")
        .sort("timestamp")
    )
    if "is_synthetic_no_trade" in schema:
        frame = frame.filter(~pl.col("is_synthetic_no_trade").fill_null(False))
    return frame.tail(max_bars).collect().to_dicts()


def latest_canonical_real_minute(asset: str, now: datetime) -> datetime | None:
    """Return the latest safely closed real canonical minute used as catch-up anchor."""

    resolution = resolve_ohlcv_files(
        asset=asset,
        timeframe="1m",
        source="canonical",
    )
    lazy = pl.scan_parquet([str(path) for path in resolution.files])
    schema = set(lazy.collect_schema().names())
    columns = [pl.col("timestamp")]
    if "is_synthetic_no_trade" in schema:
        columns.append(pl.col("is_synthetic_no_trade"))
    cutoff = as_utc(now) - timedelta(seconds=5)
    frame = (
        lazy.select(columns)
        .tail(10_000)
        .filter(pl.col("timestamp") + pl.duration(minutes=1) <= pl.lit(cutoff))
    )
    if "is_synthetic_no_trade" in schema:
        frame = frame.filter(~pl.col("is_synthetic_no_trade").fill_null(False))
    result = frame.select(pl.col("timestamp").max()).collect().item()
    return None if result is None else as_utc(result)


def _stream_key(asset: str, timeframe: str) -> str:
    return f"{asset}|{timeframe}"


def _stream_event_input(
    event: Mapping[str, Any], *, storage_stream_id: str
) -> EventInput:
    payload = {
        key: value
        for key, value in event.items()
        if key
        not in {
            "event_id",
            "event_type",
            "stream_id",
            "occurred_at",
            "observed_at",
        }
    }
    return EventInput(
        event_id=str(event["event_id"]),
        stream_id=storage_stream_id,
        event_type=str(event["event_type"]),
        occurred_at=str(event["occurred_at"]),
        observed_at=str(event["observed_at"]),
        payload=payload,
    )


def _classify_source_row(
    state: Mapping[str, Any], *, timestamp: datetime, fingerprint: str
) -> tuple[str, str]:
    timestamp_text = iso_utc(timestamp)
    recent = state.get("recent_fingerprints", {})
    retained = recent.get(timestamp_text) if isinstance(recent, dict) else None
    incident_id = _sha256_text(f"{timestamp_text}|{fingerprint}")
    if retained is not None:
        return ("duplicate" if retained == fingerprint else "revision", incident_id)
    last = parse_utc(state.get("last_timestamp"))
    if last is not None and timestamp <= last:
        return "late", incident_id
    return "new", incident_id


def _advance_source_state(
    state: dict[str, Any], *, timestamp: datetime, fingerprint: str
) -> None:
    recent = dict(state.get("recent_fingerprints", {}))
    recent[iso_utc(timestamp)] = fingerprint
    ordered = sorted(recent.items(), key=lambda item: item[0])[
        -RECENT_FINGERPRINT_LIMIT:
    ]
    state["recent_fingerprints"] = dict(ordered)
    state["last_timestamp"] = iso_utc(timestamp)


def _bounded_strings(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(values))[-RECENT_FINGERPRINT_LIMIT:]


def _restore_source_state(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise RuntimeError("Forward paper source checkpoint is invalid")
    last = parse_utc(raw.get("last_timestamp"))
    recent = raw.get("recent_fingerprints", {})
    revisions = raw.get("seen_revision_ids", [])
    late = raw.get("seen_late_ids", [])
    if (
        not isinstance(recent, dict)
        or not isinstance(revisions, list)
        or not isinstance(late, list)
    ):
        raise RuntimeError("Forward paper source checkpoint is invalid")
    return {
        "last_timestamp": iso_utc(last),
        "recent_fingerprints": {str(key): str(value) for key, value in recent.items()},
        "seen_revision_ids": [str(value) for value in revisions],
        "seen_late_ids": [str(value) for value in late],
    }


def _restore_feed_state(raw: Any, *, asset: str) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {
            "status": "restored_without_feed_state",
            "quality": "live" if asset in BYBIT_ASSETS else "delayed",
            "provider": "bybit" if asset in BYBIT_ASSETS else "yfinance",
            "expected_delay_seconds": 5 if asset in BYBIT_ASSETS else 600,
            "consecutive_failures": 0,
        }
    return dict(raw)


def _row_payload(row: Mapping[str, Any]) -> dict[str, Any]:
    payload = {
        "timestamp": iso_utc(as_utc(row["timestamp"])),  # type: ignore[arg-type]
        "open": float(row["open"]),
        "high": float(row["high"]),
        "low": float(row["low"]),
        "close": float(row["close"]),
        "volume": float(row.get("volume", 0.0)),
        "turnover": (None if row.get("turnover") is None else float(row["turnover"])),
        "interval": "1m",
    }
    if row.get("is_session_open_bar") is not None:
        payload["is_session_open_bar"] = bool(row.get("is_session_open_bar"))
    return payload


def _row_from_payload(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise RuntimeError("Journaled source row is invalid")
    row = dict(raw)
    timestamp = parse_utc(row.get("timestamp"))
    if timestamp is None:
        raise RuntimeError("Journaled source row timestamp is invalid")
    row["timestamp"] = timestamp
    return row


def _load_meta_artifact(config: ForwardPaperConfig) -> ArtifactLoadResult:
    """Load only the server-configured artifact and never abort paper trading."""

    if not config.meta_shadow_enabled:
        return ArtifactLoadResult(
            available=False,
            artifact=None,
            reason="disabled",
        )
    assert config.meta_shadow_artifact_path is not None
    return load_artifact_safe(
        config.meta_shadow_artifact_path,
        expected_feature_names=META_FEATURE_NAMES,
    )


def _artifact_identity(result: ArtifactLoadResult) -> dict[str, Any]:
    artifact: LogisticCoefficientArtifact | None = result.artifact
    return {
        "available": bool(result.available and artifact is not None),
        "reason": result.reason,
        "model_version": None if artifact is None else artifact.model_version,
        "checksum": None if artifact is None else artifact.checksum,
    }


def _service_code_digest() -> str:
    root = Path(__file__).resolve().parents[1]
    paths = (
        root / "online_signals.py",
        root / "indicators.py",
        root / "minute_replay.py",
        root / "trade_ml" / "contracts.py",
        root / "trade_ml" / "features.py",
        root / "trade_ml" / "artifact.py",
        root / "trade_ml" / "inference.py",
        root / "trade_ml" / "labeling.py",
        root / "trade_ml" / "economics.py",
        root / "trade_ml" / "shadow.py",
        Path(__file__).resolve().parent / "stream.py",
        Path(__file__).resolve().parent / "sources.py",
        Path(__file__).resolve(),
    )
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _sha256_json(payload: Mapping[str, Any]) -> str:
    return _sha256_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    )


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


__all__ = [
    "BOOTSTRAP_TARGET_BARS",
    "DATABASE_FILENAME",
    "FORWARD_META_ARTIFACT_ENV",
    "FORWARD_PAPER_SERVICE_VERSION",
    "ForwardPaperConfig",
    "ForwardPaperCoordinator",
    "latest_canonical_real_minute",
    "load_canonical_target_bootstrap",
]
