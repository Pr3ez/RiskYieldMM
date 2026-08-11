"""Append-only governance authority for V3 trading records.

This module wraps the immutable contracts in a transactional registration
protocol.  It is deliberately a small, local, single-writer authority:

* SQLite rollback-journal mode is the certified default;
* every accepted mutation produces one globally ordered receipt;
* semantic heads are derived from immutable transitions, never overwritten;
* exact idempotent retries return the original receipt;
* checkpoints sign a precise receipt prefix and can be anchored externally.

The ledger does not make a directly readable holdout secret. Its holdout API
issues a locally one-time *evaluation grant*. Rollback resistance begins only
after a post-grant checkpoint is retained externally; physical blindness
belongs in a later isolated evaluator and data-access boundary.
"""

from __future__ import annotations

import fcntl
import hashlib
import os
import re
import sqlite3
import stat
import threading
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Protocol, runtime_checkable
from urllib.parse import quote

from .calendar_actions import (
    ActionProtocolV3,
    ActionResolutionV3,
    CalendarScheduleSnapshotV3,
    CalendarSourceArtifactV3,
    InstrumentMappingV3,
    resolve_scheduled_action_window_v3,
    validate_calendar_schedule_artifact_v3,
)
from .canonical import (
    CANONICALIZATION_VERSION,
    CanonicalizationError,
    canonical_hash,
    canonical_identifier,
    canonical_json_bytes,
    canonical_safe_int,
    require_exact_keys,
    sha256_digest,
    strict_json_loads,
    utc_datetime,
    utc_iso,
)
from .contracts import (
    BarrierActivationV3,
    CandidateFeatureMaterializationV3,
    DecisionEventV3,
    EligibilityDecisionV3,
    EntryScenario,
    EventDependenceAssignmentV3,
    InformationSetV3,
    LabelOutcomeV3,
    PrimarySignalCandidateV3,
)
from .evidence import (
    EvidenceKind,
    FeatureDefinitionV3,
    FeatureDependencySlotV3,
    FeatureSchemaV3,
    SourceBundleMemberV3,
    SourceBundleV3,
    validate_feature_schema_graph,
    validate_source_bundle_graph,
    validate_source_member_lineage,
)
from .manifests import (
    EvidenceRecordV3,
    ImmutableManifestV3,
    ManifestType,
    validate_action_resolution_candidate_graph,
    validate_candidate_protocol_graph,
    validate_eligibility_protocol_graph,
    validate_feature_materialization_protocol_graph,
    validate_information_protocol_graph,
    validate_manifest_evidence_graph,
    validate_record_protocol_graph,
)
from .physical_market_data import (
    BYBIT_V5_INSTRUMENT_INFO_CLASSIFIER_RELEASE_HASH,
    BYBIT_V5_KLINE_CLASSIFIER_RELEASE_HASH,
    CaptureSegmentV3,
    DependencySelectionProofV3,
    DerivationKind,
    EvidencePrefixV3,
    MessageDispositionKind,
    ObservationDerivationV3,
    ObservationRevisionV3,
    ObservationSelectionPolicyV3,
    PhysicalEvidenceGateV3,
    PhysicalGateStage,
    PhysicalGateVerdict,
    ProviderAdapterKind,
    ProviderAdapterPolicyV3,
    ProviderMessageDispositionV3,
    SelectionStatus,
    build_bybit_v5_message_disposition,
    build_physical_evidence_gate_v3,
    select_observation_revisions_v3,
    validate_capture_segment_lineage,
    validate_dependency_against_observation,
    validate_evidence_prefix_graph,
    validate_observation_revision_lineage,
    validate_raw_normalization_v3,
    validate_source_member_physical_prefix,
)

LEDGER_SCHEMA_VERSION = "riskyieldmm_receipt_ledger_v1"
LEDGER_VALIDATION_VERSION = "riskyieldmm_receipt_validation_v5"
CHECKPOINT_SCHEMA_VERSION = "riskyieldmm_ledger_checkpoint_v1"
HOLDOUT_GRANT_SCHEMA_VERSION = "riskyieldmm_holdout_evaluation_grant_v1"
GENESIS_HASH = "0" * 64
DEFAULT_MAX_OBJECT_BYTES = 1_048_576
MINIMUM_SQLITE_VERSION = (3, 37, 0)
_SIGNATURE_RE = re.compile(r"^[0-9a-f]{128}$")
_UNSAFE_FILESYSTEMS = frozenset(
    {
        "9p",
        "afs",
        "ceph",
        "cifs",
        "fuse.sshfs",
        "gfs",
        "gfs2",
        "glusterfs",
        "lustre",
        "ncpfs",
        "nfs",
        "nfs4",
        "ocfs2",
        "smb3",
        "smbfs",
    }
)


class LedgerError(RuntimeError):
    """Base class for governance-ledger failures."""


class LedgerConfigurationError(LedgerError):
    """Raised when the runtime cannot support the requested durability mode."""


class LedgerSecurityError(LedgerError):
    """Raised when storage ownership, permissions, or filesystem is unsafe."""


class LedgerWriterLockError(LedgerError):
    """Raised when another authoritative writer already owns the ledger."""


class LedgerConflictError(LedgerError):
    """Raised when an append conflicts with immutable or active state."""


class LedgerIdempotencyConflictError(LedgerConflictError):
    """Raised when an idempotency key is reused for another request."""


class LedgerAlreadyRegisteredError(LedgerConflictError):
    """Raised when an object is submitted under a different idempotency key."""


class LedgerNotFoundError(LedgerError):
    """Raised when a referenced ledger object does not exist."""


class LedgerVerificationError(LedgerError):
    """Raised when stored bytes, chains, links, or signatures do not verify."""


class HoldoutGrantConflictError(LedgerConflictError):
    """Raised when a protocol or split already has an evaluation grant."""


class LedgerChannel(str, Enum):
    MANIFEST = "MANIFEST"
    OBSERVATION = "OBSERVATION"
    EVENT = "EVENT"
    LABEL = "LABEL"
    GOVERNANCE = "GOVERNANCE"


class LedgerOperation(str, Enum):
    APPEND_RECORD = "APPEND_RECORD"
    CREATE_CHECKPOINT = "CREATE_CHECKPOINT"
    GRANT_HOLDOUT_EVALUATION = "GRANT_HOLDOUT_EVALUATION"


class LedgerRecordKind(str, Enum):
    MANIFEST = "MANIFEST"
    CALENDAR_SOURCE_ARTIFACT = "CALENDAR_SOURCE_ARTIFACT"
    CALENDAR_SCHEDULE_SNAPSHOT = "CALENDAR_SCHEDULE_SNAPSHOT"
    ACTION_PROTOCOL = "ACTION_PROTOCOL"
    INSTRUMENT_MAPPING = "INSTRUMENT_MAPPING"
    SOURCE_BUNDLE_MEMBER = "SOURCE_BUNDLE_MEMBER"
    SOURCE_BUNDLE = "SOURCE_BUNDLE"
    FEATURE_DEPENDENCY_SLOT = "FEATURE_DEPENDENCY_SLOT"
    FEATURE_DEFINITION = "FEATURE_DEFINITION"
    FEATURE_SCHEMA = "FEATURE_SCHEMA"
    PROVIDER_ADAPTER_POLICY = "PROVIDER_ADAPTER_POLICY"
    CAPTURE_SEGMENT = "CAPTURE_SEGMENT"
    OBSERVATION_DERIVATION = "OBSERVATION_DERIVATION"
    OBSERVATION_REVISION = "OBSERVATION_REVISION"
    PROVIDER_MESSAGE_DISPOSITION = "PROVIDER_MESSAGE_DISPOSITION"
    OBSERVATION_SELECTION_POLICY = "OBSERVATION_SELECTION_POLICY"
    EVIDENCE_PREFIX = "EVIDENCE_PREFIX"
    DEPENDENCY_SELECTION_PROOF = "DEPENDENCY_SELECTION_PROOF"
    PHYSICAL_EVIDENCE_GATE = "PHYSICAL_EVIDENCE_GATE"
    INFORMATION_SET = "INFORMATION_SET"
    ACTION_RESOLUTION = "ACTION_RESOLUTION"
    PRIMARY_SIGNAL_CANDIDATE = "PRIMARY_SIGNAL_CANDIDATE"
    CANDIDATE_FEATURE_MATERIALIZATION = "CANDIDATE_FEATURE_MATERIALIZATION"
    ELIGIBILITY_DECISION = "ELIGIBILITY_DECISION"
    DECISION_EVENT = "DECISION_EVENT"
    BARRIER_ACTIVATION = "BARRIER_ACTIVATION"
    LABEL_OUTCOME = "LABEL_OUTCOME"
    EVENT_DEPENDENCE_ASSIGNMENT = "EVENT_DEPENDENCE_ASSIGNMENT"


_KIND_CLASS: dict[LedgerRecordKind, type[Any]] = {
    LedgerRecordKind.MANIFEST: ImmutableManifestV3,
    LedgerRecordKind.CALENDAR_SOURCE_ARTIFACT: CalendarSourceArtifactV3,
    LedgerRecordKind.CALENDAR_SCHEDULE_SNAPSHOT: CalendarScheduleSnapshotV3,
    LedgerRecordKind.ACTION_PROTOCOL: ActionProtocolV3,
    LedgerRecordKind.INSTRUMENT_MAPPING: InstrumentMappingV3,
    LedgerRecordKind.SOURCE_BUNDLE_MEMBER: SourceBundleMemberV3,
    LedgerRecordKind.SOURCE_BUNDLE: SourceBundleV3,
    LedgerRecordKind.FEATURE_DEPENDENCY_SLOT: FeatureDependencySlotV3,
    LedgerRecordKind.FEATURE_DEFINITION: FeatureDefinitionV3,
    LedgerRecordKind.FEATURE_SCHEMA: FeatureSchemaV3,
    LedgerRecordKind.PROVIDER_ADAPTER_POLICY: ProviderAdapterPolicyV3,
    LedgerRecordKind.CAPTURE_SEGMENT: CaptureSegmentV3,
    LedgerRecordKind.OBSERVATION_DERIVATION: ObservationDerivationV3,
    LedgerRecordKind.OBSERVATION_REVISION: ObservationRevisionV3,
    LedgerRecordKind.PROVIDER_MESSAGE_DISPOSITION: ProviderMessageDispositionV3,
    LedgerRecordKind.OBSERVATION_SELECTION_POLICY: ObservationSelectionPolicyV3,
    LedgerRecordKind.EVIDENCE_PREFIX: EvidencePrefixV3,
    LedgerRecordKind.DEPENDENCY_SELECTION_PROOF: DependencySelectionProofV3,
    LedgerRecordKind.PHYSICAL_EVIDENCE_GATE: PhysicalEvidenceGateV3,
    LedgerRecordKind.INFORMATION_SET: InformationSetV3,
    LedgerRecordKind.ACTION_RESOLUTION: ActionResolutionV3,
    LedgerRecordKind.PRIMARY_SIGNAL_CANDIDATE: PrimarySignalCandidateV3,
    LedgerRecordKind.CANDIDATE_FEATURE_MATERIALIZATION: (
        CandidateFeatureMaterializationV3
    ),
    LedgerRecordKind.ELIGIBILITY_DECISION: EligibilityDecisionV3,
    LedgerRecordKind.DECISION_EVENT: DecisionEventV3,
    LedgerRecordKind.BARRIER_ACTIVATION: BarrierActivationV3,
    LedgerRecordKind.LABEL_OUTCOME: LabelOutcomeV3,
    LedgerRecordKind.EVENT_DEPENDENCE_ASSIGNMENT: EventDependenceAssignmentV3,
}

_CLASS_KIND = {value: key for key, value in _KIND_CLASS.items()}

_EVIDENCE_RECORD_KINDS = frozenset(
    {
        LedgerRecordKind.CALENDAR_SOURCE_ARTIFACT,
        LedgerRecordKind.CALENDAR_SCHEDULE_SNAPSHOT,
        LedgerRecordKind.ACTION_PROTOCOL,
        LedgerRecordKind.INSTRUMENT_MAPPING,
        LedgerRecordKind.SOURCE_BUNDLE_MEMBER,
        LedgerRecordKind.SOURCE_BUNDLE,
        LedgerRecordKind.FEATURE_DEPENDENCY_SLOT,
        LedgerRecordKind.FEATURE_DEFINITION,
        LedgerRecordKind.FEATURE_SCHEMA,
        LedgerRecordKind.PROVIDER_ADAPTER_POLICY,
        LedgerRecordKind.OBSERVATION_SELECTION_POLICY,
    }
)

_PHYSICAL_RECORD_KINDS = frozenset(
    {
        LedgerRecordKind.PROVIDER_ADAPTER_POLICY,
        LedgerRecordKind.CAPTURE_SEGMENT,
        LedgerRecordKind.OBSERVATION_DERIVATION,
        LedgerRecordKind.OBSERVATION_REVISION,
        LedgerRecordKind.PROVIDER_MESSAGE_DISPOSITION,
        LedgerRecordKind.OBSERVATION_SELECTION_POLICY,
        LedgerRecordKind.EVIDENCE_PREFIX,
        LedgerRecordKind.DEPENDENCY_SELECTION_PROOF,
        LedgerRecordKind.PHYSICAL_EVIDENCE_GATE,
    }
)

_KIND_CHANNEL = {
    LedgerRecordKind.MANIFEST: LedgerChannel.MANIFEST,
    LedgerRecordKind.CALENDAR_SOURCE_ARTIFACT: LedgerChannel.MANIFEST,
    LedgerRecordKind.CALENDAR_SCHEDULE_SNAPSHOT: LedgerChannel.MANIFEST,
    LedgerRecordKind.ACTION_PROTOCOL: LedgerChannel.MANIFEST,
    LedgerRecordKind.INSTRUMENT_MAPPING: LedgerChannel.MANIFEST,
    LedgerRecordKind.SOURCE_BUNDLE_MEMBER: LedgerChannel.MANIFEST,
    LedgerRecordKind.SOURCE_BUNDLE: LedgerChannel.MANIFEST,
    LedgerRecordKind.FEATURE_DEPENDENCY_SLOT: LedgerChannel.MANIFEST,
    LedgerRecordKind.FEATURE_DEFINITION: LedgerChannel.MANIFEST,
    LedgerRecordKind.FEATURE_SCHEMA: LedgerChannel.MANIFEST,
    LedgerRecordKind.PROVIDER_ADAPTER_POLICY: LedgerChannel.MANIFEST,
    LedgerRecordKind.CAPTURE_SEGMENT: LedgerChannel.OBSERVATION,
    LedgerRecordKind.OBSERVATION_DERIVATION: LedgerChannel.OBSERVATION,
    LedgerRecordKind.OBSERVATION_REVISION: LedgerChannel.OBSERVATION,
    LedgerRecordKind.PROVIDER_MESSAGE_DISPOSITION: LedgerChannel.OBSERVATION,
    LedgerRecordKind.OBSERVATION_SELECTION_POLICY: LedgerChannel.MANIFEST,
    LedgerRecordKind.EVIDENCE_PREFIX: LedgerChannel.OBSERVATION,
    LedgerRecordKind.DEPENDENCY_SELECTION_PROOF: LedgerChannel.OBSERVATION,
    LedgerRecordKind.PHYSICAL_EVIDENCE_GATE: LedgerChannel.OBSERVATION,
    LedgerRecordKind.INFORMATION_SET: LedgerChannel.EVENT,
    LedgerRecordKind.ACTION_RESOLUTION: LedgerChannel.EVENT,
    LedgerRecordKind.PRIMARY_SIGNAL_CANDIDATE: LedgerChannel.EVENT,
    LedgerRecordKind.CANDIDATE_FEATURE_MATERIALIZATION: LedgerChannel.EVENT,
    LedgerRecordKind.ELIGIBILITY_DECISION: LedgerChannel.EVENT,
    LedgerRecordKind.DECISION_EVENT: LedgerChannel.EVENT,
    LedgerRecordKind.BARRIER_ACTIVATION: LedgerChannel.EVENT,
    LedgerRecordKind.LABEL_OUTCOME: LedgerChannel.LABEL,
    LedgerRecordKind.EVENT_DEPENDENCE_ASSIGNMENT: LedgerChannel.LABEL,
}


@runtime_checkable
class CheckpointSigner(Protocol):
    """Structural interface for an external checkpoint signing key."""

    algorithm: str
    key_id: str
    public_key_bytes: bytes

    def sign(self, payload: bytes) -> bytes:
        """Return a detached signature for canonical checkpoint bytes."""


@runtime_checkable
class CheckpointVerifier(Protocol):
    """Structural interface for a trusted checkpoint public key."""

    algorithm: str
    key_id: str

    def verify(self, payload: bytes, signature: bytes) -> None:
        """Raise when the detached signature is invalid."""


@dataclass(frozen=True, slots=True, kw_only=True)
class LedgerChannelRoot:
    channel: LedgerChannel
    sequence: int
    receipt_hash: str

    def __post_init__(self) -> None:
        try:
            channel = (
                self.channel
                if isinstance(self.channel, LedgerChannel)
                else LedgerChannel(self.channel)
            )
        except (TypeError, ValueError) as exc:
            raise CanonicalizationError("unsupported ledger channel") from exc
        object.__setattr__(self, "channel", channel)
        object.__setattr__(
            self,
            "sequence",
            canonical_safe_int(self.sequence, field="sequence", minimum=0),
        )
        object.__setattr__(
            self,
            "receipt_hash",
            canonical_hash(self.receipt_hash, field="receipt_hash"),
        )
        if self.sequence == 0 and self.receipt_hash != GENESIS_HASH:
            raise CanonicalizationError("empty channel must use the genesis hash")
        if self.sequence > 0 and self.receipt_hash == GENESIS_HASH:
            raise CanonicalizationError("non-empty channel cannot use the genesis hash")

    def as_dict(self) -> dict[str, Any]:
        return {
            "channel": self.channel.value,
            "receipt_hash": self.receipt_hash,
            "sequence": self.sequence,
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> LedgerChannelRoot:
        require_exact_keys(
            payload,
            expected={"channel", "receipt_hash", "sequence"},
            context="LedgerChannelRoot",
        )
        return cls(
            channel=payload["channel"],
            sequence=payload["sequence"],
            receipt_hash=payload["receipt_hash"],
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class LedgerReceipt:
    ledger_id: str
    global_sequence: int
    channel: LedgerChannel
    channel_sequence: int
    receipt_ts: datetime
    operation: LedgerOperation
    record_kind: str
    identity_id: str
    record_hash: str
    content_hash: str
    semantic_key: str
    head_type: str
    idempotency_key: str
    request_hash: str
    expected_head: str | None
    new_head: str
    previous_global_receipt_hash: str
    previous_channel_receipt_hash: str
    governance_payload_hash: str | None = None
    validation_version: str = LEDGER_VALIDATION_VERSION

    def __post_init__(self) -> None:
        for field_name in (
            "ledger_id",
            "identity_id",
            "record_hash",
            "content_hash",
            "semantic_key",
            "request_hash",
            "new_head",
            "previous_global_receipt_hash",
            "previous_channel_receipt_hash",
        ):
            object.__setattr__(
                self,
                field_name,
                canonical_hash(getattr(self, field_name), field=field_name),
            )
        object.__setattr__(
            self,
            "expected_head",
            None
            if self.expected_head is None
            else canonical_hash(self.expected_head, field="expected_head"),
        )
        object.__setattr__(
            self,
            "governance_payload_hash",
            None
            if self.governance_payload_hash is None
            else canonical_hash(
                self.governance_payload_hash,
                field="governance_payload_hash",
            ),
        )
        object.__setattr__(
            self,
            "global_sequence",
            canonical_safe_int(
                self.global_sequence, field="global_sequence", minimum=1
            ),
        )
        object.__setattr__(
            self,
            "channel_sequence",
            canonical_safe_int(
                self.channel_sequence, field="channel_sequence", minimum=1
            ),
        )
        try:
            object.__setattr__(self, "channel", LedgerChannel(self.channel))
            object.__setattr__(self, "operation", LedgerOperation(self.operation))
        except (TypeError, ValueError) as exc:
            raise CanonicalizationError("unsupported receipt enum value") from exc
        object.__setattr__(
            self,
            "receipt_ts",
            utc_datetime(self.receipt_ts, field="receipt_ts"),
        )
        object.__setattr__(
            self,
            "record_kind",
            canonical_identifier(self.record_kind, field="record_kind"),
        )
        object.__setattr__(
            self,
            "head_type",
            canonical_identifier(self.head_type, field="head_type"),
        )
        object.__setattr__(
            self,
            "idempotency_key",
            canonical_identifier(
                self.idempotency_key,
                field="idempotency_key",
                maximum=256,
            ),
        )
        validation = canonical_identifier(
            self.validation_version,
            field="validation_version",
        )
        if validation != LEDGER_VALIDATION_VERSION:
            raise CanonicalizationError("unsupported receipt validation version")
        object.__setattr__(self, "validation_version", validation)

    def identity_payload(self) -> dict[str, Any]:
        return {
            "canonicalization_version": CANONICALIZATION_VERSION,
            "channel": self.channel.value,
            "channel_sequence": self.channel_sequence,
            "content_hash": self.content_hash,
            "expected_head": self.expected_head,
            "global_sequence": self.global_sequence,
            "governance_payload_hash": self.governance_payload_hash,
            "head_type": self.head_type,
            "idempotency_key": self.idempotency_key,
            "identity_id": self.identity_id,
            "ledger_id": self.ledger_id,
            "ledger_schema_version": LEDGER_SCHEMA_VERSION,
            "new_head": self.new_head,
            "operation": self.operation.value,
            "previous_channel_receipt_hash": self.previous_channel_receipt_hash,
            "previous_global_receipt_hash": self.previous_global_receipt_hash,
            "receipt_ts": utc_iso(self.receipt_ts),
            "record_hash": self.record_hash,
            "record_kind": self.record_kind,
            "request_hash": self.request_hash,
            "semantic_key": self.semantic_key,
            "validation_version": self.validation_version,
        }

    @property
    def receipt_hash(self) -> str:
        return sha256_digest(
            {"domain": "RiskYieldMMLedgerReceiptV1", "payload": self.identity_payload()}
        )

    def as_dict(self) -> dict[str, Any]:
        return {**self.identity_payload(), "receipt_hash": self.receipt_hash}

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> LedgerReceipt:
        expected = {
            "canonicalization_version",
            "channel",
            "channel_sequence",
            "content_hash",
            "expected_head",
            "global_sequence",
            "governance_payload_hash",
            "head_type",
            "idempotency_key",
            "identity_id",
            "ledger_id",
            "ledger_schema_version",
            "new_head",
            "operation",
            "previous_channel_receipt_hash",
            "previous_global_receipt_hash",
            "receipt_hash",
            "receipt_ts",
            "record_hash",
            "record_kind",
            "request_hash",
            "semantic_key",
            "validation_version",
        }
        require_exact_keys(payload, expected=expected, context="LedgerReceipt")
        if payload["canonicalization_version"] != CANONICALIZATION_VERSION:
            raise CanonicalizationError("unsupported receipt canonicalization version")
        if payload["ledger_schema_version"] != LEDGER_SCHEMA_VERSION:
            raise CanonicalizationError("unsupported receipt ledger schema version")
        item = cls(
            ledger_id=payload["ledger_id"],
            global_sequence=payload["global_sequence"],
            channel=payload["channel"],
            channel_sequence=payload["channel_sequence"],
            receipt_ts=payload["receipt_ts"],
            operation=payload["operation"],
            record_kind=payload["record_kind"],
            identity_id=payload["identity_id"],
            record_hash=payload["record_hash"],
            content_hash=payload["content_hash"],
            semantic_key=payload["semantic_key"],
            head_type=payload["head_type"],
            idempotency_key=payload["idempotency_key"],
            request_hash=payload["request_hash"],
            expected_head=payload["expected_head"],
            new_head=payload["new_head"],
            previous_global_receipt_hash=payload["previous_global_receipt_hash"],
            previous_channel_receipt_hash=payload["previous_channel_receipt_hash"],
            governance_payload_hash=payload["governance_payload_hash"],
            validation_version=payload["validation_version"],
        )
        if canonical_hash(payload["receipt_hash"], field="receipt_hash") != (
            item.receipt_hash
        ):
            raise CanonicalizationError("receipt_hash does not match canonical content")
        return item


@dataclass(frozen=True, slots=True, kw_only=True)
class SignedLedgerCheckpoint:
    ledger_id: str
    signed_at: datetime
    global_sequence: int
    global_receipt_root: str
    channel_roots: tuple[LedgerChannelRoot, ...]
    previous_checkpoint_id: str | None
    signature_algorithm: str
    key_id: str
    signature: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "ledger_id", canonical_hash(self.ledger_id, field="ledger_id")
        )
        object.__setattr__(
            self,
            "signed_at",
            utc_datetime(self.signed_at, field="signed_at"),
        )
        object.__setattr__(
            self,
            "global_sequence",
            canonical_safe_int(
                self.global_sequence, field="global_sequence", minimum=0
            ),
        )
        object.__setattr__(
            self,
            "global_receipt_root",
            canonical_hash(self.global_receipt_root, field="global_receipt_root"),
        )
        if self.global_sequence == 0 and self.global_receipt_root != GENESIS_HASH:
            raise CanonicalizationError("empty ledger must use the genesis hash")
        roots = tuple(
            sorted(
                (
                    item
                    if isinstance(item, LedgerChannelRoot)
                    else LedgerChannelRoot.from_mapping(item)
                    for item in self.channel_roots
                ),
                key=lambda item: item.channel.value,
            )
        )
        expected_channels = set(LedgerChannel)
        if (
            len(roots) != len(expected_channels)
            or {item.channel for item in roots} != expected_channels
        ):
            raise CanonicalizationError(
                "checkpoint must contain exactly one root for every channel"
            )
        object.__setattr__(self, "channel_roots", roots)
        object.__setattr__(
            self,
            "previous_checkpoint_id",
            None
            if self.previous_checkpoint_id is None
            else canonical_hash(
                self.previous_checkpoint_id,
                field="previous_checkpoint_id",
            ),
        )
        algorithm = canonical_identifier(
            self.signature_algorithm,
            field="signature_algorithm",
            maximum=32,
        )
        if algorithm != "ED25519":
            raise CanonicalizationError("only ED25519 checkpoints are supported")
        object.__setattr__(self, "signature_algorithm", algorithm)
        object.__setattr__(
            self,
            "key_id",
            canonical_identifier(self.key_id, field="key_id", maximum=256),
        )
        if (
            not isinstance(self.signature, str)
            or _SIGNATURE_RE.fullmatch(self.signature) is None
        ):
            raise CanonicalizationError(
                "signature must be a lowercase 64-byte hexadecimal value"
            )

    def signing_payload(self) -> dict[str, Any]:
        return {
            "canonicalization_version": CANONICALIZATION_VERSION,
            "channel_roots": [item.as_dict() for item in self.channel_roots],
            "checkpoint_schema_version": CHECKPOINT_SCHEMA_VERSION,
            "global_receipt_root": self.global_receipt_root,
            "global_sequence": self.global_sequence,
            "key_id": self.key_id,
            "ledger_id": self.ledger_id,
            "ledger_schema_version": LEDGER_SCHEMA_VERSION,
            "previous_checkpoint_id": self.previous_checkpoint_id,
            "signature_algorithm": self.signature_algorithm,
            "signed_at": utc_iso(self.signed_at),
        }

    @property
    def checkpoint_id(self) -> str:
        return sha256_digest(
            {
                "domain": "RiskYieldMMSignedLedgerCheckpointV1",
                "payload": self.signing_payload(),
                "signature": self.signature,
                "signature_encoding": "HEX",
            }
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            **self.signing_payload(),
            "checkpoint_id": self.checkpoint_id,
            "signature": self.signature,
            "signature_encoding": "HEX",
        }

    def verify_signature(self, verifier: CheckpointVerifier) -> None:
        if verifier.algorithm != self.signature_algorithm:
            raise LedgerVerificationError("checkpoint signature algorithm mismatch")
        if verifier.key_id != self.key_id:
            raise LedgerVerificationError("checkpoint key ID mismatch")
        try:
            verifier.verify(
                canonical_json_bytes(self.signing_payload()),
                bytes.fromhex(self.signature),
            )
        except LedgerVerificationError:
            raise
        except Exception as exc:
            raise LedgerVerificationError("checkpoint signature is invalid") from exc

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> SignedLedgerCheckpoint:
        expected = {
            "canonicalization_version",
            "channel_roots",
            "checkpoint_id",
            "checkpoint_schema_version",
            "global_receipt_root",
            "global_sequence",
            "key_id",
            "ledger_id",
            "ledger_schema_version",
            "previous_checkpoint_id",
            "signature",
            "signature_algorithm",
            "signature_encoding",
            "signed_at",
        }
        require_exact_keys(
            payload,
            expected=expected,
            context="SignedLedgerCheckpoint",
        )
        if payload["canonicalization_version"] != CANONICALIZATION_VERSION:
            raise CanonicalizationError("unsupported checkpoint canonicalization")
        if payload["checkpoint_schema_version"] != CHECKPOINT_SCHEMA_VERSION:
            raise CanonicalizationError("unsupported checkpoint schema version")
        if payload["ledger_schema_version"] != LEDGER_SCHEMA_VERSION:
            raise CanonicalizationError("unsupported checkpoint ledger version")
        if payload["signature_encoding"] != "HEX":
            raise CanonicalizationError("unsupported checkpoint signature encoding")
        roots = payload["channel_roots"]
        if not isinstance(roots, list):
            raise CanonicalizationError("channel_roots must be a JSON array")
        item = cls(
            ledger_id=payload["ledger_id"],
            signed_at=payload["signed_at"],
            global_sequence=payload["global_sequence"],
            global_receipt_root=payload["global_receipt_root"],
            channel_roots=tuple(LedgerChannelRoot.from_mapping(root) for root in roots),
            previous_checkpoint_id=payload["previous_checkpoint_id"],
            signature_algorithm=payload["signature_algorithm"],
            key_id=payload["key_id"],
            signature=payload["signature"],
        )
        if canonical_hash(payload["checkpoint_id"], field="checkpoint_id") != (
            item.checkpoint_id
        ):
            raise CanonicalizationError(
                "checkpoint_id does not match canonical content"
            )
        return item


@dataclass(frozen=True, slots=True, kw_only=True)
class HoldoutEvaluationGrant:
    ledger_id: str
    protocol_manifest_id: str
    split_manifest_id: str
    checkpoint_id: str
    approval_hash: str
    evidence_gate_hash: str
    frozen_artifact_hash: str
    external_anchor_hash: str
    granted_at: datetime

    def __post_init__(self) -> None:
        for field_name in (
            "ledger_id",
            "protocol_manifest_id",
            "split_manifest_id",
            "checkpoint_id",
            "approval_hash",
            "evidence_gate_hash",
            "frozen_artifact_hash",
            "external_anchor_hash",
        ):
            object.__setattr__(
                self,
                field_name,
                canonical_hash(getattr(self, field_name), field=field_name),
            )
        object.__setattr__(
            self,
            "granted_at",
            utc_datetime(self.granted_at, field="granted_at"),
        )

    def identity_payload(self) -> dict[str, Any]:
        return {
            "approval_hash": self.approval_hash,
            "canonicalization_version": CANONICALIZATION_VERSION,
            "checkpoint_id": self.checkpoint_id,
            "evidence_gate_hash": self.evidence_gate_hash,
            "external_anchor_hash": self.external_anchor_hash,
            "frozen_artifact_hash": self.frozen_artifact_hash,
            "grant_schema_version": HOLDOUT_GRANT_SCHEMA_VERSION,
            "granted_at": utc_iso(self.granted_at),
            "ledger_id": self.ledger_id,
            "protocol_manifest_id": self.protocol_manifest_id,
            "split_manifest_id": self.split_manifest_id,
        }

    @property
    def grant_id(self) -> str:
        return sha256_digest(
            {
                "domain": "RiskYieldMMHoldoutEvaluationGrantV1",
                "payload": self.identity_payload(),
            }
        )

    def as_dict(self) -> dict[str, Any]:
        return {**self.identity_payload(), "grant_id": self.grant_id}

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> HoldoutEvaluationGrant:
        expected = {
            "approval_hash",
            "canonicalization_version",
            "checkpoint_id",
            "evidence_gate_hash",
            "external_anchor_hash",
            "frozen_artifact_hash",
            "grant_id",
            "grant_schema_version",
            "granted_at",
            "ledger_id",
            "protocol_manifest_id",
            "split_manifest_id",
        }
        require_exact_keys(
            payload,
            expected=expected,
            context="HoldoutEvaluationGrant",
        )
        if payload["canonicalization_version"] != CANONICALIZATION_VERSION:
            raise CanonicalizationError("unsupported grant canonicalization")
        if payload["grant_schema_version"] != HOLDOUT_GRANT_SCHEMA_VERSION:
            raise CanonicalizationError("unsupported holdout grant schema")
        item = cls(
            ledger_id=payload["ledger_id"],
            protocol_manifest_id=payload["protocol_manifest_id"],
            split_manifest_id=payload["split_manifest_id"],
            checkpoint_id=payload["checkpoint_id"],
            approval_hash=payload["approval_hash"],
            evidence_gate_hash=payload["evidence_gate_hash"],
            frozen_artifact_hash=payload["frozen_artifact_hash"],
            external_anchor_hash=payload["external_anchor_hash"],
            granted_at=payload["granted_at"],
        )
        if canonical_hash(payload["grant_id"], field="grant_id") != item.grant_id:
            raise CanonicalizationError("grant_id does not match canonical content")
        return item


@dataclass(frozen=True, slots=True, kw_only=True)
class LedgerVerificationReport:
    ledger_id: str
    object_count: int
    receipt_count: int
    head_transition_count: int
    checkpoint_count: int
    holdout_grant_count: int
    global_receipt_root: str
    channel_roots: tuple[LedgerChannelRoot, ...]
    trusted_checkpoint_id: str | None
    trusted_global_sequence: int | None
    unanchored_receipt_count: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "channel_roots": [item.as_dict() for item in self.channel_roots],
            "checkpoint_count": self.checkpoint_count,
            "global_receipt_root": self.global_receipt_root,
            "head_transition_count": self.head_transition_count,
            "holdout_grant_count": self.holdout_grant_count,
            "ledger_id": self.ledger_id,
            "object_count": self.object_count,
            "receipt_count": self.receipt_count,
            "trusted_checkpoint_id": self.trusted_checkpoint_id,
            "trusted_global_sequence": self.trusted_global_sequence,
            "unanchored_receipt_count": self.unanchored_receipt_count,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class HoldoutEvaluationSealReport:
    """Evidence that an external signed prefix includes a holdout grant."""

    grant_id: str
    protocol_manifest_id: str
    split_manifest_id: str
    grant_receipt_sequence: int
    trusted_checkpoint_id: str
    trusted_global_sequence: int
    unanchored_receipt_count: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "grant_id": self.grant_id,
            "grant_receipt_sequence": self.grant_receipt_sequence,
            "protocol_manifest_id": self.protocol_manifest_id,
            "split_manifest_id": self.split_manifest_id,
            "trusted_checkpoint_id": self.trusted_checkpoint_id,
            "trusted_global_sequence": self.trusted_global_sequence,
            "unanchored_receipt_count": self.unanchored_receipt_count,
        }


