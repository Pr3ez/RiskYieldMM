#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import polars as pl
from sklearn.linear_model import LogisticRegression

LABEL_UP = 0
LABEL_DOWN = 1
LABEL_HOLD = 2


@dataclass
class StepMetrics:
    opposite_fp_rate_active: float
    opposite_fp_rate_covered: float
    directional_active_safe_accuracy: float
    batches_per_signal: float
    active_batch_rate: float
    cadence_target_hit: bool


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Posthoc risk-first steps: meta-gate + strict/dual router.")
    p.add_argument("--strict-run-dir", required=True)
    p.add_argument("--dual-run-dir", required=True)
    p.add_argument("--output-dir", default="prediction_analysis/multitimeframe_cross_target_outputs")
    p.add_argument("--output-tag", default="")
    p.add_argument("--meta-lookback-batches", type=int, default=240)
    p.add_argument("--router-lookback-batches", type=int, default=240)
    p.add_argument("--meta-retrain-every-batches", type=int, default=8)
    p.add_argument("--router-retrain-every-batches", type=int, default=8)
    p.add_argument("--val-tail-ratio", type=float, default=0.2)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--verbose", action="store_true")
    return p.parse_args()


def _load_run(run_dir: Path) -> pl.DataFrame:
    p = run_dir / "final_ensemble_predictions_walkforward.parquet"
    if not p.exists():
        raise FileNotFoundError(f"Missing {p}")
    df = pl.read_parquet(p)
    needed = {
        "pred_batch",
        "anchor_15m_ts",
        "truth_final",
        "truth_final4",
        "pred_final",
        "score_final",
        "tau",
        "tau_up",
        "tau_down",
        "selected_break_count",
        "selected_4dir_count",
    }
    miss = sorted(needed - set(df.columns))
    if miss:
        raise ValueError(f"Missing columns in {p}: {miss}")
    return df.sort(["pred_batch", "anchor_15m_ts"])


def _metrics(df: pl.DataFrame, pred_col: str) -> StepMetrics:
    y = df["truth_final"].to_numpy().astype(int)
    y4 = df["truth_final4"].to_numpy().astype(int)
    p = df[pred_col].to_numpy().astype(int)

    n = len(y)
    active = p != LABEL_HOLD
    active_n = int(active.sum())

    opposite = ((y == LABEL_UP) & (p == LABEL_DOWN)) | ((y == LABEL_DOWN) & (p == LABEL_UP))
    opposite_count = int(opposite.sum())

    if active_n > 0:
        opposite_active = int(opposite[active].sum()) / active_n
    else:
        opposite_active = 0.0

    safe_up = np.isin(y4, np.array([0, 2]))
    safe_down = np.isin(y4, np.array([1, 3]))
    active_safe_correct = ((p == LABEL_UP) & safe_up) | ((p == LABEL_DOWN) & safe_down)
    safe_acc = float(active_safe_correct[active].mean()) if active_n > 0 else 0.0

    batch_df = (
        df.select("pred_batch", pred_col)
        .with_columns((pl.col(pred_col) != LABEL_HOLD).alias("is_active"))
        .group_by("pred_batch")
        .agg(pl.any("is_active").alias("batch_active"))
        .sort("pred_batch")
    )
    batch_count = int(batch_df.height)
    active_batches = int(batch_df["batch_active"].sum())
    batches_per_signal = float(batch_count / active_batches) if active_batches > 0 else float("inf")
    active_batch_rate = float(active_batches / max(1, batch_count))

    return StepMetrics(
        opposite_fp_rate_active=float(opposite_active),
        opposite_fp_rate_covered=float(opposite_count / max(1, n)),
        directional_active_safe_accuracy=float(safe_acc),
        batches_per_signal=float(batches_per_signal),
        active_batch_rate=float(active_batch_rate),
        cadence_target_hit=bool(10.0 <= batches_per_signal <= 15.0),
    )


