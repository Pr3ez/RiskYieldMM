from __future__ import annotations

import json
import math
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl
from catboost import CatBoostClassifier, CatBoostError, Pool
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    confusion_matrix,
    f1_score,
    log_loss,
    precision_recall_fscore_support,
)

_REPO_BOOTSTRAP_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_BOOTSTRAP_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_BOOTSTRAP_ROOT))

from scripts.project_paths import ensure_project_root_on_path  # noqa: E402

PROJECT_ROOT = ensure_project_root_on_path(Path(__file__))

from scripts.htf_backtest.catboost.utils import (  # noqa: E402
    BASE_CLASS_NAMES,
    compute_directional_accuracy,
    load_batch,
)
from scripts.feature_engineering.htf_feature_acceptance import (  # noqa: E402
    get_final_output_excluded_columns,
)


TARGET_COL = "target_4class"
TF = "1m"
CLASS_NAMES = list(BASE_CLASS_NAMES)
N_CLASSES = 4

# Keep total row budgets comparable across regimes with very different batch sizes.
ROW_BUDGET_BY_REGIME = {
    "8h": 240_000,
    "24h": 240_000,
    "7d": 240_000,
}
EXPECTED_VALID_ROWS_PER_BATCH = {
    "8h": 240,
    "24h": 720,
    "7d": 5040,
}
MIN_BATCHES_PER_ROOT = 48
TRAIN_SHARE = 0.60
VAL_SHARE = 0.20
TEST_SHARE = 0.20
CHUNK_COUNT = 5

OUTPUT_DIR = PROJECT_ROOT / "test_output" / "htf_catboost_regime_family_benchmark"

ROOTS = {
    ("8h", "B"): {
        "features_dir": PROJECT_ROOT / "data" / "htf_with_helpers",
        "labels_dir": PROJECT_ROOT / "data" / "htf_4class_labels",
    },
    ("8h", "C"): {
        "features_dir": PROJECT_ROOT / "data" / "htf_with_helpers_shift4h",
        "labels_dir": PROJECT_ROOT / "data" / "htf_4class_labels_shift4h",
    },
    ("24h", "B"): {
        "features_dir": PROJECT_ROOT / "data" / "htf_with_helpers_24h",
        "labels_dir": PROJECT_ROOT / "data" / "htf_4class_labels_24h",
    },
    ("24h", "C"): {
        "features_dir": PROJECT_ROOT / "data" / "htf_with_helpers_24h_shift12h",
        "labels_dir": PROJECT_ROOT / "data" / "htf_4class_labels_24h_shift12h",
    },
    ("7d", "B"): {
        "features_dir": PROJECT_ROOT / "data" / "htf_with_helpers_7d",
        "labels_dir": PROJECT_ROOT / "data" / "htf_4class_labels_7d",
    },
    ("7d", "C"): {
        "features_dir": PROJECT_ROOT / "data" / "htf_with_helpers_7d_shift84h",
        "labels_dir": PROJECT_ROOT / "data" / "htf_4class_labels_7d_shift84h",
    },
}

META_EXCLUDE = {
    "timestamp",
    "batch_id",
    "target_4class",
    "target_breakfree",
    "target_name",
    "period_8h_start",
    "batch_family",
    "family_batch_id",
    "family_period_start",
    "family_period_end",
    "family_bar_pos",
    "source_base_batch_id",
    "source_base_period_start",
    "source_half_in_base",
    "is_label_half",
    "batch_regime",
    "batch_duration_hours",
    "family_shift_hours",
    "anchor_utc",
    "entry_window_hours",
}


@dataclass
class RootResult:
    regime: str
    family: str
    first_ready_batch: int
    total_available_batches: int
    selected_batches: int
    train_batches: int
    val_batches: int
    test_batches: int
    train_rows: int
    val_rows: int
    test_rows: int
    n_features: int
    best_iteration: int
    accuracy: float
    balanced_accuracy: float
    macro_f1: float
    weighted_f1: float
    log_loss: float
    directional_accuracy: float
    test_class_support: dict[str, int]
    per_class_precision: dict[str, float]
    per_class_recall: dict[str, float]
    per_class_f1: dict[str, float]


def _feature_dir_for_batches(features_dir: Path) -> Path:
    return features_dir / TF / TARGET_COL


def _expected_batch_budget(regime: str, total_batches: int) -> int:
    approx = int(round(ROW_BUDGET_BY_REGIME[regime] / EXPECTED_VALID_ROWS_PER_BATCH[regime]))
    return max(MIN_BATCHES_PER_ROOT, min(total_batches, approx))


def _helper_columns(sample_df: pl.DataFrame) -> list[str]:
    return [c for c in sample_df.columns if c.startswith("H_")]


def _find_first_ready_batch(features_dir: Path) -> int:
    batch_files = sorted(_feature_dir_for_batches(features_dir).glob("batch_*.parquet"))
    if not batch_files:
        raise FileNotFoundError(f"No helper batch files under {features_dir}")
    for p in batch_files:
        df = pl.read_parquet(p)
        helper_cols = _helper_columns(df)
        if not helper_cols:
            return int(p.stem.split("_")[1])
        non_null_any = (
            df.select(pl.any_horizontal([pl.col(c).is_not_null() for c in helper_cols]).alias("ok"))
            .select(pl.col("ok").any())
            .item()
        )
        if bool(non_null_any):
            return int(p.stem.split("_")[1])
    raise RuntimeError(f"No ready helper batch found under {features_dir}")


