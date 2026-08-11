"""Fail-closed contract tests for A4-R475-V1-C2-S."""

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
GENERATOR = (
    ROOT
    / "scripts/tests/generate_raw_v8_step2_maximum_protocol_v2_intrinsic_dual_source_freeze_v49f.py"
)
REVIEWER = (
    ROOT
    / "scripts/tests/review_raw_v8_step2_maximum_protocol_v2_intrinsic_dual_source_freeze_v49f.py"
)
MANIFEST = (
    ROOT
    / "scripts/tests/raw_v8_step2_maximum_protocol_v2_intrinsic_dual_source_freeze_v49f.json"
)
CONTRACT = (
    ROOT
    / "scripts/tests/raw_v8_step2_maximum_protocol_v2_intrinsic_correction_contract_v49f.json"
)
REPORT = (
    ROOT
    / "scripts/tests/raw_v8_step2_maximum_protocol_v2_intrinsic_dual_source_freeze_acceptance_report_v49f.json"
)
UPPER_SOURCE = (
    ROOT
    / "scripts/tests/solve_raw_v8_step2_maximum_protocol_v2_intrinsic_upper_v49f.py"
)
ATTAINER_SOURCE = (
    ROOT
    / "scripts/tests/construct_raw_v8_step2_maximum_protocol_v2_intrinsic_attainers_v49f.py"
)
UPPER_SCHEMA = (
    ROOT
    / "scripts/tests/raw_v8_step2_maximum_protocol_v2_intrinsic_upper_result_schema_v49f.json"
)
ATTAINER_SCHEMA = (
    ROOT
    / "scripts/tests/raw_v8_step2_maximum_protocol_v2_intrinsic_attainer_result_schema_v49f.json"
)


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


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _semantic_id(domain: str, payload: Any) -> str:
    return _sha256(_canonical_bytes({"domain": domain, "payload": payload}))


def _load_module(path: Path, name: str) -> Any:
    specification = importlib.util.spec_from_file_location(name, path)
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    sys.modules[name] = module
    specification.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def generator() -> Any:
    return _load_module(GENERATOR, "_test_intrinsic_c2s_generator")


@pytest.fixture(scope="module")
def manifest() -> dict[str, Any]:
    raw = MANIFEST.read_bytes()
    value = json.loads(raw)
    assert raw == _pretty_bytes(value)
    return value


def _imports(tree: ast.AST) -> set[str]:
    result: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module != "__future__":
            assert node.module is not None
            result.add(node.module.split(".", 1)[0])
    return result


def _assigned_derivation_kinds(tree: ast.Module) -> set[str]:
    assignment = next(
        node
        for node in tree.body
        if isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
        and node.target.id == "SUPPORTED_DERIVATION_KINDS"
    )
    assert isinstance(assignment.value, ast.Call)
    literal = assignment.value.args[0]
    assert isinstance(literal, ast.Set)
    return {child.value for child in literal.elts if isinstance(child, ast.Constant)}


