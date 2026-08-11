"""Small report helpers for clean RPF walk-forward stages."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import polars as pl


def append_event(path: Path, event: str, **fields: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"event": event, "ts": datetime.now(timezone.utc).isoformat(), **fields}
    with path.open("a") as handle:
        handle.write(json.dumps(payload, default=str) + "\n")


def write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str))
    return path


def write_stage_status(path: Path, *, stage: str, status: str, **fields: Any) -> Path:
    return write_json(
        path,
        {
            "stage": stage,
            "status": status,
            "written_at": datetime.now(timezone.utc).isoformat(),
            **fields,
        },
    )


def write_trials(path: Path, rows: list[dict[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if rows:
        pl.DataFrame(rows, infer_schema_length=None).write_parquet(path)
    else:
        pl.DataFrame(schema={"trial_number": pl.Int64, "status": pl.String}).write_parquet(path)
    return path


def write_markdown(path: Path, *, title: str, sections: dict[str, Any]) -> Path:
    lines = [f"# {title}", ""]
    for heading, value in sections.items():
        lines.extend([f"## {heading}", ""])
        if isinstance(value, dict):
            for key, item in value.items():
                lines.append(f"- `{key}`: `{_fmt(item)}`")
        elif isinstance(value, list):
            for item in value:
                lines.append(f"- {item}")
        else:
            lines.append(str(value))
        lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n")
    return path


def _fmt(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)
