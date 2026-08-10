#!/usr/bin/env python3
"""Fail closed when the Stage 1 control ledger drifts from its recorded P0."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CONTROL_PATH = ROOT / "docs/research/stage1_execution_control_2026-08-08.md"
GENERATOR_PATH = (
    ROOT
    / "scripts/tests/generate_raw_v8_step2_maximum_protocol_v2_seed_catalog_v49f.py"
)
CATALOG_PATH = (
    ROOT / "scripts/tests/raw_v8_step2_maximum_protocol_v2_seed_catalog_v49f.json"
)
FINALIZER_PATH = (
    ROOT / "scripts/tests/finalize_raw_v8_step2_maximum_protocol_v2_v49f.py"
)
FINALIZER_TEST_PATH = (
    ROOT / "tests/test_raw_v8_step2_maximum_protocol_v2_finalizer_v49f.py"
)
FINALIZATION_MANIFEST_PATH = (
    ROOT
    / "scripts/tests/raw_v8_step2_maximum_protocol_v2_finalization_manifest_v49f.json"
)
FINALIZATION_MANIFEST_DOMAIN = "RiskYieldMMStep2FinalizationManifestV1V4_9F_RawV8"
CONSTRUCTIVE_BOUNDARY_PATH = (
    ROOT
    / "scripts/tests/raw_v8_step2_maximum_protocol_v2_constructive_boundary_v49f.json"
)
CONSTRUCTIVE_BOUNDARY_TEST_PATH = (
    ROOT / "tests/test_raw_v8_step2_maximum_protocol_v2_constructive_boundary_v49f.py"
)
IMPLEMENTATION_FAIL_FIRST_TEST_PATH = (
    ROOT
    / "tests/test_raw_v8_step2_maximum_protocol_v2_implementation_fail_first_v49f.py"
)
INDEPENDENT_VERIFIER_PATH = (
    ROOT / "scripts/tests/verify_raw_v8_step2_maximum_protocol_v2_candidate_v49f.py"
)
INDEPENDENT_VERIFIER_TEST_PATH = (
    ROOT / "tests/test_raw_v8_step2_maximum_protocol_v2_independent_verifier_v49f.py"
)
INDEPENDENT_VERIFIER_EXPANSION_V0_TEST_PATH = (
    ROOT
    / "tests/test_raw_v8_step2_maximum_protocol_v2_independent_verifier_expansion_v49f.py"
)
INDEPENDENT_VERIFIER_EXPANSION_V0_ACCEPTANCE_PATH = (
    ROOT
    / "docs/research/v4_9f_a2_raw_v8_step2_v2_"
    "independent_verifier_expansion_v0_acceptance_2026-08-10.md"
)
TYPED_RULE_RUNTIME_PATH = (
    ROOT
    / "scripts/tests/validate_raw_v8_step2_external_schema_v2_rule_runtime_v49f.py"
)
SEPARATE_PRODUCER_PATH = (
    ROOT / "scripts/tests/produce_raw_v8_step2_maximum_protocol_v2_candidate_v49f.py"
)
SEPARATE_PRODUCER_TEST_PATH = (
    ROOT / "tests/test_raw_v8_step2_maximum_protocol_v2_separate_producer_v49f.py"
)
SIX_CASE_QUALIFICATION_TEST_PATH = (
    ROOT
    / "tests/test_raw_v8_step2_maximum_protocol_v2_six_case_qualification_fail_first_v49f.py"
)
CASE435_ATTAINABILITY_ANALYZER_PATH = (
    ROOT
    / "scripts/tests/check_raw_v8_step2_maximum_protocol_v2_case435_attainability_v49f.py"
)
CASE435_ATTAINABILITY_TEST_PATH = (
    ROOT / "tests/test_raw_v8_step2_maximum_protocol_v2_case435_attainability_v49f.py"
)
PROFILE_ATTAINABILITY_SCOPE_ANALYZER_PATH = (
    ROOT
    / "scripts/tests/check_raw_v8_step2_maximum_protocol_v2_profile_attainability_scope_v49f.py"
)
PROFILE_ATTAINABILITY_SCOPE_TEST_PATH = (
    ROOT
    / "tests/test_raw_v8_step2_maximum_protocol_v2_profile_attainability_scope_v49f.py"
)
PROFILE_ATTAINABILITY_SCOPE_DESIGN_PATH = (
    ROOT
    / "docs/research/v4_9f_a2_raw_v8_step2_v2_profile_attainability_scope_and_correction_design_2026-08-10.md"
)
CASE435_DEPENDENCY_CLOSURE_ANALYZER_PATH = (
    ROOT
    / "scripts/tests/check_raw_v8_step2_maximum_protocol_v2_case435_dependency_closure_v49f.py"
)
CASE435_DEPENDENCY_CLOSURE_TEST_PATH = (
    ROOT
    / "tests/test_raw_v8_step2_maximum_protocol_v2_case435_dependency_closure_v49f.py"
)
CASE435_DEPENDENCY_CLOSURE_ACCEPTANCE_PATH = (
    ROOT
    / "docs/research/v4_9f_a2_raw_v8_step2_v2_case435_dependency_closure_acceptance_2026-08-10.md"
)
CASE435_UPPER_SOLVER_PATH = (
    ROOT / "scripts/tests/solve_raw_v8_step2_maximum_protocol_v2_case435_upper_v49f.py"
)
CASE435_UPPER_CERTIFICATE_CHECKER_PATH = (
    ROOT
    / "scripts/tests/check_raw_v8_step2_maximum_protocol_v2_case435_upper_certificate_v49f.py"
)
CASE435_UPPER_CERTIFICATE_TEST_PATH = (
    ROOT
    / "tests/test_raw_v8_step2_maximum_protocol_v2_case435_upper_certificate_v49f.py"
)
CASE435_UPPER_ACCEPTANCE_PATH = (
    ROOT
    / "docs/research/v4_9f_a2_raw_v8_step2_v2_case435_exact_upper_acceptance_2026-08-10.md"
)
CASE435_ATTAINER_CONSTRUCTOR_PATH = (
    ROOT
    / "scripts/tests/construct_raw_v8_step2_maximum_protocol_v2_case435_attainer_v49f.py"
)
CASE435_ATTAINER_CERTIFICATE_CHECKER_PATH = (
    ROOT / "scripts/tests/check_raw_v8_step2_maximum_protocol_v2_"
    "case435_attainer_certificate_v49f.py"
)
CASE435_ATTAINER_CERTIFICATE_TEST_PATH = (
    ROOT / "tests/test_raw_v8_step2_maximum_protocol_v2_"
    "case435_attainer_certificate_v49f.py"
)
CASE435_ATTAINER_ACCEPTANCE_PATH = (
    ROOT / "docs/research/v4_9f_a2_raw_v8_step2_v2_"
    "case435_independent_attainer_acceptance_2026-08-10.md"
)
CASE435_EXACTNESS_JOIN_PATH = (
    ROOT / "scripts/tests/join_raw_v8_step2_maximum_protocol_v2_"
    "case435_exactness_v49f.py"
)
CASE435_EXACTNESS_CERTIFICATE_CHECKER_PATH = (
    ROOT / "scripts/tests/check_raw_v8_step2_maximum_protocol_v2_"
    "case435_exactness_certificate_v49f.py"
)
CASE435_EXACTNESS_JOIN_TEST_PATH = (
    ROOT / "tests/test_raw_v8_step2_maximum_protocol_v2_case435_exactness_join_v49f.py"
)
CASE435_EXACTNESS_JOIN_ACCEPTANCE_PATH = (
    ROOT / "docs/research/v4_9f_a2_raw_v8_step2_v2_"
    "case435_exactness_join_acceptance_2026-08-10.md"
)
CASE435_AUTHORITY_MIGRATOR_PATH = (
    ROOT / "scripts/tests/migrate_raw_v8_step2_maximum_protocol_v2_"
    "case435_authorities_v49f.py"
)
CASE435_AUTHORITY_TRANSITION_CHECKER_PATH = (
    ROOT / "scripts/tests/check_raw_v8_step2_maximum_protocol_v2_"
    "case435_authority_transition_v49f.py"
)
CASE435_AUTHORITY_TRANSITION_TEST_PATH = (
    ROOT / "tests/test_raw_v8_step2_maximum_protocol_v2_"
    "case435_authority_transition_v49f.py"
)
CASE435_SEED_DELTA_PATH = (
    ROOT / "scripts/tests/raw_v8_step2_maximum_protocol_v2_"
    "case435_seed_delta_v49f.json"
)
CASE435_MANIFEST_DELTA_PATH = (
    ROOT / "scripts/tests/raw_v8_step2_maximum_protocol_v2_"
    "case435_manifest_delta_v49f.json"
)
CASE435_BOUNDARY_DELTA_PATH = (
    ROOT / "scripts/tests/raw_v8_step2_maximum_protocol_v2_"
    "case435_boundary_delta_v49f.json"
)
CASE435_TARGET_DELTA_PATH = (
    ROOT / "scripts/tests/raw_v8_step2_maximum_protocol_v2_"
    "case435_six_case_target_delta_v49f.json"
)
CASE435_AUTHORITY_TRANSITION_ACCEPTANCE_PATH = (
    ROOT / "docs/research/v4_9f_a2_raw_v8_step2_v2_"
    "case435_authority_transition_acceptance_2026-08-10.md"
)
PARENT_PILOT_RUNNER_PATH = (
    ROOT / "scripts/tests/run_raw_v8_step2_maximum_protocol_v2_pilot_v49f.py"
)
CONSTRUCTIVE_BOUNDARY_DOMAIN = (
    "RiskYieldMMStep2ConstructiveExecutionBoundaryV1V4_9F_RawV8"
)
F2_RESOURCE_LIMIT_CATALOG_DOMAIN = "RiskYieldMMStep2F2ResourceLimitCatalogV1V4_9F_RawV8"
S1_A2_AUTHORITY_ROLES = (
    "PREFLIGHT_CONTRACT",
    "PREFLIGHT_A",
    "PREFLIGHT_A_TEST",
    "PREFLIGHT_B",
    "PREFLIGHT_B_TEST",
    "PREFLIGHT_COMPARATOR",
    "PREFLIGHT_COMPARATOR_TEST",
)
CONTROL_PATTERN = re.compile(
    r"<!-- STAGE1_CONTROL_JSON_START\n(?P<payload>\{.*?\})\n"
    r"STAGE1_CONTROL_JSON_END -->",
    re.DOTALL,
)
ALLOWED_STATES = {"ACCEPTED", "ACTIVE", "READY", "WAITING", "HOLD", "REJECTED"}
ACTIVE_GATE_PATTERN = re.compile(
    r"<!-- STAGE1_ACTIVE_GATE: (?P<gate>S1-(?:[A-Z][0-9]+|X)) -->"
)


class ControlFailure(RuntimeError):
    """The current tree does not match the Stage 1 control ledger."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ControlFailure(message)


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _pretty_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            indent=2,
        )
        + "\n"
    ).encode("utf-8")


def _ordered_pretty_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=False,
            indent=2,
        )
        + "\n"
    ).encode("utf-8")


def _load_control() -> dict[str, Any]:
    text = CONTROL_PATH.read_text(encoding="utf-8")
    match = CONTROL_PATTERN.search(text)
    _require(match is not None, "machine-readable control block is missing")
    control = json.loads(match.group("payload"))
    _require(isinstance(control, dict), "control block must be an object")
    return control


def _validate_gate_graph(control: dict[str, Any]) -> None:
    gates = control.get("gate_states")
    _require(isinstance(gates, dict) and gates, "gate_states must be nonempty")
    active = []
    for gate_id, row in gates.items():
        _require(
            re.fullmatch(r"S1-(?:[A-Z][0-9]+|X)", gate_id) is not None,
            f"bad gate {gate_id}",
        )
        _require(isinstance(row, dict), f"{gate_id} row must be an object")
        _require(set(row) == {"depends_on", "state"}, f"{gate_id} members differ")
        state = row["state"]
        _require(state in ALLOWED_STATES, f"{gate_id} has unknown state {state}")
        if state == "ACTIVE":
            active.append(gate_id)
        dependencies = row["depends_on"]
        _require(isinstance(dependencies, list), f"{gate_id} dependencies differ")
        _require(
            len(dependencies) == len(set(dependencies)),
            f"{gate_id} duplicates a dependency",
        )
        for dependency in dependencies:
            _require(
                dependency in gates, f"{gate_id} has unknown dependency {dependency}"
            )
            _require(dependency != gate_id, f"{gate_id} depends on itself")

    _require(
        active == [control.get("active_gate")],
        "exactly one declared active gate is required",
    )

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(gate_id: str) -> None:
        _require(gate_id not in visiting, f"gate dependency cycle reaches {gate_id}")
        if gate_id in visited:
            return
        visiting.add(gate_id)
        for dependency in gates[gate_id]["depends_on"]:
            visit(dependency)
        visiting.remove(gate_id)
        visited.add(gate_id)

    for gate_id in gates:
        visit(gate_id)

    for gate_id, row in gates.items():
        if row["state"] in {"ACTIVE", "READY"}:
            for dependency in row["depends_on"]:
                _require(
                    gates[dependency]["state"] == "ACCEPTED",
                    f"{gate_id} is {row['state']} before {dependency} is accepted",
                )


