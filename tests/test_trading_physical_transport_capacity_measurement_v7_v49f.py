from __future__ import annotations

import base64
import hashlib
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from riskyieldmm.trading.canonical import (
    CanonicalizationError,
    canonical_json_bytes,
    sha256_digest,
)
from riskyieldmm.trading.physical_transport_actor_v49c import (
    CommittedRawChunkV49C,
    CommittedRawIngressV49C,
    ParserFeedUnitKindV49C,
    ParserTransitionPayloadV49C,
    RawIngressCommittedPayloadV49C,
    RetainedIngressTailV49C,
    TransportActorEventKindV49C,
    TransportActorEventV49C,
    WebSocketParserCursorV49C,
    WebSocketParserStateV49C,
    delineate_next_server_frame_v49c,
)
from riskyieldmm.trading.physical_transport_capacity_lifecycle_v49f import (
    CAPACITY_MEASUREMENT_LIFECYCLE_SCHEMA_VERSION_V49F,
    CapacityMeasurementLifecycleCancellationV49F,
    CapacityMeasurementLifecycleEffectCertaintyV49F,
    CapacityMeasurementLifecycleOperationV49F,
    CapacityMeasurementLifecycleProgressAvailabilityV49F,
    CapacityMeasurementLifecycleTerminalTriggerV49F,
    CapacityMeasurementLifecycleTerminalWriterV49F,
    CapacityMeasurementOperationAttemptV49F,
    CapacityMeasurementOperationDeclarationV49F,
    CapacityMeasurementOperationPrefixV49F,
    CapacityMeasurementOperationTerminalV49F,
    CapacityMeasurementProjectionReceiptEvidenceV49F,
    CapacityMeasurementProjectionRecordEvidenceV49F,
    CapacityMeasurementSessionTerminalAuthorityV49F,
)
from riskyieldmm.trading.physical_transport_capacity_manifest_authority_v49f import (
    A2M_CANCELLATION_PROFILE_V49F_V7,
    A2M_EXTERNAL_ATTESTATION_STATUS_V49F_V7,
    A2M_FAILED_PREFIX_PROFILE_V49F_V7,
    A2M_MANIFEST_AUTHORITY_SIGNATURE_ALGORITHM_V49F,
    A2M_OBSERVED_LOCAL_AUTHORITY_PROFILE_V49F,
    A2M_OBSERVED_LOCAL_AUTHORITY_PROFILE_V49F_V7,
    A2M_OPERATION_LIFECYCLE_PROFILE_V49F_V7,
    A2M_ORPHAN_RECOVERY_PROFILE_V49F_V7,
    A2M_REQUIRED_PROJECTION_SCHEMA_VERSION_V49F_V7,
    A2M_REQUIRED_PROJECTION_VALIDATION_VERSION_V49F_V7,
    RAW_V6_ACCEPTED_CRITICAL_SOURCE_INVENTORY_ID_V49F,
    RAW_V7_CRITICAL_SOURCE_INVENTORY_ID_V49F,
    RAW_V7_CRITICAL_SOURCE_MODULES_V49F,
    AdmittedCapacityMeasurementAuthorityExpectationV49F,
    AdmittedCapacityMeasurementAuthorityExpectationV49FV7,
    CapacityMeasurementActorBaselineV49FV7,
    CapacityMeasurementLifecycleContractV49FV7,
    CapacityMeasurementManifestAuthorityV49F,
    CapacityMeasurementManifestAuthorityV49FV7,
    CapacityMeasurementProjectionAuthorityV49FV7,
    CapacityMeasurementSourceInventoryV49FV7,
    capacity_measurement_authority_subject_signing_payload_v49f,
    capacity_measurement_authority_subject_signing_payload_v49f_v7,
    derive_capacity_measurement_manifest_authority_subject_id_v49f,
    derive_capacity_measurement_manifest_authority_subject_id_v49f_v7,
    verify_capacity_measurement_manifest_against_admitted_authority_v49f_v7,
)
from riskyieldmm.trading.physical_transport_capacity_measurement_v49f import (
    A2M_CORRECTNESS_FINALIZER_NOT_IMPLEMENTED_V49F_V7,
    A2M_OPERATION_ATTEMPT_RECORD_KIND_V49F_V7,
    A2M_OPERATION_TERMINAL_RECORD_KIND_V49F_V7,
    A2M_POST_RUN_SUFFIX_PROVENANCE_UNATTESTED_V49F_V7,
    CapacityMeasurementArtifactBundleV49FV7,
    CapacityMeasurementCommittedLifecycleRecordV49FV7,
    CapacityMeasurementCorrectnessV49FV7,
    CapacityMeasurementIngressProgressEvidenceV49F,
    CapacityMeasurementIngressWorkloadSpecV49F,
    CapacityMeasurementLogicalOutputFrameV49F,
    CapacityMeasurementManifestV49F,
    CapacityMeasurementManifestV49FV7,
    CapacityMeasurementObservationV49FV7,
    CapacityMeasurementSampleV49FV7,
    CapacityMeasurementScheduleCoverageV49FV7,
    _sample_roots_v49f_v7,
    capacity_measurement_sample_stream_sha256_v49f_v7,
    decode_capacity_measurement_json_v49f,
    decode_capacity_measurement_json_v49f_v7,
    derive_capacity_measurement_ingress_progress_from_prefix_v49f_v7,
    encode_capacity_measurement_json_v49f,
    encode_capacity_measurement_json_v49f_v7,
    verify_capacity_measurement_ingress_progress_against_prefix_v49f_v7,
)
from riskyieldmm.trading.physical_transport_capacity_source_observation_v49f import (
    SourceMemberObservationV49F,
    derive_observed_source_tree_sha256_v49f,
)
from riskyieldmm.trading.physical_transport_control_v4 import RawIngressCommitV4
from riskyieldmm.trading.physical_transport_terminal_v49c import (
    initial_terminal_state_v49c,
)
from tests.test_trading_physical_transport_capacity_measurement_v49f import (
    _TEST_MANIFEST_SIGNER,
    _hash,
    _manifest,
)
from tests.test_trading_physical_transport_runtime_v49f_capacity import _policy

T0 = datetime(2026, 7, 21, 12, 0, tzinfo=timezone.utc)


