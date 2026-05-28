from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import polars as pl
import pytest

from scripts.htf_backtest.catboost.stage1_multiasset_dataset import (
    build_context_set_hash,
    build_multiasset_stage1_dataset,
    build_stage1_dataset_variant_id,
    parse_stage1_context_assets,
    parse_stage1_target_assets,
)
from scripts.htf_backtest.catboost.utils import get_batch_count


def _timestamps(rows: int) -> list[datetime]:
    start = datetime(2024, 1, 2, 14, 30, tzinfo=timezone.utc)
    return [start + timedelta(minutes=i) for i in range(rows)]


def _asset_root(tmp_path: Path, asset: str) -> Path:
    return tmp_path / "data" / "htf_multiasset" / asset.lower()


def _write_asset_batches(
    tmp_path: Path,
    *,
    asset: str,
    timestamps: list[datetime],
    batch_id: int = 1,
    feature_root: str = "htf_with_helpers",
    label_root: str = "htf_4class_labels",
    open_values: list[float | None] | None = None,
) -> None:
    open_values = open_values or [100.0 + float(i) for i, _ in enumerate(timestamps)]
    feature_dir = (
        _asset_root(tmp_path, asset)
        / feature_root
        / "1m"
        / "target_4class"
    )
    label_dir = _asset_root(tmp_path, asset) / label_root / "1m"
    feature_dir.mkdir(parents=True, exist_ok=True)
    label_dir.mkdir(parents=True, exist_ok=True)

    features = pl.DataFrame(
        {
            "timestamp": timestamps,
            "batch_id": [batch_id for _ in timestamps],
            "open": open_values,
            "close": [200.0 + float(i) for i, _ in enumerate(timestamps)],
            "volume": [10.0 for _ in timestamps],
            "bar_in_batch_norm": [
                float(i + 1) / max(1, len(timestamps)) for i, _ in enumerate(timestamps)
            ],
            "is_label_half": [True for _ in timestamps],
            "minutes_since_prev_real_bar": [1.0 for _ in timestamps],
            "target_4class": [3 for _ in timestamps],
        }
    )
    labels = pl.DataFrame(
        {
            "timestamp": timestamps,
            "batch_id": [batch_id for _ in timestamps],
            "target_4class": [i % 4 for i, _ in enumerate(timestamps)],
            "target_name": ["UP_BALANCED" for _ in timestamps],
        }
    )
    features.write_parquet(feature_dir / f"batch_{batch_id:04d}.parquet")
    labels.write_parquet(label_dir / f"batch_{batch_id:04d}.parquet")


def _write_ta_flags(
    tmp_path: Path,
    *,
    asset: str,
    timestamps: list[datetime],
    values: list[int],
    timeframe: str = "15m",
    signal_set: str = "raw",
) -> None:
    root_name = "ta_signal_flags" if signal_set == "raw" else "ta_compact_signal_flags"
    suffix = "ta_flags" if signal_set == "raw" else "ta_compact_flags"
    flag_dir = _asset_root(tmp_path, asset) / root_name / timeframe
    flag_dir.mkdir(parents=True, exist_ok=True)
    slug = asset.lower()
    col_name = (
        f"ta_{timeframe}_test_long"
        if signal_set == "raw"
        else f"ta_{timeframe}_compact_test_long"
    )
    pl.DataFrame(
        {
            "timestamp": timestamps,
            col_name: values,
        }
    ).write_parquet(flag_dir / f"{slug}_{timeframe}_{suffix}.parquet")


def test_asset_selector_parsing_and_context_hash() -> None:
    assert parse_stage1_target_assets("BTCUSDT,ETHUSDT,BTCUSDT") == (
        "BTCUSDT",
        "ETHUSDT",
    )
    assert parse_stage1_context_assets(
        "core-ex-target",
        target_asset="BTCUSDT",
    ) == ("ETHUSDT", "EURUSD", "USDJPY", "GC", "CL", "ES", "NQ")
    assert (
        build_context_set_hash(
            target_asset="BTCUSDT",
            context_assets=("ETHUSDT", "EURUSD", "USDJPY", "GC", "CL", "ES", "NQ"),
        )
        == "corexself"
    )
    assert (
        build_stage1_dataset_variant_id(
            include_ta_flags=True,
            ta_timeframes=("15m",),
            ta_signal_sets=("raw",),
        )
        == "ta_raw_15m"
    )


