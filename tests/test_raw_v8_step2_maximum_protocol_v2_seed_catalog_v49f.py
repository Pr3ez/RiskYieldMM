"""Independent structural checks for the Raw-V8 Step-2 V2 seed catalog."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = Path(
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_seed_catalog_v49f.json"
)


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _catalog() -> dict[str, Any]:
    value = json.loads((ROOT / CATALOG_PATH).read_bytes())
    assert type(value) is dict
    return value


def _semantic_id(catalog: dict[str, Any], domain: str, payload: dict[str, Any]) -> str:
    return _sha256(
        _canonical_bytes(
            {
                "canonicalization_version": catalog["canonicalization_version"],
                "domain": domain,
                "payload": payload,
                "schema_version": catalog["measurement_schema_version"],
            }
        )
    )


def _identity(catalog: dict[str, Any], name: str) -> dict[str, Any]:
    matches = [
        row
        for row in catalog["ordered_identity_domain_records"]
        if row["identity_name"] == name
    ]
    assert len(matches) == 1
    return matches[0]


def test_seed_catalog_root_identity_and_authority_snapshots() -> None:
    catalog = _catalog()
    root_identity = _identity(catalog, "SEED_CATALOG")
    payload_names = root_identity["ordered_payload_member_names"]
    assert set(catalog) == {*payload_names, "seed_catalog_id"}
    payload = {name: catalog[name] for name in payload_names}
    assert catalog["seed_catalog_id"] == _semantic_id(
        catalog, root_identity["domain_literal"], payload
    )

    bindings = catalog["ordered_authority_binding_records"]
    assert len(bindings) == 17
    assert [row["authority_position"] for row in bindings] == list(range(1, 18))
    assert len({row["repository_relative_path"] for row in bindings}) == 17
    for row in bindings:
        raw = (ROOT / row["repository_relative_path"]).read_bytes()
        assert len(raw) == row["raw_octet_count"]
        assert _sha256(raw) == row["raw_sha256"]


def test_seed_catalog_subcatalog_identities_are_exact() -> None:
    catalog = _catalog()
    checks = (
        (
            "UNICODE_AUTHORITY_MANIFEST",
            "unicode_authority_manifest",
            "unicode_authority_manifest_id",
        ),
        (
            "F0_SEED_CEILING_CATALOG",
            "f0_seed_ceiling_catalog",
            "f0_seed_ceiling_catalog_id",
        ),
        (
            "RESOURCE_METRIC_CATALOG",
            "resource_metric_catalog",
            "resource_metric_catalog_id",
        ),
        ("RECURRENCE_CATALOG", "recurrence_catalog", "recurrence_catalog_id"),
        ("LOGICAL_EVENT_CATALOG", "logical_event_catalog", "logical_event_catalog_id"),
        ("COUNT_CASE_UNIVERSE", "case_universe_catalog", "case_universe_catalog_id"),
        (
            "LOGICAL_PLAN_RECIPE_CATALOG",
            "logical_plan_recipe_catalog",
            "logical_plan_recipe_catalog_id",
        ),
    )
    for identity_name, catalog_member, id_member in checks:
        value = catalog[catalog_member]
        identity = _identity(catalog, identity_name)
        member_names = identity["ordered_payload_member_names"]
        assert set(value) == {*member_names, id_member}
        payload = {name: value[name] for name in member_names}
        assert value[id_member] == _semantic_id(
            catalog, identity["domain_literal"], payload
        )


def test_logical_templates_are_closed_postorder_programs() -> None:
    catalog = _catalog()
    recurrence = catalog["recurrence_catalog"]
    kernel_kinds = {
        row["derivation_kind"]
        for row in recurrence["ordered_derivation_kernel_records"]
    }
    recipes = catalog["logical_plan_recipe_catalog"]
    templates = recipes["ordered_logical_plan_templates"]
    assert len(templates) == 66
    assert [row["template_position"] for row in templates] == list(range(1, 67))
    assert sum(len(row["ordered_template_steps"]) for row in templates) == 1_647

    template_ids: set[str] = set()
    identity = _identity(catalog, "LOGICAL_PLAN_TEMPLATE")
    step_identity = _identity(catalog, "LOGICAL_DERIVATION_STEP")
    for template in templates:
        steps = template["ordered_template_steps"]
        assert template["root_step_position"] == len(steps)
        assert [row["template_step_position"] for row in steps] == list(
            range(1, len(steps) + 1)
        )
        for step in steps:
            position = step["template_step_position"]
            assert step["derivation_kind"] in kernel_kinds
            assert all(
                type(child) is int and 1 <= child < position
                for child in step["ordered_child_step_positions"]
            )
            step_record = dict(step)
            step_id = step_record.pop("logical_derivation_step_id")
            assert set(step_record) == set(
                step_identity["ordered_payload_member_names"]
            )
            assert step_id == _semantic_id(
                catalog, step_identity["domain_literal"], step_record
            )
        payload = {
            name: template[name] for name in identity["ordered_payload_member_names"]
        }
        assert template["logical_plan_template_id"] == _semantic_id(
            catalog, identity["domain_literal"], payload
        )
        template_ids.add(template["logical_plan_template_id"])
    assert len(template_ids) == 66


def test_all_475_cases_have_one_closed_plan_binding() -> None:
    catalog = _catalog()
    cases = catalog["case_universe_catalog"]["ordered_case_bindings"]
    recipe = catalog["logical_plan_recipe_catalog"]
    bindings = recipe["ordered_case_plan_bindings"]
    plans = recipe["ordered_logical_count_plan_records"]
    binding_schema = recipe["case_plan_binding_schema"]
    assert binding_schema["ordered_member_names"] == [
        "case_position",
        "logical_count_plan_position",
        "logical_count_plan_id",
    ]
    assert binding_schema["unknown_or_extra_member_policy"] == "REJECT"
    template_ids = {
        row["logical_plan_template_id"]
        for row in recipe["ordered_logical_plan_templates"]
    }
    plan_identity = _identity(catalog, "LOGICAL_COUNT_PLAN")
    recurrence = catalog["recurrence_catalog"]
    template_by_id = {
        row["logical_plan_template_id"]: row
        for row in recipe["ordered_logical_plan_templates"]
    }
    named_constraint_relaxation_id = next(
        row["safe_relaxation_rule_id"]
        for row in recurrence["ordered_safe_relaxation_records"]
        if row["relaxation_name"] == "DROP_COMPLETE_NAMED_CONSTRAINT_TO_SUPERSET_V1"
    )
    assert len(cases) == len(bindings) == len(plans) == 475
    assert [row["case_position"] for row in cases] == list(range(1, 476))
    assert [row["case_position"] for row in bindings] == list(range(1, 476))
    assert [row["case_position"] for row in plans] == list(range(1, 476))
    for case, binding, plan in zip(cases, bindings, plans, strict=True):
        is_local_profile_analytic = case["case_position"] == 69
        assert set(binding) == set(binding_schema["ordered_member_names"])
        assert binding["case_position"] == case["case_position"]
        assert binding["logical_count_plan_position"] == case["case_position"]
        assert binding["logical_count_plan_id"] == plan["logical_count_plan_id"]
        assert plan["case_kind"] == case["case_kind"]
        if case["case_position"] < 475:
            assert plan["logical_plan_template_id"] in template_ids
        else:
            assert plan["logical_plan_template_id"] is None
        required_relaxation_ids: set[str] = set()
        if (
            plan["logical_plan_template_id"] is not None
            and not is_local_profile_analytic
        ):
            required_relaxation_ids.update(
                template_by_id[plan["logical_plan_template_id"]][
                    "ordered_required_safe_relaxation_rule_ids"
                ]
            )
        if (
            67 <= case["case_position"] <= 474
            and not is_local_profile_analytic
            and (
                plan["scope_summary"]["application_invocation_count"] > 0
                or plan["scope_summary"]["cross_rule_evaluation_count"] > 0
            )
        ):
            required_relaxation_ids.add(named_constraint_relaxation_id)
        ordered_required_relaxation_ids = [
            row["safe_relaxation_rule_id"]
            for row in recurrence["ordered_safe_relaxation_records"]
            if row["safe_relaxation_rule_id"] in required_relaxation_ids
        ]
        plan_payload = {
            "logical_count_plan_version": plan_identity["version_literal"],
            "case_position": case["case_position"],
            "case_kind": case["case_kind"],
            "case_binding": case["case_binding"],
            "upper_bound_mode": (
                "LEGAL_DOMAIN_SUPERSET_WITH_LEGAL_ATTAINMENT"
                if case["case_position"] <= 474 and not is_local_profile_analytic
                else "EXACT_LEGAL_DOMAIN"
            ),
            "recurrence_catalog_id": recurrence["recurrence_catalog_id"],
            "ordered_safe_relaxation_rule_ids": (
                ordered_required_relaxation_ids
                if case["case_position"] <= 474 and not is_local_profile_analytic
                else []
            ),
            "logical_plan_template_id": plan["logical_plan_template_id"],
            "profile_conditioning_program_id": plan["profile_conditioning_program_id"],
            "local_analytic_catalog_id": (
                None
                if case["case_position"] <= 474
                else recurrence["local_shutdown_analytic_catalog"][
                    "local_shutdown_analytic_catalog_id"
                ]
            ),
            "logical_root_reference": (
                {
                    "root_kind": "PROFILE_CONDITIONING_PROGRAM",
                    "root_id": plan["profile_conditioning_program_id"],
                }
                if plan["profile_conditioning_program_id"] is not None
                else {
                    "root_kind": (
                        "LOGICAL_PLAN_TEMPLATE"
                        if plan["logical_plan_template_id"] is not None
                        else "LOCAL_SHUTDOWN_ANALYTIC_CATALOG"
                    ),
                    "root_id": (
                        plan["logical_plan_template_id"]
                        if plan["logical_plan_template_id"] is not None
                        else recurrence["local_shutdown_analytic_catalog"][
                            "local_shutdown_analytic_catalog_id"
                        ]
                    ),
                }
            ),
            "scope_summary": plan["scope_summary"],
            "root_step_position": (
                None
                if plan["logical_plan_template_id"] is None
                else template_by_id[plan["logical_plan_template_id"]][
                    "root_step_position"
                ]
            ),
        }
        assert set(plan_payload) == set(plan_identity["ordered_payload_member_names"])
        assert plan == {
            **plan_payload,
            "logical_count_plan_id": _semantic_id(
                catalog, plan_identity["domain_literal"], plan_payload
            ),
        }
        assert plan["logical_count_plan_id"] == _semantic_id(
            catalog, plan_identity["domain_literal"], plan_payload
        )
    assert (
        sum(row["scope_summary"]["internal_scope_case_count"] for row in plans[66:474])
        == 475
    )
    assert (
        sum(row["scope_summary"]["synthetic_axis_count"] for row in plans[66:474]) == 33
    )


def test_metric_and_event_catalogs_cover_exact_positions() -> None:
    catalog = _catalog()
    metrics = catalog["resource_metric_catalog"]["ordered_metric_records"]
    assert len(metrics) == 18
    assert [row["metric_position"] for row in metrics] == list(range(1, 19))
    programs = catalog["logical_event_catalog"]["ordered_event_kind_records"]
    assert [row["event_kind_position"] for row in programs] == list(
        range(1, len(programs) + 1)
    )
    covered = {
        update["metric_position"]
        for program in programs
        for update in program["ordered_metric_update_program"]
    }
    assert covered == set(range(1, 19))


def test_local_shutdown_exact_boundary_and_saturation_construction() -> None:
    catalog = _catalog()
    local = catalog["recurrence_catalog"]["local_shutdown_analytic_catalog"]
    identity = _identity(catalog, "LOCAL_SHUTDOWN_ANALYTIC_CATALOG")
    payload = {name: local[name] for name in identity["ordered_payload_member_names"]}
    assert set(local) == {
        *identity["ordered_payload_member_names"],
        "local_shutdown_analytic_catalog_id",
    }
    assert local["local_shutdown_analytic_catalog_id"] == _semantic_id(
        catalog, identity["domain_literal"], payload
    )
    assert local["baseline_result_canonical_octets"] == 2_504
    assert local["baseline_attainable_maximum_octets"] == 2_581
    assert local["batch_unsaturated_program"] == {
        "opcode": "PIECEWISE_AFFINE_DECIMAL_WIDTH_V1",
        "constant_octets": 2_312,
        "linear_variable": "MAXIMUM_TERMINAL_INGRESS_BATCHES",
        "linear_coefficient": 268,
        "decimal_width_coefficient": 1,
        "valid_minimum": 1,
        "valid_maximum": 11_731,
    }
    assert local["winning_mutated_value"] == 1_948
    assert local["predecessor_attainable_maximum_octets"] == 524_112
    assert local["winner_attainable_maximum_octets"] == 524_380
    assert local["winning_absolute_delta"] == 1_947
    proof = local["batch_saturation_proof"]
    assert proof["first_saturated_batch_limit"] == 11_732
    assert local["fixed_result_skeleton_octets"] == 2_205
    assert proof["attaining_body_octets"] == 3_145_728
    assert proof["attaining_wrapper_octets"] == 3_146_277


def test_local_shutdown_unsaturated_formula_reconstructs_fixture_bytes() -> None:
    inventory = json.loads(
        (ROOT / "tests/raw_v8_step2_inventory_v4_v49f.json").read_bytes()
    )
    fixture = inventory["fixture_records"]["operation_results"]["LOCAL_SHUTDOWN"]
    spec = inventory["fixture_records"]["operation_specs"]["LOCAL_SHUTDOWN"]["spec"]
    array_names = (
        "ordered_terminal_ingress_read_attempt_event_ids",
        "ordered_terminal_ingress_read_result_event_ids",
        "ordered_terminal_raw_ingress_commit_ids",
        "ordered_terminal_raw_ingress_actor_event_ids",
    )
    counter_map = {
        "final_terminal_ingress_ciphertext_octets": "maximum_terminal_ingress_ciphertext_octets",
        "final_terminal_ingress_plaintext_octets": "maximum_terminal_ingress_plaintext_octets",
        "final_terminal_socket_receive_call_count": "maximum_terminal_socket_receive_calls",
        "final_terminal_tls_record_count": "maximum_terminal_tls_records",
        "final_terminal_tls_unwrap_iteration_count": "maximum_terminal_tls_unwrap_iterations",
        "final_terminal_zero_progress_iteration_count": "maximum_terminal_zero_progress_iterations",
        "final_terminal_ingress_parser_unit_count": "maximum_terminal_ingress_parser_units",
        "final_terminal_ingress_automatic_output_count": "maximum_terminal_ingress_automatic_outputs",
        "final_websocket_send_attempt_count": "maximum_websocket_send_attempts",
        "final_tls_control_send_attempt_count": "maximum_tls_control_send_attempts",
        "final_peer_shutdown_poll_count": "maximum_peer_shutdown_polls",
    }
    for batch_count, expected_wrapper_octets in (
        (1, 2_581),
        (1_947, 524_112),
        (1_948, 524_380),
    ):
        candidate = copy.deepcopy(fixture)
        body = candidate["result"]
        values = [f"{ordinal:064x}" for ordinal in range(batch_count)]
        for name in array_names:
            body[name] = values.copy()
        body["ordered_terminal_parser_transition_event_ids"] = ["f" * 64]
        body["local_shutdown_deadline_evidence_event_id"] = "e" * 64
        body["shutdown_trace_step_count"] = 9_007_199_254_740_991
        body["final_terminal_ingress_batch_count"] = batch_count
        for result_name, spec_name in counter_map.items():
            body[result_name] = spec[spec_name]
        assert len(_canonical_bytes(candidate)) == expected_wrapper_octets
        assert expected_wrapper_octets == 2_312 + 268 * batch_count + len(
            str(batch_count)
        )
