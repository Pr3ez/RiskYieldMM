"""Diagnose RPF features that are useful CNN sequence inputs.

This is a post-hoc diagnostic, not a train-time selector. It uses held-out
window labels to answer a narrow question: which existing RPF columns have
enough within-batch movement and target association to be worth feeding into a
causal sequence encoder?
"""

from __future__ import annotations

import argparse
import json
import math
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

from regression_feature_engineering.walkforward.ablation import FAMILY_PREFIXES, select_ablation_features
from regression_feature_engineering.walkforward.classification.data import load_joined_classification_batches
from regression_feature_engineering.walkforward.classification.targets import (
    TARGET_BINARY_UP_2X_DOWN,
    UP_EXTREME,
    positive_rule_description,
)
from regression_feature_engineering.walkforward.config import load_clean_config
from regression_feature_engineering.walkforward.data import resolve_context
from regression_feature_engineering.walkforward.metrics import _correlation, _rankdata_average
from regression_feature_engineering.walkforward.reports import write_json, write_markdown, write_trials
from regression_feature_engineering.walkforward.windows import read_windows
from scripts.project_paths import ensure_project_root_on_path


PROJECT_ROOT = ensure_project_root_on_path(Path(__file__))
OUTPUT_ROOT = PROJECT_ROOT / "test_output" / "rpf_cnn_feature_diagnostics"
TIMEFRAME_RE = re.compile(r"_(15m|1h|4h|8h|12h|1d)_")

FAST_TIMEFRAME_WEIGHT = {
    "15m": 1.00,
    "1h": 0.90,
    "4h": 0.65,
    "8h": 0.40,
    "12h": 0.30,
    "1d": 0.20,
    "tf_global": 0.55,
}

FAMILY_SEQUENCE_WEIGHT = {
    "spike_breakout": 1.00,
    "liquidity_volume_pressure": 0.95,
    "rejection_chop": 0.90,
    "acceptance_persistence": 0.85,
    "interaction_confluence": 0.75,
    "volatility_state": 0.65,
    "structural_room": 0.45,
    "temporal_memory_transforms": 0.55,
    "regime_calendar_state": 0.25,
    "cross_asset_context": 0.35,
    "unsupervised_factor_layer": 0.50,
    "sequence_embedding_layer": 0.10,
    "other": 0.35,
}


