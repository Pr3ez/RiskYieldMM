from __future__ import annotations

import base64
import hashlib
from dataclasses import fields, replace
from typing import Any

import pytest

import riskyieldmm.trading.physical_transport_capacity_measurement_v49f as measurement
from riskyieldmm.trading.canonical import (
    CANONICALIZATION_VERSION,
    CanonicalizationError,
    canonical_json_bytes,
    sha256_digest,
    strict_json_loads,
)
from riskyieldmm.trading.ledger_signing import Ed25519CheckpointSigner
from riskyieldmm.trading.physical_transport_capacity_manifest_authority_v49f import (
    A2M_EXTERNAL_ATTESTATION_STATUS_V49F,
    A2M_MANIFEST_AUTHORITY_SIGNATURE_ALGORITHM_V49F,
    A2M_OBSERVED_LOCAL_AUTHORITY_PROFILE_V49F,
    CapacityMeasurementManifestAuthorityV49F,
    CapacityMeasurementManifestRequestV49F,
    CapacityMeasurementProcessEnvironmentObservationV49F,
    CapacityMeasurementRuntimeObservationV49F,
    capacity_measurement_authority_subject_signing_payload_v49f,
    derive_capacity_measurement_manifest_authority_subject_id_v49f,
)
from riskyieldmm.trading.physical_transport_capacity_measurement_v49f import (
    CORRECTNESS_ARTIFACT_NAME_V49F,
    INTEGRITY_ARTIFACT_NAME_V49F,
    MANIFEST_ARTIFACT_NAME_V49F,
    SAMPLES_ARTIFACT_NAME_V49F,
    CapacityMeasurementAdapterSpanV49F,
    CapacityMeasurementArtifactBundleV49F,
    CapacityMeasurementArtifactErrorV49F,
    CapacityMeasurementCampaignPhaseV49F,
    CapacityMeasurementCorrectnessV49F,
    CapacityMeasurementDesignV49F,
    CapacityMeasurementEnvironmentV49F,
    CapacityMeasurementIngressProgressEvidenceV49F,
    CapacityMeasurementIngressWorkloadSpecV49F,
    CapacityMeasurementLayerSnapshotV49F,
    CapacityMeasurementLogicalOutputFrameV49F,
    CapacityMeasurementManifestV49F,
    CapacityMeasurementOutcomeV49F,
    CapacityMeasurementRuntimeBoundaryEvidenceV49F,
    CapacityMeasurementSampleV49F,
    CapacityMeasurementWorkloadV49F,
    capacity_measurement_sample_stream_sha256_v49f,
    capacity_measurement_workload_corpus_sha256_v49f,
    decode_capacity_measurement_json_v49f,
    decode_capacity_measurement_samples_jsonl_v49f,
    encode_capacity_measurement_json_v49f,
    encode_capacity_measurement_samples_jsonl_v49f,
    validate_capacity_measurement_samples_v49f,
)
from riskyieldmm.trading.physical_transport_capacity_source_observation_v49f import (
    GitSourceStateV49F,
    SourceMemberObservationV49F,
    SourceObservationSnapshotV49F,
    derive_observed_source_tree_sha256_v49f,
)
from riskyieldmm.trading.physical_transport_control_v4 import (
    V4_CONTROL_MAXIMUM_INGRESS_BYTES,
    V4_CONTROL_MAXIMUM_INGRESS_CHUNKS,
)
from riskyieldmm.trading.physical_transport_runtime_v4 import (
    PHYSICAL_TRANSPORT_RUNTIME_V4_SCHEMA_VERSION,
)
from riskyieldmm.trading.physical_transport_tls_v49 import (
    V49_MAXIMUM_POST_UPGRADE_PENDING_BYTES,
    V49_MAXIMUM_TLS_OPERATION_CIPHERTEXT_BYTES,
    V49_MAXIMUM_WEBSOCKET_MESSAGE_BYTES,
    V49C_MAXIMUM_STAGED_WIRE_CHUNKS,
    V49C_MAXIMUM_STAGED_WIRE_OCTETS,
    V49D_MAXIMUM_DURABLE_INGRESS_BUFFER_BYTES,
)
from riskyieldmm.trading.physical_transport_v4 import (
    derive_transport_attestation_key_id,
)

_TEST_MANIFEST_SIGNER = Ed25519CheckpointSigner.from_private_bytes(bytes(range(32)))
_TEST_SQLITE_PRAGMAS = (("foreign_keys", "1"), ("journal_mode", "wal"))


def _hash(digit: str) -> str:
    return digit * 64


def _forge_exact_record(record: Any, **changes: Any) -> Any:
    forged = object.__new__(type(record))
    for item in fields(type(record)):
        object.__setattr__(
            forged,
            item.name,
            changes.get(item.name, getattr(record, item.name)),
        )
    return forged


def _environment() -> CapacityMeasurementEnvironmentV49F:
    return CapacityMeasurementEnvironmentV49F(
        kernel_release="7.0.0-test",
        machine_architecture="x86_64",
        cpu_model="Test CPU",
        logical_cpu_count=8,
        cpu_affinity=(3, 1, 2),
        python_version="3.12.12",
        event_loop_implementation="asyncio.SelectorEventLoop",
        openssl_version="OpenSSL 3.6.3",
        websockets_version="16.0",
        sqlite_version="3.51.1",
        filesystem_type="tmpfs",
        storage_identity_sha256=_hash("1"),
        sqlite_pragmas_sha256=sha256_digest(
            {
                "domain": "RiskYieldMMA2MSqlitePragmasV4_9F",
                "pragmas": list(_TEST_SQLITE_PRAGMAS),
            }
        ),
    )


def _design() -> CapacityMeasurementDesignV49F:
    return CapacityMeasurementDesignV49F(
        observer_clock="CLOCK_MONOTONIC_RAW",
        observer_clock_resolution_nanoseconds=1,
        observer_overhead_subtracted=False,
        instrumentation_overhead_method="PAIRED_EMPTY_SPAN_UNSUBTRACTED",
        warmup_repetitions=1,
        measured_repetitions=1,
        trial_order=measurement.A2M_TRIAL_ORDER_V49F,
        random_seed=49_002,
        analysis_plan_sha256=_hash("3"),
        exclusion_policy_sha256=_hash("4"),
    )


