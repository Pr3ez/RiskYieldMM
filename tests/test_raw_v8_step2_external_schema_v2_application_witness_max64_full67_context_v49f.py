from __future__ import annotations

import ast
import copy
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
GENERATOR = (
    ROOT / "scripts/tests/generate_raw_v8_step2_external_schema_v2_"
    "application_witness_max64_full67_context_v49f.py"
)
VALIDATOR = (
    ROOT / "scripts/tests/validate_raw_v8_step2_external_schema_v2_"
    "application_witness_max64_full67_context_v49f.py"
)
CONTEXT = (
    ROOT / "scripts/tests/raw_v8_step2_external_schema_v2_"
    "application_witness_max64_full67_context_v49f.json"
)
REGISTRY = (
    ROOT / "scripts/tests/raw_v8_step2_external_schema_v2_structural_registry_v49f.json"
)
LITERALS = (
    ROOT
    / "scripts/tests/raw_v8_step2_external_schema_v2_rule_literal_authority_v49f.json"
)

RAW_OCTETS = 16_121_125
RAW_SHA256 = "afab90030ac96fa21157bdd3e696dd25798d7755be028c5cb8eaca103f73de97"
CANONICAL_OCTETS = 12_698_603
CANONICAL_SHA256 = "ab67d30d11d19670652b4c1a7aeb2d1483b97f6c4dde7bd673d9f25a3079059e"
ROOT_IDENTITY = "e988ccf6af1691103875d355aa64b91baabb2dc0f965999b9007bb64321a113e"
SEQUENCE_SHA256 = "e1a8ed64c6c94d5f80624e011f474904f872211e671c89e276aa61460fc1cd9f"


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _run(*arguments: str, timeout: int = 90) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        (sys.executable, "-I", "-B", *arguments),
        cwd=ROOT,
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


@pytest.fixture(scope="module")
def validator_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("_max64_context_validator", VALIDATOR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def context() -> dict[str, Any]:
    value = json.loads(CONTEXT.read_text(encoding="utf-8"))
    assert type(value) is dict
    return value


def test_materialized_context_has_exact_transport_and_semantic_pins(
    context: dict[str, Any],
) -> None:
    raw = CONTEXT.read_bytes()
    assert len(raw) == RAW_OCTETS < 16_777_216
    assert hashlib.sha256(raw).hexdigest() == RAW_SHA256
    canonical = _canonical_bytes(context)
    assert len(canonical) == CANONICAL_OCTETS
    assert hashlib.sha256(canonical).hexdigest() == CANONICAL_SHA256
    assert set(context) == {"observations", "root", "selector"}
    assert len(context["observations"]) == 67
    assert len(context["selector"]["ordered_entries"]) == 64
    assert context["root"]["target_observation_root_sha256"] == ROOT_IDENTITY
    assert (
        hashlib.sha256(_canonical_bytes(context["observations"])).hexdigest()
        == SEQUENCE_SHA256
    )


def test_independent_validator_recomputes_schema_identity_and_applications() -> None:
    result = _run(str(VALIDATOR), "--repository-root", str(ROOT))
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    report = json.loads(result.stdout)
    assert report == {
        "application_rule_invocations": 68,
        "canonical_octets": CANONICAL_OCTETS,
        "canonical_sha256": CANONICAL_SHA256,
        "identity_checks": 12_595,
        "intrinsic_rule_invocations": 12_862,
        "raw_octets": RAW_OCTETS,
        "raw_sha256": RAW_SHA256,
        "record_validations": 13_525,
        "root_identity": ROOT_IDENTITY,
        "total_rule_invocations": 12_930,
    }


def test_generator_check_and_independent_reproduction_are_byte_exact(
    tmp_path: Path,
) -> None:
    check = _run(
        str(GENERATOR),
        "--repository-root",
        str(ROOT),
        "--check",
    )
    assert check.returncode == 0, check.stderr
    assert check.stderr == ""

    reproduced = tmp_path / CONTEXT.name
    write = _run(
        str(GENERATOR),
        "--repository-root",
        str(ROOT),
        "--output",
        str(reproduced),
        "--write",
    )
    assert write.returncode == 0, write.stderr
    assert write.stderr == ""
    assert reproduced.read_bytes() == CONTEXT.read_bytes()

    second_check = _run(
        str(GENERATOR),
        "--repository-root",
        str(ROOT),
        "--output",
        str(reproduced),
        "--check",
    )
    assert second_check.returncode == 0, second_check.stderr
    assert second_check.stderr == ""


def test_generator_and_validator_do_not_import_existing_runtime_or_production() -> None:
    for path in (GENERATOR, VALIDATOR):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imported: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                imported.append(node.module)
        assert not any(
            name == "riskyieldmm" or name.startswith("riskyieldmm.")
            for name in imported
        )
        assert not any("maximum_protocol" in name for name in imported)
        assert not any("rule_runtime" in name for name in imported)
        assert not any("application_witness" in name for name in imported)


def test_validator_rejects_duplicate_keys_and_identity_drift(
    validator_module: ModuleType,
    context: dict[str, Any],
) -> None:
    with pytest.raises(
        validator_module.ContextValidationError, match="duplicate JSON key"
    ):
        validator_module._strict_object([("same", 1), ("same", 2)])

    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    literals = json.loads(LITERALS.read_text(encoding="utf-8"))
    validator = validator_module._RegistryValidator(registry, literals)
    observation = copy.deepcopy(context["observations"][0])
    observation["observation_id"] = "0" * 64
    with pytest.raises(
        validator_module.ContextValidationError, match="identity differs"
    ):
        validator.validate_type("TargetObservationV2", observation)


def test_validator_rejects_resolver_order_and_application_membership_drift(
    validator_module: ModuleType,
    context: dict[str, Any],
) -> None:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    literals = json.loads(LITERALS.read_text(encoding="utf-8"))

    reordered = {
        "observations": list(context["observations"]),
        "root": context["root"],
        "selector": context["selector"],
    }
    reordered["observations"][0], reordered["observations"][1] = (
        reordered["observations"][1],
        reordered["observations"][0],
    )
    validator = validator_module._RegistryValidator(registry, literals)
    with pytest.raises(
        validator_module.ContextValidationError,
        match="observation resolver failed",
    ):
        validator_module._validate_applications_and_resolvers(validator, reordered)

    membership_drift = {
        "observations": list(context["observations"]),
        "root": context["root"],
        "selector": context["selector"],
    }
    first = copy.deepcopy(membership_drift["observations"][0])
    first["observation_context"]["candidate_id"] = "0" * 64
    membership_drift["observations"][0] = first
    validator = validator_module._RegistryValidator(registry, literals)
    with pytest.raises(
        validator_module.ContextValidationError,
        match="membership rule is false",
    ):
        validator_module._validate_applications_and_resolvers(
            validator,
            membership_drift,
        )