def _current_v6_predecessor(
    *, source_roles: tuple[str, ...] | None = None
) -> CapacityMeasurementManifestV49F:
    base = _manifest(
        transport_capacity_policy_id=_policy().policy_id,
        monotonic_origin_nanoseconds="1000000",
        boottime_origin_nanoseconds="2000000",
        loop_time_origin_nanoseconds="3000000",
    )
    roles = (
        tuple(
            sorted(
                (
                    *(
                        f"CRITICAL_MODULE:{name}"
                        for name in RAW_V7_CRITICAL_SOURCE_MODULES_V49F
                    ),
                    *(
                        f"LOADED_MODULE:{name}"
                        for name in RAW_V7_CRITICAL_SOURCE_MODULES_V49F
                    ),
                )
            )
        )
        if source_roles is None
        else source_roles
    )
    source_member = SourceMemberObservationV49F(
        relative_path=base.source_observation.members[0].relative_path,
        roles=roles,
        size_bytes=base.source_observation.members[0].size_bytes,
        sha256=base.source_observation.members[0].sha256,
        device=base.source_observation.members[0].device,
        inode=base.source_observation.members[0].inode,
        mode=base.source_observation.members[0].mode,
        modified_ns=base.source_observation.members[0].modified_ns,
        changed_ns=base.source_observation.members[0].changed_ns,
    )
    source_tree = derive_observed_source_tree_sha256_v49f((source_member,))
    source = replace(
        base.source_observation,
        members=(source_member,),
        member_count=1,
        total_bytes=source_member.size_bytes,
        source_tree_sha256=source_tree,
        deployment_source_tree_sha256=source_tree,
        deployment_source_tree_matches=True,
        source_observation_id=None,
    )
    runtime = replace(
        base.runtime_observation,
        declared_source_tree_sha256=source_tree,
        runtime_observation_id=None,
    )
    subject = {
        "authority_profile": A2M_OBSERVED_LOCAL_AUTHORITY_PROFILE_V49F,
        "external_attestation_status": base.manifest_authority.external_attestation_status,
        "manifest_request_id": base.manifest_request.manifest_request_id,
        "source_observation_id": source.source_observation_id,
        "runtime_observation_id": runtime.runtime_observation_id,
        "environment_observation_id": (
            base.process_environment_observation.environment_observation_id
        ),
        "deployment_bundle_id": runtime.deployment_bundle_id,
        "deployment_trust_root_id": runtime.deployment_trust_root_id,
        "collector_release_manifest_id": runtime.collector_release_manifest_id,
        "runtime_environment_manifest_id": runtime.runtime_environment_manifest_id,
        "transport_session_id": base.transport_session_id,
        "driver_evidence_nonce_sha256": base.driver_evidence_nonce_sha256,
        "kernel_socket_identity": base.kernel_socket_identity,
        "transport_capacity_policy_id": base.transport_capacity_policy_id,
        "started_at_utc": base.manifest_authority.started_at_utc,
        "monotonic_origin_nanoseconds": base.monotonic_origin_nanoseconds,
        "boottime_origin_nanoseconds": base.boottime_origin_nanoseconds,
        "loop_time_origin_nanoseconds": base.loop_time_origin_nanoseconds,
        "promotion_eligible": False,
    }
    subject_id = derive_capacity_measurement_manifest_authority_subject_id_v49f(subject)
    signature = _TEST_MANIFEST_SIGNER.sign(
        canonical_json_bytes(
            capacity_measurement_authority_subject_signing_payload_v49f(
                authority_subject_id=subject_id,
                deployment_bundle_id=runtime.deployment_bundle_id,
                collector_attestation_key_id=runtime.collector_attestation_key_id,
                transport_session_id=runtime.transport_session_id,
            )
        )
    )
    authority = CapacityMeasurementManifestAuthorityV49F(
        **subject,
        authority_subject_id=subject_id,
        signature_algorithm=A2M_MANIFEST_AUTHORITY_SIGNATURE_ALGORITHM_V49F,
        collector_attestation_key_id=runtime.collector_attestation_key_id,
        collector_attestation_public_key_hex=(
            _TEST_MANIFEST_SIGNER.public_key_bytes.hex()
        ),
        signature_hex=signature.hex(),
    )
    return replace(
        base,
        source_identity_sha256=source_tree,
        runtime_identity_sha256=runtime.runtime_observation_id,
        source_observation=source,
        runtime_observation=runtime,
        manifest_authority=authority,
        campaign_manifest_id=None,
    )


def _predecessor_expectation(
    predecessor: CapacityMeasurementManifestV49F,
) -> AdmittedCapacityMeasurementAuthorityExpectationV49F:
    runtime = predecessor.runtime_observation
    authority = predecessor.manifest_authority
    return AdmittedCapacityMeasurementAuthorityExpectationV49F(
        authority_profile=runtime.authority_profile,
        transport_runtime_schema_version=runtime.transport_runtime_schema_version,
        deployment_bundle_id=runtime.deployment_bundle_id,
        deployment_sequence=runtime.deployment_sequence,
        deployment_trust_root_id=runtime.deployment_trust_root_id,
        environment_id=runtime.environment_id,
        collector_release_manifest_id=runtime.collector_release_manifest_id,
        collector_key_authorization_manifest_id=(
            runtime.collector_key_authorization_manifest_id
        ),
        collector_attestation_key_id=authority.collector_attestation_key_id,
        collector_attestation_public_key_hex=(
            authority.collector_attestation_public_key_hex
        ),
        runtime_environment_manifest_id=runtime.runtime_environment_manifest_id,
        collector_release_name=runtime.collector_release_name,
        collector_release_version=runtime.collector_release_version,
        collector_release_entrypoint=runtime.collector_release_entrypoint,
        release_source_tree_sha256=runtime.declared_source_tree_sha256,
        release_build_artifact_sha256=runtime.declared_build_artifact_sha256,
        tls_websocket_driver_policy_id=runtime.tls_websocket_driver_policy_id,
        transport_capacity_policy_id=runtime.transport_capacity_policy_id,
        clock_source_manifest_id=runtime.clock_source_manifest_id,
    )


