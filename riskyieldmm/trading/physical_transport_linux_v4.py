"""Concrete Linux owner/clock authority through the V4.9C staged-send seam.

There is intentionally no portable fallback.  Promotion-eligible evidence
requires Linux ``CLOCK_BOOTTIME``, per-thread time/network namespace handles,
``SO_COOKIE``, ``SO_NETNS_COOKIE``, and a hash-pinned chronyc 4.8 CSV query.

The deterministic adapter proves only a bounded direct-query claim.  The exact
V4.8B profile instead requires the prospective owned-launch authority and binds
its retained daemon/configuration provenance into every sample.  Neither path
attests systemd's complete effective manager state, exclusive host-clock
discipline, upstream UTC truth, peer delivery, or trading edge.

The V4.9C methods retain exact wire/ciphertext artifacts behind one owner I/O
lock.  A positive ``socket.send`` result is local kernel acceptance only; the
runtime remains responsible for durable result recording or immediate abort.
"""

from __future__ import annotations

import asyncio
import errno
import fcntl
import hashlib
import math
import os
import re
import selectors
import signal
import socket
import subprocess
import sys
import termios
import threading
import time
import weakref
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import ROUND_CEILING, Decimal, InvalidOperation
from enum import Enum
from typing import Any, Final, Protocol, runtime_checkable

from .canonical import (
    CanonicalizationError,
    canonical_hash,
    canonical_identifier,
    canonical_reason_codes,
    canonical_safe_int,
    sha256_digest,
    utc_datetime,
)
from .chronyd_provenance_v48b import ChronydLaunchAuthorityV48B
from .operational_artifact_loading_v4 import (
    ConfiguredChronySourceArtifactV4,
    OperationalArtifactV4Error,
    PinnedRuntimeArtifactV4,
    RuntimeArtifactSpecV4,
    derive_configured_chrony_source_set_root_v4,
)
from .operational_manifests_v4 import ClockSourcePolicyManifestV4
from .physical_transport_control_v4 import RawIngressCommitV4
from .physical_transport_owner_v4 import (
    TransportSocketOwnerSnapshotV4,
    derive_linux_boottime_clock_domain_id,
    derive_linux_namespace_id,
    format_linux_socket_cookie_u64,
)
from .physical_transport_runtime_v4 import (
    ClockEvidenceV4,
    OperationalDeploymentAdmissionV4,
    PhysicalTransportRuntimeConfigV4,
    PhysicalTransportRuntimeV4,
)
from .physical_transport_tls_v49 import (
    V49_MAXIMUM_TLS_OPERATION_CIPHERTEXT_BYTES,
    DriverHandshakeEvidenceV49,
    DurableIngressAdoptionV49D,
    ExactTlsWebSocketDriverV49,
    ParsedDurableUnitV49D,
    PendingRawIngressV49,
    PhysicalTlsWebSocketV49DeadlineExpiredAfterProgress,
    PhysicalTlsWebSocketV49DeadlineExpiredNoObservation,
    PhysicalTlsWebSocketV49SendDeadlineExpiredNoKernelAcceptance,
    PhysicalTlsWebSocketV49UnsendablePostHandshakeOutput,
    PreparedTlsCiphertextV49C,
    PreparedTlsControlCiphertextV49E,
    PreparedWebSocketWireV49C,
    TlsControlOutputKindV49E,
    TlsShutdownObservationKindV49E,
    TlsShutdownObservationV49E,
    TlsWebSocketDriverFlowSnapshotV49F,
    TlsWebSocketDriverStateV49,
    UnsendableTlsPostHandshakeOutputV49E,
)
from .physical_transport_v4 import (
    TransportSessionAttestationV4,
    TransportSubscriptionPolicyV4,
)

_NS_GET_NSTYPE: Final = 0xB703
_CLONE_NEWTIME: Final = 0x00000080
_CLONE_NEWNET: Final = 0x40000000
_SO_COOKIE: Final = 57
_SO_NETNS_COOKIE: Final = 71
# Linux aliases SIOCINQ to FIONREAD and SIOCOUTQ to TIOCOUTQ.  ``termios``
# supplies the architecture value when available; these fallbacks are the
# asm-generic values used by supported Linux builds.
_SIOCINQ: Final = getattr(termios, "FIONREAD", 0x541B)
_SIOCOUTQ: Final = getattr(termios, "TIOCOUTQ", 0x5411)
_MAX_CHRONY_SOURCES: Final = 64
_MAX_CLOCK_EVIDENCE_LIFETIME_MILLISECONDS: Final = 5_000
_VERSION_RE: Final = re.compile(
    rb"chronyc \(chrony\) version ([0-9][A-Za-z0-9.+-]{0,63})(?: \([^\r\n]{1,512}\))?\n?"
)
_REF_ID_RE: Final = re.compile(r"^[0-9A-F]{8}$")
_BOOT_ID_RE: Final = re.compile(
    rb"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\n?$"
)
_CHRONY_ENV: Final = {
    "LANG": "C",
    "LC_ALL": "C",
    "PATH": "/usr/bin:/bin",
    "TZ": "UTC",
}
_V49B_TRANSITION_TOKEN: Final = object()
_V49E_TCP_WRITE_SHUTDOWN_TOKEN: Final = object()
_V49E_TCP_WRITE_SHUTDOWN_RESULT_TOKEN: Final = object()
_V49E_OWNER_TLS_SHUTDOWN_OBSERVATION_TOKEN: Final = object()
_V49E_OWNER_UNSENDABLE_TLS_OUTPUT_TOKEN: Final = object()
_V49E_OWNER_UNSENDABLE_TLS_OUTPUT_EXCEPTION_TOKEN: Final = object()
_V49E_OWNER_DEADLINE_EXPIRED_NO_OBSERVATION_TOKEN: Final = object()
_V49E_OWNER_DEADLINE_EXPIRED_AFTER_PROGRESS_TOKEN: Final = object()
_V49E_OWNER_SEND_DEADLINE_NO_KERNEL_ACCEPTANCE_TOKEN: Final = object()
_V49E_DEADLINE_OPERATIONS: Final = frozenset(
    {
        "TERMINAL_CLOSE_INGRESS",
        "LOCAL_WEBSOCKET_CLOSE_PREPARATION",
        "LOCAL_WEBSOCKET_CLOSE_TLS_PREPARATION",
        "WEBSOCKET_CLOSE_SEND_BEFORE_SYSCALL",
        "LOCAL_TLS_CLOSE_NOTIFY_PREPARATION",
        "TCP_WRITE_SHUTDOWN_TOKEN_PREPARATION",
        "TLS_SHUTDOWN_POLL",
        "TLS_CONTROL_SEND_BEFORE_SYSCALL",
    }
)


class LinuxTransportEvidenceV4Error(RuntimeError):
    """Base error for unavailable or invalid Linux transport evidence."""


class LinuxNamespaceEvidenceV4Error(LinuxTransportEvidenceV4Error):
    """A pinned per-thread Linux namespace changed or is unsupported."""


class LinuxChronyEvidenceV4Error(LinuxTransportEvidenceV4Error):
    """Chrony execution, parsing, freshness, or uncertainty failed closed."""


class LinuxSocketOwnerV4Error(LinuxTransportEvidenceV4Error):
    """The retained socket is unavailable, changed, or outside its namespace."""


class LinuxSocketOwnerV4DeadlineExpiredNoObservationV49E(TimeoutError):
    """Owner-proven deadline expiry before one exact seam made progress."""

    __slots__ = (
        "__weakref__",
        "_deadline_ns",
        "_driver_evidence_nonce_sha256",
        "_kernel_socket_identity",
        "_operation",
        "_owner_evidence_id",
        "_transport_session_id",
    )

    _deadline_ns: int
    _operation: str

    def __init__(
        self,
        *,
        _token: object,
        transport_session_id: str,
        kernel_socket_identity: str,
        driver_evidence_nonce_sha256: str,
        operation: str,
        deadline_ns: int,
        owner_evidence_id: str,
    ) -> None:
        if _token is not _V49E_OWNER_DEADLINE_EXPIRED_NO_OBSERVATION_TOKEN:
            raise TypeError(
                "owner no-observation deadline errors are owner-constructed only"
            )
        if (
            type(operation) is not str
            or operation not in _V49E_DEADLINE_OPERATIONS
            or type(deadline_ns) is not int
            or deadline_ns < 1
        ):
            raise TypeError("owner no-observation deadline evidence is invalid")
        self._operation = operation
        self._deadline_ns = deadline_ns
        self._transport_session_id = transport_session_id
        self._kernel_socket_identity = kernel_socket_identity
        self._driver_evidence_nonce_sha256 = driver_evidence_nonce_sha256
        self._owner_evidence_id = owner_evidence_id
        super().__init__(
            f"V4.9E {operation} deadline expired before observable progress"
        )

    @property
    def operation(self) -> str:
        return self._operation

    @property
    def deadline_ns(self) -> int:
        return self._deadline_ns

    @property
    def transport_session_id(self) -> str:
        return self._transport_session_id

    @property
    def kernel_socket_identity(self) -> str:
        return self._kernel_socket_identity

    @property
    def driver_evidence_nonce_sha256(self) -> str:
        return self._driver_evidence_nonce_sha256

    @property
    def owner_evidence_id(self) -> str:
        return self._owner_evidence_id

    def consume_for_actor_v49e(
        self,
        *,
        transport_session_id: str,
        driver_evidence_nonce_sha256: str,
        operation: str,
        deadline_ns: int,
    ) -> LinuxSocketOwnerV4DeadlineExpiredNoObservationV49E:
        LinuxSocketOwnerV4._assert_deadline_expired_no_observation_integrity_v49e(self)
        if (
            self.transport_session_id != transport_session_id
            or self.driver_evidence_nonce_sha256 != driver_evidence_nonce_sha256
            or self.operation != operation
            or self.deadline_ns != deadline_ns
        ):
            raise LinuxSocketOwnerV4Error(
                "no-observation deadline evidence differs from actor authority"
            )
        _consume_owner_capability_v49e(
            capability_kind="DEADLINE_EXPIRED_NO_OBSERVATION",
            capability_id=self.owner_evidence_id,
            capability=self,
        )
        _register_owner_capability_v49e(
            _token=_V49E_OWNER_CAPABILITY_REGISTRATION_TOKEN,
            capability_kind="TERMINAL_CLOCK_AUTHORIZATION_HANDOFF",
            capability_id=self.owner_evidence_id,
            capability=self,
        )
        return self


class LinuxSocketOwnerV4DeadlineExpiredAfterProgressV49E(TimeoutError):
    """Sealed owner-bound partial TLS progress retained for actor convergence."""

    __slots__ = (
        "__weakref__",
        "_ciphertext_octets_received",
        "_ciphertext_sha256",
        "_deadline_ns",
        "_driver_evidence_id",
        "_driver_evidence_nonce_sha256",
        "_kernel_socket_identity",
        "_operation",
        "_owner_evidence_id",
        "_transport_session_id",
    )

    def __init__(
        self,
        *,
        _token: object,
        transport_session_id: str,
        kernel_socket_identity: str,
        driver_evidence_nonce_sha256: str,
        operation: str,
        deadline_ns: int,
        ciphertext_octets_received: int,
        ciphertext_sha256: str,
        driver_evidence_id: str,
        owner_evidence_id: str,
    ) -> None:
        if _token is not _V49E_OWNER_DEADLINE_EXPIRED_AFTER_PROGRESS_TOKEN:
            raise TypeError(
                "owner partial-progress deadline errors are owner-constructed only"
            )
        self._transport_session_id = transport_session_id
        self._kernel_socket_identity = kernel_socket_identity
        self._driver_evidence_nonce_sha256 = driver_evidence_nonce_sha256
        self._operation = operation
        self._deadline_ns = deadline_ns
        self._ciphertext_octets_received = ciphertext_octets_received
        self._ciphertext_sha256 = ciphertext_sha256
        self._driver_evidence_id = driver_evidence_id
        self._owner_evidence_id = owner_evidence_id
        super().__init__(
            f"V4.9E {operation} deadline expired after positive ciphertext"
        )

    @property
    def transport_session_id(self) -> str:
        return self._transport_session_id

    @property
    def kernel_socket_identity(self) -> str:
        return self._kernel_socket_identity

    @property
    def driver_evidence_nonce_sha256(self) -> str:
        return self._driver_evidence_nonce_sha256

    @property
    def operation(self) -> str:
        return self._operation

    @property
    def deadline_ns(self) -> int:
        return self._deadline_ns

    @property
    def ciphertext_octets_received(self) -> int:
        return self._ciphertext_octets_received

    @property
    def ciphertext_sha256(self) -> str:
        return self._ciphertext_sha256

    @property
    def driver_evidence_id(self) -> str:
        return self._driver_evidence_id

    @property
    def owner_evidence_id(self) -> str:
        return self._owner_evidence_id

    def consume_for_actor_v49e(
        self,
        *,
        transport_session_id: str,
        driver_evidence_nonce_sha256: str,
        operation: str,
        deadline_ns: int,
    ) -> LinuxSocketOwnerV4DeadlineExpiredAfterProgressV49E:
        LinuxSocketOwnerV4._assert_deadline_expired_after_progress_integrity_v49e(self)
        if (
            self.transport_session_id != transport_session_id
            or self.driver_evidence_nonce_sha256 != driver_evidence_nonce_sha256
            or self.operation != operation
            or self.deadline_ns != deadline_ns
        ):
            raise LinuxSocketOwnerV4Error(
                "partial-progress deadline evidence differs from actor authority"
            )
        _consume_owner_capability_v49e(
            capability_kind="DEADLINE_EXPIRED_AFTER_PROGRESS",
            capability_id=self.owner_evidence_id,
            capability=self,
        )
        _register_owner_capability_v49e(
            _token=_V49E_OWNER_CAPABILITY_REGISTRATION_TOKEN,
            capability_kind="TERMINAL_CLOCK_AUTHORIZATION_HANDOFF",
            capability_id=self.owner_evidence_id,
            capability=self,
        )
        return self


class LinuxSocketOwnerV4SendDeadlineExpiredNoKernelAcceptanceV49E(TimeoutError):
    """One-shot owner-bound proof of EAGAIN-only send deadline expiry."""

    __slots__ = (
        "__weakref__",
        "_ciphertext_batch_sha256",
        "_ciphertext_octets",
        "_ciphertext_start_octet",
        "_deadline_ns",
        "_driver_evidence_id",
        "_driver_evidence_nonce_sha256",
        "_exact_slice_sha256",
        "_kernel_socket_identity",
        "_owner_evidence_id",
        "_requested_octets",
        "_send_kind",
        "_transport_sequence",
        "_transport_session_id",
        "_would_block_count",
    )

    def __init__(self, *, _token: object, **values: Any) -> None:
        if _token is not _V49E_OWNER_SEND_DEADLINE_NO_KERNEL_ACCEPTANCE_TOKEN:
            raise TypeError("owner send-deadline errors are owner-constructed only")
        for name in (
            "transport_session_id",
            "kernel_socket_identity",
            "driver_evidence_nonce_sha256",
            "send_kind",
            "transport_sequence",
            "ciphertext_batch_sha256",
            "ciphertext_octets",
            "ciphertext_start_octet",
            "requested_octets",
            "exact_slice_sha256",
            "deadline_ns",
            "would_block_count",
            "driver_evidence_id",
            "owner_evidence_id",
        ):
            object.__setattr__(self, f"_{name}", values[name])
        super().__init__(
            "V4.9E send deadline expired after no kernel-accepted ciphertext"
        )

    @property
    def transport_session_id(self) -> str:
        return self._transport_session_id

    @property
    def kernel_socket_identity(self) -> str:
        return self._kernel_socket_identity

    @property
    def driver_evidence_nonce_sha256(self) -> str:
        return self._driver_evidence_nonce_sha256

    @property
    def send_kind(self) -> str:
        return self._send_kind

    @property
    def transport_sequence(self) -> int:
        return self._transport_sequence

    @property
    def ciphertext_batch_sha256(self) -> str:
        return self._ciphertext_batch_sha256

    @property
    def ciphertext_octets(self) -> int:
        return self._ciphertext_octets

    @property
    def ciphertext_start_octet(self) -> int:
        return self._ciphertext_start_octet

    @property
    def requested_octets(self) -> int:
        return self._requested_octets

    @property
    def exact_slice_sha256(self) -> str:
        return self._exact_slice_sha256

    @property
    def deadline_ns(self) -> int:
        return self._deadline_ns

    @property
    def would_block_count(self) -> int:
        return self._would_block_count

    @property
    def driver_evidence_id(self) -> str:
        return self._driver_evidence_id

    @property
    def owner_evidence_id(self) -> str:
        return self._owner_evidence_id

    def consume_for_actor_v49e(
        self,
        *,
        transport_session_id: str,
        driver_evidence_nonce_sha256: str,
        deadline_ns: int,
        ciphertext_batch_sha256: str,
        ciphertext_start_octet: int,
        requested_octets: int,
    ) -> LinuxSocketOwnerV4SendDeadlineExpiredNoKernelAcceptanceV49E:
        LinuxSocketOwnerV4._assert_send_deadline_no_kernel_acceptance_integrity_v49e(
            self
        )
        if (
            self.transport_session_id != transport_session_id
            or self.driver_evidence_nonce_sha256 != driver_evidence_nonce_sha256
            or self.deadline_ns != deadline_ns
            or self.ciphertext_batch_sha256 != ciphertext_batch_sha256
            or self.ciphertext_start_octet != ciphertext_start_octet
            or self.requested_octets != requested_octets
        ):
            raise LinuxSocketOwnerV4Error(
                "send-deadline evidence differs from actor authority"
            )
        _consume_owner_capability_v49e(
            capability_kind="SEND_DEADLINE_NO_KERNEL_ACCEPTANCE",
            capability_id=self.owner_evidence_id,
            capability=self,
        )
        _register_owner_capability_v49e(
            _token=_V49E_OWNER_CAPABILITY_REGISTRATION_TOKEN,
            capability_kind="TERMINAL_CLOCK_AUTHORIZATION_HANDOFF",
            capability_id=self.owner_evidence_id,
            capability=self,
        )
        return self


@dataclass(frozen=True, slots=True)
class BoundedCommandResultV4:
    returncode: int
    stdout: bytes
    stderr: bytes


def _boottime_ns() -> int:
    clock_id = getattr(time, "CLOCK_BOOTTIME", None)
    if clock_id is None or not hasattr(time, "clock_gettime_ns"):
        raise LinuxTransportEvidenceV4Error("Linux CLOCK_BOOTTIME is unavailable")
    try:
        value = time.clock_gettime_ns(clock_id)
    except OSError as exc:
        raise LinuxTransportEvidenceV4Error(
            "Linux CLOCK_BOOTTIME could not be sampled"
        ) from exc
    if type(value) is not int or value < 0:
        raise LinuxTransportEvidenceV4Error(
            "Linux CLOCK_BOOTTIME returned an invalid value"
        )
    return value


def _bounded_owner_deadline_v49e(deadline_ns: int) -> int:
    if type(deadline_ns) is not int or deadline_ns < 1:
        raise LinuxSocketOwnerV4Error(
            "V4.9E deadline must be an absolute CLOCK_BOOTTIME integer"
        )
    remaining_ns = deadline_ns - _boottime_ns()
    if remaining_ns <= 0:
        raise TimeoutError("V4.9E absolute CLOCK_BOOTTIME deadline elapsed")
    if remaining_ns > 300 * 10**9:
        raise LinuxSocketOwnerV4Error(
            "V4.9E absolute deadline exceeds the bounded operation window"
        )
    return deadline_ns


def _owner_deadline_expired_no_observation_v49e(
    *, owner: LinuxSocketOwnerV4, operation: str, deadline_ns: int
) -> LinuxSocketOwnerV4DeadlineExpiredNoObservationV49E:
    return owner._bind_deadline_expired_no_observation_v49e(
        operation=operation,
        deadline_ns=deadline_ns,
    )


def _require_owner_pre_mutation_deadline_v49e(
    *, owner: LinuxSocketOwnerV4, operation: str, deadline_ns: int
) -> int:
    try:
        return _bounded_owner_deadline_v49e(deadline_ns)
    except TimeoutError as exc:
        raise _owner_deadline_expired_no_observation_v49e(
            owner=owner,
            operation=operation,
            deadline_ns=deadline_ns,
        ) from exc


