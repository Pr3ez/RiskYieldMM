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

import pytest

ROOT = Path(__file__).resolve().parents[1]
CHECKER_PATH = (
    ROOT
    / "scripts/tests/check_raw_v8_step2_maximum_protocol_v2_case435_dependency_closure_v49f.py"
)


def _load_checker():
    spec = importlib.util.spec_from_file_location(
        "case435_dependency_closure_checker", CHECKER_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _canonical_bytes(value) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _resign_manifest(checker, manifest) -> None:
    payload = {
        key: value
        for key, value in manifest.items()
        if key != "case435_dependency_manifest_id"
    }
    manifest["case435_dependency_manifest_id"] = checker._identity(
        checker.MANIFEST_DOMAIN, payload
    )


def _resign_proof(checker, proof) -> None:
    payload = {
        key: value
        for key, value in proof.items()
        if key != "case435_conditional_factorization_proof_id"
    }
    proof["case435_conditional_factorization_proof_id"] = checker._identity(
        checker.PROOF_DOMAIN, payload
    )


def _copy_authority_tree(checker, destination: Path) -> None:
    for relative in checker.PINNED_RAW_SHA256:
        source = ROOT / relative
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)


def test_case435_dependency_closure_freezes_complete_conditional_graph() -> None:
    checker = _load_checker()
    report = checker.analyze(ROOT)
    manifest = report["case435_dependency_manifest"]
    proof = report["case435_conditional_factorization_proof"]

    assert report["case435_dependency_closure_audit_id"] == (
        "56923275cd4422c3bc90115a6ee647b3b7142d1d800a855757d7c90924fd4583"
    )
    assert manifest["case435_dependency_manifest_id"] == (
        "d80797d6d34486ed15f73d19a201c7b5ff0ac19593e25302bcba081c2e7b5c3c"
    )
    assert proof["case435_conditional_factorization_proof_id"] == (
        "13dd74d6478f11f61d2f7665fc32025b288562b37a7ecd62ecf7595413145dcc"
    )
    assert report["schema_closure_type_count"] == 32
    assert report["schema_closure_value_schema_count"] == 133
    assert report["schema_closure_intrinsic_rule_count"] == 21
    assert report["selected_cross_rule_count"] == 5
    assert report["selected_rule_count"] == 26
    assert report["selected_rule_expression_node_count"] == 754
    assert report["complex_operator_count"] == 9
    assert report["runtime_function_closure_count"] == 24
    assert report["runtime_constant_closure_count"] == 9
    assert report["field_count"] == 185
    assert report["ordinary_singleton_component_count"] == 182
    assert report["a1_coupled_field_count"] == 3
    assert report["conditional_component_count"] == 183
    assert report["dependency_closure_complete"] is True
    assert report["conditional_factorization_proved"] is True
    assert report["unconditional_factorization_rejected"] is True
    assert report["exact_case435_maximum_derived"] is False
    assert report["legal_case435_attainer_constructed"] is False
    assert report["correction_subgate"] == "A4-P6-C435-B"
    assert report["next_subgate"] == "A4-P6-C435-C1"
    assert report["verifier_expansion_state"] == "HOLD"

    a1 = manifest["separator_contract"]["ordered_a1_field_ids"]
    assert a1 == [
        "a1.waiting_count",
        "a1.waiting_kinds",
        "a1.waiting_sequences",
    ]
    components = manifest["ordered_conditional_component_records"]
    assert (
        sum(row["component_kind"] == "ORDINARY_SINGLETON" for row in components) == 182
    )
    assert [
        row["ordered_field_ids"]
        for row in components
        if row["component_kind"] == "A1_FIFO_COUPLED"
    ] == [sorted(a1)]
    assert len(manifest["ordered_deterministic_projection_records"]) == 7
    assert manifest["canonical_composition_contract"] == {
        "canonicalization_version": "riskyieldmm_canonical_json_v1",
        "measured_type_name": "TargetObservationV2",
        "field_count": 185,
        "fixed_noncontext_nonfield_octets": 422,
        "field_array_bracket_octets": 2,
        "field_array_comma_octets": 184,
        "composition_formula": (
            "422_PLUS_CONTEXT_CANONICAL_OCTETS_PLUS_2_PLUS_184_PLUS_"
            "SUM_185_FIELD_CANONICAL_OCTETS"
        ),
        "identity_width_policy": (
            "ALL_CROSS_RECORD_IDENTITIES_ARE_RECOMPUTED_LOWERCASE_SHA256_"
            "TEXT_WITH_FIXED_66_CANONICAL_OCTETS_WHEN_PRESENT"
        ),
    }


