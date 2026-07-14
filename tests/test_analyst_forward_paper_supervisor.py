from __future__ import annotations

import os
import sys
from pathlib import Path

ANALYST_ROOT = (
    Path(__file__).resolve().parents[1] / "Risk_Yield_Meta_Model_Analyst_0_0_1"
)
if str(ANALYST_ROOT) not in sys.path:
    sys.path.insert(0, str(ANALYST_ROOT))

from forward_paper.runtime import atomic_write_json  # noqa: E402
from forward_paper.supervisor import (  # noqa: E402
    inspect_process,
    pid_path,
    start_background,
    stop_background,
)


def test_supervisor_starts_verifies_and_stops_only_matching_process(
    tmp_path: Path,
) -> None:
    marker = "riskyield-supervisor-test-marker"
    command = [
        sys.executable,
        "-c",
        "import time; time.sleep(30)",
        marker,
    ]
    started = start_background(
        command=command,
        state_dir=tmp_path,
        cwd=tmp_path,
        identity_tokens=(marker,),
    )
    try:
        assert started.running is True
        assert started.pid is not None
        inspected = inspect_process(tmp_path)
        assert inspected.running is True
        assert inspected.pid == started.pid
    finally:
        stopped = stop_background(tmp_path, timeout_seconds=5)
    assert stopped.running is False
    assert stopped.reason == "stopped"
    assert inspect_process(tmp_path).running is False


def test_supervisor_refuses_pid_record_with_wrong_identity(tmp_path: Path) -> None:
    atomic_write_json(
        pid_path(tmp_path),
        {
            "pid": os.getpid(),
            "identity_tokens": ["definitely-not-process-one"],
        },
    )

    status = inspect_process(tmp_path)

    assert status.running is False
    assert status.reason in {
        "pid_reused_identity_mismatch",
        "cannot_verify_process_identity",
    }
    assert stop_background(tmp_path).running is False
