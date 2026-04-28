"""Clean production entrypoint for the shared HTF workflow.

This file is the supported HTF production launcher.
The old mixed legacy notebook body was archived to:
- `Archive/htf_pythonscript_legacy_2026-04-01.py`

Actual stage execution still lives in shared modules under
`scripts/feature_engineering/`. This file owns only production orchestration,
run logging, and the config surface used to launch the shared pipeline.
"""

from __future__ import annotations

import atexit
import builtins
import importlib
import json
import os
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import polars as pl


def resolve_project_root() -> Path:
    """Resolve repo root for script execution from any cwd."""
    candidates: list[Path] = []

    if "__file__" in globals():
        file_path = Path(__file__).resolve()
        candidates.extend([file_path.parent.parent, file_path.parent])

    cwd = Path.cwd().resolve()
    candidates.extend([cwd, cwd.parent, cwd.parent.parent])

    seen: set[Path] = set()
    for cand in candidates:
        try:
            cand = cand.resolve()
        except FileNotFoundError:
            continue
        if cand in seen:
            continue
        seen.add(cand)
        if (cand / "notebooks" / "htf_pythonscript.py").exists():
            return cand
        if (cand / "data").exists() and (cand / "fetchingByBit").exists():
            return cand

    return Path("..").resolve()


PROJECT_ROOT = resolve_project_root()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.feature_engineering.htf_shared_config import (  # noqa: E402
    SHARED_BREAKFREE_THRESHOLD_1M,
    SHARED_BREAKOUT_THRESHOLD,
    SHARED_DISTANCE_WINDOWS_BY_TF,
    SHARED_PIPELINE_ARTIFACT_VERSION,
    SHARED_RISK_RATIO,
    SHARED_THRESHOLDS_BY_TF,
)


RUN_DEBUG_OUTPUT_DIR = PROJECT_ROOT / "test_output" / "htf_run_logs"
RUN_DEBUG_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

RUN_INSTANCE_ID = (
    f"htf_pythonscript_{datetime.now().strftime('%Y%m%d_%H%M%S')}_pid{os.getpid()}"
)
RUN_LOG_PATH = RUN_DEBUG_OUTPUT_DIR / f"{RUN_INSTANCE_ID}.log"
RUN_STATUS_PATH = RUN_DEBUG_OUTPUT_DIR / f"{RUN_INSTANCE_ID}_status.json"
RUN_HEARTBEAT_SECONDS = 60
RUN_SILENCE_HEARTBEAT_SECONDS = 60
RUN_LOOP_PROGRESS_EVERY = 250
RUN_LOG_HANDLE = open(RUN_LOG_PATH, "a", buffering=1, encoding="utf-8")
RUN_LOG_LOCK = threading.Lock()
RUN_HEARTBEAT_STOP = threading.Event()
_ORIGINAL_PRINT = builtins.print
RUN_PROGRESS: dict[str, Any] = {
    "run_id": RUN_INSTANCE_ID,
    "pid": os.getpid(),
    "stage": "startup",
    "detail": "",
    "started_at": time.time(),
    "stage_started_at": time.time(),
    "last_activity_at": time.time(),
    "last_status_write_at": 0.0,
}


def _format_elapsed(seconds: float) -> str:
    seconds = max(0, int(seconds))
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}h{minutes:02d}m{secs:02d}s"
    if minutes:
        return f"{minutes}m{secs:02d}s"
    return f"{secs}s"


def _stringify_progress_value(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, tuple):
        return list(value)
    return value


def _write_run_status(reason: str = "update") -> None:
    now = time.time()
    payload = {
        "reason": reason,
        "run_id": RUN_PROGRESS["run_id"],
        "pid": RUN_PROGRESS["pid"],
        "stage": RUN_PROGRESS["stage"],
        "detail": RUN_PROGRESS["detail"],
        "run_elapsed_seconds": round(now - RUN_PROGRESS["started_at"], 3),
        "stage_elapsed_seconds": round(now - RUN_PROGRESS["stage_started_at"], 3),
        "silence_seconds": round(now - RUN_PROGRESS["last_activity_at"], 3),
        "log_path": str(RUN_LOG_PATH),
        "status_path": str(RUN_STATUS_PATH),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }
    with RUN_STATUS_PATH.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
    RUN_PROGRESS["last_status_write_at"] = now


def _append_to_run_log(text: str) -> None:
    if not text:
        return
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    normalized = text if text.endswith("\n") else text + "\n"
    lines = normalized.rstrip("\n").split("\n") or [""]
    with RUN_LOG_LOCK:
        for line in lines:
            RUN_LOG_HANDLE.write(f"[{timestamp}] {line}\n")
        RUN_LOG_HANDLE.flush()


def _tee_print(*args, **kwargs):
    _ORIGINAL_PRINT(*args, **kwargs)
    sep = kwargs.get("sep", " ")
    end = kwargs.get("end", "\n")
    message = sep.join(str(arg) for arg in args) + end
    RUN_PROGRESS["last_activity_at"] = time.time()
    _append_to_run_log(message)
    if RUN_PROGRESS["last_activity_at"] - RUN_PROGRESS["last_status_write_at"] >= 15:
        _write_run_status("activity")


