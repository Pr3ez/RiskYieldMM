"""Chronological row-filter rule bank for ranked-signal diagnostics.

The command consumes a completed ``rank_signal_row_diagnostic`` run.  It learns
simple one-feature filters from prior matured signal rows, applies eligibility
gates, and replays eligible filters on the next chronological block.
"""

from __future__ import annotations

import argparse
import math
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

from regression_feature_engineering.walkforward.rank_signal import write_rows_parquet
from regression_feature_engineering.walkforward.rank_signal_rule_bank import wilson_lower_bound
from regression_feature_engineering.walkforward.rank_signal_row_diagnostic import OUTCOME_COLUMNS
from regression_feature_engineering.walkforward.rank_signal_transfer_separator import markdown_value
from regression_feature_engineering.walkforward.reports import append_event, write_json, write_stage_status
from scripts.project_paths import ensure_project_root_on_path


PROJECT_ROOT = ensure_project_root_on_path(Path(__file__))
OUTPUT_ROOT = PROJECT_ROOT / "test_output" / "rpf_ranked_signal_row_rule_bank"

IDENTITY_COLUMNS = {
    "source_run",
    "source_block",
    "side",
    "candidate_name",
    "router_step_idx",
    "router_pred_batch_id",
    "step_idx",
    "pred_batch_id",
    "timestamp",
    "batch_id",
    "target_col",
    "split",
    "candidate_status",
    "candidate_fail_reasons",
    "decision_policy",
    "score_source",
}


@dataclass(frozen=True)
class RowRule:
    fold_idx: int
    train_blocks: str
    test_block: str
    side: str
    candidate_name: str
    feature: str
    direction: str
    threshold: float
    train_rows: int
    train_accepted_rows: int
    train_tp: int
    train_fp: int
    train_precision: float
    train_base_precision: float
    train_lift: float
    train_false_discovery_rate: float
    train_precision_lcb: float | None
    train_accepted_rate: float
    rule_score: float
    feature_auc: float | None = None
    feature_auc_abs: float | None = None
    feature_auc_direction: str | None = None
    direction_agreement: bool | None = None
    directional_lcb_score: float | None = None


@dataclass(frozen=True)
class RowRuleEligibilityConfig:
    min_train_signals: int = 5
    min_train_precision: float = 0.60
    min_train_precision_lcb: float = 0.35
    min_train_lift: float = 1.20
    max_train_false_discovery_rate: float = 0.40
    max_train_accepted_rate: float = 0.50
    lcb_z: float = 1.0
    min_feature_auc_abs: float = 0.0
    require_feature_direction_agreement: bool = False
    allowed_directions: tuple[str, ...] = ()


@dataclass(frozen=True)
class RowRuleReliabilityConfig:
    min_history_folds: int = 1
    min_signals: int = 8
    min_precision_lcb: float = 0.50
    max_false_discovery_rate: float = 0.50
    lcb_z: float = 1.0
    key_mode: str = "feature_direction"
    warmup_mode: str = "no_signal"
    lookback_folds: int = 0