def _v7_manifest_and_expectation() -> tuple[
    CapacityMeasurementManifestV49FV7,
    AdmittedCapacityMeasurementAuthorityExpectationV49FV7,
]:
    predecessor = _current_v6_predecessor()
    runtime = predecessor.runtime_observation
    source = predecessor.source_observation
    source_inventory = CapacityMeasurementSourceInventoryV49FV7(
        predecessor_source_inventory_id=(
            RAW_V6_ACCEPTED_CRITICAL_SOURCE_INVENTORY_ID_V49F
        ),
        module_names=RAW_V7_CRITICAL_SOURCE_MODULES_V49F,
        source_inventory_id=RAW_V7_CRITICAL_SOURCE_INVENTORY_ID_V49F,
    )
    lifecycle = CapacityMeasurementLifecycleContractV49FV7(
        lifecycle_schema_id=CAPACITY_MEASUREMENT_LIFECYCLE_SCHEMA_VERSION_V49F,
        operation_lifecycle_profile=A2M_OPERATION_LIFECYCLE_PROFILE_V49F_V7,
        failed_prefix_profile=A2M_FAILED_PREFIX_PROFILE_V49F_V7,
        cancellation_profile=A2M_CANCELLATION_PROFILE_V49F_V7,
        orphan_recovery_profile=A2M_ORPHAN_RECOVERY_PROFILE_V49F_V7,
        fatal_operation_exceptions=(("FATAL_MEMORY_ERROR", "builtins.MemoryError"),),
    )
    projection = CapacityMeasurementProjectionAuthorityV49FV7(
        projection_ledger_id=_hash("7"),
        projection_schema_version=A2M_REQUIRED_PROJECTION_SCHEMA_VERSION_V49F_V7,
        projection_validation_version=(
            A2M_REQUIRED_PROJECTION_VALIDATION_VERSION_V49F_V7
        ),
        projection_schema_fingerprint=_hash("8"),
        baseline_receipt_sequence=0,
        baseline_receipt_hash="0" * 64,
    )
    parser_cursor = WebSocketParserCursorV49C(
        cursor_sequence=0,
        next_stream_octet=0,
        websocket_state=WebSocketParserStateV49C.OPEN,
    )
    actor = CapacityMeasurementActorBaselineV49FV7(
        transport_subscription_policy_id=_hash("1"),
        transport_session_id=predecessor.transport_session_id,
        driver_evidence_nonce_sha256=predecessor.driver_evidence_nonce_sha256,
        kernel_socket_identity=predecessor.kernel_socket_identity,
        transport_capacity_policy_id=predecessor.transport_capacity_policy_id,
        physical_scope_manifest_id=_hash("2"),
        adapter_policy_id=_hash("3"),
        capture_partition_id=_hash("4"),
        socket_lease_id=_hash("5"),
        connection_generation=1,
        deployment_bundle_id=runtime.deployment_bundle_id,
        writer_fence_token_sha256=_hash("6"),
        writer_fence_generation=1,
        monotonic_clock_domain_id=runtime.monotonic_clock_domain_id,
        driver_policy_id=runtime.tls_websocket_driver_policy_id,
        raw_ingress_sequence=0,
        raw_ingress_commit_id=None,
        actor_event_count=0,
        actor_tail_event_id=None,
        parser_cursor=parser_cursor,
        parser_cursor_id=parser_cursor.parser_cursor_id,
        runtime_state="READY",
        projection_receipt_sequence=projection.baseline_receipt_sequence,
        projection_receipt_hash=projection.baseline_receipt_hash,
    )
    base_authority = predecessor.manifest_authority
    subject = {
        "authority_profile": A2M_OBSERVED_LOCAL_AUTHORITY_PROFILE_V49F_V7,
        "external_attestation_status": A2M_EXTERNAL_ATTESTATION_STATUS_V49F_V7,
        "base_observed_authority_id": base_authority.manifest_authority_id,
        "predecessor_manifest_id": predecessor.campaign_manifest_id,
        "predecessor_manifest_authority_id": base_authority.manifest_authority_id,
        "v7_source_inventory_id": source_inventory.source_inventory_id,
        "source_inventory_record_id": source_inventory.source_inventory_record_id,
        "v7_source_observation_id": source.source_observation_id,
        "v7_source_tree_sha256": source.source_tree_sha256,
        "v7_release_source_tree_sha256": source.deployment_source_tree_sha256,
        "lifecycle_schema_id": lifecycle.lifecycle_schema_id,
        "lifecycle_contract_id": lifecycle.lifecycle_contract_id,
        "projection_authority_id": projection.projection_authority_id,
        "projection_ledger_id": projection.projection_ledger_id,
        "projection_schema_version": projection.projection_schema_version,
        "projection_validation_version": projection.projection_validation_version,
        "projection_schema_fingerprint": projection.projection_schema_fingerprint,
        "actor_baseline_id": actor.actor_baseline_id,
        "collector_attestation_key_id": base_authority.collector_attestation_key_id,
        "deployment_bundle_id": runtime.deployment_bundle_id,
        "deployment_trust_root_id": runtime.deployment_trust_root_id,
        "collector_release_manifest_id": runtime.collector_release_manifest_id,
        "runtime_environment_manifest_id": runtime.runtime_environment_manifest_id,
        "transport_session_id": predecessor.transport_session_id,
        "driver_evidence_nonce_sha256": predecessor.driver_evidence_nonce_sha256,
        "kernel_socket_identity": predecessor.kernel_socket_identity,
        "transport_capacity_policy_id": predecessor.transport_capacity_policy_id,
        "started_at_utc": predecessor.started_at_utc,
        "monotonic_origin_nanoseconds": predecessor.monotonic_origin_nanoseconds,
        "boottime_origin_nanoseconds": predecessor.boottime_origin_nanoseconds,
        "loop_time_origin_nanoseconds": predecessor.loop_time_origin_nanoseconds,
        "operation_lifecycle_profile": lifecycle.operation_lifecycle_profile,
        "failed_prefix_profile": lifecycle.failed_prefix_profile,
        "cancellation_profile": lifecycle.cancellation_profile,
        "orphan_recovery_profile": lifecycle.orphan_recovery_profile,
        "promotion_eligible": False,
    }
    subject_id = derive_capacity_measurement_manifest_authority_subject_id_v49f_v7(
        subject
    )
    signature = _TEST_MANIFEST_SIGNER.sign(
        canonical_json_bytes(
            capacity_measurement_authority_subject_signing_payload_v49f_v7(
                authority_subject_id=subject_id,
                base_observed_authority_id=subject["base_observed_authority_id"],
                predecessor_manifest_id=subject["predecessor_manifest_id"],
                predecessor_manifest_authority_id=subject[
                    "predecessor_manifest_authority_id"
                ],
                v7_source_inventory_id=subject["v7_source_inventory_id"],
                v7_source_observation_id=subject["v7_source_observation_id"],
                v7_source_tree_sha256=subject["v7_source_tree_sha256"],
                v7_release_source_tree_sha256=subject["v7_release_source_tree_sha256"],
                lifecycle_schema_id=subject["lifecycle_schema_id"],
                projection_ledger_id=subject["projection_ledger_id"],
                projection_schema_version=subject["projection_schema_version"],
                projection_validation_version=subject["projection_validation_version"],
                projection_schema_fingerprint=subject["projection_schema_fingerprint"],
                actor_baseline_id=subject["actor_baseline_id"],
                collector_attestation_key_id=subject["collector_attestation_key_id"],
                deployment_bundle_id=subject["deployment_bundle_id"],
                transport_session_id=subject["transport_session_id"],
                operation_lifecycle_profile=subject["operation_lifecycle_profile"],
                failed_prefix_profile=subject["failed_prefix_profile"],
                cancellation_profile=subject["cancellation_profile"],
                orphan_recovery_profile=subject["orphan_recovery_profile"],
            )
        )
    )
    authority = CapacityMeasurementManifestAuthorityV49FV7(
        **subject,
        authority_subject_id=subject_id,
        signature_algorithm=A2M_MANIFEST_AUTHORITY_SIGNATURE_ALGORITHM_V49F,
        collector_attestation_public_key_hex=(
            _TEST_MANIFEST_SIGNER.public_key_bytes.hex()
        ),
        signature_hex=signature.hex(),
    )
    manifest = CapacityMeasurementManifestV49FV7(
        predecessor_manifest_v6=predecessor,
        source_inventory=source_inventory,
        lifecycle_contract=lifecycle,
        projection_authority=projection,
        actor_baseline=actor,
        manifest_authority_v7=authority,
    )
    expectation = AdmittedCapacityMeasurementAuthorityExpectationV49FV7(
        predecessor_expectation_v6=_predecessor_expectation(predecessor),
        v7_source_inventory_id=source_inventory.source_inventory_id,
        source_inventory_record_id=source_inventory.source_inventory_record_id,
        v7_source_observation_id=source.source_observation_id,
        v7_source_tree_sha256=source.source_tree_sha256,
        v7_release_source_tree_sha256=source.deployment_source_tree_sha256,
        lifecycle_contract_id=lifecycle.lifecycle_contract_id,
        projection_authority_id=projection.projection_authority_id,
        projection_ledger_id=projection.projection_ledger_id,
        projection_schema_version=projection.projection_schema_version,
        projection_validation_version=projection.projection_validation_version,
        projection_schema_fingerprint=projection.projection_schema_fingerprint,
        baseline_receipt_sequence=projection.baseline_receipt_sequence,
        baseline_receipt_hash=projection.baseline_receipt_hash,
        actor_baseline_id=actor.actor_baseline_id,
        collector_attestation_key_id=base_authority.collector_attestation_key_id,
        collector_attestation_public_key_hex=(
            base_authority.collector_attestation_public_key_hex
        ),
    )
    return manifest, expectation


