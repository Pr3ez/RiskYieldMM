"""Closed exploratory sampler and neutrality oracles for V4.9F-A2-M.

The sampler calls only the public, session-owned runtime operation.  Full
observations occur before and after that operation while admission is
quiescent.  It never polls the owner concurrently, synthesizes a peak, writes
measurement data inside transport locks, or turns measurement into runtime
authority.  A missing stable in-operation hook is represented explicitly as
unavailable evidence.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import os
import time
from collections.abc import Callable, Sequence
from dataclasses import InitVar, dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from .canonical import (
    MAX_IJSON_INTEGER,
    CanonicalizationError,
    canonical_hash,
    canonical_identifier,
    canonical_reason_codes,
    canonical_safe_int,
    sha256_digest,
)
from .physical_transport_capacity_manifest_authority_v49f import (
    CapacityMeasurementCampaignRunnerAuthorizationV49FV7,
    CollectedCapacityMeasurementCampaignV49F,
    CollectedCapacityMeasurementCampaignV49FV7,
)
from .physical_transport_capacity_measurement_v49f import (
    A2M_CORRECTNESS_FINALIZER_NOT_IMPLEMENTED_V49F,
    A2M_LAYER_ADAPTER_FIELDS_V49F,
    A2M_LAYER_VALUE_FIELDS_V49F,
    A2M_RETURNED_PROGRESS_UNAVAILABLE_AFTER_EXCEPTION_V49F,
    CapacityMeasurementAdapterSpanV49F,
    CapacityMeasurementArtifactBundleV49F,
    CapacityMeasurementCorrectnessV49F,
    CapacityMeasurementIngressProgressEvidenceV49F,
    CapacityMeasurementIngressWorkloadSpecV49F,
    CapacityMeasurementLayerSnapshotV49F,
    CapacityMeasurementLogicalOutputFrameV49F,
    CapacityMeasurementManifestV49F,
    CapacityMeasurementOutcomeV49F,
    CapacityMeasurementRuntimeBoundaryEvidenceV49F,
    CapacityMeasurementSampleV49F,
    capacity_measurement_logical_frames_sha256_v49f,
    capacity_measurement_sample_stream_sha256_v49f,
)
from .physical_transport_linux_v4 import LinuxSocketTransportFlowSnapshotV49F
from .physical_transport_runtime_v4 import (
    PhysicalTransportCapacityMeasurementBoundaryV49F,
    PhysicalTransportIngressProgressV49D,
    PhysicalTransportRuntimeV4,
)


class CapacityMeasurementSamplerErrorV49F(CanonicalizationError):
    """Raised when a local exploratory measurement cannot remain truthful."""


def _ordered_output_batch_sha256_v49f(chunks: tuple[bytes, ...]) -> str:
    return sha256_digest(
        {
            "domain": "RiskYieldMMA2MExactOrderedOutputChunksV4_9F",
            "ordered_chunks_base64": [
                base64.b64encode(chunk).decode("ascii") for chunk in chunks
            ],
        }
    )


def _measurement_runtime_boundary_evidence_v49f(
    boundary: PhysicalTransportCapacityMeasurementBoundaryV49F,
    *,
    role: str,
    capture_started_offset_nanoseconds: int,
    capture_completed_offset_nanoseconds: int,
) -> CapacityMeasurementRuntimeBoundaryEvidenceV49F:
    if type(boundary) is not PhysicalTransportCapacityMeasurementBoundaryV49F:
        raise TypeError("boundary must be exact runtime boundary evidence")
    return CapacityMeasurementRuntimeBoundaryEvidenceV49F(
        boundary_role=role,
        capture_started_offset_nanoseconds=capture_started_offset_nanoseconds,
        capture_completed_offset_nanoseconds=capture_completed_offset_nanoseconds,
        transport_session_id=boundary.transport_session_id,
        driver_evidence_nonce_sha256=boundary.driver_evidence_nonce_sha256,
        kernel_socket_identity=boundary.kernel_socket_identity,
        transport_capacity_policy_id=boundary.transport_capacity_policy_id,
        admission_epoch=boundary.admission_epoch,
        admission_closed=boundary.admission_closed,
        admission_terminal_barrier_admission_sequence=(
            boundary.admission_terminal_barrier_admission_sequence
        ),
        admission_terminal_barrier_committed=(
            boundary.admission_terminal_barrier_committed
        ),
        admission_active_admission_sequence=(
            boundary.admission_active_admission_sequence
        ),
        admission_active_command_kind=boundary.admission_active_command_kind,
        admission_waiting_admission_sequences=(
            boundary.admission_waiting_admission_sequences
        ),
        admission_waiting_command_kinds=boundary.admission_waiting_command_kinds,
        admission_oldest_waiting_age_nanoseconds=(
            boundary.admission_oldest_waiting_age_nanoseconds
        ),
        admission_reserved_work_units=boundary.admission_reserved_work_units,
        admission_maximum_observed_admitted_commands=(
            boundary.admission_maximum_observed_admitted_commands
        ),
        admission_maximum_observed_reserved_work_units=(
            boundary.admission_maximum_observed_reserved_work_units
        ),
        admission_last_started_queue_wait_nanoseconds=(
            boundary.admission_last_started_queue_wait_nanoseconds
        ),
        admission_maximum_observed_queue_wait_nanoseconds=(
            boundary.admission_maximum_observed_queue_wait_nanoseconds
        ),
        admission_released_commands=boundary.admission_released_commands,
        admission_rejected_commands=boundary.admission_rejected_commands,
        admission_duplicate_kind_rejections=(
            boundary.admission_duplicate_kind_rejections
        ),
        admission_terminal_barrier_rejections=(
            boundary.admission_terminal_barrier_rejections
        ),
        admission_capacity_rejections=boundary.admission_capacity_rejections,
        admission_closed_rejections=boundary.admission_closed_rejections,
        admission_timed_out_commands=boundary.admission_timed_out_commands,
        admission_cancelled_before_entry_commands=(
            boundary.admission_cancelled_before_entry_commands
        ),
        admission_closed_before_entry_commands=(
            boundary.admission_closed_before_entry_commands
        ),
        actor_event_count=boundary.actor_event_count,
        actor_tail_event_id=boundary.actor_tail_event_id,
        actor_wire_queue_events=boundary.actor_wire_queue_events,
        actor_wire_queue_octets=boundary.actor_wire_queue_octets,
        runtime_state=boundary.runtime_state,
    )


def _measurement_ingress_progress_evidence_v49f(
    progress: PhysicalTransportIngressProgressV49D,
    *,
    loop_time_origin_nanoseconds: int,
) -> CapacityMeasurementIngressProgressEvidenceV49F:
    if type(progress) is not PhysicalTransportIngressProgressV49D:
        raise TypeError("progress must be exact returned ingress progress")
    admission_values = (
        progress.admission_policy_id_v49f,
        progress.admission_epoch_v49f,
        progress.admission_sequence_v49f,
        progress.admission_queue_wait_nanoseconds_v49f,
        progress.admission_command_kind_v49f,
        progress.admission_reservation_work_units_v49f,
        progress.admission_admitted_loop_time_ns_v49f,
        progress.admission_started_loop_time_ns_v49f,
        progress.admission_start_deadline_loop_time_ns_v49f,
    )
    if any(value is None for value in admission_values):
        raise CapacityMeasurementSamplerErrorV49F(
            "A2-M returned progress lacks the full signed admission grant"
        )

    def loop_offset(value: Any, *, field: str) -> int:
        if type(value) is not int:
            raise CapacityMeasurementSamplerErrorV49F(
                f"{field} must be an exact integer"
            )
        offset = value - loop_time_origin_nanoseconds
        if not 0 <= offset <= MAX_IJSON_INTEGER:
            raise CapacityMeasurementSamplerErrorV49F(
                f"{field} is outside the campaign event-loop clock domain"
            )
        return offset

    chunks = progress.automatic_protocol_output_chunks
    return CapacityMeasurementIngressProgressEvidenceV49F(
        raw_ingress_commit_id=progress.raw_ingress_commit_id,
        ingress_sequence=progress.ingress_sequence,
        committed_raw_octets=progress.committed_raw_octets,
        raw_ingress_batch_sha256=progress.raw_ingress_batch_sha256,
        parser_event_ids=progress.parser_event_ids,
        automatic_output_source_parser_event_ids=(
            progress.automatic_output_source_parser_event_ids
        ),
        automatic_dispatch_completion_event_ids=(
            progress.automatic_dispatch_completion_event_ids
        ),
        automatic_protocol_output_base64=base64.b64encode(b"".join(chunks)).decode(
            "ascii"
        ),
        automatic_protocol_output_chunk_octet_counts=tuple(map(len, chunks)),
        automatic_output_wire_chunk_counts=(
            progress.automatic_output_wire_chunk_counts
        ),
        automatic_protocol_output_frames=tuple(
            CapacityMeasurementLogicalOutputFrameV49F(
                opcode=opcode,
                payload_base64=base64.b64encode(payload).decode("ascii"),
            )
            for opcode, payload in progress.automatic_protocol_output_frames
        ),
        actor_event_count_before=progress.actor_event_count_before,
        actor_tail_event_id_before=progress.actor_tail_event_id_before,
        actor_event_count_after=progress.actor_event_count_after,
        actor_tail_event_id_after=progress.actor_tail_event_id_after,
        retained_incomplete_octets=progress.retained_incomplete_octets,
        used_initial_pending_ingress=progress.used_initial_pending_ingress,
        websocket_parser_state=progress.websocket_parser_state,
        admission_policy_id=progress.admission_policy_id_v49f,
        admission_epoch=progress.admission_epoch_v49f,
        admission_sequence=progress.admission_sequence_v49f,
        admission_command_kind=progress.admission_command_kind_v49f,
        admission_reservation_work_units=(
            progress.admission_reservation_work_units_v49f
        ),
        admission_admitted_loop_time_offset_nanoseconds=loop_offset(
            progress.admission_admitted_loop_time_ns_v49f,
            field="admission_admitted_loop_time_ns_v49f",
        ),
        admission_started_loop_time_offset_nanoseconds=loop_offset(
            progress.admission_started_loop_time_ns_v49f,
            field="admission_started_loop_time_ns_v49f",
        ),
        admission_start_deadline_loop_time_offset_nanoseconds=loop_offset(
            progress.admission_start_deadline_loop_time_ns_v49f,
            field="admission_start_deadline_loop_time_ns_v49f",
        ),
        admission_queue_wait_nanoseconds=(
            progress.admission_queue_wait_nanoseconds_v49f
        ),
    )


_TRANSPORT_FLOW_FIELDS_V49F = (
    "driver_state",
    "durable_ingress_buffer_octets",
    "effective_so_rcvbuf_octets",
    "effective_so_sndbuf_octets",
    "has_complete_durable_unit",
    "kernel_socket_identity",
    "memory_bio_incoming_pending_octets",
    "memory_bio_outgoing_pending_octets",
    "pending_raw_chunks",
    "pending_raw_octets",
    "pending_send_eof",
    "pending_tls_ciphertext_octets",
    "protocol_output_chunks",
    "protocol_output_octets",
    "remaining_pending_tls_ciphertext_octets",
    "remaining_staged_tls_ciphertext_octets",
    "remaining_staged_tls_control_ciphertext_octets",
    "siocinq_queued_octets",
    "siocoutq_queued_octets",
    "ssl_plaintext_pending_octets",
    "staged_tls_ciphertext_octets",
    "staged_tls_control_ciphertext_octets",
    "staged_websocket_wire_chunks",
    "staged_websocket_wire_octets",
)
_ADMISSION_FIELDS_V49F = (
    "admission_active_commands",
    "admission_capacity_rejections",
    "admission_queue_wait_nanoseconds",
    "admission_reserved_work_units",
    "admission_waiting_commands",
)
_ACTOR_FIELDS_V49F = (
    "actor_event_count",
    "actor_wire_queue_events",
    "actor_wire_queue_octets",
)
_SQLITE_FIELDS_V49F = (
    "sqlite_database_bytes",
    "sqlite_freelist_count",
    "sqlite_journal_bytes",
    "sqlite_page_count",
    "sqlite_shm_bytes",
    "sqlite_wal_bytes",
)
_PROCESS_FIELDS_V49F = (
    "cgroup_memory_bytes",
    "process_pss_bytes",
    "process_rss_bytes",
)
_EVENT_LOOP_FIELDS_V49F = ("event_loop_lag_nanoseconds",)
_ADAPTER_FIELDS_V49F = (
    ("TRANSPORT_FLOW", _TRANSPORT_FLOW_FIELDS_V49F),
    ("ADMISSION", _ADMISSION_FIELDS_V49F),
    ("ACTOR", _ACTOR_FIELDS_V49F),
    ("SQLITE", _SQLITE_FIELDS_V49F),
    ("PROCESS", _PROCESS_FIELDS_V49F),
    ("EVENT_LOOP", _EVENT_LOOP_FIELDS_V49F),
)
assert {name for _, names in _ADAPTER_FIELDS_V49F for name in names} == set(
    A2M_LAYER_VALUE_FIELDS_V49F
)
assert (
    tuple(
        sorted(
            (adapter, tuple(sorted(names))) for adapter, names in _ADAPTER_FIELDS_V49F
        )
    )
    == A2M_LAYER_ADAPTER_FIELDS_V49F
)


def _optional_count(value: Any, *, field: str, minimum: int = 0) -> int | None:
    if value is None:
        return None
    return canonical_safe_int(value, field=field, minimum=minimum)


@dataclass(frozen=True, slots=True, kw_only=True)
class CapacityMeasurementProcessPointV49F:
    process_rss_bytes: int | None
    process_pss_bytes: int | None
    cgroup_memory_bytes: int | None
    unavailable_reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        for name in _PROCESS_FIELDS_V49F:
            object.__setattr__(
                self, name, _optional_count(getattr(self, name), field=name)
            )
        reasons = canonical_reason_codes(
            self.unavailable_reason_codes, field="unavailable_reason_codes"
        )
        if bool(reasons) != any(
            getattr(self, name) is None for name in _PROCESS_FIELDS_V49F
        ):
            raise CanonicalizationError(
                "process reason codes must be present exactly for missing fields"
            )
        object.__setattr__(self, "unavailable_reason_codes", reasons)


def observe_linux_process_point_v49f() -> CapacityMeasurementProcessPointV49F:
    """Read target-process memory without turning absence into zero."""

    reasons: list[str] = []
    rss: int | None = None
    pss: int | None = None
    cgroup: int | None = None
    try:
        statm = Path("/proc/self/statm").read_text(encoding="ascii").split()
        if len(statm) < 2:
            raise ValueError("statm is truncated")
        rss = int(statm[1]) * os.sysconf("SC_PAGE_SIZE")
        if rss < 0:
            raise ValueError("RSS is negative")
    except (OSError, ValueError, TypeError):
        rss = None
        reasons.append("PROC_STATM_RSS_UNAVAILABLE")
    try:
        for line in (
            Path("/proc/self/smaps_rollup").read_text(encoding="ascii").splitlines()
        ):
            if line.startswith("Pss:"):
                parts = line.split()
                if len(parts) != 3 or parts[2] != "kB":
                    raise ValueError("Pss line is malformed")
                pss = int(parts[1]) * 1024
                break
        if pss is None or pss < 0:
            raise ValueError("Pss is unavailable")
    except (OSError, ValueError):
        pss = None
        reasons.append("PROC_SMAPS_ROLLUP_PSS_UNAVAILABLE")
    try:
        cgroup_path: str | None = None
        for line in Path("/proc/self/cgroup").read_text(encoding="ascii").splitlines():
            parts = line.split(":", 2)
            if len(parts) == 3 and parts[0] == "0" and parts[1] == "":
                cgroup_path = parts[2].lstrip("/")
                break
        if cgroup_path is None:
            raise ValueError("cgroup v2 path is unavailable")
        cgroup = int(
            (Path("/sys/fs/cgroup") / cgroup_path / "memory.current")
            .read_text(encoding="ascii")
            .strip()
        )
        if cgroup < 0:
            raise ValueError("cgroup memory is negative")
    except (OSError, ValueError):
        cgroup = None
        reasons.append("CGROUP_V2_MEMORY_CURRENT_UNAVAILABLE")
    return CapacityMeasurementProcessPointV49F(
        process_rss_bytes=rss,
        process_pss_bytes=pss,
        cgroup_memory_bytes=cgroup,
        unavailable_reason_codes=tuple(reasons),
    )


def capacity_measurement_storage_identity_sha256_v49f(path: Path) -> str:
    """Identify the exact database directory entry used by the runtime store."""

    if not isinstance(path, Path) or not path.is_absolute():
        raise CanonicalizationError("capacity storage path must be an absolute Path")
    try:
        resolved = path.resolve(strict=True)
        observed = resolved.stat()
    except OSError as exc:
        raise CapacityMeasurementSamplerErrorV49F(
            "capacity storage path is unavailable"
        ) from exc
    return sha256_digest(
        {
            "device": observed.st_dev,
            "domain": "RiskYieldMMA2MProjectionStorageIdentityV4_9F",
            "inode": observed.st_ino,
            "resolved_path": str(resolved),
        }
    )


@dataclass(frozen=True, slots=True, kw_only=True)
class CapacityMeasurementTrialV49F:
    workload_id: str
    workload_family: str
    repetition_index: int
    is_warmup: bool
    stage: str
    input_chunks: tuple[bytes, ...]
    expected_output_frames: tuple[tuple[str, bytes], ...]
    timeout_seconds: int = 10

    def __post_init__(self) -> None:
        for name in ("workload_id", "workload_family", "stage"):
            object.__setattr__(
                self, name, canonical_identifier(getattr(self, name), field=name)
            )
        object.__setattr__(
            self,
            "repetition_index",
            canonical_safe_int(
                self.repetition_index, field="repetition_index", minimum=0
            ),
        )
        if type(self.is_warmup) is not bool:
            raise CanonicalizationError("is_warmup must be an exact boolean")
        chunks = self.input_chunks
        if (
            type(chunks) is not tuple
            or not chunks
            or any(type(chunk) is not bytes or not chunk for chunk in chunks)
        ):
            raise CanonicalizationError(
                "input_chunks must be an exact tuple of non-empty byte chunks"
            )
        object.__setattr__(
            self,
            "timeout_seconds",
            canonical_safe_int(
                self.timeout_seconds,
                field="timeout_seconds",
                minimum=1,
                maximum=300,
            ),
        )
        _ = self.workload_spec

    @property
    def workload_spec(self) -> CapacityMeasurementIngressWorkloadSpecV49F:
        return CapacityMeasurementIngressWorkloadSpecV49F(
            workload_family=self.workload_family,
            stage=self.stage,
            input_chunks=self.input_chunks,
            expected_output_frames=self.expected_output_frames,
            timeout_seconds=self.timeout_seconds,
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class CapacityMeasurementSampleRunV49F:
    sample: CapacityMeasurementSampleV49F
    operation_exception_class: str | None
    initial_boundary: PhysicalTransportCapacityMeasurementBoundaryV49F
    boundary_before: PhysicalTransportCapacityMeasurementBoundaryV49F
    boundary_after: PhysicalTransportCapacityMeasurementBoundaryV49F

    def __post_init__(self) -> None:
        if type(self.sample) is not CapacityMeasurementSampleV49F:
            raise TypeError("sample must be exact CapacityMeasurementSampleV49F")
        for name in ("initial_boundary", "boundary_before", "boundary_after"):
            if (
                type(getattr(self, name))
                is not PhysicalTransportCapacityMeasurementBoundaryV49F
            ):
                raise TypeError(f"{name} must be an exact runtime boundary")
        for runtime_name, evidence_name, role in (
            ("initial_boundary", "initial_runtime_boundary", "INITIAL"),
            ("boundary_before", "before_runtime_boundary", "BEFORE_OPERATION"),
            ("boundary_after", "after_runtime_boundary", "AFTER_OPERATION"),
        ):
            evidence = getattr(self.sample, evidence_name)
            mirrored = _measurement_runtime_boundary_evidence_v49f(
                getattr(self, runtime_name),
                role=role,
                capture_started_offset_nanoseconds=(
                    evidence.capture_started_offset_nanoseconds
                ),
                capture_completed_offset_nanoseconds=(
                    evidence.capture_completed_offset_nanoseconds
                ),
            )
            if mirrored != evidence:
                raise CanonicalizationError(
                    f"{runtime_name} differs from persisted runtime evidence"
                )
        if self.operation_exception_class is not None:
            object.__setattr__(
                self,
                "operation_exception_class",
                canonical_identifier(
                    self.operation_exception_class,
                    field="operation_exception_class",
                    maximum=128,
                ),
            )
        if self.operation_exception_class != self.sample.operation_exception_class:
            raise CanonicalizationError(
                "sample run exception class differs from persisted sample evidence"
            )


class _ScheduledLoopLagProbeV49F:
    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop
        self._future: asyncio.Future[int] = loop.create_future()
        expected = loop.time()

        def complete() -> None:
            lag = max(0.0, loop.time() - expected)
            if not self._future.done():
                self._future.set_result(int(lag * 1_000_000_000))

        self._handle = loop.call_soon(complete)

    async def result(self) -> int:
        return await self._future

    def cancel(self) -> None:
        self._handle.cancel()
        if not self._future.done():
            self._future.cancel()


class LocalCapacityMeasurementLayerAdapterV49F:
    """Translate fixed runtime, file, process, and loop observers sequentially."""

    def __init__(
        self,
        *,
        runtime: PhysicalTransportRuntimeV4,
        manifest: CapacityMeasurementManifestV49F,
        monotonic_ns: Any = time.monotonic_ns,
    ) -> None:
        if type(runtime) is not PhysicalTransportRuntimeV4:
            raise TypeError("runtime must be exact PhysicalTransportRuntimeV4")
        if type(manifest) is not CapacityMeasurementManifestV49F:
            raise TypeError("manifest must be exact CapacityMeasurementManifestV49F")
        if not callable(monotonic_ns):
            raise TypeError("monotonic_ns must be callable")
        self._runtime = runtime
        self._manifest = manifest
        database_path = runtime.capacity_measurement_database_path_v49f().resolve(
            strict=True
        )
        storage_identity = capacity_measurement_storage_identity_sha256_v49f(
            database_path
        )
        if storage_identity != manifest.environment.storage_identity_sha256:
            raise CapacityMeasurementSamplerErrorV49F(
                "manifest storage identity differs from the runtime projection"
            )
        database_stat = database_path.stat()
        self._sqlite_database_path = database_path
        self._sqlite_database_device_inode = (
            database_stat.st_dev,
            database_stat.st_ino,
        )
        self._clock = monotonic_ns
        self._origin = int(manifest.monotonic_origin_nanoseconds)

    def _offset(self) -> int:
        value = self._clock()
        if type(value) is not int:
            raise CapacityMeasurementSamplerErrorV49F(
                "observer monotonic clock returned a non-integer"
            )
        offset = value - self._origin
        return canonical_safe_int(
            offset, field="observed_offset_nanoseconds", minimum=0
        )

    @staticmethod
    def unavailable_snapshot(
        *, offset: int, reason_code: str
    ) -> CapacityMeasurementLayerSnapshotV49F:
        reason = canonical_identifier(reason_code, field="reason_code")
        spans = tuple(
            CapacityMeasurementAdapterSpanV49F(
                adapter_name=adapter,
                observation_method="UNAVAILABLE_NO_STABLE_IN_OPERATION_HOOK",
                observation_started_offset_nanoseconds=offset,
                observation_completed_offset_nanoseconds=offset,
                observed_fields=fields,
                unavailable_fields=fields,
                unavailable_reason_codes=(reason,),
            )
            for adapter, fields in sorted(_ADAPTER_FIELDS_V49F)
        )
        return CapacityMeasurementLayerSnapshotV49F(
            observation_method="DECLARED_UNAVAILABLE_POINT",
            observed_offset_nanoseconds=offset,
            adapter_spans=spans,
            unavailable_fields=A2M_LAYER_VALUE_FIELDS_V49F,
            unavailable_reason_codes=(reason,),
            **dict.fromkeys(A2M_LAYER_VALUE_FIELDS_V49F),
        )

    async def observe(
        self, *, event_loop_lag_nanoseconds: int | None
    ) -> CapacityMeasurementLayerSnapshotV49F:
        values: dict[str, Any] = dict.fromkeys(A2M_LAYER_VALUE_FIELDS_V49F)
        spans: list[CapacityMeasurementAdapterSpanV49F] = []
        all_reasons: set[str] = set()

        async def observe_transport() -> None:
            started = self._offset()
            reasons: set[str] = set()
            try:
                flow = await self._runtime.capacity_measurement_transport_flow_v49f()
                if type(flow) is not LinuxSocketTransportFlowSnapshotV49F:
                    raise TypeError("runtime returned an unsupported flow snapshot")
                driver = flow.driver_flow
                values.update(
                    {
                        "kernel_socket_identity": flow.kernel_socket_identity,
                        "effective_so_rcvbuf_octets": flow.effective_so_rcvbuf_octets,
                        "effective_so_sndbuf_octets": flow.effective_so_sndbuf_octets,
                        "siocinq_queued_octets": flow.siocinq_queued_octets,
                        "siocoutq_queued_octets": flow.siocoutq_queued_octets,
                        "driver_state": driver.driver_state.value,
                        "memory_bio_incoming_pending_octets": driver.memory_bio_incoming_pending_octets,
                        "memory_bio_outgoing_pending_octets": driver.memory_bio_outgoing_pending_octets,
                        "ssl_plaintext_pending_octets": driver.ssl_plaintext_pending_octets,
                        "pending_raw_chunks": driver.pending_raw_chunks,
                        "pending_raw_octets": driver.pending_raw_octets,
                        "durable_ingress_buffer_octets": driver.durable_ingress_buffer_octets,
                        "has_complete_durable_unit": driver.has_complete_durable_unit,
                        "protocol_output_chunks": driver.protocol_output_chunks,
                        "protocol_output_octets": driver.protocol_output_octets,
                        "pending_send_eof": driver.pending_send_eof,
                        "staged_websocket_wire_chunks": driver.staged_websocket_wire_chunks,
                        "staged_websocket_wire_octets": driver.staged_websocket_wire_octets,
                        "pending_tls_ciphertext_octets": driver.pending_tls_ciphertext_octets,
                        "remaining_pending_tls_ciphertext_octets": driver.remaining_pending_tls_ciphertext_octets,
                        "staged_tls_ciphertext_octets": driver.staged_tls_ciphertext_octets,
                        "remaining_staged_tls_ciphertext_octets": driver.remaining_staged_tls_ciphertext_octets,
                        "staged_tls_control_ciphertext_octets": driver.staged_tls_control_ciphertext_octets,
                        "remaining_staged_tls_control_ciphertext_octets": driver.remaining_staged_tls_control_ciphertext_octets,
                    }
                )
                reasons.update(flow.unavailable_reason_codes)
            except Exception:
                for name in _TRANSPORT_FLOW_FIELDS_V49F:
                    values[name] = None
                reasons.add("TRANSPORT_FLOW_OBSERVER_ERROR")
            completed = self._offset()
            unavailable = tuple(
                name for name in _TRANSPORT_FLOW_FIELDS_V49F if values[name] is None
            )
            if unavailable and not reasons:
                reasons.add("TRANSPORT_FLOW_FIELD_UNAVAILABLE")
            all_reasons.update(reasons)
            spans.append(
                CapacityMeasurementAdapterSpanV49F(
                    adapter_name="TRANSPORT_FLOW",
                    observation_method="OWNER_IO_LOCK_DRIVER_LOCK_SEQUENTIAL_IOCTL",
                    observation_started_offset_nanoseconds=started,
                    observation_completed_offset_nanoseconds=completed,
                    observed_fields=_TRANSPORT_FLOW_FIELDS_V49F,
                    unavailable_fields=unavailable,
                    unavailable_reason_codes=tuple(reasons) if unavailable else (),
                )
            )

        await observe_transport()

        started = self._offset()
        reasons: set[str] = set()
        try:
            admission = self._runtime.transport_admission_snapshot_v49f()
            if admission is None:
                raise ValueError("signed admission is unavailable")
            values.update(
                {
                    "admission_active_commands": (
                        1 if admission.active_admission_sequence is not None else 0
                    ),
                    "admission_waiting_commands": len(
                        admission.waiting_admission_sequences
                    ),
                    "admission_reserved_work_units": admission.reserved_work_units,
                    "admission_capacity_rejections": admission.capacity_rejections,
                    "admission_queue_wait_nanoseconds": (
                        admission.last_started_queue_wait_nanoseconds
                    ),
                }
            )
        except Exception:
            reasons.add("ADMISSION_OBSERVER_ERROR")
        completed = self._offset()
        unavailable = tuple(
            name for name in _ADMISSION_FIELDS_V49F if values[name] is None
        )
        all_reasons.update(reasons)
        spans.append(
            CapacityMeasurementAdapterSpanV49F(
                adapter_name="ADMISSION",
                observation_method="QUIESCENT_A1_GATE_SNAPSHOT",
                observation_started_offset_nanoseconds=started,
                observation_completed_offset_nanoseconds=completed,
                observed_fields=_ADMISSION_FIELDS_V49F,
                unavailable_fields=unavailable,
                unavailable_reason_codes=tuple(reasons) if unavailable else (),
            )
        )

        started = self._offset()
        reasons = set()
        try:
            boundary = await self._runtime.capture_capacity_measurement_boundary_v49f()
            values["actor_event_count"] = boundary.actor_event_count
            values["actor_wire_queue_events"] = boundary.actor_wire_queue_events
            values["actor_wire_queue_octets"] = boundary.actor_wire_queue_octets
        except Exception:
            reasons.add("ACTOR_OBSERVER_ERROR")
        completed = self._offset()
        unavailable = tuple(name for name in _ACTOR_FIELDS_V49F if values[name] is None)
        all_reasons.update(reasons)
        spans.append(
            CapacityMeasurementAdapterSpanV49F(
                adapter_name="ACTOR",
                observation_method="QUIESCENT_CONSTANT_COST_ACTOR_COUNTERS",
                observation_started_offset_nanoseconds=started,
                observation_completed_offset_nanoseconds=completed,
                observed_fields=_ACTOR_FIELDS_V49F,
                unavailable_fields=unavailable,
                unavailable_reason_codes=tuple(reasons) if unavailable else (),
            )
        )

        started = self._offset()
        reasons = set()
        database = self._sqlite_database_path
        try:
            database_stat = database.stat()
            if (database_stat.st_dev, database_stat.st_ino) != (
                self._sqlite_database_device_inode
            ):
                raise OSError("projection database identity changed")
            values["sqlite_database_bytes"] = database_stat.st_size
        except (OSError, ValueError):
            reasons.add("SQLITE_DATABASE_STAT_UNAVAILABLE")
        for suffix, field, reason in (
            ("-journal", "sqlite_journal_bytes", "SQLITE_JOURNAL_STAT_UNAVAILABLE"),
            ("-wal", "sqlite_wal_bytes", "SQLITE_WAL_STAT_UNAVAILABLE"),
            ("-shm", "sqlite_shm_bytes", "SQLITE_SHM_STAT_UNAVAILABLE"),
        ):
            try:
                values[field] = Path(f"{database}{suffix}").stat().st_size
            except FileNotFoundError:
                values[field] = 0
            except (OSError, ValueError):
                reasons.add(reason)
        reasons.add("SQLITE_CONNECTION_PRAGMAS_NOT_SAMPLED")
        completed = self._offset()
        unavailable = tuple(
            name for name in _SQLITE_FIELDS_V49F if values[name] is None
        )
        all_reasons.update(reasons)
        spans.append(
            CapacityMeasurementAdapterSpanV49F(
                adapter_name="SQLITE",
                observation_method="FILESYSTEM_SIDECARS_NO_CONNECTION_REENTRY",
                observation_started_offset_nanoseconds=started,
                observation_completed_offset_nanoseconds=completed,
                observed_fields=_SQLITE_FIELDS_V49F,
                unavailable_fields=unavailable,
                unavailable_reason_codes=tuple(reasons) if unavailable else (),
            )
        )

        started = self._offset()
        reasons = set()
        try:
            process = observe_linux_process_point_v49f()
            for name in _PROCESS_FIELDS_V49F:
                values[name] = getattr(process, name)
            reasons.update(process.unavailable_reason_codes)
        except Exception:
            for name in _PROCESS_FIELDS_V49F:
                values[name] = None
            reasons.add("PROCESS_OBSERVER_ERROR")
        completed = self._offset()
        unavailable = tuple(
            name for name in _PROCESS_FIELDS_V49F if values[name] is None
        )
        all_reasons.update(reasons)
        spans.append(
            CapacityMeasurementAdapterSpanV49F(
                adapter_name="PROCESS",
                observation_method="LINUX_PROCFS_SMAPS_ROLLUP_CGROUP_V2",
                observation_started_offset_nanoseconds=started,
                observation_completed_offset_nanoseconds=completed,
                observed_fields=_PROCESS_FIELDS_V49F,
                unavailable_fields=unavailable,
                unavailable_reason_codes=tuple(reasons) if unavailable else (),
            )
        )

        started = self._offset()
        reasons = set()
        if event_loop_lag_nanoseconds is None:
            reasons.add("EVENT_LOOP_LAG_NOT_SCHEDULED")
        else:
            values["event_loop_lag_nanoseconds"] = canonical_safe_int(
                event_loop_lag_nanoseconds,
                field="event_loop_lag_nanoseconds",
                minimum=0,
            )
        completed = self._offset()
        unavailable = tuple(
            name for name in _EVENT_LOOP_FIELDS_V49F if values[name] is None
        )
        all_reasons.update(reasons)
        spans.append(
            CapacityMeasurementAdapterSpanV49F(
                adapter_name="EVENT_LOOP",
                observation_method="ASYNCIO_EXPECTED_VERSUS_ACTUAL_CALLBACK",
                observation_started_offset_nanoseconds=started,
                observation_completed_offset_nanoseconds=completed,
                observed_fields=_EVENT_LOOP_FIELDS_V49F,
                unavailable_fields=unavailable,
                unavailable_reason_codes=tuple(reasons) if unavailable else (),
            )
        )

        ordered_spans = tuple(
            sorted(
                spans,
                key=lambda span: (
                    span.observation_started_offset_nanoseconds,
                    span.observation_completed_offset_nanoseconds,
                    span.adapter_name,
                ),
            )
        )
        unavailable_fields = tuple(
            sorted(name for name, value in values.items() if value is None)
        )
        return CapacityMeasurementLayerSnapshotV49F(
            observation_method="SEQUENTIAL_BOUNDARY_ADAPTERS_NOT_SIMULTANEOUS",
            observed_offset_nanoseconds=max(
                span.observation_completed_offset_nanoseconds for span in ordered_spans
            ),
            adapter_spans=ordered_spans,
            unavailable_fields=unavailable_fields,
            unavailable_reason_codes=tuple(all_reasons) if unavailable_fields else (),
            **values,
        )


class CapacityMeasurementSessionRunnerV49F:
    """Run ingress trials through the exact retained public runtime seam."""

    def __init__(
        self,
        *,
        campaign: CollectedCapacityMeasurementCampaignV49F,
    ) -> None:
        if type(campaign) is not CollectedCapacityMeasurementCampaignV49F:
            raise TypeError(
                "campaign must be an exact collected V6 measurement campaign"
            )
        campaign.assert_local_current()
        self._initialize(
            runtime=campaign.runtime,
            manifest=campaign.manifest,
            authority_context=campaign,
            monotonic_ns=time.monotonic_ns,
            boottime_ns=lambda: time.clock_gettime_ns(time.CLOCK_BOOTTIME),
        )

    @classmethod
    def _for_test(
        cls,
        *,
        runtime: PhysicalTransportRuntimeV4,
        manifest: CapacityMeasurementManifestV49F,
        monotonic_ns: Any = time.monotonic_ns,
        boottime_ns: Any | None = None,
    ) -> CapacityMeasurementSessionRunnerV49F:
        """Construct the explicit non-authoritative deterministic test profile."""

        if runtime.is_live_profile:
            raise TypeError("the test runner cannot accept a live runtime profile")
        result = object.__new__(cls)
        result._initialize(
            runtime=runtime,
            manifest=manifest,
            authority_context=None,
            monotonic_ns=monotonic_ns,
            boottime_ns=(
                boottime_ns
                if boottime_ns is not None
                else lambda: time.clock_gettime_ns(time.CLOCK_BOOTTIME)
            ),
        )
        return result

    def _initialize(
        self,
        *,
        runtime: PhysicalTransportRuntimeV4,
        manifest: CapacityMeasurementManifestV49F,
        authority_context: CollectedCapacityMeasurementCampaignV49F | None,
        monotonic_ns: Any,
        boottime_ns: Any,
    ) -> None:
        if type(runtime) is not PhysicalTransportRuntimeV4:
            raise TypeError("runtime must be exact PhysicalTransportRuntimeV4")
        if type(manifest) is not CapacityMeasurementManifestV49F:
            raise TypeError("manifest must be exact CapacityMeasurementManifestV49F")
        if authority_context is not None and (
            type(authority_context) is not CollectedCapacityMeasurementCampaignV49F
            or authority_context.runtime is not runtime
            or authority_context.manifest is not manifest
        ):
            raise TypeError("runner authority context differs from campaign inputs")
        if not callable(monotonic_ns) or not callable(boottime_ns):
            raise TypeError("measurement clocks must be callable")
        self._runtime = runtime
        self._manifest = manifest
        self._authority_context = authority_context
        self._monotonic_ns = monotonic_ns
        self._boottime_ns = boottime_ns
        self._monotonic_origin = int(manifest.monotonic_origin_nanoseconds)
        self._boottime_origin = int(manifest.boottime_origin_nanoseconds)
        self._loop_origin = int(manifest.loop_time_origin_nanoseconds)
        self._adapter = LocalCapacityMeasurementLayerAdapterV49F(
            runtime=runtime,
            manifest=manifest,
            monotonic_ns=monotonic_ns,
        )

    async def _assert_manifest_authority_current(self) -> None:
        authority = self._authority_context
        if authority is not None:
            await authority.assert_current()

    def _relative(self, value: Any, origin: int, *, field: str) -> int:
        if type(value) is not int:
            raise CapacityMeasurementSamplerErrorV49F(
                f"{field} clock returned a non-integer"
            )
        offset = value - origin
        if not 0 <= offset <= MAX_IJSON_INTEGER:
            raise CapacityMeasurementSamplerErrorV49F(
                f"{field} offset is outside the I-JSON domain"
            )
        return offset

    def _observer_offset(self) -> int:
        return self._relative(
            self._monotonic_ns(), self._monotonic_origin, field="observer"
        )

    def _boottime_offset(self) -> int:
        return self._relative(
            self._boottime_ns(), self._boottime_origin, field="boottime"
        )

    def _loop_offset(self, loop: asyncio.AbstractEventLoop) -> int:
        return self._relative(
            int(loop.time() * 1_000_000_000), self._loop_origin, field="loop_time"
        )

    def _assert_manifest_boundary(
        self, boundary: PhysicalTransportCapacityMeasurementBoundaryV49F
    ) -> None:
        expected = (
            self._manifest.transport_session_id,
            self._manifest.driver_evidence_nonce_sha256,
            self._manifest.kernel_socket_identity,
            self._manifest.transport_capacity_policy_id,
        )
        actual = (
            boundary.transport_session_id,
            boundary.driver_evidence_nonce_sha256,
            boundary.kernel_socket_identity,
            boundary.transport_capacity_policy_id,
        )
        if actual != expected:
            raise CapacityMeasurementSamplerErrorV49F(
                "runtime boundary differs from the exact campaign manifest"
            )

    async def _one_tick_lag(self) -> int:
        return await _ScheduledLoopLagProbeV49F(asyncio.get_running_loop()).result()

    async def run_ingress(
        self,
        trial: CapacityMeasurementTrialV49F,
        *,
        sample_sequence: int,
        parent_sample_id: str | None,
    ) -> CapacityMeasurementSampleRunV49F:
        if type(trial) is not CapacityMeasurementTrialV49F:
            raise TypeError("trial must be exact CapacityMeasurementTrialV49F")
        sequence = canonical_safe_int(
            sample_sequence, field="sample_sequence", minimum=1
        )
        workload_map = {item.workload_id: item for item in self._manifest.workloads}
        if trial.workload_id not in workload_map:
            raise CapacityMeasurementSamplerErrorV49F(
                "trial workload is absent from the campaign manifest"
            )
        workload = workload_map[trial.workload_id]
        if (
            trial.workload_spec.workload_manifest_json
            != workload.workload_manifest_json
        ):
            raise CapacityMeasurementSamplerErrorV49F(
                "trial differs from the exact executable workload manifest"
            )
        await self._assert_manifest_authority_current()
        loop = asyncio.get_running_loop()
        observer_start = self._observer_offset()
        initial_boundary_capture_start = self._observer_offset()
        initial_boundary = (
            await self._runtime.capture_capacity_measurement_boundary_v49f()
        )
        initial_boundary_capture_end = self._observer_offset()
        self._assert_manifest_boundary(initial_boundary)
        boottime_start = self._boottime_offset()
        loop_start = self._loop_offset(loop)

        baseline_lag = await self._one_tick_lag()
        before = await self._adapter.observe(event_loop_lag_nanoseconds=baseline_lag)
        boundary_before_capture_start = self._observer_offset()
        boundary_before = (
            await self._runtime.capture_capacity_measurement_boundary_v49f()
        )
        boundary_before_capture_end = self._observer_offset()
        self._assert_manifest_boundary(boundary_before)
        await self._assert_manifest_authority_current()

        operation_start = self._observer_offset()
        operation_probe = _ScheduledLoopLagProbeV49F(loop)
        progress: PhysicalTransportIngressProgressV49D | None = None
        operation_exception_class: str | None = None
        operation_outcome = CapacityMeasurementOutcomeV49F.PASS
        operation_error_code: str | None = None
        try:
            progress = await self._runtime.process_next_ingress_v49d(
                timeout_seconds=trial.timeout_seconds
            )
        except Exception as exc:
            operation_exception_class = type(exc).__name__
            operation_outcome = CapacityMeasurementOutcomeV49F.ERROR
            operation_error_code = "INGRESS_OPERATION_EXCEPTION"
        except BaseException:
            operation_probe.cancel()
            raise
        operation_end = self._observer_offset()
        operation_lag = await operation_probe.result()

        in_operation = self._adapter.unavailable_snapshot(
            offset=operation_end,
            reason_code="NO_STABLE_IN_OPERATION_HOOK",
        )
        after = await self._adapter.observe(event_loop_lag_nanoseconds=operation_lag)
        boundary_after_capture_start = self._observer_offset()
        boundary_after = (
            await self._runtime.capture_capacity_measurement_boundary_v49f()
        )
        boundary_after_capture_end = self._observer_offset()
        self._assert_manifest_boundary(boundary_after)
        authority_currentness_error = False
        try:
            await self._assert_manifest_authority_current()
        except Exception:
            authority_currentness_error = True
        observer_end = self._observer_offset()
        boottime_end = self._boottime_offset()
        loop_end = self._loop_offset(loop)

        observed_output_chunks: tuple[bytes, ...] | None = None
        observed_output_frames: tuple[tuple[str, bytes], ...] | None = None
        parser_event_ids: tuple[str, ...] | None = None
        automatic_output_source_parser_event_ids: tuple[str, ...] | None = None
        automatic_dispatch_completion_event_ids: tuple[str, ...] | None = None
        automatic_output_wire_chunk_counts: tuple[int, ...] | None = None
        raw_commit_id: str | None = None
        raw_sequence: int | None = None
        attribution = "UNAVAILABLE"
        admission_policy_id: str | None = None
        admission_epoch: int | None = None
        admission_sequence: int | None = None
        admission_wait: int | None = None
        declared_input_sha256 = hashlib.sha256(b"".join(trial.input_chunks)).hexdigest()
        declared_raw_batch_sha256 = trial.workload_spec.raw_ingress_batch_sha256
        persisted_progress: CapacityMeasurementIngressProgressEvidenceV49F | None = None
        if progress is not None:
            persisted_progress = _measurement_ingress_progress_evidence_v49f(
                progress,
                loop_time_origin_nanoseconds=self._loop_origin,
            )
            raw_commit_id = progress.raw_ingress_commit_id
            raw_sequence = progress.ingress_sequence
            observed_output_chunks = progress.automatic_protocol_output_chunks
            observed_output_frames = progress.automatic_protocol_output_frames
            parser_event_ids = progress.parser_event_ids
            automatic_output_source_parser_event_ids = (
                progress.automatic_output_source_parser_event_ids
            )
            automatic_dispatch_completion_event_ids = (
                progress.automatic_dispatch_completion_event_ids
            )
            automatic_output_wire_chunk_counts = (
                progress.automatic_output_wire_chunk_counts
            )
            if progress.raw_ingress_batch_sha256 != declared_raw_batch_sha256:
                operation_outcome = CapacityMeasurementOutcomeV49F.FAIL
                operation_error_code = "COMMITTED_RAW_BATCH_SHA256_MISMATCH"
            elif progress.committed_raw_octets != sum(map(len, trial.input_chunks)):
                operation_outcome = CapacityMeasurementOutcomeV49F.FAIL
                operation_error_code = "COMMITTED_INPUT_OCTETS_MISMATCH"
            if operation_outcome is CapacityMeasurementOutcomeV49F.PASS:
                if not (
                    len(observed_output_frames)
                    == len(automatic_output_source_parser_event_ids)
                    == len(automatic_dispatch_completion_event_ids)
                    == len(automatic_output_wire_chunk_counts)
                ) or (bool(observed_output_frames) != bool(observed_output_chunks)):
                    operation_outcome = CapacityMeasurementOutcomeV49F.ERROR
                    operation_error_code = "AUTOMATIC_OUTPUT_COMMITMENT_INCOMPLETE"
                elif observed_output_frames != trial.expected_output_frames:
                    operation_outcome = CapacityMeasurementOutcomeV49F.FAIL
                    operation_error_code = "EXPECTED_LOGICAL_OUTPUT_MISMATCH"
            if progress.admission_policy_id_v49f is not None:
                attribution = "EXACT_RETURNED_GRANT"
                admission_policy_id = progress.admission_policy_id_v49f
                admission_epoch = progress.admission_epoch_v49f
                admission_sequence = progress.admission_sequence_v49f
                admission_wait = progress.admission_queue_wait_nanoseconds_v49f
                if (
                    admission_policy_id != boundary_before.transport_capacity_policy_id
                    or admission_epoch != boundary_before.admission_epoch
                ):
                    operation_outcome = CapacityMeasurementOutcomeV49F.ERROR
                    operation_error_code = "ADMISSION_GRANT_BOUNDARY_MISMATCH"

        pre_operation_boundary_stable = initial_boundary == boundary_before
        snapshots_aligned_to_boundaries = (
            before.kernel_socket_identity == boundary_before.kernel_socket_identity
            and before.actor_event_count == boundary_before.actor_event_count
            and before.actor_wire_queue_events
            == boundary_before.actor_wire_queue_events
            and before.actor_wire_queue_octets
            == boundary_before.actor_wire_queue_octets
            and before.admission_capacity_rejections
            == boundary_before.admission_capacity_rejections
            and after.kernel_socket_identity == boundary_after.kernel_socket_identity
            and after.actor_event_count == boundary_after.actor_event_count
            and after.actor_wire_queue_events == boundary_after.actor_wire_queue_events
            and after.actor_wire_queue_octets == boundary_after.actor_wire_queue_octets
            and after.admission_capacity_rejections
            == boundary_after.admission_capacity_rejections
        )
        operation_boundary_verified = False
        if progress is not None:
            operation_boundary_verified = (
                progress.actor_event_count_before == boundary_before.actor_event_count
                and progress.actor_tail_event_id_before
                == boundary_before.actor_tail_event_id
                and progress.actor_event_count_after == boundary_after.actor_event_count
                and progress.actor_tail_event_id_after
                == boundary_after.actor_tail_event_id
                and boundary_after.admission_released_commands
                == boundary_before.admission_released_commands + 1
                and boundary_after.admission_rejected_commands
                == boundary_before.admission_rejected_commands
                and boundary_after.admission_timed_out_commands
                == boundary_before.admission_timed_out_commands
                and boundary_after.admission_cancelled_before_entry_commands
                == boundary_before.admission_cancelled_before_entry_commands
                and boundary_after.admission_closed_before_entry_commands
                == boundary_before.admission_closed_before_entry_commands
            )
        snapshots = (before, in_operation, after)
        measurement_complete = all(not item.unavailable_fields for item in snapshots)
        measurement_outcome = (
            CapacityMeasurementOutcomeV49F.PASS
            if not authority_currentness_error
            and measurement_complete
            and attribution == "EXACT_RETURNED_GRANT"
            and pre_operation_boundary_stable
            and snapshots_aligned_to_boundaries
            and operation_boundary_verified
            else CapacityMeasurementOutcomeV49F.ERROR
        )
        if authority_currentness_error:
            measurement_error_code = "MANIFEST_AUTHORITY_CHANGED_AFTER_OPERATION"
        elif measurement_outcome is CapacityMeasurementOutcomeV49F.PASS:
            measurement_error_code = None
        elif progress is None:
            measurement_error_code = "OPERATION_BOUNDARY_UNVERIFIED"
        elif not pre_operation_boundary_stable or not operation_boundary_verified:
            measurement_error_code = "NON_TARGET_RUNTIME_ACTIVITY_DETECTED"
        elif not snapshots_aligned_to_boundaries:
            measurement_error_code = "BOUNDARY_SNAPSHOT_MISALIGNED"
        else:
            measurement_error_code = "MEASUREMENT_INCOMPLETE"
        initial_boundary_evidence = _measurement_runtime_boundary_evidence_v49f(
            initial_boundary,
            role="INITIAL",
            capture_started_offset_nanoseconds=initial_boundary_capture_start,
            capture_completed_offset_nanoseconds=initial_boundary_capture_end,
        )
        before_boundary_evidence = _measurement_runtime_boundary_evidence_v49f(
            boundary_before,
            role="BEFORE_OPERATION",
            capture_started_offset_nanoseconds=boundary_before_capture_start,
            capture_completed_offset_nanoseconds=boundary_before_capture_end,
        )
        after_boundary_evidence = _measurement_runtime_boundary_evidence_v49f(
            boundary_after,
            role="AFTER_OPERATION",
            capture_started_offset_nanoseconds=boundary_after_capture_start,
            capture_completed_offset_nanoseconds=boundary_after_capture_end,
        )
        observed_bytes = (
            None if observed_output_chunks is None else b"".join(observed_output_chunks)
        )
        sample = CapacityMeasurementSampleV49F(
            campaign_manifest_id=self._manifest.campaign_manifest_id,
            manifest_authority_id=(
                self._manifest.manifest_authority.manifest_authority_id
            ),
            transport_session_id=self._manifest.transport_session_id,
            driver_evidence_nonce_sha256=self._manifest.driver_evidence_nonce_sha256,
            kernel_socket_identity=self._manifest.kernel_socket_identity,
            source_identity_sha256=self._manifest.source_identity_sha256,
            runtime_identity_sha256=self._manifest.runtime_identity_sha256,
            workload_corpus_sha256=self._manifest.workload_corpus_sha256,
            measurement_design_id=self._manifest.design.measurement_design_id,
            sample_sequence=sequence,
            parent_sample_id=parent_sample_id,
            workload_id=trial.workload_id,
            workload_sha256=workload.workload_sha256,
            trial_index=sequence - 1,
            repetition_index=trial.repetition_index,
            is_warmup=trial.is_warmup,
            stage=trial.stage,
            observer_start_offset_nanoseconds=observer_start,
            observer_end_offset_nanoseconds=observer_end,
            boottime_start_offset_nanoseconds=boottime_start,
            boottime_end_offset_nanoseconds=boottime_end,
            loop_time_start_offset_nanoseconds=loop_start,
            loop_time_end_offset_nanoseconds=loop_end,
            operation_start_offset_nanoseconds=operation_start,
            operation_end_offset_nanoseconds=operation_end,
            initial_runtime_boundary=initial_boundary_evidence,
            before_runtime_boundary=before_boundary_evidence,
            returned_ingress_progress=persisted_progress,
            returned_ingress_progress_unavailable_reason=(
                A2M_RETURNED_PROGRESS_UNAVAILABLE_AFTER_EXCEPTION_V49F
                if progress is None
                else None
            ),
            after_runtime_boundary=after_boundary_evidence,
            raw_ingress_commit_id=raw_commit_id,
            raw_ingress_sequence=raw_sequence,
            raw_ingress_batch_sha256=(
                None if progress is None else progress.raw_ingress_batch_sha256
            ),
            parser_event_ids=parser_event_ids,
            automatic_output_source_parser_event_ids=(
                automatic_output_source_parser_event_ids
            ),
            automatic_dispatch_completion_event_ids=(
                automatic_dispatch_completion_event_ids
            ),
            automatic_output_wire_chunk_counts=automatic_output_wire_chunk_counts,
            admission_attribution=attribution,
            admission_policy_id=admission_policy_id,
            admission_epoch=admission_epoch,
            admission_sequence=admission_sequence,
            admission_queue_wait_nanoseconds=admission_wait,
            input_chunk_count=len(trial.input_chunks),
            input_octet_count=sum(map(len, trial.input_chunks)),
            input_sha256=declared_input_sha256,
            output_chunk_count=(
                None if observed_output_chunks is None else len(observed_output_chunks)
            ),
            output_octet_count=None if observed_bytes is None else len(observed_bytes),
            observed_output_sha256=(
                None
                if observed_bytes is None
                else hashlib.sha256(observed_bytes).hexdigest()
            ),
            observed_output_batch_sha256=(
                None
                if observed_output_chunks is None
                else _ordered_output_batch_sha256_v49f(observed_output_chunks)
            ),
            output_frame_count=(
                None if observed_output_frames is None else len(observed_output_frames)
            ),
            expected_output_frame_count=len(trial.expected_output_frames),
            observed_output_frames_sha256=(
                None
                if observed_output_frames is None
                else capacity_measurement_logical_frames_sha256_v49f(
                    observed_output_frames
                )
            ),
            expected_output_frames_sha256=(
                trial.workload_spec.expected_output_frames_sha256
            ),
            before_snapshot=before,
            in_operation_snapshot=in_operation,
            after_snapshot=after,
            operation_outcome=operation_outcome,
            operation_error_code=operation_error_code,
            operation_exception_class=operation_exception_class,
            measurement_outcome=measurement_outcome,
            measurement_error_code=measurement_error_code,
        )
        return CapacityMeasurementSampleRunV49F(
            sample=sample,
            operation_exception_class=operation_exception_class,
            initial_boundary=initial_boundary,
            boundary_before=boundary_before,
            boundary_after=boundary_after,
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class CapacityMeasurementCorrectnessInputsV49F:
    raw_ingress_root_sha256: str
    actor_event_root_sha256: str
    projection_root_sha256: str
    no_loss: bool
    no_duplication: bool
    no_reordering: bool
    control_output_causal: bool
    projection_verified: bool
    cleanup_complete: bool
    failure_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in (
            "raw_ingress_root_sha256",
            "actor_event_root_sha256",
            "projection_root_sha256",
        ):
            object.__setattr__(
                self, name, canonical_hash(getattr(self, name), field=name)
            )
        for name in (
            "no_loss",
            "no_duplication",
            "no_reordering",
            "control_output_causal",
            "projection_verified",
            "cleanup_complete",
        ):
            if type(getattr(self, name)) is not bool:
                raise CanonicalizationError(f"{name} must be an exact boolean")
        object.__setattr__(
            self,
            "failure_codes",
            canonical_reason_codes(self.failure_codes, field="failure_codes"),
        )


async def build_capacity_measurement_bundle_v49f(
    *,
    campaign: CollectedCapacityMeasurementCampaignV49F,
    runs: Sequence[CapacityMeasurementSampleRunV49F],
    correctness_inputs: CapacityMeasurementCorrectnessInputsV49F,
) -> CapacityMeasurementArtifactBundleV49F:
    if type(campaign) is not CollectedCapacityMeasurementCampaignV49F:
        raise TypeError("campaign must be an exact collected V6 campaign")
    await campaign.assert_current()
    bundle = _build_capacity_measurement_bundle_for_test_v49f(
        manifest=campaign.manifest,
        runs=runs,
        correctness_inputs=correctness_inputs,
    )
    await campaign.assert_current()
    return bundle


def _build_capacity_measurement_bundle_for_test_v49f(
    *,
    manifest: CapacityMeasurementManifestV49F,
    runs: Sequence[CapacityMeasurementSampleRunV49F],
    correctness_inputs: CapacityMeasurementCorrectnessInputsV49F,
) -> CapacityMeasurementArtifactBundleV49F:
    """Build a provisional bundle for deterministic codec/sampler tests only."""

    if type(manifest) is not CapacityMeasurementManifestV49F:
        raise TypeError("manifest must be exact CapacityMeasurementManifestV49F")
    normalized = tuple(runs)
    if not normalized or any(
        type(item) is not CapacityMeasurementSampleRunV49F for item in normalized
    ):
        raise TypeError("runs must contain exact sample runs")
    if type(correctness_inputs) is not CapacityMeasurementCorrectnessInputsV49F:
        raise TypeError("correctness_inputs must be exact")
    samples = tuple(item.sample for item in normalized)
    observations_complete = all(
        sample.measurement_outcome is CapacityMeasurementOutcomeV49F.PASS
        and sample.admission_attribution == "EXACT_RETURNED_GRANT"
        and not sample.before_snapshot.unavailable_fields
        and not sample.in_operation_snapshot.unavailable_fields
        and not sample.after_snapshot.unavailable_fields
        for sample in samples
    )
    failures = set(correctness_inputs.failure_codes)
    checks = {
        "NO_LOSS_FAILED": correctness_inputs.no_loss,
        "NO_DUPLICATION_FAILED": correctness_inputs.no_duplication,
        "NO_REORDERING_FAILED": correctness_inputs.no_reordering,
        "CONTROL_OUTPUT_CAUSALITY_FAILED": correctness_inputs.control_output_causal,
        "PROJECTION_VERIFICATION_FAILED": correctness_inputs.projection_verified,
        "CLEANUP_INCOMPLETE": correctness_inputs.cleanup_complete,
        "OBSERVATIONS_INCOMPLETE": observations_complete,
    }
    failures.update(code for code, passed in checks.items() if not passed)
    failures.add(A2M_CORRECTNESS_FINALIZER_NOT_IMPLEMENTED_V49F)
    correctness = CapacityMeasurementCorrectnessV49F(
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
        raw_ingress_root_sha256=correctness_inputs.raw_ingress_root_sha256,
        actor_event_root_sha256=correctness_inputs.actor_event_root_sha256,
        projection_root_sha256=correctness_inputs.projection_root_sha256,
        no_loss=False,
        no_duplication=False,
        no_reordering=False,
        control_output_causal=False,
        projection_verified=False,
        observations_complete=observations_complete,
        cleanup_complete=False,
        failure_codes=tuple(failures),
    )
    return CapacityMeasurementArtifactBundleV49F.build(
        manifest=manifest,
        samples=samples,
        correctness=correctness,
    )


@dataclass(frozen=True, slots=True, kw_only=True)
class CapacityMeasurementSampleRunV49FV7:
    """One terminalized Raw-V7 operation plus its surfaced exception class."""

    sample: Any
    operation_exception_class: str | None

    def __post_init__(self) -> None:
        from .physical_transport_capacity_measurement_v49f import (
            CapacityMeasurementSampleV49FV7,
        )

        if type(self.sample) is not CapacityMeasurementSampleV49FV7:
            raise TypeError("Raw-V7 run sample must be exact")
        expected = self.sample.terminal.surfaced_exception_class
        if self.operation_exception_class != expected:
            raise CanonicalizationError(
                "Raw-V7 run exception differs from its durable terminal"
            )


def _capacity_measurement_v7_unavailable_observation(
    *,
    initial_boundary: Any | None = None,
    before_boundary: Any | None = None,
    before_snapshot: Any | None = None,
    in_operation_snapshot: Any | None = None,
    reason: str,
) -> Any:
    from .physical_transport_capacity_measurement_v49f import (
        CapacityMeasurementObservationV49FV7,
    )

    code = canonical_identifier(reason, field="observation_unavailable_reason")
    return CapacityMeasurementObservationV49FV7(
        initial_runtime_boundary=initial_boundary,
        initial_runtime_boundary_unavailable_reason=(
            code if initial_boundary is None else None
        ),
        before_runtime_boundary=before_boundary,
        before_runtime_boundary_unavailable_reason=(
            code if before_boundary is None else None
        ),
        after_runtime_boundary=None,
        after_runtime_boundary_unavailable_reason=code,
        before_snapshot=before_snapshot,
        before_snapshot_unavailable_reason=code if before_snapshot is None else None,
        in_operation_snapshot=in_operation_snapshot,
        in_operation_snapshot_unavailable_reason=(
            code if in_operation_snapshot is None else None
        ),
        after_snapshot=None,
        after_snapshot_unavailable_reason=code,
        returned_ingress_progress=None,
        returned_ingress_progress_unavailable_reason=code,
    )


def _capacity_measurement_v7_sample_from_prefix(
    *,
    prefix: Any,
    observation: Any,
) -> Any:
    from .physical_transport_capacity_lifecycle_v49f import (
        CapacityMeasurementOperationPrefixV49F,
    )
    from .physical_transport_capacity_measurement_v49f import (
        CapacityMeasurementCommittedLifecycleRecordV49FV7,
        CapacityMeasurementObservationV49FV7,
        CapacityMeasurementSampleV49FV7,
    )

    if (
        type(prefix) is not CapacityMeasurementOperationPrefixV49F
        or prefix.terminal is None
        or type(observation) is not CapacityMeasurementObservationV49FV7
    ):
        raise CapacityMeasurementSamplerErrorV49F(
            "Raw-V7 sample requires one exact terminalized prefix and observation"
        )
    return CapacityMeasurementSampleV49FV7(
        committed_attempt=CapacityMeasurementCommittedLifecycleRecordV49FV7(
            record=prefix.attempt,
            projection_receipt=prefix.projection_receipts[0],
        ),
        committed_terminal=CapacityMeasurementCommittedLifecycleRecordV49FV7(
            record=prefix.terminal,
            projection_receipt=prefix.projection_receipts[-1],
        ),
        recovered_prefix=prefix,
        observation=observation,
    )


def build_provisional_capacity_measurement_bundle_v49f_v7(
    *,
    campaign: CollectedCapacityMeasurementCampaignV49FV7,
    runner_authority: CapacityMeasurementCampaignRunnerAuthorizationV49FV7,
    runner: CapacityMeasurementSessionRunnerV49FV7,
    samples: Sequence[Any],
) -> Any:
    """Build one runner-bound candidate; finalizer claims remain false.

    The process-local runner capability proves only how this candidate was
    assembled during the retained campaign.  Offline replay authenticates the
    signed manifest anchor and checks suffix hash consistency; it does not turn
    the unsigned samples/correctness/integrity suffix into an authenticated
    final result.  A later independent finalizer/publisher gate remains
    mandatory.
    """

    from .physical_transport_capacity_measurement_v49f import (
        A2M_CORRECTNESS_FINALIZER_NOT_IMPLEMENTED_V49F_V7,
        A2M_POST_RUN_SUFFIX_PROVENANCE_UNATTESTED_V49F_V7,
        CapacityMeasurementArtifactBundleV49FV7,
        CapacityMeasurementCorrectnessV49FV7,
        CapacityMeasurementSampleV49FV7,
        CapacityMeasurementScheduleCoverageV49FV7,
        _expected_schedule_v49f_v7,
        _sample_roots_v49f_v7,
        capacity_measurement_observation_is_complete_v49f_v7,
        capacity_measurement_sample_stream_sha256_v49f_v7,
        validate_capacity_measurement_samples_v49f_v7,
    )

    if type(campaign) is not CollectedCapacityMeasurementCampaignV49FV7:
        raise TypeError("campaign must be an exact retained Raw-V7 campaign")
    try:
        campaign.assert_local_current()
        if not campaign.artifact_eligible:
            raise CapacityMeasurementSamplerErrorV49F(
                "Raw-V7 campaign was permanently made ineligible for publication"
            )
        normalized = campaign._assert_artifact_candidate_v49f(  # noqa: SLF001
            runtime=campaign.runtime,
            runner_authority=runner_authority,
            runner=runner,
            samples=samples,
        )
        if any(
            type(item) is not CapacityMeasurementSampleV49FV7 for item in normalized
        ):
            raise TypeError("samples must contain exact Raw-V7 samples")
        manifest = campaign.manifest
        normalized = validate_capacity_measurement_samples_v49f_v7(
            normalized, manifest=manifest
        )
        expected_count = len(_expected_schedule_v49f_v7(manifest))
        coverage = (
            CapacityMeasurementScheduleCoverageV49FV7.COMPLETE
            if len(normalized) == expected_count
            else CapacityMeasurementScheduleCoverageV49FV7.RUN_ENDING_PREFIX
        )
        raw_root, actor_root, projection_root = _sample_roots_v49f_v7(normalized)
        correctness = CapacityMeasurementCorrectnessV49FV7(
            campaign_manifest_id=manifest.campaign_manifest_id,
            manifest_authority_id=(
                manifest.manifest_authority_v7.manifest_authority_id
            ),
            sample_stream_sha256=(
                capacity_measurement_sample_stream_sha256_v49f_v7(
                    normalized, manifest=manifest
                )
            ),
            sample_count=len(normalized),
            first_sample_id=normalized[0].sample_id,
            last_sample_id=normalized[-1].sample_id,
            schedule_coverage=coverage,
            expected_sample_count=expected_count,
            last_operation_sequence=normalized[-1].attempt.operation_sequence,
            last_terminal_id=normalized[-1].terminal.terminal_id,
            raw_ingress_root_sha256=raw_root,
            actor_event_root_sha256=actor_root,
            projection_root_sha256=projection_root,
            no_loss=False,
            no_duplication=False,
            no_reordering=False,
            control_output_causal=False,
            projection_verified=False,
            observations_complete=all(
                capacity_measurement_observation_is_complete_v49f_v7(sample.observation)
                for sample in normalized
            ),
            cleanup_complete=False,
            failure_codes=(
                A2M_CORRECTNESS_FINALIZER_NOT_IMPLEMENTED_V49F_V7,
                A2M_POST_RUN_SUFFIX_PROVENANCE_UNATTESTED_V49F_V7,
            ),
        )
        bundle = CapacityMeasurementArtifactBundleV49FV7.build(
            manifest=manifest,
            samples=normalized,
            correctness=correctness,
        )
        from . import physical_transport_capacity_measurement_v49f as contract

        artifacts = bundle.artifact_bytes()
        if any(not value for value in artifacts.values()):
            raise CapacityMeasurementSamplerErrorV49F(
                "Raw-V7 final artifact closure exceeds its frozen bounds"
            )
        try:
            contract._validate_capacity_measurement_artifact_member_lengths_v49f_v7(  # noqa: SLF001
                {name: len(value) for name, value in artifacts.items()}
            )
        except contract.CapacityMeasurementArtifactErrorV49F as exc:
            raise CapacityMeasurementSamplerErrorV49F(
                "Raw-V7 final artifact closure exceeds its frozen bounds"
            ) from exc
        campaign.assert_local_current()
        return bundle
    except BaseException:
        try:
            campaign._mark_artifact_finalization_failure_v49f()  # noqa: SLF001
        except BaseException:
            pass
        raise


class CapacityMeasurementSessionRunnerV49FV7:
    """Execute the signed V7 schedule through only the retained runtime authority."""

    def __init__(
        self,
        *,
        campaign: CollectedCapacityMeasurementCampaignV49FV7,
    ) -> None:
        if type(campaign) is not CollectedCapacityMeasurementCampaignV49FV7:
            raise TypeError("runner requires an exact retained Raw-V7 campaign")
        campaign.assert_local_current()
        self._campaign = campaign
        self._runtime = campaign.runtime
        self._manifest = campaign.manifest
        predecessor = self._manifest.predecessor_manifest_v6
        self._origin = int(predecessor.monotonic_origin_nanoseconds)
        self._adapter = LocalCapacityMeasurementLayerAdapterV49F(
            runtime=self._runtime,
            manifest=predecessor,
            monotonic_ns=time.monotonic_ns,
        )
        self._runs: list[CapacityMeasurementSampleRunV49FV7] = []
        self._final_bundle: Any | None = None
        self._samples_artifact_byte_count = 0
        self._initial_currentness_validated = False
        from . import physical_transport_capacity_measurement_v49f as contract

        self._manifest_artifact_byte_count = len(
            contract.encode_capacity_measurement_json_v49f_v7(self._manifest)
        )
        if (
            self._manifest_artifact_byte_count
            > contract.A2M_MAXIMUM_MANIFEST_ARTIFACT_BYTES_V49F
        ):
            raise CapacityMeasurementSamplerErrorV49F(
                "Raw-V7 manifest exceeds its frozen artifact bound"
            )
        self._runner_authority = (
            CapacityMeasurementCampaignRunnerAuthorizationV49FV7._create(
                campaign=campaign,
                runner=self,
            )
        )

    @property
    def completed_runs(self) -> tuple[CapacityMeasurementSampleRunV49FV7, ...]:
        return tuple(self._runs)

    @property
    def completed_samples(self) -> tuple[Any, ...]:
        return tuple(item.sample for item in self._runs)

    def _offset(self) -> int:
        value = time.monotonic_ns() - self._origin
        return canonical_safe_int(value, field="Raw_V7_observer_offset", minimum=0)

    async def _ensure_initial_currentness(self) -> None:
        """Perform the expensive retained-source/runtime check once per runner."""

        if not self._initial_currentness_validated:
            await self._campaign.assert_current()
            self._initial_currentness_validated = True

    def _assert_next_sample_capacity(self) -> None:
        """Reserve a conservative bounded closure before causing an operation."""

        from . import physical_transport_capacity_measurement_v49f as contract

        self._campaign.assert_operation_context_v49f(
            runtime=self._runtime,
            runner_authority=self._runner_authority,
        )
        next_count = len(self._runs) + 1
        # One byte is the only defensible pre-effect lower bound.  Exact
        # canonical JSONL bytes are enforced after the durable terminal exists;
        # reserving the per-record maximum here would cap ordinary campaigns at
        # roughly four samples despite the signed 100k-trial protocol bound.
        next_minimum_samples_bytes = self._samples_artifact_byte_count + 1
        next_minimum_closure_bytes = (
            self._manifest_artifact_byte_count
            + next_minimum_samples_bytes
            + contract.A2M_MAXIMUM_CORRECTNESS_ARTIFACT_BYTES_V49F
            + contract.A2M_MAXIMUM_INTEGRITY_ARTIFACT_BYTES_V49F
        )
        if (
            next_count > contract.A2M_MAXIMUM_TOTAL_TRIALS_V49F
            or next_minimum_samples_bytes
            > contract.A2M_MAXIMUM_SAMPLES_ARTIFACT_BYTES_V49F
            or next_minimum_closure_bytes
            > contract.A2M_MAXIMUM_ARTIFACT_CLOSURE_BYTES_V49F
        ):
            self._campaign._mark_unpublishable_v49f(  # noqa: SLF001
                runner_authority=self._runner_authority,
            )
            raise CapacityMeasurementSamplerErrorV49F(
                "Raw-V7 next sample cannot fit its conservative artifact bounds"
            )

    def _sample_artifact_byte_count(self, sample: Any) -> int:
        """Validate and return one canonical JSONL record's incremental size."""

        from . import physical_transport_capacity_measurement_v49f as contract

        sample_bytes = contract.encode_capacity_measurement_json_v49f_v7(sample)
        byte_count = len(sample_bytes)
        next_samples_bytes = self._samples_artifact_byte_count + byte_count
        next_closure_bytes = (
            self._manifest_artifact_byte_count
            + next_samples_bytes
            + contract.A2M_MAXIMUM_CORRECTNESS_ARTIFACT_BYTES_V49F
            + contract.A2M_MAXIMUM_INTEGRITY_ARTIFACT_BYTES_V49F
        )
        if (
            byte_count > contract.A2M_MAXIMUM_SAMPLE_RECORD_BYTES_V49F
            or next_samples_bytes > contract.A2M_MAXIMUM_SAMPLES_ARTIFACT_BYTES_V49F
            or next_closure_bytes > contract.A2M_MAXIMUM_ARTIFACT_CLOSURE_BYTES_V49F
        ):
            raise CapacityMeasurementSamplerErrorV49F(
                "Raw-V7 sample exceeds its frozen record or closure bound"
            )
        return byte_count

    async def _boundary_evidence(self, *, role: str) -> Any:
        started = self._offset()
        boundary = await self._runtime.capture_capacity_measurement_boundary_v49f()
        completed = self._offset()
        expected = self._manifest.actor_baseline
        if (
            boundary.transport_session_id != expected.transport_session_id
            or boundary.driver_evidence_nonce_sha256
            != expected.driver_evidence_nonce_sha256
            or boundary.kernel_socket_identity != expected.kernel_socket_identity
            or boundary.transport_capacity_policy_id
            != expected.transport_capacity_policy_id
        ):
            raise CapacityMeasurementSamplerErrorV49F(
                "Raw-V7 runtime boundary left the signed actor authority"
            )
        return _measurement_runtime_boundary_evidence_v49f(
            boundary,
            role=role,
            capture_started_offset_nanoseconds=started,
            capture_completed_offset_nanoseconds=completed,
        )

    async def _before_observations(self) -> tuple[Any, Any, Any, Any]:
        initial = await self._boundary_evidence(role="INITIAL")
        lag = await _ScheduledLoopLagProbeV49F(asyncio.get_running_loop()).result()
        before_snapshot = await self._adapter.observe(event_loop_lag_nanoseconds=lag)
        before = await self._boundary_evidence(role="BEFORE_OPERATION")
        in_operation = self._adapter.unavailable_snapshot(
            offset=self._offset(),
            reason_code="NO_STABLE_IN_OPERATION_HOOK",
        )
        return initial, before, before_snapshot, in_operation

    async def _after_observations(self) -> tuple[Any, Any]:
        lag = await _ScheduledLoopLagProbeV49F(asyncio.get_running_loop()).result()
        after_snapshot = await self._adapter.observe(event_loop_lag_nanoseconds=lag)
        after = await self._boundary_evidence(role="AFTER_OPERATION")
        return after, after_snapshot

    @staticmethod
    def _add_secondary_failure_note(
        primary: BaseException,
        *,
        context: str,
        secondary: BaseException,
    ) -> None:
        secondary_class = f"{type(secondary).__module__}.{type(secondary).__qualname__}"
        primary.add_note(f"{context}: {secondary_class}"[:512])

    def _try_latch_unpublishable(
        self,
        *,
        primary: BaseException,
        declaration: Any | None = None,
        unenveloped: bool = False,
    ) -> None:
        """Best-effort fail-closed latch that never replaces the primary error."""

        method = (
            self._campaign._mark_unenveloped_run_termination_v49f  # noqa: SLF001
            if unenveloped
            else self._campaign._mark_unpublishable_v49f  # noqa: SLF001
        )
        try:
            method(
                runner_authority=self._runner_authority,
                declaration=declaration,
            )
        except BaseException as latch_error:
            if declaration is not None:
                try:
                    method(
                        runner_authority=self._runner_authority,
                        declaration=None,
                    )
                    return
                except BaseException as fallback_error:
                    self._add_secondary_failure_note(
                        primary,
                        context="Raw-V7 fallback campaign latch failed",
                        secondary=fallback_error,
                    )
            self._add_secondary_failure_note(
                primary,
                context="Raw-V7 campaign latch failed",
                secondary=latch_error,
            )

    def _consume_prefix_after_assembly_failure(
        self,
        *,
        declaration: Any,
        prefix: Any,
        primary: BaseException,
    ) -> None:
        """Advance one runner-issued durable prefix after assembly failure."""

        completed = False
        try:
            self._campaign._complete_operation_v49f(  # noqa: SLF001
                declaration=declaration,
                prefix=prefix,
                sample=None,
                runner_authority=self._runner_authority,
            )
            completed = True
        except BaseException as completion_error:
            self._add_secondary_failure_note(
                primary,
                context="Raw-V7 prefix completion failed",
                secondary=completion_error,
            )
        self._try_latch_unpublishable(
            primary=primary,
            declaration=None if completed else declaration,
        )

    def _assemble_and_record_prefix(
        self,
        *,
        declaration: Any,
        prefix: Any,
        observation_factory: Callable[[], Any],
    ) -> CapacityMeasurementSampleRunV49FV7:
        try:
            observation = observation_factory()
            sample = _capacity_measurement_v7_sample_from_prefix(
                prefix=prefix,
                observation=observation,
            )
            sample_byte_count = self._sample_artifact_byte_count(sample)
            run = CapacityMeasurementSampleRunV49FV7(
                sample=sample,
                operation_exception_class=(sample.terminal.surfaced_exception_class),
            )
        except BaseException as assembly_error:
            self._consume_prefix_after_assembly_failure(
                declaration=declaration,
                prefix=prefix,
                primary=assembly_error,
            )
            raise
        try:
            self._campaign._complete_operation_v49f(  # noqa: SLF001
                declaration=declaration,
                prefix=prefix,
                sample=sample,
                runner_authority=self._runner_authority,
            )
        except BaseException as completion_error:
            self._consume_prefix_after_assembly_failure(
                declaration=declaration,
                prefix=prefix,
                primary=completion_error,
            )
            raise
        try:
            self._runs.append(run)
            self._samples_artifact_byte_count += sample_byte_count
        except BaseException as recording_error:
            self._try_latch_unpublishable(primary=recording_error)
            raise
        return run

    async def run_next_ingress(self) -> CapacityMeasurementSampleRunV49FV7:
        """Run one signed schedule item; cancellation/interruption still propagate."""

        from .physical_transport_capacity_measurement_v49f import (
            CapacityMeasurementObservationV49FV7,
        )

        if not self._campaign.has_next_operation_v49f(
            runtime=self._runtime,
            runner_authority=self._runner_authority,
        ):
            raise CapacityMeasurementSamplerErrorV49F(
                "Raw-V7 campaign has no admissible next operation"
            )
        try:
            await self._ensure_initial_currentness()
            self._assert_next_sample_capacity()
            (
                initial,
                before,
                before_snapshot,
                in_operation,
            ) = await self._before_observations()
            declaration, authorization = (
                self._runtime.issue_capacity_measurement_ingress_authorization_v49f_v7(
                    campaign=self._campaign,
                    runner_authority=self._runner_authority,
                    runner=self,
                )
            )
        except BaseException as preparation_error:
            self._try_latch_unpublishable(
                primary=preparation_error,
                unenveloped=True,
            )
            raise
        try:
            closure = (
                await self._runtime.process_next_ingress_for_capacity_measurement_v49f(
                    campaign=self._campaign,
                    declaration=declaration,
                    authorization=authorization,
                )
            )
        except BaseException as exc:
            attempt_id = authorization.committed_attempt_id
            if attempt_id is None:
                self._try_latch_unpublishable(
                    primary=exc,
                    declaration=declaration,
                    unenveloped=True,
                )
                raise
            try:
                prefix = (
                    self._runtime.load_capacity_measurement_operation_prefix_v49f_v7(
                        campaign=self._campaign,
                        attempt_id=attempt_id,
                    )
                )
            except BaseException as recovery_error:
                self._try_latch_unpublishable(
                    primary=exc,
                    declaration=declaration,
                    unenveloped=True,
                )
                self._add_secondary_failure_note(
                    exc,
                    context=(
                        "Raw-V7 committed attempt lacks an immediately "
                        "recoverable terminal"
                    ),
                    secondary=recovery_error,
                )
                raise
            assembly_error: BaseException | None = None
            try:
                run = self._assemble_and_record_prefix(
                    declaration=declaration,
                    prefix=prefix,
                    observation_factory=lambda: (
                        _capacity_measurement_v7_unavailable_observation(
                            initial_boundary=initial,
                            before_boundary=before,
                            before_snapshot=before_snapshot,
                            in_operation_snapshot=in_operation,
                            reason="OPERATION_DID_NOT_RETURN",
                        )
                    ),
                )
            except BaseException as failure:
                assembly_error = failure
            if assembly_error is not None:
                self._add_secondary_failure_note(
                    exc,
                    context="Raw-V7 exception-prefix sample assembly failed",
                    secondary=assembly_error,
                )
                raise
            if isinstance(exc, Exception) and not isinstance(
                exc, asyncio.CancelledError
            ):
                return run
            raise

        prefix = closure.terminalized_prefix
        try:
            after, after_snapshot = await self._after_observations()
        except BaseException as observation_error:
            assembly_error = None
            try:
                self._assemble_and_record_prefix(
                    declaration=declaration,
                    prefix=prefix,
                    observation_factory=lambda: (
                        _capacity_measurement_v7_unavailable_observation(
                            initial_boundary=initial,
                            before_boundary=before,
                            before_snapshot=before_snapshot,
                            in_operation_snapshot=in_operation,
                            reason="POST_OPERATION_OBSERVATION_INTERRUPTED",
                        )
                    ),
                )
            except BaseException as failure:
                assembly_error = failure
            if assembly_error is None:
                self._try_latch_unpublishable(
                    primary=observation_error,
                    unenveloped=True,
                )
            else:
                self._add_secondary_failure_note(
                    observation_error,
                    context="Raw-V7 interrupted observation assembly failed",
                    secondary=assembly_error,
                )
            raise
        return self._assemble_and_record_prefix(
            declaration=declaration,
            prefix=prefix,
            observation_factory=lambda: CapacityMeasurementObservationV49FV7(
                initial_runtime_boundary=initial,
                initial_runtime_boundary_unavailable_reason=None,
                before_runtime_boundary=before,
                before_runtime_boundary_unavailable_reason=None,
                after_runtime_boundary=after,
                after_runtime_boundary_unavailable_reason=None,
                before_snapshot=before_snapshot,
                before_snapshot_unavailable_reason=None,
                in_operation_snapshot=in_operation,
                in_operation_snapshot_unavailable_reason=None,
                after_snapshot=after_snapshot,
                after_snapshot_unavailable_reason=None,
                returned_ingress_progress=closure.returned_progress_evidence,
                returned_ingress_progress_unavailable_reason=None,
            ),
        )

    async def run_campaign(self) -> Any:
        """Run until complete or a runner-recorded run-ending prefix, then build."""

        from .physical_transport_capacity_measurement_v49f import (
            _expected_schedule_v49f_v7,
            _terminal_is_run_ending_v49f_v7,
        )

        if self._final_bundle is not None:
            return self._final_bundle
        expected = len(_expected_schedule_v49f_v7(self._manifest))
        run_ended = bool(self._runs) and _terminal_is_run_ending_v49f_v7(
            self._runs[-1].sample.terminal,
            lifecycle_contract=self._manifest.lifecycle_contract,
        )
        while len(self._runs) < expected and not run_ended:
            run = await self.run_next_ingress()
            run_ended = _terminal_is_run_ending_v49f_v7(
                run.sample.terminal,
                lifecycle_contract=self._manifest.lifecycle_contract,
            )
        try:
            await self._campaign.assert_current()
            bundle = build_provisional_capacity_measurement_bundle_v49f_v7(
                campaign=self._campaign,
                runner_authority=self._runner_authority,
                runner=self,
                samples=self.completed_samples,
            )
            self._final_bundle = bundle
            return bundle
        except BaseException as finalization_error:
            try:
                self._campaign._mark_artifact_finalization_failure_v49f()  # noqa: SLF001
            except BaseException as latch_error:
                self._add_secondary_failure_note(
                    finalization_error,
                    context="Raw-V7 finalization latch failed",
                    secondary=latch_error,
                )
            raise


