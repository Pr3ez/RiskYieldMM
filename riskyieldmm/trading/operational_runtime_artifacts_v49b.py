"""Measured runtime-artifact authority for the exact V4.9B transport driver.

The capture helper in this module is deliberately non-authoritative: it reports
the bytes and import origins visible to the current process so an operator can
prepare a deployment manifest for independent signing.  Authority exists only
after the signed policy is admitted again through
``PinnedTlsWebSocketRuntimeArtifactsV49B.open_verified``.

The live verifier retains one non-inheritable descriptor per signed member.  It
doesn't treat a package version or a fictional aggregate hash as evidence; the
policy contains every admitted file path, size, and SHA-256 digest.
"""

from __future__ import annotations

import hashlib
import importlib
import importlib.metadata
import importlib.util
import os
import platform
import posixpath
import site
import ssl
import stat
import sys
import sysconfig
import threading
import weakref
from dataclasses import dataclass
from types import ModuleType
from typing import Final

from .canonical import sha256_digest
from .operational_manifests_v4 import (
    TLS_WEBSOCKET_DRIVER_PROFILE_V49B,
    InstalledDistributionClosureV49B,
    RuntimeArtifactMemberV49B,
    RuntimeEnvironmentManifestV4,
    TlsWebSocketDriverPolicyV49B,
)

_MAX_PROC_MAPS_BYTES: Final = 16 * 1024 * 1024
_READ_CHUNK_BYTES: Final = 128 * 1024
_RUNTIME_MODULE_ROLES: Final = {
    "PYTHON_SSL_EXTENSION": "_ssl",
    "PYTHON_STDLIB_SSL": "ssl",
    "RISKYIELDMM_TLS_DRIVER": ("riskyieldmm.trading.physical_transport_tls_v49"),
    "RISKYIELDMM_TLS_TRUST_STORE": "riskyieldmm.trading.tls_trust_store_v49",
}
_PYTHON_BYTECODE_CACHE_ROLES: Final = {
    "PYTHON_STDLIB_SSL": "PYTHON_STDLIB_SSL_BYTECODE_CACHE",
    "RISKYIELDMM_TLS_DRIVER": "RISKYIELDMM_TLS_DRIVER_BYTECODE_CACHE",
    "RISKYIELDMM_TLS_TRUST_STORE": ("RISKYIELDMM_TLS_TRUST_STORE_BYTECODE_CACHE"),
}
_DISTRIBUTION_MODULES: Final = {
    "cryptography": "cryptography",
    "websockets": "websockets",
}
_RUNTIME_OBSERVATION_DOMAIN: Final = "RiskYieldMMTlsWebSocketRuntimeObservationV49B"


class RuntimeArtifactAuthorityV49BError(RuntimeError):
    """The loaded process differs from the signed V4.9B artifact closure."""


def _normalized_absolute_path(value: os.PathLike[str] | str, *, field: str) -> str:
    try:
        raw = os.fspath(value)
    except TypeError as exc:
        raise RuntimeArtifactAuthorityV49BError(f"{field} is not path-like") from exc
    if type(raw) is not str or not raw or "\x00" in raw:
        raise RuntimeArtifactAuthorityV49BError(f"{field} is not an exact text path")
    absolute = os.path.abspath(raw)
    normalized = posixpath.normpath(absolute)
    if not normalized.startswith("/") or normalized != absolute:
        raise RuntimeArtifactAuthorityV49BError(
            f"{field} is not a normalized absolute path"
        )
    return normalized


def _open_flags() -> int:
    return os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0)


