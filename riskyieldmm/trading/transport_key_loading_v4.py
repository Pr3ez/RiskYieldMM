"""Fail-closed local key loading for V4 transport attestations.

The transport runtime needs an Ed25519 signer, but it must not silently accept
an arbitrary private key from an ordinary configuration file.  This module is
the narrow boundary between local encrypted PKCS#8 storage and the structural
signer interface consumed by :mod:`riskyieldmm.trading.physical_transport_v4`.

Only an encrypted PKCS#8 PEM file in a private, caller-owned directory is
accepted.  The loader pins both the approved raw public key and the
transport-domain key ID.  Mutable key-file and password buffers are cleared on
every exit path as a best effort; the cryptography provider necessarily keeps
the loaded private-key object in provider-managed memory for the signer's
lifetime.
"""

from __future__ import annotations

import os
import secrets
import stat
from pathlib import Path
from typing import Any

from .canonical import CanonicalizationError, canonical_hash, canonical_safe_int
from .ledger_signing import ed25519_public_key_is_valid
from .physical_transport_v4 import derive_transport_attestation_key_id

TRANSPORT_KEY_FILE_MAXIMUM_BYTES_V4 = 16 * 1024
TRANSPORT_KEY_PASSWORD_MAXIMUM_BYTES_V4 = 4 * 1024
TRANSPORT_KEY_PARENT_DIRECTORY_MODE_V4 = 0o700
TRANSPORT_KEY_ALLOWED_FILE_MODES_V4 = frozenset({0o400, 0o600})

_ENCRYPTED_PKCS8_PEM_BEGIN = b"-----BEGIN ENCRYPTED PRIVATE KEY-----"
_ENCRYPTED_PKCS8_PEM_END = b"-----END ENCRYPTED PRIVATE KEY-----"
_TRAILING_PEM_WHITESPACE = frozenset(b" \t\r\n")


class TransportKeyLoadingV4Error(RuntimeError):
    """Base class for fail-closed transport-key loading errors."""


class TransportKeyLoadingV4ConfigurationError(TransportKeyLoadingV4Error):
    """The caller supplied an invalid loader configuration or key encoding."""


class TransportKeyLoadingV4SecurityError(TransportKeyLoadingV4Error):
    """The local path or file metadata violates the secure-storage policy."""


class TransportKeyLoadingV4MismatchError(TransportKeyLoadingV4Error):
    """The loaded key differs from the independently approved public identity."""


def _cryptography_types() -> tuple[type[Any], Any, Any, Any]:
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PrivateKey,
        )
    except ImportError as exc:  # pragma: no cover - depends on optional extra
        raise TransportKeyLoadingV4ConfigurationError(
            "transport key loading requires riskyieldmm[transport]"
        ) from exc
    return (
        Ed25519PrivateKey,
        serialization.Encoding,
        serialization.PublicFormat,
        serialization.load_pem_private_key,
    )


def _clear_mutable(buffer: bytearray | None) -> None:
    """Best-effort in-place clearing without allocating a second secret copy."""

    if buffer is None:
        return
    for index in range(len(buffer)):
        buffer[index] = 0


def _effective_user_id() -> int:
    get_effective_user_id = getattr(os, "geteuid", None)
    if not callable(get_effective_user_id):  # pragma: no cover - POSIX contract
        raise TransportKeyLoadingV4SecurityError(
            "secure transport key loading requires an effective-user identity"
        )
    return int(get_effective_user_id())


def _secure_open_constants() -> tuple[int, int]:
    close_on_exec = getattr(os, "O_CLOEXEC", None)
    no_follow = getattr(os, "O_NOFOLLOW", None)
    directory = getattr(os, "O_DIRECTORY", None)
    if close_on_exec is None or no_follow is None or directory is None:
        raise TransportKeyLoadingV4SecurityError(
            "secure transport key loading requires O_CLOEXEC, O_NOFOLLOW, and "
            "O_DIRECTORY"
        )
    parent_flags = os.O_RDONLY | close_on_exec | no_follow | directory
    key_flags = os.O_RDONLY | close_on_exec | no_follow
    return parent_flags, key_flags


def _normalize_key_path(path: str | os.PathLike[str]) -> Path:
    try:
        raw_path = os.fspath(path)
    except TypeError as exc:
        raise TransportKeyLoadingV4ConfigurationError(
            "transport key path must be a string or path-like object"
        ) from exc
    if not isinstance(raw_path, str) or not raw_path or "\x00" in raw_path:
        raise TransportKeyLoadingV4ConfigurationError(
            "transport key path must be non-empty text without NUL bytes"
        )
    normalized = Path(os.path.abspath(raw_path))
    if normalized.name in {"", ".", ".."}:
        raise TransportKeyLoadingV4ConfigurationError(
            "transport key path must identify a file"
        )
    return normalized


