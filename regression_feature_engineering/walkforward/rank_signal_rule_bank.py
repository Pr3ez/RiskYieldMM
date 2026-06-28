"""Chronological context-rule bank backtest for RPF ranked-signal candidates.

This command consumes completed ``rank_signal_router`` runs, treats each input
run as one chronological block, trains simple candidate-specific context rules
from prior matured blocks only, and replays them on the next block.  It is an
offline diagnostic for validation-to-prediction transfer; it does not change
the live router.
"""

from __future__ import annotations

import argparse
import math
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import polars as pl

from regression_feature_engineering.walkforward.rank_signal import write_rows_parquet
from regression_feature_engineering.walkforward.rank_signal_meta_router_simulator import (
    CandidateRule,
    aggregate_rows,
    apply_candidate_rules,
    simulate_side_router,
    train_candidate_rules,
)
from regression_feature_engineering.walkforward.rank_signal_transfer_diagnostic import (
    CURRENT_LABEL_COLUMNS,
    DiagnosticInput,
    build_candidate_transfer_table,
    parse_candidate_names,
    safe_context_features_from_transfer_table,
)
from regression_feature_engineering.walkforward.rank_signal_transfer_separator import safe_numeric_feature_columns
from regression_feature_engineering.walkforward.reports import append_event, write_json, write_stage_status
from scripts.project_paths import ensure_project_root_on_path


PROJECT_ROOT = ensure_project_root_on_path(Path(__file__))
OUTPUT_ROOT = PROJECT_ROOT / "test_output" / "rpf_ranked_signal_rule_bank"
TRAIN_BLOCK_LABEL = "__rule_bank_train__"


@dataclass(frozen=True)
class RuleEligibilityConfig:
    min_train_signals: int = 0
    min_train_precision: float = 0.0
    min_train_precision_lcb: float = 0.0
    min_train_lift: float = 0.0
    max_train_false_discovery_rate: float = 1.0
    max_train_active_rate: float = 1.0
    lcb_z: float = 1.0