def main() -> int:
    args = parse_args()
    config = load_clean_config(args.config)
    asset = str(args.asset or config.asset)
    root = str(args.root or config.root)
    target_col = str(args.target_col)
    context = resolve_context(project_root=PROJECT_ROOT, asset=asset, root=root, target_col=UP_EXTREME)
    windows = read_windows(Path(args.base_run) / "frozen_windows.parquet")
    windows = windows[-int(args.n_steps) :] if int(args.n_steps) > 0 else windows
    if not windows:
        raise ValueError("No frozen windows selected")
    feature_columns = select_ablation_features(context.manifest.feature_columns, str(args.feature_ablation))
    run_root = run_root_for_args(args, target_col)
    run_root.mkdir(parents=True, exist_ok=True)

    print(
        "[rpf-cnn-diag] start "
        f"asset={asset} root={root} target={target_col} windows={len(windows)} "
        f"features={len(feature_columns)} run={run_root}",
        flush=True,
    )
    rows: list[dict[str, Any]] = []
    pred_batch_ids = tuple(int(window.pred_batch_id) for window in windows)
    for chunk_idx, chunk in enumerate(chunks(feature_columns, int(args.feature_chunk_size)), start=1):
        print(
            "[rpf-cnn-diag] chunk "
            f"{chunk_idx}/{math.ceil(len(feature_columns) / int(args.feature_chunk_size))} "
            f"features={len(chunk)}",
            flush=True,
        )
        frame = load_joined_classification_batches(
            context,
            pred_batch_ids,
            feature_columns=tuple(chunk),
            target_col=target_col,
        )
        rows.extend(score_feature_chunk(frame, target_col=target_col, feature_columns=tuple(chunk)))

    feature_scores = pl.DataFrame(rows, infer_schema_length=None).sort("cnn_candidate_score", descending=True)
    selected = select_cnn_panel(
        feature_scores,
        selected_count=int(args.selected_count),
        per_family_limit=int(args.per_family_limit),
        per_timeframe_limit=int(args.per_timeframe_limit),
        min_nonconstant_batch_rate=float(args.min_nonconstant_batch_rate),
    )
    summary = summarize_feature_scores(feature_scores)
    feature_scores.write_parquet(run_root / "feature_scores.parquet")
    selected.write_parquet(run_root / f"selected_cnn_panel_{int(args.selected_count)}.parquet")
    write_trials(run_root / "family_timeframe_summary.parquet", summary["family_timeframe"])
    write_trials(run_root / "family_summary.parquet", summary["family"])
    write_trials(run_root / "timeframe_summary.parquet", summary["timeframe"])
    write_json(
        run_root / f"selected_cnn_panel_{int(args.selected_count)}.json",
        {
            "schema_version": "rpf_cnn_candidate_panel_v1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "asset": asset,
            "root": root,
            "target_col": target_col,
            "positive_rule": positive_rule_description(target_col),
            "source": "post_hoc_feature_diagnostic",
            "feature_ablation": str(args.feature_ablation),
            "window_count": len(windows),
            "pred_batch_ids": list(pred_batch_ids),
            "selected_feature_count": selected.height,
            "selected_features": selected["feature"].to_list(),
            "selection_notes": [
                "Use as a CNN sequence input candidate panel only.",
                "Do not treat this as production feature selection because it uses diagnostic labels.",
                "Train-time CNN must still fit only inside each walk-forward fold.",
            ],
        },
    )
    write_markdown(
        run_root / "report.md",
        title="RPF CNN Feature Diagnostic",
        sections={
            "Scope": {
                "asset": asset,
                "root": root,
                "target_col": target_col,
                "positive_rule": positive_rule_description(target_col),
                "windows": len(windows),
                "candidate_features": len(feature_columns),
                "selected_features": selected.height,
            },
            "Interpretation": {
                "purpose": "Find fast-changing RPF features that can add causal sequence memory.",
                "not_a_model": "This report does not promote a classifier and does not fit CatBoost.",
                "main_score": "cnn_candidate_score combines within-batch variation, row ranking, batch-regime association, timeframe speed, and family prior.",
            },
            "Top Families": summary["family"][:12],
            "Top Timeframes": summary["timeframe"],
            "Top Family Timeframes": summary["family_timeframe"][:20],
            "Top Features": selected.head(40).to_dicts(),
        },
    )
    print(
        "[rpf-cnn-diag] done "
        f"run={run_root} selected={selected.height} "
        f"top_family={selected['family'][0] if selected.height else '-'}",
        flush=True,
    )
    return 0


def score_feature_chunk(frame: pl.DataFrame, *, target_col: str, feature_columns: tuple[str, ...]) -> list[dict[str, Any]]:
    y_all = frame[target_col].to_numpy().astype("int8")
    batch_all = frame["batch_id"].to_numpy().astype("int64")
    batches = sorted(int(value) for value in np.unique(batch_all))
    rows: list[dict[str, Any]] = []
    for feature in feature_columns:
        x_all = frame[feature].to_numpy().astype("float64", copy=False)
        finite_all = np.isfinite(x_all)
        if finite_all.sum() < 3:
            rows.append(empty_feature_row(feature, "too_few_finite_rows"))
            continue
        batch_rows: list[dict[str, float | int | None]] = []
        for batch_id in batches:
            mask = batch_all == int(batch_id)
            x = x_all[mask]
            y = y_all[mask]
            finite = np.isfinite(x)
            x = x[finite]
            y = y[finite]
            if x.size == 0:
                continue
            batch_rows.append(batch_feature_stats(x, y))
        rows.append(feature_score_row(feature, batch_rows))
    return rows


