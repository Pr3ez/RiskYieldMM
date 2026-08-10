from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CONSTRUCTOR_PATH = (
    ROOT / "scripts/tests/construct_raw_v8_step2_maximum_protocol_v2_"
    "case435_attainer_v49f.py"
)
CHECKER_PATH = (
    ROOT / "scripts/tests/check_raw_v8_step2_maximum_protocol_v2_"
    "case435_attainer_certificate_v49f.py"
)


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


constructor = _load("raw_v8_case435_attainer_constructor_test_v49f", CONSTRUCTOR_PATH)
checker = _load("raw_v8_case435_attainer_checker_test_v49f", CHECKER_PATH)


@pytest.fixture(scope="module")
def certificate():
    return constructor.construct(ROOT)


@pytest.fixture(scope="module")
def verified_report(certificate):
    return checker.verify(ROOT, certificate)


def _reseal(value):
    payload = {
        key: member
        for key, member in value.items()
        if key != "case435_attainer_certificate_id"
    }
    value["case435_attainer_certificate_id"] = hashlib.sha256(
        checker._canonical_bytes(
            {"domain": checker.CERTIFICATE_DOMAIN, "payload": payload}
        )
    ).hexdigest()
    return value


def _rejected(certificate, mutation):
    challenger = copy.deepcopy(certificate)
    mutation(challenger)
    _reseal(challenger)
    with pytest.raises(checker.CertificateError):
        checker.verify(ROOT, challenger)


def test_constructor_emits_a_legal_nonexact_c2_certificate(certificate):
    assert certificate["case435_attainer_certificate_id"] == (
        "1d801ba5b81a5e5ed27adfba2ff718fa24a7bd27e3cbf87ce5b603f653502dba"
    )
    assert certificate["p1_legal"] is True
    assert certificate["legal_attainer_constructed"] is True
    assert certificate["exactness_claimed"] is False
    assert certificate["correction_subgate"] == "A4-P6-C435-C2"
    assert certificate["next_subgate"] == "A4-P6-C435-C3"
    assert (
        certificate["construction_protocol"]["external_upper_channel_imported"] is False
    )
    assert certificate["construction_protocol"]["precomputed_witness_imported"] is False


def test_independent_checker_replays_complete_p1(verified_report):
    assert verified_report == {
        "case435_attainer_certificate_id": (
            "1d801ba5b81a5e5ed27adfba2ff718fa24a7bd27e3cbf87ce5b603f653502dba"
        ),
        "measured_attainer_canonical_octets": 257_887,
        "measured_attainer_canonical_sha256": (
            "f29bb04a79ff2c1ecff867224f70ae7b45c0d7d9c94960a6c81652d6b7b74bad"
        ),
        "p1_application_invocation_count": 137,
        "p1_rule_evaluation_count": 12_531,
        "p1_direct_expression_node_count": 125_431,
        "p1_legal": True,
        "exactness_claimed": False,
        "acceptance_state": "LEGAL_ATTAINER_CONSTRUCTED_EXACTNESS_JOIN_PENDING",
        "next_subgate": "A4-P6-C435-C3",
    }


def test_retained_witness_has_exact_causal_role_and_selector_shape(certificate):
    retained = certificate["retained_witness_context"]
    observations = retained["ordered_observations"]
    selector = retained["checkpoint_selector"]
    root = retained["target_observation_root"]
    assert len(observations) == root["observation_count"] == 67
    assert selector["selector_length"] == 64
    assert [row["observation_context"]["observation_role"] for row in observations] == (
        ["BEFORE_OPERATION"]
        + ["STABLE_CHECKPOINT"] * 64
        + ["AFTER_OPERATION", "OPERATION_AGGREGATE"]
    )
    assert certificate["measured_attainer"]["observation_sequence_position"] == 65
    assert (
        observations[64]["observation_id"]
        == certificate["measured_attainer"]["observation_id"]
    )


