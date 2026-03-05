#!/usr/bin/env python3
"""Run sparse EWAF parameter sweep + causal gate optimization."""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Sparse EWAF sweep with gated post-optimization.")
    p.add_argument("--project-root", default="/media/przem/linux_data/RiskYieldMM (Copy)")
    p.add_argument("--ensemble-run-dir", required=True)
    p.add_argument("--candidate-search-run-dir", required=True)
    p.add_argument("--combos", default="1:2,2:2,3:2,2:4")
    p.add_argument("--wf-warmup-batches", type=int, default=120)
    p.add_argument("--wf-step-size", type=int, default=50)
    p.add_argument("--purge-batches", type=int, default=2)
    p.add_argument("--embargo-batches", type=int, default=2)
    p.add_argument("--allow-missing-aligned", action="store_true")
    p.add_argument("--verbose", action="store_true")
    p.add_argument("--output-dir", default="prediction_analysis/multitimeframe_cross_target_validation")
    p.add_argument("--output-tag", default="")
    return p.parse_args()


def _parse_combos(spec: str) -> list[tuple[int, float]]:
    out: list[tuple[int, float]] = []
    for tok in str(spec).split(","):
        t = tok.strip()
        if not t:
            continue
        k, eta = t.split(":", 1)
        out.append((int(k), float(eta)))
    if not out:
        raise ValueError("No combos parsed")
    return out


