from __future__ import annotations

import hashlib
import os
import sys
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

import riskyieldmm.trading.physical_transport_linux_v4 as linux_v4
from riskyieldmm.trading.canonical import CanonicalizationError
from riskyieldmm.trading.operational_artifact_loading_v4 import (
    ConfiguredChronySourceArtifactV4,
    OperationalArtifactV4Error,
    derive_configured_chrony_source_set_root_v4,
)
from riskyieldmm.trading.operational_manifests_v4 import (
    CLOCK_SOURCE_KIND,
    MONOTONIC_DOMAIN_PROFILE,
    ClockSourcePolicyManifestV4,
)
from riskyieldmm.trading.physical_transport_linux_v4 import (
    BoundedCommandResultV4,
    DeterministicLinuxChronyClockV4,
    LinuxChronyClockV4,
    LinuxChronyEvidenceV4Error,
    LinuxTransportEvidenceV4Error,
    parse_chronyc_tracking_sources_v4,
    run_bounded_command_v4,
)
from tests._chronyd_launch_policy_v48b import (
    make_test_chronyd_launch_policy_v48b,
)

T0 = datetime(2026, 7, 15, 10, tzinfo=timezone.utc)
BOOT_ID = "12345678-1234-4123-8123-123456789abc"
TIME_NAMESPACE_ID = "1" * 64
VERSION_OUTPUT = b"chronyc (chrony) version 4.8\n"


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _parser_policy(**changes: Any) -> ClockSourcePolicyManifestV4:
    values: dict[str, Any] = {
        "source_kind": CLOCK_SOURCE_KIND,
        "chrony_version": "4.8",
        "chronyc_executable_path": "/usr/bin/chronyc",
        "chronyc_executable_sha256": "2" * 64,
        "chrony_config_path": "/etc/chrony/chrony.conf",
        "chrony_config_sha256": "3" * 64,
        "chronyc_command_socket_path": "/run/chrony/chronyd.sock",
        "chronyc_command_timeout_milliseconds": 2_000,
        "chronyc_max_output_bytes": 65_536,
        "configured_source_set_root_sha256": "4" * 64,
        "min_selectable_sources": 3,
        "max_uncertainty_milliseconds": 100,
        "max_sample_age_milliseconds": 5_000,
        "require_synchronized": True,
        "require_normal_leap": True,
        "monotonic_domain_profile": MONOTONIC_DOMAIN_PROFILE,
        "chronyd_launch_policy": make_test_chronyd_launch_policy_v48b(
            read_only_api_socket_path="/run/chrony/chronyd.sock"
        ),
    }
    values.update(changes)
    return ClockSourcePolicyManifestV4(**values)


def _tracking_fields(
    *,
    reference_id: str = "C0000201",
    reference_name: str = "time-a.example",
    reference_time: datetime = T0,
    leap_status: str = "Normal",
) -> list[str]:
    return [
        reference_id,
        reference_name,
        "2",
        str(int(reference_time.timestamp())),
        "0.001000000",
        "-0.000250000",
        "0.000500000",
        "1.250000",
        "-0.125000",
        "0.010000",
        "0.004000000",
        "0.002000000",
        "16.000000000",
        leap_status,
    ]


def _source_fields(
    name: str,
    state: str,
    *,
    reach: str = "377",
    last_rx: int = 1,
) -> list[str]:
    return [
        "^",
        state,
        name,
        "1",
        "6",
        reach,
        str(last_rx),
        "0.000100000",
        "-0.000200000",
        "0.001000000",
    ]


def _valid_source_rows() -> list[list[str]]:
    return [
        _source_fields("time-a.example", "*"),
        _source_fields("time-b.example", "+", last_rx=0),
        _source_fields("time-c.example", "-", last_rx=2),
    ]


def _combined_output(
    *,
    tracking: list[str] | None = None,
    sources: list[list[str]] | None = None,
) -> bytes:
    tracking_row = ",".join(tracking or _tracking_fields())
    source_rows = "\n".join(
        ",".join(fields) for fields in (sources or _valid_source_rows())
    )
    return f".\n.\n{tracking_row}\n.\n{source_rows}\n.\n".encode("ascii")


def _parse(
    raw: bytes,
    *,
    policy: ClockSourcePolicyManifestV4 | None = None,
):
    return parse_chronyc_tracking_sources_v4(
        raw,
        policy=policy or _parser_policy(),
        wall_after_at=T0 + timedelta(milliseconds=10),
        collection_width_ns=10_000_000,
        clock_resolution_ns=1_000,
    )