def main() -> int:
    args = parse_args()
    block_inputs = parse_block_runs(args.block_run)
    candidate_names = parse_candidate_names(args.candidate_names)
    rule_eligibility = RuleEligibilityConfig(
        min_train_signals=int(args.rule_min_train_signals),
        min_train_precision=float(args.rule_min_train_precision),
        min_train_precision_lcb=float(args.rule_min_train_precision_lcb),
        min_train_lift=float(args.rule_min_train_lift),
        max_train_false_discovery_rate=float(args.rule_max_train_fdr),
        max_train_active_rate=float(args.rule_max_train_active_rate),
        lcb_z=float(args.rule_lcb_z),
    )
    side_rule_eligibility = build_side_rule_eligibility(args, rule_eligibility)
    run_root = run_root_for_args()
    run_root.mkdir(parents=True, exist_ok=True)
    events_path = run_root / "events.jsonl"
    append_event(events_path, "stage_start", command="rank_signal_rule_bank")

    transfer = build_candidate_transfer_table(
        block_inputs,
        candidate_names=candidate_names,
        good_precision_lift=float(args.good_precision_lift),
        good_max_false_discovery_rate=float(args.good_max_false_discovery_rate),
        bad_min_false_discovery_rate=float(args.bad_min_false_discovery_rate),
    )
    frame = joined_safe_context_with_labels(transfer)
    feature_columns = safe_numeric_feature_columns(frame)
    folds = build_forward_folds(
        [item.source_block for item in block_inputs],
        min_train_blocks=int(args.min_train_blocks),
        rolling_train_blocks=int(args.rolling_train_blocks),
    )

    rule_rows: list[dict[str, Any]] = []
    rule_candidate_rows: list[dict[str, Any]] = []
    candidate_acceptance_frames: list[pl.DataFrame] = []
    side_window_frames: list[pl.DataFrame] = []
    side_summary_rows: list[dict[str, Any]] = []
    candidate_summary_rows: list[dict[str, Any]] = []

    for fold_idx, train_blocks, test_block in folds:
        train_frame = frame.filter(pl.col("source_block").is_in(train_blocks))
        test_frame = frame.filter(pl.col("source_block") == test_block)
        if train_frame.is_empty() or test_frame.is_empty():
            continue
        train_for_rules = train_frame.with_columns(pl.lit(TRAIN_BLOCK_LABEL).alias("source_block"))
        raw_rules = train_candidate_rules(
            train_for_rules,
            feature_columns=feature_columns,
            train_source_block=TRAIN_BLOCK_LABEL,
            min_train_good_rows=int(args.min_train_good_rows),
            min_train_bad_rows=int(args.min_train_bad_rows),
            min_train_signals=int(args.min_train_signals),
        )
        rules, rule_audit_rows = filter_eligible_rules(
            raw_rules,
            rule_eligibility,
            side_configs=side_rule_eligibility,
        )
        for row in rule_audit_rows:
            rule_candidate_rows.append(
                {
                    "fold_idx": fold_idx,
                    "train_blocks": ",".join(train_blocks),
                    "test_block": test_block,
                    **row,
                }
            )
        for rule in rules:
            eligibility = rule_eligibility_row(
                rule,
                rule_config_for_side(rule.side, rule_eligibility, side_rule_eligibility),
            )
            rule_rows.append(
                {
                    "fold_idx": fold_idx,
                    "train_blocks": ",".join(train_blocks),
                    "test_block": test_block,
                    **asdict(rule),
                    **eligibility,
                }
            )
        acceptance = apply_candidate_rules(test_frame, rules)
        if not acceptance.is_empty():
            acceptance = acceptance.with_columns(
                pl.lit(fold_idx).alias("fold_idx"),
                pl.lit(",".join(train_blocks)).alias("train_blocks"),
                pl.lit(test_block).alias("test_block"),
            )
            candidate_acceptance_frames.append(acceptance)
            candidate_summary_rows.extend(candidate_fold_summary(acceptance, fold_idx, train_blocks, test_block))
        side_windows = simulate_side_router(acceptance)
        if not side_windows.is_empty():
            side_windows = side_windows.with_columns(
                pl.lit(fold_idx).alias("fold_idx"),
                pl.lit(",".join(train_blocks)).alias("train_blocks"),
                pl.lit(test_block).alias("test_block"),
            )
            side_window_frames.append(side_windows)
            side_summary_rows.extend(side_fold_summary(side_windows, fold_idx, train_blocks, test_block))

    candidate_acceptance = concat_or_empty(candidate_acceptance_frames)
    side_windows = concat_or_empty(side_window_frames)
    overall_side_summary = overall_summary(side_windows)
    overall_candidate_summary = overall_candidate_acceptance_summary(candidate_acceptance)

    write_rows_parquet(run_root / "candidate_transfer_table.parquet", transfer.to_dicts())
    write_rows_parquet(run_root / "safe_context_features.parquet", safe_context_features_from_transfer_table(transfer).to_dicts())
    write_rows_parquet(run_root / "rule_bank_rule_candidates.parquet", rule_candidate_rows)
    write_rows_parquet(run_root / "rule_bank_rules.parquet", rule_rows)
    write_rows_parquet(run_root / "rule_bank_candidate_acceptance.parquet", candidate_acceptance.to_dicts())
    write_rows_parquet(run_root / "rule_bank_side_windows.parquet", side_windows.to_dicts())
    write_rows_parquet(run_root / "rule_bank_candidate_summary.parquet", candidate_summary_rows)
    write_rows_parquet(run_root / "rule_bank_side_summary.parquet", side_summary_rows)
    write_rows_parquet(run_root / "rule_bank_overall_side_summary.parquet", overall_side_summary)
    write_rows_parquet(run_root / "rule_bank_overall_candidate_summary.parquet", overall_candidate_summary)
    write_rule_bank_report(
        run_root / "rule_bank_report.md",
        block_inputs=block_inputs,
        folds=folds,
        rule_rows=rule_rows,
        side_summary_rows=side_summary_rows,
        overall_side_summary=overall_side_summary,
    )
    write_json(
        run_root / "rule_bank_config.json",
        {
            "block_runs": [{"source_block": item.source_block, "run": str(item.run_path)} for item in block_inputs],
            "candidate_names": list(candidate_names),
            "min_train_blocks": int(args.min_train_blocks),
            "rolling_train_blocks": int(args.rolling_train_blocks),
            "min_train_good_rows": int(args.min_train_good_rows),
            "min_train_bad_rows": int(args.min_train_bad_rows),
            "min_train_signals": int(args.min_train_signals),
            "good_precision_lift": float(args.good_precision_lift),
            "good_max_false_discovery_rate": float(args.good_max_false_discovery_rate),
            "bad_min_false_discovery_rate": float(args.bad_min_false_discovery_rate),
            "rule_eligibility": asdict(rule_eligibility),
            "side_rule_eligibility": {
                side: asdict(config) for side, config in sorted(side_rule_eligibility.items())
            },
            "feature_columns": feature_columns,
            "excluded_current_label_columns": sorted(CURRENT_LABEL_COLUMNS),
        },
    )
    write_stage_status(
        run_root / "stage_status.json",
        stage="rank_signal_rule_bank",
        status="complete",
        summary={
            "input_blocks": len(block_inputs),
            "folds": len(folds),
            "transfer_rows": transfer.height,
            "feature_count": len(feature_columns),
            "rules": len(rule_rows),
            "rule_candidates": len(rule_candidate_rows),
            "side_window_rows": side_windows.height,
        },
    )
    append_event(events_path, "stage_done", run=str(run_root))
    print(f"[rpf-rule-bank] done run={run_root}", flush=True)
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backtest context-rule transfer across chronological router blocks.")
    parser.add_argument("--block-run", action="append", required=True, help="Chronological block as name=router_run_path.")
    parser.add_argument("--candidate-names", required=True)
    parser.add_argument("--min-train-blocks", type=int, default=1)
    parser.add_argument(
        "--rolling-train-blocks",
        type=int,
        default=0,
        help="Use only this many prior blocks for training. 0 means all prior blocks.",
    )
    parser.add_argument("--min-train-good-rows", type=int, default=2)
    parser.add_argument("--min-train-bad-rows", type=int, default=2)
    parser.add_argument("--min-train-signals", type=int, default=3)
    parser.add_argument("--good-precision-lift", type=float, default=1.20)
    parser.add_argument("--good-max-false-discovery-rate", type=float, default=0.50)
    parser.add_argument("--bad-min-false-discovery-rate", type=float, default=0.60)
    parser.add_argument("--rule-min-train-signals", type=int, default=0)
    parser.add_argument("--rule-min-train-precision", type=float, default=0.0)
    parser.add_argument("--rule-min-train-precision-lcb", type=float, default=0.0)
    parser.add_argument("--rule-min-train-lift", type=float, default=0.0)
    parser.add_argument("--rule-max-train-fdr", type=float, default=1.0)
    parser.add_argument("--rule-max-train-active-rate", type=float, default=1.0)
    parser.add_argument("--rule-lcb-z", type=float, default=1.0)
    add_side_rule_args(parser, "up")
    add_side_rule_args(parser, "down")
    return parser.parse_args()


