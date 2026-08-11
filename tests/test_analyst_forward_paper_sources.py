from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

ANALYST_ROOT = (
    Path(__file__).resolve().parents[1] / "Risk_Yield_Meta_Model_Analyst_0_0_1"
)
if str(ANALYST_ROOT) not in sys.path:
    sys.path.insert(0, str(ANALYST_ROOT))

from forward_paper.sources import (  # noqa: E402
    BybitFinalizedMinuteSource,
    FinalizedMinuteSourceRouter,
    SourceDataError,
    UnsupportedSourceAsset,
    YahooFinalizedMinuteSource,
    stable_row_fingerprint,
)


def _bybit_kline(
    timestamp: datetime,
    *,
    open_value: float = 100.0,
    close: float = 101.0,
) -> list[str]:
    return [
        str(int(timestamp.timestamp() * 1_000)),
        str(open_value),
        str(max(open_value, close) + 1.0),
        str(min(open_value, close) - 1.0),
        str(close),
        "12.5",
        "1262.5",
    ]


class _FakeResponse:
    def __init__(self, payload: Any) -> None:
        self.payload = payload
        self.raise_calls = 0

    def raise_for_status(self) -> None:
        self.raise_calls += 1

    def json(self) -> Any:
        return self.payload


def test_bybit_fetch_is_finalized_bounded_sorted_unique_and_uses_timeout() -> None:
    now = datetime(2026, 7, 11, 12, 3, 4, tzinfo=timezone.utc)
    starts = [now.replace(minute=minute, second=0) for minute in (0, 1, 2)]
    response = _FakeResponse(
        {
            "retCode": 0,
            "retMsg": "OK",
            "result": {
                "category": "linear",
                "list": [
                    _bybit_kline(starts[2]),  # forming until 12:03:05
                    _bybit_kline(starts[1], close=102.0),
                    _bybit_kline(starts[0]),
                    _bybit_kline(starts[1], close=102.0),
                ],
            },
        }
    )
    calls: list[dict[str, Any]] = []

    def fake_get(url: str, **kwargs: Any) -> _FakeResponse:
        calls.append({"url": url, **kwargs})
        return response

    source = BybitFinalizedMinuteSource(
        http_get=fake_get,
        timeout_seconds=7.0,
        overlap_bars=1,
        max_tail_rows=5,
    )
    batch = source.fetch("btcusdt", after_timestamp=starts[1], now=now)

    assert batch.asset == "BTCUSDT"
    assert batch.provider == "bybit"
    assert batch.quality == "live"
    assert batch.expected_delay_seconds == 5
    assert batch.observed_at == now
    assert [row["timestamp"] for row in batch.rows] == [starts[1]]
    assert batch.rows[-1]["close"] == 102.0
    assert response.raise_calls == 1
    assert calls == [
        {
            "url": "https://api.bybit.com/v5/market/kline",
            "params": {
                "category": "linear",
                "symbol": "BTCUSDT",
                "interval": "1",
                "start": int(starts[1].timestamp() * 1_000),
                "end": int(starts[1].timestamp() * 1_000),
                "limit": 5,
            },
            "timeout": 7.0,
        }
    ]


@pytest.mark.parametrize(
    "payload",
    [
        {"retCode": 10001, "retMsg": "bad request", "result": {"list": []}},
        {"retCode": 0, "result": {"list": "not-a-list"}},
        {"retCode": 0, "result": {"list": [["bad-timestamp"]]}},
    ],
)
def test_bybit_rejects_malformed_provider_responses(payload: Any) -> None:
    source = BybitFinalizedMinuteSource(
        http_get=lambda *_args, **_kwargs: _FakeResponse(payload)
    )
    with pytest.raises(SourceDataError):
        source.fetch("BTCUSDT", now=datetime(2026, 7, 11, tzinfo=timezone.utc))


