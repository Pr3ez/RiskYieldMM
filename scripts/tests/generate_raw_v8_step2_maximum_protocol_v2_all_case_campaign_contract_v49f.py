#!/usr/bin/env python3
"""Build the A4-R475-T versioned all-475 campaign contract.

This generator is intentionally data-only.  It does not import or execute the
accepted producer, verifier, runner, seed generator, or preflight programs.
It resolves the immutable predecessor and successor authorities, derives the
effective ordered case/plan ledger, and freezes orchestration semantics for a
future versioned implementation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import sys
from typing import Any

SOURCE_MARKER = "A4_R475_T_ALL_CASE_CAMPAIGN_CONTRACT_GENERATOR_V1"
ERROR_PREFIX = "RAW_V8_STEP2_MAXIMUM_PROTOCOL_V2_ALL_CASE_CONTRACT_"
CONTRACT_VERSION = (
    "riskyieldmm.raw_v8_step2.maximum_protocol_v2.all_case_campaign_contract.v1"
)
CONTRACT_DOMAIN = (
    "RiskYieldMMRawV8Step2MaximumProtocolV2AllCaseCampaignContractV1"
)
CASE_RECORD_DOMAIN = (
    "RiskYieldMMRawV8Step2MaximumProtocolV2AllCaseExecutionRecordV1"
)
CASE_LEDGER_DOMAIN = (
    "RiskYieldMMRawV8Step2MaximumProtocolV2AllCaseExecutionLedgerV1"
)

CASE_COUNT = 475
MAXIMUM_CASE_COUNT = 474
LOCAL_CASE_POSITION = 475
CASE69_POSITION = 69
CASE435_POSITION = 435
PILOT_CASES = [5, 24, 54, 69, 435, 475]

ROLE_PATHS = {
    "VERSIONED_ALL_CASE_PRODUCER": (
        "scripts/tests/produce_raw_v8_step2_maximum_protocol_v2_"
        "all_case_candidate_v49f.py"
    ),
    "VERSIONED_ALL_CASE_VERIFIER": (
        "scripts/tests/verify_raw_v8_step2_maximum_protocol_v2_"
        "all_case_candidate_v49f.py"
    ),
    "VERSIONED_ALL_CASE_RUNNER": (
        "scripts/tests/run_raw_v8_step2_maximum_protocol_v2_"
        "all_case_campaign_v49f.py"
    ),
}

AUTHORITIES: dict[str, tuple[str, int, str]] = {
    "PREFLIGHT_CONTRACT": (
        "scripts/tests/raw_v8_step2_maximum_protocol_v2_preflight_contract_v49f.json",
        16_919,
        "007ed9a8d06b91f73708129b66a33eaf525e203d306426d05b8cd8bba9c7294b",
    ),
    "SEED": (
        "scripts/tests/raw_v8_step2_maximum_protocol_v2_seed_catalog_v49f.json",
        13_419_905,
        "a75a2f352e8513b7ff0043693a0c65ebbf4bc6f06859354789af69e1162b0e4f",
    ),
    "FINALIZATION_MANIFEST": (
        "scripts/tests/raw_v8_step2_maximum_protocol_v2_finalization_manifest_v49f.json",
        15_560,
        "0136fba014287605336193f782b4885f16e0163000d36429ceb0dfaf0cea52e0",
    ),
    "CONSTRUCTIVE_BOUNDARY": (
        "scripts/tests/raw_v8_step2_maximum_protocol_v2_constructive_boundary_v49f.json",
        27_334,
        "05468ec3411869fc5b4b5c60d2820e58f8ebf0af96dea978f06d92705fe3bb2b",
    ),
    "CASE435_SEED_DELTA": (
        "scripts/tests/raw_v8_step2_maximum_protocol_v2_case435_seed_delta_v49f.json",
        22_976,
        "5ce6b2156389ff0aecad7272a564308662a6ec3a77c4b94bfcae7ce32739c3da",
    ),
    "CASE435_MANIFEST_DELTA": (
        "scripts/tests/raw_v8_step2_maximum_protocol_v2_case435_manifest_delta_v49f.json",
        2_192,
        "daa55d18aa8adfcef9b8a6ea2c6fa734f7922888a902eb863c6307c0fc13bacf",
    ),
    "CASE435_BOUNDARY_DELTA": (
        "scripts/tests/raw_v8_step2_maximum_protocol_v2_case435_boundary_delta_v49f.json",
        4_806,
        "208d0cd50eb0bbfe206148dbf58df862f8adc857e382623e91e4e10d942c936c",
    ),
    "CASE435_TARGET_DELTA": (
        "scripts/tests/raw_v8_step2_maximum_protocol_v2_case435_six_case_target_delta_v49f.json",
        4_768,
        "394da62c1b5146990b2769feaefa1c06c75387ab7a38ec410ec7e327699b340b",
    ),
    "PACKED_CONTEXT_BOUNDARY": (
        "scripts/tests/raw_v8_step2_maximum_protocol_v2_case435_context_pack_boundary_delta_v49f.json",
        6_049,
        "985f0d67a545d036f1777a627f01b609d396a39c690ac81c1bacfc4f7563f56b",
    ),
    "A4_P6_E_REPORT": (
        "scripts/tests/raw_v8_step2_maximum_protocol_v2_six_case_end_to_end_acceptance_report_v49f.json",
        16_064,
        "8aab9f9be12edb028eae154f05c032b0d125865f37cad04e32862857a78b2d7e",
    ),
    "PILOT_PRODUCER": (
        "scripts/tests/produce_raw_v8_step2_maximum_protocol_v2_candidate_v49f.py",
        129_026,
        "46c67738905488a467cbb66a6de719f4cd4804e7ac68143cb301dc1e9c46d7da",
    ),
    "PILOT_VERIFIER": (
        "scripts/tests/verify_raw_v8_step2_maximum_protocol_v2_candidate_v49f.py",
        373_327,
        "b1bfb5778b1408c4b2dc45dd008f1089e2405b503b7eee9686820535d5631d25",
    ),
    "PILOT_RUNNER": (
        "scripts/tests/run_raw_v8_step2_maximum_protocol_v2_pilot_v49f.py",
        50_461,
        "5f1997b4e689a14cbae0a340fce2f320bb058eb9dd04449897ff3dfdf8de7ad7",
    ),
}


class ContractFailure(ValueError):
    """Fail-closed contract construction rejection."""


def _require(condition: bool, code: str, detail: str = "") -> None:
    if not condition:
        raise ContractFailure(f"{code}: {detail}" if detail else code)


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
    value: dict[str, Any] = {}
    for name, child in pairs:
        _require(name not in value, "DUPLICATE_JSON_KEY", name)
        value[name] = child
    return value


def _reject_number(value: str) -> Any:
    raise ContractFailure(f"JSON_NUMBER_INVALID: {value}")


def _strict_json(
    raw: bytes, label: str, *, require_sorted_pretty_encoding: bool = True
) -> dict[str, Any]:
    try:
        value = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_duplicate_guard,
            parse_float=_reject_number,
            parse_constant=_reject_number,
        )
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ContractFailure(f"JSON_INVALID: {label}") from error
    _require(type(value) is dict, "JSON_ROOT_INVALID", label)
    if require_sorted_pretty_encoding:
        _require(raw == _pretty_bytes(value), "JSON_ENCODING_INVALID", label)
    return value


def _read_regular(root: pathlib.Path, role: str) -> tuple[bytes, dict[str, Any]]:
    relative, expected_octets, expected_sha256 = AUTHORITIES[role]
    path = root / relative
    _require(path.is_file() and not path.is_symlink(), "AUTHORITY_TYPE_INVALID", role)
    status = path.stat()
    _require(status.st_nlink == 1, "AUTHORITY_LINK_INVALID", role)
    raw = path.read_bytes()
    _require(len(raw) == expected_octets, "AUTHORITY_SIZE_DRIFT", role)
    _require(_sha256(raw) == expected_sha256, "AUTHORITY_HASH_DRIFT", role)
    descriptor = {
        "authority_role": role,
        "repository_relative_path": relative,
        "raw_octets": len(raw),
        "raw_sha256": _sha256(raw),
    }
    return raw, descriptor


def _load_inputs(root: pathlib.Path) -> tuple[dict[str, Any], dict[str, Any]]:
    values: dict[str, Any] = {}
    descriptors: list[dict[str, Any]] = []
    for role in AUTHORITIES:
        raw, descriptor = _read_regular(root, role)
        descriptors.append(descriptor)
        if descriptor["repository_relative_path"].endswith(".json"):
            values[role] = _strict_json(
                raw,
                role,
                # The accepted A4-B0 boundary predates sorted-key physical
                # JSON. Its exact bytes are pinned above; do not normalize it.
                require_sorted_pretty_encoding=(role != "CONSTRUCTIVE_BOUNDARY"),
            )
        else:
            values[role] = raw
    return values, {
        "authority_loading_rule": (
            "OPEN_NOFOLLOW_REGULAR_SINGLE_LINK_EXACT_SIZE_HASH_AND_RECHECK_BEFORE_EVERY_CASE_COMMIT_AND_FINAL_PUBLICATION"
        ),
        "ordered_authority_records": descriptors,
        "unknown_missing_extra_or_drifted_authority_policy": "REJECT",
    }


def _validate_authority_chain(values: dict[str, Any]) -> None:
    preflight = values["PREFLIGHT_CONTRACT"]
    seed = values["SEED"]
    manifest = values["FINALIZATION_MANIFEST"]
    boundary = values["CONSTRUCTIVE_BOUNDARY"]
    seed_delta = values["CASE435_SEED_DELTA"]
    manifest_delta = values["CASE435_MANIFEST_DELTA"]
    boundary_delta = values["CASE435_BOUNDARY_DELTA"]
    target = values["CASE435_TARGET_DELTA"]
    packed = values["PACKED_CONTEXT_BOUNDARY"]
    acceptance = values["A4_P6_E_REPORT"]

    _require(
        preflight["contract_id"]
        == "6609ad7b9abf21432136e49af178e20c17cb7bc27d3b444a4b6f01a17073fc76",
        "PREFLIGHT_ID_INVALID",
    )
    _require(
        seed["seed_catalog_id"]
        == "ac22151fa74702ac1488924f01161eaa38574545e6272a290db6b0bbd288ae5f",
        "SEED_ID_INVALID",
    )
    _require(
        manifest["finalization_manifest_id"]
        == "edde204e98ed1caeeb8ae270487d85e39a2168e0a3692ce1d8748d2d8e7fd858",
        "MANIFEST_ID_INVALID",
    )
    _require(
        boundary["constructive_boundary_id"]
        == "bdc7363ae28dfe9a1c1dc132808cb1bd4a06c409201cd49b31e394893142a7ed",
        "BOUNDARY_ID_INVALID",
    )
    _require(
        seed_delta["successor_seed_catalog_id"]
        == "7fad47e881624d0f39809e72ce2d3d3fd81fb8c85f854fe8332faf543cd1120b",
        "SUCCESSOR_SEED_ID_INVALID",
    )
    _require(
        manifest_delta["successor_manifest_id"]
        == "6aed1139c158f8685bcb226697a2efe57af3c42f57831173bd7b3ea169025d9c",
        "SUCCESSOR_MANIFEST_ID_INVALID",
    )
    _require(
        boundary_delta["successor_constructive_boundary_id"]
        == "7d4c06f56cd3cacd97cc4ff655e31f380fe9231c6c7c1374caee499186e1f73d",
        "SUCCESSOR_BOUNDARY_ID_INVALID",
    )
    _require(
        target["successor_six_case_target_id"]
        == "a000285d1bedd88306786ea33e1be9cc7d2a8459fe75b20c045f7174d52cc072",
        "TARGET_ID_INVALID",
    )
    _require(
        packed["case435_context_pack_boundary_delta_id"]
        == "c8448f57dcdc3e4f1f3239043ed4977013efbd99c750cb2e2e857025f5ac0acd",
        "PACKED_BOUNDARY_ID_INVALID",
    )
    _require(
        acceptance["six_case_end_to_end_acceptance_report_id"]
        == "c94c784f29a57fd8fc345cd49b90b7225e2a5697ff2077c8dd0b4b2115809d11"
        and acceptance["release_decision"]
        == "RELEASED_FOR_A4_R475_VERSIONED_IMPLEMENTATION",
        "A4_P6_E_RELEASE_INVALID",
    )
    effective = packed["unchanged_effective_authorities"]
    _require(
        effective["successor_seed_catalog_id"] == seed_delta["successor_seed_catalog_id"]
        and effective["successor_manifest_id"]
        == manifest_delta["successor_manifest_id"]
        and effective["case435_logical_count_plan_id"]
        == seed_delta["successor_case435_logical_count_plan"]["logical_count_plan_id"]
        and effective["f2_resource_limit_catalog_id"]
        == boundary_delta["successor_f2_resource_limit_catalog"][
            "f2_resource_limit_catalog_id"
        ],
        "SUCCESSOR_CHAIN_INVALID",
    )
    _require(
        manifest_delta["f2_limit_authority"]["ordered_f2_limit_records_sha256"]
        == _sha256(_canonical_bytes(manifest["ordered_f2_limit_records"])),
        "F2_CHAIN_INVALID",
    )


def _execution_family(case_position: int, plan: dict[str, Any]) -> str:
    if case_position == LOCAL_CASE_POSITION:
        return "LOCAL_MINIMALITY"
    if case_position == CASE69_POSITION:
        return "SIGNED_ANALYTIC_EXACT_PROFILE"
    if case_position == CASE435_POSITION:
        return "CORRECTED_APPLICATION_EXACT_PROFILE"
    if plan["profile_conditioning_program_id"] is not None:
        return "GENERIC_PROFILE_ATTAINMENT"
    return "INTRINSIC_TEMPLATE_ATTAINMENT"


def _case_ledger(values: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    seed = values["SEED"]
    seed_delta = values["CASE435_SEED_DELTA"]
    cases = seed["case_universe_catalog"]["ordered_case_bindings"]
    plans = seed["logical_plan_recipe_catalog"]["ordered_logical_count_plan_records"]
    bindings = seed["logical_plan_recipe_catalog"]["ordered_case_plan_bindings"]
    _require(
        len(cases) == len(plans) == len(bindings) == CASE_COUNT,
        "CASE_UNIVERSE_COUNT_INVALID",
    )
    records: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    for position in range(1, CASE_COUNT + 1):
        case = cases[position - 1]
        plan = (
            seed_delta["successor_case435_logical_count_plan"]
            if position == CASE435_POSITION
            else plans[position - 1]
        )
        binding = (
            seed_delta["successor_case435_case_plan_binding"]
            if position == CASE435_POSITION
            else bindings[position - 1]
        )
        _require(
            case["case_position"]
            == plan["case_position"]
            == binding["case_position"]
            == binding["logical_count_plan_position"]
            == position,
            "CASE_ORDER_INVALID",
            str(position),
        )
        _require(
            case["case_binding"] == plan["case_binding"]
            and binding["logical_count_plan_id"] == plan["logical_count_plan_id"],
            "CASE_PLAN_BINDING_INVALID",
            str(position),
        )
        family = _execution_family(position, plan)
        counts[family] = counts.get(family, 0) + 1
        case_binding = case["case_binding"]
        without_id = {
            "campaign_position": position,
            "case_position": position,
            "case_kind": case["case_kind"],
            "row_kind": case_binding.get("row_kind"),
            "type_name": case_binding.get("type_name"),
            "alternative_name": case_binding.get("alternative_name"),
            "constraint_scope_profile_id": case_binding.get(
                "constraint_scope_profile_id"
            ),
            "effective_logical_count_plan_id": plan["logical_count_plan_id"],
            "effective_plan_source": (
                "CASE435_SUCCESSOR_DELTA" if position == CASE435_POSITION else "BASE_SEED"
            ),
            "execution_family": family,
            "candidate_transport": (
                "CASE435_PACKED_CONTEXT_V1"
                if position == CASE435_POSITION
                else "INHERITED_CLOSED_CANDIDATE_BUNDLE_V1"
            ),
        }
        records.append(
            {
                **without_id,
                "case_execution_record_id": _semantic_id(
                    CASE_RECORD_DOMAIN, without_id
                ),
            }
        )
    _require(
        counts
        == {
            "CORRECTED_APPLICATION_EXACT_PROFILE": 1,
            "GENERIC_PROFILE_ATTAINMENT": 406,
            "INTRINSIC_TEMPLATE_ATTAINMENT": 66,
            "LOCAL_MINIMALITY": 1,
            "SIGNED_ANALYTIC_EXACT_PROFILE": 1,
        },
        "EXECUTION_FAMILY_COUNTS_INVALID",
    )
    return records, counts


def _role_contract() -> dict[str, Any]:
    rows = [
        {
            "role_position": 1,
            "role_name": "VERSIONED_ALL_CASE_VERIFIER",
            "repository_relative_path": ROLE_PATHS["VERSIONED_ALL_CASE_VERIFIER"],
            "source_marker": "INDEPENDENT_V2_ALL_CASE_CONSTRUCTIVE_VERIFIER_V1",
            "semantic_authority": True,
            "may_execute_other_role": False,
            "implementation_state": "ABSENT_FAIL_FIRST",
        },
        {
            "role_position": 2,
            "role_name": "VERSIONED_ALL_CASE_PRODUCER",
            "repository_relative_path": ROLE_PATHS["VERSIONED_ALL_CASE_PRODUCER"],
            "source_marker": "SEPARATE_V2_ALL_CASE_CONSTRUCTIVE_PRODUCER_V1",
            "semantic_authority": False,
            "may_execute_other_role": False,
            "implementation_state": "ABSENT_FAIL_FIRST",
        },
        {
            "role_position": 3,
            "role_name": "VERSIONED_ALL_CASE_RUNNER",
            "repository_relative_path": ROLE_PATHS["VERSIONED_ALL_CASE_RUNNER"],
            "source_marker": "PARENT_OWNED_V2_ALL_CASE_CAMPAIGN_RUNNER_V1",
            "semantic_authority": False,
            "may_execute_other_role": True,
            "implementation_state": "ABSENT_FAIL_FIRST",
        },
    ]
    return {
        "ordered_role_records": rows,
        "implementation_identity_rule": (
            "ROLE_ACCEPTANCE_FREEZES_PATH_DEVICE_INODE_RAW_OCTETS_SHA256_AND_SOURCE_MARKER_IN_A_NEW_VERSIONED_AUTHORITY_WITHOUT_RESEALING_THIS_CONTRACT"
        ),
        "single_case_cli_rule": "INHERIT_A4_B0_FIXED_ORDER_PYTHON_I_S_B_CONTRACT",
        "producer_verifier_shared_executable_code_policy": "NONE",
        "runner_launch_policy": "FORK_SETRLIMIT_EXECVE_NO_SHELL_FIXED_ARGV_MINIMAL_ENVIRONMENT",
        "runner_single_writer_lock": "NONBLOCKING_KERNEL_FLOCK_HELD_FOR_COMPLETE_MUTATING_INVOCATION",
        "unknown_extra_or_in_place_role_policy": "REJECT",
    }


def build_contract(root: pathlib.Path) -> dict[str, Any]:
    values, authority_contract = _load_inputs(root)
    _validate_authority_chain(values)
    seed = values["SEED"]
    manifest = values["FINALIZATION_MANIFEST"]
    boundary = values["CONSTRUCTIVE_BOUNDARY"]
    packed = values["PACKED_CONTEXT_BOUNDARY"]
    acceptance = values["A4_P6_E_REPORT"]
    case_records, family_counts = _case_ledger(values)
    f0 = seed["f0_seed_ceiling_catalog"]["ordered_platform_ceiling_records"]
    f2 = manifest["ordered_f2_limit_records"]
    _require(len(f0) == 12 and len(f2) == 18, "RESOURCE_LEDGER_INVALID")
    _require(
        [row["metric_position"] for row in f2] == list(range(1, 19)),
        "F2_ORDER_INVALID",
    )
    case_ledger_payload = {
        "case_count": CASE_COUNT,
        "ordered_case_execution_records": case_records,
    }
    contract: dict[str, Any] = {
        "all_case_campaign_contract_version": CONTRACT_VERSION,
        "canonicalization_version": seed["canonicalization_version"],
        "measurement_schema_version": seed["measurement_schema_version"],
        "protocol_version": boundary["protocol_version"],
        "gate_contract": {
            "correction_subgate": "A4-R475-T",
            "contract_decision": "ACCEPTABLE_ONLY_AFTER_INDEPENDENT_RECONSTRUCTION",
            "formal_stage1_state": "NO-GO",
            "all_case_implementation_state": "FAIL_FIRST_NOT_IMPLEMENTED",
            "campaign_execution_state": "FORBIDDEN_UNTIL_ALL_ROLE_AND_RUNNER_GATES_ACCEPT",
            "next_bounded_packet_after_contract_acceptance": "A4-R475-V0",
            "accepted_scope": "CONTRACT_AND_FAIL_FIRST_BOUNDARY_ONLY",
            "profitability_safety_or_live_readiness_claimed": False,
        },
        "authority_contract": authority_contract,
        "effective_authority_contract": {
            "predecessor_seed_catalog_id": seed["seed_catalog_id"],
            "effective_successor_seed_catalog_id": packed[
                "unchanged_effective_authorities"
            ]["successor_seed_catalog_id"],
            "predecessor_finalization_manifest_id": manifest[
                "finalization_manifest_id"
            ],
            "effective_successor_manifest_id": packed[
                "unchanged_effective_authorities"
            ]["successor_manifest_id"],
            "effective_f2_resource_limit_catalog_id": packed[
                "unchanged_effective_authorities"
            ]["f2_resource_limit_catalog_id"],
            "case435_effective_plan_rule": "ONLY_CASE_435_RESOLVES_THROUGH_ACCEPTED_SUCCESSOR_SEED_DELTA",
            "all_other_case_plan_rule": "RESOLVE_EXACT_BASE_SEED_CASE_AND_PLAN_AT_SAME_ONE_BASED_POSITION",
            "candidate_authority_mode": "SUCCESSOR_CASE435_PACKED_CONTEXT_BOUNDARY_V1",
            "authority_read_barrier": "ALL_AUTHORITIES_AND_ALL_THREE_VERSIONED_ROLE_SOURCES_BEFORE_ANY_WORK_ROOT_OR_CANDIDATE_PATH",
            "drift_policy": "RECHECK_BEFORE_AND_AFTER_EACH_CHILD_CASE_COMMIT_AND_FINAL_RENAME_OR_REJECT",
        },
        "predecessor_regression_authority_contract": {
            "a4_p6_e_report_id": acceptance[
                "six_case_end_to_end_acceptance_report_id"
            ],
            "surface": "EXACTLY_SIX_CASES",
            "ordered_supported_case_positions": PILOT_CASES,
            "non_pilot_case_count": CASE_COUNT - len(PILOT_CASES),
            "in_place_extension_policy": "FORBIDDEN",
            "regression_replay_rule": "ALL_SIX_ACCEPTED_CASES_MUST_REMAIN_BYTE_IDENTICAL_UNDER_NEW_VERSIONED_ROLES",
            "all_case_readiness_claimed": False,
            "pilot_f2_implies_full_campaign_fit": False,
        },
        "case_universe_contract": {
            "case_count": CASE_COUNT,
            "maximum_publication_case_count": MAXIMUM_CASE_COUNT,
            "local_minimality_case_count": 1,
            "ordering_rule": "EXACTLY_CASE_POSITIONS_1_THROUGH_475_ONCE_EACH",
            "completion_rule": "EVERY_CASE_COMMIT_PRESENT_VALID_AND_STRICTLY_ORDERED",
            "execution_family_counts": family_counts,
            "ordered_case_execution_records_sha256": _sha256(
                _canonical_bytes(case_records)
            ),
            "case_execution_ledger_id": _semantic_id(
                CASE_LEDGER_DOMAIN, case_ledger_payload
            ),
            "ordered_case_execution_records": case_records,
        },
        "versioned_role_contract": _role_contract(),
        "candidate_and_result_contract": {
            "candidate_schema_source": "A4_B0_CANDIDATE_BUNDLE_CONTRACT_PLUS_ACCEPTED_CASE435_PACKED_TRANSPORT_DELTA",
            "verified_result_schema_source": "A4_B0_VERIFIER_OUTPUT_CONTRACT",
            "producer_claim_policy": "CANDIDATE_IS_UNTRUSTED_DATA_NEVER_PROOF",
            "verifier_recomputation_rule": "RECOMPUTE_TYPED_LEGALITY_BOUND_ATTAINMENT_IDENTITIES_CONTEXT_CLOSURE_AND_ALL_18_METRICS",
            "generic_profile_rule": "STRUCTURAL_P2_SUPERSET_IS_NOT_EXACT_UNLESS_AN_INDEPENDENT_P1_LEGAL_WITNESS_ATTAINS_P2_UPPER",
            "unattained_or_unresolved_case_policy": "COMPLETE_CAMPAIGN_NO_GO_WITHOUT_LIMIT_OR_AUTHORITY_REPAIR",
            "per_case_output_rule": "ONE_CLOSED_CANDIDATE_ROOT_ONE_SEPARATE_CLOSED_VERIFIED_ROOT_ONE_PARENT_CASE_COMMIT",
            "candidate_immutability_rule": "PARENT_RECOMPUTES_COMPLETE_CANDIDATE_CLOSURE_BEFORE_AND_AFTER_VERIFIER",
        },
        "scheduler_and_checkpoint_contract": {
            "scheduler_version": "STRICT_SEQUENTIAL_SINGLE_WRITER_V1",
            "maximum_concurrent_case_attempts": 1,
            "completion_order_rule": "STRICT_CASE_POSITION_1_THROUGH_475",
            "selection_rule": "LOWEST_MISSING_CASE_POSITION_ONLY",
            "work_root": "test_output/.raw_v8_step2_maximum_protocol_v2_all_case_campaign_v49f.work",
            "accepted_root": "test_output/raw_v8_step2_maximum_protocol_v2_all_case_campaign_v49f",
            "anchor_write_rule": "IMMUTABLE_CAMPAIGN_ANCHOR_WRITTEN_AND_FSYNCED_BEFORE_FIRST_CASE_ATTEMPT",
            "attempt_root_rule": "RECOGNIZED_PRIVATE_ATTEMPT_ROOT_NEVER_COUNTS_AS_CHECKPOINT",
            "stale_attempt_rollback_rule": "DELETE_ONLY_RECOGNIZED_UNCOMMITTED_ATTEMPT_ROOT_AFTER_EXCLUSIVE_LOCK_AND_FSYNC_PARENT",
            "case_checkpoint_rule": "WRITE_CASE_COMMIT_LAST_FSYNC_TREE_THEN_RENAME_ATTEMPT_TO_ABSENT_FOUR_DIGIT_CASE_ROOT",
            "checkpoint_reuse_rule": "REVALIDATE_COMPLETE_CASE_CLOSURE_AUTHORITIES_ROLE_IDENTITIES_AND_CASE_COMMIT_BEFORE_REUSE",
            "corrupt_or_ambiguous_checkpoint_policy": "REJECT_WITHOUT_REPAIR_DELETE_OR_SKIP",
            "failed_case_policy": "REMOVE_CURRENT_UNCOMMITTED_ATTEMPT_PRESERVE_PRIOR_VERIFIED_COMMITS_AND_RETURN_NO_GO",
            "resume_selection_rule": "REUSE_ONLY_CONTIGUOUS_VALID_PREFIX_THEN_RUN_LOWEST_MISSING_CASE",
            "nondeterministic_scheduler_state_in_identity_policy": "FORBIDDEN",
        },
        "checkpoint_schema_contract": {
            "campaign_anchor_ordered_member_names": [
                "anchor_version",
                "campaign_contract_id",
                "canonicalization_version",
                "protocol_version",
                "effective_seed_catalog_id",
                "effective_manifest_id",
                "case_execution_ledger_id",
                "producer_authority",
                "verifier_authority",
                "runner_authority",
                "campaign_anchor_id",
            ],
            "case_commit_ordered_member_names": [
                "case_commit_version",
                "campaign_anchor_id",
                "campaign_position",
                "case_position",
                "case_execution_record_id",
                "constructive_candidate_id",
                "candidate_root_raw_octets",
                "candidate_root_sha256",
                "verification_receipt_id",
                "verified_result_artifact_id",
                "verified_result_root_raw_octets",
                "verified_result_root_sha256",
                "ordered_resource_measurements",
                "case_commit_id",
            ],
            "case_directory_name_rule": "FOUR_DIGIT_ZERO_PADDED_CASE_POSITION",
            "identity_rule": "DOMAIN_SEPARATED_SHA256_OVER_EVERY_PRECEDING_ORDERED_MEMBER",
            "unknown_missing_duplicate_extra_or_resealed_mismatch_policy": "REJECT",
        },
        "resource_contract": {
            "ordered_f0_limit_records": f0,
            "ordered_f2_limit_records": f2,
            "per_child_f0_rule": "PARENT_ENFORCES_EVERY_F0_PROCESS_AND_ARTIFACT_LIMIT_INDEPENDENTLY_FOR_EACH_PRODUCER_AND_VERIFIER",
            "whole_work_root_storage_rule": "ALLOCATED_ST_BLOCKS_TIMES_512_NEVER_EXCEEDS_PUBLICATION_STAGING_STORAGE_OCTETS",
            "per_case_f2_rule": "ALL_18_MEASURED_VALUES_MUST_NOT_EXCEED_F2_PER_CASE",
            "full_run_f2_rule": "AGGREGATE_ALL_475_CASE_VECTORS_BY_FROZEN_SUM_OR_MAXIMUM_REQUIRE_EXACT_REQUIRED_FULL_RUN_AND_NOT_ABOVE_F2_FULL_RUN",
            "checked_arithmetic_rule": "UINT128_FOR_ACCUMULATION_SAFE_INTEGER_FOR_JSON",
            "telemetry_identity_policy": "WALL_CPU_RSS_AND_STORAGE_TELEMETRY_MAY_REJECT_BUT_NEVER_ENTERS_SEMANTIC_IDENTITIES",
            "limit_change_or_observation_based_repair_policy": "FORBIDDEN",
        },
        "publication_contract": {
            "accepted_root_rule": "RENAME_COMPLETE_PRIVATE_WORK_ROOT_TO_ABSENT_ACCEPTED_ROOT_ONCE",
            "campaign_manifest_write_order": "AFTER_475_CASE_COMMITS_BEFORE_FINAL_ROOT_RENAME",
            "campaign_manifest_ordered_member_names": [
                "campaign_version",
                "campaign_contract_id",
                "campaign_anchor_id",
                "canonicalization_version",
                "protocol_version",
                "effective_seed_catalog_id",
                "effective_manifest_id",
                "case_execution_ledger_id",
                "producer_authority",
                "verifier_authority",
                "runner_authority",
                "ordered_case_commit_entries",
                "ordered_full_run_f2_reconciliation_records",
                "campaign_status",
                "all_case_campaign_manifest_id",
            ],
            "campaign_status_literal": "ALL_475_CASES_INDEPENDENTLY_VERIFIED_UNDER_IMMUTABLE_F2",
            "manifest_identity_rule": "DOMAIN_SEPARATED_SHA256_OVER_EVERY_PRECEDING_ORDERED_MEMBER",
            "finalization_revalidation_rule": "REVALIDATE_ANCHOR_ALL_CASE_COMMITS_ALL_CLOSURES_ALL_AUTHORITIES_ALL_ROLE_SOURCES_AND_EXACT_F2_AGGREGATE",
            "fsync_rule": "FSYNC_EVERY_FILE_AND_DIRECTORY_BOTTOM_UP_THEN_RENAME_AND_FSYNC_ACCEPTED_PARENT",
            "accepted_root_collision_policy": "REJECT_WITHOUT_OVERWRITE_MERGE_OR_DELETE",
            "partial_acceptance_policy": "FORBIDDEN",
            "check_mode_rule": "READ_ONLY_COMPLETE_RECONSTRUCTION_NO_REPAIR_NORMALIZATION_OR_DELETION",
        },
        "architecture_decision_contract": {
            "selected_architecture": "SEQUENTIAL_RESUMABLE_VERIFIED_CASE_COMMITS_WITH_ROOT_LAST_CAMPAIGN_PUBLICATION",
            "ordered_alternative_records": [
                {
                    "alternative_position": 1,
                    "architecture": "EDIT_ACCEPTED_SIX_CASE_BINARIES_IN_PLACE",
                    "decision": "REJECTED",
                    "reason": "DESTROYS_IMMUTABLE_REGRESSION_AUTHORITIES_AND_DOES_NOT_ADD_GENERIC_TYPED_LEGALITY",
                },
                {
                    "alternative_position": 2,
                    "architecture": "MONOLITHIC_475_CASE_RUN_WITH_NO_CHECKPOINTS",
                    "decision": "REJECTED",
                    "reason": "MAXIMIZES_CRASH_REWORK_AND_HAS_NO_SAFE_RESUME_BOUNDARY",
                },
                {
                    "alternative_position": 3,
                    "architecture": "PUBLISH_EACH_CASE_AS_ACCEPTED_IMMEDIATELY",
                    "decision": "REJECTED",
                    "reason": "EXPOSES_PARTIAL_CAMPAIGN_AS_ACCEPTED_STATE",
                },
                {
                    "alternative_position": 4,
                    "architecture": "UNBOUNDED_OR_COMPLETION_ORDER_PARALLELISM",
                    "decision": "REJECTED",
                    "reason": "BREAKS_DETERMINISTIC_ORDER_AND_MULTIPLIES_RESOURCE_AND_RACE_SURFACE_BEFORE_BASELINE_QUALIFICATION",
                },
                {
                    "alternative_position": 5,
                    "architecture": "SEQUENTIAL_RESUMABLE_ROOT_LAST",
                    "decision": "SELECTED",
                    "reason": "PRESERVES_DETERMINISM_BOUNDS_SIMULTANEOUS_RESOURCES_AND_LIMITS_CRASH_REWORK_WITHOUT_PARTIAL_ACCEPTANCE",
                },
            ],
            "parallel_successor_policy": "MAY_BE_PROPOSED_ONLY_AS_A_NEW_VERSION_AFTER_SEQUENTIAL_BASELINE_ACCEPTANCE_WITH_IDENTICAL_SEMANTIC_OUTPUT",
        },
        "implementation_sequence_contract": {
            "ordered_packet_records": [
                {
                    "packet_position": 1,
                    "packet": "A4-R475-V0",
                    "scope": "VERSIONED_VERIFIER_AUTHORITY_RESOLVER_GENERIC_TYPED_LEGALITY_AND_RULE_AST_FOUNDATION",
                },
                {
                    "packet_position": 2,
                    "packet": "A4-R475-V1",
                    "scope": "ALL_66_INTRINSIC_TEMPLATE_CASES_PLUS_SIX_CASE_REGRESSION",
                },
                {
                    "packet_position": 3,
                    "packet": "A4-R475-V2",
                    "scope": "ALL_406_GENERIC_PROFILE_ATTAINMENT_CASES",
                },
                {
                    "packet_position": 4,
                    "packet": "A4-R475-V3",
                    "scope": "SPECIAL_CASES_69_435_475_AND_ALL_475_VERIFIER_ACCEPTANCE",
                },
                {
                    "packet_position": 5,
                    "packet": "A4-R475-P",
                    "scope": "GENERIC_INDEPENDENT_WITNESS_SYNTHESIS_AND_ALL_475_PRODUCER_ACCEPTANCE",
                },
                {
                    "packet_position": 6,
                    "packet": "A4-R475-R",
                    "scope": "RESUMABLE_SINGLE_WRITER_PARENT_CAMPAIGN_RUNNER_AND_CRASH_MATRIX",
                },
                {
                    "packet_position": 7,
                    "packet": "A4-R475-E",
                    "scope": "COMPLETE_475_CASE_EXECUTION_INDEPENDENT_REPLAY_AND_ACCEPTANCE",
                },
            ],
            "advance_rule": "ONE_PACKET_ACTIVE_ONLY_AFTER_PREDECESSOR_ACCEPTANCE_AND_NO_UNEXPECTED_RED_TEST",
        },
        "acceptance_contract": {
            "contract_acceptance_rule": "INDEPENDENT_RECONSTRUCTION_OF_ALL_475_EFFECTIVE_CASE_RECORDS_AUTHORITIES_RESOURCES_AND_LIFECYCLE",
            "required_contract_case_count": CASE_COUNT,
            "required_f0_record_count": 12,
            "required_f2_record_count": 18,
            "required_intentional_fail_first_role_failures": 3,
            "six_case_nonpilot_rejection_must_remain_true": True,
            "all_case_execution_is_accepted_by_this_contract": False,
            "raw_v8_step2_is_accepted_by_this_contract": False,
            "formal_stage1_is_accepted_by_this_contract": False,
        },
    }
    contract["all_case_campaign_contract_id"] = _semantic_id(
        CONTRACT_DOMAIN, contract
    )
    return contract


def _atomic_write(path: pathlib.Path, raw: bytes) -> None:
    _require(path.is_absolute(), "OUTPUT_PATH_INVALID")
    _require(path.parent.is_dir() and not path.parent.is_symlink(), "OUTPUT_PARENT_INVALID")
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
            _require(written > 0, "OUTPUT_WRITE_STALLED")
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
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--write")
    modes.add_argument("--check")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        arguments = _arguments(sys.argv[1:] if argv is None else argv)
        root = pathlib.Path(arguments.repository_root)
        _require(
            root.is_absolute() and pathlib.Path(os.path.realpath(root)) == root,
            "REPOSITORY_ROOT_INVALID",
        )
        contract = build_contract(root)
        raw = _pretty_bytes(contract)
        selected = arguments.write if arguments.write is not None else arguments.check
        path = pathlib.Path(selected)
        _require(path.is_absolute(), "OUTPUT_PATH_INVALID")
        if arguments.write is not None:
            _atomic_write(path, raw)
        else:
            _require(path.is_file() and not path.is_symlink(), "CHECK_TARGET_INVALID")
            _require(path.read_bytes() == raw, "CONTRACT_STALE")
    except (ContractFailure, OSError, ValueError, TypeError, KeyError) as error:
        sys.stderr.write(f"{ERROR_PREFIX}REJECTED: {type(error).__name__}: {error}\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