def _projection_commit(
    record: Any,
    *,
    record_kind: str,
    identity_id: str,
    ledger_id: str,
    global_sequence: int,
    previous_receipt_hash: str,
) -> tuple[
    CapacityMeasurementProjectionReceiptEvidenceV49F,
    CapacityMeasurementProjectionRecordEvidenceV49F,
]:
    canonical_record = canonical_json_bytes(record.as_dict())
    content_hash = hashlib.sha256(canonical_record).hexdigest()
    receipt_hash = sha256_digest(
        {
            "content_hash": content_hash,
            "domain": "RiskYieldMMPhysicalProjectionReceiptV4",
            "global_sequence": global_sequence,
            "identity_id": identity_id,
            "ledger_id": ledger_id,
            "previous_receipt_hash": previous_receipt_hash,
            "record_kind": record_kind,
        }
    )
    return (
        CapacityMeasurementProjectionReceiptEvidenceV49F(
            ledger_id=ledger_id,
            global_sequence=global_sequence,
            receipt_hash=receipt_hash,
            previous_receipt_hash=previous_receipt_hash,
            record_kind=record_kind,
            identity_id=identity_id,
            content_hash=content_hash,
            committed_at=T0 + timedelta(microseconds=global_sequence),
        ),
        CapacityMeasurementProjectionRecordEvidenceV49F(
            record_kind=record_kind,
            identity_id=identity_id,
            content_hash=content_hash,
            canonical_record_base64=base64.b64encode(canonical_record).decode("ascii"),
        ),
    )


def _attempt(
    manifest: CapacityMeasurementManifestV49FV7,
    *,
    declaration_changes: dict[str, Any] | None = None,
    attempt_changes: dict[str, Any] | None = None,
) -> CapacityMeasurementOperationAttemptV49F:
    predecessor = manifest.predecessor_manifest_v6
    workload = predecessor.workloads[0]
    spec = CapacityMeasurementIngressWorkloadSpecV49F.from_manifest_json(
        workload.workload_manifest_json
    )
    input_bytes = b"".join(spec.input_chunks)
    declaration_values: dict[str, Any] = {
        "campaign_manifest_id": manifest.campaign_manifest_id,
        "manifest_authority_id": manifest.manifest_authority_v7.manifest_authority_id,
        "measurement_design_id": predecessor.design.measurement_design_id,
        "workload_id": workload.workload_id,
        "workload_sha256": workload.workload_sha256,
        "sample_sequence": 1,
        "operation_sequence": 1,
        "trial_index": 0,
        "repetition_index": 0,
        "is_warmup": True,
        "stage": spec.stage,
        "operation": CapacityMeasurementLifecycleOperationV49F.INGRESS,
        "input_chunk_count": len(spec.input_chunks),
        "input_octet_count": len(input_bytes),
        "input_sha256": hashlib.sha256(input_bytes).hexdigest(),
        "raw_ingress_batch_sha256": spec.raw_ingress_batch_sha256,
        "timeout_seconds": spec.timeout_seconds,
        "expected_output_frame_count": len(spec.expected_output_frames),
        "expected_output_frames_sha256": spec.expected_output_frames_sha256,
    }
    declaration_values.update(declaration_changes or {})
    declaration = CapacityMeasurementOperationDeclarationV49F(**declaration_values)
    actor = manifest.actor_baseline
    projection = manifest.projection_authority
    policy = _policy()
    loop_origin = int(predecessor.loop_time_origin_nanoseconds)
    attempt_values: dict[str, Any] = {
        **declaration_values,
        "declaration_id": declaration.declaration_id,
        "previous_operation_terminal_id": None,
        "transport_session_id": predecessor.transport_session_id,
        "driver_evidence_nonce_sha256": predecessor.driver_evidence_nonce_sha256,
        "kernel_socket_identity": predecessor.kernel_socket_identity,
        "transport_capacity_policy_id": predecessor.transport_capacity_policy_id,
        "transport_capacity_policy": policy,
        "projection_ledger_id": projection.projection_ledger_id,
        "projection_schema_version": projection.projection_schema_version,
        "projection_validation_version": projection.projection_validation_version,
        "projection_schema_fingerprint": projection.projection_schema_fingerprint,
        "projection_store_observation_id": _hash("a"),
        "writer_fence_token_sha256": actor.writer_fence_token_sha256,
        "writer_fence_generation": actor.writer_fence_generation,
        "pre_attempt_receipt_sequence": projection.baseline_receipt_sequence,
        "pre_attempt_receipt_hash": projection.baseline_receipt_hash,
        "retained_raw_dependencies": (),
        "initial_pending_ingress_present_before": False,
        "observer_start_offset_nanoseconds": 30,
        "boottime_start_offset_nanoseconds": 30,
        "loop_time_start_offset_nanoseconds": 30,
        "loop_time_origin_nanoseconds": str(loop_origin),
        "admission_policy_id": policy.policy_id,
        "admission_epoch": 1,
        "admission_sequence": 1,
        "admission_command_kind": CapacityMeasurementLifecycleOperationV49F.INGRESS,
        "admission_reservation_work_units": policy.ingress_reservation_work_units,
        "admission_admitted_loop_time_ns": str(loop_origin + 10),
        "admission_started_loop_time_ns": str(loop_origin + 20),
        "admission_start_deadline_loop_time_ns": str(loop_origin + 2_000),
        "admission_queue_wait_nanoseconds": 10,
        "baseline_raw_ingress_sequence": actor.raw_ingress_sequence,
        "baseline_raw_ingress_commit_id": actor.raw_ingress_commit_id,
        "baseline_actor_event_count": actor.actor_event_count,
        "baseline_actor_tail_event_id": actor.actor_tail_event_id,
        "parser_cursor_before": actor.parser_cursor,
        "parser_cursor_id_before": actor.parser_cursor_id,
        "runtime_state_before": actor.runtime_state,
        "started_at": T0,
        "started_monotonic_ns": "1000000",
        "monotonic_clock_domain_id": actor.monotonic_clock_domain_id,
    }
    attempt_values.update(attempt_changes or {})
    return CapacityMeasurementOperationAttemptV49F(**attempt_values)


def _unavailable_observation() -> CapacityMeasurementObservationV49FV7:
    values: dict[str, Any] = {}
    for name, _ in CapacityMeasurementObservationV49FV7._COMPONENTS:
        values[name] = None
        values[f"{name}_unavailable_reason"] = "CANCELLED_BEFORE_OBSERVATION"
    return CapacityMeasurementObservationV49FV7(**values)


def _observation_with_progress(
    progress: CapacityMeasurementIngressProgressEvidenceV49F,
) -> CapacityMeasurementObservationV49FV7:
    values: dict[str, Any] = {}
    for name, _ in CapacityMeasurementObservationV49FV7._COMPONENTS:
        if name == "returned_ingress_progress":
            values[name] = progress
            values[f"{name}_unavailable_reason"] = None
        else:
            values[name] = None
            values[f"{name}_unavailable_reason"] = "NOT_CAPTURED_BY_FIXTURE"
    return CapacityMeasurementObservationV49FV7(**values)


