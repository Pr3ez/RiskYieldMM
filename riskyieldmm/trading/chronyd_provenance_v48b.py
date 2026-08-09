"""Prospective loaded-chronyd authority for the V4.8B transport profile.

The existing distribution daemon is deliberately not attachable.  This module
only admits configuration bytes assembled from retained signed artifacts,
seals those bytes in a memfd, validates the exact configuration interpreted by
the pinned chronyd executable, and defines the credential-authenticated,
read-only Chrony protocol used by a dedicated supervisor.

This is a local provenance mechanism under a trusted Linux kernel and trusted
systemd/supervisor boundary.  It does not prove upstream UTC truth, a
compromise-free daemon/kernel, remote attestation, or trading profitability.
"""

from __future__ import annotations

import ctypes
import fcntl
import hashlib
import ipaddress
import os
import posixpath
import pwd
import re
import secrets
import select
import selectors
import signal
import socket
import stat
import struct
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Final, Protocol

from .canonical import canonical_hash, canonical_identifier, sha256_digest
from .operational_artifact_loading_v4 import (
    ConfiguredChronySourceArtifactV4,
    OperationalArtifactV4Error,
    PinnedRuntimeArtifactV4,
    RuntimeArtifactSpecV4,
    derive_configured_chrony_source_set_root_v4,
)
from .operational_manifests_v4 import (
    CHRONYD_FIXED_ENVIRONMENT_SHA256,
    CHRONYD_QUERY_SOCKET_PATH_SUFFIX_BYTES,
    ChronydLaunchPolicyV48B,
    ClockSourcePolicyManifestV4,
)

_MAX_CONFIG_BYTES: Final = 1_048_576
_MAX_CONFIG_LINE_BYTES: Final = 2_047
_CHRONY_PROTOCOL_VERSION: Final = 6
_CHRONY_REQUEST_TYPE: Final = 1
_CHRONY_REPLY_TYPE: Final = 2
_REQ_TRACKING: Final = 33
_REQ_N_SOURCES: Final = 14
_REQ_SOURCE_DATA: Final = 15
_RPY_TRACKING: Final = 5
_RPY_N_SOURCES: Final = 2
_RPY_SOURCE_DATA: Final = 3
_TRACKING_PACKET_BYTES: Final = 104
_N_SOURCES_PACKET_BYTES: Final = 32
_SOURCE_DATA_PACKET_BYTES: Final = 76
_REQUEST_DATA_OFFSET: Final = 20
_REPLY_DATA_OFFSET: Final = 28
_MAX_CHRONY_SOURCES: Final = 64
_SO_PASSCRED: Final = 16
_SCM_CREDENTIALS: Final = 2
_UCRED = struct.Struct("=iii")

# Linux UAPI values.  They are stable ABI constants and are used only when the
# Python build does not expose the corresponding wrappers/constants.
_MFD_CLOEXEC: Final = 0x0001
_MFD_ALLOW_SEALING: Final = 0x0002
_F_ADD_SEALS: Final = 1033
_F_GET_SEALS: Final = 1034
_F_SEAL_SEAL: Final = 0x0001
_F_SEAL_SHRINK: Final = 0x0002
_F_SEAL_GROW: Final = 0x0004
_F_SEAL_WRITE: Final = 0x0008
_REQUIRED_CONFIG_SEALS: Final = (
    _F_SEAL_SEAL | _F_SEAL_SHRINK | _F_SEAL_GROW | _F_SEAL_WRITE
)

_FIXED_CHRONYD_ENVIRONMENT: Final = {
    "LANG": "C",
    "LC_ALL": "C",
    "PATH": "/usr/bin:/bin",
    "TZ": "UTC",
}

_FORBIDDEN_DIRECTIVES: Final = frozenset(
    {
        "acquisitionport",
        "allow",
        "authselectmode",
        "bindacqaddress",
        "bindaddress",
        "binddevice",
        "cmdallow",
        "cmdallowall",
        "cmddeny",
        "cmddenyall",
        "confdir",
        "copy",
        "hwtimestamp",
        "include",
        "initstepslew",
        "keyfile",
        "leapsectz",
        "local",
        "manual",
        "ntsdumpdir",
        "ntsservercert",
        "ntsserverkey",
        "pool",
        "refclock",
        "rtcfile",
        "sourcedir",
        "user",
    }
)
_ALLOWED_DIRECTIVES: Final = frozenset(
    {
        "bindcmdaddress",
        "cmdport",
        "combinelimit",
        "corrtimeratio",
        "driftfile",
        "makestep",
        "maxclockerror",
        "maxdistance",
        "maxslewrate",
        "maxupdateskew",
        "minsources",
        "noclientlog",
        "peer",
        "pidfile",
        "port",
        "reselectdist",
        "rtcsync",
        "server",
        "stratumweight",
    }
)
_SOURCE_OPTIONS_REQUIRING_EXTERNAL_STATE: Final = frozenset(
    {"certset", "key", "nts", "ntsport"}
)
_SYSTEMD_INVOCATION_ID_RE: Final = re.compile(r"^[0-9a-f]{32}$")
_BOOT_ID_RE: Final = re.compile(
    rb"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-"
    rb"[89ab][0-9a-f]{3}-[0-9a-f]{12}\n?$"
)
_CHRONYD_INITIAL_SOCKET_MODE: Final = 0o660
_CHRONYD_SEALED_SOCKET_MODE: Final = 0o600
_CHRONYD_VERSION_RE: Final = re.compile(
    rb"chronyd \(chrony\) version 4\.8(?: \([^\r\n]{1,512}\))?\n?"
)
_REQUIRED_CHRONYD_CAPABILITY_MASK: Final = 0x0000000002000400
_CAPABILITY_HEX_RE: Final = re.compile(rb"^[0-9a-f]{16}$")


class ChronydProvenanceV48BError(RuntimeError):
    """Raised when prospective loaded-daemon provenance cannot be proven."""


class ChronydConfigurationV48BError(ChronydProvenanceV48BError):
    """Raised when configuration is dynamic, ambiguous, or outside profile."""


class ChronydProtocolV48BError(ChronydProvenanceV48BError):
    """Raised on any deviation from the frozen read-only Chrony v6 exchange."""


class ChronydSourcesNotReadyV48BError(ChronydProtocolV48BError):
    """Raised only while configured sources are not loaded after lifecycle READY."""


class ChronydProcessV48BError(ChronydProvenanceV48BError):
    """Raised when the retained chronyd process or socket instance changes."""


@dataclass(frozen=True, slots=True, kw_only=True)
class EffectiveChronydConfigurationV48B:
    """One deterministic static configuration assembled from signed inputs."""

    raw_bytes: bytes
    sha256: str
    configured_endpoints: tuple[str, ...]
    configured_source_count: int

    def __post_init__(self) -> None:
        if type(self.raw_bytes) is not bytes or not self.raw_bytes:
            raise ChronydConfigurationV48BError(
                "effective chronyd configuration must be non-empty bytes"
            )
        if hashlib.sha256(self.raw_bytes).hexdigest() != canonical_hash(
            self.sha256, field="effective_config_sha256"
        ):
            raise ChronydConfigurationV48BError(
                "effective chronyd configuration digest is inconsistent"
            )
        if (
            not isinstance(self.configured_endpoints, tuple)
            or not self.configured_endpoints
            or tuple(sorted(set(self.configured_endpoints)))
            != self.configured_endpoints
        ):
            raise ChronydConfigurationV48BError(
                "configured endpoints must be a non-empty sorted unique tuple"
            )
        if self.configured_source_count != len(self.configured_endpoints):
            raise ChronydConfigurationV48BError(
                "configured source count differs from endpoint closure"
            )


def _strict_config_lines(raw: bytes, *, context: str) -> tuple[str, ...]:
    if type(raw) is not bytes or not raw or len(raw) > _MAX_CONFIG_BYTES:
        raise ChronydConfigurationV48BError(
            f"{context} must be non-empty bounded bytes"
        )
    if b"\x00" in raw or b"\r" in raw or not raw.endswith(b"\n"):
        raise ChronydConfigurationV48BError(
            f"{context} must be NUL-free LF-terminated ASCII"
        )
    try:
        text = raw.decode("ascii", errors="strict")
    except UnicodeDecodeError as exc:
        raise ChronydConfigurationV48BError(f"{context} must use strict ASCII") from exc
    lines = tuple(text[:-1].split("\n"))
    if any(len(line.encode("ascii")) > _MAX_CONFIG_LINE_BYTES for line in lines):
        raise ChronydConfigurationV48BError(
            f"{context} contains a line longer than the reviewed chrony bound"
        )
    return lines


def _canonical_config_input_path(path: str, *, field: str) -> str:
    value = canonical_identifier(path, field=field, maximum=4096)
    if not value.startswith("/") or posixpath.normpath(value) != value:
        raise ChronydConfigurationV48BError(
            f"{field} must be a normalized absolute POSIX path"
        )
    return value


def _config_directive_tokens(lines: tuple[str, ...]) -> tuple[tuple[str, ...], ...]:
    directives: list[tuple[str, ...]] = []
    for line in lines:
        content = line.split("#", 1)[0].strip()
        if not content:
            continue
        tokens = tuple(content.split())
        if any(not token or not token.isascii() for token in tokens):
            raise ChronydConfigurationV48BError(
                "chronyd configuration contains a malformed token"
            )
        directives.append((tokens[0].lower(), *tokens[1:]))
    return tuple(directives)


def _validate_static_configuration_profile(
    lines: tuple[str, ...],
    *,
    launch_policy: ChronydLaunchPolicyV48B,
    minimum_selectable_sources: int,
) -> tuple[str, ...]:
    directives = _config_directive_tokens(lines)
    exact_singletons: dict[str, list[tuple[str, ...]]] = {
        name: []
        for name in (
            "bindcmdaddress",
            "cmdport",
            "driftfile",
            "minsources",
            "pidfile",
            "port",
        )
    }
    endpoints: list[str] = []
    for tokens in directives:
        name = tokens[0]
        if name in _FORBIDDEN_DIRECTIVES:
            raise ChronydConfigurationV48BError(
                f"chronyd directive {name!r} is forbidden by the static profile"
            )
        if name not in _ALLOWED_DIRECTIVES:
            raise ChronydConfigurationV48BError(
                f"chronyd directive {name!r} is not reviewed by V4.8B"
            )
        if name in exact_singletons:
            exact_singletons[name].append(tokens)
        if name in {"server", "peer"}:
            if len(tokens) < 2:
                raise ChronydConfigurationV48BError(
                    f"chronyd {name} directive has no endpoint"
                )
            try:
                endpoint = str(ipaddress.ip_address(tokens[1]))
            except ValueError as exc:
                raise ChronydConfigurationV48BError(
                    "V4.8B sources must use canonical literal IP endpoints"
                ) from exc
            if endpoint != tokens[1]:
                raise ChronydConfigurationV48BError(
                    "V4.8B source endpoints must use canonical IP spelling"
                )
            option_names = {token.lower() for token in tokens[2:]}
            forbidden_options = option_names & _SOURCE_OPTIONS_REQUIRING_EXTERNAL_STATE
            if forbidden_options:
                raise ChronydConfigurationV48BError(
                    "V4.8B source options require unsealed external state: "
                    + ", ".join(sorted(forbidden_options))
                )
            endpoints.append(endpoint)

    expected_singletons = {
        "bindcmdaddress": ("bindcmdaddress", launch_policy.real_command_socket_path),
        "cmdport": ("cmdport", "0"),
        "driftfile": ("driftfile", "/"),
        "minsources": ("minsources", str(minimum_selectable_sources)),
        "pidfile": ("pidfile", "/"),
        "port": ("port", "0"),
    }
    for name, expected in expected_singletons.items():
        if exact_singletons[name] != [expected]:
            raise ChronydConfigurationV48BError(
                f"chronyd static profile requires exactly {expected!r}"
            )
    if len(endpoints) < minimum_selectable_sources:
        raise ChronydConfigurationV48BError(
            "chronyd configuration has fewer literal sources than signed policy"
        )
    if len(endpoints) > _MAX_CHRONY_SOURCES or len(set(endpoints)) != len(endpoints):
        raise ChronydConfigurationV48BError(
            "chronyd configuration source endpoints are duplicated or excessive"
        )
    return tuple(sorted(endpoints))


