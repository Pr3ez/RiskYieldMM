from __future__ import annotations

from datetime import datetime, timezone

import polars as pl

from fetchingMultiAsset.asset_config import (
    ASSETS,
    normalized_asset_ids,
    selected_assets,
)
from fetchingMultiAsset.fetch_twelve_data import (
    OHLCV_COLUMNS,
    TIMESTAMP_DTYPE,
    TwelveDataClient,
    append_ohlcv_batches,
    batch_prefix,
    configured_api_key,
    fetch_asset_interval,
    load_local_env_file,
    load_local_secret_files,
    output_dir_for_interval,
    replace_ohlcv_window,
    twelve_values_to_ohlcv,
)


class FakeTwelveDataClient:
    def __init__(self, pages: list[list[dict[str, str]]]) -> None:
        self.pages = pages
        self.calls = []

    def time_series(self, **kwargs):
        self.calls.append(kwargs)
        return self.pages.pop(0) if self.pages else []


def test_configured_assets_cover_requested_instruments() -> None:
    assert normalized_asset_ids() == (
        "EURUSD",
        "USDJPY",
        "XAUUSD",
        "WTIUSD",
        "SPX",
        "NDX",
    )
    assert tuple(
        asset.symbol for asset in selected_assets(["eurusd", "EURUSD", "spx"])
    ) == (
        "EURUSD",
        "SPX",
    )
    assert all(asset.provider_symbol for asset in ASSETS)


def test_twelve_values_convert_to_exact_bybit_ohlcv_schema() -> None:
    df = twelve_values_to_ohlcv(
        [
            {
                "datetime": "2021-01-01 00:01:00",
                "open": "2.0",
                "high": "2.5",
                "low": "1.5",
                "close": "2.2",
            },
            {
                "datetime": "2021-01-01 00:00:00",
                "open": "1.0",
                "high": "1.5",
                "low": "0.5",
                "close": "1.2",
                "volume": "100",
            },
        ],
        "1m",
    )

    assert df.columns == OHLCV_COLUMNS
    assert df.schema["timestamp"] == TIMESTAMP_DTYPE
    assert df.schema["volume"] == pl.Float64
    assert df.schema["turnover"] == pl.Float64
    assert df["timestamp"].to_list() == [
        datetime(2021, 1, 1, 0, 0, tzinfo=timezone.utc),
        datetime(2021, 1, 1, 0, 1, tzinfo=timezone.utc),
    ]
    assert df["volume"].to_list() == [100.0, None]
    assert df["turnover"].to_list() == [None, None]


def test_append_ohlcv_batches_writes_sorted_bybit_style_files(tmp_path) -> None:
    asset = selected_assets(["EURUSD"])[0]
    df = twelve_values_to_ohlcv(
        [
            {
                "datetime": "2021-01-01 00:02:00",
                "open": "3",
                "high": "3",
                "low": "3",
                "close": "3",
            },
            {
                "datetime": "2021-01-01 00:00:00",
                "open": "1",
                "high": "1",
                "low": "1",
                "close": "1",
            },
            {
                "datetime": "2021-01-01 00:01:00",
                "open": "2",
                "high": "2",
                "low": "2",
                "close": "2",
            },
        ],
        "1m",
    )

    summary = append_ohlcv_batches(
        df,
        asset=asset,
        interval="1m",
        base_dir=tmp_path,
        chunk_size=2,
    )

    output_dir = output_dir_for_interval(tmp_path, "1m")
    files = sorted(output_dir.glob(f"{batch_prefix(asset)}*.parquet"))
    assert [path.name for path in files] == [
        "eurusd_twelvedata_sorted_batch_000000.parquet",
        "eurusd_twelvedata_sorted_batch_000001.parquet",
    ]
    assert summary.rows_written == 3
    first = pl.read_parquet(files[0])
    second = pl.read_parquet(files[1])
    assert first.columns == OHLCV_COLUMNS
    assert first.height == 2
    assert second.height == 1
    assert first["close"].to_list() == [1.0, 2.0]
    assert second["close"].to_list() == [3.0]


def test_append_ohlcv_batches_does_not_lock_resume_to_tiny_probe_chunk(
    tmp_path,
) -> None:
    asset = selected_assets(["EURUSD"])[0]
    first_probe = twelve_values_to_ohlcv(
        [
            {
                "datetime": "2021-01-01 00:00:00",
                "open": "1",
                "high": "1",
                "low": "1",
                "close": "1",
            }
        ],
        "1m",
    )
    append_ohlcv_batches(
        first_probe,
        asset=asset,
        interval="1m",
        base_dir=tmp_path,
        chunk_size=4,
    )

    next_rows = twelve_values_to_ohlcv(
        [
            {
                "datetime": "2021-01-01 00:01:00",
                "open": "2",
                "high": "2",
                "low": "2",
                "close": "2",
            },
            {
                "datetime": "2021-01-01 00:02:00",
                "open": "3",
                "high": "3",
                "low": "3",
                "close": "3",
            },
            {
                "datetime": "2021-01-01 00:03:00",
                "open": "4",
                "high": "4",
                "low": "4",
                "close": "4",
            },
            {
                "datetime": "2021-01-01 00:04:00",
                "open": "5",
                "high": "5",
                "low": "5",
                "close": "5",
            },
        ],
        "1m",
    )
    append_ohlcv_batches(
        next_rows,
        asset=asset,
        interval="1m",
        base_dir=tmp_path,
        chunk_size=4,
    )

    output_dir = output_dir_for_interval(tmp_path, "1m")
    files = sorted(output_dir.glob(f"{batch_prefix(asset)}*.parquet"))
    assert [pl.read_parquet(path).height for path in files] == [4, 1]


