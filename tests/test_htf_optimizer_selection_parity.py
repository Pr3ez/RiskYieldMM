from __future__ import annotations

import numpy as np
import pandas as pd
import polars as pl
import pytest

from scripts.analysis.optimizers.rolling_rank_winsorize import (
    RollingRankWinsorizeTransformer,
    _rolling_rank_streaming_matrix_from_start,
    get_winsorize_rank_candidates,
)
from scripts.feature_engineering.htf_feature_acceptance import (
    FINAL_OUTPUT_LABEL_ONLY_COLUMNS,
)
from scripts.feature_engineering import optimize_htf_features as opt


def _reference_select_best_config(
    X: pd.DataFrame,
    y: pd.Series,
    tf: str,
    target: str,
    config: opt.HTFOptimizationConfig,
) -> dict:
    candidates = get_winsorize_rank_candidates(tf)
    target_type = "multiclass" if target in {"target_4class"} else "binary"
    n_classes = int(np.nanmax(y)) + 1 if target_type == "multiclass" else None

    best_score = -float("inf")
    best_config = candidates[0]
    best_mean_ic = 0.0
    best_std_ic = 0.0

    for cand in candidates:
        transformer = RollingRankWinsorizeTransformer(
            window=cand["window"],
            p_min=cand["p_min"],
            p_max=cand["p_max"],
            post_transform=cand["post_transform"],
        )
        mean_ic, std_ic = opt.walk_forward_validate(
            X,
            y,
            transformer,
            n_folds=config.n_val_folds,
            target_type=target_type,
            n_classes=n_classes,
        )
        score = mean_ic - config.stability_lambda * std_ic
        if score > best_score:
            best_score = score
            best_config = cand
            best_mean_ic = mean_ic
            best_std_ic = std_ic

    return {
        "config": best_config,
        "best_mean_ic": float(best_mean_ic),
        "best_std_ic": float(best_std_ic),
        "best_score": float(best_score),
        "target_type": target_type,
        "n_classes": int(n_classes) if n_classes is not None else None,
    }


def test_grouped_optimizer_selection_matches_reference() -> None:
    rng = np.random.default_rng(42)
    n_rows = 140
    base = np.linspace(0.0, 1.0, n_rows)
    X = pd.DataFrame(
        {
            "F_trend": base + rng.normal(0.0, 0.02, n_rows),
            "F_cycle": np.sin(np.linspace(0.0, 12.0, n_rows)),
            "F_noise": rng.normal(0.0, 1.0, n_rows),
            "F_sparse": np.where(np.arange(n_rows) % 11 == 0, np.nan, base),
            "F_binary_state": (np.arange(n_rows) % 2).astype(float),
        }
    )
    y = pd.Series((base * 4).astype(int).clip(0, 3), name="target_4class")
    config = opt.HTFOptimizationConfig(n_val_folds=3, stability_lambda=0.5)

    expected = _reference_select_best_config(X, y, "1m", "target_4class", config)
    actual = opt.select_best_config(X, y, "1m", "target_4class", config)

    assert actual["config"] == expected["config"]
    assert actual["target_type"] == expected["target_type"]
    assert actual["n_classes"] == expected["n_classes"]
    assert actual["best_mean_ic"] == pytest.approx(expected["best_mean_ic"], abs=1e-12)
    assert actual["best_std_ic"] == pytest.approx(expected["best_std_ic"], abs=1e-12)
    assert actual["best_score"] == pytest.approx(expected["best_score"], abs=1e-12)


def test_parallel_rank_matrix_matches_streaming_transformer() -> None:
    X = pd.DataFrame(
        {
            "F_a": [1.0, 3.0, np.nan, 2.0, 4.0, 1.5, 1.5, 5.0],
            "F_b": [10.0, np.nan, 9.0, 8.0, 8.0, 11.0, 7.0, 12.0],
            "F_state": [0.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0, 1.0],
        }
    )
    feature_cols = ["F_a", "F_b"]
    transformer = RollingRankWinsorizeTransformer(
        window=3,
        p_min=0.0,
        p_max=1.0,
        post_transform="uniform",
    )

    expected, _ = transformer.transform_streaming(
        X,
        state=None,
        feature_cols=feature_cols,
    )
    actual = _rolling_rank_streaming_matrix_from_start(
        np.ascontiguousarray(X[feature_cols].to_numpy(dtype=np.float64)),
        3,
    )

    np.testing.assert_allclose(
        actual,
        expected[feature_cols].to_numpy(dtype=np.float64),
        rtol=0.0,
        atol=0.0,
        equal_nan=True,
    )