def _meta_features(df: pl.DataFrame) -> np.ndarray:
    pred = df["pred_final"].to_numpy().astype(int)
    score = df["score_final"].to_numpy().astype(float)
    tau = df["tau"].to_numpy().astype(float)
    tau_up = df["tau_up"].to_numpy().astype(float)
    tau_down = df["tau_down"].to_numpy().astype(float)
    sb = df["selected_break_count"].to_numpy().astype(float)
    sd = df["selected_4dir_count"].to_numpy().astype(float)

    pred_up = (pred == LABEL_UP).astype(float)
    pred_down = (pred == LABEL_DOWN).astype(float)
    pred_hold = (pred == LABEL_HOLD).astype(float)

    x = np.column_stack([
        score,
        np.abs(score),
        tau,
        tau_up,
        tau_down,
        sb,
        sd,
        pred_up,
        pred_down,
        pred_hold,
    ])
    x = np.nan_to_num(x, nan=0.0, posinf=0.0, neginf=0.0)
    return x.astype(np.float64)


def _gate_predictions(base_pred: np.ndarray, prob: np.ndarray, threshold: float) -> np.ndarray:
    out = np.full_like(base_pred, LABEL_HOLD)
    active = (base_pred != LABEL_HOLD) & (prob >= float(threshold))
    out[active] = base_pred[active]
    return out