LedgerRecord = (
    ImmutableManifestV3
    | CalendarSourceArtifactV3
    | CalendarScheduleSnapshotV3
    | ActionProtocolV3
    | InstrumentMappingV3
    | SourceBundleMemberV3
    | SourceBundleV3
    | FeatureDependencySlotV3
    | FeatureDefinitionV3
    | FeatureSchemaV3
    | ProviderAdapterPolicyV3
    | CaptureSegmentV3
    | ObservationDerivationV3
    | ObservationRevisionV3
    | ProviderMessageDispositionV3
    | ObservationSelectionPolicyV3
    | EvidencePrefixV3
    | DependencySelectionProofV3
    | PhysicalEvidenceGateV3
    | InformationSetV3
    | ActionResolutionV3
    | PrimarySignalCandidateV3
    | CandidateFeatureMaterializationV3
    | EligibilityDecisionV3
    | DecisionEventV3
    | BarrierActivationV3
    | LabelOutcomeV3
    | EventDependenceAssignmentV3
)


def sqlite_wal_runtime_is_safe(
    version: tuple[int, int, int] | None = None,
) -> bool:
    """Return whether the runtime includes SQLite's WAL-reset race fix.

    SQLite fixed the issue in 3.51.3 and backported it to 3.50.7 and 3.44.6.
    Versions on other intervening branches are conservatively rejected.
    """

    value = sqlite3.sqlite_version_info if version is None else version
    if value >= (3, 51, 3):
        return True
    if (3, 50, 7) <= value < (3, 51, 0):
        return True
    return (3, 44, 6) <= value < (3, 45, 0)


def _filesystem_type(path: Path) -> str | None:
    """Return Linux mount type for ``path`` using the longest mount match."""

    mountinfo = Path("/proc/self/mountinfo")
    if not mountinfo.exists():
        return None
    target = str(path.resolve())
    best: tuple[int, str] | None = None
    try:
        lines = mountinfo.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in lines:
        left, separator, right = line.partition(" - ")
        if not separator:
            continue
        left_fields = left.split()
        right_fields = right.split()
        if len(left_fields) < 5 or not right_fields:
            continue
        mount_point = (
            left_fields[4]
            .replace("\\040", " ")
            .replace("\\011", "\t")
            .replace("\\134", "\\")
        )
        if target == mount_point or target.startswith(mount_point.rstrip("/") + "/"):
            candidate = (len(mount_point), right_fields[0])
            if best is None or candidate[0] > best[0]:
                best = candidate
    return None if best is None else best[1]


def _raw_sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _parse_json_object(blob: bytes, *, context: str) -> Mapping[str, Any]:
    value = strict_json_loads(blob)
    if not isinstance(value, Mapping):
        raise CanonicalizationError(f"{context} must be a JSON object")
    return value


def _parse_record(kind: LedgerRecordKind, blob: bytes) -> LedgerRecord:
    payload = _parse_json_object(blob, context=kind.value)
    parser = _KIND_CLASS[kind]
    return parser.from_mapping(payload)


def _record_kind(record: LedgerRecord) -> LedgerRecordKind:
    kind = _CLASS_KIND.get(type(record))
    if kind is None:
        raise CanonicalizationError(
            "ledger accepts only exact V3 record and manifest classes"
        )
    return kind


def _record_identity(record: LedgerRecord) -> str:
    if isinstance(record, ImmutableManifestV3):
        return record.manifest_id
    if isinstance(record, CalendarSourceArtifactV3):
        return record.calendar_source_artifact_id
    if isinstance(record, CalendarScheduleSnapshotV3):
        return record.calendar_snapshot_id
    if isinstance(record, ActionProtocolV3):
        return record.action_protocol_id
    if isinstance(record, InstrumentMappingV3):
        return record.instrument_mapping_id
    if isinstance(record, SourceBundleMemberV3):
        return record.source_member_id
    if isinstance(record, SourceBundleV3):
        return record.source_bundle_id
    if isinstance(record, FeatureDependencySlotV3):
        return record.dependency_slot_id
    if isinstance(record, FeatureDefinitionV3):
        return record.feature_definition_id
    if isinstance(record, FeatureSchemaV3):
        return record.feature_schema_id
    if isinstance(record, ProviderAdapterPolicyV3):
        return record.adapter_policy_id
    if isinstance(record, CaptureSegmentV3):
        return record.capture_segment_id
    if isinstance(record, ObservationDerivationV3):
        return record.observation_derivation_id
    if isinstance(record, ObservationRevisionV3):
        return record.observation_revision_id
    if isinstance(record, ProviderMessageDispositionV3):
        return record.provider_message_disposition_id
    if isinstance(record, ObservationSelectionPolicyV3):
        return record.observation_selection_policy_id
    if isinstance(record, EvidencePrefixV3):
        return record.evidence_prefix_id
    if isinstance(record, DependencySelectionProofV3):
        return record.dependency_selection_proof_id
    if isinstance(record, PhysicalEvidenceGateV3):
        return record.physical_evidence_gate_id
    if isinstance(record, InformationSetV3):
        return record.information_set_id
    if isinstance(record, ActionResolutionV3):
        return record.action_resolution_id
    if isinstance(record, PrimarySignalCandidateV3):
        return record.primary_signal_candidate_id
    if isinstance(record, CandidateFeatureMaterializationV3):
        return record.candidate_feature_materialization_id
    if isinstance(record, EligibilityDecisionV3):
        return record.eligibility_decision_id
    if isinstance(record, DecisionEventV3):
        return record.decision_event_id
    if isinstance(record, BarrierActivationV3):
        return record.barrier_activation_id
    if isinstance(record, LabelOutcomeV3):
        return record.label_outcome_id
    if isinstance(record, EventDependenceAssignmentV3):
        return record.assignment_id
    raise CanonicalizationError("unsupported ledger record")


def _record_native_hash(record: LedgerRecord, content_hash: str) -> str:
    value = getattr(record, "record_hash", None)
    return content_hash if value is None else canonical_hash(value, field="record_hash")


def _record_terminal_ts(record: LedgerRecord) -> datetime:
    if isinstance(record, ImmutableManifestV3):
        field = {
            ManifestType.SOURCE: "knowledge_cutoff_ts",
            ManifestType.PROTOCOL: "protocol_frozen_at",
            ManifestType.SPLIT: "as_of_ts",
            ManifestType.TRIAL_SPEC: "registered_at",
            ManifestType.TRIAL_RESULT: "completed_at",
        }[record.manifest_type]
        return utc_datetime(record.payload[field], field=field)
    if isinstance(record, CalendarSourceArtifactV3):
        return record.retrieved_at
    if isinstance(record, CalendarScheduleSnapshotV3):
        return record.frozen_at
    if isinstance(record, ActionProtocolV3):
        return record.frozen_at
    if isinstance(record, InstrumentMappingV3):
        return record.known_at
    if isinstance(record, SourceBundleMemberV3):
        return record.knowledge_cutoff_ts
    if isinstance(record, SourceBundleV3):
        return record.knowledge_cutoff_ts
    if isinstance(record, (FeatureDependencySlotV3, FeatureDefinitionV3)):
        return datetime(1970, 1, 1, tzinfo=timezone.utc)
    if isinstance(record, FeatureSchemaV3):
        return record.frozen_at
    if isinstance(record, ProviderAdapterPolicyV3):
        return record.frozen_at
    if isinstance(record, CaptureSegmentV3):
        return record.closed_at
    if isinstance(record, ObservationDerivationV3):
        return record.derived_at
    if isinstance(record, ObservationRevisionV3):
        return record.available_at
    if isinstance(record, ProviderMessageDispositionV3):
        return record.classified_at
    if isinstance(record, ObservationSelectionPolicyV3):
        return record.frozen_at
    if isinstance(record, EvidencePrefixV3):
        return record.assembled_at
    if isinstance(record, DependencySelectionProofV3):
        return record.computed_at
    if isinstance(record, PhysicalEvidenceGateV3):
        return record.evaluated_at
    if isinstance(record, InformationSetV3):
        return record.assembled_at
    if isinstance(record, ActionResolutionV3):
        return record.resolved_at
    if isinstance(record, PrimarySignalCandidateV3):
        return record.candidate_available_ts
    if isinstance(record, CandidateFeatureMaterializationV3):
        return record.feature_available_ts
    if isinstance(record, EligibilityDecisionV3):
        return record.evaluated_at
    if isinstance(record, DecisionEventV3):
        return record.decision_ts
    if isinstance(record, BarrierActivationV3):
        return record.activated_at
    if isinstance(record, LabelOutcomeV3):
        return record.label_known_ts
    if isinstance(record, EventDependenceAssignmentV3):
        return record.assignment_known_ts
    raise CanonicalizationError("unsupported ledger record")


def _semantic_claim(record: LedgerRecord) -> tuple[str, str, str | None, str]:
    """Return ``(head_type, key, expected_predecessor, new_head)``."""

    identity = _record_identity(record)
    if isinstance(record, ImmutableManifestV3):
        if record.manifest_type is ManifestType.SOURCE:
            payload = record.payload
            key = sha256_digest(
                {
                    "domain": "SourceManifestLineageKeyV1",
                    "source_contract_id": payload["source_contract_id"],
                    "source_dataset_id": payload["source_dataset_id"],
                }
            )
            return (
                "SOURCE_LINEAGE",
                key,
                payload["parent_source_manifest_id"],
                identity,
            )
        return (f"MANIFEST_{record.manifest_type.value}", identity, None, identity)
    if isinstance(record, CalendarSourceArtifactV3):
        return ("CALENDAR_SOURCE_ARTIFACT", identity, None, identity)
    if isinstance(record, CalendarScheduleSnapshotV3):
        key = sha256_digest(
            {
                "contract_id": record.contract_id,
                "domain": "CalendarScheduleLineageKeyV1",
                "venue_id": record.venue_id,
            }
        )
        return (
            "CALENDAR_SCHEDULE_LINEAGE",
            key,
            record.parent_calendar_snapshot_id,
            identity,
        )
    if isinstance(record, ActionProtocolV3):
        return ("ACTION_PROTOCOL", identity, None, identity)
    if isinstance(record, InstrumentMappingV3):
        key = sha256_digest(
            {
                "asset_id": record.asset_id,
                "domain": "InstrumentMappingLineageKeyV1",
                "source_contract_id": record.source_contract_id,
                "venue_id": record.venue_id,
            }
        )
        return (
            "INSTRUMENT_MAPPING_LINEAGE",
            key,
            record.parent_instrument_mapping_id,
            identity,
        )
    if isinstance(record, SourceBundleMemberV3):
        return (
            "SOURCE_BUNDLE_MEMBER_OBJECT",
            identity,
            None,
            identity,
        )
    if isinstance(record, SourceBundleV3):
        key = sha256_digest(
            {
                "domain": "SourceBundleLineageKeyV1",
                "source_contract_id": record.source_contract_id,
                "source_dataset_id": record.source_dataset_id,
            }
        )
        return (
            "SOURCE_BUNDLE_LINEAGE",
            key,
            record.parent_source_bundle_id,
            identity,
        )
    if isinstance(record, FeatureDependencySlotV3):
        return ("FEATURE_DEPENDENCY_SLOT", identity, None, identity)
    if isinstance(record, FeatureDefinitionV3):
        return ("FEATURE_DEFINITION", identity, None, identity)
    if isinstance(record, FeatureSchemaV3):
        return ("FEATURE_SCHEMA", identity, None, identity)
    if isinstance(record, ProviderAdapterPolicyV3):
        return ("PROVIDER_ADAPTER_POLICY", identity, None, identity)
    if isinstance(record, CaptureSegmentV3):
        return (
            "CAPTURE_SEGMENT_LINEAGE",
            record.capture_partition_id,
            record.parent_capture_segment_id,
            identity,
        )
    if isinstance(record, ObservationDerivationV3):
        return ("OBSERVATION_DERIVATION", identity, None, identity)
    if isinstance(record, ObservationRevisionV3):
        return (
            "OBSERVATION_REVISION_LINEAGE",
            record.observation_key,
            record.parent_observation_revision_id,
            identity,
        )
    if isinstance(record, ProviderMessageDispositionV3):
        return (
            "RAW_MESSAGE_DISPOSITION",
            record.message_receipt_id,
            None,
            identity,
        )
    if isinstance(record, ObservationSelectionPolicyV3):
        return (
            "OBSERVATION_SELECTION_POLICY",
            record.dependency_slot_id,
            None,
            identity,
        )
    if isinstance(record, EvidencePrefixV3):
        key = sha256_digest(
            {
                "adapter_policy_id": record.adapter_policy_id,
                "domain": "EvidencePrefixLineageKeyV1",
                "ledger_id": record.ledger_id,
                "source_member_key": record.source_member_key,
            }
        )
        return (
            "EVIDENCE_PREFIX_LINEAGE",
            key,
            record.parent_evidence_prefix_id,
            identity,
        )
    if isinstance(record, DependencySelectionProofV3):
        key = sha256_digest(
            {
                "dependency_slot_id": record.dependency_slot_id,
                "domain": "DependencySelectionProofKeyV1",
                "evidence_prefix_id": record.evidence_prefix_id,
                "observation_cutoff_ts": utc_iso(record.observation_cutoff_ts),
                "source_member_id": record.source_member_id,
            }
        )
        return ("DEPENDENCY_SELECTION_PROOF", key, None, identity)
    if isinstance(record, PhysicalEvidenceGateV3):
        key = sha256_digest(
            {
                "domain": "PhysicalEvidenceGateKeyV1",
                "gate_stage": record.gate_stage.value,
                "information_set_id": record.information_set_id,
            }
        )
        return ("PHYSICAL_EVIDENCE_GATE", key, None, identity)
    if isinstance(record, InformationSetV3):
        return ("INFORMATION_SET", record.information_set_id, None, identity)
    if isinstance(record, ActionResolutionV3):
        return ("ACTION_RESOLUTION", record.action_request_key, None, identity)
    if isinstance(record, PrimarySignalCandidateV3):
        return (
            "PRIMARY_SIGNAL_CANDIDATE",
            record.primary_signal_candidate_key,
            None,
            identity,
        )
    if isinstance(record, CandidateFeatureMaterializationV3):
        return (
            "CANDIDATE_FEATURE_MATERIALIZATION",
            record.candidate_feature_materialization_key,
            None,
            identity,
        )
    if isinstance(record, EligibilityDecisionV3):
        return ("ELIGIBILITY_DECISION", record.eligibility_key, None, identity)
    if isinstance(record, DecisionEventV3):
        return ("DECISION_EVENT", record.decision_event_key, None, identity)
    if isinstance(record, BarrierActivationV3):
        return ("BARRIER_ACTIVATION", record.decision_event_id, None, identity)
    if isinstance(record, LabelOutcomeV3):
        return (
            "LABEL_OUTCOME",
            record.decision_event_id,
            record.supersedes_label_outcome_id,
            identity,
        )
    if isinstance(record, EventDependenceAssignmentV3):
        key = sha256_digest(
            {
                "decision_event_id": record.decision_event_id,
                "dependence_policy_id": record.dependence_policy_id,
                "domain": "EventDependenceAssignmentKeyV1",
            }
        )
        return (
            "EVENT_DEPENDENCE_ASSIGNMENT",
            key,
            record.supersedes_assignment_id,
            identity,
        )
    raise CanonicalizationError("unsupported ledger record")


def _derive_ledger_id(
    *,
    nonce: str,
    created_at: datetime | str,
    journal_mode: str,
    max_object_bytes: int,
) -> str:
    return sha256_digest(
        {
            "canonicalization_version": CANONICALIZATION_VERSION,
            "created_at": utc_iso(utc_datetime(created_at, field="created_at")),
            "domain": "RiskYieldMMLedgerIdentityV1",
            "journal_mode": journal_mode,
            "max_object_bytes": canonical_safe_int(
                max_object_bytes,
                field="max_object_bytes",
                minimum=1,
                maximum=64 * 1024 * 1024,
            ),
            "nonce": canonical_hash(nonce, field="ledger_identity_nonce"),
            "schema_version": LEDGER_SCHEMA_VERSION,
            "validation_version": LEDGER_VALIDATION_VERSION,
        }
    )