RAW_V7_LIFECYCLE_NEUTRALITY_BASELINE_PROFILE_V49F = "RAW_V7_LIFECYCLE_JOURNAL_ON"
RAW_V7_LITERAL_NEUTRALITY_CLAIM_SCOPE_V49F = (
    "RAW_V7_LIFECYCLE_BASELINE_BYTE_AND_ROOT_EQUIVALENCE"
)
RAW_V7_PHYSICAL_NEUTRALITY_CLAIM_SCOPE_V49F = (
    "RAW_V7_LIFECYCLE_BASELINE_PHYSICAL_ALPHA_NO_BYTE_OR_ROOT_EQUIVALENCE"
)
MAX_CAPACITY_MEASUREMENT_NEUTRALITY_PREFIX_OCTETS_V49F = 16 * 1024 * 1024
MAX_CAPACITY_MEASUREMENT_NEUTRALITY_SEQUENCE_ITEMS_V49F = 4096
MAX_CAPACITY_MEASUREMENT_NEUTRALITY_IDENTIFIER_UTF8_OCTETS_V49F = 256
MAX_CAPACITY_MEASUREMENT_NEUTRALITY_CAUSAL_LINKS_V49F = 65_536


class CapacityMeasurementNeutralityArmV49FV7(str, Enum):
    """Admissible Raw-V7 arms under the lifecycle-on neutrality baseline.

    Resource observation may vary between arms.  Lifecycle journaling may not:
    Raw V6/no-lifecycle data is deliberately unrepresentable by this type.
    """

    RESOURCE_PROBES_OFF = "RAW_V7_RESOURCE_PROBES_OFF"
    RESOURCE_PROBES_ON = "RAW_V7_RESOURCE_PROBES_ON"

    @property
    def lifecycle_journaling_enabled(self) -> bool:
        return True

    @property
    def resource_probes_enabled(self) -> bool:
        return self is CapacityMeasurementNeutralityArmV49FV7.RESOURCE_PROBES_ON

    @property
    def raw_protocol_profile(self) -> str:
        return RAW_V7_LIFECYCLE_NEUTRALITY_BASELINE_PROFILE_V49F


