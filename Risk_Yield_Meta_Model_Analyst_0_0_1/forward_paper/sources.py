"""Read-only, provider-graded sources of finalized one-minute OHLCV bars.

These adapters deliberately do not write provider or canonical parquet.  They
return a bounded overlap around the caller's high-water timestamp so a
forward-paper journal can identify both new bars and provider revisions by
fingerprint.

Yahoo Finance is a delayed, indicative front-futures fallback.  It is not
described or exposed as a live execution-quality source.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Literal, Protocol

import requests

from fetchingMultiAsset.asset_config import YFINANCE_FUTURES
from fetchingMultiAsset.fetch_yfinance import (
    fetch_yfinance_frame,
    yfinance_frame_to_ohlcv,
)

BYBIT_KLINE_URL = "https://api.bybit.com/v5/market/kline"
BYBIT_ASSETS = frozenset({"BTCUSDT", "ETHUSDT"})
YAHOO_ASSETS = frozenset(asset.symbol for asset in YFINANCE_FUTURES)
CANONICAL_ASSETS = frozenset(BYBIT_ASSETS | YAHOO_ASSETS)

MINUTE = timedelta(minutes=1)
MINUTE_MS = 60_000
BYBIT_FINALITY_LAG_SECONDS = 5
BYBIT_EXPECTED_DELAY_SECONDS = 5
YAHOO_EXPECTED_DELAY_SECONDS = 600
YAHOO_1M_RETENTION = timedelta(days=7)
DEFAULT_OVERLAP_BARS = 2
DEFAULT_MAX_TAIL_ROWS = 240
MAX_PROVIDER_TAIL_ROWS = 1_000
DEFAULT_BYBIT_TIMEOUT_SECONDS = 10.0
MAX_BYBIT_TIMEOUT_SECONDS = 20.0

SourceQuality = Literal["live", "delayed"]
MinuteRow = dict[str, object]


class FinalizedMinuteSourceError(RuntimeError):
    """Base error raised by a finalized-minute provider adapter."""


class UnsupportedSourceAsset(FinalizedMinuteSourceError, ValueError):
    """Raised when an adapter is asked for an asset it does not provide."""


class SourceFetchError(FinalizedMinuteSourceError):
    """Raised when a provider request fails before a response is validated."""


class SourceDataError(FinalizedMinuteSourceError, ValueError):
    """Raised when provider output violates the finalized OHLCV contract."""


@dataclass(frozen=True)
class FinalizedMinuteBatch:
    """One observed, provider-graded batch of real finalized minute rows."""

    asset: str
    provider: str
    quality: SourceQuality
    expected_delay_seconds: int
    observed_at: datetime
    rows: tuple[MinuteRow, ...]

    def __post_init__(self) -> None:
        normalized_asset = _normalized_asset(self.asset)
        if normalized_asset not in CANONICAL_ASSETS:
            raise UnsupportedSourceAsset(f"Unsupported canonical asset {self.asset!r}")
        if not self.provider.strip():
            raise ValueError("provider cannot be empty")
        if self.quality not in ("live", "delayed"):
            raise ValueError(f"Unsupported source quality {self.quality!r}")
        if self.expected_delay_seconds < 0:
            raise ValueError("expected_delay_seconds must be non-negative")
        observed_at = _require_utc(self.observed_at, name="observed_at")
        if tuple(sorted(row["timestamp"] for row in self.rows)) != tuple(
            row["timestamp"] for row in self.rows
        ):
            raise ValueError("batch rows must be sorted by timestamp")
        if len({row["timestamp"] for row in self.rows}) != len(self.rows):
            raise ValueError("batch rows must have unique timestamps")
        object.__setattr__(self, "asset", normalized_asset)
        object.__setattr__(self, "provider", self.provider.strip().lower())
        object.__setattr__(self, "observed_at", observed_at)


class FinalizedMinuteSource(Protocol):
    """Common polling contract used by the forward-paper coordinator."""

    def fetch(
        self,
        asset: str,
        after_timestamp: datetime | None = None,
        now: datetime | None = None,
    ) -> FinalizedMinuteBatch: ...


class BybitFinalizedMinuteSource:
    """Bounded public-REST source for finalized Bybit linear klines."""

    def __init__(
        self,
        *,
        http_get: Callable[..., Any] | None = None,
        timeout_seconds: float = DEFAULT_BYBIT_TIMEOUT_SECONDS,
        overlap_bars: int = DEFAULT_OVERLAP_BARS,
        max_tail_rows: int = DEFAULT_MAX_TAIL_ROWS,
    ) -> None:
        self._timeout_seconds = _validated_timeout(timeout_seconds)
        self._overlap_bars, self._max_tail_rows = _validated_bounds(
            overlap_bars=overlap_bars,
            max_tail_rows=max_tail_rows,
        )
        self._session: requests.Session | None = None
        if http_get is None:
            self._session = requests.Session()
            self._http_get = self._session.get
        else:
            self._http_get = http_get

    def fetch(
        self,
        asset: str,
        after_timestamp: datetime | None = None,
        now: datetime | None = None,
    ) -> FinalizedMinuteBatch:
        normalized_asset = _normalized_asset(asset)
        if normalized_asset not in BYBIT_ASSETS:
            raise UnsupportedSourceAsset(
                f"Bybit finalized-minute source does not provide {normalized_asset}"
            )
        request_clock = _resolved_now(now)
        after = _optional_utc(after_timestamp, name="after_timestamp")
        latest_start = _latest_finalized_start(
            request_clock,
            finality_lag_seconds=BYBIT_FINALITY_LAG_SECONDS,
        )
        start, request_end = _bounded_window(
            latest_start=latest_start,
            after_timestamp=after,
            overlap_bars=self._overlap_bars,
            max_tail_rows=self._max_tail_rows,
        )
        if start > latest_start:
            return _batch(
                asset=normalized_asset,
                provider="bybit",
                quality="live",
                expected_delay_seconds=BYBIT_EXPECTED_DELAY_SECONDS,
                observed_at=request_clock,
                rows=(),
            )

        params = {
            "category": "linear",
            "symbol": normalized_asset,
            "interval": "1",
            "start": _epoch_ms(start),
            "end": _epoch_ms(request_end),
            "limit": self._max_tail_rows,
        }
        try:
            response = self._http_get(
                BYBIT_KLINE_URL,
                params=params,
                timeout=self._timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            raise SourceFetchError(
                f"Bybit 1m request failed for {normalized_asset}: {exc}"
            ) from exc

        # In production, timestamp the observation after the response has
        # arrived.  Using request-start time could make a boundary-crossing
        # response appear actionable before it was actually known.  Tests may
        # pass an explicit deterministic clock, in which case it is preserved.
        observed_at = request_clock if now is not None else _resolved_now(None)
        raw_rows = _validated_bybit_payload(payload)
        parsed_rows = [
            _bybit_row(raw_row, query_start=start, query_end=request_end)
            for raw_row in raw_rows
        ]
        rows = _normalize_finalized_rows(
            (row for row in parsed_rows if row is not None),
            observed_at=observed_at,
            finality_lag_seconds=BYBIT_FINALITY_LAG_SECONDS,
            max_tail_rows=self._max_tail_rows,
        )
        return _batch(
            asset=normalized_asset,
            provider="bybit",
            quality="live",
            expected_delay_seconds=BYBIT_EXPECTED_DELAY_SECONDS,
            observed_at=observed_at,
            rows=rows,
        )


class YahooFinalizedMinuteSource:
    """Delayed Yahoo front-futures source for the six non-crypto assets."""

    def __init__(
        self,
        *,
        frame_fetcher: Callable[..., Any] = fetch_yfinance_frame,
        frame_normalizer: Callable[..., Any] = yfinance_frame_to_ohlcv,
        overlap_bars: int = DEFAULT_OVERLAP_BARS,
        max_tail_rows: int = DEFAULT_MAX_TAIL_ROWS,
    ) -> None:
        self._frame_fetcher = frame_fetcher
        self._frame_normalizer = frame_normalizer
        self._overlap_bars, self._max_tail_rows = _validated_bounds(
            overlap_bars=overlap_bars,
            max_tail_rows=max_tail_rows,
        )
        self._specs = {spec.symbol: spec for spec in YFINANCE_FUTURES}

    def fetch(
        self,
        asset: str,
        after_timestamp: datetime | None = None,
        now: datetime | None = None,
    ) -> FinalizedMinuteBatch:
        normalized_asset = _normalized_asset(asset)
        spec = self._specs.get(normalized_asset)
        if spec is None:
            raise UnsupportedSourceAsset(
                f"Yahoo delayed minute source does not provide {normalized_asset}"
            )
        request_clock = _resolved_now(now)
        after = _optional_utc(after_timestamp, name="after_timestamp")
        latest_start = _latest_finalized_start(
            request_clock,
            finality_lag_seconds=0,
        )
        # A row-count window is unsuitable across exchange weekends: 1,000
        # calendar minutes on Saturday no longer reaches Friday's last traded
        # bar.  Yahoo permits seven calendar days of 1m history, while the
        # normalized result remains capped to ``max_tail_rows``.
        retention_start = _floor_minute(request_clock) - YAHOO_1M_RETENTION + MINUTE
        start = max(
            retention_start,
            (
                latest_start - YAHOO_1M_RETENTION + MINUTE
                if after is None
                else _floor_minute(after) - MINUTE * (self._overlap_bars - 1)
            ),
        )
        if start > latest_start:
            return _batch(
                asset=normalized_asset,
                provider="yfinance",
                quality="delayed",
                expected_delay_seconds=YAHOO_EXPECTED_DELAY_SECONDS,
                observed_at=request_clock,
                rows=(),
            )

        try:
            raw_frame = self._frame_fetcher(
                spec.provider_symbol,
                interval="1m",
                start=start,
                end=latest_start,
            )
            normalized_frame = self._frame_normalizer(
                raw_frame,
                "1m",
                price_transform=spec.price_transform,
            )
            raw_rows = normalized_frame.iter_rows(named=True)
        except Exception as exc:
            raise SourceFetchError(
                f"Yahoo 1m request failed for {normalized_asset}: {exc}"
            ) from exc

        observed_at = request_clock if now is not None else _resolved_now(None)
        rows = _normalize_finalized_rows(
            raw_rows,
            observed_at=observed_at,
            finality_lag_seconds=0,
            max_tail_rows=self._max_tail_rows,
            keep="head" if after is not None else "tail",
        )
        return _batch(
            asset=normalized_asset,
            provider="yfinance",
            quality="delayed",
            expected_delay_seconds=YAHOO_EXPECTED_DELAY_SECONDS,
            observed_at=observed_at,
            rows=rows,
        )


class FinalizedMinuteSourceRouter:
    """Route all eight canonical assets to their provider-graded adapter."""

    def __init__(
        self,
        *,
        bybit: FinalizedMinuteSource | None = None,
        yahoo: FinalizedMinuteSource | None = None,
    ) -> None:
        self._bybit = bybit or BybitFinalizedMinuteSource()
        self._yahoo = yahoo or YahooFinalizedMinuteSource()

    def fetch(
        self,
        asset: str,
        after_timestamp: datetime | None = None,
        now: datetime | None = None,
    ) -> FinalizedMinuteBatch:
        normalized_asset = _normalized_asset(asset)
        if normalized_asset in BYBIT_ASSETS:
            return self._bybit.fetch(normalized_asset, after_timestamp, now)
        if normalized_asset in YAHOO_ASSETS:
            return self._yahoo.fetch(normalized_asset, after_timestamp, now)
        known = ", ".join(sorted(CANONICAL_ASSETS))
        raise UnsupportedSourceAsset(
            f"No finalized-minute source for {normalized_asset!r}; known: {known}"
        )


def stable_row_fingerprint(asset: str, row: Mapping[str, Any]) -> str:
    """Return a stable content digest for one canonical asset/minute row.

    Provider and observation time are intentionally excluded: identical OHLCV
    content observed twice has the same digest, while any price, volume, or
    turnover revision produces a new digest.
    """

    normalized_asset = _normalized_asset(asset)
    if normalized_asset not in CANONICAL_ASSETS:
        raise UnsupportedSourceAsset(f"Unsupported canonical asset {asset!r}")
    timestamp = _validated_timestamp(row.get("timestamp"))
    validated = _validated_ohlcv_row(row, timestamp=timestamp)
    payload = {
        "asset": normalized_asset,
        "timestamp": _iso_utc(timestamp),
        "open": _float_fingerprint(validated["open"]),
        "high": _float_fingerprint(validated["high"]),
        "low": _float_fingerprint(validated["low"]),
        "close": _float_fingerprint(validated["close"]),
        "volume": _float_fingerprint(validated["volume"]),
        "turnover": _float_fingerprint(validated["turnover"]),
        "interval": "1m",
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _batch(
    *,
    asset: str,
    provider: str,
    quality: SourceQuality,
    expected_delay_seconds: int,
    observed_at: datetime,
    rows: tuple[MinuteRow, ...],
) -> FinalizedMinuteBatch:
    return FinalizedMinuteBatch(
        asset=asset,
        provider=provider,
        quality=quality,
        expected_delay_seconds=expected_delay_seconds,
        observed_at=observed_at,
        rows=rows,
    )


def _validated_bybit_payload(payload: Any) -> list[Any]:
    if not isinstance(payload, Mapping):
        raise SourceDataError("Bybit response must be a JSON object")
    if payload.get("retCode") != 0:
        raise SourceDataError(
            f"Bybit response retCode={payload.get('retCode')!r}: "
            f"{payload.get('retMsg', 'unknown error')}"
        )
    result = payload.get("result")
    if not isinstance(result, Mapping):
        raise SourceDataError("Bybit response is missing result object")
    category = result.get("category")
    if category is not None and category != "linear":
        raise SourceDataError(f"Unexpected Bybit category {category!r}")
    rows = result.get("list")
    if not isinstance(rows, list):
        raise SourceDataError("Bybit response result.list must be a list")
    return rows


def _bybit_row(
    raw: Any,
    *,
    query_start: datetime,
    query_end: datetime,
) -> MinuteRow | None:
    if not isinstance(raw, (list, tuple)) or len(raw) < 6:
        raise SourceDataError("Each Bybit kline must contain at least six fields")
    try:
        timestamp_ms = int(raw[0])
    except (TypeError, ValueError) as exc:
        raise SourceDataError(f"Invalid Bybit kline timestamp {raw[0]!r}") from exc
    if timestamp_ms % MINUTE_MS != 0:
        raise SourceDataError(f"Bybit kline is not minute-aligned: {timestamp_ms}")
    try:
        timestamp = datetime.fromtimestamp(timestamp_ms / 1_000, tz=timezone.utc)
    except (OverflowError, OSError, ValueError) as exc:
        raise SourceDataError(f"Invalid Bybit kline timestamp {timestamp_ms}") from exc
    if timestamp < query_start or timestamp > query_end:
        return None
    return {
        "timestamp": timestamp,
        "open": raw[1],
        "high": raw[2],
        "low": raw[3],
        "close": raw[4],
        "volume": raw[5],
        "turnover": raw[6] if len(raw) > 6 else None,
        "interval": "1m",
    }


def _normalize_finalized_rows(
    rows: Any,
    *,
    observed_at: datetime,
    finality_lag_seconds: int,
    max_tail_rows: int,
    keep: Literal["head", "tail"] = "tail",
) -> tuple[MinuteRow, ...]:
    unique: dict[datetime, MinuteRow] = {}
    for raw in rows:
        if not isinstance(raw, Mapping):
            raise SourceDataError("Normalized OHLCV row must be a mapping")
        timestamp = _validated_timestamp(raw.get("timestamp"))
        if timestamp + MINUTE + timedelta(seconds=finality_lag_seconds) > observed_at:
            continue
        unique[timestamp] = _validated_ohlcv_row(raw, timestamp=timestamp)
    ordered = [unique[timestamp] for timestamp in sorted(unique)]
    if keep == "head":
        return tuple(ordered[:max_tail_rows])
    if keep == "tail":
        return tuple(ordered[-max_tail_rows:])
    raise ValueError(f"Unknown finalized-row retention policy {keep!r}")


def _validated_ohlcv_row(
    raw: Mapping[str, Any],
    *,
    timestamp: datetime,
) -> MinuteRow:
    interval = raw.get("interval", "1m")
    if interval != "1m":
        raise SourceDataError(f"Expected 1m interval, got {interval!r}")
    open_value = _positive_finite(raw.get("open"), name="open")
    high = _positive_finite(raw.get("high"), name="high")
    low = _positive_finite(raw.get("low"), name="low")
    close = _positive_finite(raw.get("close"), name="close")
    volume = _nonnegative_finite(raw.get("volume"), name="volume")
    turnover_raw = raw.get("turnover")
    turnover = (
        None
        if turnover_raw is None
        else _nonnegative_finite(turnover_raw, name="turnover")
    )
    if high < low or high < max(open_value, close) or low > min(open_value, close):
        raise SourceDataError(
            "OHLC invariant violated: high must cover open/close and low must "
            "be below open/close"
        )
    return {
        "timestamp": timestamp,
        "open": open_value,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
        "turnover": turnover,
        "interval": "1m",
    }


def _validated_timestamp(value: Any) -> datetime:
    timestamp = _require_utc(value, name="row timestamp")
    if timestamp.second != 0 or timestamp.microsecond != 0:
        raise SourceDataError(f"OHLCV timestamp is not minute-aligned: {timestamp}")
    return timestamp


def _positive_finite(value: Any, *, name: str) -> float:
    parsed = _finite_float(value, name=name)
    if parsed <= 0.0:
        raise SourceDataError(f"{name} must be positive, got {value!r}")
    return parsed


def _nonnegative_finite(value: Any, *, name: str) -> float:
    parsed = _finite_float(value, name=name)
    if parsed < 0.0:
        raise SourceDataError(f"{name} must be non-negative, got {value!r}")
    return parsed


def _finite_float(value: Any, *, name: str) -> float:
    if value is None or isinstance(value, bool):
        raise SourceDataError(f"{name} must be a finite number, got {value!r}")
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise SourceDataError(f"{name} must be a finite number, got {value!r}") from exc
    if not math.isfinite(parsed):
        raise SourceDataError(f"{name} must be finite, got {value!r}")
    return parsed


def _float_fingerprint(value: Any) -> str | None:
    if value is None:
        return None
    return float(value).hex()


def _latest_finalized_start(
    now: datetime,
    *,
    finality_lag_seconds: int,
) -> datetime:
    cutoff = now - MINUTE - timedelta(seconds=finality_lag_seconds)
    minute_epoch = int(cutoff.timestamp()) // 60 * 60
    return datetime.fromtimestamp(minute_epoch, tz=timezone.utc)


def _bounded_window(
    *,
    latest_start: datetime,
    after_timestamp: datetime | None,
    overlap_bars: int,
    max_tail_rows: int,
) -> tuple[datetime, datetime]:
    """Return a provider-sized window without skipping a catch-up backlog.

    A cold read intentionally returns the newest bounded tail.  Once the caller
    supplies a high-water timestamp, however, the window advances from that
    timestamp toward ``latest_start`` oldest-first.  Clamping the *start* to the
    latest provider page would permanently discard minutes after a long service
    outage.
    """

    bounded_start = latest_start - MINUTE * (max_tail_rows - 1)
    if after_timestamp is None:
        return bounded_start, latest_start
    # `after_timestamp` is the caller's last observed bar.  An overlap of one
    # therefore includes that high-water bar; an overlap of two also includes
    # its immediate predecessor.
    overlap_start = _floor_minute(after_timestamp) - MINUTE * (overlap_bars - 1)
    request_end = min(
        latest_start,
        overlap_start + MINUTE * (max_tail_rows - 1),
    )
    return overlap_start, request_end


def _validated_bounds(*, overlap_bars: int, max_tail_rows: int) -> tuple[int, int]:
    if isinstance(overlap_bars, bool) or not 1 <= overlap_bars <= 2:
        raise ValueError("overlap_bars must be one or two")
    if (
        isinstance(max_tail_rows, bool)
        or max_tail_rows < overlap_bars + 1
        or max_tail_rows > MAX_PROVIDER_TAIL_ROWS
    ):
        raise ValueError(
            f"max_tail_rows must be in [{overlap_bars + 1}, {MAX_PROVIDER_TAIL_ROWS}]"
        )
    return int(overlap_bars), int(max_tail_rows)


def _validated_timeout(value: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("timeout_seconds must be numeric") from exc
    if not math.isfinite(parsed) or parsed <= 0 or parsed > MAX_BYBIT_TIMEOUT_SECONDS:
        raise ValueError(
            f"timeout_seconds must be within (0, {MAX_BYBIT_TIMEOUT_SECONDS}]"
        )
    return parsed


def _normalized_asset(asset: str) -> str:
    normalized = str(asset).strip().upper()
    if not normalized:
        raise UnsupportedSourceAsset("asset cannot be empty")
    return normalized


def _resolved_now(value: datetime | None) -> datetime:
    return _require_utc(value or datetime.now(timezone.utc), name="now")


def _optional_utc(value: datetime | None, *, name: str) -> datetime | None:
    return None if value is None else _require_utc(value, name=name)


def _require_utc(value: Any, *, name: str) -> datetime:
    if not isinstance(value, datetime):
        raise SourceDataError(f"{name} must be a timezone-aware datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise SourceDataError(f"{name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _floor_minute(value: datetime) -> datetime:
    return value.replace(second=0, microsecond=0)


def _epoch_ms(value: datetime) -> int:
    return int(value.timestamp() * 1_000)


def _iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


__all__ = [
    "BYBIT_ASSETS",
    "CANONICAL_ASSETS",
    "YAHOO_ASSETS",
    "BybitFinalizedMinuteSource",
    "FinalizedMinuteBatch",
    "FinalizedMinuteSource",
    "FinalizedMinuteSourceError",
    "FinalizedMinuteSourceRouter",
    "SourceDataError",
    "SourceFetchError",
    "UnsupportedSourceAsset",
    "YahooFinalizedMinuteSource",
    "stable_row_fingerprint",
]
