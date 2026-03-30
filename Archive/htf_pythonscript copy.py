# %% [markdown]
# # HTF Strategy Backtest
#
# ## Data Preparation Summary
#
#
# | Timeframe | Batches | Rows/Batch | Total Rows | Combined File |
# |-----------|---------|------------|------------|---------------|
# | 1m | 5,574 | 480 | 2,675,634 | `1m_HTF_combined.parquet` (41.6 MB) |
# for now only 1m timeframe since it prove best performance
# | 5m | 5,574 | 96 | 535,060 | `5m_HTF_combined.parquet` (8.9 MB) |
# | 15m | 5,574 | 32 | 178,354 | `15m_HTF_combined.parquet` (3.1 MB) |
# 15m timeframe also need computation in order to make labels
#
# **Data structure:**
# - Each batch covers one 8h period (00:00-08:00, 08:00-16:00, or 16:00-00:00 UTC)
# - Columns: `timestamp`, `open`, `high`, `low`, `close`, `volume`, `period_8h_start`, `batch_id`
#
#
# **File locations:**
# - Individual batches: `data/htf_backtest/{tf}_HTF_backtest_XXXX.parquet`
# - Combined files: `data/htf_backtest/{tf}_HTF_combined.parquet`

# %%
# =============================================================================
# CELL 2: SETUP & PATHS (No data loading - just config)
# =============================================================================
import gc
import hashlib
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

import polars as pl


def resolve_project_root() -> Path:
    """Resolve repo root robustly for both notebook-style and script execution."""
    candidates: list[Path] = []

    if "__file__" in globals():
        file_path = Path(__file__).resolve()
        candidates.extend([file_path.parent.parent, file_path.parent])

    cwd = Path.cwd().resolve()
    candidates.extend([cwd, cwd.parent, cwd.parent.parent])

    seen: set[Path] = set()
    for cand in candidates:
        try:
            cand = cand.resolve()
        except FileNotFoundError:
            continue
        if cand in seen:
            continue
        seen.add(cand)
        if (cand / "notebooks" / "htf_pythonscript.py").exists():
            return cand
        if (cand / "data").exists() and (cand / "fetchingByBit").exists():
            return cand

    return Path("..").resolve()


# Project paths
PROJECT_ROOT = resolve_project_root()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
DATA_DIR = PROJECT_ROOT / "data"
HTF_BACKTEST_DIR = DATA_DIR / "htf_backtest"
HTF_BACKTEST_SHIFT4H_DIR = DATA_DIR / "htf_backtest_shift4h"
HTF_FEATURES_DIR = DATA_DIR / "htf_features"
HTF_FEATURES_SHIFT4H_DIR = DATA_DIR / "htf_features_shift4h"
HTF_LABELS_DIR = DATA_DIR / "htf_4class_labels"
HTF_LABELS_SHIFT4H_DIR = DATA_DIR / "htf_4class_labels_shift4h"
HTF_OPTIMIZED_DIR = DATA_DIR / "htf_optimized"
HTF_OPTIMIZED_SHIFT4H_DIR = DATA_DIR / "htf_optimized_shift4h"
HTF_WITH_HELPERS_DIR = DATA_DIR / "htf_with_helpers"
HTF_WITH_HELPERS_SHIFT4H_DIR = DATA_DIR / "htf_with_helpers_shift4h"
RAW_DATA_DIR = PROJECT_ROOT / "fetchingByBit"

# Create ALL required dirs (robust - works from scratch)
DATA_DIR.mkdir(parents=True, exist_ok=True)
HTF_BACKTEST_DIR.mkdir(parents=True, exist_ok=True)
HTF_BACKTEST_SHIFT4H_DIR.mkdir(parents=True, exist_ok=True)
HTF_FEATURES_DIR.mkdir(parents=True, exist_ok=True)
HTF_FEATURES_SHIFT4H_DIR.mkdir(parents=True, exist_ok=True)
HTF_LABELS_DIR.mkdir(parents=True, exist_ok=True)
HTF_LABELS_SHIFT4H_DIR.mkdir(parents=True, exist_ok=True)
HTF_OPTIMIZED_DIR.mkdir(parents=True, exist_ok=True)
HTF_OPTIMIZED_SHIFT4H_DIR.mkdir(parents=True, exist_ok=True)
HTF_WITH_HELPERS_DIR.mkdir(parents=True, exist_ok=True)
HTF_WITH_HELPERS_SHIFT4H_DIR.mkdir(parents=True, exist_ok=True)

# Active repair scope
ENABLE_5M_PIPELINE = False
PIPELINE_ARTIFACT_VERSION = "2026-03-06-repair-01"
ARTIFACT_STAGE_VERSIONS = {
    "shift4h_combined": f"{PIPELINE_ARTIFACT_VERSION}-shift4h-combined-v1",
    "shift4h_metrics": f"{PIPELINE_ARTIFACT_VERSION}-shift4h-metrics-v1",
    "labels": f"{PIPELINE_ARTIFACT_VERSION}-labels-v1",
    "shift4h_features": f"{PIPELINE_ARTIFACT_VERSION}-shift4h-features-v1",
    "shift4h_helpers": f"{PIPELINE_ARTIFACT_VERSION}-shift4h-helpers-v1",
}

# Timeframes we're working with (1m)
HTF_TIMEFRAMES = ["1m", "15m"]
SHIFT4H_TIMEFRAMES = ["1m", "15m"]
FAMILY_ACTIVE_SCOPE = {
    "B": {
        "family": "B",
        "shift_hours": 0,
        "backtest_dir": HTF_BACKTEST_DIR,
        "features_dir": HTF_FEATURES_DIR,
        "labels_dir": HTF_LABELS_DIR,
        "optimized_dir": HTF_OPTIMIZED_DIR,
        "helpers_dir": HTF_WITH_HELPERS_DIR,
    },
    "C": {
        "family": "C",
        "shift_hours": 4,
        "backtest_dir": HTF_BACKTEST_SHIFT4H_DIR,
        "features_dir": HTF_FEATURES_SHIFT4H_DIR,
        "labels_dir": HTF_LABELS_SHIFT4H_DIR,
        "optimized_dir": HTF_OPTIMIZED_SHIFT4H_DIR,
        "helpers_dir": HTF_WITH_HELPERS_SHIFT4H_DIR,
    },
}


def bars_per_half(tf: str) -> int:
    return TF_CONFIG[tf]["bars_per_8h"] // 2


def family_scope(family: str) -> dict:
    return FAMILY_ACTIVE_SCOPE[family]


def family_metadata_cols(include_timestamp: bool = True) -> list[str]:
    cols = [
        "batch_id",
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
        "bar_in_batch_norm",
    ]
    return (["timestamp"] + cols) if include_timestamp else cols


LABEL_SHARED_META_COLS = [
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
    "bar_in_batch_norm",
]


def project_relative_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT))
    except Exception:
        return str(path)


def load_json_safe(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return None


def fingerprint_paths(paths: list[Path]) -> dict:
    entries: list[tuple[str, int, int]] = []
    for path in sorted({Path(p) for p in paths}, key=lambda p: str(p)):
        if not path.exists():
            continue
        stat = path.stat()
        entries.append(
            (
                project_relative_path(path),
                int(stat.st_mtime_ns),
                int(stat.st_size),
            )
        )

    digest = hashlib.sha256()
    for rel_path, mtime_ns, size_bytes in entries:
        digest.update(f"{rel_path}|{mtime_ns}|{size_bytes}\n".encode("utf-8"))

    return {
        "count": int(len(entries)),
        "latest_mtime_ns": int(max((e[1] for e in entries), default=0)),
        "total_size_bytes": int(sum(e[2] for e in entries)),
        "digest": digest.hexdigest(),
    }


def fingerprint_batch_dir(directory: Path) -> dict:
    return fingerprint_paths(sorted(directory.glob("batch_*.parquet")))


def schema_columns_for_batch_dir(directory: Path) -> list[str]:
    files = sorted(directory.glob("batch_*.parquet"))
    if not files:
        return []
    return pl.scan_parquet(str(files[0])).collect_schema().names()


def find_batch_missing_required_columns(
    directory: Path, required_cols: set[str]
) -> dict | None:
    for batch_path in sorted(directory.glob("batch_*.parquet")):
        cols = set(pl.scan_parquet(str(batch_path)).collect_schema().names())
        missing = sorted(required_cols - cols)
        if missing:
            return {
                "path": project_relative_path(batch_path),
                "missing": missing,
            }
    return None


def clear_artifact_target(path: Path) -> list[str]:
    removed: list[str] = []
    if not path.exists():
        return removed

    if path.is_dir():
        for child in sorted(path.iterdir(), key=lambda p: p.name):
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
            removed.append(project_relative_path(child))
        return removed

    path.unlink()
    removed.append(project_relative_path(path))
    return removed


def artifact_rebuild_reasons(
    *,
    meta_path: Path,
    artifact_version: str,
    family: str,
    timeframe: str,
    source_fingerprint: dict,
    schema_columns: list[str] | None = None,
) -> list[str]:
    meta = load_json_safe(meta_path)
    if meta is None:
        return ["missing_meta"]

    reasons: list[str] = []
    if meta.get("artifact_version") != artifact_version:
        reasons.append("artifact_version")
    if meta.get("family") != family:
        reasons.append("family")
    if meta.get("timeframe") != timeframe:
        reasons.append("timeframe")
    if meta.get("source_fingerprint") != source_fingerprint:
        reasons.append("source_fingerprint")
    if schema_columns is not None and sorted(meta.get("schema_columns", [])) != sorted(
        schema_columns
    ):
        reasons.append("schema_columns")
    return reasons


def artifact_meta_payload(
    *,
    artifact_version: str,
    family: str,
    timeframe: str,
    source_fingerprint: dict,
    schema_columns: list[str],
    rebuild_mode: str,
    extra: dict | None = None,
) -> dict:
    payload = {
        "artifact_version": artifact_version,
        "family": family,
        "timeframe": timeframe,
        "source_fingerprint": source_fingerprint,
        "schema_columns": schema_columns,
        "rebuild_mode": rebuild_mode,
        "updated_at": f"{datetime.utcnow().isoformat()}Z",
    }
    if extra:
        payload.update(extra)
    return payload


def prepare_stage_rebuild(
    *,
    stage_name: str,
    meta_path: Path,
    artifact_version: str,
    family: str,
    timeframe: str,
    source_fingerprint: dict,
    schema_columns: list[str],
    output_targets: list[Path],
    inspect_batch_dir: Path | None = None,
    required_batch_columns: set[str] | None = None,
    full_rebuild_reasons: set[str] | None = None,
) -> tuple[list[str], str]:
    reasons = artifact_rebuild_reasons(
        meta_path=meta_path,
        artifact_version=artifact_version,
        family=family,
        timeframe=timeframe,
        source_fingerprint=source_fingerprint,
        schema_columns=schema_columns,
    )

    legacy_schema = None
    if inspect_batch_dir is not None and required_batch_columns:
        if inspect_batch_dir.exists() and list(inspect_batch_dir.glob("batch_*.parquet")):
            legacy_schema = find_batch_missing_required_columns(
                inspect_batch_dir, required_batch_columns
            )
            if legacy_schema is not None:
                reasons.append(
                    "legacy_schema:"
                    f"{legacy_schema['path']} missing={','.join(legacy_schema['missing'])}"
                )

    def _reason_key(reason: str) -> str:
        return "legacy_schema" if reason.startswith("legacy_schema:") else reason

    destructive_reason_keys = (
        {_reason_key(reason) for reason in reasons}
        if full_rebuild_reasons is None
        else set(full_rebuild_reasons)
    )
    should_full_rebuild = any(_reason_key(reason) in destructive_reason_keys for reason in reasons)

    rebuild_mode = "full" if should_full_rebuild else "incremental_tail"
    if should_full_rebuild:
        for target in output_targets:
            clear_artifact_target(target)
        print(
            f"  {stage_name} rebuild mode: full "
            f"({', '.join(reasons)})"
        )
    elif reasons:
        print(
            f"  {stage_name} rebuild mode: incremental_tail "
            f"({', '.join(reasons)})"
        )
    else:
        print(f"  {stage_name} rebuild mode: incremental_tail")

    return reasons, rebuild_mode

# Quick validation - check files exist
print("=" * 70)
print("DATA FILES CHECK")
print("=" * 70)
for tf in HTF_TIMEFRAMES:
    ohlcv_path = HTF_BACKTEST_DIR / f"{tf}_HTF_combined.parquet"
    feature_path = HTF_FEATURES_DIR / tf

    ohlcv_exists = "✓" if ohlcv_path.exists() else "✗"
    feature_exists = (
        "✓"
        if feature_path.exists() and list(feature_path.glob("batch_*.parquet"))
        else "○ (will compute)"
    )

    # Get row counts without loading full data
    if ohlcv_path.exists():
        rows = pl.scan_parquet(ohlcv_path).select(pl.len()).collect().item()
        print(f"{tf}: OHLCV {ohlcv_exists} ({rows:,} rows), Features {feature_exists}")
    else:
        print(f"{tf}: OHLCV {ohlcv_exists}, Features {feature_exists}")

print("\n✓ Setup complete. Run next cells to process data.")

# %%
# =============================================================================
# CELL 2.5: ROBUST HTF COMBINED FILE GENERATION
# =============================================================================
# For each timeframe in HTF_TIMEFRAMES:
#   1. Check if {tf}_HTF_combined.parquet exists
#   2. Compare against raw source data (fetchingByBit/sorted-{tf}-bybit-linear/)
#   3. Create/update if raw data is newer or has more rows
#
# This ensures combined files are always in sync with fetched data.
# =============================================================================

from datetime import timedelta
from pathlib import Path

import polars as pl

# Configuration
DATE_START = datetime(2021, 1, 1)
# Use a rolling end bound so combined files can extend with newly fetched data.
DATE_END = datetime.utcnow() + timedelta(days=1)
FORCE_RECREATE_ALL = False  # Set True to force regenerate everything
# Production continuity: update combined file whenever raw data advanced.
# Set to 8.0 to require one full 8h block before refresh.
MIN_RAW_LEAD_HOURS_FOR_UPDATE = 0.0

# Timeframe config: how many bars per 8h batch
TF_CONFIG = {
    "1m": {"bars_per_8h": 480, "raw_dir": "sorted-1m-bybit-linear"},
    "5m": {"bars_per_8h": 96, "raw_dir": "sorted-5m-bybit-linear"},
    "15m": {"bars_per_8h": 32, "raw_dir": "sorted-15m-bybit-linear"},
    "1h": {"bars_per_8h": 8, "raw_dir": "sorted-1h-bybit-linear"},
    "4h": {"bars_per_8h": 2, "raw_dir": "sorted-4h-bybit-linear"},
}


def add_family_metadata(
    df: pl.DataFrame,
    tf: str,
    family: str,
    family_period_col: str,
    family_batch_col: str,
) -> pl.DataFrame:
    """Attach family-aware metadata columns to HTF rows."""
    half_bars = bars_per_half(tf)
    period_expr = pl.col(family_period_col)
    batch_expr = pl.col(family_batch_col)

    df = df.with_columns(
        [
            pl.lit(family).alias("batch_family"),
            batch_expr.cast(pl.Int32).alias("family_batch_id"),
            period_expr.dt.replace_time_zone("UTC")
            .cast(pl.Datetime("us", "UTC"))
            .alias("family_period_start"),
            (period_expr + timedelta(hours=8))
            .dt.replace_time_zone("UTC")
            .cast(pl.Datetime("us", "UTC"))
            .alias("family_period_end"),
            (pl.col("timestamp").rank("ordinal").over(family_batch_col) - 1)
            .cast(pl.Int32)
            .alias("family_bar_pos"),
        ]
    )

    if "period_8h_start" not in df.columns:
        df = df.with_columns(
            period_expr.dt.replace_time_zone("UTC")
            .cast(pl.Datetime("us", "UTC"))
            .alias("period_8h_start")
        )
    if "batch_id" not in df.columns:
        df = df.with_columns(batch_expr.cast(pl.Int32).alias("batch_id"))

    base_period_col = "source_base_period_start"
    base_batch_col = "source_base_batch_id"
    if base_period_col not in df.columns:
        df = df.with_columns(
            pl.col("period_8h_start").cast(pl.Datetime("us", "UTC")).alias(base_period_col)
        )
    if base_batch_col not in df.columns:
        df = df.with_columns(pl.col("batch_id").cast(pl.Int32).alias(base_batch_col))

    df = df.with_columns(
        [
            pl.when(
                pl.col("timestamp").dt.replace_time_zone(None)
                < (pl.col(base_period_col).dt.replace_time_zone(None) + timedelta(hours=4))
            )
            .then(pl.lit("L"))
            .otherwise(pl.lit("F"))
            .alias("source_half_in_base"),
            (pl.col("family_bar_pos") < half_bars).alias("is_label_half"),
            (
                pl.col("family_bar_pos").cast(pl.Float64)
                / max(1, TF_CONFIG[tf]["bars_per_8h"] - 1)
            ).alias("bar_in_batch_norm"),
        ]
    )

    return df


SHIFT4H_RECOMPUTED_COLS = {
    "batch_family",
    "family_batch_id",
    "family_period_start",
    "family_period_end",
    "family_bar_pos",
    "source_half_in_base",
    "is_label_half",
    "bar_in_batch_norm",
}
SHIFT4H_COMBINED_OUTPUT_COLS = [
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "period_8h_start",
    "batch_id",
    "batch_family",
    "family_batch_id",
    "family_period_start",
    "family_period_end",
    "family_bar_pos",
    "source_base_batch_id",
    "source_base_period_start",
    "source_half_in_base",
    "is_label_half",
    "bar_in_batch_norm",
]


def _shift4h_combined_meta_path(tf: str) -> Path:
    return HTF_BACKTEST_SHIFT4H_DIR / f"{tf}_HTF_combined_meta.json"


def _assert_shift4h_combined_invariants(df: pl.DataFrame, tf: str) -> None:
    half = bars_per_half(tf)
    batch_stats = (
        df.group_by("batch_id")
        .agg(
            [
                pl.len().alias("n_rows"),
                pl.col("family_period_start").n_unique().alias("n_family_periods"),
                pl.col("family_bar_pos").min().alias("min_pos"),
                pl.col("family_bar_pos").max().alias("max_pos"),
                pl.col("family_bar_pos").n_unique().alias("n_unique_pos"),
            ]
        )
        .sort("batch_id")
    )
    bad_family_periods = int(
        len(batch_stats.filter(pl.col("n_family_periods") != 1))
    )
    bad_bar_windows = int(
        len(
            batch_stats.filter(
                (pl.col("min_pos") != 0)
                | (pl.col("max_pos") != (pl.col("n_rows") - 1))
                | (pl.col("n_unique_pos") != pl.col("n_rows"))
                | (pl.col("max_pos") >= TF_CONFIG[tf]["bars_per_8h"])
            )
        )
    )
    bad_first = int(
        df.filter(
            (pl.col("family_bar_pos") < half)
            & (
                (pl.col("source_base_batch_id") != pl.col("batch_id"))
                | (pl.col("source_half_in_base") != "F")
            )
        )
        .select(pl.len())
        .item()
    )
    bad_second = int(
        df.filter(
            (pl.col("family_bar_pos") >= half)
            & (
                (pl.col("source_base_batch_id") != (pl.col("batch_id") + 1))
                | (pl.col("source_half_in_base") != "L")
            )
        )
        .select(pl.len())
        .item()
    )
    if any([bad_family_periods, bad_bar_windows, bad_first, bad_second]):
        raise AssertionError(
            "Shift4H combined invariant failure for "
            f"{tf}: family_periods={bad_family_periods}, "
            f"bar_windows={bad_bar_windows}, "
            f"first_half_mapping={bad_first}, second_half_mapping={bad_second}"
        )


def build_shift4h_combined_from_base(tf: str) -> dict:
    """Build shifted 4h family C from base family B combined rows."""
    base_path = HTF_BACKTEST_DIR / f"{tf}_HTF_combined.parquet"
    output_path = HTF_BACKTEST_SHIFT4H_DIR / f"{tf}_HTF_combined.parquet"
    meta_path = _shift4h_combined_meta_path(tf)
    if not base_path.exists():
        return {"exists": False, "reason": f"missing_base:{base_path}"}

    source_fingerprint = {
        "base_combined": fingerprint_paths([base_path]),
    }
    rebuild_reasons = artifact_rebuild_reasons(
        meta_path=meta_path,
        artifact_version=ARTIFACT_STAGE_VERSIONS["shift4h_combined"],
        family="C",
        timeframe=tf,
        source_fingerprint=source_fingerprint,
        schema_columns=SHIFT4H_COMBINED_OUTPUT_COLS,
    )
    rebuild_mode = "full" if rebuild_reasons else "current"
    if not rebuild_reasons and output_path.exists():
        stats = (
            pl.scan_parquet(output_path)
            .select(
                [
                    pl.len().alias("total_rows"),
                    pl.col("batch_id").n_unique().alias("n_batches"),
                    pl.col("timestamp").min().alias("min_ts"),
                    pl.col("timestamp").max().alias("max_ts"),
                ]
            )
            .collect()
        )
        return {
            "exists": True,
            "path": output_path,
            "meta_path": meta_path,
            "skipped": True,
            "rebuild_mode": rebuild_mode,
            "rebuild_reasons": [],
            "total_rows": int(stats["total_rows"].item()),
            "n_batches": int(stats["n_batches"].item()),
            "min_ts": stats["min_ts"].item(),
            "max_ts": stats["max_ts"].item(),
        }

    clear_artifact_target(output_path)
    clear_artifact_target(meta_path)

    base_df = pl.read_parquet(base_path).sort("timestamp")
    if base_df.is_empty():
        return {"exists": False, "reason": "empty_base"}

    min_base_start = base_df["period_8h_start"].min()
    if min_base_start is None:
        return {"exists": False, "reason": "null_min_base_start"}
    min_base_start_naive = (
        min_base_start.replace(tzinfo=None)
        if hasattr(min_base_start, "tzinfo") and min_base_start.tzinfo is not None
        else min_base_start
    )

    shifted_start = (
        (pl.col("timestamp").dt.replace_time_zone(None) - timedelta(hours=4))
        .dt.truncate("8h")
        + timedelta(hours=4)
    )
    df = base_df.with_columns(shifted_start.alias("family_period_start_raw"))
    df = df.filter(
        pl.col("family_period_start_raw")
        >= (pl.lit(min_base_start_naive) + timedelta(hours=4))
    )
    if df.is_empty():
        return {"exists": False, "reason": "empty_shifted"}

    batch_mapping = (
        df.select("family_period_start_raw")
        .unique()
        .sort("family_period_start_raw")
        .with_row_index("shift_family_batch_id")
        .with_columns((pl.col("shift_family_batch_id") + 1).cast(pl.Int32))
    )
    inherited_family_cols = [
        col for col in SHIFT4H_RECOMPUTED_COLS if col in df.columns
    ]
    if inherited_family_cols:
        df = df.drop(inherited_family_cols)
    df = df.join(batch_mapping, on="family_period_start_raw", how="left")
    df = add_family_metadata(
        df=df,
        tf=tf,
        family="C",
        family_period_col="family_period_start_raw",
        family_batch_col="shift_family_batch_id",
    )
    df = df.with_columns(
        [
            pl.col("family_period_start").alias("period_8h_start"),
            pl.col("family_batch_id").alias("batch_id"),
        ]
    )
    df_final = df.select(SHIFT4H_COMBINED_OUTPUT_COLS).sort(["batch_id", "timestamp"])
    _assert_shift4h_combined_invariants(df_final, tf)

    df_final.write_parquet(output_path)
    with open(meta_path, "w") as f:
        json.dump(
            artifact_meta_payload(
                artifact_version=ARTIFACT_STAGE_VERSIONS["shift4h_combined"],
                family="C",
                timeframe=tf,
                source_fingerprint=source_fingerprint,
                schema_columns=SHIFT4H_COMBINED_OUTPUT_COLS,
                rebuild_mode="full",
                extra={
                    "rebuild_reasons": rebuild_reasons,
                    "path": project_relative_path(output_path),
                    "total_rows": int(len(df_final)),
                    "n_batches": int(df_final["batch_id"].n_unique()),
                },
            ),
            f,
            indent=2,
        )
    return {
        "exists": True,
        "path": output_path,
        "meta_path": meta_path,
        "skipped": False,
        "rebuild_mode": "full",
        "rebuild_reasons": rebuild_reasons,
        "total_rows": len(df_final),
        "n_batches": int(df_final["batch_id"].n_unique()),
        "min_ts": df_final["timestamp"].min(),
        "max_ts": df_final["timestamp"].max(),
    }


def ensure_base_combined_family_metadata(tf: str) -> dict:
    """Ensure base combined parquet carries current family metadata columns."""
    base_path = HTF_BACKTEST_DIR / f"{tf}_HTF_combined.parquet"
    if not base_path.exists():
        return {"exists": False, "reason": f"missing_base:{base_path}"}

    df = pl.read_parquet(base_path)
    required = {
        "batch_family",
        "family_batch_id",
        "family_period_start",
        "family_period_end",
        "family_bar_pos",
        "source_base_batch_id",
        "source_base_period_start",
        "source_half_in_base",
        "is_label_half",
        "bar_in_batch_norm",
    }
    if required.issubset(set(df.columns)):
        return {"exists": True, "path": base_path, "updated": False}

    df = add_family_metadata(
        df=df,
        tf=tf,
        family="B",
        family_period_col="period_8h_start",
        family_batch_col="batch_id",
    ).select(
        [
            "timestamp",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "period_8h_start",
            "batch_id",
            "batch_family",
            "family_batch_id",
            "family_period_start",
            "family_period_end",
            "family_bar_pos",
            "source_base_batch_id",
            "source_base_period_start",
            "source_half_in_base",
            "is_label_half",
            "bar_in_batch_norm",
        ]
    ).sort(["batch_id", "timestamp"])
    df.write_parquet(base_path)
    return {"exists": True, "path": base_path, "updated": True}


def get_raw_data_info(tf: str) -> dict:
    """Get info about raw source data for a timeframe."""
    if tf not in TF_CONFIG:
        return {"exists": False, "error": f"Unknown timeframe: {tf}"}

    raw_dir = RAW_DATA_DIR / TF_CONFIG[tf]["raw_dir"]
    if not raw_dir.exists():
        return {"exists": False, "error": f"Raw dir not found: {raw_dir}"}

    files = sorted(raw_dir.glob("*.parquet"))
    if not files:
        return {"exists": False, "error": f"No parquet files in {raw_dir}"}

    # Scan all files lazily to get row count and date range
    lf = pl.scan_parquet(raw_dir / "*.parquet")
    stats = lf.select(
        [
            pl.len().alias("total_rows"),
            pl.col("timestamp").min().alias("min_ts"),
            pl.col("timestamp").max().alias("max_ts"),
        ]
    ).collect()

    return {
        "exists": True,
        "raw_dir": raw_dir,
        "n_files": len(files),
        "total_rows": stats["total_rows"].item(),
        "min_ts": stats["min_ts"].item(),
        "max_ts": stats["max_ts"].item(),
    }


def get_combined_info(tf: str) -> dict:
    """Get info about existing combined file."""
    combined_path = HTF_BACKTEST_DIR / f"{tf}_HTF_combined.parquet"

    if not combined_path.exists():
        return {"exists": False, "path": combined_path}

    lf = pl.scan_parquet(combined_path)
    stats = lf.select(
        [
            pl.len().alias("total_rows"),
            pl.col("timestamp").min().alias("min_ts"),
            pl.col("timestamp").max().alias("max_ts"),
            pl.col("batch_id").max().alias("max_batch"),
        ]
    ).collect()

    return {
        "exists": True,
        "path": combined_path,
        "total_rows": stats["total_rows"].item(),
        "min_ts": stats["min_ts"].item(),
        "max_ts": stats["max_ts"].item(),
        "max_batch": stats["max_batch"].item(),
    }


def create_combined_file(tf: str, raw_info: dict) -> dict:
    """Create or recreate the combined file for a timeframe."""
    bars_per_8h = TF_CONFIG[tf]["bars_per_8h"]
    output_path = HTF_BACKTEST_DIR / f"{tf}_HTF_combined.parquet"

    # Load all raw data
    df_raw = pl.read_parquet(raw_info["raw_dir"] / "*.parquet")

    # Normalize timestamp and filter date range
    df = (
        df_raw.with_columns(
            pl.col("timestamp").dt.replace_time_zone(None).alias("ts_norm")
        )
        .filter((pl.col("ts_norm") >= DATE_START) & (pl.col("ts_norm") < DATE_END))
        .sort("ts_norm")
    )

    # Guard against overlapping raw source files:
    # keep one row per normalized timestamp (latest row wins).
    # This prevents oversized batches when raw batches overlap in time.
    rows_before_dedup = len(df)
    df = df.unique(subset=["ts_norm"], keep="last", maintain_order=True)
    rows_after_dedup = len(df)
    duplicate_rows_removed = rows_before_dedup - rows_after_dedup

    # Compute period_8h_start (floor to nearest 8h boundary)
    df = df.with_columns((pl.col("ts_norm").dt.truncate("8h")).alias("period_8h_start"))

    # Assign batch_id (sequential, starting from 1)
    batch_mapping = (
        df.select("period_8h_start")
        .unique()
        .sort("period_8h_start")
        .with_row_index("batch_id")
        .with_columns((pl.col("batch_id") + 1).cast(pl.Int32))
    )

    df = df.join(batch_mapping, on="period_8h_start", how="left")

    df = add_family_metadata(
        df=df,
        tf=tf,
        family="B",
        family_period_col="period_8h_start",
        family_batch_col="batch_id",
    )

    # Select and order columns to match expected format
    df_final = df.select(
        [
            "timestamp",
            pl.col("open").cast(pl.Float64),
            pl.col("high").cast(pl.Float64),
            pl.col("low").cast(pl.Float64),
            pl.col("close").cast(pl.Float64),
            pl.col("volume").cast(pl.Float64),
            pl.col("period_8h_start")
            .dt.replace_time_zone("UTC")
            .cast(pl.Datetime("us", "UTC")),
            "batch_id",
            "batch_family",
            "family_batch_id",
            "family_period_start",
            "family_period_end",
            "family_bar_pos",
            "source_base_batch_id",
            "source_base_period_start",
            "source_half_in_base",
            "is_label_half",
            "bar_in_batch_norm",
        ]
    ).sort(["batch_id", "timestamp"])

    # Check for incomplete batches
    rows_per_batch = df_final.group_by("batch_id").len()
    complete_batches = rows_per_batch.filter(pl.col("len") == bars_per_8h)
    incomplete_batches = rows_per_batch.filter(pl.col("len") != bars_per_8h)

    # Save
    df_final.write_parquet(output_path)

    return {
        "path": output_path,
        "total_rows": len(df_final),
        "rows_before_dedup": rows_before_dedup,
        "rows_after_dedup": rows_after_dedup,
        "duplicate_rows_removed": duplicate_rows_removed,
        "n_batches": df_final["batch_id"].n_unique(),
        "complete_batches": len(complete_batches),
        "incomplete_batches": len(incomplete_batches),
        "rows_per_batch": bars_per_8h,
        "date_range": (df_final["timestamp"].min(), df_final["timestamp"].max()),
    }


# =============================================================================
# MAIN: Check and update all timeframes
# =============================================================================
print("=" * 70)
print("HTF COMBINED FILE CHECK & UPDATE")
print("=" * 70)
print(f"Timeframes: {HTF_TIMEFRAMES}")
print(f"Date range: {DATE_START} to {DATE_END}")
print()

results = {}

for tf in HTF_TIMEFRAMES:
    print(f"\n{'─' * 70}")
    print(f"TIMEFRAME: {tf}")
    print(f"{'─' * 70}")

    # Check if timeframe is supported
    if tf not in TF_CONFIG:
        print("  ✗ Unknown timeframe (not in TF_CONFIG)")
        results[tf] = {"status": "error", "reason": "unknown_tf"}
        continue

    # Get raw data info
    raw_info = get_raw_data_info(tf)
    if not raw_info["exists"]:
        combined_info = get_combined_info(tf)
        if combined_info["exists"]:
            print(f"  ⚠ Raw data not found: {raw_info.get('error', 'unknown')}")
            print("  ✓ Using existing combined file")
            results[tf] = {"status": "current_no_raw", **combined_info}
        else:
            print(f"  ✗ Raw data not found: {raw_info.get('error', 'unknown')}")
            results[tf] = {"status": "error", "reason": "no_raw_data"}
        continue

    print(f"  Raw data: {raw_info['total_rows']:,} rows in {raw_info['n_files']} files")
    print(f"  Raw range: {raw_info['min_ts']} to {raw_info['max_ts']}")

    # Get combined file info
    combined_info = get_combined_info(tf)

    # Decide if we need to create/update
    needs_update = False
    update_reason = ""

    if FORCE_RECREATE_ALL:
        needs_update = True
        update_reason = "forced"
    elif not combined_info["exists"]:
        needs_update = True
        update_reason = "missing"
    else:
        print(
            f"  Combined: {combined_info['total_rows']:,} rows, {combined_info['max_batch']} batches"
        )
        print(
            f"  Combined range: {combined_info['min_ts']} to {combined_info['max_ts']}"
        )

        # Check if raw data is newer (has later timestamp)
        raw_max = raw_info["max_ts"]
        combined_max = combined_info["max_ts"]

        # Normalize both to compare (remove timezone if needed)
        if hasattr(raw_max, "replace"):
            raw_max_cmp = (
                raw_max.replace(tzinfo=None) if hasattr(raw_max, "tzinfo") else raw_max
            )
        else:
            raw_max_cmp = raw_max
        if hasattr(combined_max, "replace"):
            combined_max_cmp = (
                combined_max.replace(tzinfo=None)
                if hasattr(combined_max, "tzinfo")
                else combined_max
            )
        else:
            combined_max_cmp = combined_max

        # Compare timestamps
        if raw_max_cmp > combined_max_cmp:
            # Refresh if raw data moved ahead by configured lead.
            # With 0.0 this captures partial live batches as well.
            time_diff = raw_max_cmp - combined_max_cmp
            if hasattr(time_diff, "total_seconds"):
                hours_diff = time_diff.total_seconds() / 3600
            else:
                hours_diff = time_diff / timedelta(hours=1)

            if hours_diff >= MIN_RAW_LEAD_HOURS_FOR_UPDATE:
                needs_update = True
                update_reason = f"new_data (+{hours_diff:.1f}h)"
            else:
                print(
                    f"  ℹ Raw has {hours_diff:.1f}h more data "
                    f"(< {MIN_RAW_LEAD_HOURS_FOR_UPDATE}h threshold, skipping)"
                )

    if needs_update:
        print(f"  → Creating/updating ({update_reason})...")
        result = create_combined_file(tf, raw_info)
        print(f"  ✓ Saved: {result['path'].name}")
        print(
            f"    Rows: {result['total_rows']:,} "
            f"(dedup removed {result['duplicate_rows_removed']:,})"
        )
        print(
            f"    Batches: {result['n_batches']} ({result['complete_batches']} complete, {result['incomplete_batches']} incomplete)"
        )
        print(f"    Rows/batch: {result['rows_per_batch']}")
        results[tf] = {"status": "created", **result}
    else:
        print("  ✓ Up to date")
        results[tf] = {"status": "current", **combined_info}

# =============================================================================
# SUMMARY
# =============================================================================
print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)
print(f"{'TF':<6} {'Status':<12} {'Rows':>12} {'Batches':>10} {'Rows/Batch':>12}")
print("-" * 70)

