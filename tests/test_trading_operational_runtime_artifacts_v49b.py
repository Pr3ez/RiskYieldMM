from __future__ import annotations

import copy
import hashlib
import importlib.metadata
import importlib.util
import multiprocessing
import os
import platform
import py_compile
import ssl
import subprocess
import sys
import sysconfig
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from riskyieldmm.trading import operational_runtime_artifacts_v49b as artifacts_v49b
from riskyieldmm.trading.canonical import CanonicalizationError
from riskyieldmm.trading.operational_manifests_v4 import (
    TLS_WEBSOCKET_DRIVER_ARTIFACT_ROLES_V49B,
    TLS_WEBSOCKET_DRIVER_BYTECODE_CACHE_ROLES_V49B,
    TLS_WEBSOCKET_DRIVER_DISTRIBUTIONS_V49B,
    InstalledDistributionClosureV49B,
    OperationalManifestKindV4,
    RuntimeArtifactMemberV49B,
    RuntimeEnvironmentManifestV4,
    TlsWebSocketDriverPolicyV49B,
)
from riskyieldmm.trading.operational_runtime_artifacts_v49b import (
    PinnedTlsWebSocketRuntimeArtifactsV49B,
    RuntimeArtifactAuthorityV49BError,
    _mapped_openssl_paths,
    _mapped_openssl_paths_from_maps,
    _PinnedRuntimeMemberV49B,
    capture_current_tls_websocket_driver_policy_v49b,
)

_BYTECODE_CACHE_MODULES = {
    "PYTHON_STDLIB_SSL_BYTECODE_CACHE": "ssl",
    "RISKYIELDMM_TLS_DRIVER_BYTECODE_CACHE": (
        "riskyieldmm.trading.physical_transport_tls_v49"
    ),
    "RISKYIELDMM_TLS_TRUST_STORE_BYTECODE_CACHE": (
        "riskyieldmm.trading.tls_trust_store_v49"
    ),
}


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _member(path: Path, payload: bytes) -> RuntimeArtifactMemberV49B:
    return RuntimeArtifactMemberV49B(
        role="TEST_RUNTIME_MEMBER",
        path=str(path),
        size_bytes=len(payload),
        sha256=_digest(payload),
        require_executable=False,
    )


@pytest.fixture(scope="module")
def current_policy() -> TlsWebSocketDriverPolicyV49B:
    return capture_current_tls_websocket_driver_policy_v49b()


def _runtime_environment(
    policy: TlsWebSocketDriverPolicyV49B,
) -> RuntimeEnvironmentManifestV4:
    python_member = next(
        member
        for member in policy.runtime_artifacts
        if member.role == "PYTHON_EXECUTABLE"
    )
    return RuntimeEnvironmentManifestV4(
        python_implementation=policy.python_implementation,
        python_version=policy.python_version,
        python_executable_sha256=python_member.sha256,
        platform_tag=sysconfig.get_platform(),
        openssl_version=policy.openssl_version,
        installed_distribution_root_sha256=(policy.installed_distribution_root_sha256),
        dependency_lock_manifest_id="1" * 64,
        collector_release_manifest_id="2" * 64,
        tls_trust_store_manifest_id="3" * 64,
        clock_source_policy_manifest_id="4" * 64,
        isolated_mode=True,
        user_site_enabled=False,
        tls_websocket_driver_policy=policy,
    )


