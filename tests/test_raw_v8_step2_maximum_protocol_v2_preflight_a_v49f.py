"""Independent acceptance surface for S1-A2 preflight A.

The implementation is a standalone consumer of the frozen seed.  These tests
check its static separation, fail-closed CLI, deterministic publication, and
the complete semantic report without importing the implementation.
"""

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
SCRIPT = ROOT / "scripts/tests/preflight_raw_v8_step2_maximum_protocol_v2_a_v49f.py"
SEED = ROOT / "scripts/tests/raw_v8_step2_maximum_protocol_v2_seed_catalog_v49f.json"
CONTRACT = (
    ROOT / "scripts/tests/raw_v8_step2_maximum_protocol_v2_preflight_contract_v49f.json"
)
U128_MAX = (1 << 128) - 1


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _pretty_bytes(value: Any) -> bytes:
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


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _domain_id(domain: str, payload: Any) -> str:
    return _sha256(_canonical_bytes({"domain": domain, "payload": payload}))


def _run(output: Path) -> subprocess.CompletedProcess[bytes]:
    environment = {
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONHASHSEED": "0",
    }
    return subprocess.run(
        [
            sys.executable,
            "-I",
            "-S",
            "-B",
            str(SCRIPT),
            "--seed",
            str(SEED),
            "--semantic-output",
            str(output),
        ],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        check=False,
        timeout=600,
    )


