from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import polars as pl

from scripts.analysis.htf_stage1_label_anomaly_experiment import (
    TARGET_COL,
    apply_anomaly_decisions,
    assign_chronological_splits,
    collapse_8_to_4,
    compute_eval_metrics,
    export_review_set,
    make_expanding_oof_folds,
    select_train_variance_features,
)


def test_chronological_splits_and_oof_folds_are_time_ordered() -> None:
    meta = pd.DataFrame(
        {
            "batch_id": list(range(1, 21)),
            "feature_path": [f"batch_{i:04d}.parquet" for i in range(1, 21)],
            "label_path": [f"batch_{i:04d}.parquet" for i in range(1, 21)],
            "feature_rows": [10] * 20,
        }
    )

    split_meta, train_batches, val_batches, test_batches = assign_chronological_splits(meta)

    assert max(train_batches) < min(val_batches)
    assert max(val_batches) < min(test_batches)
    assert split_meta["split"].value_counts().to_dict() == {
        "train": 12,
        "val": 4,
        "test": 4,
    }

    folds = make_expanding_oof_folds(
        train_batches,
        n_folds=3,
        min_train_batches=4,
    )

    assert folds
    for _fold_id, fold_train, fold_val in folds:
        assert int(fold_train.max()) < int(fold_val.min())
        assert set(fold_train).isdisjoint(set(fold_val))


def test_train_variance_feature_selection_ignores_future_batches(tmp_path) -> None:
    train_path = tmp_path / "batch_0001.parquet"
    val_path = tmp_path / "batch_0002.parquet"
    pl.DataFrame(
        {
            "train_var": [0.0, 10.0, 20.0],
            "future_only_var": [1.0, 1.0, 1.0],
        }
    ).write_parquet(train_path)
    pl.DataFrame(
        {
            "train_var": [2.0, 2.0, 2.0],
            "future_only_var": [0.0, 1000.0, 2000.0],
        }
    ).write_parquet(val_path)
    meta = pd.DataFrame(
        {
            "feature_path": [str(train_path), str(val_path)],
            "split": ["train", "val"],
        }
    )

    selected = select_train_variance_features(
        meta,
        ["train_var", "future_only_var"],
        max_features=1,
    )

    assert selected.index.to_list() == ["train_var"]


def test_anomaly_decisions_never_auto_relabel_opposite_direction() -> None:
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    score_df = pd.DataFrame(
        {
            "row_id": [1, 2, 3, 4],
            "timestamp": [start + timedelta(minutes=i) for i in range(4)],
            "batch_id": [10, 10, 10, 10],
            TARGET_COL: [0, 0, 0, 0],
            "pred_label": [1, 2, 2, 0],
            "model_confidence": [0.70, 0.95, 0.60, 0.40],
            "noise_score": [0.90, 0.85, 0.80, 0.10],
            "prob_0": [0.2, 0.1, 0.2, 0.8],
            "prob_1": [0.6, 0.1, 0.2, 0.1],
            "prob_2": [0.1, 0.7, 0.5, 0.05],
            "prob_3": [0.1, 0.1, 0.1, 0.05],
            "temporal_inconsistency": [0.1, 0.9, 0.7, 0.0],
            "class_conditional_outlier_score": [0.3, 0.8, 0.7, 0.1],
        }
    )

    decisions = apply_anomaly_decisions(
        score_df,
        threshold_pct=0.75,
        opposite_policy="exclude_review",
        opposite_high_confidence=0.80,
    )

    same_direction = decisions.loc[decisions["row_id"] == 1].iloc[0]
    high_conf_opposite = decisions.loc[decisions["row_id"] == 2].iloc[0]
    low_conf_opposite = decisions.loc[decisions["row_id"] == 3].iloc[0]

    assert same_direction["training_action"] == "same_parent_anomaly"
    assert int(same_direction["target_8class_anomaly"]) == 4

    assert high_conf_opposite["training_action"] == "review_exclude"
    assert int(high_conf_opposite["target_8class_anomaly"]) == 0
    assert float(high_conf_opposite["sample_weight_anomaly"]) == 0.0

    assert low_conf_opposite["training_action"] == "low_weight_opposite"
    assert int(low_conf_opposite["target_8class_anomaly"]) == 0
    assert float(low_conf_opposite["sample_weight_anomaly"]) == 0.35


def test_collapsed_4_metrics_are_primary_for_anomaly_leaves() -> None:
    y_true = np.array([0, 1, 2, 3])
    pred_leaf = np.array([4, 5, 6, 7])
    proba8 = np.zeros((4, 8), dtype=float)
    proba8[np.arange(4), pred_leaf] = 1.0

    metrics, _bins = compute_eval_metrics(y_true, pred_leaf, proba8)

    assert collapse_8_to_4(pred_leaf).tolist() == [0, 1, 2, 3]
    assert metrics["collapsed_4_accuracy"] == 1.0
    assert metrics["cross_direction_error"] == 0.0


def test_review_set_export_contains_required_columns_and_no_duplicates(tmp_path) -> None:
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    score_df = pd.DataFrame(
        {
            "row_id": [1, 2, 3, 4],
            "timestamp": [start + timedelta(minutes=i) for i in range(4)],
            "batch_id": [10, 10, 10, 10],
            TARGET_COL: [0, 0, 0, 0],
            "pred_label": [1, 2, 2, 0],
            "model_confidence": [0.70, 0.95, 0.60, 0.40],
            "noise_score": [0.90, 0.85, 0.80, 0.10],
            "prob_0": [0.2, 0.1, 0.2, 0.8],
            "prob_1": [0.6, 0.1, 0.2, 0.1],
            "prob_2": [0.1, 0.7, 0.5, 0.05],
            "prob_3": [0.1, 0.1, 0.1, 0.05],
            "temporal_inconsistency": [0.1, 0.9, 0.7, 0.0],
            "class_conditional_outlier_score": [0.3, 0.8, 0.7, 0.1],
        }
    )
    decisions = apply_anomaly_decisions(
        score_df,
        threshold_pct=0.75,
        opposite_policy="exclude_review",
        opposite_high_confidence=0.80,
    )

    config = type(
        "Config",
        (),
        {"config_id": "test_config"},
    )()
    manifest = export_review_set(decisions, output_dir=tmp_path, config=config)
    review = pd.read_parquet(manifest["parquet_path"])

    required = {
        "timestamp",
        "batch_id",
        TARGET_COL,
        "pred_label",
        "prob_0",
        "prob_1",
        "prob_2",
        "prob_3",
        "model_confidence",
        "noise_score",
        "temporal_inconsistency",
        "class_conditional_outlier_score",
        "training_action",
    }
    assert required.issubset(set(review.columns))
    assert not review.duplicated(["timestamp", "batch_id"]).any()
    assert set(review["training_action"]) == {"review_exclude"}