def test_capture_is_exact_member_closure_with_real_origins_and_versions(
    current_policy: TlsWebSocketDriverPolicyV49B,
) -> None:
    assert current_policy.python_implementation == platform.python_implementation()
    assert current_policy.python_version == platform.python_version()
    assert current_policy.openssl_version == ssl.OPENSSL_VERSION
    assert {
        member.role for member in current_policy.runtime_artifacts
    } == TLS_WEBSOCKET_DRIVER_ARTIFACT_ROLES_V49B
    assert {
        member.role for member in current_policy.python_bytecode_cache_artifacts
    } == TLS_WEBSOCKET_DRIVER_BYTECODE_CACHE_ROLES_V49B
    assert {
        distribution.distribution_name
        for distribution in current_policy.installed_distributions
    } == TLS_WEBSOCKET_DRIVER_DISTRIBUTIONS_V49B

    all_paths = [
        member.path
        for member in (
            current_policy.runtime_artifacts
            + current_policy.python_bytecode_cache_artifacts
        )
    ]
    for member in current_policy.python_bytecode_cache_artifacts:
        module = importlib.import_module(_BYTECODE_CACHE_MODULES[member.role])
        origin = module.__spec__.origin
        assert type(origin) is str
        assert member.path == module.__cached__
        assert member.path == importlib.util.cache_from_source(origin)
        assert member.require_executable is False
    for closure in current_policy.installed_distributions:
        installed = importlib.metadata.distribution(closure.distribution_name)
        assert closure.distribution_version == installed.version
        assert closure.distribution_origin == os.path.abspath(
            os.fspath(installed.locate_file(""))
        )
        expected_paths = {
            os.path.abspath(os.fspath(installed.locate_file(item)))
            for item in installed.files or ()
        }
        actual_paths = {member.path for member in closure.members}
        assert actual_paths == expected_paths
        assert closure.module_origin in actual_paths
        all_paths.extend(actual_paths)

    assert len(all_paths) == len(set(all_paths))
    for member in (
        current_policy.runtime_artifacts
        + current_policy.python_bytecode_cache_artifacts
    ):
        status = os.stat(member.path, follow_symlinks=False)
        assert status.st_size == member.size_bytes
    python_member = next(
        member
        for member in current_policy.runtime_artifacts
        if member.role == "PYTHON_EXECUTABLE"
    )
    assert os.path.samefile(python_member.path, "/proc/self/exe")


def test_policy_and_nested_runtime_manifest_round_trip_and_tamper_rejection(
    current_policy: TlsWebSocketDriverPolicyV49B,
) -> None:
    restored = TlsWebSocketDriverPolicyV49B.from_mapping(current_policy.as_dict())
    assert restored == current_policy
    assert restored.policy_id == current_policy.policy_id

    runtime = _runtime_environment(current_policy)
    assert RuntimeEnvironmentManifestV4.from_mapping(runtime.as_dict()) == runtime
    assert runtime.tls_websocket_driver_policy is current_policy

    tampered = copy.deepcopy(current_policy.as_dict())
    tampered["runtime_artifacts"][0]["sha256"] = "0" * 64
    with pytest.raises(CanonicalizationError, match="policy ID differs"):
        TlsWebSocketDriverPolicyV49B.from_mapping(tampered)

    tampered_cache = copy.deepcopy(current_policy.as_dict())
    tampered_cache["python_bytecode_cache_artifacts"][0]["sha256"] = "0" * 64
    with pytest.raises(CanonicalizationError, match="policy ID differs"):
        TlsWebSocketDriverPolicyV49B.from_mapping(tampered_cache)

    incomplete_cache = copy.deepcopy(current_policy.as_dict())
    incomplete_cache["python_bytecode_cache_artifacts"].pop()
    with pytest.raises(CanonicalizationError, match="exact three roles"):
        TlsWebSocketDriverPolicyV49B.from_mapping(incomplete_cache)


def test_nested_driver_policy_does_not_expand_exact_six_deployment_children(
    current_policy: TlsWebSocketDriverPolicyV49B,
) -> None:
    runtime = _runtime_environment(current_policy)

    assert len(OperationalManifestKindV4) == 6
    assert runtime.KIND is OperationalManifestKindV4.RUNTIME_ENVIRONMENT
    assert "tls_websocket_driver_policy" in runtime.as_dict()
    assert "kind" not in runtime.as_dict()["tls_websocket_driver_policy"]


def test_full_authority_is_non_promotable_in_test_profile_and_fork_invalidates(
    current_policy: TlsWebSocketDriverPolicyV49B,
) -> None:
    runtime = _runtime_environment(current_policy)
    authority = PinnedTlsWebSocketRuntimeArtifactsV49B._open_verified_for_test(
        policy=current_policy,
        runtime_environment=runtime,
    )
    try:
        authority.assert_current()
        observation = authority.runtime_observation_sha256
        assert len(observation) == 64
        assert authority.runtime_observation_sha256 == observation
        assert authority.policy_id == current_policy.policy_id
        assert authority.runtime_environment_manifest_id == runtime.manifest_id
        assert authority.is_promotion_eligible is False
        assert authority.is_promotion_profile is False
        assert len(authority._artifacts) == (
            len(current_policy.runtime_artifacts)
            + len(current_policy.python_bytecode_cache_artifacts)
            + sum(
                len(distribution.members)
                for distribution in current_policy.installed_distributions
            )
        )

        read_descriptor, write_descriptor = os.pipe()
        child_pid = os.fork()
        if child_pid == 0:
            os.close(read_descriptor)
            try:
                authority.assert_current()
            except RuntimeArtifactAuthorityV49BError:
                os.write(write_descriptor, b"invalid")
            else:
                os.write(write_descriptor, b"live")
            finally:
                os.close(write_descriptor)
            os._exit(0)
        os.close(write_descriptor)
        child_result = os.read(read_descriptor, 16)
        os.close(read_descriptor)
        _, child_status = os.waitpid(child_pid, 0)
        assert os.waitstatus_to_exitcode(child_status) == 0
        assert child_result == b"invalid"
        authority.assert_current()
    finally:
        authority.close()
        authority.close()

    with pytest.raises(RuntimeArtifactAuthorityV49BError, match="creating process"):
        authority.assert_current()


