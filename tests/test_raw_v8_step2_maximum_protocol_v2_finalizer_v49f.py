"""Fail-first contract for the S1-A3 V2 finalization manifest.

This suite owns an independent manifest oracle.  It does not import the seed
generator, either preflight, or the comparator.  The current tree is expected
to have exactly one conformance failure until the standalone finalizer is
implemented: ``FINALIZER_PATH`` does not yet exist.  The oracle and hostile
mutation tests must already pass, so implementation cannot define the target
after seeing its own output.
"""

from __future__ import annotations

import ast
import copy
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
SEED_PATH = (
    ROOT / "scripts/tests/raw_v8_step2_maximum_protocol_v2_seed_catalog_v49f.json"
)
CONTRACT_PATH = (
    ROOT / "scripts/tests/raw_v8_step2_maximum_protocol_v2_preflight_contract_v49f.json"
)
FINALIZER_PATH = (
    ROOT / "scripts/tests/finalize_raw_v8_step2_maximum_protocol_v2_v49f.py"
)
MANIFEST_PATH = (
    ROOT
    / "scripts/tests/raw_v8_step2_maximum_protocol_v2_finalization_manifest_v49f.json"
)
CONTROL_PATH = ROOT / "docs/research/stage1_execution_control_2026-08-08.md"
LEGACY_CANDIDATE_PATH = (
    ROOT
    / "docs/research/v4_9f_a2_raw_v8_step2_constructive_maximum_protocol_v2_freeze_2026-08-02.md"
)

MANIFEST_VERSION = (
    "riskyieldmm.raw_v8_step2_external_schema_v2.finalization_manifest.v1"
)
FINALIZATION_STATUS = "FINAL_V2_F2_FROZEN"
CANONICALIZATION_VERSION = "riskyieldmm_canonical_json_v1"
MANIFEST_DOMAIN = "RiskYieldMMStep2FinalizationManifestV1V4_9F_RawV8"
SEMANTIC_VERSION = (
    "riskyieldmm.raw_v8_step2_external_schema_v2.preflight_semantic_payload.v1"
)
COMPARISON_VERSION = (
    "riskyieldmm.raw_v8_step2_external_schema_v2.preflight_comparison_payload.v1"
)
PROTOCOL_VERSION = (
    "riskyieldmm.raw_v8_step2_external_schema_v2.constructive_maximum_protocol.v2"
)
PROTOCOL_SEMANTICS_ID = (
    "34f6c285e1ce5c2b0496a63f6eda3ee15f72d6268f5ba9dbb0748e01e61d38fb"
)
SEED_ID = "ac22151fa74702ac1488924f01161eaa38574545e6272a290db6b0bbd288ae5f"
CONTRACT_ID = "6609ad7b9abf21432136e49af178e20c17cb7bc27d3b444a4b6f01a17073fc76"
SEMANTIC_RAW_SHA256 = "27d583074ed3b684d969644222ce025791e85fd7f28578b1ef9ca6fd6e573081"
SEMANTIC_PAYLOAD_ID = "d51f81fe078309ee817a4f7ab93be3891ef4fbb5aab45e41b8e0d60ce3103c1b"
COUNT_VECTOR_SHA256 = "a9d7cd1ce1cb0aa6dccb175a5a1c49e69f1e672e18a9b4419ccbcdfedc1f79a8"
COMPARISON_RAW_SHA256 = (
    "44e1572ea8a9bfd19a876e80dcb027a503f9e720389a2671d02c37bc740f9b43"
)
COMPARISON_PAYLOAD_ID = (
    "8fca05661cbf728468b442466f613b7840b9c462cb2fd55302d34569fe243256"
)
U128_MAX = (1 << 128) - 1