def main() -> int:
    args = parse_args()
    row_diagnostic_run = Path(args.row_diagnostic_run)
    run_root = run_root_for_args()
    run_root.mkdir(parents=True, exist_ok=True)
    events_path = run_root / "events.jsonl"
    append_event(events_path, "stage_start", command="rank_signal_row_rule_bank")

    frame = load_row_rule_frame(
        row_diagnostic_run,
        side=str(args.side),
        candidate_names=parse_optional_csv(args.candidate_names),
    )
    feature_columns = safe_numeric_feature_columns(frame)
    blocks = chronological_source_blocks(frame)
    folds = build_forward_folds(blocks, min_train_blocks=int(args.min_train_blocks), rolling_train_blocks=int(args.rolling_train_blocks))
    config = RowRuleEligibilityConfig(
        min_train_signals=int(args.rule_min_train_signals),
        min_train_precision=float(args.rule_min_train_precision),
        min_train_precision_lcb=float(args.rule_min_train_precision_lcb),
        min_train_lift=float(args.rule_min_train_lift),
        max_train_false_discovery_rate=float(args.rule_max_train_fdr),
        max_train_accepted_rate=float(args.rule_max_train_accepted_rate),
        lcb_z=float(args.rule_lcb_z),
        min_feature_auc_abs=float(args.rule_min_feature_auc_abs),
        require_feature_direction_agreement=bool(args.rule_require_feature_direction_agreement),
        allowed_directions=parse_optional_csv(args.rule_allowed_directions),
    )
    reliability_config = RowRuleReliabilityConfig(
        min_history_folds=int(args.rule_reliability_min_history_folds),
        min_signals=int(args.rule_reliability_min_signals),
        min_precision_lcb=float(args.rule_reliability_min_precision_lcb),
        max_false_discovery_rate=float(args.rule_reliability_max_fdr),
        lcb_z=float(args.rule_reliability_lcb_z),
        key_mode=str(args.rule_reliability_key),
        warmup_mode=str(args.rule_reliability_warmup_mode),
        lookback_folds=int(args.rule_reliability_lookback_folds),
    )
    quantiles = parse_float_tuple(args.rule_quantiles)

    candidate_rows: list[dict[str, Any]] = []
    rule_rows: list[dict[str, Any]] = []
    rule_acceptance_rows: list[dict[str, Any]] = []
    shadow_rule_acceptance_rows: list[dict[str, Any]] = []
    selection_audit_rows: list[dict[str, Any]] = []
    reliability_snapshot_rows: list[dict[str, Any]] = []
    union_frames: list[pl.DataFrame] = []
    shadow_history_rows: list[dict[str, Any]] = []
    for fold_idx, train_blocks, test_block in folds:
        train = frame.filter(pl.col("source_block").is_in(train_blocks))
        test = frame.filter(pl.col("source_block") == test_block)
        if train.is_empty() or test.is_empty():
            continue
        raw_rules = train_row_rules(
            train,
            feature_columns=feature_columns,
            fold_idx=fold_idx,
            train_blocks=train_blocks,
            test_block=test_block,
            quantiles=quantiles,
            min_train_tp_rows=int(args.min_train_tp_rows),
            min_train_fp_rows=int(args.min_train_fp_rows),
            lcb_z=float(config.lcb_z),
        )
        eligible_rules, audit_rows = filter_eligible_row_rules(raw_rules, config)
        shadow_rows = replay_rules(test, eligible_rules, rule_level=True)
        for row in shadow_rows:
            shadow_rule_acceptance_rows.append(row | {"shadow_rule": True})
        reliability_source_rows = recent_shadow_history_rows(shadow_history_rows, reliability_config.lookback_folds)
        reliability_rows = rule_reliability_rows(reliability_source_rows, reliability_config)
        reliability_snapshot_rows.extend([row | {"fold_idx": fold_idx, "test_block": str(test_block)} for row in reliability_rows])
        if str(args.row_rule_selection_mode) == "prequential_reliability_v1":
            selected_rules, audit = select_prequential_reliable_rules(
                eligible_rules,
                reliability_rows=reliability_rows,
                config=reliability_config,
                max_rules_per_candidate=int(args.max_rules_per_candidate),
                fallback_selection_score=str(args.rule_selection_score),
            )
            selection_audit_rows.extend(audit)
        else:
            selected_rules = limit_rules_per_candidate(
                eligible_rules,
                max_rules_per_candidate=int(args.max_rules_per_candidate),
                selection_score=str(args.rule_selection_score),
            )
            selection_audit_rows.extend(
                [
                    selection_audit_row(
                        rule,
                        selected=rule in selected_rules,
                        selection_mode=str(args.row_rule_selection_mode),
                        reliability=None,
                        reject_reasons=[] if rule in selected_rules else ["not_top_static_rule"],
                        selection_score=row_selection_score(rule, str(args.rule_selection_score)),
                    )
                    for rule in eligible_rules
                ]
            )
        candidate_rows.extend(audit_rows)
        rule_rows.extend([asdict(rule) | row_rule_eligibility_row(rule, config) for rule in selected_rules])
        rule_acceptance_rows.extend(replay_rules(test, selected_rules, rule_level=True))
        union = replay_rules_union(test, selected_rules)
        if not union.is_empty():
            union_frames.append(union)
        shadow_history_rows.extend(shadow_rows)

    union_acceptance = pl.concat(union_frames, how="diagonal_relaxed") if union_frames else pl.DataFrame()
    fold_summary = summarize_acceptance(union_acceptance, by=["fold_idx", "train_blocks", "test_block", "side", "candidate_name"])
    overall_summary = summarize_acceptance(union_acceptance, by=["side", "candidate_name"])
    fold_comparison = compare_fold_summary_with_raw(frame, fold_summary)
    overall_comparison = compare_overall_summary_with_raw(frame, fold_summary, overall_summary)

    write_rows_parquet(run_root / "row_rule_bank_rule_candidates.parquet", candidate_rows)
    write_rows_parquet(run_root / "row_rule_bank_rules.parquet", rule_rows)
    write_rows_parquet(run_root / "row_rule_bank_rule_acceptance.parquet", rule_acceptance_rows)
    write_rows_parquet(run_root / "row_rule_bank_shadow_rule_acceptance.parquet", shadow_rule_acceptance_rows)
    write_rows_parquet(run_root / "row_rule_bank_rule_reliability.parquet", reliability_snapshot_rows)
    write_rows_parquet(run_root / "row_rule_bank_selection_audit.parquet", selection_audit_rows)
    write_rows_parquet(run_root / "row_rule_bank_candidate_acceptance.parquet", union_acceptance.to_dicts())
    write_rows_parquet(run_root / "row_rule_bank_fold_summary.parquet", fold_summary)
    write_rows_parquet(run_root / "row_rule_bank_overall_summary.parquet", overall_summary)
    write_rows_parquet(run_root / "row_rule_bank_fold_comparison.parquet", fold_comparison)
    write_rows_parquet(run_root / "row_rule_bank_overall_comparison.parquet", overall_comparison)
    write_row_rule_bank_report(
        run_root / "row_rule_bank_report.md",
        row_diagnostic_run=row_diagnostic_run,
        blocks=blocks,
        folds=folds,
        rule_rows=rule_rows,
        fold_summary=fold_summary,
        overall_summary=overall_summary,
        fold_comparison=fold_comparison,
        overall_comparison=overall_comparison,
    )
    write_json(
        run_root / "row_rule_bank_config.json",
        {
            "row_diagnostic_run": str(row_diagnostic_run),
            "side": str(args.side),
            "candidate_names": list(parse_optional_csv(args.candidate_names)),
            "blocks": blocks,
            "folds": [{"fold_idx": idx, "train_blocks": train, "test_block": test} for idx, train, test in folds],
            "rule_quantiles": quantiles,
            "max_rules_per_candidate": int(args.max_rules_per_candidate),
            "row_rule_selection_mode": str(args.row_rule_selection_mode),
            "rule_selection_score": str(args.rule_selection_score),
            "rule_eligibility": asdict(config),
            "rule_reliability": asdict(reliability_config),
            "feature_columns": feature_columns,
        },
    )
    write_stage_status(
        run_root / "stage_status.json",
        stage="rank_signal_row_rule_bank",
        status="complete",
        summary={
            "row_diagnostic_run": str(row_diagnostic_run),
            "input_rows": frame.height,
            "feature_count": len(feature_columns),
            "folds": len(folds),
            "rule_candidates": len(candidate_rows),
            "rules": len(rule_rows),
            "shadow_rule_acceptance_rows": len(shadow_rule_acceptance_rows),
            "selection_audit_rows": len(selection_audit_rows),
            "accepted_rows": union_acceptance.height,
            "fold_comparison_rows": len(fold_comparison),
            "overall_comparison_rows": len(overall_comparison),
        },
    )
    append_event(events_path, "stage_done", run=str(run_root))
    print(f"[rpf-row-rule-bank] done run={run_root}", flush=True)
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Replay row-level signal filters across chronological blocks.")
    parser.add_argument("--row-diagnostic-run", required=True)
    parser.add_argument("--side", choices=("up", "down"), default="down")
    parser.add_argument("--candidate-names", default="")
    parser.add_argument("--min-train-blocks", type=int, default=1)
    parser.add_argument("--rolling-train-blocks", type=int, default=1)
    parser.add_argument("--min-train-tp-rows", type=int, default=2)
    parser.add_argument("--min-train-fp-rows", type=int, default=2)
    parser.add_argument("--rule-quantiles", default="0.2,0.3,0.4,0.5,0.6,0.7,0.75,0.8,0.85,0.9")
    parser.add_argument("--rule-min-train-signals", type=int, default=5)
    parser.add_argument("--rule-min-train-precision", type=float, default=0.60)
    parser.add_argument("--rule-min-train-precision-lcb", type=float, default=0.35)
    parser.add_argument("--rule-min-train-lift", type=float, default=1.20)
    parser.add_argument("--rule-max-train-fdr", type=float, default=0.40)
    parser.add_argument("--rule-max-train-accepted-rate", type=float, default=0.50)
    parser.add_argument("--rule-lcb-z", type=float, default=1.0)
    parser.add_argument("--rule-min-feature-auc-abs", type=float, default=0.0)
    parser.add_argument("--rule-require-feature-direction-agreement", action="store_true")
    parser.add_argument(
        "--rule-allowed-directions",
        default="",
        help="Optional comma-separated row-rule directions to keep, e.g. higher_good. Empty keeps both directions.",
    )
    parser.add_argument(
        "--row-rule-selection-mode",
        choices=("static", "prequential_reliability_v1"),
        default="static",
        help="How to choose from eligible row rules before replaying the next block.",
    )
    parser.add_argument(
        "--rule-selection-score",
        choices=("rule_score", "directional_lcb_v1"),
        default="rule_score",
        help="Train-only score used when limiting eligible rules per candidate.",
    )
    parser.add_argument(
        "--rule-reliability-key",
        choices=("feature_direction", "family_direction"),
        default="feature_direction",
        help="Key used to mature prior shadow rule performance.",
    )
    parser.add_argument("--rule-reliability-min-history-folds", type=int, default=1)
    parser.add_argument("--rule-reliability-min-signals", type=int, default=8)
    parser.add_argument("--rule-reliability-min-precision-lcb", type=float, default=0.50)
    parser.add_argument("--rule-reliability-max-fdr", type=float, default=0.50)
    parser.add_argument("--rule-reliability-lcb-z", type=float, default=1.0)
    parser.add_argument("--rule-reliability-warmup-mode", choices=("no_signal", "static"), default="no_signal")
    parser.add_argument(
        "--rule-reliability-lookback-folds",
        type=int,
        default=0,
        help="Use only the last N matured folds for row-rule reliability; 0 keeps all prior history.",
    )
    parser.add_argument("--max-rules-per-candidate", type=int, default=1)
    return parser.parse_args()


