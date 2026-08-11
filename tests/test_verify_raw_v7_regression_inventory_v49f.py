from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from scripts.tests import verify_raw_v7_regression_inventory_v49f as verifier


def _write_payload(path: Path, payload: dict[str, Any]) -> None:
    payload["inventory_sha256"] = verifier._canonical_inventory_sha256(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def _repository(tmp_path: Path) -> tuple[Path, Path, dict[str, Any]]:
    root = tmp_path / "repository"
    groups: list[dict[str, Any]] = []
    for group_name in verifier.EXPECTED_GROUPS:
        relative = f"tests/test_{group_name}.py"
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        source = f"def test_{group_name}():\n    assert True\n"
        path.write_text(source, encoding="utf-8")
        groups.append(
            {
                "name": group_name,
                "expected_case_count": 1,
                "files": [
                    {
                        "path": relative,
                        "expected_cases": 1,
                        "sha256": hashlib.sha256(source.encode()).hexdigest(),
                    }
                ],
            }
        )
    payload: dict[str, Any] = {
        "schema_version": verifier.SCHEMA_VERSION,
        "scope": verifier.INVENTORY_SCOPE,
        "inventory_sha256": "0" * 64,
        "expected_file_count": len(groups),
        "expected_case_count": len(groups),
        "groups": groups,
    }
    manifest = root / "tests/inventory.json"
    _write_payload(manifest, payload)
    return root, manifest, payload


def test_cli_accepts_exact_inventory_with_skip_collection(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root, manifest, _ = _repository(tmp_path)
    assert (
        verifier.main(
            ["--manifest", str(manifest), "--skip-collection"],
            repository_root=root,
        )
        == 0
    )
    output = capsys.readouterr()
    assert "PASS:" in output.out
    assert "8 disjoint files / 8 collected cases" in output.out
    assert "collection_command" not in output.out


def test_cli_accepts_exact_inventory_and_collection(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root, manifest, _ = _repository(tmp_path)
    assert verifier.main(["--manifest", str(manifest)], repository_root=root) == 0
    output = capsys.readouterr()
    assert "PASS:" in output.out
    assert "collection_command:" in output.out


def test_manifest_digest_drift_is_rejected(tmp_path: Path) -> None:
    root, manifest, payload = _repository(tmp_path)
    payload["expected_case_count"] += 1
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(verifier.InventoryError, match="inventory_sha256 differs"):
        verifier._load_and_verify_manifest(manifest, repository_root=root)


def test_inventory_file_hash_drift_is_rejected(tmp_path: Path) -> None:
    root, manifest, payload = _repository(tmp_path)
    changed = root / payload["groups"][0]["files"][0]["path"]
    changed.write_text("def test_changed():\n    assert False\n", encoding="utf-8")
    with pytest.raises(verifier.InventoryError, match="file sha256 differs"):
        verifier._load_and_verify_manifest(manifest, repository_root=root)


def test_frozen_file_count_drift_is_rejected(tmp_path: Path) -> None:
    root, manifest, payload = _repository(tmp_path)
    payload["expected_file_count"] += 1
    _write_payload(manifest, payload)
    with pytest.raises(verifier.InventoryError, match="file count differs"):
        verifier._load_and_verify_manifest(manifest, repository_root=root)


def test_frozen_group_order_drift_is_rejected(tmp_path: Path) -> None:
    root, manifest, payload = _repository(tmp_path)
    payload["groups"][0], payload["groups"][1] = (
        payload["groups"][1],
        payload["groups"][0],
    )
    _write_payload(manifest, payload)
    with pytest.raises(verifier.InventoryError, match="group order or membership"):
        verifier._load_and_verify_manifest(manifest, repository_root=root)


def test_collection_case_count_drift_is_rejected(tmp_path: Path) -> None:
    root, manifest, payload = _repository(tmp_path)
    payload["groups"][0]["files"][0]["expected_cases"] = 2
    payload["groups"][0]["expected_case_count"] = 2
    payload["expected_case_count"] += 1
    _write_payload(manifest, payload)
    _, entries = verifier._load_and_verify_manifest(manifest, repository_root=root)
    with pytest.raises(verifier.InventoryError, match="collection differs"):
        verifier._collect_and_verify(entries, repository_root=root, timeout_seconds=30)


def test_parent_path_is_rejected_before_file_access(tmp_path: Path) -> None:
    root, manifest, payload = _repository(tmp_path)
    payload["groups"][0]["files"][0]["path"] = "tests/../outside.py"
    _write_payload(manifest, payload)
    with pytest.raises(verifier.InventoryError, match="unsafe inventory path"):
        verifier._load_and_verify_manifest(manifest, repository_root=root)


def test_symlink_escape_is_rejected(tmp_path: Path) -> None:
    root, manifest, payload = _repository(tmp_path)
    entry = payload["groups"][0]["files"][0]
    link = root / entry["path"]
    original = link.read_bytes()
    outside = tmp_path / "outside.py"
    outside.write_bytes(original)
    link.unlink()
    link.symlink_to(outside)
    with pytest.raises(verifier.InventoryError, match="escapes or is unavailable"):
        verifier._load_and_verify_manifest(manifest, repository_root=root)


def test_duplicate_json_keys_are_rejected(tmp_path: Path) -> None:
    root = tmp_path / "repository"
    root.mkdir()
    manifest = root / "inventory.json"
    manifest.write_text('{"schema_version":"a","schema_version":"b"}', encoding="utf-8")
    with pytest.raises(verifier.InventoryError, match="duplicate JSON key"):
        verifier._load_and_verify_manifest(manifest, repository_root=root)


def test_nonfinite_json_constants_are_rejected(tmp_path: Path) -> None:
    root = tmp_path / "repository"
    root.mkdir()
    manifest = root / "inventory.json"
    manifest.write_text('{"expected_file_count":NaN}', encoding="utf-8")
    with pytest.raises(verifier.InventoryError, match="non-finite JSON constant"):
        verifier._load_and_verify_manifest(manifest, repository_root=root)


@pytest.mark.parametrize("bad_scope", (None, 1, "different scope"))
def test_scope_type_and_value_are_frozen(tmp_path: Path, bad_scope: object) -> None:
    root, manifest, payload = _repository(tmp_path)
    payload["scope"] = bad_scope
    _write_payload(manifest, payload)
    with pytest.raises(verifier.InventoryError, match="inventory scope differs"):
        verifier._load_and_verify_manifest(manifest, repository_root=root)