def add_side_rule_args(parser: argparse.ArgumentParser, side: str) -> None:
    prefix = f"{side}-rule"
    parser.add_argument(f"--{prefix}-min-train-signals", type=int, default=None)
    parser.add_argument(f"--{prefix}-min-train-precision", type=float, default=None)
    parser.add_argument(f"--{prefix}-min-train-precision-lcb", type=float, default=None)
    parser.add_argument(f"--{prefix}-min-train-lift", type=float, default=None)
    parser.add_argument(f"--{prefix}-max-train-fdr", type=float, default=None)
    parser.add_argument(f"--{prefix}-max-train-active-rate", type=float, default=None)
    parser.add_argument(f"--{prefix}-lcb-z", type=float, default=None)


def build_side_rule_eligibility(
    args: argparse.Namespace,
    default_config: RuleEligibilityConfig,
) -> dict[str, RuleEligibilityConfig]:
    configs: dict[str, RuleEligibilityConfig] = {}
    for side in ("up", "down"):
        overrides = {
            "min_train_signals": getattr(args, f"{side}_rule_min_train_signals"),
            "min_train_precision": getattr(args, f"{side}_rule_min_train_precision"),
            "min_train_precision_lcb": getattr(args, f"{side}_rule_min_train_precision_lcb"),
            "min_train_lift": getattr(args, f"{side}_rule_min_train_lift"),
            "max_train_false_discovery_rate": getattr(args, f"{side}_rule_max_train_fdr"),
            "max_train_active_rate": getattr(args, f"{side}_rule_max_train_active_rate"),
            "lcb_z": getattr(args, f"{side}_rule_lcb_z"),
        }
        if all(value is None for value in overrides.values()):
            continue
        configs[side] = RuleEligibilityConfig(
            min_train_signals=int(
                default_config.min_train_signals
                if overrides["min_train_signals"] is None
                else overrides["min_train_signals"]
            ),
            min_train_precision=float(
                default_config.min_train_precision
                if overrides["min_train_precision"] is None
                else overrides["min_train_precision"]
            ),
            min_train_precision_lcb=float(
                default_config.min_train_precision_lcb
                if overrides["min_train_precision_lcb"] is None
                else overrides["min_train_precision_lcb"]
            ),
            min_train_lift=float(
                default_config.min_train_lift
                if overrides["min_train_lift"] is None
                else overrides["min_train_lift"]
            ),
            max_train_false_discovery_rate=float(
                default_config.max_train_false_discovery_rate
                if overrides["max_train_false_discovery_rate"] is None
                else overrides["max_train_false_discovery_rate"]
            ),
            max_train_active_rate=float(
                default_config.max_train_active_rate
                if overrides["max_train_active_rate"] is None
                else overrides["max_train_active_rate"]
            ),
            lcb_z=float(default_config.lcb_z if overrides["lcb_z"] is None else overrides["lcb_z"]),
        )
    return configs