def _assert_v7_lifecycle_neutrality_arm_v49f(
    arm: CapacityMeasurementNeutralityArmV49FV7,
) -> None:
    if type(arm) is not CapacityMeasurementNeutralityArmV49FV7:
        raise TypeError("neutrality_arm must be an exact Raw-V7 lifecycle-on arm")
    if (
        not arm.lifecycle_journaling_enabled
        or arm.raw_protocol_profile != RAW_V7_LIFECYCLE_NEUTRALITY_BASELINE_PROFILE_V49F
    ):
        raise CanonicalizationError(
            "neutrality arm must retain the Raw-V7 lifecycle-on baseline"
        )


def _bounded_neutrality_identifiers_v49f(
    value: Any, *, field: str, maximum_characters: int = 128
) -> tuple[str, ...]:
    if (
        type(value) is not tuple
        or len(value) > MAX_CAPACITY_MEASUREMENT_NEUTRALITY_SEQUENCE_ITEMS_V49F
    ):
        raise CanonicalizationError(f"{field} must be a bounded exact tuple")
    normalized: list[str] = []
    for item in value:
        if type(item) is not str:
            raise CanonicalizationError(f"{field} entries must be exact strings")
        canonical = canonical_identifier(item, field=field, maximum=maximum_characters)
        if (
            len(canonical.encode("utf-8"))
            > MAX_CAPACITY_MEASUREMENT_NEUTRALITY_IDENTIFIER_UTF8_OCTETS_V49F
        ):
            raise CanonicalizationError(
                f"{field} entry exceeds the UTF-8 octet ceiling"
            )
        normalized.append(canonical)
    return tuple(normalized)


