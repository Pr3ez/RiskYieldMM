from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import polars as pl

from scripts.analysis.materialize_stage1_regression_targets import (
    DOWN_EXTREME_HVOL_V2_COL,
    DOWN_EXTREME_COL,
    DOWN_MEAN_LOW_HVOL_V2_COL,
    DOWN_MEAN_LOW_COL,
    HORIZON_MINUTES_COL_V2,
    HORIZON_VOL_COL_V2,
    REGRESSION_VARIANT,
    REGRESSION_VARIANT_HORIZON_VOL_V2,
    UP_EXTREME_HVOL_V2_COL,
    UP_EXTREME_COL,
    UP_MEAN_HIGH_HVOL_V2_COL,
    UP_MEAN_HIGH_COL,
    VALID_COL,
    VALID_COL_V2,
    compute_distance_regression_targets,
    materialize_regression_targets,
    scan_distance_regression_targets,
    target_cols_for_variant,
)
from scripts.analysis.materialize_stage1_target_variants import (
    compute_prediction_time_indicators,
)
from scripts.analysis.validate_stage1_regression_targets import (
    validate_regression_target_root,
)
from scripts.htf_backtest.catboost.stage1_multiasset_dataset import (
    build_multiasset_stage1_dataset,
)


def _timestamps(rows: int) -> list[datetime]:
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    return [start + timedelta(minutes=i) for i in range(rows)]


def test_distance_scan_computes_positive_excursion_targets() -> None:
    rows = pl.DataFrame(
        {
            "close": [100.0],
            "tb_volatility_pct": [0.02],
            "label_window_batch_id": [10],
            "is_label_half": [True],
        }
    )
    windows = {
        10: {
            "high": pl.Series([101.0, 103.0]).to_numpy(),
            "low": pl.Series([99.0, 95.0]).to_numpy(),
            "timestamp": _timestamps(2),
        }
    }

    out = scan_distance_regression_targets(rows, windows)

    assert out[VALID_COL] == [True]
    assert out[UP_EXTREME_COL][0] == pytest.approx(1.5)
    assert out[UP_MEAN_HIGH_COL][0] == pytest.approx(1.0)
    assert out[DOWN_MEAN_LOW_COL][0] == pytest.approx(1.5)
    assert out[DOWN_EXTREME_COL][0] == pytest.approx(2.5)


def test_distance_scan_marks_invalid_rows_with_null_targets() -> None:
    rows = pl.DataFrame(
        {
            "close": [100.0, 100.0],
            "tb_volatility_pct": [0.02, 0.02],
            "label_window_batch_id": [10, 999],
            "is_label_half": [False, True],
        }
    )
    windows = {
        10: {
            "high": pl.Series([101.0]).to_numpy(),
            "low": pl.Series([99.0]).to_numpy(),
            "timestamp": _timestamps(1),
        }
    }

    out = scan_distance_regression_targets(rows, windows)

    assert out[VALID_COL] == [False, False]
    assert out[UP_EXTREME_COL] == [None, None]
    assert out["target_reg_distance_reason_v1"] == [
        "not_label_half",
        "missing_label_window",
    ]


def test_target_columns_share_one_regression_variant() -> None:
    assert target_cols_for_variant(REGRESSION_VARIANT) == (
        UP_EXTREME_COL,
        UP_MEAN_HIGH_COL,
        DOWN_MEAN_LOW_COL,
        DOWN_EXTREME_COL,
    )
    assert target_cols_for_variant(REGRESSION_VARIANT_HORIZON_VOL_V2) == (
        UP_EXTREME_HVOL_V2_COL,
        UP_MEAN_HIGH_HVOL_V2_COL,
        DOWN_MEAN_LOW_HVOL_V2_COL,
        DOWN_EXTREME_HVOL_V2_COL,
    )


def test_horizon_vol_v2_normalizes_by_future_window_horizon() -> None:
    rows = pl.DataFrame(
        {
            "close": [100.0],
            "tb_volatility_pct": [0.02],
            "label_window_batch_id": [10],
            "is_label_half": [True],
        }
    )
    windows = {
        10: {
            "high": pl.Series([101.0, 103.0]).to_numpy(),
            "low": pl.Series([99.0, 95.0]).to_numpy(),
            "timestamp": _timestamps(2),
        }
    }

    out = scan_distance_regression_targets(
        rows,
        windows,
        variant=REGRESSION_VARIANT_HORIZON_VOL_V2,
    )
    denominator = 0.02 * (30.0 ** 0.5)

    assert out[VALID_COL_V2] == [True]
    assert out[HORIZON_MINUTES_COL_V2] == [30.0]
    assert out[HORIZON_VOL_COL_V2][0] == pytest.approx(denominator)
    assert out[UP_EXTREME_HVOL_V2_COL][0] == pytest.approx(0.03 / denominator)
    assert out[UP_MEAN_HIGH_HVOL_V2_COL][0] == pytest.approx(0.02 / denominator)
    assert out[DOWN_MEAN_LOW_HVOL_V2_COL][0] == pytest.approx(0.03 / denominator)
    assert out[DOWN_EXTREME_HVOL_V2_COL][0] == pytest.approx(0.05 / denominator)


