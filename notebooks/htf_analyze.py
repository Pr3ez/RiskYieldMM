#%%
# =============================================================================
# CELL 1: LOAD HTF TRAINING DATA (FEATURES + LABELS) USED IN BACKTEST
# =============================================================================

from pathlib import Path

import polars as pl

# Project paths
PROJECT_ROOT = Path("..").resolve()
DATA_DIR = PROJECT_ROOT / "data"
FEATURES_DIR = DATA_DIR / "htf_with_helpers"
LABELS_DIR = DATA_DIR / "htf_8class_labels"

TARGET = "target_8class"
TIMEFRAMES = ["5m", "15m"]


def load_backtest_dataset(tf: str, target: str) -> pl.DataFrame:
    """Load the exact features+labels used by the backtest for a timeframe."""
    feat_glob = FEATURES_DIR / tf / target / "batch_*.parquet"
    label_glob = LABELS_DIR / tf / "batch_*.parquet"

    if not feat_glob.parent.exists():
        raise FileNotFoundError(f"Features dir not found: {feat_glob.parent}")
    if not label_glob.parent.exists():
        raise FileNotFoundError(f"Labels dir not found: {label_glob.parent}")

    label_scan = pl.scan_parquet(str(label_glob))
    label_cols = ["timestamp", "batch_id", target]
    schema_names = label_scan.collect_schema().names()
    target_name_col = f"{target}_name"
    if target_name_col in schema_names:
        label_cols.append(target_name_col)
    elif target == "target_8class" and "target_name" in schema_names:
        label_cols.append("target_name")

    feat_scan = pl.scan_parquet(str(feat_glob))
    df = (
        feat_scan.join(label_scan.select(label_cols), on=["timestamp", "batch_id"], how="left")
        .collect()
        .sort(["batch_id", "timestamp"])
    )
    return df


df_5m = load_backtest_dataset("5m", TARGET)
df_15m = load_backtest_dataset("15m", TARGET)

meta_cols = {
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "batch_id",
    "period_8h_start",
    TARGET,
    "target_name",
}

def feature_cols(df: pl.DataFrame) -> list[str]:
    return [c for c in df.columns if c not in meta_cols]

print(f"Loaded 5m:  {len(df_5m):,} rows | {df_5m['batch_id'].n_unique():,} batches")
print(f"Loaded 15m: {len(df_15m):,} rows | {df_15m['batch_id'].n_unique():,} batches")
print(f"5m features:  {len(feature_cols(df_5m))}")
print(f"15m features: {len(feature_cols(df_15m))}")

#%%
# =============================================================================
# CELL 2: DATA QUALITY CHECKS (FEATURES + LABELS)
# =============================================================================

def quality_report(df: pl.DataFrame, name: str, target: str) -> pl.DataFrame:
    """Return per-feature quality stats and print a quick summary."""
    feat_cols = feature_cols(df)
    n_rows = len(df)

    # Target sanity
    target_nulls = df[target].null_count() if target in df.columns else n_rows
    target_invalid = (
        df.filter(pl.col(target) < 0).height if target in df.columns else n_rows
    )

    print(f"\n{name} | rows={n_rows:,} | features={len(feat_cols)}")
    print(f"  Target nulls:   {target_nulls:,}")
    print(f"  Target invalid (<0): {target_invalid:,}")

    # Build stats in one pass
    exprs = []
    for c in feat_cols:
        exprs.append(pl.col(c).null_count().alias(f"{c}__nulls"))
        exprs.append(pl.col(c).n_unique().alias(f"{c}__nuniq"))
        if df[c].dtype in (pl.Float32, pl.Float64):
            exprs.append(pl.col(c).is_nan().sum().alias(f"{c}__nans"))
            exprs.append(pl.col(c).is_infinite().sum().alias(f"{c}__infs"))
            exprs.append(pl.col(c).min().alias(f"{c}__min"))
            exprs.append(pl.col(c).max().alias(f"{c}__max"))
        else:
            exprs.append(pl.lit(0).alias(f"{c}__nans"))
            exprs.append(pl.lit(0).alias(f"{c}__infs"))
            exprs.append(pl.lit(None).alias(f"{c}__min"))
            exprs.append(pl.lit(None).alias(f"{c}__max"))

    stats = df.select(exprs).to_dicts()[0] if feat_cols else {}

    rows = []
    for c in feat_cols:
        nulls = int(stats.get(f"{c}__nulls", 0))
        nans = int(stats.get(f"{c}__nans", 0))
        infs = int(stats.get(f"{c}__infs", 0))
        min_v = stats.get(f"{c}__min")
        max_v = stats.get(f"{c}__max")
        nuniq = int(stats.get(f"{c}__nuniq", 0))
        zero_var = (min_v == max_v) if min_v is not None and max_v is not None else False
        rows.append(
            {
                "feature": c,
                "nulls": nulls,
                "nans": nans,
                "infs": infs,
                "n_unique": nuniq,
                "min": min_v,
                "max": max_v,
                "zero_var": zero_var,
            }
        )

    report = pl.DataFrame(rows) if rows else pl.DataFrame()

    # Print top issues
    if len(report) == 0:
        print("  No features found.")
        return report

    problems = report.filter(
        (pl.col("nulls") > 0) | (pl.col("nans") > 0) | (pl.col("infs") > 0)
    )
    zero_var = report.filter(pl.col("zero_var") == True)

    print(f"  Features with any null/NaN/inf: {len(problems):,}")
    print(f"  Zero-variance features:        {len(zero_var):,}")

    if len(problems) > 0:
        print("\n  Top missing/NaN/inf features:")
        print(
            problems.sort(
                by=["nulls", "nans", "infs"], descending=True
            )
            .head(10)
            .select(["feature", "nulls", "nans", "infs"])
        )

    if len(zero_var) > 0:
        print("\n  Zero-variance features (top 10):")
        print(zero_var.head(10).select(["feature", "min", "max"]))

    return report