def set_run_stage(stage: str, detail: str | None = None, *, announce: bool = True) -> None:
    RUN_PROGRESS["stage"] = stage
    RUN_PROGRESS["detail"] = detail or ""
    RUN_PROGRESS["stage_started_at"] = time.time()
    RUN_PROGRESS["last_activity_at"] = time.time()
    _write_run_status("stage_change")
    if announce:
        print("\n" + "=" * 70)
        print(f"[RUN STAGE] {stage}")
        if detail:
            print(f"detail: {detail}")
        print(f"log: {RUN_LOG_PATH}")
        print(f"status: {RUN_STATUS_PATH}")
        print("=" * 70)


def log_loop_progress(
    label: str,
    current: int,
    total: int,
    *,
    started_at: float,
    every: int = RUN_LOOP_PROGRESS_EVERY,
) -> None:
    if total <= 0:
        return
    if current != 1 and current != total and current % every != 0:
        return
    progress = current / total
    elapsed = time.time() - started_at
    eta = (elapsed / progress) * (1.0 - progress) if progress > 0 else 0.0
    print(
        f"  {label}: {current:,}/{total:,} "
        f"({progress * 100:5.1f}%) | elapsed={_format_elapsed(elapsed)} "
        f"| eta~{_format_elapsed(eta)}"
    )
    _write_run_status("loop_progress")


def workflow_progress_callback(event: str, payload: dict[str, Any]) -> None:
    stage = payload.get("stage", "multi-regime")
    fields = []
    for key, value in payload.items():
        if key == "stage":
            continue
        rendered = _stringify_progress_value(value)
        if isinstance(rendered, (list, dict)):
            rendered = json.dumps(rendered)
        fields.append(f"{key}={rendered}")
    detail = ", ".join(fields)
    if event == "start":
        set_run_stage(f"HTF / {stage}", detail=detail, announce=True)
    else:
        RUN_PROGRESS["detail"] = f"{stage} | {detail}" if detail else stage
        RUN_PROGRESS["last_activity_at"] = time.time()
        _write_run_status(f"multi_regime_{event}")
        print(f"[HTF][{event.upper()}] {stage}" + (f" | {detail}" if detail else ""))


def _heartbeat_worker() -> None:
    while not RUN_HEARTBEAT_STOP.wait(RUN_HEARTBEAT_SECONDS):
        silence = time.time() - RUN_PROGRESS["last_activity_at"]
        if silence < RUN_SILENCE_HEARTBEAT_SECONDS:
            continue
        print(
            "[HEARTBEAT] "
            f"stage={RUN_PROGRESS['stage']} | "
            f"detail={RUN_PROGRESS['detail'] or '-'} | "
            f"run_elapsed={_format_elapsed(time.time() - RUN_PROGRESS['started_at'])} | "
            f"stage_elapsed={_format_elapsed(time.time() - RUN_PROGRESS['stage_started_at'])} | "
            f"silence={_format_elapsed(silence)}"
        )
        _write_run_status("heartbeat")


def _shutdown_run_logging() -> None:
    RUN_HEARTBEAT_STOP.set()
    _write_run_status("shutdown")
    builtins.print = _ORIGINAL_PRINT
    with RUN_LOG_LOCK:
        RUN_LOG_HANDLE.flush()
        RUN_LOG_HANDLE.close()


builtins.print = _tee_print
HEARTBEAT_THREAD = threading.Thread(
    target=_heartbeat_worker,
    name="htf-run-heartbeat",
    daemon=True,
)
HEARTBEAT_THREAD.start()
atexit.register(_shutdown_run_logging)


RUN_MULTI_REGIME_EXTENSION = os.environ.get("HTF_RUN_MULTI_REGIME_EXTENSION", "1") == "1"
MULTI_REGIME_BUILD_REGIMES = ("8h", "24h", "7d")
MULTI_REGIME_VALIDATE_REGIMES = ("8h", "24h", "7d")
MULTI_REGIME_FORCE_FULL_REBUILD = False
MULTI_REGIME_SMOKE_MODE = False
MULTI_REGIME_SMOKE_START = None
MULTI_REGIME_SMOKE_END = None
MULTI_REGIME_RUN_OPTIMIZATION = True
MULTI_REGIME_RUN_HELPERS = True
MULTI_REGIME_RUN_VALIDATION = True

MULTI_REGIME_PIPELINE_ARTIFACT_VERSION = SHARED_PIPELINE_ARTIFACT_VERSION
MULTI_REGIME_THRESHOLDS_BY_TF = SHARED_THRESHOLDS_BY_TF
MULTI_REGIME_DISTANCE_WINDOWS_BY_TF = SHARED_DISTANCE_WINDOWS_BY_TF
MULTI_REGIME_BREAKOUT_THRESHOLD = SHARED_BREAKOUT_THRESHOLD
MULTI_REGIME_RISK_RATIO = SHARED_RISK_RATIO
MULTI_REGIME_BREAKFREE_THRESHOLD_1M = SHARED_BREAKFREE_THRESHOLD_1M


