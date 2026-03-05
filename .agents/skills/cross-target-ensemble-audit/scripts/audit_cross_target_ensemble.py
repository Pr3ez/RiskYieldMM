#!/usr/bin/env python3
"""Audit cross-target ensemble alignment and confusion integrity."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import polars as pl

BATCH_EXPECTED = {"1m": 240, "5m": 48, "15m": 16}
ANCHOR_EXPECTED = {"1m": 15, "5m": 3, "15m": 1}


def read_df(path: Path) -> pl.DataFrame:
    if path.suffix.lower() == ".parquet":
        return pl.read_parquet(path)
    return pl.read_csv(path)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Audit cross-target ensemble artifacts")
    p.add_argument("--unit-rows", required=True)
    p.add_argument("--final-preds", default="")
    p.add_argument("--outdir", default=".")
    return p.parse_args()


def main() -> None:
    a = parse_args()
    outdir = Path(a.outdir).resolve()
    outdir.mkdir(parents=True, exist_ok=True)

    unit = read_df(Path(a.unit_rows).resolve())

    req = {"pred_batch", "timestamp", "timeframe", "action_key"}
    miss = sorted(req - set(unit.columns))
    if miss:
        raise SystemExit(f"missing required columns: {miss}")

    unit = unit.with_columns(
        pl.col("timestamp").cast(pl.Datetime("us"), strict=False).dt.truncate("15m").alias("anchor_15m_ts")
    )

    per_batch = (
        unit.group_by(["timeframe", "action_key", "pred_batch"])             .len()             .with_columns(pl.col("timeframe").replace_strict(BATCH_EXPECTED).alias("expected"))             .with_columns((pl.col("len") == pl.col("expected")).alias("ok"))
    )
    bad_batch = per_batch.filter(~pl.col("ok"))

    per_anchor = (
        unit.group_by(["timeframe", "action_key", "pred_batch", "anchor_15m_ts"])             .len()             .with_columns(pl.col("timeframe").replace_strict(ANCHOR_EXPECTED).alias("expected"))             .with_columns((pl.col("len") == pl.col("expected")).alias("ok"))
    )
    bad_anchor = per_anchor.filter(~pl.col("ok"))

    confusion_df = pl.DataFrame({"truth": [], "pred": [], "count": []})
    if a.final_preds:
        fp = read_df(Path(a.final_preds).resolve())
        if {"truth_final", "pred_final"}.issubset(fp.columns):
            confusion_df = (
                fp.group_by(["truth_final", "pred_final"]).len().rename({"len": "count"})
            )

    summary = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "unit_rows": int(unit.height),
        "bad_batch_rows": int(bad_batch.height),
        "bad_anchor_rows": int(bad_anchor.height),
        "status": "pass" if bad_batch.is_empty() and bad_anchor.is_empty() else "fail",
    }

    (outdir / "ensemble_audit.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    confusion_df.write_parquet(outdir / "confusions.parquet")
    print(outdir)


if __name__ == "__main__":
    main()
