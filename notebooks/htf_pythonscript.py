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
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any

import polars as pl


# The launcher can be called from the repo root, from `notebooks/`, or by an
# IDE/debugger with a different cwd. Resolve the repository root first so every
# later path is stable and absolute.
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

# Keep shared thresholds and artifact-version values outside the launcher. This
# script should decide *what to run*, while shared modules define model/label
# contracts used by the real pipeline.
from scripts.feature_engineering.htf_shared_config import (  # noqa: E402
    SHARED_BREAKFREE_THRESHOLD_1M,
    SHARED_BREAKOUT_THRESHOLD,
    SHARED_DISTANCE_WINDOWS_BY_TF,
    SHARED_PIPELINE_ARTIFACT_VERSION,
    SHARED_RISK_RATIO,
    SHARED_THRESHOLDS_BY_TF,
)
from scripts.feature_engineering.htf_asset_registry import (  # noqa: E402
    get_htf_asset_spec,
    htf_asset_ids_from_csv,
)


# Per-run diagnostics are always written under ignored `test_output/` paths.
# This gives long local runs a live log and heartbeat status without polluting
# source-controlled artifacts.
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
    """Persist lightweight heartbeat/status JSON for external monitoring."""
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
    """Mirror all launcher/pipeline prints to stdout and the run log."""
    _ORIGINAL_PRINT(*args, **kwargs)
    sep = kwargs.get("sep", " ")
    end = kwargs.get("end", "\n")
    message = sep.join(str(arg) for arg in args) + end
    RUN_PROGRESS["last_activity_at"] = time.time()
    _append_to_run_log(message)
    if RUN_PROGRESS["last_activity_at"] - RUN_PROGRESS["last_status_write_at"] >= 15:
        _write_run_status("activity")


def set_run_stage(stage: str, detail: str | None = None, *, announce: bool = True) -> None:
    """Move the run heartbeat to a new human-readable workflow stage."""
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
    """Print sparse progress for large loops without flooding the run log."""
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
    """Bridge structured progress from the shared HTF pipeline into run logging."""
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
    """Emit periodic status when a long-running stage is otherwise quiet."""
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
    """Restore normal printing and close run-log resources on every exit path."""
    RUN_HEARTBEAT_STOP.set()
    _write_run_status("shutdown")
    builtins.print = _ORIGINAL_PRINT
    with RUN_LOG_LOCK:
        RUN_LOG_HANDLE.flush()
        RUN_LOG_HANDLE.close()


# Install print teeing before workflow startup so early failures are captured in
# the same log as normal pipeline output.
builtins.print = _tee_print
HEARTBEAT_THREAD = threading.Thread(
    target=_heartbeat_worker,
    name="htf-run-heartbeat",
    daemon=True,
)
HEARTBEAT_THREAD.start()
atexit.register(_shutdown_run_logging)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off"}


