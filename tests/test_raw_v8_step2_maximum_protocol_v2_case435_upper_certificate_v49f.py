from __future__ import annotations

import ast
import copy
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOLVER_PATH = (
    ROOT / "scripts/tests/solve_raw_v8_step2_maximum_protocol_v2_case435_upper_v49f.py"
)
CHECKER_PATH = (
    ROOT
    / "scripts/tests/check_raw_v8_step2_maximum_protocol_v2_case435_upper_certificate_v49f.py"
)
EXPECTED_CERTIFICATE_ID = (
    "c01bba7c5f5f19c12957493c7a0989dc3ddbc42306c0f059ee922c18341e62b4"
)


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _resign(certificate: dict[str, Any], checker) -> None:
    payload = {
        key: value
        for key, value in certificate.items()
        if key != "case435_upper_certificate_id"
    }
    certificate["case435_upper_certificate_id"] = hashlib.sha256(
        _canonical_bytes({"domain": checker.CERTIFICATE_DOMAIN, "payload": payload})
    ).hexdigest()


def _set_path(root: Any, path: tuple[Any, ...], value: Any) -> None:
    target = root
    for member in path[:-1]:
        target = target[member]
    target[path[-1]] = value


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add((node.module or "").split(".")[0])
    return imported


@pytest.fixture(scope="module")
def solver():
    return _load_module(SOLVER_PATH, "case435_exact_upper_solver")


@pytest.fixture(scope="module")
def checker():
    return _load_module(CHECKER_PATH, "case435_exact_upper_checker")


@pytest.fixture(scope="module")
def certificate(solver) -> dict[str, Any]:
    return solver.solve(ROOT)


def test_case435_solver_freezes_exact_upper_certificate(certificate) -> None:
    assert certificate["case435_upper_certificate_id"] == EXPECTED_CERTIFICATE_ID
    assert certificate["exact_upper_bound_octets"] == 257_887
    assert certificate["exact_upper_bound_proved"] is True
    assert certificate["independent_attainer_accepted"] is False
    assert certificate["acceptance_state"] == (
        "EXACT_UPPER_BOUND_PROVED_INDEPENDENT_ATTAINER_PENDING"
    )
    assert certificate["correction_subgate"] == "A4-P6-C435-C1"
    assert certificate["next_subgate"] == "A4-P6-C435-C2"

    fields = certificate["ordered_field_maximum_records"]
    reduction = certificate["finite_domain_reduction"]
    composition = certificate["canonical_composition"]
    assert len(fields) == 185
    assert [row["field_position"] for row in fields] == list(range(1, 186))
    assert len({row["field_id"] for row in fields}) == 185
    assert sum(row["maximum_canonical_octets"] for row in fields) == 255_532
    assert sum(row["reduced_candidate_count"] for row in fields) == 4_089
    assert sum(row["legal_reduced_candidate_count"] for row in fields) == 2_971
    assert reduction["ordinary_singleton_component_count"] == 182
    assert reduction["a1_component_field_count"] == 3
    assert composition == {
        "codec_constraint_satisfied": True,
        "codec_octet_limit": 262_144,
        "codec_relation": "LT",
        "context_canonical_octets": 1_747,
        "exact_upper_bound_octets": 257_887,
        "field_array_bracket_octets": 2,
        "field_array_comma_octets": 184,
        "field_maximum_sum_octets": 255_532,
        "fixed_noncontext_nonfield_octets": 422,
        "maximizing_observation_canonical_sha256": (
            "f29bb04a79ff2c1ecff867224f70ae7b45c0d7d9c94960a6c81652d6b7b74bad"
        ),
        "maximizing_observation_id": (
            "86f29eb6706b58d33db45d3a035e1f4b5bd78e50ba1347355d15d380e5856be9"
        ),
    }


def test_case435_solver_freezes_joint_component_and_separator_proofs(
    certificate,
) -> None:
    a1 = certificate["a1_component_certificate"]
    assert a1 == {
        "legal_reduced_tuple_count": 9_051,
        "maximum_component_canonical_octets": 4_111,
        "ordered_field_ids": [
            "a1.waiting_count",
            "a1.waiting_kinds",
            "a1.waiting_sequences",
        ],
        "reduced_cartesian_tuple_count": 9_261,
        "winner_activates_constraint": False,
        "winner_field_observation_id_vector_sha256": (
            "4b2452fc371a167f57194981bed961e7165bd70dd409bc433118c3ed2de17b1d"
        ),
    }
    branches = certificate["ordered_separator_branch_bound_records"]
    assert [row["observation_canonical_octets"] for row in branches] == [
        257_887,
        188_317,
        188_317,
        188_506,
        189_077,
    ]
    assert [row["binding_reason"] for row in branches] == [
        None,
        "ARTIFACT_BOUND_EXCEEDED",
        "OBSERVER_INTERNAL_ERROR",
        "SOURCE_CLOCK_UNAVAILABLE",
        "TARGET_BOUNDARY_NOT_REACHED",
    ]
    feasibility = certificate["separator_feasibility_certificate"]
    assert feasibility["lifecycle_feasible"] is True
    assert feasibility["observation_count"] == 67
    assert feasibility["preceding_placeholder_count"] == 63
    assert feasibility["selected_exact_marker_count"] == 1
    assert feasibility["root_id"] == (
        "572b4a11e1d4108faf55361b1c5dc165d4730e20e7c73c58a2b8b34822c913fb"
    )


