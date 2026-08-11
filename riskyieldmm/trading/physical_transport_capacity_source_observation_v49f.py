"""Retained local source observation for the V4.9F capacity campaign.

The observer makes the exact source files visible to the running RiskYieldMM
process authoritative.  Git metadata is captured twice as descriptive state;
it is never treated as proof that the bytes loaded from the filesystem match a
commit.  Every selected source path is instead opened beneath one retained
repository directory descriptor, without following any path-component
symlink, hashed from that descriptor, reopened, and retained for later checks.

The path walk follows the POSIX/Linux ``openat(2)`` capability pattern and uses
``O_NOFOLLOW`` and ``O_CLOEXEC`` at every component.  ``pread(2)`` plus
pre/post ``fstat(2)`` brackets each bounded hash.  Git's porcelain-v2 ``-z``
format is retained byte-for-byte as base64 because filenames are not required
to be UTF-8.  These are cooperative local-process controls, not verified boot,
IMA, fs-verity, remote attestation, or a defence against a privileged attacker.

Primary specifications:

* Linux ``open(2)`` / ``openat(2)`` and ``pread(2)`` manual pages;
* Git ``status --porcelain=v2 -z`` and ``rev-parse --show-object-format``;
* Python's ``ModuleSpec.origin``, ``module.__file__``, and
  ``SourceFileLoader`` import machinery contracts.

This module deliberately imports neither the measurement nor transport runtime
modules.  Critical module names are strings and are resolved only when an
observation is explicitly requested.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import importlib
import importlib.machinery
import os
import posixpath
import re
import selectors
import shutil
import stat
import subprocess
import sys
import threading
import time
import weakref
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import ModuleType
from typing import Any, ClassVar, Final

from .canonical import (
    CANONICALIZATION_VERSION,
    CanonicalizationError,
    canonical_hash,
    canonical_identifier,
    canonical_safe_int,
    require_exact_keys,
    sha256_digest,
)

SOURCE_OBSERVATION_SCHEMA_VERSION_V49F: Final = (
    "riskyieldmm_physical_transport_capacity_source_observation_v4_9f"
)

_GIT_STATE_DOMAIN: Final = "RiskYieldMMCapacityGitSourceStateV49F"
_MEMBER_DOMAIN: Final = "RiskYieldMMCapacitySourceMemberObservationV49F"
_SOURCE_TREE_DOMAIN: Final = "RiskYieldMMCapacityObservedSourceTreeV49F"
_OBSERVATION_DOMAIN: Final = "RiskYieldMMCapacitySourceObservationV49F"

# This is the versioned release-source inventory shared by deployment builders
# and the live observer.  Import timing is deliberately excluded: every member
# is loaded in this exact inventory, and any loaded RiskYieldMM module outside
# it fails closed pending an explicit inventory/schema revision.
RAW_V6_ACCEPTED_CRITICAL_SOURCE_MODULES_V49F: Final[tuple[str, ...]] = (
    "riskyieldmm",
    "riskyieldmm.trading",
    "riskyieldmm.trading.calendar_actions",
    "riskyieldmm.trading.canonical",
    "riskyieldmm.trading.chronyd_provenance_v48b",
    "riskyieldmm.trading.contracts",
    "riskyieldmm.trading.evidence",
    "riskyieldmm.trading.ledger",
    "riskyieldmm.trading.ledger_cli",
    "riskyieldmm.trading.ledger_signing",
    "riskyieldmm.trading.manifests",
    "riskyieldmm.trading.operational_artifact_loading_v4",
    "riskyieldmm.trading.operational_manifests_v4",
    "riskyieldmm.trading.operational_runtime_artifacts_v49b",
    "riskyieldmm.trading.physical_evidence_v4",
    "riskyieldmm.trading.physical_gate_v4",
    "riskyieldmm.trading.physical_health_v4",
    "riskyieldmm.trading.physical_market_data",
    "riskyieldmm.trading.physical_projection_v4",
    "riskyieldmm.trading.physical_selection_v4",
    "riskyieldmm.trading.physical_transport_actor_journal_v49c",
    "riskyieldmm.trading.physical_transport_actor_v49c",
    "riskyieldmm.trading.physical_transport_capacity_manifest_authority_v49f",
    "riskyieldmm.trading.physical_transport_capacity_measurement_v49f",
    "riskyieldmm.trading.physical_transport_capacity_sampler_v49f",
    "riskyieldmm.trading.physical_transport_capacity_source_observation_v49f",
    "riskyieldmm.trading.physical_transport_capacity_v49f",
    "riskyieldmm.trading.physical_transport_control_runtime_v4",
    "riskyieldmm.trading.physical_transport_control_v4",
    "riskyieldmm.trading.physical_transport_lease_v4",
    "riskyieldmm.trading.physical_transport_linux_v4",
    "riskyieldmm.trading.physical_transport_owner_v4",
    "riskyieldmm.trading.physical_transport_runtime_v4",
    "riskyieldmm.trading.physical_transport_session_actor_v49c",
    "riskyieldmm.trading.physical_transport_terminal_v49c",
    "riskyieldmm.trading.physical_transport_tls_v49",
    "riskyieldmm.trading.physical_transport_v4",
    "riskyieldmm.trading.tls_trust_store_v49",
    "riskyieldmm.trading.transparency_log",
    "riskyieldmm.trading.transport_key_loading_v4",
)
RAW_V6_ACCEPTED_CRITICAL_SOURCE_INVENTORY_ID_V49F: Final[str] = sha256_digest(
    {
        "domain": "RiskYieldMMA2MRawV6AcceptedCriticalSourceInventoryV4_9F",
        "module_names": list(RAW_V6_ACCEPTED_CRITICAL_SOURCE_MODULES_V49F),
    }
)

# Raw V6's accepted checkpoint above remains a historical 40-member source
# closure.  Raw V7 adds one separately versioned lifecycle module.  The source
# snapshot already serializes every exact path, role, byte count, and digest,
# so retaining the old tuple does not mutate or reinterpret a historical V6
# snapshot.  Current collection deliberately uses the explicit V7 inventory.
RAW_V7_CRITICAL_SOURCE_MODULES_V49F: Final[tuple[str, ...]] = tuple(
    sorted(
        (
            *RAW_V6_ACCEPTED_CRITICAL_SOURCE_MODULES_V49F,
            "riskyieldmm.trading.physical_transport_capacity_lifecycle_v49f",
        )
    )
)
RAW_V7_CRITICAL_SOURCE_INVENTORY_ID_V49F: Final[str] = sha256_digest(
    {
        "domain": "RiskYieldMMA2MRawV7CriticalSourceInventoryV4_9F",
        "module_names": list(RAW_V7_CRITICAL_SOURCE_MODULES_V49F),
    }
)

# Preserve the established collector name for callers while making its current
# release profile explicit.  Historical artifact replay never consults this
# process-local constant; it validates the members embedded in the snapshot.
CRITICAL_SOURCE_MODULES_V49F: Final[tuple[str, ...]] = (
    RAW_V7_CRITICAL_SOURCE_MODULES_V49F
)

_MAX_SOURCE_MEMBERS: Final = 512
_MAX_SOURCE_FILE_BYTES: Final = 8 * 1024 * 1024
_MAX_SOURCE_TOTAL_BYTES: Final = 64 * 1024 * 1024
_MAX_GIT_STATUS_BYTES: Final = 2 * 1024 * 1024
_MAX_GIT_STDOUT_BYTES: Final = _MAX_GIT_STATUS_BYTES + 4096
_MAX_GIT_STDERR_BYTES: Final = 64 * 1024
_GIT_TIMEOUT_SECONDS: Final = 10.0
_READ_CHUNK_BYTES: Final = 128 * 1024
_SUBPROCESS_READ_BYTES: Final = 64 * 1024
_MAX_UINT_TEXT_DIGITS: Final = 39
_UINT_TEXT_RE: Final = re.compile(r"^(?:0|[1-9][0-9]*)$")
_HEX_OID_RE: Final = re.compile(r"^[0-9a-f]+$")


class SourceObservationV49FError(RuntimeError):
    """A complete bounded local source observation could not be established."""


class SourceObservationChangedV49FError(SourceObservationV49FError):
    """The observed source, Git state, path, module closure, or context changed."""


_PINNED_SOURCE_FORK_GUARDS: weakref.WeakSet[Any] = weakref.WeakSet()


def _invalidate_pinned_sources_in_fork_child() -> None:
    for item in tuple(_PINNED_SOURCE_FORK_GUARDS):
        item._invalidate_in_fork_child()  # noqa: SLF001


os.register_at_fork(after_in_child=_invalidate_pinned_sources_in_fork_child)


def _canonical_uint_text(value: object, *, field: str) -> str:
    if type(value) is int:
        if value < 0 or value >= 10**_MAX_UINT_TEXT_DIGITS:
            raise CanonicalizationError(
                f"{field} must be bounded canonical unsigned text"
            )
        text = str(value)
    else:
        text = value
    if (
        type(text) is not str
        or len(text) > _MAX_UINT_TEXT_DIGITS
        or _UINT_TEXT_RE.fullmatch(text) is None
    ):
        raise CanonicalizationError(f"{field} must be bounded canonical unsigned text")
    return text


def _normalized_absolute_path(value: os.PathLike[str] | str, *, field: str) -> str:
    try:
        path = os.fspath(value)
    except TypeError as exc:
        raise SourceObservationV49FError(f"{field} is not path-like") from exc
    if type(path) is not str or not path or "\x00" in path:
        raise SourceObservationV49FError(f"{field} must be an exact text path")
    try:
        canonical_identifier(path, field=field, maximum=4096)
    except CanonicalizationError as exc:
        raise SourceObservationV49FError(str(exc)) from exc
    if not path.startswith("/") or posixpath.normpath(path) != path:
        raise SourceObservationV49FError(
            f"{field} must be a normalized absolute POSIX path"
        )
    return path


def _canonical_relative_path(value: object, *, field: str) -> str:
    path = canonical_identifier(value, field=field, maximum=4096)
    if path.startswith("/") or posixpath.normpath(path) != path or path in {".", ".."}:
        raise CanonicalizationError(
            f"{field} must be a normalized repository-relative POSIX path"
        )
    if any(component in {"", ".", ".."} for component in path.split("/")):
        raise CanonicalizationError(f"{field} contains an unsafe path component")
    return path


def _exact_bool(value: object, *, field: str) -> bool:
    if type(value) is not bool:
        raise CanonicalizationError(f"{field} must be an exact boolean")
    return value


def _decode_canonical_base64(value: object, *, field: str) -> bytes:
    if type(value) is not str:
        raise CanonicalizationError(f"{field} must be an exact string")
    text = value
    if len(text) > 4 * _MAX_GIT_STATUS_BYTES:
        raise CanonicalizationError(f"{field} exceeds its encoded byte bound")
    # The canonical base64 of an empty clean status is itself the empty string.
    # For non-empty values the decoder below rejects whitespace and controls.
    try:
        raw = base64.b64decode(text, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise CanonicalizationError(f"{field} is not valid base64") from exc
    if base64.b64encode(raw).decode("ascii") != text:
        raise CanonicalizationError(f"{field} is not canonical base64")
    if len(raw) > _MAX_GIT_STATUS_BYTES:
        raise CanonicalizationError(f"{field} exceeds the Git-status byte bound")
    return raw


def _git_oid(value: object, *, field: str, object_format: str) -> str:
    text = canonical_identifier(value, field=field, maximum=64)
    length = 40 if object_format == "sha1" else 64
    if len(text) != length or _HEX_OID_RE.fullmatch(text) is None:
        raise CanonicalizationError(
            f"{field} is not a lowercase {object_format} object identifier"
        )
    return text


@dataclass(frozen=True, slots=True, kw_only=True)
class GitSourceStateV49F:
    object_format: str
    head_commit: str
    head_tree: str
    branch_ref: str | None
    porcelain_v2_status_base64: str
    source_tree_clean: bool
    git_state_id: str | None = None

    _KEYS: ClassVar[frozenset[str]] = frozenset(
        {
            "object_format",
            "head_commit",
            "head_tree",
            "branch_ref",
            "porcelain_v2_status_base64",
            "source_tree_clean",
            "git_state_id",
        }
    )

    def __post_init__(self) -> None:
        object_format = canonical_identifier(
            self.object_format, field="object_format", maximum=8
        )
        if object_format not in {"sha1", "sha256"}:
            raise CanonicalizationError("object_format must be sha1 or sha256")
        object.__setattr__(self, "object_format", object_format)
        object.__setattr__(
            self,
            "head_commit",
            _git_oid(
                self.head_commit, field="head_commit", object_format=object_format
            ),
        )
        object.__setattr__(
            self,
            "head_tree",
            _git_oid(self.head_tree, field="head_tree", object_format=object_format),
        )
        if self.branch_ref is not None:
            branch = canonical_identifier(
                self.branch_ref, field="branch_ref", maximum=1024
            )
            if not branch.startswith("refs/heads/"):
                raise CanonicalizationError(
                    "branch_ref must be a full local branch ref"
                )
            object.__setattr__(self, "branch_ref", branch)
        status = _decode_canonical_base64(
            self.porcelain_v2_status_base64,
            field="porcelain_v2_status_base64",
        )
        clean = _exact_bool(self.source_tree_clean, field="source_tree_clean")
        if clean != (status == b""):
            raise CanonicalizationError(
                "source_tree_clean differs from exact porcelain-v2 status bytes"
            )
        identity = sha256_digest(
            {
                "branch_ref": self.branch_ref,
                "canonicalization_version": CANONICALIZATION_VERSION,
                "domain": _GIT_STATE_DOMAIN,
                "head_commit": self.head_commit,
                "head_tree": self.head_tree,
                "object_format": self.object_format,
                "porcelain_v2_status_base64": self.porcelain_v2_status_base64,
                "schema_version": SOURCE_OBSERVATION_SCHEMA_VERSION_V49F,
                "source_tree_clean": self.source_tree_clean,
            }
        )
        if self.git_state_id is not None and self.git_state_id != identity:
            raise CanonicalizationError("git_state_id differs from canonical content")
        object.__setattr__(self, "git_state_id", identity)

    @property
    def status_bytes(self) -> bytes:
        return _decode_canonical_base64(
            self.porcelain_v2_status_base64,
            field="porcelain_v2_status_base64",
        )

    def _as_dict_unchecked(self) -> dict[str, Any]:
        return {
            "branch_ref": self.branch_ref,
            "git_state_id": self.git_state_id,
            "head_commit": self.head_commit,
            "head_tree": self.head_tree,
            "object_format": self.object_format,
            "porcelain_v2_status_base64": self.porcelain_v2_status_base64,
            "source_tree_clean": self.source_tree_clean,
        }

    def as_dict(self) -> dict[str, Any]:
        checked = type(self)(**self._as_dict_unchecked())
        if checked != self:
            raise CanonicalizationError("Git source state was mutated")
        return self._as_dict_unchecked()

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> GitSourceStateV49F:
        require_exact_keys(payload, expected=cls._KEYS, context=cls.__name__)
        return cls(**{name: payload[name] for name in cls._KEYS})


@dataclass(frozen=True, slots=True, kw_only=True)
class SourceMemberObservationV49F:
    relative_path: str
    roles: tuple[str, ...]
    size_bytes: int
    sha256: str
    device: str
    inode: str
    mode: str
    modified_ns: str
    changed_ns: str
    member_id: str | None = None

    _KEYS: ClassVar[frozenset[str]] = frozenset(
        {
            "relative_path",
            "roles",
            "size_bytes",
            "sha256",
            "device",
            "inode",
            "mode",
            "modified_ns",
            "changed_ns",
            "member_id",
        }
    )

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "relative_path",
            _canonical_relative_path(self.relative_path, field="relative_path"),
        )
        if type(self.roles) is not tuple or not self.roles:
            raise CanonicalizationError("roles must be a non-empty exact tuple")
        roles = tuple(
            canonical_identifier(role, field="roles", maximum=1024)
            for role in self.roles
        )
        if roles != tuple(sorted(set(roles))):
            raise CanonicalizationError("roles must be sorted and unique")
        object.__setattr__(self, "roles", roles)
        object.__setattr__(
            self,
            "size_bytes",
            canonical_safe_int(
                self.size_bytes,
                field="size_bytes",
                minimum=0,
                maximum=_MAX_SOURCE_FILE_BYTES,
            ),
        )
        object.__setattr__(self, "sha256", canonical_hash(self.sha256, field="sha256"))
        for name in ("device", "inode", "mode", "modified_ns", "changed_ns"):
            object.__setattr__(
                self,
                name,
                _canonical_uint_text(getattr(self, name), field=name),
            )
        identity = sha256_digest(
            {
                "canonicalization_version": CANONICALIZATION_VERSION,
                "changed_ns": self.changed_ns,
                "device": self.device,
                "domain": _MEMBER_DOMAIN,
                "inode": self.inode,
                "mode": self.mode,
                "modified_ns": self.modified_ns,
                "relative_path": self.relative_path,
                "roles": list(self.roles),
                "schema_version": SOURCE_OBSERVATION_SCHEMA_VERSION_V49F,
                "sha256": self.sha256,
                "size_bytes": self.size_bytes,
            }
        )
        if self.member_id is not None and self.member_id != identity:
            raise CanonicalizationError("member_id differs from canonical content")
        object.__setattr__(self, "member_id", identity)

    def _as_dict_unchecked(self) -> dict[str, Any]:
        return {
            "changed_ns": self.changed_ns,
            "device": self.device,
            "inode": self.inode,
            "member_id": self.member_id,
            "mode": self.mode,
            "modified_ns": self.modified_ns,
            "relative_path": self.relative_path,
            "roles": list(self.roles),
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
        }

    def as_dict(self) -> dict[str, Any]:
        checked = type(self)(
            changed_ns=self.changed_ns,
            device=self.device,
            inode=self.inode,
            member_id=self.member_id,
            mode=self.mode,
            modified_ns=self.modified_ns,
            relative_path=self.relative_path,
            roles=self.roles,
            sha256=self.sha256,
            size_bytes=self.size_bytes,
        )
        if checked != self:
            raise CanonicalizationError("source member observation was mutated")
        return self._as_dict_unchecked()

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> SourceMemberObservationV49F:
        require_exact_keys(payload, expected=cls._KEYS, context=cls.__name__)
        roles = payload["roles"]
        if not isinstance(roles, Sequence) or isinstance(
            roles, (str, bytes, bytearray)
        ):
            raise CanonicalizationError("roles must be a sequence")
        return cls(
            **{
                **{name: payload[name] for name in cls._KEYS if name != "roles"},
                "roles": tuple(roles),
            }
        )


def derive_observed_source_tree_sha256_v49f(
    members: Sequence[SourceMemberObservationV49F],
) -> str:
    """Derive a portable path/content tree, excluding host-specific inode state."""

    if isinstance(members, (str, bytes, bytearray)):
        raise CanonicalizationError("members must be a sequence")
    normalized = tuple(members)
    if not normalized or any(
        type(member) is not SourceMemberObservationV49F for member in normalized
    ):
        raise CanonicalizationError("members must contain exact source records")
    paths = tuple(member.relative_path for member in normalized)
    if paths != tuple(sorted(set(paths))):
        raise CanonicalizationError("source member paths must be sorted and unique")
    return sha256_digest(
        {
            "canonicalization_version": CANONICALIZATION_VERSION,
            "domain": _SOURCE_TREE_DOMAIN,
            "members": [
                {
                    "relative_path": member.relative_path,
                    "sha256": member.sha256,
                    "size_bytes": member.size_bytes,
                }
                for member in normalized
            ],
            "schema_version": SOURCE_OBSERVATION_SCHEMA_VERSION_V49F,
        }
    )


@dataclass(frozen=True, slots=True, kw_only=True)
class SourceObservationSnapshotV49F:
    repository_root: str
    git_state: GitSourceStateV49F
    members: tuple[SourceMemberObservationV49F, ...]
    member_count: int
    total_bytes: int
    source_tree_sha256: str
    deployment_source_tree_sha256: str
    deployment_source_tree_matches: bool
    source_observation_id: str | None = None
    schema_version: str = SOURCE_OBSERVATION_SCHEMA_VERSION_V49F

    _KEYS: ClassVar[frozenset[str]] = frozenset(
        {
            "repository_root",
            "git_state",
            "members",
            "member_count",
            "total_bytes",
            "source_tree_sha256",
            "deployment_source_tree_sha256",
            "deployment_source_tree_matches",
            "source_observation_id",
            "schema_version",
        }
    )

    def __post_init__(self) -> None:
        try:
            root = _normalized_absolute_path(
                self.repository_root, field="repository_root"
            )
        except SourceObservationV49FError as exc:
            raise CanonicalizationError(str(exc)) from exc
        object.__setattr__(self, "repository_root", root)
        if type(self.git_state) is not GitSourceStateV49F:
            raise CanonicalizationError("git_state must be exact")
        if type(self.members) is not tuple or not self.members:
            raise CanonicalizationError("members must be a non-empty exact tuple")
        if any(type(item) is not SourceMemberObservationV49F for item in self.members):
            raise CanonicalizationError("members contain an unsupported record")
        paths = tuple(item.relative_path for item in self.members)
        if paths != tuple(sorted(set(paths))):
            raise CanonicalizationError("members must be path-sorted and unique")
        count = canonical_safe_int(
            self.member_count,
            field="member_count",
            minimum=1,
            maximum=_MAX_SOURCE_MEMBERS,
        )
        if count != len(self.members):
            raise CanonicalizationError("member_count differs from members")
        total = canonical_safe_int(
            self.total_bytes,
            field="total_bytes",
            minimum=0,
            maximum=_MAX_SOURCE_TOTAL_BYTES,
        )
        if total != sum(member.size_bytes for member in self.members):
            raise CanonicalizationError("total_bytes differs from members")
        source_tree = canonical_hash(
            self.source_tree_sha256, field="source_tree_sha256"
        )
        expected_tree = derive_observed_source_tree_sha256_v49f(self.members)
        if source_tree != expected_tree:
            raise CanonicalizationError(
                "source_tree_sha256 differs from exact observed members"
            )
        deployment_tree = canonical_hash(
            self.deployment_source_tree_sha256,
            field="deployment_source_tree_sha256",
        )
        matches = _exact_bool(
            self.deployment_source_tree_matches,
            field="deployment_source_tree_matches",
        )
        if matches != (deployment_tree == source_tree):
            raise CanonicalizationError(
                "deployment_source_tree_matches differs from compared hashes"
            )
        if self.schema_version != SOURCE_OBSERVATION_SCHEMA_VERSION_V49F:
            raise CanonicalizationError("source observation schema version differs")
        identity = sha256_digest(
            {
                "canonicalization_version": CANONICALIZATION_VERSION,
                "deployment_source_tree_matches": matches,
                "deployment_source_tree_sha256": deployment_tree,
                "domain": _OBSERVATION_DOMAIN,
                "git_state": self.git_state.as_dict(),
                "member_count": count,
                "members": [member.as_dict() for member in self.members],
                "repository_root": root,
                "schema_version": self.schema_version,
                "source_tree_sha256": source_tree,
                "total_bytes": total,
            }
        )
        if (
            self.source_observation_id is not None
            and self.source_observation_id != identity
        ):
            raise CanonicalizationError(
                "source_observation_id differs from canonical content"
            )
        object.__setattr__(self, "source_tree_sha256", source_tree)
        object.__setattr__(self, "deployment_source_tree_sha256", deployment_tree)
        object.__setattr__(self, "deployment_source_tree_matches", matches)
        object.__setattr__(self, "source_observation_id", identity)

    def _as_dict_unchecked(self) -> dict[str, Any]:
        return {
            "deployment_source_tree_matches": self.deployment_source_tree_matches,
            "deployment_source_tree_sha256": self.deployment_source_tree_sha256,
            "git_state": self.git_state.as_dict(),
            "member_count": self.member_count,
            "members": [member.as_dict() for member in self.members],
            "repository_root": self.repository_root,
            "schema_version": self.schema_version,
            "source_observation_id": self.source_observation_id,
            "source_tree_sha256": self.source_tree_sha256,
            "total_bytes": self.total_bytes,
        }

    def as_dict(self) -> dict[str, Any]:
        checked = type(self)(
            deployment_source_tree_matches=self.deployment_source_tree_matches,
            deployment_source_tree_sha256=self.deployment_source_tree_sha256,
            git_state=self.git_state,
            member_count=self.member_count,
            members=self.members,
            repository_root=self.repository_root,
            schema_version=self.schema_version,
            source_observation_id=self.source_observation_id,
            source_tree_sha256=self.source_tree_sha256,
            total_bytes=self.total_bytes,
        )
        if checked != self:
            raise CanonicalizationError("source observation snapshot was mutated")
        return self._as_dict_unchecked()

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> SourceObservationSnapshotV49F:
        require_exact_keys(payload, expected=cls._KEYS, context=cls.__name__)
        members = payload["members"]
        if not isinstance(members, Sequence) or isinstance(
            members, (str, bytes, bytearray)
        ):
            raise CanonicalizationError("members must be a sequence")
        return cls(
            repository_root=payload["repository_root"],
            git_state=GitSourceStateV49F.from_mapping(payload["git_state"]),
            members=tuple(
                SourceMemberObservationV49F.from_mapping(member) for member in members
            ),
            member_count=payload["member_count"],
            total_bytes=payload["total_bytes"],
            source_tree_sha256=payload["source_tree_sha256"],
            deployment_source_tree_sha256=payload["deployment_source_tree_sha256"],
            deployment_source_tree_matches=payload["deployment_source_tree_matches"],
            source_observation_id=payload["source_observation_id"],
            schema_version=payload["schema_version"],
        )


@dataclass(frozen=True, slots=True)
class _RetainedStatV49F:
    device: int
    inode: int
    mode: int
    size: int
    modified_ns: int
    changed_ns: int

    @classmethod
    def from_stat(cls, value: os.stat_result) -> _RetainedStatV49F:
        return cls(
            device=value.st_dev,
            inode=value.st_ino,
            mode=value.st_mode,
            size=value.st_size,
            modified_ns=value.st_mtime_ns,
            changed_ns=value.st_ctime_ns,
        )


@dataclass(frozen=True, slots=True)
class _RootIdentityV49F:
    device: int
    inode: int
    mode: int

    @classmethod
    def from_stat(cls, value: os.stat_result) -> _RootIdentityV49F:
        if not stat.S_ISDIR(value.st_mode):
            raise SourceObservationV49FError("repository root is not a directory")
        return cls(device=value.st_dev, inode=value.st_ino, mode=value.st_mode)


def _directory_open_flags() -> int:
    return os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0)


def _file_open_flags() -> int:
    return os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0)


def _make_non_inheritable(descriptor: int, *, context: str) -> None:
    os.set_inheritable(descriptor, False)
    if os.get_inheritable(descriptor):
        raise SourceObservationV49FError(f"{context} descriptor remained inheritable")


def _open_absolute_directory_no_symlinks(path: str) -> int:
    components = path.split("/")[1:]
    descriptor = os.open("/", _directory_open_flags())
    try:
        _make_non_inheritable(descriptor, context="filesystem root")
        for component in components:
            next_descriptor = os.open(
                component,
                _directory_open_flags(),
                dir_fd=descriptor,
            )
            try:
                _make_non_inheritable(next_descriptor, context="directory component")
            except BaseException:
                os.close(next_descriptor)
                raise
            os.close(descriptor)
            descriptor = next_descriptor
        _RootIdentityV49F.from_stat(os.fstat(descriptor))
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _open_relative_file(root_descriptor: int, relative_path: str) -> int:
    components = relative_path.split("/")
    descriptor = os.dup(root_descriptor)
    try:
        _make_non_inheritable(descriptor, context="repository walk")
        for component in components[:-1]:
            next_descriptor = os.open(
                component,
                _directory_open_flags(),
                dir_fd=descriptor,
            )
            try:
                _make_non_inheritable(next_descriptor, context="source parent")
            except BaseException:
                os.close(next_descriptor)
                raise
            os.close(descriptor)
            descriptor = next_descriptor
        leaf = os.open(components[-1], _file_open_flags(), dir_fd=descriptor)
        try:
            _make_non_inheritable(leaf, context="source member")
        except BaseException:
            os.close(leaf)
            raise
        return leaf
    finally:
        os.close(descriptor)


def _validate_member_stat(value: os.stat_result) -> None:
    if not stat.S_ISREG(value.st_mode):
        raise SourceObservationV49FError("source member is not a regular file")
    if value.st_size < 0 or value.st_size > _MAX_SOURCE_FILE_BYTES:
        raise SourceObservationV49FError("source member exceeds its fixed byte bound")


def _hash_descriptor(descriptor: int) -> tuple[str, _RetainedStatV49F]:
    before_raw = os.fstat(descriptor)
    _validate_member_stat(before_raw)
    before = _RetainedStatV49F.from_stat(before_raw)
    digest = hashlib.sha256()
    offset = 0
    while offset < before.size:
        chunk = os.pread(
            descriptor,
            min(_READ_CHUNK_BYTES, before.size - offset),
            offset,
        )
        if not chunk:
            raise SourceObservationChangedV49FError(
                "source member became truncated while hashing"
            )
        digest.update(chunk)
        offset += len(chunk)
    after_raw = os.fstat(descriptor)
    _validate_member_stat(after_raw)
    after = _RetainedStatV49F.from_stat(after_raw)
    if before != after or offset != after.size:
        raise SourceObservationChangedV49FError(
            "source member changed while it was being hashed"
        )
    return digest.hexdigest(), after


def _repository_relative_path(repository_root: str, origin: str) -> str:
    normalized = _normalized_absolute_path(origin, field="module origin")
    try:
        common = posixpath.commonpath((repository_root, normalized))
    except ValueError as exc:
        raise SourceObservationV49FError(
            "module origin cannot be related to repository root"
        ) from exc
    if common != repository_root or normalized == repository_root:
        raise SourceObservationV49FError("module origin is outside repository root")
    relative = posixpath.relpath(normalized, repository_root)
    try:
        return _canonical_relative_path(relative, field="module relative path")
    except CanonicalizationError as exc:
        raise SourceObservationV49FError(str(exc)) from exc


def _module_origin(module_name: str, module: ModuleType, repository_root: str) -> str:
    if type(module) is not ModuleType:
        raise SourceObservationV49FError(
            f"{module_name} did not resolve to an exact module"
        )
    specification = getattr(module, "__spec__", None)
    file_value = getattr(module, "__file__", None)
    spec_origin = None if specification is None else specification.origin
    if type(file_value) is not str or type(spec_origin) is not str:
        raise SourceObservationV49FError(
            f"{module_name} is not an exact file-backed source module"
        )
    if file_value != spec_origin:
        raise SourceObservationV49FError(
            f"{module_name} __file__ differs from __spec__.origin"
        )
    if module.__name__ != module_name or specification.name != module_name:
        raise SourceObservationV49FError(
            f"{module_name} module and specification names differ"
        )
    loader = specification.loader
    if type(loader) is not importlib.machinery.SourceFileLoader:
        raise SourceObservationV49FError(
            f"{module_name} does not use the supported SourceFileLoader"
        )
    if loader.name != module_name or loader.path != file_value:
        raise SourceObservationV49FError(
            f"{module_name} loader identity differs from its source origin"
        )
    if posixpath.splitext(file_value)[1] != ".py":
        raise SourceObservationV49FError(
            f"{module_name} does not originate from a Python source file"
        )
    return _repository_relative_path(repository_root, file_value)


def _loaded_riskyieldmm_modules() -> dict[str, ModuleType]:
    result: dict[str, ModuleType] = {}
    for name, module in tuple(sys.modules.items()):
        if name != "riskyieldmm" and not name.startswith("riskyieldmm."):
            continue
        if module is None:
            raise SourceObservationV49FError(f"{name} has an incomplete import")
        if type(module) is not ModuleType:
            raise SourceObservationV49FError(f"{name} is not an exact module")
        result[name] = module
    return result


def _resolve_production_module_inventory() -> dict[str, ModuleType]:
    result: dict[str, ModuleType] = {}
    for name in CRITICAL_SOURCE_MODULES_V49F:
        module = importlib.import_module(name)
        if type(module) is not ModuleType or sys.modules.get(name) is not module:
            raise SourceObservationV49FError(
                f"critical module {name} did not resolve exactly"
            )
        result[name] = module
    loaded = _loaded_riskyieldmm_modules()
    extras = tuple(sorted(set(loaded) - set(CRITICAL_SOURCE_MODULES_V49F)))
    if extras:
        raise SourceObservationV49FError(
            "loaded RiskYieldMM modules are outside the frozen release inventory: "
            + ", ".join(extras)
        )
    return result


def _module_roles(
    *,
    repository_root: str,
    modules: Mapping[str, ModuleType],
    critical_module_names: tuple[str, ...],
) -> dict[str, tuple[str, ...]]:
    if type(critical_module_names) is not tuple or not critical_module_names:
        raise SourceObservationV49FError(
            "critical module names must be a non-empty exact tuple"
        )
    if critical_module_names != tuple(sorted(set(critical_module_names))):
        raise SourceObservationV49FError(
            "critical module names must be sorted and unique"
        )
    roles_by_path: dict[str, set[str]] = {}
    for name in critical_module_names:
        if name not in modules:
            raise SourceObservationV49FError(f"critical module {name} is absent")
    for name in sorted(modules):
        module = modules[name]
        relative = _module_origin(name, module, repository_root)
        roles = roles_by_path.setdefault(relative, set())
        roles.add(f"LOADED_MODULE:{name}")
        if name in critical_module_names:
            roles.add(f"CRITICAL_MODULE:{name}")
    if len(roles_by_path) > _MAX_SOURCE_MEMBERS:
        raise SourceObservationV49FError("source closure exceeds its member bound")
    return {path: tuple(sorted(roles)) for path, roles in sorted(roles_by_path.items())}


def _git_environment() -> dict[str, str]:
    return {
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_OPTIONAL_LOCKS": "0",
        "HOME": "/",
        "LANG": "C",
        "LC_ALL": "C",
        "PATH": "/usr/bin:/bin",
    }


def _bounded_git_command(
    *,
    root_descriptor: int,
    arguments: tuple[str, ...],
    allowed_returncodes: frozenset[int] = frozenset({0}),
) -> tuple[int, bytes]:
    git = shutil.which("git", path="/usr/bin:/bin")
    if git is None or not git.startswith("/"):
        raise SourceObservationV49FError("an absolute system Git executable is absent")
    command = (git,) + arguments
    try:
        process = subprocess.Popen(
            command,
            cwd=f"/proc/self/fd/{root_descriptor}",
            env=_git_environment(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            close_fds=True,
        )
    except OSError as exc:
        raise SourceObservationV49FError("Git subprocess could not start") from exc
    if process.stdout is None or process.stderr is None:  # pragma: no cover
        process.kill()
        process.wait()
        raise SourceObservationV49FError("Git subprocess pipes are unavailable")
    stdout_buffer = bytearray()
    stderr_buffer = bytearray()
    streams = {
        process.stdout.fileno(): (
            process.stdout,
            stdout_buffer,
            _MAX_GIT_STDOUT_BYTES,
        ),
        process.stderr.fileno(): (
            process.stderr,
            stderr_buffer,
            _MAX_GIT_STDERR_BYTES,
        ),
    }
    selector = selectors.DefaultSelector()
    try:
        for descriptor, (stream, _, _) in streams.items():
            os.set_blocking(descriptor, False)
            selector.register(stream, selectors.EVENT_READ, descriptor)
        deadline = time.monotonic() + _GIT_TIMEOUT_SECONDS
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise SourceObservationV49FError("Git subprocess exceeded its timeout")
            events = selector.select(remaining)
            if not events:
                raise SourceObservationV49FError("Git subprocess exceeded its timeout")
            for key, _ in events:
                descriptor = key.data
                stream, output, maximum = streams[descriptor]
                chunk = os.read(
                    descriptor,
                    min(_SUBPROCESS_READ_BYTES, maximum + 1 - len(output)),
                )
                if not chunk:
                    selector.unregister(stream)
                    continue
                output.extend(chunk)
                if len(output) > maximum:
                    raise SourceObservationV49FError(
                        "Git subprocess output exceeded its fixed bound"
                    )
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise SourceObservationV49FError("Git subprocess exceeded its timeout")
        returncode = process.wait(timeout=remaining)
    except BaseException:
        if process.poll() is None:
            process.kill()
        process.wait()
        raise
    finally:
        selector.close()
        process.stdout.close()
        process.stderr.close()
    stdout = bytes(stdout_buffer)
    stderr = bytes(stderr_buffer)
    if returncode not in allowed_returncodes:
        detail = stderr.decode("utf-8", errors="replace")[:512]
        raise SourceObservationV49FError(
            f"Git command failed with status {returncode}: {detail}"
        )
    if stderr:
        detail = stderr.decode("utf-8", errors="replace")[:512]
        raise SourceObservationV49FError(f"Git command wrote stderr: {detail}")
    return returncode, stdout


def _single_git_line(raw: bytes, *, field: str, allow_empty: bool = False) -> str:
    if not raw.endswith(b"\n") or raw.count(b"\n") != 1:
        raise SourceObservationV49FError(f"Git {field} output is not one exact line")
    line = raw[:-1]
    if not line and allow_empty:
        return ""
    try:
        text = line.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise SourceObservationV49FError(
            f"Git {field} output is not strict UTF-8"
        ) from exc
    if not text:
        raise SourceObservationV49FError(f"Git {field} output is empty")
    return text


def _assert_git_repository_root(
    root_descriptor: int, root_identity: _RootIdentityV49F
) -> None:
    _, raw = _bounded_git_command(
        root_descriptor=root_descriptor,
        arguments=("rev-parse", "--show-toplevel"),
    )
    reported = _single_git_line(raw, field="repository root")
    try:
        reported_path = _normalized_absolute_path(reported, field="Git repository root")
        descriptor = _open_absolute_directory_no_symlinks(reported_path)
    except (OSError, SourceObservationV49FError) as exc:
        raise SourceObservationV49FError(
            "Git repository root cannot be opened safely"
        ) from exc
    try:
        if _RootIdentityV49F.from_stat(os.fstat(descriptor)) != root_identity:
            raise SourceObservationV49FError(
                "supplied repository root is not Git's work-tree root"
            )
    finally:
        os.close(descriptor)


def _capture_git_state(root_descriptor: int) -> GitSourceStateV49F:
    _, format_raw = _bounded_git_command(
        root_descriptor=root_descriptor,
        arguments=("rev-parse", "--show-object-format=storage"),
    )
    object_format = _single_git_line(format_raw, field="object format")
    _, head_raw = _bounded_git_command(
        root_descriptor=root_descriptor,
        arguments=("rev-parse", "--verify", "HEAD^{commit}"),
    )
    head = _single_git_line(head_raw, field="HEAD")
    _git_oid(head, field="head_commit", object_format=object_format)
    _, tree_raw = _bounded_git_command(
        root_descriptor=root_descriptor,
        arguments=("rev-parse", "--verify", f"{head}^{{tree}}"),
    )
    tree = _single_git_line(tree_raw, field="HEAD tree")
    returncode, branch_raw = _bounded_git_command(
        root_descriptor=root_descriptor,
        arguments=("symbolic-ref", "--quiet", "HEAD"),
        allowed_returncodes=frozenset({0, 1}),
    )
    branch = None if returncode == 1 else _single_git_line(branch_raw, field="branch")
    if returncode == 1 and branch_raw:
        raise SourceObservationV49FError("detached-HEAD branch output is not empty")
    _, status = _bounded_git_command(
        root_descriptor=root_descriptor,
        arguments=(
            "--no-optional-locks",
            "-c",
            "core.fsmonitor=false",
            "-c",
            "core.untrackedCache=false",
            "status",
            "--porcelain=v2",
            "-z",
            "--untracked-files=all",
        ),
    )
    if len(status) > _MAX_GIT_STATUS_BYTES:
        raise SourceObservationV49FError("Git status exceeds its fixed byte bound")
    return GitSourceStateV49F(
        object_format=object_format,
        head_commit=head,
        head_tree=tree,
        branch_ref=branch,
        porcelain_v2_status_base64=base64.b64encode(status).decode("ascii"),
        source_tree_clean=status == b"",
    )


class _PinnedSourceMemberV49F:
    def __init__(
        self,
        *,
        record: SourceMemberObservationV49F,
        descriptor: int,
        admitted_stat: _RetainedStatV49F,
    ) -> None:
        self.record = record
        self.descriptor = descriptor
        self.admitted_stat = admitted_stat
        self.closed = False

    @classmethod
    def open_observed(
        cls,
        *,
        root_descriptor: int,
        relative_path: str,
        roles: tuple[str, ...],
    ) -> _PinnedSourceMemberV49F:
        try:
            descriptor = _open_relative_file(root_descriptor, relative_path)
        except OSError as exc:
            raise SourceObservationV49FError(
                f"source member {relative_path!r} could not be opened safely"
            ) from exc
        try:
            digest, admitted_stat = _hash_descriptor(descriptor)
            reopened = _open_relative_file(root_descriptor, relative_path)
            try:
                reopened_digest, reopened_stat = _hash_descriptor(reopened)
            finally:
                os.close(reopened)
            if reopened_digest != digest or reopened_stat != admitted_stat:
                raise SourceObservationChangedV49FError(
                    f"source path {relative_path!r} changed during observation"
                )
            record = SourceMemberObservationV49F(
                relative_path=relative_path,
                roles=roles,
                size_bytes=admitted_stat.size,
                sha256=digest,
                device=str(admitted_stat.device),
                inode=str(admitted_stat.inode),
                mode=str(admitted_stat.mode),
                modified_ns=str(admitted_stat.modified_ns),
                changed_ns=str(admitted_stat.changed_ns),
            )
            return cls(
                record=record,
                descriptor=descriptor,
                admitted_stat=admitted_stat,
            )
        except BaseException:
            os.close(descriptor)
            raise

    def assert_current(self, *, root_descriptor: int) -> None:
        if self.closed:
            raise SourceObservationChangedV49FError("source member is closed")
        if os.get_inheritable(self.descriptor):
            raise SourceObservationChangedV49FError(
                "source member descriptor became inheritable"
            )
        digest, current_stat = _hash_descriptor(self.descriptor)
        if digest != self.record.sha256 or current_stat != self.admitted_stat:
            raise SourceObservationChangedV49FError(
                f"retained source member {self.record.relative_path!r} changed"
            )
        try:
            reopened = _open_relative_file(root_descriptor, self.record.relative_path)
        except OSError as exc:
            raise SourceObservationChangedV49FError(
                f"source path {self.record.relative_path!r} cannot be reopened safely"
            ) from exc
        try:
            reopened_digest, reopened_stat = _hash_descriptor(reopened)
        finally:
            os.close(reopened)
        if reopened_digest != self.record.sha256 or reopened_stat != self.admitted_stat:
            raise SourceObservationChangedV49FError(
                f"source path {self.record.relative_path!r} no longer names retained file"
            )

    def close(self) -> None:
        if not self.closed:
            self.closed = True
            os.close(self.descriptor)


class PinnedSourceObservationV49F:
    """PID/thread-bound retained capability for one exact local source closure."""

    def __init__(
        self,
        *,
        snapshot: SourceObservationSnapshotV49F,
        root_descriptor: int,
        root_identity: _RootIdentityV49F,
        members: tuple[_PinnedSourceMemberV49F, ...],
        module_inventory_factory: Any,
        critical_module_names: tuple[str, ...],
    ) -> None:
        self._snapshot = snapshot
        self._root_descriptor = root_descriptor
        self._root_identity = root_identity
        self._members = members
        self._module_inventory_factory = module_inventory_factory
        self._critical_module_names = critical_module_names
        self._creator_pid = os.getpid()
        self._creator_thread_id = threading.get_ident()
        self._fork_invalid = False
        self._closed = False
        self._lock = threading.RLock()
        _PINNED_SOURCE_FORK_GUARDS.add(self)

    @classmethod
    def open_observed(
        cls,
        *,
        repository_root: os.PathLike[str] | str,
        deployment_source_tree_sha256: str,
    ) -> PinnedSourceObservationV49F:
        return cls._open_observed(
            repository_root=repository_root,
            deployment_source_tree_sha256=deployment_source_tree_sha256,
            module_inventory_factory=_resolve_production_module_inventory,
            critical_module_names=CRITICAL_SOURCE_MODULES_V49F,
            after_first_git_state=None,
        )

    @classmethod
    def _open_observed_for_test(
        cls,
        *,
        repository_root: os.PathLike[str] | str,
        deployment_source_tree_sha256: str,
        module_inventory_factory: Any,
        critical_module_names: tuple[str, ...],
        after_first_git_state: Any = None,
    ) -> PinnedSourceObservationV49F:
        return cls._open_observed(
            repository_root=repository_root,
            deployment_source_tree_sha256=deployment_source_tree_sha256,
            module_inventory_factory=module_inventory_factory,
            critical_module_names=critical_module_names,
            after_first_git_state=after_first_git_state,
        )

    @classmethod
    def _open_observed(
        cls,
        *,
        repository_root: os.PathLike[str] | str,
        deployment_source_tree_sha256: str,
        module_inventory_factory: Any,
        critical_module_names: tuple[str, ...],
        after_first_git_state: Any,
    ) -> PinnedSourceObservationV49F:
        if cls is not PinnedSourceObservationV49F:
            raise TypeError("source observation subclasses are unsupported")
        root = _normalized_absolute_path(repository_root, field="repository_root")
        try:
            deployment_tree = canonical_hash(
                deployment_source_tree_sha256,
                field="deployment_source_tree_sha256",
            )
        except CanonicalizationError as exc:
            raise SourceObservationV49FError(str(exc)) from exc
        try:
            root_descriptor = _open_absolute_directory_no_symlinks(root)
        except OSError as exc:
            raise SourceObservationV49FError(
                "repository root could not be opened without symlinks"
            ) from exc
        opened: list[_PinnedSourceMemberV49F] = []
        try:
            root_identity = _RootIdentityV49F.from_stat(os.fstat(root_descriptor))
            _assert_git_repository_root(root_descriptor, root_identity)
            before_git = _capture_git_state(root_descriptor)
            if after_first_git_state is not None:
                after_first_git_state()
            modules_before = module_inventory_factory()
            roles_by_path = _module_roles(
                repository_root=root,
                modules=modules_before,
                critical_module_names=critical_module_names,
            )
            total = 0
            for relative_path, roles in roles_by_path.items():
                member = _PinnedSourceMemberV49F.open_observed(
                    root_descriptor=root_descriptor,
                    relative_path=relative_path,
                    roles=roles,
                )
                opened.append(member)
                total += member.record.size_bytes
                if total > _MAX_SOURCE_TOTAL_BYTES:
                    raise SourceObservationV49FError(
                        "source closure exceeds its total byte bound"
                    )
            modules_after = module_inventory_factory()
            roles_after = _module_roles(
                repository_root=root,
                modules=modules_after,
                critical_module_names=critical_module_names,
            )
            if roles_after != roles_by_path:
                raise SourceObservationChangedV49FError(
                    "loaded source-module closure changed during observation"
                )
            after_git = _capture_git_state(root_descriptor)
            if after_git != before_git:
                raise SourceObservationChangedV49FError(
                    "Git source state changed during observation"
                )
            cls._assert_root_path_identity(root, root_identity)
            records = tuple(member.record for member in opened)
            source_tree = derive_observed_source_tree_sha256_v49f(records)
            snapshot = SourceObservationSnapshotV49F(
                repository_root=root,
                git_state=after_git,
                members=records,
                member_count=len(records),
                total_bytes=total,
                source_tree_sha256=source_tree,
                deployment_source_tree_sha256=deployment_tree,
                deployment_source_tree_matches=source_tree == deployment_tree,
            )
            result = cls(
                snapshot=snapshot,
                root_descriptor=root_descriptor,
                root_identity=root_identity,
                members=tuple(opened),
                module_inventory_factory=module_inventory_factory,
                critical_module_names=critical_module_names,
            )
            opened.clear()
            root_descriptor = -1
            result.assert_current()
            return result
        except (CanonicalizationError, OSError) as exc:
            raise SourceObservationV49FError(str(exc)) from exc
        finally:
            for member in reversed(opened):
                try:
                    member.close()
                except OSError:
                    pass
            if root_descriptor >= 0:
                try:
                    os.close(root_descriptor)
                except OSError:
                    pass

    @staticmethod
    def _assert_root_path_identity(root: str, admitted: _RootIdentityV49F) -> None:
        try:
            descriptor = _open_absolute_directory_no_symlinks(root)
        except OSError as exc:
            raise SourceObservationChangedV49FError(
                "repository root path cannot be reopened safely"
            ) from exc
        try:
            if _RootIdentityV49F.from_stat(os.fstat(descriptor)) != admitted:
                raise SourceObservationChangedV49FError(
                    "repository root path no longer names the retained directory"
                )
        finally:
            os.close(descriptor)

    @property
    def snapshot(self) -> SourceObservationSnapshotV49F:
        return self._snapshot

    @property
    def source_observation_id(self) -> str:
        if self._snapshot.source_observation_id is None:  # pragma: no cover
            raise SourceObservationChangedV49FError("source observation ID is absent")
        return self._snapshot.source_observation_id

    @property
    def source_tree_sha256(self) -> str:
        return self._snapshot.source_tree_sha256

    @property
    def is_deployment_source_tree_match(self) -> bool:
        return self._snapshot.deployment_source_tree_matches

    def _assert_context(self) -> None:
        if (
            self._closed
            or self._fork_invalid
            or os.getpid() != self._creator_pid
            or threading.get_ident() != self._creator_thread_id
        ):
            raise SourceObservationChangedV49FError(
                "source observation left its creating process/thread"
            )

    def assert_current(self) -> None:
        with self._lock:
            self._assert_context()
            if os.get_inheritable(self._root_descriptor):
                raise SourceObservationChangedV49FError(
                    "repository root descriptor became inheritable"
                )
            if (
                _RootIdentityV49F.from_stat(os.fstat(self._root_descriptor))
                != self._root_identity
            ):
                raise SourceObservationChangedV49FError(
                    "retained repository root changed identity"
                )
            self._assert_root_path_identity(
                self._snapshot.repository_root,
                self._root_identity,
            )
            current_roles = _module_roles(
                repository_root=self._snapshot.repository_root,
                modules=self._module_inventory_factory(),
                critical_module_names=self._critical_module_names,
            )
            expected_roles = {
                member.relative_path: member.roles for member in self._snapshot.members
            }
            if current_roles != expected_roles:
                raise SourceObservationChangedV49FError(
                    "loaded source-module closure changed after observation"
                )
            if _capture_git_state(self._root_descriptor) != self._snapshot.git_state:
                raise SourceObservationChangedV49FError(
                    "Git source state changed after observation"
                )
            for member in self._members:
                member.assert_current(root_descriptor=self._root_descriptor)

    def _invalidate_in_fork_child(self) -> None:
        self._fork_invalid = True
        self._closed = True
        for member in self._members:
            try:
                member.close()
            except OSError:
                pass
        self._members = ()
        if self._root_descriptor >= 0:
            try:
                os.close(self._root_descriptor)
            except OSError:
                pass
            self._root_descriptor = -1

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            for member in reversed(self._members):
                try:
                    member.close()
                except OSError:
                    pass
            self._members = ()
            if self._root_descriptor >= 0:
                try:
                    os.close(self._root_descriptor)
                except OSError:
                    pass
                self._root_descriptor = -1

    def __enter__(self) -> PinnedSourceObservationV49F:
        self.assert_current()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def observe_current_source_v49f(
    *,
    repository_root: os.PathLike[str] | str,
    deployment_source_tree_sha256: str,
) -> PinnedSourceObservationV49F:
    """Observe and retain the exact current RiskYieldMM source closure."""

    return PinnedSourceObservationV49F.open_observed(
        repository_root=repository_root,
        deployment_source_tree_sha256=deployment_source_tree_sha256,
    )


def measure_current_release_source_tree_v49f(
    *, repository_root: os.PathLike[str] | str
) -> str:
    """Produce the exact source-tree hash a deployment release must sign."""

    observation = observe_current_source_v49f(
        repository_root=repository_root,
        deployment_source_tree_sha256="0" * 64,
    )
    try:
        return observation.source_tree_sha256
    finally:
        observation.close()


__all__ = [
    "CRITICAL_SOURCE_MODULES_V49F",
    "GitSourceStateV49F",
    "PinnedSourceObservationV49F",
    "RAW_V6_ACCEPTED_CRITICAL_SOURCE_INVENTORY_ID_V49F",
    "RAW_V6_ACCEPTED_CRITICAL_SOURCE_MODULES_V49F",
    "RAW_V7_CRITICAL_SOURCE_INVENTORY_ID_V49F",
    "RAW_V7_CRITICAL_SOURCE_MODULES_V49F",
    "SOURCE_OBSERVATION_SCHEMA_VERSION_V49F",
    "SourceMemberObservationV49F",
    "SourceObservationChangedV49FError",
    "SourceObservationSnapshotV49F",
    "SourceObservationV49FError",
    "derive_observed_source_tree_sha256_v49f",
    "measure_current_release_source_tree_v49f",
    "observe_current_source_v49f",
]