def _validate_parent_metadata(path: Path, info: os.stat_result, *, euid: int) -> None:
    if stat.S_ISLNK(info.st_mode):
        raise TransportKeyLoadingV4SecurityError(
            f"transport key parent must not be a symlink: {path}"
        )
    if not stat.S_ISDIR(info.st_mode):
        raise TransportKeyLoadingV4SecurityError(
            f"transport key parent must be a directory: {path}"
        )
    if info.st_uid != euid:
        raise TransportKeyLoadingV4SecurityError(
            f"transport key parent must be owned by the effective user: {path}"
        )
    mode = stat.S_IMODE(info.st_mode)
    if mode != TRANSPORT_KEY_PARENT_DIRECTORY_MODE_V4:
        raise TransportKeyLoadingV4SecurityError(
            f"transport key parent must have mode 0700; found {mode:04o}: {path}"
        )


def _validate_file_metadata(
    path: Path,
    info: os.stat_result,
    *,
    euid: int,
    maximum_bytes: int,
) -> None:
    if not stat.S_ISREG(info.st_mode):
        raise TransportKeyLoadingV4SecurityError(
            f"transport key must be a regular file: {path}"
        )
    if info.st_uid != euid:
        raise TransportKeyLoadingV4SecurityError(
            f"transport key must be owned by the effective user: {path}"
        )
    if info.st_nlink != 1:
        raise TransportKeyLoadingV4SecurityError(
            f"transport key must have exactly one hard link: {path}"
        )
    mode = stat.S_IMODE(info.st_mode)
    if mode not in TRANSPORT_KEY_ALLOWED_FILE_MODES_V4:
        allowed = "0400 or 0600"
        raise TransportKeyLoadingV4SecurityError(
            f"transport key must have mode {allowed}; found {mode:04o}: {path}"
        )
    if info.st_size <= 0:
        raise TransportKeyLoadingV4SecurityError(
            f"transport key file must not be empty: {path}"
        )
    if info.st_size > maximum_bytes:
        raise TransportKeyLoadingV4SecurityError(
            f"transport key file exceeds {maximum_bytes} bytes: {path}"
        )


def _identity_and_size(info: os.stat_result) -> tuple[int, int, int]:
    return info.st_dev, info.st_ino, info.st_size


def _change_stamp(info: os.stat_result) -> tuple[int, int]:
    return info.st_mtime_ns, info.st_ctime_ns


def _same_entry(
    descriptor: os.stat_result,
    directory_entry: os.stat_result,
) -> bool:
    return _identity_and_size(descriptor) == _identity_and_size(directory_entry)


def _inspect_directory_entry(parent_fd: int, name: str, path: Path) -> os.stat_result:
    try:
        return os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except OSError as exc:
        raise TransportKeyLoadingV4SecurityError(
            f"cannot inspect transport key directory entry: {path}"
        ) from exc


def _inspect_descriptor(fd: int, *, description: str) -> os.stat_result:
    try:
        return os.fstat(fd)
    except OSError as exc:
        raise TransportKeyLoadingV4SecurityError(
            f"cannot inspect open {description} descriptor"
        ) from exc


def _read_bounded_file(
    fd: int,
    *,
    expected_size: int,
    maximum_bytes: int,
) -> bytearray:
    payload = bytearray()
    try:
        while len(payload) <= expected_size:
            remaining_with_probe = expected_size - len(payload) + 1
            chunk = os.read(fd, min(remaining_with_probe, 4096))
            if not chunk:
                break
            payload.extend(chunk)
            if len(payload) > expected_size or len(payload) > maximum_bytes:
                raise TransportKeyLoadingV4SecurityError(
                    "transport key file size changed while it was read"
                )
        if len(payload) != expected_size:
            raise TransportKeyLoadingV4SecurityError(
                "transport key file size changed while it was read"
            )
        return payload
    except Exception:
        _clear_mutable(payload)
        raise


