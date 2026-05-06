from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import polars as pl

from fetchingMultiAsset.asset_config import selected_databento_futures
from fetchingMultiAsset.fetch_databento import (
    databento_available_end,
    databento_batch_prefix,
    databento_frame_to_ohlcv,
    latest_safe_databento_end,
    output_dir_for_databento_interval,
    plan_fetch_range,
    resolve_databento_end,
)
from fetchingMultiAsset.fetch_twelve_data import (
    OHLCV_COLUMNS,
    TIMESTAMP_DTYPE,
    append_ohlcv_batches,
)


def test_databento_futures_registry_covers_requested_tradeable_proxies() -> None:
    assets = selected_databento_futures()
    assert tuple(asset.symbol for asset in assets) == (
        "EURUSD",
        "USDJPY",
        "GC",
        "CL",
        "ES",
        "NQ",
    )
    assert tuple(asset.provider_symbol for asset in assets) == (
        "6E.v.0",
        "6J.v.0",
        "GC.v.0",
        "CL.v.0",
        "ES.v.0",
        "NQ.v.0",
    )
    assert all(asset.dataset == "GLBX.MDP3" for asset in assets)
    assert all(asset.schema == "ohlcv-1m" for asset in assets)
    assert all(asset.stype_in == "continuous" for asset in assets)
    assert selected_databento_futures(["USDJPY"])[0].price_transform == "inverse"


def test_databento_output_paths_match_provider_root(tmp_path) -> None:
    asset = selected_databento_futures(["ES"])[0]
    out_dir = output_dir_for_databento_interval(tmp_path, "1m")

    assert out_dir == tmp_path / "sorted-1m-databento-futures"
    assert databento_batch_prefix(asset) == "es_databento_sorted_batch_"


def test_databento_frame_converts_to_bybit_style_ohlcv_schema() -> None:
    frame = pd.DataFrame(
        {
            "ts_event": pd.to_datetime(
                ["2024-01-02T14:30:00Z", "2024-01-02T14:31:00Z"],
                utc=True,
            ),
            "open": [100.0, 101.0],
            "high": [101.0, 102.0],
            "low": [99.0, 100.0],
            "close": [100.5, 101.5],
            "volume": [10, 20],
            "symbol": ["ES.v.0", "ES.v.0"],
        }
    )

    df = databento_frame_to_ohlcv(frame, "1m")

    assert df.columns == OHLCV_COLUMNS
    assert df.schema["timestamp"] == TIMESTAMP_DTYPE
    assert df.schema["volume"] == pl.Float64
    assert df.schema["turnover"] == pl.Float64
    assert df["timestamp"].to_list() == [
        datetime(2024, 1, 2, 14, 30, tzinfo=timezone.utc),
        datetime(2024, 1, 2, 14, 31, tzinfo=timezone.utc),
    ]
    assert df["turnover"].to_list() == [None, None]


def test_databento_frame_can_invert_jpy_futures_to_usdjpy_path() -> None:
    frame = pd.DataFrame(
        {
            "ts_event": pd.to_datetime(["2024-01-02T14:30:00Z"], utc=True),
            "open": [0.0068],
            "high": [0.0069],
            "low": [0.0067],
            "close": [0.00675],
            "volume": [10],
        }
    )

    df = databento_frame_to_ohlcv(frame, "1m", price_transform="inverse")

    assert df["open"][0] == 1.0 / 0.0068
    assert df["high"][0] == 1.0 / 0.0067
    assert df["low"][0] == 1.0 / 0.0069
    assert df["close"][0] == 1.0 / 0.00675


def test_databento_now_end_is_capped_to_provider_safe_boundary() -> None:
    now = datetime(2026, 5, 6, 15, 42, 22, tzinfo=timezone.utc)

    assert latest_safe_databento_end(now) == datetime(
        2026, 5, 6, 15, 30, tzinfo=timezone.utc
    )
    assert resolve_databento_end("now", now=now) == datetime(
        2026, 5, 6, 15, 30, tzinfo=timezone.utc
    )
    assert resolve_databento_end(
        datetime(2024, 1, 2, 15, 30, tzinfo=timezone.utc),
        now=now,
    ) == datetime(2024, 1, 2, 15, 30, tzinfo=timezone.utc)