def test_bybit_rejects_invalid_finalized_ohlc() -> None:
    timestamp = datetime(2026, 7, 11, 11, 55, tzinfo=timezone.utc)
    bad = _bybit_kline(timestamp)
    bad[2] = "99"  # high below open and close
    source = BybitFinalizedMinuteSource(
        http_get=lambda *_args, **_kwargs: _FakeResponse(
            {"retCode": 0, "result": {"category": "linear", "list": [bad]}}
        )
    )
    with pytest.raises(SourceDataError, match="OHLC invariant"):
        source.fetch(
            "BTCUSDT",
            after_timestamp=timestamp,
            now=timestamp + timedelta(minutes=2),
        )


def test_bybit_catchup_advances_oldest_first_without_skipping_provider_pages() -> None:
    anchor = datetime(2026, 7, 11, 10, 0, tzinfo=timezone.utc)
    now = anchor + timedelta(minutes=20, seconds=5)
    response = _FakeResponse(
        {
            "retCode": 0,
            "result": {
                "category": "linear",
                "list": [
                    _bybit_kline(anchor + timedelta(minutes=offset))
                    for offset in reversed(range(5))
                ],
            },
        }
    )
    calls: list[dict[str, Any]] = []

    def fake_get(url: str, **kwargs: Any) -> _FakeResponse:
        calls.append({"url": url, **kwargs})
        return response

    batch = BybitFinalizedMinuteSource(
        http_get=fake_get,
        overlap_bars=1,
        max_tail_rows=5,
    ).fetch("BTCUSDT", after_timestamp=anchor, now=now)

    assert [row["timestamp"] for row in batch.rows] == [
        anchor + timedelta(minutes=offset) for offset in range(5)
    ]
    assert calls[0]["params"]["start"] == int(anchor.timestamp() * 1_000)
    assert calls[0]["params"]["end"] == int(
        (anchor + timedelta(minutes=4)).timestamp() * 1_000
    )


def test_bybit_repeated_catchup_pages_cover_backlog_with_two_bar_overlap() -> None:
    anchor = datetime(2026, 7, 11, 10, 0, tzinfo=timezone.utc)
    available = [anchor + timedelta(minutes=offset) for offset in range(15)]
    now = anchor + timedelta(minutes=15, seconds=5)
    calls: list[tuple[datetime, datetime]] = []

    def fake_get(_url: str, **kwargs: Any) -> _FakeResponse:
        params = kwargs["params"]
        start = datetime.fromtimestamp(params["start"] / 1_000, tz=timezone.utc)
        end = datetime.fromtimestamp(params["end"] / 1_000, tz=timezone.utc)
        calls.append((start, end))
        rows = [
            _bybit_kline(timestamp)
            for timestamp in reversed(available)
            if start <= timestamp <= end
        ]
        assert len(rows) <= params["limit"]
        return _FakeResponse(
            {
                "retCode": 0,
                "result": {"category": "linear", "list": rows},
            }
        )

    source = BybitFinalizedMinuteSource(
        http_get=fake_get,
        overlap_bars=2,
        max_tail_rows=5,
    )
    high_water = anchor
    pages: list[list[datetime]] = []
    for _ in range(5):
        batch = source.fetch("BTCUSDT", after_timestamp=high_water, now=now)
        timestamps = [row["timestamp"] for row in batch.rows]
        assert timestamps
        pages.append(timestamps)
        high_water = timestamps[-1]  # type: ignore[assignment]

    assert high_water == available[-1]
    assert sorted({timestamp for page in pages for timestamp in page}) == available
    assert [page[-1] for page in pages] == [
        anchor + timedelta(minutes=offset) for offset in (3, 6, 9, 12, 14)
    ]
    assert set(pages[0]) & set(pages[1]) == set(available[2:4])
    assert calls == [
        (
            anchor + timedelta(minutes=start_offset),
            anchor + timedelta(minutes=end_offset),
        )
        for start_offset, end_offset in ((-1, 3), (2, 6), (5, 9), (8, 12), (11, 14))
    ]