@dataclass(frozen=True, slots=True, kw_only=True)
class CapacityMeasurementLiteralNeutralityTraceV49F:
    neutrality_arm: CapacityMeasurementNeutralityArmV49FV7
    raw_prefix_bytes: bytes
    actor_prefix_bytes: bytes
    projection_prefix_bytes: bytes
    logical_output_bytes: bytes
    outcome_classes: tuple[str, ...]

    def __post_init__(self) -> None:
        _assert_v7_lifecycle_neutrality_arm_v49f(self.neutrality_arm)
        for name in (
            "raw_prefix_bytes",
            "actor_prefix_bytes",
            "projection_prefix_bytes",
            "logical_output_bytes",
        ):
            value = getattr(self, name)
            if (
                type(value) is not bytes
                or len(value) > MAX_CAPACITY_MEASUREMENT_NEUTRALITY_PREFIX_OCTETS_V49F
            ):
                raise CanonicalizationError(
                    f"{name} must be exact bytes within the octet ceiling"
                )
        outcomes = _bounded_neutrality_identifiers_v49f(
            self.outcome_classes, field="outcome_classes"
        )
        object.__setattr__(self, "outcome_classes", outcomes)


@dataclass(frozen=True, slots=True, kw_only=True)
class CapacityMeasurementPhysicalNeutralityTraceV49F:
    neutrality_arm: CapacityMeasurementNeutralityArmV49FV7
    actor_event_kinds: tuple[str, ...]
    causal_parent_ordinals: tuple[tuple[int, ...], ...]
    logical_frames: tuple[tuple[str, str], ...]
    admission_decisions: tuple[str, ...]
    operation_outcomes: tuple[str, ...]
    runtime_states: tuple[str, ...]
    chain_verified: bool
    projection_verified: bool

    def __post_init__(self) -> None:
        _assert_v7_lifecycle_neutrality_arm_v49f(self.neutrality_arm)
        for name in (
            "actor_event_kinds",
            "admission_decisions",
            "operation_outcomes",
            "runtime_states",
        ):
            values = _bounded_neutrality_identifiers_v49f(
                getattr(self, name), field=name
            )
            object.__setattr__(self, name, values)
        if (
            type(self.logical_frames) is not tuple
            or len(self.logical_frames)
            > MAX_CAPACITY_MEASUREMENT_NEUTRALITY_SEQUENCE_ITEMS_V49F
        ):
            raise CanonicalizationError(
                "logical_frames must be an exact tuple within the item ceiling"
            )
        for frame in self.logical_frames:
            if type(frame) is not tuple or len(frame) != 2:
                raise CanonicalizationError("logical_frames must contain exact pairs")
            if type(frame[0]) is not str or type(frame[1]) is not str:
                raise CanonicalizationError(
                    "logical_frames must contain exact string pairs"
                )
            opcode = canonical_identifier(
                frame[0], field="logical_frame_opcode", maximum=16
            )
            if (
                len(opcode.encode("utf-8"))
                > MAX_CAPACITY_MEASUREMENT_NEUTRALITY_IDENTIFIER_UTF8_OCTETS_V49F
            ):
                raise CanonicalizationError(
                    "logical frame opcode exceeds the UTF-8 octet ceiling"
                )
            canonical_hash(frame[1], field="logical_frame_payload_sha256")
        if (
            type(self.causal_parent_ordinals) is not tuple
            or len(self.causal_parent_ordinals)
            > MAX_CAPACITY_MEASUREMENT_NEUTRALITY_SEQUENCE_ITEMS_V49F
            or len(self.causal_parent_ordinals) != len(self.actor_event_kinds)
        ):
            raise CanonicalizationError(
                "causal_parent_ordinals must align exactly with actor events within the item ceiling"
            )
        causal_link_count = 0
        for event_ordinal, parents in enumerate(self.causal_parent_ordinals):
            if type(parents) is not tuple or any(
                type(value) is not int
                or value < 0
                or value >= event_ordinal
                or value > MAX_IJSON_INTEGER
                for value in parents
            ):
                raise CanonicalizationError(
                    "causal parents must be exact earlier event ordinals"
                )
            if tuple(sorted(set(parents))) != parents:
                raise CanonicalizationError(
                    "causal parents must be unique and canonically ordered"
                )
            causal_link_count += len(parents)
            if (
                len(parents) > MAX_CAPACITY_MEASUREMENT_NEUTRALITY_SEQUENCE_ITEMS_V49F
                or causal_link_count
                > MAX_CAPACITY_MEASUREMENT_NEUTRALITY_CAUSAL_LINKS_V49F
            ):
                raise CanonicalizationError(
                    "causal parents exceed the bounded link ceiling"
                )
        for name in ("chain_verified", "projection_verified"):
            if type(getattr(self, name)) is not bool:
                raise CanonicalizationError(f"{name} must be an exact boolean")