def _load_generator() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "stage1_seed_generator", GENERATOR_PATH
    )
    _require(spec is not None and spec.loader is not None, "cannot load seed generator")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_case435_attainability_analyzer() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "stage1_case435_attainability_analyzer",
        CASE435_ATTAINABILITY_ANALYZER_PATH,
    )
    _require(
        spec is not None and spec.loader is not None,
        "cannot load case-435 attainability analyzer",
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_profile_attainability_scope_analyzer() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "stage1_profile_attainability_scope_analyzer",
        PROFILE_ATTAINABILITY_SCOPE_ANALYZER_PATH,
    )
    _require(
        spec is not None and spec.loader is not None,
        "cannot load profile-attainability scope analyzer",
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_case435_dependency_closure_analyzer() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "stage1_case435_dependency_closure_analyzer",
        CASE435_DEPENDENCY_CLOSURE_ANALYZER_PATH,
    )
    _require(
        spec is not None and spec.loader is not None,
        "cannot load case-435 dependency-closure analyzer",
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_case435_upper_solver() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "stage1_case435_upper_solver",
        CASE435_UPPER_SOLVER_PATH,
    )
    _require(
        spec is not None and spec.loader is not None,
        "cannot load case-435 exact-upper solver",
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_case435_upper_certificate_checker() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "stage1_case435_upper_certificate_checker",
        CASE435_UPPER_CERTIFICATE_CHECKER_PATH,
    )
    _require(
        spec is not None and spec.loader is not None,
        "cannot load case-435 upper-certificate checker",
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_case435_attainer_constructor() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "stage1_case435_attainer_constructor",
        CASE435_ATTAINER_CONSTRUCTOR_PATH,
    )
    _require(
        spec is not None and spec.loader is not None,
        "cannot load case-435 attainer constructor",
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_case435_attainer_certificate_checker() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "stage1_case435_attainer_certificate_checker",
        CASE435_ATTAINER_CERTIFICATE_CHECKER_PATH,
    )
    _require(
        spec is not None and spec.loader is not None,
        "cannot load case-435 attainer-certificate checker",
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_case435_exactness_join() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "stage1_case435_exactness_join",
        CASE435_EXACTNESS_JOIN_PATH,
    )
    _require(
        spec is not None and spec.loader is not None,
        "cannot load case-435 exactness join",
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_case435_exactness_certificate_checker() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "stage1_case435_exactness_certificate_checker",
        CASE435_EXACTNESS_CERTIFICATE_CHECKER_PATH,
    )
    _require(
        spec is not None and spec.loader is not None,
        "cannot load case-435 exactness-certificate checker",
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_case435_authority_transition_checker() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "stage1_case435_authority_transition_checker",
        CASE435_AUTHORITY_TRANSITION_CHECKER_PATH,
    )
    _require(
        spec is not None and spec.loader is not None,
        "cannot load case-435 authority-transition checker",
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _validate_navigation(active_gate: str) -> None:
    pointers = {
        ROOT / "README.md": "docs/research/stage1_execution_control_2026-08-08.md",
        ROOT / "docs/README.md": "research/stage1_execution_control_2026-08-08.md",
        ROOT / "docs/research/README.md": "stage1_execution_control_2026-08-08.md",
        ROOT
        / "docs/research/trading_prediction_system_diagnosis_and_redesign_2026-07-14.md": (
            "stage1_execution_control_2026-08-08.md"
        ),
    }
    for path, pointer in pointers.items():
        text = path.read_text(encoding="utf-8")
        _require(
            pointer in text,
            f"missing current pointer in {path}",
        )
        markers = ACTIVE_GATE_PATTERN.findall(text)
        _require(
            markers == [active_gate],
            f"active-gate navigation marker differs in {path}: {markers}",
        )


def _validate_s1_a2_snapshot(snapshot: dict[str, Any]) -> None:
    _require(
        set(snapshot)
        == {
            "comparison_payload_id",
            "comparison_raw_octets",
            "comparison_raw_sha256",
            "ordered_authority_records",
            "semantic_count_vector_sha256",
            "semantic_payload_id",
            "semantic_raw_octets",
            "semantic_raw_sha256",
        },
        "S1-A2 snapshot members differ",
    )
    records = snapshot["ordered_authority_records"]
    _require(isinstance(records, list), "S1-A2 authority records are missing")
    _require(
        [row.get("artifact_role") for row in records] == list(S1_A2_AUTHORITY_ROLES),
        "S1-A2 authority order differs",
    )
    paths: list[str] = []
    hashes: list[str] = []
    for position, row in enumerate(records, 1):
        _require(
            set(row)
            == {
                "artifact_position",
                "artifact_role",
                "raw_octets",
                "raw_sha256",
                "repository_relative_path",
            },
            f"S1-A2 authority {position} members differ",
        )
        _require(
            row["artifact_position"] == position,
            f"S1-A2 authority {position} position differs",
        )
        relative = row["repository_relative_path"]
        _require(
            isinstance(relative, str)
            and relative
            and not relative.startswith("/")
            and ".." not in Path(relative).parts,
            f"S1-A2 authority {position} path is invalid",
        )
        path = ROOT / relative
        _require(
            path.is_file() and not path.is_symlink(),
            f"S1-A2 authority {position} is not a regular file",
        )
        raw = path.read_bytes()
        _require(
            len(raw) == row["raw_octets"],
            f"S1-A2 authority {position} size drifted",
        )
        _require(
            _sha256(raw) == row["raw_sha256"],
            f"S1-A2 authority {position} hash drifted",
        )
        paths.append(relative)
        hashes.append(row["raw_sha256"])
    _require(len(paths) == len(set(paths)), "S1-A2 authority path is duplicated")
    _require(len(hashes) == len(set(hashes)), "S1-A2 authority hash is duplicated")

    for name in (
        "comparison_payload_id",
        "comparison_raw_sha256",
        "semantic_count_vector_sha256",
        "semantic_payload_id",
        "semantic_raw_sha256",
    ):
        value = snapshot[name]
        _require(
            isinstance(value, str)
            and len(value) == 64
            and all(character in "0123456789abcdef" for character in value),
            f"S1-A2 {name} is not a SHA-256 identity",
        )
    _require(
        snapshot["comparison_raw_octets"] == 1_206,
        "S1-A2 comparison size differs",
    )
    _require(
        snapshot["semantic_raw_octets"] == 1_702_217,
        "S1-A2 semantic size differs",
    )


def _validate_s1_a3_snapshot(
    snapshot: dict[str, Any], s1_a2_snapshot: dict[str, Any]
) -> None:
    _require(
        set(snapshot)
        == {
            "comparison_payload_id",
            "finalization_manifest_id",
            "finalization_manifest_raw_octets",
            "finalization_manifest_raw_sha256",
            "finalizer_raw_octets",
            "finalizer_raw_sha256",
            "finalizer_test_raw_octets",
            "finalizer_test_raw_sha256",
            "ordered_f2_limit_record_count",
            "semantic_count_vector_sha256",
            "semantic_payload_id",
        },
        "S1-A3 snapshot members differ",
    )
    artifacts = (
        (
            "finalizer",
            FINALIZER_PATH,
            snapshot["finalizer_raw_octets"],
            snapshot["finalizer_raw_sha256"],
        ),
        (
            "finalizer test",
            FINALIZER_TEST_PATH,
            snapshot["finalizer_test_raw_octets"],
            snapshot["finalizer_test_raw_sha256"],
        ),
        (
            "finalization manifest",
            FINALIZATION_MANIFEST_PATH,
            snapshot["finalization_manifest_raw_octets"],
            snapshot["finalization_manifest_raw_sha256"],
        ),
    )
    for label, path, expected_octets, expected_sha256 in artifacts:
        _require(path.is_file() and not path.is_symlink(), f"S1-A3 {label} is absent")
        raw = path.read_bytes()
        _require(len(raw) == expected_octets, f"S1-A3 {label} size drifted")
        _require(_sha256(raw) == expected_sha256, f"S1-A3 {label} hash drifted")

    manifest_raw = FINALIZATION_MANIFEST_PATH.read_bytes()
    manifest = json.loads(manifest_raw)
    _require(isinstance(manifest, dict), "S1-A3 manifest root differs")
    _require(
        manifest_raw == _pretty_bytes(manifest),
        "S1-A3 manifest is not canonical pretty JSON",
    )
    expected_root = {
        "canonicalization_version",
        "comparison_evidence",
        "finalization_manifest_id",
        "finalization_manifest_version",
        "finalization_status",
        "ordered_f2_limit_records",
        "ordered_implementation_authorities",
        "preflight_contract_authority",
        "protocol_counting_semantics_id",
        "protocol_version",
        "seed_authority",
        "semantic_evidence",
    }
    _require(set(manifest) == expected_root, "S1-A3 manifest members differ")
    _require(
        manifest["finalization_status"] == "FINAL_V2_F2_FROZEN",
        "S1-A3 manifest status differs",
    )
    identity_payload = {
        name: value
        for name, value in manifest.items()
        if name != "finalization_manifest_id"
    }
    identity = _sha256(
        _canonical_bytes(
            {"domain": FINALIZATION_MANIFEST_DOMAIN, "payload": identity_payload}
        )
    )
    _require(
        manifest["finalization_manifest_id"]
        == snapshot["finalization_manifest_id"]
        == identity,
        "S1-A3 manifest identity differs",
    )

    semantic = manifest["semantic_evidence"]
    comparison = manifest["comparison_evidence"]
    _require(
        semantic["semantic_payload_id"]
        == snapshot["semantic_payload_id"]
        == s1_a2_snapshot["semantic_payload_id"],
        "S1-A3 semantic payload identity differs",
    )
    _require(
        semantic["semantic_count_vector_sha256"]
        == snapshot["semantic_count_vector_sha256"]
        == s1_a2_snapshot["semantic_count_vector_sha256"],
        "S1-A3 semantic count-vector identity differs",
    )
    _require(
        comparison["comparison_payload_id"]
        == snapshot["comparison_payload_id"]
        == s1_a2_snapshot["comparison_payload_id"],
        "S1-A3 comparison identity differs",
    )
    for name in (
        "semantic_payload_bytes_equal",
        "all_475_case_records_equal",
        "all_18_metric_summaries_equal",
        "all_resource_limits_satisfied",
    ):
        _require(comparison[name] is True, f"S1-A3 comparison flag {name} differs")

    authorities = {
        row["implementation_label"]: row
        for row in manifest["ordered_implementation_authorities"]
    }
    a2_authorities = {
        row["artifact_role"]: row for row in s1_a2_snapshot["ordered_authority_records"]
    }
    _require(
        [
            row["implementation_label"]
            for row in manifest["ordered_implementation_authorities"]
        ]
        == ["A", "B", "COMPARATOR"],
        "S1-A3 implementation order differs",
    )
    for label, role in (
        ("A", "PREFLIGHT_A"),
        ("B", "PREFLIGHT_B"),
        ("COMPARATOR", "PREFLIGHT_COMPARATOR"),
    ):
        _require(
            authorities[label]["raw_sha256"] == a2_authorities[role]["raw_sha256"],
            f"S1-A3 {label} source seal differs",
        )

    f2_records = manifest["ordered_f2_limit_records"]
    _require(
        isinstance(f2_records, list)
        and len(f2_records) == snapshot["ordered_f2_limit_record_count"] == 18,
        "S1-A3 F2 record count differs",
    )
    for position, row in enumerate(f2_records, 1):
        _require(row["metric_position"] == position, f"S1-A3 F2 {position} order")
        integer_names = (
            "required_per_case",
            "per_case_rounding_unit",
            "f2_per_case",
            "per_case_f0_ceiling",
            "required_full_run",
            "full_run_rounding_unit",
            "f2_full_run",
            "full_run_f0_ceiling",
        )
        _require(
            all(
                isinstance(row[name], int)
                and not isinstance(row[name], bool)
                and row[name] >= 0
                for name in integer_names
            ),
            f"S1-A3 F2 {position} integer domain differs",
        )
        per_unit = row["per_case_rounding_unit"]
        full_unit = row["full_run_rounding_unit"]
        _require(per_unit > 0 and full_unit > 0, f"S1-A3 F2 {position} zero unit")
        expected_per = row["required_per_case"] + (
            (per_unit - (row["required_per_case"] % per_unit)) % per_unit
        )
        expected_full = row["required_full_run"] + (
            (full_unit - (row["required_full_run"] % full_unit)) % full_unit
        )
        _require(
            row["f2_per_case"] == expected_per
            and row["required_per_case"]
            <= row["f2_per_case"]
            <= row["per_case_f0_ceiling"],
            f"S1-A3 F2 {position} per-case derivation differs",
        )
        _require(
            row["f2_full_run"] == expected_full
            and row["required_full_run"]
            <= row["f2_full_run"]
            <= row["full_run_f0_ceiling"],
            f"S1-A3 F2 {position} full-run derivation differs",
        )


def _validate_s1_a4_boundary_snapshot(
    snapshot: dict[str, Any], s1_a3_snapshot: dict[str, Any]
) -> None:
    _require(
        set(snapshot)
        == {
            "boundary_raw_octets",
            "boundary_raw_sha256",
            "boundary_test_raw_octets",
            "boundary_test_raw_sha256",
            "constructive_boundary_id",
            "f2_resource_limit_catalog_id",
            "focused_passed",
            "legacy_v1_bootstrap_raw_octets",
            "legacy_v1_bootstrap_raw_sha256",
            "maximum_protocol_sha256",
            "ordered_pilot_case_positions",
        },
        "S1-A4 boundary snapshot members differ",
    )
    artifacts = (
        (
            "constructive boundary",
            CONSTRUCTIVE_BOUNDARY_PATH,
            snapshot["boundary_raw_octets"],
            snapshot["boundary_raw_sha256"],
        ),
        (
            "constructive boundary test",
            CONSTRUCTIVE_BOUNDARY_TEST_PATH,
            snapshot["boundary_test_raw_octets"],
            snapshot["boundary_test_raw_sha256"],
        ),
    )
    for label, path, expected_octets, expected_sha256 in artifacts:
        _require(path.is_file() and not path.is_symlink(), f"S1-A4 {label} is absent")
        raw = path.read_bytes()
        _require(len(raw) == expected_octets, f"S1-A4 {label} size drifted")
        _require(_sha256(raw) == expected_sha256, f"S1-A4 {label} hash drifted")

    raw = CONSTRUCTIVE_BOUNDARY_PATH.read_bytes()
    boundary = json.loads(raw)
    _require(isinstance(boundary, dict), "S1-A4 boundary root differs")
    _require(
        raw == _ordered_pretty_bytes(boundary),
        "S1-A4 boundary physical encoding differs",
    )
    expected_root_order = [
        "boundary_version",
        "canonicalization_version",
        "measurement_schema_version",
        "protocol_version",
        "boundary_status",
        "authority_contract",
        "implementation_role_contract",
        "candidate_bundle_contract",
        "verifier_output_contract",
        "pilot_contract",
        "resource_enforcement_contract",
        "filesystem_contract",
        "independence_contract",
        "legacy_v1_exclusion_contract",
        "constructive_boundary_id",
    ]
    _require(
        list(boundary) == expected_root_order,
        "S1-A4 boundary root order differs",
    )
    _require(
        boundary["boundary_status"] == "A4_B0_V2_ONLY_BOUNDARY_FROZEN",
        "S1-A4 boundary status differs",
    )
    identity_payload = {
        name: value
        for name, value in boundary.items()
        if name != "constructive_boundary_id"
    }
    identity = _sha256(
        _canonical_bytes(
            {"domain": CONSTRUCTIVE_BOUNDARY_DOMAIN, "payload": identity_payload}
        )
    )
    _require(
        boundary["constructive_boundary_id"]
        == snapshot["constructive_boundary_id"]
        == identity,
        "S1-A4 constructive boundary identity differs",
    )

    authority = boundary["authority_contract"]
    manifest_authority = authority["finalization_manifest_authority"]
    _require(
        manifest_authority["finalization_manifest_id"]
        == s1_a3_snapshot["finalization_manifest_id"],
        "S1-A4 finalization manifest identity differs",
    )
    _require(
        manifest_authority["raw_sha256"]
        == snapshot["maximum_protocol_sha256"]
        == s1_a3_snapshot["finalization_manifest_raw_sha256"],
        "S1-A4 maximum-protocol physical binding differs",
    )
    _require(
        authority["downstream_field_binding_rules"]["maximum_protocol_sha256"]
        == "FINALIZATION_MANIFEST_AUTHORITY_RAW_SHA256",
        "S1-A4 downstream maximum-protocol mapping differs",
    )

    manifest = json.loads(FINALIZATION_MANIFEST_PATH.read_bytes())
    f2_catalog = authority["f2_resource_limit_catalog"]
    f2_payload = {
        "catalog_version": f2_catalog["catalog_version"],
        "protocol_version": boundary["protocol_version"],
        "seed_catalog_id": authority["seed_authority"]["seed_catalog_id"],
        "finalization_manifest_id": manifest["finalization_manifest_id"],
        "ordered_f2_limit_records": manifest["ordered_f2_limit_records"],
    }
    f2_identity = _sha256(
        _canonical_bytes(
            {
                "domain": F2_RESOURCE_LIMIT_CATALOG_DOMAIN,
                "payload": f2_payload,
            }
        )
    )
    _require(
        f2_catalog["f2_resource_limit_catalog_id"]
        == snapshot["f2_resource_limit_catalog_id"]
        == f2_identity,
        "S1-A4 F2 resource-limit catalog identity differs",
    )

    pilot_positions = [
        row["case_position"]
        for row in boundary["pilot_contract"]["ordered_pilot_case_records"]
    ]
    _require(
        pilot_positions
        == snapshot["ordered_pilot_case_positions"]
        == [5, 24, 54, 69, 435, 475],
        "S1-A4 pilot case positions differ",
    )
    _require(snapshot["focused_passed"] == 28, "S1-A4 focused test count differs")

    legacy = boundary["legacy_v1_exclusion_contract"]["rejected_bootstrap_authority"]
    legacy_path = ROOT / legacy["repository_relative_path"]
    _require(
        legacy_path.is_file() and not legacy_path.is_symlink(),
        "S1-A4 legacy V1 bootstrap is absent",
    )
    legacy_raw = legacy_path.read_bytes()
    _require(
        len(legacy_raw)
        == legacy["raw_octets"]
        == snapshot["legacy_v1_bootstrap_raw_octets"],
        "S1-A4 legacy V1 bootstrap size drifted",
    )
    _require(
        _sha256(legacy_raw)
        == legacy["raw_sha256"]
        == snapshot["legacy_v1_bootstrap_raw_sha256"],
        "S1-A4 legacy V1 bootstrap hash drifted",
    )


def _validate_s1_a4_fail_first_snapshot(
    snapshot: dict[str, Any], boundary_snapshot: dict[str, Any]
) -> None:
    _require(
        set(snapshot)
        == {
            "constructive_boundary_id",
            "contract_hostile_passed",
            "fail_first_test_raw_octets",
            "fail_first_test_raw_sha256",
            "implementation_dependent_skipped",
            "implementation_paths_absent_at_acceptance",
            "intended_missing_path_failed",
            "next_subgate_at_acceptance",
            "ordered_failure_codes",
            "ordered_implementation_paths",
            "passing_selection_deselected",
            "unexpected_failed",
        },
        "S1-A4 fail-first snapshot members differ",
    )
    _require(
        IMPLEMENTATION_FAIL_FIRST_TEST_PATH.is_file()
        and not IMPLEMENTATION_FAIL_FIRST_TEST_PATH.is_symlink(),
        "S1-A4 fail-first test is absent",
    )
    raw = IMPLEMENTATION_FAIL_FIRST_TEST_PATH.read_bytes()
    _require(
        len(raw) == snapshot["fail_first_test_raw_octets"],
        "S1-A4 fail-first test size drifted",
    )
    _require(
        _sha256(raw) == snapshot["fail_first_test_raw_sha256"],
        "S1-A4 fail-first test hash drifted",
    )
    _require(
        snapshot["constructive_boundary_id"]
        == boundary_snapshot["constructive_boundary_id"],
        "S1-A4 fail-first boundary identity differs",
    )

    boundary = json.loads(CONSTRUCTIVE_BOUNDARY_PATH.read_bytes())
    role_rows = boundary["implementation_role_contract"]["ordered_role_records"]
    expected_paths = [row["repository_relative_path"] for row in role_rows]
    expected_codes = [
        "A4_T_INDEPENDENT_VERIFIER_MISSING",
        "A4_T_SEPARATE_PRODUCER_MISSING",
        "A4_T_PARENT_PILOT_RUNNER_MISSING",
    ]
    _require(
        snapshot["ordered_implementation_paths"] == expected_paths,
        "S1-A4 fail-first implementation paths differ",
    )
    _require(
        snapshot["ordered_failure_codes"] == expected_codes,
        "S1-A4 fail-first failure codes differ",
    )
    _require(
        snapshot["contract_hostile_passed"] == 50,
        "S1-A4 fail-first passing count differs",
    )
    _require(
        snapshot["implementation_dependent_skipped"] == 11,
        "S1-A4 fail-first skipped count differs",
    )
    _require(
        snapshot["intended_missing_path_failed"]
        == snapshot["passing_selection_deselected"]
        == 3,
        "S1-A4 fail-first missing-path count differs",
    )
    _require(snapshot["unexpected_failed"] == 0, "S1-A4 fail-first has failures")
    _require(
        snapshot["next_subgate_at_acceptance"] == "A4-V",
        "S1-A4 accepted fail-first next sub-gate differs",
    )
    _require(
        snapshot["implementation_paths_absent_at_acceptance"] is True,
        "S1-A4 fail-first acceptance absence state differs",
    )
    source = raw.decode("utf-8", errors="strict")
    for code, path, row in zip(expected_codes, expected_paths, role_rows, strict=True):
        _require(code in source, f"S1-A4 fail-first code is absent: {code}")
        _require(path in source, f"S1-A4 fail-first path is absent: {path}")
        _require(
            row["source_marker"] in source,
            f"S1-A4 fail-first source marker is absent: {path}",
        )
    for test_name in (
        "test_verifier_accepts_independent_legal_case5_attainer",
        "test_verifier_rejects_hostile_candidate_without_output",
        "test_producer_emits_only_the_legal_case5_candidate",
    ):
        _require(test_name in source, f"S1-A4 functional target is absent: {test_name}")


def _validate_s1_a4_verifier_snapshot(
    snapshot: dict[str, Any], boundary_snapshot: dict[str, Any]
) -> None:
    _require(
        set(snapshot)
        == {
            "a4_t_at_acceptance_intended_failed",
            "a4_t_at_acceptance_passed",
            "a4_t_at_acceptance_skipped",
            "accepted_case_position",
            "case5_expected_maximum_octets",
            "case5_resource_vector_sha256",
            "case5_stream_sha256",
            "constructive_boundary_id",
            "focused_passed",
            "next_subgate_at_acceptance",
            "ordered_remaining_failure_codes_at_acceptance",
            "ordered_remaining_implementation_paths_at_acceptance",
            "source_marker",
            "successor_paths_absent_at_acceptance",
            "verifier_raw_octets",
            "verifier_raw_sha256",
            "verifier_test_raw_octets",
            "verifier_test_raw_sha256",
        },
        "S1-A4 verifier snapshot members differ",
    )
    _require(
        snapshot["constructive_boundary_id"]
        == boundary_snapshot["constructive_boundary_id"],
        "S1-A4 verifier boundary identity differs",
    )
    _require(
        snapshot["verifier_raw_octets"] == 94_839,
        "S1-A4 verifier historical size drifted",
    )
    _require(
        snapshot["verifier_raw_sha256"]
        == "bd81e47b0c07dc82f28a8d02e536329446267290c4e0e41c6e5fb96fd5c356a7",
        "S1-A4 verifier hash drifted",
    )
    _require(
        INDEPENDENT_VERIFIER_TEST_PATH.is_file()
        and not INDEPENDENT_VERIFIER_TEST_PATH.is_symlink(),
        "S1-A4 verifier test is absent",
    )
    verifier_test_raw = INDEPENDENT_VERIFIER_TEST_PATH.read_bytes()
    _require(
        len(verifier_test_raw) == snapshot["verifier_test_raw_octets"],
        "S1-A4 verifier test size drifted",
    )
    _require(
        _sha256(verifier_test_raw) == snapshot["verifier_test_raw_sha256"],
        "S1-A4 verifier test hash drifted",
    )

    boundary = json.loads(CONSTRUCTIVE_BOUNDARY_PATH.read_bytes())
    roles = boundary["implementation_role_contract"]["ordered_role_records"]
    verifier_role = roles[0]
    _require(
        verifier_role["role_name"] == "INDEPENDENT_VERIFIER"
        and ROOT / verifier_role["repository_relative_path"]
        == INDEPENDENT_VERIFIER_PATH
        and verifier_role["source_marker"] == snapshot["source_marker"],
        "S1-A4 verifier role binding differs",
    )
    verifier_source = INDEPENDENT_VERIFIER_PATH.read_text(encoding="utf-8")
    _require(
        snapshot["source_marker"] in verifier_source,
        "S1-A4 verifier source marker is absent",
    )
    remaining_paths = [row["repository_relative_path"] for row in roles[1:]]
    remaining_codes = [
        "A4_T_SEPARATE_PRODUCER_MISSING",
        "A4_T_PARENT_PILOT_RUNNER_MISSING",
    ]
    _require(
        snapshot["ordered_remaining_implementation_paths_at_acceptance"]
        == remaining_paths,
        "S1-A4 verifier remaining implementation paths differ",
    )
    _require(
        snapshot["ordered_remaining_failure_codes_at_acceptance"] == remaining_codes,
        "S1-A4 verifier remaining failure codes differ",
    )
    _require(
        snapshot["successor_paths_absent_at_acceptance"] is True,
        "S1-A4 verifier historical successor state differs",
    )
    _require(
        snapshot["accepted_case_position"] == 5
        and snapshot["case5_expected_maximum_octets"] == 29,
        "S1-A4 verifier case-5 scope differs",
    )
    expected_vector = [
        1,
        3,
        4,
        8,
        8,
        0,
        4,
        2684,
        8104,
        10384,
        33573,
        0,
        0,
        0,
        3,
        3,
        3783,
        1359,
    ]
    _require(
        snapshot["case5_resource_vector_sha256"]
        == _sha256(_canonical_bytes(expected_vector)),
        "S1-A4 verifier case-5 resource vector differs",
    )
    _require(
        snapshot["case5_stream_sha256"]
        == "79375d5ecab2af215e9259524c7f16b41a2b5737cda7f5897a3cd6c272c0b314",
        "S1-A4 verifier case-5 stream differs",
    )
    _require(snapshot["focused_passed"] == 12, "S1-A4 verifier focused count differs")
    _require(
        snapshot["a4_t_at_acceptance_passed"] == 57
        and snapshot["a4_t_at_acceptance_skipped"] == 5
        and snapshot["a4_t_at_acceptance_intended_failed"] == 2,
        "S1-A4 verifier A4-T transition counts differ",
    )
    _require(
        snapshot["next_subgate_at_acceptance"] == "A4-P",
        "S1-A4 verifier next sub-gate differs",
    )


def _validate_s1_a4_producer_snapshot(
    snapshot: dict[str, Any],
    boundary_snapshot: dict[str, Any],
) -> None:
    _require(
        set(snapshot)
        == {
            "a4_t_current_intended_failed",
            "a4_t_current_passed",
            "a4_t_current_skipped",
            "a4_t_filtered_deselected",
            "a4_t_filtered_passed",
            "a4_t_filtered_skipped",
            "accepted_case_position",
            "candidate_raw_octets",
            "candidate_raw_sha256",
            "constructive_boundary_id",
            "constructive_candidate_id",
            "focused_passed",
            "next_subgate",
            "ordered_remaining_failure_codes",
            "ordered_remaining_implementation_paths",
            "producer_raw_octets",
            "producer_raw_sha256",
            "producer_test_raw_octets",
            "producer_test_raw_sha256",
            "source_marker",
            "verifier_regression_passed",
        },
        "S1-A4 producer snapshot members differ",
    )
    _require(
        snapshot["constructive_boundary_id"]
        == boundary_snapshot["constructive_boundary_id"],
        "S1-A4 producer boundary identity differs",
    )
    for label, path, octets, digest in (
        (
            "producer",
            SEPARATE_PRODUCER_PATH,
            snapshot["producer_raw_octets"],
            snapshot["producer_raw_sha256"],
        ),
        (
            "producer test",
            SEPARATE_PRODUCER_TEST_PATH,
            snapshot["producer_test_raw_octets"],
            snapshot["producer_test_raw_sha256"],
        ),
    ):
        _require(path.is_file() and not path.is_symlink(), f"S1-A4 {label} is absent")
        raw = path.read_bytes()
        _require(len(raw) == octets, f"S1-A4 {label} size drifted")
        _require(_sha256(raw) == digest, f"S1-A4 {label} hash drifted")

    boundary = json.loads(CONSTRUCTIVE_BOUNDARY_PATH.read_bytes())
    roles = boundary["implementation_role_contract"]["ordered_role_records"]
    producer_role = roles[1]
    _require(
        producer_role["role_name"] == "SEPARATE_PRODUCER"
        and ROOT / producer_role["repository_relative_path"] == SEPARATE_PRODUCER_PATH
        and producer_role["source_marker"] == snapshot["source_marker"],
        "S1-A4 producer role binding differs",
    )
    producer_source = SEPARATE_PRODUCER_PATH.read_text(encoding="utf-8")
    _require(
        snapshot["source_marker"] in producer_source,
        "S1-A4 producer source marker is absent",
    )
    _require(
        str(INDEPENDENT_VERIFIER_PATH.relative_to(ROOT)) not in producer_source,
        "S1-A4 producer references verifier source",
    )
    for forbidden in boundary["candidate_bundle_contract"][
        "forbidden_producer_claim_member_names"
    ]:
        _require(
            forbidden not in producer_source,
            f"S1-A4 producer contains verifier-owned field: {forbidden}",
        )
    verifier_stat = INDEPENDENT_VERIFIER_PATH.stat()
    producer_stat = SEPARATE_PRODUCER_PATH.stat()
    _require(
        (verifier_stat.st_dev, verifier_stat.st_ino)
        != (producer_stat.st_dev, producer_stat.st_ino),
        "S1-A4 verifier and producer share one file",
    )

    runner_role = roles[2]
    expected_remaining_paths = [runner_role["repository_relative_path"]]
    _require(
        snapshot["ordered_remaining_implementation_paths"] == expected_remaining_paths,
        "S1-A4 producer remaining implementation paths differ",
    )
    _require(
        snapshot["ordered_remaining_failure_codes"]
        == ["A4_T_PARENT_PILOT_RUNNER_MISSING"],
        "S1-A4 producer remaining failure codes differ",
    )
    _require(
        ROOT / runner_role["repository_relative_path"] == PARENT_PILOT_RUNNER_PATH
        and not PARENT_PILOT_RUNNER_PATH.exists(),
        "S1-A4 parent runner must remain absent",
    )

    seed = json.loads(CATALOG_PATH.read_bytes())
    manifest = json.loads(FINALIZATION_MANIFEST_PATH.read_bytes())
    case = next(
        row
        for row in seed["case_universe_catalog"]["ordered_case_bindings"]
        if row["case_position"] == 5
    )
    plan = next(
        row
        for row in seed["logical_plan_recipe_catalog"][
            "ordered_logical_count_plan_records"
        ]
        if row["case_position"] == 5
    )
    schema = boundary["candidate_bundle_contract"]["candidate_envelope_schema"]
    candidate: dict[str, Any] = {
        "candidate_version": schema["version_literal"],
        "canonicalization_version": boundary["canonicalization_version"],
        "measurement_schema_version": boundary["measurement_schema_version"],
        "protocol_version": boundary["protocol_version"],
        "seed_catalog_id": seed["seed_catalog_id"],
        "finalization_manifest_id": manifest["finalization_manifest_id"],
        "case_position": 5,
        "case_kind": case["case_kind"],
        "case_binding": case["case_binding"],
        "logical_count_plan_id": plan["logical_count_plan_id"],
        "candidate_payload": {
            "candidate_kind": "MAXIMUM_WITNESS_CONTEXT",
            "witness_record": {"kind": "BOOL", "value": False},
            "scope_witness_context": None,
            "ordered_context_object_entries": [],
        },
    }
    identity_payload = {
        name: candidate[name] for name in schema["ordered_member_names"][:-1]
    }
    candidate["constructive_candidate_id"] = _sha256(
        _canonical_bytes(
            {"domain": schema["identity_domain"], "payload": identity_payload}
        )
    )
    candidate_raw = _pretty_bytes(candidate)
    _require(
        snapshot["accepted_case_position"] == 5,
        "S1-A4 producer accepted case differs",
    )
    _require(
        snapshot["constructive_candidate_id"] == candidate["constructive_candidate_id"],
        "S1-A4 producer candidate identity differs",
    )
    _require(
        snapshot["candidate_raw_octets"] == len(candidate_raw),
        "S1-A4 producer candidate size differs",
    )
    _require(
        snapshot["candidate_raw_sha256"] == _sha256(candidate_raw),
        "S1-A4 producer candidate hash differs",
    )
    _require(snapshot["focused_passed"] == 20, "S1-A4 producer focused count differs")
    _require(
        snapshot["verifier_regression_passed"] == 12,
        "S1-A4 producer verifier regression count differs",
    )
    _require(
        snapshot["a4_t_current_passed"] == 61
        and snapshot["a4_t_current_skipped"] == 2
        and snapshot["a4_t_current_intended_failed"] == 1,
        "S1-A4 producer A4-T transition counts differ",
    )
    _require(
        snapshot["a4_t_filtered_passed"] == 59
        and snapshot["a4_t_filtered_skipped"] == 2
        and snapshot["a4_t_filtered_deselected"] == 3,
        "S1-A4 producer filtered A4-T counts differ",
    )
    _require(
        snapshot["next_subgate"] == "A4-P6", "S1-A4 producer next sub-gate differs"
    )
    test_source = SEPARATE_PRODUCER_TEST_PATH.read_text(encoding="utf-8")
    for test_name in (
        "test_producer_emits_exact_closed_case5_bundle",
        "test_independent_verifier_accepts_producer_bytes_without_mutating_them",
        "test_producer_rejects_authority_substitution_and_link_aliases",
    ):
        _require(
            test_name in test_source, f"S1-A4 producer test is absent: {test_name}"
        )


def _validate_s1_a4_six_case_target_snapshot(
    snapshot: dict[str, Any],
    boundary_snapshot: dict[str, Any],
    producer_snapshot: dict[str, Any],
) -> None:
    _require(
        set(snapshot)
        == {
            "accepted_control_case_position",
            "constructive_boundary_id",
            "contract_and_case5_control_passed",
            "existing_pair_unmodified_at_acceptance",
            "fail_first_test_raw_octets",
            "fail_first_test_raw_sha256",
            "implementation_dependent_skipped",
            "intended_failed",
            "next_subgate",
            "ordered_case_positions",
            "ordered_failure_codes",
            "ordered_remaining_pipeline_case_positions",
            "passing_selection_deselected",
            "runner_absent_at_acceptance",
            "runner_path",
            "unexpected_failed",
        },
        "S1-A4 six-case target snapshot members differ",
    )
    _require(
        snapshot["constructive_boundary_id"]
        == boundary_snapshot["constructive_boundary_id"],
        "S1-A4 six-case target boundary identity differs",
    )
    _require(
        SIX_CASE_QUALIFICATION_TEST_PATH.is_file()
        and not SIX_CASE_QUALIFICATION_TEST_PATH.is_symlink(),
        "S1-A4 six-case target is absent",
    )
    raw = SIX_CASE_QUALIFICATION_TEST_PATH.read_bytes()
    _require(
        len(raw) == snapshot["fail_first_test_raw_octets"],
        "S1-A4 six-case target size drifted",
    )
    _require(
        _sha256(raw) == snapshot["fail_first_test_raw_sha256"],
        "S1-A4 six-case target hash drifted",
    )

    boundary = json.loads(CONSTRUCTIVE_BOUNDARY_PATH.read_bytes())
    case_positions = [
        row["case_position"]
        for row in boundary["pilot_contract"]["ordered_pilot_case_records"]
    ]
    _require(
        snapshot["ordered_case_positions"]
        == case_positions
        == [5, 24, 54, 69, 435, 475],
        "S1-A4 six-case target case order differs",
    )
    _require(
        snapshot["accepted_control_case_position"]
        == producer_snapshot["accepted_case_position"]
        == 5,
        "S1-A4 six-case target control case differs",
    )
    remaining = case_positions[1:]
    _require(
        snapshot["ordered_remaining_pipeline_case_positions"] == remaining,
        "S1-A4 six-case target remaining case order differs",
    )
    expected_codes = [
        *(f"A4_P6_CASE_{position}_PRODUCER_NOT_QUALIFIED" for position in remaining),
        "A4_P6_PARENT_RUNNER_MISSING",
    ]
    _require(
        snapshot["ordered_failure_codes"] == expected_codes,
        "S1-A4 six-case target failure codes differ",
    )
    _require(
        snapshot["contract_and_case5_control_passed"] == 13
        and snapshot["implementation_dependent_skipped"] == 2
        and snapshot["intended_failed"] == 6
        and snapshot["passing_selection_deselected"] == 6
        and snapshot["unexpected_failed"] == 0,
        "S1-A4 six-case target test counts differ",
    )
    runner_relative = str(PARENT_PILOT_RUNNER_PATH.relative_to(ROOT))
    _require(
        snapshot["runner_path"] == runner_relative,
        "S1-A4 six-case target runner path differs",
    )
    _require(
        snapshot["runner_absent_at_acceptance"] is True
        and not PARENT_PILOT_RUNNER_PATH.exists(),
        "S1-A4 six-case target runner acceptance state differs",
    )
    _require(
        snapshot["existing_pair_unmodified_at_acceptance"] is True,
        "S1-A4 six-case target existing-pair state differs",
    )
    _require(
        snapshot["next_subgate"] == "A4-P6-V",
        "S1-A4 six-case target next sub-gate differs",
    )

    source = raw.decode("utf-8", errors="strict")
    for test_name in (
        "test_f2_limits_are_exact_immutable_and_complete",
        "test_candidate_oracle_rejects_hostile_resealed_fixtures",
        "test_case5_pipeline_control_remains_exact_deterministic_and_immutable",
        "test_remaining_pilot_pipeline_is_exact_deterministic_and_candidate_immutable",
        "test_parent_runner_emits_exact_two_run_all_or_nothing_pilot",
    ):
        _require(
            test_name in source,
            f"S1-A4 six-case qualification target is absent: {test_name}",
        )


def _validate_s1_a4_case435_attainability_falsification_snapshot(
    snapshot: dict[str, Any],
    six_case_snapshot: dict[str, Any],
    seed_snapshot: dict[str, Any],
) -> None:
    report_members = {
        "analysis_version",
        "attainability_analysis_id",
        "case_position",
        "constraint_scope_profile_id",
        "constructed_superset_canonical_sha256",
        "context_structural_superset_canonical_octets",
        "derived_legal_domain_superset_upper_bound_octets",
        "field_array_syntax_octets",
        "field_superset_upper_bound_sum_octets",
        "inventory_raw_sha256",
        "logical_count_plan_id",
        "measured_sequence_ordinal",
        "observation_fixed_nonfield_octets",
        "ordered_field_superset_bound_vector_sha256",
        "p2_structural_upper_bound_octets",
        "p3_equality_possible",
        "p3_unattainable_gap_octets",
        "registry_raw_sha256",
        "seed_raw_sha256",
        "target_field_count",
        "target_type_name",
    }
    control_members = {
        "analyzer_raw_octets",
        "analyzer_raw_sha256",
        "analyzer_test_raw_octets",
        "analyzer_test_raw_sha256",
        "correction_subgate",
        "verifier_expansion_state",
    }
    _require(
        set(snapshot) == report_members | control_members,
        "S1-A4 case-435 falsification snapshot members differ",
    )
    for label, path, octet_member, hash_member in (
        (
            "attainability analyzer",
            CASE435_ATTAINABILITY_ANALYZER_PATH,
            "analyzer_raw_octets",
            "analyzer_raw_sha256",
        ),
        (
            "attainability test",
            CASE435_ATTAINABILITY_TEST_PATH,
            "analyzer_test_raw_octets",
            "analyzer_test_raw_sha256",
        ),
    ):
        _require(
            path.is_file() and not path.is_symlink(),
            f"S1-A4 case-435 {label} is absent",
        )
        raw = path.read_bytes()
        _require(
            len(raw) == snapshot[octet_member],
            f"S1-A4 case-435 {label} size drifted",
        )
        _require(
            _sha256(raw) == snapshot[hash_member],
            f"S1-A4 case-435 {label} hash drifted",
        )

    analyzer = _load_case435_attainability_analyzer()
    actual_report = analyzer.analyze(ROOT)
    expected_report = {name: snapshot[name] for name in report_members}
    _require(
        actual_report == expected_report,
        "S1-A4 case-435 attainability report drifted",
    )
    _require(
        snapshot["case_position"]
        in six_case_snapshot["ordered_remaining_pipeline_case_positions"],
        "S1-A4 case-435 falsification is outside the frozen pilot",
    )
    _require(
        snapshot["seed_raw_sha256"] == seed_snapshot["catalog_sha256"],
        "S1-A4 case-435 falsification seed identity differs",
    )
    _require(
        snapshot["field_superset_upper_bound_sum_octets"]
        + snapshot["field_array_syntax_octets"]
        + snapshot["observation_fixed_nonfield_octets"]
        == snapshot["derived_legal_domain_superset_upper_bound_octets"],
        "S1-A4 case-435 falsification decomposition differs",
    )
    _require(
        snapshot["derived_legal_domain_superset_upper_bound_octets"]
        + snapshot["p3_unattainable_gap_octets"]
        == snapshot["p2_structural_upper_bound_octets"],
        "S1-A4 case-435 falsification gap differs",
    )
    _require(
        snapshot["p3_equality_possible"] is False
        and snapshot["p3_unattainable_gap_octets"] == 1_234,
        "S1-A4 case-435 P3 falsification differs",
    )
    _require(
        snapshot["correction_subgate"] == "A4-P6-C435"
        and snapshot["verifier_expansion_state"] == "HOLD",
        "S1-A4 case-435 correction disposition differs",
    )
    test_source = CASE435_ATTAINABILITY_TEST_PATH.read_text(encoding="utf-8")
    for test_name in (
        "test_case435_authority_complete_superset_falsifies_frozen_p3_endpoint",
        "test_case435_checker_is_independent_of_producer_verifier_and_legacy_v1",
        "test_case435_falsification_is_stronger_than_a_failed_candidate_search",
    ):
        _require(
            test_name in test_source,
            f"S1-A4 case-435 attainability test is absent: {test_name}",
        )


def _validate_s1_a4_profile_attainability_scope_snapshot(
    snapshot: dict[str, Any],
    case435_snapshot: dict[str, Any],
    seed_snapshot: dict[str, Any],
) -> None:
    report_members = {
        "affected_case_position_vector_sha256",
        "affected_profile_id_vector_sha256",
        "affected_profile_record_vector_sha256",
        "affected_program_id_vector_sha256",
        "affected_publication_case_maximum",
        "affected_publication_case_minimum",
        "application_aware_exact_program_count",
        "application_aware_exact_scope_case_count",
        "audit_version",
        "case435_is_affected",
        "current_catalog_satisfies_application_aware_exactness",
        "exact_control_case_position",
        "inventory_raw_sha256",
        "logical_plan_recipe_catalog_id",
        "p1_p3_exact_equality_program_count",
        "profile_attainability_scope_audit_id",
        "profile_program_count",
        "profile_scope_case_count",
        "required_disposition",
        "seed_catalog_id",
        "seed_raw_sha256",
        "selected_correction_contract_id",
        "structural_superset_application_invocation_count",
        "structural_superset_cross_rule_evaluation_count",
        "structural_superset_deleted_cross_application_count",
        "structural_superset_direct_cross_expression_node_count",
        "structural_superset_program_count",
        "structural_superset_scope_case_count",
        "structural_superset_selector_absent_scope_case_count",
        "structural_superset_selector_present_scope_case_count",
    }
    control_members = {
        "analyzer_raw_octets",
        "analyzer_raw_sha256",
        "analyzer_test_raw_octets",
        "analyzer_test_raw_sha256",
        "correction_subgate",
        "design_doc_raw_octets",
        "design_doc_raw_sha256",
        "focused_passed",
        "next_subgate",
        "verifier_expansion_state",
    }
    _require(
        set(snapshot) == report_members | control_members,
        "S1-A4 profile-attainability scope snapshot members differ",
    )
    for label, path, octet_member, hash_member in (
        (
            "profile-attainability analyzer",
            PROFILE_ATTAINABILITY_SCOPE_ANALYZER_PATH,
            "analyzer_raw_octets",
            "analyzer_raw_sha256",
        ),
        (
            "profile-attainability test",
            PROFILE_ATTAINABILITY_SCOPE_TEST_PATH,
            "analyzer_test_raw_octets",
            "analyzer_test_raw_sha256",
        ),
        (
            "profile-attainability design",
            PROFILE_ATTAINABILITY_SCOPE_DESIGN_PATH,
            "design_doc_raw_octets",
            "design_doc_raw_sha256",
        ),
    ):
        _require(
            path.is_file() and not path.is_symlink(),
            f"S1-A4 {label} is absent",
        )
        raw = path.read_bytes()
        _require(len(raw) == snapshot[octet_member], f"S1-A4 {label} size drifted")
        _require(_sha256(raw) == snapshot[hash_member], f"S1-A4 {label} hash drifted")

    analyzer = _load_profile_attainability_scope_analyzer()
    actual = analyzer.analyze(ROOT)
    expected = {name: snapshot[name] for name in report_members}
    _require(
        {name: actual[name] for name in report_members} == expected,
        "S1-A4 profile-attainability scope report drifted",
    )
    _require(
        actual["selected_correction_contract"] == analyzer.CORRECTION_CONTRACT,
        "S1-A4 profile-attainability correction contract drifted",
    )
    correction = actual["selected_correction_contract"]
    _require(
        correction["upper_bound_channel"]["result_kind"] == "PROVED_LEGAL_UPPER_BOUND"
        and correction["attainment_channel"]["result_kind"]
        == "INDEPENDENT_LEGAL_ATTAINMENT"
        and correction["exactness_join"]["success_result_kind"]
        == "EXACT_ATTAINED_MAXIMUM"
        and correction["exactness_join"]["superset_join_policy"] == "FORBIDDEN",
        "S1-A4 profile-attainability three-channel contract differs",
    )
    _require(
        snapshot["seed_raw_sha256"]
        == case435_snapshot["seed_raw_sha256"]
        == seed_snapshot["catalog_sha256"],
        "S1-A4 profile-attainability seed identity differs",
    )
    _require(
        snapshot["inventory_raw_sha256"] == case435_snapshot["inventory_raw_sha256"],
        "S1-A4 profile-attainability inventory identity differs",
    )
    _require(
        snapshot["profile_program_count"]
        == snapshot["p1_p3_exact_equality_program_count"]
        == 408
        and snapshot["profile_scope_case_count"] == 475,
        "S1-A4 profile-attainability universe differs",
    )
    _require(
        snapshot["structural_superset_program_count"] == 407
        and snapshot["structural_superset_scope_case_count"] == 474
        and snapshot["application_aware_exact_program_count"] == 1
        and snapshot["application_aware_exact_scope_case_count"] == 1
        and snapshot["exact_control_case_position"] == 69,
        "S1-A4 profile-attainability strategy census differs",
    )
    _require(
        snapshot["case435_is_affected"] is True
        and snapshot["current_catalog_satisfies_application_aware_exactness"] is False,
        "S1-A4 profile-attainability fail-first state differs",
    )
    _require(
        snapshot["structural_superset_selector_present_scope_case_count"]
        + snapshot["structural_superset_selector_absent_scope_case_count"]
        == snapshot["structural_superset_scope_case_count"],
        "S1-A4 profile-attainability selector partition differs",
    )
    _require(
        snapshot["correction_subgate"] == "A4-P6-C435-A"
        and snapshot["next_subgate"] == "A4-P6-C435-B"
        and snapshot["verifier_expansion_state"] == "HOLD"
        and snapshot["focused_passed"] == 10,
        "S1-A4 profile-attainability disposition differs",
    )
    test_source = PROFILE_ATTAINABILITY_SCOPE_TEST_PATH.read_text(encoding="utf-8")
    for test_name in (
        "test_scope_audit_freezes_every_structural_p2_equality_surface",
        "test_scope_audit_is_independent_of_generator_runtime_and_candidate_pair",
        "test_fail_first_exactness_boundary_rejects_current_catalog",
        "test_scope_audit_rejects_structural_p2_disguised_as_exact",
        "test_scope_audit_rejects_weakened_p1_p3_equality",
    ):
        _require(
            test_name in test_source,
            f"S1-A4 profile-attainability test is absent: {test_name}",
        )
    design = PROFILE_ATTAINABILITY_SCOPE_DESIGN_PATH.read_text(encoding="utf-8")
    for marker in (
        "A4-P6-C435-A",
        snapshot["profile_attainability_scope_audit_id"],
        snapshot["selected_correction_contract_id"],
        "A4-P6-C435-B",
    ):
        _require(
            marker in design,
            f"S1-A4 profile-attainability design marker absent: {marker}",
        )


def _validate_s1_a4_case435_dependency_closure_snapshot(
    snapshot: dict[str, Any],
    profile_scope_snapshot: dict[str, Any],
    case435_snapshot: dict[str, Any],
) -> None:
    report_members = {
        "a1_coupled_field_count",
        "audit_version",
        "case435_dependency_closure_audit_id",
        "complex_operator_count",
        "conditional_component_count",
        "conditional_factorization_proved",
        "correction_subgate",
        "dependency_closure_complete",
        "exact_case435_maximum_derived",
        "field_count",
        "legal_case435_attainer_constructed",
        "next_subgate",
        "ordinary_singleton_component_count",
        "required_disposition",
        "runtime_constant_closure_count",
        "runtime_function_closure_count",
        "schema_closure_intrinsic_rule_count",
        "schema_closure_type_count",
        "schema_closure_value_schema_count",
        "selected_cross_rule_count",
        "selected_rule_count",
        "selected_rule_expression_node_count",
        "unconditional_factorization_rejected",
        "verifier_expansion_state",
    }
    control_members = {
        "acceptance_doc_raw_octets",
        "acceptance_doc_raw_sha256",
        "analyzer_raw_octets",
        "analyzer_raw_sha256",
        "analyzer_test_raw_octets",
        "analyzer_test_raw_sha256",
        "case435_conditional_factorization_proof_id",
        "case435_dependency_manifest_id",
        "focused_passed",
        "microdomain_brute_force_legal_tuple_count",
        "microdomain_exact_maximum",
        "runtime_constant_ast_vector_sha256",
        "runtime_function_ast_vector_sha256",
    }
    _require(
        set(snapshot) == report_members | control_members,
        "S1-A4 case-435 dependency-closure snapshot members differ",
    )
    for label, path, octet_member, hash_member in (
        (
            "case-435 dependency-closure analyzer",
            CASE435_DEPENDENCY_CLOSURE_ANALYZER_PATH,
            "analyzer_raw_octets",
            "analyzer_raw_sha256",
        ),
        (
            "case-435 dependency-closure test",
            CASE435_DEPENDENCY_CLOSURE_TEST_PATH,
            "analyzer_test_raw_octets",
            "analyzer_test_raw_sha256",
        ),
        (
            "case-435 dependency-closure acceptance",
            CASE435_DEPENDENCY_CLOSURE_ACCEPTANCE_PATH,
            "acceptance_doc_raw_octets",
            "acceptance_doc_raw_sha256",
        ),
    ):
        _require(path.is_file() and not path.is_symlink(), f"S1-A4 {label} is absent")
        raw = path.read_bytes()
        _require(len(raw) == snapshot[octet_member], f"S1-A4 {label} size drifted")
        _require(_sha256(raw) == snapshot[hash_member], f"S1-A4 {label} hash drifted")

    analyzer = _load_case435_dependency_closure_analyzer()
    actual = analyzer.analyze(ROOT)
    expected = {name: snapshot[name] for name in report_members}
    _require(
        {name: actual[name] for name in report_members} == expected,
        "S1-A4 case-435 dependency-closure report drifted",
    )
    manifest = actual["case435_dependency_manifest"]
    proof = actual["case435_conditional_factorization_proof"]
    microdomain = actual["microdomain_factorization_check"]
    _require(
        manifest["case435_dependency_manifest_id"]
        == snapshot["case435_dependency_manifest_id"],
        "S1-A4 case-435 dependency-manifest identity differs",
    )
    _require(
        proof["case435_conditional_factorization_proof_id"]
        == snapshot["case435_conditional_factorization_proof_id"],
        "S1-A4 case-435 factorization-proof identity differs",
    )
    source_closure = manifest["runtime_source_closure"]
    _require(
        source_closure["function_ast_vector_sha256"]
        == snapshot["runtime_function_ast_vector_sha256"]
        and source_closure["constant_ast_vector_sha256"]
        == snapshot["runtime_constant_ast_vector_sha256"],
        "S1-A4 case-435 runtime AST closure differs",
    )
    _require(
        microdomain["brute_force_legal_tuple_count"]
        == snapshot["microdomain_brute_force_legal_tuple_count"]
        == 16
        and microdomain["brute_force_maximum"]
        == microdomain["factorized_maximum"]
        == snapshot["microdomain_exact_maximum"]
        == 29,
        "S1-A4 case-435 microdomain equivalence differs",
    )
    _require(
        manifest["global_codec_constraint"]["accepted_superset_analysis_id"]
        == case435_snapshot["attainability_analysis_id"],
        "S1-A4 case-435 dependency/falsification join differs",
    )
    _require(
        manifest["authority_sha256_by_path"][analyzer.SEED_RELATIVE_PATH]
        == profile_scope_snapshot["seed_raw_sha256"]
        and manifest["authority_sha256_by_path"][analyzer.INVENTORY_RELATIVE_PATH]
        == profile_scope_snapshot["inventory_raw_sha256"],
        "S1-A4 case-435 dependency/profile authority join differs",
    )
    _require(
        snapshot["correction_subgate"] == "A4-P6-C435-B"
        and snapshot["next_subgate"] == "A4-P6-C435-C1"
        and snapshot["focused_passed"] == 12
        and snapshot["dependency_closure_complete"] is True
        and snapshot["conditional_factorization_proved"] is True
        and snapshot["unconditional_factorization_rejected"] is True
        and snapshot["exact_case435_maximum_derived"] is False
        and snapshot["legal_case435_attainer_constructed"] is False
        and snapshot["verifier_expansion_state"] == "HOLD",
        "S1-A4 case-435 dependency-closure disposition differs",
    )
    test_source = CASE435_DEPENDENCY_CLOSURE_TEST_PATH.read_text(encoding="utf-8")
    for test_name in (
        "test_case435_dependency_closure_freezes_complete_conditional_graph",
        "test_case435_dependency_closure_independently_reconstructs_schedule_and_types",
        "test_case435_dependency_manifest_rejects_operator_contract_weakening",
        "test_case435_factorization_proof_rejects_premature_maximum_claim",
        "test_case435_dependency_closure_rejects_runtime_source_drift",
    ):
        _require(
            test_name in test_source,
            f"S1-A4 case-435 dependency-closure test is absent: {test_name}",
        )
    acceptance = CASE435_DEPENDENCY_CLOSURE_ACCEPTANCE_PATH.read_text(encoding="utf-8")
    for marker in (
        "A4-P6-C435-B",
        snapshot["case435_dependency_closure_audit_id"],
        snapshot["case435_dependency_manifest_id"],
        snapshot["case435_conditional_factorization_proof_id"],
        "A4-P6-C435-C1",
    ):
        _require(
            marker in acceptance,
            f"S1-A4 case-435 dependency acceptance marker absent: {marker}",
        )


def _validate_s1_a4_case435_upper_snapshot(
    snapshot: dict[str, Any],
    dependency_snapshot: dict[str, Any],
) -> dict[str, Any]:
    expected_members = {
        "a1_legal_reduced_tuple_count",
        "a1_maximum_component_canonical_octets",
        "a1_reduced_cartesian_tuple_count",
        "acceptance_doc_raw_octets",
        "acceptance_doc_raw_sha256",
        "acceptance_state",
        "broad_reduced_candidate_count",
        "case435_dependency_manifest_id",
        "case435_upper_certificate_id",
        "certificate_version",
        "checker_raw_octets",
        "checker_raw_sha256",
        "context_canonical_octets",
        "correction_subgate",
        "exact_upper_bound_octets",
        "exact_upper_bound_proved",
        "field_count",
        "field_maximum_sum_octets",
        "focused_passed",
        "independent_attainer_accepted",
        "legal_reduced_candidate_count",
        "maximizing_observation_canonical_sha256",
        "maximizing_observation_id",
        "next_subgate",
        "ordinary_singleton_component_count",
        "separator_branch_count",
        "separator_observation_octet_vector",
        "separator_root_id",
        "solver_raw_octets",
        "solver_raw_sha256",
        "test_raw_octets",
        "test_raw_sha256",
        "verifier_expansion_state",
    }
    _require(
        set(snapshot) == expected_members,
        "S1-A4 case-435 exact-upper snapshot members differ",
    )
    for label, path, octet_member, hash_member in (
        (
            "case-435 exact-upper solver",
            CASE435_UPPER_SOLVER_PATH,
            "solver_raw_octets",
            "solver_raw_sha256",
        ),
        (
            "case-435 upper-certificate checker",
            CASE435_UPPER_CERTIFICATE_CHECKER_PATH,
            "checker_raw_octets",
            "checker_raw_sha256",
        ),
        (
            "case-435 upper-certificate test",
            CASE435_UPPER_CERTIFICATE_TEST_PATH,
            "test_raw_octets",
            "test_raw_sha256",
        ),
        (
            "case-435 exact-upper acceptance",
            CASE435_UPPER_ACCEPTANCE_PATH,
            "acceptance_doc_raw_octets",
            "acceptance_doc_raw_sha256",
        ),
    ):
        _require(path.is_file() and not path.is_symlink(), f"S1-A4 {label} is absent")
        raw = path.read_bytes()
        _require(len(raw) == snapshot[octet_member], f"S1-A4 {label} size drifted")
        _require(_sha256(raw) == snapshot[hash_member], f"S1-A4 {label} hash drifted")

    solver = _load_case435_upper_solver()
    checker = _load_case435_upper_certificate_checker()
    _require(
        solver.PINNED_SHA256 == checker.PINNED_SHA256,
        "S1-A4 case-435 upper authority sets differ",
    )
    try:
        certificate = solver.solve(ROOT)
        verification = checker.verify(ROOT, _canonical_bytes(certificate))
    except (solver.UpperBoundError, checker.CertificateError) as error:
        raise ControlFailure(
            f"S1-A4 case-435 exact-upper replay failed: {error}"
        ) from error

    fields = certificate["ordered_field_maximum_records"]
    reduction = certificate["finite_domain_reduction"]
    composition = certificate["canonical_composition"]
    a1 = certificate["a1_component_certificate"]
    branches = certificate["ordered_separator_branch_bound_records"]
    feasibility = certificate["separator_feasibility_certificate"]
    actual = {
        "certificate_version": certificate["certificate_version"],
        "case435_dependency_manifest_id": certificate["case435_dependency_manifest_id"],
        "case435_upper_certificate_id": certificate["case435_upper_certificate_id"],
        "exact_upper_bound_octets": certificate["exact_upper_bound_octets"],
        "exact_upper_bound_proved": certificate["exact_upper_bound_proved"],
        "independent_attainer_accepted": certificate["independent_attainer_accepted"],
        "acceptance_state": certificate["acceptance_state"],
        "correction_subgate": certificate["correction_subgate"],
        "next_subgate": certificate["next_subgate"],
        "field_count": len(fields),
        "ordinary_singleton_component_count": reduction[
            "ordinary_singleton_component_count"
        ],
        "broad_reduced_candidate_count": sum(
            row["reduced_candidate_count"] for row in fields
        ),
        "legal_reduced_candidate_count": sum(
            row["legal_reduced_candidate_count"] for row in fields
        ),
        "a1_reduced_cartesian_tuple_count": a1["reduced_cartesian_tuple_count"],
        "a1_legal_reduced_tuple_count": a1["legal_reduced_tuple_count"],
        "a1_maximum_component_canonical_octets": a1[
            "maximum_component_canonical_octets"
        ],
        "context_canonical_octets": composition["context_canonical_octets"],
        "field_maximum_sum_octets": composition["field_maximum_sum_octets"],
        "maximizing_observation_id": composition["maximizing_observation_id"],
        "maximizing_observation_canonical_sha256": composition[
            "maximizing_observation_canonical_sha256"
        ],
        "separator_branch_count": len(branches),
        "separator_observation_octet_vector": [
            row["observation_canonical_octets"] for row in branches
        ],
        "separator_root_id": feasibility["root_id"],
    }
    expected = {name: snapshot[name] for name in actual}
    _require(actual == expected, "S1-A4 case-435 exact-upper result drifted")
    _require(
        snapshot["case435_dependency_manifest_id"]
        == dependency_snapshot["case435_dependency_manifest_id"],
        "S1-A4 case-435 upper/dependency manifest join differs",
    )
    _require(
        certificate["authority_sha256_by_path"][solver.DEPENDENCY_ANALYZER_PATH]
        == dependency_snapshot["analyzer_raw_sha256"],
        "S1-A4 case-435 upper/dependency source join differs",
    )
    _require(
        composition["fixed_noncontext_nonfield_octets"]
        + composition["context_canonical_octets"]
        + composition["field_array_bracket_octets"]
        + composition["field_array_comma_octets"]
        + composition["field_maximum_sum_octets"]
        == composition["exact_upper_bound_octets"]
        == snapshot["exact_upper_bound_octets"],
        "S1-A4 case-435 exact-upper composition differs",
    )
    _require(
        max(snapshot["separator_observation_octet_vector"])
        == snapshot["exact_upper_bound_octets"]
        and snapshot["separator_observation_octet_vector"]
        == [257_887, 188_317, 188_317, 188_506, 189_077],
        "S1-A4 case-435 separator maximum differs",
    )
    _require(
        verification
        == {
            "verification_version": (
                "riskyieldmm.raw_v8_step2.maximum_protocol_v2."
                "case435_upper_certificate_verification.v1"
            ),
            "case435_upper_certificate_id": snapshot["case435_upper_certificate_id"],
            "exact_upper_bound_octets": snapshot["exact_upper_bound_octets"],
            "field_count": snapshot["field_count"],
            "separator_branch_count": snapshot["separator_branch_count"],
            "legal_reduced_candidate_count": snapshot["legal_reduced_candidate_count"],
            "legal_a1_tuple_count": snapshot["a1_legal_reduced_tuple_count"],
            "independent_attainer_accepted": False,
            "next_subgate": "A4-P6-C435-C2",
        },
        "S1-A4 case-435 upper-certificate verification differs",
    )
    _require(
        snapshot["focused_passed"] == 17
        and snapshot["exact_upper_bound_proved"] is True
        and snapshot["independent_attainer_accepted"] is False
        and snapshot["acceptance_state"]
        == "EXACT_UPPER_BOUND_PROVED_INDEPENDENT_ATTAINER_PENDING"
        and snapshot["correction_subgate"] == "A4-P6-C435-C1"
        and snapshot["next_subgate"] == "A4-P6-C435-C2"
        and snapshot["verifier_expansion_state"] == "HOLD",
        "S1-A4 case-435 exact-upper disposition differs",
    )
    test_source = CASE435_UPPER_CERTIFICATE_TEST_PATH.read_text(encoding="utf-8")
    for test_name in (
        "test_case435_solver_freezes_exact_upper_certificate",
        "test_case435_independent_checker_reconstructs_solver_certificate",
        "test_case435_solver_and_checker_are_separate_standard_library_programs",
        "test_case435_checker_rejects_resealed_semantic_mutations",
        "test_case435_checker_rejects_authority_drift",
    ):
        _require(
            test_name in test_source,
            f"S1-A4 case-435 exact-upper test is absent: {test_name}",
        )
    acceptance = CASE435_UPPER_ACCEPTANCE_PATH.read_text(encoding="utf-8")
    for marker in (
        "A4-P6-C435-C1",
        snapshot["case435_dependency_manifest_id"],
        snapshot["case435_upper_certificate_id"],
        f"{snapshot['exact_upper_bound_octets']:,}",
        "independent_attainer_accepted = false",
        "A4-P6-C435-C2",
    ):
        _require(
            marker in acceptance,
            f"S1-A4 case-435 exact-upper acceptance marker absent: {marker}",
        )
    return certificate


def _validate_s1_a4_case435_attainer_snapshot(
    snapshot: dict[str, Any],
    dependency_snapshot: dict[str, Any],
) -> dict[str, Any]:
    expected_members = {
        "a1_cartesian_tuple_count",
        "a1_legal_tuple_count",
        "acceptance_doc_raw_octets",
        "acceptance_doc_raw_sha256",
        "acceptance_state",
        "attainer_certificate_id",
        "attainer_certificate_version",
        "case435_dependency_manifest_id",
        "checker_raw_octets",
        "checker_raw_sha256",
        "constructor_raw_octets",
        "constructor_raw_sha256",
        "correction_subgate",
        "exactness_claimed",
        "external_upper_channel_imported",
        "field_count",
        "field_canonical_octet_sum",
        "focused_passed",
        "legal_attainer_constructed",
        "measured_attainer_canonical_octets",
        "measured_attainer_canonical_sha256",
        "measured_attainer_observation_id",
        "measured_observation_sequence_position",
        "next_subgate",
        "ordered_observation_id_vector_sha256",
        "p1_application_invocation_count",
        "p1_direct_expression_node_count",
        "p1_legal",
        "p1_receipt_vector_sha256",
        "p1_rule_evaluation_count",
        "precomputed_witness_imported",
        "root_canonical_sha256",
        "root_id",
        "test_raw_octets",
        "test_raw_sha256",
        "total_field_proposal_count",
        "verifier_expansion_state",
    }
    _require(
        set(snapshot) == expected_members,
        "S1-A4 case-435 attainer snapshot members differ",
    )
    for label, path, octet_member, hash_member in (
        (
            "case-435 attainer constructor",
            CASE435_ATTAINER_CONSTRUCTOR_PATH,
            "constructor_raw_octets",
            "constructor_raw_sha256",
        ),
        (
            "case-435 attainer-certificate checker",
            CASE435_ATTAINER_CERTIFICATE_CHECKER_PATH,
            "checker_raw_octets",
            "checker_raw_sha256",
        ),
        (
            "case-435 attainer-certificate test",
            CASE435_ATTAINER_CERTIFICATE_TEST_PATH,
            "test_raw_octets",
            "test_raw_sha256",
        ),
        (
            "case-435 attainer acceptance",
            CASE435_ATTAINER_ACCEPTANCE_PATH,
            "acceptance_doc_raw_octets",
            "acceptance_doc_raw_sha256",
        ),
    ):
        _require(path.is_file() and not path.is_symlink(), f"S1-A4 {label} is absent")
        raw = path.read_bytes()
        _require(len(raw) == snapshot[octet_member], f"S1-A4 {label} size drifted")
        _require(_sha256(raw) == snapshot[hash_member], f"S1-A4 {label} hash drifted")

    frozen_result = {
        "a1_cartesian_tuple_count": 10_164,
        "a1_legal_tuple_count": 9_989,
        "acceptance_state": "LEGAL_ATTAINER_CONSTRUCTED_EXACTNESS_JOIN_PENDING",
        "attainer_certificate_id": (
            "1d801ba5b81a5e5ed27adfba2ff718fa24a7bd27e3cbf87ce5b603f653502dba"
        ),
        "attainer_certificate_version": (
            "riskyieldmm.raw_v8_step2.maximum_protocol_v2."
            "case435_attainer_certificate.v1"
        ),
        "case435_dependency_manifest_id": (
            "d80797d6d34486ed15f73d19a201c7b5ff0ac19593e25302bcba081c2e7b5c3c"
        ),
        "correction_subgate": "A4-P6-C435-C2",
        "exactness_claimed": False,
        "external_upper_channel_imported": False,
        "field_count": 185,
        "field_canonical_octet_sum": 255_532,
        "focused_passed": 17,
        "legal_attainer_constructed": True,
        "measured_attainer_canonical_octets": 257_887,
        "measured_attainer_canonical_sha256": (
            "f29bb04a79ff2c1ecff867224f70ae7b45c0d7d9c94960a6c81652d6b7b74bad"
        ),
        "measured_attainer_observation_id": (
            "86f29eb6706b58d33db45d3a035e1f4b5bd78e50ba1347355d15d380e5856be9"
        ),
        "measured_observation_sequence_position": 65,
        "next_subgate": "A4-P6-C435-C3",
        "ordered_observation_id_vector_sha256": (
            "6125c0b00f817fd1593013a547f24da965110b27fceaa70762b5ede43811c80c"
        ),
        "p1_application_invocation_count": 137,
        "p1_direct_expression_node_count": 125_431,
        "p1_legal": True,
        "p1_receipt_vector_sha256": (
            "71e39e33ccf923fb922d73336a4afba96051b741d1da5b3fc16af0b0cb95c44b"
        ),
        "p1_rule_evaluation_count": 12_531,
        "precomputed_witness_imported": False,
        "root_canonical_sha256": (
            "aa682944ac87cdd7e4180347d285145a4b4d231a2246a3246a184ae4757a655d"
        ),
        "root_id": ("65bc6b241b3ad861443401d3b101ad0b6eab9108a4653cdeef86b6f8a03e9147"),
        "total_field_proposal_count": 3_144,
        "verifier_expansion_state": "HOLD",
    }
    _require(
        {name: snapshot[name] for name in frozen_result} == frozen_result,
        "S1-A4 case-435 attainer result drifted",
    )
    _require(
        snapshot["case435_dependency_manifest_id"]
        == dependency_snapshot["case435_dependency_manifest_id"],
        "S1-A4 case-435 attainer/dependency manifest join differs",
    )

    constructor = _load_case435_attainer_constructor()
    checker = _load_case435_attainer_certificate_checker()
    _require(
        constructor.PINNED_SHA256 == checker.PINNED_SHA256,
        "S1-A4 case-435 attainer authority sets differ",
    )
    try:
        certificate = constructor.construct(ROOT)
        verification = checker.verify(ROOT, certificate)
    except (constructor.AttainerError, checker.CertificateError) as error:
        raise ControlFailure(
            f"S1-A4 case-435 attainer replay failed: {error}"
        ) from error

    protocol = certificate["construction_protocol"]
    measurement = certificate["measured_attainer"]
    execution = certificate["p1_execution_certificate"]
    selected_fields = certificate["ordered_selected_field_witness_records"]
    actual = {
        "a1_cartesian_tuple_count": protocol["a1_cartesian_tuple_count"],
        "a1_legal_tuple_count": protocol["a1_legal_tuple_count"],
        "acceptance_state": certificate["acceptance_state"],
        "attainer_certificate_id": certificate["case435_attainer_certificate_id"],
        "attainer_certificate_version": certificate["attainer_certificate_version"],
        "case435_dependency_manifest_id": certificate["case435_dependency_manifest_id"],
        "correction_subgate": certificate["correction_subgate"],
        "exactness_claimed": certificate["exactness_claimed"],
        "external_upper_channel_imported": protocol["external_upper_channel_imported"],
        "field_count": len(selected_fields),
        "field_canonical_octet_sum": sum(
            row["selected_canonical_octets"] for row in selected_fields
        ),
        "legal_attainer_constructed": certificate["legal_attainer_constructed"],
        "measured_attainer_canonical_octets": measurement["canonical_octets"],
        "measured_attainer_canonical_sha256": measurement["canonical_sha256"],
        "measured_attainer_observation_id": measurement["observation_id"],
        "measured_observation_sequence_position": measurement[
            "observation_sequence_position"
        ],
        "next_subgate": certificate["next_subgate"],
        "ordered_observation_id_vector_sha256": measurement[
            "ordered_observation_id_vector_sha256"
        ],
        "p1_application_invocation_count": execution["application_invocation_count"],
        "p1_direct_expression_node_count": execution["direct_expression_node_count"],
        "p1_legal": certificate["p1_legal"],
        "p1_receipt_vector_sha256": execution["receipt_vector_sha256"],
        "p1_rule_evaluation_count": execution["charged_rule_evaluation_count"],
        "precomputed_witness_imported": protocol["precomputed_witness_imported"],
        "root_canonical_sha256": measurement["root_canonical_sha256"],
        "root_id": measurement["root_id"],
        "total_field_proposal_count": protocol["total_field_proposal_count"],
    }
    _require(
        actual == {name: snapshot[name] for name in actual},
        "S1-A4 case-435 attainer replay result differs",
    )
    _require(
        verification["case435_attainer_certificate_id"]
        == snapshot["attainer_certificate_id"]
        and verification["measured_attainer_canonical_octets"]
        == snapshot["measured_attainer_canonical_octets"]
        and verification["measured_attainer_canonical_sha256"]
        == snapshot["measured_attainer_canonical_sha256"]
        and verification["p1_application_invocation_count"]
        == snapshot["p1_application_invocation_count"]
        and verification["p1_rule_evaluation_count"]
        == snapshot["p1_rule_evaluation_count"]
        and verification["p1_direct_expression_node_count"]
        == snapshot["p1_direct_expression_node_count"]
        and verification["p1_legal"] is True
        and verification["exactness_claimed"] is False
        and verification["next_subgate"] == "A4-P6-C435-C3",
        "S1-A4 case-435 attainer verification differs",
    )
    test_source = CASE435_ATTAINER_CERTIFICATE_TEST_PATH.read_text(encoding="utf-8")
    for test_name in (
        "test_constructor_emits_a_legal_nonexact_c2_certificate",
        "test_independent_checker_replays_complete_p1",
        "test_constructor_and_checker_do_not_import_or_embed_c1_results",
        "test_rejects_resealed_premature_exactness_claim",
        "test_rejects_resealed_receipt_vector_substitution",
    ):
        _require(
            test_name in test_source,
            f"S1-A4 case-435 attainer test is absent: {test_name}",
        )
    acceptance = CASE435_ATTAINER_ACCEPTANCE_PATH.read_text(encoding="utf-8")
    for marker in (
        "A4-P6-C435-C2",
        snapshot["case435_dependency_manifest_id"],
        snapshot["attainer_certificate_id"],
        f"{snapshot['measured_attainer_canonical_octets']:,}",
        "exactness_claimed = false",
        "A4-P6-C435-C3",
    ):
        _require(
            marker in acceptance,
            f"S1-A4 case-435 attainer acceptance marker absent: {marker}",
        )
    return certificate


def _validate_s1_a4_case435_exactness_join_snapshot(
    snapshot: dict[str, Any],
    dependency_snapshot: dict[str, Any],
    upper_snapshot: dict[str, Any],
    attainer_snapshot: dict[str, Any],
    upper_certificate: dict[str, Any],
    attainer_certificate: dict[str, Any],
) -> dict[str, Any]:
    expected_members = {
        "acceptance_doc_raw_octets",
        "acceptance_doc_raw_sha256",
        "acceptance_state",
        "attainer_certificate_id",
        "attainer_observation_id",
        "attainer_observation_sha256",
        "canonicalization_binding_sha256",
        "case435_dependency_manifest_id",
        "case435_exactness_join_certificate_id",
        "case_binding_sha256",
        "channel_source_set_sha256",
        "checker_raw_octets",
        "checker_raw_sha256",
        "correction_subgate",
        "exact_maximum_octets",
        "exact_maximum_proved",
        "exactness_claimed",
        "focused_passed",
        "join_raw_octets",
        "join_raw_sha256",
        "join_version",
        "next_subgate",
        "ordered_application_instruction_sha256",
        "p1_application_invocation_count",
        "p1_direct_expression_node_count",
        "p1_rule_evaluation_count",
        "required_join_predicate_count",
        "schedule_authority_sha256",
        "shared_raw_authority_set_sha256",
        "test_raw_octets",
        "test_raw_sha256",
        "upper_certificate_id",
        "verifier_expansion_state",
    }
    _require(
        set(snapshot) == expected_members,
        "S1-A4 case-435 exactness-join snapshot members differ",
    )
    for label, path, octet_member, hash_member in (
        (
            "case-435 exactness join",
            CASE435_EXACTNESS_JOIN_PATH,
            "join_raw_octets",
            "join_raw_sha256",
        ),
        (
            "case-435 exactness-certificate checker",
            CASE435_EXACTNESS_CERTIFICATE_CHECKER_PATH,
            "checker_raw_octets",
            "checker_raw_sha256",
        ),
        (
            "case-435 exactness-join test",
            CASE435_EXACTNESS_JOIN_TEST_PATH,
            "test_raw_octets",
            "test_raw_sha256",
        ),
        (
            "case-435 exactness-join acceptance",
            CASE435_EXACTNESS_JOIN_ACCEPTANCE_PATH,
            "acceptance_doc_raw_octets",
            "acceptance_doc_raw_sha256",
        ),
    ):
        _require(path.is_file() and not path.is_symlink(), f"S1-A4 {label} is absent")
        raw = path.read_bytes()
        _require(len(raw) == snapshot[octet_member], f"S1-A4 {label} size drifted")
        _require(_sha256(raw) == snapshot[hash_member], f"S1-A4 {label} hash drifted")

    frozen_result = {
        "acceptance_state": "EXACT_MAXIMUM_PROVED_BY_BOUND_AND_LEGAL_ATTAINMENT",
        "attainer_certificate_id": (
            "1d801ba5b81a5e5ed27adfba2ff718fa24a7bd27e3cbf87ce5b603f653502dba"
        ),
        "attainer_observation_id": (
            "86f29eb6706b58d33db45d3a035e1f4b5bd78e50ba1347355d15d380e5856be9"
        ),
        "attainer_observation_sha256": (
            "f29bb04a79ff2c1ecff867224f70ae7b45c0d7d9c94960a6c81652d6b7b74bad"
        ),
        "canonicalization_binding_sha256": (
            "e2e1b3068a5f48ae3eb9e8797010f4c5023c03e97d95025cc4f503aa4420ddb8"
        ),
        "case435_dependency_manifest_id": (
            "d80797d6d34486ed15f73d19a201c7b5ff0ac19593e25302bcba081c2e7b5c3c"
        ),
        "case435_exactness_join_certificate_id": (
            "2abf00603826f93bb6a538511bbd49ee45096901edbf9bc63c7d0cefb9e7fc3f"
        ),
        "case_binding_sha256": (
            "136dafc839046d8071f7d245367faa5583de32209fcf9d0df09b1ab185fc22c4"
        ),
        "channel_source_set_sha256": (
            "55153bd86b25735de198f7a3d0baae6527ed0ed409bdd2dd7b6c12b2dc6a9b99"
        ),
        "correction_subgate": "A4-P6-C435-C3",
        "exact_maximum_octets": 257_887,
        "exact_maximum_proved": True,
        "exactness_claimed": True,
        "focused_passed": 16,
        "join_version": (
            "riskyieldmm.raw_v8_step2.maximum_protocol_v2.case435_exactness_join.v1"
        ),
        "next_subgate": "A4-P6-C435-D",
        "ordered_application_instruction_sha256": (
            "08955976b1ad455a7e18068ae8d8affe1316f50a56cf50dafd95dc0e0331b20e"
        ),
        "p1_application_invocation_count": 137,
        "p1_direct_expression_node_count": 125_431,
        "p1_rule_evaluation_count": 12_531,
        "required_join_predicate_count": 8,
        "schedule_authority_sha256": (
            "7b5d72df8bea5f01beb0b3d4ecb4ffad5d2a301b32013b72ad02a5457215ae0e"
        ),
        "shared_raw_authority_set_sha256": (
            "0b565a74447d12c80f1fc8f7ce0c8ce9127fb58e155e2b3cbca3cef638a4c593"
        ),
        "upper_certificate_id": (
            "c01bba7c5f5f19c12957493c7a0989dc3ddbc42306c0f059ee922c18341e62b4"
        ),
        "verifier_expansion_state": "HOLD",
    }
    _require(
        {name: snapshot[name] for name in frozen_result} == frozen_result,
        "S1-A4 case-435 exactness-join result drifted",
    )
    _require(
        snapshot["case435_dependency_manifest_id"]
        == dependency_snapshot["case435_dependency_manifest_id"],
        "S1-A4 case-435 exactness/dependency manifest join differs",
    )
    _require(
        snapshot["upper_certificate_id"]
        == upper_snapshot["case435_upper_certificate_id"]
        and snapshot["exact_maximum_octets"]
        == upper_snapshot["exact_upper_bound_octets"],
        "S1-A4 case-435 exactness/upper channel join differs",
    )
    _require(
        snapshot["attainer_certificate_id"]
        == attainer_snapshot["attainer_certificate_id"]
        and snapshot["exact_maximum_octets"]
        == attainer_snapshot["measured_attainer_canonical_octets"]
        and snapshot["attainer_observation_id"]
        == attainer_snapshot["measured_attainer_observation_id"]
        and snapshot["attainer_observation_sha256"]
        == attainer_snapshot["measured_attainer_canonical_sha256"],
        "S1-A4 case-435 exactness/attainer channel join differs",
    )

    joiner = _load_case435_exactness_join()
    checker = _load_case435_exactness_certificate_checker()
    _require(
        joiner.RAW_AUTHORITY_SHA256 == checker.RAW_AUTHORITY_SHA256
        and joiner.CHANNEL_SOURCE_SHA256 == checker.CHANNEL_SOURCE_SHA256,
        "S1-A4 case-435 exactness authority sets differ",
    )
    try:
        certificate = joiner.join(ROOT, upper_certificate, attainer_certificate)
        verification = checker.verify(
            ROOT,
            upper_certificate,
            attainer_certificate,
            certificate,
        )
    except (joiner.JoinError, checker.ExactnessError) as error:
        raise ControlFailure(
            f"S1-A4 case-435 exactness-join replay failed: {error}"
        ) from error

    schedule = certificate["schedule_authority"]
    upper_channel = certificate["upper_channel"]
    attainer_channel = certificate["attainer_channel"]
    actual = {
        "acceptance_state": certificate["acceptance_state"],
        "attainer_certificate_id": attainer_channel["certificate_id"],
        "attainer_observation_id": attainer_channel["measured_attainer_observation_id"],
        "attainer_observation_sha256": attainer_channel[
            "measured_attainer_canonical_sha256"
        ],
        "canonicalization_binding_sha256": _sha256(
            _canonical_bytes(certificate["canonicalization_binding"])
        ),
        "case435_dependency_manifest_id": certificate["case435_dependency_manifest_id"],
        "case435_exactness_join_certificate_id": certificate[
            "case435_exactness_join_certificate_id"
        ],
        "case_binding_sha256": _sha256(_canonical_bytes(certificate["case_binding"])),
        "channel_source_set_sha256": _sha256(
            _canonical_bytes(certificate["channel_source_sha256_by_path"])
        ),
        "correction_subgate": certificate["correction_subgate"],
        "exact_maximum_octets": certificate["exact_maximum_octets"],
        "exact_maximum_proved": certificate["exact_maximum_proved"],
        "exactness_claimed": certificate["exactness_claimed"],
        "join_version": certificate["exactness_join_version"],
        "next_subgate": certificate["next_subgate"],
        "ordered_application_instruction_sha256": schedule[
            "ordered_application_instruction_sha256"
        ],
        "p1_application_invocation_count": schedule["application_invocation_count"],
        "p1_direct_expression_node_count": schedule[
            "direct_cross_expression_node_count"
        ],
        "p1_rule_evaluation_count": schedule["cross_rule_evaluation_count"],
        "required_join_predicate_count": len(
            certificate["ordered_required_join_predicates"]
        ),
        "schedule_authority_sha256": _sha256(_canonical_bytes(schedule)),
        "shared_raw_authority_set_sha256": _sha256(
            _canonical_bytes(certificate["shared_raw_authority_sha256_by_path"])
        ),
        "upper_certificate_id": upper_channel["certificate_id"],
        "verifier_expansion_state": certificate["verifier_expansion_state"],
    }
    _require(
        actual == {name: snapshot[name] for name in actual},
        "S1-A4 case-435 exactness-join replay result differs",
    )
    _require(
        verification
        == {
            "case435_exactness_join_certificate_id": snapshot[
                "case435_exactness_join_certificate_id"
            ],
            "upper_certificate_id": snapshot["upper_certificate_id"],
            "attainer_certificate_id": snapshot["attainer_certificate_id"],
            "exact_maximum_octets": snapshot["exact_maximum_octets"],
            "exact_maximum_proved": True,
            "exactness_claimed": True,
            "next_subgate": "A4-P6-C435-D",
            "verifier_expansion_state": "HOLD",
        },
        "S1-A4 case-435 exactness-certificate verification differs",
    )
    test_source = CASE435_EXACTNESS_JOIN_TEST_PATH.read_text(encoding="utf-8")
    for test_name in (
        "test_c3_join_accepts_only_the_two_frozen_channels",
        "test_independent_checker_reconstructs_join",
        "test_join_and_checker_have_no_local_cross_imports",
        "test_equality_predicate_rejects_different_legal_length",
        "test_checker_rejects_resealed_join_projection_mutation",
    ):
        _require(
            test_name in test_source,
            f"S1-A4 case-435 exactness-join test is absent: {test_name}",
        )
    acceptance = CASE435_EXACTNESS_JOIN_ACCEPTANCE_PATH.read_text(encoding="utf-8")
    for marker in (
        "A4-P6-C435-C3",
        snapshot["case435_dependency_manifest_id"],
        snapshot["case435_exactness_join_certificate_id"],
        snapshot["upper_certificate_id"],
        snapshot["attainer_certificate_id"],
        f"{snapshot['exact_maximum_octets']:,}",
        "exactness_claimed = true",
        "A4-P6-C435-D",
    ):
        _require(
            marker in acceptance,
            f"S1-A4 case-435 exactness acceptance marker absent: {marker}",
        )
    return certificate


def _validate_s1_a4_case435_authority_transition_snapshot(
    snapshot: dict[str, Any],
    exactness_snapshot: dict[str, Any],
    seed_snapshot: dict[str, Any],
    s1_a3_snapshot: dict[str, Any],
    boundary_snapshot: dict[str, Any],
) -> None:
    expected_members = {
        "acceptance_doc_raw_octets",
        "acceptance_doc_raw_sha256",
        "authorized_case_change_count",
        "authorized_case_plan_binding_change_count",
        "authorized_logical_plan_change_count",
        "authorized_profile_program_change_count",
        "boundary_delta_raw_octets",
        "boundary_delta_raw_sha256",
        "case435_exact_maximum_octets",
        "checker_raw_octets",
        "checker_raw_sha256",
        "correction_subgate",
        "exactness_join_certificate_id",
        "f2_resource_requalification_state",
        "focused_passed",
        "manifest_delta_raw_octets",
        "manifest_delta_raw_sha256",
        "migrator_raw_octets",
        "migrator_raw_sha256",
        "next_subgate",
        "predecessor_boundary_id",
        "predecessor_manifest_id",
        "predecessor_seed_catalog_id",
        "producer_expansion_state",
        "runner_state",
        "seed_delta_raw_octets",
        "seed_delta_raw_sha256",
        "successor_case435_logical_count_plan_id",
        "successor_case435_profile_conditioning_program_id",
        "successor_constructive_boundary_id",
        "successor_f2_resource_limit_catalog_id",
        "successor_manifest_id",
        "successor_seed_catalog_id",
        "successor_six_case_target_id",
        "target_delta_raw_octets",
        "target_delta_raw_sha256",
        "test_raw_octets",
        "test_raw_sha256",
        "unaffected_case_count",
        "unaffected_profile_program_count",
        "verifier_expansion_state",
    }
    _require(
        set(snapshot) == expected_members,
        "S1-A4 case-435 authority-transition snapshot members differ",
    )
    artifacts = (
        (
            "case-435 authority migrator",
            CASE435_AUTHORITY_MIGRATOR_PATH,
            "migrator_raw_octets",
            "migrator_raw_sha256",
        ),
        (
            "case-435 authority-transition checker",
            CASE435_AUTHORITY_TRANSITION_CHECKER_PATH,
            "checker_raw_octets",
            "checker_raw_sha256",
        ),
        (
            "case-435 authority-transition test",
            CASE435_AUTHORITY_TRANSITION_TEST_PATH,
            "test_raw_octets",
            "test_raw_sha256",
        ),
        (
            "case-435 seed delta",
            CASE435_SEED_DELTA_PATH,
            "seed_delta_raw_octets",
            "seed_delta_raw_sha256",
        ),
        (
            "case-435 manifest delta",
            CASE435_MANIFEST_DELTA_PATH,
            "manifest_delta_raw_octets",
            "manifest_delta_raw_sha256",
        ),
        (
            "case-435 boundary delta",
            CASE435_BOUNDARY_DELTA_PATH,
            "boundary_delta_raw_octets",
            "boundary_delta_raw_sha256",
        ),
        (
            "case-435 target delta",
            CASE435_TARGET_DELTA_PATH,
            "target_delta_raw_octets",
            "target_delta_raw_sha256",
        ),
        (
            "case-435 authority-transition acceptance",
            CASE435_AUTHORITY_TRANSITION_ACCEPTANCE_PATH,
            "acceptance_doc_raw_octets",
            "acceptance_doc_raw_sha256",
        ),
    )
    for label, path, octet_member, hash_member in artifacts:
        _require(path.is_file() and not path.is_symlink(), f"S1-A4 {label} absent")
        raw = path.read_bytes()
        _require(len(raw) == snapshot[octet_member], f"S1-A4 {label} size drifted")
        _require(_sha256(raw) == snapshot[hash_member], f"S1-A4 {label} hash drifted")

    frozen_result = {
        "authorized_case_change_count": 1,
        "authorized_case_plan_binding_change_count": 1,
        "authorized_logical_plan_change_count": 1,
        "authorized_profile_program_change_count": 1,
        "case435_exact_maximum_octets": 257_887,
        "correction_subgate": "A4-P6-C435-D",
        "exactness_join_certificate_id": (
            "2abf00603826f93bb6a538511bbd49ee45096901edbf9bc63c7d0cefb9e7fc3f"
        ),
        "f2_resource_requalification_state": "REQUIRED_IN_A4_P6_V",
        "focused_passed": 26,
        "next_subgate": "A4-P6-V",
        "predecessor_boundary_id": (
            "bdc7363ae28dfe9a1c1dc132808cb1bd4a06c409201cd49b31e394893142a7ed"
        ),
        "predecessor_manifest_id": (
            "edde204e98ed1caeeb8ae270487d85e39a2168e0a3692ce1d8748d2d8e7fd858"
        ),
        "predecessor_seed_catalog_id": (
            "ac22151fa74702ac1488924f01161eaa38574545e6272a290db6b0bbd288ae5f"
        ),
        "producer_expansion_state": "HOLD_UNTIL_A4_P6_V_ACCEPTED",
        "runner_state": "HOLD_UNTIL_VERIFIER_AND_PRODUCER_EXPANSIONS_ACCEPTED",
        "successor_case435_logical_count_plan_id": (
            "343259e38b6050fac5905fdc7ed6dca6d345d32c07b8370085bdf865793e7ad8"
        ),
        "successor_case435_profile_conditioning_program_id": (
            "160486e8c6023b4cfb7ac430065a1dd8c8c422342535fbd5b9b0bceb2ca2e820"
        ),
        "successor_constructive_boundary_id": (
            "7d4c06f56cd3cacd97cc4ff655e31f380fe9231c6c7c1374caee499186e1f73d"
        ),
        "successor_f2_resource_limit_catalog_id": (
            "5b2171f64c082ddaa5ecbeb19e2e2f5b952c07336a097364f23fd1658c3d944f"
        ),
        "successor_manifest_id": (
            "6aed1139c158f8685bcb226697a2efe57af3c42f57831173bd7b3ea169025d9c"
        ),
        "successor_seed_catalog_id": (
            "7fad47e881624d0f39809e72ce2d3d3fd81fb8c85f854fe8332faf543cd1120b"
        ),
        "successor_six_case_target_id": (
            "a000285d1bedd88306786ea33e1be9cc7d2a8459fe75b20c045f7174d52cc072"
        ),
        "unaffected_case_count": 474,
        "unaffected_profile_program_count": 407,
        "verifier_expansion_state": "RELEASED_FOR_A4_P6_V_IMPLEMENTATION",
    }
    _require(
        {name: snapshot[name] for name in frozen_result} == frozen_result,
        "S1-A4 case-435 authority-transition result drifted",
    )
    _require(
        snapshot["exactness_join_certificate_id"]
        == exactness_snapshot["case435_exactness_join_certificate_id"]
        and snapshot["case435_exact_maximum_octets"]
        == exactness_snapshot["exact_maximum_octets"],
        "S1-A4 case-435 transition/exactness binding differs",
    )
    _require(
        snapshot["predecessor_seed_catalog_id"]
        == seed_snapshot["prospective_seed_catalog_id"],
        "S1-A4 case-435 predecessor seed binding differs",
    )
    _require(
        snapshot["predecessor_manifest_id"]
        == s1_a3_snapshot["finalization_manifest_id"],
        "S1-A4 case-435 predecessor manifest binding differs",
    )
    _require(
        snapshot["predecessor_boundary_id"]
        == boundary_snapshot["constructive_boundary_id"],
        "S1-A4 case-435 predecessor boundary binding differs",
    )

    transition_checker = _load_case435_authority_transition_checker()
    try:
        report = transition_checker.verify(ROOT)
    except transition_checker.AuthorityTransitionReject as error:
        raise ControlFailure(
            f"S1-A4 case-435 authority-transition replay failed: {error}"
        ) from error
    report_projection = {
        "authorized_case_change_count": report["authorized_case_change_count"],
        "authorized_case_plan_binding_change_count": report[
            "authorized_case_plan_binding_change_count"
        ],
        "authorized_logical_plan_change_count": report[
            "authorized_logical_plan_change_count"
        ],
        "authorized_profile_program_change_count": report[
            "authorized_profile_program_change_count"
        ],
        "case435_exact_maximum_octets": report["case435_exact_maximum_octets"],
        "f2_resource_requalification_state": report[
            "f2_resource_requalification_state"
        ],
        "next_subgate": report["next_subgate"],
        "successor_case435_logical_count_plan_id": report[
            "successor_case435_logical_count_plan_id"
        ],
        "successor_case435_profile_conditioning_program_id": report[
            "successor_case435_profile_conditioning_program_id"
        ],
        "successor_constructive_boundary_id": report[
            "successor_constructive_boundary_id"
        ],
        "successor_f2_resource_limit_catalog_id": report[
            "successor_f2_resource_limit_catalog_id"
        ],
        "successor_manifest_id": report["successor_manifest_id"],
        "successor_seed_catalog_id": report["successor_seed_catalog_id"],
        "successor_six_case_target_id": report["successor_six_case_target_id"],
        "unaffected_case_count": report["unaffected_case_count"],
        "unaffected_profile_program_count": report[
            "unaffected_profile_program_count"
        ],
        "verifier_expansion_state": report["verifier_expansion_state"],
    }
    _require(
        report_projection
        == {name: snapshot[name] for name in report_projection},
        "S1-A4 case-435 authority-transition replay result differs",
    )
    _require(report["verification_status"] == "ACCEPTED", "transition not accepted")

    test_source = CASE435_AUTHORITY_TRANSITION_TEST_PATH.read_text(encoding="utf-8")
    for test_name in (
        "test_independent_checker_accepts_exact_single_case_transition",
        "test_case435_effective_program_uses_exact_cell_without_relaxation",
        "test_manifest_does_not_relabel_predecessor_preflight_as_successor_evidence",
        "test_independent_checker_rejects_hostile_resealed_mutations",
    ):
        _require(
            test_name in test_source,
            f"S1-A4 case-435 authority-transition test absent: {test_name}",
        )
    acceptance = CASE435_AUTHORITY_TRANSITION_ACCEPTANCE_PATH.read_text(
        encoding="utf-8"
    )
    for marker in (
        "A4-P6-C435-D",
        snapshot["exactness_join_certificate_id"],
        snapshot["successor_seed_catalog_id"],
        snapshot["successor_manifest_id"],
        snapshot["successor_constructive_boundary_id"],
        snapshot["successor_six_case_target_id"],
        f"{snapshot['case435_exact_maximum_octets']:,}",
        "A4-P6-V",
    ):
        _require(
            marker in acceptance,
            f"S1-A4 case-435 authority-transition acceptance marker absent: {marker}",
        )


def _validate_s1_a4_verifier_expansion_v0_snapshot(
    snapshot: dict[str, Any],
    historical_verifier_snapshot: dict[str, Any],
    boundary_snapshot: dict[str, Any],
    transition_snapshot: dict[str, Any],
) -> None:
    _require(
        set(snapshot)
        == {
            "acceptance_doc_raw_octets",
            "acceptance_doc_raw_sha256",
            "acceptance_state",
            "accepted_case_positions",
            "authority_mode_order",
            "case435_resource_requalification_state",
            "correction_subgate",
            "f0_input_file_count_limit",
            "f0_total_pinned_input_octets_limit",
            "focused_passed",
            "next_subgate",
            "ordered_remaining_case_positions",
            "predecessor_authority_file_count",
            "predecessor_authority_octets",
            "predecessor_file_headroom",
            "predecessor_octet_headroom",
            "source_marker",
            "successor_authority_file_count",
            "successor_authority_octets",
            "successor_constructive_boundary_id",
            "successor_f2_resource_limit_catalog_id",
            "successor_file_headroom",
            "successor_manifest_id",
            "successor_maximum_protocol_sha256",
            "successor_octet_headroom",
            "successor_seed_catalog_id",
            "successor_six_case_target_id",
            "typed_rule_runtime_raw_octets",
            "typed_rule_runtime_raw_sha256",
            "verifier_raw_octets",
            "verifier_raw_sha256",
            "verifier_test_raw_octets",
            "verifier_test_raw_sha256",
        },
        "S1-A4 verifier-expansion V0 snapshot members differ",
    )
    _require(
        snapshot["correction_subgate"] == "A4-P6-V0"
        and snapshot["acceptance_state"]
        == "EXACT_PREDECESSOR_SUCCESSOR_RESOLVER_AND_READ_BARRIER_ACCEPTED"
        and snapshot["next_subgate"] == "A4-P6-V1"
        and snapshot["accepted_case_positions"] == [5]
        and snapshot["ordered_remaining_case_positions"] == [24, 54, 69, 435, 475]
        and snapshot["authority_mode_order"]
        == [
            "PREDECESSOR_CONSTRUCTIVE_BOUNDARY_V1",
            "SUCCESSOR_CASE435_EXACT_DELTA_V1",
        ]
        and snapshot["case435_resource_requalification_state"]
        == "WAITING_FOR_A4_P6_V3_EXECUTION"
        and snapshot["focused_passed"] == 7,
        "S1-A4 verifier-expansion V0 state differs",
    )
    _require(
        snapshot["source_marker"] == historical_verifier_snapshot["source_marker"],
        "S1-A4 verifier-expansion source marker differs",
    )
    _require(
        snapshot["successor_seed_catalog_id"]
        == transition_snapshot["successor_seed_catalog_id"]
        and snapshot["successor_manifest_id"]
        == transition_snapshot["successor_manifest_id"]
        and snapshot["successor_constructive_boundary_id"]
        == transition_snapshot["successor_constructive_boundary_id"]
        and snapshot["successor_f2_resource_limit_catalog_id"]
        == transition_snapshot["successor_f2_resource_limit_catalog_id"]
        and snapshot["successor_six_case_target_id"]
        == transition_snapshot["successor_six_case_target_id"]
        and snapshot["successor_maximum_protocol_sha256"]
        == transition_snapshot["manifest_delta_raw_sha256"],
        "S1-A4 verifier-expansion successor bindings differ",
    )

    for label, path, octets, digest in (
        (
            "verifier",
            INDEPENDENT_VERIFIER_PATH,
            snapshot["verifier_raw_octets"],
            snapshot["verifier_raw_sha256"],
        ),
        (
            "verifier-expansion test",
            INDEPENDENT_VERIFIER_EXPANSION_V0_TEST_PATH,
            snapshot["verifier_test_raw_octets"],
            snapshot["verifier_test_raw_sha256"],
        ),
        (
            "typed rule runtime",
            TYPED_RULE_RUNTIME_PATH,
            snapshot["typed_rule_runtime_raw_octets"],
            snapshot["typed_rule_runtime_raw_sha256"],
        ),
        (
            "verifier-expansion acceptance",
            INDEPENDENT_VERIFIER_EXPANSION_V0_ACCEPTANCE_PATH,
            snapshot["acceptance_doc_raw_octets"],
            snapshot["acceptance_doc_raw_sha256"],
        ),
    ):
        _require(path.is_file() and not path.is_symlink(), f"S1-A4 V0 {label} is absent")
        raw = path.read_bytes()
        _require(len(raw) == octets, f"S1-A4 V0 {label} size drifted")
        _require(_sha256(raw) == digest, f"S1-A4 V0 {label} hash drifted")

    boundary = json.loads(CONSTRUCTIVE_BOUNDARY_PATH.read_bytes())
    seed_record = boundary["authority_contract"]["seed_authority"]
    manifest_record = boundary["authority_contract"][
        "finalization_manifest_authority"
    ]
    seed_path = ROOT / seed_record["repository_relative_path"]
    manifest_path = ROOT / manifest_record["repository_relative_path"]
    seed = json.loads(seed_path.read_bytes())
    seed_delta = json.loads(CASE435_SEED_DELTA_PATH.read_bytes())
    target_delta = json.loads(CASE435_TARGET_DELTA_PATH.read_bytes())

    authority_specs: list[tuple[str, Path, int, str]] = [
        (
            "predecessor boundary",
            CONSTRUCTIVE_BOUNDARY_PATH,
            boundary_snapshot["boundary_raw_octets"],
            boundary_snapshot["boundary_raw_sha256"],
        ),
        (
            "predecessor seed",
            seed_path,
            seed_record["raw_octets"],
            seed_record["raw_sha256"],
        ),
        (
            "predecessor manifest",
            manifest_path,
            manifest_record["raw_octets"],
            manifest_record["raw_sha256"],
        ),
        (
            "current verifier",
            INDEPENDENT_VERIFIER_PATH,
            snapshot["verifier_raw_octets"],
            snapshot["verifier_raw_sha256"],
        ),
    ]
    for row in seed["ordered_authority_binding_records"]:
        authority_specs.append(
            (
                f"seed authority {row['authority_position']}",
                ROOT / row["repository_relative_path"],
                row["raw_octet_count"],
                row["raw_sha256"],
            )
        )
    legacy = boundary["legacy_v1_exclusion_contract"]
    for name in (
        "rejected_protocol_authority",
        "rejected_bootstrap_authority",
        "accepted_rejection_authority",
    ):
        row = legacy[name]
        authority_specs.append(
            (
                name,
                ROOT / row["repository_relative_path"],
                row["raw_octets"],
                row["raw_sha256"],
            )
        )

    predecessor_count = len(authority_specs)
    predecessor_octets = sum(spec[2] for spec in authority_specs)
    _require(
        predecessor_count == snapshot["predecessor_authority_file_count"]
        and predecessor_octets == snapshot["predecessor_authority_octets"],
        "S1-A4 V0 predecessor authority footprint differs",
    )

    authority_specs.append(
        (
            "successor seed delta",
            CASE435_SEED_DELTA_PATH,
            transition_snapshot["seed_delta_raw_octets"],
            transition_snapshot["seed_delta_raw_sha256"],
        )
    )
    for row in seed_delta["exactness_theorem_authority"][
        "ordered_source_authority_records"
    ]:
        authority_specs.append(
            (
                f"exactness source {row['source_position']}",
                ROOT / row["repository_relative_path"],
                row["raw_octets"],
                row["raw_sha256"],
            )
        )
    authority_specs.extend(
        [
            (
                "successor manifest delta",
                CASE435_MANIFEST_DELTA_PATH,
                transition_snapshot["manifest_delta_raw_octets"],
                transition_snapshot["manifest_delta_raw_sha256"],
            ),
            (
                "successor boundary delta",
                CASE435_BOUNDARY_DELTA_PATH,
                transition_snapshot["boundary_delta_raw_octets"],
                transition_snapshot["boundary_delta_raw_sha256"],
            ),
        ]
    )
    target_source = target_delta["predecessor_six_case_target_authority"]
    authority_specs.extend(
        [
            (
                "predecessor six-case target",
                ROOT / target_source["repository_relative_path"],
                target_source["raw_octets"],
                target_source["raw_sha256"],
            ),
            (
                "successor six-case target delta",
                CASE435_TARGET_DELTA_PATH,
                transition_snapshot["target_delta_raw_octets"],
                transition_snapshot["target_delta_raw_sha256"],
            ),
            (
                "typed rule runtime",
                TYPED_RULE_RUNTIME_PATH,
                snapshot["typed_rule_runtime_raw_octets"],
                snapshot["typed_rule_runtime_raw_sha256"],
            ),
        ]
    )
    seen_paths: set[Path] = set()
    seen_inodes: set[tuple[int, int]] = set()
    for label, path, octets, digest in authority_specs:
        _require(path not in seen_paths, f"S1-A4 V0 {label} path aliases")
        _require(path.is_file() and not path.is_symlink(), f"S1-A4 V0 {label} is absent")
        stat_result = path.stat()
        inode = (stat_result.st_dev, stat_result.st_ino)
        _require(inode not in seen_inodes, f"S1-A4 V0 {label} inode aliases")
        raw = path.read_bytes()
        _require(len(raw) == octets, f"S1-A4 V0 {label} authority size differs")
        _require(_sha256(raw) == digest, f"S1-A4 V0 {label} authority hash differs")
        seen_paths.add(path)
        seen_inodes.add(inode)

    successor_count = len(authority_specs)
    successor_octets = sum(spec[2] for spec in authority_specs)
    _require(
        successor_count == snapshot["successor_authority_file_count"]
        and successor_octets == snapshot["successor_authority_octets"],
        "S1-A4 V0 successor authority footprint differs",
    )
    file_limit = snapshot["f0_input_file_count_limit"]
    octet_limit = snapshot["f0_total_pinned_input_octets_limit"]
    _require(
        file_limit == 64
        and octet_limit == 67_108_864
        and file_limit - predecessor_count == snapshot["predecessor_file_headroom"]
        and octet_limit - predecessor_octets == snapshot["predecessor_octet_headroom"]
        and file_limit - successor_count == snapshot["successor_file_headroom"]
        and octet_limit - successor_octets == snapshot["successor_octet_headroom"],
        "S1-A4 V0 immutable F0 headroom differs",
    )

    source = INDEPENDENT_VERIFIER_PATH.read_text(encoding="utf-8")
    for marker in (
        snapshot["source_marker"],
        "PREDECESSOR_CONSTRUCTIVE_BOUNDARY_V1",
        "SUCCESSOR_CASE435_EXACT_DELTA_V1",
        transition_snapshot["successor_seed_catalog_id"],
        transition_snapshot["successor_manifest_id"],
        transition_snapshot["successor_constructive_boundary_id"],
    ):
        _require(marker in source, f"S1-A4 V0 verifier marker absent: {marker}")
    test_source = INDEPENDENT_VERIFIER_EXPANSION_V0_TEST_PATH.read_text(
        encoding="utf-8"
    )
    for test_name in (
        "test_v0_preserves_predecessor_case5_and_accepts_successor_case5",
        "test_v0_successor_mode_is_byte_deterministic",
        "test_v0_rejects_cross_mode_candidate_authority_ids",
        "test_v0_rejects_tampered_successor_authority_before_candidate_open",
    ):
        _require(test_name in test_source, f"S1-A4 V0 test absent: {test_name}")
    acceptance = INDEPENDENT_VERIFIER_EXPANSION_V0_ACCEPTANCE_PATH.read_text(
        encoding="utf-8"
    )
    for marker in (
        "A4-P6-V0",
        "A4-P6-V1",
        snapshot["verifier_raw_sha256"],
        snapshot["successor_seed_catalog_id"],
        snapshot["successor_constructive_boundary_id"],
        "28,752,433",
        "NO-GO",
    ):
        _require(marker in acceptance, f"S1-A4 V0 acceptance marker absent: {marker}")


def validate() -> dict[str, Any]:
    control = _load_control()
    _require(control.get("control_version") == 1, "unknown control version")
    _require(control.get("formal_stage1_state") == "NO-GO", "Stage 1 must remain NO-GO")
    _require(
        control.get("offline_stage2_state") == "BLOCKED",
        "offline Stage 2 state differs",
    )
    _require(
        control.get("live_activation_state") == "BLOCKED",
        "live activation must remain blocked",
    )
    _validate_gate_graph(control)
    _validate_navigation(control["active_gate"])
    s1_a2_snapshot = control.get("s1_a2_snapshot")
    _require(isinstance(s1_a2_snapshot, dict), "s1_a2_snapshot is missing")
    _validate_s1_a2_snapshot(s1_a2_snapshot)
    s1_a3_snapshot = control.get("s1_a3_snapshot")
    _require(isinstance(s1_a3_snapshot, dict), "s1_a3_snapshot is missing")
    _validate_s1_a3_snapshot(s1_a3_snapshot, s1_a2_snapshot)
    s1_a4_boundary_snapshot = control.get("s1_a4_boundary_snapshot")
    _require(
        isinstance(s1_a4_boundary_snapshot, dict),
        "s1_a4_boundary_snapshot is missing",
    )
    _validate_s1_a4_boundary_snapshot(s1_a4_boundary_snapshot, s1_a3_snapshot)
    s1_a4_fail_first_snapshot = control.get("s1_a4_fail_first_snapshot")
    _require(
        isinstance(s1_a4_fail_first_snapshot, dict),
        "s1_a4_fail_first_snapshot is missing",
    )
    _validate_s1_a4_fail_first_snapshot(
        s1_a4_fail_first_snapshot,
        s1_a4_boundary_snapshot,
    )
    s1_a4_verifier_snapshot = control.get("s1_a4_verifier_snapshot")
    _require(
        isinstance(s1_a4_verifier_snapshot, dict),
        "s1_a4_verifier_snapshot is missing",
    )
    _validate_s1_a4_verifier_snapshot(
        s1_a4_verifier_snapshot,
        s1_a4_boundary_snapshot,
    )
    s1_a4_producer_snapshot = control.get("s1_a4_producer_snapshot")
    _require(
        isinstance(s1_a4_producer_snapshot, dict),
        "s1_a4_producer_snapshot is missing",
    )
    _validate_s1_a4_producer_snapshot(
        s1_a4_producer_snapshot,
        s1_a4_boundary_snapshot,
    )
    s1_a4_six_case_target_snapshot = control.get("s1_a4_six_case_target_snapshot")
    _require(
        isinstance(s1_a4_six_case_target_snapshot, dict),
        "s1_a4_six_case_target_snapshot is missing",
    )
    _validate_s1_a4_six_case_target_snapshot(
        s1_a4_six_case_target_snapshot,
        s1_a4_boundary_snapshot,
        s1_a4_producer_snapshot,
    )

    snapshot = control.get("seed_snapshot")
    _require(isinstance(snapshot, dict), "seed_snapshot is missing")
    case435_snapshot = control.get("s1_a4_case435_attainability_falsification_snapshot")
    _require(
        isinstance(case435_snapshot, dict),
        "s1_a4_case435_attainability_falsification_snapshot is missing",
    )
    _validate_s1_a4_case435_attainability_falsification_snapshot(
        case435_snapshot,
        s1_a4_six_case_target_snapshot,
        snapshot,
    )
    profile_scope_snapshot = control.get("s1_a4_profile_attainability_scope_snapshot")
    _require(
        isinstance(profile_scope_snapshot, dict),
        "s1_a4_profile_attainability_scope_snapshot is missing",
    )
    _validate_s1_a4_profile_attainability_scope_snapshot(
        profile_scope_snapshot,
        case435_snapshot,
        snapshot,
    )
    dependency_closure_snapshot = control.get(
        "s1_a4_case435_dependency_closure_snapshot"
    )
    _require(
        isinstance(dependency_closure_snapshot, dict),
        "s1_a4_case435_dependency_closure_snapshot is missing",
    )
    _validate_s1_a4_case435_dependency_closure_snapshot(
        dependency_closure_snapshot,
        profile_scope_snapshot,
        case435_snapshot,
    )
    upper_snapshot = control.get("s1_a4_case435_upper_snapshot")
    _require(
        isinstance(upper_snapshot, dict),
        "s1_a4_case435_upper_snapshot is missing",
    )
    upper_certificate = _validate_s1_a4_case435_upper_snapshot(
        upper_snapshot,
        dependency_closure_snapshot,
    )
    attainer_snapshot = control.get("s1_a4_case435_attainer_snapshot")
    _require(
        isinstance(attainer_snapshot, dict),
        "s1_a4_case435_attainer_snapshot is missing",
    )
    attainer_certificate = _validate_s1_a4_case435_attainer_snapshot(
        attainer_snapshot,
        dependency_closure_snapshot,
    )
    exactness_join_snapshot = control.get("s1_a4_case435_exactness_join_snapshot")
    _require(
        isinstance(exactness_join_snapshot, dict),
        "s1_a4_case435_exactness_join_snapshot is missing",
    )
    _validate_s1_a4_case435_exactness_join_snapshot(
        exactness_join_snapshot,
        dependency_closure_snapshot,
        upper_snapshot,
        attainer_snapshot,
        upper_certificate,
        attainer_certificate,
    )
    authority_transition_snapshot = control.get(
        "s1_a4_case435_authority_transition_snapshot"
    )
    _require(
        isinstance(authority_transition_snapshot, dict),
        "s1_a4_case435_authority_transition_snapshot is missing",
    )
    _validate_s1_a4_case435_authority_transition_snapshot(
        authority_transition_snapshot,
        exactness_join_snapshot,
        snapshot,
        s1_a3_snapshot,
        s1_a4_boundary_snapshot,
    )
    verifier_expansion_v0_snapshot = control.get(
        "s1_a4_verifier_expansion_v0_snapshot"
    )
    _require(
        isinstance(verifier_expansion_v0_snapshot, dict),
        "s1_a4_verifier_expansion_v0_snapshot is missing",
    )
    _validate_s1_a4_verifier_expansion_v0_snapshot(
        verifier_expansion_v0_snapshot,
        s1_a4_verifier_snapshot,
        s1_a4_boundary_snapshot,
        authority_transition_snapshot,
    )
    generator_raw = GENERATOR_PATH.read_bytes()
    catalog_raw = CATALOG_PATH.read_bytes()
    _require(
        _sha256(generator_raw) == snapshot["generator_sha256"], "seed generator drifted"
    )
    _require(
        _sha256(catalog_raw) == snapshot["catalog_sha256"],
        "stored seed catalog drifted",
    )
    _require(
        len(catalog_raw) == snapshot["catalog_raw_octets"],
        "stored catalog size drifted",
    )

    generator = _load_generator()
    prospective = generator.build_catalog(ROOT)
    prospective_raw = generator._pretty_bytes(prospective)
    _require(
        len(prospective_raw) == snapshot["prospective_raw_octets"],
        "prospective seed size drifted",
    )
    _require(
        _sha256(prospective_raw) == snapshot["prospective_sha256"],
        "prospective seed bytes drifted",
    )
    _require(
        prospective["seed_catalog_id"] == snapshot["prospective_seed_catalog_id"],
        "prospective seed identity drifted",
    )
    _require(
        (catalog_raw != prospective_raw) is snapshot["catalog_stale"],
        "catalog staleness differs",
    )
    if control["gate_states"]["S1-A1"]["state"] == "ACCEPTED":
        _require(snapshot["catalog_stale"] is False, "accepted S1-A1 seed is stale")
        _require(snapshot["focused_failed"] == 0, "accepted S1-A1 has failures")
        _require(snapshot["focused_passed"] > 0, "accepted S1-A1 has no tests")
    operational_limit = snapshot["operational_output_maximum_octets"]
    _require(
        len(catalog_raw) <= operational_limit,
        "stored seed exceeds the operational output target",
    )
    _require(
        operational_limit - len(catalog_raw) == snapshot["operational_headroom_octets"],
        "operational seed headroom drifted",
    )
    f0 = {
        row["resource_name"]: row["ceiling_value"]
        for row in prospective["f0_seed_ceiling_catalog"][
            "ordered_platform_ceiling_records"
        ]
    }
    _require(
        f0["INDIVIDUAL_FILE_STRICT_UPPER_OCTETS"]
        == snapshot["strict_individual_file_upper_octets"],
        "strict individual-file cap drifted",
    )
    return control


def main() -> int:
    try:
        control = validate()
        snapshot = control["seed_snapshot"]
        print(
            "STAGE1_CONTROL_OK "
            f"active_gate={control['active_gate']} "
            f"formal_state={control['formal_stage1_state']} "
            f"catalog_stale={str(snapshot['catalog_stale']).lower()} "
            f"s1_a2_comparison_id={control['s1_a2_snapshot']['comparison_payload_id']} "
            f"s1_a3_manifest_id={control['s1_a3_snapshot']['finalization_manifest_id']} "
            f"s1_a4_boundary_id={control['s1_a4_boundary_snapshot']['constructive_boundary_id']} "
            f"s1_a4_fail_first_sha256={control['s1_a4_fail_first_snapshot']['fail_first_test_raw_sha256']} "
            f"s1_a4_verifier_sha256={control['s1_a4_verifier_expansion_v0_snapshot']['verifier_raw_sha256']} "
            f"s1_a4_producer_sha256={control['s1_a4_producer_snapshot']['producer_raw_sha256']} "
            f"s1_a4_six_case_target_sha256={control['s1_a4_six_case_target_snapshot']['fail_first_test_raw_sha256']} "
            f"s1_a4_case435_analysis_id={control['s1_a4_case435_attainability_falsification_snapshot']['attainability_analysis_id']} "
            f"s1_a4_case435_gap_octets={control['s1_a4_case435_attainability_falsification_snapshot']['p3_unattainable_gap_octets']} "
            f"s1_a4_profile_scope_audit_id={control['s1_a4_profile_attainability_scope_snapshot']['profile_attainability_scope_audit_id']} "
            f"s1_a4_profile_scope_affected={control['s1_a4_profile_attainability_scope_snapshot']['structural_superset_program_count']}/"
            f"{control['s1_a4_profile_attainability_scope_snapshot']['structural_superset_scope_case_count']} "
            f"s1_a4_case435_dependency_audit_id={control['s1_a4_case435_dependency_closure_snapshot']['case435_dependency_closure_audit_id']} "
            f"s1_a4_case435_components={control['s1_a4_case435_dependency_closure_snapshot']['ordinary_singleton_component_count']}+"
            f"{control['s1_a4_case435_dependency_closure_snapshot']['a1_coupled_field_count']} "
            f"s1_a4_case435_upper_certificate_id={control['s1_a4_case435_upper_snapshot']['case435_upper_certificate_id']} "
            f"s1_a4_case435_upper_octets={control['s1_a4_case435_upper_snapshot']['exact_upper_bound_octets']} "
            f"s1_a4_case435_attainer_certificate_id={control['s1_a4_case435_attainer_snapshot']['attainer_certificate_id']} "
            f"s1_a4_case435_attainer_octets={control['s1_a4_case435_attainer_snapshot']['measured_attainer_canonical_octets']} "
            f"s1_a4_case435_exactness_join_id={control['s1_a4_case435_exactness_join_snapshot']['case435_exactness_join_certificate_id']} "
            f"s1_a4_case435_exact_maximum_octets={control['s1_a4_case435_exactness_join_snapshot']['exact_maximum_octets']} "
            f"s1_a4_case435_successor_seed_id={control['s1_a4_case435_authority_transition_snapshot']['successor_seed_catalog_id']} "
            f"s1_a4_case435_successor_target_id={control['s1_a4_case435_authority_transition_snapshot']['successor_six_case_target_id']} "
            f"s1_a4_case435_verifier_expansion={control['s1_a4_case435_authority_transition_snapshot']['verifier_expansion_state']} "
            f"s1_a4_verifier_packet={control['s1_a4_verifier_expansion_v0_snapshot']['correction_subgate']} "
            f"s1_a4_verifier_next={control['s1_a4_verifier_expansion_v0_snapshot']['next_subgate']} "
            f"prospective_raw_octets={snapshot['prospective_raw_octets']} "
            f"strict_upper_octets={snapshot['strict_individual_file_upper_octets']}"
        )
        return 0
    except (ControlFailure, OSError, ValueError, KeyError, TypeError) as exc:
        print(f"STAGE1_CONTROL_INVALID: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