def _manifest(
    *,
    transport_session_id: str = _hash("5"),
    driver_evidence_nonce_sha256: str = _hash("a"),
    kernel_socket_identity: str = _hash("b"),
    transport_capacity_policy_id: str = _hash("9"),
    monotonic_origin_nanoseconds: str = str((1 << 53) + 123_456_789),
    boottime_origin_nanoseconds: str = str((1 << 53) + 223_456_789),
    loop_time_origin_nanoseconds: str = str((1 << 53) + 323_456_789),
    workloads: tuple[CapacityMeasurementWorkloadV49F, ...] | None = None,
    design: CapacityMeasurementDesignV49F | None = None,
    environment: CapacityMeasurementEnvironmentV49F | None = None,
) -> CapacityMeasurementManifestV49F:
    workload_spec = CapacityMeasurementIngressWorkloadSpecV49F(
        workload_family="COALESCED_INGRESS_BURST",
        stage="INTEGRATED_INGRESS",
        input_chunks=(b"\x8a\x00",),
        expected_output_frames=(),
        timeout_seconds=2,
    )
    workload_manifest_json = workload_spec.workload_manifest_json
    workload = CapacityMeasurementWorkloadV49F(
        workload_id="COALESCED_EMPTY_PONG",
        workload_sha256=workload_spec.workload_sha256,
        workload_manifest_json=workload_manifest_json,
    )
    workloads = (workload,) if workloads is None else workloads
    design = _design() if design is None else design
    environment = _environment() if environment is None else environment
    workload_corpus_sha256 = capacity_measurement_workload_corpus_sha256_v49f(workloads)
    request = CapacityMeasurementManifestRequestV49F(
        campaign_label="v49f-a2m-exploratory",
        phase=CapacityMeasurementCampaignPhaseV49F.EXPLORATORY.value,
        measurement_design_id=design.measurement_design_id,
        workload_corpus_sha256=workload_corpus_sha256,
        workload_ids=tuple(item.workload_id for item in workloads),
        workload_sha256s=tuple(item.workload_sha256 for item in workloads),
    )
    source_member = SourceMemberObservationV49F(
        relative_path="riskyieldmm/trading/test_capacity_source.py",
        roles=("TEST_CAPACITY_SOURCE",),
        size_bytes=1,
        sha256=_hash("6"),
        device="1",
        inode="2",
        mode=str(0o100644),
        modified_ns="3",
        changed_ns="4",
    )
    source_tree_sha256 = derive_observed_source_tree_sha256_v49f((source_member,))
    source_observation = SourceObservationSnapshotV49F(
        repository_root="/workspace/riskyieldmm-test",
        git_state=GitSourceStateV49F(
            object_format="sha1",
            head_commit="4b3e9eda62c09564ce4626087383eeed9f5faea9",
            head_tree="5b3e9eda62c09564ce4626087383eeed9f5faea9",
            branch_ref="refs/heads/test",
            porcelain_v2_status_base64=base64.b64encode(
                b"1 .M N... test_capacity_source.py\x00"
            ).decode("ascii"),
            source_tree_clean=False,
        ),
        members=(source_member,),
        member_count=1,
        total_bytes=1,
        source_tree_sha256=source_tree_sha256,
        deployment_source_tree_sha256=source_tree_sha256,
        deployment_source_tree_matches=True,
    )
    collector_key_id = derive_transport_attestation_key_id(
        _TEST_MANIFEST_SIGNER.public_key_bytes
    )
    runtime_observation = CapacityMeasurementRuntimeObservationV49F(
        authority_profile="EXACT_TEST",
        transport_runtime_schema_version=PHYSICAL_TRANSPORT_RUNTIME_V4_SCHEMA_VERSION,
        deployment_bundle_id=_hash("d"),
        deployment_sequence=1,
        deployment_trust_root_id=_hash("e"),
        environment_id="test-environment",
        collector_release_manifest_id=_hash("f"),
        collector_key_authorization_manifest_id=_hash("0"),
        collector_attestation_key_id=collector_key_id,
        collector_release_name="riskyieldmm-test-collector",
        collector_release_version="0.0.test",
        collector_release_entrypoint="riskyieldmm.test",
        declared_source_tree_sha256=source_tree_sha256,
        declared_build_artifact_sha256=_hash("1"),
        runtime_environment_manifest_id=_hash("2"),
        tls_websocket_driver_policy_id=_hash("3"),
        retained_runtime_observation_sha256=_hash("4"),
        transport_capacity_policy_id=transport_capacity_policy_id,
        transport_session_id=transport_session_id,
        driver_evidence_nonce_sha256=driver_evidence_nonce_sha256,
        kernel_socket_identity=kernel_socket_identity,
        kernel_boot_id="test-boot-id",
        time_namespace_id=_hash("c"),
        network_namespace_id=_hash("d"),
        monotonic_clock_domain_id=_hash("e"),
        clock_source_manifest_id=_hash("f"),
        chronyd_launch_id=None,
        chronyd_runtime_observation_sha256=None,
    )
    sensitive_environment_values_sha256 = sha256_digest(
        {
            "domain": "RiskYieldMMA2MSensitiveEnvironmentValuesV4_9F",
            "pairs": [],
        }
    )
    environment_variables_sha256 = sha256_digest(
        {
            "domain": "RiskYieldMMA2MProcessEnvironmentVariablesV4_9F",
            "profile": (
                "REVIEWED_NON_SECRET_VALUES_AND_AGGREGATE_SENSITIVE_VALUE_DIGEST_V2"
            ),
            "safe_values": [],
            "sensitive_presence": [],
            "sensitive_values_sha256": sensitive_environment_values_sha256,
        }
    )
    process_observation = CapacityMeasurementProcessEnvironmentObservationV49F(
        observation_profile="LINUX_PROCESS_AND_OWNER_SQLITE_OBSERVED_LOCAL_V49F_V6",
        captured_at_utc="2026-07-20T08:00:00+02:00",
        capture_started_monotonic_nanoseconds="10",
        capture_completed_monotonic_nanoseconds="20",
        kernel_release=environment.kernel_release,
        kernel_version="test-kernel-version",
        machine_architecture=environment.machine_architecture,
        cpu_model=environment.cpu_model,
        logical_cpu_count=environment.logical_cpu_count,
        cpu_affinity=environment.cpu_affinity,
        python_implementation="CPython",
        python_version=environment.python_version,
        python_full_version="3.12.12 test",
        python_cache_tag="cpython-312",
        python_abi_flags="NONE",
        python_executable_path="/usr/bin/python3",
        python_executable_sha256=_hash("1"),
        platform_tag="linux-x86_64",
        sys_flags=(("debug", "0"),),
        sys_path_sha256=_hash("2"),
        meta_path_profile_sha256=_hash("3"),
        event_loop_implementation=environment.event_loop_implementation,
        event_loop_policy_implementation="asyncio.DefaultEventLoopPolicy",
        openssl_version=environment.openssl_version,
        websockets_version=environment.websockets_version,
        sqlite_version=environment.sqlite_version,
        filesystem_type=environment.filesystem_type,
        filesystem_mount_identity_sha256=_hash("4"),
        database_path="/tmp/riskyieldmm-test.sqlite3",
        database_device=1,
        database_inode=2,
        storage_identity_sha256=environment.storage_identity_sha256,
        sqlite_pragmas=_TEST_SQLITE_PRAGMAS,
        sqlite_pragmas_sha256=environment.sqlite_pragmas_sha256,
        kernel_boot_id=runtime_observation.kernel_boot_id,
        time_namespace_id=runtime_observation.time_namespace_id,
        network_namespace_id=runtime_observation.network_namespace_id,
        mount_namespace_id=_hash("5"),
        pid_namespace_id=_hash("6"),
        cgroup_namespace_id=_hash("7"),
        cgroup_membership_sha256=_hash("8"),
        environment_value_profile=(
            "REVIEWED_NON_SECRET_VALUES_AND_AGGREGATE_SENSITIVE_VALUE_DIGEST_V2"
        ),
        safe_environment_values=(),
        sensitive_environment_presence=(),
        sensitive_environment_values_sha256=sensitive_environment_values_sha256,
        environment_sha256=environment_variables_sha256,
        loader_injection_present=False,
    )
    subject_payload = {
        "authority_profile": A2M_OBSERVED_LOCAL_AUTHORITY_PROFILE_V49F,
        "external_attestation_status": A2M_EXTERNAL_ATTESTATION_STATUS_V49F,
        "manifest_request_id": request.manifest_request_id,
        "source_observation_id": source_observation.source_observation_id,
        "runtime_observation_id": runtime_observation.runtime_observation_id,
        "environment_observation_id": process_observation.environment_observation_id,
        "deployment_bundle_id": runtime_observation.deployment_bundle_id,
        "deployment_trust_root_id": runtime_observation.deployment_trust_root_id,
        "collector_release_manifest_id": (
            runtime_observation.collector_release_manifest_id
        ),
        "runtime_environment_manifest_id": (
            runtime_observation.runtime_environment_manifest_id
        ),
        "transport_session_id": transport_session_id,
        "driver_evidence_nonce_sha256": runtime_observation.driver_evidence_nonce_sha256,
        "kernel_socket_identity": runtime_observation.kernel_socket_identity,
        "transport_capacity_policy_id": (
            runtime_observation.transport_capacity_policy_id
        ),
        "started_at_utc": "2026-07-20T06:00:00Z",
        "monotonic_origin_nanoseconds": monotonic_origin_nanoseconds,
        "boottime_origin_nanoseconds": boottime_origin_nanoseconds,
        "loop_time_origin_nanoseconds": loop_time_origin_nanoseconds,
        "promotion_eligible": False,
    }
    authority_subject_id = (
        derive_capacity_measurement_manifest_authority_subject_id_v49f(subject_payload)
    )
    signature = _TEST_MANIFEST_SIGNER.sign(
        canonical_json_bytes(
            capacity_measurement_authority_subject_signing_payload_v49f(
                authority_subject_id=authority_subject_id,
                deployment_bundle_id=runtime_observation.deployment_bundle_id,
                collector_attestation_key_id=collector_key_id,
                transport_session_id=transport_session_id,
            )
        )
    )
    manifest_authority = CapacityMeasurementManifestAuthorityV49F(
        **subject_payload,
        authority_subject_id=authority_subject_id,
        signature_algorithm=A2M_MANIFEST_AUTHORITY_SIGNATURE_ALGORITHM_V49F,
        collector_attestation_key_id=collector_key_id,
        collector_attestation_public_key_hex=(
            _TEST_MANIFEST_SIGNER.public_key_bytes.hex()
        ),
        signature_hex=signature.hex(),
    )
    return CapacityMeasurementManifestV49F(
        campaign_label="v49f-a2m-exploratory",
        phase=CapacityMeasurementCampaignPhaseV49F.EXPLORATORY,
        started_at_utc="2026-07-20T08:00:00+02:00",
        source_revision="4b3e9eda62c09564ce4626087383eeed9f5faea9",
        source_identity_sha256=source_tree_sha256,
        source_tree_clean=False,
        runtime_identity_sha256=runtime_observation.runtime_observation_id,
        workload_corpus_sha256=workload_corpus_sha256,
        transport_capacity_policy_id=transport_capacity_policy_id,
        transport_runtime_version=runtime_observation.transport_runtime_schema_version,
        transport_session_id=transport_session_id,
        driver_evidence_nonce_sha256=driver_evidence_nonce_sha256,
        kernel_socket_identity=kernel_socket_identity,
        monotonic_origin_nanoseconds=monotonic_origin_nanoseconds,
        boottime_origin_nanoseconds=boottime_origin_nanoseconds,
        loop_time_origin_nanoseconds=loop_time_origin_nanoseconds,
        workloads=workloads,
        environment=environment,
        design=design,
        manifest_request=request,
        source_observation=source_observation,
        runtime_observation=runtime_observation,
        process_environment_observation=process_observation,
        manifest_authority=manifest_authority,
    )


def _snapshot(
    offset: int,
    *,
    unavailable: tuple[str, ...] = (),
    actor_event_count: int = 2,
) -> CapacityMeasurementLayerSnapshotV49F:
    values: dict[str, object] = {
        "kernel_socket_identity": _hash("b"),
        "effective_so_rcvbuf_octets": 262_144,
        "effective_so_sndbuf_octets": 262_144,
        "siocinq_queued_octets": 0,
        "siocoutq_queued_octets": 0,
        "driver_state": "WS_OPEN_BOUND",
        "memory_bio_incoming_pending_octets": 0,
        "memory_bio_outgoing_pending_octets": 0,
        "ssl_plaintext_pending_octets": 0,
        "pending_raw_chunks": 0,
        "pending_raw_octets": 0,
        "durable_ingress_buffer_octets": 0,
        "has_complete_durable_unit": False,
        "protocol_output_chunks": 0,
        "protocol_output_octets": 0,
        "pending_send_eof": False,
        "staged_websocket_wire_chunks": 0,
        "staged_websocket_wire_octets": 0,
        "pending_tls_ciphertext_octets": 0,
        "remaining_pending_tls_ciphertext_octets": 0,
        "staged_tls_ciphertext_octets": 0,
        "remaining_staged_tls_ciphertext_octets": 0,
        "staged_tls_control_ciphertext_octets": 0,
        "remaining_staged_tls_control_ciphertext_octets": 0,
        "admission_active_commands": 0,
        "admission_waiting_commands": 0,
        "admission_reserved_work_units": 0,
        "admission_capacity_rejections": 0,
        "admission_queue_wait_nanoseconds": 0,
        "actor_event_count": actor_event_count,
        "actor_wire_queue_events": 0,
        "actor_wire_queue_octets": 0,
        "sqlite_database_bytes": 16_384,
        "sqlite_journal_bytes": 0,
        "sqlite_wal_bytes": 0,
        "sqlite_shm_bytes": 0,
        "sqlite_page_count": 4,
        "sqlite_freelist_count": 0,
        "process_rss_bytes": 10_000_000,
        "process_pss_bytes": 9_000_000,
        "cgroup_memory_bytes": 11_000_000,
        "event_loop_lag_nanoseconds": 10,
    }
    for name in unavailable:
        values[name] = None
    adapter_fields = (
        (
            "ACTOR",
            (
                "actor_event_count",
                "actor_wire_queue_events",
                "actor_wire_queue_octets",
            ),
        ),
        (
            "ADMISSION",
            (
                "admission_active_commands",
                "admission_capacity_rejections",
                "admission_queue_wait_nanoseconds",
                "admission_reserved_work_units",
                "admission_waiting_commands",
            ),
        ),
        ("EVENT_LOOP", ("event_loop_lag_nanoseconds",)),
        (
            "PROCESS",
            ("cgroup_memory_bytes", "process_pss_bytes", "process_rss_bytes"),
        ),
        (
            "SQLITE",
            (
                "sqlite_database_bytes",
                "sqlite_freelist_count",
                "sqlite_journal_bytes",
                "sqlite_shm_bytes",
                "sqlite_page_count",
                "sqlite_wal_bytes",
            ),
        ),
        (
            "TRANSPORT_FLOW",
            tuple(
                sorted(
                    set(measurement.A2M_LAYER_VALUE_FIELDS_V49F)
                    - {
                        "actor_event_count",
                        "actor_wire_queue_events",
                        "actor_wire_queue_octets",
                        "admission_active_commands",
                        "admission_capacity_rejections",
                        "admission_queue_wait_nanoseconds",
                        "admission_reserved_work_units",
                        "admission_waiting_commands",
                        "event_loop_lag_nanoseconds",
                        "cgroup_memory_bytes",
                        "process_pss_bytes",
                        "process_rss_bytes",
                        "sqlite_database_bytes",
                        "sqlite_freelist_count",
                        "sqlite_journal_bytes",
                        "sqlite_shm_bytes",
                        "sqlite_page_count",
                        "sqlite_wal_bytes",
                    }
                )
            ),
        ),
    )
    spans = tuple(
        CapacityMeasurementAdapterSpanV49F(
            adapter_name=adapter_name,
            observation_method=f"TEST_{adapter_name}",
            observation_started_offset_nanoseconds=offset,
            observation_completed_offset_nanoseconds=offset,
            observed_fields=field_names,
            unavailable_fields=tuple(
                name for name in field_names if name in unavailable
            ),
            unavailable_reason_codes=("OBSERVER_UNAVAILABLE",)
            if any(name in unavailable for name in field_names)
            else (),
        )
        for adapter_name, field_names in adapter_fields
    )
    return CapacityMeasurementLayerSnapshotV49F(
        observation_method="OWNER_LOCKED_COUNTS_PLUS_PROCFS",
        observed_offset_nanoseconds=offset,
        adapter_spans=spans,
        unavailable_fields=unavailable,
        unavailable_reason_codes=("OBSERVER_UNAVAILABLE",) if unavailable else (),
        **values,
    )