def load_row_rule_frame(row_diagnostic_run: Path, *, side: str, candidate_names: tuple[str, ...]) -> pl.DataFrame:
    safe_path = row_diagnostic_run / "row_safe_context_features.parquet"
    transfer_path = row_diagnostic_run / "row_signal_transfer_table.parquet"
    if not safe_path.exists() or not transfer_path.exists():
        raise FileNotFoundError(f"Missing row diagnostic artifacts in {row_diagnostic_run}")
    safe = pl.read_parquet(safe_path)
    if set(safe.columns) & OUTCOME_COLUMNS:
        raise ValueError("row_safe_context_features leaked outcome columns")
    transfer = pl.read_parquet(transfer_path)
    keys = [col for col in JOIN_KEYS if col in safe.columns and col in transfer.columns]
    labels = transfer.select([*keys, "signal_tp", "signal_fp", "signal_outcome"])
    out = safe.join(labels, on=keys, how="inner").filter(pl.col("side") == side)
    if candidate_names:
        out = out.filter(pl.col("candidate_name").is_in(candidate_names))
    if out.is_empty():
        raise ValueError("No rows matched requested side/candidates")
    return out


JOIN_KEYS = [
    "source_run",
    "source_block",
    "side",
    "candidate_name",
    "router_step_idx",
    "router_pred_batch_id",
    "timestamp",
    "batch_id",
]


def safe_numeric_feature_columns(df: pl.DataFrame) -> list[str]:
    allowed = {
        pl.Boolean,
        pl.Int8,
        pl.Int16,
        pl.Int32,
        pl.Int64,
        pl.UInt8,
        pl.UInt16,
        pl.UInt32,
        pl.UInt64,
        pl.Float32,
        pl.Float64,
    }
    blocked = IDENTITY_COLUMNS | OUTCOME_COLUMNS | {"signal_tp", "signal_fp", "decision", "raw_decision_before_batch_state_gate"}
    return [name for name, dtype in df.schema.items() if name not in blocked and dtype in allowed]


def chronological_source_blocks(df: pl.DataFrame) -> list[str]:
    return sorted([str(value) for value in df["source_block"].unique().to_list()], key=block_sort_key, reverse=True)