def _returned_sample(
    manifest: CapacityMeasurementManifestV49FV7,
) -> CapacityMeasurementSampleV49FV7:
    """Build one receipt-complete returned prefix from durable records only."""

    attempt = _attempt(manifest)
    ledger_id = manifest.projection_authority.projection_ledger_id
    attempt_receipt, attempt_record = _projection_commit(
        attempt,
        record_kind=A2M_OPERATION_ATTEMPT_RECORD_KIND_V49F_V7,
        identity_id=attempt.attempt_id,
        ledger_id=ledger_id,
        global_sequence=1,
        previous_receipt_hash="0" * 64,
    )
    spec = CapacityMeasurementIngressWorkloadSpecV49F.from_manifest_json(
        manifest.predecessor_manifest_v6.workloads[0].workload_manifest_json
    )
    raw_chunks_base64 = tuple(
        base64.b64encode(chunk).decode("ascii") for chunk in spec.input_chunks
    )
    actor = manifest.actor_baseline
    raw = RawIngressCommitV4(
        transport_subscription_policy_id=actor.transport_subscription_policy_id,
        transport_session_id=actor.transport_session_id,
        physical_scope_manifest_id=actor.physical_scope_manifest_id,
        adapter_policy_id=actor.adapter_policy_id,
        capture_partition_id=actor.capture_partition_id,
        socket_lease_id=actor.socket_lease_id,
        connection_generation=actor.connection_generation,
        deployment_bundle_id=actor.deployment_bundle_id,
        writer_fence_token_sha256=actor.writer_fence_token_sha256,
        writer_fence_generation=actor.writer_fence_generation,
        ingress_sequence=1,
        raw_ingress_chunks_base64=raw_chunks_base64,
        raw_ingress_chunks_sha256=tuple(
            hashlib.sha256(chunk).hexdigest() for chunk in spec.input_chunks
        ),
        raw_ingress_batch_sha256=spec.raw_ingress_batch_sha256,
        received_at=T0 + timedelta(microseconds=2),
        monotonic_clock_domain_id=actor.monotonic_clock_domain_id,
        received_monotonic_ns=1_000_002,
    )
    raw_receipt, raw_record = _projection_commit(
        raw,
        record_kind="RAW_INGRESS_COMMIT_V4",
        identity_id=raw.raw_ingress_commit_id,
        ledger_id=ledger_id,
        global_sequence=2,
        previous_receipt_hash=attempt_receipt.receipt_hash,
    )
    committed_raw = CommittedRawIngressV49C.from_mapping(raw_receipt.as_dict())
    raw_event = TransportActorEventV49C.create(
        transport_subscription_policy_id=actor.transport_subscription_policy_id,
        transport_session_id=actor.transport_session_id,
        physical_scope_manifest_id=actor.physical_scope_manifest_id,
        adapter_policy_id=actor.adapter_policy_id,
        capture_partition_id=actor.capture_partition_id,
        socket_lease_id=actor.socket_lease_id,
        connection_generation=actor.connection_generation,
        deployment_bundle_id=actor.deployment_bundle_id,
        writer_fence_token_sha256=actor.writer_fence_token_sha256,
        writer_fence_generation=actor.writer_fence_generation,
        monotonic_clock_domain_id=actor.monotonic_clock_domain_id,
        driver_policy_id=actor.driver_policy_id,
        recorded_at=T0 + timedelta(microseconds=3),
        recorded_monotonic_ns=1_000_003,
        actor_sequence=1,
        previous_event_id=None,
        event_kind=TransportActorEventKindV49C.RAW_INGRESS_COMMITTED,
        payload=RawIngressCommittedPayloadV49C(
            raw_ingress_commit_id=raw.raw_ingress_commit_id,
            receipt=committed_raw,
            ingress_sequence=raw.ingress_sequence,
            previous_raw_ingress_commit_id=None,
            stream_start_octet=0,
            stream_end_octet=len(raw.raw_bytes),
            ordered_chunk_octet_lengths=tuple(map(len, spec.input_chunks)),
            ordered_chunk_sha256=raw.raw_ingress_chunks_sha256,
            raw_ingress_batch_sha256=raw.raw_ingress_batch_sha256,
            received_at=raw.received_at,
            received_monotonic_ns=raw.received_monotonic_ns,
        ),
    )
    raw_event_receipt, raw_event_record = _projection_commit(
        raw_event,
        record_kind="TRANSPORT_ACTOR_EVENT_V49C",
        identity_id=raw_event.transport_actor_event_id,
        ledger_id=ledger_id,
        global_sequence=3,
        previous_receipt_hash=raw_receipt.receipt_hash,
    )
    delineated = delineate_next_server_frame_v49c(
        prior_tail=RetainedIngressTailV49C(),
        committed_raw_chunks=(
            CommittedRawChunkV49C(
                raw_ingress_commit_id=raw.raw_ingress_commit_id,
                projection_receipt_sequence=raw_receipt.global_sequence,
                projection_receipt_hash=raw_receipt.receipt_hash,
                raw_local_start_octet=0,
                stream_start_octet=0,
                data=raw.raw_bytes,
            ),
        ),
    )
    assert delineated.unit is not None
    cursor_after = WebSocketParserCursorV49C(
        cursor_sequence=actor.parser_cursor.cursor_sequence + 1,
        next_stream_octet=len(raw.raw_bytes),
        websocket_state=WebSocketParserStateV49C.OPEN,
    )
    parser_event = TransportActorEventV49C.create(
        transport_subscription_policy_id=actor.transport_subscription_policy_id,
        transport_session_id=actor.transport_session_id,
        physical_scope_manifest_id=actor.physical_scope_manifest_id,
        adapter_policy_id=actor.adapter_policy_id,
        capture_partition_id=actor.capture_partition_id,
        socket_lease_id=actor.socket_lease_id,
        connection_generation=actor.connection_generation,
        deployment_bundle_id=actor.deployment_bundle_id,
        writer_fence_token_sha256=actor.writer_fence_token_sha256,
        writer_fence_generation=actor.writer_fence_generation,
        monotonic_clock_domain_id=actor.monotonic_clock_domain_id,
        driver_policy_id=actor.driver_policy_id,
        recorded_at=T0 + timedelta(microseconds=4),
        recorded_monotonic_ns=1_000_004,
        actor_sequence=2,
        previous_event_id=raw_event.transport_actor_event_id,
        event_kind=TransportActorEventKindV49C.PARSER_TRANSITION,
        payload=ParserTransitionPayloadV49C(
            cursor_before=actor.parser_cursor,
            cursor_after=cursor_after,
            feed_unit_kind=ParserFeedUnitKindV49C.COMPLETE_FRAME,
            source_slices=delineated.unit.source_slices,
            frame=delineated.unit.metadata,
            parser_error=None,
            ordered_protocol_output_chunks_base64=(),
            ordered_protocol_output_chunks_sha256=(),
            protocol_output_batch_sha256=None,
            send_eof_after_output=False,
            processed_at=T0 + timedelta(microseconds=4),
            processed_monotonic_ns=1_000_004,
        ),
    )
    parser_receipt, parser_record = _projection_commit(
        parser_event,
        record_kind="TRANSPORT_ACTOR_EVENT_V49C",
        identity_id=parser_event.transport_actor_event_id,
        ledger_id=ledger_id,
        global_sequence=4,
        previous_receipt_hash=raw_event_receipt.receipt_hash,
    )
    open_prefix = CapacityMeasurementOperationPrefixV49F(
        attempt=attempt,
        terminal=None,
        new_raw_ingress_commits=(raw,),
        raw_dependencies=(raw,),
        actor_events=(raw_event, parser_event),
        projection_receipts=(
            attempt_receipt,
            raw_receipt,
            raw_event_receipt,
            parser_receipt,
        ),
        projection_records=(
            attempt_record,
            raw_record,
            raw_event_record,
            parser_record,
        ),
    )
    progress = derive_capacity_measurement_ingress_progress_from_prefix_v49f_v7(
        open_prefix
    )
    terminal = CapacityMeasurementOperationTerminalV49F(
        attempt_id=attempt.attempt_id,
        previous_operation_terminal_id=None,
        terminal_writer=CapacityMeasurementLifecycleTerminalWriterV49F.SAME_TASK,
        terminal_trigger=CapacityMeasurementLifecycleTerminalTriggerV49F.RETURNED,
        cancellation_classification=CapacityMeasurementLifecycleCancellationV49F.NONE,
        effect_certainty=CapacityMeasurementLifecycleEffectCertaintyV49F.COMPLETE,
        progress_availability=(
            CapacityMeasurementLifecycleProgressAvailabilityV49F.EXACT_RETURNED_PROGRESS
        ),
        progress_unavailable_reason=None,
        operation_error_code=None,
        surfaced_exception_class=None,
        exception_class_chain=(),
        exception_message_sha256_chain=(),
        returned_progress_evidence_id=progress.ingress_progress_evidence_id,
        terminal_raw_ingress_sequence=raw.ingress_sequence,
        terminal_raw_ingress_commit_id=raw.raw_ingress_commit_id,
        terminal_actor_event_count=2,
        terminal_actor_tail_event_id=parser_event.transport_actor_event_id,
        parser_cursor_id_after=cursor_after.parser_cursor_id,
        runtime_state_after="READY",
        actor_terminal_state_id_after=initial_terminal_state_v49c(
            attempt.transport_session_id
        ).terminal_state_id,
        actor_terminal_outcome=None,
        actor_terminal_cause_code=None,
        session_terminal_authority=(
            CapacityMeasurementSessionTerminalAuthorityV49F.NONTERMINAL_RUNTIME
        ),
        recovered_prefix_id=open_prefix.recovered_prefix_id,
        observer_end_offset_nanoseconds=50,
        boottime_end_offset_nanoseconds=50,
        loop_time_end_offset_nanoseconds=50,
        completed_at=T0 + timedelta(seconds=1),
        completed_monotonic_ns="1000100",
    )
    terminal_receipt, terminal_record = _projection_commit(
        terminal,
        record_kind=A2M_OPERATION_TERMINAL_RECORD_KIND_V49F_V7,
        identity_id=terminal.terminal_id,
        ledger_id=ledger_id,
        global_sequence=5,
        previous_receipt_hash=parser_receipt.receipt_hash,
    )
    prefix = CapacityMeasurementOperationPrefixV49F(
        attempt=attempt,
        terminal=terminal,
        new_raw_ingress_commits=(raw,),
        raw_dependencies=(raw,),
        actor_events=(raw_event, parser_event),
        projection_receipts=(
            attempt_receipt,
            raw_receipt,
            raw_event_receipt,
            parser_receipt,
            terminal_receipt,
        ),
        projection_records=(
            attempt_record,
            raw_record,
            raw_event_record,
            parser_record,
            terminal_record,
        ),
    )
    return CapacityMeasurementSampleV49FV7(
        committed_attempt=CapacityMeasurementCommittedLifecycleRecordV49FV7(
            record=attempt,
            projection_receipt=attempt_receipt,
        ),
        committed_terminal=CapacityMeasurementCommittedLifecycleRecordV49FV7(
            record=terminal,
            projection_receipt=terminal_receipt,
        ),
        recovered_prefix=prefix,
        observation=_observation_with_progress(progress),
    )