report_5m = quality_report(df_5m, "5m", TARGET)
report_15m = quality_report(df_15m, "15m", TARGET)

#%%
# =============================================================================
# CELL 3: CATBOOST FEATURE SELECTION (PER CLASS, PER TIMEFRAME)
# =============================================================================
# Goal:
# - Use only FIRST 5000 batches (exclude newest batches)
# - Train on first 2500 batches, validate on next 2500 batches
# - Split validation into chunks of 50 batches to measure stability
# - Run per-class (one-vs-rest) feature selection with CatBoost
# - 2 timeframes × 24 classes = 48 selections
# =============================================================================

import json
from dataclasses import dataclass
from datetime import datetime

import numpy as np
import pandas as pd
import optuna
from catboost import CatBoostClassifier, Pool
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score


@dataclass
class FeatureSelectionConfig:
    batch_limit: int = 5000
    train_batches: int = 2500
    val_batches: int = 2500
    val_chunk_size: int = 50
    n_classes: int = 8
    feature_counts: tuple[int, ...] = (50,)  # adjust if you want a sweep
    stability_lambda: float = 0.5  # stability_score = mean_f1 - lambda * std_f1
    candidate_features: int = 200  # prefilter top-N by importance before selection
    base_iterations: int = 300  # baseline model for feature ranking
    selection_algorithm: str = "RecursiveByPredictionValuesChange"
    selection_steps: int = 1
    min_features: int = 20
    max_features: int = 120
    feature_step: int = 10
    optuna_trials: int = 50
    optuna_timeout: int | None = None  # seconds
    print_chunk_metrics: bool = True
    random_seed: int = 42
    min_iterations: int = 300
    max_iterations: int = 1200
    depth: int = 6
    learning_rate: float = 0.1
    l2_leaf_reg: float = 3.0
    max_bins: int = 128
    thread_count: int = -1
    verbose: bool = False


FS_CONFIG = FeatureSelectionConfig()
OUTPUT_DIR = DATA_DIR / "htf_feature_selection" / "catboost"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def split_by_batches(
    df: pl.DataFrame, cfg: FeatureSelectionConfig
) -> tuple[pl.DataFrame, pl.DataFrame, list[int], list[int], list[list[int]]]:
    """Return train_df, val_df, train_ids, val_ids, val_chunks."""
    batch_ids = sorted(df["batch_id"].unique().to_list())
    batch_ids = batch_ids[: cfg.batch_limit]

    train_ids = batch_ids[: cfg.train_batches]
    val_ids = batch_ids[cfg.train_batches : cfg.train_batches + cfg.val_batches]

    if len(train_ids) < cfg.train_batches or len(val_ids) < cfg.val_batches:
        raise ValueError(
            f"Not enough batches after limit={cfg.batch_limit}. "
            f"Got train={len(train_ids)}, val={len(val_ids)}"
        )

    train_df = df.filter(pl.col("batch_id").is_in(train_ids))
    val_df = df.filter(pl.col("batch_id").is_in(val_ids))

    val_chunks = [
        val_ids[i : i + cfg.val_chunk_size]
        for i in range(0, len(val_ids), cfg.val_chunk_size)
    ]
    return train_df, val_df, train_ids, val_ids, val_chunks