def _runtime_boundary(
    manifest: CapacityMeasurementManifestV49F,
    *,
    role: str,
    capture_start: int,
    actor_event_count: int,
    actor_tail_event_id: str,
    released_commands: int,
) -> CapacityMeasurementRuntimeBoundaryEvidenceV49F:
    return CapacityMeasurementRuntimeBoundaryEvidenceV49F(
        boundary_role=role,
        capture_started_offset_nanoseconds=capture_start,
        capture_completed_offset_nanoseconds=capture_start + 1,
        transport_session_id=manifest.transport_session_id,
        driver_evidence_nonce_sha256=manifest.driver_evidence_nonce_sha256,
        kernel_socket_identity=manifest.kernel_socket_identity,
        transport_capacity_policy_id=manifest.transport_capacity_policy_id,
        admission_epoch=1,
        admission_closed=False,
        admission_terminal_barrier_admission_sequence=None,
        admission_terminal_barrier_committed=False,
        admission_active_admission_sequence=None,
        admission_active_command_kind=None,
        admission_waiting_admission_sequences=(),
        admission_waiting_command_kinds=(),
        admission_oldest_waiting_age_nanoseconds=0,
        admission_reserved_work_units=0,
        admission_maximum_observed_admitted_commands=(
            0 if released_commands == 0 else 1
        ),
        admission_maximum_observed_reserved_work_units=(
            0 if released_commands == 0 else 1
        ),
        admission_last_started_queue_wait_nanoseconds=0,
        admission_maximum_observed_queue_wait_nanoseconds=0,
        admission_released_commands=released_commands,
        admission_rejected_commands=0,
        admission_duplicate_kind_rejections=0,
        admission_terminal_barrier_rejections=0,
        admission_capacity_rejections=0,
        admission_closed_rejections=0,
        admission_timed_out_commands=0,
        admission_cancelled_before_entry_commands=0,
        admission_closed_before_entry_commands=0,
        actor_event_count=actor_event_count,
        actor_tail_event_id=actor_tail_event_id,
        actor_wire_queue_events=0,
        actor_wire_queue_octets=0,
        runtime_state="ACK_BOUND",
    )


def _sample(
    manifest: CapacityMeasurementManifestV49F,
    *,
    sequence: int,
    is_warmup: bool,
    parent_sample_id: str | None,
    process_rss_bytes: int = 10_000_000,
) -> CapacityMeasurementSampleV49F:
    start = sequence * 1_000
    workload_spec = CapacityMeasurementIngressWorkloadSpecV49F.from_manifest_json(
        manifest.workloads[0].workload_manifest_json
    )
    parser_event_id = hashlib.sha256(f"parser-{sequence}".encode("ascii")).hexdigest()
    actor_tail_before = hashlib.sha256(
        f"actor-before-{sequence}".encode("ascii")
    ).hexdigest()
    actor_before = sequence * 2
    initial_boundary = _runtime_boundary(
        manifest,
        role="INITIAL",
        capture_start=start + 1,
        actor_event_count=actor_before,
        actor_tail_event_id=actor_tail_before,
        released_commands=sequence - 1,
    )
    before_boundary = _runtime_boundary(
        manifest,
        role="BEFORE_OPERATION",
        capture_start=start + 80,
        actor_event_count=actor_before,
        actor_tail_event_id=actor_tail_before,
        released_commands=sequence - 1,
    )
    after_boundary = _runtime_boundary(
        manifest,
        role="AFTER_OPERATION",
        capture_start=start + 220,
        actor_event_count=actor_before + 1,
        actor_tail_event_id=parser_event_id,
        released_commands=sequence,
    )
    progress = CapacityMeasurementIngressProgressEvidenceV49F(
        raw_ingress_commit_id=hashlib.sha256(
            f"raw-ingress-{sequence}".encode("ascii")
        ).hexdigest(),
        ingress_sequence=sequence,
        committed_raw_octets=2,
        raw_ingress_batch_sha256=workload_spec.raw_ingress_batch_sha256,
        parser_event_ids=(parser_event_id,),
        automatic_output_source_parser_event_ids=(),
        automatic_dispatch_completion_event_ids=(),
        automatic_protocol_output_base64="",
        automatic_protocol_output_chunk_octet_counts=(),
        automatic_output_wire_chunk_counts=(),
        automatic_protocol_output_frames=(),
        actor_event_count_before=actor_before,
        actor_tail_event_id_before=actor_tail_before,
        actor_event_count_after=actor_before + 1,
        actor_tail_event_id_after=parser_event_id,
        retained_incomplete_octets=0,
        used_initial_pending_ingress=False,
        websocket_parser_state="OPEN",
        admission_policy_id=manifest.transport_capacity_policy_id,
        admission_epoch=1,
        admission_sequence=sequence,
        admission_command_kind="INGRESS",
        admission_reservation_work_units=1,
        admission_admitted_loop_time_offset_nanoseconds=start + 100,
        admission_started_loop_time_offset_nanoseconds=start + 100,
        admission_start_deadline_loop_time_offset_nanoseconds=start + 200,
        admission_queue_wait_nanoseconds=0,
    )
    return CapacityMeasurementSampleV49F(
        campaign_manifest_id=manifest.campaign_manifest_id,
        manifest_authority_id=manifest.manifest_authority.manifest_authority_id,
        transport_session_id=manifest.transport_session_id,
        driver_evidence_nonce_sha256=manifest.driver_evidence_nonce_sha256,
        kernel_socket_identity=manifest.kernel_socket_identity,
        source_identity_sha256=manifest.source_identity_sha256,
        runtime_identity_sha256=manifest.runtime_identity_sha256,
        workload_corpus_sha256=manifest.workload_corpus_sha256,
        measurement_design_id=manifest.design.measurement_design_id,
        sample_sequence=sequence,
        parent_sample_id=parent_sample_id,
        workload_id=manifest.workloads[0].workload_id,
        workload_sha256=manifest.workloads[0].workload_sha256,
        trial_index=sequence - 1,
        repetition_index=0,
        is_warmup=is_warmup,
        stage="INTEGRATED_INGRESS",
        observer_start_offset_nanoseconds=start,
        observer_end_offset_nanoseconds=start + 300,
        boottime_start_offset_nanoseconds=start + 10,
        boottime_end_offset_nanoseconds=start + 310,
        loop_time_start_offset_nanoseconds=start + 20,
        loop_time_end_offset_nanoseconds=start + 320,
        operation_start_offset_nanoseconds=start + 100,
        operation_end_offset_nanoseconds=start + 200,
        initial_runtime_boundary=initial_boundary,
        before_runtime_boundary=before_boundary,
        returned_ingress_progress=progress,
        returned_ingress_progress_unavailable_reason=None,
        after_runtime_boundary=after_boundary,
        raw_ingress_commit_id=hashlib.sha256(
            f"raw-ingress-{sequence}".encode("ascii")
        ).hexdigest(),
        raw_ingress_sequence=sequence,
        raw_ingress_batch_sha256=workload_spec.raw_ingress_batch_sha256,
        parser_event_ids=(parser_event_id,),
        automatic_output_source_parser_event_ids=(),
        automatic_dispatch_completion_event_ids=(),
        automatic_output_wire_chunk_counts=(),
        admission_attribution="EXACT_RETURNED_GRANT",
        admission_policy_id=manifest.transport_capacity_policy_id,
        admission_epoch=1,
        admission_sequence=sequence,
        admission_queue_wait_nanoseconds=0,
        input_chunk_count=1,
        input_octet_count=2,
        input_sha256=hashlib.sha256(b"\x8a\x00").hexdigest(),
        output_chunk_count=0,
        output_octet_count=0,
        observed_output_sha256=hashlib.sha256(b"").hexdigest(),
        observed_output_batch_sha256=sha256_digest(
            {
                "domain": "RiskYieldMMA2MExactOrderedOutputChunksV4_9F",
                "ordered_chunks_base64": [],
            }
        ),
        output_frame_count=0,
        expected_output_frame_count=0,
        observed_output_frames_sha256=(workload_spec.expected_output_frames_sha256),
        expected_output_frames_sha256=(workload_spec.expected_output_frames_sha256),
        before_snapshot=replace(
            _snapshot(start + 50, actor_event_count=actor_before),
            process_rss_bytes=process_rss_bytes,
        ),
        in_operation_snapshot=replace(
            _snapshot(start + 150, actor_event_count=actor_before + 1),
            process_rss_bytes=process_rss_bytes,
        ),
        after_snapshot=replace(
            _snapshot(start + 210, actor_event_count=actor_before + 1),
            process_rss_bytes=process_rss_bytes,
        ),
        operation_outcome=CapacityMeasurementOutcomeV49F.PASS,
        operation_error_code=None,
        operation_exception_class=None,
        measurement_outcome=CapacityMeasurementOutcomeV49F.PASS,
        measurement_error_code=None,
    )


def _samples(
    manifest: CapacityMeasurementManifestV49F,
    *,
    measured_process_rss_bytes: int = 10_000_000,
) -> tuple[CapacityMeasurementSampleV49F, ...]:
    warmup = _sample(
        manifest,
        sequence=1,
        is_warmup=True,
        parent_sample_id=None,
    )
    measured = _sample(
        manifest,
        sequence=2,
        is_warmup=False,
        parent_sample_id=warmup.sample_id,
        process_rss_bytes=measured_process_rss_bytes,
    )
    return warmup, measured


def _with_exact_pong_output(
    sample: CapacityMeasurementSampleV49F,
) -> CapacityMeasurementSampleV49F:
    payload = b"ok"
    mask = b"\x01\x02\x03\x04"
    wire = (
        bytes((0x8A, 0x80 | len(payload)))
        + mask
        + bytes(value ^ mask[index % 4] for index, value in enumerate(payload))
    )
    chunks = (wire[:2], wire[2:])
    completion_id = _hash("d")
    assert sample.returned_ingress_progress is not None
    assert sample.parser_event_ids is not None
    progress = replace(
        sample.returned_ingress_progress,
        automatic_output_source_parser_event_ids=(sample.parser_event_ids[0],),
        automatic_dispatch_completion_event_ids=(completion_id,),
        automatic_protocol_output_base64=base64.b64encode(wire).decode("ascii"),
        automatic_protocol_output_chunk_octet_counts=tuple(map(len, chunks)),
        automatic_output_wire_chunk_counts=(len(chunks),),
        automatic_protocol_output_frames=(
            CapacityMeasurementLogicalOutputFrameV49F(
                opcode="PONG",
                payload_base64=base64.b64encode(payload).decode("ascii"),
            ),
        ),
        ingress_progress_evidence_id=None,
    )
    return replace(
        sample,
        returned_ingress_progress=progress,
        automatic_output_source_parser_event_ids=(sample.parser_event_ids[0],),
        automatic_dispatch_completion_event_ids=(completion_id,),
        automatic_output_wire_chunk_counts=(len(chunks),),
        output_chunk_count=len(chunks),
        output_octet_count=len(wire),
        observed_output_sha256=hashlib.sha256(wire).hexdigest(),
        observed_output_batch_sha256=sha256_digest(
            {
                "domain": "RiskYieldMMA2MExactOrderedOutputChunksV4_9F",
                "ordered_chunks_base64": [
                    base64.b64encode(chunk).decode("ascii") for chunk in chunks
                ],
            }
        ),
        output_frame_count=1,
        observed_output_frames_sha256=(
            measurement.capacity_measurement_logical_frames_sha256_v49f(
                (("PONG", payload),)
            )
        ),
        operation_outcome=CapacityMeasurementOutcomeV49F.FAIL,
        operation_error_code="EXPECTED_LOGICAL_OUTPUT_MISMATCH",
        sample_id=None,
    )


