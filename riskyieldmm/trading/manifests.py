"""Content-addressed manifests for causal trading experiments.

Each manifest kind has an exact, versioned payload schema.  The envelope is
small on purpose: semantically meaningful clocks belong inside the kind
payload and therefore inside ``manifest_id``.  Internally, payloads are stored
as canonical JSON text so a frozen dataclass cannot conceal a mutable mapping.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any

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
    DecisionEventV3,
    EligibilityDecisionV3,
    InformationSetV3,
)

MANIFEST_SCHEMA_VERSION = "riskyieldmm_experiment_manifest_v1"
SUPPORTED_EVENT_SCHEMA_VERSION = "riskyieldmm_trade_event_v3"


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


def validate_record_protocol_graph(
    *,
    protocol: ImmutableManifestV3,
    information_set: InformationSetV3,
    eligibility: EligibilityDecisionV3,
    event: DecisionEventV3,
    registry: Mapping[str, ImmutableManifestV3],
) -> None:
    """Bind a validated causal record graph to one frozen protocol manifest."""

    if protocol.manifest_type is not ManifestType.PROTOCOL:
        raise CanonicalizationError("record graph requires a PROTOCOL manifest")
    validate_manifest_graph(protocol, registry)
    eligibility.validate_against(information_set)
    event.validate_against(information_set, eligibility)

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

    policy_bindings = {
        "eligibility_policy_id": (
            eligibility.eligibility_policy_id,
            payload["eligibility_policy_id"],
        ),
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
    if not (
        child_vintage == parent_vintage
        or (
            parent_vintage == "NOMINAL_CURRENT_REVISION"
            and child_vintage == "LIVE_FIRST_SEEN_CERTIFIED"
        )
    ):
        raise CanonicalizationError("source lineage uses an invalid vintage transition")
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
    "ImmutableManifestV3",
    "ManifestType",
    "validate_manifest_graph",
    "validate_record_protocol_graph",
]
