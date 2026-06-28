"""Separate target-event and classifier-trust bank planning for RPF decisions."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import polars as pl

from regression_feature_engineering.walkforward.classify import (
    TARGET_BINARY_DOWN_2X_UP,
    TARGET_BINARY_UP_2X_DOWN,
    DOWN_EXTREME,
    UP_EXTREME,
)
from regression_feature_engineering.walkforward.config import load_clean_config
from regression_feature_engineering.walkforward.data import RPFDataContext, resolve_context
from regression_feature_engineering.walkforward.reports import append_event, write_json, write_markdown, write_stage_status
from regression_feature_engineering.walkforward.signal_bank import build_batch_signal_inventory
from regression_feature_engineering.walkforward.windows import RPFWindow, read_windows
from scripts.project_paths import ensure_project_root_on_path


PROJECT_ROOT = ensure_project_root_on_path(Path(__file__))
OUTPUT_ROOT = PROJECT_ROOT / "test_output" / "rpf_decision_banks"

SIDE_UP = "up"
SIDE_DOWN = "down"
SIDES = (SIDE_UP, SIDE_DOWN)


@dataclass(frozen=True)
class SeparateBankConfig:
    target_positive_batch_min_rate: float = 0.80
    target_opposite_batch_max_rate: float = 0.20
    target_train_positive_batches: int = 80
    target_train_negative_batches: int = 160
    target_val_positive_batches: int = 20
    target_val_negative_batches: int = 40
    gate_min_active_rows: int = 10
    gate_trust_min_precision: float = 0.70
    gate_reject_min_fp_rate: float = 0.70
    gate_train_trust_batches: int = 80
    gate_train_reject_batches: int = 160
    gate_val_trust_batches: int = 20
    gate_val_reject_batches: int = 40
    candidate_lookback_batches: int = 2000
    label_maturity_embargo_batches: int = 1


def main() -> int:
    args = _parse_args()
    config = load_clean_config(args.config)
    asset = str(args.asset or config.asset)
    root = str(args.root or config.root)
    side = str(args.side)
    context = resolve_context(project_root=PROJECT_ROOT, asset=asset, root=root, target_col=UP_EXTREME)
    run_root = _run_root(args, side)
    run_root.mkdir(parents=True, exist_ok=True)
    events = run_root / "events.jsonl"
    append_event(events, "stage_start", stage="decision_bank_plan", asset=asset, root=root, side=side, run=str(run_root))
    print(f"[rpf-bank] start asset={asset} root={root} side={side} run={run_root}", flush=True)

    windows = read_windows(Path(args.base_run) / "frozen_windows.parquet")
    n_steps = int(args.n_steps)
    windows = windows[-n_steps:] if n_steps > 0 else windows
    if not windows:
        raise ValueError("No frozen windows to plan")

    bank_config = SeparateBankConfig(
        target_positive_batch_min_rate=float(args.target_positive_batch_min_rate),
        target_opposite_batch_max_rate=float(args.target_opposite_batch_max_rate),
        target_train_positive_batches=int(args.target_train_positive_batches),
        target_train_negative_batches=int(args.target_train_negative_batches),
        target_val_positive_batches=int(args.target_val_positive_batches),
        target_val_negative_batches=int(args.target_val_negative_batches),
        gate_min_active_rows=int(args.gate_min_active_rows),
        gate_trust_min_precision=float(args.gate_trust_min_precision),
        gate_reject_min_fp_rate=float(args.gate_reject_min_fp_rate),
        gate_train_trust_batches=int(args.gate_train_trust_batches),
        gate_train_reject_batches=int(args.gate_train_reject_batches),
        gate_val_trust_batches=int(args.gate_val_trust_batches),
        gate_val_reject_batches=int(args.gate_val_reject_batches),
        candidate_lookback_batches=int(args.candidate_lookback_batches),
        label_maturity_embargo_batches=int(args.label_maturity_embargo_batches),
    )

    target_inventory = build_batch_signal_inventory(context)
    target_inventory.write_parquet(run_root / "target_signal_inventory.parquet")
    gate_inventory = build_classifier_outcome_inventory(
        Path(args.classifier_score_path),
        classifier_trial_number=args.classifier_trial_number,
        classifier_threshold=float(args.classifier_threshold),
    )
    gate_inventory.write_parquet(run_root / "gate_trust_inventory.parquet")
    plan = build_separate_bank_plan(
        windows,
        target_inventory=target_inventory,
        gate_inventory=gate_inventory,
        side=side,
        config=bank_config,
    )
    plan.write_parquet(run_root / "separate_bank_plan.parquet")
    summary = summarize_separate_bank_plan(plan)
    write_json(
        run_root / "bank_config.json",
        {
            "asset": asset,
            "root": root,
            "side": side,
            "classifier_score_path": str(args.classifier_score_path),
            "classifier_trial_number": args.classifier_trial_number,
            "classifier_threshold": float(args.classifier_threshold),
            "config": asdict(bank_config),
            "summary": summary,
        },
    )
    write_markdown(
        run_root / "report.md",
        title="RPF Separate Decision Bank Plan",
        sections={
            "Scope": {
                "asset": asset,
                "root": root,
                "side": side,
                "windows": len(windows),
                "classifier_score_path": str(args.classifier_score_path),
            },
            "Config": asdict(bank_config),
            "Summary": summary,
            "Interpretation": (
                "Target-bank batches train the main UP/DOWN event model. "
                "Gate-bank batches train the trust filter from historical classifier true-positive "
                "and false-positive behavior. Both banks are mature before the prediction batch."
            ),
        },
    )
    write_stage_status(
        run_root / "stage_status.json",
        stage="decision_bank_plan",
        status="ok",
        asset=asset,
        root=root,
        side=side,
        run=str(run_root),
        windows=len(windows),
        summary=summary,
    )
    append_event(events, "stage_done", stage="decision_bank_plan", run=str(run_root), **summary)
    print(
        "[rpf-bank] done "
        f"run={run_root} usable_target={summary['target_bank_usable_window_rate']:.3f} "
        f"usable_gate={summary['gate_bank_usable_window_rate']:.3f}",
        flush=True,
    )
    return 0


def build_classifier_outcome_inventory(
    score_path: Path,
    *,
    classifier_trial_number: int | None = None,
    classifier_threshold: float = 0.5,
) -> pl.DataFrame:
    """Build batch-level TP/FP inventory from row-level classifier scores."""

    path = Path(score_path)
    if not path.exists():
        raise FileNotFoundError(f"Classifier score file not found: {path}")
    scores = pl.read_parquet(path)
    if scores.is_empty():
        return _empty_gate_inventory()
    if "trial_number" in scores.columns:
        trial = classifier_trial_number
        if trial is None:
            trial = _best_classifier_trial_from_run(path.parent)
        scores = scores.filter(pl.col("trial_number") == int(trial))
    prob_col = _first_existing(scores, ("prob", "prediction_prob", "classifier_prob", "positive_probability"))
    target_col = _first_existing(scores, ("target", "label", "y_true", "classifier_target"))
    pred_col = "predicted_positive" if "predicted_positive" in scores.columns else None
    pred_expr = pl.col(pred_col).cast(pl.Int8) if pred_col else (pl.col(prob_col) >= float(classifier_threshold)).cast(pl.Int8)
    pred_batch_expr = pl.col("pred_batch_id") if "pred_batch_id" in scores.columns else pl.col("batch_id")
    select_cols = ["timestamp", "batch_id", target_col, prob_col]
    if pred_col:
        select_cols.append(pred_col)
    out = (
        scores.select([*select_cols, pred_batch_expr.alias("score_pred_batch_id")])
        .with_columns(
            [
                pl.col(target_col).cast(pl.Int8).alias("classifier_target"),
                pl.col(prob_col).cast(pl.Float64).alias("classifier_prob"),
                pred_expr.alias("classifier_active"),
            ]
        )
        .filter(
            pl.col("classifier_target").is_not_null()
            & pl.col("classifier_prob").is_not_null()
            & pl.col("classifier_prob").is_finite()
        )
        .with_columns(
            [
                ((pl.col("classifier_active") == 1) & (pl.col("classifier_target") == 1)).cast(pl.Int8).alias("trust_tp"),
                ((pl.col("classifier_active") == 1) & (pl.col("classifier_target") == 0)).cast(pl.Int8).alias("reject_fp"),
                ((pl.col("classifier_active") == 0) & (pl.col("classifier_target") == 1)).cast(pl.Int8).alias("missed_fn"),
                ((pl.col("classifier_active") == 0) & (pl.col("classifier_target") == 0)).cast(pl.Int8).alias("safe_tn"),
            ]
        )
        .group_by("batch_id")
        .agg(
            [
                pl.len().alias("rows"),
                pl.col("timestamp").min().alias("batch_start_ts"),
                pl.col("timestamp").max().alias("batch_end_ts"),
                pl.col("score_pred_batch_id").min().alias("score_pred_batch_id_min"),
                pl.col("score_pred_batch_id").max().alias("score_pred_batch_id_max"),
                pl.col("classifier_active").sum().alias("classifier_active_rows"),
                pl.col("trust_tp").sum().alias("trust_tp_rows"),
                pl.col("reject_fp").sum().alias("reject_fp_rows"),
                pl.col("missed_fn").sum().alias("missed_fn_rows"),
                pl.col("safe_tn").sum().alias("safe_tn_rows"),
                pl.col("classifier_target").mean().alias("classifier_target_positive_rate"),
                pl.col("classifier_prob").mean().alias("classifier_prob_mean"),
                pl.col("classifier_prob").quantile(0.80).alias("classifier_prob_q80"),
            ]
        )
        .with_columns(
            [
                (pl.col("classifier_active_rows") / pl.col("rows")).alias("classifier_active_rate"),
                _safe_ratio_expr("trust_tp_rows", "classifier_active_rows").alias("trust_precision_among_active"),
                _safe_ratio_expr("reject_fp_rows", "classifier_active_rows").alias("reject_fp_rate_among_active"),
                _safe_ratio_expr("missed_fn_rows", "rows").alias("missed_fn_rate_all"),
            ]
        )
        .sort("batch_id")
    )
    return out


def build_separate_bank_plan(
    base_windows: list[RPFWindow],
    *,
    target_inventory: pl.DataFrame,
    gate_inventory: pl.DataFrame,
    side: str,
    config: SeparateBankConfig,
) -> pl.DataFrame:
    if side not in SIDES:
        known = ", ".join(SIDES)
        raise ValueError(f"Unsupported side {side!r}; expected one of: {known}")
    target_rows = {int(row["batch_id"]): row for row in target_inventory.to_dicts()}
    gate_rows = {int(row["batch_id"]): row for row in gate_inventory.to_dicts()}
    rows: list[dict[str, Any]] = []
    for window in base_windows:
        pred_batch_id = int(window.pred_batch_id)
        mature_cutoff = pred_batch_id - 1 - int(config.label_maturity_embargo_batches)
        target_selected = _select_target_bank_ids(target_inventory, pred_batch_id=pred_batch_id, side=side, config=config)
        gate_selected = _select_gate_bank_ids(gate_inventory, pred_batch_id=pred_batch_id, config=config)
        target_train = target_selected["train_ids"]
        target_val = target_selected["val_ids"]
        gate_train = gate_selected["train_ids"]
        gate_val = gate_selected["val_ids"]
        rows.append(
            {
                "step_idx": int(window.step_idx),
                "pred_batch_id": pred_batch_id,
                "side": side,
                "mature_cutoff_batch_id": mature_cutoff,
                "target_train_batch_ids": list(target_train),
                "target_val_batch_ids": list(target_val),
                "gate_train_batch_ids": list(gate_train),
                "gate_val_batch_ids": list(gate_val),
                "target_train_batch_count": len(target_train),
                "target_val_batch_count": len(target_val),
                "gate_train_batch_count": len(gate_train),
                "gate_val_batch_count": len(gate_val),
                "target_train_positive_count": target_selected["train_positive_count"],
                "target_train_negative_count": target_selected["train_negative_count"],
                "target_val_positive_count": target_selected["val_positive_count"],
                "target_val_negative_count": target_selected["val_negative_count"],
                "gate_train_trust_count": gate_selected["train_trust_count"],
                "gate_train_reject_count": gate_selected["train_reject_count"],
                "gate_val_trust_count": gate_selected["val_trust_count"],
                "gate_val_reject_count": gate_selected["val_reject_count"],
                "target_positive_candidate_count": target_selected["positive_candidate_count"],
                "target_negative_candidate_count": target_selected["negative_candidate_count"],
                "gate_trust_candidate_count": gate_selected["trust_candidate_count"],
                "gate_reject_candidate_count": gate_selected["reject_candidate_count"],
                "target_train_rate_weighted": _weighted_target_rate(target_rows, target_train, side),
                "target_val_rate_weighted": _weighted_target_rate(target_rows, target_val, side),
                "gate_train_precision_weighted": _weighted_gate_rate(gate_rows, gate_train, "trust_precision_among_active"),
                "gate_val_precision_weighted": _weighted_gate_rate(gate_rows, gate_val, "trust_precision_among_active"),
                "gate_train_fp_rate_weighted": _weighted_gate_rate(gate_rows, gate_train, "reject_fp_rate_among_active"),
                "gate_val_fp_rate_weighted": _weighted_gate_rate(gate_rows, gate_val, "reject_fp_rate_among_active"),
                "max_target_train_label_window_batch_id": _max_field(target_rows, target_train, "label_window_batch_id_max"),
                "max_target_val_label_window_batch_id": _max_field(target_rows, target_val, "label_window_batch_id_max"),
                "max_gate_train_score_pred_batch_id": _max_field(gate_rows, gate_train, "score_pred_batch_id_max"),
                "max_gate_val_score_pred_batch_id": _max_field(gate_rows, gate_val, "score_pred_batch_id_max"),
                "target_train_maturity_violation": _violation(target_rows, target_train, "label_window_batch_id_max", mature_cutoff),
                "target_val_maturity_violation": _violation(target_rows, target_val, "label_window_batch_id_max", mature_cutoff),
                "gate_train_maturity_violation": _violation(gate_rows, gate_train, "score_pred_batch_id_max", mature_cutoff),
                "gate_val_maturity_violation": _violation(gate_rows, gate_val, "score_pred_batch_id_max", mature_cutoff),
                "target_bank_usable": _bank_complete(
                    target_selected,
                    ("train_positive_count", "train_negative_count", "val_positive_count", "val_negative_count"),
                    (
                        config.target_train_positive_batches,
                        config.target_train_negative_batches,
                        config.target_val_positive_batches,
                        config.target_val_negative_batches,
                    ),
                ),
                "gate_bank_usable": _bank_complete(
                    gate_selected,
                    ("train_trust_count", "train_reject_count", "val_trust_count", "val_reject_count"),
                    (
                        config.gate_train_trust_batches,
                        config.gate_train_reject_batches,
                        config.gate_val_trust_batches,
                        config.gate_val_reject_batches,
                    ),
                ),
            }
        )
    return pl.DataFrame(rows, infer_schema_length=None)


def summarize_separate_bank_plan(plan: pl.DataFrame) -> dict[str, Any]:
    if plan.is_empty():
        return {
            "windows": 0,
            "target_bank_usable_window_rate": 0.0,
            "gate_bank_usable_window_rate": 0.0,
            "any_maturity_violations": False,
        }
    violation_cols = [
        "target_train_maturity_violation",
        "target_val_maturity_violation",
        "gate_train_maturity_violation",
        "gate_val_maturity_violation",
    ]
    return {
        "windows": int(plan.height),
        "target_bank_usable_window_rate": float(plan["target_bank_usable"].mean()),
        "gate_bank_usable_window_rate": float(plan["gate_bank_usable"].mean()),
        "target_train_batch_count_min": int(plan["target_train_batch_count"].min()),
        "target_val_batch_count_min": int(plan["target_val_batch_count"].min()),
        "gate_train_batch_count_min": int(plan["gate_train_batch_count"].min()),
        "gate_val_batch_count_min": int(plan["gate_val_batch_count"].min()),
        "gate_train_precision_weighted_mean": _optional_float(plan["gate_train_precision_weighted"].mean()),
        "gate_train_fp_rate_weighted_mean": _optional_float(plan["gate_train_fp_rate_weighted"].mean()),
        "any_maturity_violations": any(bool(plan[col].max()) for col in violation_cols if col in plan.columns),
    }


def _select_target_bank_ids(
    inventory: pl.DataFrame,
    *,
    pred_batch_id: int,
    side: str,
    config: SeparateBankConfig,
) -> dict[str, Any]:
    pos_col, opposite_col = _side_rate_columns(side)
    mature_cutoff = int(pred_batch_id) - 1 - int(config.label_maturity_embargo_batches)
    min_batch = int(pred_batch_id) - int(config.candidate_lookback_batches)
    eligible = inventory.filter(
        (pl.col("batch_id") <= mature_cutoff)
        & (pl.col("batch_id") >= min_batch)
        & (pl.col("label_window_batch_id_max") <= mature_cutoff)
    )
    positives = eligible.filter(
        (pl.col(pos_col) >= float(config.target_positive_batch_min_rate))
        & (pl.col(opposite_col) <= float(config.target_opposite_batch_max_rate))
    ).sort("batch_id", descending=True)
    negatives = eligible.filter(pl.col(pos_col) <= float(config.target_opposite_batch_max_rate)).sort(
        "batch_id", descending=True
    )
    val_pos = _take_ids(positives, 0, int(config.target_val_positive_batches))
    train_pos = _take_ids(positives, int(config.target_val_positive_batches), int(config.target_train_positive_batches))
    val_neg = _take_ids(negatives, 0, int(config.target_val_negative_batches))
    train_neg = _take_ids(negatives, int(config.target_val_negative_batches), int(config.target_train_negative_batches))
    return {
        "train_ids": _sorted_unique((*train_pos, *train_neg)),
        "val_ids": _sorted_unique((*val_pos, *val_neg)),
        "positive_candidate_count": positives.height,
        "negative_candidate_count": negatives.height,
        "train_positive_count": len(train_pos),
        "train_negative_count": len(train_neg),
        "val_positive_count": len(val_pos),
        "val_negative_count": len(val_neg),
    }


def _select_gate_bank_ids(
    inventory: pl.DataFrame,
    *,
    pred_batch_id: int,
    config: SeparateBankConfig,
) -> dict[str, Any]:
    mature_cutoff = int(pred_batch_id) - 1 - int(config.label_maturity_embargo_batches)
    min_batch = int(pred_batch_id) - int(config.candidate_lookback_batches)
    eligible = inventory.filter(
        (pl.col("batch_id") <= mature_cutoff)
        & (pl.col("batch_id") >= min_batch)
        & (pl.col("score_pred_batch_id_max") <= mature_cutoff)
    )
    trust = eligible.filter(
        (pl.col("classifier_active_rows") >= int(config.gate_min_active_rows))
        & (pl.col("trust_precision_among_active") >= float(config.gate_trust_min_precision))
    ).sort("batch_id", descending=True)
    reject = eligible.filter(
        (pl.col("classifier_active_rows") >= int(config.gate_min_active_rows))
        & (pl.col("reject_fp_rate_among_active") >= float(config.gate_reject_min_fp_rate))
    ).sort("batch_id", descending=True)
    val_trust = _take_ids(trust, 0, int(config.gate_val_trust_batches))
    train_trust = _take_ids(trust, int(config.gate_val_trust_batches), int(config.gate_train_trust_batches))
    val_reject = _take_ids(reject, 0, int(config.gate_val_reject_batches))
    train_reject = _take_ids(reject, int(config.gate_val_reject_batches), int(config.gate_train_reject_batches))
    return {
        "train_ids": _sorted_unique((*train_trust, *train_reject)),
        "val_ids": _sorted_unique((*val_trust, *val_reject)),
        "trust_candidate_count": trust.height,
        "reject_candidate_count": reject.height,
        "train_trust_count": len(train_trust),
        "train_reject_count": len(train_reject),
        "val_trust_count": len(val_trust),
        "val_reject_count": len(val_reject),
    }


def _side_rate_columns(side: str) -> tuple[str, str]:
    if side == SIDE_UP:
        return "up_dom_rate", "down_dom_rate"
    if side == SIDE_DOWN:
        return "down_dom_rate", "up_dom_rate"
    known = ", ".join(SIDES)
    raise ValueError(f"Unsupported side {side!r}; expected one of: {known}")


def _take_ids(frame: pl.DataFrame, start: int, count: int) -> tuple[int, ...]:
    if count <= 0 or frame.is_empty():
        return ()
    return tuple(int(value) for value in frame.slice(int(start), int(count))["batch_id"].to_list())


def _sorted_unique(values: tuple[int, ...]) -> tuple[int, ...]:
    return tuple(sorted({int(value) for value in values}))


def _weighted_target_rate(rows_by_batch: dict[int, dict[str, Any]], batch_ids: tuple[int, ...], side: str) -> float | None:
    rate_col, _ = _side_rate_columns(side)
    return _weighted_rate(rows_by_batch, batch_ids, rate_col, weight_col="rows")


def _weighted_gate_rate(
    rows_by_batch: dict[int, dict[str, Any]], batch_ids: tuple[int, ...], rate_col: str
) -> float | None:
    return _weighted_rate(rows_by_batch, batch_ids, rate_col, weight_col="classifier_active_rows")


def _weighted_rate(
    rows_by_batch: dict[int, dict[str, Any]], batch_ids: tuple[int, ...], rate_col: str, *, weight_col: str
) -> float | None:
    numerator = 0.0
    denominator = 0.0
    for batch_id in batch_ids:
        row = rows_by_batch.get(int(batch_id))
        if row is None:
            continue
        value = row.get(rate_col)
        weight = float(row.get(weight_col) or 0.0)
        if value is None or weight <= 0.0:
            continue
        numerator += float(value) * weight
        denominator += weight
    return None if denominator == 0.0 else float(numerator / denominator)


def _max_field(rows_by_batch: dict[int, dict[str, Any]], batch_ids: tuple[int, ...], field: str) -> int | None:
    values = [
        int(row[field])
        for batch_id in batch_ids
        if (row := rows_by_batch.get(int(batch_id))) is not None and row.get(field) is not None
    ]
    return max(values) if values else None


def _violation(rows_by_batch: dict[int, dict[str, Any]], batch_ids: tuple[int, ...], field: str, mature_cutoff: int) -> bool:
    value = _max_field(rows_by_batch, batch_ids, field)
    return False if value is None else bool(value > int(mature_cutoff))


def _bank_complete(selected: dict[str, Any], keys: tuple[str, ...], expected: tuple[int, ...]) -> bool:
    return all(int(selected[key]) >= int(required) for key, required in zip(keys, expected))


def _safe_ratio_expr(numerator: str, denominator: str) -> pl.Expr:
    return (
        pl.when(pl.col(denominator) > 0)
        .then(pl.col(numerator).cast(pl.Float64) / pl.col(denominator).cast(pl.Float64))
        .otherwise(None)
    )


def _first_existing(frame: pl.DataFrame, names: tuple[str, ...]) -> str:
    for name in names:
        if name in frame.columns:
            return name
    raise ValueError(f"None of these columns exist in frame: {names}")


def _best_classifier_trial_from_run(run_root: Path) -> int | None:
    best_path = Path(run_root) / "best_config.json"
    if not best_path.exists():
        return None
    import json

    payload = json.loads(best_path.read_text())
    best = payload.get("best") or {}
    value = best.get("trial_number")
    return None if value is None else int(value)


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _empty_gate_inventory() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "batch_id": pl.Int64,
            "rows": pl.Int64,
            "batch_start_ts": pl.Datetime(time_zone="UTC"),
            "batch_end_ts": pl.Datetime(time_zone="UTC"),
            "score_pred_batch_id_min": pl.Int64,
            "score_pred_batch_id_max": pl.Int64,
            "classifier_active_rows": pl.Int64,
            "trust_tp_rows": pl.Int64,
            "reject_fp_rows": pl.Int64,
            "missed_fn_rows": pl.Int64,
            "safe_tn_rows": pl.Int64,
            "classifier_target_positive_rate": pl.Float64,
            "classifier_prob_mean": pl.Float64,
            "classifier_prob_q80": pl.Float64,
            "classifier_active_rate": pl.Float64,
            "trust_precision_among_active": pl.Float64,
            "reject_fp_rate_among_active": pl.Float64,
            "missed_fn_rate_all": pl.Float64,
        }
    )


def _run_root(args: argparse.Namespace, side: str) -> Path:
    now = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return Path(args.output_dir) / f"{now}_decision_banks_{side}"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Plan separate RPF target and gate decision banks.")
    parser.add_argument("--asset", default=None)
    parser.add_argument("--root", default=None)
    parser.add_argument("--side", choices=SIDES, required=True)
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--base-run", type=Path, required=True)
    parser.add_argument("--classifier-score-path", type=Path, required=True)
    parser.add_argument("--classifier-trial-number", type=int, default=None)
    parser.add_argument("--classifier-threshold", type=float, default=0.5)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_ROOT)
    parser.add_argument("--n-steps", type=int, default=50)
    parser.add_argument("--target-positive-batch-min-rate", type=float, default=0.80)
    parser.add_argument("--target-opposite-batch-max-rate", type=float, default=0.20)
    parser.add_argument("--target-train-positive-batches", type=int, default=80)
    parser.add_argument("--target-train-negative-batches", type=int, default=160)
    parser.add_argument("--target-val-positive-batches", type=int, default=20)
    parser.add_argument("--target-val-negative-batches", type=int, default=40)
    parser.add_argument("--gate-min-active-rows", type=int, default=10)
    parser.add_argument("--gate-trust-min-precision", type=float, default=0.70)
    parser.add_argument("--gate-reject-min-fp-rate", type=float, default=0.70)
    parser.add_argument("--gate-train-trust-batches", type=int, default=80)
    parser.add_argument("--gate-train-reject-batches", type=int, default=160)
    parser.add_argument("--gate-val-trust-batches", type=int, default=20)
    parser.add_argument("--gate-val-reject-batches", type=int, default=40)
    parser.add_argument("--candidate-lookback-batches", type=int, default=2000)
    parser.add_argument("--label-maturity-embargo-batches", type=int, default=1)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
