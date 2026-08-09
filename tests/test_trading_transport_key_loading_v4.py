from __future__ import annotations

import os
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
)
from cryptography.hazmat.primitives.asymmetric.rsa import generate_private_key

import riskyieldmm.trading.transport_key_loading_v4 as key_loading
from riskyieldmm.trading.canonical import sha256_digest
from riskyieldmm.trading.ledger_signing import derive_ed25519_key_id
from riskyieldmm.trading.physical_transport_v4 import (
    derive_transport_attestation_key_id,
)
from riskyieldmm.trading.transport_key_loading_v4 import (
    TRANSPORT_KEY_FILE_MAXIMUM_BYTES_V4,
    TransportKeyLoadingV4ConfigurationError,
    TransportKeyLoadingV4MismatchError,
    TransportKeyLoadingV4SecurityError,
    load_encrypted_pkcs8_ed25519_transport_signer_v4,
)

TEST_PASSWORD = b"test-only-transport-key-password"


def _private_directory(tmp_path: Path, name: str = "transport-keys") -> Path:
    directory = tmp_path / name
    directory.mkdir(mode=0o700)
    directory.chmod(0o700)
    return directory


def _public_bytes(private_key: Ed25519PrivateKey) -> bytes:
    return private_key.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )


def _encrypted_ed25519_file(
    directory: Path,
    *,
    private_key: Ed25519PrivateKey | None = None,
    password: bytes = TEST_PASSWORD,
    mode: int = 0o600,
    name: str = "transport-key.pem",
) -> tuple[Path, Ed25519PrivateKey, bytes]:
    key = private_key or Ed25519PrivateKey.generate()
    payload = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.BestAvailableEncryption(password),
    )
    path = directory / name
    path.write_bytes(payload)
    path.chmod(mode)
    return path, key, _public_bytes(key)


def _load(
    path: Path,
    *,
    public_key: bytes,
    password: bytearray,
    maximum_key_file_bytes: int = TRANSPORT_KEY_FILE_MAXIMUM_BYTES_V4,
):
    return load_encrypted_pkcs8_ed25519_transport_signer_v4(
        path,
        password=password,
        expected_transport_key_id=derive_transport_attestation_key_id(public_key),
        expected_public_key_bytes=public_key,
        maximum_key_file_bytes=maximum_key_file_bytes,
    )


@pytest.mark.parametrize("mode", [0o400, 0o600])
def test_loader_returns_transport_domain_signer_and_consumes_password(
    tmp_path: Path,
    mode: int,
) -> None:
    directory = _private_directory(tmp_path)
    path, private_key, public_key = _encrypted_ed25519_file(
        directory,
        mode=mode,
    )
    password = bytearray(TEST_PASSWORD)

    signer = _load(path, public_key=public_key, password=password)

    assert signer.public_key_bytes == public_key
    assert signer.key_id == derive_transport_attestation_key_id(public_key)
    assert signer.key_id != derive_ed25519_key_id(public_key)
    payload = b"transport-attestation-test-payload"
    signature = signer.sign(payload)
    assert len(signature) == 64
    private_key.public_key().verify(signature, payload)
    assert password == bytearray(len(TEST_PASSWORD))


def test_signer_rejects_non_bytes_payload(tmp_path: Path) -> None:
    directory = _private_directory(tmp_path)
    path, _, public_key = _encrypted_ed25519_file(directory)
    signer = _load(
        path,
        public_key=public_key,
        password=bytearray(TEST_PASSWORD),
    )

    with pytest.raises(TypeError, match="payload must be bytes"):
        signer.sign(bytearray(b"not-an-immutable-payload"))  # type: ignore[arg-type]


