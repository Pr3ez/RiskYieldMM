#%%
# =============================================================================
# HTF Batch Correlation Analysis
# =============================================================================
# Goal:
#   Measure similarity between 8h batches to help choose a train/validation
#   window that captures patterns similar to the most recent prediction batch.
#
# Outputs (per timeframe):
#   - data/htf_batch_correlation/{tf}/similarity_to_latest.parquet
#   - data/htf_batch_correlation/{tf}/lag_similarity.parquet
#   - data/htf_batch_correlation/{tf}/top_similar_batches.parquet
#   - data/htf_batch_correlation/{tf}/summary.json
# =============================================================================

import json
from pathlib import Path
from typing import Iterable

import numpy as np
import polars as pl

# =============================================================================
# CONFIG
# =============================================================================
PROJECT_ROOT = Path("..").resolve()

TIMEFRAMES = ["5m", "15m"]

# Feature source for similarity.
# Note: `target_breakfree` reuses `target_8class` features in the backtest.
FEATURE_TARGET = "target_8class"

# Optional label target to compute label-distribution similarity.
LABEL_TARGET = "target_8class"

# Batch slicing (set one; None means use all)
USE_FIRST_N_BATCHES = None  # e.g., 5000
USE_LAST_N_BATCHES = None   # e.g., 2000

# Per-batch analysis window
# If set, only batches with batch_id >= MIN_BATCH_ID_FOR_ANALYSIS are included
MIN_BATCH_ID_FOR_ANALYSIS = 1000

# Similarity configuration
MAX_LAG = 1000
SIM_THRESHOLD = 0.25  # heuristic for suggesting lookback window
TOP_K_SIMILAR = 50

# Lookback optimization
LOOKBACK_MIN = 100
LOOKBACK_MAX = 1200
LOOKBACK_STEP = 50
VAL_RATIO = 0.2  # fraction of lookback reserved for validation
STABILITY_LAMBDA = 0.5  # score = mean_sim - lambda * std_sim

# Aggregation for per-batch feature vectors
INCLUDE_STD = True

# Head exclusion grid (portion of first rows to exclude per batch)
HEAD_GRID = [0.0, 0.05, 0.1, 0.2, 0.25, 0.33]
HEAD_SELECT_METRIC = "label_mse"

# Tail exclusion grid (portion of last rows to exclude per batch)
TAIL_GRID = [0.0, 0.1, 0.25, 0.33]
TAIL_SELECT_METRIC = "median_best_score"

# 8-class target distribution (DOC_TARGETS) for head exclusion selection
DOC_TARGETS_8CLASS = {
    0: 25.5,
    1: 11.2,
    2: 9.8,
    3: 28.4,
    4: 9.5,
    5: 9.6,
    6: 3.5,
    7: 2.6,
}

OUTPUT_DIR = PROJECT_ROOT / "data" / "htf_batch_correlation"


# =============================================================================
# HELPERS
# =============================================================================
def _select_batch_ids(batch_ids: list[int]) -> list[int]:
    batch_ids = sorted(batch_ids)
    if MIN_BATCH_ID_FOR_ANALYSIS is not None:
        batch_ids = [b for b in batch_ids if b >= MIN_BATCH_ID_FOR_ANALYSIS]
    if USE_FIRST_N_BATCHES is not None:
        return batch_ids[:USE_FIRST_N_BATCHES]
    if USE_LAST_N_BATCHES is not None:
        return batch_ids[-USE_LAST_N_BATCHES:]
    return batch_ids


def _feature_cols_from_schema(schema: dict[str, pl.DataType]) -> list[str]:
    exclude = {
        "timestamp",
        "batch_id",
        "period_8h_start",
        "bar_in_batch_norm",
        "target_8class",
        "target_breakfree",
        "target_name",
        "target_8class_name",
        "target_breakfree_name",
    }
    return [c for c in schema.keys() if c not in exclude and not c.endswith("_right")]


