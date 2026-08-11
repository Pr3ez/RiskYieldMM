from __future__ import annotations

import errno
import fcntl
import hashlib
import inspect
import os
import socket
import stat
import subprocess
import sys
import tempfile
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import riskyieldmm.trading.chronyd_provenance_v48b as provenance_v48b
import riskyieldmm.trading.physical_transport_linux_v4 as linux_transport_v4
from riskyieldmm.trading.canonical import sha256_digest
from riskyieldmm.trading.chronyd_provenance_v48b import (
    BoundedChronydCommandResultV48B,
    ChronydConfigurationV48BError,
    ChronydLaunchAuthorityV48B,
    ChronydProcessV48BError,
    ChronydProtocolV48BError,
    ChronydProvenanceV48BError,
    ChronydSourcesNotReadyV48BError,
    ChronyReadOnlyQueryStateV48B,
    PreparedChronydLaunchV48B,
    SealedChronydConfigurationV48B,
    assemble_effective_chronyd_configuration_v48b,
    chronyd_fixed_environment_v48b,
    current_systemd_invocation_id_v48b,
    receive_authenticated_datagram_v48b,
)
from riskyieldmm.trading.operational_artifact_loading_v4 import (
    ConfiguredChronySourceArtifactV4,
    OperationalArtifactV4Error,
    PinnedRuntimeArtifactV4,
    RuntimeArtifactSpecV4,
    derive_configured_chrony_source_set_root_v4,
)
from riskyieldmm.trading.operational_manifests_v4 import (
    CLOCK_SOURCE_KIND,
    MONOTONIC_DOMAIN_PROFILE,
    ClockSourcePolicyManifestV4,
)
from tests._chronyd_launch_policy_v48b import (
    make_test_chronyd_launch_policy_v48b,
)


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _minimal_base(real_command_socket_path: str) -> bytes:
    return (
        f"bindcmdaddress {real_command_socket_path}\n"
        "cmdport 0\n"
        "driftfile /\n"
        "minsources 1\n"
        "pidfile /\n"
        "port 0\n"
        "rtcsync\n"
        "makestep 1.0 3\n"
    ).encode("ascii")


def _effective_bytes(base: bytes, fragments: tuple[bytes, ...]) -> bytes:
    chunks = [
        b"# riskyieldmm-v48b-static-config\n",
        f"# base-sha256 {_digest(base)}\n".encode("ascii"),
        base,
    ]
    for index, raw in enumerate(fragments):
        chunks.extend(
            (
                f"# fragment-{index}-sha256 {_digest(raw)}\n".encode("ascii"),
                raw,
            )
        )
    return b"".join(chunks)


def _launch_policy(
    *,
    runtime_dir: str,
    effective_sha256: str,
    printed_sha256: str = "9" * 64,
    **changes: Any,
):
    base = make_test_chronyd_launch_policy_v48b(
        read_only_api_socket_path=f"{runtime_dir}/supervisor/readonly.sock"
    )
    return replace(
        base,
        effective_config_sha256=effective_sha256,
        printed_config_sha256=printed_sha256,
        **changes,
    )


def _assemble_fixture(
    *,
    runtime_dir: str = "/run/riskyieldmm-chronyd",
    base_override: bytes | None = None,
    fragments: tuple[tuple[str, bytes], ...] | None = None,
):
    provisional = make_test_chronyd_launch_policy_v48b(
        read_only_api_socket_path=f"{runtime_dir}/supervisor/readonly.sock"
    )
    base = base_override or _minimal_base(provisional.real_command_socket_path)
    source_fragments = fragments or (
        ("/etc/chrony/sources.d/10-a.sources", b"server 192.0.2.1 iburst\n"),
    )
    ordered_raw = tuple(raw for _, raw in sorted(source_fragments))
    expected_raw = _effective_bytes(base, ordered_raw)
    launch = _launch_policy(
        runtime_dir=runtime_dir,
        effective_sha256=_digest(expected_raw),
    )
    effective = assemble_effective_chronyd_configuration_v48b(
        base_path="/etc/chrony/chrony.conf",
        base_bytes=base,
        source_fragments=source_fragments,
        launch_policy=launch,
        minimum_selectable_sources=1,
    )
    return launch, effective


def _request(command: int, size: int, *, sequence: bytes, index: int | None = None):
    raw = bytearray(size)
    raw[0] = 6
    raw[1] = 1
    raw[4:6] = command.to_bytes(2, "big")
    raw[8:12] = sequence
    if index is not None:
        raw[20:24] = index.to_bytes(4, "big")
    return bytes(raw)


def _reply(
    command: int,
    reply: int,
    size: int,
    *,
    sequence: bytes,
    source_count: int | None = None,
):
    raw = bytearray(size)
    raw[0] = 6
    raw[1] = 2
    raw[4:6] = command.to_bytes(2, "big")
    raw[6:8] = reply.to_bytes(2, "big")
    raw[16:20] = sequence
    if source_count is not None:
        raw[28:32] = source_count.to_bytes(4, "big")
    return bytes(raw)


def _complete_state(*, source_count: int = 1) -> ChronyReadOnlyQueryStateV48B:
    state = ChronyReadOnlyQueryStateV48B(expected_source_count=source_count)
    state.accept_exchange(
        _request(33, 104, sequence=b"TRAK"),
        _reply(33, 5, 104, sequence=b"TRAK"),
    )
    state.accept_exchange(
        _request(14, 32, sequence=b"NUMS"),
        _reply(14, 2, 32, sequence=b"NUMS", source_count=source_count),
    )
    for index in range(source_count):
        sequence = index.to_bytes(4, "big")
        state.accept_exchange(
            _request(15, 76, sequence=sequence, index=index),
            _reply(15, 3, 76, sequence=sequence),
        )
    return state


