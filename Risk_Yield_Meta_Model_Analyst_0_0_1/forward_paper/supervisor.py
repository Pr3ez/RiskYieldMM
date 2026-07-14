"""Conservative background-process control for the forward-paper service."""

from __future__ import annotations

import os
import signal
import subprocess
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .runtime import atomic_write_json, iso_utc, read_json_object, utc_now

PID_FILENAME = "service.pid.json"
LOG_FILENAME = "service.log"
STATUS_FILENAME = "status.json"


@dataclass(frozen=True)
class ProcessStatus:
    running: bool
    pid: int | None
    reason: str
    record: dict[str, Any] | None


def pid_path(state_dir: Path) -> Path:
    return Path(state_dir) / PID_FILENAME


def log_path(state_dir: Path) -> Path:
    return Path(state_dir) / LOG_FILENAME


def status_path(state_dir: Path) -> Path:
    return Path(state_dir) / STATUS_FILENAME


def inspect_process(state_dir: Path) -> ProcessStatus:
    """Return whether the recorded service process still matches its command."""

    path = pid_path(state_dir)
    try:
        record = read_json_object(path)
    except (OSError, ValueError) as exc:
        return ProcessStatus(False, None, f"invalid_pid_record: {exc}", None)
    if record is None:
        return ProcessStatus(False, None, "not_started", None)
    try:
        pid = int(record["pid"])
    except (KeyError, TypeError, ValueError):
        return ProcessStatus(False, None, "invalid_pid_record", record)
    if pid <= 1 or not _pid_exists(pid):
        return ProcessStatus(False, pid, "stale_pid", record)
    expected_tokens = record.get("identity_tokens")
    if not isinstance(expected_tokens, list) or not all(
        isinstance(token, str) and token for token in expected_tokens
    ):
        return ProcessStatus(False, pid, "unsafe_pid_record", record)
    command_line = _process_command_line(pid)
    if command_line is None:
        return ProcessStatus(False, pid, "cannot_verify_process_identity", record)
    if not all(token in command_line for token in expected_tokens):
        return ProcessStatus(False, pid, "pid_reused_identity_mismatch", record)
    return ProcessStatus(True, pid, "running", record)


def start_background(
    *,
    command: Sequence[str],
    state_dir: Path,
    cwd: Path,
    identity_tokens: Sequence[str],
) -> ProcessStatus:
    """Start one detached service only when no verified instance is running."""

    state_dir = Path(state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)
    current = inspect_process(state_dir)
    if current.running:
        return current
    if not command or not identity_tokens:
        raise ValueError("Background command and identity tokens are required")

    output_path = log_path(state_dir)
    with output_path.open("ab", buffering=0) as output:
        process = subprocess.Popen(
            list(command),
            cwd=str(cwd),
            stdin=subprocess.DEVNULL,
            stdout=output,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            close_fds=True,
        )
    record = {
        "pid": process.pid,
        "started_at": iso_utc(utc_now()),
        "command": list(command),
        "cwd": str(Path(cwd).resolve()),
        "identity_tokens": list(identity_tokens),
        "log_path": str(output_path.resolve()),
    }
    atomic_write_json(pid_path(state_dir), record)
    time.sleep(0.25)
    if process.poll() is not None:
        return ProcessStatus(
            False,
            process.pid,
            f"exited_during_startup_code_{process.returncode}",
            record,
        )
    return inspect_process(state_dir)


def stop_background(state_dir: Path, *, timeout_seconds: float = 15.0) -> ProcessStatus:
    """Send SIGTERM only after verifying the recorded process identity."""

    if timeout_seconds <= 0.0:
        raise ValueError("timeout_seconds must be positive")
    current = inspect_process(state_dir)
    if not current.running or current.pid is None:
        return current
    os.kill(current.pid, signal.SIGTERM)
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if not _pid_exists(current.pid):
            _remove_stale_pid_file(state_dir, expected_pid=current.pid)
            return ProcessStatus(False, current.pid, "stopped", current.record)
        time.sleep(0.1)
    return ProcessStatus(True, current.pid, "termination_timeout", current.record)


def remove_own_pid_file(state_dir: Path, *, pid: int | None = None) -> None:
    _remove_stale_pid_file(state_dir, expected_pid=pid or os.getpid())


def _remove_stale_pid_file(state_dir: Path, *, expected_pid: int) -> None:
    path = pid_path(state_dir)
    try:
        record = read_json_object(path)
    except (OSError, ValueError):
        return
    if record is None:
        return
    try:
        recorded_pid = int(record.get("pid"))
    except (TypeError, ValueError):
        return
    if recorded_pid != expected_pid:
        return
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def _pid_exists(pid: int) -> bool:
    try:
        stat_fields = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8").split()
    except OSError:
        stat_fields = []
    if len(stat_fields) >= 3 and stat_fields[2] == "Z":
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _process_command_line(pid: int) -> str | None:
    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes()
    except OSError:
        return None
    return raw.replace(b"\x00", b" ").decode("utf-8", errors="replace")


__all__ = [
    "LOG_FILENAME",
    "PID_FILENAME",
    "STATUS_FILENAME",
    "ProcessStatus",
    "inspect_process",
    "log_path",
    "pid_path",
    "remove_own_pid_file",
    "start_background",
    "status_path",
    "stop_background",
]
