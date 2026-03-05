#!/usr/bin/env python3
"""
Full directional-pattern audit for 1m/target_4class over stored walk-forward batches.

Focus:
- How directional accuracy changes across the 12 prepared configs
- Repeating-pattern diagnostics (high-accuracy recurrence + winner transitions)
- Stability by time segment and by row decile (first/late rows inside 1m batches)
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import polars as pl


DEFAULT_OUTPUT_DIR = "prediction_analysis/one_minute_target4class_pattern_outputs"
DEFAULT_UNIT = "1m/target_4class"


@dataclass(frozen=True)
class Inputs:
    project_root: Path
    ensemble_run_dir: Path
    output_dir: Path
    output_tag: str
    unit: str
    high_accuracy_threshold: float
    rolling_window_short: int
    rolling_window_long: int
    max_period_lag: int
    linear_issue_url: str
    notion_page_url: str
    verbose: bool


def parse_args() -> Inputs:
    p = argparse.ArgumentParser(description="Audit 1m/target_4class directional patterns across 12 configs.")
    p.add_argument("--project-root", type=str, default=".")
    p.add_argument(
        "--ensemble-run-dir",
        type=str,
        default="prediction_analysis/multitimeframe_ensemble_outputs/20260225_173235_all6_3500_current_periodclose_nolive_ram",
    )
    p.add_argument("--output-dir", type=str, default=DEFAULT_OUTPUT_DIR)
    p.add_argument("--output-tag", type=str, default="full3500")
    p.add_argument("--unit", type=str, default=DEFAULT_UNIT)
    p.add_argument("--high-accuracy-threshold", type=float, default=0.70)
    p.add_argument("--rolling-window-short", type=int, default=25)
    p.add_argument("--rolling-window-long", type=int, default=100)
    p.add_argument("--max-period-lag", type=int, default=60)
    p.add_argument("--linear-issue-url", type=str, default="")
    p.add_argument("--notion-page-url", type=str, default="")
    p.add_argument("--verbose", action="store_true")
    a = p.parse_args()

    project_root = Path(a.project_root).expanduser().resolve()
    ensemble_run_dir = (project_root / a.ensemble_run_dir).resolve()
    output_root = (project_root / a.output_dir).resolve()
    if a.rolling_window_short <= 1 or a.rolling_window_long <= 1:
        raise ValueError("rolling windows must be > 1")
    if a.rolling_window_short > a.rolling_window_long:
        raise ValueError("rolling-window-short must be <= rolling-window-long")
    if a.max_period_lag < 1:
        raise ValueError("max-period-lag must be >= 1")

    return Inputs(
        project_root=project_root,
        ensemble_run_dir=ensemble_run_dir,
        output_dir=output_root,
        output_tag=str(a.output_tag).strip(),
        unit=str(a.unit),
        high_accuracy_threshold=float(a.high_accuracy_threshold),
        rolling_window_short=int(a.rolling_window_short),
        rolling_window_long=int(a.rolling_window_long),
        max_period_lag=int(a.max_period_lag),
        linear_issue_url=str(a.linear_issue_url),
        notion_page_url=str(a.notion_page_url),
        verbose=bool(a.verbose),
    )


def _rolling_mean(arr: np.ndarray, window: int) -> np.ndarray:
    out = np.full(arr.shape[0], np.nan, dtype=np.float64)
    if arr.size < window:
        return out
    csum = np.cumsum(np.insert(arr.astype(np.float64, copy=False), 0, 0.0))
    out[window - 1 :] = (csum[window:] - csum[:-window]) / float(window)
    return out


def _lag_corr(arr: np.ndarray, lag: int) -> float:
    if lag <= 0 or arr.size <= lag:
        return float("nan")
    a = arr[:-lag]
    b = arr[lag:]
    if a.size < 3 or b.size < 3:
        return float("nan")
    sa = float(np.std(a))
    sb = float(np.std(b))
    if sa < 1e-12 or sb < 1e-12:
        return float("nan")
    return float(np.corrcoef(a, b)[0, 1])


def _write_df(df: pl.DataFrame, path_parquet: Path, path_csv: Path) -> None:
    df.write_parquet(path_parquet)
    df.write_csv(path_csv)


def _candidate_keys(ensemble_run_dir: Path, unit: str) -> list[str]:
    p = ensemble_run_dir / "candidate_sets_by_unit.json"
    if not p.exists():
        raise FileNotFoundError(f"Missing candidate_sets_by_unit.json: {p}")
    obj = json.loads(p.read_text(encoding="utf-8"))
    unit_obj = obj.get(unit)
    if unit_obj is None:
        raise KeyError(f"Unit not found in candidate sets: {unit}")
    keys = [str(v) for v in (unit_obj.get("action_keys") or [])]
    if len(keys) != 12:
        raise ValueError(f"{unit} must have 12 configs, got {len(keys)}")
    return keys


def _build_batch_config_metrics(rows_path: Path, unit: str, action_keys: list[str]) -> pl.DataFrame:
    unit_scan = (
        pl.scan_parquet(str(rows_path))
        .filter((pl.col("unit") == unit) & pl.col("action_key").is_in(action_keys))
        .select(["pred_batch", "timestamp", "action_key", "y_true_direction", "y_pred_direction"])
    )
    directional_true = pl.col("y_true_direction").is_in(["UP", "DOWN"])
    directional_pred = pl.col("y_pred_direction").is_in(["UP", "DOWN"])
    active = directional_true & directional_pred
    correct = pl.col("y_true_direction") == pl.col("y_pred_direction")

    batch_cfg = (
        unit_scan.group_by(["pred_batch", "action_key"])
        .agg(
            [
                pl.len().alias("rows"),
                active.cast(pl.Int32).sum().alias("directional_rows"),
                (active & correct).cast(pl.Int32).sum().alias("directional_correct_rows"),
                (active & (pl.col("y_pred_direction") == "UP")).cast(pl.Int32).sum().alias("pred_up_rows"),
                (active & (pl.col("y_pred_direction") == "DOWN")).cast(pl.Int32).sum().alias("pred_down_rows"),
                (active & (pl.col("y_true_direction") == "UP")).cast(pl.Int32).sum().alias("true_up_rows"),
                (active & (pl.col("y_true_direction") == "DOWN")).cast(pl.Int32).sum().alias("true_down_rows"),
                (
                    (
                        active
                        & (pl.col("y_pred_direction") == "UP")
                        & (pl.col("y_true_direction") == "UP")
                    )
                    .cast(pl.Int32)
                    .sum()
                ).alias("tp_up_rows"),
                (
                    (
                        active
                        & (pl.col("y_pred_direction") == "DOWN")
                        & (pl.col("y_true_direction") == "DOWN")
                    )
                    .cast(pl.Int32)
                    .sum()
                ).alias("tp_down_rows"),
                (active & (pl.col("y_true_direction") != pl.col("y_pred_direction")))
                .cast(pl.Int32)
                .sum()
                .alias("opposite_rows"),
            ]
        )
        .with_columns(
            [
                pl.when(pl.col("directional_rows") > 0)
                .then(pl.col("directional_correct_rows") / pl.col("directional_rows"))
                .otherwise(None)
                .alias("directional_accuracy"),
                pl.when(pl.col("pred_up_rows") > 0)
                .then(pl.col("tp_up_rows") / pl.col("pred_up_rows"))
                .otherwise(None)
                .alias("up_precision"),
                pl.when(pl.col("pred_down_rows") > 0)
                .then(pl.col("tp_down_rows") / pl.col("pred_down_rows"))
                .otherwise(None)
                .alias("down_precision"),
                pl.when(pl.col("directional_rows") > 0)
                .then(pl.col("opposite_rows") / pl.col("directional_rows"))
                .otherwise(None)
                .alias("opposite_rate"),
                pl.when(pl.col("directional_rows") > 0)
                .then(pl.col("pred_up_rows") / pl.col("directional_rows"))
                .otherwise(None)
                .alias("pred_up_rate"),
                pl.when(pl.col("directional_rows") > 0)
                .then(pl.col("pred_down_rows") / pl.col("directional_rows"))
                .otherwise(None)
                .alias("pred_down_rate"),
            ]
        )
        .sort(["pred_batch", "action_key"])
        .collect()
    )
    return batch_cfg


def _build_row_decile_accuracy(
    rows_path: Path,
    unit: str,
    action_keys: list[str],
) -> pl.DataFrame:
    ref_action = action_keys[0]
    all_rows = (
        pl.scan_parquet(str(rows_path))
        .filter((pl.col("unit") == unit) & pl.col("action_key").is_in(action_keys))
        .select(["pred_batch", "timestamp", "action_key", "y_true_direction", "y_pred_direction"])
    )
    row_map = (
        pl.scan_parquet(str(rows_path))
        .filter((pl.col("unit") == unit) & (pl.col("action_key") == ref_action))
        .select(["pred_batch", "timestamp"])
        .sort(["pred_batch", "timestamp"])
        .with_columns(
            [
                pl.col("timestamp").cum_count().over("pred_batch").alias("row_pos"),
            ]
        )
        .with_columns(
            [
                ((((pl.col("row_pos") - 1) * 10) / pl.lit(240)).floor().cast(pl.Int32) + 1).alias(
                    "row_decile"
                )
            ]
        )
        .with_columns(pl.col("row_decile").clip(1, 10))
        .select(["pred_batch", "timestamp", "row_pos", "row_decile"])
    )

    directional = (
        all_rows.join(row_map, on=["pred_batch", "timestamp"], how="inner")
        .with_columns(
            [
                (
                    pl.col("y_true_direction").is_in(["UP", "DOWN"])
                    & pl.col("y_pred_direction").is_in(["UP", "DOWN"])
                ).alias("is_active"),
                (pl.col("y_true_direction") == pl.col("y_pred_direction")).alias("is_correct"),
            ]
        )
        .group_by(["action_key", "row_decile"])
        .agg(
            [
                pl.col("is_active").cast(pl.Int64).sum().alias("directional_rows"),
                (pl.col("is_active") & pl.col("is_correct")).cast(pl.Int64).sum().alias(
                    "directional_correct_rows"
                ),
            ]
        )
        .with_columns(
            pl.when(pl.col("directional_rows") > 0)
            .then(pl.col("directional_correct_rows") / pl.col("directional_rows"))
            .otherwise(None)
            .alias("directional_accuracy")
        )
        .sort(["action_key", "row_decile"])
        .collect()
    )
    return directional


def _build_report_text(
    *,
    run_dir: Path,
    summary: dict,
    top_cfg: pl.DataFrame,
    segment_drift: pl.DataFrame,
    threshold_dist: pl.DataFrame,
    repeat_df: pl.DataFrame,
) -> str:
    lines: list[str] = []
    lines.append("# 1m/target_4class Directional Pattern Audit")
    lines.append("")
    lines.append(f"- Run dir: `{run_dir}`")
    lines.append(f"- Batches: {summary['batches']} | Configs: {summary['configs']} | Threshold: {summary['high_accuracy_threshold']:.2f}")
    lines.append(
        f"- Mean directional accuracy across all config-batch points: {summary['global_directional_accuracy_mean']:.4f}"
    )
    lines.append(
        f"- Mean opposite-direction rate across all config-batch points: {summary['global_opposite_rate_mean']:.4f}"
    )
    lines.append("")
    lines.append("## Top Configs By Mean Directional Accuracy")
    lines.append("")
    lines.append(top_cfg.to_pandas().to_markdown(index=False))
    lines.append("")
    lines.append("## Drift (Last Segment - First Segment)")
    lines.append("")
    lines.append(segment_drift.to_pandas().to_markdown(index=False))
    lines.append("")
    lines.append("## High-Accuracy Availability Per Batch")
    lines.append("")
    lines.append(threshold_dist.to_pandas().to_markdown(index=False))
    lines.append("")
    lines.append("## Strongest Repeating High-Accuracy Lags")
    lines.append("")
    lines.append(repeat_df.to_pandas().to_markdown(index=False))
    lines.append("")
    lines.append("## Notes")
    lines.append("")
    lines.append("- Repeating lags are descriptive diagnostics only; they are not direct trading signals.")
    lines.append("- Any future config-selection policy must use only history `< t`.")
    return "\n".join(lines) + "\n"


def main() -> None:
    inp = parse_args()
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_name = f"{ts}_{inp.output_tag}" if inp.output_tag else ts
    out_dir = inp.output_dir / out_name
    out_dir.mkdir(parents=True, exist_ok=False)

    rows_path = inp.ensemble_run_dir / "unit_prediction_rows_dedup.parquet"
    if not rows_path.exists():
        raise FileNotFoundError(f"Missing rows parquet: {rows_path}")

    action_keys = _candidate_keys(inp.ensemble_run_dir, inp.unit)
    if inp.verbose:
        print("1m target_4class pattern audit")
        print(f"  ensemble_run_dir: {inp.ensemble_run_dir}")
        print(f"  unit: {inp.unit}")
        print(f"  action_keys: {len(action_keys)}")
        print(f"  output_dir: {out_dir}")

    batch_cfg = _build_batch_config_metrics(rows_path, inp.unit, action_keys)
    batches_n = int(batch_cfg["pred_batch"].n_unique())
    configs_n = int(batch_cfg["action_key"].n_unique())
    expected = batches_n * configs_n
    if len(batch_cfg) != expected:
        raise ValueError(
            f"Incomplete batch-config grid: rows={len(batch_cfg)} expected={expected} "
            f"(batches={batches_n}, configs={configs_n})"
        )

    # Segment id by batch chronology.
    batch_order = (
        batch_cfg.select("pred_batch")
        .unique()
        .sort("pred_batch")
        .with_row_count("batch_rank", offset=1)
        .with_columns(
            (((pl.col("batch_rank") - 1) * 10 / pl.lit(batches_n)).floor().cast(pl.Int32) + 1)
            .clip(1, 10)
            .alias("segment_10")
        )
    )
    batch_cfg = batch_cfg.join(batch_order, on="pred_batch", how="left")

    cfg_summary = (
        batch_cfg.group_by("action_key")
        .agg(
            [
                pl.len().alias("batches_seen"),
                pl.mean("directional_accuracy").alias("directional_accuracy_mean"),
                pl.median("directional_accuracy").alias("directional_accuracy_median"),
                pl.std("directional_accuracy").alias("directional_accuracy_std"),
                pl.quantile("directional_accuracy", 0.10).alias("directional_accuracy_p10"),
                pl.quantile("directional_accuracy", 0.90).alias("directional_accuracy_p90"),
                pl.min("directional_accuracy").alias("directional_accuracy_min"),
                pl.max("directional_accuracy").alias("directional_accuracy_max"),
                pl.mean("up_precision").alias("up_precision_mean"),
                pl.mean("down_precision").alias("down_precision_mean"),
                pl.mean("opposite_rate").alias("opposite_rate_mean"),
                (pl.col("directional_accuracy") >= inp.high_accuracy_threshold).cast(pl.Int32).sum().alias(
                    "high_acc_batches"
                ),
                (pl.col("directional_accuracy") <= 0.40).cast(pl.Int32).sum().alias("low_acc_batches"),
            ]
        )
        .with_columns(
            [
                (pl.col("high_acc_batches") / pl.col("batches_seen")).alias("high_acc_share"),
                (pl.col("low_acc_batches") / pl.col("batches_seen")).alias("low_acc_share"),
            ]
        )
        .sort(["directional_accuracy_mean", "opposite_rate_mean"], descending=[True, False])
    )

    # Rolling metrics + recurrence/autocorr diagnostics per config.
    roll_rows: list[dict] = []
    recur_rows: list[dict] = []
    periodic_rows: list[dict] = []
    for key in action_keys:
        s = batch_cfg.filter(pl.col("action_key") == key).sort("pred_batch")
        batches = s["pred_batch"].to_list()
        acc = s["directional_accuracy"].to_numpy()
        high = (acc >= inp.high_accuracy_threshold).astype(np.float64)
        roll_s = _rolling_mean(acc, inp.rolling_window_short)
        roll_l = _rolling_mean(acc, inp.rolling_window_long)
        for i in range(len(batches)):
            roll_rows.append(
                {
                    "action_key": key,
                    "pred_batch": int(batches[i]),
                    "directional_accuracy": float(acc[i]),
                    f"acc_roll_{inp.rolling_window_short}": float(roll_s[i]) if not np.isnan(roll_s[i]) else None,
                    f"acc_roll_{inp.rolling_window_long}": float(roll_l[i]) if not np.isnan(roll_l[i]) else None,
                }
            )

        high_idx = np.where(high > 0.5)[0]
        gaps = np.diff(high_idx) if high_idx.size >= 2 else np.array([], dtype=np.int64)
        recur_rows.append(
            {
                "action_key": key,
                "lag1_accuracy_autocorr": _lag_corr(acc, 1),
                "high_acc_events": int(high_idx.size),
                "high_acc_mean_gap_batches": float(gaps.mean()) if gaps.size > 0 else None,
                "high_acc_median_gap_batches": float(np.median(gaps)) if gaps.size > 0 else None,
            }
        )

        lag_corrs: list[tuple[int, float]] = []
        for lag in range(1, inp.max_period_lag + 1):
            c = _lag_corr(high, lag)
            if not math.isnan(c):
                lag_corrs.append((lag, c))
        lag_corrs.sort(key=lambda x: x[1], reverse=True)
        for lag, corr in lag_corrs[:3]:
            periodic_rows.append({"action_key": key, "lag": int(lag), "corr_high_acc_indicator": float(corr)})

    rolling_df = pl.DataFrame(roll_rows).sort(["action_key", "pred_batch"])
    recurrence_df = pl.DataFrame(recur_rows).sort("action_key")
    periodic_df = pl.DataFrame(periodic_rows).sort(["action_key", "corr_high_acc_indicator"], descending=[False, True])
    cfg_summary = cfg_summary.join(recurrence_df, on="action_key", how="left")

    # Segment profile.
    segment_df = (
        batch_cfg.group_by(["action_key", "segment_10"])
        .agg(
            [
                pl.mean("directional_accuracy").alias("directional_accuracy_mean"),
                pl.mean("opposite_rate").alias("opposite_rate_mean"),
            ]
        )
        .sort(["action_key", "segment_10"])
    )
    seg_first = (
        segment_df.filter(pl.col("segment_10") == 1)
        .select(["action_key", pl.col("directional_accuracy_mean").alias("acc_seg_first")])
    )
    seg_last = (
        segment_df.filter(pl.col("segment_10") == 10)
        .select(["action_key", pl.col("directional_accuracy_mean").alias("acc_seg_last")])
    )
    segment_drift = (
        cfg_summary.select(["action_key"])
        .join(seg_first, on="action_key", how="left")
        .join(seg_last, on="action_key", how="left")
        .with_columns((pl.col("acc_seg_last") - pl.col("acc_seg_first")).alias("acc_drift_last_minus_first"))
        .sort("acc_drift_last_minus_first", descending=True)
    )

    # Winner diagnostics per batch.
    winner_by_batch = (
        batch_cfg.sort(["pred_batch", "directional_accuracy", "action_key"], descending=[False, True, False])
        .group_by("pred_batch", maintain_order=True)
        .first()
        .rename({"action_key": "winner_action_key", "directional_accuracy": "winner_directional_accuracy"})
        .sort("pred_batch")
    )
    winner_counts = (
        winner_by_batch.group_by("winner_action_key")
        .agg(pl.len().alias("winner_batches"))
        .with_columns((pl.col("winner_batches") / pl.lit(float(batches_n))).alias("winner_share"))
        .sort("winner_batches", descending=True)
    )

    wb = winner_by_batch["winner_action_key"].to_list()
    transition_rows: list[dict] = []
    for i in range(1, len(wb)):
        transition_rows.append({"from_action_key": wb[i - 1], "to_action_key": wb[i], "cnt": 1})
    transition_df = (
        pl.DataFrame(transition_rows)
        .group_by(["from_action_key", "to_action_key"])
        .agg(pl.sum("cnt").alias("transitions"))
        .sort("transitions", descending=True)
    )

    # How many configs are above threshold each batch.
    threshold_by_batch = (
        batch_cfg.group_by("pred_batch")
        .agg(
            [
                (pl.col("directional_accuracy") >= inp.high_accuracy_threshold).cast(pl.Int32).sum().alias(
                    "configs_ge_threshold"
                ),
                pl.max("directional_accuracy").alias("best_config_accuracy"),
                pl.mean("directional_accuracy").alias("mean_accuracy_across_12"),
            ]
        )
        .sort("pred_batch")
    )
    threshold_dist = (
        threshold_by_batch.group_by("configs_ge_threshold")
        .agg(pl.len().alias("batches"))
        .with_columns((pl.col("batches") / pl.lit(float(batches_n))).alias("batch_share"))
        .sort("configs_ge_threshold")
    )

    # Correlation matrix across configs by batch accuracy.
    pivot = batch_cfg.select(["pred_batch", "action_key", "directional_accuracy"]).pivot(
        values="directional_accuracy",
        index="pred_batch",
        columns="action_key",
    )
    corr_df = pivot.drop("pred_batch").corr()
    corr_df = corr_df.insert_column(0, pl.Series("action_key", corr_df.columns))

    # Row-decile diagnostics inside each 1m batch.
    row_decile_df = _build_row_decile_accuracy(rows_path, inp.unit, action_keys)
    row_decile_overall = (
        row_decile_df.group_by("row_decile")
        .agg(pl.mean("directional_accuracy").alias("directional_accuracy_mean"))
        .sort("row_decile")
    )

    # Summary + report.
    summary = {
        "unit": inp.unit,
        "ensemble_run_dir": str(inp.ensemble_run_dir),
        "rows_path": str(rows_path),
        "batches": batches_n,
        "configs": configs_n,
        "batch_config_rows": int(len(batch_cfg)),
        "high_accuracy_threshold": float(inp.high_accuracy_threshold),
        "rolling_window_short": int(inp.rolling_window_short),
        "rolling_window_long": int(inp.rolling_window_long),
        "global_directional_accuracy_mean": float(batch_cfg["directional_accuracy"].mean()),
        "global_opposite_rate_mean": float(batch_cfg["opposite_rate"].mean()),
        "top_config_by_mean_accuracy": cfg_summary.select("action_key").to_series()[0],
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }

    top_cfg = cfg_summary.select(
        ["action_key", "directional_accuracy_mean", "opposite_rate_mean", "high_acc_share", "lag1_accuracy_autocorr"]
    ).head(6)
    top_periodic = periodic_df.group_by("action_key").first().sort("corr_high_acc_indicator", descending=True).head(6)
    report = _build_report_text(
        run_dir=inp.ensemble_run_dir,
        summary=summary,
        top_cfg=top_cfg,
        segment_drift=segment_drift.select(["action_key", "acc_seg_first", "acc_seg_last", "acc_drift_last_minus_first"]),
        threshold_dist=threshold_dist,
        repeat_df=top_periodic,
    )

    # Persist outputs.
    _write_df(batch_cfg, out_dir / "batch_config_directional_metrics.parquet", out_dir / "batch_config_directional_metrics.csv")
    _write_df(cfg_summary, out_dir / "config_directional_summary.parquet", out_dir / "config_directional_summary.csv")
    _write_df(rolling_df, out_dir / "config_rolling_accuracy.parquet", out_dir / "config_rolling_accuracy.csv")
    _write_df(segment_df, out_dir / "config_segment_profile.parquet", out_dir / "config_segment_profile.csv")
    _write_df(segment_drift, out_dir / "config_segment_drift.parquet", out_dir / "config_segment_drift.csv")
    _write_df(winner_by_batch, out_dir / "winner_by_batch.parquet", out_dir / "winner_by_batch.csv")
    _write_df(winner_counts, out_dir / "winner_counts.parquet", out_dir / "winner_counts.csv")
    _write_df(transition_df, out_dir / "winner_transition_matrix.parquet", out_dir / "winner_transition_matrix.csv")
    _write_df(threshold_by_batch, out_dir / "threshold_coverage_by_batch.parquet", out_dir / "threshold_coverage_by_batch.csv")
    _write_df(threshold_dist, out_dir / "threshold_coverage_distribution.parquet", out_dir / "threshold_coverage_distribution.csv")
    _write_df(periodic_df, out_dir / "periodic_high_accuracy_lags.parquet", out_dir / "periodic_high_accuracy_lags.csv")
    _write_df(corr_df, out_dir / "config_accuracy_correlation_matrix.parquet", out_dir / "config_accuracy_correlation_matrix.csv")
    _write_df(row_decile_df, out_dir / "row_decile_accuracy_by_config.parquet", out_dir / "row_decile_accuracy_by_config.csv")
    _write_df(row_decile_overall, out_dir / "row_decile_accuracy_overall.parquet", out_dir / "row_decile_accuracy_overall.csv")

    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (out_dir / "analysis_report.md").write_text(report, encoding="utf-8")

    tracking = {
        "linear_issue_url": inp.linear_issue_url,
        "notion_page_url": inp.notion_page_url,
        "run_command": " ".join([os.path.basename(sys.executable), *sys.argv]),
        "cwd": str(Path.cwd().resolve()),
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }
    (out_dir / "tracking_context.json").write_text(json.dumps(tracking, indent=2), encoding="utf-8")

    print("1m/target_4class pattern audit complete")
    print(f"  output_dir: {out_dir}")
    print(f"  summary: {out_dir / 'summary.json'}")
    print(f"  report: {out_dir / 'analysis_report.md'}")


if __name__ == "__main__":
    main()