def block_sort_key(block: str) -> int:
    if block == "latest":
        return 0
    if block == "middle":
        return 120
    match = re.match(r"offset(\d+)$", str(block))
    if match:
        return int(match.group(1))
    match = re.match(r"block(\d+)$", str(block))
    if match:
        return -int(match.group(1))
    return 0


def build_forward_folds(blocks: list[str], *, min_train_blocks: int, rolling_train_blocks: int) -> list[tuple[int, list[str], str]]:
    folds: list[tuple[int, list[str], str]] = []
    for test_idx in range(max(1, int(min_train_blocks)), len(blocks)):
        train_blocks = list(blocks[:test_idx])
        if int(rolling_train_blocks) > 0:
            train_blocks = train_blocks[-int(rolling_train_blocks) :]
        folds.append((len(folds), train_blocks, blocks[test_idx]))
    return folds


def train_row_rules(
    train: pl.DataFrame,
    *,
    feature_columns: list[str],
    fold_idx: int,
    train_blocks: list[str],
    test_block: str,
    quantiles: tuple[float, ...],
    min_train_tp_rows: int,
    min_train_fp_rows: int,
    lcb_z: float = 1.0,
) -> list[RowRule]:
    rules: list[RowRule] = []
    grouped = train.partition_by(["side", "candidate_name"], as_dict=True)
    for key, frame in grouped.items():
        side, candidate = key if isinstance(key, tuple) else key
        tp = frame["signal_tp"].fill_null(False).to_numpy().astype(bool)
        fp = frame["signal_fp"].fill_null(False).to_numpy().astype(bool)
        if int(tp.sum()) < int(min_train_tp_rows) or int(fp.sum()) < int(min_train_fp_rows):
            continue
        train_base_precision = float(tp.sum() / frame.height) if frame.height else 0.0
        feature_auc_by_name = train_feature_auc(frame, feature_columns, tp)
        for feature in feature_columns:
            values = frame[feature].cast(pl.Float64, strict=False).to_numpy()
            finite = np.isfinite(values)
            if int(finite.sum()) < int(min_train_tp_rows) + int(min_train_fp_rows):
                continue
            finite_values = values[finite]
            if np.unique(finite_values).size <= 1:
                continue
            thresholds = np.unique(np.nanquantile(finite_values, quantiles))
            for direction in ("higher_good", "lower_good"):
                for threshold in thresholds:
                    keep = finite & ((values >= threshold) if direction == "higher_good" else (values <= threshold))
                    accepted = int(keep.sum())
                    if accepted <= 0:
                        continue
                    train_tp = int((tp & keep).sum())
                    train_fp = int((fp & keep).sum())
                    precision = train_tp / accepted if accepted else 0.0
                    fdr = train_fp / accepted if accepted else 1.0
                    lift = precision / train_base_precision if train_base_precision > 0 else 0.0
                    lcb = wilson_lower_bound(train_tp, accepted, z=float(lcb_z))
                    accepted_rate = accepted / frame.height if frame.height else 0.0
                    score = 2.0 * max(0.0, lift - 1.0) + precision - fdr - 0.25 * accepted_rate
                    feature_auc, feature_auc_abs, feature_auc_direction = feature_auc_by_name.get(
                        feature,
                        (None, None, None),
                    )
                    direction_agreement = bool(feature_auc_direction == direction) if feature_auc_direction else None
                    signed_auc_edge = 0.0
                    if feature_auc_abs is not None:
                        signed_auc_edge = float(feature_auc_abs) - 0.5
                        if direction_agreement is False:
                            signed_auc_edge *= -1.0
                    directional_lcb_score = (
                        float(lcb if lcb is not None else 0.0)
                        + 2.0 * signed_auc_edge
                        + 0.002 * accepted
                        - 0.5 * fdr
                    )
                    rules.append(
                        RowRule(
                            fold_idx=int(fold_idx),
                            train_blocks=",".join(train_blocks),
                            test_block=str(test_block),
                            side=str(side),
                            candidate_name=str(candidate),
                            feature=str(feature),
                            direction=direction,
                            threshold=float(threshold),
                            train_rows=int(frame.height),
                            train_accepted_rows=accepted,
                            train_tp=train_tp,
                            train_fp=train_fp,
                            train_precision=float(precision),
                            train_base_precision=float(train_base_precision),
                            train_lift=float(lift),
                            train_false_discovery_rate=float(fdr),
                            train_precision_lcb=lcb,
                            train_accepted_rate=float(accepted_rate),
                            rule_score=float(score),
                            feature_auc=feature_auc,
                            feature_auc_abs=feature_auc_abs,
                            feature_auc_direction=feature_auc_direction,
                            direction_agreement=direction_agreement,
                            directional_lcb_score=float(directional_lcb_score),
                        )
                    )
    return sorted(rules, key=lambda row: row.rule_score, reverse=True)


def train_feature_auc(
    frame: pl.DataFrame,
    feature_columns: list[str],
    target_positive: np.ndarray,
) -> dict[str, tuple[float, float, str]]:
    out: dict[str, tuple[float, float, str]] = {}
    for feature in feature_columns:
        values = frame[feature].cast(pl.Float64, strict=False).to_numpy()
        finite = np.isfinite(values)
        if int(finite.sum()) <= 1:
            continue
        y = target_positive[finite]
        x = values[finite]
        if np.unique(x).size <= 1 or np.unique(y).size <= 1:
            continue
        auc = binary_auc_score(y.astype(bool), x.astype(float))
        auc_abs = max(auc, 1.0 - auc)
        direction = "higher_good" if auc >= 0.5 else "lower_good"
        out[feature] = (float(auc), float(auc_abs), direction)
    return out