def test_target_only_assembly_preserves_target_rows_and_labels(tmp_path: Path) -> None:
    ts = _timestamps(3)
    _write_asset_batches(tmp_path, asset="BTCUSDT", timestamps=ts)

    result = build_multiasset_stage1_dataset(
        project_root=tmp_path,
        target_asset="BTCUSDT",
        context_assets=(),
        root_key="8h/B",
    )

    features = pl.read_parquet(
        result.features_dir / "1m" / "target_4class" / "batch_0001.parquet"
    )
    labels = pl.read_parquet(result.labels_dir / "1m" / "batch_0001.parquet")

    assert features["timestamp"].to_list() == ts
    assert labels["target_4class"].to_list() == [0, 1, 2]
    assert "bar_in_batch_norm" in features.columns
    assert "T_BTCUSDT__open" in features.columns
    assert "target_4class" not in features.columns
    assert "T_BTCUSDT__minutes_since_prev_real_bar" not in features.columns
    assert result.manifest["output_rows"] == 3
    assert result.manifest["null_feature_count"] == 0
    assert result.manifest["duplicate_count"] == 0
    batch_index = pl.read_parquet(result.manifest["output_paths"]["stage1_batch_index"])
    assert batch_index["stage1_available_pos"].to_list() == [0]
    assert batch_index["batch_id"].to_list() == [1]
    assert batch_index["valid_row_count"].to_list() == [3]


def test_assembly_can_limit_batches_for_smoke_runs(tmp_path: Path) -> None:
    first = _timestamps(2)
    second = [ts + timedelta(hours=1) for ts in first]
    _write_asset_batches(tmp_path, asset="BTCUSDT", timestamps=first, batch_id=1)
    _write_asset_batches(tmp_path, asset="BTCUSDT", timestamps=second, batch_id=2)

    result = build_multiasset_stage1_dataset(
        project_root=tmp_path,
        target_asset="BTCUSDT",
        context_assets=(),
        root_key="8h/B",
        max_batches=1,
        batch_id_min=2,
    )

    assert result.manifest["processed_batches"] == 1
    assert result.manifest["written_batches"] == 1
    assert result.manifest["max_batches"] == 1
    assert result.manifest["batch_id_min"] == 2
    assert result.manifest["output_rows"] == 2
    assert (
        result.features_dir / "1m" / "target_4class" / "batch_0002.parquet"
    ).exists()
    assert not (
        result.features_dir / "1m" / "target_4class" / "batch_0001.parquet"
    ).exists()


def test_exact_timestamp_context_join_drops_unmatched_rows(tmp_path: Path) -> None:
    target_ts = _timestamps(3)
    context_ts = [target_ts[0], target_ts[2]]
    _write_asset_batches(tmp_path, asset="BTCUSDT", timestamps=target_ts)
    _write_asset_batches(tmp_path, asset="ETHUSDT", timestamps=context_ts)

    result = build_multiasset_stage1_dataset(
        project_root=tmp_path,
        target_asset="BTCUSDT",
        context_assets=("ETHUSDT",),
        root_key="8h/B",
    )

    features = pl.read_parquet(
        result.features_dir / "1m" / "target_4class" / "batch_0001.parquet"
    )
    labels = pl.read_parquet(result.labels_dir / "1m" / "batch_0001.parquet")

    assert features["timestamp"].to_list() == context_ts
    assert labels["timestamp"].to_list() == context_ts
    assert "C_ETHUSDT__open" in features.columns
    assert "C_ETHUSDT__target_4class" not in features.columns
    assert result.manifest["output_rows"] == 2
    assert result.manifest["rows_dropped_by_missing_context"] == 1


def test_duplicate_target_or_context_timestamps_fail(tmp_path: Path) -> None:
    ts = _timestamps(3)
    duplicate_ts = [ts[0], ts[0], ts[1]]

    _write_asset_batches(tmp_path, asset="BTCUSDT", timestamps=duplicate_ts)
    with pytest.raises(ValueError, match="Target BTCUSDT"):
        build_multiasset_stage1_dataset(
            project_root=tmp_path,
            target_asset="BTCUSDT",
            context_assets=(),
            root_key="8h/B",
        )

    tmp_path_2 = tmp_path / "context_duplicate"
    _write_asset_batches(tmp_path_2, asset="BTCUSDT", timestamps=ts)
    _write_asset_batches(tmp_path_2, asset="ETHUSDT", timestamps=duplicate_ts)
    with pytest.raises(ValueError, match="Context ETHUSDT"):
        build_multiasset_stage1_dataset(
            project_root=tmp_path_2,
            target_asset="BTCUSDT",
            context_assets=("ETHUSDT",),
            root_key="8h/B",
        )


