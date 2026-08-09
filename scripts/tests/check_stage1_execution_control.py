#!/usr/bin/env python3
"""Fail closed when the Stage 1 control ledger drifts from its recorded P0."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CONTROL_PATH = ROOT / "docs/research/stage1_execution_control_2026-08-08.md"
GENERATOR_PATH = (
    ROOT
    / "scripts/tests/generate_raw_v8_step2_maximum_protocol_v2_seed_catalog_v49f.py"
)
CATALOG_PATH = (
    ROOT / "scripts/tests/raw_v8_step2_maximum_protocol_v2_seed_catalog_v49f.json"
)
CONTROL_PATTERN = re.compile(
    r"<!-- STAGE1_CONTROL_JSON_START\n(?P<payload>\{.*?\})\n"
    r"STAGE1_CONTROL_JSON_END -->",
    re.DOTALL,
)
ALLOWED_STATES = {"ACCEPTED", "ACTIVE", "READY", "WAITING", "HOLD", "REJECTED"}
ACTIVE_GATE_PATTERN = re.compile(
    r"<!-- STAGE1_ACTIVE_GATE: (?P<gate>S1-(?:[A-Z][0-9]+|X)) -->"
)


class ControlFailure(RuntimeError):
    """The current tree does not match the Stage 1 control ledger."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ControlFailure(message)


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _load_control() -> dict[str, Any]:
    text = CONTROL_PATH.read_text(encoding="utf-8")
    match = CONTROL_PATTERN.search(text)
    _require(match is not None, "machine-readable control block is missing")
    control = json.loads(match.group("payload"))
    _require(isinstance(control, dict), "control block must be an object")
    return control


def _validate_gate_graph(control: dict[str, Any]) -> None:
    gates = control.get("gate_states")
    _require(isinstance(gates, dict) and gates, "gate_states must be nonempty")
    active = []
    for gate_id, row in gates.items():
        _require(
            re.fullmatch(r"S1-(?:[A-Z][0-9]+|X)", gate_id) is not None,
            f"bad gate {gate_id}",
        )
        _require(isinstance(row, dict), f"{gate_id} row must be an object")
        _require(set(row) == {"depends_on", "state"}, f"{gate_id} members differ")
        state = row["state"]
        _require(state in ALLOWED_STATES, f"{gate_id} has unknown state {state}")
        if state == "ACTIVE":
            active.append(gate_id)
        dependencies = row["depends_on"]
        _require(isinstance(dependencies, list), f"{gate_id} dependencies differ")
        _require(
            len(dependencies) == len(set(dependencies)),
            f"{gate_id} duplicates a dependency",
        )
        for dependency in dependencies:
            _require(
                dependency in gates, f"{gate_id} has unknown dependency {dependency}"
            )
            _require(dependency != gate_id, f"{gate_id} depends on itself")

    _require(
        active == [control.get("active_gate")],
        "exactly one declared active gate is required",
    )

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(gate_id: str) -> None:
        _require(gate_id not in visiting, f"gate dependency cycle reaches {gate_id}")
        if gate_id in visited:
            return
        visiting.add(gate_id)
        for dependency in gates[gate_id]["depends_on"]:
            visit(dependency)
        visiting.remove(gate_id)
        visited.add(gate_id)

    for gate_id in gates:
        visit(gate_id)

    for gate_id, row in gates.items():
        if row["state"] in {"ACTIVE", "READY"}:
            for dependency in row["depends_on"]:
                _require(
                    gates[dependency]["state"] == "ACCEPTED",
                    f"{gate_id} is {row['state']} before {dependency} is accepted",
                )