def _cancelled_sample(
    manifest: CapacityMeasurementManifestV49FV7,
    *,
    declaration_changes: dict[str, Any] | None = None,
    attempt_changes: dict[str, Any] | None = None,
) -> CapacityMeasurementSampleV49FV7:
    attempt = _attempt(
        manifest,
        declaration_changes=declaration_changes,
        attempt_changes=attempt_changes,
    )
    attempt_receipt, attempt_record = _projection_commit(
        attempt,
        record_kind=A2M_OPERATION_ATTEMPT_RECORD_KIND_V49F_V7,
        identity_id=attempt.attempt_id,
        ledger_id=manifest.projection_authority.projection_ledger_id,
        global_sequence=1,
        previous_receipt_hash="0" * 64,
    )
    open_prefix = CapacityMeasurementOperationPrefixV49F(
        attempt=attempt,
        terminal=None,
        new_raw_ingress_commits=(),
        raw_dependencies=(),
        actor_events=(),
        projection_receipts=(attempt_receipt,),
        projection_records=(attempt_record,),
    )
    exception_class = "asyncio.exceptions.CancelledError"
    terminal = CapacityMeasurementOperationTerminalV49F(
        attempt_id=attempt.attempt_id,
        previous_operation_terminal_id=None,
        terminal_writer=CapacityMeasurementLifecycleTerminalWriterV49F.SAME_TASK,
        terminal_trigger=CapacityMeasurementLifecycleTerminalTriggerV49F.CANCELLED,
        cancellation_classification=(
            CapacityMeasurementLifecycleCancellationV49F.ASYNCIO_CANCELLED_ERROR
        ),
        effect_certainty=(
            CapacityMeasurementLifecycleEffectCertaintyV49F.NO_DURABLE_EFFECT
        ),
        progress_availability=(
            CapacityMeasurementLifecycleProgressAvailabilityV49F.EXACT_DURABLE_PREFIX
        ),
        progress_unavailable_reason=None,
        operation_error_code="ASYNCIO_CANCELLED_ERROR",
        surfaced_exception_class=exception_class,
        exception_class_chain=(exception_class,),
        exception_message_sha256_chain=(hashlib.sha256(b"").hexdigest(),),
        returned_progress_evidence_id=None,
        terminal_raw_ingress_sequence=attempt.baseline_raw_ingress_sequence,
        terminal_raw_ingress_commit_id=attempt.baseline_raw_ingress_commit_id,
        terminal_actor_event_count=attempt.baseline_actor_event_count,
        terminal_actor_tail_event_id=attempt.baseline_actor_tail_event_id,
        parser_cursor_id_after=attempt.parser_cursor_id_before,
        runtime_state_after=attempt.runtime_state_before,
        actor_terminal_state_id_after=initial_terminal_state_v49c(
            attempt.transport_session_id
        ).terminal_state_id,
        actor_terminal_outcome=None,
        actor_terminal_cause_code=None,
        session_terminal_authority=(
            CapacityMeasurementSessionTerminalAuthorityV49F.NONTERMINAL_RUNTIME
        ),
        recovered_prefix_id=open_prefix.recovered_prefix_id,
        observer_end_offset_nanoseconds=40,
        boottime_end_offset_nanoseconds=40,
        loop_time_end_offset_nanoseconds=40,
        completed_at=T0 + timedelta(seconds=1),
        completed_monotonic_ns="1000100",
    )
    terminal_receipt, terminal_record = _projection_commit(
        terminal,
        record_kind=A2M_OPERATION_TERMINAL_RECORD_KIND_V49F_V7,
        identity_id=terminal.terminal_id,
        ledger_id=manifest.projection_authority.projection_ledger_id,
        global_sequence=2,
        previous_receipt_hash=attempt_receipt.receipt_hash,
    )
    prefix = CapacityMeasurementOperationPrefixV49F(
        attempt=attempt,
        terminal=terminal,
        new_raw_ingress_commits=(),
        raw_dependencies=(),
        actor_events=(),
        projection_receipts=(attempt_receipt, terminal_receipt),
        projection_records=(attempt_record, terminal_record),
    )
    return CapacityMeasurementSampleV49FV7(
        committed_attempt=CapacityMeasurementCommittedLifecycleRecordV49FV7(
            record=attempt,
            projection_receipt=attempt_receipt,
        ),
        committed_terminal=CapacityMeasurementCommittedLifecycleRecordV49FV7(
            record=terminal,
            projection_receipt=terminal_receipt,
        ),
        recovered_prefix=prefix,
        observation=_unavailable_observation(),
    )