def _unfinalized_correctness(
    manifest: CapacityMeasurementManifestV49F,
    samples: tuple[CapacityMeasurementSampleV49F, ...],
) -> CapacityMeasurementCorrectnessV49F:
    return CapacityMeasurementCorrectnessV49F(
        campaign_manifest_id=manifest.campaign_manifest_id,
        transport_session_id=manifest.transport_session_id,
        driver_evidence_nonce_sha256=manifest.driver_evidence_nonce_sha256,
        kernel_socket_identity=manifest.kernel_socket_identity,
        sample_stream_sha256=capacity_measurement_sample_stream_sha256_v49f(
            samples, manifest=manifest
        ),
        sample_count=len(samples),
        first_sample_id=samples[0].sample_id,
        last_sample_id=samples[-1].sample_id,
        raw_ingress_root_sha256=_hash("1"),
        actor_event_root_sha256=_hash("2"),
        projection_root_sha256=_hash("3"),
        no_loss=False,
        no_duplication=False,
        no_reordering=False,
        control_output_causal=False,
        projection_verified=False,
        observations_complete=True,
        cleanup_complete=False,
        failure_codes=(measurement.A2M_CORRECTNESS_FINALIZER_NOT_IMPLEMENTED_V49F,),
    )


def _pass_correctness_mapping(
    manifest: CapacityMeasurementManifestV49F,
    samples: tuple[CapacityMeasurementSampleV49F, ...],
) -> dict[str, object]:
    payload = _unfinalized_correctness(manifest, samples).as_dict()
    for name in CapacityMeasurementCorrectnessV49F._BOOLEAN_FIELDS:
        payload[name] = True
    payload["failure_codes"] = []
    payload["correctness_id"] = measurement._semantic_identity_v49f(  # noqa: SLF001
        domain=measurement.A2M_CORRECTNESS_DOMAIN_V49F,
        payload={
            item.name: payload[item.name]
            for item in fields(CapacityMeasurementCorrectnessV49F)
            if item.name != "correctness_id"
        },
    )
    return payload


def _forged_pass_correctness(
    manifest: CapacityMeasurementManifestV49F,
    samples: tuple[CapacityMeasurementSampleV49F, ...],
) -> CapacityMeasurementCorrectnessV49F:
    payload = _pass_correctness_mapping(manifest, samples)
    forged = object.__new__(CapacityMeasurementCorrectnessV49F)
    for item in fields(CapacityMeasurementCorrectnessV49F):
        value = payload[item.name]
        if item.name == "failure_codes":
            value = tuple(value)  # type: ignore[arg-type]
        object.__setattr__(forged, item.name, value)
    return forged


def _bundle(
    *, measured_process_rss_bytes: int = 10_000_000
) -> CapacityMeasurementArtifactBundleV49F:
    manifest = _manifest()
    samples = _samples(manifest, measured_process_rss_bytes=measured_process_rss_bytes)
    return CapacityMeasurementArtifactBundleV49F.build(
        manifest=manifest,
        samples=samples,
        correctness=_unfinalized_correctness(manifest, samples),
    )


def test_exploratory_manifest_is_canonical_session_bound_and_long_uptime_safe() -> None:
    manifest = _manifest()

    assert int(manifest.monotonic_origin_nanoseconds) > (1 << 53)
    assert isinstance(manifest.monotonic_origin_nanoseconds, str)
    assert manifest.environment.cpu_affinity == (1, 2, 3)
    encoded = encode_capacity_measurement_json_v49f(manifest)
    assert (
        decode_capacity_measurement_json_v49f(
            encoded,
            record_type=CapacityMeasurementManifestV49F,
        )
        == manifest
    )

    with pytest.raises(CanonicalizationError, match="exact.*Phase"):
        replace(manifest, phase="CALIBRATION")  # type: ignore[arg-type]
    with pytest.raises(CanonicalizationError, match="leading zeroes"):
        _manifest(monotonic_origin_nanoseconds="09007199254740993")


def test_records_are_self_describing_versioned_and_domain_separated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = _manifest()
    manifest_payload = manifest.as_dict()

    assert manifest_payload["canonicalization_version"] == CANONICALIZATION_VERSION
    assert (
        manifest_payload["measurement_schema_version"]
        == measurement.A2M_MEASUREMENT_SCHEMA_VERSION_V49F
    )
    assert manifest_payload["record_domain"] == measurement.A2M_MANIFEST_DOMAIN_V49F
    routed = strict_json_loads(encode_capacity_measurement_json_v49f(manifest))
    assert routed["measurement_schema_version"] == (
        measurement.A2M_MEASUREMENT_SCHEMA_VERSION_V49F
    )

    domains = {
        measurement.A2M_ENVIRONMENT_DOMAIN_V49F,
        measurement.A2M_DESIGN_DOMAIN_V49F,
        measurement.A2M_MANIFEST_DOMAIN_V49F,
        measurement.A2M_SAMPLE_DOMAIN_V49F,
        measurement.A2M_CORRECTNESS_DOMAIN_V49F,
        measurement.A2M_INTEGRITY_DOMAIN_V49F,
    }
    assert len(domains) == 6
    assert len(
        {
            measurement._semantic_identity_v49f(  # noqa: SLF001
                domain=domain, payload={"same": "payload"}
            )
            for domain in domains
        }
    ) == len(domains)

    original_environment_id = _environment().environment_id
    monkeypatch.setattr(
        measurement,
        "A2M_MEASUREMENT_SCHEMA_VERSION_V49F",
        "riskyieldmm_physical_transport_a2m_raw_v49f_v4-test",
    )
    assert _environment().environment_id != original_environment_id


@pytest.mark.parametrize(
    ("field", "replacement", "message"),
    [
        ("canonicalization_version", "unsupported", "canonicalization_version"),
        ("measurement_schema_version", "unsupported", "measurement_schema_version"),
        ("record_domain", "unsupported", "record_domain"),
    ],
)
def test_manifest_rejects_wrong_or_missing_self_description(
    field: str, replacement: str, message: str
) -> None:
    payload = _manifest().as_dict()
    payload[field] = replacement
    with pytest.raises(CanonicalizationError, match=message):
        CapacityMeasurementManifestV49F.from_mapping(payload)

    payload = _manifest().as_dict()
    del payload[field]
    with pytest.raises(CanonicalizationError, match="keys do not match schema"):
        CapacityMeasurementManifestV49F.from_mapping(payload)


@pytest.mark.parametrize("phase", ["CALIBRATION", "CONFIRMATION"])
def test_calibration_and_confirmation_manifest_payloads_are_rejected(
    phase: str,
) -> None:
    payload = _manifest().as_dict()
    payload["phase"] = phase

    with pytest.raises(CanonicalizationError, match="exactly EXPLORATORY"):
        CapacityMeasurementManifestV49F.from_mapping(payload)


def test_layer_snapshot_covers_flow_fields_and_null_is_never_zero() -> None:
    snapshot = _snapshot(10, unavailable=("event_loop_lag_nanoseconds",))

    assert snapshot.event_loop_lag_nanoseconds is None
    assert snapshot.siocinq_queued_octets == 0
    assert "event_loop_lag_nanoseconds" in snapshot.unavailable_fields
    assert "siocinq_queued_octets" not in snapshot.unavailable_fields
    assert (
        CapacityMeasurementLayerSnapshotV49F.from_mapping(snapshot.as_dict())
        == snapshot
    )

    with pytest.raises(CanonicalizationError, match="exactly equal every null"):
        replace(snapshot, unavailable_fields=())
    with pytest.raises(CanonicalizationError, match="non-empty iff"):
        replace(snapshot, unavailable_reason_codes=())


def test_adapter_spans_are_exact_temporal_field_partition_and_reason_attribution() -> (
    None
):
    snapshot = _snapshot(10, unavailable=("event_loop_lag_nanoseconds",))

    with pytest.raises(CanonicalizationError, match="frozen adapter field ownership"):
        replace(snapshot, adapter_spans=snapshot.adapter_spans[:-1])
    with pytest.raises(CanonicalizationError, match="last adapter completion"):
        replace(snapshot, observed_offset_nanoseconds=11)
    event_loop_span = next(
        span for span in snapshot.adapter_spans if span.adapter_name == "EVENT_LOOP"
    )
    with pytest.raises(CanonicalizationError, match="completion precedes"):
        replace(
            event_loop_span,
            observation_started_offset_nanoseconds=11,
            observation_completed_offset_nanoseconds=10,
        )
    with pytest.raises(CanonicalizationError, match="attribute every unavailable"):
        replace(
            snapshot,
            adapter_spans=tuple(
                replace(
                    span,
                    unavailable_fields=(),
                    unavailable_reason_codes=(),
                )
                if span.adapter_name == "EVENT_LOOP"
                else span
                for span in snapshot.adapter_spans
            ),
        )


def test_adapter_spans_reject_renamed_adapters_and_cross_adapter_field_swaps() -> None:
    snapshot = _snapshot(10)
    actor = next(
        span for span in snapshot.adapter_spans if span.adapter_name == "ACTOR"
    )
    admission = next(
        span for span in snapshot.adapter_spans if span.adapter_name == "ADMISSION"
    )

    with pytest.raises(CanonicalizationError, match="frozen adapter field ownership"):
        replace(
            snapshot,
            adapter_spans=tuple(
                replace(span, adapter_name="ACTOR_RENAMED") if span is actor else span
                for span in snapshot.adapter_spans
            ),
        )

    swapped_spans = tuple(
        replace(
            span,
            observed_fields=tuple(
                sorted(
                    (set(span.observed_fields) - {"actor_event_count"})
                    | {"admission_active_commands"}
                )
            ),
        )
        if span is actor
        else replace(
            span,
            observed_fields=tuple(
                sorted(
                    (set(span.observed_fields) - {"admission_active_commands"})
                    | {"actor_event_count"}
                )
            ),
        )
        if span is admission
        else span
        for span in snapshot.adapter_spans
    )
    with pytest.raises(CanonicalizationError, match="frozen adapter field ownership"):
        replace(snapshot, adapter_spans=swapped_spans)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"effective_so_rcvbuf_octets": 0}, "must be at least 1"),
        ({"driver_state": "IMPOSSIBLE_STATE"}, "outside the V4.9 state machine"),
        (
            {"pending_raw_chunks": 0, "pending_raw_octets": 10},
            "zero states differ",
        ),
        (
            {
                "staged_tls_ciphertext_octets": 10,
                "remaining_staged_tls_ciphertext_octets": 11,
            },
            "exceeds",
        ),
        (
            {
                "staged_tls_control_ciphertext_octets": 10,
                "remaining_staged_tls_control_ciphertext_octets": 0,
            },
            "zero states differ",
        ),
        (
            {
                "has_complete_durable_unit": True,
                "durable_ingress_buffer_octets": 0,
            },
            "requires retained durable ingress bytes",
        ),
        (
            {"pending_raw_chunks": 129, "pending_raw_octets": 65_536},
            "frozen V4.9 bound",
        ),
        (
            {"pending_raw_chunks": 128, "pending_raw_octets": 65_537},
            "frozen V4.9 bound",
        ),
        (
            {"durable_ingress_buffer_octets": 1_114_127},
            "frozen V4.9 bound",
        ),
        (
            {
                "staged_websocket_wire_chunks": 33,
                "staged_websocket_wire_octets": 65_536,
            },
            "frozen V4.9 bound",
        ),
        (
            {
                "staged_websocket_wire_chunks": 32,
                "staged_websocket_wire_octets": 65_537,
            },
            "frozen V4.9 bound",
        ),
        (
            {
                "staged_tls_ciphertext_octets": 4_194_305,
                "remaining_staged_tls_ciphertext_octets": 4_194_305,
            },
            "frozen V4.9 bound",
        ),
    ],
)
def test_layer_snapshot_rejects_impossible_typed_flow_states(
    changes: dict[str, object], message: str
) -> None:
    with pytest.raises(CanonicalizationError, match=message):
        replace(_snapshot(10), **changes)