def _env_csv_tuple(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    values = tuple(part.strip() for part in raw.split(",") if part.strip())
    return values or default


# Environment surface for local production runs.
#
# Common examples:
#   HTF_ASSETS=core
#   HTF_ASSET_OUTPUT_MODE=multiasset
#   HTF_RUN_OPTIMIZATION=0 HTF_RUN_HELPERS=0  # fast validation/smoke mode
#   HTF_SESSION_REGIMES=8h                    # rollback session assets only
RUN_MULTI_REGIME_EXTENSION = _env_bool("HTF_RUN_MULTI_REGIME_EXTENSION", True)
MULTI_REGIME_ASSETS = htf_asset_ids_from_csv(os.environ.get("HTF_ASSETS"))
MULTI_REGIME_ASSET_OUTPUT_MODE = os.environ.get("HTF_ASSET_OUTPUT_MODE", "legacy")
MULTI_REGIME_BUILD_REGIMES = _env_csv_tuple("HTF_BUILD_REGIMES", ("8h", "24h", "7d"))
MULTI_REGIME_VALIDATE_REGIMES = _env_csv_tuple(
    "HTF_VALIDATE_REGIMES",
    MULTI_REGIME_BUILD_REGIMES,
)
# Session assets are now allowed to run 8h/24h/7d. This override exists only as
# a conservative rollback switch when we want to temporarily restrict them, e.g.
# `HTF_SESSION_REGIMES=8h`.
MULTI_REGIME_SESSION_REGIMES = (
    _env_csv_tuple("HTF_SESSION_REGIMES", MULTI_REGIME_BUILD_REGIMES)
    if os.environ.get("HTF_SESSION_REGIMES") is not None
    else None
)
MULTI_REGIME_FORCE_FULL_REBUILD = _env_bool("HTF_FORCE_FULL_REBUILD", False)
MULTI_REGIME_SMOKE_MODE = False
MULTI_REGIME_SMOKE_START = None
MULTI_REGIME_SMOKE_END = None
MULTI_REGIME_RUN_OPTIMIZATION = _env_bool("HTF_RUN_OPTIMIZATION", True)
MULTI_REGIME_RUN_HELPERS = _env_bool("HTF_RUN_HELPERS", True)
MULTI_REGIME_RUN_VALIDATION = _env_bool("HTF_RUN_VALIDATION", True)
MULTI_REGIME_FAIL_FAST_ASSET_ERRORS = _env_bool("HTF_FAIL_FAST_ASSET_ERRORS", False)

# Shared model/label constants are copied into the config object below so the
# launcher logs exactly which contract was used for a run.
MULTI_REGIME_PIPELINE_ARTIFACT_VERSION = SHARED_PIPELINE_ARTIFACT_VERSION
MULTI_REGIME_THRESHOLDS_BY_TF = SHARED_THRESHOLDS_BY_TF
MULTI_REGIME_DISTANCE_WINDOWS_BY_TF = SHARED_DISTANCE_WINDOWS_BY_TF
MULTI_REGIME_BREAKOUT_THRESHOLD = SHARED_BREAKOUT_THRESHOLD
MULTI_REGIME_RISK_RATIO = SHARED_RISK_RATIO
MULTI_REGIME_BREAKFREE_THRESHOLD_1M = SHARED_BREAKFREE_THRESHOLD_1M
MULTI_REGIME_LABEL_WINDOW_POLICY = os.environ.get(
    "HTF_LABEL_WINDOW_POLICY",
    "opposite_family_first_half",
)


def _htf_output_dir_for_asset(asset_id: str) -> Path:
    """Resolve where generated HTF artifacts should be written for an asset."""
    # Preserve legacy BTC-only behavior for old local workflows. New multi-asset
    # work should set `HTF_ASSET_OUTPUT_MODE=multiasset`, which writes each asset
    # into its own isolated tree under `data/htf_multiasset/{asset}/`.
    if (
        MULTI_REGIME_ASSET_OUTPUT_MODE == "legacy"
        and MULTI_REGIME_ASSETS == ("BTCUSDT",)
    ):
        return PROJECT_ROOT / "data"
    return PROJECT_ROOT / "data" / "htf_multiasset" / asset_id.lower()


def _htf_raw_dir_for_asset(asset_id: str) -> Path:
    """Resolve the provider root used by feature code for this asset."""
    spec = get_htf_asset_spec(asset_id)
    if spec.source_kind == "multiasset_ohlcv":
        return PROJECT_ROOT / "fetchingMultiAsset"
    return PROJECT_ROOT / "fetchingByBit"


def _htf_regimes_for_asset(asset_id: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Apply optional per-session-asset regime rollback after global parsing."""
    spec = get_htf_asset_spec(asset_id)
    build_regimes = MULTI_REGIME_BUILD_REGIMES
    validate_regimes = MULTI_REGIME_VALIDATE_REGIMES
    if spec.source_kind == "multiasset_ohlcv" and MULTI_REGIME_SESSION_REGIMES is not None:
        allowed = set(MULTI_REGIME_SESSION_REGIMES)
        build_regimes = tuple(regime for regime in build_regimes if regime in allowed)
        validate_regimes = tuple(regime for regime in validate_regimes if regime in allowed)
        if not build_regimes:
            raise ValueError(
                f"Asset {asset_id} has no regimes left after HTF_SESSION_REGIMES="
                f"{MULTI_REGIME_SESSION_REGIMES!r}."
            )
    return build_regimes, validate_regimes


def run_htf_workflow() -> dict[str, Any] | None:
    """Build per-asset HTF artifacts using the shared multi-regime pipeline."""
    # Reload the pipeline module so iterative local development can update the
    # implementation without restarting the whole Python process/IDE session.
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
    print(f"Assets: {MULTI_REGIME_ASSETS}")
    print(f"Asset output mode: {MULTI_REGIME_ASSET_OUTPUT_MODE}")
    print(f"Requested build regimes: {MULTI_REGIME_BUILD_REGIMES}")
    print(f"Requested validate regimes: {MULTI_REGIME_VALIDATE_REGIMES}")
    print(
        "Session regime override: "
        f"{MULTI_REGIME_SESSION_REGIMES if MULTI_REGIME_SESSION_REGIMES is not None else 'none'}"
    )
    print(f"Force full rebuild: {MULTI_REGIME_FORCE_FULL_REBUILD}")
    print(f"Smoke mode: {MULTI_REGIME_SMOKE_MODE}")
    print(f"Run optimization: {MULTI_REGIME_RUN_OPTIMIZATION}")
    print(f"Run helpers: {MULTI_REGIME_RUN_HELPERS}")
    print(f"Run validation: {MULTI_REGIME_RUN_VALIDATION}")
    print(f"Fail fast on asset errors: {MULTI_REGIME_FAIL_FAST_ASSET_ERRORS}")
    print("=" * 70)

    if not RUN_MULTI_REGIME_EXTENSION:
        print("Shared multi-regime pipeline disabled by HTF_RUN_MULTI_REGIME_EXTENSION=0.")
        return None

    # Run each requested asset independently. By default one asset failure is
    # recorded and the launcher continues, which is useful for long core runs
    # where a single source issue should not hide the status of later assets.
    # `HTF_FAIL_FAST_ASSET_ERRORS=1` restores immediate failure behavior.
    summaries: dict[str, Any] = {}
    asset_errors: dict[str, str] = {}
    for asset_id in MULTI_REGIME_ASSETS:
        print("\n" + "=" * 70)
        print(f"HTF ASSET START: {asset_id}")
        print("=" * 70)
        asset_build_regimes, asset_validate_regimes = _htf_regimes_for_asset(asset_id)
        print(f"Asset build regimes: {asset_build_regimes}")
        print(f"Asset validate regimes: {asset_validate_regimes}")
        # MultiRegimeHTFConfig is the narrow handoff from this launcher to the
        # real pipeline. Everything below is either a path, a run-control flag,
        # or a shared model/label contract value.
        config = MultiRegimeHTFConfig(
            project_root=PROJECT_ROOT,
            data_dir=_htf_output_dir_for_asset(asset_id),
            raw_data_dir=_htf_raw_dir_for_asset(asset_id),
            pipeline_artifact_version=MULTI_REGIME_PIPELINE_ARTIFACT_VERSION,
            thresholds_by_tf=MULTI_REGIME_THRESHOLDS_BY_TF,
            distance_windows_by_tf=MULTI_REGIME_DISTANCE_WINDOWS_BY_TF,
            asset_id=asset_id,
            build_regimes=asset_build_regimes,
            validate_regimes=asset_validate_regimes,
            rebuild_existing=MULTI_REGIME_FORCE_FULL_REBUILD,
            run_optimization=MULTI_REGIME_RUN_OPTIMIZATION,
            run_helpers=MULTI_REGIME_RUN_HELPERS,
            run_validation=MULTI_REGIME_RUN_VALIDATION,
            breakout_threshold=MULTI_REGIME_BREAKOUT_THRESHOLD,
            risk_ratio=MULTI_REGIME_RISK_RATIO,
            breakfree_threshold_1m=MULTI_REGIME_BREAKFREE_THRESHOLD_1M,
            label_window_policy=MULTI_REGIME_LABEL_WINDOW_POLICY,
            smoke_mode=MULTI_REGIME_SMOKE_MODE,
            smoke_start=MULTI_REGIME_SMOKE_START,
            smoke_end=MULTI_REGIME_SMOKE_END,
            progress_callback=workflow_progress_callback,
        )
        try:
            summaries[asset_id] = run_multi_regime_htf_pipeline(config)
        except Exception:
            if len(MULTI_REGIME_ASSETS) == 1 or MULTI_REGIME_FAIL_FAST_ASSET_ERRORS:
                raise
            asset_errors[asset_id] = traceback.format_exc()
            summaries[asset_id] = {
                "status": "failed",
                "error": asset_errors[asset_id].splitlines()[-1],
            }
            print("\n" + "=" * 70)
            print(f"HTF ASSET FAILED: {asset_id}")
            print("=" * 70)
            print(asset_errors[asset_id])
            print("Continuing with remaining assets. Final exit will report failures.")

    # Single-asset runs keep the old summary/validation behavior. Multi-asset
    # runs return a dictionary keyed by asset id so callers can inspect each
    # asset's result separately.
    summary = summaries[MULTI_REGIME_ASSETS[0]] if len(MULTI_REGIME_ASSETS) == 1 else summaries
    validation_df = (
        summary.get("validation")
        if isinstance(summary, dict) and len(MULTI_REGIME_ASSETS) == 1
        else None
    )
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
    if asset_errors:
        failed = ", ".join(asset_errors)
        raise AssertionError(
            "One or more HTF assets failed after attempting the configured asset set: "
            f"{failed}. See the per-asset traceback above."
        )
    return summary


def main() -> int:
    """CLI entrypoint used by local shell runs and IDE run configurations."""
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