def _compute_batch_feature_matrix(
    tf: str,
    feature_target: str,
    exclude_head_pct: float = 0.0,
    exclude_tail_pct: float = 0.0,
) -> pl.DataFrame:
    feat_glob = (
        PROJECT_ROOT
        / "data"
        / "htf_with_helpers"
        / tf
        / feature_target
        / "batch_*.parquet"
    )
    scan = pl.scan_parquet(str(feat_glob))
    schema = scan.collect_schema()
    feat_cols = _feature_cols_from_schema(schema)
    if not feat_cols:
        raise ValueError(f"No feature columns detected for {tf}/{feature_target}.")

    schema_names = set(scan.collect_schema().names())
    base_cols = ["batch_id"]
    if "timestamp" in schema_names:
        base_cols.append("timestamp")
    if "bar_in_batch_norm" in schema_names:
        base_cols.append("bar_in_batch_norm")
    df_scan = scan.select(base_cols + feat_cols)
    if (exclude_head_pct and exclude_head_pct > 0) or (
        exclude_tail_pct and exclude_tail_pct > 0
    ):
        if "bar_in_batch_norm" in schema_names:
            low_cut = exclude_head_pct
            high_cut = 1.0 - exclude_tail_pct
            df_scan = df_scan.filter(
                (pl.col("bar_in_batch_norm") >= low_cut)
                & (pl.col("bar_in_batch_norm") <= high_cut)
            )
        elif "timestamp" in schema_names:
            # Fallback: drop last N rows per batch based on timestamp order
            df_scan = (
                df_scan.with_columns(
                    pl.col("timestamp")
                    .rank("ordinal")
                    .over("batch_id")
                    .alias("_row_in_batch")
                )
                .with_columns(
                    pl.count().over("batch_id").alias("_batch_size")
                )
                .filter(
                    (pl.col("_row_in_batch") > (pl.col("_batch_size") * exclude_head_pct))
                    & (
                        pl.col("_row_in_batch")
                        <= (pl.col("_batch_size") * (1.0 - exclude_tail_pct))
                    )
                )
            )
        else:
            # No ordering column available, skip tail exclusion
            pass
    agg_exprs = [pl.col(c).mean().alias(f"{c}__mean") for c in feat_cols]
    if INCLUDE_STD:
        agg_exprs += [pl.col(c).std().alias(f"{c}__std") for c in feat_cols]

    df = (
        df_scan.select(["batch_id"] + feat_cols)
        .group_by("batch_id")
        .agg(agg_exprs)
        .collect()
        .sort("batch_id")
    )
    return df


def _compute_batch_label_distribution(
    tf: str,
    target: str,
    exclude_head_pct: float = 0.0,
    exclude_tail_pct: float = 0.0,
) -> pl.DataFrame | None:
    label_glob = (
        PROJECT_ROOT / "data" / "htf_8class_labels" / tf / "batch_*.parquet"
    )
    scan = pl.scan_parquet(str(label_glob))
    schema = scan.collect_schema()
    if target not in schema.names():
        return None

    # Determine class IDs from available values
    # Using a small sample to infer unique classes
    sample = scan.select(["batch_id", target]).limit(50_000).collect()
    classes = sorted(
        [
            int(v)
            for v in sample[target].drop_nulls().unique().to_list()
            if v is not None and int(v) >= 0
        ]
    )

    agg_exprs = [pl.len().alias("n_rows")]
    for c in classes:
        agg_exprs.append((pl.col(target) == c).mean().alias(f"label_pct_{c}"))

    schema_names = set(scan.collect_schema().names())
    cols = ["batch_id", target]
    if "timestamp" in schema_names:
        cols.append("timestamp")
    if "bar_in_batch_norm" in schema_names:
        cols.append("bar_in_batch_norm")
    df_scan = scan.select(cols).filter(pl.col(target) >= 0)
    if (exclude_head_pct and exclude_head_pct > 0) or (
        exclude_tail_pct and exclude_tail_pct > 0
    ):
        if "bar_in_batch_norm" in schema_names:
            low_cut = exclude_head_pct
            high_cut = 1.0 - exclude_tail_pct
            df_scan = df_scan.filter(
                (pl.col("bar_in_batch_norm") >= low_cut)
                & (pl.col("bar_in_batch_norm") <= high_cut)
            )
        elif "timestamp" in schema_names:
            df_scan = (
                df_scan.with_columns(
                    pl.col("timestamp")
                    .rank("ordinal")
                    .over("batch_id")
                    .alias("_row_in_batch")
                )
                .with_columns(
                    pl.count().over("batch_id").alias("_batch_size")
                )
                .filter(
                    (pl.col("_row_in_batch") > (pl.col("_batch_size") * exclude_head_pct))
                    & (
                        pl.col("_row_in_batch")
                        <= (pl.col("_batch_size") * (1.0 - exclude_tail_pct))
                    )
                )
            )
        else:
            # No ordering column available, skip tail exclusion
            pass
    df = (
        df_scan
        .group_by("batch_id")
        .agg(agg_exprs)
        .collect()
        .sort("batch_id")
    )
    return df


