#!/usr/bin/env python3
"""Materialize the pinned max64/full-67 application-witness context.

This pilot-only producer uses Python's standard library and three immutable
JSON authorities.  It imports neither production ``riskyieldmm`` nor any
maximum producer/checker or application runtime.  The output is deliberately
the recipe value itself: ``{observations, root, selector}``.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import stat
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Final, NoReturn

CANONICALIZATION_VERSION: Final = "riskyieldmm_canonical_json_v1"
MEASUREMENT_SCHEMA_VERSION: Final = "riskyieldmm_physical_transport_a2m_raw_v49f_v8"
SAFE_INTEGER_MAXIMUM: Final = 9_007_199_254_740_991
MAXIMUM_ARTIFACT_OCTETS: Final = 16_777_216

REGISTRY_RELATIVE_PATH: Final = (
    "scripts/tests/raw_v8_step2_external_schema_v2_structural_registry_v49f.json"
)
LITERAL_AUTHORITY_RELATIVE_PATH: Final = (
    "scripts/tests/raw_v8_step2_external_schema_v2_rule_literal_authority_v49f.json"
)
APPLICATION_WITNESS_RELATIVE_PATH: Final = (
    "scripts/tests/raw_v8_step2_external_schema_v2_application_witness_v49f.json"
)
OUTPUT_RELATIVE_PATH: Final = (
    "scripts/tests/raw_v8_step2_external_schema_v2_"
    "application_witness_max64_full67_context_v49f.json"
)

REGISTRY_RAW_OCTETS: Final = 1_469_663
REGISTRY_RAW_SHA256: Final = (
    "9160297ff316c5931737c92f8b359f0a1e2ec22f0aa996ef3b09cf830dc96bf3"
)
REGISTRY_SEMANTIC_ID: Final = (
    "5dc95a3e99c5646e912b6a7e9c3970cf2489d560ea890b0a19d38af4c51c2140"
)
LITERAL_AUTHORITY_RAW_OCTETS: Final = 484_301
LITERAL_AUTHORITY_RAW_SHA256: Final = (
    "aba3461059367904734e2eb9ae404787b9aab5ed4c3fbcd292925a364926cce2"
)
LITERAL_AUTHORITY_SEMANTIC_ID: Final = (
    "5239e6ec09244d772c72c7883393da5707984408f7a7e21e1731948a82ea647e"
)
APPLICATION_WITNESS_RAW_OCTETS: Final = 697_208
APPLICATION_WITNESS_RAW_SHA256: Final = (
    "d2f40badc85c58965a72e52fd98bfebbd4caf3335ec5a0415a89294cc3fb3415"
)
APPLICATION_WITNESS_SEMANTIC_ID: Final = (
    "1d859520c24a973a5a157139183ae24ef0184ce4cede5531bb4b442227e1a8ba"
)

REGISTRY_DOMAIN: Final = "RiskYieldMMA2MStep2ExternalSchemaRegistryV2V4_9F_RawV8"
LITERAL_AUTHORITY_DOMAIN: Final = "RiskYieldMMA2MStep2RuleLiteralAuthorityV1V4_9F_RawV8"
APPLICATION_WITNESS_DOMAIN: Final = (
    "RiskYieldMMRawV8Step2ExternalSchemaV2ApplicationWitnessV1"
)

RECIPE_NAME: Final = "ordinary_on_max64_full67"
EXPECTED_OBSERVATION_COUNT: Final = 67
EXPECTED_ROOT_IDENTITY: Final = (
    "e988ccf6af1691103875d355aa64b91baabb2dc0f965999b9007bb64321a113e"
)
EXPECTED_ROOT_CANONICAL_SHA256: Final = (
    "9df17464ca761b9f3be18f9ecced73ab6e2f6cee20de4c7ffceba8c6ac8e52f2"
)
EXPECTED_SEQUENCE_CANONICAL_OCTETS: Final = 12_660_543
EXPECTED_SEQUENCE_CANONICAL_SHA256: Final = (
    "e1a8ed64c6c94d5f80624e011f474904f872211e671c89e276aa61460fc1cd9f"
)
EXPECTED_ORDERED_IDS_CANONICAL_SHA256: Final = (
    "17bdff1114c67db9e4fb0770890bbd68ad5e63e0845f49073cdca3213291b16e"
)
EXPECTED_SELECTOR_IDENTITY: Final = (
    "6cc3c8c09a08675ecbddddb4131dabbdd24ea3e879bc467fe56e3089834ff2f9"
)
EXPECTED_OUTPUT_RAW_OCTETS: Final = 16_121_125
EXPECTED_OUTPUT_RAW_SHA256: Final = (
    "afab90030ac96fa21157bdd3e696dd25798d7755be028c5cb8eaca103f73de97"
)
EXPECTED_OUTPUT_CANONICAL_OCTETS: Final = 12_698_603
EXPECTED_OUTPUT_CANONICAL_SHA256: Final = (
    "ab67d30d11d19670652b4c1a7aeb2d1483b97f6c4dde7bd673d9f25a3079059e"
)


class ContextGenerationError(ValueError):
    """Raised when an authority or the derived context differs."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ContextGenerationError(message)


