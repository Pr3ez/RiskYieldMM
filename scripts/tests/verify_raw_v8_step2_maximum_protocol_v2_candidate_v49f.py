#!/usr/bin/env python3
"""Independent S1-A4 verifier for one closed constructive V2 candidate.

The accepted predecessor slice implements the frozen exhaustive case-5 Boolean
attainer.  A4-P6-V0 adds an exact predecessor/successor authority dispatcher and
read barrier without replacing that path.  A4-P6-V1 adds successor cases 24 and
54.  A4-P6-V2 adds only the exact local-shutdown profile at case 69.  A4-P6-V3
adds exact case 435 through its versioned packed-context transport.  A4-P6-V4
adds the separate local-minimality result at case 475.  The candidate is data,
never proof: this process reloads
every pinned authority before reading it and independently recomputes legality,
the exact bound, attainment, identities, and resources.
"""

import hashlib
import json
import os
import pathlib
import stat
import sys
import tempfile

SOURCE_MARKER = "INDEPENDENT_V2_CONSTRUCTIVE_VERIFIER_V1"
ERROR_PREFIX = "RAW_V8_STEP2_MAXIMUM_PROTOCOL_V2_VERIFIER_"

BOUNDARY_RELATIVE_PATH = (
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_constructive_boundary_v49f.json"
)
BOUNDARY_OCTETS = 27_334
BOUNDARY_SHA256 = "05468ec3411869fc5b4b5c60d2820e58f8ebf0af96dea978f06d92705fe3bb2b"
BOUNDARY_ID = "bdc7363ae28dfe9a1c1dc132808cb1bd4a06c409201cd49b31e394893142a7ed"
BOUNDARY_DOMAIN = "RiskYieldMMStep2ConstructiveExecutionBoundaryV1V4_9F_RawV8"
SEED_RELATIVE_PATH = (
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_seed_catalog_v49f.json"
)
MANIFEST_RELATIVE_PATH = (
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_finalization_manifest_v49f.json"
)

SUCCESSOR_BOUNDARY_RELATIVE_PATH = (
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_case435_boundary_delta_v49f.json"
)
SUCCESSOR_BOUNDARY_OCTETS = 4_806
SUCCESSOR_BOUNDARY_SHA256 = (
    "208d0cd50eb0bbfe206148dbf58df862f8adc857e382623e91e4e10d942c936c"
)
SUCCESSOR_BOUNDARY_ID = (
    "7d4c06f56cd3cacd97cc4ff655e31f380fe9231c6c7c1374caee499186e1f73d"
)
SUCCESSOR_BOUNDARY_DOMAIN = (
    "RiskYieldMMStep2Case435ExactBoundaryDeltaV1V4_9F_RawV8"
)

PACKED_CONTEXT_BOUNDARY_RELATIVE_PATH = (
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_"
    "case435_context_pack_boundary_delta_v49f.json"
)
PACKED_CONTEXT_BOUNDARY_OCTETS = 6_049
PACKED_CONTEXT_BOUNDARY_SHA256 = (
    "985f0d67a545d036f1777a627f01b609d396a39c690ac81c1bacfc4f7563f56b"
)
PACKED_CONTEXT_BOUNDARY_ID = (
    "c8448f57dcdc3e4f1f3239043ed4977013efbd99c750cb2e2e857025f5ac0acd"
)
PACKED_CONTEXT_BOUNDARY_DOMAIN = (
    "RiskYieldMMStep2Case435ContextPackBoundaryDeltaV1V4_9F_RawV8"
)
CASE435_CONTEXT_PACK_VERSION = (
    "riskyieldmm.raw_v8_step2_external_schema_v2.case435_context_pack.v1"
)
CASE435_CONTEXT_PACK_DOMAIN = "RiskYieldMMStep2Case435ContextPackV1V4_9F_RawV8"
CASE435_PACKED_CANDIDATE_VERSION = (
    "riskyieldmm.raw_v8_step2_external_schema_v2."
    "constructive_candidate_envelope.case435_packed_context.v1"
)
CASE435_PACKED_CANDIDATE_DOMAIN = (
    "RiskYieldMMA2MStep2ExternalSchemaV2Case435PackedContextCandidateV1V4_9F_RawV8"
)

SEED_DELTA_RELATIVE_PATH = (
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_case435_seed_delta_v49f.json"
)
SEED_DELTA_OCTETS = 22_976
SEED_DELTA_SHA256 = (
    "5ce6b2156389ff0aecad7272a564308662a6ec3a77c4b94bfcae7ce32739c3da"
)
SUCCESSOR_SEED_ID = (
    "7fad47e881624d0f39809e72ce2d3d3fd81fb8c85f854fe8332faf543cd1120b"
)
SEED_DELTA_DOMAIN = "RiskYieldMMStep2Case435ExactSeedDeltaV1V4_9F_RawV8"

MANIFEST_DELTA_RELATIVE_PATH = (
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_case435_manifest_delta_v49f.json"
)
MANIFEST_DELTA_OCTETS = 2_192
MANIFEST_DELTA_SHA256 = (
    "daa55d18aa8adfcef9b8a6ea2c6fa734f7922888a902eb863c6307c0fc13bacf"
)
SUCCESSOR_MANIFEST_ID = (
    "6aed1139c158f8685bcb226697a2efe57af3c42f57831173bd7b3ea169025d9c"
)
MANIFEST_DELTA_DOMAIN = (
    "RiskYieldMMStep2Case435ExactManifestDeltaV1V4_9F_RawV8"
)

TARGET_DELTA_RELATIVE_PATH = (
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_case435_six_case_target_delta_v49f.json"
)
TARGET_DELTA_OCTETS = 4_768
TARGET_DELTA_SHA256 = (
    "394da62c1b5146990b2769feaefa1c06c75387ab7a38ec410ec7e327699b340b"
)
SUCCESSOR_TARGET_ID = (
    "a000285d1bedd88306786ea33e1be9cc7d2a8459fe75b20c045f7174d52cc072"
)
TARGET_DELTA_DOMAIN = (
    "RiskYieldMMStep2Case435ExactSixCaseTargetDeltaV1V4_9F_RawV8"
)

SUCCESSOR_F2_ID = (
    "5b2171f64c082ddaa5ecbeb19e2e2f5b952c07336a097364f23fd1658c3d944f"
)
SUCCESSOR_F2_DOMAIN = (
    "RiskYieldMMStep2Case435ExactF2ResourceLimitCatalogV2V4_9F_RawV8"
)
SUCCESSOR_CASE435_PROGRAM_ID = (
    "160486e8c6023b4cfb7ac430065a1dd8c8c422342535fbd5b9b0bceb2ca2e820"
)
SUCCESSOR_CASE435_PLAN_ID = (
    "343259e38b6050fac5905fdc7ed6dca6d345d32c07b8370085bdf865793e7ad8"
)
CASE435_EXACTNESS_JOIN_ID = (
    "2abf00603826f93bb6a538511bbd49ee45096901edbf9bc63c7d0cefb9e7fc3f"
)
CASE435_EXACT_MAXIMUM_OCTETS = 257_887
CASE435_PREDECESSOR_STRUCTURAL_UPPER_OCTETS = 262_143
CASE435_POSITION = 435
CASE435_TYPE = "TargetObservationV2"
CASE435_ROOT_TYPE = "TargetObservationRootV2"
CASE435_SELECTOR_TYPE = "CheckpointSelectorV1"
CASE435_TARGET_REGISTRY_TYPE = "TargetFieldRegistryV1"
CASE435_MARKER_CONTRACT_TYPE = "MarkerContractV1"
CASE435_PROFILE_ID = (
    "505dac244288e6fb666919c99567f883c28ed573a898ce2a5dd680744dd57540"
)
CASE435_PROFILE_POSITION = 369
CASE435_MEASURED_SEQUENCE_ORDINAL = 64
CASE435_OBSERVATION_COUNT = 67
CASE435_APPLICATION_INVOCATION_COUNT = 137
CASE435_RULE_EVALUATION_COUNT = 12_531
CASE435_DIRECT_EXPRESSION_NODE_COUNT = 125_431
CASE435_PROFILE_POINTER = (
    "/operation_contracts/maximum_constraint_scope_profile_catalog/368"
)
CASE435_SELECTOR_POINTER = "/checkpoint_selector_catalog/3/selector"
CASE435_TARGET_REGISTRY_POINTER = "/target_field_registry"
CASE435_MARKER_CONTRACT_POINTER = "/marker_contract"
CASE435_APPLICATIONS = (
    (
        "APPLY/SELECTOR_MARKER_CONTRACT_V1",
        "30f3a8688435dff87bc5ff329e7a9dd6bbbf40c71de5dd746a4cb1e9008b3ee5",
        "RULE/CROSS/SELECTOR_MARKER_CONTRACT_V1",
        1,
        "SINGLE_ZERO_NULL_BOUND_V1",
    ),
    (
        "APPLY/V2_OBSERVATION_AGGREGATE_REGISTRY_V1",
        "0fff77cbc03f9fcf019e8352875d9b7f49a3ab8a0ed374e9d5b9bb2f7f9a38fb",
        "RULE/CROSS/V2_OBSERVATION_AGGREGATE_REGISTRY_V1",
        67,
        "ZERO_BASED_OBSERVATION_RANGE_V1",
    ),
    (
        "APPLY/V2_OBSERVATION_FIELDS_REGISTRY_V1",
        "87b0ee70e1eab470868e357facd3bb6eb203ce4ed8363cbd6fa30a6ee86c8d63",
        "RULE/CROSS/V2_OBSERVATION_FIELD_REGISTRY_V1",
        67,
        "ZERO_BASED_OBSERVATION_RANGE_V1",
    ),
    (
        "APPLY/V2_ROOT_OBSERVATION_MEMBERSHIP_V1",
        "0737d82dae748ff1bf3b19230be2196973c7d6d0fa6c97ef834e9517e09e5f0a",
        "RULE/CROSS/V2_ROOT_OBSERVATION_MEMBERSHIP_V1",
        1,
        "SINGLE_ZERO_NULL_BOUND_V1",
    ),
    (
        "APPLY/V2_ROOT_SELECTOR_LIFECYCLE_V1",
        "86a3acbf53805768a1a462fe28c75a7e7192487f71579ba021aa03d7992a9a42",
        "RULE/CROSS/V2_ROOT_SELECTOR_LIFECYCLE_V1",
        1,
        "SINGLE_ZERO_NULL_BOUND_V1",
    ),
)
SUCCESSOR_PILOT_CASE_POSITIONS = (5, 24, 54, 69, 435, 475)

PREDECESSOR_TARGET_RELATIVE_PATH = (
    "tests/test_raw_v8_step2_maximum_protocol_v2_six_case_qualification_fail_first_v49f.py"
)
PREDECESSOR_TARGET_OCTETS = 60_279
PREDECESSOR_TARGET_SHA256 = (
    "12c1ff23ca6a7b58ddcda205ae017af15d7eef5be799ca7385231777c443a886"
)

TYPED_RULE_RUNTIME_RELATIVE_PATH = (
    "scripts/tests/validate_raw_v8_step2_external_schema_v2_rule_runtime_v49f.py"
)
TYPED_RULE_RUNTIME_OCTETS = 249_268
TYPED_RULE_RUNTIME_SHA256 = (
    "47aa90d897e8dbae5e244b7c04cbd82dfe036b0292d36ef0f5552c868627ab22"
)

SUCCESSOR_PROGRAM_DOMAIN = (
    "RiskYieldMMStep2Case435ExactProfileConditioningProgramV2V4_9F_RawV8"
)
SUCCESSOR_PLAN_DOMAIN = (
    "RiskYieldMMStep2Case435ExactLogicalCountPlanV4V4_9F_RawV8"
)

SEED_ID = "ac22151fa74702ac1488924f01161eaa38574545e6272a290db6b0bbd288ae5f"
MANIFEST_ID = "edde204e98ed1caeeb8ae270487d85e39a2168e0a3692ce1d8748d2d8e7fd858"
MANIFEST_SHA256 = "0136fba014287605336193f782b4885f16e0163000d36429ceb0dfaf0cea52e0"
MANIFEST_DOMAIN = "RiskYieldMMStep2FinalizationManifestV1V4_9F_RawV8"

CONSTRAINT_SCOPE_DOMAIN = (
    "RiskYieldMMA2MStep2ExternalSchemaV2MaximumConstraintScopeV2V4_9F_RawV8"
)
ROW_CONTEXT_DOMAIN = (
    "RiskYieldMMA2MStep2ExternalSchemaV2MaximumRowContextClosureV2V4_9F_RawV8"
)
CONTEXT_OBJECT_DOMAIN = (
    "RiskYieldMMA2MStep2ExternalSchemaV2MaximumContextObjectV2V4_9F_RawV8"
)
RECORD_REFERENCE_DOMAIN = (
    "RiskYieldMMA2MStep2ExternalSchemaV2MaximumRecordReferenceV2V4_9F_RawV8"
)
REGISTRY_DOMAIN = "RiskYieldMMA2MStep2ExternalSchemaRegistryV2V4_9F_RawV8"
EVALUATION_SEMANTICS = (
    "FULL_GRAPH_EXACT_IJSON_INTRINSIC_DEPENDENCY_POSTORDER_THEN_"
    "LEXICAL_APPLICATION_NAME_THEN_INVOCATION_ORDINAL_V1"
)

CASE5_POSITION = 5
CASE5_TYPE = "CapacityMeasurementBoolValueV1"
CASE24_POSITION = 24
CASE24_TYPE = "CapacityMeasurementOperationResultBody"
CASE24_ALTERNATIVE = "LOCAL_SHUTDOWN_RESULT_EVIDENCE_V2"
CASE24_BODY_TYPE = "CapacityMeasurementLocalShutdownResultEvidenceV2"
CASE24_OWNER_TYPE = "CapacityMeasurementOperationResultEvidence"
CASE24_INTRINSIC_RULE = (
    "RULE/INTRINSIC/CapacityMeasurementLocalShutdownResultEvidenceV2/V1"
)
CASE54_POSITION = 54
CASE54_TYPE = "CapacityMeasurementVocabularyDefinitionV1"
CASE54_INTRINSIC_RULE = (
    "RULE/INTRINSIC/CapacityMeasurementVocabularyDefinitionV1/V1"
)
CASE69_POSITION = 69
CASE69_TYPE = "CapacityMeasurementOperationResultEvidence"
CASE69_BODY_TYPE = "CapacityMeasurementLocalShutdownResultEvidenceV2"
CASE69_SPEC_TYPE = "CapacityMeasurementOperationSpec"
CASE69_SPEC_BODY_TYPE = "CapacityMeasurementLocalShutdownSpecV2"
CASE69_RESULT_INTRINSIC_RULE = CASE24_INTRINSIC_RULE
CASE69_SPEC_INTRINSIC_RULE = (
    "RULE/INTRINSIC/CapacityMeasurementLocalShutdownSpecV2/V1"
)
CASE69_APPLICATION_NAME = "APPLY/OPERATION_RESULT_SIGNED_SPEC_V1"
CASE69_APPLICATION_ID = (
    "770d99b0001802ceb6bdc044b9b55ce3cfd319754e9b9716c10d0b3d2e214f18"
)
CASE69_CROSS_RULE = "RULE/CROSS/OPERATION_RESULT_SIGNED_SPEC_V1"
CASE69_PROFILE_ID = (
    "92a80f3b2dc5d4b9a6284adfb6819823de7e2546d4141b2b12c5c7c9afff21f4"
)
CASE69_PROGRAM_ID = (
    "6912414e364c4117822c7ad0d24d1436d46f29e945ed076140785f5c0c9fc442"
)
CASE69_ANALYTIC_ID = (
    "759b3fbd70f3a36c0a6309ec35c4f5cd8efda7cf01d23bcd5e52e290ff29f0e0"
)
CASE69_SPEC_ID = (
    "f88cf223f28a146b08b5ffbb3b5ce419fb7ce473563edb27900983d6583a2d21"
)
CASE69_SPEC_POINTER = "/fixture_records/operation_specs/LOCAL_SHUTDOWN"
CASE69_EXACT_MAXIMUM = 2_581
CASE475_POSITION = 475
CASE475_TYPE = CASE69_TYPE
CASE475_SPEC_TYPE = CASE69_SPEC_TYPE
CASE475_SPEC_BODY_TYPE = CASE69_SPEC_BODY_TYPE
CASE475_RESULT_BODY_TYPE = CASE69_BODY_TYPE
CASE475_EXACT_MAXIMUM = 524_380
CASE475_PREDECESSOR_MAXIMUM = 524_112
CASE475_WINNING_MEMBER = "maximum_terminal_ingress_batches"
CASE475_WINNING_VALUE = 1_948
CASE475_WINNING_DELTA = 1_947
LOCAL_PROOF_SCOPE_DOMAIN = (
    "RiskYieldMMA2MStep2ExternalSchemaV2LocalShutdownProofScopeV2V4_9F_RawV8"
)
LOCAL_MINIMALITY_CERTIFICATE_VERSION = (
    "riskyieldmm.raw_v8_step2_external_schema_v2."
    "local_shutdown_minimality_certificate.v2"
)
LOCAL_MINIMALITY_CERTIFICATE_DOMAIN = (
    "RiskYieldMMA2MStep2ExternalSchemaV2LocalShutdownMinimalityCertificateV2"
    "V4_9F_RawV8"
)
LOCAL_EXCLUSION_RESULT_VERSION = (
    "riskyieldmm.raw_v8_step2_external_schema_v2."
    "local_shutdown_better_objective_exclusion_result.v1"
)
V2_SUCCESSOR_CASE_POSITIONS = (
    CASE5_POSITION,
    CASE24_POSITION,
    CASE54_POSITION,
    CASE69_POSITION,
)
V3_SUCCESSOR_CASE_POSITIONS = (*V2_SUCCESSOR_CASE_POSITIONS, CASE435_POSITION)
V4_SUCCESSOR_CASE_POSITIONS = (*V3_SUCCESSOR_CASE_POSITIONS, CASE475_POSITION)
CASE435_SELECTOR_MARKER_ORDER_BY_OPERATION = {
    "ACK_DEADLINE_EXPIRY": (
        "ACK_DEADLINE_NOT_DUE",
        "ACK_DEADLINE_TERMINAL_CONVERGED",
        "TARGET_ESCAPE_OBSERVED",
    ),
    "INGRESS": (
        "RAW_PREFIX_COMMITTED",
        "PARSER_UNIT_CONVERGED",
        "INGRESS_RETURN_READY",
        "TARGET_ESCAPE_OBSERVED",
    ),
    "LOCAL_SHUTDOWN": (
        "LOCAL_CLOSE_DISPATCH_CONVERGED",
        "TLS_CONTROL_CONVERGED",
        "TCP_HALF_CLOSE_CONVERGED",
        "SHUTDOWN_TERMINAL_CONVERGED",
        "TARGET_ESCAPE_OBSERVED",
    ),
    "SUBSCRIPTION_DISPATCH": (
        "OUTBOUND_ARTIFACTS_PREPARED",
        "KERNEL_SEND_RESULT_CONVERGED",
        "DISPATCH_RETURN_READY",
        "TARGET_ESCAPE_OBSERVED",
    ),
}
CASE435_PLACEHOLDER_FIELD_REASON_BY_CONTEXT_REASON = {
    "TARGET_BOUNDARY_NOT_REACHED": (
        "CHECKPOINT_PLACEHOLDER_TARGET_BOUNDARY_NOT_REACHED"
    ),
    "SOURCE_CLOCK_UNAVAILABLE": "CHECKPOINT_PLACEHOLDER_SOURCE_CLOCK_UNAVAILABLE",
    "ARTIFACT_BOUND_EXCEEDED": "CHECKPOINT_PLACEHOLDER_ARTIFACT_BOUND_EXCEEDED",
    "OBSERVER_INTERNAL_ERROR": "CHECKPOINT_PLACEHOLDER_OBSERVER_INTERNAL_ERROR",
}
CASE435_PLACEHOLDER_FIELD_REASONS = frozenset(
    CASE435_PLACEHOLDER_FIELD_REASON_BY_CONTEXT_REASON.values()
)
CASE435_OFF_STATIC_FIELD_IDS = frozenset(
    {
        "loop.probe_interval_ns",
        "process.filesystem_mount_cgroup_identity_id",
        "process.runtime_environment_id",
    }
)
CASE435_ATTEMPT_REQUIRED_FIELD_IDS = frozenset(
    """
actor.batch_append_maximum_elapsed_ns
actor.batch_append_total_elapsed_ns
actor.operation_appended_events
actor.operation_batch_append_calls
actor.operation_single_append_calls
actor.rebuild_maximum_elapsed_ns
actor.rebuild_total_elapsed_ns
actor.single_append_maximum_elapsed_ns
actor.single_append_total_elapsed_ns
actor.validation_maximum_elapsed_ns
actor.validation_total_elapsed_ns
freshness.close_to_response_terminal_last_ns
freshness.close_to_response_terminal_maximum_ns
freshness.close_units
freshness.ping_to_pong_terminal_last_ns
freshness.ping_to_pong_terminal_maximum_ns
freshness.ping_units
freshness.target_effect_elapsed_boottime_ns
ingress.operation_new_raw_count
ingress.operation_new_raw_octets
kernel.operation_last_send_errno
kernel.operation_recv_calls
kernel.operation_recv_ciphertext_octets
kernel.operation_send_accepted_octets
kernel.operation_send_attempts
kernel.operation_send_failures
kernel.operation_send_positive_results
loop.final_unfired_delay_lower_bound_ns
loop.probe_last_delay_ns
loop.probe_maximum_delay_ns
loop.probe_phases_missed
loop.probe_ring_overwritten
loop.probe_total_delay_ns
loop.probes_fired
loop.probes_scheduled
loop.slow_callback_events
parser.last_unit_elapsed_ns
parser.last_unit_thread_cpu_ns
parser.maximum_unit_elapsed_ns
parser.maximum_unit_thread_cpu_ns
parser.operation_application_completions
parser.operation_automatic_output_chunks
parser.operation_automatic_output_octets
parser.operation_complete_frames
parser.operation_error_units
parser.operation_fragment_units
parser.operation_payload_octets
parser.operation_source_octets
parser.operation_units
parser.total_unit_elapsed_ns
parser.total_unit_thread_cpu_ns
process.gc_collected_objects_by_generation
process.gc_collections_by_generation
process.gc_pause_count
process.gc_pause_maximum_elapsed_ns
process.gc_pause_total_elapsed_ns
process.gc_uncollectable_by_generation
process.operation_owner_thread_cpu_ns
process.operation_process_cpu_ns
sqlite.begin_maximum_elapsed_ns
sqlite.begin_total_elapsed_ns
sqlite.body_maximum_elapsed_ns
sqlite.body_total_elapsed_ns
sqlite.commit_maximum_elapsed_ns
sqlite.commit_total_elapsed_ns
sqlite.last_primary_result_class
sqlite.operation_canonical_record_octets
sqlite.operation_rollbacks_attempted
sqlite.operation_rows_written
sqlite.operation_transactions_attempted
sqlite.operation_transactions_begun
sqlite.operation_transactions_committed
sqlite.operation_transactions_rolled_back
sqlite.operation_transactions_uncertain
sqlite.result_class_counts
sqlite.rollback_maximum_elapsed_ns
sqlite.rollback_total_elapsed_ns
tls.operation_ciphertext_fed_octets
tls.operation_ciphertext_produced_octets
tls.operation_plaintext_accepted_octets
tls.operation_plaintext_produced_octets
tls.operation_read_calls
tls.operation_want_read_count
tls.operation_want_write_count
tls.operation_write_calls
""".split()
)
CASE435_SOURCE_ERROR_DETAIL_DOMAIN = "RiskYieldMMA2MSourceErrorDetailV4_9F_RawV8"
CASE435_SOURCE_ERROR_DETAIL_CANONICAL_OCTET_LIMIT = 2_048
MAY_BE_NONEMPTY = "MAY_BE_NONEMPTY"
U128_MAX = (1 << 128) - 1
SAFE_INTEGER_MAX = 9_007_199_254_740_991
DEFAULT_FILE_LIMIT = 16_777_216
DEFAULT_JSON_DEPTH_LIMIT = 96
DEFAULT_JSON_NODE_LIMIT = 2_097_152
DEFAULT_ARRAY_ENTRY_LIMIT = 1_048_576
DEFAULT_OBJECT_MEMBER_LIMIT = 1_048_576


class VerifierReject(Exception):
    """Stable fail-closed verifier rejection."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = str(message).replace("\n", " ").replace("\r", " ")[:768]


def _reject(code, message):
    raise VerifierReject(code, message)


def _require(condition, code, message):
    if not condition:
        _reject(code, message)


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _u128(value, label="value"):
    _require(
        _is_int(value) and 0 <= value <= U128_MAX,
        "CHECKED_ARITHMETIC_REJECT",
        f"{label} is not UInt128",
    )
    return value


def _checked_add(*values):
    total = 0
    for value in values:
        value = _u128(value, "addend")
        _require(
            value <= U128_MAX - total,
            "CHECKED_ARITHMETIC_REJECT",
            "UInt128 addition overflow",
        )
        total += value
    return total


def _checked_sub(left, right):
    left = _u128(left, "minuend")
    right = _u128(right, "subtrahend")
    _require(
        right <= left,
        "CHECKED_ARITHMETIC_REJECT",
        "UInt128 subtraction underflow",
    )
    return left - right


def _checked_mul(left, right):
    left = _u128(left, "multiplicand")
    right = _u128(right, "multiplier")
    _require(
        not left or right <= U128_MAX // left,
        "CHECKED_ARITHMETIC_REJECT",
        "UInt128 multiplication overflow",
    )
    return left * right


def _sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def _canonical_bytes(value):
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as error:
        _reject("CANONICALIZATION_INVALID", f"canonical JSON rejected: {error}")


def _pretty_bytes(value, sort_keys=True):
    try:
        return (
            json.dumps(
                value,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=sort_keys,
                indent=2,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as error:
        _reject("CANONICALIZATION_INVALID", f"pretty JSON rejected: {error}")


def _semantic_id(domain, payload):
    return _sha256(_canonical_bytes({"domain": domain, "payload": payload}))


def _seed_semantic_id(seed, domain, payload):
    return _sha256(
        _canonical_bytes(
            {
                "canonicalization_version": seed["canonicalization_version"],
                "domain": domain,
                "payload": payload,
                "schema_version": seed["measurement_schema_version"],
            }
        )
    )


def _duplicate_guard(pairs):
    value = {}
    for key, child in pairs:
        _require(
            key not in value,
            "CANONICALIZATION_INVALID",
            f"duplicate JSON key: {key}",
        )
        value[key] = child
    return value


def _reject_float(value):
    _reject("CANONICALIZATION_INVALID", f"floating JSON number is forbidden: {value}")


def _reject_constant(value):
    _reject("CANONICALIZATION_INVALID", f"non-finite JSON number is forbidden: {value}")


def _validate_json_shape(value, limits):
    stack = [(value, 1)]
    nodes = 0
    arrays = 0
    members = 0
    while stack:
        child, depth = stack.pop()
        nodes += 1
        _require(
            depth <= limits["JSON_NESTING_DEPTH"],
            "INPUT_LIMIT_EXCEEDED",
            "JSON nesting depth exceeded",
        )
        _require(
            nodes <= limits["DECODED_JSON_NODE_COUNT"],
            "INPUT_LIMIT_EXCEEDED",
            "decoded JSON node count exceeded",
        )
        if isinstance(child, dict):
            members += len(child)
            _require(
                members <= limits["DECODED_JSON_OBJECT_MEMBER_COUNT"],
                "INPUT_LIMIT_EXCEEDED",
                "decoded JSON object-member count exceeded",
            )
            for key, nested in child.items():
                _require(
                    isinstance(key, str),
                    "CANONICALIZATION_INVALID",
                    "JSON object key is not text",
                )
                stack.append((key, depth + 1))
                stack.append((nested, depth + 1))
        elif isinstance(child, list):
            arrays += len(child)
            _require(
                arrays <= limits["DECODED_JSON_ARRAY_ENTRY_COUNT"],
                "INPUT_LIMIT_EXCEEDED",
                "decoded JSON array-entry count exceeded",
            )
            stack.extend((nested, depth + 1) for nested in child)
        elif isinstance(child, str):
            _require(
                all(not 0xD800 <= ord(character) <= 0xDFFF for character in child),
                "CANONICALIZATION_INVALID",
                "lone surrogate is forbidden",
            )
        elif child is None or isinstance(child, bool):
            continue
        elif _is_int(child):
            _require(
                -SAFE_INTEGER_MAX <= child <= SAFE_INTEGER_MAX,
                "CANONICALIZATION_INVALID",
                "JSON integer exceeds the safe-integer domain",
            )
        else:
            _reject("CANONICALIZATION_INVALID", "unsupported decoded JSON value")


def _strict_loads(raw, limits=None):
    if limits is None:
        limits = {
            "JSON_NESTING_DEPTH": DEFAULT_JSON_DEPTH_LIMIT,
            "DECODED_JSON_NODE_COUNT": DEFAULT_JSON_NODE_LIMIT,
            "DECODED_JSON_ARRAY_ENTRY_COUNT": DEFAULT_ARRAY_ENTRY_LIMIT,
            "DECODED_JSON_OBJECT_MEMBER_COUNT": DEFAULT_OBJECT_MEMBER_LIMIT,
        }
    try:
        text = raw.decode("utf-8", errors="strict")
        _require(
            not text.startswith("\ufeff"),
            "CANONICALIZATION_INVALID",
            "UTF-8 BOM is forbidden",
        )
        value = json.loads(
            text,
            object_pairs_hook=_duplicate_guard,
            parse_float=_reject_float,
            parse_constant=_reject_constant,
        )
    except VerifierReject:
        raise
    except (UnicodeError, json.JSONDecodeError) as error:
        _reject("CANONICALIZATION_INVALID", f"strict JSON rejected: {error}")
    _validate_json_shape(value, limits)
    return value


def _closed(value, names, label):
    _require(isinstance(value, dict), "SCHEMA_INVALID", f"{label} is not an object")
    _require(
        set(value) == set(names),
        "SCHEMA_INVALID",
        f"{label} members differ",
    )
    return value


def _sha(value, label):
    _require(
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value),
        "SCHEMA_INVALID",
        f"{label} is not lowercase SHA-256",
    )
    return value


def _absolute_lexical_path(value, label, must_exist):
    path = pathlib.Path(value)
    _require(path.is_absolute(), "INVOCATION_INVALID", f"{label} must be absolute")
    _require(
        path == pathlib.Path(os.path.abspath(os.fspath(path))),
        "INVOCATION_INVALID",
        f"{label} must be lexically canonical",
    )
    probe = path if must_exist else path.parent
    _require(probe.exists(), "INVOCATION_INVALID", f"{label} anchor is absent")
    current = pathlib.Path(path.anchor)
    for component in probe.parts[1:]:
        _require(
            component not in {"", ".", ".."},
            "INVOCATION_INVALID",
            f"{label} has a forbidden component",
        )
        current = current / component
        info = os.lstat(current)
        _require(
            not stat.S_ISLNK(info.st_mode),
            "FILESYSTEM_INVALID",
            f"{label} traverses a symlink",
        )
    return path


def _signature(info):
    return (
        info.st_dev,
        info.st_ino,
        info.st_mode,
        info.st_nlink,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


def _directory_signature(path, label):
    info = os.lstat(path)
    _require(
        stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode),
        "FILESYSTEM_INVALID",
        f"{label} is not a direct directory",
    )
    return _signature(info)


def _read_regular(path, limit, label):
    before = os.lstat(path)
    _require(
        stat.S_ISREG(before.st_mode) and not stat.S_ISLNK(before.st_mode),
        "FILESYSTEM_INVALID",
        f"{label} is not a direct regular file",
    )
    _require(
        before.st_nlink == 1,
        "FILESYSTEM_INVALID",
        f"{label} is not single-link",
    )
    _require(
        0 <= before.st_size < limit,
        "INPUT_LIMIT_EXCEEDED",
        f"{label} exceeds the strict file limit",
    )
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    descriptor = os.open(path, flags)
    try:
        opened = os.fstat(descriptor)
        _require(
            _signature(opened) == _signature(before),
            "INPUT_RACE_DETECTED",
            f"{label} changed before read",
        )
        chunks = []
        remaining = before.st_size
        while remaining:
            chunk = os.read(descriptor, min(remaining, 1 << 20))
            _require(chunk, "INPUT_RACE_DETECTED", f"{label} ended early")
            chunks.append(chunk)
            remaining -= len(chunk)
        _require(
            os.read(descriptor, 1) == b"",
            "INPUT_RACE_DETECTED",
            f"{label} grew during read",
        )
        after = os.fstat(descriptor)
        _require(
            _signature(after) == _signature(before),
            "INPUT_RACE_DETECTED",
            f"{label} changed during read",
        )
    finally:
        os.close(descriptor)
    return b"".join(chunks), _signature(before)


def _safe_relative_path(root, relative, label):
    _require(
        isinstance(relative, str) and relative and not relative.startswith("/"),
        "AUTHORITY_INVALID",
        f"{label} relative path is invalid",
    )
    parts = pathlib.PurePosixPath(relative).parts
    _require(
        parts and all(part not in {"", ".", ".."} for part in parts),
        "AUTHORITY_INVALID",
        f"{label} relative path escapes",
    )
    path = root.joinpath(*parts)
    current = root
    for component in parts[:-1]:
        current = current / component
        _directory_signature(current, label)
    return path


def _f0_limits(seed):
    rows = seed["f0_seed_ceiling_catalog"]["ordered_platform_ceiling_records"]
    _require(
        isinstance(rows, list) and len(rows) == 12,
        "AUTHORITY_INVALID",
        "F0 catalog differs",
    )
    limits = {}
    for position, row in enumerate(rows, 1):
        _require(
            row.get("ceiling_position") == position,
            "AUTHORITY_INVALID",
            "F0 order differs",
        )
        limits[row["resource_name"]] = _u128(row["ceiling_value"], "F0 ceiling")
    return limits


def _authority_recheck(records):
    seen = set()
    total = 0
    for record in records:
        raw, signature = _read_regular(record["path"], record["limit"], record["label"])
        _require(
            signature == record["signature"],
            "INPUT_RACE_DETECTED",
            f"{record['label']} snapshot drifted",
        )
        _require(
            len(raw) == record["octets"],
            "INPUT_RACE_DETECTED",
            f"{record['label']} size drifted",
        )
        _require(
            _sha256(raw) == record["sha256"],
            "INPUT_RACE_DETECTED",
            f"{record['label']} hash drifted",
        )
        inode = signature[:2]
        _require(
            inode not in seen, "FILESYSTEM_INVALID", "authority inode alias detected"
        )
        seen.add(inode)
        total += len(raw)
    return total


def _load_predecessor_authorities(repository_root, boundary_path):
    expected_boundary = repository_root / BOUNDARY_RELATIVE_PATH
    _require(
        boundary_path == expected_boundary,
        "INVOCATION_INVALID",
        "boundary path differs",
    )
    boundary_raw, boundary_signature = _read_regular(
        boundary_path, DEFAULT_FILE_LIMIT, "constructive boundary"
    )
    _require(
        len(boundary_raw) == BOUNDARY_OCTETS,
        "AUTHORITY_INVALID",
        "boundary size differs",
    )
    _require(
        _sha256(boundary_raw) == BOUNDARY_SHA256,
        "AUTHORITY_INVALID",
        "boundary hash differs",
    )
    boundary = _strict_loads(boundary_raw)
    _require(
        boundary_raw == _pretty_bytes(boundary, sort_keys=False),
        "AUTHORITY_INVALID",
        "boundary encoding differs",
    )
    boundary_payload = {
        name: value
        for name, value in boundary.items()
        if name != "constructive_boundary_id"
    }
    _require(
        boundary.get("constructive_boundary_id")
        == _semantic_id(BOUNDARY_DOMAIN, boundary_payload)
        == BOUNDARY_ID,
        "AUTHORITY_INVALID",
        "boundary identity differs",
    )

    authority = boundary["authority_contract"]
    seed_record = authority["seed_authority"]
    seed_path = _safe_relative_path(
        repository_root, seed_record["repository_relative_path"], "seed"
    )
    seed_raw, seed_signature = _read_regular(seed_path, DEFAULT_FILE_LIMIT, "seed")
    _require(
        len(seed_raw) == seed_record["raw_octets"],
        "AUTHORITY_INVALID",
        "seed size differs",
    )
    _require(
        _sha256(seed_raw) == seed_record["raw_sha256"],
        "AUTHORITY_INVALID",
        "seed hash differs",
    )
    seed = _strict_loads(seed_raw)
    _require(
        seed.get("seed_catalog_id") == seed_record["seed_catalog_id"] == SEED_ID,
        "AUTHORITY_INVALID",
        "seed ID differs",
    )
    seed_identity = next(
        (
            row
            for row in seed["ordered_identity_domain_records"]
            if row["identity_name"] == "SEED_CATALOG"
        ),
        None,
    )
    _require(
        seed_identity is not None,
        "AUTHORITY_INVALID",
        "seed identity authority is absent",
    )
    seed_payload = {
        name: seed[name] for name in seed_identity["ordered_payload_member_names"]
    }
    _require(
        _seed_semantic_id(seed, seed_identity["domain_literal"], seed_payload)
        == SEED_ID,
        "AUTHORITY_INVALID",
        "seed identity does not reproduce",
    )
    limits = _f0_limits(seed)
    _validate_json_shape(seed, limits)
    file_limit = limits["INDIVIDUAL_FILE_STRICT_UPPER_OCTETS"]

    manifest_record = authority["finalization_manifest_authority"]
    manifest_path = _safe_relative_path(
        repository_root, manifest_record["repository_relative_path"], "manifest"
    )
    manifest_raw, manifest_signature = _read_regular(
        manifest_path, file_limit, "manifest"
    )
    _require(
        len(manifest_raw) == manifest_record["raw_octets"],
        "AUTHORITY_INVALID",
        "manifest size differs",
    )
    _require(
        _sha256(manifest_raw) == manifest_record["raw_sha256"] == MANIFEST_SHA256,
        "AUTHORITY_INVALID",
        "manifest hash differs",
    )
    manifest = _strict_loads(manifest_raw, limits)
    manifest_payload = {
        name: value
        for name, value in manifest.items()
        if name != "finalization_manifest_id"
    }
    _require(
        manifest.get("finalization_manifest_id")
        == _semantic_id(MANIFEST_DOMAIN, manifest_payload)
        == MANIFEST_ID,
        "AUTHORITY_INVALID",
        "manifest identity differs",
    )

    records = [
        {
            "path": boundary_path,
            "limit": file_limit,
            "label": "constructive boundary",
            "signature": boundary_signature,
            "octets": len(boundary_raw),
            "sha256": _sha256(boundary_raw),
        },
        {
            "path": seed_path,
            "limit": file_limit,
            "label": "seed",
            "signature": seed_signature,
            "octets": len(seed_raw),
            "sha256": _sha256(seed_raw),
        },
        {
            "path": manifest_path,
            "limit": file_limit,
            "label": "manifest",
            "signature": manifest_signature,
            "octets": len(manifest_raw),
            "sha256": _sha256(manifest_raw),
        },
    ]
    authority_bytes = {}
    seen_paths = {str(boundary_path), str(seed_path), str(manifest_path)}
    seen_inodes = {boundary_signature[:2], seed_signature[:2], manifest_signature[:2]}
    total = len(boundary_raw) + len(seed_raw) + len(manifest_raw)

    verifier_role = boundary["implementation_role_contract"]["ordered_role_records"][0]
    _require(
        verifier_role["role_name"] == "INDEPENDENT_VERIFIER",
        "AUTHORITY_INVALID",
        "verifier role binding differs",
    )
    verifier_path = _safe_relative_path(
        repository_root,
        verifier_role["repository_relative_path"],
        "verifier source",
    )
    _require(
        verifier_path == pathlib.Path(__file__),
        "AUTHORITY_INVALID",
        "executed verifier path differs from the frozen role path",
    )
    verifier_raw, verifier_signature = _read_regular(
        verifier_path, file_limit, "verifier source"
    )
    _require(
        verifier_role["source_marker"].encode("utf-8") in verifier_raw,
        "AUTHORITY_INVALID",
        "verifier source marker is absent",
    )
    _require(
        str(verifier_path) not in seen_paths
        and verifier_signature[:2] not in seen_inodes,
        "FILESYSTEM_INVALID",
        "verifier source aliases an authority",
    )
    seen_paths.add(str(verifier_path))
    seen_inodes.add(verifier_signature[:2])
    total += len(verifier_raw)
    records.append(
        {
            "path": verifier_path,
            "limit": file_limit,
            "label": "verifier source",
            "signature": verifier_signature,
            "octets": len(verifier_raw),
            "sha256": _sha256(verifier_raw),
        }
    )

    authority_rows = seed["ordered_authority_binding_records"]
    _require(
        len(authority_rows)
        == seed_record["ordered_authority_binding_record_count"]
        == 17,
        "AUTHORITY_INVALID",
        "authority count differs",
    )
    for position, row in enumerate(authority_rows, 1):
        _require(
            row["authority_position"] == position,
            "AUTHORITY_INVALID",
            "authority order differs",
        )
        path = _safe_relative_path(
            repository_root, row["repository_relative_path"], f"authority {position}"
        )
        _require(
            str(path) not in seen_paths,
            "AUTHORITY_INVALID",
            "authority path alias detected",
        )
        raw, signature = _read_regular(path, file_limit, f"authority {position}")
        _require(
            len(raw) == row["raw_octet_count"],
            "AUTHORITY_INVALID",
            f"authority {position} size differs",
        )
        _require(
            _sha256(raw) == row["raw_sha256"],
            "AUTHORITY_INVALID",
            f"authority {position} hash differs",
        )
        _require(
            signature[:2] not in seen_inodes,
            "FILESYSTEM_INVALID",
            "authority inode alias detected",
        )
        seen_paths.add(str(path))
        seen_inodes.add(signature[:2])
        total += len(raw)
        authority_bytes[row["authority_role"]] = raw
        records.append(
            {
                "path": path,
                "limit": file_limit,
                "label": f"authority {position}",
                "signature": signature,
                "octets": len(raw),
                "sha256": _sha256(raw),
            }
        )

    legacy = boundary["legacy_v1_exclusion_contract"]
    for member in (
        "rejected_protocol_authority",
        "rejected_bootstrap_authority",
        "accepted_rejection_authority",
    ):
        row = legacy[member]
        path = _safe_relative_path(
            repository_root, row["repository_relative_path"], member
        )
        _require(
            str(path) not in seen_paths,
            "AUTHORITY_INVALID",
            "legacy authority path alias detected",
        )
        raw, signature = _read_regular(path, file_limit, member)
        _require(
            signature[:2] not in seen_inodes,
            "FILESYSTEM_INVALID",
            "legacy authority inode alias detected",
        )
        _require(
            len(raw) == row["raw_octets"] and _sha256(raw) == row["raw_sha256"],
            "AUTHORITY_INVALID",
            f"{member} identity differs",
        )
        required_fragment = row.get(
            "required_status_fragment", row.get("required_module_fragment")
        )
        if required_fragment is not None:
            _require(
                required_fragment.encode("utf-8") in raw,
                "AUTHORITY_INVALID",
                f"{member} rejection marker is absent",
            )
        seen_paths.add(str(path))
        seen_inodes.add(signature[:2])
        total += len(raw)
        records.append(
            {
                "path": path,
                "limit": file_limit,
                "label": member,
                "signature": signature,
                "octets": len(raw),
                "sha256": _sha256(raw),
            }
        )

    _require(
        len(records) <= limits["INPUT_FILE_COUNT"],
        "INPUT_LIMIT_EXCEEDED",
        "input file count exceeded",
    )
    _require(
        total <= limits["TOTAL_PINNED_INPUT_OCTETS"],
        "INPUT_LIMIT_EXCEEDED",
        "total pinned input octets exceeded",
    )
    registry = _strict_loads(authority_bytes["STRUCTURAL_REGISTRY"], limits)
    return {
        "authority_mode": "PREDECESSOR_CONSTRUCTIVE_BOUNDARY_V1",
        "boundary": boundary,
        "seed": seed,
        "manifest": manifest,
        "registry": registry,
        "authority_bytes": authority_bytes,
        "authority_records": records,
        "limits": limits,
        "effective_seed_id": SEED_ID,
        "effective_manifest_id": MANIFEST_ID,
        "effective_protocol_sha256": MANIFEST_SHA256,
        "effective_f2_id": None,
    }


def _authority_descriptor(relative_path, raw, identity_name=None, identity=None):
    value = {
        "repository_relative_path": relative_path,
        "raw_octets": len(raw),
        "raw_sha256": _sha256(raw),
    }
    if identity_name is not None:
        value[identity_name] = identity
    return value


def _load_additional_authority(
    repository_root,
    authorities,
    relative_path,
    expected_octets,
    expected_sha256,
    label,
):
    path = _safe_relative_path(repository_root, relative_path, label)
    records = authorities["authority_records"]
    _require(
        all(record["path"] != path for record in records),
        "AUTHORITY_INVALID",
        f"{label} path aliases an earlier authority",
    )
    raw, signature = _read_regular(
        path,
        authorities["limits"]["INDIVIDUAL_FILE_STRICT_UPPER_OCTETS"],
        label,
    )
    _require(
        len(raw) == expected_octets and _sha256(raw) == expected_sha256,
        "AUTHORITY_INVALID",
        f"{label} identity differs",
    )
    _require(
        all(record["signature"][:2] != signature[:2] for record in records),
        "FILESYSTEM_INVALID",
        f"{label} inode aliases an earlier authority",
    )
    _require(
        len(records) + 1 <= authorities["limits"]["INPUT_FILE_COUNT"],
        "INPUT_LIMIT_EXCEEDED",
        "input file count exceeded while loading successor authorities",
    )
    _require(
        sum(record["octets"] for record in records) + len(raw)
        <= authorities["limits"]["TOTAL_PINNED_INPUT_OCTETS"],
        "INPUT_LIMIT_EXCEEDED",
        "total pinned input octets exceeded while loading successor authorities",
    )
    records.append(
        {
            "path": path,
            "limit": authorities["limits"]["INDIVIDUAL_FILE_STRICT_UPPER_OCTETS"],
            "label": label,
            "signature": signature,
            "octets": len(raw),
            "sha256": _sha256(raw),
        }
    )
    return path, raw


def _load_additional_json_authority(
    repository_root,
    authorities,
    relative_path,
    expected_octets,
    expected_sha256,
    label,
):
    path, raw = _load_additional_authority(
        repository_root,
        authorities,
        relative_path,
        expected_octets,
        expected_sha256,
        label,
    )
    value = _strict_loads(raw, authorities["limits"])
    _require(
        isinstance(value, dict) and raw == _pretty_bytes(value, sort_keys=False),
        "AUTHORITY_INVALID",
        f"{label} encoding differs",
    )
    return path, raw, value


def _payload_identity(value, identity_name, domain, expected_identity, label):
    payload = {name: child for name, child in value.items() if name != identity_name}
    _require(
        value.get(identity_name)
        == _semantic_id(domain, payload)
        == expected_identity,
        "AUTHORITY_INVALID",
        f"{label} semantic identity differs",
    )


def _one_by_position(rows, position, label):
    matches = [row for row in rows if row.get("case_position") == position]
    _require(
        len(matches) == 1,
        "AUTHORITY_INVALID",
        f"{label} resolution is missing or ambiguous",
    )
    return matches[0]


def _validate_successor_seed_delta(
    repository_root, authorities, seed_delta_raw, seed_delta
):
    _payload_identity(
        seed_delta,
        "successor_seed_catalog_id",
        SEED_DELTA_DOMAIN,
        SUCCESSOR_SEED_ID,
        "successor seed delta",
    )
    seed = authorities["seed"]
    predecessor_seed_raw = next(
        record
        for record in authorities["authority_records"]
        if record["label"] == "seed"
    )
    _require(
        seed_delta.get("predecessor_seed_authority")
        == {
            "raw_octets": predecessor_seed_raw["octets"],
            "raw_sha256": predecessor_seed_raw["sha256"],
            "repository_relative_path": SEED_RELATIVE_PATH,
            "seed_catalog_id": SEED_ID,
        },
        "AUTHORITY_INVALID",
        "successor seed predecessor binding differs",
    )
    theorem = seed_delta.get("exactness_theorem_authority")
    _require(
        isinstance(theorem, dict)
        and theorem.get("case_position") == CASE435_POSITION
        and theorem.get("profile_position") == 369
        and theorem.get("exactness_join_certificate_id")
        == CASE435_EXACTNESS_JOIN_ID
        and theorem.get("proved_legal_upper_bound_octets")
        == CASE435_EXACT_MAXIMUM_OCTETS
        and theorem.get("independently_measured_legal_attainer_octets")
        == CASE435_EXACT_MAXIMUM_OCTETS
        and theorem.get("exact_maximum_octets") == CASE435_EXACT_MAXIMUM_OCTETS
        and theorem.get("exact_cell_kind") == "EXACT_ATTAINED_MAXIMUM",
        "AUTHORITY_INVALID",
        "case435 exactness theorem binding differs",
    )
    source_rows = theorem.get("ordered_source_authority_records")
    _require(
        isinstance(source_rows, list) and len(source_rows) == 8,
        "AUTHORITY_INVALID",
        "case435 exactness source set differs",
    )
    for position, row in enumerate(source_rows, 1):
        _require(
            isinstance(row, dict)
            and row.get("source_position") == position
            and isinstance(row.get("source_role"), str)
            and isinstance(row.get("repository_relative_path"), str)
            and _is_int(row.get("raw_octets"))
            and isinstance(row.get("raw_sha256"), str),
            "AUTHORITY_INVALID",
            "case435 exactness source record differs",
        )
        _load_additional_authority(
            repository_root,
            authorities,
            row["repository_relative_path"],
            row["raw_octets"],
            row["raw_sha256"],
            f"case435 exactness source {position}",
        )

    resolution = seed_delta.get("resolution_contract")
    _require(
        isinstance(resolution, dict)
        and resolution.get("ordered_override_case_positions") == [CASE435_POSITION]
        and resolution.get("override_cardinality") == 1
        and resolution.get("base_fallback_case_count") == 474
        and resolution.get("shadowed_predecessor_case435_use_policy") == "REJECT"
        and resolution.get("structural_superset_as_exact_maximum_policy") == "REJECT"
        and resolution.get("unknown_duplicate_or_extra_override_policy") == "REJECT",
        "AUTHORITY_INVALID",
        "successor seed resolution contract differs",
    )

    program = seed_delta.get("successor_case435_profile_conditioning_program")
    plan = seed_delta.get("successor_case435_logical_count_plan")
    binding = seed_delta.get("successor_case435_case_plan_binding")
    _require(
        isinstance(program, dict) and isinstance(plan, dict) and isinstance(binding, dict),
        "AUTHORITY_INVALID",
        "case435 successor records are absent",
    )
    program_payload = {
        name: child
        for name, child in program.items()
        if name != "profile_conditioning_program_id"
    }
    plan_payload = {
        name: child for name, child in plan.items() if name != "logical_count_plan_id"
    }
    _require(
        program.get("profile_conditioning_program_id")
        == _semantic_id(SUCCESSOR_PROGRAM_DOMAIN, program_payload)
        == SUCCESSOR_CASE435_PROGRAM_ID
        and plan.get("logical_count_plan_id")
        == _semantic_id(SUCCESSOR_PLAN_DOMAIN, plan_payload)
        == SUCCESSOR_CASE435_PLAN_ID,
        "AUTHORITY_INVALID",
        "case435 successor program or plan identity differs",
    )
    _require(
        plan.get("case_position") == CASE435_POSITION
        and plan.get("profile_conditioning_program_id")
        == SUCCESSOR_CASE435_PROGRAM_ID
        and plan.get("upper_bound_mode") == "EXACT_LEGAL_DOMAIN"
        and plan.get("ordered_safe_relaxation_rule_ids") == []
        and binding
        == {
            "case_position": CASE435_POSITION,
            "logical_count_plan_id": SUCCESSOR_CASE435_PLAN_ID,
            "logical_count_plan_position": CASE435_POSITION,
        },
        "AUTHORITY_INVALID",
        "case435 successor plan binding differs",
    )
    p2 = program["conditioning_transfer_program"]["p2_upper_bound_program"]
    instructions = p2.get("ordered_instruction_records")
    _require(
        isinstance(instructions, list)
        and [row.get("opcode") for row in instructions]
        == [
            "IMPORT_ACCEPTED_CASE_EXACTNESS_JOIN_CELL_V1",
            "LOAD_STRUCTURAL_TEMPLATE_SUPERSET_CELL_V1",
            "REQUIRE_EXACT_CELL_WITHIN_STRUCTURAL_CEILING_V1",
        ]
        and instructions[0]["parameters"]["exact_maximum_octets"]
        == CASE435_EXACT_MAXIMUM_OCTETS
        and instructions[0]["parameters"]["exactness_join_certificate_id"]
        == CASE435_EXACTNESS_JOIN_ID
        and instructions[1]["parameters"]["predecessor_structural_upper_bound_octets"]
        == CASE435_PREDECESSOR_STRUCTURAL_UPPER_OCTETS
        and CASE435_EXACT_MAXIMUM_OCTETS
        <= CASE435_PREDECESSOR_STRUCTURAL_UPPER_OCTETS,
        "AUTHORITY_INVALID",
        "case435 exact-cell P2 program differs",
    )

    recipe = seed["logical_plan_recipe_catalog"]
    unaffected_programs = [
        row
        for row in recipe["ordered_profile_conditioning_program_records"]
        if row["case_position"] != CASE435_POSITION
    ]
    unaffected_plans = [
        row
        for row in recipe["ordered_logical_count_plan_records"]
        if row["case_position"] != CASE435_POSITION
    ]
    unaffected_bindings = [
        row
        for row in recipe["ordered_case_plan_bindings"]
        if row["case_position"] != CASE435_POSITION
    ]
    inherited = {
        name: child
        for name, child in recipe.items()
        if name
        not in {
            "logical_plan_recipe_catalog_id",
            "ordered_profile_conditioning_program_records",
            "ordered_logical_count_plan_records",
            "ordered_case_plan_bindings",
        }
    }
    no_drift = seed_delta.get("no_unrelated_drift_proof")
    _require(
        no_drift
        == {
            "authorized_override_json_pointers": [
                "/logical_plan_recipe_catalog/ordered_profile_conditioning_program_records/368",
                "/logical_plan_recipe_catalog/ordered_logical_count_plan_records/434",
                "/logical_plan_recipe_catalog/ordered_case_plan_bindings/434",
            ],
            "case_universe_record_count": 475,
            "case_universe_records_sha256": _sha256(
                _canonical_bytes(
                    seed["case_universe_catalog"]["ordered_case_bindings"]
                )
            ),
            "inherited_recipe_member_names": sorted(inherited),
            "inherited_recipe_members_sha256": _sha256(_canonical_bytes(inherited)),
            "unaffected_case_plan_binding_count": 474,
            "unaffected_case_plan_binding_records_sha256": _sha256(
                _canonical_bytes(unaffected_bindings)
            ),
            "unaffected_case_plan_count": 474,
            "unaffected_case_plan_records_sha256": _sha256(
                _canonical_bytes(unaffected_plans)
            ),
            "unaffected_profile_program_count": 407,
            "unaffected_profile_program_records_sha256": _sha256(
                _canonical_bytes(unaffected_programs)
            ),
        },
        "AUTHORITY_INVALID",
        "successor seed no-unrelated-drift proof differs",
    )
    return seed_delta_raw


def _validate_successor_manifest_delta(
    authorities, seed_delta_raw, manifest_delta_raw, manifest_delta
):
    _payload_identity(
        manifest_delta,
        "successor_manifest_id",
        MANIFEST_DELTA_DOMAIN,
        SUCCESSOR_MANIFEST_ID,
        "successor manifest delta",
    )
    manifest_record = next(
        record
        for record in authorities["authority_records"]
        if record["label"] == "manifest"
    )
    _require(
        manifest_delta.get("predecessor_finalization_manifest_authority")
        == {
            "finalization_manifest_id": MANIFEST_ID,
            "raw_octets": manifest_record["octets"],
            "raw_sha256": manifest_record["sha256"],
            "repository_relative_path": MANIFEST_RELATIVE_PATH,
        }
        and manifest_delta.get("successor_seed_delta_authority")
        == _authority_descriptor(
            SEED_DELTA_RELATIVE_PATH,
            seed_delta_raw,
            "successor_seed_catalog_id",
            SUCCESSOR_SEED_ID,
        )
        and manifest_delta.get("exactness_join_certificate_id")
        == CASE435_EXACTNESS_JOIN_ID
        and manifest_delta.get("case435_exact_maximum_octets")
        == CASE435_EXACT_MAXIMUM_OCTETS,
        "AUTHORITY_INVALID",
        "successor manifest authority binding differs",
    )
    f2 = manifest_delta.get("f2_limit_authority")
    f2_digest = _sha256(
        _canonical_bytes(authorities["manifest"]["ordered_f2_limit_records"])
    )
    _require(
        isinstance(f2, dict)
        and f2.get("limit_record_count") == 18
        and f2.get("ordered_f2_limit_records_sha256") == f2_digest
        and f2.get("limits_are_byte_exact_predecessor_ceilings") is True
        and f2.get("limits_may_not_be_raised_or_repaired_by_case435") is True
        and f2.get("case435_successor_resource_requalification")
        == "REQUIRED_DURING_A4_P6_V_BEFORE_CASE_ACCEPTANCE"
        and manifest_delta.get("manifest_status")
        == "CASE435_EXACT_DELTA_BOUND_VERIFIER_RESOURCE_REQUALIFICATION_REQUIRED",
        "AUTHORITY_INVALID",
        "successor manifest F2 contract differs",
    )
    return manifest_delta_raw


def _validate_successor_boundary_delta(
    authorities,
    boundary_delta_path,
    seed_delta_raw,
    manifest_delta_raw,
    boundary_delta_raw,
    boundary_delta,
):
    _require(
        boundary_delta_path
        == authorities["repository_root"] / SUCCESSOR_BOUNDARY_RELATIVE_PATH,
        "INVOCATION_INVALID",
        "successor boundary path differs",
    )
    _payload_identity(
        boundary_delta,
        "successor_constructive_boundary_id",
        SUCCESSOR_BOUNDARY_DOMAIN,
        SUCCESSOR_BOUNDARY_ID,
        "successor boundary delta",
    )
    boundary_record = next(
        record
        for record in authorities["authority_records"]
        if record["label"] == "constructive boundary"
    )
    _require(
        boundary_delta.get("predecessor_constructive_boundary_authority")
        == {
            "constructive_boundary_id": BOUNDARY_ID,
            "raw_octets": boundary_record["octets"],
            "raw_sha256": boundary_record["sha256"],
            "repository_relative_path": BOUNDARY_RELATIVE_PATH,
        }
        and boundary_delta.get("successor_seed_delta_authority")
        == _authority_descriptor(
            SEED_DELTA_RELATIVE_PATH,
            seed_delta_raw,
            "successor_seed_catalog_id",
            SUCCESSOR_SEED_ID,
        )
        and boundary_delta.get("successor_manifest_delta_authority")
        == _authority_descriptor(
            MANIFEST_DELTA_RELATIVE_PATH,
            manifest_delta_raw,
            "successor_manifest_id",
            SUCCESSOR_MANIFEST_ID,
        ),
        "AUTHORITY_INVALID",
        "successor boundary authority binding differs",
    )
    resolution = boundary_delta.get("effective_authority_resolution")
    expected_load_order = [
        "PREDECESSOR_BOUNDARY",
        "PREDECESSOR_SEED_AND_MANIFEST",
        "SUCCESSOR_SEED_DELTA",
        "SUCCESSOR_MANIFEST_DELTA",
    ]
    _require(
        isinstance(resolution, dict)
        and resolution.get("load_order") == expected_load_order
        and resolution.get("case435_resolution") == "SUCCESSOR_EXACT_RECORDS_ONLY"
        and resolution.get("all_other_case_resolution")
        == "BYTE_EXACT_PREDECESSOR_RECORDS_ONLY"
        and resolution.get("ambiguous_missing_duplicate_or_extra_resolution_policy")
        == "REJECT"
        and resolution.get("candidate_read_barrier")
        == "ALL_PREDECESSOR_AND_DELTA_AUTHORITIES_ACCEPTED_BEFORE_OPENING_CANDIDATE_BYTES",
        "AUTHORITY_INVALID",
        "successor authority resolution differs",
    )
    overrides = resolution.get("downstream_field_binding_overrides")
    _require(
        isinstance(overrides, dict)
        and overrides.get("seed_catalog_id") == "SUCCESSOR_SEED_CATALOG_ID"
        and overrides.get("finalization_manifest_id") == "SUCCESSOR_MANIFEST_ID"
        and overrides.get("maximum_protocol_sha256")
        == "SUCCESSOR_MANIFEST_DELTA_RAW_SHA256"
        and overrides.get("derivation_plan_id_for_case435")
        == "SUCCESSOR_CASE435_LOGICAL_COUNT_PLAN_ID"
        and overrides.get("upper_bound_mode_for_case435") == "EXACT_LEGAL_DOMAIN"
        and overrides.get("ordered_safe_relaxation_rule_ids_for_case435") == []
        and overrides.get("resource_limit_catalog_id")
        == "SUCCESSOR_F2_RESOURCE_LIMIT_CATALOG_ID",
        "AUTHORITY_INVALID",
        "successor downstream binding overrides differ",
    )
    f2 = boundary_delta.get("successor_f2_resource_limit_catalog")
    f2_payload = {
        name: child
        for name, child in f2.items()
        if name
        not in {
            "f2_resource_limit_catalog_id",
            "limit_records_source",
            "resource_requalification_rule",
        }
    }
    _require(
        isinstance(f2, dict)
        and f2.get("f2_resource_limit_catalog_id")
        == _semantic_id(SUCCESSOR_F2_DOMAIN, f2_payload)
        == SUCCESSOR_F2_ID
        and f2.get("successor_seed_catalog_id") == SUCCESSOR_SEED_ID
        and f2.get("successor_manifest_id") == SUCCESSOR_MANIFEST_ID
        and f2.get("predecessor_ordered_f2_limit_records_sha256")
        == _sha256(
            _canonical_bytes(authorities["manifest"]["ordered_f2_limit_records"])
        ),
        "AUTHORITY_INVALID",
        "successor F2 identity differs",
    )
    predecessor_pilot = _one_by_position(
        authorities["boundary"]["pilot_contract"]["ordered_pilot_case_records"],
        CASE435_POSITION,
        "predecessor case435 pilot",
    )
    expected_pilot = dict(predecessor_pilot)
    expected_pilot["logical_count_plan_id"] = SUCCESSOR_CASE435_PLAN_ID
    expected_pilot["coverage_tag"] = (
        "MAX64_ROOT_FULL67_CONTEXT_137_APPLICATIONS_EXACT_257887"
    )
    _require(
        boundary_delta.get("case435_pilot_record_override") == expected_pilot,
        "AUTHORITY_INVALID",
        "successor case435 pilot override differs",
    )
    inherited = {
        name: child
        for name, child in authorities["boundary"].items()
        if name
        not in {
            "constructive_boundary_id",
            "authority_contract",
            "pilot_contract",
            "resource_enforcement_contract",
        }
    }
    preserved = boundary_delta.get("preserved_boundary_contract")
    _require(
        isinstance(preserved, dict)
        and preserved.get("inherited_member_names") == sorted(inherited)
        and preserved.get("inherited_members_sha256")
        == _sha256(_canonical_bytes(inherited))
        and preserved.get("candidate_and_result_schemas_unchanged") is True
        and preserved.get("filesystem_and_independence_contracts_unchanged") is True
        and preserved.get("implementation_role_records_unchanged") is True
        and boundary_delta.get("verifier_expansion_state")
        == "RELEASED_FOR_A4_P6_V_IMPLEMENTATION"
        and boundary_delta.get("producer_expansion_state")
        == "HOLD_UNTIL_A4_P6_V_ACCEPTED",
        "AUTHORITY_INVALID",
        "successor preserved-boundary contract differs",
    )
    return boundary_delta_raw


def _validate_successor_target_delta(
    authorities,
    target_source_raw,
    seed_delta_raw,
    manifest_delta_raw,
    boundary_delta_raw,
    target_delta,
):
    _payload_identity(
        target_delta,
        "successor_six_case_target_id",
        TARGET_DELTA_DOMAIN,
        SUCCESSOR_TARGET_ID,
        "successor six-case target delta",
    )
    _require(
        target_delta.get("predecessor_six_case_target_authority")
        == _authority_descriptor(PREDECESSOR_TARGET_RELATIVE_PATH, target_source_raw)
        and target_delta.get("successor_seed_delta_authority")
        == _authority_descriptor(
            SEED_DELTA_RELATIVE_PATH,
            seed_delta_raw,
            "successor_seed_catalog_id",
            SUCCESSOR_SEED_ID,
        )
        and target_delta.get("successor_manifest_delta_authority")
        == _authority_descriptor(
            MANIFEST_DELTA_RELATIVE_PATH,
            manifest_delta_raw,
            "successor_manifest_id",
            SUCCESSOR_MANIFEST_ID,
        )
        and target_delta.get("successor_boundary_delta_authority")
        == _authority_descriptor(
            SUCCESSOR_BOUNDARY_RELATIVE_PATH,
            boundary_delta_raw,
            "successor_constructive_boundary_id",
            SUCCESSOR_BOUNDARY_ID,
        ),
        "AUTHORITY_INVALID",
        "successor target authority binding differs",
    )
    expected_pilots = [
        dict(row)
        for row in authorities["boundary"]["pilot_contract"][
            "ordered_pilot_case_records"
        ]
    ]
    expected_case435 = _one_by_position(
        expected_pilots, CASE435_POSITION, "successor target case435 pilot"
    )
    expected_case435["logical_count_plan_id"] = SUCCESSOR_CASE435_PLAN_ID
    expected_case435["coverage_tag"] = (
        "MAX64_ROOT_FULL67_CONTEXT_137_APPLICATIONS_EXACT_257887"
    )
    _require(
        target_delta.get("ordered_pilot_case_records") == expected_pilots
        and tuple(
            row["case_position"]
            for row in target_delta["ordered_pilot_case_records"]
        )
        == SUCCESSOR_PILOT_CASE_POSITIONS,
        "AUTHORITY_INVALID",
        "successor target pilot set differs",
    )
    expectation = target_delta.get("case435_exact_expectation")
    qualification = target_delta.get("qualification_contract")
    _require(
        isinstance(expectation, dict)
        and expectation.get("case_position") == CASE435_POSITION
        and expectation.get("successor_profile_conditioning_program_id")
        == SUCCESSOR_CASE435_PROGRAM_ID
        and expectation.get("successor_logical_count_plan_id")
        == SUCCESSOR_CASE435_PLAN_ID
        and expectation.get("upper_bound_mode") == "EXACT_LEGAL_DOMAIN"
        and expectation.get("ordered_safe_relaxation_rule_ids") == []
        and expectation.get("exactness_join_certificate_id")
        == CASE435_EXACTNESS_JOIN_ID
        and expectation.get("certified_upper_bound_octets")
        == expectation.get("required_legal_attainer_octets")
        == CASE435_EXACT_MAXIMUM_OCTETS
        and isinstance(qualification, dict)
        and qualification.get("verifier_expansion_state") == "NEXT"
        and qualification.get("producer_expansion_state") == "WAITING"
        and qualification.get("runner_state") == "WAITING"
        and qualification.get("next_subgate") == "A4-P6-V"
        and qualification.get("no_case_result_or_profitability_claimed") is True,
        "AUTHORITY_INVALID",
        "successor target acceptance contract differs",
    )


def _load_successor_authorities(repository_root, boundary_delta_path, authorities):
    authorities["repository_root"] = repository_root
    _, seed_delta_raw, seed_delta = _load_additional_json_authority(
        repository_root,
        authorities,
        SEED_DELTA_RELATIVE_PATH,
        SEED_DELTA_OCTETS,
        SEED_DELTA_SHA256,
        "successor seed delta",
    )
    _validate_successor_seed_delta(
        repository_root, authorities, seed_delta_raw, seed_delta
    )

    _, manifest_delta_raw, manifest_delta = _load_additional_json_authority(
        repository_root,
        authorities,
        MANIFEST_DELTA_RELATIVE_PATH,
        MANIFEST_DELTA_OCTETS,
        MANIFEST_DELTA_SHA256,
        "successor manifest delta",
    )
    _validate_successor_manifest_delta(
        authorities, seed_delta_raw, manifest_delta_raw, manifest_delta
    )

    loaded_boundary_path, boundary_delta_raw, boundary_delta = (
        _load_additional_json_authority(
            repository_root,
            authorities,
            SUCCESSOR_BOUNDARY_RELATIVE_PATH,
            SUCCESSOR_BOUNDARY_OCTETS,
            SUCCESSOR_BOUNDARY_SHA256,
            "successor boundary delta",
        )
    )
    _require(
        loaded_boundary_path == boundary_delta_path,
        "INVOCATION_INVALID",
        "successor boundary invocation does not select the loaded authority",
    )
    _validate_successor_boundary_delta(
        authorities,
        boundary_delta_path,
        seed_delta_raw,
        manifest_delta_raw,
        boundary_delta_raw,
        boundary_delta,
    )

    _, target_source_raw = _load_additional_authority(
        repository_root,
        authorities,
        PREDECESSOR_TARGET_RELATIVE_PATH,
        PREDECESSOR_TARGET_OCTETS,
        PREDECESSOR_TARGET_SHA256,
        "predecessor six-case target source",
    )
    _, target_delta_raw, target_delta = _load_additional_json_authority(
        repository_root,
        authorities,
        TARGET_DELTA_RELATIVE_PATH,
        TARGET_DELTA_OCTETS,
        TARGET_DELTA_SHA256,
        "successor six-case target delta",
    )
    _validate_successor_target_delta(
        authorities,
        target_source_raw,
        seed_delta_raw,
        manifest_delta_raw,
        boundary_delta_raw,
        target_delta,
    )
    typed_runtime_path, typed_runtime_raw = _load_additional_authority(
        repository_root,
        authorities,
        TYPED_RULE_RUNTIME_RELATIVE_PATH,
        TYPED_RULE_RUNTIME_OCTETS,
        TYPED_RULE_RUNTIME_SHA256,
        "accepted typed rule runtime",
    )

    authorities.update(
        {
            "authority_mode": "SUCCESSOR_CASE435_EXACT_DELTA_V1",
            "seed_delta": seed_delta,
            "manifest_delta": manifest_delta,
            "successor_boundary": boundary_delta,
            "target_delta": target_delta,
            "effective_seed_id": SUCCESSOR_SEED_ID,
            "effective_manifest_id": SUCCESSOR_MANIFEST_ID,
            "effective_protocol_sha256": MANIFEST_DELTA_SHA256,
            "effective_f2_id": SUCCESSOR_F2_ID,
            "effective_case435_program_id": SUCCESSOR_CASE435_PROGRAM_ID,
            "effective_case435_plan_id": SUCCESSOR_CASE435_PLAN_ID,
            "typed_rule_runtime_path": typed_runtime_path,
            "typed_rule_runtime_raw": typed_runtime_raw,
        }
    )
    return authorities


def _load_packed_context_authority(
    repository_root, packed_boundary_path, authorities
):
    loaded_path, raw, correction = _load_additional_json_authority(
        repository_root,
        authorities,
        PACKED_CONTEXT_BOUNDARY_RELATIVE_PATH,
        PACKED_CONTEXT_BOUNDARY_OCTETS,
        PACKED_CONTEXT_BOUNDARY_SHA256,
        "case435 packed-context boundary delta",
    )
    _require(
        loaded_path == packed_boundary_path,
        "INVOCATION_INVALID",
        "packed-context boundary invocation does not select the loaded authority",
    )
    _payload_identity(
        correction,
        "case435_context_pack_boundary_delta_id",
        PACKED_CONTEXT_BOUNDARY_DOMAIN,
        PACKED_CONTEXT_BOUNDARY_ID,
        "case435 packed-context boundary delta",
    )
    _closed(
        correction,
        [
            "correction_version",
            "case_position",
            "predecessor_successor_boundary_authority",
            "f0_contradiction_proof",
            "packed_context_candidate_contract",
            "context_pack_contract",
            "filesystem_and_publication_contract",
            "unchanged_effective_authorities",
            "scope_and_non_drift_contract",
            "case435_context_pack_boundary_delta_id",
        ],
        "case435 packed-context boundary delta",
    )
    predecessor = correction["predecessor_successor_boundary_authority"]
    _require(
        correction["correction_version"]
        == (
            "riskyieldmm.raw_v8_step2_external_schema_v2."
            "case435_context_pack_boundary_delta.v1"
        )
        and correction["case_position"] == CASE435_POSITION
        and predecessor
        == {
            "repository_relative_path": SUCCESSOR_BOUNDARY_RELATIVE_PATH,
            "raw_octets": SUCCESSOR_BOUNDARY_OCTETS,
            "raw_sha256": SUCCESSOR_BOUNDARY_SHA256,
            "successor_constructive_boundary_id": SUCCESSOR_BOUNDARY_ID,
        },
        "AUTHORITY_INVALID",
        "packed-context predecessor binding differs",
    )
    contradiction = correction["f0_contradiction_proof"]
    _require(
        contradiction
        == {
            "successor_authority_file_count_before_this_delta": 38,
            "candidate_envelope_file_count": 1,
            "root_context_object_count": 1,
            "observation_count": CASE435_OBSERVATION_COUNT,
            "inline_witness_count": 1,
            "non_inline_observation_context_object_count": 66,
            "logical_context_object_count": 67,
            "measured_sequence_ordinal": CASE435_MEASURED_SEQUENCE_ORDINAL,
            "minimum_flat_input_file_count": 106,
            "input_file_count_ceiling": 64,
            "flat_transport_acceptance_state": (
                "IMPOSSIBLE_UNDER_IMMUTABLE_F0"
            ),
        },
        "AUTHORITY_INVALID",
        "packed-context F0 contradiction proof differs",
    )
    candidate_contract = correction["packed_context_candidate_contract"]
    _require(
        candidate_contract
        == {
            "candidate_version_literal": CASE435_PACKED_CANDIDATE_VERSION,
            "candidate_identity_domain": CASE435_PACKED_CANDIDATE_DOMAIN,
            "candidate_kind": "MAXIMUM_WITNESS_PACKED_CONTEXT",
            "ordered_payload_member_names": [
                "candidate_kind",
                "witness_record",
                "scope_witness_context",
                "ordered_context_pack_entries",
            ],
            "required_case_position": CASE435_POSITION,
            "required_context_kind": "ROOT_APPLICATION",
            "required_measured_sequence_ordinal": (
                CASE435_MEASURED_SEQUENCE_ORDINAL
            ),
            "required_observation_reference_count": CASE435_OBSERVATION_COUNT,
            "required_inline_witness_reference_count": 1,
            "required_logical_context_object_count": 67,
            "unknown_or_extra_member_policy": "REJECT",
        },
        "AUTHORITY_INVALID",
        "packed-context candidate contract differs",
    )
    pack_contract = correction["context_pack_contract"]
    _require(
        pack_contract["context_pack_version"] == CASE435_CONTEXT_PACK_VERSION
        and pack_contract["context_pack_identity_domain"]
        == CASE435_CONTEXT_PACK_DOMAIN
        and pack_contract["required_pack_count_for_case435"] == 1
        and pack_contract["required_context_object_count_for_case435"] == 67
        and pack_contract["individual_pack_strict_upper_octets"]
        == authorities["limits"]["INDIVIDUAL_FILE_STRICT_UPPER_OCTETS"]
        and pack_contract["physical_encoding"]
        == "EXACT_COMPACT_CANONICAL_UTF8_JSON_NO_TRAILING_BYTE"
        and pack_contract["context_object_ordering_rule"]
        == "STRICTLY_INCREASING_MAXIMUM_CONTEXT_OBJECT_ID"
        and pack_contract["inline_witness_exclusion_rule"]
        == "INLINE_WITNESS_RECORD_IS_NOT_DUPLICATED_IN_CONTEXT_PACK"
        and pack_contract["logical_closure_rule"]
        == (
            "EVERY_AND_ONLY_CONTEXT_OBJECT_REFERENCE_REACHABLE_FROM_"
            "SCOPE_WITNESS_CONTEXT_RESOLVES_ONCE"
        )
        and pack_contract["repository_relative_path_rule"]
        == (
            "context_objects/packs/<first-two-pack-id-characters>/"
            "<context-pack-id>.json"
        )
        and pack_contract["ordered_candidate_pack_entry_member_names"]
        == [
            "context_pack_position",
            "context_pack_id",
            "first_maximum_context_object_id",
            "last_maximum_context_object_id",
            "context_object_count",
            "repository_relative_path",
            "raw_octet_count",
            "raw_sha256",
        ]
        and pack_contract["ordered_pack_member_names"]
        == [
            "context_pack_version",
            "canonicalization_version",
            "measurement_schema_version",
            "maximum_protocol_sha256",
            "case_position",
            "pack_position",
            "ordered_context_object_records",
            "context_pack_id",
        ]
        and pack_contract["ordered_context_object_record_member_names"]
        == [
            "context_object_position",
            "maximum_context_object_id",
            "record_type_name",
            "record_identity_field",
            "record_identity",
            "record_canonical_byte_length",
            "record_canonical_sha256",
            "record",
        ],
        "AUTHORITY_INVALID",
        "case435 context-pack schema differs",
    )
    unchanged = correction["unchanged_effective_authorities"]
    _require(
        unchanged
        == {
            "successor_seed_catalog_id": SUCCESSOR_SEED_ID,
            "successor_manifest_id": SUCCESSOR_MANIFEST_ID,
            "maximum_protocol_sha256": MANIFEST_DELTA_SHA256,
            "f2_resource_limit_catalog_id": SUCCESSOR_F2_ID,
            "case435_profile_conditioning_program_id": (
                SUCCESSOR_CASE435_PROGRAM_ID
            ),
            "case435_logical_count_plan_id": SUCCESSOR_CASE435_PLAN_ID,
            "case435_exactness_join_certificate_id": CASE435_EXACTNESS_JOIN_ID,
            "case435_exact_maximum_octets": CASE435_EXACT_MAXIMUM_OCTETS,
        },
        "AUTHORITY_INVALID",
        "packed-context mathematical authority drifted",
    )
    filesystem = correction["filesystem_and_publication_contract"]
    nondrift = correction["scope_and_non_drift_contract"]
    _require(
        filesystem["corrected_minimum_input_file_count"] == 41
        and filesystem["input_file_count_headroom"] == 23
        and filesystem["input_pack_count"] == 1
        and filesystem["total_pinned_input_octet_ceiling"]
        == authorities["limits"]["TOTAL_PINNED_INPUT_OCTETS"]
        and filesystem["context_object_semantic_id_domain_unchanged"] is True
        and filesystem["record_reference_semantic_id_domain_unchanged"] is True
        and filesystem["verified_output_rule"]
        == (
            "UNPACK_TO_INHERITED_COMPACT_CONTEXT_OBJECT_FILES_AND_"
            "INHERITED_LOGICAL_RECEIPT_ENTRIES"
        )
        and nondrift["authorized_change"]
        == "CASE435_CANDIDATE_CONTEXT_PHYSICAL_TRANSPORT_ONLY"
        and nondrift["old_flat_case435_transport_acceptance_policy"] == "REJECT"
        and nondrift["candidate_transport_for_cases_5_24_54_69_unchanged"]
        is True
        and nondrift["case475_transport_unchanged_and_unsupported_during_v3"]
        is True
        and nondrift["f0_or_f2_limit_increase_forbidden"] is True
        and nondrift["seed_manifest_plan_program_exactness_and_f2_values_unchanged"]
        is True
        and nondrift["c2_certificate_or_stored_witness_as_verifier_input_forbidden"]
        is True
        and nondrift["next_subgate"] == "A4-P6-V3",
        "AUTHORITY_INVALID",
        "packed-context non-drift contract differs",
    )
    authorities.update(
        {
            "authority_mode": "SUCCESSOR_CASE435_PACKED_CONTEXT_BOUNDARY_V1",
            "packed_context_boundary": correction,
            "packed_context_boundary_raw": raw,
        }
    )
    return authorities


def _load_authorities(repository_root, boundary_path):
    predecessor_path = repository_root / BOUNDARY_RELATIVE_PATH
    successor_path = repository_root / SUCCESSOR_BOUNDARY_RELATIVE_PATH
    packed_path = repository_root / PACKED_CONTEXT_BOUNDARY_RELATIVE_PATH
    if boundary_path == predecessor_path:
        authorities = _load_predecessor_authorities(
            repository_root, predecessor_path
        )
        authorities["repository_root"] = repository_root
        return authorities
    _require(
        boundary_path in {successor_path, packed_path},
        "INVOCATION_INVALID",
        "boundary path does not select a frozen predecessor, successor, or packed-context authority",
    )
    authorities = _load_predecessor_authorities(repository_root, predecessor_path)
    authorities = _load_successor_authorities(
        repository_root, successor_path, authorities
    )
    if boundary_path == successor_path:
        return authorities
    return _load_packed_context_authority(repository_root, packed_path, authorities)


def _contains_forbidden_member(value, forbidden):
    if isinstance(value, dict):
        return any(
            name in forbidden or _contains_forbidden_member(child, forbidden)
            for name, child in value.items()
        )
    if isinstance(value, list):
        return any(_contains_forbidden_member(child, forbidden) for child in value)
    return False


def _candidate_snapshot(candidate_root, authorities):
    root_signature = _directory_signature(candidate_root, "candidate root")
    names = sorted(entry.name for entry in os.scandir(candidate_root))
    expected = sorted(
        authorities["boundary"]["candidate_bundle_contract"]["bundle_root_member_paths"]
    )
    _require(names == expected, "FILESYSTEM_INVALID", "candidate root members differ")
    context_root = candidate_root / "context_objects"
    context_signature = _directory_signature(context_root, "candidate context root")
    candidate_path = candidate_root / "candidate.json"
    raw, file_signature = _read_regular(
        candidate_path,
        authorities["limits"]["INDIVIDUAL_FILE_STRICT_UPPER_OCTETS"],
        "candidate envelope",
    )
    authority_inodes = {
        record["signature"][:2] for record in authorities["authority_records"]
    }
    _require(
        file_signature[:2] not in authority_inodes,
        "FILESYSTEM_INVALID",
        "candidate envelope aliases an authority inode",
    )
    seen_file_inodes = {file_signature[:2]}
    directory_records = []
    file_records = []
    pending = [context_root]
    while pending:
        directory = pending.pop()
        entries = sorted(os.scandir(directory), key=lambda entry: entry.name)
        for entry in entries:
            path = directory / entry.name
            info = os.lstat(path)
            _require(
                not stat.S_ISLNK(info.st_mode),
                "FILESYSTEM_INVALID",
                "candidate context closure contains a symlink",
            )
            relative = path.relative_to(candidate_root).as_posix()
            if stat.S_ISDIR(info.st_mode):
                signature = _signature(info)
                directory_records.append((relative, signature))
                pending.append(path)
                continue
            _require(
                stat.S_ISREG(info.st_mode),
                "FILESYSTEM_INVALID",
                "candidate context closure contains a non-regular object",
            )
            context_raw, signature = _read_regular(
                path,
                authorities["limits"]["INDIVIDUAL_FILE_STRICT_UPPER_OCTETS"],
                f"candidate context object {relative}",
            )
            inode = signature[:2]
            _require(
                inode not in authority_inodes and inode not in seen_file_inodes,
                "FILESYSTEM_INVALID",
                "candidate context file inode aliases another input",
            )
            seen_file_inodes.add(inode)
            file_records.append(
                {
                    "relative_path": relative,
                    "signature": signature,
                    "raw": context_raw,
                    "raw_sha256": _sha256(context_raw),
                }
            )
    directory_records.sort(key=lambda row: row[0])
    file_records.sort(key=lambda row: row["relative_path"])
    input_file_count = len(authorities["authority_records"]) + 1 + len(file_records)
    total_octets = (
        sum(record["octets"] for record in authorities["authority_records"])
        + len(raw)
        + sum(len(record["raw"]) for record in file_records)
    )
    _require(
        input_file_count <= authorities["limits"]["INPUT_FILE_COUNT"],
        "INPUT_LIMIT_EXCEEDED",
        "candidate context closure exceeds the F0 input-file ceiling",
    )
    _require(
        total_octets <= authorities["limits"]["TOTAL_PINNED_INPUT_OCTETS"],
        "INPUT_LIMIT_EXCEEDED",
        "candidate context closure exceeds the F0 input-octet ceiling",
    )
    return {
        "root_signature": root_signature,
        "context_signature": context_signature,
        "file_signature": file_signature,
        "raw": raw,
        "context_directories": tuple(directory_records),
        "context_files": tuple(file_records),
        "input_file_count": input_file_count,
        "total_input_octets": total_octets,
    }


def _candidate_recheck(candidate_root, snapshot, authorities):
    current = _candidate_snapshot(candidate_root, authorities)
    _require(
        current == snapshot,
        "INPUT_RACE_DETECTED",
        "candidate bundle changed during verification",
    )


def _resolve_case_and_plan(authorities, case_position):
    seed = authorities["seed"]
    case_rows = seed["case_universe_catalog"]["ordered_case_bindings"]
    _require(
        _is_int(case_position) and 1 <= case_position <= len(case_rows),
        "SCHEMA_INVALID",
        "candidate case position is outside the frozen universe",
    )
    case = case_rows[case_position - 1]
    _require(
        case["case_position"] == case_position,
        "AUTHORITY_INVALID",
        "case-universe order differs",
    )
    if (
        authorities["authority_mode"]
        in {
            "SUCCESSOR_CASE435_EXACT_DELTA_V1",
            "SUCCESSOR_CASE435_PACKED_CONTEXT_BOUNDARY_V1",
        }
        and case_position == CASE435_POSITION
    ):
        plan = authorities["seed_delta"]["successor_case435_logical_count_plan"]
        binding = authorities["seed_delta"][
            "successor_case435_case_plan_binding"
        ]
    else:
        plan = seed["logical_plan_recipe_catalog"][
            "ordered_logical_count_plan_records"
        ][case_position - 1]
        binding = seed["logical_plan_recipe_catalog"]["ordered_case_plan_bindings"][
            case_position - 1
        ]
    _require(
        plan["case_position"] == binding["case_position"] == case_position
        and binding["logical_count_plan_id"] == plan["logical_count_plan_id"],
        "AUTHORITY_INVALID",
        "effective case-plan resolution differs",
    )
    return case, plan


def _validate_record_reference(
    reference, seed, expected_kind, source_inventory=None
):
    common = [
        "reference_kind",
        "record_type_name",
        "record_identity_field",
        "record_identity",
        "record_canonical_byte_length",
        "record_canonical_sha256",
        "maximum_record_reference_id",
    ]
    names_by_kind = {
        "WITNESS_RECORD": common,
        "CONTEXT_OBJECT": [
            "reference_kind",
            "maximum_context_object_id",
            *common[1:],
        ],
        "V3_INVENTORY_POINTER": [
            "reference_kind",
            "source_inventory_sha256",
            "inventory_json_pointer",
            *common[1:],
        ],
    }
    _require(
        expected_kind in names_by_kind,
        "AUTHORITY_INVALID",
        "record-reference kind authority differs",
    )
    names = names_by_kind[expected_kind]
    _closed(reference, names, "maximum record reference")
    _require(
        reference["reference_kind"] == expected_kind,
        "SCHEMA_INVALID",
        "maximum record-reference kind differs",
    )
    _require(
        isinstance(reference["record_type_name"], str)
        and reference["record_type_name"]
        and isinstance(reference["record_identity_field"], str)
        and reference["record_identity_field"],
        "SCHEMA_INVALID",
        "maximum record-reference type/identity field differs",
    )
    _sha(reference["record_identity"], "maximum record-reference identity")
    _u128(
        reference["record_canonical_byte_length"],
        "maximum record-reference canonical length",
    )
    _require(
        reference["record_canonical_byte_length"] > 0,
        "SCHEMA_INVALID",
        "maximum record-reference canonical length is empty",
    )
    _sha(reference["record_canonical_sha256"], "maximum record-reference hash")
    if expected_kind == "CONTEXT_OBJECT":
        _sha(reference["maximum_context_object_id"], "context-object reference ID")
    elif expected_kind == "V3_INVENTORY_POINTER":
        _require(
            source_inventory is not None
            and reference["source_inventory_sha256"] == source_inventory
            and isinstance(reference["inventory_json_pointer"], str)
            and reference["inventory_json_pointer"].startswith("/"),
            "SCHEMA_INVALID",
            "inventory record-reference authority differs",
        )
    payload = {name: reference[name] for name in names[:-1]}
    _require(
        reference["maximum_record_reference_id"]
        == _seed_semantic_id(seed, RECORD_REFERENCE_DOMAIN, payload),
        "IDENTITY_INVALID",
        "context record-reference identity differs",
    )
    return reference


def _json_pointer(root, pointer, label):
    _require(
        isinstance(pointer, str) and pointer.startswith("/"),
        "SCHEMA_INVALID",
        f"{label} JSON pointer differs",
    )
    value = root
    for token in pointer[1:].split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        if isinstance(value, list):
            _require(
                token.isdigit() and str(int(token)) == token,
                "SCHEMA_INVALID",
                f"{label} array pointer token differs",
            )
            position = int(token)
            _require(
                0 <= position < len(value),
                "SCHEMA_INVALID",
                f"{label} array pointer is unresolved",
            )
            value = value[position]
        else:
            _require(
                isinstance(value, dict) and token in value,
                "SCHEMA_INVALID",
                f"{label} object pointer is unresolved",
            )
            value = value[token]
    return value


def _case435_expected_invocations():
    rows = []
    for application_name, _, _, count, ordinal_program in CASE435_APPLICATIONS:
        if ordinal_program == "SINGLE_ZERO_NULL_BOUND_V1":
            _require(
                count == 1,
                "AUTHORITY_INVALID",
                "case435 singleton invocation authority differs",
            )
            rows.append(
                {
                    "application_name": application_name,
                    "application_invocation_ordinal": 0,
                    "bound_observation_ordinal": None,
                }
            )
            continue
        _require(
            ordinal_program == "ZERO_BASED_OBSERVATION_RANGE_V1"
            and count == CASE435_OBSERVATION_COUNT,
            "AUTHORITY_INVALID",
            "case435 ranged invocation authority differs",
        )
        rows.extend(
            {
                "application_name": application_name,
                "application_invocation_ordinal": ordinal,
                "bound_observation_ordinal": ordinal,
            }
            for ordinal in range(count)
        )
    _require(
        len(rows) == CASE435_APPLICATION_INVOCATION_COUNT,
        "AUTHORITY_INVALID",
        "case435 invocation expansion differs",
    )
    return rows


def _validate_case435_reference_resolution(
    reference,
    expected_kind,
    expected_type,
    expected_identity_field,
    authorities,
    source_inventory,
    context_by_id,
    witness,
    inventory,
    expected_pointer=None,
):
    validated = _validate_record_reference(
        reference,
        authorities["seed"],
        expected_kind,
        source_inventory if expected_kind == "V3_INVENTORY_POINTER" else None,
    )
    if expected_kind == "WITNESS_RECORD":
        record = witness
        object_id = None
    elif expected_kind == "CONTEXT_OBJECT":
        object_id = validated["maximum_context_object_id"]
        row = context_by_id.get(object_id)
        _require(
            row is not None,
            "SCHEMA_INVALID",
            "case435 context reference is unresolved",
        )
        record = row["record"]
    else:
        _require(
            validated["inventory_json_pointer"] == expected_pointer,
            "SCHEMA_INVALID",
            "case435 fixed-authority pointer differs",
        )
        record = _json_pointer(inventory, expected_pointer, "case435 authority")
        object_id = None
    raw = _canonical_bytes(record)
    _require(
        validated["record_type_name"] == expected_type
        and validated["record_identity_field"] == expected_identity_field
        and isinstance(record, dict)
        and validated["record_identity"] == record.get(expected_identity_field)
        and validated["record_canonical_byte_length"] == len(raw)
        and validated["record_canonical_sha256"] == _sha256(raw),
        "SCHEMA_INVALID",
        "case435 record reference does not resolve byte-exactly",
    )
    if expected_kind == "CONTEXT_OBJECT":
        _require(
            context_by_id[object_id]["record_type_name"] == expected_type
            and context_by_id[object_id]["record_identity_field"]
            == expected_identity_field,
            "SCHEMA_INVALID",
            "case435 context reference type metadata differs",
        )
    return record, object_id


def _validate_case435_packed_context(
    payload, snapshot, authorities, case, witness
):
    _require(
        authorities["authority_mode"]
        == "SUCCESSOR_CASE435_PACKED_CONTEXT_BOUNDARY_V1"
        and case["case_position"] == CASE435_POSITION,
        "UNSUPPORTED_CASE",
        "packed context is authorized only for case435 under its correction boundary",
    )
    correction = authorities["packed_context_boundary"]
    pack_contract = correction["context_pack_contract"]
    pack_entries = payload["ordered_context_pack_entries"]
    _require(
        isinstance(pack_entries, list) and len(pack_entries) == 1,
        "SCHEMA_INVALID",
        "case435 requires exactly one context-pack entry",
    )
    candidate_entry = pack_entries[0]
    _closed(
        candidate_entry,
        pack_contract["ordered_candidate_pack_entry_member_names"],
        "case435 context-pack entry",
    )
    pack_id = _sha(candidate_entry["context_pack_id"], "case435 context-pack ID")
    expected_path = f"context_objects/packs/{pack_id[:2]}/{pack_id}.json"
    _require(
        candidate_entry["context_pack_position"] == 1
        and candidate_entry["repository_relative_path"] == expected_path,
        "SCHEMA_INVALID",
        "case435 context-pack path or position differs",
    )
    file_by_path = {
        row["relative_path"]: row for row in snapshot["context_files"]
    }
    _require(
        len(file_by_path) == len(snapshot["context_files"]) == 1
        and expected_path in file_by_path,
        "FILESYSTEM_INVALID",
        "case435 context-pack physical closure differs",
    )
    _require(
        [row[0] for row in snapshot["context_directories"]]
        == ["context_objects/packs", f"context_objects/packs/{pack_id[:2]}"],
        "FILESYSTEM_INVALID",
        "case435 context-pack directory closure differs",
    )
    file_record = file_by_path[expected_path]
    pack_raw = file_record["raw"]
    _require(
        candidate_entry["raw_octet_count"] == len(pack_raw)
        and candidate_entry["raw_sha256"] == file_record["raw_sha256"]
        and len(pack_raw)
        < pack_contract["individual_pack_strict_upper_octets"],
        "IDENTITY_INVALID",
        "case435 context-pack physical identity differs",
    )
    pack = _strict_loads(pack_raw, authorities["limits"])
    _closed(
        pack,
        pack_contract["ordered_pack_member_names"],
        "case435 context pack",
    )
    _require(
        pack_raw == _canonical_bytes(pack),
        "CANONICALIZATION_INVALID",
        "case435 context pack is not exact compact canonical JSON",
    )
    pack_payload = {
        name: pack[name]
        for name in pack_contract["ordered_pack_member_names"][:-1]
    }
    _require(
        pack["context_pack_version"] == CASE435_CONTEXT_PACK_VERSION
        and pack["canonicalization_version"]
        == authorities["boundary"]["canonicalization_version"]
        and pack["measurement_schema_version"]
        == authorities["boundary"]["measurement_schema_version"]
        and pack["maximum_protocol_sha256"]
        == authorities["effective_protocol_sha256"]
        and pack["case_position"] == CASE435_POSITION
        and pack["pack_position"] == 1
        and pack["context_pack_id"]
        == _semantic_id(CASE435_CONTEXT_PACK_DOMAIN, pack_payload)
        == pack_id,
        "IDENTITY_INVALID",
        "case435 context-pack semantic identity differs",
    )
    packed_rows = pack["ordered_context_object_records"]
    _require(
        isinstance(packed_rows, list)
        and len(packed_rows) == 67
        and candidate_entry["context_object_count"] == 67,
        "SCHEMA_INVALID",
        "case435 packed context-object count differs",
    )
    source_inventory, registry_id, literal_sha = _authority_provenance(authorities)
    descriptors = {
        row["type_name"]: row
        for row in authorities["registry"]["ordered_external_type_descriptors"]
    }
    context_by_id = {}
    inherited_entries = []
    inherited_files = []
    context_ids = []
    records = []
    for position, row in enumerate(packed_rows, 1):
        _closed(
            row,
            pack_contract["ordered_context_object_record_member_names"],
            "case435 packed context-object record",
        )
        object_id = _sha(
            row["maximum_context_object_id"], "case435 context-object ID"
        )
        _require(
            row["context_object_position"] == position
            and (not context_ids or context_ids[-1] < object_id),
            "SCHEMA_INVALID",
            "case435 context-object order differs",
        )
        type_name = row["record_type_name"]
        descriptor = descriptors.get(type_name)
        record = row["record"]
        record_raw = _canonical_bytes(record)
        _require(
            descriptor is not None
            and descriptor["type_form"] == "RECORD"
            and descriptor["identity_field"] == row["record_identity_field"]
            and isinstance(record, dict)
            and row["record_identity"] == record.get(row["record_identity_field"])
            and row["record_canonical_byte_length"] == len(record_raw)
            and row["record_canonical_sha256"] == _sha256(record_raw),
            "IDENTITY_INVALID",
            "case435 packed logical-record identity differs",
        )
        context_payload = {
            "maximum_protocol_sha256": authorities["effective_protocol_sha256"],
            "source_inventory_sha256": source_inventory,
            "external_schema_registry_id": registry_id,
            "rule_literal_authority_sha256": literal_sha,
            "record_type_name": type_name,
            "record_identity_field": row["record_identity_field"],
            "record_identity": row["record_identity"],
            "record_canonical_byte_length": len(record_raw),
            "record_canonical_sha256": _sha256(record_raw),
            "record": record,
        }
        _require(
            object_id
            == _seed_semantic_id(
                authorities["seed"], CONTEXT_OBJECT_DOMAIN, context_payload
            ),
            "IDENTITY_INVALID",
            "case435 context-object semantic identity differs",
        )
        output_path = f"context_objects/{object_id[:2]}/{object_id}.json"
        inherited_entries.append(
            {
                "context_object_position": position,
                "claimed_maximum_context_object_id": object_id,
                "record_type_name": type_name,
                "repository_relative_path": output_path,
                "raw_octet_count": len(record_raw),
                "raw_sha256": _sha256(record_raw),
            }
        )
        inherited_files.append(
            {
                "relative_path": output_path,
                "raw": record_raw,
                "raw_sha256": _sha256(record_raw),
            }
        )
        context_ids.append(object_id)
        records.append(record)
        context_by_id[object_id] = row
    _require(
        candidate_entry["first_maximum_context_object_id"] == context_ids[0]
        and candidate_entry["last_maximum_context_object_id"] == context_ids[-1]
        and len(context_by_id) == len(context_ids),
        "SCHEMA_INVALID",
        "case435 context-pack range or uniqueness differs",
    )

    scope = payload["scope_witness_context"]
    _closed(
        scope,
        [
            "context_kind",
            "constraint_scope_profile_id",
            "selected_root_family_position",
            "measured_sequence_ordinal",
            "root_record_reference",
            "selector_authority_reference",
            "target_field_registry_authority_reference",
            "marker_contract_authority_reference",
            "ordered_observation_record_references",
            "ordered_application_invocations",
        ],
        "case435 root-application scope",
    )
    _require(
        scope["context_kind"] == "ROOT_APPLICATION"
        and scope["constraint_scope_profile_id"] == CASE435_PROFILE_ID
        and scope["selected_root_family_position"] == 1
        and scope["measured_sequence_ordinal"]
        == CASE435_MEASURED_SEQUENCE_ORDINAL,
        "SCHEMA_INVALID",
        "case435 root-application coordinate differs",
    )
    inventory = _strict_loads(
        authorities["authority_bytes"]["V4_INVENTORY"], authorities["limits"]
    )
    root, root_object_id = _validate_case435_reference_resolution(
        scope["root_record_reference"],
        "CONTEXT_OBJECT",
        CASE435_ROOT_TYPE,
        "target_observation_root_sha256",
        authorities,
        source_inventory,
        context_by_id,
        witness,
        inventory,
    )
    selector, _ = _validate_case435_reference_resolution(
        scope["selector_authority_reference"],
        "V3_INVENTORY_POINTER",
        CASE435_SELECTOR_TYPE,
        "checkpoint_selector_id",
        authorities,
        source_inventory,
        context_by_id,
        witness,
        inventory,
        CASE435_SELECTOR_POINTER,
    )
    target_registry, _ = _validate_case435_reference_resolution(
        scope["target_field_registry_authority_reference"],
        "V3_INVENTORY_POINTER",
        CASE435_TARGET_REGISTRY_TYPE,
        "target_field_registry_id",
        authorities,
        source_inventory,
        context_by_id,
        witness,
        inventory,
        CASE435_TARGET_REGISTRY_POINTER,
    )
    marker_contract, _ = _validate_case435_reference_resolution(
        scope["marker_contract_authority_reference"],
        "V3_INVENTORY_POINTER",
        CASE435_MARKER_CONTRACT_TYPE,
        "marker_contract_id",
        authorities,
        source_inventory,
        context_by_id,
        witness,
        inventory,
        CASE435_MARKER_CONTRACT_POINTER,
    )
    observation_references = scope["ordered_observation_record_references"]
    _require(
        isinstance(observation_references, list)
        and len(observation_references) == CASE435_OBSERVATION_COUNT,
        "SCHEMA_INVALID",
        "case435 observation-reference count differs",
    )
    observations = []
    referenced_context_ids = [root_object_id]
    for ordinal, reference in enumerate(observation_references):
        kind = (
            "WITNESS_RECORD"
            if ordinal == CASE435_MEASURED_SEQUENCE_ORDINAL
            else "CONTEXT_OBJECT"
        )
        observation, object_id = _validate_case435_reference_resolution(
            reference,
            kind,
            CASE435_TYPE,
            "observation_id",
            authorities,
            source_inventory,
            context_by_id,
            witness,
            inventory,
        )
        observations.append(observation)
        if object_id is not None:
            referenced_context_ids.append(object_id)
    _require(
        len({row["observation_id"] for row in observations})
        == CASE435_OBSERVATION_COUNT
        and observations[CASE435_MEASURED_SEQUENCE_ORDINAL] == witness
        and witness["observation_id"]
        not in {
            row["record_identity"]
            for row in packed_rows
            if row["record_type_name"] == CASE435_TYPE
        }
        and root["observation_count"] == CASE435_OBSERVATION_COUNT
        and root["ordered_observation_ids"]
        == [row["observation_id"] for row in observations]
        and root["full_checkpoint_selector_id"]
        == selector["checkpoint_selector_id"]
        and root["target_field_registry_id"]
        == target_registry["target_field_registry_id"]
        and root["operation_kind"] == "INGRESS"
        and sorted(referenced_context_ids) == context_ids
        and len(referenced_context_ids) == len(set(referenced_context_ids)),
        "SCHEMA_INVALID",
        "case435 retained record/reference closure differs",
    )
    _require(
        scope["ordered_application_invocations"]
        == _case435_expected_invocations(),
        "SCHEMA_INVALID",
        "case435 retained application schedule differs",
    )
    return {
        "entries": inherited_entries,
        "ids": context_ids,
        "records": records,
        "owner": None,
        "scope": scope,
        "root": root,
        "observations": observations,
        "selector": selector,
        "target_registry": target_registry,
        "marker_contract": marker_contract,
        "signed_spec": None,
        "files": inherited_files,
    }


def _validate_candidate_context(
    payload, snapshot, authorities, case, witness
):
    if case["case_position"] == CASE435_POSITION:
        return _validate_case435_packed_context(
            payload, snapshot, authorities, case, witness
        )
    entries = payload["ordered_context_object_entries"]
    _require(
        isinstance(entries, list),
        "SCHEMA_INVALID",
        "candidate context entries are not an array",
    )
    file_by_path = {
        record["relative_path"]: record for record in snapshot["context_files"]
    }
    _require(
        len(file_by_path) == len(snapshot["context_files"]),
        "FILESYSTEM_INVALID",
        "candidate context paths are duplicate",
    )
    source_inventory, registry_id, literal_sha = _authority_provenance(authorities)
    entry_schema = authorities["boundary"]["candidate_bundle_contract"][
        "context_object_entry_schema"
    ]
    descriptors = {
        row["type_name"]: row
        for row in authorities["registry"]["ordered_external_type_descriptors"]
    }
    context_ids = []
    records = []
    expected_paths = []
    for position, entry in enumerate(entries, 1):
        _closed(entry, entry_schema["ordered_member_names"], "context-object entry")
        _require(
            entry["context_object_position"] == position,
            "SCHEMA_INVALID",
            "context-object position differs",
        )
        object_id = _sha(
            entry["claimed_maximum_context_object_id"], "context-object ID"
        )
        _require(
            not context_ids or context_ids[-1] < object_id,
            "SCHEMA_INVALID",
            "context-object IDs are not strictly increasing",
        )
        context_ids.append(object_id)
        expected_path = f"context_objects/{object_id[:2]}/{object_id}.json"
        _require(
            entry["repository_relative_path"] == expected_path,
            "SCHEMA_INVALID",
            "context-object path differs",
        )
        expected_paths.append(expected_path)
        file_record = file_by_path.get(expected_path)
        _require(
            file_record is not None,
            "FILESYSTEM_INVALID",
            "declared context-object file is absent",
        )
        raw = file_record["raw"]
        _require(
            entry["raw_octet_count"] == len(raw)
            and entry["raw_sha256"] == file_record["raw_sha256"],
            "IDENTITY_INVALID",
            "context-object physical identity differs",
        )
        record = _strict_loads(raw, authorities["limits"])
        _require(
            isinstance(record, dict) and raw == _canonical_bytes(record),
            "CANONICALIZATION_INVALID",
            "context object is not exact compact canonical JSON",
        )
        type_name = entry["record_type_name"]
        descriptor = descriptors.get(type_name)
        _require(
            descriptor is not None and isinstance(descriptor["identity_field"], str),
            "SCHEMA_INVALID",
            "context-object type is not a standalone record",
        )
        identity_field = descriptor["identity_field"]
        _require(
            identity_field in record,
            "SCHEMA_INVALID",
            "context object lacks its record identity",
        )
        context_payload = {
            "maximum_protocol_sha256": authorities["effective_protocol_sha256"],
            "source_inventory_sha256": source_inventory,
            "external_schema_registry_id": registry_id,
            "rule_literal_authority_sha256": literal_sha,
            "record_type_name": type_name,
            "record_identity_field": identity_field,
            "record_identity": record[identity_field],
            "record_canonical_byte_length": len(raw),
            "record_canonical_sha256": file_record["raw_sha256"],
            "record": record,
        }
        _require(
            object_id
            == _seed_semantic_id(
                authorities["seed"], CONTEXT_OBJECT_DOMAIN, context_payload
            ),
            "IDENTITY_INVALID",
            "context-object semantic identity differs",
        )
        records.append(record)
    _require(
        sorted(file_by_path) == expected_paths,
        "FILESYSTEM_INVALID",
        "candidate context file closure differs",
    )
    expected_directories = sorted(
        {str(pathlib.PurePosixPath(path).parent) for path in expected_paths}
    )
    _require(
        [row[0] for row in snapshot["context_directories"]]
        == expected_directories,
        "FILESYSTEM_INVALID",
        "candidate context directory closure differs",
    )

    case_position = case["case_position"]
    if case_position in {CASE5_POSITION, CASE54_POSITION}:
        _require(
            payload["scope_witness_context"] is None
            and entries == []
            and records == [],
            "SCHEMA_INVALID",
            "intrinsic self-record case has retained context",
        )
        return {
            "entries": entries,
            "ids": context_ids,
            "records": records,
            "owner": None,
            "scope": None,
            "files": snapshot["context_files"],
        }

    if case_position == CASE69_POSITION:
        _require(
            entries == [] and records == [],
            "SCHEMA_INVALID",
            "case 69 fixed-authority scope cannot contain context-object files",
        )
        scope = payload["scope_witness_context"]
        _closed(
            scope,
            [
                "context_kind",
                "constraint_scope_profile_id",
                "operation_result_record_reference",
                "operation_spec_authority_reference",
                "ordered_application_invocations",
            ],
            "case 69 outer-result scope context",
        )
        _require(
            scope["context_kind"] == "OUTER_RESULT_APPLICATION"
            and scope["constraint_scope_profile_id"] == CASE69_PROFILE_ID,
            "SCHEMA_INVALID",
            "case 69 outer-result context/profile differs",
        )
        source_inventory, _, _ = _authority_provenance(authorities)
        result_reference = _validate_record_reference(
            scope["operation_result_record_reference"],
            authorities["seed"],
            "WITNESS_RECORD",
        )
        inventory = _strict_loads(
            authorities["authority_bytes"]["V4_INVENTORY"], authorities["limits"]
        )
        spec = inventory["fixture_records"]["operation_specs"]["LOCAL_SHUTDOWN"]
        spec_reference = _validate_record_reference(
            scope["operation_spec_authority_reference"],
            authorities["seed"],
            "V3_INVENTORY_POINTER",
            source_inventory,
        )
        witness_raw = _canonical_bytes(witness)
        spec_raw = _canonical_bytes(spec)
        _require(
            result_reference["record_type_name"] == CASE69_TYPE
            and result_reference["record_identity_field"] == "result_evidence_id"
            and result_reference["record_identity"]
            == witness.get("result_evidence_id")
            and result_reference["record_canonical_byte_length"] == len(witness_raw)
            and result_reference["record_canonical_sha256"] == _sha256(witness_raw),
            "SCHEMA_INVALID",
            "case 69 witness reference does not resolve byte-exactly",
        )
        _require(
            spec_reference["inventory_json_pointer"] == CASE69_SPEC_POINTER
            and spec_reference["record_type_name"] == CASE69_SPEC_TYPE
            and spec_reference["record_identity_field"] == "operation_spec_id"
            and spec_reference["record_identity"] == spec.get("operation_spec_id")
            and spec_reference["record_canonical_byte_length"] == len(spec_raw)
            and spec_reference["record_canonical_sha256"] == _sha256(spec_raw),
            "SCHEMA_INVALID",
            "case 69 signed-spec reference does not resolve byte-exactly",
        )
        _require(
            scope["ordered_application_invocations"]
            == [
                {
                    "application_name": CASE69_APPLICATION_NAME,
                    "application_invocation_ordinal": 0,
                    "bound_observation_ordinal": None,
                }
            ],
            "SCHEMA_INVALID",
            "case 69 retained application invocation differs",
        )
        return {
            "entries": entries,
            "ids": context_ids,
            "records": records,
            "owner": None,
            "scope": scope,
            "signed_spec": spec,
            "files": snapshot["context_files"],
        }

    _require(
        case_position == CASE24_POSITION and len(entries) == len(records) == 1,
        "SCHEMA_INVALID",
        "case 24 requires exactly one owner context object",
    )
    scope = payload["scope_witness_context"]
    _closed(
        scope,
        ["context_kind", "owner_record_reference", "payload_typed_member_path"],
        "case 24 scope context",
    )
    _require(
        scope["context_kind"] == "OWNER_MEMBER"
        and scope["payload_typed_member_path"] == ["result"],
        "SCHEMA_INVALID",
        "case 24 owner-member scope differs",
    )
    reference = _validate_record_reference(
        scope["owner_record_reference"], authorities["seed"], "CONTEXT_OBJECT"
    )
    entry = entries[0]
    owner = records[0]
    _require(
        entry["record_type_name"] == reference["record_type_name"] == CASE24_OWNER_TYPE
        and reference["maximum_context_object_id"] == context_ids[0]
        and reference["record_identity_field"] == "result_evidence_id"
        and reference["record_identity"] == owner.get("result_evidence_id")
        and reference["record_canonical_byte_length"] == entry["raw_octet_count"]
        and reference["record_canonical_sha256"] == entry["raw_sha256"],
        "SCHEMA_INVALID",
        "case 24 owner reference does not resolve byte-exactly",
    )
    _require(
        isinstance(owner.get("result"), dict)
        and _canonical_bytes(owner["result"]) == _canonical_bytes(witness),
        "WITNESS_ILLEGAL",
        "case 24 inline witness differs from the retained owner result",
    )
    return {
        "entries": entries,
        "ids": context_ids,
        "records": records,
        "owner": owner,
        "scope": scope,
        "signed_spec": None,
        "files": snapshot["context_files"],
    }


def _validate_candidate(candidate, raw, snapshot, authorities):
    boundary = authorities["boundary"]
    contract = boundary["candidate_bundle_contract"]
    schema = contract["candidate_envelope_schema"]
    _closed(candidate, schema["ordered_member_names"], "candidate envelope")
    _require(
        raw == _pretty_bytes(candidate),
        "CANONICALIZATION_INVALID",
        "candidate envelope encoding differs",
    )
    packed_candidate = candidate["candidate_version"] == CASE435_PACKED_CANDIDATE_VERSION
    _require(
        packed_candidate
        or candidate["candidate_version"] == schema["version_literal"],
        "SCHEMA_INVALID",
        "candidate version differs",
    )
    _require(
        candidate["canonicalization_version"] == boundary["canonicalization_version"],
        "AUTHORITY_INVALID",
        "candidate canonicalization differs",
    )
    _require(
        candidate["measurement_schema_version"]
        == boundary["measurement_schema_version"],
        "AUTHORITY_INVALID",
        "candidate measurement schema differs",
    )
    _require(
        candidate["protocol_version"] == boundary["protocol_version"],
        "AUTHORITY_INVALID",
        "candidate protocol differs",
    )
    _require(
        candidate["seed_catalog_id"] == authorities["effective_seed_id"],
        "AUTHORITY_INVALID",
        "candidate seed differs",
    )
    _require(
        candidate["finalization_manifest_id"]
        == authorities["effective_manifest_id"],
        "AUTHORITY_INVALID",
        "candidate manifest differs",
    )
    case, plan = _resolve_case_and_plan(authorities, candidate["case_position"])
    mode = authorities["authority_mode"]
    supported = (
        (CASE5_POSITION,)
        if mode == "PREDECESSOR_CONSTRUCTIVE_BOUNDARY_V1"
        else V4_SUCCESSOR_CASE_POSITIONS
        if mode == "SUCCESSOR_CASE435_PACKED_CONTEXT_BOUNDARY_V1"
        else V2_SUCCESSOR_CASE_POSITIONS
    )
    _require(
        candidate["case_position"] in supported,
        "UNSUPPORTED_CASE",
        "the selected verifier packet does not support this case",
    )
    _require(
        case["case_position"] == plan["case_position"] == candidate["case_position"],
        "AUTHORITY_INVALID",
        "effective case order differs",
    )
    expected_case_kind = (
        "LOCAL_SHUTDOWN_UNREPRESENTABLE_MINIMALITY"
        if candidate["case_position"] == CASE475_POSITION
        else "MAXIMUM_PUBLICATION_ROW"
    )
    _require(
        candidate["case_kind"] == case["case_kind"] == expected_case_kind,
        "SCHEMA_INVALID",
        "candidate case kind differs",
    )
    _require(
        candidate["case_binding"] == case["case_binding"] == plan["case_binding"],
        "SCHEMA_INVALID",
        "candidate case binding differs",
    )
    _require(
        candidate["logical_count_plan_id"] == plan["logical_count_plan_id"],
        "SCHEMA_INVALID",
        "candidate logical plan differs",
    )
    _require(
        packed_candidate == (candidate["case_position"] == CASE435_POSITION),
        "SCHEMA_INVALID",
        "case435 and packed-candidate versions are not paired exactly",
    )

    payload = candidate["candidate_payload"]
    local_candidate = candidate["case_position"] == CASE475_POSITION
    if packed_candidate:
        packed_contract = authorities["packed_context_boundary"][
            "packed_context_candidate_contract"
        ]
        _closed(
            payload,
            packed_contract["ordered_payload_member_names"],
            "packed candidate payload",
        )
        _require(
            payload["candidate_kind"]
            == packed_contract["candidate_kind"]
            == "MAXIMUM_WITNESS_PACKED_CONTEXT",
            "SCHEMA_INVALID",
            "packed candidate payload tag differs",
        )
        identity_domain = CASE435_PACKED_CANDIDATE_DOMAIN
    elif local_candidate:
        alternative = contract["candidate_payload_tagged_union"][
            "ordered_alternative_records"
        ][1]
        _closed(payload, alternative["ordered_member_names"], "local candidate payload")
        _require(
            payload["candidate_kind"]
            == alternative["candidate_kind"]
            == "LOCAL_SHUTDOWN_MUTATION"
            and isinstance(payload["mutated_spec"], dict)
            and isinstance(payload["prospective_result"], dict),
            "SCHEMA_INVALID",
            "local candidate payload differs",
        )
        identity_domain = schema["identity_domain"]
    else:
        alternative = contract["candidate_payload_tagged_union"][
            "ordered_alternative_records"
        ][0]
        _closed(payload, alternative["ordered_member_names"], "candidate payload")
        _require(
            payload["candidate_kind"]
            == alternative["candidate_kind"]
            == "MAXIMUM_WITNESS_CONTEXT",
            "SCHEMA_INVALID",
            "candidate payload tag differs",
        )
        identity_domain = schema["identity_domain"]
    if not local_candidate:
        _require(
            isinstance(payload["witness_record"], dict),
            "SCHEMA_INVALID",
            "witness record is not an object",
        )
        _require(
            payload["scope_witness_context"] is None
            or isinstance(payload["scope_witness_context"], dict),
            "SCHEMA_INVALID",
            "maximum scope context is neither null nor an object",
        )
    forbidden = set(contract["forbidden_producer_claim_member_names"])
    _require(
        not _contains_forbidden_member(candidate, forbidden),
        "PRODUCER_CLAIM_REJECT",
        "candidate contains a verifier-owned claim",
    )
    identity_payload = {
        name: candidate[name] for name in schema["ordered_member_names"][:-1]
    }
    _require(
        candidate["constructive_candidate_id"]
        == _semantic_id(identity_domain, identity_payload),
        "IDENTITY_INVALID",
        "candidate identity differs",
    )
    if local_candidate:
        _require(
            snapshot["context_directories"] == ()
            and snapshot["context_files"] == (),
            "FILESYSTEM_INVALID",
            "local candidate must have an empty context root",
        )
        return case, plan, payload, {
            "entries": [],
            "ids": [],
            "records": [],
            "owner": None,
            "scope": None,
            "files": (),
        }
    context = _validate_candidate_context(
        payload, snapshot, authorities, case, payload["witness_record"]
    )
    return case, plan, payload["witness_record"], context


def _eval_meter_expression(expression, step):
    _require(
        isinstance(expression, dict) and "opcode" in expression,
        "DERIVATION_INVALID",
        "meter expression differs",
    )
    opcode = expression["opcode"]
    if opcode == "CONST_U128" and set(expression) == {"opcode", "value"}:
        return _u128(expression["value"], "meter constant")
    if opcode == "STEP_LOGICAL_TRANSFER_MULTIPLICITY" and set(expression) == {"opcode"}:
        return _u128(step["logical_transfer_multiplicity"], "transfer multiplicity")
    if opcode == "PARAM_U128" and set(expression) == {"opcode", "parameter_name"}:
        return _u128(
            step["recurrence_parameters"][expression["parameter_name"]],
            "meter parameter",
        )
    if opcode == "PARAM_LIST_COUNT" and set(expression) == {"opcode", "parameter_name"}:
        value = step["recurrence_parameters"][expression["parameter_name"]]
        _require(
            isinstance(value, list),
            "DERIVATION_INVALID",
            "meter list parameter differs",
        )
        return len(value)
    if opcode in {"INDICATOR_PARAM_NONZERO", "INDICATOR_PARAM_IS_NULL"} and set(
        expression
    ) == {"opcode", "parameter_name"}:
        value = step["recurrence_parameters"][expression["parameter_name"]]
        return (
            int(value is not None)
            if opcode == "INDICATOR_PARAM_NONZERO"
            else int(value is None)
        )
    if opcode in {"CHECKED_ADD", "CHECKED_MUL"} and set(expression) == {
        "opcode",
        "ordered_operands",
    }:
        values = [
            _eval_meter_expression(child, step)
            for child in expression["ordered_operands"]
        ]
        _require(values, "DERIVATION_INVALID", "meter arithmetic has no operands")
        if opcode == "CHECKED_ADD":
            return _checked_add(*values)
        result = 1
        for value in values:
            result = _checked_mul(result, value)
        return result
    _reject("DERIVATION_INVALID", f"meter opcode differs: {opcode}")


def _cell(lower, upper, state=None):
    lower = _u128(lower, "cell lower bound")
    upper = _u128(upper, "cell upper bound")
    _require(lower <= upper, "DERIVATION_INVALID", "cell bounds are inverted")
    return {
        "status": MAY_BE_NONEMPTY,
        "lower": lower,
        "upper": upper,
        "state": [] if state is None else list(state),
    }


def _locator_values(witness, locator, expected_alternative):
    values = [witness]
    typed_path = locator["typed_path"]
    _require(isinstance(typed_path, list), "DERIVATION_INVALID", "typed path differs")
    for step in typed_path:
        _closed(
            step,
            ["member_name", "path_step_kind", "union_alternative_name"],
            "typed-path step",
        )
        kind = step["path_step_kind"]
        if kind == "UNION_ALTERNATIVE":
            _require(
                step["member_name"] is None
                and isinstance(step["union_alternative_name"], str),
                "DERIVATION_INVALID",
                "typed path union-alternative step differs",
            )
            if step["union_alternative_name"] != expected_alternative:
                return []
            continue
        if kind == "RECORD_MEMBER":
            _require(
                step["union_alternative_name"] is None
                and isinstance(step["member_name"], str),
                "DERIVATION_INVALID",
                "record-member path step differs",
            )
            name = step["member_name"]
            next_values = []
            for value in values:
                _require(
                    isinstance(value, dict) and name in value,
                    "WITNESS_ILLEGAL",
                    f"witness member is absent: {name}",
                )
                next_values.append(value[name])
            values = next_values
            continue
        if kind == "ARRAY_ITEM_TEMPLATE":
            _require(
                step["member_name"] is None
                and step["union_alternative_name"] is None,
                "DERIVATION_INVALID",
                "array-item path step differs",
            )
            next_values = []
            for value in values:
                _require(
                    isinstance(value, list),
                    "WITNESS_ILLEGAL",
                    "array-item path does not resolve an array",
                )
                next_values.extend(value)
            values = next_values
            continue
        _reject("DERIVATION_INVALID", f"unsupported typed-path step: {kind}")
    return values


def _logical_template(seed, plan, case):
    recipe = seed["logical_plan_recipe_catalog"]
    templates = {
        row["logical_plan_template_id"]: row
        for row in recipe["ordered_logical_plan_templates"]
    }
    template = templates.get(plan["logical_plan_template_id"])
    _require(template is not None, "DERIVATION_INVALID", "logical template is absent")
    binding = case["case_binding"]
    if case["case_position"] in {CASE69_POSITION, CASE435_POSITION}:
        expected_program_id = (
            CASE69_PROGRAM_ID
            if case["case_position"] == CASE69_POSITION
            else SUCCESSOR_CASE435_PROGRAM_ID
        )
        _require(
            plan["profile_conditioning_program_id"] == expected_program_id
            and plan["logical_root_reference"]
            == {
                "root_kind": "PROFILE_CONDITIONING_PROGRAM",
                "root_id": expected_program_id,
            }
            and plan["local_analytic_catalog_id"] is None
            and plan["root_step_position"] == template["root_step_position"]
            and template["root_type_name"] == binding["type_name"]
            == (CASE69_TYPE if case["case_position"] == CASE69_POSITION else CASE435_TYPE)
            and template["root_alternative_name"]
            == binding["alternative_name"]
            is None,
            "DERIVATION_INVALID",
            "profile-conditioned template root binding differs",
        )
        return template
    _require(
        plan["logical_root_reference"]
        == {
            "root_kind": "LOGICAL_PLAN_TEMPLATE",
            "root_id": template["logical_plan_template_id"],
        },
        "DERIVATION_INVALID",
        "logical-template root reference differs",
    )
    _require(
        plan["profile_conditioning_program_id"] is None,
        "DERIVATION_INVALID",
        "ordinary case unexpectedly has profile conditioning",
    )
    _require(
        plan["local_analytic_catalog_id"] is None,
        "DERIVATION_INVALID",
        "ordinary case unexpectedly has local analytics",
    )
    _require(
        plan["root_step_position"] == template["root_step_position"],
        "DERIVATION_INVALID",
        "ordinary-case root step differs",
    )
    _require(
        template["root_type_name"] == binding["type_name"]
        and template["root_alternative_name"] == binding["alternative_name"],
        "DERIVATION_INVALID",
        "ordinary-case template root binding differs",
    )
    return template


def _plan_identity_preimage(seed, plan):
    if plan["logical_count_plan_id"] == SUCCESSOR_CASE435_PLAN_ID:
        payload = {
            name: value
            for name, value in plan.items()
            if name != "logical_count_plan_id"
        }
        raw = _canonical_bytes(
            {"domain": SUCCESSOR_PLAN_DOMAIN, "payload": payload}
        )
        _require(
            _sha256(raw) == SUCCESSOR_CASE435_PLAN_ID,
            "DERIVATION_INVALID",
            "successor case435 logical-plan identity does not reproduce",
        )
        return raw

    identity = next(
        (
            row
            for row in seed["ordered_identity_domain_records"]
            if row["identity_name"] == "LOGICAL_COUNT_PLAN"
        ),
        None,
    )
    _require(
        identity is not None,
        "AUTHORITY_INVALID",
        "logical-plan identity authority is absent",
    )
    payload = {name: plan[name] for name in identity["ordered_payload_member_names"]}
    raw = _canonical_bytes(
        {
            "canonicalization_version": seed["canonicalization_version"],
            "domain": identity["domain_literal"],
            "payload": payload,
            "schema_version": seed["measurement_schema_version"],
        }
    )
    _require(
        _sha256(raw) == plan["logical_count_plan_id"],
        "DERIVATION_INVALID",
        "logical-plan identity does not reproduce",
    )
    return raw


def _registry_indexes(registry):
    def exact_index(rows, key, label):
        _require(isinstance(rows, list), "AUTHORITY_INVALID", f"{label} is not an array")
        result = {}
        for row in rows:
            _require(
                isinstance(row, dict)
                and isinstance(row.get(key), str)
                and row[key] not in result,
                "AUTHORITY_INVALID",
                f"{label} identity is absent or duplicate",
            )
            result[row[key]] = row
        return result

    return {
        "types": exact_index(
            registry["ordered_external_type_descriptors"], "type_name", "type catalog"
        ),
        "schemas": exact_index(
            registry["value_schema_catalog"], "value_schema_id", "value-schema catalog"
        ),
        "languages": exact_index(
            registry["text_language_catalog"], "text_language_id", "text-language catalog"
        ),
        "dfas": exact_index(
            registry["ascii_dfa_catalog"], "ascii_dfa_id", "ASCII-DFA catalog"
        ),
        "identifier_profiles": exact_index(
            registry["identifier_profile_catalog"],
            "unicode_identifier_profile_id",
            "Unicode identifier-profile catalog",
        ),
        "rules": exact_index(
            registry["ordered_cross_field_rule_descriptors"], "rule_id", "rule catalog"
        ),
        "applications": exact_index(
            registry["ordered_rule_application_descriptors"],
            "application_name",
            "rule-application catalog",
        ),
    }


def _validate_subset_codec(descriptor, value):
    relation = descriptor["codec_byte_bound_relation"]
    limit = _u128(descriptor["codec_octet_limit"], "typed codec limit")
    length = len(_canonical_bytes(value))
    _require(
        (relation == "LE" and length <= limit)
        or (relation == "LT" and length < limit),
        "WITNESS_ILLEGAL",
        f"typed value exceeds the {descriptor['type_name']} codec bound",
    )


def _validate_subset_text(indexes, language_id, value):
    _require(type(value) is str, "WITNESS_ILLEGAL", "typed text is not exact text")
    _require(
        not any(0xD800 <= ord(character) <= 0xDFFF for character in value),
        "WITNESS_ILLEGAL",
        "typed text contains a surrogate",
    )
    encoded = value.encode("utf-8", errors="strict")
    language = indexes["languages"].get(language_id)
    _require(language is not None, "AUTHORITY_INVALID", "text language is unresolved")
    minimum = language["minimum_utf8_octets"]
    maximum = language["maximum_utf8_octets"]
    _require(
        (minimum is None or len(encoded) >= minimum)
        and (maximum is None or len(encoded) <= maximum),
        "WITNESS_ILLEGAL",
        "typed text length is outside its frozen language",
    )
    kind = language["language_kind"]
    if kind in {"LITERAL", "ENUM"}:
        _require(
            value in language["ordered_literals"],
            "WITNESS_ILLEGAL",
            "typed text is outside its frozen literal set",
        )
        return
    if kind == "BUILTIN":
        builtin = language["built_in_language_kind"]
        if builtin == "LOWERCASE_SHA256":
            _require(
                len(value) == 64
                and all(character in "0123456789abcdef" for character in value),
                "WITNESS_ILLEGAL",
                "typed SHA-256 text differs",
            )
            return
        if builtin == "UINT128_DECIMAL":
            maximum = language["decimal_maximum"]
            _require(
                value
                and value.isascii()
                and value.isdigit()
                and (value == "0" or not value.startswith("0"))
                and isinstance(maximum, str)
                and (
                    len(value) < len(maximum)
                    or (len(value) == len(maximum) and value <= maximum)
                ),
                "WITNESS_ILLEGAL",
                "typed UInt128 decimal text differs",
            )
            return
        _require(
            builtin == "RAW_CANONICAL_JSON_STRING",
            "AUTHORITY_INVALID",
            "V2 subset encountered an unsupported built-in text language",
        )
        _canonical_bytes(value)
        return
    if kind == "ASCII_DFA":
        dfa = indexes["dfas"].get(language["ascii_dfa_id"])
        _require(dfa is not None, "AUTHORITY_INVALID", "ASCII DFA is unresolved")
        _require(
            all(byte < 128 for byte in encoded)
            and dfa["minimum_octets"] <= len(encoded) <= dfa["maximum_octets"],
            "WITNESS_ILLEGAL",
            "typed text is outside its ASCII-DFA byte domain",
        )
        state = dfa["start_state"]
        rows = dfa["ordered_transition_rows"]
        for byte in encoded:
            matches = [
                row
                for row in rows
                if row["source_state"] == state
                and row["inclusive_byte_minimum"] <= byte <= row["inclusive_byte_maximum"]
            ]
            _require(
                len(matches) == 1,
                "WITNESS_ILLEGAL",
                "typed text has no unique ASCII-DFA transition",
            )
            state = matches[0]["target_state"]
        _require(
            state in dfa["ordered_accepting_states"],
            "WITNESS_ILLEGAL",
            "typed text ends outside an ASCII-DFA accepting state",
        )
        return
    if kind == "UNICODE_IDENTIFIER":
        profile = indexes["identifier_profiles"].get(
            language["unicode_identifier_profile_id"]
        )
        _require(
            profile is not None
            and profile["unicode_version"] == "15.0.0"
            and profile["normalization_form"] == "NFC",
            "AUTHORITY_INVALID",
            "Unicode identifier profile is unresolved or not frozen at 15.0.0 NFC",
        )
        _require(
            value
            and len(value) <= profile["maximum_scalar_values"]
            and len(encoded) <= profile["maximum_utf8_octets"],
            "WITNESS_ILLEGAL",
            "Unicode identifier is empty or exceeds its frozen profile",
        )
        # V2 needs only the fixed ASCII workload-family authority.  ASCII is
        # NFC-stable, so this strict subset never accepts a non-NFC value and
        # avoids trusting the host's potentially drifting Unicode database.
        _require(
            all(ord(character) < 128 for character in value),
            "AUTHORITY_INVALID",
            "V2 subset does not admit non-ASCII Unicode identifiers",
        )

        def code_point(literal):
            _require(
                isinstance(literal, str)
                and literal.startswith("U+")
                and 4 <= len(literal[2:]) <= 6
                and all(
                    character in "0123456789ABCDEF" for character in literal[2:]
                ),
                "AUTHORITY_INVALID",
                "Unicode identifier code-point authority differs",
            )
            return int(literal[2:], 16)

        forbidden = [
            (code_point(lower), code_point(upper))
            for lower, upper in profile["forbidden_code_point_ranges"]
        ]
        _require(
            not any(
                lower <= ord(character) <= upper
                for character in value
                for lower, upper in forbidden
            ),
            "WITNESS_ILLEGAL",
            "Unicode identifier contains a forbidden code point",
        )
        edge_trim = {
            code_point(literal) for literal in profile["edge_trim_code_points"]
        }
        _require(
            ord(value[0]) not in edge_trim and ord(value[-1]) not in edge_trim,
            "WITNESS_ILLEGAL",
            "Unicode identifier has a forbidden edge trim",
        )
        return
    _reject("AUTHORITY_INVALID", f"V2 subset text language is unsupported: {kind}")


def _validate_subset_schema(indexes, schema_id, value, owner, owner_type_name):
    schema = indexes["schemas"].get(schema_id)
    _require(schema is not None, "AUTHORITY_INVALID", "value schema is unresolved")
    if value is None:
        _require(
            schema["nullable"] is True,
            "WITNESS_ILLEGAL",
            "non-nullable typed value is null",
        )
        return
    kind = schema["schema_kind"]
    if kind == "TEXT":
        _validate_subset_text(indexes, schema["text_language_id"], value)
        return
    if kind == "SAFE_INTEGER":
        _require(
            type(value) is int
            and schema["integer_minimum"] <= value <= schema["integer_maximum"],
            "WITNESS_ILLEGAL",
            "typed safe integer is outside its frozen interval",
        )
        return
    if kind == "EXACT_BOOLEAN":
        _require(
            type(value) is bool,
            "WITNESS_ILLEGAL",
            "typed exact Boolean differs",
        )
        return
    if kind == "ARRAY":
        _require(
            isinstance(value, list)
            and schema["array_minimum_items"]
            <= len(value)
            <= schema["array_maximum_items"],
            "WITNESS_ILLEGAL",
            "typed array cardinality is outside its frozen interval",
        )
        for item in value:
            _validate_subset_schema(
                indexes,
                schema["array_item_value_schema_id"],
                item,
                owner,
                owner_type_name,
            )
        return
    if kind == "OBJECT_REF":
        _validate_subset_type(
            indexes,
            schema["referenced_type_name"],
            value,
            owner,
            owner_type_name,
        )
        return
    _reject("AUTHORITY_INVALID", f"V2 subset schema kind is unsupported: {kind}")


def _validate_subset_type(
    indexes, type_name, value, owner=None, owner_type_name=None
):
    descriptor = indexes["types"].get(type_name)
    _require(descriptor is not None, "AUTHORITY_INVALID", "typed descriptor is unresolved")
    form = descriptor["type_form"]
    if form == "RECORD":
        _require(isinstance(value, dict), "WITNESS_ILLEGAL", "typed record is not an object")
        members = descriptor["record_member_descriptors"]
        _require(
            set(value) == {row["member_name"] for row in members},
            "WITNESS_ILLEGAL",
            f"typed {type_name} record members differ",
        )
        for row in members:
            _validate_subset_schema(
                indexes,
                row["value_schema_id"],
                value[row["member_name"]],
                value,
                type_name,
            )
        identity_field = descriptor["identity_field"]
        if identity_field is not None:
            identity_payload = {
                name: value[name]
                for name in descriptor["identity_payload_member_order"]
            }
            _require(
                value["record_domain"] == descriptor["described_record_domain"]
                and value[identity_field]
                == _sha256(
                    _canonical_bytes(
                        {
                            "canonicalization_version": value[
                                "canonicalization_version"
                            ],
                            "domain": descriptor["described_record_domain"],
                            "payload": identity_payload,
                            "schema_version": value["measurement_schema_version"],
                        }
                    )
                ),
                "WITNESS_ILLEGAL",
                f"typed {type_name} semantic identity differs",
            )
        _validate_subset_codec(descriptor, value)
        return
    if form == "TAGGED_UNION":
        topology = descriptor["tagged_union_descriptor"]
        payload_path = topology["payload_typed_member_path"]
        if topology["payload_binding_scope"] == "SELF_VALUE":
            _require(
                topology["payload_owner_type_name"] is None
                and payload_path == [],
                "AUTHORITY_INVALID",
                "self-value tagged-union authority differs",
            )
            selected_payload = value
        else:
            _require(
                topology["payload_binding_scope"] == "OWNER_MEMBER"
                and isinstance(owner, dict)
                and topology["payload_owner_type_name"] == owner_type_name
                and isinstance(payload_path, list)
                and payload_path,
                "WITNESS_ILLEGAL",
                (
                    "owner-member tagged-union binding differs: "
                    f"union={type_name}, expected_owner={topology['payload_owner_type_name']}, "
                    f"actual_owner={owner_type_name}"
                ),
            )
            selected_payload = owner
            for member in payload_path:
                _require(
                    isinstance(selected_payload, dict) and member in selected_payload,
                    "WITNESS_ILLEGAL",
                    "owner-member tagged-union payload path is unresolved",
                )
                selected_payload = selected_payload[member]
        _require(
            _canonical_bytes(selected_payload) == _canonical_bytes(value),
            "WITNESS_ILLEGAL",
            "owner-member tagged-union payload differs",
        )
        discriminators = {}
        for row in topology["ordered_discriminator_descriptors"]:
            path = row["discriminator_typed_member_path"]
            root = (
                value
                if row["discriminator_scope"] == "SELECTED_VALUE"
                else owner
            )
            _require(
                len(path) == 1 and isinstance(root, dict) and path[0] in root,
                "WITNESS_ILLEGAL",
                "tagged-union discriminator path is unresolved",
            )
            _validate_subset_text(indexes, row["text_language_id"], root[path[0]])
            discriminators[path[0]] = root[path[0]]
        matches = [
            row
            for row in topology["ordered_alternatives"]
            if {
                literal["member_name"]: literal["text_value"]
                for literal in row["ordered_discriminator_literals"]
            }
            == discriminators
        ]
        _require(
            len(matches) == 1,
            "WITNESS_ILLEGAL",
            "owner discriminators do not select exactly one alternative",
        )
        _validate_subset_type(
            indexes, matches[0]["referenced_type_name"], selected_payload
        )
        _validate_subset_codec(descriptor, selected_payload)
        return
    _reject("AUTHORITY_INVALID", f"V2 subset type form is unsupported: {form}")


class _Case435RuleRuntime:
    """Verifier-owned static semantics for the frozen case-435 rule closure."""

    def __init__(self, indexes):
        self.indexes = indexes
        self._target_registry_cache = {}
        self.records = {
            name: row
            for name, row in indexes["types"].items()
            if row["type_form"] == "RECORD"
        }
        self.unions = {
            name: row
            for name, row in indexes["types"].items()
            if row["type_form"] == "TAGGED_UNION"
        }

    @staticmethod
    def _exact_equal(left, right):
        return type(left) is type(right) and (
            _canonical_bytes(left) == _canonical_bytes(right)
            if isinstance(left, (dict, list))
            else left == right
        )

    def _record_identity(self, type_name, record):
        descriptor = self.records.get(type_name)
        _require(
            descriptor is not None
            and descriptor["identity_field"] is not None
            and isinstance(record, dict),
            "AUTHORITY_INVALID",
            f"case435 identity descriptor is unresolved: {type_name}",
        )
        payload = {
            name: record[name]
            for name in descriptor["identity_payload_member_order"]
        }
        return _sha256(
            _canonical_bytes(
                {
                    "canonicalization_version": record["canonicalization_version"],
                    "domain": descriptor["described_record_domain"],
                    "payload": payload,
                    "schema_version": record["measurement_schema_version"],
                }
            )
        )

    @staticmethod
    def _index_records(records, key, count, label):
        _require(
            isinstance(records, list) and len(records) == count,
            "WITNESS_ILLEGAL",
            f"case435 {label} count differs",
        )
        result = {}
        for row in records:
            _require(
                isinstance(row, dict)
                and isinstance(row.get(key), str)
                and row[key] not in result,
                "WITNESS_ILLEGAL",
                f"case435 {label} identity is absent or duplicate",
            )
            result[row[key]] = row
        return result

    def _target_indexes(self, registry):
        _require(
            isinstance(registry, dict)
            and isinstance(registry.get("status_reason_policy_definition"), dict),
            "WITNESS_ILLEGAL",
            "case435 target registry is malformed",
        )
        cached = self._target_registry_cache.get(id(registry))
        if cached is not None and cached[0] is registry:
            return cached[1]
        result = {
            "descriptors": self._index_records(
                registry.get("descriptors"), "field_id", 185, "field descriptor"
            ),
            "constraints": self._index_records(
                registry.get("ordered_value_constraint_definitions"),
                "value_constraint_id",
                17,
                "value constraint",
            ),
            "shapes": self._index_records(
                registry.get("ordered_value_shape_definitions"),
                "value_shape_id",
                6,
                "value shape",
            ),
            "vocabularies": self._index_records(
                registry.get("ordered_vocabulary_definitions"),
                "vocabulary_id",
                25,
                "vocabulary",
            ),
            "reasons": self._index_records(
                registry["status_reason_policy_definition"].get("reason_rules"),
                "reason",
                26,
                "status reason",
            ),
            "cross": self._index_records(
                registry.get("ordered_cross_field_constraint_definitions"),
                "cross_field_constraint_id",
                1,
                "cross-field constraint",
            ),
        }
        recomputed = self._record_identity(CASE435_TARGET_REGISTRY_TYPE, registry)
        _require(
            registry.get("target_field_registry_id") == recomputed,
            "WITNESS_ILLEGAL",
            "case435 target-registry identity does not recompute",
        )
        result["registry_id"] = recomputed
        self._target_registry_cache[id(registry)] = (registry, result)
        return result

    def _selected_union_payload(
        self, union_type_name, selected_value, owner_type_name=None, owner=None
    ):
        descriptor = self.unions.get(union_type_name)
        _require(
            descriptor is not None and isinstance(selected_value, dict),
            "WITNESS_ILLEGAL",
            f"case435 union is unresolved: {union_type_name}",
        )
        topology = descriptor["tagged_union_descriptor"]
        if topology["payload_binding_scope"] == "SELF_VALUE":
            payload = selected_value
        else:
            _require(
                topology["payload_binding_scope"] == "OWNER_MEMBER"
                and topology["payload_owner_type_name"] == owner_type_name
                and isinstance(owner, dict),
                "WITNESS_ILLEGAL",
                "case435 owner-scoped union binding differs",
            )
            payload = owner
            for member in topology["payload_typed_member_path"]:
                _require(
                    isinstance(payload, dict) and member in payload,
                    "WITNESS_ILLEGAL",
                    "case435 union payload path is unresolved",
                )
                payload = payload[member]
            _require(
                payload is selected_value,
                "WITNESS_ILLEGAL",
                "case435 owner-scoped union payload aliases a different value",
            )
        actual = {}
        for discriminator in topology["ordered_discriminator_descriptors"]:
            root = (
                selected_value
                if discriminator["discriminator_scope"] == "SELECTED_VALUE"
                else owner
            )
            _require(
                isinstance(root, dict),
                "WITNESS_ILLEGAL",
                "case435 union discriminator owner differs",
            )
            value = root
            path = discriminator["discriminator_typed_member_path"]
            for member in path:
                _require(
                    isinstance(value, dict) and member in value,
                    "WITNESS_ILLEGAL",
                    "case435 union discriminator path is unresolved",
                )
                value = value[member]
            _require(
                isinstance(value, str),
                "WITNESS_ILLEGAL",
                "case435 union discriminator is not text",
            )
            actual[path[-1]] = value
        matches = [
            row
            for row in topology["ordered_alternatives"]
            if {
                literal["member_name"]: literal["text_value"]
                for literal in row["ordered_discriminator_literals"]
            }
            == actual
        ]
        _require(
            len(matches) == 1,
            "WITNESS_ILLEGAL",
            "case435 union alternative is missing or ambiguous",
        )
        return matches[0], payload

    def checkpoint_selector_intrinsic_valid(self, selector):
        _require(
            isinstance(selector, dict),
            "WITNESS_ILLEGAL",
            "case435 selector is not an object",
        )
        operation = selector.get("operation_kind")
        entries = selector.get("ordered_entries")
        declared_length = selector.get("selector_length")
        declared_ids = selector.get("ordered_checkpoint_selector_entry_ids")
        _require(
            isinstance(entries, list)
            and isinstance(declared_ids, list)
            and len(entries) <= 64
            and len(declared_ids) <= 64,
            "WITNESS_ILLEGAL",
            "case435 selector arrays differ",
        )
        order = CASE435_SELECTOR_MARKER_ORDER_BY_OPERATION.get(operation)
        _require(
            order is not None,
            "WITNESS_ILLEGAL",
            "case435 selector operation is unresolved",
        )
        ranks = {marker: rank for rank, marker in enumerate(order)}
        last_rank = -1
        last_occurrence = {}
        coordinates = set()
        recomputed_ids = []
        for ordinal, entry in enumerate(entries, 1):
            _require(
                isinstance(entry, dict),
                "WITNESS_ILLEGAL",
                "case435 selector entry is not an object",
            )
            position = entry.get("selector_position")
            entry_operation = entry.get("operation_kind")
            marker = entry.get("checkpoint_marker_kind")
            occurrence = entry.get("occurrence_index_within_kind")
            _require(
                _is_int(position)
                and _is_int(occurrence)
                and isinstance(marker, str)
                and isinstance(entry_operation, str),
                "WITNESS_ILLEGAL",
                "case435 selector entry scalar differs",
            )
            if position != ordinal or entry_operation != operation:
                return False
            rank = ranks.get(marker)
            if rank is None or rank < last_rank:
                return False
            last_rank = rank
            coordinate = (marker, occurrence)
            if coordinate in coordinates or occurrence <= last_occurrence.get(marker, 0):
                return False
            coordinates.add(coordinate)
            last_occurrence[marker] = occurrence
            recomputed_ids.append(
                self._record_identity("CheckpointSelectorEntryV1", entry)
            )
        return declared_length == len(entries) and declared_ids == recomputed_ids

    def checkpoint_selector_marker_contract_admitted(self, selector, marker_contract):
        _require(
            isinstance(selector, dict) and isinstance(marker_contract, dict),
            "WITNESS_ILLEGAL",
            "case435 selector/marker authority differs",
        )
        records = marker_contract.get("ordered_checkpoint_operation_records")
        full_markers = marker_contract.get("ordered_full_checkpoint_marker_kinds")
        forbidden = marker_contract.get("forbidden_full_checkpoint_marker_kinds")
        maximum = marker_contract.get("maximum_checkpoint_selector_length")
        entries = selector.get("ordered_entries")
        selector_length = selector.get("selector_length")
        operation = selector.get("operation_kind")
        record_index = self._index_records(
            records, "checkpoint_marker_kind", 13, "marker contract"
        )
        _require(
            isinstance(full_markers, list)
            and isinstance(forbidden, list)
            and isinstance(entries, list)
            and _is_int(maximum)
            and _is_int(selector_length)
            and len(full_markers) == len(set(full_markers)) == 13
            and set(full_markers) == set(record_index)
            and not set(full_markers) & set(forbidden),
            "WITNESS_ILLEGAL",
            "case435 marker contract is inconsistent",
        )
        if selector_length > maximum:
            return False
        for entry in entries:
            _require(
                isinstance(entry, dict),
                "WITNESS_ILLEGAL",
                "case435 selector entry is malformed",
            )
            record = record_index.get(entry.get("checkpoint_marker_kind"))
            _require(
                record is not None
                and isinstance(record.get("applicable_operation_kinds"), list)
                and record["applicable_operation_kinds"],
                "WITNESS_ILLEGAL",
                "case435 marker authority row is unresolved",
            )
            if operation not in record["applicable_operation_kinds"]:
                return False
        return True

    @staticmethod
    def field_observation_intrinsic_valid(field):
        _require(
            isinstance(field, dict),
            "WITNESS_ILLEGAL",
            "case435 field observation is not an object",
        )
        availability = field.get("availability")
        value = field.get("value")
        method = field.get("observation_method")
        attempt = field.get("observation_attempt")
        span_status = field.get("adapter_span_status")
        started = field.get("observation_started_offset_nanoseconds")
        completed = field.get("observation_completed_offset_nanoseconds")
        reason = field.get("unavailable_reason")
        censoring = field.get("censoring")
        errno_number = field.get("source_errno_number")
        errno_name = field.get("source_errno_name")
        failure_phase = field.get("source_failure_phase")
        error_class = field.get("source_error_class")
        error_digest = field.get("source_error_detail_sha256")
        span_valid = (
            span_status == "AVAILABLE"
            and _is_int(started)
            and _is_int(completed)
            and started <= completed
        ) or (span_status != "AVAILABLE" and started is None and completed is None)
        if not span_valid or (errno_number is None) != (errno_name is None):
            return False
        if (error_class is None) != (error_digest is None):
            return False
        source_absent = all(
            child is None
            for child in (errno_number, errno_name, error_class, error_digest)
        )
        if not (
            (attempt == "ATTEMPTED" and method != "NOT_ATTEMPTED")
            or (attempt == "NOT_ATTEMPTED" and method == "NOT_ATTEMPTED")
        ):
            return False
        if availability in {"AVAILABLE", "CENSORED"}:
            if (
                value is None
                or attempt != "ATTEMPTED"
                or method == "NOT_ATTEMPTED"
                or span_status != "AVAILABLE"
                or reason is not None
                or failure_phase != "NONE"
                or not source_absent
            ):
                return False
            if availability == "AVAILABLE":
                return censoring == "NONE" and (
                    not isinstance(value, dict)
                    or value.get("kind") != "DURATION_BOUND"
                    or value.get("relation") == "EXACT"
                )
            relations = {
                "LEFT": "UPPER_BOUND",
                "RIGHT": "LOWER_BOUND",
                "INTERVAL": "INTERVAL",
            }
            return (
                isinstance(value, dict)
                and value.get("kind") == "DURATION_BOUND"
                and censoring in relations
                and value.get("relation") == relations[censoring]
            )
        if availability == "NOT_APPLICABLE":
            return (
                value is None
                and reason
                in {
                    "NOT_APPLICABLE_TO_OPERATION",
                    "NOT_APPLICABLE_TO_REACHED_STATE",
                }
                and method == "NOT_ATTEMPTED"
                and attempt == "NOT_ATTEMPTED"
                and span_status == "NOT_APPLICABLE"
                and censoring == "NONE"
                and failure_phase == "NONE"
                and source_absent
            )
        if availability == "UNAVAILABLE":
            return value is None and reason is not None and censoring == "NONE"
        return False

    @staticmethod
    def source_error_detail_id_recomputes_from_field(field):
        _require(
            isinstance(field, dict),
            "WITNESS_ILLEGAL",
            "case435 source-error field differs",
        )
        error_class = field.get("source_error_class")
        supplied = field.get("source_error_detail_sha256")
        if error_class is None:
            return supplied is None
        payload = {
            "field_id": field.get("field_id"),
            "observation_method": field.get("observation_method"),
            "source_failure_phase": field.get("source_failure_phase"),
            "source_errno_number": field.get("source_errno_number"),
            "source_errno_name": field.get("source_errno_name"),
            "source_error_class": error_class,
        }
        preimage = _canonical_bytes(
            {
                "canonicalization_version": "riskyieldmm_canonical_json_v1",
                "domain": CASE435_SOURCE_ERROR_DETAIL_DOMAIN,
                "payload": payload,
                "schema_version": "riskyieldmm_physical_transport_a2m_raw_v49f_v8",
            }
        )
        _require(
            len(preimage) <= CASE435_SOURCE_ERROR_DETAIL_CANONICAL_OCTET_LIMIT,
            "AUTHORITY_INVALID",
            "case435 source-error preimage exceeds its frozen limit",
        )
        return supplied == _sha256(preimage)

    def _resolve_descriptor(self, field, descriptor, registry, indexes):
        _require(
            isinstance(field, dict)
            and isinstance(descriptor, dict)
            and isinstance(registry, dict)
            and isinstance(field.get("field_id"), str),
            "WITNESS_ILLEGAL",
            "case435 field/descriptor authority differs",
        )
        resolved = indexes["descriptors"].get(field["field_id"])
        _require(
            resolved is not None and self._exact_equal(resolved, descriptor),
            "WITNESS_ILLEGAL",
            "case435 explicit field descriptor is unresolved",
        )
        _require(
            field.get("target_field_registry_id") == indexes["registry_id"],
            "WITNESS_ILLEGAL",
            "case435 field names a different target registry",
        )
        return resolved

    @staticmethod
    def _vocabulary_members(vocabulary_id, indexes):
        vocabulary = indexes["vocabularies"].get(vocabulary_id)
        members = None if vocabulary is None else vocabulary.get("members")
        _require(
            isinstance(members, list)
            and len(members) <= 32
            and all(isinstance(member, str) for member in members)
            and len(members) == len(set(members)),
            "WITNESS_ILLEGAL",
            "case435 vocabulary authority is unresolved",
        )
        return members

    def _scalar_constraint_valid(self, value, constraint, indexes):
        profile = constraint.get("scalar_profile")
        kind = constraint.get("value_kind")
        if profile == "EXACT_BOOL":
            _require(
                kind == "BOOL",
                "AUTHORITY_INVALID",
                "case435 Boolean constraint kind differs",
            )
            return type(value) is bool
        if profile == "SAFE_IJSON_UINT":
            _require(
                kind in {"UINT", "OPTIONAL_UINT"}
                and _is_int(constraint.get("integer_minimum"))
                and _is_int(constraint.get("integer_maximum")),
                "AUTHORITY_INVALID",
                "case435 integer constraint differs",
            )
            return (
                _is_int(value)
                and constraint["integer_minimum"]
                <= value
                <= constraint["integer_maximum"]
            )
        if profile in {"ENUM", "PLATFORM_ERRNO", "SHA256", "UINT128_DECIMAL"}:
            _require(
                kind in {"TEXT", "OPTIONAL_TEXT"},
                "AUTHORITY_INVALID",
                "case435 text constraint kind differs",
            )
            if not isinstance(value, str):
                return False
            encoded_length = len(value.encode("utf-8"))
            minimum = constraint.get("text_minimum_utf8_bytes")
            maximum = constraint.get("text_maximum_utf8_bytes")
            if not (
                _is_int(minimum)
                and _is_int(maximum)
                and minimum <= encoded_length <= maximum
            ):
                return False
            if profile == "ENUM":
                return value in self._vocabulary_members(
                    constraint.get("vocabulary_id"), indexes
                )
            pattern = constraint.get("text_ascii_pattern")
            expected_pattern = {
                "PLATFORM_ERRNO": "[A-Z][A-Z0-9_]{0,63}",
                "SHA256": "[0-9a-f]{64}",
                "UINT128_DECIMAL": "0|[1-9][0-9]*",
            }[profile]
            _require(
                pattern == expected_pattern,
                "AUTHORITY_INVALID",
                "case435 text pattern differs",
            )
            if profile == "PLATFORM_ERRNO":
                if not (
                    value
                    and "A" <= value[0] <= "Z"
                    and all(
                        "A" <= character <= "Z"
                        or "0" <= character <= "9"
                        or character == "_"
                        for character in value[1:]
                    )
                ):
                    return False
            elif profile == "SHA256":
                if len(value) != 64 or any(
                    character not in "0123456789abcdef" for character in value
                ):
                    return False
            elif not (
                value == "0"
                or (
                    value
                    and "1" <= value[0] <= "9"
                    and all("0" <= character <= "9" for character in value[1:])
                )
            ):
                return False
            if profile == "UINT128_DECIMAL":
                decimal_maximum = constraint.get("decimal_maximum")
                _require(
                    isinstance(decimal_maximum, str),
                    "AUTHORITY_INVALID",
                    "case435 uint128 maximum is unresolved",
                )
                return len(value) < len(decimal_maximum) or (
                    len(value) == len(decimal_maximum) and value <= decimal_maximum
                )
            return True
        _reject(
            "AUTHORITY_INVALID",
            f"case435 scalar constraint profile is unsupported: {profile}",
        )

    def target_value_satisfies_descriptor(self, field, descriptor, registry):
        indexes = self._target_indexes(registry)
        resolved = self._resolve_descriptor(field, descriptor, registry, indexes)
        value = field.get("value")
        if value is None:
            return True
        alternative, payload = self._selected_union_payload(
            "CapacityMeasurementTargetValue", value
        )
        expected_kind = resolved.get("value_kind")
        _require(
            alternative["alternative_name"] == expected_kind,
            "WITNESS_ILLEGAL",
            "case435 target-value alternative differs from its descriptor",
        )
        constraint_id = resolved.get("value_constraint_id")
        constraint = indexes["constraints"].get(constraint_id)
        _require(
            constraint is not None and constraint.get("value_kind") == expected_kind,
            "AUTHORITY_INVALID",
            "case435 target-value constraint is unresolved",
        )
        shape = indexes["shapes"].get(resolved.get("value_shape_id"))
        _require(
            shape is not None,
            "AUTHORITY_INVALID",
            "case435 target-value shape is unresolved",
        )
        expected_container = (
            "FIXED_MAP"
            if expected_kind == "FIXED_UINT_MAP"
            else "LIST"
            if expected_kind in {"UINT_LIST", "TEXT_LIST"}
            else "SCALAR"
        )
        _require(
            shape.get("container_kind") == expected_container,
            "AUTHORITY_INVALID",
            "case435 target-value container differs",
        )
        collection_kinds = {"UINT_LIST", "TEXT_LIST", "FIXED_UINT_MAP"}
        item_constraint_id = constraint.get("collection_item_constraint_id")
        if expected_kind in collection_kinds:
            item_constraint = indexes["constraints"].get(item_constraint_id)
            expected_item_kind = "TEXT" if expected_kind == "TEXT_LIST" else "UINT"
            _require(
                isinstance(item_constraint_id, str)
                and item_constraint is not None
                and item_constraint_id != constraint_id
                and item_constraint.get("collection_item_constraint_id") is None
                and item_constraint.get("value_kind") == expected_item_kind,
                "AUTHORITY_INVALID",
                "case435 collection item constraint differs",
            )
        else:
            _require(
                item_constraint_id is None,
                "AUTHORITY_INVALID",
                "case435 scalar constraint names a collection item",
            )
            item_constraint = None
        if expected_kind == "DURATION_BOUND":
            _require(
                constraint.get("scalar_profile") == "DURATION_BOUND",
                "AUTHORITY_INVALID",
                "case435 duration constraint differs",
            )
            relation = payload.get("relation")
            lower = payload.get("lower_nanoseconds")
            upper = payload.get("upper_nanoseconds")
            relation_valid = {
                "EXACT": _is_int(lower) and _is_int(upper) and lower == upper,
                "LOWER_BOUND": _is_int(lower) and upper is None,
                "UPPER_BOUND": lower is None and _is_int(upper),
                "INTERVAL": _is_int(lower) and _is_int(upper) and lower <= upper,
            }.get(relation, False)
            if not relation_valid:
                return False
            minimum = constraint.get("integer_minimum")
            maximum = constraint.get("integer_maximum")
            _require(
                _is_int(minimum) and _is_int(maximum),
                "AUTHORITY_INVALID",
                "case435 duration bounds differ",
            )
            return all(
                endpoint is None
                or (_is_int(endpoint) and minimum <= endpoint <= maximum)
                for endpoint in (lower, upper)
            )
        if expected_kind in {"BOOL", "UINT", "TEXT"}:
            return self._scalar_constraint_valid(
                payload.get("value"), constraint, indexes
            )
        if expected_kind in {"OPTIONAL_UINT", "OPTIONAL_TEXT"}:
            present = payload.get("present")
            scalar = payload.get("value")
            if type(present) is not bool or present != (scalar is not None):
                return False
            return scalar is None or self._scalar_constraint_valid(
                scalar, constraint, indexes
            )
        if expected_kind in {"UINT_LIST", "TEXT_LIST"}:
            values = payload.get("values")
            _require(
                isinstance(values, list),
                "WITNESS_ILLEGAL",
                "case435 target list is not an array",
            )
            minimum = shape.get("minimum_items")
            maximum = shape.get("maximum_items")
            _require(
                _is_int(minimum) and _is_int(maximum) and item_constraint is not None,
                "AUTHORITY_INVALID",
                "case435 target-list shape differs",
            )
            return minimum <= len(values) <= maximum and all(
                self._scalar_constraint_valid(item, item_constraint, indexes)
                for item in values
            )
        if expected_kind == "FIXED_UINT_MAP":
            ordered = payload.get("ordered")
            _require(
                isinstance(ordered, list),
                "WITNESS_ILLEGAL",
                "case435 fixed map is not an array",
            )
            expected_keys = resolved.get("value_shape_keys")
            shape_keys = shape.get("ordered_keys")
            minimum = shape.get("minimum_items")
            maximum = shape.get("maximum_items")
            _require(
                isinstance(expected_keys, list)
                and expected_keys == shape_keys
                and _is_int(minimum)
                and _is_int(maximum)
                and item_constraint is not None,
                "AUTHORITY_INVALID",
                "case435 fixed-map authority differs",
            )
            if not minimum <= len(ordered) <= maximum:
                return False
            actual_keys = []
            for entry in ordered:
                _require(
                    isinstance(entry, dict),
                    "WITNESS_ILLEGAL",
                    "case435 fixed-map entry differs",
                )
                actual_keys.append(entry.get("key"))
                if not self._scalar_constraint_valid(
                    entry.get("value"), item_constraint, indexes
                ):
                    return False
            return actual_keys == expected_keys
        _reject(
            "AUTHORITY_INVALID",
            f"case435 target-value kind is unsupported: {expected_kind}",
        )

    def field_observation_satisfies_descriptor_policy(
        self, field, descriptor, registry
    ):
        indexes = self._target_indexes(registry)
        resolved = self._resolve_descriptor(field, descriptor, registry, indexes)
        status_policy = registry.get("status_reason_policy_definition")
        _require(
            isinstance(status_policy, dict)
            and resolved.get("status_reason_policy_id")
            == status_policy.get("status_reason_policy_id"),
            "AUTHORITY_INVALID",
            "case435 status-reason policy differs",
        )
        reason = field.get("unavailable_reason")
        allowed = resolved.get("allowed_status_reasons")
        _require(
            isinstance(allowed, list),
            "AUTHORITY_INVALID",
            "case435 allowed-reason authority differs",
        )
        if reason is not None and reason not in allowed:
            return False
        if field.get("availability") == "CENSORED" and not resolved.get(
            "censoring_allowed"
        ):
            return False
        if reason is None:
            return True
        reason_rule = indexes["reasons"].get(reason)
        _require(
            reason_rule is not None,
            "AUTHORITY_INVALID",
            "case435 reason rule is unresolved",
        )
        if reason_rule.get("required_availability") != field.get("availability"):
            return False
        attempt_rows = reason_rule.get("attempt_state_error_forms")
        _require(
            isinstance(attempt_rows, list) and 1 <= len(attempt_rows) <= 2,
            "AUTHORITY_INVALID",
            "case435 attempt-state authority differs",
        )
        matches = [
            row
            for row in attempt_rows
            if isinstance(row, dict)
            and row.get("attempt_state") == field.get("observation_attempt")
        ]
        _require(
            len(matches) == 1,
            "AUTHORITY_INVALID",
            "case435 attempt state is missing or ambiguous",
        )
        row = matches[0]
        required_span = {
            "AVAILABLE_ONLY": "AVAILABLE",
            "NOT_APPLICABLE_ONLY": "NOT_APPLICABLE",
            "UNAVAILABLE_ONLY": "UNAVAILABLE",
        }.get(row.get("adapter_span_policy"))
        _require(
            required_span is not None,
            "AUTHORITY_INVALID",
            "case435 adapter-span policy is unresolved",
        )
        if field.get("adapter_span_status") != required_span:
            return False
        phases = row.get("permitted_failure_phases")
        forms = row.get("permitted_error_forms")
        _require(
            isinstance(phases, list) and isinstance(forms, list),
            "AUTHORITY_INVALID",
            "case435 error-form policy differs",
        )
        if field.get("source_failure_phase") not in phases:
            return False
        if field.get("source_errno_number") is not None:
            effective_form = "OS"
        elif field.get("source_error_class") is not None:
            effective_form = "NON_OS"
        elif "STATUS_ONLY" in forms:
            effective_form = "STATUS_ONLY"
        else:
            effective_form = "NONE"
        return effective_form in forms

    def v2_field_observation_context_valid(
        self, field, descriptor, registry, context, ordinal
    ):
        _require(
            isinstance(context, dict) and _is_int(ordinal) and ordinal >= 0,
            "WITNESS_ILLEGAL",
            "case435 field/context ordinal differs",
        )
        if ordinal >= 185:
            return False
        indexes = self._target_indexes(registry)
        resolved = self._resolve_descriptor(field, descriptor, registry, indexes)
        descriptors = registry["descriptors"]
        if not self._exact_equal(descriptors[ordinal], resolved):
            return False
        if (
            field.get("field_id") != resolved.get("field_id")
            or field.get("target_field_registry_id")
            != context.get("target_field_registry_id")
            or context.get("target_field_registry_id") != indexes["registry_id"]
            or field.get("observation_context_id")
            != context.get("observation_context_id")
        ):
            return False
        binding_reason = context.get("checkpoint_binding_unavailable_reason")
        placeholder_reason = CASE435_PLACEHOLDER_FIELD_REASON_BY_CONTEXT_REASON.get(
            binding_reason
        )
        if placeholder_reason is not None:
            return (
                field.get("availability") == "UNAVAILABLE"
                and field.get("value") is None
                and field.get("unavailable_reason") == placeholder_reason
                and field.get("observation_method") == "NOT_ATTEMPTED"
                and field.get("observation_attempt") == "NOT_ATTEMPTED"
                and field.get("adapter_span_status") == "NOT_APPLICABLE"
                and field.get("observation_started_offset_nanoseconds") is None
                and field.get("observation_completed_offset_nanoseconds") is None
                and field.get("censoring") == "NONE"
                and field.get("source_failure_phase") == "NONE"
                and field.get("source_errno_number") is None
                and field.get("source_errno_name") is None
                and field.get("source_error_class") is None
                and field.get("source_error_detail_sha256") is None
            )
        if field.get("unavailable_reason") in CASE435_PLACEHOLDER_FIELD_REASONS:
            return False
        applicable = resolved.get("applicable_operation_kinds")
        _require(
            isinstance(applicable, list),
            "AUTHORITY_INVALID",
            "case435 descriptor operation authority differs",
        )
        if context.get("operation_kind") not in applicable:
            return (
                field.get("availability") == "NOT_APPLICABLE"
                and field.get("unavailable_reason") == "NOT_APPLICABLE_TO_OPERATION"
            )
        if field.get("unavailable_reason") == "NOT_APPLICABLE_TO_OPERATION":
            return False
        field_id = field.get("field_id")
        if context.get("attempt_id") is None and field_id in CASE435_ATTEMPT_REQUIRED_FIELD_IDS:
            return (
                field.get("availability") == "NOT_APPLICABLE"
                and field.get("unavailable_reason")
                == "NOT_APPLICABLE_TO_REACHED_STATE"
            )
        if context.get("instrumentation_mode") == "OFF":
            if field_id in CASE435_OFF_STATIC_FIELD_IDS:
                if field.get("availability") != "AVAILABLE":
                    return False
            elif field_id == "freshness.analysis_pressure_episode_age_boottime_ns":
                if not (
                    field.get("availability") == "UNAVAILABLE"
                    and field.get("unavailable_reason") == "NO_FROZEN_PRESSURE_POLICY"
                ):
                    return False
            elif not (
                field.get("availability") == "UNAVAILABLE"
                and field.get("unavailable_reason") == "INSTRUMENTATION_DISABLED"
            ):
                return False
        elif field.get("unavailable_reason") == "INSTRUMENTATION_DISABLED":
            return False
        if field.get("observation_attempt") == "ATTEMPTED":
            method_rows = resolved.get("observation_method_role_pairs")
            _require(
                isinstance(method_rows, list) and len(method_rows) <= 2,
                "AUTHORITY_INVALID",
                "case435 method/role authority differs",
            )
            matches = [
                row
                for row in method_rows
                if isinstance(row, dict)
                and row.get("observation_method")
                == field.get("observation_method")
            ]
            _require(
                len(matches) == 1
                and isinstance(matches[0].get("allowed_roles"), list),
                "AUTHORITY_INVALID",
                "case435 observation method is unresolved",
            )
            if context.get("observation_role") not in matches[0]["allowed_roles"]:
                return False
            if context.get("observation_role") == "STABLE_CHECKPOINT":
                markers = resolved.get("allowed_checkpoint_marker_kinds")
                _require(
                    isinstance(markers, list),
                    "AUTHORITY_INVALID",
                    "case435 checkpoint-marker authority differs",
                )
                if context.get("checkpoint_marker_kind") not in markers:
                    return False
        if field.get("adapter_span_status") == "AVAILABLE":
            span = context.get("observer_clock_span")
            _require(
                isinstance(span, dict),
                "WITNESS_ILLEGAL",
                "case435 observer clock span differs",
            )
            values = (
                field.get("observation_started_offset_nanoseconds"),
                field.get("observation_completed_offset_nanoseconds"),
                span.get("started_offset_nanoseconds"),
                span.get("completed_offset_nanoseconds"),
            )
            if (
                span.get("span_status") != "AVAILABLE"
                or not all(_is_int(value) for value in values)
                or not values[2] <= values[0] <= values[1] <= values[3]
            ):
                return False
        return True

    def a1_fifo_fields_valid(self, fields, registry):
        _require(
            isinstance(fields, list) and len(fields) <= 185,
            "WITNESS_ILLEGAL",
            "case435 A1 field input differs",
        )
        indexes = self._target_indexes(registry)
        constraint = indexes["cross"].get(
            "A1_FIFO_SEQUENCE_KIND_LENGTH_AND_ORDER_V1"
        )
        _require(
            constraint is not None
            and all(
                constraint.get(key) == value
                for key, value in {
                    "activation_condition": "ALL_MEMBERS_AVAILABLE",
                    "cardinality_rule": "COUNT_EQUALS_BOTH_ARRAY_LENGTHS",
                    "maximum_items": 4,
                    "pairing_rule": "SAME_INDEX",
                    "sequence_order": "STRICTLY_INCREASING_UNIQUE",
                }.items()
            ),
            "AUTHORITY_INVALID",
            "case435 A1 FIFO authority differs",
        )
        by_id = {}
        for field in fields:
            _require(
                isinstance(field, dict)
                and isinstance(field.get("field_id"), str)
                and field["field_id"] not in by_id,
                "WITNESS_ILLEGAL",
                "case435 A1 field identifier differs",
            )
            by_id[field["field_id"]] = field
        ids = (
            constraint.get("count_field_id"),
            constraint.get("sequence_field_id"),
            constraint.get("kind_field_id"),
        )
        _require(
            all(identifier in by_id and identifier in indexes["descriptors"] for identifier in ids),
            "WITNESS_ILLEGAL",
            "case435 A1 field is unresolved",
        )
        count_field, sequence_field, kind_field = (by_id[identifier] for identifier in ids)
        if any(
            field.get("availability") != "AVAILABLE"
            for field in (count_field, sequence_field, kind_field)
        ):
            return True
        count_value = count_field.get("value")
        sequence_value = sequence_field.get("value")
        kind_value = kind_field.get("value")
        _require(
            isinstance(count_value, dict)
            and count_value.get("kind") == "UINT"
            and isinstance(sequence_value, dict)
            and sequence_value.get("kind") == "UINT_LIST"
            and isinstance(kind_value, dict)
            and kind_value.get("kind") == "TEXT_LIST",
            "WITNESS_ILLEGAL",
            "case435 A1 union alternatives differ",
        )
        count = count_value.get("value")
        sequences = sequence_value.get("values")
        kinds = kind_value.get("values")
        _require(
            _is_int(count) and isinstance(sequences, list) and isinstance(kinds, list),
            "WITNESS_ILLEGAL",
            "case435 A1 payload types differ",
        )
        return (
            count == len(sequences) == len(kinds)
            and len(sequences) <= constraint["maximum_items"]
            and all(
                _is_int(left) and _is_int(right) and left < right
                for left, right in zip(sequences, sequences[1:])
            )
        )

    def v2_root_sequence_selector_valid(self, root, observations, selector):
        _require(
            isinstance(root, dict)
            and isinstance(observations, list)
            and 1 <= len(observations) <= 67,
            "WITNESS_ILLEGAL",
            "case435 root/observation sequence differs",
        )
        if root.get("observation_count") != len(observations):
            return False
        recomputed_ids = []
        contexts = []
        for observation in observations:
            _require(
                isinstance(observation, dict)
                and isinstance(observation.get("observation_context"), dict),
                "WITNESS_ILLEGAL",
                "case435 observation/context differs",
            )
            recomputed = self._record_identity(CASE435_TYPE, observation)
            _require(
                observation.get("observation_id") == recomputed,
                "WITNESS_ILLEGAL",
                "case435 observation identity does not recompute",
            )
            recomputed_ids.append(recomputed)
            contexts.append(observation["observation_context"])
        _require(
            root.get("ordered_observation_ids") == recomputed_ids,
            "WITNESS_ILLEGAL",
            "case435 root observation IDs do not resolve",
        )
        for context in contexts:
            if any(
                context.get(member) != root.get(member)
                for member in (
                    "candidate_id",
                    "attempt_id",
                    "operation_kind",
                    "instrumentation_mode",
                    "target_field_registry_id",
                )
            ):
                return False
        if contexts[0].get("observation_role") == "STARTUP_RECOVERY":
            return (
                len(contexts) == 1
                and root.get("attempt_id") is None
                and root.get("full_checkpoint_selector_id") is None
                and selector is None
            )
        roles = [context.get("observation_role") for context in contexts]
        if not (
            len(roles) >= 3
            and roles[0] == "BEFORE_OPERATION"
            and roles[-2:] == ["AFTER_OPERATION", "OPERATION_AGGREGATE"]
            and all(role == "STABLE_CHECKPOINT" for role in roles[1:-2])
        ):
            return False
        selector_required = (
            root.get("instrumentation_mode") == "ON"
            and root.get("attempt_id") is not None
        )
        if not selector_required:
            return (
                len(contexts) == 3
                and root.get("full_checkpoint_selector_id") is None
                and selector is None
            )
        _require(
            isinstance(selector, dict),
            "WITNESS_ILLEGAL",
            "case435 attempted ON root requires a selector",
        )
        if not self.checkpoint_selector_intrinsic_valid(selector):
            return False
        selector_id = self._record_identity(CASE435_SELECTOR_TYPE, selector)
        _require(
            selector.get("checkpoint_selector_id") == selector_id,
            "WITNESS_ILLEGAL",
            "case435 selector identity does not recompute",
        )
        entries = selector.get("ordered_entries")
        if (
            selector.get("operation_kind") != root.get("operation_kind")
            or selector_id != root.get("full_checkpoint_selector_id")
            or not isinstance(entries, list)
            or len(contexts) != selector.get("selector_length", -1) + 3
        ):
            return False
        exact_ordinals = []
        for context, entry in zip(contexts[1:-2], entries):
            _require(
                isinstance(entry, dict),
                "WITNESS_ILLEGAL",
                "case435 selector entry differs",
            )
            if (
                context.get("full_checkpoint_selector_id") != selector_id
                or context.get("checkpoint_selector_position")
                != entry.get("selector_position")
                or context.get("checkpoint_selector_entry_id")
                != entry.get("checkpoint_selector_entry_id")
                or context.get("expected_checkpoint_marker_kind")
                != entry.get("checkpoint_marker_kind")
                or context.get("expected_occurrence_index_within_kind")
                != entry.get("occurrence_index_within_kind")
            ):
                return False
            if context.get("checkpoint_binding_status") == "EXACT_MARKER":
                marker_ordinal = context.get("marker_ordinal")
                if not _is_int(marker_ordinal):
                    return False
                exact_ordinals.append(marker_ordinal)
        return all(
            left < right for left, right in zip(exact_ordinals, exact_ordinals[1:])
        )

    def complex_operator(self, opcode, operands):
        dispatch = {
            "CHECKPOINT_SELECTOR_INTRINSIC_VALID": self.checkpoint_selector_intrinsic_valid,
            "CHECKPOINT_SELECTOR_MARKER_CONTRACT_ADMITTED": self.checkpoint_selector_marker_contract_admitted,
            "FIELD_OBSERVATION_INTRINSIC_VALID": self.field_observation_intrinsic_valid,
            "SOURCE_ERROR_DETAIL_ID_RECOMPUTES_FROM_FIELD": self.source_error_detail_id_recomputes_from_field,
            "TARGET_VALUE_SATISFIES_DESCRIPTOR": self.target_value_satisfies_descriptor,
            "FIELD_OBSERVATION_SATISFIES_DESCRIPTOR_POLICY": self.field_observation_satisfies_descriptor_policy,
            "V2_FIELD_OBSERVATION_CONTEXT_VALID": self.v2_field_observation_context_valid,
            "A1_FIFO_FIELDS_VALID": self.a1_fifo_fields_valid,
            "V2_ROOT_SEQUENCE_SELECTOR_VALID": self.v2_root_sequence_selector_valid,
        }
        function = dispatch.get(opcode)
        _require(
            function is not None,
            "AUTHORITY_INVALID",
            f"case435 complex operator is unsupported: {opcode}",
        )
        return function(*operands)

def _resolve_rule_path(root, path):
    value = root
    for member in path:
        _require(
            isinstance(value, dict) and member in value,
            "WITNESS_ILLEGAL",
            "intrinsic-rule input path is unresolved",
        )
        value = value[member]
    return value


def _operation_result_matches_case69_spec(result, signed_spec):
    _require(
        isinstance(result, dict) and isinstance(signed_spec, dict),
        "WITNESS_ILLEGAL",
        "result/spec operands require records",
    )
    result_kind = result.get("operation_kind")
    spec_kind = signed_spec.get("operation_kind")
    _require(
        type(result_kind) is str and type(spec_kind) is str,
        "WITNESS_ILLEGAL",
        "result/spec operation kind is not text",
    )
    if result_kind != spec_kind:
        return False
    _require(
        result_kind == "LOCAL_SHUTDOWN"
        and result.get("result_type") == "LOCAL_SHUTDOWN_RESULT_EVIDENCE_V2"
        and signed_spec.get("spec_type") == "LOCAL_SHUTDOWN_SPEC_V2",
        "AUTHORITY_INVALID",
        "V2 subset result/spec union matrix differs",
    )
    result_body = result.get("result")
    spec_body = signed_spec.get("spec")
    _require(
        isinstance(result_body, dict) and isinstance(spec_body, dict),
        "WITNESS_ILLEGAL",
        "local result/spec body is absent",
    )
    if result_body["terminal_outcome"] != spec_body["expected_terminal_outcome"]:
        return False
    limit_pairs = (
        ("final_terminal_ingress_batch_count", "maximum_terminal_ingress_batches"),
        (
            "final_terminal_ingress_ciphertext_octets",
            "maximum_terminal_ingress_ciphertext_octets",
        ),
        (
            "final_terminal_ingress_plaintext_octets",
            "maximum_terminal_ingress_plaintext_octets",
        ),
        (
            "final_terminal_socket_receive_call_count",
            "maximum_terminal_socket_receive_calls",
        ),
        ("final_terminal_tls_record_count", "maximum_terminal_tls_records"),
        (
            "final_terminal_tls_unwrap_iteration_count",
            "maximum_terminal_tls_unwrap_iterations",
        ),
        (
            "final_terminal_zero_progress_iteration_count",
            "maximum_terminal_zero_progress_iterations",
        ),
        (
            "final_terminal_ingress_parser_unit_count",
            "maximum_terminal_ingress_parser_units",
        ),
        (
            "final_terminal_ingress_automatic_output_count",
            "maximum_terminal_ingress_automatic_outputs",
        ),
        ("final_websocket_send_attempt_count", "maximum_websocket_send_attempts"),
        ("final_tls_control_send_attempt_count", "maximum_tls_control_send_attempts"),
        ("final_peer_shutdown_poll_count", "maximum_peer_shutdown_polls"),
    )
    if any(
        result_body[result_member] > spec_body[spec_member]
        for result_member, spec_member in limit_pairs
    ):
        return False
    return (
        len(result_body["ordered_terminal_ingress_read_attempt_event_ids"])
        <= spec_body["maximum_terminal_ingress_batches"]
        and len(result_body["ordered_terminal_parser_transition_event_ids"])
        <= spec_body["maximum_terminal_ingress_parser_units"]
    )


def _evaluate_subset_rule(
    indexes,
    rule_id,
    input_values,
    expected_types,
    expected_scope,
    complex_runtime=None,
):
    rule = indexes["rules"].get(rule_id)
    _require(rule is not None, "AUTHORITY_INVALID", "typed rule is unresolved")
    bindings = rule["ordered_rule_input_bindings"]
    _require(
        rule["rule_scope"] == expected_scope
        and isinstance(bindings, list)
        and len(bindings) == len(expected_types)
        and set(input_values) == set(expected_types)
        and all(binding["binding_name"] in expected_types for binding in bindings),
        "AUTHORITY_INVALID",
        "typed-rule input binding differs",
    )
    for binding in bindings:
        expected = expected_types[binding["binding_name"]]
        if isinstance(expected, str):
            expected_kind, expected_type = "RECORD", expected
        else:
            expected_kind, expected_type = expected
        _require(
            binding["binding_kind"] == expected_kind
            and binding["expected_type_name"] == expected_type,
            "AUTHORITY_INVALID",
            "typed-rule input binding kind/type differs",
        )
    results = []
    nodes = rule["ordered_expression_nodes"]
    _require(
        rule["maximum_expression_nodes"] == len(nodes),
        "AUTHORITY_INVALID",
        "typed-rule expression count differs",
    )
    for position, node in enumerate(nodes, 1):
        _require(
            node["expression_position"] == position
            and all(
                _is_int(operand) and 1 <= operand < position
                for operand in node["ordered_operand_positions"]
            ),
            "AUTHORITY_INVALID",
            "intrinsic-rule expression is not strict postorder",
        )
        operands = [results[operand - 1] for operand in node["ordered_operand_positions"]]
        opcode = node["operator"]
        if opcode == "INPUT_PATH":
            _require(
                node["input_binding_name"] in input_values and operands == [],
                "AUTHORITY_INVALID",
                "typed-rule input node differs",
            )
            result = _resolve_rule_path(
                input_values[node["input_binding_name"]], node["typed_member_path"]
            )
        elif opcode == "LITERAL":
            _require(
                operands == [] and node["input_binding_name"] is None,
                "AUTHORITY_INVALID",
                "typed-rule literal node differs",
            )
            result = node["literal_value"]
        elif opcode == "ARRAY_LENGTH":
            _require(len(operands) == 1 and isinstance(operands[0], list), "WITNESS_ILLEGAL", "array-length operand differs")
            result = len(operands[0])
        elif opcode == "SAFE_UINT_TO_INTERNAL_UINT128":
            _require(len(operands) == 1 and type(operands[0]) is int and 0 <= operands[0] <= U128_MAX, "WITNESS_ILLEGAL", "safe-uint conversion differs")
            result = operands[0]
        elif opcode in {"UINT128_ADD", "UINT128_MULTIPLY"}:
            _require(
                len(operands) == 2,
                "AUTHORITY_INVALID",
                "UInt128 rule arithmetic arity differs",
            )
            result = (
                _checked_add(*operands)
                if opcode == "UINT128_ADD"
                else _checked_mul(*operands)
            )
        elif opcode == "ARRAY_UNIQUE":
            _require(len(operands) == 1 and isinstance(operands[0], list), "WITNESS_ILLEGAL", "array-unique operand differs")
            encoded = [_canonical_bytes(value) for value in operands[0]]
            result = len(encoded) == len(set(encoded))
        elif opcode == "ARRAY_STRICT_ASCENDING":
            _require(len(operands) == 1 and isinstance(operands[0], list), "WITNESS_ILLEGAL", "array-order operand differs")
            result = all(
                type(left) is type(right)
                and type(left) in {int, str}
                and left < right
                for left, right in zip(operands[0], operands[0][1:])
            )
        elif opcode == "ARRAY_PROJECT_REQUIRED_MEMBER":
            _require(
                len(operands) == 1
                and isinstance(operands[0], list)
                and isinstance(node["typed_member_path"], list)
                and node["typed_member_path"],
                "AUTHORITY_INVALID",
                "array projection authority differs",
            )
            result = [
                _resolve_rule_path(item, node["typed_member_path"])
                for item in operands[0]
            ]
        elif opcode in {"EQ", "NE", "LE", "GE"}:
            _require(len(operands) == 2, "AUTHORITY_INVALID", "comparison arity differs")
            if opcode in {"EQ", "NE"}:
                equal = type(operands[0]) is type(operands[1]) and (
                    _canonical_bytes(operands[0]) == _canonical_bytes(operands[1])
                    if isinstance(operands[0], (dict, list))
                    else operands[0] == operands[1]
                )
                result = equal if opcode == "EQ" else not equal
            else:
                _require(
                    operands[0] is not None
                    and type(operands[0]) is type(operands[1])
                    and type(operands[0]) in {int, str},
                    "WITNESS_ILLEGAL",
                    "ordered comparison operands differ",
                )
                result = (
                    operands[0] <= operands[1]
                    if opcode == "LE"
                    else operands[0] >= operands[1]
                )
        elif opcode == "IS_NULL":
            _require(len(operands) == 1, "AUTHORITY_INVALID", "IS_NULL arity differs")
            result = operands[0] is None
        elif opcode == "NOT":
            _require(
                len(operands) == 1 and type(operands[0]) is bool,
                "AUTHORITY_INVALID",
                "NOT operand differs",
            )
            result = not operands[0]
        elif opcode in {"AND", "OR", "IMPLIES"}:
            _require(
                len(operands) == 2 and all(type(value) is bool for value in operands),
                "AUTHORITY_INVALID",
                "Boolean rule operands differ",
            )
            result = (
                operands[0] and operands[1]
                if opcode == "AND"
                else operands[0] or operands[1]
                if opcode == "OR"
                else (not operands[0]) or operands[1]
            )
        elif opcode == "PRESENT_EQ":
            _require(len(operands) == 2, "AUTHORITY_INVALID", "PRESENT_EQ arity differs")
            result = operands[0] is not None and type(operands[0]) is type(operands[1]) and operands[0] == operands[1]
        elif opcode == "PRESENT_LE":
            _require(len(operands) == 2, "AUTHORITY_INVALID", "PRESENT_LE arity differs")
            result = (
                operands[0] is not None
                and operands[1] is not None
                and type(operands[0]) is type(operands[1])
                and type(operands[0]) in {int, str}
                and operands[0] <= operands[1]
            )
        elif opcode == "FIELD_LAYER_EQUALS_UPPERCASE_FIELD_PREFIX":
            _require(
                len(operands) == 2 and all(isinstance(value, str) for value in operands),
                "WITNESS_ILLEGAL",
                "field-layer operator operands differ",
            )
            if operands[1].count(".") != 1:
                result = False
            else:
                prefix = operands[1].split(".", 1)[0]
                try:
                    result = prefix.encode("ascii").upper() == operands[0].encode("ascii")
                except UnicodeEncodeError:
                    result = False
        elif opcode == "OPERATION_RESULT_MATCHES_SIGNED_SPEC":
            _require(
                len(operands) == 2,
                "AUTHORITY_INVALID",
                "result/spec operator arity differs",
            )
            result = _operation_result_matches_case69_spec(*operands)
        elif complex_runtime is not None:
            result = complex_runtime.complex_operator(opcode, operands)
        else:
            _reject("AUTHORITY_INVALID", f"static subset rule opcode is unsupported: {opcode}")
        results.append(result)
    _require(
        rule["root_expression_position"] == len(results)
        and results
        and results[-1] is True,
        "WITNESS_ILLEGAL",
        f"typed rule is false: {rule_id}",
    )
    return len(nodes)


def _case435_apply_intrinsic_graph(
    indexes,
    runtime,
    type_name,
    value,
    owner=None,
    owner_type_name=None,
):
    descriptor = indexes["types"].get(type_name)
    _require(
        descriptor is not None,
        "AUTHORITY_INVALID",
        f"case435 intrinsic type is unresolved: {type_name}",
    )

    def walk_schema(schema_id, child, record_owner, record_owner_type):
        schema = indexes["schemas"].get(schema_id)
        _require(
            schema is not None,
            "AUTHORITY_INVALID",
            "case435 intrinsic schema is unresolved",
        )
        if child is None:
            return
        kind = schema["schema_kind"]
        if kind == "OBJECT_REF":
            _case435_apply_intrinsic_graph(
                indexes,
                runtime,
                schema["referenced_type_name"],
                child,
                record_owner,
                record_owner_type,
            )
        elif kind == "ARRAY":
            for item in child:
                walk_schema(
                    schema["array_item_value_schema_id"],
                    item,
                    record_owner,
                    record_owner_type,
                )

    if descriptor["type_form"] == "RECORD":
        for member in descriptor["record_member_descriptors"]:
            walk_schema(
                member["value_schema_id"], value[member["member_name"]], value, type_name
            )
    else:
        _require(
            descriptor["type_form"] == "TAGGED_UNION",
            "AUTHORITY_INVALID",
            "case435 intrinsic type form differs",
        )
        alternative, payload = runtime._selected_union_payload(
            type_name, value, owner_type_name, owner
        )
        _case435_apply_intrinsic_graph(
            indexes,
            runtime,
            alternative["referenced_type_name"],
            payload,
        )
    for rule_id in descriptor["ordered_intrinsic_rule_ids"]:
        _evaluate_subset_rule(
            indexes,
            rule_id,
            {"self": value},
            {"self": type_name},
            "INTRINSIC_RECORD",
            runtime,
        )


def _case435_validate_complete_record(indexes, runtime, type_name, value):
    _validate_subset_type(indexes, type_name, value)
    _case435_apply_intrinsic_graph(indexes, runtime, type_name, value)


def _execute_case435_p1(authorities, context):
    indexes = _registry_indexes(authorities["registry"])
    runtime = _Case435RuleRuntime(indexes)
    selector = context["selector"]
    marker_contract = context["marker_contract"]
    target_registry = context["target_registry"]
    root = context["root"]
    observations = context["observations"]
    for type_name, value in (
        (CASE435_SELECTOR_TYPE, selector),
        (CASE435_MARKER_CONTRACT_TYPE, marker_contract),
        (CASE435_TARGET_REGISTRY_TYPE, target_registry),
        (CASE435_ROOT_TYPE, root),
    ):
        _case435_validate_complete_record(indexes, runtime, type_name, value)
    for observation in observations:
        _case435_validate_complete_record(indexes, runtime, CASE435_TYPE, observation)

    descriptors = target_registry["descriptors"]
    _require(
        len(descriptors) == 185,
        "WITNESS_ILLEGAL",
        "case435 descriptor count differs",
    )

    def application_contract(application):
        return (
            application["application_kind"],
            application["evaluation_order"],
            application["iteration_ordinal_binding_name"],
            application["maximum_rule_evaluations"],
            application["requires_equal_cardinality"],
            tuple(
                (
                    row["tuple_position"],
                    row["binding_name"],
                    row["expected_type_name"],
                )
                for row in application["ordered_root_input_bindings"]
            ),
            tuple(
                (
                    row["binding_name"],
                    row["binding_mode"],
                    tuple(row["embedded_array_typed_member_path"]),
                    row["expected_item_type_name"],
                    row["fixed_position_resolver_profile_id"],
                    row["source_kind"],
                    row["source_root_binding_name"],
                )
                for row in application["ordered_sequence_input_bindings"]
            ),
        )

    lexical = "LEXICAL_APPLICATION_NAME_THEN_SEQUENCE_ORDINAL"
    fixed_observation_resolver = (
        "87224ef058fff2867da671aec58d53c0a06fc9542ae84ad0378af6db48349daf"
    )
    optional_selector_resolver = (
        "73acbeea28d638acb77aab44dad201e08cc5267e830ddd4714d54aa70813b54b"
    )
    expected_application_contracts = {
        "APPLY/SELECTOR_MARKER_CONTRACT_V1": (
            "RECORD_TUPLE",
            "SINGLE_EVALUATION",
            None,
            1,
            False,
            (
                (1, "selector", CASE435_SELECTOR_TYPE),
                (2, "marker_contract", CASE435_MARKER_CONTRACT_TYPE),
            ),
            (),
        ),
        "APPLY/V2_OBSERVATION_AGGREGATE_REGISTRY_V1": (
            "RECORD_TUPLE",
            "SINGLE_EVALUATION",
            None,
            1,
            False,
            (
                (1, "observation", CASE435_TYPE),
                (2, "target_registry", CASE435_TARGET_REGISTRY_TYPE),
            ),
            (),
        ),
        "APPLY/V2_OBSERVATION_FIELDS_REGISTRY_V1": (
            "ARRAY_EACH",
            lexical,
            "field_ordinal",
            185,
            True,
            (
                (1, "observation", CASE435_TYPE),
                (2, "target_registry", CASE435_TARGET_REGISTRY_TYPE),
            ),
            (
                (
                    "field_observation",
                    "ITERATED_RECORD",
                    ("field_observations",),
                    "TargetFieldObservationV1",
                    None,
                    "EMBEDDED_ARRAY",
                    "observation",
                ),
                (
                    "field_descriptor",
                    "ITERATED_RECORD",
                    ("descriptors",),
                    "CapacityMeasurementTargetFieldDescriptorV1",
                    None,
                    "EMBEDDED_ARRAY",
                    "target_registry",
                ),
            ),
        ),
        "APPLY/V2_ROOT_OBSERVATION_MEMBERSHIP_V1": (
            "FOR_EACH_FIXED_POSITION_BINDING",
            lexical,
            "observation_ordinal",
            67,
            False,
            ((1, "root", CASE435_ROOT_TYPE),),
            (
                (
                    "observation",
                    "ITERATED_RECORD",
                    (),
                    CASE435_TYPE,
                    fixed_observation_resolver,
                    "EXTERNAL_FIXED_SEQUENCE",
                    "root",
                ),
            ),
        ),
        "APPLY/V2_ROOT_SELECTOR_LIFECYCLE_V1": (
            "FIXED_SEQUENCE_AGGREGATE",
            "SINGLE_EVALUATION",
            None,
            1,
            False,
            ((1, "root", CASE435_ROOT_TYPE),),
            (
                (
                    "observations",
                    "COMPLETE_RECORD_SEQUENCE",
                    (),
                    CASE435_TYPE,
                    fixed_observation_resolver,
                    "EXTERNAL_FIXED_SEQUENCE",
                    "root",
                ),
                (
                    "selector",
                    "OPTIONAL_RECORD",
                    (),
                    CASE435_SELECTOR_TYPE,
                    optional_selector_resolver,
                    "EXTERNAL_FIXED_SEQUENCE",
                    "root",
                ),
            ),
        ),
    }
    actual_application_rows = []
    for name, application_id, rule_id, count, ordinal_program in CASE435_APPLICATIONS:
        application = indexes["applications"].get(name)
        _require(
            application is not None
            and application["rule_application_id"] == application_id
            and application["rule_id"] == rule_id
            and application_contract(application)
            == expected_application_contracts[name],
            "AUTHORITY_INVALID",
            f"case435 application authority differs: {name}",
        )
        actual_application_rows.append((name, count, ordinal_program))
    _require(
        actual_application_rows
        == [(name, count, program) for name, _, _, count, program in CASE435_APPLICATIONS],
        "AUTHORITY_INVALID",
        "case435 application order differs",
    )

    evaluations = 0
    direct_nodes = 0

    def evaluate(rule_id, values, types):
        nonlocal evaluations, direct_nodes
        direct_nodes += _evaluate_subset_rule(
            indexes,
            rule_id,
            values,
            types,
            "CROSS_RECORD",
            runtime,
        )
        evaluations += 1

    evaluate(
        CASE435_APPLICATIONS[0][2],
        {"selector": selector, "marker_contract": marker_contract},
        {"selector": CASE435_SELECTOR_TYPE, "marker_contract": CASE435_MARKER_CONTRACT_TYPE},
    )
    for observation in observations:
        evaluate(
            CASE435_APPLICATIONS[1][2],
            {"observation": observation, "target_registry": target_registry},
            {"observation": CASE435_TYPE, "target_registry": CASE435_TARGET_REGISTRY_TYPE},
        )
    for observation in observations:
        fields = observation["field_observations"]
        _require(
            isinstance(fields, list) and len(fields) == len(descriptors) == 185,
            "WITNESS_ILLEGAL",
            "case435 observation field/descriptor cardinality differs",
        )
        for ordinal, (field, descriptor) in enumerate(zip(fields, descriptors)):
            evaluate(
                CASE435_APPLICATIONS[2][2],
                {
                    "observation": observation,
                    "target_registry": target_registry,
                    "field_observation": field,
                    "field_descriptor": descriptor,
                    "field_ordinal": ordinal,
                },
                {
                    "observation": CASE435_TYPE,
                    "target_registry": CASE435_TARGET_REGISTRY_TYPE,
                    "field_observation": "TargetFieldObservationV1",
                    "field_descriptor": "CapacityMeasurementTargetFieldDescriptorV1",
                    "field_ordinal": ("SAFE_UINT", None),
                },
            )
    for ordinal, observation in enumerate(observations):
        evaluate(
            CASE435_APPLICATIONS[3][2],
            {
                "root": root,
                "observation": observation,
                "observation_ordinal": ordinal,
            },
            {
                "root": CASE435_ROOT_TYPE,
                "observation": CASE435_TYPE,
                "observation_ordinal": ("SAFE_UINT", None),
            },
        )
    evaluate(
        CASE435_APPLICATIONS[4][2],
        {"root": root, "observations": observations, "selector": selector},
        {
            "root": CASE435_ROOT_TYPE,
            "observations": ("FIXED_RECORD_SEQUENCE", CASE435_TYPE),
            "selector": ("OPTIONAL_FIXED_RECORD", CASE435_SELECTOR_TYPE),
        },
    )
    _require(
        evaluations == CASE435_RULE_EVALUATION_COUNT
        and direct_nodes == CASE435_DIRECT_EXPRESSION_NODE_COUNT,
        "DERIVATION_INVALID",
        "case435 completed P1 work differs from the frozen schedule",
    )
    context["p1_execution"] = {
        "application_invocation_count": CASE435_APPLICATION_INVOCATION_COUNT,
        "charged_rule_evaluation_count": evaluations,
        "completed_rule_evaluation_count": evaluations,
        "direct_expression_node_count": direct_nodes,
    }


def _validate_typed_legality(authorities, case, witness, context):
    case_position = case["case_position"]
    if case_position == CASE5_POSITION:
        _require(
            set(witness) == {"kind", "value"}
            and type(witness["kind"]) is str
            and type(witness["value"]) is bool,
            "WITNESS_ILLEGAL",
            "case 5 witness differs from its exact record shape",
        )
        return
    indexes = _registry_indexes(authorities["registry"])
    if case_position == CASE24_POSITION:
        _validate_subset_type(indexes, CASE24_OWNER_TYPE, context["owner"])
        _evaluate_subset_rule(
            indexes,
            CASE24_INTRINSIC_RULE,
            {"self": witness},
            {"self": CASE24_BODY_TYPE},
            "INTRINSIC_RECORD",
        )
        return
    if case_position == CASE54_POSITION:
        _validate_subset_type(indexes, CASE54_TYPE, witness)
        _evaluate_subset_rule(
            indexes,
            CASE54_INTRINSIC_RULE,
            {"self": witness},
            {"self": CASE54_TYPE},
            "INTRINSIC_RECORD",
        )
        return
    if case_position == CASE69_POSITION:
        signed_spec = context["signed_spec"]
        _validate_subset_type(indexes, CASE69_TYPE, witness)
        _validate_subset_type(indexes, CASE69_SPEC_TYPE, signed_spec)
        _evaluate_subset_rule(
            indexes,
            CASE69_RESULT_INTRINSIC_RULE,
            {"self": witness["result"]},
            {"self": CASE69_BODY_TYPE},
            "INTRINSIC_RECORD",
        )
        _evaluate_subset_rule(
            indexes,
            CASE69_SPEC_INTRINSIC_RULE,
            {"self": signed_spec["spec"]},
            {"self": CASE69_SPEC_BODY_TYPE},
            "INTRINSIC_RECORD",
        )
        _evaluate_subset_rule(
            indexes,
            CASE69_CROSS_RULE,
            {"result": witness, "signed_spec": signed_spec},
            {"result": CASE69_TYPE, "signed_spec": CASE69_SPEC_TYPE},
            "CROSS_RECORD",
        )
        return
    if case_position == CASE435_POSITION:
        _execute_case435_p1(authorities, context)
        return
    _reject("UNSUPPORTED_CASE", "typed-legality packet is not implemented")


def _seed_identity_contract(seed, identity_name):
    matches = [
        row
        for row in seed["ordered_identity_domain_records"]
        if row["identity_name"] == identity_name
    ]
    _require(
        len(matches) == 1,
        "AUTHORITY_INVALID",
        f"identity contract is absent or ambiguous: {identity_name}",
    )
    return matches[0]


def _validate_seed_identity_record(seed, identity_name, record, identity_field):
    contract = _seed_identity_contract(seed, identity_name)
    names = contract["ordered_payload_member_names"]
    _closed(record, [*names, identity_field], f"{identity_name} record")
    payload = {name: record[name] for name in names}
    _require(
        record[identity_field]
        == _seed_semantic_id(seed, contract["domain_literal"], payload),
        "AUTHORITY_INVALID",
        f"{identity_name} semantic identity differs",
    )
    return contract


def _reseal_typed_record(indexes, type_name, record):
    descriptor = indexes["types"].get(type_name)
    _require(
        descriptor is not None
        and descriptor["type_form"] == "RECORD"
        and isinstance(descriptor["identity_field"], str),
        "AUTHORITY_INVALID",
        f"typed identity descriptor differs: {type_name}",
    )
    sealed = dict(record)
    payload = {
        name: sealed[name] for name in descriptor["identity_payload_member_order"]
    }
    sealed[descriptor["identity_field"]] = _sha256(
        _canonical_bytes(
            {
                "canonicalization_version": sealed["canonicalization_version"],
                "domain": descriptor["described_record_domain"],
                "payload": payload,
                "schema_version": sealed["measurement_schema_version"],
            }
        )
    )
    return sealed


def _validate_local_result_with_outer_codec_mask(indexes, value):
    descriptor = indexes["types"].get(CASE475_TYPE)
    _require(
        descriptor is not None
        and descriptor["type_form"] == "RECORD"
        and descriptor["codec_byte_bound_relation"] == "LT"
        and descriptor["codec_octet_limit"] == 524_288,
        "AUTHORITY_INVALID",
        "local outer-codec authority differs",
    )
    _require(
        isinstance(value, dict)
        and set(value)
        == {row["member_name"] for row in descriptor["record_member_descriptors"]},
        "WITNESS_ILLEGAL",
        "local prospective result members differ",
    )
    for row in descriptor["record_member_descriptors"]:
        _validate_subset_schema(
            indexes,
            row["value_schema_id"],
            value[row["member_name"]],
            value,
            CASE475_TYPE,
        )
    payload = {
        name: value[name] for name in descriptor["identity_payload_member_order"]
    }
    _require(
        value["record_domain"] == descriptor["described_record_domain"]
        and value[descriptor["identity_field"]]
        == _sha256(
            _canonical_bytes(
                {
                    "canonicalization_version": value["canonicalization_version"],
                    "domain": descriptor["described_record_domain"],
                    "payload": payload,
                    "schema_version": value["measurement_schema_version"],
                }
            )
        ),
        "WITNESS_ILLEGAL",
        "local prospective result identity differs",
    )


def _local_eval_u128(expression, parameters):
    _require(
        isinstance(expression, dict) and isinstance(expression.get("opcode"), str),
        "DERIVATION_INVALID",
        "local UInt128 expression differs",
    )
    opcode = expression["opcode"]
    if opcode == "CONST_U128":
        _closed(expression, ["opcode", "value"], "local UInt128 constant")
        return _u128(expression["value"], "local UInt128 constant")
    if opcode == "PARAM_U128":
        _closed(
            expression,
            ["opcode", "parameter_name"],
            "local UInt128 parameter",
        )
        name = expression["parameter_name"]
        _require(
            isinstance(name, str) and name in parameters,
            "DERIVATION_INVALID",
            "local UInt128 parameter is unresolved",
        )
        return _u128(parameters[name], f"local parameter {name}")
    _require(
        opcode in {"CHECKED_ADD", "CHECKED_MUL"},
        "DERIVATION_INVALID",
        f"local UInt128 opcode is unsupported: {opcode}",
    )
    _closed(expression, ["opcode", "ordered_operands"], "local UInt128 operation")
    operands = expression["ordered_operands"]
    _require(
        isinstance(operands, list) and operands,
        "DERIVATION_INVALID",
        "local UInt128 operands differ",
    )
    values = [_local_eval_u128(child, parameters) for child in operands]
    return _checked_add(*values) if opcode == "CHECKED_ADD" else _checked_mul(*values)


def _local_relations_hold(local, spec_body):
    records = local["ordered_intrinsic_affine_relation_records"]
    _require(
        isinstance(records, list) and len(records) == 5,
        "AUTHORITY_INVALID",
        "local intrinsic-relation cardinality differs",
    )
    for position, record in enumerate(records, 1):
        _require(
            record["relation_position"] == position,
            "AUTHORITY_INVALID",
            "local intrinsic-relation order differs",
        )
        program = record["relation_program"]
        _closed(
            program,
            [
                "program_version",
                "opcode",
                "left_expression",
                "right_expression",
            ],
            "local intrinsic-relation program",
        )
        _require(
            program["opcode"] == "CHECK_LE_U128_V1"
            and _local_eval_u128(program["left_expression"], spec_body)
            <= _local_eval_u128(program["right_expression"], spec_body),
            "WITNESS_ILLEGAL",
            "local intrinsic affine relation is false",
        )


def _local_batch_octets(local, batch_limit):
    program = local["batch_unsaturated_program"]
    _closed(
        program,
        [
            "opcode",
            "constant_octets",
            "linear_variable",
            "linear_coefficient",
            "decimal_width_coefficient",
            "valid_minimum",
            "valid_maximum",
        ],
        "local batch-length program",
    )
    _require(
        program["opcode"] == "PIECEWISE_AFFINE_DECIMAL_WIDTH_V1"
        and program["linear_variable"] == "MAXIMUM_TERMINAL_INGRESS_BATCHES"
        and program["valid_minimum"] <= batch_limit <= program["valid_maximum"]
        and program["linear_coefficient"] > 0
        and program["decimal_width_coefficient"] >= 0,
        "DERIVATION_INVALID",
        "local batch-length authority differs",
    )
    return _checked_add(
        _u128(program["constant_octets"], "local batch constant"),
        _checked_mul(program["linear_coefficient"], batch_limit),
        _checked_mul(program["decimal_width_coefficient"], len(str(batch_limit))),
    )


def _local_mutated_spec(indexes, baseline_spec, member_name, value):
    spec_body = dict(baseline_spec["spec"])
    spec_body[member_name] = value
    return _reseal_typed_record(
        indexes,
        CASE475_SPEC_TYPE,
        {**baseline_spec, "spec": spec_body},
    )


def _local_attainer(indexes, local, baseline_result, signed_spec):
    spec_body = signed_spec["spec"]
    body = dict(baseline_result["result"])
    array_rows = local["ordered_result_array_mapping_records"]
    _require(
        isinstance(array_rows, list) and len(array_rows) == 5,
        "AUTHORITY_INVALID",
        "local result-array mapping cardinality differs",
    )
    for position, row in enumerate(array_rows, 1):
        cardinality = _u128(
            spec_body[row["cardinality_source"]], "local array cardinality"
        )
        _require(
            row["mapping_position"] == position
            and cardinality <= row["schema_maximum_items"],
            "WITNESS_ILLEGAL",
            "local result-array mapping differs",
        )
        body[row["result_member"]] = [
            f"{ordinal:064x}" for ordinal in range(cardinality)
        ]
    optional_names = local["ordered_optional_sha256_member_names"]
    _require(
        isinstance(optional_names, list) and len(optional_names) == 3,
        "AUTHORITY_INVALID",
        "local optional-SHA authority differs",
    )
    for position, member_name in enumerate(optional_names, 1):
        body[member_name] = f"{position:064x}"
    counter_rows = local["ordered_result_counter_mapping_records"]
    _require(
        isinstance(counter_rows, list) and len(counter_rows) == 13,
        "AUTHORITY_INVALID",
        "local counter mapping cardinality differs",
    )
    for position, row in enumerate(counter_rows, 1):
        _require(
            row["mapping_position"] == position,
            "AUTHORITY_INVALID",
            "local counter mapping order differs",
        )
        source_kind = row["source_kind"]
        if source_kind == "UNSATURATED_RAW_MAXIMIZER_SAFE_INTEGER_MAXIMUM":
            _require(
                row["spec_member"] is None,
                "AUTHORITY_INVALID",
                "local trace-count source differs",
            )
            value = SAFE_INTEGER_MAX
        else:
            name = row["spec_member"]
            _require(
                isinstance(name, str) and name in spec_body,
                "AUTHORITY_INVALID",
                "local counter source is unresolved",
            )
            value = spec_body[name]
            if source_kind == (
                "UNSATURATED_RAW_MAXIMIZER_MIN_SPEC_AND_ARRAY_MAXIMUM"
            ):
                matching = [
                    item
                    for item in array_rows
                    if item["cardinality_source"] == name
                ]
                _require(
                    matching,
                    "AUTHORITY_INVALID",
                    "local min-spec array source is unresolved",
                )
                value = min(
                    value, min(item["schema_maximum_items"] for item in matching)
                )
            else:
                _require(
                    source_kind == "UNSATURATED_RAW_MAXIMIZER_SPEC_LIMIT",
                    "AUTHORITY_INVALID",
                    "local counter source opcode differs",
                )
        body[row["result_member"]] = value
    return _reseal_typed_record(
        indexes,
        CASE475_TYPE,
        {**baseline_result, "result": body},
    )


def _validate_local_result_spec_pair(indexes, result, signed_spec, mask_outer):
    _validate_subset_type(indexes, CASE475_SPEC_TYPE, signed_spec)
    if mask_outer:
        _validate_local_result_with_outer_codec_mask(indexes, result)
    else:
        _validate_subset_type(indexes, CASE475_TYPE, result)
    _evaluate_subset_rule(
        indexes,
        CASE69_RESULT_INTRINSIC_RULE,
        {"self": result["result"]},
        {"self": CASE475_RESULT_BODY_TYPE},
        "INTRINSIC_RECORD",
    )
    _evaluate_subset_rule(
        indexes,
        CASE69_SPEC_INTRINSIC_RULE,
        {"self": signed_spec["spec"]},
        {"self": CASE475_SPEC_BODY_TYPE},
        "INTRINSIC_RECORD",
    )
    _evaluate_subset_rule(
        indexes,
        CASE69_CROSS_RULE,
        {"result": result, "signed_spec": signed_spec},
        {"result": CASE475_TYPE, "signed_spec": CASE475_SPEC_TYPE},
        "CROSS_RECORD",
    )


def _execute_local_minimality(authorities, case, plan, payload):
    seed = authorities["seed"]
    registry = authorities["registry"]
    indexes = _registry_indexes(registry)
    recurrence = seed["recurrence_catalog"]
    local = recurrence["local_shutdown_analytic_catalog"]
    _validate_seed_identity_record(
        seed,
        "LOCAL_SHUTDOWN_ANALYTIC_CATALOG",
        local,
        "local_shutdown_analytic_catalog_id",
    )
    _require(
        case["case_position"] == plan["case_position"] == CASE475_POSITION
        and case["case_kind"]
        == plan["case_kind"]
        == "LOCAL_SHUTDOWN_UNREPRESENTABLE_MINIMALITY"
        and plan["local_analytic_catalog_id"]
        == local["local_shutdown_analytic_catalog_id"]
        == CASE69_ANALYTIC_ID
        and plan["logical_plan_template_id"] is None
        and plan["profile_conditioning_program_id"] is None
        and plan["root_step_position"] is None
        and plan["logical_root_reference"]
        == {
            "root_kind": "LOCAL_SHUTDOWN_ANALYTIC_CATALOG",
            "root_id": CASE69_ANALYTIC_ID,
        }
        and plan["upper_bound_mode"] == "EXACT_LEGAL_DOMAIN"
        and plan["ordered_safe_relaxation_rule_ids"] == [],
        "AUTHORITY_INVALID",
        "local case-plan binding differs",
    )
    _plan_identity_preimage(seed, plan)
    binding = case["case_binding"]
    _require(
        binding == plan["case_binding"]
        and binding["baseline_inventory_json_pointer"] == CASE69_SPEC_POINTER
        and binding["baseline_operation_spec_id"] == CASE69_SPEC_ID
        and binding["constraint_scope_profile_id"] == CASE69_PROFILE_ID
        and binding["counterexample_kind"]
        == "LOCAL_SHUTDOWN_UNREPRESENTABLE_MINIMALITY"
        and binding["masked_codec_coordinate"]
        == {
            "validation_root_type_name": CASE475_TYPE,
            "codec_owner_type_name": CASE475_TYPE,
            "codec_owner_typed_member_path": [],
            "codec_byte_bound_relation": "LT",
            "codec_octet_limit": 524_288,
        },
        "AUTHORITY_INVALID",
        "local case binding differs",
    )
    inventory = _strict_loads(
        authorities["authority_bytes"]["V4_INVENTORY"], authorities["limits"]
    )
    baseline_spec = _json_pointer(inventory, CASE69_SPEC_POINTER, "local baseline spec")
    baseline_result = _json_pointer(
        inventory,
        local["baseline_result_inventory_json_pointer"],
        "local baseline result",
    )
    _require(
        local["baseline_inventory_json_pointer"] == CASE69_SPEC_POINTER
        and baseline_spec["operation_spec_id"]
        == local["baseline_operation_spec_id"]
        == CASE69_SPEC_ID
        and baseline_result["result_evidence_id"]
        == local["baseline_result_evidence_id"]
        and len(_canonical_bytes(baseline_result))
        == local["baseline_result_canonical_octets"],
        "AUTHORITY_INVALID",
        "local baseline authority differs",
    )
    _validate_local_result_spec_pair(
        indexes, baseline_result, baseline_spec, mask_outer=False
    )

    kernel = next(
        (
            row
            for row in recurrence["ordered_derivation_kernel_records"]
            if row["derivation_kind"] == "LOCAL_SHUTDOWN_ANALYTIC_LENGTH_SWEEP"
        ),
        None,
    )
    _require(
        kernel is not None
        and kernel["state_signature_id"] == local["state_signature_id"]
        and kernel["kernel_record_sha256"]
        == local["derivation_kernel_record_sha256"]
        == _sha256(
            _canonical_bytes(
                {
                    name: value
                    for name, value in kernel.items()
                    if name != "kernel_record_sha256"
                }
            )
        )
        and kernel["transfer_program"]["opcode"]
        == "CELL_LOCAL_SHUTDOWN_SWEEP_V2",
        "AUTHORITY_INVALID",
        "local derivation-kernel binding differs",
    )
    signature = next(
        (
            row
            for row in recurrence["ordered_state_signature_records"]
            if row["state_signature_id"] == local["state_signature_id"]
        ),
        None,
    )
    _require(
        signature is not None
        and len(signature["ordered_component_records"]) == 8
        and [
            row["component_kind"] for row in signature["ordered_component_records"]
        ]
        == local["controller_instruction_set"][
            "ordered_state_component_kinds"
        ],
        "AUTHORITY_INVALID",
        "local state-signature authority differs",
    )
    application = indexes["applications"].get(CASE69_APPLICATION_NAME)
    _require(
        application is not None
        and application["rule_application_id"] == CASE69_APPLICATION_ID
        and application["rule_id"] == CASE69_CROSS_RULE
        and application["maximum_rule_evaluations"] == 1,
        "AUTHORITY_INVALID",
        "local signed-spec application authority differs",
    )

    mutable_records = local["ordered_mutable_limit_records"]
    states = local["ordered_controller_state_records"]
    transitions = local["ordered_controller_transition_records"]
    _require(
        len(mutable_records) == len(transitions) == 11
        and len(states) == 12
        and local["fixed_controller_transition_count"] == 11
        and local["fixed_controller_state_count"] == 12
        and local["initial_controller_state_position"] == 1
        and local["terminal_controller_state_position"] == 12
        and [row["member_name"] for row in mutable_records]
        == binding["ordered_mutable_limit_member_names"],
        "AUTHORITY_INVALID",
        "local controller cardinality or mutable-member order differs",
    )
    for position, state in enumerate(states, 1):
        _validate_seed_identity_record(
            seed,
            "LOCAL_SHUTDOWN_CONTROLLER_STATE",
            state,
            "controller_state_id",
        )
        _require(
            state["controller_state_position"] == position
            and state["state_signature_id"] == local["state_signature_id"]
            and len(state["ordered_state_components"]) == 8,
            "AUTHORITY_INVALID",
            "local controller state differs",
        )
    _require(
        states[0]["state_kind"] == "INITIAL"
        and states[0]["ordered_state_components"]
        == [0, "NOT_EVALUATED", None, None, None, None, None, None]
        and states[-1]["state_kind"] == "TERMINAL",
        "AUTHORITY_INVALID",
        "local initial/terminal state differs",
    )

    relation_literals = inventory["operation_contracts"][
        "local_shutdown_intrinsic_limit_relations"
    ]
    _require(
        [row["authority_relation_literal"] for row in local[
            "ordered_intrinsic_affine_relation_records"
        ]]
        == relation_literals,
        "AUTHORITY_INVALID",
        "local intrinsic-relation literal authority differs",
    )
    baseline_max = _local_attainer(indexes, local, baseline_result, baseline_spec)
    _validate_local_result_spec_pair(
        indexes, baseline_max, baseline_spec, mask_outer=False
    )
    _require(
        len(_canonical_bytes(baseline_max))
        == local["baseline_attainable_maximum_octets"]
        == CASE69_EXACT_MAXIMUM,
        "DERIVATION_INVALID",
        "local baseline attainable maximum differs",
    )

    endpoint_octets = {}
    spec_body_descriptor = indexes["types"].get(CASE475_SPEC_BODY_TYPE)
    _require(
        spec_body_descriptor is not None
        and spec_body_descriptor["type_form"] == "RECORD"
        and {row["authority_domain_position"] for row in mutable_records}
        == set(range(1, 12)),
        "AUTHORITY_INVALID",
        "local mutable-limit structural authority differs",
    )
    spec_member_descriptors = {
        row["member_name"]: row
        for row in spec_body_descriptor["record_member_descriptors"]
    }
    for position, record in enumerate(mutable_records, 1):
        name = record["member_name"]
        member_descriptor = spec_member_descriptors.get(name)
        member_schema = (
            None
            if member_descriptor is None
            else indexes["schemas"].get(member_descriptor["value_schema_id"])
        )
        _require(
            record["lexical_position"] == position
            and record["baseline_value"] == baseline_spec["spec"][name]
            and member_schema is not None
            and member_schema["schema_kind"] == "SAFE_INTEGER"
            and record["integer_minimum"] == member_schema["integer_minimum"]
            and record["integer_maximum"] == member_schema["integer_maximum"]
            and record["integer_minimum"]
            <= record["one_field_non_decreasing_upper"]
            <= record["integer_maximum"],
            "AUTHORITY_INVALID",
            "local mutable-limit authority differs",
        )
        if name == CASE475_WINNING_MEMBER:
            continue
        endpoint_spec = _local_mutated_spec(
            indexes, baseline_spec, name, record["one_field_non_decreasing_upper"]
        )
        _local_relations_hold(local, endpoint_spec["spec"])
        endpoint_result = _local_attainer(
            indexes, local, baseline_result, endpoint_spec
        )
        _validate_local_result_spec_pair(
            indexes, endpoint_result, endpoint_spec, mask_outer=False
        )
        length = len(_canonical_bytes(endpoint_result))
        _require(
            length == record["one_field_endpoint_or_cap_maximum_octets"]
            and length < 524_288,
            "DERIVATION_INVALID",
            "local one-field endpoint reconstruction differs",
        )
        endpoint_octets[position] = length

    predecessor_spec = _local_mutated_spec(
        indexes, baseline_spec, CASE475_WINNING_MEMBER, CASE475_WINNING_VALUE - 1
    )
    winner_spec = _local_mutated_spec(
        indexes, baseline_spec, CASE475_WINNING_MEMBER, CASE475_WINNING_VALUE
    )
    _local_relations_hold(local, predecessor_spec["spec"])
    _local_relations_hold(local, winner_spec["spec"])
    predecessor_result = _local_attainer(
        indexes, local, baseline_result, predecessor_spec
    )
    winner_attainer = _local_attainer(indexes, local, baseline_result, winner_spec)
    _validate_local_result_spec_pair(
        indexes, predecessor_result, predecessor_spec, mask_outer=False
    )
    _validate_local_result_spec_pair(
        indexes, winner_attainer, winner_spec, mask_outer=True
    )
    predecessor_length = len(_canonical_bytes(predecessor_result))
    winner_length = len(_canonical_bytes(winner_attainer))
    winner_body_length = len(_canonical_bytes(winner_attainer["result"]))
    _require(
        predecessor_length
        == _local_batch_octets(local, CASE475_WINNING_VALUE - 1)
        == local["predecessor_attainable_maximum_octets"]
        == CASE475_PREDECESSOR_MAXIMUM
        and winner_length
        == _local_batch_octets(local, CASE475_WINNING_VALUE)
        == local["winner_attainable_maximum_octets"]
        == CASE475_EXACT_MAXIMUM
        and winner_body_length == local["winner_body_octets"]
        and winner_length - winner_body_length == local["wrapper_overhead_octets"]
        and predecessor_length < 524_288 <= winner_length,
        "DERIVATION_INVALID",
        "local predecessor/winner boundary differs",
    )

    best = None
    best_position = None
    best_octets = None
    evaluation_rows = []
    for position, (record, transition) in enumerate(
        zip(mutable_records, transitions, strict=True), 1
    ):
        _validate_seed_identity_record(
            seed,
            "LOCAL_SHUTDOWN_CONTROLLER_TRANSITION",
            transition,
            "controller_transition_id",
        )
        _require(
            transition["controller_transition_position"] == position
            and transition["input_mutable_limit_lexical_position"] == position
            and transition["source_controller_state_id"]
            == states[position - 1]["controller_state_id"]
            and transition["target_controller_state_id"]
            == states[position]["controller_state_id"],
            "AUTHORITY_INVALID",
            "local controller transition adjacency differs",
        )
        transition_program = transition["transition_program"]
        _closed(
            transition_program,
            [
                "program_version",
                "opcode",
                "candidate_evaluation_program",
                "objective_member_order",
                "best_update_opcode",
            ],
            "local controller transition program",
        )
        _require(
            transition_program["opcode"]
            == "EVALUATE_ONE_FIELD_AND_FOLD_OBJECTIVE_V1"
            and transition_program["objective_member_order"]
            == local["ordered_objective_member_names"]
            == binding["ordered_objective_member_names"],
            "AUTHORITY_INVALID",
            "local objective-fold program differs",
        )
        program = transition_program["candidate_evaluation_program"]
        common = [
            "program_version",
            "opcode",
            "baseline_value",
            "strict_limit_octets",
        ]
        _require(
            program["baseline_value"] == record["baseline_value"]
            and program["strict_limit_octets"] == 524_288,
            "AUTHORITY_INVALID",
            "local candidate-evaluation authority differs",
        )
        opcode = program["opcode"]
        objective = None
        if opcode == "EMPTY_NONDECREASING_INTERVAL_V1":
            _closed(
                program,
                [*common, "non_decreasing_upper", "decisive_attainable_maximum_octets"],
                "local empty-interval program",
            )
            value = program["non_decreasing_upper"]
            octets = program["decisive_attainable_maximum_octets"]
            outcome = "EMPTY_NONDECREASING_MUTATION_INTERVAL"
            _require(
                value == record["one_field_non_decreasing_upper"]
                and value <= record["baseline_value"]
                and octets == endpoint_octets[position] < 524_288
                and record["one_field_threshold_class"]
                == "NO_NONDECREASING_MUTATION",
                "DERIVATION_INVALID",
                "local empty mutation interval differs",
            )
        elif opcode == "MONOTONE_ENDPOINT_BELOW_STRICT_LIMIT_V1":
            _closed(
                program,
                [*common, "endpoint_mutated_value", "endpoint_attainable_maximum_octets"],
                "local endpoint program",
            )
            value = program["endpoint_mutated_value"]
            octets = program["endpoint_attainable_maximum_octets"]
            outcome = "ENDPOINT_BELOW_STRICT_OUTER_CODEC_LIMIT"
            _require(
                value == record["one_field_non_decreasing_upper"]
                and value > record["baseline_value"]
                and octets == endpoint_octets[position] < 524_288
                and record["one_field_threshold_class"] == "FAIL",
                "DERIVATION_INVALID",
                "local endpoint mutation result differs",
            )
        else:
            _require(
                opcode == "FIRST_MONOTONE_STRICT_LIMIT_VIOLATION_V1",
                "DERIVATION_INVALID",
                f"local candidate-evaluation opcode is unsupported: {opcode}",
            )
            _closed(
                program,
                [
                    *common,
                    "length_program_locator",
                    "predecessor_mutated_value",
                    "predecessor_attainable_maximum_octets",
                    "candidate_mutated_value",
                    "candidate_attainable_maximum_octets",
                ],
                "local first-violation program",
            )
            predecessor = program["predecessor_mutated_value"]
            value = program["candidate_mutated_value"]
            octets = program["candidate_attainable_maximum_octets"]
            outcome = "FIRST_STRICT_OUTER_CODEC_VIOLATION"
            _require(
                position == 2
                and record["member_name"] == CASE475_WINNING_MEMBER
                and record["one_field_threshold_class"] == "PASS_BY_BATCH_FORMULA"
                and program["length_program_locator"] == "/batch_unsaturated_program"
                and predecessor + 1 == value == CASE475_WINNING_VALUE
                and program["predecessor_attainable_maximum_octets"]
                == predecessor_length
                and octets == winner_length
                and predecessor_length < 524_288 <= octets,
                "DERIVATION_INVALID",
                "local first monotone strict-limit violation differs",
            )
            objective = (value - record["baseline_value"], record["member_name"], value)
        if objective is not None and (best is None or objective < best):
            expected_update = (
                "SET_FIRST_ELIGIBLE_BEST_V1"
                if best is None
                else "REPLACE_WITH_LEXICOGRAPHICALLY_SMALLER_BEST_V1"
            )
            best = objective
            best_position = position
            best_octets = octets
        elif objective is not None:
            expected_update = "KEEP_LEXICOGRAPHICALLY_SMALLER_BEST_V1"
        else:
            expected_update = "KEEP_NO_ELIGIBLE_BEST_V1"
        expected_objective = (
            None
            if objective is None
            else {
                "changed_limit_field_count": 1,
                "sum_absolute_integer_deltas": objective[0],
                "changed_member_names_in_lexical_order": [objective[1]],
                "resulting_changed_values_in_that_same_order": [objective[2]],
            }
        )
        expected_components = [
            position,
            outcome,
            value,
            octets,
            best_position,
            None if best is None else best[2],
            None if best is None else best[0],
            best_octets,
        ]
        _require(
            transition["candidate_outcome"] == outcome
            and transition["candidate_objective"] == expected_objective
            and transition_program["best_update_opcode"] == expected_update
            and transition["expected_target_state_components"]
            == states[position]["ordered_state_components"]
            == expected_components,
            "DERIVATION_INVALID",
            "local controller transition execution differs",
        )
        evaluation_rows.append(
            {
                "lexical_position": position,
                "member_name": record["member_name"],
                "baseline_value": record["baseline_value"],
                "one_field_non_decreasing_upper": record[
                    "one_field_non_decreasing_upper"
                ],
                "candidate_outcome": outcome,
                "candidate_mutated_value": value,
                "candidate_attainable_maximum_octets": octets,
                "candidate_objective": expected_objective,
            }
        )
    _require(
        best == (CASE475_WINNING_DELTA, CASE475_WINNING_MEMBER, CASE475_WINNING_VALUE)
        and best_position == 2
        and best_octets == CASE475_EXACT_MAXIMUM
        and local["winning_member_name"] == CASE475_WINNING_MEMBER
        and local["winning_mutated_value"] == CASE475_WINNING_VALUE
        and local["winning_absolute_delta"] == CASE475_WINNING_DELTA
        and local["winner_attainable_maximum_octets"] == CASE475_EXACT_MAXIMUM
        and local["largest_other_one_field_maximum_octets"]
        == max(endpoint_octets.values()),
        "DERIVATION_INVALID",
        "local terminal winner differs",
    )

    candidate_spec = payload["mutated_spec"]
    candidate_result = payload["prospective_result"]
    _require(
        candidate_spec == winner_spec,
        "WITNESS_ILLEGAL",
        "local candidate is not the exact minimal one-field mutation",
    )
    _validate_local_result_spec_pair(
        indexes, candidate_result, candidate_spec, mask_outer=True
    )
    candidate_result_raw = _canonical_bytes(candidate_result)
    _require(
        len(candidate_result_raw) == CASE475_EXACT_MAXIMUM
        and len(candidate_result_raw) >= 524_288,
        "ATTAINMENT_REJECT",
        "local prospective result does not attain the masked-domain maximum",
    )
    winning_objective = {
        "changed_limit_field_count": 1,
        "sum_absolute_integer_deltas": CASE475_WINNING_DELTA,
        "changed_member_names_in_lexical_order": [CASE475_WINNING_MEMBER],
        "resulting_changed_values_in_that_same_order": [CASE475_WINNING_VALUE],
    }
    exclusion_result = {
        "exclusion_result_version": LOCAL_EXCLUSION_RESULT_VERSION,
        "ordered_one_field_evaluation_records": evaluation_rows,
        "winning_objective": winning_objective,
        "ordered_strictly_better_legal_objectives": [],
    }
    return {
        "local": local,
        "baseline_spec": baseline_spec,
        "mutated_spec": winner_spec,
        "prospective_result": candidate_result,
        "prospective_result_raw": candidate_result_raw,
        "winning_objective": winning_objective,
        "better_objective_exclusion_result_sha256": _sha256(
            _canonical_bytes(exclusion_result)
        ),
    }


def _condition_case69_profile(authorities, case, plan, template, cells, context):
    seed = authorities["seed"]
    recipe = seed["logical_plan_recipe_catalog"]
    profiles = [
        row
        for row in recipe["ordered_profile_conditioning_program_records"]
        if row["profile_conditioning_program_id"] == CASE69_PROGRAM_ID
    ]
    _require(
        len(profiles) == 1,
        "AUTHORITY_INVALID",
        "case 69 profile program is absent or duplicate",
    )
    profile = profiles[0]
    identity = next(
        (
            row
            for row in seed["ordered_identity_domain_records"]
            if row["identity_name"] == "PROFILE_CONDITIONING_PROGRAM"
        ),
        None,
    )
    _require(
        identity is not None
        and _seed_semantic_id(
            seed,
            identity["domain_literal"],
            {
                name: profile[name]
                for name in identity["ordered_payload_member_names"]
            },
        )
        == CASE69_PROGRAM_ID,
        "AUTHORITY_INVALID",
        "case 69 profile program identity does not reproduce",
    )
    _require(
        profile["program_position"] == profile["profile_position"] == 3
        and profile["case_position"] == case["case_position"] == CASE69_POSITION
        and profile["maximum_constraint_scope_profile_id"] == CASE69_PROFILE_ID
        and profile["profile_kind"] == "OUTER_RESULT_BOUNDARY_FIXTURE"
        and profile["constraint_scope"] == "FROZEN_FIXTURE"
        and profile["operation_kind"] == "LOCAL_SHUTDOWN"
        and profile["conditioning_strategy"]
        == "LOCAL_SHUTDOWN_BASELINE_ANALYTIC_EXACT_V1"
        and profile["measured_type_name"] == CASE69_TYPE
        and profile["logical_plan_template_id"] == plan["logical_plan_template_id"]
        and profile["template_root_step_position"]
        == plan["root_step_position"]
        == template["root_step_position"],
        "AUTHORITY_INVALID",
        "case 69 profile binding differs",
    )
    scope_summary = plan["scope_summary"]
    _require(
        plan["upper_bound_mode"] == "EXACT_LEGAL_DOMAIN"
        and plan["ordered_safe_relaxation_rule_ids"] == []
        and scope_summary["application_invocation_count"] == 1
        and scope_summary["cross_rule_evaluation_count"] == 1
        and scope_summary["direct_cross_expression_node_count"] == 3
        and scope_summary["internal_scope_case_count"] == 1
        and scope_summary["context_record_reference_count"] == 2
        and scope_summary["application_schedule_operation_position"] == 3
        and scope_summary["schedule_authority_kind"]
        == "PROFILE_CONDITIONING_PROGRAM"
        and scope_summary["schedule_authority_id"] == CASE69_PROGRAM_ID,
        "AUTHORITY_INVALID",
        "case 69 plan scope summary differs",
    )

    inventory = _strict_loads(
        authorities["authority_bytes"]["V4_INVENTORY"], authorities["limits"]
    )
    inventory_profile = inventory["operation_contracts"][
        "maximum_constraint_scope_profile_catalog"
    ][2]
    profile_raw = _canonical_bytes(inventory_profile)
    scope = profile["scope_root_operation"]
    _require(
        profile["profile_inventory_json_pointer"]
        == "/operation_contracts/maximum_constraint_scope_profile_catalog/2"
        and inventory_profile["maximum_constraint_scope_profile_id"]
        == CASE69_PROFILE_ID
        and scope["operation_position"] == 2
        and scope["opcode"] == "SCOPE_ROOT"
        and scope["scope_transfer_kind"] == "OUTER_RESULT_APPLICATION"
        and scope["measured_template_root_step_position"]
        == template["root_step_position"]
        and scope["ordered_fixed_authority_operation_positions"] == [1]
        and scope["ordered_scope_case_records"]
        == [
            {
                "scope_case_position": 1,
                "root_family_position": None,
                "mode_attempt_pair_position": None,
                "observation_role_position": None,
                "measured_sequence_ordinal": None,
            }
        ]
        and scope["profile_canonical_octets"] == len(profile_raw)
        and scope["profile_canonical_sha256"] == _sha256(profile_raw),
        "AUTHORITY_INVALID",
        "case 69 exact scope-root authority differs",
    )

    fixed = profile["ordered_fixed_authority_operations"]
    spec = context["signed_spec"]
    spec_raw = _canonical_bytes(spec)
    _require(
        len(fixed) == 1
        and fixed[0]
        == {
            "operation_position": 1,
            "opcode": "FIXED_VALUE",
            "inventory_json_pointer": CASE69_SPEC_POINTER,
            "expected_authority_id": CASE69_SPEC_ID,
            "identity_member_name": "operation_spec_id",
            "fixed_canonical_octets": len(spec_raw),
            "fixed_canonical_sha256": _sha256(spec_raw),
        }
        and spec["operation_spec_id"] == CASE69_SPEC_ID,
        "AUTHORITY_INVALID",
        "case 69 fixed signed-spec authority differs",
    )

    schedule = profile["application_schedule_operation"]
    segments = schedule["ordered_schedule_segment_records"]
    _require(
        schedule["operation_position"] == 3
        and schedule["opcode"] == "APPLICATION_SCHEDULE_COUNT"
        and schedule["child_operation_position"] == 2
        and schedule["execution_mode"] == "EXACT_CROSS_RULE_APPLICATION_V1"
        and schedule["application_invocation_count"] == 1
        and schedule["cross_rule_evaluation_count"] == 1
        and schedule["direct_cross_expression_node_count"] == 3
        and len(segments) == 1
        and segments[0]["segment_position"] == 1
        and segments[0]["scope_case_multiplicity"] == 1
        and segments[0]["selector_present"] is False
        and segments[0]["application_invocation_count_per_scope_case"] == 1
        and segments[0]["cross_rule_evaluation_count_per_scope_case"] == 1
        and segments[0]["direct_cross_expression_node_count_per_scope_case"] == 3
        and segments[0]["observation_count"] == 0,
        "AUTHORITY_INVALID",
        "case 69 application schedule aggregate differs",
    )
    instructions = segments[0]["ordered_application_instruction_records"]
    _require(
        instructions
        == [
            {
                "instruction_position": 1,
                "application_name": CASE69_APPLICATION_NAME,
                "rule_application_id": CASE69_APPLICATION_ID,
                "rule_id": CASE69_CROSS_RULE,
                "invocation_ordinal_program": "SINGLE_ZERO_NULL_BOUND_V1",
                "application_invocation_count_per_scope_case": 1,
                "cross_rule_evaluation_count_per_scope_case": 1,
            }
        ],
        "AUTHORITY_INVALID",
        "case 69 exact application instruction differs",
    )
    applications = inventory["external_schema_registry_v2"][
        "ordered_rule_application_descriptors"
    ]
    application = next(
        (row for row in applications if row["application_name"] == CASE69_APPLICATION_NAME),
        None,
    )
    _require(
        application is not None
        and application["rule_application_id"] == CASE69_APPLICATION_ID
        and application["rule_id"] == CASE69_CROSS_RULE
        and application["application_kind"] == "RECORD_TUPLE"
        and application["maximum_rule_evaluations"] == 1
        and application["ordered_root_input_bindings"]
        == [
            {
                "tuple_position": 1,
                "binding_name": "result",
                "expected_type_name": CASE69_TYPE,
            },
            {
                "tuple_position": 2,
                "binding_name": "signed_spec",
                "expected_type_name": CASE69_SPEC_TYPE,
            },
        ],
        "AUTHORITY_INVALID",
        "case 69 registry application binding differs",
    )

    transfer = profile["conditioning_transfer_program"]
    contract = recipe["profile_conditioned_cell_contract"]
    _require(
        transfer["cell_contract_id"]
        == contract["profile_conditioned_cell_contract_id"]
        and contract["p2_cell_kind_enum"]
        == ["SUPERSET_UPPER_BOUND", "EXACT_ATTAINED_MAXIMUM"]
        and contract["exact_cell_invariant"]
        == "CELL_KIND_EXACT_IMPLIES_LOWER_EQUALS_UPPER_EQUALS_ATTAINING_WITNESS"
        and contract["p1_p3_acceptance_rule"]
        == "EXACT_RETAINED_WITNESS_CONTEXT_LEGAL_AND_CANONICAL_LENGTH_EQUALS_P2_UPPER"
        and contract["unresolved_or_unattained_policy"] == "NO_GO"
        and contract["structural_bound_only_acceptance_forbidden"] is True,
        "AUTHORITY_INVALID",
        "case 69 profile-conditioned cell contract differs",
    )

    p2 = transfer["p2_upper_bound_program"]
    p2_rows = p2["ordered_instruction_records"]
    _require(
        [row["instruction_position"] for row in p2_rows] == [1, 2, 3, 4]
        and [row["opcode"] for row in p2_rows]
        == [
            "LOAD_STRUCTURAL_TEMPLATE_SUPERSET_CELL_V1",
            "LOAD_FIXED_AUTHORITY_SET_V1",
            "EXECUTE_LOCAL_SHUTDOWN_BASELINE_ANALYTIC_EXACT_V1",
            "INTERSECT_EXACT_ANALYTIC_WITH_STRUCTURAL_CELL_V1",
        ]
        and [row["ordered_input_instruction_positions"] for row in p2_rows]
        == [[], [], [2], [3, 1]]
        and p2["root_instruction_position"] == 4
        and p2["upper_bound_source"]
        == "LOCAL_SHUTDOWN_BASELINE_ANALYTIC_EXACT_V1"
        and p2["ordered_template_relaxation_application_record_positions"] == []
        and p2["ordered_deleted_cross_application_references"] == []
        and p2["ordered_safe_relaxation_rule_ids"] == []
        and p2["p2_cross_application_deletion_policy_id"] is None
        and p2["application_schedule_operation_position"] is None
        and p2["generic_attainability_claimed"] is None,
        "AUTHORITY_INVALID",
        "case 69 P2 instruction program differs",
    )
    _require(
        p2_rows[0]["parameters"]
        == {
            "logical_plan_template_id": template["logical_plan_template_id"],
            "template_root_step_position": template["root_step_position"],
        }
        and p2_rows[1]["parameters"]
        == {"ordered_fixed_authority_operation_positions": [1]}
        and p2_rows[2]["parameters"]
        == {
            "local_shutdown_analytic_catalog_id": CASE69_ANALYTIC_ID,
            "fixed_spec_operation_position": 1,
        }
        and p2_rows[3]["parameters"]
        == {
            "intersection_rule": "EXACT_ANALYTIC_UPPER_MUST_NOT_EXCEED_STRUCTURAL_UPPER",
            "empty_structural_cell_policy": "NO_GO",
            "analytic_above_structural_upper_policy": "NO_GO",
            "preserve_exact_attained_cell": True,
        },
        "AUTHORITY_INVALID",
        "case 69 P2 parameters differ",
    )

    p1_p3 = transfer["p1_p3_attainment_program"]
    p1_p3_rows = p1_p3["ordered_instruction_records"]
    expected_inputs = [[], [], [], [2, 3], [4, 3], [2, 3, 5], [2], [1, 6, 7]]
    expected_parameters = [
        {"p2_root_instruction_position": 4},
        {
            "constraint_scope_profile_id": CASE69_PROFILE_ID,
            "measured_type_name": CASE69_TYPE,
        },
        {"ordered_fixed_authority_operation_positions": [1]},
        {"scope_root_operation_position": 2},
        {"application_schedule_operation_position": 3},
        {
            "application_schedule_operation_position": 3,
            "execution_mode": "EXACT_CROSS_RULE_APPLICATION_V1",
        },
        {"measured_type_name": CASE69_TYPE},
        {"acceptance_rule": "P1_TRUE_AND_MEASURED_CANONICAL_OCTETS_EQUALS_P2_UPPER"},
    ]
    _require(
        [row["instruction_position"] for row in p1_p3_rows]
        == list(range(1, 9))
        and [row["opcode"] for row in p1_p3_rows]
        == [
            "IMPORT_P2_BOUND_CELL_V1",
            "LOAD_RETAINED_WITNESS_CONTEXT_V1",
            "LOAD_FIXED_AUTHORITY_SET_V1",
            "MATCH_EXACT_PROFILE_SCOPE_CASE_V1",
            "RECONSTRUCT_EXACT_APPLICATION_SCHEDULE_V1",
            "EXECUTE_PINNED_APPLICATION_RULE_AST_ON_RETAINED_BYTES_V1",
            "MEASURE_RETAINED_WITNESS_CANONICAL_OCTETS_V1",
            "REQUIRE_P1_AND_P3_EQUALITY_V1",
        ]
        and [row["ordered_input_instruction_positions"] for row in p1_p3_rows]
        == expected_inputs
        and [row["parameters"] for row in p1_p3_rows] == expected_parameters
        and p1_p3["root_instruction_position"] == 8,
        "AUTHORITY_INVALID",
        "case 69 P1/P3 instruction program differs",
    )

    local = seed["recurrence_catalog"]["local_shutdown_analytic_catalog"]
    formula = local["batch_unsaturated_program"]
    _require(
        local["local_shutdown_analytic_catalog_id"] == CASE69_ANALYTIC_ID
        and local["baseline_inventory_json_pointer"] == CASE69_SPEC_POINTER
        and local["baseline_operation_spec_id"] == CASE69_SPEC_ID
        and local["baseline_attainable_maximum_octets"] == CASE69_EXACT_MAXIMUM,
        "AUTHORITY_INVALID",
        "case 69 local analytic authority differs",
    )
    _closed(
        formula,
        [
            "opcode",
            "constant_octets",
            "linear_variable",
            "linear_coefficient",
            "decimal_width_coefficient",
            "valid_minimum",
            "valid_maximum",
        ],
        "case 69 analytic formula",
    )
    batch_limit = _u128(
        spec["spec"]["maximum_terminal_ingress_batches"],
        "case 69 baseline batch limit",
    )
    _require(
        formula["opcode"] == "PIECEWISE_AFFINE_DECIMAL_WIDTH_V1"
        and formula["linear_variable"] == "MAXIMUM_TERMINAL_INGRESS_BATCHES"
        and formula["valid_minimum"] <= batch_limit <= formula["valid_maximum"],
        "AUTHORITY_INVALID",
        "case 69 analytic formula domain differs",
    )
    derived = _checked_add(
        formula["constant_octets"],
        _checked_mul(formula["linear_coefficient"], batch_limit),
        _checked_mul(formula["decimal_width_coefficient"], len(str(batch_limit))),
    )
    _require(
        derived == local["baseline_attainable_maximum_octets"],
        "DERIVATION_INVALID",
        "case 69 analytic endpoint differs",
    )
    structural = cells[template["root_step_position"] - 1]
    _require(
        structural["status"] == MAY_BE_NONEMPTY and derived <= structural["upper"],
        "DERIVATION_INVALID",
        "case 69 analytic endpoint exceeds the structural cell",
    )
    conditioned = list(cells)
    conditioned[template["root_step_position"] - 1] = _cell(
        derived, derived, structural["state"]
    )
    return conditioned, profile["profile_position"]


def _condition_case435_profile(authorities, case, plan, template, cells, context):
    _require(
        authorities["authority_mode"]
        == "SUCCESSOR_CASE435_PACKED_CONTEXT_BOUNDARY_V1",
        "UNSUPPORTED_CASE",
        "case435 exact profile requires the packed-context authority mode",
    )
    program = authorities["seed_delta"][
        "successor_case435_profile_conditioning_program"
    ]
    _require(
        program["profile_conditioning_program_id"] == SUCCESSOR_CASE435_PROGRAM_ID
        and program["program_position"]
        == program["profile_position"]
        == CASE435_PROFILE_POSITION
        and program["case_position"] == case["case_position"] == CASE435_POSITION
        and program["maximum_constraint_scope_profile_id"] == CASE435_PROFILE_ID
        and program["profile_kind"] == "CHECKPOINT_ROOT_COORDINATE"
        and program["constraint_scope"] == "FROZEN_ROOT_APPLICATION"
        and program["operation_kind"] == "INGRESS"
        and program["conditioning_strategy"]
        == "APPLICATION_AWARE_EXACT_UPPER_ATTAINMENT_JOIN_V1"
        and program["measured_type_name"] == CASE435_TYPE
        and program["logical_plan_template_id"] == plan["logical_plan_template_id"]
        and program["template_root_step_position"]
        == plan["root_step_position"]
        == template["root_step_position"]
        == 158,
        "AUTHORITY_INVALID",
        "case435 profile binding differs",
    )
    scope_summary = plan["scope_summary"]
    _require(
        plan["upper_bound_mode"] == "EXACT_LEGAL_DOMAIN"
        and plan["ordered_safe_relaxation_rule_ids"] == []
        and scope_summary["application_invocation_count"]
        == CASE435_APPLICATION_INVOCATION_COUNT
        and scope_summary["cross_rule_evaluation_count"]
        == CASE435_RULE_EVALUATION_COUNT
        and scope_summary["direct_cross_expression_node_count"]
        == CASE435_DIRECT_EXPRESSION_NODE_COUNT
        and scope_summary["internal_scope_case_count"] == 1
        and scope_summary["constructed_context_occurrence_count"] == 67
        and scope_summary["context_record_reference_count"] == 71
        and scope_summary["observation_count"] == CASE435_OBSERVATION_COUNT
        and scope_summary["application_schedule_operation_position"] == 5
        and scope_summary["schedule_authority_kind"]
        == "PROFILE_CONDITIONING_PROGRAM"
        and scope_summary["schedule_authority_id"] == SUCCESSOR_CASE435_PROGRAM_ID,
        "AUTHORITY_INVALID",
        "case435 plan scope summary differs",
    )
    inventory = _strict_loads(
        authorities["authority_bytes"]["V4_INVENTORY"], authorities["limits"]
    )
    inventory_profile = _json_pointer(
        inventory, CASE435_PROFILE_POINTER, "case435 profile"
    )
    profile_raw = _canonical_bytes(inventory_profile)
    scope = program["scope_root_operation"]
    _require(
        program["profile_inventory_json_pointer"] == CASE435_PROFILE_POINTER
        and inventory_profile["maximum_constraint_scope_profile_id"]
        == CASE435_PROFILE_ID
        and inventory_profile["profile_position"] == CASE435_PROFILE_POSITION
        and inventory_profile["selector_position"]
        == CASE435_MEASURED_SEQUENCE_ORDINAL
        and inventory_profile["ordered_admissible_root_families"]
        == [
            {
                "root_family_kind": "ORDINARY_SELECTOR_BOUND",
                "selector_present": True,
                "selector_catalog_name": "INGRESS_MAX64_PARSER_UNITS",
                "selector_catalog_position": 4,
                "checkpoint_selector_id": context["selector"][
                    "checkpoint_selector_id"
                ],
                "selector_length": 64,
                "observation_count": 67,
                "ordered_instrumentation_mode_attempt_presence_pairs": [
                    ["ON", "NON_NULL"]
                ],
                "ordered_measured_observation_roles": ["STABLE_CHECKPOINT"],
                "role_sequence_formula": (
                    "ORDINARY_BEFORE_CHECKPOINTS_AFTER_AGGREGATE_V1"
                ),
            }
        ]
        and scope["operation_position"] == 4
        and scope["opcode"] == "SCOPE_ROOT"
        and scope["scope_transfer_kind"] == "ROOT_APPLICATION"
        and scope["measured_template_root_step_position"] == 158
        and scope["ordered_fixed_authority_operation_positions"] == [1, 2, 3]
        and scope["ordered_scope_case_records"]
        == [
            {
                "scope_case_position": 1,
                "root_family_position": 1,
                "mode_attempt_pair_position": 1,
                "observation_role_position": 1,
                "measured_sequence_ordinal": CASE435_MEASURED_SEQUENCE_ORDINAL,
            }
        ]
        and scope["profile_canonical_octets"] == len(profile_raw)
        and scope["profile_canonical_sha256"] == _sha256(profile_raw),
        "AUTHORITY_INVALID",
        "case435 exact profile/scope authority differs",
    )
    fixed_values = (
        (CASE435_TARGET_REGISTRY_POINTER, context["target_registry"]),
        (CASE435_MARKER_CONTRACT_POINTER, context["marker_contract"]),
        (CASE435_SELECTOR_POINTER, context["selector"]),
    )
    fixed = program["ordered_fixed_authority_operations"]
    _require(
        len(fixed) == len(fixed_values) == 3,
        "AUTHORITY_INVALID",
        "case435 fixed-authority count differs",
    )
    for position, (operation, (pointer, value)) in enumerate(
        zip(fixed, fixed_values), 1
    ):
        raw = _canonical_bytes(value)
        _require(
            operation["operation_position"] == position
            and operation["opcode"] == "FIXED_VALUE"
            and operation["inventory_json_pointer"] == pointer
            and operation["fixed_canonical_octets"] == len(raw)
            and operation["fixed_canonical_sha256"] == _sha256(raw)
            and value[operation["identity_member_name"]]
            == operation["expected_authority_id"],
            "AUTHORITY_INVALID",
            "case435 fixed-authority binding differs",
        )
    schedule = program["application_schedule_operation"]
    segments = schedule["ordered_schedule_segment_records"]
    _require(
        schedule["operation_position"] == 5
        and schedule["opcode"] == "APPLICATION_SCHEDULE_COUNT"
        and schedule["child_operation_position"] == 4
        and schedule["execution_mode"] == "EXACT_CROSS_RULE_APPLICATION_V1"
        and schedule["application_invocation_count"]
        == CASE435_APPLICATION_INVOCATION_COUNT
        and schedule["cross_rule_evaluation_count"]
        == CASE435_RULE_EVALUATION_COUNT
        and schedule["direct_cross_expression_node_count"]
        == CASE435_DIRECT_EXPRESSION_NODE_COUNT
        and len(segments) == 1,
        "AUTHORITY_INVALID",
        "case435 application schedule aggregate differs",
    )
    segment = segments[0]
    _require(
        segment["segment_position"] == 1
        and segment["scope_case_multiplicity"] == 1
        and segment["root_family_position"] == 1
        and segment["selector_present"] is True
        and segment["observation_count"] == CASE435_OBSERVATION_COUNT
        and segment["application_invocation_count_per_scope_case"]
        == CASE435_APPLICATION_INVOCATION_COUNT
        and segment["cross_rule_evaluation_count_per_scope_case"]
        == CASE435_RULE_EVALUATION_COUNT
        and segment["direct_cross_expression_node_count_per_scope_case"]
        == CASE435_DIRECT_EXPRESSION_NODE_COUNT,
        "AUTHORITY_INVALID",
        "case435 application schedule segment differs",
    )
    instructions = segment["ordered_application_instruction_records"]
    _require(
        len(instructions) == len(CASE435_APPLICATIONS),
        "AUTHORITY_INVALID",
        "case435 instruction count differs",
    )
    for position, (instruction, expected) in enumerate(
        zip(instructions, CASE435_APPLICATIONS), 1
    ):
        name, application_id, rule_id, count, ordinal_program = expected
        _require(
            instruction["instruction_position"] == position
            and instruction["application_name"] == name
            and instruction["rule_application_id"] == application_id
            and instruction["rule_id"] == rule_id
            and instruction["invocation_ordinal_program"] == ordinal_program
            and instruction["application_invocation_count_per_scope_case"] == count,
            "AUTHORITY_INVALID",
            "case435 exact application instruction differs",
        )
    p1 = context.get("p1_execution")
    _require(
        p1
        == {
            "application_invocation_count": CASE435_APPLICATION_INVOCATION_COUNT,
            "charged_rule_evaluation_count": CASE435_RULE_EVALUATION_COUNT,
            "completed_rule_evaluation_count": CASE435_RULE_EVALUATION_COUNT,
            "direct_expression_node_count": CASE435_DIRECT_EXPRESSION_NODE_COUNT,
        },
        "DERIVATION_INVALID",
        "case435 completed P1 receipt differs",
    )
    transfer = program["conditioning_transfer_program"]
    contract = authorities["seed"]["logical_plan_recipe_catalog"][
        "profile_conditioned_cell_contract"
    ]
    _require(
        transfer["program_version"]
        == "riskyieldmm.raw_v8_step2_external_schema_v2.profile_conditioning_dual_channel_program.v2"
        and transfer["cell_contract_id"]
        == contract["profile_conditioned_cell_contract_id"]
        and contract["p2_cell_kind_enum"]
        == ["SUPERSET_UPPER_BOUND", "EXACT_ATTAINED_MAXIMUM"]
        and contract["exact_cell_invariant"]
        == "CELL_KIND_EXACT_IMPLIES_LOWER_EQUALS_UPPER_EQUALS_ATTAINING_WITNESS"
        and contract["p1_p3_acceptance_rule"]
        == "EXACT_RETAINED_WITNESS_CONTEXT_LEGAL_AND_CANONICAL_LENGTH_EQUALS_P2_UPPER"
        and contract["unresolved_or_unattained_policy"] == "NO_GO"
        and contract["structural_bound_only_acceptance_forbidden"] is True,
        "AUTHORITY_INVALID",
        "case435 profile-conditioned cell contract differs",
    )
    p2 = transfer["p2_upper_bound_program"]
    p2_rows = p2["ordered_instruction_records"]
    exact_cell = p2_rows[0]["parameters"]["exact_cell"]
    structural = cells[template["root_step_position"] - 1]
    p2_expected_parameters = [
        {
            "case_position": CASE435_POSITION,
            "maximum_constraint_scope_profile_id": CASE435_PROFILE_ID,
            "exactness_join_certificate_id": CASE435_EXACTNESS_JOIN_ID,
            "exact_maximum_octets": CASE435_EXACT_MAXIMUM_OCTETS,
            "exact_cell": {
                "cell_kind": "EXACT_ATTAINED_MAXIMUM",
                "cell_status": "C3_EXACTNESS_JOIN_ACCEPTED",
                "certified_lower_bound_octets": CASE435_EXACT_MAXIMUM_OCTETS,
                "certified_upper_bound_octets": CASE435_EXACT_MAXIMUM_OCTETS,
                "attaining_witness_canonical_octets": CASE435_EXACT_MAXIMUM_OCTETS,
                "proof_source_id": CASE435_EXACTNESS_JOIN_ID,
            },
        },
        {
            "logical_plan_template_id": template["logical_plan_template_id"],
            "template_root_step_position": template["root_step_position"],
            "predecessor_structural_upper_bound_octets": (
                CASE435_PREDECESSOR_STRUCTURAL_UPPER_OCTETS
            ),
        },
        {
            "acceptance_rule": (
                "EXACT_CELL_LOWER_EQUALS_UPPER_EQUALS_ATTAINER_AND_"
                "EXACT_UPPER_LE_STRUCTURAL_CEILING"
            )
        },
    ]
    _require(
        [row["instruction_position"] for row in p2_rows] == [1, 2, 3]
        and [row["opcode"] for row in p2_rows]
        == [
            "IMPORT_ACCEPTED_CASE_EXACTNESS_JOIN_CELL_V1",
            "LOAD_STRUCTURAL_TEMPLATE_SUPERSET_CELL_V1",
            "REQUIRE_EXACT_CELL_WITHIN_STRUCTURAL_CEILING_V1",
        ]
        and [row["ordered_input_instruction_positions"] for row in p2_rows]
        == [[], [], [1, 2]]
        and [row["output_type"] for row in p2_rows]
        == [
            "P2_EXACT_ATTAINED_CELL",
            "P2_SUPERSET_BOUND_CELL",
            "P2_EXACT_ATTAINED_CELL",
        ]
        and [row["parameters"] for row in p2_rows] == p2_expected_parameters
        and p2["program_version"]
        == "riskyieldmm.raw_v8_step2_external_schema_v2.case_exactness_join_p2_program.v1"
        and p2["failure_policy"]
        == "UNRESOLVED_EMPTY_INVALID_OR_LIMIT_EXCEEDED_NO_GO"
        and p2["root_instruction_position"] == 3
        and p2["upper_bound_source"] == "ACCEPTED_CASE_EXACTNESS_JOIN_V1"
        and p2["exact_attainability_claimed"] is True
        and p2["safe_relaxation_applied"] is False
        and p2["cross_application_deletion_applied"] is False
        and exact_cell == p2_expected_parameters[0]["exact_cell"]
        and structural["status"] == MAY_BE_NONEMPTY
        and structural["upper"] == CASE435_PREDECESSOR_STRUCTURAL_UPPER_OCTETS
        and CASE435_EXACT_MAXIMUM_OCTETS <= structural["upper"],
        "AUTHORITY_INVALID",
        "case435 P2 exact-cell program differs",
    )
    p1_p3 = transfer["p1_p3_attainment_program"]
    p1_p3_rows = p1_p3["ordered_instruction_records"]
    p1_p3_expected_inputs = [
        [],
        [],
        [],
        [2, 3],
        [4, 3],
        [2, 3, 5],
        [2],
        [1, 6, 7],
    ]
    p1_p3_expected_outputs = [
        "P2_BOUND_CELL",
        "RETAINED_WITNESS_CONTEXT",
        "FIXED_AUTHORITY_SET",
        "SELECTED_EXACT_SCOPE_CASE",
        "EXACT_APPLICATION_SCHEDULE",
        "P1_LEGALITY_RESULT",
        "MEASURED_CANONICAL_OCTETS",
        "PROFILE_MAXIMUM_ACCEPTANCE_RESULT",
    ]
    p1_p3_expected_parameters = [
        {"p2_root_instruction_position": 3},
        {
            "constraint_scope_profile_id": CASE435_PROFILE_ID,
            "measured_type_name": CASE435_TYPE,
        },
        {"ordered_fixed_authority_operation_positions": [1, 2, 3]},
        {"scope_root_operation_position": 4},
        {"application_schedule_operation_position": 5},
        {
            "application_schedule_operation_position": 5,
            "execution_mode": "EXACT_CROSS_RULE_APPLICATION_V1",
        },
        {"measured_type_name": CASE435_TYPE},
        {
            "acceptance_rule": (
                "P1_TRUE_AND_MEASURED_CANONICAL_OCTETS_EQUALS_P2_UPPER"
            )
        },
    ]
    _require(
        [row["instruction_position"] for row in p1_p3_rows] == list(range(1, 9))
        and [row["opcode"] for row in p1_p3_rows]
        == [
            "IMPORT_P2_BOUND_CELL_V1",
            "LOAD_RETAINED_WITNESS_CONTEXT_V1",
            "LOAD_FIXED_AUTHORITY_SET_V1",
            "MATCH_EXACT_PROFILE_SCOPE_CASE_V1",
            "RECONSTRUCT_EXACT_APPLICATION_SCHEDULE_V1",
            "EXECUTE_PINNED_APPLICATION_RULE_AST_ON_RETAINED_BYTES_V1",
            "MEASURE_RETAINED_WITNESS_CANONICAL_OCTETS_V1",
            "REQUIRE_P1_AND_P3_EQUALITY_V1",
        ]
        and [
            row["ordered_input_instruction_positions"] for row in p1_p3_rows
        ]
        == p1_p3_expected_inputs
        and [row["output_type"] for row in p1_p3_rows]
        == p1_p3_expected_outputs
        and [row["parameters"] for row in p1_p3_rows]
        == p1_p3_expected_parameters
        and p1_p3["program_version"]
        == "riskyieldmm.raw_v8_step2_external_schema_v2.profile_p1_p3_attainment_program.v1"
        and p1_p3["failure_policy"]
        == "UNRESOLVED_EMPTY_INVALID_OR_LIMIT_EXCEEDED_NO_GO"
        and p1_p3["root_instruction_position"] == 8,
        "AUTHORITY_INVALID",
        "case435 P1/P3 instruction program differs",
    )
    conditioned = list(cells)
    conditioned[template["root_step_position"] - 1] = _cell(
        CASE435_EXACT_MAXIMUM_OCTETS,
        CASE435_EXACT_MAXIMUM_OCTETS,
        structural["state"],
    )
    return conditioned, CASE435_PROFILE_POSITION


def _execute_bound(authorities, case, plan, witness, context):
    seed = authorities["seed"]
    registry = authorities["registry"]
    _validate_typed_legality(authorities, case, witness, context)
    template = _logical_template(seed, plan, case)
    recurrence = seed["recurrence_catalog"]
    kernels = {
        row["derivation_kind"]: row
        for row in recurrence["ordered_derivation_kernel_records"]
    }
    opcode_rows = recurrence["instruction_set"]["transfer_program_schema"][
        "ordered_transfer_opcode_records"
    ]
    opcode_contracts = {row["opcode"]: row for row in opcode_rows}
    _require(
        len(kernels) == 18 and len(opcode_contracts) == 18,
        "AUTHORITY_INVALID",
        "recurrence instruction catalog differs",
    )
    ambient_ceiling = _u128(
        recurrence["arithmetic_policy"]["published_maximum"],
        "published arithmetic maximum",
    )
    nullable_child_positions = {
        step["recurrence_parameters"]["child_step_position"]
        for step in template["ordered_template_steps"]
        if step["derivation_kind"] == "NULLABLE_BRANCH"
    }
    selected_alternative = case["case_binding"]["alternative_name"]
    if case["case_position"] == CASE69_POSITION:
        _require(
            witness.get("operation_kind") == "LOCAL_SHUTDOWN"
            and witness.get("result_type")
            == "LOCAL_SHUTDOWN_RESULT_EVIDENCE_V2",
            "WITNESS_ILLEGAL",
            "case 69 witness does not select the local-shutdown result branch",
        )
        selected_alternative = "LOCAL_SHUTDOWN_RESULT_EVIDENCE_V2"
    cells = []
    actual_lengths = []
    for position, step in enumerate(template["ordered_template_steps"], 1):
        _require(
            step["template_step_position"] == position,
            "DERIVATION_INVALID",
            "template is not strict postorder",
        )
        kernel = kernels.get(step["derivation_kind"])
        _require(
            kernel is not None
            and kernel["kernel_record_sha256"] == step["kernel_record_sha256"],
            "DERIVATION_INVALID",
            "step kernel identity differs",
        )
        children = step["ordered_child_step_positions"]
        _require(
            isinstance(children, list)
            and all(_is_int(child) and 1 <= child < position for child in children),
            "DERIVATION_INVALID",
            "step child order differs",
        )
        parameters = step["recurrence_parameters"]
        _require(
            isinstance(parameters, dict)
            and set(parameters) == set(kernel["ordered_parameter_member_names"]),
            "DERIVATION_INVALID",
            "step parameters differ",
        )
        for target, expression in (
            ("physical_transition_count", "transition_attempt_count_expression"),
            (
                "logical_unbatched_transition_equivalent_count",
                "logical_unbatched_transition_equivalent_count_expression",
            ),
            ("physical_batch_application_count", "batch_application_count_expression"),
        ):
            _require(
                _eval_meter_expression(kernel["meter_program"][expression], step)
                == step[target],
                "DERIVATION_INVALID",
                f"step meter differs: {target}",
            )
        opcode = kernel["transfer_program"]["opcode"]
        contract = opcode_contracts.get(opcode)
        _require(
            contract is not None
            and contract["transfer_rule_id"]
            in {
                row["transfer_rule_id"]
                for row in recurrence["transfer_rule_catalog"][
                    "ordered_transfer_rule_records"
                ]
            },
            "DERIVATION_INVALID",
            "step transfer rule is unresolved",
        )
        _require(
            set(parameters) == set(contract["ordered_required_parameter_names"]),
            "DERIVATION_INVALID",
            "transfer parameter contract differs",
        )
        actual_values = (
            []
            if case["case_position"] == CASE435_POSITION
            and step["subject_locator"]["typed_path"] != []
            else _locator_values(
                witness,
                step["subject_locator"],
                selected_alternative,
            )
        )
        if position in nullable_child_positions:
            actual_values = [value for value in actual_values if value is not None]
        actual_lengths_for_step = [
            len(_canonical_bytes(value)) for value in actual_values
        ]

        if opcode == "CELL_FINITE_TEXT_V1":
            literals = parameters["ordered_literals"]
            _require(
                isinstance(literals, list)
                and literals
                and all(type(value) is str for value in literals),
                "DERIVATION_INVALID",
                "finite-text authority differs",
            )
            _require(
                all(value in literals for value in actual_values),
                "WITNESS_ILLEGAL",
                "witness text is outside the finite language",
            )
            lengths = [len(_canonical_bytes(value)) for value in literals]
            cell = _cell(min(lengths), max(lengths))
        elif opcode == "CELL_BOOLEAN_LITERAL_V1":
            literal = parameters["boolean_literal"]
            domain = [False, True] if literal is None else [literal]
            _require(
                all(type(value) is bool for value in domain),
                "DERIVATION_INVALID",
                "Boolean authority differs",
            )
            _require(
                all(type(value) is bool and value in domain for value in actual_values),
                "WITNESS_ILLEGAL",
                "witness Boolean is outside the legal domain",
            )
            lengths = [len(_canonical_bytes(value)) for value in domain]
            cell = _cell(min(lengths), max(lengths))
        elif opcode == "CELL_SAFE_INTEGER_INTERVAL_V1":
            minimum = parameters["integer_minimum"]
            maximum = parameters["integer_maximum"]
            _require(
                type(minimum) is int
                and type(maximum) is int
                and -SAFE_INTEGER_MAX <= minimum <= maximum <= SAFE_INTEGER_MAX,
                "DERIVATION_INVALID",
                "safe-integer interval differs",
            )
            nearest_zero = (
                0
                if minimum <= 0 <= maximum
                else minimum
                if minimum > 0
                else maximum
            )
            _require(
                all(
                    type(value) is int and minimum <= value <= maximum
                    for value in actual_values
                ),
                "WITNESS_ILLEGAL",
                "witness integer is outside the frozen interval",
            )
            cell = _cell(
                len(str(nearest_zero).encode("ascii")),
                max(
                    len(str(minimum).encode("ascii")),
                    len(str(maximum).encode("ascii")),
                ),
            )
        elif opcode == "CELL_BOUNDED_TEXT_OCTETS_V1":
            lower = _u128(
                parameters["minimum_canonical_octets"], "bounded-text minimum"
            )
            upper = _u128(
                parameters["maximum_canonical_octets"], "bounded-text maximum"
            )
            _require(
                lower <= upper <= ambient_ceiling,
                "DERIVATION_INVALID",
                "bounded-text interval differs",
            )
            _require(
                all(type(value) is str for value in actual_values),
                "WITNESS_ILLEGAL",
                "bounded-text witness is not text",
            )
            cell = _cell(lower, upper)
        elif opcode == "CELL_RELAXED_JSON_STRING_V1":
            _require(
                ambient_ceiling >= 2,
                "DERIVATION_INVALID",
                "relaxed string domain is empty",
            )
            _require(
                all(type(value) is str for value in actual_values),
                "WITNESS_ILLEGAL",
                "relaxed-string witness is not text",
            )
            cell = _cell(2, ambient_ceiling)
        elif opcode == "CELL_CHILD_BOUNDS_ALIAS_V1":
            _require(
                children == [parameters["child_step_position"]]
                and any(
                    row["type_name"] == parameters["referenced_type_name"]
                    for row in registry["ordered_external_type_descriptors"]
                ),
                "DERIVATION_INVALID",
                "object-reference child/type authority differs",
            )
            child = cells[children[0] - 1]
            cell = _cell(child["lower"], child["upper"], child["state"])
        elif opcode == "CELL_NULLABLE_V1":
            _require(
                children == [parameters["child_step_position"]],
                "DERIVATION_INVALID",
                "nullable child differs",
            )
            child = cells[children[0] - 1]
            _require(
                all(value is None or value is not None for value in actual_values),
                "WITNESS_ILLEGAL",
                "nullable witness differs",
            )
            cell = _cell(min(4, child["lower"]), max(4, child["upper"]))
        elif opcode == "CELL_ARRAY_BATCH_V1":
            _require(
                children == [parameters["item_step_position"]],
                "DERIVATION_INVALID",
                "array item child differs",
            )
            minimum_items = _u128(parameters["minimum_items"], "array minimum")
            maximum_items = _u128(parameters["maximum_items"], "array maximum")
            _require(
                minimum_items <= maximum_items,
                "DERIVATION_INVALID",
                "array cardinality interval is inverted",
            )
            observer = parameters["observer_closure_record"]
            runs = parameters["ordered_run_records"]
            _require(
                isinstance(observer, dict)
                and observer.get("batch_eligible") is True
                and isinstance(runs, list)
                and sum(_u128(row.get("item_count"), "array run count") for row in runs)
                == maximum_items
                and all(
                    row.get("item_step_position") == children[0] for row in runs
                ),
                "DERIVATION_INVALID",
                "array batch closure differs",
            )
            _require(
                all(
                    isinstance(value, list)
                    and minimum_items <= len(value) <= maximum_items
                    for value in actual_values
                ),
                "WITNESS_ILLEGAL",
                "witness array cardinality differs",
            )
            child = cells[children[0] - 1]

            def array_length(cardinality, item_octets):
                commas = cardinality - 1 if cardinality else 0
                return _checked_add(
                    2, _checked_mul(cardinality, item_octets), commas
                )

            raw_lower = array_length(minimum_items, child["lower"])
            raw_upper = array_length(maximum_items, child["upper"])
            _require(
                raw_lower <= ambient_ceiling,
                "DERIVATION_INVALID",
                "array lower bound exceeds the ambient ceiling",
            )
            item_upper_sum = min(
                ambient_ceiling, _checked_mul(maximum_items, child["upper"])
            )
            comma_count = maximum_items - 1 if maximum_items else 0
            cell = _cell(
                raw_lower,
                min(raw_upper, ambient_ceiling),
                [maximum_items, item_upper_sum, comma_count],
            )
        elif opcode == "CELL_RECORD_V1":
            rows = parameters["ordered_member_records"]
            _require(
                parameters["record_member_count"] == len(rows) == len(children),
                "DERIVATION_INVALID",
                "record member count differs",
            )
            names = []
            syntax = 2 + max(0, len(rows) - 1)
            for member_position, row in enumerate(rows, 1):
                _require(
                    row["member_position"] == member_position
                    and row["child_step_position"] == children[member_position - 1],
                    "DERIVATION_INVALID",
                    "record member order differs",
                )
                name = row["member_name"]
                names.append(name)
                name_octets = len(_canonical_bytes(name))
                _require(
                    row["member_name_canonical_octets"] == name_octets,
                    "DERIVATION_INVALID",
                    "record member-name length differs",
                )
                syntax = _checked_add(syntax, name_octets, 1)
            _require(
                parameters["record_syntax_octets_excluding_child_values"] == syntax,
                "DERIVATION_INVALID",
                "record syntax authority differs",
            )
            _require(
                all(
                    isinstance(value, dict) and set(value) == set(names)
                    for value in actual_values
                ),
                "WITNESS_ILLEGAL",
                "witness record members differ",
            )
            child_cells = [cells[child - 1] for child in children]
            lower = _checked_add(
                syntax, *(child["lower"] for child in child_cells)
            )
            upper = _checked_add(
                syntax, *(child["upper"] for child in child_cells)
            )
            _require(
                lower <= ambient_ceiling,
                "DERIVATION_INVALID",
                "record lower bound exceeds the ambient ceiling",
            )
            cell = _cell(
                lower,
                min(upper, ambient_ceiling),
            )
        elif opcode == "CELL_UNION_V1":
            rows = parameters["ordered_alternative_records"]
            _require(
                isinstance(rows, list)
                and len(rows) == len(children)
                and all(
                    row["child_step_position"] == child
                    for row, child in zip(rows, children, strict=True)
                )
                and len(
                    {
                        (row["alternative_position"], row["alternative_name"])
                        for row in rows
                    }
                )
                == len(rows),
                "DERIVATION_INVALID",
                "union alternative order differs",
            )
            if case["case_position"] != CASE435_POSITION:
                _require(
                    any(
                        row["alternative_name"] == selected_alternative
                        for row in rows
                    ),
                    "DERIVATION_INVALID",
                    "selected union alternative is absent",
                )
            child_cells = [cells[child - 1] for child in children]
            cell = _cell(
                min(child["lower"] for child in child_cells),
                max(child["upper"] for child in child_cells),
            )
        elif opcode == "CELL_CODEC_INTERSECTION_V1":
            _require(
                children == [parameters["child_step_position"]],
                "DERIVATION_INVALID",
                "codec child differs",
            )
            child = cells[children[0] - 1]
            ceiling = ambient_ceiling
            coordinates = parameters["ordered_codec_coordinate_records"]
            _require(
                isinstance(coordinates, list) and coordinates,
                "DERIVATION_INVALID",
                "codec coordinates are absent",
            )
            for coordinate_position, coordinate in enumerate(coordinates, 1):
                _require(
                    coordinate["coordinate_position"] == coordinate_position,
                    "DERIVATION_INVALID",
                    "codec coordinate order differs",
                )
                relation = coordinate["codec_byte_bound_relation"]
                limit = _u128(coordinate["codec_octet_limit"], "codec limit")
                _require(
                    relation in {"LE", "LT"},
                    "DERIVATION_INVALID",
                    "codec relation differs",
                )
                effective = _checked_sub(limit, int(relation == "LT"))
                sibling = _u128(
                    coordinate["minimum_sibling_and_syntax_octets"],
                    "codec sibling minimum",
                )
                payload_ceiling = 0 if sibling > effective else effective - sibling
                _require(
                    coordinate["derived_payload_octet_ceiling"] == payload_ceiling,
                    "DERIVATION_INVALID",
                    "codec residual differs",
                )
                ceiling = min(ceiling, payload_ceiling)
            _require(
                child["lower"] <= ceiling,
                "DERIVATION_INVALID",
                "codec intersection is empty",
            )
            cell = _cell(
                child["lower"], min(child["upper"], ceiling), child["state"]
            )
        else:
            _reject(
                "UNSUPPORTED_CASE",
                f"A4-P6-V2 does not admit transfer opcode {opcode}",
            )

        _require(
            all(
                cell["lower"] <= actual_length <= cell["upper"]
                for actual_length in actual_lengths_for_step
            ),
            "WITNESS_ILLEGAL",
            f"witness misses step {position} bounds",
        )
        cells.append(cell)
        actual_lengths.append(actual_lengths_for_step)

    _require(
        template["root_step_position"] == len(cells),
        "DERIVATION_INVALID",
        "template root is not last",
    )
    owner_profile_position = None
    if case["case_position"] == CASE69_POSITION:
        cells, owner_profile_position = _condition_case69_profile(
            authorities, case, plan, template, cells, context
        )
    elif case["case_position"] == CASE435_POSITION:
        cells, owner_profile_position = _condition_case435_profile(
            authorities, case, plan, template, cells, context
        )
    root = cells[-1]
    witness_raw = _canonical_bytes(witness)
    _require(
        actual_lengths[-1] == [len(witness_raw)]
        and len(witness_raw) == root["upper"],
        "ATTAINMENT_REJECT",
        "witness does not attain the exact upper bound",
    )

    descriptors = {
        row["type_name"]: row for row in registry["ordered_external_type_descriptors"]
    }
    root_descriptor = descriptors.get(case["case_binding"]["type_name"])
    _require(
        root_descriptor is not None,
        "AUTHORITY_INVALID",
        "ordinary-case root descriptor is absent",
    )
    if root_descriptor["type_form"] == "TAGGED_UNION":
        alternative = next(
            (
                row
                for row in root_descriptor["tagged_union_descriptor"][
                    "ordered_alternatives"
                ]
                if row["alternative_name"]
                == case["case_binding"]["alternative_name"]
            ),
            None,
        )
        _require(
            alternative is not None,
            "AUTHORITY_INVALID",
            "ordinary-case selected union descriptor is absent",
        )
        descriptor = descriptors.get(alternative["referenced_type_name"])
    else:
        _require(
            root_descriptor["type_form"] == "RECORD"
            and case["case_binding"]["alternative_name"] is None,
            "AUTHORITY_INVALID",
            "ordinary-case record/alternative binding differs",
        )
        descriptor = root_descriptor
    _require(
        descriptor is not None and descriptor["type_form"] == "RECORD",
        "AUTHORITY_INVALID",
        "ordinary-case concrete record descriptor is absent",
    )
    record_steps = [
        step
        for step in template["ordered_template_steps"]
        if step["derivation_kind"] == "RECORD_MEMBER_FOLD"
        and (
            case["case_position"] not in {CASE69_POSITION, CASE435_POSITION}
            or step["subject_locator"]["typed_path"] == []
        )
    ]
    _require(
        len(record_steps) == 1
        and [
            row["member_name"]
            for row in record_steps[0]["recurrence_parameters"][
                "ordered_member_records"
            ]
        ]
        == [row["member_name"] for row in descriptor["record_member_descriptors"]],
        "AUTHORITY_INVALID",
        "root descriptor/template member binding differs",
    )
    self_coordinates = [
        coordinate
        for step in template["ordered_template_steps"]
        if step["derivation_kind"] == "CODEC_INTERSECTION"
        for coordinate in step["recurrence_parameters"][
            "ordered_codec_coordinate_records"
        ]
        if coordinate["coordinate_scope"] == "SELF_TYPE"
        and coordinate["codec_owner_type_name"] == descriptor["type_name"]
    ]
    _require(
        any(
            descriptor["codec_byte_bound_relation"]
            == coordinate["codec_byte_bound_relation"]
            and descriptor["codec_octet_limit"] == coordinate["codec_octet_limit"]
            for coordinate in self_coordinates
        ),
        "AUTHORITY_INVALID",
        "root descriptor/plan codec binding differs",
    )
    return template, cells, descriptor, witness_raw, owner_profile_position


def _tagged_subject(schema, values):
    members = schema["ordered_member_names"]
    version_member = members[0]
    complete = {version_member: schema[version_member], **values}
    _require(
        set(complete) == set(members),
        "RESOURCE_DERIVATION_INVALID",
        "tagged subject members differ",
    )
    return {name: complete[name] for name in members}


class _CaseEvents:
    def __init__(self, seed, plan):
        self.seed = seed
        self.plan = plan
        self.recurrence = seed["recurrence_catalog"]
        self.grammar = seed["logical_event_catalog"]["case_level_event_grammar"]
        self.programs = {
            row["program_name"]: row
            for row in self.grammar["ordered_case_program_records"]
        }
        self.metadata = {
            row["program_name"]: row
            for row in self.grammar["event_metadata_program"][
                "ordered_program_metadata_records"
            ]
        }
        self.subject_schemas = {
            row["event_kind"]: row
            for row in self.grammar["ordered_subject_schema_records"]
        }
        execution = self.grammar["full_case_execution_program"]
        self.constructors = {
            row["event_kind"]: row
            for row in execution["ordered_subject_constructor_records"]
        }
        self.metric_programs = {
            row["event_kind"]: row["ordered_metric_update_program"]
            for row in seed["logical_event_catalog"]["ordered_event_kind_records"]
        }
        _require(
            len(self.programs) == len(self.metadata) == 9,
            "AUTHORITY_INVALID",
            "case event programs differ",
        )
        _require(
            len(self.subject_schemas) == len(self.constructors) == 16,
            "AUTHORITY_INVALID",
            "case event constructors differ",
        )
        self.tokens = []
        self.event_ordinals = {}
        self.measurements = dict.fromkeys(range(1, 19), 0)

    def construct(self, event_kind, context):
        constructor = self.constructors[event_kind]
        _require(
            constructor["event_kind"] == event_kind,
            "RESOURCE_DERIVATION_INVALID",
            "subject constructor binding differs",
        )
        if constructor["constructor_opcode"] == "USE_EXACT_HASH_SOURCE_BYTES_V1":
            raw = context.get("ORDERED_CASE_HASH_PROGRAM_SELECTED_PREIMAGE_BYTES")
            _require(
                type(raw) is bytes,
                "RESOURCE_DERIVATION_INVALID",
                "hash preimage bytes are absent",
            )
            return raw
        values = {}
        for position, row in enumerate(constructor["ordered_value_source_records"], 1):
            _require(
                row["value_source_position"] == position,
                "RESOURCE_DERIVATION_INVALID",
                "constructor value order differs",
            )
            source = row["value_source"]
            if source.startswith("CONST:"):
                value = source[6:]
            elif source == "null":
                value = None
            elif source in context:
                value = context[source]
            else:
                _reject(
                    "RESOURCE_DERIVATION_INVALID",
                    f"constructor source is unresolved: {event_kind}:{source}",
                )
            _require(
                row["member_name"] not in values,
                "RESOURCE_DERIVATION_INVALID",
                "constructor member is duplicate",
            )
            values[row["member_name"]] = value
        source = constructor["subject_member_order_source"]
        if source == "CONSTRUCTOR_ORDERED_VALUE_SOURCE_RECORDS":
            members = [
                row["member_name"]
                for row in constructor["ordered_value_source_records"]
            ]
        elif source == "/recurrence_catalog/cache_key_schema/ordered_member_names":
            members = self.recurrence["cache_key_schema"]["ordered_member_names"]
        elif (
            source == "/recurrence_catalog/transition_token_schema/ordered_member_names"
        ):
            members = self.recurrence["transition_token_schema"]["ordered_member_names"]
        elif source == "/recurrence_catalog/result_cell_schema/ordered_member_names":
            members = self.recurrence["result_cell_schema"]["ordered_member_names"]
        elif (
            source == "/recurrence_catalog/step_commitment_schema/ordered_member_names"
        ):
            members = self.recurrence["step_commitment_schema"]["ordered_member_names"]
        elif (
            source
            == "/logical_event_catalog/case_level_event_grammar/final_result_subject_contract/ordered_member_names"
        ):
            members = self.grammar["final_result_subject_contract"][
                "ordered_member_names"
            ]
        else:
            _reject(
                "RESOURCE_DERIVATION_INVALID", "subject member-order source differs"
            )
        _require(
            set(values) == set(members),
            "RESOURCE_DERIVATION_INVALID",
            f"subject members differ: {event_kind}",
        )
        return {name: values[name] for name in members}

    def add(
        self,
        program_name,
        emission_position,
        subject,
        source_record=None,
        collection_ordinal=None,
        derivation_unit_ordinal=None,
        ordinary_step_position=None,
    ):
        program = self.programs[program_name]
        metadata = self.metadata[program_name]
        emission = program["ordered_event_emission_records"][emission_position - 1]
        _require(
            emission["emission_position"] == emission_position,
            "RESOURCE_DERIVATION_INVALID",
            "event emission order differs",
        )
        event_kind = emission["event_kind"]
        source_record = source_record or {}

        def expression_value(expression, default=None):
            opcode = expression["opcode"]
            if opcode == "CONST_U128" and set(expression) == {"opcode", "value"}:
                return _u128(expression["value"], "event constant")
            if opcode == "SOURCE_FIELD_U128" and set(expression) == {
                "opcode",
                "field_name",
            }:
                name = expression["field_name"]
                if name not in source_record:
                    if default is not None:
                        return default
                    _reject(
                        "RESOURCE_DERIVATION_INVALID",
                        f"event source field is absent: {name}",
                    )
                return _u128(source_record[name], f"event source field {name}")
            _reject("RESOURCE_DERIVATION_INVALID", "event expression opcode differs")

        _require(
            expression_value(emission["condition_expression"]) == 1,
            "RESOURCE_DERIVATION_INVALID",
            "event condition is false",
        )
        aggregation = expression_value(
            emission["aggregation_multiplicity_expression"], 1
        )
        logical = expression_value(
            emission["logical_unbatched_equivalent_count_expression"], 0
        )
        ordinal = self.event_ordinals.get(event_kind, 0) + 1
        ordinal_source = metadata["subject_ordinal_sources"][emission_position - 1]
        if ordinal_source == "NULL":
            subject_ordinal = None
        elif ordinal_source == "EMISSION_SUBJECT_COLLECTION_ORDINAL":
            subject_ordinal = collection_ordinal
        elif ordinal_source == "EVENT_KIND_ORDINAL":
            subject_ordinal = ordinal
        elif ordinal_source == "DERIVATION_UNIT_ORDINAL":
            subject_ordinal = derivation_unit_ordinal
        else:
            _reject(
                "RESOURCE_DERIVATION_INVALID", "event subject-ordinal source differs"
            )
        _require(
            ordinal_source == "NULL" or subject_ordinal is not None,
            "RESOURCE_DERIVATION_INVALID",
            "event subject ordinal is unresolved",
        )
        step_source = metadata["logical_derivation_step_position_source"]
        step_position = (
            ordinary_step_position
            if step_source == "CURRENT_ORDINARY_TEMPLATE_STEP_POSITION"
            else None
        )
        _require(
            step_source in {"CURRENT_ORDINARY_TEMPLATE_STEP_POSITION", "NULL"},
            "RESOURCE_DERIVATION_INVALID",
            "event step source differs",
        )
        _require(
            step_source == "NULL" or step_position is not None,
            "RESOURCE_DERIVATION_INVALID",
            "event step is unresolved",
        )
        observed_source = metadata["observed_value_sources"][emission_position - 1]
        if observed_source == "NULL":
            observed = None
        elif observed_source == "SUBJECT_OBSERVED_VALUE":
            _require(
                isinstance(subject, dict),
                "RESOURCE_DERIVATION_INVALID",
                "observed subject differs",
            )
            observed = subject.get(
                "observed_value",
                subject.get("derived_depth", subject.get("iteration_depth")),
            )
            _u128(observed, "observed event value")
        else:
            _reject(
                "RESOURCE_DERIVATION_INVALID", "event observed-value source differs"
            )
        raw = subject if type(subject) is bytes else _canonical_bytes(subject)
        schema = self.subject_schemas[event_kind]
        token = {
            "event_position": len(self.tokens) + 1,
            "execution_phase": emission["execution_phase"],
            "logical_derivation_step_position": step_position,
            "event_kind": event_kind,
            "event_ordinal": ordinal,
            "subject_schema_version": schema["subject_schema_version"],
            "subject_kind": schema["subject_kind"],
            "subject_role": metadata["ordered_subject_role_literals"][
                emission_position - 1
            ],
            "subject_ordinal": subject_ordinal,
            "subject_canonical_octets": len(raw),
            "subject_sha256": _sha256(raw),
            "aggregation_multiplicity": aggregation,
            "logical_unbatched_equivalent_count": logical,
            "observed_value": observed,
        }
        self.tokens.append(token)
        self.event_ordinals[event_kind] = ordinal
        for update in self.metric_programs[event_kind]:
            source = update["value_source"]
            if source == "ONE":
                value = 1
            elif source == "SUBJECT_CANONICAL_OCTETS":
                value = len(raw)
            elif source == "AGGREGATION_MULTIPLICITY":
                value = aggregation
            elif source == "LOGICAL_UNBATCHED_EQUIVALENT_COUNT":
                value = logical
            elif source == "OBSERVED_VALUE":
                value = observed
            else:
                _reject("RESOURCE_DERIVATION_INVALID", "metric value source differs")
            value = _u128(value, "metric event value")
            metric_position = update["metric_position"]
            if update["update_kind"] == "ADD":
                self.measurements[metric_position] = _checked_add(
                    self.measurements[metric_position], value
                )
            elif update["update_kind"] == "MAX":
                self.measurements[metric_position] = max(
                    self.measurements[metric_position], value
                )
            else:
                _reject("RESOURCE_DERIVATION_INVALID", "metric update kind differs")
        return raw


def _base_context(events):
    plan = events.plan
    recurrence = events.recurrence
    return {
        "PLAN.case_position": plan["case_position"],
        "PLAN.case_kind": plan["case_kind"],
        "PLAN.logical_count_plan_id": plan["logical_count_plan_id"],
        "PLAN.local_analytic_catalog_id": plan["local_analytic_catalog_id"],
        "PLAN.scope_summary.schedule_authority_id": plan["scope_summary"][
            "schedule_authority_id"
        ],
        "PLAN.scope_summary.cross_rule_evaluation_count": plan["scope_summary"][
            "cross_rule_evaluation_count"
        ],
        "PLAN.scope_summary.application_invocation_count": plan["scope_summary"][
            "application_invocation_count"
        ],
        "RECURRENCE.cache_key_schema.cache_key_version": recurrence["cache_key_schema"][
            "cache_key_version"
        ],
        "RECURRENCE.transition_token_schema.transition_token_version": recurrence[
            "transition_token_schema"
        ]["transition_token_version"],
        "RECURRENCE.result_cell_schema.result_cell_version": recurrence[
            "result_cell_schema"
        ]["result_cell_version"],
        "RECURRENCE.step_commitment_schema.step_commitment_version": recurrence[
            "step_commitment_schema"
        ]["step_commitment_version"],
    }


def _live_entries(raw_pairs, commitment_digests):
    entries = []
    for pair in sorted(raw_pairs, key=lambda item: item["key_raw"]):
        entries.extend(
            [
                {
                    "entry_kind": "RECURRENCE_CACHE_KEY_V2",
                    "entry_id": pair["key_sha256"],
                    "canonical_octets": len(pair["key_raw"]),
                },
                {
                    "entry_kind": "RECURRENCE_RESULT_CELL_V2",
                    "entry_id": pair["cell_sha256"],
                    "canonical_octets": len(pair["cell_raw"]),
                },
            ]
        )
    entries.extend(
        {
            "entry_kind": "STEP_COMMITMENT_DIGEST_V1",
            "entry_id": digest,
            "canonical_octets": 32,
        }
        for digest in commitment_digests
    )
    return entries


def _retention_context(events, entries, label):
    observed = _checked_add(*(row["canonical_octets"] for row in entries))
    return {
        "CONTIGUOUS_ONE_BASED_RETENTION_OBSERVATION_ORDINAL": events.event_ordinals.get(
            "RETENTION_OBSERVATION", 0
        )
        + 1,
        "RETENTION.observation_label": label,
        "RETENTION.ordered_live_entry_records": entries,
        "SUM:RETENTION.ordered_live_entry_records.canonical_octets": observed,
    }


def _ordinary_case_units(events, template, cells, owner_profile_position=None):
    base = _base_context(events)
    plan = events.plan
    recurrence = events.recurrence
    ceiling = recurrence["arithmetic_policy"]["published_maximum"]
    steps = template["ordered_template_steps"]
    last_parent = {position: position for position in range(1, len(steps) + 1)}
    for parent in steps:
        for child in parent["ordered_child_step_positions"]:
            last_parent[child] = max(
                last_parent[child], parent["template_step_position"]
            )
    active_pairs = {}
    commitment_digests = []
    commitment_records = []
    root_pair = None
    depths = []
    iterations = []
    intrinsic_rule_ids = []
    for position, (step, cell) in enumerate(zip(steps, cells, strict=True), 1):
        child_depths = [
            depths[child - 1] for child in step["ordered_child_step_positions"]
        ]
        depths.append(1 if not child_depths else 1 + max(child_depths))
        kind = step["derivation_kind"]
        if kind == "ASSOCIATIVE_HOMOGENEOUS_RUN_BATCH":
            maximum_items = step["recurrence_parameters"]["maximum_items"]
            iteration = 0 if maximum_items <= 1 else (maximum_items - 1).bit_length()
        elif kind == "ARRAY_STREAM_FOLD":
            iteration = step["recurrence_parameters"]["maximum_items"]
        elif kind == "APPLICATION_SCHEDULE_COUNT":
            iteration = len(
                step["recurrence_parameters"]["ordered_application_invocation_records"]
            )
        else:
            iteration = step["physical_transition_count"]
        iterations.append(_u128(iteration, "ordinary iteration depth"))
        intrinsic_rule_ids.extend(step["ordered_intrinsic_rule_ids"])
        unit = {
            "UNIT.subject_variant": "ORDINARY_STEP",
            "UNIT.logical_derivation_step_position": position,
            "UNIT.logical_derivation_step_id": step["logical_derivation_step_id"],
            "UNIT.derivation_kind": kind,
            "UNIT.effective_canonical_octet_ceiling": ceiling,
            "UNIT.state_signature_id": step["state_signature_id"],
            "UNIT.owner_profile_position": owner_profile_position,
        }
        cell_context = {
            **base,
            **unit,
            "CELL.state_signature_id": step["state_signature_id"],
            "CELL.ordered_state_components": list(cell["state"]),
            "CELL.cell_status": cell["status"],
            "CELL.certified_lower_bound_octets": cell["lower"],
            "CELL.certified_upper_bound_octets": cell["upper"],
            "ORDINARY:STEP.template_step_position|LOCAL:null": position,
            "ORDINARY:CONST_U128_1|LOCAL:null": 1,
            "ORDINARY:null|LOCAL:CONTROLLER_STATE.controller_state_position": None,
            "ORDINARY:null|LOCAL:CONTROLLER_STATE.controller_state_id": None,
        }
        result_cell = events.construct("RESULT_CELL_EMIT", cell_context)
        result_raw = _canonical_bytes(result_cell)
        result_sha = _sha256(result_raw)
        key_context = {
            **base,
            **unit,
            "CELL.ordered_state_components": list(cell["state"]),
            "ORDINARY:STEP.template_step_position|LOCAL:null": position,
            "ORDINARY:STEP.derivation_kind|LOCAL:null": kind,
            "ORDINARY:CONST_U128_1|LOCAL:null": 1,
            "ORDINARY:null|LOCAL:CONTROLLER_STATE.controller_state_position": None,
            "ORDINARY:null|LOCAL:CONTROLLER_STATE.controller_state_id": None,
        }
        cache_key = events.construct("CACHE_INSERT", key_context)
        key_raw = _canonical_bytes(cache_key)
        pair = {
            "position": position,
            "key_raw": key_raw,
            "key_sha256": _sha256(key_raw),
            "cell_raw": result_raw,
            "cell_sha256": result_sha,
        }
        transition_subjects = []
        physical = _u128(step["physical_transition_count"], "physical transitions")
        logical = _u128(
            step["logical_unbatched_transition_equivalent_count"], "logical transitions"
        )
        _require(
            physical > 0 and logical >= physical,
            "RESOURCE_DERIVATION_INVALID",
            "transition run differs",
        )
        quotient, remainder = divmod(logical, physical)
        for ordinal in range(1, physical + 1):
            transition_context = {
                **base,
                **unit,
                "TRANSITION.physical_transition_ordinal": ordinal,
                "ORDINARY:ORDINARY_KERNEL_TRANSITION|LOCAL:LOCAL_CONTROLLER_TRANSITION": "ORDINARY_KERNEL_TRANSITION",
                "TRANSITION.source_state_components": list(cell["state"]),
                "TRANSITION.input_symbol": {
                    "derivation_kind": kind,
                    "physical_transition_ordinal": ordinal,
                },
                "TRANSITION.candidate_state_components": list(cell["state"]),
                "TRANSITION.candidate_certified_upper_bound_octets": cell["upper"],
                "ORDINARY:STEP.template_step_position|LOCAL:null": position,
                "ORDINARY:null|LOCAL:CONTROLLER_TRANSITION.controller_transition_position": None,
                "ORDINARY:null|LOCAL:CONTROLLER_TRANSITION.controller_transition_id": None,
                "ORDINARY:null|LOCAL:CONTROLLER_TRANSITION.source_controller_state_id": None,
                "ORDINARY:null|LOCAL:CONTROLLER_TRANSITION.target_controller_state_id": None,
            }
            transition_subjects.append(
                (
                    events.construct("TRANSITION_ATTEMPT", transition_context),
                    quotient + int(ordinal <= remainder),
                )
            )
        _require(
            sum(row[1] for row in transition_subjects) == logical,
            "RESOURCE_DERIVATION_INVALID",
            "transition distribution differs",
        )
        batch_subjects = []
        for ordinal in range(1, step["physical_batch_application_count"] + 1):
            batch_subjects.append(
                events.construct(
                    "BATCH_APPLICATION",
                    {
                        **base,
                        "STEP.template_step_position": position,
                        "BATCH.physical_batch_ordinal": ordinal,
                        "STEP.derivation_kind": kind,
                        "STEP.logical_transfer_multiplicity": step[
                            "logical_transfer_multiplicity"
                        ],
                    },
                )
            )
        commitment_context = {
            **base,
            **unit,
            "UNIT.ordered_result_cells.LENGTH": 1,
            "MAXIMUM:UNIT.ordered_result_cells.certified_upper_bound_octets": cell[
                "upper"
            ],
            "UNIT.ordered_result_cells.CANONICAL_SHA256": [result_sha],
            "ORDINARY:STEP.template_step_position|LOCAL:null": position,
            "ORDINARY:null|LOCAL:PLAN.local_analytic_catalog_id": None,
            "ORDINARY:null|LOCAL:INITIAL_CONTROLLER_STATE.controller_state_id": None,
            "ORDINARY:null|LOCAL:TERMINAL_CONTROLLER_STATE.controller_state_id": None,
        }
        commitment = events.construct("STEP_COMMITMENT_EMIT", commitment_context)
        commitment_raw = _canonical_bytes(commitment)
        commitment_sha = _sha256(commitment_raw)
        commitment_records.append(
            {
                "derivation_unit_ordinal": position,
                "subject_variant": "ORDINARY_STEP",
                "logical_derivation_step_position": position,
                "local_controller_unit_ordinal": None,
                "step_commitment_sha256": commitment_sha,
            }
        )
        descriptor = events.construct("LOGICAL_DESCRIPTOR_VISIT", {**base, **unit})
        events.add(
            "ORDINARY_POSTORDER_STEPS",
            1,
            descriptor,
            {"aggregation_multiplicity": step["logical_descriptor_occurrence_count"]},
            ordinary_step_position=position,
        )
        for ordinal, (subject, logical_count) in enumerate(transition_subjects, 1):
            events.add(
                "ORDINARY_POSTORDER_STEPS",
                2,
                subject,
                {"logical_unbatched_equivalent_count": logical_count},
                collection_ordinal=ordinal,
                ordinary_step_position=position,
            )
        for ordinal, subject in enumerate(batch_subjects, 1):
            events.add(
                "ORDINARY_POSTORDER_STEPS",
                3,
                subject,
                collection_ordinal=ordinal,
                ordinary_step_position=position,
            )
        events.add(
            "ORDINARY_POSTORDER_STEPS",
            4,
            result_cell,
            collection_ordinal=1,
            ordinary_step_position=position,
        )
        events.add(
            "ORDINARY_POSTORDER_STEPS",
            5,
            cache_key,
            collection_ordinal=1,
            ordinary_step_position=position,
        )
        active_pairs[position] = pair
        retention = events.construct(
            "RETENTION_OBSERVATION",
            _retention_context(
                events,
                _live_entries(list(active_pairs.values()), commitment_digests),
                "LIVE_CHILDREN_PLUS_PROSPECTIVE_PARENT",
            ),
        )
        events.add(
            "ORDINARY_POSTORDER_STEPS", 6, retention, ordinary_step_position=position
        )
        events.add(
            "ORDINARY_POSTORDER_STEPS",
            7,
            events.construct(
                "HASH_PREIMAGE",
                {"ORDERED_CASE_HASH_PROGRAM_SELECTED_PREIMAGE_BYTES": result_raw},
            ),
            ordinary_step_position=position,
        )
        events.add(
            "ORDINARY_POSTORDER_STEPS",
            8,
            commitment,
            derivation_unit_ordinal=position,
            ordinary_step_position=position,
        )
        events.add(
            "ORDINARY_POSTORDER_STEPS",
            9,
            events.construct(
                "HASH_PREIMAGE",
                {"ORDERED_CASE_HASH_PROGRAM_SELECTED_PREIMAGE_BYTES": commitment_raw},
            ),
            ordinary_step_position=position,
        )
        commitment_digests.append(commitment_sha)
        for retained_position in list(active_pairs):
            if last_parent[retained_position] <= position:
                del active_pairs[retained_position]
        retention = events.construct(
            "RETENTION_OBSERVATION",
            _retention_context(
                events,
                _live_entries(list(active_pairs.values()), commitment_digests),
                "AFTER_PARENT_COMMITMENT_HASH_AND_RELEASE",
            ),
        )
        events.add(
            "ORDINARY_POSTORDER_STEPS", 10, retention, ordinary_step_position=position
        )
        if position == plan["root_step_position"]:
            root_pair = pair
    _require(
        root_pair is not None and not active_pairs,
        "RESOURCE_DERIVATION_INVALID",
        "root/release program did not close",
    )
    return {
        "commitment_digests": commitment_digests,
        "commitment_records": commitment_records,
        "root_pair": root_pair,
        "maximum_derivation_depth": max(depths),
        "maximum_iteration_depth": max(
            max(iterations), plan["scope_summary"]["application_invocation_count"]
        ),
        "intrinsic_rule_ids": intrinsic_rule_ids,
    }


def _local_case_units(events):
    base = _base_context(events)
    plan = events.plan
    recurrence = events.recurrence
    local = recurrence["local_shutdown_analytic_catalog"]
    ceiling = recurrence["arithmetic_policy"]["published_maximum"]
    states = local["ordered_controller_state_records"]
    transitions = local["ordered_controller_transition_records"]
    _require(
        len(states) == 12 and len(transitions) == 11,
        "RESOURCE_DERIVATION_INVALID",
        "local controller cardinality differs",
    )
    cells = []
    pairs = []
    for position, state in enumerate(states, 1):
        _require(
            state["controller_state_position"] == position,
            "RESOURCE_DERIVATION_INVALID",
            "local state order differs",
        )
        components = state["ordered_state_components"]
        upper = (
            local["baseline_attainable_maximum_octets"]
            if position == 1
            else components[7]
            if position == 12
            else components[3]
        )
        cell = _cell(0, _u128(upper, "local cell upper"), components)
        unit = {
            "UNIT.subject_variant": "LOCAL_CONTROLLER",
            "UNIT.logical_derivation_step_position": None,
            "UNIT.logical_derivation_step_id": plan["local_analytic_catalog_id"],
            "UNIT.derivation_kind": "LOCAL_SHUTDOWN_ANALYTIC_CONTROLLER",
            "UNIT.effective_canonical_octet_ceiling": ceiling,
            "UNIT.state_signature_id": local["state_signature_id"],
            "UNIT.owner_profile_position": None,
        }
        result = events.construct(
            "RESULT_CELL_EMIT",
            {
                **base,
                **unit,
                "CELL.state_signature_id": local["state_signature_id"],
                "CELL.ordered_state_components": components,
                "CELL.cell_status": cell["status"],
                "CELL.certified_lower_bound_octets": cell["lower"],
                "CELL.certified_upper_bound_octets": cell["upper"],
                "ORDINARY:STEP.template_step_position|LOCAL:null": None,
                "ORDINARY:CONST_U128_1|LOCAL:null": None,
                "ORDINARY:null|LOCAL:CONTROLLER_STATE.controller_state_position": position,
                "ORDINARY:null|LOCAL:CONTROLLER_STATE.controller_state_id": state[
                    "controller_state_id"
                ],
            },
        )
        result_raw = _canonical_bytes(result)
        key = events.construct(
            "CACHE_INSERT",
            {
                **base,
                **unit,
                "CELL.ordered_state_components": components,
                "ORDINARY:STEP.template_step_position|LOCAL:null": None,
                "ORDINARY:STEP.derivation_kind|LOCAL:null": None,
                "ORDINARY:CONST_U128_1|LOCAL:null": None,
                "ORDINARY:null|LOCAL:CONTROLLER_STATE.controller_state_position": position,
                "ORDINARY:null|LOCAL:CONTROLLER_STATE.controller_state_id": state[
                    "controller_state_id"
                ],
            },
        )
        key_raw = _canonical_bytes(key)
        cells.append((state, cell, result))
        pairs.append(
            {
                "position": position,
                "key": key,
                "key_raw": key_raw,
                "key_sha256": _sha256(key_raw),
                "cell": result,
                "cell_raw": result_raw,
                "cell_sha256": _sha256(result_raw),
            }
        )
    transition_subjects = []
    for position, transition in enumerate(transitions, 1):
        source_state = states[position - 1]
        target_state = states[position]
        _require(
            transition["controller_transition_position"] == position
            and transition["source_controller_state_id"]
            == source_state["controller_state_id"]
            and transition["target_controller_state_id"]
            == target_state["controller_state_id"]
            and transition["expected_target_state_components"]
            == target_state["ordered_state_components"],
            "RESOURCE_DERIVATION_INVALID",
            "local transition adjacency differs",
        )
        transition_subjects.append(
            events.construct(
                "TRANSITION_ATTEMPT",
                {
                    **base,
                    "UNIT.subject_variant": "LOCAL_CONTROLLER",
                    "TRANSITION.physical_transition_ordinal": position,
                    "ORDINARY:ORDINARY_KERNEL_TRANSITION|LOCAL:LOCAL_CONTROLLER_TRANSITION": "LOCAL_CONTROLLER_TRANSITION",
                    "TRANSITION.source_state_components": source_state[
                        "ordered_state_components"
                    ],
                    "TRANSITION.input_symbol": transition[
                        "input_mutable_limit_lexical_position"
                    ],
                    "TRANSITION.candidate_state_components": transition[
                        "expected_target_state_components"
                    ],
                    "TRANSITION.candidate_certified_upper_bound_octets": cells[
                        position
                    ][1]["upper"],
                    "ORDINARY:STEP.template_step_position|LOCAL:null": None,
                    "ORDINARY:null|LOCAL:CONTROLLER_TRANSITION.controller_transition_position": position,
                    "ORDINARY:null|LOCAL:CONTROLLER_TRANSITION.controller_transition_id": transition[
                        "controller_transition_id"
                    ],
                    "ORDINARY:null|LOCAL:CONTROLLER_TRANSITION.source_controller_state_id": transition[
                        "source_controller_state_id"
                    ],
                    "ORDINARY:null|LOCAL:CONTROLLER_TRANSITION.target_controller_state_id": transition[
                        "target_controller_state_id"
                    ],
                },
            )
        )
    intrinsic_ids = next(
        row["ordered_authority_values"]
        for row in local["controller_metric_count_program"][
            "ordered_exact_non_byte_metric_records"
        ]
        if row["metric_position"] == 12
    )
    unit = {
        "UNIT.subject_variant": "LOCAL_CONTROLLER",
        "UNIT.logical_derivation_step_position": None,
        "UNIT.logical_derivation_step_id": plan["local_analytic_catalog_id"],
        "UNIT.derivation_kind": "LOCAL_SHUTDOWN_ANALYTIC_CONTROLLER",
    }
    events.add(
        "LOCAL_CONTROLLER",
        1,
        events.construct("LOGICAL_DESCRIPTOR_VISIT", {**base, **unit}),
        {"aggregation_multiplicity": len(transitions)},
    )
    for ordinal, subject in enumerate(transition_subjects, 1):
        events.add(
            "LOCAL_CONTROLLER",
            2,
            subject,
            {"logical_unbatched_equivalent_count": 1},
            collection_ordinal=ordinal,
        )
    intrinsic = events.construct(
        "INTRINSIC_RULE_EVALUATION",
        {
            **base,
            "ORDINARY:TEMPLATE_STEPS.ordered_intrinsic_rule_ids|LOCAL:LOCAL_METRIC_PROGRAM.metric_12.ordered_authority_values": intrinsic_ids,
            "ORDERED_INTRINSIC_RULE_IDS.LENGTH": len(intrinsic_ids),
        },
    )
    events.add(
        "LOCAL_CONTROLLER",
        3,
        intrinsic,
        {"aggregation_multiplicity": len(intrinsic_ids)},
    )
    for ordinal, pair in enumerate(pairs, 1):
        events.add("LOCAL_CONTROLLER", 4, pair["cell"], collection_ordinal=ordinal)
    for ordinal, pair in enumerate(pairs, 1):
        events.add("LOCAL_CONTROLLER", 5, pair["key"], collection_ordinal=ordinal)
    events.add(
        "LOCAL_CONTROLLER",
        6,
        events.construct(
            "RETENTION_OBSERVATION",
            _retention_context(
                events,
                _live_entries(pairs, []),
                "LIVE_CHILDREN_PLUS_PROSPECTIVE_PARENT",
            ),
        ),
    )
    for pair in sorted(pairs, key=lambda item: item["key_raw"]):
        events.add(
            "LOCAL_CONTROLLER",
            7,
            events.construct(
                "HASH_PREIMAGE",
                {
                    "ORDERED_CASE_HASH_PROGRAM_SELECTED_PREIMAGE_BYTES": pair[
                        "cell_raw"
                    ]
                },
            ),
        )
    initial = states[local["initial_controller_state_position"] - 1]
    terminal = states[local["terminal_controller_state_position"] - 1]
    commitment = events.construct(
        "STEP_COMMITMENT_EMIT",
        {
            **base,
            "UNIT.subject_variant": "LOCAL_CONTROLLER",
            "UNIT.ordered_result_cells.LENGTH": len(pairs),
            "MAXIMUM:UNIT.ordered_result_cells.certified_upper_bound_octets": max(
                cell[1]["upper"] for cell in cells
            ),
            "UNIT.ordered_result_cells.CANONICAL_SHA256": [
                pair["cell_sha256"] for pair in pairs
            ],
            "ORDINARY:STEP.template_step_position|LOCAL:null": None,
            "ORDINARY:null|LOCAL:PLAN.local_analytic_catalog_id": plan[
                "local_analytic_catalog_id"
            ],
            "ORDINARY:null|LOCAL:INITIAL_CONTROLLER_STATE.controller_state_id": initial[
                "controller_state_id"
            ],
            "ORDINARY:null|LOCAL:TERMINAL_CONTROLLER_STATE.controller_state_id": terminal[
                "controller_state_id"
            ],
        },
    )
    commitment_raw = _canonical_bytes(commitment)
    commitment_sha = _sha256(commitment_raw)
    events.add("LOCAL_CONTROLLER", 8, commitment, derivation_unit_ordinal=1)
    events.add(
        "LOCAL_CONTROLLER",
        9,
        events.construct(
            "HASH_PREIMAGE",
            {"ORDERED_CASE_HASH_PROGRAM_SELECTED_PREIMAGE_BYTES": commitment_raw},
        ),
    )
    events.add(
        "LOCAL_CONTROLLER",
        10,
        events.construct(
            "RETENTION_OBSERVATION",
            _retention_context(
                events,
                _live_entries([], [commitment_sha]),
                "AFTER_PARENT_COMMITMENT_HASH_AND_RELEASE",
            ),
        ),
    )
    return {
        "commitment_digests": [commitment_sha],
        "commitment_records": [
            {
                "derivation_unit_ordinal": 1,
                "subject_variant": "LOCAL_CONTROLLER",
                "logical_derivation_step_position": None,
                "local_controller_unit_ordinal": 1,
                "step_commitment_sha256": commitment_sha,
            }
        ],
        "root_pair": pairs[-1],
        "maximum_derivation_depth": 1,
        "maximum_iteration_depth": len(transitions),
        "intrinsic_rule_ids": intrinsic_ids,
    }


def _event_stream_version(seed):
    record = next(
        (
            row
            for row in seed["ordered_identity_domain_records"]
            if row["identity_name"] == "LOGICAL_EVENT_STREAM"
        ),
        None,
    )
    _require(
        record is not None,
        "AUTHORITY_INVALID",
        "logical event-stream identity is absent",
    )
    return record["version_literal"]


def _finalize_case_events(events, unit_result, seed, manifest):
    base = _base_context(events)
    plan = events.plan
    intrinsic_ids = unit_result["intrinsic_rule_ids"]
    if intrinsic_ids:
        intrinsic = events.construct(
            "INTRINSIC_RULE_EVALUATION",
            {
                **base,
                "ORDINARY:TEMPLATE_STEPS.ordered_intrinsic_rule_ids|LOCAL:LOCAL_METRIC_PROGRAM.metric_12.ordered_authority_values": intrinsic_ids,
                "ORDERED_INTRINSIC_RULE_IDS.LENGTH": len(intrinsic_ids),
            },
        )
        events.add(
            "EXACT_ATTAINER_VALIDATION",
            1,
            intrinsic,
            {"aggregation_multiplicity": len(intrinsic_ids)},
        )
    scope = plan["scope_summary"]
    application_count = _u128(
        scope["application_invocation_count"], "application count"
    )
    cross_count = _u128(scope["cross_rule_evaluation_count"], "cross-rule count")
    if application_count or cross_count:
        _require(
            isinstance(scope["schedule_authority_id"], str),
            "RESOURCE_DERIVATION_INVALID",
            "nonempty scope has no schedule authority",
        )
    if application_count:
        application = events.construct("APPLICATION_EVALUATION", base)
        events.add(
            "SCOPE_APPLICATIONS",
            1,
            application,
            {"aggregation_multiplicity": application_count},
            collection_ordinal=1,
        )
    if cross_count:
        cross = events.construct("CROSS_RULE_EVALUATION", base)
        events.add(
            "SCOPE_APPLICATIONS",
            2,
            cross,
            {"aggregation_multiplicity": cross_count},
            collection_ordinal=1,
        )
    depth = events.construct(
        "DERIVATION_DEPTH_OBSERVATION",
        {
            **base,
            "DEPTH.maximum_derivation_depth": unit_result["maximum_derivation_depth"],
        },
    )
    events.add("DEPTH_AND_RETENTION", 1, depth)
    iteration = events.construct(
        "ITERATION_DEPTH_OBSERVATION",
        {
            **base,
            "DEPTH.maximum_iteration_depth": unit_result["maximum_iteration_depth"],
        },
    )
    events.add("DEPTH_AND_RETENTION", 2, iteration)
    retention = events.construct(
        "RETENTION_OBSERVATION",
        _retention_context(
            events,
            _live_entries([], unit_result["commitment_digests"]),
            "ROOT_COMMITMENT_DIGEST_THROUGH_FINAL_RESULT_HASH",
        ),
    )
    events.add("DEPTH_AND_RETENTION", 3, retention)
    root_pair = unit_result["root_pair"]
    final_result = events.construct(
        "FINAL_RESULT_EMIT",
        {
            **base,
            "ROOT_RESULT_CELLS.IN_CANONICAL_CELL_KEY_ORDER.DIGEST_RECORDS": [
                {
                    "result_cell_ordinal": 1,
                    "result_cell_sha256": root_pair["cell_sha256"],
                }
            ],
            "DERIVATION_UNITS.IN_POSTORDER.COMMITMENT_DIGEST_RECORDS": unit_result[
                "commitment_records"
            ],
        },
    )
    final_raw = events.add("FINAL_RESULT", 1, final_result)
    events.add(
        "FINAL_RESULT",
        2,
        events.construct(
            "HASH_PREIMAGE",
            {"ORDERED_CASE_HASH_PROGRAM_SELECTED_PREIMAGE_BYTES": final_raw},
        ),
    )
    preimage_members = events.grammar["stream_finalization_program"][
        "preimage_member_names"
    ]
    stream_payload = {
        "logical_event_stream_version": _event_stream_version(seed),
        "logical_count_plan_id": plan["logical_count_plan_id"],
        "ordered_pre_close_logical_event_tokens": list(events.tokens),
    }
    _require(
        list(stream_payload) == preimage_members,
        "RESOURCE_DERIVATION_INVALID",
        "event-stream preimage order differs",
    )
    stream_raw = _canonical_bytes(stream_payload)
    stream_sha = _sha256(stream_raw)
    close = events.construct(
        "EVENT_STREAM_CLOSE",
        {
            **base,
            "EVENT_STREAM_PREIMAGE.RAW_OCTET_COUNT": len(stream_raw),
            "EVENT_STREAM_PREIMAGE.SHA256": stream_sha,
        },
    )
    events.add("STREAM_FINALIZATION", 1, close)
    events.add(
        "STREAM_FINALIZATION",
        2,
        events.construct(
            "HASH_PREIMAGE",
            {"ORDERED_CASE_HASH_PROGRAM_SELECTED_PREIMAGE_BYTES": stream_raw},
        ),
    )
    _require(
        [row["event_position"] for row in events.tokens]
        == list(range(1, len(events.tokens) + 1)),
        "RESOURCE_DERIVATION_INVALID",
        "event positions differ",
    )

    metric_rows = seed["resource_metric_catalog"]["ordered_metric_records"]
    f2_rows = manifest["ordered_f2_limit_records"]
    _require(
        len(metric_rows) == len(f2_rows) == 18,
        "AUTHORITY_INVALID",
        "resource metric cardinality differs",
    )
    measurements = []
    for position, (metric, limit) in enumerate(
        zip(metric_rows, f2_rows, strict=True), 1
    ):
        _require(
            metric["metric_position"] == limit["metric_position"] == position,
            "AUTHORITY_INVALID",
            "resource metric order differs",
        )
        _require(
            metric["metric_name"] == limit["metric_name"],
            "AUTHORITY_INVALID",
            "resource metric name differs",
        )
        measured = _u128(events.measurements[position], "resource measurement")
        _require(
            measured <= limit["f2_per_case"],
            "RESOURCE_LIMIT_EXCEEDED",
            f"metric {position} exceeds frozen F2",
        )
        measurements.append(
            {
                "metric_position": position,
                "metric_name": metric["metric_name"],
                "measured_value": measured,
            }
        )
    return measurements, stream_sha


def _derive_case_resources(
    seed, manifest, plan, template, cells, owner_profile_position=None
):
    events = _CaseEvents(seed, plan)
    base = _base_context(events)
    events.add("CASE_OPEN", 1, events.construct("CASE_OPEN", base))
    plan_raw = _plan_identity_preimage(seed, plan)
    events.add(
        "BOUND_PLAN_HASH_PREIMAGE",
        1,
        events.construct(
            "HASH_PREIMAGE",
            {"ORDERED_CASE_HASH_PROGRAM_SELECTED_PREIMAGE_BYTES": plan_raw},
        ),
    )
    unit_result = _ordinary_case_units(
        events, template, cells, owner_profile_position
    )
    return _finalize_case_events(events, unit_result, seed, manifest)


def _derive_local_case_resources(seed, manifest, plan):
    events = _CaseEvents(seed, plan)
    base = _base_context(events)
    events.add("CASE_OPEN", 1, events.construct("CASE_OPEN", base))
    plan_raw = _plan_identity_preimage(seed, plan)
    events.add(
        "BOUND_PLAN_HASH_PREIMAGE",
        1,
        events.construct(
            "HASH_PREIMAGE",
            {"ORDERED_CASE_HASH_PROGRAM_SELECTED_PREIMAGE_BYTES": plan_raw},
        ),
    )
    return _finalize_case_events(
        events, _local_case_units(events), seed, manifest
    )


def _authority_provenance(authorities):
    seed = authorities["seed"]
    rows = {
        row["authority_role"]: row for row in seed["ordered_authority_binding_records"]
    }
    inventory_row = rows["V4_INVENTORY"]
    registry_row = rows["STRUCTURAL_REGISTRY"]
    literal_row = rows["RULE_LITERAL_AUTHORITY"]
    inventory = _strict_loads(
        authorities["authority_bytes"]["V4_INVENTORY"], authorities["limits"]
    )
    inventory_payload = {
        name: value for name, value in inventory.items() if name != "inventory_sha256"
    }
    _require(
        inventory.get("inventory_sha256")
        == _sha256(_canonical_bytes(inventory_payload))
        == inventory_row["semantic_id"],
        "AUTHORITY_INVALID",
        "V4 inventory semantic identity differs",
    )
    registry = authorities["registry"]
    registry_payload = {
        name: value
        for name, value in registry.items()
        if name
        not in {
            "canonicalization_version",
            "measurement_schema_version",
            "record_domain",
            "external_schema_registry_id",
        }
    }
    _require(
        registry.get("record_domain") == REGISTRY_DOMAIN
        and registry.get("external_schema_registry_id")
        == _seed_semantic_id(registry, REGISTRY_DOMAIN, registry_payload)
        == registry_row["semantic_id"],
        "AUTHORITY_INVALID",
        "structural registry semantic identity differs",
    )
    _require(
        inventory["external_schema_registry_v2"]["external_schema_registry_id"]
        == registry["external_schema_registry_id"],
        "AUTHORITY_INVALID",
        "inventory/registry identity binding differs",
    )
    return (
        inventory_row["semantic_id"],
        registry_row["semantic_id"],
        literal_row["raw_sha256"],
    )


def _constraint_scope(
    authorities, case, context, source_inventory, registry_id, literal_sha
):
    binding = case["case_binding"]
    if case["case_position"] == CASE24_POSITION:
        _require(
            binding["row_kind"] == "INTRINSIC_UNION_ALTERNATIVE",
            "AUTHORITY_INVALID",
            "case 24 row kind differs",
        )
        measurement_binding = {
            "binding_kind": "OWNER_MEMBER_UNION_VALUE",
            "validation_root_type_name": CASE24_OWNER_TYPE,
            "measured_value_typed_member_path": ["result"],
            "sequence_binding_name": None,
            "sequence_ordinal": None,
        }
        constraint_scope = "INTRINSIC_TYPE"
        scope_source_inventory = None
    elif case["case_position"] == CASE69_POSITION:
        _require(
            binding["row_kind"] == "OUTER_RESULT_BOUNDARY_FIXTURE"
            and binding["type_name"] == CASE69_TYPE
            and binding["alternative_name"] is None
            and binding["constraint_scope_profile_id"] == CASE69_PROFILE_ID,
            "AUTHORITY_INVALID",
            "case 69 maximum-row binding differs",
        )
        measurement_binding = {
            "binding_kind": "OUTER_RESULT_RECORD",
            "validation_root_type_name": CASE69_TYPE,
            "measured_value_typed_member_path": [],
            "sequence_binding_name": None,
            "sequence_ordinal": None,
        }
        constraint_scope = "FROZEN_FIXTURE"
        scope_source_inventory = source_inventory
    elif case["case_position"] == CASE435_POSITION:
        _require(
            binding["row_kind"] == "CHECKPOINT_ROOT_COORDINATE"
            and binding["type_name"] == CASE435_TYPE
            and binding["alternative_name"] is None
            and binding["constraint_scope_profile_id"] == CASE435_PROFILE_ID
            and context["scope"]["context_kind"] == "ROOT_APPLICATION"
            and context["scope"]["measured_sequence_ordinal"]
            == CASE435_MEASURED_SEQUENCE_ORDINAL,
            "AUTHORITY_INVALID",
            "case435 maximum-row measurement binding differs",
        )
        measurement_binding = {
            "binding_kind": "ROOT_EXACT_CHECKPOINT_OBSERVATION",
            "validation_root_type_name": CASE435_ROOT_TYPE,
            "measured_value_typed_member_path": [],
            "sequence_binding_name": "observations",
            "sequence_ordinal": CASE435_MEASURED_SEQUENCE_ORDINAL,
        }
        constraint_scope = "FROZEN_ROOT_APPLICATION"
        scope_source_inventory = source_inventory
    else:
        _require(
            binding["row_kind"] == "INTRINSIC_RECORD",
            "AUTHORITY_INVALID",
            "intrinsic-record row kind differs",
        )
        measurement_binding = {
            "binding_kind": "SELF_RECORD",
            "validation_root_type_name": binding["type_name"],
            "measured_value_typed_member_path": [],
            "sequence_binding_name": None,
            "sequence_ordinal": None,
        }
        constraint_scope = "INTRINSIC_TYPE"
        scope_source_inventory = None
    payload = {
        "constraint_scope": constraint_scope,
        "measured_type_name": binding["type_name"],
        "alternative_name": binding["alternative_name"],
        "measurement_binding": measurement_binding,
        "constraint_scope_profile_id": binding["constraint_scope_profile_id"],
        "external_schema_registry_id": registry_id,
        "rule_literal_authority_sha256": literal_sha,
        "maximum_protocol_sha256": authorities["effective_protocol_sha256"],
        "source_inventory_sha256": scope_source_inventory,
        "evaluation_semantics": EVALUATION_SEMANTICS,
    }
    scope_id = _semantic_id(CONSTRAINT_SCOPE_DOMAIN, payload)
    row_context_payload = {
        "maximum_protocol_sha256": authorities["effective_protocol_sha256"],
        "source_inventory_sha256": source_inventory,
        "constraint_scope_id": scope_id,
        "required_context_object_count": len(context["ids"]),
        "ordered_required_context_object_ids": context["ids"],
    }
    return (
        payload["constraint_scope"],
        scope_id,
        _semantic_id(ROW_CONTEXT_DOMAIN, row_context_payload),
    )


def _f2_resource_catalog_id(authorities):
    if authorities["effective_f2_id"] is not None:
        return authorities["effective_f2_id"]
    boundary = authorities["boundary"]
    seed = authorities["seed"]
    manifest = authorities["manifest"]
    catalog = boundary["authority_contract"]["f2_resource_limit_catalog"]
    payload = {
        "catalog_version": catalog["catalog_version"],
        "protocol_version": boundary["protocol_version"],
        "seed_catalog_id": seed["seed_catalog_id"],
        "finalization_manifest_id": manifest["finalization_manifest_id"],
        "ordered_f2_limit_records": manifest["ordered_f2_limit_records"],
    }
    catalog_id = _semantic_id(catalog["identity_domain"], payload)
    _require(
        catalog_id == catalog["f2_resource_limit_catalog_id"],
        "AUTHORITY_INVALID",
        "F2 resource-limit catalog identity differs",
    )
    return catalog_id


def _build_result(
    authorities,
    case,
    plan,
    witness,
    witness_raw,
    context,
    descriptor,
    measurements,
    stream_sha,
):
    boundary = authorities["boundary"]
    output = boundary["verifier_output_contract"]
    source_inventory, registry_id, literal_sha = _authority_provenance(authorities)
    constraint_scope, scope_id, row_context_id = _constraint_scope(
        authorities, case, context, source_inventory, registry_id, literal_sha
    )
    maximum = len(witness_raw)
    relation = descriptor["codec_byte_bound_relation"]
    codec_limit = descriptor["codec_octet_limit"]
    codec_slack = _checked_sub(codec_limit, maximum + int(relation == "LT"))

    certificate_schema = output["upper_bound_certificate_schema"]
    certificate = {
        "certificate_version": certificate_schema["version_literal"],
        "maximum_protocol_sha256": authorities["effective_protocol_sha256"],
        "derivation_scope_id": scope_id,
        "upper_bound_mode": plan["upper_bound_mode"],
        "derivation_catalog_id": plan["recurrence_catalog_id"],
        "derivation_plan_id": plan["logical_count_plan_id"],
        "ordered_safe_relaxation_rule_ids": plan["ordered_safe_relaxation_rule_ids"],
        "certified_upper_bound_octets": maximum,
        "streamed_derivation_result_sha256": stream_sha,
    }
    certificate["upper_bound_certificate_id"] = _semantic_id(
        certificate_schema["identity_domain"], certificate
    )

    report_schema = output["proof_resource_report_schema"]
    report = {
        "resource_report_version": report_schema["version_literal"],
        "maximum_protocol_sha256": authorities["effective_protocol_sha256"],
        "derivation_scope_id": scope_id,
        "derivation_plan_id": plan["logical_count_plan_id"],
        "derivation_certificate_id": certificate["upper_bound_certificate_id"],
        "resource_limit_catalog_id": _f2_resource_catalog_id(authorities),
        "ordered_resource_measurements": measurements,
    }
    report["proof_resource_report_id"] = _semantic_id(
        report_schema["identity_domain"], report
    )

    schema = output["maximum_attainer_schema"]
    result = {
        "artifact_version": schema["version_literal"],
        "canonicalization_version": boundary["canonicalization_version"],
        "measurement_schema_version": boundary["measurement_schema_version"],
        "maximum_protocol_sha256": authorities["effective_protocol_sha256"],
        "source_inventory_sha256": source_inventory,
        "external_schema_registry_id": registry_id,
        "rule_literal_authority_sha256": literal_sha,
        "type_name": case["case_binding"]["type_name"],
        "alternative_name": case["case_binding"]["alternative_name"],
        "constraint_scope": constraint_scope,
        "constraint_scope_id": scope_id,
        "constraint_scope_profile_id": case["case_binding"][
            "constraint_scope_profile_id"
        ],
        "witness_kind": schema["witness_kind"],
        "canonical_byte_length": maximum,
        "certified_analytic_maximum_octets": maximum,
        "codec_byte_bound_relation": relation,
        "codec_octet_limit": codec_limit,
        "codec_slack_octets": codec_slack,
        "canonical_sha256": _sha256(witness_raw),
        "witness_record": witness,
        "scope_witness_context": context["scope"],
        "required_context_object_count": len(context["ids"]),
        "ordered_required_context_object_ids": context["ids"],
        "row_context_closure_id": row_context_id,
        "upper_bound_certificate": certificate,
        "proof_resource_report": report,
    }
    _require(
        list(result) == schema["ordered_member_names"][:-1],
        "OUTPUT_SCHEMA_INVALID",
        "maximum result member order differs",
    )
    result["maximum_attainer_id"] = _semantic_id(schema["identity_domain"], result)
    return result


def _build_local_result(
    authorities,
    case,
    plan,
    execution,
    measurements,
    stream_sha,
):
    boundary = authorities["boundary"]
    output = boundary["verifier_output_contract"]
    source_inventory, registry_id, literal_sha = _authority_provenance(authorities)
    baseline_spec = execution["baseline_spec"]
    mutated_spec = execution["mutated_spec"]
    prospective_result = execution["prospective_result"]
    prospective_raw = execution["prospective_result_raw"]
    binding = case["case_binding"]

    baseline_raw = _canonical_bytes(baseline_spec)
    reference_payload = {
        "reference_kind": "V3_INVENTORY_POINTER",
        "source_inventory_sha256": source_inventory,
        "inventory_json_pointer": CASE69_SPEC_POINTER,
        "record_type_name": CASE475_SPEC_TYPE,
        "record_identity_field": "operation_spec_id",
        "record_identity": baseline_spec["operation_spec_id"],
        "record_canonical_byte_length": len(baseline_raw),
        "record_canonical_sha256": _sha256(baseline_raw),
    }
    baseline_reference = {
        **reference_payload,
        "maximum_record_reference_id": _seed_semantic_id(
            authorities["seed"], RECORD_REFERENCE_DOMAIN, reference_payload
        ),
    }

    scope_payload = {
        "maximum_protocol_sha256": authorities["effective_protocol_sha256"],
        "source_inventory_sha256": source_inventory,
        "constraint_scope_profile_id": binding["constraint_scope_profile_id"],
        "baseline_operation_spec_id": baseline_spec["operation_spec_id"],
        "mutated_operation_spec_id": mutated_spec["operation_spec_id"],
    }
    local_scope_id = _semantic_id(LOCAL_PROOF_SCOPE_DOMAIN, scope_payload)

    certificate_schema = output["upper_bound_certificate_schema"]
    bound_certificate = {
        "certificate_version": certificate_schema["version_literal"],
        "maximum_protocol_sha256": authorities["effective_protocol_sha256"],
        "derivation_scope_id": local_scope_id,
        "upper_bound_mode": plan["upper_bound_mode"],
        "derivation_catalog_id": plan["recurrence_catalog_id"],
        "derivation_plan_id": plan["logical_count_plan_id"],
        "ordered_safe_relaxation_rule_ids": plan[
            "ordered_safe_relaxation_rule_ids"
        ],
        "certified_upper_bound_octets": CASE475_EXACT_MAXIMUM,
        "streamed_derivation_result_sha256": stream_sha,
    }
    bound_certificate["upper_bound_certificate_id"] = _semantic_id(
        certificate_schema["identity_domain"], bound_certificate
    )

    minimality_certificate = {
        "certificate_version": LOCAL_MINIMALITY_CERTIFICATE_VERSION,
        "maximum_protocol_sha256": authorities["effective_protocol_sha256"],
        "source_inventory_sha256": source_inventory,
        "constraint_scope_profile_id": binding["constraint_scope_profile_id"],
        "baseline_operation_spec_id": baseline_spec["operation_spec_id"],
        "mutated_operation_spec_id": mutated_spec["operation_spec_id"],
        "local_shutdown_proof_scope_id": local_scope_id,
        "winning_objective": execution["winning_objective"],
        "minimality_derivation_catalog_id": execution["local"][
            "local_shutdown_analytic_catalog_id"
        ],
        "minimality_derivation_plan_id": plan["logical_count_plan_id"],
        "ordered_safe_relaxation_rule_ids": plan[
            "ordered_safe_relaxation_rule_ids"
        ],
        "winning_prospective_bound_certificate": bound_certificate,
        "better_objective_exclusion_result_sha256": execution[
            "better_objective_exclusion_result_sha256"
        ],
    }
    minimality_certificate["local_shutdown_minimality_certificate_id"] = (
        _semantic_id(
            LOCAL_MINIMALITY_CERTIFICATE_DOMAIN, minimality_certificate
        )
    )

    report_schema = output["proof_resource_report_schema"]
    report = {
        "resource_report_version": report_schema["version_literal"],
        "maximum_protocol_sha256": authorities["effective_protocol_sha256"],
        "derivation_scope_id": local_scope_id,
        "derivation_plan_id": plan["logical_count_plan_id"],
        "derivation_certificate_id": minimality_certificate[
            "local_shutdown_minimality_certificate_id"
        ],
        "resource_limit_catalog_id": _f2_resource_catalog_id(authorities),
        "ordered_resource_measurements": measurements,
    }
    report["proof_resource_report_id"] = _semantic_id(
        report_schema["identity_domain"], report
    )

    schema = output["local_shutdown_result_schema"]
    result = {
        "artifact_version": schema["version_literal"],
        "canonicalization_version": boundary["canonicalization_version"],
        "measurement_schema_version": boundary["measurement_schema_version"],
        "maximum_protocol_sha256": authorities["effective_protocol_sha256"],
        "source_inventory_sha256": source_inventory,
        "external_schema_registry_id": registry_id,
        "rule_literal_authority_sha256": literal_sha,
        "constraint_scope_profile_id": binding["constraint_scope_profile_id"],
        "baseline_spec_record_reference": baseline_reference,
        "mutated_limit_members": [
            {
                "domain_position": 1,
                "member_name": CASE475_WINNING_MEMBER,
                "baseline_value": 1,
                "mutated_value": CASE475_WINNING_VALUE,
                "absolute_delta": CASE475_WINNING_DELTA,
            }
        ],
        "mutated_spec": mutated_spec,
        "changed_limit_field_count": 1,
        "sum_absolute_integer_deltas": CASE475_WINNING_DELTA,
        "prospective_result": prospective_result,
        "prospective_result_canonical_byte_length": len(prospective_raw),
        "outer_codec_byte_bound_relation": "LT",
        "outer_codec_octet_limit": 524_288,
        "expected_rejection_coordinate": {
            "record_type_name": CASE475_TYPE,
            "typed_member_path": [],
            "validation_layer": "CODEC_BOUND",
            "codec_byte_bound_relation": "LT",
            "codec_octet_limit": 524_288,
            "observed_canonical_byte_length": len(prospective_raw),
            "failure_class": "CODEC_OCTET_LIMIT_VIOLATION",
        },
        "minimality_certificate": minimality_certificate,
        "proof_resource_report": report,
    }
    _require(
        list(result) == schema["ordered_member_names"][:-1],
        "OUTPUT_SCHEMA_INVALID",
        "local result member order differs",
    )
    result["local_shutdown_unrepresentable_id"] = _semantic_id(
        schema["identity_domain"], result
    )
    return result


def _build_receipt(
    authorities, candidate, candidate_raw, context, result, result_raw
):
    boundary = authorities["boundary"]
    output = boundary["verifier_output_contract"]
    schema = output["verification_receipt_schema"]
    local_result = candidate["case_position"] == CASE475_POSITION
    result_id = (
        result["local_shutdown_unrepresentable_id"]
        if local_result
        else result["maximum_attainer_id"]
    )
    result_path = output["verified_bundle_paths"][
        "local_result" if local_result else "maximum_result"
    ]
    receipt = {
        "receipt_version": schema["version_literal"],
        "canonicalization_version": boundary["canonicalization_version"],
        "protocol_version": boundary["protocol_version"],
        "seed_catalog_id": authorities["effective_seed_id"],
        "finalization_manifest_id": authorities["effective_manifest_id"],
        "case_position": candidate["case_position"],
        "case_kind": candidate["case_kind"],
        "case_binding": candidate["case_binding"],
        "logical_count_plan_id": candidate["logical_count_plan_id"],
        "constructive_candidate_id": candidate["constructive_candidate_id"],
        "candidate_raw_octets": len(candidate_raw),
        "candidate_raw_sha256": _sha256(candidate_raw),
        "verification_status": (
            schema["local_status"] if local_result else schema["maximum_status"]
        ),
        "result_artifact_kind": (
            "LOCAL_SHUTDOWN_RESULT" if local_result else "MAXIMUM_ATTAINER"
        ),
        "result_artifact_id": result_id,
        "result_repository_relative_path": result_path,
        "result_raw_octets": len(result_raw),
        "result_raw_sha256": _sha256(result_raw),
        "ordered_verified_context_object_entries": context["entries"],
    }
    _require(
        list(receipt) == schema["ordered_member_names"][:-1],
        "OUTPUT_SCHEMA_INVALID",
        "receipt member order differs",
    )
    receipt["verification_receipt_id"] = _semantic_id(
        schema["identity_domain"], receipt
    )
    return receipt


def _write_all(descriptor, raw):
    offset = 0
    while offset < len(raw):
        written = os.write(descriptor, raw[offset:])
        _require(
            written > 0, "OUTPUT_ATOMICITY_INVALID", "output write made no progress"
        )
        offset += written


def _write_exclusive(path, raw):
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o600)
    try:
        _write_all(descriptor, raw)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _fsync_directory(path):
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _remove_private_tree(path):
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        return
    if stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode):
        for entry in os.scandir(path):
            _remove_private_tree(path / entry.name)
        os.rmdir(path)
    else:
        os.unlink(path)


def _publish_output(output_root, result, receipt, context_files, file_limit):
    _require(
        not output_root.exists(),
        "OUTPUT_ATOMICITY_INVALID",
        "output root already exists",
    )
    parent = output_root.parent
    _directory_signature(parent, "output parent")
    temporary = pathlib.Path(
        tempfile.mkdtemp(prefix=f".{output_root.name}.private.", dir=parent)
    )
    try:
        os.chmod(temporary, 0o700)
        context = temporary / "context_objects"
        os.mkdir(context, 0o700)
        context_directories = set()
        for record in context_files:
            parts = pathlib.PurePosixPath(record["relative_path"]).parts
            _require(
                len(parts) == 3
                and parts[0] == "context_objects"
                and len(parts[1]) == 2,
                "OUTPUT_SCHEMA_INVALID",
                "verified context-object path differs",
            )
            directory = context / parts[1]
            if parts[1] not in context_directories:
                os.mkdir(directory, 0o700)
                context_directories.add(parts[1])
            _write_exclusive(directory / parts[2], record["raw"])
        for name in sorted(context_directories):
            _fsync_directory(context / name)
        result_raw = _pretty_bytes(result)
        receipt_raw = _pretty_bytes(receipt)
        _require(
            len(result_raw) < file_limit and len(receipt_raw) < file_limit,
            "OUTPUT_LIMIT_EXCEEDED",
            "verified output file exceeds the frozen individual-file limit",
        )
        result_name = (
            "local_shutdown_unrepresentable.json"
            if "local_shutdown_unrepresentable_id" in result
            else "maximum_attainer.json"
        )
        _write_exclusive(temporary / result_name, result_raw)
        _write_exclusive(temporary / "verification_receipt.json", receipt_raw)
        _fsync_directory(context)
        _fsync_directory(temporary)
        _require(
            not output_root.exists(),
            "OUTPUT_ATOMICITY_INVALID",
            "output root appeared during publication",
        )
        os.rename(temporary, output_root)
        _fsync_directory(parent)
        temporary = None
    finally:
        if temporary is not None:
            _remove_private_tree(temporary)


def _lexical_cli_path(value, label):
    path = pathlib.Path(value)
    _require(path.is_absolute(), "INVOCATION_INVALID", f"{label} must be absolute")
    _require(
        path == pathlib.Path(os.path.abspath(os.fspath(path))),
        "INVOCATION_INVALID",
        f"{label} must be lexically canonical",
    )
    _require(
        all(part not in {"", ".", ".."} for part in path.parts[1:]),
        "INVOCATION_INVALID",
        f"{label} has a forbidden component",
    )
    return path


def _arguments(argv):
    expected_flags = [
        "--repository-root",
        "--boundary",
        "--candidate-root",
        "--output-root",
    ]
    _require(len(argv) == 8, "INVOCATION_INVALID", "expected four option/value pairs")
    _require(
        argv[::2] == expected_flags, "INVOCATION_INVALID", "argument order differs"
    )
    return tuple(
        _lexical_cli_path(value, flag[2:])
        for flag, value in zip(expected_flags, argv[1::2], strict=True)
    )


def _verify(repository_root, boundary_path, candidate_root, output_root):
    _absolute_lexical_path(repository_root, "repository root", True)
    _directory_signature(repository_root, "repository root")
    _absolute_lexical_path(boundary_path, "boundary", True)
    authorities = _load_authorities(repository_root, boundary_path)

    _absolute_lexical_path(candidate_root, "candidate root", True)
    _absolute_lexical_path(output_root, "output root", False)
    _require(
        not output_root.exists(),
        "OUTPUT_ATOMICITY_INVALID",
        "output root already exists",
    )
    candidate_text = os.fspath(candidate_root)
    output_text = os.fspath(output_root)
    _require(
        os.path.commonpath([candidate_text, output_text])
        not in {candidate_text, output_text},
        "OUTPUT_ATOMICITY_INVALID",
        "candidate and output roots overlap",
    )

    snapshot = _candidate_snapshot(candidate_root, authorities)
    candidate = _strict_loads(snapshot["raw"], authorities["limits"])
    _require(
        isinstance(candidate, dict), "SCHEMA_INVALID", "candidate root is not an object"
    )
    case, plan, candidate_value, context = _validate_candidate(
        candidate, snapshot["raw"], snapshot, authorities
    )
    if case["case_position"] == CASE475_POSITION:
        execution = _execute_local_minimality(
            authorities, case, plan, candidate_value
        )
        measurements, stream_sha = _derive_local_case_resources(
            authorities["seed"], authorities["manifest"], plan
        )
        result = _build_local_result(
            authorities,
            case,
            plan,
            execution,
            measurements,
            stream_sha,
        )
    else:
        witness = candidate_value
        template, cells, descriptor, witness_raw, owner_profile_position = (
            _execute_bound(authorities, case, plan, witness, context)
        )
        measurements, stream_sha = _derive_case_resources(
            authorities["seed"],
            authorities["manifest"],
            plan,
            template,
            cells,
            owner_profile_position,
        )
        result = _build_result(
            authorities,
            case,
            plan,
            witness,
            witness_raw,
            context,
            descriptor,
            measurements,
            stream_sha,
        )
    result_raw = _pretty_bytes(result)
    receipt = _build_receipt(
        authorities, candidate, snapshot["raw"], context, result, result_raw
    )

    _candidate_recheck(candidate_root, snapshot, authorities)
    total = _authority_recheck(authorities["authority_records"])
    _require(
        total
        + len(snapshot["raw"])
        + sum(len(record["raw"]) for record in snapshot["context_files"])
        <= authorities["limits"]["TOTAL_PINNED_INPUT_OCTETS"],
        "INPUT_LIMIT_EXCEEDED",
        "rechecked authority bytes exceed F0",
    )
    _require(
        len(authorities["authority_records"])
        + 1
        + len(snapshot["context_files"])
        <= authorities["limits"]["INPUT_FILE_COUNT"],
        "INPUT_LIMIT_EXCEEDED",
        "rechecked input file count exceeds F0",
    )
    _publish_output(
        output_root,
        result,
        receipt,
        context["files"],
        authorities["limits"]["INDIVIDUAL_FILE_STRICT_UPPER_OCTETS"],
    )


def _entrypoint(argv):
    try:
        arguments = _arguments(argv)
        _verify(*arguments)
        return 0
    except VerifierReject as error:
        line = f"{ERROR_PREFIX}{error.code}: {error.message}\n"
        sys.stderr.write(line)
        return 2 if error.code == "INVOCATION_INVALID" else 1
    except Exception as error:
        message = f"{type(error).__name__}: {error}".replace("\n", " ").replace(
            "\r", " "
        )[:768]
        sys.stderr.write(f"{ERROR_PREFIX}INTERNAL_FAIL_CLOSED: {message}\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(_entrypoint(sys.argv[1:]))