def test_static_configuration_is_deterministic_and_endpoint_closed() -> None:
    launch, effective = _assemble_fixture(
        fragments=(
            ("/etc/chrony/sources.d/20-b.sources", b"peer 2001:db8::2\n"),
            ("/etc/chrony/sources.d/10-a.sources", b"server 192.0.2.1 iburst\n"),
        )
    )

    assert effective.sha256 == launch.effective_config_sha256
    assert effective.configured_endpoints == ("192.0.2.1", "2001:db8::2")
    assert effective.configured_source_count == 2
    assert effective.raw_bytes.index(b"192.0.2.1") < effective.raw_bytes.index(
        b"2001:db8::2"
    )


@pytest.mark.parametrize(
    "bad_line",
    (
        b"include /etc/chrony/*.conf\n",
        b"confdir /etc/chrony/conf.d\n",
        b"sourcedir /run/chrony-dhcp\n",
        b"pool pool.ntp.org\n",
        b"server time.example iburst\n",
        b"refclock SHM 0\n",
        b"local stratum 10\n",
        b"server 192.0.2.1 nts\n",
    ),
)
def test_static_configuration_rejects_dynamic_or_unsealed_inputs(
    bad_line: bytes,
) -> None:
    provisional = make_test_chronyd_launch_policy_v48b(
        read_only_api_socket_path="/run/riskyieldmm-chronyd/readonly.sock"
    )
    base = _minimal_base(provisional.real_command_socket_path)
    expected = _effective_bytes(base, (bad_line,))
    launch = _launch_policy(
        runtime_dir="/run/riskyieldmm-chronyd",
        effective_sha256=_digest(expected),
    )

    with pytest.raises(ChronydConfigurationV48BError):
        assemble_effective_chronyd_configuration_v48b(
            base_path="/etc/chrony/chrony.conf",
            base_bytes=base,
            source_fragments=(("/etc/chrony/sources.d/bad.sources", bad_line),),
            launch_policy=launch,
            minimum_selectable_sources=1,
        )


def test_static_configuration_rejects_duplicate_endpoint_and_digest_substitution() -> (
    None
):
    _, effective = _assemble_fixture()
    wrong_launch = _launch_policy(
        runtime_dir="/run/riskyieldmm-chronyd",
        effective_sha256="a" * 64,
    )
    with pytest.raises(
        ChronydConfigurationV48BError,
        match="differs from signed effective digest",
    ):
        assemble_effective_chronyd_configuration_v48b(
            base_path="/etc/chrony/chrony.conf",
            base_bytes=_minimal_base(wrong_launch.real_command_socket_path),
            source_fragments=(("/a.sources", b"server 192.0.2.1\n"),),
            launch_policy=wrong_launch,
            minimum_selectable_sources=1,
        )
    duplicate_raw = b"server 192.0.2.1\nserver 192.0.2.1\n"
    expected = _effective_bytes(
        _minimal_base(wrong_launch.real_command_socket_path), (duplicate_raw,)
    )
    duplicate_launch = replace(wrong_launch, effective_config_sha256=_digest(expected))
    with pytest.raises(ChronydConfigurationV48BError, match="duplicated"):
        assemble_effective_chronyd_configuration_v48b(
            base_path="/etc/chrony/chrony.conf",
            base_bytes=_minimal_base(duplicate_launch.real_command_socket_path),
            source_fragments=(("/a.sources", duplicate_raw),),
            launch_policy=duplicate_launch,
            minimum_selectable_sources=1,
        )
    assert effective.configured_source_count == 1


def test_effective_configuration_memfd_is_fully_write_sealed() -> None:
    _, effective = _assemble_fixture()
    sealed = SealedChronydConfigurationV48B.create(effective)
    try:
        assert sealed.seals == 0xF
        sealed.assert_sealed()
        with pytest.raises(OSError) as exc_info:
            os.pwrite(sealed.descriptor, b"X", 0)
        assert exc_info.value.errno in {errno.EPERM, errno.EBUSY}
        with pytest.raises(OSError):
            fcntl.fcntl(sealed.descriptor, 1033, 0x10)
    finally:
        sealed.close()


def test_exact_read_only_protocol_accepts_n_plus_two_exchanges() -> None:
    state = _complete_state(source_count=3)
    transcript = state.finish()

    assert state.complete
    assert transcript.source_count == 3
    assert [item.command for item in transcript.exchanges] == [33, 14, 15, 15, 15]
    assert len(transcript.transcript_sha256) == 64


@pytest.mark.parametrize("count", (1, 64))
def test_exact_read_only_protocol_accepts_signed_count_boundaries(count: int) -> None:
    transcript = _complete_state(source_count=count).finish()
    assert len(transcript.exchanges) == count + 2


@pytest.mark.parametrize("count", (0, 65, (1 << 32) - 1))
def test_exact_read_only_protocol_rejects_untrusted_source_counts(count: int) -> None:
    state = ChronyReadOnlyQueryStateV48B(expected_source_count=1)
    state.accept_exchange(
        _request(33, 104, sequence=b"TRAK"),
        _reply(33, 5, 104, sequence=b"TRAK"),
    )
    with pytest.raises(ChronydProtocolV48BError, match="source count"):
        state.accept_exchange(
            _request(14, 32, sequence=b"NUMS"),
            _reply(14, 2, 32, sequence=b"NUMS", source_count=count),
        )