def _meta_step(
    df: pl.DataFrame,
    lookback_batches: int,
    retrain_every_batches: int,
    val_tail_ratio: float,
    seed: int,
    verbose: bool,
) -> pl.DataFrame:
    batches = df["pred_batch"].unique().sort().to_list()
    out_parts: list[pl.DataFrame] = []

    y_true = df["truth_final"].to_numpy().astype(int)
    base_pred = df["pred_final"].to_numpy().astype(int)
    x_all = _meta_features(df)

    batch_idx = df.select("pred_batch").to_series().to_numpy().astype(int)
    last_clf = None
    last_thr = 0.80

    for i, b in enumerate(batches):
        if i == 0:
            cur_mask = batch_idx == b
            cur_df = df.filter(pl.col("pred_batch") == int(b)).with_columns(pl.col("pred_final").alias("pred_step1_meta"))
            out_parts.append(cur_df)
            continue

        start_i = max(0, i - int(lookback_batches))
        hist_batches = set(int(x) for x in batches[start_i:i])
        hist_mask = np.isin(batch_idx, np.array(sorted(hist_batches), dtype=int))
        cur_mask = batch_idx == int(b)

        x_hist = x_all[hist_mask]
        y_hist = ((base_pred[hist_mask] == y_true[hist_mask]) & (base_pred[hist_mask] != LABEL_HOLD)).astype(int)

        retrain_now = (last_clf is None) or (i % max(1, int(retrain_every_batches)) == 0)

        if x_hist.shape[0] < 256 or len(np.unique(y_hist)) < 2 or not retrain_now:
            if last_clf is not None and x_hist.shape[0] >= 32:
                prob_cur = last_clf.predict_proba(x_all[cur_mask])[:, 1]
                pred_cur = _gate_predictions(base_pred[cur_mask], prob_cur, last_thr)
            else:
                pred_cur = base_pred[cur_mask]
            cur_df = df.filter(pl.col("pred_batch") == int(b)).with_columns(pl.Series("pred_step1_meta", pred_cur))
            out_parts.append(cur_df)
            continue

        if x_hist.shape[0] < 256 or len(np.unique(y_hist)) < 2:
            pred_cur = base_pred[cur_mask]
            cur_df = df.filter(pl.col("pred_batch") == int(b)).with_columns(pl.Series("pred_step1_meta", pred_cur))
            out_parts.append(cur_df)
            continue

        n_hist = x_hist.shape[0]
        val_n = max(64, int(n_hist * float(val_tail_ratio)))
        val_n = min(val_n, max(64, n_hist // 2))
        fit_n = n_hist - val_n

        x_fit = x_hist[:fit_n]
        y_fit = y_hist[:fit_n]
        x_val = x_hist[fit_n:]

        base_val = base_pred[hist_mask][fit_n:]
        truth_val = y_true[hist_mask][fit_n:]
        pb_val = batch_idx[hist_mask][fit_n:]

        clf = LogisticRegression(C=0.5, solver="lbfgs", max_iter=300, random_state=int(seed))
        clf.fit(x_fit, y_fit)
        prob_val = clf.predict_proba(x_val)[:, 1]

        best_thr = 0.80
        best_score = float("inf")
        for thr in np.linspace(0.50, 0.98, 49):
            pred_val = _gate_predictions(base_val, prob_val, float(thr))
            tmp = pl.DataFrame({"pred_batch": pb_val, "truth_final": truth_val, "truth_final4": truth_val, "p": pred_val})
            m = _metrics(tmp.rename({"p": "pred"}), "pred")
            cadence_pen = 0.0
            if not np.isfinite(m.batches_per_signal):
                cadence_pen = 1.0
            elif m.batches_per_signal < 10.0:
                cadence_pen = (10.0 - m.batches_per_signal) / 10.0
            elif m.batches_per_signal > 15.0:
                cadence_pen = (m.batches_per_signal - 15.0) / 15.0
            score = (
                4.0 * m.opposite_fp_rate_active
                + 3.0 * m.opposite_fp_rate_covered
                + 2.0 * (1.0 - m.directional_active_safe_accuracy)
                + 1.0 * cadence_pen
            )
            if score < best_score:
                best_score = float(score)
                best_thr = float(thr)

        clf_full = LogisticRegression(C=0.5, solver="lbfgs", max_iter=300, random_state=int(seed))
        clf_full.fit(x_hist, y_hist)
        prob_cur = clf_full.predict_proba(x_all[cur_mask])[:, 1]
        pred_cur = _gate_predictions(base_pred[cur_mask], prob_cur, best_thr)
        last_clf = clf_full
        last_thr = best_thr

        cur_df = df.filter(pl.col("pred_batch") == int(b)).with_columns(pl.Series("pred_step1_meta", pred_cur))
        out_parts.append(cur_df)

        if verbose and (i % 100 == 0):
            print(f"[step1-meta] batch={b} history_rows={n_hist} best_thr={best_thr:.3f}")

    return pl.concat(out_parts).sort(["pred_batch", "anchor_15m_ts"])


def _batch_features_for_router(df_strict: pl.DataFrame, df_dual: pl.DataFrame) -> pl.DataFrame:
    s = df_strict.select(
        "pred_batch",
        pl.col("pred_final").alias("pred_s"),
        pl.col("score_final").alias("score_s"),
        "truth_final",
        "truth_final4",
    )
    d = df_dual.select(
        "pred_batch",
        pl.col("pred_final").alias("pred_d"),
        pl.col("score_final").alias("score_d"),
    )
    j = s.with_row_index("idx").join(d.with_row_index("idx"), on=["idx", "pred_batch"], how="inner")

    def _cost_expr(pred_col: str) -> pl.Expr:
        return (
            pl.when((pl.col("truth_final") == LABEL_UP) & (pl.col(pred_col) == LABEL_DOWN))
            .then(2)
            .when((pl.col("truth_final") == LABEL_DOWN) & (pl.col(pred_col) == LABEL_UP))
            .then(2)
            .when((pl.col("truth_final") == LABEL_HOLD) & (pl.col(pred_col) != LABEL_HOLD))
            .then(1)
            .when((pl.col("truth_final") != LABEL_HOLD) & (pl.col(pred_col) == LABEL_HOLD))
            .then(1)
            .otherwise(0)
        )

    b = (
        j.group_by("pred_batch")
        .agg(
            ((pl.col("pred_s") != LABEL_HOLD).cast(pl.Float64)).mean().alias("strict_active_rate"),
            ((pl.col("pred_d") != LABEL_HOLD).cast(pl.Float64)).mean().alias("dual_active_rate"),
            ((pl.col("pred_s") != pl.col("pred_d")).cast(pl.Float64)).mean().alias("disagreement_rate"),
            pl.col("score_s").abs().mean().alias("strict_abs_score_mean"),
            pl.col("score_d").abs().mean().alias("dual_abs_score_mean"),
            _cost_expr("pred_s").cast(pl.Float64).mean().alias("strict_cost_mean"),
            _cost_expr("pred_d").cast(pl.Float64).mean().alias("dual_cost_mean"),
        )
        .sort("pred_batch")
        .with_columns((pl.col("dual_cost_mean") < pl.col("strict_cost_mean")).cast(pl.Int64).alias("dual_better"))
    )
    return b


def _router_step(
    df_strict: pl.DataFrame,
    df_dual: pl.DataFrame,
    lookback_batches: int,
    retrain_every_batches: int,
    seed: int,
    verbose: bool,
) -> pl.DataFrame:
    batch_feats = _batch_features_for_router(df_strict, df_dual)
    batches = batch_feats["pred_batch"].to_list()

    cols_x = [
        "strict_active_rate",
        "dual_active_rate",
        "disagreement_rate",
        "strict_abs_score_mean",
        "dual_abs_score_mean",
    ]

    choices: list[tuple[int, str, float]] = []
    last_clf = None
    for i, b in enumerate(batches):
        if i == 0:
            choices.append((int(b), "strict", 0.0))
            continue
        lo = max(0, i - int(lookback_batches))
        hist = batch_feats.slice(lo, i - lo)
        retrain_now = (last_clf is None) or (i % max(1, int(retrain_every_batches)) == 0)
        if hist.height < 40 or hist["dual_better"].n_unique() < 2:
            choices.append((int(b), "strict", 0.0))
            continue

        if retrain_now:
            x = hist.select(cols_x).to_numpy().astype(float)
            y = hist["dual_better"].to_numpy().astype(int)
            clf = LogisticRegression(C=1.0, solver="lbfgs", max_iter=300, random_state=int(seed))
            clf.fit(x, y)
            last_clf = clf

        cur = batch_feats.filter(pl.col("pred_batch") == int(b)).select(cols_x).to_numpy().astype(float)
        p_dual = float(last_clf.predict_proba(cur)[0, 1]) if last_clf is not None else 0.0
        policy = "dual" if p_dual >= 0.5 else "strict"
        choices.append((int(b), policy, p_dual))
        if verbose and (i % 100 == 0):
            print(f"[step4-router] batch={b} p_dual={p_dual:.3f} policy={policy}")

    cdf = pl.DataFrame(choices, schema=["pred_batch", "policy", "p_dual_better"])
    s = df_strict.join(cdf, on="pred_batch", how="left")
    d = df_dual.select("pred_batch", "anchor_15m_ts", pl.col("pred_final").alias("pred_dual"))
    j = s.join(d, on=["pred_batch", "anchor_15m_ts"], how="left")
    out = j.with_columns(
        pl.when(pl.col("policy") == "dual").then(pl.col("pred_dual")).otherwise(pl.col("pred_final")).alias("pred_step4_router")
    )
    return out.sort(["pred_batch", "anchor_15m_ts"])


def main() -> None:
    args = parse_args()
    strict_dir = Path(args.strict_run_dir).expanduser().resolve()
    dual_dir = Path(args.dual_run_dir).expanduser().resolve()

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    tag = str(args.output_tag).strip().replace(" ", "_")
    out_dir = Path(args.output_dir).expanduser().resolve() / (f"{ts}_{tag}" if tag else ts)
    out_dir.mkdir(parents=True, exist_ok=True)

    df_strict = _load_run(strict_dir)
    df_dual = _load_run(dual_dir)

    keys = ["pred_batch", "anchor_15m_ts"]
    if df_strict.select(keys).height != df_dual.select(keys).height:
        raise RuntimeError("Strict and dual runs have different row counts")

    step1_df = _meta_step(
        df=df_strict,
        lookback_batches=int(args.meta_lookback_batches),
        retrain_every_batches=int(args.meta_retrain_every_batches),
        val_tail_ratio=float(args.val_tail_ratio),
        seed=int(args.seed),
        verbose=bool(args.verbose),
    )
    step4_df = _router_step(
        df_strict=df_strict,
        df_dual=df_dual,
        lookback_batches=int(args.router_lookback_batches),
        retrain_every_batches=int(args.router_retrain_every_batches),
        seed=int(args.seed),
        verbose=bool(args.verbose),
    )

    m1 = _metrics(step1_df, "pred_step1_meta")
    m4 = _metrics(step4_df, "pred_step4_router")

    step1_path = out_dir / "step1_meta_predictions.parquet"
    step4_path = out_dir / "step4_router_predictions.parquet"
    step1_df.write_parquet(step1_path)
    step4_df.write_parquet(step4_path)

    summary = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "strict_run_dir": str(strict_dir),
            "dual_run_dir": str(dual_dir),
            "meta_lookback_batches": int(args.meta_lookback_batches),
            "router_lookback_batches": int(args.router_lookback_batches),
            "meta_retrain_every_batches": int(args.meta_retrain_every_batches),
            "router_retrain_every_batches": int(args.router_retrain_every_batches),
        },
        "step1_meta": m1.__dict__,
        "step4_router": m4.__dict__,
        "artifacts": {
            "step1_meta_predictions": str(step1_path),
            "step4_router_predictions": str(step4_path),
        },
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