def _hash_descriptor(fd: int, *, expected_size: int | None = None) -> tuple[int, str]:
    before = os.fstat(fd)
    if not stat.S_ISREG(before.st_mode):
        raise RuntimeArtifactAuthorityV49BError("artifact is not a regular file")
    if before.st_size < 0 or before.st_size > 1 << 30:
        raise RuntimeArtifactAuthorityV49BError("artifact size is outside V4.9B bounds")
    if expected_size is not None and before.st_size != expected_size:
        raise RuntimeArtifactAuthorityV49BError(
            "artifact size differs from its signed member"
        )
    digest = hashlib.sha256()
    offset = 0
    while offset < before.st_size:
        chunk = os.pread(fd, min(_READ_CHUNK_BYTES, before.st_size - offset), offset)
        if not chunk:
            raise RuntimeArtifactAuthorityV49BError(
                "artifact became truncated while hashing"
            )
        digest.update(chunk)
        offset += len(chunk)
    after = os.fstat(fd)
    if (
        before.st_dev,
        before.st_ino,
        before.st_mode,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
    ) != (
        after.st_dev,
        after.st_ino,
        after.st_mode,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
    ):
        raise RuntimeArtifactAuthorityV49BError(
            "artifact changed while its member digest was measured"
        )
    return after.st_size, digest.hexdigest()


def _measure_path(
    *,
    role: str,
    path: str,
    require_executable: bool | None = None,
    allow_writable: bool,
) -> RuntimeArtifactMemberV49B:
    normalized = _normalized_absolute_path(path, field=f"{role}_path")
    try:
        descriptor = os.open(normalized, _open_flags())
    except OSError as exc:
        raise RuntimeArtifactAuthorityV49BError(
            f"{role} could not be opened without following a final symlink"
        ) from exc
    try:
        os.set_inheritable(descriptor, False)
        if os.get_inheritable(descriptor):
            raise RuntimeArtifactAuthorityV49BError(
                f"{role} descriptor remained inheritable"
            )
        current = os.fstat(descriptor)
        if not allow_writable and current.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
            raise RuntimeArtifactAuthorityV49BError(
                f"{role} is group- or world-writable"
            )
        executable = bool(
            current.st_mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        )
        if require_executable is True and not executable:
            raise RuntimeArtifactAuthorityV49BError(f"{role} is not executable")
        size, digest = _hash_descriptor(descriptor)
        return RuntimeArtifactMemberV49B(
            role=role,
            path=normalized,
            size_bytes=size,
            sha256=digest,
            require_executable=(
                executable if require_executable is None else require_executable
            ),
        )
    finally:
        os.close(descriptor)


def _module_origin(module_name: str) -> str:
    module = importlib.import_module(module_name)
    if type(module) is not ModuleType:
        raise RuntimeArtifactAuthorityV49BError(
            f"{module_name} did not resolve to an exact module"
        )
    file_value = getattr(module, "__file__", None)
    specification = getattr(module, "__spec__", None)
    spec_origin = None if specification is None else specification.origin
    if not isinstance(file_value, str) or not isinstance(spec_origin, str):
        raise RuntimeArtifactAuthorityV49BError(
            f"{module_name} has no exact file-backed import origin"
        )
    file_path = _normalized_absolute_path(file_value, field=f"{module_name}.__file__")
    origin_path = _normalized_absolute_path(
        spec_origin, field=f"{module_name}.__spec__.origin"
    )
    if file_path != origin_path:
        raise RuntimeArtifactAuthorityV49BError(
            f"{module_name} file and import-spec origins differ"
        )
    return file_path


def _module_bytecode_cache_path(module_name: str, *, origin: str) -> str:
    module = importlib.import_module(module_name)
    cached_value = getattr(module, "__cached__", None)
    if type(cached_value) is not str:
        raise RuntimeArtifactAuthorityV49BError(
            f"{module_name} has no exact bytecode-cache path"
        )
    cached_path = _normalized_absolute_path(
        cached_value,
        field=f"{module_name}.__cached__",
    )
    try:
        expected = importlib.util.cache_from_source(origin)
    except (NotImplementedError, ValueError) as exc:
        raise RuntimeArtifactAuthorityV49BError(
            f"{module_name} bytecode-cache path cannot be derived from its origin"
        ) from exc
    expected_path = _normalized_absolute_path(
        expected,
        field=f"{module_name}.cache_from_source",
    )
    if cached_path != expected_path:
        raise RuntimeArtifactAuthorityV49BError(
            f"{module_name} bytecode-cache path differs from its exact source origin"
        )
    return cached_path