def test_volatility_inputs_match_existing_triple_barrier_causal_logic() -> None:
    ts = _timestamps(130)
    rows = pl.DataFrame(
        {
            "timestamp": ts,
            "open": [100.0 + i * 0.01 for i in range(130)],
            "high": [100.2 + i * 0.01 for i in range(130)],
            "low": [99.8 + i * 0.01 for i in range(130)],
            "close": [100.0 + i * 0.01 for i in range(130)],
            "batch_id": [1] * 130,
            "label_window_batch_id": [10] * 130,
            "is_label_half": [True] * 130,
        }
    )
    window = pl.DataFrame(
        {
            "timestamp": [ts[-1] + timedelta(minutes=15 * i) for i in range(2)],
            "high": [101.0, 104.0],
            "low": [99.0, 97.0],
            "batch_id": [10, 10],
            "family_bar_pos": [0, 1],
            "is_label_half": [True, True],
        }
    )

    expected = compute_prediction_time_indicators(rows)
    labeled = compute_distance_regression_targets(rows, window)

    assert labeled["tb_volatility_pct"].tail(10).to_list() == pytest.approx(
        expected["tb_volatility_pct"].tail(10).to_list()
    )


def test_materializer_writes_common_regression_root_without_overwriting_legacy(
    tmp_path: Path,
) -> None:
    asset_root = tmp_path / "data" / "htf_multiasset" / "btcusdt"
    label_dir = asset_root / "htf_4class_labels" / "1m"
    window_dir = asset_root / "htf_backtest_shift4h"
    label_dir.mkdir(parents=True)
    window_dir.mkdir(parents=True)

    ts = _timestamps(130)
    pl.DataFrame(
        {
            "timestamp": ts,
            "open": [100.0 + i * 0.01 for i in range(130)],
            "high": [100.2 + i * 0.01 for i in range(130)],
            "low": [99.8 + i * 0.01 for i in range(130)],
            "close": [100.0 + i * 0.01 for i in range(130)],
            "volume": [1.0] * 130,
            "batch_id": [1] * 130,
            "target_4class": [i % 4 for i in range(130)],
            "target_name": ["UP_BALANCED"] * 130,
            "label_window_batch_id": [10] * 130,
            "label_window_start": [ts[-1] + timedelta(minutes=1)] * 130,
            "label_window_end": [ts[-1] + timedelta(hours=4)] * 130,
            "label_window_policy": ["opposite_family_first_half"] * 130,
            "label_entry_family": ["B"] * 130,
            "label_window_family": ["C"] * 130,
            "is_label_half": [True] * 130,
        }
    ).write_parquet(label_dir / "batch_0001.parquet")
    pl.DataFrame(
        {
            "timestamp": [ts[-1] + timedelta(minutes=15 * i) for i in range(4)],
            "high": [101.0, 103.0, 102.0, 104.0],
            "low": [99.5, 98.0, 97.5, 99.0],
            "batch_id": [10] * 4,
            "family_bar_pos": [0, 1, 2, 3],
            "is_label_half": [True] * 4,
        }
    ).write_parquet(window_dir / "15m_HTF_combined.parquet")

    summaries = materialize_regression_targets(
        project_root=tmp_path,
        assets=("BTCUSDT",),
        roots=("8h/B",),
        variant=REGRESSION_VARIANT,
    )

    out_path = (
        asset_root
        / "htf_4class_labels_reg_distance_vol_v1"
        / "1m"
        / "batch_0001.parquet"
    )
    assert out_path.exists()
    assert (label_dir / "batch_0001.parquet").exists()
    out = pl.read_parquet(out_path)
    assert set(target_cols_for_variant()).issubset(out.columns)
    assert out.select(["timestamp", "batch_id"]).unique().height == out.height
    assert out.filter(pl.col(VALID_COL)).height > 0
    assert summaries[0].output_dir == out_path.parent

    validation = validate_regression_target_root(
        project_root=tmp_path,
        asset_id="BTCUSDT",
        root_key="8h/B",
    )
    assert validation.status == "PASS"
    assert validation.counters["rows"] == 130
    assert validation.raw_recompute[
        "target_reg_distance_up_extreme_pct_v1"
    ]["violations_gt_1e_12"] == 0

    v2_summaries = materialize_regression_targets(
        project_root=tmp_path,
        assets=("BTCUSDT",),
        roots=("8h/B",),
        variant=REGRESSION_VARIANT_HORIZON_VOL_V2,
    )
    v2_path = (
        asset_root
        / "htf_4class_labels_reg_distance_horizon_vol_v2"
        / "1m"
        / "batch_0001.parquet"
    )
    assert v2_path.exists()
    assert out_path.exists()
    v2 = pl.read_parquet(v2_path)
    assert set(target_cols_for_variant(REGRESSION_VARIANT_HORIZON_VOL_V2)).issubset(v2.columns)
    assert v2.filter(pl.col(VALID_COL_V2)).height > 0
    assert v2_summaries[0].output_dir == v2_path.parent
    v2_validation = validate_regression_target_root(
        project_root=tmp_path,
        asset_id="BTCUSDT",
        root_key="8h/B",
        variant=REGRESSION_VARIANT_HORIZON_VOL_V2,
    )
    assert v2_validation.status == "PASS"
    assert v2_validation.counters["horizon_minutes_mismatch"] == 0
    assert v2_validation.counters["horizon_vol_mismatch"] == 0


