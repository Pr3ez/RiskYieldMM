#!/usr/bin/env python3
"""Causal ensemble benchmark harness (baseline-first, attention-second).

Methods evaluated under the same walk-forward protocol:
- online_ewaf_logloss
- online_ewaf_brier
- regularized_stacker_logit
- regularized_stacker_gbm
- causal_attention_gate_small
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import polars as pl
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression

DEFAULT_PROJECT_ROOT = Path("/media/przem/linux_data/RiskYieldMM (Copy)")
DEFAULT_OUTPUT_ROOT = "prediction_analysis/multitimeframe_causal_benchmark_outputs"
EXPECTED_UNITS = [
    "1m/target_4class",
    "1m/target_breakfree",
    "5m/target_4class",
    "5m/target_breakfree",
    "15m/target_4class",
    "15m/target_breakfree",
]
ROW_POS_BY_TIMEFRAME = {"1m": 15, "5m": 3, "15m": 1}
TIMESTAMP_OFFSET_MIN = {"1m": 14, "5m": 10, "15m": 0}

LABEL_UP = 0
LABEL_DOWN = 1
LABEL_HOLD = 2

HEAD_BF_CLASSES = 3
HEAD_4DIR_CLASSES = 2

METHODS_AVAILABLE = [
    "online_ewaf_logloss",
    "online_ewaf_brier",
    "online_sparse_ewaf_brier",
    "regularized_stacker_logit",
    "regularized_stacker_gbm",
    "causal_attention_gate_small",
]


@dataclass(frozen=True)
class DatasetBundle:
    anchor_df: pl.DataFrame
    pred_batch: np.ndarray
    truth_breakfree: np.ndarray
    truth_4dir: np.ndarray
    truth_final: np.ndarray
    breakfree_probs: np.ndarray  # shape [N, E_bf, 3]
    dir4_probs: np.ndarray  # shape [N, E_4d, 2]
    breakfree_experts: list[str]
    dir4_experts: list[str]


@dataclass(frozen=True)
class RunInputs:
    project_root: Path
    ensemble_run_dir: Path
    candidate_search_run_dir: Path
    out_dir: Path


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Causal multi-target multi-timeframe ensemble benchmark (risk-first)."
    )
    p.add_argument("--project-root", type=str, default=str(DEFAULT_PROJECT_ROOT))
    p.add_argument(
        "--ensemble-run-dir",
        type=str,
        default="",
        help="Path to multitimeframe_ensemble_outputs run dir (default: latest).",
    )
    p.add_argument(
        "--candidate-search-run-dir",
        type=str,
        required=True,
        help="Path to candidate_search_v2 run dir with 6-unit candidate12 files.",
    )
    p.add_argument("--output-dir", type=str, default=DEFAULT_OUTPUT_ROOT)
    p.add_argument("--output-tag", type=str, default="")
    p.add_argument(
        "--alignment-mode",
        type=str,
        default="same_period_close",
        choices=["same_period_close"],
    )
    p.add_argument("--wf-warmup-batches", type=int, default=120)
    p.add_argument("--wf-step-size", type=int, default=1)
    p.add_argument("--purge-batches", type=int, default=0)
    p.add_argument("--embargo-batches", type=int, default=0)
    p.add_argument(
        "--methods",
        type=str,
        default=",".join(METHODS_AVAILABLE),
        help="Comma list of methods.",
    )
    p.add_argument(
        "--risk-objective",
        type=str,
        default="risk_first",
        choices=["risk_first"],
    )
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--val-tail-ratio", type=float, default=0.20)
    p.add_argument("--ewaf-eta", type=float, default=2.0)
    p.add_argument(
        "--allow-missing-aligned",
        action="store_true",
        help=(
            "Allow missing anchor-candidate rows by filling missing probabilities "
            "with uniform priors. Keeps causality, relaxes strict completeness."
        ),
    )
    p.add_argument(
        "--ewaf-sparse-topk",
        type=int,
        default=3,
        help="Top-k experts kept active for online_sparse_ewaf_brier prediction.",
    )
    p.add_argument(
        "--disable-temperature-scaling",
        action="store_true",
        help="Disable per-head temperature scaling for stacker/attention methods.",
    )
    p.add_argument("--attn-hidden-dim", type=int, default=32)
    p.add_argument("--attn-max-epochs", type=int, default=40)
    p.add_argument("--attn-batch-size", type=int, default=1024)
    p.add_argument("--linear-issue-url", type=str, default="")
    p.add_argument("--notion-page-url", type=str, default="")
    p.add_argument("--run-command", type=str, default="")
    p.add_argument("--verbose", action="store_true")
    args = p.parse_args()

    if int(args.wf_warmup_batches) < 1:
        raise ValueError("--wf-warmup-batches must be >= 1")
    if int(args.wf_step_size) < 1:
        raise ValueError("--wf-step-size must be >= 1")
    if int(args.purge_batches) < 0 or int(args.embargo_batches) < 0:
        raise ValueError("--purge-batches and --embargo-batches must be >= 0")
    if not (0.0 < float(args.val_tail_ratio) < 0.5):
        raise ValueError("--val-tail-ratio must be in (0, 0.5)")
    if float(args.ewaf_eta) <= 0.0:
        raise ValueError("--ewaf-eta must be > 0")
    if int(args.ewaf_sparse_topk) < 1:
        raise ValueError("--ewaf-sparse-topk must be >= 1")

    methods = [m.strip() for m in str(args.methods).split(",") if m.strip()]
    unknown = sorted(set(methods) - set(METHODS_AVAILABLE))
    if unknown:
        raise ValueError(f"Unknown methods: {unknown}")
    args.methods = methods
    return args


def _normalize_units(units: Iterable[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in units:
        for part in str(raw).split(","):
            unit = part.strip()
            if not unit:
                continue
            if unit not in seen:
                seen.add(unit)
                out.append(unit)
    return out


def _resolve_ensemble_run_dir(project_root: Path, arg: str) -> Path:
    root = project_root / "prediction_analysis" / "multitimeframe_ensemble_outputs"
    if arg:
        p = Path(arg).expanduser()
        if p.exists():
            return p.resolve()
        p2 = root / arg
        if p2.exists():
            return p2.resolve()
        raise FileNotFoundError(f"ensemble run dir not found: {arg}")
    runs = sorted([p for p in root.glob("20*") if p.is_dir()])
    if not runs:
        raise FileNotFoundError(f"No ensemble runs under {root}")
    return runs[-1].resolve()


def _resolve_inputs(args: argparse.Namespace) -> RunInputs:
    project_root = Path(args.project_root).expanduser().resolve()
    ensemble_run_dir = _resolve_ensemble_run_dir(project_root, str(args.ensemble_run_dir))

    candidate_search_run_dir = Path(args.candidate_search_run_dir).expanduser()
    if not candidate_search_run_dir.exists():
        alt = (
            project_root
            / "data"
            / "htf_backtest_results"
            / "stage1_catboost_live"
            / "catboost"
            / "candidate_search_v2"
            / str(args.candidate_search_run_dir)
        )
        if not alt.exists():
            raise FileNotFoundError(f"candidate-search run dir not found: {args.candidate_search_run_dir}")
        candidate_search_run_dir = alt

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    tag = str(args.output_tag).strip().replace(" ", "_")
    out_dir = project_root / str(args.output_dir) / (f"{stamp}_{tag}" if tag else stamp)
    out_dir.mkdir(parents=True, exist_ok=True)

    return RunInputs(
        project_root=project_root,
        ensemble_run_dir=ensemble_run_dir.resolve(),
        candidate_search_run_dir=candidate_search_run_dir.resolve(),
        out_dir=out_dir.resolve(),
    )


def _load_candidate12_map(candidate_search_run_dir: Path) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for unit in EXPECTED_UNITS:
        tf, target = unit.split("/", 1)
        p = candidate_search_run_dir / tf / target / "candidate12_v2.parquet"
        if not p.exists():
            raise FileNotFoundError(f"Missing candidate12 file for {unit}: {p}")
        df = pl.read_parquet(p).select("action_key").drop_nulls().unique().sort("action_key")
        keys = [str(v) for v in df["action_key"].to_list()]
        if len(keys) != 12:
            raise ValueError(f"{unit} candidate12 count must be 12, got {len(keys)}")
        out[unit] = keys
    return out


def _safe_expert_key(unit: str, action_key: str) -> str:
    return f"{unit.replace('/', '__')}__{action_key}"


def _fail_with_report(report_path: Path, report: dict[str, Any], message: str) -> None:
    report_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    raise RuntimeError(message)


def _build_aligned_dataset(
    *,
    ensemble_run_dir: Path,
    candidate12_map: dict[str, list[str]],
    leakage_report_path: Path,
    allow_missing_aligned: bool,
) -> DatasetBundle:
    report: dict[str, Any] = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "passed": False,
        "checks": {},
        "samples": {},
    }

    rows_path = ensemble_run_dir / "unit_prediction_rows_dedup.parquet"
    if not rows_path.exists():
        _fail_with_report(leakage_report_path, report, f"Missing input parquet: {rows_path}")

    needed_cols = [
        "pred_batch",
        "timestamp",
        "anchor_15m_ts",
        "unit",
        "timeframe",
        "target",
        "action_key",
        "y_true",
        "prob_class_0",
        "prob_class_1",
        "prob_class_2",
        "prob_class_3",
    ]

    lf = pl.scan_parquet(rows_path).select(needed_cols)
    cond = None
    for unit, keys in candidate12_map.items():
        c = (pl.col("unit") == unit) & (pl.col("action_key").is_in(keys))
        cond = c if cond is None else (cond | c)
    lf = lf.filter(cond & pl.col("anchor_15m_ts").is_not_null())

    # same_period_close row-position selection per unit/action/anchor.
    group_cols = ["pred_batch", "unit", "action_key", "anchor_15m_ts"]
    lf = (
        lf.sort(group_cols + ["timestamp"])
        .with_columns(
            [
                pl.col("timestamp")
                .rank(method="ordinal")
                .over(group_cols)
                .cast(pl.Int64)
                .alias("row_pos"),
                pl.len().over(group_cols).alias("rows_in_anchor"),
            ]
        )
        .with_columns(
            pl.when(pl.col("timeframe") == "1m")
            .then(pl.lit(15))
            .when(pl.col("timeframe") == "5m")
            .then(pl.lit(3))
            .when(pl.col("timeframe") == "15m")
            .then(pl.lit(1))
            .otherwise(pl.lit(-1))
            .alias("required_row_pos")
        )
        .filter(pl.col("row_pos") == pl.col("required_row_pos"))
    )

    # as-of/anchor integrity check for exact same_period_close timestamp expectations.
    expected_ts_expr = (
        pl.when(pl.col("timeframe") == "1m")
        .then(pl.col("anchor_15m_ts") + pl.duration(minutes=TIMESTAMP_OFFSET_MIN["1m"]))
        .when(pl.col("timeframe") == "5m")
        .then(pl.col("anchor_15m_ts") + pl.duration(minutes=TIMESTAMP_OFFSET_MIN["5m"]))
        .when(pl.col("timeframe") == "15m")
        .then(pl.col("anchor_15m_ts") + pl.duration(minutes=TIMESTAMP_OFFSET_MIN["15m"]))
        .otherwise(pl.col("anchor_15m_ts"))
    )
    with_expected = lf.with_columns(expected_ts_expr.alias("expected_timestamp"))
    asof_bad = with_expected.filter(pl.col("timestamp") != pl.col("expected_timestamp")).collect()

    report["checks"]["asof_violation_count"] = int(asof_bad.height)
    if asof_bad.height > 0:
        report["samples"]["asof_violations_head"] = asof_bad.head(30).to_dicts()
        _fail_with_report(
            leakage_report_path,
            report,
            "as-of alignment violations detected for same_period_close",
        )

    selected = with_expected.drop("expected_timestamp").collect()
    if selected.is_empty():
        _fail_with_report(leakage_report_path, report, "No rows after same_period_close selection")

    # anchor-level completeness: require 72 rows per anchor (6 units x 12 candidates)
    keys = ["pred_batch", "anchor_15m_ts"]
    anchor_counts = selected.group_by(keys).agg(pl.len().alias("n_rows"))
    bad_anchors = anchor_counts.filter(pl.col("n_rows") != 72)
    report["checks"]["anchor_count_bad"] = int(bad_anchors.height)
    report["checks"]["anchor_count_min"] = int(anchor_counts["n_rows"].min())
    report["checks"]["anchor_count_max"] = int(anchor_counts["n_rows"].max())
    if bad_anchors.height > 0:
        report["samples"]["bad_anchors_head"] = bad_anchors.head(30).to_dicts()

        # Build first missing pairs sample for easier debugging.
        anchors = anchor_counts.select(keys)
        exp_rows: list[dict[str, Any]] = []
        for unit, action_keys in candidate12_map.items():
            for ak in action_keys:
                exp_rows.append({"unit": unit, "action_key": ak})
        expected_pairs = pl.DataFrame(exp_rows)
        expected = anchors.join(expected_pairs, how="cross")
        present = selected.select(keys + ["unit", "action_key"]).unique()
        missing = expected.join(
            present,
            on=keys + ["unit", "action_key"],
            how="anti",
        )
        report["checks"]["missing_anchor_candidate_rows"] = int(missing.height)
        report["samples"]["missing_anchor_candidate_rows_head"] = missing.head(50).to_dicts()
        if not bool(allow_missing_aligned):
            _fail_with_report(
                leakage_report_path,
                report,
                "Strict completeness failed: missing anchor-candidate rows",
            )
    else:
        report["checks"]["missing_anchor_candidate_rows"] = 0

    selected = selected.with_columns(
        _safe_expert_key_expr=pl.concat_str(
            [
                pl.col("unit").str.replace_all("/", "__"),
                pl.lit("__"),
                pl.col("action_key"),
            ],
            separator="",
        )
    ).rename({"_safe_expert_key_expr": "expert_key"})

    # Anchor keys and truths.
    anchor_df = selected.select(keys).unique().sort(keys)

    truth_bf = (
        selected.filter(pl.col("unit") == "15m/target_breakfree")
        .group_by(keys)
        .agg(pl.first("y_true").cast(pl.Int64).alias("truth_breakfree"))
    )
    truth_4 = (
        selected.filter(pl.col("unit") == "15m/target_4class")
        .group_by(keys)
        .agg(pl.first("y_true").cast(pl.Int64).alias("truth_4class_raw"))
        .with_columns(
            pl.when(pl.col("truth_4class_raw").is_in([2, 3]))
            .then(pl.lit(1))
            .otherwise(pl.lit(0))
            .alias("truth_4dir")
        )
        .drop("truth_4class_raw")
    )

    anchor_df = anchor_df.join(truth_bf, on=keys, how="left").join(truth_4, on=keys, how="left")
    has_missing_truth = (
        anchor_df.select(
            pl.any_horizontal(
                pl.col("truth_breakfree").is_null(),
                pl.col("truth_4dir").is_null(),
            )
            .any()
            .alias("has_missing_truth")
        )
        .item(0, 0)
    )
    if bool(has_missing_truth):
        _fail_with_report(
            leakage_report_path,
            report,
            "Missing truth labels for some anchors (15m truth extraction failed)",
        )

    anchor_df = anchor_df.with_columns(
        [
            pl.when(pl.col("truth_breakfree") == 0)
            .then(pl.lit(LABEL_UP))
            .when(pl.col("truth_breakfree") == 1)
            .then(pl.lit(LABEL_DOWN))
            .otherwise(pl.lit(LABEL_HOLD))
            .alias("truth_breakfree_label"),
            pl.when(pl.col("truth_breakfree") == 2)
            .then(pl.lit(LABEL_HOLD))
            .when((pl.col("truth_breakfree") == 0) & (pl.col("truth_4dir") == 1))
            .then(pl.lit(LABEL_UP))
            .when((pl.col("truth_breakfree") == 1) & (pl.col("truth_4dir") == 0))
            .then(pl.lit(LABEL_DOWN))
            .otherwise(pl.lit(LABEL_HOLD))
            .alias("truth_final"),
        ]
    )

    # Build expert lists and pivoted probability tables.
    breakfree_units = [u for u in EXPECTED_UNITS if u.endswith("target_breakfree")]
    dir4_units = [u for u in EXPECTED_UNITS if u.endswith("target_4class")]

    bf_experts = sorted(
        _safe_expert_key(u, ak)
        for u in breakfree_units
        for ak in candidate12_map[u]
    )
    d4_experts = sorted(
        _safe_expert_key(u, ak)
        for u in dir4_units
        for ak in candidate12_map[u]
    )

    bf_base = selected.filter(pl.col("target") == "target_breakfree")
    d4_base = selected.filter(pl.col("target") == "target_4class").with_columns(
        [
            (pl.col("prob_class_0") + pl.col("prob_class_1")).alias("p_down"),
            (pl.col("prob_class_2") + pl.col("prob_class_3")).alias("p_up"),
        ]
    )

    def _pivot_prob(base: pl.DataFrame, value_col: str, prefix: str) -> pl.DataFrame:
        pv = (
            base.select(keys + ["expert_key", value_col])
            .pivot(index=keys, on="expert_key", values=value_col, aggregate_function="first")
        )
        ren = {c: f"{prefix}__{c}" for c in pv.columns if c not in keys}
        return pv.rename(ren)

    bf_p0 = _pivot_prob(bf_base, "prob_class_0", "bf_p0")
    bf_p1 = _pivot_prob(bf_base, "prob_class_1", "bf_p1")
    bf_p2 = _pivot_prob(bf_base, "prob_class_2", "bf_p2")

    d4_pd = _pivot_prob(d4_base, "p_down", "d4_pdown")
    d4_pu = _pivot_prob(d4_base, "p_up", "d4_pup")

    feat_df = anchor_df.join(bf_p0, on=keys, how="left")
    feat_df = feat_df.join(bf_p1, on=keys, how="left")
    feat_df = feat_df.join(bf_p2, on=keys, how="left")
    feat_df = feat_df.join(d4_pd, on=keys, how="left")
    feat_df = feat_df.join(d4_pu, on=keys, how="left")
    feat_df = feat_df.sort(keys)

    bf_cols0 = [f"bf_p0__{e}" for e in bf_experts]
    bf_cols1 = [f"bf_p1__{e}" for e in bf_experts]
    bf_cols2 = [f"bf_p2__{e}" for e in bf_experts]
    d4_cols_down = [f"d4_pdown__{e}" for e in d4_experts]
    d4_cols_up = [f"d4_pup__{e}" for e in d4_experts]

    for colset in [bf_cols0, bf_cols1, bf_cols2, d4_cols_down, d4_cols_up]:
        missing = [c for c in colset if c not in feat_df.columns]
        if missing:
            if not bool(allow_missing_aligned):
                report["samples"]["missing_feature_columns"] = missing[:30]
                _fail_with_report(
                    leakage_report_path,
                    report,
                    "Pivoted feature matrix missing expected expert columns",
                )
            feat_df = feat_df.with_columns([pl.lit(None).cast(pl.Float64).alias(c) for c in missing])

    bf0 = feat_df.select(bf_cols0).to_numpy().astype(np.float64)
    bf1 = feat_df.select(bf_cols1).to_numpy().astype(np.float64)
    bf2 = feat_df.select(bf_cols2).to_numpy().astype(np.float64)
    breakfree_probs = np.stack([bf0, bf1, bf2], axis=2)

    d4d = feat_df.select(d4_cols_down).to_numpy().astype(np.float64)
    d4u = feat_df.select(d4_cols_up).to_numpy().astype(np.float64)
    dir4_probs = np.stack([d4d, d4u], axis=2)

    if np.isnan(breakfree_probs).any() or np.isnan(dir4_probs).any():
        report["checks"]["nan_breakfree_probs"] = int(np.isnan(breakfree_probs).sum())
        report["checks"]["nan_dir4_probs"] = int(np.isnan(dir4_probs).sum())
        if not bool(allow_missing_aligned):
            _fail_with_report(
                leakage_report_path,
                report,
                "NaNs in aligned probability tensors (completeness violation)",
            )
        breakfree_probs = np.nan_to_num(breakfree_probs, nan=(1.0 / 3.0))
        dir4_probs = np.nan_to_num(dir4_probs, nan=(1.0 / 2.0))

    report["checks"].update(
        {
            "anchor_rows": int(feat_df.height),
            "breakfree_experts": int(len(bf_experts)),
            "dir4_experts": int(len(d4_experts)),
            "asof_violation_count": int(report["checks"].get("asof_violation_count", 0)),
            "missing_anchor_candidate_rows": int(report["checks"].get("missing_anchor_candidate_rows", 0)),
            "allow_missing_aligned": bool(allow_missing_aligned),
        }
    )
    report["passed"] = True
    leakage_report_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    return DatasetBundle(
        anchor_df=feat_df.select(keys + ["truth_breakfree", "truth_4dir", "truth_breakfree_label", "truth_final"]),
        pred_batch=feat_df["pred_batch"].to_numpy().astype(np.int64),
        truth_breakfree=feat_df["truth_breakfree_label"].to_numpy().astype(np.int64),
        truth_4dir=feat_df["truth_4dir"].to_numpy().astype(np.int64),
        truth_final=feat_df["truth_final"].to_numpy().astype(np.int64),
        breakfree_probs=breakfree_probs,
        dir4_probs=dir4_probs,
        breakfree_experts=bf_experts,
        dir4_experts=d4_experts,
    )


def _softmax(z: np.ndarray, axis: int = -1) -> np.ndarray:
    z = z - np.max(z, axis=axis, keepdims=True)
    ez = np.exp(z)
    s = np.sum(ez, axis=axis, keepdims=True)
    s = np.clip(s, 1e-12, None)
    return ez / s


def _apply_temperature(probs: np.ndarray, temperature: float) -> np.ndarray:
    if not np.isfinite(temperature) or temperature <= 0.0:
        return probs
    logits = np.log(np.clip(probs, 1e-12, 1.0))
    return _softmax(logits / float(temperature), axis=1)


def _nll_loss(probs: np.ndarray, y: np.ndarray) -> float:
    idx = np.arange(len(y))
    p = np.clip(probs[idx, y], 1e-12, 1.0)
    return float(-np.mean(np.log(p)))


def _fit_temperature_grid(probs_val: np.ndarray, y_val: np.ndarray) -> tuple[float, float, float]:
    if len(y_val) < 16:
        base = _nll_loss(probs_val, y_val)
        return 1.0, base, base
    grid = np.linspace(0.5, 3.0, 51)
    best_t = 1.0
    best_nll = float("inf")
    base_nll = _nll_loss(probs_val, y_val)
    for t in grid:
        p = _apply_temperature(probs_val, float(t))
        nll = _nll_loss(p, y_val)
        if nll < best_nll:
            best_nll = nll
            best_t = float(t)
    return best_t, base_nll, best_nll


def _predict_proba_full(model: Any, x: np.ndarray, n_classes: int) -> np.ndarray:
    out = np.zeros((x.shape[0], n_classes), dtype=np.float64)
    probs = model.predict_proba(x)
    classes = [int(c) for c in list(model.classes_)]
    for i, c in enumerate(classes):
        out[:, c] = probs[:, i]
    # If any class missing, keep epsilon and renormalize.
    out = np.clip(out, 1e-12, 1.0)
    out = out / np.sum(out, axis=1, keepdims=True)
    return out


def _majority_fallback(y_train: np.ndarray, n_eval: int, n_classes: int) -> np.ndarray:
    vals, counts = np.unique(y_train, return_counts=True)
    majority = int(vals[np.argmax(counts)])
    probs = np.full((n_eval, n_classes), 1e-9, dtype=np.float64)
    probs[:, majority] = 1.0
    probs = probs / np.sum(probs, axis=1, keepdims=True)
    return probs


def _split_train_val_indices(n: int, val_tail_ratio: float) -> tuple[np.ndarray, np.ndarray]:
    val_n = max(16, int(math.ceil(n * float(val_tail_ratio))))
    val_n = min(val_n, max(1, n - 16))
    fit_n = n - val_n
    fit_idx = np.arange(0, fit_n, dtype=np.int64)
    val_idx = np.arange(fit_n, n, dtype=np.int64)
    return fit_idx, val_idx


def _fit_predict_stacker(
    *,
    method: str,
    train_x: np.ndarray,
    train_y: np.ndarray,
    eval_x: np.ndarray,
    n_classes: int,
    val_tail_ratio: float,
    seed: int,
    apply_temperature: bool,
) -> tuple[np.ndarray, dict[str, Any]]:
    if len(np.unique(train_y)) < 2 or train_x.shape[0] < 64:
        probs = _majority_fallback(train_y, eval_x.shape[0], n_classes)
        return probs, {"fallback_majority": True, "temperature": 1.0, "val_nll_before": None, "val_nll_after": None}

    fit_idx, val_idx = _split_train_val_indices(len(train_y), val_tail_ratio)
    x_fit = train_x[fit_idx]
    y_fit = train_y[fit_idx]
    x_val = train_x[val_idx]
    y_val = train_y[val_idx]

    if method == "regularized_stacker_logit":
        model = LogisticRegression(
            C=0.2,
            solver="lbfgs",
            max_iter=500,
            random_state=int(seed),
        )
    elif method == "regularized_stacker_gbm":
        model = HistGradientBoostingClassifier(
            max_depth=4,
            learning_rate=0.05,
            max_iter=200,
            l2_regularization=1.0,
            random_state=int(seed),
        )
    else:
        raise ValueError(f"Unsupported stacker method: {method}")

    model.fit(x_fit, y_fit)
    p_val = _predict_proba_full(model, x_val, n_classes)
    t, nll_before, nll_after = _fit_temperature_grid(p_val, y_val)
    if not apply_temperature:
        t = 1.0
        nll_after = nll_before

    # Refit on full history (still leakage-safe), apply temperature calibrated on history tail.
    model.fit(train_x, train_y)
    p_eval = _predict_proba_full(model, eval_x, n_classes)
    if apply_temperature:
        p_eval = _apply_temperature(p_eval, t)

    return p_eval, {
        "fallback_majority": False,
        "temperature": float(t),
        "val_nll_before": float(nll_before),
        "val_nll_after": float(nll_after),
    }


def _fit_predict_attention_gate(
    *,
    train_probs: np.ndarray,  # [N,E,C]
    train_y: np.ndarray,
    eval_probs: np.ndarray,
    n_classes: int,
    val_tail_ratio: float,
    seed: int,
    hidden_dim: int,
    max_epochs: int,
    batch_size: int,
    apply_temperature: bool,
) -> tuple[np.ndarray, dict[str, Any]]:
    if len(np.unique(train_y)) < 2 or train_probs.shape[0] < 128:
        probs = _majority_fallback(train_y, eval_probs.shape[0], n_classes)
        return probs, {"fallback_majority": True, "temperature": 1.0, "val_nll_before": None, "val_nll_after": None}

    import torch
    import torch.nn as nn

    torch.manual_seed(int(seed))
    np.random.seed(int(seed))

    fit_idx, val_idx = _split_train_val_indices(len(train_y), val_tail_ratio)

    x_all = np.nan_to_num(train_probs.astype(np.float32), nan=1.0 / float(n_classes))
    x_fit = x_all[fit_idx]
    y_fit = train_y[fit_idx]
    x_val = x_all[val_idx]
    y_val = train_y[val_idx]
    x_eval = np.nan_to_num(eval_probs.astype(np.float32), nan=1.0 / float(n_classes))

    class AttentionGateSmall(nn.Module):
        def __init__(self, c: int, hidden: int):
            super().__init__()
            self.scorer = nn.Sequential(
                nn.Linear(c, hidden),
                nn.ReLU(),
                nn.Linear(hidden, 1),
            )
            self.class_bias = nn.Parameter(torch.zeros(c, dtype=torch.float32))

        def forward(self, x: torch.Tensor) -> torch.Tensor:
            # x: [B,E,C]
            scores = self.scorer(x).squeeze(-1)
            w = torch.softmax(scores, dim=1)
            pooled = (w.unsqueeze(-1) * x).sum(dim=1)
            logits = torch.log(torch.clamp(pooled, min=1e-6)) + self.class_bias
            return logits

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = AttentionGateSmall(c=n_classes, hidden=int(hidden_dim)).to(device)
    optim = torch.optim.Adam(model.parameters(), lr=5e-3, weight_decay=1e-4)
    criterion = nn.CrossEntropyLoss()

    x_fit_t = torch.from_numpy(x_fit).to(device)
    y_fit_t = torch.from_numpy(y_fit.astype(np.int64)).to(device)
    x_val_t = torch.from_numpy(x_val).to(device)
    y_val_t = torch.from_numpy(y_val.astype(np.int64)).to(device)

    best_state = None
    best_val = float("inf")
    bad_epochs = 0
    patience = 5

    n_fit = x_fit_t.shape[0]
    for _epoch in range(int(max_epochs)):
        model.train()
        perm = torch.randperm(n_fit, device=device)
        for start in range(0, n_fit, int(batch_size)):
            idx = perm[start : start + int(batch_size)]
            xb = x_fit_t[idx]
            yb = y_fit_t[idx]
            optim.zero_grad(set_to_none=True)
            logits = model(xb)
            loss = criterion(logits, yb)
            loss.backward()
            optim.step()

        model.eval()
        with torch.no_grad():
            val_logits = model(x_val_t)
            val_loss = criterion(val_logits, y_val_t).item()
        if val_loss + 1e-6 < best_val:
            best_val = val_loss
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
            bad_epochs = 0
        else:
            bad_epochs += 1
            if bad_epochs >= patience:
                break

    if best_state is not None:
        model.load_state_dict(best_state)

    model.eval()
    with torch.no_grad():
        val_logits = model(x_val_t).detach().cpu().numpy()
        eval_logits = model(torch.from_numpy(x_eval).to(device)).detach().cpu().numpy()

    p_val = _softmax(val_logits, axis=1)
    t, nll_before, nll_after = _fit_temperature_grid(p_val, y_val)
    if not apply_temperature:
        t = 1.0
        nll_after = nll_before
    p_eval = _softmax(eval_logits, axis=1)
    if apply_temperature:
        p_eval = _apply_temperature(p_eval, t)

    return p_eval, {
        "fallback_majority": False,
        "temperature": float(t),
        "val_nll_before": float(nll_before),
        "val_nll_after": float(nll_after),
    }


def _predict_online_ewaf(
    *,
    train_probs: np.ndarray,  # [N,E,C]
    train_y: np.ndarray,
    eval_probs: np.ndarray,
    loss_mode: str,
    eta: float,
    sparse_topk: int | None = None,
) -> np.ndarray:
    n_train, n_exp, n_cls = train_probs.shape
    weights = np.full(n_exp, 1.0 / max(1, n_exp), dtype=np.float64)

    for i in range(n_train):
        p = train_probs[i]
        avail = np.isfinite(p).all(axis=1)
        if not np.any(avail):
            continue
        pa = np.clip(p[avail], 1e-12, 1.0)
        y = int(train_y[i])
        if loss_mode == "logloss":
            losses = -np.log(pa[:, y])
        elif loss_mode == "brier":
            y_one = np.zeros(n_cls, dtype=np.float64)
            y_one[y] = 1.0
            losses = np.sum((pa - y_one[None, :]) ** 2, axis=1)
        else:
            raise ValueError(f"Unsupported EWAF loss mode: {loss_mode}")

        w_av = weights[avail] * np.exp(-float(eta) * losses)
        weights[avail] = w_av
        weights = np.clip(weights, 1e-12, None)
        weights = weights / np.sum(weights)

    n_eval = eval_probs.shape[0]
    out = np.full((n_eval, n_cls), 1.0 / n_cls, dtype=np.float64)
    for i in range(n_eval):
        p = eval_probs[i]
        avail = np.isfinite(p).all(axis=1)
        if not np.any(avail):
            continue
        w = weights * avail.astype(np.float64)
        s = np.sum(w)
        if s <= 0:
            continue
        if sparse_topk is not None and int(sparse_topk) > 0:
            avail_idx = np.flatnonzero(w > 0.0)
            if avail_idx.size > int(sparse_topk):
                top_local = np.argpartition(w[avail_idx], -int(sparse_topk))[-int(sparse_topk) :]
                keep = avail_idx[top_local]
                sparse_w = np.zeros_like(w)
                sparse_w[keep] = w[keep]
                w = sparse_w
                s = np.sum(w)
                if s <= 0:
                    continue
        w = w / s
        p_clip = np.clip(np.nan_to_num(p, nan=1.0 / n_cls), 1e-12, 1.0)
        out[i] = np.sum(w[:, None] * p_clip, axis=0)
        out[i] = out[i] / np.sum(out[i])
    return out


def _build_head_features(probs: np.ndarray) -> np.ndarray:
    # flatten [N,E,C] -> [N, E*C]
    x = np.nan_to_num(probs, nan=0.0).reshape(probs.shape[0], -1)
    return x.astype(np.float64, copy=False)


def _predict_heads_for_method(
    *,
    method: str,
    train_idx: np.ndarray,
    eval_idx: np.ndarray,
    bundle: DatasetBundle,
    args: argparse.Namespace,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, dict[str, Any]]:
    bf_train = bundle.breakfree_probs[train_idx]
    bf_eval = bundle.breakfree_probs[eval_idx]
    y_bf = bundle.truth_breakfree[train_idx]

    d4_train = bundle.dir4_probs[train_idx]
    d4_eval = bundle.dir4_probs[eval_idx]
    y_d4 = bundle.truth_4dir[train_idx]

    diag: dict[str, Any] = {"method": method}

    if method == "online_ewaf_logloss":
        p_bf = _predict_online_ewaf(
            train_probs=bf_train,
            train_y=y_bf,
            eval_probs=bf_eval,
            loss_mode="logloss",
            eta=float(args.ewaf_eta),
        )
        p_d4 = _predict_online_ewaf(
            train_probs=d4_train,
            train_y=y_d4,
            eval_probs=d4_eval,
            loss_mode="logloss",
            eta=float(args.ewaf_eta),
        )
        diag.update({"head_breakfree": {"temperature": 1.0}, "head_4dir": {"temperature": 1.0}})

    elif method == "online_ewaf_brier":
        p_bf = _predict_online_ewaf(
            train_probs=bf_train,
            train_y=y_bf,
            eval_probs=bf_eval,
            loss_mode="brier",
            eta=float(args.ewaf_eta),
        )
        p_d4 = _predict_online_ewaf(
            train_probs=d4_train,
            train_y=y_d4,
            eval_probs=d4_eval,
            loss_mode="brier",
            eta=float(args.ewaf_eta),
        )
        diag.update({"head_breakfree": {"temperature": 1.0}, "head_4dir": {"temperature": 1.0}})

    elif method == "online_sparse_ewaf_brier":
        p_bf = _predict_online_ewaf(
            train_probs=bf_train,
            train_y=y_bf,
            eval_probs=bf_eval,
            loss_mode="brier",
            eta=float(args.ewaf_eta),
            sparse_topk=int(args.ewaf_sparse_topk),
        )
        p_d4 = _predict_online_ewaf(
            train_probs=d4_train,
            train_y=y_d4,
            eval_probs=d4_eval,
            loss_mode="brier",
            eta=float(args.ewaf_eta),
            sparse_topk=int(args.ewaf_sparse_topk),
        )
        diag.update(
            {
                "head_breakfree": {"temperature": 1.0, "sparse_topk": int(args.ewaf_sparse_topk)},
                "head_4dir": {"temperature": 1.0, "sparse_topk": int(args.ewaf_sparse_topk)},
            }
        )

    elif method in {"regularized_stacker_logit", "regularized_stacker_gbm"}:
        x_bf_train = _build_head_features(bf_train)
        x_bf_eval = _build_head_features(bf_eval)
        p_bf, dbf = _fit_predict_stacker(
            method=method,
            train_x=x_bf_train,
            train_y=y_bf,
            eval_x=x_bf_eval,
            n_classes=HEAD_BF_CLASSES,
            val_tail_ratio=float(args.val_tail_ratio),
            seed=int(args.seed),
            apply_temperature=not bool(args.disable_temperature_scaling),
        )

        x_d4_train = _build_head_features(d4_train)
        x_d4_eval = _build_head_features(d4_eval)
        p_d4, dd4 = _fit_predict_stacker(
            method=method,
            train_x=x_d4_train,
            train_y=y_d4,
            eval_x=x_d4_eval,
            n_classes=HEAD_4DIR_CLASSES,
            val_tail_ratio=float(args.val_tail_ratio),
            seed=int(args.seed),
            apply_temperature=not bool(args.disable_temperature_scaling),
        )
        diag.update({"head_breakfree": dbf, "head_4dir": dd4})

    elif method == "causal_attention_gate_small":
        p_bf, dbf = _fit_predict_attention_gate(
            train_probs=bf_train,
            train_y=y_bf,
            eval_probs=bf_eval,
            n_classes=HEAD_BF_CLASSES,
            val_tail_ratio=float(args.val_tail_ratio),
            seed=int(args.seed),
            hidden_dim=int(args.attn_hidden_dim),
            max_epochs=int(args.attn_max_epochs),
            batch_size=int(args.attn_batch_size),
            apply_temperature=not bool(args.disable_temperature_scaling),
        )
        p_d4, dd4 = _fit_predict_attention_gate(
            train_probs=d4_train,
            train_y=y_d4,
            eval_probs=d4_eval,
            n_classes=HEAD_4DIR_CLASSES,
            val_tail_ratio=float(args.val_tail_ratio),
            seed=int(args.seed),
            hidden_dim=int(args.attn_hidden_dim),
            max_epochs=int(args.attn_max_epochs),
            batch_size=int(args.attn_batch_size),
            apply_temperature=not bool(args.disable_temperature_scaling),
        )
        diag.update({"head_breakfree": dbf, "head_4dir": dd4})
    else:
        raise ValueError(f"Unsupported method: {method}")

    pred_bf = np.argmax(p_bf, axis=1).astype(np.int64)
    pred_d4 = np.argmax(p_d4, axis=1).astype(np.int64)

    return pred_bf, pred_d4, p_bf, p_d4, diag


def _final_prediction_from_heads(pred_bf: np.ndarray, pred_d4: np.ndarray) -> np.ndarray:
    # pred_d4 uses labels: 0=DOWN,1=UP
    final = np.full_like(pred_bf, LABEL_HOLD)
    # breakfree HOLD always HOLD
    up_mask = pred_bf == LABEL_UP
    down_mask = pred_bf == LABEL_DOWN
    final[up_mask & (pred_d4 == 1)] = LABEL_UP
    final[down_mask & (pred_d4 == 0)] = LABEL_DOWN
    return final


def _confusion_matrix(y_true: np.ndarray, y_pred: np.ndarray, n_classes: int = 3) -> np.ndarray:
    cm = np.zeros((n_classes, n_classes), dtype=np.int64)
    for t, p in zip(y_true.astype(int), y_pred.astype(int)):
        cm[t, p] += 1
    return cm


def _prf_from_confusion(cm: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    n = cm.shape[0]
    precision = np.zeros(n, dtype=np.float64)
    recall = np.zeros(n, dtype=np.float64)
    f1 = np.zeros(n, dtype=np.float64)
    for i in range(n):
        tp = float(cm[i, i])
        fp = float(cm[:, i].sum() - tp)
        fn = float(cm[i, :].sum() - tp)
        precision[i] = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall[i] = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1[i] = (
            2.0 * precision[i] * recall[i] / (precision[i] + recall[i])
            if (precision[i] + recall[i]) > 0
            else 0.0
        )
    return precision, recall, f1


def _compute_custom_cost(y_true: np.ndarray, y_pred: np.ndarray) -> tuple[np.ndarray, float, float]:
    opposite = ((y_true == LABEL_UP) & (y_pred == LABEL_DOWN)) | (
        (y_true == LABEL_DOWN) & (y_pred == LABEL_UP)
    )
    hold_mismatch = ((y_true == LABEL_HOLD) & (y_pred != LABEL_HOLD)) | (
        (y_true != LABEL_HOLD) & (y_pred == LABEL_HOLD)
    )
    cost = opposite.astype(np.float64) * 2.0 + hold_mismatch.astype(np.float64) * 1.0
    mean_cost = float(np.mean(cost))
    utility = float(1.0 - mean_cost / 2.0)
    return cost, mean_cost, utility


def _hold_side_metrics(
    truth_breakfree: np.ndarray,
    truth_4dir: np.ndarray,
    pred_final: np.ndarray,
) -> dict[str, float | int]:
    hold_up = (truth_breakfree == LABEL_HOLD) & (truth_4dir == 1)
    hold_down = (truth_breakfree == LABEL_HOLD) & (truth_4dir == 0)
    bad = (hold_up & (pred_final == LABEL_DOWN)) | (hold_down & (pred_final == LABEL_UP))
    n = len(pred_final)
    return {
        "hold_side_cross_error_count": int(np.sum(bad)),
        "hold_side_cross_error_rate_covered": float(np.sum(bad) / max(1, n)),
    }


def _evaluate_metrics(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    truth_breakfree: np.ndarray,
    truth_4dir: np.ndarray,
) -> dict[str, Any]:
    cm = _confusion_matrix(y_true, y_pred, n_classes=3)
    precision, recall, f1 = _prf_from_confusion(cm)

    macro_f1 = float(np.mean(f1))
    balanced_acc = float(np.mean(recall))
    coverage = 1.0

    active = y_pred != LABEL_HOLD
    active_count = int(np.sum(active))
    n = len(y_pred)
    dir_active_coverage = float(active_count / max(1, n))

    # Strict active directional accuracy against final truth UP/DOWN only.
    dir_active_correct = ((y_pred == LABEL_UP) & (y_true == LABEL_UP)) | (
        (y_pred == LABEL_DOWN) & (y_true == LABEL_DOWN)
    )
    dir_active_acc = float(np.sum(dir_active_correct) / max(1, active_count))

    # Safe active directional accuracy where hold_up counts as UP-safe and hold_down as DOWN-safe.
    hold_up = (truth_breakfree == LABEL_HOLD) & (truth_4dir == 1)
    hold_down = (truth_breakfree == LABEL_HOLD) & (truth_4dir == 0)
    safe_correct = (
        ((y_pred == LABEL_UP) & ((y_true == LABEL_UP) | hold_up))
        | ((y_pred == LABEL_DOWN) & ((y_true == LABEL_DOWN) | hold_down))
    )
    dir_active_safe_acc = float(np.sum(safe_correct) / max(1, active_count))

    opposite = ((y_true == LABEL_UP) & (y_pred == LABEL_DOWN)) | (
        (y_true == LABEL_DOWN) & (y_pred == LABEL_UP)
    )
    opposite_count = int(np.sum(opposite))
    opposite_cov = float(opposite_count / max(1, n))
    opposite_active = float(opposite_count / max(1, active_count))

    cost_rows, mean_cost, utility = _compute_custom_cost(y_true, y_pred)
    hs = _hold_side_metrics(truth_breakfree, truth_4dir, y_pred)

    dir_recall_bal = float(np.mean([recall[LABEL_UP], recall[LABEL_DOWN]]))

    return {
        "confusion": cm,
        "precision_up": float(precision[LABEL_UP]),
        "precision_down": float(precision[LABEL_DOWN]),
        "precision_hold": float(precision[LABEL_HOLD]),
        "recall_up": float(recall[LABEL_UP]),
        "recall_down": float(recall[LABEL_DOWN]),
        "recall_hold": float(recall[LABEL_HOLD]),
        "f1_up": float(f1[LABEL_UP]),
        "f1_down": float(f1[LABEL_DOWN]),
        "f1_hold": float(f1[LABEL_HOLD]),
        "macro_f1": macro_f1,
        "balanced_accuracy": balanced_acc,
        "directional_balanced_recall": dir_recall_bal,
        "coverage": coverage,
        "directional_active_coverage": dir_active_coverage,
        "directional_active_accuracy": dir_active_acc,
        "directional_active_safe_accuracy": dir_active_safe_acc,
        "opposite_fp_rate_covered": opposite_cov,
        "opposite_fp_rate_active": opposite_active,
        "hold_side_cross_error_count": int(hs["hold_side_cross_error_count"]),
        "hold_side_cross_error_rate_covered": float(hs["hold_side_cross_error_rate_covered"]),
        "custom_mean_cost": mean_cost,
        "custom_utility": utility,
        "custom_cost_rows": cost_rows,
    }


def _method_rank_key(row: dict[str, Any]) -> tuple[float, float, float, float, float]:
    # risk-first sorting: lower opposite rates + hold-side error, then higher safe accuracy + coverage.
    return (
        float(row["opposite_fp_rate_covered"]),
        float(row["opposite_fp_rate_active"]),
        float(row["hold_side_cross_error_rate_covered"]),
        -float(row["directional_active_safe_accuracy"]),
        -float(row["directional_active_coverage"]),
    )


def _git_commit(project_root: Path) -> str:
    try:
        proc = subprocess.run(
            ["git", "-C", str(project_root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
        return proc.stdout.strip()
    except Exception:
        return ""


def _write_tracking_context(
    out_dir: Path,
    *,
    project_root: Path,
    run_command: str,
    linear_issue_url: str,
    notion_page_url: str,
    ensemble_run_dir: Path,
    candidate_search_run_dir: Path,
) -> Path:
    payload = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "project_root": str(project_root),
        "git_commit": _git_commit(project_root),
        "run_command": run_command,
        "linear_issue_url": linear_issue_url,
        "notion_page_url": notion_page_url,
        "ensemble_run_dir": str(ensemble_run_dir),
        "candidate_search_run_dir": str(candidate_search_run_dir),
    }
    p = out_dir / "tracking_context.json"
    p.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return p


def _serialize_confusion_rows(method_name: str, cm: np.ndarray) -> list[dict[str, Any]]:
    labels = ["UP", "DOWN", "HOLD"]
    rows: list[dict[str, Any]] = []
    for i, t in enumerate(labels):
        for j, p in enumerate(labels):
            rows.append(
                {
                    "method_name": method_name,
                    "truth": t,
                    "pred": p,
                    "count": int(cm[i, j]),
                }
            )
    return rows


def main() -> None:
    args = _parse_args()
    np.random.seed(int(args.seed))

    inputs = _resolve_inputs(args)
    leakage_report_path = inputs.out_dir / "leakage_guard_report.json"

    candidate12 = _load_candidate12_map(inputs.candidate_search_run_dir)

    print("Causal ensemble benchmark")
    print(f"  ensemble_run_dir: {inputs.ensemble_run_dir}")
    print(f"  candidate_search_run_dir: {inputs.candidate_search_run_dir}")
    print(f"  output_dir: {inputs.out_dir}")
    print(f"  methods: {args.methods}")

    bundle = _build_aligned_dataset(
        ensemble_run_dir=inputs.ensemble_run_dir,
        candidate12_map=candidate12,
        leakage_report_path=leakage_report_path,
        allow_missing_aligned=bool(args.allow_missing_aligned),
    )

    pred_batch_arr = bundle.pred_batch
    unique_batches = np.unique(pred_batch_arr)
    unique_batches.sort()
    n_batches = len(unique_batches)

    if int(args.wf_warmup_batches) >= n_batches:
        raise ValueError(
            f"wf_warmup_batches={args.wf_warmup_batches} must be < discovered batches={n_batches}"
        )

    # Storage
    pred_rows: list[dict[str, Any]] = []
    batch_rows: list[dict[str, Any]] = []
    method_rows: list[dict[str, Any]] = []
    confusion_rows: list[dict[str, Any]] = []
    calibration_rows: list[dict[str, Any]] = []

    leakage_rows: list[dict[str, Any]] = []

    eval_batch_windows: list[tuple[int, int]] = []
    start_positions = list(range(int(args.wf_warmup_batches), n_batches, int(args.wf_step_size)))

    for method in args.methods:
        if bool(args.verbose):
            print(f"\n[Method] {method}")
        method_pred_idx: list[int] = []
        method_pred_final: list[int] = []

        for i_pos, start_pos in enumerate(start_positions, start=1):
            eval_batches = unique_batches[start_pos : start_pos + int(args.wf_step_size)]
            if eval_batches.size == 0:
                continue
            eval_start_batch = int(eval_batches[0])
            eval_end_batch = int(eval_batches[-1])
            eval_batch_windows.append((eval_start_batch, eval_end_batch))

            gap = max(int(args.purge_batches), int(args.embargo_batches))
            cutoff = int(eval_start_batch - gap)
            train_mask = pred_batch_arr < cutoff if gap > 0 else pred_batch_arr < int(eval_start_batch)
            eval_mask = np.isin(pred_batch_arr, eval_batches)

            train_idx = np.where(train_mask)[0]
            eval_idx = np.where(eval_mask)[0]
            if train_idx.size == 0:
                continue

            max_train_batch = int(np.max(pred_batch_arr[train_idx]))
            min_eval_batch = int(np.min(pred_batch_arr[eval_idx]))
            violation = max_train_batch >= min_eval_batch
            leakage_rows.append(
                {
                    "method_name": method,
                    "eval_start_batch": int(eval_start_batch),
                    "eval_end_batch": int(eval_end_batch),
                    "max_train_batch": max_train_batch,
                    "min_eval_batch": min_eval_batch,
                    "gap_batches": int(gap),
                    "violation": bool(violation),
                }
            )
            if violation:
                raise RuntimeError(
                    f"Leakage violation for {method}: max_train_batch={max_train_batch} >= min_eval_batch={min_eval_batch}"
                )

            pred_bf, pred_d4, p_bf, p_d4, diag = _predict_heads_for_method(
                method=method,
                train_idx=train_idx,
                eval_idx=eval_idx,
                bundle=bundle,
                args=args,
            )
            pred_final = _final_prediction_from_heads(pred_bf, pred_d4)

            calibration_rows.append(
                {
                    "method_name": method,
                    "eval_start_batch": int(eval_start_batch),
                    "eval_end_batch": int(eval_end_batch),
                    "head": "breakfree",
                    "temperature": float(diag.get("head_breakfree", {}).get("temperature", 1.0)),
                    "val_nll_before": diag.get("head_breakfree", {}).get("val_nll_before"),
                    "val_nll_after": diag.get("head_breakfree", {}).get("val_nll_after"),
                    "fallback_majority": bool(diag.get("head_breakfree", {}).get("fallback_majority", False)),
                }
            )
            calibration_rows.append(
                {
                    "method_name": method,
                    "eval_start_batch": int(eval_start_batch),
                    "eval_end_batch": int(eval_end_batch),
                    "head": "dir4",
                    "temperature": float(diag.get("head_4dir", {}).get("temperature", 1.0)),
                    "val_nll_before": diag.get("head_4dir", {}).get("val_nll_before"),
                    "val_nll_after": diag.get("head_4dir", {}).get("val_nll_after"),
                    "fallback_majority": bool(diag.get("head_4dir", {}).get("fallback_majority", False)),
                }
            )

            # Per-row predictions
            eval_anchor = bundle.anchor_df[eval_idx]
            y_true_eval = bundle.truth_final[eval_idx]
            y_bf_eval = bundle.truth_breakfree[eval_idx]
            y_4_eval = bundle.truth_4dir[eval_idx]

            for j in range(len(eval_idx)):
                pred_rows.append(
                    {
                        "method_name": method,
                        "pred_batch": int(eval_anchor["pred_batch"][j]),
                        "anchor_15m_ts": eval_anchor["anchor_15m_ts"][j],
                        "truth_breakfree": int(y_bf_eval[j]),
                        "truth_4dir": int(y_4_eval[j]),
                        "truth_final": int(y_true_eval[j]),
                        "pred_breakfree": int(pred_bf[j]),
                        "pred_4dir": int(pred_d4[j]),
                        "pred_final": int(pred_final[j]),
                        "prob_bf_up": float(p_bf[j, LABEL_UP]),
                        "prob_bf_down": float(p_bf[j, LABEL_DOWN]),
                        "prob_bf_hold": float(p_bf[j, LABEL_HOLD]),
                        "prob_4dir_down": float(p_d4[j, 0]),
                        "prob_4dir_up": float(p_d4[j, 1]),
                    }
                )

            # Per-batch metrics
            eval_batches_unique = np.unique(pred_batch_arr[eval_idx])
            for b in eval_batches_unique:
                sub = eval_idx[pred_batch_arr[eval_idx] == b]
                met = _evaluate_metrics(
                    bundle.truth_final[sub],
                    pred_final[pred_batch_arr[eval_idx] == b],
                    bundle.truth_breakfree[sub],
                    bundle.truth_4dir[sub],
                )
                batch_rows.append(
                    {
                        "method_name": method,
                        "pred_batch": int(b),
                        "rows": int(len(sub)),
                        "macro_f1": float(met["macro_f1"]),
                        "balanced_accuracy": float(met["balanced_accuracy"]),
                        "directional_active_safe_accuracy": float(met["directional_active_safe_accuracy"]),
                        "directional_active_coverage": float(met["directional_active_coverage"]),
                        "opposite_fp_rate_covered": float(met["opposite_fp_rate_covered"]),
                        "opposite_fp_rate_active": float(met["opposite_fp_rate_active"]),
                        "hold_side_cross_error_rate_covered": float(met["hold_side_cross_error_rate_covered"]),
                        "custom_mean_cost": float(met["custom_mean_cost"]),
                        "custom_utility": float(met["custom_utility"]),
                    }
                )

            method_pred_idx.extend(eval_idx.tolist())
            method_pred_final.extend(pred_final.tolist())

            if bool(args.verbose):
                print(
                    f"  block {i_pos}/{len(start_positions)} eval_batches={int(eval_start_batch)}..{int(eval_end_batch)} train_rows={int(train_idx.size)} eval_rows={int(eval_idx.size)}"
                )

        if not method_pred_idx:
            continue

        method_pred_idx_np = np.array(method_pred_idx, dtype=np.int64)
        method_pred_final_np = np.array(method_pred_final, dtype=np.int64)
        y_true_all = bundle.truth_final[method_pred_idx_np]
        y_bf_all = bundle.truth_breakfree[method_pred_idx_np]
        y_4_all = bundle.truth_4dir[method_pred_idx_np]

        met = _evaluate_metrics(y_true_all, method_pred_final_np, y_bf_all, y_4_all)
        cm = met["confusion"]
        confusion_rows.extend(_serialize_confusion_rows(method, cm))

        method_rows.append(
            {
                "method_name": method,
                "alignment_mode": str(args.alignment_mode),
                "risk_objective": str(args.risk_objective),
                "rows_evaluated": int(len(method_pred_idx_np)),
                "macro_f1": float(met["macro_f1"]),
                "balanced_accuracy": float(met["balanced_accuracy"]),
                "directional_balanced_recall": float(met["directional_balanced_recall"]),
                "coverage": float(met["coverage"]),
                "directional_active_coverage": float(met["directional_active_coverage"]),
                "directional_active_accuracy": float(met["directional_active_accuracy"]),
                "directional_active_safe_accuracy": float(met["directional_active_safe_accuracy"]),
                "opposite_fp_rate_covered": float(met["opposite_fp_rate_covered"]),
                "opposite_fp_rate_active": float(met["opposite_fp_rate_active"]),
                "hold_side_cross_error_rate_covered": float(met["hold_side_cross_error_rate_covered"]),
                "custom_mean_cost": float(met["custom_mean_cost"]),
                "custom_utility": float(met["custom_utility"]),
                "precision_up": float(met["precision_up"]),
                "precision_down": float(met["precision_down"]),
                "precision_hold": float(met["precision_hold"]),
                "recall_up": float(met["recall_up"]),
                "recall_down": float(met["recall_down"]),
                "recall_hold": float(met["recall_hold"]),
                "f1_up": float(met["f1_up"]),
                "f1_down": float(met["f1_down"]),
                "f1_hold": float(met["f1_hold"]),
            }
        )

    if not method_rows:
        raise RuntimeError("No method produced evaluation rows")

    method_df = pl.DataFrame(method_rows)
    # deterministic risk-first sort
    method_df = method_df.sort(
        [
            "opposite_fp_rate_covered",
            "opposite_fp_rate_active",
            "hold_side_cross_error_rate_covered",
            "directional_active_safe_accuracy",
            "directional_active_coverage",
            "macro_f1",
            "method_name",
        ],
        descending=[False, False, False, True, True, True, False],
    ).with_row_index("rank", offset=1)

    pred_df = pl.DataFrame(pred_rows).sort(["method_name", "pred_batch", "anchor_15m_ts"])
    batch_df = pl.DataFrame(batch_rows).sort(["method_name", "pred_batch"])
    conf_df = pl.DataFrame(confusion_rows).sort(["method_name", "truth", "pred"])
    calib_df = pl.DataFrame(
        calibration_rows,
        schema={
            "method_name": pl.Utf8,
            "eval_start_batch": pl.Int64,
            "eval_end_batch": pl.Int64,
            "head": pl.Utf8,
            "temperature": pl.Float64,
            "val_nll_before": pl.Float64,
            "val_nll_after": pl.Float64,
            "fallback_majority": pl.Boolean,
        },
        strict=False,
    ).sort(["method_name", "eval_start_batch", "head"])
    leakage_df = pl.DataFrame(leakage_rows).sort(["method_name", "eval_start_batch"])

    # prediction distribution by 50-batch windows
    dist_rows: list[dict[str, Any]] = []
    all_batches_sorted = np.unique(pred_df["pred_batch"].to_numpy().astype(np.int64))
    window_size = 50
    for method in method_df["method_name"].to_list():
        sub = pred_df.filter(pl.col("method_name") == method).sort("pred_batch")
        bvals = np.unique(sub["pred_batch"].to_numpy().astype(np.int64))
        for i in range(0, len(bvals), window_size):
            w_batches = bvals[i : i + window_size]
            w = sub.filter(pl.col("pred_batch").is_in(w_batches))
            if w.is_empty():
                continue
            n = int(w.height)
            pred_final = w["pred_final"].to_numpy().astype(np.int64)
            truth = w["truth_final"].to_numpy().astype(np.int64)
            opposite = int(np.sum(((truth == LABEL_UP) & (pred_final == LABEL_DOWN)) | ((truth == LABEL_DOWN) & (pred_final == LABEL_UP))))
            dist_rows.append(
                {
                    "method_name": method,
                    "window_idx": int(i // window_size + 1),
                    "pred_batch_start": int(w_batches[0]),
                    "pred_batch_end": int(w_batches[-1]),
                    "rows": n,
                    "pred_up_count": int(np.sum(pred_final == LABEL_UP)),
                    "pred_down_count": int(np.sum(pred_final == LABEL_DOWN)),
                    "pred_hold_count": int(np.sum(pred_final == LABEL_HOLD)),
                    "pred_up_share": float(np.mean(pred_final == LABEL_UP)),
                    "pred_down_share": float(np.mean(pred_final == LABEL_DOWN)),
                    "pred_hold_share": float(np.mean(pred_final == LABEL_HOLD)),
                    "opposite_fp_rate_covered": float(opposite / max(1, n)),
                }
            )
    dist_df = pl.DataFrame(dist_rows).sort(["method_name", "window_idx"])

    # Write artifacts
    path_method = inputs.out_dir / "method_comparison_table.parquet"
    path_method_csv = inputs.out_dir / "method_comparison_table.csv"
    method_df.write_parquet(path_method)
    method_df.write_csv(path_method_csv)

    path_batch = inputs.out_dir / "evaluation_by_batch.parquet"
    path_batch_csv = inputs.out_dir / "evaluation_by_batch.csv"
    batch_df.write_parquet(path_batch)
    batch_df.write_csv(path_batch_csv)

    path_pred = inputs.out_dir / "final_predictions_walkforward.parquet"
    pred_df.write_parquet(path_pred)

    path_dist = inputs.out_dir / "prediction_distribution_by_window.parquet"
    path_dist_csv = inputs.out_dir / "prediction_distribution_by_window.csv"
    dist_df.write_parquet(path_dist)
    dist_df.write_csv(path_dist_csv)

    path_conf = inputs.out_dir / "final_confusion_standard.parquet"
    conf_df.write_parquet(path_conf)

    path_calib = inputs.out_dir / "calibration_report.json"
    calib_summary = {
        "rows": int(calib_df.height),
        "by_method_head": {},
    }
    if calib_df.height > 0:
        for row in (
            calib_df.group_by(["method_name", "head"])
            .agg(
                [
                    pl.mean("temperature").alias("temperature_mean"),
                    pl.mean("val_nll_before").alias("val_nll_before_mean"),
                    pl.mean("val_nll_after").alias("val_nll_after_mean"),
                    pl.col("fallback_majority").cast(pl.Float64).mean().alias("fallback_share"),
                ]
            )
            .to_dicts()
        ):
            key = f"{row['method_name']}::{row['head']}"
            calib_summary["by_method_head"][key] = {
                "temperature_mean": row["temperature_mean"],
                "val_nll_before_mean": row["val_nll_before_mean"],
                "val_nll_after_mean": row["val_nll_after_mean"],
                "fallback_share": row["fallback_share"],
            }
    path_calib.write_text(json.dumps(calib_summary, indent=2), encoding="utf-8")

    path_leak = inputs.out_dir / "leakage_guard_report.json"
    leak_report = json.loads(path_leak.read_text(encoding="utf-8")) if path_leak.exists() else {}
    leak_report.update(
        {
            "wf": {
                "methods": args.methods,
                "warmup_batches": int(args.wf_warmup_batches),
                "wf_step_size": int(args.wf_step_size),
                "purge_batches": int(args.purge_batches),
                "embargo_batches": int(args.embargo_batches),
                "leakage_violations": int(leakage_df.filter(pl.col("violation")).height),
            },
            "passed": bool(leakage_df.filter(pl.col("violation")).is_empty()) and bool(
                leak_report.get("passed", False)
            ),
        }
    )
    path_leak.write_text(json.dumps(leak_report, indent=2), encoding="utf-8")

    tracking_path = _write_tracking_context(
        inputs.out_dir,
        project_root=inputs.project_root,
        run_command=(str(args.run_command).strip() or " ".join(sys.argv)),
        linear_issue_url=str(args.linear_issue_url),
        notion_page_url=str(args.notion_page_url),
        ensemble_run_dir=inputs.ensemble_run_dir,
        candidate_search_run_dir=inputs.candidate_search_run_dir,
    )

    best = method_df.row(0, named=True)
    summary = {
        "run_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "config": {
            "project_root": str(inputs.project_root),
            "ensemble_run_dir": str(inputs.ensemble_run_dir),
            "candidate_search_run_dir": str(inputs.candidate_search_run_dir),
            "alignment_mode": str(args.alignment_mode),
            "wf_warmup_batches": int(args.wf_warmup_batches),
            "wf_step_size": int(args.wf_step_size),
            "purge_batches": int(args.purge_batches),
            "embargo_batches": int(args.embargo_batches),
            "methods": args.methods,
            "risk_objective": str(args.risk_objective),
            "seed": int(args.seed),
        },
        "counts": {
            "anchor_rows": int(bundle.anchor_df.height),
            "batches": int(n_batches),
            "breakfree_experts": int(len(bundle.breakfree_experts)),
            "dir4_experts": int(len(bundle.dir4_experts)),
            "methods_evaluated": int(method_df.height),
        },
        "best_method_risk_first": {
            "method_name": best["method_name"],
            "rank": int(best["rank"]),
            "macro_f1": float(best["macro_f1"]),
            "directional_active_safe_accuracy": float(best["directional_active_safe_accuracy"]),
            "directional_active_coverage": float(best["directional_active_coverage"]),
            "opposite_fp_rate_covered": float(best["opposite_fp_rate_covered"]),
            "opposite_fp_rate_active": float(best["opposite_fp_rate_active"]),
            "hold_side_cross_error_rate_covered": float(best["hold_side_cross_error_rate_covered"]),
            "custom_mean_cost": float(best["custom_mean_cost"]),
        },
        "artifacts": {
            "method_comparison_table_parquet": str(path_method),
            "method_comparison_table_csv": str(path_method_csv),
            "evaluation_by_batch_parquet": str(path_batch),
            "evaluation_by_batch_csv": str(path_batch_csv),
            "final_predictions_walkforward_parquet": str(path_pred),
            "prediction_distribution_by_window_parquet": str(path_dist),
            "prediction_distribution_by_window_csv": str(path_dist_csv),
            "final_confusion_standard_parquet": str(path_conf),
            "calibration_report_json": str(path_calib),
            "leakage_guard_report_json": str(path_leak),
            "tracking_context_json": str(tracking_path),
        },
    }
    path_summary = inputs.out_dir / "summary.json"
    path_summary.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print("\nCompleted benchmark.")
    print(f"  summary: {path_summary}")
    print(
        "  best:",
        best["method_name"],
        f"opp_cov={float(best['opposite_fp_rate_covered']):.4f}",
        f"hold_side={float(best['hold_side_cross_error_rate_covered']):.4f}",
        f"safe_acc={float(best['directional_active_safe_accuracy']):.4f}",
        f"coverage={float(best['directional_active_coverage']):.4f}",
    )


if __name__ == "__main__":
    main()