def _read_secure_key_file(path: Path, *, maximum_bytes: int) -> bytearray:
    euid = _effective_user_id()
    parent_flags, key_flags = _secure_open_constants()
    parent = path.parent

    try:
        parent_before = parent.stat(follow_symlinks=False)
    except OSError as exc:
        raise TransportKeyLoadingV4SecurityError(
            f"cannot inspect transport key parent: {parent}"
        ) from exc
    _validate_parent_metadata(parent, parent_before, euid=euid)

    # Resolve only for a comparison: any symlink in the parent path is rejected.
    # The actual open below remains anchored to an O_NOFOLLOW directory handle.
    try:
        if parent.resolve(strict=True) != parent:
            raise TransportKeyLoadingV4SecurityError(
                f"transport key parent path must contain no symlink: {parent}"
            )
    except OSError as exc:
        raise TransportKeyLoadingV4SecurityError(
            f"cannot resolve transport key parent: {parent}"
        ) from exc

    try:
        parent_fd = os.open(parent, parent_flags)
    except OSError as exc:
        raise TransportKeyLoadingV4SecurityError(
            f"cannot securely open transport key parent: {parent}"
        ) from exc
    try:
        parent_descriptor = _inspect_descriptor(
            parent_fd,
            description="transport key parent",
        )
        _validate_parent_metadata(parent, parent_descriptor, euid=euid)
        if (parent_before.st_dev, parent_before.st_ino) != (
            parent_descriptor.st_dev,
            parent_descriptor.st_ino,
        ):
            raise TransportKeyLoadingV4SecurityError(
                f"transport key parent changed while opening: {parent}"
            )

        entry_before = _inspect_directory_entry(parent_fd, path.name, path)
        _validate_file_metadata(
            path,
            entry_before,
            euid=euid,
            maximum_bytes=maximum_bytes,
        )
        try:
            key_fd = os.open(path.name, key_flags, dir_fd=parent_fd)
        except OSError as exc:
            raise TransportKeyLoadingV4SecurityError(
                f"cannot securely open transport key: {path}"
            ) from exc
        payload: bytearray | None = None
        try:
            descriptor_before = _inspect_descriptor(
                key_fd,
                description="transport key",
            )
            _validate_file_metadata(
                path,
                descriptor_before,
                euid=euid,
                maximum_bytes=maximum_bytes,
            )
            if not _same_entry(descriptor_before, entry_before):
                raise TransportKeyLoadingV4SecurityError(
                    f"transport key changed while opening: {path}"
                )
            payload = _read_bounded_file(
                key_fd,
                expected_size=descriptor_before.st_size,
                maximum_bytes=maximum_bytes,
            )
            descriptor_after = _inspect_descriptor(
                key_fd,
                description="transport key",
            )
            entry_after = _inspect_directory_entry(parent_fd, path.name, path)
            _validate_file_metadata(
                path,
                descriptor_after,
                euid=euid,
                maximum_bytes=maximum_bytes,
            )
            _validate_file_metadata(
                path,
                entry_after,
                euid=euid,
                maximum_bytes=maximum_bytes,
            )
            continuous = (
                _same_entry(descriptor_before, descriptor_after)
                and _same_entry(descriptor_after, entry_after)
                and _change_stamp(descriptor_before) == _change_stamp(descriptor_after)
            )
            if not continuous:
                raise TransportKeyLoadingV4SecurityError(
                    f"transport key changed while it was read: {path}"
                )
            parent_after = _inspect_descriptor(
                parent_fd,
                description="transport key parent",
            )
            _validate_parent_metadata(parent, parent_after, euid=euid)
            if (parent_descriptor.st_dev, parent_descriptor.st_ino) != (
                parent_after.st_dev,
                parent_after.st_ino,
            ):
                raise TransportKeyLoadingV4SecurityError(
                    f"transport key parent changed while reading: {parent}"
                )
            result = payload
            payload = None
            return result
        except Exception:
            _clear_mutable(payload)
            raise
        finally:
            os.close(key_fd)
    finally:
        os.close(parent_fd)


def _require_encrypted_pkcs8_pem(payload: bytearray) -> None:
    if not payload.startswith(_ENCRYPTED_PKCS8_PEM_BEGIN):
        raise TransportKeyLoadingV4ConfigurationError(
            "transport key must use encrypted PKCS#8 PEM encoding"
        )
    header_end = len(_ENCRYPTED_PKCS8_PEM_BEGIN)
    if len(payload) <= header_end or payload[header_end] not in {10, 13}:
        raise TransportKeyLoadingV4ConfigurationError(
            "transport key has an invalid encrypted PKCS#8 PEM envelope"
        )
    content_end = len(payload)
    while content_end and payload[content_end - 1] in _TRAILING_PEM_WHITESPACE:
        content_end -= 1
    footer_start = content_end - len(_ENCRYPTED_PKCS8_PEM_END)
    if (
        footer_start < 0
        or payload.find(_ENCRYPTED_PKCS8_PEM_END, footer_start, content_end)
        != footer_start
    ):
        raise TransportKeyLoadingV4ConfigurationError(
            "transport key has an invalid encrypted PKCS#8 PEM envelope"
        )


