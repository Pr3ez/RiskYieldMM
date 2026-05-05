from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from scripts.feature_engineering.compute_htf_features import (
    DATA_SOURCE_PATTERNS,
    HTFFeatureEngine,
    source_available_timestamps,
)


def _engine() -> HTFFeatureEngine:
    return HTFFeatureEngine(data_dir=Path("fetchingByBit"), verbose=False)


def _base_frame(start: str, periods: int, freq: str = "1min") -> pd.DataFrame:
    return pd.DataFrame(
        {"timestamp": pd.date_range(start, periods=periods, freq=freq, tz="UTC")}
    )


def test_period_start_aggregate_not_visible_before_available_time() -> None:
    base = _base_frame("2021-01-01 00:00:00", periods=11)
    source = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                ["2021-01-01 00:00:00", "2021-01-01 00:05:00"], utc=True
            ),
            "value": [100.0, 105.0],
        }
    )

    aligned = _engine().align_source_to_base(
        base,
        source,
        columns=["value"],
        source_tf="5m",
        data_type="synthetic_period_aggregate",
        timestamp_role="period_start_aggregate",
    )

    assert aligned["value"].iloc[:5].isna().all()
    assert aligned["value"].iloc[5:10].to_list() == [100.0] * 5
    assert aligned["value"].iloc[10] == 105.0


def test_available_at_snapshot_is_visible_from_its_timestamp() -> None:
    base = _base_frame("2021-01-01 00:03:00", periods=5)
    source = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(["2021-01-01 00:05:00"], utc=True),
            "value": [105.0],
        }
    )

    aligned = _engine().align_source_to_base(
        base,
        source,
        columns=["value"],
        source_tf="5m",
        data_type="synthetic_available_at",
        timestamp_role="available_at",
    )

    assert aligned["value"].iloc[:2].isna().all()
    assert aligned["value"].iloc[2:].to_list() == [105.0, 105.0, 105.0]


def test_funding_settlement_alignment_uses_latest_settled_rate() -> None:
    base = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [
                    "2021-01-01 07:59:00",
                    "2021-01-01 08:00:00",
                    "2021-01-01 08:01:00",
                ],
                utc=True,
            )
        }
    )
    source = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                ["2021-01-01 00:00:00", "2021-01-01 08:00:00"], utc=True
            ),
            "fundingRate": [0.0001, 0.0002],
        }
    )

    aligned = _engine().align_source_to_base(
        base,
        source,
        columns=["fundingRate"],
        source_tf="8h",
        data_type="funding_rate",
    )

    assert aligned["fundingRate"].to_list() == [0.0001, 0.0002, 0.0002]


def test_broadcast_compat_wrapper_preserves_available_at_behavior() -> None:
    base = _base_frame("2021-01-01 00:00:00", periods=7)
    source = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                ["2021-01-01 00:00:00", "2021-01-01 00:05:00"], utc=True
            ),
            "value": [100.0, 105.0],
        }
    )

    aligned = _engine().broadcast_higher_tf(base, source, ["value"], "5m")

    assert aligned["value"].to_list() == [
        100.0,
        100.0,
        100.0,
        100.0,
        100.0,
        105.0,
        105.0,
    ]


def test_source_metadata_complete_for_alignment_contract() -> None:
    required_keys = {"timestamp_role", "availability_offset", "publication_lag"}
    valid_roles = {
        "bar_start",
        "available_at",
        "settlement_at",
        "period_start_aggregate",
    }

    for data_type, config in DATA_SOURCE_PATTERNS.items():
        assert required_keys <= set(config), data_type
        assert config["timestamp_role"] in valid_roles, data_type


def test_source_available_timestamps_shifts_period_start_aggregate_by_source_tf() -> None:
    timestamps = pd.Series(
        pd.to_datetime(["2021-01-01 00:00:00", "2021-01-01 00:05:00"], utc=True)
    )

    available = source_available_timestamps(
        timestamps,
        source_tf="5m",
        timestamp_role="period_start_aggregate",
    )

    expected = pd.Series(
        pd.to_datetime(["2021-01-01 00:05:00", "2021-01-01 00:10:00"])
    )
    assert np.array_equal(available.to_numpy(), expected.to_numpy())