def _proc_self_maps_bytes() -> bytes:
    try:
        with open("/proc/self/maps", "rb", buffering=0) as source:
            chunks: list[bytes] = []
            total = 0
            while total <= _MAX_PROC_MAPS_BYTES:
                chunk = source.read(
                    min(_READ_CHUNK_BYTES, _MAX_PROC_MAPS_BYTES + 1 - total)
                )
                if not chunk:
                    break
                chunks.append(chunk)
                total += len(chunk)
            raw = b"".join(chunks)
    except OSError as exc:
        raise RuntimeArtifactAuthorityV49BError(
            "loaded process mappings are unavailable"
        ) from exc
    if len(raw) > _MAX_PROC_MAPS_BYTES:
        raise RuntimeArtifactAuthorityV49BError("/proc/self/maps exceeds its bound")
    return raw


def _mapped_openssl_paths() -> dict[str, str]:
    return _mapped_openssl_paths_from_maps(_proc_self_maps_bytes())


def _openssl_mapping_role(basename: str) -> str | None:
    if basename == "libssl.so" or basename.startswith("libssl.so."):
        return "OPENSSL_LIBSSL"
    if basename == "libcrypto.so" or basename.startswith("libcrypto.so."):
        return "OPENSSL_LIBCRYPTO"
    return None


def _mapped_openssl_paths_from_maps(raw: bytes) -> dict[str, str]:
    if type(raw) is not bytes or len(raw) > _MAX_PROC_MAPS_BYTES:
        raise RuntimeArtifactAuthorityV49BError(
            "process mappings are not exact bounded bytes"
        )
    paths: dict[str, set[str]] = {"OPENSSL_LIBCRYPTO": set(), "OPENSSL_LIBSSL": set()}
    for line in raw.splitlines():
        parts = line.split(maxsplit=5)
        if len(parts) != 6 or not parts[5].startswith(b"/"):
            continue
        try:
            candidate = parts[5].decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise RuntimeArtifactAuthorityV49BError(
                "a loaded library path is not strict UTF-8"
            ) from exc
        deleted = candidate.endswith(" (deleted)")
        effective = candidate.removesuffix(" (deleted)")
        role = _openssl_mapping_role(posixpath.basename(effective))
        if role is None:
            continue
        if deleted:
            raise RuntimeArtifactAuthorityV49BError(
                f"the loaded {role} mapping was deleted"
            )
        paths[role].add(
            _normalized_absolute_path(
                effective,
                field=f"loaded_{role.lower()}_path",
            )
        )
    result: dict[str, str] = {}
    for role, candidates in paths.items():
        if len(candidates) != 1:
            raise RuntimeArtifactAuthorityV49BError(
                f"{role} does not identify exactly one loaded object"
            )
        result[role] = next(iter(candidates))
    return result


def _mapped_libpython_paths() -> tuple[str, ...]:
    paths: set[str] = set()
    for line in _proc_self_maps_bytes().splitlines():
        parts = line.split(maxsplit=5)
        if len(parts) != 6 or not parts[5].startswith(b"/"):
            continue
        try:
            candidate = parts[5].decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise RuntimeArtifactAuthorityV49BError(
                "a loaded library path is not strict UTF-8"
            ) from exc
        deleted = candidate.endswith(" (deleted)")
        effective = candidate.removesuffix(" (deleted)")
        basename = posixpath.basename(effective)
        if not basename.startswith("libpython") or ".so" not in basename:
            continue
        if deleted:
            raise RuntimeArtifactAuthorityV49BError(
                "a loaded libpython mapping was deleted"
            )
        paths.add(
            _normalized_absolute_path(
                effective,
                field="loaded_libpython_path",
            )
        )
    return tuple(sorted(paths))


