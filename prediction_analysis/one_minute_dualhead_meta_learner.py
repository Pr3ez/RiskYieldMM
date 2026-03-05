#!/usr/bin/env python3
"""
1m-only dual-head meta-learner (causal walk-forward).

Builds separate logistic meta-models for:
- 1m/target_breakfree (3-class)
- 1m/target_4class direction (2-class up/down)

Then composes final prediction with the same cross-target final-rule logic.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


UNITS = ["1m/target_breakfree", "1m/target_4class"]
DEFAULT_OUTPUT_DIR = "prediction_analysis/multitimeframe_cross_target_validation"


@dataclass
class HeadModel:
    pipeline: Pipeline | None
    constant_class: int | None
    class_to_col: dict[int, int]


def _load_core_module(project_root: Path):
    mod_path = (project_root / "prediction_analysis" / "multitimeframe_cross_target_ensemble_search.py").resolve()
    spec = importlib.util.spec_from_file_location("ctes_mod", mod_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module spec: {mod_path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _build_candidate_meta(candidate_sets: dict[str, Any], units: list[str]) -> pl.DataFrame:
    rows: list[dict[str, Any]] = []
    for unit in units:
        meta = candidate_sets.get(unit)
        if meta is None:
            raise KeyError(f"Unit not found in candidate sets: {unit}")
        tf, target = unit.split("/", 1)
        wins = {str(k): int(v) for k, v in (meta.get("winner_wins", {}) or {}).items()}
        action_keys = [str(v) for v in (meta.get("action_keys", []) or [])]
        for action_key in action_keys:
            rows.append(
                {
                    "unit": unit,
                    "timeframe": tf,
                    "target": target,
                    "action_key": action_key,
                    "candidate_id": f"{unit}::{action_key}",
                    "winner_wins": int(wins.get(action_key, 0)),
                }
            )
    return pl.DataFrame(rows)


def _fit_head(
    X: np.ndarray,
    y: np.ndarray,
    *,
    c_value: float,
    max_iter: int,
    seed: int,
) -> HeadModel:
    y = y.astype(np.int16, copy=False)
    uniq = np.unique(y)
    if uniq.size <= 1:
        constant = int(uniq[0]) if uniq.size == 1 else 0
        return HeadModel(pipeline=None, constant_class=constant, class_to_col={constant: 0})

    pipe = Pipeline(
        steps=[
            ("scaler", StandardScaler(with_mean=True, with_std=True)),
            (
                "clf",
                LogisticRegression(
                    solver="lbfgs",
                    max_iter=int(max_iter),
                    C=float(max(c_value, 1e-6)),
                    random_state=int(seed),
                    class_weight="balanced",
                ),
            ),
        ]
    )
    pipe.fit(X, y)
    classes = pipe.named_steps["clf"].classes_.astype(np.int16).tolist()
    return HeadModel(
        pipeline=pipe,
        constant_class=None,
        class_to_col={int(c): i for i, c in enumerate(classes)},
    )


def _predict_head(model: HeadModel, X: np.ndarray) -> tuple[np.ndarray, np.ndarray | None]:
    if model.pipeline is None:
        pred = np.full(X.shape[0], int(model.constant_class), dtype=np.int16)
        return pred, None
    pred = model.pipeline.predict(X).astype(np.int16, copy=False)
    proba = model.pipeline.predict_proba(X).astype(np.float64, copy=False)
    return pred, proba


def _safe_col(proba: np.ndarray | None, class_to_col: dict[int, int], cls: int, n: int) -> np.ndarray:
    if proba is None:
        return np.full(n, np.nan, dtype=np.float64)
    idx = class_to_col.get(int(cls))
    if idx is None:
        return np.full(n, 0.0, dtype=np.float64)
    return proba[:, int(idx)]


def _make_features_breakfree(data, idx: np.ndarray) -> np.ndarray:
    x = np.concatenate(
        [
            data.p_up[:, idx],
            data.p_down[:, idx],
            data.p_hold[:, idx],
        ],
        axis=1,
    ).astype(np.float32, copy=False)
    return np.nan_to_num(x, nan=1.0 / 3.0)


def _make_features_4dir(data, idx: np.ndarray) -> np.ndarray:
    x = np.concatenate([data.p_up[:, idx], data.p_down[:, idx]], axis=1).astype(np.float32, copy=False)
    return np.nan_to_num(x, nan=0.5)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="1m-only dual-head logistic meta-learner.")
    p.add_argument("--project-root", type=str, default=".")
    p.add_argument("--ensemble-run-dir", type=str, default="")
    p.add_argument("--output-dir", type=str, default=DEFAULT_OUTPUT_DIR)
    p.add_argument("--output-tag", type=str, default="one_minute_dualhead_meta")
    p.add_argument("--alignment-mode", type=str, default="same_period_close", choices=["same_period_close"])
    p.add_argument("--wf-warmup-batches", type=int, default=120)
    p.add_argument("--wf-recalibrate-every", type=int, default=10)
    p.add_argument("--max-train-batches", type=int, default=0)
    p.add_argument("--val-tail-ratio", type=float, default=0.20)
    p.add_argument("--meta-c-breakfree", type=float, default=0.5)
    p.add_argument("--meta-c-dir4", type=float, default=0.5)
    p.add_argument("--meta-max-iter", type=int, default=300)
    p.add_argument("--final-rule", type=str, default="strict_agreement_margin", choices=["strict_agreement_margin", "dual_ova_thresholds", "agreement_hold"])
    p.add_argument("--hold-band-grid", type=str, default="0.00:0.20:0.01")
    p.add_argument("--ova-threshold-grid", type=str, default="0.45:0.80:0.02")
    p.add_argument("--tau-objective", type=str, default="risk_aware", choices=["macro_f1", "risk_aware"])
    p.add_argument("--tau-fp-penalty", type=float, default=0.75)
    p.add_argument("--tau-opposite-fp-penalty", type=float, default=1.50)
    p.add_argument("--tau-hold-side-penalty", type=float, default=1.00)
    p.add_argument("--tau-opposite-active-penalty", type=float, default=0.0)
    p.add_argument("--tau-min-active-coverage", type=float, default=0.0)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--progress-every-batches", type=int, default=50)
    p.add_argument("--verbose", action="store_true")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    project_root = Path(args.project_root).expanduser().resolve()
    mod = _load_core_module(project_root)

    ensemble_run_dir = mod._resolve_ensemble_run_dir(project_root, str(args.ensemble_run_dir))
    unit_rows_path = ensemble_run_dir / "unit_prediction_rows_dedup.parquet"
    candidate_sets_path = ensemble_run_dir / "candidate_sets_by_unit.json"
    if not unit_rows_path.exists() or not candidate_sets_path.exists():
        raise FileNotFoundError("Missing required ensemble inputs")

    now = datetime.now(timezone.utc)
    out_name = now.strftime("%Y%m%d_%H%M%S") + (f"_{args.output_tag}" if args.output_tag else "")
    out_dir = (project_root / str(args.output_dir) / out_name).resolve()
    out_dir.mkdir(parents=True, exist_ok=False)

    if args.verbose:
        print("1m dual-head meta-learner")
        print(f"  ensemble_run_dir: {ensemble_run_dir}")
        print(f"  output_dir: {out_dir}")

    unit_rows_all = pl.read_parquet(unit_rows_path)
    candidate_sets = json.loads(candidate_sets_path.read_text(encoding="utf-8"))
    candidate_meta = _build_candidate_meta(candidate_sets, UNITS)
    candidate_set = set(candidate_meta["candidate_id"].to_list())

    unit_rows_pred = unit_rows_all.with_columns(
        pl.concat_str([pl.col("unit"), pl.lit("::"), pl.col("action_key")]).alias("candidate_id")
    ).filter(pl.col("candidate_id").is_in(list(candidate_set)))

    anchor_truth = mod._prepare_truth_table(unit_rows_all)
    mode_df = mod._build_anchor_candidate_probs(unit_rows_pred, str(args.alignment_mode))
    mode_df = mode_df.join(
        anchor_truth.select(["pred_batch", "anchor_15m_ts"]),
        on=["pred_batch", "anchor_15m_ts"],
        how="inner",
    ).with_columns(
        pl.concat_str([pl.col("unit"), pl.lit("::"), pl.col("action_key")]).alias("candidate_id")
    ).filter(pl.col("candidate_id").is_in(list(candidate_set)))

    data = mod._build_alignment_data(
        aligned_df=mode_df,
        candidate_meta=candidate_meta,
        anchor_truth=anchor_truth,
        mode=str(args.alignment_mode),
    )

    break_idx = np.where(data.candidate_targets == mod.TARGET_BREAKFREE)[0].astype(np.int32)
    dir4_idx = np.where(data.candidate_targets == mod.TARGET_4CLASS)[0].astype(np.int32)
    if break_idx.size == 0 or dir4_idx.size == 0:
        raise ValueError("Missing breakfree or 4class candidates")

    Xb_all = _make_features_breakfree(data, break_idx)
    Xd_all = _make_features_4dir(data, dir4_idx)
    yb_all = data.anchors["truth_breakfree"].to_numpy().astype(np.int16)
    y4_all = data.anchors["truth_4dir"].to_numpy().astype(np.int16)

    tau_grid = mod._parse_hold_band_grid(str(args.hold_band_grid))
    ova_grid = mod._parse_hold_band_grid(str(args.ova_threshold_grid))

    batch_order = data.batch_order
    warmup = int(args.wf_warmup_batches)
    if warmup >= len(batch_order):
        raise ValueError(f"wf_warmup_batches={warmup} must be < total_batches={len(batch_order)}")

    rows_final: list[dict[str, Any]] = []
    rows_target: list[dict[str, Any]] = []
    calib_rows: list[dict[str, Any]] = []
    model_b: HeadModel | None = None
    model_d: HeadModel | None = None
    tau = float(tau_grid[0])
    tau_up = float(ova_grid[0])
    tau_down = float(ova_grid[0])

    wf_t0 = time.perf_counter()
    pred_total = max(len(batch_order) - warmup, 1)
    max_train_batches = int(args.max_train_batches) if int(args.max_train_batches) > 0 else 0

    for i, batch in enumerate(batch_order):
        start, end = data.batch_ranges[int(batch)]
        if i < warmup:
            continue
        pred_idx = i - warmup + 1
        hist_end = start

        should_recal = (i == warmup) or ((i - warmup) % int(args.wf_recalibrate_every) == 0)
        if should_recal:
            hist_batches = batch_order[:i]
            if max_train_batches > 0 and len(hist_batches) > max_train_batches:
                hist_batches = hist_batches[-max_train_batches:]
            hist_start = data.batch_ranges[int(hist_batches[0])][0] if hist_batches else 0
            hist_idx = np.arange(hist_start, hist_end, dtype=np.int32)
            if hist_idx.size < 200:
                raise ValueError(f"Insufficient history for meta training at batch={batch}: {hist_idx.size}")

            val_n = max(64, int(hist_idx.size * float(args.val_tail_ratio)))
            val_n = min(max(32, val_n), max(hist_idx.size - 64, 32))
            split_at = hist_idx.size - val_n
            train_idx = hist_idx[:split_at]
            val_idx = hist_idx[split_at:]

            model_b = _fit_head(
                Xb_all[train_idx],
                yb_all[train_idx],
                c_value=float(args.meta_c_breakfree),
                max_iter=int(args.meta_max_iter),
                seed=int(args.seed),
            )
            model_d = _fit_head(
                Xd_all[train_idx],
                y4_all[train_idx],
                c_value=float(args.meta_c_dir4),
                max_iter=int(args.meta_max_iter),
                seed=int(args.seed),
            )

            pb_val, prob_b_val = _predict_head(model_b, Xb_all[val_idx])
            p4_val, prob_d_val = _predict_head(model_d, Xd_all[val_idx])
            up_b_val = _safe_col(prob_b_val, model_b.class_to_col, mod.UP, val_idx.size)
            dn_b_val = _safe_col(prob_b_val, model_b.class_to_col, mod.DOWN, val_idx.size)
            up_d_val = _safe_col(prob_d_val, model_d.class_to_col, mod.UP, val_idx.size)
            dn_d_val = _safe_col(prob_d_val, model_d.class_to_col, mod.DOWN, val_idx.size)
            score_b_val = up_b_val - dn_b_val
            score_d_val = up_d_val - dn_d_val

            truth_b_val = yb_all[val_idx]
            truth_4_val = y4_all[val_idx]

            if str(args.final_rule) == "dual_ova_thresholds":
                tau_up, tau_down = mod._select_dual_thresholds(
                    prob_up_break=up_b_val,
                    prob_down_break=dn_b_val,
                    prob_up_4=up_d_val,
                    prob_down_4=dn_d_val,
                    pred_break=pb_val,
                    pred_4=p4_val,
                    truth_breakfree=truth_b_val,
                    truth_4dir=truth_4_val,
                    ova_threshold_grid=ova_grid,
                    tau_objective=str(args.tau_objective),
                    tau_fp_penalty=float(args.tau_fp_penalty),
                    tau_opposite_fp_penalty=float(args.tau_opposite_fp_penalty),
                    tau_hold_side_penalty=float(args.tau_hold_side_penalty),
                    tau_opposite_active_penalty=float(args.tau_opposite_active_penalty),
                    tau_min_active_coverage=float(args.tau_min_active_coverage),
                )
                tau = 0.0
            elif str(args.final_rule) == "strict_agreement_margin":
                tau = mod._select_tau(
                    score_break=score_b_val,
                    score_4=score_d_val,
                    pred_break=pb_val,
                    pred_4=p4_val,
                    truth_breakfree=truth_b_val,
                    truth_4dir=truth_4_val,
                    tau_grid=tau_grid,
                    final_rule=str(args.final_rule),
                    tau_objective=str(args.tau_objective),
                    tau_fp_penalty=float(args.tau_fp_penalty),
                    tau_opposite_fp_penalty=float(args.tau_opposite_fp_penalty),
                    tau_hold_side_penalty=float(args.tau_hold_side_penalty),
                    tau_opposite_active_penalty=float(args.tau_opposite_active_penalty),
                    tau_min_active_coverage=float(args.tau_min_active_coverage),
                )
                tau_up = float(tau)
                tau_down = float(tau)
            else:
                tau = 0.0
                tau_up = 0.0
                tau_down = 0.0

            # Refit on full history after calibration.
            model_b = _fit_head(
                Xb_all[hist_idx],
                yb_all[hist_idx],
                c_value=float(args.meta_c_breakfree),
                max_iter=int(args.meta_max_iter),
                seed=int(args.seed),
            )
            model_d = _fit_head(
                Xd_all[hist_idx],
                y4_all[hist_idx],
                c_value=float(args.meta_c_dir4),
                max_iter=int(args.meta_max_iter),
                seed=int(args.seed),
            )

            calib_rows.append(
                {
                    "pred_batch": int(batch),
                    "history_rows": int(hist_idx.size),
                    "train_rows": int(train_idx.size),
                    "val_rows": int(val_idx.size),
                    "tau": float(tau),
                    "tau_up": float(tau_up),
                    "tau_down": float(tau_down),
                }
            )

        assert model_b is not None and model_d is not None
        pb, prob_b = _predict_head(model_b, Xb_all[start:end])
        p4, prob_d = _predict_head(model_d, Xd_all[start:end])
        n = end - start
        up_b = _safe_col(prob_b, model_b.class_to_col, mod.UP, n)
        dn_b = _safe_col(prob_b, model_b.class_to_col, mod.DOWN, n)
        up_d = _safe_col(prob_d, model_d.class_to_col, mod.UP, n)
        dn_d = _safe_col(prob_d, model_d.class_to_col, mod.DOWN, n)
        score_b = up_b - dn_b
        score_d = up_d - dn_d

        if str(args.final_rule) == "agreement_hold":
            final_pred = np.where(pb == p4, pb, mod.HOLD).astype(np.int16)
            score_final = np.where(pb == p4, np.maximum(np.abs(score_b), np.abs(score_d)), 0.0)
        else:
            final_pred, score_final = mod._compose_final(
                rule=str(args.final_rule),
                pred_breakfree=pb,
                pred_4dir=p4,
                score_breakfree=score_b,
                score_4dir=score_d,
                tau=float(tau),
                tau_up=float(tau_up),
                tau_down=float(tau_down),
                prob_up_break=up_b,
                prob_down_break=dn_b,
                prob_up_4=up_d,
                prob_down_4=dn_d,
            )

        truth_b = yb_all[start:end]
        truth_4 = y4_all[start:end]
        truth4 = mod._compose_truth4_labels(truth_b, truth_4)
        anchor_ts = data.anchors["anchor_15m_ts"].to_list()[start:end]

        for j in range(n):
            rows_target.append(
                {
                    "pred_batch": int(batch),
                    "anchor_15m_ts": anchor_ts[j],
                    "truth_breakfree": int(truth_b[j]),
                    "truth_4dir": int(truth_4[j]),
                    "pred_breakfree": int(pb[j]),
                    "pred_4dir": int(p4[j]),
                    "score_breakfree": float(score_b[j]) if np.isfinite(score_b[j]) else None,
                    "score_4dir": float(score_d[j]) if np.isfinite(score_d[j]) else None,
                }
            )
            rows_final.append(
                {
                    "alignment_mode": str(args.alignment_mode),
                    "weight_method": "dualhead_meta_logit",
                    "final_rule": str(args.final_rule),
                    "pred_batch": int(batch),
                    "anchor_15m_ts": anchor_ts[j],
                    "truth_final": int(truth_b[j]),
                    "truth_final4": int(truth4[j]),
                    "truth_breakfree": int(truth_b[j]),
                    "truth_4dir": int(truth_4[j]),
                    "pred_final": int(final_pred[j]),
                    "pred_breakfree": int(pb[j]),
                    "pred_4dir": int(p4[j]),
                    "score_final": float(score_final[j]) if np.isfinite(score_final[j]) else None,
                    "tau": float(tau),
                    "tau_up": float(tau_up),
                    "tau_down": float(tau_down),
                }
            )

        if args.verbose and (pred_idx == 1 or pred_idx == pred_total or pred_idx % int(args.progress_every_batches) == 0):
            elapsed = float(time.perf_counter() - wf_t0)
            eta = (elapsed / max(pred_idx, 1)) * max(pred_total - pred_idx, 0)
            print(
                f"[wf/meta] batch={int(batch)} pred_idx={pred_idx}/{pred_total} tau={float(tau):.4f} "
                f"tau_up={float(tau_up):.4f} tau_down={float(tau_down):.4f} elapsed={elapsed:.1f}s eta={eta:.1f}s",
                flush=True,
            )

    final_df = pl.DataFrame(rows_final)
    target_df = pl.DataFrame(rows_target)
    method_df, _, _, batch_df = mod._metrics_from_predictions(final_df, seed=int(args.seed))
    method_df = method_df.with_columns(
        pl.lit("dualhead_meta_logit").alias("weight_method"),
        pl.lit(str(args.final_rule)).alias("final_rule"),
    )

    yb = target_df["truth_breakfree"].to_numpy().astype(np.int16)
    pb = target_df["pred_breakfree"].to_numpy().astype(np.int16)
    y4 = target_df["truth_4dir"].to_numpy().astype(np.int16)
    p4 = target_df["pred_4dir"].to_numpy().astype(np.int16)
    b_std = mod._compute_standard_metrics(yb, pb)
    d_std = mod._compute_standard_metrics(y4, p4)

    method_csv = out_dir / "method_comparison_table.csv"
    batch_csv = out_dir / "evaluation_by_batch.csv"
    head_csv = out_dir / "target_head_method_comparison.csv"
    calib_csv = out_dir / "calibration_provenance.csv"
    method_df.write_csv(method_csv)
    batch_df.write_csv(batch_csv)
    pl.DataFrame(
        [
            {
                "target_head": "breakfree",
                "accuracy_covered": float(b_std["accuracy_covered"]),
                "macro_f1": float(b_std["macro_f1"]),
                "balanced_accuracy": float(b_std["balanced_accuracy"]),
                "directional_balanced_recall": float(b_std["directional_balanced_recall"]),
            },
            {
                "target_head": "dir4",
                "accuracy_covered": float(d_std["accuracy_covered"]),
                "macro_f1": float(d_std["macro_f1"]),
                "balanced_accuracy": float(d_std["balanced_accuracy"]),
                "directional_balanced_recall": float(d_std["directional_balanced_recall"]),
            },
        ]
    ).write_csv(head_csv)
    pl.DataFrame(calib_rows).write_csv(calib_csv)

    summary = {
        "created_utc": now.isoformat(),
        "ensemble_run_dir": str(ensemble_run_dir),
        "alignment_mode": str(args.alignment_mode),
        "final_rule": str(args.final_rule),
        "wf_warmup_batches": int(args.wf_warmup_batches),
        "wf_recalibrate_every": int(args.wf_recalibrate_every),
        "max_train_batches": int(args.max_train_batches),
        "meta_c_breakfree": float(args.meta_c_breakfree),
        "meta_c_dir4": float(args.meta_c_dir4),
        "meta_max_iter": int(args.meta_max_iter),
        "artifacts": {
            "method_comparison_table_csv": str(method_csv),
            "evaluation_by_batch_csv": str(batch_csv),
            "target_head_method_comparison_csv": str(head_csv),
            "calibration_provenance_csv": str(calib_csv),
        },
        "best": method_df.to_dicts()[0] if method_df.height else {},
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    if args.verbose and method_df.height:
        row = method_df.to_dicts()[0]
        print(
            "[meta-result] dir_acc={:.4f} coverage={:.4f} opp_active={:.4f} cost={:.4f}".format(
                float(row["directional_active_accuracy"]),
                float(row["directional_active_coverage"]),
                float(row["opposite_fp_rate_active"]),
                float(row["custom_mean_cost"]),
            )
        )
        print(f"Saved: {out_dir}")


if __name__ == "__main__":
    main()