def test_frozen_layer_bounds_match_the_current_v49_source_snapshot_contract() -> None:
    assert (
        measurement.A2M_MAXIMUM_PENDING_RAW_CHUNKS_V49F
        == V4_CONTROL_MAXIMUM_INGRESS_CHUNKS
    )
    assert (
        measurement.A2M_MAXIMUM_PENDING_RAW_OCTETS_V49F
        == V4_CONTROL_MAXIMUM_INGRESS_BYTES
        == V49_MAXIMUM_POST_UPGRADE_PENDING_BYTES
    )
    assert (
        measurement.A2M_MAXIMUM_DURABLE_INGRESS_OCTETS_V49F
        == V49D_MAXIMUM_DURABLE_INGRESS_BUFFER_BYTES
        == (
            V49_MAXIMUM_WEBSOCKET_MESSAGE_BYTES
            + V49_MAXIMUM_POST_UPGRADE_PENDING_BYTES
            + 14
        )
    )
    assert (
        measurement.A2M_MAXIMUM_STAGED_WIRE_CHUNKS_V49F
        == V49C_MAXIMUM_STAGED_WIRE_CHUNKS
    )
    assert (
        measurement.A2M_MAXIMUM_STAGED_WIRE_OCTETS_V49F
        == V49C_MAXIMUM_STAGED_WIRE_OCTETS
    )
    assert (
        measurement.A2M_MAXIMUM_TLS_CIPHERTEXT_OCTETS_V49F
        == V49_MAXIMUM_TLS_OPERATION_CIPHERTEXT_BYTES
    )


def test_samples_are_canonical_contiguous_parent_linked_and_schedule_exact() -> None:
    manifest = _manifest()
    samples = _samples(manifest)
    payload = encode_capacity_measurement_samples_jsonl_v49f(samples, manifest=manifest)

    assert payload.endswith(b"\n")
    first_record = strict_json_loads(payload.splitlines()[0])
    assert first_record["canonicalization_version"] == CANONICALIZATION_VERSION
    assert (
        first_record["measurement_schema_version"]
        == measurement.A2M_MEASUREMENT_SCHEMA_VERSION_V49F
    )
    assert first_record["record_domain"] == measurement.A2M_SAMPLE_DOMAIN_V49F
    assert (
        decode_capacity_measurement_samples_jsonl_v49f(payload, manifest=manifest)
        == samples
    )
    assert samples[1].duration_nanoseconds == 300

    bad_sequence = replace(samples[1], sample_sequence=3, sample_id=None)
    with pytest.raises(CanonicalizationError, match="contiguous"):
        validate_capacity_measurement_samples_v49f(
            (samples[0], bad_sequence), manifest=manifest
        )
    bad_parent = replace(samples[1], parent_sample_id=_hash("0"), sample_id=None)
    with pytest.raises(CanonicalizationError, match="immediately preceding"):
        validate_capacity_measurement_samples_v49f(
            (samples[0], bad_parent), manifest=manifest
        )
    with pytest.raises(CanonicalizationError, match="frozen deterministic schedule"):
        validate_capacity_measurement_samples_v49f((samples[0],), manifest=manifest)

    measured_first = replace(samples[0], is_warmup=False, sample_id=None)
    warmup_second = replace(
        samples[1],
        is_warmup=True,
        parent_sample_id=measured_first.sample_id,
        sample_id=None,
    )
    with pytest.raises(CanonicalizationError, match="frozen deterministic schedule"):
        validate_capacity_measurement_samples_v49f(
            (measured_first, warmup_second), manifest=manifest
        )


def test_sample_causality_and_raw_ingress_sequence_cannot_move_backward() -> None:
    manifest = _manifest()
    samples = _samples(manifest)
    backward_child = replace(
        samples[1],
        observer_start_offset_nanoseconds=0,
        observer_end_offset_nanoseconds=300,
        boottime_start_offset_nanoseconds=10,
        boottime_end_offset_nanoseconds=310,
        loop_time_start_offset_nanoseconds=20,
        loop_time_end_offset_nanoseconds=320,
        operation_start_offset_nanoseconds=100,
        operation_end_offset_nanoseconds=200,
        initial_runtime_boundary=replace(
            samples[1].initial_runtime_boundary,
            capture_started_offset_nanoseconds=1,
            capture_completed_offset_nanoseconds=2,
            boundary_evidence_id=None,
        ),
        before_runtime_boundary=replace(
            samples[1].before_runtime_boundary,
            capture_started_offset_nanoseconds=80,
            capture_completed_offset_nanoseconds=81,
            boundary_evidence_id=None,
        ),
        returned_ingress_progress=replace(
            samples[1].returned_ingress_progress,
            admission_admitted_loop_time_offset_nanoseconds=100,
            admission_started_loop_time_offset_nanoseconds=100,
            admission_start_deadline_loop_time_offset_nanoseconds=200,
            ingress_progress_evidence_id=None,
        ),
        after_runtime_boundary=replace(
            samples[1].after_runtime_boundary,
            capture_started_offset_nanoseconds=220,
            capture_completed_offset_nanoseconds=221,
            boundary_evidence_id=None,
        ),
        before_snapshot=_snapshot(50, actor_event_count=4),
        in_operation_snapshot=_snapshot(150, actor_event_count=5),
        after_snapshot=_snapshot(210, actor_event_count=5),
        sample_id=None,
    )
    with pytest.raises(CanonicalizationError, match="parent completed"):
        validate_capacity_measurement_samples_v49f(
            (samples[0], backward_child), manifest=manifest
        )

    first = replace(
        samples[0],
        raw_ingress_sequence=2,
        returned_ingress_progress=replace(
            samples[0].returned_ingress_progress,
            ingress_sequence=2,
            ingress_progress_evidence_id=None,
        ),
        sample_id=None,
    )
    second = replace(
        samples[1],
        parent_sample_id=first.sample_id,
        raw_ingress_sequence=1,
        returned_ingress_progress=replace(
            samples[1].returned_ingress_progress,
            ingress_sequence=1,
            ingress_progress_evidence_id=None,
        ),
        sample_id=None,
    )
    with pytest.raises(CanonicalizationError, match="strictly forward"):
        validate_capacity_measurement_samples_v49f((first, second), manifest=manifest)

    duplicate_admission = replace(
        samples[1],
        admission_sequence=samples[0].admission_sequence,
        returned_ingress_progress=replace(
            samples[1].returned_ingress_progress,
            admission_sequence=samples[0].admission_sequence,
            ingress_progress_evidence_id=None,
        ),
        sample_id=None,
    )
    with pytest.raises(CanonicalizationError, match="admission sequence"):
        validate_capacity_measurement_samples_v49f(
            (samples[0], duplicate_admission), manifest=manifest
        )

    reused_actor_event = replace(
        samples[1],
        parser_event_ids=samples[0].parser_event_ids,
        returned_ingress_progress=replace(
            samples[1].returned_ingress_progress,
            parser_event_ids=samples[0].parser_event_ids,
            ingress_progress_evidence_id=None,
        ),
        sample_id=None,
    )
    with pytest.raises(CanonicalizationError, match="multiple samples"):
        validate_capacity_measurement_samples_v49f(
            (samples[0], reused_actor_event), manifest=manifest
        )


def test_operation_measurement_and_clock_domains_are_separate_and_bundle_derived() -> (
    None
):
    manifest = _manifest()
    samples = _samples(manifest)
    incomplete = replace(
        samples[1],
        measurement_outcome=CapacityMeasurementOutcomeV49F.ERROR,
        measurement_error_code="INJECTED_OBSERVER_FAILURE",
        sample_id=None,
    )
    assert incomplete.operation_outcome is CapacityMeasurementOutcomeV49F.PASS
    assert incomplete.measurement_outcome is CapacityMeasurementOutcomeV49F.ERROR

    incorrect_claim = _unfinalized_correctness(manifest, (samples[0], incomplete))
    with pytest.raises(CanonicalizationError, match="observations_complete"):
        CapacityMeasurementArtifactBundleV49F.build(
            manifest=manifest,
            samples=(samples[0], incomplete),
            correctness=incorrect_claim,
        )
    with pytest.raises(CanonicalizationError, match="attribution is unsupported"):
        replace(
            samples[1],
            admission_attribution="INFERRED_SOLE_CALLER",
            sample_id=None,
        )
    false_negative_claim = replace(
        _unfinalized_correctness(manifest, samples),
        observations_complete=False,
        correctness_id=None,
    )
    with pytest.raises(CanonicalizationError, match="observations_complete"):
        CapacityMeasurementArtifactBundleV49F.build(
            manifest=manifest,
            samples=samples,
            correctness=false_negative_claim,
        )
    with pytest.raises(CanonicalizationError, match="BOOTTIME end"):
        replace(
            samples[1],
            boottime_end_offset_nanoseconds=(
                samples[1].boottime_start_offset_nanoseconds - 1
            ),
            sample_id=None,
        )

    with pytest.raises(
        CanonicalizationError,
        match="PASS measurement cannot contain unavailable observations",
    ):
        replace(
            samples[1],
            before_snapshot=_snapshot(
                samples[1].before_snapshot.observed_offset_nanoseconds,
                unavailable=("event_loop_lag_nanoseconds",),
            ),
            sample_id=None,
        )


def test_workload_manifest_bytes_and_corpus_root_cannot_be_substituted() -> None:
    manifest = _manifest()
    workload = manifest.workloads[0]
    workload_spec = CapacityMeasurementIngressWorkloadSpecV49F.from_manifest_json(
        workload.workload_manifest_json
    )
    substituted_spec = replace(workload_spec, stage="SUBSTITUTED")
    with pytest.raises(CanonicalizationError, match="workload_sha256 differs"):
        replace(
            workload,
            workload_manifest_json=substituted_spec.workload_manifest_json,
        )
    with pytest.raises(CanonicalizationError, match="workload_corpus_sha256"):
        replace(manifest, workload_corpus_sha256="0" * 64, campaign_manifest_id=None)


def test_ingress_workload_vector_binds_nonempty_ordered_chunks_stage_and_timeout() -> (
    None
):
    with pytest.raises(CanonicalizationError, match="exact ingress workload bounds"):
        CapacityMeasurementIngressWorkloadSpecV49F(
            workload_family="COALESCED_INGRESS_BURST",
            stage="INTEGRATED_INGRESS",
            input_chunks=(),
            expected_output_frames=(),
            timeout_seconds=2,
        )

    first_partition = CapacityMeasurementIngressWorkloadSpecV49F(
        workload_family="COALESCED_INGRESS_BURST",
        stage="INTEGRATED_INGRESS",
        input_chunks=(b"a", b"bc"),
        expected_output_frames=(),
        timeout_seconds=2,
    )
    second_partition = replace(first_partition, input_chunks=(b"ab", b"c"))
    assert b"".join(first_partition.input_chunks) == b"".join(
        second_partition.input_chunks
    )
    assert first_partition.raw_ingress_batch_sha256 != (
        second_partition.raw_ingress_batch_sha256
    )
    assert first_partition.workload_sha256 != second_partition.workload_sha256

    changed_stage = replace(first_partition, stage="DIFFERENT_STAGE")
    changed_timeout = replace(first_partition, timeout_seconds=3)
    assert changed_stage.workload_sha256 != first_partition.workload_sha256
    assert changed_timeout.workload_sha256 != first_partition.workload_sha256
    assert (
        CapacityMeasurementIngressWorkloadSpecV49F.from_manifest_json(
            first_partition.workload_manifest_json
        )
        == first_partition
    )


