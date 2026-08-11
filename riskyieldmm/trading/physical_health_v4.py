"""Frozen V4.3 physical-health policy and transition contracts.

This module contains identity-bearing contracts only.  It does not decide
health from caller assertions.  The projection reducer must derive every
transition from the immutable physical prefix and independently replay it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

from .canonical import (
    CANONICALIZATION_VERSION,
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
from .physical_evidence_v4 import (
    V4_MAX_REASON_CODES,
    V4_MAX_TREE_SIZE,
    PhysicalScopeManifestV4,
)
from .physical_market_data import (
    CaptureSegmentV3,
    CompletionBasis,
    CompletionState,
    MessageDispositionKind,
    ObservationKind,
    ObservationRevisionV3,
    PhysicalVintage,
    PrefixHealth,
)
from .transparency_log import rfc9162_empty_root, rfc9162_tree_hash

PHYSICAL_AUTHORITY_V4_SCHEMA_VERSION = "riskyieldmm_physical_authority_v4_3"
PHYSICAL_HEALTH_BLOCKER_LEAF_DOMAIN_V4 = "RiskYieldMMPhysicalHealthBlockerLeafV4_3"
V4_MAX_HEALTH_BLOCKERS = 4096

V4_HEALTH_POLICY_NAME = "RiskYieldMMPhysicalHealthPolicyV4_3"
V4_HEALTH_INTERVAL_SECONDS = 60
V4_PRIMARY_FRESHNESS_SECONDS = 90
V4_STATUS_FRESHNESS_SECONDS = 90
V4_MAX_CLOCK_UNCERTAINTY_MILLISECONDS = 250
V4_RECOVERY_CONSECUTIVE_COMPLETED_BARS = 2
V4_REQUIRED_STATUS_VALUE = "Trading"
V4_REQUIRED_CONTRACT_TYPE_VALUE = "LinearPerpetual"


class BlockerRecoveryModeV4(str, Enum):
    """Frozen evidence required to resolve one blocking disposition kind."""

    NEW_GENERATION_AND_AUTHORITY = "NEW_GENERATION_AND_AUTHORITY"
    FRESH_TRADING_STATUS = "FRESH_TRADING_STATUS"
    CONSECUTIVE_COMPLETED_BARS = "CONSECUTIVE_COMPLETED_BARS"
    NEW_COLLECTOR_BOOT_AND_AUTHORITY = "NEW_COLLECTOR_BOOT_AND_AUTHORITY"
    SCOPE_ROTATION_ONLY = "SCOPE_ROTATION_ONLY"


V4_HEALTH_STATE_PRECEDENCE = (
    PrefixHealth.JOURNAL_FAILURE,
    PrefixHealth.INTEGRITY_CONFLICT,
    PrefixHealth.SCHEMA_UNSUPPORTED,
    PrefixHealth.CLOCK_UNCERTAIN,
    PrefixHealth.GAP,
    PrefixHealth.DISCONNECTED,
    PrefixHealth.STATUS_BLOCKED,
    PrefixHealth.STALE,
    PrefixHealth.RECOVERING,
    PrefixHealth.BOOTSTRAPPING,
    PrefixHealth.HEALTHY,
)

_FROZEN_RECOVERY_PAIRS = (
    (
        MessageDispositionKind.PROVIDER_ERROR,
        BlockerRecoveryModeV4.NEW_GENERATION_AND_AUTHORITY,
    ),
    (
        MessageDispositionKind.EXPECTED_INSTRUMENT_STATUS_ABSENT,
        BlockerRecoveryModeV4.FRESH_TRADING_STATUS,
    ),
    (
        MessageDispositionKind.MALFORMED_PAYLOAD,
        BlockerRecoveryModeV4.NEW_GENERATION_AND_AUTHORITY,
    ),
    (
        MessageDispositionKind.UNSUPPORTED_SCHEMA,
        BlockerRecoveryModeV4.SCOPE_ROTATION_ONLY,
    ),
    (
        MessageDispositionKind.OUT_OF_SCOPE,
        BlockerRecoveryModeV4.NEW_GENERATION_AND_AUTHORITY,
    ),
    (
        MessageDispositionKind.RECEIPT_LAG_REJECTED,
        BlockerRecoveryModeV4.CONSECUTIVE_COMPLETED_BARS,
    ),
    (
        MessageDispositionKind.CLOCK_ORDERING_REJECTED,
        BlockerRecoveryModeV4.NEW_COLLECTOR_BOOT_AND_AUTHORITY,
    ),
    (
        MessageDispositionKind.CONTENT_CONFLICT,
        BlockerRecoveryModeV4.SCOPE_ROTATION_ONLY,
    ),
)


def _identity(domain: str, payload: Mapping[str, Any]) -> str:
    return sha256_digest(
        {
            "canonicalization_version": CANONICALIZATION_VERSION,
            "domain": domain,
            "payload": dict(payload),
            "schema_version": PHYSICAL_AUTHORITY_V4_SCHEMA_VERSION,
        }
    )


def _require_versions(payload: Mapping[str, Any]) -> None:
    if payload["canonicalization_version"] != CANONICALIZATION_VERSION:
        raise CanonicalizationError("unsupported canonicalization_version")
    if payload["schema_version"] != PHYSICAL_AUTHORITY_V4_SCHEMA_VERSION:
        raise CanonicalizationError(
            "unsupported physical-authority V4.3 schema_version"
        )


def _require_identity(provided: Any, expected: str, *, field: str) -> None:
    if canonical_hash(provided, field=field) != expected:
        raise CanonicalizationError(f"{field} does not match canonical content")


def _strict_bool(value: Any, *, field: str) -> bool:
    if not isinstance(value, bool):
        raise CanonicalizationError(f"{field} must be a boolean")
    return value


def _prefix_health(value: Any, *, field: str) -> PrefixHealth:
    try:
        return value if isinstance(value, PrefixHealth) else PrefixHealth(value)
    except (TypeError, ValueError) as exc:
        choices = ", ".join(item.value for item in PrefixHealth)
        raise CanonicalizationError(f"{field} must be one of: {choices}") from exc


def _physical_vintage(value: Any, *, field: str) -> PhysicalVintage:
    try:
        return value if isinstance(value, PhysicalVintage) else PhysicalVintage(value)
    except (TypeError, ValueError) as exc:
        choices = ", ".join(item.value for item in PhysicalVintage)
        raise CanonicalizationError(f"{field} must be one of: {choices}") from exc


def _optional_hash(value: Any, *, field: str) -> str | None:
    return None if value is None else canonical_hash(value, field=field)


def _optional_timestamp(value: Any, *, field: str) -> datetime | None:
    return None if value is None else utc_datetime(value, field=field)


def health_blocker_leaf_input_v4(*, ordinal: int, message_disposition_id: str) -> bytes:
    """Return one ordered unresolved-blocker RFC 9162 leaf input."""

    checked_ordinal = canonical_safe_int(
        ordinal,
        field="ordinal",
        minimum=0,
        maximum=V4_MAX_HEALTH_BLOCKERS - 1,
    )
    blocker_id = canonical_hash(message_disposition_id, field="message_disposition_id")
    return canonical_json_bytes(
        {
            "domain": PHYSICAL_HEALTH_BLOCKER_LEAF_DOMAIN_V4,
            "message_disposition_id": blocker_id,
            "ordinal": checked_ordinal,
        }
    )


def health_blocker_root_v4(
    ordered_message_disposition_ids: Sequence[str],
) -> str:
    """Commit an ordered unresolved-blocker set, including the empty set."""

    if isinstance(
        ordered_message_disposition_ids, (str, bytes, bytearray)
    ) or not isinstance(ordered_message_disposition_ids, Sequence):
        raise CanonicalizationError(
            "ordered_message_disposition_ids must be a sequence"
        )
    if len(ordered_message_disposition_ids) > V4_MAX_HEALTH_BLOCKERS:
        raise CanonicalizationError(
            f"health blocker result exceeds {V4_MAX_HEALTH_BLOCKERS} values"
        )
    checked = tuple(
        canonical_hash(value, field="message_disposition_id")
        for value in ordered_message_disposition_ids
    )
    if len(set(checked)) != len(checked):
        raise CanonicalizationError("health blocker result contains duplicate values")
    return rfc9162_tree_hash(
        tuple(
            health_blocker_leaf_input_v4(
                ordinal=ordinal, message_disposition_id=blocker_id
            )
            for ordinal, blocker_id in enumerate(checked)
        )
    ).hex()


@dataclass(frozen=True, slots=True, kw_only=True)
class HealthBlockerRecoveryRuleV4:
    """One entry in the reviewed blocker-recovery matrix."""

    disposition_kind: MessageDispositionKind
    recovery_mode: BlockerRecoveryModeV4

    def __post_init__(self) -> None:
        try:
            kind = (
                self.disposition_kind
                if isinstance(self.disposition_kind, MessageDispositionKind)
                else MessageDispositionKind(self.disposition_kind)
            )
            mode = (
                self.recovery_mode
                if isinstance(self.recovery_mode, BlockerRecoveryModeV4)
                else BlockerRecoveryModeV4(self.recovery_mode)
            )
        except (TypeError, ValueError) as exc:
            raise CanonicalizationError("unsupported health recovery rule") from exc
        object.__setattr__(self, "disposition_kind", kind)
        object.__setattr__(self, "recovery_mode", mode)

    def as_dict(self) -> dict[str, str]:
        return {
            "disposition_kind": self.disposition_kind.value,
            "recovery_mode": self.recovery_mode.value,
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> HealthBlockerRecoveryRuleV4:
        require_exact_keys(
            payload,
            expected={"disposition_kind", "recovery_mode"},
            context="HealthBlockerRecoveryRuleV4",
        )
        return cls(
            disposition_kind=payload["disposition_kind"],
            recovery_mode=payload["recovery_mode"],
        )


V4_BLOCKER_RECOVERY_RULES = tuple(
    HealthBlockerRecoveryRuleV4(disposition_kind=kind, recovery_mode=mode)
    for kind, mode in _FROZEN_RECOVERY_PAIRS
)


@dataclass(frozen=True, slots=True, kw_only=True)
class PhysicalHealthPolicyV4:
    """Reviewed, self-hashed V4.3 physical-health reducer policy."""

    policy_name: str = V4_HEALTH_POLICY_NAME
    interval_seconds: int = V4_HEALTH_INTERVAL_SECONDS
    primary_freshness_seconds: int = V4_PRIMARY_FRESHNESS_SECONDS
    status_freshness_seconds: int = V4_STATUS_FRESHNESS_SECONDS
    max_clock_uncertainty_milliseconds: int = V4_MAX_CLOCK_UNCERTAINTY_MILLISECONDS
    recovery_consecutive_completed_bars: int = V4_RECOVERY_CONSECUTIVE_COMPLETED_BARS
    required_vintage: PhysicalVintage = PhysicalVintage.PROSPECTIVE_LIVE
    bound_subscription_ack_required: bool = True
    required_status_value: str = V4_REQUIRED_STATUS_VALUE
    required_contract_type_value: str = V4_REQUIRED_CONTRACT_TYPE_VALUE
    state_precedence: tuple[PrefixHealth, ...] = V4_HEALTH_STATE_PRECEDENCE
    blocker_recovery_rules: tuple[HealthBlockerRecoveryRuleV4, ...] = (
        V4_BLOCKER_RECOVERY_RULES
    )

    def __post_init__(self) -> None:
        policy_name = canonical_identifier(self.policy_name, field="policy_name")
        if policy_name != V4_HEALTH_POLICY_NAME:
            raise CanonicalizationError("unsupported V4.3 health policy name")
        object.__setattr__(self, "policy_name", policy_name)
        fixed_integers = {
            "interval_seconds": V4_HEALTH_INTERVAL_SECONDS,
            "primary_freshness_seconds": V4_PRIMARY_FRESHNESS_SECONDS,
            "status_freshness_seconds": V4_STATUS_FRESHNESS_SECONDS,
            "max_clock_uncertainty_milliseconds": (
                V4_MAX_CLOCK_UNCERTAINTY_MILLISECONDS
            ),
            "recovery_consecutive_completed_bars": (
                V4_RECOVERY_CONSECUTIVE_COMPLETED_BARS
            ),
        }
        for field_name, required in fixed_integers.items():
            value = canonical_safe_int(
                getattr(self, field_name),
                field=field_name,
                minimum=required,
                maximum=required,
            )
            object.__setattr__(self, field_name, value)
        vintage = _physical_vintage(self.required_vintage, field="required_vintage")
        if vintage is not PhysicalVintage.PROSPECTIVE_LIVE:
            raise CanonicalizationError(
                "V4.3 health authority requires prospective-live evidence"
            )
        object.__setattr__(self, "required_vintage", vintage)
        ack_required = _strict_bool(
            self.bound_subscription_ack_required,
            field="bound_subscription_ack_required",
        )
        if not ack_required:
            raise CanonicalizationError(
                "V4.3 health authority requires a bound subscription ACK"
            )
        object.__setattr__(self, "bound_subscription_ack_required", ack_required)
        for field_name, required in (
            ("required_status_value", V4_REQUIRED_STATUS_VALUE),
            ("required_contract_type_value", V4_REQUIRED_CONTRACT_TYPE_VALUE),
        ):
            value = canonical_identifier(getattr(self, field_name), field=field_name)
            if value != required:
                raise CanonicalizationError(f"unsupported {field_name}")
            object.__setattr__(self, field_name, value)
        precedence = tuple(
            _prefix_health(value, field="state_precedence")
            for value in self.state_precedence
        )
        if precedence != V4_HEALTH_STATE_PRECEDENCE:
            raise CanonicalizationError("unsupported V4.3 health-state precedence")
        object.__setattr__(self, "state_precedence", precedence)
        rules = tuple(self.blocker_recovery_rules)
        if not all(isinstance(rule, HealthBlockerRecoveryRuleV4) for rule in rules):
            raise CanonicalizationError(
                "blocker_recovery_rules must contain health recovery rules"
            )
        if rules != V4_BLOCKER_RECOVERY_RULES:
            raise CanonicalizationError("unsupported V4.3 blocker recovery matrix")
        object.__setattr__(self, "blocker_recovery_rules", rules)

    def identity_payload(self) -> dict[str, Any]:
        return {
            "blocker_recovery_rules": [
                rule.as_dict() for rule in self.blocker_recovery_rules
            ],
            "interval_seconds": self.interval_seconds,
            "max_clock_uncertainty_milliseconds": (
                self.max_clock_uncertainty_milliseconds
            ),
            "policy_name": self.policy_name,
            "primary_freshness_seconds": self.primary_freshness_seconds,
            "recovery_consecutive_completed_bars": (
                self.recovery_consecutive_completed_bars
            ),
            "required_contract_type_value": self.required_contract_type_value,
            "required_status_value": self.required_status_value,
            "required_vintage": self.required_vintage.value,
            "state_precedence": [item.value for item in self.state_precedence],
            "status_freshness_seconds": self.status_freshness_seconds,
            "bound_subscription_ack_required": self.bound_subscription_ack_required,
        }

    @property
    def physical_health_policy_id(self) -> str:
        return _identity("PhysicalHealthPolicyV4", self.identity_payload())

    def as_dict(self) -> dict[str, Any]:
        return {
            "canonicalization_version": CANONICALIZATION_VERSION,
            **self.identity_payload(),
            "physical_health_policy_id": self.physical_health_policy_id,
            "schema_version": PHYSICAL_AUTHORITY_V4_SCHEMA_VERSION,
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> PhysicalHealthPolicyV4:
        expected = set(cls.__dataclass_fields__) | {
            "canonicalization_version",
            "physical_health_policy_id",
            "schema_version",
        }
        require_exact_keys(payload, expected=expected, context="PhysicalHealthPolicyV4")
        _require_versions(payload)
        raw_precedence = payload["state_precedence"]
        raw_rules = payload["blocker_recovery_rules"]
        if not isinstance(raw_precedence, list):
            raise CanonicalizationError("state_precedence must be a JSON array")
        if not isinstance(raw_rules, list):
            raise CanonicalizationError("blocker_recovery_rules must be a JSON array")
        item = cls(
            policy_name=payload["policy_name"],
            interval_seconds=payload["interval_seconds"],
            primary_freshness_seconds=payload["primary_freshness_seconds"],
            status_freshness_seconds=payload["status_freshness_seconds"],
            max_clock_uncertainty_milliseconds=payload[
                "max_clock_uncertainty_milliseconds"
            ],
            recovery_consecutive_completed_bars=payload[
                "recovery_consecutive_completed_bars"
            ],
            required_vintage=payload["required_vintage"],
            bound_subscription_ack_required=payload["bound_subscription_ack_required"],
            required_status_value=payload["required_status_value"],
            required_contract_type_value=payload["required_contract_type_value"],
            state_precedence=tuple(raw_precedence),
            blocker_recovery_rules=tuple(
                HealthBlockerRecoveryRuleV4.from_mapping(rule) for rule in raw_rules
            ),
        )
        _require_identity(
            payload["physical_health_policy_id"],
            item.physical_health_policy_id,
            field="physical_health_policy_id",
        )
        return item


REVIEWED_PHYSICAL_HEALTH_POLICY_V4 = PhysicalHealthPolicyV4()
REVIEWED_PHYSICAL_HEALTH_POLICY_ID_V4 = (
    REVIEWED_PHYSICAL_HEALTH_POLICY_V4.physical_health_policy_id
)


@dataclass(frozen=True, slots=True, kw_only=True)
class HealthEvidenceItemV4:
    """One causally visible classifier outcome supplied to the pure reducer.

    This is deliberately not an identity-bearing ledger record.  The projection
    constructs it independently from typed rows and canonical replay before it
    admits a transition.
    """

    scope_message_sequence: int
    disposition_receipt_sequence: int
    message_disposition_id: str
    disposition_kind: MessageDispositionKind
    adapter_policy_id: str
    classified_at: datetime
    capture_segment: CaptureSegmentV3
    observation_revision: ObservationRevisionV3 | None = None
    observation_admission_receipt_sequence: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "scope_message_sequence",
            canonical_safe_int(
                self.scope_message_sequence,
                field="scope_message_sequence",
                minimum=1,
            ),
        )
        object.__setattr__(
            self,
            "disposition_receipt_sequence",
            canonical_safe_int(
                self.disposition_receipt_sequence,
                field="disposition_receipt_sequence",
                minimum=1,
            ),
        )
        object.__setattr__(
            self,
            "message_disposition_id",
            canonical_hash(self.message_disposition_id, field="message_disposition_id"),
        )
        try:
            kind = (
                self.disposition_kind
                if isinstance(self.disposition_kind, MessageDispositionKind)
                else MessageDispositionKind(self.disposition_kind)
            )
        except (TypeError, ValueError) as exc:
            raise CanonicalizationError(
                "unsupported health evidence disposition"
            ) from exc
        object.__setattr__(self, "disposition_kind", kind)
        object.__setattr__(
            self,
            "adapter_policy_id",
            canonical_hash(self.adapter_policy_id, field="adapter_policy_id"),
        )
        object.__setattr__(
            self,
            "classified_at",
            utc_datetime(self.classified_at, field="classified_at"),
        )
        if not isinstance(self.capture_segment, CaptureSegmentV3):
            raise CanonicalizationError("health evidence requires its CaptureSegmentV3")
        if self.capture_segment.adapter_policy_id != self.adapter_policy_id:
            raise CanonicalizationError(
                "health evidence segment changes adapter policy"
            )
        revision = self.observation_revision
        admission = self.observation_admission_receipt_sequence
        if kind is MessageDispositionKind.NORMALIZED_OBSERVATION:
            if not isinstance(revision, ObservationRevisionV3) or admission is None:
                raise CanonicalizationError(
                    "normalized health evidence requires its admitted revision"
                )
            if revision.adapter_policy_id != self.adapter_policy_id:
                raise CanonicalizationError(
                    "health evidence revision changes adapter policy"
                )
            admission = canonical_safe_int(
                admission,
                field="observation_admission_receipt_sequence",
                minimum=1,
            )
        elif revision is not None or admission is not None:
            raise CanonicalizationError(
                "non-normalized health evidence cannot carry a revision"
            )
        object.__setattr__(self, "observation_admission_receipt_sequence", admission)


@dataclass(frozen=True, slots=True, kw_only=True)
class TransportAuthorityContextV4:
    """Projection-derived transport authority visible at one health cutoff.

    This is intentionally not a ledger record.  The projection must construct
    it independently from typed transport rows and canonical-record replay.
    Supplying a raw ACK disposition alone is insufficient: the context commits
    the latest attested session, its latest durable outbound intent, the exact
    ACK binding, and any terminal event visible at the cutoff.
    """

    physical_scope_manifest_id: str
    adapter_policy_id: str
    transport_subscription_policy_id: str
    transport_session_id: str
    transport_session_receipt_sequence: int
    capture_partition_id: str
    collector_boot_id: str
    connection_generation: int
    subscription_manifest_hash: str
    outbound_subscription_intent_id: str | None
    outbound_subscription_intent_receipt_sequence: int | None
    subscription_ack_binding_id: str | None
    bound_message_disposition_id: str | None
    subscription_ack_binding_receipt_sequence: int | None
    transport_session_termination_id: str | None = None
    transport_session_termination_receipt_sequence: int | None = None

    def __post_init__(self) -> None:
        for field_name in (
            "physical_scope_manifest_id",
            "adapter_policy_id",
            "transport_subscription_policy_id",
            "transport_session_id",
            "capture_partition_id",
            "subscription_manifest_hash",
        ):
            object.__setattr__(
                self,
                field_name,
                canonical_hash(getattr(self, field_name), field=field_name),
            )
        object.__setattr__(
            self,
            "collector_boot_id",
            canonical_identifier(self.collector_boot_id, field="collector_boot_id"),
        )
        session_receipt = canonical_safe_int(
            self.transport_session_receipt_sequence,
            field="transport_session_receipt_sequence",
            minimum=1,
        )
        generation = canonical_safe_int(
            self.connection_generation,
            field="connection_generation",
            minimum=1,
        )
        object.__setattr__(self, "transport_session_receipt_sequence", session_receipt)
        object.__setattr__(self, "connection_generation", generation)

        intent_id = _optional_hash(
            self.outbound_subscription_intent_id,
            field="outbound_subscription_intent_id",
        )
        intent_receipt = self.outbound_subscription_intent_receipt_sequence
        if (intent_id is None) != (intent_receipt is None):
            raise CanonicalizationError(
                "transport intent identity and receipt must be supplied together"
            )
        if intent_receipt is not None:
            intent_receipt = canonical_safe_int(
                intent_receipt,
                field="outbound_subscription_intent_receipt_sequence",
                minimum=session_receipt + 1,
            )

        binding_id = _optional_hash(
            self.subscription_ack_binding_id,
            field="subscription_ack_binding_id",
        )
        bound_disposition_id = _optional_hash(
            self.bound_message_disposition_id,
            field="bound_message_disposition_id",
        )
        binding_receipt = self.subscription_ack_binding_receipt_sequence
        binding_values = (binding_id, bound_disposition_id, binding_receipt)
        if any(value is None for value in binding_values) != all(
            value is None for value in binding_values
        ):
            raise CanonicalizationError(
                "ACK binding identity, disposition, and receipt are all-or-none"
            )
        if binding_id is not None:
            if intent_receipt is None:
                raise CanonicalizationError("ACK binding requires a durable intent")
            assert binding_receipt is not None
            binding_receipt = canonical_safe_int(
                binding_receipt,
                field="subscription_ack_binding_receipt_sequence",
                minimum=intent_receipt + 1,
            )

        termination_id = _optional_hash(
            self.transport_session_termination_id,
            field="transport_session_termination_id",
        )
        termination_receipt = self.transport_session_termination_receipt_sequence
        if (termination_id is None) != (termination_receipt is None):
            raise CanonicalizationError(
                "transport termination identity and receipt must be supplied together"
            )
        if termination_receipt is not None:
            termination_receipt = canonical_safe_int(
                termination_receipt,
                field="transport_session_termination_receipt_sequence",
                minimum=session_receipt + 1,
            )

        object.__setattr__(self, "outbound_subscription_intent_id", intent_id)
        object.__setattr__(
            self,
            "outbound_subscription_intent_receipt_sequence",
            intent_receipt,
        )
        object.__setattr__(self, "subscription_ack_binding_id", binding_id)
        object.__setattr__(self, "bound_message_disposition_id", bound_disposition_id)
        object.__setattr__(
            self, "subscription_ack_binding_receipt_sequence", binding_receipt
        )
        object.__setattr__(self, "transport_session_termination_id", termination_id)
        object.__setattr__(
            self,
            "transport_session_termination_receipt_sequence",
            termination_receipt,
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class HealthReductionResultV4:
    """Non-persisted output of the deterministic health reducer."""

    health: PrefixHealth
    reason_codes: tuple[str, ...]
    unresolved_blocker_ids: tuple[str, ...]
    recovery_consecutive_completed_bars: int
    current_required_status_revision_id: str | None
    current_transport_session_id: str | None
    current_outbound_subscription_intent_id: str | None
    current_subscription_ack_binding_id: str | None
    event_time_watermark: datetime | None
    health_valid_until: datetime
    vintage: PhysicalVintage

    def __post_init__(self) -> None:
        health = _prefix_health(self.health, field="health")
        reasons = canonical_reason_codes(self.reason_codes, field="reason_codes")
        if (health is PrefixHealth.HEALTHY) != (not reasons):
            raise CanonicalizationError(
                "HEALTHY reduction requires no reasons and non-healthy requires reasons"
            )
        blockers = tuple(
            canonical_hash(value, field="unresolved_blocker_ids")
            for value in self.unresolved_blocker_ids
        )
        if len(blockers) > V4_MAX_HEALTH_BLOCKERS or len(set(blockers)) != len(
            blockers
        ):
            raise CanonicalizationError("invalid unresolved health blocker set")
        recovery = canonical_safe_int(
            self.recovery_consecutive_completed_bars,
            field="recovery_consecutive_completed_bars",
            minimum=0,
            maximum=V4_RECOVERY_CONSECUTIVE_COMPLETED_BARS,
        )
        status_id = _optional_hash(
            self.current_required_status_revision_id,
            field="current_required_status_revision_id",
        )
        session_id = _optional_hash(
            self.current_transport_session_id,
            field="current_transport_session_id",
        )
        intent_id = _optional_hash(
            self.current_outbound_subscription_intent_id,
            field="current_outbound_subscription_intent_id",
        )
        binding_id = _optional_hash(
            self.current_subscription_ack_binding_id,
            field="current_subscription_ack_binding_id",
        )
        if health is PrefixHealth.HEALTHY and (
            session_id is None or intent_id is None or binding_id is None
        ):
            raise CanonicalizationError(
                "HEALTHY reduction requires session, intent, and ACK-binding identities"
            )
        if binding_id is not None and (session_id is None or intent_id is None):
            raise CanonicalizationError(
                "ACK-binding identity requires session and intent identities"
            )
        if intent_id is not None and session_id is None:
            raise CanonicalizationError(
                "subscription-intent identity requires a transport session"
            )
        watermark = _optional_timestamp(
            self.event_time_watermark, field="event_time_watermark"
        )
        valid_until = utc_datetime(self.health_valid_until, field="health_valid_until")
        object.__setattr__(self, "health", health)
        object.__setattr__(self, "reason_codes", reasons)
        object.__setattr__(self, "unresolved_blocker_ids", blockers)
        object.__setattr__(self, "recovery_consecutive_completed_bars", recovery)
        object.__setattr__(self, "current_required_status_revision_id", status_id)
        object.__setattr__(self, "current_transport_session_id", session_id)
        object.__setattr__(self, "current_outbound_subscription_intent_id", intent_id)
        object.__setattr__(self, "current_subscription_ack_binding_id", binding_id)
        object.__setattr__(self, "event_time_watermark", watermark)
        object.__setattr__(self, "health_valid_until", valid_until)
        object.__setattr__(
            self, "vintage", _physical_vintage(self.vintage, field="vintage")
        )


_BLOCKING_KINDS_V4 = frozenset(
    rule.disposition_kind for rule in V4_BLOCKER_RECOVERY_RULES
)


def _reconnected_after(
    blocker: HealthEvidenceItemV4, recovery: HealthEvidenceItemV4
) -> bool:
    left = blocker.capture_segment
    right = recovery.capture_segment
    return left.collector_boot_id != right.collector_boot_id or (
        left.capture_partition_id == right.capture_partition_id
        and right.connection_generation > left.connection_generation
    )


def _unresolved_blockers_v4(
    evidence: Sequence[HealthEvidenceItemV4],
) -> tuple[HealthEvidenceItemV4, ...]:
    unresolved: dict[str, HealthEvidenceItemV4] = {}
    recovery_modes = {
        rule.disposition_kind: rule.recovery_mode for rule in V4_BLOCKER_RECOVERY_RULES
    }
    for item in evidence:
        if item.disposition_kind in _BLOCKING_KINDS_V4:
            unresolved[item.message_disposition_id] = item
            continue
        revision = item.observation_revision
        if (
            item.disposition_kind is not MessageDispositionKind.NORMALIZED_OBSERVATION
            or revision is None
            or revision.completion_state is not CompletionState.COMPLETE
        ):
            continue
        for blocker_id, blocker in tuple(unresolved.items()):
            if blocker.adapter_policy_id != item.adapter_policy_id:
                continue
            mode = recovery_modes[blocker.disposition_kind]
            resolved = False
            if mode is BlockerRecoveryModeV4.SCOPE_ROTATION_ONLY:
                resolved = False
            elif mode is BlockerRecoveryModeV4.FRESH_TRADING_STATUS:
                resolved = (
                    revision.observation_kind is ObservationKind.INSTRUMENT_STATUS
                )
            elif mode is BlockerRecoveryModeV4.CONSECUTIVE_COMPLETED_BARS:
                resolved = revision.observation_kind in {
                    ObservationKind.BAR,
                    ObservationKind.INSTRUMENT_STATUS,
                }
            elif mode is BlockerRecoveryModeV4.NEW_COLLECTOR_BOOT_AND_AUTHORITY:
                resolved = (
                    blocker.capture_segment.collector_boot_id
                    != item.capture_segment.collector_boot_id
                    and revision.observation_kind
                    in {
                        ObservationKind.BAR,
                        ObservationKind.INSTRUMENT_STATUS,
                    }
                )
            elif mode is BlockerRecoveryModeV4.NEW_GENERATION_AND_AUTHORITY:
                resolved = _reconnected_after(blocker, item) and (
                    revision.observation_kind
                    in {ObservationKind.BAR, ObservationKind.INSTRUMENT_STATUS}
                )
            if resolved:
                unresolved.pop(blocker_id)
    return tuple(
        unresolved[key]
        for key in sorted(
            unresolved,
            key=lambda identity: (
                unresolved[identity].scope_message_sequence,
                identity,
            ),
        )
    )


def _active_revision_items_v4(
    evidence: Sequence[HealthEvidenceItemV4],
) -> tuple[tuple[HealthEvidenceItemV4, ...], bool]:
    normalized = [item for item in evidence if item.observation_revision is not None]
    by_key: dict[str, list[HealthEvidenceItemV4]] = {}
    for item in normalized:
        assert item.observation_revision is not None
        by_key.setdefault(item.observation_revision.observation_key, []).append(item)
    active: list[HealthEvidenceItemV4] = []
    forked = False
    for values in by_key.values():
        parent_ids = {
            item.observation_revision.parent_observation_revision_id
            for item in values
            if item.observation_revision is not None
            and item.observation_revision.parent_observation_revision_id is not None
        }
        heads = [
            item
            for item in values
            if item.observation_revision is not None
            and item.observation_revision.observation_revision_id not in parent_ids
        ]
        if len(heads) != 1:
            forked = True
        else:
            active.append(heads[0])
    active.sort(
        key=lambda item: (
            utc_iso(item.observation_revision.available_at)
            if item.observation_revision is not None
            else "",
            item.observation_admission_receipt_sequence or 0,
            item.message_disposition_id,
        )
    )
    return tuple(active), forked


def reduce_physical_health_v4(
    *,
    policy: PhysicalHealthPolicyV4,
    scope: PhysicalScopeManifestV4,
    evidence: Sequence[HealthEvidenceItemV4],
    transport_authority: TransportAuthorityContextV4 | None = None,
    covered_message_count: int,
    knowledge_cutoff_ts: datetime | str,
) -> HealthReductionResultV4:
    """Reduce one exact dual-cutoff evidence prefix without external state."""

    if not isinstance(policy, PhysicalHealthPolicyV4):
        raise CanonicalizationError("policy must be PhysicalHealthPolicyV4")
    if not isinstance(scope, PhysicalScopeManifestV4):
        raise CanonicalizationError("scope must be PhysicalScopeManifestV4")
    if transport_authority is not None and not isinstance(
        transport_authority, TransportAuthorityContextV4
    ):
        raise CanonicalizationError(
            "transport_authority must be TransportAuthorityContextV4 or None"
        )
    if transport_authority is not None and (
        transport_authority.physical_scope_manifest_id
        != scope.physical_scope_manifest_id
        or transport_authority.adapter_policy_id != scope.primary_adapter_policy_id
    ):
        raise CanonicalizationError(
            "transport authority changes the health scope or primary adapter"
        )
    knowledge = utc_datetime(knowledge_cutoff_ts, field="knowledge_cutoff_ts")
    covered = canonical_safe_int(
        covered_message_count, field="covered_message_count", minimum=0
    )
    items = tuple(evidence)
    if not all(isinstance(item, HealthEvidenceItemV4) for item in items):
        raise CanonicalizationError("evidence must contain HealthEvidenceItemV4")
    if tuple(item.scope_message_sequence for item in items) != tuple(
        sorted(item.scope_message_sequence for item in items)
    ) or len({item.scope_message_sequence for item in items}) != len(items):
        raise CanonicalizationError("health evidence order is not canonical")
    if any(item.classified_at > knowledge for item in items):
        raise CanonicalizationError("health reducer received future classification")

    current_transport_session_id = (
        None
        if transport_authority is None
        else transport_authority.transport_session_id
    )
    current_outbound_subscription_intent_id = (
        None
        if transport_authority is None
        else transport_authority.outbound_subscription_intent_id
    )
    current_subscription_ack_binding_id = (
        None
        if transport_authority is None
        else transport_authority.subscription_ack_binding_id
    )

    fallback_valid_until = knowledge + timedelta(microseconds=1)
    if covered == 0:
        return HealthReductionResultV4(
            health=PrefixHealth.BOOTSTRAPPING,
            reason_codes=("EMPTY_EVIDENCE_PREFIX",),
            unresolved_blocker_ids=(),
            recovery_consecutive_completed_bars=0,
            current_required_status_revision_id=None,
            current_transport_session_id=current_transport_session_id,
            current_outbound_subscription_intent_id=(
                current_outbound_subscription_intent_id
            ),
            current_subscription_ack_binding_id=(current_subscription_ack_binding_id),
            event_time_watermark=None,
            health_valid_until=fallback_valid_until,
            vintage=PhysicalVintage.REPLAY,
        )

    reasons: set[str] = set()
    if scope.health_policy_id != policy.physical_health_policy_id:
        reasons.add("UNREVIEWED_HEALTH_POLICY")
    if len(items) != covered or tuple(
        item.scope_message_sequence for item in items
    ) != tuple(range(1, covered + 1)):
        reasons.add("INCOMPLETE_CAUSAL_CLASSIFICATION")

    primary_items = [
        item
        for item in items
        if item.adapter_policy_id == scope.primary_adapter_policy_id
    ]
    authority_policy_ids = {scope.primary_adapter_policy_id}
    if scope.required_status_adapter_policy_id is not None:
        authority_policy_ids.add(scope.required_status_adapter_policy_id)
    vintages = {
        item.capture_segment.vintage
        for item in items
        if item.adapter_policy_id in authority_policy_ids
    }
    if vintages != {policy.required_vintage}:
        reasons.add("NON_PROSPECTIVE_OR_MIXED_VINTAGE")
    derived_vintage = (
        policy.required_vintage
        if vintages == {policy.required_vintage}
        else (next(iter(vintages)) if len(vintages) == 1 else PhysicalVintage.REPLAY)
    )

    unresolved = _unresolved_blockers_v4(items)
    unresolved_ids = tuple(item.message_disposition_id for item in unresolved)
    unresolved_kinds = {item.disposition_kind for item in unresolved}
    reasons.update(
        "UNRESOLVED_" + item.value
        for item in sorted(unresolved_kinds, key=lambda x: x.value)
    )

    active, forked = _active_revision_items_v4(items)
    if forked:
        reasons.add("ACTIVE_REVISION_FORK")
    bar_items = [
        item
        for item in active
        if item.adapter_policy_id == scope.primary_adapter_policy_id
        and item.observation_revision is not None
        and item.observation_revision.observation_kind is ObservationKind.BAR
        and item.observation_revision.completion_state is CompletionState.COMPLETE
        and item.observation_revision.completion_basis
        is CompletionBasis.PROVIDER_FINAL_FLAG
    ]
    bar_items.sort(
        key=lambda item: (
            item.observation_revision.bar_close_ts,
            item.observation_revision.available_at,
            item.observation_admission_receipt_sequence or 0,
            item.observation_revision.observation_revision_id,
        )
    )
    latest_bar = bar_items[-1] if bar_items else None
    watermark = (
        None
        if latest_bar is None or latest_bar.observation_revision is None
        else latest_bar.observation_revision.bar_close_ts
    )

    status_id: str | None = None
    status_expiry: datetime | None = None
    if scope.required_status_adapter_policy_id is None:
        reasons.add("REQUIRED_STATUS_POLICY_NOT_BOUND")
    else:
        statuses = [
            item
            for item in active
            if item.adapter_policy_id == scope.required_status_adapter_policy_id
            and item.observation_revision is not None
            and item.observation_revision.observation_kind
            is ObservationKind.INSTRUMENT_STATUS
            and item.observation_revision.completion_state is CompletionState.COMPLETE
            and item.observation_revision.completion_basis
            is CompletionBasis.PROVIDER_FINAL_RECORD
        ]
        if len(statuses) != 1:
            reasons.add("REQUIRED_STATUS_MISSING_OR_AMBIGUOUS")
        else:
            status = statuses[0].observation_revision
            assert status is not None
            status_id = status.observation_revision_id
            fields = dict(zip(status.field_ids, status.field_values, strict=True))
            if fields.get("status") != policy.required_status_value:
                reasons.add("INSTRUMENT_STATUS_NOT_TRADING")
            if fields.get("contract_type") != policy.required_contract_type_value:
                reasons.add("INSTRUMENT_CONTRACT_TYPE_BLOCKED")
            if status.source_publish_ts is None or status.source_publish_ts > knowledge:
                reasons.add("INSTRUMENT_STATUS_CLOCK_INVALID")
            else:
                status_expiry = status.source_publish_ts + timedelta(
                    seconds=policy.status_freshness_seconds
                )
                if knowledge >= status_expiry:
                    reasons.add("INSTRUMENT_STATUS_STALE")

    recovery_count = 0
    bar_expiry: datetime | None = None
    if latest_bar is None or watermark is None:
        reasons.add("COMPLETED_PRIMARY_BAR_MISSING")
    else:
        bar_expiry = watermark + timedelta(seconds=policy.primary_freshness_seconds)
        if knowledge >= bar_expiry:
            reasons.add("PRIMARY_BAR_STALE")
        current_segment = latest_bar.capture_segment
        if current_segment.clock_uncertainty_milliseconds > (
            policy.max_clock_uncertainty_milliseconds
        ):
            reasons.add("CLOCK_UNCERTAINTY_EXCEEDED")
        transport_matches_segment = (
            transport_authority is not None
            and transport_authority.transport_session_id
            == current_segment.connection_id
            and transport_authority.capture_partition_id
            == current_segment.capture_partition_id
            and transport_authority.collector_boot_id
            == current_segment.collector_boot_id
            and transport_authority.connection_generation
            == current_segment.connection_generation
        )
        binding_valid = False
        binding_sequence = 0
        if not transport_matches_segment:
            reasons.add("CURRENT_TRANSPORT_SESSION_ATTESTATION_MISSING")
        elif transport_authority is not None:
            if transport_authority.transport_session_termination_id is not None:
                reasons.add("CURRENT_TRANSPORT_SESSION_TERMINATED")
            if transport_authority.outbound_subscription_intent_id is None:
                reasons.add("CURRENT_SESSION_SUBSCRIPTION_INTENT_MISSING")
            elif (
                transport_authority.subscription_manifest_hash
                != current_segment.subscription_manifest_hash
            ):
                reasons.add("CURRENT_SESSION_SUBSCRIPTION_INTENT_MANIFEST_MISMATCH")
            if (
                transport_authority.subscription_ack_binding_id is None
                or transport_authority.bound_message_disposition_id is None
                or transport_authority.subscription_ack_binding_receipt_sequence is None
            ):
                reasons.add("CURRENT_SESSION_SUBSCRIPTION_ACK_BINDING_MISSING")
            else:
                bound_acknowledgements = [
                    item
                    for item in primary_items
                    if item.message_disposition_id
                    == transport_authority.bound_message_disposition_id
                    and item.disposition_kind
                    is MessageDispositionKind.CONTROL_SUBSCRIPTION_ACK
                    and item.capture_segment.capture_partition_id
                    == current_segment.capture_partition_id
                    and item.capture_segment.collector_boot_id
                    == current_segment.collector_boot_id
                    and item.capture_segment.connection_generation
                    == current_segment.connection_generation
                    and item.capture_segment.connection_id
                    == current_segment.connection_id
                    and item.capture_segment.subscription_manifest_hash
                    == current_segment.subscription_manifest_hash
                    and item.disposition_receipt_sequence
                    < transport_authority.subscription_ack_binding_receipt_sequence
                ]
                if len(bound_acknowledgements) != 1:
                    reasons.add("CURRENT_SESSION_SUBSCRIPTION_ACK_BINDING_INVALID")
                else:
                    binding_valid = True
                    binding_sequence = (
                        transport_authority.subscription_ack_binding_receipt_sequence
                    )
        if policy.bound_subscription_ack_required and not binding_valid:
            binding_sequence = 0
        latest_blocker_sequence = max(
            (
                item.disposition_receipt_sequence
                for item in items
                if item.disposition_kind in _BLOCKING_KINDS_V4
            ),
            default=0,
        )
        termination_sequence = (
            0
            if transport_authority is None
            or transport_authority.transport_session_termination_receipt_sequence
            is None
            else transport_authority.transport_session_termination_receipt_sequence
        )
        anchor_sequence = max(
            binding_sequence, latest_blocker_sequence, termination_sequence
        )
        clean = [
            item
            for item in bar_items
            if (item.observation_admission_receipt_sequence or 0) > anchor_sequence
            and item.capture_segment.capture_partition_id
            == current_segment.capture_partition_id
            and item.capture_segment.collector_boot_id
            == current_segment.collector_boot_id
            and item.capture_segment.connection_generation
            == current_segment.connection_generation
            and item.capture_segment.connection_id == current_segment.connection_id
        ]
        suffix: list[HealthEvidenceItemV4] = []
        for item in reversed(clean):
            revision = item.observation_revision
            assert revision is not None
            if not suffix:
                suffix.append(item)
            else:
                right = suffix[-1].observation_revision
                assert right is not None
                if revision.bar_close_ts != right.bar_open_ts:
                    break
                suffix.append(item)
            if len(suffix) == policy.recovery_consecutive_completed_bars:
                break
        recovery_count = len(suffix)
        if len(bar_items) >= policy.recovery_consecutive_completed_bars:
            recent = bar_items[-policy.recovery_consecutive_completed_bars :]
            if any(
                left.observation_revision.bar_close_ts
                != right.observation_revision.bar_open_ts
                for left, right in zip(recent, recent[1:])
            ):
                reasons.add("STRICT_PRIMARY_GRID_GAP")
        if recovery_count < policy.recovery_consecutive_completed_bars:
            reasons.add("RECOVERY_STREAK_INCOMPLETE")

    if unresolved:
        if MessageDispositionKind.CONTENT_CONFLICT in unresolved_kinds or (
            unresolved_kinds
            & {
                MessageDispositionKind.MALFORMED_PAYLOAD,
                MessageDispositionKind.OUT_OF_SCOPE,
            }
        ):
            health = PrefixHealth.INTEGRITY_CONFLICT
        elif MessageDispositionKind.UNSUPPORTED_SCHEMA in unresolved_kinds:
            health = PrefixHealth.SCHEMA_UNSUPPORTED
        elif MessageDispositionKind.CLOCK_ORDERING_REJECTED in unresolved_kinds:
            health = PrefixHealth.CLOCK_UNCERTAIN
        elif MessageDispositionKind.PROVIDER_ERROR in unresolved_kinds:
            health = PrefixHealth.DISCONNECTED
        elif (
            MessageDispositionKind.EXPECTED_INSTRUMENT_STATUS_ABSENT in unresolved_kinds
        ):
            health = PrefixHealth.STATUS_BLOCKED
        else:
            health = PrefixHealth.STALE
    elif "ACTIVE_REVISION_FORK" in reasons:
        health = PrefixHealth.INTEGRITY_CONFLICT
    elif (
        "UNREVIEWED_HEALTH_POLICY" in reasons
        or "NON_PROSPECTIVE_OR_MIXED_VINTAGE" in reasons
    ):
        health = PrefixHealth.SCHEMA_UNSUPPORTED
    elif "CLOCK_UNCERTAINTY_EXCEEDED" in reasons:
        health = PrefixHealth.CLOCK_UNCERTAIN
    elif (
        "STRICT_PRIMARY_GRID_GAP" in reasons
        or "INCOMPLETE_CAUSAL_CLASSIFICATION" in reasons
    ):
        health = PrefixHealth.GAP
    elif any(
        code.startswith("CURRENT_TRANSPORT_SESSION")
        or code.startswith("CURRENT_SESSION_SUBSCRIPTION")
        for code in reasons
    ):
        health = PrefixHealth.DISCONNECTED
    elif any(
        code.startswith("INSTRUMENT_") or code.startswith("REQUIRED_STATUS")
        for code in reasons
    ):
        health = PrefixHealth.STATUS_BLOCKED
    elif "PRIMARY_BAR_STALE" in reasons:
        health = PrefixHealth.STALE
    elif latest_bar is None:
        health = PrefixHealth.BOOTSTRAPPING
    elif reasons:
        health = PrefixHealth.RECOVERING
    else:
        health = PrefixHealth.HEALTHY

    if health not in {PrefixHealth.RECOVERING, PrefixHealth.HEALTHY}:
        recovery_count = 0
    if health is PrefixHealth.HEALTHY:
        expiries = [value for value in (bar_expiry, status_expiry) if value is not None]
        if not expiries:
            raise CanonicalizationError("healthy reduction has no validity clock")
        valid_until = min(expiries)
        final_reasons: tuple[str, ...] = ()
    else:
        valid_until = fallback_valid_until
        final_reasons = canonical_reason_codes(tuple(reasons), field="reason_codes")
    return HealthReductionResultV4(
        health=health,
        reason_codes=final_reasons,
        unresolved_blocker_ids=unresolved_ids,
        recovery_consecutive_completed_bars=recovery_count,
        current_required_status_revision_id=status_id,
        current_transport_session_id=current_transport_session_id,
        current_outbound_subscription_intent_id=(
            current_outbound_subscription_intent_id
        ),
        current_subscription_ack_binding_id=current_subscription_ack_binding_id,
        event_time_watermark=watermark,
        health_valid_until=valid_until,
        vintage=derived_vintage,
    )


@dataclass(frozen=True, slots=True, kw_only=True)
class PhysicalHealthTransitionV4:
    """One deterministic health assessment over an exact evidence cutoff."""

    physical_scope_manifest_id: str
    ledger_id: str
    physical_health_policy_id: str
    evidence_cutoff_id: str
    cutoff_global_sequence: int
    cutoff_receipt_hash: str
    knowledge_cutoff_ts: datetime
    tree_size: int
    tree_root: str
    parent_physical_health_transition_id: str | None
    prior_health: PrefixHealth
    current_health: PrefixHealth
    health_reason_codes: tuple[str, ...]
    unresolved_blocker_count: int
    unresolved_blocker_root: str
    recovery_consecutive_completed_bars: int
    current_required_status_revision_id: str | None
    current_transport_session_id: str | None
    current_outbound_subscription_intent_id: str | None
    current_subscription_ack_binding_id: str | None
    event_time_watermark: datetime | None
    health_valid_until: datetime
    evaluated_at: datetime

    def __post_init__(self) -> None:
        for field_name in (
            "physical_scope_manifest_id",
            "ledger_id",
            "physical_health_policy_id",
            "evidence_cutoff_id",
            "cutoff_receipt_hash",
            "tree_root",
            "unresolved_blocker_root",
        ):
            object.__setattr__(
                self,
                field_name,
                canonical_hash(getattr(self, field_name), field=field_name),
            )
        if self.physical_health_policy_id != REVIEWED_PHYSICAL_HEALTH_POLICY_ID_V4:
            raise CanonicalizationError(
                "transition uses an unreviewed V4.3 health policy"
            )
        object.__setattr__(
            self,
            "parent_physical_health_transition_id",
            _optional_hash(
                self.parent_physical_health_transition_id,
                field="parent_physical_health_transition_id",
            ),
        )
        object.__setattr__(
            self,
            "current_required_status_revision_id",
            _optional_hash(
                self.current_required_status_revision_id,
                field="current_required_status_revision_id",
            ),
        )
        for field_name in (
            "current_transport_session_id",
            "current_outbound_subscription_intent_id",
            "current_subscription_ack_binding_id",
        ):
            object.__setattr__(
                self,
                field_name,
                _optional_hash(getattr(self, field_name), field=field_name),
            )
        if self.current_subscription_ack_binding_id is not None and (
            self.current_transport_session_id is None
            or self.current_outbound_subscription_intent_id is None
        ):
            raise CanonicalizationError(
                "ACK-binding transition identity requires session and intent"
            )
        if (
            self.current_outbound_subscription_intent_id is not None
            and self.current_transport_session_id is None
        ):
            raise CanonicalizationError(
                "subscription-intent transition identity requires a session"
            )
        sequence = canonical_safe_int(
            self.cutoff_global_sequence,
            field="cutoff_global_sequence",
            minimum=1,
        )
        size = canonical_safe_int(
            self.tree_size,
            field="tree_size",
            minimum=0,
            maximum=V4_MAX_TREE_SIZE,
        )
        blocker_count = canonical_safe_int(
            self.unresolved_blocker_count,
            field="unresolved_blocker_count",
            minimum=0,
            maximum=V4_MAX_HEALTH_BLOCKERS,
        )
        recovery_count = canonical_safe_int(
            self.recovery_consecutive_completed_bars,
            field="recovery_consecutive_completed_bars",
            minimum=0,
            maximum=V4_RECOVERY_CONSECUTIVE_COMPLETED_BARS,
        )
        object.__setattr__(self, "cutoff_global_sequence", sequence)
        object.__setattr__(self, "tree_size", size)
        object.__setattr__(self, "unresolved_blocker_count", blocker_count)
        object.__setattr__(self, "recovery_consecutive_completed_bars", recovery_count)
        prior = _prefix_health(self.prior_health, field="prior_health")
        current = _prefix_health(self.current_health, field="current_health")
        object.__setattr__(self, "prior_health", prior)
        object.__setattr__(self, "current_health", current)
        reasons = canonical_reason_codes(
            self.health_reason_codes, field="health_reason_codes"
        )
        if len(reasons) > V4_MAX_REASON_CODES:
            raise CanonicalizationError(
                f"health_reason_codes exceeds {V4_MAX_REASON_CODES} values"
            )
        if (current is PrefixHealth.HEALTHY) != (not reasons):
            raise CanonicalizationError(
                "HEALTHY transition requires no reasons and non-healthy requires reasons"
            )
        object.__setattr__(self, "health_reason_codes", reasons)
        empty_root = rfc9162_empty_root().hex()
        if (blocker_count == 0) != (self.unresolved_blocker_root == empty_root):
            raise CanonicalizationError(
                "unresolved blocker count and RFC9162 root disagree"
            )
        if size == 0:
            if self.tree_root != empty_root:
                raise CanonicalizationError(
                    "empty health prefix must use the empty root"
                )
            if current is not PrefixHealth.BOOTSTRAPPING:
                raise CanonicalizationError(
                    "empty health prefix must remain BOOTSTRAPPING"
                )
        elif self.tree_root == empty_root:
            raise CanonicalizationError("non-empty health prefix cannot use empty root")
        if self.parent_physical_health_transition_id is None and (
            prior is not PrefixHealth.BOOTSTRAPPING
        ):
            raise CanonicalizationError(
                "first health transition must start from BOOTSTRAPPING"
            )
        if current is PrefixHealth.HEALTHY:
            if blocker_count or size == 0 or self.event_time_watermark is None:
                raise CanonicalizationError(
                    "HEALTHY transition requires non-empty unblocked evidence and a watermark"
                )
            if recovery_count != V4_RECOVERY_CONSECUTIVE_COMPLETED_BARS:
                raise CanonicalizationError(
                    "HEALTHY transition requires the complete recovery streak"
                )
            if (
                self.current_transport_session_id is None
                or self.current_outbound_subscription_intent_id is None
                or self.current_subscription_ack_binding_id is None
            ):
                raise CanonicalizationError(
                    "HEALTHY transition requires session, intent, and ACK binding"
                )
        elif current is PrefixHealth.RECOVERING:
            if blocker_count:
                raise CanonicalizationError(
                    "RECOVERING transition cannot retain unresolved blockers"
                )
            if recovery_count >= V4_RECOVERY_CONSECUTIVE_COMPLETED_BARS:
                raise CanonicalizationError(
                    "complete recovery streak must transition to HEALTHY"
                )
        elif recovery_count:
            raise CanonicalizationError(
                "only RECOVERING or HEALTHY may carry a recovery streak"
            )
        knowledge = utc_datetime(self.knowledge_cutoff_ts, field="knowledge_cutoff_ts")
        watermark = _optional_timestamp(
            self.event_time_watermark, field="event_time_watermark"
        )
        evaluated = utc_datetime(self.evaluated_at, field="evaluated_at")
        valid_until = utc_datetime(self.health_valid_until, field="health_valid_until")
        if watermark is not None and watermark > knowledge:
            raise CanonicalizationError(
                "event_time_watermark cannot follow knowledge_cutoff_ts"
            )
        if evaluated < knowledge:
            raise CanonicalizationError(
                "health transition evaluated before its knowledge cutoff"
            )
        if valid_until <= evaluated:
            raise CanonicalizationError("health_valid_until must follow evaluated_at")
        if size == 0 and watermark is not None:
            raise CanonicalizationError(
                "empty health prefix cannot claim an event-time watermark"
            )
        object.__setattr__(self, "knowledge_cutoff_ts", knowledge)
        object.__setattr__(self, "event_time_watermark", watermark)
        object.__setattr__(self, "evaluated_at", evaluated)
        object.__setattr__(self, "health_valid_until", valid_until)

    def identity_payload(self) -> dict[str, Any]:
        return {
            "current_health": self.current_health.value,
            "current_required_status_revision_id": (
                self.current_required_status_revision_id
            ),
            "current_transport_session_id": self.current_transport_session_id,
            "current_outbound_subscription_intent_id": (
                self.current_outbound_subscription_intent_id
            ),
            "current_subscription_ack_binding_id": (
                self.current_subscription_ack_binding_id
            ),
            "cutoff_global_sequence": self.cutoff_global_sequence,
            "cutoff_receipt_hash": self.cutoff_receipt_hash,
            "evaluated_at": utc_iso(self.evaluated_at),
            "event_time_watermark": (
                None
                if self.event_time_watermark is None
                else utc_iso(self.event_time_watermark)
            ),
            "evidence_cutoff_id": self.evidence_cutoff_id,
            "health_reason_codes": list(self.health_reason_codes),
            "health_valid_until": utc_iso(self.health_valid_until),
            "knowledge_cutoff_ts": utc_iso(self.knowledge_cutoff_ts),
            "ledger_id": self.ledger_id,
            "parent_physical_health_transition_id": (
                self.parent_physical_health_transition_id
            ),
            "physical_health_policy_id": self.physical_health_policy_id,
            "physical_scope_manifest_id": self.physical_scope_manifest_id,
            "prior_health": self.prior_health.value,
            "recovery_consecutive_completed_bars": (
                self.recovery_consecutive_completed_bars
            ),
            "tree_root": self.tree_root,
            "tree_size": self.tree_size,
            "unresolved_blocker_count": self.unresolved_blocker_count,
            "unresolved_blocker_root": self.unresolved_blocker_root,
        }

    @property
    def physical_health_transition_id(self) -> str:
        return _identity("PhysicalHealthTransitionV4", self.identity_payload())

    def as_dict(self) -> dict[str, Any]:
        return {
            "canonicalization_version": CANONICALIZATION_VERSION,
            **self.identity_payload(),
            "physical_health_transition_id": self.physical_health_transition_id,
            "schema_version": PHYSICAL_AUTHORITY_V4_SCHEMA_VERSION,
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> PhysicalHealthTransitionV4:
        expected = set(cls.__dataclass_fields__) | {
            "canonicalization_version",
            "physical_health_transition_id",
            "schema_version",
        }
        require_exact_keys(
            payload, expected=expected, context="PhysicalHealthTransitionV4"
        )
        _require_versions(payload)
        item = cls(**{field: payload[field] for field in cls.__dataclass_fields__})
        _require_identity(
            payload["physical_health_transition_id"],
            item.physical_health_transition_id,
            field="physical_health_transition_id",
        )
        return item


def validate_health_transition_successor_v4(
    parent: PhysicalHealthTransitionV4,
    successor: PhysicalHealthTransitionV4,
) -> None:
    """Validate one same-scope, monotone transition-chain edge."""

    if not isinstance(parent, PhysicalHealthTransitionV4) or not isinstance(
        successor, PhysicalHealthTransitionV4
    ):
        raise CanonicalizationError("health transition chain requires V4 transitions")
    if successor.parent_physical_health_transition_id != (
        parent.physical_health_transition_id
    ):
        raise CanonicalizationError("health transition parent identity differs")
    for field_name in (
        "physical_scope_manifest_id",
        "ledger_id",
        "physical_health_policy_id",
    ):
        if getattr(successor, field_name) != getattr(parent, field_name):
            raise CanonicalizationError(
                f"health transition successor changes {field_name}"
            )
    if successor.prior_health is not parent.current_health:
        raise CanonicalizationError(
            "health transition prior state differs from parent current state"
        )
    if successor.cutoff_global_sequence < parent.cutoff_global_sequence:
        raise CanonicalizationError("health transition cutoff sequence regresses")
    if successor.knowledge_cutoff_ts < parent.knowledge_cutoff_ts:
        raise CanonicalizationError("health transition knowledge cutoff regresses")
    if successor.tree_size < parent.tree_size:
        raise CanonicalizationError("health transition tree size regresses")
    if successor.evaluated_at <= parent.evaluated_at:
        raise CanonicalizationError("health transition evaluation must advance")
    if successor.cutoff_global_sequence == parent.cutoff_global_sequence and (
        successor.cutoff_receipt_hash != parent.cutoff_receipt_hash
        or successor.tree_size != parent.tree_size
        or successor.tree_root != parent.tree_root
        or successor.evidence_cutoff_id != parent.evidence_cutoff_id
    ):
        raise CanonicalizationError(
            "same-cutoff health transition changes cutoff evidence"
        )
    if (
        parent.event_time_watermark is not None
        and successor.event_time_watermark is not None
        and successor.event_time_watermark < parent.event_time_watermark
    ):
        raise CanonicalizationError("health transition watermark regresses")


__all__ = [
    "BlockerRecoveryModeV4",
    "HealthBlockerRecoveryRuleV4",
    "HealthEvidenceItemV4",
    "HealthReductionResultV4",
    "PHYSICAL_AUTHORITY_V4_SCHEMA_VERSION",
    "PHYSICAL_HEALTH_BLOCKER_LEAF_DOMAIN_V4",
    "PhysicalHealthPolicyV4",
    "PhysicalHealthTransitionV4",
    "TransportAuthorityContextV4",
    "REVIEWED_PHYSICAL_HEALTH_POLICY_ID_V4",
    "REVIEWED_PHYSICAL_HEALTH_POLICY_V4",
    "V4_BLOCKER_RECOVERY_RULES",
    "V4_HEALTH_INTERVAL_SECONDS",
    "V4_HEALTH_STATE_PRECEDENCE",
    "V4_MAX_CLOCK_UNCERTAINTY_MILLISECONDS",
    "V4_MAX_HEALTH_BLOCKERS",
    "V4_PRIMARY_FRESHNESS_SECONDS",
    "V4_RECOVERY_CONSECUTIVE_COMPLETED_BARS",
    "V4_REQUIRED_CONTRACT_TYPE_VALUE",
    "V4_REQUIRED_STATUS_VALUE",
    "V4_STATUS_FRESHNESS_SECONDS",
    "health_blocker_leaf_input_v4",
    "health_blocker_root_v4",
    "reduce_physical_health_v4",
    "validate_health_transition_successor_v4",
]