ROOT_MEMBERS = (
    "finalization_manifest_version",
    "finalization_status",
    "canonicalization_version",
    "protocol_version",
    "protocol_counting_semantics_id",
    "seed_authority",
    "preflight_contract_authority",
    "ordered_implementation_authorities",
    "semantic_evidence",
    "comparison_evidence",
    "ordered_f2_limit_records",
    "finalization_manifest_id",
)
SEED_AUTHORITY_MEMBERS = (
    "repository_relative_path",
    "raw_octets",
    "raw_sha256",
    "catalog_version",
    "seed_catalog_id",
)
CONTRACT_AUTHORITY_MEMBERS = (
    "repository_relative_path",
    "raw_octets",
    "raw_sha256",
    "contract_version",
    "contract_id",
)
IMPLEMENTATION_AUTHORITY_MEMBERS = (
    "implementation_position",
    "implementation_label",
    "repository_relative_path",
    "raw_octets",
    "raw_sha256",
    "algorithm_marker",
)
SEMANTIC_EVIDENCE_MEMBERS = (
    "preflight_semantic_payload_version",
    "raw_octets",
    "raw_sha256",
    "semantic_payload_id",
    "semantic_count_vector_sha256",
    "ordered_metric_evidence_records",
)
METRIC_EVIDENCE_MEMBERS = (
    "metric_position",
    "metric_name",
    "full_run_aggregation",
    "required_per_case",
    "required_full_run",
)
COMPARISON_EVIDENCE_MEMBERS = (
    "comparison_payload_version",
    "raw_octets",
    "raw_sha256",
    "comparison_payload_id",
    "comparison_status",
    "implementation_a_raw_sha256",
    "implementation_b_raw_sha256",
    "implementation_a_semantic_payload_id",
    "implementation_b_semantic_payload_id",
    "semantic_count_vector_sha256",
    "semantic_payload_bytes_equal",
    "all_475_case_records_equal",
    "all_18_metric_summaries_equal",
    "all_resource_limits_satisfied",
)
F2_MEMBERS = (
    "metric_position",
    "metric_name",
    "full_run_aggregation",
    "required_per_case",
    "per_case_rounding_unit",
    "f2_per_case",
    "per_case_f0_ceiling",
    "required_full_run",
    "full_run_rounding_unit",
    "f2_full_run",
    "full_run_f0_ceiling",
)

MAXIMUM_CASE_VALUES = (
    1,
    2_101_890,
    158,
    1_002,
    4_204_335,
    20,
    158,
    106_427,
    789_383,
    880_113,
    1_481_221,
    10,
    48_649,
    569,
    17,
    569,
    54_297,
    37_195,
)
FULL_RUN_VALUES = (
    475,
    29_189_597,
    66_119,
    417_528,
    170_915_620,
    1_735,
    66_119,
    44_461_267,
    329_067_149,
    367_039_374,
    619_175_993,
    4_160,
    4_198_492,
    46_268,
    17,
    569,
    54_297,
    15_585_644,
)
EXPECTED_F2_PER_CASE = (
    1,
    2_102_272,
    1_024,
    1_024,
    4_204_544,
    1_024,
    1_024,
    106_496,
    790_528,
    880_640,
    1_482_752,
    1_024,
    49_152,
    1_024,
    17,
    569,
    57_344,
    40_960,
)
EXPECTED_F2_FULL_RUN = (
    475,
    29_190_144,
    66_560,
    417_792,
    170_915_840,
    2_048,
    66_560,
    45_088_768,
    329_252_864,
    368_050_176,
    619_708_416,
    5_120,
    4_199_424,
    47_104,
    17,
    569,
    57_344,
    15_728_640,
)

CONTROL_PATTERN = re.compile(
    r"<!-- STAGE1_CONTROL_JSON_START\n(?P<payload>\{.*?\})\n"
    r"STAGE1_CONTROL_JSON_END -->",
    re.DOTALL,
)


