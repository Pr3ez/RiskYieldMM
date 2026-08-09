#!/usr/bin/env python3
"""Validate the isolated Raw-V8 Step-2 External Schema V2 topology ledger.

This standard-library-only validator deliberately does not import production,
the inventory generator, or the separate Unicode/foundation component.  The
ledger is a topology and typed-path commitment, not the complete External
Schema Registry V2.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
from collections import deque
from pathlib import Path
from typing import Any, Final, NamedTuple

CANONICALIZATION_VERSION: Final = "riskyieldmm_canonical_json_v1"
TOPOLOGY_COMPONENT_STATUS: Final = "TOPOLOGY_ONLY_NOT_FULL_REGISTRY"
TOPOLOGY_LEDGER_VERSION: Final = (
    "riskyieldmm.raw_v8_step2_external_schema_v2.topology_ledger.v1"
)
TOPOLOGY_LEDGER_SHA256: Final = (
    "17b6355afcc23438efad97967180fb7e6292b7dd3d72d8b91a0320bfb9696778"
)
TOPOLOGY_LEDGER_MAXIMUM_OCTETS: Final = 1_048_576
TOPOLOGY_LEDGER_MAXIMUM_JSON_NESTING_DEPTH: Final = 16
TYPE_VERSION_TAG_PREFIX: Final = "RAW_V8_STEP2_EXTERNAL_SCHEMA_V2/"
ENVELOPE_PREFIX: Final = (
    "canonicalization_version",
    "measurement_schema_version",
    "record_domain",
)
EXCLUDED_PRODUCTION_TYPE_NAMES: Final = (
    "CapacityMeasurementClockSpanV1",
    "CapacityMeasurementTargetObservationContextV1",
    "CapacityMeasurementTargetObservationV1",
    "CapacityMeasurementTargetObservationRootV1",
    "_HistoricalCapacityMeasurementLocalShutdownResultEvidenceV1V49FV8",
)


class TopologyValidationError(ValueError):
    """Raised when the independent topology ledger is invalid."""


class RecordSpec(NamedTuple):
    """One independently enumerated concrete-record topology."""

    type_name: str
    type_role: str
    codec_byte_bound_relation: str
    codec_octet_limit: int
    payload_members: tuple[str, ...]
    described_record_domain: str | None = None
    identity_field: str | None = None
    identity_payload_member_order: tuple[str, ...] | None = None


class UnionSpec(NamedTuple):
    """One independently enumerated tagged-union topology."""

    type_name: str
    codec_octet_limit: int
    payload_binding_scope: str
    payload_owner_type_name: str | None
    payload_typed_member_path: tuple[str, ...]
    discriminators: tuple[
        tuple[str, str | None, tuple[str, ...]],
        ...,
    ]
    alternatives: tuple[
        tuple[str, tuple[tuple[str, str], ...], str],
        ...,
    ]


def _members(*chunks: str) -> tuple[str, ...]:
    return tuple(" ".join(chunks).split())


def _nested(
    type_name: str,
    relation: str,
    limit: int,
    *member_chunks: str,
) -> RecordSpec:
    return RecordSpec(
        type_name,
        "NESTED",
        relation,
        limit,
        _members(*member_chunks),
    )


def _standalone(
    type_name: str,
    relation: str,
    limit: int,
    domain: str,
    identity_field: str,
    *member_chunks: str,
    identity_payload_member_order: tuple[str, ...] | None = None,
) -> RecordSpec:
    payload_members = _members(*member_chunks)
    return RecordSpec(
        type_name,
        "STANDALONE",
        relation,
        limit,
        payload_members,
        domain,
        identity_field,
        (
            payload_members
            if identity_payload_member_order is None
            else identity_payload_member_order
        ),
    )


RECORD_SPECS: Final = (
    _nested(
        "CapacityMeasurementAckDeadlineExpirySpecV1",
        "LE",
        3_145_728,
        "workload_family expected_outbound_subscription_intent_id",
        "due_scenario expected_terminal_cause_code",
    ),
    _nested(
        "CapacityMeasurementAckDeadlineExpiryResultEvidenceV1",
        "LE",
        3_145_728,
        "expired due_decision_clock_evidence due_decision_clock_evidence_id",
        "ack_deadline_expired_event_id terminal_transition_event_id",
        "transport_session_termination_id",
    ),
    _standalone(
        "CapacityMeasurementDispatchWindowEvidenceV1",
        "LE",
        524_288,
        "RiskYieldMMA2MDispatchWindowEvidenceV4_9F_RawV8",
        "dispatch_window_evidence_id",
        "transport_session_id outbound_subscription_intent_id socket_lease_id",
        "monotonic_clock_domain_id dispatch_started_at dispatch_completed_at",
        "dispatch_started_monotonic_ns dispatch_completed_monotonic_ns",
    ),
    _standalone(
        "CapacityMeasurementDueDecisionClockEvidenceV1",
        "LE",
        524_288,
        "RiskYieldMMA2MDueDecisionClockEvidenceV4_9F_RawV8",
        "due_decision_clock_evidence_id",
        "transport_session_id outbound_subscription_intent_id",
        "dispatch_window_evidence dispatch_window_evidence_id",
        "clock_source_manifest_id monotonic_clock_domain_id wall_before_at",
        "sampled_at wall_after_at monotonic_before_ns monotonic_sampled_ns",
        "monotonic_after_ns uncertainty_milliseconds synchronized valid_until",
        "clock_resolution_ns source_observation_sha256 selectable_source_count",
        "chronyd_launch_id chronyd_runtime_observation_sha256",
        "committed_ack_deadline_at committed_ack_deadline_monotonic_ns",
        "due_scenario",
    ),
    _standalone(
        "CapacityMeasurementIngressLogicalOracleProfileV1",
        "LE",
        8_192,
        "RiskYieldMMA2MIngressLogicalOracleProfileV1V4_9F_RawV8",
        "logical_oracle_profile_id",
        "profile_version oracle_kind input_chunk_semantics",
        "requires_empty_fragmentation_baseline",
        "requires_empty_complete_unit_baseline maximum_input_chunks",
        "maximum_input_octets maximum_parser_units",
        "maximum_completed_application_messages maximum_logical_output_frames",
        "maximum_logical_output_payload_octets logical_output_frame_domain",
        "raw_ingress_batch_domain streamed_digest_algorithm",
        "parser_oracle_descriptor_requirement",
    ),
    _nested(
        "CapacityMeasurementIngressOperationSpecV2",
        "LE",
        3_145_728,
        "workload_family ordered_input_chunks_base64 input_chunk_count",
        "input_octet_count input_sha256 raw_ingress_batch_sha256",
        "timeout_seconds logical_oracle_profile_id expected_parser_unit_count",
        "expected_completed_application_message_count",
        "expected_logical_output_frame_count",
        "expected_logical_output_payload_octets",
        "expected_logical_output_frames_sha256",
    ),
    _nested(
        "CapacityMeasurementIngressResultEvidenceV2",
        "LE",
        3_145_728,
        "ingress_progress_evidence_id final_parser_cursor_id",
        "final_retained_tail_id final_retained_tail_octets",
        "final_retained_tail_sha256 sealed_pending_input_id",
        "ingress_oracle_baseline_id observed_consumed_new_input_octets",
        "observed_parser_unit_count",
        "observed_completed_application_message_count",
        "observed_logical_output_frame_count",
        "observed_logical_output_payload_octets",
        "observed_logical_output_frames_sha256",
    ),
    _nested(
        "CapacityMeasurementLocalShutdownSpecV2",
        "LE",
        3_145_728,
        "workload_family timeout_seconds expected_terminal_outcome",
        "expected_local_close_code expected_local_close_reason_sha256",
        "maximum_terminal_ingress_batches",
        "maximum_terminal_ingress_ciphertext_octets",
        "maximum_terminal_ingress_plaintext_octets",
        "maximum_terminal_socket_receive_calls maximum_terminal_tls_records",
        "maximum_terminal_tls_unwrap_iterations",
        "maximum_terminal_zero_progress_iterations",
        "maximum_terminal_ingress_parser_units",
        "maximum_terminal_ingress_automatic_outputs",
        "maximum_websocket_send_attempts maximum_tls_control_send_attempts",
        "maximum_peer_shutdown_polls",
    ),
    _nested(
        "CapacityMeasurementLocalShutdownResultEvidenceV2",
        "LE",
        3_145_728,
        "local_shutdown_started_event_id",
        "local_shutdown_deadline_evidence_event_id",
        "local_close_dispatch_completion_event_id",
        "ordered_terminal_ingress_read_attempt_event_ids",
        "ordered_terminal_ingress_read_result_event_ids",
        "ordered_terminal_raw_ingress_commit_ids",
        "ordered_terminal_raw_ingress_actor_event_ids",
        "ordered_terminal_parser_transition_event_ids",
        "websocket_close_received_transition_event_id shutdown_trace_step_count",
        "shutdown_trace_root_sha256 final_terminal_ingress_batch_count",
        "final_terminal_ingress_ciphertext_octets",
        "final_terminal_ingress_plaintext_octets",
        "final_terminal_socket_receive_call_count",
        "final_terminal_tls_record_count",
        "final_terminal_tls_unwrap_iteration_count",
        "final_terminal_zero_progress_iteration_count",
        "final_terminal_ingress_parser_unit_count",
        "final_terminal_ingress_automatic_output_count",
        "final_websocket_send_attempt_count",
        "final_tls_control_send_attempt_count final_peer_shutdown_poll_count",
        "final_terminal_tls_staging_state_id",
        "decisive_terminal_transition_event_id",
        "transport_session_termination_id terminal_outcome",
    ),
    _nested(
        "CapacityMeasurementLogicalOutputFrameV1",
        "LE",
        3_145_728,
        "opcode payload_base64",
    ),
    _standalone(
        "CapacityMeasurementOperationDeclarationV1",
        "LE",
        3_145_728,
        "RiskYieldMMA2MOperationDeclarationV4_9F_RawV8",
        "declaration_id",
        "campaign_manifest_id manifest_authority_id measurement_design_id",
        "workload_plan_id workload_id workload_sha256 sample_sequence",
        "operation_sequence trial_index repetition_index is_warmup stage",
        "timeout_policy_id operation_kind operation_spec operation_spec_id",
    ),
    _standalone(
        "CapacityMeasurementOperationSpec",
        "LE",
        2_097_152,
        "RiskYieldMMA2MOperationSpecV4_9F_RawV8",
        "operation_spec_id",
        "operation_kind spec_type spec",
    ),
    _standalone(
        "CapacityMeasurementOperationResultEvidence",
        "LT",
        524_288,
        "RiskYieldMMA2MOperationResultEvidenceV4_9F_RawV8",
        "result_evidence_id",
        "candidate_id attempt_id operation_kind result_type result",
    ),
    _nested(
        "CapacityMeasurementSubscriptionDispatchSpecV2",
        "LE",
        3_145_728,
        "workload_family idempotency_key transport_subscription_policy_id",
        "adapter_policy_id expected_topic expected_operation",
        "expected_logical_opcode expected_dispatch_disposition",
    ),
    _nested(
        "CapacityMeasurementSubscriptionDispatchResultEvidenceV2",
        "LE",
        3_145_728,
        "outbound_subscription_intent_id generated_request_id",
        "generated_request_command_sha256 generated_logical_opcode",
        "generated_logical_payload_sha256 generated_logical_payload_octets",
        "dispatch_window_evidence dispatch_window_evidence_id",
        "outbound_wire_prepared_event_id tls_ciphertext_prepared_event_id",
        "ordered_kernel_attempt_event_ids ordered_kernel_result_event_ids",
        "outbound_dispatch_completed_event_id submitted_ciphertext_octets",
        "local_dispatch_disposition",
    ),
    _standalone(
        "CheckpointSelectorEntryV1",
        "LE",
        2_048,
        "RiskYieldMMA2MCheckpointSelectorEntryV1V4_9F_RawV8",
        "checkpoint_selector_entry_id",
        "selector_position operation_kind checkpoint_marker_kind",
        "occurrence_index_within_kind",
    ),
    _standalone(
        "CheckpointSelectorV1",
        "LE",
        262_144,
        "RiskYieldMMA2MCheckpointSelectorV1V4_9F_RawV8",
        "checkpoint_selector_id",
        "operation_kind ordered_entries selector_length",
        "ordered_checkpoint_selector_entry_ids",
        identity_payload_member_order=(
            "operation_kind",
            "selector_length",
            "ordered_checkpoint_selector_entry_ids",
        ),
    ),
    _standalone(
        "MarkerContractV1",
        "LE",
        32_768,
        "RiskYieldMMA2MMarkerContractV1V4_9F_RawV8",
        "marker_contract_id",
        "contract_version ordered_marker_kinds",
        "ordered_full_checkpoint_marker_kinds",
        "ordered_checkpoint_operation_records",
        "forbidden_full_checkpoint_marker_kinds",
        "minimum_marker_ring_capacity maximum_marker_ring_capacity",
        "maximum_checkpoint_selector_length stable_checkpoint_requires_attempt",
    ),
    _nested(
        "TargetObservationClockSpanV2",
        "LE",
        512,
        "clock_domain span_status started_offset_nanoseconds",
        "completed_offset_nanoseconds unavailable_reason",
    ),
    _standalone(
        "TargetObservationContextV2",
        "LE",
        2_048,
        "RiskYieldMMA2MTargetObservationContextV2V4_9F_RawV8",
        "observation_context_id",
        "observation_role operation_kind instrumentation_mode candidate_id",
        "attempt_id target_field_registry_id marker_ordinal",
        "checkpoint_marker_kind full_checkpoint_selector_id",
        "checkpoint_selector_position checkpoint_selector_entry_id",
        "expected_checkpoint_marker_kind",
        "expected_occurrence_index_within_kind checkpoint_binding_status",
        "checkpoint_binding_unavailable_reason observer_clock_span",
        "boottime_clock_span loop_clock_span",
    ),
    _standalone(
        "TargetFieldObservationV1",
        "LE",
        4_096,
        "RiskYieldMMA2MTargetFieldObservationV4_9F_RawV8",
        "field_observation_id",
        "target_field_registry_id observation_context_id field_id availability",
        "value observation_method observation_attempt adapter_span_status",
        "observation_started_offset_nanoseconds",
        "observation_completed_offset_nanoseconds unavailable_reason censoring",
        "source_errno_number source_errno_name source_failure_phase",
        "source_error_class source_error_detail_sha256",
    ),
    _standalone(
        "TargetObservationV2",
        "LT",
        262_144,
        "RiskYieldMMA2MTargetObservationV2V4_9F_RawV8",
        "observation_id",
        "observation_context observation_context_id field_observations",
    ),
    _standalone(
        "TargetObservationRootV2",
        "LE",
        8_192,
        "RiskYieldMMA2MTargetObservationRootV2V4_9F_RawV8",
        "target_observation_root_sha256",
        "candidate_id attempt_id operation_kind instrumentation_mode",
        "target_field_registry_id full_checkpoint_selector_id",
        "observation_count ordered_observation_ids",
    ),
    _standalone(
        "TargetFieldRegistryV1",
        "LE",
        2_097_152,
        "RiskYieldMMA2MTargetFieldRegistryV4_9F_RawV8",
        "target_field_registry_id",
        "target_registry_profile status_reason_policy_definition",
        "ordered_vocabulary_definitions ordered_value_shape_definitions",
        "ordered_value_constraint_definitions",
        "ordered_cross_field_constraint_definitions field_count descriptors",
    ),
    _standalone(
        "OperationCounterSnapshotSchemaV1",
        "LE",
        8_192,
        "RiskYieldMMA2MOperationCounterSnapshotSchemaV4_9F_RawV8",
        "counter_schema_id",
        "counter_field_count ordered_counter_field_ids",
        "monotone_counter_field_ids",
    ),
    _nested(
        "OperationCounterSnapshotV1",
        "LE",
        2_048,
        "counter_schema_id availability_bitmap values",
    ),
    _standalone(
        "SourceErrorDetailV1",
        "LE",
        2_048,
        "RiskYieldMMA2MSourceErrorDetailV4_9F_RawV8",
        "source_error_detail_sha256",
        "field_id observation_method source_failure_phase",
        "source_errno_number source_errno_name source_error_class",
    ),
    _nested(
        "CapacityMeasurementObservationMethodRolePairV1",
        "LE",
        3_145_728,
        "observation_method allowed_roles",
    ),
    _nested(
        "CapacityMeasurementVocabularyDefinitionV1",
        "LE",
        3_145_728,
        "vocabulary_id members",
    ),
    _nested(
        "CapacityMeasurementValueShapeDefinitionV1",
        "LE",
        3_145_728,
        "value_shape_id container_kind minimum_items maximum_items ordered_keys",
    ),
    _nested(
        "CapacityMeasurementValueConstraintDefinitionV1",
        "LE",
        3_145_728,
        "value_constraint_id value_kind scalar_profile vocabulary_id",
        "integer_minimum integer_maximum text_minimum_utf8_bytes",
        "text_maximum_utf8_bytes text_ascii_pattern decimal_maximum",
        "collection_item_constraint_id external_authority_profile",
    ),
    _nested(
        "CapacityMeasurementAvailabilityStateRuleV1",
        "LE",
        3_145_728,
        "availability value_policy reason_policy censoring_policy",
        "attempt_policy adapter_span_policy",
    ),
    _nested(
        "CapacityMeasurementAttemptStateErrorFormsV1",
        "LE",
        3_145_728,
        "attempt_state permitted_error_forms permitted_failure_phases",
        "adapter_span_policy",
    ),
    _nested(
        "CapacityMeasurementStatusReasonRuleV1",
        "LE",
        3_145_728,
        "reason required_availability context_predicate",
        "attempt_state_error_forms",
    ),
    _nested(
        "CapacityMeasurementErrorFormDefinitionV1",
        "LE",
        3_145_728,
        "error_form errno_pair_policy error_class_policy error_digest_policy",
        "class_digest_pair_policy",
    ),
    _nested(
        "CapacityMeasurementStatusReasonPolicyDefinitionV1",
        "LE",
        3_145_728,
        "status_reason_policy_id availability_state_rules reason_rules",
        "error_form_definitions",
    ),
    _nested(
        "CapacityMeasurementCrossFieldConstraintDefinitionV1",
        "LE",
        3_145_728,
        "cross_field_constraint_id count_field_id sequence_field_id",
        "kind_field_id activation_condition maximum_items sequence_order",
        "cardinality_rule pairing_rule",
    ),
    _nested(
        "CapacityMeasurementTargetFieldDescriptorV1",
        "LE",
        3_145_728,
        "field_id layer value_kind unit value_constraint_id",
        "observation_method_role_pairs allowed_checkpoint_marker_kinds",
        "applicable_operation_kinds allowed_status_reasons",
        "status_reason_policy_id censoring_allowed",
        "later_threshold_action_if_unavailable value_shape_id value_shape_keys",
        "cross_field_constraint_ids",
    ),
    _nested(
        "CapacityMeasurementCheckpointOperationRecordV1",
        "LE",
        3_145_728,
        "checkpoint_marker_kind applicable_operation_kinds",
    ),
    _nested(
        "CapacityMeasurementUIntValueV1",
        "LE",
        3_072,
        "kind value",
    ),
    _nested(
        "CapacityMeasurementBoolValueV1",
        "LE",
        3_072,
        "kind value",
    ),
    _nested(
        "CapacityMeasurementTextValueV1",
        "LE",
        3_072,
        "kind value",
    ),
    _nested(
        "CapacityMeasurementOptionalUIntValueV1",
        "LE",
        3_072,
        "kind present value",
    ),
    _nested(
        "CapacityMeasurementOptionalTextValueV1",
        "LE",
        3_072,
        "kind present value",
    ),
    _nested(
        "CapacityMeasurementUIntListValueV1",
        "LE",
        3_072,
        "kind values",
    ),
    _nested(
        "CapacityMeasurementTextListValueV1",
        "LE",
        3_072,
        "kind values",
    ),
    _nested(
        "CapacityMeasurementFixedUIntMapEntryV1",
        "LE",
        3_145_728,
        "key value",
    ),
    _nested(
        "CapacityMeasurementFixedUIntMapValueV1",
        "LE",
        3_072,
        "kind ordered",
    ),
    _nested(
        "CapacityMeasurementDurationBoundValueV1",
        "LE",
        3_072,
        "kind relation lower_nanoseconds upper_nanoseconds",
    ),
)

REFERENCE_SPECS: Final = {
    (
        "CapacityMeasurementAckDeadlineExpiryResultEvidenceV1",
        "due_decision_clock_evidence",
    ): ("OBJECT_REF", "CapacityMeasurementDueDecisionClockEvidenceV1"),
    (
        "CapacityMeasurementDueDecisionClockEvidenceV1",
        "dispatch_window_evidence",
    ): ("OBJECT_REF", "CapacityMeasurementDispatchWindowEvidenceV1"),
    (
        "CapacityMeasurementOperationDeclarationV1",
        "operation_spec",
    ): ("OBJECT_REF", "CapacityMeasurementOperationSpec"),
    (
        "CapacityMeasurementOperationSpec",
        "spec",
    ): ("TAGGED_UNION_REF", "CapacityMeasurementOperationSpecBody"),
    (
        "CapacityMeasurementOperationResultEvidence",
        "result",
    ): ("TAGGED_UNION_REF", "CapacityMeasurementOperationResultBody"),
    (
        "CapacityMeasurementSubscriptionDispatchResultEvidenceV2",
        "dispatch_window_evidence",
    ): ("OBJECT_REF", "CapacityMeasurementDispatchWindowEvidenceV1"),
    (
        "CheckpointSelectorV1",
        "ordered_entries",
    ): ("ARRAY_OBJECT_REF", "CheckpointSelectorEntryV1"),
    (
        "MarkerContractV1",
        "ordered_checkpoint_operation_records",
    ): (
        "ARRAY_OBJECT_REF",
        "CapacityMeasurementCheckpointOperationRecordV1",
    ),
    (
        "TargetObservationContextV2",
        "observer_clock_span",
    ): ("OBJECT_REF", "TargetObservationClockSpanV2"),
    (
        "TargetObservationContextV2",
        "boottime_clock_span",
    ): ("OBJECT_REF", "TargetObservationClockSpanV2"),
    (
        "TargetObservationContextV2",
        "loop_clock_span",
    ): ("OBJECT_REF", "TargetObservationClockSpanV2"),
    (
        "TargetFieldObservationV1",
        "value",
    ): ("TAGGED_UNION_REF", "CapacityMeasurementTargetValue"),
    (
        "TargetObservationV2",
        "observation_context",
    ): ("OBJECT_REF", "TargetObservationContextV2"),
    (
        "TargetObservationV2",
        "field_observations",
    ): ("ARRAY_OBJECT_REF", "TargetFieldObservationV1"),
    (
        "TargetFieldRegistryV1",
        "status_reason_policy_definition",
    ): (
        "OBJECT_REF",
        "CapacityMeasurementStatusReasonPolicyDefinitionV1",
    ),
    (
        "TargetFieldRegistryV1",
        "ordered_vocabulary_definitions",
    ): ("ARRAY_OBJECT_REF", "CapacityMeasurementVocabularyDefinitionV1"),
    (
        "TargetFieldRegistryV1",
        "ordered_value_shape_definitions",
    ): ("ARRAY_OBJECT_REF", "CapacityMeasurementValueShapeDefinitionV1"),
    (
        "TargetFieldRegistryV1",
        "ordered_value_constraint_definitions",
    ): (
        "ARRAY_OBJECT_REF",
        "CapacityMeasurementValueConstraintDefinitionV1",
    ),
    (
        "TargetFieldRegistryV1",
        "ordered_cross_field_constraint_definitions",
    ): (
        "ARRAY_OBJECT_REF",
        "CapacityMeasurementCrossFieldConstraintDefinitionV1",
    ),
    (
        "TargetFieldRegistryV1",
        "descriptors",
    ): ("ARRAY_OBJECT_REF", "CapacityMeasurementTargetFieldDescriptorV1"),
    (
        "CapacityMeasurementStatusReasonRuleV1",
        "attempt_state_error_forms",
    ): ("ARRAY_OBJECT_REF", "CapacityMeasurementAttemptStateErrorFormsV1"),
    (
        "CapacityMeasurementStatusReasonPolicyDefinitionV1",
        "availability_state_rules",
    ): ("ARRAY_OBJECT_REF", "CapacityMeasurementAvailabilityStateRuleV1"),
    (
        "CapacityMeasurementStatusReasonPolicyDefinitionV1",
        "reason_rules",
    ): ("ARRAY_OBJECT_REF", "CapacityMeasurementStatusReasonRuleV1"),
    (
        "CapacityMeasurementStatusReasonPolicyDefinitionV1",
        "error_form_definitions",
    ): ("ARRAY_OBJECT_REF", "CapacityMeasurementErrorFormDefinitionV1"),
    (
        "CapacityMeasurementTargetFieldDescriptorV1",
        "observation_method_role_pairs",
    ): (
        "ARRAY_OBJECT_REF",
        "CapacityMeasurementObservationMethodRolePairV1",
    ),
    (
        "CapacityMeasurementFixedUIntMapValueV1",
        "ordered",
    ): ("ARRAY_OBJECT_REF", "CapacityMeasurementFixedUIntMapEntryV1"),
}

UNION_SPECS: Final = (
    UnionSpec(
        "CapacityMeasurementOperationSpecBody",
        3_145_728,
        "OWNER_MEMBER",
        "CapacityMeasurementOperationSpec",
        ("spec",),
        (
            (
                "OWNER_OBJECT",
                "CapacityMeasurementOperationSpec",
                ("operation_kind",),
            ),
            (
                "OWNER_OBJECT",
                "CapacityMeasurementOperationSpec",
                ("spec_type",),
            ),
        ),
        (
            (
                "ACK_DEADLINE_EXPIRY_SPEC_V1",
                (
                    ("operation_kind", "ACK_DEADLINE_EXPIRY"),
                    ("spec_type", "ACK_DEADLINE_EXPIRY_SPEC_V1"),
                ),
                "CapacityMeasurementAckDeadlineExpirySpecV1",
            ),
            (
                "INGRESS_OPERATION_SPEC_V2",
                (
                    ("operation_kind", "INGRESS"),
                    ("spec_type", "INGRESS_OPERATION_SPEC_V2"),
                ),
                "CapacityMeasurementIngressOperationSpecV2",
            ),
            (
                "LOCAL_SHUTDOWN_SPEC_V2",
                (
                    ("operation_kind", "LOCAL_SHUTDOWN"),
                    ("spec_type", "LOCAL_SHUTDOWN_SPEC_V2"),
                ),
                "CapacityMeasurementLocalShutdownSpecV2",
            ),
            (
                "SUBSCRIPTION_DISPATCH_SPEC_V2",
                (
                    ("operation_kind", "SUBSCRIPTION_DISPATCH"),
                    ("spec_type", "SUBSCRIPTION_DISPATCH_SPEC_V2"),
                ),
                "CapacityMeasurementSubscriptionDispatchSpecV2",
            ),
        ),
    ),
    UnionSpec(
        "CapacityMeasurementOperationResultBody",
        3_145_728,
        "OWNER_MEMBER",
        "CapacityMeasurementOperationResultEvidence",
        ("result",),
        (
            (
                "OWNER_OBJECT",
                "CapacityMeasurementOperationResultEvidence",
                ("operation_kind",),
            ),
            (
                "OWNER_OBJECT",
                "CapacityMeasurementOperationResultEvidence",
                ("result_type",),
            ),
        ),
        (
            (
                "ACK_DEADLINE_EXPIRY_RESULT_EVIDENCE_V1",
                (
                    ("operation_kind", "ACK_DEADLINE_EXPIRY"),
                    (
                        "result_type",
                        "ACK_DEADLINE_EXPIRY_RESULT_EVIDENCE_V1",
                    ),
                ),
                "CapacityMeasurementAckDeadlineExpiryResultEvidenceV1",
            ),
            (
                "INGRESS_RESULT_EVIDENCE_V2",
                (
                    ("operation_kind", "INGRESS"),
                    ("result_type", "INGRESS_RESULT_EVIDENCE_V2"),
                ),
                "CapacityMeasurementIngressResultEvidenceV2",
            ),
            (
                "LOCAL_SHUTDOWN_RESULT_EVIDENCE_V2",
                (
                    ("operation_kind", "LOCAL_SHUTDOWN"),
                    ("result_type", "LOCAL_SHUTDOWN_RESULT_EVIDENCE_V2"),
                ),
                "CapacityMeasurementLocalShutdownResultEvidenceV2",
            ),
            (
                "SUBSCRIPTION_DISPATCH_RESULT_EVIDENCE_V2",
                (
                    ("operation_kind", "SUBSCRIPTION_DISPATCH"),
                    (
                        "result_type",
                        "SUBSCRIPTION_DISPATCH_RESULT_EVIDENCE_V2",
                    ),
                ),
                "CapacityMeasurementSubscriptionDispatchResultEvidenceV2",
            ),
        ),
    ),
    UnionSpec(
        "CapacityMeasurementTargetValue",
        3_072,
        "SELF_VALUE",
        None,
        (),
        (("SELECTED_VALUE", None, ("kind",)),),
        (
            (
                "BOOL",
                (("kind", "BOOL"),),
                "CapacityMeasurementBoolValueV1",
            ),
            (
                "DURATION_BOUND",
                (("kind", "DURATION_BOUND"),),
                "CapacityMeasurementDurationBoundValueV1",
            ),
            (
                "FIXED_UINT_MAP",
                (("kind", "FIXED_UINT_MAP"),),
                "CapacityMeasurementFixedUIntMapValueV1",
            ),
            (
                "OPTIONAL_TEXT",
                (("kind", "OPTIONAL_TEXT"),),
                "CapacityMeasurementOptionalTextValueV1",
            ),
            (
                "OPTIONAL_UINT",
                (("kind", "OPTIONAL_UINT"),),
                "CapacityMeasurementOptionalUIntValueV1",
            ),
            (
                "TEXT",
                (("kind", "TEXT"),),
                "CapacityMeasurementTextValueV1",
            ),
            (
                "TEXT_LIST",
                (("kind", "TEXT_LIST"),),
                "CapacityMeasurementTextListValueV1",
            ),
            (
                "UINT",
                (("kind", "UINT"),),
                "CapacityMeasurementUIntValueV1",
            ),
            (
                "UINT_LIST",
                (("kind", "UINT_LIST"),),
                "CapacityMeasurementUIntListValueV1",
            ),
        ),
    ),
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise TopologyValidationError(message)


def _canonical_pretty_bytes(value: Any) -> bytes:
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


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _record_descriptor(spec: RecordSpec) -> dict[str, Any]:
    if spec.type_role == "STANDALONE":
        assert spec.identity_field is not None
        assert spec.identity_payload_member_order is not None
        logical_members = (
            *ENVELOPE_PREFIX,
            *spec.payload_members,
            spec.identity_field,
        )
        payload_members = set(spec.identity_payload_member_order)
        roles = (
            *("ENVELOPE_PREFIX" for _ in ENVELOPE_PREFIX),
            *(
                (
                    "IDENTITY_PAYLOAD"
                    if member in payload_members
                    else "ENVELOPE_NON_IDENTITY"
                )
                for member in spec.payload_members
            ),
            "IDENTITY_FIELD",
        )
    else:
        logical_members = spec.payload_members
        roles = tuple("NESTED_PAYLOAD" for _ in logical_members)
    member_topology = [
        {
            "member_name": member_name,
            "member_position": position,
            "member_role": member_role,
        }
        for position, (member_name, member_role) in enumerate(
            zip(logical_members, roles, strict=True),
            start=1,
        )
    ]
    references = []
    for member in logical_members:
        reference = REFERENCE_SPECS.get((spec.type_name, member))
        if reference is not None:
            reference_kind, referenced_type_name = reference
            references.append(
                {
                    "member_name": member,
                    "reference_kind": reference_kind,
                    "referenced_type_name": referenced_type_name,
                    "typed_member_path": [member],
                }
            )
    return {
        "codec_bound_inclusive": spec.codec_byte_bound_relation == "LE",
        "codec_byte_bound_relation": spec.codec_byte_bound_relation,
        "codec_octet_limit": spec.codec_octet_limit,
        "described_record_domain": spec.described_record_domain,
        "identity_field": spec.identity_field,
        "identity_payload_member_order": (
            None
            if spec.identity_payload_member_order is None
            else list(spec.identity_payload_member_order)
        ),
        "member_topology": member_topology,
        "tagged_union_topology": None,
        "type_form": "RECORD",
        "type_name": spec.type_name,
        "type_role": spec.type_role,
        "type_version_tag": TYPE_VERSION_TAG_PREFIX + spec.type_name,
        "typed_member_references": references,
    }


def _union_descriptor(spec: UnionSpec) -> dict[str, Any]:
    union_topology = {
        "ordered_alternatives": [
            {
                "alternative_name": alternative_name,
                "alternative_position": position,
                "ordered_discriminator_literals": [
                    {
                        "member_name": member_name,
                        "text_value": text_value,
                    }
                    for member_name, text_value in discriminator_literals
                ],
                "referenced_type_name": referenced_type_name,
            }
            for position, (
                alternative_name,
                discriminator_literals,
                referenced_type_name,
            ) in enumerate(spec.alternatives, start=1)
        ],
        "ordered_discriminator_topology": [
            {
                "discriminator_owner_type_name": owner_type_name,
                "discriminator_position": position,
                "discriminator_scope": scope,
                "discriminator_typed_member_path": list(typed_path),
            }
            for position, (
                scope,
                owner_type_name,
                typed_path,
            ) in enumerate(spec.discriminators, start=1)
        ],
        "payload_binding_scope": spec.payload_binding_scope,
        "payload_owner_type_name": spec.payload_owner_type_name,
        "payload_typed_member_path": list(spec.payload_typed_member_path),
    }
    return {
        "codec_bound_inclusive": True,
        "codec_byte_bound_relation": "LE",
        "codec_octet_limit": spec.codec_octet_limit,
        "described_record_domain": None,
        "identity_field": None,
        "identity_payload_member_order": None,
        "member_topology": None,
        "tagged_union_topology": union_topology,
        "type_form": "TAGGED_UNION",
        "type_name": spec.type_name,
        "type_role": "NESTED",
        "type_version_tag": TYPE_VERSION_TAG_PREFIX + spec.type_name,
        "typed_member_references": None,
    }


def _derive_path_ledger(
    type_descriptors: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    record_member_paths: list[dict[str, Any]] = []
    typed_reference_paths: list[dict[str, Any]] = []
    union_binding_paths: list[dict[str, Any]] = []
    for descriptor in type_descriptors:
        if descriptor["type_form"] == "RECORD":
            for member in descriptor["member_topology"]:
                record_member_paths.append(
                    {
                        "member_name": member["member_name"],
                        "member_position": member["member_position"],
                        "member_role": member["member_role"],
                        "path_position": len(record_member_paths) + 1,
                        "source_type_name": descriptor["type_name"],
                        "typed_member_path": [member["member_name"]],
                    }
                )
            for reference in descriptor["typed_member_references"]:
                typed_reference_paths.append(
                    {
                        "path_position": len(typed_reference_paths) + 1,
                        "reference_kind": reference["reference_kind"],
                        "referenced_type_name": reference["referenced_type_name"],
                        "source_type_name": descriptor["type_name"],
                        "typed_member_path": reference["typed_member_path"],
                    }
                )
            continue
        topology = descriptor["tagged_union_topology"]
        union_binding_paths.append(
            {
                "binding_kind": "PAYLOAD",
                "binding_position": 1,
                "binding_scope": topology["payload_binding_scope"],
                "owner_type_name": topology["payload_owner_type_name"],
                "path_position": len(union_binding_paths) + 1,
                "typed_member_path": topology["payload_typed_member_path"],
                "union_type_name": descriptor["type_name"],
            }
        )
        for discriminator in topology["ordered_discriminator_topology"]:
            union_binding_paths.append(
                {
                    "binding_kind": "DISCRIMINATOR",
                    "binding_position": discriminator["discriminator_position"],
                    "binding_scope": discriminator["discriminator_scope"],
                    "owner_type_name": discriminator["discriminator_owner_type_name"],
                    "path_position": len(union_binding_paths) + 1,
                    "typed_member_path": discriminator[
                        "discriminator_typed_member_path"
                    ],
                    "union_type_name": descriptor["type_name"],
                }
            )
    return {
        "record_member_paths": record_member_paths,
        "typed_reference_paths": typed_reference_paths,
        "union_binding_paths": union_binding_paths,
    }


def _expected_ledger() -> dict[str, Any]:
    type_descriptors = [
        *(_record_descriptor(spec) for spec in RECORD_SPECS),
        *(_union_descriptor(spec) for spec in UNION_SPECS),
    ]
    path_ledger = _derive_path_ledger(type_descriptors)
    return {
        "canonicalization_version": CANONICALIZATION_VERSION,
        "component_status": TOPOLOGY_COMPONENT_STATUS,
        "concrete_record_count": len(RECORD_SPECS),
        "excluded_production_type_names": list(EXCLUDED_PRODUCTION_TYPE_NAMES),
        "nested_type_count": sum(
            descriptor["type_role"] == "NESTED" for descriptor in type_descriptors
        ),
        "path_ledger": path_ledger,
        "record_member_path_count": len(path_ledger["record_member_paths"]),
        "standalone_record_count": sum(
            descriptor["type_role"] == "STANDALONE" for descriptor in type_descriptors
        ),
        "tagged_union_count": len(UNION_SPECS),
        "topology_ledger_version": TOPOLOGY_LEDGER_VERSION,
        "total_type_count": len(type_descriptors),
        "type_descriptors": type_descriptors,
        "typed_reference_path_count": len(path_ledger["typed_reference_paths"]),
        "union_binding_path_count": len(path_ledger["union_binding_paths"]),
    }


def _resolve_record_path(
    descriptors_by_name: dict[str, dict[str, Any]],
    type_name: str,
    typed_path: list[str],
) -> dict[str, Any]:
    _require(
        type_name in descriptors_by_name,
        f"typed path owner is outside the exact catalog: {type_name}",
    )
    descriptor = descriptors_by_name[type_name]
    _require(
        descriptor["type_form"] == "RECORD",
        f"typed path owner is not a record: {type_name}",
    )
    _require(
        len(typed_path) == 1 and type(typed_path[0]) is str,
        f"topology typed path is not exactly one member: {type_name}",
    )
    matches = [
        member
        for member in descriptor["member_topology"]
        if member["member_name"] == typed_path[0]
    ]
    _require(
        len(matches) == 1,
        f"topology typed path does not resolve exactly once: {type_name}",
    )
    return matches[0]


def _validate_graph_and_bindings(
    type_descriptors: list[dict[str, Any]],
    excluded_names: list[str],
) -> int:
    descriptor_names = [descriptor["type_name"] for descriptor in type_descriptors]
    _require(
        len(descriptor_names) == len(set(descriptor_names)),
        "type descriptor names are not unique",
    )
    descriptors_by_name = {
        descriptor["type_name"]: descriptor for descriptor in type_descriptors
    }
    _require(
        set(excluded_names).isdisjoint(descriptors_by_name),
        "excluded production type is present in topology",
    )
    edges: dict[str, set[str]] = {name: set() for name in descriptors_by_name}
    for descriptor in type_descriptors:
        type_name = descriptor["type_name"]
        if descriptor["type_form"] == "RECORD":
            for reference in descriptor["typed_member_references"]:
                _resolve_record_path(
                    descriptors_by_name,
                    type_name,
                    reference["typed_member_path"],
                )
                target = reference["referenced_type_name"]
                _require(
                    target in descriptors_by_name,
                    f"typed reference target is outside the exact catalog: {target}",
                )
                _require(
                    target not in excluded_names,
                    f"typed reference reaches an excluded type: {target}",
                )
                edges[type_name].add(target)
            continue
        topology = descriptor["tagged_union_topology"]
        payload_scope = topology["payload_binding_scope"]
        payload_owner = topology["payload_owner_type_name"]
        payload_path = topology["payload_typed_member_path"]
        if payload_scope == "OWNER_MEMBER":
            _require(
                type(payload_owner) is str and bool(payload_path),
                f"owner-member payload binding is incomplete: {type_name}",
            )
            _resolve_record_path(
                descriptors_by_name,
                payload_owner,
                payload_path,
            )
            owner_descriptor = descriptors_by_name[payload_owner]
            matching_reference = [
                reference
                for reference in owner_descriptor["typed_member_references"]
                if reference["typed_member_path"] == payload_path
                and reference["reference_kind"] == "TAGGED_UNION_REF"
                and reference["referenced_type_name"] == type_name
            ]
            _require(
                len(matching_reference) == 1,
                f"union payload binding lacks its exact owner reference: {type_name}",
            )
        else:
            _require(
                payload_scope == "SELF_VALUE"
                and payload_owner is None
                and payload_path == [],
                f"self-value payload binding is malformed: {type_name}",
            )
        discriminators = topology["ordered_discriminator_topology"]
        for expected_position, discriminator in enumerate(
            discriminators,
            start=1,
        ):
            _require(
                discriminator["discriminator_position"] == expected_position,
                f"union discriminator positions are not contiguous: {type_name}",
            )
            scope = discriminator["discriminator_scope"]
            owner = discriminator["discriminator_owner_type_name"]
            typed_path = discriminator["discriminator_typed_member_path"]
            if scope == "OWNER_OBJECT":
                _require(
                    owner == payload_owner,
                    f"union discriminator owner differs from payload owner: {type_name}",
                )
                _resolve_record_path(descriptors_by_name, owner, typed_path)
            else:
                _require(
                    scope == "SELECTED_VALUE" and owner is None,
                    f"selected-value discriminator binding is malformed: {type_name}",
                )
                for alternative in topology["ordered_alternatives"]:
                    _resolve_record_path(
                        descriptors_by_name,
                        alternative["referenced_type_name"],
                        typed_path,
                    )
        seen_names: set[str] = set()
        seen_literal_tuples: set[tuple[str, ...]] = set()
        discriminator_member_names = [
            discriminator["discriminator_typed_member_path"][-1]
            for discriminator in discriminators
        ]
        for expected_position, alternative in enumerate(
            topology["ordered_alternatives"],
            start=1,
        ):
            _require(
                alternative["alternative_position"] == expected_position,
                f"union alternative positions are not contiguous: {type_name}",
            )
            alternative_name = alternative["alternative_name"]
            _require(
                alternative_name not in seen_names,
                f"union alternative name is duplicated: {type_name}",
            )
            seen_names.add(alternative_name)
            literals = alternative["ordered_discriminator_literals"]
            _require(
                [literal["member_name"] for literal in literals]
                == discriminator_member_names,
                f"union literal member order differs from discriminator order: {type_name}",
            )
            literal_tuple = tuple(literal["text_value"] for literal in literals)
            _require(
                literal_tuple not in seen_literal_tuples,
                f"union discriminator literal tuple is duplicated: {type_name}",
            )
            seen_literal_tuples.add(literal_tuple)
            target = alternative["referenced_type_name"]
            _require(
                target in descriptors_by_name
                and descriptors_by_name[target]["type_form"] == "RECORD",
                f"union alternative target is not an exact record: {target}",
            )
            _require(
                target not in excluded_names,
                f"union alternative reaches an excluded type: {target}",
            )
            edges[type_name].add(target)
    indegree = dict.fromkeys(edges, 0)
    for targets in edges.values():
        for target in targets:
            indegree[target] += 1
    queue = deque(sorted(name for name, degree in indegree.items() if degree == 0))
    emitted_order: list[str] = []
    while queue:
        name = queue.popleft()
        emitted_order.append(name)
        for target in sorted(edges[name]):
            indegree[target] -= 1
            if indegree[target] == 0:
                queue.append(target)
    _require(
        len(emitted_order) == len(type_descriptors),
        "the exact topology type graph contains a cycle",
    )

    depth_cache: dict[str, int] = {}
    for name in reversed(emitted_order):
        depth_cache[name] = 1 + max(
            (depth_cache[target] for target in edges[name]),
            default=0,
        )
    maximum_depth = max(depth_cache.values())
    _require(maximum_depth <= 16, "topology type graph exceeds depth 16")
    return maximum_depth


def _validate_descriptor_shapes(type_descriptors: list[dict[str, Any]]) -> None:
    _require(bool(type_descriptors), "type descriptor catalog is empty")
    for descriptor in type_descriptors:
        name = descriptor["type_name"]
        relation = descriptor["codec_byte_bound_relation"]
        _require(relation in {"LE", "LT"}, f"unknown codec relation: {name}")
        _require(
            type(descriptor["codec_octet_limit"]) is int
            and descriptor["codec_octet_limit"] >= 1,
            f"codec octet limit is not a positive integer: {name}",
        )
        _require(
            type(descriptor["codec_bound_inclusive"]) is bool
            and descriptor["codec_bound_inclusive"] == (relation == "LE"),
            f"codec inclusive flag differs from relation: {name}",
        )
        _require(
            descriptor["type_version_tag"] == TYPE_VERSION_TAG_PREFIX + name,
            f"type version tag differs from exact derivation: {name}",
        )
        if descriptor["type_form"] == "TAGGED_UNION":
            _require(
                descriptor["type_role"] == "NESTED"
                and descriptor["described_record_domain"] is None
                and descriptor["identity_field"] is None
                and descriptor["identity_payload_member_order"] is None
                and descriptor["member_topology"] is None
                and descriptor["typed_member_references"] is None
                and type(descriptor["tagged_union_topology"]) is dict,
                f"tagged-union descriptor has a record-only member: {name}",
            )
            continue
        members = descriptor["member_topology"]
        _require(
            type(members) is list and bool(members),
            f"record descriptor has no member topology: {name}",
        )
        _require(
            descriptor["tagged_union_topology"] is None
            and type(descriptor["typed_member_references"]) is list,
            f"record descriptor has union-only topology: {name}",
        )
        positions = [member["member_position"] for member in members]
        _require(
            positions == list(range(1, len(members) + 1)),
            f"record member positions are not contiguous: {name}",
        )
        member_names = [member["member_name"] for member in members]
        _require(
            len(member_names) == len(set(member_names)),
            f"record member name is duplicated: {name}",
        )
        if descriptor["type_role"] == "STANDALONE":
            _require(
                member_names[:3] == list(ENVELOPE_PREFIX)
                and [member["member_role"] for member in members[:3]]
                == ["ENVELOPE_PREFIX"] * 3,
                f"standalone envelope prefix is malformed: {name}",
            )
            identity_field = descriptor["identity_field"]
            _require(
                type(descriptor["described_record_domain"]) is str
                and type(identity_field) is str
                and member_names[-1] == identity_field
                and members[-1]["member_role"] == "IDENTITY_FIELD",
                f"standalone domain or identity topology is malformed: {name}",
            )
            middle = members[3:-1]
            _require(
                all(
                    member["member_role"]
                    in {"IDENTITY_PAYLOAD", "ENVELOPE_NON_IDENTITY"}
                    for member in middle
                ),
                f"standalone middle member role is invalid: {name}",
            )
            _require(
                descriptor["identity_payload_member_order"]
                == [
                    member["member_name"]
                    for member in middle
                    if member["member_role"] == "IDENTITY_PAYLOAD"
                ],
                f"standalone identity payload is not the role subsequence: {name}",
            )
        else:
            _require(
                descriptor["type_role"] == "NESTED"
                and descriptor["described_record_domain"] is None
                and descriptor["identity_field"] is None
                and descriptor["identity_payload_member_order"] is None
                and all(
                    member["member_role"] == "NESTED_PAYLOAD" for member in members
                ),
                f"nested record topology is malformed: {name}",
            )


def _reject_json_constant(value: str) -> Any:
    raise TopologyValidationError(f"topology ledger contains non-finite JSON: {value}")


def _reject_json_float(value: str) -> Any:
    raise TopologyValidationError(f"topology ledger contains a float: {value}")


def _strict_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise TopologyValidationError(
                f"topology ledger contains duplicate JSON key: {key}"
            )
        result[key] = value
    return result


def _validate_json_nesting(text: str) -> None:
    depth = 0
    in_string = False
    escaped = False
    for character in text:
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue
        if character == '"':
            in_string = True
        elif character in "[{":
            depth += 1
            _require(
                depth <= TOPOLOGY_LEDGER_MAXIMUM_JSON_NESTING_DEPTH,
                "topology ledger JSON nesting exceeds the reviewed bound",
            )
        elif character in "]}":
            depth -= 1
            _require(
                depth >= 0,
                "topology ledger JSON closes an unopened container",
            )
    _require(not in_string, "topology ledger contains an unterminated JSON string")
    _require(depth == 0, "topology ledger JSON has unclosed containers")


def _require_json_scalar_strings(value: Any) -> None:
    if type(value) is str:
        _require(
            not any(0xD800 <= ord(character) <= 0xDFFF for character in value),
            "topology ledger contains a non-scalar JSON string",
        )
    elif type(value) is list:
        for item in value:
            _require_json_scalar_strings(item)
    elif type(value) is dict:
        for key, item in value.items():
            _require_json_scalar_strings(key)
            _require_json_scalar_strings(item)


def _load_ledger(path: Path) -> tuple[dict[str, Any], bytes]:
    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise TopologyValidationError(f"cannot open topology ledger: {exc}") from exc
    try:
        metadata_before = os.fstat(descriptor)
        _require(
            stat.S_ISREG(metadata_before.st_mode),
            "topology ledger is not a direct regular file",
        )
        _require(metadata_before.st_size > 0, "topology ledger is empty")
        _require(
            metadata_before.st_size <= TOPOLOGY_LEDGER_MAXIMUM_OCTETS,
            "topology ledger exceeds the reviewed byte bound",
        )
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            raw = stream.read(TOPOLOGY_LEDGER_MAXIMUM_OCTETS + 1)
        metadata_after = os.fstat(descriptor)
        _require(
            (
                metadata_after.st_dev,
                metadata_after.st_ino,
                metadata_after.st_mode,
                metadata_after.st_size,
                metadata_after.st_mtime_ns,
                metadata_after.st_ctime_ns,
            )
            == (
                metadata_before.st_dev,
                metadata_before.st_ino,
                metadata_before.st_mode,
                metadata_before.st_size,
                metadata_before.st_mtime_ns,
                metadata_before.st_ctime_ns,
            ),
            "topology ledger changed while it was read",
        )
    finally:
        os.close(descriptor)
    _require(
        len(raw) <= TOPOLOGY_LEDGER_MAXIMUM_OCTETS,
        "topology ledger exceeds the reviewed byte bound",
    )
    _require(
        len(raw) == metadata_before.st_size,
        "topology ledger size changed or was short-read",
    )
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise TopologyValidationError("topology ledger is not strict UTF-8") from exc
    _validate_json_nesting(text)
    try:
        value = json.loads(
            text,
            object_pairs_hook=_strict_json_object,
            parse_constant=_reject_json_constant,
            parse_float=_reject_json_float,
        )
    except (json.JSONDecodeError, RecursionError, TopologyValidationError) as exc:
        raise TopologyValidationError(
            f"topology ledger is not valid JSON: {exc.msg}"
            if isinstance(exc, json.JSONDecodeError)
            else f"topology ledger is not valid JSON: {exc}"
        ) from exc
    _require(type(value) is dict, "topology ledger root is not an object")
    _require_json_scalar_strings(value)
    try:
        canonical = _canonical_pretty_bytes(value)
    except (RecursionError, UnicodeError, ValueError) as exc:
        raise TopologyValidationError(
            f"topology ledger cannot be canonicalized: {exc}"
        ) from exc
    _require(raw == canonical, "topology ledger bytes are not canonical pretty JSON")
    return value, raw


def validate_topology_ledger(path: Path) -> dict[str, Any]:
    """Validate one canonical topology ledger and return a compact report."""

    ledger, raw = _load_ledger(path)
    expected = _expected_ledger()
    _require(
        set(ledger) == set(expected),
        "topology ledger root has missing or extra members",
    )
    _require(
        ledger["component_status"] == TOPOLOGY_COMPONENT_STATUS,
        "topology-only status marker differs",
    )
    type_descriptors = ledger["type_descriptors"]
    _require(
        type(type_descriptors) is list,
        "type_descriptors is not an exact array",
    )
    _validate_descriptor_shapes(type_descriptors)
    derived_paths = _derive_path_ledger(type_descriptors)
    _require(
        ledger["path_ledger"] == derived_paths,
        "path ledger differs from its exact descriptor derivation",
    )
    _require(
        ledger["record_member_path_count"] == len(derived_paths["record_member_paths"])
        and ledger["typed_reference_path_count"]
        == len(derived_paths["typed_reference_paths"])
        and ledger["union_binding_path_count"]
        == len(derived_paths["union_binding_paths"]),
        "path ledger count differs from its exact derivation",
    )
    maximum_depth = _validate_graph_and_bindings(
        type_descriptors,
        ledger["excluded_production_type_names"],
    )
    _require(
        ledger == expected,
        "topology ledger differs from the independently enumerated authority",
    )
    digest = _sha256_bytes(raw)
    _require(
        digest == TOPOLOGY_LEDGER_SHA256,
        "topology ledger SHA-256 differs from the frozen digest",
    )
    return {
        "component_status": TOPOLOGY_COMPONENT_STATUS,
        "concrete_record_count": ledger["concrete_record_count"],
        "ledger_octets": len(raw),
        "ledger_path": str(path),
        "ledger_sha256": digest,
        "maximum_type_graph_depth": maximum_depth,
        "nested_type_count": ledger["nested_type_count"],
        "record_member_path_count": ledger["record_member_path_count"],
        "standalone_record_count": ledger["standalone_record_count"],
        "tagged_union_count": ledger["tagged_union_count"],
        "total_type_count": ledger["total_type_count"],
        "typed_reference_path_count": ledger["typed_reference_path_count"],
        "union_binding_path_count": ledger["union_binding_path_count"],
    }


def _write_expected_ledger(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_canonical_pretty_bytes(_expected_ledger()))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path)
    parser.add_argument(
        "--write-expected-ledger",
        type=Path,
        help="mechanically materialize the independently enumerated ledger",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        if arguments.write_expected_ledger is not None:
            _require(
                arguments.ledger is None,
                "--ledger and --write-expected-ledger are mutually exclusive",
            )
            _write_expected_ledger(arguments.write_expected_ledger)
            return 0
        _require(arguments.ledger is not None, "--ledger is required")
        report = validate_topology_ledger(arguments.ledger)
    except (
        AssertionError,
        AttributeError,
        IndexError,
        KeyError,
        OSError,
        TopologyValidationError,
        TypeError,
    ) as exc:
        print(
            f"Raw-V8 Step-2 external-schema V2 topology error: {exc}",
            file=sys.stderr,
        )
        return 1
    print(
        json.dumps(
            report,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