def _assert_static_interpreter_profile() -> None:
    shared = sysconfig.get_config_var("Py_ENABLE_SHARED")
    if type(shared) is not int or shared != 0:
        raise RuntimeArtifactAuthorityV49BError(
            "V4.9B requires Python core code linked into the signed executable"
        )
    if _mapped_libpython_paths():
        raise RuntimeArtifactAuthorityV49BError(
            "V4.9B rejects a separately mapped libpython runtime"
        )


def _promotion_interpreter_flags_are_exact() -> bool:
    flags = sys.flags
    return (
        flags.isolated == 1
        and flags.no_user_site == 1
        and flags.no_site == 1
        and flags.dont_write_bytecode == 1
        and flags.ignore_environment == 1
        and bool(flags.safe_path)
        and flags.optimize == 0
    )


def _python_executable_path() -> str:
    try:
        proc_executable = os.readlink("/proc/self/exe")
        if not os.path.samefile(sys.executable, "/proc/self/exe"):
            raise RuntimeArtifactAuthorityV49BError(
                "sys.executable differs from /proc/self/exe"
            )
    except OSError as exc:
        raise RuntimeArtifactAuthorityV49BError(
            "the loaded Python executable cannot be identified"
        ) from exc
    return _normalized_absolute_path(proc_executable, field="proc_self_exe")


def _capture_distribution(
    distribution_name: str, *, allow_writable: bool
) -> InstalledDistributionClosureV49B:
    try:
        distribution = importlib.metadata.distribution(distribution_name)
    except importlib.metadata.PackageNotFoundError as exc:
        raise RuntimeArtifactAuthorityV49BError(
            f"required distribution {distribution_name} is not installed"
        ) from exc
    files = distribution.files
    if files is None or not files:
        raise RuntimeArtifactAuthorityV49BError(
            f"distribution {distribution_name} has no installed file closure"
        )
    origin = _normalized_absolute_path(
        distribution.locate_file(""),
        field=f"{distribution_name}_distribution_origin",
    )
    member_paths = tuple(
        sorted(
            _normalized_absolute_path(
                distribution.locate_file(file),
                field=f"{distribution_name}_member_path",
            )
            for file in files
        )
    )
    if len(member_paths) != len(set(member_paths)):
        raise RuntimeArtifactAuthorityV49BError(
            f"distribution {distribution_name} contains duplicate normalized paths"
        )
    members = tuple(
        _measure_path(
            role=f"{distribution_name.upper()}_MEMBER_{index:06d}",
            path=path,
            allow_writable=allow_writable,
        )
        for index, path in enumerate(member_paths, start=1)
    )
    module_origin = _module_origin(_DISTRIBUTION_MODULES[distribution_name])
    return InstalledDistributionClosureV49B(
        distribution_name=distribution_name,
        distribution_version=distribution.version,
        distribution_origin=origin,
        module_origin=module_origin,
        members=members,
    )


def _capture_current_policy(*, allow_writable: bool) -> TlsWebSocketDriverPolicyV49B:
    # Importing ssl before reading maps ensures the actual linked OpenSSL objects
    # have been loaded into this process.
    _ = ssl.OPENSSL_VERSION
    _assert_static_interpreter_profile()
    artifacts: list[RuntimeArtifactMemberV49B] = [
        _measure_path(
            role="PYTHON_EXECUTABLE",
            path=_python_executable_path(),
            require_executable=True,
            allow_writable=allow_writable,
        )
    ]
    bytecode_cache_artifacts: list[RuntimeArtifactMemberV49B] = []
    for role, module_name in _RUNTIME_MODULE_ROLES.items():
        origin = _module_origin(module_name)
        artifacts.append(
            _measure_path(
                role=role,
                path=origin,
                allow_writable=allow_writable,
            )
        )
        cache_role = _PYTHON_BYTECODE_CACHE_ROLES.get(role)
        if cache_role is not None:
            bytecode_cache_artifacts.append(
                _measure_path(
                    role=cache_role,
                    path=_module_bytecode_cache_path(
                        module_name,
                        origin=origin,
                    ),
                    require_executable=False,
                    allow_writable=allow_writable,
                )
            )
    for role, path in _mapped_openssl_paths().items():
        artifacts.append(
            _measure_path(
                role=role,
                path=path,
                allow_writable=allow_writable,
            )
        )
    distributions = tuple(
        _capture_distribution(name, allow_writable=allow_writable)
        for name in sorted(_DISTRIBUTION_MODULES)
    )
    return TlsWebSocketDriverPolicyV49B(
        driver_profile=TLS_WEBSOCKET_DRIVER_PROFILE_V49B,
        python_implementation=platform.python_implementation(),
        python_version=platform.python_version(),
        openssl_version=ssl.OPENSSL_VERSION,
        runtime_artifacts=tuple(sorted(artifacts, key=lambda member: member.role)),
        python_bytecode_cache_artifacts=tuple(
            sorted(
                bytecode_cache_artifacts,
                key=lambda member: member.role,
            )
        ),
        installed_distributions=distributions,
    )