def binary_auc_score(target_positive: np.ndarray, values: np.ndarray) -> float:
    pos = values[target_positive]
    neg = values[~target_positive]
    if pos.size == 0 or neg.size == 0:
        return 0.5
    comparisons = pos[:, None] - neg[None, :]
    wins = float((comparisons > 0).sum())
    ties = float((comparisons == 0).sum())
    return (wins + 0.5 * ties) / float(pos.size * neg.size)


def filter_eligible_row_rules(
    rules: list[RowRule],
    config: RowRuleEligibilityConfig,
) -> tuple[list[RowRule], list[dict[str, Any]]]:
    eligible: list[RowRule] = []
    audit: list[dict[str, Any]] = []
    for rule in rules:
        row = asdict(rule) | row_rule_eligibility_row(rule, config)
        audit.append(row)
        if row["rule_eligible"]:
            eligible.append(rule)
    return eligible, audit


def limit_rules_per_candidate(
    rules: list[RowRule],
    *,
    max_rules_per_candidate: int,
    selection_score: str = "rule_score",
) -> list[RowRule]:
    if int(max_rules_per_candidate) <= 0:
        return list(rules)
    out: list[RowRule] = []
    grouped: dict[tuple[int, str, str], list[RowRule]] = {}
    for rule in rules:
        grouped.setdefault((int(rule.fold_idx), rule.side, rule.candidate_name), []).append(rule)
    for key in sorted(grouped):
        selected = sorted(grouped[key], key=lambda row: row_selection_score(row, selection_score), reverse=True)[
            : int(max_rules_per_candidate)
        ]
        out.extend(selected)
    return sorted(out, key=lambda row: (row.fold_idx, row.side, row.candidate_name, -row_selection_score(row, selection_score)))


def row_selection_score(rule: RowRule, selection_score: str) -> float:
    if selection_score == "rule_score":
        return float(rule.rule_score)
    if selection_score == "directional_lcb_v1":
        return float(rule.directional_lcb_score if rule.directional_lcb_score is not None else -math.inf)
    raise ValueError(f"Unknown rule selection score: {selection_score}")


def select_prequential_reliable_rules(
    rules: list[RowRule],
    *,
    reliability_rows: list[dict[str, Any]],
    config: RowRuleReliabilityConfig,
    max_rules_per_candidate: int,
    fallback_selection_score: str,
) -> tuple[list[RowRule], list[dict[str, Any]]]:
    reliability_by_key = {reliability_key_from_row(row, config.key_mode): row for row in reliability_rows}
    selected: list[RowRule] = []
    audit_rows: list[dict[str, Any]] = []
    grouped: dict[tuple[int, str, str], list[tuple[RowRule, dict[str, Any] | None, list[str], float]]] = {}
    has_history = bool(reliability_by_key)
    for rule in rules:
        reliability = reliability_by_key.get(reliability_key_for_rule(rule, config.key_mode))
        reject_reasons = rule_reliability_reject_reasons(reliability, config)
        if reliability is not None and not reject_reasons:
            score = rule_reliability_selection_score(rule, reliability)
            grouped.setdefault((int(rule.fold_idx), rule.side, rule.candidate_name), []).append((rule, reliability, reject_reasons, score))
        elif not has_history and config.warmup_mode == "static":
            score = row_selection_score(rule, fallback_selection_score)
            grouped.setdefault((int(rule.fold_idx), rule.side, rule.candidate_name), []).append((rule, reliability, ["warmup_static"], score))
        else:
            score = row_selection_score(rule, fallback_selection_score)
        audit_rows.append(
            selection_audit_row(
                rule,
                selected=False,
                selection_mode="prequential_reliability_v1",
                reliability=reliability,
                reject_reasons=reject_reasons if reject_reasons else ([] if reliability is not None else ["no_reliability_history"]),
                selection_score=score,
            )
        )
    selected_ids: set[tuple[int, str, str, str, str, float]] = set()
    for key in sorted(grouped):
        ranked = sorted(grouped[key], key=lambda item: item[3], reverse=True)
        if int(max_rules_per_candidate) > 0:
            ranked = ranked[: int(max_rules_per_candidate)]
        for rule, _reliability, _reject_reasons, _score in ranked:
            selected.append(rule)
            selected_ids.add(rule_identity(rule))
    out_audit: list[dict[str, Any]] = []
    for row in audit_rows:
        is_selected = (
            int(row["fold_idx"]),
            str(row["side"]),
            str(row["candidate_name"]),
            str(row["feature"]),
            str(row["direction"]),
            float(row["threshold"]),
        ) in selected_ids
        out_audit.append(row | {"selected": bool(is_selected), "selection_reject_reasons": "" if is_selected else row["selection_reject_reasons"]})
    return sorted(selected, key=lambda row: (row.fold_idx, row.side, row.candidate_name, -rule_reliability_selection_score(row, reliability_by_key.get(reliability_key_for_rule(row, config.key_mode), {})))), out_audit


def rule_identity(rule: RowRule) -> tuple[int, str, str, str, str, float]:
    return (int(rule.fold_idx), rule.side, rule.candidate_name, rule.feature, rule.direction, float(rule.threshold))