def test_selected_field_vector_is_complete_and_measured(certificate):
    records = certificate["ordered_selected_field_witness_records"]
    fields = certificate["retained_witness_context"]["ordered_observations"][64][
        "field_observations"
    ]
    assert len(records) == len(fields) == 185
    assert [row["field_position"] for row in records] == list(range(1, 186))
    assert [row["field_id"] for row in records] == [row["field_id"] for row in fields]
    assert sum(row["selected_canonical_octets"] for row in records) == 255_532


def test_constructor_and_checker_do_not_import_or_embed_c1_results():
    combined = CONSTRUCTOR_PATH.read_text() + CHECKER_PATH.read_text()
    forbidden = (
        "solve_raw_v8_step2_maximum_protocol_v2_case435_upper",
        "check_raw_v8_step2_maximum_protocol_v2_case435_upper",
        "c01bba7c5f5f19c12957493c7a0989dc3ddbc42306c0f059ee922c18341e62b4",
        "257887",
        "86f29eb6706b58d33db45d3a035e1f4b5bd78e50ba1347355d15d380e5856be9",
        "f29bb04a79ff2c1ecff867224f70ae7b45c0d7d9c94960a6c81652d6b7b74bad",
    )
    assert all(token not in combined for token in forbidden)


def test_strict_loader_rejects_duplicate_members():
    with pytest.raises(checker.CertificateError, match="duplicate JSON key"):
        checker._strict_load(b'{"a":1,"a":2}', "duplicate challenger")


def test_rejects_resealed_extra_top_level_member(certificate):
    _rejected(certificate, lambda value: value.__setitem__("unbound", True))


def test_rejects_resealed_authority_substitution(certificate):
    def mutate(value):
        first = next(iter(value["authority_sha256_by_path"]))
        value["authority_sha256_by_path"][first] = "0" * 64

    _rejected(certificate, mutate)


def test_rejects_resealed_imported_bound_claim(certificate):
    _rejected(
        certificate,
        lambda value: value["construction_protocol"].__setitem__(
            "external_upper_channel_imported", True
        ),
    )


def test_rejects_resealed_premature_exactness_claim(certificate):
    _rejected(certificate, lambda value: value.__setitem__("exactness_claimed", True))


def test_rejects_resealed_measured_octet_substitution(certificate):
    _rejected(
        certificate,
        lambda value: value["measured_attainer"].__setitem__(
            "canonical_octets", value["measured_attainer"]["canonical_octets"] + 1
        ),
    )


def test_rejects_resealed_selected_field_substitution(certificate):
    _rejected(
        certificate,
        lambda value: value["ordered_selected_field_witness_records"][0].__setitem__(
            "selected_canonical_octets", 0
        ),
    )


def test_rejects_resealed_observation_omission(certificate):
    _rejected(
        certificate,
        lambda value: value["retained_witness_context"]["ordered_observations"].pop(1),
    )


def test_rejects_resealed_outer_role_substitution(certificate):
    _rejected(
        certificate,
        lambda value: value["retained_witness_context"]["ordered_observations"][0][
            "observation_context"
        ].__setitem__("observation_role", "AFTER_OPERATION"),
    )


def test_rejects_resealed_receipt_vector_substitution(certificate):
    def mutate(value):
        execution = value["p1_execution_certificate"]
        execution["ordered_application_execution_receipts"][0]["application_name"] = (
            "APPLY/V2_OBSERVATION_AGGREGATE_REGISTRY_V1"
        )
        execution["receipt_vector_sha256"] = hashlib.sha256(
            checker._canonical_bytes(
                execution["ordered_application_execution_receipts"]
            )
        ).hexdigest()

    _rejected(certificate, mutate)


def test_rejects_unsealed_certificate_mutation(certificate):
    challenger = copy.deepcopy(certificate)
    challenger["next_subgate"] = "A4-P6-C435-D"
    with pytest.raises(checker.CertificateError, match="certificate identity differs"):
        checker.verify(ROOT, challenger)


def test_certificate_canonical_round_trip_is_stable(certificate):
    raw = checker._canonical_bytes(certificate)
    assert checker._strict_load(raw, "round-trip certificate") == certificate
    assert raw == checker._canonical_bytes(json.loads(raw))