class _FakePinnedThreadNamespaceV4:
    instances: list[_FakePinnedThreadNamespaceV4] = []

    def __init__(self, *, kind: str, expected_type: int) -> None:
        assert kind == "time"
        assert expected_type == linux_v4._CLONE_NEWTIME
        self.kind = kind
        self.namespace_id = TIME_NAMESPACE_ID
        self.closed = False
        self.instances.append(self)

    def assert_current(self) -> None:
        if self.closed:
            raise AssertionError("test namespace was used after close")

    def close(self) -> None:
        self.closed = True


class _FakeRunner:
    def __init__(
        self,
        *,
        sample_output: bytes,
        version_result: object | None = None,
        sample_result: object | None = None,
    ) -> None:
        self.sample_output = sample_output
        self.version_result = version_result
        self.sample_result = sample_result
        self.calls: list[tuple[tuple[str, ...], dict[str, object]]] = []

    def __call__(self, argv: tuple[str, ...], **kwargs: object) -> object:
        self.calls.append((argv, kwargs))
        if argv[-1] == "--version":
            return self.version_result or BoundedCommandResultV4(
                returncode=0,
                stdout=VERSION_OUTPUT,
                stderr=b"",
            )
        if self.sample_result is not None:
            return self.sample_result
        return BoundedCommandResultV4(
            returncode=0,
            stdout=self.sample_output,
            stderr=b"",
        )


def _write_artifact(path: Path, raw: bytes, *, executable: bool = False) -> None:
    path.write_bytes(raw)
    path.chmod(0o700 if executable else 0o600)


def _clock_policy_and_artifacts(
    tmp_path: Path,
) -> tuple[
    ClockSourcePolicyManifestV4,
    tuple[ConfiguredChronySourceArtifactV4, ...],
    dict[str, Path],
]:
    paths = {
        "chronyc": tmp_path / "chronyc",
        "config": tmp_path / "chrony.conf",
        "source_a": tmp_path / "source-a.sources",
        "source_b": tmp_path / "source-b.sources",
    }
    raw = {
        "chronyc": b"test chronyc executable\n",
        "config": b"confdir /etc/chrony/sources.d\n",
        "source_a": b"server time-a.example iburst\n",
        "source_b": b"server time-b.example iburst\n",
    }
    for name, path in paths.items():
        _write_artifact(path, raw[name], executable=name == "chronyc")
    sources = tuple(
        ConfiguredChronySourceArtifactV4(
            path=str(paths[name]),
            sha256=_sha256(raw[name]),
        )
        for name in ("source_a", "source_b")
    )
    policy = ClockSourcePolicyManifestV4(
        source_kind=CLOCK_SOURCE_KIND,
        chrony_version="4.8",
        chronyc_executable_path=str(paths["chronyc"]),
        chronyc_executable_sha256=_sha256(raw["chronyc"]),
        chrony_config_path=str(paths["config"]),
        chrony_config_sha256=_sha256(raw["config"]),
        chronyc_command_socket_path="/run/chrony/chronyd.sock",
        chronyc_command_timeout_milliseconds=2_000,
        chronyc_max_output_bytes=65_536,
        configured_source_set_root_sha256=(
            derive_configured_chrony_source_set_root_v4(sources)
        ),
        min_selectable_sources=3,
        max_uncertainty_milliseconds=100,
        max_sample_age_milliseconds=5_000,
        require_synchronized=True,
        require_normal_leap=True,
        monotonic_domain_profile=MONOTONIC_DOMAIN_PROFILE,
        chronyd_launch_policy=make_test_chronyd_launch_policy_v48b(
            read_only_api_socket_path="/run/chrony/chronyd.sock"
        ),
    )
    return policy, sources, paths


def _install_deterministic_kernel(
    monkeypatch: pytest.MonkeyPatch,
    *,
    boottimes_ns: tuple[int, ...] = (1_000_000_000, 1_010_000_000),
) -> None:
    samples = iter(boottimes_ns)
    _FakePinnedThreadNamespaceV4.instances.clear()
    monkeypatch.setattr(
        linux_v4, "_PinnedThreadNamespaceV4", _FakePinnedThreadNamespaceV4
    )
    monkeypatch.setattr(linux_v4, "_boottime_ns", lambda: next(samples))
    monkeypatch.setattr(linux_v4.time, "clock_getres", lambda _clock_id: 0.000001)
    monkeypatch.setattr(
        LinuxChronyClockV4,
        "_read_boot_id",
        lambda _self: BOOT_ID,
    )


