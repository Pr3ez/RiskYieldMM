from __future__ import annotations

import errno
import hashlib
import importlib.machinery
import importlib.util
import os
import shutil
import subprocess
import sys
import threading
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

import pytest

from riskyieldmm.trading import (
    physical_transport_capacity_source_observation_v49f as source_mod,
)
from riskyieldmm.trading.canonical import (
    CanonicalizationError,
    canonical_json_bytes,
    sha256_digest,
    strict_json_loads,
)
from riskyieldmm.trading.physical_transport_capacity_source_observation_v49f import (
    PinnedSourceObservationV49F,
    SourceObservationChangedV49FError,
    SourceObservationSnapshotV49F,
    SourceObservationV49FError,
)


def test_raw_v7_source_inventory_is_an_explicit_historical_successor() -> None:
    historical = source_mod.RAW_V6_ACCEPTED_CRITICAL_SOURCE_MODULES_V49F
    current = source_mod.RAW_V7_CRITICAL_SOURCE_MODULES_V49F

    assert len(historical) == 40
    assert len(current) == 41
    assert historical == tuple(sorted(set(historical)))
    assert current == tuple(sorted(set(current)))
    assert set(current) - set(historical) == {
        "riskyieldmm.trading.physical_transport_capacity_lifecycle_v49f"
    }
    assert (
        source_mod.RAW_V6_ACCEPTED_CRITICAL_SOURCE_INVENTORY_ID_V49F
        == sha256_digest(
            {
                "domain": ("RiskYieldMMA2MRawV6AcceptedCriticalSourceInventoryV4_9F"),
                "module_names": list(historical),
            }
        )
    )
    assert source_mod.CRITICAL_SOURCE_MODULES_V49F is current
    assert source_mod.RAW_V7_CRITICAL_SOURCE_INVENTORY_ID_V49F == sha256_digest(
        {
            "domain": "RiskYieldMMA2MRawV7CriticalSourceInventoryV4_9F",
            "module_names": list(current),
        }
    )


def test_historical_raw_v6_source_snapshot_replays_after_inventory_revision() -> None:
    members = tuple(
        source_mod.SourceMemberObservationV49F(
            relative_path=f"historical/{index:02d}.py",
            roles=tuple(
                sorted(
                    (
                        f"CRITICAL_MODULE:{module_name}",
                        f"LOADED_MODULE:{module_name}",
                    )
                )
            ),
            size_bytes=1,
            sha256=hashlib.sha256(module_name.encode("utf-8")).hexdigest(),
            device="1",
            inode=str(index + 1),
            mode=str(0o100644),
            modified_ns="1",
            changed_ns="1",
        )
        for index, module_name in enumerate(
            source_mod.RAW_V6_ACCEPTED_CRITICAL_SOURCE_MODULES_V49F
        )
    )
    source_tree = source_mod.derive_observed_source_tree_sha256_v49f(members)
    historical = source_mod.SourceObservationSnapshotV49F(
        repository_root="/historical/riskyieldmm-v6",
        git_state=source_mod.GitSourceStateV49F(
            object_format="sha1",
            head_commit="1" * 40,
            head_tree="2" * 40,
            branch_ref="refs/heads/regression-targets",
            porcelain_v2_status_base64="",
            source_tree_clean=True,
        ),
        members=members,
        member_count=len(members),
        total_bytes=len(members),
        source_tree_sha256=source_tree,
        deployment_source_tree_sha256=source_tree,
        deployment_source_tree_matches=True,
    )
    encoded = canonical_json_bytes(historical.as_dict())

    replay = source_mod.SourceObservationSnapshotV49F.from_mapping(
        strict_json_loads(encoded)
    )

    assert replay == historical
    assert replay.member_count == 40
    assert canonical_json_bytes(replay.as_dict()) == encoded


def _git(root: Path, *arguments: str) -> bytes:
    return subprocess.run(
        ("git", *arguments),
        cwd=root,
        check=True,
        capture_output=True,
        env={
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_NOSYSTEM": "1",
            "HOME": "/",
            "LANG": "C",
            "LC_ALL": "C",
            "PATH": "/usr/bin:/bin",
        },
    ).stdout


