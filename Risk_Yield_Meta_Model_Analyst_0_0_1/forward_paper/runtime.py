"""Small runtime helpers shared by the forward-paper service and chart API.

Runtime state deliberately lives outside the repository by default.  This
keeps append-only journals, PID files, and optimizer trial registries out of
Git while still allowing tests and deployments to select an explicit state
directory through ``RISKYIELDMM_STATE_DIR``.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STATE_DIR_ENV = "RISKYIELDMM_STATE_DIR"


def default_state_dir() -> Path:
    """Return the process-independent RiskYieldMM runtime state directory."""

    configured = os.environ.get(STATE_DIR_ENV, "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    xdg_state = os.environ.get("XDG_STATE_HOME", "").strip()
    root = Path(xdg_state).expanduser() if xdg_state else Path.home() / ".local/state"
    return (root / "riskyieldmm" / "forward_paper").resolve()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def iso_utc(value: datetime | None) -> str | None:
    if value is None:
        return None
    return as_utc(value).isoformat().replace("+00:00", "Z")


def parse_utc(value: str | datetime | None) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return as_utc(value)
    return as_utc(datetime.fromisoformat(str(value).replace("Z", "+00:00")))


def atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    """Publish one JSON object through fsync plus atomic replacement."""

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    encoded = json.dumps(
        dict(payload),
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    try:
        with temporary.open("wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def read_json_object(path: Path) -> dict[str, Any] | None:
    """Read a JSON object, returning ``None`` for an absent file."""

    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    if not isinstance(raw, dict):
        raise ValueError(f"Runtime JSON must contain an object: {path}")
    return raw


def _fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


__all__ = [
    "STATE_DIR_ENV",
    "as_utc",
    "atomic_write_json",
    "default_state_dir",
    "iso_utc",
    "parse_utc",
    "read_json_object",
    "utc_now",
]