def _make_clock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    runner: _FakeRunner | None = None,
    wall_clock: Callable[[], datetime] | None = None,
) -> tuple[LinuxChronyClockV4, _FakeRunner, dict[str, Path]]:
    policy, sources, paths = _clock_policy_and_artifacts(tmp_path)
    active_runner = runner or _FakeRunner(sample_output=_combined_output())
    walls = iter((T0, T0 + timedelta(milliseconds=10)))
    clock = DeterministicLinuxChronyClockV4(
        policy=policy,
        configured_source_artifacts=sources,
        command_runner=active_runner,
        wall_clock=wall_clock or (lambda: next(walls)),
    )
    return clock, active_runner, paths


def test_governed_clock_produces_rich_nonzero_bracket_from_pinned_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_deterministic_kernel(monkeypatch)
    clock, runner, _ = _make_clock(tmp_path, monkeypatch)
    raw = _combined_output()

    try:
        sample = clock.sample_governed()
        evidence = sample.as_clock_evidence()

        assert sample.clock_source_manifest_id == clock.policy.manifest_id
        assert sample.kernel_boot_id == BOOT_ID
        assert sample.time_namespace_id == TIME_NAMESPACE_ID
        assert sample.monotonic_clock_domain_id == clock.monotonic_clock_domain_id
        assert sample.wall_before_at == T0
        assert sample.wall_after_at == T0 + timedelta(milliseconds=10)
        assert sample.boottime_before_ns == 1_000_000_000
        assert sample.boottime_after_ns == 1_010_000_000
        assert sample.clock_resolution_ns == 1_000
        assert sample.uncertainty_milliseconds == 16
        assert sample.selectable_source_count == 3
        assert sample.selected_source_age_milliseconds == 1_000
        assert sample.valid_until == T0 + timedelta(seconds=5)
        assert sample.observation_sha256 == _sha256(raw)
        assert sample.chronyd_launch_id is None
        assert sample.chronyd_runtime_observation_sha256 is None
        assert sample.tracking_output_sha256 == _sha256(
            (",".join(_tracking_fields()) + "\n").encode("ascii")
        )
        assert sample.sources_output_sha256 == _sha256(
            ("\n".join(",".join(row) for row in _valid_source_rows()) + "\n").encode(
                "ascii"
            )
        )
        assert evidence.monotonic_before_ns == sample.boottime_before_ns
        assert evidence.monotonic_ns == sample.boottime_after_ns
        assert evidence.monotonic_after_ns == sample.boottime_after_ns
        assert evidence.wall_before_at == sample.wall_before_at
        assert evidence.wall_after_at == sample.wall_after_at
        assert evidence.observation_sha256 == sample.observation_sha256
        assert evidence.selectable_source_count == 3
        assert evidence.chronyd_launch_id is None
        assert evidence.chronyd_runtime_observation_sha256 is None
        assert evidence.synchronized is True

        assert len(runner.calls) == 2
        version_argv, version_kwargs = runner.calls[0]
        sample_argv, sample_kwargs = runner.calls[1]
        assert version_argv[0].startswith("/proc/self/fd/")
        assert version_argv[1:] == ("--version",)
        assert sample_argv[0] == version_argv[0]
        assert sample_argv[1:] == (
            "-n",
            "-c",
            "-e",
            "-h",
            "/run/chrony/chronyd.sock",
            "-m",
            "timeout 1000",
            "retries 0",
            "tracking",
            "sources -a",
        )
        for kwargs in (version_kwargs, sample_kwargs):
            assert kwargs["timeout_milliseconds"] == 2_000
            assert kwargs["maximum_output_bytes"] == 65_536
            pass_fds = kwargs["pass_fds"]
            assert type(pass_fds) is tuple and len(pass_fds) == 1
            assert type(pass_fds[0]) is int
            assert os.get_inheritable(pass_fds[0]) is False
    finally:
        clock.close()


@pytest.mark.parametrize(
    "raw",
    [
        b"not-the-reviewed-profile\n",
        _combined_output(tracking=_tracking_fields() + ["unexpected"]),
        _combined_output(tracking=_tracking_fields()[:-1]),
        _combined_output(
            tracking=[
                "NaN" if index == 4 else value
                for index, value in enumerate(_tracking_fields())
            ]
        ),
        _combined_output(
            tracking=[
                "Infinity" if index == 11 else value
                for index, value in enumerate(_tracking_fields())
            ]
        ),
        _combined_output()[:-1],
    ],
    ids=(
        "malformed-boundaries",
        "extra-tracking-field",
        "truncated-tracking-row",
        "nan-tracking-field",
        "infinite-tracking-field",
        "truncated-final-boundary",
    ),
)
def test_tracking_parser_rejects_malformed_extra_truncated_and_nonfinite_rows(
    raw: bytes,
) -> None:
    with pytest.raises(LinuxChronyEvidenceV4Error):
        _parse(raw)


