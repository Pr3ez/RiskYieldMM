"""
Metrics Tracking for Pipeline Quality Monitoring
=================================================

Stores metrics from each pipeline run to detect quality degradation
when new data is added.

Usage:
    from scripts.workflow.metrics_tracking import (
        record_run_metrics,
        load_metrics_history,
        check_quality_degradation,
        print_metrics_comparison,
    )

    # After running optimization
    record_run_metrics(
        run_type="optimization",
        metrics={"mean_ic": 0.045, "n_rows": 5438},
    )

    # Check if quality dropped
    degradation = check_quality_degradation()
    if degradation:
        print("⚠️ Quality degradation detected!")
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# Default metrics file location
METRICS_FILE = Path(__file__).parent.parent.parent / "data" / "pipeline_metrics.json"


def _load_metrics_db() -> dict[str, list]:
    """Load metrics database from file."""
    if METRICS_FILE.exists():
        with open(METRICS_FILE) as f:
            return json.load(f)
    return {"runs": []}


def _save_metrics_db(db: dict[str, list]) -> None:
    """Save metrics database to file."""
    METRICS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(METRICS_FILE, "w") as f:
        json.dump(db, f, indent=2, default=str)


def record_run_metrics(
    run_type: str,
    metrics: dict[str, Any],
    data_rows: int | None = None,
    data_timestamp_end: str | None = None,
    notes: str | None = None,
) -> dict:
    """
    Record metrics from a pipeline run.

    Args:
        run_type: Type of run (e.g., "optimization", "l1_precompute", "backtest")
        metrics: Dict of metric name -> value
        data_rows: Number of rows in source data
        data_timestamp_end: Last timestamp in data
        notes: Optional notes about this run

    Returns:
        The recorded run entry
    """
    db = _load_metrics_db()

    run_entry = {
        "timestamp": datetime.now().isoformat(),
        "run_type": run_type,
        "data_rows": data_rows,
        "data_timestamp_end": data_timestamp_end,
        "metrics": metrics,
        "notes": notes,
    }

    db["runs"].append(run_entry)
    _save_metrics_db(db)

    print(f"📊 Recorded {run_type} metrics: {len(metrics)} values")
    return run_entry


def load_metrics_history(
    run_type: str | None = None,
    last_n: int | None = None,
) -> pd.DataFrame:
    """
    Load metrics history as DataFrame.

    Args:
        run_type: Filter by run type (optional)
        last_n: Return only last N runs (optional)

    Returns:
        DataFrame with run history
    """
    db = _load_metrics_db()
    runs = db.get("runs", [])

    if run_type:
        runs = [r for r in runs if r.get("run_type") == run_type]

    if last_n:
        runs = runs[-last_n:]

    if not runs:
        return pd.DataFrame()

    # Flatten metrics into columns
    rows = []
    for run in runs:
        row = {
            "timestamp": run["timestamp"],
            "run_type": run["run_type"],
            "data_rows": run.get("data_rows"),
            "data_timestamp_end": run.get("data_timestamp_end"),
            "notes": run.get("notes"),
        }
        # Add all metrics as columns
        for k, v in run.get("metrics", {}).items():
            row[f"metric_{k}"] = v
        rows.append(row)

    return pd.DataFrame(rows)


def compute_optimization_metrics(project_root: Path) -> dict[str, float]:
    """
    Compute current optimization metrics for all target-horizon combinations.

    Args:
        project_root: Path to project root

    Returns:
        Dict of metrics
    """
    import polars as pl
    from scipy.stats import spearmanr

    from scripts.analysis import config, data

    metrics = {}

    # Load source data
    df = data.load_analysis_data()

    raw = pl.read_parquet(config.RAW_FILE)
    close = raw["RAW_P_close_abs_NN"].to_pandas()
    high = raw["RAW_P_high_abs_NN"].to_pandas()
    low = raw["RAW_P_low_abs_NN"].to_pandas()
    close.index = df.index
    high.index = df.index
    low.index = df.index

    # Import centralized target configuration
    from scripts.workflow.config import WORKFLOW_TARGETS

    targets = WORKFLOW_TARGETS
    horizons = [1, 3, 6, 12]

    for target in targets:
        for horizon in horizons:
            config_name = f"{target}_{horizon}bar"
            opt_file = (
                project_root / "data" / f"features_8h_optimized_{config_name}.parquet"
            )

            if not opt_file.exists():
                continue

            # Load optimized features
            X_opt = pd.read_parquet(opt_file)

            # Compute target using full data
            future_high = high.shift(-horizon)
            future_low = low.shift(-horizon)
            up_move = (future_high - close) / close
            down_move = (close - future_low) / close
            net_candle_ret = up_move - down_move

            if target == "direction":
                y = (net_candle_ret > 0).astype(float)
            elif target == "volatility":
                fwd_ret = (close.shift(-horizon) - close) / close
                y = fwd_ret.abs()
            elif target == "volatility_regime":
                # Binary: will volatility INCREASE (1) or DECREASE (0)?
                log_returns = np.log(close / close.shift(1))
                vol_window = 21
                rolling_vol = log_returns.rolling(vol_window).std()
                future_vol = rolling_vol.shift(-horizon)
                y = (future_vol > rolling_vol).astype(float)
                y[rolling_vol.isna() | future_vol.isna()] = np.nan
            elif target == "trend_regime":
                fast_window = max(21, horizon * 5)
                slow_window = max(63, horizon * 15)
                sma_fast = close.rolling(fast_window).mean()
                sma_slow = close.rolling(slow_window).mean()
                y = (sma_fast > sma_slow).astype(float)
            else:
                continue

            # Align y to X_opt's index (optimized features may have different row count)
            y_aligned = (
                y.loc[X_opt.index] if hasattr(X_opt, "index") else y.iloc[: len(X_opt)]
            )

            # Compute mean |IC| across features
            ics = []
            y_vals = y_aligned.values
            for col in X_opt.columns:
                if "×" in col:  # Skip interaction features for base IC
                    continue
                x_vals = X_opt[col].values
                mask = ~(np.isnan(x_vals) | np.isnan(y_vals))
                if mask.sum() > 100:
                    ic, _ = spearmanr(x_vals[mask], y_vals[mask])
                    if not np.isnan(ic):
                        ics.append(abs(ic))

            if ics:
                metrics[f"{config_name}_mean_ic"] = float(np.mean(ics))
                metrics[f"{config_name}_max_ic"] = float(np.max(ics))
                metrics[f"{config_name}_n_features"] = len(X_opt.columns)

    # Overall metrics
    ic_values = [v for k, v in metrics.items() if k.endswith("_mean_ic")]
    if ic_values:
        metrics["overall_mean_ic"] = float(np.mean(ic_values))

    return metrics


def check_quality_degradation(
    threshold_pct: float = 10.0,
    run_type: str = "optimization",
) -> dict[str, Any] | None:
    """
    Check if quality has degraded compared to previous runs.

    Only compares targets that exist in BOTH runs (handles target changes like
    vol_spike → volatility_regime without false alarms).

    Args:
        threshold_pct: Percentage drop to consider degradation
        run_type: Type of run to check

    Returns:
        Dict with degradation info if detected, None otherwise
    """
    history = load_metrics_history(run_type=run_type, last_n=10)

    if len(history) < 2:
        return None

    # Get last two runs
    prev = history.iloc[-2]
    curr = history.iloc[-1]

    # Check key metrics - only compare targets present in BOTH runs
    degradations = []
    skipped_metrics = []

    metric_cols = [c for c in history.columns if c.startswith("metric_")]

    # Find common metrics (present in both runs with valid values)
    common_ic_metrics = []
    for col in metric_cols:
        prev_val = prev.get(col)
        curr_val = curr.get(col)

        # Skip if metric doesn't exist in both runs
        if pd.isna(prev_val) or pd.isna(curr_val):
            if pd.notna(prev_val) or pd.notna(curr_val):
                skipped_metrics.append(col.replace("metric_", ""))
            continue
        if prev_val == 0:
            continue

        # Track IC metrics for common-only overall comparison
        if "_mean_ic" in col and col != "metric_overall_mean_ic":
            common_ic_metrics.append((col, prev_val, curr_val))

        pct_change = (curr_val - prev_val) / abs(prev_val) * 100

        # For IC metrics, negative change is bad
        if "ic" in col.lower() and pct_change < -threshold_pct:
            # Skip overall_mean_ic - we'll recalculate from common targets only
            if col == "metric_overall_mean_ic":
                continue
            degradations.append(
                {
                    "metric": col.replace("metric_", ""),
                    "prev": prev_val,
                    "curr": curr_val,
                    "pct_change": pct_change,
                }
            )

    # Recalculate overall_mean_ic from COMMON targets only
    if common_ic_metrics:
        prev_common_mean = np.mean([x[1] for x in common_ic_metrics])
        curr_common_mean = np.mean([x[2] for x in common_ic_metrics])
        common_pct_change = (
            (curr_common_mean - prev_common_mean) / abs(prev_common_mean) * 100
        )

        if common_pct_change < -threshold_pct:
            degradations.append(
                {
                    "metric": "overall_mean_ic (common targets only)",
                    "prev": prev_common_mean,
                    "curr": curr_common_mean,
                    "pct_change": common_pct_change,
                    "common_targets": [
                        c[0].replace("metric_", "").replace("_mean_ic", "")
                        for c in common_ic_metrics
                    ],
                }
            )

    if degradations:
        return {
            "detected": True,
            "threshold_pct": threshold_pct,
            "degradations": degradations,
            "skipped_metrics": skipped_metrics,
            "prev_timestamp": prev["timestamp"],
            "curr_timestamp": curr["timestamp"],
        }

    return None


def print_metrics_comparison(last_n: int = 5, run_type: str = "optimization") -> None:
    """
    Print comparison of recent metrics runs.

    Args:
        last_n: Number of recent runs to show
        run_type: Type of runs to compare
    """
    history = load_metrics_history(run_type=run_type, last_n=last_n)

    if history.empty:
        print("No metrics history found.")
        return

    print("=" * 80)
    print(f"METRICS HISTORY ({run_type}, last {len(history)} runs)")
    print("=" * 80)

    # Show key metrics over time
    key_metrics = [c for c in history.columns if "overall" in c or "mean_ic" in c][:5]

    for _, row in history.iterrows():
        ts = row["timestamp"][:19]  # Trim to datetime
        rows = row.get("data_rows", "?")
        print(f"\n📅 {ts} | {rows} rows")

        for col in key_metrics:
            val = row.get(col)
            if val is not None and not pd.isna(val):
                metric_name = col.replace("metric_", "")
                print(f"   {metric_name}: {val:.4f}")


def get_baseline_metrics(run_type: str = "optimization") -> dict[str, float] | None:
    """
    Get baseline metrics from first run (or earliest available).

    Args:
        run_type: Type of run

    Returns:
        Dict of baseline metrics or None
    """
    history = load_metrics_history(run_type=run_type)

    if history.empty:
        return None

    first_run = history.iloc[0]
    metrics = {}

    for col in history.columns:
        if col.startswith("metric_"):
            val = first_run.get(col)
            if val is not None and not pd.isna(val):
                metrics[col.replace("metric_", "")] = val

    return metrics


# =============================================================================
# STEP-BY-STEP QUALITY GATES
# =============================================================================


class QualityGateError(Exception):
    """Raised when a quality gate fails and execution should stop."""

    def __init__(self, step: str, message: str, degradations: list[dict]):
        self.step = step
        self.message = message
        self.degradations = degradations
        super().__init__(f"Quality gate failed at {step}: {message}")


def compute_step_metrics(step: str, project_root: Path) -> dict[str, float]:
    """
    Compute metrics for a specific pipeline step.

    Args:
        step: Step name (step0_data, step1_features, step2_targets, step3_optimization)
        project_root: Path to project root

    Returns:
        Dict of metric name -> value
    """
    import polars as pl

    metrics = {}

    if step == "step0_data":
        # Data quality metrics
        raw_file = project_root / "data" / "merged_8h_raw.parquet"
        if raw_file.exists():
            df = pl.read_parquet(raw_file)
            metrics["n_rows"] = len(df)
            metrics["n_columns"] = len(df.columns)

            # Check for NaN percentage in key columns
            for col in ["RAW_P_close_abs_NN", "RAW_P_high_abs_NN", "RAW_P_low_abs_NN"]:
                if col in df.columns:
                    nan_pct = df[col].null_count() / len(df) * 100
                    metrics[f"{col}_nan_pct"] = nan_pct

    elif step == "step1_features":
        # Feature engineering metrics
        features_file = project_root / "data" / "features_8h.parquet"
        if features_file.exists():
            df = pl.read_parquet(features_file)
            metrics["n_rows"] = len(df)
            metrics["n_features"] = len(df.columns)

            # Check feature distributions (sample 10 features)
            numeric_cols = [
                c for c in df.columns if df[c].dtype in [pl.Float64, pl.Float32]
            ][:10]
            for col in numeric_cols:
                vals = df[col].drop_nulls().to_numpy()
                if len(vals) > 100:
                    metrics[f"{col}_mean"] = float(np.mean(vals))
                    metrics[f"{col}_std"] = float(np.std(vals))

    elif step == "step2_targets":
        # Target label metrics
        analysis_file = project_root / "data" / "analysis_8h.parquet"
        if analysis_file.exists():
            df = pl.read_parquet(analysis_file)
            metrics["n_rows"] = len(df)

            # Check target distributions
            for target_col in ["y_direction", "y_volatility_regime", "y_trend_regime"]:
                if target_col in df.columns:
                    vals = df[target_col].drop_nulls()
                    if len(vals) > 0:
                        # Class balance
                        value_counts = vals.value_counts()
                        for row in value_counts.iter_rows():
                            val, count = row[0], row[1]
                            metrics[f"{target_col}_class{int(val)}_pct"] = (
                                count / len(vals) * 100
                            )

    elif step == "step3_optimization":
        # Use existing compute_optimization_metrics
        metrics = compute_optimization_metrics(project_root)

    return metrics


def check_step_quality(
    step: str,
    project_root: Path,
    threshold_pct: float = 10.0,
    halt_on_failure: bool = True,
) -> dict[str, Any]:
    """
    Check quality metrics for a pipeline step and optionally halt on degradation.

    Args:
        step: Step name
        project_root: Path to project root
        threshold_pct: Percentage change threshold for degradation
        halt_on_failure: If True, raise QualityGateError on degradation

    Returns:
        Dict with check results

    Raises:
        QualityGateError: If halt_on_failure=True and degradation detected
    """
    import polars as pl

    # Compute current metrics
    current_metrics = compute_step_metrics(step, project_root)

    if not current_metrics:
        print(f"⚠️ No metrics computed for {step}")
        return {"step": step, "status": "no_metrics", "metrics": {}}

    # Get data info
    analysis_file = project_root / "data" / "analysis_8h.parquet"
    data_rows = None
    data_timestamp = None
    if analysis_file.exists():
        df = pl.read_parquet(analysis_file)
        data_rows = len(df)
        if "timestamp" in df.columns:
            data_timestamp = str(df.select("timestamp").max().item())

    # Record metrics
    record_run_metrics(
        run_type=step,
        metrics=current_metrics,
        data_rows=data_rows,
        data_timestamp_end=data_timestamp,
    )

    # Check for degradation against previous run
    history = load_metrics_history(run_type=step, last_n=2)

    if len(history) < 2:
        print(
            f"✅ {step}: First run, baseline captured ({len(current_metrics)} metrics)"
        )
        return {
            "step": step,
            "status": "baseline",
            "metrics": current_metrics,
            "data_rows": data_rows,
        }

    # Compare with previous
    prev = history.iloc[-2]
    degradations = []
    skipped_new_targets = []

    # Collect common target ICs for a fair overall comparison
    common_target_ics_prev = []
    common_target_ics_curr = []

    for key, curr_val in current_metrics.items():
        prev_key = f"metric_{key}"
        prev_val = prev.get(prev_key)

        # Skip metrics that don't exist in previous run (new targets like volatility_regime)
        if prev_val is None or pd.isna(prev_val):
            if "_mean_ic" in key and key != "overall_mean_ic":
                skipped_new_targets.append(key.replace("_mean_ic", ""))
            continue
        if prev_val == 0:
            continue

        # Track per-target ICs for fair overall comparison
        if "_mean_ic" in key and key != "overall_mean_ic":
            common_target_ics_prev.append(prev_val)
            common_target_ics_curr.append(curr_val)

        pct_change = (curr_val - prev_val) / abs(prev_val) * 100

        # Determine if this is a "higher is better" or "lower is better" metric
        is_degraded = False

        # IC metrics: higher is better (but skip overall_mean_ic - we handle it separately)
        if key == "overall_mean_ic":
            # Skip the stored overall_mean_ic, we'll compute from common targets
            continue
        elif "ic" in key.lower() or "mean_ic" in key.lower():
            if pct_change < -threshold_pct:
                is_degraded = True

        # NaN percentage: lower is better
        elif "nan_pct" in key.lower():
            if pct_change > threshold_pct:
                is_degraded = True

        # Class balance: stability is important (either direction)
        elif "class" in key.lower() and "pct" in key.lower():
            if (
                abs(pct_change) > threshold_pct * 2
            ):  # Allow more variance for class balance
                is_degraded = True

        # Feature count/row count: should be stable or growing
        elif key in ["n_rows", "n_features", "n_columns"]:
            if pct_change < -5:  # Alert if data shrinks
                is_degraded = True

        if is_degraded:
            degradations.append(
                {
                    "metric": key,
                    "prev": prev_val,
                    "curr": curr_val,
                    "pct_change": pct_change,
                }
            )

    # Compute overall_mean_ic from COMMON targets only (fair comparison)
    if common_target_ics_prev and common_target_ics_curr:
        prev_overall = np.mean(common_target_ics_prev)
        curr_overall = np.mean(common_target_ics_curr)
        overall_pct_change = (curr_overall - prev_overall) / abs(prev_overall) * 100

        if overall_pct_change < -threshold_pct:
            degradations.append(
                {
                    "metric": "overall_mean_ic (common targets)",
                    "prev": prev_overall,
                    "curr": curr_overall,
                    "pct_change": overall_pct_change,
                }
            )

    # Log skipped new targets
    if skipped_new_targets:
        print(f"ℹ️ New targets (no baseline yet): {', '.join(skipped_new_targets)}")

    if degradations:
        print(f"\n{'=' * 70}")
        print(f"⚠️ QUALITY DEGRADATION DETECTED AT {step.upper()}")
        print(f"{'=' * 70}")
        for d in degradations:
            print(
                f"   {d['metric']}: {d['prev']:.4f} → {d['curr']:.4f} ({d['pct_change']:+.1f}%)"
            )
        print(f"{'=' * 70}\n")

        if halt_on_failure:
            raise QualityGateError(
                step=step,
                message=f"{len(degradations)} metrics degraded beyond {threshold_pct}% threshold",
                degradations=degradations,
            )

        return {
            "step": step,
            "status": "degraded",
            "metrics": current_metrics,
            "degradations": degradations,
            "data_rows": data_rows,
        }

    print(f"✅ {step}: Quality check passed ({len(current_metrics)} metrics stable)")
    return {
        "step": step,
        "status": "passed",
        "metrics": current_metrics,
        "data_rows": data_rows,
    }


# =============================================================================
# L1 HISTORICAL CONSISTENCY MONITORING
# =============================================================================

# Storage for L1 snapshots
L1_SNAPSHOT_DIR = Path(__file__).parent.parent.parent / "data" / "pipeline_results"


def snapshot_l1_historical(
    config: str,
    project_root: Path,
    n_rows: int = 100,
) -> dict[str, Any]:
    """
    Snapshot historical L1 values BEFORE resuming computation.

    This captures checksums and sample values of the first N assembled iterations
    to verify they don't change when new data is added.

    Args:
        config: Config name (e.g., "direction_1bar")
        project_root: Path to project root
        n_rows: Number of historical rows to snapshot

    Returns:
        Dict with snapshot data (checksums, sample values, metadata)
    """
    import hashlib

    assembled_path = (
        project_root / "data" / "precomputed" / config / "assembled.parquet"
    )

    if not assembled_path.exists():
        return {
            "config": config,
            "status": "no_existing_data",
            "n_rows": 0,
            "timestamp": datetime.now().isoformat(),
        }

    # Load existing assembled data
    df = pd.read_parquet(assembled_path)

    if len(df) == 0:
        return {
            "config": config,
            "status": "empty_data",
            "n_rows": 0,
            "timestamp": datetime.now().isoformat(),
        }

    # Take first N rows (historical data that should never change)
    n_rows = min(n_rows, len(df))
    historical = df.head(n_rows)

    # Get feature columns (H_* are helper features)
    feature_cols = [c for c in historical.columns if c.startswith("H_")]

    # Compute checksums for each feature column
    feature_checksums = {}
    for col in feature_cols:
        values = historical[col].values
        # Round to handle floating point noise
        values_rounded = np.round(values.astype(float), 8)
        checksum = hashlib.md5(values_rounded.tobytes()).hexdigest()
        feature_checksums[col] = checksum

    # Store sample values at key positions for detailed comparison
    sample_rows = [0, n_rows // 4, n_rows // 2, 3 * n_rows // 4, n_rows - 1]
    sample_rows = [r for r in sample_rows if r < n_rows]

    sample_values = {}
    for row_idx in sample_rows:
        sample_values[f"row_{row_idx}"] = {
            col: float(historical.iloc[row_idx][col])
            for col in feature_cols[:10]  # Limit to 10 features for readability
            if not pd.isna(historical.iloc[row_idx][col])
        }

    # Overall checksum of all feature data
    all_feature_data = historical[feature_cols].values
    all_feature_rounded = np.round(all_feature_data.astype(float), 8)
    overall_checksum = hashlib.md5(all_feature_rounded.tobytes()).hexdigest()

    snapshot = {
        "config": config,
        "status": "captured",
        "n_rows": n_rows,
        "n_features": len(feature_cols),
        "feature_columns": feature_cols,
        "feature_checksums": feature_checksums,
        "overall_checksum": overall_checksum,
        "sample_values": sample_values,
        "timestamp": datetime.now().isoformat(),
        "pred_idx_range": [
            int(historical["pred_idx"].min())
            if "pred_idx" in historical.columns
            else None,
            int(historical["pred_idx"].max())
            if "pred_idx" in historical.columns
            else None,
        ],
    }

    return snapshot


def verify_l1_historical(
    config: str,
    project_root: Path,
    snapshot: dict[str, Any],
    halt_on_failure: bool = True,
) -> dict[str, Any]:
    """
    Verify L1 historical values AFTER resuming computation.

    Compares current assembled data against the pre-resume snapshot.
    If any historical row has changed, this indicates a causality violation.

    Args:
        config: Config name
        project_root: Path to project root
        snapshot: Snapshot from snapshot_l1_historical()
        halt_on_failure: If True, raise QualityGateError on mismatch

    Returns:
        Dict with verification results

    Raises:
        QualityGateError: If halt_on_failure=True and historical values changed
    """
    import hashlib

    # Handle case where no prior data existed
    if snapshot.get("status") in ["no_existing_data", "empty_data"]:
        return {
            "config": config,
            "status": "first_run",
            "message": "No prior data to compare (first L1 computation)",
        }

    assembled_path = (
        project_root / "data" / "precomputed" / config / "assembled.parquet"
    )

    if not assembled_path.exists():
        return {
            "config": config,
            "status": "error",
            "message": "Assembled file missing after computation",
        }

    df = pd.read_parquet(assembled_path)
    n_rows = snapshot["n_rows"]

    if len(df) < n_rows:
        return {
            "config": config,
            "status": "error",
            "message": f"Data shrunk: expected >= {n_rows} rows, got {len(df)}",
        }

    # Get the same historical rows
    historical = df.head(n_rows)
    feature_cols = snapshot["feature_columns"]

    # Verify overall checksum first (fast check)
    all_feature_data = historical[feature_cols].values
    all_feature_rounded = np.round(all_feature_data.astype(float), 8)
    current_overall = hashlib.md5(all_feature_rounded.tobytes()).hexdigest()

    if current_overall == snapshot["overall_checksum"]:
        return {
            "config": config,
            "status": "passed",
            "message": f"All {n_rows} historical rows unchanged",
            "n_rows_verified": n_rows,
            "n_features_verified": len(feature_cols),
        }

    # Overall checksum failed - find which features changed
    changed_features = []
    changed_details = []

    for col in feature_cols:
        values = historical[col].values
        values_rounded = np.round(values.astype(float), 8)
        current_checksum = hashlib.md5(values_rounded.tobytes()).hexdigest()

        if current_checksum != snapshot["feature_checksums"].get(col):
            changed_features.append(col)

            # Find specific rows that changed
            snapshot_values = snapshot.get("sample_values", {})
            for row_key, row_data in snapshot_values.items():
                if col in row_data:
                    row_idx = int(row_key.split("_")[1])
                    current_val = float(historical.iloc[row_idx][col])
                    expected_val = row_data[col]
                    if abs(current_val - expected_val) > 1e-6:
                        changed_details.append(
                            {
                                "feature": col,
                                "row": row_idx,
                                "expected": expected_val,
                                "actual": current_val,
                                "diff": current_val - expected_val,
                            }
                        )

    # Build error report
    result = {
        "config": config,
        "status": "FAILED",
        "n_rows_checked": n_rows,
        "n_features_changed": len(changed_features),
        "changed_features": changed_features[:20],  # Limit for readability
        "changed_details": changed_details[:10],
        "message": f"HISTORICAL VALUES CHANGED! {len(changed_features)} features modified.",
    }

    if halt_on_failure:
        print("\n" + "=" * 70)
        print(f"❌ L1 HISTORICAL CONSISTENCY FAILURE: {config}")
        print("=" * 70)
        print(f"\nRows checked: {n_rows}")
        print(f"Features changed: {len(changed_features)}")
        print(f"\nChanged features: {', '.join(changed_features[:10])}")
        if changed_details:
            print("\nSample changes:")
            for d in changed_details[:5]:
                print(
                    f"  {d['feature']} row {d['row']}: {d['expected']:.6f} → {d['actual']:.6f}"
                )
        print("\n⚠️ This should NEVER happen if optimizers are truly causal!")
        print("   Possible causes:")
        print("   1. Bug in optimizer code (non-causal computation)")
        print("   2. Source data was modified (not just extended)")
        print("   3. Random seed or floating point instability")
        print("=" * 70 + "\n")

        raise QualityGateError(
            step=f"l1_historical_{config}",
            message=f"Historical L1 values changed for {config}! {len(changed_features)} features affected.",
            degradations=[
                {
                    "metric": f,
                    "prev": "checksum_mismatch",
                    "curr": "changed",
                    "pct_change": 100,
                }
                for f in changed_features[:10]
            ],
        )

    return result


def run_l1_quality_gate(
    config: str,
    project_root: Path,
    before_snapshot: dict[str, Any],
    auto_halt: bool = True,
) -> bool:
    """
    Run L1 historical consistency check after resume.

    This is the main function to call after L1 precomputation for a config.

    Args:
        config: Config name
        project_root: Path to project root
        before_snapshot: Snapshot from snapshot_l1_historical() called before resume
        auto_halt: If True, raise exception on failure

    Returns:
        True if passed, False if failed (only if auto_halt=False)

    Example:
        # Before L1 computation:
        snapshot = snapshot_l1_historical("direction_1bar", PROJECT_ROOT)

        # Run L1 computation...
        precompute_l1_for_config(...)

        # After L1 computation:
        run_l1_quality_gate("direction_1bar", PROJECT_ROOT, snapshot)
    """
    result = verify_l1_historical(
        config=config,
        project_root=project_root,
        snapshot=before_snapshot,
        halt_on_failure=auto_halt,
    )

    status = result.get("status", "unknown")

    if status == "passed":
        print(
            f"✅ L1 {config}: Historical consistency verified ({result.get('n_rows_verified', '?')} rows)"
        )
        return True
    elif status == "first_run":
        print(f"📝 L1 {config}: First run, no prior data to compare")
        return True
    elif status == "FAILED":
        if not auto_halt:
            print(f"❌ L1 {config}: Historical consistency FAILED!")
        return False
    else:
        print(f"⚠️ L1 {config}: Unexpected status: {status}")
        return False


def run_quality_gate(
    step: str,
    project_root: Path,
    threshold_pct: float = 10.0,
    auto_halt: bool = True,
) -> bool:
    """
    Run quality gate for a step. Returns True if passed, False if degraded.

    This is the main function to use in the notebook at each step.

    Args:
        step: Step name
        project_root: Path to project root
        threshold_pct: Percentage change threshold
        auto_halt: If True, raise exception on failure (stops notebook)

    Returns:
        True if quality check passed, False if degraded (only if auto_halt=False)

    Example:
        # In notebook cell after Step 1:
        from scripts.workflow.metrics_tracking import run_quality_gate
        run_quality_gate("step1_features", PROJECT_ROOT)
        # Will halt if degradation detected
    """
    try:
        result = check_step_quality(
            step=step,
            project_root=project_root,
            threshold_pct=threshold_pct,
            halt_on_failure=auto_halt,
        )
        return result["status"] in ["passed", "baseline"]
    except QualityGateError:
        if auto_halt:
            raise
        return False


def print_quality_summary(project_root: Path) -> None:
    """
    Print summary of quality metrics across all steps.

    Args:
        project_root: Path to project root
    """
    steps = ["step0_data", "step1_features", "step2_targets", "step3_optimization"]

    print("=" * 80)
    print("PIPELINE QUALITY SUMMARY")
    print("=" * 80)

    for step in steps:
        history = load_metrics_history(run_type=step, last_n=1)
        if history.empty:
            print(f"\n{step}: No data")
            continue

        last_run = history.iloc[-1]
        ts = last_run["timestamp"][:19]
        rows = last_run.get("data_rows", "?")

        print(f"\n📊 {step} (last run: {ts}, {rows} rows)")

        # Show key metrics
        metric_cols = [c for c in history.columns if c.startswith("metric_")]
        shown = 0
        for col in sorted(metric_cols):
            val = last_run.get(col)
            if val is not None and not pd.isna(val) and shown < 5:
                metric_name = col.replace("metric_", "")
                print(f"   {metric_name}: {val:.4f}")
                shown += 1