@pytest.fixture(scope="module")
def report(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    directory = tmp_path_factory.mktemp("raw-v8-step2-preflight-a")
    output = directory / "semantic.json"
    completed = _run(output)
    assert completed.returncode == 0, completed.stderr.decode("utf-8", "replace")
    assert completed.stdout == b""
    assert completed.stderr == b""
    raw = output.read_bytes()
    value = json.loads(raw)
    assert type(value) is dict
    assert raw == _pretty_bytes(value)
    return value


def test_preflight_a_source_is_standalone_and_allowlisted() -> None:
    assert SCRIPT.is_file()
    source = SCRIPT.read_text(encoding="utf-8")
    tree = ast.parse(source)
    contract = json.loads(CONTRACT.read_bytes())
    separation = contract["implementation_separation_policy"]
    allowed = set(separation["allowed_preflight_standard_library_import_roots"])
    forbidden = set(separation["forbidden_import_roots"])
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.module is not None
            imported.add(node.module.split(".", 1)[0])
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in separation["forbidden_ast_call_names"]
    assert imported <= allowed
    assert imported.isdisjoint(forbidden)
    assert separation["algorithm_markers"]["A"] in source
    assert "preflight_raw_v8_step2_maximum_protocol_v2_b_v49f" not in source
    assert "generate_raw_v8_step2_maximum_protocol_v2_seed_catalog_v49f" not in source


def test_preflight_a_emits_complete_identity_closed_payload(
    report: dict[str, Any],
) -> None:
    contract = json.loads(CONTRACT.read_bytes())
    seed_raw = SEED.read_bytes()
    seed = json.loads(seed_raw)
    schema = contract["report_contract"]
    assert set(report) == set(
        schema["preflight_semantic_payload_schema"]["ordered_member_names"]
    )
    assert (
        report["preflight_semantic_payload_version"]
        == schema["version_literals"]["preflight_semantic_payload_version"]
    )
    assert report["canonicalization_version"] == seed["canonicalization_version"]
    assert report["measurement_schema_version"] == seed["measurement_schema_version"]
    assert report["contract_id"] == contract["contract_id"]
    assert report["protocol_version"] == seed["protocol_version"]
    assert (
        report["protocol_counting_semantics_id"]
        == seed["protocol_counting_semantics_id"]
    )
    assert report["seed_catalog_raw_octets"] == len(seed_raw)
    assert report["seed_catalog_raw_sha256"] == _sha256(seed_raw)
    assert report["seed_catalog_id"] == seed["seed_catalog_id"]
    for root in contract["input_authority"]["ordered_required_semantic_root_records"]:
        member = f"{root['root_name']}_id"
        assert report[member] == root["expected_id"]

    cases = report["ordered_case_result_records"]
    plans = seed["logical_plan_recipe_catalog"]["ordered_logical_count_plan_records"]
    metrics = seed["resource_metric_catalog"]["ordered_metric_records"]
    assert report["verifier_owned_scope_case_count"] == len(cases) == len(plans) == 475
    assert [row["case_position"] for row in cases] == list(range(1, 476))
    for case, plan in zip(cases, plans, strict=True):
        assert set(case) == set(
            schema["case_result_record_schema"]["ordered_member_names"]
        )
        assert case["case_kind"] == plan["case_kind"]
        assert case["case_binding"] == plan["case_binding"]
        assert case["logical_count_plan_id"] == plan["logical_count_plan_id"]
        assert case["result_status"] == "ACCEPT"
        measurements = case["ordered_resource_measurements"]
        assert len(measurements) == 18
        for measurement, metric in zip(measurements, metrics, strict=True):
            assert set(measurement) == set(
                schema["resource_measurement_record_schema"]["ordered_member_names"]
            )
            assert measurement["metric_position"] == metric["metric_position"]
            assert measurement["metric_name"] == metric["metric_name"]
            value = measurement["measured_value"]
            assert type(value) is int and 0 <= value <= U128_MAX
            assert value <= metric["per_case_f0_ceiling"]
        assert len(case["derivation_event_stream_sha256"]) == 64
        case_payload = {
            name: case[name]
            for name in schema["case_result_record_schema"]["ordered_member_names"]
            if name != "case_result_record_id"
        }
        assert case["case_result_record_id"] == _domain_id(
            schema["identity_programs"]["case_result_record_id"]["domain_literal"],
            case_payload,
        )

    count_vector = [
        {
            name: case[name]
            for name in schema["case_result_record_schema"]["ordered_member_names"]
            if name != "case_result_record_id"
        }
        for case in cases
    ]
    assert report["semantic_count_vector_sha256"] == _domain_id(
        schema["identity_programs"]["semantic_count_vector_sha256"]["domain_literal"],
        [*count_vector, *report["ordered_metric_summary_records"]],
    )

    payload_without_id = {
        name: report[name]
        for name in schema["preflight_semantic_payload_schema"]["ordered_member_names"]
        if name != "semantic_payload_id"
    }
    assert report["semantic_payload_id"] == _domain_id(
        schema["identity_programs"]["semantic_payload_id"]["domain_literal"],
        payload_without_id,
    )


def test_preflight_a_simple_metrics_reconcile_independently(
    report: dict[str, Any],
) -> None:
    seed = json.loads(SEED.read_bytes())
    recipe = seed["logical_plan_recipe_catalog"]
    template_by_id = {
        row["logical_plan_template_id"]: row
        for row in recipe["ordered_logical_plan_templates"]
    }
    local = seed["recurrence_catalog"]["local_shutdown_analytic_catalog"]
    for case, plan in zip(
        report["ordered_case_result_records"],
        recipe["ordered_logical_count_plan_records"],
        strict=True,
    ):
        values = {
            row["metric_position"]: row["measured_value"]
            for row in case["ordered_resource_measurements"]
        }
        assert values[1] == 1
        if plan["logical_plan_template_id"] is None:
            assert values[2] == local["fixed_controller_transition_count"]
            assert values[3] == local["fixed_controller_state_count"]
            assert values[4] == local["fixed_controller_transition_count"]
            assert values[5] == local["fixed_controller_transition_count"]
            assert values[6] == 0
            assert values[7] == local["fixed_controller_state_count"]
            intrinsic_ids = next(
                row["ordered_authority_values"]
                for row in local["controller_metric_count_program"][
                    "ordered_exact_non_byte_metric_records"
                ]
                if row["metric_position"] == 12
            )
            assert values[12] == 2 * len(intrinsic_ids)
            assert values[15] == 1
            assert values[16] == local["fixed_controller_transition_count"]
        else:
            steps = template_by_id[plan["logical_plan_template_id"]][
                "ordered_template_steps"
            ]
            assert values[2] == sum(
                row["logical_descriptor_occurrence_count"] for row in steps
            )
            assert values[3] == len(steps)
            assert values[4] == sum(row["physical_transition_count"] for row in steps)
            assert values[5] == sum(
                row["logical_unbatched_transition_equivalent_count"] for row in steps
            )
            assert values[6] == sum(
                row["physical_batch_application_count"] for row in steps
            )
            assert values[7] == len(steps)
            assert values[12] == sum(
                len(row["ordered_intrinsic_rule_ids"]) for row in steps
            )
            depths: list[int] = []
            iterations: list[int] = []
            for step in steps:
                children = step["ordered_child_step_positions"]
                depths.append(
                    1
                    if not children
                    else 1 + max(depths[child - 1] for child in children)
                )
                kind = step["derivation_kind"]
                if kind == "ASSOCIATIVE_HOMOGENEOUS_RUN_BATCH":
                    maximum_items = step["recurrence_parameters"]["maximum_items"]
                    iteration = (
                        0 if maximum_items <= 1 else (maximum_items - 1).bit_length()
                    )
                elif kind == "ARRAY_STREAM_FOLD":
                    iteration = step["recurrence_parameters"]["maximum_items"]
                elif kind == "APPLICATION_SCHEDULE_COUNT":
                    iteration = len(
                        step["recurrence_parameters"][
                            "ordered_application_invocation_records"
                        ]
                    )
                else:
                    iteration = step["physical_transition_count"]
                iterations.append(iteration)
            assert values[15] == max(depths)
            assert values[16] == max(
                max(iterations), plan["scope_summary"]["application_invocation_count"]
            )
        assert values[13] == plan["scope_summary"]["cross_rule_evaluation_count"]
        assert values[14] == plan["scope_summary"]["application_invocation_count"]


def test_preflight_a_summaries_reconcile(report: dict[str, Any]) -> None:
    seed = json.loads(SEED.read_bytes())
    metric_rows = seed["resource_metric_catalog"]["ordered_metric_records"]
    cases = report["ordered_case_result_records"]
    summaries = report["ordered_metric_summary_records"]
    assert len(summaries) == 18
    for summary, metric in zip(summaries, metric_rows, strict=True):
        assert set(summary) == {
            "metric_position",
            "metric_name",
            "full_run_aggregation",
            "full_run_value",
            "maximum_case_value",
            "ordered_maximum_case_positions",
        }
        values = [
            case["ordered_resource_measurements"][metric["metric_position"] - 1][
                "measured_value"
            ]
            for case in cases
        ]
        maximum = max(values)
        aggregate = sum(values) if metric["full_run_aggregation"] == "SUM" else maximum
        assert summary == {
            "metric_position": metric["metric_position"],
            "metric_name": metric["metric_name"],
            "full_run_aggregation": metric["full_run_aggregation"],
            "full_run_value": aggregate,
            "maximum_case_value": maximum,
            "ordered_maximum_case_positions": [
                position for position, value in enumerate(values, 1) if value == maximum
            ],
        }
        assert aggregate <= metric["full_run_f0_ceiling"]


def test_preflight_a_is_byte_deterministic(
    report: dict[str, Any], tmp_path: Path
) -> None:
    output = tmp_path / "semantic.json"
    completed = _run(output)
    assert completed.returncode == 0
    assert completed.stdout == completed.stderr == b""
    assert output.read_bytes() == _pretty_bytes(report)


def test_preflight_a_fails_closed_without_partial_output(tmp_path: Path) -> None:
    output = tmp_path / "semantic.json"
    output.write_text("occupied", encoding="utf-8")
    completed = _run(output)
    assert completed.returncode != 0
    assert completed.stdout == b""
    assert completed.stderr.count(b"\n") == 1
    assert completed.stderr.startswith(b"RAW_V8_STEP2_MAXIMUM_PROTOCOL_V2_PREFLIGHT_A_")
    assert output.read_text(encoding="utf-8") == "occupied"
    assert sorted(path.name for path in tmp_path.iterdir()) == ["semantic.json"]