@pytest.mark.parametrize(
    "tracking,sources",
    [
        (_tracking_fields(leap_status="Not synchronised"), _valid_source_rows()),
        (_tracking_fields(reference_id="7F7F0101"), _valid_source_rows()),
        (
            _tracking_fields(reference_name="different.example"),
            _valid_source_rows(),
        ),
    ],
    ids=("non-normal-leap", "local-reference", "reference-source-mismatch"),
)
def test_tracking_parser_rejects_leap_local_and_reference_mismatch(
    tracking: list[str], sources: list[list[str]]
) -> None:
    with pytest.raises(LinuxChronyEvidenceV4Error):
        _parse(_combined_output(tracking=tracking, sources=sources))


@pytest.mark.parametrize(
    "tracking,sources",
    [
        (
            _tracking_fields(reference_time=T0 - timedelta(seconds=6)),
            _valid_source_rows(),
        ),
        (
            _tracking_fields(),
            [
                _source_fields("time-a.example", "*", last_rx=6),
                _source_fields("time-b.example", "+"),
                _source_fields("time-c.example", "-"),
            ],
        ),
    ],
    ids=("stale-tracking-reference", "stale-selected-source"),
)
def test_tracking_parser_rejects_stale_tracking_and_source_evidence(
    tracking: list[str], sources: list[list[str]]
) -> None:
    with pytest.raises(LinuxChronyEvidenceV4Error, match="stale"):
        _parse(_combined_output(tracking=tracking, sources=sources))


def test_tracking_parser_counts_selected_combined_and_selectable_sources() -> None:
    parsed = _parse(_combined_output())

    assert parsed.selectable_source_count == 3
    assert parsed.selected_source_age_milliseconds == 1_000


def test_tracking_parser_rejects_insufficient_selectable_sources() -> None:
    sources = [
        _source_fields("time-a.example", "*"),
        _source_fields("time-b.example", "+"),
    ]

    with pytest.raises(LinuxChronyEvidenceV4Error, match="fewer selectable"):
        _parse(_combined_output(sources=sources))


def test_tracking_parser_rejects_duplicate_selected_sources() -> None:
    sources = [
        _source_fields("time-a.example", "*"),
        _source_fields("time-b.example", "*"),
        _source_fields("time-c.example", "+"),
    ]

    with pytest.raises(LinuxChronyEvidenceV4Error, match="sole selected"):
        _parse(_combined_output(sources=sources))


def test_clock_rejects_signed_source_root_mismatch(tmp_path: Path) -> None:
    policy, sources, _ = _clock_policy_and_artifacts(tmp_path)

    with pytest.raises(LinuxChronyEvidenceV4Error, match="source closure"):
        DeterministicLinuxChronyClockV4(
            policy=replace(policy, configured_source_set_root_sha256="f" * 64),
            configured_source_artifacts=sources,
            command_runner=_FakeRunner(sample_output=_combined_output()),
            wall_clock=lambda: T0,
        )


def test_source_root_binds_sorted_unique_paths_and_declared_digests(
    tmp_path: Path,
) -> None:
    policy, sources, _ = _clock_policy_and_artifacts(tmp_path)
    changed = replace(sources[1], sha256="e" * 64)

    assert derive_configured_chrony_source_set_root_v4(sources) == (
        policy.configured_source_set_root_sha256
    )
    assert derive_configured_chrony_source_set_root_v4((sources[0], changed)) != (
        policy.configured_source_set_root_sha256
    )
    with pytest.raises(CanonicalizationError, match="path-sorted"):
        derive_configured_chrony_source_set_root_v4(tuple(reversed(sources)))
    with pytest.raises(CanonicalizationError, match="unique"):
        derive_configured_chrony_source_set_root_v4((sources[0], sources[0]))


@pytest.mark.parametrize("artifact_name", ("chronyc", "config", "source_a"))
def test_clock_revalidates_every_pinned_artifact_before_sampling(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    artifact_name: str,
) -> None:
    _install_deterministic_kernel(monkeypatch)
    clock, _, paths = _make_clock(tmp_path, monkeypatch)
    paths[artifact_name].write_bytes(b"changed after admission\n")

    try:
        with pytest.raises(LinuxChronyEvidenceV4Error, match="artifact changed"):
            clock.sample_governed()
    finally:
        clock.close()