def test_case435_dependency_closure_independently_reconstructs_schedule_and_types() -> (
    None
):
    checker = _load_checker()
    report = checker.analyze(ROOT)
    manifest = report["case435_dependency_manifest"]
    seed = json.loads((ROOT / checker.SEED_RELATIVE_PATH).read_text())
    inventory = json.loads((ROOT / checker.INVENTORY_RELATIVE_PATH).read_text())
    registry = inventory["external_schema_registry_v2"]

    plan = seed["logical_plan_recipe_catalog"]["ordered_logical_count_plan_records"][
        checker.CASE_POSITION - 1
    ]
    program = next(
        row
        for row in seed["logical_plan_recipe_catalog"][
            "ordered_profile_conditioning_program_records"
        ]
        if row["profile_conditioning_program_id"]
        == plan["profile_conditioning_program_id"]
    )
    instructions = program["application_schedule_operation"][
        "ordered_schedule_segment_records"
    ][0]["ordered_application_instruction_records"]
    assert [
        (
            row["application_name"],
            row["rule_id"],
            row["rule_application_id"],
            row["application_invocation_count_per_scope_case"],
        )
        for row in instructions
    ] == list(checker.SELECTED_APPLICATIONS)

    types = {
        row["type_name"]: row for row in registry["ordered_external_type_descriptors"]
    }
    schemas = {row["value_schema_id"]: row for row in registry["value_schema_catalog"]}
    pending_types = list(checker.ROOT_TYPES)
    pending_schemas: list[str] = []
    seen_types: set[str] = set()
    seen_schemas: set[str] = set()
    while pending_types or pending_schemas:
        if pending_types:
            name = pending_types.pop()
            if name in seen_types:
                continue
            seen_types.add(name)
            descriptor = types[name]
            pending_schemas.extend(
                row["value_schema_id"]
                for row in descriptor.get("record_member_descriptors") or []
            )
            pending_types.extend(
                row["referenced_type_name"]
                for row in (descriptor.get("tagged_union_descriptor") or {}).get(
                    "ordered_alternatives", []
                )
            )
        else:
            schema_id = pending_schemas.pop()
            if schema_id in seen_schemas:
                continue
            seen_schemas.add(schema_id)
            schema = schemas[schema_id]
            if schema["referenced_type_name"] is not None:
                pending_types.append(schema["referenced_type_name"])
            if schema["array_item_value_schema_id"] is not None:
                pending_schemas.append(schema["array_item_value_schema_id"])
    assert len(seen_types) == 32
    assert len(seen_schemas) == 133
    assert sorted(seen_schemas) == manifest["ordered_schema_closure_value_schema_ids"]


