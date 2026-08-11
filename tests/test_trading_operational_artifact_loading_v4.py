from __future__ import annotations

import hashlib
import os
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from riskyieldmm.trading.canonical import CanonicalizationError
from riskyieldmm.trading.operational_artifact_loading_v4 import (
    ConfiguredChronySourceArtifactV4,
    OperationalArtifactChangedV4Error,
    OperationalArtifactV4Error,
    PinnedRuntimeArtifactV4,
    RuntimeArtifactSpecV4,
    derive_configured_chrony_source_set_root_v4,
)


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _write_artifact(
    tmp_path: Path,
    *,
    payload: bytes = b"admitted runtime artifact\n",
    name: str = "runtime-artifact",
    mode: int = 0o644,
) -> Path:
    path = tmp_path / name
    path.write_bytes(payload)
    path.chmod(mode)
    return path


def _spec(
    path: Path,
    payload: bytes,
    *,
    max_bytes: int | None = None,
    require_executable: bool = False,
) -> RuntimeArtifactSpecV4:
    return RuntimeArtifactSpecV4(
        path=str(path),
        sha256=_digest(payload),
        max_bytes=len(payload) if max_bytes is None else max_bytes,
        require_executable=require_executable,
    )


def _source(path: str, marker: bytes) -> ConfiguredChronySourceArtifactV4:
    return ConfiguredChronySourceArtifactV4(
        path=path,
        sha256=_digest(marker),
    )


def test_verified_artifact_retains_non_inheritable_descriptor_and_revalidates(
    tmp_path: Path,
) -> None:
    payload = b"exact admitted chronyc bytes\n"
    path = _write_artifact(tmp_path, payload=payload, mode=0o755)

    with PinnedRuntimeArtifactV4.open_verified(
        _spec(path, payload, require_executable=True)
    ) as artifact:
        descriptor = artifact.descriptor
        assert descriptor >= 0
        assert not os.get_inheritable(descriptor)
        assert artifact.proc_fd_path == f"/proc/self/fd/{descriptor}"
        assert artifact.read_bytes() == payload
        artifact.assert_unchanged()
        assert artifact.read_bytes() == payload

    with pytest.raises(OperationalArtifactChangedV4Error, match="closed"):
        _ = artifact.descriptor


def test_open_rejects_digest_different_from_signed_policy(tmp_path: Path) -> None:
    payload = b"deployed bytes\n"
    path = _write_artifact(tmp_path, payload=payload)
    approved_payload = b"different signed bytes\n"

    with pytest.raises(
        OperationalArtifactV4Error,
        match="digest differs from signed policy",
    ):
        PinnedRuntimeArtifactV4.open_verified(_spec(path, approved_payload))


def test_open_rejects_leaf_symlink_even_when_target_digest_matches(
    tmp_path: Path,
) -> None:
    payload = b"real artifact\n"
    target = _write_artifact(tmp_path, payload=payload, name="real-artifact")
    link = tmp_path / "linked-artifact"
    link.symlink_to(target.name)

    with pytest.raises(
        OperationalArtifactV4Error,
        match="without following a symlink",
    ):
        PinnedRuntimeArtifactV4.open_verified(_spec(link, payload))


def test_open_rejects_artifact_larger_than_signed_byte_bound(
    tmp_path: Path,
) -> None:
    payload = b"0123456789"
    path = _write_artifact(tmp_path, payload=payload)

    with pytest.raises(OperationalArtifactV4Error, match="exceeds its byte bound"):
        PinnedRuntimeArtifactV4.open_verified(
            _spec(path, payload, max_bytes=len(payload) - 1)
        )


@pytest.mark.parametrize("mode", [0o664, 0o646, 0o666])
def test_open_rejects_group_or_world_writable_artifact(
    tmp_path: Path,
    mode: int,
) -> None:
    payload = b"writable artifact\n"
    path = _write_artifact(tmp_path, payload=payload, mode=mode)

    with pytest.raises(
        OperationalArtifactV4Error,
        match="must not be group- or world-writable",
    ):
        PinnedRuntimeArtifactV4.open_verified(_spec(path, payload))