for tf in HTF_TIMEFRAMES:
    r = results.get(tf, {})
    status = r.get("status", "?")
    rows = r.get("total_rows", 0)
    batches = r.get("n_batches", r.get("max_batch", 0))
    expected_rpb = TF_CONFIG.get(tf, {}).get("bars_per_8h", "?")
    actual_rpb = f"{rows / batches:.0f}" if batches else "?"

    status_icon = {
        "created": "🆕",
        "current": "✓",
        "current_no_raw": "✓",
        "error": "✗",
    }.get(status, "?")
    print(
        f"{tf:<6} {status_icon} {status:<10} {rows:>12,} {batches:>10} {actual_rpb:>8}/{expected_rpb}"
    )

print("\n✓ All HTF combined files checked.")

print("\n" + "=" * 70)
print("SHIFT4H FAMILY C COMBINED FILE CHECK & UPDATE")
print("=" * 70)
shift4h_results = {}
for tf in SHIFT4H_TIMEFRAMES:
    ensure_res = ensure_base_combined_family_metadata(tf)
    if ensure_res.get("updated"):
        print(f"  ✓ Refreshed base family metadata for {tf}")
    print(f"\n{'─' * 70}")
    print(f"SHIFT4H FAMILY C: {tf}")
    print(f"{'─' * 70}")
    result = build_shift4h_combined_from_base(tf)
    if not result.get("exists"):
        print(f"  ✗ {result.get('reason', 'unknown')}")
        shift4h_results[tf] = {"status": "error", **result}
        continue
    action = "Current" if result.get("skipped") else "Saved"
    print(f"  ✓ {action}: {result['path'].name}")
    if result.get("rebuild_reasons"):
        print(f"    Rebuild reasons: {', '.join(result['rebuild_reasons'])}")
    print(f"    Rows: {result['total_rows']:,}")
    print(f"    Batches: {result['n_batches']}")
    print(f"    Range: {result['min_ts']} to {result['max_ts']}")
    shift4h_results[tf] = {
        "status": "current" if result.get("skipped") else "created",
        **result,
    }

print("\n" + "=" * 70)
print("SHIFT4H SUMMARY")
print("=" * 70)
for tf in SHIFT4H_TIMEFRAMES:
    r = shift4h_results.get(tf, {})
    print(
        f"{tf:<6} {r.get('status', '?'):<10} "
        f"rows={int(r.get('total_rows', 0)):,} "
        f"batches={int(r.get('n_batches', 0))}"
    )

# %%
# =============================================================================
# CELL 3: VALIDATE BATCH ALIGNMENT (Load → Validate → Save Results → Free Memory)
# =============================================================================
# Validates that batched LTF data aligns with 8h candles (OPEN & CLOSE match)
# Results saved to parquet so we don't need to keep data in memory
# =============================================================================

SKIP_VALIDATION = False  # Set False to re-run validation

validation_results_path = HTF_BACKTEST_DIR / "validation_results.parquet"

if SKIP_VALIDATION and validation_results_path.exists():
    print("=" * 70)
    print("VALIDATION: Loading cached results")
    print("=" * 70)
    validation_summary = pl.read_parquet(validation_results_path)
    print(validation_summary)
    print("\n✓ Validation already completed. Set SKIP_VALIDATION=False to re-run.")

else:
    print("=" * 70)
    print("VALIDATION: 8h OHLCV vs Batched Data (OPEN & CLOSE Alignment)")
    print("=" * 70)

    reference_8h_path = RAW_DATA_DIR / "sorted-8h-bybit-linear/btcusdt_8h.parquet"
    if not reference_8h_path.exists():
        print(f"⚠️ 8h reference data missing: {reference_8h_path}")
        if validation_results_path.exists():
            validation_summary = pl.read_parquet(validation_results_path)
            print("✓ Loaded cached validation results.")
            print(validation_summary)
        else:
            validation_summary = pl.DataFrame(
                [
                    {
                        "tf": tf,
                        "total_batches": 0,
                        "matched": 0,
                        "open_aligned": 0,
                        "close_aligned": 0,
                        "open_pct": None,
                        "close_pct": None,
                        "status": "skipped_missing_8h_reference",
                    }
                    for tf in HTF_TIMEFRAMES
                ]
            )
            validation_summary.write_parquet(validation_results_path)
            print("✓ Saved skipped validation marker.")
        print("✓ Validation step skipped due to missing 8h reference.")
    else:
        # Load 8h reference data (small - only ~5.5K rows)
        df_8h = pl.read_parquet(reference_8h_path)
        df_8h = (
            df_8h.with_columns(
                pl.col("timestamp")
                .dt.replace_time_zone(None)
                .cast(pl.Datetime("us"))
                .alias("timestamp_norm")
            )
            .filter(
                (pl.col("timestamp_norm") >= datetime(2021, 1, 1))
                & (pl.col("timestamp_norm") < DATE_END)
            )
            .sort("timestamp_norm")
        )

        print(f"8h reference data: {len(df_8h):,} rows")

        # Validation function
        def validate_batch_alignment(
            df_ltf: pl.DataFrame, df_8h: pl.DataFrame, tf_name: str
        ) -> dict:
            """Validate that LTF batches align with 8h candles."""
            df_ltf_norm = df_ltf.with_columns(
                pl.col("period_8h_start")
                .dt.replace_time_zone(None)
                .cast(pl.Datetime("us"))
                .alias("period_norm"),
                pl.col("timestamp")
                .dt.replace_time_zone(None)
                .cast(pl.Datetime("us"))
                .alias("ts_norm"),
            )

            batches = (
                df_ltf_norm.sort("ts_norm")
                .group_by("batch_id", "period_norm")
                .agg(
                    [
                        pl.col("ts_norm").first().alias("first_ts"),
                        pl.col("open").first().alias("batch_open"),
                        pl.col("close").last().alias("batch_close"),
                    ]
                )
                .sort("batch_id")
            )

            df_8h_ref = df_8h.select(
                [
                    pl.col("timestamp_norm").alias("period_norm"),
                    pl.col("open").alias("ref_open"),
                    pl.col("close").alias("ref_close"),
                ]
            )

            validation = batches.join(df_8h_ref, on="period_norm", how="left")
            matched = validation.filter(pl.col("ref_close").is_not_null())

            tolerance = 0.001
            open_ok = matched.filter(
                (pl.col("batch_open") - pl.col("ref_open")).abs() <= tolerance
            )
            close_ok = matched.filter(
                (pl.col("batch_close") - pl.col("ref_close")).abs() <= tolerance
            )

            return {
                "tf": tf_name,
                "total_batches": len(batches),
                "matched": len(matched),
                "open_aligned": len(open_ok),
                "close_aligned": len(close_ok),
                "open_pct": 100 * len(open_ok) / len(matched) if len(matched) > 0 else 0,
                "close_pct": 100 * len(close_ok) / len(matched) if len(matched) > 0 else 0,
            }

        # Run validation for each timeframe (load one at a time to save memory)
        results = []
        for tf in HTF_TIMEFRAMES:
            print(f"\nValidating {tf}...")
            df_ltf = pl.read_parquet(HTF_BACKTEST_DIR / f"{tf}_HTF_combined.parquet")
            r = validate_batch_alignment(df_ltf, df_8h, tf)
            results.append(r)

            status = "✅" if r["open_pct"] == 100 and r["close_pct"] == 100 else "⚠️"
            print(f"  {status} OPEN={r['open_pct']:.1f}%, CLOSE={r['close_pct']:.1f}%")

            # Free memory immediately
            del df_ltf
            gc.collect()

        # Save results
        validation_summary = pl.DataFrame(results)
        validation_summary.write_parquet(validation_results_path)

        # Free 8h data
        del df_8h
        gc.collect()

        print("\n" + "=" * 70)
        print("VALIDATION SUMMARY (saved to validation_results.parquet)")
        print("=" * 70)
        print(validation_summary)
        print("\n✓ Validation complete. Memory freed.")

# %%
# =============================================================================
# CELL 5: HTF FEATURE ENGINEERING (Compute on Full Data, Then Split to Batches)
# =============================================================================
# Features with long windows (xlong=8h) need continuous data to avoid NaN
# Strategy: Compute features on FULL combined data, THEN split into batch files
# Output: data/htf_features/{tf}/batch_{batch_id:04d}.parquet
# =============================================================================

import gc
import importlib
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl
from numba import njit

# Add project root to path for imports
project_root = Path.cwd().parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Force reload of the module (in case it was changed)
import scripts.feature_engineering.compute_htf_features as htf_module

importlib.reload(htf_module)
from scripts.feature_engineering.compute_htf_features import HTFFeatureEngine

# =============================================================================
# CONFIGURATION
# =============================================================================
RECOMPUTE_FEATURES = False  # True => full rebuild
# Fast incremental mode (production default):
# - Detect new/missing combined batches
# - Recompute only affected tail + small context warmup for rolling windows
INCREMENTAL_FEATURE_UPDATE = True
FEATURE_INCREMENTAL_OVERLAP_BATCHES_BY_TF = {"1m": 2, "5m": 2, "15m": 2}
FEATURE_CONTEXT_BATCHES_BY_TF = {"1m": 2, "5m": 2, "15m": 2}

# Ensure bars-per-batch mapping exists (Cell 7 defines it; keep safe default here)
if "BARS_PER_8H" not in globals():
    BARS_PER_8H = {"1m": 480, "5m": 96, "15m": 32}

# Rolling distance feature windows (fixed from IC optimization)
# These are past-window (causal) distances based on OHLCV only.
DISTANCE_WINDOWS_BY_TF = {
    # Keep time-equivalent horizons across TFs:
    # 1m: 240/120 bars == 5m: 48/24 bars == 15m: 16/8 bars
    "1m": {
        "dist_avg_high": 240,
        "dist_avg_low": 240,
        "dist_top5_high": 240,
        "dist_bot5_low": 120,
    },
    "5m": {
        "dist_avg_high": 48,
        "dist_avg_low": 48,
        "dist_top5_high": 48,
        "dist_bot5_low": 24,
    },
    "15m": {
        "dist_avg_high": 16,
        "dist_avg_low": 16,
        "dist_top5_high": 16,
        "dist_bot5_low": 8,
    },
}
DISTANCE_OUTLIER_PCT = 0.05


@njit
def _compute_past_distance_metrics(close, high, low, bar_pos, window, outlier_pct):
    n = len(close)
    dist_avg_high = np.full(n, np.nan, dtype=np.float64)
    dist_avg_low = np.full(n, np.nan, dtype=np.float64)
    dist_top5_high = np.full(n, np.nan, dtype=np.float64)
    dist_bot5_low = np.full(n, np.nan, dtype=np.float64)

    top_n = max(1, int(window * outlier_pct))

    for i in range(n):
        if bar_pos[i] < window:
            continue

        entry = close[i]
        if entry == 0:
            continue

        start = i - window
        highs = high[start:i]
        lows = low[start:i]

        avg_high = np.mean(highs)
        avg_low = np.mean(lows)

        sorted_highs = np.sort(highs)
        sorted_lows = np.sort(lows)
        avg_top_high = np.mean(sorted_highs[-top_n:])
        avg_bot_low = np.mean(sorted_lows[:top_n])

        dist_avg_high[i] = 100.0 * (avg_high - entry) / entry
        dist_avg_low[i] = 100.0 * (entry - avg_low) / entry
        dist_top5_high[i] = 100.0 * (avg_top_high - entry) / entry
        dist_bot5_low[i] = 100.0 * (entry - avg_bot_low) / entry

    return dist_avg_high, dist_avg_low, dist_top5_high, dist_bot5_low


# Verify paths from Cell 2 exist
assert HTF_BACKTEST_DIR.exists(), f"HTF_BACKTEST_DIR not found: {HTF_BACKTEST_DIR}"

# =============================================================================
# STEP 1: INITIALIZE ENGINE
# =============================================================================
print("=" * 70)
print("HTF FEATURE ENGINEERING PIPELINE")
print("=" * 70)
print(f"Source: {HTF_BACKTEST_DIR}")
print(f"Output: {HTF_FEATURES_DIR}/{{tf}}/batch_XXXX.parquet")
print()
print("Strategy: Compute on FULL data (for long windows), then split to batches")
print()

# Engine for feature computation
engine = HTFFeatureEngine(data_dir=RAW_DATA_DIR, verbose=False)
engine.discover_available_sources()

# =============================================================================
# STEP 2: COMPUTE FEATURES ON FULL DATA, THEN SPLIT TO BATCHES
# =============================================================================
for tf in HTF_TIMEFRAMES:
    print(f"\n{'=' * 70}")
    print(f"PROCESSING {tf.upper()} TIMEFRAME")
    print(f"{'=' * 70}")

    # Create output directory for this timeframe
    tf_output_dir = HTF_FEATURES_DIR / tf
    tf_output_dir.mkdir(parents=True, exist_ok=True)

    # Load FULL combined data (has batch_id, period_8h_start)
    src_path = HTF_BACKTEST_DIR / f"{tf}_HTF_combined.parquet"
    if not src_path.exists():
        print(f"  ✗ Source file not found: {src_path}")
        continue

    print(f"  Loading full data: {src_path.name}")
    df_full = pl.read_parquet(src_path)
    combined_batch_ids = sorted(df_full["batch_id"].unique().drop_nulls().to_list())
    if not combined_batch_ids:
        print("  ⚠ No combined batches found, skipping timeframe")
        continue
    combined_batch_set = set(combined_batch_ids)
    combined_max_batch = combined_batch_ids[-1]
    print(
        f"  → {len(df_full):,} rows, {len(combined_batch_ids)} batches "
        f"(max_batch={combined_max_batch})"
    )

    # Existing feature outputs
    existing_batches = sorted(tf_output_dir.glob("batch_*.parquet"))
    existing_batch_ids = sorted(
        [
            int(p.stem.split("_")[1])
            for p in existing_batches
            if p.stem.startswith("batch_")
        ]
    )
    existing_batch_set = set(existing_batch_ids)

    # Decide scope: full rebuild vs incremental tail update
    if RECOMPUTE_FEATURES or not existing_batch_ids:
        run_mode = "full_recompute" if RECOMPUTE_FEATURES else "full_first_build"
        write_start_batch = combined_batch_ids[0]
        write_batch_ids = combined_batch_ids
        context_start_batch = combined_batch_ids[0]
    else:
        if not INCREMENTAL_FEATURE_UPDATE:
            print(
                f"  ✓ Feature batches already exist ({len(existing_batch_ids)}). "
                "Set INCREMENTAL_FEATURE_UPDATE=True or RECOMPUTE_FEATURES=True to refresh."
            )
            continue

        stale_batch_ids = [b for b in existing_batch_ids if b not in combined_batch_set]
        if stale_batch_ids:
            print(
                f"  Removing {len(stale_batch_ids)} stale feature batches "
                f"(not present in combined anymore)"
            )
            for bid in stale_batch_ids:
                stale_path = tf_output_dir / f"batch_{bid:04d}.parquet"
                if stale_path.exists():
                    stale_path.unlink()
            existing_batch_ids = [
                b for b in existing_batch_ids if b in combined_batch_set
            ]
            existing_batch_set = set(existing_batch_ids)

        missing_batch_ids = [
            b for b in combined_batch_ids if b not in existing_batch_set
        ]
        if not missing_batch_ids and existing_batch_ids[-1] >= combined_max_batch:
            print(
                f"  ✓ Features up to date ({len(existing_batch_ids)} batches, "
                f"max_batch={existing_batch_ids[-1]})."
            )
            meta_path = tf_output_dir / "_build_meta.json"
            if meta_path.exists():
                print(f"  ✓ Existing metadata: {meta_path.name}")
            continue

        run_mode = "incremental_tail"
        overlap_batches = FEATURE_INCREMENTAL_OVERLAP_BATCHES_BY_TF.get(tf, 2)
        context_batches = FEATURE_CONTEXT_BATCHES_BY_TF.get(tf, 2)
        first_missing_batch = (
            min(missing_batch_ids)
            if missing_batch_ids
            else (existing_batch_ids[-1] + 1)
        )
        write_start_batch = max(
            combined_batch_ids[0], first_missing_batch - overlap_batches
        )
        context_start_batch = max(
            combined_batch_ids[0], write_start_batch - context_batches
        )
        write_batch_ids = [b for b in combined_batch_ids if b >= write_start_batch]
        print(
            f"  Incremental feature update: "
            f"context_start={context_start_batch}, write_start={write_start_batch}, "
            f"write_batches={len(write_batch_ids)}"
        )

    # Restrict to context window needed for rolling continuity
    df_full = df_full.filter(pl.col("batch_id") >= context_start_batch)
    print(
        f"  Compute scope rows: {len(df_full):,} "
        f"(batches {context_start_batch}..{combined_max_batch})"
    )

    # Sort by timestamp for correct rolling window computation
    df_full = df_full.sort("timestamp")

    # Compute bar position inside each batch (for causal past-window distances)
    df_full = df_full.with_columns(
        (pl.cum_count("timestamp").over("batch_id") - 1).alias("bar_pos")
    )
    # Normalized time-within-batch feature (0..1)
    bars_per_batch = BARS_PER_8H[tf]
    df_full = df_full.with_columns(
        ((pl.col("bar_pos") + 1) / bars_per_batch).alias("bar_in_batch_norm")
    )

    # Extract metadata to rejoin later
    meta_keep_cols = [
        "timestamp",
        "batch_id",
        "period_8h_start",
        "bar_in_batch_norm",
        "batch_family",
        "family_batch_id",
        "family_period_start",
        "family_period_end",
        "family_bar_pos",
        "source_base_batch_id",
        "source_base_period_start",
        "source_half_in_base",
        "is_label_half",
    ]
    meta_df = df_full.select([c for c in meta_keep_cols if c in df_full.columns])

    # Cache bar_pos for distance feature computation
    bar_pos = df_full["bar_pos"].to_numpy().astype(np.int32)

    # Convert to pandas for feature computation (OHLCV only)
    ohlcv_cols = ["timestamp", "open", "high", "low", "close", "volume"]
    df_pd = df_full.select(ohlcv_cols).to_pandas()

    # Free polars data
    del df_full
    gc.collect()

    # Compute features on FULL continuous data
    print(f"  Computing features on full {len(df_pd):,} rows...")
    print("    (This ensures xlong windows have enough history)")
    df_features = engine.compute_features(df=df_pd, target_tf=tf)

    # Compute past-window distance features (causal)
    distance_windows = DISTANCE_WINDOWS_BY_TF.get(tf, {})
    if distance_windows:
        unique_windows = sorted(set(distance_windows.values()))
        close = df_pd["close"].to_numpy()
        high = df_pd["high"].to_numpy()
        low = df_pd["low"].to_numpy()

        dist_feature_map = {}
        for window in unique_windows:
            d_avg_high, d_avg_low, d_top5_high, d_bot5_low = (
                _compute_past_distance_metrics(
                    close, high, low, bar_pos, window, DISTANCE_OUTLIER_PCT
                )
            )

            if distance_windows.get("dist_avg_high") == window:
                dist_feature_map[f"D_dist_avg_high_w{window}"] = d_avg_high
            if distance_windows.get("dist_avg_low") == window:
                dist_feature_map[f"D_dist_avg_low_w{window}"] = d_avg_low
            if distance_windows.get("dist_top5_high") == window:
                dist_feature_map[f"D_dist_top5_high_w{window}"] = d_top5_high
            if distance_windows.get("dist_bot5_low") == window:
                dist_feature_map[f"D_dist_bot5_low_w{window}"] = d_bot5_low

        if dist_feature_map:
            df_features = pd.concat(
                [df_features, pd.DataFrame(dist_feature_map)], axis=1
            )

    # Merge OHLCV back (compute_features returns features + timestamp)
    df_features = pd.concat(
        [df_features, df_pd[["open", "high", "low", "close", "volume"]]], axis=1
    )
    print(f"  → Features computed: {len(df_features.columns)} columns")

    # Convert to polars and join batch metadata
    df_pl = pl.from_pandas(df_features)
    del df_features, df_pd
    gc.collect()

    # Join batch_id and period_8h_start back by timestamp
    df_pl = df_pl.join(meta_df, on="timestamp", how="left")
    del meta_df
    gc.collect()

    # Verify batch_id joined correctly
    null_batch_count = df_pl["batch_id"].null_count()
    if null_batch_count > 0:
        print(f"  ⚠ Warning: {null_batch_count} rows have null batch_id after join")

    # ==========================================================================
    # SPLIT INTO BATCH FILES
    # ==========================================================================
    print("  Splitting into batch files...")
    batch_ids = sorted(df_pl["batch_id"].unique().drop_nulls().to_list())
    write_batch_set = set(write_batch_ids)
    batch_ids_to_write = [b for b in batch_ids if b in write_batch_set]

    if not batch_ids_to_write:
        print(
            "  ⚠ No batches selected for writing after compute scope filter, skipping"
        )
        del df_pl
        gc.collect()
        continue

    batch_stats = (
        df_pl.group_by("batch_id")
        .agg(
            [
                pl.len().alias("rows"),
                pl.col("timestamp").min().alias("first_ts"),
                pl.col("timestamp").max().alias("last_ts"),
            ]
        )
        .sort("batch_id")
    )

    write_stats = batch_stats.filter(pl.col("batch_id").is_in(batch_ids_to_write))

    for i, batch_id in enumerate(batch_ids_to_write):
        out_path = tf_output_dir / f"batch_{batch_id:04d}.parquet"

        # Extract this batch
        df_batch = df_pl.filter(pl.col("batch_id") == batch_id)

        # Save
        df_batch.write_parquet(out_path)

        # Progress every 500 batches
        if (i + 1) % 200 == 0:
            print(f"    Saved {i + 1}/{len(batch_ids_to_write)} batches...")

    print(
        f"  ✓ Saved {len(batch_ids_to_write)} batch files to {tf_output_dir.name}/ "
        f"(write_start={write_start_batch})"
    )

    # Persist build metadata for robust incremental/live updates
    expected_rows = int(bars_per_batch)
    incomplete_stats = write_stats.filter(pl.col("rows") < expected_rows)
    last_batch_id = int(write_stats["batch_id"].max())
    last_batch_row = write_stats.filter(pl.col("batch_id") == last_batch_id).row(
        0, named=True
    )
    source_plan = engine.get_source_resolution_plan(tf)
    feature_meta = {
        "timeframe": tf,
        "created_at_utc": f"{datetime.utcnow().isoformat()}Z",
        "source_file": str(src_path),
        "source_plan": source_plan,
        "run_mode": run_mode,
        "recompute_features": bool(RECOMPUTE_FEATURES),
        "incremental_feature_update": bool(INCREMENTAL_FEATURE_UPDATE),
        "context_start_batch": int(context_start_batch),
        "write_start_batch": int(write_start_batch),
        "write_batches_count": int(len(batch_ids_to_write)),
        "distance_windows": DISTANCE_WINDOWS_BY_TF.get(tf, {}),
        "distance_outlier_pct": float(DISTANCE_OUTLIER_PCT),
        "rows_total_compute_scope": int(len(df_pl)),
        "batches_total_compute_scope": int(len(batch_ids)),
        "batches_total_combined": int(len(combined_batch_ids)),
        "expected_rows_per_batch": expected_rows,
        "incomplete_batches_count": int(len(incomplete_stats)),
        "incomplete_batch_ids": [
            int(v) for v in incomplete_stats["batch_id"].to_list()
        ],
        "first_batch_id": int(write_stats["batch_id"].min()),
        "last_batch_id": last_batch_id,
        "first_timestamp": str(write_stats["first_ts"].min()),
        "last_timestamp": str(write_stats["last_ts"].max()),
        "last_batch_rows": int(last_batch_row["rows"]),
        "last_batch_first_timestamp": str(last_batch_row["first_ts"]),
        "last_batch_last_timestamp": str(last_batch_row["last_ts"]),
        "columns_total": int(len(df_pl.columns)),
        "output_dir": str(tf_output_dir),
        "output_pattern": "batch_XXXX.parquet",
    }
    meta_path = tf_output_dir / "_build_meta.json"
    with open(meta_path, "w") as f:
        json.dump(feature_meta, f, indent=2)
    print(f"  ✓ Saved metadata: {meta_path.name}")

    # Clean up
    del df_pl
    gc.collect()

# =============================================================================
# STEP 3: SUMMARY
# =============================================================================
print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)

for tf in HTF_TIMEFRAMES:
    tf_dir = HTF_FEATURES_DIR / tf
    if tf_dir.exists():
        batch_files = list(tf_dir.glob("batch_*.parquet"))
        n_batches = len(batch_files)

        # Sample one batch to get feature count
        if batch_files:
            sample = pl.read_parquet(batch_files[0])
            meta_cols = [
                "timestamp",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "batch_id",
                "period_8h_start",
            ]
            n_features = len([c for c in sample.columns if c not in meta_cols])
            rows_per_batch = len(sample)
            print(f"\n{tf.upper()}:")
            print(f"  Batches:          {n_batches}")
            print(f"  Rows per batch:   {rows_per_batch}")
            print(f"  Features:         {n_features}")
            print(f"  Location:         {tf_dir}/batch_XXXX.parquet")
    else:
        print(f"\n{tf.upper()}: No batches computed")

