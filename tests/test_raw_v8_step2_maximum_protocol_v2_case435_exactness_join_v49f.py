from __future__ import annotations

import ast
import copy
import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
UPPER_PATH = (
    ROOT / "scripts/tests/solve_raw_v8_step2_maximum_protocol_v2_case435_upper_v49f.py"
)
ATTAINER_PATH = (
    ROOT / "scripts/tests/construct_raw_v8_step2_maximum_protocol_v2_"
    "case435_attainer_v49f.py"
)
JOIN_PATH = (
    ROOT / "scripts/tests/join_raw_v8_step2_maximum_protocol_v2_"
    "case435_exactness_v49f.py"
)
CHECKER_PATH = (
    ROOT / "scripts/tests/check_raw_v8_step2_maximum_protocol_v2_"
    "case435_exactness_certificate_v49f.py"
)


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


upper_module = _load("raw_v8_case435_c3_upper_test_v49f", UPPER_PATH)
attainer_module = _load("raw_v8_case435_c3_attainer_test_v49f", ATTAINER_PATH)
join_module = _load("raw_v8_case435_c3_join_test_v49f", JOIN_PATH)
checker_module = _load("raw_v8_case435_c3_checker_test_v49f", CHECKER_PATH)


@pytest.fixture(scope="module")
def upper():
    return upper_module.solve(ROOT)


@pytest.fixture(scope="module")
def attainer():
    return attainer_module.construct(ROOT)


@pytest.fixture(scope="module")
def joined(upper, attainer):
    return join_module.join(ROOT, upper, attainer)


def _reseal(value, identity_member, domain):
    value[identity_member] = hashlib.sha256(
        join_module._canonical_bytes(
            {
                "domain": domain,
                "payload": {
                    key: member
                    for key, member in value.items()
                    if key != identity_member
                },
            }
        )
    ).hexdigest()
    return value[identity_member]


def _reseal_upper(value):
    return _reseal(
        value,
        "case435_upper_certificate_id",
        join_module.UPPER_CERTIFICATE_DOMAIN,
    )


def _reseal_attainer(value):
    return _reseal(
        value,
        "case435_attainer_certificate_id",
        join_module.ATTAINER_CERTIFICATE_DOMAIN,
    )


def _reseal_join(value):
    return _reseal(
        value,
        "case435_exactness_join_certificate_id",
        join_module.JOIN_DOMAIN,
    )


def test_c3_join_accepts_only_the_two_frozen_channels(joined):
    assert joined["case435_exactness_join_certificate_id"] == (
        "2abf00603826f93bb6a538511bbd49ee45096901edbf9bc63c7d0cefb9e7fc3f"
    )
    assert joined["upper_channel"]["certificate_id"] == (
        "c01bba7c5f5f19c12957493c7a0989dc3ddbc42306c0f059ee922c18341e62b4"
    )
    assert joined["attainer_channel"]["certificate_id"] == (
        "1d801ba5b81a5e5ed27adfba2ff718fa24a7bd27e3cbf87ce5b603f653502dba"
    )
    assert joined["exact_maximum_octets"] == 257_887
    assert joined["exact_maximum_proved"] is True
    assert joined["exactness_claimed"] is True
    assert joined["next_subgate"] == "A4-P6-C435-D"
    assert joined["verifier_expansion_state"] == "HOLD"


def test_independent_checker_reconstructs_join(upper, attainer, joined):
    assert checker_module.verify(ROOT, upper, attainer, joined) == {
        "case435_exactness_join_certificate_id": (
            "2abf00603826f93bb6a538511bbd49ee45096901edbf9bc63c7d0cefb9e7fc3f"
        ),
        "upper_certificate_id": (
            "c01bba7c5f5f19c12957493c7a0989dc3ddbc42306c0f059ee922c18341e62b4"
        ),
        "attainer_certificate_id": (
            "1d801ba5b81a5e5ed27adfba2ff718fa24a7bd27e3cbf87ce5b603f653502dba"
        ),
        "exact_maximum_octets": 257_887,
        "exact_maximum_proved": True,
        "exactness_claimed": True,
        "next_subgate": "A4-P6-C435-D",
        "verifier_expansion_state": "HOLD",
    }


def test_join_is_deterministic(upper, attainer, joined):
    assert join_module.join(ROOT, upper, attainer) == joined
    assert join_module._canonical_bytes(joined) == checker_module._canonical_bytes(
        joined
    )


def test_join_and_checker_have_no_local_cross_imports():
    allowed = {"hashlib", "json", "pathlib", "sys", "typing", "__future__"}
    for path in (JOIN_PATH, CHECKER_PATH):
        tree = ast.parse(path.read_text())
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        assert imported <= allowed


def test_exactness_does_not_require_same_maximizing_witness_identity(joined):
    predicates = joined["ordered_required_join_predicates"]
    assert "EXACT_UPPER_EQUALS_MEASURED_LEGAL_ATTAINER_OCTETS" in predicates
    assert all("WITNESS_IDENTITY_EQUAL" not in predicate for predicate in predicates)


def test_rejects_resealed_upper_channel_substitution(upper, attainer):
    challenger = copy.deepcopy(upper)
    challenger["exact_upper_bound_octets"] += 1
    _reseal_upper(challenger)
    with pytest.raises(
        join_module.JoinError, match="upper certificate identity differs"
    ):
        join_module.join(ROOT, challenger, attainer)


def test_rejects_resealed_attainer_channel_substitution(upper, attainer):
    challenger = copy.deepcopy(attainer)
    challenger["measured_attainer"]["canonical_octets"] -= 1
    _reseal_attainer(challenger)
    with pytest.raises(
        join_module.JoinError, match="attainer certificate identity differs"
    ):
        join_module.join(ROOT, upper, challenger)


