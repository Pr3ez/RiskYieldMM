from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSIONED_VERIFIER = (
    ROOT
    / "scripts/tests/verify_raw_v8_step2_maximum_protocol_v2_"
    "all_case_candidate_v49f.py"
)


def test_a4_r475_v0_versioned_verifier_foundation_exists() -> None:
    assert VERSIONED_VERIFIER.is_file(), (
        "A4-R475-V0 versioned verifier foundation is missing"
    )
