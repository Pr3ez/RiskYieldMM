#!/usr/bin/env python3
"""Validate substantial-task continuity state for Linear+Notion tracking."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STATUS_START = "START"
STATUS_IN_PROGRESS = "IN_PROGRESS"
STATUS_BLOCKER = "BLOCKER"
STATUS_DONE = "DONE"
ALLOWED_STATUSES = {STATUS_START, STATUS_IN_PROGRESS, STATUS_BLOCKER, STATUS_DONE}

ALLOWED_NEXT = {
    STATUS_START: {STATUS_IN_PROGRESS, STATUS_BLOCKER, STATUS_DONE},
    STATUS_IN_PROGRESS: {STATUS_IN_PROGRESS, STATUS_BLOCKER, STATUS_DONE},
    STATUS_BLOCKER: {STATUS_IN_PROGRESS, STATUS_BLOCKER, STATUS_DONE},
    STATUS_DONE: {STATUS_DONE},
}


@dataclass
class ValidationResult:
    ok: bool
    errors: list[str]
    warnings: list[str]
    current_status: str


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Validate research task continuity state")
    p.add_argument("--state-file", required=True, help="Path to task_state.json")
    p.add_argument("--expected-next-status", default="", choices=["", *sorted(ALLOWED_STATUSES)])
    p.add_argument("--outdir", default=".", help="Output directory for state_guard_report.json")
    return p.parse_args()


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("state JSON root must be an object")
    return data


def _validate_top_level(data: dict[str, Any], errors: list[str]) -> None:
    for field in ("task_name", "linear_issue", "notion_page", "events"):
        if field not in data:
            errors.append(f"missing required field: {field}")
    if str(data.get("linear_issue", "")).strip() == "":
        errors.append("linear_issue must be non-empty")
    if str(data.get("notion_page", "")).strip() == "":
        errors.append("notion_page must be non-empty")
    if not isinstance(data.get("events"), list) or len(data.get("events", [])) == 0:
        errors.append("events must be a non-empty array")


def _validate_events(data: dict[str, Any], errors: list[str], warnings: list[str]) -> str:
    events = data.get("events", [])
    prev_status = ""
    seen_start = False
    current_status = ""

    for idx, event in enumerate(events):
        if not isinstance(event, dict):
            errors.append(f"events[{idx}] must be object")
            continue

        status = str(event.get("status", "")).strip()
        ts = str(event.get("timestamp_utc", "")).strip()
        if status not in ALLOWED_STATUSES:
            errors.append(f"events[{idx}] invalid status: {status!r}")
            continue
        if ts == "":
            errors.append(f"events[{idx}] missing timestamp_utc")
        else:
            try:
                datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except ValueError:
                errors.append(f"events[{idx}] invalid timestamp_utc: {ts!r}")

        if idx == 0 and status != STATUS_START:
            errors.append("first event status must be START")

        if prev_status:
            allowed_next = ALLOWED_NEXT.get(prev_status, set())
            if status not in allowed_next:
                errors.append(
                    f"invalid transition at events[{idx}]: {prev_status} -> {status}"
                )

        if status == STATUS_START:
            seen_start = True
        if status == STATUS_DONE:
            artifacts = event.get("artifacts")
            metrics = event.get("metrics")
            if not isinstance(artifacts, list) or len(artifacts) == 0:
                errors.append(f"events[{idx}] DONE requires non-empty artifacts list")
            if metrics is None:
                errors.append(f"events[{idx}] DONE requires metrics")
            elif isinstance(metrics, str) and metrics.strip() == "":
                errors.append(f"events[{idx}] DONE metrics string cannot be empty")

        prev_status = status
        current_status = status

    if not seen_start:
        errors.append("status history must include START")

    if current_status != STATUS_DONE:
        warnings.append("current status is not DONE")

    return current_status


def _validate_expected_next(current_status: str, expected_next_status: str, errors: list[str]) -> None:
    if expected_next_status == "":
        return
    allowed_next = ALLOWED_NEXT.get(current_status, set())
    if expected_next_status not in allowed_next:
        errors.append(
            f"expected next status invalid for current status {current_status}: {expected_next_status}"
        )


def _write_report(outdir: Path, state_file: Path, result: ValidationResult) -> Path:
    outdir.mkdir(parents=True, exist_ok=True)
    report = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "state_file": str(state_file.resolve()),
        "ok": bool(result.ok),
        "current_status": result.current_status,
        "errors": result.errors,
        "warnings": result.warnings,
    }
    report_path = outdir / "state_guard_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report_path


def main() -> None:
    args = _parse_args()
    state_file = Path(args.state_file).expanduser().resolve()
    outdir = Path(args.outdir).expanduser().resolve()

    errors: list[str] = []
    warnings: list[str] = []
    current_status = ""

    try:
        data = _load_json(state_file)
        _validate_top_level(data, errors)
        if "events" in data and isinstance(data.get("events"), list):
            current_status = _validate_events(data, errors, warnings)
        _validate_expected_next(current_status=current_status, expected_next_status=str(args.expected_next_status), errors=errors)
    except Exception as exc:  # defensive: report parse/runtime failure as validation error
        errors.append(f"failed to validate state: {exc}")

    result = ValidationResult(
        ok=(len(errors) == 0),
        errors=errors,
        warnings=warnings,
        current_status=current_status,
    )
    report_path = _write_report(outdir, state_file, result)

    print(str(report_path))
    if not result.ok:
        for err in result.errors:
            print(f"ERROR: {err}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
