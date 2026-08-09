from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_stage1_execution_control_matches_recorded_checkpoint() -> None:
    completed = subprocess.run(
        [sys.executable, "scripts/tests/check_stage1_execution_control.py"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "STAGE1_CONTROL_OK active_gate=S1-A3" in completed.stdout
    assert "formal_state=NO-GO" in completed.stdout
    assert "catalog_stale=false" in completed.stdout
