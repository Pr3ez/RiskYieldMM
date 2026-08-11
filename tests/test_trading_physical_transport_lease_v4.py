from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest

from riskyieldmm.trading.physical_transport_lease_v4 import (
    PHYSICAL_TRANSPORT_WRITER_LEASE_FILE_MODE,
    PHYSICAL_TRANSPORT_WRITER_LEASE_SCHEMA_VERSION,
    PhysicalTransportLeaseV4ConfigurationError,
    PhysicalTransportLeaseV4ConflictError,
    PhysicalTransportLeaseV4StateError,
    PhysicalTransportWriterLeaseV4,
)


def metadata(path: Path) -> tuple[bytes, dict[str, object]]:
    raw = path.read_bytes()
    parsed = json.loads(raw)
    assert isinstance(parsed, dict)
    return raw, parsed


def test_context_manager_writes_canonical_hashed_token_metadata_and_releases(
    tmp_path: Path,
) -> None:
    path = tmp_path / "transport.writer.lease"
    lease = PhysicalTransportWriterLeaseV4(path, holder_id="collector-main")
    assert len(lease.lease_token) == 64
    assert lease.holder_id == "collector-main"
    assert not lease.is_held

    with lease as acquired:
        assert acquired is lease
        assert lease.is_held
        assert lease.assert_held() is None
        held_raw, held = metadata(path)
        assert held == {
            "acquired_at": held["acquired_at"],
            "holder_id": "collector-main",
            "lease_token_sha256": hashlib.sha256(
                bytes.fromhex(lease.lease_token)
            ).hexdigest(),
            "pid": os.getpid(),
            "schema_version": PHYSICAL_TRANSPORT_WRITER_LEASE_SCHEMA_VERSION,
            "state": "HELD",
        }
        assert lease.lease_token.encode() not in held_raw
        assert (
            held_raw
            == json.dumps(
                held,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode()
        )
        acquired_at = datetime.fromisoformat(
            str(held["acquired_at"]).replace("Z", "+00:00")
        )
        assert acquired_at.utcoffset() is not None
        assert stat.S_IMODE(path.stat().st_mode) == (
            PHYSICAL_TRANSPORT_WRITER_LEASE_FILE_MODE
        )

    assert not lease.is_held
    with pytest.raises(PhysicalTransportLeaseV4StateError, match="not held"):
        lease.assert_held()
    released_raw, released = metadata(path)
    assert released["state"] == "RELEASED"
    assert released["acquired_at"] == held["acquired_at"]
    assert released["lease_token_sha256"] == held["lease_token_sha256"]
    assert "released_at" in released
    assert lease.lease_token.encode() not in released_raw

    lease.release()
    assert path.read_bytes() == released_raw
    with pytest.raises(AttributeError):
        lease.lease_token = "0" * 64  # type: ignore[misc]
    with pytest.raises(PhysicalTransportLeaseV4StateError, match="cannot be reused"):
        lease.acquire()


def test_second_independent_open_conflicts_then_succeeds_after_release(
    tmp_path: Path,
) -> None:
    path = tmp_path / "transport.writer.lease"
    first = PhysicalTransportWriterLeaseV4(path, holder_id="first-writer")
    second = PhysicalTransportWriterLeaseV4(path, holder_id="second-writer")

    first.acquire()
    try:
        with pytest.raises(
            PhysicalTransportLeaseV4ConflictError, match="another writer"
        ):
            second.acquire()
        first.assert_held()
    finally:
        first.release()

    with second:
        second.assert_held()
        _, current = metadata(path)
        assert current["holder_id"] == "second-writer"
        assert (
            current["lease_token_sha256"]
            != hashlib.sha256(bytes.fromhex(first.lease_token)).hexdigest()
        )


def test_stale_held_metadata_never_claims_lease_ownership(tmp_path: Path) -> None:
    path = tmp_path / "transport.writer.lease"
    path.write_text(
        '{"holder_id":"dead-process","pid":999999,"state":"HELD"}',
        encoding="utf-8",
    )
    path.chmod(0o600)

    with PhysicalTransportWriterLeaseV4(path, holder_id="live-writer") as lease:
        lease.assert_held()
        _, current = metadata(path)
        assert current["holder_id"] == "live-writer"
        assert current["pid"] == os.getpid()
        assert current["state"] == "HELD"


def test_real_subprocess_cannot_enter_while_parent_holds_lease(
    tmp_path: Path,
) -> None:
    path = tmp_path / "transport.writer.lease"
    child = """
import sys
from riskyieldmm.trading.physical_transport_lease_v4 import (
    PhysicalTransportLeaseV4ConflictError,
    PhysicalTransportWriterLeaseV4,
)

try:
    with PhysicalTransportWriterLeaseV4(sys.argv[1], holder_id="subprocess-writer"):
        pass
except PhysicalTransportLeaseV4ConflictError:
    raise SystemExit(23)
"""
    parent = PhysicalTransportWriterLeaseV4(path, holder_id="parent-writer")
    with parent:
        blocked = subprocess.run(
            [sys.executable, "-c", child, str(path)],
            cwd=Path.cwd(),
            check=False,
            capture_output=True,
            text=True,
        )
        assert blocked.returncode == 23, blocked.stderr
        parent.assert_held()

    admitted = subprocess.run(
        [sys.executable, "-c", child, str(path)],
        cwd=Path.cwd(),
        check=False,
        capture_output=True,
        text=True,
    )
    assert admitted.returncode == 0, admitted.stderr


def test_symlink_lease_path_is_rejected_without_touching_target(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.write_text("sentinel", encoding="utf-8")
    target.chmod(0o600)
    path = tmp_path / "transport.writer.lease"
    path.symlink_to(target)

    lease = PhysicalTransportWriterLeaseV4(path, holder_id="collector-main")
    with pytest.raises(PhysicalTransportLeaseV4ConfigurationError, match="symlink"):
        lease.acquire()
    assert target.read_text(encoding="utf-8") == "sentinel"


@pytest.mark.parametrize("mode", (0o644, 0o660, 0o666))
def test_existing_permissive_lease_mode_is_rejected(
    tmp_path: Path,
    mode: int,
) -> None:
    path = tmp_path / f"transport-{mode:o}.writer.lease"
    path.write_bytes(b"stale metadata is diagnostic only")
    path.chmod(mode)

    lease = PhysicalTransportWriterLeaseV4(path, holder_id="collector-main")
    with pytest.raises(PhysicalTransportLeaseV4ConfigurationError, match="mode 0600"):
        lease.acquire()
    assert stat.S_IMODE(path.stat().st_mode) == mode


def test_non_regular_lease_path_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "transport.writer.lease"
    path.mkdir(mode=0o700)
    lease = PhysicalTransportWriterLeaseV4(path, holder_id="collector-main")

    with pytest.raises(
        PhysicalTransportLeaseV4ConfigurationError, match="regular file"
    ):
        lease.acquire()


def test_multiply_linked_lease_file_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "transport.writer.lease"
    alias = tmp_path / "transport.writer.alias"
    path.write_bytes(b"diagnostic metadata")
    path.chmod(0o600)
    alias.hardlink_to(path)

    lease = PhysicalTransportWriterLeaseV4(path, holder_id="collector-main")
    with pytest.raises(
        PhysicalTransportLeaseV4ConfigurationError, match="one hard link"
    ):
        lease.acquire()


def test_unprotected_group_writable_parent_is_rejected(tmp_path: Path) -> None:
    parent = tmp_path / "shared-runtime"
    parent.mkdir(mode=0o770)
    parent.chmod(0o770)
    path = parent / "transport.writer.lease"

    lease = PhysicalTransportWriterLeaseV4(path, holder_id="collector-main")
    with pytest.raises(
        PhysicalTransportLeaseV4ConfigurationError,
        match="exact mode 0700",
    ):
        lease.acquire()
    assert not path.exists()


def test_path_replacement_is_detected_without_mutating_replacement(
    tmp_path: Path,
) -> None:
    path = tmp_path / "transport.writer.lease"
    moved = tmp_path / "transport.writer.moved"
    lease = PhysicalTransportWriterLeaseV4(path, holder_id="collector-main")
    lease.acquire()
    path.rename(moved)
    replacement = b"replacement-sentinel"
    path.write_bytes(replacement)
    path.chmod(0o600)

    with pytest.raises(PhysicalTransportLeaseV4StateError, match="no longer safe"):
        lease.assert_held()
    with pytest.raises(
        PhysicalTransportLeaseV4StateError,
        match="without a durable safe release record",
    ):
        lease.release()

    assert path.read_bytes() == replacement
    assert not lease.is_held


def test_symlinked_ancestor_directory_is_rejected(tmp_path: Path) -> None:
    real_root = tmp_path / "real-root"
    real_root.mkdir(mode=0o700)
    private_parent = real_root / "private-runtime"
    private_parent.mkdir(mode=0o700)
    alias = tmp_path / "alias-root"
    alias.symlink_to(real_root, target_is_directory=True)

    lease = PhysicalTransportWriterLeaseV4(
        alias / "private-runtime" / "transport.writer.lease",
        holder_id="collector-main",
    )
    with pytest.raises(
        PhysicalTransportLeaseV4ConfigurationError,
        match="symlink components",
    ):
        lease.acquire()


@pytest.mark.parametrize("holder_id", ("", " leading", "trailing ", "line\nbreak"))
def test_holder_id_must_be_canonical(tmp_path: Path, holder_id: str) -> None:
    with pytest.raises(PhysicalTransportLeaseV4ConfigurationError, match="canonical"):
        PhysicalTransportWriterLeaseV4(
            tmp_path / "transport.writer.lease",
            holder_id=holder_id,
        )
