"""Fail-closed contract for the Raw-V8 Step-2 V2 case event grammar.

This test intentionally fails against the current label-only seed catalog.
It does not import the seed generator and does not trust provisional count
vectors. Once the catalog implements the grammar, the same validator also
performs adversarial mutations for omission, duplication, reordering, byte
ownership, live-set, and stream-finalization errors.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = (
    ROOT / "scripts/tests/raw_v8_step2_maximum_protocol_v2_seed_catalog_v49f.json"
)

EVENT_KINDS = (
    "CASE_OPEN",
    "LOGICAL_DESCRIPTOR_VISIT",
    "CACHE_INSERT",
    "TRANSITION_ATTEMPT",
    "BATCH_APPLICATION",
    "RESULT_CELL_EMIT",
    "STEP_COMMITMENT_EMIT",
    "FINAL_RESULT_EMIT",
    "INTRINSIC_RULE_EVALUATION",
    "CROSS_RULE_EVALUATION",
    "APPLICATION_EVALUATION",
    "HASH_PREIMAGE",
    "RETENTION_OBSERVATION",
    "DERIVATION_DEPTH_OBSERVATION",
    "ITERATION_DEPTH_OBSERVATION",
    "EVENT_STREAM_CLOSE",
)

TOKEN_MEMBERS = (
    "event_position",
    "execution_phase",
    "logical_derivation_step_position",
    "event_kind",
    "event_ordinal",
    "subject_schema_version",
    "subject_kind",
    "subject_role",
    "subject_ordinal",
    "subject_canonical_octets",
    "subject_sha256",
    "aggregation_multiplicity",
    "logical_unbatched_equivalent_count",
    "observed_value",
)

PHASES = (
    "CASE_OPEN",
    "PLAN_IDENTITY_BINDING",
    "UPPER_BOUND_DERIVATION",
    "LEGAL_ATTAINMENT_VALIDATION",
    "SCOPE_APPLICATION_VALIDATION",
    "DEPTH_AND_RETENTION_FINALIZATION",
    "FINAL_RESULT_SERIALIZATION",
    "EVENT_STREAM_FINALIZATION",
)

SUBJECT_KINDS = {
    "CASE_OPEN": "CASE_OPEN_RECORD_V1",
    "LOGICAL_DESCRIPTOR_VISIT": "LOGICAL_DERIVATION_STEP_REFERENCE_V1",
    "CACHE_INSERT": "RECURRENCE_CACHE_KEY_V2",
    "TRANSITION_ATTEMPT": "RECURRENCE_TRANSITION_TOKEN_V2",
    "BATCH_APPLICATION": "BATCH_APPLICATION_RECORD_V1",
    "RESULT_CELL_EMIT": "RECURRENCE_RESULT_CELL_V2",
    "STEP_COMMITMENT_EMIT": "RECURRENCE_STEP_COMMITMENT_V2",
    "FINAL_RESULT_EMIT": "LOGICAL_CASE_DERIVATION_RESULT_V1",
    "INTRINSIC_RULE_EVALUATION": "INTRINSIC_RULE_EVALUATION_RECORD_V1",
    "CROSS_RULE_EVALUATION": "CROSS_RULE_EVALUATION_RECORD_V1",
    "APPLICATION_EVALUATION": "APPLICATION_EVALUATION_RECORD_V1",
    "HASH_PREIMAGE": "HASH_PREIMAGE_BYTES_V1",
    "RETENTION_OBSERVATION": "LIVE_SET_SNAPSHOT_V1",
    "DERIVATION_DEPTH_OBSERVATION": "DERIVATION_DEPTH_RECORD_V1",
    "ITERATION_DEPTH_OBSERVATION": "ITERATION_DEPTH_RECORD_V1",
    "EVENT_STREAM_CLOSE": "EVENT_STREAM_PREIMAGE_DESCRIPTOR_V1",
}

AGGREGATABLE_EVENT_KINDS = frozenset(
    {
        "LOGICAL_DESCRIPTOR_VISIT",
        "INTRINSIC_RULE_EVALUATION",
        "CROSS_RULE_EVALUATION",
        "APPLICATION_EVALUATION",
    }
)

ONE_EXPRESSION = {"opcode": "CONST_U128", "value": 1}
ZERO_EXPRESSION = {"opcode": "CONST_U128", "value": 0}

PROGRAMS = (
    (
        "CASE_OPEN",
        "EMIT_CASE_OPEN_ONCE_V1",
        "ALL_CASES",
        ("CASE_OPEN",),
    ),
    (
        "BOUND_PLAN_HASH_PREIMAGE",
        "EMIT_BOUND_PLAN_IDENTITY_HASH_V1",
        "ALL_CASES",
        ("HASH_PREIMAGE",),
    ),
    (
        "ORDINARY_POSTORDER_STEPS",
        "EXECUTE_ORDINARY_STEPS_POSTORDER_V1",
        "LOGICAL_PLAN_TEMPLATE_PRESENT",
        (
            "LOGICAL_DESCRIPTOR_VISIT",
            "TRANSITION_ATTEMPT",
            "BATCH_APPLICATION",
            "RESULT_CELL_EMIT",
            "CACHE_INSERT",
            "RETENTION_OBSERVATION",
            "HASH_PREIMAGE",
            "STEP_COMMITMENT_EMIT",
            "HASH_PREIMAGE",
            "RETENTION_OBSERVATION",
        ),
    ),
    (
        "LOCAL_CONTROLLER",
        "EXECUTE_LOCAL_CONTROLLER_ORDER_V1",
        "LOCAL_ANALYTIC_CATALOG_PRESENT",
        (
            "LOGICAL_DESCRIPTOR_VISIT",
            "TRANSITION_ATTEMPT",
            "INTRINSIC_RULE_EVALUATION",
            "RESULT_CELL_EMIT",
            "CACHE_INSERT",
            "RETENTION_OBSERVATION",
            "HASH_PREIMAGE",
            "STEP_COMMITMENT_EMIT",
            "HASH_PREIMAGE",
            "RETENTION_OBSERVATION",
        ),
    ),
    (
        "EXACT_ATTAINER_VALIDATION",
        "EXECUTE_EXACT_ATTAINER_VALIDATION_V1",
        "ALL_CASES",
        ("INTRINSIC_RULE_EVALUATION",),
    ),
    (
        "SCOPE_APPLICATIONS",
        "EXECUTE_SCOPE_SCHEDULE_LEXICAL_V1",
        "SCOPE_SCHEDULE_NONEMPTY",
        ("APPLICATION_EVALUATION", "CROSS_RULE_EVALUATION"),
    ),
    (
        "DEPTH_AND_RETENTION",
        "EMIT_DEPTH_AND_LIVE_SET_MAXIMA_V1",
        "ALL_CASES",
        (
            "DERIVATION_DEPTH_OBSERVATION",
            "ITERATION_DEPTH_OBSERVATION",
            "RETENTION_OBSERVATION",
        ),
    ),
    (
        "FINAL_RESULT",
        "EMIT_FINAL_RESULT_ONCE_V1",
        "ALL_CASES",
        ("FINAL_RESULT_EMIT", "HASH_PREIMAGE"),
    ),
    (
        "STREAM_FINALIZATION",
        "CLOSE_THEN_HASH_EXCLUDED_CONTROL_EVENTS_V1",
        "ALL_CASES",
        ("EVENT_STREAM_CLOSE", "HASH_PREIMAGE"),
    ),
)

HASH_PROGRAMS = (
    (
        "BOUND_PLAN_IDENTITY_HASH",
        "HASH_BOUND_PLAN_IDENTITY_ENVELOPE_ONCE_V1",
        ("BOUND_PLAN_IDENTITY_ENVELOPE",),
    ),
    (
        "DERIVATION_UNITS_POSTORDER",
        "HASH_CELLS_THEN_COMMITMENT_PER_DERIVATION_UNIT_V1",
        ("RETAINED_RESULT_CELL_PREIMAGE", "STEP_COMMITMENT_PREIMAGE"),
    ),
    (
        "FINAL_RESULT_IDENTITY_HASH",
        "HASH_FINAL_RESULT_IDENTITY_ONCE_V1",
        ("FINAL_RESULT_IDENTITY_PREIMAGE",),
    ),
    (
        "EVENT_STREAM_HASH",
        "HASH_EVENT_STREAM_PREIMAGE_ONCE_LAST_V1",
        ("EVENT_STREAM_PREIMAGE",),
    ),
)

# Metric programs are exact. Tuple order is metric position, update kind,
# value source. Rule/application counts use multiplicity so the stream can
# remain bounded while the subject binds the exact covered occurrence range.
METRIC_PROGRAMS = {
    "CASE_OPEN": ((1, "ADD", "ONE"),),
    "LOGICAL_DESCRIPTOR_VISIT": ((2, "ADD", "AGGREGATION_MULTIPLICITY"),),
    "CACHE_INSERT": (
        (7, "ADD", "ONE"),
        (8, "ADD", "SUBJECT_CANONICAL_OCTETS"),
        (9, "ADD", "SUBJECT_CANONICAL_OCTETS"),
        (10, "ADD", "SUBJECT_CANONICAL_OCTETS"),
    ),
    "TRANSITION_ATTEMPT": (
        (4, "ADD", "ONE"),
        (5, "ADD", "LOGICAL_UNBATCHED_EQUIVALENT_COUNT"),
        (9, "ADD", "SUBJECT_CANONICAL_OCTETS"),
        (10, "ADD", "SUBJECT_CANONICAL_OCTETS"),
    ),
    "BATCH_APPLICATION": ((6, "ADD", "ONE"),),
    "RESULT_CELL_EMIT": (
        (3, "ADD", "ONE"),
        (10, "ADD", "SUBJECT_CANONICAL_OCTETS"),
    ),
    "STEP_COMMITMENT_EMIT": (),
    "FINAL_RESULT_EMIT": ((18, "ADD", "SUBJECT_CANONICAL_OCTETS"),),
    "INTRINSIC_RULE_EVALUATION": ((12, "ADD", "AGGREGATION_MULTIPLICITY"),),
    "CROSS_RULE_EVALUATION": ((13, "ADD", "AGGREGATION_MULTIPLICITY"),),
    "APPLICATION_EVALUATION": ((14, "ADD", "AGGREGATION_MULTIPLICITY"),),
    "HASH_PREIMAGE": ((11, "ADD", "SUBJECT_CANONICAL_OCTETS"),),
    "RETENTION_OBSERVATION": ((17, "MAX", "OBSERVED_VALUE"),),
    "DERIVATION_DEPTH_OBSERVATION": ((15, "MAX", "OBSERVED_VALUE"),),
    "ITERATION_DEPTH_OBSERVATION": ((16, "MAX", "OBSERVED_VALUE"),),
    "EVENT_STREAM_CLOSE": (),
}

BYTE_EQUATIONS = {
    8: (("CACHE_INSERT", "RECURRENCE_CACHE_KEY_V2"),),
    9: (
        ("CACHE_INSERT", "RECURRENCE_CACHE_KEY_V2"),
        ("TRANSITION_ATTEMPT", "RECURRENCE_TRANSITION_TOKEN_V2"),
    ),
    10: (
        ("CACHE_INSERT", "RECURRENCE_CACHE_KEY_V2"),
        ("TRANSITION_ATTEMPT", "RECURRENCE_TRANSITION_TOKEN_V2"),
        ("RESULT_CELL_EMIT", "RECURRENCE_RESULT_CELL_V2"),
    ),
    11: (("HASH_PREIMAGE", "HASH_PREIMAGE_BYTES_V1"),),
    18: (("FINAL_RESULT_EMIT", "LOGICAL_CASE_DERIVATION_RESULT_V1"),),
}

MUTATION_CLASSES = (
    "OMIT_EVENT",
    "DUPLICATE_EVENT",
    "REORDER_EVENT",
    "RESIZE_SUBJECT",
    "CHANGE_SUBJECT_SHA256",
    "CHANGE_EVENT_ORDINAL",
    "CHANGE_AGGREGATION_MULTIPLICITY",
    "CHANGE_LOGICAL_UNBATCHED_EQUIVALENT_COUNT",
    "EARLY_OR_LATE_RELEASE",
    "MOVE_BYTE_ACCOUNTING_TERM",
    "COUNT_M18_FRAGMENT",
    "DUPLICATE_FINAL_RESULT",
    "INCLUDE_EXCLUDED_CONTROL_EVENT_IN_PREIMAGE",
    "EVENT_AFTER_FINAL_HASH",
)

ORACLE_MEMBERS = (
    "oracle_position",
    "oracle_id",
    "ordered_coverage_tags",
    "complete_logical_count_plan",
    "exact_source_objects_or_fixture_locators",
    "ordered_logical_event_tokens",
    "event_stream_preimage_canonical_octets_hex",
    "event_stream_preimage_sha256",
    "ordered_expected_resource_measurements",
    "final_result_canonical_octets_hex",
    "final_result_sha256",
    "ordered_live_set_snapshots",
    "expected_status",
)

REQUIRED_COVERAGE_TAGS = (
    "UNRESTRICTED_BOOLEAN",
    "NULLABLE",
    "FINITE_TEXT",
    "RELAXED_TEXT",
    "SAFE_INTEGER",
    "BATCHED_ARRAY",
    "STREAM_FALLBACK_ARRAY",
    "RECORD",
    "SELF_VALUE_UNION",
    "OWNER_PAYLOAD_UNION",
    "CODEC_INTERSECTION",
    "CONTEXT_APPLICATION_SCHEDULE",
    "LOCAL_SHUTDOWN_CASE_475",
)


def _compact_canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _expected_hand_oracle_records(catalog: dict[str, Any]) -> list[dict[str, Any]]:
    event_catalog = catalog["logical_event_catalog"]
    recurrence = catalog["recurrence_catalog"]
    plans = catalog["logical_plan_recipe_catalog"]["ordered_logical_count_plan_records"]
    subject_by_kind = {
        row["event_kind"]: row
        for row in event_catalog["case_level_event_grammar"][
            "ordered_subject_schema_records"
        ]
    }
    metric_program_by_kind = {
        row["event_kind"]: row["ordered_metric_update_program"]
        for row in event_catalog["ordered_event_kind_records"]
    }
    metric_names = {
        row["metric_position"]: row["metric_name"]
        for row in catalog["resource_metric_catalog"]["ordered_metric_records"]
    }
    plan_identity = next(
        row
        for row in catalog["ordered_identity_domain_records"]
        if row["identity_name"] == "LOGICAL_COUNT_PLAN"
    )
    state_signature_id = recurrence["ordered_state_signature_records"][0][
        "state_signature_id"
    ]

    def tagged_subject(schema_name: str, values: dict[str, Any]) -> dict[str, Any]:
        schema = recurrence[schema_name]
        version_member = schema["ordered_member_names"][0]
        complete = {version_member: schema[version_member], **values}
        assert set(complete) <= set(schema["ordered_member_names"])
        return {name: complete.get(name) for name in schema["ordered_member_names"]}

    def build(
        *,
        oracle_position: int,
        oracle_name: str,
        plan_position: int,
        coverage_tags: list[str],
        local: bool,
        context: bool,
        batched: bool,
    ) -> dict[str, Any]:
        plan = plans[plan_position - 1]
        plan_id = plan["logical_count_plan_id"]
        tokens: list[dict[str, Any]] = []
        sources: list[dict[str, Any]] = []
        snapshots: list[dict[str, Any]] = []
        ordinals: dict[str, int] = {}

        def add(
            event_kind: str,
            execution_phase: str,
            subject_role: str,
            subject: Any,
            *,
            step: int | None = None,
            subject_ordinal: int | None = None,
            aggregation: int = 1,
            logical_unbatched: int = 0,
            observed: int | None = None,
        ) -> bytes:
            raw = (
                subject
                if isinstance(subject, bytes)
                else _compact_canonical_bytes(subject)
            )
            event_position = len(tokens) + 1
            ordinals[event_kind] = ordinals.get(event_kind, 0) + 1
            token = {
                "event_position": event_position,
                "execution_phase": execution_phase,
                "logical_derivation_step_position": step,
                "event_kind": event_kind,
                "event_ordinal": ordinals[event_kind],
                "subject_schema_version": subject_by_kind[event_kind][
                    "subject_schema_version"
                ],
                "subject_kind": SUBJECT_KINDS[event_kind],
                "subject_role": subject_role,
                "subject_ordinal": subject_ordinal,
                "subject_canonical_octets": len(raw),
                "subject_sha256": _sha256(raw),
                "aggregation_multiplicity": aggregation,
                "logical_unbatched_equivalent_count": logical_unbatched,
                "observed_value": observed,
            }
            tokens.append(token)
            sources.append(
                {
                    "event_position": event_position,
                    "subject_canonical_octets_hex": raw.hex(),
                }
            )
            return raw

        def retention_snapshot(
            label: str, entries: list[dict[str, Any]], *, step: int | None
        ) -> None:
            observed = sum(row["canonical_octets"] for row in entries)
            snapshot = {
                "snapshot_position": len(snapshots) + 1,
                "observation_label": label,
                "ordered_live_entry_records": entries,
                "observed_value": observed,
            }
            raw = add(
                "RETENTION_OBSERVATION",
                "UPPER_BOUND_DERIVATION",
                label,
                snapshot,
                step=step,
                subject_ordinal=len(snapshots) + 1,
                observed=observed,
            )
            snapshots.append(
                {
                    **snapshot,
                    "event_position": tokens[-1]["event_position"],
                    "snapshot_canonical_octets": len(raw),
                    "snapshot_sha256": _sha256(raw),
                }
            )

        add(
            "CASE_OPEN",
            "CASE_OPEN",
            "CASE_OPEN_RECORD",
            {
                "fixture_version": "riskyieldmm.hand_event_oracle_fixture.v1",
                "oracle_name": oracle_name,
                "logical_count_plan_id": plan_id,
                "ordered_coverage_tags": coverage_tags,
            },
        )
        plan_payload = {
            name: plan[name] for name in plan_identity["ordered_payload_member_names"]
        }
        plan_preimage = _compact_canonical_bytes(
            {
                "canonicalization_version": catalog["canonicalization_version"],
                "domain": plan_identity["domain_literal"],
                "payload": plan_payload,
                "schema_version": catalog["measurement_schema_version"],
            }
        )
        assert _sha256(plan_preimage) == plan_id
        add(
            "HASH_PREIMAGE",
            "PLAN_IDENTITY_BINDING",
            "BOUND_PLAN_IDENTITY_ENVELOPE",
            plan_preimage,
            subject_ordinal=1,
        )

        subject_variant = "LOCAL_CONTROLLER" if local else "ORDINARY_STEP"
        step = None if local else 1
        add(
            "LOGICAL_DESCRIPTOR_VISIT",
            "UPPER_BOUND_DERIVATION",
            "LOCAL_CONTROLLER_REFERENCE" if local else "LOGICAL_STEP_REFERENCE",
            {
                "logical_count_plan_id": plan_id,
                "subject_variant": subject_variant,
                "logical_derivation_step_position": step,
            },
            step=step,
            aggregation=1 if local else 3,
        )

        transition_count = 11 if local else 1
        for transition_ordinal in range(1, transition_count + 1):
            transition = tagged_subject(
                "transition_token_schema",
                {
                    "subject_variant": subject_variant,
                    "logical_count_plan_id": plan_id,
                    "transition_ordinal": transition_ordinal,
                    "transition_kind": (
                        "LOCAL_CONTROLLER_TRANSITION"
                        if local
                        else "ORDINARY_KERNEL_TRANSITION"
                    ),
                    "source_state_components": [transition_ordinal - 1],
                    "input_symbol": f"INPUT_{transition_ordinal}",
                    "candidate_state_components": [transition_ordinal],
                    "candidate_certified_upper_bound_octets": 32 + transition_ordinal,
                    "logical_derivation_step_position": step,
                    "local_controller_transition_position": (
                        transition_ordinal if local else None
                    ),
                    "local_controller_transition_id": (
                        f"local-transition-{transition_ordinal:02d}" if local else None
                    ),
                    "source_controller_state_id": (
                        f"local-state-{transition_ordinal:02d}" if local else None
                    ),
                    "target_controller_state_id": (
                        f"local-state-{transition_ordinal + 1:02d}" if local else None
                    ),
                },
            )
            add(
                "TRANSITION_ATTEMPT",
                "UPPER_BOUND_DERIVATION",
                "LOCAL_CONTROLLER_TRANSITION" if local else "ORDINARY_TRANSITION",
                transition,
                step=step,
                subject_ordinal=transition_ordinal,
                logical_unbatched=1 if local else 4,
            )

        if batched:
            add(
                "BATCH_APPLICATION",
                "UPPER_BOUND_DERIVATION",
                "HOMOGENEOUS_RUN_BATCH",
                {
                    "logical_count_plan_id": plan_id,
                    "logical_derivation_step_position": step,
                    "physical_batch_ordinal": 1,
                    "logical_item_count": 4,
                },
                step=step,
                subject_ordinal=1,
            )
        if local:
            add(
                "INTRINSIC_RULE_EVALUATION",
                "UPPER_BOUND_DERIVATION",
                "LOCAL_CONTROLLER_INTRINSIC_RELATIONS",
                {"logical_count_plan_id": plan_id, "rule_count": 2},
                aggregation=2,
            )

        result_cell = tagged_subject(
            "result_cell_schema",
            {
                "subject_variant": subject_variant,
                "logical_count_plan_id": plan_id,
                "state_signature_id": state_signature_id,
                "ordered_state_components": [] if not local else [11],
                "cell_status": "MAY_BE_NONEMPTY",
                "certified_lower_bound_octets": 1,
                "certified_upper_bound_octets": 64,
                "logical_derivation_step_position": step,
                "result_cell_ordinal": None if local else 1,
                "local_controller_state_position": 12 if local else None,
                "local_controller_state_id": "local-state-12" if local else None,
            },
        )
        result_raw = add(
            "RESULT_CELL_EMIT",
            "UPPER_BOUND_DERIVATION",
            "LOCAL_TERMINAL_RESULT_CELL" if local else "ORDINARY_RESULT_CELL",
            result_cell,
            step=step,
            subject_ordinal=1,
        )
        cache_key = tagged_subject(
            "cache_key_schema",
            {
                "subject_variant": subject_variant,
                "logical_count_plan_id": plan_id,
                "effective_canonical_octet_ceiling": 128,
                "state_signature_id": state_signature_id,
                "ordered_state_components": [] if not local else [11],
                "logical_derivation_step_position": step,
                "derivation_kind": None if local else "HAND_ORACLE_STEP",
                "occurrence_ordinal": None if local else 1,
                "array_ordinal": None,
                "owner_profile_position": None,
                "application_invocation_ordinal": None,
                "observation_ordinal": None,
                "local_controller_state_position": 12 if local else None,
                "local_controller_state_id": "local-state-12" if local else None,
            },
        )
        cache_raw = add(
            "CACHE_INSERT",
            "UPPER_BOUND_DERIVATION",
            "LOCAL_TERMINAL_CACHE_KEY" if local else "ORDINARY_CACHE_KEY",
            cache_key,
            step=step,
            subject_ordinal=1,
        )
        retention_snapshot(
            "LIVE_CHILDREN_PLUS_PROSPECTIVE_PARENT",
            [
                {
                    "entry_kind": "RECURRENCE_CACHE_KEY_V2",
                    "entry_id": _sha256(cache_raw),
                    "canonical_octets": len(cache_raw),
                },
                {
                    "entry_kind": "RECURRENCE_RESULT_CELL_V2",
                    "entry_id": _sha256(result_raw),
                    "canonical_octets": len(result_raw),
                },
            ],
            step=step,
        )
        add(
            "HASH_PREIMAGE",
            "UPPER_BOUND_DERIVATION",
            "RETAINED_RESULT_CELL_PREIMAGE",
            result_raw,
            step=step,
            subject_ordinal=2,
        )
        commitment = tagged_subject(
            "step_commitment_schema",
            {
                "subject_variant": subject_variant,
                "logical_count_plan_id": plan_id,
                "state_count": 1,
                "certified_upper_bound_octets": 64,
                "ordered_result_cell_sha256": [_sha256(result_raw)],
                "logical_derivation_step_position": step,
                "local_shutdown_analytic_catalog_id": (
                    recurrence["local_shutdown_analytic_catalog"][
                        "local_shutdown_analytic_catalog_id"
                    ]
                    if local
                    else None
                ),
                "initial_controller_state_id": "local-state-01" if local else None,
                "terminal_controller_state_id": "local-state-12" if local else None,
            },
        )
        commitment_raw = add(
            "STEP_COMMITMENT_EMIT",
            "UPPER_BOUND_DERIVATION",
            "LOCAL_CONTROLLER_COMMITMENT" if local else "ORDINARY_STEP_COMMITMENT",
            commitment,
            step=step,
            subject_ordinal=1,
        )
        add(
            "HASH_PREIMAGE",
            "UPPER_BOUND_DERIVATION",
            "STEP_COMMITMENT_PREIMAGE",
            commitment_raw,
            step=step,
            subject_ordinal=3,
        )
        retention_snapshot(
            "AFTER_PARENT_COMMITMENT_HASH_AND_RELEASE",
            [
                {
                    "entry_kind": "STEP_COMMITMENT_DIGEST_V1",
                    "entry_id": _sha256(commitment_raw),
                    "canonical_octets": 32,
                }
            ],
            step=step,
        )

        add(
            "INTRINSIC_RULE_EVALUATION",
            "LEGAL_ATTAINMENT_VALIDATION",
            "EXACT_RETAINED_ATTAINER_INTRINSIC_RULES",
            {"logical_count_plan_id": plan_id, "covered_rule_count": 2},
            aggregation=2,
        )
        if context or local:
            add(
                "APPLICATION_EVALUATION",
                "SCOPE_APPLICATION_VALIDATION",
                "EXACT_SCOPE_APPLICATION_INVOCATIONS",
                {
                    "logical_count_plan_id": plan_id,
                    "application_count": 2 if context else 1,
                },
                subject_ordinal=1,
                aggregation=2 if context else 1,
            )
            add(
                "CROSS_RULE_EVALUATION",
                "SCOPE_APPLICATION_VALIDATION",
                "EXACT_SCOPE_CROSS_RULE_ROOTS",
                {
                    "logical_count_plan_id": plan_id,
                    "cross_rule_count": 7 if context else 1,
                },
                subject_ordinal=1,
                aggregation=7 if context else 1,
            )
        add(
            "DERIVATION_DEPTH_OBSERVATION",
            "DEPTH_AND_RETENTION_FINALIZATION",
            "DERIVATION_DAG_DEPTH",
            {"logical_count_plan_id": plan_id, "derived_depth": 4 if not local else 1},
            observed=4 if not local else 1,
        )
        add(
            "ITERATION_DEPTH_OBSERVATION",
            "DEPTH_AND_RETENTION_FINALIZATION",
            "ITERATION_DEPTH",
            {
                "logical_count_plan_id": plan_id,
                "iteration_depth": 3 if not local else 12,
            },
            observed=3 if not local else 12,
        )
        retention_snapshot(
            "ROOT_COMMITMENT_DIGEST_THROUGH_FINAL_RESULT_HASH",
            [
                {
                    "entry_kind": "STEP_COMMITMENT_DIGEST_V1",
                    "entry_id": _sha256(commitment_raw),
                    "canonical_octets": 32,
                }
            ],
            step=None,
        )

        final_result = {
            "logical_case_derivation_result_version": (
                "riskyieldmm.raw_v8_step2_external_schema_v2."
                "logical_case_derivation_result.v1"
            ),
            "logical_count_plan_id": plan_id,
            "result_status": "ACCEPT",
            "ordered_root_result_cell_digest_records": [
                {
                    "result_cell_ordinal": 1,
                    "result_cell_sha256": _sha256(result_raw),
                }
            ],
            "ordered_step_commitment_digest_records": [
                {
                    "derivation_unit_ordinal": 1,
                    "subject_variant": subject_variant,
                    "logical_derivation_step_position": step,
                    "local_controller_unit_ordinal": 1 if local else None,
                    "step_commitment_sha256": _sha256(commitment_raw),
                }
            ],
        }
        final_raw = add(
            "FINAL_RESULT_EMIT",
            "FINAL_RESULT_SERIALIZATION",
            "COMPLETE_LOGICAL_CASE_DERIVATION_RESULT",
            final_result,
        )
        add(
            "HASH_PREIMAGE",
            "FINAL_RESULT_SERIALIZATION",
            "FINAL_RESULT_IDENTITY_PREIMAGE",
            final_raw,
            subject_ordinal=4,
        )
        stream_preimage = _compact_canonical_bytes(
            {
                "logical_event_stream_version": (
                    "riskyieldmm.raw_v8_step2_external_schema_v2."
                    "logical_event_stream.v1"
                ),
                "logical_count_plan_id": plan_id,
                "ordered_pre_close_logical_event_tokens": tokens,
            }
        )
        stream_digest = _sha256(stream_preimage)
        add(
            "EVENT_STREAM_CLOSE",
            "EVENT_STREAM_FINALIZATION",
            "EVENT_STREAM_PREIMAGE_DESCRIPTOR",
            {
                "logical_count_plan_id": plan_id,
                "preimage_canonical_octets": len(stream_preimage),
                "preimage_sha256": stream_digest,
            },
        )
        add(
            "HASH_PREIMAGE",
            "EVENT_STREAM_FINALIZATION",
            "EVENT_STREAM_PREIMAGE",
            stream_preimage,
            subject_ordinal=5,
        )

        measurements = dict.fromkeys(range(1, 19), 0)
        for token in tokens:
            for update in metric_program_by_kind[token["event_kind"]]:
                source = update["value_source"]
                value = {
                    "ONE": 1,
                    "SUBJECT_CANONICAL_OCTETS": token["subject_canonical_octets"],
                    "AGGREGATION_MULTIPLICITY": token["aggregation_multiplicity"],
                    "LOGICAL_UNBATCHED_EQUIVALENT_COUNT": token[
                        "logical_unbatched_equivalent_count"
                    ],
                    "OBSERVED_VALUE": token["observed_value"],
                }[source]
                assert type(value) is int and value >= 0
                position = update["metric_position"]
                if update["update_kind"] == "ADD":
                    measurements[position] += value
                else:
                    measurements[position] = max(measurements[position], value)
        ordered_measurements = [
            {
                "metric_position": position,
                "metric_name": metric_names[position],
                "measured_value": measurements[position],
            }
            for position in range(1, 19)
        ]
        without_id = {
            "oracle_position": oracle_position,
            "ordered_coverage_tags": coverage_tags,
            "complete_logical_count_plan": plan,
            "exact_source_objects_or_fixture_locators": sources,
            "ordered_logical_event_tokens": tokens,
            "event_stream_preimage_canonical_octets_hex": stream_preimage.hex(),
            "event_stream_preimage_sha256": stream_digest,
            "ordered_expected_resource_measurements": ordered_measurements,
            "final_result_canonical_octets_hex": final_raw.hex(),
            "final_result_sha256": _sha256(final_raw),
            "ordered_live_set_snapshots": snapshots,
            "expected_status": "ACCEPT",
        }
        oracle_id = _sha256(
            _compact_canonical_bytes(
                {
                    "domain": ("RiskYieldMMStep2CaseEventHandOracleV1V4_9F_RawV8"),
                    "payload": without_id,
                }
            )
        )
        return {
            "oracle_position": oracle_position,
            "oracle_id": oracle_id,
            **{
                name: without_id[name]
                for name in ORACLE_MEMBERS
                if name not in {"oracle_position", "oracle_id"}
            },
        }

    return [
        build(
            oracle_position=1,
            oracle_name="ORDINARY_BATCHED_STRUCTURAL_MICROFIXTURE",
            plan_position=67,
            coverage_tags=[
                "UNRESTRICTED_BOOLEAN",
                "NULLABLE",
                "FINITE_TEXT",
                "RELAXED_TEXT",
                "SAFE_INTEGER",
                "BATCHED_ARRAY",
                "RECORD",
                "SELF_VALUE_UNION",
                "OWNER_PAYLOAD_UNION",
                "CODEC_INTERSECTION",
            ],
            local=False,
            context=False,
            batched=True,
        ),
        build(
            oracle_position=2,
            oracle_name="ORDINARY_STREAM_CONTEXT_MICROFIXTURE",
            plan_position=68,
            coverage_tags=["STREAM_FALLBACK_ARRAY", "CONTEXT_APPLICATION_SCHEDULE"],
            local=False,
            context=True,
            batched=False,
        ),
        build(
            oracle_position=3,
            oracle_name="LOCAL_CONTROLLER_MICROFIXTURE",
            plan_position=475,
            coverage_tags=["LOCAL_SHUTDOWN_CASE_475"],
            local=True,
            context=False,
            batched=False,
        ),
    ]


def _catalog() -> dict[str, Any]:
    value = json.loads(CATALOG_PATH.read_bytes())
    assert type(value) is dict
    return value


def _event_catalog(catalog: dict[str, Any]) -> dict[str, Any]:
    event_catalog = catalog["logical_event_catalog"]
    identity = next(
        row
        for row in catalog["ordered_identity_domain_records"]
        if row["identity_name"] == "LOGICAL_EVENT_CATALOG"
    )
    assert "case_level_event_grammar" in identity["ordered_payload_member_names"], (
        "LOGICAL_EVENT_CATALOG identity does not bind the case-level event grammar"
    )
    assert "case_level_event_grammar" in event_catalog, (
        "label-only event catalog: closed case-level grammar is absent"
    )
    return event_catalog


def _program_tuple(record: dict[str, Any]) -> tuple[str, str, str, tuple[str, ...]]:
    assert set(record) == {
        "program_position",
        "program_name",
        "opcode",
        "case_selection",
        "iteration_source",
        "ordinal_source",
        "ordered_event_emission_records",
    }
    iteration = record["iteration_source"]
    ordinal = record["ordinal_source"]
    assert set(iteration) == {
        "source_kind",
        "source_locator",
        "cardinality_expression",
    }
    assert type(iteration["source_locator"]) is dict
    assert type(iteration["cardinality_expression"]) is dict
    assert set(ordinal) == {"ordinal_kind", "reset_scope"}
    emissions = record["ordered_event_emission_records"]
    assert [row["emission_position"] for row in emissions] == list(
        range(1, len(emissions) + 1)
    )
    for row in emissions:
        assert set(row) == {
            "emission_position",
            "event_kind",
            "execution_phase",
            "condition_expression",
            "cardinality_expression",
            "subject_collection_locator",
            "subject_order",
            "subject_ordinal_source",
            "aggregation_multiplicity_expression",
            "logical_unbatched_equivalent_count_expression",
        }
        assert row["event_kind"] in EVENT_KINDS
        assert row["execution_phase"] in PHASES
        assert type(row["condition_expression"]) is dict
        assert type(row["cardinality_expression"]) is dict
        assert type(row["subject_collection_locator"]) is dict
        assert type(row["subject_ordinal_source"]) is dict
        assert type(row["aggregation_multiplicity_expression"]) is dict
        assert type(row["logical_unbatched_equivalent_count_expression"]) is dict
        aggregation = row["aggregation_multiplicity_expression"]
        logical_unbatched = row["logical_unbatched_equivalent_count_expression"]
        if row["event_kind"] in AGGREGATABLE_EVENT_KINDS:
            assert aggregation.get("opcode") == "SOURCE_FIELD_U128"
            assert aggregation.get("field_name") == "aggregation_multiplicity"
        else:
            # Event aggregation is never a substitute for physical byte-bearing
            # subjects or for any other one-operation event.
            assert aggregation == ONE_EXPRESSION
        if row["event_kind"] == "TRANSITION_ATTEMPT":
            assert logical_unbatched.get("opcode") == "SOURCE_FIELD_U128"
            assert logical_unbatched.get("field_name") == (
                "logical_unbatched_equivalent_count"
            )
        else:
            assert logical_unbatched == ZERO_EXPRESSION
    return (
        record["program_name"],
        record["opcode"],
        record["case_selection"],
        tuple(row["event_kind"] for row in emissions),
    )


def _hash_program_tuple(
    record: dict[str, Any],
) -> tuple[str, str, tuple[str, ...]]:
    assert set(record) == {
        "hash_program_position",
        "hash_program_name",
        "opcode",
        "iteration_source",
        "ordinal_source",
        "ordered_hash_source_records",
    }
    assert type(record["iteration_source"]) is dict
    assert type(record["ordinal_source"]) is dict
    sources = record["ordered_hash_source_records"]
    assert [row["hash_source_position"] for row in sources] == list(
        range(1, len(sources) + 1)
    )
    for row in sources:
        assert set(row) == {
            "hash_source_position",
            "hash_purpose",
            "source_locator",
            "cardinality_expression",
            "ordinal_source",
        }
        assert type(row["source_locator"]) is dict
        assert type(row["cardinality_expression"]) is dict
        assert type(row["ordinal_source"]) is dict
    return (
        record["hash_program_name"],
        record["opcode"],
        tuple(row["hash_purpose"] for row in sources),
    )


def _challenger_minimal_catalog() -> dict[str, Any]:
    """Build a non-authoritative grammar fixture for validator self-testing.

    It deliberately contains no hand-oracle rows. That omission lets one test
    exercise every structural branch while a separate test proves that the
    normal acceptance gate still rejects a contract without real oracles.
    """

    expression_opcodes = [
        "CONST_U128",
        "SOURCE_LIST_COUNT",
        "SOURCE_FIELD_U128",
        "INDICATOR_SOURCE_PRESENT",
        "CHECKED_ADD",
        "CHECKED_MUL",
    ]
    subjects = [
        {
            "subject_schema_position": position,
            "event_kind": kind,
            "subject_schema_version": f"challenger.subject.{position}.v1",
            "subject_kind": SUBJECT_KINDS[kind],
            "subject_role_source": "EMISSION_RECORD_SUBJECT_ROLE",
            "logical_derivation_step_position_source": (
                "EMISSION_RECORD_DERIVATION_UNIT"
            ),
            "subject_ordinal_source": "EMISSION_RECORD_SUBJECT_ORDINAL",
            "subject_bytes_source": {"source": "EXACT_SUBJECT_COLLECTION_ITEM"},
            "subject_sha256_source": "SHA256_EXACT_SUBJECT_BYTES",
            "aggregation_multiplicity_source": (
                "EMISSION_RECORD_AGGREGATION_MULTIPLICITY_EXPRESSION"
            ),
            "logical_unbatched_equivalent_count_source": (
                "EMISSION_RECORD_LOGICAL_UNBATCHED_EQUIVALENT_COUNT_EXPRESSION"
            ),
            "observed_value_source": "EMISSION_RECORD_OBSERVED_VALUE",
        }
        for position, kind in enumerate(EVENT_KINDS, 1)
    ]
    phase_by_program = {
        "CASE_OPEN": "CASE_OPEN",
        "BOUND_PLAN_HASH_PREIMAGE": "PLAN_IDENTITY_BINDING",
        "ORDINARY_POSTORDER_STEPS": "UPPER_BOUND_DERIVATION",
        "LOCAL_CONTROLLER": "UPPER_BOUND_DERIVATION",
        "EXACT_ATTAINER_VALIDATION": "LEGAL_ATTAINMENT_VALIDATION",
        "SCOPE_APPLICATIONS": "SCOPE_APPLICATION_VALIDATION",
        "DEPTH_AND_RETENTION": "DEPTH_AND_RETENTION_FINALIZATION",
        "FINAL_RESULT": "FINAL_RESULT_SERIALIZATION",
        "STREAM_FINALIZATION": "EVENT_STREAM_FINALIZATION",
    }
    programs = []
    for program_position, (name, opcode, selection, kinds) in enumerate(PROGRAMS, 1):
        emissions = []
        for emission_position, kind in enumerate(kinds, 1):
            aggregation = (
                {
                    "opcode": "SOURCE_FIELD_U128",
                    "field_name": "aggregation_multiplicity",
                }
                if kind in AGGREGATABLE_EVENT_KINDS
                else copy.deepcopy(ONE_EXPRESSION)
            )
            logical_unbatched = (
                {
                    "opcode": "SOURCE_FIELD_U128",
                    "field_name": "logical_unbatched_equivalent_count",
                }
                if kind == "TRANSITION_ATTEMPT"
                else copy.deepcopy(ZERO_EXPRESSION)
            )
            emissions.append(
                {
                    "emission_position": emission_position,
                    "event_kind": kind,
                    "execution_phase": phase_by_program[name],
                    "condition_expression": copy.deepcopy(ONE_EXPRESSION),
                    "cardinality_expression": copy.deepcopy(ONE_EXPRESSION),
                    "subject_collection_locator": {
                        "source": "CHALLENGER_EXACT_SUBJECT_COLLECTION"
                    },
                    "subject_order": "PROGRAM_FROZEN_ORDER",
                    "subject_ordinal_source": {"source": "CHALLENGER_SUBJECT_ORDINAL"},
                    "aggregation_multiplicity_expression": aggregation,
                    "logical_unbatched_equivalent_count_expression": (
                        logical_unbatched
                    ),
                }
            )
        programs.append(
            {
                "program_position": program_position,
                "program_name": name,
                "opcode": opcode,
                "case_selection": selection,
                "iteration_source": {
                    "source_kind": "CHALLENGER_DERIVATION_UNIT_SOURCE",
                    "source_locator": {"program_name": name},
                    "cardinality_expression": copy.deepcopy(ONE_EXPRESSION),
                },
                "ordinal_source": {
                    "ordinal_kind": "PROGRAM_FROZEN_ORDER",
                    "reset_scope": "CASE",
                },
                "ordered_event_emission_records": emissions,
            }
        )

    hash_programs = []
    for position, (name, opcode, purposes) in enumerate(HASH_PROGRAMS, 1):
        per_unit = name == "DERIVATION_UNITS_POSTORDER"
        sources = []
        for source_position, purpose in enumerate(purposes, 1):
            if purpose == "RETAINED_RESULT_CELL_PREIMAGE":
                cardinality = {
                    "opcode": "SOURCE_LIST_COUNT",
                    "source_locator": {"source": "CURRENT_UNIT_RETAINED_CELLS"},
                }
                ordinal = {
                    "primary": "CURRENT_DERIVATION_UNIT",
                    "secondary": "COMPLETE_CANONICAL_CELL_KEY_BYTES",
                }
            elif purpose == "STEP_COMMITMENT_PREIMAGE":
                cardinality = copy.deepcopy(ONE_EXPRESSION)
                ordinal = {
                    "primary": "CURRENT_DERIVATION_UNIT",
                    "secondary": "SINGLE_COMMITMENT_AFTER_ALL_CELL_HASHES",
                }
            else:
                cardinality = copy.deepcopy(ONE_EXPRESSION)
                ordinal = {"primary": "SINGLETON", "secondary": None}
            sources.append(
                {
                    "hash_source_position": source_position,
                    "hash_purpose": purpose,
                    "source_locator": {"source": purpose},
                    "cardinality_expression": cardinality,
                    "ordinal_source": ordinal,
                }
            )
        hash_programs.append(
            {
                "hash_program_position": position,
                "hash_program_name": name,
                "opcode": opcode,
                "iteration_source": {
                    "source": ("ALL_DERIVATION_UNITS" if per_unit else "SINGLETON")
                },
                "ordinal_source": (
                    {
                        "primary": "STRICT_DERIVATION_UNIT_POSTORDER",
                        "local_case_unit_count": 1,
                    }
                    if per_unit
                    else {"primary": "SINGLETON", "local_case_unit_count": 0}
                ),
                "ordered_hash_source_records": sources,
            }
        )

    transition = {
        "contract_version": "challenger.transition_expansion.v1",
        "unknown_or_extra_member_policy": "REJECT",
        "ordered_run_record_member_names": [
            "transition_run_position",
            "transition_source_kind",
            "first_physical_transition_ordinal",
            "physical_transition_count",
            "logical_unbatched_equivalent_count",
            "token_subject_expansion_program",
            "logical_count_distribution_program",
            "canonical_octet_sum_program",
        ],
        "ordinary_run_source": (
            "RECURRENCE_KERNEL_CLOSED_TRANSITION_EXPANSION_PROGRAM"
        ),
        "local_run_source": (
            "ELEVEN_CONTROLLER_TRANSITIONS_ONE_TO_ONE_PHYSICAL_1_LOGICAL_1"
        ),
        "run_order": "CONTIGUOUS_PHYSICAL_TRANSITION_ORDINAL_RANGES",
        "physical_event_expansion_rule": (
            "EMIT_EXACTLY_PHYSICAL_TRANSITION_COUNT_DISTINCT_TOKENS"
        ),
        "logical_count_distribution_rule": (
            "PER_TOKEN_POSITIVE_U128_SUM_EQUALS_RUN_LOGICAL_UNBATCHED_COUNT"
        ),
        "transition_aggregation_policy": (
            "EVERY_EMITTED_TOKEN_AGGREGATION_MULTIPLICITY_ONE"
        ),
        "transition_byte_accounting_policy": (
            "SUM_EXACT_PER_TOKEN_CANONICAL_OCTETS_NEVER_RESIZE_ONE_TOKEN"
        ),
        "ordered_reconciliation_equations": [
            "SUM_RUN_PHYSICAL_COUNTS_EQUALS_KERNEL_PHYSICAL_TRANSITION_COUNT",
            "SUM_RUN_LOGICAL_COUNTS_EQUALS_KERNEL_LOGICAL_UNBATCHED_EQUIVALENT_COUNT",
            "EMITTED_TOKEN_COUNT_EQUALS_SUM_RUN_PHYSICAL_COUNTS",
            "SUM_TOKEN_LOGICAL_COUNTS_EQUALS_SUM_RUN_LOGICAL_COUNTS",
            "SUM_TOKEN_CANONICAL_OCTETS_EQUALS_EXACT_RUN_CANONICAL_OCTET_SUM",
        ],
        "hand_oracle_scale_policy": (
            "BOUNDED_DISCRIMINATING_MICROFIXTURES_UP_TO_CARDINALITY_16"
        ),
    }
    live_set = {
        "program_version": "challenger.live_set.v1",
        "ordered_retained_subject_kinds": [
            "RECURRENCE_CACHE_KEY_V2",
            "RECURRENCE_RESULT_CELL_V2",
            "RECURRENCE_STEP_COMMITMENT_V2",
        ],
        "equal_bytes_distinct_entries_count_separately": True,
        "last_parent_source": "POSTORDER_DAG_EXACT_REVERSE_PARENT_INDEX",
        "ordered_observation_points": [
            "LIVE_CHILDREN_BEFORE_PARENT",
            "LIVE_CHILDREN_PLUS_PROSPECTIVE_PARENT",
            "AFTER_PARENT_COMMITMENT_HASH_AND_RELEASE",
            "ROOT_COMMITMENT_DIGEST_THROUGH_FINAL_RESULT_HASH",
        ],
        "release_order": "REVERSE_CHILD_STEP_POSITION_IMMEDIATELY_AFTER_LAST_USE",
        "full_commitment_preimage_release_point": (
            "IMMEDIATELY_AFTER_CURRENT_DERIVATION_UNIT_COMMITMENT_HASH"
        ),
        "post_hash_commitment_material_policy": (
            "DIGEST_ONLY_IF_REQUIRED_NEVER_RETAIN_FULL_PREIMAGE"
        ),
        "ordered_excluded_transient_kinds": [
            "TRANSITION_TOKEN_BUFFER",
            "CANONICALIZER_SCRATCH",
            "SOURCE_AUTHORITY_BYTES",
            "EVENT_TOKEN_BYTES",
            "FINAL_RESULT_SERIALIZER_BUFFER",
            "EVENT_STREAM_PREIMAGE_BUFFER",
        ],
    }
    grammar = {
        "grammar_version": "challenger.case_event_grammar.v1",
        "unknown_or_extra_member_policy": "REJECT",
        "global_event_position_rule": "CONTIGUOUS_ONE_BASED_COMPLETE_CASE_STREAM",
        "event_ordinal_rule": "CONTIGUOUS_ONE_BASED_PER_EVENT_KIND_PER_CASE",
        "event_expression_instruction_set": {
            "instruction_set_version": "challenger.event_expression.v1",
            "unknown_or_extra_member_policy": "REJECT",
            "evaluation_order": "DEPTH_FIRST_LEFT_TO_RIGHT_CHECKED_UINT128",
            "ordered_opcode_records": [
                {"opcode_position": position, "opcode": opcode}
                for position, opcode in enumerate(expression_opcodes, 1)
            ],
        },
        "event_metadata_program": {
            "binding_rule": (
                "ZIP_PROGRAM_POSITION_THEN_EMISSION_POSITION_AND_MATERIALIZE_"
                "METADATA_ON_EMISSION_RECORD_BEFORE_TOKENIZATION_V1"
            ),
            "logical_derivation_step_position_source_enum": [
                "NULL",
                "CURRENT_ORDINARY_TEMPLATE_STEP_POSITION",
            ],
            "observed_value_source_enum": ["NULL", "SUBJECT_OBSERVED_VALUE"],
            "ordered_program_metadata_records": [
                {
                    "logical_derivation_step_position_source": (
                        "CURRENT_ORDINARY_TEMPLATE_STEP_POSITION"
                        if program["program_name"] == "ORDINARY_POSTORDER_STEPS"
                        else "NULL"
                    ),
                    "observed_value_sources": [
                        (
                            "SUBJECT_OBSERVED_VALUE"
                            if emission["event_kind"]
                            in {
                                "RETENTION_OBSERVATION",
                                "DERIVATION_DEPTH_OBSERVATION",
                                "ITERATION_DEPTH_OBSERVATION",
                            }
                            else "NULL"
                        )
                        for emission in program["ordered_event_emission_records"]
                    ],
                    "ordered_subject_role_literals": [
                        f"CHALLENGER_{program['program_name']}_{position}"
                        for position, _emission in enumerate(
                            program["ordered_event_emission_records"], 1
                        )
                    ],
                    "program_name": program["program_name"],
                    "program_position": program["program_position"],
                    "subject_ordinal_sources": [
                        "EMISSION_SUBJECT_COLLECTION_ORDINAL"
                        for _emission in program["ordered_event_emission_records"]
                    ],
                }
                for program in programs
            ],
            "program_version": (
                "riskyieldmm.raw_v8_step2_external_schema_v2.event_metadata_program.v1"
            ),
            "subject_ordinal_source_enum": [
                "NULL",
                "EMISSION_SUBJECT_COLLECTION_ORDINAL",
                "EVENT_KIND_ORDINAL",
                "DERIVATION_UNIT_ORDINAL",
            ],
            "unknown_or_extra_member_policy": "REJECT",
        },
        "ordered_execution_phase_records": [
            {"phase_position": position, "execution_phase": phase}
            for position, phase in enumerate(PHASES, 1)
        ],
        "ordered_subject_schema_records": subjects,
        "ordered_case_program_records": programs,
        "full_case_execution_program": {},
        "transition_expansion_contract": transition,
        "ordered_case_hash_program_records": hash_programs,
        "byte_metric_partition": {
            "global_validation_hash_policy": (
                "F0_PREFLIGHT_ONLY_EXCLUDED_FROM_PER_CASE_M11"
            ),
            "term_uniqueness_key": ["metric_position", "event_position"],
            "term_coefficient": 1,
            "event_token_serialization_policy": "OUTSIDE_M8_M9_M10_M18",
            "nested_container_policy": "FINAL_RESULT_ONLY_ONCE_IN_M18",
            "m18_complete_final_result_event_count": 1,
            "m18_fragment_or_nested_result_policy": "REJECT",
            "ordered_metric_equation_records": [
                {
                    "metric_position": metric_position,
                    "ordered_term_records": [
                        {
                            "event_kind": event_kind,
                            "subject_kind": subject_kind,
                            "coefficient": 1,
                        }
                        for event_kind, subject_kind in terms
                    ],
                }
                for metric_position, terms in BYTE_EQUATIONS.items()
            ],
        },
        "live_set_program": live_set,
        "stream_finalization_program": {
            "program_version": "challenger.stream_finalization.v1",
            "preimage_member_names": [
                "logical_event_stream_version",
                "logical_count_plan_id",
                "ordered_pre_close_logical_event_tokens",
            ],
            "ordered_terminal_event_kinds": ["EVENT_STREAM_CLOSE", "HASH_PREIMAGE"],
            "close_event_in_preimage": False,
            "hash_event_in_preimage": False,
            "comparator_recomputes_excluded_control_events": True,
            "event_after_final_hash_policy": "REJECT",
            "stream_hash_algorithm": "SHA256",
            "stream_hash_subject_kind": "EVENT_STREAM_PREIMAGE",
        },
        "final_result_subject_contract": {
            "contract_version": (
                "challenger.logical_case_derivation_result_contract.v1"
            ),
            "subject_kind": "LOGICAL_CASE_DERIVATION_RESULT_V1",
            "ordered_member_names": [
                "logical_case_derivation_result_version",
                "logical_count_plan_id",
                "result_status",
                "ordered_root_result_cell_digest_records",
                "ordered_step_commitment_digest_records",
            ],
            "commitment_material_member_name": (
                "ordered_step_commitment_digest_records"
            ),
            "commitment_digest_record_schema": {
                "ordered_member_names": [
                    "derivation_unit_ordinal",
                    "subject_variant",
                    "logical_derivation_step_position",
                    "local_controller_unit_ordinal",
                    "step_commitment_sha256",
                ],
                "digest_algorithm": "SHA256",
                "ordinary_local_null_rule": (
                    "EXACTLY_ONE_OF_LOGICAL_STEP_OR_LOCAL_UNIT_PRESENT"
                ),
            },
            "forbidden_member_names": [
                "ordered_step_result_commitments",
                "ordered_step_commitment_preimages",
            ],
            "complete_commitment_preimage_lifetime": (
                "RELEASE_IMMEDIATELY_AFTER_PER_UNIT_HASH"
            ),
            "unknown_or_extra_member_policy": "REJECT",
        },
        "hand_oracle_contract": {
            "contract_version": "challenger.hand_oracle_contract.v1",
            "ordered_required_member_names": list(ORACLE_MEMBERS),
            "required_metric_positions": list(range(1, 19)),
            "ordered_required_coverage_tags": list(REQUIRED_COVERAGE_TAGS),
            "ordered_required_mutation_classes": list(MUTATION_CLASSES),
        },
        "ordered_hand_oracle_records": [],
    }
    event_catalog = {
        "event_schema": {
            "ordered_member_names": list(TOKEN_MEMBERS),
            "subject_digest_algorithm": "SHA256",
            "subject_bytes_are_recomputed": True,
        },
        "metric_update_schema": {
            "ordered_member_names": [
                "metric_position",
                "update_kind",
                "value_source",
            ],
            "update_kind_enum": ["ADD", "MAX"],
            "value_source_enum": [
                "ONE",
                "SUBJECT_CANONICAL_OCTETS",
                "AGGREGATION_MULTIPLICITY",
                "LOGICAL_UNBATCHED_EQUIVALENT_COUNT",
                "OBSERVED_VALUE",
            ],
        },
        "ordered_event_kind_records": [
            {
                "event_kind_position": position,
                "event_kind": kind,
                "subject_schema_version": subjects[position - 1][
                    "subject_schema_version"
                ],
                "ordered_allowed_execution_phases": list(PHASES),
                "ordered_metric_update_program": [
                    {
                        "metric_position": metric_position,
                        "update_kind": update_kind,
                        "value_source": value_source,
                    }
                    for metric_position, update_kind, value_source in METRIC_PROGRAMS[
                        kind
                    ]
                ],
            }
            for position, kind in enumerate(EVENT_KINDS, 1)
        ],
        "case_level_event_grammar": grammar,
    }
    return {
        "ordered_identity_domain_records": [
            {
                "identity_name": "LOGICAL_EVENT_CATALOG",
                "ordered_payload_member_names": [
                    "event_schema",
                    "metric_update_schema",
                    "ordered_event_kind_records",
                    "case_level_event_grammar",
                ],
            }
        ],
        "logical_event_catalog": event_catalog,
    }


def _validate_catalog_event_grammar(
    catalog: dict[str, Any], *, require_complete_oracles: bool = True
) -> None:
    event_catalog = _event_catalog(catalog)
    grammar = event_catalog["case_level_event_grammar"]
    assert set(grammar) == {
        "grammar_version",
        "unknown_or_extra_member_policy",
        "global_event_position_rule",
        "event_ordinal_rule",
        "event_expression_instruction_set",
        "event_metadata_program",
        "ordered_execution_phase_records",
        "ordered_subject_schema_records",
        "ordered_case_program_records",
        "transition_expansion_contract",
        "ordered_case_hash_program_records",
        "byte_metric_partition",
        "live_set_program",
        "stream_finalization_program",
        "final_result_subject_contract",
        "full_case_execution_program",
        "hand_oracle_contract",
        "ordered_hand_oracle_records",
    }
    assert grammar["unknown_or_extra_member_policy"] == "REJECT"
    assert (
        grammar["global_event_position_rule"]
        == "CONTIGUOUS_ONE_BASED_COMPLETE_CASE_STREAM"
    )
    assert (
        grammar["event_ordinal_rule"] == "CONTIGUOUS_ONE_BASED_PER_EVENT_KIND_PER_CASE"
    )

    expression_set = grammar["event_expression_instruction_set"]
    assert set(expression_set) == {
        "instruction_set_version",
        "unknown_or_extra_member_policy",
        "evaluation_order",
        "ordered_opcode_records",
    }
    assert expression_set["unknown_or_extra_member_policy"] == "REJECT"
    assert (
        expression_set["evaluation_order"]
        == "DEPTH_FIRST_LEFT_TO_RIGHT_CHECKED_UINT128"
    )
    assert [
        row["opcode_position"] for row in expression_set["ordered_opcode_records"]
    ] == list(range(1, len(expression_set["ordered_opcode_records"]) + 1))
    assert [row["opcode"] for row in expression_set["ordered_opcode_records"]] == [
        "CONST_U128",
        "SOURCE_LIST_COUNT",
        "SOURCE_FIELD_U128",
        "INDICATOR_SOURCE_PRESENT",
        "CHECKED_ADD",
        "CHECKED_MUL",
    ]

    metadata = grammar["event_metadata_program"]
    assert set(metadata) == {
        "binding_rule",
        "logical_derivation_step_position_source_enum",
        "observed_value_source_enum",
        "ordered_program_metadata_records",
        "program_version",
        "subject_ordinal_source_enum",
        "unknown_or_extra_member_policy",
    }
    assert metadata["binding_rule"] == (
        "ZIP_PROGRAM_POSITION_THEN_EMISSION_POSITION_AND_MATERIALIZE_METADATA_"
        "ON_EMISSION_RECORD_BEFORE_TOKENIZATION_V1"
    )
    assert metadata["logical_derivation_step_position_source_enum"] == [
        "NULL",
        "CURRENT_ORDINARY_TEMPLATE_STEP_POSITION",
    ]
    assert metadata["observed_value_source_enum"] == [
        "NULL",
        "SUBJECT_OBSERVED_VALUE",
    ]
    assert metadata["subject_ordinal_source_enum"] == [
        "NULL",
        "EMISSION_SUBJECT_COLLECTION_ORDINAL",
        "EVENT_KIND_ORDINAL",
        "DERIVATION_UNIT_ORDINAL",
    ]
    assert metadata["unknown_or_extra_member_policy"] == "REJECT"
    programs_for_metadata = grammar["ordered_case_program_records"]
    metadata_rows = metadata["ordered_program_metadata_records"]
    assert len(metadata_rows) == len(programs_for_metadata) == 9
    observed_kinds = {
        "RETENTION_OBSERVATION",
        "DERIVATION_DEPTH_OBSERVATION",
        "ITERATION_DEPTH_OBSERVATION",
    }
    for position, (program, row) in enumerate(
        zip(programs_for_metadata, metadata_rows, strict=True), 1
    ):
        emissions = program["ordered_event_emission_records"]
        assert set(row) == {
            "logical_derivation_step_position_source",
            "observed_value_sources",
            "ordered_subject_role_literals",
            "program_name",
            "program_position",
            "subject_ordinal_sources",
        }
        assert row["program_position"] == program["program_position"] == position
        assert row["program_name"] == program["program_name"]
        assert (
            len(row["ordered_subject_role_literals"])
            == len(row["subject_ordinal_sources"])
            == len(row["observed_value_sources"])
            == len(emissions)
        )
        assert row["logical_derivation_step_position_source"] == (
            "CURRENT_ORDINARY_TEMPLATE_STEP_POSITION"
            if program["program_name"] == "ORDINARY_POSTORDER_STEPS"
            else "NULL"
        )
        assert all(
            type(role) is str and role and role == role.upper()
            for role in row["ordered_subject_role_literals"]
        )
        assert all(
            source in metadata["subject_ordinal_source_enum"]
            for source in row["subject_ordinal_sources"]
        )
        assert [
            source == "SUBJECT_OBSERVED_VALUE"
            for source in row["observed_value_sources"]
        ] == [emission["event_kind"] in observed_kinds for emission in emissions]

    token_schema = event_catalog["event_schema"]
    assert token_schema["ordered_member_names"] == list(TOKEN_MEMBERS)
    assert token_schema["subject_digest_algorithm"] == "SHA256"
    assert token_schema["subject_bytes_are_recomputed"] is True

    metric_schema = event_catalog["metric_update_schema"]
    assert metric_schema["ordered_member_names"] == [
        "metric_position",
        "update_kind",
        "value_source",
    ]
    assert metric_schema["update_kind_enum"] == ["ADD", "MAX"]
    assert metric_schema["value_source_enum"] == [
        "ONE",
        "SUBJECT_CANONICAL_OCTETS",
        "AGGREGATION_MULTIPLICITY",
        "LOGICAL_UNBATCHED_EQUIVALENT_COUNT",
        "OBSERVED_VALUE",
    ]

    phases = grammar["ordered_execution_phase_records"]
    assert [row["phase_position"] for row in phases] == list(range(1, len(PHASES) + 1))
    assert [row["execution_phase"] for row in phases] == list(PHASES)
    assert len({row["execution_phase"] for row in phases}) == len(PHASES)
    assert all(set(row) == {"phase_position", "execution_phase"} for row in phases)

    subjects = grammar["ordered_subject_schema_records"]
    assert [row["subject_schema_position"] for row in subjects] == list(
        range(1, len(EVENT_KINDS) + 1)
    )
    assert [row["event_kind"] for row in subjects] == list(EVENT_KINDS)
    assert len({row["subject_schema_version"] for row in subjects}) == len(subjects)
    for row in subjects:
        assert set(row) == {
            "subject_schema_position",
            "event_kind",
            "subject_schema_version",
            "subject_kind",
            "subject_role_source",
            "logical_derivation_step_position_source",
            "subject_ordinal_source",
            "subject_bytes_source",
            "subject_sha256_source",
            "aggregation_multiplicity_source",
            "logical_unbatched_equivalent_count_source",
            "observed_value_source",
        }
        assert row["subject_kind"] == SUBJECT_KINDS[row["event_kind"]]
        assert type(row["subject_bytes_source"]) is dict
        assert row["subject_sha256_source"] == "SHA256_EXACT_SUBJECT_BYTES"
        assert row["aggregation_multiplicity_source"] == (
            "EMISSION_RECORD_AGGREGATION_MULTIPLICITY_EXPRESSION"
        )
        assert row["logical_unbatched_equivalent_count_source"] == (
            "EMISSION_RECORD_LOGICAL_UNBATCHED_EQUIVALENT_COUNT_EXPRESSION"
        )

    event_rows = event_catalog["ordered_event_kind_records"]
    assert [row["event_kind"] for row in event_rows] == list(EVENT_KINDS)
    assert len({row["event_kind"] for row in event_rows}) == len(EVENT_KINDS)
    subject_by_kind = {row["event_kind"]: row for row in subjects}
    for row in event_rows:
        assert set(row) == {
            "event_kind_position",
            "event_kind",
            "subject_schema_version",
            "ordered_allowed_execution_phases",
            "ordered_metric_update_program",
        }
        assert (
            row["subject_schema_version"]
            == subject_by_kind[row["event_kind"]]["subject_schema_version"]
        )
        assert row["ordered_allowed_execution_phases"]
        assert set(row["ordered_allowed_execution_phases"]) <= set(PHASES)
        actual = tuple(
            (item["metric_position"], item["update_kind"], item["value_source"])
            for item in row["ordered_metric_update_program"]
        )
        assert actual == METRIC_PROGRAMS[row["event_kind"]]

    programs = grammar["ordered_case_program_records"]
    assert [row["program_position"] for row in programs] == list(
        range(1, len(PROGRAMS) + 1)
    )
    assert [_program_tuple(row) for row in programs] == list(PROGRAMS)
    assert len({row["program_name"] for row in programs}) == len(PROGRAMS)

    transition = grammar["transition_expansion_contract"]
    assert set(transition) == {
        "contract_version",
        "unknown_or_extra_member_policy",
        "ordered_run_record_member_names",
        "ordinary_run_source",
        "local_run_source",
        "run_order",
        "physical_event_expansion_rule",
        "logical_count_distribution_rule",
        "transition_aggregation_policy",
        "transition_byte_accounting_policy",
        "ordered_reconciliation_equations",
        "hand_oracle_scale_policy",
    }
    assert transition["unknown_or_extra_member_policy"] == "REJECT"
    assert transition["ordered_run_record_member_names"] == [
        "transition_run_position",
        "transition_source_kind",
        "first_physical_transition_ordinal",
        "physical_transition_count",
        "logical_unbatched_equivalent_count",
        "token_subject_expansion_program",
        "logical_count_distribution_program",
        "canonical_octet_sum_program",
    ]
    assert transition["ordinary_run_source"] == (
        "RECURRENCE_KERNEL_CLOSED_TRANSITION_EXPANSION_PROGRAM"
    )
    assert transition["local_run_source"] == (
        "ELEVEN_CONTROLLER_TRANSITIONS_ONE_TO_ONE_PHYSICAL_1_LOGICAL_1"
    )
    assert transition["run_order"] == ("CONTIGUOUS_PHYSICAL_TRANSITION_ORDINAL_RANGES")
    assert transition["physical_event_expansion_rule"] == (
        "EMIT_EXACTLY_PHYSICAL_TRANSITION_COUNT_DISTINCT_TOKENS"
    )
    assert transition["logical_count_distribution_rule"] == (
        "PER_TOKEN_POSITIVE_U128_SUM_EQUALS_RUN_LOGICAL_UNBATCHED_COUNT"
    )
    assert transition["transition_aggregation_policy"] == (
        "EVERY_EMITTED_TOKEN_AGGREGATION_MULTIPLICITY_ONE"
    )
    assert transition["transition_byte_accounting_policy"] == (
        "SUM_EXACT_PER_TOKEN_CANONICAL_OCTETS_NEVER_RESIZE_ONE_TOKEN"
    )
    assert transition["ordered_reconciliation_equations"] == [
        "SUM_RUN_PHYSICAL_COUNTS_EQUALS_KERNEL_PHYSICAL_TRANSITION_COUNT",
        "SUM_RUN_LOGICAL_COUNTS_EQUALS_KERNEL_LOGICAL_UNBATCHED_EQUIVALENT_COUNT",
        "EMITTED_TOKEN_COUNT_EQUALS_SUM_RUN_PHYSICAL_COUNTS",
        "SUM_TOKEN_LOGICAL_COUNTS_EQUALS_SUM_RUN_LOGICAL_COUNTS",
        "SUM_TOKEN_CANONICAL_OCTETS_EQUALS_EXACT_RUN_CANONICAL_OCTET_SUM",
    ]
    assert transition["hand_oracle_scale_policy"] == (
        "BOUNDED_DISCRIMINATING_MICROFIXTURES_UP_TO_CARDINALITY_16"
    )

    hash_programs = grammar["ordered_case_hash_program_records"]
    assert [row["hash_program_position"] for row in hash_programs] == list(
        range(1, len(HASH_PROGRAMS) + 1)
    )
    assert [_hash_program_tuple(row) for row in hash_programs] == list(HASH_PROGRAMS)
    assert len({row["hash_program_name"] for row in hash_programs}) == len(
        HASH_PROGRAMS
    )
    for singleton_program in (hash_programs[0], hash_programs[2], hash_programs[3]):
        assert (
            singleton_program["ordered_hash_source_records"][0][
                "cardinality_expression"
            ]
            == ONE_EXPRESSION
        )
    per_unit = hash_programs[1]
    assert per_unit["ordinal_source"] == {
        "primary": "STRICT_DERIVATION_UNIT_POSTORDER",
        "local_case_unit_count": 1,
    }
    cell_source, commitment_source = per_unit["ordered_hash_source_records"]
    assert cell_source["ordinal_source"] == {
        "primary": "CURRENT_DERIVATION_UNIT",
        "secondary": "COMPLETE_CANONICAL_CELL_KEY_BYTES",
    }
    assert commitment_source["cardinality_expression"] == ONE_EXPRESSION
    assert commitment_source["ordinal_source"] == {
        "primary": "CURRENT_DERIVATION_UNIT",
        "secondary": "SINGLE_COMMITMENT_AFTER_ALL_CELL_HASHES",
    }
    assert grammar["byte_metric_partition"]["global_validation_hash_policy"] == (
        "F0_PREFLIGHT_ONLY_EXCLUDED_FROM_PER_CASE_M11"
    )

    partition = grammar["byte_metric_partition"]
    assert partition["term_uniqueness_key"] == ["metric_position", "event_position"]
    assert partition["term_coefficient"] == 1
    assert partition["event_token_serialization_policy"] == "OUTSIDE_M8_M9_M10_M18"
    assert partition["nested_container_policy"] == "FINAL_RESULT_ONLY_ONCE_IN_M18"
    assert partition["m18_complete_final_result_event_count"] == 1
    assert partition["m18_fragment_or_nested_result_policy"] == "REJECT"
    equations = partition["ordered_metric_equation_records"]
    assert [row["metric_position"] for row in equations] == [8, 9, 10, 11, 18]
    for row in equations:
        assert set(row) == {"metric_position", "ordered_term_records"}
        terms = tuple(
            (term["event_kind"], term["subject_kind"])
            for term in row["ordered_term_records"]
        )
        assert terms == BYTE_EQUATIONS[row["metric_position"]]
        assert all(term["coefficient"] == 1 for term in row["ordered_term_records"])
        assert all(
            set(term) == {"event_kind", "subject_kind", "coefficient"}
            for term in row["ordered_term_records"]
        )
        assert len(terms) == len(set(terms))

    live = grammar["live_set_program"]
    assert type(live["program_version"]) is str and live["program_version"]
    assert live == {
        "program_version": live["program_version"],
        "ordered_retained_subject_kinds": [
            "RECURRENCE_CACHE_KEY_V2",
            "RECURRENCE_RESULT_CELL_V2",
            "RECURRENCE_STEP_COMMITMENT_V2",
        ],
        "equal_bytes_distinct_entries_count_separately": True,
        "last_parent_source": "POSTORDER_DAG_EXACT_REVERSE_PARENT_INDEX",
        "ordered_observation_points": [
            "LIVE_CHILDREN_BEFORE_PARENT",
            "LIVE_CHILDREN_PLUS_PROSPECTIVE_PARENT",
            "AFTER_PARENT_COMMITMENT_HASH_AND_RELEASE",
            "ROOT_COMMITMENT_DIGEST_THROUGH_FINAL_RESULT_HASH",
        ],
        "release_order": "REVERSE_CHILD_STEP_POSITION_IMMEDIATELY_AFTER_LAST_USE",
        "full_commitment_preimage_release_point": (
            "IMMEDIATELY_AFTER_CURRENT_DERIVATION_UNIT_COMMITMENT_HASH"
        ),
        "post_hash_commitment_material_policy": (
            "DIGEST_ONLY_IF_REQUIRED_NEVER_RETAIN_FULL_PREIMAGE"
        ),
        "ordered_excluded_transient_kinds": [
            "TRANSITION_TOKEN_BUFFER",
            "CANONICALIZER_SCRATCH",
            "SOURCE_AUTHORITY_BYTES",
            "EVENT_TOKEN_BYTES",
            "FINAL_RESULT_SERIALIZER_BUFFER",
            "EVENT_STREAM_PREIMAGE_BUFFER",
        ],
    }

    finalization = grammar["stream_finalization_program"]
    assert finalization["program_version"]
    assert finalization["preimage_member_names"] == [
        "logical_event_stream_version",
        "logical_count_plan_id",
        "ordered_pre_close_logical_event_tokens",
    ]
    assert finalization["ordered_terminal_event_kinds"] == [
        "EVENT_STREAM_CLOSE",
        "HASH_PREIMAGE",
    ]
    assert finalization["close_event_in_preimage"] is False
    assert finalization["hash_event_in_preimage"] is False
    assert finalization["comparator_recomputes_excluded_control_events"] is True
    assert finalization["event_after_final_hash_policy"] == "REJECT"
    assert finalization["stream_hash_algorithm"] == "SHA256"
    assert finalization["stream_hash_subject_kind"] == "EVENT_STREAM_PREIMAGE"

    final_result = grammar["final_result_subject_contract"]
    assert final_result == {
        "contract_version": final_result["contract_version"],
        "subject_kind": "LOGICAL_CASE_DERIVATION_RESULT_V1",
        "ordered_member_names": [
            "logical_case_derivation_result_version",
            "logical_count_plan_id",
            "result_status",
            "ordered_root_result_cell_digest_records",
            "ordered_step_commitment_digest_records",
        ],
        "commitment_material_member_name": ("ordered_step_commitment_digest_records"),
        "commitment_digest_record_schema": {
            "ordered_member_names": [
                "derivation_unit_ordinal",
                "subject_variant",
                "logical_derivation_step_position",
                "local_controller_unit_ordinal",
                "step_commitment_sha256",
            ],
            "digest_algorithm": "SHA256",
            "ordinary_local_null_rule": (
                "EXACTLY_ONE_OF_LOGICAL_STEP_OR_LOCAL_UNIT_PRESENT"
            ),
        },
        "forbidden_member_names": [
            "ordered_step_result_commitments",
            "ordered_step_commitment_preimages",
        ],
        "complete_commitment_preimage_lifetime": (
            "RELEASE_IMMEDIATELY_AFTER_PER_UNIT_HASH"
        ),
        "unknown_or_extra_member_policy": "REJECT",
    }

    oracle = grammar["hand_oracle_contract"]
    assert set(oracle) == {
        "contract_version",
        "ordered_required_member_names",
        "required_metric_positions",
        "ordered_required_coverage_tags",
        "ordered_required_mutation_classes",
    }
    assert type(oracle["contract_version"]) is str and oracle["contract_version"]
    assert oracle["ordered_required_member_names"] == list(ORACLE_MEMBERS)
    assert oracle["required_metric_positions"] == list(range(1, 19))
    assert oracle["ordered_required_mutation_classes"] == list(MUTATION_CLASSES)
    assert set(oracle["ordered_required_coverage_tags"]) >= set(REQUIRED_COVERAGE_TAGS)

    # A schema/contract alone is not a hand oracle. These complete bounded
    # fixtures are an independent acceptance surface and remain mandatory.
    oracles = grammar["ordered_hand_oracle_records"]
    if not oracles:
        assert not require_complete_oracles, (
            "hand-oracle contract exists but complete oracle fixtures are absent"
        )
        return
    assert [row["oracle_position"] for row in oracles] == list(
        range(1, len(oracles) + 1)
    )
    assert len({row["oracle_id"] for row in oracles}) == len(oracles)
    covered: set[str] = set()
    for row in oracles:
        assert set(row) == set(oracle["ordered_required_member_names"])
        assert type(row["complete_logical_count_plan"]) is dict
        assert type(row["exact_source_objects_or_fixture_locators"]) is list
        assert row["exact_source_objects_or_fixture_locators"]
        tokens = row["ordered_logical_event_tokens"]
        assert type(tokens) is list and tokens
        assert [token["event_position"] for token in tokens] == list(
            range(1, len(tokens) + 1)
        )
        ordinals: dict[str, int] = {}
        for token in tokens:
            assert set(token) == set(TOKEN_MEMBERS)
            kind = token["event_kind"]
            assert kind in EVENT_KINDS
            ordinals[kind] = ordinals.get(kind, 0) + 1
            assert token["event_ordinal"] == ordinals[kind]
            assert type(token["subject_canonical_octets"]) is int
            assert token["subject_canonical_octets"] >= 0
            assert type(token["subject_sha256"]) is str
            assert len(token["subject_sha256"]) == 64
            int(token["subject_sha256"], 16)
            assert type(token["aggregation_multiplicity"]) is int
            assert token["aggregation_multiplicity"] >= 1
            assert type(token["logical_unbatched_equivalent_count"]) is int
            assert token["logical_unbatched_equivalent_count"] >= 0
            if kind not in AGGREGATABLE_EVENT_KINDS:
                assert token["aggregation_multiplicity"] == 1
            if kind == "TRANSITION_ATTEMPT":
                assert token["logical_unbatched_equivalent_count"] >= 1
            else:
                assert token["logical_unbatched_equivalent_count"] == 0
        assert sum(token["event_kind"] == "FINAL_RESULT_EMIT" for token in tokens) == 1
        assert tokens[-2]["event_kind"] == "EVENT_STREAM_CLOSE"
        assert tokens[-1]["event_kind"] == "HASH_PREIMAGE"

        stream_bytes = bytes.fromhex(row["event_stream_preimage_canonical_octets_hex"])
        final_bytes = bytes.fromhex(row["final_result_canonical_octets_hex"])
        assert (
            hashlib.sha256(stream_bytes).hexdigest()
            == row["event_stream_preimage_sha256"]
        )
        assert hashlib.sha256(final_bytes).hexdigest() == row["final_result_sha256"]
        measurements = row["ordered_expected_resource_measurements"]
        assert [item["metric_position"] for item in measurements] == list(range(1, 19))
        assert all(
            set(item) == {"metric_position", "metric_name", "measured_value"}
            and type(item["measured_value"]) is int
            and item["measured_value"] >= 0
            for item in measurements
        )
        assert type(row["ordered_live_set_snapshots"]) is list
        assert row["ordered_live_set_snapshots"]
        assert row["expected_status"] == "ACCEPT"
        tags = row["ordered_coverage_tags"]
        assert type(tags) is list and tags
        assert len(tags) == len(set(tags))
        covered.update(tags)
    assert set(oracle["ordered_required_coverage_tags"]) <= covered
    if "logical_plan_recipe_catalog" in catalog:
        assert oracles == _expected_hand_oracle_records(catalog)


def test_catalog_contains_closed_case_level_event_grammar() -> None:
    _validate_catalog_event_grammar(_catalog())


def test_recurrence_subjects_use_closed_ordinary_local_tagged_unions() -> None:
    recurrence = _catalog()["recurrence_catalog"]
    specs = {
        "cache_key_schema": (
            "cache_key_version",
            [
                "logical_count_plan_id",
                "effective_canonical_octet_ceiling",
                "state_signature_id",
                "ordered_state_components",
            ],
            [
                "logical_derivation_step_position",
                "derivation_kind",
                "occurrence_ordinal",
                "array_ordinal",
                "owner_profile_position",
                "application_invocation_ordinal",
                "observation_ordinal",
            ],
            ["local_controller_state_position", "local_controller_state_id"],
        ),
        "transition_token_schema": (
            "transition_token_version",
            [
                "logical_count_plan_id",
                "transition_ordinal",
                "transition_kind",
                "source_state_components",
                "input_symbol",
                "candidate_state_components",
                "candidate_certified_upper_bound_octets",
            ],
            ["logical_derivation_step_position"],
            [
                "local_controller_transition_position",
                "local_controller_transition_id",
                "source_controller_state_id",
                "target_controller_state_id",
            ],
        ),
        "result_cell_schema": (
            "result_cell_version",
            [
                "logical_count_plan_id",
                "state_signature_id",
                "ordered_state_components",
                "cell_status",
                "certified_lower_bound_octets",
                "certified_upper_bound_octets",
            ],
            ["logical_derivation_step_position", "result_cell_ordinal"],
            ["local_controller_state_position", "local_controller_state_id"],
        ),
        "step_commitment_schema": (
            "step_commitment_version",
            [
                "logical_count_plan_id",
                "state_count",
                "certified_upper_bound_octets",
                "ordered_result_cell_sha256",
            ],
            ["logical_derivation_step_position"],
            [
                "local_shutdown_analytic_catalog_id",
                "initial_controller_state_id",
                "terminal_controller_state_id",
            ],
        ),
    }
    for schema_name, (version_member, common, ordinary, local) in specs.items():
        schema = recurrence[schema_name]
        expected_members = [
            version_member,
            "subject_variant",
            *common,
            *ordinary,
            *local,
        ]
        assert schema["ordered_member_names"] == expected_members
        assert schema["discriminant_member_name"] == "subject_variant"
        assert schema["variant_enum"] == ["ORDINARY_STEP", "LOCAL_CONTROLLER"]
        assert schema["canonical_member_order"] == "ORDERED_MEMBER_NAMES"
        assert schema["unknown_or_extra_member_policy"] == "REJECT"
        variants = schema["ordered_variant_records"]
        assert [row["variant_position"] for row in variants] == [1, 2]
        assert [row["subject_variant"] for row in variants] == schema["variant_enum"]
        assert variants[0]["ordered_required_member_names"] == [
            version_member,
            "subject_variant",
            *common,
            *ordinary,
        ]
        assert variants[0]["ordered_null_member_names"] == local
        assert variants[1]["ordered_required_member_names"] == [
            version_member,
            "subject_variant",
            *common,
            *local,
        ]
        assert variants[1]["ordered_null_member_names"] == ordinary
        for variant in variants:
            assert set(variant["ordered_required_member_names"]) | set(
                variant["ordered_null_member_names"]
            ) == set(expected_members)
            assert not set(variant["ordered_required_member_names"]) & set(
                variant["ordered_null_member_names"]
            )


def test_challenger_minimal_grammar_exercises_complete_structural_validator() -> None:
    _validate_catalog_event_grammar(
        _challenger_minimal_catalog(), require_complete_oracles=False
    )


def test_challenger_contract_alone_does_not_satisfy_hand_oracle_gate() -> None:
    with pytest.raises(AssertionError, match="complete oracle fixtures are absent"):
        _validate_catalog_event_grammar(_challenger_minimal_catalog())


@pytest.mark.parametrize(
    "mutation",
    (
        "omit_subject",
        "duplicate_subject",
        "reorder_program",
        "reorder_per_step_hashes",
        "resize_metric_term",
        "aggregate_transition_event",
        "zero_transition_logical_count",
        "count_m18_fragment",
        "duplicate_final_result_emission",
        "release_early",
        "include_close_in_preimage",
        "drop_resize_negative_control",
    ),
)
def test_event_grammar_validator_rejects_adversarial_mutations(mutation: str) -> None:
    catalog = _challenger_minimal_catalog()
    _validate_catalog_event_grammar(catalog, require_complete_oracles=False)
    changed = copy.deepcopy(catalog)
    grammar = changed["logical_event_catalog"]["case_level_event_grammar"]
    if mutation == "omit_subject":
        grammar["ordered_subject_schema_records"].pop()
    elif mutation == "duplicate_subject":
        grammar["ordered_subject_schema_records"][-1] = copy.deepcopy(
            grammar["ordered_subject_schema_records"][-2]
        )
    elif mutation == "reorder_program":
        programs = grammar["ordered_case_program_records"]
        programs[1], programs[2] = programs[2], programs[1]
    elif mutation == "reorder_per_step_hashes":
        sources = grammar["ordered_case_hash_program_records"][1][
            "ordered_hash_source_records"
        ]
        sources[0], sources[1] = sources[1], sources[0]
    elif mutation == "resize_metric_term":
        equation = next(
            row
            for row in grammar["byte_metric_partition"][
                "ordered_metric_equation_records"
            ]
            if row["metric_position"] == 10
        )
        equation["ordered_term_records"][-1]["coefficient"] = 2
    elif mutation == "aggregate_transition_event":
        emission = next(
            event
            for program in grammar["ordered_case_program_records"]
            for event in program["ordered_event_emission_records"]
            if event["event_kind"] == "TRANSITION_ATTEMPT"
        )
        emission["aggregation_multiplicity_expression"] = {
            "opcode": "SOURCE_FIELD_U128",
            "field_name": "physical_transition_count",
        }
    elif mutation == "zero_transition_logical_count":
        emission = next(
            event
            for program in grammar["ordered_case_program_records"]
            for event in program["ordered_event_emission_records"]
            if event["event_kind"] == "TRANSITION_ATTEMPT"
        )
        emission["logical_unbatched_equivalent_count_expression"] = ZERO_EXPRESSION
    elif mutation == "count_m18_fragment":
        equation = next(
            row
            for row in grammar["byte_metric_partition"][
                "ordered_metric_equation_records"
            ]
            if row["metric_position"] == 18
        )
        equation["ordered_term_records"].append(
            {
                "event_kind": "STEP_COMMITMENT_EMIT",
                "subject_kind": "RECURRENCE_STEP_COMMITMENT_V2",
                "coefficient": 1,
            }
        )
    elif mutation == "duplicate_final_result_emission":
        program = next(
            row
            for row in grammar["ordered_case_program_records"]
            if row["program_name"] == "FINAL_RESULT"
        )
        duplicate = copy.deepcopy(program["ordered_event_emission_records"][0])
        duplicate["emission_position"] = (
            len(program["ordered_event_emission_records"]) + 1
        )
        program["ordered_event_emission_records"].append(duplicate)
    elif mutation == "release_early":
        grammar["live_set_program"]["release_order"] = (
            "RELEASE_BEFORE_PARENT_COMMITMENT"
        )
    elif mutation == "include_close_in_preimage":
        grammar["stream_finalization_program"]["close_event_in_preimage"] = True
    elif mutation == "drop_resize_negative_control":
        grammar["hand_oracle_contract"]["ordered_required_mutation_classes"].remove(
            "RESIZE_SUBJECT"
        )
    else:  # pragma: no cover - parametrization is a closed enum
        raise AssertionError(mutation)
    with pytest.raises(AssertionError):
        _validate_catalog_event_grammar(changed, require_complete_oracles=False)


@pytest.mark.parametrize("mutation", MUTATION_CLASSES)
def test_complete_hand_oracles_reject_every_frozen_mutation_class(
    mutation: str,
) -> None:
    catalog = _catalog()
    _validate_catalog_event_grammar(catalog)
    changed = copy.deepcopy(catalog)
    oracle = changed["logical_event_catalog"]["case_level_event_grammar"][
        "ordered_hand_oracle_records"
    ][0]
    tokens = oracle["ordered_logical_event_tokens"]
    if mutation == "OMIT_EVENT":
        tokens.pop(2)
    elif mutation == "DUPLICATE_EVENT":
        tokens.insert(3, copy.deepcopy(tokens[2]))
    elif mutation == "REORDER_EVENT":
        tokens[2], tokens[3] = tokens[3], tokens[2]
    elif mutation == "RESIZE_SUBJECT":
        tokens[2]["subject_canonical_octets"] += 1
    elif mutation == "CHANGE_SUBJECT_SHA256":
        tokens[2]["subject_sha256"] = "0" * 64
    elif mutation == "CHANGE_EVENT_ORDINAL":
        tokens[2]["event_ordinal"] += 1
    elif mutation == "CHANGE_AGGREGATION_MULTIPLICITY":
        descriptor = next(
            row for row in tokens if row["event_kind"] == "LOGICAL_DESCRIPTOR_VISIT"
        )
        descriptor["aggregation_multiplicity"] += 1
    elif mutation == "CHANGE_LOGICAL_UNBATCHED_EQUIVALENT_COUNT":
        transition = next(
            row for row in tokens if row["event_kind"] == "TRANSITION_ATTEMPT"
        )
        transition["logical_unbatched_equivalent_count"] += 1
    elif mutation == "EARLY_OR_LATE_RELEASE":
        oracle["ordered_live_set_snapshots"][0]["observed_value"] += 1
    elif mutation == "MOVE_BYTE_ACCOUNTING_TERM":
        oracle["ordered_expected_resource_measurements"][8]["measured_value"] += 1
    elif mutation == "COUNT_M18_FRAGMENT":
        oracle["ordered_expected_resource_measurements"][17]["measured_value"] += 1
    elif mutation == "DUPLICATE_FINAL_RESULT":
        final = next(row for row in tokens if row["event_kind"] == "FINAL_RESULT_EMIT")
        tokens.insert(-2, copy.deepcopy(final))
    elif mutation == "INCLUDE_EXCLUDED_CONTROL_EVENT_IN_PREIMAGE":
        oracle["event_stream_preimage_canonical_octets_hex"] += "00"
    elif mutation == "EVENT_AFTER_FINAL_HASH":
        tokens.append(copy.deepcopy(tokens[-1]))
    else:  # pragma: no cover - frozen mutation enum is exhaustive
        raise AssertionError(mutation)
    with pytest.raises(AssertionError):
        _validate_catalog_event_grammar(changed)
