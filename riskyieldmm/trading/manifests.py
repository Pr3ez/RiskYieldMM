"""Content-addressed manifests for causal trading experiments.

Each manifest kind has an exact, versioned payload schema.  The envelope is
small on purpose: semantically meaningful clocks belong inside the kind
payload and therefore inside ``manifest_id``.  Internally, payloads are stored
as canonical JSON text so a frozen dataclass cannot conceal a mutable mapping.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

from .calendar_actions import (
    ActionProtocolV3,
    ActionResolutionStatus,
    ActionResolutionV3,
    CalendarScheduleSnapshotV3,
    CalendarSourceArtifactV3,
    InstrumentMappingV3,
    validate_calendar_schedule_artifact_v3,
)
from .canonical import (
    CANONICALIZATION_VERSION,
    CanonicalizationError,
    canonical_hash,
    canonical_identifier,
    canonical_json_text,
    canonical_safe_int,
    require_exact_keys,
    sha256_digest,
    strict_json_loads,
    utc_datetime,
    utc_iso,
)
from .contracts import (
    CONTRACT_SCHEMA_VERSION,
    CandidateFeatureMaterializationV3,
    DecisionEventV3,
    EligibilityDecisionV3,
    EligibilityVerdict,
    EntryScenario,
    InformationSetV3,
    PrimarySignalCandidateV3,
    VintageClass,
    decode_float64_be_hex_null_v1,
)
from .evidence import (
    CardinalityScope,
    EvidenceKind,
    FeatureDefinitionV3,
    FeatureDependencySlotV3,
    FeatureRole,
    FeatureSchemaV3,
    MissingInputPolicy,
    SourceBundleMemberV3,
    SourceBundleV3,
    SourceRole,
    validate_feature_schema_graph,
    validate_source_bundle_graph,
)
from .physical_market_data import (
    ObservationSelectionPolicyV3,
    ProviderAdapterPolicyV3,
)

MANIFEST_SCHEMA_VERSION = "riskyieldmm_experiment_manifest_v1"
SUPPORTED_EVENT_SCHEMA_VERSION = CONTRACT_SCHEMA_VERSION


class ManifestType(str, Enum):
    """Manifest roles in the experiment-governance dependency graph."""

    SOURCE = "SOURCE"
    PROTOCOL = "PROTOCOL"
    SPLIT = "SPLIT"
    TRIAL_SPEC = "TRIAL_SPEC"
    TRIAL_RESULT = "TRIAL_RESULT"


_PAYLOAD_SCHEMA_VERSIONS = {
    ManifestType.SOURCE: "riskyieldmm_source_manifest_payload_v1",
    ManifestType.PROTOCOL: "riskyieldmm_protocol_manifest_payload_v1",
    ManifestType.SPLIT: "riskyieldmm_split_manifest_payload_v1",
    ManifestType.TRIAL_SPEC: "riskyieldmm_trial_spec_manifest_payload_v1",
    ManifestType.TRIAL_RESULT: "riskyieldmm_trial_result_manifest_payload_v1",
}

_PAYLOAD_KEYS = {
    ManifestType.SOURCE: frozenset(
        {
            "calendar_manifest_id",
            "first_seen_policy_id",
            "payload_schema_version",
            "parent_source_manifest_id",
            "revision_policy_id",
            "knowledge_cutoff_ts",
            "source_contract_id",
            "source_content_root",
            "source_dataset_id",
            "source_schema_id",
            "universe_manifest_id",
            "vintage_class",
        }
    ),
    ManifestType.PROTOCOL: frozenset(
        {
            "action_protocol_id",
            "barrier_policy_id",
            "calendar_manifest_id",
            "canonicalization_version",
            "code_tree_hash",
            "cost_scenario_id",
            "eligibility_policy_id",
            "environment_hash",
            "evaluation_governance_id",
            "event_schema_version",
            "feature_schema_id",
            "holdout_policy_id",
            "label_protocol_id",
            "payload_schema_version",
            "primary_metric_id",
            "primary_signal_policy_id",
            "protocol_frozen_at",
            "source_manifest_id",
            "source_contract_id",
            "split_policy_id",
            "universe_manifest_id",
            "workspace_state_hash",
        }
    ),
    ManifestType.SPLIT: frozenset(
        {
            "as_of_ts",
            "embargo_policy_id",
            "event_ledger_root",
            "fold_membership_hash",
            "holdout_policy_id",
            "cohort_class",
            "label_ledger_root",
            "payload_schema_version",
            "protocol_manifest_id",
            "purge_policy_id",
            "role_names",
            "source_manifest_id",
            "split_policy_id",
            "support_summary_hash",
        }
    ),
    ManifestType.TRIAL_SPEC: frozenset(
        {
            "calibration_spec_hash",
            "decision_policy_spec_hash",
            "hypothesis_family_id",
            "model_spec_hash",
            "parent_trial_spec_id",
            "payload_schema_version",
            "preprocessing_spec_hash",
            "protocol_manifest_id",
            "registered_at",
            "search_space_hash",
            "seed",
            "split_manifest_id",
            "trial_ordinal",
        }
    ),
    ManifestType.TRIAL_RESULT: frozenset(
        {
            "artifact_root_hash",
            "code_tree_hash",
            "completed_at",
            "failure_record_hash",
            "metrics_hash",
            "payload_schema_version",
            "prediction_ledger_hash",
            "protocol_manifest_id",
            "run_attempt_id",
            "runtime_environment_hash",
            "source_manifest_id",
            "started_at",
            "status",
            "split_manifest_id",
            "trial_spec_manifest_id",
            "workspace_state_hash",
        }
    ),
}

_HASH_FIELDS = {
    ManifestType.SOURCE: frozenset(
        {
            "calendar_manifest_id",
            "first_seen_policy_id",
            "source_contract_id",
            "revision_policy_id",
            "source_content_root",
            "source_schema_id",
            "universe_manifest_id",
        }
    ),
    ManifestType.PROTOCOL: frozenset(
        {
            "action_protocol_id",
            "barrier_policy_id",
            "calendar_manifest_id",
            "code_tree_hash",
            "cost_scenario_id",
            "eligibility_policy_id",
            "environment_hash",
            "evaluation_governance_id",
            "feature_schema_id",
            "holdout_policy_id",
            "label_protocol_id",
            "primary_metric_id",
            "primary_signal_policy_id",
            "source_manifest_id",
            "source_contract_id",
            "split_policy_id",
            "universe_manifest_id",
            "workspace_state_hash",
        }
    ),
    ManifestType.SPLIT: frozenset(
        {
            "embargo_policy_id",
            "event_ledger_root",
            "fold_membership_hash",
            "holdout_policy_id",
            "label_ledger_root",
            "protocol_manifest_id",
            "purge_policy_id",
            "source_manifest_id",
            "split_policy_id",
            "support_summary_hash",
        }
    ),
    ManifestType.TRIAL_SPEC: frozenset(
        {
            "calibration_spec_hash",
            "decision_policy_spec_hash",
            "model_spec_hash",
            "preprocessing_spec_hash",
            "protocol_manifest_id",
            "hypothesis_family_id",
            "search_space_hash",
            "split_manifest_id",
        }
    ),
    ManifestType.TRIAL_RESULT: frozenset(
        {
            "artifact_root_hash",
            "code_tree_hash",
            "failure_record_hash",
            "metrics_hash",
            "prediction_ledger_hash",
            "protocol_manifest_id",
            "runtime_environment_hash",
            "source_manifest_id",
            "split_manifest_id",
            "trial_spec_manifest_id",
            "workspace_state_hash",
        }
    ),
}

_TIMESTAMP_FIELDS = {
    ManifestType.SOURCE: frozenset({"knowledge_cutoff_ts"}),
    ManifestType.PROTOCOL: frozenset({"protocol_frozen_at"}),
    ManifestType.SPLIT: frozenset({"as_of_ts"}),
    ManifestType.TRIAL_SPEC: frozenset({"registered_at"}),
    ManifestType.TRIAL_RESULT: frozenset({"started_at", "completed_at"}),
}

_NULLABLE_HASH_FIELDS = frozenset(
    {
        "artifact_root_hash",
        "failure_record_hash",
        "metrics_hash",
        "parent_trial_spec_id",
        "parent_source_manifest_id",
        "prediction_ledger_hash",
    }
)

_VINTAGE_CLASSES = frozenset(
    {
        "LIVE_FIRST_SEEN_CERTIFIED",
        "HISTORICAL_AS_WAS_CERTIFIED",
        "NOMINAL_CURRENT_REVISION",
    }
)
_TRIAL_RESULT_STATUSES = frozenset({"SUCCEEDED", "FAILED", "INTERRUPTED"})
_COHORT_CLASSES = frozenset({"DEVELOPMENT", "QUARANTINE_CANDIDATE", "FINAL_HOLDOUT"})
_REQUIRED_SPLIT_ROLES = frozenset(
    {"TRAIN", "VALIDATION", "CALIBRATION", "POLICY", "TEST"}
)

EvidenceRecordV3 = (
    CalendarSourceArtifactV3
    | CalendarScheduleSnapshotV3
    | ActionProtocolV3
    | InstrumentMappingV3
    | SourceBundleMemberV3
    | SourceBundleV3
    | FeatureDependencySlotV3
    | FeatureDefinitionV3
    | FeatureSchemaV3
    | ProviderAdapterPolicyV3
    | ObservationSelectionPolicyV3
)


def derive_split_policy_id(
    *,
    purge_policy_id: str,
    embargo_policy_id: str,
    role_names: list[str] | tuple[str, ...],
) -> str:
    """Bind the split's purge, embargo, and role contracts into one policy ID."""

    roles = [canonical_identifier(value, field="role_names") for value in role_names]
    if len(set(roles)) != len(roles) or set(roles) != _REQUIRED_SPLIT_ROLES:
        raise CanonicalizationError(
            "role_names must contain TRAIN, VALIDATION, CALIBRATION, POLICY, and TEST"
        )
    return sha256_digest(
        {
            "canonicalization_version": CANONICALIZATION_VERSION,
            "domain": "SplitPolicyBindingV1",
            "embargo_policy_id": canonical_hash(
                embargo_policy_id, field="embargo_policy_id"
            ),
            "purge_policy_id": canonical_hash(purge_policy_id, field="purge_policy_id"),
            "role_names": sorted(roles),
        }
    )


