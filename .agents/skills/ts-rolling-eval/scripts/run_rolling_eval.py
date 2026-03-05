#!/usr/bin/env python3
"""Leak-safe rolling-origin baseline evaluation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import polars as pl


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run rolling-origin baseline evaluation")
    p.add_argument("--input", required=True)
    p.add_argument("--ts-col", required=True)
    p.add_argument("--y-col", required=True)
    p.add_argument("--horizon", type=int, default=14)
    p.add_argument("--min-train", type=int, default=200)
    p.add_argument("--step", type=int, default=7)
    p.add_argument("--season-len", type=int, default=0)
    p.add_argument("--outdir", default="output")
    return p.parse_args()


def mae(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.mean(np.abs(a - b)))


def rmse(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.sqrt(np.mean((a - b) ** 2)))


def main() -> None:
    a = parse_args()
    outdir = Path(a.outdir).resolve()
    outdir.mkdir(parents=True, exist_ok=True)

    p = Path(a.input)
    if p.suffix.lower() == ".parquet":
        df = pl.read_parquet(p)
    else:
        df = pl.read_csv(p)

    df = df.select([a.ts_col, a.y_col]).drop_nulls().sort(a.ts_col)
    y = df[a.y_col].to_numpy().astype(np.float64)

    folds = []
    rows = []
    for train_end in range(a.min_train, len(y) - a.horizon + 1, a.step):
        test_end = train_end + a.horizon
        y_train = y[:train_end]
        y_test = y[train_end:test_end]

        last = np.full_like(y_test, y_train[-1])
        slope = (y_train[-1] - y_train[0]) / max(len(y_train) - 1, 1)
        drift = np.array([y_train[-1] + slope * (i + 1) for i in range(len(y_test))], dtype=np.float64)

        fold = {
            "train_end": int(train_end),
            "test_end": int(test_end),
            "mae_last": mae(y_test, last),
            "rmse_last": rmse(y_test, last),
            "mae_drift": mae(y_test, drift),
            "rmse_drift": rmse(y_test, drift),
        }

        if a.season_len and train_end > a.season_len:
            seasonal = y[train_end - a.season_len:test_end - a.season_len]
            fold["mae_seasonal"] = mae(y_test, seasonal)
            fold["rmse_seasonal"] = rmse(y_test, seasonal)

        folds.append(fold)
        rows.append({"train_start": 0, "train_end": int(train_end), "test_start": int(train_end), "test_end": int(test_end)})

    if not folds:
        raise SystemExit("No folds generated. Adjust min-train/horizon/step.")

    metrics = {
        "n_folds": len(folds),
        "avg_mae_last": float(np.mean([f["mae_last"] for f in folds])),
        "avg_rmse_last": float(np.mean([f["rmse_last"] for f in folds])),
        "avg_mae_drift": float(np.mean([f["mae_drift"] for f in folds])),
        "avg_rmse_drift": float(np.mean([f["rmse_drift"] for f in folds])),
    }
    if "mae_seasonal" in folds[0]:
        metrics["avg_mae_seasonal"] = float(np.mean([f["mae_seasonal"] for f in folds]))
        metrics["avg_rmse_seasonal"] = float(np.mean([f["rmse_seasonal"] for f in folds]))

    (outdir / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")

    report = [
        "# Rolling Evaluation Report",
        "",
        f"Folds: {metrics['n_folds']}",
        f"avg_mae_last: {metrics['avg_mae_last']:.6f}",
        f"avg_rmse_last: {metrics['avg_rmse_last']:.6f}",
        f"avg_mae_drift: {metrics['avg_mae_drift']:.6f}",
        f"avg_rmse_drift: {metrics['avg_rmse_drift']:.6f}",
    ]
    if "avg_mae_seasonal" in metrics:
        report.append(f"avg_mae_seasonal: {metrics['avg_mae_seasonal']:.6f}")
        report.append(f"avg_rmse_seasonal: {metrics['avg_rmse_seasonal']:.6f}")

    (outdir / "report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    pl.DataFrame(rows).write_csv(outdir / "folds.csv")
    print(outdir)


if __name__ == "__main__":
    main()
