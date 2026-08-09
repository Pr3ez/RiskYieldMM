"""Hash-pinned, race-aware public runtime artifacts for transport V4.7B.

This loader is deliberately separate from the transport private-key loader.
Executables and chrony configuration are normally root-owned, readable public
artifacts; applying secret-file ownership and 0400/0600 rules to them would be
incorrect.  The loader retains a non-inheritable descriptor, hashes bounded
bytes from that descriptor, and reopens the approved pathname when asserting
that the deployed artifact is still the one that was admitted.

The checks are cooperative process evidence.  They do not replace a read-only
or measured root filesystem, verified boot, IMA, dm-verity, or host attestation.
"""

from __future__ import annotations

import hashlib
import os
import posixpath
import stat
from dataclasses import dataclass
from typing import Final

from .canonical import (
    CanonicalizationError,
    canonical_hash,
    canonical_identifier,
    canonical_safe_int,
    sha256_digest,
)

_SOURCE_SET_DOMAIN: Final = "RiskYieldMMConfiguredChronySourceSetV4_7B"
_DEFAULT_MAX_ARTIFACT_BYTES: Final = 64 * 1024 * 1024
_READ_CHUNK_BYTES: Final = 128 * 1024


class OperationalArtifactV4Error(RuntimeError):
    """Base error for a runtime artifact that cannot remain admitted."""


class OperationalArtifactChangedV4Error(OperationalArtifactV4Error):
    """Raised when an admitted descriptor or its approved path changed."""


def _absolute_path(value: object, *, field: str) -> str:
    path = canonical_identifier(value, field=field, maximum=4096)
    if not path.startswith("/") or posixpath.normpath(path) != path:
        raise CanonicalizationError(f"{field} must be a normalized absolute POSIX path")
    return path


@dataclass(frozen=True, slots=True, kw_only=True)
class RuntimeArtifactSpecV4:
    path: str
    sha256: str
    max_bytes: int = _DEFAULT_MAX_ARTIFACT_BYTES
    require_executable: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", _absolute_path(self.path, field="path"))
        object.__setattr__(self, "sha256", canonical_hash(self.sha256, field="sha256"))
        object.__setattr__(
            self,
            "max_bytes",
            canonical_safe_int(
                self.max_bytes,
                field="max_bytes",
                minimum=1,
                maximum=1 << 30,
            ),
        )
        if type(self.require_executable) is not bool:
            raise CanonicalizationError("require_executable must be a boolean")


@dataclass(frozen=True, slots=True, kw_only=True)
class ConfiguredChronySourceArtifactV4:
    """One exact file in the signed expanded chrony source/config closure."""

    path: str
    sha256: str
    max_bytes: int = 4 * 1024 * 1024

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", _absolute_path(self.path, field="path"))
        object.__setattr__(self, "sha256", canonical_hash(self.sha256, field="sha256"))
        object.__setattr__(
            self,
            "max_bytes",
            canonical_safe_int(
                self.max_bytes,
                field="max_bytes",
                minimum=1,
                maximum=64 * 1024 * 1024,
            ),
        )

    def runtime_spec(self) -> RuntimeArtifactSpecV4:
        return RuntimeArtifactSpecV4(
            path=self.path,
            sha256=self.sha256,
            max_bytes=self.max_bytes,
        )


def derive_configured_chrony_source_set_root_v4(
    artifacts: tuple[ConfiguredChronySourceArtifactV4, ...],
) -> str:
    if type(artifacts) is not tuple or not artifacts:
        raise CanonicalizationError(
            "configured chrony source closure must be a non-empty tuple"
        )
    if any(type(item) is not ConfiguredChronySourceArtifactV4 for item in artifacts):
        raise CanonicalizationError(
            "configured chrony source closure contains an unsupported item"
        )
    ordered = tuple(sorted(artifacts, key=lambda item: item.path))
    if ordered != artifacts:
        raise CanonicalizationError(
            "configured chrony source artifacts must be path-sorted"
        )
    paths = tuple(item.path for item in artifacts)
    if len(set(paths)) != len(paths):
        raise CanonicalizationError(
            "configured chrony source artifact paths must be unique"
        )
    return sha256_digest(
        {
            "artifacts": [
                {
                    "path": item.path,
                    "sha256": item.sha256,
                }
                for item in artifacts
            ],
            "domain": _SOURCE_SET_DOMAIN,
        }
    )


@dataclass(frozen=True, slots=True)
class _ArtifactStatV4:
    device: int
    inode: int
    mode: int
    uid: int
    gid: int
    size: int
    modified_ns: int
    changed_ns: int

    @classmethod
    def from_stat(cls, value: os.stat_result) -> _ArtifactStatV4:
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


def _open_flags() -> int:
    return os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0)


def _validate_stat(value: os.stat_result, spec: RuntimeArtifactSpecV4) -> None:
    if not stat.S_ISREG(value.st_mode):
        raise OperationalArtifactV4Error("runtime artifact is not a regular file")
    if value.st_size < 0 or value.st_size > spec.max_bytes:
        raise OperationalArtifactV4Error("runtime artifact exceeds its byte bound")
    if value.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
        raise OperationalArtifactV4Error(
            "runtime artifact must not be group- or world-writable"
        )
    if spec.require_executable and not value.st_mode & (
        stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
    ):
        raise OperationalArtifactV4Error("runtime executable has no execute bit")