class TransportEd25519SignerV4:
    """Transport-domain Ed25519 signer adapter with no private-key export API."""

    algorithm = "ED25519"

    def __init__(self, private_key: Any) -> None:
        private_type, encoding, public_format, _ = _cryptography_types()
        if not isinstance(private_key, private_type):
            raise TypeError("private_key must be an Ed25519PrivateKey")
        public_key_bytes = private_key.public_key().public_bytes(
            encoding.Raw,
            public_format.Raw,
        )
        if not ed25519_public_key_is_valid(public_key_bytes):
            raise TransportKeyLoadingV4ConfigurationError(
                "transport Ed25519 public key is not a valid main-subgroup point"
            )
        self._private_key = private_key
        self.public_key_bytes = public_key_bytes
        self.key_id = derive_transport_attestation_key_id(public_key_bytes)

    def sign(self, payload: bytes) -> bytes:
        if not isinstance(payload, bytes):
            raise TypeError("transport attestation payload must be bytes")
        return self._private_key.sign(payload)


def load_encrypted_pkcs8_ed25519_transport_signer_v4(
    path: str | os.PathLike[str],
    *,
    password: bytearray,
    expected_transport_key_id: str,
    expected_public_key_bytes: bytes,
    maximum_key_file_bytes: int = TRANSPORT_KEY_FILE_MAXIMUM_BYTES_V4,
) -> TransportEd25519SignerV4:
    """Load one approved transport signer and consume ``password`` in place.

    ``password`` must be a mutable :class:`bytearray`; it is overwritten with
    zero bytes before this function returns or raises.  The expected key ID and
    raw public key are independent governance inputs, not values discovered
    from the private-key file.
    """

    if not isinstance(password, bytearray):
        raise TransportKeyLoadingV4ConfigurationError(
            "transport key password must be supplied as a mutable bytearray"
        )

    key_payload: bytearray | None = None
    try:
        if not password:
            raise TransportKeyLoadingV4ConfigurationError(
                "encrypted PKCS#8 transport key password must not be empty"
            )
        if len(password) > TRANSPORT_KEY_PASSWORD_MAXIMUM_BYTES_V4:
            raise TransportKeyLoadingV4ConfigurationError(
                "transport key password exceeds the bounded input size"
            )
        try:
            maximum_bytes = canonical_safe_int(
                maximum_key_file_bytes,
                field="maximum_key_file_bytes",
                minimum=1,
                maximum=TRANSPORT_KEY_FILE_MAXIMUM_BYTES_V4,
            )
            approved_key_id = canonical_hash(
                expected_transport_key_id,
                field="expected_transport_key_id",
            )
        except CanonicalizationError as exc:
            raise TransportKeyLoadingV4ConfigurationError(str(exc)) from exc
        if (
            not isinstance(expected_public_key_bytes, bytes)
            or len(expected_public_key_bytes) != 32
            or not ed25519_public_key_is_valid(expected_public_key_bytes)
        ):
            raise TransportKeyLoadingV4ConfigurationError(
                "expected transport public key must be exactly one valid "
                "Ed25519 public key"
            )
        derived_approved_key_id = derive_transport_attestation_key_id(
            expected_public_key_bytes
        )
        if not secrets.compare_digest(approved_key_id, derived_approved_key_id):
            raise TransportKeyLoadingV4MismatchError(
                "approved transport key ID differs from the approved public key"
            )

        key_path = _normalize_key_path(path)
        key_payload = _read_secure_key_file(
            key_path,
            maximum_bytes=maximum_bytes,
        )
        _require_encrypted_pkcs8_pem(key_payload)

        private_type, _, _, load_pem_private_key = _cryptography_types()
        try:
            private_key = load_pem_private_key(key_payload, password)
        except (TypeError, ValueError) as exc:
            raise TransportKeyLoadingV4ConfigurationError(
                "transport key is not a decryptable encrypted PKCS#8 private key"
            ) from exc
        if not isinstance(private_key, private_type):
            raise TransportKeyLoadingV4ConfigurationError(
                "transport private key must use the Ed25519 algorithm"
            )

        signer = TransportEd25519SignerV4(private_key)
        if not secrets.compare_digest(
            signer.public_key_bytes,
            expected_public_key_bytes,
        ) or not secrets.compare_digest(signer.key_id, approved_key_id):
            raise TransportKeyLoadingV4MismatchError(
                "loaded transport key differs from the approved public identity"
            )
        return signer
    finally:
        _clear_mutable(key_payload)
        _clear_mutable(password)


__all__ = [
    "TRANSPORT_KEY_ALLOWED_FILE_MODES_V4",
    "TRANSPORT_KEY_FILE_MAXIMUM_BYTES_V4",
    "TRANSPORT_KEY_PARENT_DIRECTORY_MODE_V4",
    "TRANSPORT_KEY_PASSWORD_MAXIMUM_BYTES_V4",
    "TransportEd25519SignerV4",
    "TransportKeyLoadingV4ConfigurationError",
    "TransportKeyLoadingV4Error",
    "TransportKeyLoadingV4MismatchError",
    "TransportKeyLoadingV4SecurityError",
    "load_encrypted_pkcs8_ed25519_transport_signer_v4",
]