def _bundle(
    manifest: CapacityMeasurementManifestV49FV7,
) -> CapacityMeasurementArtifactBundleV49FV7:
    sample = _cancelled_sample(manifest)
    samples = (sample,)
    raw_root, actor_root, projection_root = _sample_roots_v49f_v7(samples)
    correctness = CapacityMeasurementCorrectnessV49FV7(
        campaign_manifest_id=manifest.campaign_manifest_id,
        manifest_authority_id=manifest.manifest_authority_v7.manifest_authority_id,
        sample_stream_sha256=capacity_measurement_sample_stream_sha256_v49f_v7(
            samples, manifest=manifest
        ),
        sample_count=1,
        first_sample_id=sample.sample_id,
        last_sample_id=sample.sample_id,
        schedule_coverage=CapacityMeasurementScheduleCoverageV49FV7.RUN_ENDING_PREFIX,
        expected_sample_count=2,
        last_operation_sequence=1,
        last_terminal_id=sample.terminal.terminal_id,
        raw_ingress_root_sha256=raw_root,
        actor_event_root_sha256=actor_root,
        projection_root_sha256=projection_root,
        no_loss=False,
        no_duplication=False,
        no_reordering=False,
        control_output_causal=False,
        projection_verified=False,
        observations_complete=False,
        cleanup_complete=False,
        failure_codes=(
            A2M_CORRECTNESS_FINALIZER_NOT_IMPLEMENTED_V49F_V7,
            A2M_POST_RUN_SUFFIX_PROVENANCE_UNATTESTED_V49F_V7,
        ),
    )
    return CapacityMeasurementArtifactBundleV49FV7.build(
        manifest=manifest,
        samples=samples,
        correctness=correctness,
    )


def test_v7_manifest_round_trip_and_independent_authority_verification() -> None:
    manifest, expectation = _v7_manifest_and_expectation()
    encoded = encode_capacity_measurement_json_v49f_v7(manifest)

    assert (
        decode_capacity_measurement_json_v49f_v7(
            encoded, record_type=CapacityMeasurementManifestV49FV7
        )
        == manifest
    )
    verify_capacity_measurement_manifest_against_admitted_authority_v49f_v7(
        manifest=manifest, expectation=expectation
    )


def test_v6_and_v7_manifest_codecs_are_not_cross_compatible() -> None:
    manifest, _ = _v7_manifest_and_expectation()

    with pytest.raises(CanonicalizationError):
        decode_capacity_measurement_json_v49f(
            encode_capacity_measurement_json_v49f_v7(manifest),
            record_type=CapacityMeasurementManifestV49F,
        )
    with pytest.raises(CanonicalizationError):
        decode_capacity_measurement_json_v49f_v7(
            encode_capacity_measurement_json_v49f(manifest.predecessor_manifest_v6),
            record_type=CapacityMeasurementManifestV49FV7,
        )


def test_v7_manifest_rejects_non_current_or_aliased_source_roles() -> None:
    manifest, _ = _v7_manifest_and_expectation()
    roles = manifest.predecessor_manifest_v6.source_observation.members[0].roles
    bad_predecessor = _current_v6_predecessor(
        source_roles=tuple(sorted((*roles[:-1], "TEST_ALIAS")))
    )
    with pytest.raises(CanonicalizationError, match="unknown role"):
        replace(manifest, predecessor_manifest_v6=bad_predecessor)


def test_v7_projection_genesis_and_fatal_policy_are_fail_closed() -> None:
    with pytest.raises(CanonicalizationError, match="genesis hash"):
        CapacityMeasurementProjectionAuthorityV49FV7(
            projection_ledger_id=_hash("1"),
            projection_schema_version=A2M_REQUIRED_PROJECTION_SCHEMA_VERSION_V49F_V7,
            projection_validation_version=(
                A2M_REQUIRED_PROJECTION_VALIDATION_VERSION_V49F_V7
            ),
            projection_schema_fingerprint=_hash("2"),
            baseline_receipt_sequence=1,
            baseline_receipt_hash="0" * 64,
        )


def test_v7_actor_baseline_binds_exact_parser_state_and_runtime_enum() -> None:
    manifest, _ = _v7_manifest_and_expectation()
    actor = manifest.actor_baseline
    with pytest.raises(CanonicalizationError, match="runtime state is unsupported"):
        replace(actor, runtime_state="READY_ALIAS", actor_baseline_id=None)
    with pytest.raises(CanonicalizationError, match="cursor ID differs"):
        replace(actor, parser_cursor_id=_hash("f"), actor_baseline_id=None)
    with pytest.raises(CanonicalizationError, match="sorted and unique"):
        CapacityMeasurementLifecycleContractV49FV7(
            lifecycle_schema_id=CAPACITY_MEASUREMENT_LIFECYCLE_SCHEMA_VERSION_V49F,
            operation_lifecycle_profile=A2M_OPERATION_LIFECYCLE_PROFILE_V49F_V7,
            failed_prefix_profile=A2M_FAILED_PREFIX_PROFILE_V49F_V7,
            cancellation_profile=A2M_CANCELLATION_PROFILE_V49F_V7,
            orphan_recovery_profile=A2M_ORPHAN_RECOVERY_PROFILE_V49F_V7,
            fatal_operation_exceptions=(
                ("Z", "builtins.MemoryError"),
                ("A", "builtins.MemoryError"),
            ),
        )


def test_v7_four_member_artifact_replays_under_independent_expectation() -> None:
    manifest, expectation = _v7_manifest_and_expectation()
    bundle = _bundle(manifest)
    artifacts = bundle.artifact_bytes()

    assert set(artifacts) == {
        "correctness.json",
        "integrity.json",
        "manifest.json",
        "samples.jsonl",
    }
    assert (
        CapacityMeasurementArtifactBundleV49FV7.from_artifact_bytes(
            artifacts,
            expectation=expectation,
        )
        == bundle
    )

    corrupted = dict(artifacts)
    corrupted["samples.jsonl"] = artifacts["samples.jsonl"][:-2] + b"X\n"
    with pytest.raises(CanonicalizationError, match="integrity metadata"):
        CapacityMeasurementArtifactBundleV49FV7.from_artifact_bytes(
            corrupted,
            expectation=expectation,
        )


