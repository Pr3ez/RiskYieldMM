"""Process-local writer exclusion for one physical transport runtime.

This module makes a deliberately narrow claim: on a local Linux filesystem
whose native ``flock(2)`` and ``fsync(2)`` semantics are reliable, one held
``PhysicalTransportWriterLeaseV4`` excludes independently opened writers for
the same unchanged regular file. It makes no correctness or durability claim
for NFS, other network filesystems, distributed filesystems, or mounts that
emulate or disable advisory locks.

The JSON stored in the lease file is diagnostic metadata, not a PID-file
ownership protocol. Neither a PID nor stale file contents establish authority.
Authority exists only while this process holds the kernel lock on the validated
open-file description. The raw random lease token is never persisted.

``flock`` fences an inode, not a pathname.  The implementation therefore
requires a current-user-owned mode-0700 parent without symlink ancestry,
rejects multiply linked files, and revalidates the pathname/inode before every
authority operation.  It does not defend against a malicious process running
as the same effective user replacing the file between validations; the
authority runtime directory must be exclusively administered by that user.
"""

from __future__ import annotations

import errno
import fcntl
import hashlib
import os
import secrets
import stat
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Final

from .canonical import (
    CanonicalizationError,
    canonical_identifier,
    canonical_json_bytes,
    utc_iso,
)

PHYSICAL_TRANSPORT_WRITER_LEASE_SCHEMA_VERSION: Final = "V4.4"
PHYSICAL_TRANSPORT_WRITER_LEASE_FILE_MODE: Final = 0o600
_LEASE_TOKEN_BYTES: Final = 32
_MAXIMUM_OPEN_RACE_RETRIES: Final = 8


class PhysicalTransportLeaseV4Error(RuntimeError):
    """Base class for physical-transport writer-lease failures."""


class PhysicalTransportLeaseV4ConfigurationError(PhysicalTransportLeaseV4Error):
    """Raised when the lease path or holder configuration is unsafe."""


class PhysicalTransportLeaseV4ConflictError(PhysicalTransportLeaseV4Error):
    """Raised when another open-file description already holds the lease."""


class PhysicalTransportLeaseV4StateError(PhysicalTransportLeaseV4Error):
    """Raised when the one-shot lease object is not in the required state."""


class _LeaseState(str, Enum):
    READY = "READY"
    HELD = "HELD"
    RELEASED = "RELEASED"