def _new_repo(tmp_path: Path, files: dict[str, bytes] | None = None) -> Path:
    root = tmp_path / "repository"
    root.mkdir(parents=True)
    _git(root, "init", "--initial-branch=main")
    _git(root, "config", "user.email", "source-observer@example.invalid")
    _git(root, "config", "user.name", "Source Observer Test")
    for relative, payload in (
        files or {"riskyieldmm/observed.py": b"VALUE = 1\n"}
    ).items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
    _git(root, "add", "--all")
    _git(root, "commit", "-m", "fixture")
    return root


def _source_module(name: str, path: Path) -> ModuleType:
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    specification = importlib.util.spec_from_loader(name, loader)
    assert specification is not None
    module = ModuleType(name)
    module.__file__ = str(path)
    module.__spec__ = specification
    return module


def _inventory(
    root: Path,
    relatives: tuple[str, ...] = ("riskyieldmm/observed.py",),
) -> tuple[Callable[[], dict[str, ModuleType]], tuple[str, ...]]:
    modules = {
        f"riskyieldmm.observed_{index}": _source_module(
            f"riskyieldmm.observed_{index}", root / relative
        )
        for index, relative in enumerate(relatives)
    }
    critical = tuple(sorted(modules))
    return lambda: dict(modules), critical


def _observe(
    root: Path,
    *,
    relatives: tuple[str, ...] = ("riskyieldmm/observed.py",),
    deployment_hash: str = "0" * 64,
    hook: Callable[[], None] | None = None,
) -> PinnedSourceObservationV49F:
    inventory, critical = _inventory(root, relatives)
    return PinnedSourceObservationV49F._open_observed_for_test(
        repository_root=str(root),
        deployment_source_tree_sha256=deployment_hash,
        module_inventory_factory=inventory,
        critical_module_names=critical,
        after_first_git_state=hook,
    )


def test_clean_snapshot_is_exact_round_trip_and_deployment_comparison(
    tmp_path: Path,
) -> None:
    root = _new_repo(tmp_path)
    with _observe(root) as preliminary:
        expected = preliminary.source_tree_sha256
        assert preliminary.snapshot.git_state.source_tree_clean is True
        assert preliminary.is_deployment_source_tree_match is False

    with _observe(root, deployment_hash=expected) as observed:
        snapshot = observed.snapshot
        assert snapshot.deployment_source_tree_matches is True
        assert snapshot.member_count == 1
        assert snapshot.total_bytes == len(b"VALUE = 1\n")
        assert snapshot.members[0].roles == (
            "CRITICAL_MODULE:riskyieldmm.observed_0",
            "LOADED_MODULE:riskyieldmm.observed_0",
        )
        assert snapshot.members[0].sha256 == hashlib.sha256(b"VALUE = 1\n").hexdigest()
        assert (
            SourceObservationSnapshotV49F.from_mapping(snapshot.as_dict()) == snapshot
        )
        observed.assert_current()


def test_dirty_porcelain_v2_bytes_are_explicit_and_stable(tmp_path: Path) -> None:
    root = _new_repo(tmp_path)
    (root / "untracked name.txt").write_text("dirty", encoding="utf-8")
    with _observe(root) as observed:
        git_state = observed.snapshot.git_state
        expected = _git(
            root,
            "--no-optional-locks",
            "-c",
            "core.fsmonitor=false",
            "-c",
            "core.untrackedCache=false",
            "status",
            "--porcelain=v2",
            "-z",
            "--untracked-files=all",
        )
        assert git_state.source_tree_clean is False
        assert git_state.status_bytes == expected
        assert git_state.from_mapping(git_state.as_dict()) == git_state


def test_caller_cannot_substitute_a_claimed_source_hash(tmp_path: Path) -> None:
    root = _new_repo(tmp_path)
    claimed = "f" * 64
    with _observe(root, deployment_hash=claimed) as observed:
        snapshot = observed.snapshot
        assert snapshot.source_tree_sha256 != claimed
        assert snapshot.deployment_source_tree_sha256 == claimed
        assert snapshot.deployment_source_tree_matches is False
        forged = snapshot.as_dict()
        forged["source_tree_sha256"] = claimed
        forged["deployment_source_tree_matches"] = True
        with pytest.raises(CanonicalizationError, match="exact observed members"):
            SourceObservationSnapshotV49F.from_mapping(forged)


def test_leaf_symlink_is_rejected(tmp_path: Path) -> None:
    root = _new_repo(tmp_path, {"riskyieldmm/real.py": b"VALUE = 1\n"})
    link = root / "riskyieldmm/observed.py"
    link.symlink_to("real.py")
    _git(root, "add", "--all")
    _git(root, "commit", "-m", "leaf link")
    with pytest.raises(SourceObservationV49FError, match="opened safely"):
        _observe(root)