def capture_current_tls_websocket_driver_policy_v49b() -> TlsWebSocketDriverPolicyV49B:
    """Capture current members for offline review and signing.

    This helper intentionally permits writable development artifacts because it
    grants no authority.  The live verifier rejects group/world-writable files.
    """

    return _capture_current_policy(allow_writable=True)


@dataclass(frozen=True, slots=True)
class _RetainedMemberStatV49B:
    device: int
    inode: int
    mode: int
    uid: int
    gid: int
    size: int
    modified_ns: int
    changed_ns: int

    @classmethod
    def from_stat(cls, value: os.stat_result) -> _RetainedMemberStatV49B:
        return cls(
            device=value.st_dev,
            inode=value.st_ino,
            mode=value.st_mode,
            uid=value.st_uid,
            gid=value.st_gid,
            size=value.st_size,
            modified_ns=value.st_mtime_ns,
            changed_ns=value.st_ctime_ns,
        )


def _validate_retained_member_stat(
    value: os.stat_result,
    member: RuntimeArtifactMemberV49B,
    *,
    allow_writable: bool,
) -> None:
    if not stat.S_ISREG(value.st_mode):
        raise RuntimeArtifactAuthorityV49BError("runtime member is not a regular file")
    if value.st_size != member.size_bytes:
        raise RuntimeArtifactAuthorityV49BError(
            "runtime member size differs from signed policy"
        )
    if not allow_writable and value.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
        raise RuntimeArtifactAuthorityV49BError(
            "runtime member is group- or world-writable"
        )
    if member.require_executable and not value.st_mode & (
        stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
    ):
        raise RuntimeArtifactAuthorityV49BError(
            "signed runtime executable has no execute bit"
        )


def _hash_retained_member(
    descriptor: int,
    member: RuntimeArtifactMemberV49B,
    *,
    allow_writable: bool,
) -> tuple[str, _RetainedMemberStatV49B]:
    before_raw = os.fstat(descriptor)
    _validate_retained_member_stat(
        before_raw,
        member,
        allow_writable=allow_writable,
    )
    before = _RetainedMemberStatV49B.from_stat(before_raw)
    digest = hashlib.sha256()
    offset = 0
    while offset < member.size_bytes:
        chunk = os.pread(
            descriptor,
            min(_READ_CHUNK_BYTES, member.size_bytes - offset),
            offset,
        )
        if not chunk:
            raise RuntimeArtifactAuthorityV49BError(
                "runtime member became truncated while hashing"
            )
        digest.update(chunk)
        offset += len(chunk)
    after_raw = os.fstat(descriptor)
    _validate_retained_member_stat(
        after_raw,
        member,
        allow_writable=allow_writable,
    )
    after = _RetainedMemberStatV49B.from_stat(after_raw)
    if before != after or offset != after.size:
        raise RuntimeArtifactAuthorityV49BError(
            "runtime member changed while it was being verified"
        )
    return digest.hexdigest(), after


