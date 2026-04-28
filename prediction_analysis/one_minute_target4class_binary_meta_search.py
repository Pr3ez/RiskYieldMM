#!/usr/bin/env python3
"""
1m/target_4class binary direction meta-learner with causal walk-forward lookback search.

Label mapping:
- y_bin = 1 (UP)   for target_4class classes {2, 3}
- y_bin = 0 (DOWN) for target_4class classes {0, 1}

Features per candidate config (per row):
- up_prob    = p(class_2) + p(class_3)
- down_prob  = p(class_0) + p(class_1)
- margin     = up_prob - down_prob

Walk-forward protocol:
- train using history batches strictly < current pred_batch
- evaluate on current pred_batch only
- repeat for each lookback in lookback-grid and rank globally
"""

from __future__ import annotations

import argparse
import json
import math
import os
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


DEFAULT_OUTPUT_DIR = "prediction_analysis/one_minute_target4class_binary_meta_outputs"
DEFAULT_RUN_ID = "stage1_catboost_live"
DEFAULT_MODEL_NAME = "catboost"
DEFAULT_UNIT = "1m/target_4class"


@dataclass
class FitModel:
    pipe: Pipeline | None
    constant: int | None


def _parse_lookback_grid(raw: str) -> list[int]:
    out: list[int] = []
    for token in str(raw).split(","):
        s = token.strip().lower()
        if not s:
            continue
        if s == "all":
            out.append(-1)
        else:
            v = int(s)
            if v <= 0:
                raise ValueError(f"lookback must be > 0 or 'all', got {v}")
            out.append(v)
    if not out:
        raise ValueError("lookback-grid is empty")
    # stable unique
    uniq: list[int] = []
    seen: set[int] = set()
    for v in out:
        if v not in seen:
            seen.add(v)
            uniq.append(v)
    return uniq


def _lookback_label(v: int) -> str:
    return "all" if int(v) < 0 else str(int(v))


def _fit_model(
    X: np.ndarray,
    y: np.ndarray,
    *,
    c_value: float,
    max_iter: int,
    seed: int,
) -> FitModel:
    y = y.astype(np.int8, copy=False)
    uniq = np.unique(y)
    if uniq.size <= 1:
        const = int(uniq[0]) if uniq.size == 1 else 0
        return FitModel(pipe=None, constant=const)

    pipe = Pipeline(
        steps=[
            ("scaler", StandardScaler(with_mean=True, with_std=True)),
            (
                "clf",
                LogisticRegression(
                    solver="lbfgs",
                    max_iter=int(max_iter),
                    C=float(max(c_value, 1e-6)),
                    class_weight="balanced",
                    random_state=int(seed),
                ),
            ),
        ]
    )
    pipe.fit(X, y)
    return FitModel(pipe=pipe, constant=None)


def _predict_model(model: FitModel, X: np.ndarray) -> tuple[np.ndarray, np.ndarray | None]:
    if model.pipe is None:
        pred = np.full(X.shape[0], int(model.constant), dtype=np.int8)
        return pred, None
    pred = model.pipe.predict(X).astype(np.int8, copy=False)
    proba = model.pipe.predict_proba(X).astype(np.float64, copy=False)
    return pred, proba


def _safe_div(num: float, den: float) -> float:
    if den <= 0.0:
        return 0.0
    return float(num / den)


def _binary_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float]:
    y_true = y_true.astype(np.int8, copy=False)
    y_pred = y_pred.astype(np.int8, copy=False)

    tp_up = float(np.sum((y_true == 1) & (y_pred == 1)))
    fp_up = float(np.sum((y_true == 0) & (y_pred == 1)))
    fn_up = float(np.sum((y_true == 1) & (y_pred == 0)))
    tn = float(np.sum((y_true == 0) & (y_pred == 0)))

    tp_down = tn
    fp_down = fn_up
    fn_down = fp_up

    n = float(y_true.size)
    acc = _safe_div(tp_up + tn, n)
    prec_up = _safe_div(tp_up, tp_up + fp_up)
    prec_down = _safe_div(tp_down, tp_down + fp_down)
    rec_up = _safe_div(tp_up, tp_up + fn_up)
    rec_down = _safe_div(tp_down, tp_down + fn_down)
    bal_acc = 0.5 * (rec_up + rec_down)

    return {
        "rows": int(y_true.size),
        "directional_accuracy": float(acc),
        "directional_active_safe_accuracy": float(acc),
        "balanced_accuracy": float(bal_acc),
        "precision_up": float(prec_up),
        "precision_down": float(prec_down),
        "recall_up": float(rec_up),
        "recall_down": float(rec_down),
        "opposite_fp_rate_active": float(1.0 - acc),
        "opposite_fp_rate_covered": float(1.0 - acc),
    }