def _zscore_matrix(x: np.ndarray) -> np.ndarray:
    x = np.nan_to_num(x, nan=0.0, posinf=0.0, neginf=0.0)
    mean = x.mean(axis=0)
    std = x.std(axis=0) + 1e-9
    return (x - mean) / std


def _normalize_rows(x: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(x, axis=1, keepdims=True) + 1e-12
    return x / norms


def _cosine_similarity_to_latest(x: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(x, axis=1) + 1e-12
    latest = x[-1]
    latest_norm = np.linalg.norm(latest) + 1e-12
    sims = (x @ latest) / (norms * latest_norm)
    return sims


def _lag_similarity_stats(x: np.ndarray, max_lag: int) -> pl.DataFrame:
    n = x.shape[0]
    norms = np.linalg.norm(x, axis=1) + 1e-12
    max_lag = min(max_lag, n - 1)
    rows = []
    for lag in range(1, max_lag + 1):
        v1 = x[lag:]
        v0 = x[:-lag]
        sims = (v1 * v0).sum(axis=1) / (norms[lag:] * norms[:-lag])
        sims = np.nan_to_num(sims, nan=0.0)
        rows.append(
            {
                "lag": lag,
                "mean_sim": float(np.mean(sims)),
                "median_sim": float(np.median(sims)),
                "p25": float(np.quantile(sims, 0.25)),
                "p75": float(np.quantile(sims, 0.75)),
            }
        )
    return pl.DataFrame(rows)


def _suggest_lookback(lag_df: pl.DataFrame, threshold: float) -> int | None:
    if lag_df.is_empty():
        return None
    valid = lag_df.filter(pl.col("median_sim") >= threshold)
    if valid.is_empty():
        return None
    return int(valid["lag"].max())


def _optimize_lookback(
    batch_hist: list[int],
    sim_hist: np.ndarray,
    lookback_min: int,
    lookback_max: int,
    lookback_step: int,
    stability_lambda: float,
) -> pl.DataFrame:
    n = len(batch_hist)
    if n < lookback_min:
        return pl.DataFrame()
    results = []
    max_lb = min(lookback_max, n)
    for lb in range(lookback_min, max_lb + 1, lookback_step):
        window_sim = sim_hist[-lb:]
        mean_sim = float(np.mean(window_sim))
        std_sim = float(np.std(window_sim))
        median_sim = float(np.median(window_sim))
        score = mean_sim - stability_lambda * std_sim
        results.append(
            {
                "lookback": lb,
                "mean_sim": mean_sim,
                "median_sim": median_sim,
                "std_sim": std_sim,
                "score": score,
                "window_start_batch": int(batch_hist[-lb]),
                "window_end_batch": int(batch_hist[-1]),
            }
        )
    return pl.DataFrame(results)


def _train_val_split_from_lookback(
    batch_hist: list[int],
    lookback: int,
    val_ratio: float,
    sim_hist: np.ndarray,
) -> dict:
    if lookback > len(batch_hist):
        lookback = len(batch_hist)
    window_batches = batch_hist[-lookback:]
    window_sim = sim_hist[-lookback:]

    val_size = max(1, int(round(lookback * val_ratio)))
    train_size = max(1, lookback - val_size)
    train_batches = window_batches[:train_size]
    val_batches = window_batches[train_size:]
    train_sim = window_sim[:train_size]
    val_sim = window_sim[train_size:]

    def stats(arr: np.ndarray) -> dict:
        return {
            "mean": float(np.mean(arr)) if len(arr) else None,
            "median": float(np.median(arr)) if len(arr) else None,
            "p25": float(np.quantile(arr, 0.25)) if len(arr) else None,
            "p75": float(np.quantile(arr, 0.75)) if len(arr) else None,
            "std": float(np.std(arr)) if len(arr) else None,
        }

    return {
        "lookback": int(lookback),
        "train_batches": f"{train_batches[0]}-{train_batches[-1]}" if len(train_batches) else None,
        "val_batches": f"{val_batches[0]}-{val_batches[-1]}" if len(val_batches) else None,
        "train_size": int(len(train_batches)),
        "val_size": int(len(val_batches)),
        "train_similarity": stats(train_sim),
        "val_similarity": stats(val_sim),
    }


def _label_mse(df_label: pl.DataFrame, doc_targets: dict[int, float]) -> float | None:
    """Compute MSE between weighted label distribution and doc targets."""
    if df_label is None or df_label.is_empty():
        return None
    if "n_rows" not in df_label.columns:
        return None
    total_rows = df_label["n_rows"].sum()
    if total_rows == 0:
        return None
    mse = 0.0
    for class_id, target_pct in doc_targets.items():
        col = f"label_pct_{class_id}"
        if col not in df_label.columns:
            continue
        actual_pct = float((df_label[col] * df_label["n_rows"]).sum() / total_rows * 100.0)
        diff = actual_pct - target_pct
        mse += diff * diff
    return float(mse)


def _compute_tail_run(
    tf: str,
    tail_pct: float,
    head_pct: float,
    include_label_similarity: bool = False,
) -> dict:
    """Compute correlation outputs for a given tail exclusion percent."""
    # 1) Features per batch
    df_feat = _compute_batch_feature_matrix(
        tf, FEATURE_TARGET, exclude_head_pct=head_pct, exclude_tail_pct=tail_pct
    )
    batch_ids = _select_batch_ids(df_feat["batch_id"].to_list())
    df_feat = df_feat.filter(pl.col("batch_id").is_in(batch_ids)).sort("batch_id")

    # 2) Optional label distribution
    df_label = None
    if include_label_similarity:
        df_label = _compute_batch_label_distribution(
            tf, LABEL_TARGET, exclude_head_pct=head_pct, exclude_tail_pct=tail_pct
        )
        if df_label is not None:
            df_label = df_label.filter(pl.col("batch_id").is_in(batch_ids)).sort(
                "batch_id"
            )

    # 3) Build feature matrix and compute similarity
    X_feat = df_feat.drop("batch_id").to_numpy()
    X_feat = _zscore_matrix(X_feat)
    X_norm = _normalize_rows(X_feat)
    sim_feat = _cosine_similarity_to_latest(X_feat)

    df_sim = pl.DataFrame(
        {
            "batch_id": df_feat["batch_id"],
            "similarity_features": sim_feat,
        }
    )

    # 4) Label similarity (if available)
    if include_label_similarity and df_label is not None:
        X_label = df_label.drop(["batch_id", "n_rows"]).to_numpy()
        X_label = _zscore_matrix(X_label)
        sim_label = _cosine_similarity_to_latest(X_label)
        df_sim = df_sim.with_columns(pl.Series("similarity_labels", sim_label))

    # 5) Lag similarity summary (features)
    lag_df = _lag_similarity_stats(X_feat, MAX_LAG)

    # 5b) Optimize lookback window (features, latest batch only)
    batch_list = df_feat["batch_id"].to_list()
    lookback_df = _optimize_lookback(
        batch_hist=batch_list[:-1],
        sim_hist=sim_feat[:-1],
        lookback_min=LOOKBACK_MIN,
        lookback_max=LOOKBACK_MAX,
        lookback_step=LOOKBACK_STEP,
        stability_lambda=STABILITY_LAMBDA,
    )
    if lookback_df.is_empty():
        best_lookback = None
    else:
        best_row = lookback_df.sort("score", descending=True).head(1).to_dicts()[0]
        best_lookback = int(best_row["lookback"])

    split_info = (
        _train_val_split_from_lookback(
            batch_hist=batch_list[:-1],
            lookback=best_lookback or 0,
            val_ratio=VAL_RATIO,
            sim_hist=sim_feat[:-1],
        )
        if best_lookback
        else None
    )

    # 6) Top similar batches to latest
    df_top = (
        df_sim.sort("similarity_features", descending=True)
        .head(TOP_K_SIMILAR)
        .with_columns(
            (pl.col("batch_id") - int(df_feat["batch_id"].max())).alias(
                "lag_from_latest"
            )
        )
    )

    # 7) Per-batch lookback optimization (batch-by-batch)
    per_batch_records = []
    if len(batch_list) > 1:
        for i in range(1, len(batch_list)):
            pred_batch = batch_list[i]
            hist_batches = batch_list[:i]
            if len(hist_batches) < LOOKBACK_MIN:
                continue
            sim_hist = (X_norm[:i] @ X_norm[i]).astype(np.float64)
            lb_df = _optimize_lookback(
                batch_hist=hist_batches,
                sim_hist=sim_hist,
                lookback_min=LOOKBACK_MIN,
                lookback_max=LOOKBACK_MAX,
                lookback_step=LOOKBACK_STEP,
                stability_lambda=STABILITY_LAMBDA,
            )
            if lb_df.is_empty():
                continue
            best_row = lb_df.sort("score", descending=True).head(1).to_dicts()[0]
            best_lb = int(best_row["lookback"])
            split = _train_val_split_from_lookback(
                batch_hist=hist_batches,
                lookback=best_lb,
                val_ratio=VAL_RATIO,
                sim_hist=sim_hist,
            )
            per_batch_records.append(
                {
                    "batch_id": int(pred_batch),
                    "head_pct": float(head_pct),
                    "tail_pct": float(tail_pct),
                    "best_lookback": best_lb,
                    "best_score": float(best_row["score"]),
                    "mean_sim": float(best_row["mean_sim"]),
                    "median_sim": float(best_row["median_sim"]),
                    "std_sim": float(best_row["std_sim"]),
                    "window_start_batch": int(best_row["window_start_batch"]),
                    "window_end_batch": int(best_row["window_end_batch"]),
                    "train_batches": split["train_batches"],
                    "val_batches": split["val_batches"],
                    "train_size": split["train_size"],
                    "val_size": split["val_size"],
                    "train_sim_mean": split["train_similarity"]["mean"],
                    "val_sim_mean": split["val_similarity"]["mean"],
                }
            )

    per_batch_df = (
        pl.DataFrame(per_batch_records) if per_batch_records else pl.DataFrame()
    )

    # Tail summary for grid selection
    if not per_batch_df.is_empty():
        tail_summary = {
            "head_pct": float(head_pct),
            "tail_pct": float(tail_pct),
            "count": int(len(per_batch_df)),
            "best_score_mean": float(per_batch_df["best_score"].mean()),
            "best_score_median": float(per_batch_df["best_score"].median()),
            "best_score_p25": float(per_batch_df["best_score"].quantile(0.25)),
            "best_score_p75": float(per_batch_df["best_score"].quantile(0.75)),
            "best_lookback_median": float(per_batch_df["best_lookback"].median()),
            "best_lookback_p25": float(per_batch_df["best_lookback"].quantile(0.25)),
            "best_lookback_p75": float(per_batch_df["best_lookback"].quantile(0.75)),
        }
    else:
        tail_summary = {
            "head_pct": float(head_pct),
            "tail_pct": float(tail_pct),
            "count": 0,
            "best_score_mean": None,
            "best_score_median": None,
            "best_score_p25": None,
            "best_score_p75": None,
            "best_lookback_median": None,
            "best_lookback_p25": None,
            "best_lookback_p75": None,
        }

    return {
        "df_feat": df_feat,
        "df_label": df_label,
        "df_sim": df_sim,
        "lag_df": lag_df,
        "lookback_df": lookback_df,
        "df_top": df_top,
        "per_batch_df": per_batch_df,
        "tail_summary": tail_summary,
        "best_lookback": best_lookback,
        "split_info": split_info,
    }


# =============================================================================
# RUN
# =============================================================================
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

for tf in TIMEFRAMES:
    print(f"\n=== {tf} ===")
    out_dir = OUTPUT_DIR / tf
    out_dir.mkdir(parents=True, exist_ok=True)

    # Head grid search (label distribution MSE)
    head_summary_rows = []
    best_head_pct = None
    best_head_mse = None
    for head_pct in HEAD_GRID:
        df_label = _compute_batch_label_distribution(
            tf, LABEL_TARGET, exclude_head_pct=head_pct, exclude_tail_pct=0.0
        )
        if df_label is not None:
            batch_ids = _select_batch_ids(df_label["batch_id"].to_list())
            df_label = df_label.filter(pl.col("batch_id").is_in(batch_ids)).sort(
                "batch_id"
            )
        mse = _label_mse(df_label, DOC_TARGETS_8CLASS)
        n_rows = int(df_label["n_rows"].sum()) if df_label is not None else 0
        head_summary_rows.append(
            {
                "head_pct": float(head_pct),
                "label_mse": mse,
                "n_batches": int(len(df_label)) if df_label is not None else 0,
                "n_rows": n_rows,
            }
        )
        if mse is not None:
            if best_head_mse is None or mse < best_head_mse:
                best_head_mse = mse
                best_head_pct = head_pct
    if best_head_pct is None:
        best_head_pct = 0.0

    tail_runs = []
    per_batch_all = []
    tail_summary_rows = []

    # Grid search over tail exclusion percentages
    for tail_pct in TAIL_GRID:
        run = _compute_tail_run(
            tf, tail_pct, head_pct=best_head_pct, include_label_similarity=False
        )
        tail_runs.append((tail_pct, run))

        if not run["per_batch_df"].is_empty():
            per_batch_all.append(run["per_batch_df"])
        tail_summary_rows.append(run["tail_summary"])

    # Pick best tail by median best_score (tie -> smaller tail_pct)
    tail_summary_df = pl.DataFrame(tail_summary_rows)
    best_tail_pct = None
    if not tail_summary_df.is_empty():
        valid = tail_summary_df.filter(pl.col("best_score_median").is_not_null())
        if len(valid) > 0:
            best_tail_pct = (
                valid.sort(["best_score_median", "tail_pct"], descending=[True, False])
                .head(1)["tail_pct"][0]
            )

    if best_tail_pct is None:
        best_tail_pct = TAIL_GRID[0]

    # Recompute selected tail with label similarity (canonical outputs)
    selected_run = _compute_tail_run(
        tf, best_tail_pct, head_pct=best_head_pct, include_label_similarity=True
    )

    df_feat = selected_run["df_feat"]
    df_sim = selected_run["df_sim"]
    lag_df = selected_run["lag_df"]
    lookback_df = selected_run["lookback_df"]
    df_top = selected_run["df_top"]
    best_lookback = selected_run["best_lookback"]
    split_info = selected_run["split_info"]

    # Suggested lookback (lag stats)
    suggested = _suggest_lookback(lag_df, SIM_THRESHOLD)

    # Merge per-batch rows across tails
    per_batch_df = (
        pl.concat(per_batch_all).sort(["tail_pct", "batch_id"])
        if per_batch_all
        else pl.DataFrame()
    )

    summary = {
        "timeframe": tf,
        "feature_target": FEATURE_TARGET,
        "label_target": LABEL_TARGET,
        "head_grid": HEAD_GRID,
        "best_head_pct": float(best_head_pct),
        "head_select_metric": HEAD_SELECT_METRIC,
        "best_head_mse": best_head_mse,
        "tail_grid": TAIL_GRID,
        "best_tail_pct": float(best_tail_pct),
        "exclude_head_pct": float(best_head_pct),
        "exclude_tail_pct": float(best_tail_pct),
        "batch_count": len(df_feat),
        "feature_dim": df_feat.width - 1,
        "sim_threshold": SIM_THRESHOLD,
        "suggested_lookback_lag": suggested,
        "best_lookback": best_lookback,
        "val_ratio": VAL_RATIO,
        "train_val_split": split_info,
        "lookback_search": {
            "min": LOOKBACK_MIN,
            "max": LOOKBACK_MAX,
            "step": LOOKBACK_STEP,
            "stability_lambda": STABILITY_LAMBDA,
        },
        "latest_batch_id": int(df_feat["batch_id"].max()),
    }

    if not per_batch_df.is_empty():
        selected = per_batch_df.filter(pl.col("tail_pct") == float(best_tail_pct))
        if len(selected) > 0:
            summary["best_tail_stats"] = {
                "count": int(len(selected)),
                "best_score_median": float(selected["best_score"].median()),
                "best_score_p25": float(selected["best_score"].quantile(0.25)),
                "best_score_p75": float(selected["best_score"].quantile(0.75)),
                "best_lookback_median": float(selected["best_lookback"].median()),
                "best_lookback_p25": float(selected["best_lookback"].quantile(0.25)),
                "best_lookback_p75": float(selected["best_lookback"].quantile(0.75)),
                "first_batch_id": int(selected["batch_id"].min()),
                "last_batch_id": int(selected["batch_id"].max()),
            }

    # Save outputs
    df_sim.write_parquet(out_dir / "similarity_to_latest.parquet")
    lag_df.write_parquet(out_dir / "lag_similarity.parquet")
    if not lookback_df.is_empty():
        lookback_df.write_parquet(out_dir / "lookback_scores.parquet")
    df_top.write_parquet(out_dir / "top_similar_batches.parquet")
    if not per_batch_df.is_empty():
        per_batch_df.write_parquet(out_dir / "per_batch_lookback.parquet")
    if not tail_summary_df.is_empty():
        tail_summary_df.write_parquet(out_dir / "tail_grid_summary.parquet")
    head_summary_df = pl.DataFrame(head_summary_rows)
    if not head_summary_df.is_empty():
        head_summary_df.write_parquet(out_dir / "head_grid_summary.parquet")
    with open(out_dir / "summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    # Console output
    print(f"  Batches: {len(df_feat):,}")
    print(f"  Feature columns: {df_feat.width - 1}")
    if "similarity_labels" in df_sim.columns:
        print(f"  Label distribution: {LABEL_TARGET} (computed for selected tail)")
    else:
        print(f"  Label distribution: {LABEL_TARGET} not found, skipping")

    if head_summary_rows:
        print("\n  Head grid summary (label MSE):")
        for row in head_summary_rows:
            mse_val = row["label_mse"]
            mse_text = f"{mse_val:.2f}" if mse_val is not None else "n/a"
            print(f"    head={row['head_pct']:.2f} | label_mse={mse_text}")

    print(f"\n  Selected head: {best_head_pct:.2f}")
    if not tail_summary_df.is_empty():
        print("\n  Tail grid summary (median best_score):")
        summary_rows = (
            tail_summary_df.sort("tail_pct")
            .select(["tail_pct", "best_score_median", "best_lookback_median"])
            .to_dicts()
        )
        for row in summary_rows:
            print(
                f"    tail={row['tail_pct']:.2f} | median_score={row['best_score_median']:.4f} | "
                f"median_lookback={row['best_lookback_median']:.0f}"
            )

    print(f"\n  Selected tail: {best_tail_pct:.2f}")
    print(f"  Suggested lookback (median_sim >= {SIM_THRESHOLD}): {suggested}")
    if best_lookback:
        print(f"  Best lookback (latest batch stability score): {best_lookback}")
        if split_info:
            print(
                f"  Train: {split_info['train_batches']} | Val: {split_info['val_batches']}"
            )
    if not per_batch_df.is_empty():
        selected = per_batch_df.filter(pl.col("tail_pct") == float(best_tail_pct))
        if len(selected) > 0:
            p25 = selected["best_lookback"].quantile(0.25)
            p50 = selected["best_lookback"].median()
            p75 = selected["best_lookback"].quantile(0.75)
            first_id = int(selected["batch_id"].min())
            last_id = int(selected["batch_id"].max())
            print(
                "  Per-batch lookback (p25/median/p75): "
                f"{p25:.0f}/{p50:.0f}/{p75:.0f} from {first_id} to {last_id}"
            )
    print(f"  Saved: {out_dir}")
