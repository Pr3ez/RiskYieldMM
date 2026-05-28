from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import polars as pl

from scripts.analysis.audit_stage1_feature_target_quality import (
    detect_leakage_feature_names,
    run_quality_audit,
)
from scripts.analysis.materialize_stage1_regression_targets import (
    DOWN_EXTREME_COL,
    DOWN_MEAN_LOW_COL,
    RAW_DISTANCE_COLS,
    UP_EXTREME_COL,
    UP_MEAN_HIGH_COL,
    VALID_COL,
)
from scripts.htf_backtest.catboost.stage1_multiasset_dataset import (
    FEATURE_TARGET_COL,
    build_context_set_hash,
    build_stage1_dataset_variant_id,
)


TARGET_COLS = (UP_EXTREME_COL, UP_MEAN_HIGH_COL, DOWN_MEAN_LOW_COL, DOWN_EXTREME_COL)


def _timestamps(rows: int) -> list[datetime]:
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    return [start + timedelta(minutes=i) for i in range(rows)]


def test_leakage_name_detector_flags_target_and_future_patterns() -> None:
    hits = detect_leakage_feature_names(
        [
            "T_BTCUSDT__M_safe_feature",
            "T_BTCUSDT__target_4class",
            "C_ES__label_window_batch_id",
            "C_GC__future_high_debug",
            "T_BTCUSDT__tb_volatility_pct",
        ]
    )

    assert {item["feature"] for item in hits} == {
        "T_BTCUSDT__target_4class",
        "C_ES__label_window_batch_id",
        "C_GC__future_high_debug",
        "T_BTCUSDT__tb_volatility_pct",
    }


def test_quality_audit_detects_feature_and_target_pathologies_without_rewrites(
    tmp_path: Path,
) -> None:
    feature_cols = [
        "T_BTCUSDT__M_good",
        "T_BTCUSDT__constant",
        "T_BTCUSDT__near_constant",
        "T_BTCUSDT__dup_a",
        "T_BTCUSDT__dup_b",
        "T_BTCUSDT__has_inf",
        "T_BTCUSDT__has_null",
        "T_BTCUSDT__target_future_debug",
    ]
    features_dir, source_label_dir = _write_synthetic_audit_dataset(tmp_path, feature_cols)
    tracked_paths = [
        *sorted(features_dir.glob("batch_*.parquet")),
        *sorted(source_label_dir.glob("batch_*.parquet")),
    ]
    mtimes_before = {path: path.stat().st_mtime_ns for path in tracked_paths}

    result = run_quality_audit(
        project_root=tmp_path,
        target_asset="BTCUSDT",
        context_assets=(),
        root_key="8h/B",
        regression_variant="distance_vol_v1",
        merged_target_col=UP_EXTREME_COL,
        output_dir=tmp_path / "audit_output",
        report_path=tmp_path / "audit.md",
        write_report=True,
        sample_rows=10,
        stability_segments=2,
    )

    assert result.status == "FAIL"
    assert result.report_path is not None and result.report_path.exists()
    assert (result.output_dir / "audit_summary.json").exists()
    assert (result.output_dir / "feature_quality.parquet").exists()
    assert (result.output_dir / "target_quality.parquet").exists()
    assert (result.output_dir / "feature_target_correlations.parquet").exists()
    assert (result.output_dir / "duplicate_feature_groups.parquet").exists()
    assert (result.output_dir / "issues.parquet").exists()

    issues = set(result.issues["check"].to_list())
    assert "feature_null_values" in issues
    assert "feature_nonfinite_values" in issues
    assert "constant_feature" in issues
    assert "duplicate_or_near_duplicate_feature_groups" in issues
    assert "suspicious_leakage_feature_name" in issues
    assert "valid_null_count" in issues
    assert "invalid_nonnull_count" in issues
    assert "distance_vol_v1_scale_design" in issues

    correlations = pl.read_parquet(result.output_dir / "feature_target_correlations.parquet")
    assert set(correlations["target_col"].unique().to_list()) == set(TARGET_COLS)
    assert correlations["feature"].n_unique() == len(feature_cols)

    mtimes_after = {path: path.stat().st_mtime_ns for path in tracked_paths}
    assert mtimes_after == mtimes_before