def rule_reliability_rows(shadow_rows: list[dict[str, Any]], config: RowRuleReliabilityConfig) -> list[dict[str, Any]]:
    if not shadow_rows:
        return []
    frame = pl.DataFrame(shadow_rows, infer_schema_length=None)
    if frame.is_empty():
        return []
    key_columns = reliability_key_columns(config.key_mode)
    needed = [col for col in [*key_columns, "fold_idx", "signal_tp", "signal_fp"] if col in frame.columns]
    if len(needed) < len(key_columns) + 3:
        return []
    grouped = (
        frame.group_by(key_columns)
        .agg(
            pl.col("fold_idx").n_unique().alias("history_folds"),
            pl.len().alias("signals"),
            pl.col("signal_tp").sum().alias("tp"),
            pl.col("signal_fp").sum().alias("fp"),
        )
        .to_dicts()
    )
    rows: list[dict[str, Any]] = []
    for row in grouped:
        signals = int(row["signals"])
        tp = int(row["tp"])
        fp = int(row["fp"])
        precision = tp / signals if signals else None
        fdr = fp / signals if signals else None
        precision_lcb = wilson_lower_bound(tp, signals, z=float(config.lcb_z)) if signals else None
        score = (
            2.0 * float(precision_lcb if precision_lcb is not None else 0.0)
            + float(precision if precision is not None else 0.0)
            - float(fdr if fdr is not None else 1.0)
            + 0.05 * min(int(row["history_folds"]), 5)
        )
        rows.append(
            row
            | {
                "reliability_key_mode": config.key_mode,
                "reliability_precision": precision,
                "reliability_precision_lcb": precision_lcb,
                "reliability_false_discovery_rate": fdr,
                "reliability_score": float(score),
            }
        )
    return rows


def recent_shadow_history_rows(shadow_rows: list[dict[str, Any]], lookback_folds: int) -> list[dict[str, Any]]:
    if int(lookback_folds) <= 0 or not shadow_rows:
        return shadow_rows
    fold_ids = sorted({int(row["fold_idx"]) for row in shadow_rows if row.get("fold_idx") is not None})
    if not fold_ids:
        return []
    keep_folds = set(fold_ids[-int(lookback_folds) :])
    return [row for row in shadow_rows if row.get("fold_idx") is not None and int(row["fold_idx"]) in keep_folds]


def rule_reliability_reject_reasons(reliability: dict[str, Any] | None, config: RowRuleReliabilityConfig) -> list[str]:
    if reliability is None:
        return ["no_reliability_history"]
    reasons: list[str] = []
    if int(reliability.get("history_folds", 0)) < int(config.min_history_folds):
        reasons.append("low_history_folds")
    if int(reliability.get("signals", 0)) < int(config.min_signals):
        reasons.append("low_reliability_signals")
    precision_lcb = reliability.get("reliability_precision_lcb")
    if precision_lcb is None or float(precision_lcb) < float(config.min_precision_lcb):
        reasons.append("low_reliability_precision_lcb")
    fdr = reliability.get("reliability_false_discovery_rate")
    if fdr is None or float(fdr) > float(config.max_false_discovery_rate):
        reasons.append("high_reliability_fdr")
    return reasons


def rule_reliability_selection_score(rule: RowRule, reliability: dict[str, Any] | None) -> float:
    reliability_score = float((reliability or {}).get("reliability_score", -math.inf))
    if not math.isfinite(reliability_score):
        return -math.inf
    return reliability_score + 0.10 * float(rule.directional_lcb_score if rule.directional_lcb_score is not None else 0.0)


def selection_audit_row(
    rule: RowRule,
    *,
    selected: bool,
    selection_mode: str,
    reliability: dict[str, Any] | None,
    reject_reasons: list[str],
    selection_score: float,
) -> dict[str, Any]:
    reliability = reliability or {}
    return (
        asdict(rule)
        | {
            "selected": bool(selected),
            "row_rule_selection_mode": selection_mode,
            "selection_score": float(selection_score) if math.isfinite(float(selection_score)) else None,
            "selection_reject_reasons": ",".join(reject_reasons),
            "reliability_key_mode": reliability.get("reliability_key_mode"),
            "reliability_history_folds": reliability.get("history_folds"),
            "reliability_signals": reliability.get("signals"),
            "reliability_tp": reliability.get("tp"),
            "reliability_fp": reliability.get("fp"),
            "reliability_precision": reliability.get("reliability_precision"),
            "reliability_precision_lcb": reliability.get("reliability_precision_lcb"),
            "reliability_false_discovery_rate": reliability.get("reliability_false_discovery_rate"),
            "reliability_score": reliability.get("reliability_score"),
            "reliability_feature_family": reliability.get("feature_family"),
        }
    )


def reliability_key_columns(key_mode: str) -> list[str]:
    if key_mode == "feature_direction":
        return ["side", "candidate_name", "feature", "direction"]
    if key_mode == "family_direction":
        return ["side", "candidate_name", "feature_family", "direction"]
    raise ValueError(f"Unknown rule reliability key mode: {key_mode}")


def reliability_key_for_rule(rule: RowRule, key_mode: str) -> tuple[Any, ...]:
    if key_mode == "feature_direction":
        return (rule.side, rule.candidate_name, rule.feature, rule.direction)
    if key_mode == "family_direction":
        return (rule.side, rule.candidate_name, row_rule_feature_family(rule.feature), rule.direction)
    raise ValueError(f"Unknown rule reliability key mode: {key_mode}")


def reliability_key_from_row(row: dict[str, Any], key_mode: str) -> tuple[Any, ...]:
    return tuple(row.get(col) for col in reliability_key_columns(key_mode))


def row_rule_feature_family(feature: str) -> str:
    raw = str(feature)
    if not raw.startswith("row_rpf_"):
        return raw
    name = raw.removeprefix("row_rpf_")
    for suffix in ("_positive_rate", "_mean_abs", "_max_abs", "_mean", "_std", "_min", "_max"):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name


