#!/usr/bin/env python3
"""
1m/target_4class diversity-pruned history-only top-K ensemble test.

Workflow:
1) Load full stored rows from multitimeframe ensemble artifacts (3500 batches).
2) Build per-config directional accuracy by batch.
3) Prune near-duplicate configs using warmup-only correlation.
4) Evaluate history-only ensemble variants (lookback/K/weights/gate) and baselines.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl


DEFAULT_OUTPUT_DIR = "prediction_analysis/one_minute_target4class_diversity_outputs"


def _parse_grid_str_int(grid: str) -> list[int | str]:
    out: list[int | str] = []
    for raw in str(grid).split(","):
        s = raw.strip().lower()
        if not s:
            continue
        if s == "all":
            out.append("all")
        else:
            out.append(int(s))
    if not out:
        raise ValueError("Empty integer grid")
    return out


def _parse_grid_str_float(grid: str) -> list[float]:
    out: list[float] = []
    for raw in str(grid).split(","):
        s = raw.strip()
        if not s:
            continue
        out.append(float(s))
    if not out:
        raise ValueError("Empty float grid")
    return out


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Test diversity-pruned 1m/target_4class history-only top-K ensembles.")
    p.add_argument("--project-root", type=str, default=".")
    p.add_argument(
        "--ensemble-run-dir",
        type=str,
        default="prediction_analysis/multitimeframe_ensemble_outputs/20260225_173235_all6_3500_current_periodclose_nolive_ram",
    )
    p.add_argument("--unit", type=str, default="1m/target_4class")
    p.add_argument("--output-dir", type=str, default=DEFAULT_OUTPUT_DIR)
    p.add_argument("--output-tag", type=str, default="full3500_diversity_pruned")
    p.add_argument("--warmup-batches", type=int, default=500)
    p.add_argument("--duplicate-corr-threshold", type=float, default=0.995)
    p.add_argument("--lookback-grid", type=str, default="50,100,200,400,all")
    p.add_argument("--topk-grid", type=str, default="2,3,4,5")
    p.add_argument("--weight-methods", type=str, default="equal,history_softmax")
    p.add_argument("--gate-grid", type=str, default="0.00,0.05,0.10,0.15")
    p.add_argument("--softmax-temp", type=float, default=0.05)
    p.add_argument("--rank-min-coverage", type=float, default=0.10)
    p.add_argument("--linear-issue-url", type=str, default="")
    p.add_argument("--notion-page-url", type=str, default="")
    p.add_argument("--verbose", action="store_true")
    return p.parse_args()


def _load_candidate_keys(ensemble_run_dir: Path, unit: str) -> list[str]:
    p = ensemble_run_dir / "candidate_sets_by_unit.json"
    if not p.exists():
        raise FileNotFoundError(f"Missing candidate sets file: {p}")
    obj = json.loads(p.read_text(encoding="utf-8"))
    meta = obj.get(unit)
    if meta is None:
        raise KeyError(f"Unit not found: {unit}")
    keys = [str(v) for v in (meta.get("action_keys") or [])]
    if len(keys) != 12:
        raise ValueError(f"{unit} expected 12 configs, got {len(keys)}")
    return keys


def _load_prob_tensor(
    rows_path: Path,
    unit: str,
    action_keys: list[str],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    key_df = pl.DataFrame({"action_key": action_keys, "action_idx": np.arange(len(action_keys), dtype=np.int16)})
    df = (
        pl.scan_parquet(str(rows_path))
        .filter((pl.col("unit") == unit) & pl.col("action_key").is_in(action_keys))
        .select(
            [
                "pred_batch",
                "timestamp",
                "batch_id",
                "action_key",
                "y_true",
                "prob_class_0",
                "prob_class_1",
                "prob_class_2",
                "prob_class_3",
            ]
        )
        .collect()
        .join(key_df, on="action_key", how="inner")
        .sort(["pred_batch", "timestamp", "batch_id", "action_idx"])
    )
    if df.is_empty():
        raise ValueError("No rows after filtering")

    pred_batch = df["pred_batch"].to_numpy()
    y_true_col = df["y_true"].to_numpy()
    action_idx = df["action_idx"].to_numpy()
    p0 = df["prob_class_0"].to_numpy().astype(np.float32, copy=False)
    p1 = df["prob_class_1"].to_numpy().astype(np.float32, copy=False)
    p2 = df["prob_class_2"].to_numpy().astype(np.float32, copy=False)
    p3 = df["prob_class_3"].to_numpy().astype(np.float32, copy=False)

    c = len(action_keys)
    change = np.empty(pred_batch.shape[0], dtype=bool)
    change[0] = True
    change[1:] = pred_batch[1:] != pred_batch[:-1]
    starts = np.flatnonzero(change)
    ends = np.r_[starts[1:], pred_batch.shape[0]]
    batches = pred_batch[starts].astype(np.int64, copy=False)

    b = len(batches)
    rows_per_batch = 240
    probs = np.empty((b, rows_per_batch, c, 4), dtype=np.float32)
    y_true = np.empty((b, rows_per_batch), dtype=np.int16)

    for bi, (s, e) in enumerate(zip(starts, ends)):
        block_n = int(e - s)
        expected = rows_per_batch * c
        if block_n != expected:
            raise ValueError(
                f"Batch {int(batches[bi])} has {block_n} rows, expected {expected} "
                f"(240 rows x {c} configs)"
            )
        block_action = action_idx[s:e].reshape(rows_per_batch, c)
        if not np.all(block_action == np.arange(c, dtype=block_action.dtype)[None, :]):
            raise ValueError(f"Action index order mismatch in batch {int(batches[bi])}")

        yb = y_true_col[s:e].reshape(rows_per_batch, c)
        if not np.all(yb == yb[:, [0]]):
            raise ValueError(f"y_true mismatch across configs in batch {int(batches[bi])}")

        block_probs = np.column_stack((p0[s:e], p1[s:e], p2[s:e], p3[s:e])).reshape(rows_per_batch, c, 4)
        probs[bi] = block_probs
        y_true[bi] = yb[:, 0].astype(np.int16, copy=False)

    return batches, y_true, probs


def _compute_batch_cfg_directional_accuracy(y_true: np.ndarray, probs: np.ndarray) -> np.ndarray:
    true_dir = y_true >= 2
    pred_cls = np.argmax(probs, axis=3)
    pred_dir = pred_cls >= 2
    return np.mean(pred_dir == true_dir[:, :, None], axis=1).astype(np.float64, copy=False)


def _prune_duplicates(
    action_keys: list[str],
    batch_cfg_acc: np.ndarray,
    warmup_batches: int,
    corr_threshold: float,
) -> dict[str, Any]:
    c = len(action_keys)
    warm = batch_cfg_acc[:warmup_batches]
    corr = np.corrcoef(warm.T)
    corr = np.nan_to_num(corr, nan=0.0, posinf=0.0, neginf=0.0)

    parent = list(range(c))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra = find(a)
        rb = find(b)
        if ra != rb:
            parent[rb] = ra

    duplicate_pairs: list[dict[str, Any]] = []
    for i in range(c):
        for j in range(i + 1, c):
            if float(corr[i, j]) >= corr_threshold:
                union(i, j)
                duplicate_pairs.append(
                    {
                        "a": action_keys[i],
                        "b": action_keys[j],
                        "corr": float(corr[i, j]),
                    }
                )

    groups: dict[int, list[int]] = {}
    for i in range(c):
        groups.setdefault(find(i), []).append(i)

    warm_mean = np.mean(warm, axis=0)
    selected_idx: list[int] = []
    dropped: list[dict[str, Any]] = []
    group_rows: list[dict[str, Any]] = []
    for root, idxs in groups.items():
        idxs_sorted = sorted(
            idxs,
            key=lambda x: (
                float(warm_mean[x]),
                action_keys[x],
            ),
            reverse=True,
        )
        keep = idxs_sorted[0]
        selected_idx.append(keep)
        group_rows.append(
            {
                "group_id": int(root),
                "size": int(len(idxs_sorted)),
                "kept_action_key": action_keys[keep],
                "kept_warmup_directional_accuracy": float(warm_mean[keep]),
                "members": [action_keys[i] for i in idxs_sorted],
            }
        )
        for i in idxs_sorted[1:]:
            dropped.append(
                {
                    "dropped_action_key": action_keys[i],
                    "kept_action_key": action_keys[keep],
                    "dropped_warmup_directional_accuracy": float(warm_mean[i]),
                    "kept_warmup_directional_accuracy": float(warm_mean[keep]),
                }
            )

    selected_idx = sorted(selected_idx)
    return {
        "selected_idx": selected_idx,
        "selected_action_keys": [action_keys[i] for i in selected_idx],
        "group_rows": group_rows,
        "dropped_rows": dropped,
        "duplicate_pairs": duplicate_pairs,
        "corr_matrix": corr.tolist(),
    }


def _history_slice_start(bi: int, lookback: int | str) -> int:
    if lookback == "all":
        return 0
    return max(0, int(bi) - int(lookback))


def _weights_from_history(hist_acc: np.ndarray, method: str, temp: float) -> np.ndarray:
    if method == "equal":
        return np.full(hist_acc.shape[0], 1.0 / hist_acc.shape[0], dtype=np.float64)
    if method == "history_softmax":
        t = float(max(temp, 1e-6))
        z = (hist_acc - np.max(hist_acc)) / t
        ez = np.exp(z)
        s = float(np.sum(ez))
        if s <= 0:
            return np.full(hist_acc.shape[0], 1.0 / hist_acc.shape[0], dtype=np.float64)
        return ez / s
    raise ValueError(f"Unknown weight method: {method}")


def _evaluate_strategy(
    *,
    method_name: str,
    batches: np.ndarray,
    y_true: np.ndarray,
    probs: np.ndarray,
    batch_cfg_acc: np.ndarray,
    candidate_idx_pool: np.ndarray,
    warmup_batches: int,
    lookback: int | str,
    top_k: int,
    weight_method: str,
    gate: float,
    softmax_temp: float,
) -> dict[str, Any]:
    total_rows = 0
    active_rows = 0
    active_correct = 0
    active_opposite = 0
    batches_evaluated = 0

    for bi in range(warmup_batches, probs.shape[0]):
        hist_start = _history_slice_start(bi, lookback)
        hist = batch_cfg_acc[hist_start:bi, candidate_idx_pool]
        if hist.shape[0] == 0:
            continue
        hist_acc = np.mean(hist, axis=0)
        order = np.argsort(-hist_acc)
        k_eff = int(max(1, min(top_k, candidate_idx_pool.shape[0])))
        chosen = candidate_idx_pool[order[:k_eff]]
        chosen_acc = hist_acc[order[:k_eff]]
        weights = _weights_from_history(chosen_acc, weight_method, softmax_temp)

        p_sel = np.take(probs[bi], chosen, axis=1)
        p = np.tensordot(p_sel, weights, axes=(1, 0))
        p_up = p[:, 2] + p[:, 3]
        p_down = p[:, 0] + p[:, 1]
        margin = np.abs(p_up - p_down)
        if gate <= 0:
            active = np.ones(p.shape[0], dtype=bool)
        else:
            active = margin >= gate

        if np.any(active):
            pred_dir = p_up[active] >= p_down[active]
            true_dir = y_true[bi, active] >= 2
            correct = pred_dir == true_dir
            active_correct += int(np.sum(correct))
            active_opposite += int(np.sum(~correct))
            active_rows += int(np.sum(active))

        total_rows += int(p.shape[0])
        batches_evaluated += 1

    active_acc = (active_correct / active_rows) if active_rows > 0 else float("nan")
    opposite_rate = (active_opposite / active_rows) if active_rows > 0 else float("nan")
    coverage = (active_rows / total_rows) if total_rows > 0 else 0.0
    accuracy_over_total_rows = (active_correct / total_rows) if total_rows > 0 else 0.0
    return {
        "method": method_name,
        "lookback": str(lookback),
        "top_k": int(top_k),
        "weight_method": weight_method,
        "gate": float(gate),
        "batches_evaluated": int(batches_evaluated),
        "rows_total": int(total_rows),
        "rows_active": int(active_rows),
        "directional_active_coverage": float(coverage),
        "directional_active_accuracy": float(active_acc) if active_rows > 0 else None,
        "opposite_fp_rate_active": float(opposite_rate) if active_rows > 0 else None,
        "accuracy_over_total_rows": float(accuracy_over_total_rows),
    }


def _evaluate_uniform_baseline(
    *,
    batches: np.ndarray,
    y_true: np.ndarray,
    probs: np.ndarray,
    warmup_batches: int,
    gate: float,
) -> dict[str, Any]:
    total_rows = 0
    active_rows = 0
    active_correct = 0
    active_opposite = 0
    batches_evaluated = 0

    for bi in range(warmup_batches, probs.shape[0]):
        p = probs[bi].mean(axis=1)
        p_up = p[:, 2] + p[:, 3]
        p_down = p[:, 0] + p[:, 1]
        margin = np.abs(p_up - p_down)
        active = np.ones(p.shape[0], dtype=bool) if gate <= 0 else (margin >= gate)
        if np.any(active):
            pred_dir = p_up[active] >= p_down[active]
            true_dir = y_true[bi, active] >= 2
            correct = pred_dir == true_dir
            active_correct += int(np.sum(correct))
            active_opposite += int(np.sum(~correct))
            active_rows += int(np.sum(active))
        total_rows += int(p.shape[0])
        batches_evaluated += 1

    return {
        "method": "baseline_uniform12",
        "lookback": "na",
        "top_k": 12,
        "weight_method": "equal",
        "gate": float(gate),
        "batches_evaluated": int(batches_evaluated),
        "rows_total": int(total_rows),
        "rows_active": int(active_rows),
        "directional_active_coverage": float(active_rows / total_rows) if total_rows > 0 else 0.0,
        "directional_active_accuracy": float(active_correct / active_rows) if active_rows > 0 else None,
        "opposite_fp_rate_active": float(active_opposite / active_rows) if active_rows > 0 else None,
        "accuracy_over_total_rows": float(active_correct / total_rows) if total_rows > 0 else 0.0,
    }


def main() -> None:
    args = parse_args()
    project_root = Path(args.project_root).expanduser().resolve()
    ensemble_run_dir = (project_root / args.ensemble_run_dir).resolve()
    rows_path = ensemble_run_dir / "unit_prediction_rows_dedup.parquet"
    if not rows_path.exists():
        raise FileNotFoundError(f"Missing rows parquet: {rows_path}")

    now = datetime.now(timezone.utc)
    out_root = (project_root / args.output_dir).resolve()
    out_name = now.strftime("%Y%m%d_%H%M%S") + (f"_{args.output_tag}" if args.output_tag else "")
    out_dir = out_root / out_name
    out_dir.mkdir(parents=True, exist_ok=False)

    lookback_grid = _parse_grid_str_int(args.lookback_grid)
    topk_grid = [int(v) for v in _parse_grid_str_int(args.topk_grid)]
    gate_grid = _parse_grid_str_float(args.gate_grid)
    weight_methods = [s.strip() for s in str(args.weight_methods).split(",") if s.strip()]
    if not weight_methods:
        raise ValueError("No weight methods parsed")

    action_keys = _load_candidate_keys(ensemble_run_dir, args.unit)
    batches, y_true, probs = _load_prob_tensor(rows_path, args.unit, action_keys)
    b = probs.shape[0]
    if args.warmup_batches < 50 or args.warmup_batches >= b:
        raise ValueError(f"warmup_batches must be in [50, {b-1}]")

    batch_cfg_acc = _compute_batch_cfg_directional_accuracy(y_true, probs)
    prune = _prune_duplicates(
        action_keys=action_keys,
        batch_cfg_acc=batch_cfg_acc,
        warmup_batches=int(args.warmup_batches),
        corr_threshold=float(args.duplicate_corr_threshold),
    )
    selected_idx = np.asarray(prune["selected_idx"], dtype=np.int64)

    if args.verbose:
        print("1m/target_4class diversity-pruned test")
        print(f"  ensemble_run_dir: {ensemble_run_dir}")
        print(f"  output_dir: {out_dir}")
        print(f"  batches: {b} | configs: {len(action_keys)}")
        print(f"  warmup_batches: {args.warmup_batches}")
        print(f"  duplicate_corr_threshold: {args.duplicate_corr_threshold}")
        print(f"  selected_after_prune: {len(selected_idx)} -> {[action_keys[i] for i in selected_idx]}")

    rows: list[dict[str, Any]] = []
    for gate in gate_grid:
        rows.append(
            _evaluate_uniform_baseline(
                batches=batches,
                y_true=y_true,
                probs=probs,
                warmup_batches=int(args.warmup_batches),
                gate=float(gate),
            )
        )

    for lookback in lookback_grid:
        for k in topk_grid:
            for wm in weight_methods:
                for gate in gate_grid:
                    rows.append(
                        _evaluate_strategy(
                            method_name="diversity_pruned_topk",
                            batches=batches,
                            y_true=y_true,
                            probs=probs,
                            batch_cfg_acc=batch_cfg_acc,
                            candidate_idx_pool=selected_idx,
                            warmup_batches=int(args.warmup_batches),
                            lookback=lookback,
                            top_k=int(k),
                            weight_method=wm,
                            gate=float(gate),
                            softmax_temp=float(args.softmax_temp),
                        )
                    )

    res = pl.DataFrame(rows)
    rank_min_cov = float(args.rank_min_coverage)
    eligible = res.filter(pl.col("directional_active_coverage") >= rank_min_cov)
    if eligible.is_empty():
        eligible = res

    eligible_sorted = eligible.sort(
        by=[
            "opposite_fp_rate_active",
            "directional_active_accuracy",
            "directional_active_coverage",
            "accuracy_over_total_rows",
        ],
        descending=[False, True, True, True],
        nulls_last=True,
    )
    best = eligible_sorted.head(1)
    best_row = best.to_dicts()[0] if len(best) > 0 else {}

    pruning_summary = {
        "original_config_count": int(len(action_keys)),
        "selected_config_count": int(len(selected_idx)),
        "selected_action_keys": [action_keys[i] for i in selected_idx.tolist()],
        "duplicate_corr_threshold": float(args.duplicate_corr_threshold),
        "duplicate_pairs": prune["duplicate_pairs"],
        "groups": prune["group_rows"],
        "dropped": prune["dropped_rows"],
    }

    summary = {
        "unit": args.unit,
        "ensemble_run_dir": str(ensemble_run_dir),
        "batches": int(b),
        "rows_per_batch": int(probs.shape[1]),
        "warmup_batches": int(args.warmup_batches),
        "lookback_grid": [str(v) for v in lookback_grid],
        "topk_grid": [int(v) for v in topk_grid],
        "weight_methods": weight_methods,
        "gate_grid": [float(v) for v in gate_grid],
        "rank_min_coverage": rank_min_cov,
        "best_setup": best_row,
    }

    out_results_parquet = out_dir / "method_results.parquet"
    out_results_csv = out_dir / "method_results.csv"
    out_best_csv = out_dir / "best_setup.csv"
    out_prune_json = out_dir / "pruning_summary.json"
    out_summary_json = out_dir / "summary.json"
    out_tracking_json = out_dir / "tracking_context.json"

    res.write_parquet(out_results_parquet)
    res.write_csv(out_results_csv)
    best.write_csv(out_best_csv)
    out_prune_json.write_text(json.dumps(pruning_summary, indent=2), encoding="utf-8")
    out_summary_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    out_tracking_json.write_text(
        json.dumps(
            {
                "linear_issue_url": args.linear_issue_url,
                "notion_page_url": args.notion_page_url,
                "run_command": " ".join([os.path.basename(sys.executable), *sys.argv]),
                "cwd": str(Path.cwd().resolve()),
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    print("Diversity-pruned test complete")
    print(f"  output_dir: {out_dir}")
    print(f"  results: {out_results_csv}")
    print(f"  summary: {out_summary_json}")
    if best_row:
        print(
            "  best:"
            f" method={best_row.get('method')}"
            f" lookback={best_row.get('lookback')}"
            f" top_k={best_row.get('top_k')}"
            f" weight={best_row.get('weight_method')}"
            f" gate={best_row.get('gate')}"
            f" active_acc={best_row.get('directional_active_accuracy')}"
            f" coverage={best_row.get('directional_active_coverage')}"
            f" opposite={best_row.get('opposite_fp_rate_active')}"
        )


if __name__ == "__main__":
    main()
