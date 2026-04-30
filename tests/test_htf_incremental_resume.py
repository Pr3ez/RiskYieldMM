from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import polars as pl

from scripts.feature_engineering.htf_multiregime_pipeline import (
    MultiRegimeHTFConfig,
    _build_shifted_feature_batches_from_base,
    _label_batches_needing_repair,
    _select_incremental_label_batches,
)


def _config(tmp_path: Path) -> MultiRegimeHTFConfig:
    return MultiRegimeHTFConfig(
        project_root=tmp_path,
        data_dir=tmp_path / "data",
        raw_data_dir=tmp_path / "fetchingByBit",
        pipeline_artifact_version="test-version",
        thresholds_by_tf={"15m": {"BREAKOUT": 2.1, "RISK_RATIO": 2.5}},
        distance_windows_by_tf={"1m": {}, "15m": {}},
        run_optimization=False,
        run_helpers=False,
        run_validation=False,
    )


def _source_batch(batch_id: int, start: datetime) -> pl.DataFrame:
    timestamps = [start + timedelta(minutes=i) for i in range(2)]
    return pl.DataFrame(
        {
            "timestamp": timestamps,
            "open": [100.0 + batch_id, 101.0 + batch_id],
            "high": [102.0 + batch_id, 103.0 + batch_id],
            "low": [99.0 + batch_id, 100.0 + batch_id],
            "close": [101.0 + batch_id, 102.0 + batch_id],
            "volume": [10.0, 11.0],
            "F_example": [float(batch_id), float(batch_id) + 0.5],
        }
    )


def _combined_rows(batch_id: int, start: datetime) -> pl.DataFrame:
    timestamps = [start + timedelta(minutes=i) for i in range(2)]
    period_start = start
    period_end = start + timedelta(hours=8)
    return pl.DataFrame(
        {
            "timestamp": timestamps,
            "batch_id": [batch_id, batch_id],
            "period_8h_start": [period_start, period_start],
            "batch_family": ["C", "C"],
            "family_batch_id": [batch_id, batch_id],
            "family_period_start": [period_start, period_start],
            "family_period_end": [period_end, period_end],
            "family_bar_pos": [0, 1],
            "source_base_batch_id": [batch_id, batch_id],
            "source_base_period_start": [period_start, period_start],
            "source_half_in_base": ["first", "first"],
            "is_label_half": [True, True],
            "bar_in_batch_norm": [0.0, 0.01],
            "batch_regime": ["8h", "8h"],
            "batch_duration_hours": [8, 8],
            "family_shift_hours": [4, 4],
            "anchor_utc": ["2021-01-01T04:00:00+00:00", "2021-01-01T04:00:00+00:00"],
            "entry_window_hours": [4, 4],
        }
    )


def test_shifted_feature_resume_skips_unchanged_existing_batches(tmp_path: Path) -> None:
    config = _config(tmp_path)
    data_dir = config.data_dir
    source_dir = data_dir / "htf_features" / "1m"
    output_dir = data_dir / "htf_features_shift4h" / "1m"
    combined_dir = data_dir / "htf_backtest_shift4h"
    source_dir.mkdir(parents=True)
    output_dir.mkdir(parents=True)
    combined_dir.mkdir(parents=True)

    batch_1_start = datetime(2021, 1, 1, 4, 0, tzinfo=timezone.utc)
    batch_2_start = datetime(2021, 1, 1, 12, 0, tzinfo=timezone.utc)
    source_1 = source_dir / "batch_0001.parquet"
    source_2 = source_dir / "batch_0002.parquet"
    _source_batch(1, batch_1_start).write_parquet(source_1)
    _source_batch(2, batch_2_start).write_parquet(source_2)

    combined = pl.concat(
        [
            _combined_rows(1, batch_1_start),
            _combined_rows(2, batch_2_start),
        ],
        how="vertical",
    )
    combined.write_parquet(combined_dir / "1m_HTF_combined.parquet")
    (combined_dir / "1m_HTF_combined_meta.json").write_text("{}", encoding="utf-8")

    existing_output_1 = output_dir / "batch_0001.parquet"
    (
        _source_batch(1, batch_1_start)
        .join(_combined_rows(1, batch_1_start), on="timestamp", how="inner")
        .write_parquet(existing_output_1)
    )
    (output_dir / "_build_meta.json").write_text(
        json.dumps(
            {
                "artifact_version": "test-version-features-c-v1",
                "family": "C",
                "timeframe": "1m",
                "source_fingerprint": {"digest": "stale"},
                "schema_columns": _source_batch(1, batch_1_start).columns,
            }
        ),
        encoding="utf-8",
    )

    old_time = time.time() - 100
    new_time = time.time()
    os.utime(source_1, (old_time, old_time))
    os.utime(existing_output_1, (new_time, new_time))
    existing_mtime = existing_output_1.stat().st_mtime_ns

    result = _build_shifted_feature_batches_from_base(config, regime="8h", tf="1m")

    assert result["run_mode"] == "incremental_tail"
    assert result["written"] == 1
    assert result["skipped"] == 1
    assert existing_output_1.stat().st_mtime_ns == existing_mtime
    assert (output_dir / "batch_0002.parquet").exists()


def test_incremental_label_selection_repairs_former_partial_tail(tmp_path: Path) -> None:
    label_dir = tmp_path / "labels"
    label_dir.mkdir()
    pl.DataFrame(
        {
            "timestamp": [datetime(2021, 1, 1, tzinfo=timezone.utc)],
            "batch_id": [2],
            "target_4class": [0],
        }
    ).write_parquet(label_dir / "batch_0002.parquet")

    counts_1m = pl.DataFrame(
        {
            "batch_id": [1, 2, 3, 4],
            "n": [480, 480, 480, 120],
        }
    )

    repair_batches = _label_batches_needing_repair(
        label_dir=label_dir,
        label_batches={1, 2, 3, 4},
        counts_1m=counts_1m,
        regime="8h",
    )
    target_batches, compute_batches, missing_batches = _select_incremental_label_batches(
        label_batches={1, 2, 3, 4},
        existing_label_files=sorted(label_dir.glob("batch_*.parquet")),
        tail_batches=1,
        repair_batches=repair_batches,
    )

    assert repair_batches == {2}
    assert target_batches == {1, 2, 3, 4}
    assert compute_batches == {1, 2, 3, 4}
    assert missing_batches == [1, 3, 4]