def test_extra_runtime_source_is_fatal_not_transient_readiness() -> None:
    state = ChronyReadOnlyQueryStateV48B(expected_source_count=1)
    state.accept_exchange(
        _request(33, 104, sequence=b"TRAK"),
        _reply(33, 5, 104, sequence=b"TRAK"),
    )
    with pytest.raises(ChronydProtocolV48BError, match="more sources") as exc_info:
        state.accept_exchange(
            _request(14, 32, sequence=b"NUMS"),
            _reply(14, 2, 32, sequence=b"NUMS", source_count=2),
        )
    assert type(exc_info.value) is ChronydProtocolV48BError

    state = ChronyReadOnlyQueryStateV48B(expected_source_count=2)
    state.accept_exchange(
        _request(33, 104, sequence=b"TRAK"),
        _reply(33, 5, 104, sequence=b"TRAK"),
    )
    with pytest.raises(ChronydSourcesNotReadyV48BError):
        state.accept_exchange(
            _request(14, 32, sequence=b"NUMS"),
            _reply(14, 2, 32, sequence=b"NUMS", source_count=1),
        )


@pytest.mark.parametrize(
    "mutate",
    (
        lambda raw: bytes([5]) + raw[1:],
        lambda raw: raw[:2] + b"\x01" + raw[3:],
        lambda raw: raw[:6] + b"\x00\x01" + raw[8:],
        lambda raw: raw[:12] + b"\x01" + raw[13:],
        lambda raw: raw + b"\x00",
    ),
)
def test_exact_read_only_protocol_rejects_version_reserved_retry_padding_and_length(
    mutate,
) -> None:
    state = ChronyReadOnlyQueryStateV48B(expected_source_count=1)
    request = _request(33, 104, sequence=b"TRAK")
    with pytest.raises(ChronydProtocolV48BError):
        state.accept_exchange(mutate(request), _reply(33, 5, 104, sequence=b"TRAK"))


def test_exact_read_only_protocol_rejects_reply_substitution_and_wrong_index() -> None:
    state = ChronyReadOnlyQueryStateV48B(expected_source_count=1)
    with pytest.raises(ChronydProtocolV48BError, match="reply header"):
        state.accept_exchange(
            _request(33, 104, sequence=b"TRAK"),
            _reply(33, 5, 104, sequence=b"FAKE"),
        )

    state = ChronyReadOnlyQueryStateV48B(expected_source_count=1)
    state.accept_exchange(
        _request(33, 104, sequence=b"TRAK"),
        _reply(33, 5, 104, sequence=b"TRAK"),
    )
    state.accept_exchange(
        _request(14, 32, sequence=b"NUMS"),
        _reply(14, 2, 32, sequence=b"NUMS", source_count=1),
    )
    with pytest.raises(ChronydProtocolV48BError, match="index"):
        state.accept_exchange(
            _request(15, 76, sequence=b"DATA", index=1),
            _reply(15, 3, 76, sequence=b"DATA"),
        )


def test_protocol_forbids_any_exchange_after_exact_completion() -> None:
    state = _complete_state()
    with pytest.raises(ChronydProtocolV48BError, match="after completion"):
        state.accept_exchange(
            _request(15, 76, sequence=b"MORE", index=1),
            _reply(15, 3, 76, sequence=b"MORE"),
        )


def test_kernel_datagram_credentials_are_required_per_message() -> None:
    receiver, sender = socket.socketpair(socket.AF_UNIX, socket.SOCK_DGRAM)
    try:
        receiver.setsockopt(socket.SOL_SOCKET, socket.SO_PASSCRED, 1)
        sender.send(b"READY=1")
        raw, _ = receive_authenticated_datagram_v48b(
            receiver,
            maximum_bytes=64,
            expected_pid=os.getpid(),
            expected_uid=os.geteuid(),
            expected_gid=os.getegid(),
        )
        assert raw == b"READY=1"

        sender.send(b"READY=1")
        with pytest.raises(ChronydProtocolV48BError, match="credentials differ"):
            receive_authenticated_datagram_v48b(
                receiver,
                maximum_bytes=64,
                expected_pid=os.getpid() + 1,
                expected_uid=os.geteuid(),
                expected_gid=os.getegid(),
            )
    finally:
        receiver.close()
        sender.close()


def test_runtime_directory_revalidation_checks_path_identity_owner_and_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy = make_test_chronyd_launch_policy_v48b(
        read_only_api_socket_path=("/run/riskyieldmm-chronyd/supervisor/readonly.sock")
    )
    requirements = (
        (policy.runtime_directory_path, 0, 0, 0o711),
        (
            policy.chronyd_socket_directory_path,
            0,
            0,
            0o700,
        ),
        (
            policy.supervisor_socket_directory_path,
            0,
            policy.post_drop_gid,
            0o710,
        ),
    )
    descriptors = (40, 41, 42)
    identities = ((7, 100), (7, 101), (7, 102))
    by_descriptor = {
        descriptor: SimpleNamespace(
            st_dev=identity[0],
            st_ino=identity[1],
            st_uid=uid,
            st_gid=gid,
            st_mode=stat.S_IFDIR | mode,
        )
        for descriptor, identity, (_, uid, gid, mode) in zip(
            descriptors, identities, requirements, strict=True
        )
    }
    by_path = {
        path: by_descriptor[descriptor]
        for descriptor, (path, _, _, _) in zip(descriptors, requirements, strict=True)
    }
    monkeypatch.setattr(provenance_v48b.os.path, "realpath", lambda path: path)
    monkeypatch.setattr(provenance_v48b.os, "get_inheritable", lambda descriptor: False)
    monkeypatch.setattr(
        provenance_v48b.os, "fstat", lambda descriptor: by_descriptor[descriptor]
    )
    monkeypatch.setattr(provenance_v48b.os, "lstat", lambda path: by_path[path])

    provenance_v48b._assert_runtime_directories_current(
        policy=policy,
        descriptors=descriptors,
        identities=identities,
    )

    supervisor = by_descriptor[42]
    by_descriptor[42] = SimpleNamespace(
        **{
            **supervisor.__dict__,
            "st_mode": stat.S_IFDIR | 0o770,
        }
    )
    with pytest.raises(ChronydProcessV48BError, match="owner, mode, or identity"):
        provenance_v48b._assert_runtime_directories_current(
            policy=policy,
            descriptors=descriptors,
            identities=identities,
        )