def assemble_effective_chronyd_configuration_v48b(
    *,
    base_path: str,
    base_bytes: bytes,
    source_fragments: tuple[tuple[str, bytes], ...],
    launch_policy: ChronydLaunchPolicyV48B,
    minimum_selectable_sources: int,
) -> EffectiveChronydConfigurationV48B:
    """Assemble and validate the only configuration bytes chronyd may parse."""

    if type(launch_policy) is not ChronydLaunchPolicyV48B:
        raise TypeError("launch_policy must be an exact ChronydLaunchPolicyV48B")
    base_name = _canonical_config_input_path(base_path, field="base_config_path")
    base_lines = _strict_config_lines(base_bytes, context="base chronyd configuration")
    if not isinstance(source_fragments, tuple):
        raise TypeError("source_fragments must be an exact tuple")
    normalized: list[tuple[str, bytes, tuple[str, ...]]] = []
    seen_paths = {base_name}
    for index, item in enumerate(source_fragments):
        if (
            type(item) is not tuple
            or len(item) != 2
            or type(item[0]) is not str
            or type(item[1]) is not bytes
        ):
            raise TypeError("each source fragment must be an exact (path, bytes) tuple")
        path = _canonical_config_input_path(
            item[0], field=f"source_fragment_path_{index}"
        )
        if path in seen_paths:
            raise ChronydConfigurationV48BError(
                "chronyd configuration input paths must be unique"
            )
        seen_paths.add(path)
        normalized.append(
            (
                path,
                item[1],
                _strict_config_lines(
                    item[1], context=f"chronyd source fragment {index}"
                ),
            )
        )
    normalized.sort(key=lambda item: item[0].encode("utf-8"))

    chunks = [
        b"# riskyieldmm-v48b-static-config\n",
        ("# base-sha256 " + hashlib.sha256(base_bytes).hexdigest() + "\n").encode(
            "ascii"
        ),
        base_bytes,
    ]
    all_lines = list(base_lines)
    for index, (_, raw, lines) in enumerate(normalized):
        chunks.append(
            (f"# fragment-{index}-sha256 {hashlib.sha256(raw).hexdigest()}\n").encode(
                "ascii"
            )
        )
        chunks.append(raw)
        all_lines.extend(lines)
    effective = b"".join(chunks)
    if len(effective) > _MAX_CONFIG_BYTES:
        raise ChronydConfigurationV48BError(
            "assembled chronyd configuration exceeds the reviewed byte bound"
        )
    endpoints = _validate_static_configuration_profile(
        tuple(all_lines),
        launch_policy=launch_policy,
        minimum_selectable_sources=minimum_selectable_sources,
    )
    digest = hashlib.sha256(effective).hexdigest()
    if digest != launch_policy.effective_config_sha256:
        raise ChronydConfigurationV48BError(
            "assembled chronyd configuration differs from signed effective digest"
        )
    return EffectiveChronydConfigurationV48B(
        raw_bytes=effective,
        sha256=digest,
        configured_endpoints=endpoints,
        configured_source_count=len(endpoints),
    )


def _libc_function(name: str) -> ctypes._CFuncPtr:  # type: ignore[name-defined]
    try:
        function = getattr(ctypes.CDLL(None, use_errno=True), name)
    except AttributeError as exc:
        raise ChronydProvenanceV48BError(
            f"Linux libc does not expose required {name} capability"
        ) from exc
    return function


def _memfd_create(name: str) -> int:
    native = getattr(os, "memfd_create", None)
    if callable(native):
        return native(name, _MFD_CLOEXEC | _MFD_ALLOW_SEALING)
    function = _libc_function("memfd_create")
    function.argtypes = (ctypes.c_char_p, ctypes.c_uint)
    function.restype = ctypes.c_int
    fd = function(name.encode("ascii"), _MFD_CLOEXEC | _MFD_ALLOW_SEALING)
    if fd < 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))
    return fd


class SealedChronydConfigurationV48B:
    """Retained write-sealed Linux memfd containing the exact effective config."""

    def __init__(self, *, fd: int, sha256: str, size_bytes: int) -> None:
        self._fd = fd
        self._sha256 = canonical_hash(sha256, field="effective_config_sha256")
        self._size_bytes = size_bytes
        self._creator_pid = os.getpid()
        self._closed = False

    @classmethod
    def create(
        cls, effective: EffectiveChronydConfigurationV48B
    ) -> SealedChronydConfigurationV48B:
        if type(effective) is not EffectiveChronydConfigurationV48B:
            raise TypeError(
                "effective must be an exact EffectiveChronydConfigurationV48B"
            )
        try:
            fd = _memfd_create("riskyieldmm-chronyd-v48b")
        except OSError as exc:
            raise ChronydProvenanceV48BError(
                "sealed chronyd configuration memfd could not be created"
            ) from exc
        try:
            view = memoryview(effective.raw_bytes)
            offset = 0
            while offset < len(view):
                written = os.write(fd, view[offset:])
                if written <= 0:
                    raise ChronydProvenanceV48BError(
                        "sealed chronyd configuration write made no progress"
                    )
                offset += written
            fcntl.fcntl(fd, _F_ADD_SEALS, _REQUIRED_CONFIG_SEALS)
            os.set_inheritable(fd, False)
            item = cls(fd=fd, sha256=effective.sha256, size_bytes=len(view))
            item.assert_sealed()
            return item
        except BaseException:
            os.close(fd)
            raise

    @property
    def descriptor(self) -> int:
        self.assert_sealed()
        return self._fd

    @property
    def proc_fd_path(self) -> str:
        return f"/proc/self/fd/{self.descriptor}"

    @property
    def sha256(self) -> str:
        return self._sha256

    @property
    def seals(self) -> int:
        if self._closed:
            raise ChronydProvenanceV48BError("sealed chronyd configuration is closed")
        return int(fcntl.fcntl(self._fd, _F_GET_SEALS))

    def assert_sealed(self) -> None:
        if self._closed or os.getpid() != self._creator_pid:
            raise ChronydProvenanceV48BError(
                "sealed chronyd configuration left its creating process"
            )
        try:
            if os.get_inheritable(self._fd):
                raise ChronydProvenanceV48BError(
                    "sealed chronyd configuration descriptor became inheritable"
                )
            info = os.fstat(self._fd)
            raw = os.pread(self._fd, self._size_bytes + 1, 0)
            seals = int(fcntl.fcntl(self._fd, _F_GET_SEALS))
        except OSError as exc:
            raise ChronydProvenanceV48BError(
                "sealed chronyd configuration could not be revalidated"
            ) from exc
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_size != self._size_bytes
            or len(raw) != self._size_bytes
            or hashlib.sha256(raw).hexdigest() != self._sha256
            or seals != _REQUIRED_CONFIG_SEALS
        ):
            raise ChronydProvenanceV48BError(
                "sealed chronyd configuration identity or seals changed"
            )

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            os.close(self._fd)

    def __enter__(self) -> SealedChronydConfigurationV48B:
        self.assert_sealed()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


@dataclass(frozen=True, slots=True, kw_only=True)
class ChronyProtocolExchangeV48B:
    command: int
    request_sha256: str
    reply_sha256: str
    sequence_hex: str


@dataclass(frozen=True, slots=True, kw_only=True)
class AuthenticatedChronyTranscriptV48B:
    exchanges: tuple[ChronyProtocolExchangeV48B, ...]
    source_count: int
    transcript_sha256: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.exchanges, tuple)
            or len(self.exchanges) != self.source_count + 2
        ):
            raise ChronydProtocolV48BError(
                "chrony transcript length differs from source count"
            )
        canonical_hash(self.transcript_sha256, field="transcript_sha256")


def _network_u16(raw: bytes, offset: int) -> int:
    return int.from_bytes(raw[offset : offset + 2], "big", signed=False)


def _network_u32(raw: bytes, offset: int) -> int:
    return int.from_bytes(raw[offset : offset + 4], "big", signed=False)


def _validate_common_request(
    raw: bytes, *, expected_command: int, expected_size: int
) -> bytes:
    if type(raw) is not bytes or len(raw) != expected_size:
        raise ChronydProtocolV48BError(
            "chronyc request has a noncanonical command-specific length"
        )
    if (
        raw[0] != _CHRONY_PROTOCOL_VERSION
        or raw[1] != _CHRONY_REQUEST_TYPE
        or raw[2:4] != b"\x00\x00"
        or _network_u16(raw, 4) != expected_command
        or _network_u16(raw, 6) != 0
        or raw[12:20] != b"\x00" * 8
    ):
        raise ChronydProtocolV48BError(
            "chronyc request header differs from the frozen v6 profile"
        )
    return raw[8:12]


def _validate_common_reply(
    raw: bytes,
    *,
    expected_command: int,
    expected_reply: int,
    expected_size: int,
    sequence: bytes,
) -> None:
    if type(raw) is not bytes or len(raw) != expected_size:
        raise ChronydProtocolV48BError(
            "chronyd reply has a noncanonical command-specific length"
        )
    if (
        raw[0] != _CHRONY_PROTOCOL_VERSION
        or raw[1] != _CHRONY_REPLY_TYPE
        or raw[2:4] != b"\x00\x00"
        or _network_u16(raw, 4) != expected_command
        or _network_u16(raw, 6) != expected_reply
        or _network_u16(raw, 8) != 0
        or raw[10:16] != b"\x00" * 6
        or raw[16:20] != sequence
        or raw[20:28] != b"\x00" * 8
    ):
        raise ChronydProtocolV48BError(
            "chronyd reply header differs from the frozen successful v6 profile"
        )