def test_case435_dependency_closure_runtime_ast_seal_is_independently_recomputed() -> (
    None
):
    checker = _load_checker()
    report = checker.analyze(ROOT)
    closure = report["case435_dependency_manifest"]["runtime_source_closure"]
    tree = ast.parse((ROOT / checker.RULE_RUNTIME_RELATIVE_PATH).read_text())
    functions = {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    rows = closure["ordered_transitive_function_ast_records"]
    independent = []
    for position, row in enumerate(rows, 1):
        dumped = ast.dump(
            functions[row["function_name"]],
            annotate_fields=True,
            include_attributes=False,
        ).encode()
        independent.append(
            {
                "function_position": position,
                "function_name": row["function_name"],
                "function_ast_sha256": hashlib.sha256(dumped).hexdigest(),
            }
        )
    assert independent == rows
    assert hashlib.sha256(_canonical_bytes(independent)).hexdigest() == (
        checker.RUNTIME_FUNCTION_AST_VECTOR_SHA256
    )


def test_case435_dependency_closure_cli_is_deterministic_and_silent() -> None:
    commands = [
        [sys.executable, str(CHECKER_PATH)],
        [sys.executable, str(CHECKER_PATH), str(ROOT)],
    ]
    results = [
        subprocess.run(
            command,
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        for command in commands
    ]
    assert all(result.returncode == 0 for result in results)
    assert all(result.stderr == "" for result in results)
    assert results[0].stdout == results[1].stdout
    report = json.loads(results[0].stdout)
    assert report["case435_dependency_closure_audit_id"] == (
        "56923275cd4422c3bc90115a6ee647b3b7142d1d800a855757d7c90924fd4583"
    )


def test_case435_dependency_checker_imports_only_standard_library() -> None:
    tree = ast.parse(CHECKER_PATH.read_text())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add((node.module or "").split(".")[0])
    assert imported <= {
        "__future__",
        "ast",
        "hashlib",
        "json",
        "pathlib",
        "sys",
        "typing",
    }
    assert "importlib" not in imported
    assert "subprocess" not in imported


def test_case435_conditional_factorization_matches_full_microdomain_enumeration() -> (
    None
):
    checker = _load_checker()
    result = checker.microdomain_factorization_check()
    assert result == {
        "context_state_count": 3,
        "brute_force_legal_tuple_count": 16,
        "brute_force_maximum": 29,
        "factorized_maximum": 29,
    }


def test_case435_dependency_manifest_rejects_missing_a1_edge() -> None:
    checker = _load_checker()
    manifest = copy.deepcopy(checker.analyze(ROOT)["case435_dependency_manifest"])
    manifest["ordered_cross_field_edges"].pop()
    _resign_manifest(checker, manifest)
    with pytest.raises(
        checker.DependencyClosureError, match="A1 cross-field edge closure"
    ):
        checker.validate_dependency_manifest(manifest)


def test_case435_dependency_manifest_rejects_extra_cross_field_edge() -> None:
    checker = _load_checker()
    manifest = copy.deepcopy(checker.analyze(ROOT)["case435_dependency_manifest"])
    manifest["ordered_cross_field_edges"].append(
        {
            "edge_position": 4,
            "left_field_id": "a1.active_count",
            "right_field_id": "actor.operation_appended_events",
            "source_operator": "FORGED",
            "source_constraint_id": "FORGED",
        }
    )
    _resign_manifest(checker, manifest)
    with pytest.raises(
        checker.DependencyClosureError, match="A1 cross-field edge closure"
    ):
        checker.validate_dependency_manifest(manifest)


def test_case435_dependency_manifest_rejects_operator_contract_weakening() -> None:
    checker = _load_checker()
    manifest = copy.deepcopy(checker.analyze(ROOT)["case435_dependency_manifest"])
    a1 = next(
        row
        for row in manifest["ordered_operator_dependency_contracts"]
        if row["operator"] == "A1_FIFO_FIELDS_VALID"
    )
    a1["ordered_read_classes"].pop()
    _resign_manifest(checker, manifest)
    with pytest.raises(
        checker.DependencyClosureError, match="operator dependency contract"
    ):
        checker.validate_dependency_manifest(manifest)


def test_case435_dependency_manifest_rejects_unconditioned_field_claim() -> None:
    checker = _load_checker()
    manifest = copy.deepcopy(checker.analyze(ROOT)["case435_dependency_manifest"])
    manifest["separator_contract"]["unconditional_field_independence_forbidden"] = False
    _resign_manifest(checker, manifest)
    with pytest.raises(checker.DependencyClosureError, match="separator contract"):
        checker.validate_dependency_manifest(manifest)


def test_case435_factorization_proof_rejects_premature_maximum_claim() -> None:
    checker = _load_checker()
    report = checker.analyze(ROOT)
    proof = copy.deepcopy(report["case435_conditional_factorization_proof"])
    proof["exact_maximum_derived"] = True
    _resign_proof(checker, proof)
    with pytest.raises(
        checker.DependencyClosureError, match="factorization disposition"
    ):
        checker.validate_factorization_proof(
            proof,
            report["case435_dependency_manifest"],
        )


def test_case435_dependency_closure_rejects_runtime_source_drift(
    tmp_path: Path,
) -> None:
    checker = _load_checker()
    _copy_authority_tree(checker, tmp_path)
    runtime = tmp_path / checker.RULE_RUNTIME_RELATIVE_PATH
    runtime.write_text(runtime.read_text() + "\n# drift\n")
    with pytest.raises(
        checker.DependencyClosureError, match="rule runtime hash differs"
    ):
        checker.analyze(tmp_path)