def test_case435_independent_checker_reconstructs_solver_certificate(
    checker, certificate
) -> None:
    report = checker.verify(ROOT, _canonical_bytes(certificate))
    assert report == {
        "verification_version": (
            "riskyieldmm.raw_v8_step2.maximum_protocol_v2."
            "case435_upper_certificate_verification.v1"
        ),
        "case435_upper_certificate_id": EXPECTED_CERTIFICATE_ID,
        "exact_upper_bound_octets": 257_887,
        "field_count": 185,
        "separator_branch_count": 5,
        "legal_reduced_candidate_count": 2_971,
        "legal_a1_tuple_count": 9_051,
        "independent_attainer_accepted": False,
        "next_subgate": "A4-P6-C435-C2",
    }


def test_case435_solver_and_checker_are_deterministic_and_pipe_safe(
    certificate, tmp_path: Path
) -> None:
    solver_results = [
        subprocess.run(
            [sys.executable, str(SOLVER_PATH), str(ROOT)],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        for _ in range(2)
    ]
    assert all(result.returncode == 0 for result in solver_results)
    assert all(result.stderr == "" for result in solver_results)
    assert solver_results[0].stdout == solver_results[1].stdout
    assert json.loads(solver_results[0].stdout) == certificate

    file_path = tmp_path / "certificate.json"
    file_path.write_bytes(_canonical_bytes(certificate))
    file_result = subprocess.run(
        [sys.executable, str(CHECKER_PATH), str(file_path), str(ROOT)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    pipe_result = subprocess.run(
        [sys.executable, str(CHECKER_PATH), "-", str(ROOT)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        input=solver_results[0].stdout,
        text=True,
    )
    assert file_result.returncode == pipe_result.returncode == 0
    assert file_result.stderr == pipe_result.stderr == ""
    assert file_result.stdout == pipe_result.stdout


def test_case435_solver_and_checker_are_separate_standard_library_programs() -> None:
    allowed = {
        "__future__",
        "hashlib",
        "itertools",
        "json",
        "pathlib",
        "re",
        "sys",
        "typing",
    }
    assert _imports(SOLVER_PATH) <= allowed
    assert _imports(CHECKER_PATH) <= allowed

    solver_tree = ast.parse(SOLVER_PATH.read_text())
    checker_tree = ast.parse(CHECKER_PATH.read_text())
    solver_functions = {
        node.name for node in ast.walk(solver_tree) if isinstance(node, ast.FunctionDef)
    }
    checker_functions = {
        node.name
        for node in ast.walk(checker_tree)
        if isinstance(node, ast.FunctionDef)
    }
    assert "_candidate_valid" in solver_functions
    assert "_candidate_valid" not in checker_functions
    assert "_legal_candidates" in checker_functions
    assert "_legal_candidates" not in solver_functions
    for source in (SOLVER_PATH.read_text(), CHECKER_PATH.read_text()):
        assert (
            "import validate_raw_v8_step2_external_schema_v2_rule_runtime" not in source
        )
        assert "import check_raw_v8_step2_maximum_protocol_v2" not in source


@pytest.mark.parametrize(
    ("path", "forged_value"),
    [
        (("exact_upper_bound_octets",), 257_888),
        (("canonical_composition", "field_maximum_sum_octets"), 255_533),
        (("ordered_field_maximum_records", 0, "maximum_canonical_octets"), 1_369),
        (("ordered_field_maximum_records", 0, "legal_reduced_candidate_count"), 17),
        (("a1_component_certificate", "legal_reduced_tuple_count"), 9_052),
        (
            (
                "ordered_separator_branch_bound_records",
                4,
                "observation_canonical_octets",
            ),
            189_078,
        ),
        (("separator_feasibility_certificate", "root_id"), "0" * 64),
        (("independent_attainer_accepted",), True),
    ],
)
def test_case435_checker_rejects_resealed_semantic_mutations(
    checker,
    certificate,
    path: tuple[Any, ...],
    forged_value: Any,
) -> None:
    forged = copy.deepcopy(certificate)
    _set_path(forged, path, forged_value)
    _resign(forged, checker)
    with pytest.raises(checker.CertificateError):
        checker.verify(ROOT, _canonical_bytes(forged))


def test_case435_checker_rejects_resealed_missing_field(checker, certificate) -> None:
    forged = copy.deepcopy(certificate)
    forged["ordered_field_maximum_records"].pop()
    _resign(forged, checker)
    with pytest.raises(checker.CertificateError, match="field maximum vector differs"):
        checker.verify(ROOT, _canonical_bytes(forged))


def test_case435_checker_rejects_unsealed_certificate_mutation(
    checker, certificate
) -> None:
    forged = copy.deepcopy(certificate)
    forged["case_binding"]["case_position"] = 436
    with pytest.raises(checker.CertificateError, match="certificate identity differs"):
        checker.verify(ROOT, _canonical_bytes(forged))


def test_case435_checker_rejects_authority_drift(
    checker, certificate, tmp_path: Path
) -> None:
    for relative_path in checker.PINNED_SHA256:
        source = ROOT / relative_path
        target = tmp_path / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    runtime = tmp_path / checker.RUNTIME_PATH
    runtime.write_text(runtime.read_text() + "\n# forged drift\n")
    with pytest.raises(checker.CertificateError, match="authority hash differs"):
        checker.verify(tmp_path, _canonical_bytes(certificate))


def test_case435_checker_rejects_duplicate_json_members(checker, certificate) -> None:
    raw = _canonical_bytes(certificate)
    forged = raw[:-1] + b',"exact_upper_bound_octets":257887}'
    with pytest.raises(checker.CertificateError, match="duplicate JSON key"):
        checker.verify(ROOT, forged)