class ChronyReadOnlyQueryStateV48B:
    """Exact ``tracking`` then ``sources -a`` state machine for ``-n -c``."""

    def __init__(self, *, expected_source_count: int) -> None:
        if (
            type(expected_source_count) is not int
            or not 1 <= expected_source_count <= _MAX_CHRONY_SOURCES
        ):
            raise ChronydProtocolV48BError(
                "expected source count is outside the frozen v6 profile"
            )
        self._expected_source_count = expected_source_count
        self._source_count: int | None = None
        self._next_source_index = 0
        self._phase = "TRACKING"
        self._exchanges: list[ChronyProtocolExchangeV48B] = []

    @property
    def complete(self) -> bool:
        return self._phase == "DONE"

    @property
    def expected_command(self) -> int:
        if self._phase == "TRACKING":
            return _REQ_TRACKING
        if self._phase == "N_SOURCES":
            return _REQ_N_SOURCES
        if self._phase == "SOURCE_DATA":
            return _REQ_SOURCE_DATA
        raise ChronydProtocolV48BError(
            "chrony query state received an exchange after completion"
        )

    def accept_exchange(self, request: bytes, reply: bytes) -> None:
        command = self.expected_command
        if command == _REQ_TRACKING:
            request_size = reply_size = _TRACKING_PACKET_BYTES
            reply_type = _RPY_TRACKING
        elif command == _REQ_N_SOURCES:
            request_size = reply_size = _N_SOURCES_PACKET_BYTES
            reply_type = _RPY_N_SOURCES
        else:
            request_size = reply_size = _SOURCE_DATA_PACKET_BYTES
            reply_type = _RPY_SOURCE_DATA
        sequence = _validate_common_request(
            request, expected_command=command, expected_size=request_size
        )
        _validate_common_reply(
            reply,
            expected_command=command,
            expected_reply=reply_type,
            expected_size=reply_size,
            sequence=sequence,
        )
        if command in {_REQ_TRACKING, _REQ_N_SOURCES} and request[
            _REQUEST_DATA_OFFSET:
        ] != b"\x00" * (request_size - _REQUEST_DATA_OFFSET):
            raise ChronydProtocolV48BError(
                "read-only chronyc request contains unexpected command data"
            )
        if command == _REQ_SOURCE_DATA:
            if (
                _network_u32(request, _REQUEST_DATA_OFFSET) != self._next_source_index
                or request[_REQUEST_DATA_OFFSET + 4 :] != b"\x00" * 52
            ):
                raise ChronydProtocolV48BError(
                    "chronyc source-data request index or padding is noncanonical"
                )
        if command == _REQ_N_SOURCES:
            count = _network_u32(reply, _REPLY_DATA_OFFSET)
            if count < self._expected_source_count:
                raise ChronydSourcesNotReadyV48BError(
                    "chronyd runtime source count differs from sealed configuration"
                )
            if count > self._expected_source_count:
                raise ChronydProtocolV48BError(
                    "chronyd runtime source count includes more sources than sealed configuration"
                )
            self._source_count = count

        self._exchanges.append(
            ChronyProtocolExchangeV48B(
                command=command,
                request_sha256=hashlib.sha256(request).hexdigest(),
                reply_sha256=hashlib.sha256(reply).hexdigest(),
                sequence_hex=sequence.hex(),
            )
        )
        if self._phase == "TRACKING":
            self._phase = "N_SOURCES"
        elif self._phase == "N_SOURCES":
            self._phase = "SOURCE_DATA"
        else:
            self._next_source_index += 1
            if self._next_source_index == self._source_count:
                self._phase = "DONE"

    def finish(self) -> AuthenticatedChronyTranscriptV48B:
        if not self.complete or self._source_count is None:
            raise ChronydProtocolV48BError(
                "chrony query ended before the exact read-only state machine completed"
            )
        exchanges = tuple(self._exchanges)
        digest = sha256_digest(
            {
                "domain": "RiskYieldMMChrony48ReadOnlyTranscriptV1",
                "exchanges": [
                    {
                        "command": item.command,
                        "reply_sha256": item.reply_sha256,
                        "request_sha256": item.request_sha256,
                        "sequence_hex": item.sequence_hex,
                    }
                    for item in exchanges
                ],
                "source_count": self._source_count,
            }
        )
        return AuthenticatedChronyTranscriptV48B(
            exchanges=exchanges,
            source_count=self._source_count,
            transcript_sha256=digest,
        )


def receive_authenticated_datagram_v48b(
    sock: socket.socket,
    *,
    maximum_bytes: int,
    expected_pid: int,
    expected_uid: int,
    expected_gid: int,
) -> tuple[bytes, str | bytes | None]:
    """Receive one complete AF_UNIX datagram with exact kernel credentials."""

    ancillary_size = socket.CMSG_SPACE(_UCRED.size)
    try:
        raw, ancillary, flags, address = sock.recvmsg(maximum_bytes, ancillary_size)
    except OSError as exc:
        raise ChronydProtocolV48BError(
            "credential-authenticated Unix datagram could not be received"
        ) from exc
    if flags & (socket.MSG_TRUNC | socket.MSG_CTRUNC):
        raise ChronydProtocolV48BError(
            "credential-authenticated Unix datagram was truncated"
        )
    credentials = [
        data
        for level, kind, data in ancillary
        if level == socket.SOL_SOCKET
        and kind == getattr(socket, "SCM_CREDENTIALS", _SCM_CREDENTIALS)
    ]
    if (
        len(credentials) != 1
        or len(ancillary) != 1
        or len(credentials[0]) != _UCRED.size
    ):
        raise ChronydProtocolV48BError(
            "Unix datagram did not carry exactly one SCM_CREDENTIALS record"
        )
    pid, uid, gid = _UCRED.unpack(credentials[0])
    if (pid, uid, gid) != (expected_pid, expected_uid, expected_gid):
        raise ChronydProtocolV48BError(
            "Unix datagram kernel credentials differ from retained process identity"
        )
    if not raw or len(raw) >= maximum_bytes:
        raise ChronydProtocolV48BError(
            "Unix datagram is empty or reaches the signed receive bound"
        )
    return raw, address


@dataclass(frozen=True, slots=True, kw_only=True)
class BoundedChronydCommandResultV48B:
    returncode: int
    stdout: bytes
    stderr: bytes


class ChronydCommandRunnerV48B(Protocol):
    def __call__(
        self,
        argv: tuple[str, ...],
        *,
        pass_fds: tuple[int, ...],
        timeout_milliseconds: int,
        maximum_output_bytes: int,
    ) -> object: ...


class PreparedChronydLaunchV48B:
    """Pre-daemon retained closure ready for an explicit supervised launch.

    Preparation runs bounded ``chronyd -v`` and ``chronyd -p`` validation
    subprocesses, but it does not launch or mutate a persistent time service.
    """

    _CONSTRUCTION_TOKEN = object()

    def __init__(
        self,
        *,
        policy: ClockSourcePolicyManifestV4,
        systemd_unit: PinnedRuntimeArtifactV4,
        chronyd: PinnedRuntimeArtifactV4,
        base_config: PinnedRuntimeArtifactV4,
        source_artifacts: tuple[PinnedRuntimeArtifactV4, ...],
        effective_config: EffectiveChronydConfigurationV48B,
        sealed_config: SealedChronydConfigurationV48B,
        printed_config_sha256: str,
        live_profile: bool,
        token: object,
    ) -> None:
        if token is not self._CONSTRUCTION_TOKEN:
            raise TypeError("prepared chronyd launch cannot be caller-constructed")
        if type(live_profile) is not bool:
            raise TypeError("prepared chronyd live_profile must be a boolean")
        self._policy = policy
        self._systemd_unit = systemd_unit
        self._chronyd = chronyd
        self._base_config = base_config
        self._source_artifacts = source_artifacts
        self._effective_config = effective_config
        self._sealed_config = sealed_config
        self._printed_config_sha256 = canonical_hash(
            printed_config_sha256, field="printed_config_sha256"
        )
        self._live_profile = live_profile
        self._creator_pid = os.getpid()
        self._creator_thread = threading.get_ident()
        self._closed = False

    @classmethod
    def prepare(
        cls,
        *,
        policy: ClockSourcePolicyManifestV4,
        configured_source_artifacts: tuple[ConfiguredChronySourceArtifactV4, ...],
    ) -> PreparedChronydLaunchV48B:
        """Prepare the production closure with the sealed real command runner."""

        from .physical_transport_linux_v4 import run_bounded_command_v4

        return cls._prepare(
            policy=policy,
            configured_source_artifacts=configured_source_artifacts,
            command_runner=run_bounded_command_v4,
            live_profile=True,
        )

    @classmethod
    def _prepare_for_test(
        cls,
        *,
        policy: ClockSourcePolicyManifestV4,
        configured_source_artifacts: tuple[ConfiguredChronySourceArtifactV4, ...],
        command_runner: ChronydCommandRunnerV48B,
    ) -> PreparedChronydLaunchV48B:
        """Build a deterministic non-promotion closure for focused tests only."""

        if not callable(command_runner):
            raise TypeError("test command_runner must be callable")
        return cls._prepare(
            policy=policy,
            configured_source_artifacts=configured_source_artifacts,
            command_runner=command_runner,
            live_profile=False,
        )

    @classmethod
    def _prepare(
        cls,
        *,
        policy: ClockSourcePolicyManifestV4,
        configured_source_artifacts: tuple[ConfiguredChronySourceArtifactV4, ...],
        command_runner: ChronydCommandRunnerV48B,
        live_profile: bool,
    ) -> PreparedChronydLaunchV48B:
        if type(policy) is not ClockSourcePolicyManifestV4:
            raise TypeError("policy must be an exact ClockSourcePolicyManifestV4")
        if type(live_profile) is not bool or not callable(command_runner):
            raise TypeError("chronyd preparation profile is malformed")
        if policy.chrony_version != "4.8":
            raise ChronydProvenanceV48BError(
                "only the reviewed chronyd 4.8 launch profile is implemented"
            )
        if (
            derive_configured_chrony_source_set_root_v4(configured_source_artifacts)
            != policy.configured_source_set_root_sha256
        ):
            raise ChronydConfigurationV48BError(
                "configured source artifact closure differs from signed policy"
            )
        launch = policy.chronyd_launch_policy
        opened: list[PinnedRuntimeArtifactV4] = []
        sealed: SealedChronydConfigurationV48B | None = None
        try:
            unit = PinnedRuntimeArtifactV4.open_verified(
                RuntimeArtifactSpecV4(
                    path=launch.systemd_unit_path,
                    sha256=launch.systemd_unit_sha256,
                    max_bytes=1024 * 1024,
                )
            )
            opened.append(unit)
            chronyd = PinnedRuntimeArtifactV4.open_verified(
                RuntimeArtifactSpecV4(
                    path=launch.chronyd_executable_path,
                    sha256=launch.chronyd_executable_sha256,
                    require_executable=True,
                    max_bytes=64 * 1024 * 1024,
                )
            )
            opened.append(chronyd)
            base = PinnedRuntimeArtifactV4.open_verified(
                RuntimeArtifactSpecV4(
                    path=policy.chrony_config_path,
                    sha256=policy.chrony_config_sha256,
                    max_bytes=_MAX_CONFIG_BYTES,
                )
            )
            opened.append(base)
            source_list: list[PinnedRuntimeArtifactV4] = []
            for source_artifact in configured_source_artifacts:
                source = PinnedRuntimeArtifactV4.open_verified(
                    source_artifact.runtime_spec()
                )
                source_list.append(source)
                opened.append(source)
            sources = tuple(source_list)
            effective = assemble_effective_chronyd_configuration_v48b(
                base_path=policy.chrony_config_path,
                base_bytes=base.read_bytes(),
                source_fragments=tuple(
                    (artifact.spec.path, artifact.read_bytes()) for artifact in sources
                ),
                launch_policy=launch,
                minimum_selectable_sources=policy.min_selectable_sources,
            )
            sealed = SealedChronydConfigurationV48B.create(effective)
            version_result = command_runner(
                (chronyd.proc_fd_path, "-v"),
                pass_fds=(chronyd.descriptor,),
                timeout_milliseconds=launch.ready_timeout_milliseconds,
                maximum_output_bytes=4_096,
            )
            version_returncode = getattr(version_result, "returncode", None)
            version_stdout = getattr(version_result, "stdout", None)
            version_stderr = getattr(version_result, "stderr", None)
            if (
                version_returncode != 0
                or type(version_stdout) is not bytes
                or type(version_stderr) is not bytes
                or version_stderr
                or _CHRONYD_VERSION_RE.fullmatch(version_stdout) is None
            ):
                raise ChronydConfigurationV48BError(
                    "pinned chronyd executable is not the reviewed 4.8 version"
                )
            result = command_runner(
                (
                    chronyd.proc_fd_path,
                    "-p",
                    "-f",
                    sealed.proc_fd_path,
                ),
                pass_fds=(chronyd.descriptor, sealed.descriptor),
                timeout_milliseconds=launch.ready_timeout_milliseconds,
                maximum_output_bytes=_MAX_CONFIG_BYTES,
            )
            returncode = getattr(result, "returncode", None)
            stdout = getattr(result, "stdout", None)
            stderr = getattr(result, "stderr", None)
            if (
                type(returncode) is not int
                or type(stdout) is not bytes
                or type(stderr) is not bytes
                or returncode != 0
                or stderr
                or not stdout
                or len(stdout) > _MAX_CONFIG_BYTES
            ):
                raise ChronydConfigurationV48BError(
                    "pinned chronyd -p did not return one clean bounded configuration"
                )
            printed_sha256 = hashlib.sha256(stdout).hexdigest()
            if printed_sha256 != launch.printed_config_sha256:
                raise ChronydConfigurationV48BError(
                    "chronyd interpreted configuration differs from signed digest"
                )
            item = cls(
                policy=policy,
                systemd_unit=unit,
                chronyd=chronyd,
                base_config=base,
                source_artifacts=sources,
                effective_config=effective,
                sealed_config=sealed,
                printed_config_sha256=printed_sha256,
                live_profile=live_profile,
                token=cls._CONSTRUCTION_TOKEN,
            )
            opened.clear()
            sealed = None
            try:
                item.assert_unchanged()
            except BaseException:
                item.close()
                raise
            return item
        except BaseException:
            if sealed is not None:
                sealed.close()
            for artifact in reversed(opened):
                try:
                    artifact.close()
                except OSError:
                    pass
            raise

    @property
    def policy(self) -> ClockSourcePolicyManifestV4:
        self.assert_unchanged()
        return self._policy

    @property
    def is_live_profile(self) -> bool:
        return (
            type(self) is PreparedChronydLaunchV48B
            and self._live_profile
            and not self._closed
            and os.getpid() == self._creator_pid
            and threading.get_ident() == self._creator_thread
        )

    @property
    def configured_endpoints(self) -> tuple[str, ...]:
        self.assert_unchanged()
        return self._effective_config.configured_endpoints

    @property
    def chronyd_descriptor(self) -> int:
        self.assert_unchanged()
        return self._chronyd.descriptor

    @property
    def chronyd_proc_fd_path(self) -> str:
        self.assert_unchanged()
        return self._chronyd.proc_fd_path

    @property
    def sealed_config_descriptor(self) -> int:
        self.assert_unchanged()
        return self._sealed_config.descriptor

    @property
    def sealed_config_proc_fd_path(self) -> str:
        self.assert_unchanged()
        return self._sealed_config.proc_fd_path

    def assert_unchanged(self) -> None:
        if (
            self._closed
            or type(self._live_profile) is not bool
            or os.getpid() != self._creator_pid
            or threading.get_ident() != self._creator_thread
        ):
            raise ChronydProvenanceV48BError(
                "prepared chronyd launch left its creating process/thread"
            )
        try:
            self._systemd_unit.assert_unchanged()
            self._chronyd.assert_unchanged()
            self._base_config.assert_unchanged()
            for artifact in self._source_artifacts:
                artifact.assert_unchanged()
            self._sealed_config.assert_sealed()
        except OperationalArtifactV4Error as exc:
            raise ChronydProvenanceV48BError(
                "a retained chronyd launch artifact changed"
            ) from exc
        if (
            self._effective_config.sha256
            != self._policy.chronyd_launch_policy.effective_config_sha256
            or self._printed_config_sha256
            != self._policy.chronyd_launch_policy.printed_config_sha256
            or self._policy.chronyd_launch_policy.fixed_environment_sha256
            != CHRONYD_FIXED_ENVIRONMENT_SHA256
        ):
            raise ChronydProvenanceV48BError(
                "prepared chronyd launch no longer matches its signed policy"
            )

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self._sealed_config.close()
        except OSError:
            pass
        for artifact in reversed(self._source_artifacts):
            try:
                artifact.close()
            except OSError:
                pass
        self._source_artifacts = ()
        for artifact in (self._base_config, self._chronyd, self._systemd_unit):
            try:
                artifact.close()
            except OSError:
                pass

    def __enter__(self) -> PreparedChronydLaunchV48B:
        self.assert_unchanged()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def chronyd_fixed_environment_v48b(*, notify_socket_path: str) -> dict[str, str]:
    """Return the exact child environment plus its private readiness endpoint."""

    path = canonical_identifier(
        notify_socket_path, field="notify_socket_path", maximum=107
    )
    if not path.startswith("/") or posixpath.normpath(path) != path:
        raise ChronydProvenanceV48BError(
            "chronyd notify socket must be a normalized absolute filesystem path"
        )
    environment = dict(_FIXED_CHRONYD_ENVIRONMENT)
    environment["NOTIFY_SOCKET"] = path
    return environment


