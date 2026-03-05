#!/usr/bin/env python3
"""Build deterministic Linear lifecycle payload/state artifact."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

ALLOWED = {"START", "BLOCKER", "DONE"}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build Linear task lifecycle state")
    p.add_argument("--task-title", required=True)
    p.add_argument("--status", required=True, choices=sorted(ALLOWED))
    p.add_argument("--issue", default="")
    p.add_argument("--scope", default="")
    p.add_argument("--acceptance", default="")
    p.add_argument("--summary", default="")
    p.add_argument("--metrics", default="")
    p.add_argument("--artifacts", nargs="*", default=[])
    p.add_argument("--next-actions", default="")
    p.add_argument("--outdir", default=".")
    return p.parse_args()


def main() -> None:
    a = parse_args()
    outdir = Path(a.outdir).resolve()
    outdir.mkdir(parents=True, exist_ok=True)

    payload = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "task_title": a.task_title,
        "status": a.status,
        "issue": a.issue,
        "scope": a.scope,
        "acceptance": a.acceptance,
        "summary": a.summary,
        "metrics": a.metrics,
        "artifacts": list(a.artifacts),
        "next_actions": a.next_actions,
    }

    state_path = outdir / "linear_task_state.json"
    state_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(state_path)


if __name__ == "__main__":
    main()