def test_selection_signature_changes_when_early_inputs_change(tmp_path) -> None:
    features_dir = tmp_path / "features" / "1m"
    labels_dir = tmp_path / "labels" / "1m"
    optimized_dir = tmp_path / "optimized"
    features_dir.mkdir(parents=True)
    labels_dir.mkdir(parents=True)

    timestamps = pd.date_range("2021-01-01", periods=8, freq="min", tz="UTC")
    pl.DataFrame(
        {
            "timestamp": list(timestamps.to_pydatetime()),
            "batch_id": [1] * 8,
            "F_value": np.arange(8, dtype=float),
        }
    ).write_parquet(features_dir / "batch_0001.parquet")
    pl.DataFrame(
        {
            "timestamp": list(timestamps.to_pydatetime()),
            "batch_id": [1] * 8,
            "target_4class": (np.arange(8) % 4).astype(int),
        }
    ).write_parquet(labels_dir / "batch_0001.parquet")

    config = opt.HTFOptimizationConfig(
        htf_features_dir_override=tmp_path / "features",
        htf_labels_dir_override=tmp_path / "labels",
        htf_optimized_dir_override=optimized_dir,
        n_early_batches=1,
    )

    before = opt._build_selection_input_signature("1m", "target_4class", config)

    updated_timestamps = pd.date_range("2021-01-01", periods=9, freq="min", tz="UTC")
    pl.DataFrame(
        {
            "timestamp": list(updated_timestamps.to_pydatetime()),
            "batch_id": [1] * 9,
            "target_4class": (np.arange(9) % 4).astype(int),
        }
    ).write_parquet(labels_dir / "batch_0001.parquet")

    after = opt._build_selection_input_signature("1m", "target_4class", config)

    assert after != before


def test_apply_recomputes_existing_outputs_when_optimizer_config_changes(tmp_path) -> None:
    features_dir = tmp_path / "features" / "1m"
    labels_dir = tmp_path / "labels" / "1m"
    output_dir = tmp_path / "optimized" / "1m" / "target_4class"
    features_dir.mkdir(parents=True)
    labels_dir.mkdir(parents=True)
    output_dir.mkdir(parents=True)

    timestamps = pd.date_range("2021-01-01", periods=64, freq="min", tz="UTC")
    feature_file = features_dir / "batch_0001.parquet"
    label_file = labels_dir / "batch_0001.parquet"
    pl.DataFrame(
        {
            "timestamp": list(timestamps.to_pydatetime()),
            "batch_id": [1] * len(timestamps),
            "F_value": np.linspace(1.0, 2.0, len(timestamps)),
            "dist_avg_high": np.linspace(0.1, 0.2, len(timestamps)),
            "end_return": np.linspace(-0.01, 0.01, len(timestamps)),
            "target_breakfree": (np.arange(len(timestamps)) % 3).astype(int),
            "target_name": ["target_4class"] * len(timestamps),
        }
    ).write_parquet(feature_file)
    pl.DataFrame(
        {
            "timestamp": list(timestamps.to_pydatetime()),
            "batch_id": [1] * len(timestamps),
            "target_4class": (np.arange(len(timestamps)) % 4).astype(int),
        }
    ).write_parquet(label_file)
    pl.DataFrame(
        {
            "timestamp": list(timestamps.to_pydatetime()),
            "batch_id": [1] * len(timestamps),
            "F_value": np.zeros(len(timestamps)),
        }
    ).write_parquet(output_dir / "batch_0001.parquet")

    config = opt.HTFOptimizationConfig(
        htf_features_dir_override=tmp_path / "features",
        htf_labels_dir_override=tmp_path / "labels",
        htf_optimized_dir_override=tmp_path / "optimized",
        incremental_update=True,
        recompute=False,
    )
    cached_meta = {
        "config": {
            "window": 4,
            "p_min": 0.01,
            "p_max": 0.99,
            "post_transform": "uniform",
        },
        "batch_fingerprints": {
            "1": {
                "feature": opt._file_fingerprint(feature_file),
                "label": opt._file_fingerprint(label_file),
            }
        },
        "final_output_feature_policy_version": opt.FINAL_OUTPUT_FEATURE_POLICY_VERSION,
        "final_output_feature_policy_signature": opt.FINAL_OUTPUT_FEATURE_POLICY_SIGNATURE,
        "per_batch_rows": {"1": len(timestamps)},
        "per_batch_last_timestamp": {"1": timestamps[-1].isoformat()},
        "feature_cols": ["F_value"],
    }

    result = opt.apply_streaming_to_all_batches(
        tf="1m",
        target="target_4class",
        best_config={
            "window": 8,
            "p_min": 0.01,
            "p_max": 0.99,
            "post_transform": "uniform",
        },
        config=config,
        cached_meta=cached_meta,
        selected_feature_cols=["F_value"],
    )

    assert result["saved_batches"] == 1
    assert result["reused_batches"] == 0
    assert result["resume_reason"] == "full_recompute_from_1_optimizer_config"

    output_schema = set(pl.read_parquet(output_dir / "batch_0001.parquet").columns)
    assert output_schema.isdisjoint(FINAL_OUTPUT_LABEL_ONLY_COLUMNS)