_SCHEMA_SQL = """
CREATE TABLE ledger_meta (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    ledger_id TEXT NOT NULL CHECK (length(ledger_id) = 64),
    ledger_identity_nonce TEXT NOT NULL CHECK (
        length(ledger_identity_nonce) = 64
    ),
    schema_version TEXT NOT NULL,
    canonicalization_version TEXT NOT NULL,
    validation_version TEXT NOT NULL,
    created_at TEXT NOT NULL,
    journal_mode TEXT NOT NULL,
    max_object_bytes INTEGER NOT NULL CHECK (max_object_bytes > 0)
) STRICT;

CREATE TABLE objects (
    content_hash TEXT PRIMARY KEY CHECK (length(content_hash) = 64),
    record_kind TEXT NOT NULL,
    identity_id TEXT NOT NULL CHECK (length(identity_id) = 64),
    record_hash TEXT NOT NULL CHECK (length(record_hash) = 64),
    semantic_key TEXT NOT NULL CHECK (length(semantic_key) = 64),
    canonical_blob BLOB NOT NULL,
    first_receipt_sequence INTEGER NOT NULL UNIQUE,
    UNIQUE (record_kind, identity_id),
    UNIQUE (record_kind, record_hash),
    FOREIGN KEY (first_receipt_sequence) REFERENCES receipts(global_sequence)
        DEFERRABLE INITIALLY DEFERRED
) STRICT;

CREATE TABLE receipts (
    global_sequence INTEGER PRIMARY KEY,
    channel TEXT NOT NULL,
    channel_sequence INTEGER NOT NULL,
    receipt_hash TEXT NOT NULL UNIQUE CHECK (length(receipt_hash) = 64),
    receipt_ts TEXT NOT NULL,
    operation TEXT NOT NULL,
    record_kind TEXT NOT NULL,
    identity_id TEXT NOT NULL CHECK (length(identity_id) = 64),
    record_hash TEXT NOT NULL CHECK (length(record_hash) = 64),
    content_hash TEXT NOT NULL CHECK (length(content_hash) = 64),
    semantic_key TEXT NOT NULL CHECK (length(semantic_key) = 64),
    head_type TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    request_hash TEXT NOT NULL CHECK (length(request_hash) = 64),
    expected_head TEXT,
    new_head TEXT NOT NULL CHECK (length(new_head) = 64),
    previous_global_receipt_hash TEXT NOT NULL CHECK (
        length(previous_global_receipt_hash) = 64
    ),
    previous_channel_receipt_hash TEXT NOT NULL CHECK (
        length(previous_channel_receipt_hash) = 64
    ),
    canonical_blob BLOB NOT NULL,
    UNIQUE (channel, channel_sequence)
) STRICT;

CREATE TABLE head_transitions (
    receipt_sequence INTEGER PRIMARY KEY,
    head_type TEXT NOT NULL,
    semantic_key TEXT NOT NULL CHECK (length(semantic_key) = 64),
    previous_identity_id TEXT,
    new_identity_id TEXT NOT NULL CHECK (length(new_identity_id) = 64),
    receipt_hash TEXT NOT NULL UNIQUE CHECK (length(receipt_hash) = 64),
    FOREIGN KEY (receipt_sequence) REFERENCES receipts(global_sequence)
        DEFERRABLE INITIALLY DEFERRED
) STRICT;

CREATE INDEX head_transitions_lookup
    ON head_transitions(head_type, semantic_key, receipt_sequence DESC);

CREATE TABLE checkpoints (
    checkpoint_id TEXT PRIMARY KEY CHECK (length(checkpoint_id) = 64),
    content_hash TEXT NOT NULL UNIQUE CHECK (length(content_hash) = 64),
    key_id TEXT NOT NULL,
    signature_algorithm TEXT NOT NULL,
    signed_global_sequence INTEGER NOT NULL,
    previous_checkpoint_id TEXT,
    receipt_sequence INTEGER NOT NULL UNIQUE,
    canonical_blob BLOB NOT NULL,
    FOREIGN KEY (receipt_sequence) REFERENCES receipts(global_sequence)
        DEFERRABLE INITIALLY DEFERRED
) STRICT;

CREATE TABLE holdout_grants (
    grant_id TEXT PRIMARY KEY CHECK (length(grant_id) = 64),
    content_hash TEXT NOT NULL UNIQUE CHECK (length(content_hash) = 64),
    protocol_manifest_id TEXT NOT NULL UNIQUE CHECK (
        length(protocol_manifest_id) = 64
    ),
    split_manifest_id TEXT NOT NULL UNIQUE CHECK (length(split_manifest_id) = 64),
    checkpoint_id TEXT NOT NULL CHECK (length(checkpoint_id) = 64),
    receipt_sequence INTEGER NOT NULL UNIQUE,
    canonical_blob BLOB NOT NULL,
    FOREIGN KEY (checkpoint_id) REFERENCES checkpoints(checkpoint_id),
    FOREIGN KEY (receipt_sequence) REFERENCES receipts(global_sequence)
        DEFERRABLE INITIALLY DEFERRED
) STRICT;

CREATE TRIGGER ledger_meta_no_update BEFORE UPDATE ON ledger_meta
BEGIN SELECT RAISE(ABORT, 'ledger_meta is immutable'); END;
CREATE TRIGGER ledger_meta_no_delete BEFORE DELETE ON ledger_meta
BEGIN SELECT RAISE(ABORT, 'ledger_meta is immutable'); END;
CREATE TRIGGER objects_no_update BEFORE UPDATE ON objects
BEGIN SELECT RAISE(ABORT, 'objects are immutable'); END;
CREATE TRIGGER objects_no_delete BEFORE DELETE ON objects
BEGIN SELECT RAISE(ABORT, 'objects are immutable'); END;
CREATE TRIGGER receipts_no_update BEFORE UPDATE ON receipts
BEGIN SELECT RAISE(ABORT, 'receipts are immutable'); END;
CREATE TRIGGER receipts_no_delete BEFORE DELETE ON receipts
BEGIN SELECT RAISE(ABORT, 'receipts are immutable'); END;
CREATE TRIGGER transitions_no_update BEFORE UPDATE ON head_transitions
BEGIN SELECT RAISE(ABORT, 'head transitions are immutable'); END;
CREATE TRIGGER transitions_no_delete BEFORE DELETE ON head_transitions
BEGIN SELECT RAISE(ABORT, 'head transitions are immutable'); END;
CREATE TRIGGER checkpoints_no_update BEFORE UPDATE ON checkpoints
BEGIN SELECT RAISE(ABORT, 'checkpoints are immutable'); END;
CREATE TRIGGER checkpoints_no_delete BEFORE DELETE ON checkpoints
BEGIN SELECT RAISE(ABORT, 'checkpoints are immutable'); END;
CREATE TRIGGER grants_no_update BEFORE UPDATE ON holdout_grants
BEGIN SELECT RAISE(ABORT, 'holdout grants are immutable'); END;
CREATE TRIGGER grants_no_delete BEFORE DELETE ON holdout_grants
BEGIN SELECT RAISE(ABORT, 'holdout grants are immutable'); END;
"""

_IMMUTABILITY_TRIGGERS = frozenset(
    {
        "ledger_meta_no_update",
        "ledger_meta_no_delete",
        "objects_no_update",
        "objects_no_delete",
        "receipts_no_update",
        "receipts_no_delete",
        "transitions_no_update",
        "transitions_no_delete",
        "checkpoints_no_update",
        "checkpoints_no_delete",
        "grants_no_update",
        "grants_no_delete",
    }
)

_SCHEMA_FINGERPRINT_DOMAIN = "RiskYieldMMSQLiteSchemaFingerprintV1"
_EXPECTED_SCHEMA_FINGERPRINT: str | None = None
_EXPECTED_SCHEMA_FINGERPRINT_LOCK = threading.Lock()


def _schema_fingerprint(connection: sqlite3.Connection) -> str:
    """Hash every application-owned SQLite schema definition exactly."""

    rows = connection.execute(
        """
        SELECT type, name, tbl_name, sql
        FROM sqlite_schema
        WHERE name NOT LIKE 'sqlite_%' AND sql IS NOT NULL
        ORDER BY type, name, tbl_name
        """
    ).fetchall()
    return sha256_digest(
        {
            "domain": _SCHEMA_FINGERPRINT_DOMAIN,
            "entries": [
                {
                    "name": str(row[1]),
                    "sql": str(row[3]),
                    "table": str(row[2]),
                    "type": str(row[0]),
                }
                for row in rows
            ],
        }
    )


def _expected_schema_fingerprint() -> str:
    global _EXPECTED_SCHEMA_FINGERPRINT

    if _EXPECTED_SCHEMA_FINGERPRINT is None:
        with _EXPECTED_SCHEMA_FINGERPRINT_LOCK:
            if _EXPECTED_SCHEMA_FINGERPRINT is None:
                connection = sqlite3.connect(":memory:", isolation_level=None)
                try:
                    connection.executescript(_SCHEMA_SQL)
                    _EXPECTED_SCHEMA_FINGERPRINT = _schema_fingerprint(connection)
                finally:
                    connection.close()
    assert _EXPECTED_SCHEMA_FINGERPRINT is not None
    return _EXPECTED_SCHEMA_FINGERPRINT