def _reject_json_float(value: str) -> NoReturn:
    raise ContextGenerationError(f"floating-point JSON is forbidden: {value}")


def _reject_json_constant(value: str) -> NoReturn:
    raise ContextGenerationError(f"non-finite JSON is forbidden: {value}")


def _parse_json_integer(value: str) -> int:
    if len(value) > 17:
        raise ContextGenerationError("JSON integer exceeds predecode digit bound")
    parsed = int(value)
    if not -SAFE_INTEGER_MAXIMUM <= parsed <= SAFE_INTEGER_MAXIMUM:
        raise ContextGenerationError("JSON integer is outside safe I-JSON")
    return parsed


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ContextGenerationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _assert_exact_json(value: Any) -> None:
    if value is None or type(value) in {bool, str}:
        return
    if type(value) is int:
        _require(
            -SAFE_INTEGER_MAXIMUM <= value <= SAFE_INTEGER_MAXIMUM,
            "integer is outside safe I-JSON",
        )
        return
    if type(value) is list:
        for item in value:
            _assert_exact_json(item)
        return
    if type(value) is dict:
        for key, item in value.items():
            _require(type(key) is str, "JSON object key is not text")
            _assert_exact_json(item)
        return
    raise ContextGenerationError(f"non-I-JSON value: {type(value).__name__}")


def _canonical_bytes(value: Any) -> bytes:
    _assert_exact_json(value)
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _pretty_bytes(value: Any) -> bytes:
    _assert_exact_json(value)
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            indent=2,
        )
        + "\n"
    ).encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _semantic_id(domain: str, payload: dict[str, Any]) -> str:
    return _sha256(
        _canonical_bytes(
            {
                "canonicalization_version": CANONICALIZATION_VERSION,
                "domain": domain,
                "payload": payload,
                "schema_version": MEASUREMENT_SCHEMA_VERSION,
            }
        )
    )


def _read_no_follow(path: Path, expected_octets: int) -> bytes:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    chunks: list[bytes] = []
    total = 0
    try:
        metadata = os.fstat(descriptor)
        _require(stat.S_ISREG(metadata.st_mode), f"not a regular file: {path}")
        _require(metadata.st_size == expected_octets, f"octet count differs: {path}")
        while True:
            chunk = os.read(descriptor, min(1_048_576, expected_octets - total + 1))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            _require(total <= expected_octets, f"input grew while reading: {path}")
    finally:
        os.close(descriptor)
    raw = b"".join(chunks)
    _require(len(raw) == expected_octets, f"short read: {path}")
    return raw


def _decode_pinned_json(
    path: Path,
    *,
    expected_octets: int,
    expected_sha256: str,
) -> dict[str, Any]:
    raw = _read_no_follow(path, expected_octets)
    _require(_sha256(raw) == expected_sha256, f"raw SHA-256 differs: {path}")
    value = json.loads(
        raw,
        object_pairs_hook=_strict_object,
        parse_int=_parse_json_integer,
        parse_float=_reject_json_float,
        parse_constant=_reject_json_constant,
    )
    _require(type(value) is dict, f"JSON root is not an object: {path}")
    _require(_pretty_bytes(value) == raw, f"pretty JSON bytes differ: {path}")
    return value


