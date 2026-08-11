#!/usr/bin/env python3
"""Independent A4-R475-T contract reconstruction and acceptance review.

The reviewer imports neither the contract generator nor any constructive role.
It reconstructs the effective case ledger directly from the pinned seed and
case-435 successor delta, then checks lifecycle and resource invariants before
emitting a deterministic contract-only acceptance report.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import sys
from typing import Any

SOURCE_MARKER = "INDEPENDENT_A4_R475_T_ALL_CASE_CONTRACT_REVIEWER_V1"
ERROR_PREFIX = "RAW_V8_STEP2_MAXIMUM_PROTOCOL_V2_ALL_CASE_CONTRACT_REVIEW_"
CONTRACT_RELATIVE_PATH = pathlib.Path(
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_all_case_campaign_contract_v49f.json"
)
CONTRACT_OCTETS = 382_710
CONTRACT_SHA256 = "3ca4ff4d6e581895b813043e7fdeed24c33cf2c828e362ac81de1725e95a84bb"
CONTRACT_ID = "9be94bf6b53b612d62ac26bc74133f25c1101a0962987a855e65cdcd06418583"
CONTRACT_DOMAIN = (
    "RiskYieldMMRawV8Step2MaximumProtocolV2AllCaseCampaignContractV1"
)
CASE_RECORD_DOMAIN = (
    "RiskYieldMMRawV8Step2MaximumProtocolV2AllCaseExecutionRecordV1"
)
CASE_LEDGER_DOMAIN = (
    "RiskYieldMMRawV8Step2MaximumProtocolV2AllCaseExecutionLedgerV1"
)
REPORT_VERSION = (
    "riskyieldmm.raw_v8_step2.maximum_protocol_v2."
    "all_case_campaign_contract_acceptance_report.v1"
)
REPORT_DOMAIN = (
    "RiskYieldMMRawV8Step2MaximumProtocolV2AllCaseCampaignContractAcceptanceReportV1"
)
A4_P6_E_REPORT_DOMAIN = (
    "RiskYieldMMRawV8Step2MaximumProtocolV2SixCaseEndToEndAcceptanceReportV1"
)

CASE_COUNT = 475
PILOT_CASES = [5, 24, 54, 69, 435, 475]

ARTIFACTS: dict[str, tuple[pathlib.Path, int, str]] = {
    "PREFLIGHT_CONTRACT": (
        pathlib.Path(
            "scripts/tests/raw_v8_step2_maximum_protocol_v2_preflight_contract_v49f.json"
        ),
        16_919,
        "007ed9a8d06b91f73708129b66a33eaf525e203d306426d05b8cd8bba9c7294b",
    ),
    "SEED": (
        pathlib.Path(
            "scripts/tests/raw_v8_step2_maximum_protocol_v2_seed_catalog_v49f.json"
        ),
        13_419_905,
        "a75a2f352e8513b7ff0043693a0c65ebbf4bc6f06859354789af69e1162b0e4f",
    ),
    "FINALIZATION_MANIFEST": (
        pathlib.Path(
            "scripts/tests/raw_v8_step2_maximum_protocol_v2_finalization_manifest_v49f.json"
        ),
        15_560,
        "0136fba014287605336193f782b4885f16e0163000d36429ceb0dfaf0cea52e0",
    ),
    "CONSTRUCTIVE_BOUNDARY": (
        pathlib.Path(
            "scripts/tests/raw_v8_step2_maximum_protocol_v2_constructive_boundary_v49f.json"
        ),
        27_334,
        "05468ec3411869fc5b4b5c60d2820e58f8ebf0af96dea978f06d92705fe3bb2b",
    ),
    "CASE435_SEED_DELTA": (
        pathlib.Path(
            "scripts/tests/raw_v8_step2_maximum_protocol_v2_case435_seed_delta_v49f.json"
        ),
        22_976,
        "5ce6b2156389ff0aecad7272a564308662a6ec3a77c4b94bfcae7ce32739c3da",
    ),
    "CASE435_MANIFEST_DELTA": (
        pathlib.Path(
            "scripts/tests/raw_v8_step2_maximum_protocol_v2_case435_manifest_delta_v49f.json"
        ),
        2_192,
        "daa55d18aa8adfcef9b8a6ea2c6fa734f7922888a902eb863c6307c0fc13bacf",
    ),
    "CASE435_BOUNDARY_DELTA": (
        pathlib.Path(
            "scripts/tests/raw_v8_step2_maximum_protocol_v2_case435_boundary_delta_v49f.json"
        ),
        4_806,
        "208d0cd50eb0bbfe206148dbf58df862f8adc857e382623e91e4e10d942c936c",
    ),
    "CASE435_TARGET_DELTA": (
        pathlib.Path(
            "scripts/tests/raw_v8_step2_maximum_protocol_v2_case435_six_case_target_delta_v49f.json"
        ),
        4_768,
        "394da62c1b5146990b2769feaefa1c06c75387ab7a38ec410ec7e327699b340b",
    ),
    "PACKED_CONTEXT_BOUNDARY": (
        pathlib.Path(
            "scripts/tests/raw_v8_step2_maximum_protocol_v2_case435_context_pack_boundary_delta_v49f.json"
        ),
        6_049,
        "985f0d67a545d036f1777a627f01b609d396a39c690ac81c1bacfc4f7563f56b",
    ),
    "A4_P6_E_REPORT": (
        pathlib.Path(
            "scripts/tests/raw_v8_step2_maximum_protocol_v2_six_case_end_to_end_acceptance_report_v49f.json"
        ),
        16_064,
        "8aab9f9be12edb028eae154f05c032b0d125865f37cad04e32862857a78b2d7e",
    ),
    "PILOT_PRODUCER": (
        pathlib.Path(
            "scripts/tests/produce_raw_v8_step2_maximum_protocol_v2_candidate_v49f.py"
        ),
        129_026,
        "46c67738905488a467cbb66a6de719f4cd4804e7ac68143cb301dc1e9c46d7da",
    ),
    "PILOT_VERIFIER": (
        pathlib.Path(
            "scripts/tests/verify_raw_v8_step2_maximum_protocol_v2_candidate_v49f.py"
        ),
        373_327,
        "b1bfb5778b1408c4b2dc45dd008f1089e2405b503b7eee9686820535d5631d25",
    ),
    "PILOT_RUNNER": (
        pathlib.Path(
            "scripts/tests/run_raw_v8_step2_maximum_protocol_v2_pilot_v49f.py"
        ),
        50_461,
        "5f1997b4e689a14cbae0a340fce2f320bb058eb9dd04449897ff3dfdf8de7ad7",
    ),
}


class ReviewFailure(ValueError):
    """Independent review rejection."""


def _require(condition: bool, code: str, detail: str = "") -> None:
    if not condition:
        raise ReviewFailure(f"{code}: {detail}" if detail else code)


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


def _semantic_id(domain: str, payload: Any) -> str:
    return _sha256(_canonical_bytes({"domain": domain, "payload": payload}))


def _duplicate_guard(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name, value in pairs:
        _require(name not in result, "JSON_DUPLICATE", name)
        result[name] = value
    return result


def _reject_number(value: str) -> Any:
    raise ReviewFailure(f"JSON_NUMBER_INVALID: {value}")


def _decode(raw: bytes, label: str, require_pretty: bool) -> dict[str, Any]:
    try:
        value = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_duplicate_guard,
            parse_float=_reject_number,
            parse_constant=_reject_number,
        )
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ReviewFailure(f"JSON_INVALID: {label}") from error
    _require(type(value) is dict, "JSON_ROOT_INVALID", label)
    if require_pretty:
        _require(raw == _pretty_bytes(value), "JSON_ENCODING_INVALID", label)
    return value


def _read_artifact(
    root: pathlib.Path, role: str
) -> tuple[bytes, dict[str, Any] | None, dict[str, Any]]:
    relative, octets, digest = ARTIFACTS[role]
    path = root / relative
    _require(path.is_file() and not path.is_symlink(), "ARTIFACT_TYPE_INVALID", role)
    status = path.stat()
    _require(status.st_nlink == 1, "ARTIFACT_LINK_INVALID", role)
    raw = path.read_bytes()
    _require((len(raw), _sha256(raw)) == (octets, digest), "ARTIFACT_DRIFT", role)
    value = None
    if relative.suffix == ".json":
        value = _decode(raw, role, role != "CONSTRUCTIVE_BOUNDARY")
    return raw, value, {
        "authority_role": role,
        "repository_relative_path": relative.as_posix(),
        "raw_octets": octets,
        "raw_sha256": digest,
    }


def _load_all(root: pathlib.Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    values: dict[str, Any] = {}
    descriptors: list[dict[str, Any]] = []
    for role in ARTIFACTS:
        raw, value, descriptor = _read_artifact(root, role)
        values[role] = raw if value is None else value
        descriptors.append(descriptor)
    return values, descriptors


def _case_family(position: int, profile_program_id: Any) -> str:
    if position == 475:
        return "LOCAL_MINIMALITY"
    if position == 69:
        return "SIGNED_ANALYTIC_EXACT_PROFILE"
    if position == 435:
        return "CORRECTED_APPLICATION_EXACT_PROFILE"
    if profile_program_id is not None:
        return "GENERIC_PROFILE_ATTAINMENT"
    return "INTRINSIC_TEMPLATE_ATTAINMENT"


def _reconstruct_cases(values: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    seed = values["SEED"]
    delta = values["CASE435_SEED_DELTA"]
    cases = seed["case_universe_catalog"]["ordered_case_bindings"]
    plans = seed["logical_plan_recipe_catalog"]["ordered_logical_count_plan_records"]
    bindings = seed["logical_plan_recipe_catalog"]["ordered_case_plan_bindings"]
    _require(len(cases) == len(plans) == len(bindings) == CASE_COUNT, "CASE_COUNT")
    result: list[dict[str, Any]] = []
    families: dict[str, int] = {}
    for index, triple in enumerate(zip(cases, plans, bindings, strict=True), 1):
        case, base_plan, base_binding = triple
        if index == 435:
            plan = delta["successor_case435_logical_count_plan"]
            binding = delta["successor_case435_case_plan_binding"]
            plan_source = "CASE435_SUCCESSOR_DELTA"
        else:
            plan = base_plan
            binding = base_binding
            plan_source = "BASE_SEED"
        _require(
            index
            == case["case_position"]
            == plan["case_position"]
            == binding["case_position"]
            == binding["logical_count_plan_position"],
            "CASE_ORDER",
            str(index),
        )
        _require(
            case["case_binding"] == plan["case_binding"]
            and plan["logical_count_plan_id"] == binding["logical_count_plan_id"],
            "CASE_BINDING",
            str(index),
        )
        family = _case_family(index, plan["profile_conditioning_program_id"])
        families[family] = families.get(family, 0) + 1
        source = case["case_binding"]
        payload = {
            "campaign_position": index,
            "case_position": index,
            "case_kind": case["case_kind"],
            "row_kind": source.get("row_kind"),
            "type_name": source.get("type_name"),
            "alternative_name": source.get("alternative_name"),
            "constraint_scope_profile_id": source.get("constraint_scope_profile_id"),
            "effective_logical_count_plan_id": plan["logical_count_plan_id"],
            "effective_plan_source": plan_source,
            "execution_family": family,
            "candidate_transport": (
                "CASE435_PACKED_CONTEXT_V1"
                if index == 435
                else "INHERITED_CLOSED_CANDIDATE_BUNDLE_V1"
            ),
        }
        result.append(
            {
                **payload,
                "case_execution_record_id": _semantic_id(CASE_RECORD_DOMAIN, payload),
            }
        )
    return result, families


def _payload_id(value: dict[str, Any], member: str, domain: str) -> None:
    _require(
        value.get(member)
        == _semantic_id(domain, {name: child for name, child in value.items() if name != member}),
        "SEMANTIC_ID_INVALID",
        member,
    )


def _validate_contract(
    root: pathlib.Path, contract: dict[str, Any]
) -> dict[str, Any]:
    values, descriptors = _load_all(root)
    expected_top = {
        "all_case_campaign_contract_version",
        "canonicalization_version",
        "measurement_schema_version",
        "protocol_version",
        "gate_contract",
        "authority_contract",
        "effective_authority_contract",
        "predecessor_regression_authority_contract",
        "case_universe_contract",
        "versioned_role_contract",
        "candidate_and_result_contract",
        "scheduler_and_checkpoint_contract",
        "checkpoint_schema_contract",
        "resource_contract",
        "publication_contract",
        "architecture_decision_contract",
        "implementation_sequence_contract",
        "acceptance_contract",
        "all_case_campaign_contract_id",
    }
    _require(set(contract) == expected_top, "CONTRACT_SCHEMA_INVALID")
    _payload_id(contract, "all_case_campaign_contract_id", CONTRACT_DOMAIN)
    _require(contract["all_case_campaign_contract_id"] == CONTRACT_ID, "CONTRACT_ID")
    _require(
        contract["authority_contract"]["ordered_authority_records"] == descriptors,
        "AUTHORITY_LEDGER_INVALID",
    )

    seed = values["SEED"]
    manifest = values["FINALIZATION_MANIFEST"]
    packed = values["PACKED_CONTEXT_BOUNDARY"]
    a4_report = values["A4_P6_E_REPORT"]
    _payload_id(
        a4_report,
        "six_case_end_to_end_acceptance_report_id",
        A4_P6_E_REPORT_DOMAIN,
    )
    _require(
        a4_report["release_decision"]
        == "RELEASED_FOR_A4_R475_VERSIONED_IMPLEMENTATION",
        "PREDECESSOR_RELEASE_INVALID",
    )
    effective = contract["effective_authority_contract"]
    _require(
        effective["predecessor_seed_catalog_id"] == seed["seed_catalog_id"]
        and effective["predecessor_finalization_manifest_id"]
        == manifest["finalization_manifest_id"]
        and effective["effective_successor_seed_catalog_id"]
        == packed["unchanged_effective_authorities"]["successor_seed_catalog_id"]
        and effective["effective_successor_manifest_id"]
        == packed["unchanged_effective_authorities"]["successor_manifest_id"]
        and effective["effective_f2_resource_limit_catalog_id"]
        == packed["unchanged_effective_authorities"][
            "f2_resource_limit_catalog_id"
        ],
        "EFFECTIVE_AUTHORITY_INVALID",
    )

    rows, families = _reconstruct_cases(values)
    universe = contract["case_universe_contract"]
    _require(universe["ordered_case_execution_records"] == rows, "CASE_LEDGER")
    _require(universe["execution_family_counts"] == families, "FAMILY_COUNTS")
    _require(
        universe["case_count"] == 475
        and universe["maximum_publication_case_count"] == 474
        and universe["local_minimality_case_count"] == 1,
        "CASE_UNIVERSE_SUMMARY",
    )
    _require(
        universe["ordered_case_execution_records_sha256"]
        == _sha256(_canonical_bytes(rows)),
        "CASE_LEDGER_SHA",
    )
    ledger_payload = {"case_count": 475, "ordered_case_execution_records": rows}
    _require(
        universe["case_execution_ledger_id"]
        == _semantic_id(CASE_LEDGER_DOMAIN, ledger_payload),
        "CASE_LEDGER_ID",
    )

    resources = contract["resource_contract"]
    f0 = seed["f0_seed_ceiling_catalog"]["ordered_platform_ceiling_records"]
    f2 = manifest["ordered_f2_limit_records"]
    _require(resources["ordered_f0_limit_records"] == f0, "F0_LEDGER")
    _require(resources["ordered_f2_limit_records"] == f2, "F2_LEDGER")
    _require(len(f0) == 12 and len(f2) == 18, "RESOURCE_COUNTS")
    _require(
        [row["metric_position"] for row in f2] == list(range(1, 19))
        and all(row["required_full_run"] <= row["f2_full_run"] for row in f2),
        "F2_LIMITS",
    )

    predecessor = contract["predecessor_regression_authority_contract"]
    _require(
        predecessor["surface"] == "EXACTLY_SIX_CASES"
        and predecessor["ordered_supported_case_positions"] == PILOT_CASES
        and predecessor["non_pilot_case_count"] == 469
        and predecessor["in_place_extension_policy"] == "FORBIDDEN"
        and predecessor["all_case_readiness_claimed"] is False,
        "PREDECESSOR_SCOPE",
    )
    role_rows = contract["versioned_role_contract"]["ordered_role_records"]
    _require(
        [row["role_position"] for row in role_rows] == [1, 2, 3]
        and len({row["repository_relative_path"] for row in role_rows}) == 3
        and all(row["implementation_state"] == "ABSENT_FAIL_FIRST" for row in role_rows),
        "ROLE_CONTRACT",
    )
    scheduler = contract["scheduler_and_checkpoint_contract"]
    publication = contract["publication_contract"]
    _require(
        scheduler["maximum_concurrent_case_attempts"] == 1
        and scheduler["completion_order_rule"] == "STRICT_CASE_POSITION_1_THROUGH_475"
        and scheduler["resume_selection_rule"]
        == "REUSE_ONLY_CONTIGUOUS_VALID_PREFIX_THEN_RUN_LOWEST_MISSING_CASE"
        and scheduler["corrupt_or_ambiguous_checkpoint_policy"]
        == "REJECT_WITHOUT_REPAIR_DELETE_OR_SKIP",
        "RESUME_CONTRACT",
    )
    _require(
        publication["partial_acceptance_policy"] == "FORBIDDEN"
        and publication["accepted_root_rule"]
        == "RENAME_COMPLETE_PRIVATE_WORK_ROOT_TO_ABSENT_ACCEPTED_ROOT_ONCE"
        and publication["check_mode_rule"]
        == "READ_ONLY_COMPLETE_RECONSTRUCTION_NO_REPAIR_NORMALIZATION_OR_DELETION",
        "PUBLICATION_CONTRACT",
    )
    architecture = contract["architecture_decision_contract"]
    alternatives = architecture["ordered_alternative_records"]
    _require(
        [row["alternative_position"] for row in alternatives] == list(range(1, 6))
        and [row["decision"] for row in alternatives].count("SELECTED") == 1
        and alternatives[-1]["architecture"] == "SEQUENTIAL_RESUMABLE_ROOT_LAST"
        and alternatives[-1]["decision"] == "SELECTED",
        "ARCHITECTURE_DECISION",
    )
    sequence = contract["implementation_sequence_contract"]["ordered_packet_records"]
    _require(
        [row["packet_position"] for row in sequence] == list(range(1, 8))
        and [row["packet"] for row in sequence]
        == [
            "A4-R475-V0",
            "A4-R475-V1",
            "A4-R475-V2",
            "A4-R475-V3",
            "A4-R475-P",
            "A4-R475-R",
            "A4-R475-E",
        ],
        "IMPLEMENTATION_SEQUENCE",
    )
    gate = contract["gate_contract"]
    _require(
        gate["correction_subgate"] == "A4-R475-T"
        and gate["next_bounded_packet_after_contract_acceptance"] == "A4-R475-V0"
        and gate["formal_stage1_state"] == "NO-GO"
        and gate["campaign_execution_state"]
        == "FORBIDDEN_UNTIL_ALL_ROLE_AND_RUNNER_GATES_ACCEPT",
        "GATE_CONTRACT",
    )
    return {
        "case_count": len(rows),
        "maximum_publication_case_count": sum(
            row["case_kind"] == "MAXIMUM_PUBLICATION_ROW" for row in rows
        ),
        "local_minimality_case_count": sum(
            row["case_kind"] == "LOCAL_SHUTDOWN_UNREPRESENTABLE_MINIMALITY"
            for row in rows
        ),
        "execution_family_counts": families,
        "case_execution_ledger_id": universe["case_execution_ledger_id"],
        "ordered_case_execution_records_sha256": universe[
            "ordered_case_execution_records_sha256"
        ],
        "f0_record_count": len(f0),
        "f2_record_count": len(f2),
        "required_full_run_f2_values": [row["required_full_run"] for row in f2],
    }


def _seal_report(report: dict[str, Any]) -> None:
    payload = {
        name: value
        for name, value in report.items()
        if name != "all_case_campaign_contract_acceptance_report_id"
    }
    report["all_case_campaign_contract_acceptance_report_id"] = _semantic_id(
        REPORT_DOMAIN, payload
    )


def build_report(root: pathlib.Path, contract_path: pathlib.Path) -> dict[str, Any]:
    _require(contract_path == root / CONTRACT_RELATIVE_PATH, "CONTRACT_PATH_INVALID")
    _require(contract_path.is_file() and not contract_path.is_symlink(), "CONTRACT_TYPE")
    raw = contract_path.read_bytes()
    _require(
        (len(raw), _sha256(raw)) == (CONTRACT_OCTETS, CONTRACT_SHA256),
        "CONTRACT_ARTIFACT_DRIFT",
    )
    contract = _decode(raw, "ALL_CASE_CONTRACT", True)
    evidence = _validate_contract(root, contract)
    report: dict[str, Any] = {
        "acceptance_report_version": REPORT_VERSION,
        "source_marker": SOURCE_MARKER,
        "correction_subgate": "A4-R475-T",
        "contract_authority": {
            "repository_relative_path": CONTRACT_RELATIVE_PATH.as_posix(),
            "raw_octets": len(raw),
            "raw_sha256": _sha256(raw),
            "all_case_campaign_contract_id": contract[
                "all_case_campaign_contract_id"
            ],
        },
        "independent_reconstruction_evidence": evidence,
        "lifecycle_decision": {
            "scheduler": "STRICT_SEQUENTIAL_SINGLE_WRITER_V1",
            "checkpoint": "DURABLE_CASE_COMMIT_REVALIDATED_BEFORE_REUSE",
            "resume": "CONTIGUOUS_VALID_PREFIX_ONLY",
            "publication": "COMPLETE_PRIVATE_WORK_ROOT_RENAMED_ONCE_ROOT_LAST",
            "partial_acceptance": "FORBIDDEN",
        },
        "fail_first_boundary": {
            "versioned_role_count": 3,
            "expected_missing_role_failures": 3,
            "accepted_pilot_case_count": 6,
            "non_pilot_case_count": 469,
            "accepted_six_case_binaries_remain_immutable": True,
            "all_case_execution_authorized_now": False,
        },
        "ordered_acceptance_criteria": [
            {
                "criterion_position": 1,
                "criterion_name": "PINNED_PREDECESSOR_AND_SUCCESSOR_AUTHORITY_CHAIN",
                "criterion_state": "PASS",
            },
            {
                "criterion_position": 2,
                "criterion_name": "ALL_475_EFFECTIVE_CASE_AND_PLAN_RECORDS_RECONSTRUCTED",
                "criterion_state": "PASS",
            },
            {
                "criterion_position": 3,
                "criterion_name": "FIVE_EXECUTION_FAMILIES_EXPLICIT_AND_COMPLETE",
                "criterion_state": "PASS",
            },
            {
                "criterion_position": 4,
                "criterion_name": "IMMUTABLE_F0_AND_F2_RESOURCE_LEDGERS",
                "criterion_state": "PASS",
            },
            {
                "criterion_position": 5,
                "criterion_name": "VERSIONED_ROLE_PATHS_AND_INDEPENDENCE_BOUNDARY",
                "criterion_state": "PASS",
            },
            {
                "criterion_position": 6,
                "criterion_name": "FAIL_CLOSED_CHECKPOINT_RESUME_AND_ROLLBACK",
                "criterion_state": "PASS",
            },
            {
                "criterion_position": 7,
                "criterion_name": "ROOT_LAST_ATOMIC_CAMPAIGN_PUBLICATION",
                "criterion_state": "PASS",
            },
            {
                "criterion_position": 8,
                "criterion_name": "EXPLICIT_FAIL_FIRST_AND_STAGE1_NONCLAIMS",
                "criterion_state": "PASS",
            },
        ],
        "review_decision": "ACCEPTED_CONTRACT_ONLY",
        "next_bounded_packet": "A4-R475-V0",
        "formal_stage1_state": "NO-GO",
    }
    _seal_report(report)
    return report


def _atomic_write(path: pathlib.Path, raw: bytes) -> None:
    _require(path.is_absolute(), "OUTPUT_PATH_INVALID")
    _require(path.parent.is_dir() and not path.parent.is_symlink(), "OUTPUT_PARENT")
    _require(not path.exists() and not path.is_symlink(), "OUTPUT_EXISTS")
    temporary = path.parent / f".{path.name}.tmp"
    descriptor: int | None = None
    try:
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
            0o600,
        )
        offset = 0
        while offset < len(raw):
            written = os.write(descriptor, raw[offset:])
            _require(written > 0, "OUTPUT_STALLED")
            offset += written
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = None
        os.link(temporary, path, follow_symlinks=False)
        os.unlink(temporary)
        parent = os.open(path.parent, os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY)
        try:
            os.fsync(parent)
        finally:
            os.close(parent)
    finally:
        if descriptor is not None:
            os.close(descriptor)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _arguments(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--repository-root", required=True)
    parser.add_argument("--contract", required=True)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--write-report")
    modes.add_argument("--check-report")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        arguments = _arguments(sys.argv[1:] if argv is None else argv)
        root = pathlib.Path(arguments.repository_root)
        contract = pathlib.Path(arguments.contract)
        _require(
            root.is_absolute() and pathlib.Path(os.path.realpath(root)) == root,
            "REPOSITORY_ROOT_INVALID",
        )
        report = build_report(root, contract)
        raw = _pretty_bytes(report)
        selected = (
            arguments.write_report
            if arguments.write_report is not None
            else arguments.check_report
        )
        path = pathlib.Path(selected)
        _require(path.is_absolute(), "OUTPUT_PATH_INVALID")
        if arguments.write_report is not None:
            _atomic_write(path, raw)
        else:
            _require(path.is_file() and not path.is_symlink(), "REPORT_TYPE_INVALID")
            _require(path.read_bytes() == raw, "REPORT_STALE")
    except (ReviewFailure, OSError, ValueError, TypeError, KeyError) as error:
        sys.stderr.write(f"{ERROR_PREFIX}REJECTED: {type(error).__name__}: {error}\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
