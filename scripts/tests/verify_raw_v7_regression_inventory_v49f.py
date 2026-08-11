#!/usr/bin/env python3
"""Verify the frozen Raw-V7 adjacent regression inventory and collection."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shlex
import subprocess
import sys
import tempfile
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "riskyieldmm.raw_v7_adjacent_regression_inventory.v1"
INVENTORY_SCOPE = (
    "Disjoint current-file inventory for Raw V6, A1, actor, projection, "
    "Linux-owner, ingress, terminal, and public-denial dependencies adjacent "
    "to Raw V7."
)
EXPECTED_GROUPS = (
    "raw_v6",
    "a1",
    "actor",
    "projection",
    "linux_owner",
    "ingress",
    "terminal",
    "public_denial",
)
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
DEFAULT_MANIFEST = "tests/raw_v7_regression_inventory_v49f.json"


class InventoryError(ValueError):
    """Raised when the frozen inventory or its collection differs."""


def _reject_nonfinite_json(value: str) -> None:
    raise InventoryError(f"non-finite JSON constant is forbidden: {value}")


def _reject_duplicate_json_keys(
    pairs: list[tuple[str, Any]],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise InventoryError(f"duplicate JSON key is forbidden: {key}")
        result[key] = value
    return result


def _exact_int(value: Any, *, field: str) -> int:
    if type(value) is not int or value < 0:
        raise InventoryError(f"{field} must be an exact non-negative integer")
    return value


def _canonical_inventory_sha256(payload: dict[str, Any]) -> str:
    unsigned = dict(payload)
    unsigned.pop("inventory_sha256", None)
    encoded = json.dumps(
        unsigned,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _load_and_verify_manifest(
    manifest_path: Path, *, repository_root: Path
) -> tuple[dict[str, Any], tuple[tuple[str, int], ...]]:
    try:
        payload = json.loads(
            manifest_path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_json_keys,
            parse_constant=_reject_nonfinite_json,
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise InventoryError(f"cannot read exact inventory: {exc}") from exc
    if type(payload) is not dict:
        raise InventoryError("inventory root must be an exact object")
    expected_keys = {
        "schema_version",
        "scope",
        "inventory_sha256",
        "expected_file_count",
        "expected_case_count",
        "groups",
    }
    if set(payload) != expected_keys:
        raise InventoryError("inventory root keys differ from the frozen schema")
    if payload["schema_version"] != SCHEMA_VERSION:
        raise InventoryError("inventory schema_version differs")
    if type(payload["scope"]) is not str or payload["scope"] != INVENTORY_SCOPE:
        raise InventoryError("inventory scope differs from the frozen scope")
    expected_inventory_sha256 = payload["inventory_sha256"]
    if (
        type(expected_inventory_sha256) is not str
        or SHA256_RE.fullmatch(expected_inventory_sha256) is None
    ):
        raise InventoryError("inventory_sha256 must be one lowercase SHA-256")
    actual_inventory_sha256 = _canonical_inventory_sha256(payload)
    if actual_inventory_sha256 != expected_inventory_sha256:
        raise InventoryError(
            "inventory_sha256 differs: "
            f"expected {expected_inventory_sha256}, got {actual_inventory_sha256}"
        )
    groups = payload["groups"]
    if type(groups) is not list:
        raise InventoryError("groups must be an exact list")
    if tuple(group.get("name") for group in groups if type(group) is dict) != (
        EXPECTED_GROUPS
    ):
        raise InventoryError("inventory group order or membership differs")

    entries: list[tuple[str, int]] = []
    seen: set[str] = set()
    for group in groups:
        if type(group) is not dict or set(group) != {
            "name",
            "expected_case_count",
            "files",
        }:
            raise InventoryError("inventory group shape differs")
        files = group["files"]
        if type(files) is not list or not files:
            raise InventoryError(f"group {group['name']} has no exact file list")
        group_cases = 0
        for entry in files:
            if type(entry) is not dict or set(entry) != {
                "path",
                "expected_cases",
                "sha256",
            }:
                raise InventoryError("inventory file-entry shape differs")
            relative = entry["path"]
            if (
                type(relative) is not str
                or not relative.startswith("tests/")
                or not relative.endswith(".py")
                or Path(relative).is_absolute()
                or ".." in Path(relative).parts
            ):
                raise InventoryError(f"unsafe inventory path: {relative!r}")
            if relative in seen:
                raise InventoryError(f"inventory file is not disjoint: {relative}")
            seen.add(relative)
            expected_cases = _exact_int(
                entry["expected_cases"], field=f"{relative}.expected_cases"
            )
            if expected_cases == 0:
                raise InventoryError(f"inventory file has zero cases: {relative}")
            expected_sha256 = entry["sha256"]
            if (
                type(expected_sha256) is not str
                or SHA256_RE.fullmatch(expected_sha256) is None
            ):
                raise InventoryError(f"invalid file sha256: {relative}")
            root = repository_root.resolve(strict=True)
            unresolved_path = root / relative
            try:
                path = unresolved_path.resolve(strict=True)
                path.relative_to(root)
            except (OSError, ValueError) as exc:
                raise InventoryError(
                    f"inventory path escapes or is unavailable: {relative}"
                ) from exc
            if not path.is_file():
                raise InventoryError(f"inventory path is not a file: {relative}")
            try:
                actual_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
            except OSError as exc:
                raise InventoryError(f"cannot read {relative}: {exc}") from exc
            if actual_sha256 != expected_sha256:
                raise InventoryError(
                    f"file sha256 differs for {relative}: "
                    f"expected {expected_sha256}, got {actual_sha256}"
                )
            entries.append((relative, expected_cases))
            group_cases += expected_cases
        expected_group_cases = _exact_int(
            group["expected_case_count"],
            field=f"{group['name']}.expected_case_count",
        )
        if group_cases != expected_group_cases:
            raise InventoryError(
                f"group {group['name']} case sum differs: "
                f"expected {expected_group_cases}, got {group_cases}"
            )

    expected_files = _exact_int(
        payload["expected_file_count"], field="expected_file_count"
    )
    expected_cases = _exact_int(
        payload["expected_case_count"], field="expected_case_count"
    )
    if len(entries) != expected_files:
        raise InventoryError(
            f"file count differs: expected {expected_files}, got {len(entries)}"
        )
    total_cases = sum(case_count for _, case_count in entries)
    if total_cases != expected_cases:
        raise InventoryError(
            f"case sum differs: expected {expected_cases}, got {total_cases}"
        )
    return payload, tuple(entries)


def _collect_and_verify(
    entries: tuple[tuple[str, int], ...],
    *,
    repository_root: Path,
    timeout_seconds: int,
) -> str:
    with tempfile.TemporaryDirectory(prefix="rymm-raw-v7-inventory-") as temp_dir:
        command = [
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            f"--basetemp={Path(temp_dir) / 'pytest'}",
            *(relative for relative, _ in entries),
        ]
        try:
            completed = subprocess.run(
                command,
                cwd=repository_root,
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            raise InventoryError(
                f"pytest collection exceeded {timeout_seconds} seconds"
            ) from exc
    if completed.returncode != 0:
        raise InventoryError(
            "pytest collection failed\n"
            f"command: {shlex.join(command)}\n"
            f"stdout:\n{completed.stdout}\n"
            f"stderr:\n{completed.stderr}"
        )
    collected: Counter[str] = Counter()
    known_paths = {relative for relative, _ in entries}
    for line in completed.stdout.splitlines():
        node_id = line.strip()
        if "::" not in node_id:
            continue
        relative = node_id.split("::", 1)[0]
        if relative in known_paths:
            collected[relative] += 1
    mismatches = {
        relative: (expected_cases, collected[relative])
        for relative, expected_cases in entries
        if collected[relative] != expected_cases
    }
    unexpected = sorted(set(collected) - known_paths)
    if mismatches or unexpected:
        raise InventoryError(
            "pytest collection differs from the frozen inventory: "
            f"mismatches={mismatches}, unexpected={unexpected}"
        )
    return shlex.join(command)


def main(
    argv: Sequence[str] | None = None,
    *,
    repository_root: Path | None = None,
) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST)
    parser.add_argument("--skip-collection", action="store_true")
    parser.add_argument("--timeout-seconds", type=int, default=300)
    arguments = parser.parse_args(argv)
    if arguments.timeout_seconds <= 0:
        parser.error("--timeout-seconds must be positive")

    if repository_root is None:
        repository_root = Path(__file__).resolve().parents[2]
    repository_root = repository_root.resolve(strict=True)
    manifest_path = Path(arguments.manifest)
    if not manifest_path.is_absolute():
        manifest_path = repository_root / manifest_path
    try:
        payload, entries = _load_and_verify_manifest(
            manifest_path, repository_root=repository_root
        )
        command = None
        if not arguments.skip_collection:
            command = _collect_and_verify(
                entries,
                repository_root=repository_root,
                timeout_seconds=arguments.timeout_seconds,
            )
    except InventoryError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1

    print(
        "PASS: Raw-V7 adjacent regression inventory "
        f"{payload['inventory_sha256']} covers "
        f"{payload['expected_file_count']} disjoint files / "
        f"{payload['expected_case_count']} collected cases."
    )
    if command is not None:
        print(f"collection_command: {command}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
