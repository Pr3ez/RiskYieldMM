from __future__ import annotations

import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]

ROLE_PATHS = {
    "producer": ROOT
    / "scripts/tests/produce_raw_v8_step2_maximum_protocol_v2_all_case_candidate_v49f.py",
    "verifier": ROOT
    / "scripts/tests/verify_raw_v8_step2_maximum_protocol_v2_all_case_candidate_v49f.py",
    "runner": ROOT
    / "scripts/tests/run_raw_v8_step2_maximum_protocol_v2_all_case_campaign_v49f.py",
}


def test_versioned_all_case_producer_exists() -> None:
    assert ROLE_PATHS["producer"].is_file(), "A4-R475 versioned producer is missing"


def test_versioned_all_case_verifier_exists() -> None:
    assert ROLE_PATHS["verifier"].is_file(), "A4-R475 versioned verifier is missing"


def test_versioned_all_case_runner_exists() -> None:
    assert ROLE_PATHS["runner"].is_file(), "A4-R475 versioned runner is missing"