def current_systemd_invocation_id_v48b() -> str:
    """Read the non-secret per-unit systemd invocation identity fail-closed."""

    value = os.environ.get("INVOCATION_ID")
    if value is None or _SYSTEMD_INVOCATION_ID_RE.fullmatch(value) is None:
        raise ChronydProcessV48BError(
            "dedicated systemd INVOCATION_ID is unavailable or malformed"
        )
    return value


def _enable_passcred(sock: socket.socket) -> None:
    try:
        sock.setsockopt(
            socket.SOL_SOCKET,
            getattr(socket, "SO_PASSCRED", _SO_PASSCRED),
            1,
        )
    except OSError as exc:
        raise ChronydProtocolV48BError(
            "Linux SO_PASSCRED could not be enabled"
        ) from exc


def assert_no_queued_datagram_v48b(sock: socket.socket) -> None:
    readable, _, exceptional = select.select([sock], [], [sock], 0)
    if readable or exceptional:
        raise ChronydProtocolV48BError(
            "credential-authenticated channel contains a residual datagram"
        )


def _boottime_ns_v48b() -> int:
    clock_id = getattr(time, "CLOCK_BOOTTIME", None)
    if clock_id is None:
        raise ChronydProcessV48BError("Linux CLOCK_BOOTTIME is unavailable")
    try:
        value = time.clock_gettime_ns(clock_id)
    except OSError as exc:
        raise ChronydProcessV48BError(
            "Linux CLOCK_BOOTTIME could not be sampled"
        ) from exc
    if type(value) is not int or value < 0:
        raise ChronydProcessV48BError("Linux CLOCK_BOOTTIME sample is invalid")
    return value


def _remaining_deadline_seconds(deadline_ns: int) -> float:
    remaining_ns = deadline_ns - _boottime_ns_v48b()
    if remaining_ns <= 0:
        raise ChronydProtocolV48BError("chronyc query exceeded its global deadline")
    return remaining_ns / 1_000_000_000


def _wait_for_datagram_v48b(
    sock: socket.socket,
    *,
    deadline_ns: int,
    stop: threading.Event,
) -> None:
    while not stop.is_set():
        remaining = _remaining_deadline_seconds(deadline_ns)
        try:
            readable, _, exceptional = select.select(
                [sock], [], [sock], min(remaining, 0.05)
            )
        except OSError as exc:
            raise ChronydProtocolV48BError(
                "credential proxy socket became unavailable"
            ) from exc
        if exceptional:
            raise ChronydProtocolV48BError(
                "credential proxy socket entered an exceptional state"
            )
        if readable:
            return
    raise ChronydProtocolV48BError("credential proxy was cancelled")


def _send_datagram_v48b(
    sock: socket.socket,
    payload: bytes,
    *,
    deadline_ns: int,
    stop: threading.Event,
    address: str | bytes | None = None,
) -> None:
    while not stop.is_set():
        try:
            sent = (
                sock.send(payload) if address is None else sock.sendto(payload, address)
            )
        except BlockingIOError:
            remaining = _remaining_deadline_seconds(deadline_ns)
            try:
                _, writable, exceptional = select.select(
                    [], [sock], [sock], min(remaining, 0.05)
                )
            except OSError as exc:
                raise ChronydProtocolV48BError(
                    "credential proxy send socket became unavailable"
                ) from exc
            if exceptional:
                raise ChronydProtocolV48BError(
                    "credential proxy send socket entered an exceptional state"
                ) from None
            if not writable:
                continue
        except OSError as exc:
            raise ChronydProtocolV48BError(
                "credential proxy datagram could not be sent"
            ) from exc
        else:
            if sent != len(payload):
                raise ChronydProtocolV48BError(
                    "credential proxy sent a partial Unix datagram"
                )
            return
    raise ChronydProtocolV48BError("credential proxy was cancelled")


def _collect_bounded_process_output_v48b(
    proc: subprocess.Popen[bytes],
    *,
    deadline_ns: int,
    maximum_output_bytes: int,
) -> tuple[int, bytes, bytes]:
    if proc.stdout is None or proc.stderr is None:
        raise ChronydProtocolV48BError("pinned chronyc pipes were not created")
    selector: selectors.BaseSelector | None = None
    buffers: dict[str, bytearray] = {"stdout": bytearray(), "stderr": bytearray()}
    try:
        selector = selectors.DefaultSelector()
        selector.register(proc.stdout, selectors.EVENT_READ, "stdout")
        selector.register(proc.stderr, selectors.EVENT_READ, "stderr")
        while selector.get_map():
            remaining = _remaining_deadline_seconds(deadline_ns)
            events = selector.select(min(remaining, 0.05))
            if not events:
                continue
            for key, _ in events:
                try:
                    chunk = os.read(key.fd, 8_192)
                except OSError as exc:
                    raise ChronydProtocolV48BError(
                        "pinned chronyc output could not be read"
                    ) from exc
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                buffers[key.data].extend(chunk)
                if sum(len(value) for value in buffers.values()) > maximum_output_bytes:
                    raise ChronydProtocolV48BError(
                        "pinned chronyc output exceeded its signed byte cap"
                    )
        try:
            returncode = proc.wait(timeout=_remaining_deadline_seconds(deadline_ns))
        except subprocess.TimeoutExpired as exc:
            raise ChronydProtocolV48BError(
                "pinned chronyc exceeded the global query deadline"
            ) from exc
    finally:
        if selector is not None:
            selector.close()
        proc.stdout.close()
        proc.stderr.close()
    return returncode, bytes(buffers["stdout"]), bytes(buffers["stderr"])


def _pidfd_open(pid: int) -> int:
    native = getattr(os, "pidfd_open", None)
    if callable(native):
        return native(pid, 0)
    function = _libc_function("pidfd_open")
    function.argtypes = (ctypes.c_int, ctypes.c_uint)
    function.restype = ctypes.c_int
    fd = function(pid, 0)
    if fd < 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))
    return fd


def _pidfd_is_alive(pidfd: int) -> bool:
    poller = select.poll()
    poller.register(pidfd, select.POLLIN | select.POLLERR | select.POLLHUP)
    try:
        events = poller.poll(0)
    except OSError as exc:
        raise ChronydProcessV48BError("retained chronyd pidfd is unusable") from exc
    return not events


def _pidfd_send_signal(pidfd: int, signal_number: int) -> None:
    native = getattr(signal, "pidfd_send_signal", None)
    if callable(native):
        native(pidfd, signal_number, None, 0)
        return
    function = _libc_function("pidfd_send_signal")
    function.argtypes = (
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_void_p,
        ctypes.c_uint,
    )
    function.restype = ctypes.c_int
    if function(pidfd, signal_number, None, 0) < 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))


def _read_bounded_proc_file(path: str, *, maximum_bytes: int) -> bytes:
    try:
        fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC)
    except OSError as exc:
        raise ChronydProcessV48BError(
            f"required process evidence {path!r} is unavailable"
        ) from exc
    try:
        raw = os.read(fd, maximum_bytes + 1)
    except OSError as exc:
        raise ChronydProcessV48BError(
            f"required process evidence {path!r} could not be read"
        ) from exc
    finally:
        os.close(fd)
    if not raw or len(raw) > maximum_bytes:
        raise ChronydProcessV48BError(
            f"required process evidence {path!r} is empty or oversized"
        )
    return raw