def test_replace_ohlcv_window_backfills_inside_existing_asset_files(tmp_path) -> None:
    asset = selected_assets(["EURUSD"])[0]
    existing = twelve_values_to_ohlcv(
        [
            {
                "datetime": "2021-01-01 00:02:00",
                "open": "2",
                "high": "2",
                "low": "2",
                "close": "2",
            },
            {
                "datetime": "2021-01-01 00:10:00",
                "open": "10",
                "high": "10",
                "low": "10",
                "close": "10",
            },
        ],
        "1m",
    )
    append_ohlcv_batches(
        existing,
        asset=asset,
        interval="1m",
        base_dir=tmp_path,
        chunk_size=1,
    )
    replacement = twelve_values_to_ohlcv(
        [
            {
                "datetime": "2021-01-01 00:00:00",
                "open": "100",
                "high": "100",
                "low": "100",
                "close": "100",
            },
            {
                "datetime": "2021-01-01 00:01:00",
                "open": "101",
                "high": "101",
                "low": "101",
                "close": "101",
            },
            {
                "datetime": "2021-01-01 00:02:00",
                "open": "102",
                "high": "102",
                "low": "102",
                "close": "102",
            },
        ],
        "1m",
    )

    summary = replace_ohlcv_window(
        replacement,
        asset=asset,
        interval="1m",
        window_start=datetime(2021, 1, 1, 0, 0, tzinfo=timezone.utc),
        window_end=datetime(2021, 1, 1, 0, 2, tzinfo=timezone.utc),
        base_dir=tmp_path,
        chunk_size=2,
    )

    output_dir = output_dir_for_interval(tmp_path, "1m")
    files = sorted(output_dir.glob(f"{batch_prefix(asset)}*.parquet"))
    combined = pl.concat([pl.read_parquet(path) for path in files]).sort("timestamp")

    assert summary.rows_written == 4
    assert combined["timestamp"].to_list() == [
        datetime(2021, 1, 1, 0, 0, tzinfo=timezone.utc),
        datetime(2021, 1, 1, 0, 1, tzinfo=timezone.utc),
        datetime(2021, 1, 1, 0, 2, tzinfo=timezone.utc),
        datetime(2021, 1, 1, 0, 10, tzinfo=timezone.utc),
    ]
    assert combined["close"].to_list() == [100.0, 101.0, 102.0, 10.0]


def test_fetch_asset_interval_resumes_from_latest_local_timestamp(tmp_path) -> None:
    asset = selected_assets(["EURUSD"])[0]
    existing = twelve_values_to_ohlcv(
        [
            {
                "datetime": "2021-01-01 00:00:00",
                "open": "1",
                "high": "1",
                "low": "1",
                "close": "1",
            }
        ],
        "1m",
    )
    append_ohlcv_batches(existing, asset=asset, interval="1m", base_dir=tmp_path)

    client = FakeTwelveDataClient(
        [
            [
                {
                    "datetime": "2021-01-01 00:00:00",
                    "open": "1",
                    "high": "1",
                    "low": "1",
                    "close": "1",
                },
                {
                    "datetime": "2021-01-01 00:01:00",
                    "open": "2",
                    "high": "2",
                    "low": "2",
                    "close": "2",
                },
            ]
        ]
    )

    summary = fetch_asset_interval(
        asset=asset,
        interval="1m",
        client=client,  # type: ignore[arg-type]
        start_date="2021-01-01 00:00:00",
        end_date="2021-01-01 00:01:00",
        base_dir=tmp_path,
        request_sleep=0,
    )

    assert summary.rows_written == 1
    assert client.calls[0]["start"] == datetime(2021, 1, 1, 0, 1, tzinfo=timezone.utc)
    files = sorted(output_dir_for_interval(tmp_path, "1m").glob("eurusd_*.parquet"))
    combined = pl.concat([pl.read_parquet(path) for path in files]).sort("timestamp")
    assert combined["close"].to_list() == [1.0, 2.0]


def test_twelve_data_client_raises_on_api_error_payload() -> None:
    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self):
            return {"status": "error", "message": "bad symbol"}

    class Session:
        def get(self, *args, **kwargs):
            return Response()

    client = TwelveDataClient("key", session=Session())  # type: ignore[arg-type]
    try:
        client.time_series(
            symbol="BAD",
            interval="1min",
            start=datetime(2021, 1, 1, tzinfo=timezone.utc),
            end=datetime(2021, 1, 2, tzinfo=timezone.utc),
        )
    except Exception as exc:
        assert "bad symbol" in str(exc)
    else:
        raise AssertionError("Expected API error")


def test_local_secret_file_loads_key_without_overriding_environment(
    tmp_path, monkeypatch
) -> None:
    secret_file = tmp_path / "local_secrets.env"
    secret_file.write_text(
        "\n".join(
            [
                "# comment",
                "export TWELVE_DATA_API_KEY=file-key",
                'OANDA_API_TOKEN="quoted-token"',
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("TWELVE_DATA_API_KEY", "env-key")

    loaded = load_local_env_file(secret_file)

    assert loaded["TWELVE_DATA_API_KEY"] == "file-key"
    assert loaded["OANDA_API_TOKEN"] == "quoted-token"
    assert configured_api_key() == "env-key"


def test_configured_api_key_can_come_from_local_secret_file(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.delenv("TWELVE_DATA_API_KEY", raising=False)
    secret_file = tmp_path / "local_secrets.env"
    secret_file.write_text("TWELVE_DATA_API_KEY=file-key\n", encoding="utf-8")

    load_local_secret_files((secret_file,))

    assert configured_api_key() == "file-key"
    assert configured_api_key("cli-key") == "cli-key"
