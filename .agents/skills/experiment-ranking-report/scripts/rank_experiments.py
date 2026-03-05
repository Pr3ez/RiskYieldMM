#!/usr/bin/env python3
"""Rank experiment runs with deterministic tie-breakers."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import polars as pl


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Rank experiment runs")
    p.add_argument("--root", required=True)
    p.add_argument("--pattern", default="**/summary.json")
    p.add_argument("--outdir", default=".")
    return p.parse_args()


def main() -> None:
    a = parse_args()
    root = Path(a.root).resolve()
    outdir = Path(a.outdir).resolve()
    outdir.mkdir(parents=True, exist_ok=True)

    rows = []
    for path in sorted(root.glob(a.pattern)):
        try:
            obj = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        metrics = obj.get("best_metrics", {})
        if not metrics:
            metrics = obj.get("metrics", {})
        rows.append(
            {
                "run_path": str(path.parent),
                "summary_path": str(path),
                "macro_f1": float(metrics.get("macro_f1", 0.0) or 0.0),
                "custom_mean_cost": float(metrics.get("custom_mean_cost", metrics.get("mean_cost", 999.0)) or 999.0),
                "coverage": float(metrics.get("coverage", 0.0) or 0.0),
            }
        )

    if not rows:
        raise SystemExit("No valid summaries found.")

    df = pl.DataFrame(rows).sort(
        by=["macro_f1", "custom_mean_cost", "coverage", "run_path"],
        descending=[True, False, True, False],
    ).with_row_index("rank", offset=1)

    df.write_parquet(outdir / "ranking_table.parquet")
    df.write_csv(outdir / "ranking_table.csv")

    best = df.row(0, named=True)
    report = [
        "# Experiment Ranking Report",
        "",
        f"Best run: {best['run_path']}",
        f"macro_f1: {best['macro_f1']}",
        f"custom_mean_cost: {best['custom_mean_cost']}",
        f"coverage: {best['coverage']}",
        "",
        "Tie-break order:",
        "1. macro_f1 desc",
        "2. custom_mean_cost asc",
        "3. coverage desc",
        "4. run_path asc",
    ]
    (outdir / "selection_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print(outdir)


if __name__ == "__main__":
    main()