def row_rule_eligibility_row(rule: RowRule, config: RowRuleEligibilityConfig) -> dict[str, Any]:
    reasons: list[str] = []
    if config.allowed_directions and rule.direction not in set(config.allowed_directions):
        reasons.append("direction_not_allowed")
    if rule.train_accepted_rows < int(config.min_train_signals):
        reasons.append("low_train_signals")
    if rule.train_precision < float(config.min_train_precision):
        reasons.append("low_train_precision")
    lcb = rule.train_precision_lcb
    if lcb is None or lcb < float(config.min_train_precision_lcb):
        reasons.append("low_train_precision_lcb")
    if rule.train_lift < float(config.min_train_lift):
        reasons.append("low_train_lift")
    if rule.train_false_discovery_rate > float(config.max_train_false_discovery_rate):
        reasons.append("high_train_fdr")
    if rule.train_accepted_rate > float(config.max_train_accepted_rate):
        reasons.append("high_train_accepted_rate")
    if rule.feature_auc_abs is not None and rule.feature_auc_abs < float(config.min_feature_auc_abs):
        reasons.append("low_feature_auc_abs")
    if bool(config.require_feature_direction_agreement) and rule.direction_agreement is not True:
        reasons.append("feature_direction_disagreement")
    return {
        "rule_eligible": not reasons,
        "rule_reject_reasons": ",".join(reasons),
        "rule_min_train_signals": int(config.min_train_signals),
        "rule_min_train_precision": float(config.min_train_precision),
        "rule_min_train_precision_lcb": float(config.min_train_precision_lcb),
        "rule_min_train_lift": float(config.min_train_lift),
        "rule_max_train_fdr": float(config.max_train_false_discovery_rate),
        "rule_max_train_accepted_rate": float(config.max_train_accepted_rate),
        "rule_lcb_z": float(config.lcb_z),
        "rule_min_feature_auc_abs": float(config.min_feature_auc_abs),
        "rule_require_feature_direction_agreement": bool(config.require_feature_direction_agreement),
        "rule_allowed_directions": ",".join(config.allowed_directions),
    }


def replay_rules(test: pl.DataFrame, rules: list[RowRule], *, rule_level: bool) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if test.is_empty() or not rules:
        return rows
    for rule_idx, rule in enumerate(rules):
        frame = test.filter((pl.col("side") == rule.side) & (pl.col("candidate_name") == rule.candidate_name))
        if frame.is_empty() or rule.feature not in frame.columns:
            continue
        accepted = filter_by_rule(frame, rule)
        for row in accepted.to_dicts():
            rows.append(row | {"rule_idx": rule_idx, "feature_family": row_rule_feature_family(rule.feature), **asdict(rule)})
    return rows


def replay_rules_union(test: pl.DataFrame, rules: list[RowRule]) -> pl.DataFrame:
    if test.is_empty() or not rules:
        return pl.DataFrame()
    frames: list[pl.DataFrame] = []
    for rule_idx, rule in enumerate(rules):
        frame = test.filter((pl.col("side") == rule.side) & (pl.col("candidate_name") == rule.candidate_name))
        if frame.is_empty() or rule.feature not in frame.columns:
            continue
        accepted = filter_by_rule(frame, rule).with_columns(
            pl.lit(rule_idx).alias("first_rule_idx"),
            pl.lit(rule.feature).alias("first_rule_feature"),
            pl.lit(rule.direction).alias("first_rule_direction"),
            pl.lit(rule.threshold).alias("first_rule_threshold"),
            pl.lit(rule.fold_idx).alias("fold_idx"),
            pl.lit(rule.train_blocks).alias("train_blocks"),
            pl.lit(rule.test_block).alias("test_block"),
        )
        frames.append(accepted)
    if not frames:
        return pl.DataFrame()
    out = pl.concat(frames, how="diagonal_relaxed")
    unique_keys = [col for col in ["source_run", "side", "candidate_name", "router_pred_batch_id", "timestamp", "batch_id"] if col in out.columns]
    return out.unique(unique_keys, keep="first") if unique_keys else out


def filter_by_rule(frame: pl.DataFrame, rule: RowRule) -> pl.DataFrame:
    expr = pl.col(rule.feature).cast(pl.Float64, strict=False)
    keep = expr >= float(rule.threshold) if rule.direction == "higher_good" else expr <= float(rule.threshold)
    return frame.filter(keep)


def summarize_acceptance(frame: pl.DataFrame, *, by: list[str]) -> list[dict[str, Any]]:
    if frame.is_empty():
        return []
    return (
        frame.group_by(by)
        .agg(
            pl.len().alias("signals"),
            pl.col("signal_tp").sum().alias("tp"),
            pl.col("signal_fp").sum().alias("fp"),
        )
        .with_columns(
            (pl.col("tp") / pl.col("signals")).alias("precision"),
            (pl.col("fp") / pl.col("signals")).alias("false_discovery_rate"),
        )
        .sort(by)
        .to_dicts()
    )