class _PinnedRuntimeMemberV49B:
    """One retained member of the signed V4.9B process closure."""

    def __init__(
        self,
        *,
        member: RuntimeArtifactMemberV49B,
        descriptor: int,
        admitted_stat: _RetainedMemberStatV49B,
        allow_writable: bool,
    ) -> None:
        self._member = member
        self._descriptor = descriptor
        self._admitted_stat = admitted_stat
        self._allow_writable = allow_writable
        self._creator_pid = os.getpid()
        self._closed = False

    @classmethod
    def open_verified(
        cls,
        member: RuntimeArtifactMemberV49B,
        *,
        allow_writable: bool,
    ) -> _PinnedRuntimeMemberV49B:
        if cls is not _PinnedRuntimeMemberV49B:
            raise TypeError("runtime member subclasses are unsupported")
        if type(member) is not RuntimeArtifactMemberV49B:
            raise TypeError("member must be an exact RuntimeArtifactMemberV49B")
        if type(allow_writable) is not bool:
            raise TypeError("allow_writable must be a boolean")
        try:
            descriptor = os.open(member.path, _open_flags())
        except OSError as exc:
            raise RuntimeArtifactAuthorityV49BError(
                "runtime member could not be opened without following a final symlink"
            ) from exc
        try:
            os.set_inheritable(descriptor, False)
            if os.get_inheritable(descriptor):
                raise RuntimeArtifactAuthorityV49BError(
                    "runtime member descriptor remained inheritable"
                )
            digest, admitted_stat = _hash_retained_member(
                descriptor,
                member,
                allow_writable=allow_writable,
            )
            if digest != member.sha256:
                raise RuntimeArtifactAuthorityV49BError(
                    "runtime member digest differs from signed policy"
                )
            return cls(
                member=member,
                descriptor=descriptor,
                admitted_stat=admitted_stat,
                allow_writable=allow_writable,
            )
        except BaseException:
            os.close(descriptor)
            raise

    @property
    def observation_identity(self) -> dict[str, int | str]:
        return {
            "device": self._admitted_stat.device,
            "inode": self._admitted_stat.inode,
            "path": self._member.path,
            "role": self._member.role,
            "size_bytes": self._admitted_stat.size,
        }

    def assert_current(self) -> None:
        if self._closed or os.getpid() != self._creator_pid:
            raise RuntimeArtifactAuthorityV49BError(
                "retained runtime member is not live"
            )
        try:
            if os.get_inheritable(self._descriptor):
                raise RuntimeArtifactAuthorityV49BError(
                    "runtime member descriptor became inheritable"
                )
            digest, current_stat = _hash_retained_member(
                self._descriptor,
                self._member,
                allow_writable=self._allow_writable,
            )
            if digest != self._member.sha256 or current_stat != self._admitted_stat:
                raise RuntimeArtifactAuthorityV49BError(
                    "retained runtime member changed after admission"
                )
            reopened = os.open(self._member.path, _open_flags())
            try:
                os.set_inheritable(reopened, False)
                if os.get_inheritable(reopened):
                    raise RuntimeArtifactAuthorityV49BError(
                        "reopened runtime member descriptor remained inheritable"
                    )
                reopened_digest, reopened_stat = _hash_retained_member(
                    reopened,
                    self._member,
                    allow_writable=self._allow_writable,
                )
            finally:
                os.close(reopened)
            if (
                reopened_digest != self._member.sha256
                or reopened_stat != self._admitted_stat
            ):
                raise RuntimeArtifactAuthorityV49BError(
                    "signed path no longer names the retained runtime member"
                )
        except RuntimeArtifactAuthorityV49BError:
            raise
        except OSError as exc:
            raise RuntimeArtifactAuthorityV49BError(
                "retained runtime member could not be revalidated"
            ) from exc

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            os.close(self._descriptor)


