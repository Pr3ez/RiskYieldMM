"""Cross-block diagnostics for RPF ranked-signal router transfer.

This command compares completed ``rank_signal_router`` runs and builds a
prediction-safe context table plus post-hoc transfer labels.  It is diagnostic
only: current prediction labels are written for analysis, but are excluded from
the safe context feature table that a future meta-router may train on.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

from regression_feature_engineering.walkforward.ablation import FAMILY_PREFIXES
from regression_feature_engineering.walkforward.classification.targets import UP_EXTREME
from regression_feature_engineering.walkforward.data import resolve_context
from regression_feature_engineering.walkforward.rank_signal import write_rows_parquet
from regression_feature_engineering.walkforward.reports import append_event, write_json, write_stage_status
from scripts.project_paths import ensure_project_root_on_path


PROJECT_ROOT = ensure_project_root_on_path(Path(__file__))
OUTPUT_ROOT = PROJECT_ROOT / "test_output" / "rpf_ranked_signal_transfer_diagnostic"

CURRENT_LABEL_COLUMNS = {
    "rows",
    "positive_count",
    "negative_count",
    "predicted_positive_count",
    "true_positive_count",
    "false_positive_count",
    "false_negative_count",
    "true_negative_count",
    "precision",
    "recall",
    "false_positive_rate",
    "false_discovery_rate",
    "predicted_positive_rate",
    "base_positive_rate",
    "precision_lift",
    "decision_cost",
    "decision_cost_per_row",
    "decision_cost_per_signal",
    "positive_rate",
    "high_target_window",
    "active_window",
    "captured_high_target_window",
    "missed_high_target_window",
    "high_false_positive_window",
    "offline_topk_precision",
    "offline_topk_recall",
    "batch_state_gate_target",
    "batch_state_gate_positive_rate",
    "prediction_batch_positive_rate",
    "candidate_active",
    "candidate_good",
    "candidate_bad",
    "candidate_good_reason",
}

SAFE_CONTEXT_COLUMNS = [
    "source_block",
    "source_role",
    "source_run",
    "side",
    "candidate_name",
    "diagnostic",
    "status",
    "candidate_passed_validation",
    "candidate_fail_reasons",
    "router_step_idx",
    "router_pred_batch_id",
    "selected_feature_count",
    "threshold",
    "threshold_quantile",
    "max_signals_per_batch",
    "score_mean",
    "score_std",
    "validation_threshold_score",
    "batch_state_gate_mode",
    "batch_state_gate_status",
    "batch_state_gate_prefix_rows",
    "batch_state_gate_min_positive_rate",
    "batch_state_gate_probability_threshold",
    "batch_state_gate_train_batches",
    "batch_state_gate_train_positive_batches",
    "batch_state_gate_train_negative_batches",
    "batch_state_gate_val_pass_rate",
    "batch_state_gate_pred_pass_rate",
    "batch_state_gate_probability",
    "batch_state_gate_passed",
    "validation_status",
    "validation_passed",
    "validation_fail_reasons",
    "validation_ranked_signal_quality",
    "validation_precision",
    "validation_precision_lift",
    "validation_false_discovery_rate",
    "validation_predicted_positive_count",
    "validation_active_window_rate",
    "validation_zero_signal_window_rate",
    "validation_batch_count",
    "validation_active_batch_count",
    "validation_lift_positive_batch_count",
    "validation_lift_positive_batch_rate",
    "validation_median_active_precision_lift",
    "validation_median_active_false_discovery_rate",
    "validation_high_target_window_capture_rate",
    "validation_missed_high_target_window_rate",
    "sequence_feature_count",
    "selection_mode",
    "selection_rejected_reason",
    "specialist_entry_mode",
    "specialist_entry_candidate",
    "specialist_entry_reason",
    "reliability_reliability_status",
    "reliability_reliability_passed",
    "reliability_reliability_fail_reasons",
    "reliability_reliability_score",
    "reliability_history_windows",
    "reliability_signal_count",
    "reliability_active_windows",
    "reliability_precision",
    "reliability_base_rate",
    "reliability_precision_lift",
    "reliability_precision_lift_lcb",
    "reliability_precision_lcb",
    "reliability_false_discovery_rate",
    "reliability_active_window_rate",
    "reliability_zero_signal_window_rate",
    "reliability_high_false_positive_window_rate",
    "reliability_active_window_base_rate",
    "reliability_window_selection_lift",
    "reliability_selected_window_precision",
    "reliability_selected_window_precision_lcb",
    "reliability_selected_window_row_lift",
    "reliability_selected_window_row_lift_lcb",
    "reliability_selected_window_false_discovery_rate",
    "past_20_batch_positive_rate_mean",
    "past_20_batch_positive_rate_std",
    "past_60_batch_positive_rate_mean",
    "past_60_batch_positive_rate_std",
    "recent_candidate_precision_lift",
    "recent_candidate_precision_lift_lcb",
    "recent_candidate_window_selection_lift",
    "recent_candidate_selected_window_row_lift",
    "recent_candidate_selected_window_row_lift_lcb",
    "recent_candidate_false_discovery_rate",
    "current_validation_positive_rate",
    "current_validation_signal_rate",
    "validation_score_rows",
    "validation_score_mean",
    "validation_score_std",
    "validation_score_min",
    "validation_score_max",
    "validation_score_q50",
    "validation_score_q90",
    "validation_score_q95",
    "validation_score_q99",
    "validation_score_tail_spread_q95_q50",
    "validation_score_unique",
    "validation_margin_mean",
    "validation_margin_std",
    "validation_margin_min",
    "validation_margin_max",
    "validation_margin_q50",
    "validation_margin_q90",
    "validation_margin_q95",
    "validation_margin_q99",
    "validation_margin_positive_rate",
    "validation_margin_tail_spread_q95_q50",
    "validation_batch_count_observed",
    "validation_batch_base_rate_mean",
    "validation_batch_base_rate_std",
    "validation_batch_base_rate_min",
    "validation_batch_base_rate_max",
    "validation_batch_base_rate_range",
    "validation_batch_signal_rate_mean",
    "validation_batch_signal_rate_std",
    "validation_batch_signal_rate_max",
    "validation_batch_precision_lift_mean",
    "validation_batch_precision_lift_median",
    "validation_batch_precision_lift_std",
    "validation_batch_precision_lift_max",
    "validation_batch_fdr_mean",
    "validation_batch_fdr_median",
    "validation_batch_fdr_max",
    "validation_batch_active_rate_observed",
    "validation_batch_high_fpr_rate",
    "selected_feature_rows",
    "selected_abs_coef_sum",
    "selected_abs_coef_mean",
    "selected_abs_coef_std",
    "selected_abs_coef_max",
    "selected_top1_abs_coef_share",
    "selected_feature_train_std_mean",
    "selected_feature_train_std_max",
    "sequence_input_features",
    "sequence_length",
    "rocket_kernels",
    "sequence_scaler_fit_rows",
]

PRIOR_RPF_CONTEXT_FAMILIES = tuple(FAMILY_PREFIXES)
PRIOR_RPF_CONTEXT_METRICS = (
    "available_batches",
    "feature_count",
    "mean_abs",
    "std_abs",
    "recent_shift_abs",
    "mean",
    "std_mean",
)
DEFAULT_RPF_CONTEXT_LOOKBACKS = (20, 60)
DEFAULT_RPF_CONTEXT_MAX_FEATURES_PER_FAMILY = 24


def prior_rpf_context_columns(
    *,
    lookbacks: tuple[int, ...] = DEFAULT_RPF_CONTEXT_LOOKBACKS,
    families: tuple[str, ...] = PRIOR_RPF_CONTEXT_FAMILIES,
) -> list[str]:
    columns: list[str] = []
    for lookback in lookbacks:
        for family in families:
            for metric in PRIOR_RPF_CONTEXT_METRICS:
                columns.append(f"prior_rpf_l{int(lookback)}_{family}_{metric}")
    return columns


SAFE_CONTEXT_COLUMNS.extend(prior_rpf_context_columns())


@dataclass(frozen=True)
class DiagnosticInput:
    run_path: Path
    source_block: str
    source_role: str


def main() -> int:
    args = parse_args()
    candidate_names = parse_candidate_names(args.candidate_names)
    inputs = [
        DiagnosticInput(Path(args.older_run), "older", "comparison_train"),
        DiagnosticInput(Path(args.latest_run), "latest", "comparison_test"),
    ]
    if args.extra_run:
        for idx, run in enumerate(args.extra_run, start=1):
            inputs.append(DiagnosticInput(Path(run), f"extra_{idx}", "comparison_extra"))

    run_root = run_root_for_args()
    run_root.mkdir(parents=True, exist_ok=True)
    events_path = run_root / "events.jsonl"
    append_event(events_path, "stage_start", command="rank_signal_transfer_diagnostic")

    if args.base_run:
        base_run = Path(args.base_run)
        if not base_run.exists():
            raise FileNotFoundError(f"--base-run does not exist: {base_run}")

    transfer = build_candidate_transfer_table(
        inputs,
        candidate_names=candidate_names,
        good_precision_lift=float(args.good_precision_lift),
        good_max_false_discovery_rate=float(args.good_max_false_discovery_rate),
        bad_min_false_discovery_rate=float(args.bad_min_false_discovery_rate),
    )
    if bool(args.rpf_prior_context) and args.base_run:
        rpf_context = build_prior_rpf_context_for_transfer(
            transfer,
            base_run=Path(args.base_run),
            inputs=inputs,
            lookbacks=parse_int_tuple(args.rpf_prior_context_lookbacks),
            max_features_per_family=int(args.rpf_prior_context_max_features_per_family),
        )
        if not rpf_context.is_empty():
            transfer = transfer.join(rpf_context, on="router_pred_batch_id", how="left")
    safe = safe_context_features_from_transfer_table(transfer)
    active = active_window_comparison_from_transfer_table(transfer)
    summary = summarize_transfer_table(transfer)

    write_rows_parquet(run_root / "candidate_transfer_table.parquet", transfer.to_dicts())
    write_rows_parquet(run_root / "safe_context_features.parquet", safe.to_dicts())
    write_rows_parquet(run_root / "active_window_comparison.parquet", active.to_dicts())
    write_transfer_report(run_root / "transfer_report.md", transfer=transfer, summary=summary)
    write_json(
        run_root / "diagnostic_config.json",
        {
            "older_run": str(args.older_run),
            "latest_run": str(args.latest_run),
            "extra_run": [str(item) for item in args.extra_run or []],
            "base_run": str(args.base_run) if args.base_run else None,
            "candidate_names": list(candidate_names),
            "good_precision_lift": float(args.good_precision_lift),
            "good_max_false_discovery_rate": float(args.good_max_false_discovery_rate),
            "bad_min_false_discovery_rate": float(args.bad_min_false_discovery_rate),
            "rpf_prior_context": bool(args.rpf_prior_context),
            "rpf_prior_context_lookbacks": parse_int_tuple(args.rpf_prior_context_lookbacks),
            "rpf_prior_context_max_features_per_family": int(args.rpf_prior_context_max_features_per_family),
            "safe_context_columns": SAFE_CONTEXT_COLUMNS,
            "excluded_current_label_columns": sorted(CURRENT_LABEL_COLUMNS),
        },
    )
    write_stage_status(
        run_root / "stage_status.json",
        stage="rank_signal_transfer_diagnostic",
        status="complete",
        summary={
            "candidate_transfer_rows": transfer.height,
            "safe_context_rows": safe.height,
            "active_window_rows": active.height,
            "candidate_count": len(candidate_names),
            "source_run_count": len(inputs),
            "good_rows": int(transfer["candidate_good"].sum()) if transfer.height else 0,
            "bad_rows": int(transfer["candidate_bad"].sum()) if transfer.height else 0,
        },
    )
    append_event(events_path, "stage_done", run=str(run_root))
    print(f"[rpf-transfer] done run={run_root}", flush=True)
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build cross-block RPF ranked-signal transfer diagnostics.")
    parser.add_argument("--older-run", required=True)
    parser.add_argument("--latest-run", required=True)
    parser.add_argument("--extra-run", action="append", default=[])
    parser.add_argument("--base-run", default=None)
    parser.add_argument("--candidate-names", required=True)
    parser.add_argument("--good-precision-lift", type=float, default=1.20)
    parser.add_argument("--good-max-false-discovery-rate", type=float, default=0.50)
    parser.add_argument("--bad-min-false-discovery-rate", type=float, default=0.60)
    parser.add_argument("--rpf-prior-context", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--rpf-prior-context-lookbacks", default="20,60")
    parser.add_argument("--rpf-prior-context-max-features-per-family", type=int, default=24)
    return parser.parse_args()


def parse_candidate_names(raw: str | list[str] | tuple[str, ...]) -> tuple[str, ...]:
    if isinstance(raw, str):
        values = raw.split(",")
    else:
        values = list(raw)
    out = tuple(dict.fromkeys(str(value).strip() for value in values if str(value).strip()))
    if not out:
        raise ValueError("At least one candidate name is required")
    return out


def build_candidate_transfer_table(
    inputs: list[DiagnosticInput],
    *,
    candidate_names: tuple[str, ...],
    good_precision_lift: float = 1.20,
    good_max_false_discovery_rate: float = 0.50,
    bad_min_false_discovery_rate: float = 0.60,
) -> pl.DataFrame:
    frames = [
        load_router_run_transfer_rows(
            item,
            candidate_names=candidate_names,
            good_precision_lift=good_precision_lift,
            good_max_false_discovery_rate=good_max_false_discovery_rate,
            bad_min_false_discovery_rate=bad_min_false_discovery_rate,
        )
        for item in inputs
    ]
    if not frames:
        return pl.DataFrame()
    return pl.concat(frames, how="diagonal_relaxed").sort(["source_block", "side", "candidate_name", "router_pred_batch_id"])


def load_router_run_transfer_rows(
    item: DiagnosticInput,
    *,
    candidate_names: tuple[str, ...],
    good_precision_lift: float,
    good_max_false_discovery_rate: float,
    bad_min_false_discovery_rate: float,
) -> pl.DataFrame:
    run = item.run_path
    required = [
        run / "candidate_prediction_window_metrics.parquet",
        run / "candidate_validation_metrics.parquet",
    ]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Missing required router artifacts in {run}: {missing}")

    prediction = pl.read_parquet(run / "candidate_prediction_window_metrics.parquet").filter(
        pl.col("candidate_name").is_in(candidate_names)
    )
    prediction = ensure_columns(prediction, ["router_step_idx", "router_pred_batch_id"])
    prediction = prediction.with_columns(
        pl.lit(str(item.source_block)).alias("source_block"),
        pl.lit(str(item.source_role)).alias("source_role"),
        pl.lit(str(run)).alias("source_run"),
    )

    validation = normalize_validation_metrics(pl.read_parquet(run / "candidate_validation_metrics.parquet"))
    validation = validation.filter(pl.col("candidate_name").is_in(candidate_names))
    out = prediction.join(
        validation,
        on=["side", "candidate_name", "router_pred_batch_id"],
        how="left",
        suffix="_validation_dup",
    )

    validation_score_path = run / "candidate_validation_scores.parquet"
    if validation_score_path.exists():
        validation_score_context = normalize_validation_score_context(pl.read_parquet(validation_score_path)).filter(
            pl.col("candidate_name").is_in(candidate_names)
        )
        out = out.join(
            validation_score_context,
            on=["side", "candidate_name", "router_pred_batch_id"],
            how="left",
            suffix="_validation_score_dup",
        )

    validation_window_path = run / "candidate_validation_window_metrics.parquet"
    if validation_window_path.exists():
        validation_window_context = normalize_validation_window_context(pl.read_parquet(validation_window_path)).filter(
            pl.col("candidate_name").is_in(candidate_names)
        )
        out = out.join(
            validation_window_context,
            on=["side", "candidate_name", "router_pred_batch_id"],
            how="left",
            suffix="_validation_window_dup",
        )

    selected_feature_path = run / "selected_features.parquet"
    if selected_feature_path.exists():
        selected_feature_context = normalize_selected_feature_context(pl.read_parquet(selected_feature_path)).filter(
            pl.col("candidate_name").is_in(candidate_names)
        )
        out = out.join(
            selected_feature_context,
            on=["side", "candidate_name", "router_pred_batch_id"],
            how="left",
            suffix="_selected_feature_dup",
        )

    sequence_path = run / "sequence_diagnostics.parquet"
    if sequence_path.exists():
        sequence_context = normalize_sequence_context(pl.read_parquet(sequence_path)).filter(
            pl.col("candidate_name").is_in(candidate_names)
        )
        out = out.join(
            sequence_context,
            on=["side", "candidate_name", "router_pred_batch_id"],
            how="left",
            suffix="_sequence_dup",
        )

    audit_path = run / "candidate_selection_audit.parquet"
    if audit_path.exists():
        audit = normalize_selection_audit(pl.read_parquet(audit_path)).filter(pl.col("candidate_name").is_in(candidate_names))
        out = out.join(audit, on=["side", "candidate_name", "router_pred_batch_id"], how="left", suffix="_audit_dup")

    regime_path = run / "batch_regime_diagnostics.parquet"
    if regime_path.exists():
        regime = normalize_batch_regime(pl.read_parquet(regime_path))
        out = out.join(regime, on=["side", "router_pred_batch_id"], how="left", suffix="_regime_dup")

    out = add_transfer_labels(
        out,
        good_precision_lift=good_precision_lift,
        good_max_false_discovery_rate=good_max_false_discovery_rate,
        bad_min_false_discovery_rate=bad_min_false_discovery_rate,
    )
    return drop_duplicate_suffix_columns(out)


def normalize_validation_metrics(df: pl.DataFrame) -> pl.DataFrame:
    out = ensure_columns(df, ["pred_batch_id", "step_idx", "status", "passed_validation", "fail_reasons"])
    rename = {
        "pred_batch_id": "router_pred_batch_id",
        "step_idx": "validation_step_idx",
        "status": "validation_status",
        "passed_validation": "validation_passed",
        "fail_reasons": "validation_fail_reasons",
    }
    return out.rename({old: new for old, new in rename.items() if old in out.columns})


def normalize_validation_score_context(df: pl.DataFrame) -> pl.DataFrame:
    required = ["side", "candidate_name", "router_pred_batch_id", "rank_score", "threshold"]
    out = ensure_columns(df, required)
    if out.is_empty():
        return pl.DataFrame(schema={"side": pl.String, "candidate_name": pl.String, "router_pred_batch_id": pl.Int64})
    out = out.with_columns(
        pl.col("rank_score").cast(pl.Float64, strict=False).alias("_rank_score"),
        pl.col("threshold").cast(pl.Float64, strict=False).alias("_threshold"),
    ).with_columns((pl.col("_rank_score") - pl.col("_threshold")).alias("_margin"))
    return (
        out.group_by(["side", "candidate_name", "router_pred_batch_id"])
        .agg(
            pl.len().alias("validation_score_rows"),
            pl.col("_rank_score").mean().alias("validation_score_mean"),
            pl.col("_rank_score").std().alias("validation_score_std"),
            pl.col("_rank_score").min().alias("validation_score_min"),
            pl.col("_rank_score").max().alias("validation_score_max"),
            pl.col("_rank_score").quantile(0.50).alias("validation_score_q50"),
            pl.col("_rank_score").quantile(0.90).alias("validation_score_q90"),
            pl.col("_rank_score").quantile(0.95).alias("validation_score_q95"),
            pl.col("_rank_score").quantile(0.99).alias("validation_score_q99"),
            pl.col("_rank_score").n_unique().alias("validation_score_unique"),
            pl.col("_margin").mean().alias("validation_margin_mean"),
            pl.col("_margin").std().alias("validation_margin_std"),
            pl.col("_margin").min().alias("validation_margin_min"),
            pl.col("_margin").max().alias("validation_margin_max"),
            pl.col("_margin").quantile(0.50).alias("validation_margin_q50"),
            pl.col("_margin").quantile(0.90).alias("validation_margin_q90"),
            pl.col("_margin").quantile(0.95).alias("validation_margin_q95"),
            pl.col("_margin").quantile(0.99).alias("validation_margin_q99"),
            (pl.col("_margin") >= 0.0).mean().alias("validation_margin_positive_rate"),
        )
        .with_columns(
            (pl.col("validation_score_q95") - pl.col("validation_score_q50")).alias(
                "validation_score_tail_spread_q95_q50"
            ),
            (pl.col("validation_margin_q95") - pl.col("validation_margin_q50")).alias(
                "validation_margin_tail_spread_q95_q50"
            ),
        )
    )


def normalize_validation_window_context(df: pl.DataFrame) -> pl.DataFrame:
    required = [
        "side",
        "candidate_name",
        "router_pred_batch_id",
        "base_positive_rate",
        "predicted_positive_rate",
        "precision_lift",
        "false_discovery_rate",
        "active_window",
        "high_false_positive_window",
    ]
    out = ensure_columns(df, required)
    if out.is_empty():
        return pl.DataFrame(schema={"side": pl.String, "candidate_name": pl.String, "router_pred_batch_id": pl.Int64})
    out = out.with_columns(
        pl.col("base_positive_rate").cast(pl.Float64, strict=False).alias("_base_rate"),
        pl.col("predicted_positive_rate").cast(pl.Float64, strict=False).alias("_signal_rate"),
        pl.col("precision_lift").cast(pl.Float64, strict=False).alias("_precision_lift"),
        pl.col("false_discovery_rate").cast(pl.Float64, strict=False).alias("_fdr"),
        pl.col("active_window").cast(pl.Float64, strict=False).alias("_active"),
        pl.col("high_false_positive_window").cast(pl.Float64, strict=False).alias("_high_fpr"),
    )
    return (
        out.group_by(["side", "candidate_name", "router_pred_batch_id"])
        .agg(
            pl.len().alias("validation_batch_count_observed"),
            pl.col("_base_rate").mean().alias("validation_batch_base_rate_mean"),
            pl.col("_base_rate").std().alias("validation_batch_base_rate_std"),
            pl.col("_base_rate").min().alias("validation_batch_base_rate_min"),
            pl.col("_base_rate").max().alias("validation_batch_base_rate_max"),
            pl.col("_signal_rate").mean().alias("validation_batch_signal_rate_mean"),
            pl.col("_signal_rate").std().alias("validation_batch_signal_rate_std"),
            pl.col("_signal_rate").max().alias("validation_batch_signal_rate_max"),
            pl.col("_precision_lift").mean().alias("validation_batch_precision_lift_mean"),
            pl.col("_precision_lift").median().alias("validation_batch_precision_lift_median"),
            pl.col("_precision_lift").std().alias("validation_batch_precision_lift_std"),
            pl.col("_precision_lift").max().alias("validation_batch_precision_lift_max"),
            pl.col("_fdr").mean().alias("validation_batch_fdr_mean"),
            pl.col("_fdr").median().alias("validation_batch_fdr_median"),
            pl.col("_fdr").max().alias("validation_batch_fdr_max"),
            pl.col("_active").mean().alias("validation_batch_active_rate_observed"),
            pl.col("_high_fpr").mean().alias("validation_batch_high_fpr_rate"),
        )
        .with_columns(
            (pl.col("validation_batch_base_rate_max") - pl.col("validation_batch_base_rate_min")).alias(
                "validation_batch_base_rate_range"
            )
        )
    )


def normalize_selected_feature_context(df: pl.DataFrame) -> pl.DataFrame:
    required = [
        "side",
        "candidate_name",
        "router_pred_batch_id",
        "abs_coefficient",
        "feature_std_train",
        "final_status",
    ]
    out = ensure_columns(df, required)
    if out.is_empty():
        return pl.DataFrame(schema={"side": pl.String, "candidate_name": pl.String, "router_pred_batch_id": pl.Int64})
    out = out.filter(pl.col("final_status").fill_null("selected") == "selected").with_columns(
        pl.col("abs_coefficient").cast(pl.Float64, strict=False).alias("_abs_coef"),
        pl.col("feature_std_train").cast(pl.Float64, strict=False).alias("_feature_std_train"),
    )
    grouped = (
        out.group_by(["side", "candidate_name", "router_pred_batch_id"])
        .agg(
            pl.len().alias("selected_feature_rows"),
            pl.col("_abs_coef").sum().alias("selected_abs_coef_sum"),
            pl.col("_abs_coef").mean().alias("selected_abs_coef_mean"),
            pl.col("_abs_coef").std().alias("selected_abs_coef_std"),
            pl.col("_abs_coef").max().alias("selected_abs_coef_max"),
            pl.col("_feature_std_train").mean().alias("selected_feature_train_std_mean"),
            pl.col("_feature_std_train").max().alias("selected_feature_train_std_max"),
        )
        .with_columns(
            (
                pl.col("selected_abs_coef_max")
                / pl.when(pl.col("selected_abs_coef_sum") == 0.0)
                .then(None)
                .otherwise(pl.col("selected_abs_coef_sum"))
            ).alias("selected_top1_abs_coef_share")
        )
    )
    return grouped


def normalize_sequence_context(df: pl.DataFrame) -> pl.DataFrame:
    required = [
        "side",
        "candidate_name",
        "router_pred_batch_id",
        "sequence_input_features",
        "sequence_length",
        "rocket_kernels",
        "sequence_scaler_fit_rows",
    ]
    out = ensure_columns(df, required)
    keep = [
        "side",
        "candidate_name",
        "router_pred_batch_id",
        "sequence_input_features",
        "sequence_length",
        "rocket_kernels",
        "sequence_scaler_fit_rows",
    ]
    if out.is_empty():
        return pl.DataFrame(schema={"side": pl.String, "candidate_name": pl.String, "router_pred_batch_id": pl.Int64})
    return out.select([col for col in keep if col in out.columns]).unique(["side", "candidate_name", "router_pred_batch_id"])


def normalize_selection_audit(df: pl.DataFrame) -> pl.DataFrame:
    out = ensure_columns(df, ["router_pred_batch_id"])
    keep = [
        "side",
        "candidate_name",
        "router_pred_batch_id",
        "selection_mode",
        "selection_rejected_reason",
        "specialist_entry_mode",
        "specialist_entry_candidate",
        "specialist_entry_reason",
        "reliability_reliability_status",
        "reliability_reliability_passed",
        "reliability_reliability_fail_reasons",
        "reliability_reliability_score",
        "reliability_history_windows",
        "reliability_signal_count",
        "reliability_active_windows",
        "reliability_precision",
        "reliability_base_rate",
        "reliability_precision_lift",
        "reliability_precision_lift_lcb",
        "reliability_precision_lcb",
        "reliability_false_discovery_rate",
        "reliability_active_window_rate",
        "reliability_zero_signal_window_rate",
        "reliability_high_false_positive_window_rate",
        "reliability_active_window_base_rate",
        "reliability_window_selection_lift",
        "reliability_selected_window_precision",
        "reliability_selected_window_precision_lcb",
        "reliability_selected_window_row_lift",
        "reliability_selected_window_row_lift_lcb",
        "reliability_selected_window_false_discovery_rate",
    ]
    return out.select([col for col in keep if col in out.columns])


def normalize_batch_regime(df: pl.DataFrame) -> pl.DataFrame:
    out = ensure_columns(df, ["pred_batch_id"])
    out = out.rename({"pred_batch_id": "router_pred_batch_id"})
    keep = [
        "side",
        "router_pred_batch_id",
        "past_20_batch_positive_rate_mean",
        "past_20_batch_positive_rate_std",
        "past_60_batch_positive_rate_mean",
        "past_60_batch_positive_rate_std",
        "recent_candidate_precision_lift",
        "recent_candidate_precision_lift_lcb",
        "recent_candidate_window_selection_lift",
        "recent_candidate_selected_window_row_lift",
        "recent_candidate_selected_window_row_lift_lcb",
        "recent_candidate_false_discovery_rate",
        "current_validation_positive_rate",
        "current_validation_signal_rate",
        "prediction_batch_positive_rate",
    ]
    return out.select([col for col in keep if col in out.columns])


def build_prior_rpf_context_for_transfer(
    transfer: pl.DataFrame,
    *,
    base_run: Path,
    inputs: list[DiagnosticInput],
    lookbacks: tuple[int, ...] = DEFAULT_RPF_CONTEXT_LOOKBACKS,
    max_features_per_family: int = DEFAULT_RPF_CONTEXT_MAX_FEATURES_PER_FAMILY,
) -> pl.DataFrame:
    if transfer.is_empty() or "router_pred_batch_id" not in transfer.columns:
        return pl.DataFrame()
    asset, root = infer_asset_root_from_inputs(inputs)
    context = resolve_context(project_root=PROJECT_ROOT, asset=asset, root=root, target_col=UP_EXTREME)
    batch_index_path = Path(base_run) / "batch_index.parquet"
    if not batch_index_path.exists():
        raise FileNotFoundError(f"RPF prior context requires batch_index.parquet in --base-run: {base_run}")
    batch_index = pl.read_parquet(batch_index_path).select(["batch_id"]).sort("batch_id")
    batch_ids = tuple(int(value) for value in batch_index["batch_id"].to_list())
    pred_batch_ids = tuple(
        sorted({int(value) for value in transfer["router_pred_batch_id"].drop_nulls().to_list()})
    )
    if not pred_batch_ids:
        return pl.DataFrame()
    family_columns = select_prior_rpf_context_features(
        context.manifest.feature_columns,
        max_features_per_family=max_features_per_family,
    )
    needed_batch_ids = sorted(
        {
            batch_id
            for pred_batch_id in pred_batch_ids
            for batch_id in prior_batch_ids(batch_ids, pred_batch_id=pred_batch_id, lookback=max(lookbacks))
        }
    )
    batch_summaries = build_prior_rpf_batch_summaries(
        feature_root=context.feature_root,
        batch_ids=needed_batch_ids,
        family_columns=family_columns,
    )
    return aggregate_prior_rpf_context(
        pred_batch_ids=pred_batch_ids,
        all_batch_ids=batch_ids,
        batch_summaries=batch_summaries,
        lookbacks=lookbacks,
        families=tuple(family_columns),
    )


def infer_asset_root_from_inputs(inputs: list[DiagnosticInput]) -> tuple[str, str]:
    for item in inputs:
        config_path = Path(item.run_path) / "router_config.json"
        if not config_path.exists():
            continue
        payload = json.loads(config_path.read_text())
        asset = str(payload.get("asset") or "").strip()
        root = str(payload.get("root") or "").strip()
        if asset and root:
            return asset, root
    raise FileNotFoundError("Cannot infer asset/root because no router_config.json exists in input runs")


def parse_int_tuple(raw: str | tuple[int, ...] | list[int]) -> tuple[int, ...]:
    if isinstance(raw, str):
        values = [value.strip() for value in raw.split(",") if value.strip()]
    else:
        values = list(raw)
    parsed = tuple(dict.fromkeys(int(value) for value in values if int(value) > 0))
    if not parsed:
        raise ValueError("Expected at least one positive integer")
    return parsed


def select_prior_rpf_context_features(
    feature_columns: tuple[str, ...],
    *,
    max_features_per_family: int = DEFAULT_RPF_CONTEXT_MAX_FEATURES_PER_FAMILY,
) -> dict[str, tuple[str, ...]]:
    out: dict[str, tuple[str, ...]] = {}
    limit = max(1, int(max_features_per_family))
    for family, prefixes in FAMILY_PREFIXES.items():
        selected = tuple(feature for feature in feature_columns if feature.startswith(prefixes))[:limit]
        if selected:
            out[family] = selected
    return out


def prior_batch_ids(all_batch_ids: tuple[int, ...], *, pred_batch_id: int, lookback: int) -> tuple[int, ...]:
    eligible = [batch_id for batch_id in all_batch_ids if int(batch_id) < int(pred_batch_id)]
    return tuple(eligible[-max(0, int(lookback)) :])


def build_prior_rpf_batch_summaries(
    *,
    feature_root: Path,
    batch_ids: list[int] | tuple[int, ...],
    family_columns: dict[str, tuple[str, ...]],
) -> dict[int, dict[str, float]]:
    summaries: dict[int, dict[str, float]] = {}
    read_columns = sorted({feature for columns in family_columns.values() for feature in columns})
    if not read_columns:
        return summaries
    for batch_id in batch_ids:
        path = Path(feature_root) / f"batch_{int(batch_id):04d}.parquet"
        if not path.exists():
            continue
        frame = pl.read_parquet(path, columns=read_columns)
        summaries[int(batch_id)] = summarize_rpf_feature_batch(frame, family_columns)
    return summaries


def summarize_rpf_feature_batch(frame: pl.DataFrame, family_columns: dict[str, tuple[str, ...]]) -> dict[str, float]:
    row: dict[str, float] = {}
    for family, columns in family_columns.items():
        available = [col for col in columns if col in frame.columns]
        row[f"{family}__feature_count"] = float(len(available))
        if not available:
            row[f"{family}__mean_abs"] = math.nan
            row[f"{family}__mean"] = math.nan
            continue
        numeric = frame.select([pl.col(col).cast(pl.Float64, strict=False) for col in available])
        means_abs = numeric.select([pl.col(col).abs().mean().alias(col) for col in available]).row(0)
        means = numeric.select([pl.col(col).mean().alias(col) for col in available]).row(0)
        row[f"{family}__mean_abs"] = float(np.nanmean(np.asarray(means_abs, dtype=float)))
        row[f"{family}__mean"] = float(np.nanmean(np.asarray(means, dtype=float)))
    return row


def aggregate_prior_rpf_context(
    *,
    pred_batch_ids: tuple[int, ...],
    all_batch_ids: tuple[int, ...],
    batch_summaries: dict[int, dict[str, float]],
    lookbacks: tuple[int, ...],
    families: tuple[str, ...],
) -> pl.DataFrame:
    rows: list[dict[str, Any]] = []
    for pred_batch_id in pred_batch_ids:
        row: dict[str, Any] = {"router_pred_batch_id": int(pred_batch_id)}
        for lookback in lookbacks:
            prior_ids = prior_batch_ids(all_batch_ids, pred_batch_id=int(pred_batch_id), lookback=int(lookback))
            available_prior_ids = [batch_id for batch_id in prior_ids if batch_id in batch_summaries]
            recent_count = max(1, min(5, len(available_prior_ids)))
            recent_ids = available_prior_ids[-recent_count:]
            for family in families:
                prefix = f"prior_rpf_l{int(lookback)}_{family}"
                mean_abs_values = np.asarray(
                    [
                        batch_summaries[batch_id].get(f"{family}__mean_abs", math.nan)
                        for batch_id in available_prior_ids
                    ],
                    dtype=float,
                )
                recent_mean_abs_values = np.asarray(
                    [
                        batch_summaries[batch_id].get(f"{family}__mean_abs", math.nan)
                        for batch_id in recent_ids
                    ],
                    dtype=float,
                )
                mean_values = np.asarray(
                    [batch_summaries[batch_id].get(f"{family}__mean", math.nan) for batch_id in available_prior_ids],
                    dtype=float,
                )
                feature_counts = np.asarray(
                    [
                        batch_summaries[batch_id].get(f"{family}__feature_count", math.nan)
                        for batch_id in available_prior_ids
                    ],
                    dtype=float,
                )
                row[f"{prefix}_available_batches"] = int(len(available_prior_ids))
                row[f"{prefix}_feature_count"] = safe_nanmean(feature_counts)
                row[f"{prefix}_mean_abs"] = safe_nanmean(mean_abs_values)
                row[f"{prefix}_std_abs"] = safe_nanstd(mean_abs_values)
                row[f"{prefix}_recent_shift_abs"] = safe_subtract(
                    safe_nanmean(recent_mean_abs_values),
                    safe_nanmean(mean_abs_values),
                )
                row[f"{prefix}_mean"] = safe_nanmean(mean_values)
                row[f"{prefix}_std_mean"] = safe_nanstd(mean_values)
        rows.append(row)
    return pl.DataFrame(rows, infer_schema_length=None) if rows else pl.DataFrame()


def safe_nanmean(values: np.ndarray) -> float | None:
    finite = values[np.isfinite(values)]
    return float(finite.mean()) if finite.size else None


def safe_nanstd(values: np.ndarray) -> float | None:
    finite = values[np.isfinite(values)]
    return float(finite.std()) if finite.size else None


def safe_subtract(left: float | None, right: float | None) -> float | None:
    if left is None or right is None:
        return None
    return float(left - right)


def add_transfer_labels(
    df: pl.DataFrame,
    *,
    good_precision_lift: float,
    good_max_false_discovery_rate: float,
    bad_min_false_discovery_rate: float,
) -> pl.DataFrame:
    out = ensure_columns(df, ["predicted_positive_count", "precision_lift", "false_discovery_rate"])
    active = pl.col("predicted_positive_count").fill_null(0) > 0
    good = active & (pl.col("precision_lift").fill_null(0.0) >= good_precision_lift) & (
        pl.col("false_discovery_rate").fill_null(1.0) <= good_max_false_discovery_rate
    )
    bad = active & (pl.col("false_discovery_rate").fill_null(1.0) > bad_min_false_discovery_rate)
    return out.with_columns(
        active.alias("candidate_active"),
        good.alias("candidate_good"),
        bad.alias("candidate_bad"),
        pl.when(good)
        .then(pl.lit("active_precision_lift_and_fdr_pass"))
        .when(bad)
        .then(pl.lit("active_high_false_discovery"))
        .when(active)
        .then(pl.lit("active_neutral_or_mixed"))
        .otherwise(pl.lit("inactive"))
        .alias("candidate_good_reason"),
    )


def safe_context_features_from_transfer_table(df: pl.DataFrame) -> pl.DataFrame:
    forbidden = CURRENT_LABEL_COLUMNS & set(df.columns)
    safe_cols = [col for col in SAFE_CONTEXT_COLUMNS if col in df.columns and col not in forbidden]
    out = df.select(safe_cols)
    leaked = CURRENT_LABEL_COLUMNS & set(out.columns)
    if leaked:
        raise ValueError(f"Safe context contains current prediction label columns: {sorted(leaked)}")
    return out


def active_window_comparison_from_transfer_table(df: pl.DataFrame) -> pl.DataFrame:
    if "candidate_active" not in df.columns:
        return pl.DataFrame()
    keep = [
        "source_block",
        "source_role",
        "side",
        "candidate_name",
        "router_step_idx",
        "router_pred_batch_id",
        "candidate_active",
        "candidate_good",
        "candidate_bad",
        "candidate_good_reason",
        "predicted_positive_count",
        "true_positive_count",
        "false_positive_count",
        "positive_count",
        "base_positive_rate",
        "precision",
        "false_discovery_rate",
        "precision_lift",
        "validation_ranked_signal_quality",
        "validation_precision_lift",
        "validation_predicted_positive_count",
        "validation_false_discovery_rate",
        "batch_state_gate_probability",
        "batch_state_gate_passed",
        "score_mean",
        "score_std",
        "threshold",
        "max_signals_per_batch",
        "past_20_batch_positive_rate_mean",
        "past_60_batch_positive_rate_mean",
        "recent_candidate_precision_lift",
        "recent_candidate_selected_window_row_lift_lcb",
    ]
    return df.filter(pl.col("candidate_active")).select([col for col in keep if col in df.columns])


def summarize_transfer_table(df: pl.DataFrame) -> dict[str, Any]:
    if df.is_empty():
        return {"status": "empty"}
    grouped = (
        df.group_by(["source_block", "side", "candidate_name"])
        .agg(
            pl.len().alias("windows"),
            pl.col("candidate_active").sum().alias("active_windows"),
            pl.col("candidate_good").sum().alias("good_windows"),
            pl.col("candidate_bad").sum().alias("bad_windows"),
            pl.col("predicted_positive_count").fill_null(0).sum().alias("signals"),
            pl.col("true_positive_count").fill_null(0).sum().alias("true_positives"),
            pl.col("false_positive_count").fill_null(0).sum().alias("false_positives"),
            pl.col("positive_count").fill_null(0).sum().alias("positives"),
            pl.col("rows").fill_null(0).sum().alias("rows"),
        )
        .with_columns(
            (pl.col("true_positives") / pl.col("signals")).alias("precision"),
            (pl.col("positives") / pl.col("rows")).alias("base_rate"),
            ((pl.col("true_positives") / pl.col("signals")) / (pl.col("positives") / pl.col("rows"))).alias(
                "precision_lift"
            ),
        )
        .sort(["source_block", "side", "candidate_name"])
    )
    return {
        "rows": df.height,
        "source_blocks": sorted(df["source_block"].unique().to_list()),
        "candidate_summary": grouped.to_dicts(),
    }


def write_transfer_report(path: Path, *, transfer: pl.DataFrame, summary: dict[str, Any]) -> None:
    lines = [
        "# RPF Ranked Signal Transfer Diagnostic",
        "",
        "## Purpose",
        "",
        "Compare completed router blocks and separate prediction-safe context from post-hoc prediction outcomes.",
        "",
        "## Summary",
        "",
        f"- transfer rows: `{transfer.height}`",
        f"- source blocks: `{', '.join(summary.get('source_blocks', []))}`",
        "",
        "## Candidate Aggregates",
        "",
        "| Source | Side | Candidate | Windows | Active | Good | Bad | Signals | TP | FP | Precision | Base Rate | Lift |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in summary.get("candidate_summary", []):
        lines.append(
            "| {source_block} | {side} | {candidate_name} | {windows} | {active_windows} | {good_windows} | "
            "{bad_windows} | {signals} | {true_positives} | {false_positives} | {precision} | {base_rate} | "
            "{precision_lift} |".format(
                **{key: markdown_value(value) for key, value in row.items()}
            )
        )
    lines.extend(
        [
            "",
            "## Interpretation Rules",
            "",
            "- `safe_context_features.parquet` excludes current prediction outcomes and can feed future meta-router research.",
            "- `candidate_transfer_table.parquet` includes post-hoc labels and must not be used as current-window input.",
            "- `candidate_good` means active, precision lift >= configured threshold, and false-discovery rate <= configured threshold.",
            "- `candidate_bad` means active with high false-discovery rate.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n")


def markdown_value(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)


def ensure_columns(df: pl.DataFrame, columns: list[str]) -> pl.DataFrame:
    out = df
    for col in columns:
        if col not in out.columns:
            out = out.with_columns(pl.lit(None).alias(col))
    return out


def drop_duplicate_suffix_columns(df: pl.DataFrame) -> pl.DataFrame:
    drop_cols = [col for col in df.columns if col.endswith("_validation_dup") or col.endswith("_audit_dup") or col.endswith("_regime_dup")]
    return df.drop(drop_cols) if drop_cols else df


def run_root_for_args() -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return OUTPUT_ROOT / f"{timestamp}_rank_signal_transfer_diagnostic"


if __name__ == "__main__":
    raise SystemExit(main())