@pytest.mark.parametrize(
    "frame",
    [
        ("PONG", b"x" * 126),
        ("CLOSE", b"\x03"),
        ("CLOSE", b"\x03\xe7"),
        ("CLOSE", b"\x03\xe8\xff"),
    ],
)
def test_ingress_workload_rejects_invalid_automatic_control_frames(
    frame: tuple[str, bytes],
) -> None:
    with pytest.raises(CanonicalizationError):
        CapacityMeasurementIngressWorkloadSpecV49F(
            workload_family="CONTROL_OUTPUT",
            stage="INTEGRATED_INGRESS",
            input_chunks=(b"x",),
            expected_output_frames=(frame,),
            timeout_seconds=2,
        )


def test_logical_output_oracle_ignores_serialized_mask_but_binds_opcode_payload() -> (
    None
):
    baseline = CapacityMeasurementIngressWorkloadSpecV49F(
        workload_family="CONTROL_OUTPUT",
        stage="INTEGRATED_INGRESS",
        input_chunks=(b"x",),
        expected_output_frames=(("PONG", b"payload"),),
        timeout_seconds=2,
    )
    changed_opcode = replace(
        baseline, expected_output_frames=(("CLOSE", b"\x03\xe8payload"),)
    )
    changed_payload = replace(
        baseline, expected_output_frames=(("PONG", b"different"),)
    )

    assert baseline.expected_output_frames_sha256 != (
        changed_opcode.expected_output_frames_sha256
    )
    assert baseline.expected_output_frames_sha256 != (
        changed_payload.expected_output_frames_sha256
    )
    stale = baseline.workload_manifest_json.replace(
        '"expected_output_frames"', '"expected_output_chunks_base64"'
    )
    with pytest.raises(CanonicalizationError):
        CapacityMeasurementIngressWorkloadSpecV49F.from_manifest_json(stale)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        (
            {
                "output_frame_count": (
                    measurement.A2M_MAXIMUM_AUTOMATIC_OUTPUT_FRAMES_PER_INGRESS_V49F + 1
                )
            },
            "output_frame_count exceeds the aggregate automatic-output bound",
        ),
        (
            {
                "expected_output_frame_count": (
                    measurement.A2M_MAXIMUM_STAGED_WIRE_CHUNKS_V49F + 1
                )
            },
            "expected_output_frame_count exceeds the workload output bound",
        ),
    ],
)
def test_failed_sample_rejects_impossible_logical_output_counts(
    changes: dict[str, object], message: str
) -> None:
    sample = _samples(_manifest())[0]

    with pytest.raises(CanonicalizationError, match=message):
        replace(
            sample,
            **changes,
            operation_outcome=CapacityMeasurementOutcomeV49F.FAIL,
            operation_error_code="EXPECTED_LOGICAL_OUTPUT_MISMATCH",
            sample_id=None,
        )


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        (
            {
                "output_chunk_count": (
                    measurement.A2M_MAXIMUM_RAW_SAMPLE_OUTPUT_CHUNKS_V49F + 1
                )
            },
            "output_chunk_count exceeds the raw-sample source-snapshot bound",
        ),
        (
            {
                "output_octet_count": (
                    measurement.A2M_MAXIMUM_RAW_SAMPLE_SERIALIZED_WEBSOCKET_WIRE_OCTETS_V49F
                    + 1
                )
            },
            (
                "output_octet_count exceeds the serialized WebSocket-wire "
                "source-snapshot bound"
            ),
        ),
    ],
)
def test_failed_sample_rejects_raw_output_above_source_snapshot_bounds(
    changes: dict[str, object], message: str
) -> None:
    sample = _samples(_manifest())[0]

    with pytest.raises(CanonicalizationError, match=message):
        replace(
            sample,
            **changes,
            operation_outcome=CapacityMeasurementOutcomeV49F.FAIL,
            operation_error_code="ADVERSARIAL_IMPOSSIBLE_RAW_OUTPUT",
            sample_id=None,
        )


def test_failed_sample_rejects_per_frame_wire_chunks_above_snapshot_bound() -> None:
    sample = _samples(_manifest())[0]
    impossible_chunk_count = measurement.A2M_MAXIMUM_STAGED_WIRE_CHUNKS_V49F + 1

    with pytest.raises(
        CanonicalizationError,
        match=(
            "automatic_output_wire_chunk_counts must be at most "
            f"{measurement.A2M_MAXIMUM_STAGED_WIRE_CHUNKS_V49F}"
        ),
    ):
        replace(
            sample,
            automatic_output_wire_chunk_counts=(impossible_chunk_count,),
            output_chunk_count=impossible_chunk_count,
            operation_outcome=CapacityMeasurementOutcomeV49F.FAIL,
            operation_error_code="ADVERSARIAL_IMPOSSIBLE_RAW_OUTPUT_GROUPING",
            sample_id=None,
        )


def test_pass_sample_rejects_more_parser_events_than_one_ingress_can_cause() -> None:
    sample = _samples(_manifest())[0]
    impossible_parser_ids = (sample.parser_event_ids[0],) * (
        measurement.A2M_MAXIMUM_AUTOMATIC_OUTPUT_FRAMES_PER_INGRESS_V49F + 1
    )

    with pytest.raises(
        CanonicalizationError,
        match="parser_event_ids exceeds the aggregate ingress-unit bound",
    ):
        replace(
            sample,
            parser_event_ids=impossible_parser_ids,
            sample_id=None,
        )


def test_optional_raw_commit_is_paired_and_sample_output_is_exact() -> None:
    sample = _samples(_manifest())[1]

    with pytest.raises(CanonicalizationError, match="present together"):
        replace(sample, raw_ingress_sequence=None, sample_id=None)
    with pytest.raises(CanonicalizationError, match="exact returned progress"):
        replace(sample, observed_output_sha256=_hash("0"), sample_id=None)
    with pytest.raises(CanonicalizationError, match="exact returned progress"):
        replace(sample, observed_output_frames_sha256=_hash("0"), sample_id=None)
    with pytest.raises(CanonicalizationError, match="returned progress"):
        replace(
            sample,
            raw_ingress_commit_id=None,
            raw_ingress_sequence=None,
            raw_ingress_batch_sha256=None,
            operation_outcome=CapacityMeasurementOutcomeV49F.FAIL,
            operation_error_code="RAW_COMMIT_UNAVAILABLE",
            sample_id=None,
        )


def test_exact_physical_output_and_chunk_partition_round_trip_in_bundle() -> None:
    manifest = _manifest()
    first, second = _samples(manifest)
    second = _with_exact_pong_output(second)
    samples = (first, second)
    bundle = CapacityMeasurementArtifactBundleV49F.build(
        manifest=manifest,
        samples=samples,
        correctness=_unfinalized_correctness(manifest, samples),
    )

    replayed = CapacityMeasurementArtifactBundleV49F.from_artifact_bytes(
        bundle.artifact_bytes()
    )
    progress = replayed.samples[1].returned_ingress_progress
    assert progress is not None
    assert progress.automatic_protocol_output_chunks == (
        b"\x8a\x82",
        b"\x01\x02\x03\x04ni",
    )
    assert progress.logical_output_frames == (("PONG", b"ok"),)
    assert replayed.artifact_bytes() == bundle.artifact_bytes()


def test_exact_output_rejects_noncanonical_bytes_partition_and_logical_substitution() -> (
    None
):
    sample = _with_exact_pong_output(_samples(_manifest())[1])
    progress = sample.returned_ingress_progress
    assert progress is not None

    with pytest.raises(CanonicalizationError, match="non-canonical base64"):
        replace(
            progress,
            automatic_protocol_output_base64="AB==",
            automatic_protocol_output_chunk_octet_counts=(1,),
            automatic_output_wire_chunk_counts=(1,),
            ingress_progress_evidence_id=None,
        )
    with pytest.raises(CanonicalizationError, match="chunk partition"):
        replace(
            progress,
            automatic_protocol_output_chunk_octet_counts=(1, 1),
            ingress_progress_evidence_id=None,
        )
    tampered = bytearray(base64.b64decode(progress.automatic_protocol_output_base64))
    tampered[-1] ^= 1
    with pytest.raises(CanonicalizationError, match="differs from logical"):
        replace(
            progress,
            automatic_protocol_output_base64=base64.b64encode(tampered).decode("ascii"),
            ingress_progress_evidence_id=None,
        )


def test_exact_output_base64_encoded_bound_is_checked_before_decode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    decode_called = False

    def unexpected_decode(*args: object, **kwargs: object) -> bytes:
        nonlocal decode_called
        decode_called = True
        raise AssertionError("oversized base64 reached the decoder")

    monkeypatch.setattr(measurement.base64, "b64decode", unexpected_decode)
    with pytest.raises(CanonicalizationError, match="encoded safety bound"):
        measurement._canonical_base64_bytes(  # noqa: SLF001
            "AAAAA",
            field="automatic_protocol_output_base64",
            maximum_decoded_octets=1,
        )
    assert not decode_called


def test_runtime_boundary_roles_and_rejection_decomposition_are_not_substitutable() -> (
    None
):
    sample = _samples(_manifest())[1]

    with pytest.raises(CanonicalizationError, match="wrong boundary role"):
        replace(
            sample,
            before_runtime_boundary=sample.initial_runtime_boundary,
            sample_id=None,
        )
    with pytest.raises(CanonicalizationError, match="exact decomposition"):
        replace(
            sample.before_runtime_boundary,
            admission_rejected_commands=1,
            boundary_evidence_id=None,
        )
    with pytest.raises(CanonicalizationError, match="released admissions require"):
        replace(
            sample.before_runtime_boundary,
            admission_maximum_observed_admitted_commands=0,
            admission_maximum_observed_reserved_work_units=0,
            boundary_evidence_id=None,
        )


def test_before_boundary_capture_must_complete_before_operation_starts() -> None:
    sample = _samples(_manifest())[1]
    overlapping_boundary = replace(
        sample.before_runtime_boundary,
        capture_completed_offset_nanoseconds=(
            sample.operation_start_offset_nanoseconds + 1
        ),
        boundary_evidence_id=None,
    )

    with pytest.raises(CanonicalizationError, match="causal order"):
        replace(
            sample,
            before_runtime_boundary=overlapping_boundary,
            sample_id=None,
        )


def test_returned_grant_must_start_within_loop_span_but_deadline_may_follow_it() -> (
    None
):
    sample = _samples(_manifest())[1]
    progress = sample.returned_ingress_progress
    assert progress is not None
    late_start = sample.loop_time_end_offset_nanoseconds + 1

    with pytest.raises(CanonicalizationError, match="sample loop-clock span"):
        replace(
            sample,
            returned_ingress_progress=replace(
                progress,
                admission_admitted_loop_time_offset_nanoseconds=late_start,
                admission_started_loop_time_offset_nanoseconds=late_start,
                admission_start_deadline_loop_time_offset_nanoseconds=late_start + 100,
                ingress_progress_evidence_id=None,
            ),
            sample_id=None,
        )

    future_deadline = sample.loop_time_end_offset_nanoseconds + 1_000
    accepted = replace(
        sample,
        returned_ingress_progress=replace(
            progress,
            admission_start_deadline_loop_time_offset_nanoseconds=future_deadline,
            ingress_progress_evidence_id=None,
        ),
        sample_id=None,
    )
    assert (
        accepted.returned_ingress_progress.admission_start_deadline_loop_time_offset_nanoseconds
        == future_deadline
    )


