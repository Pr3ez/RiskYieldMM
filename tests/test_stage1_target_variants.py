from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import polars as pl

from scripts.analysis.materialize_stage1_target_variants import (
    _scan_barriers,
    materialize_target_variants,
    parse_variants,
    target_col_for_variant,
    variant_spec,
)
from scripts.htf_backtest.catboost.stage1_multiasset_dataset import (
    build_multiasset_stage1_dataset,
)


def _timestamps(rows: int) -> list[datetime]:
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    return [start + timedelta(minutes=i) for i in range(rows)]


def test_triple_barrier_scan_assigns_four_class_outcomes() -> None:
    rows = pl.DataFrame(
        {
            "close": [100.0, 100.0, 100.0, 100.0],
            "close_end": [101.0, 101.0, 103.0, 101.0],
            "tb_upper_barrier": [105.0, 105.0, 105.0, 105.0],
            "tb_lower_barrier": [95.0, 95.0, 95.0, 95.0],
            "tb_volatility_pct": [0.10, 0.10, 0.10, 0.10],
            "label_window_batch_id": [1, 2, 3, 4],
            "is_label_half": [True, True, True, True],
        }
    )
    windows = {
        1: {
            "high": pl.Series([106.0]).to_numpy(),
            "low": pl.Series([99.0]).to_numpy(),
            "close": pl.Series([101.0]).to_numpy(),
        },
        2: {
            "high": pl.Series([101.0]).to_numpy(),
            "low": pl.Series([94.0]).to_numpy(),
            "close": pl.Series([99.0]).to_numpy(),
        },
        3: {
            "high": pl.Series([102.0]).to_numpy(),
            "low": pl.Series([98.0]).to_numpy(),
            "close": pl.Series([103.0]).to_numpy(),
        },
        4: {
            "high": pl.Series([106.0]).to_numpy(),
            "low": pl.Series([94.0]).to_numpy(),
            "close": pl.Series([101.0]).to_numpy(),
        },
    }

    result = _scan_barriers(rows, windows)

    assert result["target"].tolist() == [3, 1, 2, -1]
    assert result["first_hit"].tolist() == ["upper", "lower", "terminal", "both_same_bar"]
    assert result["same_bar_both_hit"].tolist() == [False, False, False, True]


def test_wide_atr_variant_is_available_for_target_survey() -> None:
    assert "tb_atr_wide_v2" in parse_variants("all")
    assert target_col_for_variant("tb_atr_wide_v2") == "target_4class_tb_atr_wide_v2"
    spec = variant_spec("tb_atr_wide_v2")
    assert spec["barrier_mode"] == "atr"
    assert spec["k_up"] == 15.0
    assert spec["k_down"] == 15.0
    assert spec["terminal_theta"] == 0.0


def test_materializer_writes_variant_label_root_without_overwriting_legacy(tmp_path: Path) -> None:
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
            "target_breakfree": [2] * 130,
            "label_window_batch_id": [10] * 130,
            "label_window_start": [ts[-1] + timedelta(minutes=1)] * 130,
            "label_window_end": [ts[-1] + timedelta(hours=4)] * 130,
            "label_window_policy": ["opposite_family_first_half"] * 130,
            "label_entry_family": ["B"] * 130,
            "label_window_family": ["C"] * 130,
            "is_label_half": [True] * 130,
            "close_end": [103.0] * 130,
        }
    ).write_parquet(label_dir / "batch_0001.parquet")
    pl.DataFrame(
        {
            "timestamp": [ts[-1] + timedelta(minutes=15 * i) for i in range(4)],
            "open": [100.0, 100.5, 101.0, 101.5],
            "high": [100.5, 101.0, 106.0, 106.5],
            "low": [99.5, 100.0, 100.5, 101.0],
            "close": [100.4, 100.8, 105.5, 106.0],
            "volume": [1.0] * 4,
            "batch_id": [10] * 4,
            "family_bar_pos": [0, 1, 2, 3],
            "is_label_half": [True] * 4,
        }
    ).write_parquet(window_dir / "15m_HTF_combined.parquet")

    summaries = materialize_target_variants(
        project_root=tmp_path,
        assets=("BTCUSDT",),
        roots=("8h/B",),
        variants=("tb_atr_v1",),
    )

    target_col = target_col_for_variant("tb_atr_v1")
    out_path = asset_root / "htf_4class_labels_tb_atr_v1" / "1m" / "batch_0001.parquet"
    assert out_path.exists()
    assert (label_dir / "batch_0001.parquet").exists()
    out = pl.read_parquet(out_path)
    assert target_col in out.columns
    assert f"{target_col}_name" in out.columns
    assert "tb_first_hit" in out.columns
    assert set(out[target_col].unique().to_list()).issubset({-1, 0, 1, 2, 3})
    assert summaries[0].output_dir == out_path.parent


def test_stage1_assembly_uses_non_default_target_root_and_keeps_feature_source(
    tmp_path: Path,
) -> None:
    asset_root = tmp_path / "data" / "htf_multiasset" / "btcusdt"
    feature_dir = asset_root / "htf_with_helpers" / "1m" / "target_4class"
    label_dir = asset_root / "htf_4class_labels_tb_atr_v1" / "1m"
    feature_dir.mkdir(parents=True)
    label_dir.mkdir(parents=True)
    ts = _timestamps(3)
    target_col = target_col_for_variant("tb_atr_v1")

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
            target_col: [3, 2, 1],
            f"{target_col}_name": ["UP_EXPANSION", "UP_BALANCED", "DOWN_EXPANSION"],
        }
    ).write_parquet(label_dir / "batch_0001.parquet")

    result = build_multiasset_stage1_dataset(
        project_root=tmp_path,
        target_asset="BTCUSDT",
        context_assets=(),
        root_key="8h/B",
        target_col=target_col,
        feature_target_col="target_4class",
    )

    features = pl.read_parquet(
        result.features_dir / "1m" / "target_4class" / "batch_0001.parquet"
    )
    labels = pl.read_parquet(result.labels_dir / "1m" / "batch_0001.parquet")

    assert result.manifest["target_col"] == target_col
    assert result.manifest["feature_target_col"] == "target_4class"
    assert result.manifest["dataset_variant_id"] == "target_tb_atr_v1"
    assert "target_tb_atr_v1" in result.run_id
    assert "target_tb_atr_v1" in str(result.manifest_path)
    assert "T_BTCUSDT__open" in features.columns
    assert labels[target_col].to_list() == [3, 2, 1]