def test_yahoo_is_delayed_read_only_closed_and_uses_configured_transform() -> None:
    now = datetime(2026, 7, 11, 12, 3, 30, tzinfo=timezone.utc)
    index = pd.DatetimeIndex(
        [
            datetime(2026, 7, 11, 12, 1, tzinfo=timezone.utc),
            datetime(2026, 7, 11, 12, 2, tzinfo=timezone.utc),
            datetime(2026, 7, 11, 12, 3, tzinfo=timezone.utc),
        ]
    )
    raw = pd.DataFrame(
        {
            "Open": [0.00625, 0.00620, 0.00610],
            "High": [0.00630, 0.00625, 0.00615],
            "Low": [0.00620, 0.00615, 0.00605],
            "Close": [0.00628, 0.00622, 0.00612],
            "Volume": [5.0, 6.0, 7.0],
        },
        index=index,
    )
    calls: list[dict[str, Any]] = []

    def fake_fetch(symbol: str, **kwargs: Any) -> pd.DataFrame:
        calls.append({"symbol": symbol, **kwargs})
        return raw

    source = YahooFinalizedMinuteSource(
        frame_fetcher=fake_fetch,
        overlap_bars=2,
        max_tail_rows=10,
    )
    batch = source.fetch("USDJPY", after_timestamp=index[1].to_pydatetime(), now=now)

    assert batch.provider == "yfinance"
    assert batch.quality == "delayed"
    assert batch.expected_delay_seconds == 600
    assert [row["timestamp"] for row in batch.rows] == list(index[:2].to_pydatetime())
    assert batch.rows[0]["open"] == pytest.approx(160.0)
    assert batch.rows[0]["high"] == pytest.approx(1.0 / 0.00620)
    assert batch.rows[0]["low"] == pytest.approx(1.0 / 0.00630)
    assert calls == [
        {
            "symbol": "6J=F",
            "interval": "1m",
            "start": datetime(2026, 7, 11, 12, 1, tzinfo=timezone.utc),
            "end": datetime(2026, 7, 11, 12, 2, tzinfo=timezone.utc),
        }
    ]


def test_yahoo_overlap_reaches_previous_session_across_weekend() -> None:
    friday_anchor = datetime(2026, 7, 10, 20, 59, tzinfo=timezone.utc)
    saturday_now = datetime(2026, 7, 11, 21, 16, tzinfo=timezone.utc)
    raw = pd.DataFrame(
        {
            "Open": [6300.0],
            "High": [6301.0],
            "Low": [6299.0],
            "Close": [6300.5],
            "Volume": [10.0],
        },
        index=pd.DatetimeIndex([friday_anchor]),
    )
    calls: list[dict[str, Any]] = []

    def fake_fetch(symbol: str, **kwargs: Any) -> pd.DataFrame:
        calls.append({"symbol": symbol, **kwargs})
        return raw

    batch = YahooFinalizedMinuteSource(
        frame_fetcher=fake_fetch,
        overlap_bars=1,
        max_tail_rows=10,
    ).fetch("ES", after_timestamp=friday_anchor, now=saturday_now)

    assert calls[0]["start"] == friday_anchor
    assert calls[0]["end"] == datetime(2026, 7, 11, 21, 15, tzinfo=timezone.utc)
    assert [row["timestamp"] for row in batch.rows] == [friday_anchor]


def test_yahoo_catchup_keeps_oldest_page_instead_of_skipping_to_latest() -> None:
    anchor = datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc)
    now = anchor + timedelta(minutes=30)
    index = pd.DatetimeIndex(
        [anchor + timedelta(minutes=offset) for offset in range(12)]
    )
    raw = pd.DataFrame(
        {
            "Open": [100.0 + offset for offset in range(12)],
            "High": [101.0 + offset for offset in range(12)],
            "Low": [99.0 + offset for offset in range(12)],
            "Close": [100.5 + offset for offset in range(12)],
            "Volume": [10.0] * 12,
        },
        index=index,
    )

    batch = YahooFinalizedMinuteSource(
        frame_fetcher=lambda *_args, **_kwargs: raw,
        overlap_bars=1,
        max_tail_rows=5,
    ).fetch("ES", after_timestamp=anchor, now=now)

    assert [row["timestamp"] for row in batch.rows] == list(index[:5].to_pydatetime())