def _load_stage1_feature_tensor(
    *,
    project_root: Path,
    run_id: str,
    model_name: str,
    unit: str,
    verbose: bool,
    progress_every_batches: int,
) -> tuple[np.ndarray, np.ndarray, list[int], list[str], list[int]]:
    tf, target = unit.split("/", 1)
    unit_dir = (
        project_root / "data" / "htf_backtest_results" / run_id / model_name / tf / target
    )
    if not unit_dir.exists():
        raise FileNotFoundError(f"Unit directory not found: {unit_dir}")

    batch_ids = sorted(
        int(p.name.split("_")[1])
        for p in unit_dir.glob("batch_*")
        if p.is_dir() and p.name.split("_")[1].isdigit()
    )
    if not batch_ids:
        raise ValueError(f"No batch_* directories found under: {unit_dir}")

    action_keys: list[str] | None = None
    action_to_idx: dict[str, int] | None = None
    row_slots: list[int] | None = None
    X_all: np.ndarray | None = None
    y_all: np.ndarray | None = None

    b_total = len(batch_ids)
    t0 = time.perf_counter()

    for bi, batch in enumerate(batch_ids):
        p = unit_dir / f"batch_{batch:04d}" / "stage1" / "stage1_pred_batch_predictions.parquet"
        if not p.exists():
            raise FileNotFoundError(f"Missing pred file: {p}")
        df = (
            pl.read_parquet(p)
            .filter(pl.col("scope") == "pred_batch")
            .select(
                [
                    "timestamp",
                    "action_key",
                    "y_true",
                    "prob_class_0",
                    "prob_class_1",
                    "prob_class_2",
                    "prob_class_3",
                ]
            )
            .sort(["timestamp", "action_key"])
        )
        if df.is_empty():
            raise ValueError(f"Empty pred_batch scope in {p}")

        if action_keys is None:
            action_keys = sorted(df["action_key"].drop_nulls().unique().to_list())
            if not action_keys:
                raise ValueError(f"No action keys in {p}")
            action_to_idx = {str(k): i for i, k in enumerate(action_keys)}

            # Rows are identified by sorted unique timestamps within each batch.
            unique_ts = df["timestamp"].drop_nulls().unique().sort()
            row_count = int(unique_ts.len())
            if row_count <= 0:
                raise ValueError(f"No timestamp rows in {p}")
            row_slots = list(range(row_count))

            c = len(action_keys)
            r = int(row_count)
            X_all = np.empty((b_total, r, c * 3), dtype=np.float32)
            y_all = np.empty((b_total, r), dtype=np.int8)
        else:
            assert action_to_idx is not None
            assert row_slots is not None
            keys_here = sorted(df["action_key"].drop_nulls().unique().to_list())
            if keys_here != action_keys:
                miss = sorted(set(action_keys) - set(keys_here))
                extra = sorted(set(keys_here) - set(action_keys))
                raise ValueError(
                    f"Action key mismatch in batch {batch}: missing={miss[:8]} extra={extra[:8]}"
                )
            row_count_here = int(df["timestamp"].drop_nulls().unique().len())
            if row_count_here != len(row_slots):
                raise ValueError(
                    f"Row-count mismatch in batch {batch}: expected {len(row_slots)} rows, got {row_count_here}"
                )

        assert action_to_idx is not None
        assert row_slots is not None
        assert X_all is not None and y_all is not None
        c = len(action_to_idx)
        r = len(row_slots)

        expected_rows = r * c
        if df.height != expected_rows:
            raise ValueError(
                f"Batch {batch} row count mismatch: got {df.height}, expected {expected_rows} ({r}x{c})"
            )

        act = [str(v) for v in df["action_key"].to_list()]
        action_idx = np.fromiter((action_to_idx[a] for a in act), dtype=np.int16, count=df.height)
        action_idx_m = action_idx.reshape(r, c)
        expected_order = np.arange(c, dtype=np.int16)[None, :]
        if not np.all(action_idx_m == expected_order):
            raise ValueError(f"Action order mismatch after timestamp sort in batch {batch}")

        p0 = df["prob_class_0"].to_numpy().astype(np.float32, copy=False)
        p1 = df["prob_class_1"].to_numpy().astype(np.float32, copy=False)
        p2 = df["prob_class_2"].to_numpy().astype(np.float32, copy=False)
        p3 = df["prob_class_3"].to_numpy().astype(np.float32, copy=False)
        y_true = df["y_true"].to_numpy().astype(np.int16, copy=False)

        up_m = (p2 + p3).reshape(r, c)
        dn_m = (p0 + p1).reshape(r, c)
        mg_m = (up_m - dn_m).reshape(r, c)

        y_m = y_true.reshape(r, c)
        y0 = y_m[:, 0]
        if not np.all(y_m == y0[:, None]):
            raise ValueError(f"y_true mismatch across configs in batch {batch}")

        y_bin = (y0 >= 2).astype(np.int8, copy=False)
        X_batch = np.concatenate([up_m, dn_m, mg_m], axis=1)

        X_all[bi] = X_batch
        y_all[bi] = y_bin

        if verbose and ((bi + 1) == 1 or (bi + 1) == b_total or ((bi + 1) % max(1, int(progress_every_batches)) == 0)):
            elapsed = float(time.perf_counter() - t0)
            eta = (elapsed / max(bi + 1, 1)) * max(b_total - (bi + 1), 0)
            print(
                f"[load] batch={batch} idx={bi+1}/{b_total} elapsed={elapsed:.1f}s eta={eta:.1f}s",
                flush=True,
            )

    assert action_keys is not None and row_slots is not None and X_all is not None and y_all is not None
    return X_all, y_all, batch_ids, action_keys, row_slots