def parse_block_runs(raw_items: list[str]) -> list[DiagnosticInput]:
    out: list[DiagnosticInput] = []
    seen: set[str] = set()
    for raw in raw_items:
        if "=" not in raw:
            raise ValueError(f"--block-run must use name=path format, got: {raw}")
        name, path = raw.split("=", 1)
        source_block = sanitize_block_name(name)
        if source_block in seen:
            raise ValueError(f"Duplicate block name: {source_block}")
        seen.add(source_block)
        run_path = Path(path)
        if not run_path.exists():
            raise FileNotFoundError(f"Router block path does not exist: {run_path}")
        out.append(DiagnosticInput(run_path=run_path, source_block=source_block, source_role="chronological_block"))
    if len(out) < 2:
        raise ValueError("At least two --block-run inputs are required")
    return out


def sanitize_block_name(raw: str) -> str:
    out = "".join(ch if ch.isalnum() or ch in "_-" else "_" for ch in str(raw).strip())
    if not out:
        raise ValueError("Empty block name")
    return out


def joined_safe_context_with_labels(transfer: pl.DataFrame) -> pl.DataFrame:
    safe = safe_context_features_from_transfer_table(transfer)
    leaked = set(safe.columns) & CURRENT_LABEL_COLUMNS
    if leaked:
        raise ValueError(f"safe context contains current-label columns: {sorted(leaked)}")
    keys = [
        "source_block",
        "source_role",
        "source_run",
        "side",
        "candidate_name",
        "router_step_idx",
        "router_pred_batch_id",
    ]
    label_cols = [
        "candidate_active",
        "candidate_good",
        "candidate_bad",
        "candidate_good_reason",
        "predicted_positive_count",
        "true_positive_count",
        "false_positive_count",
        "positive_count",
        "negative_count",
        "rows",
        "precision",
        "false_discovery_rate",
        "precision_lift",
        "base_positive_rate",
    ]
    labels = transfer.select([col for col in [*keys, *label_cols] if col in transfer.columns])
    return safe.join(labels, on=[col for col in keys if col in safe.columns and col in labels.columns], how="inner")