def test_databento_available_end_reads_schema_specific_entitlement() -> None:
    class Metadata:
        def get_dataset_range(self, *, dataset: str):
            assert dataset == "GLBX.MDP3"
            return {
                "end": "2026-05-06T15:30:00.000000000Z",
                "schema": {
                    "ohlcv-1m": {
                        "end": "2026-05-06T07:45:31.523776000Z",
                    },
                },
            }

    class Client:
        metadata = Metadata()

    assert databento_available_end(
        Client(),
        dataset="GLBX.MDP3",
        schema="ohlcv-1m",
    ) == datetime(2026, 5, 6, 7, 45, 31, 523776, tzinfo=timezone.utc)


def test_databento_plan_caps_end_to_entitlement_available_end(tmp_path) -> None:
    asset = selected_databento_futures(["ES"])[0]

    plan = plan_fetch_range(
        asset=asset,
        start=datetime(2026, 5, 6, 7, 40, tzinfo=timezone.utc),
        end=datetime(2026, 5, 6, 15, 30, tzinfo=timezone.utc),
        base_dir=tmp_path,
        available_end=datetime(2026, 5, 6, 7, 45, tzinfo=timezone.utc),
    )

    assert plan.needs_fetch
    assert plan.fetch_start == datetime(2026, 5, 6, 7, 40, tzinfo=timezone.utc)
    assert plan.fetch_end == datetime(2026, 5, 6, 7, 45, tzinfo=timezone.utc)


def test_databento_plan_resumes_after_latest_local_1m_bar(tmp_path) -> None:
    asset = selected_databento_futures(["ES"])[0]
    existing = pl.DataFrame(
        {
            "timestamp": [
                datetime(2024, 1, 2, 14, 30, tzinfo=timezone.utc),
                datetime(2024, 1, 2, 14, 31, tzinfo=timezone.utc),
            ],
            "open": [100.0, 101.0],
            "high": [101.0, 102.0],
            "low": [99.0, 100.0],
            "close": [100.5, 101.5],
            "volume": [10.0, 20.0],
            "turnover": [None, None],
            "interval": ["1m", "1m"],
        }
    ).with_columns(pl.col("timestamp").cast(TIMESTAMP_DTYPE))
    append_ohlcv_batches(
        existing,
        asset=asset,  # type: ignore[arg-type]
        interval="1m",
        base_dir=tmp_path,
        provider="databento",
        market="futures",
    )

    plan = plan_fetch_range(
        asset=asset,
        start=datetime(2024, 1, 2, 14, 30, tzinfo=timezone.utc),
        end=datetime(2024, 1, 2, 14, 35, tzinfo=timezone.utc),
        base_dir=tmp_path,
    )

    assert plan.needs_fetch
    assert plan.local_last_ts == datetime(2024, 1, 2, 14, 31, tzinfo=timezone.utc)
    assert plan.fetch_start == datetime(2024, 1, 2, 14, 32, tzinfo=timezone.utc)
    assert plan.fetch_end == datetime(2024, 1, 2, 14, 35, tzinfo=timezone.utc)


def test_databento_plan_marks_range_up_to_date_when_local_data_covers_it(
    tmp_path,
) -> None:
    asset = selected_databento_futures(["ES"])[0]
    existing = pl.DataFrame(
        {
            "timestamp": [
                datetime(2024, 1, 2, 14, 30, tzinfo=timezone.utc),
                datetime(2024, 1, 2, 14, 31, tzinfo=timezone.utc),
            ],
            "open": [100.0, 101.0],
            "high": [101.0, 102.0],
            "low": [99.0, 100.0],
            "close": [100.5, 101.5],
            "volume": [10.0, 20.0],
            "turnover": [None, None],
            "interval": ["1m", "1m"],
        }
    ).with_columns(pl.col("timestamp").cast(TIMESTAMP_DTYPE))
    append_ohlcv_batches(
        existing,
        asset=asset,  # type: ignore[arg-type]
        interval="1m",
        base_dir=tmp_path,
        provider="databento",
        market="futures",
    )

    plan = plan_fetch_range(
        asset=asset,
        start=datetime(2024, 1, 2, 14, 30, tzinfo=timezone.utc),
        end=datetime(2024, 1, 2, 14, 31, tzinfo=timezone.utc),
        base_dir=tmp_path,
    )

    assert not plan.needs_fetch
    assert plan.status == "up-to-date"
    assert plan.fetch_start is None
    assert plan.fetch_end is None
    assert plan.local_last_ts == datetime(2024, 1, 2, 14, 31, tzinfo=timezone.utc)