_CAPACITY_MEASUREMENT_NEUTRALITY_REPORT_TOKEN_V49F = object()


@dataclass(frozen=True, slots=True, kw_only=True)
class CapacityMeasurementNeutralityReportV49F:
    comparison_profile: str
    lifecycle_baseline_profile: str
    left_arm: CapacityMeasurementNeutralityArmV49FV7
    right_arm: CapacityMeasurementNeutralityArmV49FV7
    equivalence_claim_scope: str
    byte_or_root_equivalence_claimed: bool
    mismatch_fields: tuple[str, ...]
    _construction_token: InitVar[object] = None

    def __post_init__(self, _construction_token: object) -> None:
        if (
            _construction_token
            is not _CAPACITY_MEASUREMENT_NEUTRALITY_REPORT_TOKEN_V49F
        ):
            raise TypeError(
                "neutrality reports may only be constructed by the comparator"
            )
        _assert_v7_lifecycle_neutrality_arm_v49f(self.left_arm)
        _assert_v7_lifecycle_neutrality_arm_v49f(self.right_arm)
        if (
            self.lifecycle_baseline_profile
            != RAW_V7_LIFECYCLE_NEUTRALITY_BASELINE_PROFILE_V49F
        ):
            raise CanonicalizationError(
                "neutrality report must retain the Raw-V7 lifecycle-on baseline"
            )
        expected_claims = {
            "LITERAL_DETERMINISTIC_AUTHORITY_PREFIX_RAW_V7_V49F": (
                RAW_V7_LITERAL_NEUTRALITY_CLAIM_SCOPE_V49F,
                True,
            ),
            "PREREGISTERED_PHYSICAL_ALPHA_EQUIVALENCE_RAW_V7_V49F": (
                RAW_V7_PHYSICAL_NEUTRALITY_CLAIM_SCOPE_V49F,
                False,
            ),
        }
        expected = expected_claims.get(self.comparison_profile)
        if expected is None or expected != (
            self.equivalence_claim_scope,
            self.byte_or_root_equivalence_claimed,
        ):
            raise CanonicalizationError(
                "neutrality report comparison profile and claim scope differ"
            )
        if type(self.mismatch_fields) is not tuple or any(
            type(field) is not str or not field for field in self.mismatch_fields
        ):
            raise CanonicalizationError(
                "neutrality report mismatch_fields must be exact non-empty strings"
            )

    @property
    def passed(self) -> bool:
        return not self.mismatch_fields