def _read_kernel_boot_id() -> str:
    raw = _read_bounded_proc_file("/proc/sys/kernel/random/boot_id", maximum_bytes=64)
    if _BOOT_ID_RE.fullmatch(raw) is None:
        raise ChronydProcessV48BError("kernel boot ID is malformed")
    return raw.rstrip(b"\n").decode("ascii")


def _read_process_start_ticks(pid: int) -> int:
    raw = _read_bounded_proc_file(f"/proc/{pid}/stat", maximum_bytes=16_384)
    boundary = raw.rfind(b") ")
    if boundary < 0:
        raise ChronydProcessV48BError("chronyd /proc stat is malformed")
    fields = raw[boundary + 2 :].split()
    # The tail begins with field 3 (state); starttime is field 22.
    if len(fields) <= 19 or not fields[19].isdigit():
        raise ChronydProcessV48BError("chronyd start-time field is malformed")
    return int(fields[19])


def _read_process_parent_pid(pid: int) -> int:
    raw = _read_bounded_proc_file(f"/proc/{pid}/stat", maximum_bytes=16_384)
    boundary = raw.rfind(b") ")
    if boundary < 0:
        raise ChronydProcessV48BError("chronyd /proc stat is malformed")
    fields = raw[boundary + 2 :].split()
    # The tail begins with field 3 (state); PPID is field 4.
    if len(fields) <= 1 or not fields[1].isdigit():
        raise ChronydProcessV48BError("chronyd parent-PID field is malformed")
    return int(fields[1])


def _read_process_cgroup_sha256(pid: int) -> str:
    process_raw = _read_bounded_proc_file(
        f"/proc/{pid}/cgroup", maximum_bytes=64 * 1024
    )
    supervisor_raw = _read_bounded_proc_file(
        "/proc/self/cgroup", maximum_bytes=64 * 1024
    )
    if (
        process_raw != supervisor_raw
        or b"\x00" in process_raw
        or not process_raw.endswith(b"\n")
    ):
        raise ChronydProcessV48BError(
            "chronyd process is outside the exact supervisor cgroup"
        )
    try:
        process_raw.decode("ascii", errors="strict")
    except UnicodeDecodeError as exc:
        raise ChronydProcessV48BError("chronyd cgroup record is malformed") from exc
    return hashlib.sha256(process_raw).hexdigest()


@dataclass(frozen=True, slots=True, kw_only=True)
class _ChronydProcessSecurityV48B:
    supplementary_gids: tuple[int, ...]
    umask: int
    cap_inheritable: int
    cap_permitted: int
    cap_effective: int
    cap_bounding: int
    cap_ambient: int
    no_new_privileges: int
    seccomp_mode: int
    seccomp_filter_count: int
    core_dumping: int


def _read_process_ids(
    pid: int,
) -> tuple[int, int, _ChronydProcessSecurityV48B]:
    raw = _read_bounded_proc_file(f"/proc/{pid}/status", maximum_bytes=64 * 1024)
    values: dict[bytes, tuple[int, ...]] = {}
    scalar_values: dict[bytes, bytes] = {}
    for line in raw.splitlines():
        if line.startswith((b"Uid:\t", b"Gid:\t")):
            name, data = line.split(b":", 1)
            try:
                values[name] = tuple(int(item) for item in data.split())
            except ValueError as exc:
                raise ChronydProcessV48BError(
                    "chronyd status credentials are malformed"
                ) from exc
        elif b":" in line:
            name, data = line.split(b":", 1)
            if name in scalar_values:
                raise ChronydProcessV48BError(
                    "chronyd status contains a duplicate security field"
                )
            scalar_values[name] = data.strip()
    uid_values = values.get(b"Uid")
    gid_values = values.get(b"Gid")
    if (
        uid_values is None
        or gid_values is None
        or len(uid_values) != 4
        or len(gid_values) != 4
        or len(set(uid_values)) != 1
        or len(set(gid_values)) != 1
    ):
        raise ChronydProcessV48BError(
            "chronyd did not fully drop all real/effective/saved/fs credentials"
        )
    try:
        groups = tuple(int(item) for item in scalar_values[b"Groups"].split())
        umask_raw = scalar_values[b"Umask"]
        no_new_privileges = int(scalar_values[b"NoNewPrivs"])
        seccomp_mode = int(scalar_values[b"Seccomp"])
        seccomp_filter_count = int(scalar_values[b"Seccomp_filters"])
        core_dumping = int(scalar_values[b"CoreDumping"])
        capability_raw = {
            name: scalar_values[name]
            for name in (b"CapInh", b"CapPrm", b"CapEff", b"CapBnd", b"CapAmb")
        }
    except (KeyError, ValueError) as exc:
        raise ChronydProcessV48BError(
            "chronyd status security posture is incomplete or malformed"
        ) from exc
    if (
        len(umask_raw) != 4
        or any(byte not in b"01234567" for byte in umask_raw)
        or any(
            _CAPABILITY_HEX_RE.fullmatch(value) is None
            for value in capability_raw.values()
        )
    ):
        raise ChronydProcessV48BError(
            "chronyd status security encoding is noncanonical"
        )
    security = _ChronydProcessSecurityV48B(
        supplementary_gids=groups,
        umask=int(umask_raw, 8),
        cap_inheritable=int(capability_raw[b"CapInh"], 16),
        cap_permitted=int(capability_raw[b"CapPrm"], 16),
        cap_effective=int(capability_raw[b"CapEff"], 16),
        cap_bounding=int(capability_raw[b"CapBnd"], 16),
        cap_ambient=int(capability_raw[b"CapAmb"], 16),
        no_new_privileges=no_new_privileges,
        seccomp_mode=seccomp_mode,
        seccomp_filter_count=seccomp_filter_count,
        core_dumping=core_dumping,
    )
    if (
        security.supplementary_gids
        or security.umask & 0o022 != 0o022
        or security.cap_inheritable != 0
        or security.cap_permitted != _REQUIRED_CHRONYD_CAPABILITY_MASK
        or security.cap_effective != _REQUIRED_CHRONYD_CAPABILITY_MASK
        or security.cap_bounding != _REQUIRED_CHRONYD_CAPABILITY_MASK
        or security.cap_ambient != 0
        or security.no_new_privileges != 1
        or security.seccomp_mode != 2
        or security.seccomp_filter_count < 1
        or security.core_dumping != 0
    ):
        raise ChronydProcessV48BError(
            "chronyd process privilege or sandbox posture differs from profile"
        )
    return uid_values[0], gid_values[0], security


def _process_ids_with_effective_uid(uid: int) -> tuple[int, ...]:
    matches: list[int] = []
    scanned = 0
    try:
        entries = os.scandir("/proc")
    except OSError as exc:
        raise ChronydProcessV48BError(
            "process table is unavailable for dedicated-UID validation"
        ) from exc
    with entries:
        for entry in entries:
            if not entry.name.isdecimal():
                continue
            scanned += 1
            if scanned > 1_000_000:
                raise ChronydProcessV48BError(
                    "process table exceeds the dedicated-UID scan bound"
                )
            pid = int(entry.name)
            try:
                fd = os.open(
                    f"/proc/{pid}/status",
                    os.O_RDONLY | os.O_CLOEXEC,
                )
            except (FileNotFoundError, ProcessLookupError):
                continue
            except OSError as exc:
                raise ChronydProcessV48BError(
                    "a process credential could not be audited"
                ) from exc
            try:
                raw = os.read(fd, 64 * 1024 + 1)
            except (FileNotFoundError, ProcessLookupError):
                continue
            except OSError as exc:
                raise ChronydProcessV48BError(
                    "a process credential could not be read"
                ) from exc
            finally:
                os.close(fd)
            if not raw or len(raw) > 64 * 1024:
                raise ChronydProcessV48BError(
                    "a process credential record is empty or oversized"
                )
            uid_lines = [
                line for line in raw.splitlines() if line.startswith(b"Uid:\t")
            ]
            if len(uid_lines) != 1:
                raise ChronydProcessV48BError(
                    "a process credential record has ambiguous UIDs"
                )
            try:
                values = tuple(
                    int(item) for item in uid_lines[0].split(b":", 1)[1].split()
                )
            except ValueError as exc:
                raise ChronydProcessV48BError(
                    "a process credential record has malformed UIDs"
                ) from exc
            if len(values) != 4:
                raise ChronydProcessV48BError(
                    "a process credential record has an invalid UID cardinality"
                )
            if values[1] == uid:
                matches.append(pid)
    return tuple(sorted(matches))


def _assert_exclusive_post_drop_uid(
    *, uid: int, expected_process_ids: tuple[int, ...]
) -> None:
    if _process_ids_with_effective_uid(uid) != expected_process_ids:
        raise ChronydProcessV48BError(
            "chronyd post-drop UID is not dedicated to the retained daemon"
        )


def _read_process_lsm_profile(pid: int) -> str:
    raw = _read_bounded_proc_file(f"/proc/{pid}/attr/current", maximum_bytes=4_096)
    if b"\x00" in raw:
        raise ChronydProcessV48BError("chronyd LSM profile contains a NUL byte")
    try:
        value = raw.rstrip(b"\n").decode("ascii", errors="strict")
    except UnicodeDecodeError as exc:
        raise ChronydProcessV48BError(
            "chronyd LSM profile is not strict ASCII"
        ) from exc
    return canonical_identifier(value, field="loaded_chronyd_lsm_profile", maximum=512)


def _process_namespace_identity(pid: int, name: str) -> tuple[int, int]:
    path = f"/proc/{pid}/ns/{name}"
    try:
        fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC)
        try:
            info = os.fstat(fd)
        finally:
            os.close(fd)
    except OSError as exc:
        raise ChronydProcessV48BError(
            f"chronyd {name} namespace could not be retained"
        ) from exc
    if info.st_dev < 0 or info.st_ino <= 0:
        raise ChronydProcessV48BError(f"chronyd {name} namespace identity is invalid")
    return info.st_dev, info.st_ino


def _stat_process_executable(pid: int) -> tuple[int, int]:
    try:
        info = os.stat(f"/proc/{pid}/exe", follow_symlinks=True)
    except OSError as exc:
        raise ChronydProcessV48BError(
            "loaded chronyd executable identity is unavailable"
        ) from exc
    if not stat.S_ISREG(info.st_mode):
        raise ChronydProcessV48BError("loaded chronyd executable is not regular")
    return info.st_dev, info.st_ino


@dataclass(frozen=True, slots=True, kw_only=True)
class _ChronydProcessSnapshotV48B:
    kernel_boot_id: str
    pid: int
    parent_pid: int
    start_time_ticks: int
    uid: int
    gid: int
    security: _ChronydProcessSecurityV48B
    executable_device: int
    executable_inode: int
    cgroup_sha256: str
    lsm_profile: str
    mount_namespace: tuple[int, int]
    network_namespace: tuple[int, int]
    pid_namespace: tuple[int, int]
    time_namespace: tuple[int, int]
    user_namespace: tuple[int, int]


def _snapshot_chronyd_process(*, pid: int) -> _ChronydProcessSnapshotV48B:
    executable = _stat_process_executable(pid)
    uid, gid, security = _read_process_ids(pid)
    return _ChronydProcessSnapshotV48B(
        kernel_boot_id=_read_kernel_boot_id(),
        pid=pid,
        parent_pid=_read_process_parent_pid(pid),
        start_time_ticks=_read_process_start_ticks(pid),
        uid=uid,
        gid=gid,
        security=security,
        executable_device=executable[0],
        executable_inode=executable[1],
        cgroup_sha256=_read_process_cgroup_sha256(pid),
        lsm_profile=_read_process_lsm_profile(pid),
        mount_namespace=_process_namespace_identity(pid, "mnt"),
        network_namespace=_process_namespace_identity(pid, "net"),
        pid_namespace=_process_namespace_identity(pid, "pid"),
        time_namespace=_process_namespace_identity(pid, "time"),
        user_namespace=_process_namespace_identity(pid, "user"),
    )


