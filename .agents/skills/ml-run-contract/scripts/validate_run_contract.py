#!/usr/bin/env python3
"""Validate run artifact contract and emit deterministic reports."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_REQUIRED = [
    "summary.json",
    "method_comparison_table.parquet",
    "evaluation_by_batch.parquet",
]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Validate ML run contract")
    p.add_argument("--run-dir", required=True)
    p.add_argument("--required", nargs="*", default=DEFAULT_REQUIRED)
    p.add_argument("--manifest", default="run_manifest.json")
    p.add_argument("--outdir", default=".")
    return p.parse_args()


def main() -> None:
    a = parse_args()
    run_dir = Path(a.run_dir).resolve()
    outdir = Path(a.outdir).resolve()
    outdir.mkdir(parents=True, exist_ok=True)

    missing = [name for name in a.required if not (run_dir / name).exists()]
    manifest_path = run_dir / a.manifest
    manifest_ok = manifest_path.exists()

    manifest_obj = {
        "run_dir": str(run_dir),
        "required_artifacts": list(a.required),
        "existing_artifacts": sorted([p.name for p in run_dir.glob("*") if p.is_file()]),
    }

    (outdir / "run_manifest.json").write_text(json.dumps(manifest_obj, indent=2), encoding="utf-8")

    report = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "run_dir": str(run_dir),
        "missing_artifacts": missing,
        "manifest_present": manifest_ok,
        "status": "pass" if (not missing and manifest_ok) else "fail",
    }
    (outdir / "run_contract_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(outdir / "run_contract_report.json")


if __name__ == "__main__":
    main()
