from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from riskyieldmm.trading.calendar_actions import (
    ActionProtocolV3,
    CalendarScheduleSnapshotV3,
    CalendarSourceArtifactV3,
    InstrumentMappingV3,
)
from riskyieldmm.trading.canonical import canonical_json_bytes, strict_json_loads
from riskyieldmm.trading.ledger import V3GovernanceLedger
from riskyieldmm.trading.ledger_cli import main
from riskyieldmm.trading.ledger_signing import Ed25519CheckpointSigner
from tests.test_trading_manifests_v3 import (
    governed_protocol_graph,
    governed_source_graph,
    protocol_record_graph,
)


def private_directory(path: Path) -> Path:
    path.mkdir(mode=0o700)
    path.chmod(0o700)
    return path


def empty_ledger(directory: Path) -> Path:
    database = directory / "governance.sqlite3"
    with V3GovernanceLedger(database):
        pass
    return database


def checkpointed_ledger(
    directory: Path,
) -> tuple[Path, Path, Ed25519CheckpointSigner, str]:
    database = directory / "governance.sqlite3"
    signer = Ed25519CheckpointSigner.generate()
    with V3GovernanceLedger(database) as ledger:
        checkpoint = ledger.create_checkpoint(
            signer,
            idempotency_key="cli-checkpoint-0001",
        )
    checkpoint_path = directory / "trusted-checkpoint.json"
    checkpoint_path.write_bytes(canonical_json_bytes(checkpoint.as_dict()))
    return database, checkpoint_path, signer, checkpoint.checkpoint_id


def populated_v32_ledger(directory: Path) -> tuple[Path, int]:
    """Create the complete causal V3.2 graph that the CLI must revalidate."""

    database = directory / "governance.sqlite3"
    source, member, bundle, evidence_registry = governed_source_graph()
    protocol, slot, definition, schema, evidence_registry = governed_protocol_graph(
        source,
        member,
        bundle,
        evidence_registry,
    )
    information, candidate, materialization, eligibility, decision, resolution = (
        protocol_record_graph(protocol, source, evidence_registry)
    )
    artifact = next(
        item
        for item in evidence_registry.values()
        if isinstance(item, CalendarSourceArtifactV3)
    )
    calendar = next(
        item
        for item in evidence_registry.values()
        if isinstance(item, CalendarScheduleSnapshotV3)
    )
    action_protocol = next(
        item
        for item in evidence_registry.values()
        if isinstance(item, ActionProtocolV3)
    )
    instrument_mapping = next(
        item
        for item in evidence_registry.values()
        if isinstance(item, InstrumentMappingV3)
    )
    records = (
        artifact,
        calendar,
        action_protocol,
        instrument_mapping,
        member,
        bundle,
        slot,
        definition,
        schema,
        source,
        protocol,
        information,
        resolution,
        candidate,
        materialization,
        eligibility,
        decision,
    )
    with V3GovernanceLedger(database) as ledger:
        for index, record in enumerate(records, start=1):
            ledger.append(record, idempotency_key=f"cli-v32-graph-{index:02d}")
    return database, len(records)


def run_cli(
    capsys: pytest.CaptureFixture[str], *arguments: object
) -> tuple[int, str, str]:
    status = main([str(argument) for argument in arguments])
    captured = capsys.readouterr()
    return status, captured.out, captured.err