def evaluate_chunks(
    val_df: pd.DataFrame,
    y_true: np.ndarray,
    y_pred: np.ndarray,
    val_chunks: list[list[int]],
) -> list[dict]:
    """Compute accuracy/precision/recall/F1 per validation chunk."""
    rows = []
    batch_ids = val_df["batch_id"].to_numpy()

    for i, chunk in enumerate(val_chunks, 1):
        mask = np.isin(batch_ids, chunk)
        if mask.sum() == 0:
            continue
        y_t = y_true[mask]
        y_p = y_pred[mask]
        acc = accuracy_score(y_t, y_p)
        prec = precision_score(y_t, y_p, zero_division=0)
        rec = recall_score(y_t, y_p, zero_division=0)
        f1 = f1_score(y_t, y_p, zero_division=0)
        pos_rate = float(y_t.mean())
        rows.append(
            {
                "chunk_id": i,
                "batches": f"{chunk[0]}-{chunk[-1]}",
                "rows": int(mask.sum()),
                "accuracy": float(acc),
                "precision": float(prec),
                "recall": float(rec),
                "f1": float(f1),
                "pos_rate": pos_rate,
            }
        )
    return rows


def _save_study_artifacts(
    study: optuna.Study,
    study_dir: Path,
    tf: str,
    class_id: int,
    cfg: FeatureSelectionConfig,
    candidate_features: list[str],
) -> None:
    """Persist Optuna study artifacts similar to backtest runs."""
    study_dir.mkdir(parents=True, exist_ok=True)

    # Save study trials
    trials_df = study.trials_dataframe(attrs=("number", "value", "params", "user_attrs"))
    trials_path = study_dir / "trials.parquet"
    trials_df.to_parquet(trials_path, index=False)

    jsonl_path = study_dir / "trials.jsonl"
    with open(jsonl_path, "w") as f:
        for _, row in trials_df.iterrows():
            f.write(json.dumps(row.to_dict()) + "\n")

    # Save best summary
    best = {
        "timeframe": tf,
        "class_id": class_id,
        "best_value": study.best_value,
        "best_params": study.best_params,
        "best_trial_number": study.best_trial.number,
        "updated_at": datetime.now().isoformat(),
    }
    with open(study_dir / "best.json", "w") as f:
        json.dump(best, f, indent=2)

    # Save config and candidate pool
    config = {
        "timeframe": tf,
        "class_id": class_id,
        "candidate_features": candidate_features,
        "optuna_trials": cfg.optuna_trials,
        "optuna_timeout": cfg.optuna_timeout,
        "min_features": cfg.min_features,
        "max_features": cfg.max_features,
        "feature_step": cfg.feature_step,
        "stability_lambda": cfg.stability_lambda,
        "selection_algorithm": cfg.selection_algorithm,
        "selection_steps": cfg.selection_steps,
    }
    with open(study_dir / "config.json", "w") as f:
        json.dump(config, f, indent=2)


