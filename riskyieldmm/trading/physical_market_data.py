"""Prospective physical market-data evidence for the V3 trading protocol.

V3.2 proves that logical inputs are internally consistent.  This module adds
the missing physical boundary: exact provider bytes are captured first, then
normalised, revisioned, closed into a finite evidence prefix, and selected by
a deterministic as-of proof.  Historical downloads and current-revision
Parquet files can be represented, but they can never be promoted to a
prospective first-seen claim.

The first executable adapter is deliberately narrow: Bybit V5 public kline
messages.  A final bar requires the provider's explicit ``confirm=true`` flag.
REST klines are not an equivalent completion authority.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any

from .canonical import (
    CANONICALIZATION_VERSION,
    CanonicalizationError,
    canonical_decimal,
    canonical_hash,
    canonical_identifier,
    canonical_json_bytes,
    canonical_reason_codes,
    canonical_safe_int,
    require_exact_keys,
    sha256_digest,
    strict_json_loads,
    utc_datetime,
    utc_iso,
)
from .contracts import InformationDependencyV3, InformationSetV3, VintageClass
from .evidence import (
    DependencySelectionMode,
    FeatureDependencySlotV3,
    SourceBundleMemberV3,
)

PHYSICAL_MARKET_DATA_SCHEMA_VERSION = "riskyieldmm_physical_market_data_v2"
MAX_CAPTURE_ENVELOPES = 4096
# Raw bytes are base64-embedded in the default 1 MiB ledger object.  A 512 KiB
# ceiling leaves deterministic room for envelope metadata and canonical JSON.
MAX_CAPTURE_RAW_BYTES = 524_288
MAX_CAPTURE_CANONICAL_BYTES = 900_000
MAX_PREFIX_RECORDS = 16_384
MAX_PREFIX_CANONICAL_BYTES = 900_000
BYBIT_V5_KLINE_PARSER_VERSION = "bybit_v5_public_kline_v2"
BYBIT_V5_INSTRUMENT_INFO_PARSER_VERSION = "bybit_v5_instrument_info_v2"
BYBIT_V5_KLINE_CLASSIFIER_VERSION = "bybit_v5_public_message_classifier_v2"
BYBIT_V5_INSTRUMENT_INFO_CLASSIFIER_VERSION = (
    "bybit_v5_instrument_info_message_classifier_v2"
)
BYBIT_V5_FEED_HEALTH_POLICY_VERSION = "bybit_v5_feed_health_reducer_v1"
# Release allowlist digests.  They bind policies to a reviewed parser release;
# executable/package attestation remains a separate deployment control.
BYBIT_V5_KLINE_PARSER_RELEASE_HASH = sha256_digest(
    {
        "domain": "RiskYieldMMApprovedParserReleaseV1",
        "parser_version": BYBIT_V5_KLINE_PARSER_VERSION,
    }
)
BYBIT_V5_INSTRUMENT_INFO_PARSER_RELEASE_HASH = sha256_digest(
    {
        "domain": "RiskYieldMMApprovedParserReleaseV1",
        "parser_version": BYBIT_V5_INSTRUMENT_INFO_PARSER_VERSION,
    }
)
BYBIT_V5_KLINE_CLASSIFIER_RELEASE_HASH = sha256_digest(
    {
        "domain": "RiskYieldMMApprovedMessageClassifierReleaseV1",
        "classifier_version": BYBIT_V5_KLINE_CLASSIFIER_VERSION,
    }
)
BYBIT_V5_INSTRUMENT_INFO_CLASSIFIER_RELEASE_HASH = sha256_digest(
    {
        "domain": "RiskYieldMMApprovedMessageClassifierReleaseV1",
        "classifier_version": BYBIT_V5_INSTRUMENT_INFO_CLASSIFIER_VERSION,
    }
)
BYBIT_V5_FEED_HEALTH_POLICY_ID = sha256_digest(
    {
        "domain": "RiskYieldMMApprovedFeedHealthPolicyV1",
        "policy_version": BYBIT_V5_FEED_HEALTH_POLICY_VERSION,
    }
)


class ProviderAdapterKind(str, Enum):
    """Parser whose exact semantics are frozen by an adapter policy."""

    BYBIT_V5_PUBLIC_KLINE = "BYBIT_V5_PUBLIC_KLINE"
    BYBIT_V5_INSTRUMENT_INFO = "BYBIT_V5_INSTRUMENT_INFO"


class ProviderTransport(str, Enum):
    WEBSOCKET = "WEBSOCKET"
    HTTP_REST = "HTTP_REST"
    DBN_LIVE = "DBN_LIVE"
    FILE_REPLAY = "FILE_REPLAY"


class ProviderDataUse(str, Enum):
    TRADING_AUTHORITY = "TRADING_AUTHORITY"
    RECONCILIATION_ONLY = "RECONCILIATION_ONLY"
    RESEARCH_ONLY = "RESEARCH_ONLY"


class ProviderMessageTypeV3(str, Enum):
    """Exact provider transport payload type observed before decoding."""

    TEXT = "TEXT"
    BINARY = "BINARY"
    UNKNOWN = "UNKNOWN"


class MessageDispositionKind(str, Enum):
    """Exhaustive result of classifying one captured provider occurrence."""

    NORMALIZED_OBSERVATION = "NORMALIZED_OBSERVATION"
    EXACT_DUPLICATE = "EXACT_DUPLICATE"
    CONTROL_SUBSCRIPTION_ACK = "CONTROL_SUBSCRIPTION_ACK"
    CONTROL_PONG = "CONTROL_PONG"
    PROVIDER_ERROR = "PROVIDER_ERROR"
    EXPECTED_INSTRUMENT_STATUS_ABSENT = "EXPECTED_INSTRUMENT_STATUS_ABSENT"
    MALFORMED_PAYLOAD = "MALFORMED_PAYLOAD"
    UNSUPPORTED_SCHEMA = "UNSUPPORTED_SCHEMA"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"
    RECEIPT_LAG_REJECTED = "RECEIPT_LAG_REJECTED"
    CLOCK_ORDERING_REJECTED = "CLOCK_ORDERING_REJECTED"
    CONTENT_CONFLICT = "CONTENT_CONFLICT"


class PhysicalVintage(str, Enum):
    PROSPECTIVE_LIVE = "PROSPECTIVE_LIVE"
    HISTORICAL_IMPORT = "HISTORICAL_IMPORT"
    REPLAY = "REPLAY"


class DerivationKind(str, Enum):
    RAW_NORMALIZATION = "RAW_NORMALIZATION"
    TIMEFRAME_AGGREGATION = "TIMEFRAME_AGGREGATION"


class ObservationKind(str, Enum):
    BAR = "BAR"
    INSTRUMENT_STATUS = "INSTRUMENT_STATUS"
    SYSTEM_STATUS = "SYSTEM_STATUS"
    FEED_HEALTH = "FEED_HEALTH"
    HEARTBEAT = "HEARTBEAT"


class CompletionState(str, Enum):
    PROVISIONAL = "PROVISIONAL"
    COMPLETE = "COMPLETE"
    RETRACTED = "RETRACTED"


class CompletionBasis(str, Enum):
    NONE = "NONE"
    PROVIDER_FINAL_FLAG = "PROVIDER_FINAL_FLAG"
    PROVIDER_FINAL_RECORD = "PROVIDER_FINAL_RECORD"
    FROZEN_WATERMARK_POLICY = "FROZEN_WATERMARK_POLICY"
    DERIVED_ALL_CHILDREN_COMPLETE = "DERIVED_ALL_CHILDREN_COMPLETE"


class PrefixHealth(str, Enum):
    BOOTSTRAPPING = "BOOTSTRAPPING"
    HEALTHY = "HEALTHY"
    STALE = "STALE"
    DISCONNECTED = "DISCONNECTED"
    RECOVERING = "RECOVERING"
    GAP = "GAP"
    CLOCK_UNCERTAIN = "CLOCK_UNCERTAIN"
    STATUS_BLOCKED = "STATUS_BLOCKED"
    INTEGRITY_CONFLICT = "INTEGRITY_CONFLICT"
    JOURNAL_FAILURE = "JOURNAL_FAILURE"
    SCHEMA_UNSUPPORTED = "SCHEMA_UNSUPPORTED"


class SelectionStatus(str, Enum):
    SELECTED = "SELECTED"
    ABSTAIN = "ABSTAIN"


class PhysicalGateStage(str, Enum):
    DECISION_INPUT = "DECISION_INPUT"
    EXECUTION_BAR = "EXECUTION_BAR"


class PhysicalGateVerdict(str, Enum):
    PASS = "PASS"
    ABSTAIN = "ABSTAIN"


def _identity(domain: str, payload: Mapping[str, Any]) -> str:
    return sha256_digest(
        {
            "canonicalization_version": CANONICALIZATION_VERSION,
            "domain": domain,
            "payload": dict(payload),
            "schema_version": PHYSICAL_MARKET_DATA_SCHEMA_VERSION,
        }
    )


def _enum(value: Any, enum_type: type[Enum], *, field: str) -> Enum:
    try:
        return value if isinstance(value, enum_type) else enum_type(value)
    except (TypeError, ValueError) as exc:
        choices = ", ".join(item.value for item in enum_type)
        raise CanonicalizationError(f"{field} must be one of: {choices}") from exc


def _optional_hash(value: Any, *, field: str) -> str | None:
    return None if value is None else canonical_hash(value, field=field)


def _optional_identifier(value: Any, *, field: str) -> str | None:
    return None if value is None else canonical_identifier(value, field=field)


def _optional_timestamp(value: Any, *, field: str) -> datetime | None:
    return None if value is None else utc_datetime(value, field=field)


def _strict_bool(value: Any, *, field: str) -> bool:
    if not isinstance(value, bool):
        raise CanonicalizationError(f"{field} must be a boolean")
    return value


def _identifiers(
    values: Sequence[Any],
    *,
    field: str,
    allow_empty: bool = False,
    maximum: int = MAX_PREFIX_RECORDS,
) -> tuple[str, ...]:
    if isinstance(values, (str, bytes, bytearray)) or not isinstance(values, Sequence):
        raise CanonicalizationError(f"{field} must be a sequence")
    if len(values) > maximum:
        raise CanonicalizationError(f"{field} exceeds {maximum} values")
    result = tuple(canonical_identifier(item, field=field) for item in values)
    if not allow_empty and not result:
        raise CanonicalizationError(f"{field} must not be empty")
    if len(set(result)) != len(result):
        raise CanonicalizationError(f"{field} contains duplicate values")
    return result


def _hashes(
    values: Sequence[Any],
    *,
    field: str,
    allow_empty: bool = False,
    maximum: int = MAX_PREFIX_RECORDS,
) -> tuple[str, ...]:
    if isinstance(values, (str, bytes, bytearray)) or not isinstance(values, Sequence):
        raise CanonicalizationError(f"{field} must be a sequence")
    if len(values) > maximum:
        raise CanonicalizationError(f"{field} exceeds {maximum} values")
    result = tuple(canonical_hash(item, field=field) for item in values)
    if not allow_empty and not result:
        raise CanonicalizationError(f"{field} must not be empty")
    if len(set(result)) != len(result):
        raise CanonicalizationError(f"{field} contains duplicate values")
    return result


def _require_versions(payload: Mapping[str, Any]) -> None:
    if payload["canonicalization_version"] != CANONICALIZATION_VERSION:
        raise CanonicalizationError("unsupported canonicalization_version")
    if payload["schema_version"] != PHYSICAL_MARKET_DATA_SCHEMA_VERSION:
        raise CanonicalizationError("unsupported physical market-data schema_version")


def _require_digest(provided: Any, expected: str, *, field: str) -> None:
    if canonical_hash(provided, field=field) != expected:
        raise CanonicalizationError(f"{field} does not match canonical content")


def _raw_bytes(value: str, *, field: str = "raw_payload_base64") -> bytes:
    text = canonical_identifier(value, field=field, maximum=MAX_CAPTURE_RAW_BYTES * 2)
    try:
        raw = base64.b64decode(text, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise CanonicalizationError(f"{field} must be canonical base64") from exc
    if base64.b64encode(raw).decode("ascii") != text:
        raise CanonicalizationError(f"{field} must use canonical padded base64")
    return raw


def observation_value_digest(
    field_ids: Sequence[str], field_values: Sequence[str]
) -> str:
    """Return the exact ordered digest copied into V3 information dependencies."""

    fields = _identifiers(field_ids, field="field_ids")
    if isinstance(field_values, (str, bytes, bytearray)) or not isinstance(
        field_values, Sequence
    ):
        raise CanonicalizationError("field_values must be a sequence")
    values = tuple(
        canonical_identifier(value, field="field_values", maximum=1024)
        for value in field_values
    )
    if len(fields) != len(values):
        raise CanonicalizationError("field_ids and field_values lengths differ")
    return sha256_digest(
        {
            "domain": "PhysicalObservationValueV1",
            "field_ids": list(fields),
            "field_values": list(values),
        }
    )


@dataclass(frozen=True, slots=True, kw_only=True)
class ProviderAdapterPolicyV3:
    """Frozen trust boundary for one concrete provider stream and instrument."""

    policy_name: str
    provider_id: str
    venue_id: str
    environment_id: str
    adapter_kind: ProviderAdapterKind
    transport: ProviderTransport
    data_use: ProviderDataUse
    authoritative_endpoint: str
    channel_or_schema: str
    source_id: str
    asset_id: str
    concrete_contract_id: str
    provider_native_key: str
    timeframe_id: str
    base_interval_seconds: int
    source_schema_id: str
    parser_code_hash: str
    parser_version: str
    message_classifier_release_hash: str
    feed_health_policy_id: str
    availability_policy_id: str
    revision_policy_id: str
    calendar_manifest_id: str
    completion_basis: CompletionBasis
    max_receipt_lag_milliseconds: int
    stale_after_seconds: int
    max_clock_uncertainty_milliseconds: int
    requires_instrument_status: bool
    frozen_at: datetime

    def __post_init__(self) -> None:
        for field_name in (
            "policy_name",
            "provider_id",
            "venue_id",
            "environment_id",
            "authoritative_endpoint",
            "channel_or_schema",
            "source_id",
            "asset_id",
            "concrete_contract_id",
            "provider_native_key",
            "timeframe_id",
            "parser_version",
        ):
            object.__setattr__(
                self,
                field_name,
                canonical_identifier(getattr(self, field_name), field=field_name),
            )
        for field_name in (
            "source_schema_id",
            "parser_code_hash",
            "message_classifier_release_hash",
            "feed_health_policy_id",
            "availability_policy_id",
            "revision_policy_id",
            "calendar_manifest_id",
        ):
            object.__setattr__(
                self,
                field_name,
                canonical_hash(getattr(self, field_name), field=field_name),
            )
        object.__setattr__(
            self,
            "adapter_kind",
            _enum(self.adapter_kind, ProviderAdapterKind, field="adapter_kind"),
        )
        object.__setattr__(
            self,
            "transport",
            _enum(self.transport, ProviderTransport, field="transport"),
        )
        object.__setattr__(
            self, "data_use", _enum(self.data_use, ProviderDataUse, field="data_use")
        )
        object.__setattr__(
            self,
            "completion_basis",
            _enum(self.completion_basis, CompletionBasis, field="completion_basis"),
        )
        for field_name, minimum, maximum in (
            ("base_interval_seconds", 1, 86_400),
            ("max_receipt_lag_milliseconds", 0, 86_400_000),
            ("stale_after_seconds", 1, 604_800),
            ("max_clock_uncertainty_milliseconds", 0, 3_600_000),
        ):
            object.__setattr__(
                self,
                field_name,
                canonical_safe_int(
                    getattr(self, field_name),
                    field=field_name,
                    minimum=minimum,
                    maximum=maximum,
                ),
            )
        object.__setattr__(
            self,
            "requires_instrument_status",
            _strict_bool(
                self.requires_instrument_status, field="requires_instrument_status"
            ),
        )
        object.__setattr__(
            self, "frozen_at", utc_datetime(self.frozen_at, field="frozen_at")
        )
        if self.feed_health_policy_id != BYBIT_V5_FEED_HEALTH_POLICY_ID:
            raise CanonicalizationError(
                "Bybit adapter is not bound to the approved feed-health policy"
            )
        if self.adapter_kind is ProviderAdapterKind.BYBIT_V5_PUBLIC_KLINE:
            if (
                self.parser_version != BYBIT_V5_KLINE_PARSER_VERSION
                or self.parser_code_hash != BYBIT_V5_KLINE_PARSER_RELEASE_HASH
                or self.message_classifier_release_hash
                != BYBIT_V5_KLINE_CLASSIFIER_RELEASE_HASH
            ):
                raise CanonicalizationError(
                    "Bybit kline policy is not bound to approved parser/classifier releases"
                )
            if self.transport is not ProviderTransport.WEBSOCKET:
                raise CanonicalizationError(
                    "Bybit public kline authority requires WebSocket"
                )
            if self.data_use is ProviderDataUse.TRADING_AUTHORITY and (
                self.provider_id != "BYBIT"
                or self.venue_id != "BYBIT"
                or self.environment_id != "MAINNET"
                or self.authoritative_endpoint
                != "wss://stream.bybit.com/v5/public/linear"
                or self.provider_native_key not in {"BTCUSDT", "ETHUSDT"}
                or self.asset_id != self.provider_native_key.removesuffix("USDT")
                or self.concrete_contract_id
                != f"{self.provider_native_key}.LINEAR.PERP"
                or self.max_receipt_lag_milliseconds != 2_000
                or self.stale_after_seconds != 90
                or self.max_clock_uncertainty_milliseconds != 250
                or not self.requires_instrument_status
            ):
                raise CanonicalizationError(
                    "Bybit trading authority is outside the reviewed mainnet deployment allowlist"
                )
            if self.completion_basis is not CompletionBasis.PROVIDER_FINAL_FLAG:
                raise CanonicalizationError(
                    "Bybit public kline requires provider final flag"
                )
            if self.base_interval_seconds != 60 or self.timeframe_id != "1m":
                raise CanonicalizationError(
                    "initial Bybit authority supports completed 1m bars only"
                )
            expected_topic = f"kline.1.{self.provider_native_key}"
            if self.channel_or_schema != expected_topic:
                raise CanonicalizationError(
                    "Bybit kline topic differs from provider native key"
                )
        if self.adapter_kind is ProviderAdapterKind.BYBIT_V5_INSTRUMENT_INFO:
            if (
                self.parser_version != BYBIT_V5_INSTRUMENT_INFO_PARSER_VERSION
                or self.parser_code_hash != BYBIT_V5_INSTRUMENT_INFO_PARSER_RELEASE_HASH
                or self.message_classifier_release_hash
                != BYBIT_V5_INSTRUMENT_INFO_CLASSIFIER_RELEASE_HASH
            ):
                raise CanonicalizationError(
                    "Bybit instrument policy is not bound to approved parser/classifier releases"
                )
            if self.transport is not ProviderTransport.HTTP_REST:
                raise CanonicalizationError(
                    "Bybit instrument status requires HTTP_REST"
                )
            if (
                self.provider_id != "BYBIT"
                or self.venue_id != "BYBIT"
                or self.environment_id != "MAINNET"
                or self.authoritative_endpoint
                != "https://api.bybit.com/v5/market/instruments-info"
                or self.channel_or_schema
                != f"category=linear&symbol={self.provider_native_key}"
                or self.provider_native_key not in {"BTCUSDT", "ETHUSDT"}
                or self.asset_id != self.provider_native_key.removesuffix("USDT")
                or self.concrete_contract_id
                != f"{self.provider_native_key}.LINEAR.PERP"
                or self.max_receipt_lag_milliseconds != 2_000
                or self.stale_after_seconds != 90
                or self.max_clock_uncertainty_milliseconds != 250
                or self.requires_instrument_status
            ):
                raise CanonicalizationError(
                    "Bybit instrument evidence is outside the reviewed mainnet deployment allowlist"
                )
            if self.completion_basis is not CompletionBasis.PROVIDER_FINAL_RECORD:
                raise CanonicalizationError(
                    "Bybit instrument status requires final record basis"
                )
            if self.data_use is not ProviderDataUse.RECONCILIATION_ONLY:
                raise CanonicalizationError(
                    "instrument-status policy must be reconciliation-only evidence"
                )

    def identity_payload(self) -> dict[str, Any]:
        return {
            "adapter_kind": self.adapter_kind.value,
            "asset_id": self.asset_id,
            "authoritative_endpoint": self.authoritative_endpoint,
            "availability_policy_id": self.availability_policy_id,
            "base_interval_seconds": self.base_interval_seconds,
            "calendar_manifest_id": self.calendar_manifest_id,
            "channel_or_schema": self.channel_or_schema,
            "completion_basis": self.completion_basis.value,
            "concrete_contract_id": self.concrete_contract_id,
            "data_use": self.data_use.value,
            "environment_id": self.environment_id,
            "frozen_at": utc_iso(self.frozen_at),
            "max_clock_uncertainty_milliseconds": self.max_clock_uncertainty_milliseconds,
            "max_receipt_lag_milliseconds": self.max_receipt_lag_milliseconds,
            "message_classifier_release_hash": self.message_classifier_release_hash,
            "parser_code_hash": self.parser_code_hash,
            "parser_version": self.parser_version,
            "policy_name": self.policy_name,
            "provider_id": self.provider_id,
            "provider_native_key": self.provider_native_key,
            "requires_instrument_status": self.requires_instrument_status,
            "revision_policy_id": self.revision_policy_id,
            "feed_health_policy_id": self.feed_health_policy_id,
            "source_id": self.source_id,
            "source_schema_id": self.source_schema_id,
            "stale_after_seconds": self.stale_after_seconds,
            "timeframe_id": self.timeframe_id,
            "transport": self.transport.value,
            "venue_id": self.venue_id,
        }

    @property
    def adapter_policy_id(self) -> str:
        return _identity("ProviderAdapterPolicyV3", self.identity_payload())

    def as_dict(self) -> dict[str, Any]:
        return {
            "adapter_policy_id": self.adapter_policy_id,
            "canonicalization_version": CANONICALIZATION_VERSION,
            **self.identity_payload(),
            "schema_version": PHYSICAL_MARKET_DATA_SCHEMA_VERSION,
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> ProviderAdapterPolicyV3:
        expected = set(cls.__dataclass_fields__) | {
            "adapter_policy_id",
            "canonicalization_version",
            "schema_version",
        }
        require_exact_keys(
            payload, expected=expected, context="ProviderAdapterPolicyV3"
        )
        _require_versions(payload)
        item = cls(**{name: payload[name] for name in cls.__dataclass_fields__})
        _require_digest(
            payload["adapter_policy_id"],
            item.adapter_policy_id,
            field="adapter_policy_id",
        )
        return item


@dataclass(frozen=True, slots=True, kw_only=True)
class ProviderMessageEnvelopeV3:
    """One arrival occurrence; identical payload deliveries remain distinct."""

    collector_sequence: int
    collector_received_wall_ts: datetime
    collector_received_monotonic_ns: int
    message_type: ProviderMessageTypeV3
    raw_payload_base64: str
    raw_payload_sha256: str
    provider_generated_ts: datetime | None = None
    provider_event_ts: datetime | None = None
    provider_sequence: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "collector_sequence",
            canonical_safe_int(
                self.collector_sequence, field="collector_sequence", minimum=1
            ),
        )
        object.__setattr__(
            self,
            "collector_received_monotonic_ns",
            canonical_safe_int(
                self.collector_received_monotonic_ns,
                field="collector_received_monotonic_ns",
                minimum=0,
            ),
        )
        object.__setattr__(
            self,
            "collector_received_wall_ts",
            utc_datetime(
                self.collector_received_wall_ts, field="collector_received_wall_ts"
            ),
        )
        object.__setattr__(
            self,
            "message_type",
            _enum(
                self.message_type,
                ProviderMessageTypeV3,
                field="message_type",
            ),
        )
        raw = _raw_bytes(self.raw_payload_base64)
        object.__setattr__(
            self,
            "raw_payload_sha256",
            canonical_hash(self.raw_payload_sha256, field="raw_payload_sha256"),
        )
        if (
            sha256_digest({"raw_payload_base64": self.raw_payload_base64})
            == self.raw_payload_sha256
        ):
            raise CanonicalizationError(
                "raw_payload_sha256 must hash decoded raw bytes, not its wrapper"
            )
        if hashlib.sha256(raw).hexdigest() != self.raw_payload_sha256:
            raise CanonicalizationError(
                "raw_payload_sha256 differs from decoded raw bytes"
            )
        object.__setattr__(
            self,
            "provider_generated_ts",
            _optional_timestamp(
                self.provider_generated_ts, field="provider_generated_ts"
            ),
        )
        object.__setattr__(
            self,
            "provider_event_ts",
            _optional_timestamp(self.provider_event_ts, field="provider_event_ts"),
        )
        if self.provider_sequence is not None:
            object.__setattr__(
                self,
                "provider_sequence",
                canonical_safe_int(
                    self.provider_sequence, field="provider_sequence", minimum=0
                ),
            )

    @classmethod
    def from_raw(
        cls,
        *,
        collector_sequence: int,
        collector_received_wall_ts: datetime | str,
        collector_received_monotonic_ns: int,
        message_type: ProviderMessageTypeV3 | str,
        raw_payload: bytes,
        provider_generated_ts: datetime | str | None = None,
        provider_event_ts: datetime | str | None = None,
        provider_sequence: int | None = None,
    ) -> ProviderMessageEnvelopeV3:
        if not isinstance(raw_payload, bytes):
            raise CanonicalizationError("raw_payload must be exact bytes")
        return cls(
            collector_sequence=collector_sequence,
            collector_received_wall_ts=collector_received_wall_ts,
            collector_received_monotonic_ns=collector_received_monotonic_ns,
            message_type=message_type,
            raw_payload_base64=base64.b64encode(raw_payload).decode("ascii"),
            raw_payload_sha256=hashlib.sha256(raw_payload).hexdigest(),
            provider_generated_ts=provider_generated_ts,
            provider_event_ts=provider_event_ts,
            provider_sequence=provider_sequence,
        )

    @property
    def raw_payload(self) -> bytes:
        return _raw_bytes(self.raw_payload_base64)

    def identity_payload(self) -> dict[str, Any]:
        return {
            "collector_received_monotonic_ns": self.collector_received_monotonic_ns,
            "collector_received_wall_ts": utc_iso(self.collector_received_wall_ts),
            "collector_sequence": self.collector_sequence,
            "message_type": self.message_type.value,
            "provider_event_ts": None
            if self.provider_event_ts is None
            else utc_iso(self.provider_event_ts),
            "provider_generated_ts": None
            if self.provider_generated_ts is None
            else utc_iso(self.provider_generated_ts),
            "provider_sequence": self.provider_sequence,
            "raw_payload_base64": self.raw_payload_base64,
            "raw_payload_sha256": self.raw_payload_sha256,
        }

    @property
    def message_receipt_id(self) -> str:
        return _identity("ProviderMessageEnvelopeV3", self.identity_payload())

    def as_dict(self) -> dict[str, Any]:
        return {
            **self.identity_payload(),
            "message_receipt_id": self.message_receipt_id,
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> ProviderMessageEnvelopeV3:
        expected = set(cls.__dataclass_fields__) | {"message_receipt_id"}
        require_exact_keys(
            payload, expected=expected, context="ProviderMessageEnvelopeV3"
        )
        item = cls(**{name: payload[name] for name in cls.__dataclass_fields__})
        _require_digest(
            payload["message_receipt_id"],
            item.message_receipt_id,
            field="message_receipt_id",
        )
        return item


@dataclass(frozen=True, slots=True, kw_only=True)
class CaptureSegmentV3:
    """A bounded immutable sequence of exact provider message occurrences."""

    adapter_policy_id: str
    provider_native_key: str
    collector_instance_id: str
    collector_boot_id: str
    connection_id: str
    connection_generation: int
    subscription_manifest_hash: str
    vintage: PhysicalVintage
    envelopes: tuple[ProviderMessageEnvelopeV3, ...]
    closed_at: datetime
    clock_uncertainty_milliseconds: int
    parent_capture_segment_id: str | None = None

    def __post_init__(self) -> None:
        for field_name in ("adapter_policy_id", "subscription_manifest_hash"):
            object.__setattr__(
                self,
                field_name,
                canonical_hash(getattr(self, field_name), field=field_name),
            )
        for field_name in (
            "provider_native_key",
            "collector_instance_id",
            "collector_boot_id",
            "connection_id",
        ):
            object.__setattr__(
                self,
                field_name,
                canonical_identifier(getattr(self, field_name), field=field_name),
            )
        object.__setattr__(
            self,
            "connection_generation",
            canonical_safe_int(
                self.connection_generation, field="connection_generation", minimum=1
            ),
        )
        object.__setattr__(
            self, "vintage", _enum(self.vintage, PhysicalVintage, field="vintage")
        )
        envelopes = tuple(self.envelopes)
        if not envelopes or len(envelopes) > MAX_CAPTURE_ENVELOPES:
            raise CanonicalizationError(
                f"envelopes must contain between 1 and {MAX_CAPTURE_ENVELOPES} records"
            )
        if not all(isinstance(item, ProviderMessageEnvelopeV3) for item in envelopes):
            raise CanonicalizationError(
                "envelopes must contain ProviderMessageEnvelopeV3 records"
            )
        sequences = tuple(item.collector_sequence for item in envelopes)
        if sequences != tuple(range(sequences[0], sequences[0] + len(sequences))):
            raise CanonicalizationError(
                "capture envelope collector sequences must be contiguous"
            )
        monotonic = tuple(item.collector_received_monotonic_ns for item in envelopes)
        if any(right <= left for left, right in zip(monotonic, monotonic[1:])):
            raise CanonicalizationError(
                "capture envelope monotonic clocks must strictly increase"
            )
        if sum(len(item.raw_payload) for item in envelopes) > MAX_CAPTURE_RAW_BYTES:
            raise CanonicalizationError("capture segment exceeds raw-byte limit")
        object.__setattr__(self, "envelopes", envelopes)
        closed_at = utc_datetime(self.closed_at, field="closed_at")
        if closed_at < max(item.collector_received_wall_ts for item in envelopes):
            raise CanonicalizationError("closed_at precedes a captured message")
        object.__setattr__(self, "closed_at", closed_at)
        object.__setattr__(
            self,
            "clock_uncertainty_milliseconds",
            canonical_safe_int(
                self.clock_uncertainty_milliseconds,
                field="clock_uncertainty_milliseconds",
                minimum=0,
                maximum=3_600_000,
            ),
        )
        object.__setattr__(
            self,
            "parent_capture_segment_id",
            _optional_hash(
                self.parent_capture_segment_id, field="parent_capture_segment_id"
            ),
        )
        if len(canonical_json_bytes(self.as_dict())) > MAX_CAPTURE_CANONICAL_BYTES:
            raise CanonicalizationError(
                "capture segment exceeds canonical ledger-object budget"
            )

    @property
    def message_receipt_ids(self) -> tuple[str, ...]:
        return tuple(item.message_receipt_id for item in self.envelopes)

    @property
    def envelope_root(self) -> str:
        return sha256_digest(
            {
                "domain": "CaptureEnvelopeRootV1",
                "message_receipt_ids": list(self.message_receipt_ids),
            }
        )

    @property
    def raw_artifact_hash(self) -> str:
        return sha256_digest(
            {
                "domain": "CaptureRawArtifactV1",
                "raw_payload_sha256": [
                    item.raw_payload_sha256 for item in self.envelopes
                ],
            }
        )

    def partition_payload(self) -> dict[str, Any]:
        return {
            "adapter_policy_id": self.adapter_policy_id,
            "collector_boot_id": self.collector_boot_id,
            "collector_instance_id": self.collector_instance_id,
            "provider_native_key": self.provider_native_key,
        }

    @property
    def capture_partition_id(self) -> str:
        return _identity("CapturePartitionV3", self.partition_payload())

    def identity_payload(self) -> dict[str, Any]:
        return {
            **self.partition_payload(),
            "capture_partition_id": self.capture_partition_id,
            "clock_uncertainty_milliseconds": self.clock_uncertainty_milliseconds,
            "closed_at": utc_iso(self.closed_at),
            "connection_generation": self.connection_generation,
            "connection_id": self.connection_id,
            "envelope_root": self.envelope_root,
            "first_collector_sequence": self.envelopes[0].collector_sequence,
            "last_collector_sequence": self.envelopes[-1].collector_sequence,
            "message_receipt_ids": list(self.message_receipt_ids),
            "parent_capture_segment_id": self.parent_capture_segment_id,
            "raw_artifact_hash": self.raw_artifact_hash,
            "record_count": len(self.envelopes),
            "subscription_manifest_hash": self.subscription_manifest_hash,
            "vintage": self.vintage.value,
        }

    @property
    def capture_segment_id(self) -> str:
        return _identity("CaptureSegmentV3", self.identity_payload())

    def as_dict(self) -> dict[str, Any]:
        return {
            "canonicalization_version": CANONICALIZATION_VERSION,
            "capture_segment_id": self.capture_segment_id,
            **self.identity_payload(),
            "envelopes": [item.as_dict() for item in self.envelopes],
            "schema_version": PHYSICAL_MARKET_DATA_SCHEMA_VERSION,
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> CaptureSegmentV3:
        expected = {
            "adapter_policy_id",
            "canonicalization_version",
            "capture_partition_id",
            "capture_segment_id",
            "clock_uncertainty_milliseconds",
            "closed_at",
            "collector_boot_id",
            "collector_instance_id",
            "connection_generation",
            "connection_id",
            "envelope_root",
            "envelopes",
            "first_collector_sequence",
            "last_collector_sequence",
            "message_receipt_ids",
            "parent_capture_segment_id",
            "provider_native_key",
            "raw_artifact_hash",
            "record_count",
            "schema_version",
            "subscription_manifest_hash",
            "vintage",
        }
        require_exact_keys(payload, expected=expected, context="CaptureSegmentV3")
        _require_versions(payload)
        raw_envelopes = payload["envelopes"]
        if not isinstance(raw_envelopes, list):
            raise CanonicalizationError("envelopes must be a JSON array")
        item = cls(
            adapter_policy_id=payload["adapter_policy_id"],
            provider_native_key=payload["provider_native_key"],
            collector_instance_id=payload["collector_instance_id"],
            collector_boot_id=payload["collector_boot_id"],
            connection_id=payload["connection_id"],
            connection_generation=payload["connection_generation"],
            subscription_manifest_hash=payload["subscription_manifest_hash"],
            vintage=payload["vintage"],
            envelopes=tuple(
                ProviderMessageEnvelopeV3.from_mapping(value) for value in raw_envelopes
            ),
            closed_at=payload["closed_at"],
            clock_uncertainty_milliseconds=payload["clock_uncertainty_milliseconds"],
            parent_capture_segment_id=payload["parent_capture_segment_id"],
        )
        checks = {
            "capture_partition_id": item.capture_partition_id,
            "capture_segment_id": item.capture_segment_id,
            "envelope_root": item.envelope_root,
            "raw_artifact_hash": item.raw_artifact_hash,
        }
        for field_name, expected_value in checks.items():
            _require_digest(payload[field_name], expected_value, field=field_name)
        if payload["record_count"] != len(item.envelopes):
            raise CanonicalizationError("record_count differs from envelopes")
        if payload["message_receipt_ids"] != list(item.message_receipt_ids):
            raise CanonicalizationError("message_receipt_ids differ from envelopes")
        if payload["first_collector_sequence"] != item.envelopes[0].collector_sequence:
            raise CanonicalizationError(
                "first_collector_sequence differs from envelopes"
            )
        if payload["last_collector_sequence"] != item.envelopes[-1].collector_sequence:
            raise CanonicalizationError(
                "last_collector_sequence differs from envelopes"
            )
        return item


def validate_capture_segment_lineage(
    segment: CaptureSegmentV3,
    registry: Mapping[str, CaptureSegmentV3],
) -> None:
    """Reject capture gaps, forks, and invalid reconnect-generation transitions.

    A partition's first durable capture still starts at collector sequence one, but
    it need not come from transport generation one: an earlier connection may have
    terminated before yielding any provider message. Once a segment is registered,
    the ordinary parent, contiguity, and no-fork rules govern every successor.
    """

    if segment.parent_capture_segment_id is None:
        if segment.envelopes[0].collector_sequence != 1:
            raise CanonicalizationError(
                "capture segment root must begin at collector sequence 1"
            )
        if any(
            item.capture_partition_id == segment.capture_partition_id
            for item in registry.values()
        ):
            raise CanonicalizationError("capture partition already has a root segment")
        return
    parent = registry.get(segment.parent_capture_segment_id)
    if not isinstance(parent, CaptureSegmentV3):
        raise CanonicalizationError("capture segment parent is not registered")
    if segment.capture_partition_id != parent.capture_partition_id:
        raise CanonicalizationError("capture segment successor changes partition")
    same_partition = [
        item
        for item in registry.values()
        if item.capture_partition_id == segment.capture_partition_id
    ]
    superseded_ids = {
        item.parent_capture_segment_id
        for item in same_partition
        if item.parent_capture_segment_id is not None
    }
    if parent.capture_segment_id in superseded_ids:
        raise CanonicalizationError("capture segment forks a superseded parent")
    if (
        segment.envelopes[0].collector_sequence
        != parent.envelopes[-1].collector_sequence + 1
    ):
        raise CanonicalizationError(
            "capture segment successor skips collector sequence"
        )
    if (
        segment.envelopes[0].collector_received_monotonic_ns
        <= parent.envelopes[-1].collector_received_monotonic_ns
    ):
        raise CanonicalizationError(
            "capture segment successor monotonic clock moves backwards"
        )
    if segment.connection_generation < parent.connection_generation:
        raise CanonicalizationError("capture connection generation moves backwards")
    if (
        segment.connection_generation == parent.connection_generation
        and segment.connection_id != parent.connection_id
    ):
        raise CanonicalizationError("connection ID changed without a new generation")
    if (
        segment.connection_generation == parent.connection_generation
        and segment.subscription_manifest_hash != parent.subscription_manifest_hash
    ):
        raise CanonicalizationError(
            "subscription manifest changed inside one connection generation"
        )
    if segment.connection_generation > parent.connection_generation + 1:
        raise CanonicalizationError("capture connection generation skips an epoch")


@dataclass(frozen=True, slots=True, kw_only=True)
class ProviderMessageDispositionV3:
    """One exhaustive, immutable classification of a captured occurrence."""

    adapter_policy_id: str
    capture_segment_id: str
    message_receipt_id: str
    raw_payload_sha256: str
    disposition_kind: MessageDispositionKind
    classifier_release_hash: str
    classified_at: datetime
    observation_derivation_id: str | None = None
    observation_revision_id: str | None = None
    duplicate_of_message_receipt_id: str | None = None
    duplicate_of_disposition_id: str | None = None
    provider_diagnostic_code: str | None = None
    provider_diagnostic_digest: str | None = None

    def __post_init__(self) -> None:
        for field_name in (
            "adapter_policy_id",
            "capture_segment_id",
            "message_receipt_id",
            "raw_payload_sha256",
            "classifier_release_hash",
        ):
            object.__setattr__(
                self,
                field_name,
                canonical_hash(getattr(self, field_name), field=field_name),
            )
        if self.classifier_release_hash not in {
            BYBIT_V5_KLINE_CLASSIFIER_RELEASE_HASH,
            BYBIT_V5_INSTRUMENT_INFO_CLASSIFIER_RELEASE_HASH,
        }:
            raise CanonicalizationError(
                "message disposition is not bound to an approved classifier release"
            )
        object.__setattr__(
            self,
            "disposition_kind",
            _enum(
                self.disposition_kind,
                MessageDispositionKind,
                field="disposition_kind",
            ),
        )
        object.__setattr__(
            self,
            "classified_at",
            utc_datetime(self.classified_at, field="classified_at"),
        )
        for field_name in (
            "observation_derivation_id",
            "observation_revision_id",
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
            _optional_identifier(
                self.provider_diagnostic_code,
                field="provider_diagnostic_code",
            ),
        )
        normalized_refs = (
            self.observation_derivation_id,
            self.observation_revision_id,
        )
        duplicate_refs = (
            self.duplicate_of_message_receipt_id,
            self.duplicate_of_disposition_id,
        )
        diagnostic_refs = (
            self.provider_diagnostic_code,
            self.provider_diagnostic_digest,
        )
        if self.disposition_kind is MessageDispositionKind.NORMALIZED_OBSERVATION:
            if any(value is None for value in normalized_refs):
                raise CanonicalizationError(
                    "normalized disposition requires derivation and revision references"
                )
            if any(value is not None for value in (*duplicate_refs, *diagnostic_refs)):
                raise CanonicalizationError(
                    "normalized disposition contains foreign reference fields"
                )
        elif self.disposition_kind is MessageDispositionKind.EXACT_DUPLICATE:
            if any(value is None for value in duplicate_refs):
                raise CanonicalizationError(
                    "duplicate disposition requires original message and disposition"
                )
            if self.duplicate_of_message_receipt_id == self.message_receipt_id:
                raise CanonicalizationError(
                    "duplicate disposition cannot reference itself"
                )
            if any(value is not None for value in (*normalized_refs, *diagnostic_refs)):
                raise CanonicalizationError(
                    "duplicate disposition contains foreign reference fields"
                )
        elif self.disposition_kind is MessageDispositionKind.PROVIDER_ERROR:
            if any(value is None for value in diagnostic_refs):
                raise CanonicalizationError(
                    "provider-error disposition requires diagnostic evidence"
                )
            if any(value is not None for value in (*normalized_refs, *duplicate_refs)):
                raise CanonicalizationError(
                    "provider-error disposition contains foreign reference fields"
                )
        elif any(
            value is not None
            for value in (*normalized_refs, *duplicate_refs, *diagnostic_refs)
        ):
            raise CanonicalizationError(
                "non-observation disposition contains reference fields"
            )

    def identity_payload(self) -> dict[str, Any]:
        return {
            "adapter_policy_id": self.adapter_policy_id,
            "capture_segment_id": self.capture_segment_id,
            "classified_at": utc_iso(self.classified_at),
            "classifier_release_hash": self.classifier_release_hash,
            "disposition_kind": self.disposition_kind.value,
            "duplicate_of_disposition_id": self.duplicate_of_disposition_id,
            "duplicate_of_message_receipt_id": (self.duplicate_of_message_receipt_id),
            "message_receipt_id": self.message_receipt_id,
            "observation_derivation_id": self.observation_derivation_id,
            "observation_revision_id": self.observation_revision_id,
            "provider_diagnostic_code": self.provider_diagnostic_code,
            "provider_diagnostic_digest": self.provider_diagnostic_digest,
            "raw_payload_sha256": self.raw_payload_sha256,
        }

    @property
    def provider_message_disposition_id(self) -> str:
        return _identity("ProviderMessageDispositionV3", self.identity_payload())

    def as_dict(self) -> dict[str, Any]:
        return {
            "canonicalization_version": CANONICALIZATION_VERSION,
            **self.identity_payload(),
            "provider_message_disposition_id": (self.provider_message_disposition_id),
            "schema_version": PHYSICAL_MARKET_DATA_SCHEMA_VERSION,
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> ProviderMessageDispositionV3:
        expected = set(cls.__dataclass_fields__) | {
            "canonicalization_version",
            "provider_message_disposition_id",
            "schema_version",
        }
        require_exact_keys(
            payload,
            expected=expected,
            context="ProviderMessageDispositionV3",
        )
        _require_versions(payload)
        item = cls(**{name: payload[name] for name in cls.__dataclass_fields__})
        _require_digest(
            payload["provider_message_disposition_id"],
            item.provider_message_disposition_id,
            field="provider_message_disposition_id",
        )
        return item


@dataclass(frozen=True, slots=True, kw_only=True)
class ObservationDerivationV3:
    """Deterministic proof mapping raw receipts or child observations to one value."""

    adapter_policy_id: str
    derivation_kind: DerivationKind
    input_message_receipt_ids: tuple[str, ...]
    input_observation_revision_ids: tuple[str, ...]
    transform_code_hash: str
    transform_parameters_hash: str
    interval_policy_id: str
    numeric_policy_id: str
    sparse_interval_policy_id: str
    calendar_manifest_id: str
    output_field_ids: tuple[str, ...]
    output_field_values: tuple[str, ...]
    derived_at: datetime

    def __post_init__(self) -> None:
        for field_name in (
            "adapter_policy_id",
            "transform_code_hash",
            "transform_parameters_hash",
            "interval_policy_id",
            "numeric_policy_id",
            "sparse_interval_policy_id",
            "calendar_manifest_id",
        ):
            object.__setattr__(
                self,
                field_name,
                canonical_hash(getattr(self, field_name), field=field_name),
            )
        object.__setattr__(
            self,
            "derivation_kind",
            _enum(self.derivation_kind, DerivationKind, field="derivation_kind"),
        )
        raw_ids = _hashes(
            self.input_message_receipt_ids,
            field="input_message_receipt_ids",
            allow_empty=True,
        )
        observation_ids = _hashes(
            self.input_observation_revision_ids,
            field="input_observation_revision_ids",
            allow_empty=True,
        )
        if self.derivation_kind is DerivationKind.RAW_NORMALIZATION:
            if len(raw_ids) != 1 or observation_ids:
                raise CanonicalizationError(
                    "raw normalization requires exactly one raw receipt and no child observation"
                )
        elif raw_ids or not observation_ids:
            raise CanonicalizationError(
                "timeframe aggregation requires child observations and no raw receipt"
            )
        object.__setattr__(self, "input_message_receipt_ids", raw_ids)
        object.__setattr__(self, "input_observation_revision_ids", observation_ids)
        fields = _identifiers(self.output_field_ids, field="output_field_ids")
        if isinstance(
            self.output_field_values, (str, bytes, bytearray)
        ) or not isinstance(self.output_field_values, Sequence):
            raise CanonicalizationError("output_field_values must be a sequence")
        values = tuple(
            canonical_identifier(value, field="output_field_values", maximum=1024)
            for value in self.output_field_values
        )
        if len(fields) != len(values):
            raise CanonicalizationError(
                "output_field_ids and output_field_values lengths differ"
            )
        object.__setattr__(self, "output_field_ids", fields)
        object.__setattr__(self, "output_field_values", values)
        object.__setattr__(
            self, "derived_at", utc_datetime(self.derived_at, field="derived_at")
        )

    @property
    def input_root(self) -> str:
        return sha256_digest(
            {
                "domain": "ObservationDerivationInputRootV1",
                "input_message_receipt_ids": list(self.input_message_receipt_ids),
                "input_observation_revision_ids": list(
                    self.input_observation_revision_ids
                ),
            }
        )

    @property
    def output_value_digest(self) -> str:
        return observation_value_digest(self.output_field_ids, self.output_field_values)

    def identity_payload(self) -> dict[str, Any]:
        return {
            "adapter_policy_id": self.adapter_policy_id,
            "calendar_manifest_id": self.calendar_manifest_id,
            "derivation_kind": self.derivation_kind.value,
            "derived_at": utc_iso(self.derived_at),
            "input_message_receipt_ids": list(self.input_message_receipt_ids),
            "input_observation_revision_ids": list(self.input_observation_revision_ids),
            "input_root": self.input_root,
            "interval_policy_id": self.interval_policy_id,
            "numeric_policy_id": self.numeric_policy_id,
            "output_field_ids": list(self.output_field_ids),
            "output_field_values": list(self.output_field_values),
            "output_value_digest": self.output_value_digest,
            "sparse_interval_policy_id": self.sparse_interval_policy_id,
            "transform_code_hash": self.transform_code_hash,
            "transform_parameters_hash": self.transform_parameters_hash,
        }

    @property
    def observation_derivation_id(self) -> str:
        return _identity("ObservationDerivationV3", self.identity_payload())

    def as_dict(self) -> dict[str, Any]:
        return {
            "canonicalization_version": CANONICALIZATION_VERSION,
            **self.identity_payload(),
            "observation_derivation_id": self.observation_derivation_id,
            "schema_version": PHYSICAL_MARKET_DATA_SCHEMA_VERSION,
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> ObservationDerivationV3:
        expected = set(cls.__dataclass_fields__) | {
            "canonicalization_version",
            "input_root",
            "observation_derivation_id",
            "output_value_digest",
            "schema_version",
        }
        require_exact_keys(
            payload, expected=expected, context="ObservationDerivationV3"
        )
        _require_versions(payload)
        item = cls(**{name: payload[name] for name in cls.__dataclass_fields__})
        for field_name, expected_value in (
            ("input_root", item.input_root),
            ("output_value_digest", item.output_value_digest),
            ("observation_derivation_id", item.observation_derivation_id),
        ):
            _require_digest(payload[field_name], expected_value, field=field_name)
        return item


@dataclass(frozen=True, slots=True, kw_only=True)
class ObservationRevisionV3:
    """One immutable revision of a bar or market-status observation."""

    adapter_policy_id: str
    source_member_key: str
    instrument_mapping_id: str
    source_id: str
    asset_id: str
    venue_id: str
    concrete_contract_id: str
    timeframe_id: str
    observation_name: str
    observation_kind: ObservationKind
    bar_open_ts: datetime | None
    bar_close_ts: datetime | None
    source_event_ts: datetime
    source_publish_ts: datetime | None
    durably_appended_ts: datetime
    normalized_at: datetime
    available_at: datetime
    completion_state: CompletionState
    completion_basis: CompletionBasis
    observation_derivation_id: str
    field_ids: tuple[str, ...]
    field_values: tuple[str, ...]
    parent_observation_revision_id: str | None = None
    correction_reason: str | None = None

    def __post_init__(self) -> None:
        for field_name in (
            "adapter_policy_id",
            "source_member_key",
            "instrument_mapping_id",
            "observation_derivation_id",
        ):
            object.__setattr__(
                self,
                field_name,
                canonical_hash(getattr(self, field_name), field=field_name),
            )
        for field_name in (
            "source_id",
            "asset_id",
            "venue_id",
            "concrete_contract_id",
            "timeframe_id",
            "observation_name",
        ):
            object.__setattr__(
                self,
                field_name,
                canonical_identifier(getattr(self, field_name), field=field_name),
            )
        object.__setattr__(
            self,
            "observation_kind",
            _enum(self.observation_kind, ObservationKind, field="observation_kind"),
        )
        object.__setattr__(
            self,
            "completion_state",
            _enum(self.completion_state, CompletionState, field="completion_state"),
        )
        object.__setattr__(
            self,
            "completion_basis",
            _enum(self.completion_basis, CompletionBasis, field="completion_basis"),
        )
        for field_name in (
            "bar_open_ts",
            "bar_close_ts",
            "source_publish_ts",
        ):
            object.__setattr__(
                self,
                field_name,
                _optional_timestamp(getattr(self, field_name), field=field_name),
            )
        for field_name in (
            "source_event_ts",
            "durably_appended_ts",
            "normalized_at",
            "available_at",
        ):
            object.__setattr__(
                self,
                field_name,
                utc_datetime(getattr(self, field_name), field=field_name),
            )
        if not self.durably_appended_ts <= self.normalized_at <= self.available_at:
            raise CanonicalizationError(
                "observation clocks require durable append <= normalized <= available"
            )
        fields = _identifiers(self.field_ids, field="field_ids")
        if isinstance(self.field_values, (str, bytes, bytearray)) or not isinstance(
            self.field_values, Sequence
        ):
            raise CanonicalizationError("field_values must be a sequence")
        values = tuple(
            canonical_identifier(value, field="field_values", maximum=1024)
            for value in self.field_values
        )
        if len(fields) != len(values):
            raise CanonicalizationError("field_ids and field_values lengths differ")
        object.__setattr__(self, "field_ids", fields)
        object.__setattr__(self, "field_values", values)
        object.__setattr__(
            self,
            "parent_observation_revision_id",
            _optional_hash(
                self.parent_observation_revision_id,
                field="parent_observation_revision_id",
            ),
        )
        object.__setattr__(
            self,
            "correction_reason",
            _optional_identifier(self.correction_reason, field="correction_reason"),
        )
        if self.observation_kind is ObservationKind.BAR:
            if self.bar_open_ts is None or self.bar_close_ts is None:
                raise CanonicalizationError(
                    "bar observation requires open and close clocks"
                )
            if self.bar_open_ts >= self.bar_close_ts:
                raise CanonicalizationError("bar_open_ts must precede bar_close_ts")
            if not self.bar_open_ts <= self.source_event_ts < self.bar_close_ts:
                raise CanonicalizationError(
                    "bar source_event_ts must lie inside its half-open interval"
                )
            if (
                self.completion_state is CompletionState.COMPLETE
                and self.bar_close_ts > self.available_at
            ):
                raise CanonicalizationError(
                    "completed bar cannot be available before close"
                )
            self._validate_bar_values()
        elif self.bar_open_ts is not None or self.bar_close_ts is not None:
            raise CanonicalizationError(
                "non-bar observation must not declare bar clocks"
            )
        if (
            self.completion_state is CompletionState.PROVISIONAL
            and self.completion_basis is not CompletionBasis.NONE
        ):
            raise CanonicalizationError(
                "provisional observation must use completion basis NONE"
            )
        if (
            self.completion_state is CompletionState.COMPLETE
            and self.completion_basis is CompletionBasis.NONE
        ):
            raise CanonicalizationError(
                "completed observation requires a completion basis"
            )
        if (
            self.parent_observation_revision_id is None
            and self.correction_reason is not None
        ):
            raise CanonicalizationError(
                "root observation revision cannot declare correction_reason"
            )
        if (
            self.parent_observation_revision_id is not None
            and self.correction_reason is None
        ):
            raise CanonicalizationError(
                "successor observation revision requires correction_reason"
            )

    def _validate_bar_values(self) -> None:
        values = dict(zip(self.field_ids, self.field_values))
        required = {"open", "high", "low", "close", "volume"}
        if not required.issubset(values):
            raise CanonicalizationError("bar observation requires OHLCV fields")
        normalized = {
            name: canonical_decimal(
                values[name],
                field=name,
                strictly_positive=name != "volume",
                minimum=0 if name == "volume" else None,
            )
            for name in required
        }
        for name, value in normalized.items():
            if values[name] != value:
                raise CanonicalizationError(
                    f"bar field {name} is not a canonical decimal"
                )
        opening = Decimal(normalized["open"])
        high = Decimal(normalized["high"])
        low = Decimal(normalized["low"])
        close = Decimal(normalized["close"])
        if high < max(opening, close, low) or low > min(opening, close, high):
            raise CanonicalizationError("bar OHLC values are internally inconsistent")
        for name in set(values) - required:
            canonical_decimal(values[name], field=name, minimum=0)

    def observation_key_payload(self) -> dict[str, Any]:
        return {
            "adapter_policy_id": self.adapter_policy_id,
            "asset_id": self.asset_id,
            "bar_close_ts": None
            if self.bar_close_ts is None
            else utc_iso(self.bar_close_ts),
            "bar_open_ts": None
            if self.bar_open_ts is None
            else utc_iso(self.bar_open_ts),
            "concrete_contract_id": self.concrete_contract_id,
            "observation_kind": self.observation_kind.value,
            "observation_name": self.observation_name,
            "source_member_key": self.source_member_key,
            "timeframe_id": self.timeframe_id,
            "venue_id": self.venue_id,
        }

    @property
    def observation_key(self) -> str:
        return _identity("ObservationKeyV3", self.observation_key_payload())

    @property
    def value_digest(self) -> str:
        return observation_value_digest(self.field_ids, self.field_values)

    def identity_payload(self) -> dict[str, Any]:
        return {
            **self.observation_key_payload(),
            "available_at": utc_iso(self.available_at),
            "completion_basis": self.completion_basis.value,
            "completion_state": self.completion_state.value,
            "correction_reason": self.correction_reason,
            "durably_appended_ts": utc_iso(self.durably_appended_ts),
            "field_ids": list(self.field_ids),
            "field_values": list(self.field_values),
            "instrument_mapping_id": self.instrument_mapping_id,
            "normalized_at": utc_iso(self.normalized_at),
            "observation_derivation_id": self.observation_derivation_id,
            "observation_key": self.observation_key,
            "parent_observation_revision_id": self.parent_observation_revision_id,
            "source_event_ts": utc_iso(self.source_event_ts),
            "source_id": self.source_id,
            "source_publish_ts": None
            if self.source_publish_ts is None
            else utc_iso(self.source_publish_ts),
            "value_digest": self.value_digest,
        }

    @property
    def observation_revision_id(self) -> str:
        return _identity("ObservationRevisionV3", self.identity_payload())

    def as_dict(self) -> dict[str, Any]:
        return {
            "canonicalization_version": CANONICALIZATION_VERSION,
            **self.identity_payload(),
            "observation_revision_id": self.observation_revision_id,
            "schema_version": PHYSICAL_MARKET_DATA_SCHEMA_VERSION,
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> ObservationRevisionV3:
        expected = set(cls.__dataclass_fields__) | {
            "canonicalization_version",
            "observation_key",
            "observation_revision_id",
            "schema_version",
            "value_digest",
        }
        require_exact_keys(payload, expected=expected, context="ObservationRevisionV3")
        _require_versions(payload)
        item = cls(**{name: payload[name] for name in cls.__dataclass_fields__})
        for field_name, expected_value in (
            ("observation_key", item.observation_key),
            ("value_digest", item.value_digest),
            ("observation_revision_id", item.observation_revision_id),
        ):
            _require_digest(payload[field_name], expected_value, field=field_name)
        return item


def validate_observation_revision_lineage(
    revision: ObservationRevisionV3,
    registry: Mapping[str, ObservationRevisionV3],
) -> None:
    """Require a single append-only revision chain per stable observation key."""

    parent_id = revision.parent_observation_revision_id
    prior_same_key = [
        item
        for item in registry.values()
        if item.observation_key == revision.observation_key
    ]
    heads = {item.observation_revision_id for item in prior_same_key} - {
        item.parent_observation_revision_id
        for item in prior_same_key
        if item.parent_observation_revision_id is not None
    }
    if parent_id is None:
        if prior_same_key:
            raise CanonicalizationError("observation revision root already exists")
        return
    parent = registry.get(parent_id)
    if not isinstance(parent, ObservationRevisionV3):
        raise CanonicalizationError("observation revision parent is not registered")
    if parent.observation_key != revision.observation_key:
        raise CanonicalizationError(
            "observation revision successor changes coordinates"
        )
    if parent.instrument_mapping_id != revision.instrument_mapping_id:
        raise CanonicalizationError(
            "observation revision successor changes instrument mapping"
        )
    if parent_id not in heads:
        raise CanonicalizationError("observation revision forks a superseded parent")
    if revision.durably_appended_ts < parent.durably_appended_ts:
        raise CanonicalizationError(
            "observation revision durable clock moves backwards"
        )
    if revision.available_at < parent.available_at:
        raise CanonicalizationError("observation revision availability moves backwards")
    if revision.normalized_at < parent.normalized_at:
        raise CanonicalizationError(
            "observation revision normalization clock moves backwards"
        )
    if revision.source_event_ts < parent.source_event_ts:
        raise CanonicalizationError(
            "observation revision provider event clock moves backwards"
        )
    if parent.source_publish_ts is not None and (
        revision.source_publish_ts is None
        or revision.source_publish_ts < parent.source_publish_ts
    ):
        raise CanonicalizationError(
            "observation revision provider publication clock moves backwards"
        )
    if (
        parent.completion_state is CompletionState.COMPLETE
        and revision.completion_state is CompletionState.PROVISIONAL
    ):
        raise CanonicalizationError(
            "completed observation cannot regress to provisional"
        )


class SelectionAnchor(str, Enum):
    CUTOFF_COMPLETED_INTERVAL = "CUTOFF_COMPLETED_INTERVAL"
    LATEST_COMPLETED_ASOF = "LATEST_COMPLETED_ASOF"


class ContinuityPolicy(str, Enum):
    STRICT_INTERVAL_GRID = "STRICT_INTERVAL_GRID"
    AUTHORITATIVE_CALENDAR_GRID = "AUTHORITATIVE_CALENDAR_GRID"
    SPARSE_WITH_LIVENESS = "SPARSE_WITH_LIVENESS"


@dataclass(frozen=True, slots=True, kw_only=True)
class ObservationSelectionPolicyV3:
    """Complete selector semantics missing from the generic V3.2 slot contract."""

    dependency_slot_id: str
    selection_mode: DependencySelectionMode
    anchor: SelectionAnchor
    interval_seconds: int
    anchor_lag_intervals: int
    requested_count: int
    continuity_policy: ContinuityPolicy
    maximum_age_seconds: int | None
    maximum_prefix_age_seconds: int
    tie_break_policy: str
    frozen_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "dependency_slot_id",
            canonical_hash(self.dependency_slot_id, field="dependency_slot_id"),
        )
        object.__setattr__(
            self,
            "selection_mode",
            _enum(self.selection_mode, DependencySelectionMode, field="selection_mode"),
        )
        object.__setattr__(
            self, "anchor", _enum(self.anchor, SelectionAnchor, field="anchor")
        )
        object.__setattr__(
            self,
            "interval_seconds",
            canonical_safe_int(
                self.interval_seconds,
                field="interval_seconds",
                minimum=1,
                maximum=86_400,
            ),
        )
        object.__setattr__(
            self,
            "continuity_policy",
            _enum(self.continuity_policy, ContinuityPolicy, field="continuity_policy"),
        )
        object.__setattr__(
            self,
            "anchor_lag_intervals",
            canonical_safe_int(
                self.anchor_lag_intervals,
                field="anchor_lag_intervals",
                minimum=0,
                maximum=10_000,
            ),
        )
        object.__setattr__(
            self,
            "requested_count",
            canonical_safe_int(
                self.requested_count,
                field="requested_count",
                minimum=1,
                maximum=MAX_PREFIX_RECORDS,
            ),
        )
        object.__setattr__(
            self,
            "maximum_prefix_age_seconds",
            canonical_safe_int(
                self.maximum_prefix_age_seconds,
                field="maximum_prefix_age_seconds",
                minimum=1,
                maximum=604_800,
            ),
        )
        if self.maximum_age_seconds is not None:
            object.__setattr__(
                self,
                "maximum_age_seconds",
                canonical_safe_int(
                    self.maximum_age_seconds,
                    field="maximum_age_seconds",
                    minimum=0,
                    maximum=315_576_000,
                ),
            )
        object.__setattr__(
            self,
            "tie_break_policy",
            canonical_identifier(self.tie_break_policy, field="tie_break_policy"),
        )
        if self.tie_break_policy != "AVAILABLE_AT_THEN_REVISION_ID":
            raise CanonicalizationError(
                "unsupported physical selection tie-break policy"
            )
        object.__setattr__(
            self, "frozen_at", utc_datetime(self.frozen_at, field="frozen_at")
        )
        if self.selection_mode is DependencySelectionMode.EXACT_EVENT:
            if (
                self.anchor is not SelectionAnchor.CUTOFF_COMPLETED_INTERVAL
                or self.requested_count != 1
            ):
                raise CanonicalizationError(
                    "EXACT_EVENT requires cutoff anchor and one row"
                )
        elif self.selection_mode is DependencySelectionMode.LATEST_AVAILABLE_ASOF:
            if (
                self.anchor is not SelectionAnchor.LATEST_COMPLETED_ASOF
                or self.requested_count != 1
            ):
                raise CanonicalizationError(
                    "LATEST_AVAILABLE_ASOF requires latest anchor and one row"
                )
        elif (
            self.selection_mode
            is DependencySelectionMode.TRAILING_COMPLETED_OBSERVATIONS
        ):
            if self.anchor is not SelectionAnchor.LATEST_COMPLETED_ASOF:
                raise CanonicalizationError(
                    "trailing selection requires latest completed anchor"
                )
        else:
            raise CanonicalizationError(
                "physical observation selector supports exact/latest/trailing only"
            )

    def identity_payload(self) -> dict[str, Any]:
        return {
            "anchor": self.anchor.value,
            "anchor_lag_intervals": self.anchor_lag_intervals,
            "continuity_policy": self.continuity_policy.value,
            "dependency_slot_id": self.dependency_slot_id,
            "frozen_at": utc_iso(self.frozen_at),
            "interval_seconds": self.interval_seconds,
            "maximum_age_seconds": self.maximum_age_seconds,
            "maximum_prefix_age_seconds": self.maximum_prefix_age_seconds,
            "requested_count": self.requested_count,
            "selection_mode": self.selection_mode.value,
            "tie_break_policy": self.tie_break_policy,
        }

    @property
    def observation_selection_policy_id(self) -> str:
        return _identity("ObservationSelectionPolicyV3", self.identity_payload())

    def as_dict(self) -> dict[str, Any]:
        return {
            "canonicalization_version": CANONICALIZATION_VERSION,
            **self.identity_payload(),
            "observation_selection_policy_id": self.observation_selection_policy_id,
            "schema_version": PHYSICAL_MARKET_DATA_SCHEMA_VERSION,
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> ObservationSelectionPolicyV3:
        expected = set(cls.__dataclass_fields__) | {
            "canonicalization_version",
            "observation_selection_policy_id",
            "schema_version",
        }
        require_exact_keys(
            payload, expected=expected, context="ObservationSelectionPolicyV3"
        )
        _require_versions(payload)
        item = cls(**{name: payload[name] for name in cls.__dataclass_fields__})
        _require_digest(
            payload["observation_selection_policy_id"],
            item.observation_selection_policy_id,
            field="observation_selection_policy_id",
        )
        return item


@dataclass(frozen=True, slots=True, kw_only=True)
class EvidencePrefixV3:
    """Finite ledger prefix against which completeness and latest are meaningful."""

    adapter_policy_id: str
    supporting_adapter_policy_ids: tuple[str, ...]
    source_member_key: str
    instrument_mapping_id: str
    ledger_id: str
    cutoff_global_sequence: int
    cutoff_receipt_hash: str
    knowledge_cutoff_ts: datetime
    capture_segment_ids: tuple[str, ...]
    message_disposition_ids: tuple[str, ...]
    observation_revision_ids: tuple[str, ...]
    active_observation_revision_ids: tuple[str, ...]
    status_observation_revision_ids: tuple[str, ...]
    unresolved_disposition_ids: tuple[str, ...]
    vintage: PhysicalVintage
    health: PrefixHealth
    health_reason_codes: tuple[str, ...]
    event_time_watermark: datetime
    health_valid_until: datetime
    assembled_at: datetime
    parent_evidence_prefix_id: str | None = None

    def __post_init__(self) -> None:
        for field_name in (
            "adapter_policy_id",
            "source_member_key",
            "instrument_mapping_id",
            "ledger_id",
            "cutoff_receipt_hash",
        ):
            object.__setattr__(
                self,
                field_name,
                canonical_hash(getattr(self, field_name), field=field_name),
            )
        object.__setattr__(
            self,
            "cutoff_global_sequence",
            canonical_safe_int(
                self.cutoff_global_sequence,
                field="cutoff_global_sequence",
                minimum=1,
            ),
        )
        for field_name in (
            "capture_segment_ids",
            "message_disposition_ids",
            "observation_revision_ids",
            "active_observation_revision_ids",
            "status_observation_revision_ids",
            "unresolved_disposition_ids",
        ):
            values = _hashes(
                getattr(self, field_name),
                field=field_name,
                allow_empty=field_name
                in {"status_observation_revision_ids", "unresolved_disposition_ids"},
            )
            object.__setattr__(self, field_name, tuple(sorted(values)))
        supporting = _hashes(
            self.supporting_adapter_policy_ids,
            field="supporting_adapter_policy_ids",
            allow_empty=True,
        )
        if self.adapter_policy_id in supporting:
            raise CanonicalizationError(
                "primary adapter policy cannot also be a supporting policy"
            )
        object.__setattr__(
            self,
            "supporting_adapter_policy_ids",
            tuple(sorted(supporting)),
        )
        if not set(self.active_observation_revision_ids).issubset(
            self.observation_revision_ids
        ):
            raise CanonicalizationError(
                "active observations must be included in observation_revision_ids"
            )
        if not set(self.status_observation_revision_ids).issubset(
            self.observation_revision_ids
        ):
            raise CanonicalizationError(
                "status observations must be included in observation_revision_ids"
            )
        if not set(self.unresolved_disposition_ids).issubset(
            self.message_disposition_ids
        ):
            raise CanonicalizationError(
                "unresolved dispositions must be included in message_disposition_ids"
            )
        object.__setattr__(
            self, "vintage", _enum(self.vintage, PhysicalVintage, field="vintage")
        )
        object.__setattr__(
            self, "health", _enum(self.health, PrefixHealth, field="health")
        )
        reasons = canonical_reason_codes(
            self.health_reason_codes, field="health_reason_codes"
        )
        object.__setattr__(self, "health_reason_codes", reasons)
        if (self.health is PrefixHealth.HEALTHY) != (not reasons):
            raise CanonicalizationError(
                "HEALTHY prefix requires no reasons and every non-healthy prefix requires reasons"
            )
        for field_name in (
            "knowledge_cutoff_ts",
            "event_time_watermark",
            "health_valid_until",
            "assembled_at",
        ):
            object.__setattr__(
                self,
                field_name,
                utc_datetime(getattr(self, field_name), field=field_name),
            )
        if self.event_time_watermark > self.knowledge_cutoff_ts:
            raise CanonicalizationError(
                "event_time_watermark must not exceed knowledge_cutoff_ts"
            )
        if self.health is PrefixHealth.HEALTHY and self.health_valid_until < max(
            self.knowledge_cutoff_ts, self.assembled_at
        ):
            raise CanonicalizationError(
                "HEALTHY prefix validity expired before it was assembled"
            )
        if self.assembled_at < self.knowledge_cutoff_ts:
            raise CanonicalizationError(
                "evidence prefix assembled_at precedes knowledge cutoff"
            )
        object.__setattr__(
            self,
            "parent_evidence_prefix_id",
            _optional_hash(
                self.parent_evidence_prefix_id, field="parent_evidence_prefix_id"
            ),
        )
        if len(canonical_json_bytes(self.as_dict())) > MAX_PREFIX_CANONICAL_BYTES:
            raise CanonicalizationError(
                "evidence prefix exceeds canonical ledger-object budget"
            )

    @property
    def raw_receipt_root(self) -> str:
        return sha256_digest(
            {
                "capture_segment_ids": list(self.capture_segment_ids),
                "domain": "EvidencePrefixRawReceiptRootV1",
            }
        )

    @property
    def normalized_revision_root(self) -> str:
        return sha256_digest(
            {
                "domain": "EvidencePrefixNormalizedRevisionRootV1",
                "observation_revision_ids": list(self.observation_revision_ids),
            }
        )

    def identity_payload(self) -> dict[str, Any]:
        return {
            "active_observation_revision_ids": list(
                self.active_observation_revision_ids
            ),
            "adapter_policy_id": self.adapter_policy_id,
            "assembled_at": utc_iso(self.assembled_at),
            "capture_segment_ids": list(self.capture_segment_ids),
            "cutoff_global_sequence": self.cutoff_global_sequence,
            "cutoff_receipt_hash": self.cutoff_receipt_hash,
            "event_time_watermark": utc_iso(self.event_time_watermark),
            "health": self.health.value,
            "health_valid_until": utc_iso(self.health_valid_until),
            "health_reason_codes": list(self.health_reason_codes),
            "instrument_mapping_id": self.instrument_mapping_id,
            "knowledge_cutoff_ts": utc_iso(self.knowledge_cutoff_ts),
            "ledger_id": self.ledger_id,
            "message_disposition_ids": list(self.message_disposition_ids),
            "normalized_revision_root": self.normalized_revision_root,
            "observation_revision_ids": list(self.observation_revision_ids),
            "parent_evidence_prefix_id": self.parent_evidence_prefix_id,
            "raw_receipt_root": self.raw_receipt_root,
            "source_member_key": self.source_member_key,
            "status_observation_revision_ids": list(
                self.status_observation_revision_ids
            ),
            "supporting_adapter_policy_ids": list(self.supporting_adapter_policy_ids),
            "unresolved_disposition_ids": list(self.unresolved_disposition_ids),
            "vintage": self.vintage.value,
        }

    @property
    def evidence_prefix_id(self) -> str:
        return _identity("EvidencePrefixV3", self.identity_payload())

    def as_dict(self) -> dict[str, Any]:
        return {
            "canonicalization_version": CANONICALIZATION_VERSION,
            **self.identity_payload(),
            "evidence_prefix_id": self.evidence_prefix_id,
            "schema_version": PHYSICAL_MARKET_DATA_SCHEMA_VERSION,
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> EvidencePrefixV3:
        expected = set(cls.__dataclass_fields__) | {
            "canonicalization_version",
            "evidence_prefix_id",
            "normalized_revision_root",
            "raw_receipt_root",
            "schema_version",
        }
        require_exact_keys(payload, expected=expected, context="EvidencePrefixV3")
        _require_versions(payload)
        item = cls(**{name: payload[name] for name in cls.__dataclass_fields__})
        for field_name, expected_value in (
            ("raw_receipt_root", item.raw_receipt_root),
            ("normalized_revision_root", item.normalized_revision_root),
            ("evidence_prefix_id", item.evidence_prefix_id),
        ):
            _require_digest(payload[field_name], expected_value, field=field_name)
        return item


def active_revision_heads(
    revisions: Sequence[ObservationRevisionV3],
) -> tuple[ObservationRevisionV3, ...]:
    """Return the only non-superseded revision for each observation key."""

    items = tuple(revisions)
    identities = {item.observation_revision_id for item in items}
    if len(identities) != len(items):
        raise CanonicalizationError("observation revisions contain duplicate IDs")
    by_key: dict[str, list[ObservationRevisionV3]] = {}
    for item in items:
        by_key.setdefault(item.observation_key, []).append(item)
    heads: list[ObservationRevisionV3] = []
    for key_items in by_key.values():
        parents = {
            item.parent_observation_revision_id
            for item in key_items
            if item.parent_observation_revision_id is not None
        }
        candidates = [
            item for item in key_items if item.observation_revision_id not in parents
        ]
        if len(candidates) != 1:
            raise CanonicalizationError(
                "observation revision graph does not have one active head"
            )
        heads.append(candidates[0])
    return tuple(sorted(heads, key=lambda item: item.observation_key))


_BLOCKING_DISPOSITION_KINDS = frozenset(
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


def unresolved_message_dispositions_v3(
    *,
    dispositions: Mapping[str, ProviderMessageDispositionV3],
    segments: Mapping[str, CaptureSegmentV3],
    revisions: Mapping[str, ObservationRevisionV3],
    adapter_policies: Mapping[str, ProviderAdapterPolicyV3],
    disposition_order: Sequence[str] | None = None,
) -> tuple[str, ...]:
    """Reduce immutable message outcomes to the currently unresolved blockers."""

    items = dict(dispositions)
    if disposition_order is None:
        ordered_ids = tuple(
            item.provider_message_disposition_id
            for item in sorted(
                items.values(),
                key=lambda item: (
                    item.classified_at,
                    item.message_receipt_id,
                    item.provider_message_disposition_id,
                ),
            )
        )
    else:
        ordered_ids = _hashes(
            disposition_order,
            field="disposition_order",
            allow_empty=True,
        )
        if set(ordered_ids) != set(items):
            raise CanonicalizationError(
                "disposition order differs from the supplied disposition set"
            )

    unresolved: dict[str, ProviderMessageDispositionV3] = {}
    for disposition_id in ordered_ids:
        disposition = items.get(disposition_id)
        if not isinstance(disposition, ProviderMessageDispositionV3):
            raise CanonicalizationError("message disposition is missing")
        policy = adapter_policies.get(disposition.adapter_policy_id)
        segment = segments.get(disposition.capture_segment_id)
        if not isinstance(policy, ProviderAdapterPolicyV3):
            raise CanonicalizationError("message disposition policy is missing")
        if not isinstance(segment, CaptureSegmentV3):
            raise CanonicalizationError("message disposition segment is missing")
        if segment.adapter_policy_id != disposition.adapter_policy_id:
            raise CanonicalizationError(
                "message disposition segment changes adapter policy"
            )
        envelope = _segment_envelope(segment, disposition.message_receipt_id)
        if envelope.raw_payload_sha256 != disposition.raw_payload_sha256:
            raise CanonicalizationError(
                "message disposition raw hash differs from its envelope"
            )

        if disposition.disposition_kind in _BLOCKING_DISPOSITION_KINDS:
            unresolved[disposition_id] = disposition
            continue
        if (
            disposition.disposition_kind
            is not MessageDispositionKind.NORMALIZED_OBSERVATION
        ):
            continue
        revision = revisions.get(disposition.observation_revision_id)
        if not isinstance(revision, ObservationRevisionV3):
            raise CanonicalizationError("normalized disposition revision is missing")
        if revision.completion_state is not CompletionState.COMPLETE:
            continue

        for blocker_id, blocker in tuple(unresolved.items()):
            if blocker.adapter_policy_id != disposition.adapter_policy_id:
                continue
            blocker_segment = segments.get(blocker.capture_segment_id)
            if not isinstance(blocker_segment, CaptureSegmentV3):
                raise CanonicalizationError("unresolved disposition segment is missing")
            kind = blocker.disposition_kind
            reconnected = (
                segment.collector_boot_id != blocker_segment.collector_boot_id
                or (
                    segment.capture_partition_id == blocker_segment.capture_partition_id
                    and segment.connection_generation
                    > blocker_segment.connection_generation
                )
            )
            if (
                kind is MessageDispositionKind.CLOCK_ORDERING_REJECTED
                and segment.collector_boot_id != blocker_segment.collector_boot_id
            ):
                unresolved.pop(blocker_id)
                continue
            if revision.observation_kind is ObservationKind.INSTRUMENT_STATUS:
                if kind in {
                    MessageDispositionKind.PROVIDER_ERROR,
                    MessageDispositionKind.EXPECTED_INSTRUMENT_STATUS_ABSENT,
                    MessageDispositionKind.RECEIPT_LAG_REJECTED,
                } or (
                    reconnected
                    and kind
                    in {
                        MessageDispositionKind.MALFORMED_PAYLOAD,
                        MessageDispositionKind.OUT_OF_SCOPE,
                    }
                ):
                    unresolved.pop(blocker_id)
                continue
            if revision.observation_kind is not ObservationKind.BAR:
                continue
            if kind is MessageDispositionKind.RECEIPT_LAG_REJECTED:
                unresolved.pop(blocker_id)
                continue
            if reconnected and kind in {
                MessageDispositionKind.PROVIDER_ERROR,
                MessageDispositionKind.MALFORMED_PAYLOAD,
                MessageDispositionKind.OUT_OF_SCOPE,
            }:
                unresolved.pop(blocker_id)

    return tuple(sorted(unresolved))


def _unresolved_disposition_health(
    unresolved: Sequence[ProviderMessageDispositionV3],
    policies: Mapping[str, ProviderAdapterPolicyV3],
) -> PrefixHealth:
    kinds = {item.disposition_kind for item in unresolved}
    if kinds.intersection(
        {
            MessageDispositionKind.MALFORMED_PAYLOAD,
            MessageDispositionKind.OUT_OF_SCOPE,
            MessageDispositionKind.CONTENT_CONFLICT,
        }
    ):
        return PrefixHealth.INTEGRITY_CONFLICT
    if MessageDispositionKind.UNSUPPORTED_SCHEMA in kinds:
        return PrefixHealth.SCHEMA_UNSUPPORTED
    if MessageDispositionKind.CLOCK_ORDERING_REJECTED in kinds:
        return PrefixHealth.CLOCK_UNCERTAIN
    for item in unresolved:
        policy = policies[item.adapter_policy_id]
        if (
            item.disposition_kind is MessageDispositionKind.PROVIDER_ERROR
            and policy.adapter_kind is ProviderAdapterKind.BYBIT_V5_PUBLIC_KLINE
        ):
            return PrefixHealth.DISCONNECTED
    if kinds.intersection(
        {
            MessageDispositionKind.PROVIDER_ERROR,
            MessageDispositionKind.EXPECTED_INSTRUMENT_STATUS_ABSENT,
        }
    ):
        return PrefixHealth.STATUS_BLOCKED
    return PrefixHealth.STALE


def validate_evidence_prefix_graph(
    prefix: EvidencePrefixV3,
    *,
    adapter_policy: ProviderAdapterPolicyV3,
    adapter_policies: Mapping[str, ProviderAdapterPolicyV3],
    segments: Mapping[str, CaptureSegmentV3],
    dispositions: Mapping[str, ProviderMessageDispositionV3],
    revisions: Mapping[str, ObservationRevisionV3],
    parent_prefixes: Mapping[str, EvidencePrefixV3],
    disposition_order: Sequence[str] | None = None,
) -> None:
    """Validate the content graph; the ledger separately proves prefix omission."""

    if prefix.adapter_policy_id != adapter_policy.adapter_policy_id:
        raise CanonicalizationError("evidence prefix adapter policy differs")
    policies = dict(adapter_policies)
    policies[adapter_policy.adapter_policy_id] = adapter_policy
    supporting_policies: list[ProviderAdapterPolicyV3] = []
    for policy_id in prefix.supporting_adapter_policy_ids:
        policy = policies.get(policy_id)
        if not isinstance(policy, ProviderAdapterPolicyV3):
            raise CanonicalizationError(
                "evidence prefix supporting adapter policy is missing"
            )
        expected_scope = (
            adapter_policy.provider_id,
            adapter_policy.venue_id,
            adapter_policy.environment_id,
            adapter_policy.asset_id,
            adapter_policy.concrete_contract_id,
            adapter_policy.provider_native_key,
            adapter_policy.timeframe_id,
            adapter_policy.base_interval_seconds,
            adapter_policy.calendar_manifest_id,
        )
        actual_scope = (
            policy.provider_id,
            policy.venue_id,
            policy.environment_id,
            policy.asset_id,
            policy.concrete_contract_id,
            policy.provider_native_key,
            policy.timeframe_id,
            policy.base_interval_seconds,
            policy.calendar_manifest_id,
        )
        if actual_scope != expected_scope:
            raise CanonicalizationError(
                "supporting adapter policy changes the concrete market scope"
            )
        if (
            policy.adapter_kind is not ProviderAdapterKind.BYBIT_V5_INSTRUMENT_INFO
            or policy.data_use is not ProviderDataUse.RECONCILIATION_ONLY
        ):
            raise CanonicalizationError(
                "initial supporting policy must be non-authoritative instrument status"
            )
        supporting_policies.append(policy)
    if adapter_policy.requires_instrument_status:
        if len(supporting_policies) != 1:
            raise CanonicalizationError(
                "HEALTHY price authority requires one explicit status adapter policy"
            )
    elif supporting_policies or prefix.status_observation_revision_ids:
        raise CanonicalizationError(
            "status evidence is present although the price policy does not require it"
        )
    if (
        prefix.health is PrefixHealth.HEALTHY
        and prefix.vintage is not PhysicalVintage.PROSPECTIVE_LIVE
    ):
        raise CanonicalizationError(
            "only prospective capture may be HEALTHY for trading"
        )
    allowed_policy_ids = {
        prefix.adapter_policy_id,
        *prefix.supporting_adapter_policy_ids,
    }
    selected_segments: list[CaptureSegmentV3] = []
    for segment_id in prefix.capture_segment_ids:
        segment = segments.get(segment_id)
        if not isinstance(segment, CaptureSegmentV3):
            raise CanonicalizationError("evidence prefix capture segment is missing")
        if segment.adapter_policy_id not in allowed_policy_ids:
            raise CanonicalizationError("evidence prefix contains a foreign segment")
        segment_policy = policies[segment.adapter_policy_id]
        if segment.provider_native_key != segment_policy.provider_native_key:
            raise CanonicalizationError("evidence prefix contains a foreign instrument")
        selected_segments.append(segment)
    present_policy_ids = {item.adapter_policy_id for item in selected_segments}
    if present_policy_ids != allowed_policy_ids:
        raise CanonicalizationError(
            "evidence prefix does not bind every declared adapter capture"
        )
    segments_by_partition: dict[str, list[CaptureSegmentV3]] = {}
    for segment in selected_segments:
        segments_by_partition.setdefault(segment.capture_partition_id, []).append(
            segment
        )
    for partition_segments in segments_by_partition.values():
        partition_segments.sort(key=lambda item: item.envelopes[0].collector_sequence)
        for left, right in zip(partition_segments, partition_segments[1:]):
            if right.parent_capture_segment_id != left.capture_segment_id:
                raise CanonicalizationError(
                    "evidence prefix segment chain is not contiguous"
                )
    if any(segment.vintage is not prefix.vintage for segment in selected_segments):
        raise CanonicalizationError("evidence prefix mixes physical vintages")
    selected_segment_ids = {item.capture_segment_id for item in selected_segments}
    expected_message_occurrences = tuple(
        envelope.message_receipt_id
        for segment in selected_segments
        for envelope in segment.envelopes
    )
    expected_message_ids = set(expected_message_occurrences)
    if len(expected_message_ids) != len(expected_message_occurrences):
        raise CanonicalizationError(
            "evidence prefix repeats a captured message occurrence"
        )
    selected_dispositions: dict[str, ProviderMessageDispositionV3] = {}
    dispositions_by_message: dict[str, list[ProviderMessageDispositionV3]] = {}
    for disposition_id in prefix.message_disposition_ids:
        disposition = dispositions.get(disposition_id)
        if not isinstance(disposition, ProviderMessageDispositionV3):
            raise CanonicalizationError(
                "evidence prefix message disposition is missing"
            )
        if disposition.provider_message_disposition_id != disposition_id:
            raise CanonicalizationError(
                "evidence prefix disposition registry key is incorrect"
            )
        if (
            disposition.adapter_policy_id not in allowed_policy_ids
            or disposition.capture_segment_id not in selected_segment_ids
        ):
            raise CanonicalizationError(
                "evidence prefix contains a foreign message disposition"
            )
        if disposition.classified_at > prefix.knowledge_cutoff_ts:
            raise CanonicalizationError(
                "evidence prefix contains a future message disposition"
            )
        segment = segments[disposition.capture_segment_id]
        envelope = _segment_envelope(segment, disposition.message_receipt_id)
        if envelope.raw_payload_sha256 != disposition.raw_payload_sha256:
            raise CanonicalizationError(
                "evidence prefix disposition raw hash differs from capture"
            )
        selected_dispositions[disposition_id] = disposition
        dispositions_by_message.setdefault(disposition.message_receipt_id, []).append(
            disposition
        )
    if set(dispositions_by_message) != expected_message_ids or any(
        len(items) != 1 for items in dispositions_by_message.values()
    ):
        raise CanonicalizationError(
            "evidence prefix must classify every captured message exactly once"
        )
    normalized_revision_ids = {
        item.observation_revision_id
        for item in selected_dispositions.values()
        if item.disposition_kind is MessageDispositionKind.NORMALIZED_OBSERVATION
    }
    if normalized_revision_ids != set(prefix.observation_revision_ids):
        raise CanonicalizationError(
            "evidence prefix revisions differ from normalized message dispositions"
        )
    for disposition in selected_dispositions.values():
        if disposition.disposition_kind is MessageDispositionKind.EXACT_DUPLICATE:
            if (
                disposition.duplicate_of_disposition_id not in selected_dispositions
                or disposition.duplicate_of_message_receipt_id
                not in expected_message_ids
            ):
                raise CanonicalizationError(
                    "duplicate disposition original is outside the evidence prefix"
                )
    unresolved_ids = unresolved_message_dispositions_v3(
        dispositions=selected_dispositions,
        segments={item.capture_segment_id: item for item in selected_segments},
        revisions=revisions,
        adapter_policies=policies,
        disposition_order=disposition_order,
    )
    if unresolved_ids != prefix.unresolved_disposition_ids:
        raise CanonicalizationError(
            "evidence prefix unresolved dispositions differ from deterministic recovery"
        )
    if unresolved_ids:
        unresolved_items = [selected_dispositions[item] for item in unresolved_ids]
        expected_health = _unresolved_disposition_health(
            unresolved_items,
            policies,
        )
        if prefix.health is not expected_health:
            raise CanonicalizationError(
                "evidence prefix health differs from unresolved message dispositions"
            )
        expected_reasons = canonical_reason_codes(
            tuple(
                {
                    "unresolved-"
                    + item.disposition_kind.value.lower().replace("_", "-")
                    for item in unresolved_items
                }
            ),
            field="health_reason_codes",
        )
        if prefix.health_reason_codes != expected_reasons:
            raise CanonicalizationError(
                "evidence prefix reasons differ from unresolved message dispositions"
            )
    selected_revisions: list[ObservationRevisionV3] = []
    for revision_id in prefix.observation_revision_ids:
        revision = revisions.get(revision_id)
        if not isinstance(revision, ObservationRevisionV3):
            raise CanonicalizationError(
                "evidence prefix observation revision is missing"
            )
        if revision.instrument_mapping_id != prefix.instrument_mapping_id:
            raise CanonicalizationError(
                "evidence prefix observation uses another instrument mapping"
            )
        is_status = revision_id in prefix.status_observation_revision_ids
        if is_status:
            if (
                revision.adapter_policy_id not in prefix.supporting_adapter_policy_ids
                or revision.observation_kind is not ObservationKind.INSTRUMENT_STATUS
            ):
                raise CanonicalizationError(
                    "evidence prefix contains invalid instrument-status evidence"
                )
            status_policy = policies[revision.adapter_policy_id]
            if (
                revision.completion_state is not CompletionState.COMPLETE
                or revision.completion_basis != status_policy.completion_basis
            ):
                raise CanonicalizationError(
                    "instrument-status evidence is not provider-final"
                )
        elif (
            revision.adapter_policy_id != prefix.adapter_policy_id
            or revision.observation_kind is not ObservationKind.BAR
        ):
            raise CanonicalizationError(
                "evidence prefix contains a foreign price revision"
            )
        if revision.source_member_key != prefix.source_member_key:
            raise CanonicalizationError(
                "evidence prefix contains a foreign member revision"
            )
        if revision.available_at > prefix.knowledge_cutoff_ts:
            raise CanonicalizationError("evidence prefix contains a future revision")
        selected_revisions.append(revision)
    expected_heads = tuple(
        item.observation_revision_id
        for item in active_revision_heads(selected_revisions)
    )
    if set(expected_heads) != set(prefix.active_observation_revision_ids):
        raise CanonicalizationError("evidence prefix active heads are incorrect")
    if prefix.health is PrefixHealth.HEALTHY:
        if adapter_policy.data_use is not ProviderDataUse.TRADING_AUTHORITY:
            raise CanonicalizationError(
                "non-authoritative provider cannot produce HEALTHY prefix"
            )
        if any(
            segment.clock_uncertainty_milliseconds
            > policies[segment.adapter_policy_id].max_clock_uncertainty_milliseconds
            for segment in selected_segments
        ):
            raise CanonicalizationError(
                "HEALTHY prefix exceeds clock uncertainty limit"
            )
        all_active_bars = [
            revision
            for revision in selected_revisions
            if revision.observation_revision_id
            in prefix.active_observation_revision_ids
            and revision.observation_kind is ObservationKind.BAR
        ]
        active_bars = [
            item
            for item in all_active_bars
            if item.completion_state is CompletionState.COMPLETE
        ]
        provisional_tail = [
            item
            for item in all_active_bars
            if item.completion_state is CompletionState.PROVISIONAL
        ]
        if not active_bars:
            raise CanonicalizationError(
                "HEALTHY prefix requires a completed active bar"
            )
        if any(
            item.completion_basis != adapter_policy.completion_basis
            for item in active_bars
        ):
            raise CanonicalizationError(
                "HEALTHY prefix contains a non-final active bar"
            )
        if len(active_bars) + len(provisional_tail) != len(all_active_bars):
            raise CanonicalizationError(
                "HEALTHY prefix contains a retracted or unknown active bar"
            )
        active_bars.sort(
            key=lambda item: (item.bar_open_ts, item.observation_revision_id)
        )
        if provisional_tail:
            if len(provisional_tail) != 1:
                raise CanonicalizationError(
                    "HEALTHY prefix permits at most one provisional tail bar"
                )
            tail = provisional_tail[0]
            if (
                tail.completion_basis is not CompletionBasis.NONE
                or tail.bar_open_ts != active_bars[-1].bar_close_ts
                or tail.bar_open_ts is None
                or tail.bar_close_ts is None
                or not tail.bar_open_ts
                <= prefix.knowledge_cutoff_ts
                < tail.bar_close_ts
            ):
                raise CanonicalizationError(
                    "HEALTHY prefix provisional bar is not the current contiguous tail"
                )
        if prefix.event_time_watermark != max(
            item.bar_close_ts for item in active_bars if item.bar_close_ts is not None
        ):
            raise CanonicalizationError(
                "evidence prefix watermark differs from active completed bars"
            )
        for left, right in zip(active_bars, active_bars[1:]):
            if left.bar_close_ts != right.bar_open_ts:
                raise CanonicalizationError(
                    "HEALTHY strict provider prefix contains a bar gap"
                )
        latest_market_close = max(
            item.bar_close_ts for item in active_bars if item.bar_close_ts is not None
        )
        health_expiries = [
            latest_market_close + timedelta(seconds=adapter_policy.stale_after_seconds)
        ]
        if (
            prefix.knowledge_cutoff_ts - latest_market_close
        ).total_seconds() > adapter_policy.stale_after_seconds:
            raise CanonicalizationError("HEALTHY prefix is stale")
        if adapter_policy.requires_instrument_status:
            statuses = [
                revisions[item]
                for item in prefix.status_observation_revision_ids
                if item in revisions
                and item in prefix.active_observation_revision_ids
                and revisions[item].observation_kind
                is ObservationKind.INSTRUMENT_STATUS
                and revisions[item].completion_state is CompletionState.COMPLETE
            ]
            if len(statuses) != 1:
                raise CanonicalizationError(
                    "HEALTHY prefix requires one active instrument status"
                )
            status = statuses[0]
            status_fields = dict(
                zip(status.field_ids, status.field_values, strict=True)
            )
            if status_fields.get("status") != "Trading":
                raise CanonicalizationError("HEALTHY prefix instrument is not Trading")
            if status_fields.get("contract_type") != "LinearPerpetual":
                raise CanonicalizationError(
                    "HEALTHY prefix status does not authorize the reviewed perpetual contract"
                )
            if status.source_publish_ts is None:
                raise CanonicalizationError(
                    "HEALTHY prefix status lacks a provider publication clock"
                )
            status_policy = policies[status.adapter_policy_id]
            if (
                prefix.knowledge_cutoff_ts - status.source_publish_ts
            ).total_seconds() > status_policy.stale_after_seconds:
                raise CanonicalizationError("HEALTHY prefix instrument status is stale")
            health_expiries.append(
                status.source_publish_ts
                + timedelta(seconds=status_policy.stale_after_seconds)
            )
        if prefix.health_valid_until != min(health_expiries):
            raise CanonicalizationError(
                "evidence prefix health validity differs from observed clocks"
            )
    if prefix.parent_evidence_prefix_id is not None:
        parent = parent_prefixes.get(prefix.parent_evidence_prefix_id)
        if not isinstance(parent, EvidencePrefixV3):
            raise CanonicalizationError("evidence prefix parent is missing")
        if (
            prefix.adapter_policy_id,
            prefix.source_member_key,
            prefix.instrument_mapping_id,
            prefix.ledger_id,
            prefix.supporting_adapter_policy_ids,
        ) != (
            parent.adapter_policy_id,
            parent.source_member_key,
            parent.instrument_mapping_id,
            parent.ledger_id,
            parent.supporting_adapter_policy_ids,
        ):
            raise CanonicalizationError("evidence prefix successor changes scope")
        if prefix.knowledge_cutoff_ts <= parent.knowledge_cutoff_ts:
            raise CanonicalizationError("evidence prefix cutoff must advance")
        if prefix.cutoff_global_sequence <= parent.cutoff_global_sequence:
            raise CanonicalizationError("evidence prefix ledger sequence must advance")
        if not set(parent.capture_segment_ids).issubset(prefix.capture_segment_ids):
            raise CanonicalizationError("evidence prefix removes captured segments")
        if not set(parent.message_disposition_ids).issubset(
            prefix.message_disposition_ids
        ):
            raise CanonicalizationError("evidence prefix removes message dispositions")
        if not set(parent.observation_revision_ids).issubset(
            prefix.observation_revision_ids
        ):
            raise CanonicalizationError("evidence prefix removes observation revisions")


def validate_source_member_physical_prefix(
    member: SourceBundleMemberV3,
    prefix: EvidencePrefixV3,
    revisions: Mapping[str, ObservationRevisionV3],
) -> None:
    """Bind an existing V3 source-member snapshot to its physical prefix."""

    if member.source_member_key != prefix.source_member_key:
        raise CanonicalizationError("source member key differs from physical prefix")
    if member.semantic_content_root != prefix.evidence_prefix_id:
        raise CanonicalizationError(
            "source member semantic root is not its physical prefix"
        )
    if member.artifact_hash != prefix.raw_receipt_root:
        raise CanonicalizationError(
            "source member artifact hash is not the raw receipt root"
        )
    if member.knowledge_cutoff_ts != prefix.knowledge_cutoff_ts:
        raise CanonicalizationError("source member cutoff differs from physical prefix")
    active_bars = [
        revisions[item]
        for item in prefix.active_observation_revision_ids
        if item in revisions
        and revisions[item].observation_kind is ObservationKind.BAR
        and revisions[item].completion_state is CompletionState.COMPLETE
    ]
    if member.row_count != len(active_bars):
        raise CanonicalizationError(
            "source member row_count differs from active physical bars"
        )
    if not active_bars:
        if member.event_start_ts is not None or member.event_end_ts is not None:
            raise CanonicalizationError("empty physical member declares event coverage")
        return
    start = min(item.source_event_ts for item in active_bars)
    end = max(item.source_event_ts for item in active_bars)
    if member.event_start_ts != start or member.event_end_ts != end:
        raise CanonicalizationError(
            "source member coverage differs from active physical bars"
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class DependencySelectionProofV3:
    """Recomputable exact/latest/trailing result against one closed prefix."""

    observation_selection_policy_id: str
    dependency_slot_id: str
    source_member_id: str
    source_member_key: str
    evidence_prefix_id: str
    observation_cutoff_ts: datetime
    status: SelectionStatus
    selected_observation_revision_ids: tuple[str, ...]
    abstention_reason_codes: tuple[str, ...]
    predecessor_boundary_revision_id: str | None
    successor_boundary_revision_id: str | None
    computed_at: datetime

    def __post_init__(self) -> None:
        for field_name in (
            "observation_selection_policy_id",
            "dependency_slot_id",
            "source_member_id",
            "source_member_key",
            "evidence_prefix_id",
        ):
            object.__setattr__(
                self,
                field_name,
                canonical_hash(getattr(self, field_name), field=field_name),
            )
        object.__setattr__(
            self, "status", _enum(self.status, SelectionStatus, field="status")
        )
        selected = _hashes(
            self.selected_observation_revision_ids,
            field="selected_observation_revision_ids",
            allow_empty=True,
        )
        reasons = canonical_reason_codes(
            self.abstention_reason_codes, field="abstention_reason_codes"
        )
        if self.status is SelectionStatus.SELECTED:
            if not selected or reasons:
                raise CanonicalizationError(
                    "SELECTED proof requires rows and no reasons"
                )
        elif selected or not reasons:
            raise CanonicalizationError(
                "ABSTAIN proof requires reasons and no selected rows"
            )
        object.__setattr__(self, "selected_observation_revision_ids", selected)
        object.__setattr__(self, "abstention_reason_codes", reasons)
        for field_name in (
            "predecessor_boundary_revision_id",
            "successor_boundary_revision_id",
        ):
            object.__setattr__(
                self,
                field_name,
                _optional_hash(getattr(self, field_name), field=field_name),
            )
        object.__setattr__(
            self,
            "observation_cutoff_ts",
            utc_datetime(self.observation_cutoff_ts, field="observation_cutoff_ts"),
        )
        object.__setattr__(
            self, "computed_at", utc_datetime(self.computed_at, field="computed_at")
        )
        if self.computed_at < self.observation_cutoff_ts:
            raise CanonicalizationError("selection proof computed before its cutoff")

    def identity_payload(self) -> dict[str, Any]:
        return {
            "abstention_reason_codes": list(self.abstention_reason_codes),
            "computed_at": utc_iso(self.computed_at),
            "dependency_slot_id": self.dependency_slot_id,
            "evidence_prefix_id": self.evidence_prefix_id,
            "observation_cutoff_ts": utc_iso(self.observation_cutoff_ts),
            "observation_selection_policy_id": self.observation_selection_policy_id,
            "predecessor_boundary_revision_id": self.predecessor_boundary_revision_id,
            "selected_observation_revision_ids": list(
                self.selected_observation_revision_ids
            ),
            "source_member_id": self.source_member_id,
            "source_member_key": self.source_member_key,
            "status": self.status.value,
            "successor_boundary_revision_id": self.successor_boundary_revision_id,
        }

    @property
    def dependency_selection_proof_id(self) -> str:
        return _identity("DependencySelectionProofV3", self.identity_payload())

    def as_dict(self) -> dict[str, Any]:
        return {
            "canonicalization_version": CANONICALIZATION_VERSION,
            **self.identity_payload(),
            "dependency_selection_proof_id": self.dependency_selection_proof_id,
            "schema_version": PHYSICAL_MARKET_DATA_SCHEMA_VERSION,
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> DependencySelectionProofV3:
        expected = set(cls.__dataclass_fields__) | {
            "canonicalization_version",
            "dependency_selection_proof_id",
            "schema_version",
        }
        require_exact_keys(
            payload, expected=expected, context="DependencySelectionProofV3"
        )
        _require_versions(payload)
        item = cls(**{name: payload[name] for name in cls.__dataclass_fields__})
        _require_digest(
            payload["dependency_selection_proof_id"],
            item.dependency_selection_proof_id,
            field="dependency_selection_proof_id",
        )
        return item


def select_observation_revisions_v3(
    *,
    policy: ObservationSelectionPolicyV3,
    slot: FeatureDependencySlotV3,
    member: SourceBundleMemberV3,
    prefix: EvidencePrefixV3,
    revisions: Mapping[str, ObservationRevisionV3],
    observation_cutoff_ts: datetime | str,
    computed_at: datetime | str,
) -> DependencySelectionProofV3:
    """Compute a fail-closed proof; caller cannot assert the selected list."""

    cutoff = utc_datetime(observation_cutoff_ts, field="observation_cutoff_ts")
    computed = utc_datetime(computed_at, field="computed_at")
    reasons: list[str] = []
    if policy.dependency_slot_id != slot.dependency_slot_id:
        raise CanonicalizationError("selection policy differs from dependency slot")
    if policy.selection_mode is not slot.selection_mode:
        raise CanonicalizationError("selection mode differs from dependency slot")
    if policy.maximum_age_seconds != slot.maximum_age_seconds:
        raise CanonicalizationError(
            "selection maximum age differs from dependency slot"
        )
    if not slot.minimum_count <= policy.requested_count <= slot.maximum_count:
        raise CanonicalizationError(
            "selection requested_count is outside slot cardinality"
        )
    if member.source_member_key != prefix.source_member_key:
        raise CanonicalizationError("selection member differs from evidence prefix")
    if prefix.knowledge_cutoff_ts > cutoff:
        reasons.append("prefix-known-after-selection-cutoff")
    elif (
        cutoff - prefix.knowledge_cutoff_ts
    ).total_seconds() > policy.maximum_prefix_age_seconds:
        reasons.append("physical-prefix-stale-at-selection-cutoff")
    if cutoff > prefix.health_valid_until:
        reasons.append("physical-prefix-health-expired")
    if computed > prefix.health_valid_until:
        reasons.append("physical-prefix-expired-before-selection")
    if computed < prefix.assembled_at:
        reasons.append("selection-computed-before-prefix-assembly")
    if prefix.health is not PrefixHealth.HEALTHY:
        reasons.append("physical-prefix-not-healthy")
    candidates = [
        revisions[item]
        for item in prefix.active_observation_revision_ids
        if item in revisions
        and revisions[item].observation_kind is ObservationKind.BAR
        and revisions[item].completion_state is CompletionState.COMPLETE
        and revisions[item].source_member_key == member.source_member_key
        and revisions[item].available_at <= cutoff
        and revisions[item].bar_close_ts is not None
        and revisions[item].bar_close_ts <= cutoff
    ]
    candidates.sort(
        key=lambda item: (
            item.bar_close_ts,
            item.available_at,
            item.observation_revision_id,
        )
    )
    interval = timedelta(seconds=policy.interval_seconds)
    if any(
        item.bar_open_ts is None
        or item.bar_close_ts is None
        or item.bar_close_ts - item.bar_open_ts != interval
        for item in candidates
    ):
        raise CanonicalizationError(
            "physical selection candidate interval differs from frozen policy"
        )
    epoch = datetime(1970, 1, 1, tzinfo=cutoff.tzinfo)
    elapsed = cutoff - epoch
    interval_microseconds = policy.interval_seconds * 1_000_000
    elapsed_microseconds = (
        elapsed.days * 86_400_000_000
        + elapsed.seconds * 1_000_000
        + elapsed.microseconds
    )
    completed_intervals = elapsed_microseconds // interval_microseconds
    target_close = epoch + timedelta(
        microseconds=(completed_intervals - policy.anchor_lag_intervals)
        * interval_microseconds
    )
    candidates = [item for item in candidates if item.bar_close_ts <= target_close]
    selected: list[ObservationRevisionV3] = []
    if not reasons:
        if policy.selection_mode is DependencySelectionMode.EXACT_EVENT:
            exact = [item for item in candidates if item.bar_close_ts == target_close]
            if len(exact) != 1:
                reasons.append("exact-event-missing-or-ambiguous")
            else:
                selected = exact
        elif policy.selection_mode is DependencySelectionMode.LATEST_AVAILABLE_ASOF:
            if not candidates:
                reasons.append("latest-selection-not-provable")
            else:
                selected = [candidates[-1]]
        else:
            selected = candidates[-policy.requested_count :]
            if len(selected) != policy.requested_count:
                reasons.append("trailing-window-short")
            elif policy.continuity_policy is ContinuityPolicy.STRICT_INTERVAL_GRID:
                for left, right in zip(selected, selected[1:]):
                    if left.bar_close_ts != right.bar_open_ts:
                        reasons.append("trailing-window-gapped")
                        break
            elif policy.continuity_policy is not ContinuityPolicy.SPARSE_WITH_LIVENESS:
                reasons.append("calendar-continuity-not-materialized")
        if selected and policy.maximum_age_seconds is not None:
            if (
                cutoff - selected[0].bar_close_ts
            ).total_seconds() > policy.maximum_age_seconds:
                reasons.append("selected-observation-too-old")
    selected_ids = tuple(item.observation_revision_id for item in selected)
    predecessor = None
    successor = None
    if selected_ids:
        first_index = candidates.index(selected[0])
        last_index = candidates.index(selected[-1])
        if first_index:
            predecessor = candidates[first_index - 1].observation_revision_id
        if last_index + 1 < len(candidates):
            successor = candidates[last_index + 1].observation_revision_id
    if reasons:
        selected_ids = ()
        predecessor = None
        successor = None
    return DependencySelectionProofV3(
        observation_selection_policy_id=policy.observation_selection_policy_id,
        dependency_slot_id=slot.dependency_slot_id,
        source_member_id=member.source_member_id,
        source_member_key=member.source_member_key,
        evidence_prefix_id=prefix.evidence_prefix_id,
        observation_cutoff_ts=cutoff,
        status=SelectionStatus.ABSTAIN if reasons else SelectionStatus.SELECTED,
        selected_observation_revision_ids=selected_ids,
        abstention_reason_codes=tuple(reasons),
        predecessor_boundary_revision_id=predecessor,
        successor_boundary_revision_id=successor,
        computed_at=computed,
    )


def validate_dependency_against_observation(
    dependency: InformationDependencyV3,
    revision: ObservationRevisionV3,
) -> None:
    """Require every duplicated logical clock/value to equal physical authority."""

    if dependency.observation_revision_id != revision.observation_revision_id:
        raise CanonicalizationError(
            "dependency observation revision differs from physical revision"
        )
    expected = {
        "source_id": revision.source_id,
        "source_event_ts": revision.source_event_ts,
        "bar_open_ts": revision.bar_open_ts,
        "bar_close_ts": revision.bar_close_ts,
        "source_publish_ts": revision.source_publish_ts,
        "ingested_first_seen_ts": revision.durably_appended_ts,
        "revision_received_ts": revision.durably_appended_ts,
        "feature_available_ts": revision.available_at,
    }
    for field_name, expected_value in expected.items():
        if getattr(dependency, field_name) != expected_value:
            raise CanonicalizationError(
                f"dependency {field_name} differs from physical observation"
            )
    values = dict(zip(revision.field_ids, revision.field_values))
    try:
        selected_values = tuple(values[field] for field in dependency.source_field_ids)
    except KeyError as exc:
        raise CanonicalizationError(
            "dependency requests absent physical field"
        ) from exc
    expected_digest = observation_value_digest(
        dependency.source_field_ids, selected_values
    )
    if dependency.value_digest != expected_digest:
        raise CanonicalizationError(
            "dependency value_digest differs from physical observation"
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class PhysicalEvidenceGateV3:
    """Decision/execution promotion result over exact physical selection proofs."""

    gate_stage: PhysicalGateStage
    information_set_id: str
    information_set_record_hash: str
    evidence_prefix_ids: tuple[str, ...]
    dependency_selection_proof_ids: tuple[str, ...]
    verdict: PhysicalGateVerdict
    abstention_reason_codes: tuple[str, ...]
    evaluated_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "gate_stage",
            _enum(self.gate_stage, PhysicalGateStage, field="gate_stage"),
        )
        for field_name in ("information_set_id", "information_set_record_hash"):
            object.__setattr__(
                self,
                field_name,
                canonical_hash(getattr(self, field_name), field=field_name),
            )
        object.__setattr__(
            self,
            "evidence_prefix_ids",
            _hashes(self.evidence_prefix_ids, field="evidence_prefix_ids"),
        )
        object.__setattr__(
            self,
            "dependency_selection_proof_ids",
            _hashes(
                self.dependency_selection_proof_ids,
                field="dependency_selection_proof_ids",
            ),
        )
        object.__setattr__(
            self, "verdict", _enum(self.verdict, PhysicalGateVerdict, field="verdict")
        )
        reasons = canonical_reason_codes(
            self.abstention_reason_codes, field="abstention_reason_codes"
        )
        if self.verdict is PhysicalGateVerdict.PASS:
            if reasons:
                raise CanonicalizationError("PASS physical gate cannot have reasons")
        elif not reasons:
            raise CanonicalizationError("ABSTAIN physical gate requires reasons")
        object.__setattr__(self, "abstention_reason_codes", reasons)
        object.__setattr__(
            self, "evaluated_at", utc_datetime(self.evaluated_at, field="evaluated_at")
        )

    def identity_payload(self) -> dict[str, Any]:
        return {
            "abstention_reason_codes": list(self.abstention_reason_codes),
            "dependency_selection_proof_ids": list(self.dependency_selection_proof_ids),
            "evaluated_at": utc_iso(self.evaluated_at),
            "evidence_prefix_ids": list(self.evidence_prefix_ids),
            "gate_stage": self.gate_stage.value,
            "information_set_id": self.information_set_id,
            "information_set_record_hash": self.information_set_record_hash,
            "verdict": self.verdict.value,
        }

    @property
    def physical_evidence_gate_id(self) -> str:
        return _identity("PhysicalEvidenceGateV3", self.identity_payload())

    def as_dict(self) -> dict[str, Any]:
        return {
            "canonicalization_version": CANONICALIZATION_VERSION,
            **self.identity_payload(),
            "physical_evidence_gate_id": self.physical_evidence_gate_id,
            "schema_version": PHYSICAL_MARKET_DATA_SCHEMA_VERSION,
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> PhysicalEvidenceGateV3:
        expected = set(cls.__dataclass_fields__) | {
            "canonicalization_version",
            "physical_evidence_gate_id",
            "schema_version",
        }
        require_exact_keys(payload, expected=expected, context="PhysicalEvidenceGateV3")
        _require_versions(payload)
        item = cls(**{name: payload[name] for name in cls.__dataclass_fields__})
        _require_digest(
            payload["physical_evidence_gate_id"],
            item.physical_evidence_gate_id,
            field="physical_evidence_gate_id",
        )
        return item


def build_physical_evidence_gate_v3(
    *,
    information_set: InformationSetV3,
    proofs: Sequence[DependencySelectionProofV3],
    prefixes: Mapping[str, EvidencePrefixV3],
    revisions: Mapping[str, ObservationRevisionV3],
    gate_stage: PhysicalGateStage = PhysicalGateStage.DECISION_INPUT,
    evaluated_at: datetime | str,
) -> PhysicalEvidenceGateV3:
    """Build the gate from proofs and verify exact equality with logical inputs."""

    proof_items = tuple(proofs)
    reasons: list[str] = []
    evaluated = utc_datetime(evaluated_at, field="evaluated_at")
    if not proof_items:
        reasons.append("physical-selection-proofs-missing")
    if information_set.vintage_class is not VintageClass.LIVE_FIRST_SEEN_CERTIFIED:
        reasons.append("information-vintage-not-live-first-seen")
    if not information_set.point_in_time_certified:
        reasons.append("information-set-not-point-in-time-certified")
    if any(item.status is not SelectionStatus.SELECTED for item in proof_items):
        reasons.append("dependency-selection-abstained")
    if any(
        item.observation_cutoff_ts != information_set.observation_cutoff_ts
        for item in proof_items
    ):
        reasons.append("selection-proof-cutoff-mismatch")
    proof_groups = [
        (item.dependency_slot_id, item.source_member_id) for item in proof_items
    ]
    if len(set(proof_groups)) != len(proof_groups):
        reasons.append("duplicate-physical-selection-group")
    prefix_ids = tuple(sorted({item.evidence_prefix_id for item in proof_items}))
    if any(
        item not in prefixes or prefixes[item].health is not PrefixHealth.HEALTHY
        for item in prefix_ids
    ):
        reasons.append("physical-prefix-not-healthy")
    if any(
        item in prefixes
        and prefixes[item].knowledge_cutoff_ts > information_set.observation_cutoff_ts
        for item in prefix_ids
    ):
        reasons.append("physical-prefix-known-after-information-cutoff")
    if (
        evaluated < information_set.assembled_at
        or any(evaluated < item.computed_at for item in proof_items)
        or any(
            item in prefixes and evaluated < prefixes[item].assembled_at
            for item in prefix_ids
        )
    ):
        reasons.append("physical-gate-evaluated-before-input-availability")
    if any(
        item in prefixes and evaluated > prefixes[item].health_valid_until
        for item in prefix_ids
    ):
        reasons.append("physical-prefix-expired-before-gate")
    expected_dependencies = {
        (
            item.dependency_slot_id,
            item.source_member_id,
            item.observation_revision_id,
        ): item
        for item in information_set.dependencies
    }
    selected_keys: set[tuple[str, str, str]] = set()
    for proof in proof_items:
        for revision_id in proof.selected_observation_revision_ids:
            key = (proof.dependency_slot_id, proof.source_member_id, revision_id)
            selected_keys.add(key)
            dependency = expected_dependencies.get(key)
            revision = revisions.get(revision_id)
            if dependency is None or revision is None:
                reasons.append("physical-selection-does-not-match-information")
                continue
            try:
                validate_dependency_against_observation(dependency, revision)
            except CanonicalizationError:
                reasons.append("physical-dependency-content-mismatch")
    if selected_keys != set(expected_dependencies):
        reasons.append("physical-selection-set-mismatch")
    reasons = sorted(set(reasons))
    return PhysicalEvidenceGateV3(
        gate_stage=gate_stage,
        information_set_id=information_set.information_set_id,
        information_set_record_hash=information_set.record_hash,
        evidence_prefix_ids=prefix_ids,
        dependency_selection_proof_ids=tuple(
            sorted(item.dependency_selection_proof_id for item in proof_items)
        ),
        verdict=PhysicalGateVerdict.ABSTAIN if reasons else PhysicalGateVerdict.PASS,
        abstention_reason_codes=tuple(reasons),
        evaluated_at=evaluated,
    )


def _millisecond_timestamp(value: Any, *, field: str) -> datetime:
    milliseconds = canonical_safe_int(value, field=field, minimum=0)
    seconds, remainder = divmod(milliseconds, 1000)
    from datetime import timezone

    return datetime.fromtimestamp(seconds, tz=timezone.utc) + timedelta(
        milliseconds=remainder
    )


def _segment_envelope(
    segment: CaptureSegmentV3, message_receipt_id: str
) -> ProviderMessageEnvelopeV3:
    identity = canonical_hash(message_receipt_id, field="message_receipt_id")
    matches = [
        item for item in segment.envelopes if item.message_receipt_id == identity
    ]
    if len(matches) != 1:
        raise CanonicalizationError(
            "message receipt must occur exactly once in capture segment"
        )
    return matches[0]


def _json_object(raw: bytes, *, context: str) -> Mapping[str, Any]:
    payload = strict_json_loads(raw)
    if not isinstance(payload, Mapping):
        raise CanonicalizationError(f"{context} must be a JSON object")
    return payload


def normalize_bybit_v5_kline_message(
    *,
    adapter_policy: ProviderAdapterPolicyV3,
    segment: CaptureSegmentV3,
    message_receipt_id: str,
    source_member_key: str,
    instrument_mapping_id: str,
    durably_appended_ts: datetime | str,
    normalized_at: datetime | str,
    available_at: datetime | str,
    parent_observation_revision_id: str | None = None,
    correction_reason: str | None = None,
) -> tuple[ObservationDerivationV3, ObservationRevisionV3]:
    """Decode one Bybit V5 kline payload without consulting future state."""

    if adapter_policy.adapter_kind is not ProviderAdapterKind.BYBIT_V5_PUBLIC_KLINE:
        raise CanonicalizationError("adapter policy is not Bybit V5 public kline")
    if segment.adapter_policy_id != adapter_policy.adapter_policy_id:
        raise CanonicalizationError("capture segment uses another adapter policy")
    if segment.provider_native_key != adapter_policy.provider_native_key:
        raise CanonicalizationError("capture segment uses another provider instrument")
    envelope = _segment_envelope(segment, message_receipt_id)
    if envelope.message_type is not ProviderMessageTypeV3.TEXT:
        raise CanonicalizationError(
            "Bybit kline normalization requires an exact TEXT provider frame"
        )
    payload = _json_object(envelope.raw_payload, context="Bybit kline message")
    require_exact_keys(
        payload,
        expected={"data", "topic", "ts", "type"},
        context="Bybit kline message",
    )
    if payload["topic"] != adapter_policy.channel_or_schema:
        raise CanonicalizationError("Bybit kline message has wrong topic")
    if payload["type"] != "snapshot":
        raise CanonicalizationError("Bybit kline message type is not snapshot")
    data = payload["data"]
    if not isinstance(data, list) or len(data) != 1 or not isinstance(data[0], Mapping):
        raise CanonicalizationError("Bybit kline message must contain one data record")
    row = data[0]
    require_exact_keys(
        row,
        expected={
            "close",
            "confirm",
            "end",
            "high",
            "interval",
            "low",
            "open",
            "start",
            "timestamp",
            "turnover",
            "volume",
        },
        context="Bybit kline data record",
    )
    if row["interval"] != "1":
        raise CanonicalizationError("initial Bybit adapter accepts only interval 1")
    if not isinstance(row["confirm"], bool):
        raise CanonicalizationError("Bybit confirm must be a boolean")
    bar_open = _millisecond_timestamp(row["start"], field="Bybit start")
    inclusive_end = _millisecond_timestamp(row["end"], field="Bybit end")
    bar_close = inclusive_end + timedelta(milliseconds=1)
    if bar_close - bar_open != timedelta(seconds=adapter_policy.base_interval_seconds):
        raise CanonicalizationError("Bybit kline interval boundaries are invalid")
    if bar_open.second or bar_open.microsecond:
        raise CanonicalizationError("Bybit one-minute bar is not UTC-minute aligned")
    source_event = _millisecond_timestamp(row["timestamp"], field="Bybit timestamp")
    provider_publish = _millisecond_timestamp(payload["ts"], field="Bybit ts")
    if not bar_open <= source_event < bar_close:
        raise CanonicalizationError("Bybit last-trade timestamp lies outside the bar")
    if row["confirm"] and provider_publish < bar_close:
        raise CanonicalizationError(
            "Bybit confirmed kline was generated before its bar closed"
        )
    for field_name, expected_value in (
        ("provider_generated_ts", provider_publish),
        ("provider_event_ts", source_event),
    ):
        supplied = getattr(envelope, field_name)
        if supplied is not None and supplied != expected_value:
            raise CanonicalizationError(
                f"capture envelope {field_name} differs from raw provider payload"
            )
    field_ids = ("open", "high", "low", "close", "volume", "turnover")
    field_values = tuple(
        canonical_decimal(
            row[name],
            field=name,
            strictly_positive=name in {"open", "high", "low", "close"},
            minimum=0 if name in {"volume", "turnover"} else None,
        )
        for name in field_ids
    )
    parameters_hash = sha256_digest(
        {
            "adapter_policy_id": adapter_policy.adapter_policy_id,
            "domain": "BybitV5PublicKlineParametersV1",
            "inclusive_end_to_half_open": "ADD_ONE_MILLISECOND",
            "parser_version": BYBIT_V5_KLINE_PARSER_VERSION,
        }
    )
    derivation = ObservationDerivationV3(
        adapter_policy_id=adapter_policy.adapter_policy_id,
        derivation_kind=DerivationKind.RAW_NORMALIZATION,
        input_message_receipt_ids=(envelope.message_receipt_id,),
        input_observation_revision_ids=(),
        transform_code_hash=adapter_policy.parser_code_hash,
        transform_parameters_hash=parameters_hash,
        interval_policy_id=sha256_digest({"domain": "HalfOpenUtcIntervalPolicyV1"}),
        numeric_policy_id=sha256_digest({"domain": "CanonicalDecimalOhlcvPolicyV1"}),
        sparse_interval_policy_id=sha256_digest(
            {"domain": "NoSyntheticMissingBarsPolicyV1"}
        ),
        calendar_manifest_id=adapter_policy.calendar_manifest_id,
        output_field_ids=field_ids,
        output_field_values=field_values,
        derived_at=normalized_at,
    )
    revision = ObservationRevisionV3(
        adapter_policy_id=adapter_policy.adapter_policy_id,
        source_member_key=source_member_key,
        instrument_mapping_id=instrument_mapping_id,
        source_id=adapter_policy.source_id,
        asset_id=adapter_policy.asset_id,
        venue_id=adapter_policy.venue_id,
        concrete_contract_id=adapter_policy.concrete_contract_id,
        timeframe_id=adapter_policy.timeframe_id,
        observation_name="provider-completed-ohlcv",
        observation_kind=ObservationKind.BAR,
        bar_open_ts=bar_open,
        bar_close_ts=bar_close,
        source_event_ts=source_event,
        source_publish_ts=provider_publish,
        durably_appended_ts=durably_appended_ts,
        normalized_at=normalized_at,
        available_at=available_at,
        completion_state=(
            CompletionState.COMPLETE if row["confirm"] else CompletionState.PROVISIONAL
        ),
        completion_basis=(
            CompletionBasis.PROVIDER_FINAL_FLAG
            if row["confirm"]
            else CompletionBasis.NONE
        ),
        observation_derivation_id=derivation.observation_derivation_id,
        field_ids=field_ids,
        field_values=field_values,
        parent_observation_revision_id=parent_observation_revision_id,
        correction_reason=correction_reason,
    )
    return derivation, revision


def normalize_bybit_v5_instrument_info(
    *,
    adapter_policy: ProviderAdapterPolicyV3,
    segment: CaptureSegmentV3,
    message_receipt_id: str,
    source_member_key: str,
    instrument_mapping_id: str,
    durably_appended_ts: datetime | str,
    normalized_at: datetime | str,
    available_at: datetime | str,
    parent_observation_revision_id: str | None = None,
    correction_reason: str | None = None,
) -> tuple[ObservationDerivationV3, ObservationRevisionV3]:
    """Normalize a prospective Bybit instruments-info response for one symbol."""

    if adapter_policy.adapter_kind is not ProviderAdapterKind.BYBIT_V5_INSTRUMENT_INFO:
        raise CanonicalizationError("adapter policy is not Bybit instruments-info")
    if segment.adapter_policy_id != adapter_policy.adapter_policy_id:
        raise CanonicalizationError("capture segment uses another status adapter")
    envelope = _segment_envelope(segment, message_receipt_id)
    if envelope.message_type is not ProviderMessageTypeV3.TEXT:
        raise CanonicalizationError(
            "Bybit instruments-info normalization requires an exact TEXT payload"
        )
    payload = _json_object(
        envelope.raw_payload, context="Bybit instruments-info response"
    )
    require_exact_keys(
        payload,
        expected={"result", "retCode", "retExtInfo", "retMsg", "time"},
        context="Bybit instruments-info response",
    )
    if payload["retCode"] != 0 or payload["retMsg"] != "OK":
        raise CanonicalizationError(
            "Bybit instruments-info response was not successful"
        )
    result = payload["result"]
    if not isinstance(result, Mapping):
        raise CanonicalizationError("Bybit instruments-info result must be an object")
    if result.get("category") != "linear" or not isinstance(result.get("list"), list):
        raise CanonicalizationError("Bybit instruments-info result has wrong category")
    matches = [
        row
        for row in result["list"]
        if isinstance(row, Mapping)
        and row.get("symbol") == adapter_policy.provider_native_key
    ]
    if len(matches) != 1:
        raise CanonicalizationError(
            "Bybit instruments-info must contain exactly one symbol"
        )
    row = matches[0]
    for required in ("symbol", "status", "contractType"):
        if required not in row:
            raise CanonicalizationError(f"Bybit instruments-info row lacks {required}")
    if row["contractType"] != "LinearPerpetual":
        raise CanonicalizationError(
            "Bybit instrument type differs from the reviewed perpetual contract"
        )
    provider_publish = _millisecond_timestamp(payload["time"], field="Bybit time")
    field_ids = ("status", "contract_type")
    field_values = (
        canonical_identifier(row["status"], field="status"),
        canonical_identifier(row["contractType"], field="contractType"),
    )
    derivation = ObservationDerivationV3(
        adapter_policy_id=adapter_policy.adapter_policy_id,
        derivation_kind=DerivationKind.RAW_NORMALIZATION,
        input_message_receipt_ids=(envelope.message_receipt_id,),
        input_observation_revision_ids=(),
        transform_code_hash=adapter_policy.parser_code_hash,
        transform_parameters_hash=sha256_digest(
            {"domain": "BybitV5InstrumentInfoParametersV1"}
        ),
        interval_policy_id=sha256_digest({"domain": "PointStatusIntervalPolicyV1"}),
        numeric_policy_id=sha256_digest({"domain": "ExactProviderStatusTextV1"}),
        sparse_interval_policy_id=sha256_digest({"domain": "StatusMustBeObservedV1"}),
        calendar_manifest_id=adapter_policy.calendar_manifest_id,
        output_field_ids=field_ids,
        output_field_values=field_values,
        derived_at=normalized_at,
    )
    revision = ObservationRevisionV3(
        adapter_policy_id=adapter_policy.adapter_policy_id,
        source_member_key=source_member_key,
        instrument_mapping_id=instrument_mapping_id,
        source_id=adapter_policy.source_id,
        asset_id=adapter_policy.asset_id,
        venue_id=adapter_policy.venue_id,
        concrete_contract_id=adapter_policy.concrete_contract_id,
        timeframe_id=adapter_policy.timeframe_id,
        observation_name="instrument-status",
        observation_kind=ObservationKind.INSTRUMENT_STATUS,
        bar_open_ts=None,
        bar_close_ts=None,
        source_event_ts=provider_publish,
        source_publish_ts=provider_publish,
        durably_appended_ts=durably_appended_ts,
        normalized_at=normalized_at,
        available_at=available_at,
        completion_state=CompletionState.COMPLETE,
        completion_basis=CompletionBasis.PROVIDER_FINAL_RECORD,
        observation_derivation_id=derivation.observation_derivation_id,
        field_ids=field_ids,
        field_values=field_values,
        parent_observation_revision_id=parent_observation_revision_id,
        correction_reason=correction_reason,
    )
    return derivation, revision


def _classifier_release_hash(policy: ProviderAdapterPolicyV3) -> str:
    if policy.adapter_kind is ProviderAdapterKind.BYBIT_V5_PUBLIC_KLINE:
        return BYBIT_V5_KLINE_CLASSIFIER_RELEASE_HASH
    if policy.adapter_kind is ProviderAdapterKind.BYBIT_V5_INSTRUMENT_INFO:
        return BYBIT_V5_INSTRUMENT_INFO_CLASSIFIER_RELEASE_HASH
    raise CanonicalizationError("unsupported provider message classifier")


def _provider_message_disposition(
    *,
    policy: ProviderAdapterPolicyV3,
    segment: CaptureSegmentV3,
    envelope: ProviderMessageEnvelopeV3,
    disposition_kind: MessageDispositionKind,
    classified_at: datetime,
    derivation: ObservationDerivationV3 | None = None,
    revision: ObservationRevisionV3 | None = None,
    duplicate_of: ProviderMessageDispositionV3 | None = None,
    provider_diagnostic_code: str | None = None,
    provider_diagnostic_digest: str | None = None,
) -> ProviderMessageDispositionV3:
    return ProviderMessageDispositionV3(
        adapter_policy_id=policy.adapter_policy_id,
        capture_segment_id=segment.capture_segment_id,
        message_receipt_id=envelope.message_receipt_id,
        raw_payload_sha256=envelope.raw_payload_sha256,
        disposition_kind=disposition_kind,
        classifier_release_hash=_classifier_release_hash(policy),
        classified_at=classified_at,
        observation_derivation_id=(
            None if derivation is None else derivation.observation_derivation_id
        ),
        observation_revision_id=(
            None if revision is None else revision.observation_revision_id
        ),
        duplicate_of_message_receipt_id=(
            None if duplicate_of is None else duplicate_of.message_receipt_id
        ),
        duplicate_of_disposition_id=(
            None
            if duplicate_of is None
            else duplicate_of.provider_message_disposition_id
        ),
        provider_diagnostic_code=provider_diagnostic_code,
        provider_diagnostic_digest=provider_diagnostic_digest,
    )


def _provider_error_disposition(
    *,
    policy: ProviderAdapterPolicyV3,
    segment: CaptureSegmentV3,
    envelope: ProviderMessageEnvelopeV3,
    classified_at: datetime,
    code: str,
    diagnostic: Mapping[str, Any],
) -> ProviderMessageDispositionV3:
    return _provider_message_disposition(
        policy=policy,
        segment=segment,
        envelope=envelope,
        disposition_kind=MessageDispositionKind.PROVIDER_ERROR,
        classified_at=classified_at,
        provider_diagnostic_code=code,
        provider_diagnostic_digest=sha256_digest(
            {
                "adapter_kind": policy.adapter_kind.value,
                "diagnostic": dict(diagnostic),
                "domain": "BybitProviderMessageDiagnosticV1",
            }
        ),
    )


def _raw_timing_disposition(
    *,
    policy: ProviderAdapterPolicyV3,
    segment: CaptureSegmentV3,
    envelope: ProviderMessageEnvelopeV3,
    provider_publish_ts: datetime,
    durably_appended_ts: datetime,
) -> MessageDispositionKind | None:
    uncertainty = segment.clock_uncertainty_milliseconds
    if (
        durably_appended_ts - envelope.collector_received_wall_ts
    ).total_seconds() * 1000 < -uncertainty:
        return MessageDispositionKind.CLOCK_ORDERING_REJECTED
    measured_lag = (durably_appended_ts - provider_publish_ts).total_seconds() * 1000
    if measured_lag < -uncertainty:
        return MessageDispositionKind.CLOCK_ORDERING_REJECTED
    if measured_lag > policy.max_receipt_lag_milliseconds + uncertainty:
        return MessageDispositionKind.RECEIPT_LAG_REJECTED
    return None


def _earliest_exact_normalized_occurrence(
    *,
    policy: ProviderAdapterPolicyV3,
    envelope: ProviderMessageEnvelopeV3,
    prior_normalized_occurrences: Sequence[
        tuple[CaptureSegmentV3, ProviderMessageDispositionV3]
    ],
) -> ProviderMessageDispositionV3 | None:
    """Return the first exact normalized occurrence in caller-supplied causal order."""

    seen: set[str] = set()
    for prior_segment, disposition in prior_normalized_occurrences:
        if not isinstance(prior_segment, CaptureSegmentV3) or not isinstance(
            disposition, ProviderMessageDispositionV3
        ):
            raise CanonicalizationError(
                "prior normalized occurrences contain invalid records"
            )
        if disposition.provider_message_disposition_id in seen:
            raise CanonicalizationError(
                "prior normalized occurrences contain duplicate dispositions"
            )
        seen.add(disposition.provider_message_disposition_id)
        if (
            prior_segment.adapter_policy_id != policy.adapter_policy_id
            or disposition.adapter_policy_id != policy.adapter_policy_id
            or disposition.capture_segment_id != prior_segment.capture_segment_id
            or disposition.disposition_kind
            is not MessageDispositionKind.NORMALIZED_OBSERVATION
        ):
            raise CanonicalizationError(
                "prior normalized occurrence changes classifier scope"
            )
        prior_envelope = _segment_envelope(
            prior_segment, disposition.message_receipt_id
        )
        if disposition.raw_payload_sha256 != prior_envelope.raw_payload_sha256:
            raise CanonicalizationError(
                "prior disposition raw hash differs from its envelope"
            )
        if prior_envelope.message_receipt_id == envelope.message_receipt_id:
            raise CanonicalizationError(
                "prior normalized occurrence cannot contain the current message"
            )
        if (
            prior_envelope.raw_payload_sha256 == envelope.raw_payload_sha256
            and prior_envelope.raw_payload == envelope.raw_payload
        ):
            return disposition
    return None


def _valid_bybit_linear_command_shape(payload: Mapping[str, Any]) -> bool:
    if set(payload) not in (
        {"conn_id", "op", "ret_msg", "success"},
        {"conn_id", "op", "req_id", "ret_msg", "success"},
    ):
        return False
    if (
        not isinstance(payload["success"], bool)
        or not isinstance(payload["conn_id"], str)
        or not payload["conn_id"]
        or not isinstance(payload["ret_msg"], str)
    ):
        return False
    return "req_id" not in payload or isinstance(payload["req_id"], str)


def build_bybit_v5_message_disposition(
    *,
    adapter_policy: ProviderAdapterPolicyV3,
    segment: CaptureSegmentV3,
    message_receipt_id: str,
    source_member_key: str,
    instrument_mapping_id: str,
    durably_appended_ts: datetime | str,
    normalized_at: datetime | str,
    available_at: datetime | str,
    classified_at: datetime | str,
    parent_observation_revision_id: str | None = None,
    correction_reason: str | None = None,
    prior_normalized_occurrences: Sequence[
        tuple[CaptureSegmentV3, ProviderMessageDispositionV3]
    ] = (),
) -> tuple[
    ProviderMessageDispositionV3,
    ObservationDerivationV3 | None,
    ObservationRevisionV3 | None,
]:
    """Exhaustively classify one captured Bybit occurrence without ignoring it.

    ``prior_normalized_occurrences`` must be supplied in causal capture order.
    The physical ledger is responsible for proving that order and completeness.
    Arbitrary bounded raw bytes classify as malformed or unsupported; only
    invalid caller-supplied scope/clock metadata raises.
    """

    if segment.adapter_policy_id != adapter_policy.adapter_policy_id:
        raise CanonicalizationError("capture segment uses another adapter policy")
    if segment.provider_native_key != adapter_policy.provider_native_key:
        raise CanonicalizationError("capture segment uses another provider instrument")
    envelope = _segment_envelope(segment, message_receipt_id)
    durable = utc_datetime(durably_appended_ts, field="durably_appended_ts")
    classified = utc_datetime(classified_at, field="classified_at")
    if classified < durable:
        raise CanonicalizationError("classified_at precedes durable capture append")

    if envelope.message_type is not ProviderMessageTypeV3.TEXT:
        return (
            _provider_message_disposition(
                policy=adapter_policy,
                segment=segment,
                envelope=envelope,
                disposition_kind=MessageDispositionKind.UNSUPPORTED_SCHEMA,
                classified_at=classified,
            ),
            None,
            None,
        )

    duplicate = _earliest_exact_normalized_occurrence(
        policy=adapter_policy,
        envelope=envelope,
        prior_normalized_occurrences=prior_normalized_occurrences,
    )
    if duplicate is not None:
        return (
            _provider_message_disposition(
                policy=adapter_policy,
                segment=segment,
                envelope=envelope,
                disposition_kind=MessageDispositionKind.EXACT_DUPLICATE,
                classified_at=classified,
                duplicate_of=duplicate,
            ),
            None,
            None,
        )

    try:
        payload = _json_object(envelope.raw_payload, context="Bybit provider message")
    except (CanonicalizationError, UnicodeError, ValueError):
        return (
            _provider_message_disposition(
                policy=adapter_policy,
                segment=segment,
                envelope=envelope,
                disposition_kind=MessageDispositionKind.MALFORMED_PAYLOAD,
                classified_at=classified,
            ),
            None,
            None,
        )

    if adapter_policy.adapter_kind is ProviderAdapterKind.BYBIT_V5_PUBLIC_KLINE:
        return _classify_bybit_v5_public_kline(
            policy=adapter_policy,
            segment=segment,
            envelope=envelope,
            payload=payload,
            source_member_key=source_member_key,
            instrument_mapping_id=instrument_mapping_id,
            durable=durable,
            normalized_at=normalized_at,
            available_at=available_at,
            classified=classified,
            parent_observation_revision_id=parent_observation_revision_id,
            correction_reason=correction_reason,
        )
    if adapter_policy.adapter_kind is ProviderAdapterKind.BYBIT_V5_INSTRUMENT_INFO:
        return _classify_bybit_v5_instrument_message(
            policy=adapter_policy,
            segment=segment,
            envelope=envelope,
            payload=payload,
            source_member_key=source_member_key,
            instrument_mapping_id=instrument_mapping_id,
            durable=durable,
            normalized_at=normalized_at,
            available_at=available_at,
            classified=classified,
            parent_observation_revision_id=parent_observation_revision_id,
            correction_reason=correction_reason,
        )
    raise CanonicalizationError("unsupported Bybit message classifier")


def _classify_bybit_v5_public_kline(
    *,
    policy: ProviderAdapterPolicyV3,
    segment: CaptureSegmentV3,
    envelope: ProviderMessageEnvelopeV3,
    payload: Mapping[str, Any],
    source_member_key: str,
    instrument_mapping_id: str,
    durable: datetime,
    normalized_at: datetime | str,
    available_at: datetime | str,
    classified: datetime,
    parent_observation_revision_id: str | None,
    correction_reason: str | None,
) -> tuple[
    ProviderMessageDispositionV3,
    ObservationDerivationV3 | None,
    ObservationRevisionV3 | None,
]:
    if "op" in payload:
        op = payload.get("op")
        if op not in {"subscribe", "ping"}:
            kind = MessageDispositionKind.OUT_OF_SCOPE
        elif not _valid_bybit_linear_command_shape(payload):
            kind = MessageDispositionKind.UNSUPPORTED_SCHEMA
        elif not payload["success"]:
            return (
                _provider_error_disposition(
                    policy=policy,
                    segment=segment,
                    envelope=envelope,
                    classified_at=classified,
                    code=f"WS_{str(op).upper()}_FAILED",
                    diagnostic={
                        "op": op,
                        "ret_msg": payload["ret_msg"],
                        "success": False,
                    },
                ),
                None,
                None,
            )
        elif op == "subscribe" and payload["ret_msg"] == "":
            kind = MessageDispositionKind.CONTROL_SUBSCRIPTION_ACK
        elif op == "ping" and payload["ret_msg"] == "pong":
            kind = MessageDispositionKind.CONTROL_PONG
        else:
            kind = MessageDispositionKind.CONTENT_CONFLICT
        return (
            _provider_message_disposition(
                policy=policy,
                segment=segment,
                envelope=envelope,
                disposition_kind=kind,
                classified_at=classified,
            ),
            None,
            None,
        )

    expected_top = {"data", "topic", "ts", "type"}
    if not expected_top.intersection(payload):
        kind = MessageDispositionKind.UNSUPPORTED_SCHEMA
        return (
            _provider_message_disposition(
                policy=policy,
                segment=segment,
                envelope=envelope,
                disposition_kind=kind,
                classified_at=classified,
            ),
            None,
            None,
        )
    if set(payload) != expected_top:
        kind = MessageDispositionKind.UNSUPPORTED_SCHEMA
    elif not isinstance(payload["topic"], str) or not isinstance(payload["type"], str):
        kind = MessageDispositionKind.MALFORMED_PAYLOAD
    elif payload["topic"] != policy.channel_or_schema:
        kind = MessageDispositionKind.OUT_OF_SCOPE
    elif payload["type"] != "snapshot":
        kind = MessageDispositionKind.UNSUPPORTED_SCHEMA
    else:
        data = payload["data"]
        if (
            not isinstance(data, list)
            or len(data) != 1
            or not isinstance(data[0], Mapping)
        ):
            kind = MessageDispositionKind.MALFORMED_PAYLOAD
        else:
            row = data[0]
            expected_row = {
                "close",
                "confirm",
                "end",
                "high",
                "interval",
                "low",
                "open",
                "start",
                "timestamp",
                "turnover",
                "volume",
            }
            if set(row) != expected_row:
                kind = MessageDispositionKind.UNSUPPORTED_SCHEMA
            elif row["interval"] != "1":
                kind = MessageDispositionKind.OUT_OF_SCOPE
            elif not isinstance(row["confirm"], bool):
                kind = MessageDispositionKind.MALFORMED_PAYLOAD
            else:
                try:
                    bar_open = _millisecond_timestamp(row["start"], field="Bybit start")
                    inclusive_end = _millisecond_timestamp(
                        row["end"], field="Bybit end"
                    )
                    bar_close = inclusive_end + timedelta(milliseconds=1)
                    event_ts = _millisecond_timestamp(
                        row["timestamp"], field="Bybit timestamp"
                    )
                    publish_ts = _millisecond_timestamp(payload["ts"], field="Bybit ts")
                    decimals = {
                        name: canonical_decimal(
                            row[name],
                            field=name,
                            strictly_positive=name in {"open", "high", "low", "close"},
                            minimum=0 if name in {"volume", "turnover"} else None,
                        )
                        for name in (
                            "open",
                            "high",
                            "low",
                            "close",
                            "volume",
                            "turnover",
                        )
                    }
                except (CanonicalizationError, OverflowError, OSError, ValueError):
                    kind = MessageDispositionKind.MALFORMED_PAYLOAD
                else:
                    prices = {
                        name: Decimal(decimals[name])
                        for name in ("open", "high", "low", "close")
                    }
                    if (
                        bar_close - bar_open
                        != timedelta(seconds=policy.base_interval_seconds)
                        or bar_open.second
                        or bar_open.microsecond
                    ):
                        kind = MessageDispositionKind.OUT_OF_SCOPE
                    elif not bar_open <= event_ts < bar_close:
                        kind = MessageDispositionKind.CONTENT_CONFLICT
                    elif row["confirm"] and publish_ts < bar_close:
                        kind = MessageDispositionKind.CONTENT_CONFLICT
                    elif prices["high"] < max(prices.values()) or prices["low"] > min(
                        prices.values()
                    ):
                        kind = MessageDispositionKind.CONTENT_CONFLICT
                    elif (
                        envelope.provider_generated_ts is not None
                        and envelope.provider_generated_ts != publish_ts
                    ) or (
                        envelope.provider_event_ts is not None
                        and envelope.provider_event_ts != event_ts
                    ):
                        kind = MessageDispositionKind.CONTENT_CONFLICT
                    else:
                        timing = _raw_timing_disposition(
                            policy=policy,
                            segment=segment,
                            envelope=envelope,
                            provider_publish_ts=publish_ts,
                            durably_appended_ts=durable,
                        )
                        if timing is not None:
                            kind = timing
                        else:
                            try:
                                derivation, revision = normalize_bybit_v5_kline_message(
                                    adapter_policy=policy,
                                    segment=segment,
                                    message_receipt_id=envelope.message_receipt_id,
                                    source_member_key=source_member_key,
                                    instrument_mapping_id=instrument_mapping_id,
                                    durably_appended_ts=durable,
                                    normalized_at=normalized_at,
                                    available_at=available_at,
                                    parent_observation_revision_id=(
                                        parent_observation_revision_id
                                    ),
                                    correction_reason=correction_reason,
                                )
                            except CanonicalizationError:
                                kind = MessageDispositionKind.CONTENT_CONFLICT
                            else:
                                return (
                                    _provider_message_disposition(
                                        policy=policy,
                                        segment=segment,
                                        envelope=envelope,
                                        disposition_kind=(
                                            MessageDispositionKind.NORMALIZED_OBSERVATION
                                        ),
                                        classified_at=classified,
                                        derivation=derivation,
                                        revision=revision,
                                    ),
                                    derivation,
                                    revision,
                                )
    return (
        _provider_message_disposition(
            policy=policy,
            segment=segment,
            envelope=envelope,
            disposition_kind=kind,
            classified_at=classified,
        ),
        None,
        None,
    )


def _classify_bybit_v5_instrument_message(
    *,
    policy: ProviderAdapterPolicyV3,
    segment: CaptureSegmentV3,
    envelope: ProviderMessageEnvelopeV3,
    payload: Mapping[str, Any],
    source_member_key: str,
    instrument_mapping_id: str,
    durable: datetime,
    normalized_at: datetime | str,
    available_at: datetime | str,
    classified: datetime,
    parent_observation_revision_id: str | None,
    correction_reason: str | None,
) -> tuple[
    ProviderMessageDispositionV3,
    ObservationDerivationV3 | None,
    ObservationRevisionV3 | None,
]:
    expected_top = {"result", "retCode", "retExtInfo", "retMsg", "time"}
    if set(payload) != expected_top:
        kind = MessageDispositionKind.UNSUPPORTED_SCHEMA
    elif (
        isinstance(payload["retCode"], bool)
        or not isinstance(payload["retCode"], int)
        or not isinstance(payload["retMsg"], str)
    ):
        kind = MessageDispositionKind.MALFORMED_PAYLOAD
    elif payload["retCode"] != 0 or payload["retMsg"] != "OK":
        code = f"REST_{payload['retCode']}"
        if payload["retCode"] == 0:
            code = "REST_0_UNEXPECTED_MESSAGE"
        return (
            _provider_error_disposition(
                policy=policy,
                segment=segment,
                envelope=envelope,
                classified_at=classified,
                code=code,
                diagnostic={
                    "retCode": payload["retCode"],
                    "retMsg": payload["retMsg"],
                },
            ),
            None,
            None,
        )
    elif not isinstance(payload["result"], Mapping):
        kind = MessageDispositionKind.MALFORMED_PAYLOAD
    else:
        result = payload["result"]
        rows = result.get("list")
        if result.get("category") != "linear":
            kind = MessageDispositionKind.OUT_OF_SCOPE
        elif not isinstance(rows, list) or any(
            not isinstance(row, Mapping) for row in rows
        ):
            kind = MessageDispositionKind.MALFORMED_PAYLOAD
        else:
            matches = [
                row for row in rows if row.get("symbol") == policy.provider_native_key
            ]
            if not matches:
                kind = MessageDispositionKind.EXPECTED_INSTRUMENT_STATUS_ABSENT
            elif len(matches) > 1:
                kind = MessageDispositionKind.CONTENT_CONFLICT
            elif not {"symbol", "status", "contractType"}.issubset(matches[0]):
                kind = MessageDispositionKind.UNSUPPORTED_SCHEMA
            elif matches[0]["contractType"] != "LinearPerpetual":
                kind = MessageDispositionKind.OUT_OF_SCOPE
            elif not isinstance(matches[0]["status"], str):
                kind = MessageDispositionKind.MALFORMED_PAYLOAD
            else:
                try:
                    publish_ts = _millisecond_timestamp(
                        payload["time"], field="Bybit time"
                    )
                except (CanonicalizationError, OverflowError, OSError, ValueError):
                    kind = MessageDispositionKind.MALFORMED_PAYLOAD
                else:
                    if (
                        envelope.provider_generated_ts is not None
                        and envelope.provider_generated_ts != publish_ts
                    ):
                        kind = MessageDispositionKind.CONTENT_CONFLICT
                    else:
                        timing = _raw_timing_disposition(
                            policy=policy,
                            segment=segment,
                            envelope=envelope,
                            provider_publish_ts=publish_ts,
                            durably_appended_ts=durable,
                        )
                        if timing is not None:
                            kind = timing
                        else:
                            try:
                                derivation, revision = (
                                    normalize_bybit_v5_instrument_info(
                                        adapter_policy=policy,
                                        segment=segment,
                                        message_receipt_id=envelope.message_receipt_id,
                                        source_member_key=source_member_key,
                                        instrument_mapping_id=instrument_mapping_id,
                                        durably_appended_ts=durable,
                                        normalized_at=normalized_at,
                                        available_at=available_at,
                                        parent_observation_revision_id=(
                                            parent_observation_revision_id
                                        ),
                                        correction_reason=correction_reason,
                                    )
                                )
                            except CanonicalizationError:
                                kind = MessageDispositionKind.CONTENT_CONFLICT
                            else:
                                return (
                                    _provider_message_disposition(
                                        policy=policy,
                                        segment=segment,
                                        envelope=envelope,
                                        disposition_kind=(
                                            MessageDispositionKind.NORMALIZED_OBSERVATION
                                        ),
                                        classified_at=classified,
                                        derivation=derivation,
                                        revision=revision,
                                    ),
                                    derivation,
                                    revision,
                                )
    return (
        _provider_message_disposition(
            policy=policy,
            segment=segment,
            envelope=envelope,
            disposition_kind=kind,
            classified_at=classified,
        ),
        None,
        None,
    )


def validate_raw_normalization_v3(
    *,
    policy: ProviderAdapterPolicyV3,
    segment: CaptureSegmentV3,
    derivation: ObservationDerivationV3,
    revision: ObservationRevisionV3,
) -> None:
    """Re-run the frozen parser and compare all provider-derived semantics."""

    if derivation.adapter_policy_id != policy.adapter_policy_id:
        raise CanonicalizationError("derivation adapter policy differs")
    if revision.adapter_policy_id != policy.adapter_policy_id:
        raise CanonicalizationError("observation adapter policy differs")
    if revision.observation_derivation_id != derivation.observation_derivation_id:
        raise CanonicalizationError("observation references another derivation")
    message_id = derivation.input_message_receipt_ids[0]
    envelope = _segment_envelope(segment, message_id)
    uncertainty = timedelta(milliseconds=segment.clock_uncertainty_milliseconds)
    if revision.durably_appended_ts + uncertainty < envelope.collector_received_wall_ts:
        raise CanonicalizationError(
            "observation durable append predates collector receipt"
        )
    common = {
        "adapter_policy": policy,
        "segment": segment,
        "message_receipt_id": message_id,
        "source_member_key": revision.source_member_key,
        "instrument_mapping_id": revision.instrument_mapping_id,
        "durably_appended_ts": revision.durably_appended_ts,
        "normalized_at": revision.normalized_at,
        "available_at": revision.available_at,
        "parent_observation_revision_id": revision.parent_observation_revision_id,
        "correction_reason": revision.correction_reason,
    }
    if policy.adapter_kind is ProviderAdapterKind.BYBIT_V5_PUBLIC_KLINE:
        expected_derivation, expected_revision = normalize_bybit_v5_kline_message(
            **common
        )
    elif policy.adapter_kind is ProviderAdapterKind.BYBIT_V5_INSTRUMENT_INFO:
        expected_derivation, expected_revision = normalize_bybit_v5_instrument_info(
            **common
        )
    else:  # pragma: no cover - enum construction makes this defensive
        raise CanonicalizationError("unsupported physical normalizer")
    provider_publish_ts = expected_revision.source_publish_ts
    if provider_publish_ts is None:  # pragma: no cover - supported adapters publish it
        raise CanonicalizationError(
            "physical authority requires a provider publication timestamp"
        )
    # ``durably_appended_ts`` is coupled to the ledger receipt for the capture
    # segment.  This check therefore cannot be bypassed by omitting optional
    # envelope metadata or by forging a collector wall-clock value.
    measured_lag = (
        revision.durably_appended_ts - provider_publish_ts
    ).total_seconds() * 1000
    if measured_lag < -segment.clock_uncertainty_milliseconds:
        raise CanonicalizationError("provider/ledger clock ordering is uncertain")
    if measured_lag > (
        policy.max_receipt_lag_milliseconds + segment.clock_uncertainty_milliseconds
    ):
        raise CanonicalizationError("provider message exceeded receipt-lag limit")
    if derivation != expected_derivation or revision != expected_revision:
        raise CanonicalizationError(
            "raw normalization differs from frozen parser output"
        )


__all__ = [
    "BYBIT_V5_FEED_HEALTH_POLICY_ID",
    "BYBIT_V5_FEED_HEALTH_POLICY_VERSION",
    "BYBIT_V5_INSTRUMENT_INFO_CLASSIFIER_RELEASE_HASH",
    "BYBIT_V5_INSTRUMENT_INFO_CLASSIFIER_VERSION",
    "BYBIT_V5_INSTRUMENT_INFO_PARSER_RELEASE_HASH",
    "BYBIT_V5_INSTRUMENT_INFO_PARSER_VERSION",
    "BYBIT_V5_KLINE_CLASSIFIER_RELEASE_HASH",
    "BYBIT_V5_KLINE_CLASSIFIER_VERSION",
    "BYBIT_V5_KLINE_PARSER_RELEASE_HASH",
    "BYBIT_V5_KLINE_PARSER_VERSION",
    "MAX_CAPTURE_CANONICAL_BYTES",
    "MAX_PREFIX_CANONICAL_BYTES",
    "PHYSICAL_MARKET_DATA_SCHEMA_VERSION",
    "CaptureSegmentV3",
    "CompletionBasis",
    "CompletionState",
    "ContinuityPolicy",
    "DependencySelectionProofV3",
    "DerivationKind",
    "EvidencePrefixV3",
    "MessageDispositionKind",
    "ObservationDerivationV3",
    "ObservationKind",
    "ObservationRevisionV3",
    "ObservationSelectionPolicyV3",
    "PhysicalEvidenceGateV3",
    "PhysicalGateStage",
    "PhysicalGateVerdict",
    "PhysicalVintage",
    "PrefixHealth",
    "ProviderAdapterKind",
    "ProviderAdapterPolicyV3",
    "ProviderDataUse",
    "ProviderMessageEnvelopeV3",
    "ProviderMessageDispositionV3",
    "ProviderMessageTypeV3",
    "ProviderTransport",
    "SelectionAnchor",
    "SelectionStatus",
    "active_revision_heads",
    "build_physical_evidence_gate_v3",
    "build_bybit_v5_message_disposition",
    "normalize_bybit_v5_instrument_info",
    "normalize_bybit_v5_kline_message",
    "observation_value_digest",
    "select_observation_revisions_v3",
    "unresolved_message_dispositions_v3",
    "validate_capture_segment_lineage",
    "validate_dependency_against_observation",
    "validate_evidence_prefix_graph",
    "validate_observation_revision_lineage",
    "validate_raw_normalization_v3",
    "validate_source_member_physical_prefix",
]