def batch_feature_stats(x: np.ndarray, y: np.ndarray) -> dict[str, float | int | None]:
    std = float(np.std(x)) if x.size else 0.0
    n_unique = int(len(np.unique(np.round(x, 10)))) if x.size else 0
    target_rate = float(np.mean(y)) if y.size else None
    mixed = bool(y.size and np.any(y == 1) and np.any(y == 0))
    auc = None
    auc_lift = None
    top20_lift = None
    if mixed and std > 1e-12:
        auc = rank_auc(y, x)
        auc_lift = abs(float(auc) - 0.5) * 2.0 if auc is not None else None
        top20_lift = oriented_topk_lift(y, x, k=20)
    slope = None
    if x.size >= 3 and std > 1e-12:
        t = np.arange(x.size, dtype=float)
        slope = _correlation(t, x)
    return {
        "row_count": int(x.size),
        "target_rate": target_rate,
        "std": std,
        "n_unique": n_unique,
        "nonconstant": int(std > 1e-12 and n_unique > 2),
        "mixed": int(mixed),
        "auc": auc,
        "auc_lift": auc_lift,
        "top20_lift": top20_lift,
        "mean": float(np.mean(x)) if x.size else None,
        "last": float(x[-1]) if x.size else None,
        "slope": slope,
    }


def feature_score_row(feature: str, batch_rows: list[dict[str, float | int | None]]) -> dict[str, Any]:
    if not batch_rows:
        return empty_feature_row(feature, "no_batch_rows")
    family = feature_family(feature)
    timeframe = feature_timeframe(feature)
    nonconstant_rate = mean_or_none(row["nonconstant"] for row in batch_rows) or 0.0
    unique_median = median_or_none(row["n_unique"] for row in batch_rows) or 0.0
    unique_score = min(1.0, float(unique_median) / 20.0)
    std_median = median_or_none(row["std"] for row in batch_rows) or 0.0
    mixed_count = int(sum(int(row["mixed"] or 0) for row in batch_rows))
    row_auc_lift = mean_or_none(row["auc_lift"] for row in batch_rows if row["auc_lift"] is not None) or 0.0
    top20_lift = mean_or_none(row["top20_lift"] for row in batch_rows if row["top20_lift"] is not None) or 0.0
    batch_target = np.asarray([row["target_rate"] for row in batch_rows], dtype=float)
    batch_mean = np.asarray([row["mean"] for row in batch_rows], dtype=float)
    batch_last = np.asarray([row["last"] for row in batch_rows], dtype=float)
    batch_std = np.asarray([row["std"] for row in batch_rows], dtype=float)
    batch_slope = np.asarray([0.0 if row["slope"] is None else row["slope"] for row in batch_rows], dtype=float)
    batch_corr = max(
        abs(corr_or_zero(batch_target, batch_mean)),
        abs(corr_or_zero(batch_target, batch_last)),
        abs(corr_or_zero(batch_target, batch_std)),
        abs(corr_or_zero(batch_target, batch_slope)),
    )
    family_weight = FAMILY_SEQUENCE_WEIGHT.get(family, FAMILY_SEQUENCE_WEIGHT["other"])
    timeframe_weight = FAST_TIMEFRAME_WEIGHT.get(timeframe, FAST_TIMEFRAME_WEIGHT["tf_global"])
    score = (
        0.28 * float(row_auc_lift)
        + 0.18 * min(1.0, max(0.0, float(top20_lift)))
        + 0.22 * float(nonconstant_rate)
        + 0.12 * float(unique_score)
        + 0.12 * float(batch_corr)
        + 0.05 * float(timeframe_weight)
        + 0.03 * float(family_weight)
    )
    return {
        "feature": feature,
        "family": family,
        "timeframe": timeframe,
        "cnn_candidate_score": float(score),
        "row_auc_lift_mean": float(row_auc_lift),
        "top20_lift_mean": float(top20_lift),
        "batch_target_corr_abs": float(batch_corr),
        "nonconstant_batch_rate": float(nonconstant_rate),
        "within_batch_unique_median": float(unique_median),
        "within_batch_unique_score": float(unique_score),
        "within_batch_std_median": float(std_median),
        "mixed_batch_count": int(mixed_count),
        "batch_count": int(len(batch_rows)),
        "family_sequence_weight": float(family_weight),
        "timeframe_sequence_weight": float(timeframe_weight),
        "drop_reason": None,
    }


