#!/usr/bin/env python3
"""Audit potential lookahead leakage in temporal datasets."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import polars as pl


SEVERITY = {"critical": 3, "high": 2, "medium": 1}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Audit lookahead leakage")
    p.add_argument("--input", required=True)
    p.add_argument("--ts-col", required=True)
    p.add_argument("--split-col", default="")
    p.add_argument("--feature-time-max-col", default="")
    p.add_argument("--future-patterns", default="lead,future,t+1,next")
    p.add_argument("--outdir", default=".")
    return p.parse_args()


def read_df(path: Path) -> pl.DataFrame:
    if path.suffix.lower() == ".parquet":
        return pl.read_parquet(path)
    return pl.read_csv(path)


def main() -> None:
    a = parse_args()
    p = Path(a.input).resolve()
    outdir = Path(a.outdir).resolve()
    outdir.mkdir(parents=True, exist_ok=True)

    df = read_df(p)
    issues = []

    if a.ts_col not in df.columns:
        raise SystemExit(f"missing ts column: {a.ts_col}")

    ts = pl.col(a.ts_col)

    if a.split_col:
        if a.split_col not in df.columns:
            raise SystemExit(f"missing split column: {a.split_col}")
        by_split = (
            df.group_by(a.split_col)
            .agg([ts.min().alias("min_ts"), ts.max().alias("max_ts")])
            .sort(a.split_col)
        )
        rows = by_split.to_dicts()
        for i in range(1, len(rows)):
            prev = rows[i - 1]
            cur = rows[i]
            if prev["max_ts"] >= cur["min_ts"]:
                issues.append(
                    {
                        "severity": "critical",
                        "type": "split_overlap",
                        "message": f"split overlap: {prev} vs {cur}",
                    }
                )

    patterns = [x.strip().lower() for x in a.future_patterns.split(",") if x.strip()]
    suspicious = []
    for c in df.columns:
        lc = c.lower()
        if any(pat in lc for pat in patterns):
            suspicious.append(c)
    for c in suspicious:
        issues.append(
            {
                "severity": "medium",
                "type": "suspicious_feature_name",
                "message": f"feature name contains future pattern: {c}",
            }
        )

    if a.feature_time_max_col:
        if a.feature_time_max_col not in df.columns:
            raise SystemExit(f"missing feature-time-max column: {a.feature_time_max_col}")
        bad = df.filter(pl.col(a.feature_time_max_col) > pl.col(a.ts_col))
        if bad.height > 0:
            issues.append(
                {
                    "severity": "high",
                    "type": "row_feature_time_violation",
                    "message": f"rows with feature_time_max > ts: {bad.height}",
                }
            )

    worst = "none"
    if issues:
        worst = sorted(issues, key=lambda d: SEVERITY.get(d["severity"], 0), reverse=True)[0]["severity"]

    payload = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "input": str(p),
        "n_rows": int(df.height),
        "n_cols": int(len(df.columns)),
        "issues": issues,
        "worst_severity": worst,
        "status": "pass" if not issues else "fail",
    }

    (outdir / "leakage_audit.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

    lines = ["# Leakage Findings", "", f"Status: {payload['status']}", f"Worst severity: {worst}", ""]
    if not issues:
        lines.append("No issues detected.")
    else:
        for i, issue in enumerate(issues, start=1):
            lines.append(f"{i}. [{issue['severity']}] {issue['type']}: {issue['message']}")

    (outdir / "leakage_findings.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(outdir)


if __name__ == "__main__":
    main()