@dataclass(frozen=True, slots=True, kw_only=True)
class ImmutableManifestV3:
    """A deeply immutable, exact-schema, content-addressed manifest."""

    manifest_type: ManifestType
    payload_json: str

    def __post_init__(self) -> None:
        try:
            manifest_type = (
                self.manifest_type
                if isinstance(self.manifest_type, ManifestType)
                else ManifestType(self.manifest_type)
            )
        except (TypeError, ValueError) as exc:
            allowed = ", ".join(item.value for item in ManifestType)
            raise CanonicalizationError(
                f"manifest_type must be one of: {allowed}"
            ) from exc
        if not isinstance(self.payload_json, (str, bytes, bytearray)):
            raise CanonicalizationError("payload_json must contain JSON text")
        raw_payload = strict_json_loads(self.payload_json)
        if not isinstance(raw_payload, Mapping):
            raise CanonicalizationError("manifest payload must be a JSON object")
        normalized = _normalize_payload(manifest_type, raw_payload)
        object.__setattr__(self, "manifest_type", manifest_type)
        object.__setattr__(self, "payload_json", canonical_json_text(normalized))

    @classmethod
    def create(
        cls,
        *,
        manifest_type: ManifestType | str,
        payload: Mapping[str, Any],
    ) -> ImmutableManifestV3:
        """Validate and canonicalize a new manifest payload."""

        if not isinstance(payload, Mapping):
            raise CanonicalizationError("manifest payload must be a mapping")
        return cls(
            manifest_type=manifest_type,
            payload_json=canonical_json_text(dict(payload)),
        )

    @property
    def payload(self) -> dict[str, Any]:
        """Return a fresh copy; callers cannot mutate the stored payload."""

        value = strict_json_loads(self.payload_json)
        assert isinstance(value, dict)
        return value

    def identity_payload(self) -> dict[str, Any]:
        return {
            "canonicalization_version": CANONICALIZATION_VERSION,
            "manifest_type": self.manifest_type.value,
            "payload": self.payload,
            "schema_version": MANIFEST_SCHEMA_VERSION,
        }

    @property
    def manifest_id(self) -> str:
        return sha256_digest(
            {
                "domain": "ImmutableManifestV3",
                "envelope": self.identity_payload(),
            }
        )

    def as_dict(self) -> dict[str, Any]:
        return {**self.identity_payload(), "manifest_id": self.manifest_id}

    @classmethod
    def from_mapping(cls, envelope: Mapping[str, Any]) -> ImmutableManifestV3:
        expected = {
            "canonicalization_version",
            "manifest_id",
            "manifest_type",
            "payload",
            "schema_version",
        }
        require_exact_keys(envelope, expected=expected, context="ImmutableManifestV3")
        if envelope["canonicalization_version"] != CANONICALIZATION_VERSION:
            raise CanonicalizationError("unsupported canonicalization_version")
        if envelope["schema_version"] != MANIFEST_SCHEMA_VERSION:
            raise CanonicalizationError("unsupported manifest schema_version")
        raw_payload = envelope["payload"]
        if not isinstance(raw_payload, Mapping):
            raise CanonicalizationError("manifest payload must be a JSON object")
        item = cls.create(
            manifest_type=envelope["manifest_type"],
            payload=raw_payload,
        )
        provided = canonical_hash(envelope["manifest_id"], field="manifest_id")
        if provided != item.manifest_id:
            raise CanonicalizationError("manifest_id does not match canonical content")
        return item