def test_runtime_directory_revalidation_rejects_missing_retained_handle() -> None:
    policy = make_test_chronyd_launch_policy_v48b(
        read_only_api_socket_path=("/run/riskyieldmm-chronyd/supervisor/readonly.sock")
    )
    with pytest.raises(ChronydProcessV48BError, match="invalid cardinality"):
        provenance_v48b._assert_runtime_directories_current(
            policy=policy,
            descriptors=(40, 41),
            identities=((7, 100), (7, 101)),
        )


def test_command_socket_transition_freezes_directory_before_root_sealing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy = make_test_chronyd_launch_policy_v48b(
        read_only_api_socket_path=("/run/riskyieldmm-chronyd/supervisor/readonly.sock")
    )
    initial = provenance_v48b._ChronydCommandSocketSnapshotV48B(
        device=7,
        inode=101,
        uid=policy.post_drop_uid,
        gid=policy.post_drop_gid,
        mode=0o660,
    )
    sealed = provenance_v48b._ChronydCommandSocketSnapshotV48B(
        device=7,
        inode=101,
        uid=0,
        gid=0,
        mode=0o600,
    )
    snapshots = iter((initial, initial, sealed))
    operations: list[tuple[Any, ...]] = []
    monkeypatch.setattr(
        provenance_v48b,
        "_snapshot_command_socket",
        lambda *_args, **_kwargs: next(snapshots),
    )
    monkeypatch.setattr(
        provenance_v48b.os,
        "fchmod",
        lambda fd, mode: operations.append(("fchmod", fd, mode)),
    )
    monkeypatch.setattr(
        provenance_v48b.os,
        "fchown",
        lambda fd, uid, gid: operations.append(("fchown", fd, uid, gid)),
    )
    monkeypatch.setattr(
        provenance_v48b.os,
        "chown",
        lambda path, uid, gid, **kwargs: operations.append(
            ("chown", path, uid, gid, kwargs)
        ),
    )
    monkeypatch.setattr(
        provenance_v48b.os,
        "chmod",
        lambda path, mode, **kwargs: operations.append(("chmod", path, mode, kwargs)),
    )

    result = provenance_v48b._seal_command_socket_authority(
        policy=policy,
        chronyd_directory_fd=51,
    )
    assert result == sealed
    assert operations[:3] == [
        ("fchmod", 51, 0o500),
        ("fchown", 51, 0, 0),
        ("fchmod", 51, 0o700),
    ]
    assert operations[3][0] == "chown"
    assert operations[4][0] == "chmod"


def test_command_socket_transition_rejects_replacement_before_path_chown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy = make_test_chronyd_launch_policy_v48b(
        read_only_api_socket_path=("/run/riskyieldmm-chronyd/supervisor/readonly.sock")
    )
    initial = provenance_v48b._ChronydCommandSocketSnapshotV48B(
        device=7,
        inode=101,
        uid=policy.post_drop_uid,
        gid=policy.post_drop_gid,
        mode=0o660,
    )
    replacement = replace(initial, inode=102)
    snapshots = iter((initial, replacement))
    path_chown_called = False

    def path_chown(*_args, **_kwargs) -> None:
        nonlocal path_chown_called
        path_chown_called = True

    monkeypatch.setattr(
        provenance_v48b,
        "_snapshot_command_socket",
        lambda *_args, **_kwargs: next(snapshots),
    )
    monkeypatch.setattr(provenance_v48b.os, "fchmod", lambda *_args: None)
    monkeypatch.setattr(provenance_v48b.os, "fchown", lambda *_args: None)
    monkeypatch.setattr(provenance_v48b.os, "chown", path_chown)
    with pytest.raises(ChronydProcessV48BError, match="directory was frozen"):
        provenance_v48b._seal_command_socket_authority(
            policy=policy,
            chronyd_directory_fd=51,
        )
    assert not path_chown_called


@pytest.mark.parametrize(
    "mutation",
    (
        lambda raw: raw.replace(b"Groups:\t\n", b"Groups:\t61049\n"),
        lambda raw: raw.replace(
            b"CapEff:\t0000000002000400", b"CapEff:\t0000000002000401"
        ),
        lambda raw: raw.replace(b"NoNewPrivs:\t1", b"NoNewPrivs:\t0"),
        lambda raw: raw.replace(b"Seccomp:\t2", b"Seccomp:\t0"),
    ),
)
def test_process_security_posture_rejects_privilege_expansion(
    monkeypatch: pytest.MonkeyPatch,
    mutation,
) -> None:
    status = (
        b"Uid:\t61048\t61048\t61048\t61048\n"
        b"Gid:\t61048\t61048\t61048\t61048\n"
        b"Groups:\t\n"
        b"Umask:\t0022\n"
        b"CapInh:\t0000000000000000\n"
        b"CapPrm:\t0000000002000400\n"
        b"CapEff:\t0000000002000400\n"
        b"CapBnd:\t0000000002000400\n"
        b"CapAmb:\t0000000000000000\n"
        b"NoNewPrivs:\t1\n"
        b"Seccomp:\t2\n"
        b"Seccomp_filters:\t1\n"
        b"CoreDumping:\t0\n"
    )
    monkeypatch.setattr(
        provenance_v48b,
        "_read_bounded_proc_file",
        lambda *_args, **_kwargs: mutation(status),
    )
    with pytest.raises(ChronydProcessV48BError, match="privilege or sandbox"):
        provenance_v48b._read_process_ids(123)


