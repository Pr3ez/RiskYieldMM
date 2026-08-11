"""Independent fail-closed checks for the S1-A4/A4-B0 V2 boundary.

This suite consumes only the frozen boundary, S1-A3 authority bundle, and
repository files.  It imports no future verifier, producer, pilot runner, seed
generator, preflight implementation, or production RiskYieldMM module.
"""

from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
BOUNDARY_PATH = (
    ROOT
    / "scripts/tests/raw_v8_step2_maximum_protocol_v2_constructive_boundary_v49f.json"
)
BOUNDARY_DOMAIN = "RiskYieldMMStep2ConstructiveExecutionBoundaryV1V4_9F_RawV8"
F2_CATALOG_DOMAIN = "RiskYieldMMStep2F2ResourceLimitCatalogV1V4_9F_RawV8"
SEED_PATH = (
    ROOT / "scripts/tests/raw_v8_step2_maximum_protocol_v2_seed_catalog_v49f.json"
)
MANIFEST_PATH = (
    ROOT
    / "scripts/tests/raw_v8_step2_maximum_protocol_v2_finalization_manifest_v49f.json"
)

EXPECTED_ROOT_MEMBERS = [
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
EXPECTED_PILOT_CASES = [5, 24, 54, 69, 435, 475]
EXPECTED_MAXIMUM_ATTAINER_MEMBERS = [
    "artifact_version",
    "canonicalization_version",
    "measurement_schema_version",
    "maximum_protocol_sha256",
    "source_inventory_sha256",
    "external_schema_registry_id",
    "rule_literal_authority_sha256",
    "type_name",
    "alternative_name",
    "constraint_scope",
    "constraint_scope_id",
    "constraint_scope_profile_id",
    "witness_kind",
    "canonical_byte_length",
    "certified_analytic_maximum_octets",
    "codec_byte_bound_relation",
    "codec_octet_limit",
    "codec_slack_octets",
    "canonical_sha256",
    "witness_record",
    "scope_witness_context",
    "required_context_object_count",
    "ordered_required_context_object_ids",
    "row_context_closure_id",
    "upper_bound_certificate",
    "proof_resource_report",
    "maximum_attainer_id",
]
EXPECTED_LOCAL_RESULT_MEMBERS = [
    "artifact_version",
    "canonicalization_version",
    "measurement_schema_version",
    "maximum_protocol_sha256",
    "source_inventory_sha256",
    "external_schema_registry_id",
    "rule_literal_authority_sha256",
    "constraint_scope_profile_id",
    "baseline_spec_record_reference",
    "mutated_limit_members",
    "mutated_spec",
    "changed_limit_field_count",
    "sum_absolute_integer_deltas",
    "prospective_result",
    "prospective_result_canonical_byte_length",
    "outer_codec_byte_bound_relation",
    "outer_codec_octet_limit",
    "expected_rejection_coordinate",
    "minimality_certificate",
    "proof_resource_report",
    "local_shutdown_unrepresentable_id",
]


def _duplicate_key_guard(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def _reject_constant(value: str) -> Any:
    raise ValueError(f"non-finite JSON constant: {value}")


def _reject_float(value: str) -> Any:
    raise ValueError(f"floating JSON number: {value}")


def _strict_loads(raw: bytes) -> dict[str, Any]:
    text = raw.decode("utf-8", errors="strict")
    if text.startswith("\ufeff"):
        raise ValueError("BOM is forbidden")
    value = json.loads(
        text,
        object_pairs_hook=_duplicate_key_guard,
        parse_constant=_reject_constant,
        parse_float=_reject_float,
    )
    assert type(value) is dict
    return value


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _pretty_bytes_in_order(value: Any) -> bytes:
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


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _semantic_id(domain: str, payload: Any) -> str:
    return _sha256(_canonical_bytes({"domain": domain, "payload": payload}))


def _boundary() -> dict[str, Any]:
    return _strict_loads(BOUNDARY_PATH.read_bytes())


def _reseal(boundary: dict[str, Any]) -> None:
    payload = {
        name: value
        for name, value in boundary.items()
        if name != "constructive_boundary_id"
    }
    boundary["constructive_boundary_id"] = _semantic_id(BOUNDARY_DOMAIN, payload)


def _assert_sha256(value: Any) -> None:
    assert type(value) is str
    assert len(value) == 64
    assert all(character in "0123456789abcdef" for character in value)


def _safe_repository_path(value: Any) -> Path:
    assert type(value) is str and value
    relative = Path(value)
    assert not relative.is_absolute()
    assert ".." not in relative.parts
    assert "" not in relative.parts
    path = ROOT / relative
    assert path.is_file() and not path.is_symlink()
    return path


def _validate_file_authority(authority: dict[str, Any]) -> bytes:
    path = _safe_repository_path(authority["repository_relative_path"])
    raw = path.read_bytes()
    assert len(raw) == authority["raw_octets"]
    assert _sha256(raw) == authority["raw_sha256"]
    return raw


def _validate(boundary: dict[str, Any]) -> None:
    assert list(boundary) == EXPECTED_ROOT_MEMBERS
    assert boundary["boundary_version"] == (
        "riskyieldmm.raw_v8_step2_external_schema_v2.constructive_execution_boundary.v1"
    )
    assert boundary["canonicalization_version"] == "riskyieldmm_canonical_json_v1"
    assert boundary["measurement_schema_version"] == (
        "riskyieldmm_physical_transport_a2m_raw_v49f_v8"
    )
    assert boundary["protocol_version"] == (
        "riskyieldmm.raw_v8_step2_external_schema_v2.constructive_maximum_protocol.v2"
    )
    assert boundary["boundary_status"] == "A4_B0_V2_ONLY_BOUNDARY_FROZEN"

    identity_payload = {
        name: value
        for name, value in boundary.items()
        if name != "constructive_boundary_id"
    }
    assert boundary["constructive_boundary_id"] == _semantic_id(
        BOUNDARY_DOMAIN, identity_payload
    )

    authority = boundary["authority_contract"]
    assert set(authority) == {
        "seed_authority",
        "finalization_manifest_authority",
        "downstream_field_binding_rules",
        "f2_resource_limit_catalog",
        "candidate_read_barrier",
        "authority_drift_policy",
    }
    seed_authority = authority["seed_authority"]
    manifest_authority = authority["finalization_manifest_authority"]
    seed_raw = _validate_file_authority(seed_authority)
    manifest_raw = _validate_file_authority(manifest_authority)
    seed = _strict_loads(seed_raw)
    manifest = _strict_loads(manifest_raw)
    assert seed_authority["seed_catalog_id"] == seed["seed_catalog_id"]
    assert (
        seed_authority["protocol_counting_semantics_id"]
        == (seed["protocol_counting_semantics_id"])
    )
    assert (
        seed_authority["ordered_authority_binding_record_count"]
        == len(seed["ordered_authority_binding_records"])
        == 17
    )
    assert (
        manifest_authority["finalization_manifest_id"]
        == (manifest["finalization_manifest_id"])
    )
    assert (
        manifest_authority["finalization_status"]
        == (manifest["finalization_status"])
        == "FINAL_V2_F2_FROZEN"
    )
    assert (
        manifest_authority["semantic_payload_id"]
        == (manifest["semantic_evidence"]["semantic_payload_id"])
    )
    assert (
        manifest_authority["semantic_count_vector_sha256"]
        == (manifest["semantic_evidence"]["semantic_count_vector_sha256"])
    )
    assert (
        manifest_authority["comparison_payload_id"]
        == (manifest["comparison_evidence"]["comparison_payload_id"])
    )
    assert (
        manifest_authority["ordered_f2_limit_record_count"]
        == len(manifest["ordered_f2_limit_records"])
        == 18
    )
    assert manifest["seed_authority"]["seed_catalog_id"] == seed["seed_catalog_id"]
    assert manifest["seed_authority"]["raw_sha256"] == _sha256(seed_raw)

    seen_authority_paths: set[str] = set()
    seen_authority_inodes: set[tuple[int, int]] = set()
    for position, row in enumerate(seed["ordered_authority_binding_records"], 1):
        assert row["authority_position"] == position
        path = _safe_repository_path(row["repository_relative_path"])
        raw = path.read_bytes()
        assert len(raw) == row["raw_octet_count"]
        assert _sha256(raw) == row["raw_sha256"]
        assert row["repository_relative_path"] not in seen_authority_paths
        inode = (path.stat().st_dev, path.stat().st_ino)
        assert inode not in seen_authority_inodes
        seen_authority_paths.add(row["repository_relative_path"])
        seen_authority_inodes.add(inode)

    bindings = authority["downstream_field_binding_rules"]
    assert bindings == {
        "maximum_protocol_sha256": "FINALIZATION_MANIFEST_AUTHORITY_RAW_SHA256",
        "seed_catalog_id": "SEED_AUTHORITY_SEED_CATALOG_ID",
        "finalization_manifest_id": "FINALIZATION_MANIFEST_AUTHORITY_ID",
        "source_inventory_sha256": (
            "SEED_ORDERED_AUTHORITY_ROLE_V4_INVENTORY_SEMANTIC_ID"
        ),
        "external_schema_registry_id": (
            "SEED_ORDERED_AUTHORITY_ROLE_STRUCTURAL_REGISTRY_SEMANTIC_ID"
        ),
        "rule_literal_authority_sha256": (
            "SEED_ORDERED_AUTHORITY_ROLE_RULE_LITERAL_AUTHORITY_RAW_SHA256"
        ),
        "derivation_catalog_id": "SEED_RECURRENCE_CATALOG_ID",
        "derivation_plan_id": "SEED_LOGICAL_COUNT_PLAN_ID_FOR_EXACT_CASE_POSITION",
        "ordered_safe_relaxation_rule_ids": (
            "SEED_LOGICAL_COUNT_PLAN_ORDERED_SAFE_RELAXATION_RULE_IDS"
        ),
        "upper_bound_mode": "SEED_LOGICAL_COUNT_PLAN_UPPER_BOUND_MODE",
        "resource_limit_catalog_id": "DERIVED_F2_RESOURCE_LIMIT_CATALOG_ID",
    }
    assert manifest_authority["raw_sha256"] == _sha256(manifest_raw)

    f2_catalog = authority["f2_resource_limit_catalog"]
    assert f2_catalog["ordered_identity_payload_member_names"] == [
        "catalog_version",
        "protocol_version",
        "seed_catalog_id",
        "finalization_manifest_id",
        "ordered_f2_limit_records",
    ]
    f2_payload = {
        "catalog_version": f2_catalog["catalog_version"],
        "protocol_version": boundary["protocol_version"],
        "seed_catalog_id": seed["seed_catalog_id"],
        "finalization_manifest_id": manifest["finalization_manifest_id"],
        "ordered_f2_limit_records": manifest["ordered_f2_limit_records"],
    }
    assert f2_catalog["identity_domain"] == F2_CATALOG_DOMAIN
    assert f2_catalog["ordered_f2_limit_records_source"] == (
        "/ordered_f2_limit_records"
    )
    assert f2_catalog["f2_resource_limit_catalog_id"] == _semantic_id(
        F2_CATALOG_DOMAIN, f2_payload
    )
    assert authority["candidate_read_barrier"] == (
        "ALL_AUTHORITIES_AND_SOURCE_SNAPSHOTS_ACCEPTED_BEFORE_OPENING_ANY_"
        "CANDIDATE_PATH"
    )
    assert authority["authority_drift_policy"].startswith("RECHECK_EVERY_AUTHORITY")

    roles = boundary["implementation_role_contract"]
    role_records = roles["ordered_role_records"]
    assert [row["role_position"] for row in role_records] == [1, 2, 3]
    assert [row["role_name"] for row in role_records] == [
        "INDEPENDENT_VERIFIER",
        "SEPARATE_PRODUCER",
        "PARENT_PILOT_RUNNER",
    ]
    paths = [row["repository_relative_path"] for row in role_records]
    assert len(paths) == len(set(paths)) == 3
    assert all(path.startswith("scripts/tests/") for path in paths)
    assert all("maximum_protocol_pilot_v49f.py" not in path for path in paths)
    assert [row["semantic_authority"] for row in role_records] == [True, False, False]
    assert [row["may_execute_other_role"] for row in role_records] == [
        False,
        False,
        True,
    ]
    cli = roles["single_case_cli_contract"]
    assert cli["python_isolation_flags"] == ["-I", "-S", "-B"]
    assert cli["launch_policy"] == (
        "FORK_SETRLIMIT_EXECVE_NO_SHELL_FIXED_ARGV_MINIMAL_ENVIRONMENT"
    )
    assert cli["producer_argument_order_after_python_isolation_flags"][0] == (
        "PRODUCER_PATH"
    )
    assert cli["verifier_argument_order_after_python_isolation_flags"][0] == (
        "VERIFIER_PATH"
    )
    assert cli["success_exit_code"] == 0
    assert cli["success_stdout_policy"] == cli["success_stderr_policy"] == "EMPTY"
    assert roles["unknown_or_extra_role_policy"] == "REJECT"

    candidate = boundary["candidate_bundle_contract"]
    assert candidate["bundle_root_member_paths"] == [
        "candidate.json",
        "context_objects",
    ]
    envelope = candidate["candidate_envelope_schema"]
    assert envelope["ordered_member_names"] == [
        "candidate_version",
        "canonicalization_version",
        "measurement_schema_version",
        "protocol_version",
        "seed_catalog_id",
        "finalization_manifest_id",
        "case_position",
        "case_kind",
        "case_binding",
        "logical_count_plan_id",
        "candidate_payload",
        "constructive_candidate_id",
    ]
    assert envelope["case_binding_rule"] == (
        "EXACT_DEEP_EQUALITY_WITH_SEED_CASE_BINDING_AT_CASE_POSITION"
    )
    assert envelope["logical_count_plan_rule"] == "EXACT_SEED_PLAN_ID_AT_CASE_POSITION"
    assert envelope["identity_covers_every_preceding_member"] is True
    alternatives = candidate["candidate_payload_tagged_union"][
        "ordered_alternative_records"
    ]
    assert [row["alternative_position"] for row in alternatives] == [1, 2]
    assert [row["candidate_kind"] for row in alternatives] == [
        "MAXIMUM_WITNESS_CONTEXT",
        "LOCAL_SHUTDOWN_MUTATION",
    ]
    assert alternatives[0]["ordered_member_names"] == [
        "candidate_kind",
        "witness_record",
        "scope_witness_context",
        "ordered_context_object_entries",
    ]
    assert alternatives[1]["ordered_member_names"] == [
        "candidate_kind",
        "mutated_spec",
        "prospective_result",
    ]
    allowed_candidate_members = set(envelope["ordered_member_names"])
    for alternative in alternatives:
        allowed_candidate_members.update(alternative["ordered_member_names"])
    assert not allowed_candidate_members.intersection(
        candidate["forbidden_producer_claim_member_names"]
    )
    context = candidate["context_object_entry_schema"]
    assert context["ordered_member_names"] == [
        "context_object_position",
        "claimed_maximum_context_object_id",
        "record_type_name",
        "repository_relative_path",
        "raw_octet_count",
        "raw_sha256",
    ]
    assert context["identity_rule"].startswith("VERIFIER_RECOMPUTES")
    assert candidate["producer_to_verifier_channel_rule"].startswith(
        "CLOSED_CANDIDATE_BUNDLE"
    )

    output = boundary["verifier_output_contract"]
    assert output["maximum_attainer_schema"]["ordered_member_names"] == (
        EXPECTED_MAXIMUM_ATTAINER_MEMBERS
    )
    assert output["maximum_attainer_schema"]["acceptance_rule"] == (
        "P1_LEGAL_AND_P2_SOUND_UPPER_BOUND_AND_P3_EXACT_ATTAINMENT"
    )
    assert output["local_shutdown_result_schema"]["ordered_member_names"] == (
        EXPECTED_LOCAL_RESULT_MEMBERS
    )
    assert output["upper_bound_certificate_schema"]["ordered_member_names"] == [
        "certificate_version",
        "maximum_protocol_sha256",
        "derivation_scope_id",
        "upper_bound_mode",
        "derivation_catalog_id",
        "derivation_plan_id",
        "ordered_safe_relaxation_rule_ids",
        "certified_upper_bound_octets",
        "streamed_derivation_result_sha256",
        "upper_bound_certificate_id",
    ]
    assert (
        "ordered_component_choice_evidence"
        in output["upper_bound_certificate_schema"]["forbidden_member_names"]
    )
    resource_report = output["proof_resource_report_schema"]
    assert resource_report["ordered_member_names"][-2:] == [
        "ordered_resource_measurements",
        "proof_resource_report_id",
    ]
    assert resource_report["self_charge_policy"].startswith("REPORT_NEVER_CHARGES")
    receipt = output["verification_receipt_schema"]
    assert receipt["ordered_member_names"][-1] == "verification_receipt_id"
    assert receipt["maximum_status"] == "P1_P2_P3_ACCEPTED"
    assert receipt["local_status"] == "LOCAL_MINIMALITY_ACCEPTED"
    assert "upper_bound_certificate" in output["verifier_derived_only_fields"]
    assert (
        "winning_objective"
        not in candidate["candidate_payload_tagged_union"][
            "ordered_alternative_records"
        ][1]["ordered_member_names"]
    )

    pilot = boundary["pilot_contract"]
    pilot_rows = pilot["ordered_pilot_case_records"]
    assert [row["pilot_position"] for row in pilot_rows] == list(range(1, 7))
    assert [row["case_position"] for row in pilot_rows] == EXPECTED_PILOT_CASES
    assert len({row["coverage_tag"] for row in pilot_rows}) == 6
    seed_cases = {
        row["case_position"]: row
        for row in seed["case_universe_catalog"]["ordered_case_bindings"]
    }
    seed_plans = {
        row["case_position"]: row
        for row in seed["logical_plan_recipe_catalog"][
            "ordered_logical_count_plan_records"
        ]
    }
    for row in pilot_rows:
        position = row["case_position"]
        assert row["case_kind"] == seed_cases[position]["case_kind"]
        assert (
            row["logical_count_plan_id"]
            == seed_plans[position]["logical_count_plan_id"]
        )
    assert seed_cases[69]["case_binding"]["row_position"] == 69
    assert seed_cases[475]["case_kind"] == ("LOCAL_SHUTDOWN_UNREPRESENTABLE_MINIMALITY")
    assert pilot["execution_order"].startswith("FOR_EACH_PILOT_POSITION")
    assert "NO_PILOT_OBSERVATION_MAY_RAISE_OR_REPAIR" in pilot["limit_rule"]
    assert pilot["acceptance_rule"] == (
        "ALL_SIX_CASES_ACCEPT_OR_THE_COMPLETE_PILOT_IS_NO_GO"
    )
    assert pilot["publication_rule"].endswith(
        "DO_NOT_SELECT_OR_AUTHORIZE_THE_474_ROW_PUBLICATION"
    )
    pilot_schema = pilot["pilot_manifest_schema"]
    assert pilot_schema["ordered_member_names"][-1] == (
        "constructive_pilot_manifest_id"
    )
    assert pilot_schema["case_result_entry_ordered_member_names"][:4] == [
        "pilot_position",
        "case_position",
        "case_kind",
        "logical_count_plan_id",
    ]
    assert pilot["canonical_output_root"].startswith("test_output/")

    resources = boundary["resource_enforcement_contract"]
    assert resources["semantic_metric_limit_source"] == (
        "FINALIZATION_MANIFEST_ORDERED_F2_LIMIT_RECORDS"
    )
    assert resources["f2_metric_position_rule"] == (
        "EXACTLY_CONTIGUOUS_POSITIONS_1_THROUGH_18"
    )
    assert "BEFORE_CHARGED_OPERATION" in resources["semantic_metric_case_rule"]
    assert "SUM_OR_MAX_EXACTLY_AS_FROZEN" in resources["semantic_metric_full_run_rule"]
    assert resources["process_platform_limit_source"] == (
        "SEED_F0_ORDERED_PLATFORM_CEILING_RECORDS"
    )
    assert resources["checked_arithmetic"] == (
        "UNSIGNED_128_BIT_INTERMEDIATE_AND_SAFE_INTEGER_SERIALIZATION"
    )
    assert resources["resource_observation_program"] == {
        "wall_source": "MONOTONIC_NS_BEFORE_FORK_THROUGH_WAIT4_RETURN",
        "cpu_source": "WAIT4_RUSAGE_USER_PLUS_SYSTEM_NANOSECONDS",
        "peak_rss_source": "WAIT4_RUSAGE_MAXRSS_KIB_TIMES_1024_ON_LINUX",
        "temporary_storage_source": (
            "MAXIMUM_ALLOCATED_ST_BLOCKS_TIMES_512_IN_PRIVATE_OUTPUT_DIRECTORY"
        ),
    }
    assert resources["pilot_excess_policy"].startswith("CONTROLLED_NO_GO")

    filesystem = boundary["filesystem_contract"]
    assert "O_NOFOLLOW" in filesystem["input_open_policy"]
    assert filesystem["input_type_policy"] == (
        "DIRECT_REGULAR_SINGLE_LINK_UNIQUE_DEVICE_INODE"
    )
    assert filesystem["unexpected_file_policy"] == "REJECT"
    assert filesystem["hardlink_symlink_fifo_device_socket_policy"] == "REJECT"
    assert filesystem["network_policy"] == "NO_NETWORK_NAMESPACE_OR_SOCKET_USE"
    assert filesystem["candidate_root_policy"].startswith("PRODUCER_PUBLISHES_ABSENT")
    assert filesystem["verified_root_policy"].startswith("VERIFIER_PUBLISHES_ABSENT")

    independence = boundary["independence_contract"]
    assert independence["shared_executable_code_policy"] == (
        "NONE_BETWEEN_VERIFIER_AND_PRODUCER"
    )
    forbidden_imports = set(independence["forbidden_import_roots"])
    allowed_imports = set(independence["allowed_standard_library_import_roots"])
    assert forbidden_imports.isdisjoint(allowed_imports)
    assert {
        "riskyieldmm",
        "scripts",
        "tests",
        "subprocess",
        "socket",
        "unicodedata",
        "importlib",
        "inspect",
    } <= forbidden_imports
    assert "PRODUCER_SOURCE" in independence["verifier_forbidden_reads"]
    assert "VERIFIER_SOURCE" in independence["producer_forbidden_reads"]
    assert independence["subprocess_policy"] == (
        "VERIFIER_AND_PRODUCER_FORBIDDEN_RUNNER_ONLY_FIXED_EXECVE"
    )
    assert independence["candidate_authority_policy"].startswith("CANDIDATE_IS_DATA")

    legacy = boundary["legacy_v1_exclusion_contract"]
    for key in (
        "rejected_protocol_authority",
        "rejected_bootstrap_authority",
        "accepted_rejection_authority",
    ):
        raw = _validate_file_authority(legacy[key])
        fragment = legacy[key].get("required_status_fragment") or legacy[key].get(
            "required_module_fragment"
        )
        if fragment is not None:
            assert fragment.encode("utf-8") in raw
    assert (
        "ordered_component_choice_evidence"
        in legacy["forbidden_input_or_output_fragments"]
    )
    assert "V3_INVENTORY_POINTER" in legacy["forbidden_input_or_output_fragments"]
    assert legacy["legacy_execution_policy"].startswith("NEITHER_VERIFIER")
    assert "ZERO_PILOT_COVERAGE_CREDIT" in legacy["legacy_structural_self_test_policy"]
    assert legacy["v2_relabel_policy"].startswith("NO_V1_PATH_VERSION")


def test_constructive_boundary_is_canonical_closed_and_authority_complete() -> None:
    raw = BOUNDARY_PATH.read_bytes()
    boundary = _strict_loads(raw)
    assert raw == _pretty_bytes_in_order(boundary)
    _validate(boundary)


def test_constructive_boundary_contains_no_expected_witness_or_result_vector() -> None:
    boundary = _boundary()
    encoded = _canonical_bytes(boundary).decode("utf-8")
    forbidden_fragments = (
        "expected_witness_record",
        "expected_upper_bound_octets",
        "ordered_expected_case_results",
        "ordered_expected_maximum_attainer_ids",
        "accepted_candidate_bytes",
        "pilot_derived_f2",
    )
    assert all(fragment not in encoded for fragment in forbidden_fragments)
    assert len(boundary["pilot_contract"]["ordered_pilot_case_records"]) == 6


@pytest.mark.parametrize(
    "mutation",
    [
        "BOUNDARY_ID",
        "UNKNOWN_ROOT_MEMBER",
        "MANIFEST_HASH",
        "PROTOCOL_FIELD_MAPPING",
        "F2_CATALOG_ID",
        "VERIFIER_NOT_AUTHORITY",
        "ROLE_PATH_COLLISION",
        "PRODUCER_UPPER_BOUND_CLAIM",
        "WEAK_CASE_BINDING",
        "MAXIMUM_SCHEMA_WITHOUT_RESOURCE_REPORT",
        "LOCAL_SCHEMA_WITHOUT_RESOURCE_REPORT",
        "F2_SOURCE_REPLACED_BY_F0",
        "PILOT_DUPLICATE_CASE",
        "PILOT_WRONG_PLAN",
        "PILOT_LIMIT_TUNING",
        "SHARED_EXECUTABLE_CODE",
        "ALLOW_RISKYIELDMM_IMPORT",
        "ALLOW_SYMLINK",
        "LEGACY_BOOTSTRAP_AS_PRODUCER",
        "LEGACY_COVERAGE_CREDIT",
    ],
)
def test_constructive_boundary_rejects_hostile_mutations(mutation: str) -> None:
    boundary = copy.deepcopy(_boundary())
    if mutation == "BOUNDARY_ID":
        boundary["constructive_boundary_id"] = "0" * 64
    elif mutation == "UNKNOWN_ROOT_MEMBER":
        boundary["extra"] = None
        _reseal(boundary)
    elif mutation == "MANIFEST_HASH":
        boundary["authority_contract"]["finalization_manifest_authority"][
            "raw_sha256"
        ] = "0" * 64
        _reseal(boundary)
    elif mutation == "PROTOCOL_FIELD_MAPPING":
        boundary["authority_contract"]["downstream_field_binding_rules"][
            "maximum_protocol_sha256"
        ] = "SEED_RAW_SHA256"
        _reseal(boundary)
    elif mutation == "F2_CATALOG_ID":
        boundary["authority_contract"]["f2_resource_limit_catalog"][
            "f2_resource_limit_catalog_id"
        ] = "0" * 64
        _reseal(boundary)
    elif mutation == "VERIFIER_NOT_AUTHORITY":
        boundary["implementation_role_contract"]["ordered_role_records"][0][
            "semantic_authority"
        ] = False
        _reseal(boundary)
    elif mutation == "ROLE_PATH_COLLISION":
        roles = boundary["implementation_role_contract"]["ordered_role_records"]
        roles[1]["repository_relative_path"] = roles[0]["repository_relative_path"]
        _reseal(boundary)
    elif mutation == "PRODUCER_UPPER_BOUND_CLAIM":
        boundary["candidate_bundle_contract"]["candidate_payload_tagged_union"][
            "ordered_alternative_records"
        ][0]["ordered_member_names"].append("upper_bound_certificate")
        _reseal(boundary)
    elif mutation == "WEAK_CASE_BINDING":
        boundary["candidate_bundle_contract"]["candidate_envelope_schema"][
            "case_binding_rule"
        ] = "TRUST_PRODUCER"
        _reseal(boundary)
    elif mutation == "MAXIMUM_SCHEMA_WITHOUT_RESOURCE_REPORT":
        boundary["verifier_output_contract"]["maximum_attainer_schema"][
            "ordered_member_names"
        ].remove("proof_resource_report")
        _reseal(boundary)
    elif mutation == "LOCAL_SCHEMA_WITHOUT_RESOURCE_REPORT":
        boundary["verifier_output_contract"]["local_shutdown_result_schema"][
            "ordered_member_names"
        ].remove("proof_resource_report")
        _reseal(boundary)
    elif mutation == "F2_SOURCE_REPLACED_BY_F0":
        boundary["resource_enforcement_contract"]["semantic_metric_limit_source"] = (
            "SEED_F0_ORDERED_METRIC_RECORDS"
        )
        _reseal(boundary)
    elif mutation == "PILOT_DUPLICATE_CASE":
        rows = boundary["pilot_contract"]["ordered_pilot_case_records"]
        rows[5]["case_position"] = rows[4]["case_position"]
        _reseal(boundary)
    elif mutation == "PILOT_WRONG_PLAN":
        boundary["pilot_contract"]["ordered_pilot_case_records"][0][
            "logical_count_plan_id"
        ] = "0" * 64
        _reseal(boundary)
    elif mutation == "PILOT_LIMIT_TUNING":
        boundary["pilot_contract"]["limit_rule"] = "RAISE_F2_AFTER_PILOT"
        _reseal(boundary)
    elif mutation == "SHARED_EXECUTABLE_CODE":
        boundary["independence_contract"]["shared_executable_code_policy"] = (
            "COMMON_RECURRENCE_HELPER_ALLOWED"
        )
        _reseal(boundary)
    elif mutation == "ALLOW_RISKYIELDMM_IMPORT":
        boundary["independence_contract"]["forbidden_import_roots"].remove(
            "riskyieldmm"
        )
        _reseal(boundary)
    elif mutation == "ALLOW_SYMLINK":
        boundary["filesystem_contract"][
            "hardlink_symlink_fifo_device_socket_policy"
        ] = "ALLOW_SYMLINK"
        _reseal(boundary)
    elif mutation == "LEGACY_BOOTSTRAP_AS_PRODUCER":
        boundary["implementation_role_contract"]["ordered_role_records"][1][
            "repository_relative_path"
        ] = boundary["legacy_v1_exclusion_contract"]["rejected_bootstrap_authority"][
            "repository_relative_path"
        ]
        _reseal(boundary)
    elif mutation == "LEGACY_COVERAGE_CREDIT":
        boundary["legacy_v1_exclusion_contract"][
            "legacy_structural_self_test_policy"
        ] = "COUNTS_AS_ONE_PILOT_CASE"
        _reseal(boundary)
    else:  # pragma: no cover - the parametrization is closed above.
        raise AssertionError(mutation)

    with pytest.raises(AssertionError):
        _validate(boundary)


@pytest.mark.parametrize(
    "raw",
    [
        b'{"a":1,"a":2}',
        b'{"a":1.5}',
        b'{"a":NaN}',
        b'\xef\xbb\xbf{"a":1}',
    ],
)
def test_constructive_boundary_strict_json_rejects_invalid_forms(raw: bytes) -> None:
    with pytest.raises((AssertionError, UnicodeDecodeError, ValueError)):
        _strict_loads(raw)


@pytest.mark.parametrize("mode", ["--check", "--write"])
def test_constructive_boundary_keeps_v1_bootstrap_fail_closed(mode: str) -> None:
    legacy = _boundary()["legacy_v1_exclusion_contract"]
    bootstrap = (
        ROOT / legacy["rejected_bootstrap_authority"]["repository_relative_path"]
    )
    guarded_paths = (
        ROOT
        / "scripts/tests/raw_v8_step2_external_schema_v2_maximum_protocol_pilot_v49f.json",
        ROOT
        / "scripts/tests/raw_v8_step2_external_schema_v2_maximum_protocol_pilot_seed_v49f.json",
        ROOT
        / "scripts/tests/raw_v8_step2_external_schema_v2_maximum_protocol_pilot_seed_protocol_v49f.md",
    )
    before = {
        path: (path.exists(), _sha256(path.read_bytes()) if path.is_file() else None)
        for path in guarded_paths
    }
    completed = subprocess.run(
        [
            sys.executable,
            str(bootstrap),
            "--repository-root",
            str(ROOT),
            mode,
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 2
    assert completed.stdout == ""
    assert f"canonical {mode} refused for rejected protocol V1" in completed.stderr
    assert "94,905-coordinate and 94,906-node/depth" in completed.stderr
    assert {
        path: (path.exists(), _sha256(path.read_bytes()) if path.is_file() else None)
        for path in guarded_paths
    } == before
