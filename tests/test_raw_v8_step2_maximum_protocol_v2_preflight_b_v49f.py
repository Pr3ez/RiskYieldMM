"""Independent acceptance surface for the flat-ledger S1-A2 preflight B."""

from __future__ import annotations

import ast
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
PROGRAM = ROOT / "scripts/tests/preflight_raw_v8_step2_maximum_protocol_v2_b_v49f.py"
SEED = ROOT / "scripts/tests/raw_v8_step2_maximum_protocol_v2_seed_catalog_v49f.json"
CONTRACT = (
    ROOT / "scripts/tests/raw_v8_step2_maximum_protocol_v2_preflight_contract_v49f.json"
)
U128_MAX = (1 << 128) - 1


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()


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
    ).encode()


def _hash(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _identity(domain: str, payload: Any) -> str:
    return _hash(_canonical({"domain": domain, "payload": payload}))


def _invoke(target: Path) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        [
            sys.executable,
            "-I",
            "-S",
            "-B",
            str(PROGRAM),
            "--seed",
            str(SEED),
            "--semantic-output",
            str(target),
        ],
        cwd=ROOT,
        env={
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONHASHSEED": "0",
        },
        capture_output=True,
        check=False,
        timeout=600,
    )


@pytest.fixture(scope="module")
def report(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    directory = tmp_path_factory.mktemp("raw-v8-step2-preflight-b")
    target = directory / "semantic.json"
    result = _invoke(target)
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    assert result.stdout == result.stderr == b""
    raw = target.read_bytes()
    value = json.loads(raw)
    assert raw == _pretty(value)
    return value


def test_preflight_b_source_is_separate_and_allowlisted() -> None:
    assert PROGRAM.is_file()
    source = PROGRAM.read_text(encoding="utf-8")
    tree = ast.parse(source)
    contract = json.loads(CONTRACT.read_bytes())
    policy = contract["implementation_separation_policy"]
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.module is not None
            imported.add(node.module.split(".", 1)[0])
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in policy["forbidden_ast_call_names"]
    assert imported <= set(policy["allowed_preflight_standard_library_import_roots"])
    assert imported.isdisjoint(policy["forbidden_import_roots"])
    assert policy["algorithm_markers"]["B"] in source
    assert "preflight_raw_v8_step2_maximum_protocol_v2_a_v49f" not in source
    assert "generate_raw_v8_step2_maximum_protocol_v2_seed_catalog_v49f" not in source


def test_preflight_b_closes_all_case_and_payload_identities(
    report: dict[str, Any],
) -> None:
    contract = json.loads(CONTRACT.read_bytes())
    seed_raw = SEED.read_bytes()
    seed = json.loads(seed_raw)
    schema = contract["report_contract"]
    payload_members = schema["preflight_semantic_payload_schema"][
        "ordered_member_names"
    ]
    case_members = schema["case_result_record_schema"]["ordered_member_names"]
    assert set(report) == set(payload_members)
    assert report["seed_catalog_raw_octets"] == len(seed_raw)
    assert report["seed_catalog_raw_sha256"] == _hash(seed_raw)
    assert report["seed_catalog_id"] == seed["seed_catalog_id"]
    assert report["contract_id"] == contract["contract_id"]
    cases = report["ordered_case_result_records"]
    plans = seed["logical_plan_recipe_catalog"]["ordered_logical_count_plan_records"]
    metrics = seed["resource_metric_catalog"]["ordered_metric_records"]
    assert report["verifier_owned_scope_case_count"] == len(cases) == 475
    for position, (case, plan) in enumerate(zip(cases, plans, strict=True), 1):
        assert set(case) == set(case_members)
        assert case["case_position"] == position
        assert case["case_kind"] == plan["case_kind"]
        assert case["case_binding"] == plan["case_binding"]
        assert case["logical_count_plan_id"] == plan["logical_count_plan_id"]
        assert case["result_status"] == "ACCEPT"
        assert len(case["derivation_event_stream_sha256"]) == 64
        assert len(case["ordered_resource_measurements"]) == 18
        for measurement, metric in zip(
            case["ordered_resource_measurements"], metrics, strict=True
        ):
            assert measurement["metric_position"] == metric["metric_position"]
            assert measurement["metric_name"] == metric["metric_name"]
            value = measurement["measured_value"]
            assert type(value) is int and 0 <= value <= U128_MAX
            assert value <= metric["per_case_f0_ceiling"]
        without_id = {
            name: case[name] for name in case_members if name != "case_result_record_id"
        }
        assert case["case_result_record_id"] == _identity(
            schema["identity_programs"]["case_result_record_id"]["domain_literal"],
            without_id,
        )
    count_projection = [
        {name: case[name] for name in case_members if name != "case_result_record_id"}
        for case in cases
    ]
    assert report["semantic_count_vector_sha256"] == _identity(
        schema["identity_programs"]["semantic_count_vector_sha256"]["domain_literal"],
        [*count_projection, *report["ordered_metric_summary_records"]],
    )
    without_id = {
        name: report[name] for name in payload_members if name != "semantic_payload_id"
    }
    assert report["semantic_payload_id"] == _identity(
        schema["identity_programs"]["semantic_payload_id"]["domain_literal"],
        without_id,
    )


def test_preflight_b_plan_columns_reconcile_without_result_vector(
    report: dict[str, Any],
) -> None:
    seed = json.loads(SEED.read_bytes())
    recipe = seed["logical_plan_recipe_catalog"]
    templates = {
        row["logical_plan_template_id"]: row
        for row in recipe["ordered_logical_plan_templates"]
    }
    local = seed["recurrence_catalog"]["local_shutdown_analytic_catalog"]
    local_intrinsic = next(
        row["ordered_authority_values"]
        for row in local["controller_metric_count_program"][
            "ordered_exact_non_byte_metric_records"
        ]
        if row["metric_position"] == 12
    )
    for case, plan in zip(
        report["ordered_case_result_records"],
        recipe["ordered_logical_count_plan_records"],
        strict=True,
    ):
        column = [
            row["measured_value"] for row in case["ordered_resource_measurements"]
        ]
        assert column[0] == 1
        if plan["logical_plan_template_id"] is None:
            expected = [
                local["fixed_controller_transition_count"],
                local["fixed_controller_state_count"],
                local["fixed_controller_transition_count"],
                local["fixed_controller_transition_count"],
                0,
                local["fixed_controller_state_count"],
            ]
            assert column[1:7] == expected
            assert column[11] == 2 * len(local_intrinsic)
            assert column[14] == 1
            assert column[15] == local["fixed_controller_transition_count"]
        else:
            steps = templates[plan["logical_plan_template_id"]][
                "ordered_template_steps"
            ]
            assert column[1] == sum(
                step["logical_descriptor_occurrence_count"] for step in steps
            )
            assert column[2] == len(steps)
            assert column[3] == sum(step["physical_transition_count"] for step in steps)
            assert column[4] == sum(
                step["logical_unbatched_transition_equivalent_count"] for step in steps
            )
            assert column[5] == sum(
                step["physical_batch_application_count"] for step in steps
            )
            assert column[6] == len(steps)
            assert column[11] == sum(
                len(step["ordered_intrinsic_rule_ids"]) for step in steps
            )
        assert column[12] == plan["scope_summary"]["cross_rule_evaluation_count"]
        assert column[13] == plan["scope_summary"]["application_invocation_count"]


def test_preflight_b_summary_columns_are_exact(report: dict[str, Any]) -> None:
    seed = json.loads(SEED.read_bytes())
    metrics = seed["resource_metric_catalog"]["ordered_metric_records"]
    cases = report["ordered_case_result_records"]
    for summary, metric in zip(
        report["ordered_metric_summary_records"], metrics, strict=True
    ):
        position = metric["metric_position"]
        values = [
            case["ordered_resource_measurements"][position - 1]["measured_value"]
            for case in cases
        ]
        maximum = max(values)
        expected_full = (
            sum(values) if metric["full_run_aggregation"] == "SUM" else maximum
        )
        assert summary == {
            "metric_position": position,
            "metric_name": metric["metric_name"],
            "full_run_aggregation": metric["full_run_aggregation"],
            "full_run_value": expected_full,
            "maximum_case_value": maximum,
            "ordered_maximum_case_positions": [
                case_position
                for case_position, value in enumerate(values, 1)
                if value == maximum
            ],
        }
        assert expected_full <= metric["full_run_f0_ceiling"]


def test_preflight_b_repeats_exact_bytes(
    report: dict[str, Any], tmp_path: Path
) -> None:
    target = tmp_path / "semantic.json"
    result = _invoke(target)
    assert result.returncode == 0
    assert result.stdout == result.stderr == b""
    assert target.read_bytes() == _pretty(report)


def test_preflight_b_rejects_occupied_parent_without_leftover(tmp_path: Path) -> None:
    occupied = tmp_path / "semantic.json"
    occupied.write_bytes(b"occupied")
    result = _invoke(occupied)
    assert result.returncode != 0
    assert result.stdout == b""
    assert result.stderr.startswith(b"RAW_V8_STEP2_MAXIMUM_PROTOCOL_V2_PREFLIGHT_B_")
    assert result.stderr.count(b"\n") == 1
    assert occupied.read_bytes() == b"occupied"
    assert [path.name for path in tmp_path.iterdir()] == ["semantic.json"]
