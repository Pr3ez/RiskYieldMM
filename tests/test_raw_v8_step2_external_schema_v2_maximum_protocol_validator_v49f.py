"""Focused fail-closed tests for the rejected maximum-protocol V1 checker.

These tests exercise isolated encoding/schema primitives and rejection surfaces.
They do not construct or endorse a maximum certificate, pilot, or acceptance
report, and they do not endorse a replacement protocol or accepted maximum.
"""

from __future__ import annotations

import ast
import copy
import hashlib
import importlib.util
import json
import os
import stat
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

_VALIDATOR_RELATIVE_PATH = (
    "scripts/tests/validate_raw_v8_step2_external_schema_v2_maximum_protocol_v49f.py"
)
_GENERATOR_RELATIVE_PATH = (
    "scripts/tests/"
    "generate_raw_v8_step2_external_schema_v2_maximum_protocol_pilot_v49f.py"
)
_ERROR_PREFIX = "Raw-V8 Step-2 maximum protocol error: "
_GUARDED_CANONICAL_PATHS = (
    "scripts/tests/raw_v8_step2_external_schema_v2_maximum_protocol_pilot_v49f.json",
    "scripts/tests/"
    "raw_v8_step2_external_schema_v2_maximum_protocol_pilot_seed_v49f.json",
    "scripts/tests/"
    "raw_v8_step2_external_schema_v2_maximum_protocol_pilot_seed_protocol_v49f.md",
)


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def validator() -> ModuleType:
    path = _repository_root() / _VALIDATOR_RELATIVE_PATH
    spec = importlib.util.spec_from_file_location(
        "_raw_v8_step2_maximum_protocol_validator_v49f",
        path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def pinned_inventory_and_registry(
    validator: ModuleType,
) -> tuple[dict[str, Any], dict[str, Any]]:
    root = _repository_root()
    inventory_raw = (root / validator.INVENTORY_RELATIVE_PATH).read_bytes()
    registry_raw = (root / validator.REGISTRY_RELATIVE_PATH).read_bytes()
    assert len(inventory_raw) == validator.INVENTORY_OCTETS
    assert hashlib.sha256(inventory_raw).hexdigest() == validator.INVENTORY_RAW_SHA256
    assert len(registry_raw) == validator.REGISTRY_OCTETS
    assert hashlib.sha256(registry_raw).hexdigest() == validator.REGISTRY_RAW_SHA256
    inventory = json.loads(inventory_raw)
    registry = json.loads(registry_raw)
    validator._validate_registry(registry)  # noqa: SLF001
    literals = {
        name: inventory[name]
        for name in (
            "marker_contract",
            "operation_counter_schema",
            "target_field_registry",
        )
    }
    validator._validate_inventory(  # noqa: SLF001
        inventory,
        registry=registry,
        literals=literals,
    )
    return inventory, registry


@pytest.fixture(scope="module")
def pinned_max64_context_authority(
    validator: ModuleType,
) -> dict[str, Any]:
    path = _repository_root() / validator.MAX64_CONTEXT_AUTHORITY_RELATIVE_PATH
    raw = path.read_bytes()
    assert len(raw) == validator.MAX64_CONTEXT_AUTHORITY_OCTETS
    assert (
        hashlib.sha256(raw).hexdigest() == validator.MAX64_CONTEXT_AUTHORITY_RAW_SHA256
    )
    authority = json.loads(raw)
    validator._validate_materialized_max64_context_authority(  # noqa: SLF001
        authority,
        label="pinned max64 context authority",
    )
    return authority


def _run_child(*arguments: str, timeout: int = 180) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        (sys.executable, "-I", "-B", *arguments),
        cwd=_repository_root(),
        env={
            **os.environ,
            "PYTHONHASHSEED": "0",
            "PYTHONDONTWRITEBYTECODE": "1",
        },
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _pretty(value: Any) -> bytes:
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


def _semantic_envelope(
    validator: ModuleType, domain: str, payload: Any
) -> dict[str, Any]:
    return {
        "canonicalization_version": validator.CANONICALIZATION_VERSION,
        "domain": domain,
        "payload": payload,
        "schema_version": validator.MEASUREMENT_SCHEMA_VERSION,
    }


def _v3_record_reference(
    validator: ModuleType,
    *,
    inventory: dict[str, Any],
    pointer: str,
    record_type_name: str,
    record_identity_field: str,
) -> dict[str, Any]:
    record: Any = inventory
    for token in pointer[1:].split("/"):
        decoded = token.replace("~1", "/").replace("~0", "~")
        record = record[int(decoded)] if type(record) is list else record[decoded]
    assert type(record) is dict
    canonical_record = _canonical(record)
    reference = {
        "reference_kind": "V3_INVENTORY_POINTER",
        "source_inventory_sha256": validator.INVENTORY_SEMANTIC_ID,
        "inventory_json_pointer": pointer,
        "record_type_name": record_type_name,
        "record_identity_field": record_identity_field,
        "record_identity": record[record_identity_field],
        "record_canonical_byte_length": len(canonical_record),
        "record_canonical_sha256": hashlib.sha256(canonical_record).hexdigest(),
    }
    reference["maximum_record_reference_id"] = validator._semantic_id(  # noqa: SLF001
        validator.MAXIMUM_RECORD_REFERENCE_DOMAIN,
        reference,
    )
    return reference


def _refresh_record_reference_id(
    validator: ModuleType,
    reference: dict[str, Any],
) -> None:
    payload = {
        name: item
        for name, item in reference.items()
        if name != "maximum_record_reference_id"
    }
    reference["maximum_record_reference_id"] = validator._semantic_id(  # noqa: SLF001
        validator.MAXIMUM_RECORD_REFERENCE_DOMAIN,
        payload,
    )


def _identified_record_reference(
    validator: ModuleType,
    *,
    record: dict[str, Any],
    record_type_name: str,
    record_identity_field: str,
    reference_kind: str,
    maximum_context_object_id: str | None = None,
) -> dict[str, Any]:
    canonical_record = _canonical(record)
    reference: dict[str, Any] = {
        "reference_kind": reference_kind,
    }
    if reference_kind == "CONTEXT_OBJECT":
        assert maximum_context_object_id is not None
        reference["maximum_context_object_id"] = maximum_context_object_id
    else:
        assert reference_kind == "WITNESS_RECORD"
        assert maximum_context_object_id is None
    reference.update(
        {
            "record_type_name": record_type_name,
            "record_identity_field": record_identity_field,
            "record_identity": record[record_identity_field],
            "record_canonical_byte_length": len(canonical_record),
            "record_canonical_sha256": hashlib.sha256(canonical_record).hexdigest(),
        }
    )
    _refresh_record_reference_id(validator, reference)
    return reference


def _inline_context_entry(
    validator: ModuleType,
    *,
    record: dict[str, Any],
    record_type_name: str,
    record_identity_field: str,
    protocol_sha256: str,
) -> dict[str, Any]:
    canonical_record = _canonical(record)
    entry = {
        "context_object_position": 0,
        "context_source_kind": "INLINE_PILOT_CONTEXT_RECORD",
        "source_authority_sha256": None,
        "source_json_pointer": None,
        "derived_record_role": None,
        "derived_sequence_ordinal": None,
        "inline_record": copy.deepcopy(record),
        "maximum_context_object_id": "0" * 64,
        "record_type_name": record_type_name,
        "record_identity_field": record_identity_field,
        "record_identity": record[record_identity_field],
        "record_canonical_byte_length": len(canonical_record),
        "record_canonical_sha256": hashlib.sha256(canonical_record).hexdigest(),
    }
    _refresh_context_object_id_from_claim(
        validator,
        entry,
        protocol_sha256=protocol_sha256,
        max64_context_authority={},
    )
    return entry


def _context_source_record(
    entry: dict[str, Any],
    *,
    max64_context_authority: dict[str, Any],
) -> dict[str, Any]:
    if entry["context_source_kind"] == "INLINE_PILOT_CONTEXT_RECORD":
        return entry["inline_record"]
    role = entry["derived_record_role"]
    if role == "ROOT_RECORD":
        return max64_context_authority["root"]
    if role == "SELECTOR_RECORD":
        return max64_context_authority["selector"]
    return max64_context_authority["observations"][entry["derived_sequence_ordinal"]]


def _refresh_context_object_id_from_claim(
    validator: ModuleType,
    entry: dict[str, Any],
    *,
    protocol_sha256: str,
    max64_context_authority: dict[str, Any],
) -> None:
    record = _context_source_record(
        entry,
        max64_context_authority=max64_context_authority,
    )
    entry["maximum_context_object_id"] = validator._semantic_id(  # noqa: SLF001
        validator.MAXIMUM_CONTEXT_OBJECT_DOMAIN,
        {
            "maximum_protocol_sha256": protocol_sha256,
            "source_inventory_sha256": validator.INVENTORY_SEMANTIC_ID,
            "external_schema_registry_id": validator.REGISTRY_ID,
            "rule_literal_authority_sha256": validator.LITERAL_AUTHORITY_RAW_SHA256,
            "record_type_name": entry["record_type_name"],
            "record_identity_field": entry["record_identity_field"],
            "record_identity": entry["record_identity"],
            "record_canonical_byte_length": entry["record_canonical_byte_length"],
            "record_canonical_sha256": entry["record_canonical_sha256"],
            "record": record,
        },
    )


def _max64_context_entry(
    validator: ModuleType,
    *,
    registry: dict[str, Any],
    max64_context_authority: dict[str, Any],
    protocol_sha256: str,
    role: str,
    ordinal: int | None = None,
    inline: bool = False,
) -> dict[str, Any]:
    if role == "ROOT_RECORD":
        record = max64_context_authority["root"]
        pointer = "/root"
        record_type_name = "TargetObservationRootV2"
    elif role == "SELECTOR_RECORD":
        record = max64_context_authority["selector"]
        pointer = "/selector"
        record_type_name = "CheckpointSelectorV1"
    else:
        assert role == "OBSERVATION_RECORD" and type(ordinal) is int
        record = max64_context_authority["observations"][ordinal]
        pointer = f"/observations/{ordinal}"
        record_type_name = "TargetObservationV2"
    descriptor = next(
        item
        for item in registry["ordered_external_type_descriptors"]
        if item["type_name"] == record_type_name
    )
    identity_field = descriptor["identity_field"]
    canonical_record = _canonical(record)
    entry = {
        "context_object_position": 0,
        "context_source_kind": (
            "INLINE_PILOT_CONTEXT_RECORD"
            if inline
            else "MATERIALIZED_MAX64_CONTEXT_POINTER"
        ),
        "source_authority_sha256": (
            None if inline else validator.MAX64_CONTEXT_AUTHORITY_RAW_SHA256
        ),
        "source_json_pointer": None if inline else pointer,
        "derived_record_role": None if inline else role,
        "derived_sequence_ordinal": None if inline else ordinal,
        "inline_record": copy.deepcopy(record) if inline else None,
        "maximum_context_object_id": "0" * 64,
        "record_type_name": record_type_name,
        "record_identity_field": identity_field,
        "record_identity": record[identity_field],
        "record_canonical_byte_length": len(canonical_record),
        "record_canonical_sha256": hashlib.sha256(canonical_record).hexdigest(),
    }
    _refresh_context_object_id_from_claim(
        validator,
        entry,
        protocol_sha256=protocol_sha256,
        max64_context_authority=max64_context_authority,
    )
    return entry


def _refresh_context_manifest_id(
    validator: ModuleType,
    manifest: dict[str, Any],
) -> None:
    payload = {
        name: item
        for name, item in manifest.items()
        if name != "maximum_context_object_manifest_id"
    }
    manifest["maximum_context_object_manifest_id"] = validator._semantic_id(  # noqa: SLF001
        validator.PILOT_CONTEXT_MANIFEST_DOMAIN,
        payload,
    )


def _pilot_context_manifest(
    validator: ModuleType,
    *,
    protocol_sha256: str,
    entries: list[dict[str, Any]],
) -> dict[str, Any]:
    ordered_entries = sorted(
        copy.deepcopy(entries),
        key=lambda entry: (
            entry["record_type_name"],
            entry["record_identity"],
            entry["record_canonical_sha256"],
            entry["context_source_kind"],
            (
                entry["source_json_pointer"] is not None,
                entry["source_json_pointer"] or "",
            ),
            (
                entry["derived_record_role"] is not None,
                entry["derived_record_role"] or "",
            ),
            (
                entry["derived_sequence_ordinal"] is not None,
                entry["derived_sequence_ordinal"] or 0,
            ),
        ),
    )
    for position, entry in enumerate(ordered_entries, 1):
        entry["context_object_position"] = position
    manifest = {
        "manifest_version": (
            "riskyieldmm.raw_v8_step2_external_schema_v2."
            "maximum_protocol_pilot_context_manifest.v1"
        ),
        "canonicalization_version": validator.CANONICALIZATION_VERSION,
        "measurement_schema_version": validator.MEASUREMENT_SCHEMA_VERSION,
        "maximum_protocol_sha256": protocol_sha256,
        "source_inventory_sha256": validator.INVENTORY_SEMANTIC_ID,
        "external_schema_registry_id": validator.REGISTRY_ID,
        "rule_literal_authority_sha256": validator.LITERAL_AUTHORITY_RAW_SHA256,
        "application_witness_raw_sha256": validator.APPLICATION_WITNESS_RAW_SHA256,
        "max64_context_authority_raw_sha256": (
            validator.MAX64_CONTEXT_AUTHORITY_RAW_SHA256
        ),
        "ordered_context_object_entries": ordered_entries,
        "maximum_context_object_manifest_id": "0" * 64,
    }
    _refresh_context_manifest_id(validator, manifest)
    return manifest


def _path_fingerprint(path: Path) -> tuple[Any, ...] | None:
    if not os.path.lexists(path):
        return None
    metadata = os.lstat(path)
    digest = None
    if stat.S_ISREG(metadata.st_mode):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_nlink,
        metadata.st_size,
        metadata.st_mtime_ns,
        digest,
    )


def _empty_signature(validator: ModuleType) -> str:
    return validator._semantic_id(  # noqa: SLF001
        validator.STATE_SIGNATURE_DOMAIN,
        {"ordered_state_dimensions": []},
    )


def _frontier(runs: list[dict[str, Any]], validator: ModuleType) -> dict[str, Any]:
    signature = _empty_signature(validator)
    return {
        "frontier_soundness": "EXACT_ATTAINABLE",
        "state_signature_id": signature,
        "ordered_observable_descriptor_ids": [],
        "ordered_state_frontiers": [
            {
                "state_key": [],
                "ordered_length_bitmap_runs": runs,
            }
        ],
    }


def _bitmap(value: int) -> str:
    return f"{value:064x}"


def _path_step(*, ordinal: int | None) -> dict[str, Any]:
    return {
        "step_position": 1,
        "step_kind": "ARRAY_ITEM",
        "member_name": None,
        "member_position": None,
        "array_ordinal": ordinal,
        "sequence_name": None,
        "union_alternative_position": None,
        "nullable_branch": None,
    }


def _schema_locator(*, path: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "locator_kind": "SCHEMA_DOMAIN",
        "record_reference_id": None,
        "root_type_name": "ExampleRecord",
        "root_value_schema_id": "0" * 64,
        "ordered_path_steps": [] if path is None else path,
        "transient_state_key": None,
        "transient_source_child_position": None,
        "transient_source_child_proof_node_id": None,
    }


def _transient_locator() -> dict[str, Any]:
    return {
        "locator_kind": "TRANSIENT_FRONTIER_STATE",
        "record_reference_id": None,
        "root_type_name": None,
        "root_value_schema_id": None,
        "ordered_path_steps": [],
        "transient_state_key": [],
        "transient_source_child_position": 1,
        "transient_source_child_proof_node_id": "1" * 64,
    }


def _retained_locator(*, ordinal: int | None) -> dict[str, Any]:
    return {
        "locator_kind": "WITNESS_RECORD",
        "record_reference_id": "2" * 64,
        "root_type_name": "ExampleRecord",
        "root_value_schema_id": None,
        "ordered_path_steps": [_path_step(ordinal=ordinal)],
        "transient_state_key": None,
        "transient_source_child_position": None,
        "transient_source_child_proof_node_id": None,
    }


def _boolean_atom(value: Any) -> dict[str, Any]:
    return {
        "atom_kind": "BOOLEAN",
        "boolean_value": value,
        "integer_value": None,
        "text_value": None,
        "position_value": None,
        "canonical_bytes_hex_value": None,
    }


def _primitive_atom(kind: str, value: Any = None) -> dict[str, Any]:
    atom = {
        "atom_kind": kind,
        "boolean_value": None,
        "integer_value": None,
        "text_value": None,
        "position_value": None,
        "canonical_bytes_hex_value": None,
    }
    member = {
        "BOOLEAN": "boolean_value",
        "SAFE_INTEGER": "integer_value",
        "TEXT": "text_value",
        "POSITION": "position_value",
        "CANONICAL_BYTES": "canonical_bytes_hex_value",
    }.get(kind)
    if member is not None:
        atom[member] = value
    return atom


def _canonical_bytes_atom(value: Any) -> dict[str, Any]:
    return _primitive_atom("CANONICAL_BYTES", _canonical(value).hex())


def _ordered_string_state(
    *,
    position: int,
    state_kind: str,
    key_atoms: list[dict[str, Any]],
    payload_atoms: list[dict[str, Any]],
    attainable_runs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "state_position": position,
        "ordered_state_key_atoms": [
            _primitive_atom("TEXT", state_kind),
            *key_atoms,
        ],
        "ordered_state_key_cells": [],
        "ordered_state_payload_atoms": payload_atoms,
        "ordered_state_payload_cells": [],
        "ordered_attainable_length_bitmap_runs": (
            [] if attainable_runs is None else attainable_runs
        ),
    }


def _derived_identity_state(
    *,
    position: int,
    next_plan_position: int,
    current_prefix_position: int,
    least_prefix_position: int | None,
    derived_identity: str | None,
    relation_values: list[bool | None],
    attainable_runs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "state_position": position,
        "ordered_state_key_atoms": [
            _primitive_atom("TEXT", "PAYLOAD_PREFIX"),
            _primitive_atom("POSITION", next_plan_position),
            _primitive_atom("POSITION", current_prefix_position),
        ],
        "ordered_state_key_cells": [],
        "ordered_state_payload_atoms": [
            _primitive_atom(
                "NULL" if least_prefix_position is None else "POSITION",
                least_prefix_position,
            ),
            _primitive_atom(
                "NULL" if derived_identity is None else "TEXT",
                derived_identity,
            ),
            *[
                _primitive_atom("NULL" if value is None else "BOOLEAN", value)
                for value in relation_values
            ],
        ],
        "ordered_state_payload_cells": [],
        "ordered_attainable_length_bitmap_runs": (
            [] if attainable_runs is None else attainable_runs
        ),
    }


def _count_frontier(*supports: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "item_count": item_count,
            "ordered_total_octet_bitmap_runs": runs,
        }
        for item_count, runs in enumerate(supports)
    ]


def _exact_cell(atom: dict[str, Any], validator: ModuleType) -> dict[str, Any]:
    payload = {
        "cell_kind": "EXACT_ATOM",
        "exact_atom": atom,
        "integer_interval": None,
        "catalog_id": None,
        "catalog_position": None,
    }
    return {
        **payload,
        "state_cell_id": validator._semantic_id(  # noqa: SLF001
            validator.STATE_CELL_DOMAIN,
            payload,
        ),
    }


def _inactive_guard_sentinel_cell(validator: ModuleType) -> dict[str, Any]:
    payload = {
        "cell_kind": "INACTIVE_GUARD_SENTINEL",
        "exact_atom": None,
        "integer_interval": None,
        "catalog_id": None,
        "catalog_position": None,
    }
    return {
        **payload,
        "state_cell_id": validator._semantic_id(  # noqa: SLF001
            validator.STATE_CELL_DOMAIN,
            payload,
        ),
    }


def _catalog_cell(
    catalog_id: str,
    catalog_position: int,
    validator: ModuleType,
) -> dict[str, Any]:
    payload = {
        "cell_kind": "VERIFIER_DERIVED_CATALOG_POSITION",
        "exact_atom": None,
        "integer_interval": None,
        "catalog_id": catalog_id,
        "catalog_position": catalog_position,
    }
    return {
        **payload,
        "state_cell_id": validator._semantic_id(  # noqa: SLF001
            validator.STATE_CELL_DOMAIN,
            payload,
        ),
    }


def _one_length_run(length: int = 0) -> list[dict[str, Any]]:
    return [
        {
            "first_block_index": length // 256,
            "last_block_index": length // 256,
            "attainable_length_bitmap_hex": _bitmap(1 << (length % 256)),
        }
    ]


