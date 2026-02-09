#%%
# =============================================================================
# HTF LABEL ANALYSIS (TEMP)
# =============================================================================
# Goal: analyze end-of-batch close distance (optional diagnostics for 8-class work).
#
# Uses existing labeled data:
#   data/htf_8class_labels/{tf}/batch_*.parquet
# =============================================================================

from pathlib import Path

import polars as pl

PROJECT_ROOT = Path("..").resolve()
DATA_DIR = PROJECT_ROOT / "data"
LABELS_DIR = DATA_DIR / "htf_8class_labels"

TIMEFRAMES = ["5m", "15m"]
TARGET = "target_8class"

# Candidate flat thresholds (absolute end_return)
# Example: 0.001 = 0.10%
THRESHOLDS = [0.0002, 0.0005, 0.001, 0.0015, 0.002, 0.003]


def load_labeled_with_end_return(tf: str) -> pl.DataFrame:
    """Load labeled rows and compute end_return to batch close."""
    path = LABELS_DIR / tf / "batch_*.parquet"
    if not path.parent.exists():
        raise FileNotFoundError(f"Missing labels dir: {path.parent}")

    df = (
        pl.scan_parquet(str(path))
        .select(["timestamp", "batch_id", "close", TARGET])
        .filter(pl.col(TARGET) >= 0)
    )

    # Close at end of each batch
    batch_close = df.group_by("batch_id").agg(
        pl.col("close").sort_by("timestamp").last().alias("close_end")
    )

    df = (
        df.join(batch_close, on="batch_id", how="left")
        .with_columns(
            [
                ((pl.col("close_end") - pl.col("close")) / pl.col("close")).alias(
                    "end_return"
                ),
                (
                    (pl.col("close_end") - pl.col("close")).abs()
                    / pl.col("close")
                ).alias("abs_end_return"),
            ]
        )
        .collect()
        .sort(["batch_id", "timestamp"])
    )
    return df


def summarize_quantiles(df: pl.DataFrame, tf: str) -> None:
    qs = [0.1, 0.25, 0.5, 0.75, 0.9, 0.95, 0.99]
    exprs = [pl.col("abs_end_return").quantile(q).alias(f"q{int(q*100)}") for q in qs]
    out = df.select(exprs)
    print(f"\n{tf} | abs_end_return quantiles (as %):")
    for col in out.columns:
        val = out[col][0] * 100
        print(f"  {col}: {val:.4f}%")


def summarize_thresholds(df: pl.DataFrame, tf: str) -> pl.DataFrame:
    rows = []
    for thr in THRESHOLDS:
        flat = (pl.col("abs_end_return") <= thr).mean()
        up = (pl.col("end_return") > thr).mean()
        down = (pl.col("end_return") < -thr).mean()
        stats = df.select([flat.alias("flat"), up.alias("up"), down.alias("down")])
        rows.append(
            {
                "threshold": thr,
                "flat_pct": float(stats["flat"][0] * 100),
                "up_pct": float(stats["up"][0] * 100),
                "down_pct": float(stats["down"][0] * 100),
            }
        )
    return pl.DataFrame(rows)


def summarize_by_class(df: pl.DataFrame, thr: float) -> pl.DataFrame:
    """Return per-base-class finish distribution for a chosen threshold."""
    return (
        df.group_by(TARGET)
        .agg(
            pl.len().alias("n"),
            (pl.col("end_return") > thr).mean().alias("up_pct"),
            (pl.col("end_return") < -thr).mean().alias("down_pct"),
            (pl.col("abs_end_return") <= thr).mean().alias("flat_pct"),
        )
        .with_columns(
            [
                (pl.col("up_pct") * 100).alias("up_pct"),
                (pl.col("down_pct") * 100).alias("down_pct"),
                (pl.col("flat_pct") * 100).alias("flat_pct"),
            ]
        )
        .sort(TARGET)
    )


#%%
# =============================================================================
# RUN ANALYSIS
# =============================================================================

for tf in TIMEFRAMES:
    df_tf = load_labeled_with_end_return(tf)
    print(f"\n{'=' * 70}")
    print(f"{tf} | rows={len(df_tf):,} | batches={df_tf['batch_id'].n_unique():,}")
    summarize_quantiles(df_tf, tf)
    print("\nThreshold sweep (finish state %):")
    print(summarize_thresholds(df_tf, tf))

# Example per-class distribution at a chosen threshold
CHOSEN_THR = 0.001  # 0.10%
print(f"\nPer-class finish distribution at threshold={CHOSEN_THR:.4%}")
for tf in TIMEFRAMES:
    df_tf = load_labeled_with_end_return(tf)
    print(f"\n{tf}")
    print(summarize_by_class(df_tf, CHOSEN_THR))