def test_manifest_is_exact_generator_output_and_semantically_sealed(
    generator: Any, manifest: dict[str, Any]
) -> None:
    assert generator.build_manifest(ROOT) == manifest
    payload = {
        key: value for key, value in manifest.items() if key != "dual_source_freeze_id"
    }
    assert manifest["dual_source_freeze_id"] == _semantic_id(
        manifest["identity_domain"], payload
    )
    completed = subprocess.run(
        [sys.executable, str(GENERATOR), "--root", str(ROOT), "--check"],
        cwd=ROOT,
        capture_output=True,
        check=False,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr.decode()
    assert completed.stdout == completed.stderr == b""


def test_sources_are_frozen_together_but_have_distinct_core_implementations(
    manifest: dict[str, Any]
) -> None:
    rows = manifest["ordered_channel_source_records"]
    assert [row["channel"] for row in rows] == ["LEGAL_UPPER", "P1_LEGAL_ATTAINER"]
    assert [row["channel_position"] for row in rows] == [1, 2]
    assert len({row["raw_sha256"] for row in rows}) == 2
    assert len(set(manifest["channel_core_ast_fingerprints"].values())) == 2
    for row in rows:
        raw = (ROOT / row["relative_path"]).read_bytes()
        assert row["raw_octets"] == len(raw)
        assert row["raw_sha256"] == _sha256(raw)
        assert row["channel_output_allowed_during_source_freeze"] is False
        assert row["placeholder_or_case_specific_answer_policy"] == "FORBIDDEN"


def test_each_source_covers_the_complete_c1_derivation_language_without_importing_the_other(
    manifest: dict[str, Any]
) -> None:
    contract = json.loads(CONTRACT.read_bytes())
    actual_kinds = {
        step["derivation_kind"]
        for case in contract["ordered_intrinsic_case_records"]
        for step in case["ordered_step_contract_records"]
    }
    sources = {
        "LEGAL_UPPER": (UPPER_SOURCE, ATTAINER_SOURCE.name),
        "P1_LEGAL_ATTAINER": (ATTAINER_SOURCE, UPPER_SOURCE.name),
    }
    row_by_channel = {
        row["channel"]: row for row in manifest["ordered_channel_source_records"]
    }
    for channel, (path, opposite_name) in sources.items():
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        assert _assigned_derivation_kinds(tree) == actual_kinds
        assert _imports(tree) == set(
            row_by_channel[channel]["allowed_standard_library_import_roots"]
        )
        assert opposite_name not in source
        assert "TODO" not in source
        assert "NotImplemented" not in source
        assert not any(
            isinstance(
                node,
                (ast.Pass, ast.AsyncFunctionDef, ast.Await, ast.Yield, ast.YieldFrom),
            )
            for node in ast.walk(tree)
        )


def test_dynamic_execution_is_absent_from_upper_and_narrowly_scoped_in_attainer() -> (
    None
):
    upper_calls = [
        node.func.id
        for node in ast.walk(ast.parse(UPPER_SOURCE.read_text(encoding="utf-8")))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    ]
    attainer_tree = ast.parse(ATTAINER_SOURCE.read_text(encoding="utf-8"))
    attainer_calls = [
        node.func.id
        for node in ast.walk(attainer_tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    ]
    assert "compile" not in upper_calls and "exec" not in upper_calls
    assert attainer_calls.count("compile") == attainer_calls.count("exec") == 1
    loader = next(
        node
        for node in attainer_tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_load_runtime"
    )
    loader_calls = {
        node.func.id
        for node in ast.walk(loader)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert {"compile", "exec"} <= loader_calls


def test_output_schemas_are_closed_separate_and_semantically_sealed(
    manifest: dict[str, Any]
) -> None:
    by_channel = {
        row["channel"]: row for row in manifest["ordered_channel_source_records"]
    }
    for channel, path in (
        ("LEGAL_UPPER", UPPER_SCHEMA),
        ("P1_LEGAL_ATTAINER", ATTAINER_SCHEMA),
    ):
        raw = path.read_bytes()
        schema = json.loads(raw)
        payload = {
            key: value for key, value in schema.items() if key != "output_schema_id"
        }
        assert schema["output_schema_id"] == _semantic_id(
            schema["identity_domain"], payload
        )
        assert schema["root_record_schema"]["unknown_member_policy"] == "REJECT"
        assert schema["case_record_schema"]["unknown_member_policy"] == "REJECT"
        assert by_channel[channel]["output_schema_raw_octets"] == len(raw)
        assert by_channel[channel]["output_schema_raw_sha256"] == _sha256(raw)
        assert by_channel[channel]["output_schema_id"] == schema["output_schema_id"]
    upper = json.loads(UPPER_SCHEMA.read_bytes())
    attainer = json.loads(ATTAINER_SCHEMA.read_bytes())
    assert "ordered_case_attainer_records" not in upper["root_record_schema"][
        "ordered_member_names"
    ]
    assert "ordered_case_upper_records" not in attainer["root_record_schema"][
        "ordered_member_names"
    ]


def test_witness_transport_is_preallocated_from_protocol_caps_not_observed_answers() -> (
    None
):
    schema = json.loads(ATTAINER_SCHEMA.read_bytes())
    transport = schema["transport_contract"]
    assert transport["fixed_shard_case_ranges"] == [[1, 22], [23, 44], [45, 66]]
    assert transport["worst_case_witness_payload_octets_per_shard"] == 22 * 524_288
    assert transport["shard_count"] == 3
    assert transport["total_output_file_count"] == 4
    assert transport["worst_case_witness_payload_octets_per_shard"] < transport[
        "individual_file_strict_upper_octets"
    ]
    assert "ROOT_LAST" in transport["atomic_publication"]
    assert transport["partial_result_policy"] == "ROLL_BACK_AND_PUBLISH_NOTHING"


def test_resource_projection_is_strictly_inside_frozen_f0_and_answer_independent(
    manifest: dict[str, Any]
) -> None:
    resources = manifest["resource_contract"]
    outputs = manifest["output_transport_projection"]
    assert resources["projected_pinned_input_upper_octets"] < resources[
        "total_pinned_input_octets_limit"
    ]
    assert resources["projected_pinned_input_file_count"] < resources[
        "input_file_count_limit"
    ]
    assert outputs["projected_total_output_upper_octets"] < resources[
        "total_pinned_input_octets_limit"
    ]
    assert resources["limit_tuning_from_observed_channel_answer_allowed"] is False
    assert outputs["answer_observation_used_to_set_limits"] is False
    assert "66_CASES_TIMES_524288" in outputs["projection_basis"]


def test_all_official_channel_outputs_are_absent_before_execution(
    manifest: dict[str, Any]
) -> None:
    rows = manifest["pre_execution_output_absence_records"]
    assert len(rows) == 5
    assert [row["output_position"] for row in rows] == list(range(1, 6))
    for row in rows:
        path = ROOT / row["relative_path"]
        assert not path.exists()
        assert not path.is_symlink()
        assert row["required_state"] == "ABSENT_BEFORE_C2_U_OR_C2_A_EXECUTION"


def test_source_freeze_accepts_no_result_or_exactness_claim(
    manifest: dict[str, Any]
) -> None:
    assert manifest["acceptance_contract"] == {
        "acceptance_claim": "PRE_EXECUTION_DUAL_SOURCE_AND_OUTPUT_SCHEMA_FREEZE_ONLY",
        "all_case_campaign_released": False,
        "channel_results_accepted": False,
        "exact_maxima_accepted": False,
        "required_independent_review": "RECONSTRUCT_BYTES_SCHEMAS_AST_POLICY_RESOURCES_AND_OUTPUT_ABSENCE_WITHOUT_GENERATOR_OR_CHANNEL_IMPORT",
        "source_files_executed_by_c2_s": False,
    }
    assert manifest["formal_stage1_state"] == "NO-GO"
    assert manifest["next_bounded_packet"] == "A4-R475-V1-C2-U"


@pytest.mark.parametrize(
    ("channel", "mutation", "message"),
    [
        (
            "LEGAL_UPPER",
            lambda source: source.replace(
                "import pathlib", "import pathlib\nimport subprocess", 1
            ),
            "import surface differs",
        ),
        (
            "LEGAL_UPPER",
            lambda source: source.replace(
                'SOURCE_MARKER: Final = "A4_R475_V1_C2_U_STANDALONE_LEGAL_UPPER_SOLVER_V1"',
                'SOURCE_MARKER: Final = "MUTATED"',
                1,
            ),
            "source marker differs",
        ),
        (
            "P1_LEGAL_ATTAINER",
            lambda source: source.replace(
                "Candidate selection is implemented locally",
                "TODO Candidate selection is implemented locally",
                1,
            ),
            "placeholder implementation",
        ),
    ],
)
def test_static_source_mutations_fail_closed(
    generator: Any,
    tmp_path: Path,
    channel: str,
    mutation: Any,
    message: str,
) -> None:
    config = copy.deepcopy(generator.SOURCE_CONFIG[channel])
    for relative_path in (config["relative_path"], config["schema_path"]):
        target = tmp_path / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative_path, target)
    source_path = tmp_path / config["relative_path"]
    source_path.write_text(
        mutation(source_path.read_text(encoding="utf-8")), encoding="utf-8"
    )
    with pytest.raises(generator.FreezeFailure, match=message):
        generator._review_source(tmp_path, channel, config)


def test_schema_relaxation_with_stale_identity_fails_closed(
    generator: Any, tmp_path: Path
) -> None:
    channel = "LEGAL_UPPER"
    config = copy.deepcopy(generator.SOURCE_CONFIG[channel])
    for relative_path in (config["relative_path"], config["schema_path"]):
        target = tmp_path / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative_path, target)
    schema_path = tmp_path / config["schema_path"]
    schema = json.loads(schema_path.read_bytes())
    schema["root_record_schema"]["unknown_member_policy"] = "ALLOW"
    schema_path.write_bytes(_pretty_bytes(schema))
    with pytest.raises(generator.FreezeFailure, match="schema identity differs"):
        generator._review_source(tmp_path, channel, config)


def test_coherently_resealed_overclaims_change_freeze_identity(
    manifest: dict[str, Any]
) -> None:
    for path, value in (
        (("acceptance_contract", "channel_results_accepted"), True),
        (("acceptance_contract", "exact_maxima_accepted"), True),
        (("independence_contract", "shared_core_executable_code_policy"), "ALLOW"),
        (("resource_contract", "limit_tuning_from_observed_channel_answer_allowed"), True),
    ):
        mutated = copy.deepcopy(manifest)
        mutated[path[0]][path[1]] = value
        payload = {
            key: child
            for key, child in mutated.items()
            if key != "dual_source_freeze_id"
        }
        resealed = _semantic_id(mutated["identity_domain"], payload)
        assert resealed != manifest["dual_source_freeze_id"]


def test_independent_reviewer_imports_neither_generator_nor_channel_source() -> None:
    source = REVIEWER.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = _imports(tree)
    assert "scripts" not in imported
    assert GENERATOR.name not in source
    assert f"import {UPPER_SOURCE.stem}" not in source
    assert f"import {ATTAINER_SOURCE.stem}" not in source


def test_stored_acceptance_report_matches_two_independent_reviews() -> None:
    expected = REPORT.read_bytes()
    first = subprocess.run(
        [sys.executable, str(REVIEWER), str(ROOT)],
        cwd=ROOT,
        capture_output=True,
        check=False,
        timeout=30,
    )
    second = subprocess.run(
        [sys.executable, str(REVIEWER), str(ROOT)],
        cwd=ROOT,
        capture_output=True,
        check=False,
        timeout=30,
    )
    assert first.returncode == second.returncode == 0
    assert first.stderr == second.stderr == b""
    assert first.stdout == second.stdout == expected
    report = json.loads(expected)
    payload = {
        key: value
        for key, value in report.items()
        if key != "dual_source_freeze_acceptance_report_id"
    }
    assert report["dual_source_freeze_acceptance_report_id"] == _semantic_id(
        "RiskYieldMMRawV8Step2MaximumProtocolV2IntrinsicDualSourceFreezeAcceptanceReportV1",
        payload,
    )
    assert report["source_or_channel_execution_count"] == 0
    assert report["channel_results_accepted"] is False
    assert report["exact_maxima_accepted"] is False