def compare_fold_summary_with_raw(raw_frame: pl.DataFrame, fold_summary: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if raw_frame.is_empty() or not fold_summary:
        return []
    fold = pl.DataFrame(fold_summary, infer_schema_length=None)
    raw = raw_candidate_summary(raw_frame)
    return (
        fold.join(
            raw,
            left_on=["test_block", "side", "candidate_name"],
            right_on=["source_block", "side", "candidate_name"],
            how="left",
        )
        .with_columns(comparison_exprs())
        .sort(["fold_idx", "side", "candidate_name"])
        .to_dicts()
    )


def compare_overall_summary_with_raw(
    raw_frame: pl.DataFrame,
    fold_summary: list[dict[str, Any]],
    overall_summary: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if raw_frame.is_empty() or not fold_summary or not overall_summary:
        return []
    selected_blocks = sorted({str(row["test_block"]) for row in fold_summary})
    selected_raw = raw_frame.filter(pl.col("source_block").is_in(selected_blocks))
    if selected_raw.is_empty():
        return []
    overall = pl.DataFrame(overall_summary, infer_schema_length=None)
    raw = (
        selected_raw.group_by(["side", "candidate_name"])
        .agg(
            pl.len().alias("raw_signals"),
            pl.col("signal_tp").sum().alias("raw_tp"),
            pl.col("signal_fp").sum().alias("raw_fp"),
        )
        .with_columns(
            (pl.col("raw_tp") / pl.col("raw_signals")).alias("raw_precision"),
            (pl.col("raw_fp") / pl.col("raw_signals")).alias("raw_false_discovery_rate"),
        )
    )
    return (
        overall.join(raw, on=["side", "candidate_name"], how="left")
        .with_columns(
            *comparison_exprs(),
            pl.lit(",".join(selected_blocks)).alias("raw_baseline_blocks"),
        )
        .sort(["side", "candidate_name"])
        .to_dicts()
    )


def raw_candidate_summary(raw_frame: pl.DataFrame) -> pl.DataFrame:
    return (
        raw_frame.group_by(["source_block", "side", "candidate_name"])
        .agg(
            pl.len().alias("raw_signals"),
            pl.col("signal_tp").sum().alias("raw_tp"),
            pl.col("signal_fp").sum().alias("raw_fp"),
        )
        .with_columns(
            (pl.col("raw_tp") / pl.col("raw_signals")).alias("raw_precision"),
            (pl.col("raw_fp") / pl.col("raw_signals")).alias("raw_false_discovery_rate"),
        )
    )


def comparison_exprs() -> list[pl.Expr]:
    return [
        safe_div_col("precision", "raw_precision").alias("precision_lift_vs_raw"),
        safe_div_col("signals", "raw_signals").alias("signal_retention_vs_raw"),
        safe_div_col("tp", "raw_tp").alias("tp_retention_vs_raw"),
        safe_div_col("fp", "raw_fp").alias("fp_retention_vs_raw"),
    ]


def safe_div_col(numerator: str, denominator: str) -> pl.Expr:
    return (
        pl.when(pl.col(denominator).is_not_null() & (pl.col(denominator) != 0))
        .then(pl.col(numerator) / pl.col(denominator))
        .otherwise(None)
    )


def write_row_rule_bank_report(
    path: Path,
    *,
    row_diagnostic_run: Path,
    blocks: list[str],
    folds: list[tuple[int, list[str], str]],
    rule_rows: list[dict[str, Any]],
    fold_summary: list[dict[str, Any]],
    overall_summary: list[dict[str, Any]],
    fold_comparison: list[dict[str, Any]],
    overall_comparison: list[dict[str, Any]],
) -> None:
    lines = [
        "# RPF Ranked Signal Row Rule Bank",
        "",
        "## Scope",
        "",
        f"- row diagnostic run: `{row_diagnostic_run}`",
        f"- blocks: `{', '.join(blocks)}`",
        f"- folds: `{len(folds)}`",
        f"- eligible rules: `{len(rule_rows)}`",
        "",
        "## Fold Summary",
        "",
        "| Fold | Train | Test | Side | Candidate | Signals | TP | FP | Precision | FDR |",
        "|---:|---|---|---|---|---:|---:|---:|---:|---:|",
    ]
    for row in fold_summary:
        lines.append(
            "| {fold_idx} | {train_blocks} | {test_block} | {side} | {candidate_name} | {signals} | {tp} | {fp} | "
            "{precision} | {false_discovery_rate} |".format(**{key: markdown_value(value) for key, value in row.items()})
        )
    lines.extend(
        [
            "",
            "## Fold Raw Comparison",
            "",
            "| Fold | Test | Side | Candidate | Filtered Signals | Filtered Precision | Raw Signals | Raw Precision | Precision Lift | Signal Retention |",
            "|---:|---|---|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in fold_comparison:
        lines.append(
            "| {fold_idx} | {test_block} | {side} | {candidate_name} | {signals} | {precision} | {raw_signals} | "
            "{raw_precision} | {precision_lift_vs_raw} | {signal_retention_vs_raw} |".format(
                **{key: markdown_value(value) for key, value in row.items()}
            )
        )
    lines.extend(
        [
            "",
            "## Overall Summary",
            "",
            "| Side | Candidate | Signals | TP | FP | Precision | FDR |",
            "|---|---|---:|---:|---:|---:|---:|",
        ]
    )
    for row in overall_summary:
        lines.append(
            "| {side} | {candidate_name} | {signals} | {tp} | {fp} | {precision} | {false_discovery_rate} |".format(
                **{key: markdown_value(value) for key, value in row.items()}
            )
        )
    lines.extend(
        [
            "",
            "## Overall Raw Comparison",
            "",
            "| Side | Candidate | Filtered Signals | Filtered Precision | Raw Signals | Raw Precision | Precision Lift | Signal Retention |",
            "|---|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in overall_comparison:
        lines.append(
            "| {side} | {candidate_name} | {signals} | {precision} | {raw_signals} | {raw_precision} | "
            "{precision_lift_vs_raw} | {signal_retention_vs_raw} |".format(**{key: markdown_value(value) for key, value in row.items()})
        )
    lines.extend(
        [
            "",
            "## Interpretation Rules",
            "",
            "- Rules are trained on prior matured signal rows only.",
            "- Replayed rows are next-block signal rows accepted by at least one eligible filter.",
            "- This is still diagnostic evidence; it does not modify router decisions.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n")


def parse_float_tuple(raw: str) -> tuple[float, ...]:
    values = tuple(float(item.strip()) for item in str(raw).split(",") if item.strip())
    if not values:
        raise ValueError("Expected at least one quantile")
    bad = [value for value in values if value <= 0.0 or value >= 1.0]
    if bad:
        raise ValueError(f"Quantiles must be in (0,1), got {bad[:3]}")
    return values


def parse_optional_csv(raw: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(item.strip() for item in str(raw or "").split(",") if item.strip()))


def run_root_for_args() -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return OUTPUT_ROOT / f"{timestamp}_rank_signal_row_rule_bank"


if __name__ == "__main__":
    raise SystemExit(main())