def test_returned_grant_never_exceeds_after_boundary_historical_maxima() -> None:
    sample = _samples(_manifest())[1]
    progress = sample.returned_ingress_progress
    assert progress is not None
    adverse = replace(
        sample,
        measurement_outcome=CapacityMeasurementOutcomeV49F.ERROR,
        measurement_error_code="ADVERSE_RUNTIME_EVIDENCE",
        sample_id=None,
    )

    with pytest.raises(CanonicalizationError, match="reservation exceeds"):
        replace(
            adverse,
            returned_ingress_progress=replace(
                progress,
                admission_reservation_work_units=(
                    sample.after_runtime_boundary.admission_maximum_observed_reserved_work_units
                    + 1
                ),
                ingress_progress_evidence_id=None,
            ),
            sample_id=None,
        )

    queue_wait = (
        sample.after_runtime_boundary.admission_maximum_observed_queue_wait_nanoseconds
        + 1
    )
    with pytest.raises(CanonicalizationError, match="queue wait exceeds"):
        replace(
            adverse,
            returned_ingress_progress=replace(
                progress,
                admission_admitted_loop_time_offset_nanoseconds=(
                    progress.admission_started_loop_time_offset_nanoseconds - queue_wait
                ),
                admission_queue_wait_nanoseconds=queue_wait,
                ingress_progress_evidence_id=None,
            ),
            admission_queue_wait_nanoseconds=queue_wait,
            sample_id=None,
        )


def test_pass_binds_last_queue_wait_but_error_preserves_foreign_activity() -> None:
    sample = _samples(_manifest())[1]
    progress = sample.returned_ingress_progress
    assert progress is not None
    queue_wait = 7
    progress = replace(
        progress,
        admission_admitted_loop_time_offset_nanoseconds=(
            progress.admission_started_loop_time_offset_nanoseconds - queue_wait
        ),
        admission_queue_wait_nanoseconds=queue_wait,
        ingress_progress_evidence_id=None,
    )
    contaminated_after = replace(
        sample.after_runtime_boundary,
        admission_maximum_observed_queue_wait_nanoseconds=queue_wait,
        boundary_evidence_id=None,
    )

    with pytest.raises(CanonicalizationError, match="boundary/progress"):
        replace(
            sample,
            returned_ingress_progress=progress,
            after_runtime_boundary=contaminated_after,
            admission_queue_wait_nanoseconds=queue_wait,
            sample_id=None,
        )

    adverse = replace(
        sample,
        returned_ingress_progress=progress,
        after_runtime_boundary=contaminated_after,
        admission_queue_wait_nanoseconds=queue_wait,
        measurement_outcome=CapacityMeasurementOutcomeV49F.ERROR,
        measurement_error_code="NON_TARGET_RUNTIME_ACTIVITY_DETECTED",
        sample_id=None,
    )
    assert adverse.measurement_outcome is CapacityMeasurementOutcomeV49F.ERROR
    assert adverse.returned_ingress_progress is not None


@pytest.mark.parametrize("nested_kind", ("SNAPSHOT", "ADAPTER_SPAN"))
def test_forged_snapshot_tree_fails_as_dict_serialization_and_bundle_construction(
    nested_kind: str,
) -> None:
    bundle = _bundle()
    sample = bundle.samples[0]
    snapshot = sample.before_snapshot
    if nested_kind == "SNAPSHOT":
        forged_snapshot = _forge_exact_record(snapshot, process_rss_bytes=-1)
        message = "process_rss_bytes"
    else:
        forged_span = _forge_exact_record(
            snapshot.adapter_spans[0], observation_method=""
        )
        forged_snapshot = _forge_exact_record(
            snapshot,
            adapter_spans=(forged_span, *snapshot.adapter_spans[1:]),
        )
        message = "observation_method"
    forged_sample = _forge_exact_record(
        sample,
        before_snapshot=forged_snapshot,
    )
    forged_samples = (forged_sample, bundle.samples[1])

    with pytest.raises(CanonicalizationError, match=message):
        forged_snapshot.as_dict()
    with pytest.raises(CanonicalizationError, match=message):
        forged_sample.as_dict()
    with pytest.raises(CanonicalizationError, match=message):
        encode_capacity_measurement_samples_jsonl_v49f(
            forged_samples,
            manifest=bundle.manifest,
        )
    with pytest.raises(CanonicalizationError, match=message):
        CapacityMeasurementArtifactBundleV49F(
            manifest=bundle.manifest,
            samples=forged_samples,
            correctness=bundle.correctness,
            integrity=bundle.integrity,
        )


def test_every_public_raw_record_as_dict_revalidates_forged_exact_instances() -> None:
    bundle = _bundle()
    output_sample = _with_exact_pong_output(bundle.samples[0])
    progress = output_sample.returned_ingress_progress
    assert progress is not None
    records_and_messages = (
        (
            _forge_exact_record(bundle.manifest.environment, logical_cpu_count=0),
            "logical_cpu_count",
        ),
        (
            _forge_exact_record(bundle.manifest.design, random_seed=-1),
            "random_seed",
        ),
        (
            _forge_exact_record(bundle.manifest.workloads[0], workload_id=""),
            "workload_id",
        ),
        (
            _forge_exact_record(bundle.manifest, source_tree_clean=1),
            "source_tree_clean",
        ),
        (
            _forge_exact_record(
                progress.automatic_protocol_output_frames[0], payload_base64="AB=="
            ),
            "non-canonical base64",
        ),
        (
            _forge_exact_record(bundle.correctness, raw_ingress_root_sha256="INVALID"),
            "raw_ingress_root_sha256",
        ),
        (
            _forge_exact_record(bundle.integrity.members[0], byte_count=0),
            "byte_count",
        ),
        (
            _forge_exact_record(bundle.integrity, evidence_bundle_id=_hash("0")),
            "evidence_bundle_id",
        ),
    )

    for record, message in records_and_messages:
        with pytest.raises(CanonicalizationError, match=message):
            record.as_dict()


@pytest.mark.parametrize(
    ("changes", "message"),
    (
        ({"input_chunks": ()}, "input_chunks"),
        ({"timeout_seconds": 0}, "timeout_seconds"),
        ({"workload_family": ""}, "workload_family"),
    ),
)
def test_every_workload_spec_manifest_and_hash_projection_revalidates_forgery(
    changes: dict[str, object],
    message: str,
) -> None:
    workload = _manifest().workloads[0]
    specification = CapacityMeasurementIngressWorkloadSpecV49F.from_manifest_json(
        workload.workload_manifest_json
    )
    forged = _forge_exact_record(specification, **changes)

    for projection in (
        "manifest_payload",
        "workload_manifest_json",
        "workload_sha256",
        "raw_ingress_batch_sha256",
        "expected_output_frames_sha256",
    ):
        with pytest.raises(CanonicalizationError, match=message):
            value = getattr(forged, projection)
            if callable(value):
                value()


def test_every_public_semantic_identity_payload_revalidates_forgery() -> None:
    bundle = _bundle()
    output_sample = _with_exact_pong_output(bundle.samples[0])
    progress = output_sample.returned_ingress_progress
    assert progress is not None
    records_and_messages = (
        (
            _forge_exact_record(bundle.manifest.environment, logical_cpu_count=0),
            "logical_cpu_count",
        ),
        (
            _forge_exact_record(bundle.manifest.design, random_seed=-1),
            "random_seed",
        ),
        (
            _forge_exact_record(bundle.manifest, source_tree_clean=1),
            "source_tree_clean",
        ),
        (
            _forge_exact_record(
                output_sample.before_runtime_boundary,
                admission_reserved_work_units=1,
            ),
            "quiescent",
        ),
        (
            _forge_exact_record(
                progress,
                admission_queue_wait_nanoseconds=(
                    progress.admission_queue_wait_nanoseconds + 1
                ),
            ),
            "queue wait",
        ),
        (
            _forge_exact_record(output_sample, sample_sequence=0),
            "sample_sequence",
        ),
        (
            _forge_exact_record(bundle.correctness, raw_ingress_root_sha256="INVALID"),
            "raw_ingress_root_sha256",
        ),
        (
            _forge_exact_record(bundle.integrity, campaign_manifest_id="INVALID"),
            "campaign_manifest_id",
        ),
    )

    for record, message in records_and_messages:
        with pytest.raises(CanonicalizationError, match=message):
            record.identity_payload()


def test_public_runtime_state_payload_revalidates_forgery() -> None:
    boundary = _samples(_manifest())[0].before_runtime_boundary
    forged = _forge_exact_record(boundary, admission_reserved_work_units=1)

    with pytest.raises(CanonicalizationError, match="quiescent"):
        forged.state_payload()


def test_supported_exact_json_record_types_round_trip_and_duck_types_fail_closed() -> (
    None
):
    bundle = _bundle()
    output_sample = _with_exact_pong_output(bundle.samples[0])
    progress = output_sample.returned_ingress_progress
    assert progress is not None
    snapshot = output_sample.before_snapshot
    records = (
        bundle.manifest.environment,
        bundle.manifest.design,
        bundle.manifest.workloads[0],
        bundle.manifest,
        snapshot.adapter_spans[0],
        snapshot,
        progress.automatic_protocol_output_frames[0],
        output_sample.before_runtime_boundary,
        progress,
        output_sample,
        bundle.correctness,
        bundle.integrity.members[0],
        bundle.integrity,
    )

    for record in records:
        encoded = encode_capacity_measurement_json_v49f(record)
        replayed = decode_capacity_measurement_json_v49f(
            encoded,
            record_type=type(record),
        )
        assert replayed == record
        assert encode_capacity_measurement_json_v49f(replayed) == encoded

    class FakeMeasurementRecord:
        def as_dict(self) -> dict[str, object]:
            return {"bad": True}

        @classmethod
        def from_mapping(cls, payload: object) -> FakeMeasurementRecord:
            del payload
            return cls()

    with pytest.raises(CanonicalizationError, match="unsupported"):
        encode_capacity_measurement_json_v49f(FakeMeasurementRecord())
    with pytest.raises(CapacityMeasurementArtifactErrorV49F, match="unsupported"):
        decode_capacity_measurement_json_v49f(
            b'{"bad":true}\n',
            record_type=FakeMeasurementRecord,
        )


def test_sample_validation_revalidates_supplied_manifest_context() -> None:
    manifest = _manifest()
    samples = _samples(manifest)
    encoded = encode_capacity_measurement_samples_jsonl_v49f(
        samples,
        manifest=manifest,
    )
    forged_manifest = _forge_exact_record(manifest, source_tree_clean=1)

    with pytest.raises(CanonicalizationError, match="source_tree_clean"):
        validate_capacity_measurement_samples_v49f(
            samples,
            manifest=forged_manifest,
        )
    with pytest.raises(CanonicalizationError, match="source_tree_clean"):
        encode_capacity_measurement_samples_jsonl_v49f(
            samples,
            manifest=forged_manifest,
        )
    with pytest.raises(CanonicalizationError, match="source_tree_clean"):
        decode_capacity_measurement_samples_jsonl_v49f(
            encoded,
            manifest=forged_manifest,
        )