def empty_feature_row(feature: str, reason: str) -> dict[str, Any]:
    return {
        "feature": feature,
        "family": feature_family(feature),
        "timeframe": feature_timeframe(feature),
        "cnn_candidate_score": 0.0,
        "row_auc_lift_mean": 0.0,
        "top20_lift_mean": 0.0,
        "batch_target_corr_abs": 0.0,
        "nonconstant_batch_rate": 0.0,
        "within_batch_unique_median": 0.0,
        "within_batch_unique_score": 0.0,
        "within_batch_std_median": 0.0,
        "mixed_batch_count": 0,
        "batch_count": 0,
        "family_sequence_weight": FAMILY_SEQUENCE_WEIGHT["other"],
        "timeframe_sequence_weight": FAST_TIMEFRAME_WEIGHT["tf_global"],
        "drop_reason": reason,
    }


def rank_auc(y: np.ndarray, x: np.ndarray) -> float | None:
    y = np.asarray(y, dtype=int)
    x = np.asarray(x, dtype=float)
    pos = y == 1
    neg = y == 0
    n_pos = int(pos.sum())
    n_neg = int(neg.sum())
    if n_pos == 0 or n_neg == 0 or not np.isfinite(x).all():
        return None
    ranks = _rankdata_average(x)
    # _rankdata_average returns zero-based ranks. Mann-Whitney AUC subtracts
    # the rank mass that positives would occupy if they were the lowest rows.
    auc = (float(np.sum(ranks[pos])) - n_pos * (n_pos - 1) / 2.0) / float(n_pos * n_neg)
    return float(auc)


def oriented_topk_lift(y: np.ndarray, x: np.ndarray, *, k: int) -> float | None:
    y = np.asarray(y, dtype=int)
    x = np.asarray(x, dtype=float)
    base = float(np.mean(y)) if y.size else 0.0
    if base <= 0.0 or base >= 1.0 or x.size == 0 or not np.isfinite(x).all():
        return None
    cap = min(int(k), int(x.size))
    high = y[np.argsort(-x, kind="mergesort")[:cap]].mean() / base - 1.0
    low = y[np.argsort(x, kind="mergesort")[:cap]].mean() / base - 1.0
    return float(max(high, low))


def select_cnn_panel(
    feature_scores: pl.DataFrame,
    *,
    selected_count: int,
    per_family_limit: int,
    per_timeframe_limit: int,
    min_nonconstant_batch_rate: float,
) -> pl.DataFrame:
    rows: list[dict[str, Any]] = []
    family_counts: defaultdict[str, int] = defaultdict(int)
    timeframe_counts: defaultdict[str, int] = defaultdict(int)
    eligible = feature_scores.filter(
        pl.col("drop_reason").is_null()
        & (pl.col("nonconstant_batch_rate") >= float(min_nonconstant_batch_rate))
    ).sort("cnn_candidate_score", descending=True)
    for row in eligible.iter_rows(named=True):
        family = str(row["family"])
        timeframe = str(row["timeframe"])
        if int(per_family_limit) > 0 and family_counts[family] >= int(per_family_limit):
            continue
        if int(per_timeframe_limit) > 0 and timeframe_counts[timeframe] >= int(per_timeframe_limit):
            continue
        rows.append({**row, "selected_rank": len(rows) + 1})
        family_counts[family] += 1
        timeframe_counts[timeframe] += 1
        if len(rows) >= int(selected_count):
            break
    return pl.DataFrame(rows, infer_schema_length=None)