def _evaluate_lookback(
    *,
    X_all: np.ndarray,
    y_all: np.ndarray,
    batch_ids: list[int],
    lookback_batches: int,
    wf_warmup_batches: int,
    wf_retrain_every: int,
    c_value: float,
    max_iter: int,
    seed: int,
    verbose: bool,
    progress_every: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    b_total, rows_per_batch, feat_n = X_all.shape
    if wf_warmup_batches >= b_total:
        raise ValueError(f"wf-warmup-batches={wf_warmup_batches} must be < total_batches={b_total}")

    pred_total = b_total - wf_warmup_batches
    model: FitModel | None = None

    all_true: list[np.ndarray] = []
    all_pred: list[np.ndarray] = []
    batch_rows: list[dict[str, Any]] = []
    effective_lb_list: list[int] = []

    wf_t0 = time.perf_counter()

    for i in range(wf_warmup_batches, b_total):
        pred_idx = i - wf_warmup_batches + 1

        if lookback_batches < 0:
            hist_start_batch = 0
        else:
            hist_start_batch = max(0, i - int(lookback_batches))

        hist_batch_count = int(i - hist_start_batch)
        effective_lb_list.append(hist_batch_count)

        should_refit = (model is None) or (((i - wf_warmup_batches) % max(1, int(wf_retrain_every))) == 0)
        if should_refit:
            X_hist = X_all[hist_start_batch:i].reshape(hist_batch_count * rows_per_batch, feat_n)
            y_hist = y_all[hist_start_batch:i].reshape(hist_batch_count * rows_per_batch)
            if y_hist.size < 64:
                raise ValueError(f"Insufficient history rows at batch idx={i}: {y_hist.size}")
            model = _fit_model(
                X_hist,
                y_hist,
                c_value=float(c_value),
                max_iter=int(max_iter),
                seed=int(seed),
            )

        assert model is not None
        X_pred = X_all[i]
        y_true = y_all[i]
        y_pred, _ = _predict_model(model, X_pred)

        met = _binary_metrics(y_true, y_pred)
        batch_rows.append(
            {
                "lookback_requested_batches": int(lookback_batches),
                "lookback_requested_label": _lookback_label(int(lookback_batches)),
                "lookback_effective_batches": int(hist_batch_count),
                "pred_batch": int(batch_ids[i]),
                "pred_idx": int(pred_idx),
                **met,
            }
        )

        all_true.append(y_true)
        all_pred.append(y_pred)

        if verbose and (pred_idx == 1 or pred_idx == pred_total or (pred_idx % max(1, int(progress_every)) == 0)):
            elapsed = float(time.perf_counter() - wf_t0)
            eta = (elapsed / max(pred_idx, 1)) * max(pred_total - pred_idx, 0)
            print(
                f"[wf/lb={_lookback_label(int(lookback_batches))}] batch={batch_ids[i]} "
                f"{pred_idx}/{pred_total} eff_lb={hist_batch_count} elapsed={elapsed:.1f}s eta={eta:.1f}s",
                flush=True,
            )

    y_true_all = np.concatenate(all_true)
    y_pred_all = np.concatenate(all_pred)
    overall = _binary_metrics(y_true_all, y_pred_all)

    method_row = {
        "lookback_requested_batches": int(lookback_batches),
        "lookback_requested_label": _lookback_label(int(lookback_batches)),
        "lookback_effective_batches_mean": float(np.mean(effective_lb_list)) if effective_lb_list else 0.0,
        "lookback_effective_batches_min": int(np.min(effective_lb_list)) if effective_lb_list else 0,
        "lookback_effective_batches_max": int(np.max(effective_lb_list)) if effective_lb_list else 0,
        "wf_warmup_batches": int(wf_warmup_batches),
        "wf_retrain_every": int(wf_retrain_every),
        "rows_evaluated": int(y_true_all.size),
        **overall,
    }
    return method_row, batch_rows


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="1m/target_4class binary meta-learner lookback search.")
    p.add_argument("--project-root", type=str, default=".")
    p.add_argument("--run-id", type=str, default=DEFAULT_RUN_ID)
    p.add_argument("--model-name", type=str, default=DEFAULT_MODEL_NAME)
    p.add_argument("--unit", type=str, default=DEFAULT_UNIT)
    p.add_argument("--output-dir", type=str, default=DEFAULT_OUTPUT_DIR)
    p.add_argument("--output-tag", type=str, default="binary_meta_lookback_search")
    p.add_argument("--lookback-grid", type=str, default="120,180,240,300,500,1000,all")
    p.add_argument("--wf-warmup-batches", type=int, default=500)
    p.add_argument("--wf-retrain-every", type=int, default=10)
    p.add_argument("--meta-c", type=float, default=0.5)
    p.add_argument("--meta-max-iter", type=int, default=300)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--progress-every-batches", type=int, default=50)
    p.add_argument("--linear-issue-url", type=str, default="")
    p.add_argument("--notion-page-url", type=str, default="")
    p.add_argument("--verbose", action="store_true")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    project_root = Path(args.project_root).expanduser().resolve()
    lookbacks = _parse_lookback_grid(str(args.lookback_grid))

    now = datetime.now(timezone.utc)
    out_name = now.strftime("%Y%m%d_%H%M%S") + (f"_{args.output_tag}" if args.output_tag else "")
    out_dir = (project_root / str(args.output_dir) / out_name).resolve()
    out_dir.mkdir(parents=True, exist_ok=False)

    if args.verbose:
        print("1m target_4class binary meta lookback search")
        print(f"  unit: {args.unit}")
        print(f"  run: {args.run_id}/{args.model_name}")
        print(f"  lookbacks: {[ _lookback_label(v) for v in lookbacks ]}")
        print(f"  output_dir: {out_dir}")

    X_all, y_all, batch_ids, action_keys, row_slots = _load_stage1_feature_tensor(
        project_root=project_root,
        run_id=str(args.run_id),
        model_name=str(args.model_name),
        unit=str(args.unit),
        verbose=bool(args.verbose),
        progress_every_batches=max(1, int(args.progress_every_batches)),
    )

    method_rows: list[dict[str, Any]] = []
    batch_rows_all: list[dict[str, Any]] = []

    for lb in lookbacks:
        row, batch_rows = _evaluate_lookback(
            X_all=X_all,
            y_all=y_all,
            batch_ids=batch_ids,
            lookback_batches=int(lb),
            wf_warmup_batches=int(args.wf_warmup_batches),
            wf_retrain_every=int(args.wf_retrain_every),
            c_value=float(args.meta_c),
            max_iter=int(args.meta_max_iter),
            seed=int(args.seed),
            verbose=bool(args.verbose),
            progress_every=max(1, int(args.progress_every_batches)),
        )
        method_rows.append(row)
        batch_rows_all.extend(batch_rows)

    method_df = pl.DataFrame(method_rows)
    method_df = (
        method_df.sort(
            [
                "opposite_fp_rate_active",
                "directional_accuracy",
                "balanced_accuracy",
                "precision_up",
                "precision_down",
                "lookback_effective_batches_mean",
            ],
            descending=[False, True, True, True, True, True],
        )
        .with_row_index("rank", offset=1)
    )

    batch_df = pl.DataFrame(batch_rows_all).sort(["lookback_requested_batches", "pred_batch"])

    method_parquet = out_dir / "method_comparison_table.parquet"
    method_csv = out_dir / "method_comparison_table.csv"
    batch_parquet = out_dir / "evaluation_by_batch.parquet"
    batch_csv = out_dir / "evaluation_by_batch.csv"
    tracking_json = out_dir / "tracking_context.json"
    summary_json = out_dir / "summary.json"
    feature_meta_json = out_dir / "feature_manifest.json"

    method_df.write_parquet(method_parquet)
    method_df.write_csv(method_csv)
    batch_df.write_parquet(batch_parquet)
    batch_df.write_csv(batch_csv)

    best = method_df.to_dicts()[0] if method_df.height else {}

    summary = {
        "created_utc": now.isoformat(),
        "unit": str(args.unit),
        "run_id": str(args.run_id),
        "model_name": str(args.model_name),
        "lookback_grid": ["all" if int(v) < 0 else int(v) for v in lookbacks],
        "wf_warmup_batches": int(args.wf_warmup_batches),
        "wf_retrain_every": int(args.wf_retrain_every),
        "meta_c": float(args.meta_c),
        "meta_max_iter": int(args.meta_max_iter),
        "seed": int(args.seed),
        "dataset": {
            "batches_total": int(X_all.shape[0]),
            "rows_per_batch": int(X_all.shape[1]),
            "features_per_row": int(X_all.shape[2]),
            "configs_total": int(len(action_keys)),
        },
        "best": best,
        "artifacts": {
            "method_comparison_table_parquet": str(method_parquet),
            "method_comparison_table_csv": str(method_csv),
            "evaluation_by_batch_parquet": str(batch_parquet),
            "evaluation_by_batch_csv": str(batch_csv),
            "feature_manifest_json": str(feature_meta_json),
            "tracking_context_json": str(tracking_json),
        },
    }
    summary_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    feature_meta_json.write_text(
        json.dumps(
            {
                "action_keys": action_keys,
                "row_slots": row_slots,
                "feature_layout": {
                    "up_prob_cols": [f"up::{k}" for k in action_keys],
                    "down_prob_cols": [f"down::{k}" for k in action_keys],
                    "margin_cols": [f"margin::{k}" for k in action_keys],
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    tracking_context = {
        "created_utc": now.isoformat(),
        "run_command": " ".join(["python", *sys.argv]),
        "linear_issue_url": str(args.linear_issue_url or ""),
        "notion_page_url": str(args.notion_page_url or ""),
        "output_dir": str(out_dir),
    }
    tracking_json.write_text(json.dumps(tracking_context, indent=2), encoding="utf-8")

    if args.verbose and best:
        print(
            "[best] lookback={} dir_acc={:.4f} opp_fp_active={:.4f} bal_acc={:.4f} "
            "prec_up={:.4f} prec_down={:.4f}".format(
                best.get("lookback_requested_label"),
                float(best.get("directional_accuracy", 0.0)),
                float(best.get("opposite_fp_rate_active", 1.0)),
                float(best.get("balanced_accuracy", 0.0)),
                float(best.get("precision_up", 0.0)),
                float(best.get("precision_down", 0.0)),
            )
        )
        print(f"Saved: {out_dir}")


if __name__ == "__main__":
    main()