def test_forged_nested_progress_is_revalidated_before_sample_serialization() -> None:
    sample = _with_exact_pong_output(_samples(_manifest())[1])
    progress = sample.returned_ingress_progress
    assert progress is not None
    forged = object.__new__(CapacityMeasurementIngressProgressEvidenceV49F)
    for item in fields(CapacityMeasurementIngressProgressEvidenceV49F):
        object.__setattr__(forged, item.name, getattr(progress, item.name))
    object.__setattr__(forged, "automatic_protocol_output_base64", "AB==")
    forged_sample = object.__new__(CapacityMeasurementSampleV49F)
    for item in fields(CapacityMeasurementSampleV49F):
        value = (
            forged
            if item.name == "returned_ingress_progress"
            else getattr(sample, item.name)
        )
        object.__setattr__(forged_sample, item.name, value)

    with pytest.raises(CanonicalizationError, match="non-canonical base64"):
        encode_capacity_measurement_samples_jsonl_v49f((forged_sample,))


def test_bundle_is_exact_four_member_byte_closure_and_replays() -> None:
    bundle = _bundle()
    artifacts = bundle.artifact_bytes()

    assert set(artifacts) == {
        MANIFEST_ARTIFACT_NAME_V49F,
        SAMPLES_ARTIFACT_NAME_V49F,
        CORRECTNESS_ARTIFACT_NAME_V49F,
        INTEGRITY_ARTIFACT_NAME_V49F,
    }
    replayed = CapacityMeasurementArtifactBundleV49F.from_artifact_bytes(artifacts)
    assert replayed == bundle
    assert replayed.artifact_bytes() == artifacts
    assert bundle.integrity.integrity_id == bundle.evidence_bundle_id
    assert bundle.correctness.observations_complete is True
    assert bundle.correctness.passed is False
    assert measurement.A2M_CORRECTNESS_FINALIZER_NOT_IMPLEMENTED_V49F in (
        bundle.correctness.failure_codes
    )
    assert not any(
        getattr(bundle.correctness, name)
        for name in (
            "no_loss",
            "no_duplication",
            "no_reordering",
            "control_output_causal",
            "projection_verified",
            "cleanup_complete",
        )
    )


def test_bundle_publication_revalidates_digest_consistent_foreign_correctness() -> None:
    bundle = _bundle()
    foreign_correctness = replace(
        bundle.correctness,
        sample_stream_sha256=_hash("e"),
        correctness_id=None,
    )
    raw = measurement._raw_member_bytes(  # noqa: SLF001
        bundle.manifest,
        bundle.samples,
        foreign_correctness,
    )
    matching_integrity = measurement._integrity_for_raw(  # noqa: SLF001
        bundle.manifest,
        raw,
        sample_count=len(bundle.samples),
    )
    forged_bundle = _forge_exact_record(
        bundle,
        correctness=foreign_correctness,
        integrity=matching_integrity,
    )

    with pytest.raises(CanonicalizationError, match="exact sample stream"):
        forged_bundle.artifact_bytes()
    with pytest.raises(CanonicalizationError, match="exact sample stream"):
        _ = forged_bundle.evidence_bundle_id


def test_bundle_publication_revalidates_foreign_integrity_and_bundle_id() -> None:
    bundle = _bundle()
    foreign_integrity = replace(
        bundle.integrity,
        campaign_manifest_id=_hash("e"),
        integrity_id=None,
        evidence_bundle_id=None,
    )
    forged_bundle = _forge_exact_record(bundle, integrity=foreign_integrity)

    with pytest.raises(CanonicalizationError, match="integrity metadata"):
        forged_bundle.artifact_bytes()
    with pytest.raises(CanonicalizationError, match="integrity metadata"):
        _ = forged_bundle.evidence_bundle_id
    assert INTEGRITY_ARTIFACT_NAME_V49F not in {
        item.artifact_name for item in bundle.integrity.members
    }


def test_v6_decoder_rejects_legacy_v5_measurement_bytes_without_upgrade() -> None:
    payload = encode_capacity_measurement_json_v49f(_manifest()).replace(
        b"riskyieldmm_physical_transport_a2m_raw_v49f_v6",
        b"riskyieldmm_physical_transport_a2m_raw_v49f_v5",
    )

    with pytest.raises(CanonicalizationError, match="measurement_schema_version"):
        decode_capacity_measurement_json_v49f(
            payload,
            record_type=CapacityMeasurementManifestV49F,
        )


def test_unfinalized_correctness_cannot_be_constructed_as_pass() -> None:
    manifest = _manifest()
    samples = _samples(manifest)
    provisional = _unfinalized_correctness(manifest, samples)
    payload = _pass_correctness_mapping(manifest, samples)
    kwargs = {
        item.name: payload[item.name]
        for item in fields(CapacityMeasurementCorrectnessV49F)
    }
    kwargs["failure_codes"] = tuple(kwargs["failure_codes"])

    with pytest.raises(CanonicalizationError, match="FINALIZER_NOT_IMPLEMENTED"):
        CapacityMeasurementCorrectnessV49F(**kwargs)  # type: ignore[arg-type]
    with pytest.raises(CanonicalizationError, match="FINALIZER_NOT_IMPLEMENTED"):
        CapacityMeasurementCorrectnessV49F.from_mapping(payload)
    with pytest.raises(CanonicalizationError, match="FINALIZER_NOT_IMPLEMENTED"):
        decode_capacity_measurement_json_v49f(
            canonical_json_bytes(payload) + b"\n",
            record_type=CapacityMeasurementCorrectnessV49F,
        )
    with pytest.raises(CanonicalizationError, match="FINALIZER_NOT_IMPLEMENTED"):
        replace(provisional, failure_codes=(), correctness_id=None)


@pytest.mark.parametrize(
    "assertion_field",
    (
        "no_loss",
        "no_duplication",
        "no_reordering",
        "control_output_causal",
        "projection_verified",
        "cleanup_complete",
    ),
)
def test_unfinalized_correctness_cannot_assert_verified_checks(
    assertion_field: str,
) -> None:
    manifest = _manifest()
    samples = _samples(manifest)
    correctness = _unfinalized_correctness(manifest, samples)

    with pytest.raises(CanonicalizationError, match="cannot assert verified checks"):
        replace(
            correctness,
            **{assertion_field: True, "correctness_id": None},
        )


def test_forged_pass_is_rejected_by_bundle_and_serialization_boundaries() -> None:
    bundle = _bundle()
    forged = _forged_pass_correctness(bundle.manifest, bundle.samples)

    with pytest.raises(CanonicalizationError, match="FINALIZER_NOT_IMPLEMENTED"):
        CapacityMeasurementArtifactBundleV49F.build(
            manifest=bundle.manifest,
            samples=bundle.samples,
            correctness=forged,
        )
    with pytest.raises(CanonicalizationError, match="FINALIZER_NOT_IMPLEMENTED"):
        CapacityMeasurementArtifactBundleV49F(
            manifest=bundle.manifest,
            samples=bundle.samples,
            correctness=forged,
            integrity=bundle.integrity,
        )
    with pytest.raises(CanonicalizationError, match="FINALIZER_NOT_IMPLEMENTED"):
        encode_capacity_measurement_json_v49f(forged)
    with pytest.raises(CanonicalizationError, match="FINALIZER_NOT_IMPLEMENTED"):
        _ = forged.passed


def test_fully_rehashed_pass_closure_is_rejected_on_replay() -> None:
    bundle = _bundle()
    artifacts = bundle.artifact_bytes()
    artifacts[CORRECTNESS_ARTIFACT_NAME_V49F] = (
        canonical_json_bytes(_pass_correctness_mapping(bundle.manifest, bundle.samples))
        + b"\n"
    )
    raw = {
        name: artifacts[name]
        for name in (
            MANIFEST_ARTIFACT_NAME_V49F,
            SAMPLES_ARTIFACT_NAME_V49F,
            CORRECTNESS_ARTIFACT_NAME_V49F,
        )
    }
    integrity = measurement._integrity_for_raw(  # noqa: SLF001
        bundle.manifest,
        raw,
        sample_count=len(bundle.samples),
    )
    artifacts[INTEGRITY_ARTIFACT_NAME_V49F] = encode_capacity_measurement_json_v49f(
        integrity
    )

    with pytest.raises(CanonicalizationError, match="FINALIZER_NOT_IMPLEMENTED"):
        CapacityMeasurementArtifactBundleV49F.from_artifact_bytes(artifacts)


def test_manifest_identity_is_plan_session_only_while_bundle_closes_samples() -> None:
    first = _bundle(measured_process_rss_bytes=10_000_000)
    second = _bundle(measured_process_rss_bytes=10_000_001)

    assert first.manifest.campaign_manifest_id == second.manifest.campaign_manifest_id
    assert first.evidence_bundle_id != second.evidence_bundle_id
    assert (
        hashlib.sha256(first.artifact_bytes()[SAMPLES_ARTIFACT_NAME_V49F]).hexdigest()
        != hashlib.sha256(
            second.artifact_bytes()[SAMPLES_ARTIFACT_NAME_V49F]
        ).hexdigest()
    )


def test_cross_session_sample_splicing_is_rejected() -> None:
    manifest = _manifest()
    foreign_manifest = _manifest(transport_session_id=_hash("0"))
    foreign_samples = _samples(foreign_manifest)

    with pytest.raises(CanonicalizationError, match="manifest/session identity"):
        validate_capacity_measurement_samples_v49f(foreign_samples, manifest=manifest)


def test_tamper_noncanonical_duplicate_and_float_payloads_are_rejected() -> None:
    artifacts = _bundle().artifact_bytes()
    tampered = dict(artifacts)
    tampered[SAMPLES_ARTIFACT_NAME_V49F] = tampered[SAMPLES_ARTIFACT_NAME_V49F].replace(
        b'"input_octet_count":2', b'"input_octet_count":3', 1
    )
    with pytest.raises(
        CapacityMeasurementArtifactErrorV49F, match="integrity metadata"
    ):
        CapacityMeasurementArtifactBundleV49F.from_artifact_bytes(tampered)

    manifest_payload = encode_capacity_measurement_json_v49f(_manifest())
    with pytest.raises(CapacityMeasurementArtifactErrorV49F, match="canonically"):
        decode_capacity_measurement_json_v49f(
            manifest_payload.replace(b"{", b"{ ", 1),
            record_type=CapacityMeasurementManifestV49F,
        )
    with pytest.raises(CanonicalizationError, match="duplicate JSON object key"):
        decode_capacity_measurement_json_v49f(
            b'{"x":1,"x":2}\n',
            record_type=CapacityMeasurementManifestV49F,
        )
    with pytest.raises(CanonicalizationError, match="floating-point"):
        decode_capacity_measurement_json_v49f(
            b'{"x":1.5}\n',
            record_type=CapacityMeasurementManifestV49F,
        )


@pytest.mark.parametrize("extra_name", ["summary.json", "threshold_derivation.json"])
def test_summary_threshold_and_any_extra_artifact_are_rejected(extra_name: str) -> None:
    artifacts = _bundle().artifact_bytes()
    artifacts[extra_name] = b"{}\n"

    with pytest.raises(CapacityMeasurementArtifactErrorV49F, match="exactly"):
        CapacityMeasurementArtifactBundleV49F.from_artifact_bytes(artifacts)


def test_contract_does_not_expose_summary_or_threshold_authority() -> None:
    assert not hasattr(measurement, "CapacityMeasurementSummaryV49F")
    assert not hasattr(measurement, "CapacityMeasurementThresholdDerivationV49F")
    assert not hasattr(measurement, "SUMMARY_ARTIFACT_NAME_V49F")
    assert not hasattr(measurement, "THRESHOLD_DERIVATION_ARTIFACT_NAME_V49F")