def test_parent_symlink_is_rejected(tmp_path: Path) -> None:
    root = _new_repo(tmp_path, {"actual/observed.py": b"VALUE = 1\n"})
    (root / "riskyieldmm").symlink_to("actual", target_is_directory=True)
    _git(root, "add", "--all")
    _git(root, "commit", "-m", "parent link")
    with pytest.raises(SourceObservationV49FError, match="opened safely"):
        _observe(root)


def test_same_byte_path_replacement_is_detected_by_inode(tmp_path: Path) -> None:
    root = _new_repo(tmp_path)
    observed = _observe(root)
    path = root / "riskyieldmm/observed.py"
    replacement = path.with_suffix(".replacement")
    replacement.write_bytes(path.read_bytes())
    os.replace(replacement, path)
    try:
        with pytest.raises(SourceObservationChangedV49FError, match="source member"):
            observed.assert_current()
    finally:
        observed.close()


def test_in_place_mutation_is_detected(tmp_path: Path) -> None:
    root = _new_repo(tmp_path)
    observed = _observe(root)
    (root / "riskyieldmm/observed.py").write_bytes(b"VALUE = 2\n")
    try:
        with pytest.raises(SourceObservationChangedV49FError):
            observed.assert_current()
    finally:
        observed.close()


def test_git_status_race_hook_fails_closed(tmp_path: Path) -> None:
    root = _new_repo(tmp_path)

    def mutate_after_first_git_state() -> None:
        (root / "race.txt").write_text("appeared", encoding="utf-8")

    with pytest.raises(SourceObservationChangedV49FError, match="Git source state"):
        _observe(root, hook=mutate_after_first_git_state)


def test_fixed_file_total_member_and_status_bounds_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    file_root = _new_repo(tmp_path / "file", {"riskyieldmm/observed.py": b"12345"})
    monkeypatch.setattr(source_mod, "_MAX_SOURCE_FILE_BYTES", 4)
    with pytest.raises(SourceObservationV49FError, match="fixed byte bound"):
        _observe(file_root)

    monkeypatch.setattr(source_mod, "_MAX_SOURCE_FILE_BYTES", 8 * 1024 * 1024)
    total_root = _new_repo(
        tmp_path / "total",
        {
            "riskyieldmm/a.py": b"aa",
            "riskyieldmm/b.py": b"bb",
        },
    )
    monkeypatch.setattr(source_mod, "_MAX_SOURCE_TOTAL_BYTES", 3)
    with pytest.raises(SourceObservationV49FError, match="total byte bound"):
        _observe(total_root, relatives=("riskyieldmm/a.py", "riskyieldmm/b.py"))

    monkeypatch.setattr(source_mod, "_MAX_SOURCE_TOTAL_BYTES", 64 * 1024 * 1024)
    monkeypatch.setattr(source_mod, "_MAX_SOURCE_MEMBERS", 1)
    with pytest.raises(SourceObservationV49FError, match="member bound"):
        _observe(total_root, relatives=("riskyieldmm/a.py", "riskyieldmm/b.py"))

    monkeypatch.setattr(source_mod, "_MAX_SOURCE_MEMBERS", 512)
    status_root = _new_repo(tmp_path / "status")
    (status_root / "untracked.txt").write_text("x", encoding="utf-8")
    monkeypatch.setattr(source_mod, "_MAX_GIT_STATUS_BYTES", 4)
    with pytest.raises(
        SourceObservationV49FError, match="Git status.*fixed byte bound"
    ):
        _observe(status_root)


def test_partial_failure_closes_already_retained_member_descriptors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _new_repo(
        tmp_path,
        {"riskyieldmm/a.py": b"a\n", "riskyieldmm/b.py": b"b\n"},
    )
    retained_descriptors: list[int] = []
    original = source_mod._PinnedSourceMemberV49F.open_observed.__func__
    calls = 0

    def failing_open(cls: type, **kwargs: object):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise SourceObservationV49FError("injected second-member failure")
        member = original(cls, **kwargs)
        retained_descriptors.append(member.descriptor)
        return member

    monkeypatch.setattr(
        source_mod._PinnedSourceMemberV49F,
        "open_observed",
        classmethod(failing_open),
    )
    with pytest.raises(SourceObservationV49FError, match="injected"):
        _observe(root, relatives=("riskyieldmm/a.py", "riskyieldmm/b.py"))
    assert retained_descriptors
    with pytest.raises(OSError) as error:
        os.fstat(retained_descriptors[0])
    assert error.value.errno == errno.EBADF