def test_null_context_feature_values_are_dropped_and_reported(tmp_path: Path) -> None:
    ts = _timestamps(2)
    _write_asset_batches(tmp_path, asset="BTCUSDT", timestamps=ts)
    _write_asset_batches(
        tmp_path,
        asset="ETHUSDT",
        timestamps=ts,
        open_values=[101.0, None],
    )

    result = build_multiasset_stage1_dataset(
        project_root=tmp_path,
        target_asset="BTCUSDT",
        context_assets=("ETHUSDT",),
        root_key="8h/B",
    )

    features = pl.read_parquet(
        result.features_dir / "1m" / "target_4class" / "batch_0001.parquet"
    )

    assert len(features) == 1
    assert features["timestamp"].to_list() == [ts[0]]
    assert result.manifest["output_rows"] == 1
    assert result.manifest["rows_dropped_by_null_features"] == 1
    assert result.manifest["null_feature_count"] == 0


def test_stage1_assembly_joins_ta_flags_without_dropping_inactive_rows(tmp_path: Path) -> None:
    ts = _timestamps(3)
    _write_asset_batches(tmp_path, asset="BTCUSDT", timestamps=ts)
    _write_asset_batches(tmp_path, asset="ETHUSDT", timestamps=ts)
    _write_ta_flags(tmp_path, asset="BTCUSDT", timestamps=[ts[0], ts[2]], values=[1, 1])
    _write_ta_flags(tmp_path, asset="ETHUSDT", timestamps=[ts[1]], values=[1])

    result = build_multiasset_stage1_dataset(
        project_root=tmp_path,
        target_asset="BTCUSDT",
        context_assets=("ETHUSDT",),
        root_key="8h/B",
        include_ta_flags=True,
        ta_timeframes=("15m",),
    )

    features = pl.read_parquet(
        result.features_dir / "1m" / "target_4class" / "batch_0001.parquet"
    )

    assert len(features) == 3
    assert features["T_BTCUSDT__ta_15m_test_long"].to_list() == [1, 0, 1]
    assert features["C_ETHUSDT__ta_15m_test_long"].to_list() == [0, 1, 0]
    assert result.manifest["ta_flags_enabled"] is True
    assert result.manifest["ta_timeframes"] == ["15m"]
    assert result.manifest["ta_signal_sets"] == ["raw"]
    assert result.manifest["dataset_variant_id"] == "ta_raw_15m"
    assert "ta_raw_15m" in str(result.features_dir)
    assert "ta_raw_15m" in result.run_id
    assert result.manifest["ta_feature_columns_count"] == 2
    assert result.manifest["ta_null_count"] == 0


def test_stage1_assembly_can_join_raw_and_compact_ta_flags(tmp_path: Path) -> None:
    ts = _timestamps(2)
    _write_asset_batches(tmp_path, asset="BTCUSDT", timestamps=ts)
    _write_ta_flags(tmp_path, asset="BTCUSDT", timestamps=ts, values=[1, 0])
    _write_ta_flags(
        tmp_path,
        asset="BTCUSDT",
        timestamps=ts,
        values=[0, 1],
        signal_set="compact",
    )

    result = build_multiasset_stage1_dataset(
        project_root=tmp_path,
        target_asset="BTCUSDT",
        context_assets=(),
        root_key="8h/B",
        include_ta_flags=True,
        ta_timeframes=("15m",),
        ta_signal_sets=("all",),
    )

    features = pl.read_parquet(
        result.features_dir / "1m" / "target_4class" / "batch_0001.parquet"
    )

    assert features["T_BTCUSDT__ta_15m_test_long"].to_list() == [1, 0]
    assert features["T_BTCUSDT__ta_15m_compact_test_long"].to_list() == [0, 1]
    assert result.manifest["ta_signal_sets"] == ["raw", "compact"]
    assert result.manifest["dataset_variant_id"] == "ta_raw_compact_15m"
    assert result.manifest["ta_feature_columns_count"] == 2


def test_sparse_merged_label_roots_report_highest_batch_id(tmp_path: Path) -> None:
    label_dir = tmp_path / "labels" / "1m"
    label_dir.mkdir(parents=True)
    for batch_id in (2678, 5856):
        pl.DataFrame(
            {
                "timestamp": _timestamps(1),
                "batch_id": [batch_id],
                "target_4class": [0],
            }
        ).write_parquet(label_dir / f"batch_{batch_id:04d}.parquet")

    assert get_batch_count(tmp_path / "labels", "1m") == 5856