def test_equality_predicate_rejects_different_legal_length(
    upper, attainer, monkeypatch
):
    challenger = copy.deepcopy(attainer)
    challenger["measured_attainer"]["canonical_octets"] -= 1
    challenger_id = _reseal_attainer(challenger)
    monkeypatch.setattr(join_module, "ATTAINER_CERTIFICATE_ID", challenger_id)
    with pytest.raises(join_module.JoinError, match="canonical-octet equality fails"):
        join_module.join(ROOT, upper, challenger)


def test_rejects_case_binding_mismatch_even_when_both_channels_are_resealed(
    upper, attainer, monkeypatch
):
    upper_challenger = copy.deepcopy(upper)
    attainer_challenger = copy.deepcopy(attainer)
    upper_challenger["case_binding"]["profile_position"] -= 1
    attainer_challenger["case_binding"]["profile_position"] -= 1
    upper_id = _reseal_upper(upper_challenger)
    attainer_id = _reseal_attainer(attainer_challenger)
    monkeypatch.setattr(join_module, "UPPER_CERTIFICATE_ID", upper_id)
    monkeypatch.setattr(join_module, "ATTAINER_CERTIFICATE_ID", attainer_id)
    with pytest.raises(join_module.JoinError, match="case binding join differs"):
        join_module.join(ROOT, upper_challenger, attainer_challenger)


def test_rejects_authority_mismatch_even_when_both_channels_are_resealed(
    upper, attainer, monkeypatch
):
    upper_challenger = copy.deepcopy(upper)
    attainer_challenger = copy.deepcopy(attainer)
    authority = next(iter(upper_challenger["authority_sha256_by_path"]))
    upper_challenger["authority_sha256_by_path"][authority] = "0" * 64
    attainer_challenger["authority_sha256_by_path"][authority] = "0" * 64
    upper_id = _reseal_upper(upper_challenger)
    attainer_id = _reseal_attainer(attainer_challenger)
    monkeypatch.setattr(join_module, "UPPER_CERTIFICATE_ID", upper_id)
    monkeypatch.setattr(join_module, "ATTAINER_CERTIFICATE_ID", attainer_id)
    with pytest.raises(join_module.JoinError, match="raw authority join differs"):
        join_module.join(ROOT, upper_challenger, attainer_challenger)


def test_rejects_schedule_mismatch_even_when_attainer_is_resealed(
    upper, attainer, monkeypatch
):
    challenger = copy.deepcopy(attainer)
    challenger["schedule_authority"]["application_invocation_count"] += 1
    challenger_id = _reseal_attainer(challenger)
    monkeypatch.setattr(join_module, "ATTAINER_CERTIFICATE_ID", challenger_id)
    with pytest.raises(
        join_module.JoinError, match="attainer channel disposition differs"
    ):
        join_module.join(ROOT, upper, challenger)


def test_rejects_premature_attainer_exactness_even_when_resealed(
    upper, attainer, monkeypatch
):
    challenger = copy.deepcopy(attainer)
    challenger["exactness_claimed"] = True
    challenger_id = _reseal_attainer(challenger)
    monkeypatch.setattr(join_module, "ATTAINER_CERTIFICATE_ID", challenger_id)
    with pytest.raises(
        join_module.JoinError, match="attainer channel disposition differs"
    ):
        join_module.join(ROOT, upper, challenger)


def test_rejects_upper_channel_attainer_claim_even_when_resealed(
    upper, attainer, monkeypatch
):
    challenger = copy.deepcopy(upper)
    challenger["independent_attainer_accepted"] = True
    challenger_id = _reseal_upper(challenger)
    monkeypatch.setattr(join_module, "UPPER_CERTIFICATE_ID", challenger_id)
    with pytest.raises(
        join_module.JoinError, match="upper channel disposition differs"
    ):
        join_module.join(ROOT, challenger, attainer)


def test_checker_rejects_resealed_join_projection_mutation(upper, attainer, joined):
    challenger = copy.deepcopy(joined)
    challenger["next_subgate"] = "A4-P6-V"
    _reseal_join(challenger)
    with pytest.raises(
        checker_module.ExactnessError, match="join certificate projection differs"
    ):
        checker_module.verify(ROOT, upper, attainer, challenger)


def test_strict_loaders_reject_duplicate_members():
    raw = b'{"a":1,"a":2}'
    with pytest.raises(join_module.JoinError, match="duplicate JSON key"):
        join_module._strict_load(raw, "join duplicate")
    with pytest.raises(checker_module.ExactnessError, match="duplicate JSON key"):
        checker_module._strict_load(raw, "checker duplicate")


def test_cli_join_and_checker_interoperate(tmp_path, upper, attainer, joined):
    upper_path = tmp_path / "upper.json"
    attainer_path = tmp_path / "attainer.json"
    joined_path = tmp_path / "joined.json"
    upper_path.write_bytes(join_module._canonical_bytes(upper))
    attainer_path.write_bytes(join_module._canonical_bytes(attainer))
    joined_path.write_bytes(join_module._canonical_bytes(joined))
    produced = subprocess.run(
        [
            sys.executable,
            str(JOIN_PATH),
            str(ROOT),
            str(upper_path),
            str(attainer_path),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    assert json.loads(produced.stdout) == joined
    checked = subprocess.run(
        [
            sys.executable,
            str(CHECKER_PATH),
            str(ROOT),
            str(upper_path),
            str(attainer_path),
            str(joined_path),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    assert json.loads(checked.stdout)["exact_maximum_proved"] is True
