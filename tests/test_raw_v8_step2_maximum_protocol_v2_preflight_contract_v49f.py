"""Fail-closed tests for the shared S1-A2 preflight boundary.

The two counters may share frozen data contracts, but no executable helper.
This suite validates that boundary without importing the seed generator or any
future A/B implementation.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = (
    ROOT / "scripts/tests/raw_v8_step2_maximum_protocol_v2_preflight_contract_v49f.json"
)
CONTRACT_DOMAIN = "RiskYieldMMStep2PreflightExecutionContractV1V4_9F_RawV8"
U128_MAX = (1 << 128) - 1


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


def _contract() -> dict[str, Any]:
    value = json.loads(CONTRACT_PATH.read_bytes())
    assert type(value) is dict
    return value


def _json_pointer(root: Any, pointer: str) -> Any:
    assert pointer.startswith("/")
    value = root
    for raw_part in pointer[1:].split("/"):
        part = raw_part.replace("~1", "/").replace("~0", "~")
        if type(value) is list:
            assert part == "0" or not part.startswith("0")
            value = value[int(part)]
        else:
            assert type(value) is dict and part in value
            value = value[part]
    return value


def _validate(contract: dict[str, Any]) -> None:
    assert set(contract) == {
        "contract_id",
        "contract_version",
        "error_taxonomy",
        "implementation_separation_policy",
        "input_authority",
        "report_contract",
        "resource_enforcement_contract",
        "unknown_or_extra_member_policy",
    }
    assert contract["contract_version"] == (
        "riskyieldmm.raw_v8_step2_external_schema_v2.preflight_execution_contract.v1"
    )
    assert contract["unknown_or_extra_member_policy"] == "REJECT"
    identity_payload = {
        name: value for name, value in contract.items() if name != "contract_id"
    }
    assert contract["contract_id"] == _sha256(
        _canonical_bytes({"domain": CONTRACT_DOMAIN, "payload": identity_payload})
    )

    authority = contract["input_authority"]
    seed_path = ROOT / authority["sole_authorized_repository_relative_path"]
    seed_raw = seed_path.read_bytes()
    seed = json.loads(seed_raw)
    assert type(seed) is dict
    assert len(seed_raw) == authority["accepted_catalog_raw_octets"]
    assert _sha256(seed_raw) == authority["accepted_catalog_raw_sha256"]
    assert seed["seed_catalog_id"] == authority["accepted_catalog_id"]
    assert seed["catalog_version"] == authority["accepted_catalog_version"]
    assert (
        seed["protocol_counting_semantics_id"]
        == authority["accepted_protocol_counting_semantics_id"]
    )
    assert seed["canonicalization_version"] == authority["canonicalization_version"]
    assert seed["measurement_schema_version"] == authority["measurement_schema_version"]
    case_universe = seed["case_universe_catalog"]
    assert (
        case_universe["verifier_owned_case_count"]
        == authority["expected_verifier_owned_case_count"]
    )
    assert case_universe["maximum_row_count"] == authority["maximum_row_count"]
    assert (
        case_universe["maximum_row_universe_canonical_json_sha256"]
        == authority["maximum_row_universe_canonical_json_sha256"]
    )
    roots = authority["ordered_required_semantic_root_records"]
    assert [row["root_position"] for row in roots] == list(range(1, 7))
    assert len({row["root_name"] for row in roots}) == 6
    for row in roots:
        root_name = row["root_name"]
        assert root_name in seed
        id_member = f"{root_name}_id"
        assert seed[root_name][id_member] == row["expected_id"]
    assert authority["file_open_policy"] == (
        "OPEN_ONCE_NOFOLLOW_REGULAR_FILE_FSTAT_BEFORE_AND_AFTER_READ"
    )
    assert authority["input_read_policy"] == ("EXACT_ACCEPTED_OCTETS_THEN_REQUIRE_EOF")
    assert authority["input_file_count"] == 1

    report = contract["report_contract"]
    assert report["version_literals"] == {
        "comparison_payload_version": (
            "riskyieldmm.raw_v8_step2_external_schema_v2."
            "preflight_comparison_payload.v1"
        ),
        "execution_envelope_version": (
            "riskyieldmm.raw_v8_step2_external_schema_v2."
            "preflight_execution_envelope.v1"
        ),
        "preflight_semantic_payload_version": (
            "riskyieldmm.raw_v8_step2_external_schema_v2.preflight_semantic_payload.v1"
        ),
    }
    assert report["case_result_record_schema"]["ordered_member_names"] == [
        "case_position",
        "case_kind",
        "case_binding",
        "logical_count_plan_id",
        "result_status",
        "ordered_resource_measurements",
        "derivation_event_stream_sha256",
        "case_result_record_id",
    ]
    assert report["case_result_record_schema"]["expected_result_status"] == ("ACCEPT")
    assert report["resource_measurement_record_schema"] == {
        "integer_kind": "CHECKED_UINT128",
        "ordered_member_names": [
            "metric_position",
            "metric_name",
            "measured_value",
        ],
        "unknown_or_extra_member_policy": "REJECT",
    }
    assert report["metric_summary_record_schema"]["ordered_member_names"] == [
        "metric_position",
        "metric_name",
        "full_run_aggregation",
        "full_run_value",
        "maximum_case_value",
        "ordered_maximum_case_positions",
    ]
    semantic_members = report["preflight_semantic_payload_schema"][
        "ordered_member_names"
    ]
    assert semantic_members[0] == "preflight_semantic_payload_version"
    assert semantic_members[-2:] == [
        "semantic_count_vector_sha256",
        "semantic_payload_id",
    ]
    assert len(semantic_members) == len(set(semantic_members)) == 20
    assert report["ordered_case_rule"] == (
        "EXACTLY_CASE_POSITIONS_1_THROUGH_475_ONCE_EACH"
    )
    assert report["ordered_metric_rule"] == (
        "EXACTLY_SEED_METRIC_POSITIONS_1_THROUGH_18_ONCE_EACH"
    )
    assert report["wrapped_report_root_ordered_member_names"] == [
        "semantic_payload",
        "execution_envelope",
    ]
    assert set(report["identity_programs"]) == {
        "case_result_record_id",
        "comparison_payload_id",
        "semantic_count_vector_sha256",
        "semantic_payload_id",
    }

    separation = contract["implementation_separation_policy"]
    paths = [
        separation["implementation_a_repository_relative_path"],
        separation["implementation_b_repository_relative_path"],
        separation["comparator_repository_relative_path"],
    ]
    assert len(paths) == len(set(paths)) == 3
    assert separation["algorithm_markers"] == {
        "A": "ITERATIVE_CATALOG_INTERPRETER_V1",
        "B": "FLAT_LEDGER_PREFIX_SUM_V1",
    }
    assert separation["shared_executable_code_policy"] == "NONE_BETWEEN_A_AND_B"
    assert separation["shared_material_policy"] == (
        "PINNED_SEED_AND_THIS_DATA_CONTRACT_ONLY"
    )
    assert separation["local_module_import_policy"] == "FORBIDDEN"
    assert separation["implementation_files_must_have_distinct_raw_sha256"] is True
    assert separation["implementation_files_must_have_distinct_device_inode"] is True
    allowed = set(separation["allowed_preflight_standard_library_import_roots"])
    forbidden = set(separation["forbidden_import_roots"])
    assert allowed
    assert allowed.isdisjoint(forbidden)
    assert {"scripts", "tests", "riskyieldmm", "subprocess", "socket"} <= forbidden
    assert "THE_SEED_GENERATOR_SOURCE" in separation["forbidden_source_reads"]
    assert (
        "THE_OTHER_PREFLIGHT_SOURCE_OR_RESULT" in separation["forbidden_source_reads"]
    )

    resources = contract["resource_enforcement_contract"]
    limits = resources["ordered_f0_limit_records"]
    assert [row["limit_position"] for row in limits] == list(range(1, 13))
    seed_limit_rows = seed["f0_seed_ceiling_catalog"][
        "ordered_platform_ceiling_records"
    ]
    assert len(limits) == len(seed_limit_rows) == 12
    for contract_row, seed_row in zip(limits, seed_limit_rows, strict=True):
        assert contract_row["resource_name"] == seed_row["resource_name"]
        assert contract_row["expected_value"] == seed_row["ceiling_value"]
        assert (
            _json_pointer(seed, contract_row["seed_json_pointer"])
            == seed_row["ceiling_value"]
        )
        assert type(contract_row["expected_value"]) is int
        assert 0 < contract_row["expected_value"] <= U128_MAX
    assert resources["child_execution_program"]["launch_policy"] == (
        "FORK_SETRLIMIT_EXECVE_NO_SHELL"
    )
    assert resources["child_execution_program"]["argument_order"][1:4] == [
        "-I",
        "-S",
        "-B",
    ]
    assert resources["resource_observation_program"] == {
        "cpu_source": "WAIT4_RUSAGE_USER_PLUS_SYSTEM_NANOSECONDS",
        "peak_rss_source": "WAIT4_RUSAGE_MAXRSS_KIB_TIMES_1024_ON_LINUX",
        "temporary_storage_source": (
            "MAXIMUM_ALLOCATED_ST_BLOCKS_TIMES_512_IN_PRIVATE_OUTPUT_DIRECTORY"
        ),
        "wall_source": "MONOTONIC_NS_BEFORE_FORK_THROUGH_WAIT4_RETURN",
    }
    assert resources["atomic_output_program"]["publication_order"] == (
        "O_EXCL_TEMP_WRITE_FSYNC_CLOSE_LINK_NOREPLACE_UNLINK_TEMP_FSYNC_PARENT"
    )
    assert resources["atomic_output_program"]["failure_policy"] == (
        "REMOVE_PRIVATE_TEMPORARY_FILE_AND_PUBLISH_NOTHING"
    )

    errors = contract["error_taxonomy"]
    error_rows = errors["ordered_error_records"]
    assert [row["error_position"] for row in error_rows] == list(range(1, 19))
    assert len({row["error_code"] for row in error_rows}) == 18
    assert all(
        type(row["exit_code"]) is int and row["exit_code"] > 0 for row in error_rows
    )
    assert errors["success_exit_code"] == 0
    assert errors["success_stdout_policy"] == "EMPTY"
    assert errors["success_stderr_policy"] == "EMPTY"


def test_preflight_contract_is_canonical_and_closed() -> None:
    raw = CONTRACT_PATH.read_bytes()
    contract = json.loads(raw)
    assert raw == _pretty_bytes(contract)
    _validate(contract)


def test_preflight_contract_contains_no_expected_case_answer_vector() -> None:
    contract = _contract()
    encoded = _canonical_bytes(contract).decode("utf-8")
    forbidden_fragments = (
        "ordered_expected_case",
        "expected_case_result",
        "expected_metric_vector",
        "ordered_expected_resource_measurements",
        "expected_event_stream_sha256",
    )
    assert all(fragment not in encoded for fragment in forbidden_fragments)
    assert (
        len(contract["input_authority"]["ordered_required_semantic_root_records"]) == 6
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "CONTRACT_ID",
        "SEED_HASH",
        "SEMANTIC_ROOT_ID",
        "CASE_COUNT",
        "CASE_MEMBER_ORDER",
        "METRIC_RULE",
        "VERSION_LITERAL",
        "ALLOW_LOCAL_IMPORT",
        "F0_VALUE",
        "RESOURCE_SOURCE",
        "DUPLICATE_ERROR_CODE",
    ],
)
def test_preflight_contract_rejects_hostile_mutations(mutation: str) -> None:
    contract = copy.deepcopy(_contract())
    if mutation == "CONTRACT_ID":
        contract["contract_id"] = "0" * 64
    elif mutation == "SEED_HASH":
        contract["input_authority"]["accepted_catalog_raw_sha256"] = "0" * 64
    elif mutation == "SEMANTIC_ROOT_ID":
        contract["input_authority"]["ordered_required_semantic_root_records"][0][
            "expected_id"
        ] = "0" * 64
    elif mutation == "CASE_COUNT":
        contract["input_authority"]["expected_verifier_owned_case_count"] = 474
    elif mutation == "CASE_MEMBER_ORDER":
        members = contract["report_contract"]["case_result_record_schema"][
            "ordered_member_names"
        ]
        members[0], members[1] = members[1], members[0]
    elif mutation == "METRIC_RULE":
        contract["report_contract"]["ordered_metric_rule"] = (
            "ANY_PRESENT_METRIC_POSITIONS"
        )
    elif mutation == "VERSION_LITERAL":
        contract["report_contract"]["version_literals"][
            "preflight_semantic_payload_version"
        ] = "FUTURE_UNBOUND_VERSION"
    elif mutation == "ALLOW_LOCAL_IMPORT":
        contract["implementation_separation_policy"]["local_module_import_policy"] = (
            "ALLOW_SHARED_HELPERS"
        )
    elif mutation == "F0_VALUE":
        contract["resource_enforcement_contract"]["ordered_f0_limit_records"][9][
            "expected_value"
        ] += 1
    elif mutation == "RESOURCE_SOURCE":
        contract["resource_enforcement_contract"]["resource_observation_program"][
            "peak_rss_source"
        ] = "SELF_REPORTED_RSS"
    elif mutation == "DUPLICATE_ERROR_CODE":
        rows = contract["error_taxonomy"]["ordered_error_records"]
        rows[-1]["error_code"] = rows[-2]["error_code"]
    else:  # pragma: no cover - closed mutation enum.
        raise AssertionError(mutation)

    with pytest.raises(AssertionError):
        _validate(contract)