def build_forward_folds(
    block_names: list[str],
    *,
    min_train_blocks: int,
    rolling_train_blocks: int,
) -> list[tuple[int, list[str], str]]:
    if min_train_blocks < 1:
        raise ValueError("--min-train-blocks must be >= 1")
    folds: list[tuple[int, list[str], str]] = []
    for idx in range(min_train_blocks, len(block_names)):
        prior = block_names[:idx]
        if rolling_train_blocks > 0:
            prior = prior[-rolling_train_blocks:]
        folds.append((len(folds), prior, block_names[idx]))
    return folds


def candidate_fold_summary(
    acceptance: pl.DataFrame,
    fold_idx: int,
    train_blocks: list[str],
    test_block: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key in acceptance.select(["side", "candidate_name"]).unique().sort(["side", "candidate_name"]).to_dicts():
        subset = acceptance.filter(
            (pl.col("side") == key["side"])
            & (pl.col("candidate_name") == key["candidate_name"])
            & pl.col("meta_accept").fill_null(False)
        )
        rows.append(
            {
                "fold_idx": fold_idx,
                "train_blocks": ",".join(train_blocks),
                "test_block": test_block,
                "side": key["side"],
                "candidate_name": key["candidate_name"],
                **aggregate_rows(subset),
            }
        )
    return rows


def side_fold_summary(
    side_windows: pl.DataFrame,
    fold_idx: int,
    train_blocks: list[str],
    test_block: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key in side_windows.select(["side"]).unique().sort("side").to_dicts():
        subset = side_windows.filter(pl.col("side") == key["side"])
        rows.append(
            {
                "fold_idx": fold_idx,
                "train_blocks": ",".join(train_blocks),
                "test_block": test_block,
                "side": key["side"],
                "candidate_name": "selected_side_router",
                **aggregate_rows(subset),
            }
        )
    return rows


def overall_summary(side_windows: pl.DataFrame) -> list[dict[str, Any]]:
    if side_windows.is_empty():
        return []
    rows: list[dict[str, Any]] = []
    for key in side_windows.select(["side"]).unique().sort("side").to_dicts():
        subset = side_windows.filter(pl.col("side") == key["side"])
        rows.append({"side": key["side"], "candidate_name": "selected_side_router", **aggregate_rows(subset)})
    return rows


def overall_candidate_acceptance_summary(acceptance: pl.DataFrame) -> list[dict[str, Any]]:
    if acceptance.is_empty():
        return []
    rows: list[dict[str, Any]] = []
    for key in acceptance.select(["side", "candidate_name"]).unique().sort(["side", "candidate_name"]).to_dicts():
        subset = acceptance.filter(
            (pl.col("side") == key["side"])
            & (pl.col("candidate_name") == key["candidate_name"])
            & pl.col("meta_accept").fill_null(False)
        )
        rows.append({"side": key["side"], "candidate_name": key["candidate_name"], **aggregate_rows(subset)})
    return rows


def concat_or_empty(frames: list[pl.DataFrame]) -> pl.DataFrame:
    if not frames:
        return pl.DataFrame()
    return pl.concat(frames, how="diagonal_relaxed")


def filter_eligible_rules(
    rules: list[CandidateRule],
    config: RuleEligibilityConfig,
    *,
    side_configs: dict[str, RuleEligibilityConfig] | None = None,
) -> tuple[list[CandidateRule], list[dict[str, Any]]]:
    eligible: list[CandidateRule] = []
    rows: list[dict[str, Any]] = []
    for rule in rules:
        rule_config = rule_config_for_side(rule.side, config, side_configs or {})
        row = rule_eligibility_row(rule, rule_config)
        rows.append({**asdict(rule), **row})
        if bool(row["rule_eligible"]):
            eligible.append(rule)
    return eligible, rows


def rule_config_for_side(
    side: str,
    default_config: RuleEligibilityConfig,
    side_configs: dict[str, RuleEligibilityConfig],
) -> RuleEligibilityConfig:
    return side_configs.get(str(side), default_config)


def rule_eligibility_row(rule: CandidateRule, config: RuleEligibilityConfig) -> dict[str, Any]:
    signals = int(rule.train_signals)
    precision = finite_or_none(rule.train_precision)
    lift = finite_or_none(rule.train_lift)
    fdr = finite_or_none(rule.train_false_discovery_rate)
    active_rate = safe_ratio(rule.train_accepted_windows, rule.train_windows)
    successes = int(round(float(precision or 0.0) * float(signals))) if signals > 0 else 0
    precision_lcb = wilson_lower_bound(successes, signals, z=float(config.lcb_z))
    reasons: list[str] = []
    if signals < int(config.min_train_signals):
        reasons.append("low_train_signals")
    if precision is None or precision < float(config.min_train_precision):
        reasons.append("low_train_precision")
    if precision_lcb is None or precision_lcb < float(config.min_train_precision_lcb):
        reasons.append("low_train_precision_lcb")
    if lift is None or lift < float(config.min_train_lift):
        reasons.append("low_train_lift")
    if fdr is None or fdr > float(config.max_train_false_discovery_rate):
        reasons.append("high_train_fdr")
    if active_rate is None or active_rate > float(config.max_train_active_rate):
        reasons.append("high_train_active_rate")
    return {
        "rule_eligible": not reasons,
        "rule_reject_reasons": ",".join(reasons),
        "train_precision_lcb": precision_lcb,
        "train_active_rate": active_rate,
        "rule_min_train_signals": int(config.min_train_signals),
        "rule_min_train_precision": float(config.min_train_precision),
        "rule_min_train_precision_lcb": float(config.min_train_precision_lcb),
        "rule_min_train_lift": float(config.min_train_lift),
        "rule_max_train_fdr": float(config.max_train_false_discovery_rate),
        "rule_max_train_active_rate": float(config.max_train_active_rate),
        "rule_lcb_z": float(config.lcb_z),
    }


def wilson_lower_bound(successes: int, trials: int, *, z: float) -> float | None:
    if trials <= 0:
        return None
    n = float(trials)
    phat = float(successes) / n
    z2 = float(z) ** 2
    denominator = 1.0 + z2 / n
    centre = phat + z2 / (2.0 * n)
    margin = float(z) * math.sqrt((phat * (1.0 - phat) + z2 / (4.0 * n)) / n)
    return (centre - margin) / denominator


def finite_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        out = float(value)
    except Exception:
        return None
    return out if math.isfinite(out) else None


def safe_ratio(numerator: float | int | None, denominator: float | int | None) -> float | None:
    if numerator is None or denominator is None or float(denominator) == 0.0:
        return None
    return float(numerator) / float(denominator)


def write_rule_bank_report(
    path: Path,
    *,
    block_inputs: list[DiagnosticInput],
    folds: list[tuple[int, list[str], str]],
    rule_rows: list[dict[str, Any]],
    side_summary_rows: list[dict[str, Any]],
    overall_side_summary: list[dict[str, Any]],
) -> None:
    lines = [
        "# RPF Ranked Signal Rule Bank",
        "",
        "## Purpose",
        "",
        "Train context rules on prior matured router blocks and replay them on the next chronological block.",
        "",
        "## Input Blocks",
        "",
        "| Order | Block | Run |",
        "|---:|---|---|",
    ]
    for idx, item in enumerate(block_inputs):
        lines.append(f"| {idx} | `{item.source_block}` | `{item.run_path}` |")
    lines.extend(["", "## Forward Folds", "", "| Fold | Train Blocks | Test Block |", "|---:|---|---|"])
    for fold_idx, train_blocks, test_block in folds:
        lines.append(f"| {fold_idx} | `{', '.join(train_blocks)}` | `{test_block}` |")
    lines.extend(
        [
            "",
            "## Rules",
            "",
            "| Fold | Side | Candidate | Feature | Direction | Threshold | Train Signals | Train Precision | Train Precision LCB | Train Lift | Train FDR | Active Rate |",
            "|---:|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in rule_rows:
        lines.append(
            "| {fold_idx} | {side} | {candidate_name} | `{feature}` | {direction} | {threshold} | "
            "{train_signals} | {train_precision} | {train_precision_lcb} | {train_lift} | "
            "{train_false_discovery_rate} | {train_active_rate} |".format(
                fold_idx=row.get("fold_idx"),
                side=row.get("side"),
                candidate_name=row.get("candidate_name"),
                feature=row.get("feature"),
                direction=row.get("direction"),
                threshold=fmt(row.get("threshold")),
                train_signals=row.get("train_signals"),
                train_precision=fmt(row.get("train_precision")),
                train_precision_lcb=fmt(row.get("train_precision_lcb")),
                train_lift=fmt(row.get("train_lift")),
                train_false_discovery_rate=fmt(row.get("train_false_discovery_rate")),
                train_active_rate=fmt(row.get("train_active_rate")),
            )
        )
    lines.extend(["", "## Fold Side Summary", ""])
    lines.extend(summary_table(side_summary_rows, include_fold=True))
    lines.extend(["", "## Overall Side Summary", ""])
    lines.extend(summary_table(overall_side_summary, include_fold=False))
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- This is an offline diagnostic only.",
            "- Each fold trains rules from prior matured blocks only.",
            "- Current test-block labels are used only for post-hoc scoring.",
            "- Rules that fail forward blocks should not be wired into the live router.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n")


def summary_table(rows: list[dict[str, Any]], *, include_fold: bool) -> list[str]:
    if include_fold:
        lines = [
            "| Fold | Test Block | Side | Signals | TP | FP | Precision | Base Rate | Lift | FDR | Active Rate |",
            "|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    else:
        lines = [
            "| Side | Signals | TP | FP | Precision | Base Rate | Lift | FDR | Active Rate |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    for row in rows:
        if include_fold:
            lines.append(
                "| {fold_idx} | {test_block} | {side} | {signals} | {true_positives} | {false_positives} | "
                "{precision} | {base_rate} | {lift} | {false_discovery_rate} | {active_rate} |".format(
                    fold_idx=row.get("fold_idx"),
                    test_block=row.get("test_block"),
                    side=row.get("side"),
                    signals=row.get("signals"),
                    true_positives=row.get("true_positives"),
                    false_positives=row.get("false_positives"),
                    precision=fmt(row.get("precision")),
                    base_rate=fmt(row.get("base_rate")),
                    lift=fmt(row.get("lift")),
                    false_discovery_rate=fmt(row.get("false_discovery_rate")),
                    active_rate=fmt(row.get("active_rate")),
                )
            )
        else:
            lines.append(
                "| {side} | {signals} | {true_positives} | {false_positives} | {precision} | {base_rate} | "
                "{lift} | {false_discovery_rate} | {active_rate} |".format(
                    side=row.get("side"),
                    signals=row.get("signals"),
                    true_positives=row.get("true_positives"),
                    false_positives=row.get("false_positives"),
                    precision=fmt(row.get("precision")),
                    base_rate=fmt(row.get("base_rate")),
                    lift=fmt(row.get("lift")),
                    false_discovery_rate=fmt(row.get("false_discovery_rate")),
                    active_rate=fmt(row.get("active_rate")),
                )
            )
    return lines


def fmt(value: Any) -> str:
    if value is None:
        return "-"
    try:
        out = float(value)
    except Exception:
        return str(value)
    return f"{out:.6g}"


def run_root_for_args() -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return OUTPUT_ROOT / f"{timestamp}_rank_signal_rule_bank"


if __name__ == "__main__":
    raise SystemExit(main())