class V3GovernanceLedger:
    """Local append-only governance ledger with one authoritative writer."""

    def __init__(
        self,
        path: str | os.PathLike[str],
        *,
        read_only: bool = False,
        journal_mode: str = "DELETE",
        clock: Callable[[], datetime] | None = None,
        max_object_bytes: int | None = None,
        fault_injector: Callable[[str], None] | None = None,
    ) -> None:
        if sqlite3.sqlite_version_info < MINIMUM_SQLITE_VERSION:
            raise LedgerConfigurationError(
                "SQLite 3.37 or newer is required for STRICT ledger tables"
            )
        self.path = Path(path).expanduser().absolute()
        self.read_only = bool(read_only)
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._fault_injector = fault_injector
        self._lock_fd: int | None = None
        self._closed = False
        self._validate_storage_parent(create=not self.read_only)
        if self.read_only:
            if not self.path.exists():
                raise LedgerNotFoundError(f"ledger does not exist: {self.path}")
            self._validate_storage_file(self.path, expected_mode=0o600)
            self._validate_existing_lock_permissions()
            self._validate_sidecar_permissions()
            self._connection = self._connect_read_only()
            try:
                self._configure_connection(read_only=True)
                self._validate_meta_runtime()
                self._validate_sidecar_permissions()
            except Exception:
                self._connection.close()
                raise
            return

        requested_mode = journal_mode.strip().upper()
        if requested_mode not in {"DELETE", "WAL"}:
            raise LedgerConfigurationError("journal_mode must be DELETE or WAL")
        if requested_mode == "WAL" and not sqlite_wal_runtime_is_safe():
            raise LedgerConfigurationError(
                "WAL is not certified on this SQLite runtime; use DELETE or "
                "upgrade to a fixed SQLite release"
            )
        requested_max_bytes = (
            None
            if max_object_bytes is None
            else canonical_safe_int(
                max_object_bytes,
                field="max_object_bytes",
                minimum=1,
                maximum=64 * 1024 * 1024,
            )
        )
        self._acquire_writer_lock()
        existed = self.path.exists()
        created_database = False
        try:
            if existed:
                self._validate_storage_file(self.path, expected_mode=0o600)
                self._validate_sidecar_permissions()
            else:
                self._secure_create_regular_file(self.path, mode=0o600)
                created_database = True
            self._connection = sqlite3.connect(
                self.path,
                isolation_level=None,
                timeout=5.0,
            )
            self._validate_storage_file(self.path, expected_mode=0o600)
            self._configure_connection(read_only=False)
            if existed:
                meta = self._read_meta()
                if meta["journal_mode"] != requested_mode:
                    raise LedgerConfigurationError(
                        "requested journal mode differs from immutable ledger metadata"
                    )
                if (
                    requested_max_bytes is not None
                    and int(meta["max_object_bytes"]) != requested_max_bytes
                ):
                    raise LedgerConfigurationError(
                        "max_object_bytes differs from immutable ledger metadata"
                    )
                actual_mode = self._set_durability_mode(requested_mode)
            else:
                max_bytes = (
                    DEFAULT_MAX_OBJECT_BYTES
                    if requested_max_bytes is None
                    else requested_max_bytes
                )
                actual_mode = self._set_durability_mode(requested_mode)
                self._initialize_schema(
                    journal_mode=actual_mode,
                    max_object_bytes=max_bytes,
                )
            self._validate_meta_runtime()
            self._validate_sidecar_permissions()
            # A writer must not extend structurally corrupted history. The
            # external checkpoint remains a separate operator trust input, but
            # every writable reopen first proves the complete local ledger.
            self.verify()
        except Exception:
            connection = getattr(self, "_connection", None)
            if connection is not None:
                connection.close()
            if created_database:
                for candidate in (
                    self.path,
                    Path(f"{self.path}-journal"),
                    Path(f"{self.path}-wal"),
                    Path(f"{self.path}-shm"),
                ):
                    try:
                        candidate.unlink(missing_ok=True)
                    except OSError:
                        pass
            self._release_writer_lock()
            raise

    @classmethod
    def open_read_only(
        cls,
        path: str | os.PathLike[str],
    ) -> V3GovernanceLedger:
        return cls(path, read_only=True)

    def __enter__(self) -> V3GovernanceLedger:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        if self._closed:
            return
        self._connection.close()
        self._release_writer_lock()
        self._closed = True

    @property
    def ledger_id(self) -> str:
        return str(self._read_meta()["ledger_id"])

    @property
    def journal_mode(self) -> str:
        return str(self._read_meta()["journal_mode"])

    def _validate_storage_parent(self, *, create: bool) -> None:
        parent = self.path.parent
        if create and not parent.exists():
            parent.mkdir(parents=True, mode=0o700)
        if not parent.exists() or not parent.is_dir():
            raise LedgerSecurityError("ledger parent directory does not exist")
        if parent.is_symlink():
            raise LedgerSecurityError("ledger parent directory must not be a symlink")
        info = parent.stat()
        if hasattr(os, "getuid") and info.st_uid != os.getuid():
            raise LedgerSecurityError("ledger parent must be owned by this user")
        if stat.S_IMODE(info.st_mode) != 0o700:
            raise LedgerSecurityError("ledger parent directory must have mode 0700")
        fs_type = _filesystem_type(parent)
        if fs_type in _UNSAFE_FILESYSTEMS:
            raise LedgerSecurityError(
                f"ledger filesystem {fs_type!r} is not certified for SQLite locking"
            )
        if self.path.is_symlink():
            raise LedgerSecurityError("ledger database must not be a symlink")

    @staticmethod
    def _validate_storage_file(path: Path, *, expected_mode: int) -> None:
        try:
            info = path.stat(follow_symlinks=False)
        except FileNotFoundError as exc:
            raise LedgerNotFoundError(f"missing ledger file: {path}") from exc
        if not stat.S_ISREG(info.st_mode):
            raise LedgerSecurityError(f"ledger path is not a regular file: {path}")
        if info.st_nlink != 1:
            raise LedgerSecurityError(f"ledger file must not have hard links: {path}")
        if hasattr(os, "getuid") and info.st_uid != os.getuid():
            raise LedgerSecurityError(f"ledger file has the wrong owner: {path}")
        if stat.S_IMODE(info.st_mode) != expected_mode:
            raise LedgerSecurityError(
                f"ledger file must have mode {expected_mode:04o}: {path}"
            )

    @classmethod
    def _validate_open_file(
        cls,
        fd: int,
        path: Path,
        *,
        expected_mode: int,
    ) -> None:
        descriptor = os.fstat(fd)
        cls._validate_storage_file(path, expected_mode=expected_mode)
        pathname = path.stat(follow_symlinks=False)
        if (descriptor.st_dev, descriptor.st_ino) != (
            pathname.st_dev,
            pathname.st_ino,
        ):
            raise LedgerSecurityError(f"ledger path changed while opening: {path}")

    @classmethod
    def _secure_create_regular_file(cls, path: Path, *, mode: int) -> None:
        flags = os.O_RDWR | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            fd = os.open(path, flags, mode)
        except FileExistsError as exc:
            raise LedgerSecurityError(
                f"ledger path appeared during secure creation: {path}"
            ) from exc
        try:
            os.fchmod(fd, mode)
            cls._validate_open_file(fd, path, expected_mode=mode)
            os.fsync(fd)
        except Exception:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
            raise
        finally:
            os.close(fd)

    def _validate_sidecar_permissions(self) -> None:
        for suffix in ("-journal", "-wal", "-shm"):
            candidate = Path(f"{self.path}{suffix}")
            if candidate.exists() or candidate.is_symlink():
                self._validate_storage_file(candidate, expected_mode=0o600)

    def _validate_existing_lock_permissions(self) -> None:
        lock_path = Path(f"{self.path}.writer.lock")
        if lock_path.exists() or lock_path.is_symlink():
            self._validate_storage_file(lock_path, expected_mode=0o600)

    def _acquire_writer_lock(self) -> None:
        lock_path = Path(f"{self.path}.writer.lock")
        flags = os.O_RDWR
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            create_flags = flags | os.O_CREAT | os.O_EXCL
            fd = os.open(lock_path, create_flags, 0o600)
            os.fchmod(fd, 0o600)
        except FileExistsError:
            self._validate_storage_file(lock_path, expected_mode=0o600)
            fd = os.open(lock_path, flags)
        try:
            self._validate_open_file(fd, lock_path, expected_mode=0o600)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise LedgerWriterLockError(
                    "another process already owns the authoritative writer lock"
                ) from exc
        except Exception:
            os.close(fd)
            raise
        self._lock_fd = fd

    def _release_writer_lock(self) -> None:
        if self._lock_fd is None:
            return
        try:
            fcntl.flock(self._lock_fd, fcntl.LOCK_UN)
        finally:
            os.close(self._lock_fd)
            self._lock_fd = None

    def _connect_read_only(self) -> sqlite3.Connection:
        uri = f"file:{quote(str(self.path))}?mode=ro"
        return sqlite3.connect(uri, uri=True, isolation_level=None, timeout=5.0)

    def _configure_connection(self, *, read_only: bool) -> None:
        connection = self._connection
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA trusted_schema = OFF")
        connection.execute("PRAGMA cell_size_check = ON")
        connection.execute("PRAGMA mmap_size = 0")
        try:
            connection.enable_load_extension(False)
        except (AttributeError, sqlite3.NotSupportedError):
            pass
        setconfig = getattr(connection, "setconfig", None)
        if setconfig is not None:
            defensive = getattr(sqlite3, "SQLITE_DBCONFIG_DEFENSIVE", None)
            trusted = getattr(sqlite3, "SQLITE_DBCONFIG_TRUSTED_SCHEMA", None)
            if defensive is not None:
                setconfig(defensive, True)
            if trusted is not None:
                setconfig(trusted, False)
        if read_only and connection.execute("PRAGMA query_only").fetchone()[0] != 1:
            connection.execute("PRAGMA query_only = ON")

    def _set_durability_mode(self, requested: str) -> str:
        result = self._connection.execute(
            f"PRAGMA journal_mode = {requested}"
        ).fetchone()
        actual = str(result[0]).upper() if result else ""
        if actual != requested:
            raise LedgerConfigurationError(
                f"SQLite did not activate requested journal mode {requested}"
            )
        synchronous = "FULL" if requested == "WAL" else "EXTRA"
        self._connection.execute(f"PRAGMA synchronous = {synchronous}")
        expected_value = 2 if synchronous == "FULL" else 3
        if (
            self._connection.execute("PRAGMA synchronous").fetchone()[0]
            != expected_value
        ):
            raise LedgerConfigurationError(
                f"SQLite did not activate synchronous={synchronous}"
            )
        return actual

    def _initialize_schema(self, *, journal_mode: str, max_object_bytes: int) -> None:
        created_at = utc_iso(self._now(), field="created_at")
        identity_nonce = os.urandom(32).hex()
        ledger_id = _derive_ledger_id(
            nonce=identity_nonce,
            created_at=created_at,
            journal_mode=journal_mode,
            max_object_bytes=max_object_bytes,
        )
        try:
            self._connection.executescript(f"BEGIN IMMEDIATE;\n{_SCHEMA_SQL}")
            self._connection.execute(
                """
                INSERT INTO ledger_meta(
                    singleton, ledger_id, ledger_identity_nonce, schema_version,
                    canonicalization_version, validation_version,
                    created_at, journal_mode, max_object_bytes
                ) VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ledger_id,
                    identity_nonce,
                    LEDGER_SCHEMA_VERSION,
                    CANONICALIZATION_VERSION,
                    LEDGER_VALIDATION_VERSION,
                    created_at,
                    journal_mode,
                    max_object_bytes,
                ),
            )
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise

    def _read_meta(self) -> sqlite3.Row | Mapping[str, Any]:
        previous_factory = self._connection.row_factory
        self._connection.row_factory = sqlite3.Row
        try:
            row = self._connection.execute(
                "SELECT * FROM ledger_meta WHERE singleton = 1"
            ).fetchone()
        except sqlite3.DatabaseError as exc:
            raise LedgerConfigurationError(
                "database is not a V3 governance ledger"
            ) from exc
        finally:
            self._connection.row_factory = previous_factory
        if row is None:
            raise LedgerConfigurationError("ledger metadata is missing")
        if row["schema_version"] != LEDGER_SCHEMA_VERSION:
            raise LedgerConfigurationError("unsupported ledger schema version")
        if row["canonicalization_version"] != CANONICALIZATION_VERSION:
            raise LedgerConfigurationError("unsupported canonicalization version")
        if row["validation_version"] != LEDGER_VALIDATION_VERSION:
            raise LedgerConfigurationError("unsupported ledger validation version")
        try:
            ledger_id = canonical_hash(row["ledger_id"], field="ledger_id")
            identity_nonce = canonical_hash(
                row["ledger_identity_nonce"], field="ledger_identity_nonce"
            )
            utc_datetime(row["created_at"], field="created_at")
            max_object_bytes = canonical_safe_int(
                row["max_object_bytes"],
                field="max_object_bytes",
                minimum=1,
                maximum=64 * 1024 * 1024,
            )
        except CanonicalizationError as exc:
            raise LedgerConfigurationError("ledger metadata is invalid") from exc
        expected_ledger_id = _derive_ledger_id(
            nonce=identity_nonce,
            created_at=row["created_at"],
            journal_mode=str(row["journal_mode"]),
            max_object_bytes=max_object_bytes,
        )
        if ledger_id != expected_ledger_id:
            raise LedgerConfigurationError(
                "ledger identity does not bind the stored immutable metadata"
            )
        return row

    def _validate_meta_runtime(self) -> None:
        meta = self._read_meta()
        expected_mode = str(meta["journal_mode"])
        if expected_mode not in {"DELETE", "WAL"}:
            raise LedgerConfigurationError(
                "ledger declares an unsupported journal mode"
            )
        actual_mode = str(
            self._connection.execute("PRAGMA journal_mode").fetchone()[0]
        ).upper()
        if actual_mode != expected_mode:
            raise LedgerConfigurationError(
                "active SQLite journal mode differs from immutable ledger metadata"
            )
        if not self.read_only:
            expected_synchronous = 2 if expected_mode == "WAL" else 3
            actual_synchronous = int(
                self._connection.execute("PRAGMA synchronous").fetchone()[0]
            )
            if actual_synchronous != expected_synchronous:
                expected_name = "FULL" if expected_mode == "WAL" else "EXTRA"
                raise LedgerConfigurationError(
                    f"active SQLite synchronous mode is not {expected_name}"
                )
        if self._connection.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
            raise LedgerConfigurationError("SQLite foreign-key enforcement is disabled")
        if self._connection.execute("PRAGMA trusted_schema").fetchone()[0] != 0:
            raise LedgerConfigurationError("SQLite trusted_schema must remain disabled")
        if self._connection.execute("PRAGMA mmap_size").fetchone()[0] != 0:
            raise LedgerConfigurationError("SQLite memory mapping must remain disabled")
        if expected_mode == "WAL" and not sqlite_wal_runtime_is_safe():
            raise LedgerConfigurationError(
                "this runtime is not certified to open a WAL governance ledger"
            )

    def _now(self) -> datetime:
        value = self._clock()
        return utc_datetime(value, field="ledger_clock")

    def _fault(self, stage: str) -> None:
        if self._fault_injector is not None:
            self._fault_injector(stage)

    @contextmanager
    def _transaction(self) -> Iterator[None]:
        if self.read_only:
            raise LedgerConfigurationError("read-only ledger cannot mutate state")
        try:
            self._validate_meta_runtime()
            self._validate_sidecar_permissions()
            self._connection.execute("BEGIN IMMEDIATE")
            yield
            self._fault("before_commit")
            self._validate_sidecar_permissions()
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise

    def _manifest_registry(
        self,
        *,
        before_sequence: int | None = None,
    ) -> dict[str, ImmutableManifestV3]:
        sql = (
            "SELECT canonical_blob FROM objects WHERE record_kind = ?"
            + (" AND first_receipt_sequence < ?" if before_sequence is not None else "")
            + " ORDER BY first_receipt_sequence"
        )
        params: tuple[Any, ...] = (LedgerRecordKind.MANIFEST.value,)
        if before_sequence is not None:
            params += (before_sequence,)
        result: dict[str, ImmutableManifestV3] = {}
        for (blob,) in self._connection.execute(sql, params):
            item = _parse_record(LedgerRecordKind.MANIFEST, bytes(blob))
            assert isinstance(item, ImmutableManifestV3)
            result[item.manifest_id] = item
        return result

    def _evidence_registry(
        self,
        *,
        before_sequence: int | None = None,
    ) -> dict[str, EvidenceRecordV3]:
        placeholders = ",".join("?" for _ in _EVIDENCE_RECORD_KINDS)
        sql = (
            "SELECT record_kind, canonical_blob FROM objects "
            f"WHERE record_kind IN ({placeholders})"
            + (" AND first_receipt_sequence < ?" if before_sequence is not None else "")
            + " ORDER BY first_receipt_sequence"
        )
        ordered_kinds = tuple(
            sorted(_EVIDENCE_RECORD_KINDS, key=lambda item: item.value)
        )
        params: tuple[Any, ...] = tuple(item.value for item in ordered_kinds)
        if before_sequence is not None:
            params += (before_sequence,)
        result: dict[str, EvidenceRecordV3] = {}
        for raw_kind, blob in self._connection.execute(sql, params):
            kind = LedgerRecordKind(str(raw_kind))
            item = _parse_record(kind, bytes(blob))
            if not isinstance(
                item,
                (
                    CalendarSourceArtifactV3,
                    CalendarScheduleSnapshotV3,
                    ActionProtocolV3,
                    InstrumentMappingV3,
                    SourceBundleMemberV3,
                    SourceBundleV3,
                    FeatureDependencySlotV3,
                    FeatureDefinitionV3,
                    FeatureSchemaV3,
                    ProviderAdapterPolicyV3,
                    ObservationSelectionPolicyV3,
                ),
            ):
                raise LedgerVerificationError("evidence registry has invalid object")
            result[_record_identity(item)] = item
        return result

    def _physical_registry(
        self,
        *,
        before_sequence: int | None = None,
    ) -> dict[str, LedgerRecord]:
        """Return physical-policy and observation objects in receipt order."""

        placeholders = ",".join("?" for _ in _PHYSICAL_RECORD_KINDS)
        sql = (
            "SELECT record_kind, canonical_blob FROM objects "
            f"WHERE record_kind IN ({placeholders})"
            + (" AND first_receipt_sequence < ?" if before_sequence is not None else "")
            + " ORDER BY first_receipt_sequence"
        )
        ordered_kinds = tuple(
            sorted(_PHYSICAL_RECORD_KINDS, key=lambda item: item.value)
        )
        params: tuple[Any, ...] = tuple(item.value for item in ordered_kinds)
        if before_sequence is not None:
            params += (before_sequence,)
        result: dict[str, LedgerRecord] = {}
        for raw_kind, blob in self._connection.execute(sql, params):
            kind = LedgerRecordKind(str(raw_kind))
            item = _parse_record(kind, bytes(blob))
            if not isinstance(
                item,
                (
                    ProviderAdapterPolicyV3,
                    CaptureSegmentV3,
                    ObservationDerivationV3,
                    ObservationRevisionV3,
                    ProviderMessageDispositionV3,
                    ObservationSelectionPolicyV3,
                    EvidencePrefixV3,
                    DependencySelectionProofV3,
                    PhysicalEvidenceGateV3,
                ),
            ):
                raise LedgerVerificationError("physical registry has invalid object")
            result[_record_identity(item)] = item
        return result

    def _load_record(
        self,
        kind: LedgerRecordKind,
        identity_id: str,
        *,
        before_sequence: int | None = None,
    ) -> LedgerRecord:
        identity = canonical_hash(identity_id, field="identity_id")
        sql = """
            SELECT canonical_blob FROM objects
            WHERE record_kind = ? AND identity_id = ?
        """
        params: tuple[Any, ...] = (kind.value, identity)
        if before_sequence is not None:
            sql += " AND first_receipt_sequence < ?"
            params += (before_sequence,)
        row = self._connection.execute(sql, params).fetchone()
        if row is None:
            raise LedgerNotFoundError(f"missing {kind.value} object {identity_id}")
        return _parse_record(kind, bytes(row[0]))

    def get_record(
        self,
        kind: LedgerRecordKind | str,
        identity_id: str,
    ) -> LedgerRecord:
        try:
            normalized = (
                kind if isinstance(kind, LedgerRecordKind) else LedgerRecordKind(kind)
            )
        except (TypeError, ValueError) as exc:
            raise CanonicalizationError("unsupported record kind") from exc
        return self._load_record(normalized, identity_id)

    def get_receipt(self, global_sequence: int) -> LedgerReceipt:
        sequence = canonical_safe_int(
            global_sequence, field="global_sequence", minimum=1
        )
        row = self._connection.execute(
            "SELECT canonical_blob FROM receipts WHERE global_sequence = ?",
            (sequence,),
        ).fetchone()
        if row is None:
            raise LedgerNotFoundError(f"missing receipt sequence {sequence}")
        return LedgerReceipt.from_mapping(
            _parse_json_object(bytes(row[0]), context="LedgerReceipt")
        )

    def receipt_for_idempotency_key(self, idempotency_key: str) -> LedgerReceipt:
        key = canonical_identifier(
            idempotency_key, field="idempotency_key", maximum=256
        )
        row = self._connection.execute(
            "SELECT canonical_blob FROM receipts WHERE idempotency_key = ?",
            (key,),
        ).fetchone()
        if row is None:
            raise LedgerNotFoundError(f"unknown idempotency key {key!r}")
        return LedgerReceipt.from_mapping(
            _parse_json_object(bytes(row[0]), context="LedgerReceipt")
        )

    def active_head(self, head_type: str, semantic_key: str) -> str | None:
        normalized_type = canonical_identifier(head_type, field="head_type")
        key = canonical_hash(semantic_key, field="semantic_key")
        row = self._connection.execute(
            """
            SELECT new_identity_id FROM head_transitions
            WHERE head_type = ? AND semantic_key = ?
            ORDER BY receipt_sequence DESC LIMIT 1
            """,
            (normalized_type, key),
        ).fetchone()
        return None if row is None else str(row[0])

    def _idempotent_receipt(
        self,
        *,
        idempotency_key: str,
        request_hash: str,
    ) -> LedgerReceipt | None:
        row = self._connection.execute(
            """
            SELECT request_hash, canonical_blob FROM receipts
            WHERE idempotency_key = ?
            """,
            (idempotency_key,),
        ).fetchone()
        if row is None:
            return None
        if row[0] != request_hash:
            raise LedgerIdempotencyConflictError(
                "idempotency key was already used for another request"
            )
        return LedgerReceipt.from_mapping(
            _parse_json_object(bytes(row[1]), context="LedgerReceipt")
        )

    def _last_receipt_state(
        self,
        channel: LedgerChannel,
    ) -> tuple[int, str, datetime | None, int, str]:
        global_row = self._connection.execute(
            """
            SELECT global_sequence, receipt_hash, receipt_ts
            FROM receipts ORDER BY global_sequence DESC LIMIT 1
            """
        ).fetchone()
        if global_row is None:
            global_sequence = 0
            global_hash = GENESIS_HASH
            last_ts = None
        else:
            global_sequence = int(global_row[0])
            global_hash = str(global_row[1])
            last_ts = utc_datetime(global_row[2], field="receipt_ts")
        channel_row = self._connection.execute(
            """
            SELECT channel_sequence, receipt_hash FROM receipts
            WHERE channel = ? ORDER BY channel_sequence DESC LIMIT 1
            """,
            (channel.value,),
        ).fetchone()
        if channel_row is None:
            channel_sequence = 0
            channel_hash = GENESIS_HASH
        else:
            channel_sequence = int(channel_row[0])
            channel_hash = str(channel_row[1])
        return (
            global_sequence,
            global_hash,
            last_ts,
            channel_sequence,
            channel_hash,
        )

    def _issue_receipt(
        self,
        *,
        channel: LedgerChannel,
        operation: LedgerOperation,
        record_kind: str,
        identity_id: str,
        record_hash: str,
        content_hash: str,
        semantic_key: str,
        head_type: str,
        expected_head: str | None,
        new_head: str,
        idempotency_key: str,
        request_hash: str,
        minimum_ts: datetime,
        governance_payload_hash: str | None = None,
        receipt_ts: datetime | None = None,
    ) -> LedgerReceipt:
        (
            global_sequence,
            global_hash,
            last_ts,
            channel_sequence,
            channel_hash,
        ) = self._last_receipt_state(channel)
        timestamp = self._now() if receipt_ts is None else receipt_ts
        created_at = utc_datetime(self._read_meta()["created_at"], field="created_at")
        if timestamp < created_at:
            raise LedgerConflictError("ledger receipt time precedes ledger creation")
        if timestamp < minimum_ts:
            raise LedgerConflictError(
                "ledger receipt time precedes information availability"
            )
        if last_ts is not None and timestamp < last_ts:
            raise LedgerConflictError("ledger clock moved backwards")
        receipt = LedgerReceipt(
            ledger_id=self.ledger_id,
            global_sequence=global_sequence + 1,
            channel=channel,
            channel_sequence=channel_sequence + 1,
            receipt_ts=timestamp,
            operation=operation,
            record_kind=record_kind,
            identity_id=identity_id,
            record_hash=record_hash,
            content_hash=content_hash,
            semantic_key=semantic_key,
            head_type=head_type,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            expected_head=expected_head,
            new_head=new_head,
            previous_global_receipt_hash=global_hash,
            previous_channel_receipt_hash=channel_hash,
            governance_payload_hash=governance_payload_hash,
        )
        blob = canonical_json_bytes(receipt.as_dict())
        self._connection.execute(
            """
            INSERT INTO receipts(
                global_sequence, channel, channel_sequence, receipt_hash,
                receipt_ts, operation, record_kind, identity_id, record_hash,
                content_hash, semantic_key, head_type, idempotency_key, request_hash,
                expected_head, new_head, previous_global_receipt_hash,
                previous_channel_receipt_hash, canonical_blob
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                receipt.global_sequence,
                receipt.channel.value,
                receipt.channel_sequence,
                receipt.receipt_hash,
                utc_iso(receipt.receipt_ts),
                receipt.operation.value,
                receipt.record_kind,
                receipt.identity_id,
                receipt.record_hash,
                receipt.content_hash,
                receipt.semantic_key,
                receipt.head_type,
                receipt.idempotency_key,
                receipt.request_hash,
                receipt.expected_head,
                receipt.new_head,
                receipt.previous_global_receipt_hash,
                receipt.previous_channel_receipt_hash,
                blob,
            ),
        )
        self._fault("after_receipt_insert")
        self._connection.execute(
            """
            INSERT INTO head_transitions(
                receipt_sequence, head_type, semantic_key,
                previous_identity_id, new_identity_id, receipt_hash
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                receipt.global_sequence,
                head_type,
                semantic_key,
                expected_head,
                new_head,
                receipt.receipt_hash,
            ),
        )
        self._fault("after_head_transition_insert")
        return receipt

    def _validate_record_links(
        self,
        record: LedgerRecord,
        *,
        before_sequence: int | None = None,
    ) -> None:
        registry = self._manifest_registry(before_sequence=before_sequence)
        evidence_registry = self._evidence_registry(before_sequence=before_sequence)
        physical_registry = self._physical_registry(before_sequence=before_sequence)
        if isinstance(record, CalendarSourceArtifactV3):
            return
        if isinstance(record, CalendarScheduleSnapshotV3):
            artifact = evidence_registry.get(record.calendar_source_artifact_id)
            if not isinstance(artifact, CalendarSourceArtifactV3):
                raise LedgerNotFoundError("calendar source artifact is not registered")
            validate_calendar_schedule_artifact_v3(record, artifact)
            if record.parent_calendar_snapshot_id is not None:
                parent = evidence_registry.get(record.parent_calendar_snapshot_id)
                if not isinstance(parent, CalendarScheduleSnapshotV3):
                    raise LedgerNotFoundError(
                        "calendar snapshot parent is not registered"
                    )
                if (
                    record.venue_id,
                    record.contract_id,
                    record.product_id,
                    record.calendar_name,
                    record.timezone_name,
                    record.base_timeframe_seconds,
                ) != (
                    parent.venue_id,
                    parent.contract_id,
                    parent.product_id,
                    parent.calendar_name,
                    parent.timezone_name,
                    parent.base_timeframe_seconds,
                ):
                    raise LedgerConflictError(
                        "calendar successor changes its frozen lineage scope"
                    )
                if (
                    record.known_at < parent.known_at
                    or record.frozen_at < parent.frozen_at
                ):
                    raise LedgerConflictError(
                        "calendar successor clocks must not move backwards"
                    )
            return
        if isinstance(record, ActionProtocolV3):
            return
        if isinstance(record, InstrumentMappingV3):
            if record.parent_instrument_mapping_id is not None:
                parent = evidence_registry.get(record.parent_instrument_mapping_id)
                if not isinstance(parent, InstrumentMappingV3):
                    raise LedgerNotFoundError(
                        "instrument mapping parent is not registered"
                    )
                if (
                    record.asset_id,
                    record.venue_id,
                    record.source_contract_id,
                    record.provider_id,
                    record.mapping_policy_id,
                ) != (
                    parent.asset_id,
                    parent.venue_id,
                    parent.source_contract_id,
                    parent.provider_id,
                    parent.mapping_policy_id,
                ):
                    raise LedgerConflictError(
                        "instrument-mapping successor changes its frozen lineage scope"
                    )
                if record.known_at < parent.known_at:
                    raise LedgerConflictError(
                        "instrument-mapping successor known_at must not move backwards"
                    )
            return
        if isinstance(record, ProviderAdapterPolicyV3):
            calendar = evidence_registry.get(record.calendar_manifest_id)
            if not isinstance(calendar, CalendarScheduleSnapshotV3):
                raise LedgerNotFoundError(
                    "provider adapter calendar snapshot is not registered"
                )
            if (
                calendar.venue_id,
                calendar.contract_id,
                calendar.base_timeframe_seconds,
            ) != (
                record.venue_id,
                record.concrete_contract_id,
                record.base_interval_seconds,
            ):
                raise LedgerConflictError(
                    "provider adapter scope differs from its calendar snapshot"
                )
            if (
                calendar.known_at > record.frozen_at
                or calendar.frozen_at > record.frozen_at
            ):
                raise LedgerConflictError(
                    "provider adapter calendar was not frozen by the policy cutoff"
                )
            return
        if isinstance(record, CaptureSegmentV3):
            policy = physical_registry.get(record.adapter_policy_id)
            if not isinstance(policy, ProviderAdapterPolicyV3):
                raise LedgerNotFoundError(
                    "capture-segment adapter policy is not registered"
                )
            if record.provider_native_key != policy.provider_native_key:
                raise LedgerConflictError(
                    "capture segment provider instrument differs from adapter policy"
                )
            segments = {
                identity: item
                for identity, item in physical_registry.items()
                if isinstance(item, CaptureSegmentV3)
            }
            validate_capture_segment_lineage(record, segments)
            existing_message_ids = {
                message_id
                for segment in segments.values()
                for message_id in segment.message_receipt_ids
            }
            if existing_message_ids.intersection(record.message_receipt_ids):
                raise LedgerConflictError(
                    "provider message occurrence is already registered in a segment"
                )
            if record.vintage.value == "PROSPECTIVE_LIVE" and (
                record.envelopes[0].collector_received_wall_ts < policy.frozen_at
            ):
                raise LedgerConflictError(
                    "prospective capture predates its frozen adapter policy"
                )
            return
        if isinstance(record, ObservationDerivationV3):
            policy = physical_registry.get(record.adapter_policy_id)
            if not isinstance(policy, ProviderAdapterPolicyV3):
                raise LedgerNotFoundError(
                    "observation-derivation adapter policy is not registered"
                )
            if record.calendar_manifest_id != policy.calendar_manifest_id:
                raise LedgerConflictError(
                    "observation derivation calendar differs from adapter policy"
                )
            if record.derivation_kind is DerivationKind.RAW_NORMALIZATION:
                message_id = record.input_message_receipt_ids[0]
                containing_segments = [
                    item
                    for item in physical_registry.values()
                    if isinstance(item, CaptureSegmentV3)
                    and message_id in item.message_receipt_ids
                ]
                if len(containing_segments) != 1:
                    raise LedgerNotFoundError(
                        "raw derivation input message has no unique capture segment"
                    )
                segment = containing_segments[0]
                if segment.adapter_policy_id != policy.adapter_policy_id:
                    raise LedgerConflictError(
                        "raw derivation input uses another adapter policy"
                    )
                segment_sequence = self._object_first_receipt_sequence(
                    LedgerRecordKind.CAPTURE_SEGMENT,
                    segment.capture_segment_id,
                    before_sequence=before_sequence,
                )
                if record.derived_at < self.get_receipt(segment_sequence).receipt_ts:
                    raise LedgerConflictError(
                        "raw derivation predates durable capture registration"
                    )
            else:
                raise LedgerConflictError(
                    "timeframe aggregation is not authoritative until its frozen "
                    "grid and deterministic OHLCV verifier are implemented"
                )
            return
        if isinstance(record, ObservationRevisionV3):
            policy = physical_registry.get(record.adapter_policy_id)
            derivation = physical_registry.get(record.observation_derivation_id)
            mapping = evidence_registry.get(record.instrument_mapping_id)
            if not isinstance(policy, ProviderAdapterPolicyV3):
                raise LedgerNotFoundError(
                    "observation adapter policy is not registered"
                )
            if not isinstance(derivation, ObservationDerivationV3):
                raise LedgerNotFoundError("observation derivation is not registered")
            if not isinstance(mapping, InstrumentMappingV3):
                raise LedgerNotFoundError(
                    "observation instrument mapping is not registered"
                )
            expected_scope = (
                policy.source_id,
                policy.asset_id,
                policy.venue_id,
                policy.concrete_contract_id,
                policy.timeframe_id,
            )
            actual_scope = (
                record.source_id,
                record.asset_id,
                record.venue_id,
                record.concrete_contract_id,
                record.timeframe_id,
            )
            if actual_scope != expected_scope:
                raise LedgerConflictError(
                    "observation scope differs from adapter policy"
                )
            if (
                mapping.asset_id,
                mapping.venue_id,
                mapping.source_contract_id,
                mapping.provider_id,
                mapping.source_symbol,
            ) != (
                policy.asset_id,
                policy.venue_id,
                policy.concrete_contract_id,
                policy.provider_id,
                policy.provider_native_key,
            ):
                raise LedgerConflictError(
                    "observation instrument mapping differs from adapter policy"
                )
            if mapping.known_at > record.available_at or not (
                mapping.effective_start_ts
                <= record.source_event_ts
                < mapping.effective_end_ts_exclusive
            ):
                raise LedgerConflictError(
                    "observation instrument mapping was not applicable"
                )
            if (
                derivation.adapter_policy_id != record.adapter_policy_id
                or derivation.output_field_ids != record.field_ids
                or derivation.output_field_values != record.field_values
            ):
                raise LedgerConflictError(
                    "observation content differs from its derivation"
                )
            revisions = {
                identity: item
                for identity, item in physical_registry.items()
                if isinstance(item, ObservationRevisionV3)
            }
            validate_observation_revision_lineage(record, revisions)
            if derivation.derivation_kind is DerivationKind.RAW_NORMALIZATION:
                message_id = derivation.input_message_receipt_ids[0]
                containing_segments = [
                    item
                    for item in physical_registry.values()
                    if isinstance(item, CaptureSegmentV3)
                    and message_id in item.message_receipt_ids
                ]
                if len(containing_segments) != 1:
                    raise LedgerNotFoundError(
                        "raw observation input has no unique capture segment"
                    )
                segment = containing_segments[0]
                segment_sequence = self._object_first_receipt_sequence(
                    LedgerRecordKind.CAPTURE_SEGMENT,
                    segment.capture_segment_id,
                    before_sequence=before_sequence,
                )
                if (
                    record.durably_appended_ts
                    != self.get_receipt(segment_sequence).receipt_ts
                ):
                    raise LedgerConflictError(
                        "observation durable clock differs from capture receipt"
                    )
                validate_raw_normalization_v3(
                    policy=policy,
                    segment=segment,
                    derivation=derivation,
                    revision=record,
                )
            else:
                raise LedgerConflictError(
                    "unverified timeframe aggregation cannot enter the physical ledger"
                )
            return
        if isinstance(record, ProviderMessageDispositionV3):
            policy = physical_registry.get(record.adapter_policy_id)
            segment = physical_registry.get(record.capture_segment_id)
            if not isinstance(policy, ProviderAdapterPolicyV3):
                raise LedgerNotFoundError(
                    "message-disposition adapter policy is not registered"
                )
            if not isinstance(segment, CaptureSegmentV3):
                raise LedgerNotFoundError(
                    "message-disposition capture segment is not registered"
                )
            if segment.adapter_policy_id != policy.adapter_policy_id:
                raise LedgerConflictError(
                    "message disposition capture uses another adapter policy"
                )
            matching_envelopes = [
                item
                for item in segment.envelopes
                if item.message_receipt_id == record.message_receipt_id
            ]
            if len(matching_envelopes) != 1:
                raise LedgerNotFoundError(
                    "message disposition has no unique captured occurrence"
                )
            envelope = matching_envelopes[0]
            if envelope.raw_payload_sha256 != record.raw_payload_sha256:
                raise LedgerConflictError(
                    "message disposition raw hash differs from its envelope"
                )
            expected_classifier_hash = (
                BYBIT_V5_KLINE_CLASSIFIER_RELEASE_HASH
                if policy.adapter_kind is ProviderAdapterKind.BYBIT_V5_PUBLIC_KLINE
                else BYBIT_V5_INSTRUMENT_INFO_CLASSIFIER_RELEASE_HASH
            )
            if (
                record.classifier_release_hash != expected_classifier_hash
                or record.classifier_release_hash
                != policy.message_classifier_release_hash
            ):
                raise LedgerConflictError(
                    "message disposition classifier differs from adapter policy"
                )
            segment_sequence = self._object_first_receipt_sequence(
                LedgerRecordKind.CAPTURE_SEGMENT,
                segment.capture_segment_id,
                before_sequence=before_sequence,
            )
            if record.classified_at < self.get_receipt(segment_sequence).receipt_ts:
                raise LedgerConflictError(
                    "message disposition predates durable capture registration"
                )
            derivations_for_message = [
                item
                for item in physical_registry.values()
                if isinstance(item, ObservationDerivationV3)
                and item.derivation_kind is DerivationKind.RAW_NORMALIZATION
                and item.input_message_receipt_ids == (record.message_receipt_id,)
            ]
            normalized_derivation: ObservationDerivationV3 | None = None
            normalized_revision: ObservationRevisionV3 | None = None
            if record.disposition_kind is MessageDispositionKind.NORMALIZED_OBSERVATION:
                derivation = physical_registry.get(record.observation_derivation_id)
                revision = physical_registry.get(record.observation_revision_id)
                if not isinstance(derivation, ObservationDerivationV3):
                    raise LedgerNotFoundError(
                        "normalized disposition derivation is not registered"
                    )
                if not isinstance(revision, ObservationRevisionV3):
                    raise LedgerNotFoundError(
                        "normalized disposition revision is not registered"
                    )
                if derivations_for_message != [derivation]:
                    raise LedgerConflictError(
                        "normalized disposition does not bind the unique raw derivation"
                    )
                if (
                    revision.observation_derivation_id
                    != derivation.observation_derivation_id
                ):
                    raise LedgerConflictError(
                        "normalized disposition revision uses another derivation"
                    )
                validate_raw_normalization_v3(
                    policy=policy,
                    segment=segment,
                    derivation=derivation,
                    revision=revision,
                )
                if record.classified_at < revision.available_at:
                    raise LedgerConflictError(
                        "normalized disposition predates observation availability"
                    )
                normalized_derivation = derivation
                normalized_revision = revision
            elif record.disposition_kind is MessageDispositionKind.EXACT_DUPLICATE:
                if derivations_for_message:
                    raise LedgerConflictError(
                        "duplicate disposition cannot hide an observation derivation"
                    )
                original = physical_registry.get(record.duplicate_of_disposition_id)
                if not isinstance(original, ProviderMessageDispositionV3):
                    raise LedgerNotFoundError(
                        "duplicate disposition original is not registered"
                    )
                if (
                    original.disposition_kind
                    is not MessageDispositionKind.NORMALIZED_OBSERVATION
                    or original.message_receipt_id
                    != record.duplicate_of_message_receipt_id
                    or original.adapter_policy_id != record.adapter_policy_id
                    or original.raw_payload_sha256 != record.raw_payload_sha256
                ):
                    raise LedgerConflictError(
                        "duplicate disposition does not reference a normalized same-policy occurrence"
                    )
                original_segment = physical_registry.get(original.capture_segment_id)
                if not isinstance(original_segment, CaptureSegmentV3):
                    raise LedgerNotFoundError(
                        "duplicate disposition original segment is not registered"
                    )
                original_envelopes = [
                    item
                    for item in original_segment.envelopes
                    if item.message_receipt_id == original.message_receipt_id
                ]
                if (
                    len(original_envelopes) != 1
                    or original_envelopes[0].raw_payload != envelope.raw_payload
                ):
                    raise LedgerConflictError(
                        "duplicate disposition raw bytes differ from its original"
                    )
                normalized_matches = [
                    item
                    for item in physical_registry.values()
                    if isinstance(item, ProviderMessageDispositionV3)
                    and item.disposition_kind
                    is MessageDispositionKind.NORMALIZED_OBSERVATION
                    and item.adapter_policy_id == record.adapter_policy_id
                    and item.raw_payload_sha256 == record.raw_payload_sha256
                ]
                earliest = min(
                    normalized_matches,
                    key=lambda item: self._object_first_receipt_sequence(
                        LedgerRecordKind.PROVIDER_MESSAGE_DISPOSITION,
                        item.provider_message_disposition_id,
                        before_sequence=before_sequence,
                    ),
                )
                if earliest.provider_message_disposition_id != (
                    original.provider_message_disposition_id
                ):
                    raise LedgerConflictError(
                        "duplicate disposition does not reference the earliest normalized occurrence"
                    )
            elif derivations_for_message:
                raise LedgerConflictError(
                    "non-observation disposition cannot hide an observation derivation"
                )
            prior_normalized = sorted(
                (
                    item
                    for item in physical_registry.values()
                    if isinstance(item, ProviderMessageDispositionV3)
                    and item.disposition_kind
                    is MessageDispositionKind.NORMALIZED_OBSERVATION
                    and item.adapter_policy_id == record.adapter_policy_id
                ),
                key=lambda item: self._object_first_receipt_sequence(
                    LedgerRecordKind.PROVIDER_MESSAGE_DISPOSITION,
                    item.provider_message_disposition_id,
                    before_sequence=before_sequence,
                ),
            )
            prior_occurrences: list[
                tuple[CaptureSegmentV3, ProviderMessageDispositionV3]
            ] = []
            for item in prior_normalized:
                prior_segment = physical_registry.get(item.capture_segment_id)
                if not isinstance(prior_segment, CaptureSegmentV3):
                    raise LedgerNotFoundError(
                        "prior normalized disposition segment is not registered"
                    )
                prior_occurrences.append((prior_segment, item))
            source_member_key = (
                normalized_revision.source_member_key
                if normalized_revision is not None
                else sha256_digest(
                    {
                        "adapter_policy_id": policy.adapter_policy_id,
                        "domain": "NonObservationDispositionSourceMemberV1",
                    }
                )
            )
            instrument_mapping_id = (
                normalized_revision.instrument_mapping_id
                if normalized_revision is not None
                else sha256_digest(
                    {
                        "adapter_policy_id": policy.adapter_policy_id,
                        "domain": "NonObservationDispositionMappingV1",
                    }
                )
            )
            durable_receipt_ts = self.get_receipt(segment_sequence).receipt_ts
            expected_disposition, expected_derivation, expected_revision = (
                build_bybit_v5_message_disposition(
                    adapter_policy=policy,
                    segment=segment,
                    message_receipt_id=record.message_receipt_id,
                    source_member_key=source_member_key,
                    instrument_mapping_id=instrument_mapping_id,
                    durably_appended_ts=durable_receipt_ts,
                    normalized_at=(
                        normalized_revision.normalized_at
                        if normalized_revision is not None
                        else record.classified_at
                    ),
                    available_at=(
                        normalized_revision.available_at
                        if normalized_revision is not None
                        else record.classified_at
                    ),
                    classified_at=record.classified_at,
                    parent_observation_revision_id=(
                        normalized_revision.parent_observation_revision_id
                        if normalized_revision is not None
                        else None
                    ),
                    correction_reason=(
                        normalized_revision.correction_reason
                        if normalized_revision is not None
                        else None
                    ),
                    prior_normalized_occurrences=tuple(prior_occurrences),
                )
            )
            if record != expected_disposition:
                raise LedgerConflictError(
                    "message disposition differs from deterministic classification"
                )
            if (
                normalized_derivation != expected_derivation
                or normalized_revision != expected_revision
            ):
                raise LedgerConflictError(
                    "normalized disposition content differs from deterministic classification"
                )
            return
        if isinstance(record, ObservationSelectionPolicyV3):
            slot = evidence_registry.get(record.dependency_slot_id)
            if not isinstance(slot, FeatureDependencySlotV3):
                raise LedgerNotFoundError(
                    "observation-selection dependency slot is not registered"
                )
            if (
                record.selection_mode is not slot.selection_mode
                or record.maximum_age_seconds != slot.maximum_age_seconds
                or not slot.minimum_count
                <= record.requested_count
                <= slot.maximum_count
            ):
                raise LedgerConflictError(
                    "observation-selection policy differs from dependency slot"
                )
            return
        if isinstance(record, EvidencePrefixV3):
            if record.ledger_id != self.ledger_id:
                raise LedgerConflictError("evidence prefix belongs to another ledger")
            try:
                cutoff_receipt = self.get_receipt(record.cutoff_global_sequence)
            except LedgerNotFoundError as exc:
                raise LedgerNotFoundError(
                    "evidence-prefix cutoff receipt is not registered"
                ) from exc
            if cutoff_receipt.receipt_hash != record.cutoff_receipt_hash:
                raise LedgerConflictError(
                    "evidence-prefix cutoff hash differs from the ledger receipt"
                )
            if cutoff_receipt.receipt_ts > record.knowledge_cutoff_ts:
                raise LedgerConflictError(
                    "evidence-prefix receipt cutoff postdates its knowledge cutoff"
                )
            cutoff_physical = self._physical_registry(
                before_sequence=record.cutoff_global_sequence + 1
            )
            policy = cutoff_physical.get(record.adapter_policy_id)
            if not isinstance(policy, ProviderAdapterPolicyV3):
                raise LedgerNotFoundError(
                    "evidence-prefix adapter policy was not registered by its cutoff"
                )
            segments = {
                identity: item
                for identity, item in cutoff_physical.items()
                if isinstance(item, CaptureSegmentV3)
            }
            revisions = {
                identity: item
                for identity, item in cutoff_physical.items()
                if isinstance(item, ObservationRevisionV3)
            }
            derivations = {
                identity: item
                for identity, item in cutoff_physical.items()
                if isinstance(item, ObservationDerivationV3)
            }
            dispositions = {
                identity: item
                for identity, item in cutoff_physical.items()
                if isinstance(item, ProviderMessageDispositionV3)
            }
            parent_prefixes = {
                identity: item
                for identity, item in cutoff_physical.items()
                if isinstance(item, EvidencePrefixV3)
            }
            adapter_policies = {
                identity: item
                for identity, item in cutoff_physical.items()
                if isinstance(item, ProviderAdapterPolicyV3)
            }
            disposition_order = tuple(
                sorted(
                    record.message_disposition_ids,
                    key=lambda identity: self._object_first_receipt_sequence(
                        LedgerRecordKind.PROVIDER_MESSAGE_DISPOSITION,
                        identity,
                        before_sequence=record.cutoff_global_sequence + 1,
                    ),
                )
            )
            mapping = self._load_record(
                LedgerRecordKind.INSTRUMENT_MAPPING,
                record.instrument_mapping_id,
                before_sequence=record.cutoff_global_sequence + 1,
            )
            if not isinstance(mapping, InstrumentMappingV3):
                raise LedgerNotFoundError(
                    "evidence-prefix instrument mapping is not registered"
                )
            validate_evidence_prefix_graph(
                record,
                adapter_policy=policy,
                adapter_policies=adapter_policies,
                segments=segments,
                dispositions=dispositions,
                revisions=revisions,
                parent_prefixes=parent_prefixes,
                disposition_order=disposition_order,
            )
            in_scope_policy_ids = {
                record.adapter_policy_id,
                *record.supporting_adapter_policy_ids,
            }
            expected_segment_ids = {
                item.capture_segment_id
                for item in segments.values()
                if item.adapter_policy_id in in_scope_policy_ids
            }
            if set(record.capture_segment_ids) != expected_segment_ids:
                raise LedgerConflictError(
                    "evidence prefix omits or adds an in-scope capture segment"
                )
            expected_message_ids = {
                message_id
                for segment_id in expected_segment_ids
                for message_id in segments[segment_id].message_receipt_ids
            }
            dispositions_by_message: dict[str, list[ProviderMessageDispositionV3]] = {}
            for disposition in dispositions.values():
                if disposition.adapter_policy_id in in_scope_policy_ids:
                    dispositions_by_message.setdefault(
                        disposition.message_receipt_id, []
                    ).append(disposition)
            if set(dispositions_by_message) != expected_message_ids or any(
                len(items) != 1 for items in dispositions_by_message.values()
            ):
                raise LedgerConflictError(
                    "evidence prefix does not classify every captured provider message exactly once"
                )
            expected_disposition_ids = {
                items[0].provider_message_disposition_id
                for items in dispositions_by_message.values()
            }
            if set(record.message_disposition_ids) != expected_disposition_ids:
                raise LedgerConflictError(
                    "evidence prefix omits or adds an in-scope message disposition"
                )
            derivations_by_message: dict[str, list[ObservationDerivationV3]] = {}
            for derivation in derivations.values():
                if (
                    derivation.derivation_kind is DerivationKind.RAW_NORMALIZATION
                    and derivation.adapter_policy_id in in_scope_policy_ids
                ):
                    message_id = derivation.input_message_receipt_ids[0]
                    derivations_by_message.setdefault(message_id, []).append(derivation)
            revisions_by_derivation: dict[str, list[ObservationRevisionV3]] = {}
            for revision in revisions.values():
                revisions_by_derivation.setdefault(
                    revision.observation_derivation_id, []
                ).append(revision)
            expected_revision_ids: set[str] = set()
            for message_id, disposition_items in dispositions_by_message.items():
                disposition = disposition_items[0]
                derivation_items = derivations_by_message.get(message_id, [])
                if (
                    disposition.disposition_kind
                    is not MessageDispositionKind.NORMALIZED_OBSERVATION
                ):
                    if derivation_items:
                        raise LedgerConflictError(
                            "non-observation disposition hides a raw normalization"
                        )
                    continue
                if len(derivation_items) != 1:
                    raise LedgerConflictError(
                        "normalized message disposition lacks one exact raw derivation"
                    )
                derivation = derivation_items[0]
                if (
                    derivation.observation_derivation_id
                    != disposition.observation_derivation_id
                ):
                    raise LedgerConflictError(
                        "message disposition references another raw derivation"
                    )
                matches = revisions_by_derivation.get(
                    derivation.observation_derivation_id, []
                )
                if len(matches) != 1:
                    raise LedgerConflictError(
                        "evidence prefix normalization lacks one exact observation revision"
                    )
                normalized_revision = matches[0]
                if (
                    normalized_revision.observation_revision_id
                    != disposition.observation_revision_id
                    or normalized_revision.source_member_key != record.source_member_key
                    or normalized_revision.instrument_mapping_id
                    != record.instrument_mapping_id
                ):
                    raise LedgerConflictError(
                        "captured provider message was normalized outside its evidence prefix scope"
                    )
                expected_revision_ids.add(normalized_revision.observation_revision_id)
            if set(record.observation_revision_ids) != expected_revision_ids:
                raise LedgerConflictError(
                    "evidence prefix omits or adds an in-scope observation revision"
                )
            for item in physical_registry.values():
                if isinstance(item, CaptureSegmentV3):
                    in_scope = item.adapter_policy_id in in_scope_policy_ids
                    identity = item.capture_segment_id
                    kind = LedgerRecordKind.CAPTURE_SEGMENT
                elif isinstance(item, ObservationRevisionV3):
                    in_scope = item.source_member_key == record.source_member_key
                    identity = item.observation_revision_id
                    kind = LedgerRecordKind.OBSERVATION_REVISION
                elif isinstance(item, ProviderMessageDispositionV3):
                    in_scope = item.adapter_policy_id in in_scope_policy_ids
                    identity = item.provider_message_disposition_id
                    kind = LedgerRecordKind.PROVIDER_MESSAGE_DISPOSITION
                else:
                    continue
                if not in_scope:
                    continue
                sequence = self._object_first_receipt_sequence(
                    kind,
                    identity,
                    before_sequence=before_sequence,
                )
                receipt = self.get_receipt(sequence)
                if (
                    receipt.receipt_ts <= record.knowledge_cutoff_ts
                    and sequence > record.cutoff_global_sequence
                ):
                    raise LedgerConflictError(
                        "evidence prefix cutoff omits an in-scope known record"
                    )
            return
        if isinstance(record, DependencySelectionProofV3):
            policy = physical_registry.get(record.observation_selection_policy_id)
            slot = evidence_registry.get(record.dependency_slot_id)
            member = evidence_registry.get(record.source_member_id)
            prefix = physical_registry.get(record.evidence_prefix_id)
            if not isinstance(policy, ObservationSelectionPolicyV3):
                raise LedgerNotFoundError(
                    "dependency-selection policy is not registered"
                )
            if not isinstance(slot, FeatureDependencySlotV3):
                raise LedgerNotFoundError("dependency-selection slot is not registered")
            if not isinstance(member, SourceBundleMemberV3):
                raise LedgerNotFoundError(
                    "dependency-selection source member is not registered"
                )
            if not isinstance(prefix, EvidencePrefixV3):
                raise LedgerNotFoundError(
                    "dependency-selection evidence prefix is not registered"
                )
            revisions = {
                identity: item
                for identity, item in physical_registry.items()
                if isinstance(item, ObservationRevisionV3)
            }
            expected = select_observation_revisions_v3(
                policy=policy,
                slot=slot,
                member=member,
                prefix=prefix,
                revisions=revisions,
                observation_cutoff_ts=record.observation_cutoff_ts,
                computed_at=record.computed_at,
            )
            if record != expected:
                raise LedgerConflictError(
                    "dependency-selection proof differs from deterministic selection"
                )
            return
        if isinstance(record, PhysicalEvidenceGateV3):
            information_set = self._load_record(
                LedgerRecordKind.INFORMATION_SET,
                record.information_set_id,
                before_sequence=before_sequence,
            )
            if not isinstance(information_set, InformationSetV3):
                raise LedgerNotFoundError(
                    "physical gate information set is not registered"
                )
            if (
                self._physical_policy_for_information_set(
                    information_set,
                    registry=registry,
                    evidence_registry=evidence_registry,
                )
                is None
            ):
                raise LedgerConflictError(
                    "physical gate information set has no adapter-policy source"
                )
            source = registry.get(information_set.source_manifest_id)
            if not isinstance(source, ImmutableManifestV3):
                raise LedgerNotFoundError(
                    "physical gate source manifest is not registered"
                )
            bundle = evidence_registry.get(source.payload["source_content_root"])
            if not isinstance(bundle, SourceBundleV3):
                raise LedgerNotFoundError(
                    "physical gate source bundle is not registered"
                )
            required_groups = self._required_physical_selection_groups(
                information_set,
                evidence_registry=evidence_registry,
                physical_registry=physical_registry,
                bundle=bundle,
            )
            required_proof_ids = {
                proof.dependency_selection_proof_id for _, _, proof in required_groups
            }
            if set(record.dependency_selection_proof_ids) != required_proof_ids:
                raise LedgerConflictError(
                    "physical gate does not bind every required selection proof"
                )
            proofs: list[DependencySelectionProofV3] = []
            for proof_id in record.dependency_selection_proof_ids:
                proof = physical_registry.get(proof_id)
                if not isinstance(proof, DependencySelectionProofV3):
                    raise LedgerNotFoundError(
                        "physical gate selection proof is not registered"
                    )
                proofs.append(proof)
            prefixes: dict[str, EvidencePrefixV3] = {}
            for prefix_id in record.evidence_prefix_ids:
                prefix = physical_registry.get(prefix_id)
                if not isinstance(prefix, EvidencePrefixV3):
                    raise LedgerNotFoundError(
                        "physical gate evidence prefix is not registered"
                    )
                prefixes[prefix_id] = prefix
            revisions = {
                identity: item
                for identity, item in physical_registry.items()
                if isinstance(item, ObservationRevisionV3)
            }
            expected = build_physical_evidence_gate_v3(
                information_set=information_set,
                proofs=proofs,
                prefixes=prefixes,
                revisions=revisions,
                gate_stage=record.gate_stage,
                evaluated_at=record.evaluated_at,
            )
            if record != expected:
                raise LedgerConflictError(
                    "physical evidence gate differs from deterministic evaluation"
                )
            return
        if isinstance(record, SourceBundleMemberV3):
            members = {
                identity: item
                for identity, item in evidence_registry.items()
                if isinstance(item, SourceBundleMemberV3)
            }
            if record.parent_source_member_id is not None and not isinstance(
                members.get(record.parent_source_member_id), SourceBundleMemberV3
            ):
                raise LedgerNotFoundError("source member parent is not registered")
            validate_source_member_lineage(record, members)
            if record.parent_source_member_id is not None:
                bundles = {
                    identity: item
                    for identity, item in evidence_registry.items()
                    if isinstance(item, SourceBundleV3)
                }
                active_parent_bundles: list[SourceBundleV3] = []
                for bundle in bundles.values():
                    if record.parent_source_member_id not in bundle.source_member_ids:
                        continue
                    head_type, semantic_key, _, _ = _semantic_claim(bundle)
                    if (
                        self._active_head_before(
                            head_type,
                            semantic_key,
                            before_sequence=before_sequence,
                        )
                        == bundle.source_bundle_id
                    ):
                        active_parent_bundles.append(bundle)
                if not active_parent_bundles:
                    raise LedgerConflictError(
                        "source member successor requires its parent in an active "
                        "source bundle"
                    )
                if any(
                    record.knowledge_cutoff_ts <= bundle.knowledge_cutoff_ts
                    for bundle in active_parent_bundles
                ):
                    raise LedgerConflictError(
                        "source member successor cutoff must follow every active "
                        "parent-bundle cutoff"
                    )
            return
        if isinstance(record, SourceBundleV3):
            members = {
                identity: item
                for identity, item in evidence_registry.items()
                if isinstance(item, SourceBundleMemberV3)
            }
            bundles = {
                identity: item
                for identity, item in evidence_registry.items()
                if isinstance(item, SourceBundleV3)
            }
            validate_source_bundle_graph(record, members, bundles)
            policy = evidence_registry.get(record.source_contract_id)
            if isinstance(policy, ProviderAdapterPolicyV3):
                prefixes = {
                    identity: item
                    for identity, item in physical_registry.items()
                    if isinstance(item, EvidencePrefixV3)
                }
                revisions = {
                    identity: item
                    for identity, item in physical_registry.items()
                    if isinstance(item, ObservationRevisionV3)
                }
                for member_id in record.source_member_ids:
                    member = members[member_id]
                    prefix = prefixes.get(member.semantic_content_root)
                    if not isinstance(prefix, EvidencePrefixV3):
                        raise LedgerNotFoundError(
                            "physical source member prefix is not registered"
                        )
                    if prefix.adapter_policy_id != policy.adapter_policy_id:
                        raise LedgerConflictError(
                            "physical source member uses another adapter policy"
                        )
                    validate_source_member_physical_prefix(
                        member,
                        prefix,
                        revisions,
                    )
            return
        if isinstance(record, FeatureDependencySlotV3):
            return
        if isinstance(record, FeatureDefinitionV3):
            for slot_id in record.input_dependency_slot_ids:
                if not isinstance(
                    evidence_registry.get(slot_id),
                    FeatureDependencySlotV3,
                ):
                    raise LedgerNotFoundError(
                        "feature dependency slot is not registered"
                    )
            for feature_id in record.derived_feature_ids:
                if not isinstance(
                    evidence_registry.get(feature_id),
                    FeatureDefinitionV3,
                ):
                    raise LedgerNotFoundError(
                        "derived feature definition is not registered"
                    )
            return
        if isinstance(record, FeatureSchemaV3):
            slots = {
                identity: item
                for identity, item in evidence_registry.items()
                if isinstance(item, FeatureDependencySlotV3)
            }
            features = {
                identity: item
                for identity, item in evidence_registry.items()
                if isinstance(item, FeatureDefinitionV3)
            }
            members = {
                identity: item
                for identity, item in evidence_registry.items()
                if isinstance(item, SourceBundleMemberV3)
            }
            bundles = {
                identity: item
                for identity, item in evidence_registry.items()
                if isinstance(item, SourceBundleV3)
            }
            compatible = [
                bundle
                for bundle in bundles.values()
                if bundle.source_contract_id == record.source_contract_id
                and bundle.source_schema_id == record.source_schema_id
            ]
            if not compatible:
                raise LedgerNotFoundError(
                    "feature schema has no registered compatible source bundle"
                )
            last_error: CanonicalizationError | None = None
            for bundle in compatible:
                try:
                    validate_feature_schema_graph(
                        record,
                        slots,
                        features,
                        bundle,
                        members,
                        bundles,
                    )
                except CanonicalizationError as exc:
                    last_error = exc
                    continue
                return
            assert last_error is not None
            raise last_error
        if isinstance(record, ImmutableManifestV3):
            validate_manifest_evidence_graph(
                record,
                registry,
                evidence_registry,
            )
            self._validate_final_holdout_registration_order(
                record,
                registry=registry,
                evidence_registry=evidence_registry,
                before_sequence=before_sequence,
            )
            return
        if isinstance(record, InformationSetV3):
            protocol = registry.get(record.protocol_manifest_id)
            if protocol is None:
                raise LedgerNotFoundError("information set protocol is not registered")
            validate_information_protocol_graph(
                protocol=protocol,
                information_set=record,
                registry=registry,
                evidence_registry=evidence_registry,
            )
            self._validate_global_observation_claims(
                record,
                evidence_registry=evidence_registry,
                before_sequence=before_sequence,
            )
            self._validate_physical_information_set(
                record,
                registry=registry,
                evidence_registry=evidence_registry,
                physical_registry=physical_registry,
                before_sequence=before_sequence,
            )
            calendar = evidence_registry.get(record.calendar_manifest_id)
            if not isinstance(calendar, CalendarScheduleSnapshotV3):
                raise LedgerNotFoundError(
                    "information-set calendar snapshot is not registered"
                )
            if (
                calendar.venue_id != record.venue_id
                or calendar.contract_id != record.contract_id
            ):
                raise LedgerConflictError(
                    "information-set scope differs from its calendar snapshot"
                )
            if (
                calendar.known_at > record.observation_cutoff_ts
                or calendar.frozen_at > record.observation_cutoff_ts
            ):
                raise LedgerConflictError(
                    "information-set calendar was not frozen by its cutoff"
                )
            return
        if isinstance(record, ActionResolutionV3):
            info = self._load_record(
                LedgerRecordKind.INFORMATION_SET,
                record.information_set_id,
                before_sequence=before_sequence,
            )
            assert isinstance(info, InformationSetV3)
            experiment_protocol = registry.get(info.protocol_manifest_id)
            if not isinstance(experiment_protocol, ImmutableManifestV3):
                raise LedgerNotFoundError(
                    "action-resolution experiment protocol is not registered"
                )
            if (
                record.action_protocol_id
                != experiment_protocol.payload["action_protocol_id"]
            ):
                raise LedgerConflictError(
                    "action resolution differs from the experiment's frozen "
                    "action protocol"
                )
            if (
                record.primary_signal_policy_id
                != experiment_protocol.payload["primary_signal_policy_id"]
            ):
                raise LedgerConflictError(
                    "action resolution differs from the experiment's frozen "
                    "primary-signal policy"
                )
            if record.calendar_snapshot_id != info.calendar_manifest_id:
                raise LedgerConflictError(
                    "action resolution calendar differs from its information set"
                )
            calendar = evidence_registry.get(record.calendar_snapshot_id)
            action_protocol = evidence_registry.get(record.action_protocol_id)
            mapping = evidence_registry.get(record.instrument_mapping_id)
            calendar_artifact = (
                evidence_registry.get(calendar.calendar_source_artifact_id)
                if isinstance(calendar, CalendarScheduleSnapshotV3)
                else None
            )
            if not isinstance(calendar, CalendarScheduleSnapshotV3):
                raise LedgerNotFoundError(
                    "action-resolution calendar snapshot is not registered"
                )
            if not isinstance(action_protocol, ActionProtocolV3):
                raise LedgerNotFoundError(
                    "action-resolution protocol is not registered"
                )
            if not isinstance(mapping, InstrumentMappingV3):
                raise LedgerNotFoundError(
                    "action-resolution instrument mapping is not registered"
                )
            if not isinstance(calendar_artifact, CalendarSourceArtifactV3):
                raise LedgerNotFoundError(
                    "action-resolution calendar source artifact is not registered"
                )
            record.validate_against(
                information_set=info,
                calendar_artifact=calendar_artifact,
                calendar=calendar,
                protocol=action_protocol,
                mapping=mapping,
            )
            self._validate_action_inputs_latest_applicable(
                resolution=record,
                information_set=info,
                protocol=action_protocol,
                evidence_registry=evidence_registry,
            )
            return
        if isinstance(record, PrimarySignalCandidateV3):
            info = self._load_record(
                LedgerRecordKind.INFORMATION_SET,
                record.information_set_id,
                before_sequence=before_sequence,
            )
            assert isinstance(info, InformationSetV3)
            protocol = registry.get(info.protocol_manifest_id)
            if protocol is None:
                raise LedgerNotFoundError("candidate protocol is not registered")
            action_resolution = self._load_record(
                LedgerRecordKind.ACTION_RESOLUTION,
                record.action_resolution_id,
                before_sequence=before_sequence,
            )
            assert isinstance(action_resolution, ActionResolutionV3)
            validate_action_resolution_candidate_graph(
                information_set=info,
                candidate=record,
                action_resolution=action_resolution,
                evidence_registry=evidence_registry,
            )
            validate_candidate_protocol_graph(
                protocol=protocol,
                information_set=info,
                candidate=record,
                registry=registry,
                evidence_registry=evidence_registry,
            )
            self._require_physical_decision_gate(
                info,
                candidate=record,
                registry=registry,
                evidence_registry=evidence_registry,
                physical_registry=physical_registry,
                before_sequence=before_sequence,
            )
            if record.entry_scenario in {
                EntryScenario.FORWARD_MARKET_ORDER,
                EntryScenario.LIVE_MARKET_ORDER,
            }:
                effective_source = registry.get(info.source_manifest_id)
                if not isinstance(effective_source, ImmutableManifestV3):
                    raise LedgerNotFoundError(
                        "forward/live effective source is not registered"
                    )
                self._validate_post_protocol_source_registration(
                    protocol=protocol,
                    effective_source=effective_source,
                    registry=registry,
                    evidence_registry=evidence_registry,
                    before_sequence=before_sequence,
                    context="forward/live",
                )
            return
        if isinstance(record, CandidateFeatureMaterializationV3):
            info = self._load_record(
                LedgerRecordKind.INFORMATION_SET,
                record.information_set_id,
                before_sequence=before_sequence,
            )
            candidate = self._load_record(
                LedgerRecordKind.PRIMARY_SIGNAL_CANDIDATE,
                record.primary_signal_candidate_id,
                before_sequence=before_sequence,
            )
            assert isinstance(info, InformationSetV3)
            assert isinstance(candidate, PrimarySignalCandidateV3)
            protocol = registry.get(info.protocol_manifest_id)
            if protocol is None:
                raise LedgerNotFoundError(
                    "feature materialization protocol is not registered"
                )
            validate_feature_materialization_protocol_graph(
                protocol=protocol,
                information_set=info,
                candidate=candidate,
                feature_materialization=record,
                registry=registry,
                evidence_registry=evidence_registry,
            )
            self._validate_candidate_neutral_projection(
                record,
                evidence_registry=evidence_registry,
                before_sequence=before_sequence,
            )
            return
        if isinstance(record, EligibilityDecisionV3):
            info = self._load_record(
                LedgerRecordKind.INFORMATION_SET,
                record.information_set_id,
                before_sequence=before_sequence,
            )
            candidate = self._load_record(
                LedgerRecordKind.PRIMARY_SIGNAL_CANDIDATE,
                record.primary_signal_candidate_id,
                before_sequence=before_sequence,
            )
            materialization = self._load_record(
                LedgerRecordKind.CANDIDATE_FEATURE_MATERIALIZATION,
                record.candidate_feature_materialization_id,
                before_sequence=before_sequence,
            )
            assert isinstance(info, InformationSetV3)
            assert isinstance(candidate, PrimarySignalCandidateV3)
            assert isinstance(materialization, CandidateFeatureMaterializationV3)
            protocol = registry.get(info.protocol_manifest_id)
            if protocol is None:
                raise LedgerNotFoundError("eligibility protocol is not registered")
            validate_eligibility_protocol_graph(
                protocol=protocol,
                information_set=info,
                candidate=candidate,
                feature_materialization=materialization,
                eligibility=record,
                registry=registry,
                evidence_registry=evidence_registry,
            )
            return
        if isinstance(record, DecisionEventV3):
            info = self._load_record(
                LedgerRecordKind.INFORMATION_SET,
                record.information_set_id,
                before_sequence=before_sequence,
            )
            eligibility = self._load_record(
                LedgerRecordKind.ELIGIBILITY_DECISION,
                record.eligibility_decision_id,
                before_sequence=before_sequence,
            )
            candidate = self._load_record(
                LedgerRecordKind.PRIMARY_SIGNAL_CANDIDATE,
                record.primary_signal_candidate_id,
                before_sequence=before_sequence,
            )
            materialization = self._load_record(
                LedgerRecordKind.CANDIDATE_FEATURE_MATERIALIZATION,
                record.candidate_feature_materialization_id,
                before_sequence=before_sequence,
            )
            assert isinstance(info, InformationSetV3)
            assert isinstance(eligibility, EligibilityDecisionV3)
            assert isinstance(candidate, PrimarySignalCandidateV3)
            assert isinstance(materialization, CandidateFeatureMaterializationV3)
            protocol = registry.get(info.protocol_manifest_id)
            if protocol is None:
                raise LedgerNotFoundError("event protocol is not registered")
            validate_record_protocol_graph(
                protocol=protocol,
                information_set=info,
                candidate=candidate,
                feature_materialization=materialization,
                eligibility=eligibility,
                event=record,
                registry=registry,
                evidence_registry=evidence_registry,
            )
            return
        if isinstance(record, BarrierActivationV3):
            event = self._load_record(
                LedgerRecordKind.DECISION_EVENT,
                record.decision_event_id,
                before_sequence=before_sequence,
            )
            assert isinstance(event, DecisionEventV3)
            record.validate_against(event)
            return
        if isinstance(record, LabelOutcomeV3):
            event = self._load_record(
                LedgerRecordKind.DECISION_EVENT,
                record.decision_event_id,
                before_sequence=before_sequence,
            )
            assert isinstance(event, DecisionEventV3)
            activation: BarrierActivationV3 | None = None
            if record.barrier_activation_id is not None:
                loaded = self._load_record(
                    LedgerRecordKind.BARRIER_ACTIVATION,
                    record.barrier_activation_id,
                    before_sequence=before_sequence,
                )
                assert isinstance(loaded, BarrierActivationV3)
                activation = loaded
            record.validate_against(event, activation)
            return
        if isinstance(record, EventDependenceAssignmentV3):
            event = self._load_record(
                LedgerRecordKind.DECISION_EVENT,
                record.decision_event_id,
                before_sequence=before_sequence,
            )
            outcome = self._load_record(
                LedgerRecordKind.LABEL_OUTCOME,
                record.label_outcome_id,
                before_sequence=before_sequence,
            )
            assert isinstance(event, DecisionEventV3)
            assert isinstance(outcome, LabelOutcomeV3)
            record.validate_against(event, outcome)
            current_label = self._active_head_before(
                "LABEL_OUTCOME",
                record.decision_event_id,
                before_sequence=before_sequence,
            )
            if current_label != record.label_outcome_id:
                raise LedgerConflictError(
                    "assignment must bind the active label outcome"
                )
            return
        raise CanonicalizationError("unsupported ledger record")

    def _object_first_receipt_sequence(
        self,
        kind: LedgerRecordKind,
        identity_id: str,
        *,
        before_sequence: int | None,
    ) -> int:
        sql = """
            SELECT first_receipt_sequence FROM objects
            WHERE record_kind = ? AND identity_id = ?
        """
        params: tuple[Any, ...] = (kind.value, identity_id)
        if before_sequence is not None:
            sql += " AND first_receipt_sequence < ?"
            params += (before_sequence,)
        row = self._connection.execute(sql, params).fetchone()
        if row is None:
            raise LedgerNotFoundError(f"missing {kind.value} receipt for {identity_id}")
        return int(row[0])

    def _records_before(
        self,
        kind: LedgerRecordKind,
        *,
        before_sequence: int | None,
    ) -> list[LedgerRecord]:
        sql = """
            SELECT canonical_blob FROM objects
            WHERE record_kind = ?
        """
        params: tuple[Any, ...] = (kind.value,)
        if before_sequence is not None:
            sql += " AND first_receipt_sequence < ?"
            params += (before_sequence,)
        sql += " ORDER BY first_receipt_sequence"
        return [
            _parse_record(kind, bytes(row[0]))
            for row in self._connection.execute(sql, params)
        ]

    def _validate_global_observation_claims(
        self,
        information_set: InformationSetV3,
        *,
        evidence_registry: Mapping[str, EvidenceRecordV3],
        before_sequence: int | None,
    ) -> None:
        """Keep one immutable meaning for each stable-member revision ID."""

        coordinate_claims: dict[tuple[str, str], tuple[object, ...]] = {}
        value_claims: dict[tuple[str, str, tuple[str, ...]], str] = {}
        prior_records = self._records_before(
            LedgerRecordKind.INFORMATION_SET,
            before_sequence=before_sequence,
        )
        for record in (*prior_records, information_set):
            assert isinstance(record, InformationSetV3)
            for dependency in record.dependencies:
                member = evidence_registry.get(dependency.source_member_id)
                if not isinstance(member, SourceBundleMemberV3):
                    raise LedgerNotFoundError(
                        "observation claim source member is not registered"
                    )
                revision_key = (
                    member.source_member_key,
                    dependency.observation_revision_id,
                )
                coordinates = (
                    dependency.name,
                    dependency.source_event_ts,
                    dependency.bar_open_ts,
                    dependency.bar_close_ts,
                    dependency.source_publish_ts,
                    dependency.ingested_first_seen_ts,
                    dependency.revision_received_ts,
                )
                prior_coordinates = coordinate_claims.get(revision_key)
                if prior_coordinates is not None and prior_coordinates != coordinates:
                    raise LedgerConflictError(
                        "global observation revision has conflicting coordinates"
                    )
                coordinate_claims[revision_key] = coordinates
                value_key = (*revision_key, dependency.source_field_ids)
                prior_value = value_claims.get(value_key)
                if prior_value is not None and prior_value != dependency.value_digest:
                    raise LedgerConflictError(
                        "global observation revision field set has conflicting value "
                        "digests"
                    )
                value_claims[value_key] = dependency.value_digest

    @staticmethod
    def _physical_policy_for_information_set(
        information_set: InformationSetV3,
        *,
        registry: Mapping[str, ImmutableManifestV3],
        evidence_registry: Mapping[str, EvidenceRecordV3],
    ) -> ProviderAdapterPolicyV3 | None:
        source = registry.get(information_set.source_manifest_id)
        if not isinstance(source, ImmutableManifestV3):
            raise LedgerNotFoundError(
                "information-set effective source manifest is not registered"
            )
        candidate = evidence_registry.get(source.payload["source_contract_id"])
        return candidate if isinstance(candidate, ProviderAdapterPolicyV3) else None

    def _validate_physical_information_set(
        self,
        information_set: InformationSetV3,
        *,
        registry: Mapping[str, ImmutableManifestV3],
        evidence_registry: Mapping[str, EvidenceRecordV3],
        physical_registry: Mapping[str, LedgerRecord],
        before_sequence: int | None,
    ) -> None:
        """Enforce V3.3 only for sources that explicitly bind an adapter policy."""

        policy = self._physical_policy_for_information_set(
            information_set,
            registry=registry,
            evidence_registry=evidence_registry,
        )
        if policy is None:
            return
        source = registry[information_set.source_manifest_id]
        bundle = evidence_registry.get(source.payload["source_content_root"])
        if not isinstance(bundle, SourceBundleV3):
            raise LedgerNotFoundError(
                "physical information source bundle is not registered"
            )
        members = {
            member_id: evidence_registry.get(member_id)
            for member_id in bundle.source_member_ids
        }
        if not all(isinstance(item, SourceBundleMemberV3) for item in members.values()):
            raise LedgerNotFoundError(
                "physical information source member is not registered"
            )
        revisions = {
            identity: item
            for identity, item in physical_registry.items()
            if isinstance(item, ObservationRevisionV3)
        }
        prefixes = {
            identity: item
            for identity, item in physical_registry.items()
            if isinstance(item, EvidencePrefixV3)
        }
        selection_groups = self._required_physical_selection_groups(
            information_set,
            evidence_registry=evidence_registry,
            physical_registry=physical_registry,
            bundle=bundle,
        )
        dependency_groups: dict[tuple[str, str], list[Any]] = {}
        for dependency in information_set.dependencies:
            dependency_groups.setdefault(
                (dependency.dependency_slot_id, dependency.source_member_id), []
            ).append(dependency)
        expected_group_keys = {
            (slot.dependency_slot_id, member.source_member_id)
            for slot, member, _ in selection_groups
        }
        if not set(dependency_groups).issubset(expected_group_keys):
            raise LedgerConflictError(
                "physical dependency references an undeclared selection group"
            )
        for slot, member, proof in selection_groups:
            group_key = (slot.dependency_slot_id, member.source_member_id)
            dependencies = dependency_groups.get(group_key, [])
            prefix = prefixes.get(proof.evidence_prefix_id)
            if not isinstance(prefix, EvidencePrefixV3):
                raise LedgerNotFoundError(
                    "physical dependency evidence prefix is not registered"
                )
            if (
                member.semantic_content_root != prefix.evidence_prefix_id
                or prefix.adapter_policy_id != policy.adapter_policy_id
                or prefix.knowledge_cutoff_ts > information_set.observation_cutoff_ts
            ):
                raise LedgerConflictError(
                    "physical dependency proof differs from its frozen source member"
                )
            proof_sequence = self._object_first_receipt_sequence(
                LedgerRecordKind.DEPENDENCY_SELECTION_PROOF,
                proof.dependency_selection_proof_id,
                before_sequence=before_sequence,
            )
            prefix_sequence = self._object_first_receipt_sequence(
                LedgerRecordKind.EVIDENCE_PREFIX,
                prefix.evidence_prefix_id,
                before_sequence=before_sequence,
            )
            if information_set.assembled_at < max(
                proof.computed_at,
                prefix.assembled_at,
                self.get_receipt(proof_sequence).receipt_ts,
                self.get_receipt(prefix_sequence).receipt_ts,
            ):
                raise LedgerConflictError(
                    "physical information set predates its prefix or selection proof"
                )
            expected_revision_ids = {
                dependency.observation_revision_id for dependency in dependencies
            }
            if proof.status is SelectionStatus.ABSTAIN:
                if dependencies:
                    raise LedgerConflictError(
                        "abstained physical selection cannot supply dependencies"
                    )
                continue
            if set(proof.selected_observation_revision_ids) != expected_revision_ids:
                raise LedgerConflictError(
                    "physical selection proof differs from information dependencies"
                )
            for dependency in dependencies:
                revision = revisions.get(dependency.observation_revision_id)
                if not isinstance(revision, ObservationRevisionV3):
                    raise LedgerNotFoundError(
                        "physical information observation is not registered"
                    )
                if revision.adapter_policy_id != policy.adapter_policy_id:
                    raise LedgerConflictError(
                        "physical information observation uses another adapter policy"
                    )
                validate_dependency_against_observation(dependency, revision)
                sequence = self._object_first_receipt_sequence(
                    LedgerRecordKind.OBSERVATION_REVISION,
                    revision.observation_revision_id,
                    before_sequence=before_sequence,
                )
                if (
                    self.get_receipt(sequence).receipt_ts
                    > information_set.observation_cutoff_ts
                ):
                    raise LedgerConflictError(
                        "physical observation was registered after the information cutoff"
                    )

    @staticmethod
    def _required_physical_selection_groups(
        information_set: InformationSetV3,
        *,
        evidence_registry: Mapping[str, EvidenceRecordV3],
        physical_registry: Mapping[str, LedgerRecord],
        bundle: SourceBundleV3,
    ) -> tuple[
        tuple[
            FeatureDependencySlotV3,
            SourceBundleMemberV3,
            DependencySelectionProofV3,
        ],
        ...,
    ]:
        """Resolve exactly one proof for every physical observation slot/member."""

        schema = evidence_registry.get(information_set.feature_schema_id)
        if not isinstance(schema, FeatureSchemaV3):
            raise LedgerNotFoundError(
                "physical information feature schema is not registered"
            )
        members_by_key: dict[str, SourceBundleMemberV3] = {}
        for member_id in bundle.source_member_ids:
            member = evidence_registry.get(member_id)
            if not isinstance(member, SourceBundleMemberV3):
                raise LedgerNotFoundError(
                    "physical information source member is not registered"
                )
            if member.source_member_key in members_by_key:
                raise LedgerConflictError(
                    "physical source bundle duplicates a stable member key"
                )
            members_by_key[member.source_member_key] = member
        proofs = [
            item
            for item in physical_registry.values()
            if isinstance(item, DependencySelectionProofV3)
            and item.observation_cutoff_ts == information_set.observation_cutoff_ts
        ]
        result: list[
            tuple[
                FeatureDependencySlotV3,
                SourceBundleMemberV3,
                DependencySelectionProofV3,
            ]
        ] = []
        for slot_id in schema.dependency_slot_ids:
            slot = evidence_registry.get(slot_id)
            if not isinstance(slot, FeatureDependencySlotV3):
                raise LedgerNotFoundError(
                    "physical information dependency slot is not registered"
                )
            if slot.evidence_kind is not EvidenceKind.OBSERVATION:
                continue
            for member_key in slot.source_member_keys:
                member = members_by_key.get(member_key)
                if not isinstance(member, SourceBundleMemberV3):
                    raise LedgerConflictError(
                        "physical observation slot references a foreign member key"
                    )
                matches = [
                    proof
                    for proof in proofs
                    if proof.dependency_slot_id == slot.dependency_slot_id
                    and proof.source_member_id == member.source_member_id
                ]
                if len(matches) != 1:
                    raise LedgerConflictError(
                        "physical dependency group requires one exact selection proof"
                    )
                result.append((slot, member, matches[0]))
        return tuple(result)

    def _require_physical_decision_gate(
        self,
        information_set: InformationSetV3,
        *,
        candidate: PrimarySignalCandidateV3,
        registry: Mapping[str, ImmutableManifestV3],
        evidence_registry: Mapping[str, EvidenceRecordV3],
        physical_registry: Mapping[str, LedgerRecord],
        before_sequence: int | None,
    ) -> None:
        policy = self._physical_policy_for_information_set(
            information_set,
            registry=registry,
            evidence_registry=evidence_registry,
        )
        if policy is None:
            if candidate.entry_scenario in {
                EntryScenario.FORWARD_MARKET_ORDER,
                EntryScenario.LIVE_MARKET_ORDER,
            }:
                raise LedgerConflictError(
                    "forward/live candidate requires an approved physical adapter-policy source"
                )
            return
        gates = [
            item
            for item in physical_registry.values()
            if isinstance(item, PhysicalEvidenceGateV3)
            and item.information_set_id == information_set.information_set_id
            and item.gate_stage is PhysicalGateStage.DECISION_INPUT
        ]
        if len(gates) != 1 or gates[0].verdict is not PhysicalGateVerdict.PASS:
            raise LedgerConflictError(
                "physical source requires one PASS decision-input gate before promotion"
            )
        gate = gates[0]
        prefix_deadlines: list[datetime] = []
        for prefix_id in gate.evidence_prefix_ids:
            prefix = physical_registry.get(prefix_id)
            if not isinstance(prefix, EvidencePrefixV3):
                raise LedgerNotFoundError(
                    "physical decision gate evidence prefix is not registered"
                )
            prefix_deadlines.append(prefix.health_valid_until)
        if not prefix_deadlines:
            raise LedgerConflictError(
                "physical decision gate binds no evidence-prefix deadline"
            )
        if candidate.candidate_available_ts > min(prefix_deadlines):
            raise LedgerConflictError(
                "candidate availability postdates its physical evidence validity"
            )
        if candidate.entry_scenario in {
            EntryScenario.FORWARD_MARKET_ORDER,
            EntryScenario.LIVE_MARKET_ORDER,
        }:
            gate_sequence = self._object_first_receipt_sequence(
                LedgerRecordKind.PHYSICAL_EVIDENCE_GATE,
                gate.physical_evidence_gate_id,
                before_sequence=before_sequence,
            )
            gate_receipt_ts = self.get_receipt(gate_sequence).receipt_ts
            if (
                max(gate.evaluated_at, gate_receipt_ts)
                > candidate.candidate_available_ts
            ):
                raise LedgerConflictError(
                    "forward/live candidate predates its physical decision gate"
                )

    def _validate_physical_authority_receipt_deadline(
        self,
        record: LedgerRecord,
        receipt: LedgerReceipt,
        *,
        before_sequence: int,
    ) -> None:
        """Reject physically authoritative objects durably registered after expiry."""

        prefix_ids: tuple[str, ...] = ()
        physical_registry = self._physical_registry(before_sequence=before_sequence)
        if isinstance(record, DependencySelectionProofV3):
            prefix_ids = (record.evidence_prefix_id,)
        elif isinstance(record, PhysicalEvidenceGateV3):
            prefix_ids = record.evidence_prefix_ids
        elif isinstance(record, PrimarySignalCandidateV3):
            information_set = self._load_record(
                LedgerRecordKind.INFORMATION_SET,
                record.information_set_id,
                before_sequence=before_sequence,
            )
            if not isinstance(information_set, InformationSetV3):
                raise LedgerNotFoundError("candidate information set is not registered")
            registry = self._manifest_registry(before_sequence=before_sequence)
            evidence_registry = self._evidence_registry(before_sequence=before_sequence)
            policy = self._physical_policy_for_information_set(
                information_set,
                registry=registry,
                evidence_registry=evidence_registry,
            )
            if policy is None:
                return
            gates = [
                item
                for item in physical_registry.values()
                if isinstance(item, PhysicalEvidenceGateV3)
                and item.information_set_id == information_set.information_set_id
                and item.gate_stage is PhysicalGateStage.DECISION_INPUT
                and item.verdict is PhysicalGateVerdict.PASS
            ]
            if len(gates) != 1:
                raise LedgerConflictError(
                    "physical candidate requires one registered PASS decision gate"
                )
            prefix_ids = gates[0].evidence_prefix_ids
        else:
            return

        if not prefix_ids:
            raise LedgerConflictError(
                "physical authority record binds no evidence prefix"
            )
        for prefix_id in prefix_ids:
            prefix = physical_registry.get(prefix_id)
            if not isinstance(prefix, EvidencePrefixV3):
                raise LedgerNotFoundError(
                    "physical authority evidence prefix is not registered"
                )
            if receipt.receipt_ts > prefix.health_valid_until:
                raise LedgerConflictError(
                    "physical authority receipt postdates evidence validity"
                )

    def _validate_candidate_neutral_projection(
        self,
        materialization: CandidateFeatureMaterializationV3,
        *,
        evidence_registry: Mapping[str, EvidenceRecordV3],
        before_sequence: int | None,
    ) -> None:
        """Keep candidate-neutral feature positions invariant across candidates."""

        schema = evidence_registry.get(materialization.feature_schema_id)
        if not isinstance(schema, FeatureSchemaV3):
            raise LedgerNotFoundError(
                "materialization feature schema is not registered"
            )
        neutral_positions: list[int] = []
        for position, feature_id in enumerate(schema.feature_definition_ids):
            feature = evidence_registry.get(feature_id)
            if not isinstance(feature, FeatureDefinitionV3):
                raise LedgerNotFoundError(
                    "materialization feature definition is not registered"
                )
            if not feature.candidate_conditioned:
                neutral_positions.append(position)
        if not neutral_positions:
            return
        projection = tuple(
            materialization.feature_values[position] for position in neutral_positions
        )
        for prior in self._records_before(
            LedgerRecordKind.CANDIDATE_FEATURE_MATERIALIZATION,
            before_sequence=before_sequence,
        ):
            assert isinstance(prior, CandidateFeatureMaterializationV3)
            if (
                prior.information_set_id != materialization.information_set_id
                or prior.information_set_record_hash
                != materialization.information_set_record_hash
                or prior.feature_schema_id != materialization.feature_schema_id
            ):
                continue
            prior_projection = tuple(
                prior.feature_values[position] for position in neutral_positions
            )
            if prior_projection != projection:
                raise LedgerConflictError(
                    "candidate-neutral feature positions differ across materializations"
                )

    def _validate_action_inputs_latest_applicable(
        self,
        *,
        resolution: ActionResolutionV3,
        information_set: InformationSetV3,
        protocol: ActionProtocolV3,
        evidence_registry: Mapping[str, EvidenceRecordV3],
    ) -> None:
        """Require deterministic as-of schedule and mapping inputs for all outcomes."""

        cutoff = information_set.observation_cutoff_ts
        selected_calendar = evidence_registry.get(resolution.calendar_snapshot_id)
        if not isinstance(selected_calendar, CalendarScheduleSnapshotV3):
            raise LedgerNotFoundError(
                "action-resolution calendar snapshot is not registered"
            )
        window, _ = resolve_scheduled_action_window_v3(
            calendar=selected_calendar,
            protocol=protocol,
            resolved_at=resolution.resolved_at,
        )
        submission = resolution.resolved_at + timedelta(
            microseconds=protocol.submission_delay_microseconds
        )
        if window is not None:
            submission = window.earliest_order_submission_ts

        known_calendars: list[CalendarScheduleSnapshotV3] = []
        covering_calendars: list[CalendarScheduleSnapshotV3] = []
        for item in evidence_registry.values():
            if not isinstance(item, CalendarScheduleSnapshotV3):
                continue
            if (item.venue_id, item.contract_id) != (
                information_set.venue_id,
                information_set.contract_id,
            ):
                continue
            if item.known_at > cutoff or item.frozen_at > cutoff:
                continue
            artifact = evidence_registry.get(item.calendar_source_artifact_id)
            if not isinstance(artifact, CalendarSourceArtifactV3):
                continue
            if (
                artifact.retrieved_at > cutoff
                or artifact.authority not in protocol.allowed_calendar_authorities
            ):
                continue
            validate_calendar_schedule_artifact_v3(item, artifact)
            known_calendars.append(item)
            covers_submission = (
                item.coverage_start_ts <= submission
                and item.coverage_end_ts_exclusive > submission
            )
            covers_window = (
                window is None
                or item.coverage_end_ts_exclusive >= window.entry_expiry_ts
            )
            if covers_submission and covers_window:
                covering_calendars.append(item)
        if not known_calendars:
            raise LedgerConflictError(
                "no authoritative calendar was known by the information cutoff"
            )
        calendar_pool = covering_calendars or known_calendars
        _, latest_calendar = max(
            enumerate(calendar_pool),
            key=lambda pair: (pair[1].known_at, pair[1].frozen_at, pair[0]),
        )
        if latest_calendar.calendar_snapshot_id != resolution.calendar_snapshot_id:
            raise LedgerConflictError(
                "action resolution does not use the latest applicable calendar "
                "revision known by the information cutoff"
            )

        known_mappings = [
            item
            for item in evidence_registry.values()
            if isinstance(item, InstrumentMappingV3)
            and (item.asset_id, item.venue_id, item.source_contract_id)
            == (
                information_set.asset_id,
                information_set.venue_id,
                information_set.contract_id,
            )
            and item.known_at <= cutoff
        ]
        if not known_mappings:
            raise LedgerConflictError(
                "no instrument mapping was known by the information cutoff"
            )
        covering_mappings = (
            [
                item
                for item in known_mappings
                if item.effective_start_ts <= window.earliest_entry_ts
                and item.effective_end_ts_exclusive >= window.entry_expiry_ts
            ]
            if window is not None
            else []
        )
        mapping_pool = covering_mappings or known_mappings
        _, latest_mapping = max(
            enumerate(mapping_pool),
            key=lambda pair: (pair[1].known_at, pair[0]),
        )
        if latest_mapping.instrument_mapping_id != resolution.instrument_mapping_id:
            raise LedgerConflictError(
                "action resolution does not use the latest applicable instrument "
                "mapping known by the information cutoff"
            )

    def _validate_final_holdout_registration_order(
        self,
        manifest: ImmutableManifestV3,
        *,
        registry: Mapping[str, ImmutableManifestV3],
        evidence_registry: Mapping[str, EvidenceRecordV3],
        before_sequence: int | None,
    ) -> None:
        """Require final-holdout evidence to accrue after protocol receipt."""

        if (
            manifest.manifest_type is not ManifestType.SPLIT
            or manifest.payload["cohort_class"] != "FINAL_HOLDOUT"
        ):
            return
        protocol_id = manifest.payload["protocol_manifest_id"]
        protocol = registry.get(protocol_id)
        if not isinstance(protocol, ImmutableManifestV3):
            raise LedgerNotFoundError("final-holdout protocol is not registered")
        effective_source_id = manifest.payload["source_manifest_id"]
        effective_source = registry.get(effective_source_id)
        if not isinstance(effective_source, ImmutableManifestV3):
            raise LedgerNotFoundError(
                "final-holdout effective source is not registered"
            )
        self._validate_post_protocol_source_registration(
            protocol=protocol,
            effective_source=effective_source,
            registry=registry,
            evidence_registry=evidence_registry,
            before_sequence=before_sequence,
            context="final-holdout",
        )

    def _validate_post_protocol_source_registration(
        self,
        *,
        protocol: ImmutableManifestV3,
        effective_source: ImmutableManifestV3,
        registry: Mapping[str, ImmutableManifestV3],
        evidence_registry: Mapping[str, EvidenceRecordV3],
        before_sequence: int | None,
        context: str,
    ) -> None:
        """Prove effective source accrual follows local protocol registration."""

        protocol_sequence = self._object_first_receipt_sequence(
            LedgerRecordKind.MANIFEST,
            protocol.manifest_id,
            before_sequence=before_sequence,
        )
        anchor_source_id = protocol.payload["source_manifest_id"]

        descendants: list[ImmutableManifestV3] = []
        current = effective_source
        seen: set[str] = set()
        while current.manifest_id != anchor_source_id:
            if current.manifest_id in seen:
                raise CanonicalizationError("source lineage contains a cycle")
            seen.add(current.manifest_id)
            descendants.append(current)
            parent_id = current.payload["parent_source_manifest_id"]
            if parent_id is None:
                raise CanonicalizationError(
                    f"{context} source is not a descendant of its protocol source"
                )
            parent = registry.get(parent_id)
            if not isinstance(parent, ImmutableManifestV3):
                raise LedgerNotFoundError(
                    f"{context} source ancestor is not registered"
                )
            current = parent
        if not descendants:
            raise LedgerConflictError(
                f"{context} source must accrue after protocol registration"
            )
        anchor_source = current
        anchor_bundle = evidence_registry.get(
            anchor_source.payload["source_content_root"]
        )
        if not isinstance(anchor_bundle, SourceBundleV3):
            raise LedgerNotFoundError(
                f"{context} anchor source bundle is not registered"
            )
        anchor_member_ids = set(anchor_bundle.source_member_ids)

        for source in descendants:
            source_sequence = self._object_first_receipt_sequence(
                LedgerRecordKind.MANIFEST,
                source.manifest_id,
                before_sequence=before_sequence,
            )
            if source_sequence <= protocol_sequence:
                raise LedgerConflictError(
                    f"{context} source descendants must be registered after the "
                    "protocol"
                )
            bundle = evidence_registry.get(source.payload["source_content_root"])
            if not isinstance(bundle, SourceBundleV3):
                raise LedgerNotFoundError(f"{context} source bundle is not registered")
            bundle_sequence = self._object_first_receipt_sequence(
                LedgerRecordKind.SOURCE_BUNDLE,
                bundle.source_bundle_id,
                before_sequence=before_sequence,
            )
            if bundle_sequence <= protocol_sequence:
                raise LedgerConflictError(
                    f"{context} source bundles must be registered after the protocol"
                )
            for member_id in bundle.source_member_ids:
                if member_id in anchor_member_ids:
                    continue
                member_sequence = self._object_first_receipt_sequence(
                    LedgerRecordKind.SOURCE_BUNDLE_MEMBER,
                    member_id,
                    before_sequence=before_sequence,
                )
                if member_sequence <= protocol_sequence:
                    raise LedgerConflictError(
                        f"{context} source members must be registered after the protocol"
                    )

    def _active_head_before(
        self,
        head_type: str,
        semantic_key: str,
        *,
        before_sequence: int | None,
    ) -> str | None:
        sql = """
            SELECT new_identity_id FROM head_transitions
            WHERE head_type = ? AND semantic_key = ?
        """
        params: tuple[Any, ...] = (head_type, semantic_key)
        if before_sequence is not None:
            sql += " AND receipt_sequence < ?"
            params += (before_sequence,)
        sql += " ORDER BY receipt_sequence DESC LIMIT 1"
        row = self._connection.execute(sql, params).fetchone()
        return None if row is None else str(row[0])

    def _validate_supersession_clock(
        self,
        record: LedgerRecord,
        current_head: str | None,
    ) -> None:
        if isinstance(record, LabelOutcomeV3) and current_head is not None:
            previous = self._load_record(
                LedgerRecordKind.LABEL_OUTCOME,
                current_head,
            )
            assert isinstance(previous, LabelOutcomeV3)
            if record.label_known_ts < previous.label_known_ts:
                raise LedgerConflictError(
                    "corrected label_known_ts must not move backwards"
                )
        if isinstance(record, EventDependenceAssignmentV3) and current_head is not None:
            previous = self._load_record(
                LedgerRecordKind.EVENT_DEPENDENCE_ASSIGNMENT,
                current_head,
            )
            assert isinstance(previous, EventDependenceAssignmentV3)
            if record.assignment_known_ts < previous.assignment_known_ts:
                raise LedgerConflictError(
                    "corrected assignment_known_ts must not move backwards"
                )

    def _validate_split_roots(
        self,
        manifest: ImmutableManifestV3,
        *,
        before_sequence: int | None = None,
    ) -> None:
        if manifest.manifest_type is not ManifestType.SPLIT:
            return
        roots = {
            item.channel: item.receipt_hash
            for item in self._channel_roots(before_sequence=before_sequence)
        }
        if manifest.payload["event_ledger_root"] != roots[LedgerChannel.EVENT]:
            raise LedgerConflictError(
                "split event_ledger_root differs from the registered EVENT prefix"
            )
        if manifest.payload["label_ledger_root"] != roots[LedgerChannel.LABEL]:
            raise LedgerConflictError(
                "split label_ledger_root differs from the registered LABEL prefix"
            )

    def append(
        self,
        record: LedgerRecord,
        *,
        idempotency_key: str,
    ) -> LedgerReceipt:
        """Atomically validate and register one exact V3 object."""

        kind = _record_kind(record)
        key = canonical_identifier(
            idempotency_key, field="idempotency_key", maximum=256
        )
        canonical_blob = canonical_json_bytes(record.as_dict())
        if len(canonical_blob) > int(self._read_meta()["max_object_bytes"]):
            raise LedgerConflictError("canonical object exceeds max_object_bytes")
        parsed = _parse_record(kind, canonical_blob)
        if canonical_json_bytes(parsed.as_dict()) != canonical_blob:
            raise CanonicalizationError("record does not survive canonical round trip")
        identity_id = _record_identity(parsed)
        content_hash = _raw_sha256(canonical_blob)
        record_hash = _record_native_hash(parsed, content_hash)
        head_type, semantic_key, expected_head, new_head = _semantic_claim(parsed)
        request_hash = sha256_digest(
            {
                "content_hash": content_hash,
                "expected_head": expected_head,
                "operation": LedgerOperation.APPEND_RECORD.value,
                "record_kind": kind.value,
                "semantic_key": semantic_key,
            }
        )
        with self._transaction():
            replay = self._idempotent_receipt(
                idempotency_key=key,
                request_hash=request_hash,
            )
            if replay is not None:
                return replay
            duplicate = self._connection.execute(
                """
                SELECT first_receipt_sequence FROM objects
                WHERE content_hash = ? OR (record_kind = ? AND identity_id = ?)
                """,
                (content_hash, kind.value, identity_id),
            ).fetchone()
            if duplicate is not None:
                raise LedgerAlreadyRegisteredError(
                    "object was already registered under another idempotency key; "
                    f"first receipt sequence={duplicate[0]}"
                )
            current_head = self.active_head(head_type, semantic_key)
            if current_head != expected_head:
                raise LedgerConflictError(
                    "semantic compare-and-swap failed: active head differs from "
                    "the record predecessor"
                )
            self._validate_record_links(parsed)
            self._validate_supersession_clock(parsed, current_head)
            if isinstance(parsed, ImmutableManifestV3):
                self._validate_split_roots(parsed)

            next_sequence = self._last_receipt_state(_KIND_CHANNEL[kind])[0] + 1
            self._connection.execute(
                """
                INSERT INTO objects(
                    content_hash, record_kind, identity_id, record_hash,
                    semantic_key, canonical_blob, first_receipt_sequence
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    content_hash,
                    kind.value,
                    identity_id,
                    record_hash,
                    semantic_key,
                    canonical_blob,
                    next_sequence,
                ),
            )
            self._fault("after_object_insert")
            receipt = self._issue_receipt(
                channel=_KIND_CHANNEL[kind],
                operation=LedgerOperation.APPEND_RECORD,
                record_kind=kind.value,
                identity_id=identity_id,
                record_hash=record_hash,
                content_hash=content_hash,
                semantic_key=semantic_key,
                head_type=head_type,
                expected_head=expected_head,
                new_head=new_head,
                idempotency_key=key,
                request_hash=request_hash,
                minimum_ts=_record_terminal_ts(parsed),
            )
            if receipt.global_sequence != next_sequence:
                raise LedgerConflictError("receipt sequence allocation drifted")
            self._validate_physical_authority_receipt_deadline(
                parsed,
                receipt,
                before_sequence=receipt.global_sequence,
            )
            return receipt

    def _channel_roots(
        self,
        *,
        before_sequence: int | None = None,
    ) -> tuple[LedgerChannelRoot, ...]:
        roots: list[LedgerChannelRoot] = []
        for channel in LedgerChannel:
            sql = """
                SELECT channel_sequence, receipt_hash FROM receipts
                WHERE channel = ?
            """
            params: tuple[Any, ...] = (channel.value,)
            if before_sequence is not None:
                sql += " AND global_sequence < ?"
                params += (before_sequence,)
            sql += " ORDER BY channel_sequence DESC LIMIT 1"
            row = self._connection.execute(sql, params).fetchone()
            roots.append(
                LedgerChannelRoot(
                    channel=channel,
                    sequence=0 if row is None else int(row[0]),
                    receipt_hash=GENESIS_HASH if row is None else str(row[1]),
                )
            )
        return tuple(sorted(roots, key=lambda item: item.channel.value))

    def _global_root(
        self,
        *,
        at_sequence: int | None = None,
    ) -> tuple[int, str]:
        sql = "SELECT global_sequence, receipt_hash FROM receipts"
        params: tuple[Any, ...] = ()
        if at_sequence is not None:
            sql += " WHERE global_sequence <= ?"
            params = (at_sequence,)
        sql += " ORDER BY global_sequence DESC LIMIT 1"
        row = self._connection.execute(sql, params).fetchone()
        return (0, GENESIS_HASH) if row is None else (int(row[0]), str(row[1]))

    def _checkpoint_for_receipt(self, receipt_sequence: int) -> SignedLedgerCheckpoint:
        row = self._connection.execute(
            "SELECT canonical_blob FROM checkpoints WHERE receipt_sequence = ?",
            (receipt_sequence,),
        ).fetchone()
        if row is None:
            raise LedgerVerificationError("checkpoint receipt has no checkpoint object")
        return SignedLedgerCheckpoint.from_mapping(
            _parse_json_object(bytes(row[0]), context="SignedLedgerCheckpoint")
        )

    def create_checkpoint(
        self,
        signer: CheckpointSigner,
        *,
        idempotency_key: str,
    ) -> SignedLedgerCheckpoint:
        """Sign the current prefix and register the signature atomically."""

        if not isinstance(signer, CheckpointSigner):
            raise LedgerConfigurationError("signer does not implement CheckpointSigner")
        algorithm = canonical_identifier(
            signer.algorithm, field="signature_algorithm", maximum=32
        )
        key_id = canonical_identifier(signer.key_id, field="key_id", maximum=256)
        if algorithm != "ED25519":
            raise LedgerConfigurationError("only ED25519 checkpoints are supported")
        public_key_bytes = signer.public_key_bytes
        if not isinstance(public_key_bytes, bytes) or len(public_key_bytes) != 32:
            raise LedgerConfigurationError(
                "ED25519 signer must expose exactly 32 public-key bytes"
            )
        from .ledger_signing import (
            Ed25519CheckpointVerifier,
            derive_ed25519_key_id,
        )

        if derive_ed25519_key_id(public_key_bytes) != key_id:
            raise LedgerConfigurationError(
                "signer key ID does not bind its exposed public key"
            )
        try:
            signing_verifier = Ed25519CheckpointVerifier.from_public_bytes(
                public_key_bytes,
                key_id=key_id,
            )
        except (CanonicalizationError, TypeError, ValueError) as exc:
            raise LedgerConfigurationError(
                "signer exposes an invalid Ed25519 public-key/signature verifier"
            ) from exc
        key = canonical_identifier(
            idempotency_key, field="idempotency_key", maximum=256
        )
        request_hash = sha256_digest(
            {
                "key_id": key_id,
                "operation": LedgerOperation.CREATE_CHECKPOINT.value,
                "signature_algorithm": algorithm,
            }
        )
        with self._transaction():
            replay = self._idempotent_receipt(
                idempotency_key=key,
                request_hash=request_hash,
            )
            if replay is not None:
                return self._checkpoint_for_receipt(replay.global_sequence)

            previous_row = self._connection.execute(
                """
                SELECT checkpoint_id, key_id, signature_algorithm
                FROM checkpoints ORDER BY receipt_sequence DESC LIMIT 1
                """
            ).fetchone()
            previous_id: str | None = None
            if previous_row is not None:
                previous_id = str(previous_row[0])
                if previous_row[1] != key_id or previous_row[2] != algorithm:
                    raise LedgerConflictError(
                        "silent checkpoint key rotation is prohibited; a dual-signed "
                        "rotation protocol is required"
                    )
            global_sequence, global_root = self._global_root()
            signed_at = self._now()
            last_row = self._connection.execute(
                "SELECT receipt_ts FROM receipts ORDER BY global_sequence DESC LIMIT 1"
            ).fetchone()
            if last_row is not None and signed_at < utc_datetime(
                last_row[0], field="receipt_ts"
            ):
                raise LedgerConflictError("ledger clock moved backwards")
            unsigned = {
                "canonicalization_version": CANONICALIZATION_VERSION,
                "channel_roots": [item.as_dict() for item in self._channel_roots()],
                "checkpoint_schema_version": CHECKPOINT_SCHEMA_VERSION,
                "global_receipt_root": global_root,
                "global_sequence": global_sequence,
                "key_id": key_id,
                "ledger_id": self.ledger_id,
                "ledger_schema_version": LEDGER_SCHEMA_VERSION,
                "previous_checkpoint_id": previous_id,
                "signature_algorithm": algorithm,
                "signed_at": utc_iso(signed_at),
            }
            signature = signer.sign(canonical_json_bytes(unsigned))
            if not isinstance(signature, bytes) or len(signature) != 64:
                raise LedgerConfigurationError(
                    "ED25519 signer must return exactly 64 signature bytes"
                )
            try:
                signing_verifier.verify(canonical_json_bytes(unsigned), signature)
            except Exception as exc:
                raise LedgerConfigurationError(
                    "signer produced an invalid checkpoint signature"
                ) from exc
            checkpoint = SignedLedgerCheckpoint(
                ledger_id=self.ledger_id,
                signed_at=signed_at,
                global_sequence=global_sequence,
                global_receipt_root=global_root,
                channel_roots=self._channel_roots(),
                previous_checkpoint_id=previous_id,
                signature_algorithm=algorithm,
                key_id=key_id,
                signature=signature.hex(),
            )
            blob = canonical_json_bytes(checkpoint.as_dict())
            content_hash = _raw_sha256(blob)
            next_sequence = global_sequence + 1
            self._connection.execute(
                """
                INSERT INTO checkpoints(
                    checkpoint_id, content_hash, key_id, signature_algorithm,
                    signed_global_sequence, previous_checkpoint_id,
                    receipt_sequence, canonical_blob
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    checkpoint.checkpoint_id,
                    content_hash,
                    key_id,
                    algorithm,
                    global_sequence,
                    previous_id,
                    next_sequence,
                    blob,
                ),
            )
            self._fault("after_checkpoint_insert")
            receipt = self._issue_receipt(
                channel=LedgerChannel.GOVERNANCE,
                operation=LedgerOperation.CREATE_CHECKPOINT,
                record_kind="SIGNED_LEDGER_CHECKPOINT",
                identity_id=checkpoint.checkpoint_id,
                record_hash=content_hash,
                content_hash=content_hash,
                semantic_key=self.ledger_id,
                head_type="SIGNED_LEDGER_CHECKPOINT",
                expected_head=previous_id,
                new_head=checkpoint.checkpoint_id,
                idempotency_key=key,
                request_hash=request_hash,
                minimum_ts=signed_at,
                governance_payload_hash=content_hash,
                receipt_ts=signed_at,
            )
            if receipt.global_sequence != next_sequence:
                raise LedgerConflictError("checkpoint receipt sequence drifted")
            return checkpoint

    def _load_checkpoint(self, checkpoint_id: str) -> SignedLedgerCheckpoint:
        normalized = canonical_hash(checkpoint_id, field="checkpoint_id")
        row = self._connection.execute(
            "SELECT canonical_blob FROM checkpoints WHERE checkpoint_id = ?",
            (normalized,),
        ).fetchone()
        if row is None:
            raise LedgerNotFoundError(f"unknown checkpoint {normalized}")
        return SignedLedgerCheckpoint.from_mapping(
            _parse_json_object(bytes(row[0]), context="SignedLedgerCheckpoint")
        )

    def _grant_for_receipt(self, receipt_sequence: int) -> HoldoutEvaluationGrant:
        row = self._connection.execute(
            "SELECT canonical_blob FROM holdout_grants WHERE receipt_sequence = ?",
            (receipt_sequence,),
        ).fetchone()
        if row is None:
            raise LedgerVerificationError("grant receipt has no grant object")
        return HoldoutEvaluationGrant.from_mapping(
            _parse_json_object(bytes(row[0]), context="HoldoutEvaluationGrant")
        )

    def grant_final_holdout_evaluation(
        self,
        *,
        protocol_manifest_id: str,
        split_manifest_id: str,
        checkpoint_id: str,
        approval_hash: str,
        evidence_gate_hash: str,
        frozen_artifact_hash: str,
        external_anchor_hash: str,
        idempotency_key: str,
    ) -> HoldoutEvaluationGrant:
        """Issue one locally one-time, checkpoint-bound final-holdout grant.

        This is an authorization/audit primitive.  It does not prevent direct
        filesystem reads or by itself survive whole-database rollback. Production
        use requires a post-grant external seal and an isolated evaluator.
        """

        values = {
            "protocol_manifest_id": canonical_hash(
                protocol_manifest_id, field="protocol_manifest_id"
            ),
            "split_manifest_id": canonical_hash(
                split_manifest_id, field="split_manifest_id"
            ),
            "checkpoint_id": canonical_hash(checkpoint_id, field="checkpoint_id"),
            "approval_hash": canonical_hash(approval_hash, field="approval_hash"),
            "evidence_gate_hash": canonical_hash(
                evidence_gate_hash, field="evidence_gate_hash"
            ),
            "frozen_artifact_hash": canonical_hash(
                frozen_artifact_hash, field="frozen_artifact_hash"
            ),
            "external_anchor_hash": canonical_hash(
                external_anchor_hash, field="external_anchor_hash"
            ),
        }
        key = canonical_identifier(
            idempotency_key, field="idempotency_key", maximum=256
        )
        request_hash = sha256_digest(
            {
                **values,
                "operation": LedgerOperation.GRANT_HOLDOUT_EVALUATION.value,
            }
        )
        with self._transaction():
            replay = self._idempotent_receipt(
                idempotency_key=key,
                request_hash=request_hash,
            )
            if replay is not None:
                return self._grant_for_receipt(replay.global_sequence)
            conflict = self._connection.execute(
                """
                SELECT grant_id FROM holdout_grants
                WHERE protocol_manifest_id = ? OR split_manifest_id = ?
                """,
                (values["protocol_manifest_id"], values["split_manifest_id"]),
            ).fetchone()
            if conflict is not None:
                raise HoldoutGrantConflictError(
                    "final holdout evaluation was already granted for this protocol "
                    "or split"
                )
            protocol = self._load_record(
                LedgerRecordKind.MANIFEST,
                values["protocol_manifest_id"],
            )
            split = self._load_record(
                LedgerRecordKind.MANIFEST,
                values["split_manifest_id"],
            )
            assert isinstance(protocol, ImmutableManifestV3)
            assert isinstance(split, ImmutableManifestV3)
            if protocol.manifest_type is not ManifestType.PROTOCOL:
                raise LedgerConflictError("grant protocol must be a PROTOCOL manifest")
            if split.manifest_type is not ManifestType.SPLIT:
                raise LedgerConflictError("grant split must be a SPLIT manifest")
            if split.payload["cohort_class"] != "FINAL_HOLDOUT":
                raise LedgerConflictError("grant requires a FINAL_HOLDOUT split")
            if split.payload["protocol_manifest_id"] != protocol.manifest_id:
                raise LedgerConflictError("holdout split belongs to another protocol")
            if (
                split.payload["holdout_policy_id"]
                != protocol.payload["holdout_policy_id"]
            ):
                raise LedgerConflictError("holdout policy binding differs")
            checkpoint = self._load_checkpoint(values["checkpoint_id"])
            latest_checkpoint = self._connection.execute(
                """
                SELECT checkpoint_id, receipt_sequence FROM checkpoints
                ORDER BY receipt_sequence DESC LIMIT 1
                """
            ).fetchone()
            assert latest_checkpoint is not None
            current_sequence, _ = self._global_root()
            if latest_checkpoint[0] != checkpoint.checkpoint_id:
                raise LedgerConflictError("grant must bind the latest checkpoint")
            if int(latest_checkpoint[1]) != current_sequence:
                raise LedgerConflictError(
                    "new receipts were appended after the checkpoint registration"
                )
            split_sequence = self._connection.execute(
                """
                SELECT first_receipt_sequence FROM objects
                WHERE record_kind = ? AND identity_id = ?
                """,
                (LedgerRecordKind.MANIFEST.value, split.manifest_id),
            ).fetchone()
            assert split_sequence is not None
            if int(split_sequence[0]) > checkpoint.global_sequence:
                raise LedgerConflictError("checkpoint does not cover the holdout split")
            granted_at = self._now()
            if granted_at < checkpoint.signed_at:
                raise LedgerConflictError("grant time precedes checkpoint signing")
            grant = HoldoutEvaluationGrant(
                ledger_id=self.ledger_id,
                granted_at=granted_at,
                **values,
            )
            blob = canonical_json_bytes(grant.as_dict())
            content_hash = _raw_sha256(blob)
            next_sequence = current_sequence + 1
            self._connection.execute(
                """
                INSERT INTO holdout_grants(
                    grant_id, content_hash, protocol_manifest_id,
                    split_manifest_id, checkpoint_id, receipt_sequence,
                    canonical_blob
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    grant.grant_id,
                    content_hash,
                    grant.protocol_manifest_id,
                    grant.split_manifest_id,
                    grant.checkpoint_id,
                    next_sequence,
                    blob,
                ),
            )
            self._fault("after_holdout_grant_insert")
            receipt = self._issue_receipt(
                channel=LedgerChannel.GOVERNANCE,
                operation=LedgerOperation.GRANT_HOLDOUT_EVALUATION,
                record_kind="HOLDOUT_EVALUATION_GRANT",
                identity_id=grant.grant_id,
                record_hash=content_hash,
                content_hash=content_hash,
                semantic_key=grant.protocol_manifest_id,
                head_type="HOLDOUT_EVALUATION_GRANT",
                expected_head=None,
                new_head=grant.grant_id,
                idempotency_key=key,
                request_hash=request_hash,
                minimum_ts=granted_at,
                governance_payload_hash=content_hash,
                receipt_ts=granted_at,
            )
            if receipt.global_sequence != next_sequence:
                raise LedgerConflictError("holdout receipt sequence drifted")
            return grant

    def _verify_sqlite(self) -> None:
        integrity = self._connection.execute("PRAGMA integrity_check").fetchall()
        if integrity != [("ok",)]:
            raise LedgerVerificationError(f"SQLite integrity_check failed: {integrity}")
        foreign = self._connection.execute("PRAGMA foreign_key_check").fetchone()
        if foreign is not None:
            raise LedgerVerificationError(
                f"SQLite foreign_key_check failed at {foreign}"
            )
        triggers = {
            row[0]
            for row in self._connection.execute(
                "SELECT name FROM sqlite_schema WHERE type = 'trigger'"
            )
        }
        missing = sorted(_IMMUTABILITY_TRIGGERS - triggers)
        if missing:
            raise LedgerVerificationError(
                f"immutable-table triggers are missing: {missing}"
            )
        actual_schema = _schema_fingerprint(self._connection)
        if actual_schema != _expected_schema_fingerprint():
            raise LedgerVerificationError(
                "SQLite application schema differs from the certified ledger schema"
            )

    def _verify_receipt_chain(
        self,
    ) -> tuple[int, str, dict[LedgerChannel, tuple[int, str]]]:
        expected_global = 1
        previous_global = GENESIS_HASH
        channels = dict.fromkeys(LedgerChannel, (0, GENESIS_HASH))
        previous_ts: datetime | None = utc_datetime(
            self._read_meta()["created_at"], field="created_at"
        )
        for row in self._connection.execute(
            """
            SELECT global_sequence, channel, channel_sequence, receipt_hash,
                   receipt_ts, operation, record_kind, identity_id, record_hash,
                   content_hash, semantic_key, head_type, idempotency_key, request_hash,
                   expected_head, new_head, previous_global_receipt_hash,
                   previous_channel_receipt_hash, canonical_blob
            FROM receipts ORDER BY global_sequence
            """
        ):
            raw_blob = bytes(row[18])
            receipt = LedgerReceipt.from_mapping(
                _parse_json_object(raw_blob, context="LedgerReceipt")
            )
            if canonical_json_bytes(receipt.as_dict()) != raw_blob:
                raise LedgerVerificationError(
                    f"receipt BLOB is not exact canonical JSON at {expected_global}"
                )
            columns = (
                receipt.global_sequence,
                receipt.channel.value,
                receipt.channel_sequence,
                receipt.receipt_hash,
                utc_iso(receipt.receipt_ts),
                receipt.operation.value,
                receipt.record_kind,
                receipt.identity_id,
                receipt.record_hash,
                receipt.content_hash,
                receipt.semantic_key,
                receipt.head_type,
                receipt.idempotency_key,
                receipt.request_hash,
                receipt.expected_head,
                receipt.new_head,
                receipt.previous_global_receipt_hash,
                receipt.previous_channel_receipt_hash,
            )
            if tuple(row[:18]) != columns:
                raise LedgerVerificationError(
                    f"receipt columns differ from canonical blob at {expected_global}"
                )
            if receipt.ledger_id != self.ledger_id:
                raise LedgerVerificationError("receipt belongs to another ledger")
            if receipt.global_sequence != expected_global:
                raise LedgerVerificationError("global receipt sequence has a gap")
            if receipt.previous_global_receipt_hash != previous_global:
                raise LedgerVerificationError("global receipt hash chain is broken")
            if previous_ts is not None and receipt.receipt_ts < previous_ts:
                raise LedgerVerificationError("receipt timestamps move backwards")
            channel_sequence, channel_hash = channels[receipt.channel]
            if receipt.channel_sequence != channel_sequence + 1:
                raise LedgerVerificationError("channel receipt sequence has a gap")
            if receipt.previous_channel_receipt_hash != channel_hash:
                raise LedgerVerificationError("channel receipt hash chain is broken")
            previous_global = receipt.receipt_hash
            previous_ts = receipt.receipt_ts
            channels[receipt.channel] = (
                receipt.channel_sequence,
                receipt.receipt_hash,
            )
            expected_global += 1
        return expected_global - 1, previous_global, channels

    def _verify_objects(self) -> int:
        count = 0
        max_object_bytes = int(self._read_meta()["max_object_bytes"])
        for row in self._connection.execute(
            """
            SELECT content_hash, record_kind, identity_id, record_hash,
                   semantic_key, canonical_blob, first_receipt_sequence
            FROM objects ORDER BY first_receipt_sequence
            """
        ):
            try:
                kind = LedgerRecordKind(row[1])
            except ValueError as exc:
                raise LedgerVerificationError("object has unsupported kind") from exc
            blob = bytes(row[5])
            record = _parse_record(kind, blob)
            if canonical_json_bytes(record.as_dict()) != blob:
                raise LedgerVerificationError(
                    f"object BLOB is not exact canonical JSON at receipt {row[6]}"
                )
            if len(blob) > max_object_bytes:
                raise LedgerVerificationError(
                    f"object exceeds max_object_bytes at receipt {row[6]}"
                )
            content_hash = _raw_sha256(blob)
            head_type, semantic_key, expected_head, new_head = _semantic_claim(record)
            expected = (
                content_hash,
                kind.value,
                _record_identity(record),
                _record_native_hash(record, content_hash),
                semantic_key,
            )
            if tuple(row[:5]) != expected:
                raise LedgerVerificationError(
                    f"object metadata differs from canonical content at receipt {row[6]}"
                )
            receipt = self.get_receipt(int(row[6]))
            expected_request_hash = sha256_digest(
                {
                    "content_hash": content_hash,
                    "expected_head": expected_head,
                    "operation": LedgerOperation.APPEND_RECORD.value,
                    "record_kind": kind.value,
                    "semantic_key": semantic_key,
                }
            )
            if receipt.operation is not LedgerOperation.APPEND_RECORD:
                raise LedgerVerificationError("object points to a non-append receipt")
            if (
                receipt.content_hash != content_hash
                or receipt.identity_id != _record_identity(record)
                or receipt.record_kind != kind.value
                or receipt.record_hash != _record_native_hash(record, content_hash)
                or receipt.semantic_key != semantic_key
                or receipt.head_type != head_type
                or receipt.expected_head != expected_head
                or receipt.new_head != new_head
                or receipt.request_hash != expected_request_hash
            ):
                raise LedgerVerificationError("object and append receipt differ")
            if receipt.receipt_ts < _record_terminal_ts(record):
                raise LedgerVerificationError(
                    "object was receipted before its information was available"
                )
            try:
                self._validate_record_links(record, before_sequence=int(row[6]))
                self._validate_physical_authority_receipt_deadline(
                    record,
                    receipt,
                    before_sequence=int(row[6]),
                )
                if isinstance(record, LabelOutcomeV3) and expected_head is not None:
                    predecessor = self._load_record(
                        LedgerRecordKind.LABEL_OUTCOME,
                        expected_head,
                        before_sequence=int(row[6]),
                    )
                    assert isinstance(predecessor, LabelOutcomeV3)
                    if record.label_known_ts < predecessor.label_known_ts:
                        raise LedgerConflictError(
                            "corrected label_known_ts moved backwards"
                        )
                if (
                    isinstance(record, EventDependenceAssignmentV3)
                    and expected_head is not None
                ):
                    predecessor = self._load_record(
                        LedgerRecordKind.EVENT_DEPENDENCE_ASSIGNMENT,
                        expected_head,
                        before_sequence=int(row[6]),
                    )
                    assert isinstance(predecessor, EventDependenceAssignmentV3)
                    if record.assignment_known_ts < predecessor.assignment_known_ts:
                        raise LedgerConflictError(
                            "corrected assignment_known_ts moved backwards"
                        )
                if isinstance(record, ImmutableManifestV3):
                    self._validate_split_roots(
                        record,
                        before_sequence=int(row[6]),
                    )
            except (CanonicalizationError, LedgerError) as exc:
                raise LedgerVerificationError(
                    f"object graph validation failed at receipt {row[6]}"
                ) from exc
            count += 1
        return count

    def _verify_head_transitions(self) -> int:
        heads: dict[tuple[str, str], str] = {}
        count = 0
        receipt_count = self._connection.execute(
            "SELECT count(*) FROM receipts"
        ).fetchone()[0]
        for row in self._connection.execute(
            """
            SELECT receipt_sequence, head_type, semantic_key,
                   previous_identity_id, new_identity_id, receipt_hash
            FROM head_transitions ORDER BY receipt_sequence
            """
        ):
            receipt = self.get_receipt(int(row[0]))
            key = (str(row[1]), str(row[2]))
            current = heads.get(key)
            if row[3] != current or receipt.expected_head != current:
                raise LedgerVerificationError(
                    f"head predecessor mismatch at receipt {row[0]}"
                )
            if (
                row[1] != receipt.head_type
                or row[2] != receipt.semantic_key
                or row[4] != receipt.new_head
                or row[5] != receipt.receipt_hash
            ):
                raise LedgerVerificationError(
                    f"head transition differs from receipt {row[0]}"
                )
            heads[key] = str(row[4])
            count += 1
        if count != receipt_count:
            raise LedgerVerificationError("every receipt must have one head transition")
        return count

    def _verify_receipt_bijections(self) -> None:
        """Prove every receipt has exactly one operation-specific child row."""

        objects = {
            int(row[0]): str(row[1])
            for row in self._connection.execute(
                "SELECT first_receipt_sequence, record_kind FROM objects"
            )
        }
        checkpoints = {
            int(row[0]): str(row[1])
            for row in self._connection.execute(
                "SELECT receipt_sequence, checkpoint_id FROM checkpoints"
            )
        }
        grants = {
            int(row[0]): str(row[1])
            for row in self._connection.execute(
                "SELECT receipt_sequence, grant_id FROM holdout_grants"
            )
        }
        operation_counts = dict.fromkeys(LedgerOperation, 0)
        for (raw_sequence,) in self._connection.execute(
            "SELECT global_sequence FROM receipts ORDER BY global_sequence"
        ):
            sequence = int(raw_sequence)
            receipt = self.get_receipt(sequence)
            operation_counts[receipt.operation] += 1
            has_object = sequence in objects
            has_checkpoint = sequence in checkpoints
            has_grant = sequence in grants
            if receipt.operation is LedgerOperation.APPEND_RECORD:
                try:
                    kind = LedgerRecordKind(receipt.record_kind)
                except ValueError as exc:
                    raise LedgerVerificationError(
                        f"append receipt {sequence} has an unsupported record kind"
                    ) from exc
                if (
                    not has_object
                    or has_checkpoint
                    or has_grant
                    or objects[sequence] != kind.value
                    or receipt.channel is not _KIND_CHANNEL[kind]
                    or receipt.governance_payload_hash is not None
                ):
                    raise LedgerVerificationError(
                        f"append receipt {sequence} has no exact object bijection"
                    )
            elif receipt.operation is LedgerOperation.CREATE_CHECKPOINT:
                if (
                    has_object
                    or not has_checkpoint
                    or has_grant
                    or receipt.channel is not LedgerChannel.GOVERNANCE
                    or receipt.record_kind != "SIGNED_LEDGER_CHECKPOINT"
                    or checkpoints[sequence] != receipt.identity_id
                    or receipt.governance_payload_hash is None
                ):
                    raise LedgerVerificationError(
                        f"checkpoint receipt {sequence} has no exact checkpoint bijection"
                    )
            elif receipt.operation is LedgerOperation.GRANT_HOLDOUT_EVALUATION:
                if (
                    has_object
                    or has_checkpoint
                    or not has_grant
                    or receipt.channel is not LedgerChannel.GOVERNANCE
                    or receipt.record_kind != "HOLDOUT_EVALUATION_GRANT"
                    or grants[sequence] != receipt.identity_id
                    or receipt.governance_payload_hash is None
                ):
                    raise LedgerVerificationError(
                        f"holdout receipt {sequence} has no exact grant bijection"
                    )
        expected_counts = {
            LedgerOperation.APPEND_RECORD: len(objects),
            LedgerOperation.CREATE_CHECKPOINT: len(checkpoints),
            LedgerOperation.GRANT_HOLDOUT_EVALUATION: len(grants),
        }
        if operation_counts != expected_counts:
            raise LedgerVerificationError(
                "receipt operations and immutable child tables are not bijective"
            )

    def _state_at_sequence(
        self,
        sequence: int,
    ) -> tuple[str, tuple[LedgerChannelRoot, ...]]:
        actual_sequence, root = self._global_root(at_sequence=sequence)
        if actual_sequence != sequence:
            if sequence == 0 and actual_sequence == 0:
                pass
            else:
                raise LedgerVerificationError(
                    f"checkpoint references missing receipt sequence {sequence}"
                )
        roots = self._channel_roots(before_sequence=sequence + 1)
        return root, roots

    def _verify_checkpoints(self, verifier: CheckpointVerifier | None = None) -> int:
        previous_id: str | None = None
        previous_key: tuple[str, str] | None = None
        created_at = utc_datetime(self._read_meta()["created_at"], field="created_at")
        count = 0
        for row in self._connection.execute(
            """
            SELECT checkpoint_id, content_hash, key_id, signature_algorithm,
                   signed_global_sequence, previous_checkpoint_id,
                   receipt_sequence, canonical_blob
            FROM checkpoints ORDER BY receipt_sequence
            """
        ):
            blob = bytes(row[7])
            checkpoint = SignedLedgerCheckpoint.from_mapping(
                _parse_json_object(blob, context="SignedLedgerCheckpoint")
            )
            if canonical_json_bytes(checkpoint.as_dict()) != blob:
                raise LedgerVerificationError(
                    "checkpoint BLOB is not exact canonical JSON"
                )
            expected_columns = (
                checkpoint.checkpoint_id,
                _raw_sha256(blob),
                checkpoint.key_id,
                checkpoint.signature_algorithm,
                checkpoint.global_sequence,
                checkpoint.previous_checkpoint_id,
            )
            if tuple(row[:6]) != expected_columns:
                raise LedgerVerificationError("checkpoint columns differ from blob")
            if checkpoint.ledger_id != self.ledger_id:
                raise LedgerVerificationError("checkpoint belongs to another ledger")
            if checkpoint.signed_at < created_at:
                raise LedgerVerificationError("checkpoint predates ledger creation")
            if checkpoint.global_sequence > 0:
                signed_receipt = self._connection.execute(
                    "SELECT receipt_ts FROM receipts WHERE global_sequence = ?",
                    (checkpoint.global_sequence,),
                ).fetchone()
                if signed_receipt is None:
                    raise LedgerVerificationError(
                        f"checkpoint references missing receipt sequence "
                        f"{checkpoint.global_sequence}"
                    )
                if checkpoint.signed_at < utc_datetime(
                    signed_receipt[0], field="receipt_ts"
                ):
                    raise LedgerVerificationError(
                        "checkpoint predates the receipt prefix it claims to sign"
                    )
            if checkpoint.previous_checkpoint_id != previous_id:
                raise LedgerVerificationError("checkpoint predecessor chain is broken")
            if checkpoint.global_sequence + 1 != int(row[6]):
                raise LedgerVerificationError(
                    "checkpoint registration does not immediately follow its signed prefix"
                )
            key = (checkpoint.key_id, checkpoint.signature_algorithm)
            if previous_key is not None and key != previous_key:
                raise LedgerVerificationError("checkpoint key changed without rotation")
            expected_root, expected_channels = self._state_at_sequence(
                checkpoint.global_sequence
            )
            if checkpoint.global_receipt_root != expected_root:
                raise LedgerVerificationError("checkpoint global root is incorrect")
            if checkpoint.channel_roots != expected_channels:
                raise LedgerVerificationError("checkpoint channel roots are incorrect")
            if verifier is not None:
                checkpoint.verify_signature(verifier)
            receipt = self.get_receipt(int(row[6]))
            expected_request_hash = sha256_digest(
                {
                    "key_id": checkpoint.key_id,
                    "operation": LedgerOperation.CREATE_CHECKPOINT.value,
                    "signature_algorithm": checkpoint.signature_algorithm,
                }
            )
            if (
                receipt.operation is not LedgerOperation.CREATE_CHECKPOINT
                or receipt.identity_id != checkpoint.checkpoint_id
                or receipt.content_hash != _raw_sha256(blob)
                or receipt.record_hash != _raw_sha256(blob)
                or receipt.semantic_key != self.ledger_id
                or receipt.head_type != "SIGNED_LEDGER_CHECKPOINT"
                or receipt.expected_head != checkpoint.previous_checkpoint_id
                or receipt.new_head != checkpoint.checkpoint_id
                or receipt.request_hash != expected_request_hash
                or receipt.governance_payload_hash != _raw_sha256(blob)
                or receipt.receipt_ts != checkpoint.signed_at
            ):
                raise LedgerVerificationError("checkpoint receipt is inconsistent")
            previous_id = checkpoint.checkpoint_id
            previous_key = key
            count += 1
        return count

    def _verify_holdout_grants(self) -> int:
        count = 0
        for row in self._connection.execute(
            """
            SELECT grant_id, content_hash, protocol_manifest_id,
                   split_manifest_id, checkpoint_id, receipt_sequence,
                   canonical_blob
            FROM holdout_grants ORDER BY receipt_sequence
            """
        ):
            blob = bytes(row[6])
            grant = HoldoutEvaluationGrant.from_mapping(
                _parse_json_object(blob, context="HoldoutEvaluationGrant")
            )
            if canonical_json_bytes(grant.as_dict()) != blob:
                raise LedgerVerificationError(
                    "holdout grant BLOB is not exact canonical JSON"
                )
            expected = (
                grant.grant_id,
                _raw_sha256(blob),
                grant.protocol_manifest_id,
                grant.split_manifest_id,
                grant.checkpoint_id,
            )
            if tuple(row[:5]) != expected:
                raise LedgerVerificationError("holdout grant columns differ from blob")
            checkpoint = self._load_checkpoint(grant.checkpoint_id)
            if grant.granted_at < checkpoint.signed_at:
                raise LedgerVerificationError("holdout grant predates checkpoint")
            checkpoint_receipt = self._connection.execute(
                "SELECT receipt_sequence FROM checkpoints WHERE checkpoint_id = ?",
                (grant.checkpoint_id,),
            ).fetchone()
            assert checkpoint_receipt is not None
            if int(checkpoint_receipt[0]) + 1 != int(row[5]):
                raise LedgerVerificationError(
                    "holdout grant was not issued immediately after its checkpoint"
                )
            protocol = self._load_record(
                LedgerRecordKind.MANIFEST,
                grant.protocol_manifest_id,
                before_sequence=int(row[5]) + 1,
            )
            split = self._load_record(
                LedgerRecordKind.MANIFEST,
                grant.split_manifest_id,
                before_sequence=int(row[5]) + 1,
            )
            assert isinstance(protocol, ImmutableManifestV3)
            assert isinstance(split, ImmutableManifestV3)
            if (
                protocol.manifest_type is not ManifestType.PROTOCOL
                or split.manifest_type is not ManifestType.SPLIT
                or split.payload["cohort_class"] != "FINAL_HOLDOUT"
                or split.payload["protocol_manifest_id"] != protocol.manifest_id
                or split.payload["holdout_policy_id"]
                != protocol.payload["holdout_policy_id"]
            ):
                raise LedgerVerificationError("holdout grant manifest binding failed")
            split_receipt = self._connection.execute(
                """
                SELECT first_receipt_sequence FROM objects
                WHERE record_kind = ? AND identity_id = ?
                """,
                (LedgerRecordKind.MANIFEST.value, split.manifest_id),
            ).fetchone()
            assert split_receipt is not None
            if int(split_receipt[0]) > checkpoint.global_sequence:
                raise LedgerVerificationError(
                    "holdout checkpoint does not cover the split manifest"
                )
            receipt = self.get_receipt(int(row[5]))
            expected_request_hash = sha256_digest(
                {
                    "approval_hash": grant.approval_hash,
                    "checkpoint_id": grant.checkpoint_id,
                    "evidence_gate_hash": grant.evidence_gate_hash,
                    "external_anchor_hash": grant.external_anchor_hash,
                    "frozen_artifact_hash": grant.frozen_artifact_hash,
                    "operation": LedgerOperation.GRANT_HOLDOUT_EVALUATION.value,
                    "protocol_manifest_id": grant.protocol_manifest_id,
                    "split_manifest_id": grant.split_manifest_id,
                }
            )
            if (
                receipt.operation is not LedgerOperation.GRANT_HOLDOUT_EVALUATION
                or receipt.identity_id != grant.grant_id
                or receipt.content_hash != _raw_sha256(blob)
                or receipt.record_hash != _raw_sha256(blob)
                or receipt.semantic_key != grant.protocol_manifest_id
                or receipt.head_type != "HOLDOUT_EVALUATION_GRANT"
                or receipt.expected_head is not None
                or receipt.new_head != grant.grant_id
                or receipt.request_hash != expected_request_hash
                or receipt.governance_payload_hash != _raw_sha256(blob)
                or receipt.receipt_ts != grant.granted_at
            ):
                raise LedgerVerificationError("holdout grant receipt is inconsistent")
            count += 1
        return count

    def _validate_verification_storage(self) -> None:
        self._validate_storage_parent(create=False)
        self._validate_storage_file(self.path, expected_mode=0o600)
        self._validate_existing_lock_permissions()
        self._validate_sidecar_permissions()

    @contextmanager
    def _verification_snapshot(self) -> Iterator[None]:
        if self._connection.in_transaction:
            raise LedgerConfigurationError(
                "verification requires a connection with no active transaction"
            )
        try:
            self._connection.execute("BEGIN")
            # BEGIN is deferred.  Establish the snapshot before yielding so every
            # later verifier reads one database state even under WAL concurrency.
            self._connection.execute("SELECT singleton FROM ledger_meta").fetchone()
            yield
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise

    @staticmethod
    def _trusted_checkpoint_input(
        trusted_checkpoint: SignedLedgerCheckpoint | Mapping[str, Any] | None,
    ) -> SignedLedgerCheckpoint | None:
        if trusted_checkpoint is None:
            return None
        return (
            trusted_checkpoint
            if isinstance(trusted_checkpoint, SignedLedgerCheckpoint)
            else SignedLedgerCheckpoint.from_mapping(trusted_checkpoint)
        )

    def _verify_snapshot(
        self,
        *,
        trusted_checkpoint: SignedLedgerCheckpoint | None,
        verifier: CheckpointVerifier | None,
    ) -> LedgerVerificationReport:
        self._validate_meta_runtime()
        self._verify_sqlite()
        receipt_count, global_root, roots_map = self._verify_receipt_chain()
        object_count = self._verify_objects()
        transition_count = self._verify_head_transitions()
        self._verify_receipt_bijections()
        checkpoint_count = self._verify_checkpoints(verifier=verifier)
        grant_count = self._verify_holdout_grants()
        trusted_id: str | None = None
        trusted_sequence: int | None = None
        if trusted_checkpoint is not None:
            if verifier is None:
                raise LedgerVerificationError(
                    "trusted external checkpoint requires its public-key verifier"
                )
            checkpoint = trusted_checkpoint
            checkpoint.verify_signature(verifier)
            if checkpoint.ledger_id != self.ledger_id:
                raise LedgerVerificationError(
                    "trusted checkpoint belongs to another ledger"
                )
            created_at = utc_datetime(
                self._read_meta()["created_at"], field="created_at"
            )
            if checkpoint.signed_at < created_at:
                raise LedgerVerificationError(
                    "trusted checkpoint predates ledger creation"
                )
            if checkpoint.global_sequence > 0:
                signed_receipt = self._connection.execute(
                    "SELECT receipt_ts FROM receipts WHERE global_sequence = ?",
                    (checkpoint.global_sequence,),
                ).fetchone()
                if signed_receipt is None:
                    raise LedgerVerificationError(
                        f"checkpoint references missing receipt sequence "
                        f"{checkpoint.global_sequence}"
                    )
                if checkpoint.signed_at < utc_datetime(
                    signed_receipt[0], field="receipt_ts"
                ):
                    raise LedgerVerificationError(
                        "trusted checkpoint predates its signed receipt prefix"
                    )
            expected_root, expected_channels = self._state_at_sequence(
                checkpoint.global_sequence
            )
            if (
                checkpoint.global_receipt_root != expected_root
                or checkpoint.channel_roots != expected_channels
            ):
                raise LedgerVerificationError(
                    "database state does not match trusted external checkpoint"
                )
            trusted_id = checkpoint.checkpoint_id
            trusted_sequence = checkpoint.global_sequence
        roots = tuple(
            LedgerChannelRoot(
                channel=channel,
                sequence=roots_map[channel][0],
                receipt_hash=roots_map[channel][1],
            )
            for channel in sorted(LedgerChannel, key=lambda item: item.value)
        )
        return LedgerVerificationReport(
            ledger_id=self.ledger_id,
            object_count=object_count,
            receipt_count=receipt_count,
            head_transition_count=transition_count,
            checkpoint_count=checkpoint_count,
            holdout_grant_count=grant_count,
            global_receipt_root=global_root,
            channel_roots=roots,
            trusted_checkpoint_id=trusted_id,
            trusted_global_sequence=trusted_sequence,
            unanchored_receipt_count=(
                receipt_count
                if trusted_sequence is None
                else receipt_count - trusted_sequence
            ),
        )

    def verify(
        self,
        *,
        trusted_checkpoint: SignedLedgerCheckpoint | Mapping[str, Any] | None = None,
        verifier: CheckpointVerifier | None = None,
    ) -> LedgerVerificationReport:
        """Verify one coherent database snapshot and any supplied trust anchor."""

        checkpoint = self._trusted_checkpoint_input(trusted_checkpoint)
        if checkpoint is not None and verifier is None:
            raise LedgerVerificationError(
                "trusted external checkpoint requires its public-key verifier"
            )
        self._validate_verification_storage()
        try:
            with self._verification_snapshot():
                report = self._verify_snapshot(
                    trusted_checkpoint=checkpoint,
                    verifier=verifier,
                )
        except LedgerError:
            raise
        except (CanonicalizationError, sqlite3.Error) as exc:
            raise LedgerVerificationError(
                "stored ledger state could not be decoded or verified"
            ) from exc
        self._validate_sidecar_permissions()
        return report

    def verify_holdout_evaluation_seal(
        self,
        grant_id: str,
        *,
        trusted_checkpoint: SignedLedgerCheckpoint | Mapping[str, Any],
        verifier: CheckpointVerifier,
    ) -> HoldoutEvaluationSealReport:
        """Verify that an externally retained checkpoint covers a grant receipt.

        The checkpoint used to authorize the grant necessarily predates the grant
        receipt.  A second, registered checkpoint must therefore be created after
        the grant and retained outside the database before rollback-resistant
        exactly-once evaluation can be claimed.
        """

        normalized_grant_id = canonical_hash(grant_id, field="grant_id")
        checkpoint = self._trusted_checkpoint_input(trusted_checkpoint)
        assert checkpoint is not None
        self._validate_verification_storage()
        try:
            with self._verification_snapshot():
                report = self._verify_snapshot(
                    trusted_checkpoint=checkpoint,
                    verifier=verifier,
                )
                row = self._connection.execute(
                    """
                    SELECT receipt_sequence, canonical_blob
                    FROM holdout_grants WHERE grant_id = ?
                    """,
                    (normalized_grant_id,),
                ).fetchone()
                if row is None:
                    raise LedgerNotFoundError(
                        f"unknown holdout evaluation grant {normalized_grant_id}"
                    )
                grant_receipt_sequence = int(row[0])
                grant = HoldoutEvaluationGrant.from_mapping(
                    _parse_json_object(bytes(row[1]), context="HoldoutEvaluationGrant")
                )
                if checkpoint.global_sequence < grant_receipt_sequence:
                    raise LedgerVerificationError(
                        "trusted checkpoint does not cover the holdout grant receipt"
                    )
                registered = self._connection.execute(
                    """
                    SELECT signed_global_sequence FROM checkpoints
                    WHERE checkpoint_id = ?
                    """,
                    (checkpoint.checkpoint_id,),
                ).fetchone()
                if (
                    registered is None
                    or int(registered[0]) != checkpoint.global_sequence
                ):
                    raise LedgerVerificationError(
                        "holdout seal requires a registered checkpoint retained externally"
                    )
                seal = HoldoutEvaluationSealReport(
                    grant_id=grant.grant_id,
                    protocol_manifest_id=grant.protocol_manifest_id,
                    split_manifest_id=grant.split_manifest_id,
                    grant_receipt_sequence=grant_receipt_sequence,
                    trusted_checkpoint_id=checkpoint.checkpoint_id,
                    trusted_global_sequence=checkpoint.global_sequence,
                    unanchored_receipt_count=report.unanchored_receipt_count,
                )
        except LedgerError:
            raise
        except (CanonicalizationError, sqlite3.Error) as exc:
            raise LedgerVerificationError(
                "stored ledger state could not be decoded or verified"
            ) from exc
        self._validate_sidecar_permissions()
        return seal

    def backup_to(
        self, destination: str | os.PathLike[str]
    ) -> LedgerVerificationReport:
        """Create a consistent private SQLite backup and verify it before return."""

        target = Path(destination).expanduser().absolute()
        if target.exists() or target.is_symlink():
            raise LedgerConflictError("backup destination already exists")
        if target.parent.is_symlink() or not target.parent.exists():
            raise LedgerSecurityError(
                "backup parent must be an existing real directory"
            )
        parent_info = target.parent.stat()
        if not stat.S_ISDIR(parent_info.st_mode):
            raise LedgerSecurityError("backup parent is not a directory")
        if hasattr(os, "getuid") and parent_info.st_uid != os.getuid():
            raise LedgerSecurityError("backup parent must be owned by this user")
        if stat.S_IMODE(parent_info.st_mode) != 0o700:
            raise LedgerSecurityError("backup parent directory must have mode 0700")
        fs_type = _filesystem_type(target.parent)
        if fs_type in _UNSAFE_FILESYSTEMS:
            raise LedgerSecurityError(
                f"backup filesystem {fs_type!r} is not certified for SQLite locking"
            )
        self._secure_create_regular_file(target, mode=0o600)
        try:
            destination_connection = sqlite3.connect(target, isolation_level=None)
            try:
                self._connection.backup(destination_connection)
            finally:
                destination_connection.close()
            self._validate_storage_file(target, expected_mode=0o600)
            fd = os.open(target, os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
            parent_fd = os.open(target.parent, os.O_RDONLY)
            try:
                os.fsync(parent_fd)
            finally:
                os.close(parent_fd)
            with V3GovernanceLedger.open_read_only(target) as backup:
                return backup.verify()
        except Exception:
            for candidate in (
                target,
                Path(f"{target}-journal"),
                Path(f"{target}-wal"),
                Path(f"{target}-shm"),
            ):
                try:
                    candidate.unlink(missing_ok=True)
                except OSError:
                    pass
            raise


__all__ = [
    "CHECKPOINT_SCHEMA_VERSION",
    "DEFAULT_MAX_OBJECT_BYTES",
    "GENESIS_HASH",
    "HOLDOUT_GRANT_SCHEMA_VERSION",
    "LEDGER_SCHEMA_VERSION",
    "LEDGER_VALIDATION_VERSION",
    "CheckpointSigner",
    "CheckpointVerifier",
    "HoldoutEvaluationGrant",
    "HoldoutEvaluationSealReport",
    "HoldoutGrantConflictError",
    "LedgerAlreadyRegisteredError",
    "LedgerChannel",
    "LedgerChannelRoot",
    "LedgerConfigurationError",
    "LedgerConflictError",
    "LedgerError",
    "LedgerIdempotencyConflictError",
    "LedgerNotFoundError",
    "LedgerOperation",
    "LedgerReceipt",
    "LedgerRecordKind",
    "LedgerSecurityError",
    "LedgerVerificationError",
    "LedgerVerificationReport",
    "LedgerWriterLockError",
    "SignedLedgerCheckpoint",
    "V3GovernanceLedger",
    "sqlite_wal_runtime_is_safe",
]