@dataclass(frozen=True, slots=True, kw_only=True)
class _ChronydCommandSocketSnapshotV48B:
    device: int
    inode: int
    uid: int
    gid: int
    mode: int


def _unlink_matching_socket(path: str, *, device: int, inode: int) -> None:
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        return
    except OSError:
        return
    if stat.S_ISSOCK(info.st_mode) and (info.st_dev, info.st_ino) == (device, inode):
        try:
            os.unlink(path)
        except OSError:
            pass


def _snapshot_command_socket(
    path: str,
    *,
    expected_uid: int,
    expected_gid: int,
    expected_mode: int = _CHRONYD_SEALED_SOCKET_MODE,
) -> _ChronydCommandSocketSnapshotV48B:
    try:
        info = os.lstat(path)
    except OSError as exc:
        raise ChronydProcessV48BError(
            "chronyd command socket is unavailable after authenticated READY"
        ) from exc
    mode = stat.S_IMODE(info.st_mode)
    if (
        not stat.S_ISSOCK(info.st_mode)
        or info.st_uid != expected_uid
        or info.st_gid != expected_gid
        or mode != expected_mode
    ):
        raise ChronydProcessV48BError(
            "chronyd command socket type, credentials, or mode differ from profile"
        )
    return _ChronydCommandSocketSnapshotV48B(
        device=info.st_dev,
        inode=info.st_ino,
        uid=info.st_uid,
        gid=info.st_gid,
        mode=mode,
    )


def _seal_command_socket_authority(
    *,
    policy: ChronydLaunchPolicyV48B,
    chronyd_directory_fd: int,
) -> _ChronydCommandSocketSnapshotV48B:
    """Freeze pathname mutation, take root ownership, and preserve socket inode."""

    os.fchmod(chronyd_directory_fd, 0o500)
    initial = _snapshot_command_socket(
        policy.real_command_socket_path,
        expected_uid=policy.post_drop_uid,
        expected_gid=policy.post_drop_gid,
        expected_mode=_CHRONYD_INITIAL_SOCKET_MODE,
    )
    os.fchown(chronyd_directory_fd, 0, 0)
    os.fchmod(chronyd_directory_fd, 0o700)
    frozen = _snapshot_command_socket(
        policy.real_command_socket_path,
        expected_uid=policy.post_drop_uid,
        expected_gid=policy.post_drop_gid,
        expected_mode=_CHRONYD_INITIAL_SOCKET_MODE,
    )
    if frozen != initial:
        raise ChronydProcessV48BError(
            "chronyd command socket changed while its directory was frozen"
        )
    os.chown(
        policy.real_command_socket_path,
        0,
        0,
        follow_symlinks=False,
    )
    os.chmod(
        policy.real_command_socket_path,
        _CHRONYD_SEALED_SOCKET_MODE,
        follow_symlinks=False,
    )
    sealed = _snapshot_command_socket(
        policy.real_command_socket_path,
        expected_uid=0,
        expected_gid=0,
    )
    if (sealed.device, sealed.inode) != (initial.device, initial.inode):
        raise ChronydProcessV48BError(
            "chronyd command socket changed while sealing its authority"
        )
    return sealed


def _runtime_directory_requirements(
    policy: ChronydLaunchPolicyV48B, *, sealed: bool
) -> tuple[tuple[str, int, int, int], ...]:
    return (
        (policy.runtime_directory_path, 0, 0, 0o711),
        (
            policy.chronyd_socket_directory_path,
            0 if sealed else policy.post_drop_uid,
            0 if sealed else policy.post_drop_gid,
            0o700,
        ),
        (
            policy.supervisor_socket_directory_path,
            0,
            policy.post_drop_gid,
            0o710,
        ),
    )


def _validate_runtime_directories(
    policy: ChronydLaunchPolicyV48B,
) -> tuple[tuple[int, ...], tuple[tuple[int, int], ...]]:
    reviewed = _runtime_directory_requirements(policy, sealed=False)
    flags = os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_DIRECTORY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptors: list[int] = []
    identities: list[tuple[int, int]] = []
    try:
        for path, expected_uid, expected_gid, expected_mode in reviewed:
            if os.path.realpath(path) != path:
                raise ChronydProcessV48BError(
                    "chronyd runtime topology contains a symbolic-link component"
                )
            try:
                fd = os.open(path, flags)
            except OSError as exc:
                raise ChronydProcessV48BError(
                    "dedicated chronyd runtime topology is unavailable"
                ) from exc
            descriptors.append(fd)
            os.set_inheritable(fd, False)
            info = os.fstat(fd)
            if (
                not stat.S_ISDIR(info.st_mode)
                or stat.S_IMODE(info.st_mode) != expected_mode
                or info.st_uid != expected_uid
                or info.st_gid != expected_gid
            ):
                raise ChronydProcessV48BError(
                    "chronyd runtime topology owner or mode differs from profile"
                )
            identities.append((info.st_dev, info.st_ino))
        return tuple(descriptors), tuple(identities)
    except BaseException:
        for fd in reversed(descriptors):
            os.close(fd)
        raise


def _assert_runtime_directories_current(
    *,
    policy: ChronydLaunchPolicyV48B,
    descriptors: tuple[int, ...],
    identities: tuple[tuple[int, int], ...],
) -> None:
    reviewed = _runtime_directory_requirements(policy, sealed=True)
    if len(descriptors) != len(reviewed) or len(identities) != len(reviewed):
        raise ChronydProcessV48BError(
            "retained chronyd runtime topology has an invalid cardinality"
        )
    for (
        path,
        expected_uid,
        expected_gid,
        expected_mode,
    ), descriptor, expected_identity in zip(
        reviewed,
        descriptors,
        identities,
        strict=True,
    ):
        if os.path.realpath(path) != path:
            raise ChronydProcessV48BError(
                "chronyd runtime topology gained a symbolic-link component"
            )
        try:
            retained = os.fstat(descriptor)
            current_path = os.lstat(path)
        except OSError as exc:
            raise ChronydProcessV48BError(
                "retained chronyd runtime topology is unavailable"
            ) from exc
        identity = (retained.st_dev, retained.st_ino)
        if (
            os.get_inheritable(descriptor)
            or not stat.S_ISDIR(retained.st_mode)
            or not stat.S_ISDIR(current_path.st_mode)
            or identity != expected_identity
            or (current_path.st_dev, current_path.st_ino) != expected_identity
            or retained.st_uid != expected_uid
            or retained.st_gid != expected_gid
            or stat.S_IMODE(retained.st_mode) != expected_mode
            or current_path.st_uid != expected_uid
            or current_path.st_gid != expected_gid
            or stat.S_IMODE(current_path.st_mode) != expected_mode
        ):
            raise ChronydProcessV48BError(
                "retained chronyd runtime path, owner, mode, or identity changed"
            )


def _assert_systemd_supervisor_context(policy: ChronydLaunchPolicyV48B) -> str:
    invocation_id = current_systemd_invocation_id_v48b()
    invocation_path = f"/run/systemd/units/invocation:{policy.systemd_unit_name}"
    try:
        manager_invocation_id = os.readlink(invocation_path)
    except OSError as exc:
        raise ChronydProcessV48BError(
            "systemd unit invocation mapping is unavailable"
        ) from exc
    if manager_invocation_id != invocation_id:
        raise ChronydProcessV48BError(
            "systemd manager invocation differs from supervisor environment"
        )
    cgroup = _read_bounded_proc_file("/proc/self/cgroup", maximum_bytes=64 * 1024)
    try:
        cgroup_text = cgroup.decode("ascii", errors="strict")
    except UnicodeDecodeError as exc:
        raise ChronydProcessV48BError(
            "supervisor cgroup identity is malformed"
        ) from exc
    if not any(
        policy.systemd_unit_name in line.split(":", 2)[-1].split("/")
        for line in cgroup_text.splitlines()
    ):
        raise ChronydProcessV48BError(
            "supervisor process is outside the signed systemd unit cgroup"
        )
    return invocation_id


def _terminate_owned_process(
    proc: subprocess.Popen[bytes], *, pidfd: int | None = None
) -> None:
    if proc.poll() is None:
        try:
            if pidfd is None:
                proc.send_signal(signal.SIGTERM)
            else:
                _pidfd_send_signal(pidfd, signal.SIGTERM)
            proc.wait(timeout=2)
        except (OSError, subprocess.TimeoutExpired):
            try:
                if pidfd is None:
                    proc.kill()
                else:
                    _pidfd_send_signal(pidfd, signal.SIGKILL)
            except OSError:
                pass
    try:
        proc.wait(timeout=1)
    except (OSError, subprocess.TimeoutExpired):
        pass


@dataclass(frozen=True, slots=True, kw_only=True)
class AuthenticatedChronycQueryV48B:
    stdout: bytes
    transcript: AuthenticatedChronyTranscriptV48B
    launch_id: str
    runtime_observation_sha256: str
    query_observation_sha256: str
    configured_endpoints: tuple[str, ...]

    def __post_init__(self) -> None:
        if type(self.stdout) is not bytes or not self.stdout:
            raise ChronydProtocolV48BError("authenticated chronyc output is empty")
        for field_name in (
            "launch_id",
            "runtime_observation_sha256",
            "query_observation_sha256",
        ):
            canonical_hash(getattr(self, field_name), field=field_name)