def test_live_authority_rejects_non_isolated_test_process(
    current_policy: TlsWebSocketDriverPolicyV49B,
) -> None:
    runtime = _runtime_environment(current_policy)

    with pytest.raises(RuntimeArtifactAuthorityV49BError, match="-I -S -B"):
        PinnedTlsWebSocketRuntimeArtifactsV49B.open_verified(
            policy=current_policy,
            runtime_environment=runtime,
        )


def test_full_authority_rejects_signed_member_and_origin_tampering(
    current_policy: TlsWebSocketDriverPolicyV49B,
) -> None:
    changed_member = replace(
        current_policy.runtime_artifacts[0],
        sha256=(
            "f" * 64
            if current_policy.runtime_artifacts[0].sha256 != "f" * 64
            else "e" * 64
        ),
    )
    changed_policy = replace(
        current_policy,
        runtime_artifacts=(
            changed_member,
            *current_policy.runtime_artifacts[1:],
        ),
    )
    with pytest.raises(RuntimeArtifactAuthorityV49BError, match="differ from signed"):
        PinnedTlsWebSocketRuntimeArtifactsV49B._open_verified_for_test(
            policy=changed_policy,
            runtime_environment=_runtime_environment(changed_policy),
        )

    closure = current_policy.installed_distributions[0]
    alternate_origin = next(
        member.path
        for member in closure.members
        if member.path != closure.module_origin
    )
    changed_closure = replace(closure, module_origin=alternate_origin)
    changed_distributions = tuple(
        changed_closure if item is closure else item
        for item in current_policy.installed_distributions
    )
    origin_policy = replace(
        current_policy,
        installed_distributions=changed_distributions,
    )
    with pytest.raises(RuntimeArtifactAuthorityV49BError, match="origins differ"):
        PinnedTlsWebSocketRuntimeArtifactsV49B._open_verified_for_test(
            policy=origin_policy,
            runtime_environment=_runtime_environment(origin_policy),
        )


def test_retained_member_rejects_symlink_writable_mutation_and_replacement(
    tmp_path: Path,
) -> None:
    payload = b"exact V4.9B member bytes\n"
    path = tmp_path / "runtime-member"
    path.write_bytes(payload)
    path.chmod(0o664)
    member = _member(path, payload)

    with pytest.raises(RuntimeArtifactAuthorityV49BError, match="group- or world"):
        _PinnedRuntimeMemberV49B.open_verified(member, allow_writable=False)

    retained = _PinnedRuntimeMemberV49B.open_verified(
        member,
        allow_writable=True,
    )
    try:
        assert not os.get_inheritable(retained._descriptor)
        path.write_bytes(b"tampered V4.9B member!!!\n")
        assert path.stat().st_size == member.size_bytes
        with pytest.raises(RuntimeArtifactAuthorityV49BError):
            retained.assert_current()
    finally:
        retained.close()

    path.write_bytes(payload)
    path.chmod(0o644)
    retained = _PinnedRuntimeMemberV49B.open_verified(
        _member(path, payload),
        allow_writable=False,
    )
    replacement = tmp_path / "replacement"
    replacement.write_bytes(payload)
    replacement.chmod(0o644)
    os.replace(replacement, path)
    try:
        with pytest.raises(RuntimeArtifactAuthorityV49BError):
            retained.assert_current()
    finally:
        retained.close()

    target = tmp_path / "target"
    target.write_bytes(payload)
    target.chmod(0o644)
    link = tmp_path / "leaf-link"
    link.symlink_to(target.name)
    with pytest.raises(RuntimeArtifactAuthorityV49BError, match="final symlink"):
        _PinnedRuntimeMemberV49B.open_verified(
            _member(link, payload),
            allow_writable=False,
        )