def _run(cmd: list[str], cwd: Path) -> None:
    p = subprocess.Popen(cmd, cwd=str(cwd), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    assert p.stdout is not None
    for line in p.stdout:
        sys.stdout.write(line)
        sys.stdout.flush()
    rc = p.wait()
    if rc != 0:
        raise RuntimeError(f"Command failed ({rc}): {' '.join(cmd)}")


def main() -> None:
    args = parse_args()
    root = Path(args.project_root).expanduser().resolve()
    py = str(root / "prediction_analysis" / ".." / "")  # unused placeholder
    python_bin = sys.executable

    combos = _parse_combos(args.combos)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    tag = str(args.output_tag).strip().replace(" ", "_")
    out_dir = root / str(args.output_dir) / (f"{stamp}_{tag}" if tag else f"{stamp}_ewaf_sparse_sweep")
    out_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, object]] = []

    for topk, eta in combos:
        combo_id = f"k{topk}_eta{str(eta).replace('.', 'p')}"
        print(f"\n=== COMBO {combo_id} ===")

        bench_tag = f"sweep_sparse_{combo_id}"
        bench_cmd = [
            python_bin,
            "-u",
            "prediction_analysis/multitimeframe_causal_ensemble_benchmark.py",
            "--ensemble-run-dir",
            str(args.ensemble_run_dir),
            "--candidate-search-run-dir",
            str(args.candidate_search_run_dir),
            "--wf-warmup-batches",
            str(args.wf_warmup_batches),
            "--wf-step-size",
            str(args.wf_step_size),
            "--purge-batches",
            str(args.purge_batches),
            "--embargo-batches",
            str(args.embargo_batches),
            "--methods",
            "online_sparse_ewaf_brier",
            "--ewaf-sparse-topk",
            str(topk),
            "--ewaf-eta",
            str(eta),
            "--output-tag",
            bench_tag,
        ]
        if args.allow_missing_aligned:
            bench_cmd.append("--allow-missing-aligned")
        if args.verbose:
            bench_cmd.append("--verbose")

        _run(bench_cmd, root)

        bench_root = root / "prediction_analysis" / "multitimeframe_causal_benchmark_outputs"
        bench_dirs = sorted([p for p in bench_root.glob(f"*_{bench_tag}") if p.is_dir()])
        if not bench_dirs:
            raise RuntimeError(f"Cannot find benchmark dir for {bench_tag}")
        bench_dir = bench_dirs[-1]

        gate_tag = f"sweep_gated_{combo_id}"
        gate_cmd = [
            python_bin,
            "-u",
            "prediction_analysis/ewaf_sparse_gated_optimizer.py",
            "--predictions-parquet",
            str(bench_dir / "final_predictions_walkforward.parquet"),
            "--method-name",
            "online_sparse_ewaf_brier",
            "--lookback-grid",
            "120,240,480,960,all",
            "--recalibrate-every-batches",
            "25",
            "--val-tail-ratio",
            "0.2",
            "--min-history-rows",
            "640",
            "--theta-up-grid",
            "0.30,0.35,0.40,0.45,0.50,0.55,0.60,0.65,0.70,0.75,0.80,0.85,0.90",
            "--theta-down-grid",
            "0.30,0.35,0.40,0.45,0.50,0.55,0.60,0.65,0.70,0.75,0.80,0.85,0.90",
            "--w-opp-active",
            "4",
            "--w-opp-covered",
            "2",
            "--w-safe",
            "1",
            "--w-cadence",
            "2",
            "--cadence-min-batches",
            "10",
            "--cadence-max-batches",
            "15",
            "--output-tag",
            gate_tag,
        ]
        if args.verbose:
            gate_cmd.append("--verbose")
        _run(gate_cmd, root)

        gate_root = root / "prediction_analysis" / "multitimeframe_cross_target_validation"
        gate_dirs = sorted([p for p in gate_root.glob(f"*_{gate_tag}") if p.is_dir()])
        if not gate_dirs:
            raise RuntimeError(f"Cannot find gate dir for {gate_tag}")
        gate_dir = gate_dirs[-1]

        bench_summary = json.load(open(bench_dir / "summary.json", "r", encoding="utf-8"))
        gate_summary = json.load(open(gate_dir / "summary.json", "r", encoding="utf-8"))

        base = bench_summary["best_method_risk_first"]
        gated = gate_summary["metrics"]

        rows.append(
            {
                "combo": combo_id,
                "topk": topk,
                "eta": eta,
                "base_opposite_fp_rate_active": base["opposite_fp_rate_active"],
                "base_opposite_fp_rate_covered": base["opposite_fp_rate_covered"],
                "base_directional_active_safe_accuracy": base["directional_active_safe_accuracy"],
                "base_directional_active_coverage": base["directional_active_coverage"],
                "gated_opposite_fp_rate_active": gated["opposite_fp_rate_active"],
                "gated_opposite_fp_rate_covered": gated["opposite_fp_rate_covered"],
                "gated_directional_active_safe_accuracy": gated["directional_active_safe_accuracy"],
                "gated_batches_per_signal": gated["batches_per_signal"],
                "gated_cadence_target_hit": gated["cadence_target_hit"],
                "benchmark_dir": str(bench_dir),
                "gate_dir": str(gate_dir),
            }
        )

    # rank: cadence hit first, then lower opp_active, lower opp_covered, higher safe
    rows_sorted = sorted(
        rows,
        key=lambda r: (
            0 if bool(r["gated_cadence_target_hit"]) else 1,
            float(r["gated_opposite_fp_rate_active"]),
            float(r["gated_opposite_fp_rate_covered"]),
            -float(r["gated_directional_active_safe_accuracy"]),
        ),
    )

    csv_path = out_dir / "sweep_results.csv"
    json_path = out_dir / "summary.json"

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows_sorted[0].keys()) if rows_sorted else [])
        w.writeheader()
        for r in rows_sorted:
            w.writerow(r)

    summary = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "combos": [{"topk": k, "eta": e} for k, e in combos],
        "rows": rows_sorted,
        "best": rows_sorted[0] if rows_sorted else None,
        "artifacts": {
            "sweep_results_csv": str(csv_path),
        },
    }
    json_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print("\n=== SWEEP DONE ===")
    print(json.dumps(summary["best"], indent=2))
    print(f"Results: {csv_path}")


if __name__ == "__main__":
    main()