def _hash_descriptor(
    fd: int, spec: RuntimeArtifactSpecV4
) -> tuple[str, _ArtifactStatV4]:
    before_raw = os.fstat(fd)
    _validate_stat(before_raw, spec)
    before = _ArtifactStatV4.from_stat(before_raw)
    hasher = hashlib.sha256()
    offset = 0
    while True:
        remaining = spec.max_bytes + 1 - offset
        if remaining <= 0:
            raise OperationalArtifactV4Error("runtime artifact exceeds its byte bound")
        chunk = os.pread(fd, min(_READ_CHUNK_BYTES, remaining), offset)
        if not chunk:
            break
        hasher.update(chunk)
        offset += len(chunk)
    after_raw = os.fstat(fd)
    _validate_stat(after_raw, spec)
    after = _ArtifactStatV4.from_stat(after_raw)
    if before != after or offset != after.size:
        raise OperationalArtifactChangedV4Error(
            "runtime artifact changed while it was being hashed"
        )
    return hasher.hexdigest(), after


class PinnedRuntimeArtifactV4:
    """One retained descriptor for an exact signed public runtime artifact."""

    def __init__(
        self,
        *,
        spec: RuntimeArtifactSpecV4,
        fd: int,
        admitted_stat: _ArtifactStatV4,
    ) -> None:
        self._spec = spec
        self._fd = fd
        self._admitted_stat = admitted_stat
        self._creator_pid = os.getpid()
        self._closed = False

    @classmethod
    def open_verified(cls, spec: RuntimeArtifactSpecV4) -> PinnedRuntimeArtifactV4:
        if type(spec) is not RuntimeArtifactSpecV4:
            raise TypeError("spec must be an exact RuntimeArtifactSpecV4")
        try:
            fd = os.open(spec.path, _open_flags())
        except OSError as exc:
            raise OperationalArtifactV4Error(
                "runtime artifact could not be opened without following a symlink"
            ) from exc
        try:
            os.set_inheritable(fd, False)
            if os.get_inheritable(fd):
                raise OperationalArtifactV4Error(
                    "runtime artifact descriptor remained inheritable"
                )
            digest, admitted_stat = _hash_descriptor(fd, spec)
            if digest != spec.sha256:
                raise OperationalArtifactV4Error(
                    "runtime artifact digest differs from signed policy"
                )
            return cls(spec=spec, fd=fd, admitted_stat=admitted_stat)
        except BaseException:
            os.close(fd)
            raise

    @property
    def spec(self) -> RuntimeArtifactSpecV4:
        return self._spec

    @property
    def descriptor(self) -> int:
        if self._closed:
            raise OperationalArtifactChangedV4Error("runtime artifact is closed")
        return self._fd

    @property
    def proc_fd_path(self) -> str:
        return f"/proc/self/fd/{self.descriptor}"

    def assert_unchanged(self) -> None:
        if self._closed or os.getpid() != self._creator_pid:
            raise OperationalArtifactChangedV4Error("runtime artifact is not live")
        try:
            if os.get_inheritable(self._fd):
                raise OperationalArtifactChangedV4Error(
                    "runtime artifact descriptor became inheritable"
                )
            digest, current_stat = _hash_descriptor(self._fd, self._spec)
            if digest != self._spec.sha256 or current_stat != self._admitted_stat:
                raise OperationalArtifactChangedV4Error(
                    "retained runtime artifact changed after admission"
                )
            reopened = os.open(self._spec.path, _open_flags())
            try:
                reopened_digest, reopened_stat = _hash_descriptor(reopened, self._spec)
            finally:
                os.close(reopened)
            if (
                reopened_digest != self._spec.sha256
                or reopened_stat != self._admitted_stat
            ):
                raise OperationalArtifactChangedV4Error(
                    "approved runtime artifact path no longer names the retained file"
                )
        except OperationalArtifactV4Error:
            raise
        except OSError as exc:
            raise OperationalArtifactChangedV4Error(
                "runtime artifact could not be revalidated"
            ) from exc

    def read_bytes(self) -> bytes:
        self.assert_unchanged()
        size = self._admitted_stat.size
        raw = os.pread(self._fd, size + 1, 0)
        if len(raw) != size:
            raise OperationalArtifactChangedV4Error(
                "runtime artifact changed during its bounded read"
            )
        self.assert_unchanged()
        return raw

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            os.close(self._fd)

    def __enter__(self) -> PinnedRuntimeArtifactV4:
        self.assert_unchanged()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


__all__ = [
    "ConfiguredChronySourceArtifactV4",
    "OperationalArtifactChangedV4Error",
    "OperationalArtifactV4Error",
    "PinnedRuntimeArtifactV4",
    "RuntimeArtifactSpecV4",
    "derive_configured_chrony_source_set_root_v4",
]