def test_process_security_posture_accepts_exact_reviewed_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    status = (
        b"Uid:\t61048\t61048\t61048\t61048\n"
        b"Gid:\t61048\t61048\t61048\t61048\n"
        b"Groups:\t\n"
        b"Umask:\t0022\n"
        b"CapInh:\t0000000000000000\n"
        b"CapPrm:\t0000000002000400\n"
        b"CapEff:\t0000000002000400\n"
        b"CapBnd:\t0000000002000400\n"
        b"CapAmb:\t0000000000000000\n"
        b"NoNewPrivs:\t1\n"
        b"Seccomp:\t2\n"
        b"Seccomp_filters:\t1\n"
        b"CoreDumping:\t0\n"
    )
    monkeypatch.setattr(
        provenance_v48b,
        "_read_bounded_proc_file",
        lambda *_args, **_kwargs: status,
    )
    uid, gid, security = provenance_v48b._read_process_ids(123)
    assert (uid, gid) == (61048, 61048)
    assert security.cap_effective == 0x0000000002000400


def test_authority_rejects_self_pinned_but_unsigned_chronyc(tmp_path: Path) -> None:
    executable = tmp_path / "wrong-chronyc"
    raw = b"wrong but self-consistent chronyc\n"
    _write(executable, raw, executable=True)
    artifact = PinnedRuntimeArtifactV4.open_verified(
        RuntimeArtifactSpecV4(
            path=str(executable),
            sha256=_digest(raw),
            require_executable=True,
        )
    )
    authority = object.__new__(ChronydLaunchAuthorityV48B)
    authority._policy = SimpleNamespace(  # noqa: SLF001
        chronyc_executable_path="/signed/chronyc",
        chronyc_executable_sha256="a" * 64,
    )
    try:
        with pytest.raises(ChronydProtocolV48BError, match="signed clock policy"):
            authority._assert_signed_chronyc(artifact)  # noqa: SLF001
    finally:
        artifact.close()


def test_query_process_output_is_capped_while_it_is_streamed() -> None:
    proc = subprocess.Popen(
        (
            sys.executable,
            "-c",
            "import os; os.write(1, b'x' * 4096)",
        ),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        close_fds=True,
        shell=False,
        start_new_session=True,
    )
    try:
        with pytest.raises(ChronydProtocolV48BError, match="signed byte cap"):
            provenance_v48b._collect_bounded_process_output_v48b(
                proc,
                deadline_ns=provenance_v48b._boottime_ns_v48b() + 2_000_000_000,
                maximum_output_bytes=64,
            )
    finally:
        if proc.poll() is None:
            provenance_v48b._terminate_owned_process(proc)


def test_query_datagram_send_obeys_shared_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _BlockedSocket:
        def send(self, _payload: bytes) -> int:
            raise BlockingIOError

    monkeypatch.setattr(
        provenance_v48b.select,
        "select",
        lambda *_args, **_kwargs: ([], [], []),
    )
    with pytest.raises(ChronydProtocolV48BError, match="global deadline"):
        provenance_v48b._send_datagram_v48b(
            _BlockedSocket(),  # type: ignore[arg-type]
            b"request",
            deadline_ns=provenance_v48b._boottime_ns_v48b() + 1_000_000,
            stop=provenance_v48b.threading.Event(),
        )