def test_yahoo_repeated_catchup_pages_cover_backlog_with_overlap() -> None:
    anchor = datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc)
    available = [anchor + timedelta(minutes=offset) for offset in range(15)]
    raw = pd.DataFrame(
        {
            "Open": [100.0 + offset for offset in range(15)],
            "High": [101.0 + offset for offset in range(15)],
            "Low": [99.0 + offset for offset in range(15)],
            "Close": [100.5 + offset for offset in range(15)],
            "Volume": [10.0] * 15,
        },
        index=pd.DatetimeIndex(available),
    )
    calls: list[tuple[datetime, datetime]] = []

    def fake_fetch(_symbol: str, **kwargs: Any) -> pd.DataFrame:
        start = kwargs["start"]
        end = kwargs["end"]
        calls.append((start, end))
        return raw.loc[(raw.index >= start) & (raw.index < end)]

    source = YahooFinalizedMinuteSource(
        frame_fetcher=fake_fetch,
        overlap_bars=2,
        max_tail_rows=5,
    )
    high_water = anchor
    pages: list[list[datetime]] = []
    for _ in range(5):
        batch = source.fetch(
            "ES",
            after_timestamp=high_water,
            now=anchor + timedelta(minutes=30),
        )
        timestamps = [row["timestamp"] for row in batch.rows]
        assert timestamps
        pages.append(timestamps)
        high_water = timestamps[-1]  # type: ignore[assignment]

    assert high_water == available[-1]
    assert sorted({timestamp for page in pages for timestamp in page}) == available
    assert [page[-1] for page in pages] == [
        anchor + timedelta(minutes=offset) for offset in (4, 7, 10, 13, 14)
    ]
    assert set(pages[0]) & set(pages[1]) == set(available[3:5])
    assert [start for start, _end in calls] == [
        anchor + timedelta(minutes=offset) for offset in (-1, 3, 6, 9, 12)
    ]


def test_stable_fingerprint_is_provider_independent_and_revision_sensitive() -> None:
    row = {
        "timestamp": datetime(2026, 7, 11, 12, 0, tzinfo=timezone.utc),
        "open": 100,
        "high": 102,
        "low": 99,
        "close": 101,
        "volume": 10,
        "turnover": None,
        "interval": "1m",
    }
    same = {**row, "open": 100.0, "provider": "anything"}
    revised = {**row, "close": 101.5}

    digest = stable_row_fingerprint("BTCUSDT", row)
    assert len(digest) == 64
    assert digest == stable_row_fingerprint("btcusdt", same)
    assert digest != stable_row_fingerprint("BTCUSDT", revised)
    assert digest != stable_row_fingerprint("ETHUSDT", row)


def test_router_covers_only_the_eight_canonical_assets() -> None:
    class Stub:
        def __init__(self) -> None:
            self.assets: list[str] = []

        def fetch(
            self,
            asset: str,
            after_timestamp: datetime | None = None,
            now: datetime | None = None,
        ) -> str:
            self.assets.append(asset)
            return asset

    bybit = Stub()
    yahoo = Stub()
    router = FinalizedMinuteSourceRouter(bybit=bybit, yahoo=yahoo)  # type: ignore[arg-type]

    assert router.fetch("ETHUSDT") == "ETHUSDT"  # type: ignore[comparison-overlap]
    assert router.fetch("GC") == "GC"  # type: ignore[comparison-overlap]
    assert bybit.assets == ["ETHUSDT"]
    assert yahoo.assets == ["GC"]
    with pytest.raises(UnsupportedSourceAsset):
        router.fetch("XAUUSD")