class OracleReject(RuntimeError):
    """Independent A3-T oracle rejection."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise OracleReject(message)


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


def _manifest_id(value: dict[str, Any]) -> str:
    payload = {name: value[name] for name in ROOT_MEMBERS[:-1]}
    return _sha256(_canonical_bytes({"domain": MANIFEST_DOMAIN, "payload": payload}))


def _closed(value: Any, members: tuple[str, ...], label: str) -> dict[str, Any]:
    _require(type(value) is dict and set(value) == set(members), f"{label} members")
    return value


def _u128(value: Any, label: str) -> int:
    _require(
        type(value) is int and 0 <= value <= U128_MAX,
        f"{label} is not UInt128",
    )
    return value


def _hex(value: Any, label: str) -> str:
    _require(
        type(value) is str
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value),
        f"{label} is not SHA-256",
    )
    return value


def _round_up(value: int, unit: int) -> int:
    value = _u128(value, "F1")
    unit = _u128(unit, "rounding unit")
    _require(unit > 0, "zero rounding unit")
    remainder = value % unit
    increment = (unit - remainder) % unit
    _require(value <= U128_MAX - increment, "rounding overflow")
    return value + increment


def _control() -> dict[str, Any]:
    match = CONTROL_PATTERN.search(CONTROL_PATH.read_text(encoding="utf-8"))
    assert match is not None
    value = json.loads(match.group("payload"))
    assert type(value) is dict
    return value


def _source_record(role: str) -> dict[str, Any]:
    records = _control()["s1_a2_snapshot"]["ordered_authority_records"]
    return next(row for row in records if row["artifact_role"] == role)


def _fixture_manifest() -> tuple[dict[str, Any], bytes]:
    seed = json.loads(SEED_PATH.read_bytes())
    contract = json.loads(CONTRACT_PATH.read_bytes())
    metrics = seed["resource_metric_catalog"]["ordered_metric_records"]
    metric_evidence = []
    f2_records = []
    for position, (metric, per_case, full_run) in enumerate(
        zip(metrics, MAXIMUM_CASE_VALUES, FULL_RUN_VALUES, strict=True), 1
    ):
        metric_evidence.append(
            {
                "metric_position": position,
                "metric_name": metric["metric_name"],
                "full_run_aggregation": metric["full_run_aggregation"],
                "required_per_case": per_case,
                "required_full_run": full_run,
            }
        )
        f2_records.append(
            {
                "metric_position": position,
                "metric_name": metric["metric_name"],
                "full_run_aggregation": metric["full_run_aggregation"],
                "required_per_case": per_case,
                "per_case_rounding_unit": metric["per_case_f2_rounding_unit"],
                "f2_per_case": _round_up(per_case, metric["per_case_f2_rounding_unit"]),
                "per_case_f0_ceiling": metric["per_case_f0_ceiling"],
                "required_full_run": full_run,
                "full_run_rounding_unit": metric["full_run_f2_rounding_unit"],
                "f2_full_run": _round_up(full_run, metric["full_run_f2_rounding_unit"]),
                "full_run_f0_ceiling": metric["full_run_f0_ceiling"],
            }
        )

    seed_source = _source_record("PREFLIGHT_CONTRACT")
    implementations = []
    for position, (label, role, marker) in enumerate(
        (
            ("A", "PREFLIGHT_A", "ITERATIVE_CATALOG_INTERPRETER_V1"),
            ("B", "PREFLIGHT_B", "FLAT_LEDGER_PREFIX_SUM_V1"),
            (
                "COMPARATOR",
                "PREFLIGHT_COMPARATOR",
                "RiskYieldMMStep2PreflightComparisonV1V4_9F_RawV8",
            ),
        ),
        1,
    ):
        source = _source_record(role)
        implementations.append(
            {
                "implementation_position": position,
                "implementation_label": label,
                "repository_relative_path": source["repository_relative_path"],
                "raw_octets": source["raw_octets"],
                "raw_sha256": source["raw_sha256"],
                "algorithm_marker": marker,
            }
        )

    a_hash = implementations[0]["raw_sha256"]
    b_hash = implementations[1]["raw_sha256"]
    snapshot = _control()["s1_a2_snapshot"]
    manifest: dict[str, Any] = {
        "finalization_manifest_version": MANIFEST_VERSION,
        "finalization_status": FINALIZATION_STATUS,
        "canonicalization_version": CANONICALIZATION_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "protocol_counting_semantics_id": PROTOCOL_SEMANTICS_ID,
        "seed_authority": {
            "repository_relative_path": str(SEED_PATH.relative_to(ROOT)),
            "raw_octets": len(SEED_PATH.read_bytes()),
            "raw_sha256": _sha256(SEED_PATH.read_bytes()),
            "catalog_version": seed["catalog_version"],
            "seed_catalog_id": SEED_ID,
        },
        "preflight_contract_authority": {
            "repository_relative_path": seed_source["repository_relative_path"],
            "raw_octets": seed_source["raw_octets"],
            "raw_sha256": seed_source["raw_sha256"],
            "contract_version": contract["contract_version"],
            "contract_id": CONTRACT_ID,
        },
        "ordered_implementation_authorities": implementations,
        "semantic_evidence": {
            "preflight_semantic_payload_version": SEMANTIC_VERSION,
            "raw_octets": snapshot["semantic_raw_octets"],
            "raw_sha256": SEMANTIC_RAW_SHA256,
            "semantic_payload_id": SEMANTIC_PAYLOAD_ID,
            "semantic_count_vector_sha256": COUNT_VECTOR_SHA256,
            "ordered_metric_evidence_records": metric_evidence,
        },
        "comparison_evidence": {
            "comparison_payload_version": COMPARISON_VERSION,
            "raw_octets": snapshot["comparison_raw_octets"],
            "raw_sha256": COMPARISON_RAW_SHA256,
            "comparison_payload_id": COMPARISON_PAYLOAD_ID,
            "comparison_status": "EXACT_AGREEMENT",
            "implementation_a_raw_sha256": a_hash,
            "implementation_b_raw_sha256": b_hash,
            "implementation_a_semantic_payload_id": SEMANTIC_PAYLOAD_ID,
            "implementation_b_semantic_payload_id": SEMANTIC_PAYLOAD_ID,
            "semantic_count_vector_sha256": COUNT_VECTOR_SHA256,
            "semantic_payload_bytes_equal": True,
            "all_475_case_records_equal": True,
            "all_18_metric_summaries_equal": True,
            "all_resource_limits_satisfied": True,
        },
        "ordered_f2_limit_records": f2_records,
        "finalization_manifest_id": "",
    }
    manifest["finalization_manifest_id"] = _manifest_id(manifest)
    return manifest, _pretty_bytes(manifest)


def _validate_oracle(value: dict[str, Any], raw: bytes) -> None:
    _require(raw == _pretty_bytes(value), "manifest is not canonical pretty JSON")
    _closed(value, ROOT_MEMBERS, "root")
    _require(value["finalization_manifest_version"] == MANIFEST_VERSION, "version")
    _require(value["finalization_status"] == FINALIZATION_STATUS, "status")
    _require(
        value["canonicalization_version"] == CANONICALIZATION_VERSION,
        "canonicalization",
    )
    _require(value["protocol_version"] == PROTOCOL_VERSION, "protocol")
    _require(
        value["protocol_counting_semantics_id"] == PROTOCOL_SEMANTICS_ID,
        "semantics",
    )

    expected, _expected_raw = _fixture_manifest()
    seed = _closed(value["seed_authority"], SEED_AUTHORITY_MEMBERS, "seed")
    contract = _closed(
        value["preflight_contract_authority"],
        CONTRACT_AUTHORITY_MEMBERS,
        "contract",
    )
    _require(seed == expected["seed_authority"], "seed authority drift")
    _require(
        contract == expected["preflight_contract_authority"],
        "contract authority drift",
    )

    implementations = value["ordered_implementation_authorities"]
    _require(type(implementations) is list and len(implementations) == 3, "sources")
    for position, (record, expected_record) in enumerate(
        zip(
            implementations,
            expected["ordered_implementation_authorities"],
            strict=True,
        ),
        1,
    ):
        _closed(record, IMPLEMENTATION_AUTHORITY_MEMBERS, f"source {position}")
        _require(record == expected_record, f"source {position} drift")

    semantic = _closed(
        value["semantic_evidence"], SEMANTIC_EVIDENCE_MEMBERS, "semantic"
    )
    _require(
        {
            name: semantic[name]
            for name in SEMANTIC_EVIDENCE_MEMBERS
            if name != "ordered_metric_evidence_records"
        }
        == {
            name: expected["semantic_evidence"][name]
            for name in SEMANTIC_EVIDENCE_MEMBERS
            if name != "ordered_metric_evidence_records"
        },
        "semantic seal drift",
    )
    metrics = semantic["ordered_metric_evidence_records"]
    expected_metrics = expected["semantic_evidence"]["ordered_metric_evidence_records"]
    _require(type(metrics) is list and len(metrics) == 18, "metric count")
    for position, (record, expected_record) in enumerate(
        zip(metrics, expected_metrics, strict=True), 1
    ):
        _closed(record, METRIC_EVIDENCE_MEMBERS, f"metric {position}")
        _require(record == expected_record, f"metric {position} drift")

    comparison = _closed(
        value["comparison_evidence"], COMPARISON_EVIDENCE_MEMBERS, "comparison"
    )
    _require(comparison == expected["comparison_evidence"], "comparison drift")
    _require(
        all(
            comparison[name] is True
            for name in (
                "semantic_payload_bytes_equal",
                "all_475_case_records_equal",
                "all_18_metric_summaries_equal",
                "all_resource_limits_satisfied",
            )
        ),
        "comparison is not exact",
    )

    f2_records = value["ordered_f2_limit_records"]
    expected_f2 = expected["ordered_f2_limit_records"]
    _require(type(f2_records) is list and len(f2_records) == 18, "F2 count")
    for position, (record, expected_record) in enumerate(
        zip(f2_records, expected_f2, strict=True), 1
    ):
        _closed(record, F2_MEMBERS, f"F2 {position}")
        for name in (
            "required_per_case",
            "per_case_rounding_unit",
            "f2_per_case",
            "per_case_f0_ceiling",
            "required_full_run",
            "full_run_rounding_unit",
            "f2_full_run",
            "full_run_f0_ceiling",
        ):
            _u128(record[name], f"F2 {position} {name}")
        _require(
            record["f2_per_case"]
            == _round_up(record["required_per_case"], record["per_case_rounding_unit"]),
            f"F2 {position} per-case derivation",
        )
        _require(
            record["f2_full_run"]
            == _round_up(record["required_full_run"], record["full_run_rounding_unit"]),
            f"F2 {position} full-run derivation",
        )
        _require(
            record["required_per_case"]
            <= record["f2_per_case"]
            <= record["per_case_f0_ceiling"],
            f"F2 {position} per-case bounds",
        )
        _require(
            record["required_full_run"]
            <= record["f2_full_run"]
            <= record["full_run_f0_ceiling"],
            f"F2 {position} full-run bounds",
        )
        _require(record == expected_record, f"F2 {position} drift")

    _hex(value["finalization_manifest_id"], "manifest ID")
    _require(value["finalization_manifest_id"] == _manifest_id(value), "manifest ID")


def _reseal(value: dict[str, Any]) -> bytes:
    value["finalization_manifest_id"] = _manifest_id(value)
    return _pretty_bytes(value)


def _strict_parse(raw: bytes) -> dict[str, Any]:
    def closed_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise OracleReject("duplicate JSON member")
            value[key] = item
        return value

    def reject_float(_value: str) -> None:
        raise OracleReject("floating-point JSON")

    try:
        value = json.loads(
            raw.decode("utf-8", "strict"),
            object_pairs_hook=closed_pairs,
            parse_float=reject_float,
            parse_constant=reject_float,
        )
    except (UnicodeError, json.JSONDecodeError) as error:
        raise OracleReject("strict JSON") from error
    _require(type(value) is dict, "root object")
    return value


def _load_finalizer() -> ModuleType:
    if not FINALIZER_PATH.is_file():
        pytest.skip("A3-T expected blocker: standalone finalizer is not implemented")
    spec = importlib.util.spec_from_file_location("raw_v8_v2_finalizer", FINALIZER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_independent_oracle_freezes_all_36_mechanical_f2_values() -> None:
    manifest, raw = _fixture_manifest()
    _validate_oracle(manifest, raw)
    records = manifest["ordered_f2_limit_records"]
    assert tuple(row["f2_per_case"] for row in records) == EXPECTED_F2_PER_CASE
    assert tuple(row["f2_full_run"] for row in records) == EXPECTED_F2_FULL_RUN
    assert records[-1]["f2_full_run"] == 15_728_640
    assert records[-1]["f2_full_run"] < 16_777_216


def _mutate_root_missing(value: dict[str, Any]) -> None:
    del value["comparison_evidence"]


def _mutate_root_extra(value: dict[str, Any]) -> None:
    value["self_asserted_acceptance"] = True


def _mutate_status(value: dict[str, Any]) -> None:
    value["finalization_status"] = "CANDIDATE"


def _mutate_seed(value: dict[str, Any]) -> None:
    value["seed_authority"]["raw_sha256"] = "0" * 64


def _mutate_contract(value: dict[str, Any]) -> None:
    value["preflight_contract_authority"]["contract_id"] = "0" * 64


def _mutate_source_order(value: dict[str, Any]) -> None:
    rows = value["ordered_implementation_authorities"]
    rows[0], rows[1] = rows[1], rows[0]


def _mutate_source_hash(value: dict[str, Any]) -> None:
    value["ordered_implementation_authorities"][2]["raw_sha256"] = "0" * 64


def _mutate_semantic_seal(value: dict[str, Any]) -> None:
    value["semantic_evidence"]["semantic_payload_id"] = "0" * 64


def _mutate_metric_order(value: dict[str, Any]) -> None:
    rows = value["semantic_evidence"]["ordered_metric_evidence_records"]
    rows[0], rows[1] = rows[1], rows[0]


def _mutate_metric_aggregation(value: dict[str, Any]) -> None:
    value["semantic_evidence"]["ordered_metric_evidence_records"][14][
        "full_run_aggregation"
    ] = "SUM"


def _mutate_comparison_flag(value: dict[str, Any]) -> None:
    value["comparison_evidence"]["all_475_case_records_equal"] = False


def _mutate_comparison_semantic_id(value: dict[str, Any]) -> None:
    value["comparison_evidence"]["implementation_b_semantic_payload_id"] = "0" * 64


def _mutate_floor_rounding(value: dict[str, Any]) -> None:
    row = value["ordered_f2_limit_records"][1]
    row["f2_per_case"] = row["required_per_case"] - (
        row["required_per_case"] % row["per_case_rounding_unit"]
    )


def _mutate_percentage_headroom(value: dict[str, Any]) -> None:
    value["ordered_f2_limit_records"][7]["f2_full_run"] += 1_048_576


def _mutate_rounding_unit(value: dict[str, Any]) -> None:
    value["ordered_f2_limit_records"][8]["full_run_rounding_unit"] = 4_096


def _mutate_f2_above_f0(value: dict[str, Any]) -> None:
    row = value["ordered_f2_limit_records"][17]
    row["f2_full_run"] = row["full_run_f0_ceiling"] + 1


@pytest.mark.parametrize(
    "mutation",
    [
        _mutate_root_missing,
        _mutate_root_extra,
        _mutate_status,
        _mutate_seed,
        _mutate_contract,
        _mutate_source_order,
        _mutate_source_hash,
        _mutate_semantic_seal,
        _mutate_metric_order,
        _mutate_metric_aggregation,
        _mutate_comparison_flag,
        _mutate_comparison_semantic_id,
        _mutate_floor_rounding,
        _mutate_percentage_headroom,
        _mutate_rounding_unit,
        _mutate_f2_above_f0,
    ],
    ids=lambda function: function.__name__.removeprefix("_mutate_"),
)
def test_independent_oracle_rejects_hostile_manifest_mutations(
    mutation: Callable[[dict[str, Any]], None],
) -> None:
    manifest, _raw = _fixture_manifest()
    mutation(manifest)
    raw = (
        _reseal(manifest)
        if all(name in manifest for name in ROOT_MEMBERS[:-1])
        else _pretty_bytes(manifest)
    )
    with pytest.raises(OracleReject):
        _validate_oracle(manifest, raw)


def test_independent_oracle_rejects_invalid_identity_and_noncanonical_bytes() -> None:
    manifest, raw = _fixture_manifest()
    manifest["finalization_manifest_id"] = "0" * 64
    with pytest.raises(OracleReject, match="manifest ID"):
        _validate_oracle(manifest, _pretty_bytes(manifest))

    manifest, _raw = _fixture_manifest()
    compact = _canonical_bytes(manifest)
    assert json.loads(compact) == manifest
    with pytest.raises(OracleReject, match="canonical pretty"):
        _validate_oracle(manifest, compact)
    _validate_oracle(manifest, raw)


@pytest.mark.parametrize(
    "raw",
    [
        b'{"a":1,"a":2}',
        b'{"value":1.5}',
        b'{"value":NaN}',
        b"\xff",
    ],
)
def test_strict_parser_rejects_duplicate_float_nonfinite_and_non_utf8(
    raw: bytes,
) -> None:
    with pytest.raises(OracleReject):
        _strict_parse(raw)


def test_legacy_review_failed_markdown_cannot_be_manifest_authority() -> None:
    assert LEGACY_CANDIDATE_PATH.is_file()
    with pytest.raises(OracleReject):
        _strict_parse(LEGACY_CANDIDATE_PATH.read_bytes())


def test_a3_t_requires_standalone_finalizer_with_closed_api() -> None:
    assert FINALIZER_PATH.is_file(), (
        "A3_T_FINALIZER_MISSING: implement the standalone finalizer only after "
        "this oracle and its hostile mutation matrix are frozen"
    )
    module = _load_finalizer()
    for name in (
        "_build_manifest",
        "_derive_metric_records",
        "_parse_json",
        "_publish_atomic",
        "_secure_read",
        "_validate_checked_manifest",
        "_main",
    ):
        assert callable(getattr(module, name, None)), name


def test_finalizer_source_is_standalone_and_contains_no_f1_answer_vector() -> None:
    module = _load_finalizer()
    del module
    source = FINALIZER_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    roots: set[str] = set()
    calls: set[str] = set()
    integer_constants: list[int] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0 and node.module is not None
            roots.add(node.module.split(".", 1)[0])
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                calls.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                calls.add(node.func.attr)
        elif isinstance(node, ast.Constant) and type(node.value) is int:
            integer_constants.append(node.value)
    assert roots <= {
        "ast",
        "hashlib",
        "json",
        "os",
        "pathlib",
        "resource",
        "signal",
        "sys",
        "time",
    }
    assert roots.isdisjoint(
        {
            "importlib",
            "riskyieldmm",
            "scripts",
            "subprocess",
            "tests",
        }
    )
    assert calls.isdisjoint({"__import__", "compile", "eval", "exec"})
    forbidden_large_answers = set(MAXIMUM_CASE_VALUES[1:]) | set(FULL_RUN_VALUES[1:])
    assert forbidden_large_answers.isdisjoint(integer_constants)
    assert "MAXIMUM_CASE_VALUES" not in source
    assert "FULL_RUN_VALUES" not in source


def test_finalizer_derivation_and_builder_match_the_independent_oracle() -> None:
    module = _load_finalizer()
    seed = json.loads(SEED_PATH.read_bytes())
    expected, _raw = _fixture_manifest()
    summaries = []
    for row in expected["semantic_evidence"]["ordered_metric_evidence_records"]:
        summaries.append(
            {
                "metric_position": row["metric_position"],
                "metric_name": row["metric_name"],
                "full_run_aggregation": row["full_run_aggregation"],
                "full_run_value": row["required_full_run"],
                "maximum_case_value": row["required_per_case"],
                "ordered_maximum_case_positions": [1],
            }
        )
    metric_evidence, f2_records = module._derive_metric_records(seed, summaries)
    assert (
        metric_evidence
        == expected["semantic_evidence"]["ordered_metric_evidence_records"]
    )
    assert f2_records == expected["ordered_f2_limit_records"]

    mutated = copy.deepcopy(summaries)
    mutated[1]["full_run_value"] += 1
    changed_evidence, changed_f2 = module._derive_metric_records(seed, mutated)
    assert changed_evidence[1]["required_full_run"] == FULL_RUN_VALUES[1] + 1
    assert changed_f2[1]["f2_full_run"] == EXPECTED_F2_FULL_RUN[1]
    assert changed_evidence != metric_evidence

    reordered = copy.deepcopy(summaries)
    reordered[0], reordered[1] = reordered[1], reordered[0]
    with pytest.raises(module.Reject):
        module._derive_metric_records(seed, reordered)


def test_finalizer_checked_manifest_and_atomic_output_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_finalizer()
    manifest, raw = _fixture_manifest()
    assert module._validate_checked_manifest(raw, raw) == manifest
    with pytest.raises(module.Reject):
        module._validate_checked_manifest(raw + b" ", raw)

    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    target = private / "manifest.json"
    module._publish_atomic(target, raw)
    assert target.read_bytes() == raw
    assert target.stat().st_mode & 0o777 == 0o600
    with pytest.raises(module.Reject):
        module._publish_atomic(target, b"replacement\n")
    assert target.read_bytes() == raw

    symlink_parent = tmp_path / "symlink-parent"
    symlink_parent.symlink_to(private, target_is_directory=True)
    with pytest.raises(module.Reject):
        module._publish_atomic(symlink_parent / "other.json", raw)

    rollback_target = private / "rollback.json"
    real_lstat = module.os.lstat

    def fail_published_metadata(path: os.PathLike[str] | str):
        status = real_lstat(path)
        if Path(path) == rollback_target:
            return SimpleNamespace(
                st_mode=0,
                st_size=status.st_size,
                st_uid=status.st_uid,
            )
        return status

    monkeypatch.setattr(module.os, "lstat", fail_published_metadata)
    with pytest.raises(module.Reject):
        module._publish_atomic(rollback_target, raw)
    assert not rollback_target.exists()
    assert not any(private.glob(".rollback.json.finalizer.tmp-*"))


@pytest.mark.parametrize(
    "raw",
    [
        b'{"a":1,"a":2}',
        b'{"value":1.5}',
        b'{"value":Infinity}',
        b"\xff",
    ],
)
def test_finalizer_strict_parser_rejects_noncanonical_json_domains(raw: bytes) -> None:
    module = _load_finalizer()
    with pytest.raises(module.Reject):
        module._parse_json(raw)


def test_finalizer_rejects_same_byte_authority_timestamp_drift(tmp_path: Path) -> None:
    module = _load_finalizer()
    authority = tmp_path / "authority.bin"
    authority.write_bytes(b"fixed authority\n")
    raw, status = module._secure_read(authority, 1_024)
    snapshot = {
        "path": authority,
        "raw_octets": len(raw),
        "raw_sha256": _sha256(raw),
        "status_identity": module._status_identity(status),
    }
    os.utime(
        authority,
        ns=(status.st_atime_ns, status.st_mtime_ns + 1_000_000),
    )
    with pytest.raises(module.Reject) as error:
        module._verify_file_snapshot(snapshot)
    assert error.value.code == "INPUT_RACE_DETECTED"


@pytest.mark.parametrize(
    "body",
    [
        (
            "import pathlib,sys\n"
            "pathlib.Path(sys.argv[1]).write_bytes(b'{}\\n')\n"
            "print('noise')\n"
        ),
        "import sys\nsys.exit(3)\n",
        "pass\n",
        (
            "import pathlib,sys\n"
            "target=pathlib.Path(sys.argv[1])\n"
            "target.write_bytes(b'{}\\n')\n"
            "(target.parent/'extra').write_bytes(b'x')\n"
        ),
    ],
    ids=("noisy", "nonzero", "partial", "extra_output"),
)
def test_finalizer_child_boundary_rejects_noisy_nonzero_partial_and_extra_output(
    tmp_path: Path,
    body: str,
) -> None:
    module = _load_finalizer()
    contract = json.loads(CONTRACT_PATH.read_bytes())
    child = tmp_path / "child.py"
    child.write_text(body, encoding="utf-8")
    staging = tmp_path / "staging"
    output = staging / "output"
    staging.mkdir(mode=0o700)
    output.mkdir(mode=0o700)
    arguments = [
        sys.executable,
        "-I",
        "-S",
        "-B",
        str(child),
        str(output / "result.json"),
    ]
    with pytest.raises(module.Reject):
        module._run_child(
            "HOSTILE_FIXTURE",
            arguments,
            output,
            "result.json",
            contract,
            staging,
        )


def test_finalizer_child_boundary_rejects_parent_observed_resource_excess(
    tmp_path: Path,
) -> None:
    module = _load_finalizer()
    contract = json.loads(CONTRACT_PATH.read_bytes())
    limits = contract["resource_enforcement_contract"]["ordered_f0_limit_records"]
    temporary = next(
        row for row in limits if row["resource_name"] == "F1_TEMPORARY_STORAGE_OCTETS"
    )
    temporary["expected_value"] = 0
    child = tmp_path / "resource_child.py"
    child.write_text(
        "import pathlib,sys\n"
        "pathlib.Path(sys.argv[1]).write_bytes(b'allocated output\\n')\n",
        encoding="utf-8",
    )
    staging = tmp_path / "staging"
    output = staging / "output"
    staging.mkdir(mode=0o700)
    output.mkdir(mode=0o700)
    arguments = [
        sys.executable,
        "-I",
        "-S",
        "-B",
        str(child),
        str(output / "result.json"),
    ]
    with pytest.raises(module.Reject) as error:
        module._run_child(
            "RESOURCE_FIXTURE",
            arguments,
            output,
            "result.json",
            contract,
            staging,
        )
    assert error.value.code == "RESOURCE_LIMIT_EXCEEDED"


def test_finalizer_invalid_cli_is_silent_bounded_and_publishes_nothing(
    tmp_path: Path,
) -> None:
    completed = subprocess.run(
        [sys.executable, "-I", "-S", "-B", str(FINALIZER_PATH), "--bad"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        env={
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONHASHSEED": "0",
        },
    )
    assert completed.returncode == 2
    assert completed.stdout == b""
    assert completed.stderr.startswith(
        b"RAW_V8_STEP2_MAXIMUM_PROTOCOL_V2_FINALIZER_INVOCATION_INVALID: "
    )
    assert completed.stderr.count(b"\n") == 1
    assert not any(tmp_path.iterdir())


def test_finalizer_manifest_path_is_reserved_for_a3_f() -> None:
    if not FINALIZER_PATH.is_file():
        pytest.skip("A3-F follows the expected A3-T missing-finalizer failure")
    assert MANIFEST_PATH.is_file(), (
        "A3_F_MANIFEST_MISSING: write the exact canonical manifest only after "
        "the standalone finalizer passes the fail-first contract"
    )
    manifest = _strict_parse(MANIFEST_PATH.read_bytes())
    _validate_oracle(manifest, MANIFEST_PATH.read_bytes())