def test_owned_daemon_teardown_signals_only_through_pidfd(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    signals: list[tuple[int, int]] = []

    class _Process:
        waits = 0

        def poll(self):
            return None

        def wait(self, *, timeout):
            self.waits += 1
            if self.waits == 1:
                raise subprocess.TimeoutExpired("chronyd", timeout)
            return 0

        def send_signal(self, _signal):
            raise AssertionError("PID-number signalling is forbidden")

        def kill(self):
            raise AssertionError("PID-number signalling is forbidden")

    monkeypatch.setattr(
        provenance_v48b,
        "_pidfd_send_signal",
        lambda pidfd, signal_number: signals.append((pidfd, signal_number)),
    )
    provenance_v48b._terminate_owned_process(_Process(), pidfd=77)  # type: ignore[arg-type]
    assert signals == [
        (77, provenance_v48b.signal.SIGTERM),
        (77, provenance_v48b.signal.SIGKILL),
    ]


def test_chronyd_environment_is_exact_and_notify_path_is_filesystem_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert chronyd_fixed_environment_v48b(
        notify_socket_path="/run/riskyieldmm-chronyd/notify.sock"
    ) == {
        "LANG": "C",
        "LC_ALL": "C",
        "NOTIFY_SOCKET": "/run/riskyieldmm-chronyd/notify.sock",
        "PATH": "/usr/bin:/bin",
        "TZ": "UTC",
    }
    monkeypatch.delenv("INVOCATION_ID", raising=False)
    with pytest.raises(ChronydProcessV48BError):
        current_systemd_invocation_id_v48b()
    with pytest.raises(ChronydProvenanceV48BError):
        chronyd_fixed_environment_v48b(notify_socket_path="@abstract")


class _PreparedRunner:
    def __init__(self, *, printed: bytes) -> None:
        self.printed = printed
        self.calls: list[tuple[str, ...]] = []
        self.options: list[dict[str, Any]] = []

    def __call__(self, argv: tuple[str, ...], **options: Any):
        self.calls.append(argv)
        self.options.append(options)
        if argv[-1] == "-v":
            return BoundedChronydCommandResultV48B(
                returncode=0,
                stdout=b"chronyd (chrony) version 4.8 (+NTS +IPV6)\n",
                stderr=b"",
            )
        return BoundedChronydCommandResultV48B(
            returncode=0, stdout=self.printed, stderr=b""
        )


def _write(path: Path, raw: bytes, *, executable: bool = False) -> None:
    path.write_bytes(raw)
    path.chmod(0o700 if executable else 0o600)


def test_prepared_launch_pins_every_input_and_interpreted_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_dir = "/run/riskyieldmm-test-chronyd"
    provisional = make_test_chronyd_launch_policy_v48b(
        read_only_api_socket_path=f"{runtime_dir}/supervisor/readonly.sock"
    )
    unit = tmp_path / "riskyieldmm-chronyd.service"
    chronyd = tmp_path / "chronyd"
    config = tmp_path / "chrony.conf"
    source = tmp_path / "source.sources"
    unit_raw = b"[Service]\nType=notify\nNotifyAccess=main\n"
    chronyd_raw = b"reviewed chronyd executable\n"
    config_raw = _minimal_base(provisional.real_command_socket_path)
    source_raw = b"server 192.0.2.1 iburst\n"
    _write(unit, unit_raw)
    _write(chronyd, chronyd_raw, executable=True)
    _write(config, config_raw)
    _write(source, source_raw)
    expected_effective = _effective_bytes(config_raw, (source_raw,))
    printed = b"reviewed chronyd printed configuration\n"
    launch = _launch_policy(
        runtime_dir=runtime_dir,
        effective_sha256=_digest(expected_effective),
        printed_sha256=_digest(printed),
        systemd_unit_name=unit.name,
        systemd_unit_path=str(unit),
        systemd_unit_sha256=_digest(unit_raw),
        chronyd_executable_path=str(chronyd),
        chronyd_executable_sha256=_digest(chronyd_raw),
    )
    source_artifact = ConfiguredChronySourceArtifactV4(
        path=str(source), sha256=_digest(source_raw)
    )
    policy = ClockSourcePolicyManifestV4(
        source_kind=CLOCK_SOURCE_KIND,
        chrony_version="4.8",
        chronyc_executable_path="/usr/bin/chronyc",
        chronyc_executable_sha256=sha256_digest({"fixture": "chronyc"}),
        chrony_config_path=str(config),
        chrony_config_sha256=_digest(config_raw),
        chronyc_command_socket_path=launch.read_only_api_socket_path,
        chronyc_command_timeout_milliseconds=1_000,
        chronyc_max_output_bytes=65_536,
        configured_source_set_root_sha256=(
            derive_configured_chrony_source_set_root_v4((source_artifact,))
        ),
        min_selectable_sources=1,
        max_uncertainty_milliseconds=100,
        max_sample_age_milliseconds=5_000,
        require_synchronized=True,
        require_normal_leap=True,
        monotonic_domain_profile=MONOTONIC_DOMAIN_PROFILE,
        chronyd_launch_policy=launch,
    )
    runner = _PreparedRunner(printed=printed)
    monkeypatch.setattr(linux_transport_v4, "run_bounded_command_v4", runner)
    prepared = PreparedChronydLaunchV48B.prepare(
        policy=policy,
        configured_source_artifacts=(source_artifact,),
    )
    try:
        assert prepared.is_live_profile
        assert prepared.configured_endpoints == ("192.0.2.1",)
        assert [call[-1] for call in runner.calls] == [
            "-v",
            prepared.sealed_config_proc_fd_path,
        ]
        assert [item["maximum_output_bytes"] for item in runner.options] == [
            4_096,
            1_048_576,
        ]
        assert [item["timeout_milliseconds"] for item in runner.options] == [
            10_000,
            10_000,
        ]
        prepared.assert_unchanged()
        source.write_bytes(b"server 192.0.2.2\n")
        with pytest.raises(ChronydProvenanceV48BError):
            prepared.assert_unchanged()
    finally:
        prepared.close()


def test_prepared_launch_closes_all_handles_when_printed_digest_differs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The detailed successful fixture above establishes every admitted handle.
    # This case proves the last pre-launch interpretation gate still fails closed.
    runtime_dir = "/run/riskyieldmm-test-chronyd"
    provisional = make_test_chronyd_launch_policy_v48b(
        read_only_api_socket_path=f"{runtime_dir}/supervisor/readonly.sock"
    )
    unit = tmp_path / "riskyieldmm-chronyd.service"
    chronyd = tmp_path / "chronyd"
    config = tmp_path / "chrony.conf"
    source = tmp_path / "source.sources"
    for path, raw, executable in (
        (unit, b"[Service]\nType=notify\n", False),
        (chronyd, b"chronyd\n", True),
        (config, _minimal_base(provisional.real_command_socket_path), False),
        (source, b"server 192.0.2.1\n", False),
    ):
        _write(path, raw, executable=executable)
    effective = _effective_bytes(config.read_bytes(), (source.read_bytes(),))
    launch = _launch_policy(
        runtime_dir=runtime_dir,
        effective_sha256=_digest(effective),
        printed_sha256="f" * 64,
        systemd_unit_name=unit.name,
        systemd_unit_path=str(unit),
        systemd_unit_sha256=_digest(unit.read_bytes()),
        chronyd_executable_path=str(chronyd),
        chronyd_executable_sha256=_digest(chronyd.read_bytes()),
    )
    source_artifact = ConfiguredChronySourceArtifactV4(
        path=str(source), sha256=_digest(source.read_bytes())
    )
    policy = ClockSourcePolicyManifestV4(
        source_kind=CLOCK_SOURCE_KIND,
        chrony_version="4.8",
        chronyc_executable_path="/usr/bin/chronyc",
        chronyc_executable_sha256="a" * 64,
        chrony_config_path=str(config),
        chrony_config_sha256=_digest(config.read_bytes()),
        chronyc_command_socket_path=launch.read_only_api_socket_path,
        chronyc_command_timeout_milliseconds=1_000,
        chronyc_max_output_bytes=65_536,
        configured_source_set_root_sha256=(
            derive_configured_chrony_source_set_root_v4((source_artifact,))
        ),
        min_selectable_sources=1,
        max_uncertainty_milliseconds=100,
        max_sample_age_milliseconds=5_000,
        require_synchronized=True,
        require_normal_leap=True,
        monotonic_domain_profile=MONOTONIC_DOMAIN_PROFILE,
        chronyd_launch_policy=launch,
    )
    before = len(os.listdir("/proc/self/fd"))
    with pytest.raises(ChronydConfigurationV48BError, match="interpreted"):
        PreparedChronydLaunchV48B._prepare_for_test(
            policy=policy,
            configured_source_artifacts=(source_artifact,),
            command_runner=_PreparedRunner(printed=b"unexpected\n"),
        )
    after = len(os.listdir("/proc/self/fd"))
    assert after == before

    printed = b"reviewed printed config\n"
    good_launch = replace(launch, printed_config_sha256=_digest(printed))
    good_policy = replace(policy, chronyd_launch_policy=good_launch)

    def fail_post_construction(_self: PreparedChronydLaunchV48B) -> None:
        raise ChronydProvenanceV48BError("injected final validation failure")

    monkeypatch.setattr(
        PreparedChronydLaunchV48B,
        "assert_unchanged",
        fail_post_construction,
    )
    before = len(os.listdir("/proc/self/fd"))
    with pytest.raises(ChronydProvenanceV48BError, match="final validation"):
        PreparedChronydLaunchV48B._prepare_for_test(
            policy=good_policy,
            configured_source_artifacts=(source_artifact,),
            command_runner=_PreparedRunner(printed=printed),
        )
    after = len(os.listdir("/proc/self/fd"))
    assert after == before


def test_production_prepare_exposes_no_injected_runner_and_test_closure_cannot_launch(
    tmp_path: Path,
) -> None:
    assert (
        "command_runner"
        not in inspect.signature(PreparedChronydLaunchV48B.prepare).parameters
    )

    runtime_dir = "/run/riskyieldmm-test-chronyd"
    provisional = make_test_chronyd_launch_policy_v48b(
        read_only_api_socket_path=f"{runtime_dir}/supervisor/readonly.sock"
    )
    unit = tmp_path / "riskyieldmm-chronyd.service"
    chronyd = tmp_path / "chronyd"
    config = tmp_path / "chrony.conf"
    source = tmp_path / "source.sources"
    unit_raw = b"[Service]\nType=notify\n"
    chronyd_raw = b"chronyd\n"
    config_raw = _minimal_base(provisional.real_command_socket_path)
    source_raw = b"server 192.0.2.1\n"
    _write(unit, unit_raw)
    _write(chronyd, chronyd_raw, executable=True)
    _write(config, config_raw)
    _write(source, source_raw)
    effective = _effective_bytes(config_raw, (source_raw,))
    printed = b"reviewed printed config\n"
    launch = _launch_policy(
        runtime_dir=runtime_dir,
        effective_sha256=_digest(effective),
        printed_sha256=_digest(printed),
        systemd_unit_name=unit.name,
        systemd_unit_path=str(unit),
        systemd_unit_sha256=_digest(unit_raw),
        chronyd_executable_path=str(chronyd),
        chronyd_executable_sha256=_digest(chronyd_raw),
    )
    source_artifact = ConfiguredChronySourceArtifactV4(
        path=str(source), sha256=_digest(source_raw)
    )
    policy = ClockSourcePolicyManifestV4(
        source_kind=CLOCK_SOURCE_KIND,
        chrony_version="4.8",
        chronyc_executable_path="/usr/bin/chronyc",
        chronyc_executable_sha256="a" * 64,
        chrony_config_path=str(config),
        chrony_config_sha256=_digest(config_raw),
        chronyc_command_socket_path=launch.read_only_api_socket_path,
        chronyc_command_timeout_milliseconds=1_000,
        chronyc_max_output_bytes=65_536,
        configured_source_set_root_sha256=(
            derive_configured_chrony_source_set_root_v4((source_artifact,))
        ),
        min_selectable_sources=1,
        max_uncertainty_milliseconds=100,
        max_sample_age_milliseconds=5_000,
        require_synchronized=True,
        require_normal_leap=True,
        monotonic_domain_profile=MONOTONIC_DOMAIN_PROFILE,
        chronyd_launch_policy=launch,
    )
    prepared = PreparedChronydLaunchV48B._prepare_for_test(
        policy=policy,
        configured_source_artifacts=(source_artifact,),
        command_runner=_PreparedRunner(printed=printed),
    )
    try:
        with pytest.raises(ChronydProcessV48BError, match="production prepared"):
            ChronydLaunchAuthorityV48B.launch(prepared)
    finally:
        prepared.close()


def test_preparation_closes_first_source_when_later_source_fails(
    tmp_path: Path,
) -> None:
    runtime_dir = "/run/riskyieldmm-test-chronyd"
    provisional = make_test_chronyd_launch_policy_v48b(
        read_only_api_socket_path=f"{runtime_dir}/supervisor/readonly.sock"
    )
    unit = tmp_path / "riskyieldmm-chronyd.service"
    chronyd = tmp_path / "chronyd"
    config = tmp_path / "chrony.conf"
    source_a = tmp_path / "a.sources"
    source_b = tmp_path / "b.sources"
    unit_raw = b"[Service]\nType=notify\n"
    chronyd_raw = b"chronyd\n"
    config_raw = _minimal_base(provisional.real_command_socket_path)
    source_a_raw = b"server 192.0.2.1\n"
    source_b_raw = b"server 192.0.2.2\n"
    for path, raw, executable in (
        (unit, unit_raw, False),
        (chronyd, chronyd_raw, True),
        (config, config_raw, False),
        (source_a, source_a_raw, False),
        (source_b, source_b_raw, False),
    ):
        _write(path, raw, executable=executable)
    source_artifacts = (
        ConfiguredChronySourceArtifactV4(
            path=str(source_a), sha256=_digest(source_a_raw)
        ),
        ConfiguredChronySourceArtifactV4(path=str(source_b), sha256="f" * 64),
    )
    effective = _effective_bytes(config_raw, (source_a_raw, source_b_raw))
    launch = _launch_policy(
        runtime_dir=runtime_dir,
        effective_sha256=_digest(effective),
        systemd_unit_name=unit.name,
        systemd_unit_path=str(unit),
        systemd_unit_sha256=_digest(unit_raw),
        chronyd_executable_path=str(chronyd),
        chronyd_executable_sha256=_digest(chronyd_raw),
    )
    policy = ClockSourcePolicyManifestV4(
        source_kind=CLOCK_SOURCE_KIND,
        chrony_version="4.8",
        chronyc_executable_path="/usr/bin/chronyc",
        chronyc_executable_sha256="a" * 64,
        chrony_config_path=str(config),
        chrony_config_sha256=_digest(config_raw),
        chronyc_command_socket_path=launch.read_only_api_socket_path,
        chronyc_command_timeout_milliseconds=1_000,
        chronyc_max_output_bytes=65_536,
        configured_source_set_root_sha256=(
            derive_configured_chrony_source_set_root_v4(source_artifacts)
        ),
        min_selectable_sources=1,
        max_uncertainty_milliseconds=100,
        max_sample_age_milliseconds=5_000,
        require_synchronized=True,
        require_normal_leap=True,
        monotonic_domain_profile=MONOTONIC_DOMAIN_PROFILE,
        chronyd_launch_policy=launch,
    )
    before = len(os.listdir("/proc/self/fd"))
    with pytest.raises(OperationalArtifactV4Error, match="digest differs"):
        PreparedChronydLaunchV48B._prepare_for_test(
            policy=policy,
            configured_source_artifacts=source_artifacts,
            command_runner=_PreparedRunner(printed=b"unused\n"),
        )
    after = len(os.listdir("/proc/self/fd"))
    assert after == before


def test_launch_authority_is_not_caller_constructible() -> None:
    with pytest.raises(TypeError):
        ChronydLaunchAuthorityV48B(  # type: ignore[call-arg]
            prepared=object(),
            process=object(),
            pidfd=-1,
            notify_socket=object(),
            notify_socket_identity=(1, 1),
            runtime_directory_fds=(-1,),
            runtime_directory_identities=((1, 1),),
            supervisor_invocation_id="0" * 32,
            process_snapshot=object(),
            command_socket_snapshot=object(),
            launch_id="1" * 64,
            runtime_observation_sha256="2" * 64,
            token=object(),
        )


@pytest.mark.skipif(not hasattr(os, "fork"), reason="requires POSIX fork semantics")
def test_fork_child_close_never_signals_or_unlinks_parent_authority(
    tmp_path: Path,
) -> None:
    short_root = Path(tempfile.mkdtemp(prefix="rv8-", dir="/tmp"))
    runtime = short_root / "runtime"
    chronyd_dir = runtime / "chronyd"
    supervisor_dir = runtime / "supervisor"
    chronyd_dir.mkdir(parents=True)
    supervisor_dir.mkdir()
    policy = make_test_chronyd_launch_policy_v48b(
        read_only_api_socket_path=str(supervisor_dir / "readonly.sock")
    )
    notify = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    command = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    notify.bind(policy.notify_socket_path)
    command.bind(policy.real_command_socket_path)
    notify_info = os.lstat(policy.notify_socket_path)
    command_info = os.lstat(policy.real_command_socket_path)
    marker = tmp_path / "parent-process-not-signalled"
    marker.write_text("present", encoding="ascii")

    class _Process:
        def poll(self):
            return None

        def send_signal(self, _signal):
            marker.unlink(missing_ok=True)

        def wait(self, *, timeout):
            return 0

        def kill(self):
            marker.unlink(missing_ok=True)

    runtime_fd = os.open(runtime, os.O_RDONLY | os.O_CLOEXEC)
    pidfd = os.open("/dev/null", os.O_RDONLY | os.O_CLOEXEC)
    authority = object.__new__(ChronydLaunchAuthorityV48B)
    authority._closed = False  # noqa: SLF001
    authority._creator_pid = os.getpid()  # noqa: SLF001
    authority._process = _Process()  # noqa: SLF001
    authority._pidfd = pidfd  # noqa: SLF001
    authority._notify_socket = notify  # noqa: SLF001
    authority._notify_socket_identity = (  # noqa: SLF001
        notify_info.st_dev,
        notify_info.st_ino,
    )
    authority._runtime_directory_fds = (runtime_fd,)  # noqa: SLF001
    authority._policy = SimpleNamespace(  # noqa: SLF001
        chronyd_launch_policy=policy
    )
    authority._command_socket_snapshot = SimpleNamespace(  # noqa: SLF001
        device=command_info.st_dev,
        inode=command_info.st_ino,
    )
    authority._prepared = SimpleNamespace(close=lambda: None)  # noqa: SLF001

    child = os.fork()
    if child == 0:
        try:
            authority.close()
        except BaseException:
            os._exit(1)
        os._exit(0)
    _, status = os.waitpid(child, 0)
    try:
        assert os.waitstatus_to_exitcode(status) == 0
        assert marker.exists()
        assert os.path.exists(policy.notify_socket_path)
        assert os.path.exists(policy.real_command_socket_path)
    finally:
        notify.close()
        command.close()
        os.close(runtime_fd)
        os.close(pidfd)
        os.unlink(policy.notify_socket_path)
        os.unlink(policy.real_command_socket_path)
        supervisor_dir.rmdir()
        chronyd_dir.rmdir()
        runtime.rmdir()
        short_root.rmdir()