def test_capability_is_thread_bound_and_close_is_terminal(tmp_path: Path) -> None:
    root = _new_repo(tmp_path)
    observed = _observe(root)
    failures: list[BaseException] = []

    def use_from_other_thread() -> None:
        try:
            observed.assert_current()
        except BaseException as exc:  # test captures the exact cross-thread failure
            failures.append(exc)

    thread = threading.Thread(target=use_from_other_thread)
    thread.start()
    thread.join()
    assert len(failures) == 1
    assert isinstance(failures[0], SourceObservationChangedV49FError)
    observed.assert_current()
    observed.close()
    observed.close()
    with pytest.raises(SourceObservationChangedV49FError, match="process/thread"):
        observed.assert_current()


@pytest.mark.skipif(not hasattr(os, "fork"), reason="requires POSIX fork")
def test_capability_is_invalidated_in_fork_child_but_parent_remains_live(
    tmp_path: Path,
) -> None:
    root = _new_repo(tmp_path)
    observed = _observe(root)
    read_fd, write_fd = os.pipe()
    child = os.fork()
    if child == 0:  # pragma: no cover - asserted through pipe and wait status
        os.close(read_fd)
        try:
            observed.assert_current()
        except SourceObservationChangedV49FError:
            os.write(write_fd, b"invalid")
            os._exit(0)
        except BaseException:
            os._exit(2)
        os._exit(3)
    os.close(write_fd)
    try:
        message = os.read(read_fd, 32)
        _, status = os.waitpid(child, 0)
        assert os.waitstatus_to_exitcode(status) == 0
        assert message == b"invalid"
        observed.assert_current()
    finally:
        os.close(read_fd)
        observed.close()


def test_module_origin_loader_and_root_path_contracts_are_fail_closed(
    tmp_path: Path,
) -> None:
    root = _new_repo(tmp_path)
    path = root / "riskyieldmm/observed.py"
    module = _source_module("riskyieldmm.bad", path)
    assert module.__spec__ is not None
    module.__spec__.origin = str(path.with_name("different.py"))
    with pytest.raises(SourceObservationV49FError, match="__file__ differs"):
        PinnedSourceObservationV49F._open_observed_for_test(
            repository_root=str(root),
            deployment_source_tree_sha256="0" * 64,
            module_inventory_factory=lambda: {"riskyieldmm.bad": module},
            critical_module_names=("riskyieldmm.bad",),
        )

    module = _source_module("riskyieldmm.bad", path)
    assert module.__spec__ is not None
    module.__spec__.loader = object()
    with pytest.raises(SourceObservationV49FError, match="SourceFileLoader"):
        PinnedSourceObservationV49F._open_observed_for_test(
            repository_root=str(root),
            deployment_source_tree_sha256="0" * 64,
            module_inventory_factory=lambda: {"riskyieldmm.bad": module},
            critical_module_names=("riskyieldmm.bad",),
        )

    class ForeignSourceLoader(importlib.machinery.SourceFileLoader):
        pass

    module = _source_module("riskyieldmm.bad", path)
    assert module.__spec__ is not None
    module.__spec__.loader = ForeignSourceLoader("riskyieldmm.bad", str(path))
    with pytest.raises(SourceObservationV49FError, match="supported SourceFileLoader"):
        PinnedSourceObservationV49F._open_observed_for_test(
            repository_root=str(root),
            deployment_source_tree_sha256="0" * 64,
            module_inventory_factory=lambda: {"riskyieldmm.bad": module},
            critical_module_names=("riskyieldmm.bad",),
        )

    module = _source_module("riskyieldmm.bad", path)
    assert module.__spec__ is not None
    module.__spec__.name = "riskyieldmm.foreign"
    with pytest.raises(SourceObservationV49FError, match="names differ"):
        PinnedSourceObservationV49F._open_observed_for_test(
            repository_root=str(root),
            deployment_source_tree_sha256="0" * 64,
            module_inventory_factory=lambda: {"riskyieldmm.bad": module},
            critical_module_names=("riskyieldmm.bad",),
        )

    module = _source_module("riskyieldmm.bad", path)
    assert module.__spec__ is not None
    module.__spec__.loader = importlib.machinery.SourceFileLoader(
        "riskyieldmm.bad", str(path.with_name("foreign.py"))
    )
    with pytest.raises(SourceObservationV49FError, match="loader identity differs"):
        PinnedSourceObservationV49F._open_observed_for_test(
            repository_root=str(root),
            deployment_source_tree_sha256="0" * 64,
            module_inventory_factory=lambda: {"riskyieldmm.bad": module},
            critical_module_names=("riskyieldmm.bad",),
        )

    alias = tmp_path / "repository-alias"
    alias.symlink_to(root, target_is_directory=True)
    with pytest.raises(SourceObservationV49FError, match="without symlinks"):
        PinnedSourceObservationV49F._open_observed_for_test(
            repository_root=str(alias),
            deployment_source_tree_sha256="0" * 64,
            module_inventory_factory=lambda: {},
            critical_module_names=("riskyieldmm.bad",),
        )