def _terminate_process(proc: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (OSError, ProcessLookupError):
        try:
            proc.kill()
        except OSError:
            pass
    try:
        proc.wait(timeout=1)
    except (OSError, subprocess.TimeoutExpired):
        pass


def run_bounded_command_v4(
    argv: tuple[str, ...],
    *,
    pass_fds: tuple[int, ...],
    timeout_milliseconds: int,
    maximum_output_bytes: int,
) -> BoundedCommandResultV4:
    """Run fixed argv with a BOOTTIME deadline and incremental output cap."""

    if (
        type(argv) is not tuple
        or not argv
        or any(type(item) is not str for item in argv)
    ):
        raise TypeError("argv must be a non-empty exact tuple of strings")
    timeout_ms = canonical_safe_int(
        timeout_milliseconds,
        field="timeout_milliseconds",
        minimum=1,
        maximum=30_000,
    )
    output_cap = canonical_safe_int(
        maximum_output_bytes,
        field="maximum_output_bytes",
        minimum=1,
        maximum=1_048_576,
    )
    deadline_ns = _boottime_ns() + timeout_ms * 1_000_000
    try:
        proc = subprocess.Popen(  # noqa: S603 - fixed reviewed argv, shell disabled
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            close_fds=True,
            pass_fds=pass_fds,
            env=_CHRONY_ENV,
            shell=False,
            start_new_session=True,
        )
    except OSError as exc:
        raise LinuxChronyEvidenceV4Error("chronyc process could not start") from exc
    if proc.stdout is None or proc.stderr is None:
        _terminate_process(proc)
        raise LinuxChronyEvidenceV4Error("chronyc pipes were not created")

    selector: selectors.BaseSelector | None = None
    buffers: dict[str, bytearray] = {"stdout": bytearray(), "stderr": bytearray()}
    try:
        selector = selectors.DefaultSelector()
        selector.register(proc.stdout, selectors.EVENT_READ, "stdout")
        selector.register(proc.stderr, selectors.EVENT_READ, "stderr")
        while selector.get_map():
            remaining_ns = deadline_ns - _boottime_ns()
            if remaining_ns <= 0:
                _terminate_process(proc)
                raise LinuxChronyEvidenceV4Error(
                    "chronyc exceeded its external deadline"
                )
            events = selector.select(min(remaining_ns / 1_000_000_000, 0.05))
            if not events:
                continue
            for key, _ in events:
                try:
                    chunk = os.read(key.fd, 8192)
                except OSError as exc:
                    _terminate_process(proc)
                    raise LinuxChronyEvidenceV4Error(
                        "chronyc output could not be read"
                    ) from exc
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                buffers[key.data].extend(chunk)
                if sum(len(value) for value in buffers.values()) > output_cap:
                    _terminate_process(proc)
                    raise LinuxChronyEvidenceV4Error(
                        "chronyc output exceeded its signed byte cap"
                    )
        remaining_ns = deadline_ns - _boottime_ns()
        if remaining_ns <= 0:
            _terminate_process(proc)
            raise LinuxChronyEvidenceV4Error("chronyc exceeded its external deadline")
        try:
            returncode = proc.wait(timeout=remaining_ns / 1_000_000_000)
        except subprocess.TimeoutExpired as exc:
            _terminate_process(proc)
            raise LinuxChronyEvidenceV4Error(
                "chronyc exceeded its external deadline"
            ) from exc
    except BaseException:
        _terminate_process(proc)
        raise
    finally:
        if selector is not None:
            selector.close()
        proc.stdout.close()
        proc.stderr.close()
    return BoundedCommandResultV4(
        returncode=returncode,
        stdout=bytes(buffers["stdout"]),
        stderr=bytes(buffers["stderr"]),
    )


@dataclass(frozen=True, slots=True)
class _NamespaceIdentityV4:
    device: int
    inode: int


class _PinnedThreadNamespaceV4:
    def __init__(self, *, kind: str, expected_type: int) -> None:
        self.kind = kind
        self.expected_type = expected_type
        self.path = f"/proc/thread-self/ns/{kind}"
        try:
            self.fd = os.open(self.path, os.O_RDONLY | os.O_CLOEXEC)
        except OSError as exc:
            raise LinuxNamespaceEvidenceV4Error(
                f"Linux {kind} namespace could not be pinned"
            ) from exc
        try:
            os.set_inheritable(self.fd, False)
            if os.get_inheritable(self.fd):
                raise LinuxNamespaceEvidenceV4Error(
                    f"Linux {kind} namespace descriptor remained inheritable"
                )
            self.identity = self._identity(self.fd)
            self.assert_current()
        except BaseException:
            os.close(self.fd)
            raise
        self.namespace_id = derive_linux_namespace_id(
            namespace_kind=kind,
            stat_device_u64=self.identity.device,
            stat_inode_u64=self.identity.inode,
        )
        self.closed = False

    def _identity(self, fd: int) -> _NamespaceIdentityV4:
        try:
            namespace_type = fcntl.ioctl(fd, _NS_GET_NSTYPE)
            info = os.fstat(fd)
        except OSError as exc:
            raise LinuxNamespaceEvidenceV4Error(
                f"Linux {self.kind} namespace identity is unavailable"
            ) from exc
        if namespace_type != self.expected_type:
            raise LinuxNamespaceEvidenceV4Error(
                f"Linux {self.kind} namespace has the wrong kernel type"
            )
        if info.st_dev < 0 or info.st_ino <= 0:
            raise LinuxNamespaceEvidenceV4Error(
                f"Linux {self.kind} namespace has an invalid device/inode pair"
            )
        return _NamespaceIdentityV4(device=info.st_dev, inode=info.st_ino)

    def assert_current(self) -> None:
        if getattr(self, "closed", False):
            raise LinuxNamespaceEvidenceV4Error(
                f"Linux {self.kind} namespace pin is closed"
            )
        try:
            if os.get_inheritable(self.fd):
                raise LinuxNamespaceEvidenceV4Error(
                    f"Linux {self.kind} namespace descriptor became inheritable"
                )
            retained = self._identity(self.fd)
            current_fd = os.open(self.path, os.O_RDONLY | os.O_CLOEXEC)
            try:
                current = self._identity(current_fd)
            finally:
                os.close(current_fd)
        except LinuxNamespaceEvidenceV4Error:
            raise
        except OSError as exc:
            raise LinuxNamespaceEvidenceV4Error(
                f"Linux {self.kind} namespace could not be revalidated"
            ) from exc
        if retained != self.identity or current != self.identity:
            raise LinuxNamespaceEvidenceV4Error(
                f"calling thread changed Linux {self.kind} namespace"
            )

    def close(self) -> None:
        if not self.closed:
            self.closed = True
            os.close(self.fd)


_FORK_SENSITIVE: weakref.WeakSet[Any] = weakref.WeakSet()
_V49E_OWNER_CAPABILITY_REGISTRATION_TOKEN: Final = object()
_V49E_OWNER_CAPABILITY_REGISTRY_MAXIMUM: Final = 4_096
_V49E_OWNER_CAPABILITY_REGISTRY_LOCK = threading.RLock()
_V49E_OWNER_CAPABILITY_REGISTRY: weakref.WeakValueDictionary[tuple[str, str], Any] = (
    weakref.WeakValueDictionary()
)
_V49E_OWNER_CAPABILITY_CONTEXT: dict[tuple[str, str], tuple[int, int]] = {}


def _register_owner_capability_v49e(
    *,
    _token: object,
    capability_kind: str,
    capability_id: str,
    capability: Any,
) -> None:
    """Retain bounded weak identity, never merely attacker-copyable fields."""

    if _token is not _V49E_OWNER_CAPABILITY_REGISTRATION_TOKEN:
        raise TypeError("owner capability registration is module-private")
    key = (capability_kind, capability_id)
    with _V49E_OWNER_CAPABILITY_REGISTRY_LOCK:
        for stale in tuple(_V49E_OWNER_CAPABILITY_CONTEXT):
            if stale not in _V49E_OWNER_CAPABILITY_REGISTRY:
                _V49E_OWNER_CAPABILITY_CONTEXT.pop(stale, None)
        if (
            type(capability_kind) is not str
            or not capability_kind
            or type(capability_id) is not str
            or re.fullmatch(r"[0-9a-f]{64}", capability_id) is None
            or key in _V49E_OWNER_CAPABILITY_REGISTRY
            or len(_V49E_OWNER_CAPABILITY_CONTEXT)
            >= _V49E_OWNER_CAPABILITY_REGISTRY_MAXIMUM
        ):
            raise LinuxSocketOwnerV4Error(
                "owner capability identity registry rejected registration"
            )
        try:
            _V49E_OWNER_CAPABILITY_REGISTRY[key] = capability
        except TypeError as exc:
            raise LinuxSocketOwnerV4Error(
                "owner capability must support bounded weak identity"
            ) from exc
        _V49E_OWNER_CAPABILITY_CONTEXT[key] = (
            os.getpid(),
            threading.get_ident(),
        )


def _consume_owner_capability_v49e(
    *, capability_kind: str, capability_id: str, capability: Any
) -> None:
    key = (capability_kind, capability_id)
    with _V49E_OWNER_CAPABILITY_REGISTRY_LOCK:
        retained = _V49E_OWNER_CAPABILITY_REGISTRY.get(key)
        context = _V49E_OWNER_CAPABILITY_CONTEXT.get(key)
        if retained is not capability or context != (
            os.getpid(),
            threading.get_ident(),
        ):
            raise LinuxSocketOwnerV4Error(
                "owner capability is copied, consumed, expired, or out of context"
            )
        _V49E_OWNER_CAPABILITY_REGISTRY.pop(key, None)
        _V49E_OWNER_CAPABILITY_CONTEXT.pop(key, None)


def _discard_owner_capability_v49e(
    *, capability_kind: str, capability_id: str, capability: Any
) -> None:
    key = (capability_kind, capability_id)
    with _V49E_OWNER_CAPABILITY_REGISTRY_LOCK:
        if _V49E_OWNER_CAPABILITY_REGISTRY.get(key) is capability:
            _V49E_OWNER_CAPABILITY_REGISTRY.pop(key, None)
            _V49E_OWNER_CAPABILITY_CONTEXT.pop(key, None)


def _discard_owner_capability_key_v49e(
    *, capability_kind: str, capability_id: str
) -> None:
    key = (capability_kind, capability_id)
    with _V49E_OWNER_CAPABILITY_REGISTRY_LOCK:
        _V49E_OWNER_CAPABILITY_REGISTRY.pop(key, None)
        _V49E_OWNER_CAPABILITY_CONTEXT.pop(key, None)


def _consume_owner_capability_pair_v49e(
    *,
    first_kind: str,
    second_kind: str,
    capability_id: str,
    first: Any,
    second: Any,
) -> None:
    first_key = (first_kind, capability_id)
    second_key = (second_kind, capability_id)
    expected_context = (os.getpid(), threading.get_ident())
    with _V49E_OWNER_CAPABILITY_REGISTRY_LOCK:
        if (
            _V49E_OWNER_CAPABILITY_REGISTRY.get(first_key) is not first
            or _V49E_OWNER_CAPABILITY_REGISTRY.get(second_key) is not second
            or _V49E_OWNER_CAPABILITY_CONTEXT.get(first_key) != expected_context
            or _V49E_OWNER_CAPABILITY_CONTEXT.get(second_key) != expected_context
        ):
            raise LinuxSocketOwnerV4Error(
                "owner capability pair is copied, consumed, expired, or out of context"
            )
        for key in (first_key, second_key):
            _V49E_OWNER_CAPABILITY_REGISTRY.pop(key, None)
            _V49E_OWNER_CAPABILITY_CONTEXT.pop(key, None)


def _invalidate_after_fork() -> None:
    global _V49E_OWNER_CAPABILITY_CONTEXT  # noqa: PLW0603
    global _V49E_OWNER_CAPABILITY_REGISTRY  # noqa: PLW0603
    global _V49E_OWNER_CAPABILITY_REGISTRY_LOCK  # noqa: PLW0603

    # Never acquire or reuse a lock/weakref callback graph inherited from a
    # vanished parent thread in the child.
    _V49E_OWNER_CAPABILITY_REGISTRY_LOCK = threading.RLock()
    _V49E_OWNER_CAPABILITY_REGISTRY = weakref.WeakValueDictionary()
    _V49E_OWNER_CAPABILITY_CONTEXT = {}
    for item in tuple(_FORK_SENSITIVE):
        try:
            item._invalidate_in_fork_child()  # noqa: SLF001
        except BaseException:
            pass


if hasattr(os, "register_at_fork"):
    os.register_at_fork(after_in_child=_invalidate_after_fork)


def _decimal(value: str, *, field: str, nonnegative: bool = False) -> Decimal:
    if not value or value != value.strip() or len(value) > 96:
        raise LinuxChronyEvidenceV4Error(f"chrony {field} is malformed")
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise LinuxChronyEvidenceV4Error(f"chrony {field} is malformed") from exc
    if not parsed.is_finite() or (nonnegative and parsed < 0):
        raise LinuxChronyEvidenceV4Error(f"chrony {field} is invalid")
    return parsed


def _integer(
    value: str, *, field: str, minimum: int = 0, maximum: int = (1 << 31) - 1
) -> int:
    if not value or not value.isascii() or not value.isdecimal():
        raise LinuxChronyEvidenceV4Error(f"chrony {field} is not an integer")
    parsed = int(value)
    if parsed < minimum or parsed > maximum:
        raise LinuxChronyEvidenceV4Error(f"chrony {field} is outside policy")
    return parsed


def _decode_ascii_lines(raw: bytes, *, context: str) -> tuple[str, ...]:
    if not raw or b"\x00" in raw or b"\r" in raw:
        raise LinuxChronyEvidenceV4Error(f"chrony {context} output is malformed")
    try:
        text = raw.decode("ascii", errors="strict")
    except UnicodeDecodeError as exc:
        raise LinuxChronyEvidenceV4Error(
            f"chrony {context} output is not strict ASCII"
        ) from exc
    if not text.endswith("\n"):
        raise LinuxChronyEvidenceV4Error(
            f"chrony {context} output is not newline terminated"
        )
    lines = tuple(text[:-1].split("\n"))
    if any(not line or len(line) > 4096 for line in lines):
        raise LinuxChronyEvidenceV4Error(
            f"chrony {context} contains a blank or oversized row"
        )
    return lines


@dataclass(frozen=True, slots=True)
class _ParsedChronyV4:
    reference_time_epoch: Decimal
    uncertainty_seconds: Decimal
    selectable_source_count: int
    selected_source_age_milliseconds: int
    tracking_bytes: bytes
    sources_bytes: bytes
    source_names: tuple[str, ...]


def parse_chronyc_tracking_sources_v4(
    raw: bytes,
    *,
    policy: ClockSourcePolicyManifestV4,
    wall_after_at: datetime,
    collection_width_ns: int,
    clock_resolution_ns: int,
) -> _ParsedChronyV4:
    """Parse the exact chronyc 4.8 ``-e -m`` tracking/sources profile."""

    if type(policy) is not ClockSourcePolicyManifestV4:
        raise TypeError("policy must be an exact ClockSourcePolicyManifestV4")
    if policy.chrony_version != "4.8":
        raise LinuxChronyEvidenceV4Error(
            "only the reviewed chronyc 4.8 CSV layout is accepted"
        )
    lines = _decode_ascii_lines(raw, context="combined CSV")
    sections: list[list[str]] = [[]]
    for line in lines:
        if line == ".":
            sections.append([])
        else:
            sections[-1].append(line)
    if len(sections) != 5 or sections[-1] or sections[0] or sections[1]:
        raise LinuxChronyEvidenceV4Error(
            "chronyc command-response boundaries differ from the reviewed profile"
        )
    tracking_lines = sections[2]
    source_lines = sections[3]
    if len(tracking_lines) != 1 or not 1 <= len(source_lines) <= _MAX_CHRONY_SOURCES:
        raise LinuxChronyEvidenceV4Error(
            "chronyc returned an invalid tracking/source row count"
        )

    tracking = tracking_lines[0].split(",")
    if len(tracking) != 14 or any('"' in item for item in tracking):
        raise LinuxChronyEvidenceV4Error(
            "chronyc tracking row differs from the reviewed 14-field layout"
        )
    reference_id, reference_name = tracking[0], tracking[1]
    if _REF_ID_RE.fullmatch(reference_id) is None or reference_id == "7F7F0101":
        raise LinuxChronyEvidenceV4Error(
            "chrony reference ID is invalid, local-mode, or unsynchronized"
        )
    if not reference_name or len(reference_name) > 255:
        raise LinuxChronyEvidenceV4Error("chrony reference source name is invalid")
    _integer(tracking[2], field="stratum", minimum=1, maximum=15)
    reference_time = _decimal(tracking[3], field="reference time", nonnegative=True)
    system_offset = _decimal(tracking[4], field="system offset")
    _decimal(tracking[5], field="last offset")
    _decimal(tracking[6], field="RMS offset", nonnegative=True)
    _decimal(tracking[7], field="frequency")
    _decimal(tracking[8], field="residual frequency")
    _decimal(tracking[9], field="skew", nonnegative=True)
    root_delay = _decimal(tracking[10], field="root delay", nonnegative=True)
    root_dispersion = _decimal(tracking[11], field="root dispersion", nonnegative=True)
    update_interval = _decimal(tracking[12], field="update interval", nonnegative=True)
    if update_interval == 0 or tracking[13] != "Normal":
        raise LinuxChronyEvidenceV4Error(
            "chrony is not in the required normal synchronized state"
        )

    selectable_count = 0
    selected_count = 0
    selected_name: str | None = None
    selected_age_ms = 0
    source_names: list[str] = []
    for line in source_lines:
        fields = line.split(",")
        if len(fields) != 10 or any('"' in item for item in fields):
            raise LinuxChronyEvidenceV4Error(
                "chronyc sources row differs from the reviewed 10-field layout"
            )
        mode, state, name = fields[0], fields[1], fields[2]
        if mode not in {"^", "=", "#"} or state not in {"*", "+", "-", "x", "~", "?"}:
            raise LinuxChronyEvidenceV4Error("chrony source mode/state is invalid")
        if not name or len(name) > 255:
            raise LinuxChronyEvidenceV4Error("chrony source name is invalid")
        if name in source_names:
            raise LinuxChronyEvidenceV4Error("chrony source names are duplicated")
        source_names.append(name)
        _integer(fields[3], field="source stratum", minimum=0, maximum=16)
        _integer(fields[4], field="source poll", minimum=0, maximum=31)
        if not re.fullmatch(r"[0-7]{1,3}", fields[5]):
            raise LinuxChronyEvidenceV4Error(
                "chrony source reachability register is invalid"
            )
        last_rx = _integer(
            fields[6], field="source last receive age", maximum=10 * 365 * 24 * 3600
        )
        _decimal(fields[7], field="source adjusted offset")
        _decimal(fields[8], field="source measured offset")
        _decimal(fields[9], field="source error", nonnegative=True)
        if state in {"*", "+", "-"}:
            selectable_count += 1
        if state in {"*", "+"}:
            if int(fields[5], 8) == 0:
                raise LinuxChronyEvidenceV4Error(
                    "selected/combined chrony source is unreachable"
                )
            source_age_ms = last_rx * 1_000
            if source_age_ms > policy.max_sample_age_milliseconds:
                raise LinuxChronyEvidenceV4Error(
                    "selected/combined chrony source is stale"
                )
            selected_age_ms = max(selected_age_ms, source_age_ms)
        if state == "*":
            selected_count += 1
            selected_name = name
    if selected_count != 1 or selected_name != reference_name:
        raise LinuxChronyEvidenceV4Error(
            "chrony tracking reference differs from its sole selected source"
        )
    if selectable_count < policy.min_selectable_sources:
        raise LinuxChronyEvidenceV4Error(
            "chrony has fewer selectable sources than signed policy requires"
        )

    wall_epoch = Decimal(str(wall_after_at.timestamp()))
    reference_age_seconds = wall_epoch - reference_time
    base_error = abs(system_offset) + root_dispersion + root_delay / Decimal(2)
    collection_seconds = Decimal(collection_width_ns) / Decimal(1_000_000_000)
    resolution_seconds = Decimal(clock_resolution_ns) / Decimal(1_000_000_000)
    uncertainty_seconds = base_error + collection_seconds + resolution_seconds
    if reference_age_seconds < -uncertainty_seconds:
        raise LinuxChronyEvidenceV4Error(
            "chrony reference time lies in the future beyond its error bound"
        )
    reference_age_ms = max(Decimal(0), reference_age_seconds * Decimal(1_000))
    if reference_age_ms > policy.max_sample_age_milliseconds:
        raise LinuxChronyEvidenceV4Error("chrony tracking reference is stale")
    uncertainty_ms = int(
        (uncertainty_seconds * Decimal(1_000)).to_integral_value(rounding=ROUND_CEILING)
    )
    if uncertainty_ms > policy.max_uncertainty_milliseconds:
        raise LinuxChronyEvidenceV4Error("chrony uncertainty exceeds signed policy")
    tracking_bytes = (tracking_lines[0] + "\n").encode("ascii")
    sources_bytes = ("\n".join(source_lines) + "\n").encode("ascii")
    return _ParsedChronyV4(
        reference_time_epoch=reference_time,
        uncertainty_seconds=uncertainty_seconds,
        selectable_source_count=selectable_count,
        selected_source_age_milliseconds=selected_age_ms,
        tracking_bytes=tracking_bytes,
        sources_bytes=sources_bytes,
        source_names=tuple(source_names),
    )


@dataclass(frozen=True, slots=True, kw_only=True)
class GovernedClockSampleV4:
    clock_source_manifest_id: str
    kernel_boot_id: str
    time_namespace_id: str
    monotonic_clock_domain_id: str
    wall_before_at: datetime
    wall_after_at: datetime
    boottime_before_ns: int
    boottime_after_ns: int
    clock_resolution_ns: int
    uncertainty_milliseconds: int
    selectable_source_count: int
    selected_source_age_milliseconds: int
    tracking_output_sha256: str
    sources_output_sha256: str
    observation_sha256: str
    valid_until: datetime
    chronyd_launch_id: str | None = None
    chronyd_runtime_observation_sha256: str | None = None

    def __post_init__(self) -> None:
        launch_values = (
            self.chronyd_launch_id,
            self.chronyd_runtime_observation_sha256,
        )
        if (launch_values[0] is None) != (launch_values[1] is None):
            raise LinuxChronyEvidenceV4Error(
                "chronyd launch and runtime-observation identities must be paired"
            )
        if launch_values[0] is not None:
            canonical_hash(launch_values[0], field="chronyd_launch_id")
            canonical_hash(launch_values[1], field="chronyd_runtime_observation_sha256")

    @property
    def monotonic_ns(self) -> int:
        return self.boottime_after_ns

    def as_clock_evidence(self) -> ClockEvidenceV4:
        return ClockEvidenceV4(
            clock_source_manifest_id=self.clock_source_manifest_id,
            monotonic_clock_domain_id=self.monotonic_clock_domain_id,
            sampled_at=self.wall_after_at,
            monotonic_ns=self.boottime_after_ns,
            uncertainty_milliseconds=self.uncertainty_milliseconds,
            synchronized=True,
            valid_until=self.valid_until,
            monotonic_before_ns=self.boottime_before_ns,
            monotonic_after_ns=self.boottime_after_ns,
            wall_before_at=self.wall_before_at,
            wall_after_at=self.wall_after_at,
            clock_resolution_ns=self.clock_resolution_ns,
            observation_sha256=self.observation_sha256,
            selectable_source_count=self.selectable_source_count,
            chronyd_launch_id=self.chronyd_launch_id,
            chronyd_runtime_observation_sha256=(
                self.chronyd_runtime_observation_sha256
            ),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class LinuxTransportManifestAuthorityObservationV49F:
    """Non-capability identity recaptured from one retained Linux owner."""

    transport_session_id: str
    driver_policy_id: str
    driver_runtime_observation_sha256: str
    driver_evidence_nonce_sha256: str
    kernel_socket_identity: str
    kernel_boot_id: str
    time_namespace_id: str
    network_namespace_id: str
    monotonic_clock_domain_id: str
    clock_source_manifest_id: str
    chronyd_launch_id: str | None
    chronyd_runtime_observation_sha256: str | None

    def __post_init__(self) -> None:
        for name in (
            "transport_session_id",
            "driver_policy_id",
            "driver_runtime_observation_sha256",
            "driver_evidence_nonce_sha256",
            "kernel_socket_identity",
            "time_namespace_id",
            "network_namespace_id",
            "monotonic_clock_domain_id",
            "clock_source_manifest_id",
        ):
            object.__setattr__(
                self,
                name,
                canonical_hash(getattr(self, name), field=name),
            )
        object.__setattr__(
            self,
            "kernel_boot_id",
            canonical_identifier(self.kernel_boot_id, field="kernel_boot_id"),
        )
        chronyd_values = (
            self.chronyd_launch_id,
            self.chronyd_runtime_observation_sha256,
        )
        if (chronyd_values[0] is None) != (chronyd_values[1] is None):
            raise CanonicalizationError(
                "chronyd launch and runtime-observation IDs must be paired"
            )
        if chronyd_values[0] is not None:
            object.__setattr__(
                self,
                "chronyd_launch_id",
                canonical_hash(chronyd_values[0], field="chronyd_launch_id"),
            )
            object.__setattr__(
                self,
                "chronyd_runtime_observation_sha256",
                canonical_hash(
                    chronyd_values[1],
                    field="chronyd_runtime_observation_sha256",
                ),
            )


CommandRunnerV4 = Callable[..., BoundedCommandResultV4]


class LinuxChronyClockV4:
    """Per-thread BOOTTIME clock disciplined by strict signed chrony policy."""

    def __init__(
        self,
        *,
        policy: ClockSourcePolicyManifestV4,
        configured_source_artifacts: tuple[ConfiguredChronySourceArtifactV4, ...],
        chronyd_authority: ChronydLaunchAuthorityV48B,
    ) -> None:
        if type(self) is not LinuxChronyClockV4:
            raise TypeError(
                "LinuxChronyClockV4 subclasses must use an explicit test harness"
            )
        self._initialize(
            policy=policy,
            configured_source_artifacts=configured_source_artifacts,
            command_runner=run_bounded_command_v4,
            wall_clock=None,
            live_profile=True,
            chronyd_authority=chronyd_authority,
        )

    def _initialize(
        self,
        *,
        policy: ClockSourcePolicyManifestV4,
        configured_source_artifacts: tuple[ConfiguredChronySourceArtifactV4, ...],
        command_runner: CommandRunnerV4,
        wall_clock: Callable[[], datetime] | None,
        live_profile: bool,
        chronyd_authority: ChronydLaunchAuthorityV48B | None,
    ) -> None:
        if sys.platform != "linux":
            raise LinuxTransportEvidenceV4Error(
                "the V4.8B transport clock is Linux-only"
            )
        if type(policy) is not ClockSourcePolicyManifestV4:
            raise TypeError("policy must be an exact ClockSourcePolicyManifestV4")
        if policy.chrony_version != "4.8":
            raise LinuxChronyEvidenceV4Error(
                "only the reviewed chronyc 4.8 backend is implemented"
            )
        if (
            derive_configured_chrony_source_set_root_v4(configured_source_artifacts)
            != policy.configured_source_set_root_sha256
        ):
            raise LinuxChronyEvidenceV4Error(
                "configured chrony source closure differs from signed policy"
            )
        self._policy = policy
        if type(live_profile) is not bool:
            raise TypeError("live_profile must be a boolean")
        self._live_profile = live_profile
        if live_profile:
            if (
                type(chronyd_authority) is not ChronydLaunchAuthorityV48B
                or not chronyd_authority.is_live_profile
                or chronyd_authority.policy != policy
            ):
                raise LinuxChronyEvidenceV4Error(
                    "live clock requires the exact signed loaded-chronyd authority"
                )
        elif chronyd_authority is not None:
            raise TypeError("deterministic clock cannot receive chronyd authority")
        self._chronyd_authority = chronyd_authority
        self._runner = command_runner
        self._wall_clock = wall_clock or (lambda: datetime.now(timezone.utc))
        self._creator_pid = os.getpid()
        self._creator_thread_id = threading.get_ident()
        self._fork_invalid = False
        self._closed = False
        self._last_boottime_after_ns: int | None = None
        self._time_namespace: _PinnedThreadNamespaceV4 | None = None
        self._boot_fd: int | None = None
        self._chronyc: PinnedRuntimeArtifactV4 | None = None
        self._config: PinnedRuntimeArtifactV4 | None = None
        self._sources: tuple[PinnedRuntimeArtifactV4, ...] = ()
        try:
            self._time_namespace = _PinnedThreadNamespaceV4(
                kind="time", expected_type=_CLONE_NEWTIME
            )
            self._boot_fd = os.open(
                "/proc/sys/kernel/random/boot_id", os.O_RDONLY | os.O_CLOEXEC
            )
            os.set_inheritable(self._boot_fd, False)
            self._chronyc = PinnedRuntimeArtifactV4.open_verified(
                RuntimeArtifactSpecV4(
                    path=policy.chronyc_executable_path,
                    sha256=policy.chronyc_executable_sha256,
                    require_executable=True,
                )
            )
            self._config = PinnedRuntimeArtifactV4.open_verified(
                RuntimeArtifactSpecV4(
                    path=policy.chrony_config_path,
                    sha256=policy.chrony_config_sha256,
                    max_bytes=1_048_576,
                )
            )
            sources: list[PinnedRuntimeArtifactV4] = []
            for source_artifact in configured_source_artifacts:
                source = PinnedRuntimeArtifactV4.open_verified(
                    source_artifact.runtime_spec()
                )
                sources.append(source)
                self._sources = tuple(sources)
            self._assert_context()
            self._assert_artifacts()
            self._verify_chronyc_version()
            if self._chronyd_authority is not None:
                assert self._chronyc is not None
                self._chronyd_authority.await_source_readiness(self._chronyc)
            _FORK_SENSITIVE.add(self)
        except BaseException:
            self.close()
            raise

    @property
    def policy(self) -> ClockSourcePolicyManifestV4:
        return self._policy

    @property
    def is_live_profile(self) -> bool:
        """Whether construction used the sealed real runner and wall clock."""

        return (
            self._live_profile
            and type(self) is LinuxChronyClockV4
            and type(self._chronyd_authority) is ChronydLaunchAuthorityV48B
            and self._chronyd_authority.is_live_profile
        )

    @property
    def chronyd_launch_id(self) -> str | None:
        self._assert_context()
        if self._chronyd_authority is None:
            return None
        return self._chronyd_authority.launch_id

    @property
    def chronyd_runtime_observation_sha256(self) -> str | None:
        self._assert_context()
        if self._chronyd_authority is None:
            return None
        return self._chronyd_authority.runtime_observation_sha256

    @property
    def kernel_boot_id(self) -> str:
        self._assert_context()
        return self._read_boot_id()

    @property
    def time_namespace_id(self) -> str:
        self._assert_context()
        assert self._time_namespace is not None
        return self._time_namespace.namespace_id

    @property
    def monotonic_clock_domain_id(self) -> str:
        return derive_linux_boottime_clock_domain_id(
            kernel_boot_id=self.kernel_boot_id,
            time_namespace_id=self.time_namespace_id,
        )

    @property
    def clock_resolution_ns(self) -> int:
        clock_id = getattr(time, "CLOCK_BOOTTIME", None)
        if clock_id is None:
            raise LinuxTransportEvidenceV4Error("CLOCK_BOOTTIME is unavailable")
        resolution = time.clock_getres(clock_id)
        if not math.isfinite(resolution) or resolution <= 0:
            raise LinuxTransportEvidenceV4Error("CLOCK_BOOTTIME resolution is invalid")
        return max(1, math.ceil(resolution * 1_000_000_000))

    def _assert_context(self) -> None:
        if (
            self._closed
            or self._fork_invalid
            or os.getpid() != self._creator_pid
            or threading.get_ident() != self._creator_thread_id
        ):
            raise LinuxTransportEvidenceV4Error(
                "clock authority left its creating process/thread"
            )
        if self._time_namespace is None or self._boot_fd is None:
            raise LinuxTransportEvidenceV4Error("clock authority is incomplete")
        self._time_namespace.assert_current()
        if self._chronyd_authority is not None:
            self._chronyd_authority.assert_instance_current()
        if os.get_inheritable(self._boot_fd):
            raise LinuxTransportEvidenceV4Error("boot-ID descriptor became inheritable")

    def _read_boot_id(self) -> str:
        if self._boot_fd is None:
            raise LinuxTransportEvidenceV4Error("boot-ID descriptor is closed")
        try:
            raw = os.pread(self._boot_fd, 64, 0)
        except OSError as exc:
            raise LinuxTransportEvidenceV4Error(
                "kernel boot ID is unavailable"
            ) from exc
        if _BOOT_ID_RE.fullmatch(raw) is None:
            raise LinuxTransportEvidenceV4Error("kernel boot ID is malformed")
        return raw.rstrip(b"\n").decode("ascii")

    def _assert_artifacts(self) -> None:
        if self._chronyc is None or self._config is None:
            raise LinuxChronyEvidenceV4Error("chrony artifacts are closed")
        try:
            self._chronyc.assert_unchanged()
            self._config.assert_unchanged()
            for item in self._sources:
                item.assert_unchanged()
            if self._chronyd_authority is not None:
                self._chronyd_authority.assert_provenance_current()
        except OperationalArtifactV4Error as exc:
            raise LinuxChronyEvidenceV4Error(
                "a signed chrony runtime artifact changed"
            ) from exc

    def _run(self, argv: tuple[str, ...]) -> BoundedCommandResultV4:
        if self._chronyc is None:
            raise LinuxChronyEvidenceV4Error("chronyc artifact is closed")
        result = self._runner(
            argv,
            pass_fds=(self._chronyc.descriptor,),
            timeout_milliseconds=self._policy.chronyc_command_timeout_milliseconds,
            maximum_output_bytes=self._policy.chronyc_max_output_bytes,
        )
        if type(result) is not BoundedCommandResultV4:
            raise LinuxChronyEvidenceV4Error(
                "chronyc runner returned an unsupported result"
            )
        if (
            type(result.returncode) is not int
            or type(result.stdout) is not bytes
            or type(result.stderr) is not bytes
            or len(result.stdout) + len(result.stderr)
            > self._policy.chronyc_max_output_bytes
        ):
            raise LinuxChronyEvidenceV4Error(
                "chronyc runner returned malformed or oversized output"
            )
        if result.returncode != 0 or result.stderr:
            raise LinuxChronyEvidenceV4Error(
                "chronyc failed or emitted unexpected standard error"
            )
        return result

    def _verify_chronyc_version(self) -> None:
        assert self._chronyc is not None
        result = self._run((self._chronyc.proc_fd_path, "--version"))
        match = _VERSION_RE.fullmatch(result.stdout)
        if (
            match is None
            or match.group(1).decode("ascii") != self._policy.chrony_version
        ):
            raise LinuxChronyEvidenceV4Error(
                "chronyc version differs from signed reviewed policy"
            )

    def sample_governed(self) -> GovernedClockSampleV4:
        self._assert_context()
        self._assert_artifacts()
        assert self._chronyc is not None
        boot_before = self._read_boot_id()
        boottime_before_ns = _boottime_ns()
        wall_before_at = utc_datetime(self._wall_clock(), field="clock_wall_before_at")
        authenticated_query = None
        if self._chronyd_authority is not None:
            authenticated_query = self._chronyd_authority.query_chronyc(self._chronyc)
            raw_output = authenticated_query.stdout
        else:
            result = self._run(
                (
                    self._chronyc.proc_fd_path,
                    "-n",
                    "-c",
                    "-e",
                    "-h",
                    self._policy.chronyc_command_socket_path,
                    "-m",
                    (
                        "timeout "
                        f"{max(100, self._policy.chronyc_command_timeout_milliseconds // 2)}"
                    ),
                    "retries 0",
                    "tracking",
                    "sources -a",
                )
            )
            raw_output = result.stdout
        wall_after_at = utc_datetime(self._wall_clock(), field="clock_wall_after_at")
        boottime_after_ns = _boottime_ns()
        self._assert_context()
        boot_after = self._read_boot_id()
        self._assert_artifacts()
        if boot_before != boot_after:
            raise LinuxTransportEvidenceV4Error(
                "kernel boot ID changed during clock evidence collection"
            )
        if boottime_after_ns <= boottime_before_ns or (
            self._last_boottime_after_ns is not None
            and boottime_before_ns <= self._last_boottime_after_ns
        ):
            raise LinuxTransportEvidenceV4Error(
                "CLOCK_BOOTTIME evidence bracket overlaps or regresses"
            )
        if wall_after_at < wall_before_at:
            raise LinuxChronyEvidenceV4Error(
                "realtime clock rolled backward during chrony collection"
            )
        width_ns = boottime_after_ns - boottime_before_ns
        wall_width_ns = int(
            (wall_after_at - wall_before_at).total_seconds() * 1_000_000_000
        )
        if abs(width_ns - wall_width_ns) > (
            self._policy.max_uncertainty_milliseconds * 1_000_000
        ):
            raise LinuxChronyEvidenceV4Error(
                "realtime and BOOTTIME collection widths disagree beyond policy"
            )
        resolution_ns = self.clock_resolution_ns
        parsed = parse_chronyc_tracking_sources_v4(
            raw_output,
            policy=self._policy,
            wall_after_at=wall_after_at,
            collection_width_ns=width_ns,
            clock_resolution_ns=resolution_ns,
        )
        if authenticated_query is not None and tuple(sorted(parsed.source_names)) != (
            authenticated_query.configured_endpoints
        ):
            raise LinuxChronyEvidenceV4Error(
                "chronyd runtime sources differ from sealed literal endpoints"
            )
        uncertainty_ms = int(
            (parsed.uncertainty_seconds * Decimal(1_000)).to_integral_value(
                rounding=ROUND_CEILING
            )
        )
        reference_age_ms = max(
            0,
            math.ceil(
                (Decimal(str(wall_after_at.timestamp())) - parsed.reference_time_epoch)
                * Decimal(1_000)
            ),
        )
        remaining_age_ms = max(
            0, self._policy.max_sample_age_milliseconds - reference_age_ms
        )
        validity_ms = min(_MAX_CLOCK_EVIDENCE_LIFETIME_MILLISECONDS, remaining_age_ms)
        self._last_boottime_after_ns = boottime_after_ns
        return GovernedClockSampleV4(
            clock_source_manifest_id=self._policy.manifest_id,
            kernel_boot_id=boot_after,
            time_namespace_id=self.time_namespace_id,
            monotonic_clock_domain_id=derive_linux_boottime_clock_domain_id(
                kernel_boot_id=boot_after,
                time_namespace_id=self.time_namespace_id,
            ),
            wall_before_at=wall_before_at,
            wall_after_at=wall_after_at,
            boottime_before_ns=boottime_before_ns,
            boottime_after_ns=boottime_after_ns,
            clock_resolution_ns=resolution_ns,
            uncertainty_milliseconds=uncertainty_ms,
            selectable_source_count=parsed.selectable_source_count,
            selected_source_age_milliseconds=(parsed.selected_source_age_milliseconds),
            tracking_output_sha256=hashlib.sha256(parsed.tracking_bytes).hexdigest(),
            sources_output_sha256=hashlib.sha256(parsed.sources_bytes).hexdigest(),
            observation_sha256=(
                authenticated_query.query_observation_sha256
                if authenticated_query is not None
                else hashlib.sha256(raw_output).hexdigest()
            ),
            valid_until=wall_after_at + timedelta(milliseconds=validity_ms),
            chronyd_launch_id=(
                authenticated_query.launch_id
                if authenticated_query is not None
                else None
            ),
            chronyd_runtime_observation_sha256=(
                authenticated_query.runtime_observation_sha256
                if authenticated_query is not None
                else None
            ),
        )

    def sample(self) -> ClockEvidenceV4:
        return self.sample_governed().as_clock_evidence()

    def monotonic_now_ns(self) -> int:
        """Read the bound BOOTTIME domain without collecting new wall evidence."""

        self._assert_context()
        if self._chronyd_authority is not None:
            self._chronyd_authority.assert_instance_current()
        value = _boottime_ns()
        if self._chronyd_authority is not None:
            self._chronyd_authority.assert_instance_current()
        return value

    def _invalidate_in_fork_child(self) -> None:
        self._fork_invalid = True
        self.close()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        _FORK_SENSITIVE.discard(self)
        for item in self._sources:
            try:
                item.close()
            except OSError:
                pass
        self._sources = ()
        for name in ("_config", "_chronyc"):
            item = getattr(self, name)
            if item is not None:
                try:
                    item.close()
                except OSError:
                    pass
                setattr(self, name, None)
        if self._boot_fd is not None:
            try:
                os.close(self._boot_fd)
            except OSError:
                pass
            self._boot_fd = None
        if self._time_namespace is not None:
            try:
                self._time_namespace.close()
            except OSError:
                pass
            self._time_namespace = None
        if self._chronyd_authority is not None:
            try:
                self._chronyd_authority.close()
            except OSError:
                pass
            self._chronyd_authority = None


class DeterministicLinuxChronyClockV4(LinuxChronyClockV4):
    """Explicit non-promotion harness for deterministic Linux adapter tests.

    It retains the real namespace, boot-ID, artifact, parser, and lifecycle
    behavior while replacing only process execution and wall time. The sealed
    runtime factory never accepts or constructs this type.
    """

    def __init__(
        self,
        *,
        policy: ClockSourcePolicyManifestV4,
        configured_source_artifacts: tuple[ConfiguredChronySourceArtifactV4, ...],
        command_runner: CommandRunnerV4,
        wall_clock: Callable[[], datetime],
    ) -> None:
        if not callable(command_runner) or not callable(wall_clock):
            raise TypeError("deterministic clock seams must be callable")
        self._initialize(
            policy=policy,
            configured_source_artifacts=configured_source_artifacts,
            command_runner=command_runner,
            wall_clock=wall_clock,
            live_profile=False,
            chronyd_authority=None,
        )


@runtime_checkable
class BoundLinuxSocketDriverV4(Protocol):
    """Pinned TLS/Sans-I/O driver that is always handed the retained socket."""

    async def send_exact_text_frame(
        self, owned_socket: socket.socket, payload: bytes
    ) -> None: ...

    async def submit_permitted_chunks(
        self,
        owned_socket: socket.socket,
        *,
        permit: Any,
        ordered_chunks: tuple[bytes, ...],
    ) -> int: ...


@dataclass(frozen=True, slots=True, kw_only=True, init=False)
class DriverHandshakeTransitionV49B:
    """Owner-created causal bracket around one exact driver handshake.

    Construction is restricted to this module.  The transition retains the
    exact (not copied or reconstructed) driver evidence and both owner
    snapshots so the commit path can prove that no socket, namespace, clock,
    chronyd, or measured-driver authority changed around the network action.
    """

    _evidence: DriverHandshakeEvidenceV49
    _pre_sample: GovernedClockSampleV4
    _post_sample: GovernedClockSampleV4
    _owner_snapshot: TransportSocketOwnerSnapshotV4
    _owner_snapshot_after: TransportSocketOwnerSnapshotV4
    _handshake_started_monotonic_ns: int
    _handshake_completed_monotonic_ns: int
    _driver_policy_id: str
    _runtime_observation_sha256: str

    def __init__(
        self,
        *,
        _token: object,
        evidence: DriverHandshakeEvidenceV49,
        pre_sample: GovernedClockSampleV4,
        post_sample: GovernedClockSampleV4,
        owner_snapshot: TransportSocketOwnerSnapshotV4,
        owner_snapshot_after: TransportSocketOwnerSnapshotV4,
        handshake_started_monotonic_ns: int,
        handshake_completed_monotonic_ns: int,
        driver_policy_id: str,
        runtime_observation_sha256: str,
    ) -> None:
        if _token is not _V49B_TRANSITION_TOKEN:
            raise TypeError("driver handshake transition is owner-constructed only")
        if type(evidence) is not DriverHandshakeEvidenceV49:
            raise TypeError("evidence must be exact DriverHandshakeEvidenceV49")
        if (
            type(pre_sample) is not GovernedClockSampleV4
            or type(post_sample) is not GovernedClockSampleV4
        ):
            raise TypeError("handshake clock samples must be exact governed samples")
        if (
            type(owner_snapshot) is not TransportSocketOwnerSnapshotV4
            or type(owner_snapshot_after) is not TransportSocketOwnerSnapshotV4
        ):
            raise TypeError("handshake owner snapshots must be exact snapshots")
        started = canonical_safe_int(
            handshake_started_monotonic_ns,
            field="handshake_started_monotonic_ns",
            minimum=0,
        )
        completed = canonical_safe_int(
            handshake_completed_monotonic_ns,
            field="handshake_completed_monotonic_ns",
            minimum=0,
        )
        policy_id = canonical_hash(driver_policy_id, field="driver_policy_id")
        observation = canonical_hash(
            runtime_observation_sha256,
            field="runtime_observation_sha256",
        )
        if owner_snapshot_after != owner_snapshot:
            raise LinuxSocketOwnerV4Error(
                "socket-owner snapshot changed across driver handshake"
            )
        if not (
            pre_sample.boottime_after_ns
            < started
            < completed
            < post_sample.boottime_before_ns
        ):
            raise LinuxSocketOwnerV4Error(
                "governed BOOTTIME samples do not strictly contain handshake"
            )
        if post_sample.wall_before_at <= pre_sample.wall_after_at:
            raise LinuxSocketOwnerV4Error(
                "governed wall-time bracket does not contain a positive handshake interval"
            )
        for sample in (pre_sample, post_sample):
            if (
                sample.kernel_boot_id != owner_snapshot.kernel_boot_id
                or sample.time_namespace_id != owner_snapshot.time_namespace_id
                or sample.monotonic_clock_domain_id
                != owner_snapshot.monotonic_clock_domain_id
                or sample.clock_resolution_ns != owner_snapshot.clock_resolution_ns
                or sample.chronyd_launch_id != owner_snapshot.chronyd_launch_id
                or sample.chronyd_runtime_observation_sha256
                != owner_snapshot.chronyd_runtime_observation_sha256
            ):
                raise LinuxSocketOwnerV4Error(
                    "handshake sample differs from retained owner clock provenance"
                )
        if (
            post_sample.clock_source_manifest_id != pre_sample.clock_source_manifest_id
            or post_sample.chronyd_launch_id != pre_sample.chronyd_launch_id
            or post_sample.chronyd_runtime_observation_sha256
            != pre_sample.chronyd_runtime_observation_sha256
        ):
            raise LinuxSocketOwnerV4Error(
                "clock or chronyd provenance changed across driver handshake"
            )
        object.__setattr__(self, "_evidence", evidence)
        object.__setattr__(self, "_pre_sample", pre_sample)
        object.__setattr__(self, "_post_sample", post_sample)
        object.__setattr__(self, "_owner_snapshot", owner_snapshot)
        object.__setattr__(self, "_owner_snapshot_after", owner_snapshot_after)
        object.__setattr__(self, "_handshake_started_monotonic_ns", started)
        object.__setattr__(self, "_handshake_completed_monotonic_ns", completed)
        object.__setattr__(self, "_driver_policy_id", policy_id)
        object.__setattr__(self, "_runtime_observation_sha256", observation)

    @property
    def evidence(self) -> DriverHandshakeEvidenceV49:
        return self._evidence

    @property
    def pre_sample(self) -> GovernedClockSampleV4:
        return self._pre_sample

    @property
    def post_sample(self) -> GovernedClockSampleV4:
        return self._post_sample

    @property
    def owner_snapshot(self) -> TransportSocketOwnerSnapshotV4:
        return self._owner_snapshot

    @property
    def owner_snapshot_after(self) -> TransportSocketOwnerSnapshotV4:
        return self._owner_snapshot_after

    @property
    def handshake_started_at(self) -> datetime:
        return self._pre_sample.wall_after_at

    @property
    def handshake_completed_at(self) -> datetime:
        return self._post_sample.wall_before_at

    @property
    def handshake_started_monotonic_ns(self) -> int:
        return self._handshake_started_monotonic_ns

    @property
    def handshake_completed_monotonic_ns(self) -> int:
        return self._handshake_completed_monotonic_ns

    @property
    def clock_uncertainty_milliseconds(self) -> int:
        return max(
            self._pre_sample.uncertainty_milliseconds,
            self._post_sample.uncertainty_milliseconds,
        )

    @property
    def driver_policy_id(self) -> str:
        return self._driver_policy_id

    @property
    def runtime_observation_sha256(self) -> str:
        return self._runtime_observation_sha256


@dataclass(frozen=True, slots=True, weakref_slot=True, kw_only=True, init=False)
class TcpWriteShutdownTokenV49E:
    """Owner-minted, identity-bound capability for exactly one ``SHUT_WR``."""

    token_sequence: int
    transport_session_id: str
    tls_control_sequence: int
    tls_ciphertext_batch_sha256: str
    tls_ciphertext_octets: int
    shutdown_deadline_monotonic_ns: int
    shutdown_token_id: str

    def __init__(self, *, _token: object, **values: Any) -> None:
        if _token is not _V49E_TCP_WRITE_SHUTDOWN_TOKEN:
            raise TypeError("TCP write-shutdown tokens are owner-constructed only")
        for name in self.__dataclass_fields__:
            object.__setattr__(self, name, values[name])

    def consume_for_actor_v49e(
        self,
        *,
        transport_session_id: str,
        tls_control_sequence: int,
        tls_ciphertext_batch_sha256: str,
        tls_ciphertext_octets: int,
        shutdown_deadline_monotonic_ns: int,
    ) -> TcpWriteShutdownTokenV49E:
        """Admit this exact owner object once to the terminal actor."""

        LinuxSocketOwnerV4._assert_tcp_write_shutdown_token_integrity_v49e(self)
        if (
            self.transport_session_id != transport_session_id
            or self.tls_control_sequence != tls_control_sequence
            or self.tls_ciphertext_batch_sha256 != tls_ciphertext_batch_sha256
            or self.tls_ciphertext_octets != tls_ciphertext_octets
            or self.shutdown_deadline_monotonic_ns != shutdown_deadline_monotonic_ns
        ):
            raise LinuxSocketOwnerV4Error(
                "TCP write-shutdown token differs from actor authority"
            )
        _consume_owner_capability_v49e(
            capability_kind="TCP_WRITE_SHUTDOWN_TOKEN",
            capability_id=self.shutdown_token_id,
            capability=self,
        )
        return self


# ``Permit`` is a semantic alias: possession grants only one owner-local
# syscall, never evidence of peer receipt or completed TCP termination.
TcpWriteShutdownPermitV49E = TcpWriteShutdownTokenV49E


class TcpWriteShutdownErrorCodeV49E(str, Enum):
    """Closed Linux ``shutdown(2)`` error vocabulary admitted by V4.9E."""

    DEADLINE_EXPIRED_BEFORE_SYSCALL = "DEADLINE_EXPIRED_BEFORE_SYSCALL"
    BAD_FILE_DESCRIPTOR = "EBADF"
    INVALID_SHUTDOWN_MODE = "EINVAL"
    NOT_CONNECTED = "ENOTCONN"
    NOT_A_SOCKET = "ENOTSOCK"


@dataclass(frozen=True, slots=True, weakref_slot=True, kw_only=True, init=False)
class TcpWriteShutdownResultV49E:
    """Sealed conclusive result of one exact local ``shutdown(SHUT_WR)``."""

    shutdown_token: TcpWriteShutdownTokenV49E
    shutdown_how: int
    kernel_accepted: bool
    error_code: TcpWriteShutdownErrorCodeV49E | None
    shutdown_result_id: str

    def __init__(self, *, _token: object, **values: Any) -> None:
        if _token is not _V49E_TCP_WRITE_SHUTDOWN_RESULT_TOKEN:
            raise TypeError("TCP write-shutdown results are owner-constructed only")
        for name in self.__dataclass_fields__:
            object.__setattr__(self, name, values[name])

    def consume_for_actor_v49e(
        self,
        *,
        transport_session_id: str,
        shutdown_token: TcpWriteShutdownTokenV49E,
    ) -> TcpWriteShutdownResultV49E:
        """Admit one exact conclusive owner syscall result to the actor."""

        LinuxSocketOwnerV4._assert_tcp_write_shutdown_result_integrity_v49e(self)
        if (
            self.shutdown_token is not shutdown_token
            or shutdown_token.transport_session_id != transport_session_id
        ):
            raise LinuxSocketOwnerV4Error(
                "TCP write-shutdown result differs from actor authority"
            )
        _consume_owner_capability_v49e(
            capability_kind="TCP_WRITE_SHUTDOWN_RESULT",
            capability_id=self.shutdown_result_id,
            capability=self,
        )
        _register_owner_capability_v49e(
            _token=_V49E_OWNER_CAPABILITY_REGISTRATION_TOKEN,
            capability_kind="TERMINAL_CLOCK_AUTHORIZATION_HANDOFF",
            capability_id=self.shutdown_result_id,
            capability=self,
        )
        return self


@dataclass(frozen=True, slots=True, weakref_slot=True, kw_only=True, init=False)
class OwnerTlsShutdownObservationV49E:
    """Owner-sealed shutdown fact bound to one session and kernel socket.

    The nested driver observation preserves the exact authenticated TLS or
    raw-EOF distinction.  ``owner_observation_id`` is a separate identity that
    additionally commits the retained transport session and Linux socket.
    """

    transport_session_id: str
    kernel_socket_identity: str
    driver_observation: TlsShutdownObservationV49E
    owner_observation_id: str

    def __init__(self, *, _token: object, **values: Any) -> None:
        if _token is not _V49E_OWNER_TLS_SHUTDOWN_OBSERVATION_TOKEN:
            raise TypeError("TLS shutdown observations are owner-constructed only")
        for name in self.__dataclass_fields__:
            object.__setattr__(self, name, values[name])

    @property
    def observation_sequence(self) -> int:
        return self.driver_observation.observation_sequence

    @property
    def observation_kind(self) -> TlsShutdownObservationKindV49E:
        return self.driver_observation.observation_kind

    @property
    def driver_evidence_nonce_sha256(self) -> str:
        return self.driver_observation.driver_evidence_nonce_sha256

    @property
    def peer_close_notify_received(self) -> bool:
        return self.driver_observation.peer_close_notify_received

    @property
    def tcp_eof_received(self) -> bool:
        return self.driver_observation.tcp_eof_received

    @property
    def truncated(self) -> bool:
        return self.driver_observation.truncated

    @property
    def ciphertext_octets_received(self) -> int:
        return self.driver_observation.ciphertext_octets_received

    @property
    def observation_id(self) -> str:
        return self.driver_observation.observation_id

    def consume_for_actor_v49e(
        self,
        *,
        transport_session_id: str,
        driver_evidence_nonce_sha256: str,
    ) -> OwnerTlsShutdownObservationV49E:
        """Admit this exact owner observation once to the terminal actor."""

        LinuxSocketOwnerV4._assert_owner_tls_shutdown_observation_integrity_v49e(self)
        if (
            self.transport_session_id != transport_session_id
            or self.driver_evidence_nonce_sha256 != driver_evidence_nonce_sha256
        ):
            raise LinuxSocketOwnerV4Error(
                "TLS shutdown observation differs from actor authority"
            )
        _consume_owner_capability_v49e(
            capability_kind="TLS_SHUTDOWN_OBSERVATION",
            capability_id=self.owner_observation_id,
            capability=self,
        )
        _register_owner_capability_v49e(
            _token=_V49E_OWNER_CAPABILITY_REGISTRATION_TOKEN,
            capability_kind="TERMINAL_CLOCK_AUTHORIZATION_HANDOFF",
            capability_id=self.owner_observation_id,
            capability=self,
        )
        return self


@dataclass(frozen=True, slots=True, weakref_slot=True, kw_only=True, init=False)
class OwnerUnsendableTlsPostHandshakeOutputV49E:
    """Negative post-SHUT_WR TLS fact bound to one session and socket."""

    transport_session_id: str
    kernel_socket_identity: str
    driver_evidence: UnsendableTlsPostHandshakeOutputV49E
    owner_unsendable_output_id: str

    def __init__(self, *, _token: object, **values: Any) -> None:
        if _token is not _V49E_OWNER_UNSENDABLE_TLS_OUTPUT_TOKEN:
            raise TypeError(
                "owner unsendable TLS-output evidence is owner-constructed only"
            )
        for name in self.__dataclass_fields__:
            object.__setattr__(self, name, values[name])

    @property
    def driver_evidence_nonce_sha256(self) -> str:
        return self.driver_evidence.driver_evidence_nonce_sha256

    @property
    def ciphertext_sha256(self) -> str:
        return self.driver_evidence.ciphertext_sha256

    @property
    def ciphertext_octets(self) -> int:
        return self.driver_evidence.ciphertext_octets

    def consume_for_actor_v49e(
        self,
        *,
        transport_session_id: str,
        driver_evidence_nonce_sha256: str,
    ) -> OwnerUnsendableTlsPostHandshakeOutputV49E:
        """Admit direct negative evidence once when no exception seam is used."""

        LinuxSocketOwnerV4._assert_owner_unsendable_tls_output_integrity_v49e(self)
        if (
            self.transport_session_id != transport_session_id
            or self.driver_evidence_nonce_sha256 != driver_evidence_nonce_sha256
        ):
            raise LinuxSocketOwnerV4Error(
                "unsendable TLS output differs from actor authority"
            )
        _consume_owner_capability_v49e(
            capability_kind="UNSENDABLE_TLS_OUTPUT_EVIDENCE",
            capability_id=self.owner_unsendable_output_id,
            capability=self,
        )
        _register_owner_capability_v49e(
            _token=_V49E_OWNER_CAPABILITY_REGISTRATION_TOKEN,
            capability_kind="TERMINAL_CLOCK_AUTHORIZATION_HANDOFF",
            capability_id=self.owner_unsendable_output_id,
            capability=self,
        )
        _discard_owner_capability_key_v49e(
            capability_kind="UNSENDABLE_TLS_OUTPUT_EXCEPTION",
            capability_id=self.owner_unsendable_output_id,
        )
        return self


class LinuxSocketOwnerV4UnsendablePostHandshakeOutput(LinuxSocketOwnerV4Error):
    """Exact owner-bound negative output capability; no write is permitted."""

    evidence: OwnerUnsendableTlsPostHandshakeOutputV49E

    def __init__(
        self,
        *,
        _token: object,
        evidence: OwnerUnsendableTlsPostHandshakeOutputV49E,
    ) -> None:
        if _token is not _V49E_OWNER_UNSENDABLE_TLS_OUTPUT_EXCEPTION_TOKEN:
            raise TypeError(
                "owner unsendable TLS-output exceptions are owner-constructed only"
            )
        if type(evidence) is not OwnerUnsendableTlsPostHandshakeOutputV49E:
            raise TypeError(
                "evidence must be exact OwnerUnsendableTlsPostHandshakeOutputV49E"
            )
        self.evidence = evidence
        super().__init__(
            "post-SHUT_WR TLS output is unsendable under retained owner authority"
        )
        _register_owner_capability_v49e(
            _token=_V49E_OWNER_CAPABILITY_REGISTRATION_TOKEN,
            capability_kind="UNSENDABLE_TLS_OUTPUT_EXCEPTION",
            capability_id=evidence.owner_unsendable_output_id,
            capability=self,
        )

    def consume_for_actor_v49e(
        self,
        *,
        transport_session_id: str,
        driver_evidence_nonce_sha256: str,
    ) -> OwnerUnsendableTlsPostHandshakeOutputV49E:
        """Consume the exact exception/evidence pair once after owner abort."""

        evidence = self.evidence
        LinuxSocketOwnerV4._assert_owner_unsendable_tls_output_integrity_v49e(evidence)
        if (
            evidence.transport_session_id != transport_session_id
            or evidence.driver_evidence_nonce_sha256 != driver_evidence_nonce_sha256
        ):
            raise LinuxSocketOwnerV4Error(
                "unsendable TLS-output exception differs from actor authority"
            )
        _consume_owner_capability_pair_v49e(
            first_kind="UNSENDABLE_TLS_OUTPUT_EXCEPTION",
            second_kind="UNSENDABLE_TLS_OUTPUT_EVIDENCE",
            capability_id=evidence.owner_unsendable_output_id,
            first=self,
            second=evidence,
        )
        _register_owner_capability_v49e(
            _token=_V49E_OWNER_CAPABILITY_REGISTRATION_TOKEN,
            capability_kind="TERMINAL_CLOCK_AUTHORIZATION_HANDOFF",
            capability_id=evidence.owner_unsendable_output_id,
            capability=evidence,
        )
        return evidence


@dataclass(frozen=True, slots=True, kw_only=True)
class LinuxSocketTransportFlowSnapshotV49F:
    """Count-only driver and Linux socket observation under one owner lock.

    Kernel queue values may change immediately after observation.  This value
    retains neither a socket nor any transport/parser capability and doesn't
    claim peer receipt, storage durability, or a simultaneous kernel sample.
    """

    kernel_socket_identity: str
    effective_so_rcvbuf_octets: int | None
    effective_so_sndbuf_octets: int | None
    siocinq_queued_octets: int | None
    siocoutq_queued_octets: int | None
    driver_flow: TlsWebSocketDriverFlowSnapshotV49F
    unavailable_fields: tuple[str, ...] = ()
    unavailable_reason_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "kernel_socket_identity",
            canonical_hash(
                self.kernel_socket_identity,
                field="kernel_socket_identity",
            ),
        )
        if type(self.driver_flow) is not TlsWebSocketDriverFlowSnapshotV49F:
            raise CanonicalizationError(
                "driver_flow must be an exact TlsWebSocketDriverFlowSnapshotV49F"
            )
        for field_name, minimum in (
            ("effective_so_rcvbuf_octets", 1),
            ("effective_so_sndbuf_octets", 1),
            ("siocinq_queued_octets", 0),
            ("siocoutq_queued_octets", 0),
        ):
            value = getattr(self, field_name)
            if value is not None:
                if type(value) is not int:
                    raise CanonicalizationError(
                        f"{field_name} must be an exact integer or null"
                    )
                object.__setattr__(
                    self,
                    field_name,
                    canonical_safe_int(value, field=field_name, minimum=minimum),
                )
        expected_unavailable = tuple(
            sorted(
                field_name
                for field_name in (
                    "effective_so_rcvbuf_octets",
                    "effective_so_sndbuf_octets",
                    "siocinq_queued_octets",
                    "siocoutq_queued_octets",
                )
                if getattr(self, field_name) is None
            )
        )
        unavailable = canonical_reason_codes(
            self.unavailable_fields, field="unavailable_fields"
        )
        if unavailable != expected_unavailable:
            raise CanonicalizationError(
                "unavailable_fields must identify every null Linux flow field"
            )
        reasons = canonical_reason_codes(
            self.unavailable_reason_codes, field="unavailable_reason_codes"
        )
        if bool(reasons) != bool(unavailable):
            raise CanonicalizationError(
                "unavailable_reason_codes must be non-empty iff fields are unavailable"
            )
        object.__setattr__(self, "unavailable_fields", unavailable)
        object.__setattr__(self, "unavailable_reason_codes", reasons)


def _socket_ioctl_queued_octets(
    sock: socket.socket,
    request: int,
    *,
    field: str,
) -> int:
    """Read one Linux native-int socket queue count without exposing the fd."""

    buffer = bytearray(4)
    try:
        result = fcntl.ioctl(sock.fileno(), request, buffer, True)
    except OSError as exc:
        raise LinuxSocketOwnerV4Error(f"Linux {field} is unavailable") from exc
    if type(result) is not int:
        raise LinuxSocketOwnerV4Error(f"Linux {field} returned an invalid ioctl result")
    value = int.from_bytes(buffer, byteorder=sys.byteorder, signed=True)
    if value < 0:
        raise LinuxSocketOwnerV4Error(f"Linux {field} returned a negative count")
    return value


def _socket_u64(sock: socket.socket, option: int, *, field: str) -> int:
    try:
        raw = sock.getsockopt(socket.SOL_SOCKET, option, 8)
    except OSError as exc:
        raise LinuxSocketOwnerV4Error(f"Linux {field} is unavailable") from exc
    if type(raw) is not bytes or len(raw) != 8:
        raise LinuxSocketOwnerV4Error(f"Linux {field} is not an exact native u64")
    value = int.from_bytes(raw, byteorder=sys.byteorder, signed=False)
    if value == 0:
        raise LinuxSocketOwnerV4Error(f"Linux {field} is zero")
    return value


class LinuxSocketOwnerV4:
    """One exact connected socket, clock, namespace set, and shared I/O lock."""

    def __init__(
        self,
        *,
        owned_socket: socket.socket,
        governed_clock: LinuxChronyClockV4,
        driver: BoundLinuxSocketDriverV4,
    ) -> None:
        self._initialize(
            owned_socket=owned_socket,
            governed_clock=governed_clock,
            driver=driver,
            v49b_exact_candidate=False,
            v49b_test_candidate=False,
        )

    @classmethod
    def _from_v49b_exact_profile(
        cls,
        *,
        owned_socket: socket.socket,
        governed_clock: LinuxChronyClockV4,
        driver: ExactTlsWebSocketDriverV49,
    ) -> LinuxSocketOwnerV4:
        """Create the production candidate; the public V4 factory stays closed."""

        try:
            if cls is not LinuxSocketOwnerV4:
                raise TypeError("V4.9B owner subclasses are not promotion eligible")
            if type(governed_clock) is not LinuxChronyClockV4:
                raise TypeError("live V4.9B owner requires exact LinuxChronyClockV4")
            if type(driver) is not ExactTlsWebSocketDriverV49:
                raise TypeError(
                    "live V4.9B owner requires exact ExactTlsWebSocketDriverV49"
                )
            if not governed_clock.is_live_profile:
                raise LinuxSocketOwnerV4Error(
                    "live V4.9B owner requires loaded chronyd launch authority"
                )
            if not driver.is_v49b_promotion_eligible:
                raise LinuxSocketOwnerV4Error(
                    "live V4.9B owner requires a promotion-eligible measured "
                    "launch profile"
                )
            result = object.__new__(cls)
            result._initialize(
                owned_socket=owned_socket,
                governed_clock=governed_clock,
                driver=driver,
                v49b_exact_candidate=True,
                v49b_test_candidate=False,
            )
            return result
        except BaseException:
            cls._abort_v49b_candidate_inputs(
                owned_socket=owned_socket,
                governed_clock=governed_clock,
                driver=driver,
            )
            raise

    @classmethod
    def _from_v49b_exact_profile_for_test(
        cls,
        *,
        owned_socket: socket.socket,
        governed_clock: DeterministicLinuxChronyClockV4,
        driver: ExactTlsWebSocketDriverV49,
    ) -> LinuxSocketOwnerV4:
        """Create an exact causal candidate that is explicitly non-promotion."""

        try:
            if cls is not LinuxSocketOwnerV4:
                raise TypeError("V4.9B test owner subclasses are unsupported")
            if type(governed_clock) is not DeterministicLinuxChronyClockV4:
                raise TypeError(
                    "V4.9B test owner requires exact DeterministicLinuxChronyClockV4"
                )
            if type(driver) is not ExactTlsWebSocketDriverV49:
                raise TypeError(
                    "V4.9B test owner requires exact ExactTlsWebSocketDriverV49"
                )
            if not driver.is_v49b_measured_profile:
                raise LinuxSocketOwnerV4Error(
                    "V4.9B test owner still requires exact measured driver authority"
                )
            result = object.__new__(cls)
            result._initialize(
                owned_socket=owned_socket,
                governed_clock=governed_clock,
                driver=driver,
                v49b_exact_candidate=True,
                v49b_test_candidate=True,
            )
            return result
        except BaseException:
            cls._abort_v49b_candidate_inputs(
                owned_socket=owned_socket,
                governed_clock=governed_clock,
                driver=driver,
            )
            raise

    @staticmethod
    def _abort_v49b_candidate_inputs(
        *,
        owned_socket: object,
        governed_clock: object,
        driver: object,
    ) -> None:
        for resource, method_name in (
            (driver, "abort"),
            (owned_socket, "close"),
            (governed_clock, "close"),
        ):
            operation = getattr(resource, method_name, None)
            if callable(operation):
                try:
                    operation()
                except BaseException:
                    pass

    def _initialize(
        self,
        *,
        owned_socket: socket.socket,
        governed_clock: LinuxChronyClockV4,
        driver: BoundLinuxSocketDriverV4,
        v49b_exact_candidate: bool,
        v49b_test_candidate: bool,
    ) -> None:
        if type(self) is not LinuxSocketOwnerV4:
            raise TypeError("LinuxSocketOwnerV4 subclasses are unsupported")
        if sys.platform != "linux":
            raise LinuxSocketOwnerV4Error("the V4.7B socket owner is Linux-only")
        if type(owned_socket) is not socket.socket:
            raise TypeError("owned_socket must be an exact socket.socket")
        if type(governed_clock) not in {
            LinuxChronyClockV4,
            DeterministicLinuxChronyClockV4,
        }:
            raise TypeError(
                "governed_clock must be an exact LinuxChronyClockV4 or "
                "DeterministicLinuxChronyClockV4"
            )
        if not isinstance(driver, BoundLinuxSocketDriverV4):
            raise TypeError("driver must implement BoundLinuxSocketDriverV4")
        if (
            type(v49b_exact_candidate) is not bool
            or type(v49b_test_candidate) is not bool
        ):
            raise TypeError("V4.9B candidate flags must be booleans")
        if v49b_test_candidate and not v49b_exact_candidate:
            raise TypeError("a V4.9B test candidate must also be exact")
        if v49b_exact_candidate and (
            type(driver) is not ExactTlsWebSocketDriverV49
            or not driver.is_v49b_measured_profile
        ):
            raise LinuxSocketOwnerV4Error(
                "V4.9B candidate requires the exact measured TLS/WebSocket driver"
            )
        self._socket = owned_socket
        self._clock = governed_clock
        self._driver = driver
        self._v49b_exact_candidate = v49b_exact_candidate
        self._v49b_test_candidate = v49b_test_candidate
        self._v49b_handshake_attempted = False
        self._v49b_transition: DriverHandshakeTransitionV49B | None = None
        self._v49b_evidence_bound = False
        self._v49b_bound_session_id: str | None = None
        self._v49d_pending_raw: PendingRawIngressV49 | None = None
        self._v49c_active_prepared_wire: PreparedWebSocketWireV49C | None = None
        self._v49c_active_prepared_wire_was_protocol_output = False
        self._v49c_active_prepared_tls: PreparedTlsCiphertextV49C | None = None
        self._v49c_active_prepared_tls_offset = 0
        self._v49e_active_prepared_tls_control: (
            PreparedTlsControlCiphertextV49E | None
        ) = None
        self._v49e_active_prepared_tls_control_offset = 0
        self._v49e_completed_local_close: PreparedTlsControlCiphertextV49E | None = None
        self._v49e_completed_local_close_values: tuple[Any, ...] | None = None
        self._v49e_tcp_write_shutdown_token_sequence = 0
        self._v49e_tcp_write_shutdown_token: TcpWriteShutdownTokenV49E | None = None
        self._v49e_tcp_write_shutdown_token_values: tuple[Any, ...] | None = None
        self._v49e_tcp_write_shutdown_attempted = False
        self._v49e_tcp_write_shutdown_result: TcpWriteShutdownResultV49E | None = None
        self._v49e_terminal_io_fault_latched = False
        self._v49e_terminal_actor_clock_authorized = False
        self._v49e_terminal_actor_clock_evidence_ids: set[str] = set()
        self._creator_pid = os.getpid()
        self._creator_thread_id = threading.get_ident()
        self._fork_invalid = False
        self._closed = False
        self._net_namespace: _PinnedThreadNamespaceV4 | None = None
        self._io_lock = asyncio.Lock()
        try:
            if self._socket.family not in {socket.AF_INET, socket.AF_INET6}:
                raise LinuxSocketOwnerV4Error(
                    "owned transport socket must be AF_INET or AF_INET6"
                )
            if (
                self._socket.getsockopt(socket.SOL_SOCKET, socket.SO_TYPE)
                != socket.SOCK_STREAM
            ):
                raise LinuxSocketOwnerV4Error(
                    "owned transport socket must be a stream socket"
                )
            self._socket.getpeername()
            self._socket.set_inheritable(False)
            if self._socket.get_inheritable():
                raise LinuxSocketOwnerV4Error(
                    "owned transport socket remained inheritable"
                )
            self._net_namespace = _PinnedThreadNamespaceV4(
                kind="net", expected_type=_CLONE_NEWNET
            )
            self._socket_fd = self._socket.fileno()
            socket_stat = os.fstat(self._socket_fd)
            self._socket_stat = (socket_stat.st_dev, socket_stat.st_ino)
            self._socket_cookie = _socket_u64(
                self._socket,
                getattr(socket, "SO_COOKIE", _SO_COOKIE),
                field="SO_COOKIE",
            )
            self._netns_cookie = _socket_u64(
                self._socket,
                getattr(socket, "SO_NETNS_COOKIE", _SO_NETNS_COOKIE),
                field="SO_NETNS_COOKIE",
            )
            self._assert_context()
            self._assert_socket()
            self._initial_snapshot = self._build_snapshot()
            if self._v49b_exact_candidate:
                assert type(self._driver) is ExactTlsWebSocketDriverV49
                self._driver.assert_current()
            _FORK_SENSITIVE.add(self)
        except BaseException:
            self.abort()
            raise

    @property
    def governed_clock(self) -> LinuxChronyClockV4:
        return self._clock

    @property
    def transport_policy(self) -> TransportSubscriptionPolicyV4:
        if type(self._driver) is not ExactTlsWebSocketDriverV49:
            raise LinuxSocketOwnerV4Error(
                "structural test owner has no exact transport policy"
            )
        return self._driver.transport_policy

    @property
    def driver_policy_id(self) -> str:
        """Return the current measured-driver policy retained by this candidate."""

        driver = self._driver
        if (
            not self._v49b_exact_candidate
            or type(driver) is not ExactTlsWebSocketDriverV49
        ):
            raise LinuxSocketOwnerV4Error(
                "driver policy identity requires an exact V4.9B owner candidate"
            )
        self._assert_socket()
        driver.assert_current()
        policy_id = driver.driver_policy_id
        if policy_id is None:
            raise LinuxSocketOwnerV4Error(
                "measured driver policy identity is unavailable"
            )
        return policy_id

    @property
    def is_v49b_exact_profile(self) -> bool:
        if (
            not self._v49b_exact_candidate
            or type(self) is not LinuxSocketOwnerV4
            or type(self._driver) is not ExactTlsWebSocketDriverV49
            or type(self._clock)
            not in {LinuxChronyClockV4, DeterministicLinuxChronyClockV4}
        ):
            return False
        try:
            self._assert_socket()
            self._driver.assert_current()
        except Exception:
            return False
        return self._driver.is_v49b_measured_profile

    @property
    def is_live_profile(self) -> bool:
        """Whether every promotion-critical owner component is concrete."""

        return (
            self.is_v49b_exact_profile
            and not self._v49b_test_candidate
            and type(self._clock) is LinuxChronyClockV4
            and self._clock.is_live_profile
            and type(self._driver) is ExactTlsWebSocketDriverV49
            and self._driver.is_v49b_promotion_eligible
        )

    def monotonic_now_ns(self) -> int:
        """Probe the retained clock only while this exact owner remains valid."""

        self._assert_context()
        self._assert_socket()
        return self._clock.monotonic_now_ns()

    def _assert_context(self) -> None:
        if (
            self._closed
            or self._fork_invalid
            or os.getpid() != self._creator_pid
            or threading.get_ident() != self._creator_thread_id
        ):
            raise LinuxSocketOwnerV4Error(
                "socket authority left its creating process/thread"
            )
        if self._net_namespace is None:
            raise LinuxSocketOwnerV4Error("network namespace pin is closed")
        self._net_namespace.assert_current()

    def _current_netns_cookie(self) -> int:
        try:
            with socket.socket(self._socket.family, socket.SOCK_DGRAM) as probe:
                probe.set_inheritable(False)
                return _socket_u64(
                    probe,
                    getattr(socket, "SO_NETNS_COOKIE", _SO_NETNS_COOKIE),
                    field="probe SO_NETNS_COOKIE",
                )
        except OSError as exc:
            raise LinuxSocketOwnerV4Error(
                "current network namespace could not be probed"
            ) from exc

    def _assert_socket(self) -> None:
        self._assert_context()
        try:
            if self._socket.fileno() != self._socket_fd:
                raise LinuxSocketOwnerV4Error("owned socket descriptor changed")
            if self._socket.get_inheritable():
                raise LinuxSocketOwnerV4Error("owned socket became inheritable")
            current_stat = os.fstat(self._socket_fd)
            if (current_stat.st_dev, current_stat.st_ino) != self._socket_stat:
                raise LinuxSocketOwnerV4Error("owned socket descriptor was reused")
            self._socket.getpeername()
            cookie = _socket_u64(
                self._socket,
                getattr(socket, "SO_COOKIE", _SO_COOKIE),
                field="SO_COOKIE",
            )
            netns_cookie = _socket_u64(
                self._socket,
                getattr(socket, "SO_NETNS_COOKIE", _SO_NETNS_COOKIE),
                field="SO_NETNS_COOKIE",
            )
            if cookie != self._socket_cookie:
                raise LinuxSocketOwnerV4Error("owned socket SO_COOKIE changed")
            if (
                netns_cookie != self._netns_cookie
                or self._current_netns_cookie() != self._netns_cookie
            ):
                raise LinuxSocketOwnerV4Error(
                    "owned socket is outside the pinned network namespace"
                )
        except LinuxSocketOwnerV4Error:
            raise
        except OSError as exc:
            raise LinuxSocketOwnerV4Error("owned socket is no longer live") from exc

    def _assert_terminal_socket_owner_v49e(self) -> None:
        """Verify retained fd/namespace identity after TCP FIN disconnects peer."""

        self._assert_context()
        try:
            if self._socket.fileno() != self._socket_fd:
                raise LinuxSocketOwnerV4Error("terminal socket descriptor changed")
            if self._socket.get_inheritable():
                raise LinuxSocketOwnerV4Error("terminal socket became inheritable")
            current_stat = os.fstat(self._socket_fd)
            if (current_stat.st_dev, current_stat.st_ino) != self._socket_stat:
                raise LinuxSocketOwnerV4Error("terminal socket descriptor was reused")
            if (
                _socket_u64(
                    self._socket,
                    getattr(socket, "SO_COOKIE", _SO_COOKIE),
                    field="SO_COOKIE",
                )
                != self._socket_cookie
            ):
                raise LinuxSocketOwnerV4Error("terminal socket SO_COOKIE changed")
            netns_cookie = _socket_u64(
                self._socket,
                getattr(socket, "SO_NETNS_COOKIE", _SO_NETNS_COOKIE),
                field="SO_NETNS_COOKIE",
            )
            if (
                netns_cookie != self._netns_cookie
                or self._current_netns_cookie() != self._netns_cookie
            ):
                raise LinuxSocketOwnerV4Error(
                    "terminal socket left the pinned network namespace"
                )
            if self._build_snapshot() != self._initial_snapshot:
                raise LinuxSocketOwnerV4Error("terminal socket-owner identity changed")
        except LinuxSocketOwnerV4Error:
            raise
        except OSError as exc:
            raise LinuxSocketOwnerV4Error(
                "terminal socket identity is unavailable"
            ) from exc

    def _build_snapshot(self) -> TransportSocketOwnerSnapshotV4:
        assert self._net_namespace is not None
        return TransportSocketOwnerSnapshotV4(
            kernel_boot_id=self._clock.kernel_boot_id,
            time_namespace_id=self._clock.time_namespace_id,
            network_namespace_id=self._net_namespace.namespace_id,
            socket_cookie_u64=format_linux_socket_cookie_u64(self._socket_cookie),
            clock_resolution_ns=self._clock.clock_resolution_ns,
            chronyd_launch_id=self._clock.chronyd_launch_id,
            chronyd_runtime_observation_sha256=(
                self._clock.chronyd_runtime_observation_sha256
            ),
        )

    def snapshot(self) -> TransportSocketOwnerSnapshotV4:
        self._assert_socket()
        snapshot = self._build_snapshot()
        if hasattr(self, "_initial_snapshot") and snapshot != self._initial_snapshot:
            raise LinuxSocketOwnerV4Error("socket-owner identity changed")
        return snapshot

    def assert_same_owner(self, expected: TransportSocketOwnerSnapshotV4) -> None:
        if type(expected) is not TransportSocketOwnerSnapshotV4:
            raise TypeError("expected must be an exact TransportSocketOwnerSnapshotV4")
        if self.snapshot() != expected:
            raise LinuxSocketOwnerV4Error("socket owner differs from expected binding")

    def assert_same_terminal_journal_owner_v49e(
        self, expected: TransportSocketOwnerSnapshotV4
    ) -> None:
        """Validate the sealed post-FIN journal owner without a live peer probe."""

        if type(expected) is not TransportSocketOwnerSnapshotV4:
            raise TypeError("expected must be an exact TransportSocketOwnerSnapshotV4")
        if not self._v49e_terminal_actor_clock_authorized:
            raise LinuxSocketOwnerV4Error(
                "terminal journal owner lacks validated terminal evidence"
            )
        self._assert_terminal_actor_clock_base_v49e()
        if self._build_snapshot() != expected:
            raise LinuxSocketOwnerV4Error(
                "terminal journal owner differs from expected binding"
            )

    def sample_governed(self) -> GovernedClockSampleV4:
        self._assert_socket()
        sample = self._clock.sample_governed()
        self._assert_socket()
        if (
            sample.monotonic_clock_domain_id
            != self._initial_snapshot.monotonic_clock_domain_id
            or sample.chronyd_launch_id != self._initial_snapshot.chronyd_launch_id
            or sample.chronyd_runtime_observation_sha256
            != self._initial_snapshot.chronyd_runtime_observation_sha256
        ):
            raise LinuxSocketOwnerV4Error(
                "clock or loaded-chronyd authority changed under socket owner"
            )
        return sample

    def sample_terminal_governed_v49e(self) -> GovernedClockSampleV4:
        """Sample the actor clock after exact consumed terminal owner evidence.

        A conclusive peer EOF can make ``getpeername()`` return ``ENOTCONN``
        even though the retained descriptor, socket cookie, network namespace,
        measured driver, and governed clock are still the exact authorities
        bound to the durable session.  Ordinary and pre-observation actor work
        must continue to use :meth:`sample_governed`, whose live-peer assertion
        is intentionally stronger.  The journal actor may use this capability
        only after it has consumed and validated an owner-sealed terminal
        effect or terminal failure capability.
        """

        if not self._v49e_terminal_actor_clock_authorized:
            raise LinuxSocketOwnerV4Error(
                "terminal actor clock lacks validated terminal owner evidence"
            )
        driver = self._assert_terminal_actor_clock_base_v49e()
        sample = self._clock.sample_governed()
        self._assert_terminal_socket_owner_v49e()
        driver.assert_terminal_journal_authority_v49e()
        if (
            sample.monotonic_clock_domain_id
            != self._initial_snapshot.monotonic_clock_domain_id
            or sample.chronyd_launch_id != self._initial_snapshot.chronyd_launch_id
            or sample.chronyd_runtime_observation_sha256
            != self._initial_snapshot.chronyd_runtime_observation_sha256
        ):
            raise LinuxSocketOwnerV4Error(
                "clock or loaded-chronyd authority changed under terminal actor"
            )
        return sample

    def _assert_terminal_actor_clock_base_v49e(
        self,
    ) -> ExactTlsWebSocketDriverV49:
        """Validate retained terminal authority without requiring live peer state."""

        driver = self._driver
        if not (
            self._v49b_exact_candidate
            and self._v49b_evidence_bound
            and self._v49b_transition is not None
            and type(self._v49b_bound_session_id) is str
            and bool(self._v49b_bound_session_id)
            and type(driver) is ExactTlsWebSocketDriverV49
            and driver.state
            in {
                TlsWebSocketDriverStateV49.TLS_SHUTDOWN_V49E,
                TlsWebSocketDriverStateV49.FAULT_LATCHED,
            }
        ):
            raise LinuxSocketOwnerV4Error(
                "terminal actor clock requires exact retained session authority"
            )

        self._assert_terminal_socket_owner_v49e()
        driver.assert_terminal_journal_authority_v49e()
        return driver

    def _authorize_terminal_actor_clock_v49e(
        self,
        *,
        observation: OwnerTlsShutdownObservationV49E,
    ) -> None:
        """Admit terminal sampling from one exact consumed live capability.

        ``OwnerTlsShutdownObservationV49E.consume_for_actor_v49e`` creates a
        second registry handoff for the same exact object.  This method consumes
        that handoff, so public hash fields, copies, and duplicate calls cannot
        authorize the terminal journal clock seam.
        """

        self._authorize_terminal_actor_clock_from_evidence_v49e(observation)

    def _authorize_terminal_actor_clock_from_evidence_v49e(
        self,
        evidence: Any,
    ) -> None:
        """Consume one exact post-mutation handoff and open terminal clocks."""

        if type(evidence) is OwnerTlsShutdownObservationV49E:
            self._assert_owner_tls_shutdown_observation_integrity_v49e(evidence)
            evidence_id = evidence.owner_observation_id
            session_id = evidence.transport_session_id
            socket_identity = evidence.kernel_socket_identity
        elif type(evidence) is LinuxSocketOwnerV4DeadlineExpiredNoObservationV49E:
            self._assert_deadline_expired_no_observation_integrity_v49e(evidence)
            evidence_id = evidence.owner_evidence_id
            session_id = evidence.transport_session_id
            socket_identity = evidence.kernel_socket_identity
        elif type(evidence) is LinuxSocketOwnerV4DeadlineExpiredAfterProgressV49E:
            self._assert_deadline_expired_after_progress_integrity_v49e(evidence)
            evidence_id = evidence.owner_evidence_id
            session_id = evidence.transport_session_id
            socket_identity = evidence.kernel_socket_identity
        elif (
            type(evidence)
            is LinuxSocketOwnerV4SendDeadlineExpiredNoKernelAcceptanceV49E
        ):
            self._assert_send_deadline_no_kernel_acceptance_integrity_v49e(evidence)
            evidence_id = evidence.owner_evidence_id
            session_id = evidence.transport_session_id
            socket_identity = evidence.kernel_socket_identity
        elif type(evidence) is OwnerUnsendableTlsPostHandshakeOutputV49E:
            self._assert_owner_unsendable_tls_output_integrity_v49e(evidence)
            evidence_id = evidence.owner_unsendable_output_id
            session_id = evidence.transport_session_id
            socket_identity = evidence.kernel_socket_identity
        elif type(evidence) is TcpWriteShutdownResultV49E:
            self._assert_tcp_write_shutdown_result_integrity_v49e(evidence)
            evidence_id = evidence.shutdown_result_id
            session_id = evidence.shutdown_token.transport_session_id
            socket_identity = self._initial_snapshot.kernel_socket_identity
        else:
            raise TypeError(
                "terminal actor clock requires exact consumed owner evidence"
            )
        if (
            session_id != self._v49b_bound_session_id
            or socket_identity != self._initial_snapshot.kernel_socket_identity
        ):
            raise LinuxSocketOwnerV4Error(
                "terminal actor clock evidence differs from retained authority"
            )
        _consume_owner_capability_v49e(
            capability_kind="TERMINAL_CLOCK_AUTHORIZATION_HANDOFF",
            capability_id=evidence_id,
            capability=evidence,
        )
        driver = self._driver
        if type(driver) is not ExactTlsWebSocketDriverV49:
            raise LinuxSocketOwnerV4Error(
                "terminal actor clock lost its exact retained driver"
            )
        if driver.state not in {
            TlsWebSocketDriverStateV49.TLS_SHUTDOWN_V49E,
            TlsWebSocketDriverStateV49.FAULT_LATCHED,
        }:
            driver._latch_terminal_journal_fault_v49e()  # noqa: SLF001
        self._assert_terminal_actor_clock_base_v49e()
        self._v49e_terminal_actor_clock_authorized = True
        self._v49e_terminal_actor_clock_evidence_ids.add(evidence_id)

    def _restore_terminal_actor_clock_from_chain_v49e(
        self,
        *,
        events: tuple[Any, ...],
    ) -> None:
        """Revalidate prior live authorization against a full durable chain."""

        from .physical_transport_actor_v49c import (
            LocalShutdownDeadlineEvidencePayloadV49E,
            TcpHalfCloseResultPayloadV49E,
            TerminalIngressFailurePayloadV49E,
            TlsProtocolOperationFailedPayloadV49E,
            TlsProtocolOperationFailureKindV49E,
            TlsProtocolOperationPurposeV49E,
            TlsShutdownObservedPayloadV49E,
            TransportActorEventV49C,
            validate_transport_actor_chain_v49c,
        )

        if not events or any(
            type(event) is not TransportActorEventV49C for event in events
        ):
            raise LinuxSocketOwnerV4Error(
                "terminal actor clock restoration requires an exact durable chain"
            )
        validate_transport_actor_chain_v49c(events)
        candidate: tuple[str, str] | None = None
        for event in reversed(events):
            payload = event.payload
            if type(payload) is TlsShutdownObservedPayloadV49E:
                candidate = (
                    payload.owner_observation_id,
                    payload.owner_kernel_socket_identity,
                )
            elif type(payload) is LocalShutdownDeadlineEvidencePayloadV49E:
                candidate = (
                    payload.owner_evidence_id,
                    payload.kernel_socket_identity,
                )
            elif type(payload) is TerminalIngressFailurePayloadV49E:
                candidate = (
                    payload.owner_evidence_id,
                    payload.kernel_socket_identity,
                )
            elif type(payload) is TcpHalfCloseResultPayloadV49E:
                candidate = (
                    payload.shutdown_result_id,
                    self._initial_snapshot.kernel_socket_identity,
                )
            elif type(payload) is TlsProtocolOperationFailedPayloadV49E:
                if (
                    payload.failure_kind
                    is TlsProtocolOperationFailureKindV49E.DEADLINE_EXPIRED_AFTER_PROGRESS
                ):
                    candidate = (
                        payload.deadline_after_progress_owner_evidence_id,
                        payload.deadline_after_progress_kernel_socket_identity,
                    )
                elif (
                    payload.failure_kind
                    is TlsProtocolOperationFailureKindV49E.DEADLINE_EXPIRED_NO_OBSERVATION
                    and payload.purpose
                    is TlsProtocolOperationPurposeV49E.PEER_SHUTDOWN_POLL
                ):
                    candidate = (
                        payload.deadline_no_observation_owner_evidence_id,
                        payload.deadline_no_observation_kernel_socket_identity,
                    )
                elif (
                    payload.failure_kind
                    is TlsProtocolOperationFailureKindV49E.UNSENDABLE_POST_HANDSHAKE_OUTPUT_AFTER_SHUT_WR
                ):
                    candidate = (
                        payload.unsendable_owner_evidence_id,
                        payload.unsendable_kernel_socket_identity,
                    )
            if candidate is not None:
                break
        if candidate is None or any(value is None for value in candidate):
            raise LinuxSocketOwnerV4Error(
                "terminal actor clock restoration lacks durable owner evidence"
            )
        evidence_id, kernel_socket_identity = candidate
        assert type(evidence_id) is str
        assert type(kernel_socket_identity) is str
        if (
            not self._v49e_terminal_actor_clock_authorized
            or evidence_id not in self._v49e_terminal_actor_clock_evidence_ids
        ):
            raise LinuxSocketOwnerV4Error(
                "durable terminal evidence lacks prior live owner authorization"
            )
        if any(
            event.transport_session_id != self._v49b_bound_session_id
            for event in events
        ):
            raise LinuxSocketOwnerV4Error(
                "terminal actor clock chain differs from retained session"
            )
        if kernel_socket_identity != self._initial_snapshot.kernel_socket_identity:
            raise LinuxSocketOwnerV4Error(
                "durable terminal evidence changes retained socket authority"
            )
        self._assert_terminal_actor_clock_base_v49e()

    def sample(self) -> ClockEvidenceV4:
        return self.sample_governed().as_clock_evidence()

    async def establish_v49b_handshake(self) -> DriverHandshakeTransitionV49B:
        """Run the one permitted handshake inside owner and clock brackets."""

        async with self._io_lock:
            try:
                if not self.is_v49b_exact_profile:
                    raise LinuxSocketOwnerV4Error(
                        "driver handshake requires an exact V4.9B owner candidate"
                    )
                if self._v49b_handshake_attempted:
                    raise LinuxSocketOwnerV4Error("V4.9B owner handshake is one-shot")
                self._v49b_handshake_attempted = True
                driver = self._driver
                assert type(driver) is ExactTlsWebSocketDriverV49
                owner_before = self.snapshot()
                pre_sample = self.sample_governed()
                self.assert_same_owner(owner_before)
                driver.assert_current()
                started_ns = self.monotonic_now_ns()
                if started_ns <= pre_sample.boottime_after_ns:
                    raise LinuxSocketOwnerV4Error(
                        "handshake start is not strictly after pre-sample bracket"
                    )

                evidence = await driver.handshake(self._socket)
                if type(evidence) is not DriverHandshakeEvidenceV49:
                    raise LinuxSocketOwnerV4Error(
                        "exact driver returned unsupported handshake evidence"
                    )
                completed_ns = self.monotonic_now_ns()
                if completed_ns <= started_ns:
                    raise LinuxSocketOwnerV4Error(
                        "handshake completion did not advance CLOCK_BOOTTIME"
                    )
                post_sample = self.sample_governed()
                owner_after = self.snapshot()
                driver.assert_current()
                policy_id = driver.driver_policy_id
                runtime_observation = driver.runtime_observation_sha256
                if policy_id is None or runtime_observation is None:
                    raise LinuxSocketOwnerV4Error(
                        "measured driver identities disappeared during handshake"
                    )
                transition = DriverHandshakeTransitionV49B(
                    _token=_V49B_TRANSITION_TOKEN,
                    evidence=evidence,
                    pre_sample=pre_sample,
                    post_sample=post_sample,
                    owner_snapshot=owner_before,
                    owner_snapshot_after=owner_after,
                    handshake_started_monotonic_ns=started_ns,
                    handshake_completed_monotonic_ns=completed_ns,
                    driver_policy_id=policy_id,
                    runtime_observation_sha256=runtime_observation,
                )
                self._v49b_transition = transition
                return transition
            except BaseException:
                self.abort()
                raise

    def assert_v49b_session_mapping(
        self,
        transition: DriverHandshakeTransitionV49B,
        session: TransportSessionAttestationV4,
    ) -> None:
        """Require one signed session to be an exact projection of evidence."""

        try:
            if (
                type(transition) is not DriverHandshakeTransitionV49B
                or transition is not self._v49b_transition
                or type(session) is not TransportSessionAttestationV4
                or not self.is_v49b_exact_profile
                or not self._v49b_handshake_attempted
                or self._v49b_evidence_bound
            ):
                raise LinuxSocketOwnerV4Error(
                    "session mapping requires the retained unbound V4.9B transition"
                )
            if self._io_lock.locked():
                raise LinuxSocketOwnerV4Error("session mapping cannot race owner I/O")
            self.assert_same_owner(transition.owner_snapshot)
            driver = self._driver
            assert type(driver) is ExactTlsWebSocketDriverV49
            driver.assert_current()
            session.verify_signature()
            evidence = transition.evidence
            expected = {
                "session_nonce": evidence.evidence_nonce_sha256,
                "clock_source_manifest_id": (
                    transition.pre_sample.clock_source_manifest_id
                ),
                "transport_subscription_policy_id": (
                    driver.transport_policy.transport_subscription_policy_id
                ),
                "collector_boot_id": transition.owner_snapshot.kernel_boot_id,
                "authoritative_endpoint": (
                    driver.transport_policy.authoritative_endpoint
                ),
                "tls_server_name": driver.transport_policy.tls_server_name,
                "remote_address": evidence.remote_address,
                "tls_version": evidence.tls_version,
                "tls_cipher": evidence.tls_cipher,
                "alpn_protocol": evidence.alpn_protocol,
                "websocket_extensions": evidence.websocket_extensions,
                "peer_certificate_sha256": evidence.peer_certificate_sha256,
                "peer_spki_sha256": evidence.peer_spki_sha256,
                "trust_store_manifest_id": evidence.trust_store_manifest_id,
                "certificate_verified": evidence.certificate_verified,
                "hostname_verified": evidence.hostname_verified,
                "websocket_http_status": evidence.websocket_http_status,
                "websocket_accept_verified": (evidence.websocket_accept_verified),
                "handshake_request_sha256": evidence.handshake_request_sha256,
                "handshake_response_sha256": evidence.handshake_response_sha256,
                "handshake_started_at": transition.handshake_started_at,
                "handshake_completed_at": transition.handshake_completed_at,
                "monotonic_clock_domain_id": (
                    transition.pre_sample.monotonic_clock_domain_id
                ),
                "handshake_started_monotonic_ns": (
                    transition.pre_sample.boottime_after_ns
                ),
                "handshake_completed_monotonic_ns": (
                    transition.post_sample.boottime_before_ns
                ),
                "clock_uncertainty_milliseconds": (
                    transition.clock_uncertainty_milliseconds
                ),
                "collector_runtime_id": driver.runtime_environment_manifest_id,
            }
            mismatched_fields = tuple(
                field_name
                for field_name, expected_value in expected.items()
                if getattr(session, field_name) != expected_value
            )
            if mismatched_fields:
                raise LinuxSocketOwnerV4Error(
                    "signed session is not an exact driver/owner evidence projection: "
                    + ", ".join(mismatched_fields)
                )
            if (
                transition.driver_policy_id != driver.driver_policy_id
                or transition.runtime_observation_sha256
                != driver.runtime_observation_sha256
            ):
                raise LinuxSocketOwnerV4Error(
                    "measured driver identity changed before session commitment"
                )
            self.assert_same_owner(transition.owner_snapshot_after)
        except BaseException:
            self.abort()
            raise

    def _assert_driver_derived_session_v49b(
        self,
        session: TransportSessionAttestationV4,
    ) -> None:
        """Projection compatibility alias using the retained transition."""

        transition = self._v49b_transition
        if transition is None:
            self.abort()
            raise LinuxSocketOwnerV4Error(
                "driver-derived session has no retained handshake transition"
            )
        self.assert_v49b_session_mapping(transition, session)

    def bind_committed_v49b_handshake(
        self,
        transition: DriverHandshakeTransitionV49B,
        session: TransportSessionAttestationV4,
    ) -> PendingRawIngressV49 | None:
        """Bind the exact evidence only after its durable session commit."""

        try:
            self.assert_v49b_session_mapping(transition, session)
            if self._io_lock.locked():
                raise LinuxSocketOwnerV4Error(
                    "post-commit evidence bind cannot race owner I/O"
                )
            driver = self._driver
            assert type(driver) is ExactTlsWebSocketDriverV49
            pending = driver.bind_handshake_evidence(transition.evidence)
            if pending is not None and type(pending) is not PendingRawIngressV49:
                raise LinuxSocketOwnerV4Error(
                    "exact driver returned unsupported initial RAW ingress"
                )
            self.assert_same_owner(transition.owner_snapshot)
            self._v49b_evidence_bound = True
            self._v49b_bound_session_id = session.transport_session_id
            self._v49d_pending_raw = pending
            return pending
        except BaseException:
            self.abort()
            raise

    def _assert_v49b_io_bound(self) -> None:
        if self._v49b_exact_candidate and not self._v49b_evidence_bound:
            raise LinuxSocketOwnerV4Error(
                "V4.9B driver I/O is unavailable before committed evidence bind"
            )

    def _assert_v49c_staged_io_bound(self) -> ExactTlsWebSocketDriverV49:
        """Return the exact staged driver only under committed V4.9B authority."""

        driver = self._driver
        if (
            not self._v49b_exact_candidate
            or not self._v49b_evidence_bound
            or self._v49b_transition is None
            or type(self._v49b_bound_session_id) is not str
            or not self._v49b_bound_session_id
            or type(driver) is not ExactTlsWebSocketDriverV49
            or self._v49e_terminal_io_fault_latched
        ):
            raise LinuxSocketOwnerV4Error(
                "V4.9C staged I/O requires the exact committed V4.9B evidence binding"
            )
        self.assert_same_owner(self._initial_snapshot)
        driver.assert_current()
        return driver

    def _assert_v49f_flow_snapshot_bound(self) -> ExactTlsWebSocketDriverV49:
        """Validate snapshot ownership without mutation-authority rehash work.

        Every mutating I/O seam continues to use ``driver.assert_current()``.
        A count-only observation deliberately avoids rehashing the retained
        runtime closure and rebuilding the trust-store OpenSSL context because
        that work would contaminate the flow measurement itself.
        """

        driver = self._driver
        if (
            not self._v49b_exact_candidate
            or not self._v49b_evidence_bound
            or self._v49b_transition is None
            or type(self._v49b_bound_session_id) is not str
            or not self._v49b_bound_session_id
            or type(driver) is not ExactTlsWebSocketDriverV49
            or driver.state
            in {
                TlsWebSocketDriverStateV49.FAULT_LATCHED,
                TlsWebSocketDriverStateV49.CLOSED,
            }
            or self._v49e_terminal_io_fault_latched
        ):
            raise LinuxSocketOwnerV4Error(
                "V4.9F flow observation requires one committed live session"
            )
        self.assert_same_owner(self._initial_snapshot)
        return driver

    @property
    def capacity_measurement_driver_evidence_nonce_v49f(self) -> str:
        """Return the bound driver nonce as non-capability measurement identity."""

        transition = self._v49b_transition
        if (
            not self._v49b_exact_candidate
            or not self._v49b_evidence_bound
            or type(self._v49b_bound_session_id) is not str
            or type(transition) is not DriverHandshakeTransitionV49B
        ):
            raise LinuxSocketOwnerV4Error(
                "capacity identity requires one committed V4.9B binding"
            )
        return transition.evidence.evidence_nonce_sha256

    def authoritative_manifest_observation_v49f(
        self,
    ) -> LinuxTransportManifestAuthorityObservationV49F:
        """Revalidate and expose immutable identity of the retained authority.

        The exact measured driver is rehashed by ``assert_current()`` before
        any values are returned.  No socket, descriptor, driver, transition,
        artifact authority, or effect method escapes this seam.
        """

        driver = self._assert_v49c_staged_io_bound()
        driver.assert_current()
        transition = self._v49b_transition
        session_id = self._v49b_bound_session_id
        if (
            type(transition) is not DriverHandshakeTransitionV49B
            or type(session_id) is not str
            or not session_id
        ):
            raise LinuxSocketOwnerV4Error(
                "manifest authority requires the exact retained session transition"
            )
        snapshot = self.snapshot()
        driver_policy_id = driver.driver_policy_id
        runtime_observation = driver.runtime_observation_sha256
        if (
            driver_policy_id is None
            or runtime_observation is None
            or driver_policy_id != transition.driver_policy_id
            or runtime_observation != transition.runtime_observation_sha256
        ):
            raise LinuxSocketOwnerV4Error(
                "measured driver identity changed after the retained handshake"
            )
        return LinuxTransportManifestAuthorityObservationV49F(
            transport_session_id=session_id,
            driver_policy_id=driver_policy_id,
            driver_runtime_observation_sha256=runtime_observation,
            driver_evidence_nonce_sha256=(transition.evidence.evidence_nonce_sha256),
            kernel_socket_identity=snapshot.kernel_socket_identity,
            kernel_boot_id=snapshot.kernel_boot_id,
            time_namespace_id=snapshot.time_namespace_id,
            network_namespace_id=snapshot.network_namespace_id,
            monotonic_clock_domain_id=snapshot.monotonic_clock_domain_id,
            clock_source_manifest_id=self._clock.policy.manifest_id,
            chronyd_launch_id=snapshot.chronyd_launch_id,
            chronyd_runtime_observation_sha256=(
                snapshot.chronyd_runtime_observation_sha256
            ),
        )

    def _assert_v49e_shutdown_io_bound(self) -> ExactTlsWebSocketDriverV49:
        """Retain owner authority after a legitimate peer FIN disconnect state."""

        driver = self._driver
        if (
            not self._v49b_exact_candidate
            or not self._v49b_evidence_bound
            or self._v49b_transition is None
            or type(self._v49b_bound_session_id) is not str
            or not self._v49b_bound_session_id
            or type(driver) is not ExactTlsWebSocketDriverV49
            or driver.state is not TlsWebSocketDriverStateV49.TLS_SHUTDOWN_V49E
            or self._v49e_terminal_io_fault_latched
        ):
            raise LinuxSocketOwnerV4Error(
                "V4.9E shutdown polling requires exact retained session authority"
            )
        self._assert_terminal_socket_owner_v49e()
        driver.assert_current()
        return driver

    def _latch_terminal_io_fault_for_projection_v49e(self) -> None:
        """Fence all further I/O while retaining journal owner authority."""

        try:
            self.assert_same_owner(self._initial_snapshot)
        except BaseException:
            self.abort()
            raise
        self._v49e_terminal_io_fault_latched = True

    @property
    def has_pending_raw_ingress_v49d(self) -> bool:
        """Whether the owner retains one exact RAW batch awaiting adoption."""

        self._assert_socket()
        return self._v49d_pending_raw is not None

    @property
    def durable_ingress_buffer_octets_v49d(self) -> int:
        """Return the retained durable plaintext size without exposing bytes."""

        driver = self._assert_v49c_staged_io_bound()
        return driver.durable_ingress_buffer_octets_v49d

    async def transport_flow_snapshot_v49f(
        self,
    ) -> LinuxSocketTransportFlowSnapshotV49F:
        """Observe count-only driver and kernel flow under the owner I/O lock.

        The socket stays private.  Linux queue counters are transient local
        observations and aren't evidence that a peer received any ciphertext.
        """

        async with self._io_lock:
            driver = self._assert_v49f_flow_snapshot_bound()
            driver_flow = await driver.transport_flow_snapshot_v49f()
            if type(driver_flow) is not TlsWebSocketDriverFlowSnapshotV49F:
                raise LinuxSocketOwnerV4Error(
                    "exact driver returned an unsupported flow snapshot"
                )

            pending_raw = self._v49d_pending_raw
            if pending_raw is None:
                owner_pending_raw_chunks = 0
                owner_pending_raw_octets = 0
            else:
                if (
                    type(pending_raw) is not PendingRawIngressV49
                    or type(pending_raw.chunks) is not tuple
                    or not pending_raw.chunks
                    or any(
                        type(chunk) is not bytes or not chunk
                        for chunk in pending_raw.chunks
                    )
                    or type(pending_raw.total_octets) is not int
                    or pending_raw.total_octets != sum(map(len, pending_raw.chunks))
                ):
                    raise LinuxSocketOwnerV4Error(
                        "owner retained an invalid pending RAW count state"
                    )
                owner_pending_raw_chunks = len(pending_raw.chunks)
                owner_pending_raw_octets = pending_raw.total_octets
            if (
                driver_flow.pending_raw_chunks != owner_pending_raw_chunks
                or driver_flow.pending_raw_octets != owner_pending_raw_octets
            ):
                raise LinuxSocketOwnerV4Error(
                    "owner and driver pending RAW flow counts diverged"
                )

            staged_tls = self._v49c_active_prepared_tls
            staged_tls_offset = self._v49c_active_prepared_tls_offset
            if staged_tls is None:
                if staged_tls_offset != 0:
                    raise LinuxSocketOwnerV4Error(
                        "owner staged TLS offset exists without an artifact"
                    )
                owner_staged_tls_octets = 0
                owner_remaining_staged_tls_octets = 0
            else:
                if (
                    type(staged_tls) is not PreparedTlsCiphertextV49C
                    or type(staged_tls_offset) is not int
                    or type(staged_tls.ciphertext_octets) is not int
                    or not 0 <= staged_tls_offset < staged_tls.ciphertext_octets
                ):
                    raise LinuxSocketOwnerV4Error(
                        "owner retained an invalid staged TLS count state"
                    )
                owner_staged_tls_octets = staged_tls.ciphertext_octets
                owner_remaining_staged_tls_octets = (
                    owner_staged_tls_octets - staged_tls_offset
                )
            if (
                driver_flow.staged_tls_ciphertext_octets != owner_staged_tls_octets
                or driver_flow.remaining_staged_tls_ciphertext_octets
                != owner_remaining_staged_tls_octets
            ):
                raise LinuxSocketOwnerV4Error(
                    "owner and driver staged TLS flow counts diverged"
                )

            staged_control = self._v49e_active_prepared_tls_control
            staged_control_offset = self._v49e_active_prepared_tls_control_offset
            if staged_control is None:
                if staged_control_offset != 0:
                    raise LinuxSocketOwnerV4Error(
                        "owner TLS-control offset exists without an artifact"
                    )
                owner_staged_control_octets = 0
                owner_remaining_staged_control_octets = 0
            else:
                if (
                    type(staged_control) is not PreparedTlsControlCiphertextV49E
                    or type(staged_control_offset) is not int
                    or type(staged_control.ciphertext_octets) is not int
                    or not 0 <= staged_control_offset < staged_control.ciphertext_octets
                ):
                    raise LinuxSocketOwnerV4Error(
                        "owner retained an invalid staged TLS-control count state"
                    )
                owner_staged_control_octets = staged_control.ciphertext_octets
                owner_remaining_staged_control_octets = (
                    owner_staged_control_octets - staged_control_offset
                )
            if (
                driver_flow.staged_tls_control_ciphertext_octets
                != owner_staged_control_octets
                or driver_flow.remaining_staged_tls_control_ciphertext_octets
                != owner_remaining_staged_control_octets
            ):
                raise LinuxSocketOwnerV4Error(
                    "owner and driver staged TLS-control flow counts diverged"
                )

            unavailable_fields: list[str] = []
            unavailable_reasons: list[str] = []

            def socket_buffer(option: int, *, field: str, reason: str) -> int | None:
                try:
                    value = self._socket.getsockopt(socket.SOL_SOCKET, option)
                except OSError:
                    unavailable_fields.append(field)
                    unavailable_reasons.append(f"{reason}_UNAVAILABLE")
                    return None
                if type(value) is not int or value < 1:
                    unavailable_fields.append(field)
                    unavailable_reasons.append(f"{reason}_INVALID")
                    return None
                return value

            def socket_queue(request: int, *, field: str, reason: str) -> int | None:
                try:
                    return _socket_ioctl_queued_octets(
                        self._socket,
                        request,
                        field=reason,
                    )
                except LinuxSocketOwnerV4Error:
                    unavailable_fields.append(field)
                    unavailable_reasons.append(f"{reason}_UNAVAILABLE")
                    return None

            effective_receive_buffer = socket_buffer(
                socket.SO_RCVBUF,
                field="effective_so_rcvbuf_octets",
                reason="SO_RCVBUF",
            )
            effective_send_buffer = socket_buffer(
                socket.SO_SNDBUF,
                field="effective_so_sndbuf_octets",
                reason="SO_SNDBUF",
            )
            receive_queue = socket_queue(
                _SIOCINQ,
                field="siocinq_queued_octets",
                reason="SIOCINQ",
            )
            send_queue = socket_queue(
                _SIOCOUTQ,
                field="siocoutq_queued_octets",
                reason="SIOCOUTQ",
            )
            self.assert_same_owner(self._initial_snapshot)
            if (
                self._assert_v49f_flow_snapshot_bound() is not driver
                or driver.state is not driver_flow.driver_state
            ):
                raise LinuxSocketOwnerV4Error(
                    "driver changed during V4.9F flow observation"
                )
            return LinuxSocketTransportFlowSnapshotV49F(
                kernel_socket_identity=(self._initial_snapshot.kernel_socket_identity),
                effective_so_rcvbuf_octets=effective_receive_buffer,
                effective_so_sndbuf_octets=effective_send_buffer,
                siocinq_queued_octets=receive_queue,
                siocoutq_queued_octets=send_queue,
                driver_flow=driver_flow,
                unavailable_fields=tuple(unavailable_fields),
                unavailable_reason_codes=tuple(unavailable_reasons),
            )

    async def read_decrypted_ingress_v49d(
        self, *, timeout_seconds: int
    ) -> PendingRawIngressV49:
        """Return one owner-retained RAW batch without hidden TLS writes.

        An initial post-upgrade batch is returned without another kernel read.
        Continuing reads use the exact retained socket and V4.9D driver under
        the shared owner lock.  No socket, callback, or parser seam is exposed.
        """

        timeout = canonical_safe_int(
            timeout_seconds, field="timeout_seconds", minimum=1, maximum=300
        )
        async with self._io_lock:
            try:
                driver = self._assert_v49c_staged_io_bound()
                if (
                    self._v49c_active_prepared_wire is not None
                    or self._v49c_active_prepared_tls is not None
                    or self._v49c_active_prepared_tls_offset != 0
                ):
                    raise LinuxSocketOwnerV4Error(
                        "V4.9D ingress cannot race an active outbound artifact"
                    )
                pending = self._v49d_pending_raw
                if pending is None:
                    pending = await driver.read_decrypted_ingress_v49d(
                        self._socket, timeout_seconds=timeout
                    )
                    if type(pending) is not PendingRawIngressV49:
                        raise LinuxSocketOwnerV4Error(
                            "exact driver returned unsupported V4.9D RAW ingress"
                        )
                    self._v49d_pending_raw = pending
                self.assert_same_owner(self._initial_snapshot)
                driver.assert_current()
                return pending
            except BaseException:
                self.abort()
                raise

    async def read_terminal_close_ingress_v49e(
        self, *, deadline_ns: int
    ) -> PendingRawIngressV49:
        """Wait for terminal ingress under one frozen BOOTTIME deadline.

        Only a driver-proven zero-observation timeout preserves this owner.
        Every TLS, output, socket-identity, or partial-progress ambiguity still
        aborts the exact session.
        """

        exact_deadline_ns = _require_owner_pre_mutation_deadline_v49e(
            owner=self,
            operation="TERMINAL_CLOSE_INGRESS",
            deadline_ns=deadline_ns,
        )
        try:
            async with self._io_lock:
                driver = self._assert_v49c_staged_io_bound()
                if (
                    self._v49c_active_prepared_wire is not None
                    or self._v49c_active_prepared_tls is not None
                    or self._v49c_active_prepared_tls_offset != 0
                ):
                    raise LinuxSocketOwnerV4Error(
                        "V4.9E terminal ingress cannot race an outbound artifact"
                    )
                try:
                    _require_owner_pre_mutation_deadline_v49e(
                        owner=self,
                        operation="TERMINAL_CLOSE_INGRESS",
                        deadline_ns=exact_deadline_ns,
                    )
                    pending = self._v49d_pending_raw
                    if pending is None:
                        pending = await driver.read_terminal_close_ingress_v49e(
                            self._socket,
                            deadline_ns=exact_deadline_ns,
                        )
                        if type(pending) is not PendingRawIngressV49:
                            raise LinuxSocketOwnerV4Error(
                                "exact driver returned unsupported terminal RAW ingress"
                            )
                        self._v49d_pending_raw = pending
                except PhysicalTlsWebSocketV49DeadlineExpiredNoObservation as exc:
                    if (
                        exc.operation != "TERMINAL_CLOSE_INGRESS"
                        or exc.deadline_ns != exact_deadline_ns
                    ):
                        raise LinuxSocketOwnerV4Error(
                            "driver terminal deadline evidence differs from owner input"
                        ) from exc
                    self.assert_same_owner(self._initial_snapshot)
                    driver.assert_current()
                    raise _owner_deadline_expired_no_observation_v49e(
                        owner=self,
                        operation="TERMINAL_CLOSE_INGRESS",
                        deadline_ns=exact_deadline_ns,
                    ) from exc
                except PhysicalTlsWebSocketV49DeadlineExpiredAfterProgress as exc:
                    owner_exc = self._bind_deadline_expired_after_progress_v49e(
                        driver=driver,
                        driver_exc=exc,
                        operation="TERMINAL_CLOSE_INGRESS",
                        deadline_ns=exact_deadline_ns,
                    )
                    raise owner_exc from exc
                self.assert_same_owner(self._initial_snapshot)
                driver.assert_current()
                return pending
        except (
            LinuxSocketOwnerV4DeadlineExpiredNoObservationV49E,
            LinuxSocketOwnerV4DeadlineExpiredAfterProgressV49E,
        ):
            raise
        except BaseException:
            self._latch_terminal_io_fault_for_projection_v49e()
            raise

    async def adopt_durable_ingress_v49d(
        self, raw: RawIngressCommitV4
    ) -> DurableIngressAdoptionV49D:
        """Adopt only the RAW batch whose exact identity the owner retains."""

        async with self._io_lock:
            try:
                driver = self._assert_v49c_staged_io_bound()
                pending = self._v49d_pending_raw
                if (
                    type(raw) is not RawIngressCommitV4
                    or pending is None
                    or raw.transport_session_id != self._v49b_bound_session_id
                    or raw.transport_subscription_policy_id
                    != driver.transport_policy.transport_subscription_policy_id
                    or raw.ingress_sequence != pending.ingress_sequence
                    or self._v49c_active_prepared_wire is not None
                    or self._v49c_active_prepared_tls is not None
                    or self._v49c_active_prepared_tls_offset != 0
                ):
                    raise LinuxSocketOwnerV4Error(
                        "V4.9D adoption differs from retained RAW/session authority"
                    )
                adopted = driver.adopt_durable_ingress_v49d(raw)
                if (
                    type(adopted) is not DurableIngressAdoptionV49D
                    or adopted.raw_ingress_commit_id != raw.raw_ingress_commit_id
                    or adopted.ingress_sequence != pending.ingress_sequence
                    or adopted.adopted_octets != pending.total_octets
                    or adopted.durable_buffer_octets
                    != driver.durable_ingress_buffer_octets_v49d
                ):
                    raise LinuxSocketOwnerV4Error(
                        "exact driver returned unsupported durable adoption"
                    )
                self.assert_same_owner(self._initial_snapshot)
                driver.assert_current()
                self._v49d_pending_raw = None
                return adopted
            except BaseException:
                self.abort()
                raise

    async def parse_next_durable_unit_v49d(
        self,
    ) -> ParsedDurableUnitV49D | None:
        """Parse at most one oldest durable frame/error under owner identity."""

        async with self._io_lock:
            try:
                driver = self._assert_v49c_staged_io_bound()
                if (
                    self._v49d_pending_raw is not None
                    or self._v49c_active_prepared_wire is not None
                    or self._v49c_active_prepared_tls is not None
                    or self._v49c_active_prepared_tls_offset != 0
                ):
                    raise LinuxSocketOwnerV4Error(
                        "V4.9D parser cannot bypass pending RAW or outbound state"
                    )
                parsed = driver.parse_next_durable_unit_v49d()
                if parsed is not None and (
                    type(parsed) is not ParsedDurableUnitV49D
                    or parsed.remaining_durable_octets
                    != driver.durable_ingress_buffer_octets_v49d
                ):
                    raise LinuxSocketOwnerV4Error(
                        "exact driver returned unsupported durable parser unit"
                    )
                self.assert_same_owner(self._initial_snapshot)
                driver.assert_current()
                return parsed
            except BaseException:
                self.abort()
                raise

    async def prepare_exact_text_wire_v49c(
        self, payload: bytes
    ) -> PreparedWebSocketWireV49C:
        """Prepare one exact TEXT wire under the retained owner and I/O lock.

        This sealed boundary exposes neither a socket nor a callback seam.  Any
        failure fences the owner because Sans-I/O frame preparation advances
        protocol state and must never be replayed through a replacement path.
        """

        async with self._io_lock:
            try:
                driver = self._assert_v49c_staged_io_bound()
                if type(payload) is not bytes or not payload:
                    raise LinuxSocketOwnerV4Error(
                        "V4.9C TEXT payload must be exact non-empty bytes"
                    )
                if (
                    self._v49c_active_prepared_wire is not None
                    or self._v49c_active_prepared_tls is not None
                    or self._v49c_active_prepared_tls_offset != 0
                ):
                    raise LinuxSocketOwnerV4Error(
                        "one V4.9C owner outbound artifact is already active"
                    )
                prepared = await driver.prepare_exact_text_wire_v49c(payload)
                if type(prepared) is not PreparedWebSocketWireV49C:
                    raise LinuxSocketOwnerV4Error(
                        "exact driver returned an unsupported staged wire artifact"
                    )
                self.assert_same_owner(self._initial_snapshot)
                driver.assert_current()
                self._v49c_active_prepared_wire = prepared
                self._v49c_active_prepared_wire_was_protocol_output = False
                return prepared
            except BaseException:
                self.abort()
                raise

    async def prepare_local_websocket_close_wire_v49e(
        self,
        *,
        deadline_ns: int,
    ) -> PreparedWebSocketWireV49C:
        """Prepare fixed normal WebSocket closure without TLS or socket I/O."""

        exact_deadline_ns = _require_owner_pre_mutation_deadline_v49e(
            owner=self,
            operation="LOCAL_WEBSOCKET_CLOSE_PREPARATION",
            deadline_ns=deadline_ns,
        )
        async with self._io_lock:
            try:
                driver = self._assert_v49c_staged_io_bound()
                if (
                    self._v49d_pending_raw is not None
                    or self._v49c_active_prepared_wire is not None
                    or self._v49c_active_prepared_tls is not None
                    or self._v49c_active_prepared_tls_offset != 0
                    or self._v49e_active_prepared_tls_control is not None
                    or self._v49e_active_prepared_tls_control_offset != 0
                    or self._v49e_completed_local_close is not None
                    or self._v49e_tcp_write_shutdown_token is not None
                    or self._v49e_tcp_write_shutdown_attempted
                ):
                    raise LinuxSocketOwnerV4Error(
                        "local WebSocket Close requires one idle retained owner FIFO"
                    )
                _require_owner_pre_mutation_deadline_v49e(
                    owner=self,
                    operation="LOCAL_WEBSOCKET_CLOSE_PREPARATION",
                    deadline_ns=exact_deadline_ns,
                )
                try:
                    prepared = await driver.prepare_local_websocket_close_wire_v49e(
                        deadline_ns=exact_deadline_ns
                    )
                except PhysicalTlsWebSocketV49DeadlineExpiredNoObservation as exc:
                    if (
                        exc.operation != "LOCAL_WEBSOCKET_CLOSE_PREPARATION"
                        or exc.deadline_ns != exact_deadline_ns
                    ):
                        raise LinuxSocketOwnerV4Error(
                            "driver local-Close deadline evidence differs from owner"
                        ) from exc
                    self.assert_same_owner(self._initial_snapshot)
                    driver.assert_current()
                    raise _owner_deadline_expired_no_observation_v49e(
                        owner=self,
                        operation="LOCAL_WEBSOCKET_CLOSE_PREPARATION",
                        deadline_ns=exact_deadline_ns,
                    ) from exc
                if (
                    type(prepared) is not PreparedWebSocketWireV49C
                    or prepared.logical_opcode != 0x8
                    or prepared.logical_payload_octets != 2
                    or prepared.logical_payload_sha256
                    != hashlib.sha256((1000).to_bytes(2, "big")).hexdigest()
                ):
                    raise LinuxSocketOwnerV4Error(
                        "exact driver returned unsupported local normal Close wire"
                    )
                self.assert_same_owner(self._initial_snapshot)
                driver.assert_current()
                self._v49c_active_prepared_wire = prepared
                self._v49c_active_prepared_wire_was_protocol_output = False
                return prepared
            except LinuxSocketOwnerV4DeadlineExpiredNoObservationV49E:
                raise
            except BaseException:
                self._latch_terminal_io_fault_for_projection_v49e()
                raise

    async def prepare_pending_protocol_output_wire_v49c(
        self, ordered_chunks: tuple[bytes, ...]
    ) -> PreparedWebSocketWireV49C:
        """Prepare the exact oldest automatic Pong/Close under owner authority."""

        automatic_close_candidate = (
            type(ordered_chunks) is tuple
            and len(ordered_chunks) == 1
            and type(ordered_chunks[0]) is bytes
            and bool(ordered_chunks[0])
            and ordered_chunks[0][0] & 0x0F == 0x8
        )
        async with self._io_lock:
            try:
                driver = self._assert_v49c_staged_io_bound()
                if (
                    type(ordered_chunks) is not tuple
                    or len(ordered_chunks) != 1
                    or type(ordered_chunks[0]) is not bytes
                    or not ordered_chunks[0]
                ):
                    raise LinuxSocketOwnerV4Error(
                        "V4.9C automatic output requires one exact non-empty chunk"
                    )
                if (
                    self._v49c_active_prepared_wire is not None
                    or self._v49c_active_prepared_tls is not None
                    or self._v49c_active_prepared_tls_offset != 0
                ):
                    raise LinuxSocketOwnerV4Error(
                        "one V4.9C owner outbound artifact is already active"
                    )
                prepared = await driver.prepare_pending_protocol_output_wire_v49c(
                    ordered_chunks
                )
                if type(prepared) is not PreparedWebSocketWireV49C:
                    raise LinuxSocketOwnerV4Error(
                        "exact driver returned an unsupported automatic wire artifact"
                    )
                self.assert_same_owner(self._initial_snapshot)
                driver.assert_current()
                self._v49c_active_prepared_wire = prepared
                self._v49c_active_prepared_wire_was_protocol_output = True
                return prepared
            except BaseException:
                if automatic_close_candidate:
                    self._latch_terminal_io_fault_for_projection_v49e()
                else:
                    self.abort()
                raise

    async def prepare_tls_ciphertext_v49c(
        self,
        prepared_wire: PreparedWebSocketWireV49C,
        *,
        deadline_ns: int | None = None,
    ) -> PreparedTlsCiphertextV49C:
        """Advance only the exact owner-retained wire into retained ciphertext."""

        exact_deadline_ns: int | None = None
        if deadline_ns is not None:
            exact_deadline_ns = _require_owner_pre_mutation_deadline_v49e(
                owner=self,
                operation="LOCAL_WEBSOCKET_CLOSE_TLS_PREPARATION",
                deadline_ns=deadline_ns,
            )
        async with self._io_lock:
            try:
                driver = self._assert_v49c_staged_io_bound()
                if (
                    type(prepared_wire) is not PreparedWebSocketWireV49C
                    or prepared_wire is not self._v49c_active_prepared_wire
                    or self._v49c_active_prepared_tls is not None
                    or self._v49c_active_prepared_tls_offset != 0
                ):
                    raise LinuxSocketOwnerV4Error(
                        "TLS preparation requires the exact owner-retained wire object"
                    )
                if exact_deadline_ns is not None:
                    _require_owner_pre_mutation_deadline_v49e(
                        owner=self,
                        operation="LOCAL_WEBSOCKET_CLOSE_TLS_PREPARATION",
                        deadline_ns=exact_deadline_ns,
                    )
                try:
                    prepared = await driver.prepare_tls_ciphertext_v49c(
                        prepared_wire,
                        deadline_ns=exact_deadline_ns,
                    )
                except PhysicalTlsWebSocketV49DeadlineExpiredNoObservation as exc:
                    if (
                        exact_deadline_ns is None
                        or exc.operation != "LOCAL_WEBSOCKET_CLOSE_TLS_PREPARATION"
                        or exc.deadline_ns != exact_deadline_ns
                    ):
                        raise LinuxSocketOwnerV4Error(
                            "driver TLS-prepare deadline evidence differs from owner"
                        ) from exc
                    self.assert_same_owner(self._initial_snapshot)
                    driver.assert_current()
                    raise _owner_deadline_expired_no_observation_v49e(
                        owner=self,
                        operation="LOCAL_WEBSOCKET_CLOSE_TLS_PREPARATION",
                        deadline_ns=exact_deadline_ns,
                    ) from exc
                if (
                    type(prepared) is not PreparedTlsCiphertextV49C
                    or prepared.prepared_wire is not prepared_wire
                    or prepared.outbound_sequence != prepared_wire.outbound_sequence
                ):
                    raise LinuxSocketOwnerV4Error(
                        "exact driver returned an unsupported staged TLS artifact"
                    )
                self.assert_same_owner(self._initial_snapshot)
                driver.assert_current()
                self._v49c_active_prepared_tls = prepared
                return prepared
            except LinuxSocketOwnerV4DeadlineExpiredNoObservationV49E:
                raise
            except BaseException:
                if exact_deadline_ns is not None or (
                    type(prepared_wire) is PreparedWebSocketWireV49C
                    and prepared_wire.logical_opcode == 0x8
                ):
                    self._latch_terminal_io_fault_for_projection_v49e()
                else:
                    self.abort()
                raise

    async def send_prepared_tls_ciphertext_once_v49c(
        self,
        exact_ciphertext_slice: bytes,
        *,
        prepared: PreparedTlsCiphertextV49C,
        deadline_ns: int,
    ) -> int:
        """Submit one exact retained ciphertext slice until one positive send.

        A positive return proves only local kernel acceptance.  The actor must
        durably append that exact positive result before invoking this owner
        again.  If that append fails or is cancelled, the enclosing runtime
        must immediately abort this owner; it must never replay the unresolved
        suffix.  This method itself aborts on every exceptional or cancelled
        exit, including any failure after a positive driver return.
        """

        try:
            async with self._io_lock:
                driver = self._assert_v49c_staged_io_bound()
                if (
                    type(prepared) is not PreparedTlsCiphertextV49C
                    or prepared is not self._v49c_active_prepared_tls
                    or prepared.prepared_wire is not self._v49c_active_prepared_wire
                ):
                    raise LinuxSocketOwnerV4Error(
                        "send requires the exact owner-retained TLS artifact object"
                    )
                if type(deadline_ns) is not int or deadline_ns < 0:
                    raise LinuxSocketOwnerV4Error(
                        "V4.9C send deadline must be an absolute integer"
                    )
                offset = self._v49c_active_prepared_tls_offset
                ciphertext = prepared.exact_ciphertext
                if (
                    type(exact_ciphertext_slice) is not bytes
                    or not exact_ciphertext_slice
                    or offset < 0
                    or offset >= len(ciphertext)
                    or len(exact_ciphertext_slice) > len(ciphertext) - offset
                    or exact_ciphertext_slice
                    != ciphertext[offset : offset + len(exact_ciphertext_slice)]
                ):
                    raise LinuxSocketOwnerV4Error(
                        "send slice is not the exact owner-retained ciphertext "
                        "suffix prefix"
                    )
                if deadline_ns <= self.monotonic_now_ns():
                    if prepared.prepared_wire.logical_opcode == 0x8:
                        raise _owner_deadline_expired_no_observation_v49e(
                            owner=self,
                            operation="WEBSOCKET_CLOSE_SEND_BEFORE_SYSCALL",
                            deadline_ns=deadline_ns,
                        )
                    raise TimeoutError(
                        "V4.9C staged send exceeded its absolute CLOCK_BOOTTIME "
                        "deadline"
                    )
                close_send_kind = (
                    "AUTOMATIC_WEBSOCKET_CLOSE"
                    if self._v49c_active_prepared_wire_was_protocol_output
                    else "LOCAL_WEBSOCKET_CLOSE"
                )
                try:
                    accepted = await driver.send_prepared_tls_ciphertext_once_v49c(
                        exact_ciphertext_slice,
                        owned_socket=self._socket,
                        prepared=prepared,
                        deadline_ns=deadline_ns,
                    )
                except PhysicalTlsWebSocketV49DeadlineExpiredNoObservation as exc:
                    if (
                        prepared.prepared_wire.logical_opcode != 0x8
                        or exc.operation != "WEBSOCKET_CLOSE_SEND_BEFORE_SYSCALL"
                        or exc.deadline_ns != deadline_ns
                    ):
                        raise LinuxSocketOwnerV4Error(
                            "driver Close-send deadline evidence differs from owner"
                        ) from exc
                    self.assert_same_owner(self._initial_snapshot)
                    driver.assert_current()
                    raise _owner_deadline_expired_no_observation_v49e(
                        owner=self,
                        operation="WEBSOCKET_CLOSE_SEND_BEFORE_SYSCALL",
                        deadline_ns=deadline_ns,
                    ) from exc
                except (
                    PhysicalTlsWebSocketV49SendDeadlineExpiredNoKernelAcceptance
                ) as exc:
                    owner_exc = self._bind_send_deadline_no_kernel_acceptance_v49e(
                        driver=driver,
                        driver_exc=exc,
                        send_kind=close_send_kind,
                        transport_sequence=prepared.outbound_sequence,
                        ciphertext_batch_sha256=prepared.ciphertext_batch_sha256,
                        ciphertext_octets=prepared.ciphertext_octets,
                        ciphertext_start_octet=offset,
                        exact_slice=exact_ciphertext_slice,
                        deadline_ns=deadline_ns,
                    )
                    raise owner_exc from exc
                if (
                    type(accepted) is not int
                    or accepted <= 0
                    or accepted > len(exact_ciphertext_slice)
                ):
                    raise LinuxSocketOwnerV4Error(
                        "exact driver returned an invalid positive send count"
                    )
                self.assert_same_owner(self._initial_snapshot)
                driver.assert_current()
                next_offset = offset + accepted
                if next_offset > prepared.ciphertext_octets:
                    raise LinuxSocketOwnerV4Error(
                        "positive send advanced beyond retained ciphertext"
                    )
                self._v49c_active_prepared_tls_offset = next_offset
                if next_offset == prepared.ciphertext_octets:
                    self._v49c_active_prepared_tls = None
                    self._v49c_active_prepared_wire = None
                    self._v49c_active_prepared_wire_was_protocol_output = False
                    self._v49c_active_prepared_tls_offset = 0
                return accepted
        except (
            LinuxSocketOwnerV4DeadlineExpiredNoObservationV49E,
            LinuxSocketOwnerV4SendDeadlineExpiredNoKernelAcceptanceV49E,
        ):
            raise
        except BaseException:
            if (
                type(prepared) is PreparedTlsCiphertextV49C
                and prepared.prepared_wire.logical_opcode == 0x8
            ):
                self._latch_terminal_io_fault_for_projection_v49e()
            else:
                self.abort()
            raise

    async def prepare_local_close_notify_v49e(
        self,
        *,
        deadline_ns: int,
    ) -> PreparedTlsControlCiphertextV49E:
        """Retain the exact local TLS alert under the owner I/O lock."""

        exact_deadline_ns = _require_owner_pre_mutation_deadline_v49e(
            owner=self,
            operation="LOCAL_TLS_CLOSE_NOTIFY_PREPARATION",
            deadline_ns=deadline_ns,
        )
        async with self._io_lock:
            try:
                driver = self._assert_v49c_staged_io_bound()
                if (
                    self._v49d_pending_raw is not None
                    or self._v49c_active_prepared_wire is not None
                    or self._v49c_active_prepared_tls is not None
                    or self._v49c_active_prepared_tls_offset != 0
                    or self._v49e_active_prepared_tls_control is not None
                    or self._v49e_active_prepared_tls_control_offset != 0
                    or self._v49e_completed_local_close is not None
                    or self._v49e_tcp_write_shutdown_token is not None
                    or self._v49e_tcp_write_shutdown_attempted
                ):
                    raise LinuxSocketOwnerV4Error(
                        "local TLS close requires one idle retained owner FIFO"
                    )
                _require_owner_pre_mutation_deadline_v49e(
                    owner=self,
                    operation="LOCAL_TLS_CLOSE_NOTIFY_PREPARATION",
                    deadline_ns=exact_deadline_ns,
                )
                try:
                    prepared = await driver.prepare_local_close_notify_v49e(
                        deadline_ns=exact_deadline_ns
                    )
                except PhysicalTlsWebSocketV49DeadlineExpiredNoObservation as exc:
                    if (
                        exc.operation != "LOCAL_TLS_CLOSE_NOTIFY_PREPARATION"
                        or exc.deadline_ns != exact_deadline_ns
                    ):
                        raise LinuxSocketOwnerV4Error(
                            "driver TLS-close deadline evidence differs from owner"
                        ) from exc
                    self.assert_same_owner(self._initial_snapshot)
                    driver.assert_current()
                    raise _owner_deadline_expired_no_observation_v49e(
                        owner=self,
                        operation="LOCAL_TLS_CLOSE_NOTIFY_PREPARATION",
                        deadline_ns=exact_deadline_ns,
                    ) from exc
                if (
                    type(prepared) is not PreparedTlsControlCiphertextV49E
                    or prepared.control_kind
                    is not TlsControlOutputKindV49E.LOCAL_CLOSE_NOTIFY
                ):
                    raise LinuxSocketOwnerV4Error(
                        "exact driver returned unsupported local TLS-close output"
                    )
                self.assert_same_owner(self._initial_snapshot)
                driver.assert_current()
                self._v49e_active_prepared_tls_control = prepared
                self._v49e_active_prepared_tls_control_offset = 0
                return prepared
            except LinuxSocketOwnerV4DeadlineExpiredNoObservationV49E:
                raise
            except BaseException:
                self._latch_terminal_io_fault_for_projection_v49e()
                raise

    async def prepare_opaque_post_handshake_response_v49e(
        self,
    ) -> PreparedTlsControlCiphertextV49E:
        """Retain explicitly admitted TLS output without guessing its subtype."""

        async with self._io_lock:
            try:
                driver = self._assert_v49c_staged_io_bound()
                if (
                    self._v49d_pending_raw is not None
                    or self._v49c_active_prepared_wire is not None
                    or self._v49c_active_prepared_tls is not None
                    or self._v49c_active_prepared_tls_offset != 0
                    or self._v49e_active_prepared_tls_control is not None
                    or self._v49e_active_prepared_tls_control_offset != 0
                    or self._v49e_tcp_write_shutdown_attempted
                ):
                    raise LinuxSocketOwnerV4Error(
                        "opaque TLS output requires one idle retained owner FIFO"
                    )
                prepared = await driver.prepare_opaque_post_handshake_response_v49e()
                if (
                    type(prepared) is not PreparedTlsControlCiphertextV49E
                    or prepared.control_kind
                    is not (TlsControlOutputKindV49E.OPAQUE_POST_HANDSHAKE_RESPONSE)
                ):
                    raise LinuxSocketOwnerV4Error(
                        "exact driver returned unsupported opaque TLS output"
                    )
                self.assert_same_owner(self._initial_snapshot)
                driver.assert_current()
                self._v49e_active_prepared_tls_control = prepared
                self._v49e_active_prepared_tls_control_offset = 0
                return prepared
            except BaseException:
                self._latch_terminal_io_fault_for_projection_v49e()
                raise

    async def prepare_pending_post_handshake_output_v49e(
        self,
    ) -> PreparedTlsControlCiphertextV49E:
        """Compatibility spelling for the same explicitly opaque operation."""

        return await self.prepare_opaque_post_handshake_response_v49e()

    async def send_prepared_tls_control_ciphertext_once_v49e(
        self,
        exact_ciphertext_slice: bytes,
        *,
        prepared: PreparedTlsControlCiphertextV49E,
        deadline_ns: int,
    ) -> int:
        """Submit one exact owner-retained TLS-control suffix prefix once."""

        try:
            async with self._io_lock:
                driver = self._assert_v49c_staged_io_bound()
                if (
                    type(prepared) is not PreparedTlsControlCiphertextV49E
                    or prepared is not self._v49e_active_prepared_tls_control
                ):
                    raise LinuxSocketOwnerV4Error(
                        "send requires the exact owner-retained TLS-control artifact"
                    )
                if type(deadline_ns) is not int or deadline_ns < 0:
                    raise LinuxSocketOwnerV4Error(
                        "V4.9E send deadline must be an absolute integer"
                    )
                offset = self._v49e_active_prepared_tls_control_offset
                ciphertext = prepared.exact_ciphertext
                if (
                    type(exact_ciphertext_slice) is not bytes
                    or not exact_ciphertext_slice
                    or offset < 0
                    or offset >= len(ciphertext)
                    or len(exact_ciphertext_slice) > len(ciphertext) - offset
                    or exact_ciphertext_slice
                    != ciphertext[offset : offset + len(exact_ciphertext_slice)]
                ):
                    raise LinuxSocketOwnerV4Error(
                        "TLS-control slice is not the retained suffix prefix"
                    )
                if deadline_ns <= self.monotonic_now_ns():
                    raise _owner_deadline_expired_no_observation_v49e(
                        owner=self,
                        operation="TLS_CONTROL_SEND_BEFORE_SYSCALL",
                        deadline_ns=deadline_ns,
                    )
                try:
                    accepted = (
                        await driver.send_prepared_tls_control_ciphertext_once_v49e(
                            exact_ciphertext_slice,
                            owned_socket=self._socket,
                            prepared=prepared,
                            deadline_ns=deadline_ns,
                        )
                    )
                except PhysicalTlsWebSocketV49DeadlineExpiredNoObservation as exc:
                    if (
                        exc.operation != "TLS_CONTROL_SEND_BEFORE_SYSCALL"
                        or exc.deadline_ns != deadline_ns
                    ):
                        raise LinuxSocketOwnerV4Error(
                            "driver TLS-control deadline evidence differs from owner"
                        ) from exc
                    self.assert_same_owner(self._initial_snapshot)
                    driver.assert_current()
                    raise _owner_deadline_expired_no_observation_v49e(
                        owner=self,
                        operation="TLS_CONTROL_SEND_BEFORE_SYSCALL",
                        deadline_ns=deadline_ns,
                    ) from exc
                except (
                    PhysicalTlsWebSocketV49SendDeadlineExpiredNoKernelAcceptance
                ) as exc:
                    owner_exc = self._bind_send_deadline_no_kernel_acceptance_v49e(
                        driver=driver,
                        driver_exc=exc,
                        send_kind="TLS_CONTROL",
                        transport_sequence=prepared.control_sequence,
                        ciphertext_batch_sha256=prepared.ciphertext_batch_sha256,
                        ciphertext_octets=prepared.ciphertext_octets,
                        ciphertext_start_octet=offset,
                        exact_slice=exact_ciphertext_slice,
                        deadline_ns=deadline_ns,
                    )
                    raise owner_exc from exc
                if (
                    type(accepted) is not int
                    or accepted <= 0
                    or accepted > len(exact_ciphertext_slice)
                ):
                    raise LinuxSocketOwnerV4Error(
                        "exact driver returned an invalid TLS-control send count"
                    )
                if (
                    offset + accepted == prepared.ciphertext_octets
                    and prepared.control_kind
                    is TlsControlOutputKindV49E.LOCAL_CLOSE_NOTIFY
                ):
                    self._assert_terminal_socket_owner_v49e()
                else:
                    self.assert_same_owner(self._initial_snapshot)
                driver.assert_current()
                next_offset = offset + accepted
                if next_offset > prepared.ciphertext_octets:
                    raise LinuxSocketOwnerV4Error(
                        "TLS-control send advanced beyond retained ciphertext"
                    )
                self._v49e_active_prepared_tls_control_offset = next_offset
                if next_offset == prepared.ciphertext_octets:
                    self._v49e_active_prepared_tls_control = None
                    self._v49e_active_prepared_tls_control_offset = 0
                    if (
                        prepared.control_kind
                        is TlsControlOutputKindV49E.LOCAL_CLOSE_NOTIFY
                    ):
                        self._v49e_completed_local_close = prepared
                        self._v49e_completed_local_close_values = tuple(
                            getattr(prepared, field)
                            for field in (
                                PreparedTlsControlCiphertextV49E.__dataclass_fields__
                            )
                        )
                return accepted
        except (
            LinuxSocketOwnerV4DeadlineExpiredNoObservationV49E,
            LinuxSocketOwnerV4SendDeadlineExpiredNoKernelAcceptanceV49E,
        ):
            raise
        except BaseException:
            self._latch_terminal_io_fault_for_projection_v49e()
            raise

    async def prepare_tcp_write_shutdown_v49e(
        self,
        prepared: PreparedTlsControlCiphertextV49E,
        *,
        deadline_ns: int,
    ) -> TcpWriteShutdownTokenV49E:
        """Mint one owner-local token after complete close-alert acceptance."""

        exact_deadline_ns = _require_owner_pre_mutation_deadline_v49e(
            owner=self,
            operation="TCP_WRITE_SHUTDOWN_TOKEN_PREPARATION",
            deadline_ns=deadline_ns,
        )
        async with self._io_lock:
            try:
                driver = self._assert_v49e_shutdown_io_bound()
                if (
                    type(prepared) is not PreparedTlsControlCiphertextV49E
                    or prepared is not self._v49e_completed_local_close
                    or tuple(
                        getattr(prepared, field)
                        for field in (
                            PreparedTlsControlCiphertextV49E.__dataclass_fields__
                        )
                    )
                    != self._v49e_completed_local_close_values
                    or prepared.control_kind
                    is not TlsControlOutputKindV49E.LOCAL_CLOSE_NOTIFY
                    or self._v49e_active_prepared_tls_control is not None
                    or self._v49e_active_prepared_tls_control_offset != 0
                    or self._v49e_tcp_write_shutdown_token is not None
                    or self._v49e_tcp_write_shutdown_attempted
                    or self._v49e_tcp_write_shutdown_result is not None
                    or driver.state is not TlsWebSocketDriverStateV49.TLS_SHUTDOWN_V49E
                ):
                    raise LinuxSocketOwnerV4Error(
                        "SHUT_WR token requires the exact completed local TLS close"
                    )
                session_id = self._v49b_bound_session_id
                if type(session_id) is not str or not session_id:
                    raise LinuxSocketOwnerV4Error(
                        "SHUT_WR token lacks a bound transport session"
                    )
                _require_owner_pre_mutation_deadline_v49e(
                    owner=self,
                    operation="TCP_WRITE_SHUTDOWN_TOKEN_PREPARATION",
                    deadline_ns=exact_deadline_ns,
                )
                sequence = self._v49e_tcp_write_shutdown_token_sequence + 1
                values = {
                    "domain": "RiskYieldMMTcpWriteShutdownTokenV4_9E",
                    "token_sequence": sequence,
                    "transport_session_id": session_id,
                    "tls_control_sequence": prepared.control_sequence,
                    "tls_ciphertext_batch_sha256": (prepared.ciphertext_batch_sha256),
                    "tls_ciphertext_octets": prepared.ciphertext_octets,
                    "shutdown_deadline_monotonic_ns": exact_deadline_ns,
                }
                token = TcpWriteShutdownTokenV49E(
                    _token=_V49E_TCP_WRITE_SHUTDOWN_TOKEN,
                    token_sequence=sequence,
                    transport_session_id=session_id,
                    tls_control_sequence=prepared.control_sequence,
                    tls_ciphertext_batch_sha256=(prepared.ciphertext_batch_sha256),
                    tls_ciphertext_octets=prepared.ciphertext_octets,
                    shutdown_deadline_monotonic_ns=exact_deadline_ns,
                    shutdown_token_id=sha256_digest(values),
                )
                self._assert_tcp_write_shutdown_token_integrity_v49e(token)
                self._assert_terminal_socket_owner_v49e()
                driver.assert_current()
                _register_owner_capability_v49e(
                    _token=_V49E_OWNER_CAPABILITY_REGISTRATION_TOKEN,
                    capability_kind="TCP_WRITE_SHUTDOWN_TOKEN",
                    capability_id=token.shutdown_token_id,
                    capability=token,
                )
                self._v49e_tcp_write_shutdown_token_sequence = sequence
                self._v49e_tcp_write_shutdown_token = token
                self._v49e_tcp_write_shutdown_token_values = tuple(
                    getattr(token, field)
                    for field in TcpWriteShutdownTokenV49E.__dataclass_fields__
                )
                return token
            except LinuxSocketOwnerV4DeadlineExpiredNoObservationV49E:
                raise
            except BaseException:
                self._latch_terminal_io_fault_for_projection_v49e()
                raise

    async def prepare_tcp_write_shutdown_token_v49e(
        self,
        prepared: PreparedTlsControlCiphertextV49E,
        *,
        deadline_ns: int,
    ) -> TcpWriteShutdownTokenV49E:
        return await self.prepare_tcp_write_shutdown_v49e(
            prepared,
            deadline_ns=deadline_ns,
        )

    @staticmethod
    def _assert_tcp_write_shutdown_token_integrity_v49e(
        token: TcpWriteShutdownTokenV49E,
    ) -> None:
        if type(token) is not TcpWriteShutdownTokenV49E:
            raise TypeError("token must be exact TcpWriteShutdownTokenV49E")
        if (
            type(token.token_sequence) is not int
            or token.token_sequence < 1
            or type(token.transport_session_id) is not str
            or re.fullmatch(r"[0-9a-f]{64}", token.transport_session_id) is None
            or type(token.tls_control_sequence) is not int
            or token.tls_control_sequence < 1
            or type(token.tls_ciphertext_batch_sha256) is not str
            or re.fullmatch(r"[0-9a-f]{64}", token.tls_ciphertext_batch_sha256) is None
            or type(token.tls_ciphertext_octets) is not int
            or token.tls_ciphertext_octets < 1
            or type(token.shutdown_deadline_monotonic_ns) is not int
            or token.shutdown_deadline_monotonic_ns < 1
        ):
            raise LinuxSocketOwnerV4Error(
                "TCP write-shutdown token has inconsistent exact fields"
            )
        values = {
            "domain": "RiskYieldMMTcpWriteShutdownTokenV4_9E",
            "token_sequence": token.token_sequence,
            "transport_session_id": token.transport_session_id,
            "tls_control_sequence": token.tls_control_sequence,
            "tls_ciphertext_batch_sha256": token.tls_ciphertext_batch_sha256,
            "tls_ciphertext_octets": token.tls_ciphertext_octets,
            "shutdown_deadline_monotonic_ns": (token.shutdown_deadline_monotonic_ns),
        }
        if token.shutdown_token_id != sha256_digest(values):
            raise LinuxSocketOwnerV4Error(
                "TCP write-shutdown token ID differs from its exact fields"
            )

    @staticmethod
    def _assert_tcp_write_shutdown_result_integrity_v49e(
        result: TcpWriteShutdownResultV49E,
    ) -> None:
        if type(result) is not TcpWriteShutdownResultV49E:
            raise TypeError("result must be exact TcpWriteShutdownResultV49E")
        LinuxSocketOwnerV4._assert_tcp_write_shutdown_token_integrity_v49e(
            result.shutdown_token
        )
        error_code = result.error_code
        if (
            result.shutdown_how != socket.SHUT_WR
            or type(result.kernel_accepted) is not bool
            or (
                error_code is not None
                and type(error_code) is not TcpWriteShutdownErrorCodeV49E
            )
            or result.kernel_accepted != (error_code is None)
        ):
            raise LinuxSocketOwnerV4Error(
                "TCP write-shutdown result has inconsistent exact fields"
            )
        values = {
            "domain": "RiskYieldMMTcpWriteShutdownResultV4_9E",
            "shutdown_token_id": result.shutdown_token.shutdown_token_id,
            "shutdown_how": socket.SHUT_WR,
            "kernel_accepted": result.kernel_accepted,
            "error_code": None if error_code is None else error_code.value,
        }
        if result.shutdown_result_id != sha256_digest(values):
            raise LinuxSocketOwnerV4Error(
                "TCP write-shutdown result ID differs from its exact fields"
            )

    @staticmethod
    def _canonical_tcp_write_shutdown_error_code_v49e(
        exc: OSError,
    ) -> TcpWriteShutdownErrorCodeV49E:
        codes = {
            errno.EBADF: TcpWriteShutdownErrorCodeV49E.BAD_FILE_DESCRIPTOR,
            errno.EINVAL: TcpWriteShutdownErrorCodeV49E.INVALID_SHUTDOWN_MODE,
            errno.ENOTCONN: TcpWriteShutdownErrorCodeV49E.NOT_CONNECTED,
            errno.ENOTSOCK: TcpWriteShutdownErrorCodeV49E.NOT_A_SOCKET,
        }
        if type(exc.errno) is not int or exc.errno not in codes:
            raise LinuxSocketOwnerV4Error(
                "socket.shutdown returned an unreviewed or ambiguous OS error"
            ) from exc
        return codes[exc.errno]

    async def shutdown_tcp_write_v49e(
        self,
        token: TcpWriteShutdownTokenV49E,
        *,
        deadline_ns: int,
    ) -> TcpWriteShutdownResultV49E:
        """Invoke exactly one ``socket.shutdown(SHUT_WR)`` for the exact token."""

        try:
            async with self._io_lock:
                driver = self._assert_v49e_shutdown_io_bound()
                if (
                    type(token) is not TcpWriteShutdownTokenV49E
                    or token is not self._v49e_tcp_write_shutdown_token
                    or tuple(
                        getattr(token, field)
                        for field in TcpWriteShutdownTokenV49E.__dataclass_fields__
                    )
                    != self._v49e_tcp_write_shutdown_token_values
                    or self._v49e_tcp_write_shutdown_attempted
                    or self._v49e_tcp_write_shutdown_result is not None
                    or self._v49e_completed_local_close is None
                    or type(deadline_ns) is not int
                    or deadline_ns < 1
                    or token.shutdown_deadline_monotonic_ns != deadline_ns
                ):
                    raise LinuxSocketOwnerV4Error(
                        "SHUT_WR requires the exact unconsumed owner token"
                    )
                prepared = self._v49e_completed_local_close
                if (
                    token.transport_session_id != self._v49b_bound_session_id
                    or token.tls_control_sequence != prepared.control_sequence
                    or token.tls_ciphertext_batch_sha256
                    != prepared.ciphertext_batch_sha256
                    or token.tls_ciphertext_octets != prepared.ciphertext_octets
                ):
                    raise LinuxSocketOwnerV4Error(
                        "SHUT_WR token differs from retained TLS-close evidence"
                    )
                self._assert_tcp_write_shutdown_token_integrity_v49e(token)
                self._assert_terminal_socket_owner_v49e()
                driver.assert_current()
                # Mark before the syscall.  Reviewed Linux errno returns are
                # conclusive negative results; all other exceptional exits are
                # treated as ambiguous and the token can never be retried.
                self._v49e_tcp_write_shutdown_attempted = True
                error_code: TcpWriteShutdownErrorCodeV49E | None = None
                if _boottime_ns() >= deadline_ns:
                    error_code = (
                        TcpWriteShutdownErrorCodeV49E.DEADLINE_EXPIRED_BEFORE_SYSCALL
                    )
                    returned = None
                else:
                    try:
                        returned = self._socket.shutdown(socket.SHUT_WR)
                    except OSError as exc:
                        error_code = self._canonical_tcp_write_shutdown_error_code_v49e(
                            exc
                        )
                        returned = None
                    else:
                        if returned is not None:
                            raise LinuxSocketOwnerV4Error(
                                "socket.shutdown returned an unsupported result"
                            )
                # The syscall boundary must not turn a concurrent descriptor
                # replacement into authority for this retained session.  Re-prove
                # both the Linux socket owner and exact driver after success or a
                # reviewed conclusive errno, before minting any durable result.
                # Failure here is ambiguous: the one-shot token remains consumed
                # by ``_v49e_tcp_write_shutdown_attempted`` and the outer handler
                # retains projection-only authority for terminal classification.
                self._assert_terminal_socket_owner_v49e()
                driver.assert_current()
                kernel_accepted = error_code is None
                result_values = {
                    "domain": "RiskYieldMMTcpWriteShutdownResultV4_9E",
                    "shutdown_token_id": token.shutdown_token_id,
                    "shutdown_how": socket.SHUT_WR,
                    "kernel_accepted": kernel_accepted,
                    "error_code": (None if error_code is None else error_code.value),
                }
                result = TcpWriteShutdownResultV49E(
                    _token=_V49E_TCP_WRITE_SHUTDOWN_RESULT_TOKEN,
                    shutdown_token=token,
                    shutdown_how=socket.SHUT_WR,
                    kernel_accepted=kernel_accepted,
                    error_code=error_code,
                    shutdown_result_id=sha256_digest(result_values),
                )
                self._assert_tcp_write_shutdown_result_integrity_v49e(result)
                _discard_owner_capability_v49e(
                    capability_kind="TCP_WRITE_SHUTDOWN_TOKEN",
                    capability_id=token.shutdown_token_id,
                    capability=token,
                )
                _register_owner_capability_v49e(
                    _token=_V49E_OWNER_CAPABILITY_REGISTRATION_TOKEN,
                    capability_kind="TCP_WRITE_SHUTDOWN_RESULT",
                    capability_id=result.shutdown_result_id,
                    capability=result,
                )
                self._v49e_tcp_write_shutdown_token = None
                self._v49e_tcp_write_shutdown_token_values = None
                self._v49e_tcp_write_shutdown_result = result
                if not kernel_accepted:
                    self._v49e_terminal_io_fault_latched = True
                return result
        except BaseException:
            self._latch_terminal_io_fault_for_projection_v49e()
            raise

    async def shutdown_tcp_write_once_v49e(
        self,
        token: TcpWriteShutdownTokenV49E,
        *,
        deadline_ns: int,
    ) -> TcpWriteShutdownResultV49E:
        return await self.shutdown_tcp_write_v49e(
            token,
            deadline_ns=deadline_ns,
        )

    @staticmethod
    def _assert_owner_unsendable_tls_output_integrity_v49e(
        evidence: OwnerUnsendableTlsPostHandshakeOutputV49E,
    ) -> None:
        if type(evidence) is not OwnerUnsendableTlsPostHandshakeOutputV49E:
            raise TypeError(
                "evidence must be exact OwnerUnsendableTlsPostHandshakeOutputV49E"
            )
        driver_evidence = evidence.driver_evidence
        ExactTlsWebSocketDriverV49._assert_unsendable_tls_output_integrity_v49e(
            driver_evidence
        )
        if (
            type(evidence.transport_session_id) is not str
            or re.fullmatch(r"[0-9a-f]{64}", evidence.transport_session_id) is None
            or type(evidence.kernel_socket_identity) is not str
            or re.fullmatch(r"[0-9a-f]{64}", evidence.kernel_socket_identity) is None
        ):
            raise LinuxSocketOwnerV4Error(
                "owner unsendable TLS output lacks exact authority identities"
            )
        values = {
            "domain": "RiskYieldMMOwnerUnsendableTlsPostHandshakeOutputV4_9E",
            "transport_session_id": evidence.transport_session_id,
            "kernel_socket_identity": evidence.kernel_socket_identity,
            "driver_unsendable_output_id": driver_evidence.unsendable_output_id,
            "driver_output_sequence": driver_evidence.output_sequence,
            "driver_evidence_nonce_sha256": (
                driver_evidence.driver_evidence_nonce_sha256
            ),
            "ciphertext_sha256": driver_evidence.ciphertext_sha256,
            "ciphertext_octets": driver_evidence.ciphertext_octets,
        }
        if (
            evidence.owner_unsendable_output_id != sha256_digest(values)
            or evidence.owner_unsendable_output_id
            == driver_evidence.unsendable_output_id
        ):
            raise LinuxSocketOwnerV4Error(
                "owner unsendable TLS-output ID differs from its exact fields"
            )

    def _bind_unsendable_tls_output_v49e(
        self,
        *,
        driver: ExactTlsWebSocketDriverV49,
        driver_evidence: UnsendableTlsPostHandshakeOutputV49E,
    ) -> OwnerUnsendableTlsPostHandshakeOutputV49E:
        """Bind only the exact just-drained driver evidence to this owner."""

        driver._assert_active_unsendable_tls_output_v49e(driver_evidence)
        self._assert_terminal_socket_owner_v49e()
        driver.assert_current()
        transition = self._v49b_transition
        session_id = self._v49b_bound_session_id
        if (
            type(transition) is not DriverHandshakeTransitionV49B
            or type(session_id) is not str
            or not session_id
            or driver_evidence.driver_evidence_nonce_sha256
            != transition.evidence.evidence_nonce_sha256
        ):
            raise LinuxSocketOwnerV4Error(
                "unsendable TLS output differs from retained session evidence"
            )
        kernel_socket_identity = self._initial_snapshot.kernel_socket_identity
        values = {
            "domain": "RiskYieldMMOwnerUnsendableTlsPostHandshakeOutputV4_9E",
            "transport_session_id": session_id,
            "kernel_socket_identity": kernel_socket_identity,
            "driver_unsendable_output_id": driver_evidence.unsendable_output_id,
            "driver_output_sequence": driver_evidence.output_sequence,
            "driver_evidence_nonce_sha256": (
                driver_evidence.driver_evidence_nonce_sha256
            ),
            "ciphertext_sha256": driver_evidence.ciphertext_sha256,
            "ciphertext_octets": driver_evidence.ciphertext_octets,
        }
        evidence = OwnerUnsendableTlsPostHandshakeOutputV49E(
            _token=_V49E_OWNER_UNSENDABLE_TLS_OUTPUT_TOKEN,
            transport_session_id=session_id,
            kernel_socket_identity=kernel_socket_identity,
            driver_evidence=driver_evidence,
            owner_unsendable_output_id=sha256_digest(values),
        )
        self._assert_owner_unsendable_tls_output_integrity_v49e(evidence)
        _register_owner_capability_v49e(
            _token=_V49E_OWNER_CAPABILITY_REGISTRATION_TOKEN,
            capability_kind="UNSENDABLE_TLS_OUTPUT_EVIDENCE",
            capability_id=evidence.owner_unsendable_output_id,
            capability=evidence,
        )
        return evidence

    @staticmethod
    def _assert_owner_tls_shutdown_observation_integrity_v49e(
        observation: OwnerTlsShutdownObservationV49E,
    ) -> None:
        if type(observation) is not OwnerTlsShutdownObservationV49E:
            raise TypeError("observation must be exact OwnerTlsShutdownObservationV49E")
        driver_observation = observation.driver_observation
        ExactTlsWebSocketDriverV49._assert_tls_shutdown_observation_integrity_v49e(
            driver_observation
        )
        if (
            type(observation.transport_session_id) is not str
            or re.fullmatch(r"[0-9a-f]{64}", observation.transport_session_id) is None
            or type(observation.kernel_socket_identity) is not str
            or re.fullmatch(r"[0-9a-f]{64}", observation.kernel_socket_identity) is None
        ):
            raise LinuxSocketOwnerV4Error(
                "owner TLS shutdown observation lacks exact authority identities"
            )
        values = {
            "domain": "RiskYieldMMOwnerTlsShutdownObservationV4_9E",
            "transport_session_id": observation.transport_session_id,
            "kernel_socket_identity": observation.kernel_socket_identity,
            "driver_observation_id": driver_observation.observation_id,
            "driver_observation_sequence": (driver_observation.observation_sequence),
            "driver_observation_kind": driver_observation.observation_kind.value,
        }
        if (
            observation.owner_observation_id != sha256_digest(values)
            or observation.owner_observation_id == driver_observation.observation_id
        ):
            raise LinuxSocketOwnerV4Error(
                "owner TLS shutdown observation ID differs from its exact fields"
            )

    @staticmethod
    def _assert_deadline_expired_no_observation_integrity_v49e(
        exc: LinuxSocketOwnerV4DeadlineExpiredNoObservationV49E,
    ) -> None:
        if type(exc) is not LinuxSocketOwnerV4DeadlineExpiredNoObservationV49E:
            raise TypeError(
                "exc must be exact LinuxSocketOwnerV4DeadlineExpiredNoObservationV49E"
            )
        if (
            type(exc.transport_session_id) is not str
            or re.fullmatch(r"[0-9a-f]{64}", exc.transport_session_id) is None
            or type(exc.kernel_socket_identity) is not str
            or re.fullmatch(r"[0-9a-f]{64}", exc.kernel_socket_identity) is None
            or type(exc.driver_evidence_nonce_sha256) is not str
            or re.fullmatch(r"[0-9a-f]{64}", exc.driver_evidence_nonce_sha256) is None
            or type(exc.operation) is not str
            or exc.operation not in _V49E_DEADLINE_OPERATIONS
            or type(exc.deadline_ns) is not int
            or exc.deadline_ns < 1
        ):
            raise LinuxSocketOwnerV4Error(
                "owner no-observation deadline evidence has invalid exact fields"
            )
        values = {
            "domain": "RiskYieldMMOwnerDeadlineExpiredNoObservationV4_9E",
            "transport_session_id": exc.transport_session_id,
            "kernel_socket_identity": exc.kernel_socket_identity,
            "driver_evidence_nonce_sha256": exc.driver_evidence_nonce_sha256,
            "operation": exc.operation,
            "deadline_ns": exc.deadline_ns,
        }
        if exc.owner_evidence_id != sha256_digest(values):
            raise LinuxSocketOwnerV4Error(
                "owner no-observation deadline evidence ID differs from fields"
            )

    def _bind_deadline_expired_no_observation_v49e(
        self,
        *,
        operation: str,
        deadline_ns: int,
    ) -> LinuxSocketOwnerV4DeadlineExpiredNoObservationV49E:
        """Mint one exact terminal authority and permanently fence owner I/O."""

        if self._v49e_terminal_io_fault_latched:
            raise LinuxSocketOwnerV4Error(
                "terminal no-observation authority was already projected"
            )
        if (
            type(operation) is not str
            or operation not in _V49E_DEADLINE_OPERATIONS
            or type(deadline_ns) is not int
            or deadline_ns < 1
        ):
            raise LinuxSocketOwnerV4Error(
                "no-observation deadline evidence has invalid operation or deadline"
            )
        self.assert_same_owner(self._initial_snapshot)
        driver = self._driver
        transition = self._v49b_transition
        session_id = self._v49b_bound_session_id
        if (
            type(driver) is not ExactTlsWebSocketDriverV49
            or type(transition) is not DriverHandshakeTransitionV49B
            or not self._v49b_evidence_bound
            or type(session_id) is not str
            or re.fullmatch(r"[0-9a-f]{64}", session_id) is None
        ):
            raise LinuxSocketOwnerV4Error(
                "no-observation deadline lacks retained session/driver authority"
            )
        driver.assert_current()
        values = {
            "domain": "RiskYieldMMOwnerDeadlineExpiredNoObservationV4_9E",
            "transport_session_id": session_id,
            "kernel_socket_identity": self._initial_snapshot.kernel_socket_identity,
            "driver_evidence_nonce_sha256": (transition.evidence.evidence_nonce_sha256),
            "operation": operation,
            "deadline_ns": deadline_ns,
        }
        owner_exc = LinuxSocketOwnerV4DeadlineExpiredNoObservationV49E(
            _token=_V49E_OWNER_DEADLINE_EXPIRED_NO_OBSERVATION_TOKEN,
            transport_session_id=session_id,
            kernel_socket_identity=self._initial_snapshot.kernel_socket_identity,
            driver_evidence_nonce_sha256=(transition.evidence.evidence_nonce_sha256),
            operation=operation,
            deadline_ns=deadline_ns,
            owner_evidence_id=sha256_digest(values),
        )
        self._assert_deadline_expired_no_observation_integrity_v49e(owner_exc)
        _register_owner_capability_v49e(
            _token=_V49E_OWNER_CAPABILITY_REGISTRATION_TOKEN,
            capability_kind="DEADLINE_EXPIRED_NO_OBSERVATION",
            capability_id=owner_exc.owner_evidence_id,
            capability=owner_exc,
        )
        self._v49e_terminal_io_fault_latched = True
        return owner_exc

    @staticmethod
    def _assert_deadline_expired_after_progress_integrity_v49e(
        exc: LinuxSocketOwnerV4DeadlineExpiredAfterProgressV49E,
    ) -> None:
        if type(exc) is not LinuxSocketOwnerV4DeadlineExpiredAfterProgressV49E:
            raise TypeError(
                "exc must be exact LinuxSocketOwnerV4DeadlineExpiredAfterProgressV49E"
            )
        if (
            type(exc.transport_session_id) is not str
            or re.fullmatch(r"[0-9a-f]{64}", exc.transport_session_id) is None
            or type(exc.kernel_socket_identity) is not str
            or re.fullmatch(r"[0-9a-f]{64}", exc.kernel_socket_identity) is None
            or type(exc.driver_evidence_nonce_sha256) is not str
            or re.fullmatch(r"[0-9a-f]{64}", exc.driver_evidence_nonce_sha256) is None
            or exc.operation not in {"TERMINAL_CLOSE_INGRESS", "TLS_SHUTDOWN_POLL"}
            or type(exc.deadline_ns) is not int
            or exc.deadline_ns < 1
            or type(exc.ciphertext_octets_received) is not int
            or not 1
            <= exc.ciphertext_octets_received
            <= V49_MAXIMUM_TLS_OPERATION_CIPHERTEXT_BYTES
            or type(exc.ciphertext_sha256) is not str
            or re.fullmatch(r"[0-9a-f]{64}", exc.ciphertext_sha256) is None
            or type(exc.driver_evidence_id) is not str
            or re.fullmatch(r"[0-9a-f]{64}", exc.driver_evidence_id) is None
        ):
            raise LinuxSocketOwnerV4Error(
                "owner partial-progress deadline evidence has invalid fields"
            )
        values = {
            "domain": "RiskYieldMMOwnerDeadlineExpiredAfterProgressV4_9E",
            "transport_session_id": exc.transport_session_id,
            "kernel_socket_identity": exc.kernel_socket_identity,
            "driver_evidence_nonce_sha256": exc.driver_evidence_nonce_sha256,
            "operation": exc.operation,
            "deadline_ns": exc.deadline_ns,
            "ciphertext_octets_received": exc.ciphertext_octets_received,
            "ciphertext_sha256": exc.ciphertext_sha256,
            "driver_evidence_id": exc.driver_evidence_id,
        }
        if exc.owner_evidence_id != sha256_digest(values):
            raise LinuxSocketOwnerV4Error(
                "owner partial-progress deadline evidence ID differs from fields"
            )

    def _bind_deadline_expired_after_progress_v49e(
        self,
        *,
        driver: ExactTlsWebSocketDriverV49,
        driver_exc: PhysicalTlsWebSocketV49DeadlineExpiredAfterProgress,
        operation: str,
        deadline_ns: int,
    ) -> LinuxSocketOwnerV4DeadlineExpiredAfterProgressV49E:
        driver._assert_deadline_expired_after_progress_integrity_v49e(  # noqa: SLF001
            driver_exc
        )
        transition = self._v49b_transition
        session_id = self._v49b_bound_session_id
        if (
            type(transition) is not DriverHandshakeTransitionV49B
            or type(session_id) is not str
            or not session_id
            or driver_exc.driver_evidence_nonce_sha256
            != transition.evidence.evidence_nonce_sha256
            or driver_exc.operation != operation
            or driver_exc.deadline_ns != deadline_ns
        ):
            raise LinuxSocketOwnerV4Error(
                "partial deadline evidence differs from retained owner authority"
            )
        if operation == "TLS_SHUTDOWN_POLL":
            self._assert_terminal_socket_owner_v49e()
        elif operation == "TERMINAL_CLOSE_INGRESS":
            self.assert_same_owner(self._initial_snapshot)
        else:
            raise LinuxSocketOwnerV4Error(
                "partial deadline operation is outside terminal authority"
            )
        kernel_socket_identity = self._initial_snapshot.kernel_socket_identity
        values = {
            "domain": "RiskYieldMMOwnerDeadlineExpiredAfterProgressV4_9E",
            "transport_session_id": session_id,
            "kernel_socket_identity": kernel_socket_identity,
            "driver_evidence_nonce_sha256": (driver_exc.driver_evidence_nonce_sha256),
            "operation": operation,
            "deadline_ns": deadline_ns,
            "ciphertext_octets_received": (driver_exc.ciphertext_octets_received),
            "ciphertext_sha256": driver_exc.ciphertext_sha256,
            "driver_evidence_id": driver_exc.evidence_id,
        }
        owner_exc = LinuxSocketOwnerV4DeadlineExpiredAfterProgressV49E(
            _token=_V49E_OWNER_DEADLINE_EXPIRED_AFTER_PROGRESS_TOKEN,
            transport_session_id=session_id,
            kernel_socket_identity=kernel_socket_identity,
            driver_evidence_nonce_sha256=(driver_exc.driver_evidence_nonce_sha256),
            operation=operation,
            deadline_ns=deadline_ns,
            ciphertext_octets_received=(driver_exc.ciphertext_octets_received),
            ciphertext_sha256=driver_exc.ciphertext_sha256,
            driver_evidence_id=driver_exc.evidence_id,
            owner_evidence_id=sha256_digest(values),
        )
        self._assert_deadline_expired_after_progress_integrity_v49e(owner_exc)
        _register_owner_capability_v49e(
            _token=_V49E_OWNER_CAPABILITY_REGISTRATION_TOKEN,
            capability_kind="DEADLINE_EXPIRED_AFTER_PROGRESS",
            capability_id=owner_exc.owner_evidence_id,
            capability=owner_exc,
        )
        self._v49e_terminal_io_fault_latched = True
        return owner_exc

    @staticmethod
    def _assert_send_deadline_no_kernel_acceptance_integrity_v49e(
        exc: LinuxSocketOwnerV4SendDeadlineExpiredNoKernelAcceptanceV49E,
    ) -> None:
        if type(exc) is not LinuxSocketOwnerV4SendDeadlineExpiredNoKernelAcceptanceV49E:
            raise TypeError(
                "exc must be exact "
                "LinuxSocketOwnerV4SendDeadlineExpiredNoKernelAcceptanceV49E"
            )
        if (
            type(exc.transport_session_id) is not str
            or re.fullmatch(r"[0-9a-f]{64}", exc.transport_session_id) is None
            or type(exc.kernel_socket_identity) is not str
            or re.fullmatch(r"[0-9a-f]{64}", exc.kernel_socket_identity) is None
            or type(exc.driver_evidence_nonce_sha256) is not str
            or re.fullmatch(r"[0-9a-f]{64}", exc.driver_evidence_nonce_sha256) is None
            or exc.send_kind
            not in {
                "LOCAL_WEBSOCKET_CLOSE",
                "AUTOMATIC_WEBSOCKET_CLOSE",
                "TLS_CONTROL",
            }
            or type(exc.transport_sequence) is not int
            or exc.transport_sequence < 1
            or type(exc.ciphertext_batch_sha256) is not str
            or re.fullmatch(r"[0-9a-f]{64}", exc.ciphertext_batch_sha256) is None
            or type(exc.ciphertext_octets) is not int
            or exc.ciphertext_octets < 1
            or type(exc.ciphertext_start_octet) is not int
            or not 0 <= exc.ciphertext_start_octet < exc.ciphertext_octets
            or type(exc.requested_octets) is not int
            or not 1
            <= exc.requested_octets
            <= exc.ciphertext_octets - exc.ciphertext_start_octet
            or type(exc.exact_slice_sha256) is not str
            or re.fullmatch(r"[0-9a-f]{64}", exc.exact_slice_sha256) is None
            or type(exc.deadline_ns) is not int
            or exc.deadline_ns < 1
            or type(exc.would_block_count) is not int
            or not 1 <= exc.would_block_count <= 65_536
            or type(exc.driver_evidence_id) is not str
            or re.fullmatch(r"[0-9a-f]{64}", exc.driver_evidence_id) is None
        ):
            raise LinuxSocketOwnerV4Error(
                "owner send-deadline evidence has invalid exact fields"
            )
        values = {
            "domain": "RiskYieldMMOwnerTlsSendDeadlineNoKernelAcceptanceV4_9E",
            "transport_session_id": exc.transport_session_id,
            "kernel_socket_identity": exc.kernel_socket_identity,
            "driver_evidence_nonce_sha256": exc.driver_evidence_nonce_sha256,
            "send_kind": exc.send_kind,
            "transport_sequence": exc.transport_sequence,
            "ciphertext_batch_sha256": exc.ciphertext_batch_sha256,
            "ciphertext_octets": exc.ciphertext_octets,
            "ciphertext_start_octet": exc.ciphertext_start_octet,
            "requested_octets": exc.requested_octets,
            "exact_slice_sha256": exc.exact_slice_sha256,
            "deadline_ns": exc.deadline_ns,
            "would_block_count": exc.would_block_count,
            "driver_evidence_id": exc.driver_evidence_id,
        }
        if exc.owner_evidence_id != sha256_digest(values):
            raise LinuxSocketOwnerV4Error(
                "owner send-deadline evidence ID differs from exact fields"
            )

    def _bind_send_deadline_no_kernel_acceptance_v49e(
        self,
        *,
        driver: ExactTlsWebSocketDriverV49,
        driver_exc: PhysicalTlsWebSocketV49SendDeadlineExpiredNoKernelAcceptance,
        send_kind: str,
        transport_sequence: int,
        ciphertext_batch_sha256: str,
        ciphertext_octets: int,
        ciphertext_start_octet: int,
        exact_slice: bytes,
        deadline_ns: int,
    ) -> LinuxSocketOwnerV4SendDeadlineExpiredNoKernelAcceptanceV49E:
        driver._assert_send_deadline_no_kernel_acceptance_integrity_v49e(  # noqa: SLF001
            driver_exc
        )
        transition = self._v49b_transition
        session_id = self._v49b_bound_session_id
        if (
            transition is None
            or type(session_id) is not str
            or not session_id
            or driver_exc.driver_evidence_nonce_sha256
            != transition.evidence.evidence_nonce_sha256
            or driver_exc.send_kind != send_kind
            or driver_exc.transport_sequence != transport_sequence
            or driver_exc.ciphertext_batch_sha256 != ciphertext_batch_sha256
            or driver_exc.ciphertext_octets != ciphertext_octets
            or driver_exc.ciphertext_start_octet != ciphertext_start_octet
            or driver_exc.requested_octets != len(exact_slice)
            or driver_exc.exact_slice_sha256 != hashlib.sha256(exact_slice).hexdigest()
            or driver_exc.deadline_ns != deadline_ns
        ):
            raise LinuxSocketOwnerV4Error(
                "driver send-deadline evidence differs from owner authority"
            )
        self.assert_same_owner(self._initial_snapshot)
        driver.assert_current()
        kernel_socket_identity = self._initial_snapshot.kernel_socket_identity
        values = {
            "domain": "RiskYieldMMOwnerTlsSendDeadlineNoKernelAcceptanceV4_9E",
            "transport_session_id": session_id,
            "kernel_socket_identity": kernel_socket_identity,
            "driver_evidence_nonce_sha256": (driver_exc.driver_evidence_nonce_sha256),
            "send_kind": send_kind,
            "transport_sequence": transport_sequence,
            "ciphertext_batch_sha256": ciphertext_batch_sha256,
            "ciphertext_octets": ciphertext_octets,
            "ciphertext_start_octet": ciphertext_start_octet,
            "requested_octets": len(exact_slice),
            "exact_slice_sha256": hashlib.sha256(exact_slice).hexdigest(),
            "deadline_ns": deadline_ns,
            "would_block_count": driver_exc.would_block_count,
            "driver_evidence_id": driver_exc.evidence_id,
        }
        owner_exc = LinuxSocketOwnerV4SendDeadlineExpiredNoKernelAcceptanceV49E(
            _token=_V49E_OWNER_SEND_DEADLINE_NO_KERNEL_ACCEPTANCE_TOKEN,
            **values,
            owner_evidence_id=sha256_digest(values),
        )
        self._assert_send_deadline_no_kernel_acceptance_integrity_v49e(owner_exc)
        _register_owner_capability_v49e(
            _token=_V49E_OWNER_CAPABILITY_REGISTRATION_TOKEN,
            capability_kind="SEND_DEADLINE_NO_KERNEL_ACCEPTANCE",
            capability_id=owner_exc.owner_evidence_id,
            capability=owner_exc,
        )
        self._v49e_terminal_io_fault_latched = True
        return owner_exc

    async def poll_tls_shutdown_v49e(
        self,
        *,
        timeout_seconds: int | None = None,
        deadline_ns: int | None = None,
    ) -> OwnerTlsShutdownObservationV49E:
        """Poll shutdown and return a session/socket-bound sealed capability."""

        if (timeout_seconds is None) == (deadline_ns is None):
            raise TypeError("exactly one of timeout_seconds or deadline_ns is required")
        if deadline_ns is None:
            timeout = canonical_safe_int(
                timeout_seconds,
                field="timeout_seconds",
                minimum=1,
                maximum=300,
            )
            exact_deadline_ns: int | None = None
        else:
            timeout = None
            exact_deadline_ns = _require_owner_pre_mutation_deadline_v49e(
                owner=self,
                operation="TLS_SHUTDOWN_POLL",
                deadline_ns=deadline_ns,
            )
        try:
            async with self._io_lock:
                driver = self._assert_v49e_shutdown_io_bound()
                if (
                    type(self._v49e_tcp_write_shutdown_result)
                    is not TcpWriteShutdownResultV49E
                    or not self._v49e_tcp_write_shutdown_attempted
                    or not self._v49e_tcp_write_shutdown_result.kernel_accepted
                ):
                    raise LinuxSocketOwnerV4Error(
                        "TLS shutdown polling requires successful owner SHUT_WR"
                    )
                try:
                    if exact_deadline_ns is None:
                        assert timeout is not None
                        observation = await driver.poll_tls_shutdown_v49e(
                            self._socket,
                            timeout_seconds=timeout,
                        )
                    else:
                        _require_owner_pre_mutation_deadline_v49e(
                            owner=self,
                            operation="TLS_SHUTDOWN_POLL",
                            deadline_ns=exact_deadline_ns,
                        )
                        observation = await driver.poll_tls_shutdown_v49e(
                            self._socket,
                            deadline_ns=exact_deadline_ns,
                        )
                except PhysicalTlsWebSocketV49DeadlineExpiredNoObservation as exc:
                    if exc.operation != "TLS_SHUTDOWN_POLL" or (
                        exact_deadline_ns is not None
                        and exc.deadline_ns != exact_deadline_ns
                    ):
                        raise LinuxSocketOwnerV4Error(
                            "driver shutdown deadline evidence differs from owner"
                        ) from exc
                    self._assert_terminal_socket_owner_v49e()
                    driver.assert_current()
                    raise _owner_deadline_expired_no_observation_v49e(
                        owner=self,
                        operation="TLS_SHUTDOWN_POLL",
                        deadline_ns=exc.deadline_ns,
                    ) from exc
                except PhysicalTlsWebSocketV49DeadlineExpiredAfterProgress as exc:
                    owner_exc = self._bind_deadline_expired_after_progress_v49e(
                        driver=driver,
                        driver_exc=exc,
                        operation="TLS_SHUTDOWN_POLL",
                        deadline_ns=(
                            exc.deadline_ns
                            if exact_deadline_ns is None
                            else exact_deadline_ns
                        ),
                    )
                    raise owner_exc from exc
                except PhysicalTlsWebSocketV49UnsendablePostHandshakeOutput as exc:
                    owner_evidence = self._bind_unsendable_tls_output_v49e(
                        driver=driver,
                        driver_evidence=exc.evidence,
                    )
                    raise LinuxSocketOwnerV4UnsendablePostHandshakeOutput(
                        _token=(_V49E_OWNER_UNSENDABLE_TLS_OUTPUT_EXCEPTION_TOKEN),
                        evidence=owner_evidence,
                    ) from exc
                if type(observation) is not TlsShutdownObservationV49E:
                    raise LinuxSocketOwnerV4Error(
                        "exact driver returned an unsupported shutdown observation"
                    )
                driver._assert_tls_shutdown_observation_integrity_v49e(observation)
                if observation.observation_kind is (
                    TlsShutdownObservationKindV49E.PEER_CLOSE_NOTIFY
                ):
                    if (
                        not observation.peer_close_notify_received
                        or observation.tcp_eof_received
                        or observation.truncated
                    ):
                        raise LinuxSocketOwnerV4Error(
                            "peer close_notify observation has inconsistent flags"
                        )
                elif observation.observation_kind is (
                    TlsShutdownObservationKindV49E.TCP_EOF
                ):
                    if not observation.tcp_eof_received or observation.truncated != (
                        not observation.peer_close_notify_received
                    ):
                        raise LinuxSocketOwnerV4Error(
                            "TCP EOF observation has inconsistent truncation flags"
                        )
                else:
                    raise LinuxSocketOwnerV4Error(
                        "shutdown observation kind is outside V4.9E"
                    )
                self._assert_terminal_socket_owner_v49e()
                driver.assert_current()
                session_id = self._v49b_bound_session_id
                if type(session_id) is not str or not session_id:
                    raise LinuxSocketOwnerV4Error(
                        "shutdown observation lacks a bound transport session"
                    )
                kernel_socket_identity = self._initial_snapshot.kernel_socket_identity
                values = {
                    "domain": "RiskYieldMMOwnerTlsShutdownObservationV4_9E",
                    "transport_session_id": session_id,
                    "kernel_socket_identity": kernel_socket_identity,
                    "driver_observation_id": observation.observation_id,
                    "driver_observation_sequence": observation.observation_sequence,
                    "driver_observation_kind": observation.observation_kind.value,
                }
                owner_observation = OwnerTlsShutdownObservationV49E(
                    _token=_V49E_OWNER_TLS_SHUTDOWN_OBSERVATION_TOKEN,
                    transport_session_id=session_id,
                    kernel_socket_identity=kernel_socket_identity,
                    driver_observation=observation,
                    owner_observation_id=sha256_digest(values),
                )
                self._assert_owner_tls_shutdown_observation_integrity_v49e(
                    owner_observation
                )
                _register_owner_capability_v49e(
                    _token=_V49E_OWNER_CAPABILITY_REGISTRATION_TOKEN,
                    capability_kind="TLS_SHUTDOWN_OBSERVATION",
                    capability_id=owner_observation.owner_observation_id,
                    capability=owner_observation,
                )
                return owner_observation
        except (
            LinuxSocketOwnerV4DeadlineExpiredNoObservationV49E,
            LinuxSocketOwnerV4DeadlineExpiredAfterProgressV49E,
        ):
            # Pure expiry remains retryable until the actor classifies it.
            # Partial progress is separately I/O-fenced while retaining only
            # the socket-owner authority needed to sign terminal convergence.
            raise
        except BaseException:
            self._latch_terminal_io_fault_for_projection_v49e()
            raise

    async def send_exact_text_frame(
        self,
        payload: bytes,
        *,
        before_driver: Callable[[], None],
    ) -> None:
        if type(payload) is not bytes or not payload:
            raise LinuxSocketOwnerV4Error("TEXT payload must be non-empty bytes")
        if not callable(before_driver):
            raise TypeError("before_driver must be callable")
        async with self._io_lock:
            self._assert_v49b_io_bound()
            self.assert_same_owner(self._initial_snapshot)
            before_driver()
            self.assert_same_owner(self._initial_snapshot)
            await self._driver.send_exact_text_frame(self._socket, payload)
            self.assert_same_owner(self._initial_snapshot)

    async def submit_permitted_chunks(
        self,
        *,
        permit: Any,
        ordered_chunks: tuple[bytes, ...],
        before_driver: Callable[[], None],
    ) -> int:
        if (
            type(ordered_chunks) is not tuple
            or not ordered_chunks
            or any(type(item) is not bytes or not item for item in ordered_chunks)
        ):
            raise LinuxSocketOwnerV4Error(
                "control writer requires exact non-empty byte chunks"
            )
        if not callable(before_driver):
            raise TypeError("before_driver must be callable")
        async with self._io_lock:
            self._assert_v49b_io_bound()
            self.assert_same_owner(self._initial_snapshot)
            before_driver()
            self.assert_same_owner(self._initial_snapshot)
            submitted = await self._driver.submit_permitted_chunks(
                self._socket,
                permit=permit,
                ordered_chunks=ordered_chunks,
            )
            self.assert_same_owner(self._initial_snapshot)
            return submitted

    def _invalidate_in_fork_child(self) -> None:
        """Fence inherited authority without acquiring inherited locks."""

        self._fork_invalid = True
        self._closed = True
        self._v49b_transition = None
        self._v49b_evidence_bound = False
        self._v49d_pending_raw = None
        self._v49c_active_prepared_wire = None
        self._v49c_active_prepared_wire_was_protocol_output = False
        self._v49c_active_prepared_tls = None
        self._v49c_active_prepared_tls_offset = 0
        self._v49e_active_prepared_tls_control = None
        self._v49e_active_prepared_tls_control_offset = 0
        self._v49e_completed_local_close = None
        self._v49e_completed_local_close_values = None
        self._v49e_tcp_write_shutdown_token = None
        self._v49e_tcp_write_shutdown_token_values = None
        self._v49e_tcp_write_shutdown_attempted = True
        self._v49e_tcp_write_shutdown_result = None
        self._v49e_terminal_io_fault_latched = True
        self._v49e_terminal_actor_clock_authorized = False
        self._v49e_terminal_actor_clock_evidence_ids.clear()
        invalidator = getattr(self._driver, "_invalidate_in_fork_child", None)
        if callable(invalidator):
            try:
                invalidator()
            except BaseException:
                pass
        try:
            self._socket.close()
        except OSError:
            pass
        if self._net_namespace is not None:
            try:
                self._net_namespace.close()
            except OSError:
                pass
            self._net_namespace = None
        # The clock is independently registered in _FORK_SENSITIVE.  Calling
        # its normal close path here could transitively acquire an inherited
        # chronyd/artifact lock, so the owner performs no such call in child.

    def abort(self) -> None:
        if self._closed:
            return
        for evidence_id in self._v49e_terminal_actor_clock_evidence_ids:
            _discard_owner_capability_key_v49e(
                capability_kind="TERMINAL_CLOCK_AUTHORIZATION_HANDOFF",
                capability_id=evidence_id,
            )
        shutdown_token = self._v49e_tcp_write_shutdown_token
        if type(shutdown_token) is TcpWriteShutdownTokenV49E:
            _discard_owner_capability_v49e(
                capability_kind="TCP_WRITE_SHUTDOWN_TOKEN",
                capability_id=shutdown_token.shutdown_token_id,
                capability=shutdown_token,
            )
        shutdown_result = self._v49e_tcp_write_shutdown_result
        if type(shutdown_result) is TcpWriteShutdownResultV49E:
            _discard_owner_capability_v49e(
                capability_kind="TCP_WRITE_SHUTDOWN_RESULT",
                capability_id=shutdown_result.shutdown_result_id,
                capability=shutdown_result,
            )
        self._closed = True
        self._v49d_pending_raw = None
        self._v49c_active_prepared_wire = None
        self._v49c_active_prepared_wire_was_protocol_output = False
        self._v49c_active_prepared_tls = None
        self._v49c_active_prepared_tls_offset = 0
        self._v49e_active_prepared_tls_control = None
        self._v49e_active_prepared_tls_control_offset = 0
        self._v49e_completed_local_close = None
        self._v49e_completed_local_close_values = None
        self._v49e_tcp_write_shutdown_token = None
        self._v49e_tcp_write_shutdown_token_values = None
        self._v49e_tcp_write_shutdown_attempted = True
        self._v49e_tcp_write_shutdown_result = None
        self._v49e_terminal_io_fault_latched = True
        self._v49e_terminal_actor_clock_authorized = False
        self._v49e_terminal_actor_clock_evidence_ids.clear()
        _FORK_SENSITIVE.discard(self)
        abort_driver = getattr(self._driver, "abort", None)
        if callable(abort_driver):
            try:
                abort_driver()
            except BaseException:
                pass
        try:
            self._socket.close()
        except OSError:
            pass
        if self._net_namespace is not None:
            try:
                self._net_namespace.close()
            except OSError:
                pass
            self._net_namespace = None
        try:
            self._clock.close()
        except BaseException:
            pass


@dataclass(frozen=True, slots=True)
class LinuxPhysicalTransportRuntimeBundleV4:
    """Sealed live-profile construction result retaining its exact authority."""

    authority: LinuxSocketOwnerV4
    runtime: PhysicalTransportRuntimeV4

    def __post_init__(self) -> None:
        if (
            type(self.authority) is not LinuxSocketOwnerV4
            or not self.authority.is_live_profile
            or type(self.runtime) is not PhysicalTransportRuntimeV4
            or not self.runtime.is_live_profile
        ):
            raise TypeError(
                "Linux runtime bundle requires an exact sealed owner and runtime"
            )

    def abort(self) -> None:
        self.authority.abort()


def build_linux_physical_transport_runtime_v4(
    *,
    journal: Any,
    writer_lease: Any,
    owned_socket: socket.socket,
    driver: BoundLinuxSocketDriverV4,
    clock_policy: ClockSourcePolicyManifestV4,
    configured_source_artifacts: tuple[ConfiguredChronySourceArtifactV4, ...],
    signer: Any,
    deployment_admission: OperationalDeploymentAdmissionV4,
    idempotency_prefix: str,
    config: PhysicalTransportRuntimeConfigV4 | None = None,
) -> LinuxPhysicalTransportRuntimeBundleV4:
    """Validate and close the still-disabled public live-admission boundary.

    The factory accepts neither a prebuilt clock/owner nor alternate command,
    wall-clock, or randomness seams.  Structurally valid inputs transfer and
    close ``owned_socket`` before a fail-closed denial; this function cannot
    currently return a live bundle.
    """

    if type(deployment_admission) is not OperationalDeploymentAdmissionV4:
        raise TypeError(
            "deployment_admission must be an exact OperationalDeploymentAdmissionV4"
        )
    runtime_config = config or PhysicalTransportRuntimeConfigV4()
    if type(runtime_config) is not PhysicalTransportRuntimeConfigV4:
        raise TypeError("config must be an exact PhysicalTransportRuntimeConfigV4")
    # Imports remain local so the generic projection and lease modules don't
    # depend on this Linux-only adapter at import time.
    from .physical_projection_v4 import PhysicalProjectionStoreV4
    from .physical_transport_lease_v4 import PhysicalTransportWriterLeaseV4

    if type(journal) is not PhysicalProjectionStoreV4:
        raise TypeError(
            "sealed Linux construction requires an exact PhysicalProjectionStoreV4"
        )
    if type(writer_lease) is not PhysicalTransportWriterLeaseV4:
        raise TypeError(
            "sealed Linux construction requires an exact PhysicalTransportWriterLeaseV4"
        )
    if (
        type(clock_policy) is not ClockSourcePolicyManifestV4
        or deployment_admission.clock_policy != clock_policy
    ):
        raise TypeError(
            "sealed Linux clock policy must equal the admitted deployment policy"
        )
    if type(owned_socket) is not socket.socket:
        raise TypeError("owned_socket must be an exact socket.socket")
    if not isinstance(driver, BoundLinuxSocketDriverV4):
        raise TypeError("driver must implement BoundLinuxSocketDriverV4")

    # The V4.9E candidate now covers the governed physical lifecycle, but this
    # public live factory remains closed pending post-V4.9F integrated
    # promotion validation and operational qualification.  This is still the
    # ownership boundary: structurally valid inputs transfer the socket and
    # fail closed; no live-readiness claim follows from implementation alone.
    try:
        owned_socket.close()
    finally:
        raise LinuxTransportEvidenceV4Error(
            "live construction is disabled pending post-V4.9F promotion "
            "validation and operational qualification"
        )


__all__ = [
    "BoundLinuxSocketDriverV4",
    "BoundedCommandResultV4",
    "DriverHandshakeTransitionV49B",
    "LinuxPhysicalTransportRuntimeBundleV4",
    "GovernedClockSampleV4",
    "LinuxChronyClockV4",
    "LinuxChronyEvidenceV4Error",
    "LinuxNamespaceEvidenceV4Error",
    "LinuxSocketOwnerV4",
    "LinuxSocketOwnerV4DeadlineExpiredAfterProgressV49E",
    "LinuxSocketOwnerV4DeadlineExpiredNoObservationV49E",
    "LinuxSocketOwnerV4Error",
    "LinuxSocketOwnerV4SendDeadlineExpiredNoKernelAcceptanceV49E",
    "LinuxSocketOwnerV4UnsendablePostHandshakeOutput",
    "LinuxTransportEvidenceV4Error",
    "OwnerTlsShutdownObservationV49E",
    "OwnerUnsendableTlsPostHandshakeOutputV49E",
    "TcpWriteShutdownErrorCodeV49E",
    "TcpWriteShutdownPermitV49E",
    "TcpWriteShutdownResultV49E",
    "TcpWriteShutdownTokenV49E",
    "build_linux_physical_transport_runtime_v4",
    "parse_chronyc_tracking_sources_v4",
    "run_bounded_command_v4",
]