print("\n" + "=" * 70)
print("FEATURES READY")
print("=" * 70)
print("✓ Features computed on FULL continuous data (no xlong NaN issue)")
print("✓ Then split into individual batch files")
print("✓ Structure: HTF_FEATURES_DIR/{tf}/batch_{batch_id:04d}.parquet")

# %%
# =============================================================================
# CELL 5B: APPLY FAMILY METADATA TO BASE FEATURES + BUILD SHIFT4H FEATURES
# =============================================================================


def _feature_value_cols(df: pl.DataFrame) -> list[str]:
    meta = set(family_metadata_cols(include_timestamp=True))
    return [c for c in df.columns if c not in meta]


def _augment_base_feature_batches(tf: str) -> dict:
    feature_dir = HTF_FEATURES_DIR / tf
    combined_path = HTF_BACKTEST_DIR / f"{tf}_HTF_combined.parquet"
    if not feature_dir.exists() or not combined_path.exists():
        return {"written": 0, "skipped": 0}

    meta_all = pl.read_parquet(combined_path, columns=family_metadata_cols())
    written = 0
    skipped = 0
    for batch_path in sorted(feature_dir.glob("batch_*.parquet")):
        df = pl.read_parquet(batch_path)
        if set(family_metadata_cols(include_timestamp=False)).issubset(df.columns):
            skipped += 1
            continue
        bid = int(batch_path.stem.split("_")[1])
        meta_batch = meta_all.filter(pl.col("batch_id") == bid)
        value_cols = [c for c in df.columns if c not in set(family_metadata_cols(include_timestamp=True))]
        df_out = (
            df.select(["timestamp"] + value_cols)
            .join(meta_batch, on="timestamp", how="left")
            .sort(["batch_id", "timestamp"])
        )
        df_out.write_parquet(batch_path)
        written += 1
    return {"written": written, "skipped": skipped}


def _build_shift4h_feature_batches(tf: str) -> dict:
    source_dir = HTF_FEATURES_DIR / tf
    output_dir = HTF_FEATURES_SHIFT4H_DIR / tf
    combined_path = HTF_BACKTEST_SHIFT4H_DIR / f"{tf}_HTF_combined.parquet"
    combined_meta_path = _shift4h_combined_meta_path(tf)
    meta_path = output_dir / "_build_meta.json"
    output_dir.mkdir(parents=True, exist_ok=True)
    if not source_dir.exists() or not combined_path.exists():
        return {"written": 0, "skipped": 0}

    sample_feature_files = sorted(source_dir.glob("batch_*.parquet"))
    if not sample_feature_files:
        return {"written": 0, "skipped": 0}

    sample_cols = pl.scan_parquet(str(sample_feature_files[0])).collect_schema().names()
    value_cols_expected = [
        c for c in sample_cols if c not in set(family_metadata_cols(include_timestamp=True))
    ]
    schema_columns = ["timestamp", *value_cols_expected, *family_metadata_cols(include_timestamp=False)]
    source_fingerprint = {
        "base_features": fingerprint_batch_dir(source_dir),
        "shift4h_combined": fingerprint_paths([combined_path, combined_meta_path]),
    }
    rebuild_reasons, rebuild_mode = prepare_stage_rebuild(
        stage_name=f"Shift4h {tf} features",
        meta_path=meta_path,
        artifact_version=ARTIFACT_STAGE_VERSIONS["shift4h_features"],
        family="C",
        timeframe=tf,
        source_fingerprint=source_fingerprint,
        schema_columns=schema_columns,
        output_targets=[output_dir],
        inspect_batch_dir=output_dir,
        required_batch_columns=set(["timestamp", *family_metadata_cols(include_timestamp=False)]),
    )

    meta_all = pl.read_parquet(combined_path, columns=family_metadata_cols())
    written = 0
    skipped = 0
    for bid in sorted(meta_all["batch_id"].unique().to_list()):
        meta_batch = meta_all.filter(pl.col("batch_id") == bid).sort("timestamp")
        out_path = output_dir / f"batch_{int(bid):04d}.parquet"
        if out_path.exists():
            existing = pl.read_parquet(out_path)
            required_raw_cols = {"open", "high", "low", "close", "volume"}
            has_required_raw_cols = required_raw_cols.issubset(existing.columns)
            same_rows = len(existing) == len(meta_batch)
            same_ts = same_rows and existing["timestamp"].to_list() == meta_batch["timestamp"].to_list()
            if has_required_raw_cols and same_ts:
                skipped += 1
                continue

        src_batches = sorted(meta_batch["source_base_batch_id"].unique().to_list())
        src_parts = []
        for src_bid in src_batches:
            src_path = source_dir / f"batch_{int(src_bid):04d}.parquet"
            if src_path.exists():
                src_parts.append(pl.read_parquet(src_path))
        if not src_parts:
            continue

        src_df = pl.concat(src_parts, how="diagonal_relaxed")
        value_cols = _feature_value_cols(src_df)
        df_out = (
            src_df.select(["timestamp"] + value_cols)
            .join(meta_batch, on="timestamp", how="inner")
            .sort(["batch_id", "timestamp"])
        )
        df_out.write_parquet(out_path)
        written += 1

    with open(meta_path, "w") as f:
        json.dump(
            artifact_meta_payload(
                artifact_version=ARTIFACT_STAGE_VERSIONS["shift4h_features"],
                family="C",
                timeframe=tf,
                source_fingerprint=source_fingerprint,
                schema_columns=schema_columns,
                rebuild_mode=rebuild_mode,
                extra={
                    "rebuild_reasons": rebuild_reasons,
                    "output_dir": project_relative_path(output_dir),
                    "written": int(written),
                    "skipped": int(skipped),
                    "batch_count": int(len(list(output_dir.glob("batch_*.parquet")))),
                },
            ),
            f,
            indent=2,
        )

    return {
        "written": written,
        "skipped": skipped,
        "rebuild_mode": rebuild_mode,
        "rebuild_reasons": rebuild_reasons,
    }


print("\n" + "=" * 70)
print("FAMILY FEATURE MATERIALIZATION")
print("=" * 70)
for tf in HTF_TIMEFRAMES:
    base_res = _augment_base_feature_batches(tf)
    shift_res = _build_shift4h_feature_batches(tf)
    print(
        f"{tf}: base_written={base_res['written']} base_skipped={base_res['skipped']} "
        f"shift_written={shift_res['written']} shift_skipped={shift_res['skipped']} "
        f"shift_mode={shift_res.get('rebuild_mode', 'na')}"
    )

# %%
# =============================================================================
# CELL 6: VALIDATE BATCH FEATURE FILES
# =============================================================================
# Validates the batch-by-batch feature files created in Cell 5:
# 1. All batches exist and are readable
# 2. Each batch has correct structure (batch_id, period_8h_start, features)
# 3. No gaps in batch sequence
# 4. Feature values are reasonable (no extreme outliers, NaN patterns ok)
# 5. Timestamps align within each batch
# =============================================================================

from pathlib import Path

import polars as pl

print("=" * 70)
print("VALIDATING BATCH FEATURE FILES")
print("=" * 70)

# Ensure remaining-bars config exists (Cell 7 defines it; keep a safe default here)
if "MIN_REMAINING_BARS_BY_TF" not in globals():
    # Use only current batch; last 3 (5m) or last 1 (15m) bars are unlabeled.
    MIN_REMAINING_BARS_BY_TF = {"5m": 3, "15m": 1}

validation_results = {}