def _write_synthetic_audit_dataset(
    project_root: Path,
    feature_cols: list[str],
) -> tuple[Path, Path]:
    target_asset = "BTCUSDT"
    context_hash = build_context_set_hash(target_asset=target_asset, context_assets=())
    variant_id = build_stage1_dataset_variant_id(
        target_col=UP_EXTREME_COL,
        include_ta_flags=False,
    )
    root_dir = (
        project_root
        / "data"
        / "htf_multiasset_merged"
        / "btcusdt"
        / context_hash
        / variant_id
        / "8h_b"
    )
    features_dir = root_dir / "features" / "1m" / FEATURE_TARGET_COL
    labels_dir = root_dir / "labels" / "1m"
    source_label_dir = (
        project_root
        / "data"
        / "htf_multiasset"
        / "btcusdt"
        / "htf_4class_labels_reg_distance_vol_v1"
        / "1m"
    )
    features_dir.mkdir(parents=True)
    labels_dir.mkdir(parents=True)
    source_label_dir.mkdir(parents=True)

    ts = _timestamps(6)
    for batch_id, start in ((1, 0), (3, 3)):
        part_ts = ts[start : start + 3]
        feature_df = pl.DataFrame(
            {
                "timestamp": part_ts,
                "batch_id": [batch_id] * 3,
                "T_BTCUSDT__M_good": [1.0 + start, 2.0 + start, 3.0 + start],
                "T_BTCUSDT__constant": [7.0, 7.0, 7.0],
                "T_BTCUSDT__near_constant": [0.0, 0.0, 0.0],
                "T_BTCUSDT__dup_a": [0.1, 0.2, 0.3],
                "T_BTCUSDT__dup_b": [0.1, 0.2, 0.3],
                "T_BTCUSDT__has_inf": [1.0, float("inf"), 3.0],
                "T_BTCUSDT__has_null": [1.0, None, 3.0],
                "T_BTCUSDT__target_future_debug": [0.5, 0.6, 0.7],
            }
        )
        feature_df.write_parquet(features_dir / f"batch_{batch_id:04d}.parquet")
        pl.DataFrame(
            {
                "timestamp": part_ts,
                "batch_id": [batch_id] * 3,
                UP_EXTREME_COL: [1.0, 2.0, 3.0],
            }
        ).write_parquet(labels_dir / f"batch_{batch_id:04d}.parquet")
        _source_labels(part_ts, batch_id).write_parquet(
            source_label_dir / f"batch_{batch_id:04d}.parquet"
        )

    pl.DataFrame(
        {
            "stage1_available_pos": [0, 1],
            "batch_id": [1, 3],
            "batch_start_ts": [ts[0], ts[3]],
            "batch_end_ts": [ts[2], ts[5]],
            "row_count": [3, 3],
            "valid_row_count": [3, 3],
            "target_col": [UP_EXTREME_COL, UP_EXTREME_COL],
            "feature_target_col": [FEATURE_TARGET_COL, FEATURE_TARGET_COL],
        }
    ).write_parquet(root_dir / "stage1_batch_index.parquet")
    manifest = {
        "target_asset": target_asset,
        "context_assets": [],
        "context_hash": context_hash,
        "dataset_variant_id": variant_id,
        "root": "8h/B",
        "root_id": "8h_b",
        "target_col": UP_EXTREME_COL,
        "feature_target_col": FEATURE_TARGET_COL,
        "output_rows": 6,
        "stage1_batch_index_rows": 2,
        "duplicate_count": 0,
        "null_feature_count": 0,
        "feature_columns": feature_cols,
        "feature_columns_count": len(feature_cols),
        "output_paths": {
            "features_dir": str(root_dir / "features"),
            "labels_dir": str(root_dir / "labels"),
            "stage1_batch_index": str(root_dir / "stage1_batch_index.parquet"),
        },
    }
    (root_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return features_dir, source_label_dir


def _source_labels(timestamps: list[datetime], batch_id: int) -> pl.DataFrame:
    valid = [True, True, False]
    vol = [0.02, 0.02, 0.02]
    raw_up_extreme = [0.02, 0.04, 0.06]
    raw_up_mean = [0.01, 0.02, 0.03]
    raw_down_mean = [0.005, 0.01, 0.015]
    raw_down_extreme = [0.015, 0.03, 0.045]
    return pl.DataFrame(
        {
            "timestamp": timestamps,
            "batch_id": [batch_id] * len(timestamps),
            VALID_COL: valid,
            "target_reg_distance_reason_v1": ["ok", "ok", "not_label_half"],
            "target_reg_distance_future_bars_v1": [2, 2, 0],
            "tb_volatility_pct": vol,
            "tb_atr_pct_14": vol,
            "tb_realized_vol_120": [0.01, 0.01, 0.01],
            UP_EXTREME_COL: [raw_up_extreme[0] / vol[0], None, 99.0],
            UP_MEAN_HIGH_COL: [raw_up_mean[0] / vol[0], raw_up_mean[1] / vol[1], None],
            DOWN_MEAN_LOW_COL: [raw_down_mean[0] / vol[0], raw_down_mean[1] / vol[1], None],
            DOWN_EXTREME_COL: [raw_down_extreme[0] / vol[0], raw_down_extreme[1] / vol[1], None],
            RAW_DISTANCE_COLS[0]: raw_up_extreme,
            RAW_DISTANCE_COLS[1]: raw_up_mean,
            RAW_DISTANCE_COLS[2]: raw_down_mean,
            RAW_DISTANCE_COLS[3]: raw_down_extreme,
        }
    )