def test_stage1_assembly_reads_regression_target_from_common_root(tmp_path: Path) -> None:
    asset_root = tmp_path / "data" / "htf_multiasset" / "btcusdt"
    feature_dir = asset_root / "htf_with_helpers" / "1m" / "target_4class"
    label_dir = asset_root / "htf_4class_labels_reg_distance_vol_v1" / "1m"
    feature_dir.mkdir(parents=True)
    label_dir.mkdir(parents=True)
    ts = _timestamps(3)

    pl.DataFrame(
        {
            "timestamp": ts,
            "batch_id": [1, 1, 1],
            "open": [1.0, 2.0, 3.0],
            "close": [1.0, 2.0, 3.0],
            "bar_in_batch_norm": [0.1, 0.2, 0.3],
            "target_4class": [0, 1, 2],
        }
    ).write_parquet(feature_dir / "batch_0001.parquet")
    pl.DataFrame(
        {
            "timestamp": ts,
            "batch_id": [1, 1, 1],
            UP_EXTREME_COL: [1.0, None, 2.5],
            VALID_COL: [True, False, True],
        }
    ).write_parquet(label_dir / "batch_0001.parquet")

    result = build_multiasset_stage1_dataset(
        project_root=tmp_path,
        target_asset="BTCUSDT",
        context_assets=(),
        root_key="8h/B",
        target_col=UP_EXTREME_COL,
        feature_target_col="target_4class",
    )

    labels = pl.read_parquet(result.labels_dir / "1m" / "batch_0001.parquet")

    assert result.manifest["target_col"] == UP_EXTREME_COL
    assert result.manifest["feature_target_col"] == "target_4class"
    assert result.manifest["dataset_variant_id"] == "target_reg_distance_up_extreme_vol_v1"
    assert labels[UP_EXTREME_COL].to_list() == [1.0, None, 2.5]


def test_stage1_assembly_reads_horizon_vol_v2_root(tmp_path: Path) -> None:
    asset_root = tmp_path / "data" / "htf_multiasset" / "btcusdt"
    feature_dir = asset_root / "htf_with_helpers" / "1m" / "target_4class"
    label_dir = asset_root / "htf_4class_labels_reg_distance_horizon_vol_v2" / "1m"
    feature_dir.mkdir(parents=True)
    label_dir.mkdir(parents=True)
    ts = _timestamps(3)

    pl.DataFrame(
        {
            "timestamp": ts,
            "batch_id": [1, 1, 1],
            "close": [1.0, 2.0, 3.0],
            "bar_in_batch_norm": [0.1, 0.2, 0.3],
            "target_4class": [0, 1, 2],
        }
    ).write_parquet(feature_dir / "batch_0001.parquet")
    pl.DataFrame(
        {
            "timestamp": ts,
            "batch_id": [1, 1, 1],
            UP_EXTREME_HVOL_V2_COL: [0.5, None, 1.5],
            VALID_COL_V2: [True, False, True],
        }
    ).write_parquet(label_dir / "batch_0001.parquet")

    result = build_multiasset_stage1_dataset(
        project_root=tmp_path,
        target_asset="BTCUSDT",
        context_assets=(),
        root_key="8h/B",
        target_col=UP_EXTREME_HVOL_V2_COL,
        feature_target_col="target_4class",
    )

    labels = pl.read_parquet(result.labels_dir / "1m" / "batch_0001.parquet")

    assert result.manifest["target_col"] == UP_EXTREME_HVOL_V2_COL
    assert result.manifest["dataset_variant_id"] == "target_reg_distance_up_extreme_hvol_v2"
    assert labels[UP_EXTREME_HVOL_V2_COL].to_list() == [0.5, None, 1.5]