for tf in HTF_TIMEFRAMES:
    print(f"\n{'─' * 70}")
    print(f"{tf.upper()} TIMEFRAME VALIDATION")
    print(f"{'─' * 70}")

    tf_dir = HTF_FEATURES_DIR / tf
    issues = []

    # Check directory exists
    if not tf_dir.exists():
        print(f"  ✗ Directory not found: {tf_dir}")
        validation_results[tf] = {"valid": False, "issues": ["Directory not found"]}
        continue

    # Get all batch files
    batch_files = sorted(tf_dir.glob("batch_*.parquet"))
    n_files = len(batch_files)
    print(f"  Found {n_files} batch files")

    if n_files == 0:
        print("  ✗ No batch files found")
        validation_results[tf] = {"valid": False, "issues": ["No batch files"]}
        continue

    # ==========================================================================
    # CHECK 1: Batch ID sequence (no gaps)
    # ==========================================================================
    batch_ids_from_files = []
    for f in batch_files:
        try:
            batch_num = int(f.stem.split("_")[1])
            batch_ids_from_files.append(batch_num)
        except:
            issues.append(f"Invalid filename: {f.name}")

    batch_ids_from_files = sorted(batch_ids_from_files)
    expected_ids = list(range(min(batch_ids_from_files), max(batch_ids_from_files) + 1))
    missing_ids = set(expected_ids) - set(batch_ids_from_files)

    if missing_ids:
        issues.append(
            f"Missing batch IDs: {sorted(missing_ids)[:10]}{'...' if len(missing_ids) > 10 else ''}"
        )
        print(f"  ⚠ Missing {len(missing_ids)} batch IDs")
    else:
        print(
            f"  ✓ Batch ID sequence complete: {min(batch_ids_from_files)} → {max(batch_ids_from_files)}"
        )

    # ==========================================================================
    # CHECK 2: Sample batches for structure validation
    # ==========================================================================
    # Check first, middle, and last batches
    sample_indices = [0, n_files // 2, n_files - 1]
    required_cols = [
        "timestamp",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "batch_id",
        "period_8h_start",
    ]

    rows_per_batch = []
    feature_counts = []

    for idx in sample_indices:
        f = batch_files[idx]
        try:
            df = pl.read_parquet(f)

            # Check required columns
            missing_cols = [c for c in required_cols if c not in df.columns]
            if missing_cols:
                issues.append(f"Batch {f.name}: Missing columns {missing_cols}")

            rows_per_batch.append(len(df))

            # Count features (exclude metadata columns)
            meta_cols = [
                "timestamp",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "batch_id",
                "period_8h_start",
            ]
            feature_cols = [c for c in df.columns if c not in meta_cols]
            feature_counts.append(len(feature_cols))

            # Check batch_id consistency within file
            unique_batch_ids = df["batch_id"].unique().to_list()
            if len(unique_batch_ids) != 1:
                issues.append(
                    f"Batch {f.name}: Multiple batch_ids in single file: {unique_batch_ids}"
                )

            # Check timestamps are monotonic
            ts_sorted = df["timestamp"].is_sorted()
            if not ts_sorted:
                issues.append(f"Batch {f.name}: Timestamps not sorted")

        except Exception as e:
            issues.append(f"Batch {f.name}: Read error - {e}")

    # Verify consistent structure across samples
    if len(set(feature_counts)) > 1:
        issues.append(f"Inconsistent feature counts across batches: {feature_counts}")
    else:
        print(f"  ✓ Consistent feature count: {feature_counts[0]} features per batch")

    # Expected rows per batch based on timeframe (features are full 8h windows)
    expected_rows = {"1m": 480, "5m": 96, "15m": 32}
    if tf in expected_rows:
        exp = expected_rows[tf]
        actual_rows = rows_per_batch[0]
        if actual_rows == exp:
            print(
                f"  ✓ Rows per batch: {actual_rows} (expected {exp} for 8h of {tf} data)"
            )
        else:
            print(f"  ⚠ Rows per batch: {actual_rows} (expected {exp})")

        # Labeling excludes last bars (forward-looking metrics).
        if tf in {"5m", "15m"}:
            min_remaining = MIN_REMAINING_BARS_BY_TF.get(tf, 1)
            expected_valid_labels = max(exp - min_remaining, 0)
            print(
                f"  ℹ Expected valid label rows per full batch: {expected_valid_labels} "
                f"(exclude last {min_remaining} bars, last batch may be smaller)"
            )

    # ==========================================================================
    # CHECK 3: Feature value sanity (sample check)
    # ==========================================================================
    # Load a middle batch for detailed checks
    mid_file = batch_files[n_files // 2]
    df_mid = pl.read_parquet(mid_file)

    meta_cols = [
        "timestamp",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "batch_id",
        "period_8h_start",
    ]
    feature_cols = [c for c in df_mid.columns if c not in meta_cols]

    # Check for features that are all NaN (bad) vs partially NaN (expected at start)
    all_nan_features = []
    high_nan_features = []

    for col in feature_cols:
        null_pct = df_mid[col].null_count() / len(df_mid) * 100
        if null_pct == 100:
            all_nan_features.append(col)
        elif null_pct > 80:
            high_nan_features.append((col, null_pct))

    if all_nan_features:
        issues.append(f"Features with 100% NaN in sample batch: {all_nan_features[:5]}")
        print(f"  ⚠ {len(all_nan_features)} features are all NaN in sample batch")

    if high_nan_features:
        print(
            f"  ⚠ {len(high_nan_features)} features have >80% NaN (may be expected at batch start)"
        )
    else:
        print("  ✓ Feature NaN patterns look reasonable")

    # Check for infinite values
    for col in feature_cols[:20]:  # Sample first 20 features
        if df_mid[col].dtype in [pl.Float32, pl.Float64]:
            inf_count = df_mid.filter(pl.col(col).is_infinite()).height
            if inf_count > 0:
                issues.append(f"Feature {col} has {inf_count} infinite values")

    # ==========================================================================
    # CHECK 4: Timestamp alignment with batch boundaries
    # ==========================================================================
    first_ts = df_mid["timestamp"][0]
    period_start = df_mid["period_8h_start"][0]

    # First timestamp should equal period_8h_start for the batch
    if str(first_ts)[:19] == str(period_start)[:19]:  # Compare without timezone
        print("  ✓ Timestamps align with 8h period start")
    else:
        issues.append(
            f"Timestamp misalignment: first_ts={first_ts}, period_start={period_start}"
        )
        print("  ⚠ Timestamp alignment issue")

    # ==========================================================================
    # SUMMARY FOR THIS TIMEFRAME
    # ==========================================================================
    is_valid = len(issues) == 0
    validation_results[tf] = {
        "valid": is_valid,
        "n_batches": n_files,
        "n_features": feature_counts[0] if feature_counts else 0,
        "rows_per_batch": rows_per_batch[0] if rows_per_batch else 0,
        "issues": issues,
    }

    if is_valid:
        print(f"\n  ✅ {tf.upper()} VALIDATION PASSED")
    else:
        print(f"\n  ❌ {tf.upper()} VALIDATION FAILED - {len(issues)} issues:")
        for issue in issues[:5]:
            print(f"      - {issue}")

# =============================================================================
# FINAL SUMMARY
# =============================================================================
print("\n" + "=" * 70)
print("VALIDATION SUMMARY")
print("=" * 70)

all_valid = all(r["valid"] for r in validation_results.values())

print(
    f"\n{'Timeframe':<10} {'Batches':>10} {'Features':>10} {'Rows/Batch':>12} {'Status':>10}"
)
print("-" * 55)
for tf, r in validation_results.items():
    status = "✅ PASS" if r["valid"] else "❌ FAIL"
    print(
        f"{tf:<10} {r.get('n_batches', 0):>10} {r.get('n_features', 0):>10} {r.get('rows_per_batch', 0):>12} {status:>10}"
    )

if all_valid:
    print("\n" + "=" * 70)
    print("✅ ALL VALIDATIONS PASSED - BATCH FEATURES READY FOR BACKTEST")
    print("=" * 70)
else:
    print("\n" + "=" * 70)
    print("❌ VALIDATION ISSUES DETECTED - REVIEW BEFORE PROCEEDING")
    print("=" * 70)

# %%
# =============================================================================
# CELL 7: COMPUTE DISTANCE METRICS FOR 4-CLASS TARGET LABELING
# =============================================================================
# Computes per-bar distance metrics for all timeframes:
#   - dist_avg_high: distance to average of remaining highs (%)
#   - dist_avg_low: distance to average of remaining lows (%)
#   - dist_top5_high: distance to top 5% high average (%)
#   - dist_bot5_low: distance to bottom 5% low average (%)
#
# Output Files:
#   - {tf}_distance_metrics.parquet (per-bar metrics)
#   - {tf}_batch_stats.parquet (per-batch aggregates for future 8h labeling)
#   - distance_metrics_summary.json (global stats)
# =============================================================================

import gc
import json
from datetime import datetime
from pathlib import Path

import numpy as np
import polars as pl
from numba import njit

# =============================================================================
# PATHS (redefine here so cell can run standalone)
# =============================================================================
PROJECT_ROOT = resolve_project_root() if "resolve_project_root" in globals() else Path("..").resolve()
DATA_DIR = PROJECT_ROOT / "data"
HTF_BACKTEST_DIR = DATA_DIR / "htf_backtest"
HTF_LABELS_DIR = DATA_DIR / "htf_4class_labels"
HTF_LABELS_DIR.mkdir(exist_ok=True)


def select_incremental_label_batches(
    label_batches: set[int],
    existing_label_files: list[Path],
    tail_batches: int,
) -> tuple[set[int], set[int], list[int]]:
    """Select target/compute batches for incremental label refresh.

    Always includes:
    - the most recent `tail_batches`
    - any missing historical label batches that are already labelable
    - a single warmup batch immediately before the earliest target batch

    Compute batches span the full available range from the warmup batch through the
    latest target batch to preserve contiguous rolling context.
    """
    sorted_label_batches = sorted(label_batches)
    if not sorted_label_batches:
        return set(), set(), []

    existing_ids = {
        int(path.stem.split("_")[1])
        for path in existing_label_files
        if path.stem.startswith("batch_")
    }
    missing_batches = sorted(set(sorted_label_batches) - existing_ids)
    tail_targets = sorted_label_batches[-tail_batches:]
    target_batches = set(tail_targets) | set(missing_batches)

    min_target = min(target_batches)
    max_target = max(target_batches)
    warmup_batch = min_target - 1
    compute_batches = {
        bid
        for bid in label_batches
        if (warmup_batch <= bid <= max_target)
    }

    return target_batches, compute_batches, missing_batches

# =============================================================================
# STEP 1.1: CONFIGURATION CONSTANTS
# =============================================================================
# Only use bars within the current batch (no next-batch borrowing).
# This means the last 1 bar (15m) and last 3 bars (5m) are unlabeled
# due to missing forward bars needed for distance metrics.
MIN_REMAINING_BARS_BY_TF = {"5m": 3, "15m": 1}
OUTLIER_PERCENTILE = 0.05  # Top/bottom 5%
BB_PERIOD = 20
BB_STD = 2.0

# Per-timeframe optimal thresholds (used for labeling + batch stats)
TF_THRESHOLDS = {
    "5m": {"BREAKOUT": 1.6, "RISK_RATIO": 2.5},  # MSE=47.21 (structural mismatch)
    "15m": {"BREAKOUT": 2.1, "RISK_RATIO": 2.5},  # MSE=1.39 (perfect fit)
}

# Bars per 8h batch by timeframe
BARS_PER_8H = {"5m": 96, "15m": 32}
BARS_PER_2H = {"5m": 24, "15m": 8}

# Timeframes to process in this cell (1m hybrid labels are built in CELL 9B).
# Use a local name to avoid overriding global pipeline scope.
DISTANCE_TIMEFRAMES = ["5m", "15m"]

RECOMPUTE_DISTANCE_METRICS = False  # Fast mode default: update tail batches only when INCREMENTAL_DISTANCE_METRICS=True
INCREMENTAL_DISTANCE_METRICS = (
    True  # If True and RECOMPUTE_DISTANCE_METRICS=False, rebuild only tail batches
)
INCREMENTAL_TAIL_BATCHES_BY_TF = {"5m": 8, "15m": 8}

print("=" * 70)
print("DISTANCE METRICS COMPUTATION FOR 4-CLASS TARGET LABELING")
print("=" * 70)
print(f"Config: MIN_REMAINING_BARS_BY_TF={MIN_REMAINING_BARS_BY_TF}")
print(
    f"        OUTLIER_PERCENTILE={OUTLIER_PERCENTILE}, BB_PERIOD={BB_PERIOD}, BB_STD={BB_STD}"
)
print(f"        TF_THRESHOLDS={TF_THRESHOLDS}")
print("=" * 70)


# =============================================================================
# STEP 1.2: NUMBA FUNCTION FOR PER-BAR METRICS
# =============================================================================
@njit
def compute_distance_metrics(
    close,
    high,
    low,
    batch_id,
    bar_pos,
    bars_per_batch,
    min_remaining,
):
    """
    Compute distance metrics for each bar (current batch only).
    """
    n = len(close)
    dist_avg_high = np.full(n, np.nan, dtype=np.float64)
    dist_avg_low = np.full(n, np.nan, dtype=np.float64)
    dist_top5_high = np.full(n, np.nan, dtype=np.float64)
    dist_bot5_low = np.full(n, np.nan, dtype=np.float64)
    remaining_bars_out = np.full(n, 0, dtype=np.int32)

    outlier_pct = 0.05  # Top/bottom 5%

    for i in range(n):
        entry = close[i]
        current_batch = batch_id[i]

        # Find batch end
        batch_end = i + 1
        while batch_end < n and batch_id[batch_end] == current_batch:
            batch_end += 1

        count = batch_end - (i + 1)
        remaining_bars_out[i] = count

        if count < min_remaining:
            continue

        # Collect remaining highs/lows (current batch only)
        highs = np.zeros(count, dtype=np.float64)
        lows = np.zeros(count, dtype=np.float64)
        for j in range(count):
            highs[j] = high[i + 1 + j]
            lows[j] = low[i + 1 + j]

        # Sort for percentiles
        sorted_highs = np.sort(highs)
        sorted_lows = np.sort(lows)
        top_n = max(1, int(count * outlier_pct))

        # Compute averages
        avg_high = np.mean(highs)
        avg_low = np.mean(lows)
        avg_top_high = np.mean(sorted_highs[-top_n:])
        avg_bot_low = np.mean(sorted_lows[:top_n])

        # Compute distances as percentages
        dist_avg_high[i] = 100.0 * (avg_high - entry) / entry
        dist_avg_low[i] = 100.0 * (entry - avg_low) / entry
        dist_top5_high[i] = 100.0 * (avg_top_high - entry) / entry
        dist_bot5_low[i] = 100.0 * (entry - avg_bot_low) / entry

    return (
        dist_avg_high,
        dist_avg_low,
        dist_top5_high,
        dist_bot5_low,
        remaining_bars_out,
    )


# =============================================================================
# STEP 1.3: PROCESS EACH TIMEFRAME
# =============================================================================
if RECOMPUTE_DISTANCE_METRICS or INCREMENTAL_DISTANCE_METRICS:
    run_mode = "full_recompute" if RECOMPUTE_DISTANCE_METRICS else "incremental_tail"
    print(f"Run mode: {run_mode}")
    for tf in DISTANCE_TIMEFRAMES:
        print(f"\n{'=' * 50}")
        print(f"Processing {tf}...")
        print("=" * 50)

        # 1. Load data
        input_path = HTF_BACKTEST_DIR / f"{tf}_HTF_combined.parquet"
        df = pl.read_parquet(input_path)
        print(f"  Loaded: {len(df):,} rows")
        df = df.sort(["batch_id", "timestamp"])

        # 2. Compute BB indicators
        df = (
            df.with_columns(
                [
                    pl.col("close")
                    .rolling_mean(window_size=BB_PERIOD)
                    .alias("bb_middle"),
                    pl.col("close").rolling_std(window_size=BB_PERIOD).alias("bb_std"),
                ]
            )
            .with_columns(
                [
                    (pl.col("bb_middle") + BB_STD * pl.col("bb_std")).alias("bb_upper"),
                    (pl.col("bb_middle") - BB_STD * pl.col("bb_std")).alias("bb_lower"),
                ]
            )
            .with_columns(
                [
                    (
                        (pl.col("close") - pl.col("bb_lower"))
                        / (pl.col("bb_upper") - pl.col("bb_lower"))
                        * 100
                    ).alias("bb_position_pct"),
                ]
            )
        )

        # 3. Compute bar position within batch
        df = df.with_columns(
            (pl.col("timestamp").rank("ordinal").over("batch_id") - 1)
            .cast(pl.Int32)
            .alias("bar_pos")
        )

        # 4. Filter batches robustly:
        #    - keep full batches
        #    - always keep LAST (possibly incomplete) batch for live-update continuity
        #      (rows without enough forward bars will naturally stay unlabeled later)
        bars_per_batch = BARS_PER_8H[tf]
        min_remaining = MIN_REMAINING_BARS_BY_TF.get(tf, 1)
        # Keep last batch even if it has only 1 row
        min_last_batch_bars = 1

        batch_counts = df.group_by("batch_id").agg(pl.len().alias("n")).sort("batch_id")
        last_batch_id = batch_counts["batch_id"].max()
        valid_batches = batch_counts.filter(
            (pl.col("n") == bars_per_batch)
            | (
                (pl.col("batch_id") == last_batch_id)
                & (pl.col("n") >= min_last_batch_bars)
            )
        )["batch_id"].to_list()

        df = df.filter(pl.col("batch_id").is_in(valid_batches))
        print(
            f"  Valid batches: {len(valid_batches):,} ({len(df):,} rows) "
            f"(last batch included with >= {min_last_batch_bars} row)"
        )

        output_path = HTF_BACKTEST_DIR / f"{tf}_distance_metrics.parquet"
        if RECOMPUTE_DISTANCE_METRICS or not output_path.exists():
            rebuild_batches = valid_batches
            print("  Rebuild scope: all valid batches")
        else:
            tail_n = INCREMENTAL_TAIL_BATCHES_BY_TF.get(tf, 8)
            existing_metric_batches = set(
                pl.read_parquet(output_path, columns=["batch_id"])["batch_id"]
                .unique()
                .to_list()
            )
            missing_batches = sorted(set(valid_batches) - existing_metric_batches)
            tail_batches = valid_batches[-tail_n:]
            rebuild_batches = sorted(set(tail_batches) | set(missing_batches))
            print(
                f"  Rebuild scope: target={len(rebuild_batches)} batches "
                f"({rebuild_batches[0]}..{rebuild_batches[-1]}), "
                f"missing_backfill={len(missing_batches)}"
            )

        if len(rebuild_batches) == 0:
            print("  ⚠️ No batches selected for rebuild, skipping timeframe")
            continue

        df = df.filter(pl.col("batch_id").is_in(rebuild_batches))

        # 5. Add 2h segment column
        df = df.with_columns((pl.col("bar_pos") // BARS_PER_2H[tf]).alias("segment_2h"))

        # 6. Run numba function
        close_np = df["close"].to_numpy()
        high_np = df["high"].to_numpy()
        low_np = df["low"].to_numpy()
        batch_id_np = df["batch_id"].to_numpy()
        bar_pos_np = df["bar_pos"].to_numpy()

        d_avg_high, d_avg_low, d_top5_high, d_bot5_low, remaining = (
            compute_distance_metrics(
                close_np,
                high_np,
                low_np,
                batch_id_np,
                bar_pos_np,
                bars_per_batch,
                min_remaining,
            )
        )

        # 7. Add columns to dataframe
        df = df.with_columns(
            [
                pl.Series("dist_avg_high", d_avg_high),
                pl.Series("dist_avg_low", d_avg_low),
                pl.Series("dist_top5_high", d_top5_high),
                pl.Series("dist_bot5_low", d_bot5_low),
                pl.Series("remaining_bars", remaining),
            ]
        )

        # Count valid bars
        valid_count = len(df.filter(pl.col("dist_avg_high").is_not_nan()))
        print(
            f"  Valid bars (with metrics): {valid_count:,} ({100 * valid_count / len(df):.1f}%)"
        )

        # 8. Save per-bar metrics (incremental upsert by batch_id)
        if RECOMPUTE_DISTANCE_METRICS or not output_path.exists():
            df_out = df
        else:
            df_prev = pl.read_parquet(output_path).filter(
                ~pl.col("batch_id").is_in(rebuild_batches)
            )
            df_out = pl.concat([df_prev, df], how="diagonal_relaxed").sort(
                ["batch_id", "timestamp"]
            )

        df_out.write_parquet(output_path)
        print(f"  ✓ Saved {output_path.name}")
        meta = {
            "updated_at": datetime.now().isoformat(),
            "mode": run_mode,
            "timeframe": tf,
            "updated_batches": [int(b) for b in rebuild_batches],
            "updated_batches_count": int(len(rebuild_batches)),
            "total_rows_saved": int(len(df_out)),
            "min_remaining_bars": int(min_remaining),
            "bars_per_batch": int(bars_per_batch),
        }
        meta_path = HTF_BACKTEST_DIR / f"{tf}_distance_metrics_meta.json"
        with open(meta_path, "w") as f:
            json.dump(meta, f, indent=2)
        print(f"  ✓ Saved {meta_path.name}")

        del df
        if "df_out" in locals():
            del df_out
        if "df_prev" in locals():
            del df_prev
        gc.collect()

    print("\n" + "=" * 70)
    print("PHASE 1.3 COMPLETE: Distance metrics computed for all timeframes")
    print("=" * 70)
else:
    print(
        "Skipping recomputation (RECOMPUTE_DISTANCE_METRICS=False and INCREMENTAL_DISTANCE_METRICS=False)"
    )


# =============================================================================
# STEP 1.4: COMPUTE PER-BATCH AGGREGATES
# =============================================================================
print("\n" + "=" * 70)
print("STEP 1.4: COMPUTING PER-BATCH AGGREGATES")
print("=" * 70)


@njit
def compute_4class_label_numba(
    dist_avg_high,
    dist_avg_low,
    dist_top5_high,
    dist_bot5_low,
    breakout_thresh,
    risk_ratio,
):
    """Compute 4-class label for a single bar."""
    if np.isnan(dist_avg_high):
        return -1  # Invalid

    epsilon = 1e-10
    is_breakout_up = dist_avg_low < 0
    is_breakout_down = dist_avg_high < 0

    # Direction
    if is_breakout_up:
        is_up = True
    elif is_breakout_down:
        is_up = False
    else:
        is_up = dist_avg_high > dist_avg_low

    # Risk flags (dual threshold)
    if is_breakout_up:
        high_risk_up = dist_top5_high > breakout_thresh
        high_risk_down = False
    elif is_breakout_down:
        high_risk_up = False
        high_risk_down = dist_bot5_low > breakout_thresh
    else:
        high_risk_up = (dist_top5_high / (dist_avg_high + epsilon)) > risk_ratio
        high_risk_down = (dist_bot5_low / (dist_avg_low + epsilon)) > risk_ratio

    is_expansion = high_risk_up or high_risk_down
    if is_up:
        return 3 if is_expansion else 2  # UP_EXPANSION / UP_BALANCED
    return 1 if is_expansion else 0  # DOWN_EXPANSION / DOWN_BALANCED


@njit
def compute_4class_labels_batch(
    dist_avg_high,
    dist_avg_low,
    dist_top5_high,
    dist_bot5_low,
    breakout_thresh,
    risk_ratio,
):
    """Vectorized 4-class labeling using numba."""
    n = len(dist_avg_high)
    labels = np.full(n, -1, dtype=np.int8)
    for i in range(n):
        labels[i] = compute_4class_label_numba(
            dist_avg_high[i],
            dist_avg_low[i],
            dist_top5_high[i],
            dist_bot5_low[i],
            breakout_thresh,
            risk_ratio,
        )
    return labels


for tf in DISTANCE_TIMEFRAMES:
    print(f"\nProcessing {tf} batch stats...")

    # Load distance metrics
    df = pl.read_parquet(HTF_BACKTEST_DIR / f"{tf}_distance_metrics.parquet")

    thresholds = TF_THRESHOLDS.get(tf)
    if thresholds is None:
        print(f"  ⚠️ No thresholds for {tf}, skipping batch stats")
        del df
        gc.collect()
        continue

    # Compute 4-class labels using numba
    labels = compute_4class_labels_batch(
        df["dist_avg_high"].to_numpy(),
        df["dist_avg_low"].to_numpy(),
        df["dist_top5_high"].to_numpy(),
        df["dist_bot5_low"].to_numpy(),
        thresholds["BREAKOUT"],
        thresholds["RISK_RATIO"],
    )
    df = df.with_columns(pl.Series("target_4class", labels))

    # Re-save with labels
    df.write_parquet(HTF_BACKTEST_DIR / f"{tf}_distance_metrics.parquet")

    # Check if we have valid data for batch stats
    valid_df = df.filter(pl.col("target_4class") >= 0)
    if len(valid_df) == 0:
        print(f"  ⚠️ No valid bars for {tf}, skipping batch stats")
        del df
        gc.collect()
        continue

    # Aggregate per batch
    batch_stats = valid_df.group_by("batch_id").agg(
        [
            (pl.col("target_4class") == 0).sum().alias("class_0_count"),
            (pl.col("target_4class") == 1).sum().alias("class_1_count"),
            (pl.col("target_4class") == 2).sum().alias("class_2_count"),
            (pl.col("target_4class") == 3).sum().alias("class_3_count"),
            pl.len().alias("valid_bars"),
            (pl.col("target_4class").is_in([2, 3])).mean().alias("up_pct"),
            pl.col("dist_top5_high").mean().alias("avg_top5_high"),
            pl.col("dist_bot5_low").mean().alias("avg_bot5_low"),
            ((pl.col("target_4class").is_in([1, 3])).mean()).alias("outlier_frequency"),
        ]
    )

    # Compute dominant class
    class_cols = [f"class_{i}_count" for i in range(4)]
    batch_stats = batch_stats.with_columns(
        pl.concat_list(class_cols).list.arg_max().alias("dominant_class")
    )

    # Compute volatility regime (with None handling)
    global_avg_outlier = batch_stats["avg_top5_high"].mean()
    if global_avg_outlier is not None and len(batch_stats) > 0:
        batch_stats = batch_stats.with_columns(
            pl.when(pl.col("avg_top5_high") > global_avg_outlier * 1.5)
            .then(pl.lit("HIGH"))
            .when(pl.col("avg_top5_high") < global_avg_outlier * 0.5)
            .then(pl.lit("LOW"))
            .otherwise(pl.lit("NORMAL"))
            .alias("volatility_regime")
        )
        batch_stats = batch_stats.with_columns(
            pl.when(pl.col("up_pct") > 0.6)
            .then(pl.lit("BULLISH"))
            .when(pl.col("up_pct") < 0.4)
            .then(pl.lit("BEARISH"))
            .otherwise(pl.lit("NEUTRAL"))
            .alias("direction_bias")
        )
    else:
        batch_stats = batch_stats.with_columns(
            [
                pl.lit("UNKNOWN").alias("volatility_regime"),
                pl.lit("UNKNOWN").alias("direction_bias"),
            ]
        )

    # Save batch stats
    output_path = HTF_BACKTEST_DIR / f"{tf}_batch_stats.parquet"
    batch_stats.write_parquet(output_path)
    print(f"  ✓ Saved {output_path.name}: {len(batch_stats):,} batches")

    # Print quick class distribution
    total = len(valid_df)
    print(f"  Class distribution (n={total:,}):")
    for cls in range(4):
        count = len(valid_df.filter(pl.col("target_4class") == cls))
        pct = 100 * count / total if total > 0 else 0
        print(f"    {cls}: {count:>8,} ({pct:>5.1f}%)")

    del df, batch_stats, valid_df
    gc.collect()

print("\n" + "=" * 70)
print("STEP 1.4 COMPLETE: Batch aggregates saved")
print("=" * 70)


# =============================================================================
# STEP 1.5: SAVE SUMMARY JSON
# =============================================================================
print("\n" + "=" * 70)
print("STEP 1.5: SAVING SUMMARY JSON")
print("=" * 70)

summary = {
    "computed_at": datetime.now().isoformat(),
    "parameters": {
        "MIN_REMAINING_BARS_BY_TF": MIN_REMAINING_BARS_BY_TF,
        "OUTLIER_PERCENTILE": OUTLIER_PERCENTILE,
        "BB_PERIOD": BB_PERIOD,
        "BB_STD": BB_STD,
        "TF_THRESHOLDS": TF_THRESHOLDS,
    },
    "timeframes": {},
}

for tf in DISTANCE_TIMEFRAMES:
    df = pl.read_parquet(HTF_BACKTEST_DIR / f"{tf}_distance_metrics.parquet")
    df_valid = df.filter(pl.col("dist_avg_high").is_not_nan())

    # Handle empty or None stats
    if len(df_valid) > 0:
        avg_high = df_valid["dist_avg_high"].mean()
        avg_low = df_valid["dist_avg_low"].mean()
        top5_high = df_valid["dist_top5_high"].mean()
        bot5_low = df_valid["dist_bot5_low"].mean()
        global_stats = {
            "dist_avg_high_mean": float(avg_high) if avg_high is not None else None,
            "dist_avg_low_mean": float(avg_low) if avg_low is not None else None,
            "dist_top5_high_mean": float(top5_high) if top5_high is not None else None,
            "dist_bot5_low_mean": float(bot5_low) if bot5_low is not None else None,
        }
    else:
        global_stats = {
            "dist_avg_high_mean": None,
            "dist_avg_low_mean": None,
            "dist_top5_high_mean": None,
            "dist_bot5_low_mean": None,
        }

    summary["timeframes"][tf] = {
        "total_bars": len(df),
        "valid_bars": len(df_valid),
        "complete_batches": df["batch_id"].n_unique(),
        "global_stats": global_stats,
    }
    del df, df_valid

summary_path = HTF_BACKTEST_DIR / "distance_metrics_summary.json"
with open(summary_path, "w") as f:
    json.dump(summary, f, indent=2)

print(f"✓ Saved {summary_path.name}")
print("\nSummary contents:")
print(json.dumps(summary, indent=2))

gc.collect()
print("\n" + "=" * 70)
print("PHASE 1 COMPLETE: All distance metrics, batch stats, and summary saved")
print("=" * 70)

# %%
# =============================================================================
# CELL 8: 4-CLASS TARGET LABELING (15m IMPLEMENTATION)
# =============================================================================
# Implements the validated 4-class labeling system:
#   - Precomputed distance metrics from Cell 7
#   - Per-timeframe optimal thresholds from grid search
#
# Classes:
#   0: DOWN_BALANCED     - Down direction, no extreme outliers
#   1: DOWN_CONT         - Down with strong downside momentum
#   2: DOWN_VOLATILE     - Down with both-side outliers
#   3: UP_BALANCED       - Up direction, no extreme outliers
#   4: UP_CONT           - Up with strong upside momentum
#   5: UP_VOLATILE       - Up with both-side outliers
#   6: UP_REVERSAL_RISK  - Up but has significant downside outliers
#   7: DOWN_REVERSAL_RISK- Down but has significant upside outliers
#
# Output: {tf}_labels.parquet in HTF_LABELS_DIR (target_4class)
# =============================================================================

import json
from datetime import datetime
from pathlib import Path

import polars as pl

# =============================================================================
# PATHS
# =============================================================================
PROJECT_ROOT = resolve_project_root() if "resolve_project_root" in globals() else Path("..").resolve()
DATA_DIR = PROJECT_ROOT / "data"
HTF_BACKTEST_DIR = DATA_DIR / "htf_backtest"
HTF_LABELS_DIR = DATA_DIR / "htf_4class_labels"
HTF_LABELS_DIR.mkdir(exist_ok=True)

# =============================================================================
# PER-TIMEFRAME OPTIMAL THRESHOLDS (from grid search)
# (Defined in STEP 1.1 above; reused here)
# =============================================================================

# Class names for display
CLASS_NAMES = {
    0: "DOWN_BALANCED",
    1: "DOWN_EXPANSION",
    2: "UP_BALANCED",
    3: "UP_EXPANSION",
}

# Target distribution reference (collapsed from prior detailed class scheme)
DOC_TARGETS = {0: 25.5, 1: 23.6, 2: 28.4, 3: 22.6}

# Breakfree threshold (end-of-batch close distance)
# end_return = (close_end - close_now) / close_now
# target_breakfree (3-class, position-aware, non-overlapping):
#   0: UP_ABOVE_BREAKFREE
#      (4-class is UP-side and end_return >= +threshold)
#   1: DOWN_ABOVE_BREAKFREE
#      (4-class is DOWN-side and end_return <= -threshold)
#   2: IN_BETWEEN_BELOW_BREAKFREE
#      (valid 4-class row but neither UP_ABOVE nor DOWN_ABOVE condition met)
#   -1: invalid / unlabeled (invalid 4-class row)
BREAKFREE_THRESHOLD = 0.001  # 0.10%
# Only consider entries in the first 4h of each 8h batch
ENTRY_WINDOW_HOURS = 4

# Which timeframes to process (15m first since it matches perfectly)
PROCESS_TIMEFRAMES = ["15m"]  # Add "5m" later with 5m-specific targets

RECOMPUTE_LABELS = False  # Fast mode default: update label tail batches only
INCREMENTAL_LABEL_UPDATE = True
INCREMENTAL_LABEL_TAIL_BATCHES_BY_TF = {"15m": 8, "5m": 8, "1m": 8}

print("=" * 70)
print("4-CLASS TARGET LABELING")
print("=" * 70)
print(f"Processing timeframes: {PROCESS_TIMEFRAMES}")
print(f"Output directory: {HTF_LABELS_DIR}")
print(f"Min remaining bars per TF: {MIN_REMAINING_BARS_BY_TF} (exclude last bars)")
print(f"Entry window: first {ENTRY_WINDOW_HOURS}h of each 8h batch")
print("=" * 70)


# =============================================================================
# LABELING FUNCTION (VECTORIZED POLARS)
# =============================================================================
def compute_4class_labels(
    df: pl.DataFrame, breakout_thresh: float, risk_thresh: float
) -> pl.DataFrame:
    """
    Compute 4-class labels using vectorized Polars expressions.

    Classes:
    - 0 DOWN_BALANCED
    - 1 DOWN_EXPANSION
    - 2 UP_BALANCED
    - 3 UP_EXPANSION
    """
    eps = 1e-10

    # Scenario detection
    df = df.with_columns(
        [
            (pl.col("dist_avg_low") < 0).alias("is_breakout_up"),
            (pl.col("dist_avg_high") < 0).alias("is_breakout_down"),
            ((pl.col("dist_avg_low") > 0) & (pl.col("dist_avg_high") > 0)).alias(
                "is_oscillation"
            ),
        ]
    )

    # Direction: breakout UP → UP, breakout DOWN → DOWN, oscillation → compare avgs
    df = df.with_columns(
        [
            pl.when(pl.col("is_breakout_up"))
            .then(pl.lit(True))
            .when(pl.col("is_breakout_down"))
            .then(pl.lit(False))
            .otherwise(pl.col("dist_avg_high") > pl.col("dist_avg_low"))
            .alias("is_up")
        ]
    )

    # Risk flags
    # For breakouts: use absolute threshold
    # For oscillation: use ratio threshold
    df = df.with_columns(
        [
            # high_risk_up
            pl.when(pl.col("is_breakout_up"))
            .then(pl.col("dist_top5_high") > breakout_thresh)
            .when(pl.col("is_breakout_down"))
            .then(pl.lit(False))  # Ignore upside in breakout DOWN
            .otherwise(
                (pl.col("dist_top5_high") / (pl.col("dist_avg_high") + eps))
                > risk_thresh
            )
            .alias("high_risk_up"),
            # high_risk_down
            pl.when(pl.col("is_breakout_down"))
            .then(pl.col("dist_bot5_low") > breakout_thresh)
            .when(pl.col("is_breakout_up"))
            .then(pl.lit(False))  # Ignore downside in breakout UP
            .otherwise(
                (pl.col("dist_bot5_low") / (pl.col("dist_avg_low") + eps)) > risk_thresh
            )
            .alias("high_risk_down"),
        ]
    )

    # Compute 4-class label
    df = df.with_columns(
        [
            pl.when(pl.col("dist_avg_high").is_nan())
            .then(pl.lit(-1))  # Invalid bar
            .when(pl.col("is_up") & (pl.col("high_risk_up") | pl.col("high_risk_down")))
            .then(pl.lit(3))  # UP_EXPANSION
            .when(pl.col("is_up"))
            .then(pl.lit(2))  # UP_BALANCED
            .when(
                ~pl.col("is_up") & (pl.col("high_risk_up") | pl.col("high_risk_down"))
            )
            .then(pl.lit(1))  # DOWN_EXPANSION
            .when(~pl.col("is_up"))
            .then(pl.lit(0))  # DOWN_BALANCED
            .otherwise(pl.lit(-1))
            .alias("target_4class")
        ]
    )

    # Add class name column
    df = df.with_columns(
        [
            pl.col("target_4class")
            .replace_strict(
                {i: name for i, name in CLASS_NAMES.items()}, default="INVALID"
            )
            .alias("target_name")
        ]
    )

    # Clean up intermediate columns
    df = df.drop(
        [
            "is_breakout_up",
            "is_breakout_down",
            "is_oscillation",
            "is_up",
            "high_risk_up",
            "high_risk_down",
        ]
    )

    return df


# =============================================================================
# PROCESS EACH TIMEFRAME
# =============================================================================
results = {}

for tf in PROCESS_TIMEFRAMES:
    print(f"\n{'=' * 30} {tf.upper()} {'=' * 30}")

    # Get thresholds
    thresholds = TF_THRESHOLDS[tf]
    bt = thresholds["BREAKOUT"]
    rt = thresholds["RISK_RATIO"]
    print(f"Thresholds: BREAKOUT={bt}%, RISK_RATIO={rt}x")

    # Load distance metrics
    metrics_path = HTF_BACKTEST_DIR / f"{tf}_distance_metrics.parquet"
    if not metrics_path.exists():
        print(f"  ⚠️ Distance metrics not found: {metrics_path}")
        print("     Run Cell 7 first to compute distance metrics")
        continue

    print(f"Loading: {metrics_path.name}")
    df = pl.read_parquet(metrics_path)
    print(f"  → {len(df):,} rows")

    # Incremental scope: rebuild only tail batches if label files already exist
    tf_labels_dir = HTF_LABELS_DIR / tf
    tf_labels_dir.mkdir(exist_ok=True)
    combined_path = HTF_BACKTEST_DIR / f"{tf}_HTF_combined.parquet"
    label_output_cols = [
        "timestamp",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "batch_id",
        "bar_pos",
        "remaining_bars",
        "bb_upper",
        "bb_lower",
        "bb_middle",
        "bb_position_pct",
        "segment_2h",
        "dist_avg_high",
        "dist_avg_low",
        "dist_top5_high",
        "dist_bot5_low",
        "close_end",
        "end_return",
        "target_4class",
        "target_name",
        "target_breakfree",
        *LABEL_SHARED_META_COLS,
    ]
    labels_meta_path = tf_labels_dir / "_labels_meta.json"
    label_source_fingerprint = {
        "combined": fingerprint_paths([combined_path]),
        "distance_metrics": fingerprint_paths([metrics_path]),
    }
    rebuild_reasons, label_rebuild_mode = prepare_stage_rebuild(
        stage_name=f"Labels B/{tf}",
        meta_path=labels_meta_path,
        artifact_version=ARTIFACT_STAGE_VERSIONS["labels"],
        family="B",
        timeframe=tf,
        source_fingerprint=label_source_fingerprint,
        schema_columns=label_output_cols,
        output_targets=[tf_labels_dir],
        inspect_batch_dir=tf_labels_dir,
        required_batch_columns=set(
            ["timestamp", "batch_id", "target_4class", "target_breakfree", *LABEL_SHARED_META_COLS]
        ),
    )
    existing_label_files = sorted(tf_labels_dir.glob("batch_*.parquet"))
    all_batches = sorted(df["batch_id"].unique().to_list())
    if (
        RECOMPUTE_LABELS
        or not INCREMENTAL_LABEL_UPDATE
        or not existing_label_files
        or label_rebuild_mode == "full"
    ):
        target_batches = all_batches
        print("  Label scope: full")
    else:
        tail_n = INCREMENTAL_LABEL_TAIL_BATCHES_BY_TF.get(tf, 8)
        target_batches, _, missing_batches = select_incremental_label_batches(
            label_batches=set(all_batches),
            existing_label_files=existing_label_files,
            tail_batches=tail_n,
        )
        target_batches = sorted(target_batches)
        print(
            f"  Label scope: incremental target={len(target_batches)} "
            f"({target_batches[0]}..{target_batches[-1]}), "
            f"missing_backfill={len(missing_batches)}"
        )

    df = df.filter(pl.col("batch_id").is_in(target_batches))
    if len(df) == 0:
        print("  ⚠️ No rows in selected label scope, skipping timeframe")
        continue

    # Compute end-of-batch close distance for breakfree target
    batch_close = df.group_by("batch_id").agg(
        pl.col("close").sort_by("timestamp").last().alias("close_end")
    )
    df = df.join(batch_close, on="batch_id", how="left").with_columns(
        ((pl.col("close_end") - pl.col("close")) / pl.col("close")).alias("end_return")
    )

    # Count valid rows (current batch only), then keep first 4h entry window.
    # We still compute/save labels for ALL rows; invalid rows become -1.
    entry_bar_limit = int(BARS_PER_8H[tf] * (ENTRY_WINDOW_HOURS / 8.0))
    df_valid = df.filter(
        pl.col("dist_avg_high").is_not_nan() & (pl.col("bar_pos") < entry_bar_limit)
    )
    n_valid = len(df_valid)
    n_invalid = len(df) - n_valid
    print(
        f"  → {n_valid:,} valid rows, {n_invalid:,} invalid (insufficient remaining bars)"
    )
    expected_valid = min(
        BARS_PER_8H[tf] - MIN_REMAINING_BARS_BY_TF.get(tf, 1),
        entry_bar_limit,
    )
    print(
        f"  Expected valid rows per full batch: {expected_valid} "
        f"(first {ENTRY_WINDOW_HOURS}h only)"
    )

    if len(df) == 0:
        print(f"  ⚠️ No rows for {tf}. Skipping.")
        continue

    # Compute 4-class labels on full rows; invalid horizon rows become -1
    print("Computing 4-class labels...")
    df_labeled = compute_4class_labels(df, bt, rt)
    df_labeled = df_labeled.with_columns(
        [
            pl.when(pl.col("bar_pos") < entry_bar_limit)
            .then(pl.col("target_4class"))
            .otherwise(pl.lit(-1))
            .alias("target_4class")
        ]
    )
    df_labeled = df_labeled.with_columns(
        [
            pl.col("target_4class")
            .replace_strict(
                {i: name for i, name in CLASS_NAMES.items()}, default="INVALID"
            )
            .alias("target_name")
        ]
    )

    # Breakfree 3-class target (position-aware and non-overlapping)
    # UP classes in 4-class: 2,3
    # DOWN classes in 4-class: 0,1
    df_labeled = df_labeled.with_columns(
        [
            pl.when(pl.col("target_4class") < 0)
            .then(pl.lit(-1))
            .when(
                pl.col("target_4class").is_in([2, 3])
                & (pl.col("end_return") >= BREAKFREE_THRESHOLD)
            )
            .then(pl.lit(0))  # UP_ABOVE_BREAKFREE
            .when(
                pl.col("target_4class").is_in([0, 1])
                & (pl.col("end_return") <= -BREAKFREE_THRESHOLD)
            )
            .then(pl.lit(1))  # DOWN_ABOVE_BREAKFREE
            .otherwise(pl.lit(2))  # IN_BETWEEN_BELOW_BREAKFREE
            .alias("target_breakfree")
        ]
    )

    # ==========================================================================
    # VALIDATE CLASS DISTRIBUTION
    # ==========================================================================
    print(f"\n{'─' * 60}")
    print("CLASS DISTRIBUTION VALIDATION")
    print(f"{'─' * 60}")

    class_counts = (
        df_labeled.filter(pl.col("target_4class") >= 0)
        .group_by("target_4class")
        .agg(pl.len().alias("count"))
        .sort("target_4class")
    )

    total = class_counts["count"].sum()

    print(
        f"\n{'Class':<3} {'Name':<20} {'Count':>10} {'Actual':>8} {'Target':>8} {'Diff':>8} {'Status'}"
    )
    print("-" * 75)

    mse = 0.0
    for cls in range(4):
        row = class_counts.filter(pl.col("target_4class") == cls)
        count = row["count"][0] if len(row) > 0 else 0
        pct = 100 * count / total if total > 0 else 0
        target = DOC_TARGETS[cls]
        diff = pct - target
        mse += diff**2
        status = "✓" if abs(diff) < 2 else "≈" if abs(diff) < 5 else "✗"
        print(
            f"{cls:<3} {CLASS_NAMES[cls]:<20} {count:>10,} {pct:>7.1f}% {target:>7.1f}% {diff:>+7.1f}% {status}"
        )

    print(f"\nMSE to doc targets: {mse:.2f}")

    # Group summary
    print(f"\n{'─' * 60}")
    print("GROUP SUMMARY")
    print(f"{'─' * 60}")

    groups = {
        "DOWN_SIDE": [0, 1],
        "UP_SIDE": [2, 3],
        "BALANCED": [0, 2],
        "EXPANSION": [1, 3],
    }
    doc_group = {
        "DOWN_SIDE": DOC_TARGETS[0] + DOC_TARGETS[1],
        "UP_SIDE": DOC_TARGETS[2] + DOC_TARGETS[3],
        "BALANCED": DOC_TARGETS[0] + DOC_TARGETS[2],
        "EXPANSION": DOC_TARGETS[1] + DOC_TARGETS[3],
    }

    for name, classes in groups.items():
        group_count = sum(
            class_counts.filter(pl.col("target_4class") == c)["count"][0]
            if len(class_counts.filter(pl.col("target_4class") == c)) > 0
            else 0
            for c in classes
        )
        pct = 100 * group_count / total if total > 0 else 0
        target = doc_group[name]
        print(f"  {name:<12}: {pct:>6.1f}% (target: {target:.1f}%)")

    # ==========================================================================
    # SAVE LABELED DATA (PER-BATCH for downstream compatibility)
    # ==========================================================================
    print(f"\nSaving per-batch files to: {tf_labels_dir}")

    # Only keep columns that exist
    available_cols = [c for c in label_output_cols if c in df_labeled.columns]
    df_output = df_labeled.select(available_cols)

    # Save per-batch (8h aligned) - overwrite only selected scope
    batch_ids = df_output["batch_id"].unique().sort().to_list()
    for bid in batch_ids:
        batch_df = df_output.filter(pl.col("batch_id") == bid)
        batch_path = tf_labels_dir / f"batch_{bid:04d}.parquet"
        batch_df.write_parquet(batch_path)

    print(f"  ✓ Saved {len(batch_ids):,} batch files ({len(df_output):,} total rows)")
    labels_meta = artifact_meta_payload(
        artifact_version=ARTIFACT_STAGE_VERSIONS["labels"],
        family="B",
        timeframe=tf,
        source_fingerprint=label_source_fingerprint,
        schema_columns=available_cols,
        rebuild_mode=label_rebuild_mode,
        extra={
            "rebuild_reasons": rebuild_reasons,
            "updated_batches": [int(b) for b in batch_ids],
            "updated_batches_count": int(len(batch_ids)),
            "entry_window_hours": ENTRY_WINDOW_HOURS,
            "breakfree_threshold": BREAKFREE_THRESHOLD,
            "rows": int(len(df_output)),
        },
    )
    with open(labels_meta_path, "w") as f:
        json.dump(labels_meta, f, indent=2)
    print(f"  ✓ Saved {labels_meta_path.name}")

    results[tf] = {
        "batches": len(batch_ids),
        "rows": len(df_output),
        "mse": mse,
        "thresholds": thresholds,
    }

    del df, df_valid, df_labeled, df_output
    import gc

    gc.collect()

# =============================================================================
# SUMMARY
# =============================================================================
print("\n" + "=" * 70)
print("4-CLASS LABELING COMPLETE")
print("=" * 70)

for tf, res in results.items():
    print(f"\n{tf}:")
    print(f"  Batches: {res['batches']:,}")
    print(f"  Rows: {res['rows']:,}")
    print(f"  MSE: {res['mse']:.2f}")
    print(
        f"  Thresholds: BREAKOUT={res['thresholds']['BREAKOUT']}%, RISK_RATIO={res['thresholds']['RISK_RATIO']}x"
    )
    print(f"  Output: {HTF_LABELS_DIR / tf}/batch_*.parquet")

print(f"\n{'=' * 70}")
print("NEXT STEPS")
print("=" * 70)
print("1. Use target_4class as ML target for classification")
print("2. Filter to valid rows (target_4class >= 0)")
print("3. Train model to predict class given features")
print("4. For 5m/1m hybrid, use 15m future bars for distance metrics")
print("=" * 70)

# %%
# =============================================================================
# CELL 8B: SHIFT4H FAMILY C - 15m DISTANCE METRICS + LABELS
# =============================================================================
print("\n" + "=" * 70)
print("SHIFT4H FAMILY C - 15M DISTANCE METRICS + LABELS")
print("=" * 70)

SHIFT4H_15M_INPUT = HTF_BACKTEST_SHIFT4H_DIR / "15m_HTF_combined.parquet"
SHIFT4H_15M_METRICS = HTF_BACKTEST_SHIFT4H_DIR / "15m_distance_metrics.parquet"
SHIFT4H_15M_METRICS_META = HTF_BACKTEST_SHIFT4H_DIR / "15m_distance_metrics_meta.json"
SHIFT4H_15M_LABEL_DIR = HTF_LABELS_SHIFT4H_DIR / "15m"
SHIFT4H_15M_LABEL_DIR.mkdir(parents=True, exist_ok=True)

if SHIFT4H_15M_INPUT.exists():
    df_c15 = pl.read_parquet(SHIFT4H_15M_INPUT).sort(["batch_id", "timestamp"])
    bars_per_batch_15m = BARS_PER_8H["15m"]
    min_remaining_15m = MIN_REMAINING_BARS_BY_TF.get("15m", 1)
    batch_counts_c15 = (
        df_c15.group_by("batch_id").agg(pl.len().alias("n")).sort("batch_id")
    )
    last_batch_c15 = batch_counts_c15["batch_id"].max()
    valid_batches_c15 = batch_counts_c15.filter(
        (pl.col("n") == bars_per_batch_15m)
        | ((pl.col("batch_id") == last_batch_c15) & (pl.col("n") >= 1))
    )["batch_id"].to_list()
    df_c15 = df_c15.filter(pl.col("batch_id").is_in(valid_batches_c15))
    df_c15 = df_c15.with_columns(
        [
            pl.col("family_bar_pos").cast(pl.Int32).alias("bar_pos"),
            pl.col("bb_middle"),
        ]
    ) if "bb_middle" in df_c15.columns else (
        df_c15.with_columns(pl.col("family_bar_pos").cast(pl.Int32).alias("bar_pos"))
    )
    df_c15 = (
        df_c15.with_columns(
            [
                pl.col("close").rolling_mean(window_size=BB_PERIOD).alias("bb_middle"),
                pl.col("close").rolling_std(window_size=BB_PERIOD).alias("bb_std"),
            ]
        )
        .with_columns(
            [
                (pl.col("bb_middle") + BB_STD * pl.col("bb_std")).alias("bb_upper"),
                (pl.col("bb_middle") - BB_STD * pl.col("bb_std")).alias("bb_lower"),
            ]
        )
        .with_columns(
            (
                (pl.col("close") - pl.col("bb_lower"))
                / (pl.col("bb_upper") - pl.col("bb_lower"))
                * 100
            ).alias("bb_position_pct")
        )
        .with_columns((pl.col("bar_pos") // BARS_PER_2H["15m"]).alias("segment_2h"))
    )

    shift15_metric_schema = sorted(
        [*df_c15.columns, "dist_avg_high", "dist_avg_low", "dist_top5_high", "dist_bot5_low", "remaining_bars"]
    )
    shift15_metric_fingerprint = {
        "shift4h_combined": fingerprint_paths(
            [SHIFT4H_15M_INPUT, _shift4h_combined_meta_path("15m")]
        ),
    }
    metric_rebuild_reasons, metric_rebuild_mode = prepare_stage_rebuild(
        stage_name="Shift4h 15m metrics",
        meta_path=SHIFT4H_15M_METRICS_META,
        artifact_version=ARTIFACT_STAGE_VERSIONS["shift4h_metrics"],
        family="C",
        timeframe="15m",
        source_fingerprint=shift15_metric_fingerprint,
        schema_columns=shift15_metric_schema,
        output_targets=[SHIFT4H_15M_METRICS, SHIFT4H_15M_METRICS_META],
    )
    if metric_rebuild_mode == "full":
        rebuild_c15_batches = valid_batches_c15
        missing_c15_batches = valid_batches_c15
    else:
        existing_c15_batches = (
            set(
                pl.read_parquet(SHIFT4H_15M_METRICS, columns=["batch_id"])[
                    "batch_id"
                ]
                .unique()
                .to_list()
            )
            if SHIFT4H_15M_METRICS.exists()
            else set()
        )
        missing_c15_batches = sorted(set(valid_batches_c15) - existing_c15_batches)
        tail_c15 = valid_batches_c15[-INCREMENTAL_TAIL_BATCHES_BY_TF.get("15m", 8) :]
        rebuild_c15_batches = sorted(set(tail_c15) | set(missing_c15_batches))
    print(
        f"  Shift4h 15m metrics rebuild: target={len(rebuild_c15_batches)} "
        f"(missing_backfill={len(missing_c15_batches)})"
    )
    df_c15_rebuild = df_c15.filter(pl.col("batch_id").is_in(rebuild_c15_batches))
    d_avg_high, d_avg_low, d_top5_high, d_bot5_low, remaining = compute_distance_metrics(
        df_c15_rebuild["close"].to_numpy(),
        df_c15_rebuild["high"].to_numpy(),
        df_c15_rebuild["low"].to_numpy(),
        df_c15_rebuild["batch_id"].to_numpy(),
        df_c15_rebuild["bar_pos"].to_numpy(),
        bars_per_batch_15m,
        min_remaining_15m,
    )
    df_c15_rebuild = df_c15_rebuild.with_columns(
        [
            pl.Series("dist_avg_high", d_avg_high),
            pl.Series("dist_avg_low", d_avg_low),
            pl.Series("dist_top5_high", d_top5_high),
            pl.Series("dist_bot5_low", d_bot5_low),
            pl.Series("remaining_bars", remaining),
        ]
    )
    if SHIFT4H_15M_METRICS.exists() and metric_rebuild_mode != "full":
        prev = pl.read_parquet(SHIFT4H_15M_METRICS).filter(
            ~pl.col("batch_id").is_in(rebuild_c15_batches)
        )
        df_c15_metrics = pl.concat([prev, df_c15_rebuild], how="diagonal_relaxed").sort(
            ["batch_id", "timestamp"]
        )
    else:
        df_c15_metrics = df_c15_rebuild
    df_c15_metrics.write_parquet(SHIFT4H_15M_METRICS)
    with open(SHIFT4H_15M_METRICS_META, "w") as f:
        json.dump(
            artifact_meta_payload(
                artifact_version=ARTIFACT_STAGE_VERSIONS["shift4h_metrics"],
                family="C",
                timeframe="15m",
                source_fingerprint=shift15_metric_fingerprint,
                schema_columns=sorted(df_c15_metrics.columns),
                rebuild_mode=metric_rebuild_mode,
                extra={
                    "rebuild_reasons": metric_rebuild_reasons,
                    "updated_batches": [int(b) for b in rebuild_c15_batches],
                    "updated_batches_count": int(len(rebuild_c15_batches)),
                    "rows": int(len(df_c15_metrics)),
                },
            ),
            f,
            indent=2,
        )

    shift15_cols = [
        "timestamp",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "batch_id",
        "bar_pos",
        "remaining_bars",
        "bb_upper",
        "bb_lower",
        "bb_middle",
        "bb_position_pct",
        "segment_2h",
        "dist_avg_high",
        "dist_avg_low",
        "dist_top5_high",
        "dist_bot5_low",
        "close_end",
        "end_return",
        "target_4class",
        "target_name",
        "target_breakfree",
        *LABEL_SHARED_META_COLS,
    ]
    shift15_label_meta_path = SHIFT4H_15M_LABEL_DIR / "_labels_meta.json"
    shift15_label_fingerprint = {
        "shift4h_combined": fingerprint_paths(
            [SHIFT4H_15M_INPUT, _shift4h_combined_meta_path("15m")]
        ),
        "shift4h_metrics": fingerprint_paths([SHIFT4H_15M_METRICS, SHIFT4H_15M_METRICS_META]),
    }
    shift15_rebuild_reasons, shift15_rebuild_mode = prepare_stage_rebuild(
        stage_name="Shift4h 15m labels",
        meta_path=shift15_label_meta_path,
        artifact_version=ARTIFACT_STAGE_VERSIONS["labels"],
        family="C",
        timeframe="15m",
        source_fingerprint=shift15_label_fingerprint,
        schema_columns=shift15_cols,
        output_targets=[SHIFT4H_15M_LABEL_DIR],
        inspect_batch_dir=SHIFT4H_15M_LABEL_DIR,
        required_batch_columns=set(
            ["timestamp", "batch_id", "target_4class", "target_breakfree", *LABEL_SHARED_META_COLS]
        ),
    )
    existing_shift15_labels = sorted(SHIFT4H_15M_LABEL_DIR.glob("batch_*.parquet"))
    shift15_all_batches = set(sorted(df_c15_metrics["batch_id"].unique().to_list()))
    if not existing_shift15_labels or shift15_rebuild_mode == "full":
        target_shift15_batches = shift15_all_batches
        missing_shift15 = sorted(shift15_all_batches)
    else:
        target_shift15_batches, _, missing_shift15 = select_incremental_label_batches(
            label_batches=shift15_all_batches,
            existing_label_files=existing_shift15_labels,
            tail_batches=INCREMENTAL_LABEL_TAIL_BATCHES_BY_TF.get("15m", 8),
        )
    print(
        f"  Shift4h 15m labels: target={len(target_shift15_batches)} "
        f"(missing_backfill={len(missing_shift15)})"
    )
    df_shift15_labels = df_c15_metrics.filter(pl.col("batch_id").is_in(sorted(target_shift15_batches)))
    batch_close_shift15 = df_shift15_labels.group_by("batch_id").agg(
        pl.col("close").sort_by("timestamp").last().alias("close_end")
    )
    df_shift15_labels = df_shift15_labels.join(batch_close_shift15, on="batch_id", how="left").with_columns(
        ((pl.col("close_end") - pl.col("close")) / pl.col("close")).alias("end_return")
    )
    df_shift15_labels = compute_4class_labels(
        df_shift15_labels,
        TF_THRESHOLDS["15m"]["BREAKOUT"],
        TF_THRESHOLDS["15m"]["RISK_RATIO"],
    )
    entry_bar_limit_shift15 = int(BARS_PER_8H["15m"] * (ENTRY_WINDOW_HOURS / 8.0))
    df_shift15_labels = df_shift15_labels.with_columns(
        [
            pl.when(pl.col("family_bar_pos") < entry_bar_limit_shift15)
            .then(pl.col("target_4class"))
            .otherwise(pl.lit(-1))
            .alias("target_4class")
        ]
    )
    df_shift15_labels = df_shift15_labels.with_columns(
        [
            pl.when(pl.col("target_4class") < 0)
            .then(pl.lit(-1))
            .when(
                pl.col("target_4class").is_in([2, 3])
                & (pl.col("end_return") >= BREAKFREE_THRESHOLD)
            )
            .then(pl.lit(0))
            .when(
                pl.col("target_4class").is_in([0, 1])
                & (pl.col("end_return") <= -BREAKFREE_THRESHOLD)
            )
            .then(pl.lit(1))
            .otherwise(pl.lit(2))
            .alias("target_breakfree")
        ]
    )
    df_shift15_out = df_shift15_labels.select([c for c in shift15_cols if c in df_shift15_labels.columns])
    for bid in sorted(df_shift15_out["batch_id"].unique().to_list()):
        df_shift15_out.filter(pl.col("batch_id") == bid).write_parquet(
            SHIFT4H_15M_LABEL_DIR / f"batch_{int(bid):04d}.parquet"
        )
    with open(shift15_label_meta_path, "w") as f:
        json.dump(
            artifact_meta_payload(
                artifact_version=ARTIFACT_STAGE_VERSIONS["labels"],
                family="C",
                timeframe="15m",
                source_fingerprint=shift15_label_fingerprint,
                schema_columns=df_shift15_out.columns,
                rebuild_mode=shift15_rebuild_mode,
                extra={
                    "rebuild_reasons": shift15_rebuild_reasons,
                    "updated_batches": [
                        int(b) for b in sorted(df_shift15_out["batch_id"].unique().to_list())
                    ],
                    "updated_batches_count": int(df_shift15_out["batch_id"].n_unique()),
                    "rows": int(len(df_shift15_out)),
                },
            ),
            f,
            indent=2,
        )
    print(
        f"  ✓ Shift4h 15m labels saved: batches={df_shift15_out['batch_id'].n_unique()} "
        f"rows={len(df_shift15_out):,}"
    )
else:
    print("  ⚠️ Missing shift4h 15m combined input, skipping shift family 15m labels")

# %%
# =============================================================================
# CELL 9: HYBRID 5m TARGET LABELING (5m ENTRY + 15m DISTANCE METRICS)
# =============================================================================
# This cell implements a hybrid approach for 5m timeframe:
#   - Entry reference: 5m close (granular entry timing)
#   - Distance metrics: computed from remaining 15m bars (smoother targets)
#
# Why this works:
#   - Each 5m bar gets unique distances because entry close differs
#   - But the future bars used are 15m (less noisy than 5m)
#   - Inherits 15m's better oscillation/breakout distribution (~26% vs 16%)
#
# Current-batch only:
#   - No next-batch borrowing
#   - Last 3 (5m) bars of each batch are unlabeled (need 1 remaining 15m bar)
#
# Output: data/htf_4class_labels/5m/batch_XXXX.parquet
# =============================================================================

import gc
import json
from datetime import datetime
from pathlib import Path

import polars as pl
from numba import njit

# =============================================================================
# PATHS
# =============================================================================
PROJECT_ROOT = resolve_project_root() if "resolve_project_root" in globals() else Path("..").resolve()
DATA_DIR = PROJECT_ROOT / "data"
HTF_BACKTEST_DIR = DATA_DIR / "htf_backtest"
HTF_LABELS_DIR = DATA_DIR / "htf_4class_labels"
HTF_LABELS_DIR.mkdir(exist_ok=True)

# Shared hybrid-label configuration for Cells 9/9B/9C
MIN_REMAINING_BARS_15M = 1
MIN_REMAINING_BARS_5M = MIN_REMAINING_BARS_15M * 3
OUTLIER_PERCENTILE = 0.05
BB_PERIOD = 20
BB_STD = 2.0
BARS_PER_8H_15M = 32
BARS_PER_8H_5M = 96
BREAKOUT_THRESHOLD = 2.1
RISK_RATIO = 2.5
ENTRY_WINDOW_HOURS_5M = 4
BREAKFREE_THRESHOLD_5M = 0.001
INCREMENTAL_LABEL_UPDATE_5M = True
INCREMENTAL_TAIL_BATCHES_5M = 8

CLASS_NAMES = {
    0: "DOWN_BALANCED",
    1: "DOWN_EXPANSION",
    2: "UP_BALANCED",
    3: "UP_EXPANSION",
}


@njit
def compute_hybrid_distance_metrics(
    close_entry,
    batch_id_entry,
    bar_pos_15m_for_entry,
    high_15m,
    low_15m,
    batch_id_15m,
    bar_pos_15m,
    min_remaining,
    outlier_pct,
):
    """Hybrid future-distance metrics using entry closes and 15m future bars."""
    n = len(close_entry)
    dist_avg_high = np.full(n, np.nan, dtype=np.float64)
    dist_avg_low = np.full(n, np.nan, dtype=np.float64)
    dist_top5_high = np.full(n, np.nan, dtype=np.float64)
    dist_bot5_low = np.full(n, np.nan, dtype=np.float64)
    remaining_bars_out = np.full(n, 0, dtype=np.int32)

    n_15m = len(high_15m)
    for i in range(n):
        entry = close_entry[i]
        current_batch = batch_id_entry[i]
        current_15m_pos = bar_pos_15m_for_entry[i]

        highs = []
        lows = []
        for j in range(n_15m):
            if batch_id_15m[j] == current_batch and bar_pos_15m[j] > current_15m_pos:
                highs.append(high_15m[j])
                lows.append(low_15m[j])

        count = len(highs)
        remaining_bars_out[i] = count
        if count < min_remaining:
            continue

        highs_arr = np.array(highs, dtype=np.float64)
        lows_arr = np.array(lows, dtype=np.float64)
        sorted_highs = np.sort(highs_arr)
        sorted_lows = np.sort(lows_arr)
        top_n = max(1, int(count * outlier_pct))

        avg_high = np.mean(highs_arr)
        avg_low = np.mean(lows_arr)
        avg_top_high = np.mean(sorted_highs[-top_n:])
        avg_bot_low = np.mean(sorted_lows[:top_n])

        dist_avg_high[i] = 100.0 * (avg_high - entry) / entry
        dist_avg_low[i] = 100.0 * (entry - avg_low) / entry
        dist_top5_high[i] = 100.0 * (avg_top_high - entry) / entry
        dist_bot5_low[i] = 100.0 * (entry - avg_bot_low) / entry

    return (
        dist_avg_high,
        dist_avg_low,
        dist_top5_high,
        dist_bot5_low,
        remaining_bars_out,
    )


if "compute_4class_labels" not in globals():
    def compute_4class_labels(
        df: pl.DataFrame, breakout_thresh: float, risk_thresh: float
    ) -> pl.DataFrame:
        eps = 1e-10
        df = df.with_columns(
            [
                (pl.col("dist_avg_low") < 0).alias("is_breakout_up"),
                (pl.col("dist_avg_high") < 0).alias("is_breakout_down"),
                ((pl.col("dist_avg_low") > 0) & (pl.col("dist_avg_high") > 0)).alias(
                    "is_oscillation"
                ),
            ]
        )
        df = df.with_columns(
            [
                pl.when(pl.col("is_breakout_up"))
                .then(pl.lit(True))
                .when(pl.col("is_breakout_down"))
                .then(pl.lit(False))
                .otherwise(pl.col("dist_avg_high") > pl.col("dist_avg_low"))
                .alias("is_up")
            ]
        )
        df = df.with_columns(
            [
                pl.when(pl.col("is_breakout_up"))
                .then(pl.col("dist_top5_high") > breakout_thresh)
                .when(pl.col("is_breakout_down"))
                .then(pl.lit(False))
                .otherwise(
                    (pl.col("dist_top5_high") / (pl.col("dist_avg_high") + eps))
                    > risk_thresh
                )
                .alias("high_risk_up"),
                pl.when(pl.col("is_breakout_down"))
                .then(pl.col("dist_bot5_low") > breakout_thresh)
                .when(pl.col("is_breakout_up"))
                .then(pl.lit(False))
                .otherwise(
                    (pl.col("dist_bot5_low") / (pl.col("dist_avg_low") + eps))
                    > risk_thresh
                )
                .alias("high_risk_down"),
            ]
        )
        df = df.with_columns(
            [
                pl.when(pl.col("dist_avg_high").is_nan())
                .then(pl.lit(-1))
                .when(
                    pl.col("is_up")
                    & (pl.col("high_risk_up") | pl.col("high_risk_down"))
                )
                .then(pl.lit(3))
                .when(pl.col("is_up"))
                .then(pl.lit(2))
                .when(
                    ~pl.col("is_up")
                    & (pl.col("high_risk_up") | pl.col("high_risk_down"))
                )
                .then(pl.lit(1))
                .when(~pl.col("is_up"))
                .then(pl.lit(0))
                .otherwise(pl.lit(-1))
                .alias("target_4class")
            ]
        )
        df = df.with_columns(
            pl.col("target_4class")
            .replace_strict({i: name for i, name in CLASS_NAMES.items()}, default="INVALID")
            .alias("target_name")
        )
        return df.drop(
            [
                "is_breakout_up",
                "is_breakout_down",
                "is_oscillation",
                "is_up",
                "high_risk_up",
                "high_risk_down",
                "batch_id_check",
            ]
        )


print("=" * 70)
print("HYBRID 5m TARGET LABELING (5m Entry + 15m Distance Metrics)")
print("=" * 70)
if not ENABLE_5M_PIPELINE:
    print("5m pipeline disabled by ENABLE_5M_PIPELINE=False; skipping Cell 9 materialization.")
    print("Shared hybrid helpers remain available for Cell 9B and Cell 9C.")
else:
    print(f"Thresholds: BREAKOUT={BREAKOUT_THRESHOLD}%, RISK_RATIO={RISK_RATIO}x")
    print(f"Entry window: first {ENTRY_WINDOW_HOURS_5M}h of each 8h batch")

    df_5m = pl.read_parquet(HTF_BACKTEST_DIR / "5m_HTF_combined.parquet").sort("timestamp")
    df_15m = pl.read_parquet(HTF_BACKTEST_DIR / "15m_HTF_combined.parquet").sort("timestamp")
    counts_5m = df_5m.group_by("batch_id").agg(pl.len().alias("n")).sort("batch_id")
    counts_15m = df_15m.group_by("batch_id").agg(pl.len().alias("n")).sort("batch_id")
    last_5m = counts_5m["batch_id"].max()
    last_15m = counts_15m["batch_id"].max()
    valid_5m = counts_5m.filter(
        (pl.col("n") == BARS_PER_8H_5M)
        | ((pl.col("batch_id") == last_5m) & (pl.col("n") >= 1))
    )["batch_id"].to_list()
    valid_15m = counts_15m.filter(
        (pl.col("n") == BARS_PER_8H_15M)
        | ((pl.col("batch_id") == last_15m) & (pl.col("n") >= 1))
    )["batch_id"].to_list()
    label_batches = set(valid_5m) & set(valid_15m)

    tf_labels_dir = HTF_LABELS_DIR / "5m"
    tf_labels_dir.mkdir(exist_ok=True)
    label_output_cols_5m = [
        "timestamp",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "batch_id",
        "bar_pos_5m",
        "bar_pos_15m",
        "remaining_bars",
        "bb_upper",
        "bb_lower",
        "bb_middle",
        "bb_position_pct",
        "segment_2h",
        "dist_avg_high",
        "dist_avg_low",
        "dist_top5_high",
        "dist_bot5_low",
        "close_end",
        "end_return",
        "target_4class",
        "target_name",
        "target_breakfree",
        *LABEL_SHARED_META_COLS,
    ]
    labels_meta_5m_path = tf_labels_dir / "_labels_meta.json"
    labels_5m_fingerprint = {
        "combined_5m": fingerprint_paths([HTF_BACKTEST_DIR / "5m_HTF_combined.parquet"]),
        "combined_15m": fingerprint_paths([HTF_BACKTEST_DIR / "15m_HTF_combined.parquet"]),
    }
    labels_5m_reasons, labels_5m_rebuild_mode = prepare_stage_rebuild(
        stage_name="Labels B/5m",
        meta_path=labels_meta_5m_path,
        artifact_version=ARTIFACT_STAGE_VERSIONS["labels"],
        family="B",
        timeframe="5m",
        source_fingerprint=labels_5m_fingerprint,
        schema_columns=label_output_cols_5m,
        output_targets=[tf_labels_dir],
        inspect_batch_dir=tf_labels_dir,
        required_batch_columns=set(
            ["timestamp", "batch_id", "target_4class", "target_breakfree", *LABEL_SHARED_META_COLS]
        ),
    )
    existing_5m_labels = sorted(tf_labels_dir.glob("batch_*.parquet"))
    if (
        INCREMENTAL_LABEL_UPDATE_5M
        and existing_5m_labels
        and label_batches
        and labels_5m_rebuild_mode != "full"
    ):
        target_batches_5m, compute_batches_5m, missing_5m_batches = (
            select_incremental_label_batches(
                label_batches=label_batches,
                existing_label_files=existing_5m_labels,
                tail_batches=INCREMENTAL_TAIL_BATCHES_5M,
            )
        )
        print(
            f"Incremental 5m labels: target={len(target_batches_5m)} "
            f"compute={len(compute_batches_5m)} "
            f"(missing_backfill={len(missing_5m_batches)})"
        )
    else:
        target_batches_5m = set(label_batches)
        compute_batches_5m = set(label_batches)
        print("5m label update mode: full")

    df_5m = df_5m.filter(pl.col("batch_id").is_in(compute_batches_5m))
    df_15m = df_15m.filter(pl.col("batch_id").is_in(compute_batches_5m))
    batch_close_5m = df_5m.group_by("batch_id").agg(
        pl.col("close").sort_by("timestamp").last().alias("close_end")
    )
    df_5m = df_5m.join(batch_close_5m, on="batch_id", how="left").with_columns(
        ((pl.col("close_end") - pl.col("close")) / pl.col("close")).alias("end_return")
    )
    df_5m = df_5m.with_columns(
        [
            (pl.col("timestamp").rank("ordinal").over("batch_id") - 1)
            .cast(pl.Int32)
            .alias("bar_pos_5m"),
            pl.col("timestamp").dt.truncate("15m").alias("ts_15m"),
        ]
    )
    df_15m = df_15m.with_columns(
        (pl.col("timestamp").rank("ordinal").over("batch_id") - 1)
        .cast(pl.Int32)
        .alias("bar_pos_15m")
    )
    df_5m = (
        df_5m.with_columns(
            [
                pl.col("close").rolling_mean(window_size=BB_PERIOD).alias("bb_middle"),
                pl.col("close").rolling_std(window_size=BB_PERIOD).alias("bb_std"),
            ]
        )
        .with_columns(
            [
                (pl.col("bb_middle") + BB_STD * pl.col("bb_std")).alias("bb_upper"),
                (pl.col("bb_middle") - BB_STD * pl.col("bb_std")).alias("bb_lower"),
            ]
        )
        .with_columns(
            (
                (pl.col("close") - pl.col("bb_lower"))
                / (pl.col("bb_upper") - pl.col("bb_lower"))
                * 100
            ).alias("bb_position_pct")
        )
        .with_columns((pl.col("bar_pos_5m") // 24).alias("segment_2h"))
    )
    df_15m_pos = df_15m.select(
        [
            pl.col("timestamp").alias("ts_15m"),
            pl.col("batch_id").alias("batch_id_check"),
            "bar_pos_15m",
        ]
    )
    df_5m = df_5m.join(df_15m_pos, on="ts_15m", how="left")
    d_avg_high, d_avg_low, d_top5_high, d_bot5_low, remaining = (
        compute_hybrid_distance_metrics(
            df_5m["close"].to_numpy().astype("float64"),
            df_5m["batch_id"].to_numpy().astype("int64"),
            df_5m["bar_pos_15m"].fill_null(0).to_numpy().astype("int32"),
            df_15m["high"].to_numpy().astype("float64"),
            df_15m["low"].to_numpy().astype("float64"),
            df_15m["batch_id"].to_numpy().astype("int64"),
            df_15m["bar_pos_15m"].to_numpy().astype("int32"),
            MIN_REMAINING_BARS_15M,
            OUTLIER_PERCENTILE,
        )
    )
    df_5m = df_5m.with_columns(
        [
            pl.Series("dist_avg_high", d_avg_high),
            pl.Series("dist_avg_low", d_avg_low),
            pl.Series("dist_top5_high", d_top5_high),
            pl.Series("dist_bot5_low", d_bot5_low),
            pl.Series("remaining_bars", remaining),
        ]
    )
    entry_bar_limit_5m = int(BARS_PER_8H_5M * (ENTRY_WINDOW_HOURS_5M / 8.0))
    df_labeled = compute_4class_labels(df_5m, BREAKOUT_THRESHOLD, RISK_RATIO)
    df_labeled = df_labeled.with_columns(
        [
            pl.when(pl.col("target_4class") < 0)
            .then(pl.lit(-1))
            .when(
                pl.col("target_4class").is_in([2, 3])
                & (pl.col("end_return") >= BREAKFREE_THRESHOLD_5M)
            )
            .then(pl.lit(0))
            .when(
                pl.col("target_4class").is_in([0, 1])
                & (pl.col("end_return") <= -BREAKFREE_THRESHOLD_5M)
            )
            .then(pl.lit(1))
            .otherwise(pl.lit(2))
            .alias("target_breakfree")
        ]
    )
    df_labeled = df_labeled.with_columns(
        [
            pl.when(pl.col("bar_pos_5m") < entry_bar_limit_5m)
            .then(pl.col("target_4class"))
            .otherwise(pl.lit(-1))
            .alias("target_4class"),
            pl.when(pl.col("bar_pos_5m") < entry_bar_limit_5m)
            .then(pl.col("target_breakfree"))
            .otherwise(pl.lit(-1))
            .alias("target_breakfree"),
        ]
    )
    df_labeled = df_labeled.with_columns(
        pl.col("target_4class")
        .replace_strict({i: name for i, name in CLASS_NAMES.items()}, default="INVALID")
        .alias("target_name")
    )
    available_cols = [c for c in label_output_cols_5m if c in df_labeled.columns]
    df_output = df_labeled.filter(pl.col("batch_id").is_in(target_batches_5m)).select(
        available_cols
    )
    batch_ids = df_output["batch_id"].unique().sort().to_list()
    for bid in batch_ids:
        df_output.filter(pl.col("batch_id") == bid).write_parquet(
            tf_labels_dir / f"batch_{bid:04d}.parquet"
        )
    labels_meta_5m = artifact_meta_payload(
        artifact_version=ARTIFACT_STAGE_VERSIONS["labels"],
        family="B",
        timeframe="5m",
        source_fingerprint=labels_5m_fingerprint,
        schema_columns=available_cols,
        rebuild_mode=labels_5m_rebuild_mode,
        extra={
            "rebuild_reasons": labels_5m_reasons,
            "updated_batches": [int(b) for b in batch_ids],
            "updated_batches_count": int(len(batch_ids)),
            "entry_window_hours": ENTRY_WINDOW_HOURS_5M,
            "breakfree_threshold": BREAKFREE_THRESHOLD_5M,
            "rows": int(len(df_output)),
        },
    )
    with open(labels_meta_5m_path, "w") as f:
        json.dump(labels_meta_5m, f, indent=2)
    print(f"5m labels saved: batches={len(batch_ids)} rows={len(df_output):,}")
    del df_5m, df_15m, df_labeled, df_output
    gc.collect()

# %%
# =============================================================================
# CELL 9B: HYBRID 1m TARGET LABELING (1m ENTRY + 15m DISTANCE METRICS)
# =============================================================================
# This mirrors Cell 9 logic used for 5m:
#   - Entry reference: 1m close
#   - Future distance metrics: remaining 15m bars from the same 8h batch
#   - Same BREAKOUT/RISK thresholds as 15m and 5m hybrid, so target levels align
#   - Labels restricted to first 4h of each 8h batch
#
# Output: data/htf_4class_labels/1m/batch_XXXX.parquet
# =============================================================================

import gc
import json
from datetime import datetime
from pathlib import Path

import polars as pl

if "compute_hybrid_distance_metrics" not in globals():
    raise RuntimeError(
        "Run CELL 9 first (compute_hybrid_distance_metrics is required)."
    )
if "compute_4class_labels" not in globals():
    raise RuntimeError("Run CELL 9 first (compute_4class_labels is required).")

PROJECT_ROOT = resolve_project_root() if "resolve_project_root" in globals() else Path("..").resolve()
DATA_DIR = PROJECT_ROOT / "data"
HTF_BACKTEST_DIR = DATA_DIR / "htf_backtest"
HTF_LABELS_DIR = DATA_DIR / "htf_4class_labels"
HTF_LABELS_DIR.mkdir(exist_ok=True)

# 1m entry config (hybrid distances still use 15m bars)
MIN_REMAINING_BARS_15M = 1
MIN_REMAINING_BARS_1M = MIN_REMAINING_BARS_15M * 15
BARS_PER_8H_15M = 32
BARS_PER_8H_1M = 480
ENTRY_WINDOW_HOURS_1M = 4
BREAKFREE_THRESHOLD_1M = 0.001  # 0.10%
INCREMENTAL_LABEL_UPDATE_1M = True
INCREMENTAL_TAIL_BATCHES_1M = 8

print("=" * 70)
print("HYBRID 1m TARGET LABELING (1m Entry + 15m Distance Metrics)")
print("=" * 70)
print(f"Thresholds: BREAKOUT={BREAKOUT_THRESHOLD}%, RISK_RATIO={RISK_RATIO}x")
print(f"Entry window: first {ENTRY_WINDOW_HOURS_1M}h of each 8h batch")
print("=" * 70)

print("\n[STEP 1] Loading 1m + 15m data...")
df_1m = pl.read_parquet(HTF_BACKTEST_DIR / "1m_HTF_combined.parquet").sort("timestamp")
df_15m = pl.read_parquet(HTF_BACKTEST_DIR / "15m_HTF_combined.parquet").sort(
    "timestamp"
)

print(f"  1m bars: {len(df_1m):,}")
print(f"  15m bars: {len(df_15m):,}")

# Keep full batches and always include last partial batch for live continuity
counts_1m = df_1m.group_by("batch_id").agg(pl.len().alias("n")).sort("batch_id")
counts_15m = df_15m.group_by("batch_id").agg(pl.len().alias("n")).sort("batch_id")
last_1m = counts_1m["batch_id"].max()
last_15m = counts_15m["batch_id"].max()
min_last_1m = 1
min_last_15m = 1

valid_1m = counts_1m.filter(
    (pl.col("n") == BARS_PER_8H_1M)
    | ((pl.col("batch_id") == last_1m) & (pl.col("n") >= min_last_1m))
)["batch_id"].to_list()
valid_15m_for_label = counts_15m.filter(
    (pl.col("n") == BARS_PER_8H_15M)
    | ((pl.col("batch_id") == last_15m) & (pl.col("n") >= min_last_15m))
)["batch_id"].to_list()

label_batches = set(valid_1m) & set(valid_15m_for_label)
print(
    f"  Label batches (both TFs): {len(label_batches):,} "
    f"(last batch included with >= {min_last_1m} row in each TF)"
)

tf_labels_dir_1m = HTF_LABELS_DIR / "1m"
tf_labels_dir_1m.mkdir(exist_ok=True)
label_output_cols_1m = [
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "batch_id",
    "bar_pos_1m",
    "bar_pos_15m",
    "remaining_bars",
    "bb_upper",
    "bb_lower",
    "bb_middle",
    "bb_position_pct",
    "segment_2h",
    "dist_avg_high",
    "dist_avg_low",
    "dist_top5_high",
    "dist_bot5_low",
    "close_end",
    "end_return",
    "target_4class",
    "target_name",
    "target_breakfree",
    *LABEL_SHARED_META_COLS,
]
labels_meta_1m_path = tf_labels_dir_1m / "_labels_meta.json"
labels_1m_fingerprint = {
    "combined_1m": fingerprint_paths([HTF_BACKTEST_DIR / "1m_HTF_combined.parquet"]),
    "combined_15m": fingerprint_paths([HTF_BACKTEST_DIR / "15m_HTF_combined.parquet"]),
}
labels_1m_reasons, labels_1m_rebuild_mode = prepare_stage_rebuild(
    stage_name="Labels B/1m",
    meta_path=labels_meta_1m_path,
    artifact_version=ARTIFACT_STAGE_VERSIONS["labels"],
    family="B",
    timeframe="1m",
    source_fingerprint=labels_1m_fingerprint,
    schema_columns=label_output_cols_1m,
    output_targets=[tf_labels_dir_1m],
    inspect_batch_dir=tf_labels_dir_1m,
    required_batch_columns=set(
        ["timestamp", "batch_id", "target_4class", "target_breakfree", *LABEL_SHARED_META_COLS]
    ),
)
existing_1m_labels = sorted(tf_labels_dir_1m.glob("batch_*.parquet"))
sorted_label_batches_1m = sorted(label_batches)
if (
    INCREMENTAL_LABEL_UPDATE_1M
    and existing_1m_labels
    and len(sorted_label_batches_1m) > 0
    and labels_1m_rebuild_mode != "full"
):
    target_batches_1m, compute_batches_1m, missing_1m_batches = (
        select_incremental_label_batches(
            label_batches=label_batches,
            existing_label_files=existing_1m_labels,
            tail_batches=INCREMENTAL_TAIL_BATCHES_1M,
        )
    )
    print(
        f"  Incremental label update: target={len(target_batches_1m)} batches, "
        f"compute={len(compute_batches_1m)} (missing_backfill={len(missing_1m_batches)})"
    )
else:
    target_batches_1m = set(label_batches)
    compute_batches_1m = set(label_batches)
    print("  Label update mode: full")

df_1m = df_1m.filter(pl.col("batch_id").is_in(compute_batches_1m))
df_15m = df_15m.filter(pl.col("batch_id").is_in(compute_batches_1m))
print(f"  Filtered 1m bars: {len(df_1m):,}")
print(f"  Filtered 15m bars: {len(df_15m):,}")

# End-of-batch close distance for breakfree target
batch_close_1m = df_1m.group_by("batch_id").agg(
    pl.col("close").sort_by("timestamp").last().alias("close_end")
)
df_1m = df_1m.join(batch_close_1m, on="batch_id", how="left").with_columns(
    ((pl.col("close_end") - pl.col("close")) / pl.col("close")).alias("end_return")
)

print("\n[STEP 2] Computing bar positions and 15m mapping...")
df_1m = df_1m.with_columns(
    (pl.col("timestamp").rank("ordinal").over("batch_id") - 1)
    .cast(pl.Int32)
    .alias("bar_pos_1m")
)
df_1m = df_1m.with_columns(pl.col("timestamp").dt.truncate("15m").alias("ts_15m"))
df_15m = df_15m.with_columns(
    (pl.col("timestamp").rank("ordinal").over("batch_id") - 1)
    .cast(pl.Int32)
    .alias("bar_pos_15m")
)

# BB context on 1m entry stream
df_1m = (
    df_1m.with_columns(
        [
            pl.col("close").rolling_mean(window_size=BB_PERIOD).alias("bb_middle"),
            pl.col("close").rolling_std(window_size=BB_PERIOD).alias("bb_std"),
        ]
    )
    .with_columns(
        [
            (pl.col("bb_middle") + BB_STD * pl.col("bb_std")).alias("bb_upper"),
            (pl.col("bb_middle") - BB_STD * pl.col("bb_std")).alias("bb_lower"),
        ]
    )
    .with_columns(
        (
            (pl.col("close") - pl.col("bb_lower"))
            / (pl.col("bb_upper") - pl.col("bb_lower"))
            * 100
        ).alias("bb_position_pct")
    )
)
df_1m = df_1m.with_columns((pl.col("bar_pos_1m") // 120).alias("segment_2h"))

print("\n[STEP 3] Computing hybrid distance metrics (1m entry, 15m future)...")
df_15m_pos = df_15m.select(
    [
        pl.col("timestamp").alias("ts_15m"),
        pl.col("batch_id").alias("batch_id_check"),
        "bar_pos_15m",
    ]
)
df_1m = df_1m.join(df_15m_pos, on="ts_15m", how="left")

close_1m_np = df_1m["close"].to_numpy().astype("float64")
batch_id_1m_np = df_1m["batch_id"].to_numpy().astype("int64")
bar_pos_15m_for_1m_np = df_1m["bar_pos_15m"].fill_null(0).to_numpy().astype("int32")
high_15m_np = df_15m["high"].to_numpy().astype("float64")
low_15m_np = df_15m["low"].to_numpy().astype("float64")
batch_id_15m_np = df_15m["batch_id"].to_numpy().astype("int64")
bar_pos_15m_np = df_15m["bar_pos_15m"].to_numpy().astype("int32")

d_avg_high, d_avg_low, d_top5_high, d_bot5_low, remaining = (
    compute_hybrid_distance_metrics(
        close_1m_np,
        batch_id_1m_np,
        bar_pos_15m_for_1m_np,
        high_15m_np,
        low_15m_np,
        batch_id_15m_np,
        bar_pos_15m_np,
        MIN_REMAINING_BARS_15M,
        OUTLIER_PERCENTILE,
    )
)

df_1m = df_1m.with_columns(
    [
        pl.Series("dist_avg_high", d_avg_high),
        pl.Series("dist_avg_low", d_avg_low),
        pl.Series("dist_top5_high", d_top5_high),
        pl.Series("dist_bot5_low", d_bot5_low),
        pl.Series("remaining_bars", remaining),
    ]
)

entry_bar_limit_1m = int(BARS_PER_8H_1M * (ENTRY_WINDOW_HOURS_1M / 8.0))
valid_count = len(df_1m.filter(pl.col("dist_avg_high").is_not_nan()))
expected_valid_1m = min(BARS_PER_8H_1M - MIN_REMAINING_BARS_1M, entry_bar_limit_1m)
print(
    f"  Valid 1m bars (with metrics): {valid_count:,} "
    f"({100 * valid_count / max(1, len(df_1m)):.1f}%)"
)
print(
    f"  Expected valid label rows per full 1m batch: {expected_valid_1m} "
    f"(first {ENTRY_WINDOW_HOURS_1M}h only)"
)

print("\n[STEP 4] Computing 4-class + breakfree labels...")
df_labeled_1m = compute_4class_labels(df_1m, BREAKOUT_THRESHOLD, RISK_RATIO)
df_labeled_1m = df_labeled_1m.with_columns(
    [
        pl.when(pl.col("target_4class") < 0)
        .then(pl.lit(-1))
        .when(
            pl.col("target_4class").is_in([2, 3])
            & (pl.col("end_return") >= BREAKFREE_THRESHOLD_1M)
        )
        .then(pl.lit(0))  # UP_ABOVE_BREAKFREE
        .when(
            pl.col("target_4class").is_in([0, 1])
            & (pl.col("end_return") <= -BREAKFREE_THRESHOLD_1M)
        )
        .then(pl.lit(1))  # DOWN_ABOVE_BREAKFREE
        .otherwise(pl.lit(2))  # IN_BETWEEN_BELOW_BREAKFREE
        .alias("target_breakfree")
    ]
)
df_labeled_1m = df_labeled_1m.with_columns(
    [
        pl.when(pl.col("bar_pos_1m") < entry_bar_limit_1m)
        .then(pl.col("target_4class"))
        .otherwise(pl.lit(-1))
        .alias("target_4class"),
        pl.when(pl.col("bar_pos_1m") < entry_bar_limit_1m)
        .then(pl.col("target_breakfree"))
        .otherwise(pl.lit(-1))
        .alias("target_breakfree"),
    ]
)
df_labeled_1m = df_labeled_1m.with_columns(
    pl.col("target_4class")
    .replace_strict({i: name for i, name in CLASS_NAMES.items()}, default="INVALID")
    .alias("target_name")
)

print("\n[STEP 5] Saving per-batch 1m labels...")
available_cols_1m = [c for c in label_output_cols_1m if c in df_labeled_1m.columns]
df_output_1m = df_labeled_1m.filter(pl.col("batch_id").is_in(target_batches_1m)).select(
    available_cols_1m
)

batch_ids_1m = df_output_1m["batch_id"].unique().sort().to_list()
for bid in batch_ids_1m:
    df_output_1m.filter(pl.col("batch_id") == bid).write_parquet(
        tf_labels_dir_1m / f"batch_{bid:04d}.parquet"
    )

valid_labels_1m = len(df_output_1m.filter(pl.col("target_4class") >= 0))
print(f"  ✓ Saved {len(batch_ids_1m):,} batch files to {tf_labels_dir_1m}")
print(f"  ✓ Total rows: {len(df_output_1m):,}")
print(f"  ✓ Valid 4-class labels: {valid_labels_1m:,}")
labels_meta_1m = artifact_meta_payload(
    artifact_version=ARTIFACT_STAGE_VERSIONS["labels"],
    family="B",
    timeframe="1m",
    source_fingerprint=labels_1m_fingerprint,
    schema_columns=available_cols_1m,
    rebuild_mode=labels_1m_rebuild_mode,
    extra={
        "rebuild_reasons": labels_1m_reasons,
        "updated_batches": [int(b) for b in batch_ids_1m],
        "updated_batches_count": int(len(batch_ids_1m)),
        "entry_window_hours": ENTRY_WINDOW_HOURS_1M,
        "breakfree_threshold": BREAKFREE_THRESHOLD_1M,
        "rows": int(len(df_output_1m)),
        "valid_labels": int(valid_labels_1m),
    },
)
with open(labels_meta_1m_path, "w") as f:
    json.dump(labels_meta_1m, f, indent=2)
print("  ✓ Saved _labels_meta.json")

print("\n" + "=" * 70)
print("HYBRID 1m LABELING COMPLETE")
print("=" * 70)
print("Approach: 1m entry close + 15m remaining bars for distance metrics")
print(f"Output: {tf_labels_dir_1m}/batch_*.parquet")

del df_1m, df_15m, df_labeled_1m, df_output_1m
gc.collect()

# %%
# =============================================================================
# CELL 9C: SHIFT4H FAMILY C - HYBRID 1m TARGET LABELING (1m ENTRY + SHIFT4H 15m DISTANCE METRICS)
# =============================================================================

import gc
import json
from datetime import datetime
from pathlib import Path

import polars as pl

if "compute_hybrid_distance_metrics" not in globals():
    raise RuntimeError(
        "Run CELL 9 first (compute_hybrid_distance_metrics is required)."
    )
if "compute_4class_labels" not in globals():
    raise RuntimeError(
        "Run CELL 9 first (compute_4class_labels is required)."
    )

PROJECT_ROOT = resolve_project_root() if "resolve_project_root" in globals() else Path("..").resolve()
DATA_DIR = PROJECT_ROOT / "data"
HTF_BACKTEST_SHIFT4H_DIR = DATA_DIR / "htf_backtest_shift4h"
HTF_LABELS_SHIFT4H_DIR = DATA_DIR / "htf_4class_labels_shift4h"
HTF_LABELS_SHIFT4H_DIR.mkdir(exist_ok=True)

MIN_REMAINING_BARS_15M_SHIFT = 1
MIN_REMAINING_BARS_1M_SHIFT = MIN_REMAINING_BARS_15M_SHIFT * 15
BARS_PER_8H_15M_SHIFT = 32
BARS_PER_8H_1M_SHIFT = 480
ENTRY_WINDOW_HOURS_1M_SHIFT = 4
BREAKFREE_THRESHOLD_1M_SHIFT = 0.001
INCREMENTAL_LABEL_UPDATE_1M_SHIFT = True
INCREMENTAL_TAIL_BATCHES_1M_SHIFT = 8

print("=" * 70)
print("SHIFT4H FAMILY C - HYBRID 1m TARGET LABELING")
print("=" * 70)
print(f"Thresholds: BREAKOUT={BREAKOUT_THRESHOLD}%, RISK_RATIO={RISK_RATIO}x")
print(f"Entry window: first {ENTRY_WINDOW_HOURS_1M_SHIFT}h of each shifted 8h batch")
print("=" * 70)

shift_1m_input = HTF_BACKTEST_SHIFT4H_DIR / "1m_HTF_combined.parquet"
shift_15m_input = HTF_BACKTEST_SHIFT4H_DIR / "15m_HTF_combined.parquet"
shift_1m_label_dir = HTF_LABELS_SHIFT4H_DIR / "1m"
shift_1m_label_dir.mkdir(exist_ok=True)
shift_output_cols_1m = [
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "batch_id",
    "bar_pos_1m",
    "bar_pos_15m",
    "remaining_bars",
    "bb_upper",
    "bb_lower",
    "bb_middle",
    "bb_position_pct",
    "segment_2h",
    "dist_avg_high",
    "dist_avg_low",
    "dist_top5_high",
    "dist_bot5_low",
    "close_end",
    "end_return",
    "target_4class",
    "target_name",
    "target_breakfree",
    *LABEL_SHARED_META_COLS,
]
shift_1m_label_meta_path = shift_1m_label_dir / "_labels_meta.json"

if not shift_1m_input.exists() or not shift_15m_input.exists():
    print("  ⚠️ Missing shift4h inputs, skipping shift family 1m labels")
else:
    print("\n[STEP 1] Loading shift4h 1m + 15m data...")
    df_1m_shift = pl.read_parquet(shift_1m_input).sort("timestamp")
    df_15m_shift = pl.read_parquet(shift_15m_input).sort("timestamp")

    print(f"  Shift4h 1m bars: {len(df_1m_shift):,}")
    print(f"  Shift4h 15m bars: {len(df_15m_shift):,}")

    counts_1m_shift = (
        df_1m_shift.group_by("batch_id").agg(pl.len().alias("n")).sort("batch_id")
    )
    counts_15m_shift = (
        df_15m_shift.group_by("batch_id").agg(pl.len().alias("n")).sort("batch_id")
    )
    last_1m_shift = counts_1m_shift["batch_id"].max()
    last_15m_shift = counts_15m_shift["batch_id"].max()

    valid_1m_shift = counts_1m_shift.filter(
        (pl.col("n") == BARS_PER_8H_1M_SHIFT)
        | ((pl.col("batch_id") == last_1m_shift) & (pl.col("n") >= 1))
    )["batch_id"].to_list()
    valid_15m_shift = counts_15m_shift.filter(
        (pl.col("n") == BARS_PER_8H_15M_SHIFT)
        | ((pl.col("batch_id") == last_15m_shift) & (pl.col("n") >= 1))
    )["batch_id"].to_list()

    shift_label_batches = set(valid_1m_shift) & set(valid_15m_shift)
    print(
        f"  Shift label batches (both TFs): {len(shift_label_batches):,} "
        f"(last batch included with >= 1 row in each TF)"
    )

    shift_1m_label_fingerprint = {
        "shift4h_combined_1m": fingerprint_paths(
            [shift_1m_input, _shift4h_combined_meta_path("1m")]
        ),
        "shift4h_combined_15m": fingerprint_paths(
            [shift_15m_input, _shift4h_combined_meta_path("15m")]
        ),
    }
    shift_1m_reasons, shift_1m_rebuild_mode = prepare_stage_rebuild(
        stage_name="Shift4h 1m labels",
        meta_path=shift_1m_label_meta_path,
        artifact_version=ARTIFACT_STAGE_VERSIONS["labels"],
        family="C",
        timeframe="1m",
        source_fingerprint=shift_1m_label_fingerprint,
        schema_columns=shift_output_cols_1m,
        output_targets=[shift_1m_label_dir],
        inspect_batch_dir=shift_1m_label_dir,
        required_batch_columns=set(
            ["timestamp", "batch_id", "target_4class", "target_breakfree", *LABEL_SHARED_META_COLS]
        ),
    )
    existing_shift_1m_labels = sorted(shift_1m_label_dir.glob("batch_*.parquet"))
    sorted_shift_label_batches = sorted(shift_label_batches)
    if (
        INCREMENTAL_LABEL_UPDATE_1M_SHIFT
        and existing_shift_1m_labels
        and sorted_shift_label_batches
        and shift_1m_rebuild_mode != "full"
    ):
        target_batches_1m_shift, compute_batches_1m_shift, missing_1m_shift = (
            select_incremental_label_batches(
                label_batches=shift_label_batches,
                existing_label_files=existing_shift_1m_labels,
                tail_batches=INCREMENTAL_TAIL_BATCHES_1M_SHIFT,
            )
        )
        print(
            f"  Incremental shift label update: target={len(target_batches_1m_shift)} batches, "
            f"compute={len(compute_batches_1m_shift)} "
            f"(missing_backfill={len(missing_1m_shift)})"
        )
    else:
        target_batches_1m_shift = set(shift_label_batches)
        compute_batches_1m_shift = set(shift_label_batches)
        print("  Shift label update mode: full")

    df_1m_shift = df_1m_shift.filter(pl.col("batch_id").is_in(compute_batches_1m_shift))
    df_15m_shift = df_15m_shift.filter(pl.col("batch_id").is_in(compute_batches_1m_shift))
    print(f"  Filtered shift4h 1m bars: {len(df_1m_shift):,}")
    print(f"  Filtered shift4h 15m bars: {len(df_15m_shift):,}")

    batch_close_shift = df_1m_shift.group_by("batch_id").agg(
        pl.col("close").sort_by("timestamp").last().alias("close_end")
    )
    df_1m_shift = df_1m_shift.join(batch_close_shift, on="batch_id", how="left").with_columns(
        ((pl.col("close_end") - pl.col("close")) / pl.col("close")).alias("end_return")
    )

    print("\n[STEP 2] Computing family bar positions and 15m mapping...")
    df_1m_shift = df_1m_shift.with_columns(
        [
            pl.col("family_bar_pos").cast(pl.Int32).alias("bar_pos_1m"),
            pl.col("timestamp").dt.truncate("15m").alias("ts_15m"),
        ]
    )
    df_15m_shift = df_15m_shift.with_columns(
        pl.col("family_bar_pos").cast(pl.Int32).alias("bar_pos_15m")
    )

    df_1m_shift = (
        df_1m_shift.with_columns(
            [
                pl.col("close").rolling_mean(window_size=BB_PERIOD).alias("bb_middle"),
                pl.col("close").rolling_std(window_size=BB_PERIOD).alias("bb_std"),
            ]
        )
        .with_columns(
            [
                (pl.col("bb_middle") + BB_STD * pl.col("bb_std")).alias("bb_upper"),
                (pl.col("bb_middle") - BB_STD * pl.col("bb_std")).alias("bb_lower"),
            ]
        )
        .with_columns(
            (
                (pl.col("close") - pl.col("bb_lower"))
                / (pl.col("bb_upper") - pl.col("bb_lower"))
                * 100
            ).alias("bb_position_pct")
        )
    )
    df_1m_shift = df_1m_shift.with_columns((pl.col("bar_pos_1m") // 120).alias("segment_2h"))

    print("\n[STEP 3] Computing shift hybrid distance metrics (1m entry, shifted 15m future)...")
    df_shift_15m_pos = df_15m_shift.select(
        [
            pl.col("timestamp").alias("ts_15m"),
            pl.col("batch_id").alias("batch_id_check"),
            "bar_pos_15m",
        ]
    )
    df_1m_shift = df_1m_shift.join(df_shift_15m_pos, on="ts_15m", how="left")

    close_1m_shift_np = df_1m_shift["close"].to_numpy().astype("float64")
    batch_id_1m_shift_np = df_1m_shift["batch_id"].to_numpy().astype("int64")
    bar_pos_15m_for_1m_shift_np = (
        df_1m_shift["bar_pos_15m"].fill_null(0).to_numpy().astype("int32")
    )
    high_15m_shift_np = df_15m_shift["high"].to_numpy().astype("float64")
    low_15m_shift_np = df_15m_shift["low"].to_numpy().astype("float64")
    batch_id_15m_shift_np = df_15m_shift["batch_id"].to_numpy().astype("int64")
    bar_pos_15m_shift_np = df_15m_shift["bar_pos_15m"].to_numpy().astype("int32")

    d_avg_high, d_avg_low, d_top5_high, d_bot5_low, remaining = (
        compute_hybrid_distance_metrics(
            close_1m_shift_np,
            batch_id_1m_shift_np,
            bar_pos_15m_for_1m_shift_np,
            high_15m_shift_np,
            low_15m_shift_np,
            batch_id_15m_shift_np,
            bar_pos_15m_shift_np,
            MIN_REMAINING_BARS_15M_SHIFT,
            OUTLIER_PERCENTILE,
        )
    )

    df_1m_shift = df_1m_shift.with_columns(
        [
            pl.Series("dist_avg_high", d_avg_high),
            pl.Series("dist_avg_low", d_avg_low),
            pl.Series("dist_top5_high", d_top5_high),
            pl.Series("dist_bot5_low", d_bot5_low),
            pl.Series("remaining_bars", remaining),
        ]
    )

    entry_bar_limit_1m_shift = int(BARS_PER_8H_1M_SHIFT * (ENTRY_WINDOW_HOURS_1M_SHIFT / 8.0))
    valid_count_shift = len(df_1m_shift.filter(pl.col("dist_avg_high").is_not_nan()))
    expected_valid_shift = min(
        BARS_PER_8H_1M_SHIFT - MIN_REMAINING_BARS_1M_SHIFT,
        entry_bar_limit_1m_shift,
    )
    print(
        f"  Valid shift4h 1m bars (with metrics): {valid_count_shift:,} "
        f"({100 * valid_count_shift / max(1, len(df_1m_shift)):.1f}%)"
    )
    print(
        f"  Expected valid shift4h label rows per full 1m batch: {expected_valid_shift} "
        f"(first {ENTRY_WINDOW_HOURS_1M_SHIFT}h only)"
    )

    print("\n[STEP 4] Computing shift4h 4-class + breakfree labels...")
    df_labeled_1m_shift = compute_4class_labels(df_1m_shift, BREAKOUT_THRESHOLD, RISK_RATIO)
    df_labeled_1m_shift = df_labeled_1m_shift.with_columns(
        [
            pl.when(pl.col("target_4class") < 0)
            .then(pl.lit(-1))
            .when(
                pl.col("target_4class").is_in([2, 3])
                & (pl.col("end_return") >= BREAKFREE_THRESHOLD_1M_SHIFT)
            )
            .then(pl.lit(0))
            .when(
                pl.col("target_4class").is_in([0, 1])
                & (pl.col("end_return") <= -BREAKFREE_THRESHOLD_1M_SHIFT)
            )
            .then(pl.lit(1))
            .otherwise(pl.lit(2))
            .alias("target_breakfree")
        ]
    )
    df_labeled_1m_shift = df_labeled_1m_shift.with_columns(
        [
            pl.when(pl.col("bar_pos_1m") < entry_bar_limit_1m_shift)
            .then(pl.col("target_4class"))
            .otherwise(pl.lit(-1))
            .alias("target_4class"),
            pl.when(pl.col("bar_pos_1m") < entry_bar_limit_1m_shift)
            .then(pl.col("target_breakfree"))
            .otherwise(pl.lit(-1))
            .alias("target_breakfree"),
        ]
    )
    df_labeled_1m_shift = df_labeled_1m_shift.with_columns(
        pl.col("target_4class")
        .replace_strict({i: name for i, name in CLASS_NAMES.items()}, default="INVALID")
        .alias("target_name")
    )

    print("\n[STEP 5] Saving per-batch shift4h 1m labels...")
    available_cols_1m_shift = [c for c in shift_output_cols_1m if c in df_labeled_1m_shift.columns]
    df_output_1m_shift = df_labeled_1m_shift.filter(
        pl.col("batch_id").is_in(target_batches_1m_shift)
    ).select(available_cols_1m_shift)

    batch_ids_1m_shift = df_output_1m_shift["batch_id"].unique().sort().to_list()
    for bid in batch_ids_1m_shift:
        df_output_1m_shift.filter(pl.col("batch_id") == bid).write_parquet(
            shift_1m_label_dir / f"batch_{bid:04d}.parquet"
        )

    valid_labels_1m_shift = len(df_output_1m_shift.filter(pl.col("target_4class") >= 0))
    print(f"  ✓ Saved {len(batch_ids_1m_shift):,} shift4h batch files to {shift_1m_label_dir}")
    print(f"  ✓ Total rows: {len(df_output_1m_shift):,}")
    print(f"  ✓ Valid shift4h 4-class labels: {valid_labels_1m_shift:,}")
    labels_meta_1m_shift = artifact_meta_payload(
        artifact_version=ARTIFACT_STAGE_VERSIONS["labels"],
        family="C",
        timeframe="1m",
        source_fingerprint=shift_1m_label_fingerprint,
        schema_columns=available_cols_1m_shift,
        rebuild_mode=shift_1m_rebuild_mode,
        extra={
            "rebuild_reasons": shift_1m_reasons,
            "updated_batches": [int(b) for b in batch_ids_1m_shift],
            "updated_batches_count": int(len(batch_ids_1m_shift)),
            "entry_window_hours": ENTRY_WINDOW_HOURS_1M_SHIFT,
            "breakfree_threshold": BREAKFREE_THRESHOLD_1M_SHIFT,
            "rows": int(len(df_output_1m_shift)),
            "valid_labels": int(valid_labels_1m_shift),
        },
    )
    with open(shift_1m_label_meta_path, "w") as f:
        json.dump(labels_meta_1m_shift, f, indent=2)
    print("  ✓ Saved shift4h _labels_meta.json")

    print("\n" + "=" * 70)
    print("SHIFT4H HYBRID 1m LABELING COMPLETE")
    print("=" * 70)
    print("Approach: 1m shifted-family entry close + shifted-family 15m remaining bars")
    print(f"Output: {shift_1m_label_dir}/batch_*.parquet")

    del df_1m_shift, df_15m_shift, df_labeled_1m_shift, df_output_1m_shift
    gc.collect()

# %%
# =============================================================================
# CELL 10: HTF FEATURE OPTIMIZATION (Rolling Rank-Winsorize)
# =============================================================================
# CORRECT winsorize-rank implementation:
#   1. Rolling rank: u_t = percentile of x_t vs past L values (t-L..t-1)
#   2. Clip ranks: u_t' = clip(u_t, p_min, p_max)
#   3. Post-transform: uniform [-1,1] or signed
#
# KEY DESIGN:
#   - Rolling window (bounded memory O(L) per feature)
#   - State carries across batches (no reset at boundaries)
#   - Walk-forward validation on EARLY data only (no look-ahead)
#   - Grid search: window L, clip bounds, post-transform
#
# CAUSAL GUARANTEE:
#   At row t, rank uses ONLY t-L..t-1. No future leakage.
#
# Output: data/htf_optimized/{tf}/{target}/batch_XXXX.parquet
# =============================================================================

import importlib
import json
import sys
from pathlib import Path

# Ensure project root is in path
PROJECT_ROOT = resolve_project_root() if "resolve_project_root" in globals() else Path("..").resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Force reload to pick up changes
import scripts.feature_engineering.optimize_htf_features as opt_module

importlib.reload(opt_module)
from scripts.feature_engineering.optimize_htf_features import (
    HTFOptimizationConfig,
    optimize_htf_features,
)

# Configuration - Walk-forward on EARLY data
# For 4-class: optimize directly against target_4class
import pandas as pd

optimization_runs = [
    ("B", family_scope("B"), list(globals().get("HTF_TIMEFRAMES", ["1m", "15m"]))),
    (
        "C",
        family_scope("C"),
        list(
            globals().get(
                "SHIFT4H_TIMEFRAMES",
                list(globals().get("HTF_TIMEFRAMES", ["1m", "15m"])),
            )
        ),
    ),
]

all_opt_results: list[pd.DataFrame] = []
for family, scope, family_timeframes in optimization_runs:
    active_timeframes = [
        tf
        for tf in family_timeframes
        if (scope["features_dir"] / tf).exists() and (scope["labels_dir"] / tf).exists()
    ]
    if not active_timeframes:
        print(f"\nSkipping family {family}: no features/labels directories available")
        continue

    print("\n" + "=" * 70)
    print(f"OPTIMIZATION FAMILY {family}")
    print("=" * 70)

    config_kwargs = {}
    if family == "C":
        config_kwargs = {
            "htf_features_dir_override": scope["features_dir"],
            "htf_labels_dir_override": scope["labels_dir"],
            "htf_optimized_dir_override": scope["optimized_dir"],
        }

    config = HTFOptimizationConfig(
        project_root=PROJECT_ROOT,
        timeframes=active_timeframes,
        targets=["target_4class"],
        n_early_batches=200,
        n_val_folds=3,
        stability_lambda=0.5,
        recompute=False,
        incremental_update=True,
        max_state_snapshots=32,
        save_results=True,
        **config_kwargs,
    )

    family_results = optimize_htf_features(config, verbose=True)
    if len(family_results) > 0:
        if not isinstance(family_results, pd.DataFrame):
            family_results = pd.DataFrame(family_results)
        family_results.insert(0, "family", family)
        all_opt_results.append(family_results)

if all_opt_results:
    optimization_results = pd.concat(all_opt_results, ignore_index=True)
    print("\n" + "=" * 70)
    print("OPTIMIZATION RESULTS")
    print("=" * 70)
    print(optimization_results.to_string(index=False))
else:
    optimization_results = pd.DataFrame()
    print("\nNo optimization results produced.")

# %%
# =============================================================================
# CELL 11: L1 HELPER FEATURES (CORRECTED - RAW DATA INPUT)
# =============================================================================
# ISSUE FIXED: Previous version fed rank-winsorized data (0-1) to helpers.
# Helpers expect RAW returns and prices for proper estimation.
#
# SOLUTION:
# 1. Load from htf_features/ (has raw OHLCV: close ~40000-70000)
# 2. Compute raw returns from raw close
# 3. Build feature matrix with raw returns at column 0 (what helpers expect)
# 4. Run walk-forward helper generation
# 5. Join results with htf_optimized/ (rank-winsorized features)
#
# OUTPUT:
#   - data/htf_with_helpers/{tf}/{target}/batch_XXXX.parquet
#   - optional: data/htf_with_helpers/{tf}/{target}/combined.parquet
# =============================================================================

import json
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl

# Ensure project root is in path
PROJECT_ROOT = resolve_project_root() if "resolve_project_root" in globals() else Path("..").resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Import helper infrastructure (SAME as main_wf)
from scripts.target_models.helpers import create_helper_ensemble

# =============================================================================
# HELPER: PREPARE RAW DATA FOR HELPERS
# =============================================================================


def prepare_raw_features_for_helpers(df: pl.DataFrame) -> tuple[np.ndarray, list[str]]:
    """
    Prepare feature matrix with RAW returns/volatility that helpers expect.

    Helpers use column indices:
    - return_col_idx=0: raw log returns
    - vol_col_idx=1: raw volatility (rolling std of returns)
    - price_col_idx: close price (for OU, Kalman)

    Returns:
        (feature_matrix, column_names)
    """
    # Get raw close prices
    close = df["close"].to_numpy().astype(np.float64)

    # Compute raw log returns
    returns = np.zeros_like(close)
    returns[1:] = np.diff(np.log(np.maximum(close, 1e-10)))

    # Compute rolling volatility (20-period std of returns)
    volatility = pd.Series(returns).rolling(20, min_periods=1).std().fillna(0.01).values

    # Build feature matrix: [returns, volatility, close, other raw columns...]
    # This puts returns at index 0, volatility at index 1
    feature_cols = ["raw_returns", "raw_volatility", "close"]
    features = np.column_stack([returns, volatility, close])

    # Add other raw numeric columns that might be useful
    for col in ["open", "high", "low", "volume"]:
        if col in df.columns:
            vals = df[col].to_numpy().astype(np.float64)
            features = np.column_stack([features, vals])
            feature_cols.append(col)

    return features, feature_cols


# =============================================================================
# WALK-FORWARD HELPER GENERATION (NO LOOK-AHEAD BIAS)
# =============================================================================


def compute_helpers_walk_forward_raw(
    raw_df: pl.DataFrame,
    target: str,
    horizon: int = 1,
    warmup_rows: int = 5000,
    refit_every: int = 1000,
    helpers: list[str] | None = None,
    start_row: int | None = None,
    verbose: bool = True,
) -> pd.DataFrame:
    """
    Generate L1 helper features using walk-forward approach with RAW data.

    CRITICAL: At each row t, we only use data from rows [0, t-1] to fit.
    Uses RAW returns/prices, not rank-winsorized data.
    """
    if helpers is None:
        helpers = ["ou", "garch", "cusum", "kalman", "egarch"]

    # Prepare raw feature matrix
    X, feature_cols = prepare_raw_features_for_helpers(raw_df)
    n_rows = len(X)

    if verbose:
        print(f"  Raw data prepared: {n_rows:,} rows, {len(feature_cols)} columns")
        print(f"  Returns range: {np.nanmin(X[:, 0]):.6f} to {np.nanmax(X[:, 0]):.6f}")
        print(f"  Close range: {np.nanmin(X[:, 2]):.2f} to {np.nanmax(X[:, 2]):.2f}")
        print(f"  Walk-forward: warmup={warmup_rows}, refit_every={refit_every}")

    # Convert to DataFrame for helper API
    X_df = pd.DataFrame(X, columns=feature_cols)

    # Incremental mode: only compute rows >= start_row
    if start_row is None:
        start_row = warmup_rows
    start_row = int(max(start_row, warmup_rows))
    if start_row >= n_rows:
        return pd.DataFrame({"row_idx": []})

    helper_output_list = []
    t0 = time.time()
    chunk_size = refit_every
    first_chunk_start = (
        warmup_rows + ((start_row - warmup_rows) // chunk_size) * chunk_size
    )
    processed_chunks = 0
    total_rows_to_compute = n_rows - start_row

    if verbose:
        print(
            f"  Incremental helper compute window: start_row={start_row:,}, "
            f"rows_to_compute={total_rows_to_compute:,}, first_chunk={first_chunk_start:,}"
        )

    for chunk_start in range(first_chunk_start, n_rows, chunk_size):
        chunk_end = min(chunk_start + chunk_size, n_rows)

        # 1. FIT on all data up to chunk_start (past only)
        X_train = X_df.iloc[:chunk_start]

        # Create and fit fresh ensemble
        ensemble = create_helper_ensemble(
            target=target,
            horizon=horizon,
            random_state=42 + chunk_start,
            helpers=helpers,
            enable_boosting=False,
        )
        ensemble.fit(X_train)

        # 2. TRANSFORM the current chunk
        pred_start = max(chunk_start, start_row)
        if pred_start >= chunk_end:
            continue

        X_chunk = X_df.iloc[pred_start:chunk_end]
        chunk_features = ensemble.transform(X_chunk)
        chunk_df = chunk_features.features.reset_index(drop=True).copy()
        chunk_df.insert(
            0,
            "row_idx",
            np.arange(pred_start, chunk_end, dtype=np.int64),
        )
        helper_output_list.append(chunk_df)
        processed_chunks += 1

        if verbose and (
            processed_chunks == 1 or processed_chunks % 20 == 0 or chunk_end == n_rows
        ):
            elapsed = time.time() - t0
            progress = (chunk_end - start_row) / max(1, (n_rows - start_row))
            eta = elapsed / max(progress, 0.01) * (1 - progress)
            print(
                f"    chunk {processed_chunks}: {chunk_end:,}/{n_rows:,} "
                f"({progress * 100:.1f}% incremental), "
                f"{elapsed / 60:.1f}m elapsed, ~{eta / 60:.1f}m remaining"
            )

    if not helper_output_list:
        return pd.DataFrame({"row_idx": []})

    helper_df_partial = pd.concat(helper_output_list, axis=0, ignore_index=True)

    if verbose:
        print(
            f"  Generated {len(helper_df_partial.columns) - 1} helper features "
            f"for {len(helper_df_partial):,} rows in {time.time() - t0:.1f}s"
        )

    return helper_df_partial


# =============================================================================
# PROCESS ALL FAMILIES / TIMEFRAMES / TARGETS
# =============================================================================


def _helper_family_runs() -> list[tuple[str, dict, list[str]]]:
    return [
        ("B", family_scope("B"), list(globals().get("HTF_TIMEFRAMES", ["1m", "15m"]))),
        (
            "C",
            family_scope("C"),
            list(
                globals().get(
                    "SHIFT4H_TIMEFRAMES",
                    list(globals().get("HTF_TIMEFRAMES", ["1m", "15m"])),
                )
            ),
        ),
    ]


def _helper_cols_from_batch_dir(helper_dir: Path) -> list[str]:
    files = sorted(helper_dir.glob("batch_*.parquet"))
    if not files:
        return []
    schema = pl.scan_parquet(
        str(helper_dir / "batch_*.parquet"),
        extra_columns="ignore",
        missing_columns="insert",
    ).collect_schema().names()
    return [c for c in schema if c.startswith("H_")]


def _load_helper_source_batches(
    helper_dir: Path, source_batch_ids: list[int], helper_cols: list[str]
) -> pl.DataFrame | None:
    parts = []
    for source_batch_id in sorted({int(bid) for bid in source_batch_ids}):
        batch_path = helper_dir / f"batch_{source_batch_id:04d}.parquet"
        if not batch_path.exists():
            return None
        parts.append(pl.read_parquet(batch_path, columns=["timestamp"] + helper_cols))
    if not parts:
        return None
    return (
        pl.concat(parts, how="diagonal_relaxed")
        .sort("timestamp")
        .unique(subset=["timestamp"], keep="last")
    )


print("=" * 70)
print("HTF L1 HELPER FEATURES (CORRECTED - RAW DATA INPUT)")
print("=" * 70)

TARGETS = ["target_4class"]
INCREMENTAL_SPLIT_BATCHES = True
HELPERS = ["ou", "garch", "cusum", "kalman", "egarch"]
INCREMENTAL_HELPERS_SKIP_UNCHANGED = True
WRITE_HELPERS_COMBINED = False
HELPER_OVERLAP_BATCHES_BY_TF = {"1m": 2, "5m": 2, "15m": 2}

results = []

for family, scope, family_timeframes in _helper_family_runs():
    print("\n" + "=" * 70)
    print(f"FAMILY {family} HELPER MATERIALIZATION")
    print("=" * 70)

    for tf in family_timeframes:
        for target in TARGETS:
            print(f"\n{'─' * 50}")
            print(f"{family} / {tf} / {target}")
            print("─" * 50)

            output_dir = scope["helpers_dir"] / tf / target
            output_dir.mkdir(parents=True, exist_ok=True)
            combined_path = output_dir / "combined.parquet"
            helpers_meta_path = output_dir / "_helpers_meta.json"

            raw_dir = scope["features_dir"] / tf
            if not raw_dir.exists():
                print(f"  ⚠️ features directory not found: {raw_dir}")
                continue

            raw_files = sorted(raw_dir.glob("batch_*.parquet"))
            if not raw_files:
                print("  ⚠️ No batch files in features directory")
                continue

            opt_dir = scope["optimized_dir"] / tf / target
            if not opt_dir.exists():
                print(f"  ⚠️ optimized directory not found: {opt_dir}")
                continue
            opt_files = sorted(opt_dir.glob("batch_*.parquet"))
            if not opt_files:
                print(f"  ⚠️ No optimized batch files in {opt_dir}")
                continue

            helper_source_fingerprint = {
                "raw_batches": fingerprint_batch_dir(raw_dir),
                "optimized_batches": fingerprint_batch_dir(opt_dir),
                "optimized_meta": fingerprint_paths(
                    [scope["optimized_dir"] / tf / f"optimized_{target}_meta.json"]
                ),
            }
            helper_schema_columns = schema_columns_for_batch_dir(output_dir)
            if not helper_schema_columns:
                helper_schema_columns = (load_json_safe(helpers_meta_path) or {}).get(
                    "schema_columns", []
                )
            helper_rebuild_reasons: list[str] = []
            helper_rebuild_mode = "incremental_tail"
            if family == "C":
                helper_rebuild_reasons, helper_rebuild_mode = prepare_stage_rebuild(
                    stage_name=f"Shift4h helpers {tf}/{target}",
                    meta_path=helpers_meta_path,
                    artifact_version=ARTIFACT_STAGE_VERSIONS["shift4h_helpers"],
                    family=family,
                    timeframe=tf,
                    source_fingerprint=helper_source_fingerprint,
                    schema_columns=helper_schema_columns,
                    output_targets=[output_dir],
                    inspect_batch_dir=output_dir,
                    required_batch_columns=set(
                        ["timestamp", *family_metadata_cols(include_timestamp=False)]
                    ),
                    full_rebuild_reasons={
                        "missing_meta",
                        "artifact_version",
                        "family",
                        "timeframe",
                        "schema_columns",
                        "legacy_schema",
                    },
                )

            raw_by_id = {
                int(path.stem.split("_")[1]): path
                for path in raw_files
                if path.stem.startswith("batch_")
            }
            opt_by_id = {
                int(path.stem.split("_")[1]): path
                for path in opt_files
                if path.stem.startswith("batch_")
            }
            helper_files = sorted(output_dir.glob("batch_*.parquet"))
            helper_by_id = {
                int(path.stem.split("_")[1]): path
                for path in helper_files
                if path.stem.startswith("batch_")
            }

            common_batch_ids = sorted(set(raw_by_id) & set(opt_by_id))
            if not common_batch_ids:
                print("  ⚠️ No overlapping batch IDs between features and optimized")
                continue

            orphan_helper_ids = sorted(set(helper_by_id) - set(common_batch_ids))
            if orphan_helper_ids:
                print(f"  Removing {len(orphan_helper_ids)} orphan helper batches")
                for bid in orphan_helper_ids:
                    helper_by_id[bid].unlink(missing_ok=True)
                    helper_by_id.pop(bid, None)

            raw_mtime = {bid: int(path.stat().st_mtime_ns) for bid, path in raw_by_id.items()}
            opt_mtime = {bid: int(path.stat().st_mtime_ns) for bid, path in opt_by_id.items()}
            helper_mtime = {
                bid: int(path.stat().st_mtime_ns) for bid, path in helper_by_id.items()
            }

            affected_batch_ids = []
            for bid in common_batch_ids:
                helper_stamp = helper_mtime.get(bid)
                if helper_stamp is None or helper_stamp < max(raw_mtime[bid], opt_mtime[bid]):
                    affected_batch_ids.append(bid)
            affected_batch_set = set(affected_batch_ids)

            raw_sig = {
                "count": int(len(raw_by_id)),
                "max_batch": int(max(raw_by_id)),
                "max_mtime_ns": int(max(raw_mtime.values())),
            }
            opt_sig = {
                "count": int(len(opt_by_id)),
                "max_batch": int(max(opt_by_id)),
                "max_mtime_ns": int(max(opt_mtime.values())),
            }

            if INCREMENTAL_HELPERS_SKIP_UNCHANGED and not affected_batch_ids:
                print("  ✓ Helper outputs up to date (no affected batches), skipping")
                results.append(
                    {
                        "family": family,
                        "tf": tf,
                        "target": target,
                        "rows": 0,
                        "helpers": 0,
                        "warmup": 0,
                        "time": 0.0,
                        "skipped": True,
                    }
                )
                continue

            first_affected_batch = min(affected_batch_ids)
            overlap_batches = HELPER_OVERLAP_BATCHES_BY_TF.get(tf, 2)
            write_start_batch = max(common_batch_ids[0], first_affected_batch - overlap_batches)
            batches_to_write = [bid for bid in common_batch_ids if bid >= write_start_batch]
            print(
                f"  Incremental helper update: affected={len(affected_batch_ids)} "
                f"(first={first_affected_batch}), write_start={write_start_batch}, "
                f"write_batches={len(batches_to_write)}"
            )

            reuse_helper_dir = output_dir
            if family == "C":
                base_helper_dir = family_scope("B")["helpers_dir"] / tf / target
                if base_helper_dir.exists() and list(base_helper_dir.glob("batch_*.parquet")):
                    reuse_helper_dir = base_helper_dir
            reuse_helper_cols = _helper_cols_from_batch_dir(reuse_helper_dir)
            if reuse_helper_cols:
                print(f"  Attempting helper reuse from {reuse_helper_dir}")
                t0 = time.time()
                rows_joined = 0
                saved_batches = 0
                skipped_batches = 0
                reuse_failed = False
                reuse_failure_detail = ""

                for i, batch_id in enumerate(batches_to_write, 1):
                    opt_file = opt_by_id.get(batch_id)
                    if opt_file is None:
                        continue

                    opt_batch = pl.read_parquet(opt_file).with_columns(
                        pl.lit(batch_id).alias("batch_id")
                    )
                    if family == "B":
                        source_batch_ids = [batch_id]
                    else:
                        source_batch_ids = opt_batch["source_base_batch_id"].drop_nulls().unique().to_list()

                    helper_source = _load_helper_source_batches(
                        reuse_helper_dir, source_batch_ids, reuse_helper_cols
                    )
                    if helper_source is None:
                        reuse_failed = True
                        reuse_failure_detail = (
                            f"missing helper source batch for {family}/{tf}/{target} batch {batch_id}"
                        )
                        break

                    missing_helper_ts = int(
                        opt_batch.join(
                            helper_source.select(["timestamp"]),
                            on="timestamp",
                            how="anti",
                        )
                        .select(pl.len())
                        .item()
                    )
                    if missing_helper_ts > 0:
                        reuse_failed = True
                        reuse_failure_detail = (
                            f"helper reuse missing {missing_helper_ts} timestamps for "
                            f"{family}/{tf}/{target} batch {batch_id}"
                        )
                        break

                    enriched_batch = opt_batch.join(helper_source, on="timestamp", how="left")

                    batch_path = output_dir / f"batch_{batch_id:04d}.parquet"
                    force_rewrite = batch_id in affected_batch_set
                    if INCREMENTAL_SPLIT_BATCHES and batch_path.exists() and not force_rewrite:
                        existing = pl.read_parquet(batch_path, columns=["timestamp"])
                        same_rows = len(existing) == len(enriched_batch)
                        same_last_ts = (
                            existing["timestamp"].max() == enriched_batch["timestamp"].max()
                        )
                        if same_rows and same_last_ts:
                            skipped_batches += 1
                            rows_joined += len(enriched_batch)
                            if i % 500 == 0:
                                print(f"    processed {i}/{len(batches_to_write)} batches...")
                            continue

                    enriched_batch.write_parquet(batch_path, compression="zstd")
                    saved_batches += 1
                    rows_joined += len(enriched_batch)
                    if i % 500 == 0:
                        print(f"    processed {i}/{len(batches_to_write)} batches...")

                if not reuse_failed:
                    join_elapsed = time.time() - t0
                    print(
                        f"  Reused helper features for {rows_joined:,} rows in {join_elapsed:.1f}s "
                        f"(saved={saved_batches}, skipped={skipped_batches})"
                    )
                    if WRITE_HELPERS_COMBINED:
                        print("  Building optional combined.parquet from per-batch files...")
                        pl.concat(
                            [
                                pl.read_parquet(batch_file)
                                for batch_file in sorted(output_dir.glob("batch_*.parquet"))
                            ]
                        ).sort("timestamp").write_parquet(combined_path)
                        print(f"  ✓ Saved {combined_path.name}")

                    helpers_meta = {
                        "updated_at": datetime.now().isoformat(),
                        "family": family,
                        "timeframe": tf,
                        "target": target,
                        "artifact_version": ARTIFACT_STAGE_VERSIONS["shift4h_helpers"]
                        if family == "C"
                        else None,
                        "source_fingerprint": helper_source_fingerprint,
                        "schema_columns": schema_columns_for_batch_dir(output_dir),
                        "rebuild_mode": helper_rebuild_mode,
                        "run_mode": "reuse_existing_helpers",
                        "helper_source_dir": str(reuse_helper_dir),
                        "rebuild_reasons": helper_rebuild_reasons,
                        "first_affected_batch": int(first_affected_batch),
                        "write_start_batch": int(write_start_batch),
                        "affected_batches_count": int(len(affected_batch_ids)),
                        "write_batches_count": int(len(batches_to_write)),
                        "rows": int(rows_joined),
                        "helper_cols": int(len(reuse_helper_cols)),
                        "warmup": 0,
                        "refit_every": 0,
                        "raw_sig": raw_sig,
                        "opt_sig": opt_sig,
                        "saved_batches": int(saved_batches),
                        "skipped_batches": int(skipped_batches),
                        "write_helpers_combined": bool(WRITE_HELPERS_COMBINED),
                    }
                    with open(helpers_meta_path, "w") as f:
                        json.dump(helpers_meta, f, indent=2)

                    results.append(
                        {
                            "family": family,
                            "tf": tf,
                            "target": target,
                            "rows": rows_joined,
                            "helpers": len(reuse_helper_cols),
                            "warmup": 0,
                            "time": 0.0,
                            "skipped": False,
                        }
                    )
                    print(
                        f"  ✓ Saved batch helper files ({len(reuse_helper_cols)} helper features via reuse)"
                    )
                    print(f"  ✓ Saved {helpers_meta_path.name}")
                    continue

                print(f"  Helper reuse unavailable, falling back to walk-forward compute: {reuse_failure_detail}")

            print(f"  Loading {len(raw_files)} raw batches...", end=" ", flush=True)
            t0 = time.time()
            raw_combined = (
                pl.scan_parquet(
                    str(raw_dir / "batch_*.parquet"),
                    extra_columns="ignore",
                    missing_columns="insert",
                )
                .sort("timestamp")
                .collect()
            )
            print(f"{len(raw_combined):,} rows in {time.time() - t0:.1f}s")

            if tf == "1m":
                warmup, refit = 20000, 10000
            elif tf == "5m":
                warmup, refit = 10000, 5000
            elif tf == "15m":
                warmup, refit = 5000, 2500
            else:
                warmup, refit = 2000, 1000

            batch_np = raw_combined["batch_id"].to_numpy()
            start_candidates = np.where(batch_np >= write_start_batch)[0]
            if len(start_candidates) == 0:
                print("  ⚠️ Could not find write_start_batch in combined rows, skipping")
                continue
            start_row = int(start_candidates[0])

            t0 = time.time()
            helper_df_partial = compute_helpers_walk_forward_raw(
                raw_df=raw_combined,
                target=target.replace("target_", ""),
                horizon=1,
                warmup_rows=warmup,
                refit_every=refit,
                helpers=HELPERS,
                start_row=start_row,
                verbose=True,
            )
            helper_time = time.time() - t0

            if helper_df_partial.empty:
                print("  ⚠️ Incremental helper output empty, skipping")
                continue

            helper_pl = pl.from_pandas(helper_df_partial).with_columns(
                pl.col("row_idx").cast(pl.Int64)
            )
            timestamp_lookup = (
                raw_combined.select(["timestamp"])
                .with_row_index("row_idx")
                .with_columns(pl.col("row_idx").cast(pl.Int64))
            )
            helper_cols = [c for c in helper_pl.columns if c.startswith("H_")]
            helper_lookup = (
                helper_pl.join(timestamp_lookup, on="row_idx", how="left")
                .drop("row_idx")
                .select(["timestamp"] + helper_cols)
                .sort("timestamp")
                .unique(subset=["timestamp"], keep="last")
            )

            print(
                f"  Joining helper features into {len(batches_to_write)} optimized batches...",
                flush=True,
            )
            t0 = time.time()
            rows_joined = 0
            saved_batches = 0
            skipped_batches = 0

            for i, batch_id in enumerate(batches_to_write, 1):
                opt_file = opt_by_id.get(batch_id)
                if opt_file is None:
                    continue
                opt_batch = pl.read_parquet(opt_file).with_columns(
                    pl.lit(batch_id).alias("batch_id")
                )
                enriched_batch = opt_batch.join(helper_lookup, on="timestamp", how="left")

                batch_path = output_dir / f"batch_{batch_id:04d}.parquet"
                force_rewrite = batch_id in affected_batch_set
                if INCREMENTAL_SPLIT_BATCHES and batch_path.exists() and not force_rewrite:
                    existing = pl.read_parquet(batch_path, columns=["timestamp"])
                    same_rows = len(existing) == len(enriched_batch)
                    same_last_ts = (
                        existing["timestamp"].max() == enriched_batch["timestamp"].max()
                    )
                    if same_rows and same_last_ts:
                        skipped_batches += 1
                        rows_joined += len(enriched_batch)
                        if i % 500 == 0:
                            print(f"    processed {i}/{len(batches_to_write)} batches...")
                        continue

                enriched_batch.write_parquet(batch_path, compression="zstd")
                saved_batches += 1
                rows_joined += len(enriched_batch)

                if i % 500 == 0:
                    print(f"    processed {i}/{len(batches_to_write)} batches...")

            join_elapsed = time.time() - t0
            print(
                f"  Joined and saved {rows_joined:,} rows in {join_elapsed:.1f}s "
                f"(saved={saved_batches}, skipped={skipped_batches})"
            )

            if WRITE_HELPERS_COMBINED:
                print("  Building optional combined.parquet from per-batch files...")
                pl.concat(
                    [
                        pl.read_parquet(batch_file)
                        for batch_file in sorted(output_dir.glob("batch_*.parquet"))
                    ]
                ).sort("timestamp").write_parquet(combined_path)
                print(f"  ✓ Saved {combined_path.name}")

            n_helper = len(helper_cols)
            helpers_meta = {
                "updated_at": datetime.now().isoformat(),
                "family": family,
                "timeframe": tf,
                "target": target,
                "artifact_version": ARTIFACT_STAGE_VERSIONS["shift4h_helpers"]
                if family == "C"
                else None,
                "source_fingerprint": helper_source_fingerprint,
                "schema_columns": schema_columns_for_batch_dir(output_dir),
                "rebuild_mode": helper_rebuild_mode,
                "run_mode": "incremental_tail",
                "rebuild_reasons": helper_rebuild_reasons,
                "first_affected_batch": int(first_affected_batch),
                "write_start_batch": int(write_start_batch),
                "affected_batches_count": int(len(affected_batch_ids)),
                "write_batches_count": int(len(batches_to_write)),
                "start_row": int(start_row),
                "rows": int(rows_joined),
                "helper_cols": int(n_helper),
                "warmup": int(warmup),
                "refit_every": int(refit),
                "raw_sig": raw_sig,
                "opt_sig": opt_sig,
                "saved_batches": int(saved_batches),
                "skipped_batches": int(skipped_batches),
                "write_helpers_combined": bool(WRITE_HELPERS_COMBINED),
            }
            with open(helpers_meta_path, "w") as f:
                json.dump(helpers_meta, f, indent=2)

            results.append(
                {
                    "family": family,
                    "tf": tf,
                    "target": target,
                    "rows": rows_joined,
                    "helpers": n_helper,
                    "warmup": warmup,
                    "time": helper_time,
                    "skipped": False,
                }
            )
            print(f"  ✓ Saved batch helper files ({n_helper} helper features)")
            print(f"  ✓ Saved {helpers_meta_path.name}")

print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)
print(pl.DataFrame(results) if results else pl.DataFrame({"family": [], "tf": [], "target": []}))

# %%
# =============================================================================
# CELL 12: SPLIT BACK TO 8H BATCHES
# =============================================================================
# In low-RAM mode (WRITE_HELPERS_COMBINED=False), helper batch files are already
# written directly in Cell 11. This cell verifies/splits combined helper outputs
# for both base family B and shifted family C when combined.parquet is present.
# =============================================================================

import time
from pathlib import Path

import polars as pl

PROJECT_ROOT = resolve_project_root() if "resolve_project_root" in globals() else Path("..").resolve()


def _split_family_runs() -> list[tuple[str, dict, list[str]]]:
    return [
        ("B", family_scope("B"), list(globals().get("HTF_TIMEFRAMES", ["1m", "15m"]))),
        (
            "C",
            family_scope("C"),
            list(
                globals().get(
                    "SHIFT4H_TIMEFRAMES",
                    list(globals().get("HTF_TIMEFRAMES", ["1m", "15m"])),
                )
            ),
        ),
    ]


print("=" * 70)
print("SPLIT COMBINED DATA BACK TO 8H BATCHES")
print("=" * 70)

TARGETS = ["target_4class"]
BARS_PER_BATCH = {
    "1m": 480,
    "5m": 96,
    "15m": 32,
}

results = []

for family, scope, family_timeframes in _split_family_runs():
    print("\n" + "=" * 70)
    print(f"FAMILY {family} HELPER SPLIT")
    print("=" * 70)

    for tf in family_timeframes:
        for target in TARGETS:
            print(f"\n{'─' * 50}")
            print(f"{family} / {tf} / {target}")
            print("─" * 50)

            helper_dir = scope["helpers_dir"] / tf / target
            combined_path = helper_dir / "combined.parquet"
            if not combined_path.exists():
                existing_batches = sorted(helper_dir.glob("batch_*.parquet"))
                if existing_batches:
                    print(
                        "  ℹ️ combined.parquet not present (low-RAM mode); "
                        "batch files already available, skipping split."
                    )
                    results.append(
                        {
                            "family": family,
                            "tf": tf,
                            "target": target,
                            "batches": len(existing_batches),
                            "rows": 0,
                            "time_s": 0.0,
                            "mode": "already_split",
                        }
                    )
                    continue
                print(f"  ⚠️ Combined file not found: {combined_path}")
                continue

            t0 = time.time()
            df = pl.read_parquet(combined_path)
            print(f"  Loaded: {len(df):,} rows, {len(df.columns)} columns")

            if "batch_id" not in df.columns:
                print("  ⚠️ No batch_id column - cannot split by original batches")
                continue

            batch_ids = sorted(df["batch_id"].unique().drop_nulls().to_list())
            print(f"  Found {len(batch_ids)} unique batch_ids")

            expected_bars = BARS_PER_BATCH[tf]
            saved_count = 0
            skipped_count = 0
            total_rows = 0

            for batch_id in batch_ids:
                batch_df = df.filter(pl.col("batch_id") == batch_id)
                batch_path = helper_dir / f"batch_{batch_id:04d}.parquet"
                if INCREMENTAL_SPLIT_BATCHES and batch_path.exists():
                    existing = pl.read_parquet(batch_path, columns=["timestamp"])
                    same_rows = len(existing) == len(batch_df)
                    same_last_ts = (
                        existing["timestamp"].max() == batch_df["timestamp"].max()
                    )
                    if same_rows and same_last_ts:
                        skipped_count += 1
                        total_rows += len(batch_df)
                        continue
                if len(batch_df) > expected_bars:
                    print(
                        f"  ⚠️ Batch {batch_id}: {len(batch_df)} rows (expected <= {expected_bars})"
                    )
                batch_df.write_parquet(batch_path, compression="zstd")
                saved_count += 1
                total_rows += len(batch_df)

            elapsed = time.time() - t0
            results.append(
                {
                    "family": family,
                    "tf": tf,
                    "target": target,
                    "batches": saved_count,
                    "rows": total_rows,
                    "time_s": round(elapsed, 1),
                    "mode": "split_from_combined",
                }
            )

            print(
                f"  ✓ Saved {saved_count} batch files ({total_rows:,} rows) in {elapsed:.1f}s"
            )
            if INCREMENTAL_SPLIT_BATCHES:
                print(f"  ↪ Skipped unchanged batches: {skipped_count}")

print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)
print(pl.DataFrame(results) if results else pl.DataFrame({"family": [], "tf": [], "target": []}))

print("\n" + "=" * 70)
print("VERIFICATION")
print("=" * 70)

for family, scope, family_timeframes in _split_family_runs():
    for tf in family_timeframes:
        for target in TARGETS:
            batch_dir = scope["helpers_dir"] / tf / target
            batch_files = sorted(batch_dir.glob("batch_*.parquet"))
            if not batch_files:
                continue
            first = pl.read_parquet(batch_files[0])
            last = pl.read_parquet(batch_files[-1])
            first_ts = first["timestamp"].min()
            last_ts = last["timestamp"].max()
            h_cols = len([c for c in first.columns if c.startswith("H_")])

            print(f"\n{family}/{tf}/{target}:")
            print(f"  Batches: {len(batch_files)}")
            print(f"  Date range: {first_ts} to {last_ts}")
            print(f"  Helper features: {h_cols}")
            print(f"  Rows per batch: {len(first)} (first), {len(last)} (last)")
# %%
# =============================================================================
# CELL 13: END-TO-END PIPELINE VALIDATION SUITE
# =============================================================================
# Purpose:
#   Validate each stage output (combined/features/labels/optimized/helpers)
#   for both base family B and shifted family C and fail fast on structural
#   or family-lineage integrity problems.
# =============================================================================

from datetime import timedelta
from pathlib import Path

import polars as pl

PROJECT_ROOT = resolve_project_root() if "resolve_project_root" in globals() else Path("..").resolve()
DATA_DIR = PROJECT_ROOT / "data"

FAMILY_RUNS = [
    ("B", family_scope("B"), list(globals().get("HTF_TIMEFRAMES", ["1m", "15m"]))),
    (
        "C",
        family_scope("C"),
        list(
            globals().get(
                "SHIFT4H_TIMEFRAMES",
                list(globals().get("HTF_TIMEFRAMES", ["1m", "15m"])),
            )
        ),
    ),
]
TIMEFRAME_UNION = sorted({tf for _, _, tfs in FAMILY_RUNS for tf in tfs})
BARS_PER_BATCH = {"1m": 480, "5m": 96, "15m": 32}
ENTRY_VALID_ROWS = {"1m": 240, "5m": 48, "15m": 16}
FAMILY_META_REQUIRED = set(family_metadata_cols(include_timestamp=False))
DOWNSTREAM_META_REQUIRED = FAMILY_META_REQUIRED - {"bar_in_batch_norm"}


def _row(stage: str, family: str, tf: str, check: str, ok: bool, detail: str) -> dict:
    return {
        "stage": stage,
        "family": family,
        "tf": tf,
        "check": check,
        "ok": bool(ok),
        "detail": detail,
    }


def _scan_parquet_relaxed(path_or_glob: str | Path) -> pl.LazyFrame:
    return pl.scan_parquet(
        str(path_or_glob),
        extra_columns="ignore",
        missing_columns="insert",
    )


def _coerce_lazy_scan(scan_or_path: pl.LazyFrame | str | Path) -> pl.LazyFrame:
    if isinstance(scan_or_path, pl.LazyFrame):
        return scan_or_path
    return _scan_parquet_relaxed(scan_or_path)


def _label_metadata_lookup(tf: str, family: str) -> pl.LazyFrame:
    combined_path = family_scope(family)["backtest_dir"] / f"{tf}_HTF_combined.parquet"
    return pl.scan_parquet(combined_path).select(
        ["timestamp", "batch_id", *sorted(FAMILY_META_REQUIRED - {"batch_id"})]
    )


def _scan_label_batches_normalized(tf: str, family: str, label_dir: Path) -> pl.LazyFrame:
    """Normalize mixed old/new label batches to a canonical family metadata schema."""
    base_scan = _scan_parquet_relaxed(label_dir / "batch_*.parquet")
    base_cols = base_scan.collect_schema().names()
    preserved_cols = [c for c in base_cols if c not in FAMILY_META_REQUIRED - {"batch_id"}]
    return base_scan.select(preserved_cols).join(
        _label_metadata_lookup(tf, family),
        on=["timestamp", "batch_id"],
        how="left",
    )


def _scan_batch_counts(scan_or_path: pl.LazyFrame | str | Path) -> pl.DataFrame:
    return (
        _coerce_lazy_scan(scan_or_path)
        .group_by("batch_id")
        .agg(pl.len().alias("n"))
        .collect()
        .sort("batch_id")
    )


def _duplicate_ts_count(scan_or_path: pl.LazyFrame | str | Path) -> int:
    return int(
        _coerce_lazy_scan(scan_or_path)
        .group_by(["batch_id", "timestamp"])
        .agg(pl.len().alias("n"))
        .filter(pl.col("n") > 1)
        .select(pl.len())
        .collect()
        .item()
    )


def _null_count(scan_or_path: pl.LazyFrame | str | Path, col: str) -> int:
    return int(
        _coerce_lazy_scan(scan_or_path)
        .filter(pl.col(col).is_null())
        .select(pl.len())
        .collect()
        .item()
    )


def _expected_batch_ids(tf: str, scope: dict) -> list[int]:
    path = scope["backtest_dir"] / f"{tf}_HTF_combined.parquet"
    if not path.exists():
        return []
    return (
        pl.scan_parquet(path)
        .select("batch_id")
        .unique()
        .collect()
        .sort("batch_id")["batch_id"]
        .to_list()
    )


def _complete_batch_ids(tf: str, scope: dict) -> list[int]:
    path = scope["backtest_dir"] / f"{tf}_HTF_combined.parquet"
    if not path.exists():
        return []
    return (
        pl.scan_parquet(path)
        .group_by("batch_id")
        .agg(pl.len().alias("n"))
        .filter(pl.col("n") == BARS_PER_BATCH[tf])
        .select("batch_id")
        .collect()
        .sort("batch_id")["batch_id"]
        .to_list()
    )


def _period_expr(family: str) -> pl.Expr:
    ts = pl.col("timestamp").dt.replace_time_zone(None)
    if family == "B":
        return ts.dt.truncate("8h")
    return (ts - timedelta(hours=4)).dt.truncate("8h") + timedelta(hours=4)


def _validate_batch_dir_family(
    stage: str,
    family: str,
    tf: str,
    path: Path,
    expected_rows_per_batch: int | None,
    required_cols: set[str],
    expected_batch_ids: list[int] | None = None,
    allow_last_incomplete: bool = False,
    require_contiguous: bool = True,
    scan_override: pl.LazyFrame | None = None,
) -> tuple[list[dict], int]:
    rows = []
    files = sorted(path.glob("batch_*.parquet"))
    ids = [int(f.stem.split("_")[1]) for f in files]

    if not files:
        rows.append(_row(stage, family, tf, "files_exist", False, f"missing files in {path}"))
        return rows, 0

    rows.append(_row(stage, family, tf, "batch_file_count", True, f"found={len(files)}"))
    rows.append(
        _row(
            stage,
            family,
            tf,
            "batch_ids_contiguous",
            ids == list(range(ids[0], ids[-1] + 1)) if require_contiguous and ids else True,
            f"min={ids[0] if ids else None}, max={ids[-1] if ids else None}"
            if require_contiguous
            else "skipped (dependency-scoped validation)",
        )
    )

    if expected_batch_ids is not None:
        expected_ids = sorted(set(expected_batch_ids))
        expected_set = set(expected_ids)
        actual_set = set(ids)
        max_actual_id = ids[-1] if ids else None
        prefix_expected_ids = [bid for bid in expected_ids if max_actual_id is not None and bid <= max_actual_id]
        prefix_expected_set = set(prefix_expected_ids)
        missing_prefix_ids = sorted(prefix_expected_set - actual_set)
        trailing_missing_ids = sorted(expected_set - actual_set - set(missing_prefix_ids))
        extra_ids = sorted(actual_set - expected_set)
        rows.append(
            _row(
                stage,
                family,
                tf,
                "batch_ids_cover_expected_prefix",
                len(missing_prefix_ids) == 0 and len(extra_ids) == 0,
                f"missing_prefix={len(missing_prefix_ids)} extra={len(extra_ids)} "
                f"first_missing_prefix={missing_prefix_ids[:5]} first_extra={extra_ids[:5]}",
            )
        )
        rows.append(
            _row(
                stage,
                family,
                tf,
                "trailing_lag_vs_expected",
                True,
                f"trailing_missing={len(trailing_missing_ids)} first_trailing={trailing_missing_ids[:5]}",
            )
        )

    glob_pattern = str(path / "batch_*.parquet")
    scan = scan_override if scan_override is not None else _scan_parquet_relaxed(glob_pattern)
    schema = set(scan.collect_schema().names())
    missing = sorted(required_cols - schema)
    rows.append(
        _row(
            stage,
            family,
            tf,
            "required_columns",
            len(missing) == 0,
            "missing=" + ",".join(missing) if missing else "ok",
        )
    )

    counts = _scan_batch_counts(scan)
    if expected_rows_per_batch is not None:
        if allow_last_incomplete and len(counts) > 0:
            last_batch_id = counts["batch_id"].max()
            bad_n = counts.filter(
                (
                    (pl.col("batch_id") != last_batch_id)
                    & (pl.col("n") != expected_rows_per_batch)
                )
                | (
                    (pl.col("batch_id") == last_batch_id)
                    & ((pl.col("n") <= 0) | (pl.col("n") > expected_rows_per_batch))
                )
            )
        else:
            bad_n = counts.filter(pl.col("n") != expected_rows_per_batch)
        rows.append(
            _row(
                stage,
                family,
                tf,
                "rows_per_batch",
                len(bad_n) == 0,
                f"bad_batches={len(bad_n)}, allow_last_incomplete={allow_last_incomplete}",
            )
        )

    dup_ts = _duplicate_ts_count(scan)
    rows.append(
        _row(
            stage,
            family,
            tf,
            "duplicate_timestamp_within_batch",
            dup_ts == 0,
            f"duplicates={dup_ts}",
        )
    )

    for check_col in ["timestamp", "batch_id"]:
        if check_col in schema:
            n_null = _null_count(scan, check_col)
            rows.append(
                _row(
                    stage,
                    family,
                    tf,
                    f"null_{check_col}",
                    n_null == 0,
                    f"nulls={n_null}",
                )
            )

    return rows, len(files)


def _validate_combined_family(tf: str, family: str, scope: dict, expected_ids: list[int]) -> tuple[list[dict], dict]:
    stage = "combined"
    rows = []
    state = {"ok": True, "batch_count": 0}
    path = scope["backtest_dir"] / f"{tf}_HTF_combined.parquet"
    if not path.exists():
        rows.append(_row(stage, family, tf, "file_exists", False, f"missing: {path}"))
        state["ok"] = False
        return rows, state

    scan = pl.scan_parquet(path)
    schema = set(scan.collect_schema().names())
    required = {
        "timestamp",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "period_8h_start",
        "batch_id",
    } | FAMILY_META_REQUIRED
    missing = sorted(required - schema)
    rows.append(
        _row(
            stage,
            family,
            tf,
            "required_columns",
            len(missing) == 0,
            "missing=" + ",".join(missing) if missing else "ok",
        )
    )

    counts = scan.group_by("batch_id").agg(pl.len().alias("n")).collect().sort("batch_id")
    ids = counts["batch_id"].to_list()
    state["batch_count"] = len(ids)
    if len(counts) > 0:
        last_batch_id = counts["batch_id"].max()
        bad_n = counts.filter(
            (
                (pl.col("batch_id") != last_batch_id)
                & (pl.col("n") != BARS_PER_BATCH[tf])
            )
            | (
                (pl.col("batch_id") == last_batch_id)
                & ((pl.col("n") <= 0) | (pl.col("n") > BARS_PER_BATCH[tf]))
            )
        )
    else:
        bad_n = counts

    rows.extend(
        [
            _row(stage, family, tf, "batch_count", len(ids) == len(expected_ids), f"found={len(ids)}, expected={len(expected_ids)}"),
            _row(stage, family, tf, "batch_ids_contiguous", ids == list(range(ids[0], ids[-1] + 1)) if ids else False, f"min={ids[0] if ids else None}, max={ids[-1] if ids else None}"),
            _row(stage, family, tf, "rows_per_batch", len(bad_n) == 0, f"bad_batches={len(bad_n)}, allow_last_incomplete=True"),
        ]
    )

    dup_ts = _duplicate_ts_count(str(path))
    rows.append(_row(stage, family, tf, "duplicate_timestamp_within_batch", dup_ts == 0, f"duplicates={dup_ts}"))
    for col in ["timestamp", "batch_id", "period_8h_start", "family_period_start", "family_period_end"]:
        if col in schema:
            n_null = _null_count(str(path), col)
            rows.append(_row(stage, family, tf, f"null_{col}", n_null == 0, f"nulls={n_null}"))

    period_mismatch = int(
        scan.filter(pl.col("period_8h_start").dt.replace_time_zone(None) != _period_expr(family))
        .select(pl.len())
        .collect()
        .item()
    )
    family_period_mismatch = int(
        scan.filter(pl.col("family_period_start").dt.replace_time_zone(None) != _period_expr(family))
        .select(pl.len())
        .collect()
        .item()
    )
    family_end_mismatch = int(
        scan.filter(
            pl.col("family_period_end").dt.replace_time_zone(None)
            != (pl.col("family_period_start").dt.replace_time_zone(None) + timedelta(hours=8))
        )
        .select(pl.len())
        .collect()
        .item()
    )
    family_name_mismatch = int(
        scan.filter(pl.col("batch_family") != family).select(pl.len()).collect().item()
    )
    family_batch_mismatch = int(
        scan.filter(pl.col("family_batch_id") != pl.col("batch_id")).select(pl.len()).collect().item()
    )
    label_half_mismatch = int(
        scan.filter(pl.col("is_label_half") != (pl.col("family_bar_pos") < (BARS_PER_BATCH[tf] // 2)))
        .select(pl.len())
        .collect()
        .item()
    )
    bar_pos_bounds = int(
        scan.filter((pl.col("family_bar_pos") < 0) | (pl.col("family_bar_pos") >= BARS_PER_BATCH[tf]))
        .select(pl.len())
        .collect()
        .item()
    )
    rows.extend(
        [
            _row(stage, family, tf, "period_8h_start_alignment", period_mismatch == 0, f"mismatched_rows={period_mismatch}"),
            _row(stage, family, tf, "family_period_start_alignment", family_period_mismatch == 0, f"mismatched_rows={family_period_mismatch}"),
            _row(stage, family, tf, "family_period_end_alignment", family_end_mismatch == 0, f"mismatched_rows={family_end_mismatch}"),
            _row(stage, family, tf, "batch_family_value", family_name_mismatch == 0, f"mismatched_rows={family_name_mismatch}"),
            _row(stage, family, tf, "family_batch_id_alignment", family_batch_mismatch == 0, f"mismatched_rows={family_batch_mismatch}"),
            _row(stage, family, tf, "is_label_half_alignment", label_half_mismatch == 0, f"mismatched_rows={label_half_mismatch}"),
            _row(stage, family, tf, "family_bar_pos_bounds", bar_pos_bounds == 0, f"bad_rows={bar_pos_bounds}"),
        ]
    )

    state["ok"] = all(r["ok"] for r in rows)
    return rows, state


def _validate_labels_family(tf: str, family: str, scope: dict, expected_ids: list[int]) -> tuple[list[dict], pl.DataFrame]:
    stage = "labels"
    path = scope["labels_dir"] / tf
    files = sorted(path.glob("batch_*.parquet"))
    scan = _scan_label_batches_normalized(tf, family, path) if files else None
    rows, _ = _validate_batch_dir_family(
        stage=stage,
        family=family,
        tf=tf,
        path=path,
        expected_rows_per_batch=BARS_PER_BATCH[tf],
        required_cols={"timestamp", "batch_id", "target_4class", "target_breakfree"} | FAMILY_META_REQUIRED,
        expected_batch_ids=expected_ids,
        allow_last_incomplete=True,
        scan_override=scan,
    )
    if not files:
        return rows, pl.DataFrame({"batch_id": [], "n_valid_4class": []})

    schema = set(scan.collect_schema().names())
    metadata_nulls = int(
        scan.filter(
            pl.any_horizontal(
                [pl.col(col).is_null() for col in sorted(FAMILY_META_REQUIRED - {"batch_id"})]
            )
        )
        .select(pl.len())
        .collect()
        .item()
    )
    rows.append(
        _row(
            stage,
            family,
            tf,
            "family_metadata_backfilled",
            metadata_nulls == 0,
            f"rows_with_missing_meta={metadata_nulls}",
        )
    )

    bad_t4 = int(scan.filter(~pl.col("target_4class").is_in([-1, 0, 1, 2, 3])).select(pl.len()).collect().item())
    bad_bf = int(scan.filter(~pl.col("target_breakfree").is_in([-1, 0, 1, 2])).select(pl.len()).collect().item())
    rows.extend(
        [
            _row(stage, family, tf, "target_4class_value_range", bad_t4 == 0, f"invalid_rows={bad_t4}"),
            _row(stage, family, tf, "target_breakfree_value_range", bad_bf == 0, f"invalid_rows={bad_bf}"),
        ]
    )

    valid_counts = (
        scan.group_by("batch_id")
        .agg((pl.col("target_4class") >= 0).sum().alias("n_valid_4class"))
        .collect()
        .sort("batch_id")
    )
    if len(valid_counts) > 0:
        last_batch_id = valid_counts["batch_id"].max()
        bad_valid = valid_counts.filter(
            (
                (pl.col("batch_id") != last_batch_id)
                & (pl.col("n_valid_4class") != ENTRY_VALID_ROWS[tf])
            )
            | (
                (pl.col("batch_id") == last_batch_id)
                & (pl.col("n_valid_4class") > ENTRY_VALID_ROWS[tf])
            )
        )
    else:
        bad_valid = valid_counts
    rows.append(
        _row(
            stage,
            family,
            tf,
            "target_4class_valid_rows_per_batch",
            len(bad_valid) == 0,
            f"bad_batches={len(bad_valid)}, expected_non_last={ENTRY_VALID_ROWS[tf]}, allow_last_incomplete=True",
        )
    )

    invalid_pair = int(
        scan.filter((pl.col("target_4class") < 0) & (pl.col("target_breakfree") != -1))
        .select(pl.len())
        .collect()
        .item()
    )
    rows.append(_row(stage, family, tf, "breakfree_invalid_when_4class_invalid", invalid_pair == 0, f"violations={invalid_pair}"))

    bar_col_map = {"1m": "bar_pos_1m", "5m": "bar_pos_5m", "15m": "bar_pos"}
    bar_col = bar_col_map[tf]
    if bar_col in schema:
        entry_limit = BARS_PER_BATCH[tf] // 2
        late_labels = int(
            scan.filter((pl.col(bar_col) >= entry_limit) & (pl.col("target_4class") >= 0))
            .select(pl.len())
            .collect()
            .item()
        )
        rows.append(_row(stage, family, tf, "entry_window_gating_4class", late_labels == 0, f"late_labeled_rows={late_labels}"))

    return rows, valid_counts


def _validate_optimized_family(tf: str, family: str, scope: dict, label_valid_counts: pl.DataFrame) -> tuple[list[dict], pl.DataFrame]:
    stage = "optimized"
    path = scope["optimized_dir"] / tf / "target_4class"
    expected_opt_ids = (
        label_valid_counts.filter(pl.col("n_valid_4class") > 0)["batch_id"].to_list()
        if len(label_valid_counts) > 0
        else []
    )
    rows, _ = _validate_batch_dir_family(
        stage=stage,
        family=family,
        tf=tf,
        path=path,
        expected_rows_per_batch=None,
        required_cols={"timestamp", "batch_id"} | DOWNSTREAM_META_REQUIRED,
        expected_batch_ids=expected_opt_ids,
        require_contiguous=False,
    )
    files = sorted(path.glob("batch_*.parquet"))
    if not files:
        return rows, pl.DataFrame({"batch_id": [], "n_opt": []})

    opt_counts = _scan_batch_counts(str(path / "batch_*.parquet")).rename({"n": "n_opt"})
    joined = label_valid_counts.join(opt_counts, on="batch_id", how="left").with_columns(pl.col("n_opt").fill_null(0))
    bad = joined.filter(
        ((pl.col("n_valid_4class") > 0) & (pl.col("n_valid_4class") != pl.col("n_opt")))
        | ((pl.col("n_valid_4class") == 0) & (pl.col("n_opt") > 0))
    )
    rows.append(_row(stage, family, tf, "rows_match_label_valid_counts", len(bad) == 0, f"bad_batches={len(bad)}"))
    return rows, opt_counts


def _validate_helpers_family(tf: str, family: str, scope: dict, opt_counts: pl.DataFrame) -> list[dict]:
    stage = "helpers"
    path = scope["helpers_dir"] / tf / "target_4class"
    expected_helper_ids = opt_counts["batch_id"].to_list() if len(opt_counts) > 0 else []
    rows, _ = _validate_batch_dir_family(
        stage=stage,
        family=family,
        tf=tf,
        path=path,
        expected_rows_per_batch=None,
        required_cols={"timestamp", "batch_id"} | DOWNSTREAM_META_REQUIRED,
        expected_batch_ids=expected_helper_ids,
        require_contiguous=False,
    )
    files = sorted(path.glob("batch_*.parquet"))
    if not files:
        return rows

    schema = set(_scan_parquet_relaxed(str(path / "batch_*.parquet")).collect_schema().names())
    n_helper_cols = len([c for c in schema if c.startswith("H_")])
    rows.append(_row(stage, family, tf, "helper_columns_present", n_helper_cols > 0, f"helper_cols={n_helper_cols}"))

    helper_counts = _scan_batch_counts(str(path / "batch_*.parquet")).rename({"n": "n_helper"})
    if len(opt_counts) > 0:
        joined = opt_counts.join(helper_counts, on="batch_id", how="left").with_columns(pl.col("n_helper").fill_null(-1))
        bad = joined.filter(pl.col("n_opt") != pl.col("n_helper"))
        rows.append(_row(stage, family, tf, "rows_match_optimized_counts", len(bad) == 0, f"bad_batches={len(bad)}"))
    return rows


def _validate_cross_family(tf: str) -> list[dict]:
    rows = []
    stage = "cross_family"
    base_scope = family_scope("B")
    shift_scope = family_scope("C")
    b_path = base_scope["backtest_dir"] / f"{tf}_HTF_combined.parquet"
    c_path = shift_scope["backtest_dir"] / f"{tf}_HTF_combined.parquet"
    if not b_path.exists() or not c_path.exists():
        rows.append(_row(stage, "B+C", tf, "combined_files_exist", False, f"missing={b_path.exists()}/{c_path.exists()}"))
        return rows

    half = BARS_PER_BATCH[tf] // 2
    b = pl.read_parquet(
        b_path,
        columns=["timestamp", "batch_id", "family_bar_pos", "is_label_half"],
    )
    c = pl.read_parquet(
        c_path,
        columns=[
            "timestamp",
            "batch_id",
            "family_bar_pos",
            "source_base_batch_id",
            "source_half_in_base",
            "is_label_half",
        ],
    )

    c_first = c.filter(pl.col("family_bar_pos") < half)
    c_second = c.filter(pl.col("family_bar_pos") >= half)
    bad_source_first = c_first.filter(
        (pl.col("source_base_batch_id") != pl.col("batch_id"))
        | (pl.col("source_half_in_base") != "F")
    )
    bad_source_second = c_second.filter(
        (pl.col("source_base_batch_id") != (pl.col("batch_id") + 1))
        | (pl.col("source_half_in_base") != "L")
    )
    rows.extend(
        [
            _row(stage, "B+C", tf, "c_first_half_source_mapping", len(bad_source_first) == 0, f"bad_rows={len(bad_source_first)}"),
            _row(stage, "B+C", tf, "c_second_half_source_mapping", len(bad_source_second) == 0, f"bad_rows={len(bad_source_second)}"),
        ]
    )

    b_second = b.filter(pl.col("family_bar_pos") >= half).select(
        ["timestamp", pl.col("batch_id").alias("c_batch_id")]
    )
    c_first_join = c_first.select(["timestamp", pl.col("batch_id").alias("c_batch_id")])
    missing_first = c_first_join.join(b_second, on=["timestamp", "c_batch_id"], how="anti")

    b_first_next = (
        b.filter(pl.col("family_bar_pos") < half)
        .select(["timestamp", (pl.col("batch_id") - 1).alias("c_batch_id")])
        .filter(pl.col("c_batch_id") > 0)
    )
    c_second_join = c_second.select(["timestamp", pl.col("batch_id").alias("c_batch_id")])
    missing_second = c_second_join.join(b_first_next, on=["timestamp", "c_batch_id"], how="anti")
    rows.extend(
        [
            _row(stage, "B+C", tf, "c_first_half_equals_b_second_half", len(missing_first) == 0, f"missing_rows={len(missing_first)}"),
            _row(stage, "B+C", tf, "c_second_half_equals_next_b_first_half", len(missing_second) == 0, f"missing_rows={len(missing_second)}"),
        ]
    )

    b_counts = b.group_by("batch_id").agg(pl.len().alias("n")).sort("batch_id")
    c_counts = c.group_by("batch_id").agg(pl.len().alias("n")).sort("batch_id")
    complete_b_ids = b_counts.filter(pl.col("n") == BARS_PER_BATCH[tf])["batch_id"].to_list()
    complete_c_ids = c_counts.filter(pl.col("n") == BARS_PER_BATCH[tf])["batch_id"].to_list()

    b_expected_valid = b.filter(
        pl.col("batch_id").is_in(complete_b_ids) & pl.col("is_label_half")
    ).select("timestamp")
    c_expected_valid = c.filter(
        pl.col("batch_id").is_in(complete_c_ids) & pl.col("is_label_half")
    ).select("timestamp")
    expected_valid = pl.concat([b_expected_valid, c_expected_valid], how="vertical").unique()

    b_label_path = base_scope["labels_dir"] / tf
    c_label_path = shift_scope["labels_dir"] / tf
    if not b_label_path.exists() or not c_label_path.exists():
        rows.append(_row(stage, "B+C", tf, "label_dirs_exist", False, f"missing={b_label_path.exists()}/{c_label_path.exists()}"))
        return rows

    b_valid = (
        _scan_label_batches_normalized(tf, "B", b_label_path)
        .filter(pl.col("batch_id").is_in(complete_b_ids) & (pl.col("target_4class") >= 0))
        .select("timestamp")
        .collect()
        .unique()
    )
    c_valid = (
        _scan_label_batches_normalized(tf, "C", c_label_path)
        .filter(pl.col("batch_id").is_in(complete_c_ids) & (pl.col("target_4class") >= 0))
        .select("timestamp")
        .collect()
        .unique()
    )
    dup_valid = b_valid.join(c_valid, on="timestamp", how="inner")
    actual_valid = pl.concat([b_valid, c_valid], how="vertical").unique()
    missing_valid = expected_valid.join(actual_valid, on="timestamp", how="anti")
    extra_valid = actual_valid.join(expected_valid, on="timestamp", how="anti")

    rows.extend(
        [
            _row(stage, "B+C", tf, "no_row_valid_in_both_families", len(dup_valid) == 0, f"duplicate_valid_rows={len(dup_valid)}"),
            _row(stage, "B+C", tf, "completed_windows_expected_valid_covered", len(missing_valid) == 0, f"missing_valid_rows={len(missing_valid)}"),
            _row(stage, "B+C", tf, "completed_windows_no_extra_valid_rows", len(extra_valid) == 0, f"extra_valid_rows={len(extra_valid)}"),
        ]
    )
    return rows


print("=" * 70)
print("CELL 13: END-TO-END PIPELINE VALIDATION")
print("=" * 70)
print(
    f"Families/timeframes: {[(family, timeframes) for family, _, timeframes in FAMILY_RUNS]}"
)
print(f"Expected valid label rows per batch: {ENTRY_VALID_ROWS}")
print("=" * 70)

all_rows: list[dict] = []

for family, scope, family_timeframes in FAMILY_RUNS:
    print(f"\n=== FAMILY {family} ===")
    for tf in family_timeframes:
        print(f"\n--- {family} / {tf} ---")
        expected_ids = _expected_batch_ids(tf, scope)
        complete_ids = _complete_batch_ids(tf, scope)
        combined_rows, _ = _validate_combined_family(tf, family, scope, expected_ids)
        all_rows.extend(combined_rows)

        feature_rows, _ = _validate_batch_dir_family(
            stage="features",
            family=family,
            tf=tf,
            path=scope["features_dir"] / tf,
            expected_rows_per_batch=BARS_PER_BATCH[tf],
            required_cols={
                "timestamp",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "batch_id",
                "period_8h_start",
                "bar_in_batch_norm",
            } | FAMILY_META_REQUIRED,
            expected_batch_ids=expected_ids,
            allow_last_incomplete=True,
        )
        all_rows.extend(feature_rows)

        label_rows, label_valid_counts = _validate_labels_family(tf, family, scope, expected_ids)
        all_rows.extend(label_rows)

        opt_rows, opt_counts = _validate_optimized_family(tf, family, scope, label_valid_counts)
        all_rows.extend(opt_rows)

        helper_rows = _validate_helpers_family(tf, family, scope, opt_counts)
        all_rows.extend(helper_rows)

for tf in sorted(set(globals().get("HTF_TIMEFRAMES", ["1m", "15m"])) & set(globals().get("SHIFT4H_TIMEFRAMES", ["1m", "15m"]))):
    all_rows.extend(_validate_cross_family(tf))

validation_df = pl.DataFrame(all_rows).with_columns(
    pl.when(pl.col("ok")).then(pl.lit("PASS")).otherwise(pl.lit("FAIL")).alias("status")
)

summary = (
    validation_df.group_by(["stage", "family", "tf"])
    .agg(
        [
            pl.len().alias("checks"),
            pl.col("ok").sum().alias("pass"),
            (pl.len() - pl.col("ok").sum()).alias("fail"),
        ]
    )
    .sort(["stage", "family", "tf"])
)

print("\n" + "=" * 70)
print("VALIDATION SUMMARY")
print("=" * 70)
print(summary)

fails = validation_df.filter(~pl.col("ok"))
if len(fails) > 0:
    print("\n" + "=" * 70)
    print("FAILED CHECKS")
    print("=" * 70)
    print(fails.select(["stage", "family", "tf", "check", "detail"]))
    raise AssertionError(
        f"Pipeline validation failed: {len(fails)} failed checks. "
        "Fix failures before running backtest."
    )

print("\nAll validation checks passed.")