def test_open_rejects_required_executable_without_any_execute_bit(
    tmp_path: Path,
) -> None:
    payload = b"not executable\n"
    path = _write_artifact(tmp_path, payload=payload, mode=0o644)

    with pytest.raises(
        OperationalArtifactV4Error,
        match="executable has no execute bit",
    ):
        PinnedRuntimeArtifactV4.open_verified(
            _spec(path, payload, require_executable=True)
        )


def test_revalidation_rejects_atomic_path_replacement_with_identical_bytes(
    tmp_path: Path,
) -> None:
    payload = b"same content, different inode\n"
    path = _write_artifact(tmp_path, payload=payload)
    artifact = PinnedRuntimeArtifactV4.open_verified(_spec(path, payload))
    replacement = _write_artifact(
        tmp_path,
        payload=payload,
        name="replacement-artifact",
    )
    os.replace(replacement, path)

    try:
        with pytest.raises(OperationalArtifactChangedV4Error):
            artifact.assert_unchanged()
    finally:
        artifact.close()


def test_revalidation_rejects_in_place_content_change(tmp_path: Path) -> None:
    original = b"approved-bytes-1\n"
    changed = b"tampered-bytes-2\n"
    assert len(original) == len(changed)
    path = _write_artifact(tmp_path, payload=original)
    artifact = PinnedRuntimeArtifactV4.open_verified(_spec(path, original))
    path.write_bytes(changed)

    try:
        with pytest.raises(
            OperationalArtifactChangedV4Error,
            match="retained runtime artifact changed after admission",
        ):
            artifact.assert_unchanged()
    finally:
        artifact.close()


def test_close_is_idempotent_and_closed_artifact_fails_closed(
    tmp_path: Path,
) -> None:
    payload = b"close semantics\n"
    path = _write_artifact(tmp_path, payload=payload)
    artifact = PinnedRuntimeArtifactV4.open_verified(_spec(path, payload))

    artifact.close()
    artifact.close()

    with pytest.raises(OperationalArtifactChangedV4Error, match="not live"):
        artifact.assert_unchanged()
    with pytest.raises(OperationalArtifactChangedV4Error, match="not live"):
        artifact.read_bytes()


def test_source_set_root_is_deterministic_and_commits_to_member_content() -> None:
    first = _source("/etc/chrony/conf.d/10-primary.conf", b"primary")
    second = _source("/etc/chrony/sources.d/20-backup.sources", b"backup")
    artifacts = (first, second)

    root = derive_configured_chrony_source_set_root_v4(artifacts)

    assert root == derive_configured_chrony_source_set_root_v4(artifacts)
    mutated_second = _source(second.path, b"changed backup")
    assert root != derive_configured_chrony_source_set_root_v4((first, mutated_second))


def test_source_set_root_rejects_noncanonical_order() -> None:
    first = _source("/etc/chrony/conf.d/10-primary.conf", b"primary")
    second = _source("/etc/chrony/sources.d/20-backup.sources", b"backup")

    with pytest.raises(CanonicalizationError, match="must be path-sorted"):
        derive_configured_chrony_source_set_root_v4((second, first))


def test_source_set_root_rejects_duplicate_paths() -> None:
    first = _source("/etc/chrony/sources.d/feed.sources", b"first")
    duplicate = _source(first.path, b"second")

    with pytest.raises(CanonicalizationError, match="paths must be unique"):
        derive_configured_chrony_source_set_root_v4((first, duplicate))


def test_source_set_contract_rejects_mutable_container_and_frozen_member_mutation() -> (
    None
):
    source = _source("/etc/chrony/sources.d/feed.sources", b"source")

    with pytest.raises(CanonicalizationError, match="non-empty tuple"):
        derive_configured_chrony_source_set_root_v4([source])  # type: ignore[arg-type]
    with pytest.raises(FrozenInstanceError):
        source.sha256 = _digest(b"mutated")  # type: ignore[misc]