def _load_selected_batches(features_dir: Path, labels_dir: Path, batch_ids: list[int]) -> pl.DataFrame:
    frames: list[pl.DataFrame] = []
    for batch_id in batch_ids:
        frames.append(load_batch(features_dir, labels_dir, TF, batch_id, target_col=TARGET_COL))
    return pl.concat(frames, how="diagonal_relaxed").filter(pl.col(TARGET_COL) >= 0).sort(["batch_id", "timestamp"])


def _split_batch_ids(batch_ids: list[int]) -> tuple[list[int], list[int], list[int]]:
    n = len(batch_ids)
    train_n = max(1, int(math.floor(n * TRAIN_SHARE)))
    val_n = max(1, int(math.floor(n * VAL_SHARE)))
    test_n = n - train_n - val_n
    if test_n < 1:
        test_n = 1
        if val_n > 1:
            val_n -= 1
        else:
            train_n = max(1, train_n - 1)
    train_ids = batch_ids[:train_n]
    val_ids = batch_ids[train_n : train_n + val_n]
    test_ids = batch_ids[train_n + val_n :]
    return train_ids, val_ids, test_ids


def _feature_columns(df: pl.DataFrame) -> list[str]:
    helper_exclude = set(get_final_output_excluded_columns(df.columns, stage="helpers"))
    feature_cols: list[str] = []
    for c, dtype in df.schema.items():
        if c in META_EXCLUDE:
            continue
        if c in helper_exclude:
            continue
        if dtype in {
            pl.Float32,
            pl.Float64,
            pl.Int8,
            pl.Int16,
            pl.Int32,
            pl.Int64,
            pl.UInt8,
            pl.UInt16,
            pl.UInt32,
            pl.UInt64,
            pl.Boolean,
        }:
            feature_cols.append(c)
    return feature_cols


def _to_matrix(df: pl.DataFrame, feature_cols: list[str]) -> np.ndarray:
    casted = df.select(
        [
            pl.col(c).cast(pl.Float32, strict=False).alias(c)
            for c in feature_cols
        ]
    )
    arr = casted.to_numpy()
    arr = np.asarray(arr, dtype=np.float32)
    arr[np.isinf(arr)] = np.nan
    return arr


def _catboost_params() -> dict[str, Any]:
    return {
        "loss_function": "MultiClass",
        "eval_metric": "MultiClass",
        "iterations": 500,
        "learning_rate": 0.05,
        "depth": 6,
        "l2_leaf_reg": 5.0,
        "random_seed": 42,
        "auto_class_weights": "Balanced",
        "allow_writing_files": False,
        "verbose": False,
        "thread_count": -1,
    }


def _fit_catboost(X_train: np.ndarray, y_train: np.ndarray, X_val: np.ndarray, y_val: np.ndarray, feature_cols: list[str]) -> CatBoostClassifier:
    params = _catboost_params()
    train_pool = Pool(X_train, y_train, feature_names=feature_cols)
    val_pool = Pool(X_val, y_val, feature_names=feature_cols)
    try:
        model = CatBoostClassifier(task_type="GPU", devices="0", **params)
        model.fit(train_pool, eval_set=val_pool, use_best_model=True, early_stopping_rounds=50)
        return model
    except CatBoostError:
        model = CatBoostClassifier(task_type="CPU", **params)
        model.fit(train_pool, eval_set=val_pool, use_best_model=True, early_stopping_rounds=50)
        return model


def _chunk_metrics(batch_ids: list[int], pred_df: pl.DataFrame) -> list[dict[str, Any]]:
    if not batch_ids:
        return []
    chunk_size = max(1, int(math.ceil(len(batch_ids) / CHUNK_COUNT)))
    chunks: list[dict[str, Any]] = []
    for i in range(0, len(batch_ids), chunk_size):
        ids = batch_ids[i : i + chunk_size]
        chunk = pred_df.filter(pl.col("batch_id").is_in(ids))
        if len(chunk) == 0:
            continue
        y_true = chunk[TARGET_COL].to_numpy()
        y_pred = chunk["pred_class"].to_numpy()
        chunks.append(
            {
                "chunk_id": len(chunks) + 1,
                "batch_start": int(ids[0]),
                "batch_end": int(ids[-1]),
                "rows": int(len(chunk)),
                "accuracy": float(accuracy_score(y_true, y_pred)),
                "balanced_accuracy": float(balanced_accuracy_score(y_true, y_pred)),
                "macro_f1": float(f1_score(y_true, y_pred, average="macro", zero_division=0)),
                "directional_accuracy": float(compute_directional_accuracy(y_true, y_pred, CLASS_NAMES)),
            }
        )
    return chunks