def test_snapshot_rejects_unknown_fields_and_noncanonical_member_order(
    tmp_path: Path,
) -> None:
    root = _new_repo(
        tmp_path,
        {"riskyieldmm/a.py": b"a\n", "riskyieldmm/b.py": b"b\n"},
    )
    with _observe(root, relatives=("riskyieldmm/a.py", "riskyieldmm/b.py")) as observed:
        payload = observed.snapshot.as_dict()
        payload["unknown"] = "field"
        with pytest.raises(CanonicalizationError, match="unknown"):
            SourceObservationSnapshotV49F.from_mapping(payload)

        payload = observed.snapshot.as_dict()
        payload["members"] = list(reversed(payload["members"]))
        with pytest.raises(CanonicalizationError, match="path-sorted"):
            SourceObservationSnapshotV49F.from_mapping(payload)


@pytest.mark.parametrize(
    "field", ("device", "inode", "mode", "modified_ns", "changed_ns")
)
def test_source_member_rejects_oversized_unsigned_text_before_integer_conversion(
    tmp_path: Path,
    field: str,
) -> None:
    root = _new_repo(tmp_path)
    with _observe(root) as observed:
        payload = observed.snapshot.as_dict()
        payload["members"][0][field] = "9" * 10_000
        with pytest.raises(
            CanonicalizationError,
            match="bounded canonical unsigned text",
        ):
            SourceObservationSnapshotV49F.from_mapping(payload)


def test_module_file_outside_repository_is_rejected(tmp_path: Path) -> None:
    root = _new_repo(tmp_path)
    outside = tmp_path / "outside.py"
    outside.write_text("VALUE = 1\n", encoding="utf-8")
    module = _source_module("riskyieldmm.outside", outside)
    with pytest.raises(SourceObservationV49FError, match="outside repository"):
        PinnedSourceObservationV49F._open_observed_for_test(
            repository_root=str(root),
            deployment_source_tree_sha256="0" * 64,
            module_inventory_factory=lambda: {"riskyieldmm.outside": module},
            critical_module_names=("riskyieldmm.outside",),
        )


def test_observer_requires_normalized_absolute_repository_root(tmp_path: Path) -> None:
    root = _new_repo(tmp_path)
    inventory, critical = _inventory(root)
    with pytest.raises(SourceObservationV49FError, match="normalized absolute"):
        PinnedSourceObservationV49F._open_observed_for_test(
            repository_root="relative/repository",
            deployment_source_tree_sha256="0" * 64,
            module_inventory_factory=inventory,
            critical_module_names=critical,
        )


def test_root_path_replacement_is_detected(tmp_path: Path) -> None:
    root = _new_repo(tmp_path)
    observed = _observe(root)
    moved = tmp_path / "moved-repository"
    root.rename(moved)
    shutil.copytree(moved, root)
    try:
        with pytest.raises(SourceObservationChangedV49FError, match="root path"):
            observed.assert_current()
    finally:
        observed.close()


def test_fileless_loaded_riskyieldmm_module_is_not_omitted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    name = "riskyieldmm.synthetic_fileless_extra"
    module = ModuleType(name)
    monkeypatch.setitem(sys.modules, name, module)
    with pytest.raises(SourceObservationV49FError, match="outside the frozen"):
        source_mod._resolve_production_module_inventory()  # noqa: SLF001