def _load_generator() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "stage1_seed_generator", GENERATOR_PATH
    )
    _require(spec is not None and spec.loader is not None, "cannot load seed generator")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _validate_navigation(active_gate: str) -> None:
    pointers = {
        ROOT / "README.md": "docs/research/stage1_execution_control_2026-08-08.md",
        ROOT / "docs/README.md": "research/stage1_execution_control_2026-08-08.md",
        ROOT / "docs/research/README.md": "stage1_execution_control_2026-08-08.md",
        ROOT
        / "docs/research/trading_prediction_system_diagnosis_and_redesign_2026-07-14.md": (
            "stage1_execution_control_2026-08-08.md"
        ),
    }
    for path, pointer in pointers.items():
        text = path.read_text(encoding="utf-8")
        _require(
            pointer in text,
            f"missing current pointer in {path}",
        )
        markers = ACTIVE_GATE_PATTERN.findall(text)
        _require(
            markers == [active_gate],
            f"active-gate navigation marker differs in {path}: {markers}",
        )


def validate() -> dict[str, Any]:
    control = _load_control()
    _require(control.get("control_version") == 1, "unknown control version")
    _require(control.get("formal_stage1_state") == "NO-GO", "Stage 1 must remain NO-GO")
    _require(
        control.get("offline_stage2_state") == "BLOCKED",
        "offline Stage 2 state differs",
    )
    _require(
        control.get("live_activation_state") == "BLOCKED",
        "live activation must remain blocked",
    )
    _validate_gate_graph(control)
    _validate_navigation(control["active_gate"])

    snapshot = control.get("seed_snapshot")
    _require(isinstance(snapshot, dict), "seed_snapshot is missing")
    generator_raw = GENERATOR_PATH.read_bytes()
    catalog_raw = CATALOG_PATH.read_bytes()
    _require(
        _sha256(generator_raw) == snapshot["generator_sha256"], "seed generator drifted"
    )
    _require(
        _sha256(catalog_raw) == snapshot["catalog_sha256"],
        "stored seed catalog drifted",
    )
    _require(
        len(catalog_raw) == snapshot["catalog_raw_octets"],
        "stored catalog size drifted",
    )

    generator = _load_generator()
    prospective = generator.build_catalog(ROOT)
    prospective_raw = generator._pretty_bytes(prospective)
    _require(
        len(prospective_raw) == snapshot["prospective_raw_octets"],
        "prospective seed size drifted",
    )
    _require(
        _sha256(prospective_raw) == snapshot["prospective_sha256"],
        "prospective seed bytes drifted",
    )
    _require(
        prospective["seed_catalog_id"] == snapshot["prospective_seed_catalog_id"],
        "prospective seed identity drifted",
    )
    _require(
        (catalog_raw != prospective_raw) is snapshot["catalog_stale"],
        "catalog staleness differs",
    )
    if control["gate_states"]["S1-A1"]["state"] == "ACCEPTED":
        _require(snapshot["catalog_stale"] is False, "accepted S1-A1 seed is stale")
        _require(snapshot["focused_failed"] == 0, "accepted S1-A1 has failures")
        _require(snapshot["focused_passed"] > 0, "accepted S1-A1 has no tests")
    operational_limit = snapshot["operational_output_maximum_octets"]
    _require(
        len(catalog_raw) <= operational_limit,
        "stored seed exceeds the operational output target",
    )
    _require(
        operational_limit - len(catalog_raw) == snapshot["operational_headroom_octets"],
        "operational seed headroom drifted",
    )
    f0 = {
        row["resource_name"]: row["ceiling_value"]
        for row in prospective["f0_seed_ceiling_catalog"][
            "ordered_platform_ceiling_records"
        ]
    }
    _require(
        f0["INDIVIDUAL_FILE_STRICT_UPPER_OCTETS"]
        == snapshot["strict_individual_file_upper_octets"],
        "strict individual-file cap drifted",
    )
    return control


def main() -> int:
    try:
        control = validate()
        snapshot = control["seed_snapshot"]
        print(
            "STAGE1_CONTROL_OK "
            f"active_gate={control['active_gate']} "
            f"formal_state={control['formal_stage1_state']} "
            f"catalog_stale={str(snapshot['catalog_stale']).lower()} "
            f"prospective_raw_octets={snapshot['prospective_raw_octets']} "
            f"strict_upper_octets={snapshot['strict_individual_file_upper_octets']}"
        )
        return 0
    except (ControlFailure, OSError, ValueError, KeyError, TypeError) as exc:
        print(f"STAGE1_CONTROL_INVALID: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
