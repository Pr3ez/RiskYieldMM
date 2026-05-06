from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import polars as pl

from fetchingByBit import fetch_bybit_market_data as fetcher
from fetchingByBit.source_config import BYBIT_SYMBOLS, normalized_symbols, symbol_slug


def _ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


def test_timestamp_normalizer_casts_to_millisecond_utc() -> None:
    df = pl.DataFrame(
        {"timestamp": [datetime(2021, 1, 1, tzinfo=timezone.utc)], "value": [1.0]}
    )

    normalized = fetcher._normalize_timestamp_dtype(df)

    assert normalized.schema["timestamp"] == fetcher.TIMESTAMP_DTYPE


def test_klines_to_df_uses_persisted_timestamp_dtype() -> None:
    df = fetcher._klines_to_df(
        [["1609459200000", "1", "2", "0.5", "1.5", "10", "15"]],
        "1m",
    )

    assert df.schema["timestamp"] == fetcher.TIMESTAMP_DTYPE


def test_to_ms_accepts_iso_datetime_strings() -> None:
    assert fetcher._to_ms("2024-01-02T14:30:00Z") == _ms(
        datetime(2024, 1, 2, 14, 30, tzinfo=timezone.utc)
    )
    assert fetcher._to_ms("2024-01-02") == _ms(
        datetime(2024, 1, 2, tzinfo=timezone.utc)
    )


def test_configured_bybit_symbols_include_btc_and_eth() -> None:
    assert normalized_symbols(BYBIT_SYMBOLS) == ("BTCUSDT", "ETHUSDT")
    assert symbol_slug("ETHUSDT") == "ethusdt"


def test_progress_keys_are_symbol_specific(tmp_path: Path, monkeypatch) -> None:
    progress_file = tmp_path / ".fetch_progress.json"
    monkeypatch.setattr(fetcher, "PROGRESS_FILE", str(progress_file))

    fetcher.save_progress(
        "klines",
        "1m",
        1609459200000,
        "complete",
        symbol="ETHUSDT",
        category="linear",
    )

    progress = json.loads(progress_file.read_text())
    assert "ETHUSDT_linear_klines_1m" in progress
    assert "BTCUSDT_linear_klines_1m" not in progress
    assert (
        fetcher.load_progress("klines", "1m", symbol="ETHUSDT", category="linear")[
            "last_timestamp_ms"
        ]
        == 1609459200000
    )
    assert fetcher.load_progress("klines", "1m", symbol="BTCUSDT") is None


class _FakeResponse:
    headers: dict[str, str] = {}

    def __init__(self, payload: dict):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class _FakeSession:
    def __init__(self, payload: dict):
        self.payload = payload
        self.calls: list[dict] = []

    def get(self, _url: str, params: dict, timeout: int) -> _FakeResponse:
        self.calls.append(dict(params))
        return _FakeResponse(self.payload)


def test_long_short_ratio_resumes_from_latest_local_timestamp(
    tmp_path: Path, monkeypatch
) -> None:
    existing_ts = [
        _ms(datetime(2021, 1, 1, 0, 0, tzinfo=timezone.utc)),
        _ms(datetime(2021, 1, 1, 0, 5, tzinfo=timezone.utc)),
    ]
    new_ts = [
        _ms(datetime(2021, 1, 1, 0, 10, tzinfo=timezone.utc)),
        _ms(datetime(2021, 1, 1, 0, 15, tzinfo=timezone.utc)),
    ]

    output_dir = tmp_path / "long-short-ratio-5m-bybit-linear"
    output_dir.mkdir()
    output_file = output_dir / "btcusdt_ls_ratio.parquet"
    pl.DataFrame(
        {
            "timestamp_ms": existing_ts,
            "buyRatio": [0.51, 0.52],
            "sellRatio": [0.49, 0.48],
        }
    ).with_columns(
        pl.from_epoch("timestamp_ms", time_unit="ms")
        .dt.replace_time_zone("UTC")
        .cast(fetcher.TIMESTAMP_DTYPE)
        .alias("timestamp")
    ).write_parquet(output_file)

    payload = {
        "retCode": 0,
        "result": {
            "list": [
                {
                    "symbol": "BTCUSDT",
                    "timestamp": str(new_ts[1]),
                    "buyRatio": "0.54",
                    "sellRatio": "0.46",
                },
                {
                    "symbol": "BTCUSDT",
                    "timestamp": str(new_ts[0]),
                    "buyRatio": "0.53",
                    "sellRatio": "0.47",
                },
            ],
            "nextPageCursor": "",
        },
    }
    fake_session = _FakeSession(payload)
    monkeypatch.setattr(fetcher, "BASE_DIR", str(tmp_path))
    monkeypatch.setattr(
        fetcher, "PROGRESS_FILE", str(tmp_path / ".fetch_progress.json")
    )
    monkeypatch.setattr(fetcher, "SESSION", fake_session)
    monkeypatch.setattr(fetcher.time, "sleep", lambda _seconds: None)

    fetcher.fetch_long_short_ratio(
        "BTCUSDT",
        "linear",
        "5",
        "5m",
        "2021-01-01",
        "2021-01-02",
    )

    assert len(fake_session.calls) == 1
    assert fake_session.calls[0]["startTime"] == str(existing_ts[-1] + 5 * 60_000)
    assert fake_session.calls[0]["endTime"] == str(
        _ms(datetime(2021, 1, 2, tzinfo=timezone.utc))
    )

    updated = pl.read_parquet(output_file)
    assert updated.schema["timestamp"] == fetcher.TIMESTAMP_DTYPE
    assert updated["timestamp_ms"].to_list() == existing_ts + new_ts
    assert updated.height == 4
