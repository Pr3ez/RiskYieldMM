#!/usr/bin/env python3
"""Validate authorities and fail closed for rejected maximum protocol V1.

This checker is deliberately independent and Python-standard-library-only.  It
does not import ``riskyieldmm``, a maximum generator/solver, or another
validator.  Its reusable semantic primitives remain testable, but V1 cannot
enter a pilot: a verifier-owned pre-search lower bound exceeds its immutable
coordinate, proof-node, and proof-depth seed caps.  No successful subcheck validates any of
the 474 eventual maximum-witness rows or makes Step 2 GO.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from collections import Counter
from collections.abc import Callable, Mapping
from pathlib import Path
from types import MappingProxyType
from typing import Any, Final, NamedTuple

CANONICALIZATION_VERSION: Final = "riskyieldmm_canonical_json_v1"
MEASUREMENT_SCHEMA_VERSION: Final = "riskyieldmm_physical_transport_a2m_raw_v49f_v8"
PROTOCOL_VERSION: Final = (
    "riskyieldmm.raw_v8_step2_external_schema_v2.maximum_protocol.v1"
)
PILOT_VERSION: Final = (
    "riskyieldmm.raw_v8_step2_external_schema_v2.maximum_protocol_pilot.v1"
)
COMPONENT_STATUS: Final = "REJECTED_MAXIMUM_PROTOCOL_V1_PRESEARCH_CAP_CONTRADICTION"
FRONTIER_ENCODING_VERSION: Final = (
    "TAGGED_MATERIALIZED_OR_DIRECT_CHILD_ALIAS_FIXED_256_LENGTH_BITMAP_BLOCKS_V2"
)
TRANSIENT_RECURRENCE_CATALOG_VERSION: Final = (
    "riskyieldmm.raw_v8_step2_external_schema_v2."
    "maximum_transient_recurrence_catalog.v1"
)
TRANSIENT_RECURRENCE_KINDS: Final = frozenset(
    {
        "ASCII_DFA_DYNAMIC_PROGRAM_V1",
        "UNICODE_15_NFC_DYNAMIC_PROGRAM_V1",
        "ORDERED_RAW_STRING_PREFIX_FEASIBILITY_V1",
        "DERIVED_IDENTITY_PREFIX_FEASIBILITY_V1",
    }
)

PROTOCOL_RELATIVE_PATH: Final = (
    "docs/research/"
    "v4_9f_a2_raw_v8_step2_constructive_maximum_protocol_freeze_2026-08-01.md"
)
CORRECTION_RELATIVE_PATH: Final = (
    "docs/research/v4_9f_a2_raw_v8_step2_external_schema_v2_correction_2026-07-28.md"
)
INVENTORY_RELATIVE_PATH: Final = "tests/raw_v8_step2_inventory_v49f.json"
REGISTRY_RELATIVE_PATH: Final = (
    "scripts/tests/raw_v8_step2_external_schema_v2_structural_registry_v49f.json"
)
LITERAL_AUTHORITY_RELATIVE_PATH: Final = (
    "scripts/tests/raw_v8_step2_external_schema_v2_rule_literal_authority_v49f.json"
)
PILOT_RELATIVE_PATH: Final = (
    "scripts/tests/raw_v8_step2_external_schema_v2_maximum_protocol_pilot_v49f.json"
)
APPLICATION_WITNESS_RELATIVE_PATH: Final = (
    "scripts/tests/raw_v8_step2_external_schema_v2_application_witness_v49f.json"
)
MAX64_CONTEXT_AUTHORITY_RELATIVE_PATH: Final = (
    "scripts/tests/"
    "raw_v8_step2_external_schema_v2_application_witness_"
    "max64_full67_context_v49f.json"
)
ACCEPTANCE_AUTHORITY_RELATIVE_PATH: Final = (
    "scripts/tests/"
    "raw_v8_step2_external_schema_v2_maximum_protocol_acceptance_v49f.json"
)

# These pins retain the exact rejected V1 bytes as falsification authority.
# They do not authorize a pilot, maximum witness, final rebind, or acceptance.
PROTOCOL_OCTETS: Final[int | None] = 246_093
PROTOCOL_SHA256: Final[str | None] = (
    "b3b39b3cb15caa450d9974925db9b5f0b91dd5832a462d2a8687dc19a50c4409"
)
CORRECTION_OCTETS: Final = 217_135
CORRECTION_SHA256: Final = (
    "29ec141e53adeb1c0afd51f205f5b57eb784b8859b5ba40958299abd1b713b55"
)
INVENTORY_OCTETS: Final = 5_264_966
INVENTORY_RAW_SHA256: Final = (
    "f33c1019afa7f49a316aac1bfbef7498e240f391e4fee00dfd95fdcda658669f"
)
INVENTORY_SEMANTIC_ID: Final = (
    "128d07a45dc2300c140f333cc3a45e2497aaa4089684f6e44da048ab403bbf9d"
)
REGISTRY_OCTETS: Final = 1_469_663
REGISTRY_RAW_SHA256: Final = (
    "9160297ff316c5931737c92f8b359f0a1e2ec22f0aa996ef3b09cf830dc96bf3"
)
REGISTRY_ID: Final = "5dc95a3e99c5646e912b6a7e9c3970cf2489d560ea890b0a19d38af4c51c2140"
LITERAL_AUTHORITY_OCTETS: Final = 484_301
LITERAL_AUTHORITY_RAW_SHA256: Final = (
    "aba3461059367904734e2eb9ae404787b9aab5ed4c3fbcd292925a364926cce2"
)
LITERAL_AUTHORITY_SEMANTIC_ID: Final = (
    "5239e6ec09244d772c72c7883393da5707984408f7a7e21e1731948a82ea647e"
)
APPLICATION_WITNESS_RAW_SHA256: Final = (
    "d2f40badc85c58965a72e52fd98bfebbd4caf3335ec5a0415a89294cc3fb3415"
)
APPLICATION_WITNESS_OCTETS: Final = 697_208
MAX64_CONTEXT_AUTHORITY_OCTETS: Final = 16_121_125
MAX64_CONTEXT_AUTHORITY_RAW_SHA256: Final = (
    "afab90030ac96fa21157bdd3e696dd25798d7755be028c5cb8eaca103f73de97"
)
MAX64_CONTEXT_AUTHORITY_COMPACT_OCTETS: Final = 12_698_603
MAX64_CONTEXT_AUTHORITY_COMPACT_SHA256: Final = (
    "ab67d30d11d19670652b4c1a7aeb2d1483b97f6c4dde7bd673d9f25a3079059e"
)

MAXIMUM_AUTHORITY_OCTETS: Final = 16_777_216
MAXIMUM_PILOT_OCTETS: Final = 16_777_216
MAXIMUM_JSON_DEPTH: Final = 96
SAFE_INTEGER_MAXIMUM: Final = 9_007_199_254_740_991
UINT128_MAXIMUM: Final = 340_282_366_920_938_463_463_374_607_431_768_211_455
SHA256_HEX_LENGTH: Final = 64
UINT256_HEX_LENGTH: Final = 64

REGISTRY_DOMAIN: Final = "RiskYieldMMA2MStep2ExternalSchemaRegistryV2V4_9F_RawV8"
VALUE_SCHEMA_DOMAIN: Final = "RiskYieldMMA2MStep2ValueSchemaV2V4_9F_RawV8"
LITERAL_AUTHORITY_DOMAIN: Final = "RiskYieldMMA2MStep2RuleLiteralAuthorityV1V4_9F_RawV8"
PROFILE_DOMAIN: Final = (
    "RiskYieldMMA2MStep2ExternalSchemaV2MaximumConstraintScopeProfileV1V4_9F_RawV8"
)
CONSTRAINT_SCOPE_DOMAIN: Final = (
    "RiskYieldMMA2MStep2ExternalSchemaV2MaximumConstraintScopeV1V4_9F_RawV8"
)
PILOT_DOMAIN: Final = (
    "RiskYieldMMA2MStep2ExternalSchemaV2MaximumProtocolPilotV1V4_9F_RawV8"
)
PILOT_CASE_DOMAIN: Final = (
    "RiskYieldMMA2MStep2ExternalSchemaV2MaximumProtocolPilotCaseV1V4_9F_RawV8"
)
PILOT_OUTCOME_DOMAIN: Final = (
    "RiskYieldMMA2MStep2ExternalSchemaV2MaximumProtocolPilotOutcomeV1V4_9F_RawV8"
)
PROOF_NODE_DOMAIN: Final = (
    "RiskYieldMMA2MStep2ExternalSchemaV2MaximumProofNodeV1V4_9F_RawV8"
)
OBSERVABLE_DESCRIPTOR_DOMAIN: Final = (
    "RiskYieldMMA2MStep2ExternalSchemaV2MaximumObservableDescriptorV1V4_9F_RawV8"
)
STATE_SIGNATURE_DOMAIN: Final = (
    "RiskYieldMMA2MStep2ExternalSchemaV2MaximumStateSignatureV1V4_9F_RawV8"
)
STATE_CELL_DOMAIN: Final = (
    "RiskYieldMMA2MStep2ExternalSchemaV2MaximumStateCellV1V4_9F_RawV8"
)
DERIVED_STATE_CATALOG_DOMAIN: Final = (
    "RiskYieldMMA2MStep2ExternalSchemaV2MaximumDerivedStateCatalogV1V4_9F_RawV8"
)
TRANSIENT_RECURRENCE_CATALOG_DOMAIN: Final = (
    "RiskYieldMMA2MStep2ExternalSchemaV2MaximumTransientRecurrenceCatalogV1V4_9F_RawV8"
)
DERIVED_IDENTITY_MAPPING_CATALOG_DOMAIN: Final = "RiskYieldMMA2MStep2ExternalSchemaV2MaximumDerivedIdentityMappingCatalogV1V4_9F_RawV8"
FRONTIER_COMMITMENT_DOMAIN: Final = (
    "RiskYieldMMA2MStep2ExternalSchemaV2MaximumFrontierCommitmentV1V4_9F_RawV8"
)
CHOICE_COORDINATE_PLAN_DOMAIN: Final = (
    "RiskYieldMMA2MStep2ExternalSchemaV2MaximumChoiceCoordinatePlanV1V4_9F_RawV8"
)
CHOICE_COORDINATE_DOMAIN: Final = (
    "RiskYieldMMA2MStep2ExternalSchemaV2MaximumComponentChoiceCoordinateV1V4_9F_RawV8"
)
CERTIFICATE_DOMAIN: Final = (
    "RiskYieldMMA2MStep2ExternalSchemaV2MaximumUpperBoundCertificateV1V4_9F_RawV8"
)
PILOT_CONTEXT_MANIFEST_DOMAIN: Final = "RiskYieldMMA2MStep2ExternalSchemaV2MaximumProtocolPilotContextManifestV1V4_9F_RawV8"
MAXIMUM_CONTEXT_OBJECT_DOMAIN: Final = (
    "RiskYieldMMA2MStep2ExternalSchemaV2MaximumContextObjectV1V4_9F_RawV8"
)
BOUNDARY_CANDIDATE_WITNESS_DOMAIN: Final = "RiskYieldMMA2MStep2ExternalSchemaV2LocalShutdownBoundaryCandidateWitnessV1V4_9F_RawV8"
MAXIMUM_RECORD_REFERENCE_DOMAIN: Final = (
    "RiskYieldMMA2MStep2ExternalSchemaV2MaximumRecordReferenceV1V4_9F_RawV8"
)
LOCAL_SHUTDOWN_MINIMALITY_CERTIFICATE_DOMAIN: Final = (
    "RiskYieldMMA2MStep2ExternalSchemaV2LocalShutdownMinimalityCertificateV1V4_9F_RawV8"
)
LOCAL_SHUTDOWN_PROOF_SCOPE_DOMAIN: Final = (
    "RiskYieldMMA2MStep2ExternalSchemaV2LocalShutdownMaximumProofScopeV1V4_9F_RawV8"
)
LOCAL_SHUTDOWN_PROOF_CONTEXT_DOMAIN: Final = (
    "RiskYieldMMA2MStep2ExternalSchemaV2LocalShutdownMaximumProofContextV1V4_9F_RawV8"
)
LOCAL_SHUTDOWN_UNREPRESENTABLE_DOMAIN: Final = (
    "RiskYieldMMA2MStep2ExternalSchemaV2LocalShutdownUnrepresentableV1V4_9F_RawV8"
)
ACCEPTANCE_AUTHORITY_DOMAIN: Final = (
    "RiskYieldMMA2MStep2ExternalSchemaV2MaximumProtocolAcceptanceV1V4_9F_RawV8"
)

INVENTORY_ROOT_KEYS: Final = frozenset(
    {
        "schema_version",
        "normative_document_inputs",
        "invariants",
        "target_field_registry",
        "operation_counter_schema",
        "marker_contract",
        "checkpoint_selector_catalog",
        "ingress_logical_oracle_profile_catalog",
        "external_schema_registry_v2",
        "operation_contracts",
        "fixture_records",
        "inventory_sha256",
    }
)
REGISTRY_ROOT_KEYS: Final = frozenset(
    {
        "canonicalization_version",
        "measurement_schema_version",
        "record_domain",
        "external_schema_profile",
        "unicode_source_catalog",
        "identifier_profile_catalog",
        "ascii_dfa_catalog",
        "text_language_catalog",
        "value_schema_catalog",
        "external_type_descriptor_count",
        "ordered_external_type_descriptors",
        "cross_field_rule_descriptor_count",
        "ordered_cross_field_rule_descriptors",
        "fixed_position_resolver_profile_catalog",
        "rule_application_descriptor_count",
        "ordered_rule_application_descriptors",
        "schema_graph_node_count",
        "ordered_schema_graph_node_names",
        "external_schema_registry_id",
    }
)
REGISTRY_IDENTITY_PAYLOAD_MEMBERS: Final = (
    "external_schema_profile",
    "unicode_source_catalog",
    "identifier_profile_catalog",
    "ascii_dfa_catalog",
    "text_language_catalog",
    "value_schema_catalog",
    "external_type_descriptor_count",
    "ordered_external_type_descriptors",
    "cross_field_rule_descriptor_count",
    "ordered_cross_field_rule_descriptors",
    "fixed_position_resolver_profile_catalog",
    "rule_application_descriptor_count",
    "ordered_rule_application_descriptors",
    "schema_graph_node_count",
    "ordered_schema_graph_node_names",
)
VALUE_SCHEMA_KEYS: Final = frozenset(
    {
        "schema_kind",
        "nullable",
        "boolean_literal",
        "integer_minimum",
        "integer_maximum",
        "text_language_id",
        "array_minimum_items",
        "array_maximum_items",
        "array_item_value_schema_id",
        "referenced_type_name",
        "value_schema_id",
    }
)
LITERAL_AUTHORITY_KEYS: Final = frozenset(
    {
        "canonicalization_version",
        "component_status",
        "measurement_schema_version",
        "rule_literal_authority_version",
        "marker_contract",
        "operation_counter_schema",
        "target_field_registry",
        "selected_literal_canonical_sha256",
        "rule_literal_authority_sha256",
    }
)
PROFILE_KEYS: Final = frozenset(
    {
        "profile_position",
        "profile_kind",
        "constraint_scope",
        "measured_type_name",
        "operation_kind",
        "ordered_source_authority_pointers",
        "ordered_source_authority_ids",
        "selector_catalog_position",
        "selector_catalog_name",
        "checkpoint_selector_id",
        "checkpoint_selector_entry_id",
        "expected_checkpoint_marker_kind",
        "expected_occurrence_index_within_kind",
        "selector_position",
        "checkpoint_outcome",
        "checkpoint_binding_status",
        "checkpoint_binding_unavailable_reason",
        "checkpoint_field_unavailable_reason",
        "ordered_admissible_root_families",
        "application_schedule_formula",
        "maximum_constraint_scope_profile_id",
    }
)
ROOT_FAMILY_KEYS: Final = frozenset(
    {
        "root_family_kind",
        "ordered_instrumentation_mode_attempt_presence_pairs",
        "selector_catalog_position",
        "selector_catalog_name",
        "checkpoint_selector_id",
        "selector_length",
        "observation_count",
        "role_sequence_formula",
        "ordered_measured_observation_roles",
        "selector_present",
    }
)

EXPECTED_SELECTED_PROFILE_IDS: Final = {
    3: "92a80f3b2dc5d4b9a6284adfb6819823de7e2546d4141b2b12c5c7c9afff21f4",
    369: "505dac244288e6fb666919c99567f883c28ed573a898ce2a5dd680744dd57540",
    370: "b764c8c83c39681fe5de8c4064dd8dd25a97dd48c170f1206ce4e1904be74146",
    371: "323d26f06e1ac00198f8dfe9627b9d1759fcbe856ae4e2b68636c14e15785532",
    372: "46c0032e1f747c59b6e60e1bee4edf92c24d2894e9755c4c27d6362810066a47",
    373: "ab3d22d821ab9f68654e3f4c692db7021caeaab517cf0271078a38a3397b0cb1",
}
CHECKPOINT_OUTCOMES: Final = (
    "EXACT_MARKER",
    "ARTIFACT_BOUND_EXCEEDED",
    "OBSERVER_INTERNAL_ERROR",
    "SOURCE_CLOCK_UNAVAILABLE",
    "TARGET_BOUNDARY_NOT_REACHED",
)
SCOPE_OPERATION_KINDS: Final = (
    "ACK_DEADLINE_EXPIRY",
    "INGRESS",
    "LOCAL_SHUTDOWN",
    "SUBSCRIPTION_DISPATCH",
)
CHECKPOINT_OUTCOME_BINDINGS: Final = MappingProxyType(
    {
        "EXACT_MARKER": ("EXACT_MARKER", None, None),
        "ARTIFACT_BOUND_EXCEEDED": (
            "UNAVAILABLE_MARKER_OBSERVER_FAILURE",
            "ARTIFACT_BOUND_EXCEEDED",
            "CHECKPOINT_PLACEHOLDER_ARTIFACT_BOUND_EXCEEDED",
        ),
        "OBSERVER_INTERNAL_ERROR": (
            "UNAVAILABLE_MARKER_OBSERVER_FAILURE",
            "OBSERVER_INTERNAL_ERROR",
            "CHECKPOINT_PLACEHOLDER_OBSERVER_INTERNAL_ERROR",
        ),
        "SOURCE_CLOCK_UNAVAILABLE": (
            "UNAVAILABLE_MARKER_OBSERVER_FAILURE",
            "SOURCE_CLOCK_UNAVAILABLE",
            "CHECKPOINT_PLACEHOLDER_SOURCE_CLOCK_UNAVAILABLE",
        ),
        "TARGET_BOUNDARY_NOT_REACHED": (
            "UNAVAILABLE_TARGET_BOUNDARY_NOT_REACHED",
            "TARGET_BOUNDARY_NOT_REACHED",
            "CHECKPOINT_PLACEHOLDER_TARGET_BOUNDARY_NOT_REACHED",
        ),
    }
)
PILOT_CASE_NAMES: Final = (
    "SMALL_BOOL_SCALAR",
    "OWNER_LOCAL_SHUTDOWN_RESULT_UNION",
    "RAW_STRING_ARRAY_RECORD",
    "LOCAL_SHUTDOWN_FIXTURE",
    "MAX64_EXACT_MARKER_ROOT",
    "MAX64_PLACEHOLDER_ROOT",
)
LOCAL_SHUTDOWN_MUTABLE_LIMIT_MEMBERS: Final = (
    "maximum_terminal_ingress_automatic_outputs",
    "maximum_terminal_ingress_batches",
    "maximum_terminal_ingress_ciphertext_octets",
    "maximum_terminal_ingress_parser_units",
    "maximum_terminal_ingress_plaintext_octets",
    "maximum_terminal_socket_receive_calls",
    "maximum_terminal_tls_records",
    "maximum_terminal_tls_unwrap_iterations",
    "maximum_terminal_zero_progress_iterations",
    "maximum_tls_control_send_attempts",
    "maximum_websocket_send_attempts",
)
LOCAL_SHUTDOWN_LIMIT_DOMAINS: Final = (
    ("maximum_terminal_ingress_batches", 1, SAFE_INTEGER_MAXIMUM),
    ("maximum_terminal_ingress_ciphertext_octets", 1, SAFE_INTEGER_MAXIMUM),
    ("maximum_terminal_ingress_plaintext_octets", 1, SAFE_INTEGER_MAXIMUM),
    ("maximum_terminal_socket_receive_calls", 1, SAFE_INTEGER_MAXIMUM),
    ("maximum_terminal_tls_records", 1, SAFE_INTEGER_MAXIMUM),
    ("maximum_terminal_tls_unwrap_iterations", 1, SAFE_INTEGER_MAXIMUM),
    ("maximum_terminal_zero_progress_iterations", 1, SAFE_INTEGER_MAXIMUM),
    ("maximum_terminal_ingress_parser_units", 1, 4_096),
    ("maximum_terminal_ingress_automatic_outputs", 1, 4_096),
    ("maximum_websocket_send_attempts", 1, 1_048_832),
    ("maximum_tls_control_send_attempts", 1, 256),
    ("maximum_peer_shutdown_polls", 2, 2),
)
LOCAL_SHUTDOWN_LIMIT_DOMAIN_BY_NAME: Final = MappingProxyType(
    {
        member_name: (domain_position, integer_minimum, integer_maximum)
        for domain_position, (
            member_name,
            integer_minimum,
            integer_maximum,
        ) in enumerate(LOCAL_SHUTDOWN_LIMIT_DOMAINS, 1)
    }
)
LOCAL_SHUTDOWN_INTRINSIC_RULE_ID: Final = (
    "RULE/INTRINSIC/CapacityMeasurementLocalShutdownSpecV2/V1"
)
LOCAL_SHUTDOWN_INTRINSIC_RELATION_IDS: Final = (
    "maximum_terminal_ingress_plaintext_octets<=16384*maximum_terminal_ingress_batches",
    "2*maximum_terminal_ingress_parser_units<=maximum_terminal_ingress_plaintext_octets",
    "maximum_terminal_tls_records<=maximum_terminal_ingress_batches",
    "maximum_terminal_ingress_automatic_outputs<=maximum_terminal_ingress_parser_units",
    "maximum_websocket_send_attempts<=256*(1+maximum_terminal_ingress_automatic_outputs)",
)
LOCAL_SHUTDOWN_INTRINSIC_COMPARISON_NODES: Final = (
    (25, "LE", (4, 15)),
    (26, "LE", (18, 4)),
    (27, "LE", (8, 2)),
    (28, "LE", (10, 6)),
    (29, "LE", (12, 24)),
)
LOCAL_SHUTDOWN_BASELINE_SPEC_POINTER: Final = (
    "/fixture_records/operation_specs/LOCAL_SHUTDOWN"
)
LOCAL_SHUTDOWN_BASELINE_SPEC_TYPE_NAME: Final = "CapacityMeasurementOperationSpec"
LOCAL_SHUTDOWN_BASELINE_SPEC_VALUE_SCHEMA_ID: Final = (
    "4fae771b5c217c12346a142112f49360f7919f9fa6d4d321622471d158ac2edc"
)
LOCAL_SHUTDOWN_BASELINE_SPEC_CANONICAL_OCTETS: Final = 1_109
LOCAL_SHUTDOWN_BASELINE_SPEC_CANONICAL_SHA256: Final = (
    "292a5c5110b8c98910fae5ad48abb6e384bca17fc0f21c1ab2dde10c4fd026df"
)
LOCAL_SHUTDOWN_BASELINE_SPEC_EFFECTIVE_CEILING: Final = 2_097_152
LOCAL_SHUTDOWN_BASELINE_RESULT_POINTER: Final = (
    "/fixture_records/operation_results/LOCAL_SHUTDOWN"
)
LOCAL_SHUTDOWN_BASELINE_RESULT_TYPE_NAME: Final = (
    "CapacityMeasurementOperationResultEvidence"
)
LOCAL_SHUTDOWN_BASELINE_RESULT_IDENTITY: Final = (
    "237336c1d3867c7b38d3dcf4d9af455f4dc4675ae2dd1af6ba89b04d010be5db"
)
LOCAL_SHUTDOWN_BASELINE_RESULT_CANONICAL_OCTETS: Final = 2_504
LOCAL_SHUTDOWN_BASELINE_RESULT_CANONICAL_SHA256: Final = (
    "f8abb509fc87ec47dd8ec7a95c262c9731f20f2d261067e40af755a91773b1f6"
)
LOCAL_SHUTDOWN_OBJECTIVE_PREFIX_VERSION: Final = (
    "riskyieldmm.raw_v8_step2_external_schema_v2.local_shutdown_objective_prefix.v1"
)
LOCAL_SHUTDOWN_EQUIVALENCE_KEY_VERSION: Final = (
    "riskyieldmm.raw_v8_step2_external_schema_v2.local_shutdown_equivalence_key.v1"
)
LOCAL_SHUTDOWN_LIMIT_DOMAIN_POSITIONS: Final = MappingProxyType(
    {
        "maximum_terminal_ingress_batches": 1,
        "maximum_terminal_ingress_ciphertext_octets": 2,
        "maximum_terminal_ingress_plaintext_octets": 3,
        "maximum_terminal_socket_receive_calls": 4,
        "maximum_terminal_tls_records": 5,
        "maximum_terminal_tls_unwrap_iterations": 6,
        "maximum_terminal_zero_progress_iterations": 7,
        "maximum_terminal_ingress_parser_units": 8,
        "maximum_terminal_ingress_automatic_outputs": 9,
        "maximum_websocket_send_attempts": 10,
        "maximum_tls_control_send_attempts": 11,
    }
)
LOCAL_SHUTDOWN_BASELINE_MUTABLE_VALUES: Final = MappingProxyType(
    {
        "maximum_terminal_ingress_automatic_outputs": 1,
        "maximum_terminal_ingress_batches": 1,
        "maximum_terminal_ingress_ciphertext_octets": 16_645,
        "maximum_terminal_ingress_parser_units": 1,
        "maximum_terminal_ingress_plaintext_octets": 16_384,
        "maximum_terminal_socket_receive_calls": 4,
        "maximum_terminal_tls_records": 1,
        "maximum_terminal_tls_unwrap_iterations": 2,
        "maximum_terminal_zero_progress_iterations": 2,
        "maximum_tls_control_send_attempts": 2,
        "maximum_websocket_send_attempts": 2,
    }
)
LOCAL_SHUTDOWN_MUTABLE_DOMAIN_MAXIMUMS: Final = MappingProxyType(
    {
        "maximum_terminal_ingress_automatic_outputs": 4_096,
        "maximum_terminal_ingress_batches": SAFE_INTEGER_MAXIMUM,
        "maximum_terminal_ingress_ciphertext_octets": SAFE_INTEGER_MAXIMUM,
        "maximum_terminal_ingress_parser_units": 4_096,
        "maximum_terminal_ingress_plaintext_octets": SAFE_INTEGER_MAXIMUM,
        "maximum_terminal_socket_receive_calls": SAFE_INTEGER_MAXIMUM,
        "maximum_terminal_tls_records": SAFE_INTEGER_MAXIMUM,
        "maximum_terminal_tls_unwrap_iterations": SAFE_INTEGER_MAXIMUM,
        "maximum_terminal_zero_progress_iterations": SAFE_INTEGER_MAXIMUM,
        "maximum_tls_control_send_attempts": 256,
        "maximum_websocket_send_attempts": 1_048_832,
    }
)
WINNING_OBJECTIVE_KEYS: Final = frozenset(
    {
        "changed_limit_field_count",
        "sum_of_absolute_integer_deltas",
        "changed_member_names_in_lexical_order",
        "resulting_changed_values_in_that_same_order",
    }
)
MUTATED_LIMIT_MEMBER_KEYS: Final = frozenset(
    {
        "domain_position",
        "member_name",
        "baseline_value",
        "mutated_value",
        "absolute_delta",
    }
)
EXPECTED_REJECTION_COORDINATE_KEYS: Final = frozenset(
    {
        "record_type_name",
        "typed_member_path",
        "validation_layer",
        "codec_byte_bound_relation",
        "codec_octet_limit",
        "observed_canonical_byte_length",
        "failure_class",
    }
)
LOCAL_SHUTDOWN_MINIMALITY_CERTIFICATE_KEYS: Final = frozenset(
    {
        "certificate_version",
        "maximum_protocol_sha256",
        "baseline_operation_spec_id",
        "mutated_operation_spec_id",
        "mutable_limit_member_count",
        "ordered_mutable_limit_member_names",
        "winning_objective",
        "ordered_proof_nodes",
        "root_proof_node_position",
        "local_shutdown_minimality_certificate_id",
    }
)
LOCAL_SHUTDOWN_UNREPRESENTABLE_KEYS: Final = frozenset(
    {
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
        "local_shutdown_unrepresentable_id",
    }
)
LOCAL_SHUTDOWN_OPERATION_SPEC_KEYS: Final = frozenset(
    {
        "canonicalization_version",
        "measurement_schema_version",
        "record_domain",
        "operation_kind",
        "spec_type",
        "spec",
        "operation_spec_id",
    }
)
LOCAL_SHUTDOWN_SPEC_BODY_KEYS: Final = frozenset(
    {
        "workload_family",
        "timeout_seconds",
        "expected_terminal_outcome",
        "expected_local_close_code",
        "expected_local_close_reason_sha256",
        *(member_name for member_name, _, _ in LOCAL_SHUTDOWN_LIMIT_DOMAINS),
    }
)
LOCAL_SHUTDOWN_OPERATION_RESULT_KEYS: Final = frozenset(
    {
        "canonicalization_version",
        "measurement_schema_version",
        "record_domain",
        "candidate_id",
        "attempt_id",
        "operation_kind",
        "result_type",
        "result",
        "result_evidence_id",
    }
)
LOCAL_SHUTDOWN_RESULT_BODY_KEYS: Final = frozenset(
    {
        "local_shutdown_started_event_id",
        "local_shutdown_deadline_evidence_event_id",
        "local_close_dispatch_completion_event_id",
        "ordered_terminal_ingress_read_attempt_event_ids",
        "ordered_terminal_ingress_read_result_event_ids",
        "ordered_terminal_raw_ingress_commit_ids",
        "ordered_terminal_raw_ingress_actor_event_ids",
        "ordered_terminal_parser_transition_event_ids",
        "websocket_close_received_transition_event_id",
        "shutdown_trace_step_count",
        "shutdown_trace_root_sha256",
        "final_terminal_ingress_batch_count",
        "final_terminal_ingress_ciphertext_octets",
        "final_terminal_ingress_plaintext_octets",
        "final_terminal_socket_receive_call_count",
        "final_terminal_tls_record_count",
        "final_terminal_tls_unwrap_iteration_count",
        "final_terminal_zero_progress_iteration_count",
        "final_terminal_ingress_parser_unit_count",
        "final_terminal_ingress_automatic_output_count",
        "final_websocket_send_attempt_count",
        "final_tls_control_send_attempt_count",
        "final_peer_shutdown_poll_count",
        "final_terminal_tls_staging_state_id",
        "decisive_terminal_transition_event_id",
        "transport_session_termination_id",
        "terminal_outcome",
    }
)
LOCAL_SHUTDOWN_TERMINAL_OUTCOMES: Final = frozenset(
    {
        "CLEAN_ALL_LAYERS",
        "FATAL",
        "STORAGE_FAILURE",
        "TIMEOUT",
        "TRUNCATED",
        "UNKNOWN_SEND",
    }
)
LOCAL_SHUTDOWN_RESULT_ARRAY_MAXIMUM_ITEMS: Final = MappingProxyType(
    {
        "ordered_terminal_ingress_read_attempt_event_ids": 524_288,
        "ordered_terminal_ingress_read_result_event_ids": 524_288,
        "ordered_terminal_raw_ingress_commit_ids": 524_288,
        "ordered_terminal_raw_ingress_actor_event_ids": 524_288,
        "ordered_terminal_parser_transition_event_ids": 4_096,
    }
)
LOCAL_SHUTDOWN_RECURRENCE_STATE_KEYS: Final = frozenset(
    {
        "state_position",
        "processed_mutable_member_count",
        "ordered_processed_values",
        "ordered_changed_domain_positions",
        "sum_absolute_integer_deltas",
        "ordered_intrinsic_relation_states",
        "prospective_result_root_position",
        "state_status",
        "recurrence_state_id",
    }
)
LOCAL_SHUTDOWN_RECURRENCE_TRANSITION_KEYS: Final = frozenset(
    {
        "transition_position",
        "source_state_position",
        "breakpoint_position",
        "result_state_position",
        "transition_kind",
        "failed_relation_id",
        "recurrence_transition_id",
    }
)
LOCAL_SHUTDOWN_DOMINANCE_DELETION_KEYS: Final = frozenset(
    {
        "deletion_position",
        "deleted_state_position",
        "retained_state_position",
        "equivalence_state_key_sha256",
        "dominance_reason",
    }
)
LOCAL_SHUTDOWN_BREAKPOINT_KEYS: Final = frozenset(
    {
        "breakpoint_position",
        "source_state_position",
        "domain_position",
        "member_name",
        "breakpoint_kind",
        "candidate_value",
        "source_relation_id",
        "prospective_result_root_position",
    }
)
LOCAL_SHUTDOWN_INTERVAL_EXCLUSION_KEYS: Final = frozenset(
    {
        "interval_position",
        "source_state_position",
        "domain_position",
        "first_omitted_value",
        "last_omitted_value",
        "dominating_breakpoint_position",
        "prospective_result_root_position",
        "piecewise_signature_id",
    }
)
LOCAL_SHUTDOWN_BREAKPOINT_KINDS: Final = (
    "DOMAIN_MINIMUM",
    "DOMAIN_MAXIMUM",
    "BASELINE",
    "BASELINE_NEIGHBOR",
    "DECIMAL_WIDTH_BOUNDARY",
    "INTRINSIC_RELATION_BOUNDARY",
    "PROSPECTIVE_BYTE_BOUNDARY",
)
LOCAL_SHUTDOWN_RECURRENCE_STATE_DOMAIN: Final = (
    "RiskYieldMMA2MStep2ExternalSchemaV2LocalShutdownRecurrenceStateV1V4_9F_RawV8"
)
LOCAL_SHUTDOWN_RECURRENCE_TRANSITION_DOMAIN: Final = (
    "RiskYieldMMA2MStep2ExternalSchemaV2LocalShutdownRecurrenceTransitionV1V4_9F_RawV8"
)

PILOT_ROOT_KEYS: Final = frozenset(
    {
        "artifact_version",
        "canonicalization_version",
        "measurement_schema_version",
        "pilot_phase",
        "seed_protocol_sha256",
        "seed_protocol_raw_octet_count",
        "maximum_protocol_sha256",
        "seed_artifact_raw_octet_count",
        "seed_artifact_raw_sha256",
        "source_inventory_sha256",
        "external_schema_registry_id",
        "rule_literal_authority_sha256",
        "application_witness_raw_sha256",
        "max64_context_authority_raw_sha256",
        "ordered_pilot_case_records",
        "local_shutdown_minimality_pilot_record",
        "ordered_row_preflight_records",
        "local_shutdown_minimality_preflight_record",
        "metric_rounding_catalog",
        "derived_resource_ceiling_record",
        "phase_invariant_payload_sha256",
        "maximum_protocol_pilot_id",
    }
)
PILOT_CONTEXT_MANIFEST_KEYS: Final = frozenset(
    {
        "manifest_version",
        "canonicalization_version",
        "measurement_schema_version",
        "maximum_protocol_sha256",
        "source_inventory_sha256",
        "external_schema_registry_id",
        "rule_literal_authority_sha256",
        "application_witness_raw_sha256",
        "max64_context_authority_raw_sha256",
        "ordered_context_object_entries",
        "maximum_context_object_manifest_id",
    }
)
PILOT_CONTEXT_OBJECT_ENTRY_KEYS: Final = frozenset(
    {
        "context_object_position",
        "context_source_kind",
        "source_authority_sha256",
        "source_json_pointer",
        "derived_record_role",
        "derived_sequence_ordinal",
        "inline_record",
        "maximum_context_object_id",
        "record_type_name",
        "record_identity_field",
        "record_identity",
        "record_canonical_byte_length",
        "record_canonical_sha256",
    }
)
PILOT_SCOPE_WITNESS_CONTEXT_KEYS: Final = MappingProxyType(
    {
        "SELF_VALUE": frozenset({"context_kind"}),
        "OWNER_MEMBER": frozenset(
            {
                "context_kind",
                "owner_record_reference",
                "payload_typed_member_path",
            }
        ),
        "OUTER_RESULT_APPLICATION": frozenset(
            {
                "context_kind",
                "constraint_scope_profile_id",
                "operation_result_record_reference",
                "operation_spec_authority_reference",
                "ordered_application_invocations",
            }
        ),
        "ROOT_APPLICATION": frozenset(
            {
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
            }
        ),
    }
)
OUTER_RESULT_APPLICATION_NAME: Final = "APPLY/OPERATION_RESULT_SIGNED_SPEC_V1"
SELECTOR_MARKER_APPLICATION_NAME: Final = "APPLY/SELECTOR_MARKER_CONTRACT_V1"
OBSERVATION_AGGREGATE_APPLICATION_NAME: Final = (
    "APPLY/V2_OBSERVATION_AGGREGATE_REGISTRY_V1"
)
OBSERVATION_FIELDS_APPLICATION_NAME: Final = "APPLY/V2_OBSERVATION_FIELDS_REGISTRY_V1"
ROOT_OBSERVATION_MEMBERSHIP_APPLICATION_NAME: Final = (
    "APPLY/V2_ROOT_OBSERVATION_MEMBERSHIP_V1"
)
ROOT_SELECTOR_LIFECYCLE_APPLICATION_NAME: Final = "APPLY/V2_ROOT_SELECTOR_LIFECYCLE_V1"
PILOT_CASE_KEYS: Final = frozenset(
    {
        "case_position",
        "case_id",
        "case_binding",
        "ordered_outcome_subrecords",
        "pilot_context_manifest",
        "pilot_witness_record",
        "pilot_scope_witness_context",
        "ordered_component_choice_evidence",
        "pilot_upper_bound_certificate",
        "producer_resource_measurement",
        "pilot_case_id",
    }
)
CASE_BINDING_KEYS: Final = frozenset(
    {
        "type_name",
        "alternative_name",
        "constraint_scope",
        "constraint_scope_profile_id",
        "profile_position",
        "measurement_binding",
        "pilot_domain_kind",
    }
)
MEASUREMENT_BINDING_KEYS: Final = frozenset(
    {
        "binding_kind",
        "validation_root_type_name",
        "measured_value_typed_member_path",
        "sequence_binding_name",
        "sequence_ordinal",
    }
)
PILOT_OUTCOME_KEYS: Final = frozenset(
    {
        "outcome_position",
        "checkpoint_outcome",
        "profile_position",
        "constraint_scope_profile_id",
        "pilot_context_manifest",
        "pilot_witness_record",
        "pilot_scope_witness_context",
        "ordered_component_choice_evidence",
        "pilot_upper_bound_certificate",
        "producer_resource_measurement",
        "pilot_outcome_subrecord_id",
    }
)
PROOF_RESOURCE_KEYS: Final = frozenset(
    {
        "proof_node_count",
        "proof_edge_count",
        "maximum_proof_depth",
        "maximum_child_count",
        "state_signature_dimension_count",
        "maximum_state_signature_dimension_count",
        "state_catalog_entry_count",
        "state_catalog_canonicalized_octets",
        "peak_retained_state_catalog_octets",
        "frontier_state_entry_count",
        "frontier_bitmap_run_count",
        "frontier_expanded_point_count",
        "maximum_frontier_width",
        "peak_retained_frontier_octets",
        "frontier_transition_count",
        "frontier_canonicalized_octets",
        "hash_preimage_octets",
        "component_choice_coordinate_count",
        "certificate_canonical_octets",
    }
)
PROOF_RESOURCE_MAXIMUM_FIELDS: Final = frozenset(
    {
        "maximum_proof_depth",
        "maximum_child_count",
        "maximum_state_signature_dimension_count",
        "maximum_frontier_width",
        "peak_retained_state_catalog_octets",
        "peak_retained_frontier_octets",
    }
)
PROOF_RESOURCE_TOTAL_FIELDS: Final = PROOF_RESOURCE_KEYS - PROOF_RESOURCE_MAXIMUM_FIELDS
SEED_CAP_DERIVATION_PHASE: Final = "SEED_CAP_DERIVATION"
FINAL_PROTOCOL_REBIND_PHASE: Final = "FINAL_PROTOCOL_REBIND"
PRODUCTION_VALIDATION_PHASE: Final = "PRODUCTION_VALIDATION"
PROOF_RESOURCE_PHASES: Final = frozenset(
    {
        SEED_CAP_DERIVATION_PHASE,
        FINAL_PROTOCOL_REBIND_PHASE,
        PRODUCTION_VALIDATION_PHASE,
    }
)
SEMANTIC_RESOURCE_ACCOUNTING_INCOMPLETE: Final = (
    "SEMANTIC_RESOURCE_ACCOUNTING_INCOMPLETE"
)
CERTIFICATE_SEMANTIC_RESOURCE_ACCOUNTING_COMPLETE: Final = False
LEXICALLY_OBSERVABLE_PROOF_RESOURCE_FIELDS: Final = frozenset(
    {
        "proof_node_count",
        "proof_edge_count",
        "maximum_child_count",
        "state_signature_dimension_count",
        "maximum_state_signature_dimension_count",
        "state_catalog_entry_count",
        "frontier_state_entry_count",
        "frontier_bitmap_run_count",
        "component_choice_coordinate_count",
        "certificate_canonical_octets",
    }
)
CURRENTLY_METERED_LEXICAL_FIELDS: Final = LEXICALLY_OBSERVABLE_PROOF_RESOURCE_FIELDS - {
    "state_catalog_entry_count",
    "certificate_canonical_octets",
}
LEXICAL_ANY_CERTIFICATE_PROFILE: Final = "ANY_CERTIFICATE_PATH_V1"
LEXICAL_PILOT_CERTIFICATE_PROFILE: Final = "MAXIMUM_PROTOCOL_PILOT_PATHS_V1"
LEXICAL_CERTIFICATE_PROFILES: Final = frozenset(
    {LEXICAL_ANY_CERTIFICATE_PROFILE, LEXICAL_PILOT_CERTIFICATE_PROFILE}
)
PILOT_CERTIFICATE_ANCHORS: Final = frozenset(
    {
        (
            "ordered_pilot_case_records",
            "*",
            "pilot_upper_bound_certificate",
        ),
        (
            "ordered_pilot_case_records",
            "*",
            "ordered_outcome_subrecords",
            "*",
            "pilot_upper_bound_certificate",
        ),
        (
            "local_shutdown_minimality_pilot_record",
            "minimality_certificate",
        ),
    }
)
DERIVED_RESOURCE_LIMIT_FIELD: Final = "state_signature_dimension_count"
ACCEPTED_PROOF_RESOURCE_LIMIT_KEYS: Final = PROOF_RESOURCE_KEYS - {
    DERIVED_RESOURCE_LIMIT_FIELD
}
SEED_EXECUTION_SAFETY_LIMITS_V1: Final = MappingProxyType(
    {
        "proof_node_count": 65_536,
        "proof_edge_count": 1_048_576,
        "maximum_proof_depth": 65_536,
        "maximum_child_count": 65_535,
        "state_signature_dimension_count": 4_194_304,
        "maximum_state_signature_dimension_count": 64,
        "state_catalog_entry_count": 1_048_576,
        "state_catalog_canonicalized_octets": 16_773_120,
        "peak_retained_state_catalog_octets": 16_773_120,
        "frontier_state_entry_count": 1_048_576,
        "frontier_bitmap_run_count": 1_048_576,
        "frontier_expanded_point_count": 8_388_608,
        "maximum_frontier_width": 8_388_608,
        "peak_retained_frontier_octets": 16_773_120,
        "frontier_transition_count": 67_108_864,
        "frontier_canonicalized_octets": 536_870_912,
        "hash_preimage_octets": 536_870_912,
        "component_choice_coordinate_count": 65_536,
        "certificate_canonical_octets": 16_773_120,
    }
)
PRODUCER_RESOURCE_KEYS: Final = PROOF_RESOURCE_KEYS | frozenset(
    {
        "resolved_context_reference_count",
        "resolved_context_object_count",
        "deduplicated_context_reference_count",
        "resolved_context_object_octets",
        "maximum_context_object_octets",
        "observation_count",
        "application_invocation_count",
        "charged_cross_rule_evaluation_count",
        "direct_cross_expression_node_count",
        "row_pretty_octets",
        "choice_evidence_pretty_octets",
        "certificate_pretty_octets",
        "total_staged_raw_octets",
    }
)
DOMINANCE_KEYS: Final = frozenset(
    {
        "row_position",
        "row_kind",
        "type_name",
        "alternative_name",
        "constraint_scope_profile_id",
        "bound_source_kind",
        "ordered_bound_source_case_ids",
        "dimension_vector",
        "ordered_symbolic_bound_nodes",
        "ordered_metric_upper_bounds",
    }
)
LOCAL_SHUTDOWN_DOMINANCE_KEYS: Final = frozenset(
    {
        "counterexample_kind",
        "bound_source_kind",
        "ordered_bound_source_case_ids",
        "dimension_vector",
        "ordered_symbolic_bound_nodes",
        "ordered_metric_upper_bounds",
    }
)
DIMENSION_VECTOR_KEYS: Final = frozenset(
    {
        "reachable_type_count",
        "reachable_value_schema_count",
        "reachable_intrinsic_rule_count",
        "reachable_intrinsic_expression_node_count",
        "member_occurrence_count",
        "nullable_occurrence_count",
        "union_alternative_count",
        "maximum_array_cardinality",
        "maximum_text_canonical_octets",
        "context_record_reference_count",
        "observation_count",
        "application_invocation_count",
        "charged_cross_rule_evaluation_count",
        "direct_cross_expression_node_count",
        "owner_codec_octet_limit",
        "measured_codec_octet_limit",
    }
)
METRIC_BOUND_KEYS: Final = frozenset(
    {
        "metric_position",
        "metric_name",
        "derived_upper_bound",
        "bound_formula_id",
        "symbolic_bound_root_position",
        "rounded_ceiling",
        "ceiling_slack",
    }
)
ROUNDING_KEYS: Final = frozenset(
    {
        "metric_position",
        "metric_name",
        "rounding_unit",
        "measured_pilot_maximum",
        "rounded_ceiling",
        "ceiling_slack",
    }
)
METRIC_NAMES: Final = (
    "PROOF_NODE_COUNT_PER_CERTIFICATE",
    "PROOF_EDGE_COUNT_PER_CERTIFICATE",
    "MAXIMUM_PROOF_DEPTH_PER_CERTIFICATE",
    "MAXIMUM_CHILD_COUNT_PER_NODE",
    "MAXIMUM_STATE_SIGNATURE_DIMENSION_COUNT_PER_NODE",
    "STATE_CATALOG_ENTRY_COUNT_PER_CERTIFICATE",
    "STATE_CATALOG_CANONICALIZED_OCTETS_PER_CERTIFICATE",
    "PEAK_RETAINED_STATE_CATALOG_OCTETS_PER_CERTIFICATE",
    "FRONTIER_STATE_ENTRY_COUNT_PER_CERTIFICATE",
    "FRONTIER_BITMAP_RUN_COUNT_PER_CERTIFICATE",
    "EXPANDED_FRONTIER_POINT_COUNT_PER_CERTIFICATE",
    "MAXIMUM_LIVE_FRONTIER_WIDTH",
    "PEAK_RETAINED_FRONTIER_OCTETS_PER_CERTIFICATE",
    "FRONTIER_TRANSITION_COUNT_PER_CERTIFICATE",
    "FRONTIER_CANONICALIZED_OCTETS_PER_CERTIFICATE",
    "HASH_PREIMAGE_OCTETS_PER_CERTIFICATE",
    "COMPONENT_CHOICE_COORDINATE_COUNT_PER_ROW",
    "CERTIFICATE_CANONICAL_OCTETS",
    "MAXIMUM_ROW_RAW_OCTETS",
    "AGGREGATE_CONTEXT_OBJECT_COMPACT_OCTETS",
    "AGGREGATE_ROW_RAW_OCTETS",
    "AGGREGATE_COMPLETE_ARTIFACT_RAW_OCTETS",
)
METRIC_ROUNDING_UNITS: Final = (
    1,
    1,
    1,
    1,
    1,
    1_024,
    4_096,
    4_096,
    1_024,
    1_024,
    1_024,
    1_024,
    4_096,
    1_024,
    4_096,
    4_096,
    1,
    4_096,
    4_096,
    1_048_576,
    1_048_576,
    1_048_576,
)
CAP_RECORD_KEYS: Final = frozenset(name.lower() for name in METRIC_NAMES)
BOUND_FORMULA_IDS: Final = frozenset(
    {
        "PILOT_COMPONENTWISE_MAX_V1",
        "SCHEMA_GRAPH_LOOP_PRODUCT_V1",
        "NO_DEDUP_CONTEXT_SUM_V1",
        "FIXED_474_ROW_SUM_V1",
        "EXACT_MANIFEST_PAGE_OVERHEAD_V1",
    }
)
SYMBOLIC_BOUND_NODE_KEYS: Final = frozenset(
    {
        "bound_node_position",
        "bound_operator",
        "literal_value",
        "dimension_name",
        "ordered_operand_positions",
        "computed_value",
    }
)

PATH_STEP_KEYS: Final = frozenset(
    {
        "step_position",
        "step_kind",
        "member_name",
        "member_position",
        "array_ordinal",
        "sequence_name",
        "union_alternative_position",
        "nullable_branch",
    }
)
PROOF_SUBJECT_LOCATOR_KEYS: Final = frozenset(
    {
        "locator_kind",
        "record_reference_id",
        "root_type_name",
        "root_value_schema_id",
        "ordered_path_steps",
        "transient_state_key",
        "transient_source_child_position",
        "transient_source_child_proof_node_id",
    }
)
RETAINED_VALUE_LOCATOR_KEYS: Final = frozenset(
    {
        "retained_source_kind",
        "record_reference_id",
        "root_type_name",
        "scope_context_member_name",
        "ordered_path_steps",
        "projection_kind",
    }
)
MAXIMUM_RECORD_REFERENCE_KEYS: Final = MappingProxyType(
    {
        "WITNESS_RECORD": frozenset(
            {
                "reference_kind",
                "record_type_name",
                "record_identity_field",
                "record_identity",
                "record_canonical_byte_length",
                "record_canonical_sha256",
                "maximum_record_reference_id",
            }
        ),
        "CONTEXT_OBJECT": frozenset(
            {
                "reference_kind",
                "maximum_context_object_id",
                "record_type_name",
                "record_identity_field",
                "record_identity",
                "record_canonical_byte_length",
                "record_canonical_sha256",
                "maximum_record_reference_id",
            }
        ),
        "V3_INVENTORY_POINTER": frozenset(
            {
                "reference_kind",
                "source_inventory_sha256",
                "inventory_json_pointer",
                "record_type_name",
                "record_identity_field",
                "record_identity",
                "record_canonical_byte_length",
                "record_canonical_sha256",
                "maximum_record_reference_id",
            }
        ),
    }
)
STATE_DIMENSION_KEYS: Final = frozenset(
    {
        "dimension_position",
        "dimension_kind",
        "subject_locator",
        "value_schema_id",
        "comparison_semantics",
        "ordered_activation_guard_clauses",
        "observable_descriptor_id",
    }
)
PRIMITIVE_ATOM_KEYS: Final = frozenset(
    {
        "atom_kind",
        "boolean_value",
        "integer_value",
        "text_value",
        "position_value",
        "canonical_bytes_hex_value",
    }
)
STATE_CELL_KEYS: Final = frozenset(
    {
        "cell_kind",
        "exact_atom",
        "integer_interval",
        "catalog_id",
        "catalog_position",
        "state_cell_id",
    }
)
DERIVED_STATE_CATALOG_KEYS: Final = frozenset(
    {
        "catalog_version",
        "catalog_kind",
        "defining_subject_locator",
        "defining_value_schema_id",
        "ordered_observable_descriptor_ids",
        "ordered_catalog_entries",
    }
)
DERIVED_STATE_CATALOG_ENTRY_KEYS: Final = frozenset(
    {
        "catalog_position",
        "ordered_partition_atoms",
        "ordered_partition_state_cells",
        "canonical_representative_atom",
        "ordered_attainable_length_bitmap_runs",
    }
)
TRANSIENT_RECURRENCE_CATALOG_KEYS: Final = frozenset(
    {
        "catalog_version",
        "recurrence_kind",
        "defining_subject_locator",
        "recurrence_parameters",
        "ordered_scalar_prefix_records",
        "ordered_primitive_prefix_records",
        "ordered_lex_interval_records",
        "ordered_state_records",
        "recurrence_catalog_id",
    }
)
TRANSIENT_SCALAR_PREFIX_RECORD_KEYS: Final = frozenset(
    {
        "prefix_position",
        "parent_prefix_position",
        "appended_scalar_value",
        "appended_scalar_repeat_count",
        "scalar_count",
        "json_value_octets",
    }
)
TRANSIENT_PRIMITIVE_PREFIX_RECORD_KEYS: Final = frozenset(
    {
        "prefix_position",
        "parent_prefix_position",
        "appended_choice_coordinate_plan_id",
        "appended_atom",
        "active_atom_count",
    }
)
TRANSIENT_RAW_LEX_INTERVAL_RECORD_KEYS: Final = frozenset(
    {"interval_position", "ordered_interval_blocks"}
)
TRANSIENT_RAW_LEX_INTERVAL_BLOCK_KEYS: Final = frozenset(
    {
        "block_position",
        "block_kind",
        "prefix_position",
        "inclusive_next_scalar_minimum",
        "inclusive_next_scalar_maximum",
        "repeated_lower_bound_scalar",
        "minimum_retained_repeat_count",
        "maximum_retained_repeat_count",
    }
)
TRANSIENT_RECURRENCE_STATE_KEYS: Final = frozenset(
    {
        "state_position",
        "ordered_state_key_atoms",
        "ordered_state_key_cells",
        "ordered_state_payload_atoms",
        "ordered_state_payload_cells",
        "ordered_attainable_length_bitmap_runs",
    }
)
ORDERED_STRING_COUNT_FRONTIER_RECORD_KEYS: Final = frozenset(
    {"item_count", "ordered_total_octet_bitmap_runs"}
)
ORDERED_STRING_RECURRENCE_STATE_KINDS: Final = frozenset(
    {
        "SUFFIX_COUNT_RUN",
        "INTERVAL_MULTIPLICITY_RUN",
        "FACTOR_RUN",
        "FACTOR_FOLD_RUN",
        "K1_DIRECT_FEASIBILITY",
        "BULK_UNRANK_TEST",
        "QUERY_RESULT",
    }
)
TRANSIENT_RECURRENCE_PARAMETER_KEYS: Final = {
    "ASCII_DFA_DYNAMIC_PROGRAM_V1": frozenset(
        {
            "text_language_id",
            "effective_canonical_octet_ceiling",
            "ordered_relation_descriptor_ids",
        }
    ),
    "UNICODE_15_NFC_DYNAMIC_PROGRAM_V1": frozenset(
        {
            "text_language_id",
            "effective_canonical_octet_ceiling",
            "ordered_relation_descriptor_ids",
        }
    ),
    "ORDERED_RAW_STRING_PREFIX_FEASIBILITY_V1": frozenset(
        {
            "invocation_kind",
            "safe_array_node_position",
            "target_array_octets",
            "cardinality_query_kind",
            "minimum_array_cardinality",
            "maximum_array_cardinality",
            "array_cardinality",
            "fixed_item_count",
            "ordered_fixed_item_scalar_prefix_positions",
            "per_string_canonical_octet_ceiling",
        }
    ),
    "DERIVED_IDENTITY_PREFIX_FEASIBILITY_V1": frozenset(
        {
            "invocation_kind",
            "safe_identity_node_position",
            "semantic_identity_domain",
            "target_enclosing_canonical_octets",
            "input_prefix_frontier_child_position",
            "fixed_active_prefix_coordinate_count",
            "fixed_primitive_prefix_position",
            "ordered_identity_payload_child_positions",
            "ordered_payload_observable_descriptor_ids",
            "ordered_identity_relation_descriptor_ids",
        }
    ),
}
DERIVED_IDENTITY_MAPPING_CATALOG_KEYS: Final = frozenset(
    {
        "catalog_version",
        "defining_subject_locator",
        "semantic_identity_domain",
        "ordered_mapping_records",
    }
)
DERIVED_IDENTITY_MAPPING_RECORD_KEYS: Final = frozenset(
    {
        "semantic_identity_preimage_canonical_bytes_hex",
        "derived_identity_text",
        "derived_identity_canonical_sha256",
    }
)
INTEGER_INTERVAL_KEYS: Final = frozenset(
    {
        "inclusive_minimum",
        "inclusive_maximum",
        "decimal_digit_count",
        "ordered_constant_affine_region_ids",
    }
)
ACTIVATION_GUARD_KEYS: Final = frozenset(
    {
        "guard_clause_position",
        "prior_choice_coordinate_plan_id",
        "guard_operator",
        "guard_atom",
    }
)
CODEC_COORDINATE_KEYS: Final = frozenset(
    {
        "validation_root_type_name",
        "codec_owner_type_name",
        "codec_owner_typed_member_path",
        "codec_byte_bound_relation",
        "codec_octet_limit",
    }
)
BITMAP_RUN_KEYS: Final = frozenset(
    {"first_block_index", "last_block_index", "attainable_length_bitmap_hex"}
)
STATE_FRONTIER_KEYS: Final = frozenset({"state_key", "ordered_length_bitmap_runs"})
MATERIALIZED_FRONTIER_KEYS: Final = frozenset(
    {
        "frontier_soundness",
        "state_signature_id",
        "ordered_observable_descriptor_ids",
        "ordered_state_frontiers",
    }
)
DIRECT_CHILD_ALIAS_KEYS: Final = frozenset(
    {
        "aliased_child_position",
        "aliased_child_proof_node_id",
        "resolved_materialized_origin_position",
    }
)
OUTPUT_FRONTIER_KEYS: Final = frozenset(
    {
        "frontier_encoding_kind",
        "materialized_frontier",
        "direct_child_alias",
    }
)
FRONTIER_COMMITMENT_KEYS: Final = frozenset(
    {
        "frontier_version",
        "state_signature_id",
        "state_entry_count",
        "bitmap_run_count",
        "expanded_attainable_point_count",
        "minimum_attainable_octets",
        "maximum_attainable_octets",
        "expanded_frontier_sha256",
        "canonical_bitmap_run_frontier_sha256",
        "least_measured_choice_vector_sha256_at_maximum",
        "least_context_choice_vector_sha256_at_maximum",
        "frontier_commitment_id",
    }
)
PROOF_NODE_KEYS: Final = frozenset(
    {
        "proof_node_position",
        "proof_node_kind",
        "subject_locator",
        "value_schema_id",
        "type_name",
        "alternative_name",
        "effective_canonical_octet_ceiling",
        "ordered_child_positions",
        "ordered_child_proof_node_ids",
        "ordered_ancestor_observable_dimensions",
        "output_frontier",
        "frontier_commitment",
        "derivation",
        "proof_node_id",
    }
)
PROOF_NODE_KINDS: Final = frozenset(
    {
        "FIXED_VALUE",
        "BOOLEAN_VALUE_FRONTIER",
        "SAFE_UINT_DIGIT_FRONTIER",
        "TEXT_LANGUAGE_FRONTIER",
        "NULLABLE_CASE_FRONTIER",
        "ARRAY_FRONTIER",
        "RECORD_FRONTIER",
        "TAGGED_UNION_FRONTIER",
        "CONSTRAINT_FRONTIER",
        "SCOPE_FRONTIER",
        "MAXIMUM_SLICE_EXACT_FRONTIER",
        "LEXICOGRAPHIC_PREFIX_EXCLUSION",
        "LOCAL_SHUTDOWN_MINIMALITY_FRONTIER",
        "CODEC_INTERSECTION_ATTAINMENT",
    }
)
DERIVATION_KEYS: Final = {
    "FIXED_VALUE": frozenset(
        {
            "derivation_kind",
            "fixed_source_kind",
            "fixed_source_locator",
            "fixed_transfer_kind",
            "fixed_canonical_byte_length",
            "fixed_canonical_sha256",
            "derived_identity_mapping_catalog_id",
            "ordered_identity_payload_child_positions",
        }
    ),
    "BOOLEAN_VALUE_FRONTIER": frozenset({"derivation_kind", "ordered_boolean_values"}),
    "SAFE_UINT_DIGIT_FRONTIER": frozenset(
        {
            "derivation_kind",
            "integer_minimum",
            "integer_maximum",
            "ordered_decimal_digit_bands",
        }
    ),
    "TEXT_LANGUAGE_FRONTIER": frozenset(
        {
            "derivation_kind",
            "text_language_id",
            "language_kind",
            "text_solver_kind",
            "unicode_version",
            "transient_recurrence_catalog",
        }
    ),
    "NULLABLE_CASE_FRONTIER": frozenset(
        {"derivation_kind", "null_branch_enabled", "non_null_child_position"}
    ),
    "ARRAY_FRONTIER": frozenset(
        {
            "derivation_kind",
            "array_minimum_items",
            "array_maximum_items",
            "item_child_position",
            "array_semantics",
            "array_transfer_kind",
        }
    ),
    "RECORD_FRONTIER": frozenset(
        {
            "derivation_kind",
            "record_type_name",
            "ordered_member_child_positions",
            "derived_identity_member_name",
        }
    ),
    "TAGGED_UNION_FRONTIER": frozenset(
        {
            "derivation_kind",
            "union_type_name",
            "ordered_alternative_child_positions",
            "ordered_alternative_names",
            "owner_constraint_present",
        }
    ),
    "CONSTRAINT_FRONTIER": frozenset(
        {
            "derivation_kind",
            "constraint_source_kind",
            "ordered_constraint_ids",
            "application_invocation",
            "ordered_applicable_scope_case_positions",
            "constraint_transfer_kind",
            "relaxation_direction",
            "input_frontier_child_position",
        }
    ),
    "SCOPE_FRONTIER": frozenset(
        {
            "derivation_kind",
            "constraint_scope",
            "constraint_scope_id",
            "constraint_scope_profile_id",
            "measurement_binding",
            "ordered_scope_cases",
            "scope_transfer_kind",
        }
    ),
    "MAXIMUM_SLICE_EXACT_FRONTIER": frozenset(
        {
            "derivation_kind",
            "target_canonical_byte_length",
            "ordered_exact_constraint_bindings",
            "ordered_exact_domain_reinstatement_node_positions",
            "ordered_choice_coordinate_plan_ids",
            "ordered_transient_recurrence_catalogs",
            "upper_frontier_child_position",
        }
    ),
    "LEXICOGRAPHIC_PREFIX_EXCLUSION": frozenset(
        {
            "derivation_kind",
            "target_canonical_byte_length",
            "choice_scope",
            "choice_coordinate_plan_id",
            "coordinate_activation",
            "fixed_prefix_coordinate_count",
            "fixed_active_prefix_coordinate_count",
            "selected_atom",
            "ordered_transient_recurrence_catalogs",
            "input_prefix_frontier_child_position",
        }
    ),
    "LOCAL_SHUTDOWN_MINIMALITY_FRONTIER": frozenset(
        {
            "derivation_kind",
            "baseline_spec_record_reference",
            "ordered_mutable_limit_member_names",
            "ordered_intrinsic_relation_ids",
            "prospective_result_attainment_mode",
            "masked_outer_codec_coordinate",
            "baseline_result_inventory_json_pointer",
            "baseline_result_canonical_byte_length",
            "outer_codec_byte_bound_relation",
            "outer_codec_octet_limit",
            "winning_objective",
            "prospective_result_canonical_byte_length",
            "prospective_result_canonical_sha256",
            "baseline_spec_fixed_child_position",
            "ordered_boundary_candidate_root_positions",
            "ordered_boundary_candidate_witness_records",
            "ordered_breakpoint_records",
            "ordered_interval_exclusion_records",
            "ordered_recurrence_state_records",
            "ordered_recurrence_transition_records",
            "ordered_dominance_deletion_records",
            "recurrence_version",
        }
    ),
    "CODEC_INTERSECTION_ATTAINMENT": frozenset(
        {
            "derivation_kind",
            "attainment_mode",
            "codec_byte_bound_relation",
            "codec_octet_limit",
            "owner_codec_byte_bound_relation",
            "owner_codec_octet_limit",
            "masked_codec_coordinate",
            "certified_upper_bound_octets",
            "attaining_witness_canonical_byte_length",
            "attaining_witness_canonical_sha256",
            "attaining_scope_case_position",
            "upper_frontier_child_position",
            "winner_frontier_child_position",
        }
    ),
}

DECIMAL_DIGIT_BAND_KEYS: Final = frozenset(
    {"digit_count", "inclusive_minimum", "inclusive_maximum"}
)
SCOPE_CASE_KEYS: Final = frozenset(
    {
        "scope_case_position",
        "root_family_position",
        "mode_attempt_pair_position",
        "observation_role_position",
        "measured_sequence_ordinal",
        "ordered_application_invocations",
        "scope_case_child_position",
    }
)
EXACT_CONSTRAINT_BINDING_KEYS: Final = frozenset(
    {
        "constraint_id",
        "application_invocation",
        "ordered_applicable_scope_case_positions",
    }
)
BOUNDARY_CANDIDATE_WITNESS_KEYS: Final = frozenset(
    {
        "boundary_witness_position",
        "boundary_candidate_root_position",
        "candidate_mutated_spec",
        "prospective_scope_witness_context",
        "prospective_result",
        "ordered_component_choice_evidence",
        "prospective_result_canonical_byte_length",
        "prospective_result_canonical_sha256",
        "boundary_candidate_witness_id",
    }
)
APPLICATION_INVOCATION_KEYS: Final = frozenset(
    {
        "application_name",
        "application_invocation_ordinal",
        "bound_observation_ordinal",
    }
)
CHOICE_COORDINATE_PLAN_KEYS: Final = frozenset(
    {
        "coordinate_plan_position",
        "coordinate_scope",
        "coordinate_kind",
        "subject_locator",
        "value_schema_id",
        "ordered_activation_guard_clauses",
        "choice_coordinate_plan_id",
    }
)
CHOICE_EVIDENCE_KEYS: Final = frozenset(
    {
        "evidence_position",
        "coordinate_plan_position",
        "coordinate_scope",
        "coordinate_kind",
        "subject_locator",
        "value_schema_id",
        "ordered_activation_guard_clauses",
        "choice_coordinate_plan_id",
        "selected_value_kind",
        "selected_value_locator",
        "selected_canonical_byte_length",
        "selected_canonical_sha256",
        "supporting_proof_node_position",
        "component_choice_coordinate_id",
    }
)
CERTIFICATE_KEYS: Final = frozenset(
    {
        "certificate_version",
        "canonicalization_version",
        "measurement_schema_version",
        "maximum_protocol_sha256",
        "source_inventory_sha256",
        "external_schema_registry_id",
        "rule_literal_authority_sha256",
        "maximum_context_object_manifest_id",
        "constraint_scope_id",
        "measured_type_name",
        "alternative_name",
        "objective_version",
        "proof_plan_version",
        "frontier_encoding_version",
        "ordered_proof_nodes",
        "root_proof_node_position",
        "measured_choice_root_proof_node_position",
        "context_choice_root_proof_node_position",
        "proof_resource_claim",
        "certified_analytic_maximum_octets",
        "winning_measured_choice_vector_sha256",
        "winning_context_choice_vector_sha256",
        "upper_bound_certificate_id",
    }
)
MAX64_CONTEXT_AUTHORITY_ROOT_KEYS: Final = frozenset(
    {"observations", "root", "selector"}
)
ACCEPTANCE_AUTHORITY_KEYS: Final = frozenset(
    {
        "artifact_version",
        "candidate_protocol_raw_octet_count",
        "candidate_protocol_sha256",
        "final_protocol_raw_octet_count",
        "final_protocol_sha256",
        "ordered_protocol_rebind_patch_records",
        "seed_pilot_raw_octet_count",
        "seed_pilot_raw_sha256",
        "final_pilot_raw_octet_count",
        "final_pilot_raw_sha256",
        "independent_validator_raw_octet_count",
        "independent_validator_raw_sha256",
        "focused_test_raw_octet_count",
        "focused_test_raw_sha256",
        "acceptance_decision",
        "maximum_protocol_acceptance_id",
    }
)
PROTOCOL_REBIND_PATCH_KEYS: Final = frozenset(
    {
        "patch_position",
        "patch_kind",
        "candidate_start_octet",
        "candidate_end_octet_exclusive",
        "candidate_bytes_hex",
        "final_bytes_hex",
    }
)


class MaximumProtocolValidationError(ValueError):
    """Controlled candidate-protocol validation failure."""


class FrozenFile(NamedTuple):
    raw: bytes
    signature: tuple[int, ...]


class RowPlan(NamedTuple):
    row_position: int
    row_kind: str
    type_name: str
    alternative_name: str | None
    constraint_scope_profile_id: str | None


class V1PresearchCapRejection(NamedTuple):
    intrinsic_row_position: int
    outer_fixed_descriptor_occurrence_count: int
    inner_array_cardinality_coordinate_count: int
    inner_text_coordinate_count: int
    component_choice_coordinate_lower_bound: int
    prefix_proof_node_lower_bound: int
    tie_break_proof_node_lower_bound: int
    maximum_proof_depth_lower_bound: int
    component_coordinate_cap_excess: int
    proof_node_cap_excess_before_base_nodes: int
    tie_break_proof_node_cap_excess_before_descriptor_and_root_nodes: int
    maximum_proof_depth_cap_excess_before_descriptor_and_root_nodes: int


class ScopeAxisKey(NamedTuple):
    profile_position: int
    coordinate_kind: str
    root_family_position: int | None
    mode_attempt_pair_position: int | None
    observation_role_position: int | None


class ScopeGuardSeed(NamedTuple):
    prior_axis_key: ScopeAxisKey
    guard_operator: str
    position_value: int


class SyntheticScopeAxisSeed(NamedTuple):
    axis_key: ScopeAxisKey
    coordinate_kind: str
    subject_locator: dict[str, Any]
    ordered_admissible_position_values: tuple[int, ...]
    ordered_activation_guard_seeds: tuple[ScopeGuardSeed, ...]


class ConstructedContextOccurrence(NamedTuple):
    occurrence_position_within_case: int
    record_role: str
    record_type_name: str
    external_sequence_ordinal: int | None
    ordered_activation_guard_seeds: tuple[ScopeGuardSeed, ...]


class ScopeCaseSeed(NamedTuple):
    scope_case_position: int
    root_family_position: int | None
    mode_attempt_pair_position: int | None
    observation_role_position: int | None
    measured_sequence_ordinal: int | None
    mode_attempt_pair: tuple[str, str] | None
    observation_role: str | None
    ordered_activation_guard_seeds: tuple[ScopeGuardSeed, ...]
    ordered_application_invocations: tuple[dict[str, Any], ...]
    ordered_constructed_context_occurrences: tuple[ConstructedContextOccurrence, ...]


class ScopePlanEvent(NamedTuple):
    event_kind: str
    synthetic_axis: SyntheticScopeAxisSeed | None
    scope_case: ScopeCaseSeed | None


class DerivedScopeHierarchy(NamedTuple):
    profile_position: int
    constraint_scope_profile_id: str
    ordered_events: tuple[ScopePlanEvent, ...]
    ordered_scope_cases: tuple[ScopeCaseSeed, ...]
    synthetic_axis_count: int
    constructed_context_occurrence_count: int
    context_record_reference_count: int
    observation_count: int
    application_invocation_count: int
    charged_cross_rule_evaluation_count: int
    direct_cross_expression_node_count: int


class PriorScopeAxisPlanAuthority(NamedTuple):
    axis_key: ScopeAxisKey
    coordinate_plan_position: int
    choice_coordinate_plan_id: str


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise MaximumProtocolValidationError(message)


def _select_effective_resource_limits(
    *,
    phase: str,
    accepted_limits: Mapping[str, int] | None = None,
) -> dict[str, int]:
    """Return the only legal limit table for one validation phase."""

    _require(phase in PROOF_RESOURCE_PHASES, "proof-resource phase differs")
    if phase == SEED_CAP_DERIVATION_PHASE:
        _require(
            accepted_limits is None,
            "seed-cap derivation cannot consume pilot-derived accepted limits",
        )
        return dict(SEED_EXECUTION_SAFETY_LIMITS_V1)
    _require(
        accepted_limits is not None,
        f"{phase} requires independently accepted proof-resource limits",
    )
    actual = set(accepted_limits)
    missing = sorted(ACCEPTED_PROOF_RESOURCE_LIMIT_KEYS - actual)
    extra = sorted(actual - ACCEPTED_PROOF_RESOURCE_LIMIT_KEYS)
    _require(
        not missing and not extra,
        f"accepted proof-resource limit keys differ: {missing=} {extra=}",
    )
    selected: dict[str, int] = {}
    for name in sorted(ACCEPTED_PROOF_RESOURCE_LIMIT_KEYS):
        value = accepted_limits[name]
        _require(
            type(value) is int and 0 <= value <= SAFE_INTEGER_MAXIMUM,
            f"accepted proof-resource limit {name} is not a nonnegative safe integer",
        )
        _require(
            value <= SEED_EXECUTION_SAFETY_LIMITS_V1[name],
            f"accepted proof-resource limit {name} exceeds its seed safety limit",
        )
        selected[name] = value
    derived_dimension_limit = (
        selected["proof_node_count"]
        * selected["maximum_state_signature_dimension_count"]
    )
    _require(
        derived_dimension_limit <= SAFE_INTEGER_MAXIMUM
        and derived_dimension_limit
        <= SEED_EXECUTION_SAFETY_LIMITS_V1[DERIVED_RESOURCE_LIMIT_FIELD],
        "derived state-signature-dimension limit exceeds seed-safe arithmetic",
    )
    selected[DERIVED_RESOURCE_LIMIT_FIELD] = derived_dimension_limit
    return selected


class ProofResourceMeter:
    """Atomic cap-first accounting for the nineteen frozen claim fields."""

    __slots__ = ("_limits", "_values", "phase")

    def __init__(
        self,
        *,
        phase: str,
        accepted_limits: Mapping[str, int] | None = None,
    ) -> None:
        self.phase = phase
        self._limits = _select_effective_resource_limits(
            phase=phase,
            accepted_limits=accepted_limits,
        )
        self._values = dict.fromkeys(PROOF_RESOURCE_KEYS, 0)

    @property
    def limits(self) -> dict[str, int]:
        return dict(self._limits)

    def snapshot(self) -> dict[str, int]:
        return dict(self._values)

    def value(self, name: str) -> int:
        _require(name in PROOF_RESOURCE_KEYS, f"unknown proof-resource field: {name}")
        return self._values[name]

    def _check_candidate(self, name: str, candidate: int) -> None:
        _require(name in PROOF_RESOURCE_KEYS, f"unknown proof-resource field: {name}")
        _require(
            type(candidate) is int and 0 <= candidate <= SAFE_INTEGER_MAXIMUM,
            f"{self.phase} {name} prospective value exceeds safe-I-JSON arithmetic",
        )
        _require(
            candidate <= self._limits[name],
            f"{self.phase} {name} prospective value {candidate} exceeds "
            f"effective limit {self._limits[name]}",
        )

    def ensure_at_most(self, name: str, candidate: int) -> None:
        """Check a directly observable prospective value without committing it."""

        self._check_candidate(name, candidate)

    def reserve(self, increments: Mapping[str, int]) -> None:
        """Atomically check all total-field increments before committing any."""

        _require(bool(increments), "proof-resource reservation must not be empty")
        candidates: dict[str, int] = {}
        for name, increment in increments.items():
            _require(
                name in PROOF_RESOURCE_TOTAL_FIELDS,
                f"proof-resource reservation cannot increment maximum field {name}",
            )
            _require(
                type(increment) is int and increment >= 0,
                f"proof-resource increment {name} is not a nonnegative integer",
            )
            candidate = self._values[name] + increment
            self._check_candidate(name, candidate)
            candidates[name] = candidate
        for name, candidate in candidates.items():
            self._values[name] = candidate

    def add(self, name: str, increment: int = 1) -> None:
        self.reserve({name: increment})

    def observe_maximum(self, name: str, observed: int) -> None:
        """Cap-check a possible maximum before making it the recorded maximum."""

        _require(
            name in PROOF_RESOURCE_MAXIMUM_FIELDS,
            f"proof-resource maximum observation targets non-maximum field {name}",
        )
        _require(
            type(observed) is int and observed >= 0,
            f"proof-resource maximum {name} is not a nonnegative integer",
        )
        candidate = max(self._values[name], observed)
        self._check_candidate(name, candidate)
        self._values[name] = candidate


class CertificateFixedPoint(NamedTuple):
    certificate: dict[str, Any]
    hash_preimage_octets: int
    certificate_canonical_octets: int
    certificate_id: str
    iteration_count: int


class CatalogStaticEvidence(NamedTuple):
    """Exact serialization evidence for one verifier-derived catalog root."""

    catalog: dict[str, Any]
    catalog_id: str
    entry_count: int
    complete_root_octets: int
    validation_hash_preimage_octets: int
    referenced_prior_catalog_ids: tuple[str, ...]


class CatalogOccurrenceKey(NamedTuple):
    defining_node_position: int
    catalog_ordinal_within_node: int


class CatalogOccurrence(NamedTuple):
    key: CatalogOccurrenceKey
    catalog_id: str
    complete_root_octets: int
    direct_prior_occurrences: tuple[CatalogOccurrenceKey, ...]
    retention_kind: str


class CatalogRetentionEvidence(NamedTuple):
    last_use_by_occurrence: dict[CatalogOccurrenceKey, int]
    release_buckets: tuple[tuple[CatalogOccurrenceKey, ...], ...]
    peak_retained_octets: int


class ValidatedRecord(NamedTuple):
    """One complete record validated against its frozen structural descriptor."""

    record_type_name: str
    record_identity_field: str
    record_identity: str
    record_canonical_byte_length: int
    record_canonical_sha256: str
    record: dict[str, Any]


class ResolvedRecordReference(NamedTuple):
    """A checked MaximumRecordReferenceV1 paired with its complete record."""

    reference: dict[str, Any]
    validated_record: ValidatedRecord


class ResolvedPilotContextObjectEntry(NamedTuple):
    """One manifest entry paired with its authority-resolved complete record."""

    entry: dict[str, Any]
    validated_record: ValidatedRecord
    maximum_context_object_id: str


class ValidatedPilotContextManifest(NamedTuple):
    """A checked pilot manifest and its closed ordered context-object entries."""

    manifest: dict[str, Any]
    resolved_entries: tuple[ResolvedPilotContextObjectEntry, ...]


class ValidatedPilotLeaf(NamedTuple):
    """Retained pilot leaf after reference and scope-context closure checks."""

    context_manifest: ValidatedPilotContextManifest
    witness_record: dict[str, Any]
    scope_witness_context: dict[str, Any] | None
    resolved_context_reference_count: int
    resolved_context_object_ids: frozenset[str]
    resolved_context_object_octets: int
    maximum_context_object_octets: int
    observation_count: int
    application_invocation_count: int
    charged_cross_rule_evaluation_count: int
    direct_cross_expression_node_count: int


class OrderedRawStringRecurrenceBounds(NamedTuple):
    """Verifier-derived finite bounds needed by ordered-string slot decoders."""

    item_count_limit: int
    maximum_total_octets: int
    fixed_prefix_positions: tuple[int, ...]
    array_cardinality: int | None
    target_array_octets: int
    per_string_canonical_octet_ceiling: int


class DerivedIdentityRecurrenceBounds(NamedTuple):
    """Locally checkable bounds for a derived-identity recurrence root."""

    target_enclosing_canonical_octets: int
    fixed_primitive_prefix_position: int
    observable_descriptor_count: int
    identity_relation_count: int


class TextRecurrenceBounds(NamedTuple):
    """Locally checkable bounds shared by ASCII and pinned-NFC recurrences."""

    effective_canonical_octet_ceiling: int
    relation_descriptor_count: int


def _canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise MaximumProtocolValidationError(
            "value is not compact canonical I-JSON encodable"
        ) from exc


def _pretty_bytes(value: Any) -> bytes:
    try:
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
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise MaximumProtocolValidationError(
            "value is not pretty canonical I-JSON encodable"
        ) from exc


def _pretty_octet_length(value: Any) -> int:
    """Measure sorted two-space-indented JSON plus LF without retaining it."""

    encoder = json.JSONEncoder(
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        indent=2,
    )
    total = 1  # The frozen pretty encoding has one final LF.
    try:
        for chunk in encoder.iterencode(value):
            chunk_octets = len(chunk.encode("utf-8"))
            _require(
                total <= SAFE_INTEGER_MAXIMUM - chunk_octets,
                "pretty JSON length exceeds safe-I-JSON arithmetic",
            )
            total += chunk_octets
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise MaximumProtocolValidationError(
            "value is not pretty canonical I-JSON encodable"
        ) from exc
    return total


def _canonical_text_chunks(value: Any):  # type: ignore[no-untyped-def]
    encoder = json.JSONEncoder(
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    try:
        yield from encoder.iterencode(value)
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise MaximumProtocolValidationError(
            "value is not compact canonical I-JSON encodable"
        ) from exc


def _canonical_octet_length(value: Any) -> int:
    """Compute compact-canonical UTF-8 length without constructing its bytes."""

    active_container_ids: set[int] = set()

    def checked_sum(*parts: int) -> int:
        total = 0
        for part in parts:
            prospective = total + part
            _require(
                prospective <= SAFE_INTEGER_MAXIMUM,
                "canonical JSON length exceeds safe-I-JSON arithmetic",
            )
            total = prospective
        return total

    def string_octets(text: str) -> int:
        total = 2
        for character in text:
            codepoint = ord(character)
            if character in {'"', "\\"} or character in {"\b", "\t", "\n", "\f", "\r"}:
                width = 2
            elif codepoint < 0x20:
                width = 6
            elif codepoint <= 0x7F:
                width = 1
            elif codepoint <= 0x7FF:
                width = 2
            elif 0xD800 <= codepoint <= 0xDFFF:
                raise MaximumProtocolValidationError(
                    "canonical JSON text contains a surrogate code point"
                )
            elif codepoint <= 0xFFFF:
                width = 3
            else:
                width = 4
            total = checked_sum(total, width)
        return total

    def visit(item: Any, depth: int) -> int:
        _require(
            depth <= MAXIMUM_JSON_DEPTH,
            "canonical JSON exceeds the structural depth cap",
        )
        if item is None:
            return 4
        if type(item) is bool:
            return 4 if item else 5
        if type(item) is int:
            _require(
                -SAFE_INTEGER_MAXIMUM <= item <= SAFE_INTEGER_MAXIMUM,
                "canonical JSON integer is outside the safe-I-JSON domain",
            )
            return len(str(item))
        if type(item) is str:
            return string_octets(item)
        if type(item) not in {dict, list, tuple}:
            raise MaximumProtocolValidationError(
                "value is not compact canonical I-JSON encodable"
            )
        identity = id(item)
        _require(
            identity not in active_container_ids,
            "canonical JSON contains a circular container reference",
        )
        active_container_ids.add(identity)
        try:
            if type(item) is dict:
                total = 2
                for position, (key, child) in enumerate(item.items()):
                    _require(
                        type(key) is str,
                        "canonical JSON object member name is not text",
                    )
                    total = checked_sum(
                        total,
                        int(position != 0),
                        string_octets(key),
                        1,
                        visit(child, depth + 1),
                    )
                return total
            total = 2
            for position, child in enumerate(item):
                total = checked_sum(
                    total,
                    int(position != 0),
                    visit(child, depth + 1),
                )
            return total
        finally:
            active_container_ids.remove(identity)

    return visit(value, 1)


def _canonical_sha256_stream(value: Any) -> str:
    """Hash compact canonical JSON incrementally, never as one byte buffer."""

    digest = hashlib.sha256()
    for chunk in _canonical_text_chunks(value):
        digest.update(chunk.encode("utf-8", errors="strict"))
    return digest.hexdigest()


def _metered_canonical_sha256(
    value: Any,
    *,
    meter: ProofResourceMeter,
    canonicalized_field: str | None = None,
) -> tuple[str, int]:
    """Reserve canonical/hash work atomically before emitting or hashing bytes."""

    octets = _canonical_octet_length(value)
    increments = {"hash_preimage_octets": octets}
    if canonicalized_field is not None:
        _require(
            canonicalized_field in PROOF_RESOURCE_TOTAL_FIELDS,
            "canonicalized work targets an invalid proof-resource field",
        )
        increments[canonicalized_field] = octets
    meter.reserve(increments)
    return _canonical_sha256_stream(value), octets


def _metered_raw_sha256(
    raw: bytes,
    *,
    meter: ProofResourceMeter,
) -> str:
    _require(type(raw) is bytes, "raw SHA preimage must be bytes")
    meter.add("hash_preimage_octets", len(raw))
    return hashlib.sha256(raw).hexdigest()


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _semantic_id(
    domain: str,
    payload: dict[str, Any],
    *,
    resource_meter: ProofResourceMeter | None = None,
) -> str:
    envelope = {
        "canonicalization_version": CANONICALIZATION_VERSION,
        "domain": domain,
        "payload": payload,
        "schema_version": MEASUREMENT_SCHEMA_VERSION,
    }
    if resource_meter is not None:
        digest, _ = _metered_canonical_sha256(envelope, meter=resource_meter)
        return digest
    return _sha256(_canonical_bytes(envelope))


def _solve_upper_bound_certificate_fixed_point(
    certificate: dict[str, Any],
    *,
    hash_preimage_octets_before_certificate: int,
    meter: ProofResourceMeter,
) -> CertificateFixedPoint:
    """Solve and commit the protocol's least joint certificate H/C fixed point."""

    h0 = hash_preimage_octets_before_certificate
    _require(
        type(h0) is int and 0 <= h0 <= SAFE_INTEGER_MAXIMUM,
        "certificate fixed-point H0 is not a nonnegative safe integer",
    )
    _require(
        meter.value("hash_preimage_octets") == h0,
        "certificate fixed-point H0 differs from the committed meter",
    )
    _require(
        meter.value("certificate_canonical_octets") == 0,
        "certificate canonical octets were committed before fixed-point solving",
    )
    _require(type(certificate) is dict, "upper-bound certificate must be an object")
    unsigned_base = {
        name: item
        for name, item in certificate.items()
        if name != "upper_bound_certificate_id"
    }
    claim = unsigned_base.get("proof_resource_claim")
    _require(type(claim) is dict, "upper-bound certificate resource claim differs")
    actual = set(claim)
    _require(
        actual == PROOF_RESOURCE_KEYS,
        "upper-bound certificate resource-claim keys differ at fixed-point solving",
    )
    for name, value in claim.items():
        _require(
            type(value) is int and 0 <= value <= SAFE_INTEGER_MAXIMUM,
            f"upper-bound certificate resource claim {name} is not a "
            "nonnegative safe integer",
        )
    for name in PROOF_RESOURCE_KEYS - {
        "hash_preimage_octets",
        "certificate_canonical_octets",
    }:
        _require(
            claim[name] == meter.value(name),
            f"upper-bound certificate resource claim {name} differs before fixed point",
        )

    def unsigned_at(hash_octets: int, certificate_octets: int) -> dict[str, Any]:
        completed_claim = {
            **claim,
            "hash_preimage_octets": hash_octets,
            "certificate_canonical_octets": certificate_octets,
        }
        return {**unsigned_base, "proof_resource_claim": completed_claim}

    def identity_envelope(unsigned: dict[str, Any]) -> dict[str, Any]:
        return {
            "canonicalization_version": CANONICALIZATION_VERSION,
            "domain": CERTIFICATE_DOMAIN,
            "payload": unsigned,
            "schema_version": MEASUREMENT_SCHEMA_VERSION,
        }

    hash_octets = 0
    certificate_octets = 0
    iteration_count = 0
    fixed_unsigned: dict[str, Any] | None = None
    fixed_envelope: dict[str, Any] | None = None
    for iteration in range(1, 129):
        iteration_count = iteration
        trial_unsigned = unsigned_at(hash_octets, certificate_octets)
        trial_envelope = identity_envelope(trial_unsigned)
        envelope_octets = _canonical_octet_length(trial_envelope)
        prospective_hash_octets = h0 + envelope_octets
        _require(
            prospective_hash_octets <= SAFE_INTEGER_MAXIMUM,
            "certificate fixed-point hash count exceeds safe-I-JSON arithmetic",
        )
        trial_completed = {
            **trial_unsigned,
            "upper_bound_certificate_id": "0" * SHA256_HEX_LENGTH,
        }
        prospective_certificate_octets = _canonical_octet_length(trial_completed)
        pair = (prospective_hash_octets, prospective_certificate_octets)
        previous_pair = (hash_octets, certificate_octets)
        _require(
            pair[0] >= previous_pair[0] and pair[1] >= previous_pair[1],
            "certificate length fixed-point map is not monotone",
        )
        if pair == previous_pair:
            fixed_unsigned = trial_unsigned
            fixed_envelope = trial_envelope
            break
        hash_octets, certificate_octets = pair
    _require(
        fixed_unsigned is not None and fixed_envelope is not None,
        "certificate length fixed point did not stabilize",
    )
    envelope_octets = _canonical_octet_length(fixed_envelope)
    _require(
        hash_octets == h0 + envelope_octets,
        "certificate hash-preimage fixed-point equality differs",
    )
    meter.reserve(
        {
            "hash_preimage_octets": envelope_octets,
            "certificate_canonical_octets": certificate_octets,
        }
    )
    certificate_id = _canonical_sha256_stream(fixed_envelope)
    completed = {
        **fixed_unsigned,
        "upper_bound_certificate_id": certificate_id,
    }
    _require(
        _canonical_octet_length(completed) == certificate_octets,
        "certificate canonical-octet fixed-point equality differs",
    )
    _require(
        meter.value("hash_preimage_octets") == hash_octets
        and meter.value("certificate_canonical_octets") == certificate_octets,
        "certificate fixed-point meter commit differs",
    )
    return CertificateFixedPoint(
        certificate=completed,
        hash_preimage_octets=hash_octets,
        certificate_canonical_octets=certificate_octets,
        certificate_id=certificate_id,
        iteration_count=iteration_count,
    )


def _finalize_upper_bound_certificate_resource_claim(
    certificate: dict[str, Any],
    *,
    meter: ProofResourceMeter,
) -> CertificateFixedPoint:
    """Solve once, then require exact producer equality and a full meter match."""

    solved = _solve_upper_bound_certificate_fixed_point(
        certificate,
        hash_preimage_octets_before_certificate=meter.value("hash_preimage_octets"),
        meter=meter,
    )
    _require(
        certificate == solved.certificate,
        "upper-bound certificate differs from the least joint H/C fixed point",
    )
    _require(
        certificate["proof_resource_claim"] == meter.snapshot(),
        "upper-bound certificate resource claim differs from the completed meter",
    )
    return solved


def _require_certificate_semantic_resource_accounting_complete() -> None:
    """Keep certificate acceptance unreachable until every event is derived."""

    _require(
        CERTIFICATE_SEMANTIC_RESOURCE_ACCOUNTING_COMPLETE,
        SEMANTIC_RESOURCE_ACCOUNTING_INCOMPLETE,
    )


def _is_sha256(value: Any) -> bool:
    return (
        type(value) is str
        and len(value) == SHA256_HEX_LENGTH
        and all(character in "0123456789abcdef" for character in value)
    )


def _require_sha256(value: Any, *, label: str) -> str:
    _require(_is_sha256(value), f"{label} must be one lowercase SHA-256")
    return value


def _require_absolute_rfc6901_pointer(value: Any, *, label: str) -> str:
    _require(
        type(value) is str and value.startswith("/"),
        f"{label} must be one nonempty absolute RFC 6901 JSON Pointer",
    )
    position = 0
    while position < len(value):
        if value[position] != "~":
            position += 1
            continue
        _require(
            position + 1 < len(value) and value[position + 1] in {"0", "1"},
            f"{label} contains a non-RFC-6901 escape",
        )
        position += 2
    return value


def _resolve_absolute_rfc6901_pointer(
    document: Any,
    pointer: Any,
    *,
    label: str,
) -> Any:
    """Resolve one strict, nonempty RFC 6901 pointer without coercion."""

    checked_pointer = _require_absolute_rfc6901_pointer(pointer, label=label)
    current = document
    for token_position, encoded_token in enumerate(
        checked_pointer[1:].split("/"),
        1,
    ):
        token = encoded_token.replace("~1", "/").replace("~0", "~")
        token_label = f"{label} token {token_position}"
        if type(current) is dict:
            _require(token in current, f"{token_label} does not exist")
            current = current[token]
            continue
        if type(current) is list:
            _require(
                bool(token) and all("0" <= character <= "9" for character in token),
                f"{token_label} is not an RFC-6901 array index",
            )
            _require(
                token == "0" or not token.startswith("0"),
                f"{token_label} has a noncanonical leading zero",
            )
            maximum_index_text = str(len(current) - 1)
            _require(
                len(current) > 0
                and (
                    len(token) < len(maximum_index_text)
                    or (
                        len(token) == len(maximum_index_text)
                        and token <= maximum_index_text
                    )
                ),
                f"{token_label} is outside the array",
            )
            current = current[int(token)]
            continue
        raise MaximumProtocolValidationError(
            f"{token_label} traverses a non-container value"
        )
    return current


def _require_integer(
    value: Any,
    *,
    label: str,
    minimum: int = 0,
    maximum: int = SAFE_INTEGER_MAXIMUM,
) -> int:
    _require(
        type(value) is int and minimum <= value <= maximum,
        f"{label} must be an exact integer in {minimum}..{maximum}",
    )
    return value


def _require_exact_keys(
    value: Any, expected: frozenset[str], *, label: str
) -> dict[str, Any]:
    _require(type(value) is dict, f"{label} must be an exact object")
    actual = set(value)
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    _require(not missing and not extra, f"{label} keys differ: {missing=} {extra=}")
    return value


def _require_array(
    value: Any,
    *,
    label: str,
    exact_length: int | None = None,
    maximum_length: int | None = None,
) -> list[Any]:
    _require(type(value) is list, f"{label} must be an array")
    if exact_length is not None:
        _require(len(value) == exact_length, f"{label} length differs")
    if maximum_length is not None:
        _require(len(value) <= maximum_length, f"{label} exceeds its item cap")
    return value


def _stat_signature(value: os.stat_result) -> tuple[int, ...]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_nlink,
        value.st_uid,
        value.st_gid,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _absolute_lexical_path(path: Path, *, base: Path | None = None) -> Path:
    if not path.is_absolute():
        _require(base is not None, "relative secure path has no base")
        path = base / path
    _require(path.is_absolute(), "secure input path is not absolute")
    _require(
        all(part not in {"", ".", ".."} for part in path.parts[1:]),
        f"secure input path is not normalized: {path}",
    )
    return path


def _secure_bounded_read(
    path: Path,
    *,
    base: Path | None = None,
    maximum_octets: int,
    expected_octets: int | None = None,
    expected_sha256: str | None = None,
) -> FrozenFile:
    """Read through no-follow directory descriptors and retain exact bytes."""

    _require(
        type(maximum_octets) is int and maximum_octets > 0,
        "secure read limit is invalid",
    )
    absolute = _absolute_lexical_path(path, base=base)
    directory_flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    directory_flags |= getattr(os, "O_DIRECTORY", 0)
    directory_flags |= getattr(os, "O_NOFOLLOW", 0)
    file_flags = os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_CLOEXEC", 0)
    file_flags |= getattr(os, "O_NOFOLLOW", 0)
    directory_fd: int | None = None
    file_fd: int | None = None
    raw = b""
    signature: tuple[int, ...] = ()
    try:
        directory_fd = os.open("/", directory_flags)
        parts = absolute.parts[1:]
        _require(bool(parts), "secure input path names no file")
        for part in parts[:-1]:
            next_fd = os.open(part, directory_flags, dir_fd=directory_fd)
            os.close(directory_fd)
            directory_fd = next_fd
        file_name = parts[-1]
        file_fd = os.open(file_name, file_flags, dir_fd=directory_fd)
        before = os.fstat(file_fd)
        _require(stat.S_ISREG(before.st_mode), f"input is not regular: {absolute}")
        _require(before.st_nlink == 1, f"input has a hard-link alias: {absolute}")
        _require(before.st_size < maximum_octets, f"input reaches byte cap: {absolute}")
        if expected_octets is not None:
            _require(
                before.st_size == expected_octets, f"input octets differ: {absolute}"
            )
        chunks: list[bytes] = []
        total = 0
        while True:
            remaining = maximum_octets - total
            _require(remaining > 0, f"input reaches byte cap: {absolute}")
            chunk = os.read(file_fd, min(65_536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            _require(total < maximum_octets, f"input reaches byte cap: {absolute}")
        after = os.fstat(file_fd)
        signature = _stat_signature(before)
        _require(signature == _stat_signature(after), f"input changed: {absolute}")
        entry = os.stat(file_name, dir_fd=directory_fd, follow_symlinks=False)
        _require(
            not stat.S_ISLNK(entry.st_mode) and signature == _stat_signature(entry),
            f"input directory entry changed: {absolute}",
        )
        raw = b"".join(chunks)
        _require(len(raw) == before.st_size, f"input was truncated: {absolute}")
        if expected_sha256 is not None:
            _require(_sha256(raw) == expected_sha256, f"input SHA differs: {absolute}")
    except OSError as exc:
        raise MaximumProtocolValidationError(
            f"cannot securely read input without symlink traversal: {absolute}"
        ) from exc
    finally:
        if file_fd is not None:
            os.close(file_fd)
        if directory_fd is not None:
            os.close(directory_fd)
    return FrozenFile(raw=raw, signature=signature)


def _scan_json_structure(raw: bytes) -> None:
    _require(not raw.startswith(b"\xef\xbb\xbf"), "JSON BOM is forbidden")
    stack: list[int] = []
    closing = {ord("}"): ord("{"), ord("]"): ord("[")}
    in_string = False
    escaped = False
    for octet in raw:
        if in_string:
            if escaped:
                escaped = False
            elif octet == ord("\\"):
                escaped = True
            elif octet == ord('"'):
                in_string = False
            elif octet < 0x20:
                raise MaximumProtocolValidationError(
                    "JSON contains an unescaped control octet"
                )
            continue
        if octet == ord('"'):
            in_string = True
        elif octet in (ord("["), ord("{")):
            stack.append(octet)
            _require(
                len(stack) <= MAXIMUM_JSON_DEPTH,
                "JSON exceeds the structural depth cap",
            )
        elif octet in closing:
            _require(
                bool(stack) and stack[-1] == closing[octet],
                "JSON delimiters are unbalanced",
            )
            stack.pop()
    _require(not in_string and not escaped, "JSON string is unterminated")
    _require(not stack, "JSON container is unterminated")


class _JsonLexicalFrame:
    __slots__ = (
        "item_count",
        "compact_octets",
        "is_certificate",
        "kind",
        "path",
        "pending_key",
        "seen_keys",
        "state",
    )

    def __init__(
        self,
        *,
        kind: str,
        path: tuple[str, ...],
        state: str,
        is_certificate: bool = False,
    ) -> None:
        self.kind = kind
        self.path = path
        self.state = state
        self.is_certificate = is_certificate
        self.compact_octets = 1 if is_certificate else 0
        self.pending_key: str | None = None
        self.item_count = 0
        self.seen_keys: set[str] | None = set() if kind == "OBJECT" else None


class _LexicalProofResourceObserver:
    __slots__ = (
        "_certificate_counts",
        "_expected_pilot_phase",
        "_generic_array_limit",
        "_limits",
        "_path_profile",
    )

    def __init__(
        self,
        limits: Mapping[str, int],
        *,
        path_profile: str,
        expected_pilot_phase: str | None,
    ) -> None:
        _require(
            path_profile in LEXICAL_CERTIFICATE_PROFILES,
            "lexical certificate path profile differs",
        )
        self._path_profile = path_profile
        _require(
            expected_pilot_phase is None
            or expected_pilot_phase
            in {SEED_CAP_DERIVATION_PHASE, FINAL_PROTOCOL_REBIND_PHASE},
            "expected lexical pilot phase differs",
        )
        self._expected_pilot_phase = expected_pilot_phase
        actual = set(limits)
        missing = sorted(PROOF_RESOURCE_KEYS - actual)
        extra = sorted(actual - PROOF_RESOURCE_KEYS)
        _require(
            not missing and not extra,
            f"lexical proof-resource limit keys differ: {missing=} {extra=}",
        )
        self._limits: dict[str, int] = {}
        for name in sorted(PROOF_RESOURCE_KEYS):
            value = limits[name]
            _require(
                type(value) is int and 0 <= value <= SAFE_INTEGER_MAXIMUM,
                f"lexical proof-resource limit {name} differs",
            )
            self._limits[name] = value
        self._generic_array_limit = max(
            self._limits["proof_edge_count"],
            self._limits["state_catalog_entry_count"],
            self._limits["frontier_state_entry_count"],
            self._limits["frontier_bitmap_run_count"],
            self._limits["component_choice_coordinate_count"],
        )
        self._certificate_counts: dict[tuple[str, ...], dict[str, int]] = {}

    def is_certificate_anchor(self, path: tuple[str, ...]) -> bool:
        if self._path_profile == LEXICAL_ANY_CERTIFICATE_PROFILE:
            return True
        normalized_path = tuple(
            "*"
            if len(segment) >= 3
            and segment[0] == "["
            and segment[-1] == "]"
            and segment[1:-1].isdigit()
            else segment
            for segment in path
        )
        return normalized_path in PILOT_CERTIFICATE_ANCHORS

    @property
    def certificate_counts(self) -> dict[tuple[str, ...], dict[str, int]]:
        return {
            anchor: dict(counts) for anchor, counts in self._certificate_counts.items()
        }

    def _counts(self, anchor: tuple[str, ...]) -> dict[str, int]:
        if anchor not in self._certificate_counts:
            self._certificate_counts[anchor] = dict.fromkeys(PROOF_RESOURCE_KEYS, 0)
        return self._certificate_counts[anchor]

    def _check(self, name: str, value: int, *, path: tuple[str, ...]) -> None:
        _require(
            value <= self._limits[name],
            f"JSON lexical path {'/'.join(path)} exceeds {name} limit "
            f"{self._limits[name]}",
        )

    def observe_certificate_compact(
        self, anchor: tuple[str, ...], compact_octets: int
    ) -> None:
        counts = self._counts(anchor)
        counts["certificate_canonical_octets"] = compact_octets
        self._check(
            "certificate_canonical_octets",
            compact_octets,
            path=anchor,
        )

    def observe_scalar(
        self,
        path: tuple[str, ...],
        *,
        token_kind: str,
        token: bytes,
    ) -> None:
        if path != ("pilot_phase",) or self._expected_pilot_phase is None:
            return
        _require(token_kind == "STRING", "pilot_phase is not lexical text")
        _require(
            _decode_bounded_json_member_name(token) == self._expected_pilot_phase,
            f"pilot_phase differs from expected {self._expected_pilot_phase}",
        )

    def observe_array_item(self, path: tuple[str, ...], item_count: int) -> None:
        try:
            proof_marker = len(path) - 1 - path[::-1].index("ordered_proof_nodes")
        except ValueError:
            return
        anchor = path[:proof_marker]
        if not self.is_certificate_anchor(anchor):
            return
        _require(
            item_count <= self._generic_array_limit,
            f"JSON lexical path {'/'.join(path)} exceeds the generic proof-array limit",
        )
        counts = self._counts(anchor)
        field_name = path[-1]
        if proof_marker == len(path) - 1:
            counts["proof_node_count"] = item_count
            self._check("proof_node_count", item_count, path=path)
            return
        relative_path = tuple(
            "*"
            if len(segment) >= 3
            and segment[0] == "["
            and segment[-1] == "]"
            and segment[1:-1].isdigit()
            else segment
            for segment in path[proof_marker + 1 :]
        )
        if relative_path == ("*", "ordered_child_positions"):
            counts["proof_edge_count"] += 1
            counts["maximum_child_count"] = max(
                counts["maximum_child_count"], item_count
            )
            self._check("proof_edge_count", counts["proof_edge_count"], path=path)
            self._check("maximum_child_count", item_count, path=path)
            return
        if relative_path == ("*", "ordered_ancestor_observable_dimensions"):
            counts["state_signature_dimension_count"] += 1
            counts["maximum_state_signature_dimension_count"] = max(
                counts["maximum_state_signature_dimension_count"], item_count
            )
            self._check(
                "state_signature_dimension_count",
                counts["state_signature_dimension_count"],
                path=path,
            )
            self._check(
                "maximum_state_signature_dimension_count", item_count, path=path
            )
            return
        if relative_path == (
            "*",
            "output_frontier",
            "materialized_frontier",
            "ordered_state_frontiers",
        ):
            counts["frontier_state_entry_count"] += 1
            self._check(
                "frontier_state_entry_count",
                counts["frontier_state_entry_count"],
                path=path,
            )
            return
        if relative_path == (
            "*",
            "output_frontier",
            "materialized_frontier",
            "ordered_state_frontiers",
            "*",
            "ordered_length_bitmap_runs",
        ):
            counts["frontier_bitmap_run_count"] += 1
            self._check(
                "frontier_bitmap_run_count",
                counts["frontier_bitmap_run_count"],
                path=path,
            )
            return
        if relative_path == (
            "*",
            "derivation",
            "ordered_choice_coordinate_plan_ids",
        ):
            counts["component_choice_coordinate_count"] += 1
            self._check(
                "component_choice_coordinate_count",
                counts["component_choice_coordinate_count"],
                path=path,
            )
            return
        if "derivation" in relative_path and field_name in {
            "ordered_catalog_entries",
            "ordered_mapping_records",
            "ordered_scalar_prefix_records",
            "ordered_primitive_prefix_records",
            "ordered_lex_interval_records",
            "ordered_state_records",
        }:
            counts["state_catalog_entry_count"] += 1
            self._check(
                "state_catalog_entry_count",
                counts["state_catalog_entry_count"],
                path=path,
            )


def _decode_bounded_json_member_name(token: bytes) -> str:
    _require(
        len(token) >= 2 and token[0] == token[-1] == ord('"'),
        "JSON object member token differs",
    )
    _require(len(token) <= 512, "JSON object member name reaches lexical key cap")
    result: list[str] = []
    position = 1
    chunk_start = position
    terminal = len(token) - 1
    simple_escapes = {
        ord('"'): '"',
        ord("\\"): "\\",
        ord("/"): "/",
        ord("b"): "\b",
        ord("f"): "\f",
        ord("n"): "\n",
        ord("r"): "\r",
        ord("t"): "\t",
    }
    while position < terminal:
        octet = token[position]
        if octet != ord("\\"):
            _require(octet >= 0x20, "JSON member name has an unescaped control")
            position += 1
            continue
        if chunk_start < position:
            try:
                result.append(
                    token[chunk_start:position].decode("utf-8", errors="strict")
                )
            except UnicodeDecodeError as exc:
                raise MaximumProtocolValidationError(
                    "JSON member name is not UTF-8"
                ) from exc
        _require(position + 1 < terminal, "JSON member-name escape is truncated")
        escape = token[position + 1]
        if escape in simple_escapes:
            result.append(simple_escapes[escape])
            position += 2
            chunk_start = position
            continue
        _require(escape == ord("u"), "JSON member-name escape differs")
        _require(
            position + 6 <= terminal, "JSON member-name Unicode escape is truncated"
        )
        digits = token[position + 2 : position + 6]
        _require(
            re.fullmatch(rb"[0-9A-Fa-f]{4}", digits) is not None,
            "JSON member-name Unicode escape differs",
        )
        codepoint = int(digits, 16)
        position += 6
        if 0xD800 <= codepoint <= 0xDBFF:
            _require(
                position + 6 <= terminal
                and token[position : position + 2] == b"\\u"
                and re.fullmatch(rb"[0-9A-Fa-f]{4}", token[position + 2 : position + 6])
                is not None,
                "JSON member-name surrogate pair differs",
            )
            low = int(token[position + 2 : position + 6], 16)
            _require(
                0xDC00 <= low <= 0xDFFF,
                "JSON member-name low surrogate differs",
            )
            codepoint = 0x10000 + ((codepoint - 0xD800) << 10) + (low - 0xDC00)
            position += 6
        else:
            _require(
                not 0xDC00 <= codepoint <= 0xDFFF,
                "JSON member-name contains a lone low surrogate",
            )
        result.append(chr(codepoint))
        chunk_start = position
    if chunk_start < terminal:
        try:
            result.append(token[chunk_start:terminal].decode("utf-8", errors="strict"))
        except UnicodeDecodeError as exc:
            raise MaximumProtocolValidationError(
                "JSON member name is not UTF-8"
            ) from exc
    return "".join(result)


def _iter_json_lexical_tokens(raw: bytes):  # type: ignore[no-untyped-def]
    position = 0
    whitespace = {0x09, 0x0A, 0x0D, 0x20}
    punctuation = {ord(item) for item in "{}[],:"}
    while position < len(raw):
        octet = raw[position]
        if octet in whitespace:
            position += 1
            continue
        if octet in punctuation:
            yield chr(octet), position, position + 1
            position += 1
            continue
        if octet == ord('"'):
            start = position
            position += 1
            escaped = False
            while position < len(raw):
                current = raw[position]
                if escaped:
                    escaped = False
                elif current == ord("\\"):
                    escaped = True
                elif current == ord('"'):
                    position += 1
                    yield "STRING", start, position
                    break
                elif current < 0x20:
                    raise MaximumProtocolValidationError(
                        "JSON contains an unescaped control octet"
                    )
                position += 1
            else:
                raise MaximumProtocolValidationError("JSON string is unterminated")
            continue
        start = position
        while (
            position < len(raw)
            and raw[position] not in whitespace
            and raw[position] not in punctuation
            and raw[position] != ord('"')
        ):
            position += 1
        _require(position > start, "JSON lexical token differs")
        yield "ATOM", start, position


def _validate_json_lexical_atom(token: bytes) -> None:
    if token in {b"null", b"true", b"false"}:
        return
    _require(
        re.fullmatch(rb"-?(0|[1-9][0-9]*)", token) is not None,
        "JSON lexical scalar is not a canonical integer/null/boolean",
    )
    digits = token[1:] if token.startswith(b"-") else token
    _require(len(digits) <= 16, "JSON lexical integer exceeds digit cap")
    parsed = int(token, 10)
    _require(
        -SAFE_INTEGER_MAXIMUM <= parsed <= SAFE_INTEGER_MAXIMUM,
        "JSON lexical integer is outside the safe-I-JSON domain",
    )


def _scan_json_resource_structure(
    raw: bytes,
    *,
    limits: Mapping[str, int],
    label: str,
    path_profile: str = LEXICAL_ANY_CERTIFICATE_PROFILE,
    expected_pilot_phase: str | None = None,
) -> dict[tuple[str, ...], dict[str, int]]:
    """Enforce directly observable proof limits before whole-object decoding."""

    observer = _LexicalProofResourceObserver(
        limits,
        path_profile=path_profile,
        expected_pilot_phase=expected_pilot_phase,
    )
    frames: list[_JsonLexicalFrame] = []
    active_certificate_frames: list[_JsonLexicalFrame] = []
    root_state = "VALUE"

    def begin_value(path: tuple[str, ...], token: str) -> None:
        nonlocal root_state
        if token == "{":
            frame = _JsonLexicalFrame(
                kind="OBJECT",
                path=path,
                state="KEY_OR_END",
                is_certificate=observer.is_certificate_anchor(path),
            )
            frames.append(frame)
            if frame.is_certificate:
                active_certificate_frames.append(frame)
        elif token == "[":
            frames.append(
                _JsonLexicalFrame(kind="ARRAY", path=path, state="FIRST_VALUE_OR_END")
            )
        else:
            _require(token in {"STRING", "ATOM"}, f"{label} value token differs")
        if not frames or len(frames) == 1:
            root_state = "DONE"

    def close_frame() -> None:
        frame = frames.pop()
        if frame.is_certificate:
            _require(
                bool(active_certificate_frames)
                and active_certificate_frames[-1] is frame,
                f"{label} lexical certificate stack differs",
            )
            observer.observe_certificate_compact(frame.path, frame.compact_octets)
            active_certificate_frames.pop()

    for token, start, end in _iter_json_lexical_tokens(raw):
        for certificate_frame in active_certificate_frames:
            certificate_frame.compact_octets += end - start
            _require(
                certificate_frame.compact_octets <= SAFE_INTEGER_MAXIMUM,
                f"{label} lexical certificate length exceeds safe arithmetic",
            )
        if token == "ATOM":
            _validate_json_lexical_atom(raw[start:end])
        if not frames:
            _require(root_state == "VALUE", f"{label} has trailing lexical content")
            begin_value((), token)
            continue
        frame = frames[-1]
        if frame.kind == "OBJECT":
            if frame.state == "KEY_OR_END":
                if token == "}":
                    close_frame()
                    continue
                _require(token == "STRING", f"{label} object member name differs")
                member_name = _decode_bounded_json_member_name(raw[start:end])
                _require(
                    frame.seen_keys is not None and member_name not in frame.seen_keys,
                    f"{label} duplicate lexical object member: {member_name}",
                )
                frame.seen_keys.add(member_name)
                frame.pending_key = member_name
                frame.state = "COLON"
                continue
            if frame.state == "COLON":
                _require(token == ":", f"{label} object member colon differs")
                frame.state = "VALUE"
                continue
            if frame.state == "VALUE":
                _require(frame.pending_key is not None, f"{label} object key is absent")
                child_path = (*frame.path, frame.pending_key)
                frame.pending_key = None
                frame.state = "COMMA_OR_END"
                if token in {"STRING", "ATOM"}:
                    observer.observe_scalar(
                        child_path,
                        token_kind=token,
                        token=raw[start:end],
                    )
                begin_value(child_path, token)
                continue
            _require(frame.state == "COMMA_OR_END", f"{label} object state differs")
            if token == "}":
                close_frame()
            else:
                _require(token == ",", f"{label} object separator differs")
                frame.state = "KEY_OR_END"
            continue

        if frame.state in {"FIRST_VALUE_OR_END", "VALUE"}:
            if token == "]" and frame.state == "FIRST_VALUE_OR_END":
                close_frame()
                continue
            frame.item_count += 1
            observer.observe_array_item(frame.path, frame.item_count)
            frame.state = "COMMA_OR_END"
            begin_value((*frame.path, f"[{frame.item_count - 1}]"), token)
            continue
        _require(frame.state == "COMMA_OR_END", f"{label} array state differs")
        if token == "]":
            close_frame()
        else:
            _require(token == ",", f"{label} array separator differs")
            frame.state = "VALUE"

    _require(root_state == "DONE" and not frames, f"{label} lexical JSON is incomplete")
    return observer.certificate_counts


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        _require(key not in result, f"duplicate JSON key is forbidden: {key}")
        result[key] = value
    return result


def _parse_integer(value: str) -> int:
    _require(len(value.lstrip("-")) <= 16, "JSON integer exceeds digit cap")
    parsed = int(value, 10)
    _require(
        -SAFE_INTEGER_MAXIMUM <= parsed <= SAFE_INTEGER_MAXIMUM,
        "JSON integer is outside the safe-I-JSON domain",
    )
    return parsed


def _parse_canonical_uint128_text(value: Any, *, label: str) -> int:
    _require(
        type(value) is str and re.fullmatch(r"0|[1-9][0-9]{0,38}", value) is not None,
        f"{label} is not canonical unsigned-128 decimal text",
    )
    parsed = 0
    for character in value:
        digit = ord(character) - ord("0")
        _require(
            parsed <= (UINT128_MAXIMUM - digit) // 10,
            f"{label} exceeds checked UInt128",
        )
        parsed = parsed * 10 + digit
    return parsed


def _reject_float(value: str) -> Any:
    raise MaximumProtocolValidationError(f"JSON float is forbidden: {value}")


def _reject_constant(value: str) -> Any:
    raise MaximumProtocolValidationError(f"non-finite JSON is forbidden: {value}")


def _validate_json_scalars(value: Any) -> None:
    stack = [value]
    while stack:
        current = stack.pop()
        if type(current) is dict:
            stack.extend(current.keys())
            stack.extend(current.values())
        elif type(current) is list:
            stack.extend(current)
        elif type(current) is str:
            _require(
                not any(0xD800 <= ord(character) <= 0xDFFF for character in current),
                "JSON text contains a surrogate code point",
            )
        else:
            _require(
                current is None
                or type(current) is bool
                or (
                    type(current) is int
                    and -SAFE_INTEGER_MAXIMUM <= current <= SAFE_INTEGER_MAXIMUM
                ),
                "JSON scalar is outside the controlled I-JSON subset",
            )


def _decode_pretty_json(
    raw: bytes,
    *,
    label: str,
    lexical_resource_limits: Mapping[str, int] | None = None,
    lexical_path_profile: str = LEXICAL_ANY_CERTIFICATE_PROFILE,
    expected_pilot_phase: str | None = None,
    lexical_summary_out: dict[tuple[str, ...], dict[str, int]] | None = None,
) -> dict[str, Any]:
    _scan_json_structure(raw)
    if lexical_resource_limits is not None:
        lexical_summary = _scan_json_resource_structure(
            raw,
            limits=lexical_resource_limits,
            label=label,
            path_profile=lexical_path_profile,
            expected_pilot_phase=expected_pilot_phase,
        )
        if lexical_summary_out is not None:
            lexical_summary_out.clear()
            lexical_summary_out.update(lexical_summary)
    try:
        value = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_strict_object,
            parse_int=_parse_integer,
            parse_float=_reject_float,
            parse_constant=_reject_constant,
        )
    except (
        MaximumProtocolValidationError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        RecursionError,
        ValueError,
    ) as exc:
        if isinstance(exc, MaximumProtocolValidationError):
            raise
        raise MaximumProtocolValidationError(
            f"{label} is not strict canonical JSON"
        ) from exc
    _require(type(value) is dict, f"{label} root must be an object")
    _validate_json_scalars(value)
    _require(_pretty_bytes(value) == raw, f"{label} is not canonical pretty JSON")
    return value


def _decode_compact_json_value(raw: bytes, *, label: str) -> Any:
    """Decode exactly one strict, duplicate-free compact-canonical JSON value."""

    _scan_json_structure(raw)
    try:
        value = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_strict_object,
            parse_int=_parse_integer,
            parse_float=_reject_float,
            parse_constant=_reject_constant,
        )
    except (
        MaximumProtocolValidationError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        RecursionError,
        ValueError,
    ) as exc:
        if isinstance(exc, MaximumProtocolValidationError):
            raise
        raise MaximumProtocolValidationError(
            f"{label} is not strict canonical JSON"
        ) from exc
    _validate_json_scalars(value)
    _require(_canonical_bytes(value) == raw, f"{label} is not canonical compact JSON")
    return value


def _decode_compact_json(raw: bytes, *, label: str) -> dict[str, Any]:
    value = _decode_compact_json_value(raw, label=label)
    _require(type(value) is dict, f"{label} root must be an object")
    return value


def _load_json(
    path: Path,
    *,
    repository_root: Path,
    maximum_octets: int,
    expected_octets: int | None = None,
    expected_sha256: str | None = None,
    label: str,
    lexical_resource_limits: Mapping[str, int] | None = None,
    lexical_path_profile: str = LEXICAL_ANY_CERTIFICATE_PROFILE,
    expected_pilot_phase: str | None = None,
    lexical_summary_out: dict[tuple[str, ...], dict[str, int]] | None = None,
) -> tuple[dict[str, Any], FrozenFile]:
    frozen = _secure_bounded_read(
        path,
        base=repository_root,
        maximum_octets=maximum_octets,
        expected_octets=expected_octets,
        expected_sha256=expected_sha256,
    )
    return (
        _decode_pretty_json(
            frozen.raw,
            label=label,
            lexical_resource_limits=lexical_resource_limits,
            lexical_path_profile=lexical_path_profile,
            expected_pilot_phase=expected_pilot_phase,
            lexical_summary_out=lexical_summary_out,
        ),
        frozen,
    )


def _derive_self_reference_value_schema_index(
    registry: dict[str, Any],
) -> Mapping[str, dict[str, Any]]:
    """Derive one non-null OBJECT_REF locator anchor for every frozen type."""

    descriptors = _require_array(
        registry["ordered_external_type_descriptors"],
        label="self-reference external type descriptors",
        exact_length=52,
    )
    type_names: list[str] = []
    for position, descriptor in enumerate(descriptors, 1):
        type_name = descriptor.get("type_name") if type(descriptor) is dict else None
        _require(
            type(type_name) is str and bool(type_name),
            f"self-reference descriptor {position} type name differs",
        )
        type_names.append(type_name)
    _require(
        len(set(type_names)) == len(type_names),
        "self-reference descriptor type names are not unique",
    )

    derived: dict[str, dict[str, Any]] = {}
    for type_name in type_names:
        payload = {
            "schema_kind": "OBJECT_REF",
            "nullable": False,
            "boolean_literal": None,
            "integer_minimum": None,
            "integer_maximum": None,
            "text_language_id": None,
            "array_minimum_items": None,
            "array_maximum_items": None,
            "array_item_value_schema_id": None,
            "referenced_type_name": type_name,
        }
        derived[type_name] = {
            **payload,
            "value_schema_id": _semantic_id(VALUE_SCHEMA_DOMAIN, payload),
        }

    catalog = _require_array(
        registry["value_schema_catalog"],
        label="self-reference value-schema catalog",
        maximum_length=1_000_000,
    )
    catalog_self_types: set[str] = set()
    for position, schema_value in enumerate(catalog, 1):
        schema = _require_exact_keys(
            schema_value,
            VALUE_SCHEMA_KEYS,
            label=f"self-reference value schema {position}",
        )
        if schema["schema_kind"] != "OBJECT_REF":
            continue
        referenced_type_name = schema["referenced_type_name"]
        _require(
            referenced_type_name in derived,
            f"self-reference value schema {position} names an unknown type",
        )
        if schema["nullable"] is False:
            _require(
                referenced_type_name not in catalog_self_types
                and schema == derived[referenced_type_name],
                f"self-reference value schema {position} differs",
            )
            catalog_self_types.add(referenced_type_name)
    return MappingProxyType(derived)


def _validate_registry(registry: dict[str, Any]) -> None:
    _require_exact_keys(registry, REGISTRY_ROOT_KEYS, label="structural registry")
    _require(
        registry["canonicalization_version"] == CANONICALIZATION_VERSION,
        "registry canonicalization differs",
    )
    _require(
        registry["measurement_schema_version"] == MEASUREMENT_SCHEMA_VERSION,
        "registry measurement schema differs",
    )
    _require(registry["record_domain"] == REGISTRY_DOMAIN, "registry domain differs")
    payload = {name: registry[name] for name in REGISTRY_IDENTITY_PAYLOAD_MEMBERS}
    _require(
        _semantic_id(REGISTRY_DOMAIN, payload)
        == registry["external_schema_registry_id"],
        "registry semantic identity differs",
    )
    _require(
        registry["external_schema_registry_id"] == REGISTRY_ID,
        "registry identity is not frozen",
    )
    descriptors = _require_array(
        registry["ordered_external_type_descriptors"],
        label="external type descriptors",
        exact_length=52,
    )
    _require(
        registry["external_type_descriptor_count"] == 52
        and registry["schema_graph_node_count"] == 52,
        "registry 52-node counts differ",
    )
    _require(
        Counter(item["type_form"] for item in descriptors)
        == Counter({"RECORD": 49, "TAGGED_UNION": 3}),
        "registry 49-record/three-union partition differs",
    )
    _derive_self_reference_value_schema_index(registry)


def _validate_literal_authority(value: dict[str, Any]) -> None:
    _require_exact_keys(value, LITERAL_AUTHORITY_KEYS, label="literal authority")
    _require(
        value["canonicalization_version"] == CANONICALIZATION_VERSION
        and value["measurement_schema_version"] == MEASUREMENT_SCHEMA_VERSION,
        "literal-authority versions differ",
    )
    selected = _require_exact_keys(
        value["selected_literal_canonical_sha256"],
        frozenset(
            {"marker_contract", "operation_counter_schema", "target_field_registry"}
        ),
        label="selected literal hashes",
    )
    for name, digest in selected.items():
        _require_sha256(digest, label=f"selected literal hash {name}")
        _require(
            _sha256(_canonical_bytes(value[name])) == digest,
            f"selected literal hash differs: {name}",
        )
    payload = {
        name: item
        for name, item in value.items()
        if name != "rule_literal_authority_sha256"
    }
    _require(
        _semantic_id(LITERAL_AUTHORITY_DOMAIN, payload)
        == value["rule_literal_authority_sha256"]
        == LITERAL_AUTHORITY_SEMANTIC_ID,
        "literal-authority semantic identity differs",
    )


def _validate_inventory(
    inventory: dict[str, Any],
    *,
    registry: dict[str, Any],
    literals: dict[str, Any],
) -> None:
    _require_exact_keys(inventory, INVENTORY_ROOT_KEYS, label="V3 inventory")
    _require(
        inventory["schema_version"] == "riskyieldmm.raw_v8_step2_inventory.v3",
        "inventory schema version differs",
    )
    _require(
        inventory["external_schema_registry_v2"] == registry,
        "inventory embedded registry differs from standalone authority",
    )
    _validate_local_shutdown_relation_authority(inventory, registry=registry)
    for name in (
        "marker_contract",
        "operation_counter_schema",
        "target_field_registry",
    ):
        _require(
            inventory[name] == literals[name],
            f"inventory frozen literal differs: {name}",
        )
    unsigned = dict(inventory)
    semantic_identity = unsigned.pop("inventory_sha256", None)
    _require(
        _is_sha256(semantic_identity)
        and _sha256(_canonical_bytes(unsigned)) == semantic_identity
        and semantic_identity == INVENTORY_SEMANTIC_ID,
        "inventory semantic identity differs",
    )


def _validate_local_shutdown_relation_authority(
    inventory: dict[str, Any],
    *,
    registry: dict[str, Any],
) -> None:
    relations = inventory["operation_contracts"][
        "local_shutdown_intrinsic_limit_relations"
    ]
    _require(
        type(relations) is list
        and tuple(relations) == LOCAL_SHUTDOWN_INTRINSIC_RELATION_IDS,
        "local-shutdown intrinsic relation authority differs",
    )
    matching_rules = [
        item
        for item in registry["ordered_cross_field_rule_descriptors"]
        if item.get("rule_id") == LOCAL_SHUTDOWN_INTRINSIC_RULE_ID
    ]
    _require(
        len(matching_rules) == 1,
        "local-shutdown intrinsic rule authority differs",
    )
    nodes = matching_rules[0]["ordered_expression_nodes"]
    for relation_ordinal, (position, operator, operands) in enumerate(
        LOCAL_SHUTDOWN_INTRINSIC_COMPARISON_NODES,
        1,
    ):
        _require(
            position <= len(nodes),
            f"local-shutdown relation {relation_ordinal} node is absent",
        )
        node = nodes[position - 1]
        _require(
            node.get("expression_position") == position
            and node.get("operator") == operator
            and tuple(node.get("ordered_operand_positions", ())) == operands,
            f"local-shutdown relation {relation_ordinal} expression differs",
        )


def _profile_payload(profile: dict[str, Any]) -> dict[str, Any]:
    return {
        name: value
        for name, value in profile.items()
        if name != "maximum_constraint_scope_profile_id"
    }


def _profile_id(profile: dict[str, Any]) -> str:
    return _semantic_id(PROFILE_DOMAIN, _profile_payload(profile))


def _fixture_profile(inventory: dict[str, Any]) -> dict[str, Any]:
    spec = inventory["fixture_records"]["operation_specs"]["LOCAL_SHUTDOWN"]
    profile: dict[str, Any] = {
        "application_schedule_formula": (
            "OUTER_RESULT_SIGNED_SPEC_SINGLE_APPLICATION_V1"
        ),
        "checkpoint_binding_status": None,
        "checkpoint_binding_unavailable_reason": None,
        "checkpoint_field_unavailable_reason": None,
        "checkpoint_outcome": None,
        "checkpoint_selector_entry_id": None,
        "checkpoint_selector_id": None,
        "constraint_scope": "FROZEN_FIXTURE",
        "expected_checkpoint_marker_kind": None,
        "expected_occurrence_index_within_kind": None,
        "measured_type_name": "CapacityMeasurementOperationResultEvidence",
        "operation_kind": "LOCAL_SHUTDOWN",
        "ordered_admissible_root_families": [],
        "ordered_source_authority_ids": [spec["operation_spec_id"]],
        "ordered_source_authority_pointers": [
            "/fixture_records/operation_specs/LOCAL_SHUTDOWN"
        ],
        "profile_kind": "OUTER_RESULT_BOUNDARY_FIXTURE",
        "profile_position": 3,
        "selector_catalog_name": None,
        "selector_catalog_position": None,
        "selector_position": None,
    }
    profile["maximum_constraint_scope_profile_id"] = _profile_id(profile)
    return profile


def _checkpoint_profile(
    inventory: dict[str, Any], *, position: int, outcome: str
) -> dict[str, Any]:
    selector_catalog = inventory["checkpoint_selector_catalog"]
    _require(
        type(selector_catalog) is list and len(selector_catalog) >= 4,
        "selector catalog differs",
    )
    catalog = selector_catalog[3]
    selector = catalog["selector"]
    entries = selector["ordered_entries"]
    _require(type(entries) is list and len(entries) == 64, "max64 selector differs")
    entry = entries[63]
    _require(
        catalog["catalog_name"] == "INGRESS_MAX64_PARSER_UNITS"
        and selector["selector_length"] == 64
        and entry["selector_position"] == 64
        and entry["occurrence_index_within_kind"] == 64,
        "max64 selector coordinate differs",
    )
    if outcome == "EXACT_MARKER":
        binding_status = "EXACT_MARKER"
        unavailable_reason = None
        field_reason = None
    elif outcome == "TARGET_BOUNDARY_NOT_REACHED":
        binding_status = "UNAVAILABLE_TARGET_BOUNDARY_NOT_REACHED"
        unavailable_reason = outcome
        field_reason = "CHECKPOINT_PLACEHOLDER_TARGET_BOUNDARY_NOT_REACHED"
    else:
        binding_status = "UNAVAILABLE_MARKER_OBSERVER_FAILURE"
        unavailable_reason = outcome
        field_reason = f"CHECKPOINT_PLACEHOLDER_{outcome}"
    target_id = inventory["target_field_registry"]["target_field_registry_id"]
    marker_id = inventory["marker_contract"]["marker_contract_id"]
    root_family = {
        "checkpoint_selector_id": selector["checkpoint_selector_id"],
        "observation_count": 67,
        "ordered_instrumentation_mode_attempt_presence_pairs": [["ON", "NON_NULL"]],
        "ordered_measured_observation_roles": ["STABLE_CHECKPOINT"],
        "role_sequence_formula": "ORDINARY_BEFORE_CHECKPOINTS_AFTER_AGGREGATE_V1",
        "root_family_kind": "ORDINARY_SELECTOR_BOUND",
        "selector_catalog_name": catalog["catalog_name"],
        "selector_catalog_position": 4,
        "selector_length": 64,
        "selector_present": True,
    }
    _require_exact_keys(root_family, ROOT_FAMILY_KEYS, label="rebuilt root family")
    profile: dict[str, Any] = {
        "application_schedule_formula": (
            "SELECTOR_PRESENT_2N_PLUS_3_CALLS_187N_PLUS_2_EVALS_1872N_PLUS_7_NODES_V1"
        ),
        "checkpoint_binding_status": binding_status,
        "checkpoint_binding_unavailable_reason": unavailable_reason,
        "checkpoint_field_unavailable_reason": field_reason,
        "checkpoint_outcome": outcome,
        "checkpoint_selector_entry_id": entry["checkpoint_selector_entry_id"],
        "checkpoint_selector_id": selector["checkpoint_selector_id"],
        "constraint_scope": "FROZEN_ROOT_APPLICATION",
        "expected_checkpoint_marker_kind": entry["checkpoint_marker_kind"],
        "expected_occurrence_index_within_kind": entry["occurrence_index_within_kind"],
        "measured_type_name": "TargetObservationV2",
        "operation_kind": "INGRESS",
        "ordered_admissible_root_families": [root_family],
        "ordered_source_authority_ids": [
            target_id,
            marker_id,
            selector["checkpoint_selector_id"],
        ],
        "ordered_source_authority_pointers": [
            "/target_field_registry",
            "/marker_contract",
            "/checkpoint_selector_catalog/3/selector",
        ],
        "profile_kind": "CHECKPOINT_ROOT_COORDINATE",
        "profile_position": position,
        "selector_catalog_name": catalog["catalog_name"],
        "selector_catalog_position": 4,
        "selector_position": 64,
    }
    profile["maximum_constraint_scope_profile_id"] = _profile_id(profile)
    return profile


def _validate_selected_profiles(inventory: dict[str, Any]) -> dict[int, dict[str, Any]]:
    profiles = inventory["operation_contracts"][
        "maximum_constraint_scope_profile_catalog"
    ]
    _require(type(profiles) is list and len(profiles) == 408, "profile count differs")
    for position, profile in enumerate(profiles, 1):
        _require_exact_keys(profile, PROFILE_KEYS, label=f"profile {position}")
        _require(profile["profile_position"] == position, "profile position differs")
        _require(
            _profile_id(profile) == profile["maximum_constraint_scope_profile_id"],
            "profile identity differs",
        )
    expected = {
        3: _fixture_profile(inventory),
        369: _checkpoint_profile(
            inventory, position=369, outcome=CHECKPOINT_OUTCOMES[0]
        ),
        370: _checkpoint_profile(
            inventory, position=370, outcome=CHECKPOINT_OUTCOMES[1]
        ),
        371: _checkpoint_profile(
            inventory, position=371, outcome=CHECKPOINT_OUTCOMES[2]
        ),
        372: _checkpoint_profile(
            inventory, position=372, outcome=CHECKPOINT_OUTCOMES[3]
        ),
        373: _checkpoint_profile(
            inventory, position=373, outcome=CHECKPOINT_OUTCOMES[4]
        ),
    }
    for position, rebuilt in expected.items():
        _require(
            rebuilt == profiles[position - 1],
            f"independently rebuilt profile {position} differs",
        )
        _require(
            rebuilt["maximum_constraint_scope_profile_id"]
            == EXPECTED_SELECTED_PROFILE_IDS[position],
            f"profile {position} is not the frozen identity",
        )
    _derive_all_profile_scope_hierarchies(
        inventory,
        label="maximum constraint-scope profile authority",
    )
    return expected


def _scope_root_family(
    *,
    root_family_kind: str,
    mode_attempt_pairs: tuple[tuple[str, str], ...],
    selector_catalog_position: int | None,
    selector_catalog_name: str | None,
    checkpoint_selector_id: str | None,
    selector_length: int,
    observation_count: int,
    role_sequence_formula: str,
    measured_roles: tuple[str, ...],
    selector_present: bool,
) -> dict[str, Any]:
    family = {
        "root_family_kind": root_family_kind,
        "ordered_instrumentation_mode_attempt_presence_pairs": [
            list(pair) for pair in mode_attempt_pairs
        ],
        "selector_catalog_position": selector_catalog_position,
        "selector_catalog_name": selector_catalog_name,
        "checkpoint_selector_id": checkpoint_selector_id,
        "selector_length": selector_length,
        "observation_count": observation_count,
        "role_sequence_formula": role_sequence_formula,
        "ordered_measured_observation_roles": list(measured_roles),
        "selector_present": selector_present,
    }
    _require_exact_keys(family, ROOT_FAMILY_KEYS, label="derived scope root family")
    return family


def _expected_scope_profile_catalog(
    inventory: dict[str, Any],
    *,
    label: str,
) -> tuple[dict[str, Any], ...]:
    """Independently rebuild the complete ordered 408-profile authority."""

    selectors = _require_array(
        inventory["checkpoint_selector_catalog"],
        label=f"{label} selector catalog",
        exact_length=9,
    )
    specs = inventory["fixture_records"]["operation_specs"]
    target_registry_id = _require_sha256(
        inventory["target_field_registry"]["target_field_registry_id"],
        label=f"{label} target-field registry ID",
    )
    marker_contract_id = _require_sha256(
        inventory["marker_contract"]["marker_contract_id"],
        label=f"{label} marker-contract ID",
    )
    profiles: list[dict[str, Any]] = []

    def append_profile(**payload: Any) -> None:
        complete_payload = {"profile_position": len(profiles) + 1, **payload}
        profile = {
            **complete_payload,
            "maximum_constraint_scope_profile_id": _semantic_id(
                PROFILE_DOMAIN,
                complete_payload,
            ),
        }
        _require_exact_keys(
            profile,
            PROFILE_KEYS,
            label=f"{label} rebuilt profile {len(profiles) + 1}",
        )
        profiles.append(profile)

    null_checkpoint_fields = {
        "selector_catalog_position": None,
        "selector_catalog_name": None,
        "checkpoint_selector_id": None,
        "checkpoint_selector_entry_id": None,
        "expected_checkpoint_marker_kind": None,
        "expected_occurrence_index_within_kind": None,
        "selector_position": None,
        "checkpoint_outcome": None,
        "checkpoint_binding_status": None,
        "checkpoint_binding_unavailable_reason": None,
        "checkpoint_field_unavailable_reason": None,
    }
    for operation_kind in SCOPE_OPERATION_KINDS:
        spec = specs[operation_kind]
        append_profile(
            profile_kind="OUTER_RESULT_BOUNDARY_FIXTURE",
            constraint_scope="FROZEN_FIXTURE",
            measured_type_name="CapacityMeasurementOperationResultEvidence",
            operation_kind=operation_kind,
            ordered_source_authority_pointers=[
                f"/fixture_records/operation_specs/{operation_kind}"
            ],
            ordered_source_authority_ids=[spec["operation_spec_id"]],
            ordered_admissible_root_families=[],
            application_schedule_formula=(
                "OUTER_RESULT_SIGNED_SPEC_SINGLE_APPLICATION_V1"
            ),
            **null_checkpoint_fields,
        )

    startup_family = _scope_root_family(
        root_family_kind="STARTUP_RECOVERY_ONE",
        mode_attempt_pairs=(("OFF", "NULL"), ("ON", "NULL")),
        selector_catalog_position=None,
        selector_catalog_name=None,
        checkpoint_selector_id=None,
        selector_length=0,
        observation_count=1,
        role_sequence_formula="STARTUP_RECOVERY_ONE_V1",
        measured_roles=("STARTUP_RECOVERY",),
        selector_present=False,
    )
    selector_free_family = _scope_root_family(
        root_family_kind="ORDINARY_SELECTOR_FREE_THREE",
        mode_attempt_pairs=(
            ("OFF", "NULL"),
            ("OFF", "NON_NULL"),
            ("ON", "NULL"),
        ),
        selector_catalog_position=None,
        selector_catalog_name=None,
        checkpoint_selector_id=None,
        selector_length=0,
        observation_count=3,
        role_sequence_formula="ORDINARY_BEFORE_CHECKPOINTS_AFTER_AGGREGATE_V1",
        measured_roles=(
            "BEFORE_OPERATION",
            "AFTER_OPERATION",
            "OPERATION_AGGREGATE",
        ),
        selector_present=False,
    )
    selectors_by_operation: dict[str, list[tuple[int, dict[str, Any]]]] = {
        operation_kind: [] for operation_kind in SCOPE_OPERATION_KINDS
    }
    for catalog_position, catalog in enumerate(selectors, 1):
        _require(type(catalog) is dict, f"{label} selector record differs")
        selector = catalog["selector"]
        operation_kind = selector["operation_kind"]
        _require(
            operation_kind in selectors_by_operation,
            f"{label} selector operation differs",
        )
        selector_length = _require_integer(
            selector["selector_length"],
            label=f"{label} selector length {catalog_position}",
            maximum=64,
        )
        entries = _require_array(
            selector["ordered_entries"],
            label=f"{label} selector entries {catalog_position}",
            exact_length=selector_length,
        )
        _require(
            [entry["selector_position"] for entry in entries]
            == list(range(1, selector_length + 1)),
            f"{label} selector entry positions {catalog_position} differ",
        )
        selectors_by_operation[operation_kind].append((catalog_position, catalog))

    for operation_kind in SCOPE_OPERATION_KINDS:
        pointers = ["/target_field_registry", "/marker_contract"]
        identities = [target_registry_id, marker_contract_id]
        families = [startup_family, selector_free_family]
        for catalog_position, catalog in selectors_by_operation[operation_kind]:
            selector = catalog["selector"]
            selector_length = selector["selector_length"]
            pointer = f"/checkpoint_selector_catalog/{catalog_position - 1}/selector"
            pointers.append(pointer)
            identities.append(selector["checkpoint_selector_id"])
            families.append(
                _scope_root_family(
                    root_family_kind="ORDINARY_SELECTOR_BOUND",
                    mode_attempt_pairs=(("ON", "NON_NULL"),),
                    selector_catalog_position=catalog_position,
                    selector_catalog_name=catalog["catalog_name"],
                    checkpoint_selector_id=selector["checkpoint_selector_id"],
                    selector_length=selector_length,
                    observation_count=selector_length + 3,
                    role_sequence_formula=(
                        "ORDINARY_BEFORE_CHECKPOINTS_AFTER_AGGREGATE_V1"
                    ),
                    measured_roles=(
                        "BEFORE_OPERATION",
                        "AFTER_OPERATION",
                        "OPERATION_AGGREGATE",
                    ),
                    selector_present=True,
                )
            )
        append_profile(
            profile_kind="NON_CHECKPOINT_ROOT_FAMILY",
            constraint_scope="FROZEN_ROOT_APPLICATION",
            measured_type_name="TargetObservationV2",
            operation_kind=operation_kind,
            ordered_source_authority_pointers=pointers,
            ordered_source_authority_ids=identities,
            ordered_admissible_root_families=families,
            application_schedule_formula=(
                "FINITE_UNION_OF_LISTED_ROOT_FAMILY_SCHEDULES_V1"
            ),
            **null_checkpoint_fields,
        )

    for catalog_position, catalog in enumerate(selectors, 1):
        selector = catalog["selector"]
        selector_length = selector["selector_length"]
        selector_pointer = (
            f"/checkpoint_selector_catalog/{catalog_position - 1}/selector"
        )
        for entry in selector["ordered_entries"]:
            family = _scope_root_family(
                root_family_kind="ORDINARY_SELECTOR_BOUND",
                mode_attempt_pairs=(("ON", "NON_NULL"),),
                selector_catalog_position=catalog_position,
                selector_catalog_name=catalog["catalog_name"],
                checkpoint_selector_id=selector["checkpoint_selector_id"],
                selector_length=selector_length,
                observation_count=selector_length + 3,
                role_sequence_formula=(
                    "ORDINARY_BEFORE_CHECKPOINTS_AFTER_AGGREGATE_V1"
                ),
                measured_roles=("STABLE_CHECKPOINT",),
                selector_present=True,
            )
            for outcome in CHECKPOINT_OUTCOMES:
                binding_status, unavailable_reason, field_reason = (
                    CHECKPOINT_OUTCOME_BINDINGS[outcome]
                )
                append_profile(
                    profile_kind="CHECKPOINT_ROOT_COORDINATE",
                    constraint_scope="FROZEN_ROOT_APPLICATION",
                    measured_type_name="TargetObservationV2",
                    operation_kind=selector["operation_kind"],
                    ordered_source_authority_pointers=[
                        "/target_field_registry",
                        "/marker_contract",
                        selector_pointer,
                    ],
                    ordered_source_authority_ids=[
                        target_registry_id,
                        marker_contract_id,
                        selector["checkpoint_selector_id"],
                    ],
                    selector_catalog_position=catalog_position,
                    selector_catalog_name=catalog["catalog_name"],
                    checkpoint_selector_id=selector["checkpoint_selector_id"],
                    checkpoint_selector_entry_id=entry["checkpoint_selector_entry_id"],
                    expected_checkpoint_marker_kind=entry["checkpoint_marker_kind"],
                    expected_occurrence_index_within_kind=entry[
                        "occurrence_index_within_kind"
                    ],
                    selector_position=entry["selector_position"],
                    checkpoint_outcome=outcome,
                    checkpoint_binding_status=binding_status,
                    checkpoint_binding_unavailable_reason=unavailable_reason,
                    checkpoint_field_unavailable_reason=field_reason,
                    ordered_admissible_root_families=[family],
                    application_schedule_formula=(
                        "SELECTOR_PRESENT_2N_PLUS_3_CALLS_187N_PLUS_2_"
                        "EVALS_1872N_PLUS_7_NODES_V1"
                    ),
                )
    _require(len(profiles) == 408, f"{label} rebuilt profile count differs")
    return tuple(profiles)


def _scope_checked_add(left: int, right: int, *, label: str) -> int:
    _require(
        type(left) is int
        and type(right) is int
        and 0 <= left <= SAFE_INTEGER_MAXIMUM
        and 0 <= right <= SAFE_INTEGER_MAXIMUM - left,
        f"{label} exceeds checked safe-integer addition",
    )
    return left + right


def _scope_profile_subject_locator(profile: dict[str, Any]) -> dict[str, Any]:
    return {
        "locator_kind": "V3_INVENTORY_POINTER",
        "record_reference_id": (
            "/operation_contracts/maximum_constraint_scope_profile_catalog/"
            f"{profile['profile_position'] - 1}"
        ),
        "root_type_name": profile["measured_type_name"],
        "root_value_schema_id": None,
        "ordered_path_steps": [],
        "transient_state_key": None,
        "transient_source_child_position": None,
        "transient_source_child_proof_node_id": None,
    }


def _scope_guard(axis_key: ScopeAxisKey, position_value: int) -> ScopeGuardSeed:
    return ScopeGuardSeed(axis_key, "EQUALS", position_value)


def _scope_axis_event(
    profile: dict[str, Any],
    *,
    axis_key: ScopeAxisKey,
    admissible_position_values: tuple[int, ...],
    guards: tuple[ScopeGuardSeed, ...],
) -> ScopePlanEvent:
    _require(
        len(admissible_position_values) >= 2,
        "synthetic scope axis has a singleton domain",
    )
    axis = SyntheticScopeAxisSeed(
        axis_key=axis_key,
        coordinate_kind=axis_key.coordinate_kind,
        subject_locator=_scope_profile_subject_locator(profile),
        ordered_admissible_position_values=admissible_position_values,
        ordered_activation_guard_seeds=guards,
    )
    return ScopePlanEvent("SYNTHETIC_AXIS", axis, None)


def _eligible_scope_ordinals(
    profile: dict[str, Any],
    family: dict[str, Any],
    *,
    observation_role: str,
    label: str,
) -> tuple[int, ...]:
    formula = family["role_sequence_formula"]
    if formula == "STARTUP_RECOVERY_ONE_V1":
        _require(
            observation_role == "STARTUP_RECOVERY"
            and family["selector_length"] == 0
            and family["observation_count"] == 1,
            f"{label} startup ordinal authority differs",
        )
        return (0,)
    _require(
        formula == "ORDINARY_BEFORE_CHECKPOINTS_AFTER_AGGREGATE_V1",
        f"{label} role-sequence formula differs",
    )
    selector_length = family["selector_length"]
    if observation_role == "BEFORE_OPERATION":
        return (0,)
    if observation_role == "AFTER_OPERATION":
        return (selector_length + 1,)
    if observation_role == "OPERATION_AGGREGATE":
        return (selector_length + 2,)
    _require(
        observation_role == "STABLE_CHECKPOINT"
        and profile["profile_kind"] == "CHECKPOINT_ROOT_COORDINATE",
        f"{label} measured role has no frozen ordinal mapping",
    )
    selector_position = _require_integer(
        profile["selector_position"],
        label=f"{label} checkpoint selector position",
        minimum=1,
        maximum=selector_length,
    )
    return (selector_position,)


def _constructed_root_context_occurrences(
    *,
    observation_count: int,
    measured_ordinal: int,
    guards: tuple[ScopeGuardSeed, ...],
) -> tuple[ConstructedContextOccurrence, ...]:
    occurrences = [
        ConstructedContextOccurrence(
            1,
            "ROOT_RECORD",
            "TargetObservationRootV2",
            None,
            guards,
        )
    ]
    for ordinal in range(observation_count):
        if ordinal == measured_ordinal:
            continue
        occurrences.append(
            ConstructedContextOccurrence(
                len(occurrences) + 1,
                "NON_WITNESS_OBSERVATION",
                "TargetObservationV2",
                ordinal,
                guards,
            )
        )
    _require(
        len(occurrences) == observation_count,
        "constructed root context occurrence count differs",
    )
    return tuple(occurrences)


def _derive_validated_profile_scope_hierarchy(
    profile: dict[str, Any],
    *,
    label: str,
) -> DerivedScopeHierarchy:
    events: list[ScopePlanEvent] = []
    cases: list[ScopeCaseSeed] = []
    context_reference_count = 0
    observation_total = 0
    invocation_total = 0
    evaluation_total = 0
    expression_total = 0
    constructed_total = 0

    if profile["profile_kind"] == "OUTER_RESULT_BOUNDARY_FIXTURE":
        invocations = tuple(
            _derive_profile_application_invocations(
                profile,
                selected_root_family=None,
                label=f"{label} fixture schedule",
            )
        )
        case = ScopeCaseSeed(
            1,
            None,
            None,
            None,
            None,
            None,
            None,
            (),
            invocations,
            (),
        )
        cases.append(case)
        events.append(ScopePlanEvent("SCOPE_CASE", None, case))
        context_reference_count = 2
        invocation_total = 1
        evaluation_total = 1
        expression_total = 3
    else:
        families = profile["ordered_admissible_root_families"]
        root_axis_key: ScopeAxisKey | None = None
        if len(families) >= 2:
            root_axis_key = ScopeAxisKey(
                profile["profile_position"],
                "ROOT_FAMILY_POSITION",
                None,
                None,
                None,
            )
            events.append(
                _scope_axis_event(
                    profile,
                    axis_key=root_axis_key,
                    admissible_position_values=tuple(range(1, len(families) + 1)),
                    guards=(),
                )
            )
        for family_position, family in enumerate(families, 1):
            family_guards = (
                (_scope_guard(root_axis_key, family_position),)
                if root_axis_key is not None
                else ()
            )
            pairs = family["ordered_instrumentation_mode_attempt_presence_pairs"]
            roles = family["ordered_measured_observation_roles"]
            mode_axis_key: ScopeAxisKey | None = None
            if len(pairs) >= 2:
                mode_axis_key = ScopeAxisKey(
                    profile["profile_position"],
                    "MODE_ATTEMPT_POSITION",
                    family_position,
                    None,
                    None,
                )
                events.append(
                    _scope_axis_event(
                        profile,
                        axis_key=mode_axis_key,
                        admissible_position_values=tuple(range(1, len(pairs) + 1)),
                        guards=family_guards,
                    )
                )
            for pair_position, pair_value in enumerate(pairs, 1):
                _require(
                    type(pair_value) is list
                    and len(pair_value) == 2
                    and all(type(item) is str for item in pair_value),
                    f"{label} mode/attempt pair differs",
                )
                pair = (pair_value[0], pair_value[1])
                pair_guards = family_guards + (
                    (_scope_guard(mode_axis_key, pair_position),)
                    if mode_axis_key is not None
                    else ()
                )
                role_axis_key: ScopeAxisKey | None = None
                if len(roles) >= 2:
                    role_axis_key = ScopeAxisKey(
                        profile["profile_position"],
                        "OBSERVATION_ROLE_POSITION",
                        family_position,
                        pair_position,
                        None,
                    )
                    events.append(
                        _scope_axis_event(
                            profile,
                            axis_key=role_axis_key,
                            admissible_position_values=tuple(range(1, len(roles) + 1)),
                            guards=pair_guards,
                        )
                    )
                for role_position, observation_role in enumerate(roles, 1):
                    role_guards = pair_guards + (
                        (_scope_guard(role_axis_key, role_position),)
                        if role_axis_key is not None
                        else ()
                    )
                    eligible_ordinals = _eligible_scope_ordinals(
                        profile,
                        family,
                        observation_role=observation_role,
                        label=(
                            f"{label} family {family_position} role {role_position}"
                        ),
                    )
                    _require(
                        tuple(sorted(set(eligible_ordinals))) == eligible_ordinals,
                        f"{label} eligible ordinals are not unique/increasing",
                    )
                    sequence_axis_key: ScopeAxisKey | None = None
                    if len(eligible_ordinals) >= 2:
                        sequence_axis_key = ScopeAxisKey(
                            profile["profile_position"],
                            "SEQUENCE_ORDINAL",
                            family_position,
                            pair_position,
                            role_position,
                        )
                        events.append(
                            _scope_axis_event(
                                profile,
                                axis_key=sequence_axis_key,
                                admissible_position_values=eligible_ordinals,
                                guards=role_guards,
                            )
                        )
                    for measured_ordinal in eligible_ordinals:
                        case_guards = role_guards + (
                            (_scope_guard(sequence_axis_key, measured_ordinal),)
                            if sequence_axis_key is not None
                            else ()
                        )
                        observation_count = family["observation_count"]
                        _require_integer(
                            measured_ordinal,
                            label=f"{label} measured ordinal",
                            maximum=observation_count - 1,
                        )
                        occurrences = _constructed_root_context_occurrences(
                            observation_count=observation_count,
                            measured_ordinal=measured_ordinal,
                            guards=case_guards,
                        )
                        invocations = tuple(
                            _derive_profile_application_invocations(
                                profile,
                                selected_root_family=family,
                                label=f"{label} scope-case schedule",
                            )
                        )
                        case = ScopeCaseSeed(
                            len(cases) + 1,
                            family_position,
                            pair_position,
                            role_position,
                            measured_ordinal,
                            pair,
                            observation_role,
                            case_guards,
                            invocations,
                            occurrences,
                        )
                        cases.append(case)
                        events.append(ScopePlanEvent("SCOPE_CASE", None, case))
                        selector_present = family["selector_present"]
                        constructed_total = _scope_checked_add(
                            constructed_total,
                            len(occurrences),
                            label=f"{label} constructed occurrence total",
                        )
                        # Count non-null MaximumRecordReference occurrences:
                        # N observations, root, target registry, marker contract,
                        # and the selector only for a selector-present family.
                        context_reference_count = _scope_checked_add(
                            context_reference_count,
                            observation_count + 3 + int(selector_present),
                            label=f"{label} non-null reference total",
                        )
                        observation_total = _scope_checked_add(
                            observation_total,
                            observation_count,
                            label=f"{label} observation total",
                        )
                        invocation_total = _scope_checked_add(
                            invocation_total,
                            len(invocations),
                            label=f"{label} invocation total",
                        )
                        evaluation_total = _scope_checked_add(
                            evaluation_total,
                            187 * observation_count + 1 + int(selector_present),
                            label=f"{label} evaluation total",
                        )
                        expression_total = _scope_checked_add(
                            expression_total,
                            1_872 * observation_count + 4 + 3 * int(selector_present),
                            label=f"{label} expression total",
                        )
    axis_count = sum(event.event_kind == "SYNTHETIC_AXIS" for event in events)
    _require(
        [case.scope_case_position for case in cases] == list(range(1, len(cases) + 1)),
        f"{label} scope-case positions differ",
    )
    return DerivedScopeHierarchy(
        profile_position=profile["profile_position"],
        constraint_scope_profile_id=profile["maximum_constraint_scope_profile_id"],
        ordered_events=tuple(events),
        ordered_scope_cases=tuple(cases),
        synthetic_axis_count=axis_count,
        constructed_context_occurrence_count=constructed_total,
        context_record_reference_count=context_reference_count,
        observation_count=observation_total,
        application_invocation_count=invocation_total,
        charged_cross_rule_evaluation_count=evaluation_total,
        direct_cross_expression_node_count=expression_total,
    )


def _derive_profile_scope_hierarchy(
    profile: dict[str, Any],
    *,
    validated_inventory: dict[str, Any],
    label: str,
) -> DerivedScopeHierarchy:
    _require(type(profile) is dict, f"{label} profile must be an exact object")
    _require_exact_keys(profile, PROFILE_KEYS, label=f"{label} profile")
    position = _require_integer(
        profile.get("profile_position"),
        label=f"{label} profile position",
        minimum=1,
        maximum=408,
    )
    expected = _expected_scope_profile_catalog(
        validated_inventory,
        label=f"{label} authority",
    )[position - 1]
    _require(profile == expected, f"{label} differs from rebuilt profile authority")
    return _derive_validated_profile_scope_hierarchy(profile, label=label)


def _derive_all_profile_scope_hierarchies(
    inventory: dict[str, Any],
    *,
    label: str,
) -> tuple[DerivedScopeHierarchy, ...]:
    actual = _require_array(
        inventory["operation_contracts"]["maximum_constraint_scope_profile_catalog"],
        label=f"{label} profile catalog",
        exact_length=408,
    )
    expected = _expected_scope_profile_catalog(inventory, label=label)
    _require(actual == list(expected), f"{label} complete profile authority differs")
    hierarchies = tuple(
        _derive_validated_profile_scope_hierarchy(
            profile,
            label=f"{label} profile {position}",
        )
        for position, profile in enumerate(actual, 1)
    )
    _require(
        sum(len(item.ordered_scope_cases) for item in hierarchies) == 475
        and sum(item.synthetic_axis_count for item in hierarchies) == 33,
        f"{label} global scope hierarchy counts differ",
    )
    return hierarchies


def _materialize_synthetic_scope_axis(
    seed: SyntheticScopeAxisSeed,
    *,
    coordinate_plan_position: int,
    prior_plan_id_by_axis_key: Mapping[
        ScopeAxisKey,
        PriorScopeAxisPlanAuthority,
    ],
    resource_meter: ProofResourceMeter,
    label: str,
) -> dict[str, Any]:
    """Resolve one verifier-derived symbolic scope axis into an exact plan."""

    _require(
        type(seed) is SyntheticScopeAxisSeed,
        f"{label} seed is not a synthetic scope-axis seed",
    )
    _require(
        isinstance(prior_plan_id_by_axis_key, Mapping),
        f"{label} prior scope-axis authority is not a mapping",
    )
    _require(
        type(resource_meter) is ProofResourceMeter,
        f"{label} resource meter differs",
    )
    plan_position = _require_integer(
        coordinate_plan_position,
        label=f"{label} coordinate-plan position",
        minimum=1,
    )
    axis_key = seed.axis_key
    _require(type(axis_key) is ScopeAxisKey, f"{label} axis key differs")
    _require(
        type(axis_key.coordinate_kind) is str
        and type(seed.coordinate_kind) is str
        and axis_key.coordinate_kind == seed.coordinate_kind,
        f"{label} coordinate kind differs from its axis key",
    )
    coordinate_kind = seed.coordinate_kind
    _require(
        coordinate_kind
        in {
            "ROOT_FAMILY_POSITION",
            "MODE_ATTEMPT_POSITION",
            "OBSERVATION_ROLE_POSITION",
            "SEQUENCE_ORDINAL",
        },
        f"{label} coordinate kind is not a synthetic scope kind",
    )
    profile_position = _require_integer(
        axis_key.profile_position,
        label=f"{label} profile position",
        minimum=1,
        maximum=408,
    )
    _require(
        5 <= profile_position <= 8,
        f"{label} profile does not admit a synthetic scope axis",
    )
    outer_positions = (
        axis_key.root_family_position,
        axis_key.mode_attempt_pair_position,
        axis_key.observation_role_position,
    )
    required_outer_count = {
        "ROOT_FAMILY_POSITION": 0,
        "MODE_ATTEMPT_POSITION": 1,
        "OBSERVATION_ROLE_POSITION": 2,
        "SEQUENCE_ORDINAL": 3,
    }[coordinate_kind]
    for position, value in enumerate(outer_positions, 1):
        if position <= required_outer_count:
            _require_integer(
                value,
                label=f"{label} outer scope position {position}",
                minimum=1,
            )
        else:
            _require(
                value is None,
                f"{label} inactive outer scope position {position} is non-null",
            )

    admissible_values = seed.ordered_admissible_position_values
    _require(
        type(admissible_values) is tuple and len(admissible_values) >= 2,
        f"{label} admissible scope positions differ",
    )
    for position, value in enumerate(admissible_values, 1):
        _require_integer(
            value,
            label=f"{label} admissible scope position {position}",
            minimum=(0 if coordinate_kind == "SEQUENCE_ORDINAL" else 1),
        )
    _require(
        tuple(sorted(set(admissible_values))) == admissible_values,
        f"{label} admissible scope positions are not unique/increasing",
    )
    if coordinate_kind != "SEQUENCE_ORDINAL":
        _require(
            admissible_values == tuple(range(1, len(admissible_values) + 1)),
            f"{label} one-based scope position domain differs",
        )

    _require(
        type(seed.subject_locator) is dict,
        f"{label} synthetic profile locator differs",
    )
    root_type_name = seed.subject_locator.get("root_type_name")
    _require(
        root_type_name == "TargetObservationV2",
        f"{label} synthetic locator root type differs",
    )
    subject_locator = {
        "locator_kind": "V3_INVENTORY_POINTER",
        "record_reference_id": (
            "/operation_contracts/maximum_constraint_scope_profile_catalog/"
            f"{profile_position - 1}"
        ),
        "root_type_name": root_type_name,
        "root_value_schema_id": None,
        "ordered_path_steps": [],
        "transient_state_key": None,
        "transient_source_child_position": None,
        "transient_source_child_proof_node_id": None,
    }
    _require(
        seed.subject_locator == subject_locator,
        f"{label} synthetic profile locator differs",
    )
    _validate_proof_subject_locator(
        subject_locator,
        label=f"{label} synthetic profile locator",
    )
    _require(
        axis_key not in prior_plan_id_by_axis_key,
        f"{label} current axis already has plan authority",
    )
    _require(
        type(seed.ordered_activation_guard_seeds) is tuple,
        f"{label} activation guard seeds differ",
    )

    clauses: list[dict[str, Any]] = []
    seen_guard_keys: set[ScopeAxisKey] = set()
    seen_guard_plan_ids: set[str] = set()
    seen_guard_plan_positions: set[int] = set()
    previous_guard_plan_position = 0
    scope_kind_rank = {
        "ROOT_FAMILY_POSITION": 0,
        "MODE_ATTEMPT_POSITION": 1,
        "OBSERVATION_ROLE_POSITION": 2,
        "SEQUENCE_ORDINAL": 3,
    }
    for clause_position, guard in enumerate(
        seed.ordered_activation_guard_seeds,
        1,
    ):
        _require(
            type(guard) is ScopeGuardSeed
            and type(guard.prior_axis_key) is ScopeAxisKey,
            f"{label} guard seed {clause_position} differs",
        )
        guard_axis_key = guard.prior_axis_key
        _require(
            type(guard_axis_key.coordinate_kind) is str
            and guard_axis_key.profile_position == profile_position,
            f"{label} guard seed {clause_position} crosses profile authority",
        )
        guard_coordinate_kind = guard_axis_key.coordinate_kind
        _require(
            guard_coordinate_kind in scope_kind_rank
            and scope_kind_rank[guard_coordinate_kind]
            < scope_kind_rank[coordinate_kind],
            f"{label} guard seed {clause_position} is not an outer scope axis",
        )
        expected_guard_value = {
            "ROOT_FAMILY_POSITION": axis_key.root_family_position,
            "MODE_ATTEMPT_POSITION": axis_key.mode_attempt_pair_position,
            "OBSERVATION_ROLE_POSITION": axis_key.observation_role_position,
            "SEQUENCE_ORDINAL": None,
        }[guard_coordinate_kind]
        _require(
            guard.position_value == expected_guard_value,
            f"{label} guard seed {clause_position} selected position differs",
        )
        expected_guard_outer_positions = {
            "ROOT_FAMILY_POSITION": (None, None, None),
            "MODE_ATTEMPT_POSITION": (
                axis_key.root_family_position,
                None,
                None,
            ),
            "OBSERVATION_ROLE_POSITION": (
                axis_key.root_family_position,
                axis_key.mode_attempt_pair_position,
                None,
            ),
            "SEQUENCE_ORDINAL": (
                axis_key.root_family_position,
                axis_key.mode_attempt_pair_position,
                axis_key.observation_role_position,
            ),
        }[guard_coordinate_kind]
        _require(
            (
                guard_axis_key.root_family_position,
                guard_axis_key.mode_attempt_pair_position,
                guard_axis_key.observation_role_position,
            )
            == expected_guard_outer_positions,
            f"{label} guard seed {clause_position} symbolic axis differs",
        )
        _require(
            guard_axis_key not in seen_guard_keys,
            f"{label} guard seed {clause_position} repeats symbolic authority",
        )
        seen_guard_keys.add(guard_axis_key)
        _require(
            guard_axis_key in prior_plan_id_by_axis_key,
            f"{label} guard seed {clause_position} has no prior plan authority",
        )
        authority = prior_plan_id_by_axis_key[guard_axis_key]
        _require(
            type(authority) is PriorScopeAxisPlanAuthority
            and authority.axis_key == guard_axis_key,
            f"{label} guard seed {clause_position} axis authority differs",
        )
        prior_position = _require_integer(
            authority.coordinate_plan_position,
            label=f"{label} guard seed {clause_position} prior plan position",
            minimum=1,
        )
        _require(
            previous_guard_plan_position < prior_position < plan_position,
            f"{label} guard seed {clause_position} is not in strict prior-plan order",
        )
        previous_guard_plan_position = prior_position
        _require(
            prior_position not in seen_guard_plan_positions,
            f"{label} guard seed {clause_position} repeats a prior plan position",
        )
        seen_guard_plan_positions.add(prior_position)
        prior_plan_id = _require_sha256(
            authority.choice_coordinate_plan_id,
            label=f"{label} guard seed {clause_position} prior plan ID",
        )
        _require(
            prior_plan_id not in seen_guard_plan_ids,
            f"{label} guard seed {clause_position} repeats a prior plan ID",
        )
        seen_guard_plan_ids.add(prior_plan_id)
        _require(
            guard.guard_operator == "EQUALS",
            f"{label} guard seed {clause_position} operator differs",
        )
        minimum_position_value = 0 if guard_coordinate_kind == "SEQUENCE_ORDINAL" else 1
        position_value = _require_integer(
            guard.position_value,
            label=f"{label} guard seed {clause_position} position atom",
            minimum=minimum_position_value,
        )
        guard_atom = {
            "atom_kind": "POSITION",
            "boolean_value": None,
            "integer_value": None,
            "text_value": None,
            "position_value": position_value,
            "canonical_bytes_hex_value": None,
        }
        _validate_primitive_atom(
            guard_atom,
            label=f"{label} guard seed {clause_position} position atom",
        )
        clauses.append(
            {
                "guard_clause_position": clause_position,
                "prior_choice_coordinate_plan_id": prior_plan_id,
                "guard_operator": "EQUALS",
                "guard_atom": guard_atom,
            }
        )
    _validate_activation_guards(clauses, label=f"{label} activation guards")

    payload = {
        "coordinate_plan_position": plan_position,
        "coordinate_scope": "CONSTRUCTED_CONTEXT",
        "coordinate_kind": coordinate_kind,
        "subject_locator": subject_locator,
        "value_schema_id": None,
        "ordered_activation_guard_clauses": clauses,
    }
    plan = {
        **payload,
        "choice_coordinate_plan_id": _semantic_id(
            CHOICE_COORDINATE_PLAN_DOMAIN,
            payload,
            resource_meter=resource_meter,
        ),
    }
    _require_exact_keys(plan, CHOICE_COORDINATE_PLAN_KEYS, label=label)
    return plan


def _derive_synthetic_selected_value_locator(
    coordinate_kind: str,
    *,
    witness_record_reference_id: str | None,
    label: str,
) -> dict[str, Any]:
    """Derive the one legal retained-value projection for a scope coordinate."""

    _require(
        type(coordinate_kind) is str
        and coordinate_kind
        in {
            "ROOT_FAMILY_POSITION",
            "MODE_ATTEMPT_POSITION",
            "OBSERVATION_ROLE_POSITION",
            "SEQUENCE_ORDINAL",
        },
        f"{label} coordinate kind is not a synthetic scope kind",
    )

    def member_step(
        step_position: int,
        member_name: str,
        member_position: int,
    ) -> dict[str, Any]:
        return {
            "step_position": step_position,
            "step_kind": "RECORD_MEMBER",
            "member_name": member_name,
            "member_position": member_position,
            "array_ordinal": None,
            "sequence_name": None,
            "union_alternative_position": None,
            "nullable_branch": None,
        }

    if coordinate_kind in {"ROOT_FAMILY_POSITION", "SEQUENCE_ORDINAL"}:
        _require(
            witness_record_reference_id is None,
            f"{label} scope-context coordinate has a witness reference",
        )
        locator = {
            "retained_source_kind": "SCOPE_WITNESS_CONTEXT",
            "record_reference_id": None,
            "root_type_name": None,
            "scope_context_member_name": (
                "selected_root_family_position"
                if coordinate_kind == "ROOT_FAMILY_POSITION"
                else "measured_sequence_ordinal"
            ),
            "ordered_path_steps": [],
            "projection_kind": "FROZEN_CATALOG_POSITION",
        }
    else:
        witness_reference = _require_sha256(
            witness_record_reference_id,
            label=f"{label} measured TargetObservationV2 witness reference",
        )
        path = [member_step(1, "observation_context", 4)]
        if coordinate_kind == "OBSERVATION_ROLE_POSITION":
            path.append(member_step(2, "observation_role", 4))
        locator = {
            "retained_source_kind": "WITNESS_RECORD",
            "record_reference_id": witness_reference,
            "root_type_name": "TargetObservationV2",
            "scope_context_member_name": None,
            "ordered_path_steps": path,
            "projection_kind": "FROZEN_CATALOG_POSITION",
        }
    _validate_retained_value_locator(locator, label=label)
    return locator


def _derive_row_universe(
    registry: dict[str, Any], inventory: dict[str, Any]
) -> tuple[RowPlan, ...]:
    rows: list[RowPlan] = []
    descriptors = registry["ordered_external_type_descriptors"]
    for descriptor in descriptors:
        type_name = descriptor["type_name"]
        if descriptor["type_form"] == "RECORD":
            rows.append(
                RowPlan(
                    len(rows) + 1,
                    "INTRINSIC_RECORD",
                    type_name,
                    None,
                    None,
                )
            )
            continue
        _require(descriptor["type_form"] == "TAGGED_UNION", "unknown type form")
        alternatives = descriptor["tagged_union_descriptor"]["ordered_alternatives"]
        for alternative_position, alternative in enumerate(alternatives, 1):
            _require(
                alternative["alternative_position"] == alternative_position,
                "union alternative positions differ",
            )
            rows.append(
                RowPlan(
                    len(rows) + 1,
                    "INTRINSIC_UNION_ALTERNATIVE",
                    type_name,
                    alternative["alternative_name"],
                    None,
                )
            )
    _require(len(rows) == 66, "expanded intrinsic row count differs")
    profiles = inventory["operation_contracts"][
        "maximum_constraint_scope_profile_catalog"
    ]
    expected_profile_kinds = (
        ["OUTER_RESULT_BOUNDARY_FIXTURE"] * 4
        + ["NON_CHECKPOINT_ROOT_FAMILY"] * 4
        + ["CHECKPOINT_ROOT_COORDINATE"] * 400
    )
    _require(
        [profile["profile_kind"] for profile in profiles] == expected_profile_kinds,
        "profile kind/order partition differs",
    )
    for profile in profiles:
        rows.append(
            RowPlan(
                len(rows) + 1,
                profile["profile_kind"],
                profile["measured_type_name"],
                None,
                profile["maximum_constraint_scope_profile_id"],
            )
        )
    _require(
        len(rows) == 474 and [row.row_position for row in rows] == list(range(1, 475)),
        "474-row universe differs",
    )
    return tuple(rows)


def _derive_v1_presearch_cap_rejection(
    registry: dict[str, Any],
    *,
    rows: tuple[RowPlan, ...],
) -> V1PresearchCapRejection:
    """Prove the rejected V1 plan lower bound from one intrinsic schema path."""

    target_rows = [
        row
        for row in rows
        if row.row_kind == "INTRINSIC_RECORD"
        and row.type_name == "TargetFieldRegistryV1"
        and row.alternative_name is None
        and row.constraint_scope_profile_id is None
    ]
    _require(
        len(target_rows) == 1 and target_rows[0].row_position == 62,
        "V1 rejection target intrinsic row differs",
    )
    descriptors = registry["ordered_external_type_descriptors"]
    _require(
        len(descriptors) >= 48
        and descriptors[47]["type_name"] == "TargetFieldRegistryV1",
        "V1 rejection target external descriptor position differs",
    )
    descriptor_by_name = {item["type_name"]: item for item in descriptors}
    _require(
        len(descriptor_by_name) == len(descriptors),
        "V1 rejection descriptor names repeat",
    )
    schemas = registry["value_schema_catalog"]
    schema_by_id = {item["value_schema_id"]: item for item in schemas}
    _require(
        len(schema_by_id) == len(schemas),
        "V1 rejection value-schema identities repeat",
    )

    def exact_member(
        type_name: str,
        member_name: str,
        member_position: int,
    ) -> dict[str, Any]:
        descriptor = descriptor_by_name[type_name]
        _require(
            descriptor["type_form"] == "RECORD",
            f"V1 rejection {type_name} is not a record",
        )
        matches = [
            member
            for member in descriptor["record_member_descriptors"]
            if member["member_name"] == member_name
        ]
        _require(
            len(matches) == 1 and matches[0]["member_position"] == member_position,
            f"V1 rejection {type_name}.{member_name} authority differs",
        )
        return matches[0]

    outer_member = exact_member("TargetFieldRegistryV1", "descriptors", 11)
    _require(
        descriptor_by_name["TargetFieldRegistryV1"]["type_role"] == "STANDALONE"
        and outer_member["member_role"] == "IDENTITY_PAYLOAD",
        "V1 rejection outer payload roles differ",
    )
    outer_array = schema_by_id[outer_member["value_schema_id"]]
    _require(
        outer_array["schema_kind"] == "ARRAY"
        and outer_array["nullable"] is False
        and outer_array["array_minimum_items"]
        == outer_array["array_maximum_items"]
        == 185,
        "V1 rejection outer descriptor-array authority differs",
    )
    outer_item = schema_by_id[outer_array["array_item_value_schema_id"]]
    _require(
        outer_item["schema_kind"] == "OBJECT_REF"
        and outer_item["nullable"] is False
        and outer_item["referenced_type_name"]
        == "CapacityMeasurementTargetFieldDescriptorV1",
        "V1 rejection outer descriptor-item authority differs",
    )
    inner_member = exact_member(
        "CapacityMeasurementTargetFieldDescriptorV1",
        "value_shape_keys",
        14,
    )
    _require(
        descriptor_by_name["CapacityMeasurementTargetFieldDescriptorV1"]["type_role"]
        == "NESTED"
        and inner_member["member_role"] == "NESTED_PAYLOAD",
        "V1 rejection inner payload roles differ",
    )
    inner_array = schema_by_id[inner_member["value_schema_id"]]
    _require(
        inner_array["schema_kind"] == "ARRAY"
        and inner_array["nullable"] is False
        and inner_array["array_minimum_items"] == 0
        and inner_array["array_maximum_items"] == 512,
        "V1 rejection inner key-array authority differs",
    )
    inner_item = schema_by_id[inner_array["array_item_value_schema_id"]]
    raw_string_language_id = (
        "eb311c28e0711cd6f7e5f21119366b18881a30ef6dd56d8626c5cfea2d5bc727"
    )
    _require(
        inner_item["schema_kind"] == "TEXT"
        and inner_item["nullable"] is False
        and inner_item["text_language_id"] == raw_string_language_id,
        "V1 rejection key-item text authority differs",
    )
    language_matches = [
        item
        for item in registry["text_language_catalog"]
        if item["text_language_id"] == raw_string_language_id
    ]
    _require(len(language_matches) == 1, "V1 rejection text language differs")
    language = language_matches[0]
    _require(
        language["language_kind"] == "BUILTIN"
        and language["built_in_language_kind"] == "RAW_CANONICAL_JSON_STRING"
        and language["ordered_literals"] == []
        and language["ordering_semantics"] == "UNICODE_SCALAR_LEXICOGRAPHIC",
        "V1 rejection raw-string language authority differs",
    )
    _require(
        all(
            language[name] is None
            for name in (
                "ascii_dfa_id",
                "decimal_maximum",
                "maximum_decoded_octets",
                "maximum_utf8_octets",
                "minimum_decoded_octets",
                "minimum_utf8_octets",
                "unicode_identifier_profile_id",
            )
        ),
        "V1 rejection raw-string unused parameters differ",
    )

    outer_count = outer_array["array_maximum_items"]
    inner_maximum = inner_array["array_maximum_items"]
    cardinality_count = outer_count
    text_count = outer_count * inner_maximum
    coordinate_lower_bound = cardinality_count + text_count
    coordinate_cap = SEED_EXECUTION_SAFETY_LIMITS_V1[
        "component_choice_coordinate_count"
    ]
    proof_node_cap = SEED_EXECUTION_SAFETY_LIMITS_V1["proof_node_count"]
    maximum_proof_depth_cap = SEED_EXECUTION_SAFETY_LIMITS_V1["maximum_proof_depth"]
    tie_break_proof_node_lower_bound = coordinate_lower_bound + 1
    maximum_proof_depth_lower_bound = tie_break_proof_node_lower_bound
    _require(
        coordinate_lower_bound == 94_905
        and coordinate_lower_bound > coordinate_cap
        and coordinate_lower_bound > proof_node_cap,
        "V1 pre-search lower bound no longer proves cap rejection",
    )
    _require(
        tie_break_proof_node_lower_bound == 94_906
        and tie_break_proof_node_lower_bound > proof_node_cap
        and maximum_proof_depth_lower_bound > maximum_proof_depth_cap,
        "V1 tie-break proof chain no longer proves node/depth cap rejection",
    )
    return V1PresearchCapRejection(
        intrinsic_row_position=target_rows[0].row_position,
        outer_fixed_descriptor_occurrence_count=outer_count,
        inner_array_cardinality_coordinate_count=cardinality_count,
        inner_text_coordinate_count=text_count,
        component_choice_coordinate_lower_bound=coordinate_lower_bound,
        prefix_proof_node_lower_bound=coordinate_lower_bound,
        tie_break_proof_node_lower_bound=tie_break_proof_node_lower_bound,
        maximum_proof_depth_lower_bound=maximum_proof_depth_lower_bound,
        component_coordinate_cap_excess=coordinate_lower_bound - coordinate_cap,
        proof_node_cap_excess_before_base_nodes=(
            coordinate_lower_bound - proof_node_cap
        ),
        tie_break_proof_node_cap_excess_before_descriptor_and_root_nodes=(
            tie_break_proof_node_lower_bound - proof_node_cap
        ),
        maximum_proof_depth_cap_excess_before_descriptor_and_root_nodes=(
            maximum_proof_depth_lower_bound - maximum_proof_depth_cap
        ),
    )


def _validate_measurement_binding(value: Any, *, label: str) -> dict[str, Any]:
    binding = _require_exact_keys(value, MEASUREMENT_BINDING_KEYS, label=label)
    _require(
        binding["binding_kind"]
        in {
            "SELF_RECORD",
            "SELF_UNION_VALUE",
            "OWNER_MEMBER_UNION_VALUE",
            "OUTER_RESULT_RECORD",
            "ROOT_ANY_NONCHECKPOINT_OBSERVATION",
            "ROOT_EXACT_CHECKPOINT_OBSERVATION",
        },
        f"{label} binding kind differs",
    )
    _require(
        type(binding["validation_root_type_name"]) is str, f"{label} root type differs"
    )
    path = _require_array(
        binding["measured_value_typed_member_path"],
        label=f"{label} typed path",
        maximum_length=64,
    )
    _require(
        all(type(part) is str and part for part in path), f"{label} typed path differs"
    )
    _require(
        binding["sequence_binding_name"] is None
        or type(binding["sequence_binding_name"]) is str,
        f"{label} sequence binding differs",
    )
    _require(
        binding["sequence_ordinal"] is None
        or (
            type(binding["sequence_ordinal"]) is int
            and 0 <= binding["sequence_ordinal"] <= SAFE_INTEGER_MAXIMUM
        ),
        f"{label} sequence ordinal differs",
    )
    return binding


def _validate_path_steps(
    value: Any,
    *,
    label: str,
    schema_domain: bool,
) -> list[dict[str, Any]]:
    steps = _require_array(value, label=label, maximum_length=64)
    result: list[dict[str, Any]] = []
    for position, step_value in enumerate(steps, 1):
        step = _require_exact_keys(
            step_value,
            PATH_STEP_KEYS,
            label=f"{label} step {position}",
        )
        _require(step["step_position"] == position, f"{label} positions differ")
        kind = step["step_kind"]
        _require(
            kind
            in {
                "RECORD_MEMBER",
                "ARRAY_ITEM",
                "EXTERNAL_SEQUENCE_ITEM",
                "UNION_ALTERNATIVE",
                "NULLABLE_BRANCH",
            },
            f"{label} step kind differs",
        )
        required: dict[str, Any] = {
            "member_name": None,
            "member_position": None,
            "array_ordinal": None,
            "sequence_name": None,
            "union_alternative_position": None,
            "nullable_branch": None,
        }
        if kind == "RECORD_MEMBER":
            _require(
                type(step["member_name"]) is str and bool(step["member_name"]),
                f"{label} record-member name differs",
            )
            _require_integer(
                step["member_position"],
                label=f"{label} record-member position",
                minimum=1,
            )
            required["member_name"] = step["member_name"]
            required["member_position"] = step["member_position"]
        elif kind in {"ARRAY_ITEM", "EXTERNAL_SEQUENCE_ITEM"}:
            if kind == "EXTERNAL_SEQUENCE_ITEM":
                _require(
                    type(step["sequence_name"]) is str and bool(step["sequence_name"]),
                    f"{label} external-sequence name differs",
                )
                required["sequence_name"] = step["sequence_name"]
            ordinal = step["array_ordinal"]
            _require(
                (kind == "ARRAY_ITEM" and schema_domain and ordinal is None)
                or type(ordinal) is int,
                f"{label} array ordinal differs",
            )
            if ordinal is not None:
                _require_integer(ordinal, label=f"{label} array ordinal")
                required["array_ordinal"] = ordinal
        elif kind == "UNION_ALTERNATIVE":
            _require_integer(
                step["union_alternative_position"],
                label=f"{label} union-alternative position",
                minimum=1,
            )
            required["union_alternative_position"] = step["union_alternative_position"]
        else:
            _require(
                step["nullable_branch"] in {"NULL", "NON_NULL"},
                f"{label} nullable branch differs",
            )
            required["nullable_branch"] = step["nullable_branch"]
        for name, expected in required.items():
            _require(step[name] == expected, f"{label} inactive path field differs")
        result.append(step)
    return result


def _validate_proof_subject_locator(
    value: Any,
    *,
    label: str,
    resource_meter: ProofResourceMeter | None = None,
    referenced_prior_catalog_ids: list[str] | None = None,
) -> dict[str, Any]:
    locator = _require_exact_keys(value, PROOF_SUBJECT_LOCATOR_KEYS, label=label)
    kind = locator["locator_kind"]
    _require(
        kind
        in {
            "SCHEMA_DOMAIN",
            "WITNESS_RECORD",
            "CONTEXT_OBJECT",
            "V3_INVENTORY_POINTER",
            "TRANSIENT_FRONTIER_STATE",
        },
        f"{label} locator kind differs",
    )
    reference = locator["record_reference_id"]
    root_type = locator["root_type_name"]
    root_schema = locator["root_value_schema_id"]
    transient = locator["transient_state_key"]
    transient_position = locator["transient_source_child_position"]
    transient_id = locator["transient_source_child_proof_node_id"]
    _require(
        root_type is None or (type(root_type) is str and bool(root_type)),
        f"{label} root type differs",
    )
    _require(
        root_schema is None or _is_sha256(root_schema),
        f"{label} root value-schema identity differs",
    )
    _validate_path_steps(
        locator["ordered_path_steps"],
        label=f"{label} path",
        schema_domain=kind == "SCHEMA_DOMAIN",
    )
    if kind == "SCHEMA_DOMAIN":
        _require(
            reference is None
            and transient is None
            and transient_position is None
            and transient_id is None
            and root_type is not None
            and root_schema is not None,
            f"{label} schema-domain nullability differs",
        )
    elif kind == "TRANSIENT_FRONTIER_STATE":
        _require(
            reference is None
            and root_type is None
            and root_schema is None
            and type(transient) is list,
            f"{label} transient-state nullability differs",
        )
        _require_integer(
            transient_position,
            label=f"{label} transient source child position",
            minimum=1,
        )
        _require_sha256(transient_id, label=f"{label} transient source child ID")
        _require(
            locator["ordered_path_steps"] == [],
            f"{label} transient path is not empty",
        )
        for position, cell in enumerate(transient, 1):
            _validate_state_cell(
                cell,
                label=f"{label} transient cell {position}",
                resource_meter=resource_meter,
            )
            if (
                referenced_prior_catalog_ids is not None
                and cell["cell_kind"] == "VERIFIER_DERIVED_CATALOG_POSITION"
            ):
                referenced_prior_catalog_ids.append(cell["catalog_id"])
    else:
        _require(
            reference is not None
            and root_type is not None
            and root_schema is None
            and transient is None,
            f"{label} retained-record nullability differs",
        )
        _require(
            transient_position is None and transient_id is None,
            f"{label} retained-record transient source differs",
        )
        if kind in {"WITNESS_RECORD", "CONTEXT_OBJECT"}:
            _require_sha256(reference, label=f"{label} record reference")
        else:
            _require_absolute_rfc6901_pointer(
                reference,
                label=f"{label} inventory pointer",
            )
    return locator


def _validate_retained_value_locator(value: Any, *, label: str) -> dict[str, Any]:
    locator = _require_exact_keys(value, RETAINED_VALUE_LOCATOR_KEYS, label=label)
    kind = locator["retained_source_kind"]
    _require(
        kind
        in {
            "WITNESS_RECORD",
            "CONTEXT_OBJECT",
            "V3_INVENTORY_POINTER",
            "SCOPE_WITNESS_CONTEXT",
        },
        f"{label} retained source kind differs",
    )
    if kind == "SCOPE_WITNESS_CONTEXT":
        _require(
            locator["record_reference_id"] is None
            and locator["root_type_name"] is None
            and type(locator["scope_context_member_name"]) is str
            and bool(locator["scope_context_member_name"]),
            f"{label} scope-context nullability differs",
        )
    else:
        if kind in {"WITNESS_RECORD", "CONTEXT_OBJECT"}:
            _require_sha256(
                locator["record_reference_id"], label=f"{label} record reference"
            )
        else:
            _require_absolute_rfc6901_pointer(
                locator["record_reference_id"],
                label=f"{label} inventory pointer",
            )
        _require(
            type(locator["root_type_name"]) is str
            and bool(locator["root_type_name"])
            and locator["scope_context_member_name"] is None,
            f"{label} record-source nullability differs",
        )
    _validate_path_steps(
        locator["ordered_path_steps"],
        label=f"{label} path",
        schema_domain=False,
    )
    _require(
        locator["projection_kind"]
        in {
            "VALUE",
            "NULLABILITY_BRANCH",
            "ARRAY_CARDINALITY",
            "UNION_ALTERNATIVE_POSITION",
            "FROZEN_CATALOG_POSITION",
        },
        f"{label} projection kind differs",
    )
    return locator


def _validate_maximum_record_reference(
    value: Any,
    *,
    expected_reference_kind: str | None,
    expected_inventory_pointer: str | None,
    label: str,
    resource_meter: ProofResourceMeter | None = None,
) -> dict[str, Any]:
    _require(type(value) is dict, f"{label} is not a record-reference object")
    reference_kind = value.get("reference_kind")
    _require(
        reference_kind in MAXIMUM_RECORD_REFERENCE_KEYS,
        f"{label} reference kind differs",
    )
    if expected_reference_kind is not None:
        _require(
            reference_kind == expected_reference_kind,
            f"{label} reference kind differs from its authority",
        )
    reference = _require_exact_keys(
        value,
        MAXIMUM_RECORD_REFERENCE_KEYS[reference_kind],
        label=label,
    )
    for name in ("record_type_name", "record_identity_field"):
        _require(
            type(reference[name]) is str and bool(reference[name]),
            f"{label} {name} differs",
        )
    _require(
        reference_kind == "WITNESS_RECORD"
        or reference["record_identity_field"] != "$canonical_sha256",
        f"{label} uses the witness-only canonical-SHA identity sentinel",
    )
    _require_sha256(reference["record_identity"], label=f"{label} record identity")
    _require_integer(
        reference["record_canonical_byte_length"],
        label=f"{label} record canonical length",
        minimum=1,
    )
    _require_sha256(
        reference["record_canonical_sha256"],
        label=f"{label} record canonical SHA",
    )
    if reference_kind == "CONTEXT_OBJECT":
        _require_sha256(
            reference["maximum_context_object_id"],
            label=f"{label} context-object ID",
        )
        _require(
            expected_inventory_pointer is None,
            f"{label} context reference cannot bind an inventory pointer",
        )
    elif reference_kind == "V3_INVENTORY_POINTER":
        _require(
            reference["source_inventory_sha256"] == INVENTORY_SEMANTIC_ID,
            f"{label} inventory authority differs",
        )
        pointer = _require_absolute_rfc6901_pointer(
            reference["inventory_json_pointer"],
            label=f"{label} inventory pointer",
        )
        if expected_inventory_pointer is not None:
            _require(
                pointer == expected_inventory_pointer,
                f"{label} inventory pointer differs from its authority",
            )
    else:
        _require(
            expected_inventory_pointer is None,
            f"{label} witness reference cannot bind an inventory pointer",
        )
    payload = {
        name: item
        for name, item in reference.items()
        if name != "maximum_record_reference_id"
    }
    _require(
        reference["maximum_record_reference_id"]
        == _semantic_id(
            MAXIMUM_RECORD_REFERENCE_DOMAIN,
            payload,
            resource_meter=resource_meter,
        ),
        f"{label} semantic identity differs",
    )
    return reference


def _inventory_pointer_authority_from_profile(
    profile: Any,
    *,
    label: str,
) -> Mapping[str, str]:
    """Derive the profile's closed V3 pointer-to-record-identity authority."""

    _require(type(profile) is dict, f"{label} must be one validated profile object")
    pointers = _require_array(
        profile.get("ordered_source_authority_pointers"),
        label=f"{label} source-authority pointers",
    )
    identities = _require_array(
        profile.get("ordered_source_authority_ids"),
        label=f"{label} source-authority identities",
    )
    _require(
        len(pointers) == len(identities),
        f"{label} source-authority pairing differs",
    )
    authority: dict[str, str] = {}
    for position, (pointer, identity) in enumerate(
        zip(pointers, identities, strict=True),
        1,
    ):
        checked_pointer = _require_absolute_rfc6901_pointer(
            pointer,
            label=f"{label} source-authority pointer {position}",
        )
        checked_identity = _require_sha256(
            identity,
            label=f"{label} source-authority identity {position}",
        )
        _require(
            checked_pointer not in authority,
            f"{label} repeats source-authority pointer {checked_pointer}",
        )
        authority[checked_pointer] = checked_identity
    return MappingProxyType(authority)


def _resolve_v3_inventory_record_reference(
    value: Any,
    *,
    validated_inventory: dict[str, Any],
    validated_registry: dict[str, Any],
    permitted_inventory_pointer_authority: Mapping[str, str],
    expected_inventory_pointer: str | None,
    expected_record_type_name: str | None,
    label: str,
    resource_meter: ProofResourceMeter,
) -> ResolvedRecordReference:
    """Resolve and fully validate one profile-permitted V3 record reference."""

    _require(
        isinstance(permitted_inventory_pointer_authority, Mapping),
        f"{label} permitted inventory-pointer authority must be a mapping",
    )
    normalized_authority: dict[str, str] = {}
    for pointer, identity in permitted_inventory_pointer_authority.items():
        checked_pointer = _require_absolute_rfc6901_pointer(
            pointer,
            label=f"{label} permitted inventory pointer",
        )
        checked_identity = _require_sha256(
            identity,
            label=f"{label} permitted inventory identity",
        )
        _require(
            checked_pointer not in normalized_authority,
            f"{label} repeats a permitted inventory pointer",
        )
        normalized_authority[checked_pointer] = checked_identity

    reference = _validate_maximum_record_reference(
        value,
        expected_reference_kind="V3_INVENTORY_POINTER",
        expected_inventory_pointer=expected_inventory_pointer,
        label=label,
        resource_meter=resource_meter,
    )
    pointer = reference["inventory_json_pointer"]
    _require(
        pointer in normalized_authority,
        f"{label} inventory pointer is not permitted by its scope profile",
    )
    _require(
        reference["record_identity"] == normalized_authority[pointer],
        f"{label} record identity differs from its scope-profile authority",
    )
    if expected_record_type_name is not None:
        _require(
            reference["record_type_name"] == expected_record_type_name,
            f"{label} record type differs from its exact authority",
        )

    record = _resolve_absolute_rfc6901_pointer(
        validated_inventory,
        pointer,
        label=f"{label} inventory pointer",
    )
    _require(type(record) is dict, f"{label} does not resolve to a complete record")

    descriptor_matches = [
        descriptor
        for descriptor in validated_registry["ordered_external_type_descriptors"]
        if descriptor["type_name"] == reference["record_type_name"]
    ]
    _require(
        len(descriptor_matches) == 1,
        f"{label} record type has no unique structural descriptor",
    )
    descriptor = descriptor_matches[0]
    _require(
        descriptor["type_form"] == "RECORD",
        f"{label} record type is not a structural record",
    )
    identity_field = descriptor["identity_field"]
    _require(
        reference["record_identity_field"] == identity_field,
        f"{label} identity field differs from its structural descriptor",
    )
    member_descriptors = _require_array(
        descriptor["record_member_descriptors"],
        label=f"{label} structural record members",
    )
    expected_member_names = frozenset(
        member["member_name"] for member in member_descriptors
    )
    _require(
        len(expected_member_names) == len(member_descriptors),
        f"{label} structural descriptor repeats a member name",
    )
    _require_exact_keys(record, expected_member_names, label=f"{label} resolved record")
    _require(
        record["canonicalization_version"] == CANONICALIZATION_VERSION
        and record["measurement_schema_version"] == MEASUREMENT_SCHEMA_VERSION
        and record["record_domain"] == descriptor["described_record_domain"],
        f"{label} resolved record envelope differs from its descriptor",
    )
    actual_identity = _require_sha256(
        record[identity_field],
        label=f"{label} resolved record identity",
    )
    _require(
        actual_identity == reference["record_identity"],
        f"{label} resolved record identity differs from its reference",
    )
    identity_payload = {
        member_name: record[member_name]
        for member_name in descriptor["identity_payload_member_order"]
    }
    _require(
        _semantic_id(
            descriptor["described_record_domain"],
            identity_payload,
            resource_meter=resource_meter,
        )
        == actual_identity,
        f"{label} resolved record semantic identity differs",
    )

    canonical_length = _canonical_octet_length(record)
    _require(
        canonical_length == reference["record_canonical_byte_length"],
        f"{label} resolved record canonical length differs",
    )
    canonical_sha256, hashed_octets = _metered_canonical_sha256(
        record,
        meter=resource_meter,
    )
    _require(
        hashed_octets == canonical_length
        and canonical_sha256 == reference["record_canonical_sha256"],
        f"{label} resolved record canonical SHA differs",
    )
    return ResolvedRecordReference(
        reference=reference,
        validated_record=ValidatedRecord(
            record_type_name=reference["record_type_name"],
            record_identity_field=identity_field,
            record_identity=actual_identity,
            record_canonical_byte_length=canonical_length,
            record_canonical_sha256=canonical_sha256,
            record=record,
        ),
    )


def _resolve_local_baseline_result_control_pointer(
    value: Any,
    *,
    validated_inventory: dict[str, Any],
    validated_registry: dict[str, Any],
    resource_meter: ProofResourceMeter,
    label: str,
) -> ValidatedRecord:
    """Resolve the sole local control pointer without widening row references."""

    pointer = _require_absolute_rfc6901_pointer(value, label=label)
    _require(
        pointer == LOCAL_SHUTDOWN_BASELINE_RESULT_POINTER,
        f"{label} differs from the sole local baseline-result authority",
    )
    record = _resolve_absolute_rfc6901_pointer(
        validated_inventory,
        pointer,
        label=label,
    )
    _require(type(record) is dict, f"{label} does not resolve to a complete record")
    descriptor_matches = [
        descriptor
        for descriptor in validated_registry["ordered_external_type_descriptors"]
        if descriptor["type_name"] == LOCAL_SHUTDOWN_BASELINE_RESULT_TYPE_NAME
    ]
    _require(
        len(descriptor_matches) == 1,
        f"{label} result type has no unique structural descriptor",
    )
    descriptor = descriptor_matches[0]
    _require(
        descriptor["type_form"] == "RECORD"
        and descriptor["identity_field"] == "result_evidence_id"
        and descriptor["described_record_domain"]
        == "RiskYieldMMA2MOperationResultEvidenceV4_9F_RawV8",
        f"{label} result descriptor differs",
    )
    member_descriptors = _require_array(
        descriptor["record_member_descriptors"],
        label=f"{label} structural record members",
    )
    expected_members = frozenset(member["member_name"] for member in member_descriptors)
    _require(
        len(expected_members) == len(member_descriptors),
        f"{label} structural descriptor repeats a member name",
    )
    _require_exact_keys(record, expected_members, label=f"{label} resolved record")
    _require(
        record["canonicalization_version"] == CANONICALIZATION_VERSION
        and record["measurement_schema_version"] == MEASUREMENT_SCHEMA_VERSION
        and record["record_domain"] == descriptor["described_record_domain"],
        f"{label} resolved record envelope differs",
    )
    identity = _require_sha256(
        record["result_evidence_id"],
        label=f"{label} result identity",
    )
    _require(
        identity == LOCAL_SHUTDOWN_BASELINE_RESULT_IDENTITY,
        f"{label} result identity differs from the pinned fixture",
    )
    identity_payload = {
        member_name: record[member_name]
        for member_name in descriptor["identity_payload_member_order"]
    }
    _require(
        _semantic_id(
            descriptor["described_record_domain"],
            identity_payload,
            resource_meter=resource_meter,
        )
        == identity,
        f"{label} result semantic identity differs",
    )
    canonical_octets = _canonical_octet_length(record)
    _require(
        canonical_octets == LOCAL_SHUTDOWN_BASELINE_RESULT_CANONICAL_OCTETS,
        f"{label} compact canonical length differs",
    )
    return ValidatedRecord(
        record_type_name=LOCAL_SHUTDOWN_BASELINE_RESULT_TYPE_NAME,
        record_identity_field="result_evidence_id",
        record_identity=identity,
        record_canonical_byte_length=canonical_octets,
        record_canonical_sha256=LOCAL_SHUTDOWN_BASELINE_RESULT_CANONICAL_SHA256,
        record=record,
    )


def _validate_primitive_atom(value: Any, *, label: str) -> tuple[int, Any]:
    atom = _require_exact_keys(value, PRIMITIVE_ATOM_KEYS, label=label)
    kind = atom["atom_kind"]
    _require(
        kind
        in {
            "INACTIVE",
            "NULL",
            "BOOLEAN",
            "SAFE_INTEGER",
            "TEXT",
            "POSITION",
            "CANONICAL_BYTES",
        },
        f"{label} kind differs",
    )
    expected_non_null = {
        "INACTIVE": None,
        "NULL": None,
        "BOOLEAN": "boolean_value",
        "SAFE_INTEGER": "integer_value",
        "TEXT": "text_value",
        "POSITION": "position_value",
        "CANONICAL_BYTES": "canonical_bytes_hex_value",
    }[kind]
    value_names = (
        "boolean_value",
        "integer_value",
        "text_value",
        "position_value",
        "canonical_bytes_hex_value",
    )
    for name in value_names:
        if name == expected_non_null:
            continue
        _require(atom[name] is None, f"{label} has a noncanonical inactive member")
    if kind == "INACTIVE":
        return (0, None)
    if kind == "NULL":
        return (1, None)
    if kind == "BOOLEAN":
        _require(type(atom["boolean_value"]) is bool, f"{label} Boolean differs")
        return (2, atom["boolean_value"])
    if kind == "SAFE_INTEGER":
        integer = _require_integer(atom["integer_value"], label=f"{label} integer")
        return (3, integer)
    if kind == "TEXT":
        _require(type(atom["text_value"]) is str, f"{label} text differs")
        return (4, atom["text_value"])
    if kind == "POSITION":
        position = _require_integer(atom["position_value"], label=f"{label} position")
        return (5, position)
    encoded = atom["canonical_bytes_hex_value"]
    _require(
        type(encoded) is str
        and len(encoded) % 2 == 0
        and re.fullmatch(r"[0-9a-f]*", encoded) is not None,
        f"{label} canonical-byte spelling differs",
    )
    return (6, bytes.fromhex(encoded))


def _validate_state_cell(
    value: Any,
    *,
    label: str,
    resource_meter: ProofResourceMeter | None = None,
) -> dict[str, Any]:
    cell = _require_exact_keys(value, STATE_CELL_KEYS, label=label)
    kind = cell["cell_kind"]
    _require(
        kind
        in {
            "INACTIVE_GUARD_SENTINEL",
            "EXACT_ATOM",
            "SAFE_INTEGER_INTERVAL",
            "VERIFIER_DERIVED_CATALOG_POSITION",
        },
        f"{label} cell kind differs",
    )
    if kind == "INACTIVE_GUARD_SENTINEL":
        _require(
            cell["exact_atom"] is None
            and cell["integer_interval"] is None
            and cell["catalog_id"] is None
            and cell["catalog_position"] is None,
            f"{label} inactive-guard sentinel payload differs",
        )
    elif kind == "EXACT_ATOM":
        atom = cell["exact_atom"]
        _validate_primitive_atom(atom, label=f"{label} exact atom")
        _require(
            atom["atom_kind"] != "INACTIVE",
            f"{label} cannot contain the prefix-only INACTIVE atom",
        )
        _require(
            cell["integer_interval"] is None
            and cell["catalog_id"] is None
            and cell["catalog_position"] is None,
            f"{label} exact-cell inactive members differ",
        )
    elif kind == "SAFE_INTEGER_INTERVAL":
        interval = _require_exact_keys(
            cell["integer_interval"],
            INTEGER_INTERVAL_KEYS,
            label=f"{label} integer interval",
        )
        minimum = _require_integer(
            interval["inclusive_minimum"], label=f"{label} interval minimum"
        )
        maximum = _require_integer(
            interval["inclusive_maximum"], label=f"{label} interval maximum"
        )
        digits = _require_integer(
            interval["decimal_digit_count"],
            label=f"{label} interval digit count",
            minimum=1,
        )
        _require(
            minimum <= maximum
            and len(str(minimum)) == digits
            and len(str(maximum)) == digits,
            f"{label} interval bounds/digit width differ",
        )
        _require_sha256_array(
            interval["ordered_constant_affine_region_ids"],
            label=f"{label} affine-region IDs",
        )
        _require(
            cell["exact_atom"] is None
            and cell["catalog_id"] is None
            and cell["catalog_position"] is None,
            f"{label} interval-cell inactive members differ",
        )
    else:
        _require_sha256(cell["catalog_id"], label=f"{label} catalog ID")
        _require_integer(cell["catalog_position"], label=f"{label} catalog position")
        _require(
            cell["exact_atom"] is None and cell["integer_interval"] is None,
            f"{label} catalog-cell inactive members differ",
        )
    payload = {name: item for name, item in cell.items() if name != "state_cell_id"}
    _require(
        cell["state_cell_id"]
        == _semantic_id(
            STATE_CELL_DOMAIN,
            payload,
            resource_meter=resource_meter,
        ),
        f"{label} semantic identity differs",
    )
    return cell


def _validate_activation_guards(value: Any, *, label: str) -> list[dict[str, Any]]:
    clauses = _require_array(value, label=label, maximum_length=1_000_000)
    for position, clause_value in enumerate(clauses, 1):
        clause = _require_exact_keys(
            clause_value,
            ACTIVATION_GUARD_KEYS,
            label=f"{label} clause {position}",
        )
        _require(
            clause["guard_clause_position"] == position,
            f"{label} positions differ",
        )
        _require_sha256(
            clause["prior_choice_coordinate_plan_id"],
            label=f"{label} prior plan ID {position}",
        )
        _require(
            clause["guard_operator"] in {"EQUALS", "ARRAY_CARDINALITY_GREATER_THAN"},
            f"{label} operator differs",
        )
        atom_order = _validate_primitive_atom(
            clause["guard_atom"], label=f"{label} guard atom {position}"
        )
        _require(
            atom_order[0] != 0,
            f"{label} guard atom {position} is prefix-only INACTIVE",
        )
    return clauses


def _validate_codec_coordinate(value: Any, *, label: str) -> dict[str, Any]:
    coordinate = _require_exact_keys(value, CODEC_COORDINATE_KEYS, label=label)
    for name in ("validation_root_type_name", "codec_owner_type_name"):
        _require(
            type(coordinate[name]) is str and bool(coordinate[name]),
            f"{label} {name} differs",
        )
    path = _require_array(
        coordinate["codec_owner_typed_member_path"],
        label=f"{label} owner path",
        maximum_length=64,
    )
    _require(
        all(type(item) is str and bool(item) for item in path),
        f"{label} owner path differs",
    )
    _require(
        coordinate["codec_byte_bound_relation"] in {"LT", "LE"},
        f"{label} relation differs",
    )
    _require_integer(
        coordinate["codec_octet_limit"],
        label=f"{label} octet limit",
        minimum=1,
    )
    return coordinate


def _validate_winning_objective(value: Any, *, label: str) -> dict[str, Any]:
    objective = _require_exact_keys(value, WINNING_OBJECTIVE_KEYS, label=label)
    changed_count = _require_integer(
        objective["changed_limit_field_count"],
        label=f"{label} changed-limit count",
        maximum=len(LOCAL_SHUTDOWN_MUTABLE_LIMIT_MEMBERS),
    )
    _parse_canonical_uint128_text(
        objective["sum_of_absolute_integer_deltas"],
        label=f"{label} absolute-delta sum",
    )
    names = _require_array(
        objective["changed_member_names_in_lexical_order"],
        label=f"{label} changed member names",
        exact_length=changed_count,
    )
    _require(
        all(type(name) is str for name in names)
        and tuple(names) == tuple(sorted(names))
        and len(set(names)) == len(names)
        and set(names).issubset(LOCAL_SHUTDOWN_MUTABLE_LIMIT_MEMBERS),
        f"{label} changed member names differ",
    )
    values = _require_array(
        objective["resulting_changed_values_in_that_same_order"],
        label=f"{label} resulting changed values",
        exact_length=changed_count,
    )
    for position, item in enumerate(values, 1):
        _require_integer(item, label=f"{label} changed value {position}")
    return objective


def _validate_local_shutdown_mutated_spec(
    value: Any,
    *,
    baseline_spec: dict[str, Any],
    validated_registry: dict[str, Any],
    resource_meter: ProofResourceMeter,
    label: str,
) -> dict[str, Any]:
    """Validate the complete inline mutated spec except proof minimality."""

    record = _require_exact_keys(value, LOCAL_SHUTDOWN_OPERATION_SPEC_KEYS, label=label)
    baseline = _require_exact_keys(
        baseline_spec,
        LOCAL_SHUTDOWN_OPERATION_SPEC_KEYS,
        label=f"{label} resolved baseline",
    )
    _require(
        record["canonicalization_version"] == CANONICALIZATION_VERSION
        and record["measurement_schema_version"] == MEASUREMENT_SCHEMA_VERSION
        and record["record_domain"] == "RiskYieldMMA2MOperationSpecV4_9F_RawV8"
        and record["operation_kind"] == "LOCAL_SHUTDOWN"
        and record["spec_type"] == "LOCAL_SHUTDOWN_SPEC_V2",
        f"{label} wrapper/tag differs",
    )
    body = _require_exact_keys(
        record["spec"], LOCAL_SHUTDOWN_SPEC_BODY_KEYS, label=f"{label} body"
    )
    baseline_body = _require_exact_keys(
        baseline["spec"],
        LOCAL_SHUTDOWN_SPEC_BODY_KEYS,
        label=f"{label} resolved baseline body",
    )
    for member_name, integer_minimum, integer_maximum in LOCAL_SHUTDOWN_LIMIT_DOMAINS:
        _require_integer(
            body[member_name],
            label=f"{label} body {member_name}",
            minimum=integer_minimum,
            maximum=integer_maximum,
        )
    for member_name in LOCAL_SHUTDOWN_SPEC_BODY_KEYS - frozenset(
        LOCAL_SHUTDOWN_LIMIT_DOMAIN_BY_NAME
    ):
        _require(
            body[member_name] == baseline_body[member_name],
            f"{label} changes non-limit member {member_name}",
        )
    _require(
        body["maximum_peer_shutdown_polls"]
        == baseline_body["maximum_peer_shutdown_polls"]
        == 2,
        f"{label} changes the fixed peer-shutdown-poll member",
    )
    _require(
        body["maximum_terminal_ingress_plaintext_octets"]
        <= 16_384 * body["maximum_terminal_ingress_batches"]
        and 2 * body["maximum_terminal_ingress_parser_units"]
        <= body["maximum_terminal_ingress_plaintext_octets"]
        and body["maximum_terminal_tls_records"]
        <= body["maximum_terminal_ingress_batches"]
        and body["maximum_terminal_ingress_automatic_outputs"]
        <= body["maximum_terminal_ingress_parser_units"]
        and body["maximum_websocket_send_attempts"]
        <= 256 * (1 + body["maximum_terminal_ingress_automatic_outputs"]),
        f"{label} violates an intrinsic local-shutdown relation",
    )
    descriptors = [
        descriptor
        for descriptor in validated_registry["ordered_external_type_descriptors"]
        if descriptor["type_name"] == LOCAL_SHUTDOWN_BASELINE_SPEC_TYPE_NAME
    ]
    _require(len(descriptors) == 1, f"{label} wrapper descriptor differs")
    descriptor = descriptors[0]
    _require(
        descriptor["identity_field"] == "operation_spec_id"
        and descriptor["described_record_domain"]
        == "RiskYieldMMA2MOperationSpecV4_9F_RawV8",
        f"{label} wrapper identity descriptor differs",
    )
    identity_payload = {
        name: record[name] for name in descriptor["identity_payload_member_order"]
    }
    _require(
        record["operation_spec_id"]
        == _semantic_id(
            descriptor["described_record_domain"],
            identity_payload,
            resource_meter=resource_meter,
        ),
        f"{label} operation-spec identity differs",
    )
    _require(
        _canonical_octet_length(body) <= 3_145_728
        and _canonical_octet_length(record) <= 2_097_152,
        f"{label} violates a nested spec codec ceiling",
    )
    return record


def _validate_mutated_limit_members(
    value: Any,
    *,
    baseline_spec: dict[str, Any],
    mutated_spec: dict[str, Any],
    label: str,
) -> tuple[list[dict[str, Any]], int]:
    members = _require_array(
        value,
        label=label,
        maximum_length=len(LOCAL_SHUTDOWN_MUTABLE_LIMIT_MEMBERS),
    )
    _require(bool(members), f"{label} must be nonempty")
    baseline_body = baseline_spec["spec"]
    mutated_body = mutated_spec["spec"]
    previous_name: str | None = None
    total_delta = 0
    checked: list[dict[str, Any]] = []
    for array_position, member_value in enumerate(members, 1):
        member_label = f"{label} item {array_position}"
        member = _require_exact_keys(
            member_value, MUTATED_LIMIT_MEMBER_KEYS, label=member_label
        )
        name = member["member_name"]
        _require(
            type(name) is str and name in LOCAL_SHUTDOWN_MUTABLE_LIMIT_MEMBERS,
            f"{member_label} member name differs",
        )
        _require(
            previous_name is None or previous_name < name,
            f"{label} is not in strict lexical member-name order",
        )
        previous_name = name
        domain_position, integer_minimum, integer_maximum = (
            LOCAL_SHUTDOWN_LIMIT_DOMAIN_BY_NAME[name]
        )
        claimed_domain_position = _require_integer(
            member["domain_position"],
            label=f"{member_label} domain position",
            minimum=1,
            maximum=len(LOCAL_SHUTDOWN_LIMIT_DOMAINS),
        )
        _require(
            claimed_domain_position == domain_position,
            f"{member_label} domain position differs",
        )
        baseline_value = _require_integer(
            member["baseline_value"],
            label=f"{member_label} baseline value",
            minimum=integer_minimum,
            maximum=integer_maximum,
        )
        mutated_value = _require_integer(
            member["mutated_value"],
            label=f"{member_label} mutated value",
            minimum=integer_minimum,
            maximum=integer_maximum,
        )
        absolute_delta = _require_integer(
            member["absolute_delta"],
            label=f"{member_label} absolute delta",
            minimum=1,
        )
        _require(
            baseline_value == baseline_body[name]
            and mutated_value == mutated_body[name]
            and mutated_value != baseline_value
            and absolute_delta == abs(mutated_value - baseline_value),
            f"{member_label} duplicated mutation arithmetic differs",
        )
        total_delta += absolute_delta
        _require(total_delta <= UINT128_MAXIMUM, f"{label} delta sum exceeds UInt128")
        checked.append(member)
    actual_changed_names = tuple(
        sorted(
            name
            for name in LOCAL_SHUTDOWN_MUTABLE_LIMIT_MEMBERS
            if baseline_body[name] != mutated_body[name]
        )
    )
    _require(
        tuple(member["member_name"] for member in checked) == actual_changed_names,
        f"{label} does not contain every and only changed mutable limit",
    )
    return checked, total_delta


def _validate_local_shutdown_prospective_result(
    value: Any,
    *,
    mutated_spec: dict[str, Any],
    validated_registry: dict[str, Any],
    resource_meter: ProofResourceMeter,
    label: str,
) -> tuple[dict[str, Any], int]:
    record = _require_exact_keys(
        value, LOCAL_SHUTDOWN_OPERATION_RESULT_KEYS, label=label
    )
    _require(
        record["canonicalization_version"] == CANONICALIZATION_VERSION
        and record["measurement_schema_version"] == MEASUREMENT_SCHEMA_VERSION
        and record["record_domain"]
        == "RiskYieldMMA2MOperationResultEvidenceV4_9F_RawV8"
        and record["operation_kind"] == "LOCAL_SHUTDOWN"
        and record["result_type"] == "LOCAL_SHUTDOWN_RESULT_EVIDENCE_V2",
        f"{label} wrapper/tag differs",
    )
    _require_sha256(record["candidate_id"], label=f"{label} candidate ID")
    _require_sha256(record["attempt_id"], label=f"{label} attempt ID")
    body = _require_exact_keys(
        record["result"], LOCAL_SHUTDOWN_RESULT_BODY_KEYS, label=f"{label} body"
    )
    for name in (
        "local_shutdown_started_event_id",
        "shutdown_trace_root_sha256",
        "final_terminal_tls_staging_state_id",
        "decisive_terminal_transition_event_id",
        "transport_session_termination_id",
    ):
        _require_sha256(body[name], label=f"{label} body {name}")
    for name in (
        "local_shutdown_deadline_evidence_event_id",
        "local_close_dispatch_completion_event_id",
        "websocket_close_received_transition_event_id",
    ):
        _require_optional_sha256(body[name], label=f"{label} body {name}")
    arrays: dict[str, list[Any]] = {}
    for name, maximum_items in LOCAL_SHUTDOWN_RESULT_ARRAY_MAXIMUM_ITEMS.items():
        items = _require_array(
            body[name], label=f"{label} body {name}", maximum_length=maximum_items
        )
        for position, item in enumerate(items, 1):
            _require_sha256(item, label=f"{label} body {name} item {position}")
        _require(len(set(items)) == len(items), f"{label} body {name} repeats an ID")
        arrays[name] = items
    count_names = (
        "shutdown_trace_step_count",
        "final_terminal_ingress_batch_count",
        "final_terminal_ingress_ciphertext_octets",
        "final_terminal_ingress_plaintext_octets",
        "final_terminal_socket_receive_call_count",
        "final_terminal_tls_record_count",
        "final_terminal_tls_unwrap_iteration_count",
        "final_terminal_zero_progress_iteration_count",
        "final_terminal_ingress_parser_unit_count",
        "final_terminal_ingress_automatic_output_count",
        "final_websocket_send_attempt_count",
        "final_tls_control_send_attempt_count",
    )
    for name in count_names:
        _require_integer(body[name], label=f"{label} body {name}")
    _require_integer(
        body["final_peer_shutdown_poll_count"],
        label=f"{label} body final_peer_shutdown_poll_count",
        maximum=2,
    )
    _require(
        type(body["terminal_outcome"]) is str
        and body["terminal_outcome"] in LOCAL_SHUTDOWN_TERMINAL_OUTCOMES,
        f"{label} body terminal outcome differs",
    )
    attempts = arrays["ordered_terminal_ingress_read_attempt_event_ids"]
    results = arrays["ordered_terminal_ingress_read_result_event_ids"]
    commits = arrays["ordered_terminal_raw_ingress_commit_ids"]
    actors = arrays["ordered_terminal_raw_ingress_actor_event_ids"]
    transitions = arrays["ordered_terminal_parser_transition_event_ids"]
    _require(
        len(attempts) == len(results)
        and len(commits) == len(actors)
        and len(commits) <= len(results)
        and body["final_terminal_ingress_batch_count"] == len(attempts)
        and body["final_terminal_ingress_parser_unit_count"] >= len(transitions),
        f"{label} violates an intrinsic local-shutdown result relation",
    )
    spec = mutated_spec["spec"]
    result_to_limit = (
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
    _require(
        body["terminal_outcome"] == spec["expected_terminal_outcome"]
        and all(
            body[result_name] <= spec[limit_name]
            for result_name, limit_name in result_to_limit
        )
        and len(attempts) <= spec["maximum_terminal_ingress_batches"]
        and len(transitions) <= spec["maximum_terminal_ingress_parser_units"],
        f"{label} violates the signed-spec/result matrix",
    )
    descriptors = [
        descriptor
        for descriptor in validated_registry["ordered_external_type_descriptors"]
        if descriptor["type_name"] == LOCAL_SHUTDOWN_BASELINE_RESULT_TYPE_NAME
    ]
    _require(len(descriptors) == 1, f"{label} wrapper descriptor differs")
    descriptor = descriptors[0]
    identity_payload = {
        name: record[name] for name in descriptor["identity_payload_member_order"]
    }
    _require(
        record["result_evidence_id"]
        == _semantic_id(
            descriptor["described_record_domain"],
            identity_payload,
            resource_meter=resource_meter,
        ),
        f"{label} result identity differs",
    )
    _require(
        _canonical_octet_length(body) <= 3_145_728,
        f"{label} violates its nested result-body codec ceiling",
    )
    return record, _canonical_octet_length(record)


def _validate_expected_rejection_coordinate(
    value: Any,
    *,
    prospective_result_canonical_byte_length: int,
    label: str,
) -> dict[str, Any]:
    coordinate = _require_exact_keys(
        value, EXPECTED_REJECTION_COORDINATE_KEYS, label=label
    )
    _require(
        coordinate
        == {
            "record_type_name": LOCAL_SHUTDOWN_BASELINE_RESULT_TYPE_NAME,
            "typed_member_path": [],
            "validation_layer": "CODEC_BOUND",
            "codec_byte_bound_relation": "LT",
            "codec_octet_limit": 524_288,
            "observed_canonical_byte_length": (
                prospective_result_canonical_byte_length
            ),
            "failure_class": "CODEC_OCTET_LIMIT_VIOLATION",
        },
        f"{label} differs from the sole masked outer-codec coordinate",
    )
    return coordinate


def _derive_local_shutdown_proof_authority_ids(
    *,
    maximum_protocol_sha256: str,
    constraint_scope_profile_id: str,
    baseline_operation_spec_id: str,
    mutated_operation_spec_id: str,
    prospective_result_canonical_byte_length: int,
    prospective_result_canonical_sha256: str,
    resource_meter: ProofResourceMeter,
) -> tuple[str, str]:
    """Derive the two acyclic authorities inherited by every local proof node."""

    _require_sha256(maximum_protocol_sha256, label="local proof protocol SHA")
    _require_sha256(
        constraint_scope_profile_id,
        label="local proof constraint-scope profile ID",
    )
    _require_sha256(
        baseline_operation_spec_id,
        label="local proof baseline operation-spec ID",
    )
    _require_sha256(
        mutated_operation_spec_id,
        label="local proof mutated operation-spec ID",
    )
    _require_integer(
        prospective_result_canonical_byte_length,
        label="local proof prospective-result length",
        minimum=1,
    )
    _require_sha256(
        prospective_result_canonical_sha256,
        label="local proof prospective-result SHA",
    )
    scope_id = _semantic_id(
        LOCAL_SHUTDOWN_PROOF_SCOPE_DOMAIN,
        {
            "maximum_protocol_sha256": maximum_protocol_sha256,
            "source_inventory_sha256": INVENTORY_SEMANTIC_ID,
            "external_schema_registry_id": REGISTRY_ID,
            "rule_literal_authority_sha256": LITERAL_AUTHORITY_RAW_SHA256,
            "constraint_scope_profile_id": constraint_scope_profile_id,
            "baseline_operation_spec_id": baseline_operation_spec_id,
            "ordered_mutable_limit_member_names": list(
                LOCAL_SHUTDOWN_MUTABLE_LIMIT_MEMBERS
            ),
        },
        resource_meter=resource_meter,
    )
    context_id = _semantic_id(
        LOCAL_SHUTDOWN_PROOF_CONTEXT_DOMAIN,
        {
            "maximum_protocol_sha256": maximum_protocol_sha256,
            "mutated_operation_spec_id": mutated_operation_spec_id,
            "prospective_result_canonical_byte_length": (
                prospective_result_canonical_byte_length
            ),
            "prospective_result_canonical_sha256": (
                prospective_result_canonical_sha256
            ),
        },
        resource_meter=resource_meter,
    )
    return scope_id, context_id


def _validate_local_shutdown_minimality_certificate_outer(
    value: Any,
    *,
    maximum_protocol_sha256: str,
    baseline_operation_spec_id: str,
    mutated_operation_spec_id: str,
    prospective_result_canonical_byte_length: int,
    prospective_result_canonical_sha256: str,
    proof_scope_authority_id: str,
    proof_context_authority_id: str,
    validated_inventory: dict[str, Any],
    validated_registry: dict[str, Any],
    expected_winning_objective: dict[str, Any],
    resource_meter: ProofResourceMeter,
    proof_dag_validator: Callable[..., None] | None,
    label: str,
) -> dict[str, Any]:
    certificate = _require_exact_keys(
        value, LOCAL_SHUTDOWN_MINIMALITY_CERTIFICATE_KEYS, label=label
    )
    _require(
        certificate["certificate_version"]
        == "riskyieldmm.raw_v8_step2_external_schema_v2.local_shutdown_minimality_certificate.v1"
        and certificate["maximum_protocol_sha256"] == maximum_protocol_sha256
        and certificate["baseline_operation_spec_id"] == baseline_operation_spec_id
        and certificate["mutated_operation_spec_id"] == mutated_operation_spec_id,
        f"{label} version/protocol/spec binding differs",
    )
    mutable_count = _require_integer(
        certificate["mutable_limit_member_count"],
        label=f"{label} mutable-limit member count",
    )
    _require(
        mutable_count == len(LOCAL_SHUTDOWN_MUTABLE_LIMIT_MEMBERS)
        and certificate["ordered_mutable_limit_member_names"]
        == list(LOCAL_SHUTDOWN_MUTABLE_LIMIT_MEMBERS),
        f"{label} mutable-limit universe differs",
    )
    objective = _validate_winning_objective(
        certificate["winning_objective"], label=f"{label} winning objective"
    )
    _require(
        objective == expected_winning_objective,
        f"{label} winning objective differs from the retained mutation",
    )
    nodes = _require_array(
        certificate["ordered_proof_nodes"],
        label=f"{label} proof nodes",
        maximum_length=resource_meter.limits["proof_node_count"],
    )
    _require(bool(nodes), f"{label} proof DAG is empty")
    root_position = _require_integer(
        certificate["root_proof_node_position"],
        label=f"{label} root proof-node position",
        minimum=1,
        maximum=len(nodes),
    )
    _require(root_position == len(nodes), f"{label} root is not the final proof node")
    _require(
        proof_dag_validator is not None and callable(proof_dag_validator),
        f"{label} proof DAG validation is unavailable",
    )
    callback_result = proof_dag_validator(
        nodes,
        root_position=root_position,
        maximum_protocol_sha256=maximum_protocol_sha256,
        proof_scope_authority_id=proof_scope_authority_id,
        proof_context_authority_id=proof_context_authority_id,
        validated_inventory=validated_inventory,
        validated_registry=validated_registry,
        expected_winning_objective=expected_winning_objective,
        expected_prospective_result_canonical_byte_length=(
            prospective_result_canonical_byte_length
        ),
        expected_prospective_result_canonical_sha256=(
            prospective_result_canonical_sha256
        ),
        resource_meter=resource_meter,
        label=f"{label} proof DAG",
    )
    _require(callback_result is None, f"{label} proof validator returned a value")
    payload = {
        name: item
        for name, item in certificate.items()
        if name != "local_shutdown_minimality_certificate_id"
    }
    _require(
        certificate["local_shutdown_minimality_certificate_id"]
        == _semantic_id(
            LOCAL_SHUTDOWN_MINIMALITY_CERTIFICATE_DOMAIN,
            payload,
            resource_meter=resource_meter,
        ),
        f"{label} semantic identity differs",
    )
    return certificate


def _validate_local_shutdown_unrepresentable_outer_artifact(
    value: Any,
    *,
    maximum_protocol_sha256: str,
    validated_inventory: dict[str, Any],
    validated_registry: dict[str, Any],
    resource_meter: ProofResourceMeter,
    proof_dag_validator: Callable[..., None] | None,
    label: str,
) -> dict[str, Any]:
    """Validate all local counterexample facts outside the proof recurrence."""

    _require_sha256(maximum_protocol_sha256, label="maximum protocol SHA")
    artifact = _require_exact_keys(
        value, LOCAL_SHUTDOWN_UNREPRESENTABLE_KEYS, label=label
    )
    _require(
        artifact["artifact_version"]
        == "riskyieldmm.raw_v8_step2_external_schema_v2.local_shutdown_unrepresentable.v1"
        and artifact["canonicalization_version"] == CANONICALIZATION_VERSION
        and artifact["measurement_schema_version"] == MEASUREMENT_SCHEMA_VERSION
        and artifact["maximum_protocol_sha256"] == maximum_protocol_sha256
        and artifact["source_inventory_sha256"] == INVENTORY_SEMANTIC_ID
        and artifact["external_schema_registry_id"] == REGISTRY_ID
        and artifact["rule_literal_authority_sha256"] == LITERAL_AUTHORITY_RAW_SHA256
        and artifact["constraint_scope_profile_id"] == EXPECTED_SELECTED_PROFILE_IDS[3],
        f"{label} authority/version envelope differs",
    )
    profiles = _require_array(
        validated_inventory["operation_contracts"][
            "maximum_constraint_scope_profile_catalog"
        ],
        label=f"{label} profile authority",
        exact_length=408,
    )
    profile = profiles[2]
    _require(
        profile["maximum_constraint_scope_profile_id"]
        == EXPECTED_SELECTED_PROFILE_IDS[3],
        f"{label} profile-3 authority differs",
    )
    baseline = _resolve_v3_inventory_record_reference(
        artifact["baseline_spec_record_reference"],
        validated_inventory=validated_inventory,
        validated_registry=validated_registry,
        permitted_inventory_pointer_authority=(
            _inventory_pointer_authority_from_profile(
                profile, label=f"{label} profile-3 authority"
            )
        ),
        expected_inventory_pointer=LOCAL_SHUTDOWN_BASELINE_SPEC_POINTER,
        expected_record_type_name=LOCAL_SHUTDOWN_BASELINE_SPEC_TYPE_NAME,
        label=f"{label} baseline-spec reference",
        resource_meter=resource_meter,
    ).validated_record
    mutated_spec = _validate_local_shutdown_mutated_spec(
        artifact["mutated_spec"],
        baseline_spec=baseline.record,
        validated_registry=validated_registry,
        resource_meter=resource_meter,
        label=f"{label} mutated spec",
    )
    mutated_members, total_delta = _validate_mutated_limit_members(
        artifact["mutated_limit_members"],
        baseline_spec=baseline.record,
        mutated_spec=mutated_spec,
        label=f"{label} mutated limit members",
    )
    changed_count = len(mutated_members)
    claimed_changed_count = _require_integer(
        artifact["changed_limit_field_count"],
        label=f"{label} changed-limit field count",
        minimum=1,
        maximum=len(LOCAL_SHUTDOWN_MUTABLE_LIMIT_MEMBERS),
    )
    claimed_delta = _parse_canonical_uint128_text(
        artifact["sum_absolute_integer_deltas"],
        label=f"{label} absolute-delta sum",
    )
    _require(
        claimed_changed_count == changed_count and claimed_delta == total_delta,
        f"{label} duplicated mutation count/delta differs",
    )
    prospective_result, prospective_length = (
        _validate_local_shutdown_prospective_result(
            artifact["prospective_result"],
            mutated_spec=mutated_spec,
            validated_registry=validated_registry,
            resource_meter=resource_meter,
            label=f"{label} prospective result",
        )
    )
    _require(
        artifact["prospective_result_canonical_byte_length"] == prospective_length
        and prospective_length >= 524_288
        and artifact["outer_codec_byte_bound_relation"] == "LT"
        and artifact["outer_codec_octet_limit"] == 524_288,
        f"{label} prospective-result outer codec arithmetic differs",
    )
    _validate_expected_rejection_coordinate(
        artifact["expected_rejection_coordinate"],
        prospective_result_canonical_byte_length=prospective_length,
        label=f"{label} expected rejection coordinate",
    )
    expected_objective = {
        "changed_limit_field_count": changed_count,
        "sum_of_absolute_integer_deltas": str(total_delta),
        "changed_member_names_in_lexical_order": [
            member["member_name"] for member in mutated_members
        ],
        "resulting_changed_values_in_that_same_order": [
            member["mutated_value"] for member in mutated_members
        ],
    }
    _validate_winning_objective(
        expected_objective, label=f"{label} recomputed winning objective"
    )
    prospective_sha256, _ = _metered_canonical_sha256(
        prospective_result,
        meter=resource_meter,
    )
    proof_scope_authority_id, proof_context_authority_id = (
        _derive_local_shutdown_proof_authority_ids(
            maximum_protocol_sha256=maximum_protocol_sha256,
            constraint_scope_profile_id=artifact["constraint_scope_profile_id"],
            baseline_operation_spec_id=baseline.record_identity,
            mutated_operation_spec_id=mutated_spec["operation_spec_id"],
            prospective_result_canonical_byte_length=prospective_length,
            prospective_result_canonical_sha256=prospective_sha256,
            resource_meter=resource_meter,
        )
    )
    _validate_local_shutdown_minimality_certificate_outer(
        artifact["minimality_certificate"],
        maximum_protocol_sha256=maximum_protocol_sha256,
        baseline_operation_spec_id=baseline.record_identity,
        mutated_operation_spec_id=mutated_spec["operation_spec_id"],
        prospective_result_canonical_byte_length=prospective_length,
        prospective_result_canonical_sha256=prospective_sha256,
        proof_scope_authority_id=proof_scope_authority_id,
        proof_context_authority_id=proof_context_authority_id,
        validated_inventory=validated_inventory,
        validated_registry=validated_registry,
        expected_winning_objective=expected_objective,
        resource_meter=resource_meter,
        proof_dag_validator=proof_dag_validator,
        label=f"{label} minimality certificate",
    )
    payload = {
        name: item
        for name, item in artifact.items()
        if name != "local_shutdown_unrepresentable_id"
    }
    _require(
        artifact["local_shutdown_unrepresentable_id"]
        == _semantic_id(
            LOCAL_SHUTDOWN_UNREPRESENTABLE_DOMAIN,
            payload,
            resource_meter=resource_meter,
        ),
        f"{label} semantic identity differs",
    )
    _require(
        prospective_result is artifact["prospective_result"],
        f"{label} prospective result resolution differs",
    )
    return artifact


def _derive_local_shutdown_objective_prefix(
    value: Any,
    *,
    label: str,
) -> tuple[dict[str, Any], tuple[int, ...]]:
    processed_values = _require_array(
        value,
        label=f"{label} processed values",
        maximum_length=len(LOCAL_SHUTDOWN_MUTABLE_LIMIT_MEMBERS),
    )
    changed_names: list[str] = []
    changed_values: list[int] = []
    changed_domain_positions: list[int] = []
    delta_sum = 0
    for processed_position, item in enumerate(processed_values):
        member_name = LOCAL_SHUTDOWN_MUTABLE_LIMIT_MEMBERS[processed_position]
        current = _require_integer(
            item,
            label=f"{label} processed value {processed_position + 1}",
            minimum=1,
            maximum=LOCAL_SHUTDOWN_MUTABLE_DOMAIN_MAXIMUMS[member_name],
        )
        baseline = LOCAL_SHUTDOWN_BASELINE_MUTABLE_VALUES[member_name]
        if current == baseline:
            continue
        delta = abs(current - baseline)
        _require(
            delta_sum <= UINT128_MAXIMUM - delta,
            f"{label} absolute-delta sum exceeds checked UInt128",
        )
        delta_sum += delta
        changed_names.append(member_name)
        changed_values.append(current)
        changed_domain_positions.append(
            LOCAL_SHUTDOWN_LIMIT_DOMAIN_POSITIONS[member_name]
        )
    objective_prefix = {
        "objective_prefix_version": LOCAL_SHUTDOWN_OBJECTIVE_PREFIX_VERSION,
        "processed_mutable_member_count": len(processed_values),
        "changed_limit_field_count": len(changed_names),
        "sum_of_absolute_integer_deltas": str(delta_sum),
        "changed_member_names_in_lexical_order": changed_names,
        "resulting_changed_values_in_that_same_order": changed_values,
    }
    return objective_prefix, tuple(sorted(changed_domain_positions))


def _local_shutdown_objective_sort_key(
    objective_prefix: Mapping[str, Any],
    *,
    label: str,
) -> tuple[int, int, tuple[str, ...], tuple[int, ...]]:
    changed_count = _require_integer(
        objective_prefix.get("changed_limit_field_count"),
        label=f"{label} changed count",
        maximum=len(LOCAL_SHUTDOWN_MUTABLE_LIMIT_MEMBERS),
    )
    delta_sum = _parse_canonical_uint128_text(
        objective_prefix.get("sum_of_absolute_integer_deltas"),
        label=f"{label} delta sum",
    )
    names = _require_array(
        objective_prefix.get("changed_member_names_in_lexical_order"),
        label=f"{label} names",
        exact_length=changed_count,
    )
    values = _require_array(
        objective_prefix.get("resulting_changed_values_in_that_same_order"),
        label=f"{label} values",
        exact_length=changed_count,
    )
    _require(
        all(type(name) is str for name in names),
        f"{label} names differ",
    )
    checked_values = tuple(
        _require_integer(item, label=f"{label} value {position}", minimum=1)
        for position, item in enumerate(values, 1)
    )
    return changed_count, delta_sum, tuple(names), checked_values


def _derive_local_shutdown_intrinsic_relation_states(
    processed_values: Any,
    *,
    label: str,
) -> list[str]:
    values = _require_array(
        processed_values,
        label=f"{label} processed values",
        maximum_length=len(LOCAL_SHUTDOWN_MUTABLE_LIMIT_MEMBERS),
    )
    by_name: dict[str, int] = {}
    for position, item in enumerate(values, 1):
        member_name = LOCAL_SHUTDOWN_MUTABLE_LIMIT_MEMBERS[position - 1]
        by_name[member_name] = _require_integer(
            item,
            label=f"{label} processed value {position}",
            minimum=1,
            maximum=LOCAL_SHUTDOWN_MUTABLE_DOMAIN_MAXIMUMS[member_name],
        )
    relation_specs: tuple[tuple[tuple[str, ...], Any], ...] = (
        (
            (
                "maximum_terminal_ingress_plaintext_octets",
                "maximum_terminal_ingress_batches",
            ),
            lambda item: (
                item["maximum_terminal_ingress_plaintext_octets"]
                <= _checked_uint128(
                    16_384 * item["maximum_terminal_ingress_batches"],
                    label=f"{label} relation 1 product",
                )
            ),
        ),
        (
            (
                "maximum_terminal_ingress_parser_units",
                "maximum_terminal_ingress_plaintext_octets",
            ),
            lambda item: (
                _checked_uint128(
                    2 * item["maximum_terminal_ingress_parser_units"],
                    label=f"{label} relation 2 product",
                )
                <= item["maximum_terminal_ingress_plaintext_octets"]
            ),
        ),
        (
            (
                "maximum_terminal_tls_records",
                "maximum_terminal_ingress_batches",
            ),
            lambda item: (
                item["maximum_terminal_tls_records"]
                <= item["maximum_terminal_ingress_batches"]
            ),
        ),
        (
            (
                "maximum_terminal_ingress_automatic_outputs",
                "maximum_terminal_ingress_parser_units",
            ),
            lambda item: (
                item["maximum_terminal_ingress_automatic_outputs"]
                <= item["maximum_terminal_ingress_parser_units"]
            ),
        ),
        (
            (
                "maximum_websocket_send_attempts",
                "maximum_terminal_ingress_automatic_outputs",
            ),
            lambda item: (
                item["maximum_websocket_send_attempts"]
                <= _checked_uint128(
                    256
                    * _checked_uint128(
                        1 + item["maximum_terminal_ingress_automatic_outputs"],
                        label=f"{label} relation 5 addend",
                    ),
                    label=f"{label} relation 5 product",
                )
            ),
        ),
    )
    states: list[str] = []
    for required_names, evaluator in relation_specs:
        if not all(name in by_name for name in required_names):
            states.append("UNRESOLVED")
        else:
            states.append("TRUE" if evaluator(by_name) else "FALSE")
    return states


def _derive_local_shutdown_equivalence_key(
    *,
    processed_values: Any,
    ordered_intrinsic_relation_states: Any,
    intrinsically_feasible: bool,
    prospective_result_frontier_commitment_id: Any,
    label: str,
) -> dict[str, Any]:
    values = _require_array(
        processed_values,
        label=f"{label} processed values",
        maximum_length=len(LOCAL_SHUTDOWN_MUTABLE_LIMIT_MEMBERS),
    )
    for position, item in enumerate(values, 1):
        member_name = LOCAL_SHUTDOWN_MUTABLE_LIMIT_MEMBERS[position - 1]
        _require_integer(
            item,
            label=f"{label} processed value {position}",
            minimum=1,
            maximum=LOCAL_SHUTDOWN_MUTABLE_DOMAIN_MAXIMUMS[member_name],
        )
    relation_states = _require_array(
        ordered_intrinsic_relation_states,
        label=f"{label} relation states",
        exact_length=len(LOCAL_SHUTDOWN_INTRINSIC_RELATION_IDS),
    )
    _require(
        all(state in {"FALSE", "TRUE", "UNRESOLVED"} for state in relation_states),
        f"{label} relation state differs",
    )
    complete = len(values) == len(LOCAL_SHUTDOWN_MUTABLE_LIMIT_MEMBERS)
    _require(
        not complete or "UNRESOLVED" not in relation_states,
        f"{label} complete state retains an unresolved relation",
    )
    _require(
        relation_states
        == _derive_local_shutdown_intrinsic_relation_states(values, label=label),
        f"{label} relation states differ from the exact processed prefix",
    )
    _require(
        type(intrinsically_feasible) is bool,
        f"{label} intrinsic-feasibility flag differs",
    )
    _require(
        intrinsically_feasible == ("FALSE" not in relation_states),
        f"{label} intrinsic-feasibility flag differs from relation states",
    )
    if complete and intrinsically_feasible:
        _require(
            relation_states == ["TRUE"] * len(LOCAL_SHUTDOWN_INTRINSIC_RELATION_IDS),
            f"{label} complete feasible relation state differs",
        )
        commitment_id = _require_sha256(
            prospective_result_frontier_commitment_id,
            label=f"{label} prospective commitment ID",
        )
        continuation_kind = "COMPLETE_PROSPECTIVE_FRONTIER"
        exact_values: list[int] | None = None
    else:
        _require(
            prospective_result_frontier_commitment_id is None,
            f"{label} exact-prefix key has a prospective commitment",
        )
        commitment_id = None
        continuation_kind = "EXACT_PROCESSED_PREFIX"
        exact_values = list(values)
    return {
        "equivalence_key_version": LOCAL_SHUTDOWN_EQUIVALENCE_KEY_VERSION,
        "processed_mutable_member_count": len(values),
        "continuation_equivalence_kind": continuation_kind,
        "ordered_exact_processed_values": exact_values,
        "ordered_intrinsic_relation_states": list(relation_states),
        "prospective_result_frontier_commitment_id": commitment_id,
    }


def _validate_local_shutdown_recurrence_records(
    *,
    state_values: Any,
    transition_values: Any,
    dominance_deletion_values: Any,
    breakpoint_values: Any,
    interval_exclusion_values: Any,
    boundary_root_positions: list[int],
    boundary_witnesses: list[dict[str, Any]],
    proof_nodes: list[dict[str, Any]],
    expected_winning_objective: dict[str, Any],
    expected_winning_length: int,
    expected_winning_sha256: str,
    resource_meter: ProofResourceMeter,
    label: str,
) -> dict[str, Any]:
    """Validate the closed V1 recurrence over already-derived breakpoints.

    This routine deliberately does not claim to derive the breakpoint set or
    the piecewise-signature payloads.  It validates recurrence closure,
    dominance, winner selection, and the interval partition induced by a
    structurally valid breakpoint array.  Independent symbolic regeneration
    remains a separate acceptance gate.
    """

    _require(
        len(boundary_root_positions) == len(boundary_witnesses),
        f"{label} boundary root/witness cardinality differs",
    )
    witness_by_root: dict[int, dict[str, Any]] = {}
    commitment_by_root: dict[int, str] = {}
    maximum_by_root: dict[int, int] = {}
    for root_position, witness in zip(
        boundary_root_positions, boundary_witnesses, strict=True
    ):
        _require(
            root_position not in witness_by_root,
            f"{label} repeats a boundary root",
        )
        _require_integer(
            root_position,
            label=f"{label} boundary root position",
            minimum=1,
            maximum=len(proof_nodes),
        )
        root = proof_nodes[root_position - 1]
        commitment = _require_exact_keys(
            root["frontier_commitment"],
            FRONTIER_COMMITMENT_KEYS,
            label=f"{label} boundary root {root_position} commitment",
        )
        commitment_by_root[root_position] = _require_sha256(
            commitment["frontier_commitment_id"],
            label=f"{label} boundary root {root_position} commitment ID",
        )
        maximum_by_root[root_position] = _require_integer(
            commitment["maximum_attainable_octets"],
            label=f"{label} boundary root {root_position} maximum",
            minimum=1,
        )
        witness_by_root[root_position] = witness

    raw_states = _require_array(
        state_values,
        label=f"{label} states",
        maximum_length=1_000_000,
    )
    _require(bool(raw_states), f"{label} states are empty")
    checked_states: list[dict[str, Any]] = []
    state_order_keys: list[tuple[Any, ...]] = []
    processed_prefixes: set[tuple[int, ...]] = set()
    for state_position, state_value in enumerate(raw_states, 1):
        state_label = f"{label} state {state_position}"
        state = _require_exact_keys(
            state_value,
            LOCAL_SHUTDOWN_RECURRENCE_STATE_KEYS,
            label=state_label,
        )
        _require(
            state["state_position"] == state_position,
            f"{state_label} position differs",
        )
        processed_count = _require_integer(
            state["processed_mutable_member_count"],
            label=f"{state_label} processed count",
            maximum=len(LOCAL_SHUTDOWN_MUTABLE_LIMIT_MEMBERS),
        )
        processed_values = _require_array(
            state["ordered_processed_values"],
            label=f"{state_label} processed values",
            exact_length=processed_count,
        )
        objective_prefix, changed_positions = _derive_local_shutdown_objective_prefix(
            processed_values,
            label=f"{state_label} objective prefix",
        )
        _require(
            state["ordered_changed_domain_positions"] == list(changed_positions),
            f"{state_label} changed-domain positions differ",
        )
        delta_sum = _parse_canonical_uint128_text(
            state["sum_absolute_integer_deltas"],
            label=f"{state_label} absolute-delta sum",
        )
        _require(
            state["sum_absolute_integer_deltas"]
            == objective_prefix["sum_of_absolute_integer_deltas"],
            f"{state_label} objective-prefix delta differs",
        )
        relation_states = _require_array(
            state["ordered_intrinsic_relation_states"],
            label=f"{state_label} intrinsic relation states",
            exact_length=len(LOCAL_SHUTDOWN_INTRINSIC_RELATION_IDS),
        )
        derived_relation_states = _derive_local_shutdown_intrinsic_relation_states(
            processed_values,
            label=f"{state_label} intrinsic relation states",
        )
        _require(
            relation_states == derived_relation_states,
            f"{state_label} intrinsic relation states differ",
        )
        status = state["state_status"]
        _require(
            status in {"RETAINED", "INFEASIBLE", "DOMINATED"},
            f"{state_label} status differs",
        )
        complete = processed_count == len(LOCAL_SHUTDOWN_MUTABLE_LIMIT_MEMBERS)
        feasible = "FALSE" not in relation_states
        root_position = state["prospective_result_root_position"]
        if not feasible:
            _require(
                status == "INFEASIBLE" and root_position is None,
                f"{state_label} infeasible status/root differs",
            )
            commitment_id = None
        elif not complete:
            _require(
                status == "RETAINED" and root_position is None,
                f"{state_label} partial feasible status/root differs",
            )
            commitment_id = None
        else:
            root_position = _require_integer(
                root_position,
                label=f"{state_label} prospective root",
                minimum=1,
                maximum=len(proof_nodes),
            )
            _require(
                root_position in witness_by_root,
                f"{state_label} prospective root is not a local boundary root",
            )
            candidate = witness_by_root[root_position]["candidate_mutated_spec"]
            _require(
                type(candidate) is dict and type(candidate.get("spec")) is dict,
                f"{state_label} boundary candidate spec is not complete",
            )
            candidate_values = [
                candidate["spec"].get(member_name)
                for member_name in LOCAL_SHUTDOWN_MUTABLE_LIMIT_MEMBERS
            ]
            _require(
                candidate_values == processed_values,
                f"{state_label} boundary candidate values differ",
            )
            commitment_id = commitment_by_root[root_position]
        equivalence_key = _derive_local_shutdown_equivalence_key(
            processed_values=processed_values,
            ordered_intrinsic_relation_states=relation_states,
            intrinsically_feasible=feasible,
            prospective_result_frontier_commitment_id=commitment_id,
            label=f"{state_label} equivalence key",
        )
        objective_key = _local_shutdown_objective_sort_key(
            objective_prefix,
            label=f"{state_label} objective",
        )
        state_payload = {
            name: item for name, item in state.items() if name != "recurrence_state_id"
        }
        _require(
            state["recurrence_state_id"]
            == _semantic_id(
                LOCAL_SHUTDOWN_RECURRENCE_STATE_DOMAIN,
                state_payload,
                resource_meter=resource_meter,
            ),
            f"{state_label} semantic identity differs",
        )
        prefix_key = tuple(processed_values)
        _require(
            prefix_key not in processed_prefixes,
            f"{label} repeats a processed recurrence prefix",
        )
        processed_prefixes.add(prefix_key)
        status_rank = {"RETAINED": 0, "INFEASIBLE": 1, "DOMINATED": 2}[status]
        root_sort_key = (0, 0) if root_position is None else (1, root_position)
        state_order_keys.append(
            (
                processed_count,
                _canonical_bytes(processed_values),
                _canonical_bytes(state["ordered_changed_domain_positions"]),
                delta_sum,
                _canonical_bytes(relation_states),
                root_sort_key,
                status_rank,
            )
        )
        checked_states.append(
            {
                "record": state,
                "processed_values": list(processed_values),
                "objective_prefix": objective_prefix,
                "objective_key": objective_key,
                "equivalence_key": equivalence_key,
                "equivalence_key_bytes": _canonical_bytes(equivalence_key),
                "complete": complete,
                "feasible": feasible,
            }
        )
    _require(
        state_order_keys == sorted(state_order_keys),
        f"{label} state canonical order differs",
    )
    _require(
        checked_states[0]["record"]["processed_mutable_member_count"] == 0
        and checked_states[0]["record"]["ordered_processed_values"] == []
        and checked_states[0]["record"]["state_status"] == "RETAINED",
        f"{label} does not begin with the unique empty retained state",
    )

    complete_groups: dict[bytes, list[dict[str, Any]]] = {}
    for checked_state in checked_states:
        if checked_state["complete"] and checked_state["feasible"]:
            complete_groups.setdefault(
                checked_state["equivalence_key_bytes"], []
            ).append(checked_state)
    for group_position, group in enumerate(complete_groups.values(), 1):
        ordered_group = sorted(group, key=lambda item: item["objective_key"])
        _require(
            len({item["objective_key"] for item in group}) == len(group),
            f"{label} complete group {group_position} retains an equal-objective duplicate",
        )
        for group_ordinal, checked_state in enumerate(ordered_group):
            expected_status = "RETAINED" if group_ordinal == 0 else "DOMINATED"
            _require(
                checked_state["record"]["state_status"] == expected_status,
                f"{label} complete group {group_position} status differs",
            )

    breakpoint_records = _require_array(
        breakpoint_values,
        label=f"{label} breakpoints",
        maximum_length=1_000_000,
    )
    breakpoints_by_position: dict[int, dict[str, Any]] = {}
    breakpoint_order_keys: list[tuple[Any, ...]] = []
    breakpoint_candidate_keys: set[tuple[int, int, int]] = set()
    breakpoint_count_by_source: Counter[int] = Counter()
    for breakpoint_position, breakpoint_value in enumerate(breakpoint_records, 1):
        breakpoint_label = f"{label} breakpoint {breakpoint_position}"
        breakpoint = _require_exact_keys(
            breakpoint_value,
            LOCAL_SHUTDOWN_BREAKPOINT_KEYS,
            label=breakpoint_label,
        )
        _require(
            breakpoint["breakpoint_position"] == breakpoint_position,
            f"{breakpoint_label} position differs",
        )
        source_position = _require_integer(
            breakpoint["source_state_position"],
            label=f"{breakpoint_label} source state",
            minimum=1,
            maximum=len(checked_states),
        )
        source = checked_states[source_position - 1]
        source_record = source["record"]
        source_count = source_record["processed_mutable_member_count"]
        _require(
            source_record["state_status"] == "RETAINED"
            and source_count < len(LOCAL_SHUTDOWN_MUTABLE_LIMIT_MEMBERS),
            f"{breakpoint_label} source is not a retained partial state",
        )
        member_name = LOCAL_SHUTDOWN_MUTABLE_LIMIT_MEMBERS[source_count]
        expected_domain_position = LOCAL_SHUTDOWN_LIMIT_DOMAIN_POSITIONS[member_name]
        _require(
            breakpoint["domain_position"] == expected_domain_position
            and breakpoint["member_name"] == member_name,
            f"{breakpoint_label} next lexical domain differs",
        )
        candidate_value = _require_integer(
            breakpoint["candidate_value"],
            label=f"{breakpoint_label} candidate value",
            minimum=1,
            maximum=LOCAL_SHUTDOWN_MUTABLE_DOMAIN_MAXIMUMS[member_name],
        )
        kind = breakpoint["breakpoint_kind"]
        _require(
            kind in LOCAL_SHUTDOWN_BREAKPOINT_KINDS,
            f"{breakpoint_label} kind differs",
        )
        relation_id = breakpoint["source_relation_id"]
        root_position = breakpoint["prospective_result_root_position"]
        if kind == "INTRINSIC_RELATION_BOUNDARY":
            _require(
                relation_id in LOCAL_SHUTDOWN_INTRINSIC_RELATION_IDS
                and root_position is None,
                f"{breakpoint_label} relation provenance differs",
            )
        elif kind == "PROSPECTIVE_BYTE_BOUNDARY":
            _require(
                relation_id is None
                and type(root_position) is int
                and root_position in witness_by_root,
                f"{breakpoint_label} prospective provenance differs",
            )
        else:
            _require(
                relation_id is None and root_position is None,
                f"{breakpoint_label} inactive provenance differs",
            )
        candidate_key = (source_position, expected_domain_position, candidate_value)
        _require(
            candidate_key not in breakpoint_candidate_keys,
            f"{label} repeats a source/domain/candidate breakpoint",
        )
        breakpoint_candidate_keys.add(candidate_key)
        breakpoint_count_by_source[source_position] += 1
        relation_sort = (
            0
            if relation_id is None
            else 1 + LOCAL_SHUTDOWN_INTRINSIC_RELATION_IDS.index(relation_id)
        )
        root_sort = (0, 0) if root_position is None else (1, root_position)
        breakpoint_order_keys.append(
            (
                source_position,
                expected_domain_position,
                candidate_value,
                LOCAL_SHUTDOWN_BREAKPOINT_KINDS.index(kind),
                relation_sort,
                root_sort,
            )
        )
        breakpoints_by_position[breakpoint_position] = breakpoint
    _require(
        breakpoint_order_keys == sorted(breakpoint_order_keys),
        f"{label} breakpoint canonical order differs",
    )
    retained_partial_positions = {
        item["record"]["state_position"]
        for item in checked_states
        if not item["complete"] and item["record"]["state_status"] == "RETAINED"
    }
    _require(
        set(breakpoint_count_by_source) == retained_partial_positions,
        f"{label} breakpoint source coverage differs",
    )

    expected_interval_rows: list[tuple[int, int, int, int, int]] = []
    breakpoints_by_source: dict[int, list[dict[str, Any]]] = {}
    for breakpoint in breakpoint_records:
        breakpoints_by_source.setdefault(
            breakpoint["source_state_position"], []
        ).append(breakpoint)
    for source_position in sorted(breakpoints_by_source):
        source_breakpoints = sorted(
            breakpoints_by_source[source_position],
            key=lambda item: item["candidate_value"],
        )
        baseline = LOCAL_SHUTDOWN_BASELINE_MUTABLE_VALUES[
            source_breakpoints[0]["member_name"]
        ]
        for lower, upper in zip(
            source_breakpoints, source_breakpoints[1:], strict=False
        ):
            if upper["candidate_value"] <= lower["candidate_value"] + 1:
                continue
            lower_distance = abs(lower["candidate_value"] - baseline)
            upper_distance = abs(upper["candidate_value"] - baseline)
            _require(
                lower_distance != upper_distance,
                f"{label} interval endpoints have an ambiguous delta direction",
            )
            dominating = lower if lower_distance < upper_distance else upper
            expected_interval_rows.append(
                (
                    source_position,
                    lower["domain_position"],
                    lower["candidate_value"] + 1,
                    upper["candidate_value"] - 1,
                    dominating["breakpoint_position"],
                )
            )
    interval_records = _require_array(
        interval_exclusion_values,
        label=f"{label} interval exclusions",
        exact_length=len(expected_interval_rows),
    )
    for interval_position, (interval_value, expected_row) in enumerate(
        zip(interval_records, expected_interval_rows, strict=True),
        1,
    ):
        interval_label = f"{label} interval exclusion {interval_position}"
        interval = _require_exact_keys(
            interval_value,
            LOCAL_SHUTDOWN_INTERVAL_EXCLUSION_KEYS,
            label=interval_label,
        )
        _require(
            interval["interval_position"] == interval_position
            and (
                interval["source_state_position"],
                interval["domain_position"],
                interval["first_omitted_value"],
                interval["last_omitted_value"],
                interval["dominating_breakpoint_position"],
            )
            == expected_row,
            f"{interval_label} induced partition/dominator differs",
        )
        root_position = _require_integer(
            interval["prospective_result_root_position"],
            label=f"{interval_label} prospective root",
            minimum=1,
            maximum=len(proof_nodes),
        )
        _require(
            root_position in witness_by_root,
            f"{interval_label} prospective root is not a boundary root",
        )
        _require_sha256(
            interval["piecewise_signature_id"],
            label=f"{interval_label} piecewise signature ID",
        )
    resource_meter.add("frontier_transition_count", len(interval_records))

    transition_records = _require_array(
        transition_values,
        label=f"{label} transitions",
        exact_length=len(breakpoint_records),
    )
    transition_pairs: set[tuple[int, int]] = set()
    transition_order_keys: list[tuple[int, int]] = []
    reached_state_positions: set[int] = set()
    for transition_position, transition_value in enumerate(transition_records, 1):
        transition_label = f"{label} transition {transition_position}"
        transition = _require_exact_keys(
            transition_value,
            LOCAL_SHUTDOWN_RECURRENCE_TRANSITION_KEYS,
            label=transition_label,
        )
        _require(
            transition["transition_position"] == transition_position,
            f"{transition_label} position differs",
        )
        source_position = _require_integer(
            transition["source_state_position"],
            label=f"{transition_label} source state",
            minimum=1,
            maximum=len(checked_states),
        )
        breakpoint_position = _require_integer(
            transition["breakpoint_position"],
            label=f"{transition_label} breakpoint",
            minimum=1,
            maximum=len(breakpoint_records),
        )
        result_position = _require_integer(
            transition["result_state_position"],
            label=f"{transition_label} result state",
            minimum=1,
            maximum=len(checked_states),
        )
        source = checked_states[source_position - 1]["record"]
        result = checked_states[result_position - 1]["record"]
        breakpoint = breakpoints_by_position[breakpoint_position]
        _require(
            breakpoint["source_state_position"] == source_position
            and source["state_status"] == "RETAINED"
            and source["processed_mutable_member_count"]
            < len(LOCAL_SHUTDOWN_MUTABLE_LIMIT_MEMBERS),
            f"{transition_label} source/breakpoint binding differs",
        )
        expected_result_values = [
            *source["ordered_processed_values"],
            breakpoint["candidate_value"],
        ]
        _require(
            result["processed_mutable_member_count"]
            == source["processed_mutable_member_count"] + 1
            and result["ordered_processed_values"] == expected_result_values,
            f"{transition_label} does not append its breakpoint candidate",
        )
        expected_kind = {
            "RETAINED": "EXTEND_RETAINED",
            "INFEASIBLE": "EXTEND_INFEASIBLE",
            "DOMINATED": "EXTEND_DOMINATED",
        }[result["state_status"]]
        _require(
            transition["transition_kind"] == expected_kind,
            f"{transition_label} result status/kind differs",
        )
        false_relation_positions = [
            position
            for position, relation_state in enumerate(
                result["ordered_intrinsic_relation_states"]
            )
            if relation_state == "FALSE"
        ]
        expected_failed_relation_id = (
            LOCAL_SHUTDOWN_INTRINSIC_RELATION_IDS[false_relation_positions[0]]
            if expected_kind == "EXTEND_INFEASIBLE"
            else None
        )
        _require(
            transition["failed_relation_id"] == expected_failed_relation_id,
            f"{transition_label} first failed relation differs",
        )
        transition_pair = (source_position, breakpoint_position)
        _require(
            transition_pair not in transition_pairs,
            f"{label} repeats a source/breakpoint transition",
        )
        transition_pairs.add(transition_pair)
        transition_order_keys.append(transition_pair)
        reached_state_positions.add(result_position)
        transition_payload = {
            name: item
            for name, item in transition.items()
            if name != "recurrence_transition_id"
        }
        _require(
            transition["recurrence_transition_id"]
            == _semantic_id(
                LOCAL_SHUTDOWN_RECURRENCE_TRANSITION_DOMAIN,
                transition_payload,
                resource_meter=resource_meter,
            ),
            f"{transition_label} semantic identity differs",
        )
    _require(
        transition_order_keys == sorted(transition_order_keys),
        f"{label} transition canonical order differs",
    )
    expected_transition_pairs = {
        (breakpoint["source_state_position"], breakpoint_position)
        for breakpoint_position, breakpoint in breakpoints_by_position.items()
    }
    _require(
        transition_pairs == expected_transition_pairs,
        f"{label} transition coverage differs",
    )
    _require(
        reached_state_positions == set(range(2, len(checked_states) + 1)),
        f"{label} contains an unreachable or omitted noninitial state",
    )
    resource_meter.add("frontier_transition_count", len(transition_records))

    dominated_states = [
        item for item in checked_states if item["record"]["state_status"] == "DOMINATED"
    ]
    deletion_records = _require_array(
        dominance_deletion_values,
        label=f"{label} dominance deletions",
        exact_length=len(dominated_states),
    )
    dominated_by_position = {
        item["record"]["state_position"]: item for item in dominated_states
    }
    seen_deleted_positions: set[int] = set()
    previous_deleted_position = 0
    for deletion_position, deletion_value in enumerate(deletion_records, 1):
        deletion_label = f"{label} dominance deletion {deletion_position}"
        deletion = _require_exact_keys(
            deletion_value,
            LOCAL_SHUTDOWN_DOMINANCE_DELETION_KEYS,
            label=deletion_label,
        )
        _require(
            deletion["deletion_position"] == deletion_position,
            f"{deletion_label} position differs",
        )
        deleted_position = _require_integer(
            deletion["deleted_state_position"],
            label=f"{deletion_label} deleted state",
            minimum=1,
            maximum=len(checked_states),
        )
        retained_position = _require_integer(
            deletion["retained_state_position"],
            label=f"{deletion_label} retained state",
            minimum=1,
            maximum=len(checked_states),
        )
        _require(
            deleted_position > previous_deleted_position
            and deleted_position in dominated_by_position
            and deleted_position not in seen_deleted_positions,
            f"{deletion_label} deleted-state order/coverage differs",
        )
        previous_deleted_position = deleted_position
        seen_deleted_positions.add(deleted_position)
        deleted = dominated_by_position[deleted_position]
        group = complete_groups[deleted["equivalence_key_bytes"]]
        retained = min(group, key=lambda item: item["objective_key"])
        _require(
            retained["record"]["state_position"] == retained_position
            and retained["record"]["state_status"] == "RETAINED"
            and retained["complete"]
            and retained["feasible"]
            and retained["equivalence_key_bytes"] == deleted["equivalence_key_bytes"]
            and retained["objective_key"] < deleted["objective_key"],
            f"{deletion_label} dominator proof differs",
        )
        equivalence_digest, _ = _metered_canonical_sha256(
            deleted["equivalence_key"],
            meter=resource_meter,
        )
        _require(
            deletion["equivalence_state_key_sha256"] == equivalence_digest
            and deletion["dominance_reason"]
            == "BYTE_EQUAL_STATE_KEY_AND_OBJECTIVE_PREFIX_NO_WORSE",
            f"{deletion_label} key hash/reason differs",
        )
    _require(
        seen_deleted_positions == set(dominated_by_position),
        f"{label} dominance-deletion coverage differs",
    )

    referenced_boundary_roots = {
        item["record"]["prospective_result_root_position"]
        for item in checked_states
        if item["complete"] and item["feasible"]
    }
    _require(
        referenced_boundary_roots == set(boundary_root_positions),
        f"{label} complete-state/boundary-root coverage differs",
    )
    eligible = [
        item
        for item in checked_states
        if item["complete"]
        and item["feasible"]
        and item["record"]["state_status"] == "RETAINED"
        and maximum_by_root[item["record"]["prospective_result_root_position"]]
        >= 524_288
    ]
    _require(bool(eligible), f"{label} has no retained outer-limit witness")
    winner = min(eligible, key=lambda item: item["objective_key"])
    winner_objective = {
        name: item
        for name, item in winner["objective_prefix"].items()
        if name not in {"objective_prefix_version", "processed_mutable_member_count"}
    }
    winner_root_position = winner["record"]["prospective_result_root_position"]
    winner_witness = witness_by_root[winner_root_position]
    _require(
        winner_objective == expected_winning_objective
        and winner_witness["prospective_result_canonical_byte_length"]
        == expected_winning_length
        and winner_witness["prospective_result_canonical_sha256"]
        == expected_winning_sha256,
        f"{label} winning objective/result differs",
    )
    return {
        "winner_state": winner["record"],
        "winner_objective": winner_objective,
        "winner_root_position": winner_root_position,
        "winner_length": expected_winning_length,
        "winner_sha256": expected_winning_sha256,
    }


def _validate_state_dimensions(
    value: Any,
    *,
    label: str,
    resource_meter: ProofResourceMeter | None = None,
) -> tuple[list[dict[str, Any]], str]:
    dimensions = _require_array(value, label=label, maximum_length=8_192)
    descriptor_ids: list[str] = []
    for position, dimension_value in enumerate(dimensions, 1):
        dimension = _require_exact_keys(
            dimension_value,
            STATE_DIMENSION_KEYS,
            label=f"{label} item {position}",
        )
        _require(
            dimension["dimension_position"] == position,
            f"{label} positions differ",
        )
        _require(
            dimension["dimension_kind"]
            in {
                "NULLABILITY_BRANCH",
                "BOOLEAN_VALUE",
                "SAFE_INTEGER_VALUE",
                "TEXT_RELATION_CLASS",
                "TEXT_CANONICAL_LENGTH",
                "ARRAY_CARDINALITY",
                "ARRAY_ORDER_CLASS",
                "ARRAY_UNIQUENESS_CLASS",
                "UNION_ALTERNATIVE_POSITION",
                "CATALOG_POSITION",
                "ROOT_FAMILY_POSITION",
                "MODE_ATTEMPT_POSITION",
                "OBSERVATION_ROLE_POSITION",
                "SEQUENCE_ORDINAL",
                "TEXT_VALUE",
            },
            f"{label} dimension kind differs",
        )
        _validate_proof_subject_locator(
            dimension["subject_locator"],
            label=f"{label} locator {position}",
            resource_meter=resource_meter,
        )
        _require(
            dimension["value_schema_id"] is None
            or _is_sha256(dimension["value_schema_id"]),
            f"{label} value schema identity differs",
        )
        _require(
            dimension["comparison_semantics"]
            in {
                "NULL_BEFORE_NON_NULL",
                "FALSE_BEFORE_TRUE",
                "MATHEMATICAL_INTEGER",
                "UNICODE_SCALAR_LEXICAL",
                "CARDINALITY_THEN_ITEMS",
                "FROZEN_CATALOG_POSITION",
                "CANONICAL_OCTET_LEXICAL",
            },
            f"{label} comparison semantics differ",
        )
        _validate_activation_guards(
            dimension["ordered_activation_guard_clauses"],
            label=f"{label} activation guards {position}",
        )
        payload = {
            name: dimension[name]
            for name in dimension
            if name != "observable_descriptor_id"
        }
        recomputed = _semantic_id(
            OBSERVABLE_DESCRIPTOR_DOMAIN,
            payload,
            resource_meter=resource_meter,
        )
        _require(
            dimension["observable_descriptor_id"] == recomputed,
            f"{label} observable descriptor identity differs",
        )
        descriptor_ids.append(recomputed)
    signature_id = _semantic_id(
        STATE_SIGNATURE_DOMAIN,
        {"ordered_state_dimensions": dimensions},
        resource_meter=resource_meter,
    )
    return dimensions, signature_id


def _bitmap_set_bit_positions(bitmap: int) -> tuple[int, ...]:
    positions: list[int] = []
    remaining = bitmap
    while remaining:
        low = remaining & -remaining
        positions.append(low.bit_length() - 1)
        remaining ^= low
    return tuple(positions)


def _stream_expanded_frontier_digest(
    state_frontiers: list[dict[str, Any]],
) -> tuple[str | None, int, int | None, int | None, int]:
    return _stream_expanded_frontier_digest_metered(
        state_frontiers,
        meter=ProofResourceMeter(phase=SEED_CAP_DERIVATION_PHASE),
    )


def _stream_expanded_frontier_digest_metered(
    state_frontiers: list[dict[str, Any]],
    *,
    meter: ProofResourceMeter,
) -> tuple[str | None, int, int | None, int | None, int]:
    point_count = 0
    minimum: int | None = None
    maximum: int | None = None
    canonicalized_octets = 2
    for frontier in state_frontiers:
        state_key = frontier["state_key"]
        for run in frontier["ordered_length_bitmap_runs"]:
            bitmap = int(run["attainable_length_bitmap_hex"], 16)
            offsets = _bitmap_set_bit_positions(bitmap)
            blocks = run["last_block_index"] - run["first_block_index"] + 1
            run_point_count = blocks * len(offsets)
            prospective = point_count + run_point_count
            _require(
                prospective <= SAFE_INTEGER_MAXIMUM,
                "expanded frontier point count exceeds safe-I-JSON arithmetic",
            )
            meter.ensure_at_most(
                "frontier_expanded_point_count",
                meter.value("frontier_expanded_point_count") + prospective,
            )
            meter.ensure_at_most("maximum_frontier_width", prospective)
            for block in range(run["first_block_index"], run["last_block_index"] + 1):
                for offset in offsets:
                    length = block * 256 + offset
                    record = {
                        "canonical_byte_length": length,
                        "state_key": state_key,
                    }
                    record_octets = _canonical_octet_length(record)
                    prospective_canonicalized = (
                        canonicalized_octets + int(point_count != 0) + record_octets
                    )
                    _require(
                        prospective_canonicalized <= SAFE_INTEGER_MAXIMUM,
                        "expanded frontier canonical length exceeds safe-I-JSON "
                        "arithmetic",
                    )
                    meter.ensure_at_most(
                        "frontier_canonicalized_octets",
                        meter.value("frontier_canonicalized_octets")
                        + prospective_canonicalized,
                    )
                    meter.ensure_at_most(
                        "hash_preimage_octets",
                        meter.value("hash_preimage_octets") + prospective_canonicalized,
                    )
                    canonicalized_octets = prospective_canonicalized
                    point_count += 1
                    minimum = length if minimum is None else min(minimum, length)
                    maximum = length if maximum is None else max(maximum, length)
    increments = {
        "frontier_expanded_point_count": point_count,
        "frontier_canonicalized_octets": canonicalized_octets,
    }
    if point_count:
        increments["hash_preimage_octets"] = canonicalized_octets
    meter.reserve(increments)
    meter.observe_maximum("maximum_frontier_width", point_count)
    if not point_count:
        return None, 0, None, None, canonicalized_octets

    digest = hashlib.sha256()
    digest.update(b"[")
    first_record = True
    for frontier in state_frontiers:
        state_key = frontier["state_key"]
        for run in frontier["ordered_length_bitmap_runs"]:
            bitmap = int(run["attainable_length_bitmap_hex"], 16)
            offsets = _bitmap_set_bit_positions(bitmap)
            for block in range(run["first_block_index"], run["last_block_index"] + 1):
                for offset in offsets:
                    if not first_record:
                        digest.update(b",")
                    record = {
                        "canonical_byte_length": block * 256 + offset,
                        "state_key": state_key,
                    }
                    for chunk in _canonical_text_chunks(record):
                        digest.update(chunk.encode("utf-8", errors="strict"))
                    first_record = False
    digest.update(b"]")
    return digest.hexdigest(), point_count, minimum, maximum, canonicalized_octets


def _validate_cell_for_dimension(
    cell: dict[str, Any],
    dimension: dict[str, Any],
    *,
    label: str,
) -> None:
    dimension_kind = dimension["dimension_kind"]
    cell_kind = cell["cell_kind"]
    if cell_kind == "INACTIVE_GUARD_SENTINEL":
        _require(
            bool(dimension["ordered_activation_guard_clauses"]),
            f"{label} inactive-guard sentinel is not legal for an unguarded dimension",
        )
        return
    if cell_kind == "SAFE_INTEGER_INTERVAL":
        _require(
            dimension_kind == "SAFE_INTEGER_VALUE",
            f"{label} interval is not legal for its dimension",
        )
        return
    if cell_kind == "VERIFIER_DERIVED_CATALOG_POSITION":
        _require(
            dimension_kind
            in {
                "TEXT_RELATION_CLASS",
                "ARRAY_ORDER_CLASS",
                "ARRAY_UNIQUENESS_CLASS",
            },
            f"{label} catalog position is not legal for its dimension",
        )
        return
    atom_kind = cell["exact_atom"]["atom_kind"]
    expected_atom_kinds = {
        "NULLABILITY_BRANCH": {"POSITION"},
        "BOOLEAN_VALUE": {"BOOLEAN"},
        "SAFE_INTEGER_VALUE": {"SAFE_INTEGER"},
        "TEXT_RELATION_CLASS": set(),
        "TEXT_CANONICAL_LENGTH": {"SAFE_INTEGER"},
        "TEXT_VALUE": {"TEXT"},
        "ARRAY_CARDINALITY": {"SAFE_INTEGER"},
        "ARRAY_ORDER_CLASS": set(),
        "ARRAY_UNIQUENESS_CLASS": set(),
        "UNION_ALTERNATIVE_POSITION": {"POSITION"},
        "CATALOG_POSITION": {"POSITION"},
        "ROOT_FAMILY_POSITION": {"POSITION"},
        "MODE_ATTEMPT_POSITION": {"POSITION"},
        "OBSERVATION_ROLE_POSITION": {"POSITION"},
        "SEQUENCE_ORDINAL": {"POSITION"},
    }[dimension_kind]
    _require(
        atom_kind in expected_atom_kinds,
        f"{label} exact atom is not legal for its dimension",
    )
    if dimension_kind == "NULLABILITY_BRANCH":
        _require(
            cell["exact_atom"]["position_value"] in {0, 1},
            f"{label} nullability position differs",
        )


def _validate_bitmap_runs(
    value: Any,
    *,
    label: str,
    require_nonempty: bool,
) -> list[dict[str, Any]]:
    runs = _require_array(value, label=label, maximum_length=1_000_000)
    if require_nonempty:
        _require(bool(runs), f"{label} must not be empty")
    previous_last = -1
    previous_bitmap: str | None = None
    for run_position, run_value in enumerate(runs, 1):
        run = _require_exact_keys(
            run_value,
            BITMAP_RUN_KEYS,
            label=f"{label} item {run_position}",
        )
        first = _require_integer(
            run["first_block_index"],
            label=f"{label} first block {run_position}",
        )
        last = _require_integer(
            run["last_block_index"],
            label=f"{label} last block {run_position}",
        )
        bitmap = run["attainable_length_bitmap_hex"]
        _require(
            type(bitmap) is str
            and re.fullmatch(r"[0-9a-f]{64}", bitmap) is not None
            and int(bitmap, 16) != 0,
            f"{label} bitmap {run_position} differs",
        )
        _require(
            first <= last and first > previous_last,
            f"{label} run order differs",
        )
        _require(
            last <= (SAFE_INTEGER_MAXIMUM - 255) // 256,
            f"{label} bitmap block produces a non-I-JSON length",
        )
        _require(
            not (first == previous_last + 1 and bitmap == previous_bitmap),
            f"{label} adjacent equal bitmap runs are not merged",
        )
        previous_last = last
        previous_bitmap = bitmap
    return runs


def _validate_bitmap_runs_with_bounds(
    value: Any,
    *,
    inclusive_minimum: int,
    inclusive_maximum: int,
    label: str,
    require_nonempty: bool,
) -> list[dict[str, Any]]:
    """Validate bitmap support bounds algebraically without expanding blocks."""

    minimum = _require_integer(inclusive_minimum, label=f"{label} lower bound")
    maximum = _require_integer(inclusive_maximum, label=f"{label} upper bound")
    _require(minimum <= maximum, f"{label} bounds are reversed")
    runs = _validate_bitmap_runs(
        value,
        label=label,
        require_nonempty=require_nonempty,
    )
    if not runs:
        return runs
    minimum_block, minimum_bit = divmod(minimum, 256)
    maximum_block, maximum_bit = divmod(maximum, 256)
    for run_position, run in enumerate(runs, 1):
        first = run["first_block_index"]
        last = run["last_block_index"]
        bitmap = int(run["attainable_length_bitmap_hex"], 16)
        _require(
            first >= minimum_block and last <= maximum_block,
            f"{label} item {run_position} has support outside its block bounds",
        )
        if first == minimum_block and minimum_bit:
            _require(
                bitmap & ((1 << minimum_bit) - 1) == 0,
                f"{label} item {run_position} has support below its lower bound",
            )
        if last == maximum_block and maximum_bit < 255:
            _require(
                bitmap >> (maximum_bit + 1) == 0,
                f"{label} item {run_position} has support above its upper bound",
            )
    return runs


def _decode_ordered_string_slot_json(raw: bytes, *, label: str) -> Any:
    _require(type(raw) is bytes and bool(raw), f"{label} raw bytes must not be empty")
    return _decode_compact_json_value(raw, label=label)


def _decode_ordered_string_count_frontier(
    raw: bytes,
    *,
    item_count_limit: int,
    maximum_total_octets: int,
    label: str,
) -> list[dict[str, Any]]:
    """Decode the closed count-frontier slot without expanding bitmap runs."""

    maximum_item_count = _require_integer(
        item_count_limit,
        label=f"{label} item-count limit",
        maximum=512,
    )
    maximum_octets = _require_integer(
        maximum_total_octets,
        label=f"{label} total-octet limit",
    )
    decoded = _decode_ordered_string_slot_json(raw, label=label)
    records = _require_array(
        decoded,
        label=label,
        exact_length=maximum_item_count + 1,
    )
    for item_count, record_value in enumerate(records):
        record = _require_exact_keys(
            record_value,
            ORDERED_STRING_COUNT_FRONTIER_RECORD_KEYS,
            label=f"{label} item-count record {item_count}",
        )
        _require(
            record["item_count"] == item_count,
            f"{label} item counts are not contiguous from zero",
        )
        runs = _validate_bitmap_runs_with_bounds(
            record["ordered_total_octet_bitmap_runs"],
            inclusive_minimum=0,
            inclusive_maximum=maximum_octets,
            label=f"{label} item-count {item_count} total-octet runs",
            require_nonempty=False,
        )
        if item_count == 0:
            _require(
                runs
                == [
                    {
                        "first_block_index": 0,
                        "last_block_index": 0,
                        "attainable_length_bitmap_hex": f"{1:064x}",
                    }
                ],
                f"{label} item-count zero support is not exactly zero",
            )
    return records


def _decode_ordered_string_least_completion_prefix_positions(
    raw: bytes,
    *,
    expected_remaining_items: int,
    scalar_prefixes: list[dict[str, Any]],
    label: str,
    resource_meter: ProofResourceMeter,
    preceding_prefix_positions: tuple[int, ...] = (),
) -> list[int]:
    """Decode and locally validate one completing scalar-prefix-position array."""

    remaining_items = _require_integer(
        expected_remaining_items,
        label=f"{label} remaining-item count",
        maximum=512,
    )
    decoded = _decode_ordered_string_slot_json(raw, label=label)
    positions = _require_array(decoded, label=label, exact_length=remaining_items)
    checked_positions = [
        _require_integer(
            position,
            label=f"{label} prefix position {item_position}",
            maximum=len(scalar_prefixes) - 1,
        )
        for item_position, position in enumerate(positions)
    ]
    complete_positions = [*preceding_prefix_positions, *checked_positions]
    for item_position, position in enumerate(complete_positions):
        _require_integer(
            position,
            label=f"{label} complete prefix position {item_position}",
            maximum=len(scalar_prefixes) - 1,
        )
    for item_position, (left, right) in enumerate(
        zip(complete_positions, complete_positions[1:], strict=False),
        1,
    ):
        _require(
            _compare_scalar_prefix_strings(
                scalar_prefixes,
                left,
                right,
                label=f"{label} lexical pair {item_position}",
                resource_meter=resource_meter,
            )
            < 0,
            f"{label} reconstructed strings are not strictly scalar-lex increasing",
        )
    return checked_positions


def _decode_ordered_string_feasible_cardinality_bitmap_runs(
    raw: bytes,
    *,
    minimum_array_cardinality: int,
    maximum_array_cardinality: int,
    label: str,
) -> list[dict[str, Any]]:
    """Decode cardinality support and reject every out-of-interval set bit."""

    minimum = _require_integer(
        minimum_array_cardinality,
        label=f"{label} minimum cardinality",
        maximum=512,
    )
    maximum = _require_integer(
        maximum_array_cardinality,
        label=f"{label} maximum cardinality",
        maximum=512,
    )
    _require(minimum <= maximum, f"{label} cardinality bounds are reversed")
    decoded = _decode_ordered_string_slot_json(raw, label=label)
    return _validate_bitmap_runs_with_bounds(
        decoded,
        inclusive_minimum=minimum,
        inclusive_maximum=maximum,
        label=label,
        require_nonempty=False,
    )


def _validate_atom_array(value: Any, *, label: str) -> list[dict[str, Any]]:
    atoms = _require_array(value, label=label, maximum_length=1_000_000)
    for position, atom in enumerate(atoms, 1):
        atom_order = _validate_primitive_atom(atom, label=f"{label} item {position}")
        _require(
            atom_order[0] != 0,
            f"{label} item {position} is prefix-only INACTIVE",
        )
    return atoms


def _validate_cell_array(
    value: Any,
    *,
    allowed_prior_catalog_ids: frozenset[str],
    label: str,
    resource_meter: ProofResourceMeter | None = None,
    referenced_prior_catalog_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    cells = _require_array(value, label=label, maximum_length=1_000_000)
    for position, cell_value in enumerate(cells, 1):
        cell = _validate_state_cell(
            cell_value,
            label=f"{label} item {position}",
            resource_meter=resource_meter,
        )
        if cell["cell_kind"] == "VERIFIER_DERIVED_CATALOG_POSITION":
            _require(
                cell["catalog_id"] in allowed_prior_catalog_ids,
                f"{label} item {position} references a non-prior catalog",
            )
            if referenced_prior_catalog_ids is not None:
                referenced_prior_catalog_ids.append(cell["catalog_id"])
    return cells


def _validate_derived_state_catalog(
    value: Any,
    *,
    maximum_protocol_sha256: str,
    expected_catalog_id: str,
    allowed_prior_catalog_ids: frozenset[str],
    label: str,
    resource_meter: ProofResourceMeter | None = None,
) -> CatalogStaticEvidence:
    _require_sha256(maximum_protocol_sha256, label=f"{label} protocol SHA")
    _require_sha256(expected_catalog_id, label=f"{label} expected catalog ID")
    catalog = _require_exact_keys(value, DERIVED_STATE_CATALOG_KEYS, label=label)
    meter = (
        resource_meter
        if resource_meter is not None
        else ProofResourceMeter(phase=SEED_CAP_DERIVATION_PHASE)
    )
    hash_octets_before = meter.value("hash_preimage_octets")
    _require(
        catalog["catalog_version"]
        == "riskyieldmm.raw_v8_step2_external_schema_v2.maximum_state_catalog.v1",
        f"{label} version differs",
    )
    _require(
        catalog["catalog_kind"]
        in {
            "TEXT_RELATION_SLICE",
            "ARRAY_ORDER_PREFIX",
            "ARRAY_UNIQUENESS_SET",
        },
        f"{label} kind differs",
    )
    entries = _require_array(
        catalog["ordered_catalog_entries"],
        label=f"{label} entries",
        maximum_length=1_000_000,
    )
    complete_root_octets = _canonical_octet_length(catalog)
    meter.reserve(
        {
            "state_catalog_entry_count": len(entries),
            "state_catalog_canonicalized_octets": complete_root_octets,
        }
    )
    referenced_prior_catalog_ids: list[str] = []
    _validate_proof_subject_locator(
        catalog["defining_subject_locator"],
        label=f"{label} defining subject locator",
        resource_meter=meter,
        referenced_prior_catalog_ids=referenced_prior_catalog_ids,
    )
    _require_optional_sha256(
        catalog["defining_value_schema_id"],
        label=f"{label} defining value-schema ID",
    )
    _require_sha256_array(
        catalog["ordered_observable_descriptor_ids"],
        label=f"{label} observable descriptor IDs",
    )
    previous_key: bytes | None = None
    for position, entry_value in enumerate(entries):
        entry = _require_exact_keys(
            entry_value,
            DERIVED_STATE_CATALOG_ENTRY_KEYS,
            label=f"{label} entry {position}",
        )
        _require(
            entry["catalog_position"] == position,
            f"{label} entry positions differ",
        )
        atoms = _validate_atom_array(
            entry["ordered_partition_atoms"],
            label=f"{label} partition atoms {position}",
        )
        cells = _validate_cell_array(
            entry["ordered_partition_state_cells"],
            allowed_prior_catalog_ids=allowed_prior_catalog_ids,
            label=f"{label} partition cells {position}",
            resource_meter=meter,
            referenced_prior_catalog_ids=referenced_prior_catalog_ids,
        )
        representative = entry["canonical_representative_atom"]
        if representative is not None:
            representative_order = _validate_primitive_atom(
                representative,
                label=f"{label} representative atom {position}",
            )
            _require(
                representative_order[0] != 0,
                f"{label} representative atom {position} is prefix-only INACTIVE",
            )
        _validate_bitmap_runs(
            entry["ordered_attainable_length_bitmap_runs"],
            label=f"{label} attainable runs {position}",
            require_nonempty=True,
        )
        entry_key = _canonical_bytes([atoms, cells])
        _require(
            previous_key is None or previous_key < entry_key,
            f"{label} entry key order differs",
        )
        previous_key = entry_key
    payload = {"maximum_protocol_sha256": maximum_protocol_sha256, **catalog}
    _require(
        _semantic_id(
            DERIVED_STATE_CATALOG_DOMAIN,
            payload,
            resource_meter=meter,
        )
        == expected_catalog_id,
        f"{label} semantic identity differs",
    )
    return CatalogStaticEvidence(
        catalog=catalog,
        catalog_id=expected_catalog_id,
        entry_count=len(entries),
        complete_root_octets=complete_root_octets,
        validation_hash_preimage_octets=(
            meter.value("hash_preimage_octets") - hash_octets_before
        ),
        referenced_prior_catalog_ids=tuple(dict.fromkeys(referenced_prior_catalog_ids)),
    )


def _require_unicode_scalar(value: Any, *, label: str) -> int:
    scalar = _require_integer(value, label=label, maximum=0x10FFFF)
    _require(
        not 0xD800 <= scalar <= 0xDFFF,
        f"{label} must not be a Unicode surrogate",
    )
    return scalar


def _canonical_json_scalar_value_octet_cost(scalar: int) -> int:
    """Return the canonical JSON cost of one scalar, excluding string quotes."""

    _require_unicode_scalar(scalar, label="canonical JSON scalar")
    if scalar in {0x22, 0x5C, 0x08, 0x09, 0x0A, 0x0C, 0x0D}:
        return 2
    if scalar < 0x20:
        return 6
    if scalar <= 0x7F:
        return 1
    if scalar <= 0x7FF:
        return 2
    if scalar <= 0xFFFF:
        return 3
    return 4


def _prefix_chain_positions(
    records: list[dict[str, Any]],
    position: int,
    *,
    label: str,
    resource_meter: ProofResourceMeter,
) -> list[int]:
    """Resolve one parent-linked prefix without expanding repeated values."""

    reverse_positions: list[int] = []
    current = position
    while current != 0:
        resource_meter.add("frontier_transition_count")
        reverse_positions.append(current)
        parent = records[current]["parent_prefix_position"]
        _require(
            type(parent) is int and 0 <= parent < current,
            f"{label} parent chain differs",
        )
        current = parent
    reverse_positions.reverse()
    return reverse_positions


def _compare_scalar_prefix_sequences(
    records: list[dict[str, Any]],
    left_position: int,
    right_position: int,
    *,
    label: str,
    resource_meter: ProofResourceMeter,
) -> int:
    """Compare two equal-length scalar sequences directly over their RLE runs."""

    left_chain = _prefix_chain_positions(
        records,
        left_position,
        label=f"{label} left",
        resource_meter=resource_meter,
    )
    right_chain = _prefix_chain_positions(
        records,
        right_position,
        label=f"{label} right",
        resource_meter=resource_meter,
    )
    left_index = right_index = 0
    left_remaining = right_remaining = 0
    left_scalar = right_scalar = 0
    while left_index < len(left_chain) or left_remaining:
        if left_remaining == 0:
            left_record = records[left_chain[left_index]]
            left_index += 1
            left_scalar = left_record["appended_scalar_value"]
            left_remaining = left_record["appended_scalar_repeat_count"]
        if right_remaining == 0:
            _require(
                right_index < len(right_chain),
                f"{label} reconstructed lengths differ",
            )
            right_record = records[right_chain[right_index]]
            right_index += 1
            right_scalar = right_record["appended_scalar_value"]
            right_remaining = right_record["appended_scalar_repeat_count"]
        resource_meter.add("frontier_transition_count")
        if left_scalar != right_scalar:
            return -1 if left_scalar < right_scalar else 1
        consumed = min(left_remaining, right_remaining)
        left_remaining -= consumed
        right_remaining -= consumed
    _require(
        right_index == len(right_chain) and right_remaining == 0,
        f"{label} reconstructed lengths differ",
    )
    return 0


def _compare_scalar_prefix_strings(
    records: list[dict[str, Any]],
    left_position: int,
    right_position: int,
    *,
    label: str,
    resource_meter: ProofResourceMeter,
) -> int:
    """Compare arbitrary-length scalar strings over parent-linked RLE runs."""

    left_chain = _prefix_chain_positions(
        records,
        left_position,
        label=f"{label} left",
        resource_meter=resource_meter,
    )
    right_chain = _prefix_chain_positions(
        records,
        right_position,
        label=f"{label} right",
        resource_meter=resource_meter,
    )
    left_index = right_index = 0
    left_remaining = right_remaining = 0
    left_scalar = right_scalar = 0
    while True:
        if left_remaining == 0 and left_index < len(left_chain):
            left_record = records[left_chain[left_index]]
            left_index += 1
            left_scalar = left_record["appended_scalar_value"]
            left_remaining = left_record["appended_scalar_repeat_count"]
        if right_remaining == 0 and right_index < len(right_chain):
            right_record = records[right_chain[right_index]]
            right_index += 1
            right_scalar = right_record["appended_scalar_value"]
            right_remaining = right_record["appended_scalar_repeat_count"]
        left_done = left_remaining == 0 and left_index == len(left_chain)
        right_done = right_remaining == 0 and right_index == len(right_chain)
        if left_done or right_done:
            if left_done and right_done:
                return 0
            return -1 if left_done else 1
        resource_meter.add("frontier_transition_count")
        if left_scalar != right_scalar:
            return -1 if left_scalar < right_scalar else 1
        consumed = min(left_remaining, right_remaining)
        left_remaining -= consumed
        right_remaining -= consumed


def _validate_scalar_prefix_pool(
    value: Any,
    *,
    label: str,
    ascii_only: bool = False,
    resource_meter: ProofResourceMeter | None = None,
) -> list[dict[str, Any]]:
    records = _require_array(value, label=label, maximum_length=1_000_000)
    meter = (
        resource_meter
        if resource_meter is not None
        else ProofResourceMeter(phase=SEED_CAP_DERIVATION_PHASE)
    )
    previous_scalar_count = -1
    for position, record_value in enumerate(records):
        record = _require_exact_keys(
            record_value,
            TRANSIENT_SCALAR_PREFIX_RECORD_KEYS,
            label=f"{label} record {position}",
        )
        _require(
            record["prefix_position"] == position,
            f"{label} positions differ",
        )
        parent = record["parent_prefix_position"]
        scalar = record["appended_scalar_value"]
        repeat_count = _require_integer(
            record["appended_scalar_repeat_count"],
            label=f"{label} repeat count {position}",
        )
        scalar_count = _require_integer(
            record["scalar_count"],
            label=f"{label} scalar count {position}",
        )
        json_octets = _require_integer(
            record["json_value_octets"],
            label=f"{label} JSON octets {position}",
        )
        if position == 0:
            _require(
                parent is None
                and scalar is None
                and repeat_count == scalar_count == json_octets == 0,
                f"{label} empty-prefix record differs",
            )
            continue
        parent_position = _require_integer(
            parent,
            label=f"{label} parent {position}",
            maximum=position - 1,
        )
        scalar = _require_unicode_scalar(scalar, label=f"{label} scalar {position}")
        _require(
            not ascii_only or scalar <= 0x7F,
            f"{label} scalar {position} is outside the ASCII recurrence",
        )
        _require(repeat_count > 0, f"{label} repeat count {position} is not positive")
        parent_record = records[parent_position]
        if parent_position != 0:
            _require(
                parent_record["appended_scalar_value"] != scalar,
                f"{label} record {position} chains an adjacent equal scalar run",
            )
        _require(
            repeat_count <= SAFE_INTEGER_MAXIMUM - parent_record["scalar_count"]
            and scalar_count == parent_record["scalar_count"] + repeat_count,
            f"{label} scalar count {position} differs from its parent",
        )
        scalar_cost = _canonical_json_scalar_value_octet_cost(scalar)
        _require(
            repeat_count
            <= (SAFE_INTEGER_MAXIMUM - parent_record["json_value_octets"])
            // scalar_cost
            and json_octets
            == parent_record["json_value_octets"] + repeat_count * scalar_cost,
            f"{label} JSON octets {position} differ from its parent",
        )
        _require(
            scalar_count >= previous_scalar_count,
            f"{label} scalar-count order differs",
        )
        if scalar_count == previous_scalar_count:
            _require(
                _compare_scalar_prefix_sequences(
                    records,
                    position - 1,
                    position,
                    label=f"{label} records {position - 1}:{position}",
                    resource_meter=meter,
                )
                < 0,
                f"{label} reconstructed scalar-prefix order differs",
            )
        previous_scalar_count = scalar_count
    return records


def _validate_primitive_prefix_pool(
    value: Any,
    *,
    label: str,
    resource_meter: ProofResourceMeter | None = None,
) -> list[dict[str, Any]]:
    records = _require_array(value, label=label, maximum_length=1_000_000)
    meter = (
        resource_meter
        if resource_meter is not None
        else ProofResourceMeter(phase=SEED_CAP_DERIVATION_PHASE)
    )
    atom_orders: list[tuple[int, Any] | None] = []
    previous_active_count = -1
    for position, record_value in enumerate(records):
        record = _require_exact_keys(
            record_value,
            TRANSIENT_PRIMITIVE_PREFIX_RECORD_KEYS,
            label=f"{label} record {position}",
        )
        _require(
            record["prefix_position"] == position,
            f"{label} positions differ",
        )
        parent = record["parent_prefix_position"]
        plan_id = record["appended_choice_coordinate_plan_id"]
        atom = record["appended_atom"]
        active_count = _require_integer(
            record["active_atom_count"],
            label=f"{label} active-atom count {position}",
        )
        if position == 0:
            _require(
                parent is None
                and plan_id is None
                and atom is None
                and active_count == 0,
                f"{label} empty-prefix record differs",
            )
            atom_orders.append(None)
            previous_active_count = 0
            continue
        parent_position = _require_integer(
            parent,
            label=f"{label} parent {position}",
            maximum=position - 1,
        )
        _require_sha256(plan_id, label=f"{label} plan ID {position}")
        atom_order = _validate_primitive_atom(
            atom,
            label=f"{label} appended atom {position}",
        )
        _require(
            atom_order[0] != 0,
            f"{label} appended atom {position} is prefix-only INACTIVE",
        )
        _require(
            active_count == records[parent_position]["active_atom_count"] + 1,
            f"{label} active-atom count {position} differs from its parent",
        )
        atom_orders.append(atom_order)
        _require(
            active_count >= previous_active_count,
            f"{label} active-atom-count order differs",
        )
        if active_count == previous_active_count:
            left_positions = _prefix_chain_positions(
                records,
                position - 1,
                label=f"{label} left primitive prefix",
                resource_meter=meter,
            )
            right_positions = _prefix_chain_positions(
                records,
                position,
                label=f"{label} right primitive prefix",
                resource_meter=meter,
            )
            left_vector = tuple(atom_orders[item] for item in left_positions)
            right_vector = tuple(atom_orders[item] for item in right_positions)
            _require(
                left_vector < right_vector,
                f"{label} reconstructed primitive-prefix order differs",
            )
        previous_active_count = active_count
    return records


def _validate_raw_lex_interval_pool(
    value: Any,
    *,
    scalar_prefix_count: int,
    label: str,
) -> list[dict[str, Any]]:
    intervals = _require_array(value, label=label, maximum_length=1_000_000)
    previous_blocks: bytes | None = None
    empty_interval_count = 0
    for interval_position, interval_value in enumerate(intervals):
        interval = _require_exact_keys(
            interval_value,
            TRANSIENT_RAW_LEX_INTERVAL_RECORD_KEYS,
            label=f"{label} interval {interval_position}",
        )
        _require(
            interval["interval_position"] == interval_position,
            f"{label} interval positions differ",
        )
        blocks = _require_array(
            interval["ordered_interval_blocks"],
            label=f"{label} blocks {interval_position}",
            maximum_length=1_000_000,
        )
        empty_interval_count += int(not blocks)
        for block_position, block_value in enumerate(blocks, 1):
            block = _require_exact_keys(
                block_value,
                TRANSIENT_RAW_LEX_INTERVAL_BLOCK_KEYS,
                label=f"{label} block {interval_position}:{block_position}",
            )
            _require(
                block["block_position"] == block_position,
                f"{label} block positions differ",
            )
            _require_integer(
                block["prefix_position"],
                label=f"{label} block prefix {interval_position}:{block_position}",
                maximum=scalar_prefix_count - 1,
            )
            kind = block["block_kind"]
            _require(
                kind
                in {
                    "PREFIX_SINGLETON",
                    "PREFIX_SUBTREE",
                    "STRICT_EXTENSION_SUBTREE",
                    "NEXT_SCALAR_RANGE_SUBTREES",
                    "HOMOGENEOUS_ANCESTOR_DIVERGENCE_RUN",
                },
                f"{label} block kind differs",
            )
            next_minimum = block["inclusive_next_scalar_minimum"]
            next_maximum = block["inclusive_next_scalar_maximum"]
            repeated_scalar = block["repeated_lower_bound_scalar"]
            minimum_repeat = block["minimum_retained_repeat_count"]
            maximum_repeat = block["maximum_retained_repeat_count"]
            if kind in {
                "PREFIX_SINGLETON",
                "PREFIX_SUBTREE",
                "STRICT_EXTENSION_SUBTREE",
            }:
                _require(
                    next_minimum is None
                    and next_maximum is None
                    and repeated_scalar is None
                    and minimum_repeat is None
                    and maximum_repeat is None,
                    f"{label} simple block nullable members differ",
                )
            elif kind == "NEXT_SCALAR_RANGE_SUBTREES":
                minimum_scalar = _require_unicode_scalar(
                    next_minimum,
                    label=f"{label} next-scalar minimum",
                )
                maximum_scalar = _require_unicode_scalar(
                    next_maximum,
                    label=f"{label} next-scalar maximum",
                )
                _require(
                    minimum_scalar <= maximum_scalar
                    and not (minimum_scalar < 0xD800 and maximum_scalar > 0xDFFF)
                    and _canonical_json_scalar_value_octet_cost(minimum_scalar)
                    == _canonical_json_scalar_value_octet_cost(maximum_scalar)
                    and repeated_scalar is None
                    and minimum_repeat is None
                    and maximum_repeat is None,
                    f"{label} next-scalar block range/cost/nullability differs",
                )
            else:
                _require(
                    next_minimum is None and next_maximum is None,
                    f"{label} homogeneous block next-scalar members differ",
                )
                repeated_scalar = _require_unicode_scalar(
                    repeated_scalar,
                    label=f"{label} repeated lower-bound scalar",
                )
                _require(
                    repeated_scalar < 0x10FFFF,
                    f"{label} homogeneous block has no greater scalar",
                )
                minimum_count = _require_integer(
                    minimum_repeat,
                    label=f"{label} minimum retained-repeat count",
                    minimum=0,
                )
                maximum_count = _require_integer(
                    maximum_repeat,
                    label=f"{label} maximum retained-repeat count",
                    minimum=0,
                )
                _require(
                    minimum_count == 0 and minimum_count <= maximum_count,
                    f"{label} retained-repeat range is not canonical from zero",
                )
        block_key = _canonical_bytes(blocks)
        _require(
            previous_blocks is None or previous_blocks < block_key,
            f"{label} interval block-array order differs",
        )
        previous_blocks = block_key
    _require(empty_interval_count <= 1, f"{label} repeats the empty interval")
    return intervals


def _ordered_string_atom_value(
    atom: dict[str, Any],
    *,
    allowed_kinds: frozenset[str],
    label: str,
) -> Any:
    atom_kind = atom["atom_kind"]
    _require(atom_kind in allowed_kinds, f"{label} atom kind differs")
    return _validate_primitive_atom(atom, label=label)[1]


def _validate_ordered_string_recurrence_parameters(
    parameters: dict[str, Any],
    *,
    scalar_prefixes: list[dict[str, Any]],
    label: str,
    resource_meter: ProofResourceMeter,
) -> OrderedRawStringRecurrenceBounds:
    invocation_kind = parameters["invocation_kind"]
    _require(
        invocation_kind
        in {"MAXIMUM_SLICE_FEASIBILITY", "PREFIX_FEASIBILITY_OR_UNRANK"},
        f"{label} invocation kind differs",
    )
    _require_integer(
        parameters["safe_array_node_position"],
        label=f"{label} safe-array node position",
        minimum=1,
    )
    target_array_octets = _require_integer(
        parameters["target_array_octets"],
        label=f"{label} target array octets",
    )
    cardinality_query_kind = parameters["cardinality_query_kind"]
    _require(
        cardinality_query_kind in {"ALL_LEGAL_CARDINALITIES", "FIXED_CARDINALITY"},
        f"{label} cardinality query kind differs",
    )
    minimum_cardinality = _require_integer(
        parameters["minimum_array_cardinality"],
        label=f"{label} minimum array cardinality",
        maximum=512,
    )
    maximum_cardinality = _require_integer(
        parameters["maximum_array_cardinality"],
        label=f"{label} maximum array cardinality",
        maximum=512,
    )
    _require(
        minimum_cardinality <= maximum_cardinality,
        f"{label} cardinality bounds are reversed",
    )
    fixed_item_count = _require_integer(
        parameters["fixed_item_count"],
        label=f"{label} fixed-item count",
        maximum=512,
    )
    fixed_positions_value = _require_array(
        parameters["ordered_fixed_item_scalar_prefix_positions"],
        label=f"{label} fixed-item prefix positions",
        exact_length=fixed_item_count,
    )
    fixed_positions = tuple(
        _require_integer(
            position,
            label=f"{label} fixed-item prefix position {item_position}",
            maximum=len(scalar_prefixes) - 1,
        )
        for item_position, position in enumerate(fixed_positions_value)
    )
    for item_position, (left, right) in enumerate(
        zip(fixed_positions, fixed_positions[1:], strict=False),
        1,
    ):
        _require(
            _compare_scalar_prefix_strings(
                scalar_prefixes,
                left,
                right,
                label=f"{label} fixed lexical pair {item_position}",
                resource_meter=resource_meter,
            )
            < 0,
            f"{label} fixed strings are not strictly scalar-lex increasing",
        )
    per_string_ceiling = _require_integer(
        parameters["per_string_canonical_octet_ceiling"],
        label=f"{label} per-string canonical-octet ceiling",
    )
    fixed_string_octets = 0
    for item_position, position in enumerate(fixed_positions):
        string_octets = scalar_prefixes[position]["json_value_octets"] + 2
        _require(
            string_octets <= per_string_ceiling,
            f"{label} fixed string {item_position} exceeds its canonical ceiling",
        )
        _require(
            fixed_string_octets <= SAFE_INTEGER_MAXIMUM - string_octets,
            f"{label} fixed-string octets exceed safe arithmetic",
        )
        fixed_string_octets += string_octets

    array_cardinality_value = parameters["array_cardinality"]
    if cardinality_query_kind == "ALL_LEGAL_CARDINALITIES":
        _require(
            array_cardinality_value is None
            and fixed_item_count == 0
            and not fixed_positions,
            f"{label} all-cardinality nullability/prefix differs",
        )
        array_cardinality = None
        item_count_limit = maximum_cardinality
        _require(
            item_count_limit == 0
            or per_string_ceiling <= SAFE_INTEGER_MAXIMUM // item_count_limit,
            f"{label} all-cardinality octet product exceeds safe arithmetic",
        )
        maximum_total_octets = min(
            item_count_limit * per_string_ceiling,
            max(0, target_array_octets - 2),
        )
    else:
        array_cardinality = _require_integer(
            array_cardinality_value,
            label=f"{label} fixed array cardinality",
            minimum=minimum_cardinality,
            maximum=maximum_cardinality,
        )
        _require(
            fixed_item_count <= array_cardinality,
            f"{label} fixed-item count exceeds array cardinality",
        )
        item_count_limit = array_cardinality - fixed_item_count
        punctuation_octets = 2 if array_cardinality == 0 else array_cardinality + 1
        residual = target_array_octets - punctuation_octets - fixed_string_octets
        maximum_total_octets = max(0, residual)
    return OrderedRawStringRecurrenceBounds(
        item_count_limit=item_count_limit,
        maximum_total_octets=maximum_total_octets,
        fixed_prefix_positions=fixed_positions,
        array_cardinality=array_cardinality,
        target_array_octets=target_array_octets,
        per_string_canonical_octet_ceiling=per_string_ceiling,
    )


def _validate_ordered_string_completion_target(
    positions: list[int],
    *,
    bounds: OrderedRawStringRecurrenceBounds,
    scalar_prefixes: list[dict[str, Any]],
    label: str,
) -> None:
    complete_positions = [*bounds.fixed_prefix_positions, *positions]
    if (
        bounds.array_cardinality is None
        or len(complete_positions) != bounds.array_cardinality
    ):
        return
    string_octets = 0
    for item_position, position in enumerate(complete_positions):
        item_octets = scalar_prefixes[position]["json_value_octets"] + 2
        _require(
            item_octets <= bounds.per_string_canonical_octet_ceiling,
            f"{label} string {item_position} exceeds its canonical ceiling",
        )
        _require(
            string_octets <= SAFE_INTEGER_MAXIMUM - item_octets,
            f"{label} string octets exceed safe arithmetic",
        )
        string_octets += item_octets
    punctuation_octets = (
        2 if bounds.array_cardinality == 0 else bounds.array_cardinality + 1
    )
    _require(
        punctuation_octets + string_octets == bounds.target_array_octets,
        f"{label} completion does not attain the target array octets",
    )


def _ordered_string_canonical_bytes_atom(atom: dict[str, Any], *, label: str) -> bytes:
    raw = _ordered_string_atom_value(
        atom,
        allowed_kinds=frozenset({"CANONICAL_BYTES"}),
        label=label,
    )
    _require(type(raw) is bytes, f"{label} canonical bytes differ")
    return raw


def _ordered_string_singleton_bitmap(length: int) -> list[dict[str, Any]]:
    block, bit = divmod(length, 256)
    return [
        {
            "first_block_index": block,
            "last_block_index": block,
            "attainable_length_bitmap_hex": f"{1 << bit:064x}",
        }
    ]


def _validate_ordered_raw_string_state_slots(
    *,
    key_atoms: list[dict[str, Any]],
    key_cells: list[dict[str, Any]],
    payload_atoms: list[dict[str, Any]],
    payload_cells: list[dict[str, Any]],
    attainable_runs: list[dict[str, Any]],
    parameters: dict[str, Any],
    bounds: OrderedRawStringRecurrenceBounds,
    scalar_prefixes: list[dict[str, Any]],
    lex_intervals: list[dict[str, Any]],
    label: str,
    resource_meter: ProofResourceMeter,
) -> None:
    _require(bool(key_atoms), f"{label} state kind is absent")
    state_kind = _ordered_string_atom_value(
        key_atoms[0],
        allowed_kinds=frozenset({"TEXT"}),
        label=f"{label} state kind",
    )
    _require(
        state_kind in ORDERED_STRING_RECURRENCE_STATE_KINDS,
        f"{label} state kind differs",
    )
    _require(not key_cells and not payload_cells, f"{label} state cells must be empty")

    def key_value(position: int, *kinds: str) -> Any:
        return _ordered_string_atom_value(
            key_atoms[position],
            allowed_kinds=frozenset(kinds),
            label=f"{label} key atom {position}",
        )

    def payload_value(position: int, *kinds: str) -> Any:
        return _ordered_string_atom_value(
            payload_atoms[position],
            allowed_kinds=frozenset(kinds),
            label=f"{label} payload atom {position}",
        )

    if state_kind == "SUFFIX_COUNT_RUN":
        _require(
            len(key_atoms) == 3 and len(payload_atoms) == 1, f"{label} layout differs"
        )
        first = _require_integer(
            key_value(1, "SAFE_INTEGER"), label=f"{label} first value octets"
        )
        last = _require_integer(
            key_value(2, "SAFE_INTEGER"), label=f"{label} last value octets"
        )
        count = _require_integer(
            payload_value(0, "SAFE_INTEGER"),
            label=f"{label} saturated count",
            minimum=1,
        )
        _require(
            bounds.item_count_limit > 0
            and bounds.per_string_canonical_octet_ceiling >= 2
            and first <= last <= max(0, bounds.per_string_canonical_octet_ceiling - 2)
            and count <= bounds.item_count_limit + 1,
            f"{label} suffix-run bounds differ",
        )
        _require(not attainable_runs, f"{label} generic attainable runs must be empty")
        return

    if state_kind == "INTERVAL_MULTIPLICITY_RUN":
        _require(
            len(key_atoms) == 4 and len(payload_atoms) == 1, f"{label} layout differs"
        )
        _require_integer(
            key_value(1, "POSITION"),
            label=f"{label} interval position",
            maximum=len(lex_intervals) - 1,
        )
        first = _require_integer(
            key_value(2, "SAFE_INTEGER"),
            label=f"{label} first string octets",
            minimum=2,
        )
        last = _require_integer(
            key_value(3, "SAFE_INTEGER"), label=f"{label} last string octets", minimum=2
        )
        multiplicity = _require_integer(
            payload_value(0, "SAFE_INTEGER"),
            label=f"{label} capped multiplicity",
            minimum=1,
        )
        _require(
            bounds.item_count_limit > 0
            and first <= last <= bounds.per_string_canonical_octet_ceiling
            and multiplicity <= bounds.item_count_limit,
            f"{label} multiplicity-run bounds differ",
        )
        _require(not attainable_runs, f"{label} generic attainable runs must be empty")
        return

    if state_kind in {"FACTOR_RUN", "FACTOR_FOLD_RUN"}:
        _require(
            len(key_atoms) == 3 and len(payload_atoms) == 1, f"{label} layout differs"
        )
        _require(bounds.item_count_limit > 0, f"{label} is illegal for terminal K=0")
        _require_integer(
            key_value(1, "POSITION"),
            label=f"{label} interval position",
            maximum=len(lex_intervals) - 1,
        )
        _require_integer(
            key_value(2, "POSITION"), label=f"{label} run ordinal", minimum=1
        )
        raw = _ordered_string_canonical_bytes_atom(
            payload_atoms[0], label=f"{label} count frontier"
        )
        _decode_ordered_string_count_frontier(
            raw,
            item_count_limit=bounds.item_count_limit,
            maximum_total_octets=bounds.maximum_total_octets,
            label=f"{label} count frontier",
        )
        _require(not attainable_runs, f"{label} generic attainable runs must be empty")
        return

    if state_kind == "K1_DIRECT_FEASIBILITY":
        _require(
            len(key_atoms) == 3 and len(payload_atoms) == 2, f"{label} layout differs"
        )
        required_octets = key_value(1, "SAFE_INTEGER", "NULL")
        if required_octets is not None:
            required_octets = _require_integer(
                required_octets,
                label=f"{label} required value octets",
                maximum=max(0, bounds.per_string_canonical_octet_ceiling - 2),
            )
        lower_bound = key_value(2, "POSITION", "NULL")
        if lower_bound is not None:
            _require_integer(
                lower_bound,
                label=f"{label} lower-bound prefix",
                maximum=len(scalar_prefixes) - 1,
            )
        decision = payload_value(0, "BOOLEAN")
        least_position = payload_value(1, "POSITION", "NULL")
        _require(type(decision) is bool, f"{label} decision differs")
        _require(
            decision == (least_position is not None)
            and (required_octets is not None or not decision),
            f"{label} decision/result nullability differs",
        )
        if least_position is not None:
            least_position = _require_integer(
                least_position,
                label=f"{label} least prefix",
                maximum=len(scalar_prefixes) - 1,
            )
            _require(
                scalar_prefixes[least_position]["json_value_octets"] == required_octets,
                f"{label} least prefix has the wrong value-octet cost",
            )
            if lower_bound is not None:
                _require(
                    _compare_scalar_prefix_strings(
                        scalar_prefixes,
                        lower_bound,
                        least_position,
                        label=f"{label} strict lower bound",
                        resource_meter=resource_meter,
                    )
                    < 0,
                    f"{label} least prefix is not above its lower bound",
                )
        _require(not attainable_runs, f"{label} generic attainable runs must be empty")
        return

    if state_kind == "BULK_UNRANK_TEST":
        _require(
            len(key_atoms) == 5 and len(payload_atoms) == 2, f"{label} layout differs"
        )
        remaining_items = _require_integer(
            key_value(1, "SAFE_INTEGER"),
            label=f"{label} remaining items",
            minimum=2,
            maximum=bounds.item_count_limit,
        )
        remaining_octets = key_value(2, "SAFE_INTEGER", "NULL")
        if remaining_octets is not None:
            remaining_octets = _require_integer(
                remaining_octets,
                label=f"{label} remaining total octets",
                maximum=bounds.maximum_total_octets,
            )
        candidate_interval = key_value(3, "POSITION", "NULL")
        greater_interval = key_value(4, "POSITION", "NULL")
        for interval_label, interval_position in (
            ("candidate", candidate_interval),
            ("strictly-greater", greater_interval),
        ):
            if interval_position is not None:
                _require_integer(
                    interval_position,
                    label=f"{label} {interval_label} interval",
                    maximum=len(lex_intervals) - 1,
                )
        decision = payload_value(0, "BOOLEAN")
        completion_raw = payload_value(1, "CANONICAL_BYTES", "NULL")
        _require(type(decision) is bool, f"{label} decision differs")
        _require(
            decision == (completion_raw is not None)
            and (remaining_octets is not None or not decision),
            f"{label} decision/completion nullability differs",
        )
        if completion_raw is not None:
            positions = _decode_ordered_string_least_completion_prefix_positions(
                completion_raw,
                expected_remaining_items=remaining_items,
                scalar_prefixes=scalar_prefixes,
                label=f"{label} least completion",
                resource_meter=resource_meter,
            )
            total = 0
            for item_position, position in enumerate(positions):
                item_octets = scalar_prefixes[position]["json_value_octets"] + 2
                _require(
                    item_octets <= bounds.per_string_canonical_octet_ceiling,
                    f"{label} completion string {item_position} exceeds its canonical ceiling",
                )
                _require(
                    total <= SAFE_INTEGER_MAXIMUM - item_octets,
                    f"{label} completion octets exceed safe arithmetic",
                )
                total += item_octets
            _require(total == remaining_octets, f"{label} completion octets differ")
        _require(not attainable_runs, f"{label} generic attainable runs must be empty")
        return

    _require(state_kind == "QUERY_RESULT", f"{label} state kind differs")
    _require(len(key_atoms) == 2 and len(payload_atoms) == 3, f"{label} layout differs")
    query_kind = key_value(1, "TEXT")
    _require(
        query_kind == parameters["cardinality_query_kind"],
        f"{label} query kind differs from its invocation",
    )
    decision = payload_value(0, "BOOLEAN")
    cardinality_raw = payload_value(1, "CANONICAL_BYTES", "NULL")
    completion_raw = payload_value(2, "CANONICAL_BYTES", "NULL")
    _require(type(decision) is bool, f"{label} decision differs")
    if query_kind == "ALL_LEGAL_CARDINALITIES":
        _require(
            cardinality_raw is not None and completion_raw is None,
            f"{label} all-cardinality payload nullability differs",
        )
        cardinality_runs = _decode_ordered_string_feasible_cardinality_bitmap_runs(
            cardinality_raw,
            minimum_array_cardinality=parameters["minimum_array_cardinality"],
            maximum_array_cardinality=parameters["maximum_array_cardinality"],
            label=f"{label} feasible cardinalities",
        )
        _require(
            decision == bool(cardinality_runs),
            f"{label} decision differs from cardinality support",
        )
    else:
        _require(
            cardinality_raw is None and decision == (completion_raw is not None),
            f"{label} fixed-query payload nullability differs",
        )
        if completion_raw is not None:
            positions = _decode_ordered_string_least_completion_prefix_positions(
                completion_raw,
                expected_remaining_items=bounds.item_count_limit,
                scalar_prefixes=scalar_prefixes,
                preceding_prefix_positions=bounds.fixed_prefix_positions,
                label=f"{label} least completion",
                resource_meter=resource_meter,
            )
            _validate_ordered_string_completion_target(
                positions,
                bounds=bounds,
                scalar_prefixes=scalar_prefixes,
                label=f"{label} least completion",
            )
    expected_runs = (
        _ordered_string_singleton_bitmap(bounds.target_array_octets) if decision else []
    )
    _require(
        attainable_runs == expected_runs,
        f"{label} complete-array attainable runs differ",
    )


def _validate_derived_identity_recurrence_parameters(
    parameters: dict[str, Any],
    *,
    primitive_prefixes: list[dict[str, Any]],
    label: str,
) -> DerivedIdentityRecurrenceBounds:
    """Validate the recurrence fields whose authority is locally decidable."""

    _require(
        parameters["invocation_kind"]
        in {"MAXIMUM_SLICE_FEASIBILITY", "PREFIX_FEASIBILITY_OR_UNRANK"},
        f"{label} invocation kind differs",
    )
    _require_integer(
        parameters["safe_identity_node_position"],
        label=f"{label} safe-identity node position",
        minimum=1,
    )
    _require(
        type(parameters["semantic_identity_domain"]) is str
        and bool(parameters["semantic_identity_domain"]),
        f"{label} semantic-identity domain differs",
    )
    target = _require_integer(
        parameters["target_enclosing_canonical_octets"],
        label=f"{label} target enclosing octets",
        minimum=1,
    )
    _require_integer(
        parameters["input_prefix_frontier_child_position"],
        label=f"{label} input-prefix child position",
        minimum=1,
    )
    fixed_active_count = _require_integer(
        parameters["fixed_active_prefix_coordinate_count"],
        label=f"{label} fixed active-prefix count",
    )
    fixed_prefix_position = _require_integer(
        parameters["fixed_primitive_prefix_position"],
        label=f"{label} fixed primitive-prefix position",
        maximum=len(primitive_prefixes) - 1,
    )
    _require(
        primitive_prefixes[fixed_prefix_position]["active_atom_count"]
        == fixed_active_count,
        f"{label} fixed prefix/count binding differs",
    )
    payload_children = _require_array(
        parameters["ordered_identity_payload_child_positions"],
        label=f"{label} payload child positions",
        maximum_length=1_000_000,
    )
    previous_child_position = 0
    for child_ordinal, child_position in enumerate(payload_children, 1):
        checked_position = _require_integer(
            child_position,
            label=f"{label} payload child position {child_ordinal}",
            minimum=1,
        )
        _require(
            checked_position > previous_child_position,
            f"{label} payload child positions are not strictly increasing",
        )
        previous_child_position = checked_position
    observable_ids = _require_sha256_array(
        parameters["ordered_payload_observable_descriptor_ids"],
        label=f"{label} payload observable descriptor IDs",
    )
    relation_ids = _require_sha256_array(
        parameters["ordered_identity_relation_descriptor_ids"],
        label=f"{label} identity relation descriptor IDs",
    )
    return DerivedIdentityRecurrenceBounds(
        target_enclosing_canonical_octets=target,
        fixed_primitive_prefix_position=fixed_prefix_position,
        observable_descriptor_count=len(observable_ids),
        identity_relation_count=len(relation_ids),
    )


def _validate_text_recurrence_parameters(
    parameters: dict[str, Any],
    *,
    label: str,
) -> TextRecurrenceBounds:
    _require_sha256(parameters["text_language_id"], label=f"{label} language ID")
    ceiling = _require_integer(
        parameters["effective_canonical_octet_ceiling"],
        label=f"{label} effective canonical-octet ceiling",
        minimum=2,
    )
    relation_ids = _require_sha256_array(
        parameters["ordered_relation_descriptor_ids"],
        label=f"{label} relation descriptor IDs",
    )
    return TextRecurrenceBounds(
        effective_canonical_octet_ceiling=ceiling,
        relation_descriptor_count=len(relation_ids),
    )


def _validate_ascii_dfa_state_slots(
    *,
    key_atoms: list[dict[str, Any]],
    key_cells: list[dict[str, Any]],
    payload_atoms: list[dict[str, Any]],
    payload_cells: list[dict[str, Any]],
    attainable_runs: list[dict[str, Any]],
    bounds: TextRecurrenceBounds,
    scalar_prefixes: list[dict[str, Any]],
    label: str,
) -> None:
    _require(
        len(key_atoms) == 3 + bounds.relation_descriptor_count
        and not key_cells
        and len(payload_atoms) == 1
        and not payload_cells,
        f"{label} layout differs",
    )
    expected_key_kinds = [
        "POSITION",
        "POSITION",
        "SAFE_INTEGER",
        *(["POSITION"] * bounds.relation_descriptor_count),
    ]
    key_values: list[Any] = []
    for atom_position, (atom, expected_kind) in enumerate(
        zip(key_atoms, expected_key_kinds, strict=True)
    ):
        _require(
            atom["atom_kind"] == expected_kind,
            f"{label} key atom {atom_position} kind differs",
        )
        key_values.append(
            _validate_primitive_atom(
                atom,
                label=f"{label} key atom {atom_position}",
            )[1]
        )
    input_octet_count = _require_integer(
        key_values[0], label=f"{label} input octet count"
    )
    _require_integer(key_values[1], label=f"{label} DFA state position")
    json_value_octets = _require_integer(
        key_values[2], label=f"{label} JSON value octets"
    )
    for relation_position, residual_position in enumerate(key_values[3:], 1):
        _require_integer(
            residual_position,
            label=f"{label} relation residual position {relation_position}",
        )
    prefix_atom = payload_atoms[0]
    _require(
        prefix_atom["atom_kind"] == "POSITION",
        f"{label} least-prefix atom kind differs",
    )
    prefix_position = _require_integer(
        _validate_primitive_atom(
            prefix_atom,
            label=f"{label} least-prefix atom",
        )[1],
        label=f"{label} least-prefix position",
        maximum=len(scalar_prefixes) - 1,
    )
    prefix = scalar_prefixes[prefix_position]
    _require(
        prefix["scalar_count"] == input_octet_count
        and prefix["json_value_octets"] == json_value_octets,
        f"{label} least prefix/count binding differs",
    )
    terminal_octets = _require_integer(
        json_value_octets + 2,
        label=f"{label} terminal canonical octets",
    )
    _require(
        not attainable_runs
        or (
            terminal_octets <= bounds.effective_canonical_octet_ceiling
            and attainable_runs == _ordered_string_singleton_bitmap(terminal_octets)
        ),
        f"{label} terminal attainable runs differ",
    )


def _validate_unicode_nfc_state_slots(
    *,
    key_atoms: list[dict[str, Any]],
    key_cells: list[dict[str, Any]],
    payload_atoms: list[dict[str, Any]],
    payload_cells: list[dict[str, Any]],
    attainable_runs: list[dict[str, Any]],
    bounds: TextRecurrenceBounds,
    scalar_prefixes: list[dict[str, Any]],
    label: str,
) -> None:
    _require(
        len(key_atoms) == 6 + bounds.relation_descriptor_count
        and not key_cells
        and len(payload_atoms) == 1
        and not payload_cells,
        f"{label} layout differs",
    )
    expected_key_kinds = [
        "POSITION",
        "SAFE_INTEGER",
        "SAFE_INTEGER",
        "POSITION",
        "POSITION",
        "POSITION",
        *(["POSITION"] * bounds.relation_descriptor_count),
    ]
    key_values: list[Any] = []
    for atom_position, (atom, expected_kind) in enumerate(
        zip(key_atoms, expected_key_kinds, strict=True)
    ):
        _require(
            atom["atom_kind"] == expected_kind,
            f"{label} key atom {atom_position} kind differs",
        )
        key_values.append(
            _validate_primitive_atom(
                atom,
                label=f"{label} key atom {atom_position}",
            )[1]
        )
    input_scalar_count = _require_integer(
        key_values[0], label=f"{label} input scalar count"
    )
    _require_integer(key_values[1], label=f"{label} normalized UTF-8 octets")
    committed_json_value_octets = _require_integer(
        key_values[2], label=f"{label} committed JSON value octets"
    )
    leading_trim_class = _require_integer(
        key_values[3], label=f"{label} leading trim class", maximum=2
    )
    trailing_trim_class = _require_integer(
        key_values[4], label=f"{label} trailing trim class", maximum=2
    )
    segment_prefix_position = _require_integer(
        key_values[5],
        label=f"{label} normalization-segment prefix position",
        maximum=len(scalar_prefixes) - 1,
    )
    for relation_position, residual_position in enumerate(key_values[6:], 1):
        _require_integer(
            residual_position,
            label=f"{label} relation residual position {relation_position}",
        )
    _require(
        (input_scalar_count == 0 and leading_trim_class == trailing_trim_class == 0)
        or (
            input_scalar_count > 0
            and leading_trim_class in {1, 2}
            and trailing_trim_class in {1, 2}
        ),
        f"{label} trim-class emptiness differs",
    )
    source_prefix_atom = payload_atoms[0]
    _require(
        source_prefix_atom["atom_kind"] == "POSITION",
        f"{label} least-source-prefix atom kind differs",
    )
    source_prefix_position = _require_integer(
        _validate_primitive_atom(
            source_prefix_atom,
            label=f"{label} least-source-prefix atom",
        )[1],
        label=f"{label} least-source-prefix position",
        maximum=len(scalar_prefixes) - 1,
    )
    _require(
        scalar_prefixes[source_prefix_position]["scalar_count"] == input_scalar_count,
        f"{label} least source prefix/count binding differs",
    )
    open_segment_octets = scalar_prefixes[segment_prefix_position]["json_value_octets"]
    terminal_octets = _require_integer(
        committed_json_value_octets + open_segment_octets + 2,
        label=f"{label} terminal canonical octets",
    )
    _require(
        not attainable_runs
        or (
            terminal_octets <= bounds.effective_canonical_octet_ceiling
            and attainable_runs == _ordered_string_singleton_bitmap(terminal_octets)
        ),
        f"{label} terminal attainable runs differ",
    )


def _validate_derived_identity_state_slots(
    *,
    key_atoms: list[dict[str, Any]],
    key_cells: list[dict[str, Any]],
    payload_atoms: list[dict[str, Any]],
    payload_cells: list[dict[str, Any]],
    attainable_runs: list[dict[str, Any]],
    bounds: DerivedIdentityRecurrenceBounds,
    primitive_prefixes: list[dict[str, Any]],
    label: str,
    resource_meter: ProofResourceMeter,
) -> None:
    """Close terminal/nonterminal layout and target-run semantics."""

    _require(
        len(key_atoms) == 3
        and len(key_cells) == bounds.observable_descriptor_count
        and len(payload_atoms) == 2 + bounds.identity_relation_count
        and not payload_cells,
        f"{label} layout differs",
    )

    def atom_value(position: int, *allowed_kinds: str) -> tuple[str, Any]:
        atom = key_atoms[position]
        _require(
            atom["atom_kind"] in allowed_kinds,
            f"{label} key atom {position} kind differs",
        )
        return atom["atom_kind"], _validate_primitive_atom(
            atom,
            label=f"{label} key atom {position}",
        )[1]

    _, state_kind = atom_value(0, "TEXT")
    _require(state_kind == "PAYLOAD_PREFIX", f"{label} state kind differs")
    _, next_plan_position = atom_value(1, "POSITION")
    next_plan_position = _require_integer(
        next_plan_position,
        label=f"{label} next payload plan position",
    )
    _, current_prefix_position = atom_value(2, "POSITION")
    current_prefix_position = _require_integer(
        current_prefix_position,
        label=f"{label} current primitive-prefix position",
        maximum=len(primitive_prefixes) - 1,
    )

    fixed_prefix = bounds.fixed_primitive_prefix_position
    current_chain = _prefix_chain_positions(
        primitive_prefixes,
        current_prefix_position,
        label=f"{label} current primitive prefix",
        resource_meter=resource_meter,
    )
    _require(
        fixed_prefix == 0 or fixed_prefix in current_chain,
        f"{label} current prefix does not extend the fixed prefix",
    )

    least_atom = payload_atoms[0]
    _require(
        least_atom["atom_kind"] in {"POSITION", "NULL"},
        f"{label} least-completion atom kind differs",
    )
    least_prefix_position = _validate_primitive_atom(
        least_atom,
        label=f"{label} least-completion atom",
    )[1]
    if least_prefix_position is not None:
        least_prefix_position = _require_integer(
            least_prefix_position,
            label=f"{label} least-completion position",
            maximum=len(primitive_prefixes) - 1,
        )

    identity_atom = payload_atoms[1]
    _require(
        identity_atom["atom_kind"] in {"TEXT", "NULL"},
        f"{label} derived-identity atom kind differs",
    )
    derived_identity = _validate_primitive_atom(
        identity_atom,
        label=f"{label} derived-identity atom",
    )[1]
    relation_values: list[bool | None] = []
    for relation_position, relation_atom in enumerate(payload_atoms[2:], 1):
        _require(
            relation_atom["atom_kind"] in {"BOOLEAN", "NULL"},
            f"{label} relation atom {relation_position} kind differs",
        )
        relation_values.append(
            _validate_primitive_atom(
                relation_atom,
                label=f"{label} relation atom {relation_position}",
            )[1]
        )

    expected_target_runs = _ordered_string_singleton_bitmap(
        bounds.target_enclosing_canonical_octets
    )
    if next_plan_position == 0:
        _require_sha256(derived_identity, label=f"{label} terminal identity")
        _require(
            all(type(value) is bool for value in relation_values),
            f"{label} terminal relation values are not complete",
        )
        if attainable_runs:
            _require(
                least_prefix_position == current_prefix_position
                and attainable_runs == expected_target_runs,
                f"{label} accepted terminal completion/runs differ",
            )
        else:
            _require(
                least_prefix_position is None,
                f"{label} rejected terminal retains a completion",
            )
        return

    _require(
        derived_identity is None and all(value is None for value in relation_values),
        f"{label} nonterminal identity/relation payload differs",
    )
    if least_prefix_position is None:
        _require(not attainable_runs, f"{label} dead nonterminal has attainable runs")
        return
    least_chain = _prefix_chain_positions(
        primitive_prefixes,
        least_prefix_position,
        label=f"{label} least completing primitive prefix",
        resource_meter=resource_meter,
    )
    _require(
        (current_prefix_position == 0 or current_prefix_position in least_chain)
        and attainable_runs == expected_target_runs,
        f"{label} live nonterminal completion/runs differ",
    )


def _validate_transient_recurrence_catalog(
    value: Any,
    *,
    maximum_protocol_sha256: str,
    expected_catalog_id: str,
    allowed_prior_catalog_ids: frozenset[str],
    label: str,
    resource_meter: ProofResourceMeter | None = None,
) -> CatalogStaticEvidence:
    _require_sha256(maximum_protocol_sha256, label=f"{label} protocol SHA")
    _require_sha256(expected_catalog_id, label=f"{label} expected catalog ID")
    catalog = _require_exact_keys(
        value,
        TRANSIENT_RECURRENCE_CATALOG_KEYS,
        label=label,
    )
    meter = (
        resource_meter
        if resource_meter is not None
        else ProofResourceMeter(phase=SEED_CAP_DERIVATION_PHASE)
    )
    hash_octets_before = meter.value("hash_preimage_octets")
    _require(
        catalog["catalog_version"] == TRANSIENT_RECURRENCE_CATALOG_VERSION,
        f"{label} version differs",
    )
    recurrence_kind = catalog["recurrence_kind"]
    _require(
        recurrence_kind in TRANSIENT_RECURRENCE_KINDS,
        f"{label} recurrence kind differs",
    )
    raw_scalar_prefixes = _require_array(
        catalog["ordered_scalar_prefix_records"],
        label=f"{label} scalar-prefix pool",
        maximum_length=1_000_000,
    )
    raw_primitive_prefixes = _require_array(
        catalog["ordered_primitive_prefix_records"],
        label=f"{label} primitive-prefix pool",
        maximum_length=1_000_000,
    )
    raw_lex_intervals = _require_array(
        catalog["ordered_lex_interval_records"],
        label=f"{label} lex-interval pool",
        maximum_length=1_000_000,
    )
    records = _require_array(
        catalog["ordered_state_records"],
        label=f"{label} state records",
        maximum_length=1_000_000,
    )
    entry_count = (
        len(raw_scalar_prefixes)
        + len(raw_primitive_prefixes)
        + len(raw_lex_intervals)
        + len(records)
    )
    complete_root_octets = _canonical_octet_length(catalog)
    meter.reserve(
        {
            "state_catalog_entry_count": entry_count,
            "state_catalog_canonicalized_octets": complete_root_octets,
        }
    )
    referenced_prior_catalog_ids: list[str] = []
    _validate_proof_subject_locator(
        catalog["defining_subject_locator"],
        label=f"{label} defining subject locator",
        resource_meter=meter,
        referenced_prior_catalog_ids=referenced_prior_catalog_ids,
    )
    parameters = _require_exact_keys(
        catalog["recurrence_parameters"],
        TRANSIENT_RECURRENCE_PARAMETER_KEYS[recurrence_kind],
        label=f"{label} recurrence parameters",
    )
    scalar_prefixes = _validate_scalar_prefix_pool(
        catalog["ordered_scalar_prefix_records"],
        label=f"{label} scalar-prefix pool",
        ascii_only=recurrence_kind == "ASCII_DFA_DYNAMIC_PROGRAM_V1",
        resource_meter=meter,
    )
    primitive_prefixes = _validate_primitive_prefix_pool(
        catalog["ordered_primitive_prefix_records"],
        label=f"{label} primitive-prefix pool",
        resource_meter=meter,
    )
    lex_intervals = _validate_raw_lex_interval_pool(
        catalog["ordered_lex_interval_records"],
        scalar_prefix_count=len(scalar_prefixes),
        label=f"{label} lex-interval pool",
    )
    expected_pool_presence = {
        "ASCII_DFA_DYNAMIC_PROGRAM_V1": (True, False, False),
        "UNICODE_15_NFC_DYNAMIC_PROGRAM_V1": (True, False, False),
        "ORDERED_RAW_STRING_PREFIX_FEASIBILITY_V1": (True, False, True),
        "DERIVED_IDENTITY_PREFIX_FEASIBILITY_V1": (False, True, False),
    }[recurrence_kind]
    _require(
        tuple(
            bool(pool) for pool in (scalar_prefixes, primitive_prefixes, lex_intervals)
        )
        == expected_pool_presence,
        f"{label} recurrence-kind pool emptiness differs",
    )
    ordered_string_bounds = (
        _validate_ordered_string_recurrence_parameters(
            parameters,
            scalar_prefixes=scalar_prefixes,
            label=f"{label} ordered-string recurrence parameters",
            resource_meter=meter,
        )
        if recurrence_kind == "ORDERED_RAW_STRING_PREFIX_FEASIBILITY_V1"
        else None
    )
    derived_identity_bounds = (
        _validate_derived_identity_recurrence_parameters(
            parameters,
            primitive_prefixes=primitive_prefixes,
            label=f"{label} derived-identity recurrence parameters",
        )
        if recurrence_kind == "DERIVED_IDENTITY_PREFIX_FEASIBILITY_V1"
        else None
    )
    text_recurrence_bounds = (
        _validate_text_recurrence_parameters(
            parameters,
            label=f"{label} text recurrence parameters",
        )
        if recurrence_kind
        in {"ASCII_DFA_DYNAMIC_PROGRAM_V1", "UNICODE_15_NFC_DYNAMIC_PROGRAM_V1"}
        else None
    )
    previous_key: bytes | None = None
    for position, record_value in enumerate(records, 1):
        record = _require_exact_keys(
            record_value,
            TRANSIENT_RECURRENCE_STATE_KEYS,
            label=f"{label} state {position}",
        )
        _require(
            record["state_position"] == position,
            f"{label} state positions differ",
        )
        key_atoms = _validate_atom_array(
            record["ordered_state_key_atoms"],
            label=f"{label} key atoms {position}",
        )
        _require(
            all(atom["atom_kind"] != "INACTIVE" for atom in key_atoms),
            f"{label} key atoms {position} contain prefix-only INACTIVE",
        )
        key_cells = _validate_cell_array(
            record["ordered_state_key_cells"],
            allowed_prior_catalog_ids=allowed_prior_catalog_ids,
            label=f"{label} key cells {position}",
            resource_meter=meter,
            referenced_prior_catalog_ids=referenced_prior_catalog_ids,
        )
        payload_atoms = _validate_atom_array(
            record["ordered_state_payload_atoms"],
            label=f"{label} payload atoms {position}",
        )
        _require(
            all(atom["atom_kind"] != "INACTIVE" for atom in payload_atoms),
            f"{label} payload atoms {position} contain prefix-only INACTIVE",
        )
        payload_cells = _validate_cell_array(
            record["ordered_state_payload_cells"],
            allowed_prior_catalog_ids=allowed_prior_catalog_ids,
            label=f"{label} payload cells {position}",
            resource_meter=meter,
            referenced_prior_catalog_ids=referenced_prior_catalog_ids,
        )
        attainable_runs = _validate_bitmap_runs(
            record["ordered_attainable_length_bitmap_runs"],
            label=f"{label} attainable runs {position}",
            require_nonempty=False,
        )
        if ordered_string_bounds is not None:
            _validate_ordered_raw_string_state_slots(
                key_atoms=key_atoms,
                key_cells=key_cells,
                payload_atoms=payload_atoms,
                payload_cells=payload_cells,
                attainable_runs=attainable_runs,
                parameters=parameters,
                bounds=ordered_string_bounds,
                scalar_prefixes=scalar_prefixes,
                lex_intervals=lex_intervals,
                label=f"{label} ordered-string state {position}",
                resource_meter=meter,
            )
        elif derived_identity_bounds is not None:
            _validate_derived_identity_state_slots(
                key_atoms=key_atoms,
                key_cells=key_cells,
                payload_atoms=payload_atoms,
                payload_cells=payload_cells,
                attainable_runs=attainable_runs,
                bounds=derived_identity_bounds,
                primitive_prefixes=primitive_prefixes,
                label=f"{label} derived-identity state {position}",
                resource_meter=meter,
            )
        elif recurrence_kind == "ASCII_DFA_DYNAMIC_PROGRAM_V1":
            _require(
                text_recurrence_bounds is not None,
                f"{label} ASCII recurrence bounds are absent",
            )
            _validate_ascii_dfa_state_slots(
                key_atoms=key_atoms,
                key_cells=key_cells,
                payload_atoms=payload_atoms,
                payload_cells=payload_cells,
                attainable_runs=attainable_runs,
                bounds=text_recurrence_bounds,
                scalar_prefixes=scalar_prefixes,
                label=f"{label} ASCII state {position}",
            )
        elif recurrence_kind == "UNICODE_15_NFC_DYNAMIC_PROGRAM_V1":
            _require(
                text_recurrence_bounds is not None,
                f"{label} Unicode recurrence bounds are absent",
            )
            _validate_unicode_nfc_state_slots(
                key_atoms=key_atoms,
                key_cells=key_cells,
                payload_atoms=payload_atoms,
                payload_cells=payload_cells,
                attainable_runs=attainable_runs,
                bounds=text_recurrence_bounds,
                scalar_prefixes=scalar_prefixes,
                label=f"{label} Unicode state {position}",
            )
        state_key = _canonical_bytes([key_atoms, key_cells])
        _require(
            previous_key is None or previous_key < state_key,
            f"{label} state key order differs",
        )
        previous_key = state_key
    # TODO(P0): Independently derive every recurrence transition, state payload,
    # and invoking-node catalog set.  Ordered-string slot schemas and their
    # locally checkable bounds/nullability are closed above, but factor/fold and
    # least-unranking equality still require independent recurrence derivation.
    embedded_catalog_id = _require_sha256(
        catalog["recurrence_catalog_id"],
        label=f"{label} embedded catalog ID",
    )
    payload = {
        "maximum_protocol_sha256": maximum_protocol_sha256,
        **{
            name: item
            for name, item in catalog.items()
            if name != "recurrence_catalog_id"
        },
    }
    recomputed_catalog_id = _semantic_id(
        TRANSIENT_RECURRENCE_CATALOG_DOMAIN,
        payload,
        resource_meter=meter,
    )
    _require(
        embedded_catalog_id == recomputed_catalog_id == expected_catalog_id,
        f"{label} semantic identity differs",
    )
    return CatalogStaticEvidence(
        catalog=catalog,
        catalog_id=expected_catalog_id,
        entry_count=entry_count,
        complete_root_octets=complete_root_octets,
        validation_hash_preimage_octets=(
            meter.value("hash_preimage_octets") - hash_octets_before
        ),
        referenced_prior_catalog_ids=tuple(dict.fromkeys(referenced_prior_catalog_ids)),
    )


def _validate_derived_identity_mapping_catalog(
    value: Any,
    *,
    maximum_protocol_sha256: str,
    expected_catalog_id: str,
    label: str,
    resource_meter: ProofResourceMeter | None = None,
) -> CatalogStaticEvidence:
    _require_sha256(maximum_protocol_sha256, label=f"{label} protocol SHA")
    _require_sha256(expected_catalog_id, label=f"{label} expected catalog ID")
    catalog = _require_exact_keys(
        value,
        DERIVED_IDENTITY_MAPPING_CATALOG_KEYS,
        label=label,
    )
    meter = (
        resource_meter
        if resource_meter is not None
        else ProofResourceMeter(phase=SEED_CAP_DERIVATION_PHASE)
    )
    hash_octets_before = meter.value("hash_preimage_octets")
    _require(
        catalog["catalog_version"]
        == (
            "riskyieldmm.raw_v8_step2_external_schema_v2."
            "derived_identity_mapping_catalog.v1"
        ),
        f"{label} version differs",
    )
    semantic_domain = catalog["semantic_identity_domain"]
    _require(
        type(semantic_domain) is str and bool(semantic_domain),
        f"{label} semantic identity domain differs",
    )
    records = _require_array(
        catalog["ordered_mapping_records"],
        label=f"{label} mapping records",
        maximum_length=1_000_000,
    )
    _require(bool(records), f"{label} mapping records must not be empty")
    complete_root_octets = _canonical_octet_length(catalog)
    meter.reserve(
        {
            "state_catalog_entry_count": len(records),
            "state_catalog_canonicalized_octets": complete_root_octets,
        }
    )
    referenced_prior_catalog_ids: list[str] = []
    _validate_proof_subject_locator(
        catalog["defining_subject_locator"],
        label=f"{label} defining subject locator",
        resource_meter=meter,
        referenced_prior_catalog_ids=referenced_prior_catalog_ids,
    )
    previous_preimage: bytes | None = None
    for position, record_value in enumerate(records, 1):
        record = _require_exact_keys(
            record_value,
            DERIVED_IDENTITY_MAPPING_RECORD_KEYS,
            label=f"{label} mapping record {position}",
        )
        encoded_preimage = record["semantic_identity_preimage_canonical_bytes_hex"]
        _require(
            type(encoded_preimage) is str
            and bool(encoded_preimage)
            and len(encoded_preimage) % 2 == 0
            and re.fullmatch(r"[0-9a-f]+", encoded_preimage) is not None,
            f"{label} mapping preimage {position} differs",
        )
        preimage_octets = len(encoded_preimage) // 2
        meter.add("hash_preimage_octets", preimage_octets)
        preimage = bytes.fromhex(encoded_preimage)
        decoded = _decode_compact_json(
            preimage,
            label=f"{label} mapping preimage {position}",
        )
        _require_exact_keys(
            decoded,
            frozenset(
                {
                    "canonicalization_version",
                    "domain",
                    "payload",
                    "schema_version",
                }
            ),
            label=f"{label} mapping semantic preimage {position}",
        )
        _require(
            decoded["canonicalization_version"] == CANONICALIZATION_VERSION
            and decoded["schema_version"] == MEASUREMENT_SCHEMA_VERSION
            and decoded["domain"] == semantic_domain
            and type(decoded["payload"]) is dict,
            f"{label} mapping semantic payload {position} differs",
        )
        derived_identity = hashlib.sha256(preimage).hexdigest()
        _require(
            record["derived_identity_text"] == derived_identity,
            f"{label} derived identity {position} differs",
        )
        derived_identity_canonical_sha256, _ = _metered_canonical_sha256(
            derived_identity,
            meter=meter,
        )
        _require(
            record["derived_identity_canonical_sha256"]
            == derived_identity_canonical_sha256,
            f"{label} derived identity canonical SHA {position} differs",
        )
        _require(
            previous_preimage is None or previous_preimage < preimage,
            f"{label} mapping preimage order differs",
        )
        previous_preimage = preimage
    payload = {"maximum_protocol_sha256": maximum_protocol_sha256, **catalog}
    _require(
        _semantic_id(
            DERIVED_IDENTITY_MAPPING_CATALOG_DOMAIN,
            payload,
            resource_meter=meter,
        )
        == expected_catalog_id,
        f"{label} semantic identity differs",
    )
    return CatalogStaticEvidence(
        catalog=catalog,
        catalog_id=expected_catalog_id,
        entry_count=len(records),
        complete_root_octets=complete_root_octets,
        validation_hash_preimage_octets=(
            meter.value("hash_preimage_octets") - hash_octets_before
        ),
        referenced_prior_catalog_ids=tuple(dict.fromkeys(referenced_prior_catalog_ids)),
    )


def _nullable_text_sort_key(value: Any) -> tuple[int, str]:
    if value is None:
        return (0, "")
    _require(type(value) is str, "nullable text sort value differs")
    return (1, value)


def _nullable_integer_sort_key(value: Any) -> tuple[int, int]:
    if value is None:
        return (0, 0)
    _require(type(value) is int, "nullable integer sort value differs")
    return (1, value)


def _validate_complete_pilot_context_record(
    record: Any,
    *,
    entry: dict[str, Any],
    validated_registry: dict[str, Any],
    expected_record_type_name: str | None,
    label: str,
    resource_meter: ProofResourceMeter | None,
) -> ValidatedRecord:
    """Validate one complete context record against its frozen V3 descriptor."""

    _require(type(record) is dict, f"{label} is not one complete record")
    _validate_json_scalars(record)
    record_type_name = entry["record_type_name"]
    _require(
        type(record_type_name) is str and bool(record_type_name),
        f"{label} record type differs",
    )
    if expected_record_type_name is not None:
        _require(
            record_type_name == expected_record_type_name,
            f"{label} record type differs from its materialized authority",
        )
    descriptor_matches = [
        descriptor
        for descriptor in validated_registry["ordered_external_type_descriptors"]
        if descriptor["type_name"] == record_type_name
    ]
    _require(
        len(descriptor_matches) == 1,
        f"{label} record type has no unique structural descriptor",
    )
    descriptor = descriptor_matches[0]
    identity_field = descriptor["identity_field"]
    _require(
        descriptor["type_form"] == "RECORD"
        and type(identity_field) is str
        and bool(identity_field),
        f"{label} context type is not an identified structural record",
    )
    _require(
        entry["record_identity_field"] == identity_field,
        f"{label} identity field differs from its structural descriptor",
    )
    member_descriptors = _require_array(
        descriptor["record_member_descriptors"],
        label=f"{label} structural record members",
    )
    expected_member_names = frozenset(
        member["member_name"] for member in member_descriptors
    )
    _require(
        len(expected_member_names) == len(member_descriptors),
        f"{label} structural descriptor repeats a member name",
    )
    _require_exact_keys(record, expected_member_names, label=f"{label} record")
    _require(
        record["canonicalization_version"] == CANONICALIZATION_VERSION
        and record["measurement_schema_version"] == MEASUREMENT_SCHEMA_VERSION
        and record["record_domain"] == descriptor["described_record_domain"],
        f"{label} record envelope differs from its structural descriptor",
    )
    actual_identity = _require_sha256(
        record[identity_field],
        label=f"{label} resolved record identity",
    )
    _require(
        entry["record_identity"] == actual_identity,
        f"{label} record identity differs from its complete record",
    )
    identity_member_order = _require_array(
        descriptor["identity_payload_member_order"],
        label=f"{label} identity payload order",
    )
    _require(
        all(
            type(member_name) is str and member_name in record
            for member_name in identity_member_order
        ),
        f"{label} identity payload order differs",
    )
    identity_payload = {
        member_name: record[member_name] for member_name in identity_member_order
    }
    _require(
        _semantic_id(
            descriptor["described_record_domain"],
            identity_payload,
            resource_meter=resource_meter,
        )
        == actual_identity,
        f"{label} resolved record semantic identity differs",
    )
    canonical_length = _canonical_octet_length(record)
    if resource_meter is None:
        canonical_sha256 = _canonical_sha256_stream(record)
    else:
        canonical_sha256, hashed_octets = _metered_canonical_sha256(
            record,
            meter=resource_meter,
        )
        _require(
            hashed_octets == canonical_length,
            f"{label} canonical hash length differs",
        )
    _require(
        entry["record_canonical_byte_length"] == canonical_length,
        f"{label} record canonical length differs",
    )
    _require(
        entry["record_canonical_sha256"] == canonical_sha256,
        f"{label} record canonical SHA differs",
    )
    return ValidatedRecord(
        record_type_name=record_type_name,
        record_identity_field=identity_field,
        record_identity=actual_identity,
        record_canonical_byte_length=canonical_length,
        record_canonical_sha256=canonical_sha256,
        record=record,
    )


def _validate_pilot_context_manifest(
    value: Any,
    *,
    maximum_protocol_sha256: str,
    validated_inventory: dict[str, Any],
    validated_registry: dict[str, Any],
    validated_max64_context_authority: dict[str, Any],
    label: str,
    resource_meter: ProofResourceMeter | None = None,
) -> ValidatedPilotContextManifest:
    _require_sha256(maximum_protocol_sha256, label=f"{label} protocol SHA")
    embedded_registry = (
        validated_inventory.get("external_schema_registry_v2")
        if type(validated_inventory) is dict
        else None
    )
    _require(
        type(validated_inventory) is dict
        and validated_inventory.get("inventory_sha256") == INVENTORY_SEMANTIC_ID
        and type(embedded_registry) is dict
        and embedded_registry.get("external_schema_registry_id") == REGISTRY_ID
        and type(validated_registry) is dict
        and validated_registry.get("external_schema_registry_id") == REGISTRY_ID,
        f"{label} validated V3 authority binding differs",
    )
    _require_exact_keys(
        validated_max64_context_authority,
        MAX64_CONTEXT_AUTHORITY_ROOT_KEYS,
        label=f"{label} validated max64 context authority",
    )
    _require_array(
        validated_max64_context_authority["observations"],
        label=f"{label} validated max64 observations",
        exact_length=67,
    )
    _require(
        type(validated_max64_context_authority["root"]) is dict
        and type(validated_max64_context_authority["selector"]) is dict,
        f"{label} validated max64 record roots differ",
    )
    manifest = _require_exact_keys(value, PILOT_CONTEXT_MANIFEST_KEYS, label=label)
    _require(
        manifest["manifest_version"]
        == (
            "riskyieldmm.raw_v8_step2_external_schema_v2."
            "maximum_protocol_pilot_context_manifest.v1"
        )
        and manifest["canonicalization_version"] == CANONICALIZATION_VERSION
        and manifest["measurement_schema_version"] == MEASUREMENT_SCHEMA_VERSION,
        f"{label} version differs",
    )
    _require(
        manifest["maximum_protocol_sha256"] == maximum_protocol_sha256
        and manifest["source_inventory_sha256"] == INVENTORY_SEMANTIC_ID
        and manifest["external_schema_registry_id"] == REGISTRY_ID
        and manifest["rule_literal_authority_sha256"] == LITERAL_AUTHORITY_RAW_SHA256
        and manifest["application_witness_raw_sha256"] == APPLICATION_WITNESS_RAW_SHA256
        and manifest["max64_context_authority_raw_sha256"]
        == MAX64_CONTEXT_AUTHORITY_RAW_SHA256,
        f"{label} authority binding differs",
    )
    entries = _require_array(
        manifest["ordered_context_object_entries"],
        label=f"{label} context entries",
        maximum_length=1_000_000,
    )
    previous_sort: tuple[Any, ...] | None = None
    seen_context_object_ids: set[str] = set()
    resolved_entries: list[ResolvedPilotContextObjectEntry] = []
    for position, entry_value in enumerate(entries, 1):
        entry = _require_exact_keys(
            entry_value,
            PILOT_CONTEXT_OBJECT_ENTRY_KEYS,
            label=f"{label} context entry {position}",
        )
        _require(
            entry["context_object_position"] == position,
            f"{label} context entry positions differ",
        )
        source_kind = entry["context_source_kind"]
        _require(
            source_kind
            in {
                "INLINE_PILOT_CONTEXT_RECORD",
                "MATERIALIZED_MAX64_CONTEXT_POINTER",
            },
            f"{label} context source kind differs",
        )
        authority = entry["source_authority_sha256"]
        pointer = entry["source_json_pointer"]
        role = entry["derived_record_role"]
        ordinal = entry["derived_sequence_ordinal"]
        inline_record = entry["inline_record"]
        if source_kind == "INLINE_PILOT_CONTEXT_RECORD":
            _require(
                authority is None
                and pointer is None
                and role is None
                and ordinal is None
                and type(inline_record) is dict,
                f"{label} inline context nullability differs",
            )
            resolved_record = inline_record
            expected_record_type_name = None
        else:
            _require(
                authority == MAX64_CONTEXT_AUTHORITY_RAW_SHA256
                and inline_record is None
                and role in {"ROOT_RECORD", "OBSERVATION_RECORD"},
                f"{label} materialized context authority/role differs",
            )
            if role == "ROOT_RECORD":
                _require(
                    pointer == "/root" and ordinal is None,
                    f"{label} root pointer differs",
                )
                expected_record_type_name = "TargetObservationRootV2"
            else:
                _require_integer(
                    ordinal,
                    label=f"{label} observation ordinal {position}",
                    maximum=66,
                )
                _require(
                    pointer == f"/observations/{ordinal}",
                    f"{label} observation pointer differs",
                )
                expected_record_type_name = "TargetObservationV2"
            resolved_record = _resolve_absolute_rfc6901_pointer(
                validated_max64_context_authority,
                pointer,
                label=f"{label} context entry {position} materialized pointer",
            )
        validated_record = _validate_complete_pilot_context_record(
            resolved_record,
            entry=entry,
            validated_registry=validated_registry,
            expected_record_type_name=expected_record_type_name,
            label=f"{label} context entry {position}",
            resource_meter=resource_meter,
        )
        context_object_payload = {
            "maximum_protocol_sha256": maximum_protocol_sha256,
            "source_inventory_sha256": INVENTORY_SEMANTIC_ID,
            "external_schema_registry_id": REGISTRY_ID,
            "rule_literal_authority_sha256": LITERAL_AUTHORITY_RAW_SHA256,
            "record_type_name": validated_record.record_type_name,
            "record_identity_field": validated_record.record_identity_field,
            "record_identity": validated_record.record_identity,
            "record_canonical_byte_length": (
                validated_record.record_canonical_byte_length
            ),
            "record_canonical_sha256": validated_record.record_canonical_sha256,
            "record": validated_record.record,
        }
        expected_context_object_id = _semantic_id(
            MAXIMUM_CONTEXT_OBJECT_DOMAIN,
            context_object_payload,
            resource_meter=resource_meter,
        )
        _require(
            _require_sha256(
                entry["maximum_context_object_id"],
                label=f"{label} context-object ID {position}",
            )
            == expected_context_object_id,
            f"{label} context-object ID {position} differs",
        )
        _require(
            expected_context_object_id not in seen_context_object_ids,
            f"{label} repeats context-object ID {expected_context_object_id}",
        )
        seen_context_object_ids.add(expected_context_object_id)
        sort_key = (
            validated_record.record_type_name,
            validated_record.record_identity,
            validated_record.record_canonical_sha256,
            source_kind,
            _nullable_text_sort_key(pointer),
            _nullable_text_sort_key(role),
            _nullable_integer_sort_key(ordinal),
        )
        _require(
            previous_sort is None or previous_sort < sort_key,
            f"{label} context entry order differs",
        )
        previous_sort = sort_key
        resolved_entries.append(
            ResolvedPilotContextObjectEntry(
                entry=entry,
                validated_record=validated_record,
                maximum_context_object_id=expected_context_object_id,
            )
        )
    payload = {
        name: item
        for name, item in manifest.items()
        if name != "maximum_context_object_manifest_id"
    }
    _require(
        manifest["maximum_context_object_manifest_id"]
        == _semantic_id(
            PILOT_CONTEXT_MANIFEST_DOMAIN,
            payload,
            resource_meter=resource_meter,
        ),
        f"{label} semantic identity differs",
    )
    return ValidatedPilotContextManifest(
        manifest=manifest,
        resolved_entries=tuple(resolved_entries),
    )


def _external_type_descriptor(
    validated_registry: dict[str, Any],
    type_name: str,
    *,
    label: str,
) -> dict[str, Any]:
    matches = [
        descriptor
        for descriptor in validated_registry["ordered_external_type_descriptors"]
        if descriptor["type_name"] == type_name
    ]
    _require(len(matches) == 1, f"{label} type has no unique descriptor")
    return matches[0]


def _validate_pilot_witness_shape(
    value: Any,
    *,
    expected_type_name: str,
    expected_alternative_name: str | None,
    validated_registry: dict[str, Any],
    label: str,
) -> dict[str, Any]:
    """Validate the retained witness's closed structural row shape.

    This bounded helper deliberately does not replace the later full graph,
    scalar-language, intrinsic-rule, or codec runtime.
    """

    _require(type(value) is dict, f"{label} must be one complete record")
    witness = value
    _validate_json_scalars(witness)
    descriptor = _external_type_descriptor(
        validated_registry,
        expected_type_name,
        label=label,
    )
    if descriptor["type_form"] == "TAGGED_UNION":
        alternatives = descriptor["tagged_union_descriptor"]["ordered_alternatives"]
        matches = [
            alternative
            for alternative in alternatives
            if alternative["alternative_name"] == expected_alternative_name
        ]
        _require(
            expected_alternative_name is not None and len(matches) == 1,
            f"{label} union alternative differs",
        )
        descriptor = _external_type_descriptor(
            validated_registry,
            matches[0]["referenced_type_name"],
            label=f"{label} selected union body",
        )
    else:
        _require(
            descriptor["type_form"] == "RECORD" and expected_alternative_name is None,
            f"{label} record/alternative binding differs",
        )
    members = _require_array(
        descriptor["record_member_descriptors"],
        label=f"{label} member descriptors",
    )
    expected_members = frozenset(member["member_name"] for member in members)
    _require(
        len(expected_members) == len(members),
        f"{label} descriptor repeats a member name",
    )
    _require_exact_keys(witness, expected_members, label=label)
    canonical_length = _canonical_octet_length(witness)
    relation = descriptor["codec_byte_bound_relation"]
    limit = descriptor["codec_octet_limit"]
    _require(
        (relation == "LE" and canonical_length <= limit)
        or (relation == "LT" and canonical_length < limit),
        f"{label} exceeds its descriptor codec bound",
    )
    return witness


def _validate_complete_pilot_witness_record(
    value: Any,
    *,
    expected_type_name: str,
    expected_alternative_name: str | None,
    validated_registry: dict[str, Any],
    label: str,
    resource_meter: ProofResourceMeter,
) -> ValidatedRecord:
    """Validate and content-identify one complete inline pilot witness."""

    witness = _validate_pilot_witness_shape(
        value,
        expected_type_name=expected_type_name,
        expected_alternative_name=expected_alternative_name,
        validated_registry=validated_registry,
        label=label,
    )
    root_descriptor = _external_type_descriptor(
        validated_registry,
        expected_type_name,
        label=label,
    )
    descriptor = root_descriptor
    if root_descriptor["type_form"] == "TAGGED_UNION":
        alternatives = root_descriptor["tagged_union_descriptor"][
            "ordered_alternatives"
        ]
        matches = [
            alternative
            for alternative in alternatives
            if alternative["alternative_name"] == expected_alternative_name
        ]
        _require(len(matches) == 1, f"{label} selected alternative differs")
        descriptor = _external_type_descriptor(
            validated_registry,
            matches[0]["referenced_type_name"],
            label=f"{label} selected body",
        )

    canonical_length = _canonical_octet_length(witness)
    canonical_sha256, hashed_octets = _metered_canonical_sha256(
        witness,
        meter=resource_meter,
    )
    _require(
        hashed_octets == canonical_length,
        f"{label} canonical hash length differs",
    )
    identity_field = descriptor["identity_field"]
    if identity_field is None:
        reference_identity_field = "$canonical_sha256"
        identity = canonical_sha256
    else:
        _require(
            type(identity_field) is str
            and bool(identity_field)
            and identity_field in witness,
            f"{label} identity field differs",
        )
        identity = _require_sha256(
            witness[identity_field],
            label=f"{label} identity",
        )
        identity_members = _require_array(
            descriptor["identity_payload_member_order"],
            label=f"{label} identity payload order",
        )
        _require(
            type(descriptor["described_record_domain"]) is str
            and bool(descriptor["described_record_domain"])
            and all(
                type(member_name) is str and member_name in witness
                for member_name in identity_members
            ),
            f"{label} identity authority differs",
        )
        identity_payload = {
            member_name: witness[member_name] for member_name in identity_members
        }
        _require(
            _semantic_id(
                descriptor["described_record_domain"],
                identity_payload,
                resource_meter=resource_meter,
            )
            == identity,
            f"{label} semantic identity differs",
        )
        reference_identity_field = identity_field
    return ValidatedRecord(
        record_type_name=expected_type_name,
        record_identity_field=reference_identity_field,
        record_identity=identity,
        record_canonical_byte_length=canonical_length,
        record_canonical_sha256=canonical_sha256,
        record=witness,
    )


def _resolve_pilot_record_reference(
    value: Any,
    *,
    witness_record: dict[str, Any],
    context_manifest: ValidatedPilotContextManifest,
    validated_inventory: dict[str, Any],
    validated_registry: dict[str, Any],
    permitted_inventory_pointer_authority: Mapping[str, str],
    expected_reference_kind: str,
    expected_inventory_pointer: str | None,
    expected_record_type_name: str,
    expected_alternative_name: str | None,
    label: str,
    resource_meter: ProofResourceMeter,
) -> ResolvedRecordReference:
    """Resolve one retained pilot-leaf reference through its closed authority."""

    if expected_reference_kind == "V3_INVENTORY_POINTER":
        return _resolve_v3_inventory_record_reference(
            value,
            validated_inventory=validated_inventory,
            validated_registry=validated_registry,
            permitted_inventory_pointer_authority=(
                permitted_inventory_pointer_authority
            ),
            expected_inventory_pointer=expected_inventory_pointer,
            expected_record_type_name=expected_record_type_name,
            label=label,
            resource_meter=resource_meter,
        )
    reference = _validate_maximum_record_reference(
        value,
        expected_reference_kind=expected_reference_kind,
        expected_inventory_pointer=None,
        label=label,
        resource_meter=resource_meter,
    )
    _require(
        reference["record_type_name"] == expected_record_type_name,
        f"{label} record type differs from its leaf binding",
    )
    if expected_reference_kind == "WITNESS_RECORD":
        validated_record = _validate_complete_pilot_witness_record(
            witness_record,
            expected_type_name=expected_record_type_name,
            expected_alternative_name=expected_alternative_name,
            validated_registry=validated_registry,
            label=f"{label} inline witness",
            resource_meter=resource_meter,
        )
        for name in (
            "record_type_name",
            "record_identity_field",
            "record_identity",
            "record_canonical_byte_length",
            "record_canonical_sha256",
        ):
            _require(
                reference[name] == getattr(validated_record, name),
                f"{label} {name} differs from the inline witness",
            )
    else:
        _require(
            expected_reference_kind == "CONTEXT_OBJECT",
            f"{label} unsupported pilot reference kind",
        )
        context_object_id = reference["maximum_context_object_id"]
        matches = [
            entry
            for entry in context_manifest.resolved_entries
            if entry.maximum_context_object_id == context_object_id
        ]
        _require(
            len(matches) == 1,
            f"{label} does not resolve exactly one manifest entry",
        )
        validated_record = matches[0].validated_record
        for name in (
            "record_type_name",
            "record_identity_field",
            "record_identity",
            "record_canonical_byte_length",
            "record_canonical_sha256",
        ):
            _require(
                reference[name] == getattr(validated_record, name),
                f"{label} {name} differs from its manifest object",
            )
    return ResolvedRecordReference(
        reference=reference,
        validated_record=validated_record,
    )


def _application_invocation(
    application_name: str,
    application_invocation_ordinal: int,
    bound_observation_ordinal: int | None,
) -> dict[str, Any]:
    return {
        "application_name": application_name,
        "application_invocation_ordinal": application_invocation_ordinal,
        "bound_observation_ordinal": bound_observation_ordinal,
    }


def _derive_profile_application_invocations(
    profile: dict[str, Any],
    *,
    selected_root_family: dict[str, Any] | None,
    label: str,
) -> list[dict[str, Any]]:
    formula = profile["application_schedule_formula"]
    if formula == "OUTER_RESULT_SIGNED_SPEC_SINGLE_APPLICATION_V1":
        _require(
            selected_root_family is None,
            f"{label} outer-result schedule cannot select a root family",
        )
        return [_application_invocation(OUTER_RESULT_APPLICATION_NAME, 0, None)]
    _require(
        selected_root_family is not None,
        f"{label} root schedule has no selected root family",
    )
    observation_count = _require_integer(
        selected_root_family["observation_count"],
        label=f"{label} observation count",
        minimum=1,
        maximum=67,
    )
    selector_present = selected_root_family["selector_present"]
    _require(type(selector_present) is bool, f"{label} selector presence differs")
    expected_formula = (
        "SELECTOR_PRESENT_2N_PLUS_3_CALLS_187N_PLUS_2_EVALS_1872N_PLUS_7_NODES_V1"
        if selector_present
        else ("SELECTOR_FREE_2N_PLUS_2_CALLS_187N_PLUS_1_EVALS_1872N_PLUS_4_NODES_V1")
    )
    _require(
        formula
        in {expected_formula, "FINITE_UNION_OF_LISTED_ROOT_FAMILY_SCHEDULES_V1"},
        f"{label} selected-family schedule formula differs",
    )
    invocations: list[dict[str, Any]] = []
    if selector_present:
        invocations.append(
            _application_invocation(SELECTOR_MARKER_APPLICATION_NAME, 0, None)
        )
    for name in (
        OBSERVATION_AGGREGATE_APPLICATION_NAME,
        OBSERVATION_FIELDS_APPLICATION_NAME,
    ):
        invocations.extend(
            _application_invocation(name, ordinal, ordinal)
            for ordinal in range(observation_count)
        )
    invocations.extend(
        (
            _application_invocation(
                ROOT_OBSERVATION_MEMBERSHIP_APPLICATION_NAME,
                0,
                None,
            ),
            _application_invocation(
                ROOT_SELECTOR_LIFECYCLE_APPLICATION_NAME,
                0,
                None,
            ),
        )
    )
    _require(
        invocations
        == sorted(
            invocations,
            key=lambda item: (
                item["application_name"],
                item["application_invocation_ordinal"],
                _nullable_integer_sort_key(item["bound_observation_ordinal"]),
            ),
        ),
        f"{label} internally derived invocation order differs",
    )
    return invocations


def _resolve_typed_member_path(
    value: Any,
    path: Any,
    *,
    label: str,
) -> Any:
    members = _require_array(path, label=label, maximum_length=1_000_000)
    current = value
    for position, member_name in enumerate(members, 1):
        _require(
            type(member_name) is str and bool(member_name),
            f"{label} member {position} differs",
        )
        _require(
            type(current) is dict and member_name in current,
            f"{label} member {position} is unresolved",
        )
        current = current[member_name]
    return current


def _validate_pilot_retained_leaf(
    *,
    pilot_context_manifest: Any,
    pilot_witness_record: Any,
    pilot_scope_witness_context: Any,
    maximum_protocol_sha256: str,
    expected_type_name: str,
    expected_alternative_name: str | None,
    expected_constraint_scope: str,
    expected_measurement_binding: dict[str, Any],
    expected_profile: dict[str, Any] | None,
    validated_inventory: dict[str, Any],
    validated_registry: dict[str, Any],
    validated_max64_context_authority: dict[str, Any],
    label: str,
    resource_meter: ProofResourceMeter,
) -> ValidatedPilotLeaf:
    """Resolve a complete dormant-pilot leaf without executing rule runtime."""

    witness = _validate_pilot_witness_shape(
        pilot_witness_record,
        expected_type_name=expected_type_name,
        expected_alternative_name=expected_alternative_name,
        validated_registry=validated_registry,
        label=f"{label} witness",
    )
    manifest = _validate_pilot_context_manifest(
        pilot_context_manifest,
        maximum_protocol_sha256=maximum_protocol_sha256,
        validated_inventory=validated_inventory,
        validated_registry=validated_registry,
        validated_max64_context_authority=validated_max64_context_authority,
        label=f"{label} context manifest",
        resource_meter=resource_meter,
    )
    binding_kind = expected_measurement_binding["binding_kind"]
    if expected_profile is None:
        pointer_authority: Mapping[str, str] = MappingProxyType({})
        expected_profile_id = None
    else:
        _require_exact_keys(
            expected_profile,
            PROFILE_KEYS,
            label=f"{label} profile",
        )
        _require(
            expected_profile["maximum_constraint_scope_profile_id"]
            == _profile_id(expected_profile)
            and expected_profile["constraint_scope"] == expected_constraint_scope
            and expected_profile["measured_type_name"] == expected_type_name,
            f"{label} profile identity/scope/type differs",
        )
        pointer_authority = _inventory_pointer_authority_from_profile(
            expected_profile,
            label=f"{label} profile",
        )
        expected_profile_id = expected_profile["maximum_constraint_scope_profile_id"]
    resolved_context_ids: list[str] = []
    context_reference_count = 0
    observation_count = 0
    application_invocation_count = 0
    charged_cross_rule_evaluation_count = 0
    direct_cross_expression_node_count = 0

    def resolve(
        reference_value: Any,
        *,
        kind: str,
        record_type_name: str,
        reference_label: str,
        inventory_pointer: str | None = None,
    ) -> ResolvedRecordReference:
        nonlocal context_reference_count
        resolved = _resolve_pilot_record_reference(
            reference_value,
            witness_record=witness,
            context_manifest=manifest,
            validated_inventory=validated_inventory,
            validated_registry=validated_registry,
            permitted_inventory_pointer_authority=pointer_authority,
            expected_reference_kind=kind,
            expected_inventory_pointer=inventory_pointer,
            expected_record_type_name=record_type_name,
            expected_alternative_name=(
                expected_alternative_name
                if kind == "WITNESS_RECORD" and record_type_name == expected_type_name
                else None
            ),
            label=reference_label,
            resource_meter=resource_meter,
        )
        if kind == "CONTEXT_OBJECT":
            context_reference_count += 1
            resolved_context_ids.append(resolved.reference["maximum_context_object_id"])
        return resolved

    context = pilot_scope_witness_context
    if binding_kind == "SELF_RECORD":
        _require(
            expected_constraint_scope == "INTRINSIC_TYPE"
            and expected_profile is None
            and context is None,
            f"{label} intrinsic concrete scope context differs",
        )
    else:
        _require(type(context) is dict, f"{label} scope context is not a record")
        context_kind = context.get("context_kind")
        _require(
            context_kind in PILOT_SCOPE_WITNESS_CONTEXT_KEYS,
            f"{label} scope context kind differs",
        )
        context = _require_exact_keys(
            context,
            PILOT_SCOPE_WITNESS_CONTEXT_KEYS[context_kind],
            label=f"{label} scope context",
        )
        if binding_kind == "SELF_UNION_VALUE":
            _require(
                context_kind == "SELF_VALUE"
                and expected_constraint_scope == "INTRINSIC_TYPE"
                and expected_profile is None,
                f"{label} self-value context differs",
            )
        elif binding_kind == "OWNER_MEMBER_UNION_VALUE":
            _require(
                context_kind == "OWNER_MEMBER"
                and expected_constraint_scope == "INTRINSIC_TYPE"
                and expected_profile is None,
                f"{label} owner-member context differs",
            )
            owner_type_name = expected_measurement_binding["validation_root_type_name"]
            owner = resolve(
                context["owner_record_reference"],
                kind="CONTEXT_OBJECT",
                record_type_name=owner_type_name,
                reference_label=f"{label} owner reference",
            )
            expected_path = expected_measurement_binding[
                "measured_value_typed_member_path"
            ]
            _require(
                context["payload_typed_member_path"] == expected_path
                and bool(expected_path),
                f"{label} owner payload path differs",
            )
            selected_payload = _resolve_typed_member_path(
                owner.validated_record.record,
                expected_path,
                label=f"{label} owner payload path",
            )
            _require(
                _canonical_bytes(selected_payload) == _canonical_bytes(witness),
                f"{label} owner payload differs from the inline witness",
            )
            union_descriptor = _external_type_descriptor(
                validated_registry,
                expected_type_name,
                label=f"{label} owner union",
            )["tagged_union_descriptor"]
            alternatives = [
                alternative
                for alternative in union_descriptor["ordered_alternatives"]
                if alternative["alternative_name"] == expected_alternative_name
            ]
            _require(len(alternatives) == 1, f"{label} owner alternative differs")
            for discriminator in alternatives[0]["ordered_discriminator_literals"]:
                actual = _resolve_typed_member_path(
                    owner.validated_record.record,
                    [discriminator["member_name"]],
                    label=f"{label} owner discriminator",
                )
                _require(
                    actual == discriminator["text_value"],
                    f"{label} owner discriminator differs",
                )
        elif binding_kind == "OUTER_RESULT_RECORD":
            _require(
                context_kind == "OUTER_RESULT_APPLICATION"
                and expected_constraint_scope == "FROZEN_FIXTURE"
                and expected_profile is not None
                and context["constraint_scope_profile_id"] == expected_profile_id,
                f"{label} outer-result context/profile differs",
            )
            resolve(
                context["operation_result_record_reference"],
                kind="WITNESS_RECORD",
                record_type_name=expected_type_name,
                reference_label=f"{label} operation-result witness reference",
            )
            spec_pointer = (
                f"/fixture_records/operation_specs/{expected_profile['operation_kind']}"
            )
            spec = resolve(
                context["operation_spec_authority_reference"],
                kind="V3_INVENTORY_POINTER",
                record_type_name="CapacityMeasurementOperationSpec",
                inventory_pointer=spec_pointer,
                reference_label=f"{label} operation-spec authority reference",
            )
            _require(
                witness["operation_kind"] == expected_profile["operation_kind"]
                and spec.validated_record.record["operation_kind"]
                == expected_profile["operation_kind"],
                f"{label} outer-result operation binding differs",
            )
            expected_invocations = _derive_profile_application_invocations(
                expected_profile,
                selected_root_family=None,
                label=f"{label} outer-result schedule",
            )
            _require(
                context["ordered_application_invocations"] == expected_invocations,
                f"{label} outer-result invocation schedule differs",
            )
            application_invocation_count = len(expected_invocations)
            charged_cross_rule_evaluation_count = 1
            direct_cross_expression_node_count = 3
        elif binding_kind in {
            "ROOT_ANY_NONCHECKPOINT_OBSERVATION",
            "ROOT_EXACT_CHECKPOINT_OBSERVATION",
        }:
            _require(
                context_kind == "ROOT_APPLICATION"
                and expected_constraint_scope == "FROZEN_ROOT_APPLICATION"
                and expected_profile is not None
                and context["constraint_scope_profile_id"] == expected_profile_id,
                f"{label} root context/profile differs",
            )
            families = expected_profile["ordered_admissible_root_families"]
            family_position = _require_integer(
                context["selected_root_family_position"],
                label=f"{label} selected root-family position",
                minimum=1,
                maximum=len(families),
            )
            family = families[family_position - 1]
            observation_count = family["observation_count"]
            measured_ordinal = _require_integer(
                context["measured_sequence_ordinal"],
                label=f"{label} measured observation ordinal",
                maximum=observation_count - 1,
            )
            expected_ordinal = expected_measurement_binding["sequence_ordinal"]
            if binding_kind == "ROOT_EXACT_CHECKPOINT_OBSERVATION":
                _require(
                    measured_ordinal == expected_ordinal,
                    f"{label} measured checkpoint ordinal differs",
                )
            else:
                _require(
                    expected_ordinal is None, f"{label} noncheckpoint ordinal differs"
                )
            root = resolve(
                context["root_record_reference"],
                kind="CONTEXT_OBJECT",
                record_type_name="TargetObservationRootV2",
                reference_label=f"{label} root reference",
            )
            target_registry = resolve(
                context["target_field_registry_authority_reference"],
                kind="V3_INVENTORY_POINTER",
                record_type_name="TargetFieldRegistryV1",
                inventory_pointer="/target_field_registry",
                reference_label=f"{label} target-field registry reference",
            )
            resolve(
                context["marker_contract_authority_reference"],
                kind="V3_INVENTORY_POINTER",
                record_type_name="MarkerContractV1",
                inventory_pointer="/marker_contract",
                reference_label=f"{label} marker-contract reference",
            )
            selector_present = family["selector_present"]
            if selector_present:
                selector_pointer = (
                    f"/checkpoint_selector_catalog/"
                    f"{family['selector_catalog_position'] - 1}/selector"
                )
                selector = resolve(
                    context["selector_authority_reference"],
                    kind="V3_INVENTORY_POINTER",
                    record_type_name="CheckpointSelectorV1",
                    inventory_pointer=selector_pointer,
                    reference_label=f"{label} selector authority reference",
                )
                expected_selector_id = selector.validated_record.record_identity
            else:
                _require(
                    context["selector_authority_reference"] is None,
                    f"{label} selector-free context retains a selector",
                )
                expected_selector_id = None
            root_record = root.validated_record.record
            _require(
                root_record["observation_count"] == observation_count
                and len(root_record["ordered_observation_ids"]) == observation_count
                and root_record["full_checkpoint_selector_id"] == expected_selector_id
                and root_record["target_field_registry_id"]
                == target_registry.validated_record.record_identity
                and root_record["operation_kind"] == expected_profile["operation_kind"],
                f"{label} root/profile authority binding differs",
            )
            pair = [
                root_record["instrumentation_mode"],
                "NULL" if root_record["attempt_id"] is None else "NON_NULL",
            ]
            _require(
                pair in family["ordered_instrumentation_mode_attempt_presence_pairs"],
                f"{label} root mode/attempt family differs",
            )
            observation_references = _require_array(
                context["ordered_observation_record_references"],
                label=f"{label} observation references",
                exact_length=observation_count,
            )
            witness_reference_count = 0
            observation_ids: list[str] = []
            for ordinal, reference_value in enumerate(observation_references):
                expected_kind = (
                    "WITNESS_RECORD"
                    if ordinal == measured_ordinal
                    else "CONTEXT_OBJECT"
                )
                resolved = resolve(
                    reference_value,
                    kind=expected_kind,
                    record_type_name="TargetObservationV2",
                    reference_label=f"{label} observation reference {ordinal}",
                )
                witness_reference_count += expected_kind == "WITNESS_RECORD"
                observation_ids.append(resolved.validated_record.record_identity)
            _require(
                witness_reference_count == 1
                and observation_ids == root_record["ordered_observation_ids"],
                f"{label} root observation-reference closure differs",
            )
            expected_invocations = _derive_profile_application_invocations(
                expected_profile,
                selected_root_family=family,
                label=f"{label} root schedule",
            )
            _require(
                context["ordered_application_invocations"] == expected_invocations,
                f"{label} root invocation schedule differs",
            )
            application_invocation_count = len(expected_invocations)
            charged_cross_rule_evaluation_count = 187 * observation_count + (
                2 if selector_present else 1
            )
            direct_cross_expression_node_count = 1_872 * observation_count + (
                7 if selector_present else 4
            )
        else:
            raise MaximumProtocolValidationError(
                f"{label} measurement binding has no closed context variant"
            )
    expected_context_ids = frozenset(
        entry.maximum_context_object_id for entry in manifest.resolved_entries
    )
    resolved_id_set = frozenset(resolved_context_ids)
    _require(
        resolved_id_set == expected_context_ids,
        f"{label} context manifest is not the exact referenced-object closure",
    )
    context_object_octet_lengths = [
        entry.validated_record.record_canonical_byte_length
        for entry in manifest.resolved_entries
    ]
    resolved_context_object_octets = _require_integer(
        sum(context_object_octet_lengths),
        label=f"{label} resolved context-object octets",
    )
    return ValidatedPilotLeaf(
        context_manifest=manifest,
        witness_record=witness,
        scope_witness_context=context,
        resolved_context_reference_count=context_reference_count,
        resolved_context_object_ids=resolved_id_set,
        resolved_context_object_octets=resolved_context_object_octets,
        maximum_context_object_octets=(
            max(context_object_octet_lengths) if context_object_octet_lengths else 0
        ),
        observation_count=observation_count,
        application_invocation_count=application_invocation_count,
        charged_cross_rule_evaluation_count=(charged_cross_rule_evaluation_count),
        direct_cross_expression_node_count=direct_cross_expression_node_count,
    )


def _validate_materialized_max64_context_authority(
    value: Any,
    *,
    label: str,
) -> dict[str, Any]:
    authority = _require_exact_keys(
        value,
        MAX64_CONTEXT_AUTHORITY_ROOT_KEYS,
        label=label,
    )
    observations = _require_array(
        authority["observations"],
        label=f"{label} observations",
        exact_length=67,
    )
    _require(
        all(type(observation) is dict for observation in observations)
        and type(authority["root"]) is dict
        and type(authority["selector"]) is dict,
        f"{label} materialized record roots differ",
    )
    compact = _canonical_bytes(authority)
    _require(
        len(compact) == MAX64_CONTEXT_AUTHORITY_COMPACT_OCTETS
        and _sha256(compact) == MAX64_CONTEXT_AUTHORITY_COMPACT_SHA256,
        f"{label} compact authority identity differs",
    )
    return authority


def _validate_protocol_rebind_patches(
    value: Any,
    *,
    candidate_protocol_raw: bytes,
    final_protocol_raw: bytes,
    label: str,
) -> list[dict[str, Any]]:
    patches = _require_array(value, label=label, exact_length=23)
    previous_end = 0
    rebuilt = bytearray()
    for position, patch_value in enumerate(patches, 1):
        patch = _require_exact_keys(
            patch_value,
            PROTOCOL_REBIND_PATCH_KEYS,
            label=f"{label} item {position}",
        )
        _require(
            patch["patch_position"] == position
            and patch["patch_kind"]
            == ("STATUS_LINE" if position == 1 else "ACCEPTED_CEILING_CELL"),
            f"{label} position/kind differs",
        )
        start = _require_integer(
            patch["candidate_start_octet"],
            label=f"{label} start {position}",
            maximum=len(candidate_protocol_raw),
        )
        end = _require_integer(
            patch["candidate_end_octet_exclusive"],
            label=f"{label} end {position}",
            minimum=1,
            maximum=len(candidate_protocol_raw),
        )
        _require(
            previous_end <= start < end,
            f"{label} spans overlap or are empty",
        )
        candidate_hex = patch["candidate_bytes_hex"]
        final_hex = patch["final_bytes_hex"]
        for name, encoded in (
            ("candidate", candidate_hex),
            ("final", final_hex),
        ):
            _require(
                type(encoded) is str
                and bool(encoded)
                and len(encoded) % 2 == 0
                and re.fullmatch(r"[0-9a-f]+", encoded) is not None,
                f"{label} {name} bytes {position} differ",
            )
        candidate_bytes = bytes.fromhex(candidate_hex)
        replacement = bytes.fromhex(final_hex)
        _require(
            candidate_bytes == candidate_protocol_raw[start:end],
            f"{label} candidate span bytes {position} differ",
        )
        rebuilt.extend(candidate_protocol_raw[previous_end:start])
        rebuilt.extend(replacement)
        previous_end = end
    rebuilt.extend(candidate_protocol_raw[previous_end:])
    _require(bytes(rebuilt) == final_protocol_raw, f"{label} rebind output differs")
    return patches


def _validate_acceptance_authority_shape(
    value: Any,
    *,
    candidate_protocol_raw: bytes,
    final_protocol_raw: bytes,
    label: str,
) -> dict[str, Any]:
    authority = _require_exact_keys(value, ACCEPTANCE_AUTHORITY_KEYS, label=label)
    _require(
        authority["artifact_version"]
        == (
            "riskyieldmm.raw_v8_step2_external_schema_v2.maximum_protocol_acceptance.v1"
        )
        and authority["acceptance_decision"] == "GO",
        f"{label} version/decision differs",
    )
    for prefix, raw in (
        ("candidate_protocol", candidate_protocol_raw),
        ("final_protocol", final_protocol_raw),
    ):
        _require(
            authority[f"{prefix}_raw_octet_count"] == len(raw)
            and authority[f"{prefix}_sha256"] == _sha256(raw),
            f"{label} {prefix} physical identity differs",
        )
    for prefix in (
        "seed_pilot",
        "final_pilot",
        "independent_validator",
        "focused_test",
    ):
        _require_integer(
            authority[f"{prefix}_raw_octet_count"],
            label=f"{label} {prefix} octet count",
            minimum=1,
        )
        _require_sha256(
            authority[f"{prefix}_raw_sha256"],
            label=f"{label} {prefix} SHA",
        )
    _validate_protocol_rebind_patches(
        authority["ordered_protocol_rebind_patch_records"],
        candidate_protocol_raw=candidate_protocol_raw,
        final_protocol_raw=final_protocol_raw,
        label=f"{label} rebind patches",
    )
    payload = {
        name: item
        for name, item in authority.items()
        if name != "maximum_protocol_acceptance_id"
    }
    _require(
        authority["maximum_protocol_acceptance_id"]
        == _semantic_id(ACCEPTANCE_AUTHORITY_DOMAIN, payload),
        f"{label} semantic identity differs",
    )
    return authority


def _validate_materialized_frontier(
    value: Any,
    *,
    dimensions: list[dict[str, Any]],
    state_signature_id: str,
    label: str,
    resource_meter: ProofResourceMeter | None = None,
) -> tuple[dict[str, Any], dict[str, int | str | None]]:
    meter = (
        resource_meter
        if resource_meter is not None
        else ProofResourceMeter(phase=SEED_CAP_DERIVATION_PHASE)
    )
    output = _require_exact_keys(value, MATERIALIZED_FRONTIER_KEYS, label=label)
    _require(
        output["frontier_soundness"] in {"EXACT_ATTAINABLE", "SAFE_UPPER_DOMAIN"},
        f"{label} soundness differs",
    )
    _require(
        output["state_signature_id"] == state_signature_id, f"{label} signature differs"
    )
    expected_descriptor_ids = [item["observable_descriptor_id"] for item in dimensions]
    _require(
        output["ordered_observable_descriptor_ids"] == expected_descriptor_ids,
        f"{label} observable descriptors differ",
    )
    state_frontiers = _require_array(
        output["ordered_state_frontiers"],
        label=f"{label} state frontiers",
        maximum_length=1_000_000,
    )
    meter.add("frontier_state_entry_count", len(state_frontiers))
    previous_state_sort: bytes | None = None
    bitmap_run_count = 0
    normalized_frontiers: list[dict[str, Any]] = []
    for state_position, state_value in enumerate(state_frontiers, 1):
        state = _require_exact_keys(
            state_value,
            STATE_FRONTIER_KEYS,
            label=f"{label} state {state_position}",
        )
        state_key = _require_array(
            state["state_key"],
            label=f"{label} state key {state_position}",
            exact_length=len(dimensions),
        )
        for ordinal, (cell_value, dimension) in enumerate(
            zip(state_key, dimensions, strict=True), 1
        ):
            cell = _validate_state_cell(
                cell_value,
                label=f"{label} cell {state_position}:{ordinal}",
                resource_meter=meter,
            )
            _validate_cell_for_dimension(
                cell,
                dimension,
                label=f"{label} cell {state_position}:{ordinal}",
            )
        state_sort = _canonical_bytes(state_key)
        if previous_state_sort is not None:
            _require(previous_state_sort < state_sort, f"{label} state order differs")
        previous_state_sort = state_sort
        runs = _validate_bitmap_runs(
            state["ordered_length_bitmap_runs"],
            label=f"{label} runs {state_position}",
            require_nonempty=True,
        )
        meter.add("frontier_bitmap_run_count", len(runs))
        bitmap_run_count += len(runs)
        normalized_frontiers.append(
            {
                "state_key": state_key,
                "ordered_length_bitmap_runs": runs,
            }
        )
    expanded_digest, point_count, minimum, maximum, expanded_octets = (
        _stream_expanded_frontier_digest_metered(
            normalized_frontiers,
            meter=meter,
        )
    )
    nonempty = point_count != 0
    bitmap_octets = _canonical_octet_length(normalized_frontiers)
    bitmap_increments = {"frontier_canonicalized_octets": bitmap_octets}
    if nonempty:
        bitmap_increments["hash_preimage_octets"] = bitmap_octets
    meter.reserve(bitmap_increments)
    bitmap_digest = _canonical_sha256_stream(normalized_frontiers) if nonempty else None
    return output, {
        "state_entry_count": len(normalized_frontiers),
        "bitmap_run_count": bitmap_run_count,
        "expanded_attainable_point_count": point_count,
        "minimum_attainable_octets": minimum,
        "maximum_attainable_octets": maximum,
        "expanded_frontier_sha256": expanded_digest,
        "canonical_bitmap_run_frontier_sha256": bitmap_digest,
        "frontier_canonicalized_octets": expanded_octets + bitmap_octets,
    }


def _required_output_alias_child_position(
    *,
    node_kind: str,
    derivation: dict[str, Any],
) -> int | None:
    """Return the only legal alias child, or ``None`` when materialization is required."""

    if (
        node_kind == "LEXICOGRAPHIC_PREFIX_EXCLUSION"
        and derivation["coordinate_activation"] == "INACTIVE"
    ):
        return int(derivation["input_prefix_frontier_child_position"])
    if node_kind == "CODEC_INTERSECTION_ATTAINMENT":
        return int(derivation["winner_frontier_child_position"])
    return None


def _validate_output_frontier(
    value: Any,
    *,
    dimensions: list[dict[str, Any]],
    state_signature_id: str,
    node_kind: str,
    derivation: dict[str, Any],
    node_position: int,
    child_positions: list[int],
    child_ids: list[str],
    prior_frontier_resolutions: list[dict[str, Any]],
    proof_depth: int,
    label: str,
    resource_meter: ProofResourceMeter | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Validate the mandatory tagged output and return its resolved frontier handle."""

    meter = (
        resource_meter
        if resource_meter is not None
        else ProofResourceMeter(phase=SEED_CAP_DERIVATION_PHASE)
    )
    output = _require_exact_keys(value, OUTPUT_FRONTIER_KEYS, label=label)
    encoding_kind = output["frontier_encoding_kind"]
    _require(
        encoding_kind in {"MATERIALIZED", "DIRECT_CHILD_ALIAS"},
        f"{label} encoding kind differs",
    )
    required_alias_child = _required_output_alias_child_position(
        node_kind=node_kind,
        derivation=derivation,
    )
    _require(
        (encoding_kind == "DIRECT_CHILD_ALIAS") == (required_alias_child is not None),
        f"{label} materialized/alias eligibility differs",
    )

    if encoding_kind == "MATERIALIZED":
        _require(
            type(output["materialized_frontier"]) is dict
            and output["direct_child_alias"] is None,
            f"{label} materialized/alias nullability differs",
        )
        materialized, evidence = _validate_materialized_frontier(
            output["materialized_frontier"],
            dimensions=dimensions,
            state_signature_id=state_signature_id,
            label=f"{label} materialized frontier",
            resource_meter=meter,
        )
        return output, {
            "frontier_encoding_kind": encoding_kind,
            "resolved_materialized_frontier": materialized,
            "resolved_materialized_origin_position": node_position,
            "alias_depth": 0,
            "frontier_evidence": evidence,
        }

    meter.add("frontier_transition_count", 1)
    _require(
        output["materialized_frontier"] is None
        and type(output["direct_child_alias"]) is dict,
        f"{label} materialized/alias nullability differs",
    )
    alias = _require_exact_keys(
        output["direct_child_alias"],
        DIRECT_CHILD_ALIAS_KEYS,
        label=f"{label} direct-child alias",
    )
    aliased_child_position = _require_integer(
        alias["aliased_child_position"],
        label=f"{label} aliased child position",
        minimum=1,
        maximum=node_position - 1,
    )
    _require(
        aliased_child_position == required_alias_child
        and aliased_child_position in child_positions,
        f"{label} alias does not name the required direct child",
    )
    child_ordinal = child_positions.index(aliased_child_position)
    aliased_child_id = _require_sha256(
        alias["aliased_child_proof_node_id"],
        label=f"{label} aliased child proof-node ID",
    )
    _require(
        aliased_child_id == child_ids[child_ordinal],
        f"{label} aliased child identity differs",
    )
    child_resolution = prior_frontier_resolutions[aliased_child_position - 1]
    expected_origin = int(child_resolution["resolved_materialized_origin_position"])
    origin_position = _require_integer(
        alias["resolved_materialized_origin_position"],
        label=f"{label} resolved materialized origin",
        minimum=1,
        maximum=node_position - 1,
    )
    _require(
        origin_position == expected_origin,
        f"{label} resolved materialized origin differs from its child",
    )
    origin_resolution = prior_frontier_resolutions[origin_position - 1]
    _require(
        origin_resolution["frontier_encoding_kind"] == "MATERIALIZED"
        and origin_resolution["resolved_materialized_origin_position"]
        == origin_position,
        f"{label} resolved origin is not materialized",
    )
    resolved_frontier = child_resolution["resolved_materialized_frontier"]
    expected_descriptor_ids = [item["observable_descriptor_id"] for item in dimensions]
    _require(
        resolved_frontier["state_signature_id"] == state_signature_id
        and resolved_frontier["ordered_observable_descriptor_ids"]
        == expected_descriptor_ids,
        f"{label} resolved frontier signature/descriptors differ",
    )
    alias_depth = int(child_resolution["alias_depth"]) + 1
    _require(
        alias_depth <= proof_depth and alias_depth <= node_position,
        f"{label} alias depth exceeds the proof bounds",
    )
    return output, {
        "frontier_encoding_kind": encoding_kind,
        "resolved_materialized_frontier": resolved_frontier,
        "resolved_materialized_origin_position": origin_position,
        "alias_depth": alias_depth,
        "frontier_evidence": child_resolution["frontier_evidence"],
    }


def _validate_frontier_commitment(
    value: Any,
    *,
    state_signature_id: str,
    frontier_evidence: dict[str, int | str | None],
    label: str,
    resource_meter: ProofResourceMeter | None = None,
) -> dict[str, Any]:
    commitment = _require_exact_keys(value, FRONTIER_COMMITMENT_KEYS, label=label)
    _require(
        commitment["frontier_version"]
        == "riskyieldmm.raw_v8_step2_external_schema_v2.attainable_frontier.v1",
        f"{label} version differs",
    )
    _require(
        commitment["state_signature_id"] == state_signature_id,
        f"{label} signature differs",
    )
    for name in (
        "state_entry_count",
        "bitmap_run_count",
        "expanded_attainable_point_count",
        "minimum_attainable_octets",
        "maximum_attainable_octets",
        "expanded_frontier_sha256",
        "canonical_bitmap_run_frontier_sha256",
    ):
        _require(commitment[name] == frontier_evidence[name], f"{label} {name} differs")
    nonempty = frontier_evidence["expanded_attainable_point_count"] != 0
    for name in (
        "least_measured_choice_vector_sha256_at_maximum",
        "least_context_choice_vector_sha256_at_maximum",
    ):
        _require(
            (nonempty and (commitment[name] is None or _is_sha256(commitment[name])))
            or (not nonempty and commitment[name] is None),
            f"{label} winner digest nullability differs",
        )
    payload = {
        name: item
        for name, item in commitment.items()
        if name != "frontier_commitment_id"
    }
    _require(
        _semantic_id(
            FRONTIER_COMMITMENT_DOMAIN,
            payload,
            resource_meter=resource_meter,
        )
        == commitment["frontier_commitment_id"],
        f"{label} identity differs",
    )
    return commitment


def _validate_alias_frontier_commitment(
    commitment: dict[str, Any],
    *,
    aliased_child_commitment: dict[str, Any],
    node_kind: str,
    derivation: dict[str, Any],
    label: str,
) -> None:
    """Validate commitment reuse without rehashing an aliased frontier."""

    # TODO(P0): Derive the current prefix scope's winner digest from the
    # verifier-owned coordinate-plan catalog and complete active prefix.  That
    # independent plan resolver is not present in this fail-closed candidate
    # validator, so this alias-only layer checks only child-preserved fields.
    if node_kind == "CODEC_INTERSECTION_ATTAINMENT":
        _require(
            commitment == aliased_child_commitment,
            f"{label} codec alias does not preserve the winner commitment",
        )
        return

    for name in (
        "state_signature_id",
        "state_entry_count",
        "bitmap_run_count",
        "expanded_attainable_point_count",
        "minimum_attainable_octets",
        "maximum_attainable_octets",
        "expanded_frontier_sha256",
        "canonical_bitmap_run_frontier_sha256",
    ):
        _require(
            commitment[name] == aliased_child_commitment[name],
            f"{label} aliased semantic commitment field {name} differs",
        )
    unchanged_choice_digest = (
        "least_context_choice_vector_sha256_at_maximum"
        if derivation["choice_scope"] == "MEASURED_RECORD"
        else "least_measured_choice_vector_sha256_at_maximum"
    )
    _require(
        commitment[unchanged_choice_digest]
        == aliased_child_commitment[unchanged_choice_digest],
        f"{label} alias changes the other choice scope digest",
    )


def _require_optional_sha256(value: Any, *, label: str) -> str | None:
    if value is None:
        return None
    return _require_sha256(value, label=label)


def _require_optional_text(value: Any, *, label: str) -> str | None:
    _require(
        value is None or (type(value) is str and bool(value)),
        f"{label} must be null or nonempty text",
    )
    return value


def _require_sha256_array(value: Any, *, label: str) -> list[str]:
    items = _require_array(value, label=label, maximum_length=1_000_000)
    for position, item in enumerate(items, 1):
        _require_sha256(item, label=f"{label} item {position}")
    _require(len(set(items)) == len(items), f"{label} contains duplicates")
    return items


def _require_text_id_array(value: Any, *, label: str) -> list[str]:
    items = _require_array(value, label=label, maximum_length=1_000_000)
    _require(
        all(type(item) is str and bool(item) for item in items),
        f"{label} must contain nonempty text identities",
    )
    _require(len(set(items)) == len(items), f"{label} contains duplicates")
    return items


def _validate_application_invocation(value: Any, *, label: str) -> dict[str, Any]:
    invocation = _require_exact_keys(value, APPLICATION_INVOCATION_KEYS, label=label)
    _require(
        type(invocation["application_name"]) is str
        and bool(invocation["application_name"]),
        f"{label} application name differs",
    )
    _require_integer(
        invocation["application_invocation_ordinal"],
        label=f"{label} application invocation ordinal",
    )
    bound_ordinal = invocation["bound_observation_ordinal"]
    _require(
        bound_ordinal is None or type(bound_ordinal) is int,
        f"{label} bound observation ordinal differs",
    )
    if bound_ordinal is not None:
        _require_integer(
            bound_ordinal,
            label=f"{label} bound observation ordinal",
        )
    return invocation


def _validate_applicable_scope_case_positions(
    value: Any,
    *,
    application_present: bool,
    label: str,
) -> list[int]:
    positions = _require_array(value, label=label, maximum_length=1_000_000)
    previous = 0
    for ordinal, position in enumerate(positions, 1):
        _require_integer(
            position,
            label=f"{label} item {ordinal}",
            minimum=1,
        )
        _require(position > previous, f"{label} is not strictly increasing")
        previous = position
    _require(
        bool(positions) == application_present,
        f"{label} null/application cardinality differs",
    )
    return positions


def _validate_exact_constraint_bindings(
    value: Any, *, label: str
) -> list[dict[str, Any]]:
    values = _require_array(value, label=label, maximum_length=1_000_000)
    bindings: list[dict[str, Any]] = []
    seen: set[bytes] = set()
    for position, binding_value in enumerate(values, 1):
        binding = _require_exact_keys(
            binding_value,
            EXACT_CONSTRAINT_BINDING_KEYS,
            label=f"{label} item {position}",
        )
        _require(
            type(binding["constraint_id"]) is str and bool(binding["constraint_id"]),
            f"{label} constraint identity differs",
        )
        invocation_value = binding["application_invocation"]
        application_present = invocation_value is not None
        if application_present:
            _validate_application_invocation(
                invocation_value,
                label=f"{label} application invocation {position}",
            )
        _validate_applicable_scope_case_positions(
            binding["ordered_applicable_scope_case_positions"],
            application_present=application_present,
            label=f"{label} applicable cases {position}",
        )
        canonical = _canonical_bytes(binding)
        _require(canonical not in seen, f"{label} contains a duplicate binding")
        seen.add(canonical)
        bindings.append(binding)
    return bindings


def _validate_scope_cases(value: Any, *, label: str) -> list[dict[str, Any]]:
    cases = _require_array(value, label=label, maximum_length=1_000_000)
    for position, case_value in enumerate(cases, 1):
        case = _require_exact_keys(
            case_value,
            SCOPE_CASE_KEYS,
            label=f"{label} item {position}",
        )
        _require(
            case["scope_case_position"] == position,
            f"{label} positions differ",
        )
        for name in (
            "root_family_position",
            "mode_attempt_pair_position",
            "observation_role_position",
            "measured_sequence_ordinal",
        ):
            item = case[name]
            _require(
                item is None or type(item) is int,
                f"{label} {name} has the wrong scalar kind",
            )
            if item is not None:
                _require_integer(
                    item,
                    label=f"{label} {name}",
                    minimum=0 if name == "measured_sequence_ordinal" else 1,
                )
        _require_integer(
            case["scope_case_child_position"],
            label=f"{label} scope-case child {position}",
            minimum=1,
        )
        invocations = _require_array(
            case["ordered_application_invocations"],
            label=f"{label} application invocations {position}",
            maximum_length=1_000_000,
        )
        previous_invocation: tuple[str, int] | None = None
        for invocation_position, invocation_value in enumerate(invocations, 1):
            invocation = _validate_application_invocation(
                invocation_value,
                label=(
                    f"{label} application invocation {position}:{invocation_position}"
                ),
            )
            name = invocation["application_name"]
            ordinal = invocation["application_invocation_ordinal"]
            invocation_key = (name, ordinal)
            _require(
                previous_invocation is None or previous_invocation < invocation_key,
                f"{label} application invocation order differs",
            )
            previous_invocation = invocation_key
    return cases


def _validate_derivation(
    value: Any,
    *,
    node_kind: str,
    child_positions: list[int],
    node_position: int,
    label: str,
    resource_meter: ProofResourceMeter | None = None,
    validated_inventory: dict[str, Any] | None = None,
    validated_registry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    derivation = _require_exact_keys(value, DERIVATION_KEYS[node_kind], label=label)
    _require(
        derivation["derivation_kind"] == node_kind,
        f"{label} kind differs from its proof node",
    )
    # TODO(P0): Thread the protocol SHA and verifier-derived safe-node
    # invocation set into this callsite, then validate every embedded
    # recurrence root and the exact TEXT/maximum-slice/prefix root ordering.
    # The bounded schema layer below enforces only member shape/nullability.
    expected_children: list[int] | None = None
    if node_kind == "FIXED_VALUE":
        source_kind = derivation["fixed_source_kind"]
        _require(
            source_kind in {"SCHEMA_LITERAL", "FROZEN_AUTHORITY", "DERIVED_IDENTITY"},
            f"{label} fixed source kind differs",
        )
        _validate_proof_subject_locator(
            derivation["fixed_source_locator"],
            label=f"{label} fixed source locator",
            resource_meter=resource_meter,
        )
        fixed_length = _require_integer(
            derivation["fixed_canonical_byte_length"],
            label=f"{label} fixed canonical byte length",
        )
        transfer_kind = derivation["fixed_transfer_kind"]
        _require(
            transfer_kind
            in {
                "EXACT_FIXED_VALUE",
                "EXACT_DERIVED_IDENTITY_MAPPING",
                "DERIVED_IDENTITY_FIXED_WIDTH_SAFE_UPPER_DOMAIN",
            },
            f"{label} fixed transfer kind differs",
        )
        payload_children = _require_array(
            derivation["ordered_identity_payload_child_positions"],
            label=f"{label} identity-payload children",
            maximum_length=1_000_000,
        )
        for position, child in enumerate(payload_children, 1):
            _require_integer(
                child,
                label=f"{label} identity-payload child {position}",
                minimum=1,
                maximum=node_position - 1,
            )
        _require(
            len(set(payload_children)) == len(payload_children),
            f"{label} repeats an identity-payload child",
        )
        if source_kind == "DERIVED_IDENTITY":
            _require(
                transfer_kind
                in {
                    "EXACT_DERIVED_IDENTITY_MAPPING",
                    "DERIVED_IDENTITY_FIXED_WIDTH_SAFE_UPPER_DOMAIN",
                }
                and fixed_length == 66
                and derivation["fixed_canonical_sha256"] is None
                and bool(payload_children),
                f"{label} derived-identity transfer differs",
            )
            if transfer_kind == "EXACT_DERIVED_IDENTITY_MAPPING":
                _require_sha256(
                    derivation["derived_identity_mapping_catalog_id"],
                    label=f"{label} derived-identity mapping catalog ID",
                )
            else:
                _require(
                    derivation["derived_identity_mapping_catalog_id"] is None,
                    f"{label} safe identity mapping catalog must be null",
                )
            expected_children = payload_children
        else:
            _require(
                transfer_kind == "EXACT_FIXED_VALUE"
                and not payload_children
                and derivation["derived_identity_mapping_catalog_id"] is None,
                f"{label} literal/authority fixed transfer differs",
            )
            _require_sha256(
                derivation["fixed_canonical_sha256"],
                label=f"{label} fixed canonical SHA",
            )
            expected_children = []
    elif node_kind == "BOOLEAN_VALUE_FRONTIER":
        values = _require_array(
            derivation["ordered_boolean_values"],
            label=f"{label} Boolean values",
        )
        _require(
            values in ([False], [True], [False, True]),
            f"{label} Boolean values are not in typed choice order",
        )
        expected_children = []
    elif node_kind == "SAFE_UINT_DIGIT_FRONTIER":
        minimum = _require_integer(
            derivation["integer_minimum"], label=f"{label} integer minimum"
        )
        maximum = _require_integer(
            derivation["integer_maximum"], label=f"{label} integer maximum"
        )
        _require(minimum <= maximum, f"{label} integer domain is empty")
        bands = _require_array(
            derivation["ordered_decimal_digit_bands"],
            label=f"{label} decimal digit bands",
            maximum_length=16,
        )
        _require(bool(bands), f"{label} decimal digit bands are empty")
        next_minimum = minimum
        for position, band_value in enumerate(bands, 1):
            band = _require_exact_keys(
                band_value,
                DECIMAL_DIGIT_BAND_KEYS,
                label=f"{label} decimal band {position}",
            )
            digit_count = _require_integer(
                band["digit_count"],
                label=f"{label} decimal band digit count",
                minimum=1,
            )
            band_minimum = _require_integer(
                band["inclusive_minimum"],
                label=f"{label} decimal band minimum",
            )
            band_maximum = _require_integer(
                band["inclusive_maximum"],
                label=f"{label} decimal band maximum",
            )
            _require(
                band_minimum == next_minimum
                and band_minimum <= band_maximum
                and len(str(band_minimum)) == digit_count
                and len(str(band_maximum)) == digit_count,
                f"{label} decimal band partition differs",
            )
            next_minimum = band_maximum + 1
        _require(
            next_minimum == maximum + 1,
            f"{label} decimal bands do not cover the domain",
        )
        expected_children = []
    elif node_kind == "TEXT_LANGUAGE_FRONTIER":
        _require_sha256(
            derivation["text_language_id"], label=f"{label} text-language ID"
        )
        _require(
            type(derivation["language_kind"]) is str
            and bool(derivation["language_kind"]),
            f"{label} language kind differs",
        )
        _require(
            derivation["text_solver_kind"]
            in {
                "FINITE_LITERAL_ENUMERATION",
                "BUILTIN_CLOSED_FORM",
                "ASCII_DFA_DYNAMIC_PROGRAM",
                "UNICODE_15_NFC_DYNAMIC_PROGRAM",
            },
            f"{label} text solver kind differs",
        )
        unicode_version = derivation["unicode_version"]
        _require(
            unicode_version is None or unicode_version == "15.0.0",
            f"{label} Unicode version differs",
        )
        _require(
            (derivation["text_solver_kind"] == "UNICODE_15_NFC_DYNAMIC_PROGRAM")
            == (unicode_version == "15.0.0"),
            f"{label} Unicode-version nullability differs",
        )
        expected_recurrence_kind = {
            "FINITE_LITERAL_ENUMERATION": None,
            "BUILTIN_CLOSED_FORM": None,
            "ASCII_DFA_DYNAMIC_PROGRAM": "ASCII_DFA_DYNAMIC_PROGRAM_V1",
            "UNICODE_15_NFC_DYNAMIC_PROGRAM": ("UNICODE_15_NFC_DYNAMIC_PROGRAM_V1"),
        }[derivation["text_solver_kind"]]
        recurrence_catalog = derivation["transient_recurrence_catalog"]
        _require(
            (expected_recurrence_kind is None and recurrence_catalog is None)
            or (
                expected_recurrence_kind is not None
                and type(recurrence_catalog) is dict
                and recurrence_catalog.get("recurrence_kind")
                == expected_recurrence_kind
            ),
            f"{label} transient recurrence nullability/kind differs",
        )
        expected_children = []
    elif node_kind == "NULLABLE_CASE_FRONTIER":
        _require(
            type(derivation["null_branch_enabled"]) is bool,
            f"{label} nullable switch differs",
        )
        child = _require_integer(
            derivation["non_null_child_position"],
            label=f"{label} non-null child",
            minimum=1,
            maximum=node_position - 1,
        )
        expected_children = [child]
    elif node_kind == "ARRAY_FRONTIER":
        minimum = _require_integer(
            derivation["array_minimum_items"],
            label=f"{label} array minimum",
        )
        maximum = _require_integer(
            derivation["array_maximum_items"],
            label=f"{label} array maximum",
        )
        _require(minimum <= maximum, f"{label} array domain is empty")
        child = _require_integer(
            derivation["item_child_position"],
            label=f"{label} item child",
            minimum=1,
            maximum=node_position - 1,
        )
        _require(
            derivation["array_semantics"]
            in {
                "INDEPENDENT_REPEAT",
                "POSITIONAL",
                "ORDERED_UNIQUE",
                "CARDINALITY_COUPLED",
            },
            f"{label} array semantics differ",
        )
        transfer_kind = derivation["array_transfer_kind"]
        _require(
            transfer_kind
            in {"EXACT_ARRAY_FRONTIER", "ORDERED_LANGUAGE_SAFE_UPPER_DOMAIN"},
            f"{label} array transfer differs",
        )
        _require(
            transfer_kind == "EXACT_ARRAY_FRONTIER"
            or derivation["array_semantics"] == "ORDERED_UNIQUE",
            f"{label} safe array transfer is not ordered-unique",
        )
        expected_children = [child]
    elif node_kind == "RECORD_FRONTIER":
        _require(
            type(derivation["record_type_name"]) is str
            and bool(derivation["record_type_name"]),
            f"{label} record type differs",
        )
        members = _require_array(
            derivation["ordered_member_child_positions"],
            label=f"{label} member children",
            maximum_length=1_000_000,
        )
        for position, child in enumerate(members, 1):
            _require_integer(
                child,
                label=f"{label} member child {position}",
                minimum=1,
                maximum=node_position - 1,
            )
        _require_optional_text(
            derivation["derived_identity_member_name"],
            label=f"{label} derived identity member",
        )
        expected_children = members
    elif node_kind == "TAGGED_UNION_FRONTIER":
        _require(
            type(derivation["union_type_name"]) is str
            and bool(derivation["union_type_name"]),
            f"{label} union type differs",
        )
        alternatives = _require_array(
            derivation["ordered_alternative_child_positions"],
            label=f"{label} alternative children",
            maximum_length=1_000_000,
        )
        names = _require_array(
            derivation["ordered_alternative_names"],
            label=f"{label} alternative names",
            exact_length=len(alternatives),
        )
        _require(
            all(type(name) is str and bool(name) for name in names)
            and len(set(names)) == len(names),
            f"{label} alternative names differ",
        )
        for position, child in enumerate(alternatives, 1):
            _require_integer(
                child,
                label=f"{label} alternative child {position}",
                minimum=1,
                maximum=node_position - 1,
            )
        _require(
            type(derivation["owner_constraint_present"]) is bool,
            f"{label} owner-constraint switch differs",
        )
        expected_children = alternatives
    elif node_kind == "CONSTRAINT_FRONTIER":
        source_kind = derivation["constraint_source_kind"]
        _require(
            source_kind in {"INTRINSIC_RULE", "CROSS_RECORD_APPLICATION"},
            f"{label} constraint source differs",
        )
        constraint_ids = _require_text_id_array(
            derivation["ordered_constraint_ids"],
            label=f"{label} constraint IDs",
        )
        _require(
            len(constraint_ids) == 1, f"{label} must contain one frozen constraint"
        )
        invocation_value = derivation["application_invocation"]
        application_present = source_kind == "CROSS_RECORD_APPLICATION"
        _require(
            (invocation_value is not None) == application_present,
            f"{label} application-invocation nullability differs",
        )
        if application_present:
            _validate_application_invocation(
                invocation_value,
                label=f"{label} application invocation",
            )
        _validate_applicable_scope_case_positions(
            derivation["ordered_applicable_scope_case_positions"],
            application_present=application_present,
            label=f"{label} applicable scope cases",
        )
        transfer = derivation["constraint_transfer_kind"]
        _require(
            transfer
            in {
                "FINITE_STATE_FILTER",
                "BOUNDED_LINEAR_FRONTIER",
                "EXACT_RULE_EVALUATION",
                "SAFE_UPPER_DOMAIN_RELAXATION",
            },
            f"{label} constraint transfer differs",
        )
        _require(
            derivation["relaxation_direction"]
            == (
                "LEGAL_DOMAIN_SUPERSET"
                if transfer == "SAFE_UPPER_DOMAIN_RELAXATION"
                else None
            ),
            f"{label} relaxation direction differs",
        )
        child = _require_integer(
            derivation["input_frontier_child_position"],
            label=f"{label} input frontier child",
            minimum=1,
            maximum=node_position - 1,
        )
        expected_children = [child]
    elif node_kind == "SCOPE_FRONTIER":
        _require(
            derivation["constraint_scope"]
            in {"INTRINSIC_TYPE", "FROZEN_ROOT_APPLICATION", "FROZEN_FIXTURE"},
            f"{label} constraint scope differs",
        )
        _require_sha256(
            derivation["constraint_scope_id"], label=f"{label} constraint-scope ID"
        )
        _require_optional_sha256(
            derivation["constraint_scope_profile_id"],
            label=f"{label} scope-profile ID",
        )
        _validate_measurement_binding(
            derivation["measurement_binding"], label=f"{label} measurement binding"
        )
        cases = _validate_scope_cases(
            derivation["ordered_scope_cases"], label=f"{label} scope cases"
        )
        _require(bool(cases), f"{label} scope cases are empty")
        _require(
            derivation["scope_transfer_kind"]
            in {
                "INTRINSIC_SELF",
                "OWNER_MEMBER",
                "OUTER_RESULT_APPLICATION",
                "ROOT_APPLICATION",
            },
            f"{label} scope transfer differs",
        )
        _require(
            child_positions == [case["scope_case_child_position"] for case in cases],
            f"{label} child/case positions differ",
        )
    elif node_kind == "MAXIMUM_SLICE_EXACT_FRONTIER":
        _require_integer(
            derivation["target_canonical_byte_length"],
            label=f"{label} target byte length",
        )
        _validate_exact_constraint_bindings(
            derivation["ordered_exact_constraint_bindings"],
            label=f"{label} exact constraint bindings",
        )
        reinstatements = _require_array(
            derivation["ordered_exact_domain_reinstatement_node_positions"],
            label=f"{label} exact-domain reinstatement positions",
            maximum_length=1_000_000,
        )
        previous_reinstatement = 0
        for position, reinstatement in enumerate(reinstatements, 1):
            _require_integer(
                reinstatement,
                label=f"{label} exact-domain reinstatement {position}",
                minimum=1,
                maximum=node_position - 1,
            )
            _require(
                reinstatement > previous_reinstatement,
                f"{label} exact-domain reinstatements are not strictly increasing",
            )
            previous_reinstatement = reinstatement
        _require_sha256_array(
            derivation["ordered_choice_coordinate_plan_ids"],
            label=f"{label} choice-coordinate plan IDs",
        )
        _require_array(
            derivation["ordered_transient_recurrence_catalogs"],
            label=f"{label} transient recurrence catalogs",
            maximum_length=1_000_000,
        )
        child = _require_integer(
            derivation["upper_frontier_child_position"],
            label=f"{label} upper frontier child",
            minimum=1,
            maximum=node_position - 1,
        )
        expected_children = [child]
    elif node_kind == "LEXICOGRAPHIC_PREFIX_EXCLUSION":
        _require_integer(
            derivation["target_canonical_byte_length"],
            label=f"{label} target byte length",
        )
        _require(
            derivation["choice_scope"] in {"MEASURED_RECORD", "CONSTRUCTED_CONTEXT"},
            f"{label} choice scope differs",
        )
        _require_sha256(
            derivation["choice_coordinate_plan_id"],
            label=f"{label} choice-coordinate plan ID",
        )
        activation = derivation["coordinate_activation"]
        _require(
            activation in {"ACTIVE", "INACTIVE"},
            f"{label} coordinate activation differs",
        )
        prefix_count = _require_integer(
            derivation["fixed_prefix_coordinate_count"],
            label=f"{label} fixed-prefix count",
            minimum=1,
        )
        active_prefix_count = _require_integer(
            derivation["fixed_active_prefix_coordinate_count"],
            label=f"{label} fixed active-prefix count",
        )
        _require(
            active_prefix_count <= prefix_count,
            f"{label} active-prefix count exceeds the plan prefix",
        )
        selected_atom_order = _validate_primitive_atom(
            derivation["selected_atom"], label=f"{label} selected atom"
        )
        _require(
            (selected_atom_order[0] == 0) == (activation == "INACTIVE"),
            f"{label} activation/selected atom differs",
        )
        recurrence_catalogs = _require_array(
            derivation["ordered_transient_recurrence_catalogs"],
            label=f"{label} transient recurrence catalogs",
            maximum_length=1_000_000,
        )
        _require(
            activation == "ACTIVE" or not recurrence_catalogs,
            f"{label} inactive prefix reruns a transient recurrence",
        )
        child = _require_integer(
            derivation["input_prefix_frontier_child_position"],
            label=f"{label} input-prefix frontier child",
            minimum=1,
            maximum=node_position - 1,
        )
        expected_children = [child]
    elif node_kind == "LOCAL_SHUTDOWN_MINIMALITY_FRONTIER":
        _require(
            type(validated_inventory) is dict and type(validated_registry) is dict,
            f"{label} local baseline authorities are unavailable",
        )
        if resource_meter is None:
            raise MaximumProtocolValidationError(
                f"{label} local baseline validation has no certificate-owned meter"
            )
        local_profiles = _require_array(
            validated_inventory["operation_contracts"][
                "maximum_constraint_scope_profile_catalog"
            ],
            label=f"{label} profile authority",
            exact_length=408,
        )
        local_profile = local_profiles[2]
        _require(
            local_profile["maximum_constraint_scope_profile_id"]
            == EXPECTED_SELECTED_PROFILE_IDS[3],
            f"{label} profile-3 authority differs",
        )
        baseline_spec = _resolve_v3_inventory_record_reference(
            derivation["baseline_spec_record_reference"],
            validated_inventory=validated_inventory,
            validated_registry=validated_registry,
            permitted_inventory_pointer_authority=(
                _inventory_pointer_authority_from_profile(
                    local_profile,
                    label=f"{label} profile-3 pointer authority",
                )
            ),
            expected_inventory_pointer=LOCAL_SHUTDOWN_BASELINE_SPEC_POINTER,
            expected_record_type_name=LOCAL_SHUTDOWN_BASELINE_SPEC_TYPE_NAME,
            label=f"{label} baseline-spec reference",
            resource_meter=resource_meter,
        ).validated_record
        _require(
            all(
                baseline_spec.record["spec"][member_name]
                == LOCAL_SHUTDOWN_BASELINE_MUTABLE_VALUES[member_name]
                for member_name in LOCAL_SHUTDOWN_MUTABLE_LIMIT_MEMBERS
            ),
            f"{label} pinned baseline mutable vector differs",
        )
        names = _require_array(
            derivation["ordered_mutable_limit_member_names"],
            label=f"{label} mutable limit names",
            exact_length=len(LOCAL_SHUTDOWN_MUTABLE_LIMIT_MEMBERS),
        )
        _require(
            tuple(names) == LOCAL_SHUTDOWN_MUTABLE_LIMIT_MEMBERS,
            f"{label} mutable limit names differ",
        )
        relations = _require_text_id_array(
            derivation["ordered_intrinsic_relation_ids"],
            label=f"{label} intrinsic relation IDs",
        )
        _require(
            tuple(relations) == LOCAL_SHUTDOWN_INTRINSIC_RELATION_IDS,
            f"{label} intrinsic relation authority/order differs",
        )
        _require(
            derivation["prospective_result_attainment_mode"]
            == "PROSPECTIVE_BYTE_MAXIMUM_WITH_ONE_MASKED_OUTER_CODEC",
            f"{label} prospective-result mode differs",
        )
        masked_coordinate = _validate_codec_coordinate(
            derivation["masked_outer_codec_coordinate"],
            label=f"{label} masked outer codec coordinate",
        )
        _require(
            masked_coordinate
            == {
                "validation_root_type_name": (
                    "CapacityMeasurementOperationResultEvidence"
                ),
                "codec_owner_type_name": ("CapacityMeasurementOperationResultEvidence"),
                "codec_owner_typed_member_path": [],
                "codec_byte_bound_relation": "LT",
                "codec_octet_limit": 524_288,
            },
            f"{label} masked outer codec coordinate differs",
        )
        baseline_result = _resolve_local_baseline_result_control_pointer(
            derivation["baseline_result_inventory_json_pointer"],
            validated_inventory=validated_inventory,
            validated_registry=validated_registry,
            resource_meter=resource_meter,
            label=f"{label} baseline-result inventory pointer",
        )
        baseline_length = _require_integer(
            derivation["baseline_result_canonical_byte_length"],
            label=f"{label} baseline result byte length",
            minimum=1,
        )
        _require(
            derivation["outer_codec_byte_bound_relation"] == "LT"
            and derivation["outer_codec_octet_limit"] == 524_288
            and baseline_length
            == baseline_result.record_canonical_byte_length
            == LOCAL_SHUTDOWN_BASELINE_RESULT_CANONICAL_OCTETS
            and baseline_length < 524_288,
            f"{label} outer codec/baseline relation differs",
        )
        _validate_winning_objective(
            derivation["winning_objective"],
            label=f"{label} winning objective",
        )
        _require_integer(
            derivation["prospective_result_canonical_byte_length"],
            label=f"{label} prospective result byte length",
            minimum=524_288,
        )
        _require_sha256(
            derivation["prospective_result_canonical_sha256"],
            label=f"{label} prospective result SHA",
        )
        baseline_child = _require_integer(
            derivation["baseline_spec_fixed_child_position"],
            label=f"{label} baseline-spec fixed child",
            minimum=1,
            maximum=node_position - 1,
        )
        _require(
            baseline_child == 1,
            f"{label} baseline-spec fixed child is not canonical position 1",
        )
        boundaries = _require_array(
            derivation["ordered_boundary_candidate_root_positions"],
            label=f"{label} boundary roots",
            maximum_length=1_000_000,
        )
        for position, child in enumerate(boundaries, 1):
            _require_integer(
                child,
                label=f"{label} boundary root {position}",
                minimum=1,
                maximum=node_position - 1,
            )
        _require(
            len(set(boundaries)) == len(boundaries)
            and baseline_child not in boundaries,
            f"{label} baseline/boundary children are not unique",
        )
        boundary_witnesses = _require_array(
            derivation["ordered_boundary_candidate_witness_records"],
            label=f"{label} boundary candidate witnesses",
            exact_length=len(boundaries),
        )
        previous_boundary_root = 0
        for witness_position, (witness_value, boundary_root) in enumerate(
            zip(boundary_witnesses, boundaries, strict=True),
            1,
        ):
            witness = _require_exact_keys(
                witness_value,
                BOUNDARY_CANDIDATE_WITNESS_KEYS,
                label=f"{label} boundary witness {witness_position}",
            )
            _require(
                witness["boundary_witness_position"] == witness_position
                and witness["boundary_candidate_root_position"] == boundary_root
                and boundary_root > previous_boundary_root,
                f"{label} boundary witness position/root order differs",
            )
            previous_boundary_root = boundary_root
            for record_name in (
                "candidate_mutated_spec",
                "prospective_scope_witness_context",
                "prospective_result",
            ):
                _require(
                    type(witness[record_name]) is dict,
                    f"{label} boundary witness {record_name} is not structured",
                )
            _require_array(
                witness["ordered_component_choice_evidence"],
                label=f"{label} boundary witness choice evidence {witness_position}",
                maximum_length=1_000_000,
            )
            _require_integer(
                witness["prospective_result_canonical_byte_length"],
                label=f"{label} boundary witness length {witness_position}",
                minimum=1,
            )
            _require_sha256(
                witness["prospective_result_canonical_sha256"],
                label=f"{label} boundary witness SHA {witness_position}",
            )
            _require_sha256(
                witness["boundary_candidate_witness_id"],
                label=f"{label} boundary witness ID {witness_position}",
            )
            candidate_spec = _validate_local_shutdown_mutated_spec(
                witness["candidate_mutated_spec"],
                baseline_spec=baseline_spec.record,
                validated_registry=validated_registry,
                resource_meter=resource_meter,
                label=f"{label} boundary witness {witness_position} candidate spec",
            )
            _, prospective_length = _validate_local_shutdown_prospective_result(
                witness["prospective_result"],
                mutated_spec=candidate_spec,
                validated_registry=validated_registry,
                resource_meter=resource_meter,
                label=(
                    f"{label} boundary witness {witness_position} prospective result"
                ),
            )
            _require(
                witness["prospective_result_canonical_byte_length"]
                == prospective_length,
                f"{label} boundary witness {witness_position} result length differs",
            )
        for member_name in (
            "ordered_breakpoint_records",
            "ordered_interval_exclusion_records",
            "ordered_recurrence_state_records",
            "ordered_recurrence_transition_records",
            "ordered_dominance_deletion_records",
        ):
            _require_array(
                derivation[member_name],
                label=f"{label} {member_name}",
                maximum_length=1_000_000,
            )
        _require(
            derivation["recurrence_version"]
            == "LEXICAL_SUBSET_UINT128_DELTA_AND_PROSPECTIVE_BYTE_FRONTIER_V1",
            f"{label} recurrence version differs",
        )
        _require(
            child_positions == [baseline_child, *boundaries],
            f"{label} direct/boundary child order differs",
        )
    else:
        mode = derivation["attainment_mode"]
        _require(
            mode
            in {
                "BYTE_MAXIMUM",
                "PROSPECTIVE_BYTE_MAXIMUM_WITH_ONE_MASKED_OUTER_CODEC",
            },
            f"{label} attainment mode differs",
        )
        _require(
            derivation["codec_byte_bound_relation"] in {"LE", "LT"},
            f"{label} codec relation differs",
        )
        _require_integer(derivation["codec_octet_limit"], label=f"{label} codec limit")
        owner_relation = derivation["owner_codec_byte_bound_relation"]
        owner_limit = derivation["owner_codec_octet_limit"]
        _require(
            (owner_relation is None and owner_limit is None)
            or (owner_relation in {"LE", "LT"} and type(owner_limit) is int),
            f"{label} owner codec nullability differs",
        )
        if owner_limit is not None:
            _require_integer(owner_limit, label=f"{label} owner codec limit")
        masked = derivation["masked_codec_coordinate"]
        _require(
            (mode == "PROSPECTIVE_BYTE_MAXIMUM_WITH_ONE_MASKED_OUTER_CODEC")
            == (type(masked) is dict),
            f"{label} masked codec coordinate differs",
        )
        if masked is not None:
            _validate_codec_coordinate(masked, label=f"{label} masked codec coordinate")
            _require(
                masked
                == {
                    "validation_root_type_name": (
                        "CapacityMeasurementOperationResultEvidence"
                    ),
                    "codec_owner_type_name": (
                        "CapacityMeasurementOperationResultEvidence"
                    ),
                    "codec_owner_typed_member_path": [],
                    "codec_byte_bound_relation": "LT",
                    "codec_octet_limit": 524_288,
                },
                f"{label} prospective masked codec coordinate differs",
            )
        maximum = _require_integer(
            derivation["certified_upper_bound_octets"],
            label=f"{label} certified upper bound",
        )
        witness_length = _require_integer(
            derivation["attaining_witness_canonical_byte_length"],
            label=f"{label} attaining witness length",
        )
        _require(maximum == witness_length, f"{label} attainment equality differs")
        _require_sha256(
            derivation["attaining_witness_canonical_sha256"],
            label=f"{label} attaining witness SHA",
        )
        attaining_case = derivation["attaining_scope_case_position"]
        _require(
            attaining_case is None or type(attaining_case) is int,
            f"{label} attaining scope-case position differs",
        )
        if attaining_case is not None:
            _require_integer(
                attaining_case,
                label=f"{label} attaining scope-case position",
                minimum=1,
            )
        upper_child = _require_integer(
            derivation["upper_frontier_child_position"],
            label=f"{label} upper-frontier child",
            minimum=1,
            maximum=node_position - 1,
        )
        winner_child = _require_integer(
            derivation["winner_frontier_child_position"],
            label=f"{label} winner-frontier child",
            minimum=1,
            maximum=node_position - 1,
        )
        _require(
            upper_child != winner_child,
            f"{label} upper and winner children must be distinct",
        )
        expected_children = [upper_child, winner_child]
    if expected_children is not None:
        _require(
            child_positions == expected_children,
            f"{label} variant/common child positions differ",
        )
    return derivation


def _validate_prior_position_graph(
    value: Any,
    *,
    root_position: int,
    label: str,
) -> list[int]:
    """Validate a contiguous, last-rooted DAG using only prior-position edges."""

    child_rows = _require_array(value, label=label, maximum_length=1_000_000)
    _require(bool(child_rows), f"{label} must not be empty")
    _require_integer(
        root_position,
        label=f"{label} root position",
        minimum=1,
        maximum=len(child_rows),
    )
    _require(
        root_position == len(child_rows),
        f"{label} root is not the last position",
    )
    depths: list[int] = []
    for position, child_value in enumerate(child_rows, 1):
        children = _require_array(
            child_value,
            label=f"{label} children {position}",
            maximum_length=1_000_000,
        )
        for ordinal, child_position in enumerate(children, 1):
            _require_integer(
                child_position,
                label=f"{label} child {position}:{ordinal}",
                minimum=1,
                maximum=position - 1,
            )
        _require(
            len(set(children)) == len(children),
            f"{label} position {position} repeats a child",
        )
        depths.append(1 + max((depths[child - 1] for child in children), default=0))
    reachable: set[int] = set()
    pending = [root_position]
    while pending:
        position = pending.pop()
        if position in reachable:
            continue
        reachable.add(position)
        pending.extend(child_rows[position - 1])
    _require(
        reachable == set(range(1, root_position + 1)),
        f"{label} contains unreachable positions",
    )
    return depths


def _validate_transient_locator_binding(
    locator: dict[str, Any],
    *,
    child_positions: list[int],
    child_ids: list[str],
    label: str,
) -> None:
    if locator["locator_kind"] != "TRANSIENT_FRONTIER_STATE":
        return
    source_position = locator["transient_source_child_position"]
    _require(
        source_position in child_positions,
        f"{label} transient source is not a direct child",
    )
    source_ordinal = child_positions.index(source_position)
    _require(
        locator["transient_source_child_proof_node_id"] == child_ids[source_ordinal],
        f"{label} transient source identity differs",
    )


def _validate_prefix_frontier_shape(
    *,
    coordinate_activation: str,
    selected_atom: dict[str, Any],
    input_dimensions: list[dict[str, Any]],
    input_frontier: dict[str, Any],
    output_dimensions: list[dict[str, Any]],
    output_frontier: dict[str, Any],
    label: str,
) -> None:
    """Check the protocol's structural state-signature prefix transition."""

    if coordinate_activation == "INACTIVE":
        _require(
            output_dimensions == input_dimensions,
            f"{label} inactive prefix changes its state signature",
        )
        # Semantic frontier identity is established by the authenticated direct
        # child alias.  Do not walk or compare the origin frontier again here.
        return

    _require(
        len(output_dimensions) == len(input_dimensions) + 1
        and output_dimensions[:-1] == input_dimensions,
        f"{label} active prefix does not append exactly one dimension",
    )
    appended_descriptor_id = output_dimensions[-1]["observable_descriptor_id"]
    _require(
        appended_descriptor_id
        not in {
            dimension["observable_descriptor_id"] for dimension in input_dimensions
        },
        f"{label} active prefix reuses an earlier dimension",
    )
    input_keys = {
        _canonical_bytes(state["state_key"])
        for state in input_frontier["ordered_state_frontiers"]
    }
    for state_position, state in enumerate(
        output_frontier["ordered_state_frontiers"],
        1,
    ):
        state_key = state["state_key"]
        _require(
            _canonical_bytes(state_key[:-1]) in input_keys,
            f"{label} state {state_position} is not retained from the input",
        )
        appended_cell = state_key[-1]
        _require(
            appended_cell["cell_kind"] == "EXACT_ATOM"
            and appended_cell["exact_atom"] == selected_atom,
            f"{label} state {state_position} does not append the selected atom",
        )


def _validate_boundary_candidate_witness_binding(
    witness: dict[str, Any],
    *,
    boundary_root: dict[str, Any],
    maximum_protocol_sha256: str,
    label: str,
    resource_meter: ProofResourceMeter | None = None,
) -> None:
    _require(
        boundary_root["proof_node_kind"] == "CODEC_INTERSECTION_ATTAINMENT"
        and boundary_root["derivation"]["attainment_mode"]
        == "PROSPECTIVE_BYTE_MAXIMUM_WITH_ONE_MASKED_OUTER_CODEC",
        f"{label} does not name a prospective codec root",
    )
    root_derivation = boundary_root["derivation"]
    prospective_octets = _canonical_octet_length(witness["prospective_result"])
    _require(
        witness["prospective_result_canonical_byte_length"]
        == prospective_octets
        == root_derivation["attaining_witness_canonical_byte_length"],
        f"{label} prospective-result length differs",
    )
    if resource_meter is None:
        witness_digest = _canonical_sha256_stream(witness["prospective_result"])
        root_digest = _canonical_sha256_stream(witness["prospective_result"])
    else:
        witness_digest, _ = _metered_canonical_sha256(
            witness["prospective_result"],
            meter=resource_meter,
        )
        root_digest, _ = _metered_canonical_sha256(
            witness["prospective_result"],
            meter=resource_meter,
        )
    _require(
        witness["prospective_result_canonical_sha256"] == witness_digest
        and root_derivation["attaining_witness_canonical_sha256"] == root_digest,
        f"{label} prospective-result SHA differs",
    )
    witness_payload = {
        name: item
        for name, item in witness.items()
        if name != "boundary_candidate_witness_id"
    }
    _require(
        witness["boundary_candidate_witness_id"]
        == _semantic_id(
            BOUNDARY_CANDIDATE_WITNESS_DOMAIN,
            {
                "maximum_protocol_sha256": maximum_protocol_sha256,
                **witness_payload,
            },
            resource_meter=resource_meter,
        ),
        f"{label} semantic identity differs",
    )


def _validate_local_baseline_spec_fixed_child(
    node: dict[str, Any],
    *,
    frontier_resolution: dict[str, Any],
    label: str,
) -> None:
    expected_locator = {
        "locator_kind": "V3_INVENTORY_POINTER",
        "record_reference_id": LOCAL_SHUTDOWN_BASELINE_SPEC_POINTER,
        "root_type_name": LOCAL_SHUTDOWN_BASELINE_SPEC_TYPE_NAME,
        "root_value_schema_id": None,
        "ordered_path_steps": [],
        "transient_state_key": None,
        "transient_source_child_position": None,
        "transient_source_child_proof_node_id": None,
    }
    _require(
        node["proof_node_position"] == 1
        and node["proof_node_kind"] == "FIXED_VALUE"
        and node["subject_locator"] == expected_locator
        and node["value_schema_id"] == LOCAL_SHUTDOWN_BASELINE_SPEC_VALUE_SCHEMA_ID
        and node["type_name"] == LOCAL_SHUTDOWN_BASELINE_SPEC_TYPE_NAME
        and node["alternative_name"] is None
        and node["effective_canonical_octet_ceiling"]
        == LOCAL_SHUTDOWN_BASELINE_SPEC_EFFECTIVE_CEILING
        and node["ordered_child_positions"] == []
        and node["ordered_child_proof_node_ids"] == []
        and node["ordered_ancestor_observable_dimensions"] == [],
        f"{label} common fixed-node shape differs",
    )
    derivation = node["derivation"]
    _require(
        derivation
        == {
            "derivation_kind": "FIXED_VALUE",
            "fixed_source_kind": "FROZEN_AUTHORITY",
            "fixed_source_locator": expected_locator,
            "fixed_transfer_kind": "EXACT_FIXED_VALUE",
            "fixed_canonical_byte_length": (
                LOCAL_SHUTDOWN_BASELINE_SPEC_CANONICAL_OCTETS
            ),
            "fixed_canonical_sha256": (LOCAL_SHUTDOWN_BASELINE_SPEC_CANONICAL_SHA256),
            "derived_identity_mapping_catalog_id": None,
            "ordered_identity_payload_child_positions": [],
        },
        f"{label} fixed derivation differs",
    )
    _require(
        node["output_frontier"]["frontier_encoding_kind"] == "MATERIALIZED",
        f"{label} must materialize its singleton frontier",
    )
    materialized = frontier_resolution["resolved_materialized_frontier"]
    evidence = frontier_resolution["frontier_evidence"]
    commitment = node["frontier_commitment"]
    _require(
        materialized["frontier_soundness"] == "EXACT_ATTAINABLE"
        and evidence["state_entry_count"] == 1
        and evidence["expanded_attainable_point_count"] == 1
        and evidence["minimum_attainable_octets"]
        == LOCAL_SHUTDOWN_BASELINE_SPEC_CANONICAL_OCTETS
        and evidence["maximum_attainable_octets"]
        == LOCAL_SHUTDOWN_BASELINE_SPEC_CANONICAL_OCTETS
        and commitment["least_measured_choice_vector_sha256_at_maximum"] is None
        and commitment["least_context_choice_vector_sha256_at_maximum"] is None,
        f"{label} singleton frontier differs",
    )


def _derive_frontier_retention_schedule(
    node_values: list[Any],
    *,
    graph_children: list[list[int]],
    label: str,
) -> tuple[list[list[int]], list[list[int]]]:
    """Derive trusted release buckets before any frontier is retained."""

    root_position = len(node_values)
    last_use = list(range(1, root_position + 1))
    for parent_position, child_positions in enumerate(graph_children, 1):
        for child_position in child_positions:
            last_use[child_position - 1] = max(
                last_use[child_position - 1], parent_position
            )

    resolved_origins: list[int] = []
    alias_positions: list[int] = []
    for position, node_value in enumerate(node_values, 1):
        node = _require_exact_keys(
            node_value,
            PROOF_NODE_KEYS,
            label=f"{label} retention node {position}",
        )
        output = _require_exact_keys(
            node["output_frontier"],
            OUTPUT_FRONTIER_KEYS,
            label=f"{label} retention output {position}",
        )
        encoding_kind = output["frontier_encoding_kind"]
        _require(
            encoding_kind in {"MATERIALIZED", "DIRECT_CHILD_ALIAS"},
            f"{label} retention output {position} encoding kind differs",
        )
        if encoding_kind == "MATERIALIZED":
            _require(
                type(output["materialized_frontier"]) is dict
                and output["direct_child_alias"] is None,
                f"{label} retention materialized output {position} differs",
            )
            resolved_origins.append(position)
            continue
        _require(
            output["materialized_frontier"] is None
            and type(output["direct_child_alias"]) is dict,
            f"{label} retention alias output {position} differs",
        )
        alias = _require_exact_keys(
            output["direct_child_alias"],
            DIRECT_CHILD_ALIAS_KEYS,
            label=f"{label} retention alias {position}",
        )
        child_position = _require_integer(
            alias["aliased_child_position"],
            label=f"{label} retention alias child {position}",
            minimum=1,
            maximum=position - 1,
        )
        _require(
            child_position in graph_children[position - 1],
            f"{label} retention alias {position} is not a direct graph child",
        )
        origin_position = resolved_origins[child_position - 1]
        resolved_origins.append(origin_position)
        alias_positions.append(position)

    encoding_last_use = list(last_use)
    for alias_position in alias_positions:
        origin_position = resolved_origins[alias_position - 1]
        encoding_last_use[origin_position - 1] = max(
            encoding_last_use[origin_position - 1],
            last_use[alias_position - 1],
        )
    encoding_release_buckets: list[list[int]] = [[] for _ in range(root_position + 1)]
    commitment_release_buckets: list[list[int]] = [[] for _ in range(root_position + 1)]
    for position in range(1, root_position + 1):
        encoding_release_buckets[encoding_last_use[position - 1]].append(position)
        commitment_release_buckets[last_use[position - 1]].append(position)
    return encoding_release_buckets, commitment_release_buckets


def _derive_catalog_retention_evidence(
    *,
    node_count: int,
    frontier_encoding_release_positions: list[int],
    node_transfer_dependencies: list[tuple[CatalogOccurrenceKey, ...]],
    node_frontier_dependencies: list[tuple[CatalogOccurrenceKey, ...]],
    occurrences: list[CatalogOccurrence],
    meter: ProofResourceMeter,
    label: str,
) -> CatalogRetentionEvidence:
    """Compute occurrence-sensitive transitive catalog liveness in linear time."""

    _require(node_count >= 1, f"{label} proof-node count differs")
    _require(
        len(frontier_encoding_release_positions)
        == len(node_transfer_dependencies)
        == len(node_frontier_dependencies)
        == node_count,
        f"{label} node schedule lengths differ",
    )
    for node_position, release_position in enumerate(
        frontier_encoding_release_positions,
        1,
    ):
        _require_integer(
            release_position,
            label=f"{label} frontier release {node_position}",
            minimum=node_position,
            maximum=node_count,
        )

    by_key: dict[CatalogOccurrenceKey, CatalogOccurrence] = {}
    ordinals_by_node: dict[int, list[int]] = {}
    for occurrence in occurrences:
        key = occurrence.key
        _require(
            type(key) is CatalogOccurrenceKey and key not in by_key,
            f"{label} catalog occurrence key differs or repeats",
        )
        _require_integer(
            key.defining_node_position,
            label=f"{label} catalog defining node",
            minimum=1,
            maximum=node_count,
        )
        _require_integer(
            key.catalog_ordinal_within_node,
            label=f"{label} catalog ordinal",
            minimum=1,
        )
        _require_sha256(occurrence.catalog_id, label=f"{label} catalog ID")
        _require_integer(
            occurrence.complete_root_octets,
            label=f"{label} catalog root octets",
        )
        _require(
            occurrence.retention_kind
            in {"PERSISTENT_INTERNAL", "CURRENT_NODE_TRANSIENT"},
            f"{label} catalog retention kind differs",
        )
        _require(
            len(set(occurrence.direct_prior_occurrences))
            == len(occurrence.direct_prior_occurrences),
            f"{label} catalog dependencies repeat",
        )
        by_key[key] = occurrence
        ordinals_by_node.setdefault(key.defining_node_position, []).append(
            key.catalog_ordinal_within_node
        )
    for node_position, ordinals in ordinals_by_node.items():
        _require(
            sorted(ordinals) == list(range(1, len(ordinals) + 1)),
            f"{label} catalog ordinals at node {node_position} are not contiguous",
        )
    ordered_keys = sorted(by_key)
    for key in ordered_keys:
        for dependency in by_key[key].direct_prior_occurrences:
            _require(
                dependency in by_key and dependency < key,
                f"{label} catalog dependency is not a prior defining occurrence",
            )

    last_use = {key: key.defining_node_position for key in ordered_keys}

    def extend_dependencies(
        dependencies: tuple[CatalogOccurrenceKey, ...],
        *,
        node_position: int,
        required_through: int,
        dependency_label: str,
    ) -> None:
        _require(
            len(set(dependencies)) == len(dependencies),
            f"{label} {dependency_label} dependencies repeat at node {node_position}",
        )
        for dependency in dependencies:
            _require(
                dependency in by_key
                and dependency.defining_node_position <= node_position,
                f"{label} {dependency_label} names an unavailable occurrence",
            )
            last_use[dependency] = max(last_use[dependency], required_through)

    for node_position in range(1, node_count + 1):
        extend_dependencies(
            node_transfer_dependencies[node_position - 1],
            node_position=node_position,
            required_through=node_position,
            dependency_label="transfer",
        )
        extend_dependencies(
            node_frontier_dependencies[node_position - 1],
            node_position=node_position,
            required_through=frontier_encoding_release_positions[node_position - 1],
            dependency_label="frontier",
        )

    for key in reversed(ordered_keys):
        required_through = last_use[key]
        for dependency in by_key[key].direct_prior_occurrences:
            last_use[dependency] = max(last_use[dependency], required_through)

    for key in ordered_keys:
        occurrence = by_key[key]
        if occurrence.retention_kind == "CURRENT_NODE_TRANSIENT":
            _require(
                last_use[key] == key.defining_node_position,
                f"{label} transient catalog escapes its defining node",
            )

    start_octets = [0] * (node_count + 2)
    release_octets = [0] * (node_count + 2)
    release_buckets: list[list[CatalogOccurrenceKey]] = [
        [] for _ in range(node_count + 1)
    ]
    for key in ordered_keys:
        octets = by_key[key].complete_root_octets
        start_octets[key.defining_node_position] += octets
        release_octets[last_use[key] + 1] += octets
        release_buckets[last_use[key]].append(key)

    live_octets = 0
    peak_octets = 0
    for node_position in range(1, node_count + 1):
        live_octets -= release_octets[node_position]
        _require(live_octets >= 0, f"{label} catalog live-octet schedule underflows")
        prospective_live = live_octets + start_octets[node_position]
        _require(
            prospective_live <= SAFE_INTEGER_MAXIMUM,
            f"{label} catalog live-octet schedule exceeds safe arithmetic",
        )
        meter.observe_maximum("peak_retained_state_catalog_octets", prospective_live)
        live_octets = prospective_live
        peak_octets = max(peak_octets, live_octets)
    _require(
        live_octets == release_octets[node_count + 1],
        f"{label} catalog terminal release differs",
    )
    return CatalogRetentionEvidence(
        last_use_by_occurrence=last_use,
        release_buckets=tuple(tuple(bucket) for bucket in release_buckets),
        peak_retained_octets=peak_octets,
    )


def _validate_proof_dag_metered(
    value: Any,
    *,
    maximum_protocol_sha256: str,
    proof_scope_authority_id: str,
    proof_context_authority_id: str,
    label: str,
    resource_meter: ProofResourceMeter,
    validated_inventory: dict[str, Any] | None = None,
    validated_registry: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    meter = resource_meter
    node_values = _require_array(value, label=label, maximum_length=1_000_000)
    _require(bool(node_values), f"{label} must not be empty")
    meter.add("proof_node_count", len(node_values))
    graph_children: list[list[int]] = []
    for position, node_value in enumerate(node_values, 1):
        graph_node = _require_exact_keys(
            node_value,
            PROOF_NODE_KEYS,
            label=f"{label} graph node {position}",
        )
        _require(
            graph_node["proof_node_position"] == position,
            f"{label} graph-node positions differ",
        )
        graph_node_children = _require_array(
            graph_node["ordered_child_positions"],
            label=f"{label} graph node {position} child positions",
        )
        meter.add("proof_edge_count", len(graph_node_children))
        meter.observe_maximum("maximum_child_count", len(graph_node_children))
        graph_children.append(graph_node_children)
    depths = _validate_prior_position_graph(
        graph_children,
        root_position=len(node_values),
        label=f"{label} prior-position graph",
    )
    meter.observe_maximum("maximum_proof_depth", max(depths))
    encoding_release_buckets, commitment_release_buckets = (
        _derive_frontier_retention_schedule(
            node_values,
            graph_children=graph_children,
            label=label,
        )
    )
    nodes: list[dict[str, Any]] = []
    frontier_resolutions: list[dict[str, Any]] = []
    frontier_encoding_octets: list[int] = []
    frontier_commitment_octets: list[int] = []
    live_encoding_octets = 0
    live_commitment_octets = 0
    recomputed = {
        "proof_node_count": len(node_values),
        "proof_edge_count": 0,
        "maximum_proof_depth": 0,
        "maximum_child_count": 0,
        "state_signature_dimension_count": 0,
        "maximum_state_signature_dimension_count": 0,
        "frontier_state_entry_count": 0,
        "frontier_bitmap_run_count": 0,
        "frontier_expanded_point_count": 0,
        "maximum_frontier_width": 0,
        "peak_retained_frontier_octets": 0,
        "frontier_canonicalized_octets": 0,
        "component_choice_coordinate_count": 0,
    }
    for position, node_value in enumerate(node_values, 1):
        node_label = f"{label} node {position}"
        node = _require_exact_keys(node_value, PROOF_NODE_KEYS, label=node_label)
        _require(
            node["proof_node_position"] == position,
            f"{node_label} position differs",
        )
        node_kind = node["proof_node_kind"]
        _require(node_kind in PROOF_NODE_KINDS, f"{node_label} kind differs")
        subject_locator = _validate_proof_subject_locator(
            node["subject_locator"],
            label=f"{node_label} subject locator",
            resource_meter=meter,
        )
        _require_optional_sha256(
            node["value_schema_id"], label=f"{node_label} value-schema ID"
        )
        _require_optional_text(node["type_name"], label=f"{node_label} type name")
        _require_optional_text(
            node["alternative_name"], label=f"{node_label} alternative name"
        )
        effective_ceiling = _require_integer(
            node["effective_canonical_octet_ceiling"],
            label=f"{node_label} effective ceiling",
        )
        child_positions = _require_array(
            node["ordered_child_positions"],
            label=f"{node_label} child positions",
            maximum_length=1_000_000,
        )
        for child_ordinal, child_position in enumerate(child_positions, 1):
            _require_integer(
                child_position,
                label=f"{node_label} child {child_ordinal}",
                minimum=1,
                maximum=position - 1,
            )
        _require(
            len(set(child_positions)) == len(child_positions),
            f"{node_label} repeats a child position",
        )
        child_ids = _require_array(
            node["ordered_child_proof_node_ids"],
            label=f"{node_label} child IDs",
            exact_length=len(child_positions),
        )
        expected_child_ids = [
            nodes[child - 1]["proof_node_id"] for child in child_positions
        ]
        _require(
            child_ids == expected_child_ids,
            f"{node_label} child identities differ from prior positions",
        )
        dimensions, state_signature_id = _validate_state_dimensions(
            node["ordered_ancestor_observable_dimensions"],
            label=f"{node_label} state dimensions",
            resource_meter=meter,
        )
        meter.add("state_signature_dimension_count", len(dimensions))
        meter.observe_maximum(
            "maximum_state_signature_dimension_count", len(dimensions)
        )
        derivation = _validate_derivation(
            node["derivation"],
            node_kind=node_kind,
            child_positions=child_positions,
            node_position=position,
            label=f"{node_label} derivation",
            resource_meter=meter,
            validated_inventory=validated_inventory,
            validated_registry=validated_registry,
        )
        depth = depths[position - 1]
        output, frontier_resolution = _validate_output_frontier(
            node["output_frontier"],
            dimensions=dimensions,
            state_signature_id=state_signature_id,
            node_kind=node_kind,
            derivation=derivation,
            node_position=position,
            child_positions=child_positions,
            child_ids=child_ids,
            prior_frontier_resolutions=frontier_resolutions,
            proof_depth=depth,
            label=f"{node_label} output frontier",
            resource_meter=meter,
        )
        resolved_output = frontier_resolution["resolved_materialized_frontier"]
        frontier_evidence = frontier_resolution["frontier_evidence"]
        commitment = _validate_frontier_commitment(
            node["frontier_commitment"],
            state_signature_id=state_signature_id,
            frontier_evidence=frontier_evidence,
            label=f"{node_label} frontier commitment",
            resource_meter=meter,
        )
        if output["frontier_encoding_kind"] == "DIRECT_CHILD_ALIAS":
            alias = output["direct_child_alias"]
            _validate_alias_frontier_commitment(
                commitment,
                aliased_child_commitment=nodes[alias["aliased_child_position"] - 1][
                    "frontier_commitment"
                ],
                node_kind=node_kind,
                derivation=derivation,
                label=f"{node_label} frontier commitment",
            )
        maximum_attainable = frontier_evidence["maximum_attainable_octets"]
        _require(
            maximum_attainable is None or maximum_attainable <= effective_ceiling,
            f"{node_label} output exceeds its downward effective ceiling",
        )
        transient_locators = [
            subject_locator,
            *(dimension["subject_locator"] for dimension in dimensions),
        ]
        if node_kind == "FIXED_VALUE":
            transient_locators.append(derivation["fixed_source_locator"])
        for locator_position, locator in enumerate(transient_locators, 1):
            _validate_transient_locator_binding(
                locator,
                child_positions=child_positions,
                child_ids=child_ids,
                label=f"{node_label} locator binding {locator_position}",
            )
        if node_kind == "FIXED_VALUE":
            safe_transfer = (
                derivation["fixed_transfer_kind"]
                == "DERIVED_IDENTITY_FIXED_WIDTH_SAFE_UPPER_DOMAIN"
            )
            _require(
                not safe_transfer
                or resolved_output["frontier_soundness"] == "SAFE_UPPER_DOMAIN",
                f"{node_label} fixed transfer/frontier soundness differs",
            )
        elif node_kind == "ARRAY_FRONTIER":
            safe_transfer = (
                derivation["array_transfer_kind"]
                == "ORDERED_LANGUAGE_SAFE_UPPER_DOMAIN"
            )
            _require(
                not safe_transfer
                or resolved_output["frontier_soundness"] == "SAFE_UPPER_DOMAIN",
                f"{node_label} array transfer/frontier soundness differs",
            )
        elif node_kind == "CONSTRAINT_FRONTIER":
            safe_transfer = (
                derivation["constraint_transfer_kind"] == "SAFE_UPPER_DOMAIN_RELAXATION"
            )
            _require(
                not safe_transfer
                or resolved_output["frontier_soundness"] == "SAFE_UPPER_DOMAIN",
                f"{node_label} constraint transfer/frontier soundness differs",
            )
        if node_kind == "MAXIMUM_SLICE_EXACT_FRONTIER":
            meter.add(
                "component_choice_coordinate_count",
                len(derivation["ordered_choice_coordinate_plan_ids"]),
            )
            _require(
                resolved_output["frontier_soundness"] == "EXACT_ATTAINABLE",
                f"{node_label} maximum slice is not exact",
            )
            _require(
                frontier_evidence["minimum_attainable_octets"]
                == frontier_evidence["maximum_attainable_octets"]
                == derivation["target_canonical_byte_length"],
                f"{node_label} maximum slice contains another byte length",
            )
            recomputed["component_choice_coordinate_count"] += len(
                derivation["ordered_choice_coordinate_plan_ids"]
            )
            for reinstatement_position in derivation[
                "ordered_exact_domain_reinstatement_node_positions"
            ]:
                reinstatement = nodes[reinstatement_position - 1]
                reinstatement_derivation = reinstatement["derivation"]
                is_safe_fixed = (
                    reinstatement["proof_node_kind"] == "FIXED_VALUE"
                    and reinstatement_derivation["fixed_transfer_kind"]
                    == "DERIVED_IDENTITY_FIXED_WIDTH_SAFE_UPPER_DOMAIN"
                )
                is_safe_array = (
                    reinstatement["proof_node_kind"] == "ARRAY_FRONTIER"
                    and reinstatement_derivation["array_transfer_kind"]
                    == "ORDERED_LANGUAGE_SAFE_UPPER_DOMAIN"
                )
                _require(
                    is_safe_fixed or is_safe_array,
                    f"{node_label} names a non-safe descriptor reinstatement",
                )
            upper_position = derivation["upper_frontier_child_position"]
            upper_ancestry: set[int] = set()
            pending = [upper_position]
            while pending:
                ancestor_position = pending.pop()
                if ancestor_position in upper_ancestry:
                    continue
                upper_ancestry.add(ancestor_position)
                pending.extend(graph_children[ancestor_position - 1])
            expected_reinstatements: list[int] = []
            expected_bindings: list[dict[str, Any]] = []
            for ancestor_position in sorted(upper_ancestry):
                ancestor = nodes[ancestor_position - 1]
                ancestor_kind = ancestor["proof_node_kind"]
                ancestor_derivation = ancestor["derivation"]
                if (
                    ancestor_kind == "FIXED_VALUE"
                    and ancestor_derivation["fixed_transfer_kind"]
                    == "DERIVED_IDENTITY_FIXED_WIDTH_SAFE_UPPER_DOMAIN"
                ) or (
                    ancestor_kind == "ARRAY_FRONTIER"
                    and ancestor_derivation["array_transfer_kind"]
                    == "ORDERED_LANGUAGE_SAFE_UPPER_DOMAIN"
                ):
                    expected_reinstatements.append(ancestor_position)
                if ancestor_kind == "CONSTRAINT_FRONTIER":
                    expected_bindings.append(
                        {
                            "constraint_id": ancestor_derivation[
                                "ordered_constraint_ids"
                            ][0],
                            "application_invocation": ancestor_derivation[
                                "application_invocation"
                            ],
                            "ordered_applicable_scope_case_positions": (
                                ancestor_derivation[
                                    "ordered_applicable_scope_case_positions"
                                ]
                            ),
                        }
                    )
            _require(
                derivation["ordered_exact_domain_reinstatement_node_positions"]
                == expected_reinstatements,
                f"{node_label} exact-domain reinstatement closure differs",
            )
            _require(
                derivation["ordered_exact_constraint_bindings"] == expected_bindings,
                f"{node_label} exact constraint-binding closure differs",
            )
        elif node_kind == "LEXICOGRAPHIC_PREFIX_EXCLUSION":
            _require(
                resolved_output["frontier_soundness"] == "EXACT_ATTAINABLE",
                f"{node_label} prefix exclusion is not exact",
            )
            input_position = derivation["input_prefix_frontier_child_position"]
            input_node = nodes[input_position - 1]
            input_kind = input_node["proof_node_kind"]
            _require(
                input_kind
                in {
                    "MAXIMUM_SLICE_EXACT_FRONTIER",
                    "LEXICOGRAPHIC_PREFIX_EXCLUSION",
                },
                f"{node_label} prefix input is not the maximum-slice/prefix chain",
            )
            if input_kind == "MAXIMUM_SLICE_EXACT_FRONTIER":
                previous_prefix_count = 0
                previous_active_count = 0
                maximum_slice = input_node
            else:
                input_derivation = input_node["derivation"]
                previous_prefix_count = input_derivation[
                    "fixed_prefix_coordinate_count"
                ]
                previous_active_count = input_derivation[
                    "fixed_active_prefix_coordinate_count"
                ]
                cursor = input_node
                while cursor["proof_node_kind"] == "LEXICOGRAPHIC_PREFIX_EXCLUSION":
                    cursor = nodes[
                        cursor["derivation"]["input_prefix_frontier_child_position"] - 1
                    ]
                _require(
                    cursor["proof_node_kind"] == "MAXIMUM_SLICE_EXACT_FRONTIER",
                    f"{node_label} prefix chain has no maximum-slice base",
                )
                maximum_slice = cursor
            prefix_count = derivation["fixed_prefix_coordinate_count"]
            active_count = derivation["fixed_active_prefix_coordinate_count"]
            activation_increment = int(derivation["coordinate_activation"] == "ACTIVE")
            _require(
                prefix_count == previous_prefix_count + 1
                and active_count == previous_active_count + activation_increment,
                f"{node_label} prefix counters differ from the input chain",
            )
            plan_ids = maximum_slice["derivation"]["ordered_choice_coordinate_plan_ids"]
            _require(
                prefix_count <= len(plan_ids)
                and derivation["choice_coordinate_plan_id"]
                == plan_ids[prefix_count - 1],
                f"{node_label} prefix plan identity/order differs",
            )
            _require(
                derivation["target_canonical_byte_length"]
                == maximum_slice["derivation"]["target_canonical_byte_length"],
                f"{node_label} target differs from its maximum-slice base",
            )
            _validate_prefix_frontier_shape(
                coordinate_activation=derivation["coordinate_activation"],
                selected_atom=derivation["selected_atom"],
                input_dimensions=input_node["ordered_ancestor_observable_dimensions"],
                input_frontier=frontier_resolutions[input_position - 1][
                    "resolved_materialized_frontier"
                ],
                output_dimensions=dimensions,
                output_frontier=resolved_output,
                label=node_label,
            )
        elif node_kind == "LOCAL_SHUTDOWN_MINIMALITY_FRONTIER":
            baseline_position = derivation["baseline_spec_fixed_child_position"]
            _validate_local_baseline_spec_fixed_child(
                nodes[baseline_position - 1],
                frontier_resolution=frontier_resolutions[baseline_position - 1],
                label=f"{node_label} baseline-spec fixed child",
            )
            boundary_witnesses = derivation[
                "ordered_boundary_candidate_witness_records"
            ]
            for witness_position, witness in enumerate(boundary_witnesses, 1):
                witness_label = f"{node_label} boundary witness {witness_position}"
                boundary_root = nodes[witness["boundary_candidate_root_position"] - 1]
                _validate_boundary_candidate_witness_binding(
                    witness,
                    boundary_root=boundary_root,
                    maximum_protocol_sha256=maximum_protocol_sha256,
                    label=witness_label,
                    resource_meter=meter,
                )
            recurrence = _validate_local_shutdown_recurrence_records(
                state_values=derivation["ordered_recurrence_state_records"],
                transition_values=derivation["ordered_recurrence_transition_records"],
                dominance_deletion_values=derivation[
                    "ordered_dominance_deletion_records"
                ],
                breakpoint_values=derivation["ordered_breakpoint_records"],
                interval_exclusion_values=derivation[
                    "ordered_interval_exclusion_records"
                ],
                boundary_root_positions=derivation[
                    "ordered_boundary_candidate_root_positions"
                ],
                boundary_witnesses=boundary_witnesses,
                proof_nodes=nodes,
                expected_winning_objective=derivation["winning_objective"],
                expected_winning_length=derivation[
                    "prospective_result_canonical_byte_length"
                ],
                expected_winning_sha256=derivation[
                    "prospective_result_canonical_sha256"
                ],
                resource_meter=meter,
                label=f"{node_label} recurrence",
            )
            _require(
                position == len(node_values)
                and dimensions == []
                and output["frontier_encoding_kind"] == "MATERIALIZED"
                and resolved_output["frontier_soundness"] == "EXACT_ATTAINABLE"
                and frontier_evidence["state_entry_count"] == 1
                and frontier_evidence["expanded_attainable_point_count"] == 1
                and frontier_evidence["minimum_attainable_octets"]
                == recurrence["winner_length"]
                and frontier_evidence["maximum_attainable_octets"]
                == recurrence["winner_length"]
                and commitment["least_measured_choice_vector_sha256_at_maximum"] is None
                and commitment["least_context_choice_vector_sha256_at_maximum"] is None,
                f"{node_label} winner singleton frontier differs",
            )
        elif node_kind == "CODEC_INTERSECTION_ATTAINMENT":
            winner = nodes[derivation["winner_frontier_child_position"] - 1]
            if winner["proof_node_kind"] == "MAXIMUM_SLICE_EXACT_FRONTIER":
                _require(
                    not winner["derivation"]["ordered_choice_coordinate_plan_ids"],
                    f"{node_label} codec bypasses a nonempty prefix catalog",
                )
            else:
                _require(
                    winner["proof_node_kind"] == "LEXICOGRAPHIC_PREFIX_EXCLUSION",
                    f"{node_label} winner child is not a prefix/maximum slice",
                )
                winner_derivation = winner["derivation"]
                cursor = winner
                while cursor["proof_node_kind"] == "LEXICOGRAPHIC_PREFIX_EXCLUSION":
                    cursor = nodes[
                        cursor["derivation"]["input_prefix_frontier_child_position"] - 1
                    ]
                _require(
                    cursor["proof_node_kind"] == "MAXIMUM_SLICE_EXACT_FRONTIER"
                    and winner_derivation["fixed_prefix_coordinate_count"]
                    == len(cursor["derivation"]["ordered_choice_coordinate_plan_ids"]),
                    f"{node_label} winner prefix chain is incomplete",
                )
        payload_node = {
            name: item for name, item in node.items() if name != "proof_node_id"
        }
        recomputed_node_id = _semantic_id(
            PROOF_NODE_DOMAIN,
            {
                "maximum_protocol_sha256": maximum_protocol_sha256,
                "proof_scope_authority_id": proof_scope_authority_id,
                "proof_context_authority_id": proof_context_authority_id,
                "node": payload_node,
            },
            resource_meter=meter,
        )
        _require(
            node["proof_node_id"] == recomputed_node_id,
            f"{node_label} semantic identity differs",
        )
        retained_frontier_object = (
            output["materialized_frontier"]
            if output["frontier_encoding_kind"] == "MATERIALIZED"
            else output["direct_child_alias"]
        )
        encoding_octets = _canonical_octet_length(retained_frontier_object)
        commitment_octets = _canonical_octet_length(commitment)
        prospective_live_encoding_octets = live_encoding_octets + encoding_octets
        prospective_live_commitment_octets = live_commitment_octets + commitment_octets
        retained_octets = (
            prospective_live_encoding_octets + prospective_live_commitment_octets
        )
        meter.observe_maximum("peak_retained_frontier_octets", retained_octets)
        frontier_encoding_octets.append(encoding_octets)
        frontier_commitment_octets.append(commitment_octets)
        live_encoding_octets = prospective_live_encoding_octets
        live_commitment_octets = prospective_live_commitment_octets
        recomputed["peak_retained_frontier_octets"] = max(
            recomputed["peak_retained_frontier_octets"], retained_octets
        )
        recomputed["proof_edge_count"] += len(child_positions)
        recomputed["maximum_proof_depth"] = max(
            recomputed["maximum_proof_depth"], depth
        )
        recomputed["maximum_child_count"] = max(
            recomputed["maximum_child_count"], len(child_positions)
        )
        recomputed["state_signature_dimension_count"] += len(dimensions)
        recomputed["maximum_state_signature_dimension_count"] = max(
            recomputed["maximum_state_signature_dimension_count"], len(dimensions)
        )
        if output["frontier_encoding_kind"] == "MATERIALIZED":
            for name in (
                "state_entry_count",
                "bitmap_run_count",
                "expanded_attainable_point_count",
            ):
                resource_name = {
                    "state_entry_count": "frontier_state_entry_count",
                    "bitmap_run_count": "frontier_bitmap_run_count",
                    "expanded_attainable_point_count": "frontier_expanded_point_count",
                }[name]
                recomputed[resource_name] += int(frontier_evidence[name])
            recomputed["frontier_canonicalized_octets"] += int(
                frontier_evidence["frontier_canonicalized_octets"]
            )
        recomputed["maximum_frontier_width"] = max(
            recomputed["maximum_frontier_width"],
            int(frontier_evidence["expanded_attainable_point_count"]),
        )
        meter.observe_maximum(
            "maximum_frontier_width",
            int(frontier_evidence["expanded_attainable_point_count"]),
        )
        nodes.append(node)
        frontier_resolutions.append(frontier_resolution)
        for released_position in encoding_release_buckets[position]:
            live_encoding_octets -= frontier_encoding_octets[released_position - 1]
        for released_position in commitment_release_buckets[position]:
            live_commitment_octets -= frontier_commitment_octets[released_position - 1]
        _require(
            commitment is node["frontier_commitment"], "internal commitment mismatch"
        )
    meter_snapshot = meter.snapshot()
    for name, expected in recomputed.items():
        _require(
            meter_snapshot[name] == expected,
            f"{label} internal proof-resource meter {name} differs",
        )
    return nodes, recomputed


def _validate_local_shutdown_proof_dag(
    value: Any,
    *,
    root_position: int,
    maximum_protocol_sha256: str,
    proof_scope_authority_id: str,
    proof_context_authority_id: str,
    validated_inventory: dict[str, Any],
    validated_registry: dict[str, Any],
    expected_winning_objective: dict[str, Any],
    expected_prospective_result_canonical_byte_length: int,
    expected_prospective_result_canonical_sha256: str,
    resource_meter: ProofResourceMeter,
    label: str,
) -> None:
    """Validate a complete local DAG under its enclosing derived authorities."""

    nodes, _ = _validate_proof_dag_metered(
        value,
        maximum_protocol_sha256=maximum_protocol_sha256,
        proof_scope_authority_id=proof_scope_authority_id,
        proof_context_authority_id=proof_context_authority_id,
        label=label,
        resource_meter=resource_meter,
        validated_inventory=validated_inventory,
        validated_registry=validated_registry,
    )
    _require(
        root_position == len(nodes)
        and nodes[-1]["proof_node_kind"] == "LOCAL_SHUTDOWN_MINIMALITY_FRONTIER",
        f"{label} root is not the sole final local-minimality root",
    )
    derivation = nodes[-1]["derivation"]
    _require(
        derivation["winning_objective"] == expected_winning_objective
        and derivation["prospective_result_canonical_byte_length"]
        == expected_prospective_result_canonical_byte_length
        and derivation["prospective_result_canonical_sha256"]
        == expected_prospective_result_canonical_sha256,
        f"{label} root retained result/objective differs",
    )


def _validate_proof_dag(
    value: Any,
    *,
    maximum_protocol_sha256: str,
    proof_scope_authority_id: str,
    proof_context_authority_id: str,
    label: str,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Seed-policy wrapper retained only for isolated structural unit tests."""

    return _validate_proof_dag_metered(
        value,
        maximum_protocol_sha256=maximum_protocol_sha256,
        proof_scope_authority_id=proof_scope_authority_id,
        proof_context_authority_id=proof_context_authority_id,
        label=label,
        resource_meter=ProofResourceMeter(phase=SEED_CAP_DERIVATION_PHASE),
    )


def _parse_resource_claim(
    value: Any,
    *,
    label: str,
) -> dict[str, Any]:
    claim = _require_exact_keys(value, PROOF_RESOURCE_KEYS, label=label)
    for name, item in claim.items():
        _require_integer(item, label=f"{label} {name}")
    return claim


def _validate_lexical_resource_summary(
    value: Mapping[str, int],
    *,
    producer_claim: Mapping[str, int],
    meter: ProofResourceMeter | None,
    label: str,
) -> None:
    actual = set(value)
    _require(
        actual == PROOF_RESOURCE_KEYS,
        f"{label} lexical resource-summary keys differ",
    )
    for name, item in value.items():
        _require(
            type(item) is int and 0 <= item <= SAFE_INTEGER_MAXIMUM,
            f"{label} lexical resource-summary {name} differs",
        )
    for name in LEXICALLY_OBSERVABLE_PROOF_RESOURCE_FIELDS:
        _require(
            producer_claim[name] == value[name],
            f"{label} producer claim {name} differs from lexical predecode",
        )
    if meter is None:
        return
    for name in CURRENTLY_METERED_LEXICAL_FIELDS:
        _require(
            value[name] == meter.value(name),
            f"{label} semantic meter {name} differs from lexical predecode",
        )


def _validate_frontier_encoding_version(value: Any, *, label: str) -> str:
    _require(
        value == FRONTIER_ENCODING_VERSION,
        f"{label} must use the mandatory tagged V2 frontier encoding",
    )
    return value


def _validate_certificate(
    value: Any,
    *,
    maximum_protocol_sha256: str,
    proof_context_manifest: dict[str, Any],
    validated_inventory: dict[str, Any],
    validated_registry: dict[str, Any],
    validated_max64_context_authority: dict[str, Any],
    expected_type_name: str,
    expected_alternative_name: str | None,
    expected_constraint_scope: str,
    expected_measurement_binding: dict[str, Any],
    expected_profile_id: str | None,
    resource_phase: str = SEED_CAP_DERIVATION_PHASE,
    accepted_resource_limits: Mapping[str, int] | None = None,
    lexical_resource_summary: Mapping[str, int] | None = None,
    label: str,
) -> tuple[dict[str, Any], dict[str, int]]:
    certificate = _require_exact_keys(value, CERTIFICATE_KEYS, label=label)
    producer_claim = _parse_resource_claim(
        certificate["proof_resource_claim"],
        label=f"{label} resource claim",
    )
    if lexical_resource_summary is not None:
        _validate_lexical_resource_summary(
            lexical_resource_summary,
            producer_claim=producer_claim,
            meter=None,
            label=label,
        )
    meter = ProofResourceMeter(
        phase=resource_phase,
        accepted_limits=accepted_resource_limits,
    )
    _require(
        certificate["certificate_version"]
        == "riskyieldmm.raw_v8_step2_external_schema_v2.upper_bound_certificate.v1",
        f"{label} version differs",
    )
    _require(
        certificate["canonicalization_version"] == CANONICALIZATION_VERSION
        and certificate["measurement_schema_version"] == MEASUREMENT_SCHEMA_VERSION,
        f"{label} canonicalization/measurement version differs",
    )
    _require(
        certificate["maximum_protocol_sha256"] == maximum_protocol_sha256,
        f"{label} protocol binding differs",
    )
    source_inventory = certificate["source_inventory_sha256"]
    _require(
        source_inventory is None or source_inventory == INVENTORY_SEMANTIC_ID,
        f"{label} source inventory binding differs",
    )
    _require(
        certificate["external_schema_registry_id"] == REGISTRY_ID,
        f"{label} registry binding differs",
    )
    _require(
        certificate["rule_literal_authority_sha256"] == LITERAL_AUTHORITY_RAW_SHA256,
        f"{label} literal-authority binding differs",
    )
    manifest_id = _require_sha256(
        certificate["maximum_context_object_manifest_id"],
        label=f"{label} context-manifest ID",
    )
    constraint_scope_id = _require_sha256(
        certificate["constraint_scope_id"], label=f"{label} constraint-scope ID"
    )
    _require(
        certificate["measured_type_name"] == expected_type_name
        and certificate["alternative_name"] == expected_alternative_name,
        f"{label} measured type/alternative differs",
    )
    expected_scope_id = _semantic_id(
        CONSTRAINT_SCOPE_DOMAIN,
        {
            "constraint_scope": expected_constraint_scope,
            "measured_type_name": expected_type_name,
            "alternative_name": expected_alternative_name,
            "measurement_binding": expected_measurement_binding,
            "constraint_scope_profile_id": expected_profile_id,
            "external_schema_registry_id": REGISTRY_ID,
            "rule_literal_authority_sha256": LITERAL_AUTHORITY_RAW_SHA256,
            "maximum_protocol_sha256": maximum_protocol_sha256,
            "source_inventory_sha256": (
                None if expected_profile_id is None else INVENTORY_SEMANTIC_ID
            ),
            "evaluation_semantics": (
                "FULL_GRAPH_EXACT_IJSON_INTRINSIC_DEPENDENCY_POSTORDER_THEN_"
                "LEXICAL_APPLICATION_NAME_THEN_INVOCATION_ORDINAL_V1"
            ),
        },
        resource_meter=meter,
    )
    _require(
        constraint_scope_id == expected_scope_id,
        f"{label} independently rebuilt constraint-scope ID differs",
    )
    context_manifest = _validate_pilot_context_manifest(
        proof_context_manifest,
        maximum_protocol_sha256=maximum_protocol_sha256,
        validated_inventory=validated_inventory,
        validated_registry=validated_registry,
        validated_max64_context_authority=validated_max64_context_authority,
        label=f"{label} proof-context manifest",
        resource_meter=meter,
    )
    _require(
        context_manifest.manifest["maximum_context_object_manifest_id"] == manifest_id,
        f"{label} proof-context manifest identity differs",
    )
    _require(
        certificate["objective_version"]
        == "MAX_BYTES_THEN_MIN_MEASURED_PRIMITIVES_THEN_MIN_CONTEXT_PRIMITIVES_V1"
        and certificate["proof_plan_version"]
        == "TOPDOWN_BUDGET_THEN_DESCRIPTOR_POSTORDER_RULE_APPLICATION_MAX_SLICE_PREFIX_V1",
        f"{label} objective/plan version differs",
    )
    _validate_frontier_encoding_version(
        certificate["frontier_encoding_version"],
        label=f"{label} frontier encoding version",
    )
    nodes, _ = _validate_proof_dag_metered(
        certificate["ordered_proof_nodes"],
        maximum_protocol_sha256=maximum_protocol_sha256,
        proof_scope_authority_id=constraint_scope_id,
        proof_context_authority_id=manifest_id,
        label=f"{label} proof DAG",
        resource_meter=meter,
        validated_inventory=validated_inventory,
        validated_registry=validated_registry,
    )
    node_count = len(nodes)
    _require(
        certificate["root_proof_node_position"] == node_count
        and nodes[-1]["proof_node_kind"] == "CODEC_INTERSECTION_ATTAINMENT",
        f"{label} root is not the last codec-attainment node",
    )
    measured_root_position = _require_integer(
        certificate["measured_choice_root_proof_node_position"],
        label=f"{label} measured-choice root",
        minimum=1,
        maximum=node_count,
    )
    context_root_position = certificate["context_choice_root_proof_node_position"]
    _require(
        context_root_position is None or type(context_root_position) is int,
        f"{label} context-choice root scalar kind differs",
    )
    if context_root_position is not None:
        _require_integer(
            context_root_position,
            label=f"{label} context-choice root",
            minimum=1,
            maximum=node_count,
        )
    maximum = _require_integer(
        certificate["certified_analytic_maximum_octets"],
        label=f"{label} certified maximum",
    )
    root = nodes[-1]
    root_derivation = root["derivation"]
    root_commitment = root["frontier_commitment"]
    _require(
        root_derivation["certified_upper_bound_octets"] == maximum
        and root_derivation["attaining_witness_canonical_byte_length"] == maximum
        and root_commitment["maximum_attainable_octets"] == maximum,
        f"{label} root maximum/attainment equality differs",
    )
    measured_digest = _require_sha256(
        certificate["winning_measured_choice_vector_sha256"],
        label=f"{label} measured winner digest",
    )
    context_digest = _require_sha256(
        certificate["winning_context_choice_vector_sha256"],
        label=f"{label} context winner digest",
    )
    _require(
        root_commitment["least_measured_choice_vector_sha256_at_maximum"]
        == measured_digest
        and root_commitment["least_context_choice_vector_sha256_at_maximum"]
        == context_digest,
        f"{label} root winner digests differ",
    )
    _require(
        nodes[measured_root_position - 1]["frontier_commitment"][
            "least_measured_choice_vector_sha256_at_maximum"
        ]
        == measured_digest,
        f"{label} measured-choice root digest differs",
    )
    if context_root_position is not None:
        _require(
            nodes[context_root_position - 1]["frontier_commitment"][
                "least_context_choice_vector_sha256_at_maximum"
            ]
            == context_digest,
            f"{label} context-choice root digest differs",
        )
    _require(
        (expected_profile_id is None) == (source_inventory is None),
        f"{label} inventory/profile binding nullability differs",
    )
    if lexical_resource_summary is not None:
        _validate_lexical_resource_summary(
            lexical_resource_summary,
            producer_claim=producer_claim,
            meter=meter,
            label=label,
        )
    _require_certificate_semantic_resource_accounting_complete()
    solved = _finalize_upper_bound_certificate_resource_claim(
        certificate,
        meter=meter,
    )
    if lexical_resource_summary is not None:
        _require(
            lexical_resource_summary["certificate_canonical_octets"]
            == solved.certificate_canonical_octets,
            f"{label} finalized certificate length differs from lexical predecode",
        )
    return solved.certificate, meter.snapshot()


def _measurement_binding(
    binding_kind: str,
    root_type_name: str,
    *,
    path: list[str] | None = None,
    sequence_name: str | None = None,
    sequence_ordinal: int | None = None,
) -> dict[str, Any]:
    return {
        "binding_kind": binding_kind,
        "validation_root_type_name": root_type_name,
        "measured_value_typed_member_path": [] if path is None else path,
        "sequence_binding_name": sequence_name,
        "sequence_ordinal": sequence_ordinal,
    }


def _expected_pilot_bindings(
    selected_profiles: dict[int, dict[str, Any]],
) -> tuple[dict[str, Any], ...]:
    return (
        {
            "type_name": "CapacityMeasurementBoolValueV1",
            "alternative_name": None,
            "constraint_scope": "INTRINSIC_TYPE",
            "constraint_scope_profile_id": None,
            "profile_position": None,
            "measurement_binding": _measurement_binding(
                "SELF_RECORD", "CapacityMeasurementBoolValueV1"
            ),
            "pilot_domain_kind": "FULL_FROZEN_SCOPE",
        },
        {
            "type_name": "CapacityMeasurementOperationResultBody",
            "alternative_name": "LOCAL_SHUTDOWN_RESULT_EVIDENCE_V2",
            "constraint_scope": "INTRINSIC_TYPE",
            "constraint_scope_profile_id": None,
            "profile_position": None,
            "measurement_binding": _measurement_binding(
                "OWNER_MEMBER_UNION_VALUE",
                "CapacityMeasurementOperationResultEvidence",
                path=["result"],
            ),
            "pilot_domain_kind": "FULL_FROZEN_SCOPE",
        },
        {
            "type_name": "CapacityMeasurementVocabularyDefinitionV1",
            "alternative_name": None,
            "constraint_scope": "INTRINSIC_TYPE",
            "constraint_scope_profile_id": None,
            "profile_position": None,
            "measurement_binding": _measurement_binding(
                "SELF_RECORD", "CapacityMeasurementVocabularyDefinitionV1"
            ),
            "pilot_domain_kind": "FULL_FROZEN_SCOPE",
        },
        {
            "type_name": "CapacityMeasurementOperationResultEvidence",
            "alternative_name": None,
            "constraint_scope": "FROZEN_FIXTURE",
            "constraint_scope_profile_id": selected_profiles[3][
                "maximum_constraint_scope_profile_id"
            ],
            "profile_position": 3,
            "measurement_binding": _measurement_binding(
                "OUTER_RESULT_RECORD",
                "CapacityMeasurementOperationResultEvidence",
            ),
            "pilot_domain_kind": "FULL_FROZEN_SCOPE",
        },
        {
            "type_name": "TargetObservationV2",
            "alternative_name": None,
            "constraint_scope": "FROZEN_ROOT_APPLICATION",
            "constraint_scope_profile_id": selected_profiles[369][
                "maximum_constraint_scope_profile_id"
            ],
            "profile_position": 369,
            "measurement_binding": _measurement_binding(
                "ROOT_EXACT_CHECKPOINT_OBSERVATION",
                "TargetObservationRootV2",
                sequence_name="observations",
                sequence_ordinal=64,
            ),
            "pilot_domain_kind": "FULL_FROZEN_SCOPE",
        },
        {
            "type_name": "TargetObservationV2",
            "alternative_name": None,
            "constraint_scope": "FROZEN_ROOT_APPLICATION",
            "constraint_scope_profile_id": None,
            "profile_position": None,
            "measurement_binding": _measurement_binding(
                "ROOT_EXACT_CHECKPOINT_OBSERVATION",
                "TargetObservationRootV2",
                sequence_name="observations",
                sequence_ordinal=64,
            ),
            "pilot_domain_kind": "FULL_FROZEN_SCOPE",
        },
    )


def _validate_producer_resource_measurement(
    value: Any,
    *,
    certificate: dict[str, Any] | None,
    label: str,
    expected_leaf_resources: Mapping[str, int] | None = None,
) -> dict[str, int]:
    measurement = _require_exact_keys(value, PRODUCER_RESOURCE_KEYS, label=label)
    for name, item in measurement.items():
        _require_integer(item, label=f"{label} {name}")
    _require(
        measurement["resolved_context_object_count"]
        <= measurement["resolved_context_reference_count"],
        f"{label} object count exceeds references",
    )
    _require(
        measurement["deduplicated_context_reference_count"]
        == measurement["resolved_context_reference_count"]
        - measurement["resolved_context_object_count"],
        f"{label} deduplicated-reference arithmetic differs",
    )
    _require(
        measurement["maximum_context_object_octets"]
        <= measurement["resolved_context_object_octets"],
        f"{label} maximum context object exceeds their total",
    )
    if certificate is not None:
        for name in PROOF_RESOURCE_KEYS:
            _require(
                measurement[name] == certificate["proof_resource_claim"][name],
                f"{label} certificate resource {name} differs",
            )
        _require(
            measurement["certificate_pretty_octets"]
            == _pretty_octet_length(certificate),
            f"{label} certificate pretty-byte count differs",
        )
    if expected_leaf_resources is not None:
        expected_keys = PRODUCER_RESOURCE_KEYS - PROOF_RESOURCE_KEYS
        _require(
            frozenset(expected_leaf_resources) == expected_keys,
            f"{label} internally derived leaf-resource keys differ",
        )
        for name, expected in expected_leaf_resources.items():
            _require_integer(
                expected,
                label=f"{label} internally derived {name}",
            )
            _require(
                measurement[name] == expected,
                f"{label} {name} differs from the retained leaf",
            )
    return measurement


def _derive_pilot_leaf_nonproof_resources(
    leaf: ValidatedPilotLeaf,
    *,
    case_binding: dict[str, Any],
    ordered_component_choice_evidence: Any,
    certificate: dict[str, Any],
    label: str,
) -> dict[str, int]:
    """Recompute every non-proof producer metric from one retained leaf."""

    choice_evidence = _require_array(
        ordered_component_choice_evidence,
        label=f"{label} component choice evidence",
        maximum_length=1_000_000,
    )
    _require(type(certificate) is dict, f"{label} certificate must be an object")
    _require_exact_keys(case_binding, CASE_BINDING_KEYS, label=f"{label} binding")
    context_object_count = len(leaf.resolved_context_object_ids)
    _require(
        context_object_count == len(leaf.context_manifest.resolved_entries)
        and context_object_count <= leaf.resolved_context_reference_count,
        f"{label} retained context cardinality differs",
    )
    row_projection = {
        "case_binding": case_binding,
        "pilot_context_manifest": leaf.context_manifest.manifest,
        "pilot_witness_record": leaf.witness_record,
        "pilot_scope_witness_context": leaf.scope_witness_context,
        "ordered_component_choice_evidence": choice_evidence,
        "pilot_upper_bound_certificate": certificate,
    }
    row_pretty_octets = _pretty_octet_length(row_projection)
    total_staged_raw_octets = _require_integer(
        row_pretty_octets + leaf.resolved_context_object_octets,
        label=f"{label} total staged raw octets",
    )
    return {
        "resolved_context_reference_count": leaf.resolved_context_reference_count,
        "resolved_context_object_count": context_object_count,
        "deduplicated_context_reference_count": (
            leaf.resolved_context_reference_count - context_object_count
        ),
        "resolved_context_object_octets": leaf.resolved_context_object_octets,
        "maximum_context_object_octets": leaf.maximum_context_object_octets,
        "observation_count": leaf.observation_count,
        "application_invocation_count": leaf.application_invocation_count,
        "charged_cross_rule_evaluation_count": (
            leaf.charged_cross_rule_evaluation_count
        ),
        "direct_cross_expression_node_count": (leaf.direct_cross_expression_node_count),
        "row_pretty_octets": row_pretty_octets,
        "choice_evidence_pretty_octets": _pretty_octet_length(choice_evidence),
        "certificate_pretty_octets": _pretty_octet_length(certificate),
        "total_staged_raw_octets": total_staged_raw_octets,
    }


def _validate_pilot_cases(
    value: Any,
    *,
    maximum_protocol_sha256: str,
    selected_profiles: dict[int, dict[str, Any]],
    validated_inventory: dict[str, Any],
    validated_registry: dict[str, Any],
    validated_max64_context_authority: dict[str, Any],
    label: str,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, int]]]:
    case_values = _require_array(value, label=label, exact_length=6)
    expected_bindings = _expected_pilot_bindings(selected_profiles)
    cases: list[dict[str, Any]] = []
    measurements: dict[str, dict[str, int]] = {}
    for position, (case_value, expected_binding) in enumerate(
        zip(case_values, expected_bindings, strict=True), 1
    ):
        case_label = f"{label} case {position}"
        case = _require_exact_keys(case_value, PILOT_CASE_KEYS, label=case_label)
        _require(case["case_position"] == position, f"{case_label} position differs")
        case_id = PILOT_CASE_NAMES[position - 1]
        _require(case["case_id"] == case_id, f"{case_label} case ID differs")
        binding = _require_exact_keys(
            case["case_binding"], CASE_BINDING_KEYS, label=f"{case_label} binding"
        )
        _validate_measurement_binding(
            binding["measurement_binding"], label=f"{case_label} measurement binding"
        )
        _require(binding == expected_binding, f"{case_label} frozen binding differs")
        outcomes = _require_array(
            case["ordered_outcome_subrecords"],
            label=f"{case_label} outcomes",
            exact_length=4 if position == 6 else 0,
        )
        if position != 6:
            profile_position = binding["profile_position"]
            expected_profile = (
                None
                if profile_position is None
                else selected_profiles[profile_position]
            )
            leaf = _validate_pilot_retained_leaf(
                pilot_context_manifest=case["pilot_context_manifest"],
                pilot_witness_record=case["pilot_witness_record"],
                pilot_scope_witness_context=case["pilot_scope_witness_context"],
                maximum_protocol_sha256=maximum_protocol_sha256,
                expected_type_name=binding["type_name"],
                expected_alternative_name=binding["alternative_name"],
                expected_constraint_scope=binding["constraint_scope"],
                expected_measurement_binding=binding["measurement_binding"],
                expected_profile=expected_profile,
                validated_inventory=validated_inventory,
                validated_registry=validated_registry,
                validated_max64_context_authority=(validated_max64_context_authority),
                label=f"{case_label} retained leaf",
                resource_meter=ProofResourceMeter(phase=SEED_CAP_DERIVATION_PHASE),
            )
            certificate, _ = _validate_certificate(
                case["pilot_upper_bound_certificate"],
                maximum_protocol_sha256=maximum_protocol_sha256,
                proof_context_manifest=case["pilot_context_manifest"],
                validated_inventory=validated_inventory,
                validated_registry=validated_registry,
                validated_max64_context_authority=(validated_max64_context_authority),
                expected_type_name=binding["type_name"],
                expected_alternative_name=binding["alternative_name"],
                expected_constraint_scope=binding["constraint_scope"],
                expected_measurement_binding=binding["measurement_binding"],
                expected_profile_id=binding["constraint_scope_profile_id"],
                label=f"{case_label} certificate",
            )
            expected_leaf_resources = _derive_pilot_leaf_nonproof_resources(
                leaf,
                case_binding=binding,
                ordered_component_choice_evidence=(
                    case["ordered_component_choice_evidence"]
                ),
                certificate=certificate,
                label=f"{case_label} retained leaf",
            )
            measurement = _validate_producer_resource_measurement(
                case["producer_resource_measurement"],
                certificate=certificate,
                label=f"{case_label} resource measurement",
                expected_leaf_resources=expected_leaf_resources,
            )
        else:
            _require(
                case["pilot_context_manifest"] is None
                and case["pilot_witness_record"] is None
                and case["pilot_scope_witness_context"] is None
                and case["ordered_component_choice_evidence"] == []
                and case["pilot_upper_bound_certificate"] is None,
                f"{case_label} top-level retained leaf must be null/empty",
            )
            outcome_measurements: list[dict[str, int]] = []
            for outcome_position, outcome_value in enumerate(outcomes, 1):
                outcome_label = f"{case_label} outcome {outcome_position}"
                outcome = _require_exact_keys(
                    outcome_value, PILOT_OUTCOME_KEYS, label=outcome_label
                )
                expected_profile_position = 369 + outcome_position
                expected_outcome = CHECKPOINT_OUTCOMES[outcome_position]
                expected_profile = selected_profiles[expected_profile_position]
                _require(
                    outcome["outcome_position"] == outcome_position
                    and outcome["checkpoint_outcome"] == expected_outcome
                    and outcome["profile_position"] == expected_profile_position
                    and outcome["constraint_scope_profile_id"]
                    == expected_profile["maximum_constraint_scope_profile_id"],
                    f"{outcome_label} frozen outcome/profile differs",
                )
                leaf = _validate_pilot_retained_leaf(
                    pilot_context_manifest=outcome["pilot_context_manifest"],
                    pilot_witness_record=outcome["pilot_witness_record"],
                    pilot_scope_witness_context=(
                        outcome["pilot_scope_witness_context"]
                    ),
                    maximum_protocol_sha256=maximum_protocol_sha256,
                    expected_type_name=binding["type_name"],
                    expected_alternative_name=None,
                    expected_constraint_scope=binding["constraint_scope"],
                    expected_measurement_binding=binding["measurement_binding"],
                    expected_profile=expected_profile,
                    validated_inventory=validated_inventory,
                    validated_registry=validated_registry,
                    validated_max64_context_authority=(
                        validated_max64_context_authority
                    ),
                    label=f"{outcome_label} retained leaf",
                    resource_meter=ProofResourceMeter(phase=SEED_CAP_DERIVATION_PHASE),
                )
                certificate, _ = _validate_certificate(
                    outcome["pilot_upper_bound_certificate"],
                    maximum_protocol_sha256=maximum_protocol_sha256,
                    proof_context_manifest=outcome["pilot_context_manifest"],
                    validated_inventory=validated_inventory,
                    validated_registry=validated_registry,
                    validated_max64_context_authority=(
                        validated_max64_context_authority
                    ),
                    expected_type_name=binding["type_name"],
                    expected_alternative_name=None,
                    expected_constraint_scope=binding["constraint_scope"],
                    expected_measurement_binding=binding["measurement_binding"],
                    expected_profile_id=outcome["constraint_scope_profile_id"],
                    label=f"{outcome_label} certificate",
                )
                expected_leaf_resources = _derive_pilot_leaf_nonproof_resources(
                    leaf,
                    case_binding=binding,
                    ordered_component_choice_evidence=(
                        outcome["ordered_component_choice_evidence"]
                    ),
                    certificate=certificate,
                    label=f"{outcome_label} retained leaf",
                )
                outcome_measurement = _validate_producer_resource_measurement(
                    outcome["producer_resource_measurement"],
                    certificate=certificate,
                    label=f"{outcome_label} resource measurement",
                    expected_leaf_resources=expected_leaf_resources,
                )
                unsigned_outcome = {
                    name: item
                    for name, item in outcome.items()
                    if name != "pilot_outcome_subrecord_id"
                }
                _require(
                    outcome["pilot_outcome_subrecord_id"]
                    == _semantic_id(PILOT_OUTCOME_DOMAIN, unsigned_outcome),
                    f"{outcome_label} semantic identity differs",
                )
                outcome_measurements.append(outcome_measurement)
            measurement = _validate_producer_resource_measurement(
                case["producer_resource_measurement"],
                certificate=None,
                label=f"{case_label} resource measurement",
            )
            expected_componentwise = {
                name: max(item[name] for item in outcome_measurements)
                for name in PRODUCER_RESOURCE_KEYS
            }
            _require(
                measurement == expected_componentwise,
                f"{case_label} resource measurement is not componentwise maximum",
            )
        unsigned_case = {
            name: item for name, item in case.items() if name != "pilot_case_id"
        }
        _require(
            case["pilot_case_id"] == _semantic_id(PILOT_CASE_DOMAIN, unsigned_case),
            f"{case_label} semantic identity differs",
        )
        cases.append(case)
        measurements[case_id] = measurement
    return cases, measurements


def _pilot_phase_invariant_projection(value: Any) -> Any:
    """Apply the frozen recursive seed/final phase-invariant projection."""

    if type(value) is dict:
        return {
            name: _pilot_phase_invariant_projection(item)
            for name, item in value.items()
            if not name.endswith(("_id", "_ids", "_sha256"))
            and name
            not in {
                "pilot_phase",
                "seed_protocol_raw_octet_count",
                "seed_artifact_raw_octet_count",
            }
        }
    if type(value) is list:
        return [_pilot_phase_invariant_projection(item) for item in value]
    return value


def _validate_pilot_root_envelope(
    value: Any,
    *,
    expected_pilot_phase: str,
    maximum_protocol_sha256: str,
    label: str,
) -> dict[str, Any]:
    """Validate the pilot root envelope before any expensive leaf semantics."""

    _require_sha256(maximum_protocol_sha256, label=f"{label} protocol SHA")
    pilot = _require_exact_keys(value, PILOT_ROOT_KEYS, label=label)
    _require(
        pilot["artifact_version"] == PILOT_VERSION
        and pilot["canonicalization_version"] == CANONICALIZATION_VERSION
        and pilot["measurement_schema_version"] == MEASUREMENT_SCHEMA_VERSION
        and pilot["pilot_phase"] == expected_pilot_phase
        and pilot["maximum_protocol_sha256"] == maximum_protocol_sha256,
        f"{label} version/phase/protocol envelope differs",
    )
    _require(
        pilot["source_inventory_sha256"] == INVENTORY_SEMANTIC_ID
        and pilot["external_schema_registry_id"] == REGISTRY_ID
        and pilot["rule_literal_authority_sha256"] == LITERAL_AUTHORITY_RAW_SHA256
        and pilot["application_witness_raw_sha256"] == APPLICATION_WITNESS_RAW_SHA256
        and pilot["max64_context_authority_raw_sha256"]
        == MAX64_CONTEXT_AUTHORITY_RAW_SHA256,
        f"{label} authority envelope differs",
    )
    if expected_pilot_phase == SEED_CAP_DERIVATION_PHASE:
        _require(
            pilot["seed_protocol_sha256"] is None
            and pilot["seed_protocol_raw_octet_count"] is None
            and pilot["seed_artifact_raw_octet_count"] is None
            and pilot["seed_artifact_raw_sha256"] is None,
            f"{label} seed phase carries final-rebind pins",
        )
    else:
        _require(
            expected_pilot_phase == FINAL_PROTOCOL_REBIND_PHASE,
            f"{label} pilot phase differs",
        )
        _require_sha256(
            pilot["seed_protocol_sha256"],
            label=f"{label} seed protocol SHA",
        )
        _require_integer(
            pilot["seed_protocol_raw_octet_count"],
            label=f"{label} seed protocol octets",
            minimum=1,
        )
        _require_integer(
            pilot["seed_artifact_raw_octet_count"],
            label=f"{label} seed artifact octets",
            minimum=1,
        )
        _require_sha256(
            pilot["seed_artifact_raw_sha256"],
            label=f"{label} seed artifact SHA",
        )
    _require_array(
        pilot["ordered_pilot_case_records"],
        label=f"{label} pilot cases",
        exact_length=6,
    )
    _require(
        type(pilot["local_shutdown_minimality_pilot_record"]) is dict,
        f"{label} local-shutdown pilot record is not structured",
    )
    _require_array(
        pilot["ordered_row_preflight_records"],
        label=f"{label} row preflights",
        exact_length=474,
    )
    _require(
        type(pilot["local_shutdown_minimality_preflight_record"]) is dict,
        f"{label} local-shutdown preflight is not structured",
    )
    _require_array(
        pilot["metric_rounding_catalog"],
        label=f"{label} metric rounding catalog",
        exact_length=len(METRIC_NAMES),
    )
    _require_exact_keys(
        pilot["derived_resource_ceiling_record"],
        CAP_RECORD_KEYS,
        label=f"{label} derived resource ceilings",
    )
    phase_payload = {
        name: item
        for name, item in pilot.items()
        if name not in {"phase_invariant_payload_sha256", "maximum_protocol_pilot_id"}
    }
    expected_phase_digest = _canonical_sha256_stream(
        _pilot_phase_invariant_projection(phase_payload)
    )
    _require(
        pilot["phase_invariant_payload_sha256"] == expected_phase_digest,
        f"{label} phase-invariant payload SHA differs",
    )
    pilot_payload = {
        name: item
        for name, item in pilot.items()
        if name != "maximum_protocol_pilot_id"
    }
    _require(
        pilot["maximum_protocol_pilot_id"] == _semantic_id(PILOT_DOMAIN, pilot_payload),
        f"{label} semantic identity differs",
    )
    return pilot


RESOURCE_METRIC_FIELD: Final = {
    "PROOF_NODE_COUNT_PER_CERTIFICATE": "proof_node_count",
    "PROOF_EDGE_COUNT_PER_CERTIFICATE": "proof_edge_count",
    "MAXIMUM_PROOF_DEPTH_PER_CERTIFICATE": "maximum_proof_depth",
    "MAXIMUM_CHILD_COUNT_PER_NODE": "maximum_child_count",
    "MAXIMUM_STATE_SIGNATURE_DIMENSION_COUNT_PER_NODE": (
        "maximum_state_signature_dimension_count"
    ),
    "STATE_CATALOG_ENTRY_COUNT_PER_CERTIFICATE": "state_catalog_entry_count",
    "STATE_CATALOG_CANONICALIZED_OCTETS_PER_CERTIFICATE": (
        "state_catalog_canonicalized_octets"
    ),
    "PEAK_RETAINED_STATE_CATALOG_OCTETS_PER_CERTIFICATE": (
        "peak_retained_state_catalog_octets"
    ),
    "FRONTIER_STATE_ENTRY_COUNT_PER_CERTIFICATE": "frontier_state_entry_count",
    "FRONTIER_BITMAP_RUN_COUNT_PER_CERTIFICATE": "frontier_bitmap_run_count",
    "EXPANDED_FRONTIER_POINT_COUNT_PER_CERTIFICATE": ("frontier_expanded_point_count"),
    "MAXIMUM_LIVE_FRONTIER_WIDTH": "maximum_frontier_width",
    "PEAK_RETAINED_FRONTIER_OCTETS_PER_CERTIFICATE": ("peak_retained_frontier_octets"),
    "FRONTIER_TRANSITION_COUNT_PER_CERTIFICATE": "frontier_transition_count",
    "FRONTIER_CANONICALIZED_OCTETS_PER_CERTIFICATE": ("frontier_canonicalized_octets"),
    "HASH_PREIMAGE_OCTETS_PER_CERTIFICATE": "hash_preimage_octets",
    "COMPONENT_CHOICE_COORDINATE_COUNT_PER_ROW": ("component_choice_coordinate_count"),
    "CERTIFICATE_CANONICAL_OCTETS": "certificate_canonical_octets",
    "MAXIMUM_ROW_RAW_OCTETS": "row_pretty_octets",
    "AGGREGATE_CONTEXT_OBJECT_COMPACT_OCTETS": "resolved_context_object_octets",
    "AGGREGATE_ROW_RAW_OCTETS": "row_pretty_octets",
    "AGGREGATE_COMPLETE_ARTIFACT_RAW_OCTETS": "total_staged_raw_octets",
}


def _checked_uint128(value: int, *, label: str) -> int:
    _require(
        type(value) is int and 0 <= value <= UINT128_MAXIMUM,
        f"{label} exceeds checked UInt128",
    )
    return value


def _validate_dimension_vector(value: Any, *, label: str) -> dict[str, Any]:
    vector = _require_exact_keys(value, DIMENSION_VECTOR_KEYS, label=label)
    for name, item in vector.items():
        if name == "owner_codec_octet_limit":
            _require(
                item is None or type(item) is int,
                f"{label} owner codec limit has the wrong scalar kind",
            )
            if item is not None:
                _require_integer(item, label=f"{label} owner codec limit")
        else:
            _require_integer(item, label=f"{label} {name}")
    _require(
        vector["measured_codec_octet_limit"] > 0,
        f"{label} measured codec limit must be positive",
    )
    return vector


def _validate_symbolic_bound_nodes(
    value: Any,
    *,
    dimensions: dict[str, Any],
    label: str,
) -> tuple[list[dict[str, Any]], list[int]]:
    node_values = _require_array(value, label=label, maximum_length=1_000_000)
    nodes: list[dict[str, Any]] = []
    computed: list[int] = []
    for position, node_value in enumerate(node_values, 1):
        node = _require_exact_keys(
            node_value,
            SYMBOLIC_BOUND_NODE_KEYS,
            label=f"{label} node {position}",
        )
        _require(
            node["bound_node_position"] == position,
            f"{label} positions differ",
        )
        operator = node["bound_operator"]
        _require(
            operator
            in {"LITERAL", "DIMENSION", "ADD", "MULTIPLY", "MAXIMUM", "CEILING_DIVIDE"},
            f"{label} operator differs",
        )
        literal = node["literal_value"]
        dimension_name = node["dimension_name"]
        operands = _require_array(
            node["ordered_operand_positions"],
            label=f"{label} operands {position}",
            maximum_length=1_000_000,
        )
        for operand_ordinal, operand in enumerate(operands, 1):
            _require_integer(
                operand,
                label=f"{label} operand {position}:{operand_ordinal}",
                minimum=1,
                maximum=position - 1,
            )
        if operator == "LITERAL":
            _require(
                type(literal) is int and dimension_name is None and not operands,
                f"{label} literal-node shape differs",
            )
            result = _checked_uint128(literal, label=f"{label} literal {position}")
        elif operator == "DIMENSION":
            _require(
                literal is None
                and type(dimension_name) is str
                and dimension_name in DIMENSION_VECTOR_KEYS
                and not operands,
                f"{label} dimension-node shape differs",
            )
            dimension_value = dimensions[dimension_name]
            _require(
                dimension_value is not None,
                f"{label} cannot use null dimension {dimension_name}",
            )
            result = dimension_value
        else:
            _require(
                literal is None and dimension_name is None,
                f"{label} operator scalar fields must be null",
            )
            if operator == "CEILING_DIVIDE":
                _require(len(operands) == 2, f"{label} ceiling-divide arity differs")
                numerator = computed[operands[0] - 1]
                denominator = computed[operands[1] - 1]
                _require(denominator > 0, f"{label} ceiling-divide denominator is zero")
                result = (numerator + denominator - 1) // denominator
            else:
                _require(len(operands) >= 2, f"{label} operator arity differs")
                operand_values = [computed[item - 1] for item in operands]
                if operator == "ADD":
                    result = sum(operand_values)
                elif operator == "MULTIPLY":
                    result = 1
                    for item in operand_values:
                        result *= item
                else:
                    result = max(operand_values)
            result = _checked_uint128(result, label=f"{label} result {position}")
        _require(
            result <= SAFE_INTEGER_MAXIMUM,
            f"{label} published node {position} exceeds safe integer",
        )
        _require(
            node["computed_value"] == result, f"{label} node {position} result differs"
        )
        nodes.append(node)
        computed.append(result)
    return nodes, computed


def _validate_metric_bounds(
    value: Any,
    *,
    bound_source_kind: str,
    source_case_ids: list[str],
    source_measurements: dict[str, dict[str, int]],
    symbolic_nodes: list[dict[str, Any]],
    symbolic_values: list[int],
    label: str,
) -> list[dict[str, Any]]:
    bounds = _require_array(value, label=label, exact_length=len(METRIC_NAMES))
    roots: set[int] = set()
    for position, (bound_value, metric_name) in enumerate(
        zip(bounds, METRIC_NAMES, strict=True), 1
    ):
        bound = _require_exact_keys(
            bound_value,
            METRIC_BOUND_KEYS,
            label=f"{label} item {position}",
        )
        _require(
            bound["metric_position"] == position
            and bound["metric_name"] == metric_name,
            f"{label} metric position/name differs",
        )
        derived = _require_integer(
            bound["derived_upper_bound"], label=f"{label} derived bound {position}"
        )
        formula = bound["bound_formula_id"]
        _require(formula in BOUND_FORMULA_IDS, f"{label} formula differs")
        root = bound["symbolic_bound_root_position"]
        if formula == "PILOT_COMPONENTWISE_MAX_V1":
            _require(
                root is None and bool(source_case_ids),
                f"{label} pilot formula root/source differs",
            )
            field = RESOURCE_METRIC_FIELD[metric_name]
            expected = max(
                source_measurements[case_id][field] for case_id in source_case_ids
            )
        else:
            _require(
                bound_source_kind == "SYMBOLIC_LOOP_BOUND" and type(root) is int,
                f"{label} symbolic formula/root differs",
            )
            root = _require_integer(
                root,
                label=f"{label} symbolic root {position}",
                minimum=1,
                maximum=len(symbolic_nodes),
            )
            roots.add(root)
            expected = symbolic_values[root - 1]
        _require(derived == expected, f"{label} derived bound {position} differs")
        ceiling = _require_integer(
            bound["rounded_ceiling"], label=f"{label} rounded ceiling {position}"
        )
        slack = _require_integer(
            bound["ceiling_slack"], label=f"{label} ceiling slack {position}"
        )
        _require(
            ceiling >= derived and slack == ceiling - derived,
            f"{label} ceiling/slack arithmetic differs",
        )
    if symbolic_nodes:
        reachable: set[int] = set()
        pending = list(roots)
        while pending:
            position = pending.pop()
            if position in reachable:
                continue
            reachable.add(position)
            pending.extend(symbolic_nodes[position - 1]["ordered_operand_positions"])
        _require(
            reachable == set(range(1, len(symbolic_nodes) + 1)),
            f"{label} symbolic DAG has unreachable nodes",
        )
    return bounds


def _validate_row_dimension_bindings(
    vector: dict[str, Any],
    *,
    row: RowPlan,
    registry: dict[str, Any],
    inventory: dict[str, Any],
    scope_hierarchy_by_profile_id: Mapping[str, DerivedScopeHierarchy] | None = None,
    label: str,
) -> None:
    descriptor_by_name = {
        item["type_name"]: item
        for item in registry["ordered_external_type_descriptors"]
    }
    descriptor = descriptor_by_name[row.type_name]
    _require(
        vector["measured_codec_octet_limit"] == descriptor["codec_octet_limit"],
        f"{label} measured codec limit differs",
    )
    owner_limit: int | None = None
    if descriptor["type_form"] == "TAGGED_UNION":
        union = descriptor["tagged_union_descriptor"]
        if union["payload_binding_scope"] == "OWNER_MEMBER":
            owner = descriptor_by_name[union["payload_owner_type_name"]]
            owner_limit = owner["codec_octet_limit"]
    _require(
        vector["owner_codec_octet_limit"] == owner_limit,
        f"{label} owner codec limit differs",
    )
    if row.constraint_scope_profile_id is None:
        expected = {
            "context_record_reference_count": 1 if owner_limit is not None else 0,
            "observation_count": 0,
            "application_invocation_count": 0,
            "charged_cross_rule_evaluation_count": 0,
            "direct_cross_expression_node_count": 0,
        }
    else:
        if scope_hierarchy_by_profile_id is None:
            profiles = inventory["operation_contracts"][
                "maximum_constraint_scope_profile_catalog"
            ]
            matching_profiles = [
                item
                for item in profiles
                if item["maximum_constraint_scope_profile_id"]
                == row.constraint_scope_profile_id
            ]
            _require(
                len(matching_profiles) == 1,
                f"{label} scope profile does not resolve uniquely",
            )
            hierarchy = _derive_profile_scope_hierarchy(
                matching_profiles[0],
                validated_inventory=inventory,
                label=f"{label} scope hierarchy",
            )
        else:
            _require(
                row.constraint_scope_profile_id in scope_hierarchy_by_profile_id,
                f"{label} scope hierarchy is absent",
            )
            hierarchy = scope_hierarchy_by_profile_id[row.constraint_scope_profile_id]
        expected = {
            "context_record_reference_count": (
                hierarchy.context_record_reference_count
            ),
            "observation_count": hierarchy.observation_count,
            "application_invocation_count": hierarchy.application_invocation_count,
            "charged_cross_rule_evaluation_count": (
                hierarchy.charged_cross_rule_evaluation_count
            ),
            "direct_cross_expression_node_count": (
                hierarchy.direct_cross_expression_node_count
            ),
        }
    for name, expected_value in expected.items():
        _require(vector[name] == expected_value, f"{label} {name} differs")


def _validate_bound_source_case_ids(value: Any, *, label: str) -> list[str]:
    case_ids = _require_array(value, label=label, maximum_length=6)
    _require(
        all(type(item) is str and item in PILOT_CASE_NAMES for item in case_ids),
        f"{label} contains an unknown pilot case ID",
    )
    _require(len(set(case_ids)) == len(case_ids), f"{label} contains duplicates")
    expected_order = sorted(case_ids, key=PILOT_CASE_NAMES.index)
    _require(case_ids == expected_order, f"{label} order differs")
    return case_ids


def _validate_dominance_entry_common(
    entry: dict[str, Any],
    *,
    source_measurements: dict[str, dict[str, int]],
    label: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    source_kind = entry["bound_source_kind"]
    _require(
        source_kind in {"PILOT_COMPONENTWISE_DOMINANCE", "SYMBOLIC_LOOP_BOUND"},
        f"{label} bound source kind differs",
    )
    source_case_ids = _validate_bound_source_case_ids(
        entry["ordered_bound_source_case_ids"], label=f"{label} source case IDs"
    )
    dimensions = _validate_dimension_vector(
        entry["dimension_vector"], label=f"{label} dimension vector"
    )
    symbolic_nodes, symbolic_values = _validate_symbolic_bound_nodes(
        entry["ordered_symbolic_bound_nodes"],
        dimensions=dimensions,
        label=f"{label} symbolic bound DAG",
    )
    if source_kind == "PILOT_COMPONENTWISE_DOMINANCE":
        _require(bool(source_case_ids), f"{label} has no dominating pilot")
        _require(not symbolic_nodes, f"{label} pilot mapping has a symbolic DAG")
    else:
        _require(bool(symbolic_nodes), f"{label} symbolic mapping has no DAG")
    bounds = _validate_metric_bounds(
        entry["ordered_metric_upper_bounds"],
        bound_source_kind=source_kind,
        source_case_ids=source_case_ids,
        source_measurements=source_measurements,
        symbolic_nodes=symbolic_nodes,
        symbolic_values=symbolic_values,
        label=f"{label} metric bounds",
    )
    return dimensions, bounds


def _validate_dominance_ledger(
    value: Any,
    *,
    rows: tuple[RowPlan, ...],
    source_measurements: dict[str, dict[str, int]],
    registry: dict[str, Any],
    inventory: dict[str, Any],
    label: str,
) -> tuple[list[dict[str, Any]], list[list[dict[str, Any]]]]:
    entry_values = _require_array(value, label=label, exact_length=474)
    scope_hierarchies = _derive_all_profile_scope_hierarchies(
        inventory,
        label=f"{label} scope authorities",
    )
    scope_hierarchy_by_profile_id = MappingProxyType(
        {
            hierarchy.constraint_scope_profile_id: hierarchy
            for hierarchy in scope_hierarchies
        }
    )
    _require(
        len(scope_hierarchy_by_profile_id) == 408,
        f"{label} scope hierarchy identities repeat",
    )
    entries: list[dict[str, Any]] = []
    all_bounds: list[list[dict[str, Any]]] = []
    for position, (entry_value, row) in enumerate(
        zip(entry_values, rows, strict=True), 1
    ):
        entry_label = f"{label} row {position}"
        entry = _require_exact_keys(entry_value, DOMINANCE_KEYS, label=entry_label)
        _require(
            entry["row_position"] == row.row_position
            and entry["row_kind"] == row.row_kind
            and entry["type_name"] == row.type_name
            and entry["alternative_name"] == row.alternative_name
            and entry["constraint_scope_profile_id"] == row.constraint_scope_profile_id,
            f"{entry_label} independently derived row binding differs",
        )
        dimensions, bounds = _validate_dominance_entry_common(
            entry,
            source_measurements=source_measurements,
            label=entry_label,
        )
        _validate_row_dimension_bindings(
            dimensions,
            row=row,
            registry=registry,
            inventory=inventory,
            scope_hierarchy_by_profile_id=scope_hierarchy_by_profile_id,
            label=f"{entry_label} dimension vector",
        )
        entries.append(entry)
        all_bounds.append(bounds)
    return entries, all_bounds


def _validate_local_shutdown_dominance(
    value: Any,
    *,
    source_measurements: dict[str, dict[str, int]],
    registry: dict[str, Any],
    label: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    entry = _require_exact_keys(value, LOCAL_SHUTDOWN_DOMINANCE_KEYS, label=label)
    _require(
        entry["counterexample_kind"] == "LOCAL_SHUTDOWN_UNREPRESENTABLE_MINIMALITY",
        f"{label} counterexample kind differs",
    )
    dimensions, bounds = _validate_dominance_entry_common(
        entry,
        source_measurements=source_measurements,
        label=label,
    )
    descriptor = next(
        item
        for item in registry["ordered_external_type_descriptors"]
        if item["type_name"] == "CapacityMeasurementOperationResultEvidence"
    )
    _require(
        dimensions["owner_codec_octet_limit"] is None
        and dimensions["measured_codec_octet_limit"] == descriptor["codec_octet_limit"],
        f"{label} codec dimensions differ",
    )
    return entry, bounds


def _validate_rounding_and_caps(
    rounding_value: Any,
    cap_value: Any,
    *,
    row_bounds: list[list[dict[str, Any]]],
    local_bounds: list[dict[str, Any]],
    label: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rounding = _require_array(
        rounding_value,
        label=f"{label} rounding catalog",
        exact_length=len(METRIC_NAMES),
    )
    caps = _require_exact_keys(cap_value, CAP_RECORD_KEYS, label=f"{label} caps")
    for position, (record_value, metric_name) in enumerate(
        zip(rounding, METRIC_NAMES, strict=True), 1
    ):
        record = _require_exact_keys(
            record_value,
            ROUNDING_KEYS,
            label=f"{label} rounding item {position}",
        )
        _require(
            record["metric_position"] == position
            and record["metric_name"] == metric_name,
            f"{label} rounding position/name differs",
        )
        unit = _require_integer(
            record["rounding_unit"],
            label=f"{label} rounding unit {position}",
            minimum=1,
        )
        measured = _require_integer(
            record["measured_pilot_maximum"],
            label=f"{label} measured pilot maximum {position}",
        )
        rounded = _require_integer(
            record["rounded_ceiling"],
            label=f"{label} rounded ceiling {position}",
        )
        slack = _require_integer(
            record["ceiling_slack"],
            label=f"{label} ceiling slack {position}",
        )
        _require(
            rounded % unit == 0 and rounded >= measured and slack == rounded - measured,
            f"{label} rounding arithmetic {position} differs",
        )
        cap_name = metric_name.lower()
        _require(caps[cap_name] == rounded, f"{label} cap {cap_name} differs")
    return rounding, caps


ERROR_PREFIX: Final = "Raw-V8 Step-2 maximum protocol error: "
NO_GO_REASON: Final = (
    "maximum protocol V1 pre-search plan exceeds immutable coordinate, "
    "proof-node, and proof-depth seed caps"
)


def _emit_no_go(payload: dict[str, Any]) -> None:
    report = {
        "acceptance_enabled": False,
        "component_status": COMPONENT_STATUS,
        "decision": "NO_GO",
        **payload,
    }
    sys.stderr.buffer.write(
        ERROR_PREFIX.encode("utf-8") + _canonical_bytes(report) + b"\n"
    )


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="repository root containing the frozen authorities",
    )
    parser.add_argument("--protocol", type=Path, default=Path(PROTOCOL_RELATIVE_PATH))
    parser.add_argument(
        "--correction", type=Path, default=Path(CORRECTION_RELATIVE_PATH)
    )
    parser.add_argument("--inventory", type=Path, default=Path(INVENTORY_RELATIVE_PATH))
    parser.add_argument("--registry", type=Path, default=Path(REGISTRY_RELATIVE_PATH))
    parser.add_argument(
        "--literal-authority",
        type=Path,
        default=Path(LITERAL_AUTHORITY_RELATIVE_PATH),
    )
    parser.add_argument(
        "--application-witness",
        type=Path,
        default=Path(APPLICATION_WITNESS_RELATIVE_PATH),
    )
    parser.add_argument(
        "--max64-context-authority",
        type=Path,
        default=Path(MAX64_CONTEXT_AUTHORITY_RELATIVE_PATH),
    )
    parser.add_argument("--pilot", type=Path, default=Path(PILOT_RELATIVE_PATH))
    parser.add_argument(
        "--expected-pilot-phase",
        choices=(SEED_CAP_DERIVATION_PHASE, FINAL_PROTOCOL_REBIND_PHASE),
        default=SEED_CAP_DERIVATION_PHASE,
    )
    parser.add_argument("--expected-protocol-octets", type=int)
    parser.add_argument("--expected-protocol-sha256")
    return parser.parse_args(argv)


def _validate_authority_snapshot(
    *,
    repository_root: Path,
    args: argparse.Namespace,
) -> dict[str, Any]:
    expected_protocol_octets = (
        args.expected_protocol_octets
        if args.expected_protocol_octets is not None
        else PROTOCOL_OCTETS
    )
    expected_protocol_sha256 = (
        args.expected_protocol_sha256
        if args.expected_protocol_sha256 is not None
        else PROTOCOL_SHA256
    )
    _require(
        (expected_protocol_octets is None) == (expected_protocol_sha256 is None),
        "protocol byte-count and SHA pins must be supplied together",
    )
    if expected_protocol_octets is not None:
        _require_integer(
            expected_protocol_octets,
            label="expected protocol octets",
            minimum=1,
        )
        _require_sha256(
            expected_protocol_sha256, label="expected protocol physical SHA"
        )
    protocol = _secure_bounded_read(
        args.protocol,
        base=repository_root,
        maximum_octets=MAXIMUM_AUTHORITY_OCTETS,
        expected_octets=expected_protocol_octets,
        expected_sha256=expected_protocol_sha256,
    )
    correction = _secure_bounded_read(
        args.correction,
        base=repository_root,
        maximum_octets=MAXIMUM_AUTHORITY_OCTETS,
        expected_octets=CORRECTION_OCTETS,
        expected_sha256=CORRECTION_SHA256,
    )
    inventory, inventory_file = _load_json(
        args.inventory,
        repository_root=repository_root,
        maximum_octets=MAXIMUM_AUTHORITY_OCTETS,
        expected_octets=INVENTORY_OCTETS,
        expected_sha256=INVENTORY_RAW_SHA256,
        label="V3 inventory",
    )
    registry, registry_file = _load_json(
        args.registry,
        repository_root=repository_root,
        maximum_octets=MAXIMUM_AUTHORITY_OCTETS,
        expected_octets=REGISTRY_OCTETS,
        expected_sha256=REGISTRY_RAW_SHA256,
        label="structural registry",
    )
    literals, literal_file = _load_json(
        args.literal_authority,
        repository_root=repository_root,
        maximum_octets=MAXIMUM_AUTHORITY_OCTETS,
        expected_octets=LITERAL_AUTHORITY_OCTETS,
        expected_sha256=LITERAL_AUTHORITY_RAW_SHA256,
        label="rule literal authority",
    )
    _, application_witness_file = _load_json(
        args.application_witness,
        repository_root=repository_root,
        maximum_octets=MAXIMUM_AUTHORITY_OCTETS,
        expected_octets=APPLICATION_WITNESS_OCTETS,
        expected_sha256=APPLICATION_WITNESS_RAW_SHA256,
        label="pilot application witness",
    )
    max64_context, max64_context_file = _load_json(
        args.max64_context_authority,
        repository_root=repository_root,
        maximum_octets=MAXIMUM_AUTHORITY_OCTETS,
        expected_octets=MAX64_CONTEXT_AUTHORITY_OCTETS,
        expected_sha256=MAX64_CONTEXT_AUTHORITY_RAW_SHA256,
        label="pilot max64 materialized context authority",
    )
    _validate_materialized_max64_context_authority(
        max64_context,
        label="pilot max64 materialized context authority",
    )
    frozen_files: list[tuple[Path, FrozenFile, int]] = [
        (args.protocol, protocol, MAXIMUM_AUTHORITY_OCTETS),
        (args.correction, correction, MAXIMUM_AUTHORITY_OCTETS),
        (args.inventory, inventory_file, MAXIMUM_AUTHORITY_OCTETS),
        (args.registry, registry_file, MAXIMUM_AUTHORITY_OCTETS),
        (args.literal_authority, literal_file, MAXIMUM_AUTHORITY_OCTETS),
        (
            args.application_witness,
            application_witness_file,
            MAXIMUM_AUTHORITY_OCTETS,
        ),
        (
            args.max64_context_authority,
            max64_context_file,
            MAXIMUM_AUTHORITY_OCTETS,
        ),
    ]
    inode_keys = [(item.signature[0], item.signature[1]) for _, item, _ in frozen_files]
    _require(
        len(set(inode_keys)) == len(inode_keys),
        "authority inputs contain an inode alias",
    )
    _validate_registry(registry)
    _validate_literal_authority(literals)
    _validate_inventory(inventory, registry=registry, literals=literals)
    selected_profiles = _validate_selected_profiles(inventory)
    rows = _derive_row_universe(registry, inventory)
    v1_rejection = _derive_v1_presearch_cap_rejection(registry, rows=rows)
    pilot_loaded = False
    pilot_envelope_valid = False
    pilot_lexical_counts: dict[tuple[str, ...], dict[str, int]] = {}
    pilot_absolute = _absolute_lexical_path(args.pilot, base=repository_root)
    if os.path.lexists(pilot_absolute):
        _require(
            args.expected_pilot_phase == SEED_CAP_DERIVATION_PHASE,
            "final protocol rebind requires independently loaded accepted "
            "18-field resource ceilings before pilot decode",
        )
        pilot, pilot_file = _load_json(
            args.pilot,
            repository_root=repository_root,
            maximum_octets=MAXIMUM_PILOT_OCTETS,
            label="candidate maximum-protocol pilot",
            lexical_resource_limits=SEED_EXECUTION_SAFETY_LIMITS_V1,
            lexical_path_profile=LEXICAL_PILOT_CERTIFICATE_PROFILE,
            expected_pilot_phase=args.expected_pilot_phase,
            lexical_summary_out=pilot_lexical_counts,
        )
        _validate_pilot_root_envelope(
            pilot,
            expected_pilot_phase=args.expected_pilot_phase,
            maximum_protocol_sha256=_sha256(protocol.raw),
            label="candidate maximum-protocol pilot",
        )
        pilot_loaded = True
        pilot_envelope_valid = True
        pilot_inode = (pilot_file.signature[0], pilot_file.signature[1])
        _require(pilot_inode not in inode_keys, "pilot aliases an authority inode")
        frozen_files.append((args.pilot, pilot_file, MAXIMUM_PILOT_OCTETS))
    for path, frozen, maximum_octets in frozen_files:
        repeated = _secure_bounded_read(
            path,
            base=repository_root,
            maximum_octets=maximum_octets,
            expected_octets=len(frozen.raw),
            expected_sha256=_sha256(frozen.raw),
        )
        _require(
            repeated.signature == frozen.signature and repeated.raw == frozen.raw,
            f"input changed between authority snapshots: {path}",
        )
    return {
        "authority_snapshot_valid": True,
        "application_witness_physical_pin_valid": True,
        "max64_context_authority_physical_and_compact_pins_valid": True,
        "max64_context_authority_root_shape_valid": True,
        "pilot_strict_json_loaded": pilot_loaded,
        "pilot_root_envelope_valid": pilot_envelope_valid,
        "pilot_predecoded_certificate_count": len(pilot_lexical_counts),
        "protocol_externally_pinned": expected_protocol_sha256 is not None,
        "protocol_octets": len(protocol.raw),
        "protocol_sha256": _sha256(protocol.raw),
        "reason": NO_GO_REASON,
        "v1_presearch_cap_rejection_valid": True,
        "v1_rejection_finding_id": (
            "RAW_V8_STEP2_MAXIMUM_PROTOCOL_V1_PRESEARCH_CAP_CONTRADICTION"
        ),
        **v1_rejection._asdict(),
        "row_universe_count": len(rows),
        "selected_profile_positions": sorted(selected_profiles),
    }


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parse_args(argv)
        repository_root = args.repository_root.resolve(strict=True)
        _require(repository_root.is_dir(), "repository root is not a directory")
        report = _validate_authority_snapshot(
            repository_root=repository_root,
            args=args,
        )
        _emit_no_go(report)
    except (MaximumProtocolValidationError, OSError, KeyError) as exc:
        _emit_no_go({"reason": str(exc)})
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