def run_htf_workflow() -> dict[str, Any] | None:
    import scripts.feature_engineering.htf_multiregime_pipeline as mr_module

    importlib.reload(mr_module)
    MultiRegimeHTFConfig = mr_module.MultiRegimeHTFConfig
    run_multi_regime_htf_pipeline = mr_module.run_multi_regime_htf_pipeline

    set_run_stage(
        "HTF workflow",
        detail=(
            f"regimes={MULTI_REGIME_BUILD_REGIMES}, helpers={MULTI_REGIME_RUN_HELPERS}, "
            f"optimization={MULTI_REGIME_RUN_OPTIMIZATION}"
        ),
    )
    print("=" * 70)
    print("HTF WORKFLOW: AUTHORITATIVE PRODUCTION ENTRYPOINT")
    print("=" * 70)
    print(f"Run enabled: {RUN_MULTI_REGIME_EXTENSION}")
    print(f"Build regimes: {MULTI_REGIME_BUILD_REGIMES}")
    print(f"Validate regimes: {MULTI_REGIME_VALIDATE_REGIMES}")
    print(f"Force full rebuild: {MULTI_REGIME_FORCE_FULL_REBUILD}")
    print(f"Smoke mode: {MULTI_REGIME_SMOKE_MODE}")
    print(f"Run optimization: {MULTI_REGIME_RUN_OPTIMIZATION}")
    print(f"Run helpers: {MULTI_REGIME_RUN_HELPERS}")
    print(f"Run validation: {MULTI_REGIME_RUN_VALIDATION}")
    print("=" * 70)

    if not RUN_MULTI_REGIME_EXTENSION:
        print("Shared multi-regime pipeline disabled by HTF_RUN_MULTI_REGIME_EXTENSION=0.")
        return None

    config = MultiRegimeHTFConfig(
        project_root=PROJECT_ROOT,
        data_dir=PROJECT_ROOT / "data",
        raw_data_dir=PROJECT_ROOT / "fetchingByBit",
        pipeline_artifact_version=MULTI_REGIME_PIPELINE_ARTIFACT_VERSION,
        thresholds_by_tf=MULTI_REGIME_THRESHOLDS_BY_TF,
        distance_windows_by_tf=MULTI_REGIME_DISTANCE_WINDOWS_BY_TF,
        build_regimes=MULTI_REGIME_BUILD_REGIMES,
        validate_regimes=MULTI_REGIME_VALIDATE_REGIMES,
        rebuild_existing=MULTI_REGIME_FORCE_FULL_REBUILD,
        run_optimization=MULTI_REGIME_RUN_OPTIMIZATION,
        run_helpers=MULTI_REGIME_RUN_HELPERS,
        run_validation=MULTI_REGIME_RUN_VALIDATION,
        breakout_threshold=MULTI_REGIME_BREAKOUT_THRESHOLD,
        risk_ratio=MULTI_REGIME_RISK_RATIO,
        breakfree_threshold_1m=MULTI_REGIME_BREAKFREE_THRESHOLD_1M,
        smoke_mode=MULTI_REGIME_SMOKE_MODE,
        smoke_start=MULTI_REGIME_SMOKE_START,
        smoke_end=MULTI_REGIME_SMOKE_END,
        progress_callback=workflow_progress_callback,
    )
    summary = run_multi_regime_htf_pipeline(config)
    validation_df = summary.get("validation")
    if isinstance(validation_df, pl.DataFrame) and len(validation_df) > 0:
        print("\n" + "=" * 70)
        print("MULTI-REGIME VALIDATION SUMMARY")
        print("=" * 70)
        print(
            validation_df.group_by(["regime", "family", "tf", "stage"])
            .agg(
                [
                    pl.len().alias("checks"),
                    pl.col("ok").sum().alias("pass"),
                    (pl.len() - pl.col("ok").sum()).alias("fail"),
                ]
            )
            .sort(["regime", "family", "tf", "stage"])
        )
    return summary


def main() -> int:
    set_run_stage(
        "Workflow bootstrap",
        detail=f"pid={os.getpid()}, run_id={RUN_INSTANCE_ID}",
        announce=False,
    )
    print("=" * 70)
    print("RUN LOGGING ENABLED")
    print("=" * 70)
    print(f"Run ID: {RUN_INSTANCE_ID}")
    print(f"PID: {os.getpid()}")
    print(f"Log file: {RUN_LOG_PATH}")
    print(f"Status file: {RUN_STATUS_PATH}")
    print("=" * 70)
    print("Production note: this is the supported HTF production entrypoint.")
    print("Legacy notebook body is archived in Archive/htf_pythonscript_legacy_2026-04-01.py.")
    print("=" * 70)
    run_htf_workflow()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