def test_loader_uses_read_only_cloexec_nofollow_opens(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    directory = _private_directory(tmp_path)
    path, _, public_key = _encrypted_ed25519_file(directory)
    real_open = key_loading.os.open
    observed_flags: list[int] = []

    def tracking_open(
        path_value: object,
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        observed_flags.append(flags)
        return real_open(path_value, flags, mode, dir_fd=dir_fd)  # type: ignore[arg-type]

    monkeypatch.setattr(key_loading.os, "open", tracking_open)

    _load(path, public_key=public_key, password=bytearray(TEST_PASSWORD))

    assert len(observed_flags) == 2
    assert observed_flags[0] & os.O_DIRECTORY
    assert all(flags & os.O_CLOEXEC for flags in observed_flags)
    assert all(flags & os.O_NOFOLLOW for flags in observed_flags)
    assert all(not flags & (os.O_WRONLY | os.O_RDWR) for flags in observed_flags)


def test_loader_rejects_key_file_symlink(tmp_path: Path) -> None:
    directory = _private_directory(tmp_path)
    target, _, public_key = _encrypted_ed25519_file(
        directory,
        name="real-key.pem",
    )
    link = directory / "linked-key.pem"
    link.symlink_to(target.name)
    password = bytearray(TEST_PASSWORD)

    with pytest.raises(TransportKeyLoadingV4SecurityError):
        _load(link, public_key=public_key, password=password)

    assert password == bytearray(len(TEST_PASSWORD))


def test_loader_rejects_symlinked_parent(tmp_path: Path) -> None:
    real_directory = _private_directory(tmp_path, "real-transport-keys")
    target, _, public_key = _encrypted_ed25519_file(real_directory)
    linked_directory = tmp_path / "linked-transport-keys"
    linked_directory.symlink_to(real_directory, target_is_directory=True)
    password = bytearray(TEST_PASSWORD)

    with pytest.raises(TransportKeyLoadingV4SecurityError):
        _load(
            linked_directory / target.name,
            public_key=public_key,
            password=password,
        )

    assert password == bytearray(len(TEST_PASSWORD))


def test_loader_rejects_hard_linked_key_file(tmp_path: Path) -> None:
    directory = _private_directory(tmp_path)
    path, _, public_key = _encrypted_ed25519_file(directory)
    os.link(path, directory / "second-name.pem")
    password = bytearray(TEST_PASSWORD)

    with pytest.raises(
        TransportKeyLoadingV4SecurityError,
        match="exactly one hard link",
    ):
        _load(path, public_key=public_key, password=password)

    assert password == bytearray(len(TEST_PASSWORD))


@pytest.mark.parametrize("mode", [0o000, 0o440, 0o644])
def test_loader_rejects_non_exact_key_file_mode(
    tmp_path: Path,
    mode: int,
) -> None:
    directory = _private_directory(tmp_path)
    path, _, public_key = _encrypted_ed25519_file(directory, mode=mode)
    password = bytearray(TEST_PASSWORD)

    with pytest.raises(TransportKeyLoadingV4SecurityError, match="0400 or 0600"):
        _load(path, public_key=public_key, password=password)

    assert password == bytearray(len(TEST_PASSWORD))


def test_loader_rejects_non_private_parent_mode(tmp_path: Path) -> None:
    directory = _private_directory(tmp_path)
    path, _, public_key = _encrypted_ed25519_file(directory)
    directory.chmod(0o750)
    password = bytearray(TEST_PASSWORD)

    with pytest.raises(TransportKeyLoadingV4SecurityError, match="mode 0700"):
        _load(path, public_key=public_key, password=password)

    assert password == bytearray(len(TEST_PASSWORD))


def test_loader_rejects_key_different_from_approved_identity(tmp_path: Path) -> None:
    directory = _private_directory(tmp_path)
    path, _, _ = _encrypted_ed25519_file(directory)
    approved_key = Ed25519PrivateKey.generate()
    approved_public_key = _public_bytes(approved_key)
    password = bytearray(TEST_PASSWORD)

    with pytest.raises(
        TransportKeyLoadingV4MismatchError,
        match="loaded transport key differs",
    ):
        _load(path, public_key=approved_public_key, password=password)

    assert password == bytearray(len(TEST_PASSWORD))


def test_loader_rejects_inconsistent_approved_key_id(tmp_path: Path) -> None:
    directory = _private_directory(tmp_path)
    path, _, public_key = _encrypted_ed25519_file(directory)
    password = bytearray(TEST_PASSWORD)

    with pytest.raises(
        TransportKeyLoadingV4MismatchError,
        match="approved transport key ID differs",
    ):
        load_encrypted_pkcs8_ed25519_transport_signer_v4(
            path,
            password=password,
            expected_transport_key_id=sha256_digest({"wrong": "approval"}),
            expected_public_key_bytes=public_key,
        )

    assert password == bytearray(len(TEST_PASSWORD))


def test_loader_rejects_unencrypted_pkcs8(tmp_path: Path) -> None:
    directory = _private_directory(tmp_path)
    key = Ed25519PrivateKey.generate()
    public_key = _public_bytes(key)
    path = directory / "unencrypted-key.pem"
    path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    path.chmod(0o600)
    password = bytearray(TEST_PASSWORD)

    with pytest.raises(
        TransportKeyLoadingV4ConfigurationError,
        match="encrypted PKCS#8 PEM",
    ):
        _load(path, public_key=public_key, password=password)

    assert password == bytearray(len(TEST_PASSWORD))


def test_loader_rejects_encrypted_non_ed25519_pkcs8(tmp_path: Path) -> None:
    directory = _private_directory(tmp_path)
    rsa_key = generate_private_key(public_exponent=65537, key_size=2048)
    path = directory / "rsa-key.pem"
    path.write_bytes(
        rsa_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.BestAvailableEncryption(TEST_PASSWORD),
        )
    )
    path.chmod(0o600)
    approved_public_key = _public_bytes(Ed25519PrivateKey.generate())
    password = bytearray(TEST_PASSWORD)

    with pytest.raises(
        TransportKeyLoadingV4ConfigurationError,
        match="must use the Ed25519 algorithm",
    ):
        _load(path, public_key=approved_public_key, password=password)

    assert password == bytearray(len(TEST_PASSWORD))


def test_loader_rejects_wrong_password_and_consumes_it(tmp_path: Path) -> None:
    directory = _private_directory(tmp_path)
    path, _, public_key = _encrypted_ed25519_file(directory)
    wrong_password = bytearray(b"wrong-password")

    with pytest.raises(
        TransportKeyLoadingV4ConfigurationError,
        match="not a decryptable encrypted PKCS#8",
    ):
        _load(path, public_key=public_key, password=wrong_password)

    assert wrong_password == bytearray(len(b"wrong-password"))


def test_loader_requires_mutable_nonempty_password(tmp_path: Path) -> None:
    directory = _private_directory(tmp_path)
    path, _, public_key = _encrypted_ed25519_file(directory)

    with pytest.raises(
        TransportKeyLoadingV4ConfigurationError,
        match="mutable bytearray",
    ):
        load_encrypted_pkcs8_ed25519_transport_signer_v4(
            path,
            password=TEST_PASSWORD,  # type: ignore[arg-type]
            expected_transport_key_id=derive_transport_attestation_key_id(public_key),
            expected_public_key_bytes=public_key,
        )

    with pytest.raises(
        TransportKeyLoadingV4ConfigurationError,
        match="must not be empty",
    ):
        _load(path, public_key=public_key, password=bytearray())


def test_loader_enforces_bounded_key_file_size(tmp_path: Path) -> None:
    directory = _private_directory(tmp_path)
    path = directory / "oversized-key.pem"
    path.write_bytes(b"x" * (TRANSPORT_KEY_FILE_MAXIMUM_BYTES_V4 + 1))
    path.chmod(0o600)
    approved_public_key = _public_bytes(Ed25519PrivateKey.generate())
    password = bytearray(TEST_PASSWORD)

    with pytest.raises(TransportKeyLoadingV4SecurityError, match="exceeds"):
        _load(path, public_key=approved_public_key, password=password)

    assert password == bytearray(len(TEST_PASSWORD))


def test_loader_rejects_fstat_size_change_during_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    directory = _private_directory(tmp_path)
    path, _, public_key = _encrypted_ed25519_file(directory)
    real_fstat = key_loading.os.fstat
    call_count = 0

    def changing_fstat(fd: int):
        nonlocal call_count
        call_count += 1
        info = real_fstat(fd)
        if call_count != 3:
            return info
        return SimpleNamespace(
            st_mode=info.st_mode,
            st_uid=info.st_uid,
            st_nlink=info.st_nlink,
            st_size=info.st_size + 1,
            st_dev=info.st_dev,
            st_ino=info.st_ino,
            st_mtime_ns=info.st_mtime_ns,
            st_ctime_ns=info.st_ctime_ns,
        )

    monkeypatch.setattr(key_loading.os, "fstat", changing_fstat)
    password = bytearray(TEST_PASSWORD)

    with pytest.raises(
        TransportKeyLoadingV4SecurityError,
        match="changed while it was read",
    ):
        _load(path, public_key=public_key, password=password)

    assert call_count == 3
    assert password == bytearray(len(TEST_PASSWORD))


def test_key_file_is_never_modified(tmp_path: Path) -> None:
    directory = _private_directory(tmp_path)
    path, _, public_key = _encrypted_ed25519_file(directory, mode=0o400)
    before = path.read_bytes()
    before_mode = stat.S_IMODE(path.stat().st_mode)

    _load(path, public_key=public_key, password=bytearray(TEST_PASSWORD))

    assert path.read_bytes() == before
    assert stat.S_IMODE(path.stat().st_mode) == before_mode == 0o400