def _validate_authorities(
    repository_root: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    registry = _decode_pinned_json(
        repository_root / REGISTRY_RELATIVE_PATH,
        expected_octets=REGISTRY_RAW_OCTETS,
        expected_sha256=REGISTRY_RAW_SHA256,
    )
    literals = _decode_pinned_json(
        repository_root / LITERAL_AUTHORITY_RELATIVE_PATH,
        expected_octets=LITERAL_AUTHORITY_RAW_OCTETS,
        expected_sha256=LITERAL_AUTHORITY_RAW_SHA256,
    )
    witness = _decode_pinned_json(
        repository_root / APPLICATION_WITNESS_RELATIVE_PATH,
        expected_octets=APPLICATION_WITNESS_RAW_OCTETS,
        expected_sha256=APPLICATION_WITNESS_RAW_SHA256,
    )

    registry_payload_names = (
        "external_schema_profile",
        "unicode_source_catalog",
        "identifier_profile_catalog",
        "ascii_dfa_catalog",
        "text_language_catalog",
        "value_schema_catalog",
        "external_type_descriptor_count",
        "ordered_external_type_descriptors",
        "cross_field_rule_descriptor_count",
        "ordered_cross_field_rule_descriptors",
        "fixed_position_resolver_profile_catalog",
        "rule_application_descriptor_count",
        "ordered_rule_application_descriptors",
        "schema_graph_node_count",
        "ordered_schema_graph_node_names",
    )
    _require(
        registry.get("record_domain") == REGISTRY_DOMAIN, "registry domain differs"
    )
    _require(
        registry.get("external_schema_registry_id") == REGISTRY_SEMANTIC_ID,
        "registry identity differs",
    )
    _require(
        _semantic_id(
            REGISTRY_DOMAIN,
            {name: registry[name] for name in registry_payload_names},
        )
        == REGISTRY_SEMANTIC_ID,
        "registry identity does not recompute",
    )

    literal_payload = {
        name: value
        for name, value in literals.items()
        if name != "rule_literal_authority_sha256"
    }
    _require(
        literals.get("rule_literal_authority_sha256") == LITERAL_AUTHORITY_SEMANTIC_ID,
        "literal-authority identity differs",
    )
    _require(
        _semantic_id(LITERAL_AUTHORITY_DOMAIN, literal_payload)
        == LITERAL_AUTHORITY_SEMANTIC_ID,
        "literal-authority identity does not recompute",
    )

    witness_payload = {
        name: value
        for name, value in witness.items()
        if name != "application_witness_sha256"
    }
    _require(
        witness.get("application_witness_sha256") == APPLICATION_WITNESS_SEMANTIC_ID,
        "application-witness identity differs",
    )
    _require(
        _sha256(
            _canonical_bytes(
                {"domain": APPLICATION_WITNESS_DOMAIN, "payload": witness_payload}
            )
        )
        == APPLICATION_WITNESS_SEMANTIC_ID,
        "application-witness identity does not recompute",
    )
    _require(
        witness["source_structural_registry"]
        == {
            "external_schema_registry_id": REGISTRY_SEMANTIC_ID,
            "physical_octets": REGISTRY_RAW_OCTETS,
            "physical_sha256": REGISTRY_RAW_SHA256,
        },
        "application-witness registry pin differs",
    )
    _require(
        witness["source_literal_authority"]
        == {
            "physical_octets": LITERAL_AUTHORITY_RAW_OCTETS,
            "physical_sha256": LITERAL_AUTHORITY_RAW_SHA256,
            "rule_literal_authority_sha256": LITERAL_AUTHORITY_SEMANTIC_ID,
        },
        "application-witness literal-authority pin differs",
    )

    fixtures = witness.get("fixture_records")
    _require(type(fixtures) is dict and len(fixtures) == 13, "fixture catalog differs")
    _require(list(fixtures) == sorted(fixtures), "fixture catalog order differs")
    for name, fixture in fixtures.items():
        _require(
            fixture["provenance"]["frozen_value_canonical_sha256"]
            == _sha256(_canonical_bytes(fixture["value"])),
            f"fixture hash differs: {name}",
        )
    return registry, literals, witness


def _record_descriptors(registry: dict[str, Any]) -> dict[str, dict[str, Any]]:
    descriptors = {
        descriptor["type_name"]: descriptor
        for descriptor in registry["ordered_external_type_descriptors"]
        if descriptor["type_form"] == "RECORD"
    }
    _require(len(descriptors) == 49, "record descriptor count differs")
    return descriptors


def _rehash_record(
    descriptors: dict[str, dict[str, Any]],
    value: dict[str, Any],
    type_name: str,
) -> None:
    descriptor = descriptors[type_name]
    identity_field = descriptor["identity_field"]
    _require(type(identity_field) is str, f"record has no identity: {type_name}")
    payload = {
        name: value[name] for name in descriptor["identity_payload_member_order"]
    }
    value[identity_field] = _semantic_id(descriptor["described_record_domain"], payload)


def _rebase_outer_observation(
    descriptors: dict[str, dict[str, Any]],
    witness: dict[str, Any],
    root: dict[str, Any],
    *,
    role: str,
) -> dict[str, Any]:
    observation = copy.deepcopy(
        witness["fixture_records"]["exact_marker_observation"]["value"]
    )
    context = observation["observation_context"]
    context.update(
        {
            "attempt_id": root["attempt_id"],
            "candidate_id": root["candidate_id"],
            "instrumentation_mode": "ON",
            "observation_role": role,
            "operation_kind": root["operation_kind"],
            "target_field_registry_id": root["target_field_registry_id"],
        }
    )
    for member in (
        "checkpoint_binding_status",
        "checkpoint_binding_unavailable_reason",
        "checkpoint_marker_kind",
        "checkpoint_selector_entry_id",
        "checkpoint_selector_position",
        "expected_checkpoint_marker_kind",
        "expected_occurrence_index_within_kind",
        "full_checkpoint_selector_id",
        "marker_ordinal",
    ):
        context[member] = None
    _rehash_record(descriptors, context, "TargetObservationContextV2")
    observation["observation_context_id"] = context["observation_context_id"]
    for field in observation["field_observations"]:
        field["observation_context_id"] = context["observation_context_id"]
        field["target_field_registry_id"] = root["target_field_registry_id"]
        _rehash_record(descriptors, field, "TargetFieldObservationV1")
    _rehash_record(descriptors, observation, "TargetObservationV2")
    return observation


def _rebase_checkpoint_observation(
    descriptors: dict[str, dict[str, Any]],
    witness: dict[str, Any],
    root: dict[str, Any],
    selector: dict[str, Any],
    entry: dict[str, Any],
) -> dict[str, Any]:
    observation = copy.deepcopy(
        witness["fixture_records"]["target_boundary_placeholder_observation"]["value"]
    )
    context = observation["observation_context"]
    context.update(
        {
            "attempt_id": root["attempt_id"],
            "candidate_id": root["candidate_id"],
            "checkpoint_binding_status": "UNAVAILABLE_TARGET_BOUNDARY_NOT_REACHED",
            "checkpoint_binding_unavailable_reason": "TARGET_BOUNDARY_NOT_REACHED",
            "checkpoint_marker_kind": None,
            "checkpoint_selector_entry_id": entry["checkpoint_selector_entry_id"],
            "checkpoint_selector_position": entry["selector_position"],
            "expected_checkpoint_marker_kind": entry["checkpoint_marker_kind"],
            "expected_occurrence_index_within_kind": entry[
                "occurrence_index_within_kind"
            ],
            "full_checkpoint_selector_id": selector["checkpoint_selector_id"],
            "instrumentation_mode": "ON",
            "marker_ordinal": None,
            "observation_role": "STABLE_CHECKPOINT",
            "operation_kind": root["operation_kind"],
            "target_field_registry_id": root["target_field_registry_id"],
        }
    )
    _rehash_record(descriptors, context, "TargetObservationContextV2")
    observation["observation_context_id"] = context["observation_context_id"]
    for field in observation["field_observations"]:
        field["observation_context_id"] = context["observation_context_id"]
        field["target_field_registry_id"] = root["target_field_registry_id"]
        _rehash_record(descriptors, field, "TargetFieldObservationV1")
    _rehash_record(descriptors, observation, "TargetObservationV2")
    return observation


def _materialize(registry: dict[str, Any], witness: dict[str, Any]) -> dict[str, Any]:
    recipe = witness["materialization_recipes"][RECIPE_NAME]
    expected_recipe = {
        "expected_observation_count": EXPECTED_OBSERVATION_COUNT,
        "expected_ordered_observation_ids_canonical_sha256": (
            EXPECTED_ORDERED_IDS_CANONICAL_SHA256
        ),
        "expected_role_sequence_summary": {
            "checkpoint_count": 64,
            "checkpoint_role": "STABLE_CHECKPOINT",
            "first": "BEFORE_OPERATION",
            "last": "OPERATION_AGGREGATE",
            "penultimate": "AFTER_OPERATION",
        },
        "expected_root_canonical_sha256": EXPECTED_ROOT_CANONICAL_SHA256,
        "expected_root_identity": EXPECTED_ROOT_IDENTITY,
        "expected_sequence_canonical_sha256": EXPECTED_SEQUENCE_CANONICAL_SHA256,
        "instrumentation_mode": "ON",
        "recipe_kind": "CAUSAL_V2_ROOT_SEQUENCE",
        "selector_fixture": "selector_ingress_max64",
        "source_root_fixture": "maximum_selector_root",
        "startup_recovery": False,
    }
    _require(recipe == expected_recipe, "max64/full-67 recipe differs")
    _require(
        witness["recipe_algorithm"]
        == {
            "algorithm_version": "CAUSAL_V2_ROOT_SEQUENCE_V1",
            "checkpoint_placeholder_base_fixture": (
                "target_boundary_placeholder_observation"
            ),
            "ordered_steps": [
                "copy the source root and selected frozen bases",
                (
                    "align candidate, attempt, operation, mode, registry, role, "
                    "and selector context"
                ),
                (
                    "clear outer checkpoint members or bind every checkpoint to "
                    "its exact selector entry"
                ),
                (
                    "recompute context, all 185 field, observation, ordered "
                    "observation, and root identities in dependency order"
                ),
                (
                    "freeze canonical hashes for root, sequence, and ordered "
                    "observation identities"
                ),
            ],
            "outer_observation_base_fixture": "exact_marker_observation",
        },
        "recipe algorithm differs",
    )

    descriptors = _record_descriptors(registry)
    fixtures = witness["fixture_records"]
    root = copy.deepcopy(fixtures["maximum_selector_root"]["value"])
    selector = copy.deepcopy(fixtures["selector_ingress_max64"]["value"])
    _require(
        selector["checkpoint_selector_id"] == EXPECTED_SELECTOR_IDENTITY,
        "max64 selector identity differs",
    )
    _require(len(selector["ordered_entries"]) == 64, "selector is not max64")

    observations = [
        _rebase_outer_observation(
            descriptors,
            witness,
            root,
            role="BEFORE_OPERATION",
        )
    ]
    observations.extend(
        _rebase_checkpoint_observation(
            descriptors,
            witness,
            root,
            selector,
            entry,
        )
        for entry in selector["ordered_entries"]
    )
    observations.extend(
        (
            _rebase_outer_observation(
                descriptors,
                witness,
                root,
                role="AFTER_OPERATION",
            ),
            _rebase_outer_observation(
                descriptors,
                witness,
                root,
                role="OPERATION_AGGREGATE",
            ),
        )
    )
    root["instrumentation_mode"] = "ON"
    root["full_checkpoint_selector_id"] = selector["checkpoint_selector_id"]
    root["observation_count"] = len(observations)
    root["ordered_observation_ids"] = [item["observation_id"] for item in observations]
    _rehash_record(descriptors, root, "TargetObservationRootV2")
    result = {"observations": observations, "root": root, "selector": selector}
    _validate_derived(result)
    return result


def _validate_derived(value: dict[str, Any]) -> None:
    _require(set(value) == {"observations", "root", "selector"}, "root shape differs")
    observations = value["observations"]
    root = value["root"]
    selector = value["selector"]
    _require(type(observations) is list, "observations is not an array")
    _require(
        type(root) is dict and type(selector) is dict, "root/selector shape differs"
    )
    _require(
        len(observations) == EXPECTED_OBSERVATION_COUNT, "observation count differs"
    )
    _require(len(selector["ordered_entries"]) == 64, "selector entry count differs")
    roles = [item["observation_context"]["observation_role"] for item in observations]
    _require(
        roles
        == ["BEFORE_OPERATION"]
        + ["STABLE_CHECKPOINT"] * 64
        + ["AFTER_OPERATION", "OPERATION_AGGREGATE"],
        "observation role order differs",
    )
    _require(root["observation_count"] == len(observations), "root count differs")
    _require(
        root["ordered_observation_ids"]
        == [item["observation_id"] for item in observations],
        "root resolver sequence differs",
    )
    _require(
        root["full_checkpoint_selector_id"] == selector["checkpoint_selector_id"],
        "selector resolver identity differs",
    )
    for ordinal, (observation, expected_id) in enumerate(
        zip(observations, root["ordered_observation_ids"], strict=True)
    ):
        _require(observation["observation_id"] == expected_id, "resolver ID differs")
        context = observation["observation_context"]
        _require(
            all(
                context[name] == root[name]
                for name in (
                    "candidate_id",
                    "attempt_id",
                    "operation_kind",
                    "instrumentation_mode",
                    "target_field_registry_id",
                )
            ),
            f"membership application differs at ordinal {ordinal}",
        )
    for ordinal, (observation, entry) in enumerate(
        zip(observations[1:-2], selector["ordered_entries"], strict=True),
        start=1,
    ):
        context = observation["observation_context"]
        _require(
            (
                context["checkpoint_selector_position"] == ordinal
                and context["checkpoint_selector_position"]
                == entry["selector_position"]
                and context["checkpoint_selector_entry_id"]
                == entry["checkpoint_selector_entry_id"]
                and context["expected_checkpoint_marker_kind"]
                == entry["checkpoint_marker_kind"]
                and context["expected_occurrence_index_within_kind"]
                == entry["occurrence_index_within_kind"]
            ),
            f"checkpoint lifecycle binding differs at position {ordinal}",
        )

    sequence_bytes = _canonical_bytes(observations)
    _require(
        len(sequence_bytes) == EXPECTED_SEQUENCE_CANONICAL_OCTETS,
        "sequence canonical octet count differs",
    )
    _require(
        _sha256(sequence_bytes) == EXPECTED_SEQUENCE_CANONICAL_SHA256,
        "sequence canonical SHA-256 differs",
    )
    _require(
        root["target_observation_root_sha256"] == EXPECTED_ROOT_IDENTITY,
        "root ID differs",
    )
    _require(
        _sha256(_canonical_bytes(root)) == EXPECTED_ROOT_CANONICAL_SHA256,
        "root canonical SHA-256 differs",
    )
    _require(
        _sha256(_canonical_bytes(root["ordered_observation_ids"]))
        == EXPECTED_ORDERED_IDS_CANONICAL_SHA256,
        "ordered observation identity SHA-256 differs",
    )
    canonical = _canonical_bytes(value)
    _require(
        len(canonical) == EXPECTED_OUTPUT_CANONICAL_OCTETS,
        "output canonical count differs",
    )
    _require(
        _sha256(canonical) == EXPECTED_OUTPUT_CANONICAL_SHA256,
        "output canonical hash differs",
    )
    rendered = _pretty_bytes(value)
    _require(len(rendered) < MAXIMUM_ARTIFACT_OCTETS, "output exceeds raw file ceiling")
    _require(len(rendered) == EXPECTED_OUTPUT_RAW_OCTETS, "output raw count differs")
    _require(
        _sha256(rendered) == EXPECTED_OUTPUT_RAW_SHA256, "output raw SHA-256 differs"
    )


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _require(not path.parent.is_symlink(), "refusing symlink output directory")
    directory_descriptor = os.open(
        path.parent,
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
    )
    temporary_name = f".{path.name}.tmp.{os.getpid()}"
    try:
        try:
            existing = os.stat(
                path.name, dir_fd=directory_descriptor, follow_symlinks=False
            )
        except FileNotFoundError:
            existing = None
        _require(
            existing is None or not stat.S_ISLNK(existing.st_mode),
            "refusing symlink output",
        )
        descriptor = os.open(
            temporary_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o644,
            dir_fd=directory_descriptor,
        )
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(
                temporary_name,
                path.name,
                src_dir_fd=directory_descriptor,
                dst_dir_fd=directory_descriptor,
            )
            os.fsync(directory_descriptor)
        finally:
            try:
                os.unlink(temporary_name, dir_fd=directory_descriptor)
            except FileNotFoundError:
                pass
    finally:
        os.close(directory_descriptor)


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--check", action="store_true")
    actions.add_argument("--write", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        repository_root = args.repository_root.resolve(strict=True)
        registry, _literals, witness = _validate_authorities(repository_root)
        value = _materialize(registry, witness)
        rendered = _pretty_bytes(value)
        output = (
            repository_root / OUTPUT_RELATIVE_PATH
            if args.output is None
            else args.output.resolve()
        )
        if args.check:
            raw = _read_no_follow(output, EXPECTED_OUTPUT_RAW_OCTETS)
            _require(raw == rendered, "materialized context is missing or stale")
            operation = "checked"
        else:
            _atomic_write(output, rendered)
            operation = "wrote"
        print(
            f"{operation} max64/full-67 context: {output} "
            f"({len(rendered)} octets, sha256={_sha256(rendered)})"
        )
        return 0
    except (ContextGenerationError, KeyError, OSError, TypeError) as exc:
        print(f"max64/full-67 context generator: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
