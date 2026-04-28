#!/usr/bin/env python3
"""Validate and build deterministic Notion worklog state artifact."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

STATUSES = {"START", "IN_PROGRESS", "BLOCKER", "DONE"}
SCOPES = {"Substantial", "Code Change", "Analysis"}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build Notion worklog state")
    p.add_argument("--name", required=True)
    p.add_argument("--date", required=True)
    p.add_argument("--status", required=True, choices=sorted(STATUSES))
    p.add_argument("--scope", required=True, choices=sorted(SCOPES))
    p.add_argument("--linear-issue", required=True)
    p.add_argument("--summary", required=True)
    p.add_argument("--artifacts", required=True)
    p.add_argument("--next-actions", required=True)
    p.add_argument("--outdir", default=".")
    return p.parse_args()


def main() -> None:
    a = parse_args()
    outdir = Path(a.outdir).resolve()
    outdir.mkdir(parents=True, exist_ok=True)

    payload = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "Name": a.name,
        "Date": a.date,
        "Status": a.status,
        "Scope": a.scope,
        "Linear Issue": a.linear_issue,
        "Summary": a.summary,
        "Artifacts": a.artifacts,
        "Next Actions": a.next_actions,
    }

    path = outdir / "notion_worklog_state.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(path)


if __name__ == "__main__":
    main()
