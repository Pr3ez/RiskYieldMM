#!/usr/bin/env python3
"""Regime-router ensemble over winner-12 combos (live-style, no lookahead).

Method:
  1) Build live-safe row-level consensus features from combo predictions.
  2) Cluster historical rows into regimes (KMeans).
  3) Learn specialist combo weights per regime from past accuracy only.
  4) Predict next batches with regime-specific weighted probability ensemble.
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl
from sklearn.cluster import KMeans
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


def _resolve_project_root(cli_root: str | None) -> Path:
    if cli_root:
        return Path(cli_root).expanduser().resolve()
    return Path(__file__).resolve().parents[1]


def _resolve_latest_run(base: Path) -> Path:
    runs = sorted([p for p in base.glob("*") if p.is_dir()])
    if not runs:
        raise FileNotFoundError(f"No runs found in: {base}")
    return runs[-1].resolve()


def _resolve_run_dir(base: Path, run_dir: str | None) -> Path:
    if run_dir:
        direct = Path(run_dir).expanduser()
        if direct.exists():
            return direct.resolve()
        child = base / run_dir
        if child.exists():
            return child.resolve()
        raise FileNotFoundError(
            f"Run dir not found: {run_dir!r} (checked {direct}, {child})"
        )
    return _resolve_latest_run(base)


def _parse_unit(unit: str) -> tuple[str, str]:
    if "/" not in unit:
        raise ValueError(f"unit must be <timeframe>/<target>, got {unit!r}")
    return unit.split("/", 1)


def _compute_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float]:
    y_true = np.asarray(y_true, dtype=np.int32)
    y_pred = np.asarray(y_pred, dtype=np.int32)
    if y_true.size == 0:
        return {
            "accuracy": 0.0,
            "macro_recall": 0.0,
            "macro_f1": 0.0,
            "cross_direction_error": 0.0,
        }

    acc = float(np.mean(y_true == y_pred))
    recalls = []
    f1s = []
    for c in range(4):
        true_c = y_true == c
        pred_c = y_pred == c
        tp = int(np.sum(true_c & pred_c))
        fp = int(np.sum((~true_c) & pred_c))
        support = int(np.sum(true_c))
        recall = float(tp / support) if support > 0 else 0.0
        precision = float(tp / (tp + fp)) if (tp + fp) > 0 else 0.0
        f1 = (
            float(2.0 * precision * recall / (precision + recall))
            if (precision + recall) > 0
            else 0.0
        )
        recalls.append(recall)
        f1s.append(f1)

    true_up = y_true >= 2
    true_down = y_true <= 1
    pred_up = y_pred >= 2
    pred_down = y_pred <= 1
    cross_err = float(np.mean((true_up & pred_down) | (true_down & pred_up)))
    return {
        "accuracy": acc,
        "macro_recall": float(np.mean(recalls)),
        "macro_f1": float(np.mean(f1s)),
        "cross_direction_error": cross_err,
    }


def _fit_router(
    *,
    X_regime: np.ndarray,
    y_true: np.ndarray,
    combo_pred: np.ndarray,
    n_regimes: int,
    specialists_per_regime: int,
    min_rows_per_regime: int,
    random_seed: int,
) -> tuple[Pipeline, dict[int, tuple[np.ndarray, np.ndarray]], tuple[np.ndarray, np.ndarray]]:
    # Scaler + KMeans regime assignment
    pipe = Pipeline(
        steps=[
            ("scaler", StandardScaler(with_mean=True, with_std=True)),
            (
                "kmeans",
                KMeans(
                    n_clusters=int(max(2, n_regimes)),
                    n_init=10,
                    random_state=int(random_seed),
                ),
            ),
        ]
    )
    pipe.fit(X_regime)
    regimes = pipe.predict(X_regime).astype(np.int32, copy=False)
    combo_count = combo_pred.shape[1]
    combo_ids = np.arange(combo_count, dtype=np.int32)

    # Global fallback specialist set
    global_acc = np.mean(combo_pred == y_true[:, None], axis=0)
    g_order = np.argsort(-global_acc, kind="mergesort")
    g_sel = g_order[: max(1, min(int(specialists_per_regime), combo_count))]
    g_raw = np.maximum(global_acc[g_sel] - 0.20, 1e-6)
    g_w = g_raw / float(np.sum(g_raw))
    global_spec = (g_sel.astype(np.int32, copy=False), g_w.astype(np.float64, copy=False))

    per_regime: dict[int, tuple[np.ndarray, np.ndarray]] = {}
    for r in range(int(max(2, n_regimes))):
        idx = np.where(regimes == r)[0]
        if idx.size < int(max(10, min_rows_per_regime)):
            per_regime[r] = global_spec
            continue
        acc = np.mean(combo_pred[idx] == y_true[idx][:, None], axis=0)
        order = np.argsort(-acc, kind="mergesort")
        sel = order[: max(1, min(int(specialists_per_regime), combo_count))]
        raw = np.maximum(acc[sel] - 0.20, 1e-6)
        w = raw / float(np.sum(raw))
        per_regime[r] = (
            sel.astype(np.int32, copy=False),
            w.astype(np.float64, copy=False),
        )

    return pipe, per_regime, global_spec


def _predict_with_router(
    *,
    router: Pipeline,
    per_regime_specs: dict[int, tuple[np.ndarray, np.ndarray]],
    global_spec: tuple[np.ndarray, np.ndarray],
    X_regime: np.ndarray,
    X_probs: np.ndarray,  # shape [n_rows, combo_count, 4]
) -> tuple[np.ndarray, np.ndarray]:
    regimes = router.predict(X_regime).astype(np.int32, copy=False)
    n_rows = X_probs.shape[0]
    out_p = np.zeros((n_rows, 4), dtype=np.float64)

    for r in np.unique(regimes):
        idx = np.where(regimes == r)[0]
        sel, w = per_regime_specs.get(int(r), global_spec)
        # Weighted sum over selected combo axes -> [rows_in_r, 4]
        out_p[idx] = np.tensordot(X_probs[idx][:, sel, :], w, axes=(1, 0))

    y_pred = np.argmax(out_p, axis=1).astype(np.int32, copy=False)
    return y_pred, regimes


def _build_batch_metrics(
    *,
    pred_batches: np.ndarray,
    y_true: np.ndarray,
    y_pred_model: np.ndarray,
    y_pred_uniform: np.ndarray,
    winner_map: dict[int, tuple[str, float]],
    oracle_map: dict[int, tuple[str, float]],
    extra_cols: dict[str, dict[int, Any]] | None = None,
) -> pl.DataFrame:
    rows: list[dict[str, Any]] = []
    for pb in sorted(np.unique(pred_batches).tolist()):
        m = pred_batches == pb
        yt = y_true[m]
        ym = y_pred_model[m]
        yu = y_pred_uniform[m]
        mm = _compute_metrics(yt, ym)
        mu = _compute_metrics(yt, yu)
        winner_combo, winner_acc = winner_map.get(int(pb), (None, np.nan))
        oracle_combo, oracle_acc = oracle_map.get(int(pb), (None, np.nan))
        row = {
            "pred_batch": int(pb),
            "rows": int(np.sum(m)),
            "winner_combo_key": winner_combo,
            "winner_accuracy": float(winner_acc) if winner_acc == winner_acc else None,
            "oracle_best_combo": oracle_combo,
            "oracle_best_combo_accuracy": float(oracle_acc)
            if oracle_acc == oracle_acc
            else None,
            "model_accuracy": float(mm["accuracy"]),
            "uniform_accuracy": float(mu["accuracy"]),
            "model_macro_f1": float(mm["macro_f1"]),
            "uniform_macro_f1": float(mu["macro_f1"]),
            "model_cross_direction_error": float(mm["cross_direction_error"]),
            "uniform_cross_direction_error": float(mu["cross_direction_error"]),
            "delta_accuracy_model_vs_uniform": float(mm["accuracy"] - mu["accuracy"]),
            "delta_macro_f1_model_vs_uniform": float(mm["macro_f1"] - mu["macro_f1"]),
            "delta_cross_direction_error_model_vs_uniform": float(
                mm["cross_direction_error"] - mu["cross_direction_error"]
            ),
            "model_beats_uniform_accuracy": bool(mm["accuracy"] > mu["accuracy"]),
        }
        if extra_cols is not None:
            for k, vmap in extra_cols.items():
                row[k] = vmap.get(int(pb))
        rows.append(row)
    return pl.DataFrame(rows).sort("pred_batch")


def run_analysis(
    *,
    project_root: Path,
    run_id: str,
    model_name: str,
    unit: str,
    probability_run_dir: str | None,
    holdout_steps: int,
    wf_warmup_steps: int,
    wf_retrain_every_steps: int,
    max_train_batches: int | None,
    n_regimes: int,
    specialists_per_regime: int,
    min_rows_per_regime: int,
    random_seed: int,
    output_dir: Path,
    verbose: bool,
) -> dict[str, Any]:
    tf, target = _parse_unit(unit)
    unit_dir = (
        project_root / "data" / "htf_backtest_results" / run_id / model_name / tf / target
    )
    if not unit_dir.exists():
        raise FileNotFoundError(f"Unit directory not found: {unit_dir}")

    prob_base = project_root / "prediction_analysis" / "winner12_probability_outputs"
    prob_dir = _resolve_run_dir(prob_base, probability_run_dir)
    pred_rows_path = prob_dir / "winner12_predictions_filtered.parquet"
    winners_path = unit_dir / "winners_all_steps.parquet"
    if not pred_rows_path.exists():
        raise FileNotFoundError(f"Missing: {pred_rows_path}")
    if not winners_path.exists():
        raise FileNotFoundError(f"Missing: {winners_path}")

    pred_rows = pl.read_parquet(pred_rows_path).sort(
        ["pred_batch", "action_key", "timestamp", "batch_id"]
    )
    req = {
        "pred_batch",
        "timestamp",
        "batch_id",
        "action_key",
        "y_true",
        "y_pred",
        "prob_class_0",
        "prob_class_1",
        "prob_class_2",
        "prob_class_3",
    }
    miss = sorted(list(req - set(pred_rows.columns)))
    if miss:
        raise ValueError(f"Missing columns in {pred_rows_path}: {miss}")

    combo_keys = sorted(pred_rows["action_key"].unique().to_list())
    combo_count = len(combo_keys)
    if combo_count == 0:
        raise ValueError("No combos in prediction rows.")

    if verbose:
        print(f"[Router] rows={len(pred_rows)} combos={combo_count} source={pred_rows_path}")

    winners = (
        pl.read_parquet(winners_path)
        .drop_nulls(["pred_batch", "winner_combo_key", "winner_accuracy"])
        .select(["pred_batch", "winner_combo_key", "winner_accuracy"])
        .unique(subset=["pred_batch"], keep="last")
        .sort("pred_batch")
    )
    winner_map = {
        int(r["pred_batch"]): (str(r["winner_combo_key"]), float(r["winner_accuracy"]))
        for r in winners.to_dicts()
    }

    # Oracle best combo accuracy by batch (for reference only).
    oracle_df = (
        pred_rows.group_by(["pred_batch", "action_key"])
        .agg((pl.col("y_true") == pl.col("y_pred")).mean().alias("combo_accuracy"))
        .sort(["pred_batch", "combo_accuracy", "action_key"], descending=[False, True, False])
        .group_by("pred_batch")
        .agg(
            [
                pl.col("action_key").first().alias("oracle_best_combo"),
                pl.col("combo_accuracy").first().alias("oracle_best_combo_accuracy"),
            ]
        )
        .sort("pred_batch")
    )
    oracle_map = {
        int(r["pred_batch"]): (
            str(r["oracle_best_combo"]),
            float(r["oracle_best_combo_accuracy"]),
        )
        for r in oracle_df.to_dicts()
    }

    # Build long-level derived cols for consensus features.
    enriched = pred_rows.with_columns(
        [
            pl.max_horizontal(["prob_class_0", "prob_class_1", "prob_class_2", "prob_class_3"]).alias(
                "prob_max"
            ),
            (
                pl.when(pl.col("y_pred") == 0)
                .then(pl.col("prob_class_0"))
                .when(pl.col("y_pred") == 1)
                .then(pl.col("prob_class_1"))
                .when(pl.col("y_pred") == 2)
                .then(pl.col("prob_class_2"))
                .otherwise(pl.col("prob_class_3"))
            ).alias("prob_pred_class"),
        ]
    )

    # Wide probability table [row x (combo x class)] + y_true
    agg_wide: list[pl.Expr] = [pl.col("y_true").first().alias("y_true")]
    for combo in combo_keys:
        for c in range(4):
            agg_wide.append(
                pl.col(f"prob_class_{c}")
                .filter(pl.col("action_key") == combo)
                .first()
                .alias(f"{combo}_p{c}")
            )

    wide_df = (
        enriched.group_by(["pred_batch", "timestamp", "batch_id"], maintain_order=True)
        .agg(agg_wide)
        .sort(["pred_batch", "timestamp", "batch_id"])
    )

    # Consensus regime features (all live-safe)
    consensus_df = (
        enriched.group_by(["pred_batch", "timestamp", "batch_id"], maintain_order=True)
        .agg(
            [
                pl.col("action_key").n_unique().alias("combos_present"),
                (pl.col("y_pred") == 0).mean().alias("vote_p0"),
                (pl.col("y_pred") == 1).mean().alias("vote_p1"),
                (pl.col("y_pred") == 2).mean().alias("vote_p2"),
                (pl.col("y_pred") == 3).mean().alias("vote_p3"),
                pl.col("prob_max").mean().alias("mean_prob_max"),
                pl.col("prob_max").std(ddof=1).fill_null(0.0).alias("std_prob_max"),
                pl.col("prob_pred_class").mean().alias("mean_prob_pred_class"),
            ]
        )
        .with_columns(
            [
                (pl.col("vote_p0") + pl.col("vote_p1")).alias("vote_p_down"),
                (pl.col("vote_p2") + pl.col("vote_p3")).alias("vote_p_up"),
                pl.max_horizontal(["vote_p0", "vote_p1", "vote_p2", "vote_p3"]).alias(
                    "vote_top1"
                ),
            ]
        )
        .with_columns(
            [
                (1.0 - pl.col("vote_top1")).alias("vote_disagreement"),
                (pl.col("vote_p_up") - pl.col("vote_p_down")).abs().alias(
                    "vote_direction_margin"
                ),
                (
                    -(
                        pl.when(pl.col("vote_p0") > 0)
                        .then(pl.col("vote_p0") * pl.col("vote_p0").log())
                        .otherwise(0.0)
                        + pl.when(pl.col("vote_p1") > 0)
                        .then(pl.col("vote_p1") * pl.col("vote_p1").log())
                        .otherwise(0.0)
                        + pl.when(pl.col("vote_p2") > 0)
                        .then(pl.col("vote_p2") * pl.col("vote_p2").log())
                        .otherwise(0.0)
                        + pl.when(pl.col("vote_p3") > 0)
                        .then(pl.col("vote_p3") * pl.col("vote_p3").log())
                        .otherwise(0.0)
                    )
                    / pl.lit(float(np.log(4.0)))
                ).alias("vote_entropy_norm"),
            ]
        )
        .sort(["pred_batch", "timestamp", "batch_id"])
    )

    row_df = wide_df.join(
        consensus_df,
        on=["pred_batch", "timestamp", "batch_id"],
        how="inner",
    ).filter(pl.col("combos_present") == combo_count)

    if row_df.is_empty():
        raise ValueError("No rows after full-coverage filter.")

    for c in range(4):
        cols = [f"{combo}_p{c}" for combo in combo_keys]
        row_df = row_df.with_columns(pl.mean_horizontal(cols).alias(f"uniform_p{c}"))
    row_df = row_df.with_columns(
        pl.max_horizontal(["uniform_p0", "uniform_p1", "uniform_p2", "uniform_p3"]).alias(
            "uniform_pmax"
        )
    ).with_columns(
        pl.when(pl.col("uniform_p0") == pl.col("uniform_pmax"))
        .then(0)
        .when(pl.col("uniform_p1") == pl.col("uniform_pmax"))
        .then(1)
        .when(pl.col("uniform_p2") == pl.col("uniform_pmax"))
        .then(2)
        .otherwise(3)
        .alias("y_pred_uniform")
    )

    row_df = row_df.sort(["pred_batch", "timestamp", "batch_id"])

    regime_feature_cols = [
        "vote_p0",
        "vote_p1",
        "vote_p2",
        "vote_p3",
        "vote_p_down",
        "vote_p_up",
        "vote_top1",
        "vote_disagreement",
        "vote_direction_margin",
        "vote_entropy_norm",
        "mean_prob_max",
        "std_prob_max",
        "mean_prob_pred_class",
    ]
    prob_feature_cols = [f"{combo}_p{c}" for combo in combo_keys for c in range(4)]

    X_regime = row_df.select(regime_feature_cols).to_numpy().astype(np.float32, copy=False)
    X_prob_flat = row_df.select(prob_feature_cols).to_numpy().astype(np.float32, copy=False)
    X_probs = X_prob_flat.reshape((-1, combo_count, 4))
    combo_pred = np.argmax(X_probs, axis=2).astype(np.int32, copy=False)
    y_true = row_df["y_true"].to_numpy().astype(np.int32, copy=False)
    y_pred_uniform = row_df["y_pred_uniform"].to_numpy().astype(np.int32, copy=False)
    pred_batches = row_df["pred_batch"].to_numpy().astype(np.int32, copy=False)
    timestamps = row_df["timestamp"].to_numpy()
    batch_ids = row_df["batch_id"].to_numpy().astype(np.int32, copy=False)

    uniq_batches = np.asarray(sorted(np.unique(pred_batches).tolist()), dtype=np.int32)
    n_batches = int(len(uniq_batches))
    holdout_steps = int(max(1, min(holdout_steps, n_batches - 1)))
    wf_warmup_steps = int(max(1, min(wf_warmup_steps, n_batches - 1)))
    wf_retrain_every_steps = int(max(1, wf_retrain_every_steps))
    max_train_batches = (
        None if (max_train_batches is None or max_train_batches <= 0) else int(max_train_batches)
    )

    # Static holdout
    train_batches_static = uniq_batches[:-holdout_steps]
    holdout_batches = uniq_batches[-holdout_steps:]
    train_mask_static = np.isin(pred_batches, train_batches_static)
    holdout_mask = np.isin(pred_batches, holdout_batches)

    t_fit = time.time()
    router_holdout, regime_specs_holdout, global_spec_holdout = _fit_router(
        X_regime=X_regime[train_mask_static],
        y_true=y_true[train_mask_static],
        combo_pred=combo_pred[train_mask_static],
        n_regimes=int(n_regimes),
        specialists_per_regime=int(specialists_per_regime),
        min_rows_per_regime=int(min_rows_per_regime),
        random_seed=int(random_seed),
    )
    holdout_fit_s = time.time() - t_fit
    y_pred_holdout, regime_holdout = _predict_with_router(
        router=router_holdout,
        per_regime_specs=regime_specs_holdout,
        global_spec=global_spec_holdout,
        X_regime=X_regime[holdout_mask],
        X_probs=X_probs[holdout_mask],
    )
    holdout_metrics_model = _compute_metrics(y_true[holdout_mask], y_pred_holdout)
    holdout_metrics_uniform = _compute_metrics(y_true[holdout_mask], y_pred_uniform[holdout_mask])

    holdout_batch_df = _build_batch_metrics(
        pred_batches=pred_batches[holdout_mask],
        y_true=y_true[holdout_mask],
        y_pred_model=y_pred_holdout,
        y_pred_uniform=y_pred_uniform[holdout_mask],
        winner_map=winner_map,
        oracle_map=oracle_map,
        extra_cols={
            "router_regime_mean": {
                int(pb): float(np.mean(regime_holdout[pred_batches[holdout_mask] == pb]))
                for pb in np.unique(pred_batches[holdout_mask]).tolist()
            }
        },
    ).with_columns(pl.lit("holdout").alias("mode"))

    holdout_row_df = pl.DataFrame(
        {
            "pred_batch": pred_batches[holdout_mask],
            "timestamp": timestamps[holdout_mask],
            "batch_id": batch_ids[holdout_mask],
            "y_true": y_true[holdout_mask],
            "y_pred_model": y_pred_holdout,
            "y_pred_uniform": y_pred_uniform[holdout_mask],
            "regime_id": regime_holdout.astype(np.int32, copy=False),
        }
    ).sort(["pred_batch", "timestamp", "batch_id"])

    # Walk-forward
    idx_by_batch = {int(pb): np.where(pred_batches == int(pb))[0] for pb in uniq_batches.tolist()}
    wf_batch_rows: list[dict[str, Any]] = []
    wf_row_frames: list[pl.DataFrame] = []
    retrain_count = 0
    curr_router: Pipeline | None = None
    curr_specs: dict[int, tuple[np.ndarray, np.ndarray]] | None = None
    curr_global: tuple[np.ndarray, np.ndarray] | None = None

    wf_model_preds: list[np.ndarray] = []
    wf_uniform_preds: list[np.ndarray] = []
    wf_true: list[np.ndarray] = []
    wf_pb: list[np.ndarray] = []

    for i in range(wf_warmup_steps, n_batches):
        pb = int(uniq_batches[i])
        hist_batches = uniq_batches[:i]
        if max_train_batches is not None and len(hist_batches) > max_train_batches:
            hist_batches = hist_batches[-max_train_batches:]
        train_idx = np.where(np.isin(pred_batches, hist_batches))[0]
        pred_idx = idx_by_batch[pb]

        should_retrain = curr_router is None or ((i - wf_warmup_steps) % wf_retrain_every_steps == 0)
        fit_s = 0.0
        if should_retrain:
            t0 = time.time()
            curr_router, curr_specs, curr_global = _fit_router(
                X_regime=X_regime[train_idx],
                y_true=y_true[train_idx],
                combo_pred=combo_pred[train_idx],
                n_regimes=int(n_regimes),
                specialists_per_regime=int(specialists_per_regime),
                min_rows_per_regime=int(min_rows_per_regime),
                random_seed=int(random_seed),
            )
            fit_s = time.time() - t0
            retrain_count += 1

        assert curr_router is not None and curr_specs is not None and curr_global is not None
        y_pred_b, regime_b = _predict_with_router(
            router=curr_router,
            per_regime_specs=curr_specs,
            global_spec=curr_global,
            X_regime=X_regime[pred_idx],
            X_probs=X_probs[pred_idx],
        )
        yt = y_true[pred_idx]
        yu = y_pred_uniform[pred_idx]

        wf_model_preds.append(y_pred_b)
        wf_uniform_preds.append(yu)
        wf_true.append(yt)
        wf_pb.append(np.full(len(pred_idx), pb, dtype=np.int32))

        mm = _compute_metrics(yt, y_pred_b)
        mu = _compute_metrics(yt, yu)
        winner_combo, winner_acc = winner_map.get(pb, (None, np.nan))
        oracle_combo, oracle_acc = oracle_map.get(pb, (None, np.nan))
        wf_batch_rows.append(
            {
                "pred_batch": pb,
                "rows": int(len(pred_idx)),
                "winner_combo_key": winner_combo,
                "winner_accuracy": float(winner_acc) if winner_acc == winner_acc else None,
                "oracle_best_combo": oracle_combo,
                "oracle_best_combo_accuracy": float(oracle_acc)
                if oracle_acc == oracle_acc
                else None,
                "model_accuracy": float(mm["accuracy"]),
                "uniform_accuracy": float(mu["accuracy"]),
                "model_macro_f1": float(mm["macro_f1"]),
                "uniform_macro_f1": float(mu["macro_f1"]),
                "model_cross_direction_error": float(mm["cross_direction_error"]),
                "uniform_cross_direction_error": float(mu["cross_direction_error"]),
                "delta_accuracy_model_vs_uniform": float(mm["accuracy"] - mu["accuracy"]),
                "delta_macro_f1_model_vs_uniform": float(mm["macro_f1"] - mu["macro_f1"]),
                "delta_cross_direction_error_model_vs_uniform": float(
                    mm["cross_direction_error"] - mu["cross_direction_error"]
                ),
                "model_beats_uniform_accuracy": bool(mm["accuracy"] > mu["accuracy"]),
                "router_regime_mean": float(np.mean(regime_b)),
                "retrained_this_step": bool(should_retrain),
                "fit_time_s": float(fit_s),
                "train_batches_used": int(len(hist_batches)),
            }
        )

        wf_row_frames.append(
            pl.DataFrame(
                {
                    "pred_batch": np.full(len(pred_idx), pb, dtype=np.int32),
                    "timestamp": timestamps[pred_idx],
                    "batch_id": batch_ids[pred_idx],
                    "y_true": yt,
                    "y_pred_model": y_pred_b,
                    "y_pred_uniform": yu,
                    "regime_id": regime_b.astype(np.int32, copy=False),
                }
            )
        )

        if verbose and ((i - wf_warmup_steps + 1) % 25 == 0):
            done = i - wf_warmup_steps + 1
            total = n_batches - wf_warmup_steps
            print(
                f"[Router][WF] step={done}/{total} pred_batch={pb} "
                f"retrain={int(should_retrain)} model_acc={mm['accuracy']:.4f}"
            )

    wf_pred_all = np.concatenate(wf_model_preds).astype(np.int32, copy=False)
    wf_uniform_all = np.concatenate(wf_uniform_preds).astype(np.int32, copy=False)
    wf_true_all = np.concatenate(wf_true).astype(np.int32, copy=False)
    wf_metrics_model = _compute_metrics(wf_true_all, wf_pred_all)
    wf_metrics_uniform = _compute_metrics(wf_true_all, wf_uniform_all)

    wf_batch_df = pl.DataFrame(wf_batch_rows).sort("pred_batch").with_columns(
        pl.lit("walkforward").alias("mode")
    )
    wf_row_df = pl.concat(wf_row_frames, how="diagonal_relaxed").sort(
        ["pred_batch", "timestamp", "batch_id"]
    )

    # Save outputs
    out_run = output_dir / datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    out_run.mkdir(parents=True, exist_ok=True)

    feature_table_parquet = out_run / "winner12_router_feature_table.parquet"
    feature_columns_json = out_run / "winner12_router_feature_columns.json"
    holdout_batch_parquet = out_run / "winner12_router_holdout_batch_metrics.parquet"
    holdout_batch_csv = out_run / "winner12_router_holdout_batch_metrics.csv"
    holdout_rows_parquet = out_run / "winner12_router_holdout_row_predictions.parquet"
    wf_batch_parquet = out_run / "winner12_router_walkforward_batch_metrics.parquet"
    wf_batch_csv = out_run / "winner12_router_walkforward_batch_metrics.csv"
    wf_rows_parquet = out_run / "winner12_router_walkforward_row_predictions.parquet"
    summary_json = out_run / "winner12_router_summary.json"

    row_df.write_parquet(feature_table_parquet)
    holdout_batch_df.write_parquet(holdout_batch_parquet)
    holdout_batch_df.write_csv(holdout_batch_csv)
    holdout_row_df.write_parquet(holdout_rows_parquet)
    wf_batch_df.write_parquet(wf_batch_parquet)
    wf_batch_df.write_csv(wf_batch_csv)
    wf_row_df.write_parquet(wf_rows_parquet)
    with open(feature_columns_json, "w") as f:
        json.dump(
            {
                "regime_feature_columns": regime_feature_cols,
                "probability_feature_columns": prob_feature_cols,
                "combo_keys": combo_keys,
            },
            f,
            indent=2,
        )

    summary = {
        "run_id": run_id,
        "unit": unit,
        "model_name": model_name,
        "source": {
            "probability_run_dir": str(prob_dir),
            "pred_rows_path": str(pred_rows_path),
            "winners_path": str(winners_path),
        },
        "config": {
            "holdout_steps": int(holdout_steps),
            "wf_warmup_steps": int(wf_warmup_steps),
            "wf_retrain_every_steps": int(wf_retrain_every_steps),
            "max_train_batches": int(max_train_batches) if max_train_batches else None,
            "n_regimes": int(n_regimes),
            "specialists_per_regime": int(specialists_per_regime),
            "min_rows_per_regime": int(min_rows_per_regime),
            "random_seed": int(random_seed),
            "combo_count": int(combo_count),
            "regime_feature_count": int(len(regime_feature_cols)),
        },
        "rows": {
            "pred_rows_long": int(len(pred_rows)),
            "row_feature_rows": int(len(row_df)),
            "holdout_rows": int(len(holdout_row_df)),
            "walkforward_rows": int(len(wf_row_df)),
            "batches_total": int(n_batches),
            "batches_holdout": int(len(holdout_batches)),
            "batches_walkforward": int(len(wf_batch_df)),
        },
        "metrics": {
            "holdout": {
                "model": holdout_metrics_model,
                "uniform": holdout_metrics_uniform,
                "mean_delta_accuracy_model_vs_uniform": float(
                    holdout_batch_df["delta_accuracy_model_vs_uniform"].mean()
                ),
                "share_model_beats_uniform_accuracy": float(
                    holdout_batch_df["model_beats_uniform_accuracy"]
                    .cast(pl.Int8, strict=False)
                    .mean()
                ),
                "fit_time_s": float(holdout_fit_s),
            },
            "walkforward": {
                "model": wf_metrics_model,
                "uniform": wf_metrics_uniform,
                "mean_delta_accuracy_model_vs_uniform": float(
                    wf_batch_df["delta_accuracy_model_vs_uniform"].mean()
                ),
                "share_model_beats_uniform_accuracy": float(
                    wf_batch_df["model_beats_uniform_accuracy"]
                    .cast(pl.Int8, strict=False)
                    .mean()
                ),
                "retrain_count": int(retrain_count),
                "mean_fit_time_s_when_retrain": float(
                    wf_batch_df.filter(pl.col("retrained_this_step"))["fit_time_s"].mean()
                ),
            },
        },
        "artifacts": {
            "winner12_router_feature_table_parquet": str(feature_table_parquet),
            "winner12_router_feature_columns_json": str(feature_columns_json),
            "winner12_router_holdout_batch_metrics_parquet": str(holdout_batch_parquet),
            "winner12_router_holdout_batch_metrics_csv": str(holdout_batch_csv),
            "winner12_router_holdout_row_predictions_parquet": str(holdout_rows_parquet),
            "winner12_router_walkforward_batch_metrics_parquet": str(wf_batch_parquet),
            "winner12_router_walkforward_batch_metrics_csv": str(wf_batch_csv),
            "winner12_router_walkforward_row_predictions_parquet": str(wf_rows_parquet),
            "winner12_router_summary_json": str(summary_json),
        },
    }
    with open(summary_json, "w") as f:
        json.dump(summary, f, indent=2)

    return summary


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Regime-router analysis over winner-12 probabilities."
    )
    p.add_argument("--project-root", type=str, default=None)
    p.add_argument("--run-id", type=str, default="stage1_catboost_live")
    p.add_argument("--model-name", type=str, default="catboost")
    p.add_argument("--unit", type=str, default="1m/target_4class")
    p.add_argument("--probability-run-dir", type=str, default=None)
    p.add_argument("--holdout-steps", type=int, default=200)
    p.add_argument("--wf-warmup-steps", type=int, default=120)
    p.add_argument("--wf-retrain-every-steps", type=int, default=25)
    p.add_argument("--max-train-batches", type=int, default=300)
    p.add_argument("--n-regimes", type=int, default=4)
    p.add_argument("--specialists-per-regime", type=int, default=4)
    p.add_argument("--min-rows-per-regime", type=int, default=1000)
    p.add_argument("--random-seed", type=int, default=42)
    p.add_argument("--verbose", action="store_true")
    p.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Default: <project_root>/prediction_analysis/winner12_regime_router_outputs",
    )
    return p


def main() -> None:
    args = build_parser().parse_args()
    project_root = _resolve_project_root(args.project_root)
    output_dir = (
        Path(args.output_dir).expanduser().resolve()
        if args.output_dir
        else project_root / "prediction_analysis" / "winner12_regime_router_outputs"
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    summary = run_analysis(
        project_root=project_root,
        run_id=args.run_id,
        model_name=args.model_name,
        unit=args.unit,
        probability_run_dir=args.probability_run_dir,
        holdout_steps=int(args.holdout_steps),
        wf_warmup_steps=int(args.wf_warmup_steps),
        wf_retrain_every_steps=int(args.wf_retrain_every_steps),
        max_train_batches=int(args.max_train_batches),
        n_regimes=int(args.n_regimes),
        specialists_per_regime=int(args.specialists_per_regime),
        min_rows_per_regime=int(args.min_rows_per_regime),
        random_seed=int(args.random_seed),
        output_dir=output_dir,
        verbose=bool(args.verbose),
    )

    hm = summary["metrics"]["holdout"]
    wm = summary["metrics"]["walkforward"]
    print("Winner-12 regime-router analysis complete")
    print(f"  Run: {summary['run_id']} | Unit: {summary['unit']}")
    print(
        "  Holdout accuracy: "
        f"model={hm['model']['accuracy']:.4f}, uniform={hm['uniform']['accuracy']:.4f}"
    )
    print(
        "  Holdout macro_f1: "
        f"model={hm['model']['macro_f1']:.4f}, uniform={hm['uniform']['macro_f1']:.4f}"
    )
    print(
        "  Walk-forward accuracy: "
        f"model={wm['model']['accuracy']:.4f}, uniform={wm['uniform']['accuracy']:.4f}"
    )
    print(
        "  Walk-forward macro_f1: "
        f"model={wm['model']['macro_f1']:.4f}, uniform={wm['uniform']['macro_f1']:.4f}"
    )
    print("  Artifacts:")
    for k, v in summary["artifacts"].items():
        print(f"    {k}: {v}")


if __name__ == "__main__":
    main()