def _normalize_payload(
    manifest_type: ManifestType,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    require_exact_keys(
        payload,
        expected=set(_PAYLOAD_KEYS[manifest_type]),
        context=f"{manifest_type.value} manifest payload",
    )
    expected_schema = _PAYLOAD_SCHEMA_VERSIONS[manifest_type]
    if payload["payload_schema_version"] != expected_schema:
        raise CanonicalizationError(
            f"unsupported {manifest_type.value} payload_schema_version"
        )
    normalized = dict(payload)

    for field in _HASH_FIELDS[manifest_type]:
        value = normalized[field]
        if field in _NULLABLE_HASH_FIELDS and value is None:
            continue
        normalized[field] = canonical_hash(value, field=field)
    for field in _TIMESTAMP_FIELDS[manifest_type]:
        value = normalized[field]
        if value is None:
            raise CanonicalizationError(f"{field} must not be null")
        normalized[field] = utc_iso(value, field=field)

    if manifest_type is ManifestType.SOURCE:
        normalized["source_dataset_id"] = canonical_identifier(
            normalized["source_dataset_id"], field="source_dataset_id"
        )
        parent = normalized["parent_source_manifest_id"]
        if parent is not None:
            normalized["parent_source_manifest_id"] = canonical_hash(
                parent, field="parent_source_manifest_id"
            )
        _require_member(normalized["vintage_class"], _VINTAGE_CLASSES, "vintage_class")
    elif manifest_type is ManifestType.PROTOCOL:
        normalized["event_schema_version"] = canonical_identifier(
            normalized["event_schema_version"], field="event_schema_version"
        )
        if normalized["event_schema_version"] != SUPPORTED_EVENT_SCHEMA_VERSION:
            raise CanonicalizationError("unsupported event_schema_version")
        if normalized["canonicalization_version"] != CANONICALIZATION_VERSION:
            raise CanonicalizationError(
                "protocol canonicalization_version differs from envelope protocol"
            )
    elif manifest_type is ManifestType.SPLIT:
        roles = normalized["role_names"]
        if not isinstance(roles, list) or not roles:
            raise CanonicalizationError("role_names must be a non-empty JSON array")
        canonical_roles = [
            canonical_identifier(value, field="role_names") for value in roles
        ]
        if len(set(canonical_roles)) != len(canonical_roles):
            raise CanonicalizationError("role_names contain duplicate values")
        if set(canonical_roles) != _REQUIRED_SPLIT_ROLES:
            raise CanonicalizationError(
                "role_names must contain TRAIN, VALIDATION, CALIBRATION, POLICY, and TEST"
            )
        normalized["role_names"] = sorted(canonical_roles)
        expected_split_policy_id = derive_split_policy_id(
            purge_policy_id=normalized["purge_policy_id"],
            embargo_policy_id=normalized["embargo_policy_id"],
            role_names=canonical_roles,
        )
        if normalized["split_policy_id"] != expected_split_policy_id:
            raise CanonicalizationError(
                "split_policy_id does not bind purge, embargo, and role policies"
            )
        _require_member(normalized["cohort_class"], _COHORT_CLASSES, "cohort_class")
    elif manifest_type is ManifestType.TRIAL_SPEC:
        normalized["trial_ordinal"] = canonical_safe_int(
            normalized["trial_ordinal"], field="trial_ordinal", minimum=1
        )
        normalized["seed"] = canonical_safe_int(normalized["seed"], field="seed")
        parent = normalized["parent_trial_spec_id"]
        if parent is not None:
            normalized["parent_trial_spec_id"] = canonical_hash(
                parent, field="parent_trial_spec_id"
            )
    elif manifest_type is ManifestType.TRIAL_RESULT:
        normalized["run_attempt_id"] = canonical_identifier(
            normalized["run_attempt_id"], field="run_attempt_id"
        )
        _require_member(normalized["status"], _TRIAL_RESULT_STATUSES, "status")
        _validate_trial_result_lifecycle(normalized)
        if utc_datetime(
            normalized["completed_at"], field="completed_at"
        ) < utc_datetime(normalized["started_at"], field="started_at"):
            raise CanonicalizationError("completed_at must not precede started_at")

    return normalized


def _require_member(value: Any, allowed: frozenset[str], field: str) -> None:
    if not isinstance(value, str) or value not in allowed:
        choices = ", ".join(sorted(allowed))
        raise CanonicalizationError(f"{field} must be one of: {choices}")


def _validate_trial_result_lifecycle(payload: Mapping[str, Any]) -> None:
    artifact_fields = (
        "artifact_root_hash",
        "metrics_hash",
        "prediction_ledger_hash",
    )
    if payload["status"] == "SUCCEEDED":
        missing = [field for field in artifact_fields if payload[field] is None]
        if missing:
            raise CanonicalizationError(
                f"SUCCEEDED trial result is missing artifacts: {missing}"
            )
        if payload["failure_record_hash"] is not None:
            raise CanonicalizationError(
                "SUCCEEDED trial result must not contain failure_record_hash"
            )
    else:
        if payload["failure_record_hash"] is None:
            raise CanonicalizationError(
                "FAILED/INTERRUPTED trial result requires failure_record_hash"
            )


def validate_manifest_graph(
    manifest: ImmutableManifestV3,
    registry: Mapping[str, ImmutableManifestV3],
) -> None:
    """Validate a complete manifest DAG without Python call-stack recursion."""

    state: dict[str, int] = {}
    stack: list[tuple[ImmutableManifestV3, bool]] = [(manifest, False)]
    while stack:
        item, exiting = stack.pop()
        item_id = item.manifest_id
        if exiting:
            _validate_manifest_local(item, registry)
            state[item_id] = 2
            continue
        current_state = state.get(item_id, 0)
        if current_state == 2:
            continue
        if current_state == 1:
            raise CanonicalizationError("manifest dependency graph contains a cycle")
        state[item_id] = 1
        stack.append((item, True))
        dependencies = _manifest_dependencies(item, registry)
        for dependency in reversed(dependencies):
            stack.append((dependency, False))


def validate_manifest_evidence_graph(
    manifest: ImmutableManifestV3,
    registry: Mapping[str, ImmutableManifestV3],
    evidence_registry: Mapping[str, EvidenceRecordV3],
) -> None:
    """Validate manifest lineage plus every inspectable source/feature root.

    ``validate_manifest_graph`` intentionally remains the manifest-only layer.
    This stricter boundary resolves the content roots that SOURCE and PROTOCOL
    historically carried as opaque hashes.  Governance-ledger registration and
    all certified record validation use this function.
    """

    validate_manifest_graph(manifest, registry)
    seen: set[str] = set()
    stack = [manifest]
    while stack:
        item = stack.pop()
        if item.manifest_id in seen:
            continue
        seen.add(item.manifest_id)
        if item.manifest_type is ManifestType.SOURCE:
            validate_source_manifest_evidence_graph(
                source=item,
                registry=registry,
                evidence_registry=evidence_registry,
            )
        elif item.manifest_type is ManifestType.PROTOCOL:
            validate_protocol_manifest_evidence_graph(
                protocol=item,
                registry=registry,
                evidence_registry=evidence_registry,
            )
        stack.extend(_manifest_dependencies(item, registry))


def validate_source_manifest_evidence_graph(
    *,
    source: ImmutableManifestV3,
    registry: Mapping[str, ImmutableManifestV3],
    evidence_registry: Mapping[str, EvidenceRecordV3],
) -> None:
    """Resolve one SOURCE content root to an exact source-bundle graph."""

    if source.manifest_type is not ManifestType.SOURCE:
        raise CanonicalizationError("source evidence requires a SOURCE manifest")
    bundle = _resolve_evidence(
        evidence_registry,
        source.payload["source_content_root"],
        SourceBundleV3,
    )
    member_registry = {
        identity: item
        for identity, item in evidence_registry.items()
        if isinstance(item, SourceBundleMemberV3)
    }
    bundle_registry = {
        identity: item
        for identity, item in evidence_registry.items()
        if isinstance(item, SourceBundleV3)
    }
    parent_source_id = source.payload["parent_source_manifest_id"]
    if parent_source_id is not None:
        parent_source = _resolve_manifest(
            registry,
            parent_source_id,
            ManifestType.SOURCE,
        )
        _resolve_evidence(
            evidence_registry,
            parent_source.payload["source_content_root"],
            SourceBundleV3,
        )
    validate_source_bundle_graph(bundle, member_registry, bundle_registry)

    physical_policy = evidence_registry.get(bundle.source_contract_id)
    if physical_policy is not None:
        if not isinstance(physical_policy, ProviderAdapterPolicyV3):
            raise CanonicalizationError(
                "physical source contract resolves to an invalid adapter policy"
            )
        physical_bindings = {
            "source_schema_id": physical_policy.source_schema_id,
            "calendar_manifest_id": physical_policy.calendar_manifest_id,
            "first_seen_policy_id": physical_policy.availability_policy_id,
            "revision_policy_id": physical_policy.revision_policy_id,
        }
        for field, expected in physical_bindings.items():
            if getattr(bundle, field) != expected:
                raise CanonicalizationError(
                    f"physical source bundle {field} differs from adapter policy"
                )
        for member_id in bundle.source_member_ids:
            member = member_registry[member_id]
            expected_scope = (
                physical_policy.source_id,
                physical_policy.asset_id,
                physical_policy.venue_id,
                physical_policy.concrete_contract_id,
                physical_policy.timeframe_id,
                physical_policy.source_schema_id,
                physical_policy.availability_policy_id,
                physical_policy.revision_policy_id,
                physical_policy.calendar_manifest_id,
            )
            actual_scope = (
                member.source_id,
                member.asset_id,
                member.venue_id,
                member.contract_id,
                member.timeframe_id,
                member.source_schema_id,
                member.availability_policy_id,
                member.revision_policy_id,
                member.calendar_manifest_id,
            )
            if actual_scope != expected_scope:
                raise CanonicalizationError(
                    "physical source member scope differs from adapter policy"
                )

    payload = source.payload
    exact_bindings = {
        "source_dataset_id": payload["source_dataset_id"],
        "source_contract_id": payload["source_contract_id"],
        "source_schema_id": payload["source_schema_id"],
        "calendar_manifest_id": payload["calendar_manifest_id"],
        "universe_manifest_id": payload["universe_manifest_id"],
        "first_seen_policy_id": payload["first_seen_policy_id"],
        "revision_policy_id": payload["revision_policy_id"],
        "vintage_class": payload["vintage_class"],
    }
    for field, expected in exact_bindings.items():
        actual = getattr(bundle, field)
        if hasattr(actual, "value"):
            actual = actual.value
        if actual != expected:
            raise CanonicalizationError(
                f"SOURCE {field} differs from its source bundle"
            )
    if bundle.knowledge_cutoff_ts != utc_datetime(
        payload["knowledge_cutoff_ts"], field="knowledge_cutoff_ts"
    ):
        raise CanonicalizationError(
            "SOURCE knowledge_cutoff_ts differs from its source bundle"
        )
    expected_parent_bundle_id = (
        None
        if parent_source_id is None
        else _resolve_manifest(
            registry,
            parent_source_id,
            ManifestType.SOURCE,
        ).payload["source_content_root"]
    )
    if bundle.parent_source_bundle_id != expected_parent_bundle_id:
        raise CanonicalizationError(
            "SOURCE parent lineage differs from its source bundle"
        )


def validate_protocol_manifest_evidence_graph(
    *,
    protocol: ImmutableManifestV3,
    registry: Mapping[str, ImmutableManifestV3],
    evidence_registry: Mapping[str, EvidenceRecordV3],
) -> None:
    """Resolve a PROTOCOL feature-schema root and its exact definition DAG."""

    if protocol.manifest_type is not ManifestType.PROTOCOL:
        raise CanonicalizationError("feature evidence requires a PROTOCOL manifest")
    calendar = _resolve_evidence(
        evidence_registry,
        protocol.payload["calendar_manifest_id"],
        CalendarScheduleSnapshotV3,
    )
    artifact = _resolve_evidence(
        evidence_registry,
        calendar.calendar_source_artifact_id,
        CalendarSourceArtifactV3,
    )
    validate_calendar_schedule_artifact_v3(calendar, artifact)
    action_protocol = _resolve_evidence(
        evidence_registry,
        protocol.payload["action_protocol_id"],
        ActionProtocolV3,
    )
    if artifact.authority not in action_protocol.allowed_calendar_authorities:
        raise CanonicalizationError(
            "calendar source authority is not allowed by the action protocol"
        )
    protocol_frozen_at = utc_datetime(
        protocol.payload["protocol_frozen_at"], field="protocol_frozen_at"
    )
    if calendar.frozen_at > protocol_frozen_at:
        raise CanonicalizationError(
            "calendar snapshot was frozen after the experiment protocol"
        )
    if action_protocol.frozen_at > protocol_frozen_at:
        raise CanonicalizationError(
            "action protocol was frozen after the experiment protocol"
        )
    source = _resolve_manifest(
        registry,
        protocol.payload["source_manifest_id"],
        ManifestType.SOURCE,
    )
    validate_source_manifest_evidence_graph(
        source=source,
        registry=registry,
        evidence_registry=evidence_registry,
    )
    schema = _resolve_evidence(
        evidence_registry,
        protocol.payload["feature_schema_id"],
        FeatureSchemaV3,
    )
    slots = {
        slot_id: _resolve_evidence(
            evidence_registry,
            slot_id,
            FeatureDependencySlotV3,
        )
        for slot_id in schema.dependency_slot_ids
    }
    physical_policy = evidence_registry.get(source.payload["source_contract_id"])
    if isinstance(physical_policy, ProviderAdapterPolicyV3):
        selection_policies = [
            item
            for item in evidence_registry.values()
            if isinstance(item, ObservationSelectionPolicyV3)
        ]
        for slot in slots.values():
            if slot.evidence_kind is not EvidenceKind.OBSERVATION:
                continue
            if slot.cardinality_scope is not CardinalityScope.PER_SOURCE_MEMBER:
                raise CanonicalizationError(
                    "physical observation slots currently require per-source-member cardinality"
                )
            matching = [
                item
                for item in selection_policies
                if item.dependency_slot_id == slot.dependency_slot_id
            ]
            if len(matching) != 1:
                raise CanonicalizationError(
                    "physical observation slot requires exactly one selection policy"
                )
            selection = matching[0]
            if selection.selection_mode is not slot.selection_mode:
                raise CanonicalizationError(
                    "physical selection policy mode differs from dependency slot"
                )
            if selection.maximum_age_seconds != slot.maximum_age_seconds:
                raise CanonicalizationError(
                    "physical selection policy age differs from dependency slot"
                )
            if selection.interval_seconds != physical_policy.base_interval_seconds:
                raise CanonicalizationError(
                    "physical selection interval differs from adapter policy"
                )
            if (
                selection.maximum_prefix_age_seconds
                != physical_policy.stale_after_seconds
            ):
                raise CanonicalizationError(
                    "physical prefix age differs from adapter freshness policy"
                )
            if selection.frozen_at > protocol_frozen_at:
                raise CanonicalizationError(
                    "physical selection policy was frozen after the protocol"
                )
    definitions = {
        definition_id: _resolve_evidence(
            evidence_registry,
            definition_id,
            FeatureDefinitionV3,
        )
        for definition_id in schema.feature_definition_ids
    }
    source_bundle = _resolve_evidence(
        evidence_registry,
        source.payload["source_content_root"],
        SourceBundleV3,
    )
    member_registry = {
        identity: item
        for identity, item in evidence_registry.items()
        if isinstance(item, SourceBundleMemberV3)
    }
    bundle_registry = {
        identity: item
        for identity, item in evidence_registry.items()
        if isinstance(item, SourceBundleV3)
    }
    validate_feature_schema_graph(
        schema,
        slots,
        definitions,
        source_bundle,
        member_registry,
        bundle_registry,
    )
    if schema.source_contract_id != source.payload["source_contract_id"]:
        raise CanonicalizationError(
            "feature schema source_contract_id differs from protocol source"
        )
    if schema.source_schema_id != source.payload["source_schema_id"]:
        raise CanonicalizationError(
            "feature schema source_schema_id differs from protocol source"
        )
    if schema.frozen_at > utc_datetime(
        protocol.payload["protocol_frozen_at"], field="protocol_frozen_at"
    ):
        raise CanonicalizationError("feature schema was frozen after the protocol")


def validate_information_protocol_graph(
    *,
    protocol: ImmutableManifestV3,
    information_set: InformationSetV3,
    registry: Mapping[str, ImmutableManifestV3],
    evidence_registry: Mapping[str, EvidenceRecordV3],
) -> None:
    """Bind one information set to its source lineage and frozen protocol."""

    if protocol.manifest_type is not ManifestType.PROTOCOL:
        raise CanonicalizationError("record graph requires a PROTOCOL manifest")
    validate_manifest_evidence_graph(protocol, registry, evidence_registry)

    payload = protocol.payload
    if information_set.protocol_manifest_id != protocol.manifest_id:
        raise CanonicalizationError(
            "information set does not bind the supplied protocol manifest"
        )
    source = _resolve_manifest(
        registry,
        information_set.source_manifest_id,
        ManifestType.SOURCE,
    )
    validate_manifest_graph(source, registry)
    validate_source_manifest_evidence_graph(
        source=source,
        registry=registry,
        evidence_registry=evidence_registry,
    )
    _require_source_descendant(
        source,
        ancestor_id=payload["source_manifest_id"],
        registry=registry,
    )
    if information_set.observation_cutoff_ts > utc_datetime(
        source.payload["knowledge_cutoff_ts"],
        field="knowledge_cutoff_ts",
    ):
        raise CanonicalizationError(
            "information-set cutoff exceeds its source knowledge cutoff"
        )
    if information_set.vintage_class.value != source.payload["vintage_class"]:
        raise CanonicalizationError(
            "information-set vintage differs from its source manifest"
        )

    information_bindings = {
        "calendar_manifest_id": payload["calendar_manifest_id"],
        "feature_schema_id": payload["feature_schema_id"],
        "universe_snapshot_id": payload["universe_manifest_id"],
    }
    for field, expected in information_bindings.items():
        if getattr(information_set, field) != expected:
            raise CanonicalizationError(
                f"information-set {field} differs from its frozen protocol"
            )
    _validate_information_evidence_graph(
        protocol=protocol,
        information_set=information_set,
        source=source,
        evidence_registry=evidence_registry,
    )


def _validate_information_evidence_graph(
    *,
    protocol: ImmutableManifestV3,
    information_set: InformationSetV3,
    source: ImmutableManifestV3,
    evidence_registry: Mapping[str, EvidenceRecordV3],
) -> None:
    """Enforce exact source membership and finite feature-slot cardinality."""

    bundle = _resolve_evidence(
        evidence_registry,
        source.payload["source_content_root"],
        SourceBundleV3,
    )
    members = {
        member_id: _resolve_evidence(
            evidence_registry,
            member_id,
            SourceBundleMemberV3,
        )
        for member_id in bundle.source_member_ids
    }
    schema = _resolve_evidence(
        evidence_registry,
        information_set.feature_schema_id,
        FeatureSchemaV3,
    )
    slots = {
        slot_id: _resolve_evidence(
            evidence_registry,
            slot_id,
            FeatureDependencySlotV3,
        )
        for slot_id in schema.dependency_slot_ids
    }
    for definition_id in schema.feature_definition_ids:
        _resolve_evidence(
            evidence_registry,
            definition_id,
            FeatureDefinitionV3,
        )

    counts = dict.fromkeys(slots, 0)
    source_member_counts = {slot_id: {} for slot_id in slots}
    revision_keys: set[tuple[str, str, str]] = set()
    observation_keys: set[tuple[str, str, datetime, datetime, datetime]] = set()
    member_observation_revisions: dict[
        tuple[str, datetime, datetime, datetime], str
    ] = {}
    revision_coordinates: dict[tuple[str, str], tuple[object, ...]] = {}
    revision_field_values: dict[tuple[str, str, tuple[str, ...]], str] = {}
    for dependency in information_set.dependencies:
        slot = slots.get(dependency.dependency_slot_id)
        if slot is None:
            raise CanonicalizationError(
                "information dependency references an undeclared slot"
            )
        if slot.evidence_kind is not EvidenceKind.OBSERVATION:
            raise CanonicalizationError(
                "observation dependency is bound to a non-observation slot"
            )
        member = members.get(dependency.source_member_id)
        if member is None:
            raise CanonicalizationError(
                "information dependency references a foreign source member"
            )
        if member.source_role is not SourceRole.DECISION_INPUT:
            raise CanonicalizationError(
                "pre-decision dependency uses a forbidden source role"
            )
        if member.row_count == 0:
            raise CanonicalizationError(
                "realized observation cannot use an empty source member"
            )
        if member.source_member_key not in slot.source_member_keys:
            raise CanonicalizationError(
                "information dependency source member cannot satisfy its slot"
            )
        if dependency.source_id != member.source_id:
            raise CanonicalizationError(
                "information dependency source_id differs from its source member"
            )
        if dependency.source_field_ids != slot.source_field_ids:
            raise CanonicalizationError(
                "information dependency source fields differ from its slot"
            )
        if not set(dependency.source_field_ids).issubset(member.source_field_ids):
            raise CanonicalizationError(
                "information dependency requests fields absent from its source member"
            )
        if dependency.feature_available_ts > member.knowledge_cutoff_ts:
            raise CanonicalizationError(
                "information dependency postdates its source-member snapshot"
            )
        if dependency.source_event_ts > dependency.ingested_first_seen_ts:
            raise CanonicalizationError(
                "information dependency source_event_ts exceeds ingested_first_seen_ts"
            )
        if member.event_start_ts is not None and (
            dependency.source_event_ts < member.event_start_ts
            or dependency.source_event_ts > member.event_end_ts
        ):
            raise CanonicalizationError(
                "information dependency lies outside source-member coverage"
            )
        if (
            slot.maximum_age_seconds is not None
            and (
                information_set.observation_cutoff_ts - dependency.bar_close_ts
            ).total_seconds()
            > slot.maximum_age_seconds
        ):
            raise CanonicalizationError(
                "information dependency exceeds its slot maximum age"
            )
        revision_key = (
            dependency.dependency_slot_id,
            dependency.source_member_id,
            dependency.observation_revision_id,
        )
        if revision_key in revision_keys:
            raise CanonicalizationError(
                "information dependencies duplicate a slot observation revision"
            )
        revision_keys.add(revision_key)
        observation_key = (
            dependency.dependency_slot_id,
            dependency.source_member_id,
            dependency.source_event_ts,
            dependency.bar_open_ts,
            dependency.bar_close_ts,
        )
        if observation_key in observation_keys:
            raise CanonicalizationError(
                "information dependencies select multiple revisions of one "
                "slot observation"
            )
        observation_keys.add(observation_key)
        member_observation_key = (
            dependency.source_member_id,
            dependency.source_event_ts,
            dependency.bar_open_ts,
            dependency.bar_close_ts,
        )
        prior_revision = member_observation_revisions.get(member_observation_key)
        if (
            prior_revision is not None
            and prior_revision != dependency.observation_revision_id
        ):
            raise CanonicalizationError(
                "information dependencies select conflicting revisions of one "
                "source-member observation"
            )
        member_observation_revisions[member_observation_key] = (
            dependency.observation_revision_id
        )
        revision_coordinate_key = (
            dependency.source_member_id,
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
        prior_coordinates = revision_coordinates.get(revision_coordinate_key)
        if prior_coordinates is not None and prior_coordinates != coordinates:
            raise CanonicalizationError(
                "one source observation revision has conflicting coordinates"
            )
        revision_coordinates[revision_coordinate_key] = coordinates
        revision_field_key = (
            dependency.source_member_id,
            dependency.observation_revision_id,
            dependency.source_field_ids,
        )
        prior_value_digest = revision_field_values.get(revision_field_key)
        if (
            prior_value_digest is not None
            and prior_value_digest != dependency.value_digest
        ):
            raise CanonicalizationError(
                "one source observation revision and field set has conflicting "
                "value digests"
            )
        revision_field_values[revision_field_key] = dependency.value_digest
        counts[dependency.dependency_slot_id] += 1
        member_counts = source_member_counts[dependency.dependency_slot_id]
        member_counts[member.source_member_key] = (
            member_counts.get(member.source_member_key, 0) + 1
        )

    realized_rows_by_member = dict.fromkeys(members, 0)
    for member_id, _, _, _ in member_observation_revisions:
        realized_rows_by_member[member_id] += 1
    for member_id, realized_rows in realized_rows_by_member.items():
        if realized_rows > members[member_id].row_count:
            raise CanonicalizationError(
                "information dependencies exceed source-member row_count"
            )

    checkpoint_keys: set[tuple[str, str]] = set()
    for dependency in information_set.state_dependencies:
        slot = slots.get(dependency.dependency_slot_id)
        if slot is None:
            raise CanonicalizationError(
                "state dependency references an undeclared slot"
            )
        if slot.evidence_kind is not EvidenceKind.STATE_CHECKPOINT:
            raise CanonicalizationError("state dependency is bound to a non-state slot")
        if dependency.state_schema_id != slot.state_schema_id:
            raise CanonicalizationError("state dependency schema differs from its slot")
        if (
            slot.maximum_age_seconds is not None
            and (
                information_set.observation_cutoff_ts - dependency.state_cutoff_ts
            ).total_seconds()
            > slot.maximum_age_seconds
        ):
            raise CanonicalizationError("state dependency exceeds its slot maximum age")
        checkpoint_key = (
            dependency.dependency_slot_id,
            dependency.state_checkpoint_id,
        )
        if checkpoint_key in checkpoint_keys:
            raise CanonicalizationError(
                "state dependencies duplicate a slot checkpoint"
            )
        checkpoint_keys.add(checkpoint_key)
        counts[dependency.dependency_slot_id] += 1

    protocol_payload = protocol.payload
    for slot_id, slot in slots.items():
        if slot.evidence_kind is EvidenceKind.PROTOCOL_CONSTANT:
            missing = [
                field
                for field in slot.protocol_field_names
                if field not in protocol_payload
            ]
            if missing:
                raise CanonicalizationError(
                    f"protocol constant slot references unknown fields: {missing}"
                )
            counts[slot_id] = len(slot.protocol_field_names)
        if (
            slot.evidence_kind is EvidenceKind.OBSERVATION
            and slot.cardinality_scope is CardinalityScope.PER_SOURCE_MEMBER
        ):
            for member_key in slot.source_member_keys:
                member_count = source_member_counts[slot_id].get(member_key, 0)
                if member_count > slot.maximum_count or (
                    member_count < slot.minimum_count
                    and slot.missing_input_policy is MissingInputPolicy.FAIL
                ):
                    raise CanonicalizationError(
                        f"dependency slot {slot_id} source member {member_key} "
                        f"cardinality {member_count} is outside "
                        f"[{slot.minimum_count}, {slot.maximum_count}]"
                    )
        else:
            count = counts[slot_id]
            if count > slot.maximum_count or (
                count < slot.minimum_count
                and slot.missing_input_policy is MissingInputPolicy.FAIL
            ):
                raise CanonicalizationError(
                    f"dependency slot {slot_id} cardinality {count} is outside "
                    f"[{slot.minimum_count}, {slot.maximum_count}]"
                )


def validate_candidate_protocol_graph(
    *,
    protocol: ImmutableManifestV3,
    information_set: InformationSetV3,
    candidate: PrimarySignalCandidateV3,
    registry: Mapping[str, ImmutableManifestV3],
    evidence_registry: Mapping[str, EvidenceRecordV3],
) -> None:
    """Bind one pre-eligibility candidate to causal evidence and policies."""

    validate_information_protocol_graph(
        protocol=protocol,
        information_set=information_set,
        registry=registry,
        evidence_registry=evidence_registry,
    )
    candidate.validate_against(information_set)
    payload = protocol.payload
    if candidate.entry_scenario in {
        EntryScenario.FORWARD_MARKET_ORDER,
        EntryScenario.LIVE_MARKET_ORDER,
    }:
        if (
            information_set.vintage_class is not VintageClass.LIVE_FIRST_SEEN_CERTIFIED
            or not information_set.point_in_time_certified
        ):
            raise CanonicalizationError(
                "forward/live candidate requires certified live first-seen evidence"
            )
        if (
            utc_datetime(payload["protocol_frozen_at"], field="protocol_frozen_at")
            > information_set.observation_cutoff_ts
        ):
            raise CanonicalizationError(
                "forward/live candidate uses a protocol frozen after its observation "
                "cutoff"
            )
    policy_bindings = {
        "primary_signal_policy_id": candidate.primary_signal_policy_id,
        "action_protocol_id": candidate.action_protocol_id,
        "label_protocol_id": candidate.label_protocol_id,
        "barrier_policy_id": candidate.barrier_policy_id,
        "cost_scenario_id": candidate.cost_scenario_id,
    }
    for field, actual in policy_bindings.items():
        if actual != payload[field]:
            raise CanonicalizationError(
                f"candidate {field} differs from its frozen protocol"
            )


def validate_action_resolution_candidate_graph(
    *,
    information_set: InformationSetV3,
    candidate: PrimarySignalCandidateV3,
    action_resolution: ActionResolutionV3,
    evidence_registry: Mapping[str, EvidenceRecordV3],
) -> None:
    """Recompute and bind the scheduled action proof carried by a candidate."""

    calendar = _resolve_evidence(
        evidence_registry,
        action_resolution.calendar_snapshot_id,
        CalendarScheduleSnapshotV3,
    )
    calendar_artifact = _resolve_evidence(
        evidence_registry,
        calendar.calendar_source_artifact_id,
        CalendarSourceArtifactV3,
    )
    action_protocol = _resolve_evidence(
        evidence_registry,
        action_resolution.action_protocol_id,
        ActionProtocolV3,
    )
    mapping = _resolve_evidence(
        evidence_registry,
        action_resolution.instrument_mapping_id,
        InstrumentMappingV3,
    )
    action_resolution.validate_against(
        information_set=information_set,
        calendar_artifact=calendar_artifact,
        calendar=calendar,
        protocol=action_protocol,
        mapping=mapping,
    )
    if action_resolution.status is not ActionResolutionStatus.RESOLVED:
        raise CanonicalizationError(
            "only a RESOLVED action may create a primary-signal candidate"
        )
    expected = {
        "action_protocol_id": action_resolution.action_protocol_id,
        "action_resolution_id": action_resolution.action_resolution_id,
        "action_resolution_record_hash": action_resolution.record_hash,
        "asset_id": action_resolution.asset_id,
        "venue_id": action_resolution.venue_id,
        "contract_id": action_resolution.source_contract_id,
        "timeframe_id": action_resolution.timeframe_id,
        "primary_signal_id": action_resolution.primary_signal_id,
        "primary_signal_version": action_resolution.primary_signal_version,
        "primary_signal_policy_id": action_resolution.primary_signal_policy_id,
        "signal_ts": action_resolution.signal_ts,
        "side": action_resolution.side,
        "candidate_available_ts": action_resolution.resolved_at,
        "earliest_order_submission_ts": (
            action_resolution.earliest_order_submission_ts
        ),
        "earliest_entry_ts": action_resolution.earliest_entry_ts,
        "entry_expiry_ts": action_resolution.entry_expiry_ts,
        "entry_scenario": action_resolution.entry_scenario,
        "executable_contract_id": action_resolution.executable_contract_id,
    }
    for field, expected_value in expected.items():
        if getattr(candidate, field) != expected_value:
            raise CanonicalizationError(
                f"candidate {field} differs from its action resolution"
            )


def _missing_dependency_slot_ids(
    *,
    information_set: InformationSetV3,
    slots: Mapping[str, FeatureDependencySlotV3],
    evidence_registry: Mapping[str, EvidenceRecordV3],
) -> frozenset[str]:
    """Return non-FAIL slots whose declared evidence is absent or incomplete."""

    total_counts = dict.fromkeys(slots, 0)
    member_counts: dict[str, dict[str, int]] = {slot_id: {} for slot_id in slots}
    for dependency in information_set.dependencies:
        total_counts[dependency.dependency_slot_id] += 1
        member = _resolve_evidence(
            evidence_registry,
            dependency.source_member_id,
            SourceBundleMemberV3,
        )
        counts = member_counts[dependency.dependency_slot_id]
        counts[member.source_member_key] = counts.get(member.source_member_key, 0) + 1
    for dependency in information_set.state_dependencies:
        total_counts[dependency.dependency_slot_id] += 1

    missing: set[str] = set()
    for slot_id, slot in slots.items():
        if (
            slot.evidence_kind is EvidenceKind.PROTOCOL_CONSTANT
            or slot.missing_input_policy is MissingInputPolicy.FAIL
        ):
            continue
        if (
            slot.evidence_kind is EvidenceKind.OBSERVATION
            and slot.cardinality_scope is CardinalityScope.PER_SOURCE_MEMBER
        ):
            realized = tuple(
                member_counts[slot_id].get(member_key, 0)
                for member_key in slot.source_member_keys
            )
            is_missing = any(count < slot.minimum_count for count in realized)
        else:
            count = total_counts[slot_id]
            is_missing = count < slot.minimum_count
        if is_missing:
            missing.add(slot_id)
    return frozenset(missing)


def _feature_slot_ancestry(
    definitions: list[FeatureDefinitionV3],
) -> dict[str, frozenset[str]]:
    """Resolve direct and inherited dependency slots for ordered features."""

    ancestry: dict[str, frozenset[str]] = {}
    for definition in definitions:
        slots = set(definition.input_dependency_slot_ids)
        for parent_id in definition.derived_feature_ids:
            slots.update(ancestry[parent_id])
        ancestry[definition.feature_definition_id] = frozenset(slots)
    return ancestry


def validate_feature_materialization_protocol_graph(
    *,
    protocol: ImmutableManifestV3,
    information_set: InformationSetV3,
    candidate: PrimarySignalCandidateV3,
    feature_materialization: CandidateFeatureMaterializationV3,
    registry: Mapping[str, ImmutableManifestV3],
    evidence_registry: Mapping[str, EvidenceRecordV3],
) -> None:
    """Bind an exact ordered candidate vector to its inspectable schema."""

    validate_candidate_protocol_graph(
        protocol=protocol,
        information_set=information_set,
        candidate=candidate,
        registry=registry,
        evidence_registry=evidence_registry,
    )
    feature_materialization.validate_against(information_set, candidate)
    schema = _resolve_evidence(
        evidence_registry,
        feature_materialization.feature_schema_id,
        FeatureSchemaV3,
    )
    definitions = [
        _resolve_evidence(
            evidence_registry,
            definition_id,
            FeatureDefinitionV3,
        )
        for definition_id in schema.feature_definition_ids
    ]
    if feature_materialization.feature_count != len(definitions):
        raise CanonicalizationError(
            "candidate feature count differs from its feature schema"
        )
    slots = {
        slot_id: _resolve_evidence(
            evidence_registry,
            slot_id,
            FeatureDependencySlotV3,
        )
        for slot_id in schema.dependency_slot_ids
    }
    missing_slots = _missing_dependency_slot_ids(
        information_set=information_set,
        slots=slots,
        evidence_registry=evidence_registry,
    )
    slot_ancestry = _feature_slot_ancestry(definitions)
    for value, definition in zip(
        feature_materialization.feature_values,
        definitions,
        strict=True,
    ):
        if definition.feature_role is FeatureRole.MISSINGNESS_INDICATOR:
            indicator_slot_id = definition.input_dependency_slot_ids[0]
            expected_indicator = 1.0 if indicator_slot_id in missing_slots else 0.0
            if decode_float64_be_hex_null_v1(value) != expected_indicator:
                raise CanonicalizationError(
                    f"missingness indicator {definition.feature_name} must equal "
                    f"{expected_indicator:.1f}"
                )
            continue
        feature_missing_slots = slot_ancestry[
            definition.feature_definition_id
        ].intersection(missing_slots)
        if feature_missing_slots and value is not None:
            raise CanonicalizationError(
                f"feature {definition.feature_name} must be null when dependency "
                "evidence is missing"
            )
        if not feature_missing_slots and value is None and not definition.nullable:
            raise CanonicalizationError(
                f"non-nullable feature {definition.feature_name} is missing"
            )


def validate_eligibility_protocol_graph(
    *,
    protocol: ImmutableManifestV3,
    information_set: InformationSetV3,
    candidate: PrimarySignalCandidateV3,
    feature_materialization: CandidateFeatureMaterializationV3,
    eligibility: EligibilityDecisionV3,
    registry: Mapping[str, ImmutableManifestV3],
    evidence_registry: Mapping[str, EvidenceRecordV3],
) -> None:
    """Bind one eligibility decision to exact evidence, proposal, and vector."""

    validate_feature_materialization_protocol_graph(
        protocol=protocol,
        information_set=information_set,
        candidate=candidate,
        feature_materialization=feature_materialization,
        registry=registry,
        evidence_registry=evidence_registry,
    )
    eligibility.validate_against(
        information_set,
        candidate,
        feature_materialization,
    )
    if eligibility.eligibility_policy_id != protocol.payload["eligibility_policy_id"]:
        raise CanonicalizationError(
            "record eligibility_policy_id differs from its frozen protocol"
        )
    schema = _resolve_evidence(
        evidence_registry,
        information_set.feature_schema_id,
        FeatureSchemaV3,
    )
    slots = {
        slot_id: _resolve_evidence(
            evidence_registry,
            slot_id,
            FeatureDependencySlotV3,
        )
        for slot_id in schema.dependency_slot_ids
    }
    missing_slots = _missing_dependency_slot_ids(
        information_set=information_set,
        slots=slots,
        evidence_registry=evidence_registry,
    )
    missing_abstain_slots = {
        slot_id
        for slot_id in missing_slots
        if slots[slot_id].missing_input_policy is MissingInputPolicy.ABSTAIN
    }
    if (
        missing_abstain_slots
        and eligibility.verdict is not EligibilityVerdict.ABSTAIN_DATA
    ):
        raise CanonicalizationError(
            "missing ABSTAIN dependency evidence requires ABSTAIN_DATA verdict"
        )


def validate_record_protocol_graph(
    *,
    protocol: ImmutableManifestV3,
    information_set: InformationSetV3,
    candidate: PrimarySignalCandidateV3,
    feature_materialization: CandidateFeatureMaterializationV3,
    eligibility: EligibilityDecisionV3,
    event: DecisionEventV3,
    registry: Mapping[str, ImmutableManifestV3],
    evidence_registry: Mapping[str, EvidenceRecordV3],
) -> None:
    """Bind a validated causal record graph to one frozen protocol manifest."""

    validate_eligibility_protocol_graph(
        protocol=protocol,
        information_set=information_set,
        candidate=candidate,
        feature_materialization=feature_materialization,
        eligibility=eligibility,
        registry=registry,
        evidence_registry=evidence_registry,
    )
    event.validate_against(
        information_set,
        candidate,
        feature_materialization,
        eligibility,
    )

    payload = protocol.payload
    policy_bindings = {
        "primary_signal_policy_id": (
            event.primary_signal_policy_id,
            payload["primary_signal_policy_id"],
        ),
        "action_protocol_id": (
            event.action_protocol_id,
            payload["action_protocol_id"],
        ),
        "label_protocol_id": (
            event.label_protocol_id,
            payload["label_protocol_id"],
        ),
        "barrier_policy_id": (
            event.barrier_policy_id,
            payload["barrier_policy_id"],
        ),
        "cost_scenario_id": (
            event.cost_scenario_id,
            payload["cost_scenario_id"],
        ),
    }
    for field, (actual, expected) in policy_bindings.items():
        if actual != expected:
            raise CanonicalizationError(
                f"record {field} differs from its frozen protocol"
            )


def _manifest_dependencies(
    manifest: ImmutableManifestV3,
    registry: Mapping[str, ImmutableManifestV3],
) -> list[ImmutableManifestV3]:
    payload = manifest.payload
    if manifest.manifest_type is ManifestType.SOURCE:
        parent_id = payload["parent_source_manifest_id"]
        return (
            []
            if parent_id is None
            else [_resolve_manifest(registry, parent_id, ManifestType.SOURCE)]
        )
    if manifest.manifest_type is ManifestType.PROTOCOL:
        return [
            _resolve_manifest(
                registry,
                payload["source_manifest_id"],
                ManifestType.SOURCE,
            )
        ]
    if manifest.manifest_type is ManifestType.SPLIT:
        return [
            _resolve_manifest(
                registry,
                payload["protocol_manifest_id"],
                ManifestType.PROTOCOL,
            ),
            _resolve_manifest(
                registry,
                payload["source_manifest_id"],
                ManifestType.SOURCE,
            ),
        ]
    if manifest.manifest_type is ManifestType.TRIAL_SPEC:
        dependencies = [
            _resolve_manifest(
                registry,
                payload["protocol_manifest_id"],
                ManifestType.PROTOCOL,
            ),
            _resolve_manifest(
                registry,
                payload["split_manifest_id"],
                ManifestType.SPLIT,
            ),
        ]
        parent_id = payload["parent_trial_spec_id"]
        if parent_id is not None:
            dependencies.append(
                _resolve_manifest(registry, parent_id, ManifestType.TRIAL_SPEC)
            )
        return dependencies
    if manifest.manifest_type is ManifestType.TRIAL_RESULT:
        return [
            _resolve_manifest(
                registry,
                payload["trial_spec_manifest_id"],
                ManifestType.TRIAL_SPEC,
            ),
            _resolve_manifest(
                registry,
                payload["protocol_manifest_id"],
                ManifestType.PROTOCOL,
            ),
            _resolve_manifest(
                registry,
                payload["split_manifest_id"],
                ManifestType.SPLIT,
            ),
        ]
    raise CanonicalizationError("unsupported manifest type")


def _validate_manifest_local(
    manifest: ImmutableManifestV3,
    registry: Mapping[str, ImmutableManifestV3],
) -> None:
    """Resolve and validate all cross-manifest type, lineage, and clock links.

    This verifies declared content relationships.  A later append-only receipt
    ledger must separately prove when a manifest was first registered.
    """

    payload = manifest.payload
    if manifest.manifest_type is ManifestType.SOURCE:
        parent_id = payload["parent_source_manifest_id"]
        if parent_id is not None:
            parent = _resolve_manifest(registry, parent_id, ManifestType.SOURCE)
            _validate_source_parent(manifest, parent)
        return

    if manifest.manifest_type is ManifestType.PROTOCOL:
        source = _resolve_manifest(
            registry, payload["source_manifest_id"], ManifestType.SOURCE
        )
        source_payload = source.payload
        if payload["source_contract_id"] != source_payload["source_contract_id"]:
            raise CanonicalizationError(
                "protocol source_contract_id differs from its source manifest"
            )
        for field in ("calendar_manifest_id", "universe_manifest_id"):
            if payload[field] != source_payload[field]:
                raise CanonicalizationError(
                    f"protocol {field} differs from its source manifest"
                )
        if utc_datetime(
            payload["protocol_frozen_at"], field="protocol_frozen_at"
        ) < utc_datetime(
            source_payload["knowledge_cutoff_ts"], field="knowledge_cutoff_ts"
        ):
            raise CanonicalizationError(
                "protocol_frozen_at precedes the source knowledge cutoff"
            )
        return

    if manifest.manifest_type is ManifestType.SPLIT:
        protocol = _resolve_manifest(
            registry, payload["protocol_manifest_id"], ManifestType.PROTOCOL
        )
        source = _resolve_manifest(
            registry, payload["source_manifest_id"], ManifestType.SOURCE
        )
        if payload["split_policy_id"] != protocol.payload["split_policy_id"]:
            raise CanonicalizationError(
                "split split_policy_id differs from its frozen protocol"
            )
        if payload["holdout_policy_id"] != protocol.payload["holdout_policy_id"]:
            raise CanonicalizationError(
                "split holdout_policy_id differs from its frozen protocol"
            )
        _require_source_descendant(
            source,
            ancestor_id=protocol.payload["source_manifest_id"],
            registry=registry,
        )
        if utc_datetime(payload["as_of_ts"], field="as_of_ts") < utc_datetime(
            source.payload["knowledge_cutoff_ts"], field="knowledge_cutoff_ts"
        ):
            raise CanonicalizationError(
                "split as_of_ts precedes its source knowledge cutoff"
            )
        if payload["cohort_class"] == "FINAL_HOLDOUT":
            if source.payload["vintage_class"] != "LIVE_FIRST_SEEN_CERTIFIED":
                raise CanonicalizationError(
                    "FINAL_HOLDOUT requires LIVE_FIRST_SEEN_CERTIFIED source evidence"
                )
            if utc_datetime(
                source.payload["knowledge_cutoff_ts"],
                field="knowledge_cutoff_ts",
            ) <= utc_datetime(
                protocol.payload["protocol_frozen_at"],
                field="protocol_frozen_at",
            ):
                raise CanonicalizationError(
                    "FINAL_HOLDOUT source must accrue after protocol_frozen_at"
                )
            _require_unique_registry_key(
                manifest,
                registry,
                fields=("protocol_manifest_id", "cohort_class"),
            )
        return

    if manifest.manifest_type is ManifestType.TRIAL_SPEC:
        protocol = _resolve_manifest(
            registry, payload["protocol_manifest_id"], ManifestType.PROTOCOL
        )
        split = _resolve_manifest(
            registry, payload["split_manifest_id"], ManifestType.SPLIT
        )
        if split.payload["protocol_manifest_id"] != protocol.manifest_id:
            raise CanonicalizationError(
                "trial spec protocol differs from its split protocol"
            )
        registered_at = utc_datetime(payload["registered_at"], field="registered_at")
        if registered_at < utc_datetime(
            protocol.payload["protocol_frozen_at"], field="protocol_frozen_at"
        ):
            raise CanonicalizationError(
                "trial registered_at precedes protocol_frozen_at"
            )
        if registered_at < utc_datetime(split.payload["as_of_ts"], field="as_of_ts"):
            raise CanonicalizationError("trial registered_at precedes split as_of_ts")
        parent_id = payload["parent_trial_spec_id"]
        if parent_id is not None:
            parent = _resolve_manifest(registry, parent_id, ManifestType.TRIAL_SPEC)
            parent_payload = parent.payload
            for field in ("protocol_manifest_id", "hypothesis_family_id"):
                if payload[field] != parent_payload[field]:
                    raise CanonicalizationError(f"trial parent has a different {field}")
            if parent_payload["trial_ordinal"] >= payload["trial_ordinal"]:
                raise CanonicalizationError(
                    "trial parent ordinal must be lower than child ordinal"
                )
            if (
                utc_datetime(parent_payload["registered_at"], field="registered_at")
                > registered_at
            ):
                raise CanonicalizationError(
                    "trial parent was registered after its child"
                )
        _require_unique_registry_key(
            manifest,
            registry,
            fields=("protocol_manifest_id", "hypothesis_family_id", "trial_ordinal"),
        )
        return

    if manifest.manifest_type is ManifestType.TRIAL_RESULT:
        spec = _resolve_manifest(
            registry,
            payload["trial_spec_manifest_id"],
            ManifestType.TRIAL_SPEC,
        )
        protocol = _resolve_manifest(
            registry, payload["protocol_manifest_id"], ManifestType.PROTOCOL
        )
        split = _resolve_manifest(
            registry, payload["split_manifest_id"], ManifestType.SPLIT
        )
        if spec.payload["protocol_manifest_id"] != protocol.manifest_id:
            raise CanonicalizationError(
                "trial result protocol differs from its trial spec"
            )
        if spec.payload["split_manifest_id"] != split.manifest_id:
            raise CanonicalizationError(
                "trial result split differs from its trial spec"
            )
        if payload["source_manifest_id"] != split.payload["source_manifest_id"]:
            raise CanonicalizationError(
                "trial result source differs from its split source"
            )
        if utc_datetime(payload["started_at"], field="started_at") < utc_datetime(
            spec.payload["registered_at"], field="registered_at"
        ):
            raise CanonicalizationError(
                "trial started_at precedes trial-spec registered_at"
            )
        if payload["status"] == "SUCCEEDED":
            frozen_bindings = {
                "code_tree_hash": protocol.payload["code_tree_hash"],
                "workspace_state_hash": protocol.payload["workspace_state_hash"],
                "runtime_environment_hash": protocol.payload["environment_hash"],
            }
            for field, expected in frozen_bindings.items():
                if payload[field] != expected:
                    raise CanonicalizationError(
                        f"successful trial {field} differs from frozen protocol"
                    )
        _require_unique_registry_key(
            manifest,
            registry,
            fields=("trial_spec_manifest_id", "run_attempt_id"),
        )
        return

    raise CanonicalizationError("unsupported manifest type")


def _resolve_manifest(
    registry: Mapping[str, ImmutableManifestV3],
    manifest_id: str,
    expected_type: ManifestType,
) -> ImmutableManifestV3:
    item = registry.get(manifest_id)
    if item is None:
        raise CanonicalizationError(
            f"missing referenced {expected_type.value} manifest"
        )
    if not isinstance(item, ImmutableManifestV3):
        raise CanonicalizationError("manifest registry contains an invalid value")
    if item.manifest_id != manifest_id:
        raise CanonicalizationError("manifest registry key does not match content ID")
    if item.manifest_type is not expected_type:
        raise CanonicalizationError(
            f"referenced manifest must have type {expected_type.value}"
        )
    return item


def _resolve_evidence(
    registry: Mapping[str, EvidenceRecordV3],
    identity_id: str,
    expected_type: type[Any],
) -> Any:
    identity = canonical_hash(identity_id, field="evidence_identity_id")
    item = registry.get(identity)
    if item is None:
        raise CanonicalizationError(
            f"missing referenced {expected_type.__name__} evidence"
        )
    if type(item) is not expected_type:
        raise CanonicalizationError(
            f"referenced evidence must have type {expected_type.__name__}"
        )
    actual_identity = _evidence_identity(item)
    if actual_identity != identity:
        raise CanonicalizationError(
            "evidence registry key does not match canonical content ID"
        )
    return item


def _evidence_identity(item: EvidenceRecordV3) -> str:
    field = {
        CalendarSourceArtifactV3: "calendar_source_artifact_id",
        CalendarScheduleSnapshotV3: "calendar_snapshot_id",
        ActionProtocolV3: "action_protocol_id",
        InstrumentMappingV3: "instrument_mapping_id",
        SourceBundleMemberV3: "source_member_id",
        SourceBundleV3: "source_bundle_id",
        FeatureDependencySlotV3: "dependency_slot_id",
        FeatureDefinitionV3: "feature_definition_id",
        FeatureSchemaV3: "feature_schema_id",
        ProviderAdapterPolicyV3: "adapter_policy_id",
        ObservationSelectionPolicyV3: "observation_selection_policy_id",
    }.get(type(item))
    if field is not None:
        return canonical_hash(getattr(item, field), field=field)
    raise CanonicalizationError("unsupported evidence contract")


def _validate_source_parent(
    child: ImmutableManifestV3,
    parent: ImmutableManifestV3,
) -> None:
    child_payload = child.payload
    parent_payload = parent.payload
    for field in (
        "calendar_manifest_id",
        "first_seen_policy_id",
        "revision_policy_id",
        "source_contract_id",
        "source_dataset_id",
        "source_schema_id",
        "universe_manifest_id",
    ):
        if child_payload[field] != parent_payload[field]:
            raise CanonicalizationError(f"source lineage changes frozen {field}")
    parent_vintage = parent_payload["vintage_class"]
    child_vintage = child_payload["vintage_class"]
    if child_vintage != parent_vintage:
        raise CanonicalizationError(
            "source lineage cannot change vintage_class; prospective live evidence "
            "requires a separate root lineage"
        )
    if utc_datetime(
        child_payload["knowledge_cutoff_ts"], field="knowledge_cutoff_ts"
    ) <= utc_datetime(
        parent_payload["knowledge_cutoff_ts"], field="knowledge_cutoff_ts"
    ):
        raise CanonicalizationError(
            "child source knowledge cutoff must follow its parent cutoff"
        )


def _require_source_descendant(
    source: ImmutableManifestV3,
    *,
    ancestor_id: str,
    registry: Mapping[str, ImmutableManifestV3],
) -> None:
    current = source
    seen: set[str] = set()
    while True:
        if current.manifest_id == ancestor_id:
            return
        if current.manifest_id in seen:
            raise CanonicalizationError("source lineage contains a cycle")
        seen.add(current.manifest_id)
        parent_id = current.payload["parent_source_manifest_id"]
        if parent_id is None:
            raise CanonicalizationError(
                "split source is not a descendant of the protocol source"
            )
        current = _resolve_manifest(registry, parent_id, ManifestType.SOURCE)


def _require_unique_registry_key(
    manifest: ImmutableManifestV3,
    registry: Mapping[str, ImmutableManifestV3],
    *,
    fields: tuple[str, ...],
) -> None:
    payload = manifest.payload
    key = tuple(payload[field] for field in fields)
    for registry_id, candidate in registry.items():
        if not isinstance(candidate, ImmutableManifestV3):
            raise CanonicalizationError("manifest registry contains an invalid value")
        if candidate.manifest_id != registry_id:
            raise CanonicalizationError(
                "manifest registry key does not match content ID"
            )
        if candidate.manifest_type is not manifest.manifest_type:
            continue
        candidate_payload = candidate.payload
        candidate_key = tuple(candidate_payload[field] for field in fields)
        if candidate_key == key and candidate.manifest_id != manifest.manifest_id:
            joined = ", ".join(fields)
            raise CanonicalizationError(
                f"conflicting {manifest.manifest_type.value} records share unique key: {joined}"
            )


__all__ = [
    "MANIFEST_SCHEMA_VERSION",
    "SUPPORTED_EVENT_SCHEMA_VERSION",
    "derive_split_policy_id",
    "EvidenceRecordV3",
    "ImmutableManifestV3",
    "ManifestType",
    "validate_candidate_protocol_graph",
    "validate_action_resolution_candidate_graph",
    "validate_eligibility_protocol_graph",
    "validate_feature_materialization_protocol_graph",
    "validate_information_protocol_graph",
    "validate_manifest_evidence_graph",
    "validate_manifest_graph",
    "validate_protocol_manifest_evidence_graph",
    "validate_record_protocol_graph",
    "validate_source_manifest_evidence_graph",
]