def summarize_feature_scores(feature_scores: pl.DataFrame) -> dict[str, list[dict[str, Any]]]:
    filtered = feature_scores.filter(pl.col("drop_reason").is_null())
    family = (
        filtered.group_by("family")
        .agg(
            pl.len().alias("feature_count"),
            pl.col("cnn_candidate_score").mean().alias("score_mean"),
            pl.col("cnn_candidate_score").max().alias("score_max"),
            pl.col("row_auc_lift_mean").mean().alias("row_auc_lift_mean"),
            pl.col("batch_target_corr_abs").mean().alias("batch_target_corr_abs_mean"),
            pl.col("nonconstant_batch_rate").mean().alias("nonconstant_batch_rate_mean"),
        )
        .sort("score_mean", descending=True)
        .to_dicts()
    )
    timeframe = (
        filtered.group_by("timeframe")
        .agg(
            pl.len().alias("feature_count"),
            pl.col("cnn_candidate_score").mean().alias("score_mean"),
            pl.col("cnn_candidate_score").max().alias("score_max"),
            pl.col("row_auc_lift_mean").mean().alias("row_auc_lift_mean"),
            pl.col("batch_target_corr_abs").mean().alias("batch_target_corr_abs_mean"),
            pl.col("nonconstant_batch_rate").mean().alias("nonconstant_batch_rate_mean"),
        )
        .sort("score_mean", descending=True)
        .to_dicts()
    )
    family_timeframe = (
        filtered.group_by(["family", "timeframe"])
        .agg(
            pl.len().alias("feature_count"),
            pl.col("cnn_candidate_score").mean().alias("score_mean"),
            pl.col("cnn_candidate_score").max().alias("score_max"),
            pl.col("row_auc_lift_mean").mean().alias("row_auc_lift_mean"),
            pl.col("batch_target_corr_abs").mean().alias("batch_target_corr_abs_mean"),
            pl.col("nonconstant_batch_rate").mean().alias("nonconstant_batch_rate_mean"),
        )
        .sort("score_mean", descending=True)
        .to_dicts()
    )
    return {"family": family, "timeframe": timeframe, "family_timeframe": family_timeframe}


def feature_family(feature: str) -> str:
    for family, prefixes in FAMILY_PREFIXES.items():
        if feature.startswith(prefixes):
            return family
    return "other"


def feature_timeframe(feature: str) -> str:
    match = TIMEFRAME_RE.search(str(feature))
    return match.group(1) if match else "tf_global"


def corr_or_zero(y: np.ndarray, x: np.ndarray) -> float:
    mask = np.isfinite(y) & np.isfinite(x)
    if int(mask.sum()) < 3:
        return 0.0
    if float(np.std(y[mask])) <= 1e-12 or float(np.std(x[mask])) <= 1e-12:
        return 0.0
    return float(_correlation(y[mask], x[mask]) or 0.0)


def mean_or_none(values: Any) -> float | None:
    cleaned = [float(value) for value in values if value is not None and np.isfinite(float(value))]
    return float(np.mean(cleaned)) if cleaned else None


def median_or_none(values: Any) -> float | None:
    cleaned = [float(value) for value in values if value is not None and np.isfinite(float(value))]
    return float(np.median(cleaned)) if cleaned else None


def chunks(values: tuple[str, ...], size: int) -> list[tuple[str, ...]]:
    size = max(1, int(size))
    return [tuple(values[start : start + size]) for start in range(0, len(values), size)]


def run_root_for_args(args: argparse.Namespace, target_col: str) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    target_slug = str(target_col).replace("target_", "").replace("classification_", "")[:56]
    return Path(args.output_dir) / f"{timestamp}_cnn_feature_diagnostic_{target_slug}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Diagnose RPF features as CNN sequence-input candidates.")
    parser.add_argument("--asset", default=None)
    parser.add_argument("--root", default=None)
    parser.add_argument("--target-col", default=TARGET_BINARY_UP_2X_DOWN)
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--base-run", type=Path, required=True)
    parser.add_argument("--feature-ablation", default="all")
    parser.add_argument("--n-steps", type=int, default=30)
    parser.add_argument("--feature-chunk-size", type=int, default=96)
    parser.add_argument("--selected-count", type=int, default=160)
    parser.add_argument("--per-family-limit", type=int, default=45)
    parser.add_argument("--per-timeframe-limit", type=int, default=45)
    parser.add_argument("--min-nonconstant-batch-rate", type=float, default=0.25)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_ROOT)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