def test_distribution_module_origin_must_be_a_signed_member(
    current_policy: TlsWebSocketDriverPolicyV49B,
) -> None:
    closure = current_policy.installed_distributions[0]

    with pytest.raises(CanonicalizationError, match="origin is not a signed member"):
        InstalledDistributionClosureV49B(
            distribution_name=closure.distribution_name,
            distribution_version=closure.distribution_version,
            distribution_origin=closure.distribution_origin,
            module_origin="/not/a/signed/member.py",
            members=closure.members,
        )


def test_minus_b_still_reads_a_valid_bytecode_cache(tmp_path: Path) -> None:
    source = tmp_path / "bytecode_probe.py"
    source.write_text("VALUE = 'PWN!'\n")
    source_timestamp_ns = source.stat().st_mtime_ns
    py_compile.compile(str(source), doraise=True)
    cache = Path(importlib.util.cache_from_source(str(source)))
    source.write_text("VALUE = 'SAFE'\n")
    os.utime(source, ns=(source_timestamp_ns, source_timestamp_ns))

    completed = subprocess.run(
        [
            sys.executable,
            "-I",
            "-S",
            "-B",
            "-c",
            (
                f"import sys; sys.path.insert(0, {str(tmp_path)!r}); "
                "import bytecode_probe; print(bytecode_probe.VALUE)"
            ),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert source.read_text() == "VALUE = 'SAFE'\n"
    assert cache.is_file()
    assert completed.stdout.strip() == "PWN!"


def test_cache_origin_mismatch_is_rejected_before_policy_capture(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(ssl, "__cached__", "/tmp/not-the-ssl-origin.pyc")

    with pytest.raises(
        RuntimeArtifactAuthorityV49BError,
        match="differs from its exact source origin",
    ):
        capture_current_tls_websocket_driver_policy_v49b()


def test_static_interpreter_guard_rejects_shared_build_and_loaded_libpython(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert sysconfig.get_config_var("Py_ENABLE_SHARED") == 0
    artifacts_v49b._assert_static_interpreter_profile()
    original_get_config_var = sysconfig.get_config_var

    monkeypatch.setattr(
        artifacts_v49b.sysconfig,
        "get_config_var",
        lambda name: 1 if name == "Py_ENABLE_SHARED" else original_get_config_var(name),
    )
    with pytest.raises(RuntimeArtifactAuthorityV49BError, match="linked into"):
        artifacts_v49b._assert_static_interpreter_profile()

    monkeypatch.setattr(
        artifacts_v49b.sysconfig,
        "get_config_var",
        original_get_config_var,
    )
    monkeypatch.setattr(
        artifacts_v49b,
        "_mapped_libpython_paths",
        lambda: ("/usr/lib/libpython3.12.so.1.0",),
    )
    with pytest.raises(RuntimeArtifactAuthorityV49BError, match="libpython"):
        artifacts_v49b._assert_static_interpreter_profile()


def test_promotion_flags_reject_optimized_python(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    exact = {
        "dont_write_bytecode": 1,
        "ignore_environment": 1,
        "isolated": 1,
        "no_site": 1,
        "no_user_site": 1,
        "safe_path": True,
    }
    monkeypatch.setattr(
        artifacts_v49b,
        "sys",
        SimpleNamespace(flags=SimpleNamespace(**exact, optimize=0)),
    )
    assert artifacts_v49b._promotion_interpreter_flags_are_exact()

    for optimization in (1, 2):
        monkeypatch.setattr(
            artifacts_v49b,
            "sys",
            SimpleNamespace(flags=SimpleNamespace(**exact, optimize=optimization)),
        )
        assert not artifacts_v49b._promotion_interpreter_flags_are_exact()


def test_deleted_posix_semaphore_mapping_does_not_poison_openssl_capture(
    current_policy: TlsWebSocketDriverPolicyV49B,
) -> None:
    baseline = _mapped_openssl_paths()
    semaphore = multiprocessing.Semaphore(1)
    try:
        maps = Path("/proc/self/maps").read_text()
        assert "/dev/shm/sem." in maps
        assert "(deleted)" in maps
        assert _mapped_openssl_paths() == baseline
        assert capture_current_tls_websocket_driver_policy_v49b() == current_policy
    finally:
        del semaphore


def test_deleted_openssl_candidate_still_fails_closed() -> None:
    raw = Path("/proc/self/maps").read_bytes()
    raw += b"70000000-70001000 r--p 00000000 00:00 12345 /tmp/libssl.so.3 (deleted)\n"

    with pytest.raises(
        RuntimeArtifactAuthorityV49BError,
        match="OPENSSL_LIBSSL mapping was deleted",
    ):
        _mapped_openssl_paths_from_maps(raw)