class ChronydLaunchAuthorityV48B:
    """One exact owned chronyd launch, pidfd, socket, and query capability."""

    _CONSTRUCTION_TOKEN = object()

    def __init__(
        self,
        *,
        prepared: PreparedChronydLaunchV48B,
        process: subprocess.Popen[bytes],
        pidfd: int,
        notify_socket: socket.socket,
        notify_socket_identity: tuple[int, int],
        runtime_directory_fds: tuple[int, ...],
        runtime_directory_identities: tuple[tuple[int, int], ...],
        supervisor_invocation_id: str,
        process_snapshot: _ChronydProcessSnapshotV48B,
        command_socket_snapshot: _ChronydCommandSocketSnapshotV48B,
        launch_id: str,
        runtime_observation_sha256: str,
        token: object,
    ) -> None:
        if token is not self._CONSTRUCTION_TOKEN:
            raise TypeError("chronyd launch authority cannot be caller-constructed")
        self._prepared = prepared
        self._policy = prepared.policy
        self._process = process
        self._pidfd = pidfd
        self._notify_socket = notify_socket
        self._notify_socket_identity = notify_socket_identity
        self._runtime_directory_fds = runtime_directory_fds
        self._runtime_directory_identities = runtime_directory_identities
        self._supervisor_invocation_id = supervisor_invocation_id
        self._process_snapshot = process_snapshot
        self._command_socket_snapshot = command_socket_snapshot
        self._launch_id = canonical_hash(launch_id, field="chronyd_launch_id")
        self._runtime_observation_sha256 = canonical_hash(
            runtime_observation_sha256, field="chronyd_runtime_observation_sha256"
        )
        self._creator_pid = os.getpid()
        self._creator_thread = threading.get_ident()
        self._closed = False
        self._faulted = False
        self._query_active = False

    @classmethod
    def launch(cls, prepared: PreparedChronydLaunchV48B) -> ChronydLaunchAuthorityV48B:
        """Launch only from an exact prepared closure in its signed systemd unit."""

        if type(prepared) is not PreparedChronydLaunchV48B:
            raise TypeError("prepared must be an exact PreparedChronydLaunchV48B")
        prepared.assert_unchanged()
        if not prepared.is_live_profile:
            raise ChronydProcessV48BError(
                "chronyd authority requires a production prepared closure"
            )
        policy = prepared.policy.chronyd_launch_policy
        invocation_id = _assert_systemd_supervisor_context(policy)
        try:
            account = pwd.getpwnam(policy.post_drop_user_name)
        except KeyError as exc:
            raise ChronydProcessV48BError(
                "signed chronyd post-drop account does not exist"
            ) from exc
        if (account.pw_uid, account.pw_gid) != (
            policy.post_drop_uid,
            policy.post_drop_gid,
        ):
            raise ChronydProcessV48BError(
                "chronyd post-drop account mapping differs from signed UID/GID"
            )
        if os.geteuid() != 0 or os.getegid() != 0:
            raise ChronydProcessV48BError(
                "dedicated chronyd supervisor must start with root credentials"
            )
        _assert_exclusive_post_drop_uid(
            uid=policy.post_drop_uid,
            expected_process_ids=(),
        )
        runtime_fds: tuple[int, ...] = ()
        notify: socket.socket | None = None
        notify_identity: tuple[int, int] | None = None
        command_socket_identity: tuple[int, int] | None = None
        proc: subprocess.Popen[bytes] | None = None
        pidfd: int | None = None
        try:
            runtime_fds, runtime_identities = _validate_runtime_directories(policy)
            for path in (
                policy.real_command_socket_path,
                policy.notify_socket_path,
                policy.read_only_api_socket_path,
            ):
                if os.path.lexists(path):
                    raise ChronydProcessV48BError(
                        "dedicated chronyd runtime socket path is not fresh"
                    )
            notify = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
            _enable_passcred(notify)
            notify.bind(policy.notify_socket_path)
            os.chown(policy.notify_socket_path, 0, policy.post_drop_gid)
            os.chmod(policy.notify_socket_path, 0o620)
            notify_info = os.lstat(policy.notify_socket_path)
            notify_identity = (notify_info.st_dev, notify_info.st_ino)
            notify.settimeout(policy.ready_timeout_milliseconds / 1_000)
            environment = chronyd_fixed_environment_v48b(
                notify_socket_path=policy.notify_socket_path
            )
            proc = subprocess.Popen(  # noqa: S603 - exact retained fd and argv
                (
                    prepared.chronyd_proc_fd_path,
                    "-n",
                    "-f",
                    prepared.sealed_config_proc_fd_path,
                    "-F",
                    "1",
                    "-u",
                    policy.post_drop_user_name,
                ),
                stdin=subprocess.DEVNULL,
                stdout=None,
                stderr=None,
                close_fds=True,
                pass_fds=(
                    prepared.chronyd_descriptor,
                    prepared.sealed_config_descriptor,
                ),
                env=environment,
                shell=False,
                start_new_session=False,
            )
            try:
                pidfd = _pidfd_open(proc.pid)
                os.set_inheritable(pidfd, False)
            except OSError as exc:
                raise ChronydProcessV48BError(
                    "chronyd pidfd could not be retained"
                ) from exc
            if not _pidfd_is_alive(pidfd):
                raise ChronydProcessV48BError(
                    "chronyd exited before authenticated readiness"
                )
            ready, _ = receive_authenticated_datagram_v48b(
                notify,
                maximum_bytes=64,
                expected_pid=proc.pid,
                expected_uid=policy.post_drop_uid,
                expected_gid=policy.post_drop_gid,
            )
            if ready != b"READY=1":
                raise ChronydProcessV48BError(
                    "chronyd readiness payload differs from exact READY=1"
                )
            assert_no_queued_datagram_v48b(notify)
            if not _pidfd_is_alive(pidfd):
                raise ChronydProcessV48BError(
                    "chronyd exited during authenticated readiness"
                )
            process_snapshot = _snapshot_chronyd_process(pid=proc.pid)
            _assert_exclusive_post_drop_uid(
                uid=policy.post_drop_uid,
                expected_process_ids=(proc.pid,),
            )
            expected_executable = os.fstat(prepared.chronyd_descriptor)
            if (
                (process_snapshot.uid, process_snapshot.gid)
                != (policy.post_drop_uid, policy.post_drop_gid)
                or process_snapshot.parent_pid != os.getpid()
                or process_snapshot.lsm_profile != policy.lsm_profile
                or (
                    process_snapshot.executable_device,
                    process_snapshot.executable_inode,
                )
                != (expected_executable.st_dev, expected_executable.st_ino)
            ):
                raise ChronydProcessV48BError(
                    "loaded chronyd process differs from signed launch closure"
                )
            if len(runtime_fds) != 3:
                raise ChronydProcessV48BError(
                    "chronyd runtime topology has an invalid descriptor count"
                )
            chronyd_directory_fd = runtime_fds[1]
            command_socket = _seal_command_socket_authority(
                policy=policy,
                chronyd_directory_fd=chronyd_directory_fd,
            )
            command_socket_identity = (
                command_socket.device,
                command_socket.inode,
            )
            _assert_runtime_directories_current(
                policy=policy,
                descriptors=runtime_fds,
                identities=runtime_identities,
            )
            launch_id = sha256_digest(
                {
                    "boot_id": process_snapshot.kernel_boot_id,
                    "chronyd_executable_sha256": policy.chronyd_executable_sha256,
                    "chronyd_pid": process_snapshot.pid,
                    "chronyd_start_time_ticks": process_snapshot.start_time_ticks,
                    "domain": "RiskYieldMMChronydLaunchIdentityV48B",
                    "effective_config_sha256": policy.effective_config_sha256,
                    "printed_config_sha256": policy.printed_config_sha256,
                    "supervisor_invocation_id": invocation_id,
                    "systemd_unit_sha256": policy.systemd_unit_sha256,
                }
            )
            runtime_observation = sha256_digest(
                {
                    "command_socket": {
                        "device": command_socket.device,
                        "gid": command_socket.gid,
                        "inode": command_socket.inode,
                        "mode": command_socket.mode,
                        "uid": command_socket.uid,
                    },
                    "domain": "RiskYieldMMChronydRuntimeObservationV48B",
                    "launch_id": launch_id,
                    "lsm_profile": process_snapshot.lsm_profile,
                    "process_cgroup_sha256": process_snapshot.cgroup_sha256,
                    "mount_namespace": list(process_snapshot.mount_namespace),
                    "network_namespace": list(process_snapshot.network_namespace),
                    "pid_namespace": list(process_snapshot.pid_namespace),
                    "process_security": {
                        "cap_ambient": process_snapshot.security.cap_ambient,
                        "cap_bounding": process_snapshot.security.cap_bounding,
                        "cap_effective": process_snapshot.security.cap_effective,
                        "cap_inheritable": process_snapshot.security.cap_inheritable,
                        "cap_permitted": process_snapshot.security.cap_permitted,
                        "core_dumping": process_snapshot.security.core_dumping,
                        "no_new_privileges": (
                            process_snapshot.security.no_new_privileges
                        ),
                        "seccomp_filter_count": (
                            process_snapshot.security.seccomp_filter_count
                        ),
                        "seccomp_mode": process_snapshot.security.seccomp_mode,
                        "supplementary_gids": list(
                            process_snapshot.security.supplementary_gids
                        ),
                        "umask": process_snapshot.security.umask,
                    },
                    "runtime_directories": [
                        list(identity) for identity in runtime_identities
                    ],
                    "time_namespace": list(process_snapshot.time_namespace),
                    "user_namespace": list(process_snapshot.user_namespace),
                }
            )
            item = cls(
                prepared=prepared,
                process=proc,
                pidfd=pidfd,
                notify_socket=notify,
                notify_socket_identity=notify_identity,
                runtime_directory_fds=runtime_fds,
                runtime_directory_identities=runtime_identities,
                supervisor_invocation_id=invocation_id,
                process_snapshot=process_snapshot,
                command_socket_snapshot=command_socket,
                launch_id=launch_id,
                runtime_observation_sha256=runtime_observation,
                token=cls._CONSTRUCTION_TOKEN,
            )
            proc = None
            pidfd = None
            notify = None
            runtime_fds = ()
            try:
                item.assert_provenance_current()
            except BaseException:
                item.close()
                raise
            return item
        except BaseException:
            if proc is not None:
                _terminate_owned_process(proc, pidfd=pidfd)
            if pidfd is not None:
                os.close(pidfd)
            if notify is not None:
                notify.close()
            if notify_identity is not None:
                _unlink_matching_socket(
                    policy.notify_socket_path,
                    device=notify_identity[0],
                    inode=notify_identity[1],
                )
            if command_socket_identity is not None:
                _unlink_matching_socket(
                    policy.real_command_socket_path,
                    device=command_socket_identity[0],
                    inode=command_socket_identity[1],
                )
            if len(runtime_fds) == 3 and os.geteuid() == 0:
                try:
                    os.fchown(
                        runtime_fds[1],
                        policy.post_drop_uid,
                        policy.post_drop_gid,
                    )
                    os.fchmod(runtime_fds[1], 0o700)
                except OSError:
                    pass
            for runtime_fd in reversed(runtime_fds):
                os.close(runtime_fd)
            raise

    @property
    def launch_id(self) -> str:
        self.assert_instance_current()
        return self._launch_id

    @property
    def policy(self) -> ClockSourcePolicyManifestV4:
        self.assert_provenance_current()
        return self._policy

    @property
    def runtime_observation_sha256(self) -> str:
        self.assert_instance_current()
        return self._runtime_observation_sha256

    @property
    def configured_endpoints(self) -> tuple[str, ...]:
        self.assert_provenance_current()
        return self._prepared.configured_endpoints

    @property
    def is_live_profile(self) -> bool:
        return (
            type(self) is ChronydLaunchAuthorityV48B
            and not self._closed
            and not self._faulted
        )

    def _assert_context(self) -> None:
        if (
            self._closed
            or self._faulted
            or os.getpid() != self._creator_pid
            or threading.get_ident() != self._creator_thread
        ):
            raise ChronydProcessV48BError(
                "chronyd launch authority left its creating process/thread"
            )

    def _latch_fault(self) -> None:
        self._faulted = True

    def assert_instance_current(self) -> None:
        self._assert_context()
        try:
            if (
                self._process.poll() is not None
                or not _pidfd_is_alive(self._pidfd)
                or _read_process_start_ticks(self._process.pid)
                != self._process_snapshot.start_time_ticks
                or _snapshot_command_socket(
                    self._policy.chronyd_launch_policy.real_command_socket_path,
                    expected_uid=0,
                    expected_gid=0,
                )
                != self._command_socket_snapshot
            ):
                raise ChronydProcessV48BError(
                    "retained chronyd process/socket instance changed"
                )
        except BaseException:
            self._latch_fault()
            raise

    def assert_provenance_current(self) -> None:
        self.assert_instance_current()
        try:
            self._prepared.assert_unchanged()
            if (
                current_systemd_invocation_id_v48b() != self._supervisor_invocation_id
                or _assert_systemd_supervisor_context(
                    self._policy.chronyd_launch_policy
                )
                != self._supervisor_invocation_id
                or _snapshot_chronyd_process(pid=self._process.pid)
                != self._process_snapshot
            ):
                raise ChronydProcessV48BError(
                    "loaded chronyd process provenance changed"
                )
            _assert_exclusive_post_drop_uid(
                uid=self._policy.chronyd_launch_policy.post_drop_uid,
                expected_process_ids=(self._process.pid,),
            )
            _assert_runtime_directories_current(
                policy=self._policy.chronyd_launch_policy,
                descriptors=self._runtime_directory_fds,
                identities=self._runtime_directory_identities,
            )
        except BaseException:
            self._latch_fault()
            raise

    def _assert_signed_chronyc(self, chronyc: PinnedRuntimeArtifactV4) -> None:
        if type(chronyc) is not PinnedRuntimeArtifactV4:
            raise TypeError("chronyc must be an exact PinnedRuntimeArtifactV4")
        if (
            chronyc.spec.path != self._policy.chronyc_executable_path
            or chronyc.spec.sha256 != self._policy.chronyc_executable_sha256
            or not chronyc.spec.require_executable
        ):
            raise ChronydProtocolV48BError(
                "chronyc artifact differs from the signed clock policy"
            )
        chronyc.assert_unchanged()

    def await_source_readiness(self, chronyc: PinnedRuntimeArtifactV4) -> None:
        """Bound initial source loading separately from lifecycle ``READY=1``."""

        self._assert_signed_chronyc(chronyc)
        self.assert_provenance_current()
        if self._query_active:
            self._latch_fault()
            raise ChronydProtocolV48BError("concurrent chronyd queries are forbidden")
        deadline_ns = _boottime_ns_v48b() + (
            self._policy.chronyd_launch_policy.ready_timeout_milliseconds * 1_000_000
        )
        self._query_active = True
        try:
            while True:
                try:
                    self._query_chronyc_once(chronyc, outer_deadline_ns=deadline_ns)
                    return
                except ChronydSourcesNotReadyV48BError:
                    remaining_ms = int(_remaining_deadline_seconds(deadline_ns) * 1_000)
                    poller = select.poll()
                    poller.register(
                        self._pidfd, select.POLLIN | select.POLLERR | select.POLLHUP
                    )
                    if poller.poll(min(50, max(1, remaining_ms))):
                        raise ChronydProcessV48BError(
                            "chronyd exited while configured sources were loading"
                        ) from None
                    self.assert_provenance_current()
        except BaseException:
            self._latch_fault()
            raise
        finally:
            self._query_active = False

    def query_chronyc(
        self, chronyc: PinnedRuntimeArtifactV4
    ) -> AuthenticatedChronycQueryV48B:
        """Run one exact pinned read-only query through a fresh credential proxy."""

        self._assert_signed_chronyc(chronyc)
        self.assert_provenance_current()
        if self._query_active:
            self._latch_fault()
            raise ChronydProtocolV48BError("concurrent chronyd queries are forbidden")
        self._query_active = True
        try:
            return self._query_chronyc_once(chronyc)
        except BaseException:
            self._latch_fault()
            raise
        finally:
            self._query_active = False

    def _query_chronyc_once(
        self,
        chronyc: PinnedRuntimeArtifactV4,
        *,
        outer_deadline_ns: int | None = None,
    ) -> AuthenticatedChronycQueryV48B:
        policy = self._policy
        launch = policy.chronyd_launch_policy
        chronyc.assert_unchanged()
        deadline_ns = _boottime_ns_v48b() + (
            policy.chronyc_command_timeout_milliseconds * 1_000_000
        )
        if outer_deadline_ns is not None:
            deadline_ns = min(deadline_ns, outer_deadline_ns)
        query_dir: str | None = None
        for _ in range(8):
            candidate = (
                f"{launch.supervisor_socket_directory_path}/"
                f"query-{secrets.token_hex(8)}"
            )
            try:
                os.mkdir(candidate, 0o700)
            except FileExistsError:
                continue
            query_dir = candidate
            break
        if query_dir is None:
            raise ChronydProtocolV48BError(
                "fresh credential-proxy directory could not be allocated"
            )
        os.chmod(query_dir, 0o711)
        downstream_path = f"{query_dir}/proxy.sock"
        upstream_path = f"{query_dir}/upstream.sock"
        if (
            len(upstream_path.encode("utf-8")) >= 108
            or len(upstream_path.encode("utf-8"))
            != len(launch.supervisor_socket_directory_path.encode("utf-8"))
            + CHRONYD_QUERY_SOCKET_PATH_SUFFIX_BYTES
        ):
            os.rmdir(query_dir)
            raise ChronydProtocolV48BError(
                "credential proxy paths exceed Linux sockaddr_un capacity"
            )
        downstream = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        upstream = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        proc: subprocess.Popen[bytes] | None = None
        thread: threading.Thread | None = None
        stop_relay = threading.Event()
        proxy_error: list[BaseException] = []
        transcript_result: list[AuthenticatedChronyTranscriptV48B] = []
        client_address: list[str | bytes | None] = []
        try:
            _enable_passcred(downstream)
            _enable_passcred(upstream)
            downstream.bind(downstream_path)
            os.chmod(downstream_path, 0o600)
            upstream.bind(upstream_path)
            os.chmod(upstream_path, 0o666)
            upstream.connect(launch.real_command_socket_path)
            downstream.setblocking(False)
            upstream.setblocking(False)
            proc = subprocess.Popen(  # noqa: S603 - exact retained fd and argv
                (
                    chronyc.proc_fd_path,
                    "-n",
                    "-c",
                    "-e",
                    "-h",
                    downstream_path,
                    "-m",
                    (
                        "timeout "
                        f"{max(100, policy.chronyc_command_timeout_milliseconds // 2)}"
                    ),
                    "retries 0",
                    "tracking",
                    "sources -a",
                ),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                close_fds=True,
                pass_fds=(chronyc.descriptor,),
                env=dict(_FIXED_CHRONYD_ENVIRONMENT),
                shell=False,
                start_new_session=True,
            )
            state = ChronyReadOnlyQueryStateV48B(
                expected_source_count=len(self._prepared.configured_endpoints)
            )

            def relay() -> None:
                try:
                    assert proc is not None
                    while not state.complete:
                        _wait_for_datagram_v48b(
                            downstream,
                            deadline_ns=deadline_ns,
                            stop=stop_relay,
                        )
                        request, address = receive_authenticated_datagram_v48b(
                            downstream,
                            maximum_bytes=launch.maximum_datagram_bytes,
                            expected_pid=proc.pid,
                            expected_uid=os.geteuid(),
                            expected_gid=os.getegid(),
                        )
                        if address in {None, "", b""}:
                            raise ChronydProtocolV48BError(
                                "chronyc request has no stable Unix return address"
                            )
                        if client_address and address != client_address[0]:
                            raise ChronydProtocolV48BError(
                                "chronyc changed its client address during one query"
                            )
                        if not client_address:
                            client_address.append(address)
                        _send_datagram_v48b(
                            upstream,
                            request,
                            deadline_ns=deadline_ns,
                            stop=stop_relay,
                        )
                        _wait_for_datagram_v48b(
                            upstream,
                            deadline_ns=deadline_ns,
                            stop=stop_relay,
                        )
                        reply, _ = receive_authenticated_datagram_v48b(
                            upstream,
                            maximum_bytes=launch.maximum_datagram_bytes,
                            expected_pid=self._process.pid,
                            expected_uid=launch.post_drop_uid,
                            expected_gid=launch.post_drop_gid,
                        )
                        state.accept_exchange(request, reply)
                        _send_datagram_v48b(
                            downstream,
                            reply,
                            deadline_ns=deadline_ns,
                            stop=stop_relay,
                            address=address,
                        )
                    assert_no_queued_datagram_v48b(downstream)
                    assert_no_queued_datagram_v48b(upstream)
                    transcript_result.append(state.finish())
                except BaseException as exc:  # delivered to creating thread
                    proxy_error.append(exc)

            thread = threading.Thread(
                target=relay, name="chronyd-v48b-read-only-proxy", daemon=False
            )
            thread.start()
            returncode, stdout, stderr = _collect_bounded_process_output_v48b(
                proc,
                deadline_ns=deadline_ns,
                maximum_output_bytes=policy.chronyc_max_output_bytes,
            )
            thread.join(timeout=_remaining_deadline_seconds(deadline_ns))
            if thread.is_alive():
                raise ChronydProtocolV48BError(
                    "credential proxy did not terminate with pinned chronyc"
                )
            if proxy_error:
                if isinstance(proxy_error[0], ChronydSourcesNotReadyV48BError):
                    raise proxy_error[0]
                raise ChronydProtocolV48BError(
                    "credential proxy rejected the chronyc/chronyd exchange"
                ) from proxy_error[0]
            if returncode != 0 or stderr or not stdout or len(transcript_result) != 1:
                raise ChronydProtocolV48BError(
                    "pinned chronyc did not return one clean bounded query"
                )
            self.assert_provenance_current()
            chronyc.assert_unchanged()
            transcript = transcript_result[0]
            query_observation = sha256_digest(
                {
                    "chronyc_stdout_sha256": hashlib.sha256(stdout).hexdigest(),
                    "domain": "RiskYieldMMAuthenticatedChronycQueryV48B",
                    "launch_id": self._launch_id,
                    "runtime_observation_sha256": self._runtime_observation_sha256,
                    "transcript_sha256": transcript.transcript_sha256,
                }
            )
            return AuthenticatedChronycQueryV48B(
                stdout=stdout,
                transcript=transcript,
                launch_id=self._launch_id,
                runtime_observation_sha256=self._runtime_observation_sha256,
                query_observation_sha256=query_observation,
                configured_endpoints=self._prepared.configured_endpoints,
            )
        finally:
            stop_relay.set()
            if proc is not None and proc.poll() is None:
                _terminate_owned_process(proc)
            downstream.close()
            upstream.close()
            if thread is not None and thread.is_alive():
                thread.join(timeout=0.25)
                if thread.is_alive():
                    self._latch_fault()
            for path in (downstream_path, upstream_path):
                try:
                    os.unlink(path)
                except FileNotFoundError:
                    pass
                except OSError:
                    self._latch_fault()
            try:
                os.rmdir(query_dir)
            except OSError:
                self._latch_fault()

    def close(self) -> None:
        if self._closed:
            return
        creating_process = os.getpid() == self._creator_pid
        policy = self._policy.chronyd_launch_policy
        self._closed = True
        if creating_process:
            _terminate_owned_process(self._process, pidfd=self._pidfd)
        try:
            os.close(self._pidfd)
        except OSError:
            pass
        self._notify_socket.close()
        if creating_process:
            _unlink_matching_socket(
                policy.notify_socket_path,
                device=self._notify_socket_identity[0],
                inode=self._notify_socket_identity[1],
            )
            _unlink_matching_socket(
                policy.real_command_socket_path,
                device=self._command_socket_snapshot.device,
                inode=self._command_socket_snapshot.inode,
            )
        if (
            creating_process
            and os.geteuid() == 0
            and len(self._runtime_directory_fds) == 3
        ):
            try:
                os.fchown(
                    self._runtime_directory_fds[1],
                    policy.post_drop_uid,
                    policy.post_drop_gid,
                )
                os.fchmod(self._runtime_directory_fds[1], 0o700)
            except OSError:
                pass
        for runtime_fd in reversed(self._runtime_directory_fds):
            try:
                os.close(runtime_fd)
            except OSError:
                pass
        self._runtime_directory_fds = ()
        self._prepared.close()

    def __enter__(self) -> ChronydLaunchAuthorityV48B:
        self.assert_provenance_current()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


__all__ = [
    "AuthenticatedChronyTranscriptV48B",
    "AuthenticatedChronycQueryV48B",
    "BoundedChronydCommandResultV48B",
    "ChronyProtocolExchangeV48B",
    "ChronyReadOnlyQueryStateV48B",
    "ChronydConfigurationV48BError",
    "ChronydProcessV48BError",
    "ChronydProtocolV48BError",
    "ChronydProvenanceV48BError",
    "ChronydSourcesNotReadyV48BError",
    "ChronydLaunchAuthorityV48B",
    "EffectiveChronydConfigurationV48B",
    "PreparedChronydLaunchV48B",
    "SealedChronydConfigurationV48B",
    "assemble_effective_chronyd_configuration_v48b",
    "assert_no_queued_datagram_v48b",
    "chronyd_fixed_environment_v48b",
    "current_systemd_invocation_id_v48b",
    "receive_authenticated_datagram_v48b",
]