def test_verify_clean_ledger_read_only(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = empty_ledger(private_directory(tmp_path / "private-ledger"))
    before = database.stat()

    status, stdout, stderr = run_cli(capsys, "verify", database)

    report = strict_json_loads(stdout)
    assert status == 0
    assert stderr == ""
    assert report["object_count"] == 0
    assert report["receipt_count"] == 0
    assert report["checkpoint_count"] == 0
    assert report["trusted_checkpoint_id"] is None
    after = database.stat()
    assert (after.st_size, after.st_mtime_ns) == (before.st_size, before.st_mtime_ns)


def test_verify_complete_v32_evidence_candidate_and_decision_graph_read_only(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database, expected_count = populated_v32_ledger(
        private_directory(tmp_path / "private-ledger")
    )
    before = database.stat()

    status, stdout, stderr = run_cli(capsys, "verify", database)

    report = strict_json_loads(stdout)
    assert status == 0
    assert stderr == ""
    assert report["object_count"] == expected_count
    assert report["receipt_count"] == expected_count
    assert report["head_transition_count"] == expected_count
    assert report["checkpoint_count"] == 0
    assert report["holdout_grant_count"] == 0
    assert report["unanchored_receipt_count"] == expected_count
    after = database.stat()
    assert (after.st_size, after.st_mtime_ns) == (before.st_size, before.st_mtime_ns)


def test_verify_accepts_trusted_external_checkpoint_and_public_key(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database, checkpoint_path, signer, checkpoint_id = checkpointed_ledger(
        private_directory(tmp_path / "private-ledger")
    )

    status, stdout, stderr = run_cli(
        capsys,
        "verify",
        database,
        "--checkpoint",
        checkpoint_path,
        "--public-key-hex",
        signer.public_key_bytes.hex(),
    )

    report = strict_json_loads(stdout)
    assert status == 0
    assert stderr == ""
    assert report["checkpoint_count"] == 1
    assert report["trusted_checkpoint_id"] == checkpoint_id


def test_verify_rejects_wrong_checkpoint_public_key(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database, checkpoint_path, _, _ = checkpointed_ledger(
        private_directory(tmp_path / "private-ledger")
    )
    wrong_signer = Ed25519CheckpointSigner.generate()

    status, stdout, stderr = run_cli(
        capsys,
        "verify",
        database,
        "--checkpoint",
        checkpoint_path,
        "--public-key-hex",
        wrong_signer.public_key_bytes.hex(),
    )

    assert status == 2
    assert stdout == ""
    assert "ledger verification failed" in stderr
    assert "key_id differs from the supplied public key" in stderr


def test_verify_rejects_checkpoint_without_public_key(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database, checkpoint_path, _, _ = checkpointed_ledger(
        private_directory(tmp_path / "private-ledger")
    )

    status, stdout, stderr = run_cli(
        capsys,
        "verify",
        database,
        "--checkpoint",
        checkpoint_path,
    )

    assert status == 2
    assert stdout == ""
    assert "--checkpoint and --public-key-hex must be supplied together" in stderr


@pytest.mark.parametrize("payload", [b"{", b"[]"])
def test_verify_rejects_malformed_checkpoint(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    payload: bytes,
) -> None:
    directory = private_directory(tmp_path / "private-ledger")
    database = empty_ledger(directory)
    checkpoint_path = directory / "malformed-checkpoint.json"
    checkpoint_path.write_bytes(payload)

    status, stdout, stderr = run_cli(
        capsys,
        "verify",
        database,
        "--checkpoint",
        checkpoint_path,
        "--public-key-hex",
        Ed25519CheckpointSigner.generate().public_key_bytes.hex(),
    )

    assert status == 2
    assert stdout == ""
    assert "ledger verification failed" in stderr


def test_verify_rejects_non_private_database(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = empty_ledger(private_directory(tmp_path / "private-ledger"))
    database.chmod(0o644)

    status, stdout, stderr = run_cli(capsys, "verify", database)

    assert status == 2
    assert stdout == ""
    assert "ledger file must have mode 0600" in stderr
    assert os.stat(database).st_mode & 0o777 == 0o644


def test_verify_rejects_missing_database(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    directory = private_directory(tmp_path / "private-ledger")
    database = directory / "missing.sqlite3"

    status, stdout, stderr = run_cli(capsys, "verify", database)

    assert status == 2
    assert stdout == ""
    assert "ledger does not exist" in stderr
    assert not database.exists()


def test_verify_reports_late_sqlite_corruption_without_a_traceback(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = empty_ledger(private_directory(tmp_path / "private-ledger"))

    with patch.object(
        V3GovernanceLedger,
        "verify",
        side_effect=sqlite3.DatabaseError("injected damaged page"),
    ):
        status, stdout, stderr = run_cli(capsys, "verify", database)

    assert status == 2
    assert stdout == ""
    assert "ledger verification failed: injected damaged page" in stderr