def run_benchmark() -> dict[str, Any]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    summary_rows: list[dict[str, Any]] = []
    per_root_details: dict[str, Any] = {}

    for (regime, family), paths in ROOTS.items():
        key = f"{regime}/{family}"
        features_dir = Path(paths["features_dir"])
        labels_dir = Path(paths["labels_dir"])
        batch_files = sorted(_feature_dir_for_batches(features_dir).glob("batch_*.parquet"))
        all_batch_ids = [int(p.stem.split("_")[1]) for p in batch_files]
        first_ready = _find_first_ready_batch(features_dir)
        usable_batch_ids = [b for b in all_batch_ids if b >= first_ready]
        selected_count = _expected_batch_budget(regime, len(usable_batch_ids))
        selected_batch_ids = usable_batch_ids[-selected_count:]
        train_ids, val_ids, test_ids = _split_batch_ids(selected_batch_ids)

        train_df = _load_selected_batches(features_dir, labels_dir, train_ids)
        val_df = _load_selected_batches(features_dir, labels_dir, val_ids)
        test_df = _load_selected_batches(features_dir, labels_dir, test_ids)

        feature_cols = _feature_columns(train_df)
        X_train = _to_matrix(train_df, feature_cols)
        X_val = _to_matrix(val_df, feature_cols)
        X_test = _to_matrix(test_df, feature_cols)
        y_train = train_df[TARGET_COL].to_numpy().astype(np.int32, copy=False)
        y_val = val_df[TARGET_COL].to_numpy().astype(np.int32, copy=False)
        y_test = test_df[TARGET_COL].to_numpy().astype(np.int32, copy=False)

        model = _fit_catboost(X_train, y_train, X_val, y_val, feature_cols)
        pred = model.predict(X_test).astype(np.int32).reshape(-1)
        proba = model.predict_proba(X_test)

        precision, recall, f1, support = precision_recall_fscore_support(
            y_test,
            pred,
            labels=list(range(N_CLASSES)),
            zero_division=0,
        )
        test_pred_df = test_df.select(["timestamp", "batch_id", TARGET_COL]).with_columns(
            pl.Series("pred_class", pred),
        )
        cm = confusion_matrix(y_test, pred, labels=list(range(N_CLASSES)))

        result = RootResult(
            regime=regime,
            family=family,
            first_ready_batch=first_ready,
            total_available_batches=len(usable_batch_ids),
            selected_batches=len(selected_batch_ids),
            train_batches=len(train_ids),
            val_batches=len(val_ids),
            test_batches=len(test_ids),
            train_rows=len(train_df),
            val_rows=len(val_df),
            test_rows=len(test_df),
            n_features=len(feature_cols),
            best_iteration=int(model.get_best_iteration() if model.get_best_iteration() is not None else model.tree_count_),
            accuracy=float(accuracy_score(y_test, pred)),
            balanced_accuracy=float(balanced_accuracy_score(y_test, pred)),
            macro_f1=float(f1_score(y_test, pred, average="macro", zero_division=0)),
            weighted_f1=float(f1_score(y_test, pred, average="weighted", zero_division=0)),
            log_loss=float(log_loss(y_test, proba, labels=list(range(N_CLASSES)))),
            directional_accuracy=float(compute_directional_accuracy(y_test, pred, CLASS_NAMES)),
            test_class_support={CLASS_NAMES[i]: int(support[i]) for i in range(N_CLASSES)},
            per_class_precision={CLASS_NAMES[i]: float(precision[i]) for i in range(N_CLASSES)},
            per_class_recall={CLASS_NAMES[i]: float(recall[i]) for i in range(N_CLASSES)},
            per_class_f1={CLASS_NAMES[i]: float(f1[i]) for i in range(N_CLASSES)},
        )
        summary_rows.append(asdict(result))
        per_root_details[key] = {
            "summary": asdict(result),
            "selected_batch_ids": selected_batch_ids,
            "confusion_matrix": {
                "labels": CLASS_NAMES,
                "matrix": cm.tolist(),
            },
            "test_chunks": _chunk_metrics(test_ids, test_pred_df),
            "feature_cols": feature_cols,
            "feature_importance_top20": [
                {
                    "feature": feature_cols[i],
                    "importance": float(v),
                }
                for i, v in sorted(
                    enumerate(model.get_feature_importance()),
                    key=lambda x: x[1],
                    reverse=True,
                )[:20]
            ],
        }

    summary_rows = sorted(summary_rows, key=lambda r: (r["regime"], r["family"]))
    out = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "method": {
            "target": TARGET_COL,
            "timeframe": TF,
            "row_budget_by_regime": ROW_BUDGET_BY_REGIME,
            "expected_valid_rows_per_batch": EXPECTED_VALID_ROWS_PER_BATCH,
            "train_share": TRAIN_SHARE,
            "val_share": VAL_SHARE,
            "test_share": TEST_SHARE,
            "post_warmup_only": True,
            "catboost_params": _catboost_params(),
        },
        "summary": summary_rows,
        "details": per_root_details,
    }
    (OUTPUT_DIR / "summary_20260401.json").write_text(json.dumps(out, indent=2))
    return out


if __name__ == "__main__":
    result = run_benchmark()
    print(json.dumps(result["summary"], indent=2))