class PinnedTlsWebSocketRuntimeArtifactsV49B:
    """Retained exact runtime members admitted by one signed driver policy."""

    def __init__(
        self,
        *,
        policy: TlsWebSocketDriverPolicyV49B,
        runtime_environment: RuntimeEnvironmentManifestV4,
        artifacts: tuple[_PinnedRuntimeMemberV49B, ...],
        allow_writable: bool,
        promotion_profile: bool,
    ) -> None:
        self._policy = policy
        self._runtime_environment = runtime_environment
        self._artifacts = artifacts
        self._allow_writable = allow_writable
        self._promotion_profile = promotion_profile
        self._creator_pid = os.getpid()
        self._creator_thread_id = threading.get_ident()
        self._fork_invalid = False
        self._closed = False
        self._lock = threading.RLock()
        self._runtime_observation_sha256 = sha256_digest(
            {
                "creator_pid": self._creator_pid,
                "domain": _RUNTIME_OBSERVATION_DOMAIN,
                "policy_id": policy.policy_id,
                "retained_members": [
                    artifact.observation_identity for artifact in artifacts
                ],
                "runtime_environment_manifest_id": (runtime_environment.manifest_id),
            }
        )
        reference = weakref.ref(self)

        def invalidate_child() -> None:
            item = reference()
            if item is not None:
                item._invalidate_in_fork_child()

        os.register_at_fork(after_in_child=invalidate_child)

    @classmethod
    def open_verified(
        cls,
        *,
        policy: TlsWebSocketDriverPolicyV49B,
        runtime_environment: RuntimeEnvironmentManifestV4,
    ) -> PinnedTlsWebSocketRuntimeArtifactsV49B:
        """Open the promotion profile; current Python must be isolated."""

        return cls._open_verified(
            policy=policy,
            runtime_environment=runtime_environment,
            enforce_isolation=True,
            allow_writable=False,
        )

    @classmethod
    def _open_verified_for_test(
        cls,
        *,
        policy: TlsWebSocketDriverPolicyV49B,
        runtime_environment: RuntimeEnvironmentManifestV4,
    ) -> PinnedTlsWebSocketRuntimeArtifactsV49B:
        """Non-promotion harness for deterministic developer-environment tests."""

        return cls._open_verified(
            policy=policy,
            runtime_environment=runtime_environment,
            enforce_isolation=False,
            allow_writable=True,
        )

    @classmethod
    def _open_verified(
        cls,
        *,
        policy: TlsWebSocketDriverPolicyV49B,
        runtime_environment: RuntimeEnvironmentManifestV4,
        enforce_isolation: bool,
        allow_writable: bool,
    ) -> PinnedTlsWebSocketRuntimeArtifactsV49B:
        if cls is not PinnedTlsWebSocketRuntimeArtifactsV49B:
            raise TypeError("runtime artifact authority subclasses are unsupported")
        if type(policy) is not TlsWebSocketDriverPolicyV49B:
            raise TypeError("policy must be an exact TlsWebSocketDriverPolicyV49B")
        if type(runtime_environment) is not RuntimeEnvironmentManifestV4:
            raise TypeError(
                "runtime_environment must be an exact RuntimeEnvironmentManifestV4"
            )
        if runtime_environment.tls_websocket_driver_policy != policy:
            raise RuntimeArtifactAuthorityV49BError(
                "runtime environment does not bind the supplied driver policy"
            )
        cls._assert_process_profile(
            runtime_environment,
            enforce_isolation=enforce_isolation,
        )
        captured = _capture_current_policy(allow_writable=allow_writable)
        if captured != policy:
            raise RuntimeArtifactAuthorityV49BError(
                "loaded runtime members or origins differ from signed driver policy"
            )
        members = (
            policy.runtime_artifacts
            + policy.python_bytecode_cache_artifacts
            + tuple(
                member
                for distribution in policy.installed_distributions
                for member in distribution.members
            )
        )
        opened: list[_PinnedRuntimeMemberV49B] = []
        try:
            for member in members:
                artifact = _PinnedRuntimeMemberV49B.open_verified(
                    member,
                    allow_writable=allow_writable,
                )
                opened.append(artifact)
            result = cls(
                policy=policy,
                runtime_environment=runtime_environment,
                artifacts=tuple(opened),
                allow_writable=allow_writable,
                promotion_profile=enforce_isolation and not allow_writable,
            )
            opened.clear()
            result.assert_current()
            return result
        except BaseException:
            for artifact in reversed(opened):
                try:
                    artifact.close()
                except OSError:
                    pass
            raise

    @staticmethod
    def _assert_process_profile(
        runtime_environment: RuntimeEnvironmentManifestV4,
        *,
        enforce_isolation: bool,
    ) -> None:
        if (
            runtime_environment.python_implementation
            != platform.python_implementation()
            or runtime_environment.python_version != platform.python_version()
            or runtime_environment.openssl_version != ssl.OPENSSL_VERSION
            or runtime_environment.platform_tag != sysconfig.get_platform()
        ):
            raise RuntimeArtifactAuthorityV49BError(
                "loaded Python/OpenSSL platform differs from runtime environment"
            )
        _assert_static_interpreter_profile()
        if enforce_isolation and not (
            runtime_environment.isolated_mode
            and not runtime_environment.user_site_enabled
            and _promotion_interpreter_flags_are_exact()
            # Under the required ``-S`` flag, importing ``site`` leaves this
            # sentinel as ``None`` rather than ``False``.  The immutable
            # ``no_user_site`` flag plus the check function establish that the
            # user site is disabled in both initialized and uninitialized-site
            # states.
            and site.ENABLE_USER_SITE is not True
            and site.check_enableusersite() is False
        ):
            raise RuntimeArtifactAuthorityV49BError(
                "live Python lacks the exact -I -S -B isolation profile"
            )

    @property
    def policy(self) -> TlsWebSocketDriverPolicyV49B:
        return self._policy

    @property
    def policy_id(self) -> str:
        return self._policy.policy_id

    @property
    def runtime_environment_manifest_id(self) -> str:
        return self._runtime_environment.manifest_id

    @property
    def runtime_observation_sha256(self) -> str:
        return self._runtime_observation_sha256

    @property
    def is_promotion_eligible(self) -> bool:
        return self._promotion_profile

    @property
    def is_promotion_profile(self) -> bool:
        """Compatibility alias for the explicit promotion-eligibility signal."""

        return self.is_promotion_eligible

    def _assert_context(self) -> None:
        if (
            self._closed
            or self._fork_invalid
            or os.getpid() != self._creator_pid
            or threading.get_ident() != self._creator_thread_id
        ):
            raise RuntimeArtifactAuthorityV49BError(
                "runtime artifact authority left its creating process/thread"
            )

    def assert_current(self) -> None:
        with self._lock:
            self._assert_context()
            self._assert_process_profile(
                self._runtime_environment,
                enforce_isolation=not self._allow_writable,
            )
            captured = _capture_current_policy(allow_writable=self._allow_writable)
            if captured != self._policy:
                raise RuntimeArtifactAuthorityV49BError(
                    "loaded runtime closure changed after admission"
                )
            for artifact in self._artifacts:
                artifact.assert_current()

    def _invalidate_in_fork_child(self) -> None:
        """Invalidate without acquiring locks inherited from vanished threads."""

        self._fork_invalid = True
        self._closed = True
        for artifact in self._artifacts:
            try:
                artifact.close()
            except OSError:
                pass
        self._artifacts = ()

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            for artifact in reversed(self._artifacts):
                try:
                    artifact.close()
                except OSError:
                    pass
            self._artifacts = ()

    def __enter__(self) -> PinnedTlsWebSocketRuntimeArtifactsV49B:
        self.assert_current()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


__all__ = [
    "PinnedTlsWebSocketRuntimeArtifactsV49B",
    "RuntimeArtifactAuthorityV49BError",
    "capture_current_tls_websocket_driver_policy_v49b",
]
