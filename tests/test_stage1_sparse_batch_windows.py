from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import polars as pl
import pytest

from scripts.htf_backtest.catboost import stage1_optimizer
from scripts.htf_backtest.catboost.stage1_optimizer import evaluate_stage1_grid

pytest.importorskip("catboost")

from scripts.htf_backtest.catboost.tf_1m import (
    Config1m,
    FeatureSpace1m,
    ModelSpace1m,
    StepOptimizer1m,
    WindowSpace1m,
)
from scripts.htf_backtest.catboost.utils import (
    build_stage1_batch_index,
    get_batch_count,
    get_valid_batches,
    load_batches_by_ids,
)


def _write_batch(root: Path, batch_id: int, rows: int = 8) -> None:
    start = datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(hours=batch_id)
    timestamps = [start + timedelta(minutes=i) for i in range(rows)]
    feature_dir = root / "features" / "1m" / "target_4class"
    label_dir = root / "labels" / "1m"
    feature_dir.mkdir(parents=True, exist_ok=True)
    label_dir.mkdir(parents=True, exist_ok=True)
    labels = [i % 4 for i in range(rows)]
    pl.DataFrame(
        {
            "timestamp": timestamps,
            "batch_id": [batch_id] * rows,
            "feature_a": [float(batch_id + i) for i in range(rows)],
            "feature_b": [float(i % 3) for i in range(rows)],
            "bar_in_batch_norm": [float(i + 1) / rows for i in range(rows)],
        }
    ).write_parquet(feature_dir / f"batch_{batch_id:04d}.parquet")
    pl.DataFrame(
        {
            "timestamp": timestamps,
            "batch_id": [batch_id] * rows,
            "target_4class": labels,
        }
    ).write_parquet(label_dir / f"batch_{batch_id:04d}.parquet")


def test_sparse_batch_index_uses_actual_files_not_numeric_span(tmp_path: Path) -> None:
    for batch_id in (10, 11, 20):
        _write_batch(tmp_path, batch_id=batch_id)

    assert get_batch_count(tmp_path / "labels", "1m") == 20
    assert get_valid_batches(
        tmp_path / "features",
        tmp_path / "labels",
        "1m",
        min_rows=1,
    ) == [10, 11, 20]

    index = build_stage1_batch_index(
        tmp_path / "features",
        tmp_path / "labels",
        "1m",
        batch_ids=[10, 11, 20],
    )
    assert index["stage1_available_pos"].to_list() == [0, 1, 2]
    assert index["batch_id"].to_list() == [10, 11, 20]

    loaded = load_batches_by_ids(
        tmp_path / "features",
        tmp_path / "labels",
        "1m",
        [11, 20],
    )
    assert loaded["batch_id"].unique().sort().to_list() == [11, 20]


def test_fold_windows_count_available_batches_not_numeric_ids() -> None:
    optimizer = StepOptimizer1m(
        config=Config1m(),
        window_space=WindowSpace1m(
            window_selection_mode="stage1_fold_cv",
            embargo_mode="none",
        ),
        feature_space=FeatureSpace1m(),
        model_space=ModelSpace1m(),
    )
    available = [10, 11, 20, 21]
    positions = {batch_id: pos for pos, batch_id in enumerate([10, 11, 20, 21, 40])}

    windows = optimizer._build_stage1_fold_windows(
        train_end=21,
        fold_count=1,
        train_batches_per_fold=2,
        val_batches_per_fold=1,
        min_batch=10,
        available_batches=available,
        batch_positions=positions,
        pred_pos=4,
    )

    assert len(windows) == 1
    assert windows[0]["train_batch_ids"] == [11, 20]
    assert windows[0]["val_batch_ids"] == [21]
    assert windows[0]["train_start_pos"] == 1
    assert windows[0]["train_end_pos"] == 2
    assert windows[0]["val_start_pos"] == 3
    assert windows[0]["pred_pos"] == 4
    assert windows[0]["window_is_sparse"] is True


def test_stage1_grid_handles_sparse_train_windows_without_missing_batch(
    tmp_path: Path,
    monkeypatch,
) -> None:
    for batch_id in (10, 11, 20, 21, 40):
        _write_batch(tmp_path, batch_id=batch_id, rows=30)

    class _DummyModel:
        classes_ = np.array([0, 1, 2, 3])

        def predict_proba(self, x):
            out = np.full((len(x), 4), 0.10, dtype=float)
            out[:, 0] = 0.40
            out[:, 2] = 0.40
            return out

    monkeypatch.setattr(
        stage1_optimizer,
        "fit_catboost_with_fallback_stage1",
        lambda **_: (_DummyModel(), False),
    )

    step_optimizer = StepOptimizer1m(
        config=Config1m(
            features_dir_override=tmp_path / "features",
            labels_dir_override=tmp_path / "labels",
        ),
        window_space=WindowSpace1m(
            window_selection_mode="stage1_fold_cv",
            embargo_mode="none",
        ),
        feature_space=FeatureSpace1m(),
        model_space=ModelSpace1m(num_boost_round_min=10, num_boost_round_max=10),
    )
    available = [10, 11, 20, 21, 40]
    positions = {batch_id: pos for pos, batch_id in enumerate(available)}

    result = evaluate_stage1_grid(
        step_optimizer=step_optimizer,
        train_end=21,
        pred_batch=40,
        step_stage1_dir=tmp_path / "stage1",
        available_batch_ids=available,
        batch_positions=positions,
        pred_pos=4,
        combo_grid_override=[
            {
                "fold_count": 1,
                "val_batches_per_fold": 1,
                "train_batches_per_fold": 2,
                "action_key": "f1_v1_t2",
            }
        ],
    )

    summary = result["summary"]
    assert summary["combo_count_completed"] == 1
    assert not any("missing_batch" in key for key in summary["fail_reasons"])

    fold_windows = pl.read_parquet(tmp_path / "stage1" / "stage1_fold_windows.parquet")
    assert fold_windows["train_batch_ids"].to_list() == [[11, 20]]
    assert fold_windows["val_batch_ids"].to_list() == [[21]]
    assert fold_windows["window_is_sparse"].to_list() == [True]