def _dimension(
    validator: ModuleType,
    *,
    position: int,
    kind: str,
    activation_guards: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    comparison = {
        "BOOLEAN_VALUE": "FALSE_BEFORE_TRUE",
        "TEXT_VALUE": "UNICODE_SCALAR_LEXICAL",
        "ARRAY_CARDINALITY": "MATHEMATICAL_INTEGER",
    }[kind]
    payload = {
        "dimension_position": position,
        "dimension_kind": kind,
        "subject_locator": _schema_locator(),
        "value_schema_id": "0" * 64,
        "comparison_semantics": comparison,
        "ordered_activation_guard_clauses": (
            [] if activation_guards is None else activation_guards
        ),
    }
    return {
        **payload,
        "observable_descriptor_id": validator._semantic_id(  # noqa: SLF001
            validator.OBSERVABLE_DESCRIPTOR_DOMAIN,
            payload,
        ),
    }


def _recurrence_parameters(kind: str) -> dict[str, Any]:
    if kind in {
        "ASCII_DFA_DYNAMIC_PROGRAM_V1",
        "UNICODE_15_NFC_DYNAMIC_PROGRAM_V1",
    }:
        return {
            "text_language_id": "1" * 64,
            "effective_canonical_octet_ceiling": 16,
            "ordered_relation_descriptor_ids": [],
        }
    if kind == "ORDERED_RAW_STRING_PREFIX_FEASIBILITY_V1":
        return {
            "invocation_kind": "MAXIMUM_SLICE_FEASIBILITY",
            "safe_array_node_position": 1,
            "target_array_octets": 2,
            "cardinality_query_kind": "ALL_LEGAL_CARDINALITIES",
            "minimum_array_cardinality": 0,
            "maximum_array_cardinality": 1,
            "array_cardinality": None,
            "fixed_item_count": 0,
            "ordered_fixed_item_scalar_prefix_positions": [],
            "per_string_canonical_octet_ceiling": 3,
        }
    return {
        "invocation_kind": "MAXIMUM_SLICE_FEASIBILITY",
        "safe_identity_node_position": 1,
        "semantic_identity_domain": "ExampleIdentityDomainV1",
        "target_enclosing_canonical_octets": 66,
        "input_prefix_frontier_child_position": 1,
        "fixed_active_prefix_coordinate_count": 0,
        "fixed_primitive_prefix_position": 0,
        "ordered_identity_payload_child_positions": [1],
        "ordered_payload_observable_descriptor_ids": [],
        "ordered_identity_relation_descriptor_ids": [],
    }


def _empty_scalar_prefix_record() -> dict[str, Any]:
    return {
        "prefix_position": 0,
        "parent_prefix_position": None,
        "appended_scalar_value": None,
        "appended_scalar_repeat_count": 0,
        "scalar_count": 0,
        "json_value_octets": 0,
    }


def _ordered_string_scalar_prefix_pool() -> list[dict[str, Any]]:
    return [
        _empty_scalar_prefix_record(),
        {
            "prefix_position": 1,
            "parent_prefix_position": 0,
            "appended_scalar_value": ord("a"),
            "appended_scalar_repeat_count": 1,
            "scalar_count": 1,
            "json_value_octets": 1,
        },
        {
            "prefix_position": 2,
            "parent_prefix_position": 0,
            "appended_scalar_value": ord("b"),
            "appended_scalar_repeat_count": 1,
            "scalar_count": 1,
            "json_value_octets": 1,
        },
        {
            "prefix_position": 3,
            "parent_prefix_position": 1,
            "appended_scalar_value": ord("b"),
            "appended_scalar_repeat_count": 1,
            "scalar_count": 2,
            "json_value_octets": 2,
        },
    ]


def _empty_primitive_prefix_record() -> dict[str, Any]:
    return {
        "prefix_position": 0,
        "parent_prefix_position": None,
        "appended_choice_coordinate_plan_id": None,
        "appended_atom": None,
        "active_atom_count": 0,
    }


def _singleton_lex_interval() -> dict[str, Any]:
    return {
        "interval_position": 0,
        "ordered_interval_blocks": [
            {
                "block_position": 1,
                "block_kind": "PREFIX_SINGLETON",
                "prefix_position": 0,
                "inclusive_next_scalar_minimum": None,
                "inclusive_next_scalar_maximum": None,
                "repeated_lower_bound_scalar": None,
                "minimum_retained_repeat_count": None,
                "maximum_retained_repeat_count": None,
            }
        ],
    }


def _transient_recurrence_catalog(
    validator: ModuleType,
    *,
    kind: str,
    protocol_sha: str,
    state_records: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    scalar_kinds = {
        "ASCII_DFA_DYNAMIC_PROGRAM_V1",
        "UNICODE_15_NFC_DYNAMIC_PROGRAM_V1",
        "ORDERED_RAW_STRING_PREFIX_FEASIBILITY_V1",
    }
    catalog = {
        "catalog_version": validator.TRANSIENT_RECURRENCE_CATALOG_VERSION,
        "recurrence_kind": kind,
        "defining_subject_locator": _schema_locator(),
        "recurrence_parameters": _recurrence_parameters(kind),
        "ordered_scalar_prefix_records": (
            [_empty_scalar_prefix_record()] if kind in scalar_kinds else []
        ),
        "ordered_primitive_prefix_records": (
            [_empty_primitive_prefix_record()]
            if kind == "DERIVED_IDENTITY_PREFIX_FEASIBILITY_V1"
            else []
        ),
        "ordered_lex_interval_records": (
            [_singleton_lex_interval()]
            if kind == "ORDERED_RAW_STRING_PREFIX_FEASIBILITY_V1"
            else []
        ),
        "ordered_state_records": [] if state_records is None else state_records,
    }
    catalog["recurrence_catalog_id"] = validator._semantic_id(  # noqa: SLF001
        validator.TRANSIENT_RECURRENCE_CATALOG_DOMAIN,
        {"maximum_protocol_sha256": protocol_sha, **catalog},
    )
    return catalog


def _rehash_transient_recurrence_catalog(
    validator: ModuleType,
    catalog: dict[str, Any],
    *,
    protocol_sha: str,
) -> str:
    payload = {
        "maximum_protocol_sha256": protocol_sha,
        **{
            name: item
            for name, item in catalog.items()
            if name != "recurrence_catalog_id"
        },
    }
    catalog_id = validator._semantic_id(  # noqa: SLF001
        validator.TRANSIENT_RECURRENCE_CATALOG_DOMAIN,
        payload,
    )
    catalog["recurrence_catalog_id"] = catalog_id
    return catalog_id


def _tagged_materialized(frontier: dict[str, Any]) -> dict[str, Any]:
    return {
        "frontier_encoding_kind": "MATERIALIZED",
        "materialized_frontier": copy.deepcopy(frontier),
        "direct_child_alias": None,
    }


def _tagged_alias(
    *,
    child_position: int,
    child_id: str,
    origin_position: int,
) -> dict[str, Any]:
    return {
        "frontier_encoding_kind": "DIRECT_CHILD_ALIAS",
        "materialized_frontier": None,
        "direct_child_alias": {
            "aliased_child_position": child_position,
            "aliased_child_proof_node_id": child_id,
            "resolved_materialized_origin_position": origin_position,
        },
    }


def _frontier_commitment(
    validator: ModuleType,
    frontier: dict[str, Any],
    *,
    measured_digest: str | None,
    context_digest: str | None,
) -> tuple[dict[str, Any], dict[str, int | str | None]]:
    _, evidence = validator._validate_materialized_frontier(  # noqa: SLF001
        frontier,
        dimensions=[],
        state_signature_id=_empty_signature(validator),
        label="fixture materialized frontier",
    )
    payload = {
        "frontier_version": (
            "riskyieldmm.raw_v8_step2_external_schema_v2.attainable_frontier.v1"
        ),
        "state_signature_id": _empty_signature(validator),
        "state_entry_count": evidence["state_entry_count"],
        "bitmap_run_count": evidence["bitmap_run_count"],
        "expanded_attainable_point_count": evidence["expanded_attainable_point_count"],
        "minimum_attainable_octets": evidence["minimum_attainable_octets"],
        "maximum_attainable_octets": evidence["maximum_attainable_octets"],
        "expanded_frontier_sha256": evidence["expanded_frontier_sha256"],
        "canonical_bitmap_run_frontier_sha256": evidence[
            "canonical_bitmap_run_frontier_sha256"
        ],
        "least_measured_choice_vector_sha256_at_maximum": measured_digest,
        "least_context_choice_vector_sha256_at_maximum": context_digest,
    }
    return (
        {
            **payload,
            "frontier_commitment_id": validator._semantic_id(  # noqa: SLF001
                validator.FRONTIER_COMMITMENT_DOMAIN,
                payload,
            ),
        },
        evidence,
    )


def _alias_v2_proof_dag(
    validator: ModuleType,
) -> tuple[list[dict[str, Any]], dict[str, str], dict[str, int | str | None]]:
    protocol_sha = "a" * 64
    scope_id = "b" * 64
    context_id = "c" * 64
    plan_id = "d" * 64
    empty_choice_digest = hashlib.sha256(_canonical([])).hexdigest()
    frontier = _frontier(_one_length_run(1), validator)

    def finish(node: dict[str, Any]) -> dict[str, Any]:
        node["proof_node_id"] = validator._semantic_id(  # noqa: SLF001
            validator.PROOF_NODE_DOMAIN,
            {
                "maximum_protocol_sha256": protocol_sha,
                "proof_scope_authority_id": scope_id,
                "proof_context_authority_id": context_id,
                "node": {
                    name: item for name, item in node.items() if name != "proof_node_id"
                },
            },
        )
        return node

    leaf_commitment, evidence = _frontier_commitment(
        validator,
        frontier,
        measured_digest=None,
        context_digest=None,
    )
    leaf = finish(
        {
            "proof_node_position": 1,
            "proof_node_kind": "BOOLEAN_VALUE_FRONTIER",
            "subject_locator": _schema_locator(),
            "value_schema_id": "0" * 64,
            "type_name": "ExampleRecord",
            "alternative_name": None,
            "effective_canonical_octet_ceiling": 1,
            "ordered_child_positions": [],
            "ordered_child_proof_node_ids": [],
            "ordered_ancestor_observable_dimensions": [],
            "output_frontier": _tagged_materialized(frontier),
            "frontier_commitment": leaf_commitment,
            "derivation": {
                "derivation_kind": "BOOLEAN_VALUE_FRONTIER",
                "ordered_boolean_values": [False],
            },
        }
    )
    slice_commitment, _ = _frontier_commitment(
        validator,
        frontier,
        measured_digest=None,
        context_digest=empty_choice_digest,
    )
    maximum_slice = finish(
        {
            "proof_node_position": 2,
            "proof_node_kind": "MAXIMUM_SLICE_EXACT_FRONTIER",
            "subject_locator": _schema_locator(),
            "value_schema_id": "0" * 64,
            "type_name": "ExampleRecord",
            "alternative_name": None,
            "effective_canonical_octet_ceiling": 1,
            "ordered_child_positions": [1],
            "ordered_child_proof_node_ids": [leaf["proof_node_id"]],
            "ordered_ancestor_observable_dimensions": [],
            "output_frontier": _tagged_materialized(frontier),
            "frontier_commitment": slice_commitment,
            "derivation": {
                "derivation_kind": "MAXIMUM_SLICE_EXACT_FRONTIER",
                "target_canonical_byte_length": 1,
                "ordered_exact_constraint_bindings": [],
                "ordered_exact_domain_reinstatement_node_positions": [],
                "ordered_choice_coordinate_plan_ids": [plan_id],
                "ordered_transient_recurrence_catalogs": [],
                "upper_frontier_child_position": 1,
            },
        }
    )
    prefix_commitment, _ = _frontier_commitment(
        validator,
        frontier,
        measured_digest=empty_choice_digest,
        context_digest=empty_choice_digest,
    )
    prefix = finish(
        {
            "proof_node_position": 3,
            "proof_node_kind": "LEXICOGRAPHIC_PREFIX_EXCLUSION",
            "subject_locator": _schema_locator(),
            "value_schema_id": "0" * 64,
            "type_name": "ExampleRecord",
            "alternative_name": None,
            "effective_canonical_octet_ceiling": 1,
            "ordered_child_positions": [2],
            "ordered_child_proof_node_ids": [maximum_slice["proof_node_id"]],
            "ordered_ancestor_observable_dimensions": [],
            "output_frontier": _tagged_alias(
                child_position=2,
                child_id=maximum_slice["proof_node_id"],
                origin_position=2,
            ),
            "frontier_commitment": prefix_commitment,
            "derivation": {
                "derivation_kind": "LEXICOGRAPHIC_PREFIX_EXCLUSION",
                "target_canonical_byte_length": 1,
                "choice_scope": "MEASURED_RECORD",
                "choice_coordinate_plan_id": plan_id,
                "coordinate_activation": "INACTIVE",
                "fixed_prefix_coordinate_count": 1,
                "fixed_active_prefix_coordinate_count": 0,
                "selected_atom": _primitive_atom("INACTIVE"),
                "ordered_transient_recurrence_catalogs": [],
                "input_prefix_frontier_child_position": 2,
            },
        }
    )
    codec = finish(
        {
            "proof_node_position": 4,
            "proof_node_kind": "CODEC_INTERSECTION_ATTAINMENT",
            "subject_locator": _schema_locator(),
            "value_schema_id": "0" * 64,
            "type_name": "ExampleRecord",
            "alternative_name": None,
            "effective_canonical_octet_ceiling": 1,
            "ordered_child_positions": [1, 3],
            "ordered_child_proof_node_ids": [
                leaf["proof_node_id"],
                prefix["proof_node_id"],
            ],
            "ordered_ancestor_observable_dimensions": [],
            "output_frontier": _tagged_alias(
                child_position=3,
                child_id=prefix["proof_node_id"],
                origin_position=2,
            ),
            "frontier_commitment": copy.deepcopy(prefix_commitment),
            "derivation": {
                "derivation_kind": "CODEC_INTERSECTION_ATTAINMENT",
                "attainment_mode": "BYTE_MAXIMUM",
                "codec_byte_bound_relation": "LE",
                "codec_octet_limit": 1,
                "owner_codec_byte_bound_relation": None,
                "owner_codec_octet_limit": None,
                "masked_codec_coordinate": None,
                "certified_upper_bound_octets": 1,
                "attaining_witness_canonical_byte_length": 1,
                "attaining_witness_canonical_sha256": "e" * 64,
                "attaining_scope_case_position": None,
                "upper_frontier_child_position": 1,
                "winner_frontier_child_position": 3,
            },
        }
    )
    return (
        [leaf, maximum_slice, prefix, codec],
        {
            "maximum_protocol_sha256": protocol_sha,
            "proof_scope_authority_id": scope_id,
            "proof_context_authority_id": context_id,
        },
        evidence,
    )


def test_direct_checker_is_deterministic_no_go_with_zero_stdout() -> None:
    validator_path = _repository_root() / _VALIDATOR_RELATIVE_PATH
    arguments = (
        str(validator_path),
        "--repository-root",
        str(_repository_root()),
    )
    first = _run_child(*arguments)
    second = _run_child(*arguments)

    assert first.returncode == second.returncode == 2
    assert first.stdout == second.stdout == ""
    assert first.stderr == second.stderr
    assert first.stderr.startswith(_ERROR_PREFIX)
    assert first.stderr.endswith("\n")
    assert first.stderr.count("\n") == 1
    assert "Traceback" not in first.stderr

    encoded = first.stderr.removeprefix(_ERROR_PREFIX).removesuffix("\n")
    report = json.loads(encoded)
    assert encoded.encode("utf-8") == _canonical(report)
    assert report["acceptance_enabled"] is False
    assert report["decision"] == "NO_GO"
    assert report["authority_snapshot_valid"] is True
    assert report["application_witness_physical_pin_valid"] is True
    assert report["max64_context_authority_physical_and_compact_pins_valid"] is True
    assert report["max64_context_authority_root_shape_valid"] is True
    assert report["protocol_externally_pinned"] is True
    assert report["component_status"] == (
        "REJECTED_MAXIMUM_PROTOCOL_V1_PRESEARCH_CAP_CONTRADICTION"
    )
    assert report["v1_presearch_cap_rejection_valid"] is True
    assert report["intrinsic_row_position"] == 62
    assert report["component_choice_coordinate_lower_bound"] == 94_905
    assert report["prefix_proof_node_lower_bound"] == 94_905
    assert report["tie_break_proof_node_lower_bound"] == 94_906
    assert report["maximum_proof_depth_lower_bound"] == 94_906
    assert report["component_coordinate_cap_excess"] == 29_369
    assert report["proof_node_cap_excess_before_base_nodes"] == 29_369
    assert (
        report["tie_break_proof_node_cap_excess_before_descriptor_and_root_nodes"]
        == 29_370
    )
    assert (
        report["maximum_proof_depth_cap_excess_before_descriptor_and_root_nodes"]
        == 29_370
    )
    assert report["row_universe_count"] == 474
    assert report["selected_profile_positions"] == [3, 369, 370, 371, 372, 373]
    assert type(report["protocol_octets"]) is int and report["protocol_octets"] > 0
    assert len(report["protocol_sha256"]) == 64


def test_main_checker_independently_derives_v1_presearch_cap_rejection(
    validator: ModuleType,
    pinned_inventory_and_registry: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    inventory, registry = pinned_inventory_and_registry
    rows = validator._derive_row_universe(registry, inventory)  # noqa: SLF001
    finding = validator._derive_v1_presearch_cap_rejection(  # noqa: SLF001
        registry,
        rows=rows,
    )

    assert finding == validator.V1PresearchCapRejection(
        intrinsic_row_position=62,
        outer_fixed_descriptor_occurrence_count=185,
        inner_array_cardinality_coordinate_count=185,
        inner_text_coordinate_count=94_720,
        component_choice_coordinate_lower_bound=94_905,
        prefix_proof_node_lower_bound=94_905,
        tie_break_proof_node_lower_bound=94_906,
        maximum_proof_depth_lower_bound=94_906,
        component_coordinate_cap_excess=29_369,
        proof_node_cap_excess_before_base_nodes=29_369,
        tie_break_proof_node_cap_excess_before_descriptor_and_root_nodes=29_370,
        maximum_proof_depth_cap_excess_before_descriptor_and_root_nodes=29_370,
    )

    corrupted = copy.deepcopy(registry)
    descriptors = {
        item["type_name"]: item
        for item in corrupted["ordered_external_type_descriptors"]
    }
    schemas = {
        item["value_schema_id"]: item for item in corrupted["value_schema_catalog"]
    }
    member = next(
        item
        for item in descriptors["CapacityMeasurementTargetFieldDescriptorV1"][
            "record_member_descriptors"
        ]
        if item["member_name"] == "value_shape_keys"
    )
    schemas[member["value_schema_id"]]["array_maximum_items"] = 511
    with pytest.raises(
        validator.MaximumProtocolValidationError,
        match="inner key-array authority differs",
    ):
        validator._derive_v1_presearch_cap_rejection(  # noqa: SLF001
            corrupted,
            rows=rows,
        )


def test_scope_hierarchy_derives_complete_408_profile_catalog(
    validator: ModuleType,
    pinned_inventory_and_registry: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    inventory, _ = pinned_inventory_and_registry
    hierarchies = validator._derive_all_profile_scope_hierarchies(  # noqa: SLF001
        inventory,
        label="frozen scope hierarchy",
    )

    assert len(hierarchies) == 408
    assert sum(len(item.ordered_scope_cases) for item in hierarchies) == 475
    assert sum(item.synthetic_axis_count for item in hierarchies) == 33
    axes = [
        event.synthetic_axis
        for hierarchy in hierarchies
        for event in hierarchy.ordered_events
        if event.synthetic_axis is not None
    ]
    assert {
        kind: sum(axis.coordinate_kind == kind for axis in axes)
        for kind in (
            "ROOT_FAMILY_POSITION",
            "MODE_ATTEMPT_POSITION",
            "OBSERVATION_ROLE_POSITION",
            "SEQUENCE_ORDINAL",
        )
    } == {
        "ROOT_FAMILY_POSITION": 4,
        "MODE_ATTEMPT_POSITION": 8,
        "OBSERVATION_ROLE_POSITION": 21,
        "SEQUENCE_ORDINAL": 0,
    }
    assert (
        sum(item.constructed_context_occurrence_count for item in hierarchies) == 22_447
    )
    assert sum(item.context_record_reference_count for item in hierarchies) == 24_295
    assert sum(item.observation_count for item in hierarchies) == 22_447
    assert sum(item.application_invocation_count for item in hierarchies) == 46_267
    assert (
        sum(item.charged_cross_rule_evaluation_count for item in hierarchies)
        == 4_198_491
    )
    assert (
        sum(item.direct_cross_expression_node_count for item in hierarchies)
        == 42_023_961
    )


def test_profile_6_scope_hierarchy_has_exact_events_guards_and_totals(
    validator: ModuleType,
    pinned_inventory_and_registry: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    inventory, _ = pinned_inventory_and_registry
    profile = inventory["operation_contracts"][
        "maximum_constraint_scope_profile_catalog"
    ][5]
    hierarchy = validator._derive_profile_scope_hierarchy(  # noqa: SLF001
        profile,
        validated_inventory=inventory,
        label="profile 6 hierarchy",
    )

    expected_cases = (
        (1, 1, 1, 1, 0),
        (2, 1, 2, 1, 0),
        (3, 2, 1, 1, 0),
        (4, 2, 1, 2, 1),
        (5, 2, 1, 3, 2),
        (6, 2, 2, 1, 0),
        (7, 2, 2, 2, 1),
        (8, 2, 2, 3, 2),
        (9, 2, 3, 1, 0),
        (10, 2, 3, 2, 1),
        (11, 2, 3, 3, 2),
        (12, 3, 1, 1, 0),
        (13, 3, 1, 2, 65),
        (14, 3, 1, 3, 66),
        (15, 4, 1, 1, 0),
        (16, 4, 1, 2, 1),
        (17, 4, 1, 3, 2),
        (18, 5, 1, 1, 0),
        (19, 5, 1, 2, 5),
        (20, 5, 1, 3, 6),
    )
    assert (
        tuple(
            (
                case.scope_case_position,
                case.root_family_position,
                case.mode_attempt_pair_position,
                case.observation_role_position,
                case.measured_sequence_ordinal,
            )
            for case in hierarchy.ordered_scope_cases
        )
        == expected_cases
    )
    assert [
        (
            event.event_kind,
            event.synthetic_axis.coordinate_kind
            if event.synthetic_axis is not None
            else event.scope_case.scope_case_position,
        )
        for event in hierarchy.ordered_events
    ] == [
        ("SYNTHETIC_AXIS", "ROOT_FAMILY_POSITION"),
        ("SYNTHETIC_AXIS", "MODE_ATTEMPT_POSITION"),
        ("SCOPE_CASE", 1),
        ("SCOPE_CASE", 2),
        ("SYNTHETIC_AXIS", "MODE_ATTEMPT_POSITION"),
        ("SYNTHETIC_AXIS", "OBSERVATION_ROLE_POSITION"),
        ("SCOPE_CASE", 3),
        ("SCOPE_CASE", 4),
        ("SCOPE_CASE", 5),
        ("SYNTHETIC_AXIS", "OBSERVATION_ROLE_POSITION"),
        ("SCOPE_CASE", 6),
        ("SCOPE_CASE", 7),
        ("SCOPE_CASE", 8),
        ("SYNTHETIC_AXIS", "OBSERVATION_ROLE_POSITION"),
        ("SCOPE_CASE", 9),
        ("SCOPE_CASE", 10),
        ("SCOPE_CASE", 11),
        ("SYNTHETIC_AXIS", "OBSERVATION_ROLE_POSITION"),
        ("SCOPE_CASE", 12),
        ("SCOPE_CASE", 13),
        ("SCOPE_CASE", 14),
        ("SYNTHETIC_AXIS", "OBSERVATION_ROLE_POSITION"),
        ("SCOPE_CASE", 15),
        ("SCOPE_CASE", 16),
        ("SCOPE_CASE", 17),
        ("SYNTHETIC_AXIS", "OBSERVATION_ROLE_POSITION"),
        ("SCOPE_CASE", 18),
        ("SCOPE_CASE", 19),
        ("SCOPE_CASE", 20),
    ]
    axes = [
        event.synthetic_axis
        for event in hierarchy.ordered_events
        if event.synthetic_axis is not None
    ]
    assert axes[0].ordered_activation_guard_seeds == ()
    assert [
        guard.position_value for guard in axes[1].ordered_activation_guard_seeds
    ] == [1]
    assert [
        guard.position_value for guard in axes[3].ordered_activation_guard_seeds
    ] == [2, 1]
    assert [
        guard.position_value
        for guard in hierarchy.ordered_scope_cases[5].ordered_activation_guard_seeds
    ] == [2, 2, 1]
    assert all(
        axis.subject_locator["record_reference_id"]
        == "/operation_contracts/maximum_constraint_scope_profile_catalog/5"
        and axis.subject_locator["root_type_name"] == "TargetObservationV2"
        and axis.subject_locator["ordered_path_steps"] == []
        for axis in axes
    )
    assert (
        hierarchy.synthetic_axis_count,
        hierarchy.constructed_context_occurrence_count,
        hierarchy.context_record_reference_count,
        hierarchy.observation_count,
        hierarchy.application_invocation_count,
        hierarchy.charged_cross_rule_evaluation_count,
        hierarchy.direct_cross_expression_node_count,
    ) == (9, 260, 329, 260, 569, 48_649, 486_827)


def test_max64_checkpoint_profiles_exclude_inline_witness_from_context_order(
    validator: ModuleType,
    pinned_inventory_and_registry: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    inventory, _ = pinned_inventory_and_registry
    hierarchies = validator._derive_all_profile_scope_hierarchies(  # noqa: SLF001
        inventory,
        label="max64 checkpoint hierarchies",
    )[368:373]

    assert [item.constraint_scope_profile_id for item in hierarchies] == [
        validator.EXPECTED_SELECTED_PROFILE_IDS[position]
        for position in range(369, 374)
    ]
    for hierarchy in hierarchies:
        assert hierarchy.synthetic_axis_count == 0
        assert len(hierarchy.ordered_events) == 1
        case = hierarchy.ordered_scope_cases[0]
        assert (
            case.root_family_position,
            case.mode_attempt_pair_position,
            case.observation_role_position,
            case.measured_sequence_ordinal,
        ) == (1, 1, 1, 64)
        occurrences = case.ordered_constructed_context_occurrences
        assert len(occurrences) == 67
        assert occurrences[0].record_role == "ROOT_RECORD"
        assert [item.external_sequence_ordinal for item in occurrences[1:]] == [
            *range(64),
            65,
            66,
        ]
        assert len(case.ordered_application_invocations) == 137
        assert (
            hierarchy.context_record_reference_count,
            hierarchy.observation_count,
            hierarchy.charged_cross_rule_evaluation_count,
            hierarchy.direct_cross_expression_node_count,
        ) == (71, 67, 12_531, 125_431)


def test_scope_hierarchy_rejects_rehashed_profile_authority_mutations(
    validator: ModuleType,
    pinned_inventory_and_registry: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    inventory, _ = pinned_inventory_and_registry
    profiles = inventory["operation_contracts"][
        "maximum_constraint_scope_profile_catalog"
    ]
    mutations = []

    reordered_pair = copy.deepcopy(profiles[5])
    reordered_pair["ordered_admissible_root_families"][0][
        "ordered_instrumentation_mode_attempt_presence_pairs"
    ].reverse()
    mutations.append(reordered_pair)

    wrong_selector_length = copy.deepcopy(profiles[5])
    wrong_selector_length["ordered_admissible_root_families"][2]["selector_length"] = 63
    mutations.append(wrong_selector_length)

    wrong_checkpoint_ordinal = copy.deepcopy(profiles[368])
    wrong_checkpoint_ordinal["selector_position"] = 63
    mutations.append(wrong_checkpoint_ordinal)

    for mutation in mutations:
        mutation["maximum_constraint_scope_profile_id"] = validator._profile_id(  # noqa: SLF001
            mutation
        )
        with pytest.raises(
            validator.MaximumProtocolValidationError,
            match="differs from rebuilt profile authority",
        ):
            validator._derive_profile_scope_hierarchy(  # noqa: SLF001
                mutation,
                validated_inventory=inventory,
                label="mutated profile",
            )


def test_profile_6_dimension_bindings_use_scope_case_sums_not_family_maxima(
    validator: ModuleType,
    pinned_inventory_and_registry: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    inventory, registry = pinned_inventory_and_registry
    hierarchy = validator._derive_all_profile_scope_hierarchies(  # noqa: SLF001
        inventory,
        label="profile 6 dimension authority",
    )[5]
    descriptor = next(
        item
        for item in registry["ordered_external_type_descriptors"]
        if item["type_name"] == "TargetObservationV2"
    )
    vector = {
        "owner_codec_octet_limit": None,
        "measured_codec_octet_limit": descriptor["codec_octet_limit"],
        "context_record_reference_count": 329,
        "observation_count": 260,
        "application_invocation_count": 569,
        "charged_cross_rule_evaluation_count": 48_649,
        "direct_cross_expression_node_count": 486_827,
    }
    row = validator.RowPlan(
        72,
        "NON_CHECKPOINT_ROOT_FAMILY",
        "TargetObservationV2",
        None,
        hierarchy.constraint_scope_profile_id,
    )
    hierarchy_map = {hierarchy.constraint_scope_profile_id: hierarchy}
    validator._validate_row_dimension_bindings(  # noqa: SLF001
        vector,
        row=row,
        registry=registry,
        inventory=inventory,
        scope_hierarchy_by_profile_id=hierarchy_map,
        label="profile 6 summed dimensions",
    )

    old_family_maxima = {
        **vector,
        "context_record_reference_count": 71,
        "observation_count": 67,
        "application_invocation_count": 137,
        "charged_cross_rule_evaluation_count": 12_531,
        "direct_cross_expression_node_count": 125_431,
    }
    with pytest.raises(validator.MaximumProtocolValidationError):
        validator._validate_row_dimension_bindings(  # noqa: SLF001
            old_family_maxima,
            row=row,
            registry=registry,
            inventory=inventory,
            scope_hierarchy_by_profile_id=hierarchy_map,
            label="profile 6 obsolete family maxima",
        )


def test_profile_6_synthetic_axes_materialize_exact_metered_choice_plans(
    validator: ModuleType,
    pinned_inventory_and_registry: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    inventory, _ = pinned_inventory_and_registry
    hierarchy = validator._derive_all_profile_scope_hierarchies(  # noqa: SLF001
        inventory,
        label="profile 6 materialized scope axes",
    )[5]
    axes = [
        event.synthetic_axis
        for event in hierarchy.ordered_events
        if event.synthetic_axis is not None
    ]
    root_axis = axes[0]
    mode_axis = axes[2]
    role_axis = axes[3]
    assert root_axis.ordered_admissible_position_values == (1, 2, 3, 4, 5)
    assert mode_axis.ordered_admissible_position_values == (1, 2, 3)
    assert role_axis.ordered_admissible_position_values == (1, 2, 3)

    meter = validator.ProofResourceMeter(
        phase=validator.SEED_CAP_DERIVATION_PHASE,
    )
    authority: dict[Any, Any] = {}
    plans = []

    def materialize(axis: Any, position: int) -> dict[str, Any]:
        plan = validator._materialize_synthetic_scope_axis(  # noqa: SLF001
            axis,
            coordinate_plan_position=position,
            prior_plan_id_by_axis_key=authority,
            resource_meter=meter,
            label=f"profile 6 scope plan {position}",
        )
        authority[axis.axis_key] = validator.PriorScopeAxisPlanAuthority(
            axis.axis_key,
            position,
            plan["choice_coordinate_plan_id"],
        )
        plans.append(plan)
        return plan

    root_plan = materialize(root_axis, 101)
    mode_plan = materialize(mode_axis, 102)
    role_plan = materialize(role_axis, 103)

    selected_case = hierarchy.ordered_scope_cases[3]
    sequence_seed = validator.SyntheticScopeAxisSeed(
        validator.ScopeAxisKey(6, "SEQUENCE_ORDINAL", 2, 1, 2),
        "SEQUENCE_ORDINAL",
        copy.deepcopy(root_axis.subject_locator),
        (1, 2),
        selected_case.ordered_activation_guard_seeds,
    )
    sequence_plan = materialize(sequence_seed, 104)

    assert all(set(plan) == validator.CHOICE_COORDINATE_PLAN_KEYS for plan in plans)
    assert [plan["coordinate_scope"] for plan in plans] == ["CONSTRUCTED_CONTEXT"] * 4
    assert [plan["coordinate_kind"] for plan in plans] == [
        "ROOT_FAMILY_POSITION",
        "MODE_ATTEMPT_POSITION",
        "OBSERVATION_ROLE_POSITION",
        "SEQUENCE_ORDINAL",
    ]
    assert all(plan["value_schema_id"] is None for plan in plans)
    assert all(
        _canonical(plan["subject_locator"]) == _canonical(root_plan["subject_locator"])
        for plan in plans
    )
    assert len({plan["choice_coordinate_plan_id"] for plan in plans}) == 4
    assert root_plan["subject_locator"] is not root_axis.subject_locator
    assert root_plan["ordered_activation_guard_clauses"] == []
    assert [
        clause["guard_atom"]["position_value"]
        for clause in mode_plan["ordered_activation_guard_clauses"]
    ] == [2]
    assert [
        clause["guard_atom"]["position_value"]
        for clause in role_plan["ordered_activation_guard_clauses"]
    ] == [2, 1]
    assert [
        clause["guard_atom"]["position_value"]
        for clause in sequence_plan["ordered_activation_guard_clauses"]
    ] == [2, 1, 2]
    assert all(
        clause["guard_atom"]["atom_kind"] == "POSITION"
        for plan in plans
        for clause in plan["ordered_activation_guard_clauses"]
    )
    assert [
        clause["prior_choice_coordinate_plan_id"]
        for clause in sequence_plan["ordered_activation_guard_clauses"]
    ] == [
        root_plan["choice_coordinate_plan_id"],
        mode_plan["choice_coordinate_plan_id"],
        role_plan["choice_coordinate_plan_id"],
    ]
    assert [
        clause["guard_clause_position"]
        for clause in sequence_plan["ordered_activation_guard_clauses"]
    ] == [1, 2, 3]

    expected_hash_preimage_octets = sum(
        len(
            _canonical(
                _semantic_envelope(
                    validator,
                    validator.CHOICE_COORDINATE_PLAN_DOMAIN,
                    {
                        name: value
                        for name, value in plan.items()
                        if name != "choice_coordinate_plan_id"
                    },
                )
            )
        )
        for plan in plans
    )
    assert meter.value("hash_preimage_octets") == expected_hash_preimage_octets
    assert meter.value("component_choice_coordinate_count") == 0
    assert {
        name: value
        for name, value in meter.snapshot().items()
        if name not in {"hash_preimage_octets", "component_choice_coordinate_count"}
    } == dict.fromkeys(
        validator.PROOF_RESOURCE_KEYS
        - {"hash_preimage_octets", "component_choice_coordinate_count"},
        0,
    )
    for plan in plans:
        payload = {
            name: value
            for name, value in plan.items()
            if name != "choice_coordinate_plan_id"
        }
        assert plan["choice_coordinate_plan_id"] == validator._semantic_id(  # noqa: SLF001
            validator.CHOICE_COORDINATE_PLAN_DOMAIN,
            payload,
        )

    root_payload = {
        name: value
        for name, value in root_plan.items()
        if name != "choice_coordinate_plan_id"
    }
    root_preimage_octets = len(
        _canonical(
            _semantic_envelope(
                validator,
                validator.CHOICE_COORDINATE_PLAN_DOMAIN,
                root_payload,
            )
        )
    )
    limits = {
        name: validator.SEED_EXECUTION_SAFETY_LIMITS_V1[name]
        for name in validator.ACCEPTED_PROOF_RESOURCE_LIMIT_KEYS
    }
    limits["hash_preimage_octets"] = root_preimage_octets - 1
    capped_meter = validator.ProofResourceMeter(
        phase=validator.FINAL_PROTOCOL_REBIND_PHASE,
        accepted_limits=limits,
    )
    with pytest.raises(
        validator.MaximumProtocolValidationError,
        match="hash_preimage_octets prospective value",
    ):
        validator._materialize_synthetic_scope_axis(  # noqa: SLF001
            root_axis,
            coordinate_plan_position=101,
            prior_plan_id_by_axis_key={},
            resource_meter=capped_meter,
            label="capped profile 6 root scope plan",
        )
    assert capped_meter.snapshot() == dict.fromkeys(validator.PROOF_RESOURCE_KEYS, 0)


def test_synthetic_scope_axis_rejects_nonprior_or_duplicate_guard_authority(
    validator: ModuleType,
    pinned_inventory_and_registry: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    inventory, _ = pinned_inventory_and_registry
    hierarchy = validator._derive_all_profile_scope_hierarchies(  # noqa: SLF001
        inventory,
        label="profile 6 rejected scope guards",
    )[5]
    axes = [
        event.synthetic_axis
        for event in hierarchy.ordered_events
        if event.synthetic_axis is not None
    ]
    root_axis = axes[0]
    mode_axis = axes[2]
    role_axis = axes[3]
    root_id = "a" * 64
    mode_id = "b" * 64
    root_authority = validator.PriorScopeAxisPlanAuthority(
        root_axis.axis_key,
        8,
        root_id,
    )
    mode_authority = validator.PriorScopeAxisPlanAuthority(
        mode_axis.axis_key,
        9,
        mode_id,
    )

    def reject(
        axis: Any,
        authority: dict[Any, Any],
        match: str,
    ) -> None:
        meter = validator.ProofResourceMeter(
            phase=validator.SEED_CAP_DERIVATION_PHASE,
        )
        before = meter.snapshot()
        with pytest.raises(validator.MaximumProtocolValidationError, match=match):
            validator._materialize_synthetic_scope_axis(  # noqa: SLF001
                axis,
                coordinate_plan_position=10,
                prior_plan_id_by_axis_key=authority,
                resource_meter=meter,
                label="rejected synthetic scope plan",
            )
        assert meter.snapshot() == before

    reject(mode_axis, {}, "no prior plan authority")
    reject(
        mode_axis,
        {
            root_axis.axis_key: validator.PriorScopeAxisPlanAuthority(
                root_axis.axis_key,
                10,
                root_id,
            )
        },
        "not in strict prior-plan order",
    )
    reject(
        mode_axis,
        {
            root_axis.axis_key: validator.PriorScopeAxisPlanAuthority(
                mode_axis.axis_key,
                8,
                root_id,
            )
        },
        "axis authority differs",
    )
    reject(
        role_axis,
        {
            root_axis.axis_key: root_authority,
            mode_axis.axis_key: validator.PriorScopeAxisPlanAuthority(
                mode_axis.axis_key,
                9,
                root_id,
            ),
        },
        "repeats a prior plan ID",
    )
    reject(
        role_axis._replace(
            ordered_activation_guard_seeds=tuple(
                reversed(role_axis.ordered_activation_guard_seeds)
            )
        ),
        {
            root_axis.axis_key: root_authority,
            mode_axis.axis_key: mode_authority,
        },
        "not in strict prior-plan order",
    )
    reject(
        mode_axis,
        {
            root_axis.axis_key: root_authority,
            mode_axis.axis_key: mode_authority,
        },
        "current axis already has plan authority",
    )
    wrong_locator = copy.deepcopy(mode_axis.subject_locator)
    wrong_locator["root_type_name"] = "NotTargetObservationV2"
    reject(
        mode_axis._replace(subject_locator=wrong_locator),
        {root_axis.axis_key: root_authority},
        "synthetic locator root type differs",
    )


def test_synthetic_selected_value_locators_are_exact_and_kind_specific(
    validator: ModuleType,
    pinned_inventory_and_registry: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    inventory, _ = pinned_inventory_and_registry
    hierarchy = validator._derive_all_profile_scope_hierarchies(  # noqa: SLF001
        inventory,
        label="profile 6 synthetic evidence locators",
    )[5]
    axes = [
        event.synthetic_axis
        for event in hierarchy.ordered_events
        if event.synthetic_axis is not None
    ]
    witness_reference_id = "c" * 64
    root_locator = validator._derive_synthetic_selected_value_locator(  # noqa: SLF001
        axes[0].coordinate_kind,
        witness_record_reference_id=None,
        label="root-family selected locator",
    )
    mode_locator = validator._derive_synthetic_selected_value_locator(  # noqa: SLF001
        axes[2].coordinate_kind,
        witness_record_reference_id=witness_reference_id,
        label="mode/attempt selected locator",
    )
    role_locator = validator._derive_synthetic_selected_value_locator(  # noqa: SLF001
        axes[3].coordinate_kind,
        witness_record_reference_id=witness_reference_id,
        label="role selected locator",
    )
    sequence_locator = validator._derive_synthetic_selected_value_locator(  # noqa: SLF001
        "SEQUENCE_ORDINAL",
        witness_record_reference_id=None,
        label="sequence selected locator",
    )

    assert root_locator == {
        "retained_source_kind": "SCOPE_WITNESS_CONTEXT",
        "record_reference_id": None,
        "root_type_name": None,
        "scope_context_member_name": "selected_root_family_position",
        "ordered_path_steps": [],
        "projection_kind": "FROZEN_CATALOG_POSITION",
    }
    assert sequence_locator == {
        **root_locator,
        "scope_context_member_name": "measured_sequence_ordinal",
    }
    observation_context_step = {
        "step_position": 1,
        "step_kind": "RECORD_MEMBER",
        "member_name": "observation_context",
        "member_position": 4,
        "array_ordinal": None,
        "sequence_name": None,
        "union_alternative_position": None,
        "nullable_branch": None,
    }
    observation_role_step = {
        **observation_context_step,
        "step_position": 2,
        "member_name": "observation_role",
    }
    assert mode_locator == {
        "retained_source_kind": "WITNESS_RECORD",
        "record_reference_id": witness_reference_id,
        "root_type_name": "TargetObservationV2",
        "scope_context_member_name": None,
        "ordered_path_steps": [observation_context_step],
        "projection_kind": "FROZEN_CATALOG_POSITION",
    }
    assert role_locator == {
        **mode_locator,
        "ordered_path_steps": [observation_context_step, observation_role_step],
    }
    for locator in (root_locator, mode_locator, role_locator, sequence_locator):
        assert set(locator) == validator.RETAINED_VALUE_LOCATOR_KEYS
        assert (
            validator._validate_retained_value_locator(  # noqa: SLF001
                locator,
                label="derived synthetic selected locator",
            )
            is locator
        )

    invalid_calls = (
        ("ROOT_FAMILY_POSITION", witness_reference_id),
        ("SEQUENCE_ORDINAL", witness_reference_id),
        ("MODE_ATTEMPT_POSITION", None),
        ("MODE_ATTEMPT_POSITION", "C" * 64),
        ("OBSERVATION_ROLE_POSITION", "/not/a/witness/reference"),
        ("NOT_A_SCOPE_COORDINATE", None),
        ([], None),
    )
    for coordinate_kind, reference in invalid_calls:
        with pytest.raises(validator.MaximumProtocolValidationError):
            validator._derive_synthetic_selected_value_locator(  # noqa: SLF001
                coordinate_kind,
                witness_record_reference_id=reference,
                label="invalid synthetic selected locator",
            )


@pytest.mark.parametrize("mode", ("--check", "--write"))
def test_canonical_generator_modes_refuse_without_writing(mode: str) -> None:
    root = _repository_root()
    generator = root / _GENERATOR_RELATIVE_PATH
    paths = [root / relative for relative in _GUARDED_CANONICAL_PATHS]
    before = {path: _path_fingerprint(path) for path in paths}

    result = _run_child(
        str(generator),
        "--repository-root",
        str(root),
        mode,
    )

    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr.startswith("maximum-protocol pilot bootstrap: ")
    assert f"canonical {mode} refused for rejected protocol V1" in result.stderr
    assert (
        "94,905-coordinate and 94,906-node/depth pre-search lower bounds"
        in result.stderr
    )
    assert result.stderr.endswith("\n")
    assert "Traceback" not in result.stderr
    assert {path: _path_fingerprint(path) for path in paths} == before


def test_local_shutdown_mutation_universe_matches_correction_authority(
    validator: ModuleType,
) -> None:
    expected = (
        "maximum_terminal_ingress_automatic_outputs",
        "maximum_terminal_ingress_batches",
        "maximum_terminal_ingress_ciphertext_octets",
        "maximum_terminal_ingress_parser_units",
        "maximum_terminal_ingress_plaintext_octets",
        "maximum_terminal_socket_receive_calls",
        "maximum_terminal_tls_records",
        "maximum_terminal_tls_unwrap_iterations",
        "maximum_terminal_zero_progress_iterations",
        "maximum_tls_control_send_attempts",
        "maximum_websocket_send_attempts",
    )
    assert validator.LOCAL_SHUTDOWN_MUTABLE_LIMIT_MEMBERS == expected
    assert expected == tuple(sorted(expected))
    assert "maximum_peer_shutdown_polls" not in expected

    generator_path = _repository_root() / _GENERATOR_RELATIVE_PATH
    tree = ast.parse(
        generator_path.read_text(encoding="utf-8"),
        filename=str(generator_path),
    )
    generated_lists: list[tuple[str, ...]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        for key, value in zip(node.keys, node.values, strict=True):
            if (
                isinstance(key, ast.Constant)
                and key.value == "ordered_mutable_limit_member_names"
                and isinstance(value, (ast.List, ast.Tuple))
                and all(
                    isinstance(item, ast.Constant) and isinstance(item.value, str)
                    for item in value.elts
                )
            ):
                generated_lists.append(tuple(item.value for item in value.elts))
    assert generated_lists == [expected]


def test_local_shutdown_relation_ids_bind_inventory_and_registry_authorities(
    validator: ModuleType,
) -> None:
    root = _repository_root()
    inventory = json.loads(
        (root / validator.INVENTORY_RELATIVE_PATH).read_text(encoding="utf-8")
    )
    registry = json.loads(
        (root / validator.REGISTRY_RELATIVE_PATH).read_text(encoding="utf-8")
    )
    validator._validate_local_shutdown_relation_authority(  # noqa: SLF001
        inventory,
        registry=registry,
    )
    assert (
        tuple(
            inventory["operation_contracts"]["local_shutdown_intrinsic_limit_relations"]
        )
        == validator.LOCAL_SHUTDOWN_INTRINSIC_RELATION_IDS
    )
    assert validator.LOCAL_SHUTDOWN_INTRINSIC_COMPARISON_NODES == (
        (25, "LE", (4, 15)),
        (26, "LE", (18, 4)),
        (27, "LE", (8, 2)),
        (28, "LE", (10, 6)),
        (29, "LE", (12, 24)),
    )

    corrupted = copy.deepcopy(inventory)
    corrupted["operation_contracts"]["local_shutdown_intrinsic_limit_relations"][0] += (
        " "
    )
    with pytest.raises(
        validator.MaximumProtocolValidationError,
        match="intrinsic relation authority differs",
    ):
        validator._validate_local_shutdown_relation_authority(  # noqa: SLF001
            corrupted,
            registry=registry,
        )

    corrupted_registry = copy.deepcopy(registry)
    rule = next(
        item
        for item in corrupted_registry["ordered_cross_field_rule_descriptors"]
        if item["rule_id"] == validator.LOCAL_SHUTDOWN_INTRINSIC_RULE_ID
    )
    rule["ordered_expression_nodes"][24]["ordered_operand_positions"] = [15, 4]
    with pytest.raises(
        validator.MaximumProtocolValidationError,
        match="relation 1 expression differs",
    ):
        validator._validate_local_shutdown_relation_authority(  # noqa: SLF001
            inventory,
            registry=corrupted_registry,
        )


def _valid_winning_objective(validator: ModuleType) -> dict[str, Any]:
    names = list(validator.LOCAL_SHUTDOWN_MUTABLE_LIMIT_MEMBERS[:2])
    return {
        "changed_limit_field_count": 2,
        "sum_of_absolute_integer_deltas": "123",
        "changed_member_names_in_lexical_order": names,
        "resulting_changed_values_in_that_same_order": [1, 2],
    }


def test_local_shutdown_winning_objective_uses_exact_correction_schema(
    validator: ModuleType,
) -> None:
    objective = _valid_winning_objective(validator)
    assert (
        validator._validate_winning_objective(  # noqa: SLF001
            objective,
            label="winning objective",
        )
        is objective
    )
    assert validator.WINNING_OBJECTIVE_KEYS == frozenset(objective)
    assert "sum_absolute_integer_deltas" not in validator.WINNING_OBJECTIVE_KEYS


def test_derived_identity_terminal_nonterminal_slots_and_parameter_binding(
    validator: ModuleType,
) -> None:
    protocol_sha = "a" * 64
    target = 66
    target_runs = validator._ordered_string_singleton_bitmap(target)  # noqa: SLF001
    primitive_prefixes = [
        _empty_primitive_prefix_record(),
        {
            "prefix_position": 1,
            "parent_prefix_position": 0,
            "appended_choice_coordinate_plan_id": "8" * 64,
            "appended_atom": _primitive_atom("BOOLEAN", False),
            "active_atom_count": 1,
        },
    ]
    bounds = validator.DerivedIdentityRecurrenceBounds(
        target_enclosing_canonical_octets=target,
        fixed_primitive_prefix_position=0,
        observable_descriptor_count=0,
        identity_relation_count=1,
    )

    def validate_state(state: dict[str, Any], *, label: str) -> None:
        validator._validate_derived_identity_state_slots(  # noqa: SLF001
            key_atoms=state["ordered_state_key_atoms"],
            key_cells=state["ordered_state_key_cells"],
            payload_atoms=state["ordered_state_payload_atoms"],
            payload_cells=state["ordered_state_payload_cells"],
            attainable_runs=state["ordered_attainable_length_bitmap_runs"],
            bounds=bounds,
            primitive_prefixes=primitive_prefixes,
            label=label,
            resource_meter=validator.ProofResourceMeter(
                phase=validator.SEED_CAP_DERIVATION_PHASE
            ),
        )

    accepted = _derived_identity_state(
        position=1,
        next_plan_position=0,
        current_prefix_position=1,
        least_prefix_position=1,
        derived_identity="b" * 64,
        relation_values=[True],
        attainable_runs=target_runs,
    )
    rejected = _derived_identity_state(
        position=1,
        next_plan_position=0,
        current_prefix_position=0,
        least_prefix_position=None,
        derived_identity="c" * 64,
        relation_values=[False],
    )
    live_nonterminal = _derived_identity_state(
        position=1,
        next_plan_position=7,
        current_prefix_position=0,
        least_prefix_position=1,
        derived_identity=None,
        relation_values=[None],
        attainable_runs=target_runs,
    )
    dead_nonterminal = _derived_identity_state(
        position=1,
        next_plan_position=7,
        current_prefix_position=0,
        least_prefix_position=None,
        derived_identity=None,
        relation_values=[None],
    )
    for state_label, state in (
        ("accepted terminal", accepted),
        ("rejected terminal", rejected),
        ("live nonterminal", live_nonterminal),
        ("dead nonterminal", dead_nonterminal),
    ):
        validate_state(state, label=state_label)

    corruptions: list[dict[str, Any]] = []
    missing_terminal_identity = copy.deepcopy(rejected)
    missing_terminal_identity["ordered_state_payload_atoms"][1] = _primitive_atom(
        "NULL"
    )
    corruptions.append(missing_terminal_identity)
    rejected_with_completion = copy.deepcopy(rejected)
    rejected_with_completion["ordered_state_payload_atoms"][0] = _primitive_atom(
        "POSITION", 0
    )
    corruptions.append(rejected_with_completion)
    rejected_with_runs = copy.deepcopy(rejected)
    rejected_with_runs["ordered_attainable_length_bitmap_runs"] = target_runs
    corruptions.append(rejected_with_runs)
    accepted_with_wrong_least = copy.deepcopy(accepted)
    accepted_with_wrong_least["ordered_state_payload_atoms"][0] = _primitive_atom(
        "POSITION", 0
    )
    corruptions.append(accepted_with_wrong_least)
    nonterminal_with_identity = copy.deepcopy(dead_nonterminal)
    nonterminal_with_identity["ordered_state_payload_atoms"][1] = _primitive_atom(
        "TEXT", "d" * 64
    )
    corruptions.append(nonterminal_with_identity)
    dead_with_runs = copy.deepcopy(dead_nonterminal)
    dead_with_runs["ordered_attainable_length_bitmap_runs"] = target_runs
    corruptions.append(dead_with_runs)
    for corruption_position, state in enumerate(corruptions, 1):
        with pytest.raises(validator.MaximumProtocolValidationError):
            validate_state(
                state, label=f"derived-identity corruption {corruption_position}"
            )

    catalog = _transient_recurrence_catalog(
        validator,
        kind="DERIVED_IDENTITY_PREFIX_FEASIBILITY_V1",
        protocol_sha=protocol_sha,
        state_records=[
            _derived_identity_state(
                position=1,
                next_plan_position=0,
                current_prefix_position=0,
                least_prefix_position=0,
                derived_identity="e" * 64,
                relation_values=[True],
                attainable_runs=target_runs,
            )
        ],
    )
    catalog["recurrence_parameters"]["ordered_identity_relation_descriptor_ids"] = [
        "9" * 64
    ]
    catalog_id = _rehash_transient_recurrence_catalog(
        validator,
        catalog,
        protocol_sha=protocol_sha,
    )
    assert (
        validator._validate_transient_recurrence_catalog(  # noqa: SLF001
            catalog,
            maximum_protocol_sha256=protocol_sha,
            expected_catalog_id=catalog_id,
            allowed_prior_catalog_ids=frozenset(),
            label="derived-identity integrated catalog",
        ).catalog
        is catalog
    )

    wrong_prefix_count = copy.deepcopy(catalog)
    wrong_prefix_count["recurrence_parameters"][
        "fixed_active_prefix_coordinate_count"
    ] = 1
    wrong_id = _rehash_transient_recurrence_catalog(
        validator,
        wrong_prefix_count,
        protocol_sha=protocol_sha,
    )
    with pytest.raises(
        validator.MaximumProtocolValidationError,
        match="fixed prefix/count binding differs",
    ):
        validator._validate_transient_recurrence_catalog(  # noqa: SLF001
            wrong_prefix_count,
            maximum_protocol_sha256=protocol_sha,
            expected_catalog_id=wrong_id,
            allowed_prior_catalog_ids=frozenset(),
            label="wrong derived-identity fixed prefix count",
        )


def test_ascii_and_unicode_recurrence_state_slots_close_local_layouts(
    validator: ModuleType,
) -> None:
    protocol_sha = "f" * 64

    def state_record(
        *,
        key_atoms: list[dict[str, Any]],
        payload_atoms: list[dict[str, Any]],
        runs: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return {
            "state_position": 1,
            "ordered_state_key_atoms": key_atoms,
            "ordered_state_key_cells": [],
            "ordered_state_payload_atoms": payload_atoms,
            "ordered_state_payload_cells": [],
            "ordered_attainable_length_bitmap_runs": runs,
        }

    ascii_prefixes = [
        _empty_scalar_prefix_record(),
        {
            "prefix_position": 1,
            "parent_prefix_position": 0,
            "appended_scalar_value": ord("a"),
            "appended_scalar_repeat_count": 1,
            "scalar_count": 1,
            "json_value_octets": 1,
        },
    ]
    ascii_state = state_record(
        key_atoms=[
            _primitive_atom("POSITION", 1),
            _primitive_atom("POSITION", 2),
            _primitive_atom("SAFE_INTEGER", 1),
        ],
        payload_atoms=[_primitive_atom("POSITION", 1)],
        runs=validator._ordered_string_singleton_bitmap(3),  # noqa: SLF001
    )
    ascii_catalog = _transient_recurrence_catalog(
        validator,
        kind="ASCII_DFA_DYNAMIC_PROGRAM_V1",
        protocol_sha=protocol_sha,
        state_records=[ascii_state],
    )
    ascii_catalog["ordered_scalar_prefix_records"] = ascii_prefixes
    ascii_id = _rehash_transient_recurrence_catalog(
        validator,
        ascii_catalog,
        protocol_sha=protocol_sha,
    )
    assert (
        validator._validate_transient_recurrence_catalog(  # noqa: SLF001
            ascii_catalog,
            maximum_protocol_sha256=protocol_sha,
            expected_catalog_id=ascii_id,
            allowed_prior_catalog_ids=frozenset(),
            label="ASCII integrated state",
        ).catalog
        is ascii_catalog
    )

    corrupt_ascii = copy.deepcopy(ascii_catalog)
    corrupt_ascii["ordered_state_records"][0]["ordered_state_key_atoms"][0] = (
        _primitive_atom("POSITION", 0)
    )
    corrupt_ascii_id = _rehash_transient_recurrence_catalog(
        validator,
        corrupt_ascii,
        protocol_sha=protocol_sha,
    )
    with pytest.raises(
        validator.MaximumProtocolValidationError,
        match="least prefix/count binding differs",
    ):
        validator._validate_transient_recurrence_catalog(  # noqa: SLF001
            corrupt_ascii,
            maximum_protocol_sha256=protocol_sha,
            expected_catalog_id=corrupt_ascii_id,
            allowed_prior_catalog_ids=frozenset(),
            label="corrupt ASCII prefix count",
        )

    unicode_prefixes = [
        _empty_scalar_prefix_record(),
        {
            "prefix_position": 1,
            "parent_prefix_position": 0,
            "appended_scalar_value": ord("é"),
            "appended_scalar_repeat_count": 1,
            "scalar_count": 1,
            "json_value_octets": 2,
        },
    ]
    unicode_state = state_record(
        key_atoms=[
            _primitive_atom("POSITION", 1),
            _primitive_atom("SAFE_INTEGER", 0),
            _primitive_atom("SAFE_INTEGER", 0),
            _primitive_atom("POSITION", 1),
            _primitive_atom("POSITION", 1),
            _primitive_atom("POSITION", 1),
        ],
        payload_atoms=[_primitive_atom("POSITION", 1)],
        runs=validator._ordered_string_singleton_bitmap(4),  # noqa: SLF001
    )
    unicode_catalog = _transient_recurrence_catalog(
        validator,
        kind="UNICODE_15_NFC_DYNAMIC_PROGRAM_V1",
        protocol_sha=protocol_sha,
        state_records=[unicode_state],
    )
    unicode_catalog["ordered_scalar_prefix_records"] = unicode_prefixes
    unicode_id = _rehash_transient_recurrence_catalog(
        validator,
        unicode_catalog,
        protocol_sha=protocol_sha,
    )
    assert (
        validator._validate_transient_recurrence_catalog(  # noqa: SLF001
            unicode_catalog,
            maximum_protocol_sha256=protocol_sha,
            expected_catalog_id=unicode_id,
            allowed_prior_catalog_ids=frozenset(),
            label="Unicode integrated state",
        ).catalog
        is unicode_catalog
    )

    corrupt_unicode = copy.deepcopy(unicode_catalog)
    corrupt_unicode["ordered_state_records"][0]["ordered_state_key_atoms"][3] = (
        _primitive_atom("POSITION", 0)
    )
    corrupt_unicode_id = _rehash_transient_recurrence_catalog(
        validator,
        corrupt_unicode,
        protocol_sha=protocol_sha,
    )
    with pytest.raises(
        validator.MaximumProtocolValidationError,
        match="trim-class emptiness differs",
    ):
        validator._validate_transient_recurrence_catalog(  # noqa: SLF001
            corrupt_unicode,
            maximum_protocol_sha256=protocol_sha,
            expected_catalog_id=corrupt_unicode_id,
            allowed_prior_catalog_ids=frozenset(),
            label="corrupt Unicode trim state",
        )

    bad_language = copy.deepcopy(ascii_catalog)
    bad_language["recurrence_parameters"]["text_language_id"] = "not-a-sha"
    bad_language_id = _rehash_transient_recurrence_catalog(
        validator,
        bad_language,
        protocol_sha=protocol_sha,
    )
    with pytest.raises(validator.MaximumProtocolValidationError):
        validator._validate_transient_recurrence_catalog(  # noqa: SLF001
            bad_language,
            maximum_protocol_sha256=protocol_sha,
            expected_catalog_id=bad_language_id,
            allowed_prior_catalog_ids=frozenset(),
            label="corrupt text language authority",
        )


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        (
            lambda value: value.update(
                {
                    "sum_absolute_integer_deltas": value.pop(
                        "sum_of_absolute_integer_deltas"
                    )
                }
            ),
            "keys differ",
        ),
        (
            lambda value: value.__setitem__("sum_of_absolute_integer_deltas", "0123"),
            "canonical unsigned-128",
        ),
        (
            lambda value: value.__setitem__(
                "sum_of_absolute_integer_deltas", str(1 << 128)
            ),
            "exceeds checked UInt128",
        ),
        (
            lambda value: value.__setitem__(
                "changed_member_names_in_lexical_order",
                list(reversed(value["changed_member_names_in_lexical_order"])),
            ),
            "changed member names differ",
        ),
        (
            lambda value: value.__setitem__("changed_limit_field_count", 1),
            "length differs",
        ),
        (
            lambda value: value[
                "resulting_changed_values_in_that_same_order"
            ].__setitem__(0, True),
            "changed value 1",
        ),
    ),
)
def test_local_shutdown_winning_objective_rejects_noncanonical_variants(
    validator: ModuleType,
    mutation: Any,
    message: str,
) -> None:
    objective = _valid_winning_objective(validator)
    mutation(objective)
    with pytest.raises(validator.MaximumProtocolValidationError, match=message):
        validator._validate_winning_objective(  # noqa: SLF001
            objective,
            label="winning objective",
        )


def _local_shutdown_outer_artifact(
    validator: ModuleType,
    *,
    inventory: dict[str, Any],
    registry: dict[str, Any],
    protocol_sha256: str,
) -> dict[str, Any]:
    baseline = inventory["fixture_records"]["operation_specs"]["LOCAL_SHUTDOWN"]
    mutated = copy.deepcopy(baseline)
    mutated["spec"]["maximum_terminal_ingress_batches"] = 8_000
    mutated_descriptor = next(
        item
        for item in registry["ordered_external_type_descriptors"]
        if item["type_name"] == "CapacityMeasurementOperationSpec"
    )
    mutated_payload = {
        name: mutated[name]
        for name in mutated_descriptor["identity_payload_member_order"]
    }
    mutated["operation_spec_id"] = validator._semantic_id(  # noqa: SLF001
        mutated_descriptor["described_record_domain"], mutated_payload
    )

    prospective = copy.deepcopy(
        inventory["fixture_records"]["operation_results"]["LOCAL_SHUTDOWN"]
    )
    attempts = [
        hashlib.sha256(f"attempt:{item}".encode()).hexdigest() for item in range(8_000)
    ]
    results = [
        hashlib.sha256(f"result:{item}".encode()).hexdigest() for item in range(8_000)
    ]
    prospective["result"]["ordered_terminal_ingress_read_attempt_event_ids"] = attempts
    prospective["result"]["ordered_terminal_ingress_read_result_event_ids"] = results
    prospective["result"]["final_terminal_ingress_batch_count"] = len(attempts)
    result_descriptor = next(
        item
        for item in registry["ordered_external_type_descriptors"]
        if item["type_name"] == "CapacityMeasurementOperationResultEvidence"
    )
    result_payload = {
        name: prospective[name]
        for name in result_descriptor["identity_payload_member_order"]
    }
    prospective["result_evidence_id"] = validator._semantic_id(  # noqa: SLF001
        result_descriptor["described_record_domain"], result_payload
    )
    prospective_length = len(_canonical(prospective))
    assert prospective_length >= 524_288

    profile = inventory["operation_contracts"][
        "maximum_constraint_scope_profile_catalog"
    ][2]
    reference = _v3_record_reference(
        validator,
        inventory=inventory,
        pointer=validator.LOCAL_SHUTDOWN_BASELINE_SPEC_POINTER,
        record_type_name=validator.LOCAL_SHUTDOWN_BASELINE_SPEC_TYPE_NAME,
        record_identity_field="operation_spec_id",
    )
    objective = {
        "changed_limit_field_count": 1,
        "sum_of_absolute_integer_deltas": "7999",
        "changed_member_names_in_lexical_order": ["maximum_terminal_ingress_batches"],
        "resulting_changed_values_in_that_same_order": [8_000],
    }
    certificate = {
        "certificate_version": (
            "riskyieldmm.raw_v8_step2_external_schema_v2."
            "local_shutdown_minimality_certificate.v1"
        ),
        "maximum_protocol_sha256": protocol_sha256,
        "baseline_operation_spec_id": baseline["operation_spec_id"],
        "mutated_operation_spec_id": mutated["operation_spec_id"],
        "mutable_limit_member_count": 11,
        "ordered_mutable_limit_member_names": list(
            validator.LOCAL_SHUTDOWN_MUTABLE_LIMIT_MEMBERS
        ),
        "winning_objective": objective,
        "ordered_proof_nodes": [
            {"proof_node_kind": "LOCAL_SHUTDOWN_MINIMALITY_FRONTIER"}
        ],
        "root_proof_node_position": 1,
    }
    certificate["local_shutdown_minimality_certificate_id"] = validator._semantic_id(  # noqa: SLF001
        validator.LOCAL_SHUTDOWN_MINIMALITY_CERTIFICATE_DOMAIN,
        certificate,
    )
    artifact = {
        "artifact_version": (
            "riskyieldmm.raw_v8_step2_external_schema_v2."
            "local_shutdown_unrepresentable.v1"
        ),
        "canonicalization_version": validator.CANONICALIZATION_VERSION,
        "measurement_schema_version": validator.MEASUREMENT_SCHEMA_VERSION,
        "maximum_protocol_sha256": protocol_sha256,
        "source_inventory_sha256": validator.INVENTORY_SEMANTIC_ID,
        "external_schema_registry_id": validator.REGISTRY_ID,
        "rule_literal_authority_sha256": validator.LITERAL_AUTHORITY_RAW_SHA256,
        "constraint_scope_profile_id": profile["maximum_constraint_scope_profile_id"],
        "baseline_spec_record_reference": reference,
        "mutated_limit_members": [
            {
                "domain_position": 1,
                "member_name": "maximum_terminal_ingress_batches",
                "baseline_value": 1,
                "mutated_value": 8_000,
                "absolute_delta": 7_999,
            }
        ],
        "mutated_spec": mutated,
        "changed_limit_field_count": 1,
        "sum_absolute_integer_deltas": "7999",
        "prospective_result": prospective,
        "prospective_result_canonical_byte_length": prospective_length,
        "outer_codec_byte_bound_relation": "LT",
        "outer_codec_octet_limit": 524_288,
        "expected_rejection_coordinate": {
            "record_type_name": "CapacityMeasurementOperationResultEvidence",
            "typed_member_path": [],
            "validation_layer": "CODEC_BOUND",
            "codec_byte_bound_relation": "LT",
            "codec_octet_limit": 524_288,
            "observed_canonical_byte_length": prospective_length,
            "failure_class": "CODEC_OCTET_LIMIT_VIOLATION",
        },
        "minimality_certificate": certificate,
    }
    artifact["local_shutdown_unrepresentable_id"] = validator._semantic_id(  # noqa: SLF001
        validator.LOCAL_SHUTDOWN_UNREPRESENTABLE_DOMAIN,
        artifact,
    )
    return artifact


def test_local_shutdown_outer_artifact_validates_every_nonproof_duplicate(
    validator: ModuleType,
    pinned_inventory_and_registry: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    inventory, registry = pinned_inventory_and_registry
    protocol_sha256 = "a" * 64
    artifact = _local_shutdown_outer_artifact(
        validator,
        inventory=inventory,
        registry=registry,
        protocol_sha256=protocol_sha256,
    )
    callback_calls: list[tuple[int, int]] = []

    def validate_minimal_proof(
        nodes: list[Any],
        *,
        root_position: int,
        resource_meter: Any,
        **_: Any,
    ) -> None:
        assert nodes == [{"proof_node_kind": "LOCAL_SHUTDOWN_MINIMALITY_FRONTIER"}]
        callback_calls.append((len(nodes), root_position))
        resource_meter.add("proof_node_count", len(nodes))

    meter = validator.ProofResourceMeter(phase=validator.SEED_CAP_DERIVATION_PHASE)
    assert (
        validator._validate_local_shutdown_unrepresentable_outer_artifact(  # noqa: SLF001
            artifact,
            maximum_protocol_sha256=protocol_sha256,
            validated_inventory=inventory,
            validated_registry=registry,
            resource_meter=meter,
            proof_dag_validator=validate_minimal_proof,
            label="local counterexample",
        )
        is artifact
    )
    assert callback_calls == [(1, 1)]
    assert meter.value("proof_node_count") == 1


def test_local_shutdown_outer_artifact_rejects_duplicate_arithmetic_before_proof(
    validator: ModuleType,
    pinned_inventory_and_registry: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    inventory, registry = pinned_inventory_and_registry
    protocol_sha256 = "b" * 64
    artifact = _local_shutdown_outer_artifact(
        validator,
        inventory=inventory,
        registry=registry,
        protocol_sha256=protocol_sha256,
    )
    artifact["changed_limit_field_count"] = 2
    callback_called = False

    def forbidden_callback(*_: Any, **__: Any) -> None:
        nonlocal callback_called
        callback_called = True

    with pytest.raises(
        validator.MaximumProtocolValidationError,
        match="duplicated mutation count/delta differs",
    ):
        validator._validate_local_shutdown_unrepresentable_outer_artifact(  # noqa: SLF001
            artifact,
            maximum_protocol_sha256=protocol_sha256,
            validated_inventory=inventory,
            validated_registry=registry,
            resource_meter=validator.ProofResourceMeter(
                phase=validator.SEED_CAP_DERIVATION_PHASE
            ),
            proof_dag_validator=forbidden_callback,
            label="contradictory local counterexample",
        )
    assert callback_called is False


def test_local_shutdown_minimality_outer_shell_fails_closed_without_proof_checker(
    validator: ModuleType,
    pinned_inventory_and_registry: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    inventory, registry = pinned_inventory_and_registry
    protocol_sha256 = "c" * 64
    artifact = _local_shutdown_outer_artifact(
        validator,
        inventory=inventory,
        registry=registry,
        protocol_sha256=protocol_sha256,
    )
    certificate = artifact["minimality_certificate"]
    with pytest.raises(
        validator.MaximumProtocolValidationError,
        match="proof DAG validation is unavailable",
    ):
        validator._validate_local_shutdown_minimality_certificate_outer(  # noqa: SLF001
            certificate,
            maximum_protocol_sha256=protocol_sha256,
            baseline_operation_spec_id=certificate["baseline_operation_spec_id"],
            mutated_operation_spec_id=certificate["mutated_operation_spec_id"],
            prospective_result_canonical_byte_length=artifact[
                "prospective_result_canonical_byte_length"
            ],
            prospective_result_canonical_sha256=hashlib.sha256(
                _canonical(artifact["prospective_result"])
            ).hexdigest(),
            proof_scope_authority_id="a" * 64,
            proof_context_authority_id="b" * 64,
            validated_inventory=inventory,
            validated_registry=registry,
            expected_winning_objective=certificate["winning_objective"],
            resource_meter=validator.ProofResourceMeter(
                phase=validator.SEED_CAP_DERIVATION_PHASE
            ),
            proof_dag_validator=None,
            label="minimality shell",
        )


def test_local_shutdown_proof_authorities_are_derived_from_enclosing_values(
    validator: ModuleType,
) -> None:
    meter = validator.ProofResourceMeter(phase=validator.SEED_CAP_DERIVATION_PHASE)
    scope_id, context_id = validator._derive_local_shutdown_proof_authority_ids(  # noqa: SLF001
        maximum_protocol_sha256="1" * 64,
        constraint_scope_profile_id=validator.EXPECTED_SELECTED_PROFILE_IDS[3],
        baseline_operation_spec_id="2" * 64,
        mutated_operation_spec_id="3" * 64,
        prospective_result_canonical_byte_length=524_288,
        prospective_result_canonical_sha256="4" * 64,
        resource_meter=meter,
    )
    expected_scope = validator._semantic_id(  # noqa: SLF001
        validator.LOCAL_SHUTDOWN_PROOF_SCOPE_DOMAIN,
        {
            "maximum_protocol_sha256": "1" * 64,
            "source_inventory_sha256": validator.INVENTORY_SEMANTIC_ID,
            "external_schema_registry_id": validator.REGISTRY_ID,
            "rule_literal_authority_sha256": validator.LITERAL_AUTHORITY_RAW_SHA256,
            "constraint_scope_profile_id": validator.EXPECTED_SELECTED_PROFILE_IDS[3],
            "baseline_operation_spec_id": "2" * 64,
            "ordered_mutable_limit_member_names": list(
                validator.LOCAL_SHUTDOWN_MUTABLE_LIMIT_MEMBERS
            ),
        },
    )
    expected_context = validator._semantic_id(  # noqa: SLF001
        validator.LOCAL_SHUTDOWN_PROOF_CONTEXT_DOMAIN,
        {
            "maximum_protocol_sha256": "1" * 64,
            "mutated_operation_spec_id": "3" * 64,
            "prospective_result_canonical_byte_length": 524_288,
            "prospective_result_canonical_sha256": "4" * 64,
        },
    )
    assert (scope_id, context_id) == (expected_scope, expected_context)
    assert meter.value("hash_preimage_octets") > 0


def _local_baseline_prefix_values(validator: ModuleType) -> list[int]:
    return [
        validator.LOCAL_SHUTDOWN_BASELINE_MUTABLE_VALUES[name]
        for name in validator.LOCAL_SHUTDOWN_MUTABLE_LIMIT_MEMBERS
    ]


def test_local_objective_prefix_is_derived_from_exact_lexical_baseline(
    validator: ModuleType,
) -> None:
    values = _local_baseline_prefix_values(validator)
    values[0] = 2
    values[3] = 3
    objective, changed_positions = validator._derive_local_shutdown_objective_prefix(  # noqa: SLF001
        values,
        label="objective prefix",
    )
    assert objective == {
        "objective_prefix_version": validator.LOCAL_SHUTDOWN_OBJECTIVE_PREFIX_VERSION,
        "processed_mutable_member_count": 11,
        "changed_limit_field_count": 2,
        "sum_of_absolute_integer_deltas": "3",
        "changed_member_names_in_lexical_order": [
            "maximum_terminal_ingress_automatic_outputs",
            "maximum_terminal_ingress_parser_units",
        ],
        "resulting_changed_values_in_that_same_order": [2, 3],
    }
    assert changed_positions == (8, 9)
    winning = {
        name: item
        for name, item in objective.items()
        if name not in {"objective_prefix_version", "processed_mutable_member_count"}
    }
    validator._validate_winning_objective(  # noqa: SLF001
        winning,
        label="derived winning objective",
    )


def test_local_objective_comparison_uses_uint128_not_decimal_lexical_order(
    validator: ModuleType,
) -> None:
    base = {
        "changed_limit_field_count": 1,
        "changed_member_names_in_lexical_order": ["maximum_terminal_ingress_batches"],
        "resulting_changed_values_in_that_same_order": [1],
    }
    nine = {**base, "sum_of_absolute_integer_deltas": "9"}
    ten = {**base, "sum_of_absolute_integer_deltas": "10"}
    assert validator._local_shutdown_objective_sort_key(  # noqa: SLF001
        nine,
        label="nine",
    ) < validator._local_shutdown_objective_sort_key(  # noqa: SLF001
        ten,
        label="ten",
    )


def test_local_equivalence_key_forbids_partial_dominance_shortcuts(
    validator: ModuleType,
) -> None:
    relations = ["UNRESOLVED"] * 5
    first = validator._derive_local_shutdown_equivalence_key(  # noqa: SLF001
        processed_values=[1],
        ordered_intrinsic_relation_states=relations,
        intrinsically_feasible=True,
        prospective_result_frontier_commitment_id=None,
        label="first partial key",
    )
    second = validator._derive_local_shutdown_equivalence_key(  # noqa: SLF001
        processed_values=[2],
        ordered_intrinsic_relation_states=relations,
        intrinsically_feasible=True,
        prospective_result_frontier_commitment_id=None,
        label="second partial key",
    )
    assert first["continuation_equivalence_kind"] == "EXACT_PROCESSED_PREFIX"
    assert first["ordered_exact_processed_values"] == [1]
    assert first != second

    with pytest.raises(
        validator.MaximumProtocolValidationError,
        match="exact-prefix key has a prospective commitment",
    ):
        validator._derive_local_shutdown_equivalence_key(  # noqa: SLF001
            processed_values=[1],
            ordered_intrinsic_relation_states=relations,
            intrinsically_feasible=True,
            prospective_result_frontier_commitment_id="a" * 64,
            label="invalid partial key",
        )


def test_local_intrinsic_relation_states_are_derived_at_operand_availability(
    validator: ModuleType,
) -> None:
    baseline = _local_baseline_prefix_values(validator)
    assert (
        validator._derive_local_shutdown_intrinsic_relation_states(  # noqa: SLF001
            baseline[:1],
            label="one-value prefix",
        )
        == ["UNRESOLVED"] * 5
    )
    assert (
        validator._derive_local_shutdown_intrinsic_relation_states(  # noqa: SLF001
            baseline[:4],
            label="parser prefix",
        )
        == ["UNRESOLVED", "UNRESOLVED", "UNRESOLVED", "TRUE", "UNRESOLVED"]
    )
    assert (
        validator._derive_local_shutdown_intrinsic_relation_states(  # noqa: SLF001
            baseline,
            label="complete baseline",
        )
        == ["TRUE"] * 5
    )

    invalid = list(baseline)
    invalid[0] = 2
    assert (
        validator._derive_local_shutdown_intrinsic_relation_states(  # noqa: SLF001
            invalid,
            label="intrinsically invalid complete vector",
        )[3]
        == "FALSE"
    )


def test_local_complete_dominance_groups_only_equal_prospective_frontiers(
    validator: ModuleType,
) -> None:
    baseline = _local_baseline_prefix_values(validator)
    changed = list(baseline)
    changed[2] += 1
    commitment = "a" * 64
    baseline_key = validator._derive_local_shutdown_equivalence_key(  # noqa: SLF001
        processed_values=baseline,
        ordered_intrinsic_relation_states=["TRUE"] * 5,
        intrinsically_feasible=True,
        prospective_result_frontier_commitment_id=commitment,
        label="baseline complete key",
    )
    changed_key = validator._derive_local_shutdown_equivalence_key(  # noqa: SLF001
        processed_values=changed,
        ordered_intrinsic_relation_states=["TRUE"] * 5,
        intrinsically_feasible=True,
        prospective_result_frontier_commitment_id=commitment,
        label="changed complete key",
    )
    assert baseline_key == changed_key
    assert baseline_key["ordered_exact_processed_values"] is None

    another_frontier = validator._derive_local_shutdown_equivalence_key(  # noqa: SLF001
        processed_values=changed,
        ordered_intrinsic_relation_states=["TRUE"] * 5,
        intrinsically_feasible=True,
        prospective_result_frontier_commitment_id="b" * 64,
        label="different complete frontier",
    )
    assert baseline_key != another_frontier

    with pytest.raises(
        validator.MaximumProtocolValidationError,
        match="complete state retains an unresolved relation",
    ):
        validator._derive_local_shutdown_equivalence_key(  # noqa: SLF001
            processed_values=baseline,
            ordered_intrinsic_relation_states=["TRUE"] * 4 + ["UNRESOLVED"],
            intrinsically_feasible=True,
            prospective_result_frontier_commitment_id=commitment,
            label="unresolved complete key",
        )


def _minimal_local_recurrence_fixture(
    validator: ModuleType,
) -> dict[str, Any]:
    values = _local_baseline_prefix_values(validator)
    winning_length = 524_288
    frontier = _frontier(_one_length_run(winning_length), validator)
    commitment, _ = _frontier_commitment(
        validator,
        frontier,
        measured_digest=None,
        context_digest=None,
    )
    winning_sha256 = "d" * 64
    boundary_root_position = 1
    proof_nodes = [{"frontier_commitment": commitment}]
    boundary_witnesses = [
        {
            "candidate_mutated_spec": {
                "spec": dict(
                    zip(
                        validator.LOCAL_SHUTDOWN_MUTABLE_LIMIT_MEMBERS,
                        values,
                        strict=True,
                    )
                )
            },
            "prospective_result_canonical_byte_length": winning_length,
            "prospective_result_canonical_sha256": winning_sha256,
        }
    ]
    states: list[dict[str, Any]] = []
    for processed_count in range(len(values) + 1):
        prefix = values[:processed_count]
        objective, changed_positions = (
            validator._derive_local_shutdown_objective_prefix(  # noqa: SLF001
                prefix,
                label=f"fixture state {processed_count + 1}",
            )
        )
        relation_states = validator._derive_local_shutdown_intrinsic_relation_states(  # noqa: SLF001
            prefix,
            label=f"fixture state {processed_count + 1}",
        )
        payload = {
            "state_position": processed_count + 1,
            "processed_mutable_member_count": processed_count,
            "ordered_processed_values": prefix,
            "ordered_changed_domain_positions": list(changed_positions),
            "sum_absolute_integer_deltas": objective["sum_of_absolute_integer_deltas"],
            "ordered_intrinsic_relation_states": relation_states,
            "prospective_result_root_position": (
                boundary_root_position if processed_count == len(values) else None
            ),
            "state_status": "RETAINED",
        }
        states.append(
            {
                **payload,
                "recurrence_state_id": validator._semantic_id(  # noqa: SLF001
                    validator.LOCAL_SHUTDOWN_RECURRENCE_STATE_DOMAIN,
                    payload,
                ),
            }
        )
    breakpoints: list[dict[str, Any]] = []
    transitions: list[dict[str, Any]] = []
    for offset, candidate_value in enumerate(values):
        source_position = offset + 1
        breakpoint_position = offset + 1
        member_name = validator.LOCAL_SHUTDOWN_MUTABLE_LIMIT_MEMBERS[offset]
        breakpoints.append(
            {
                "breakpoint_position": breakpoint_position,
                "source_state_position": source_position,
                "domain_position": validator.LOCAL_SHUTDOWN_LIMIT_DOMAIN_POSITIONS[
                    member_name
                ],
                "member_name": member_name,
                "breakpoint_kind": "BASELINE",
                "candidate_value": candidate_value,
                "source_relation_id": None,
                "prospective_result_root_position": None,
            }
        )
        transition_payload = {
            "transition_position": breakpoint_position,
            "source_state_position": source_position,
            "breakpoint_position": breakpoint_position,
            "result_state_position": source_position + 1,
            "transition_kind": "EXTEND_RETAINED",
            "failed_relation_id": None,
        }
        transitions.append(
            {
                **transition_payload,
                "recurrence_transition_id": validator._semantic_id(  # noqa: SLF001
                    validator.LOCAL_SHUTDOWN_RECURRENCE_TRANSITION_DOMAIN,
                    transition_payload,
                ),
            }
        )
    return {
        "state_values": states,
        "transition_values": transitions,
        "dominance_deletion_values": [],
        "breakpoint_values": breakpoints,
        "interval_exclusion_values": [],
        "boundary_root_positions": [boundary_root_position],
        "boundary_witnesses": boundary_witnesses,
        "proof_nodes": proof_nodes,
        "expected_winning_objective": {
            "changed_limit_field_count": 0,
            "sum_of_absolute_integer_deltas": "0",
            "changed_member_names_in_lexical_order": [],
            "resulting_changed_values_in_that_same_order": [],
        },
        "expected_winning_length": winning_length,
        "expected_winning_sha256": winning_sha256,
    }


def _add_dominated_complete_local_state(
    validator: ModuleType,
    fixture: dict[str, Any],
) -> None:
    changed_values = _local_baseline_prefix_values(validator)
    changed_values[-1] += 1
    root_position = 2
    fixture["proof_nodes"].append(
        {
            "frontier_commitment": copy.deepcopy(
                fixture["proof_nodes"][0]["frontier_commitment"]
            )
        }
    )
    changed_witness = copy.deepcopy(fixture["boundary_witnesses"][0])
    changed_witness["candidate_mutated_spec"]["spec"][
        "maximum_websocket_send_attempts"
    ] = changed_values[-1]
    fixture["boundary_root_positions"].append(root_position)
    fixture["boundary_witnesses"].append(changed_witness)

    objective, changed_positions = validator._derive_local_shutdown_objective_prefix(  # noqa: SLF001
        changed_values,
        label="dominated complete fixture state",
    )
    relation_states = validator._derive_local_shutdown_intrinsic_relation_states(  # noqa: SLF001
        changed_values,
        label="dominated complete fixture state",
    )
    state_position = len(fixture["state_values"]) + 1
    state_payload = {
        "state_position": state_position,
        "processed_mutable_member_count": len(changed_values),
        "ordered_processed_values": changed_values,
        "ordered_changed_domain_positions": list(changed_positions),
        "sum_absolute_integer_deltas": objective["sum_of_absolute_integer_deltas"],
        "ordered_intrinsic_relation_states": relation_states,
        "prospective_result_root_position": root_position,
        "state_status": "DOMINATED",
    }
    fixture["state_values"].append(
        {
            **state_payload,
            "recurrence_state_id": validator._semantic_id(  # noqa: SLF001
                validator.LOCAL_SHUTDOWN_RECURRENCE_STATE_DOMAIN,
                state_payload,
            ),
        }
    )

    breakpoint_position = len(fixture["breakpoint_values"]) + 1
    source_position = len(validator.LOCAL_SHUTDOWN_MUTABLE_LIMIT_MEMBERS)
    member_name = validator.LOCAL_SHUTDOWN_MUTABLE_LIMIT_MEMBERS[-1]
    fixture["breakpoint_values"].append(
        {
            "breakpoint_position": breakpoint_position,
            "source_state_position": source_position,
            "domain_position": validator.LOCAL_SHUTDOWN_LIMIT_DOMAIN_POSITIONS[
                member_name
            ],
            "member_name": member_name,
            "breakpoint_kind": "BASELINE_NEIGHBOR",
            "candidate_value": changed_values[-1],
            "source_relation_id": None,
            "prospective_result_root_position": None,
        }
    )
    transition_payload = {
        "transition_position": breakpoint_position,
        "source_state_position": source_position,
        "breakpoint_position": breakpoint_position,
        "result_state_position": state_position,
        "transition_kind": "EXTEND_DOMINATED",
        "failed_relation_id": None,
    }
    fixture["transition_values"].append(
        {
            **transition_payload,
            "recurrence_transition_id": validator._semantic_id(  # noqa: SLF001
                validator.LOCAL_SHUTDOWN_RECURRENCE_TRANSITION_DOMAIN,
                transition_payload,
            ),
        }
    )
    equivalence_key = validator._derive_local_shutdown_equivalence_key(  # noqa: SLF001
        processed_values=changed_values,
        ordered_intrinsic_relation_states=relation_states,
        intrinsically_feasible=True,
        prospective_result_frontier_commitment_id=fixture["proof_nodes"][1][
            "frontier_commitment"
        ]["frontier_commitment_id"],
        label="dominated complete fixture key",
    )
    fixture["dominance_deletion_values"] = [
        {
            "deletion_position": 1,
            "deleted_state_position": state_position,
            "retained_state_position": state_position - 1,
            "equivalence_state_key_sha256": hashlib.sha256(
                _canonical(equivalence_key)
            ).hexdigest(),
            "dominance_reason": ("BYTE_EQUAL_STATE_KEY_AND_OBJECTIVE_PREFIX_NO_WORSE"),
        }
    ]


def test_local_recurrence_validates_reachability_transitions_and_winner(
    validator: ModuleType,
) -> None:
    fixture = _minimal_local_recurrence_fixture(validator)
    meter = validator.ProofResourceMeter(phase=validator.SEED_CAP_DERIVATION_PHASE)
    result = validator._validate_local_shutdown_recurrence_records(  # noqa: SLF001
        **fixture,
        resource_meter=meter,
        label="minimal local recurrence",
    )
    assert result["winner_state"]["processed_mutable_member_count"] == 11
    assert result["winner_objective"] == fixture["expected_winning_objective"]
    assert meter.value("frontier_transition_count") == 11
    assert meter.value("hash_preimage_octets") > 0


def test_local_recurrence_accepts_only_commitment_backed_complete_dominance(
    validator: ModuleType,
) -> None:
    fixture = _minimal_local_recurrence_fixture(validator)
    _add_dominated_complete_local_state(validator, fixture)
    meter = validator.ProofResourceMeter(phase=validator.SEED_CAP_DERIVATION_PHASE)
    result = validator._validate_local_shutdown_recurrence_records(  # noqa: SLF001
        **fixture,
        resource_meter=meter,
        label="complete dominance recurrence",
    )
    assert result["winner_state"]["state_position"] == 12
    assert meter.value("frontier_transition_count") == 12

    wrong_key_hash = copy.deepcopy(fixture)
    wrong_key_hash["dominance_deletion_values"][0]["equivalence_state_key_sha256"] = (
        "f" * 64
    )
    with pytest.raises(
        validator.MaximumProtocolValidationError,
        match="key hash/reason differs",
    ):
        validator._validate_local_shutdown_recurrence_records(  # noqa: SLF001
            **wrong_key_hash,
            resource_meter=validator.ProofResourceMeter(
                phase=validator.SEED_CAP_DERIVATION_PHASE
            ),
            label="wrong dominance hash recurrence",
        )


def test_local_recurrence_rejects_partial_dominance(
    validator: ModuleType,
) -> None:
    fixture = _minimal_local_recurrence_fixture(validator)
    state = fixture["state_values"][1]
    state["state_status"] = "DOMINATED"
    payload = {
        name: item for name, item in state.items() if name != "recurrence_state_id"
    }
    state["recurrence_state_id"] = validator._semantic_id(  # noqa: SLF001
        validator.LOCAL_SHUTDOWN_RECURRENCE_STATE_DOMAIN,
        payload,
    )
    with pytest.raises(
        validator.MaximumProtocolValidationError,
        match="partial feasible status/root differs",
    ):
        validator._validate_local_shutdown_recurrence_records(  # noqa: SLF001
            **fixture,
            resource_meter=validator.ProofResourceMeter(
                phase=validator.SEED_CAP_DERIVATION_PHASE
            ),
            label="partial dominance recurrence",
        )


def test_local_recurrence_rejects_transition_that_does_not_append_breakpoint(
    validator: ModuleType,
) -> None:
    fixture = _minimal_local_recurrence_fixture(validator)
    fixture["breakpoint_values"][0]["candidate_value"] = 2
    with pytest.raises(
        validator.MaximumProtocolValidationError,
        match="does not append its breakpoint candidate",
    ):
        validator._validate_local_shutdown_recurrence_records(  # noqa: SLF001
            **fixture,
            resource_meter=validator.ProofResourceMeter(
                phase=validator.SEED_CAP_DERIVATION_PHASE
            ),
            label="wrong transition recurrence",
        )


def test_local_recurrence_rejects_spurious_interval_exclusion(
    validator: ModuleType,
) -> None:
    fixture = _minimal_local_recurrence_fixture(validator)
    fixture["interval_exclusion_values"] = [
        {
            "interval_position": 1,
            "source_state_position": 1,
            "domain_position": 9,
            "first_omitted_value": 2,
            "last_omitted_value": 3,
            "dominating_breakpoint_position": 1,
            "prospective_result_root_position": 1,
            "piecewise_signature_id": "a" * 64,
        }
    ]
    with pytest.raises(
        validator.MaximumProtocolValidationError,
        match="interval exclusions length differs",
    ):
        validator._validate_local_shutdown_recurrence_records(  # noqa: SLF001
            **fixture,
            resource_meter=validator.ProofResourceMeter(
                phase=validator.SEED_CAP_DERIVATION_PHASE
            ),
            label="spurious interval recurrence",
        )


def test_local_recurrence_rejects_boundary_candidate_vector_mismatch(
    validator: ModuleType,
) -> None:
    fixture = _minimal_local_recurrence_fixture(validator)
    fixture["boundary_witnesses"][0]["candidate_mutated_spec"]["spec"][
        "maximum_websocket_send_attempts"
    ] = 3
    with pytest.raises(
        validator.MaximumProtocolValidationError,
        match="boundary candidate values differ",
    ):
        validator._validate_local_shutdown_recurrence_records(  # noqa: SLF001
            **fixture,
            resource_meter=validator.ProofResourceMeter(
                phase=validator.SEED_CAP_DERIVATION_PHASE
            ),
            label="wrong boundary vector recurrence",
        )


def test_local_baseline_result_is_a_control_pointer_not_a_record_reference(
    validator: ModuleType,
) -> None:
    keys = validator.DERIVATION_KEYS["LOCAL_SHUTDOWN_MINIMALITY_FRONTIER"]
    assert "baseline_result_inventory_json_pointer" in keys
    assert "baseline_result_record_reference" not in keys

    generator_path = _repository_root() / _GENERATOR_RELATIVE_PATH
    source = generator_path.read_text(encoding="utf-8")
    assert '"baseline_result_inventory_json_pointer"' in source
    assert '"baseline_result_record_reference"' not in source


def test_local_derivation_fully_resolves_its_profile3_baseline_reference(
    validator: ModuleType,
    pinned_inventory_and_registry: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    inventory, registry = pinned_inventory_and_registry
    baseline_reference = _v3_record_reference(
        validator,
        inventory=inventory,
        pointer=validator.LOCAL_SHUTDOWN_BASELINE_SPEC_POINTER,
        record_type_name=validator.LOCAL_SHUTDOWN_BASELINE_SPEC_TYPE_NAME,
        record_identity_field="operation_spec_id",
    )
    derivation = {
        "derivation_kind": "LOCAL_SHUTDOWN_MINIMALITY_FRONTIER",
        "baseline_spec_record_reference": baseline_reference,
        "ordered_mutable_limit_member_names": list(
            validator.LOCAL_SHUTDOWN_MUTABLE_LIMIT_MEMBERS
        ),
        "ordered_intrinsic_relation_ids": list(
            validator.LOCAL_SHUTDOWN_INTRINSIC_RELATION_IDS
        ),
        "prospective_result_attainment_mode": (
            "PROSPECTIVE_BYTE_MAXIMUM_WITH_ONE_MASKED_OUTER_CODEC"
        ),
        "masked_outer_codec_coordinate": {
            "validation_root_type_name": ("CapacityMeasurementOperationResultEvidence"),
            "codec_owner_type_name": "CapacityMeasurementOperationResultEvidence",
            "codec_owner_typed_member_path": [],
            "codec_byte_bound_relation": "LT",
            "codec_octet_limit": 524_288,
        },
        "baseline_result_inventory_json_pointer": (
            validator.LOCAL_SHUTDOWN_BASELINE_RESULT_POINTER
        ),
        "baseline_result_canonical_byte_length": (
            validator.LOCAL_SHUTDOWN_BASELINE_RESULT_CANONICAL_OCTETS
        ),
        "outer_codec_byte_bound_relation": "LT",
        "outer_codec_octet_limit": 524_288,
        "winning_objective": {
            "changed_limit_field_count": 0,
            "sum_of_absolute_integer_deltas": "0",
            "changed_member_names_in_lexical_order": [],
            "resulting_changed_values_in_that_same_order": [],
        },
        "prospective_result_canonical_byte_length": 524_288,
        "prospective_result_canonical_sha256": "a" * 64,
        "baseline_spec_fixed_child_position": 1,
        "ordered_boundary_candidate_root_positions": [],
        "ordered_boundary_candidate_witness_records": [],
        "ordered_breakpoint_records": [],
        "ordered_interval_exclusion_records": [],
        "ordered_recurrence_state_records": [],
        "ordered_recurrence_transition_records": [],
        "ordered_dominance_deletion_records": [],
        "recurrence_version": (
            "LEXICAL_SUBSET_UINT128_DELTA_AND_PROSPECTIVE_BYTE_FRONTIER_V1"
        ),
    }
    assert (
        validator._validate_derivation(  # noqa: SLF001
            derivation,
            node_kind="LOCAL_SHUTDOWN_MINIMALITY_FRONTIER",
            child_positions=[1],
            node_position=2,
            label="local derivation",
            resource_meter=validator.ProofResourceMeter(
                phase=validator.SEED_CAP_DERIVATION_PHASE
            ),
            validated_inventory=inventory,
            validated_registry=registry,
        )
        is derivation
    )

    corrupt = copy.deepcopy(derivation)
    corrupt_reference = corrupt["baseline_spec_record_reference"]
    corrupt_reference["record_canonical_byte_length"] += 1
    reference_payload = {
        name: item
        for name, item in corrupt_reference.items()
        if name != "maximum_record_reference_id"
    }
    corrupt_reference["maximum_record_reference_id"] = validator._semantic_id(  # noqa: SLF001
        validator.MAXIMUM_RECORD_REFERENCE_DOMAIN,
        reference_payload,
    )
    with pytest.raises(
        validator.MaximumProtocolValidationError,
        match="canonical length differs",
    ):
        validator._validate_derivation(  # noqa: SLF001
            corrupt,
            node_kind="LOCAL_SHUTDOWN_MINIMALITY_FRONTIER",
            child_positions=[1],
            node_position=2,
            label="corrupt local derivation",
            resource_meter=validator.ProofResourceMeter(
                phase=validator.SEED_CAP_DERIVATION_PHASE
            ),
            validated_inventory=inventory,
            validated_registry=registry,
        )


def test_context_reference_deduplication_metric_is_exact_difference(
    validator: ModuleType,
) -> None:
    measurement = dict.fromkeys(validator.PRODUCER_RESOURCE_KEYS, 0)
    measurement.update(
        {
            "resolved_context_reference_count": 3,
            "resolved_context_object_count": 2,
            "deduplicated_context_reference_count": 1,
        }
    )
    assert (
        validator._validate_producer_resource_measurement(  # noqa: SLF001
            measurement,
            certificate=None,
            label="context reference measurement",
        )
        is measurement
    )
    measurement["deduplicated_context_reference_count"] = 2
    with pytest.raises(
        validator.MaximumProtocolValidationError,
        match="deduplicated-reference arithmetic differs",
    ):
        validator._validate_producer_resource_measurement(  # noqa: SLF001
            measurement,
            certificate=None,
            label="wrong context reference measurement",
        )


def _pilot_root_envelope_fixture(
    validator: ModuleType,
    *,
    protocol_sha256: str,
) -> dict[str, Any]:
    pilot = {
        "artifact_version": validator.PILOT_VERSION,
        "canonicalization_version": validator.CANONICALIZATION_VERSION,
        "measurement_schema_version": validator.MEASUREMENT_SCHEMA_VERSION,
        "pilot_phase": validator.SEED_CAP_DERIVATION_PHASE,
        "seed_protocol_sha256": None,
        "seed_protocol_raw_octet_count": None,
        "maximum_protocol_sha256": protocol_sha256,
        "seed_artifact_raw_octet_count": None,
        "seed_artifact_raw_sha256": None,
        "source_inventory_sha256": validator.INVENTORY_SEMANTIC_ID,
        "external_schema_registry_id": validator.REGISTRY_ID,
        "rule_literal_authority_sha256": validator.LITERAL_AUTHORITY_RAW_SHA256,
        "application_witness_raw_sha256": validator.APPLICATION_WITNESS_RAW_SHA256,
        "max64_context_authority_raw_sha256": (
            validator.MAX64_CONTEXT_AUTHORITY_RAW_SHA256
        ),
        "ordered_pilot_case_records": [{} for _ in range(6)],
        "local_shutdown_minimality_pilot_record": {},
        "ordered_row_preflight_records": [{} for _ in range(474)],
        "local_shutdown_minimality_preflight_record": {},
        "metric_rounding_catalog": [{} for _ in validator.METRIC_NAMES],
        "derived_resource_ceiling_record": {
            name.lower(): 0 for name in validator.METRIC_NAMES
        },
    }
    pilot["phase_invariant_payload_sha256"] = hashlib.sha256(
        _canonical(validator._pilot_phase_invariant_projection(pilot))  # noqa: SLF001
    ).hexdigest()
    pilot["maximum_protocol_pilot_id"] = validator._semantic_id(  # noqa: SLF001
        validator.PILOT_DOMAIN,
        pilot,
    )
    return pilot


def test_pilot_root_envelope_binds_phase_projection_and_semantic_identity(
    validator: ModuleType,
) -> None:
    protocol_sha256 = "9" * 64
    pilot = _pilot_root_envelope_fixture(
        validator,
        protocol_sha256=protocol_sha256,
    )
    assert (
        validator._validate_pilot_root_envelope(  # noqa: SLF001
            pilot,
            expected_pilot_phase=validator.SEED_CAP_DERIVATION_PHASE,
            maximum_protocol_sha256=protocol_sha256,
            label="pilot envelope",
        )
        is pilot
    )

    changed = copy.deepcopy(pilot)
    changed["ordered_pilot_case_records"][0]["non_identity_metric"] = 1
    changed["maximum_protocol_pilot_id"] = validator._semantic_id(  # noqa: SLF001
        validator.PILOT_DOMAIN,
        {
            name: item
            for name, item in changed.items()
            if name != "maximum_protocol_pilot_id"
        },
    )
    with pytest.raises(
        validator.MaximumProtocolValidationError,
        match="phase-invariant payload SHA differs",
    ):
        validator._validate_pilot_root_envelope(  # noqa: SLF001
            changed,
            expected_pilot_phase=validator.SEED_CAP_DERIVATION_PHASE,
            maximum_protocol_sha256=protocol_sha256,
            label="changed pilot envelope",
        )


def _local_baseline_fixed_child(
    validator: ModuleType,
) -> tuple[dict[str, Any], dict[str, Any]]:
    locator = {
        "locator_kind": "V3_INVENTORY_POINTER",
        "record_reference_id": validator.LOCAL_SHUTDOWN_BASELINE_SPEC_POINTER,
        "root_type_name": validator.LOCAL_SHUTDOWN_BASELINE_SPEC_TYPE_NAME,
        "root_value_schema_id": None,
        "ordered_path_steps": [],
        "transient_state_key": None,
        "transient_source_child_position": None,
        "transient_source_child_proof_node_id": None,
    }
    node = {
        "proof_node_position": 1,
        "proof_node_kind": "FIXED_VALUE",
        "subject_locator": locator,
        "value_schema_id": validator.LOCAL_SHUTDOWN_BASELINE_SPEC_VALUE_SCHEMA_ID,
        "type_name": validator.LOCAL_SHUTDOWN_BASELINE_SPEC_TYPE_NAME,
        "alternative_name": None,
        "effective_canonical_octet_ceiling": (
            validator.LOCAL_SHUTDOWN_BASELINE_SPEC_EFFECTIVE_CEILING
        ),
        "ordered_child_positions": [],
        "ordered_child_proof_node_ids": [],
        "ordered_ancestor_observable_dimensions": [],
        "output_frontier": {
            "frontier_encoding_kind": "MATERIALIZED",
            "materialized_frontier": {},
            "direct_child_alias": None,
        },
        "frontier_commitment": {
            "least_measured_choice_vector_sha256_at_maximum": None,
            "least_context_choice_vector_sha256_at_maximum": None,
        },
        "derivation": {
            "derivation_kind": "FIXED_VALUE",
            "fixed_source_kind": "FROZEN_AUTHORITY",
            "fixed_source_locator": locator,
            "fixed_transfer_kind": "EXACT_FIXED_VALUE",
            "fixed_canonical_byte_length": (
                validator.LOCAL_SHUTDOWN_BASELINE_SPEC_CANONICAL_OCTETS
            ),
            "fixed_canonical_sha256": (
                validator.LOCAL_SHUTDOWN_BASELINE_SPEC_CANONICAL_SHA256
            ),
            "derived_identity_mapping_catalog_id": None,
            "ordered_identity_payload_child_positions": [],
        },
    }
    resolution = {
        "resolved_materialized_frontier": {"frontier_soundness": "EXACT_ATTAINABLE"},
        "frontier_evidence": {
            "state_entry_count": 1,
            "expanded_attainable_point_count": 1,
            "minimum_attainable_octets": (
                validator.LOCAL_SHUTDOWN_BASELINE_SPEC_CANONICAL_OCTETS
            ),
            "maximum_attainable_octets": (
                validator.LOCAL_SHUTDOWN_BASELINE_SPEC_CANONICAL_OCTETS
            ),
        },
    }
    return node, resolution


def test_local_baseline_child_is_exact_position_one_fixed_authority(
    validator: ModuleType,
) -> None:
    node, resolution = _local_baseline_fixed_child(validator)
    validator._validate_local_baseline_spec_fixed_child(  # noqa: SLF001
        node,
        frontier_resolution=resolution,
        label="baseline fixed child",
    )

    for path, value in (
        (("proof_node_position",), 2),
        (("subject_locator", "record_reference_id"), "/target_field_registry"),
        (("derivation", "fixed_canonical_byte_length"), 1_108),
        (("output_frontier", "frontier_encoding_kind"), "DIRECT_CHILD_ALIAS"),
    ):
        corrupted = copy.deepcopy(node)
        target = corrupted
        for member in path[:-1]:
            target = target[member]
        target[path[-1]] = value
        with pytest.raises(validator.MaximumProtocolValidationError):
            validator._validate_local_baseline_spec_fixed_child(  # noqa: SLF001
                corrupted,
                frontier_resolution=resolution,
                label="baseline fixed child",
            )


def test_validator_static_import_and_execution_separation() -> None:
    path = _repository_root() / _VALIDATOR_RELATIVE_PATH
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    imported_roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0
            assert node.module is not None
            imported_roots.add(node.module.split(".", 1)[0])

    assert imported_roots == {
        "__future__",
        "argparse",
        "collections",
        "hashlib",
        "json",
        "os",
        "pathlib",
        "re",
        "stat",
        "sys",
        "types",
        "typing",
    }
    assert imported_roots.isdisjoint(
        {
            "riskyieldmm",
            "subprocess",
            "socket",
            "urllib",
            "requests",
            "pickle",
            "marshal",
        }
    )
    forbidden_calls = {
        "__import__",
        "compile",
        "eval",
        "exec",
        "import_module",
        "module_from_spec",
        "spec_from_file_location",
        "system",
        "popen",
    }
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            assert node.func.id not in forbidden_calls
        elif isinstance(node.func, ast.Attribute):
            assert node.func.attr not in forbidden_calls

    for obsolete_schema_token in (
        "ordered_exact_constraint_ids",
        "maximum_slice_child_position",
        "exact_maximum_slice_child_position",
        "DERIVED_IDENTITY_SUBSTITUTION",
        "LOCAL_SHUTDOWN_FIRST_UNREPRESENTABLE",
    ):
        assert obsolete_schema_token not in source
    assert source.count("_validate_acceptance_authority_shape(") == 1


def test_rejected_v1_protocol_pin_is_frozen_as_falsification_authority(
    validator: ModuleType,
) -> None:
    assert validator.PROTOCOL_OCTETS == 246_093
    assert validator.PROTOCOL_SHA256 == (
        "b3b39b3cb15caa450d9974925db9b5f0b91dd5832a462d2a8687dc19a50c4409"
    )


@pytest.mark.parametrize(
    "payload",
    (
        b'{\n  "a": 1,\n  "a": 2\n}\n',
        b'{\n  "a": 1.0\n}\n',
        b'{\n  "a": NaN\n}\n',
        b'{"a":1}\n',
        b'{\n  "z": 1,\n  "a": 2\n}\n',
        b'{\n  "a": 9007199254740992\n}\n',
    ),
)
def test_strict_json_rejects_ambiguous_or_noncanonical_bytes(
    validator: ModuleType,
    payload: bytes,
) -> None:
    with pytest.raises(validator.MaximumProtocolValidationError):
        validator._decode_pretty_json(payload, label="adversarial JSON")  # noqa: SLF001


def test_strict_json_accepts_only_canonical_pretty_object(
    validator: ModuleType,
) -> None:
    payload = b'{\n  "a": [\n    true,\n    null\n  ],\n  "z": 1\n}\n'
    assert validator._decode_pretty_json(  # noqa: SLF001
        payload,
        label="canonical JSON",
    ) == {"a": [True, None], "z": 1}


def test_bitmap_bit_order_and_gaps_are_preserved(validator: ModuleType) -> None:
    bit_zero = _frontier(
        [
            {
                "first_block_index": 0,
                "last_block_index": 0,
                "attainable_length_bitmap_hex": _bitmap(1),
            }
        ],
        validator,
    )
    _, evidence = validator._validate_materialized_frontier(  # noqa: SLF001
        bit_zero,
        dimensions=[],
        state_signature_id=_empty_signature(validator),
        label="bit zero",
    )
    assert evidence["minimum_attainable_octets"] == 0
    assert evidence["maximum_attainable_octets"] == 0

    bit_255 = copy.deepcopy(bit_zero)
    bit_255["ordered_state_frontiers"][0]["ordered_length_bitmap_runs"][0][
        "attainable_length_bitmap_hex"
    ] = _bitmap(1 << 255)
    _, evidence = validator._validate_materialized_frontier(  # noqa: SLF001
        bit_255,
        dimensions=[],
        state_signature_id=_empty_signature(validator),
        label="bit 255",
    )
    assert evidence["minimum_attainable_octets"] == 255
    assert evidence["maximum_attainable_octets"] == 255

    gapped = _frontier(
        [
            {
                "first_block_index": 0,
                "last_block_index": 0,
                "attainable_length_bitmap_hex": _bitmap(0b101),
            },
            {
                "first_block_index": 2,
                "last_block_index": 2,
                "attainable_length_bitmap_hex": _bitmap(1),
            },
        ],
        validator,
    )
    _, evidence = validator._validate_materialized_frontier(  # noqa: SLF001
        gapped,
        dimensions=[],
        state_signature_id=_empty_signature(validator),
        label="gapped frontier",
    )
    assert evidence["expanded_attainable_point_count"] == 3
    assert evidence["minimum_attainable_octets"] == 0
    assert evidence["maximum_attainable_octets"] == 512


@pytest.mark.parametrize(
    "runs",
    (
        [
            {
                "first_block_index": 0,
                "last_block_index": 0,
                "attainable_length_bitmap_hex": "0" * 64,
            }
        ],
        [
            {
                "first_block_index": 0,
                "last_block_index": 0,
                "attainable_length_bitmap_hex": "A" + "0" * 63,
            }
        ],
        [
            {
                "first_block_index": 0,
                "last_block_index": 0,
                "attainable_length_bitmap_hex": "1" * 63,
            }
        ],
        [
            {
                "first_block_index": 0,
                "last_block_index": 0,
                "attainable_length_bitmap_hex": _bitmap(1),
            },
            {
                "first_block_index": 1,
                "last_block_index": 1,
                "attainable_length_bitmap_hex": _bitmap(1),
            },
        ],
        [
            {
                "first_block_index": 1,
                "last_block_index": 1,
                "attainable_length_bitmap_hex": _bitmap(1),
            },
            {
                "first_block_index": 1,
                "last_block_index": 2,
                "attainable_length_bitmap_hex": _bitmap(2),
            },
        ],
    ),
)
def test_bitmap_rejects_noncanonical_runs(
    validator: ModuleType,
    runs: list[dict[str, Any]],
) -> None:
    with pytest.raises(validator.MaximumProtocolValidationError):
        validator._validate_materialized_frontier(  # noqa: SLF001
            _frontier(runs, validator),
            dimensions=[],
            state_signature_id=_empty_signature(validator),
            label="adversarial bitmap",
        )


def test_typed_locator_nullability_and_ordinal_rules(validator: ModuleType) -> None:
    schema = _schema_locator(path=[_path_step(ordinal=None)])
    assert (
        validator._validate_proof_subject_locator(  # noqa: SLF001
            schema,
            label="schema locator",
        )
        is schema
    )
    transient = _transient_locator()
    assert (
        validator._validate_proof_subject_locator(  # noqa: SLF001
            transient,
            label="transient locator",
        )
        is transient
    )
    retained = _retained_locator(ordinal=0)
    assert (
        validator._validate_proof_subject_locator(  # noqa: SLF001
            retained,
            label="retained locator",
        )
        is retained
    )

    missing_schema = copy.deepcopy(schema)
    missing_schema["root_value_schema_id"] = None
    with pytest.raises(validator.MaximumProtocolValidationError):
        validator._validate_proof_subject_locator(  # noqa: SLF001
            missing_schema,
            label="missing schema ID",
        )

    retained_symbolic = _retained_locator(ordinal=None)
    with pytest.raises(validator.MaximumProtocolValidationError):
        validator._validate_proof_subject_locator(  # noqa: SLF001
            retained_symbolic,
            label="retained symbolic item",
        )

    transient_with_root = copy.deepcopy(transient)
    transient_with_root["root_type_name"] = "ExampleRecord"
    with pytest.raises(validator.MaximumProtocolValidationError):
        validator._validate_proof_subject_locator(  # noqa: SLF001
            transient_with_root,
            label="transient root",
        )

    transient_without_source = copy.deepcopy(transient)
    transient_without_source["transient_source_child_position"] = None
    with pytest.raises(validator.MaximumProtocolValidationError):
        validator._validate_proof_subject_locator(  # noqa: SLF001
            transient_without_source,
            label="transient source",
        )


def test_locator_reference_grammar_is_kind_specific(validator: ModuleType) -> None:
    pointer = "/fixture_records/~0escaped/~1member"
    proof_inventory = _retained_locator(ordinal=0)
    proof_inventory["locator_kind"] = "V3_INVENTORY_POINTER"
    proof_inventory["record_reference_id"] = pointer
    assert (
        validator._validate_proof_subject_locator(  # noqa: SLF001
            proof_inventory,
            label="proof inventory pointer",
        )
        is proof_inventory
    )

    retained_inventory = {
        "retained_source_kind": "V3_INVENTORY_POINTER",
        "record_reference_id": pointer,
        "root_type_name": "ExampleRecord",
        "scope_context_member_name": None,
        "ordered_path_steps": [_path_step(ordinal=0)],
        "projection_kind": "VALUE",
    }
    assert (
        validator._validate_retained_value_locator(  # noqa: SLF001
            retained_inventory,
            label="retained inventory pointer",
        )
        is retained_inventory
    )

    for invalid_pointer in (
        "3" * 64,
        "#/fixture_records/value",
        "/fixture_records/bad~2escape",
        "/fixture_records/dangling~",
    ):
        for locator, validator_function in (
            (
                proof_inventory,
                validator._validate_proof_subject_locator,  # noqa: SLF001
            ),
            (
                retained_inventory,
                validator._validate_retained_value_locator,  # noqa: SLF001
            ),
        ):
            corrupt = copy.deepcopy(locator)
            corrupt["record_reference_id"] = invalid_pointer
            with pytest.raises(validator.MaximumProtocolValidationError):
                validator_function(corrupt, label="invalid inventory pointer")

    proof_witness = _retained_locator(ordinal=0)
    proof_witness["record_reference_id"] = pointer
    retained_witness = copy.deepcopy(retained_inventory)
    retained_witness["retained_source_kind"] = "WITNESS_RECORD"
    for locator, validator_function in (
        (proof_witness, validator._validate_proof_subject_locator),  # noqa: SLF001
        (retained_witness, validator._validate_retained_value_locator),  # noqa: SLF001
    ):
        with pytest.raises(validator.MaximumProtocolValidationError):
            validator_function(locator, label="pointer used as witness SHA")


def test_strict_rfc6901_resolver_handles_escapes_and_array_indices(
    validator: ModuleType,
) -> None:
    document = {"a/b": {"~": ["zero", {"answer": 42}]}}
    assert (
        validator._resolve_absolute_rfc6901_pointer(  # noqa: SLF001
            document,
            "/a~1b/~0/1/answer",
            label="escaped pointer",
        )
        == 42
    )
    for invalid_pointer in (
        "/a~1b/~0/01",
        "/a~1b/~0/-",
        "/a~1b/~0/+1",
        "/a~1b/~0/2",
        "/a~1b/~0/1/answer/child",
    ):
        with pytest.raises(validator.MaximumProtocolValidationError):
            validator._resolve_absolute_rfc6901_pointer(  # noqa: SLF001
                document,
                invalid_pointer,
                label="invalid pointer",
            )


def test_v3_baseline_spec_reference_resolves_complete_pinned_record_and_meters_hashes(
    validator: ModuleType,
    pinned_inventory_and_registry: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    inventory, registry = pinned_inventory_and_registry
    profile = inventory["operation_contracts"][
        "maximum_constraint_scope_profile_catalog"
    ][2]
    authority = validator._inventory_pointer_authority_from_profile(  # noqa: SLF001
        profile,
        label="fixture profile",
    )
    pointer = "/fixture_records/operation_specs/LOCAL_SHUTDOWN"
    assert dict(authority) == {pointer: profile["ordered_source_authority_ids"][0]}
    reference = _v3_record_reference(
        validator,
        inventory=inventory,
        pointer=pointer,
        record_type_name="CapacityMeasurementOperationSpec",
        record_identity_field="operation_spec_id",
    )
    meter = validator.ProofResourceMeter(phase=validator.SEED_CAP_DERIVATION_PHASE)

    resolved = validator._resolve_v3_inventory_record_reference(  # noqa: SLF001
        reference,
        validated_inventory=inventory,
        validated_registry=registry,
        permitted_inventory_pointer_authority=authority,
        expected_inventory_pointer=pointer,
        expected_record_type_name="CapacityMeasurementOperationSpec",
        label="baseline spec",
        resource_meter=meter,
    )

    record = inventory["fixture_records"]["operation_specs"]["LOCAL_SHUTDOWN"]
    assert resolved.reference is reference
    assert resolved.validated_record.record is record
    assert resolved.validated_record.record_identity == record["operation_spec_id"]
    assert resolved.validated_record.record_canonical_byte_length == len(
        _canonical(record)
    )
    descriptor = next(
        item
        for item in registry["ordered_external_type_descriptors"]
        if item["type_name"] == "CapacityMeasurementOperationSpec"
    )
    identity_payload = {
        name: record[name] for name in descriptor["identity_payload_member_order"]
    }
    reference_payload = {
        name: item
        for name, item in reference.items()
        if name != "maximum_record_reference_id"
    }
    expected_hash_preimage_octets = sum(
        (
            len(
                _canonical(
                    _semantic_envelope(
                        validator,
                        validator.MAXIMUM_RECORD_REFERENCE_DOMAIN,
                        reference_payload,
                    )
                )
            ),
            len(
                _canonical(
                    _semantic_envelope(
                        validator,
                        descriptor["described_record_domain"],
                        identity_payload,
                    )
                )
            ),
            len(_canonical(record)),
        )
    )
    assert meter.value("hash_preimage_octets") == expected_hash_preimage_octets


def test_local_baseline_result_control_pointer_resolves_without_reference_widening(
    validator: ModuleType,
    pinned_inventory_and_registry: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    inventory, registry = pinned_inventory_and_registry
    meter = validator.ProofResourceMeter(phase=validator.SEED_CAP_DERIVATION_PHASE)
    resolved = validator._resolve_local_baseline_result_control_pointer(  # noqa: SLF001
        validator.LOCAL_SHUTDOWN_BASELINE_RESULT_POINTER,
        validated_inventory=inventory,
        validated_registry=registry,
        resource_meter=meter,
        label="baseline result control pointer",
    )
    record = inventory["fixture_records"]["operation_results"]["LOCAL_SHUTDOWN"]
    descriptor = next(
        item
        for item in registry["ordered_external_type_descriptors"]
        if item["type_name"] == validator.LOCAL_SHUTDOWN_BASELINE_RESULT_TYPE_NAME
    )
    identity_payload = {
        name: record[name] for name in descriptor["identity_payload_member_order"]
    }
    expected_identity_preimage = _canonical(
        _semantic_envelope(
            validator,
            descriptor["described_record_domain"],
            identity_payload,
        )
    )
    assert resolved.record is record
    assert resolved.record_identity == validator.LOCAL_SHUTDOWN_BASELINE_RESULT_IDENTITY
    assert (
        resolved.record_canonical_byte_length
        == validator.LOCAL_SHUTDOWN_BASELINE_RESULT_CANONICAL_OCTETS
        == 2_504
    )
    assert meter.value("hash_preimage_octets") == len(expected_identity_preimage)

    with pytest.raises(
        validator.MaximumProtocolValidationError,
        match="sole local baseline-result authority",
    ):
        validator._resolve_local_baseline_result_control_pointer(  # noqa: SLF001
            "/fixture_records/operation_results/INGRESS",
            validated_inventory=inventory,
            validated_registry=registry,
            resource_meter=validator.ProofResourceMeter(
                phase=validator.SEED_CAP_DERIVATION_PHASE
            ),
            label="wrong baseline result control pointer",
        )

    corrupted_inventory = copy.deepcopy(inventory)
    corrupted_inventory["fixture_records"]["operation_results"]["LOCAL_SHUTDOWN"][
        "candidate_id"
    ] = "0" * 64
    with pytest.raises(
        validator.MaximumProtocolValidationError,
        match="semantic identity differs",
    ):
        validator._resolve_local_baseline_result_control_pointer(  # noqa: SLF001
            validator.LOCAL_SHUTDOWN_BASELINE_RESULT_POINTER,
            validated_inventory=corrupted_inventory,
            validated_registry=registry,
            resource_meter=validator.ProofResourceMeter(
                phase=validator.SEED_CAP_DERIVATION_PHASE
            ),
            label="corrupted baseline result",
        )
    assert {
        name: value
        for name, value in meter.snapshot().items()
        if name != "hash_preimage_octets"
    } == dict.fromkeys(validator.PROOF_RESOURCE_KEYS - {"hash_preimage_octets"}, 0)


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        ("pointer", "not permitted by its scope profile"),
        ("type", "record type differs from its exact authority"),
        ("identity", "record identity differs from its scope-profile authority"),
        ("length", "canonical length differs"),
        ("sha", "canonical SHA differs"),
        ("reference_id", "semantic identity differs"),
    ),
)
def test_v3_baseline_spec_reference_rejects_adversarial_metadata(
    validator: ModuleType,
    pinned_inventory_and_registry: tuple[dict[str, Any], dict[str, Any]],
    mutation: str,
    message: str,
) -> None:
    inventory, registry = pinned_inventory_and_registry
    profile = inventory["operation_contracts"][
        "maximum_constraint_scope_profile_catalog"
    ][2]
    authority = validator._inventory_pointer_authority_from_profile(  # noqa: SLF001
        profile,
        label="fixture profile",
    )
    pointer = "/fixture_records/operation_specs/LOCAL_SHUTDOWN"
    reference = _v3_record_reference(
        validator,
        inventory=inventory,
        pointer=pointer,
        record_type_name="CapacityMeasurementOperationSpec",
        record_identity_field="operation_spec_id",
    )
    if mutation == "pointer":
        reference["inventory_json_pointer"] = "/target_field_registry"
    elif mutation == "type":
        reference["record_type_name"] = "CapacityMeasurementOperationResultEvidence"
    elif mutation == "identity":
        reference["record_identity"] = "0" * 64
    elif mutation == "length":
        reference["record_canonical_byte_length"] += 1
    elif mutation == "sha":
        reference["record_canonical_sha256"] = "0" * 64
    else:
        assert mutation == "reference_id"
        reference["maximum_record_reference_id"] = "0" * 64
    if mutation != "reference_id":
        _refresh_record_reference_id(validator, reference)

    with pytest.raises(validator.MaximumProtocolValidationError, match=message):
        validator._resolve_v3_inventory_record_reference(  # noqa: SLF001
            reference,
            validated_inventory=inventory,
            validated_registry=registry,
            permitted_inventory_pointer_authority=authority,
            expected_inventory_pointer=None,
            expected_record_type_name="CapacityMeasurementOperationSpec",
            label="adversarial baseline spec",
            resource_meter=validator.ProofResourceMeter(
                phase=validator.SEED_CAP_DERIVATION_PHASE
            ),
        )


def test_v3_generic_profile_path_rejects_baseline_result_surface(
    validator: ModuleType,
    pinned_inventory_and_registry: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    inventory, registry = pinned_inventory_and_registry
    profile = inventory["operation_contracts"][
        "maximum_constraint_scope_profile_catalog"
    ][2]
    authority = validator._inventory_pointer_authority_from_profile(  # noqa: SLF001
        profile,
        label="fixture profile",
    )
    result_pointer = "/fixture_records/operation_results/LOCAL_SHUTDOWN"
    result_reference = _v3_record_reference(
        validator,
        inventory=inventory,
        pointer=result_pointer,
        record_type_name="CapacityMeasurementOperationResultEvidence",
        record_identity_field="result_evidence_id",
    )
    with pytest.raises(
        validator.MaximumProtocolValidationError,
        match="not permitted by its scope profile",
    ):
        validator._resolve_v3_inventory_record_reference(  # noqa: SLF001
            result_reference,
            validated_inventory=inventory,
            validated_registry=registry,
            permitted_inventory_pointer_authority=authority,
            expected_inventory_pointer=None,
            expected_record_type_name=None,
            label="baseline result",
            resource_meter=validator.ProofResourceMeter(
                phase=validator.SEED_CAP_DERIVATION_PHASE
            ),
        )


def test_v3_resolver_recomputes_descriptor_owned_record_identity(
    validator: ModuleType,
    pinned_inventory_and_registry: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    inventory, registry = pinned_inventory_and_registry
    corrupt_inventory = copy.deepcopy(inventory)
    pointer = "/fixture_records/operation_specs/LOCAL_SHUTDOWN"
    record = corrupt_inventory["fixture_records"]["operation_specs"]["LOCAL_SHUTDOWN"]
    record["spec"]["timeout_seconds"] += 1
    reference = _v3_record_reference(
        validator,
        inventory=corrupt_inventory,
        pointer=pointer,
        record_type_name="CapacityMeasurementOperationSpec",
        record_identity_field="operation_spec_id",
    )
    profile = inventory["operation_contracts"][
        "maximum_constraint_scope_profile_catalog"
    ][2]
    authority = validator._inventory_pointer_authority_from_profile(  # noqa: SLF001
        profile,
        label="fixture profile",
    )
    with pytest.raises(
        validator.MaximumProtocolValidationError,
        match="semantic identity differs",
    ):
        validator._resolve_v3_inventory_record_reference(  # noqa: SLF001
            reference,
            validated_inventory=corrupt_inventory,
            validated_registry=registry,
            permitted_inventory_pointer_authority=authority,
            expected_inventory_pointer=pointer,
            expected_record_type_name="CapacityMeasurementOperationSpec",
            label="corrupt baseline spec",
            resource_meter=validator.ProofResourceMeter(
                phase=validator.SEED_CAP_DERIVATION_PHASE
            ),
        )


def test_state_cell_identity_and_boolean_typing(validator: ModuleType) -> None:
    cell = _exact_cell(_boolean_atom(False), validator)
    assert validator._validate_state_cell(cell, label="Boolean cell") is cell  # noqa: SLF001

    wrong_identity = copy.deepcopy(cell)
    wrong_identity["state_cell_id"] = "f" * 64
    with pytest.raises(validator.MaximumProtocolValidationError):
        validator._validate_state_cell(  # noqa: SLF001
            wrong_identity,
            label="wrong cell identity",
        )

    Boolean_as_integer = _exact_cell(_boolean_atom(0), validator)
    with pytest.raises(validator.MaximumProtocolValidationError):
        validator._validate_state_cell(  # noqa: SLF001
            Boolean_as_integer,
            label="Boolean-as-integer cell",
        )


def test_inactive_atom_is_prefix_only_and_never_a_state_cell(
    validator: ModuleType,
) -> None:
    inactive = _primitive_atom("INACTIVE")
    assert validator._validate_primitive_atom(  # noqa: SLF001
        inactive,
        label="inactive selected atom",
    ) == (0, None)

    with pytest.raises(validator.MaximumProtocolValidationError):
        validator._validate_state_cell(  # noqa: SLF001
            _exact_cell(inactive, validator),
            label="inactive state cell",
        )

    with pytest.raises(validator.MaximumProtocolValidationError):
        validator._validate_activation_guards(  # noqa: SLF001
            [
                {
                    "guard_clause_position": 1,
                    "prior_choice_coordinate_plan_id": "5" * 64,
                    "guard_operator": "EQUALS",
                    "guard_atom": inactive,
                }
            ],
            label="inactive guard atom",
        )


def test_inactive_guard_sentinel_cell_schema_and_dimension_legality(
    validator: ModuleType,
) -> None:
    sentinel = _inactive_guard_sentinel_cell(validator)
    assert (
        validator._validate_state_cell(  # noqa: SLF001
            sentinel,
            label="inactive-guard sentinel",
        )
        is sentinel
    )

    corrupt_payload = copy.deepcopy(sentinel)
    corrupt_payload["exact_atom"] = _boolean_atom(False)
    payload = {
        name: item for name, item in corrupt_payload.items() if name != "state_cell_id"
    }
    corrupt_payload["state_cell_id"] = validator._semantic_id(  # noqa: SLF001
        validator.STATE_CELL_DOMAIN,
        payload,
    )
    with pytest.raises(validator.MaximumProtocolValidationError):
        validator._validate_state_cell(  # noqa: SLF001
            corrupt_payload,
            label="sentinel with payload",
        )

    guard = {
        "guard_clause_position": 1,
        "prior_choice_coordinate_plan_id": "6" * 64,
        "guard_operator": "EQUALS",
        "guard_atom": _boolean_atom(True),
    }
    guarded_dimension = _dimension(
        validator,
        position=1,
        kind="BOOLEAN_VALUE",
        activation_guards=[guard],
    )
    dimensions, signature = validator._validate_state_dimensions(  # noqa: SLF001
        [guarded_dimension],
        label="guarded dimension",
    )
    guarded_frontier = {
        "frontier_soundness": "EXACT_ATTAINABLE",
        "state_signature_id": signature,
        "ordered_observable_descriptor_ids": [
            guarded_dimension["observable_descriptor_id"]
        ],
        "ordered_state_frontiers": [
            {
                "state_key": [sentinel],
                "ordered_length_bitmap_runs": _one_length_run(1),
            }
        ],
    }
    validator._validate_materialized_frontier(  # noqa: SLF001
        guarded_frontier,
        dimensions=dimensions,
        state_signature_id=signature,
        label="guarded sentinel frontier",
    )

    unguarded_dimension = _dimension(
        validator,
        position=1,
        kind="BOOLEAN_VALUE",
    )
    _, unguarded_signature = validator._validate_state_dimensions(  # noqa: SLF001
        [unguarded_dimension],
        label="unguarded dimension",
    )
    unguarded_frontier = copy.deepcopy(guarded_frontier)
    unguarded_frontier["state_signature_id"] = unguarded_signature
    unguarded_frontier["ordered_observable_descriptor_ids"] = [
        unguarded_dimension["observable_descriptor_id"]
    ]
    with pytest.raises(validator.MaximumProtocolValidationError):
        validator._validate_materialized_frontier(  # noqa: SLF001
            unguarded_frontier,
            dimensions=[unguarded_dimension],
            state_signature_id=unguarded_signature,
            label="unguarded sentinel frontier",
        )

    with pytest.raises(validator.MaximumProtocolValidationError):
        validator._validate_prefix_frontier_shape(  # noqa: SLF001
            coordinate_activation="ACTIVE",
            selected_atom=_boolean_atom(False),
            input_dimensions=[],
            input_frontier=_frontier(_one_length_run(1), validator),
            output_dimensions=[guarded_dimension],
            output_frontier=guarded_frontier,
            label="active prefix sentinel",
        )


def test_exact_text_and_cardinality_dimensions_reject_catalog_cells(
    validator: ModuleType,
) -> None:
    catalog_cell = _catalog_cell("7" * 64, 0, validator)
    for dimension_kind in ("TEXT_VALUE", "ARRAY_CARDINALITY"):
        with pytest.raises(validator.MaximumProtocolValidationError):
            validator._validate_cell_for_dimension(  # noqa: SLF001
                catalog_cell,
                {"dimension_kind": dimension_kind},
                label=f"{dimension_kind} catalog cell",
            )

    validator._validate_cell_for_dimension(  # noqa: SLF001
        catalog_cell,
        {"dimension_kind": "TEXT_RELATION_CLASS"},
        label="text-relation catalog cell",
    )


def test_prior_position_graph_accepts_only_last_rooted_complete_dag(
    validator: ModuleType,
) -> None:
    assert validator._validate_prior_position_graph(  # noqa: SLF001
        [[], [1], [1, 2]],
        root_position=3,
        label="valid DAG",
    ) == [1, 2, 3]

    adversarial_graphs = (
        ([[2], []], 2),
        ([[], [1, 1]], 2),
        ([[], [], [2]], 3),
        ([[], [1]], 1),
        ([[], [True]], 2),
    )
    for child_rows, root_position in adversarial_graphs:
        with pytest.raises(validator.MaximumProtocolValidationError):
            validator._validate_prior_position_graph(  # noqa: SLF001
                child_rows,
                root_position=root_position,
                label="adversarial DAG",
            )


def test_transient_locator_must_bind_the_named_direct_child(
    validator: ModuleType,
) -> None:
    locator = _transient_locator()
    validator._validate_transient_locator_binding(  # noqa: SLF001
        locator,
        child_positions=[1],
        child_ids=["1" * 64],
        label="bound transient locator",
    )

    wrong_position = copy.deepcopy(locator)
    wrong_position["transient_source_child_position"] = 2
    with pytest.raises(validator.MaximumProtocolValidationError):
        validator._validate_transient_locator_binding(  # noqa: SLF001
            wrong_position,
            child_positions=[1],
            child_ids=["1" * 64],
            label="forward transient locator",
        )

    wrong_identity = copy.deepcopy(locator)
    wrong_identity["transient_source_child_proof_node_id"] = "3" * 64
    with pytest.raises(validator.MaximumProtocolValidationError):
        validator._validate_transient_locator_binding(  # noqa: SLF001
            wrong_identity,
            child_positions=[1],
            child_ids=["1" * 64],
            label="wrong transient identity",
        )


def test_guarded_prefix_frontier_shape_distinguishes_active_and_inactive(
    validator: ModuleType,
) -> None:
    input_frontier = _frontier(_one_length_run(), validator)
    input_node = {
        "ordered_ancestor_observable_dimensions": [],
        "output_frontier": input_frontier,
    }
    inactive = _primitive_atom("INACTIVE")
    validator._validate_prefix_frontier_shape(  # noqa: SLF001
        coordinate_activation="INACTIVE",
        selected_atom=inactive,
        input_dimensions=input_node["ordered_ancestor_observable_dimensions"],
        input_frontier=input_frontier,
        output_dimensions=[],
        output_frontier=input_frontier,
        label="inactive prefix",
    )

    selected = _boolean_atom(False)
    appended_dimension = _dimension(
        validator,
        position=1,
        kind="BOOLEAN_VALUE",
    )
    active_frontier = copy.deepcopy(input_frontier)
    active_frontier["ordered_state_frontiers"][0]["state_key"] = [
        _exact_cell(selected, validator)
    ]
    validator._validate_prefix_frontier_shape(  # noqa: SLF001
        coordinate_activation="ACTIVE",
        selected_atom=selected,
        input_dimensions=input_node["ordered_ancestor_observable_dimensions"],
        input_frontier=input_frontier,
        output_dimensions=[appended_dimension],
        output_frontier=active_frontier,
        label="active prefix",
    )

    wrong_atom_frontier = copy.deepcopy(active_frontier)
    wrong_atom_frontier["ordered_state_frontiers"][0]["state_key"][-1] = _exact_cell(
        _boolean_atom(True), validator
    )
    with pytest.raises(validator.MaximumProtocolValidationError):
        validator._validate_prefix_frontier_shape(  # noqa: SLF001
            coordinate_activation="ACTIVE",
            selected_atom=selected,
            input_dimensions=input_node["ordered_ancestor_observable_dimensions"],
            input_frontier=input_frontier,
            output_dimensions=[appended_dimension],
            output_frontier=wrong_atom_frontier,
            label="wrong active prefix",
        )

    with pytest.raises(validator.MaximumProtocolValidationError):
        validator._validate_prefix_frontier_shape(  # noqa: SLF001
            coordinate_activation="INACTIVE",
            selected_atom=inactive,
            input_dimensions=input_node["ordered_ancestor_observable_dimensions"],
            input_frontier=input_frontier,
            output_dimensions=[appended_dimension],
            output_frontier=active_frontier,
            label="dimension-adding inactive prefix",
        )


def test_tagged_v2_alias_chain_reuses_evidence_and_counts_only_materializations(
    validator: ModuleType,
) -> None:
    nodes, authorities, evidence = _alias_v2_proof_dag(validator)

    validated, recomputed = validator._validate_proof_dag(  # noqa: SLF001
        nodes,
        **authorities,
        label="tagged V2 alias proof DAG",
    )

    assert validated == nodes
    assert recomputed["frontier_state_entry_count"] == 2 * int(
        evidence["state_entry_count"]
    )
    assert recomputed["frontier_bitmap_run_count"] == 2 * int(
        evidence["bitmap_run_count"]
    )
    assert recomputed["frontier_expanded_point_count"] == 2 * int(
        evidence["expanded_attainable_point_count"]
    )
    assert recomputed["frontier_canonicalized_octets"] == 2 * int(
        evidence["frontier_canonicalized_octets"]
    )
    assert recomputed["maximum_frontier_width"] == int(
        evidence["expanded_attainable_point_count"]
    )
    encoding_octets: list[int] = []
    commitment_octets: list[int] = []
    for node in nodes:
        output = node["output_frontier"]
        retained_object = (
            output["materialized_frontier"]
            if output["frontier_encoding_kind"] == "MATERIALIZED"
            else output["direct_child_alias"]
        )
        encoding_octets.append(len(_canonical(retained_object)))
        commitment_octets.append(len(_canonical(node["frontier_commitment"])))
    expected_peak = max(
        encoding_octets[0] + commitment_octets[0],
        sum(encoding_octets[:2]) + sum(commitment_octets[:2]),
        sum(encoding_octets[:3]) + sum(commitment_octets[:3]),
        sum(encoding_octets) + sum(commitment_octets[index] for index in (0, 2, 3)),
    )
    assert recomputed["peak_retained_frontier_octets"] == expected_peak


@pytest.mark.parametrize(
    "corruption",
    (
        "legacy_untagged_frontier",
        "materialized_mandatory_alias",
        "alias_mandatory_materialization",
        "forged_child_identity",
        "forged_materialized_origin",
        "wrong_direct_child",
        "dual_payload",
    ),
)
def test_tagged_v2_rejects_legacy_optional_or_forged_aliases(
    validator: ModuleType,
    corruption: str,
) -> None:
    nodes, authorities, _ = _alias_v2_proof_dag(validator)
    if corruption == "legacy_untagged_frontier":
        nodes[0]["output_frontier"] = copy.deepcopy(
            nodes[0]["output_frontier"]["materialized_frontier"]
        )
    elif corruption == "materialized_mandatory_alias":
        nodes[0]["output_frontier"] = _tagged_alias(
            child_position=1,
            child_id="f" * 64,
            origin_position=1,
        )
    elif corruption == "alias_mandatory_materialization":
        nodes[2]["output_frontier"] = _tagged_materialized(
            copy.deepcopy(nodes[1]["output_frontier"]["materialized_frontier"])
        )
    elif corruption == "forged_child_identity":
        nodes[2]["output_frontier"]["direct_child_alias"][
            "aliased_child_proof_node_id"
        ] = "f" * 64
    elif corruption == "forged_materialized_origin":
        nodes[3]["output_frontier"]["direct_child_alias"][
            "resolved_materialized_origin_position"
        ] = 1
    elif corruption == "wrong_direct_child":
        nodes[3]["output_frontier"] = _tagged_alias(
            child_position=1,
            child_id=nodes[0]["proof_node_id"],
            origin_position=1,
        )
    else:
        nodes[2]["output_frontier"]["materialized_frontier"] = copy.deepcopy(
            nodes[1]["output_frontier"]["materialized_frontier"]
        )

    with pytest.raises(validator.MaximumProtocolValidationError):
        validator._validate_proof_dag(  # noqa: SLF001
            nodes,
            **authorities,
            label=f"corrupt tagged V2 alias proof DAG: {corruption}",
        )


def test_derivation_is_validated_before_alias_eligibility(
    validator: ModuleType,
) -> None:
    nodes, authorities, _ = _alias_v2_proof_dag(validator)
    nodes[2]["derivation"]["coordinate_activation"] = "BROKEN"
    nodes[2]["output_frontier"] = _tagged_materialized(
        copy.deepcopy(nodes[1]["output_frontier"]["materialized_frontier"])
    )

    with pytest.raises(
        validator.MaximumProtocolValidationError,
        match="coordinate activation differs",
    ):
        validator._validate_proof_dag(  # noqa: SLF001
            nodes,
            **authorities,
            label="derivation-before-output proof DAG",
        )


def test_direct_child_alias_depth_and_resolution_handle_are_closed(
    validator: ModuleType,
) -> None:
    frontier = _frontier(_one_length_run(1), validator)
    materialized, evidence = validator._validate_materialized_frontier(  # noqa: SLF001
        frontier,
        dimensions=[],
        state_signature_id=_empty_signature(validator),
        label="alias origin",
    )
    origin_resolution = {
        "frontier_encoding_kind": "MATERIALIZED",
        "resolved_materialized_frontier": materialized,
        "resolved_materialized_origin_position": 1,
        "alias_depth": 0,
        "frontier_evidence": evidence,
    }
    first_output = _tagged_alias(
        child_position=1,
        child_id="1" * 64,
        origin_position=1,
    )
    _, first_resolution = validator._validate_output_frontier(  # noqa: SLF001
        first_output,
        dimensions=[],
        state_signature_id=_empty_signature(validator),
        node_kind="LEXICOGRAPHIC_PREFIX_EXCLUSION",
        derivation={
            "coordinate_activation": "INACTIVE",
            "input_prefix_frontier_child_position": 1,
        },
        node_position=2,
        child_positions=[1],
        child_ids=["1" * 64],
        prior_frontier_resolutions=[origin_resolution],
        proof_depth=1,
        label="first direct-child alias",
    )
    assert first_resolution["resolved_materialized_frontier"] is materialized
    assert first_resolution["frontier_evidence"] is evidence
    assert first_resolution["alias_depth"] == 1

    second_output = _tagged_alias(
        child_position=2,
        child_id="2" * 64,
        origin_position=1,
    )
    second_arguments = {
        "dimensions": [],
        "state_signature_id": _empty_signature(validator),
        "node_kind": "LEXICOGRAPHIC_PREFIX_EXCLUSION",
        "derivation": {
            "coordinate_activation": "INACTIVE",
            "input_prefix_frontier_child_position": 2,
        },
        "node_position": 3,
        "child_positions": [2],
        "child_ids": ["2" * 64],
        "prior_frontier_resolutions": [origin_resolution, first_resolution],
        "label": "second direct-child alias",
    }
    _, second_resolution = validator._validate_output_frontier(  # noqa: SLF001
        second_output,
        proof_depth=2,
        **second_arguments,
    )
    assert second_resolution["resolved_materialized_frontier"] is materialized
    assert second_resolution["frontier_evidence"] is evidence
    assert second_resolution["alias_depth"] == 2
    with pytest.raises(
        validator.MaximumProtocolValidationError,
        match="alias depth exceeds",
    ):
        validator._validate_output_frontier(  # noqa: SLF001
            second_output,
            proof_depth=1,
            **second_arguments,
        )


@pytest.mark.parametrize(
    ("node_index", "digest_field"),
    (
        (2, "least_context_choice_vector_sha256_at_maximum"),
        (3, "least_measured_choice_vector_sha256_at_maximum"),
    ),
)
def test_alias_commitments_reject_preserved_scope_or_codec_drift(
    validator: ModuleType,
    node_index: int,
    digest_field: str,
) -> None:
    nodes, authorities, _ = _alias_v2_proof_dag(validator)
    commitment = nodes[node_index]["frontier_commitment"]
    commitment[digest_field] = "f" * 64
    commitment["frontier_commitment_id"] = validator._semantic_id(  # noqa: SLF001
        validator.FRONTIER_COMMITMENT_DOMAIN,
        {
            name: item
            for name, item in commitment.items()
            if name != "frontier_commitment_id"
        },
    )

    with pytest.raises(validator.MaximumProtocolValidationError):
        validator._validate_proof_dag(  # noqa: SLF001
            nodes,
            **authorities,
            label="alias commitment drift proof DAG",
        )


def test_frontier_encoding_version_requires_tagged_v2(
    validator: ModuleType,
) -> None:
    assert (
        validator._validate_frontier_encoding_version(  # noqa: SLF001
            validator.FRONTIER_ENCODING_VERSION,
            label="tagged V2 version",
        )
        == validator.FRONTIER_ENCODING_VERSION
    )
    with pytest.raises(validator.MaximumProtocolValidationError):
        validator._validate_frontier_encoding_version(  # noqa: SLF001
            "FIXED_256_LENGTH_BITMAP_BLOCKS_V1",
            label="legacy V1 version",
        )


def test_derived_state_catalog_shape_identity_order_and_prior_references(
    validator: ModuleType,
) -> None:
    protocol_sha = "a" * 64
    catalog = {
        "catalog_version": (
            "riskyieldmm.raw_v8_step2_external_schema_v2.maximum_state_catalog.v1"
        ),
        "catalog_kind": "TEXT_RELATION_SLICE",
        "defining_subject_locator": _schema_locator(),
        "defining_value_schema_id": "0" * 64,
        "ordered_observable_descriptor_ids": [],
        "ordered_catalog_entries": [
            {
                "catalog_position": position,
                "ordered_partition_atoms": [_boolean_atom(value)],
                "ordered_partition_state_cells": [],
                "canonical_representative_atom": _primitive_atom("TEXT", text),
                "ordered_attainable_length_bitmap_runs": _one_length_run(position),
            }
            for position, (value, text) in enumerate(((False, "a"), (True, "b")))
        ],
    }
    catalog_id = validator._semantic_id(  # noqa: SLF001
        validator.DERIVED_STATE_CATALOG_DOMAIN,
        {"maximum_protocol_sha256": protocol_sha, **catalog},
    )
    meter = validator.ProofResourceMeter(phase=validator.SEED_CAP_DERIVATION_PHASE)
    evidence = validator._validate_derived_state_catalog(  # noqa: SLF001
        catalog,
        maximum_protocol_sha256=protocol_sha,
        expected_catalog_id=catalog_id,
        allowed_prior_catalog_ids=frozenset(),
        label="derived state catalog",
        resource_meter=meter,
    )
    root_envelope = {
        "canonicalization_version": validator.CANONICALIZATION_VERSION,
        "domain": validator.DERIVED_STATE_CATALOG_DOMAIN,
        "payload": {"maximum_protocol_sha256": protocol_sha, **catalog},
        "schema_version": validator.MEASUREMENT_SCHEMA_VERSION,
    }
    assert evidence.catalog is catalog
    assert evidence.entry_count == 2
    assert evidence.complete_root_octets == len(_canonical(catalog))
    assert evidence.validation_hash_preimage_octets == len(_canonical(root_envelope))
    assert evidence.referenced_prior_catalog_ids == ()
    assert meter.value("state_catalog_entry_count") == 2
    assert meter.value("state_catalog_canonicalized_octets") == len(_canonical(catalog))

    reversed_catalog = copy.deepcopy(catalog)
    reversed_catalog["ordered_catalog_entries"].reverse()
    for position, entry in enumerate(reversed_catalog["ordered_catalog_entries"]):
        entry["catalog_position"] = position
    reversed_id = validator._semantic_id(  # noqa: SLF001
        validator.DERIVED_STATE_CATALOG_DOMAIN,
        {"maximum_protocol_sha256": protocol_sha, **reversed_catalog},
    )
    with pytest.raises(validator.MaximumProtocolValidationError):
        validator._validate_derived_state_catalog(  # noqa: SLF001
            reversed_catalog,
            maximum_protocol_sha256=protocol_sha,
            expected_catalog_id=reversed_id,
            allowed_prior_catalog_ids=frozenset(),
            label="reversed derived state catalog",
        )

    forward_reference = copy.deepcopy(catalog)
    forward_reference["ordered_catalog_entries"][0]["ordered_partition_state_cells"] = [
        _catalog_cell("9" * 64, 0, validator)
    ]
    forward_reference_id = validator._semantic_id(  # noqa: SLF001
        validator.DERIVED_STATE_CATALOG_DOMAIN,
        {"maximum_protocol_sha256": protocol_sha, **forward_reference},
    )
    with pytest.raises(validator.MaximumProtocolValidationError):
        validator._validate_derived_state_catalog(  # noqa: SLF001
            forward_reference,
            maximum_protocol_sha256=protocol_sha,
            expected_catalog_id=forward_reference_id,
            allowed_prior_catalog_ids=frozenset(),
            label="forward-referencing derived state catalog",
        )


def test_catalog_entry_cap_rejects_atomically_before_any_catalog_hash(
    validator: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    protocol_sha = "a" * 64
    catalog = {
        "catalog_version": (
            "riskyieldmm.raw_v8_step2_external_schema_v2.maximum_state_catalog.v1"
        ),
        "catalog_kind": "TEXT_RELATION_SLICE",
        "defining_subject_locator": _schema_locator(),
        "defining_value_schema_id": "0" * 64,
        "ordered_observable_descriptor_ids": [],
        "ordered_catalog_entries": [
            {
                "catalog_position": 0,
                "ordered_partition_atoms": [_boolean_atom(False)],
                "ordered_partition_state_cells": [],
                "canonical_representative_atom": _primitive_atom("TEXT", "a"),
                "ordered_attainable_length_bitmap_runs": _one_length_run(),
            }
        ],
    }
    catalog_id = validator._semantic_id(  # noqa: SLF001
        validator.DERIVED_STATE_CATALOG_DOMAIN,
        {"maximum_protocol_sha256": protocol_sha, **catalog},
    )
    limits = {
        name: validator.SEED_EXECUTION_SAFETY_LIMITS_V1[name]
        for name in validator.ACCEPTED_PROOF_RESOURCE_LIMIT_KEYS
    }
    limits["state_catalog_entry_count"] = 0
    meter = validator.ProofResourceMeter(
        phase=validator.FINAL_PROTOCOL_REBIND_PHASE,
        accepted_limits=limits,
    )
    called = False

    def forbidden_sha256(*_: Any, **__: Any) -> Any:
        nonlocal called
        called = True
        raise AssertionError("catalog hash began before the atomic resource reserve")

    monkeypatch.setattr(validator.hashlib, "sha256", forbidden_sha256)
    with pytest.raises(validator.MaximumProtocolValidationError):
        validator._validate_derived_state_catalog(  # noqa: SLF001
            catalog,
            maximum_protocol_sha256=protocol_sha,
            expected_catalog_id=catalog_id,
            allowed_prior_catalog_ids=frozenset(),
            label="entry-cap catalog",
            resource_meter=meter,
        )
    assert not called
    assert meter.value("state_catalog_entry_count") == 0
    assert meter.value("state_catalog_canonicalized_octets") == 0
    assert meter.value("hash_preimage_octets") == 0


def test_catalog_retention_is_occurrence_sensitive_transitive_and_cap_first(
    validator: ModuleType,
) -> None:
    first = validator.CatalogOccurrenceKey(1, 1)
    second = validator.CatalogOccurrenceKey(2, 1)
    transient = validator.CatalogOccurrenceKey(3, 1)
    repeated_catalog_id = "a" * 64
    occurrences = [
        validator.CatalogOccurrence(
            first,
            repeated_catalog_id,
            100,
            (),
            "PERSISTENT_INTERNAL",
        ),
        validator.CatalogOccurrence(
            second,
            repeated_catalog_id,
            100,
            (first,),
            "PERSISTENT_INTERNAL",
        ),
        validator.CatalogOccurrence(
            transient,
            "b" * 64,
            50,
            (first,),
            "CURRENT_NODE_TRANSIENT",
        ),
    ]
    arguments = {
        "node_count": 4,
        "frontier_encoding_release_positions": [3, 4, 3, 4],
        "node_transfer_dependencies": [(), (), (first, transient), ()],
        "node_frontier_dependencies": [(first,), (second,), (), ()],
        "occurrences": occurrences,
        "label": "catalog retention",
    }
    meter = validator.ProofResourceMeter(phase=validator.SEED_CAP_DERIVATION_PHASE)
    evidence = validator._derive_catalog_retention_evidence(  # noqa: SLF001
        **arguments,
        meter=meter,
    )
    assert evidence.last_use_by_occurrence == {
        first: 4,
        second: 4,
        transient: 3,
    }
    assert evidence.peak_retained_octets == 250
    assert meter.value("peak_retained_state_catalog_octets") == 250
    assert evidence.release_buckets[3] == (transient,)
    assert evidence.release_buckets[4] == (first, second)

    limits = {
        name: validator.SEED_EXECUTION_SAFETY_LIMITS_V1[name]
        for name in validator.ACCEPTED_PROOF_RESOURCE_LIMIT_KEYS
    }
    limits["peak_retained_state_catalog_octets"] = 249
    capped_meter = validator.ProofResourceMeter(
        phase=validator.FINAL_PROTOCOL_REBIND_PHASE,
        accepted_limits=limits,
    )
    with pytest.raises(
        validator.MaximumProtocolValidationError,
        match="prospective value 250 exceeds effective limit 249",
    ):
        validator._derive_catalog_retention_evidence(  # noqa: SLF001
            **arguments,
            meter=capped_meter,
        )
    assert capped_meter.value("peak_retained_state_catalog_octets") == 200

    escaping = dict(arguments)
    escaping["node_transfer_dependencies"] = [(), (), (first,), (transient,)]
    with pytest.raises(
        validator.MaximumProtocolValidationError,
        match="transient catalog escapes",
    ):
        validator._derive_catalog_retention_evidence(  # noqa: SLF001
            **escaping,
            meter=validator.ProofResourceMeter(
                phase=validator.SEED_CAP_DERIVATION_PHASE
            ),
        )


def test_transient_recurrence_catalog_shape_identity_and_order(
    validator: ModuleType,
) -> None:
    protocol_sha = "b" * 64
    state_records = [
        _ordered_string_state(
            position=1,
            state_kind="SUFFIX_COUNT_RUN",
            key_atoms=[
                _primitive_atom("SAFE_INTEGER", 0),
                _primitive_atom("SAFE_INTEGER", 0),
            ],
            payload_atoms=[_primitive_atom("SAFE_INTEGER", 1)],
        ),
        _ordered_string_state(
            position=2,
            state_kind="SUFFIX_COUNT_RUN",
            key_atoms=[
                _primitive_atom("SAFE_INTEGER", 1),
                _primitive_atom("SAFE_INTEGER", 1),
            ],
            payload_atoms=[_primitive_atom("SAFE_INTEGER", 2)],
        ),
    ]
    catalog = _transient_recurrence_catalog(
        validator,
        kind="ORDERED_RAW_STRING_PREFIX_FEASIBILITY_V1",
        protocol_sha=protocol_sha,
        state_records=state_records,
    )
    catalog_id = catalog["recurrence_catalog_id"]
    meter = validator.ProofResourceMeter(phase=validator.SEED_CAP_DERIVATION_PHASE)
    evidence = validator._validate_transient_recurrence_catalog(  # noqa: SLF001
        catalog,
        maximum_protocol_sha256=protocol_sha,
        expected_catalog_id=catalog_id,
        allowed_prior_catalog_ids=frozenset(),
        label="transient recurrence catalog",
        resource_meter=meter,
    )
    root_payload = {
        "maximum_protocol_sha256": protocol_sha,
        **{
            name: item
            for name, item in catalog.items()
            if name != "recurrence_catalog_id"
        },
    }
    root_envelope = {
        "canonicalization_version": validator.CANONICALIZATION_VERSION,
        "domain": validator.TRANSIENT_RECURRENCE_CATALOG_DOMAIN,
        "payload": root_payload,
        "schema_version": validator.MEASUREMENT_SCHEMA_VERSION,
    }
    expected_entry_count = sum(
        len(catalog[name])
        for name in (
            "ordered_scalar_prefix_records",
            "ordered_primitive_prefix_records",
            "ordered_lex_interval_records",
            "ordered_state_records",
        )
    )
    assert evidence.catalog is catalog
    assert evidence.entry_count == expected_entry_count
    assert evidence.complete_root_octets == len(_canonical(catalog))
    assert evidence.validation_hash_preimage_octets == len(_canonical(root_envelope))
    assert evidence.referenced_prior_catalog_ids == ()
    assert meter.value("state_catalog_entry_count") == expected_entry_count

    duplicate_key = copy.deepcopy(catalog)
    duplicate_key["ordered_state_records"][1]["ordered_state_key_atoms"] = (
        copy.deepcopy(
            duplicate_key["ordered_state_records"][0]["ordered_state_key_atoms"]
        )
    )
    duplicate_payload = {
        "maximum_protocol_sha256": protocol_sha,
        **{
            name: item
            for name, item in duplicate_key.items()
            if name != "recurrence_catalog_id"
        },
    }
    duplicate_id = validator._semantic_id(  # noqa: SLF001
        validator.TRANSIENT_RECURRENCE_CATALOG_DOMAIN,
        duplicate_payload,
    )
    duplicate_key["recurrence_catalog_id"] = duplicate_id
    with pytest.raises(validator.MaximumProtocolValidationError):
        validator._validate_transient_recurrence_catalog(  # noqa: SLF001
            duplicate_key,
            maximum_protocol_sha256=protocol_sha,
            expected_catalog_id=duplicate_id,
            allowed_prior_catalog_ids=frozenset(),
            label="duplicate transient recurrence key",
        )


@pytest.mark.parametrize(
    "raw",
    (
        b"",
        b"\xff",
        b"[ ]",
        b"[1.0]",
        b"[1][2]",
        b'[{"a":1,"a":2}]',
        b'[{"b":1,"a":2}]',
    ),
)
def test_ordered_string_slot_json_requires_strict_canonical_round_trip(
    validator: ModuleType,
    raw: bytes,
) -> None:
    with pytest.raises(validator.MaximumProtocolValidationError):
        validator._decode_ordered_string_slot_json(  # noqa: SLF001
            raw,
            label="ordered-string canonical slot",
        )


def test_ordered_string_count_frontier_schema_bounds_and_no_expansion(
    validator: ModuleType,
) -> None:
    valid = _count_frontier(
        _one_length_run(0),
        _one_length_run(2),
        [],
    )
    assert (
        validator._decode_ordered_string_count_frontier(  # noqa: SLF001
            _canonical(valid),
            item_count_limit=2,
            maximum_total_octets=10,
            label="count frontier",
        )
        == valid
    )

    corruptions = []
    wrong_root = {"item_count": 0, "ordered_total_octet_bitmap_runs": []}
    corruptions.append(wrong_root)

    missing_row = copy.deepcopy(valid[:-1])
    corruptions.append(missing_row)

    noncontiguous = copy.deepcopy(valid)
    noncontiguous[1]["item_count"] = 2
    corruptions.append(noncontiguous)

    extra_member = copy.deepcopy(valid)
    extra_member[1]["producer_hint"] = True
    corruptions.append(extra_member)

    wrong_zero_support = copy.deepcopy(valid)
    wrong_zero_support[0]["ordered_total_octet_bitmap_runs"] = _one_length_run(1)
    corruptions.append(wrong_zero_support)

    out_of_bound_bit = copy.deepcopy(valid)
    out_of_bound_bit[1]["ordered_total_octet_bitmap_runs"] = _one_length_run(11)
    corruptions.append(out_of_bound_bit)

    huge_unexpanded_run = copy.deepcopy(valid)
    huge_unexpanded_run[1]["ordered_total_octet_bitmap_runs"] = [
        {
            "first_block_index": 0,
            "last_block_index": 1_000_000_000_000,
            "attainable_length_bitmap_hex": f"{1:064x}",
        }
    ]
    corruptions.append(huge_unexpanded_run)

    for position, corrupt in enumerate(corruptions, 1):
        with pytest.raises(validator.MaximumProtocolValidationError):
            validator._decode_ordered_string_count_frontier(  # noqa: SLF001
                _canonical(corrupt),
                item_count_limit=2,
                maximum_total_octets=10,
                label=f"count frontier corruption {position}",
            )


def test_ordered_string_completion_positions_are_exact_bounded_and_lexical(
    validator: ModuleType,
) -> None:
    scalar_prefixes = _ordered_string_scalar_prefix_pool()
    validator._validate_scalar_prefix_pool(  # noqa: SLF001
        scalar_prefixes,
        label="ordered-string scalar pool",
    )
    meter = validator.ProofResourceMeter(phase=validator.SEED_CAP_DERIVATION_PHASE)
    assert validator._decode_ordered_string_least_completion_prefix_positions(  # noqa: SLF001
        _canonical([3, 2]),
        expected_remaining_items=2,
        scalar_prefixes=scalar_prefixes,
        preceding_prefix_positions=(1,),
        label="least completion",
        resource_meter=meter,
    ) == [3, 2]
    assert (
        validator._decode_ordered_string_least_completion_prefix_positions(  # noqa: SLF001
            b"[]",
            expected_remaining_items=0,
            scalar_prefixes=scalar_prefixes,
            label="empty least completion",
            resource_meter=meter,
        )
        == []
    )

    corruptions = (
        ([1], 2, ()),
        ([True, 2], 2, ()),
        ([4, 2], 2, ()),
        ([2, 1], 2, ()),
        ([1], 1, (2,)),
    )
    for position, (values, expected_length, preceding) in enumerate(corruptions, 1):
        with pytest.raises(validator.MaximumProtocolValidationError):
            validator._decode_ordered_string_least_completion_prefix_positions(  # noqa: SLF001
                _canonical(values),
                expected_remaining_items=expected_length,
                scalar_prefixes=scalar_prefixes,
                preceding_prefix_positions=preceding,
                label=f"least-completion corruption {position}",
                resource_meter=validator.ProofResourceMeter(
                    phase=validator.SEED_CAP_DERIVATION_PHASE
                ),
            )


def test_ordered_string_cardinality_bitmap_schema_bounds_and_no_expansion(
    validator: ModuleType,
) -> None:
    valid = [
        {
            "first_block_index": 0,
            "last_block_index": 0,
            "attainable_length_bitmap_hex": f"{(1 << 2) | (1 << 4):064x}",
        }
    ]
    assert (
        validator._decode_ordered_string_feasible_cardinality_bitmap_runs(  # noqa: SLF001
            _canonical(valid),
            minimum_array_cardinality=2,
            maximum_array_cardinality=4,
            label="cardinality support",
        )
        == valid
    )
    assert (
        validator._decode_ordered_string_feasible_cardinality_bitmap_runs(  # noqa: SLF001
            b"[]",
            minimum_array_cardinality=2,
            maximum_array_cardinality=4,
            label="empty cardinality support",
        )
        == []
    )

    corruptions = (
        _one_length_run(1),
        _one_length_run(5),
        [
            {
                "first_block_index": 0,
                "last_block_index": 1_000_000_000_000,
                "attainable_length_bitmap_hex": f"{1 << 2:064x}",
            }
        ],
    )
    for position, corrupt in enumerate(corruptions, 1):
        with pytest.raises(validator.MaximumProtocolValidationError):
            validator._decode_ordered_string_feasible_cardinality_bitmap_runs(  # noqa: SLF001
                _canonical(corrupt),
                minimum_array_cardinality=2,
                maximum_array_cardinality=4,
                label=f"cardinality corruption {position}",
            )


def test_ordered_string_factor_and_all_cardinality_slots_are_closed(
    validator: ModuleType,
) -> None:
    protocol_sha = "7" * 64
    count_frontier = _count_frontier(_one_length_run(0), [])
    state_records = [
        _ordered_string_state(
            position=1,
            state_kind="FACTOR_RUN",
            key_atoms=[
                _primitive_atom("POSITION", 0),
                _primitive_atom("POSITION", 1),
            ],
            payload_atoms=[_canonical_bytes_atom(count_frontier)],
        ),
        _ordered_string_state(
            position=2,
            state_kind="QUERY_RESULT",
            key_atoms=[_primitive_atom("TEXT", "ALL_LEGAL_CARDINALITIES")],
            payload_atoms=[
                _primitive_atom("BOOLEAN", True),
                _canonical_bytes_atom(_one_length_run(0)),
                _primitive_atom("NULL"),
            ],
            attainable_runs=_one_length_run(2),
        ),
    ]
    catalog = _transient_recurrence_catalog(
        validator,
        kind="ORDERED_RAW_STRING_PREFIX_FEASIBILITY_V1",
        protocol_sha=protocol_sha,
        state_records=state_records,
    )
    catalog_id = catalog["recurrence_catalog_id"]
    assert (
        validator._validate_transient_recurrence_catalog(  # noqa: SLF001
            catalog,
            maximum_protocol_sha256=protocol_sha,
            expected_catalog_id=catalog_id,
            allowed_prior_catalog_ids=frozenset(),
            label="ordered-string all-cardinality catalog",
        ).catalog
        is catalog
    )

    noncanonical = copy.deepcopy(catalog)
    noncanonical["ordered_state_records"][0]["ordered_state_payload_atoms"][0][
        "canonical_bytes_hex_value"
    ] = b"[ ]".hex()
    noncanonical_id = _rehash_transient_recurrence_catalog(
        validator,
        noncanonical,
        protocol_sha=protocol_sha,
    )
    with pytest.raises(
        validator.MaximumProtocolValidationError,
        match="not canonical compact JSON",
    ):
        validator._validate_transient_recurrence_catalog(  # noqa: SLF001
            noncanonical,
            maximum_protocol_sha256=protocol_sha,
            expected_catalog_id=noncanonical_id,
            allowed_prior_catalog_ids=frozenset(),
            label="noncanonical factor slot",
        )

    false_with_support = copy.deepcopy(catalog)
    false_with_support["ordered_state_records"][1]["ordered_state_payload_atoms"][0] = (
        _primitive_atom("BOOLEAN", False)
    )
    false_with_support_id = _rehash_transient_recurrence_catalog(
        validator,
        false_with_support,
        protocol_sha=protocol_sha,
    )
    with pytest.raises(
        validator.MaximumProtocolValidationError,
        match="decision differs from cardinality support",
    ):
        validator._validate_transient_recurrence_catalog(  # noqa: SLF001
            false_with_support,
            maximum_protocol_sha256=protocol_sha,
            expected_catalog_id=false_with_support_id,
            allowed_prior_catalog_ids=frozenset(),
            label="false query with support",
        )


def test_ordered_string_direct_bulk_and_fixed_query_slots_are_closed(
    validator: ModuleType,
) -> None:
    protocol_sha = "8" * 64
    state_records = [
        _ordered_string_state(
            position=1,
            state_kind="BULK_UNRANK_TEST",
            key_atoms=[
                _primitive_atom("SAFE_INTEGER", 2),
                _primitive_atom("SAFE_INTEGER", 6),
                _primitive_atom("POSITION", 0),
                _primitive_atom("NULL"),
            ],
            payload_atoms=[
                _primitive_atom("BOOLEAN", True),
                _canonical_bytes_atom([1, 2]),
            ],
        ),
        _ordered_string_state(
            position=2,
            state_kind="K1_DIRECT_FEASIBILITY",
            key_atoms=[
                _primitive_atom("SAFE_INTEGER", 1),
                _primitive_atom("POSITION", 1),
            ],
            payload_atoms=[
                _primitive_atom("BOOLEAN", True),
                _primitive_atom("POSITION", 2),
            ],
        ),
        _ordered_string_state(
            position=3,
            state_kind="QUERY_RESULT",
            key_atoms=[_primitive_atom("TEXT", "FIXED_CARDINALITY")],
            payload_atoms=[
                _primitive_atom("BOOLEAN", True),
                _primitive_atom("NULL"),
                _canonical_bytes_atom([1, 2]),
            ],
            attainable_runs=_one_length_run(9),
        ),
    ]
    catalog = _transient_recurrence_catalog(
        validator,
        kind="ORDERED_RAW_STRING_PREFIX_FEASIBILITY_V1",
        protocol_sha=protocol_sha,
        state_records=state_records,
    )
    catalog["ordered_scalar_prefix_records"] = _ordered_string_scalar_prefix_pool()
    catalog["recurrence_parameters"].update(
        {
            "target_array_octets": 9,
            "cardinality_query_kind": "FIXED_CARDINALITY",
            "minimum_array_cardinality": 0,
            "maximum_array_cardinality": 2,
            "array_cardinality": 2,
            "per_string_canonical_octet_ceiling": 3,
        }
    )
    catalog_id = _rehash_transient_recurrence_catalog(
        validator,
        catalog,
        protocol_sha=protocol_sha,
    )
    assert (
        validator._validate_transient_recurrence_catalog(  # noqa: SLF001
            catalog,
            maximum_protocol_sha256=protocol_sha,
            expected_catalog_id=catalog_id,
            allowed_prior_catalog_ids=frozenset(),
            label="ordered-string fixed catalog",
        ).catalog
        is catalog
    )

    wrong_order = copy.deepcopy(catalog)
    wrong_order["ordered_state_records"][2]["ordered_state_payload_atoms"][2] = (
        _canonical_bytes_atom([2, 1])
    )
    wrong_order_id = _rehash_transient_recurrence_catalog(
        validator,
        wrong_order,
        protocol_sha=protocol_sha,
    )
    with pytest.raises(
        validator.MaximumProtocolValidationError,
        match="not strictly scalar-lex increasing",
    ):
        validator._validate_transient_recurrence_catalog(  # noqa: SLF001
            wrong_order,
            maximum_protocol_sha256=protocol_sha,
            expected_catalog_id=wrong_order_id,
            allowed_prior_catalog_ids=frozenset(),
            label="wrong-order fixed completion",
        )


@pytest.mark.parametrize(
    "recurrence_kind",
    (
        "ASCII_DFA_DYNAMIC_PROGRAM_V1",
        "UNICODE_15_NFC_DYNAMIC_PROGRAM_V1",
        "ORDERED_RAW_STRING_PREFIX_FEASIBILITY_V1",
        "DERIVED_IDENTITY_PREFIX_FEASIBILITY_V1",
    ),
)
def test_transient_recurrence_root_version_kinds_and_pool_matrix(
    validator: ModuleType,
    recurrence_kind: str,
) -> None:
    protocol_sha = "c" * 64
    catalog = _transient_recurrence_catalog(
        validator,
        kind=recurrence_kind,
        protocol_sha=protocol_sha,
    )
    assert set(catalog) == validator.TRANSIENT_RECURRENCE_CATALOG_KEYS
    assert (
        validator._validate_transient_recurrence_catalog(  # noqa: SLF001
            catalog,
            maximum_protocol_sha256=protocol_sha,
            expected_catalog_id=catalog["recurrence_catalog_id"],
            allowed_prior_catalog_ids=frozenset(),
            label=f"{recurrence_kind} catalog",
        ).catalog
        is catalog
    )


def test_transient_recurrence_rejects_legacy_root_and_schema_drift(
    validator: ModuleType,
) -> None:
    protocol_sha = "d" * 64
    base = _transient_recurrence_catalog(
        validator,
        kind="ORDERED_RAW_STRING_PREFIX_FEASIBILITY_V1",
        protocol_sha=protocol_sha,
    )
    corruptions: list[dict[str, Any]] = []

    legacy = {
        "recurrence_kind": base["recurrence_kind"],
        "defining_subject_locator": base["defining_subject_locator"],
        "ordered_state_records": [],
    }
    corruptions.append(legacy)

    wrong_version = copy.deepcopy(base)
    wrong_version["catalog_version"] = "legacy.v0"
    corruptions.append(wrong_version)

    wrong_kind = copy.deepcopy(base)
    wrong_kind["recurrence_kind"] = "HOST_CACHE_DYNAMIC_PROGRAM_V1"
    corruptions.append(wrong_kind)

    extra_root_member = copy.deepcopy(base)
    extra_root_member["producer_cache"] = []
    corruptions.append(extra_root_member)

    wrong_parameters = copy.deepcopy(base)
    wrong_parameters["recurrence_parameters"]["producer_hint"] = True
    corruptions.append(wrong_parameters)

    null_pool = copy.deepcopy(base)
    null_pool["ordered_scalar_prefix_records"] = None
    corruptions.append(null_pool)

    wrong_pool_matrix = copy.deepcopy(base)
    wrong_pool_matrix["ordered_primitive_prefix_records"] = [
        _empty_primitive_prefix_record()
    ]
    corruptions.append(wrong_pool_matrix)

    forged_embedded_id = copy.deepcopy(base)
    forged_embedded_id["recurrence_catalog_id"] = "f" * 64
    corruptions.append(forged_embedded_id)

    for position, corrupt in enumerate(corruptions, 1):
        with pytest.raises(validator.MaximumProtocolValidationError):
            validator._validate_transient_recurrence_catalog(  # noqa: SLF001
                corrupt,
                maximum_protocol_sha256=protocol_sha,
                expected_catalog_id=base["recurrence_catalog_id"],
                allowed_prior_catalog_ids=frozenset(),
                label=f"recurrence schema corruption {position}",
            )


def test_transient_recurrence_pool_records_are_exact_and_inactive_free(
    validator: ModuleType,
) -> None:
    protocol_sha = "e" * 64
    scalar = _transient_recurrence_catalog(
        validator,
        kind="ASCII_DFA_DYNAMIC_PROGRAM_V1",
        protocol_sha=protocol_sha,
    )
    scalar["ordered_scalar_prefix_records"][0]["host_pointer"] = 0

    primitive = _transient_recurrence_catalog(
        validator,
        kind="DERIVED_IDENTITY_PREFIX_FEASIBILITY_V1",
        protocol_sha=protocol_sha,
    )
    primitive["ordered_primitive_prefix_records"][0]["host_pointer"] = 0

    interval = _transient_recurrence_catalog(
        validator,
        kind="ORDERED_RAW_STRING_PREFIX_FEASIBILITY_V1",
        protocol_sha=protocol_sha,
    )
    interval["ordered_lex_interval_records"][0]["host_pointer"] = 0

    block = _transient_recurrence_catalog(
        validator,
        kind="ORDERED_RAW_STRING_PREFIX_FEASIBILITY_V1",
        protocol_sha=protocol_sha,
    )
    block["ordered_lex_interval_records"][0]["ordered_interval_blocks"][0][
        "host_pointer"
    ] = 0

    block_nullability = _transient_recurrence_catalog(
        validator,
        kind="ORDERED_RAW_STRING_PREFIX_FEASIBILITY_V1",
        protocol_sha=protocol_sha,
    )
    block_nullability["ordered_lex_interval_records"][0]["ordered_interval_blocks"][0][
        "inclusive_next_scalar_minimum"
    ] = 1

    inactive_state = _transient_recurrence_catalog(
        validator,
        kind="ASCII_DFA_DYNAMIC_PROGRAM_V1",
        protocol_sha=protocol_sha,
        state_records=[
            {
                "state_position": 1,
                "ordered_state_key_atoms": [_primitive_atom("INACTIVE")],
                "ordered_state_key_cells": [],
                "ordered_state_payload_atoms": [],
                "ordered_state_payload_cells": [],
                "ordered_attainable_length_bitmap_runs": [],
            }
        ],
    )

    for position, corrupt in enumerate(
        (scalar, primitive, interval, block, block_nullability, inactive_state),
        1,
    ):
        with pytest.raises(validator.MaximumProtocolValidationError):
            validator._validate_transient_recurrence_catalog(  # noqa: SLF001
                corrupt,
                maximum_protocol_sha256=protocol_sha,
                expected_catalog_id=corrupt["recurrence_catalog_id"],
                allowed_prior_catalog_ids=frozenset(),
                label=f"recurrence pool corruption {position}",
            )


def test_scalar_prefix_pool_derives_rle_cost_order_and_ascii_domain(
    validator: ModuleType,
) -> None:
    records = [
        _empty_scalar_prefix_record(),
        {
            "prefix_position": 1,
            "parent_prefix_position": 0,
            "appended_scalar_value": ord("a"),
            "appended_scalar_repeat_count": 1,
            "scalar_count": 1,
            "json_value_octets": 1,
        },
        {
            "prefix_position": 2,
            "parent_prefix_position": 0,
            "appended_scalar_value": ord("b"),
            "appended_scalar_repeat_count": 1,
            "scalar_count": 1,
            "json_value_octets": 1,
        },
        {
            "prefix_position": 3,
            "parent_prefix_position": 1,
            "appended_scalar_value": ord("b"),
            "appended_scalar_repeat_count": 1,
            "scalar_count": 2,
            "json_value_octets": 2,
        },
    ]
    assert (
        validator._validate_scalar_prefix_pool(  # noqa: SLF001
            records,
            label="scalar RLE pool",
            ascii_only=True,
        )
        is records
    )

    corruptions = []
    wrong_cost = copy.deepcopy(records)
    wrong_cost[3]["json_value_octets"] = 3
    corruptions.append(wrong_cost)

    adjacent_equal = copy.deepcopy(records[:2])
    adjacent_equal.append(
        {
            "prefix_position": 2,
            "parent_prefix_position": 1,
            "appended_scalar_value": ord("a"),
            "appended_scalar_repeat_count": 1,
            "scalar_count": 2,
            "json_value_octets": 2,
        }
    )
    corruptions.append(adjacent_equal)

    wrong_order = copy.deepcopy(records)
    wrong_order[1]["appended_scalar_value"] = ord("b")
    wrong_order[2]["appended_scalar_value"] = ord("a")
    corruptions.append(wrong_order)

    non_ascii = copy.deepcopy(records[:2])
    non_ascii[1]["appended_scalar_value"] = 0x80
    non_ascii[1]["json_value_octets"] = 2
    corruptions.append(non_ascii)

    for position, corrupt in enumerate(corruptions, 1):
        with pytest.raises(validator.MaximumProtocolValidationError):
            validator._validate_scalar_prefix_pool(  # noqa: SLF001
                corrupt,
                label=f"scalar RLE corruption {position}",
                ascii_only=True,
            )


def test_primitive_prefix_pool_derives_typed_vector_order(
    validator: ModuleType,
) -> None:
    records = [
        _empty_primitive_prefix_record(),
        {
            "prefix_position": 1,
            "parent_prefix_position": 0,
            "appended_choice_coordinate_plan_id": "1" * 64,
            "appended_atom": _boolean_atom(False),
            "active_atom_count": 1,
        },
        {
            "prefix_position": 2,
            "parent_prefix_position": 0,
            "appended_choice_coordinate_plan_id": "1" * 64,
            "appended_atom": _boolean_atom(True),
            "active_atom_count": 1,
        },
        {
            "prefix_position": 3,
            "parent_prefix_position": 1,
            "appended_choice_coordinate_plan_id": "2" * 64,
            "appended_atom": _primitive_atom("SAFE_INTEGER", 1),
            "active_atom_count": 2,
        },
    ]
    assert (
        validator._validate_primitive_prefix_pool(  # noqa: SLF001
            records,
            label="primitive prefix pool",
        )
        is records
    )

    wrong_order = copy.deepcopy(records)
    wrong_order[1]["appended_atom"] = _boolean_atom(True)
    wrong_order[2]["appended_atom"] = _boolean_atom(False)
    with pytest.raises(validator.MaximumProtocolValidationError):
        validator._validate_primitive_prefix_pool(  # noqa: SLF001
            wrong_order,
            label="primitive prefix order",
        )

    duplicate = copy.deepcopy(records)
    duplicate[2]["appended_atom"] = _boolean_atom(False)
    duplicate[2]["appended_choice_coordinate_plan_id"] = "3" * 64
    with pytest.raises(validator.MaximumProtocolValidationError):
        validator._validate_primitive_prefix_pool(  # noqa: SLF001
            duplicate,
            label="primitive prefix duplicate",
        )


def test_raw_lex_interval_zero_divergence_and_cost_classes(
    validator: ModuleType,
) -> None:
    interval = {
        "interval_position": 0,
        "ordered_interval_blocks": [
            {
                "block_position": 1,
                "block_kind": "HOMOGENEOUS_ANCESTOR_DIVERGENCE_RUN",
                "prefix_position": 0,
                "inclusive_next_scalar_minimum": None,
                "inclusive_next_scalar_maximum": None,
                "repeated_lower_bound_scalar": ord("a"),
                "minimum_retained_repeat_count": 0,
                "maximum_retained_repeat_count": 0,
            }
        ],
    }
    assert validator._validate_raw_lex_interval_pool(  # noqa: SLF001
        [interval],
        scalar_prefix_count=1,
        label="zero divergence interval",
    ) == [interval]

    positive_minimum = copy.deepcopy(interval)
    positive_minimum["ordered_interval_blocks"][0]["minimum_retained_repeat_count"] = 1
    positive_minimum["ordered_interval_blocks"][0]["maximum_retained_repeat_count"] = 1

    maximum_scalar = copy.deepcopy(interval)
    maximum_scalar["ordered_interval_blocks"][0]["repeated_lower_bound_scalar"] = (
        0x10FFFF
    )

    cost_crossing = _singleton_lex_interval()
    cost_block = cost_crossing["ordered_interval_blocks"][0]
    cost_block.update(
        {
            "block_kind": "NEXT_SCALAR_RANGE_SUBTREES",
            "inclusive_next_scalar_minimum": 0x21,
            "inclusive_next_scalar_maximum": 0x22,
        }
    )

    surrogate_crossing = copy.deepcopy(cost_crossing)
    surrogate_crossing["ordered_interval_blocks"][0].update(
        {
            "inclusive_next_scalar_minimum": 0xD7FF,
            "inclusive_next_scalar_maximum": 0xE000,
        }
    )

    for position, corrupt in enumerate(
        (positive_minimum, maximum_scalar, cost_crossing, surrogate_crossing),
        1,
    ):
        with pytest.raises(validator.MaximumProtocolValidationError):
            validator._validate_raw_lex_interval_pool(  # noqa: SLF001
                [corrupt],
                scalar_prefix_count=1,
                label=f"lex interval corruption {position}",
            )


def test_transient_recurrence_id_covers_every_preceding_root_member(
    validator: ModuleType,
) -> None:
    protocol_sha = "f" * 64
    catalog = _transient_recurrence_catalog(
        validator,
        kind="ORDERED_RAW_STRING_PREFIX_FEASIBILITY_V1",
        protocol_sha=protocol_sha,
    )
    original_id = catalog["recurrence_catalog_id"]
    catalog["recurrence_parameters"]["target_array_octets"] = 3
    with pytest.raises(validator.MaximumProtocolValidationError):
        validator._validate_transient_recurrence_catalog(  # noqa: SLF001
            catalog,
            maximum_protocol_sha256=protocol_sha,
            expected_catalog_id=original_id,
            allowed_prior_catalog_ids=frozenset(),
            label="stale recurrence catalog ID",
        )

    payload = {
        "maximum_protocol_sha256": protocol_sha,
        **{
            name: item
            for name, item in catalog.items()
            if name != "recurrence_catalog_id"
        },
    }
    refreshed_id = validator._semantic_id(  # noqa: SLF001
        validator.TRANSIENT_RECURRENCE_CATALOG_DOMAIN,
        payload,
    )
    catalog["recurrence_catalog_id"] = refreshed_id
    assert (
        validator._validate_transient_recurrence_catalog(  # noqa: SLF001
            catalog,
            maximum_protocol_sha256=protocol_sha,
            expected_catalog_id=refreshed_id,
            allowed_prior_catalog_ids=frozenset(),
            label="refreshed recurrence catalog ID",
        ).catalog
        is catalog
    )


def test_transient_recurrence_derivation_members_and_nullability(
    validator: ModuleType,
) -> None:
    recurrence_catalog = _transient_recurrence_catalog(
        validator,
        kind="ASCII_DFA_DYNAMIC_PROGRAM_V1",
        protocol_sha="a" * 64,
    )
    text_derivation = {
        "derivation_kind": "TEXT_LANGUAGE_FRONTIER",
        "text_language_id": "1" * 64,
        "language_kind": "ASCII_DFA",
        "text_solver_kind": "ASCII_DFA_DYNAMIC_PROGRAM",
        "unicode_version": None,
        "transient_recurrence_catalog": recurrence_catalog,
    }
    assert (
        validator._validate_derivation(  # noqa: SLF001
            text_derivation,
            node_kind="TEXT_LANGUAGE_FRONTIER",
            child_positions=[],
            node_position=1,
            label="ASCII recurrence derivation",
        )
        is text_derivation
    )

    absent_catalog = copy.deepcopy(text_derivation)
    absent_catalog["transient_recurrence_catalog"] = None
    with pytest.raises(validator.MaximumProtocolValidationError):
        validator._validate_derivation(  # noqa: SLF001
            absent_catalog,
            node_kind="TEXT_LANGUAGE_FRONTIER",
            child_positions=[],
            node_position=1,
            label="missing ASCII recurrence",
        )

    closed_form = copy.deepcopy(text_derivation)
    closed_form["text_solver_kind"] = "BUILTIN_CLOSED_FORM"
    closed_form["transient_recurrence_catalog"] = None
    validator._validate_derivation(  # noqa: SLF001
        closed_form,
        node_kind="TEXT_LANGUAGE_FRONTIER",
        child_positions=[],
        node_position=1,
        label="closed-form text derivation",
    )
    closed_form["transient_recurrence_catalog"] = recurrence_catalog
    with pytest.raises(validator.MaximumProtocolValidationError):
        validator._validate_derivation(  # noqa: SLF001
            closed_form,
            node_kind="TEXT_LANGUAGE_FRONTIER",
            child_positions=[],
            node_position=1,
            label="spurious closed-form recurrence",
        )

    maximum_slice = {
        "derivation_kind": "MAXIMUM_SLICE_EXACT_FRONTIER",
        "target_canonical_byte_length": 1,
        "ordered_exact_constraint_bindings": [],
        "ordered_exact_domain_reinstatement_node_positions": [],
        "ordered_choice_coordinate_plan_ids": [],
        "ordered_transient_recurrence_catalogs": [],
        "upper_frontier_child_position": 1,
    }
    validator._validate_derivation(  # noqa: SLF001
        maximum_slice,
        node_kind="MAXIMUM_SLICE_EXACT_FRONTIER",
        child_positions=[1],
        node_position=2,
        label="maximum-slice recurrence array",
    )

    prefix = {
        "derivation_kind": "LEXICOGRAPHIC_PREFIX_EXCLUSION",
        "target_canonical_byte_length": 1,
        "choice_scope": "MEASURED_RECORD",
        "choice_coordinate_plan_id": "2" * 64,
        "coordinate_activation": "INACTIVE",
        "fixed_prefix_coordinate_count": 1,
        "fixed_active_prefix_coordinate_count": 0,
        "selected_atom": _primitive_atom("INACTIVE"),
        "ordered_transient_recurrence_catalogs": [recurrence_catalog],
        "input_prefix_frontier_child_position": 1,
    }
    with pytest.raises(validator.MaximumProtocolValidationError):
        validator._validate_derivation(  # noqa: SLF001
            prefix,
            node_kind="LEXICOGRAPHIC_PREFIX_EXCLUSION",
            child_positions=[1],
            node_position=2,
            label="inactive recurrence rerun",
        )


def test_fixed_identity_mapping_catalog_root_and_preimages(
    validator: ModuleType,
) -> None:
    protocol_sha = "c" * 64
    semantic_domain = "ExampleSemanticIdentityDomainV1"
    records = []
    for value in (0, 1):
        preimage = _canonical(
            {
                "canonicalization_version": validator.CANONICALIZATION_VERSION,
                "domain": semantic_domain,
                "payload": {"value": value},
                "schema_version": validator.MEASUREMENT_SCHEMA_VERSION,
            }
        )
        identity = hashlib.sha256(preimage).hexdigest()
        records.append(
            {
                "semantic_identity_preimage_canonical_bytes_hex": preimage.hex(),
                "derived_identity_text": identity,
                "derived_identity_canonical_sha256": hashlib.sha256(
                    _canonical(identity)
                ).hexdigest(),
            }
        )
    catalog = {
        "catalog_version": (
            "riskyieldmm.raw_v8_step2_external_schema_v2."
            "derived_identity_mapping_catalog.v1"
        ),
        "defining_subject_locator": _schema_locator(),
        "semantic_identity_domain": semantic_domain,
        "ordered_mapping_records": records,
    }
    catalog_id = validator._semantic_id(  # noqa: SLF001
        validator.DERIVED_IDENTITY_MAPPING_CATALOG_DOMAIN,
        {"maximum_protocol_sha256": protocol_sha, **catalog},
    )
    meter = validator.ProofResourceMeter(phase=validator.SEED_CAP_DERIVATION_PHASE)
    evidence = validator._validate_derived_identity_mapping_catalog(  # noqa: SLF001
        catalog,
        maximum_protocol_sha256=protocol_sha,
        expected_catalog_id=catalog_id,
        label="derived identity mapping catalog",
        resource_meter=meter,
    )
    root_envelope = {
        "canonicalization_version": validator.CANONICALIZATION_VERSION,
        "domain": validator.DERIVED_IDENTITY_MAPPING_CATALOG_DOMAIN,
        "payload": {"maximum_protocol_sha256": protocol_sha, **catalog},
        "schema_version": validator.MEASUREMENT_SCHEMA_VERSION,
    }
    expected_hash_octets = len(_canonical(root_envelope)) + sum(
        len(bytes.fromhex(record["semantic_identity_preimage_canonical_bytes_hex"]))
        + len(_canonical(record["derived_identity_text"]))
        for record in records
    )
    assert evidence.catalog is catalog
    assert evidence.entry_count == 2
    assert evidence.complete_root_octets == len(_canonical(catalog))
    assert evidence.validation_hash_preimage_octets == expected_hash_octets
    assert evidence.referenced_prior_catalog_ids == ()

    malformed = copy.deepcopy(catalog)
    malformed["ordered_mapping_records"][0]["derived_identity_text"] = "f" * 64
    malformed_id = validator._semantic_id(  # noqa: SLF001
        validator.DERIVED_IDENTITY_MAPPING_CATALOG_DOMAIN,
        {"maximum_protocol_sha256": protocol_sha, **malformed},
    )
    with pytest.raises(validator.MaximumProtocolValidationError):
        validator._validate_derived_identity_mapping_catalog(  # noqa: SLF001
            malformed,
            maximum_protocol_sha256=protocol_sha,
            expected_catalog_id=malformed_id,
            label="malformed derived identity mapping catalog",
        )

    legacy = copy.deepcopy(catalog)
    legacy_preimage = _canonical({"domain": semantic_domain, "payload": {"value": 0}})
    legacy_identity = hashlib.sha256(legacy_preimage).hexdigest()
    legacy["ordered_mapping_records"][0] = {
        "semantic_identity_preimage_canonical_bytes_hex": legacy_preimage.hex(),
        "derived_identity_text": legacy_identity,
        "derived_identity_canonical_sha256": hashlib.sha256(
            _canonical(legacy_identity)
        ).hexdigest(),
    }
    legacy_id = validator._semantic_id(  # noqa: SLF001
        validator.DERIVED_IDENTITY_MAPPING_CATALOG_DOMAIN,
        {"maximum_protocol_sha256": protocol_sha, **legacy},
    )
    with pytest.raises(validator.MaximumProtocolValidationError):
        validator._validate_derived_identity_mapping_catalog(  # noqa: SLF001
            legacy,
            maximum_protocol_sha256=protocol_sha,
            expected_catalog_id=legacy_id,
            label="legacy two-member identity mapping envelope",
        )


def test_pilot_context_manifest_binds_materialized_max64_authority(
    validator: ModuleType,
    pinned_inventory_and_registry: tuple[dict[str, Any], dict[str, Any]],
    pinned_max64_context_authority: dict[str, Any],
) -> None:
    protocol_sha = "d" * 64
    inventory, registry = pinned_inventory_and_registry
    entries = [
        _max64_context_entry(
            validator,
            registry=registry,
            max64_context_authority=pinned_max64_context_authority,
            protocol_sha256=protocol_sha,
            role=role,
            ordinal=ordinal,
        )
        for role, ordinal in (
            ("ROOT_RECORD", None),
            ("OBSERVATION_RECORD", 0),
        )
    ]
    manifest = _pilot_context_manifest(
        validator,
        protocol_sha256=protocol_sha,
        entries=entries,
    )
    validated = validator._validate_pilot_context_manifest(  # noqa: SLF001
        manifest,
        maximum_protocol_sha256=protocol_sha,
        validated_inventory=inventory,
        validated_registry=registry,
        validated_max64_context_authority=pinned_max64_context_authority,
        label="pilot context manifest",
    )
    assert validated.manifest is manifest
    assert len(validated.resolved_entries) == 2
    for resolved in validated.resolved_entries:
        assert (
            resolved.maximum_context_object_id
            == resolved.entry["maximum_context_object_id"]
        )
        assert (
            resolved.validated_record.record_identity
            == resolved.entry["record_identity"]
        )
        assert (
            resolved.validated_record.record_canonical_byte_length
            == resolved.entry["record_canonical_byte_length"]
        )
        assert (
            resolved.validated_record.record_canonical_sha256
            == resolved.entry["record_canonical_sha256"]
        )

    selector = _max64_context_entry(
        validator,
        registry=registry,
        max64_context_authority=pinned_max64_context_authority,
        protocol_sha256=protocol_sha,
        role="SELECTOR_RECORD",
    )
    selector_manifest = _pilot_context_manifest(
        validator,
        protocol_sha256=protocol_sha,
        entries=[selector],
    )
    with pytest.raises(validator.MaximumProtocolValidationError):
        validator._validate_pilot_context_manifest(  # noqa: SLF001
            selector_manifest,
            maximum_protocol_sha256=protocol_sha,
            validated_inventory=inventory,
            validated_registry=registry,
            validated_max64_context_authority=pinned_max64_context_authority,
            label="orphan selector context entry",
        )


def test_registry_derives_all_canonical_self_reference_schema_anchors(
    validator: ModuleType,
    pinned_inventory_and_registry: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    _, registry = pinned_inventory_and_registry
    anchors = validator._derive_self_reference_value_schema_index(  # noqa: SLF001
        registry
    )
    assert len(anchors) == 52
    assert anchors["TargetObservationV2"]["value_schema_id"] == (
        "bc21fb81f6e70fc69662c3cd65134eb648126422f9edd26cfbc240e48c4ca041"
    )
    assert anchors["CheckpointSelectorV1"]["value_schema_id"] == (
        "e144a993ded9071ccdeaf74ed6a9f7523b1a04453ef851ba86e2cfff34da2a11"
    )
    assert {
        type_name: anchors[type_name]["value_schema_id"]
        for type_name in (
            "CapacityMeasurementBoolValueV1",
            "CapacityMeasurementIngressLogicalOracleProfileV1",
            "CapacityMeasurementIngressResultEvidenceV2",
            "CapacityMeasurementSubscriptionDispatchSpecV2",
            "CapacityMeasurementTextListValueV1",
            "CapacityMeasurementTextValueV1",
            "CapacityMeasurementUIntListValueV1",
            "CapacityMeasurementUIntValueV1",
        )
    } == {
        "CapacityMeasurementBoolValueV1": (
            "94d36a2fdc0a95f956471b9601870765edbff3aed9c286bcc601c19877906fd8"
        ),
        "CapacityMeasurementIngressLogicalOracleProfileV1": (
            "83ec20173bb2eb5277c982d066fad703fe58ff7dc2dfeb8c046fdfa7b0795f41"
        ),
        "CapacityMeasurementIngressResultEvidenceV2": (
            "da4431319bed9ecbfded1e86ae2a2fb503dcca904e08b39f46c799a3f9cd5278"
        ),
        "CapacityMeasurementSubscriptionDispatchSpecV2": (
            "fcbc334d5f8e8bbb85f3f5bd64fd3e65633ed53560f64a4e014f933bae19920c"
        ),
        "CapacityMeasurementTextListValueV1": (
            "0328a69a9b4b555ca37aa93efca14d18283947d88f126da2c71b352120f4aa71"
        ),
        "CapacityMeasurementTextValueV1": (
            "9c905a62072425cabd2eb858a3b1d190c2983a5ef5a61282f911fb89e71965eb"
        ),
        "CapacityMeasurementUIntListValueV1": (
            "b684c06287897668a2b8a4e435c93e39148ad1bed23cf63be7d82340da8b1450"
        ),
        "CapacityMeasurementUIntValueV1": (
            "0ad840b570dbf7d254499592e7575e321ce22730904f4c16708ea7f490f8f877"
        ),
    }


def test_identityless_witness_uses_reserved_canonical_sha_reference(
    validator: ModuleType,
    pinned_inventory_and_registry: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    _, registry = pinned_inventory_and_registry
    witness = {"kind": "BOOL", "value": False}
    meter = validator.ProofResourceMeter(phase=validator.SEED_CAP_DERIVATION_PHASE)
    validated = validator._validate_complete_pilot_witness_record(  # noqa: SLF001
        witness,
        expected_type_name="CapacityMeasurementBoolValueV1",
        expected_alternative_name=None,
        validated_registry=registry,
        label="identityless Boolean witness",
        resource_meter=meter,
    )
    canonical = _canonical(witness)
    canonical_sha256 = hashlib.sha256(canonical).hexdigest()
    assert validated.record_identity_field == "$canonical_sha256"
    assert validated.record_identity == canonical_sha256
    assert validated.record_canonical_sha256 == canonical_sha256

    witness_reference = {
        "reference_kind": "WITNESS_RECORD",
        "record_type_name": "CapacityMeasurementBoolValueV1",
        "record_identity_field": "$canonical_sha256",
        "record_identity": canonical_sha256,
        "record_canonical_byte_length": len(canonical),
        "record_canonical_sha256": canonical_sha256,
    }
    _refresh_record_reference_id(validator, witness_reference)
    assert (
        validator._validate_maximum_record_reference(  # noqa: SLF001
            witness_reference,
            expected_reference_kind="WITNESS_RECORD",
            expected_inventory_pointer=None,
            label="identityless witness reference",
        )
        is witness_reference
    )

    context_reference = {
        **witness_reference,
        "reference_kind": "CONTEXT_OBJECT",
        "maximum_context_object_id": "f" * 64,
    }
    _refresh_record_reference_id(validator, context_reference)
    with pytest.raises(validator.MaximumProtocolValidationError):
        validator._validate_maximum_record_reference(  # noqa: SLF001
            context_reference,
            expected_reference_kind="CONTEXT_OBJECT",
            expected_inventory_pointer=None,
            label="forbidden identityless context reference",
        )


@pytest.mark.parametrize(
    "corruption",
    ("pointer", "type", "identity", "length", "sha256", "context_object_id"),
)
def test_pilot_context_manifest_rejects_refreshed_resolved_entry_corruption(
    validator: ModuleType,
    pinned_inventory_and_registry: tuple[dict[str, Any], dict[str, Any]],
    pinned_max64_context_authority: dict[str, Any],
    corruption: str,
) -> None:
    protocol_sha = "d" * 64
    inventory, registry = pinned_inventory_and_registry
    entry = _max64_context_entry(
        validator,
        registry=registry,
        max64_context_authority=pinned_max64_context_authority,
        protocol_sha256=protocol_sha,
        role="ROOT_RECORD",
    )
    if corruption == "pointer":
        entry["source_json_pointer"] = "/selector"
    elif corruption == "type":
        entry["record_type_name"] = "TargetObservationV2"
    elif corruption == "identity":
        entry["record_identity"] = "0" * 64
    elif corruption == "length":
        entry["record_canonical_byte_length"] += 1
    elif corruption == "sha256":
        entry["record_canonical_sha256"] = "0" * 64
    else:
        assert corruption == "context_object_id"
        entry["maximum_context_object_id"] = "0" * 64
    if corruption not in {"pointer", "context_object_id"}:
        _refresh_context_object_id_from_claim(
            validator,
            entry,
            protocol_sha256=protocol_sha,
            max64_context_authority=pinned_max64_context_authority,
        )
    manifest = _pilot_context_manifest(
        validator,
        protocol_sha256=protocol_sha,
        entries=[entry],
    )
    with pytest.raises(validator.MaximumProtocolValidationError):
        validator._validate_pilot_context_manifest(  # noqa: SLF001
            manifest,
            maximum_protocol_sha256=protocol_sha,
            validated_inventory=inventory,
            validated_registry=registry,
            validated_max64_context_authority=pinned_max64_context_authority,
            label=f"pilot context manifest with wrong {corruption}",
        )


def test_pilot_context_manifest_rejects_duplicate_orphan_and_noncanonical_order(
    validator: ModuleType,
    pinned_inventory_and_registry: tuple[dict[str, Any], dict[str, Any]],
    pinned_max64_context_authority: dict[str, Any],
) -> None:
    protocol_sha = "d" * 64
    inventory, registry = pinned_inventory_and_registry
    root_pointer = _max64_context_entry(
        validator,
        registry=registry,
        max64_context_authority=pinned_max64_context_authority,
        protocol_sha256=protocol_sha,
        role="ROOT_RECORD",
    )
    root_inline = _max64_context_entry(
        validator,
        registry=registry,
        max64_context_authority=pinned_max64_context_authority,
        protocol_sha256=protocol_sha,
        role="ROOT_RECORD",
        inline=True,
    )
    duplicate = _pilot_context_manifest(
        validator,
        protocol_sha256=protocol_sha,
        entries=[root_inline, root_pointer],
    )
    with pytest.raises(validator.MaximumProtocolValidationError):
        validator._validate_pilot_context_manifest(  # noqa: SLF001
            duplicate,
            maximum_protocol_sha256=protocol_sha,
            validated_inventory=inventory,
            validated_registry=registry,
            validated_max64_context_authority=pinned_max64_context_authority,
            label="duplicate resolved context object",
        )

    observation = _max64_context_entry(
        validator,
        registry=registry,
        max64_context_authority=pinned_max64_context_authority,
        protocol_sha256=protocol_sha,
        role="OBSERVATION_RECORD",
        ordinal=0,
    )
    valid_two = _pilot_context_manifest(
        validator,
        protocol_sha256=protocol_sha,
        entries=[root_pointer, observation],
    )
    orphan_position = copy.deepcopy(valid_two)
    orphan_position["ordered_context_object_entries"][1]["context_object_position"] = 3
    _refresh_context_manifest_id(validator, orphan_position)
    with pytest.raises(validator.MaximumProtocolValidationError):
        validator._validate_pilot_context_manifest(  # noqa: SLF001
            orphan_position,
            maximum_protocol_sha256=protocol_sha,
            validated_inventory=inventory,
            validated_registry=registry,
            validated_max64_context_authority=pinned_max64_context_authority,
            label="orphaned context entry position",
        )

    noncanonical_order = copy.deepcopy(valid_two)
    noncanonical_order["ordered_context_object_entries"].reverse()
    for position, item in enumerate(
        noncanonical_order["ordered_context_object_entries"],
        1,
    ):
        item["context_object_position"] = position
    _refresh_context_manifest_id(validator, noncanonical_order)
    with pytest.raises(validator.MaximumProtocolValidationError):
        validator._validate_pilot_context_manifest(  # noqa: SLF001
            noncanonical_order,
            maximum_protocol_sha256=protocol_sha,
            validated_inventory=inventory,
            validated_registry=registry,
            validated_max64_context_authority=pinned_max64_context_authority,
            label="noncanonical context entry order",
        )


def _leaf_arguments(
    validator: ModuleType,
    *,
    protocol_sha256: str,
    inventory: dict[str, Any],
    registry: dict[str, Any],
    max64_context_authority: dict[str, Any],
) -> dict[str, Any]:
    return {
        "maximum_protocol_sha256": protocol_sha256,
        "validated_inventory": inventory,
        "validated_registry": registry,
        "validated_max64_context_authority": max64_context_authority,
        "resource_meter": validator.ProofResourceMeter(
            phase=validator.SEED_CAP_DERIVATION_PHASE
        ),
    }


def test_pilot_leaf_self_value_and_owner_member_close_exact_context(
    validator: ModuleType,
    pinned_inventory_and_registry: tuple[dict[str, Any], dict[str, Any]],
    pinned_max64_context_authority: dict[str, Any],
) -> None:
    protocol_sha = "e" * 64
    inventory, registry = pinned_inventory_and_registry
    common = _leaf_arguments(
        validator,
        protocol_sha256=protocol_sha,
        inventory=inventory,
        registry=registry,
        max64_context_authority=pinned_max64_context_authority,
    )
    empty_manifest = _pilot_context_manifest(
        validator,
        protocol_sha256=protocol_sha,
        entries=[],
    )
    self_leaf = validator._validate_pilot_retained_leaf(  # noqa: SLF001
        pilot_context_manifest=empty_manifest,
        pilot_witness_record={"kind": "BOOL", "value": False},
        pilot_scope_witness_context={"context_kind": "SELF_VALUE"},
        expected_type_name="CapacityMeasurementTargetValue",
        expected_alternative_name="BOOL",
        expected_constraint_scope="INTRINSIC_TYPE",
        expected_measurement_binding=validator._measurement_binding(  # noqa: SLF001
            "SELF_UNION_VALUE",
            "CapacityMeasurementTargetValue",
        ),
        expected_profile=None,
        label="self-value pilot leaf",
        **common,
    )
    assert self_leaf.resolved_context_reference_count == 0
    assert self_leaf.resolved_context_object_octets == 0
    assert self_leaf.maximum_context_object_octets == 0
    assert self_leaf.observation_count == 0
    assert self_leaf.application_invocation_count == 0

    leaf_certificate = {"certificate": "retained"}
    expected_resources = validator._derive_pilot_leaf_nonproof_resources(  # noqa: SLF001
        self_leaf,
        case_binding={
            "type_name": "CapacityMeasurementTargetValue",
            "alternative_name": "BOOL",
            "constraint_scope": "INTRINSIC_TYPE",
            "constraint_scope_profile_id": None,
            "profile_position": None,
            "measurement_binding": validator._measurement_binding(  # noqa: SLF001
                "SELF_UNION_VALUE",
                "CapacityMeasurementTargetValue",
            ),
            "pilot_domain_kind": "FULL_INTRINSIC_TYPE",
        },
        ordered_component_choice_evidence=[],
        certificate=leaf_certificate,
        label="self-value resource projection",
    )
    measurement = dict.fromkeys(validator.PROOF_RESOURCE_KEYS, 0)
    measurement.update(expected_resources)
    assert (
        validator._validate_producer_resource_measurement(  # noqa: SLF001
            measurement,
            certificate=None,
            expected_leaf_resources=expected_resources,
            label="self-value resource measurement",
        )
        is measurement
    )
    corrupt_measurement = dict(measurement)
    corrupt_measurement["row_pretty_octets"] += 1
    with pytest.raises(
        validator.MaximumProtocolValidationError,
        match="row_pretty_octets differs from the retained leaf",
    ):
        validator._validate_producer_resource_measurement(  # noqa: SLF001
            corrupt_measurement,
            certificate=None,
            expected_leaf_resources=expected_resources,
            label="corrupt self-value resource measurement",
        )

    owner_record = inventory["fixture_records"]["operation_results"]["LOCAL_SHUTDOWN"]
    witness_record = owner_record["result"]
    owner_entry = _inline_context_entry(
        validator,
        record=owner_record,
        record_type_name="CapacityMeasurementOperationResultEvidence",
        record_identity_field="result_evidence_id",
        protocol_sha256=protocol_sha,
    )
    owner_manifest = _pilot_context_manifest(
        validator,
        protocol_sha256=protocol_sha,
        entries=[owner_entry],
    )
    owner_reference = _identified_record_reference(
        validator,
        record=owner_record,
        record_type_name="CapacityMeasurementOperationResultEvidence",
        record_identity_field="result_evidence_id",
        reference_kind="CONTEXT_OBJECT",
        maximum_context_object_id=owner_entry["maximum_context_object_id"],
    )
    owner_context = {
        "context_kind": "OWNER_MEMBER",
        "owner_record_reference": owner_reference,
        "payload_typed_member_path": ["result"],
    }
    owner_leaf = validator._validate_pilot_retained_leaf(  # noqa: SLF001
        pilot_context_manifest=owner_manifest,
        pilot_witness_record=witness_record,
        pilot_scope_witness_context=owner_context,
        expected_type_name="CapacityMeasurementOperationResultBody",
        expected_alternative_name="LOCAL_SHUTDOWN_RESULT_EVIDENCE_V2",
        expected_constraint_scope="INTRINSIC_TYPE",
        expected_measurement_binding=validator._measurement_binding(  # noqa: SLF001
            "OWNER_MEMBER_UNION_VALUE",
            "CapacityMeasurementOperationResultEvidence",
            path=["result"],
        ),
        expected_profile=None,
        label="owner-member pilot leaf",
        **_leaf_arguments(
            validator,
            protocol_sha256=protocol_sha,
            inventory=inventory,
            registry=registry,
            max64_context_authority=pinned_max64_context_authority,
        ),
    )
    assert owner_leaf.resolved_context_object_ids == frozenset(
        {owner_entry["maximum_context_object_id"]}
    )
    assert owner_leaf.resolved_context_object_octets == len(_canonical(owner_record))
    assert owner_leaf.maximum_context_object_octets == len(_canonical(owner_record))

    corrupted = copy.deepcopy(owner_context)
    corrupted["owner_record_reference"]["record_canonical_sha256"] = "0" * 64
    _refresh_record_reference_id(
        validator,
        corrupted["owner_record_reference"],
    )
    with pytest.raises(validator.MaximumProtocolValidationError):
        validator._validate_pilot_retained_leaf(  # noqa: SLF001
            pilot_context_manifest=owner_manifest,
            pilot_witness_record=witness_record,
            pilot_scope_witness_context=corrupted,
            expected_type_name="CapacityMeasurementOperationResultBody",
            expected_alternative_name="LOCAL_SHUTDOWN_RESULT_EVIDENCE_V2",
            expected_constraint_scope="INTRINSIC_TYPE",
            expected_measurement_binding=validator._measurement_binding(  # noqa: SLF001
                "OWNER_MEMBER_UNION_VALUE",
                "CapacityMeasurementOperationResultEvidence",
                path=["result"],
            ),
            expected_profile=None,
            label="refreshed corrupt owner-member pilot leaf",
            **_leaf_arguments(
                validator,
                protocol_sha256=protocol_sha,
                inventory=inventory,
                registry=registry,
                max64_context_authority=pinned_max64_context_authority,
            ),
        )


def test_pilot_leaf_outer_result_resolves_witness_and_profile_authority(
    validator: ModuleType,
    pinned_inventory_and_registry: tuple[dict[str, Any], dict[str, Any]],
    pinned_max64_context_authority: dict[str, Any],
) -> None:
    protocol_sha = "f" * 64
    inventory, registry = pinned_inventory_and_registry
    profile = inventory["operation_contracts"][
        "maximum_constraint_scope_profile_catalog"
    ][2]
    witness = inventory["fixture_records"]["operation_results"]["LOCAL_SHUTDOWN"]
    witness_reference = _identified_record_reference(
        validator,
        record=witness,
        record_type_name="CapacityMeasurementOperationResultEvidence",
        record_identity_field="result_evidence_id",
        reference_kind="WITNESS_RECORD",
    )
    spec_reference = _v3_record_reference(
        validator,
        inventory=inventory,
        pointer="/fixture_records/operation_specs/LOCAL_SHUTDOWN",
        record_type_name="CapacityMeasurementOperationSpec",
        record_identity_field="operation_spec_id",
    )
    context = {
        "context_kind": "OUTER_RESULT_APPLICATION",
        "constraint_scope_profile_id": profile["maximum_constraint_scope_profile_id"],
        "operation_result_record_reference": witness_reference,
        "operation_spec_authority_reference": spec_reference,
        "ordered_application_invocations": (
            validator._derive_profile_application_invocations(  # noqa: SLF001
                profile,
                selected_root_family=None,
                label="outer schedule fixture",
            )
        ),
    }
    leaf = validator._validate_pilot_retained_leaf(  # noqa: SLF001
        pilot_context_manifest=_pilot_context_manifest(
            validator,
            protocol_sha256=protocol_sha,
            entries=[],
        ),
        pilot_witness_record=witness,
        pilot_scope_witness_context=context,
        expected_type_name="CapacityMeasurementOperationResultEvidence",
        expected_alternative_name=None,
        expected_constraint_scope="FROZEN_FIXTURE",
        expected_measurement_binding=validator._measurement_binding(  # noqa: SLF001
            "OUTER_RESULT_RECORD",
            "CapacityMeasurementOperationResultEvidence",
        ),
        expected_profile=profile,
        label="outer-result pilot leaf",
        **_leaf_arguments(
            validator,
            protocol_sha256=protocol_sha,
            inventory=inventory,
            registry=registry,
            max64_context_authority=pinned_max64_context_authority,
        ),
    )
    assert leaf.resolved_context_reference_count == 0
    assert leaf.observation_count == 0
    assert leaf.application_invocation_count == 1
    assert leaf.charged_cross_rule_evaluation_count == 1
    assert leaf.direct_cross_expression_node_count == 3

    corrupted = copy.deepcopy(context)
    corrupted["operation_spec_authority_reference"]["record_identity"] = "0" * 64
    _refresh_record_reference_id(
        validator,
        corrupted["operation_spec_authority_reference"],
    )
    with pytest.raises(validator.MaximumProtocolValidationError):
        validator._validate_pilot_retained_leaf(  # noqa: SLF001
            pilot_context_manifest=_pilot_context_manifest(
                validator,
                protocol_sha256=protocol_sha,
                entries=[],
            ),
            pilot_witness_record=witness,
            pilot_scope_witness_context=corrupted,
            expected_type_name="CapacityMeasurementOperationResultEvidence",
            expected_alternative_name=None,
            expected_constraint_scope="FROZEN_FIXTURE",
            expected_measurement_binding=validator._measurement_binding(  # noqa: SLF001
                "OUTER_RESULT_RECORD",
                "CapacityMeasurementOperationResultEvidence",
            ),
            expected_profile=profile,
            label="refreshed corrupt outer-result pilot leaf",
            **_leaf_arguments(
                validator,
                protocol_sha256=protocol_sha,
                inventory=inventory,
                registry=registry,
                max64_context_authority=pinned_max64_context_authority,
            ),
        )


def test_pilot_leaf_root_application_closes_full67_reference_order(
    validator: ModuleType,
    pinned_inventory_and_registry: tuple[dict[str, Any], dict[str, Any]],
    pinned_max64_context_authority: dict[str, Any],
) -> None:
    protocol_sha = "1" * 64
    inventory, registry = pinned_inventory_and_registry
    profile = inventory["operation_contracts"][
        "maximum_constraint_scope_profile_catalog"
    ][368]
    measured_ordinal = 64
    root_entry = _max64_context_entry(
        validator,
        registry=registry,
        max64_context_authority=pinned_max64_context_authority,
        protocol_sha256=protocol_sha,
        role="ROOT_RECORD",
        inline=True,
    )
    observation_entries = [
        _max64_context_entry(
            validator,
            registry=registry,
            max64_context_authority=pinned_max64_context_authority,
            protocol_sha256=protocol_sha,
            role="OBSERVATION_RECORD",
            ordinal=ordinal,
        )
        for ordinal in range(67)
        if ordinal != measured_ordinal
    ]
    manifest_value = _pilot_context_manifest(
        validator,
        protocol_sha256=protocol_sha,
        entries=[root_entry, *observation_entries],
    )
    entries_by_ordinal = {
        entry["derived_sequence_ordinal"]: entry
        for entry in manifest_value["ordered_context_object_entries"]
        if entry["derived_record_role"] == "OBSERVATION_RECORD"
    }
    root_manifest_entry = next(
        entry
        for entry in manifest_value["ordered_context_object_entries"]
        if entry["record_type_name"] == "TargetObservationRootV2"
    )
    root_record = pinned_max64_context_authority["root"]
    witness = pinned_max64_context_authority["observations"][measured_ordinal]
    observation_references = []
    for ordinal, observation in enumerate(
        pinned_max64_context_authority["observations"]
    ):
        if ordinal == measured_ordinal:
            reference = _identified_record_reference(
                validator,
                record=observation,
                record_type_name="TargetObservationV2",
                record_identity_field="observation_id",
                reference_kind="WITNESS_RECORD",
            )
        else:
            entry = entries_by_ordinal[ordinal]
            reference = _identified_record_reference(
                validator,
                record=observation,
                record_type_name="TargetObservationV2",
                record_identity_field="observation_id",
                reference_kind="CONTEXT_OBJECT",
                maximum_context_object_id=entry["maximum_context_object_id"],
            )
        observation_references.append(reference)
    family = profile["ordered_admissible_root_families"][0]
    context = {
        "context_kind": "ROOT_APPLICATION",
        "constraint_scope_profile_id": profile["maximum_constraint_scope_profile_id"],
        "selected_root_family_position": 1,
        "measured_sequence_ordinal": measured_ordinal,
        "root_record_reference": _identified_record_reference(
            validator,
            record=root_record,
            record_type_name="TargetObservationRootV2",
            record_identity_field="target_observation_root_sha256",
            reference_kind="CONTEXT_OBJECT",
            maximum_context_object_id=root_manifest_entry["maximum_context_object_id"],
        ),
        "selector_authority_reference": _v3_record_reference(
            validator,
            inventory=inventory,
            pointer="/checkpoint_selector_catalog/3/selector",
            record_type_name="CheckpointSelectorV1",
            record_identity_field="checkpoint_selector_id",
        ),
        "target_field_registry_authority_reference": _v3_record_reference(
            validator,
            inventory=inventory,
            pointer="/target_field_registry",
            record_type_name="TargetFieldRegistryV1",
            record_identity_field="target_field_registry_id",
        ),
        "marker_contract_authority_reference": _v3_record_reference(
            validator,
            inventory=inventory,
            pointer="/marker_contract",
            record_type_name="MarkerContractV1",
            record_identity_field="marker_contract_id",
        ),
        "ordered_observation_record_references": observation_references,
        "ordered_application_invocations": (
            validator._derive_profile_application_invocations(  # noqa: SLF001
                profile,
                selected_root_family=family,
                label="full67 schedule fixture",
            )
        ),
    }
    leaf = validator._validate_pilot_retained_leaf(  # noqa: SLF001
        pilot_context_manifest=manifest_value,
        pilot_witness_record=witness,
        pilot_scope_witness_context=context,
        expected_type_name="TargetObservationV2",
        expected_alternative_name=None,
        expected_constraint_scope="FROZEN_ROOT_APPLICATION",
        expected_measurement_binding=validator._measurement_binding(  # noqa: SLF001
            "ROOT_EXACT_CHECKPOINT_OBSERVATION",
            "TargetObservationRootV2",
            sequence_name="observations",
            sequence_ordinal=measured_ordinal,
        ),
        expected_profile=profile,
        label="full67 root pilot leaf",
        **_leaf_arguments(
            validator,
            protocol_sha256=protocol_sha,
            inventory=inventory,
            registry=registry,
            max64_context_authority=pinned_max64_context_authority,
        ),
    )
    assert leaf.resolved_context_reference_count == 67
    assert len(leaf.resolved_context_object_ids) == 67
    assert leaf.observation_count == 67
    assert leaf.application_invocation_count == 137
    assert leaf.charged_cross_rule_evaluation_count == 12_531
    assert leaf.direct_cross_expression_node_count == 125_431

    reordered = copy.deepcopy(context)
    reordered["ordered_observation_record_references"][0:2] = reversed(
        reordered["ordered_observation_record_references"][0:2]
    )
    with pytest.raises(validator.MaximumProtocolValidationError):
        validator._validate_pilot_retained_leaf(  # noqa: SLF001
            pilot_context_manifest=manifest_value,
            pilot_witness_record=witness,
            pilot_scope_witness_context=reordered,
            expected_type_name="TargetObservationV2",
            expected_alternative_name=None,
            expected_constraint_scope="FROZEN_ROOT_APPLICATION",
            expected_measurement_binding=validator._measurement_binding(  # noqa: SLF001
                "ROOT_EXACT_CHECKPOINT_OBSERVATION",
                "TargetObservationRootV2",
                sequence_name="observations",
                sequence_ordinal=measured_ordinal,
            ),
            expected_profile=profile,
            label="reordered full67 root pilot leaf",
            **_leaf_arguments(
                validator,
                protocol_sha256=protocol_sha,
                inventory=inventory,
                registry=registry,
                max64_context_authority=pinned_max64_context_authority,
            ),
        )


def test_local_boundary_witness_binds_its_prospective_codec_root(
    validator: ModuleType,
) -> None:
    protocol_sha = "e" * 64
    prospective_result = {"candidate": "retained"}
    prospective_raw = _canonical(prospective_result)
    witness = {
        "boundary_witness_position": 1,
        "boundary_candidate_root_position": 7,
        "candidate_mutated_spec": {"spec": "complete"},
        "prospective_scope_witness_context": {"context": "complete"},
        "prospective_result": prospective_result,
        "ordered_component_choice_evidence": [],
        "prospective_result_canonical_byte_length": len(prospective_raw),
        "prospective_result_canonical_sha256": hashlib.sha256(
            prospective_raw
        ).hexdigest(),
    }
    witness["boundary_candidate_witness_id"] = validator._semantic_id(  # noqa: SLF001
        validator.BOUNDARY_CANDIDATE_WITNESS_DOMAIN,
        {"maximum_protocol_sha256": protocol_sha, **witness},
    )
    boundary_root = {
        "proof_node_kind": "CODEC_INTERSECTION_ATTAINMENT",
        "derivation": {
            "attainment_mode": ("PROSPECTIVE_BYTE_MAXIMUM_WITH_ONE_MASKED_OUTER_CODEC"),
            "attaining_witness_canonical_byte_length": len(prospective_raw),
            "attaining_witness_canonical_sha256": hashlib.sha256(
                prospective_raw
            ).hexdigest(),
        },
    }
    meter = validator.ProofResourceMeter(phase=validator.SEED_CAP_DERIVATION_PHASE)
    validator._validate_boundary_candidate_witness_binding(  # noqa: SLF001
        witness,
        boundary_root=boundary_root,
        maximum_protocol_sha256=protocol_sha,
        label="boundary witness",
        resource_meter=meter,
    )
    witness_identity_envelope = {
        "canonicalization_version": validator.CANONICALIZATION_VERSION,
        "domain": validator.BOUNDARY_CANDIDATE_WITNESS_DOMAIN,
        "payload": {
            "maximum_protocol_sha256": protocol_sha,
            **{
                name: item
                for name, item in witness.items()
                if name != "boundary_candidate_witness_id"
            },
        },
        "schema_version": validator.MEASUREMENT_SCHEMA_VERSION,
    }
    assert meter.value("hash_preimage_octets") == (
        2 * len(prospective_raw) + len(_canonical(witness_identity_envelope))
    )

    wrong_root = copy.deepcopy(boundary_root)
    wrong_root["derivation"]["attainment_mode"] = "BYTE_MAXIMUM"
    with pytest.raises(validator.MaximumProtocolValidationError):
        validator._validate_boundary_candidate_witness_binding(  # noqa: SLF001
            witness,
            boundary_root=wrong_root,
            maximum_protocol_sha256=protocol_sha,
            label="non-prospective boundary witness",
        )


def test_acceptance_authority_23_patch_shape_is_isolated_and_fail_closed(
    validator: ModuleType,
) -> None:
    candidate = bytearray(
        b"Status: **CANDIDATE \xe2\x80\x94 PILOT AND INDEPENDENT VERIFIER "
        b"ACCEPTANCE PENDING**  "
    )
    final = bytearray(
        b"Status: **FROZEN GO \xe2\x80\x94 PILOT AND INDEPENDENT VERIFIER ACCEPTED**  "
    )
    patches = [
        {
            "patch_position": 1,
            "patch_kind": "STATUS_LINE",
            "candidate_start_octet": 0,
            "candidate_end_octet_exclusive": len(candidate),
            "candidate_bytes_hex": bytes(candidate).hex(),
            "final_bytes_hex": bytes(final).hex(),
        }
    ]
    for resource_position in range(1, 23):
        separator = f"\nRESOURCE_{resource_position}: ".encode()
        candidate.extend(separator)
        final.extend(separator)
        start = len(candidate)
        candidate.extend(b"PILOT_PENDING")
        replacement = str(resource_position).encode()
        final.extend(replacement)
        patches.append(
            {
                "patch_position": resource_position + 1,
                "patch_kind": "ACCEPTED_CEILING_CELL",
                "candidate_start_octet": start,
                "candidate_end_octet_exclusive": start + len(b"PILOT_PENDING"),
                "candidate_bytes_hex": b"PILOT_PENDING".hex(),
                "final_bytes_hex": replacement.hex(),
            }
        )
    candidate_raw = bytes(candidate)
    final_raw = bytes(final)
    authority = {
        "artifact_version": (
            "riskyieldmm.raw_v8_step2_external_schema_v2.maximum_protocol_acceptance.v1"
        ),
        "candidate_protocol_raw_octet_count": len(candidate_raw),
        "candidate_protocol_sha256": hashlib.sha256(candidate_raw).hexdigest(),
        "final_protocol_raw_octet_count": len(final_raw),
        "final_protocol_sha256": hashlib.sha256(final_raw).hexdigest(),
        "ordered_protocol_rebind_patch_records": patches,
        "seed_pilot_raw_octet_count": 1,
        "seed_pilot_raw_sha256": "1" * 64,
        "final_pilot_raw_octet_count": 1,
        "final_pilot_raw_sha256": "2" * 64,
        "independent_validator_raw_octet_count": 1,
        "independent_validator_raw_sha256": "3" * 64,
        "focused_test_raw_octet_count": 1,
        "focused_test_raw_sha256": "4" * 64,
        "acceptance_decision": "GO",
    }
    authority["maximum_protocol_acceptance_id"] = validator._semantic_id(  # noqa: SLF001
        validator.ACCEPTANCE_AUTHORITY_DOMAIN,
        authority,
    )
    assert (
        validator._validate_acceptance_authority_shape(  # noqa: SLF001
            authority,
            candidate_protocol_raw=candidate_raw,
            final_protocol_raw=final_raw,
            label="isolated acceptance shape",
        )
        is authority
    )

    wrong_patch_count = copy.deepcopy(authority)
    wrong_patch_count["ordered_protocol_rebind_patch_records"].pop()
    with pytest.raises(validator.MaximumProtocolValidationError):
        validator._validate_acceptance_authority_shape(  # noqa: SLF001
            wrong_patch_count,
            candidate_protocol_raw=candidate_raw,
            final_protocol_raw=final_raw,
            label="incomplete acceptance shape",
        )


def test_all_resource_metrics_and_claim_fields_are_closed(
    validator: ModuleType,
) -> None:
    assert len(validator.METRIC_NAMES) == 22
    assert set(validator.RESOURCE_METRIC_FIELD) == set(validator.METRIC_NAMES)
    assert len(validator.PROOF_RESOURCE_KEYS) == 19
    assert {
        validator.RESOURCE_METRIC_FIELD[name] for name in validator.METRIC_NAMES[:18]
    }.issubset(validator.PROOF_RESOURCE_KEYS)
    assert {
        "state_catalog_entry_count",
        "state_catalog_canonicalized_octets",
        "peak_retained_state_catalog_octets",
    }.issubset(validator.PROOF_RESOURCE_KEYS)
    assert "measured_pilot_maximum" in validator.ROUNDING_KEYS
    assert "proved_global_upper_bound" not in validator.ROUNDING_KEYS
    assert {
        "coordinate_activation",
        "fixed_prefix_coordinate_count",
        "fixed_active_prefix_coordinate_count",
        "ordered_transient_recurrence_catalogs",
        "input_prefix_frontier_child_position",
    }.issubset(validator.DERIVATION_KEYS["LEXICOGRAPHIC_PREFIX_EXCLUSION"])
    assert (
        "transient_recurrence_catalog"
        in validator.DERIVATION_KEYS["TEXT_LANGUAGE_FRONTIER"]
    )
    assert (
        "ordered_boundary_candidate_witness_records"
        in validator.DERIVATION_KEYS["LOCAL_SHUTDOWN_MINIMALITY_FRONTIER"]
    )
    assert validator.DERIVATION_KEYS["MAXIMUM_SLICE_EXACT_FRONTIER"] == {
        "derivation_kind",
        "target_canonical_byte_length",
        "ordered_exact_constraint_bindings",
        "ordered_exact_domain_reinstatement_node_positions",
        "ordered_choice_coordinate_plan_ids",
        "ordered_transient_recurrence_catalogs",
        "upper_frontier_child_position",
    }
    assert validator.MAX64_CONTEXT_AUTHORITY_ROOT_KEYS == {
        "observations",
        "root",
        "selector",
    }


def test_seed_execution_safety_limits_are_exact_and_immutable(
    validator: ModuleType,
) -> None:
    expected = {
        "proof_node_count": 65_536,
        "proof_edge_count": 1_048_576,
        "maximum_proof_depth": 65_536,
        "maximum_child_count": 65_535,
        "state_signature_dimension_count": 4_194_304,
        "maximum_state_signature_dimension_count": 64,
        "state_catalog_entry_count": 1_048_576,
        "state_catalog_canonicalized_octets": 16_773_120,
        "peak_retained_state_catalog_octets": 16_773_120,
        "frontier_state_entry_count": 1_048_576,
        "frontier_bitmap_run_count": 1_048_576,
        "frontier_expanded_point_count": 8_388_608,
        "maximum_frontier_width": 8_388_608,
        "peak_retained_frontier_octets": 16_773_120,
        "frontier_transition_count": 67_108_864,
        "frontier_canonicalized_octets": 536_870_912,
        "hash_preimage_octets": 536_870_912,
        "component_choice_coordinate_count": 65_536,
        "certificate_canonical_octets": 16_773_120,
    }
    assert dict(validator.SEED_EXECUTION_SAFETY_LIMITS_V1) == expected
    assert set(expected) == validator.PROOF_RESOURCE_KEYS
    assert (
        validator.PROOF_RESOURCE_TOTAL_FIELDS | validator.PROOF_RESOURCE_MAXIMUM_FIELDS
        == validator.PROOF_RESOURCE_KEYS
    )
    assert not (
        validator.PROOF_RESOURCE_TOTAL_FIELDS & validator.PROOF_RESOURCE_MAXIMUM_FIELDS
    )
    with pytest.raises(TypeError):
        validator.SEED_EXECUTION_SAFETY_LIMITS_V1["proof_node_count"] = 1


@pytest.mark.parametrize(
    "field",
    sorted(
        {
            "proof_node_count",
            "proof_edge_count",
            "maximum_proof_depth",
            "maximum_child_count",
            "state_signature_dimension_count",
            "maximum_state_signature_dimension_count",
            "state_catalog_entry_count",
            "state_catalog_canonicalized_octets",
            "peak_retained_state_catalog_octets",
            "frontier_state_entry_count",
            "frontier_bitmap_run_count",
            "frontier_expanded_point_count",
            "maximum_frontier_width",
            "peak_retained_frontier_octets",
            "frontier_transition_count",
            "frontier_canonicalized_octets",
            "hash_preimage_octets",
            "component_choice_coordinate_count",
            "certificate_canonical_octets",
        }
    ),
)
def test_proof_resource_meter_accepts_exact_cap_and_rejects_cap_plus_one_atomically(
    validator: ModuleType,
    field: str,
) -> None:
    limit = validator.SEED_EXECUTION_SAFETY_LIMITS_V1[field]
    exact = validator.ProofResourceMeter(phase=validator.SEED_CAP_DERIVATION_PHASE)
    excessive = validator.ProofResourceMeter(phase=validator.SEED_CAP_DERIVATION_PHASE)
    if field in validator.PROOF_RESOURCE_MAXIMUM_FIELDS:
        exact.observe_maximum(field, limit)
        with pytest.raises(validator.MaximumProtocolValidationError):
            excessive.observe_maximum(field, limit + 1)
    else:
        exact.add(field, limit)
        with pytest.raises(validator.MaximumProtocolValidationError):
            excessive.add(field, limit + 1)
    assert exact.value(field) == limit
    assert excessive.value(field) == 0


def test_phase_limit_selection_rejects_circular_or_weaker_final_limits(
    validator: ModuleType,
) -> None:
    accepted_seed_bounds = {
        name: validator.SEED_EXECUTION_SAFETY_LIMITS_V1[name]
        for name in validator.ACCEPTED_PROOF_RESOURCE_LIMIT_KEYS
    }
    with pytest.raises(validator.MaximumProtocolValidationError):
        validator.ProofResourceMeter(
            phase=validator.SEED_CAP_DERIVATION_PHASE,
            accepted_limits=accepted_seed_bounds,
        )
    with pytest.raises(validator.MaximumProtocolValidationError):
        validator.ProofResourceMeter(
            phase=validator.FINAL_PROTOCOL_REBIND_PHASE,
        )
    weaker = dict(accepted_seed_bounds)
    weaker["proof_node_count"] += 1
    with pytest.raises(validator.MaximumProtocolValidationError):
        validator.ProofResourceMeter(
            phase=validator.PRODUCTION_VALIDATION_PHASE,
            accepted_limits=weaker,
        )
    accepted = dict(accepted_seed_bounds)
    accepted["proof_node_count"] -= 1
    meter = validator.ProofResourceMeter(
        phase=validator.FINAL_PROTOCOL_REBIND_PHASE,
        accepted_limits=accepted,
    )
    assert meter.limits == {
        **accepted,
        "state_signature_dimension_count": (
            accepted["proof_node_count"]
            * accepted["maximum_state_signature_dimension_count"]
        ),
    }


def test_path_aware_lexical_scan_counts_direct_proof_structures_per_certificate(
    validator: ModuleType,
) -> None:
    proof_node = {
        "ordered_child_positions": [1, 2],
        "ordered_ancestor_observable_dimensions": [{}, {}],
        "output_frontier": {
            "materialized_frontier": {
                "ordered_state_frontiers": [
                    {"ordered_length_bitmap_runs": [{}, {}]},
                    {"ordered_length_bitmap_runs": []},
                ]
            }
        },
        "derivation": {
            "ordered_choice_coordinate_plan_ids": ["a", "b"],
            "ordered_transient_recurrence_catalogs": [
                {"ordered_state_records": [{}, {}]}
            ],
        },
    }
    raw = _canonical(
        {
            "first": {"ordered_proof_nodes": [proof_node]},
            "second": {"ordered_proof_nodes": [{}, {}]},
        }
    )
    counts = validator._scan_json_resource_structure(  # noqa: SLF001
        raw,
        limits=validator.SEED_EXECUTION_SAFETY_LIMITS_V1,
        label="lexical proof structures",
    )
    first = counts[("first",)]
    assert first["proof_node_count"] == 1
    assert first["proof_edge_count"] == 2
    assert first["maximum_child_count"] == 2
    assert first["state_signature_dimension_count"] == 2
    assert first["maximum_state_signature_dimension_count"] == 2
    assert first["frontier_state_entry_count"] == 2
    assert first["frontier_bitmap_run_count"] == 2
    assert first["component_choice_coordinate_count"] == 2
    assert first["state_catalog_entry_count"] == 2
    assert counts[("second",)]["proof_node_count"] == 2


def test_lexical_resource_summary_is_equality_evidence_and_never_seeds_meter_c(
    validator: ModuleType,
) -> None:
    meter = validator.ProofResourceMeter(phase=validator.SEED_CAP_DERIVATION_PHASE)
    meter.reserve(
        {
            "proof_node_count": 2,
            "proof_edge_count": 1,
            "state_signature_dimension_count": 3,
            "frontier_state_entry_count": 4,
            "frontier_bitmap_run_count": 5,
            "component_choice_coordinate_count": 6,
        }
    )
    meter.observe_maximum("maximum_child_count", 1)
    meter.observe_maximum("maximum_state_signature_dimension_count", 2)
    summary = dict.fromkeys(validator.PROOF_RESOURCE_KEYS, 0)
    for name in validator.CURRENTLY_METERED_LEXICAL_FIELDS:
        summary[name] = meter.value(name)
    summary["certificate_canonical_octets"] = 1_234
    producer_claim = dict(summary)

    validator._validate_lexical_resource_summary(  # noqa: SLF001
        summary,
        producer_claim=producer_claim,
        meter=meter,
        label="lexical equality",
    )
    assert meter.value("certificate_canonical_octets") == 0

    wrong_claim = dict(producer_claim)
    wrong_claim["certificate_canonical_octets"] += 1
    with pytest.raises(
        validator.MaximumProtocolValidationError,
        match="differs from lexical predecode",
    ):
        validator._validate_lexical_resource_summary(  # noqa: SLF001
            summary,
            producer_claim=wrong_claim,
            meter=None,
            label="wrong producer equality target",
        )

    wrong_summary = dict(summary)
    wrong_summary["proof_node_count"] += 1
    wrong_summary_claim = dict(wrong_summary)
    with pytest.raises(
        validator.MaximumProtocolValidationError,
        match="semantic meter proof_node_count",
    ):
        validator._validate_lexical_resource_summary(  # noqa: SLF001
            wrong_summary,
            producer_claim=wrong_summary_claim,
            meter=meter,
            label="wrong semantic total",
        )


def test_path_aware_lexical_scan_rejects_escaped_oversized_proof_array(
    validator: ModuleType,
) -> None:
    limits = dict(validator.SEED_EXECUTION_SAFETY_LIMITS_V1)
    limits["proof_node_count"] = 2
    raw = b'{"ordered_proof_\\u006eodes":[{},{},{}]}'
    with pytest.raises(
        validator.MaximumProtocolValidationError,
        match="proof_node_count limit 2",
    ):
        validator._scan_json_resource_structure(  # noqa: SLF001
            raw,
            limits=limits,
            label="escaped oversized proof array",
        )


def test_predecode_resource_scan_rejects_before_whole_object_json_loads(
    validator: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    limits = dict(validator.SEED_EXECUTION_SAFETY_LIMITS_V1)
    limits["proof_edge_count"] = 1
    raw = _pretty(
        {
            "ordered_proof_nodes": [
                {"ordered_child_positions": [1, 2]},
            ]
        }
    )
    called = False

    def forbidden_loads(*_: Any, **__: Any) -> Any:
        nonlocal called
        called = True
        raise AssertionError("whole-object JSON decode occurred before cap rejection")

    monkeypatch.setattr(validator.json, "loads", forbidden_loads)
    with pytest.raises(
        validator.MaximumProtocolValidationError,
        match="proof_edge_count limit 1",
    ):
        validator._decode_pretty_json(  # noqa: SLF001
            raw,
            label="oversized proof edges",
            lexical_resource_limits=limits,
        )
    assert not called


def test_pilot_path_profile_counts_only_exact_certificate_anchors(
    validator: ModuleType,
) -> None:
    limits = dict(validator.SEED_EXECUTION_SAFETY_LIMITS_V1)
    limits["proof_node_count"] = 2
    value = {
        "ordered_pilot_case_records": [
            {
                "pilot_upper_bound_certificate": {"ordered_proof_nodes": [{}, {}]},
                "unrelated": {"ordered_proof_nodes": [{}, {}, {}]},
            },
            {"pilot_upper_bound_certificate": {"ordered_proof_nodes": [{}]}},
        ]
    }
    counts = validator._scan_json_resource_structure(  # noqa: SLF001
        _canonical(value),
        limits=limits,
        label="exact pilot certificate paths",
        path_profile=validator.LEXICAL_PILOT_CERTIFICATE_PROFILE,
    )
    first_anchor = (
        "ordered_pilot_case_records",
        "[0]",
        "pilot_upper_bound_certificate",
    )
    second_anchor = (
        "ordered_pilot_case_records",
        "[1]",
        "pilot_upper_bound_certificate",
    )
    assert set(counts) == {first_anchor, second_anchor}
    assert counts[first_anchor]["proof_node_count"] == 2
    assert counts[second_anchor]["proof_node_count"] == 1


@pytest.mark.parametrize(
    ("raw", "message"),
    (
        (b'{"duplicate":1,"duplicate":2}', "duplicate lexical object member"),
        (b'{"float":1.0}', "canonical integer/null/boolean"),
        (b'{"integer":9007199254740992}', "safe-I-JSON domain"),
    ),
)
def test_lexical_scan_rejects_duplicate_keys_or_noncanonical_scalars(
    validator: ModuleType,
    raw: bytes,
    message: str,
) -> None:
    with pytest.raises(validator.MaximumProtocolValidationError, match=message):
        validator._scan_json_resource_structure(  # noqa: SLF001
            raw,
            limits=validator.SEED_EXECUTION_SAFETY_LIMITS_V1,
            label="strict lexical JSON",
        )


def test_lexical_scan_rejects_pilot_phase_mismatch_before_decode(
    validator: ModuleType,
) -> None:
    raw = _canonical({"pilot_phase": validator.FINAL_PROTOCOL_REBIND_PHASE})
    with pytest.raises(
        validator.MaximumProtocolValidationError,
        match="pilot_phase differs from expected SEED_CAP_DERIVATION",
    ):
        validator._scan_json_resource_structure(  # noqa: SLF001
            raw,
            limits=validator.SEED_EXECUTION_SAFETY_LIMITS_V1,
            label="pilot phase mismatch",
            path_profile=validator.LEXICAL_PILOT_CERTIFICATE_PROFILE,
            expected_pilot_phase=validator.SEED_CAP_DERIVATION_PHASE,
        )


def test_lexical_scan_enforces_compact_certificate_token_length(
    validator: ModuleType,
) -> None:
    value = {"ordered_proof_nodes": [{}], "padding": "escape\\nheavy"}
    limits = dict(validator.SEED_EXECUTION_SAFETY_LIMITS_V1)
    limits["certificate_canonical_octets"] = len(_canonical(value)) - 1
    with pytest.raises(
        validator.MaximumProtocolValidationError,
        match="certificate_canonical_octets limit",
    ):
        validator._scan_json_resource_structure(  # noqa: SLF001
            _pretty(value),
            limits=limits,
            label="certificate compact token length",
        )


def test_predecode_summary_is_preserved_for_semantic_meter_handoff(
    validator: ModuleType,
) -> None:
    value = {"ordered_proof_nodes": [{}]}
    summary: dict[tuple[str, ...], dict[str, int]] = {}
    decoded = validator._decode_pretty_json(  # noqa: SLF001
        _pretty(value),
        label="lexical summary handoff",
        lexical_resource_limits=validator.SEED_EXECUTION_SAFETY_LIMITS_V1,
        lexical_summary_out=summary,
    )
    assert decoded == value
    assert summary[()]["proof_node_count"] == 1
    assert summary[()]["certificate_canonical_octets"] == len(_canonical(value))


@pytest.mark.parametrize(
    "value",
    (
        None,
        True,
        9_007_199_254_740_991,
        "plain",
        'quote\\" slash\\\\ control\\n',
        "Zażółć gęślą jaźń 🚀",
        [None, False, 17, "λ"],
        {"z": [3, 2, 1], "a": {"nested": "é"}},
    ),
)
def test_length_only_and_streaming_canonical_sinks_match_reference_bytes(
    validator: ModuleType,
    value: Any,
) -> None:
    raw = _canonical(value)
    assert validator._canonical_octet_length(value) == len(raw)  # noqa: SLF001
    assert validator._pretty_octet_length(value) == len(_pretty(value))  # noqa: SLF001
    assert (
        validator._canonical_sha256_stream(value)
        == hashlib.sha256(  # noqa: SLF001
            raw
        ).hexdigest()
    )


def test_length_only_sink_never_calls_encoder_chunk_materialization(
    validator: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    value = {
        "escape_heavy": ('"\\\n\b\t\r\fλ🚀' * 10_000),
        "nested": [None, True, False, -17],
    }
    expected = len(_canonical(value))

    def forbidden_chunks(_: Any) -> Any:
        raise AssertionError("length-only sink materialized an encoder token")

    monkeypatch.setattr(validator, "_canonical_text_chunks", forbidden_chunks)
    assert validator._canonical_octet_length(value) == expected  # noqa: SLF001


def test_metered_canonical_hash_checks_all_caps_before_hashing(
    validator: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    limits = {
        name: validator.SEED_EXECUTION_SAFETY_LIMITS_V1[name]
        for name in validator.ACCEPTED_PROOF_RESOURCE_LIMIT_KEYS
    }
    limits["hash_preimage_octets"] = 1
    limits["frontier_canonicalized_octets"] = 2
    meter = validator.ProofResourceMeter(
        phase=validator.FINAL_PROTOCOL_REBIND_PHASE,
        accepted_limits=limits,
    )
    called = False

    def forbidden_hash(_: Any) -> str:
        nonlocal called
        called = True
        raise AssertionError("hashing happened before cap rejection")

    monkeypatch.setattr(validator, "_canonical_sha256_stream", forbidden_hash)
    with pytest.raises(validator.MaximumProtocolValidationError):
        validator._metered_canonical_sha256(  # noqa: SLF001
            {},
            meter=meter,
            canonicalized_field="frontier_canonicalized_octets",
        )
    assert not called
    assert meter.value("hash_preimage_octets") == 0
    assert meter.value("frontier_canonicalized_octets") == 0


def test_expanded_frontier_reserves_complete_preimage_before_any_hash_update(
    validator: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_frontiers = [
        {
            "state_key": [],
            "ordered_length_bitmap_runs": [
                {
                    "first_block_index": 0,
                    "last_block_index": 0,
                    "attainable_length_bitmap_hex": _bitmap(3),
                }
            ],
        }
    ]
    expanded = [
        {"canonical_byte_length": 0, "state_key": []},
        {"canonical_byte_length": 1, "state_key": []},
    ]
    limits = {
        name: validator.SEED_EXECUTION_SAFETY_LIMITS_V1[name]
        for name in validator.ACCEPTED_PROOF_RESOURCE_LIMIT_KEYS
    }
    limits["frontier_canonicalized_octets"] = len(_canonical(expanded)) - 1
    meter = validator.ProofResourceMeter(
        phase=validator.FINAL_PROTOCOL_REBIND_PHASE,
        accepted_limits=limits,
    )
    called = False

    def forbidden_sha256(*_: Any, **__: Any) -> Any:
        nonlocal called
        called = True
        raise AssertionError("digest was created before whole-preimage reservation")

    monkeypatch.setattr(validator.hashlib, "sha256", forbidden_sha256)
    with pytest.raises(validator.MaximumProtocolValidationError):
        validator._stream_expanded_frontier_digest_metered(  # noqa: SLF001
            state_frontiers,
            meter=meter,
        )
    assert not called
    assert meter.value("frontier_expanded_point_count") == 0
    assert meter.value("maximum_frontier_width") == 0
    assert meter.value("frontier_canonicalized_octets") == 0
    assert meter.value("hash_preimage_octets") == 0


def test_empty_materialized_frontier_charges_four_octets_and_hashes_nothing(
    validator: ModuleType,
) -> None:
    signature = _empty_signature(validator)
    frontier = {
        "frontier_soundness": "EXACT_ATTAINABLE",
        "state_signature_id": signature,
        "ordered_observable_descriptor_ids": [],
        "ordered_state_frontiers": [],
    }
    meter = validator.ProofResourceMeter(phase=validator.SEED_CAP_DERIVATION_PHASE)
    _, evidence = validator._validate_materialized_frontier(  # noqa: SLF001
        frontier,
        dimensions=[],
        state_signature_id=signature,
        label="empty materialized frontier",
        resource_meter=meter,
    )
    assert evidence == {
        "state_entry_count": 0,
        "bitmap_run_count": 0,
        "expanded_attainable_point_count": 0,
        "minimum_attainable_octets": None,
        "maximum_attainable_octets": None,
        "expanded_frontier_sha256": None,
        "canonical_bitmap_run_frontier_sha256": None,
        "frontier_canonicalized_octets": 4,
    }
    assert meter.value("frontier_canonicalized_octets") == 4
    assert meter.value("hash_preimage_octets") == 0


def test_expanded_frontier_point_cap_rejects_before_canonical_record_work(
    validator: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    limits = {
        name: validator.SEED_EXECUTION_SAFETY_LIMITS_V1[name]
        for name in validator.ACCEPTED_PROOF_RESOURCE_LIMIT_KEYS
    }
    limits["frontier_expanded_point_count"] = 0
    limits["maximum_frontier_width"] = 0
    meter = validator.ProofResourceMeter(
        phase=validator.FINAL_PROTOCOL_REBIND_PHASE,
        accepted_limits=limits,
    )
    called = False

    def forbidden_length(_: Any) -> int:
        nonlocal called
        called = True
        raise AssertionError(
            "canonical record work happened before point-cap rejection"
        )

    monkeypatch.setattr(validator, "_canonical_octet_length", forbidden_length)
    with pytest.raises(validator.MaximumProtocolValidationError):
        validator._stream_expanded_frontier_digest_metered(  # noqa: SLF001
            [
                {
                    "state_key": [],
                    "ordered_length_bitmap_runs": _one_length_run(),
                }
            ],
            meter=meter,
        )
    assert not called
    assert meter.value("frontier_expanded_point_count") == 0
    assert meter.value("frontier_canonicalized_octets") == 0
    assert meter.value("hash_preimage_octets") == 0


def _minimal_fixed_point_certificate(
    validator: ModuleType,
    meter: Any,
) -> dict[str, Any]:
    return {
        "certificate_version": "fixed-point-test.v1",
        "proof_resource_claim": meter.snapshot(),
        "upper_bound_certificate_id": None,
    }


def test_certificate_semantic_completeness_barrier_is_closed(
    validator: ModuleType,
) -> None:
    assert validator.CERTIFICATE_SEMANTIC_RESOURCE_ACCOUNTING_COMPLETE is False
    with pytest.raises(
        validator.MaximumProtocolValidationError,
        match=validator.SEMANTIC_RESOURCE_ACCOUNTING_INCOMPLETE,
    ):
        validator._require_certificate_semantic_resource_accounting_complete()  # noqa: SLF001


def test_upper_certificate_joint_fixed_point_is_least_streamed_and_metered(
    validator: ModuleType,
) -> None:
    meter = validator.ProofResourceMeter(phase=validator.SEED_CAP_DERIVATION_PHASE)
    h0 = 17
    meter.add("hash_preimage_octets", h0)
    certificate = _minimal_fixed_point_certificate(validator, meter)
    solved = validator._solve_upper_bound_certificate_fixed_point(  # noqa: SLF001
        certificate,
        hash_preimage_octets_before_certificate=h0,
        meter=meter,
    )
    unsigned = {
        name: item
        for name, item in solved.certificate.items()
        if name != "upper_bound_certificate_id"
    }
    assert solved.iteration_count >= 2
    assert solved.certificate_id == validator._semantic_id(  # noqa: SLF001
        validator.CERTIFICATE_DOMAIN,
        unsigned,
    )
    assert solved.hash_preimage_octets == meter.value("hash_preimage_octets")
    assert solved.certificate_canonical_octets == len(_canonical(solved.certificate))
    assert solved.certificate["proof_resource_claim"]["hash_preimage_octets"] == (
        solved.hash_preimage_octets
    )

    finalizer_meter = validator.ProofResourceMeter(
        phase=validator.SEED_CAP_DERIVATION_PHASE
    )
    finalizer_meter.add("hash_preimage_octets", h0)
    finalized = validator._finalize_upper_bound_certificate_resource_claim(  # noqa: SLF001
        copy.deepcopy(solved.certificate),
        meter=finalizer_meter,
    )
    assert finalized.certificate == solved.certificate
    assert finalizer_meter.snapshot() == solved.certificate["proof_resource_claim"]

    wrong_id = copy.deepcopy(solved.certificate)
    wrong_id["upper_bound_certificate_id"] = "f" * 64
    rejecting_meter = validator.ProofResourceMeter(
        phase=validator.SEED_CAP_DERIVATION_PHASE
    )
    rejecting_meter.add("hash_preimage_octets", h0)
    with pytest.raises(
        validator.MaximumProtocolValidationError,
        match="least joint H/C fixed point",
    ):
        validator._finalize_upper_bound_certificate_resource_claim(  # noqa: SLF001
            wrong_id,
            meter=rejecting_meter,
        )
    assert (
        solved.certificate["proof_resource_claim"]["certificate_canonical_octets"]
        == solved.certificate_canonical_octets
    )


def test_upper_certificate_fixed_point_trials_are_length_only(
    validator: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    meter = validator.ProofResourceMeter(phase=validator.SEED_CAP_DERIVATION_PHASE)
    certificate = {
        **_minimal_fixed_point_certificate(validator, meter),
        "escape_heavy": ('"\\\nλ' * 10_000),
    }
    original_chunks = validator._canonical_text_chunks  # noqa: SLF001
    calls = 0

    def tracked_chunks(value: Any) -> Any:
        nonlocal calls
        calls += 1
        yield from original_chunks(value)

    monkeypatch.setattr(validator, "_canonical_text_chunks", tracked_chunks)
    solved = validator._solve_upper_bound_certificate_fixed_point(  # noqa: SLF001
        certificate,
        hash_preimage_octets_before_certificate=0,
        meter=meter,
    )
    assert solved.iteration_count >= 2
    assert calls == 1


def test_upper_certificate_fixed_point_rejects_boolean_resource_claim(
    validator: ModuleType,
) -> None:
    meter = validator.ProofResourceMeter(phase=validator.SEED_CAP_DERIVATION_PHASE)
    certificate = _minimal_fixed_point_certificate(validator, meter)
    certificate["proof_resource_claim"]["proof_node_count"] = False
    with pytest.raises(validator.MaximumProtocolValidationError):
        validator._solve_upper_bound_certificate_fixed_point(  # noqa: SLF001
            certificate,
            hash_preimage_octets_before_certificate=0,
            meter=meter,
        )


def test_upper_certificate_fixed_point_rejects_cap_plus_one_before_hashing(
    validator: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline_meter = validator.ProofResourceMeter(
        phase=validator.SEED_CAP_DERIVATION_PHASE
    )
    h0 = 11
    baseline_meter.add("hash_preimage_octets", h0)
    baseline_certificate = _minimal_fixed_point_certificate(validator, baseline_meter)
    baseline = validator._solve_upper_bound_certificate_fixed_point(  # noqa: SLF001
        baseline_certificate,
        hash_preimage_octets_before_certificate=h0,
        meter=baseline_meter,
    )

    limits = {
        name: validator.SEED_EXECUTION_SAFETY_LIMITS_V1[name]
        for name in validator.ACCEPTED_PROOF_RESOURCE_LIMIT_KEYS
    }
    limits["certificate_canonical_octets"] = baseline.certificate_canonical_octets - 1
    capped_meter = validator.ProofResourceMeter(
        phase=validator.FINAL_PROTOCOL_REBIND_PHASE,
        accepted_limits=limits,
    )
    capped_meter.add("hash_preimage_octets", h0)
    capped_certificate = _minimal_fixed_point_certificate(validator, capped_meter)
    called = False

    def forbidden_hash(_: Any) -> str:
        nonlocal called
        called = True
        raise AssertionError("certificate hashing happened before cap rejection")

    monkeypatch.setattr(validator, "_canonical_sha256_stream", forbidden_hash)
    with pytest.raises(validator.MaximumProtocolValidationError):
        validator._solve_upper_bound_certificate_fixed_point(  # noqa: SLF001
            capped_certificate,
            hash_preimage_octets_before_certificate=h0,
            meter=capped_meter,
        )
    assert not called
    assert capped_meter.value("hash_preimage_octets") == h0
    assert capped_meter.value("certificate_canonical_octets") == 0
