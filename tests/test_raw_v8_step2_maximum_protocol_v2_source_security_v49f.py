"""Fail-closed source and publication checks for the Raw-V8 Step-2 V2 seed."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
import sys
from dataclasses import replace
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
GENERATOR_PATH = (
    ROOT
    / "scripts/tests/generate_raw_v8_step2_maximum_protocol_v2_seed_catalog_v49f.py"
)
TRANSFER_RULE_PATH = (
    ROOT / "scripts/tests/raw_v8_step2_cell_transfer_rule_catalog_v49f.json"
)


def _generator() -> ModuleType:
    module_name = "raw_v8_step2_v2_seed_generator_source_security_test"
    spec = importlib.util.spec_from_file_location(module_name, GENERATOR_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


GENERATOR = _generator()


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _semantic_id(domain: str, payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        _canonical_bytes(
            {
                "canonicalization_version": GENERATOR.CANONICALIZATION_VERSION,
                "domain": domain,
                "payload": payload,
                "schema_version": GENERATOR.MEASUREMENT_SCHEMA_VERSION,
            }
        )
    ).hexdigest()


def _identity(name: str) -> dict[str, Any]:
    return next(
        row for row in GENERATOR._identity_records() if row["identity_name"] == name
    )


def test_all_pinned_sources_are_repeatable_unique_and_buildable() -> None:
    specs = GENERATOR._source_specs()
    assert len(specs) == 17
    assert sum(spec.exact_octets for spec in specs) <= 67_108_864
    snapshots = GENERATOR._load_repeatable_source_snapshots(ROOT, specs)
    assert tuple(snapshots) == tuple(spec.path for spec in specs)
    assert len({snapshot.identity[:2] for snapshot in snapshots.values()}) == 17
    for snapshot in snapshots.values():
        assert snapshot.identity[3] == 1
        assert len(snapshot.raw) == snapshot.spec.exact_octets
        assert hashlib.sha256(snapshot.raw).hexdigest() == snapshot.spec.raw_sha256

    catalog = GENERATOR._build_catalog_from_snapshots(snapshots)
    rendered = GENERATOR._pretty_bytes(catalog)
    GENERATOR._enforce_rendered_output(catalog, rendered)
    assert len(rendered) <= GENERATOR.OPERATIONAL_OUTPUT_MAXIMUM_OCTETS


@pytest.mark.parametrize(
    "raw,root_kind",
    [
        (b'{\n  "a": 1,\n  "a": 2\n}\n', "OBJECT"),
        (b'{\n  "a": NaN\n}\n', "OBJECT"),
        (b'{\n  "a": Infinity\n}\n', "OBJECT"),
        (b'{\n  "a": 1.5\n}\n', "OBJECT"),
        (b'{\n  "a": 9007199254740992\n}\n', "OBJECT"),
        (b'{\n  "a": "\\ud800"\n}\n', "OBJECT"),
        (b'{"a":1}', "OBJECT"),
        (b"{}\n", "ARRAY"),
    ],
)
def test_strict_json_rejects_ambiguous_or_noncanonical_inputs(
    raw: bytes, root_kind: str
) -> None:
    with pytest.raises(GENERATOR.CatalogFailure):
        GENERATOR._parse_strict_canonical_json(
            raw, label="adversarial input", root_kind=root_kind
        )


def test_strict_json_rejects_resource_exhaustion_shapes() -> None:
    too_deep = (
        b"[" * (GENERATOR.MAXIMUM_JSON_NESTING_DEPTH + 1)
        + b"0"
        + b"]" * (GENERATOR.MAXIMUM_JSON_NESTING_DEPTH + 1)
    )
    with pytest.raises(GENERATOR.CatalogFailure, match="nesting"):
        GENERATOR._parse_strict_canonical_json(
            too_deep, label="deep input", root_kind="ARRAY"
        )

    oversized_string = GENERATOR._pretty_bytes(
        {"value": "x" * (GENERATOR.MAXIMUM_JSON_STRING_CODEPOINTS + 1)}
    )
    with pytest.raises(GENERATOR.CatalogFailure, match="string exceeds"):
        GENERATOR._parse_strict_canonical_json(
            oversized_string, label="wide input", root_kind="OBJECT"
        )


def test_complete_snapshot_comparison_rejects_identity_or_byte_drift() -> None:
    snapshots = GENERATOR._load_repeatable_source_snapshots(
        ROOT, GENERATOR._source_specs()
    )
    path = next(iter(snapshots))
    changed = dict(snapshots)
    changed[path] = replace(
        snapshots[path],
        identity=(*snapshots[path].identity[:-1], snapshots[path].identity[-1] + 1),
    )
    with pytest.raises(GENERATOR.CatalogFailure, match="changed between"):
        GENERATOR._assert_snapshot_sets_equal(snapshots, changed)


def test_secure_source_read_rejects_symlinks_and_hardlinks(tmp_path: Path) -> None:
    raw = GENERATOR._pretty_bytes({"value": 1})
    target = tmp_path / "target.json"
    target.write_bytes(raw)
    symlink = tmp_path / "symlink.json"
    symlink.symlink_to(target.name)
    symlink_spec = GENERATOR._SourceSpec(
        "symlink",
        Path(symlink.name),
        len(raw),
        hashlib.sha256(raw).hexdigest(),
        None,
        "OBJECT",
    )
    with pytest.raises((GENERATOR.CatalogFailure, OSError)):
        GENERATOR._bounded_repository_snapshot(tmp_path, symlink_spec)

    hardlink = tmp_path / "hardlink.json"
    os.link(target, hardlink)
    hardlink_spec = replace(symlink_spec, role="hardlink", path=Path(hardlink.name))
    with pytest.raises(GENERATOR.CatalogFailure, match="single-link"):
        GENERATOR._bounded_repository_snapshot(tmp_path, hardlink_spec)


def test_transfer_source_rejects_unknown_extra_wrong_id_and_forward_call() -> None:
    original = json.loads(TRANSFER_RULE_PATH.read_bytes())
    identities = GENERATOR._identity_records()

    unknown = copy.deepcopy(original)
    unknown["ordered_transfer_rule_records"][0]["program"]["opcode"] = "UNKNOWN_V1"
    with pytest.raises(GENERATOR.CatalogFailure, match="unknown transfer AST"):
        GENERATOR._validated_transfer_rule_catalog(
            GENERATOR._pretty_bytes(unknown), identities
        )

    extra = copy.deepcopy(original)
    extra["ordered_transfer_rule_records"][0]["program"]["unexercised"] = None
    with pytest.raises(GENERATOR.CatalogFailure, match="member set differs"):
        GENERATOR._validated_transfer_rule_catalog(
            GENERATOR._pretty_bytes(extra), identities
        )

    wrong_id = copy.deepcopy(original)
    wrong_id["ordered_transfer_rule_records"][0]["transfer_rule_id"] = "0" * 64
    with pytest.raises(GENERATOR.CatalogFailure, match="transfer-rule ID differs"):
        GENERATOR._validated_transfer_rule_catalog(
            GENERATOR._pretty_bytes(wrong_id), identities
        )

    forward = copy.deepcopy(original)
    rules = forward["ordered_transfer_rule_records"]
    call = rules[14]["program"]["ordered_bindings"][0]["value_expression"]
    assert call["opcode"] == "MAP_V1"
    call_rule = call["map_expression"]
    assert call_rule["opcode"] == "CALL_RULE_V1"
    call_rule["transfer_rule_id"] = rules[-1]["transfer_rule_id"]
    rule_identity = _identity("CELL_TRANSFER_RULE")
    rule_payload = {
        name: rules[14][name] for name in rule_identity["ordered_payload_member_names"]
    }
    rules[14]["transfer_rule_id"] = _semantic_id(
        rule_identity["domain_literal"], rule_payload
    )
    with pytest.raises(GENERATOR.CatalogFailure, match="forward"):
        GENERATOR._validated_transfer_rule_catalog(
            GENERATOR._pretty_bytes(forward), identities
        )


def test_atomic_publication_is_exact_and_leaves_no_temporary(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "scripts" / "tests"
    output_dir.mkdir(parents=True)
    relative = Path("scripts/tests/output.json")
    rendered = GENERATOR._pretty_bytes({"value": 1})
    GENERATOR._atomic_write_repository_output(
        tmp_path, relative, rendered, protected_inodes=frozenset()
    )
    assert (tmp_path / relative).read_bytes() == rendered
    assert list(output_dir.glob(".output.json.tmp.*")) == []
    GENERATOR._secure_check_repository_output(
        tmp_path, relative, rendered, protected_inodes=frozenset()
    )

    second = GENERATOR._pretty_bytes({"value": 2})
    GENERATOR._atomic_write_repository_output(
        tmp_path, relative, second, protected_inodes=frozenset()
    )
    assert (tmp_path / relative).read_bytes() == second
    assert list(output_dir.glob(".output.json.tmp.*")) == []


@pytest.mark.parametrize("alias_kind", ["symlink", "hardlink"])
def test_atomic_publication_rejects_aliased_output(
    tmp_path: Path, alias_kind: str
) -> None:
    output_dir = tmp_path / "scripts" / "tests"
    output_dir.mkdir(parents=True)
    target = output_dir / "target.json"
    target.write_bytes(b"{}\n")
    output = output_dir / "output.json"
    if alias_kind == "symlink":
        output.symlink_to(target.name)
        expected = "regular file"
    else:
        os.link(target, output)
        expected = "single-link"
    with pytest.raises(GENERATOR.CatalogFailure, match=expected):
        GENERATOR._atomic_write_repository_output(
            tmp_path,
            Path("scripts/tests/output.json"),
            GENERATOR._pretty_bytes({"value": 1}),
            protected_inodes=frozenset(),
        )


def test_operational_output_limit_is_enforced(monkeypatch: pytest.MonkeyPatch) -> None:
    artifact = {
        "f0_seed_ceiling_catalog": {
            "ordered_platform_ceiling_records": [
                {
                    "resource_name": "INDIVIDUAL_FILE_STRICT_UPPER_OCTETS",
                    "ceiling_value": GENERATOR.INDIVIDUAL_FILE_STRICT_UPPER_OCTETS,
                }
            ]
        }
    }
    monkeypatch.setattr(GENERATOR, "OPERATIONAL_OUTPUT_MAXIMUM_OCTETS", 4)
    with pytest.raises(GENERATOR.CatalogFailure, match="15 MiB"):
        GENERATOR._enforce_rendered_output(artifact, b"12345")
