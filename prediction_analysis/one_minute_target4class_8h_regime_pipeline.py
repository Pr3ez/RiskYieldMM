#!/usr/bin/env python3
"""Standalone 8h Bull/Bear/Chop regime pipeline for 1m/target_4class.

This script:
- Builds batch-level directional truth from 1m/target_4class stage1 payloads
- Aligns each batch to exactly one 8h feature row from analysis_8h.parquet
- Benchmarks multiple regime methods under strict no-lookahead walk-forward
- Selects a final operating point on holdout (last N batches)
- Exports required artifacts including regime_gate_by_batch.parquet
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
from typing import Any

import numpy as np
import polars as pl
from sklearn.decomposition import PCA
from sklearn.linear_model import LogisticRegression
from sklearn.mixture import GaussianMixture

try:
    from hmmlearn.hmm import GaussianHMM  # type: ignore
except Exception:
    GaussianHMM = None


DEFAULT_UNIT_DIR = "data/htf_backtest_results/stage1_catboost_live/catboost/1m/target_4class"
DEFAULT_ANALYSIS_8H = "data/analysis_8h.parquet"
DEFAULT_OUTPUT_DIR = "prediction_analysis/one_minute_target4class_8h_regime_outputs"

DIR_DOWN = 0
DIR_UP = 1
DIR_HOLD = 2

REG_BEAR = 0
REG_CHOP = 1
REG_BULL = 2
REG_NAME = {REG_BEAR: "bear", REG_CHOP: "chop", REG_BULL: "bull"}


@dataclass(frozen=True)
class Inputs:
    project_root: Path
    unit_dir: Path
    analysis_8h_path: Path
    output_dir: Path
    output_tag: str
    batches_tail: int
    holdout_batches: int
    trend_horizon_steps: int
    wf_gap_steps: int
    wf_retrain_every: int
    lookback_grid: tuple[int, ...]
    methods: tuple[str, ...]
    direction_threshold_grid: tuple[float, ...]
    min_safe_accuracy: float
    min_active_coverage: float
    min_regime_coverage: float
    seed: int
    linear_issue_url: str
    notion_page_url: str
    verbose: bool


@dataclass(frozen=True)
class PredictRecord:
    pred_batch: int
    train_max_batch: int
    source: str


class ModelUnavailable(Exception):
    pass


def _parse_lookback_grid(raw: str) -> tuple[int, ...]:
    vals: list[int] = []
    for token in str(raw).split(","):
        t = token.strip().lower()
        if not t:
            continue
        if t == "all":
            vals.append(-1)
        else:
            v = int(t)
            if v <= 1:
                raise ValueError(f"lookback must be >1 or 'all', got {v}")
            vals.append(v)
    if not vals:
        raise ValueError("lookback-grid is empty")
    return tuple(dict.fromkeys(vals).keys())


def _parse_float_grid(raw: str) -> tuple[float, ...]:
    vals: list[float] = []
    for token in str(raw).split(","):
        t = token.strip()
        if not t:
            continue
        v = float(t)
        if not (0.0 <= v <= 1.0):
            raise ValueError(f"grid values must be in [0,1], got {v}")
        vals.append(v)
    if not vals:
        raise ValueError("float grid is empty")
    return tuple(sorted(set(vals)))


def _parse_methods(raw: str) -> tuple[str, ...]:
    allowed = {
        "rule_threshold_v1",
        "gmm3_state_mapper",
        "hmm3_state_mapper",
        "supervised_3class_v1",
        "two_head_bull_bear_v1",
    }
    out: list[str] = []
    for token in str(raw).split(","):
        t = token.strip()
        if not t:
            continue
        if t not in allowed:
            raise ValueError(f"Unsupported method: {t}")
        out.append(t)
    if not out:
        raise ValueError("methods list is empty")
    return tuple(dict.fromkeys(out).keys())


def parse_args() -> Inputs:
    p = argparse.ArgumentParser(description="8h regime predictor pipeline for 1m/target_4class")
    p.add_argument("--project-root", type=str, default=".")
    p.add_argument("--unit-dir", type=str, default=DEFAULT_UNIT_DIR)
    p.add_argument("--analysis-8h-path", type=str, default=DEFAULT_ANALYSIS_8H)
    p.add_argument("--output-dir", type=str, default=DEFAULT_OUTPUT_DIR)
    p.add_argument("--output-tag", type=str, default="baseline")

    p.add_argument("--batches-tail", type=int, default=3600)
    p.add_argument("--holdout-batches", type=int, default=500)
    p.add_argument("--trend-horizon-steps", type=int, default=1)
    p.add_argument("--wf-gap-steps", type=int, default=0)
    p.add_argument("--wf-retrain-every", type=int, default=25)
    p.add_argument("--lookback-grid", type=str, default="512,1024,2048,all")
    p.add_argument(
        "--methods",
        type=str,
        default="rule_threshold_v1,gmm3_state_mapper,hmm3_state_mapper,supervised_3class_v1,two_head_bull_bear_v1",
    )
    p.add_argument("--direction-threshold-grid", type=str, default="0.50,0.55,0.60,0.65,0.70,0.75,0.80,0.85,0.90")

    p.add_argument("--min-safe-accuracy", type=float, default=0.70)
    p.add_argument("--min-active-coverage", type=float, default=0.04)
    p.add_argument("--min-regime-coverage", type=float, default=0.10)

    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--linear-issue-url", type=str, default="")
    p.add_argument("--notion-page-url", type=str, default="")
    p.add_argument("--verbose", action="store_true")
    a = p.parse_args()

    project_root = Path(a.project_root).expanduser().resolve()
    unit_dir = (project_root / a.unit_dir).resolve()
    analysis_path = (project_root / a.analysis_8h_path).resolve()
    output_dir = (project_root / a.output_dir).resolve()

    if int(a.batches_tail) <= 0:
        raise ValueError("--batches-tail must be > 0")
    if int(a.holdout_batches) <= 0:
        raise ValueError("--holdout-batches must be > 0")
    if int(a.trend_horizon_steps) <= 0:
        raise ValueError("--trend-horizon-steps must be > 0")
    if int(a.wf_gap_steps) < 0:
        raise ValueError("--wf-gap-steps must be >= 0")
    if int(a.wf_retrain_every) <= 0:
        raise ValueError("--wf-retrain-every must be > 0")

    return Inputs(
        project_root=project_root,
        unit_dir=unit_dir,
        analysis_8h_path=analysis_path,
        output_dir=output_dir,
        output_tag=str(a.output_tag).strip() or "baseline",
        batches_tail=int(a.batches_tail),
        holdout_batches=int(a.holdout_batches),
        trend_horizon_steps=int(a.trend_horizon_steps),
        wf_gap_steps=int(a.wf_gap_steps),
        wf_retrain_every=int(a.wf_retrain_every),
        lookback_grid=_parse_lookback_grid(a.lookback_grid),
        methods=_parse_methods(a.methods),
        direction_threshold_grid=_parse_float_grid(a.direction_threshold_grid),
        min_safe_accuracy=float(a.min_safe_accuracy),
        min_active_coverage=float(a.min_active_coverage),
        min_regime_coverage=float(a.min_regime_coverage),
        seed=int(a.seed),
        linear_issue_url=str(a.linear_issue_url),
        notion_page_url=str(a.notion_page_url),
        verbose=bool(a.verbose),
    )


def _git_commit_hash(project_root: Path) -> str:
    try:
        out = subprocess.check_output(["git", "-C", str(project_root), "rev-parse", "HEAD"], text=True)
        return out.strip()
    except Exception:
        return "unknown"


def _label3_from_uprate(up: float) -> int:
    if up >= 0.60:
        return REG_BULL
    if up <= 0.40:
        return REG_BEAR
    return REG_CHOP


def _dir_from_uprate(up: float) -> int:
    if up > 0.5:
        return DIR_UP
    if up < 0.5:
        return DIR_DOWN
    return DIR_HOLD


def _safe_float(x: Any, default: float = 0.0) -> float:
    if x is None:
        return default
    try:
        v = float(x)
    except Exception:
        return default
    if math.isnan(v) or math.isinf(v):
        return default
    return v


def _normalize3(a: float, b: float, c: float) -> tuple[float, float, float]:
    arr = np.array([max(0.0, a), max(0.0, b), max(0.0, c)], dtype=np.float64)
    s = float(arr.sum())
    if s <= 0.0:
        return (0.0, 0.0, 1.0)
    arr /= s
    return (float(arr[0]), float(arr[1]), float(arr[2]))


def _regime_argmax(pb: float, pch: float, pbu: float) -> int:
    vals = np.array([pb, pch, pbu], dtype=np.float64)
    return int(np.argmax(vals))


def _signal_from_probs(pb: float, pch: float, pbu: float, thr: float) -> int:
    # active only when bull or bear is dominant and above threshold
    if (pbu >= thr) and (pbu >= pb) and (pbu >= pch):
        return DIR_UP
    if (pb >= thr) and (pb >= pbu) and (pb >= pch):
        return DIR_DOWN
    return DIR_HOLD


def _build_dataset_contract(inp: Inputs) -> tuple[pl.DataFrame, dict[str, Any]]:
    payload_paths = sorted(inp.unit_dir.glob("batch_*/stage1/stage1_pred_batch_predictions.parquet"))
    if not payload_paths:
        raise FileNotFoundError(f"No stage1 payload files found under {inp.unit_dir}")

    required_cols = {
        "scope",
        "batch_id",
        "action_key",
        "timestamp",
        "y_true",
    }
    schema = pl.read_parquet(str(payload_paths[0]), n_rows=0).schema
    missing_cols = sorted(required_cols - set(schema.keys()))

    lf = (
        pl.scan_parquet([str(p) for p in payload_paths])
        .filter(pl.col("scope") == "pred_batch")
        .select(["batch_id", "action_key", "timestamp", "y_true"])
    )

    per_cfg = (
        lf.group_by(["batch_id", "action_key"])
        .agg(
            [
                pl.len().alias("rows"),
                pl.col("timestamp").min().alias("batch_start_ts"),
                pl.col("timestamp").max().alias("batch_end_ts"),
                pl.col("y_true").is_in([2, 3]).cast(pl.Float64).mean().alias("up_rate_cfg"),
            ]
        )
        .collect()
    )

    # Tail selection on sorted batch ids.
    all_batches = per_cfg["batch_id"].unique().sort().to_list()
    selected_batches = all_batches[-inp.batches_tail :]
    per_cfg = per_cfg.filter(pl.col("batch_id").is_in(selected_batches)).sort(["batch_id", "action_key"])

    by_batch = (
        per_cfg.group_by("batch_id")
        .agg(
            [
                pl.n_unique("action_key").alias("cfg_count"),
                pl.min("rows").alias("rows_min"),
                pl.max("rows").alias("rows_max"),
                pl.col("batch_start_ts").min().alias("batch_start_ts"),
                pl.col("batch_end_ts").max().alias("batch_end_ts"),
                pl.col("up_rate_cfg").mean().alias("batch_up_rate"),
            ]
        )
        .with_columns(
            [
                pl.col("batch_start_ts").dt.replace_time_zone("UTC").alias("batch_start_ts_utc"),
                pl.when(pl.col("batch_up_rate") > 0.5)
                .then(pl.lit(DIR_UP))
                .when(pl.col("batch_up_rate") < 0.5)
                .then(pl.lit(DIR_DOWN))
                .otherwise(pl.lit(DIR_HOLD))
                .alias("batch_dir_bin"),
            ]
        )
        .sort("batch_id")
    )

    bad_cfg_batches = by_batch.filter(pl.col("cfg_count") != 24)["batch_id"].to_list()
    bad_row_batches = by_batch.filter((pl.col("rows_min") != 240) | (pl.col("rows_max") != 240))["batch_id"].to_list()
    monotonic = by_batch["batch_id"].to_list() == sorted(by_batch["batch_id"].to_list())

    contract = {
        "pass": bool(len(missing_cols) == 0 and monotonic and len(bad_cfg_batches) == 0 and len(bad_row_batches) == 0),
        "missing_required_columns": missing_cols,
        "payload_files": int(len(payload_paths)),
        "batch_count": int(by_batch.height),
        "batch_id_first": int(by_batch["batch_id"].min()) if by_batch.height else None,
        "batch_id_last": int(by_batch["batch_id"].max()) if by_batch.height else None,
        "bad_cfg_count_batches": [int(x) for x in bad_cfg_batches],
        "bad_row_count_batches": [int(x) for x in bad_row_batches],
        "required_cfg_per_batch": 24,
        "required_rows_per_batch_config": 240,
        "batch_monotonic": bool(monotonic),
    }

    return by_batch, contract


def _build_feature_table(inp: Inputs) -> tuple[pl.DataFrame, list[str], list[dict[str, Any]]]:
    if not inp.analysis_8h_path.exists():
        raise FileNotFoundError(f"Missing analysis file: {inp.analysis_8h_path}")

    adf = pl.read_parquet(inp.analysis_8h_path)
    cols = adf.columns

    dropped: list[dict[str, Any]] = []
    candidates: list[str] = []
    for c in cols:
        if c == "timestamp":
            dropped.append({"feature": c, "reason": "leaky"})
            continue
        if c.startswith("y_") or c.startswith("RAW_") or c.startswith("rolling_"):
            dropped.append({"feature": c, "reason": "leaky"})
            continue
        candidates.append(c)

    feat = adf.select(["timestamp"] + candidates).sort("timestamp")
    return feat, candidates, dropped


def _align_batch_with_8h(
    batch_df: pl.DataFrame,
    feat_df: pl.DataFrame,
    trend_horizon_steps: int,
) -> tuple[pl.DataFrame, dict[str, Any]]:
    aligned = batch_df.join(
        feat_df,
        left_on="batch_start_ts_utc",
        right_on="timestamp",
        how="left",
    ).sort("batch_id")

    missing_join = aligned.filter(pl.all_horizontal([pl.col(c).is_null() for c in feat_df.columns if c != "timestamp"]))
    missing_batches = missing_join["batch_id"].to_list() if missing_join.height else []

    aligned = aligned.with_columns([pl.col("batch_up_rate").shift(-trend_horizon_steps).alias("future_up_rate")])

    future_regime: list[int | None] = []
    future_dir: list[int | None] = []
    for v in aligned["future_up_rate"].to_list():
        if v is None:
            future_regime.append(None)
            future_dir.append(None)
        else:
            vv = float(v)
            future_regime.append(int(_label3_from_uprate(vv)))
            future_dir.append(int(_dir_from_uprate(vv)))

    aligned = aligned.with_columns(
        [
            pl.Series("future_regime_3c_60_40", future_regime, dtype=pl.Int8),
            pl.Series("future_dir_bin", future_dir, dtype=pl.Int8),
        ]
    )

    report = {
        "rows": int(aligned.height),
        "missing_join_rows": int(missing_join.height),
        "missing_join_batches": [int(x) for x in missing_batches],
        "exact_timestamp_join": bool(missing_join.height == 0),
        "trend_horizon_steps": int(trend_horizon_steps),
    }
    return aligned, report


def _update_usage(
    usage: dict[str, dict[str, Any]],
    used_features: list[str],
    dropped_by_reason: dict[str, list[str]],
) -> None:
    for f in used_features:
        if f not in usage:
            usage[f] = {"used_count": 0, "dropped": {}}
        usage[f]["used_count"] += 1
    for reason, feats in dropped_by_reason.items():
        for f in feats:
            if f not in usage:
                usage[f] = {"used_count": 0, "dropped": {}}
            usage[f]["dropped"][reason] = int(usage[f]["dropped"].get(reason, 0)) + 1


def _fit_preprocessor(
    X_train_raw: np.ndarray,
    feature_names: list[str],
    usage: dict[str, dict[str, Any]],
    pca_max_components: int = 12,
) -> tuple[np.ndarray, dict[str, Any], list[str], dict[str, list[str]], dict[str, Any]]:
    n_features = X_train_raw.shape[1]
    dropped: dict[str, list[str]] = {"all_null": [], "constant": []}
    keep_idx: list[int] = []

    for j in range(n_features):
        col = X_train_raw[:, j]
        nonnan = col[~np.isnan(col)]
        if nonnan.size == 0:
            dropped["all_null"].append(feature_names[j])
            continue
        if float(np.nanstd(col)) <= 1e-12:
            dropped["constant"].append(feature_names[j])
            continue
        keep_idx.append(j)

    used_features = [feature_names[j] for j in keep_idx]
    _update_usage(usage, used_features, dropped)

    if not keep_idx:
        return (
            np.zeros((X_train_raw.shape[0], 1), dtype=np.float64),
            {
                "keep_idx": [],
                "median": np.array([0.0], dtype=np.float64),
                "mean": np.array([0.0], dtype=np.float64),
                "std": np.array([1.0], dtype=np.float64),
                "pca": None,
                "pca_n_components": 0,
            },
            [],
            dropped,
            {"pca_n_components": 0},
        )

    Xt = X_train_raw[:, keep_idx].astype(np.float64, copy=True)

    med = np.nanmedian(Xt, axis=0)
    med = np.where(np.isnan(med), 0.0, med)

    tr_nan = np.isnan(Xt)
    if tr_nan.any():
        Xt[tr_nan] = np.take(med, np.where(tr_nan)[1])

    mean = Xt.mean(axis=0)
    std = Xt.std(axis=0)
    std = np.where(std < 1e-9, 1.0, std)

    Xt = (Xt - mean) / std

    n_comp = int(min(pca_max_components, Xt.shape[1], max(1, Xt.shape[0] - 1)))
    pca = None
    if n_comp >= 2 and Xt.shape[1] >= 2:
        pca = PCA(n_components=n_comp, random_state=0)
        Xt = pca.fit_transform(Xt)
    else:
        n_comp = int(Xt.shape[1])

    prep = {
        "keep_idx": keep_idx,
        "median": med,
        "mean": mean,
        "std": std,
        "pca": pca,
        "pca_n_components": n_comp,
    }
    return Xt, prep, used_features, dropped, {"pca_n_components": n_comp}


def _transform_with_preprocessor(X_raw: np.ndarray, prep: dict[str, Any]) -> np.ndarray:
    keep_idx = list(prep.get("keep_idx", []))
    if not keep_idx:
        return np.zeros((X_raw.shape[0], 1), dtype=np.float64)

    X = X_raw[:, keep_idx].astype(np.float64, copy=True)
    med = prep["median"]
    tr_nan = np.isnan(X)
    if tr_nan.any():
        X[tr_nan] = np.take(med, np.where(tr_nan)[1])

    mean = prep["mean"]
    std = prep["std"]
    X = (X - mean) / std

    pca = prep.get("pca")
    if pca is not None:
        X = pca.transform(X)
    return X


def _fit_logit_multi(X: np.ndarray, y: np.ndarray, seed: int) -> tuple[Any, np.ndarray]:
    classes = np.array([REG_BEAR, REG_CHOP, REG_BULL], dtype=np.int32)
    uniq = np.unique(y)
    if uniq.size <= 1:
        prior = np.zeros(3, dtype=np.float64)
        prior[int(uniq[0]) if uniq.size == 1 else REG_CHOP] = 1.0
        return None, prior

    clf = LogisticRegression(
        solver="lbfgs",
        max_iter=500,
        class_weight="balanced",
        random_state=seed,
    )
    clf.fit(X, y)

    prior = np.zeros(3, dtype=np.float64)
    prior[:] = 1.0 / 3.0
    return clf, prior


def _predict_logit_multi(model: Any, prior: np.ndarray, X: np.ndarray) -> tuple[float, float, float]:
    if model is None:
        return float(prior[0]), float(prior[1]), float(prior[2])
    proba = model.predict_proba(X)[0]
    out = np.zeros(3, dtype=np.float64)
    for idx, cls in enumerate(model.classes_):
        out[int(cls)] = float(proba[idx])
    return _normalize3(out[REG_BEAR], out[REG_CHOP], out[REG_BULL])


def _fit_logit_bin(X: np.ndarray, y: np.ndarray, seed: int) -> tuple[Any, float]:
    uniq = np.unique(y)
    if uniq.size <= 1:
        return None, float(uniq[0] if uniq.size == 1 else 0.0)
    clf = LogisticRegression(
        solver="lbfgs",
        max_iter=500,
        class_weight="balanced",
        random_state=seed,
    )
    clf.fit(X, y)
    return clf, float(y.mean())


def _predict_logit_bin(model: Any, prior: float, X: np.ndarray) -> float:
    if model is None:
        return float(np.clip(prior, 0.0, 1.0))
    return float(model.predict_proba(X)[0, 1])


def _map_states_to_regimes(state_idx: np.ndarray, future_up_rate_train: np.ndarray) -> dict[int, int]:
    means: list[tuple[int, float]] = []
    for s in sorted(set(int(v) for v in state_idx.tolist())):
        mask = state_idx == s
        if not np.any(mask):
            means.append((s, 0.5))
        else:
            means.append((s, float(np.nanmean(future_up_rate_train[mask]))))

    means_sorted = sorted(means, key=lambda x: x[1])
    mapping: dict[int, int] = {}
    if len(means_sorted) == 1:
        mapping[means_sorted[0][0]] = REG_CHOP
        return mapping
    mapping[means_sorted[0][0]] = REG_BEAR
    mapping[means_sorted[-1][0]] = REG_BULL
    for s, _ in means_sorted[1:-1]:
        mapping[s] = REG_CHOP
    return mapping


def _rule_probs(row: dict[str, float]) -> tuple[float, float, float]:
    ema_dev = _safe_float(row.get("N_P_T_priceEmaDeviation_21_pct_N"), 0.0)
    sma_dev = _safe_float(row.get("N_P_T_priceSmaDeviation_21_pct_N"), 0.0)
    roc12 = _safe_float(row.get("M_P_roc_12_pct_N"), 0.0)
    di12 = _safe_float(row.get("M_T_V_diDiff_12_bnd_N"), 0.0) / 100.0
    adx12 = _safe_float(row.get("M_T_V_adx_12_bnd_N"), 20.0)
    vol21 = _safe_float(row.get("V_returnStd_21_pct_N"), 0.0)

    trend_score = (6.0 * ema_dev) + (3.0 * sma_dev) + (1.5 * di12) + (1.0 * roc12)
    strength = 1.0 / (1.0 + math.exp(-(adx12 - 20.0) / 6.0))
    vol_penalty = 1.0 / (1.0 + math.exp((vol21 - 0.03) / 0.01))

    bull_raw = (1.0 / (1.0 + math.exp(-trend_score))) * strength * (0.5 + 0.5 * vol_penalty)
    bear_raw = (1.0 / (1.0 + math.exp(trend_score))) * strength * (0.5 + 0.5 * vol_penalty)
    chop_raw = max(0.0, 1.0 - strength) + max(0.0, 0.5 - abs(trend_score))

    return _normalize3(bear_raw, chop_raw, bull_raw)


def _run_method_predictions(
    aligned: pl.DataFrame,
    feature_cols: list[str],
    method: str,
    lookback: int,
    inp: Inputs,
    usage: dict[str, dict[str, Any]],
    mapping_records: list[dict[str, Any]],
    leak_records: list[PredictRecord],
) -> pl.DataFrame:
    batch_ids = aligned["batch_id"].to_numpy().astype(np.int64, copy=False)
    X_all = aligned.select(feature_cols).to_numpy().astype(np.float64, copy=False)
    future_up = aligned["future_up_rate"].to_numpy().astype(np.float64, copy=False)
    future_regime = aligned["future_regime_3c_60_40"].to_numpy()
    effective_gap = max(int(inp.wf_gap_steps), int(inp.trend_horizon_steps))

    out_rows: list[dict[str, Any]] = []

    # Trained model cache (retrained periodically)
    last_refit_i = -1
    model_cache: dict[str, Any] = {}

    for i in range(len(batch_ids)):
        b = int(batch_ids[i])

        # Strict no-lookahead with explicit horizon gap.
        # For prediction made at index i, we only train on rows <= i - effective_gap - 1.
        train_end = i - effective_gap - 1

        if train_end < 0:
            pb, pch, pbu = (0.0, 1.0, 0.0)
            train_max_batch = b - effective_gap - 1
        else:
            train_start = 0 if lookback < 0 else max(0, train_end - lookback + 1)
            idx = np.arange(train_start, train_end + 1, dtype=np.int64)

            should_refit = (model_cache == {}) or ((i - last_refit_i) >= inp.wf_retrain_every)
            train_max_batch = int(batch_ids[train_end])

            if method == "rule_threshold_v1":
                # deterministic / no fitting
                row = {c: _safe_float(aligned[c][i], 0.0) for c in feature_cols}
                pb, pch, pbu = _rule_probs(row)
                leak_records.append(PredictRecord(pred_batch=b, train_max_batch=train_max_batch, source=f"{method}_predict"))
                out_rows.append(
                    {
                        "batch_id": b,
                        "method": method,
                        "lookback": lookback,
                        "p_bear": pb,
                        "p_chop": pch,
                        "p_bull": pbu,
                        "regime_pred": REG_NAME[_regime_argmax(pb, pch, pbu)],
                        "train_max_batch": train_max_batch,
                    }
                )
                continue

            if should_refit:
                X_train_raw = X_all[idx, :]
                Xt, prep, used, dropped, meta = _fit_preprocessor(X_train_raw, feature_cols, usage)

                model_cache = {
                    "prep": prep,
                    "used_features": used,
                    "drop_meta": dropped,
                    "prep_meta": meta,
                    "train_start_batch": int(batch_ids[train_start]),
                    "train_end_batch": int(batch_ids[train_end]),
                }

                if method == "gmm3_state_mapper":
                    if Xt.shape[0] < 30 or Xt.shape[1] < 1:
                        model_cache["fallback"] = (0.0, 1.0, 0.0)
                    else:
                        gmm = GaussianMixture(
                            n_components=3,
                            covariance_type="full",
                            random_state=inp.seed,
                            reg_covar=1e-5,
                            n_init=3,
                        )
                        gmm.fit(Xt)
                        st = gmm.predict(Xt)
                        mapping = _map_states_to_regimes(st, future_up[idx])
                        model_cache["gmm"] = gmm
                        model_cache["mapping"] = mapping
                        mapping_records.append(
                            {
                                "method": method,
                                "lookback": lookback,
                                "train_start_batch": int(batch_ids[train_start]),
                                "train_end_batch": int(batch_ids[train_end]),
                                "mapping": {str(k): REG_NAME[v] for k, v in mapping.items()},
                            }
                        )

                elif method == "hmm3_state_mapper":
                    if GaussianHMM is None:
                        raise ModelUnavailable("hmmlearn is not available; skipping hmm3_state_mapper")
                    if Xt.shape[0] < 50 or Xt.shape[1] < 1:
                        model_cache["fallback"] = (0.0, 1.0, 0.0)
                    else:
                        hmm = GaussianHMM(
                            n_components=3,
                            covariance_type="diag",
                            n_iter=100,
                            random_state=inp.seed,
                        )
                        hmm.fit(Xt)
                        st = hmm.predict(Xt)
                        mapping = _map_states_to_regimes(st, future_up[idx])
                        model_cache["hmm"] = hmm
                        model_cache["mapping"] = mapping
                        model_cache["Xt"] = Xt
                        mapping_records.append(
                            {
                                "method": method,
                                "lookback": lookback,
                                "train_start_batch": int(batch_ids[train_start]),
                                "train_end_batch": int(batch_ids[train_end]),
                                "mapping": {str(k): REG_NAME[v] for k, v in mapping.items()},
                            }
                        )

                elif method == "supervised_3class_v1":
                    y_train = future_regime[idx]
                    valid = np.array([v is not None for v in y_train], dtype=bool)
                    Xt2 = Xt[valid]
                    y2 = np.array([int(v) for v in y_train[valid]], dtype=np.int32)
                    if Xt2.shape[0] < 20:
                        model_cache["sup"] = None
                        model_cache["sup_prior"] = np.array([0.0, 1.0, 0.0], dtype=np.float64)
                    else:
                        m, prior = _fit_logit_multi(Xt2, y2, inp.seed)
                        model_cache["sup"] = m
                        model_cache["sup_prior"] = prior

                elif method == "two_head_bull_bear_v1":
                    y_next = future_up[idx]
                    valid = ~np.isnan(y_next)
                    Xt2 = Xt[valid]
                    yn = y_next[valid]
                    if Xt2.shape[0] < 20:
                        model_cache["bull"] = (None, 0.0)
                        model_cache["bear"] = (None, 0.0)
                    else:
                        y_bull = (yn >= 0.60).astype(np.int32)
                        y_bear = (yn <= 0.40).astype(np.int32)
                        bull_model = _fit_logit_bin(Xt2, y_bull, inp.seed)
                        bear_model = _fit_logit_bin(Xt2, y_bear, inp.seed)
                        model_cache["bull"] = bull_model
                        model_cache["bear"] = bear_model

                else:
                    raise ValueError(f"Unsupported method: {method}")

                last_refit_i = i

            # Predict using cached model state
            prep = model_cache.get("prep")
            if prep is None:
                X_train_raw = X_all[idx, :]
                _, prep, _, _, _ = _fit_preprocessor(X_train_raw, feature_cols, usage)
                model_cache["prep"] = prep
            Xp = _transform_with_preprocessor(X_all[i : i + 1, :], model_cache["prep"])

            if "fallback" in model_cache:
                pb, pch, pbu = model_cache["fallback"]
            elif method == "gmm3_state_mapper":
                gmm = model_cache["gmm"]
                mapping = model_cache["mapping"]
                p_state = gmm.predict_proba(Xp)[0]
                pb, pch, pbu = (0.0, 0.0, 0.0)
                for s, ps in enumerate(p_state):
                    reg = mapping.get(int(s), REG_CHOP)
                    if reg == REG_BEAR:
                        pb += float(ps)
                    elif reg == REG_BULL:
                        pbu += float(ps)
                    else:
                        pch += float(ps)
                pb, pch, pbu = _normalize3(pb, pch, pbu)
            elif method == "hmm3_state_mapper":
                hmm = model_cache["hmm"]
                mapping = model_cache["mapping"]
                Xt_hist = model_cache.get("Xt")
                if Xt_hist is not None and Xt_hist.shape[0] > 0:
                    seq = np.vstack([Xt_hist, Xp])
                    p_state = hmm.predict_proba(seq)[-1]
                else:
                    p_state = hmm.predict_proba(Xp)[0]
                pb, pch, pbu = (0.0, 0.0, 0.0)
                for s, ps in enumerate(p_state):
                    reg = mapping.get(int(s), REG_CHOP)
                    if reg == REG_BEAR:
                        pb += float(ps)
                    elif reg == REG_BULL:
                        pbu += float(ps)
                    else:
                        pch += float(ps)
                pb, pch, pbu = _normalize3(pb, pch, pbu)
            elif method == "supervised_3class_v1":
                pb, pch, pbu = _predict_logit_multi(model_cache.get("sup"), model_cache.get("sup_prior"), Xp)
            elif method == "two_head_bull_bear_v1":
                bull_m, bull_prior = model_cache.get("bull", (None, 0.0))
                bear_m, bear_prior = model_cache.get("bear", (None, 0.0))
                pbu = _predict_logit_bin(bull_m, bull_prior, Xp)
                pb = _predict_logit_bin(bear_m, bear_prior, Xp)
                pch = max(0.0, 1.0 - max(pbu, pb))
                pb, pch, pbu = _normalize3(pb, pch, pbu)
            else:
                pb, pch, pbu = (0.0, 1.0, 0.0)

        leak_records.append(PredictRecord(pred_batch=b, train_max_batch=train_max_batch, source=f"{method}_predict"))
        out_rows.append(
            {
                "batch_id": b,
                "method": method,
                "lookback": lookback,
                "p_bear": float(pb),
                "p_chop": float(pch),
                "p_bull": float(pbu),
                "regime_pred": REG_NAME[_regime_argmax(pb, pch, pbu)],
                "train_max_batch": int(train_max_batch),
            }
        )

    return pl.DataFrame(out_rows).sort("batch_id")


def _evaluate_threshold(
    pred_df: pl.DataFrame,
    aligned: pl.DataFrame,
    holdout_batches: set[int],
    threshold: float,
    min_regime_cov: float,
    truth_col: str,
) -> dict[str, Any]:
    truth = aligned.select(["batch_id", truth_col]).with_columns(pl.col("batch_id").cast(pl.Int64))
    df = (
        pred_df.join(truth, on="batch_id", how="left")
        .filter(pl.col("batch_id").is_in(list(holdout_batches)))
        .sort("batch_id")
    )

    y_true = df[truth_col].to_numpy().astype(np.float64, copy=False)
    p_bear = df["p_bear"].to_numpy().astype(np.float64, copy=False)
    p_chop = df["p_chop"].to_numpy().astype(np.float64, copy=False)
    p_bull = df["p_bull"].to_numpy().astype(np.float64, copy=False)

    reg_pred = np.array([_regime_argmax(pb, pc, pu) for pb, pc, pu in zip(p_bear, p_chop, p_bull)], dtype=np.int32)
    signal = np.array([_signal_from_probs(pb, pc, pu, threshold) for pb, pc, pu in zip(p_bear, p_chop, p_bull)], dtype=np.int32)

    valid = np.isin(y_true, np.array([DIR_DOWN, DIR_UP], dtype=np.float64))
    y_true_i = y_true.astype(np.int32, copy=False)
    n_total = int(valid.sum())
    act = valid & np.isin(signal, np.array([DIR_DOWN, DIR_UP], dtype=np.int32))
    n_act = int(act.sum())

    opp = int(np.sum(act & (signal != y_true_i)))
    corr = int(np.sum(act & (signal == y_true_i)))

    safe_acc = float(corr / n_act) if n_act > 0 else 0.0
    coverage = float(n_act / n_total) if n_total > 0 else 0.0
    opp_active = float(opp / n_act) if n_act > 0 else 0.0
    opp_cov = float(opp / n_total) if n_total > 0 else 0.0
    cadence = (float(n_total) / float(n_act)) if n_act > 0 else None

    # Regime consistency on holdout
    def share(mask: np.ndarray, cond: np.ndarray) -> float | None:
        n = int(np.sum(mask))
        if n == 0:
            return None
        return float(np.sum(mask & cond) / n)

    rb = valid & (reg_pred == REG_BULL)
    rr = valid & (reg_pred == REG_BEAR)
    rc = valid & (reg_pred == REG_CHOP)

    cov_bull = float(np.sum(rb) / n_total) if n_total > 0 else 0.0
    cov_bear = float(np.sum(rr) / n_total) if n_total > 0 else 0.0
    cov_chop = float(np.sum(rc) / n_total) if n_total > 0 else 0.0

    p_up_given_bull = share(rb, y_true_i == DIR_UP)
    p_down_given_bear = share(rr, y_true_i == DIR_DOWN)
    chop_up = share(rc, y_true_i == DIR_UP)
    chop_down = share(rc, y_true_i == DIR_DOWN)
    chop_balance = None if (chop_up is None or chop_down is None) else float(abs(chop_up - chop_down))

    unstable_regimes = []
    if cov_bull < min_regime_cov:
        unstable_regimes.append("bull")
    if cov_bear < min_regime_cov:
        unstable_regimes.append("bear")
    if cov_chop < min_regime_cov:
        unstable_regimes.append("chop")

    feasible = (
        (p_up_given_bull is not None and p_up_given_bull >= 0.55)
        and (p_down_given_bear is not None and p_down_given_bear >= 0.55)
        and (len(unstable_regimes) == 0)
    )

    return {
        "holdout_batches": int(n_total),
        "active_batches": int(n_act),
        "coverage": float(coverage),
        "directional_active_safe_accuracy": float(safe_acc),
        "opposite_fp_count": int(opp),
        "opposite_fp_rate_active": float(opp_active),
        "opposite_fp_rate_covered": float(opp_cov),
        "batches_per_signal": cadence,
        "p_up_given_bull": p_up_given_bull,
        "p_down_given_bear": p_down_given_bear,
        "chop_up_share": chop_up,
        "chop_down_share": chop_down,
        "chop_neutrality_balance": chop_balance,
        "regime_coverage_bull": cov_bull,
        "regime_coverage_bear": cov_bear,
        "regime_coverage_chop": cov_chop,
        "unstable_regimes": unstable_regimes,
        "feasible": bool(feasible),
    }


def _build_leakage_report(records: list[PredictRecord], min_gap_steps: int) -> dict[str, Any]:
    bad = [r for r in records if int(r.train_max_batch) >= int(r.pred_batch - min_gap_steps)]
    return {
        "checks": int(len(records)),
        "violations": int(len(bad)),
        "pass": bool(len(bad) == 0),
        "min_gap_steps": int(min_gap_steps),
        "first_violations": [
            {
                "pred_batch": int(r.pred_batch),
                "train_max_batch": int(r.train_max_batch),
                "source": r.source,
            }
            for r in bad[:20]
        ],
    }


def main() -> None:
    inp = parse_args()

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    run_dir = inp.output_dir / f"{ts}_{inp.output_tag}"
    run_dir.mkdir(parents=True, exist_ok=True)

    # 1) Dataset contract from 1m payloads.
    batch_df, contract = _build_dataset_contract(inp)
    (run_dir / "dataset_contract.json").write_text(json.dumps(contract, indent=2), encoding="utf-8")
    if not contract["pass"]:
        summary = {"status": "failed_dataset_contract", "dataset_contract": contract}
        (run_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        raise RuntimeError("Dataset contract failed. See dataset_contract.json")

    # 2) 8h features and alignment.
    feat_df, candidate_features, pre_dropped = _build_feature_table(inp)
    aligned, join_report = _align_batch_with_8h(
        batch_df=batch_df,
        feat_df=feat_df,
        trend_horizon_steps=inp.trend_horizon_steps,
    )
    if not join_report["exact_timestamp_join"]:
        summary = {
            "status": "failed_alignment",
            "dataset_contract": contract,
            "join_report": join_report,
        }
        (run_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        raise RuntimeError("Exact batch->8h timestamp join failed.")

    aligned.write_parquet(run_dir / "aligned_batch_dataset.parquet")

    # Holdout split on rows with known future directional labels.
    all_batches = aligned["batch_id"].to_list()
    eligible_holdout_batches = (
        aligned.filter(pl.col("future_dir_bin").is_in([DIR_DOWN, DIR_UP]))
        .select("batch_id")
        .to_series()
        .to_list()
    )
    if len(eligible_holdout_batches) < 50:
        raise RuntimeError(
            "Not enough eligible rows with known future labels for holdout. "
            f"Eligible rows={len(eligible_holdout_batches)}."
        )
    hold_n = min(inp.holdout_batches, max(1, len(eligible_holdout_batches) - 200))
    holdout_batches = set(int(x) for x in eligible_holdout_batches[-hold_n:])

    # 3) Benchmark methods.
    usage: dict[str, dict[str, Any]] = {}
    mapping_records: list[dict[str, Any]] = []
    leak_records: list[PredictRecord] = []
    method_pred: dict[tuple[str, int], pl.DataFrame] = {}
    grid_rows: list[dict[str, Any]] = []

    for method in inp.methods:
        lookbacks = inp.lookback_grid if method != "rule_threshold_v1" else (-1,)
        for lb in lookbacks:
            if inp.verbose:
                lb_label = "all" if lb < 0 else str(lb)
                print(f"[run] method={method} lookback={lb_label}")
            try:
                pred = _run_method_predictions(
                    aligned=aligned,
                    feature_cols=candidate_features,
                    method=method,
                    lookback=lb,
                    inp=inp,
                    usage=usage,
                    mapping_records=mapping_records,
                    leak_records=leak_records,
                )
            except ModelUnavailable as e:
                if inp.verbose:
                    print(f"[skip] {method}: {e}")
                continue

            method_pred[(method, lb)] = pred

            for thr in inp.direction_threshold_grid:
                m = _evaluate_threshold(
                    pred_df=pred,
                    aligned=aligned,
                    holdout_batches=holdout_batches,
                    threshold=float(thr),
                    min_regime_cov=inp.min_regime_coverage,
                    truth_col="future_dir_bin",
                )
                unstable = list(m.get("unstable_regimes", []))
                grid_rows.append(
                    {
                        "method": method,
                        "lookback": lb,
                        "lookback_label": "all" if lb < 0 else str(lb),
                        "threshold": float(thr),
                        **{k: v for k, v in m.items() if k != "unstable_regimes"},
                        "unstable_regimes": "|".join(str(x) for x in unstable),
                        "unstable_regime_count": int(len(unstable)),
                    }
                )

    if not grid_rows:
        raise RuntimeError("No method produced predictions; cannot continue")

    grid_df = pl.DataFrame(grid_rows)
    grid_df.write_csv(run_dir / "method_grid_results.csv")

    # 4) Select final operating point.
    rows = grid_df.to_dicts()
    feasible = [r for r in rows if bool(r.get("feasible", False))]

    def sort_key(r: dict[str, Any]) -> tuple[float, float, float]:
        return (
            float(r.get("directional_active_safe_accuracy", 0.0)),
            float(r.get("coverage", 0.0)),
            -float(r.get("opposite_fp_rate_active", 1.0)),
        )

    if feasible:
        selected = sorted(feasible, key=sort_key, reverse=True)[0]
    else:
        selected = sorted(rows, key=sort_key, reverse=True)[0]

    best_safe = sorted(rows, key=lambda r: float(r.get("directional_active_safe_accuracy", 0.0)), reverse=True)[0]
    best_cov = sorted(rows, key=lambda r: float(r.get("coverage", 0.0)), reverse=True)[0]

    selected_safe = float(selected.get("directional_active_safe_accuracy", 0.0))
    selected_cov = float(selected.get("coverage", 0.0))
    selected_feasible = bool(selected.get("feasible", False))
    status = (
        "production_ready"
        if (selected_feasible and selected_safe >= inp.min_safe_accuracy and selected_cov >= inp.min_active_coverage)
        else "not_production_ready"
    )

    # 5) Emit chosen predictions + gate.
    sel_key = (str(selected["method"]), int(selected["lookback"]))
    chosen_pred = method_pred[sel_key]
    thr = float(selected["threshold"])

    truth = aligned.select(["batch_id", "future_dir_bin", "batch_start_ts_utc"]).with_columns(pl.col("batch_id").cast(pl.Int64))
    final_df = chosen_pred.join(truth, on="batch_id", how="left").sort("batch_id")

    sig = [
        _signal_from_probs(pb, pc, pu, thr)
        for pb, pc, pu in zip(
            final_df["p_bear"].to_numpy(),
            final_df["p_chop"].to_numpy(),
            final_df["p_bull"].to_numpy(),
        )
    ]
    final_df = final_df.with_columns(pl.Series("signal_dir", sig, dtype=pl.Int8))
    final_df = final_df.with_columns(
        [
            pl.when(pl.col("batch_id").is_in(list(holdout_batches))).then(pl.lit("holdout")).otherwise(pl.lit("train_oos")).alias("split"),
            pl.max_horizontal([pl.col("p_bear"), pl.col("p_chop"), pl.col("p_bull")]).alias("signal_confidence"),
            pl.col("batch_id").is_in(list(holdout_batches)).alias("is_holdout"),
            pl.col("signal_dir").is_in([DIR_DOWN, DIR_UP]).alias("is_active"),
        ]
    )

    final_df.write_parquet(run_dir / "regime_predictions_by_batch.parquet")

    gate_cols = [
        "batch_id",
        "batch_start_ts_utc",
        "split",
        "method",
        "lookback",
        "p_bear",
        "p_chop",
        "p_bull",
        "regime_pred",
        "signal_dir",
        "signal_confidence",
        "is_active",
    ]
    final_df.select(gate_cols).write_parquet(run_dir / "regime_gate_by_batch.parquet")

    # Mapping records and feature manifest.
    mapping_df = pl.DataFrame(mapping_records) if mapping_records else pl.DataFrame(
        {"method": [], "lookback": [], "train_start_batch": [], "train_end_batch": [], "mapping": []}
    )
    if mapping_df.height > 0:
        mapping_df = mapping_df.with_columns(
            pl.col("mapping").map_elements(lambda v: json.dumps(v, sort_keys=True), return_dtype=pl.Utf8).alias("mapping")
        )
    mapping_df.write_csv(run_dir / "regime_mapping_by_window.csv")

    used_features = sorted([f for f, v in usage.items() if int(v.get("used_count", 0)) > 0])
    drop_rows: list[dict[str, Any]] = []
    for f, rec in usage.items():
        for reason, cnt in rec.get("dropped", {}).items():
            drop_rows.append({"feature": f, "reason": reason, "count": int(cnt)})

    feature_manifest = {
        "all_candidate_features": candidate_features,
        "used_features": used_features,
        "dropped_features": pre_dropped + drop_rows,
        "feature_count_all": int(len(candidate_features)),
        "feature_count_used": int(len(used_features)),
    }
    (run_dir / "feature_manifest.json").write_text(json.dumps(feature_manifest, indent=2), encoding="utf-8")

    # Leakage report
    effective_gap = max(int(inp.wf_gap_steps), int(inp.trend_horizon_steps))
    leak_report = {
        "global": _build_leakage_report(leak_records, min_gap_steps=effective_gap),
        "checks": {
            "holdout_batches": int(hold_n),
            "total_batches": int(len(all_batches)),
            "eligible_holdout_batches": int(len(eligible_holdout_batches)),
            "effective_gap_steps": int(effective_gap),
        },
    }
    (run_dir / "leakage_guard_report.json").write_text(json.dumps(leak_report, indent=2), encoding="utf-8")

    # Holdout metrics + operating point.
    hold_metrics = {k: v for k, v in selected.items() if k not in {"method", "lookback", "lookback_label", "threshold"}}
    hold_metrics.update(
        {
            "method": selected["method"],
            "lookback": int(selected["lookback"]),
            "threshold": float(selected["threshold"]),
            "trend_horizon_steps": int(inp.trend_horizon_steps),
            "effective_gap_steps": int(effective_gap),
            "truth_label_col": "future_dir_bin",
            "status": status,
        }
    )
    (run_dir / "holdout_metrics.json").write_text(json.dumps(hold_metrics, indent=2), encoding="utf-8")

    final_op = {
        "selected": {
            "method": selected["method"],
            "lookback": int(selected["lookback"]),
            "threshold": float(selected["threshold"]),
            "feasible": bool(selected.get("feasible", False)),
        },
        "best_safe": {
            "method": best_safe["method"],
            "lookback": int(best_safe["lookback"]),
            "threshold": float(best_safe["threshold"]),
            "directional_active_safe_accuracy": float(best_safe.get("directional_active_safe_accuracy", 0.0)),
            "coverage": float(best_safe.get("coverage", 0.0)),
        },
        "best_coverage": {
            "method": best_cov["method"],
            "lookback": int(best_cov["lookback"]),
            "threshold": float(best_cov["threshold"]),
            "directional_active_safe_accuracy": float(best_cov.get("directional_active_safe_accuracy", 0.0)),
            "coverage": float(best_cov.get("coverage", 0.0)),
        },
        "status": status,
        "failure_reasons": []
        if status == "production_ready"
        else [
            f"selected_feasible={selected_feasible}",
            f"selected_safe_accuracy={selected_safe:.4f} (min={inp.min_safe_accuracy:.4f})",
            f"selected_coverage={selected_cov:.4f} (min={inp.min_active_coverage:.4f})",
        ],
    }
    (run_dir / "final_operating_point.json").write_text(json.dumps(final_op, indent=2), encoding="utf-8")

    # Tracking context
    tracking = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "run_command": " ".join(["python", *sys.argv]),
        "git_commit": _git_commit_hash(inp.project_root),
        "linear_issue_url": inp.linear_issue_url,
        "notion_page_url": inp.notion_page_url,
    }
    (run_dir / "tracking_context.json").write_text(json.dumps(tracking, indent=2), encoding="utf-8")

    summary = {
        "status": status,
        "inputs": {
            "project_root": str(inp.project_root),
            "unit_dir": str(inp.unit_dir),
            "analysis_8h_path": str(inp.analysis_8h_path),
            "batches_tail": inp.batches_tail,
            "holdout_batches": inp.holdout_batches,
            "trend_horizon_steps": inp.trend_horizon_steps,
            "wf_gap_steps": inp.wf_gap_steps,
            "effective_gap_steps": int(effective_gap),
            "wf_retrain_every": inp.wf_retrain_every,
            "lookback_grid": list(inp.lookback_grid),
            "methods": list(inp.methods),
            "direction_threshold_grid": list(inp.direction_threshold_grid),
            "min_safe_accuracy": inp.min_safe_accuracy,
            "min_active_coverage": inp.min_active_coverage,
            "min_regime_coverage": inp.min_regime_coverage,
            "seed": inp.seed,
        },
        "dataset_contract": contract,
        "join_report": join_report,
        "holdout_metrics": hold_metrics,
        "final_operating_point": final_op,
        "artifact_paths": {
            "dataset_contract_json": str((run_dir / "dataset_contract.json").resolve()),
            "feature_manifest_json": str((run_dir / "feature_manifest.json").resolve()),
            "aligned_batch_dataset_parquet": str((run_dir / "aligned_batch_dataset.parquet").resolve()),
            "method_grid_results_csv": str((run_dir / "method_grid_results.csv").resolve()),
            "regime_predictions_by_batch_parquet": str((run_dir / "regime_predictions_by_batch.parquet").resolve()),
            "regime_mapping_by_window_csv": str((run_dir / "regime_mapping_by_window.csv").resolve()),
            "regime_gate_by_batch_parquet": str((run_dir / "regime_gate_by_batch.parquet").resolve()),
            "holdout_metrics_json": str((run_dir / "holdout_metrics.json").resolve()),
            "final_operating_point_json": str((run_dir / "final_operating_point.json").resolve()),
            "leakage_guard_report_json": str((run_dir / "leakage_guard_report.json").resolve()),
            "tracking_context_json": str((run_dir / "tracking_context.json").resolve()),
        },
    }
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"Done. Output: {run_dir}")
    print(json.dumps({"status": status, "holdout_metrics": hold_metrics}, indent=2))


if __name__ == "__main__":
    main()
