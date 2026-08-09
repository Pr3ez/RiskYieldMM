"""Frozen V4 physical-evidence contracts for a continuous RFC 9162 log.

V4 is a new validation lineage.  It maps the reviewed V3 provider-classifier
semantics and preserves referenced V3 observation identities without changing
them.  The operational V3 disposition remains immutable upstream provenance;
the V4.1 projection stores it beside the semantic V4 wrapper and real
derivation/revision records.  This module owns the scope, message, disposition,
tree-head, cutoff, and shared selector constants.  Selection contracts live in
``physical_selection_v4``. Signed anchors, migration, health reduction, the
physical gate, and live authority remain separate gates.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from .canonical import (
    CANONICALIZATION_VERSION,
    MAX_IJSON_INTEGER,
    CanonicalizationError,
    canonical_hash,
    canonical_identifier,
    canonical_json_bytes,
    canonical_reason_codes,
    canonical_safe_int,
    require_exact_keys,
    sha256_digest,
    utc_datetime,
    utc_iso,
)
from .physical_market_data import (
    CaptureSegmentV3,
    MessageDispositionKind,
    PhysicalVintage,
    PrefixHealth,
    ProviderMessageDispositionV3,
)
from .transparency_log import (
    RFC9162_SHA256,
    RFC9162Frontier,
    RFC9162StoredHash,
    rfc9162_empty_root,
)

PHYSICAL_EVIDENCE_V4_SCHEMA_VERSION = "riskyieldmm_physical_evidence_v4_1"
PHYSICAL_DISPOSITION_LEAF_DOMAIN_V4 = "RiskYieldMMPhysicalDispositionLeafV4"
PHYSICAL_RESULT_LEAF_DOMAIN_V4 = "RiskYieldMMPhysicalSelectionResultLeafV4"
V4_MAX_SUPPORTING_POLICIES = 1
V4_MAX_DISPOSITION_OUTPUTS = 1
V4_MAX_REASON_CODES = 16
V4_MAX_SELECTION_RESULTS = 256
V4_MAX_TREE_SIZE = MAX_IJSON_INTEGER
V4_CUTOFF_MAX_CANONICAL_BYTES = 16_384
V4_STORED_TILE_HEIGHT = 4
V4_LIVE_QUERY_RETENTION_SECONDS = 35 * 24 * 60 * 60


def _protocol_profile_payload() -> dict[str, Any]:
    return {
        "canonicalization_version": CANONICALIZATION_VERSION,
        "cutoff_max_canonical_bytes": V4_CUTOFF_MAX_CANONICAL_BYTES,
        "disposition_leaf_domain": PHYSICAL_DISPOSITION_LEAF_DOMAIN_V4,
        "disposition_outputs_maximum": V4_MAX_DISPOSITION_OUTPUTS,
        "domain": "RiskYieldMMPhysicalEvidenceProtocolProfileV4",
        "hash_algorithm": RFC9162_SHA256,
        "live_query_retention_seconds": V4_LIVE_QUERY_RETENTION_SECONDS,
        "maximum_tree_size": V4_MAX_TREE_SIZE,
        "profile_revision": "V4.1_FRESH_GENESIS",
        "result_leaf_domain": PHYSICAL_RESULT_LEAF_DOMAIN_V4,
        "selection_results_maximum": V4_MAX_SELECTION_RESULTS,
        "status_policy_maximum": V4_MAX_SUPPORTING_POLICIES,
        "stored_tile_height": V4_STORED_TILE_HEIGHT,
    }


V4_PHYSICAL_EVIDENCE_PROTOCOL_PROFILE_ID = sha256_digest(_protocol_profile_payload())
V4_SCOPE_ORDERING_POLICY_ID = sha256_digest(
    {
        "domain": "RiskYieldMMPhysicalScopeOrderingPolicyV4",
        "order": ["capture_receipt_sequence", "envelope_ordinal"],
        "scope_sequence_origin": 1,
        "single_serialized_writer": True,
    }
)
V4_DISPOSITION_POLICY_ID = sha256_digest(
    {
        "domain": "RiskYieldMMMessageDispositionPolicyV4",
        "immutable": True,
        "outcomes": [item.value for item in MessageDispositionKind],
        "output_maximum": V4_MAX_DISPOSITION_OUTPUTS,
    }
)
V4_SELECTION_QUERY_SPEC_ID = sha256_digest(
    {
        "active_head": "no_direct_successor_satisfying_both_cutoffs",
        "anchor": "UTC_UNIX_EPOCH_FLOOR",
        "available_at_predicate": "available_at_us<=knowledge_cutoff_us",
        "bar_close_predicate": "bar_close_us<=knowledge_cutoff_us",
        "canonical_result_order": "ASCENDING",
        "completion_state": "COMPLETE",
        "continuity": "STRICT_60_SECOND_HALF_OPEN_GRID",
        "domain": "RiskYieldMMSelectionQuerySpecV4",
        "interval_seconds": 60,
        "maximum_result_count": V4_MAX_SELECTION_RESULTS,
        "observation_kind": "BAR",
        "primary_adapter_only": True,
        "receipt_field": "observation_admission_receipt_sequence",
        "receipt_predicate": (
            "observation_admission_receipt_sequence<=cutoff_global_sequence"
        ),
        "result_ordinal_origin": 0,
        "sql_baseline": "CORRELATED_NOT_EXISTS_ELIGIBLE_SUCCESSOR",
        "supported_modes": [
            "EXACT_EVENT",
            "LATEST_AVAILABLE_ASOF",
            "TRAILING_WINDOW",
        ],
        "trailing_in_process_mode": "TRAILING_COMPLETED_OBSERVATIONS",
        "tie_break": [
            "bar_close_us",
            "available_at_us",
            "observation_admission_receipt_sequence",
            "observation_revision_id_blob",
        ],
        "timeframe_id": "1m",
    }
)


class DispositionHealthSeverity(str, Enum):
    NEUTRAL = "NEUTRAL"
    HALT = "HALT"


_BLOCKING_DISPOSITIONS = frozenset(
    {
        MessageDispositionKind.PROVIDER_ERROR,
        MessageDispositionKind.EXPECTED_INSTRUMENT_STATUS_ABSENT,
        MessageDispositionKind.MALFORMED_PAYLOAD,
        MessageDispositionKind.UNSUPPORTED_SCHEMA,
        MessageDispositionKind.OUT_OF_SCOPE,
        MessageDispositionKind.RECEIPT_LAG_REJECTED,
        MessageDispositionKind.CLOCK_ORDERING_REJECTED,
        MessageDispositionKind.CONTENT_CONFLICT,
    }
)


def disposition_health_severity_v4(
    kind: MessageDispositionKind | str,
) -> DispositionHealthSeverity:
    try:
        normalized = (
            kind
            if isinstance(kind, MessageDispositionKind)
            else MessageDispositionKind(kind)
        )
    except (TypeError, ValueError) as exc:
        raise CanonicalizationError("unsupported V4 disposition kind") from exc
    if normalized in _BLOCKING_DISPOSITIONS:
        return DispositionHealthSeverity.HALT
    return DispositionHealthSeverity.NEUTRAL


def _identity(domain: str, payload: Mapping[str, Any]) -> str:
    return sha256_digest(
        {
            "canonicalization_version": CANONICALIZATION_VERSION,
            "domain": domain,
            "payload": dict(payload),
            "schema_version": PHYSICAL_EVIDENCE_V4_SCHEMA_VERSION,
        }
    )


def _optional_hash(value: Any, *, field: str) -> str | None:
    return None if value is None else canonical_hash(value, field=field)


def _optional_timestamp(value: Any, *, field: str) -> datetime | None:
    return None if value is None else utc_datetime(value, field=field)


def classifier_result_id_v4(
    *,
    adapter_policy_id: str,
    capture_segment_id: str,
    classifier_release_hash: str,
    disposition_kind: MessageDispositionKind | str,
    message_receipt_id: str,
    raw_payload_sha256: str,
    observation_derivation_id: str | None = None,
    observation_revision_id: str | None = None,
    duplicate_of_message_receipt_id: str | None = None,
    duplicate_of_disposition_id: str | None = None,
    provider_diagnostic_code: str | None = None,
    provider_diagnostic_digest: str | None = None,
) -> str:
    """Derive the semantic classifier result without an operational clock."""

    try:
        kind = (
            disposition_kind
            if isinstance(disposition_kind, MessageDispositionKind)
            else MessageDispositionKind(disposition_kind)
        )
    except (TypeError, ValueError) as exc:
        raise CanonicalizationError("unsupported V4 disposition kind") from exc
    payload = {
        "adapter_policy_id": canonical_hash(
            adapter_policy_id, field="adapter_policy_id"
        ),
        "capture_segment_id": canonical_hash(
            capture_segment_id, field="capture_segment_id"
        ),
        "classifier_release_hash": canonical_hash(
            classifier_release_hash, field="classifier_release_hash"
        ),
        "disposition_kind": kind.value,
        "domain": "RiskYieldMMClassifierResultV4",
        "duplicate_of_disposition_id": _optional_hash(
            duplicate_of_disposition_id, field="duplicate_of_disposition_id"
        ),
        "duplicate_of_message_receipt_id": _optional_hash(
            duplicate_of_message_receipt_id,
            field="duplicate_of_message_receipt_id",
        ),
        "message_receipt_id": canonical_hash(
            message_receipt_id, field="message_receipt_id"
        ),
        "observation_derivation_id": _optional_hash(
            observation_derivation_id, field="observation_derivation_id"
        ),
        "observation_revision_id": _optional_hash(
            observation_revision_id, field="observation_revision_id"
        ),
        "provider_diagnostic_code": (
            None
            if provider_diagnostic_code is None
            else canonical_identifier(
                provider_diagnostic_code, field="provider_diagnostic_code"
            )
        ),
        "provider_diagnostic_digest": _optional_hash(
            provider_diagnostic_digest, field="provider_diagnostic_digest"
        ),
        "raw_payload_sha256": canonical_hash(
            raw_payload_sha256, field="raw_payload_sha256"
        ),
    }
    return sha256_digest(payload)


def _hash_tuple(
    values: Sequence[Any], *, field: str, maximum: int, allow_empty: bool = True
) -> tuple[str, ...]:
    if isinstance(values, (str, bytes, bytearray)) or not isinstance(values, Sequence):
        raise CanonicalizationError(f"{field} must be a sequence")
    if len(values) > maximum:
        raise CanonicalizationError(f"{field} exceeds {maximum} values")
    result = tuple(canonical_hash(value, field=field) for value in values)
    if not allow_empty and not result:
        raise CanonicalizationError(f"{field} must not be empty")
    if len(set(result)) != len(result):
        raise CanonicalizationError(f"{field} contains duplicate values")
    return result


def _require_versions(payload: Mapping[str, Any]) -> None:
    if payload["canonicalization_version"] != CANONICALIZATION_VERSION:
        raise CanonicalizationError("unsupported canonicalization_version")
    if payload["schema_version"] != PHYSICAL_EVIDENCE_V4_SCHEMA_VERSION:
        raise CanonicalizationError("unsupported physical-evidence V4 schema_version")


def _require_identity(provided: Any, expected: str, *, field: str) -> None:
    if canonical_hash(provided, field=field) != expected:
        raise CanonicalizationError(f"{field} does not match canonical content")


@dataclass(frozen=True, slots=True, kw_only=True)
class PhysicalScopeManifestV4:
    """One immutable provider/instrument/policy evidence stream."""

    source_member_key: str
    instrument_mapping_id: str
    provider_id: str
    venue_id: str
    environment_id: str
    asset_id: str
    concrete_contract_id: str
    timeframe_id: str
    primary_adapter_policy_id: str
    primary_classifier_release_hash: str
    required_status_adapter_policy_id: str | None
    required_status_classifier_release_hash: str | None
    calendar_manifest_id: str
    protocol_lineage_id: str
    health_policy_id: str
    frozen_at: datetime
    protocol_profile_id: str = V4_PHYSICAL_EVIDENCE_PROTOCOL_PROFILE_ID
    scope_ordering_policy_id: str = V4_SCOPE_ORDERING_POLICY_ID
    disposition_policy_id: str = V4_DISPOSITION_POLICY_ID
    selection_query_spec_id: str = V4_SELECTION_QUERY_SPEC_ID
    hash_algorithm: str = RFC9162_SHA256

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "source_member_key",
            canonical_hash(self.source_member_key, field="source_member_key"),
        )
        for field_name in (
            "instrument_mapping_id",
            "primary_adapter_policy_id",
            "primary_classifier_release_hash",
            "calendar_manifest_id",
            "protocol_lineage_id",
            "health_policy_id",
            "protocol_profile_id",
            "scope_ordering_policy_id",
            "disposition_policy_id",
            "selection_query_spec_id",
        ):
            object.__setattr__(
                self,
                field_name,
                canonical_hash(getattr(self, field_name), field=field_name),
            )
        object.__setattr__(
            self,
            "required_status_adapter_policy_id",
            _optional_hash(
                self.required_status_adapter_policy_id,
                field="required_status_adapter_policy_id",
            ),
        )
        object.__setattr__(
            self,
            "required_status_classifier_release_hash",
            _optional_hash(
                self.required_status_classifier_release_hash,
                field="required_status_classifier_release_hash",
            ),
        )
        if (self.required_status_adapter_policy_id is None) != (
            self.required_status_classifier_release_hash is None
        ):
            raise CanonicalizationError(
                "status adapter policy and classifier release must be supplied together"
            )
        for field_name in (
            "provider_id",
            "venue_id",
            "environment_id",
            "asset_id",
            "concrete_contract_id",
            "timeframe_id",
        ):
            object.__setattr__(
                self,
                field_name,
                canonical_identifier(getattr(self, field_name), field=field_name),
            )
        if self.timeframe_id != "1m":
            raise CanonicalizationError(
                "V4.1 physical scope supports completed 1m evidence only"
            )
        object.__setattr__(
            self, "frozen_at", utc_datetime(self.frozen_at, field="frozen_at")
        )
        if self.protocol_profile_id != V4_PHYSICAL_EVIDENCE_PROTOCOL_PROFILE_ID:
            raise CanonicalizationError("scope uses an unsupported V4 protocol profile")
        if self.scope_ordering_policy_id != V4_SCOPE_ORDERING_POLICY_ID:
            raise CanonicalizationError("scope uses an unsupported ordering policy")
        if self.disposition_policy_id != V4_DISPOSITION_POLICY_ID:
            raise CanonicalizationError("scope uses an unsupported disposition policy")
        if self.selection_query_spec_id != V4_SELECTION_QUERY_SPEC_ID:
            raise CanonicalizationError("scope uses an unsupported selection query")
        object.__setattr__(
            self,
            "hash_algorithm",
            canonical_identifier(self.hash_algorithm, field="hash_algorithm"),
        )
        if self.hash_algorithm != RFC9162_SHA256:
            raise CanonicalizationError("scope hash_algorithm must be RFC9162_SHA256")

    def identity_payload(self) -> dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "calendar_manifest_id": self.calendar_manifest_id,
            "concrete_contract_id": self.concrete_contract_id,
            "disposition_policy_id": self.disposition_policy_id,
            "environment_id": self.environment_id,
            "frozen_at": utc_iso(self.frozen_at),
            "hash_algorithm": self.hash_algorithm,
            "health_policy_id": self.health_policy_id,
            "instrument_mapping_id": self.instrument_mapping_id,
            "primary_adapter_policy_id": self.primary_adapter_policy_id,
            "primary_classifier_release_hash": (self.primary_classifier_release_hash),
            "protocol_lineage_id": self.protocol_lineage_id,
            "protocol_profile_id": self.protocol_profile_id,
            "provider_id": self.provider_id,
            "required_status_adapter_policy_id": self.required_status_adapter_policy_id,
            "required_status_classifier_release_hash": (
                self.required_status_classifier_release_hash
            ),
            "scope_ordering_policy_id": self.scope_ordering_policy_id,
            "selection_query_spec_id": self.selection_query_spec_id,
            "source_member_key": self.source_member_key,
            "timeframe_id": self.timeframe_id,
            "venue_id": self.venue_id,
        }

    @property
    def physical_scope_manifest_id(self) -> str:
        return _identity("PhysicalScopeManifestV4", self.identity_payload())

    def as_dict(self) -> dict[str, Any]:
        return {
            "canonicalization_version": CANONICALIZATION_VERSION,
            **self.identity_payload(),
            "physical_scope_manifest_id": self.physical_scope_manifest_id,
            "schema_version": PHYSICAL_EVIDENCE_V4_SCHEMA_VERSION,
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> PhysicalScopeManifestV4:
        expected = set(cls.__dataclass_fields__) | {
            "canonicalization_version",
            "physical_scope_manifest_id",
            "schema_version",
        }
        require_exact_keys(
            payload, expected=expected, context="PhysicalScopeManifestV4"
        )
        _require_versions(payload)
        item = cls(**{field: payload[field] for field in cls.__dataclass_fields__})
        _require_identity(
            payload["physical_scope_manifest_id"],
            item.physical_scope_manifest_id,
            field="physical_scope_manifest_id",
        )
        return item


@dataclass(frozen=True, slots=True, kw_only=True)
class PhysicalMessageV4:
    """Typed identity for one captured provider-message occurrence."""

    physical_scope_manifest_id: str
    scope_message_sequence: int
    capture_segment_id: str
    envelope_ordinal: int
    message_receipt_id: str
    raw_payload_sha256: str
    adapter_policy_id: str
    raw_capture_receipt_sequence: int

    def __post_init__(self) -> None:
        for field_name in (
            "physical_scope_manifest_id",
            "capture_segment_id",
            "message_receipt_id",
            "raw_payload_sha256",
            "adapter_policy_id",
        ):
            object.__setattr__(
                self,
                field_name,
                canonical_hash(getattr(self, field_name), field=field_name),
            )
        object.__setattr__(
            self,
            "scope_message_sequence",
            canonical_safe_int(
                self.scope_message_sequence,
                field="scope_message_sequence",
                minimum=1,
                maximum=V4_MAX_TREE_SIZE,
            ),
        )
        object.__setattr__(
            self,
            "envelope_ordinal",
            canonical_safe_int(
                self.envelope_ordinal,
                field="envelope_ordinal",
                minimum=0,
                maximum=4095,
            ),
        )
        object.__setattr__(
            self,
            "raw_capture_receipt_sequence",
            canonical_safe_int(
                self.raw_capture_receipt_sequence,
                field="raw_capture_receipt_sequence",
                minimum=1,
            ),
        )

    def identity_payload(self) -> dict[str, Any]:
        return {
            "adapter_policy_id": self.adapter_policy_id,
            "capture_segment_id": self.capture_segment_id,
            "envelope_ordinal": self.envelope_ordinal,
            "message_receipt_id": self.message_receipt_id,
            "physical_scope_manifest_id": self.physical_scope_manifest_id,
            "raw_capture_receipt_sequence": self.raw_capture_receipt_sequence,
            "raw_payload_sha256": self.raw_payload_sha256,
            "scope_message_sequence": self.scope_message_sequence,
        }

    @property
    def physical_message_id(self) -> str:
        return _identity("PhysicalMessageV4", self.identity_payload())

    def as_dict(self) -> dict[str, Any]:
        return {
            "canonicalization_version": CANONICALIZATION_VERSION,
            **self.identity_payload(),
            "physical_message_id": self.physical_message_id,
            "schema_version": PHYSICAL_EVIDENCE_V4_SCHEMA_VERSION,
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> PhysicalMessageV4:
        expected = set(cls.__dataclass_fields__) | {
            "canonicalization_version",
            "physical_message_id",
            "schema_version",
        }
        require_exact_keys(payload, expected=expected, context="PhysicalMessageV4")
        _require_versions(payload)
        item = cls(**{field: payload[field] for field in cls.__dataclass_fields__})
        _require_identity(
            payload["physical_message_id"],
            item.physical_message_id,
            field="physical_message_id",
        )
        return item


def physical_message_from_v3(
    *,
    scope: PhysicalScopeManifestV4,
    segment: CaptureSegmentV3,
    envelope_ordinal: int,
    scope_message_sequence: int,
    raw_capture_receipt_sequence: int,
) -> PhysicalMessageV4:
    """Map one V3 envelope into a V4 scope without changing its raw identity."""

    if segment.adapter_policy_id not in {
        scope.primary_adapter_policy_id,
        scope.required_status_adapter_policy_id,
    }:
        raise CanonicalizationError("capture segment policy is outside the V4 scope")
    ordinal = canonical_safe_int(
        envelope_ordinal,
        field="envelope_ordinal",
        minimum=0,
        maximum=len(segment.envelopes) - 1,
    )
    envelope = segment.envelopes[ordinal]
    return PhysicalMessageV4(
        physical_scope_manifest_id=scope.physical_scope_manifest_id,
        scope_message_sequence=scope_message_sequence,
        capture_segment_id=segment.capture_segment_id,
        envelope_ordinal=ordinal,
        message_receipt_id=envelope.message_receipt_id,
        raw_payload_sha256=envelope.raw_payload_sha256,
        adapter_policy_id=segment.adapter_policy_id,
        raw_capture_receipt_sequence=raw_capture_receipt_sequence,
    )


@dataclass(frozen=True, slots=True, kw_only=True)
class MessageDispositionV4:
    """One immutable V3-compatible classification in the V4 total order."""

    physical_scope_manifest_id: str
    scope_message_sequence: int
    physical_message_id: str
    message_receipt_id: str
    capture_segment_id: str
    raw_payload_sha256: str
    adapter_policy_id: str
    classifier_release_hash: str
    disposition_kind: MessageDispositionKind
    health_severity: DispositionHealthSeverity
    reason_codes: tuple[str, ...]
    observation_derivation_ids: tuple[str, ...] = ()
    observation_revision_ids: tuple[str, ...] = ()
    duplicate_of_message_receipt_id: str | None = None
    duplicate_of_disposition_id: str | None = None
    provider_diagnostic_code: str | None = None
    provider_diagnostic_digest: str | None = None
    classifier_result_id: str = field(init=False)

    def __post_init__(self) -> None:
        for field_name in (
            "physical_scope_manifest_id",
            "physical_message_id",
            "message_receipt_id",
            "capture_segment_id",
            "raw_payload_sha256",
            "adapter_policy_id",
            "classifier_release_hash",
        ):
            object.__setattr__(
                self,
                field_name,
                canonical_hash(getattr(self, field_name), field=field_name),
            )
        object.__setattr__(
            self,
            "scope_message_sequence",
            canonical_safe_int(
                self.scope_message_sequence,
                field="scope_message_sequence",
                minimum=1,
                maximum=V4_MAX_TREE_SIZE,
            ),
        )
        try:
            kind = (
                self.disposition_kind
                if isinstance(self.disposition_kind, MessageDispositionKind)
                else MessageDispositionKind(self.disposition_kind)
            )
        except (TypeError, ValueError) as exc:
            raise CanonicalizationError("unsupported V4 disposition kind") from exc
        object.__setattr__(self, "disposition_kind", kind)
        try:
            severity = (
                self.health_severity
                if isinstance(self.health_severity, DispositionHealthSeverity)
                else DispositionHealthSeverity(self.health_severity)
            )
        except (TypeError, ValueError) as exc:
            raise CanonicalizationError("unsupported V4 disposition severity") from exc
        expected_severity = disposition_health_severity_v4(kind)
        if severity is not expected_severity:
            raise CanonicalizationError(
                "health_severity differs from disposition policy"
            )
        object.__setattr__(self, "health_severity", severity)
        reasons = canonical_reason_codes(self.reason_codes, field="reason_codes")
        if not reasons or len(reasons) > V4_MAX_REASON_CODES:
            raise CanonicalizationError(
                f"reason_codes must contain between 1 and {V4_MAX_REASON_CODES} values"
            )
        object.__setattr__(self, "reason_codes", reasons)
        derivations = _hash_tuple(
            self.observation_derivation_ids,
            field="observation_derivation_ids",
            maximum=V4_MAX_DISPOSITION_OUTPUTS,
        )
        revisions = _hash_tuple(
            self.observation_revision_ids,
            field="observation_revision_ids",
            maximum=V4_MAX_DISPOSITION_OUTPUTS,
        )
        object.__setattr__(self, "observation_derivation_ids", derivations)
        object.__setattr__(self, "observation_revision_ids", revisions)
        for field_name in (
            "duplicate_of_message_receipt_id",
            "duplicate_of_disposition_id",
            "provider_diagnostic_digest",
        ):
            object.__setattr__(
                self,
                field_name,
                _optional_hash(getattr(self, field_name), field=field_name),
            )
        object.__setattr__(
            self,
            "provider_diagnostic_code",
            None
            if self.provider_diagnostic_code is None
            else canonical_identifier(
                self.provider_diagnostic_code, field="provider_diagnostic_code"
            ),
        )
        outputs = (derivations, revisions)
        duplicates = (
            self.duplicate_of_message_receipt_id,
            self.duplicate_of_disposition_id,
        )
        diagnostics = (
            self.provider_diagnostic_code,
            self.provider_diagnostic_digest,
        )
        if kind is MessageDispositionKind.NORMALIZED_OBSERVATION:
            if any(len(values) != 1 for values in outputs):
                raise CanonicalizationError(
                    "normalized V4 disposition requires exactly one derivation and revision"
                )
            if any(value is not None for value in (*duplicates, *diagnostics)):
                raise CanonicalizationError(
                    "normalized V4 disposition contains foreign references"
                )
        elif kind is MessageDispositionKind.EXACT_DUPLICATE:
            if any(value is None for value in duplicates):
                raise CanonicalizationError(
                    "duplicate V4 disposition requires original references"
                )
            if any(outputs) or any(value is not None for value in diagnostics):
                raise CanonicalizationError(
                    "duplicate V4 disposition contains foreign references"
                )
            if self.duplicate_of_message_receipt_id == self.message_receipt_id:
                raise CanonicalizationError(
                    "duplicate V4 disposition cannot reference its own message"
                )
        elif kind is MessageDispositionKind.PROVIDER_ERROR:
            if any(value is None for value in diagnostics):
                raise CanonicalizationError(
                    "provider-error V4 disposition requires diagnostic evidence"
                )
            if any(outputs) or any(value is not None for value in duplicates):
                raise CanonicalizationError(
                    "provider-error V4 disposition contains foreign references"
                )
        elif any(outputs) or any(
            value is not None for value in (*duplicates, *diagnostics)
        ):
            raise CanonicalizationError(
                "non-output V4 disposition contains foreign references"
            )
        object.__setattr__(
            self,
            "classifier_result_id",
            classifier_result_id_v4(
                adapter_policy_id=self.adapter_policy_id,
                capture_segment_id=self.capture_segment_id,
                classifier_release_hash=self.classifier_release_hash,
                disposition_kind=self.disposition_kind,
                message_receipt_id=self.message_receipt_id,
                raw_payload_sha256=self.raw_payload_sha256,
                observation_derivation_id=(None if not derivations else derivations[0]),
                observation_revision_id=(None if not revisions else revisions[0]),
                duplicate_of_message_receipt_id=(self.duplicate_of_message_receipt_id),
                duplicate_of_disposition_id=self.duplicate_of_disposition_id,
                provider_diagnostic_code=self.provider_diagnostic_code,
                provider_diagnostic_digest=self.provider_diagnostic_digest,
            ),
        )

    def identity_payload(self) -> dict[str, Any]:
        return {
            "adapter_policy_id": self.adapter_policy_id,
            "capture_segment_id": self.capture_segment_id,
            "classifier_release_hash": self.classifier_release_hash,
            "classifier_result_id": self.classifier_result_id,
            "disposition_kind": self.disposition_kind.value,
            "duplicate_of_disposition_id": self.duplicate_of_disposition_id,
            "duplicate_of_message_receipt_id": self.duplicate_of_message_receipt_id,
            "health_severity": self.health_severity.value,
            "message_receipt_id": self.message_receipt_id,
            "observation_derivation_ids": list(self.observation_derivation_ids),
            "observation_revision_ids": list(self.observation_revision_ids),
            "physical_message_id": self.physical_message_id,
            "physical_scope_manifest_id": self.physical_scope_manifest_id,
            "provider_diagnostic_code": self.provider_diagnostic_code,
            "provider_diagnostic_digest": self.provider_diagnostic_digest,
            "raw_payload_sha256": self.raw_payload_sha256,
            "reason_codes": list(self.reason_codes),
            "scope_message_sequence": self.scope_message_sequence,
        }

    @property
    def message_disposition_id(self) -> str:
        return _identity("MessageDispositionV4", self.identity_payload())

    def as_dict(self) -> dict[str, Any]:
        return {
            "canonicalization_version": CANONICALIZATION_VERSION,
            **self.identity_payload(),
            "message_disposition_id": self.message_disposition_id,
            "schema_version": PHYSICAL_EVIDENCE_V4_SCHEMA_VERSION,
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> MessageDispositionV4:
        expected = set(cls.__dataclass_fields__) | {
            "canonicalization_version",
            "message_disposition_id",
            "schema_version",
        }
        require_exact_keys(payload, expected=expected, context="MessageDispositionV4")
        _require_versions(payload)
        item = cls(
            **{
                field_name: payload[field_name]
                for field_name, definition in cls.__dataclass_fields__.items()
                if definition.init
            }
        )
        _require_identity(
            payload["classifier_result_id"],
            item.classifier_result_id,
            field="classifier_result_id",
        )
        _require_identity(
            payload["message_disposition_id"],
            item.message_disposition_id,
            field="message_disposition_id",
        )
        return item


def message_disposition_from_v3(
    *,
    message: PhysicalMessageV4,
    disposition: ProviderMessageDispositionV3,
    duplicate_of_v4_disposition_id: str | None = None,
) -> MessageDispositionV4:
    """Create the exact V4 wrapper for one reviewed V3 classifier result."""

    if disposition.message_receipt_id != message.message_receipt_id:
        raise CanonicalizationError("V3 disposition changes the V4 message receipt")
    if disposition.capture_segment_id != message.capture_segment_id:
        raise CanonicalizationError("V3 disposition changes the V4 capture segment")
    if disposition.raw_payload_sha256 != message.raw_payload_sha256:
        raise CanonicalizationError("V3 disposition changes the V4 raw hash")
    if disposition.adapter_policy_id != message.adapter_policy_id:
        raise CanonicalizationError("V3 disposition changes the V4 adapter policy")
    if disposition.disposition_kind is MessageDispositionKind.EXACT_DUPLICATE:
        if duplicate_of_v4_disposition_id is None:
            raise CanonicalizationError(
                "duplicate V4 mapping requires the original V4 disposition ID"
            )
        duplicate_disposition_id = canonical_hash(
            duplicate_of_v4_disposition_id,
            field="duplicate_of_v4_disposition_id",
        )
    else:
        if duplicate_of_v4_disposition_id is not None:
            raise CanonicalizationError(
                "non-duplicate V4 mapping cannot supply a duplicate disposition"
            )
        duplicate_disposition_id = None
    derivations = (
        ()
        if disposition.observation_derivation_id is None
        else (disposition.observation_derivation_id,)
    )
    revisions = (
        ()
        if disposition.observation_revision_id is None
        else (disposition.observation_revision_id,)
    )
    reason_codes = [f"DISPOSITION_{disposition.disposition_kind.value}"]
    if disposition.provider_diagnostic_code is not None:
        reason_codes.append(f"PROVIDER_{disposition.provider_diagnostic_code}")
    # V3 binds the operational ``classified_at`` timestamp into its record ID.
    # V4 deliberately derives a semantic classifier-result identity without
    # that processing clock. The V3 record remains upstream provenance and is
    # not embedded in this semantic identity, so retrying or changing batch
    # size cannot change the disposition leaf or tree root.
    return MessageDispositionV4(
        physical_scope_manifest_id=message.physical_scope_manifest_id,
        scope_message_sequence=message.scope_message_sequence,
        physical_message_id=message.physical_message_id,
        message_receipt_id=message.message_receipt_id,
        capture_segment_id=message.capture_segment_id,
        raw_payload_sha256=message.raw_payload_sha256,
        adapter_policy_id=message.adapter_policy_id,
        classifier_release_hash=disposition.classifier_release_hash,
        disposition_kind=disposition.disposition_kind,
        health_severity=disposition_health_severity_v4(disposition.disposition_kind),
        reason_codes=tuple(reason_codes),
        observation_derivation_ids=derivations,
        observation_revision_ids=revisions,
        duplicate_of_message_receipt_id=(disposition.duplicate_of_message_receipt_id),
        duplicate_of_disposition_id=duplicate_disposition_id,
        provider_diagnostic_code=disposition.provider_diagnostic_code,
        provider_diagnostic_digest=disposition.provider_diagnostic_digest,
    )


def disposition_leaf_input_v4(disposition: MessageDispositionV4) -> bytes:
    """Return the frozen application bytes passed to RFC 9162 leaf hashing."""

    if not isinstance(disposition, MessageDispositionV4):
        raise CanonicalizationError("disposition must be MessageDispositionV4")
    return canonical_json_bytes(
        {
            "domain": PHYSICAL_DISPOSITION_LEAF_DOMAIN_V4,
            "message_disposition_id": disposition.message_disposition_id,
            "physical_scope_manifest_id": disposition.physical_scope_manifest_id,
            "scope_message_sequence": disposition.scope_message_sequence,
        }
    )


@dataclass(frozen=True, slots=True, kw_only=True)
class EvidenceTreeHeadV4:
    """Constant-size advertised head after one disposition append."""

    physical_scope_manifest_id: str
    tree_size: int
    tree_root: str
    last_scope_message_sequence: int
    last_message_disposition_id: str
    cutoff_global_sequence: int
    cutoff_receipt_hash: str
    parent_evidence_tree_head_id: str | None

    def __post_init__(self) -> None:
        for field_name in (
            "physical_scope_manifest_id",
            "tree_root",
            "last_message_disposition_id",
            "cutoff_receipt_hash",
        ):
            object.__setattr__(
                self,
                field_name,
                canonical_hash(getattr(self, field_name), field=field_name),
            )
        object.__setattr__(
            self,
            "parent_evidence_tree_head_id",
            _optional_hash(
                self.parent_evidence_tree_head_id,
                field="parent_evidence_tree_head_id",
            ),
        )
        size = canonical_safe_int(
            self.tree_size,
            field="tree_size",
            minimum=1,
            maximum=V4_MAX_TREE_SIZE,
        )
        sequence = canonical_safe_int(
            self.last_scope_message_sequence,
            field="last_scope_message_sequence",
            minimum=1,
            maximum=V4_MAX_TREE_SIZE,
        )
        if size != sequence:
            raise CanonicalizationError(
                "V4 tree_size must equal the contiguous disposition sequence"
            )
        object.__setattr__(self, "tree_size", size)
        object.__setattr__(self, "last_scope_message_sequence", sequence)
        object.__setattr__(
            self,
            "cutoff_global_sequence",
            canonical_safe_int(
                self.cutoff_global_sequence,
                field="cutoff_global_sequence",
                minimum=1,
            ),
        )
        if size == 1 and self.parent_evidence_tree_head_id is not None:
            raise CanonicalizationError("first V4 tree head cannot have a parent")
        if size > 1 and self.parent_evidence_tree_head_id is None:
            raise CanonicalizationError("non-first V4 tree head requires a parent")

    def identity_payload(self) -> dict[str, Any]:
        return {
            "cutoff_global_sequence": self.cutoff_global_sequence,
            "cutoff_receipt_hash": self.cutoff_receipt_hash,
            "last_message_disposition_id": self.last_message_disposition_id,
            "last_scope_message_sequence": self.last_scope_message_sequence,
            "parent_evidence_tree_head_id": self.parent_evidence_tree_head_id,
            "physical_scope_manifest_id": self.physical_scope_manifest_id,
            "tree_root": self.tree_root,
            "tree_size": self.tree_size,
        }

    @property
    def evidence_tree_head_id(self) -> str:
        return _identity("EvidenceTreeHeadV4", self.identity_payload())

    def as_dict(self) -> dict[str, Any]:
        return {
            "canonicalization_version": CANONICALIZATION_VERSION,
            **self.identity_payload(),
            "evidence_tree_head_id": self.evidence_tree_head_id,
            "schema_version": PHYSICAL_EVIDENCE_V4_SCHEMA_VERSION,
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> EvidenceTreeHeadV4:
        expected = set(cls.__dataclass_fields__) | {
            "canonicalization_version",
            "evidence_tree_head_id",
            "schema_version",
        }
        require_exact_keys(payload, expected=expected, context="EvidenceTreeHeadV4")
        _require_versions(payload)
        item = cls(**{field: payload[field] for field in cls.__dataclass_fields__})
        _require_identity(
            payload["evidence_tree_head_id"],
            item.evidence_tree_head_id,
            field="evidence_tree_head_id",
        )
        return item


def append_disposition_tree_head_v4(
    *,
    disposition: MessageDispositionV4,
    frontier: RFC9162Frontier,
    cutoff_global_sequence: int,
    cutoff_receipt_hash: str,
    parent: EvidenceTreeHeadV4 | None,
) -> tuple[EvidenceTreeHeadV4, RFC9162Frontier, tuple[RFC9162StoredHash, ...]]:
    """Append one deterministic disposition leaf and construct its tree head."""

    if disposition.scope_message_sequence != frontier.tree_size + 1:
        raise CanonicalizationError("disposition sequence is not the next tree leaf")
    if parent is None:
        if frontier.tree_size != 0:
            raise CanonicalizationError("non-empty frontier requires a parent head")
    else:
        if parent.physical_scope_manifest_id != disposition.physical_scope_manifest_id:
            raise CanonicalizationError("parent tree head changes physical scope")
        if parent.tree_size != frontier.tree_size:
            raise CanonicalizationError("parent tree size differs from frontier")
        if bytes.fromhex(parent.tree_root) != frontier.root_hash:
            raise CanonicalizationError("parent tree root differs from frontier")
        if cutoff_global_sequence <= parent.cutoff_global_sequence:
            raise CanonicalizationError(
                "tree-head cutoff sequence must advance beyond its parent"
            )
    next_frontier, stored = frontier.append_leaf_input(
        disposition_leaf_input_v4(disposition)
    )
    head = EvidenceTreeHeadV4(
        physical_scope_manifest_id=disposition.physical_scope_manifest_id,
        tree_size=next_frontier.tree_size,
        tree_root=next_frontier.root_hash.hex(),
        last_scope_message_sequence=disposition.scope_message_sequence,
        last_message_disposition_id=disposition.message_disposition_id,
        cutoff_global_sequence=cutoff_global_sequence,
        cutoff_receipt_hash=cutoff_receipt_hash,
        parent_evidence_tree_head_id=(
            None if parent is None else parent.evidence_tree_head_id
        ),
    )
    return head, next_frontier, stored


@dataclass(frozen=True, slots=True, kw_only=True)
class EvidenceCutoffV4:
    """Constant-size coverage and health claim at a predecessor ledger receipt."""

    physical_scope_manifest_id: str
    ledger_id: str
    evidence_tree_head_id: str | None
    tree_size: int
    tree_root: str
    cutoff_global_sequence: int
    cutoff_receipt_hash: str
    knowledge_cutoff_ts: datetime
    raw_message_count: int
    raw_message_high_water_sequence: int
    disposition_count: int
    disposition_high_water_sequence: int
    current_required_status_revision_id: str | None
    vintage: PhysicalVintage
    health: PrefixHealth
    health_reason_codes: tuple[str, ...]
    event_time_watermark: datetime | None
    health_valid_until: datetime
    parent_evidence_cutoff_id: str | None = None

    def __post_init__(self) -> None:
        for field_name in (
            "physical_scope_manifest_id",
            "ledger_id",
            "tree_root",
            "cutoff_receipt_hash",
        ):
            object.__setattr__(
                self,
                field_name,
                canonical_hash(getattr(self, field_name), field=field_name),
            )
        for field_name in (
            "evidence_tree_head_id",
            "current_required_status_revision_id",
            "parent_evidence_cutoff_id",
        ):
            object.__setattr__(
                self,
                field_name,
                _optional_hash(getattr(self, field_name), field=field_name),
            )
        size = canonical_safe_int(
            self.tree_size,
            field="tree_size",
            minimum=0,
            maximum=V4_MAX_TREE_SIZE,
        )
        object.__setattr__(self, "tree_size", size)
        for field_name in ("cutoff_global_sequence",):
            object.__setattr__(
                self,
                field_name,
                canonical_safe_int(
                    getattr(self, field_name), field=field_name, minimum=1
                ),
            )
        for field_name in (
            "raw_message_count",
            "raw_message_high_water_sequence",
            "disposition_count",
            "disposition_high_water_sequence",
        ):
            object.__setattr__(
                self,
                field_name,
                canonical_safe_int(
                    getattr(self, field_name), field=field_name, minimum=0
                ),
            )
        if size == 0:
            if self.evidence_tree_head_id is not None:
                raise CanonicalizationError(
                    "empty V4 cutoff cannot reference a tree head"
                )
            if self.tree_root != rfc9162_empty_root().hex():
                raise CanonicalizationError(
                    "empty V4 cutoff must use the RFC9162 empty root"
                )
        elif self.evidence_tree_head_id is None:
            raise CanonicalizationError(
                "non-empty V4 cutoff requires an evidence tree head"
            )
        object.__setattr__(
            self,
            "knowledge_cutoff_ts",
            utc_datetime(self.knowledge_cutoff_ts, field="knowledge_cutoff_ts"),
        )
        object.__setattr__(
            self,
            "event_time_watermark",
            _optional_timestamp(
                self.event_time_watermark, field="event_time_watermark"
            ),
        )
        if (
            self.event_time_watermark is not None
            and self.event_time_watermark > self.knowledge_cutoff_ts
        ):
            raise CanonicalizationError(
                "event_time_watermark cannot follow knowledge_cutoff_ts"
            )
        object.__setattr__(
            self,
            "health_valid_until",
            utc_datetime(self.health_valid_until, field="health_valid_until"),
        )
        if self.health_valid_until <= self.knowledge_cutoff_ts:
            raise CanonicalizationError(
                "health_valid_until must follow knowledge_cutoff_ts"
            )
        try:
            vintage = (
                self.vintage
                if isinstance(self.vintage, PhysicalVintage)
                else PhysicalVintage(self.vintage)
            )
            health = (
                self.health
                if isinstance(self.health, PrefixHealth)
                else PrefixHealth(self.health)
            )
        except (TypeError, ValueError) as exc:
            raise CanonicalizationError("unsupported V4 cutoff enum") from exc
        object.__setattr__(self, "vintage", vintage)
        object.__setattr__(self, "health", health)
        reasons = canonical_reason_codes(
            self.health_reason_codes, field="health_reason_codes"
        )
        if len(reasons) > V4_MAX_REASON_CODES:
            raise CanonicalizationError(
                f"health_reason_codes exceeds {V4_MAX_REASON_CODES} values"
            )
        object.__setattr__(self, "health_reason_codes", reasons)
        exact_coverage = (
            self.raw_message_count
            == self.raw_message_high_water_sequence
            == self.disposition_count
            == self.disposition_high_water_sequence
            == size
        )
        if health is PrefixHealth.HEALTHY:
            if size == 0:
                raise CanonicalizationError(
                    "healthy V4 cutoff requires a non-empty evidence prefix"
                )
            if self.event_time_watermark is None:
                raise CanonicalizationError(
                    "healthy V4 cutoff requires an event-time watermark"
                )
            if not exact_coverage:
                raise CanonicalizationError(
                    "healthy V4 cutoff requires exact contiguous coverage"
                )
            if reasons:
                raise CanonicalizationError(
                    "healthy V4 cutoff cannot contain health reasons"
                )
        elif not reasons:
            raise CanonicalizationError(
                "non-healthy V4 cutoff requires health reason codes"
            )
        if len(canonical_json_bytes(self.as_dict())) > V4_CUTOFF_MAX_CANONICAL_BYTES:
            raise CanonicalizationError("V4 cutoff exceeds its canonical byte budget")

    def identity_payload(self) -> dict[str, Any]:
        return {
            "current_required_status_revision_id": (
                self.current_required_status_revision_id
            ),
            "cutoff_global_sequence": self.cutoff_global_sequence,
            "cutoff_receipt_hash": self.cutoff_receipt_hash,
            "disposition_count": self.disposition_count,
            "disposition_high_water_sequence": (self.disposition_high_water_sequence),
            "event_time_watermark": (
                None
                if self.event_time_watermark is None
                else utc_iso(self.event_time_watermark)
            ),
            "evidence_tree_head_id": self.evidence_tree_head_id,
            "health": self.health.value,
            "health_reason_codes": list(self.health_reason_codes),
            "health_valid_until": utc_iso(self.health_valid_until),
            "knowledge_cutoff_ts": utc_iso(self.knowledge_cutoff_ts),
            "ledger_id": self.ledger_id,
            "parent_evidence_cutoff_id": self.parent_evidence_cutoff_id,
            "physical_scope_manifest_id": self.physical_scope_manifest_id,
            "raw_message_count": self.raw_message_count,
            "raw_message_high_water_sequence": (self.raw_message_high_water_sequence),
            "tree_root": self.tree_root,
            "tree_size": self.tree_size,
            "vintage": self.vintage.value,
        }

    @property
    def evidence_cutoff_id(self) -> str:
        return _identity("EvidenceCutoffV4", self.identity_payload())

    def as_dict(self) -> dict[str, Any]:
        return {
            "canonicalization_version": CANONICALIZATION_VERSION,
            **self.identity_payload(),
            "evidence_cutoff_id": self.evidence_cutoff_id,
            "schema_version": PHYSICAL_EVIDENCE_V4_SCHEMA_VERSION,
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> EvidenceCutoffV4:
        expected = set(cls.__dataclass_fields__) | {
            "canonicalization_version",
            "evidence_cutoff_id",
            "schema_version",
        }
        require_exact_keys(payload, expected=expected, context="EvidenceCutoffV4")
        _require_versions(payload)
        item = cls(**{field: payload[field] for field in cls.__dataclass_fields__})
        _require_identity(
            payload["evidence_cutoff_id"],
            item.evidence_cutoff_id,
            field="evidence_cutoff_id",
        )
        return item


__all__ = [
    "DispositionHealthSeverity",
    "EvidenceCutoffV4",
    "EvidenceTreeHeadV4",
    "MessageDispositionV4",
    "PHYSICAL_DISPOSITION_LEAF_DOMAIN_V4",
    "PHYSICAL_EVIDENCE_V4_SCHEMA_VERSION",
    "PHYSICAL_RESULT_LEAF_DOMAIN_V4",
    "PhysicalMessageV4",
    "PhysicalScopeManifestV4",
    "V4_CUTOFF_MAX_CANONICAL_BYTES",
    "V4_DISPOSITION_POLICY_ID",
    "V4_LIVE_QUERY_RETENTION_SECONDS",
    "V4_MAX_DISPOSITION_OUTPUTS",
    "V4_MAX_REASON_CODES",
    "V4_MAX_SELECTION_RESULTS",
    "V4_MAX_TREE_SIZE",
    "V4_PHYSICAL_EVIDENCE_PROTOCOL_PROFILE_ID",
    "V4_SCOPE_ORDERING_POLICY_ID",
    "V4_SELECTION_QUERY_SPEC_ID",
    "V4_STORED_TILE_HEIGHT",
    "append_disposition_tree_head_v4",
    "classifier_result_id_v4",
    "disposition_health_severity_v4",
    "disposition_leaf_input_v4",
    "message_disposition_from_v3",
    "physical_message_from_v3",
]