class PhysicalTransportWriterLeaseV4:
    """One-shot context manager backed solely by a nonblocking Linux ``flock``.

    Instances may retry ``acquire`` after a contention failure, but an instance
    that successfully acquired and released its lock cannot be reused. A fresh
    instance receives a fresh immutable 256-bit token.
    """

    __slots__ = (
        "_acquired_at",
        "_acquiring_pid",
        "_fd",
        "_holder_id",
        "_lease_token",
        "_lease_token_sha256",
        "_path",
        "_state",
    )

    def __init__(self, path: str | os.PathLike[str], *, holder_id: str) -> None:
        try:
            canonical_holder = canonical_identifier(
                holder_id,
                field="holder_id",
                maximum=256,
            )
        except CanonicalizationError as exc:
            raise PhysicalTransportLeaseV4ConfigurationError(
                "holder_id is not canonical"
            ) from exc
        try:
            raw_path = os.fspath(path)
        except TypeError as exc:
            raise PhysicalTransportLeaseV4ConfigurationError(
                "lease path must be a string or path-like object"
            ) from exc
        if not isinstance(raw_path, str) or not raw_path or "\x00" in raw_path:
            raise PhysicalTransportLeaseV4ConfigurationError(
                "lease path must be a non-empty text path without NUL bytes"
            )
        lease_path = Path(raw_path)
        if lease_path.name in {"", ".", ".."}:
            raise PhysicalTransportLeaseV4ConfigurationError(
                "lease path must identify a file"
            )

        lease_token = secrets.token_hex(_LEASE_TOKEN_BYTES)
        self._path = lease_path
        self._holder_id = canonical_holder
        self._lease_token = lease_token
        self._lease_token_sha256 = hashlib.sha256(
            bytes.fromhex(lease_token)
        ).hexdigest()
        self._fd: int | None = None
        self._acquired_at: str | None = None
        self._acquiring_pid: int | None = None
        self._state = _LeaseState.READY

    @property
    def path(self) -> Path:
        """Return the configured lease-file path."""

        return self._path

    @property
    def holder_id(self) -> str:
        """Return the validated, unmodified holder identity."""

        return self._holder_id

    @property
    def lease_token(self) -> str:
        """Return this instance's immutable in-memory 256-bit token."""

        return self._lease_token

    @property
    def is_held(self) -> bool:
        """Whether this process currently holds this instance's open-file lock."""

        return (
            self._state is _LeaseState.HELD
            and self._fd is not None
            and self._acquiring_pid == os.getpid()
        )

    @staticmethod
    def _secure_open_flags() -> int:
        flags = os.O_RDWR
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        return flags

    @classmethod
    def _validate_path_info(cls, path: Path, info: os.stat_result) -> None:
        if stat.S_ISLNK(info.st_mode):
            raise PhysicalTransportLeaseV4ConfigurationError(
                f"lease path must not be a symlink: {path}"
            )
        if not stat.S_ISREG(info.st_mode):
            raise PhysicalTransportLeaseV4ConfigurationError(
                f"lease path must be a regular file: {path}"
            )
        mode = stat.S_IMODE(info.st_mode)
        if mode != PHYSICAL_TRANSPORT_WRITER_LEASE_FILE_MODE:
            raise PhysicalTransportLeaseV4ConfigurationError(
                f"lease file must have final mode 0600; found {mode:04o}: {path}"
            )
        if info.st_uid != os.geteuid():
            raise PhysicalTransportLeaseV4ConfigurationError(
                f"lease file must be owned by the effective user: {path}"
            )
        if info.st_nlink != 1:
            raise PhysicalTransportLeaseV4ConfigurationError(
                f"lease file must have exactly one hard link: {path}"
            )

    @classmethod
    def _validate_existing_path(cls, path: Path) -> os.stat_result:
        try:
            info = path.stat(follow_symlinks=False)
        except FileNotFoundError:
            raise
        except OSError as exc:
            raise PhysicalTransportLeaseV4ConfigurationError(
                f"cannot inspect lease path: {path}"
            ) from exc
        cls._validate_path_info(path, info)
        return info

    @classmethod
    def _validate_open_file(cls, fd: int, path: Path) -> None:
        try:
            descriptor = os.fstat(fd)
        except OSError as exc:
            raise PhysicalTransportLeaseV4StateError(
                "lease file descriptor is not open"
            ) from exc
        cls._validate_path_info(path, descriptor)
        try:
            pathname = cls._validate_existing_path(path)
        except FileNotFoundError as exc:
            raise PhysicalTransportLeaseV4StateError(
                f"lease path disappeared while open: {path}"
            ) from exc
        if (descriptor.st_dev, descriptor.st_ino) != (
            pathname.st_dev,
            pathname.st_ino,
        ):
            raise PhysicalTransportLeaseV4StateError(
                f"lease path changed while open: {path}"
            )

    def _validate_parent_directory(self) -> None:
        parent = self._path.parent
        try:
            info = parent.stat(follow_symlinks=False)
        except FileNotFoundError as exc:
            raise PhysicalTransportLeaseV4ConfigurationError(
                f"lease parent directory does not exist: {parent}"
            ) from exc
        except OSError as exc:
            raise PhysicalTransportLeaseV4ConfigurationError(
                f"cannot inspect lease parent directory: {parent}"
            ) from exc
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
            raise PhysicalTransportLeaseV4ConfigurationError(
                f"lease parent must be a real directory, not a symlink: {parent}"
            )
        mode = stat.S_IMODE(info.st_mode)
        if info.st_uid != os.geteuid():
            raise PhysicalTransportLeaseV4ConfigurationError(
                f"lease parent must be owned by the effective user: {parent}"
            )
        if mode != 0o700:
            raise PhysicalTransportLeaseV4ConfigurationError(
                f"lease parent must have exact mode 0700; found {mode:04o}: {parent}"
            )
        try:
            resolved = parent.resolve(strict=True)
        except OSError as exc:
            raise PhysicalTransportLeaseV4ConfigurationError(
                f"cannot resolve lease parent without symlinks: {parent}"
            ) from exc
        if resolved != parent.absolute():
            raise PhysicalTransportLeaseV4ConfigurationError(
                f"lease parent path must not contain symlink components: {parent}"
            )

    def _open_file(self) -> int:
        flags = self._secure_open_flags()
        for _ in range(_MAXIMUM_OPEN_RACE_RETRIES):
            created = False
            try:
                fd = os.open(
                    self._path,
                    flags | os.O_CREAT | os.O_EXCL,
                    PHYSICAL_TRANSPORT_WRITER_LEASE_FILE_MODE,
                )
                created = True
            except FileExistsError:
                try:
                    self._validate_existing_path(self._path)
                    fd = os.open(self._path, flags)
                except FileNotFoundError:
                    continue
                except OSError as exc:
                    if exc.errno == errno.ELOOP:
                        raise PhysicalTransportLeaseV4ConfigurationError(
                            f"lease path must not be a symlink: {self._path}"
                        ) from exc
                    raise PhysicalTransportLeaseV4ConfigurationError(
                        f"cannot securely open lease file: {self._path}"
                    ) from exc
            except OSError as exc:
                if exc.errno == errno.ELOOP:
                    raise PhysicalTransportLeaseV4ConfigurationError(
                        f"lease path must not be a symlink: {self._path}"
                    ) from exc
                raise PhysicalTransportLeaseV4ConfigurationError(
                    f"cannot create lease file: {self._path}"
                ) from exc
            try:
                if created:
                    os.fchmod(fd, PHYSICAL_TRANSPORT_WRITER_LEASE_FILE_MODE)
                self._validate_open_file(fd, self._path)
            except PhysicalTransportLeaseV4Error:
                os.close(fd)
                raise
            except OSError as exc:
                os.close(fd)
                raise PhysicalTransportLeaseV4ConfigurationError(
                    f"cannot validate lease file after open: {self._path}"
                ) from exc
            return fd
        raise PhysicalTransportLeaseV4ConfigurationError(
            f"lease path changed repeatedly during secure open: {self._path}"
        )

    @staticmethod
    def _write_all(fd: int, payload: bytes) -> None:
        view = memoryview(payload)
        offset = 0
        while offset < len(view):
            try:
                written = os.write(fd, view[offset:])
            except InterruptedError:
                continue
            if written <= 0:
                raise OSError("lease metadata write made no progress")
            offset += written

    def _write_metadata(
        self,
        fd: int,
        *,
        state: str,
        released_at: str | None = None,
    ) -> None:
        if self._acquired_at is None or self._acquiring_pid is None:
            raise PhysicalTransportLeaseV4StateError(
                "lease acquisition metadata is unavailable"
            )
        metadata: dict[str, str | int] = {
            "acquired_at": self._acquired_at,
            "holder_id": self._holder_id,
            "lease_token_sha256": self._lease_token_sha256,
            "pid": self._acquiring_pid,
            "schema_version": PHYSICAL_TRANSPORT_WRITER_LEASE_SCHEMA_VERSION,
            "state": state,
        }
        if released_at is not None:
            metadata["released_at"] = released_at
        payload = canonical_json_bytes(metadata)
        os.lseek(fd, 0, os.SEEK_SET)
        self._write_all(fd, payload)
        os.ftruncate(fd, len(payload))
        os.fsync(fd)

    def _fsync_parent_directory(self) -> None:
        flags = os.O_RDONLY
        if hasattr(os, "O_DIRECTORY"):
            flags |= os.O_DIRECTORY
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            parent_fd = os.open(self._path.parent, flags)
        except OSError as exc:
            raise PhysicalTransportLeaseV4ConfigurationError(
                f"cannot securely open lease parent directory: {self._path.parent}"
            ) from exc
        try:
            os.fsync(parent_fd)
        except OSError as exc:
            raise PhysicalTransportLeaseV4ConfigurationError(
                f"cannot fsync lease parent directory: {self._path.parent}"
            ) from exc
        finally:
            os.close(parent_fd)

    def acquire(self) -> PhysicalTransportWriterLeaseV4:
        """Acquire the nonblocking exclusive lease and durably publish metadata.

        Callers must use the context manager or guarantee an explicit
        ``release()`` in ``finally``; integer file descriptors aren't released
        by object garbage collection.
        """

        if self._state is _LeaseState.HELD:
            raise PhysicalTransportLeaseV4StateError("writer lease is already held")
        if self._state is _LeaseState.RELEASED:
            raise PhysicalTransportLeaseV4StateError(
                "released writer lease instances cannot be reused"
            )
        self._validate_parent_directory()
        fd = self._open_file()
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            os.close(fd)
            if isinstance(exc, BlockingIOError) or exc.errno in {
                errno.EACCES,
                errno.EAGAIN,
            }:
                raise PhysicalTransportLeaseV4ConflictError(
                    f"another writer holds the physical transport lease: {self._path}"
                ) from exc
            raise PhysicalTransportLeaseV4ConfigurationError(
                f"cannot lock physical transport lease: {self._path}"
            ) from exc

        self._acquiring_pid = os.getpid()
        self._acquired_at = utc_iso(
            datetime.now(timezone.utc),
            field="acquired_at",
        )
        try:
            self._validate_open_file(fd, self._path)
            self._write_metadata(fd, state="HELD")
            self._fsync_parent_directory()
            self._validate_open_file(fd, self._path)
        except BaseException as exc:
            cleanup_failure: BaseException | None = None
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            except BaseException as cleanup_exc:
                cleanup_failure = cleanup_exc
            try:
                os.close(fd)
            except BaseException as cleanup_exc:
                cleanup_failure = cleanup_failure or cleanup_exc
            self._acquiring_pid = None
            self._acquired_at = None
            if cleanup_failure is not None:
                raise PhysicalTransportLeaseV4StateError(
                    "writer lease acquisition cleanup failed"
                ) from cleanup_failure
            if isinstance(exc, PhysicalTransportLeaseV4Error):
                raise
            if isinstance(exc, OSError):
                raise PhysicalTransportLeaseV4StateError(
                    "writer lease metadata could not be durably published"
                ) from exc
            raise

        self._fd = fd
        self._state = _LeaseState.HELD
        return self

    def assert_held(self) -> None:
        """Raise unless this process owns the unchanged lease object.

        This validates process identity, descriptor/path inode continuity, and
        reacquires the same open-description flock nonblockingly.  Linux has no
        separate API that can prove uninterrupted historical lock ownership.
        """

        if not self.is_held or self._fd is None:
            raise PhysicalTransportLeaseV4StateError(
                "physical transport writer lease is not held by this process"
            )
        try:
            self._validate_open_file(self._fd, self._path)
            fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise PhysicalTransportLeaseV4StateError(
                "physical transport writer flock is no longer held"
            ) from exc
        except PhysicalTransportLeaseV4Error as exc:
            raise PhysicalTransportLeaseV4StateError(
                "held physical transport writer lease is no longer safe"
            ) from exc

    def release(self) -> None:
        """Durably record safe release, then unlock and close; repeat calls are no-ops."""

        if self._state is not _LeaseState.HELD or self._fd is None:
            return

        fd = self._fd
        acquired_in_this_process = self._acquiring_pid == os.getpid()
        failure: BaseException | None = None
        if not acquired_in_this_process:
            failure = PhysicalTransportLeaseV4StateError(
                "a forked child cannot release its parent's writer lease"
            )
        else:
            try:
                self._validate_open_file(fd, self._path)
                released_at = utc_iso(
                    datetime.now(timezone.utc),
                    field="released_at",
                )
                self._write_metadata(fd, state="RELEASED", released_at=released_at)
                self._fsync_parent_directory()
                self._validate_open_file(fd, self._path)
            except BaseException as exc:  # release must still unlock and close
                failure = exc

        if acquired_in_this_process:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            except BaseException as exc:  # closing still releases a local flock
                failure = failure or exc
        try:
            os.close(fd)
        except BaseException as exc:
            failure = failure or exc
        finally:
            self._fd = None
            self._state = _LeaseState.RELEASED

        if failure is not None:
            raise PhysicalTransportLeaseV4StateError(
                "writer lease released without a durable safe release record"
            ) from failure

    def __enter__(self) -> PhysicalTransportWriterLeaseV4:
        return self.acquire()

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.release()