def run_feature_selection_for_timeframe(
    tf: str, df: pl.DataFrame, cfg: FeatureSelectionConfig
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Run per-class Optuna tuning for CatBoost feature selection (one-vs-rest)."""
    print(f"\n{'=' * 70}")
    print(f"CatBoost feature selection | {tf}")
    print(f"{'=' * 70}")

    # Filter invalid labels
    df = df.filter(pl.col(TARGET) >= 0)

    train_df, val_df, train_ids, val_ids, val_chunks = split_by_batches(df, cfg)
    feat_cols = feature_cols(df)

    # Convert to pandas for CatBoost
    train_pd = train_df.select(feat_cols + [TARGET, "batch_id"]).to_pandas()
    val_pd = val_df.select(feat_cols + [TARGET, "batch_id"]).to_pandas()

    results = []
    chunk_results = []

    for class_id in range(cfg.n_classes):
        print(f"\n[{tf}] Class {class_id} / {cfg.n_classes - 1}")

        y_train = (train_pd[TARGET].values == class_id).astype(np.int8)
        y_val = (val_pd[TARGET].values == class_id).astype(np.int8)

        # Handle class imbalance (simple weight ratio)
        pos = max(1, int(y_train.sum()))
        neg = max(1, int(len(y_train) - pos))
        scale_pos_weight = neg / pos

        # Baseline model for candidate feature ranking (per class)
        base_model = CatBoostClassifier(
            loss_function="Logloss",
            eval_metric="AUC",
            iterations=cfg.base_iterations,
            depth=cfg.depth,
            learning_rate=cfg.learning_rate,
            l2_leaf_reg=cfg.l2_leaf_reg,
            max_bin=cfg.max_bins,
            random_seed=cfg.random_seed,
            scale_pos_weight=scale_pos_weight,
            thread_count=cfg.thread_count,
            verbose=cfg.verbose,
        )
        base_pool = Pool(train_pd[feat_cols], y_train, feature_names=feat_cols)
        base_model.fit(base_pool, verbose=cfg.verbose)
        importances = base_model.get_feature_importance(
            base_pool, type="PredictionValuesChange"
        )
        ranked = [feat_cols[i] for i in np.argsort(importances)[::-1]]
        if cfg.candidate_features and cfg.candidate_features < len(ranked):
            candidate = ranked[: cfg.candidate_features]
        else:
            candidate = ranked

        def objective(trial: optuna.Trial) -> float:
            k = trial.suggest_int(
                "num_features", cfg.min_features, cfg.max_features, step=cfg.feature_step
            )
            k_eff = min(k, len(candidate))
            iterations = trial.suggest_int(
                "iterations", cfg.min_iterations, cfg.max_iterations, step=50
            )
            depth = trial.suggest_int("depth", 4, 10)
            learning_rate = trial.suggest_float("learning_rate", 0.01, 0.2, log=True)
            l2_leaf_reg = trial.suggest_float("l2_leaf_reg", 0.5, 50.0, log=True)
            random_strength = trial.suggest_float("random_strength", 0.0, 5.0)
            rsm = trial.suggest_float("rsm", 0.5, 1.0)
            min_data_in_leaf = trial.suggest_int("min_data_in_leaf", 20, 200, step=10)
            bootstrap_type = trial.suggest_categorical(
                "bootstrap_type", ["Bayesian", "Bernoulli", "MVS"]
            )
            bagging_temperature = None
            subsample = None
            if bootstrap_type == "Bayesian":
                bagging_temperature = trial.suggest_float("bagging_temperature", 0.0, 1.0)
            else:
                subsample = trial.suggest_float("subsample", 0.6, 1.0)
            pos_weight_mult = trial.suggest_float("pos_weight_mult", 0.5, 2.0)
            scale_pos_weight_tuned = scale_pos_weight * pos_weight_mult

            model = CatBoostClassifier(
                loss_function="Logloss",
                eval_metric="F1",
                iterations=iterations,
                depth=depth,
                learning_rate=learning_rate,
                l2_leaf_reg=l2_leaf_reg,
                max_bin=cfg.max_bins,
                random_seed=cfg.random_seed + trial.number,
                random_strength=random_strength,
                rsm=rsm,
                min_data_in_leaf=min_data_in_leaf,
                bootstrap_type=bootstrap_type,
                bagging_temperature=bagging_temperature,
                subsample=subsample,
                od_type="Iter",
                od_wait=50,
                scale_pos_weight=scale_pos_weight_tuned,
                thread_count=cfg.thread_count,
                verbose=cfg.verbose,
            )

            train_pool = Pool(train_pd[candidate], y_train, feature_names=candidate)
            val_pool = Pool(val_pd[candidate], y_val, feature_names=candidate)

            fs_summary = model.select_features(
                train_pool,
                eval_set=val_pool,
                features_for_select=candidate,
                num_features_to_select=k_eff,
                steps=cfg.selection_steps,
                algorithm=cfg.selection_algorithm,
                shap_calc_type="Regular",
                train_final_model=True,
                verbose=cfg.verbose,
            )

            selected = fs_summary.get("selected_features_names")
            if not selected:
                selected = fs_summary.get("selected_features")
            if not selected:
                selected = candidate[:k_eff]

            # Predict on validation
            val_pred = model.predict(val_pd[selected])
            val_pred = val_pred.astype(int).reshape(-1)

            acc = accuracy_score(y_val, val_pred)
            prec = precision_score(y_val, val_pred, zero_division=0)
            rec = recall_score(y_val, val_pred, zero_division=0)
            f1 = f1_score(y_val, val_pred, zero_division=0)

            chunk_metrics = evaluate_chunks(val_pd, y_val, val_pred, val_chunks)
            if chunk_metrics:
                f1_vals = [m["f1"] for m in chunk_metrics]
                mean_f1 = float(np.mean(f1_vals))
                std_f1 = float(np.std(f1_vals))
                min_f1 = float(np.min(f1_vals))
                stability_score = mean_f1 - cfg.stability_lambda * std_f1
            else:
                mean_f1 = 0.0
                std_f1 = 0.0
                min_f1 = 0.0
                stability_score = 0.0

            # Print chunk stability table
            print(
                f"  trial={trial.number} k={k_eff} | acc={acc:.3f} prec={prec:.3f} "
                f"rec={rec:.3f} f1={f1:.3f} | mean_f1={mean_f1:.3f} "
                f"std_f1={std_f1:.3f} min_f1={min_f1:.3f} "
                f"stability={stability_score:.3f}"
            )
            if cfg.print_chunk_metrics and chunk_metrics:
                print("  Chunk metrics:")
                for m in chunk_metrics:
                    print(
                        f"    chunk {m['chunk_id']:02d} "
                        f"batches {m['batches']} rows {m['rows']:>5} "
                        f"acc {m['accuracy']:.3f} prec {m['precision']:.3f} "
                        f"rec {m['recall']:.3f} f1 {m['f1']:.3f} "
                        f"pos_rate {m['pos_rate']:.3f}"
                    )

            for m in chunk_metrics:
                chunk_results.append(
                    {
                        "timeframe": tf,
                        "class_id": class_id,
                        "trial": trial.number,
                        "num_features": k_eff,
                        **m,
                    }
                )

            results.append(
                {
                    "timeframe": tf,
                    "class_id": class_id,
                    "trial": trial.number,
                    "num_features": k_eff,
                    "candidate_features": len(candidate),
                    "accuracy": float(acc),
                    "precision": float(prec),
                    "recall": float(rec),
                    "f1": float(f1),
                    "mean_f1": mean_f1,
                    "std_f1": std_f1,
                    "min_f1": min_f1,
                    "stability_score": stability_score,
                    "selected_features": selected,
                    "params": {
                        "iterations": iterations,
                        "depth": depth,
                        "learning_rate": learning_rate,
                        "l2_leaf_reg": l2_leaf_reg,
                        "random_strength": random_strength,
                        "rsm": rsm,
                        "min_data_in_leaf": min_data_in_leaf,
                        "bootstrap_type": bootstrap_type,
                        "bagging_temperature": bagging_temperature,
                        "subsample": subsample,
                        "pos_weight_mult": pos_weight_mult,
                    },
                }
            )

            return stability_score

        study_dir = OUTPUT_DIR / tf / f"class_{class_id:02d}"
        study_dir.mkdir(parents=True, exist_ok=True)
        study_db = study_dir / "study.db"
        storage = f"sqlite:///{study_db.as_posix()}"
        study = optuna.create_study(
            study_name=f"fs_catboost_{tf}_class_{class_id}",
            direction="maximize",
            storage=storage,
            load_if_exists=True,
        )
        study.optimize(objective, n_trials=cfg.optuna_trials, timeout=cfg.optuna_timeout)

        print(
            f"  Best stability for class {class_id}: {study.best_value:.4f} "
            f"(trial {study.best_trial.number})"
        )

        _save_study_artifacts(
            study=study,
            study_dir=study_dir,
            tf=tf,
            class_id=class_id,
            cfg=cfg,
            candidate_features=candidate,
        )

    return pd.DataFrame(results), pd.DataFrame(chunk_results)


# Run for each timeframe
results_all = []
chunks_all = []
for tf, df in [("5m", df_5m), ("15m", df_15m)]:
    res_tf, chunks_tf = run_feature_selection_for_timeframe(tf, df, FS_CONFIG)
    results_all.append(res_tf)
    chunks_all.append(chunks_tf)

results_df = pd.concat(results_all, ignore_index=True) if results_all else pd.DataFrame()
chunks_df = pd.concat(chunks_all, ignore_index=True) if chunks_all else pd.DataFrame()

# Save summary
summary_path = OUTPUT_DIR / "feature_selection_summary.parquet"
results_df.to_parquet(summary_path, index=False)
print(f"\nSaved: {summary_path}")

# Save chunk metrics
chunks_path = OUTPUT_DIR / "feature_selection_chunks.parquet"
chunks_df.to_parquet(chunks_path, index=False)
print(f"Saved: {chunks_path}")