def test_clock_rejects_artifact_with_wrong_declared_digest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_deterministic_kernel(monkeypatch)
    policy, sources, _ = _clock_policy_and_artifacts(tmp_path)

    with pytest.raises(OperationalArtifactV4Error, match="digest"):
        DeterministicLinuxChronyClockV4(
            policy=replace(policy, chrony_config_sha256="f" * 64),
            configured_source_artifacts=sources,
            command_runner=_FakeRunner(sample_output=_combined_output()),
            wall_clock=lambda: T0,
        )


@pytest.mark.parametrize(
    "version_result",
    [
        BoundedCommandResultV4(
            returncode=0,
            stdout=b"chronyc (chrony) version 4.7\n",
            stderr=b"",
        ),
        BoundedCommandResultV4(returncode=1, stdout=b"", stderr=b""),
        BoundedCommandResultV4(
            returncode=0,
            stdout=VERSION_OUTPUT,
            stderr=b"unexpected warning\n",
        ),
        BoundedCommandResultV4(
            returncode=False,
            stdout=VERSION_OUTPUT,
            stderr=b"",
        ),
        BoundedCommandResultV4(
            returncode=0,
            stdout="chronyc (chrony) version 4.8\n",  # type: ignore[arg-type]
            stderr=b"",
        ),
        BoundedCommandResultV4(
            returncode=0,
            stdout=b"x" * 65_537,
            stderr=b"",
        ),
        object(),
    ],
    ids=(
        "wrong-version",
        "nonzero-result",
        "stderr-result",
        "boolean-returncode",
        "non-bytes-stdout",
        "oversized-output",
        "foreign-result",
    ),
)
def test_clock_rejects_unreviewed_version_and_failed_version_results(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    version_result: object,
) -> None:
    _install_deterministic_kernel(monkeypatch)
    policy, sources, _ = _clock_policy_and_artifacts(tmp_path)
    runner = _FakeRunner(
        sample_output=_combined_output(),
        version_result=version_result,
    )

    with pytest.raises(LinuxChronyEvidenceV4Error):
        DeterministicLinuxChronyClockV4(
            policy=policy,
            configured_source_artifacts=sources,
            command_runner=runner,
            wall_clock=lambda: T0,
        )


@pytest.mark.parametrize(
    "sample_result",
    [
        BoundedCommandResultV4(returncode=1, stdout=b"", stderr=b""),
        BoundedCommandResultV4(
            returncode=0,
            stdout=_combined_output(),
            stderr=b"unexpected warning\n",
        ),
        object(),
    ],
    ids=("nonzero-result", "stderr-result", "foreign-result"),
)
def test_clock_rejects_failed_tracking_command_results(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    sample_result: object,
) -> None:
    _install_deterministic_kernel(monkeypatch)
    runner = _FakeRunner(
        sample_output=_combined_output(),
        sample_result=sample_result,
    )
    clock, _, _ = _make_clock(tmp_path, monkeypatch, runner=runner)

    try:
        with pytest.raises(LinuxChronyEvidenceV4Error):
            clock.sample_governed()
    finally:
        clock.close()


def test_clock_close_is_idempotent_and_revokes_all_future_sampling(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_deterministic_kernel(monkeypatch)
    clock, _, _ = _make_clock(tmp_path, monkeypatch)
    namespace = _FakePinnedThreadNamespaceV4.instances[-1]

    clock.close()
    clock.close()

    assert namespace.closed is True
    assert clock._time_namespace is None
    assert clock._boot_fd is None
    assert clock._chronyc is None
    assert clock._config is None
    assert clock._sources == ()
    with pytest.raises(LinuxTransportEvidenceV4Error, match="process/thread"):
        clock.sample_governed()


def test_real_bounded_runner_captures_exact_bytes_without_a_shell() -> None:
    result = run_bounded_command_v4(
        (sys.executable, "-c", "import sys;sys.stdout.buffer.write(b'ok')"),
        pass_fds=(),
        timeout_milliseconds=1_000,
        maximum_output_bytes=64,
    )

    assert result == BoundedCommandResultV4(returncode=0, stdout=b"ok", stderr=b"")


def test_real_bounded_runner_kills_timeout_and_oversized_output() -> None:
    with pytest.raises(LinuxChronyEvidenceV4Error, match="deadline"):
        run_bounded_command_v4(
            (sys.executable, "-c", "while True: pass"),
            pass_fds=(),
            timeout_milliseconds=25,
            maximum_output_bytes=64,
        )

    with pytest.raises(LinuxChronyEvidenceV4Error, match="byte cap"):
        run_bounded_command_v4(
            (
                sys.executable,
                "-c",
                "import sys;sys.stdout.buffer.write(b'x'*4096)",
            ),
            pass_fds=(),
            timeout_milliseconds=1_000,
            maximum_output_bytes=64,
        )