@pytest.mark.parametrize(
    ("changes"),
    (
        {"measurement_design_id": _hash("f")},
        {"stage": "ALIASED_STAGE"},
        {"input_chunk_count": 2},
        {"input_octet_count": 3},
        {"input_sha256": _hash("f")},
        {"raw_ingress_batch_sha256": _hash("f")},
        {"timeout_seconds": 3},
        {"expected_output_frame_count": 1},
        {"expected_output_frames_sha256": _hash("f")},
        {"sample_sequence": 2},
        {"trial_index": 1},
        {"repetition_index": 1},
        {"is_warmup": False},
    ),
)
def test_v7_sample_recomputes_attempt_declaration_from_signed_workload(
    changes: dict[str, Any],
) -> None:
    manifest, _ = _v7_manifest_and_expectation()
    sample = _cancelled_sample(manifest, declaration_changes=changes)

    with pytest.raises(CanonicalizationError):
        capacity_measurement_sample_stream_sha256_v49f_v7((sample,), manifest=manifest)


def test_v7_attempt_rejects_non_ingress_operation_before_artifact_acceptance() -> None:
    manifest, _ = _v7_manifest_and_expectation()
    with pytest.raises(CanonicalizationError, match="must be an exact"):
        _attempt(manifest, declaration_changes={"operation": "READ"})


@pytest.mark.parametrize(
    "field_name",
    (
        "admission_admitted_loop_time_ns",
        "admission_started_loop_time_ns",
        "admission_start_deadline_loop_time_ns",
        "loop_time_origin_nanoseconds",
        "started_monotonic_ns",
    ),
)
def test_v7_attempt_requires_canonical_uint128_text_for_absolute_clocks(
    field_name: str,
) -> None:
    manifest, _ = _v7_manifest_and_expectation()
    with pytest.raises(CanonicalizationError, match="unsigned 128-bit decimal text"):
        _attempt(manifest, attempt_changes={field_name: 1_000_000})


def test_v7_returned_progress_is_reconstructed_from_receipt_complete_prefix() -> None:
    manifest, _ = _v7_manifest_and_expectation()
    sample = _returned_sample(manifest)
    progress = sample.observation.returned_ingress_progress
    assert progress is not None

    verify_capacity_measurement_ingress_progress_against_prefix_v49f_v7(
        progress,
        prefix=sample.recovered_prefix,
    )
    assert CapacityMeasurementSampleV49FV7.from_mapping(sample.as_dict()) == sample
    assert progress.parser_event_ids == (
        sample.recovered_prefix.actor_events[-1].transport_actor_event_id,
    )
    assert progress.committed_raw_octets == 2
    assert progress.retained_incomplete_octets == 0
    assert progress.websocket_parser_state == "OPEN"


@pytest.mark.parametrize(
    "mutation",
    (
        "raw_identity",
        "raw_octets",
        "raw_batch",
        "parser_ids",
        "automatic_wire_and_dispatch",
        "actor_count",
        "actor_tail",
        "retained_octets",
        "initial_pending",
        "parser_state",
        "admission_policy",
        "admission_epoch",
        "admission_sequence",
        "admission_reservation",
        "grant_offsets",
    ),
)
def test_v7_returned_progress_rejects_each_non_durable_claim_group(
    mutation: str,
) -> None:
    manifest, _ = _v7_manifest_and_expectation()
    sample = _returned_sample(manifest)
    progress = sample.observation.returned_ingress_progress
    assert progress is not None
    changes: dict[str, Any] = {"ingress_progress_evidence_id": None}
    if mutation == "raw_identity":
        changes["raw_ingress_commit_id"] = _hash("c")
    elif mutation == "raw_octets":
        changes["committed_raw_octets"] = progress.committed_raw_octets + 1
    elif mutation == "raw_batch":
        changes["raw_ingress_batch_sha256"] = _hash("d")
    elif mutation == "parser_ids":
        changes["parser_event_ids"] = (_hash("d"),)
    elif mutation == "automatic_wire_and_dispatch":
        masked_empty_pong = b"\x8a\x80\x00\x00\x00\x00"
        changes.update(
            automatic_output_source_parser_event_ids=(progress.parser_event_ids[0],),
            automatic_dispatch_completion_event_ids=(_hash("e"),),
            automatic_protocol_output_base64=base64.b64encode(masked_empty_pong).decode(
                "ascii"
            ),
            automatic_protocol_output_chunk_octet_counts=(len(masked_empty_pong),),
            automatic_output_wire_chunk_counts=(1,),
            automatic_protocol_output_frames=(
                CapacityMeasurementLogicalOutputFrameV49F(
                    opcode="PONG",
                    payload_base64="",
                ),
            ),
        )
    elif mutation == "actor_count":
        changes["actor_event_count_after"] = progress.actor_event_count_after + 1
    elif mutation == "actor_tail":
        changes["actor_tail_event_id_after"] = _hash("e")
    elif mutation == "retained_octets":
        changes["retained_incomplete_octets"] = 1
    elif mutation == "initial_pending":
        changes["used_initial_pending_ingress"] = True
    elif mutation == "parser_state":
        changes["websocket_parser_state"] = "CLOSING"
    elif mutation == "admission_policy":
        changes["admission_policy_id"] = _hash("e")
    elif mutation == "admission_epoch":
        changes["admission_epoch"] = progress.admission_epoch + 1
    elif mutation == "admission_sequence":
        changes["admission_sequence"] = progress.admission_sequence + 1
    elif mutation == "admission_reservation":
        changes["admission_reservation_work_units"] = (
            progress.admission_reservation_work_units + 1
        )
    elif mutation == "grant_offsets":
        changes.update(
            admission_admitted_loop_time_offset_nanoseconds=(
                progress.admission_admitted_loop_time_offset_nanoseconds + 1
            ),
            admission_started_loop_time_offset_nanoseconds=(
                progress.admission_started_loop_time_offset_nanoseconds + 1
            ),
            admission_start_deadline_loop_time_offset_nanoseconds=(
                progress.admission_start_deadline_loop_time_offset_nanoseconds + 1
            ),
        )
    else:  # pragma: no cover - the parameter list is frozen immediately above.
        raise AssertionError(f"unsupported mutation: {mutation}")
    forged = replace(progress, **changes)

    with pytest.raises(CanonicalizationError, match="durable prefix reconstruction"):
        verify_capacity_measurement_ingress_progress_against_prefix_v49f_v7(
            forged,
            prefix=sample.recovered_prefix,
        )


def test_v7_prefix_raw_dependency_union_cannot_omit_the_new_raw_witness() -> None:
    manifest, _ = _v7_manifest_and_expectation()
    prefix = _returned_sample(manifest).recovered_prefix

    with pytest.raises(CanonicalizationError, match="RAW dependencies differ"):
        replace(
            prefix,
            raw_dependencies=(),
            recovered_prefix_id=None,
            prefix_id=None,
        )