def compare_capacity_measurement_neutrality_v49f(
    off: CapacityMeasurementLiteralNeutralityTraceV49F
    | CapacityMeasurementPhysicalNeutralityTraceV49F,
    on: CapacityMeasurementLiteralNeutralityTraceV49F
    | CapacityMeasurementPhysicalNeutralityTraceV49F,
) -> CapacityMeasurementNeutralityReportV49F:
    if type(off) is not type(on):
        raise TypeError("neutrality traces must use one exact comparison profile")
    if type(off) is CapacityMeasurementLiteralNeutralityTraceV49F:
        profile = "LITERAL_DETERMINISTIC_AUTHORITY_PREFIX_RAW_V7_V49F"
        claim_scope = RAW_V7_LITERAL_NEUTRALITY_CLAIM_SCOPE_V49F
        byte_or_root_equivalence_claimed = True
    elif type(off) is CapacityMeasurementPhysicalNeutralityTraceV49F:
        profile = "PREREGISTERED_PHYSICAL_ALPHA_EQUIVALENCE_RAW_V7_V49F"
        claim_scope = RAW_V7_PHYSICAL_NEUTRALITY_CLAIM_SCOPE_V49F
        byte_or_root_equivalence_claimed = False
    else:
        raise TypeError("unsupported neutrality trace profile")
    _assert_v7_lifecycle_neutrality_arm_v49f(off.neutrality_arm)
    _assert_v7_lifecycle_neutrality_arm_v49f(on.neutrality_arm)
    mismatches = tuple(
        name
        for name in off.__dataclass_fields__
        if name != "neutrality_arm"
        if getattr(off, name) != getattr(on, name)
    )
    if type(off) is CapacityMeasurementPhysicalNeutralityTraceV49F:
        mismatches = tuple(
            dict.fromkeys(
                (
                    *mismatches,
                    *(
                        name
                        for name in ("chain_verified", "projection_verified")
                        if not getattr(off, name) or not getattr(on, name)
                    ),
                )
            )
        )
    return CapacityMeasurementNeutralityReportV49F(
        comparison_profile=profile,
        lifecycle_baseline_profile=(RAW_V7_LIFECYCLE_NEUTRALITY_BASELINE_PROFILE_V49F),
        left_arm=off.neutrality_arm,
        right_arm=on.neutrality_arm,
        equivalence_claim_scope=claim_scope,
        byte_or_root_equivalence_claimed=byte_or_root_equivalence_claimed,
        mismatch_fields=mismatches,
        _construction_token=_CAPACITY_MEASUREMENT_NEUTRALITY_REPORT_TOKEN_V49F,
    )


def assert_capacity_measurement_neutrality_v49f(
    off: CapacityMeasurementLiteralNeutralityTraceV49F
    | CapacityMeasurementPhysicalNeutralityTraceV49F,
    on: CapacityMeasurementLiteralNeutralityTraceV49F
    | CapacityMeasurementPhysicalNeutralityTraceV49F,
) -> None:
    report = compare_capacity_measurement_neutrality_v49f(off, on)
    if not report.passed:
        raise CapacityMeasurementSamplerErrorV49F(
            "instrumentation neutrality failed: " + ", ".join(report.mismatch_fields)
        )
