from __future__ import annotations

import asyncio
import hashlib
import shutil
import sqlite3
import sys
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from websockets.frames import Frame, Opcode

from riskyieldmm.trading import physical_transport_capacity_lifecycle_v49f as lifecycle
from riskyieldmm.trading import (
    physical_transport_capacity_measurement_v49f as measurement,
)
from riskyieldmm.trading.canonical import (
    MAX_IJSON_INTEGER,
    CanonicalizationError,
    canonical_json_bytes,
    strict_json_loads,
)
from riskyieldmm.trading.ledger_signing import Ed25519CheckpointSigner
from riskyieldmm.trading.physical_projection_v4 import (
    PhysicalProjectionStoreV4,
    PhysicalProjectionV4ConfigurationError,
    PhysicalProjectionV4VerificationError,
)
from riskyieldmm.trading.physical_transport_capacity_lifecycle_v49f import (
    CAPACITY_MEASUREMENT_JSON_ARRAY_ELEMENT_LIMIT_EXCEEDED_V49F_V7,
    CAPACITY_MEASUREMENT_JSON_DEPTH_LIMIT_EXCEEDED_V49F_V7,
    CAPACITY_MEASUREMENT_JSON_MALFORMED_STRUCTURE_V49F_V7,
    CAPACITY_MEASUREMENT_JSON_OBJECT_MEMBER_LIMIT_EXCEEDED_V49F_V7,
    CAPACITY_MEASUREMENT_LIFECYCLE_MAXIMUM_EXCEPTION_CLASS_UTF8_BYTES_V49F,
    CAPACITY_MEASUREMENT_LIFECYCLE_MAXIMUM_PREFIX_BYTES_V49F,
    CAPACITY_MEASUREMENT_LIFECYCLE_MAXIMUM_RECORD_BYTES_V49F,
    CAPACITY_MEASUREMENT_MAXIMUM_JSON_ARRAY_ELEMENTS_V49F_V7,
    CAPACITY_MEASUREMENT_MAXIMUM_JSON_NESTING_DEPTH_V49F_V7,
    CAPACITY_MEASUREMENT_MAXIMUM_JSON_OBJECT_MEMBERS_V49F_V7,
    CapacityMeasurementLifecycleCancellationV49F,
    CapacityMeasurementLifecycleEffectCertaintyV49F,
    CapacityMeasurementLifecycleProgressAvailabilityV49F,
    CapacityMeasurementLifecycleTerminalTriggerV49F,
    CapacityMeasurementOperationPrefixV49F,
    CapacityMeasurementSameTaskTerminalObservationV49F,
    validate_capacity_measurement_json_structure_before_parse_v49f_v7,
)
from riskyieldmm.trading.physical_transport_capacity_manifest_authority_v49f import (
    RAW_V7_CRITICAL_SOURCE_MODULES_V49F,
)
from riskyieldmm.trading.physical_transport_capacity_measurement_v49f import (
    A2M_MAXIMUM_ARTIFACT_CLOSURE_BYTES_V49F,
    A2M_MAXIMUM_CORRECTNESS_ARTIFACT_BYTES_V49F,
    A2M_MAXIMUM_INTEGRITY_ARTIFACT_BYTES_V49F,
    A2M_MAXIMUM_MANIFEST_ARTIFACT_BYTES_V49F,
    A2M_MAXIMUM_OPERATION_ATTEMPT_BYTES_V49F_V7,
    A2M_MAXIMUM_OPERATION_TERMINAL_BYTES_V49F_V7,
    A2M_MAXIMUM_SAMPLE_RECORD_BYTES_V49F,
    A2M_MAXIMUM_SAMPLES_ARTIFACT_BYTES_V49F,
    A2M_MAXIMUM_TOTAL_TRIALS_V49F,
    A2M_OPERATION_ATTEMPT_RECORD_KIND_V49F_V7,
    A2M_OPERATION_TERMINAL_RECORD_KIND_V49F_V7,
    CapacityMeasurementArtifactBundleV49F,
    CapacityMeasurementArtifactBundleV49FV7,
    CapacityMeasurementArtifactErrorV49F,
    CapacityMeasurementCommittedLifecycleRecordV49FV7,
    CapacityMeasurementCorrectnessV49FV7,
    CapacityMeasurementManifestV49FV7,
    CapacityMeasurementSampleV49F,
    CapacityMeasurementSampleV49FV7,
    CapacityMeasurementScheduleCoverageV49FV7,
    decode_capacity_measurement_json_v49f,
    decode_capacity_measurement_json_v49f_v7,
    decode_capacity_measurement_samples_jsonl_v49f_v7,
    encode_capacity_measurement_json_v49f,
    encode_capacity_measurement_json_v49f_v7,
    validate_capacity_measurement_samples_v49f_v7,
)
from riskyieldmm.trading.physical_transport_capacity_source_observation_v49f import (
    SourceMemberObservationV49F,
    SourceObservationSnapshotV49F,
    derive_observed_source_tree_sha256_v49f,
)
from tests import (
    test_trading_physical_transport_capacity_measurement_v7_v49f as v7_fixtures,
)
from tests import (
    test_trading_physical_transport_capacity_measurement_v49f as v6_fixtures,
)
from tests.test_trading_physical_transport_capacity_lifecycle_v49f import (
    T0,
    _cancel_observation,
    _declaration,
)
from tests.test_trading_physical_transport_capacity_lifecycle_v49f import (
    _attempt as _runtime_attempt,
)
from tests.test_trading_physical_transport_capacity_measurement_v7_v49f import (
    _attempt,
    _bundle,
    _cancelled_sample,
    _current_v6_predecessor,
    _projection_commit,
    _returned_sample,
    _v7_manifest_and_expectation,
)
from tests.test_trading_physical_transport_capacity_v7_adversarial import (
    _capacity_identity_counts,
)
from tests.test_trading_physical_transport_runtime_v49b import _build_harness
from tests.test_trading_physical_transport_runtime_v49d_ingress import (
    _establish_and_activate,
)
from tests.test_trading_physical_transport_runtime_v49f_capacity import _policy

pytestmark = pytest.mark.skipif(
    sys.platform != "linux", reason="Linux-only Raw-V7 acceptance-edge tests"
)


class _InjectedRecoveryFault(RuntimeError):
    pass


class _InjectedRecoveryRollbackFault(RuntimeError):
    pass


class _ParseReached(RuntimeError):
    pass


def _sqlite_backup(store: PhysicalProjectionStoreV4, target: Path) -> None:
    target.unlink(missing_ok=True)
    connection = sqlite3.connect(target)
    try:
        store._connection.backup(connection)  # noqa: SLF001
    finally:
        connection.close()


@pytest.fixture(scope="module")
def lifecycle_database_snapshots(
    tmp_path_factory: pytest.TempPathFactory,
) -> dict[str, Any]:
    root = tmp_path_factory.mktemp("v7-edges")

    async def scenario() -> dict[str, Any]:
        harness = await _build_harness(
            root,
            first_frame=Frame(Opcode.PONG, b"").serialize(mask=False),
            transport_capacity_policy_v49f=_policy(),
        )
        try:
            await _establish_and_activate(harness)
            attempt = _runtime_attempt(harness, _declaration((b"x",)))
            committed = (
                harness.store._append_capacity_measurement_operation_attempt_core_v49f(  # noqa: SLF001
                    attempt,
                    idempotency_key="raw-v7-acceptance-edge-attempt",
                )
            )
            open_path = root / "open.sqlite3"
            _sqlite_backup(harness.store, open_path)
            prefix = harness.store.append_capacity_measurement_operation_terminal_v49f(
                committed,
                _cancel_observation(attempt),
                idempotency_key="raw-v7-acceptance-edge-terminal",
            )
            assert prefix.terminal is not None
            closed_path = root / "closed.sqlite3"
            _sqlite_backup(harness.store, closed_path)
            return {
                "open": open_path,
                "closed": closed_path,
                "attempt_id": str(attempt.attempt_id),
                "terminal_id": str(prefix.terminal.terminal_id),
            }
        finally:
            await harness.close()

    return asyncio.run(scenario())


@pytest.mark.parametrize(
    "mutation",
    ("missing_critical", "missing_loaded", "renamed_module", "unknown_role"),
)
def test_v7_source_roles_require_exact_critical_and_loaded_cardinality(
    mutation: str,
) -> None:
    manifest, _ = _v7_manifest_and_expectation()
    roles = list(manifest.predecessor_manifest_v6.source_observation.members[0].roles)
    module = RAW_V7_CRITICAL_SOURCE_MODULES_V49F[0]
    if mutation == "missing_critical":
        roles.remove(f"CRITICAL_MODULE:{module}")
    elif mutation == "missing_loaded":
        roles.remove(f"LOADED_MODULE:{module}")
    elif mutation == "renamed_module":
        roles.remove(f"CRITICAL_MODULE:{module}")
        roles.append(f"CRITICAL_MODULE:{module}_alias")
    else:
        roles.remove(f"LOADED_MODULE:{module}")
        roles.append(f"TEST_ALIAS:{module}")
    predecessor = _current_v6_predecessor(source_roles=tuple(sorted(roles)))

    with pytest.raises(CanonicalizationError):
        replace(
            manifest,
            predecessor_manifest_v6=predecessor,
            campaign_manifest_id=None,
        )


def test_v7_source_roles_reject_cross_member_duplicate_cardinality() -> None:
    predecessor = _current_v6_predecessor()
    source = predecessor.source_observation
    first = source.members[0]
    duplicate = SourceMemberObservationV49F(
        relative_path="000-duplicate-role.py",
        roles=(first.roles[0],),
        size_bytes=0,
        sha256=hashlib.sha256(b"").hexdigest(),
        device=first.device,
        inode=str(int(first.inode) + 1),
        mode=first.mode,
        modified_ns=first.modified_ns,
        changed_ns=first.changed_ns,
    )
    members = tuple(sorted((duplicate, first), key=lambda item: item.relative_path))
    source_tree = derive_observed_source_tree_sha256_v49f(members)
    snapshot = SourceObservationSnapshotV49F(
        repository_root=source.repository_root,
        git_state=source.git_state,
        members=members,
        member_count=2,
        total_bytes=sum(item.size_bytes for item in members),
        source_tree_sha256=source_tree,
        deployment_source_tree_sha256=source_tree,
        deployment_source_tree_matches=True,
    )

    with pytest.raises(CanonicalizationError, match="duplicates a module role"):
        measurement._source_role_modules_v49f_v7(  # noqa: SLF001
            snapshot,
            role_prefix=first.roles[0].split(":", 1)[0] + ":",
        )


@pytest.mark.parametrize(
    "mutation",
    ("embedded_v5", "reference_only", "mutated_predecessor"),
)
def test_v7_manifest_rejects_non_self_contained_or_mutated_predecessor(
    mutation: str,
) -> None:
    manifest, _ = _v7_manifest_and_expectation()
    payload = strict_json_loads(canonical_json_bytes(manifest.as_dict()))
    payload["campaign_manifest_id"] = None
    predecessor = payload["predecessor_manifest_v6"]
    if mutation == "embedded_v5":
        predecessor["measurement_schema_version"] = (
            "riskyieldmm_physical_transport_a2m_raw_v49f_v5"
        )
    elif mutation == "reference_only":
        payload["predecessor_manifest_v6"] = {
            "campaign_manifest_id": manifest.predecessor_manifest_v6.campaign_manifest_id
        }
    else:
        predecessor["campaign_label"] = "MUTATED_PREDECESSOR"
        predecessor["campaign_manifest_id"] = None

    with pytest.raises(CanonicalizationError):
        CapacityMeasurementManifestV49FV7.from_mapping(payload)


def test_v7_manifest_rejects_outer_predecessor_key_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest, _ = _v7_manifest_and_expectation()
    foreign_signer = Ed25519CheckpointSigner.from_private_bytes(
        bytes(reversed(range(32)))
    )
    monkeypatch.setattr(v6_fixtures, "_TEST_MANIFEST_SIGNER", foreign_signer)
    monkeypatch.setattr(v7_fixtures, "_TEST_MANIFEST_SIGNER", foreign_signer)
    foreign_predecessor = _current_v6_predecessor()
    assert (
        foreign_predecessor.manifest_authority.collector_attestation_key_id
        != manifest.predecessor_manifest_v6.manifest_authority.collector_attestation_key_id
    )

    with pytest.raises(CanonicalizationError, match="signed authority differs"):
        replace(
            manifest,
            predecessor_manifest_v6=foreign_predecessor,
            campaign_manifest_id=None,
        )


def test_v6_signature_cannot_replay_as_v7_authority_signature() -> None:
    manifest, _ = _v7_manifest_and_expectation()
    v6_signature = manifest.predecessor_manifest_v6.manifest_authority.signature_hex

    with pytest.raises(CanonicalizationError, match="Raw V7 manifest signature"):
        replace(
            manifest.manifest_authority_v7,
            signature_hex=v6_signature,
            manifest_authority_id=None,
        )


def test_pre_v7_projection_schema_rejects_without_automatic_upgrade(
    tmp_path: Path,
) -> None:
    path = tmp_path / "pre-v7.sqlite3"
    PhysicalProjectionStoreV4(path, clock=lambda: T0).close()
    connection = sqlite3.connect(path)
    try:
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.executescript(
            """
            DROP TABLE capacity_measurement_open_attempts_v49f;
            DROP TABLE capacity_measurement_operation_terminals_v49f;
            DROP TABLE capacity_measurement_operation_attempts_v49f;
            """
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(PhysicalProjectionV4VerificationError, match="schema differs"):
        PhysicalProjectionStoreV4(path, clock=lambda: T0)

    connection = sqlite3.connect(path)
    try:
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    finally:
        connection.close()
    assert (
        not {
            "capacity_measurement_open_attempts_v49f",
            "capacity_measurement_operation_attempts_v49f",
            "capacity_measurement_operation_terminals_v49f",
        }
        & tables
    )


@pytest.mark.parametrize(
    ("snapshot", "statement"),
    (
        (
            "open",
            "UPDATE capacity_measurement_operation_attempts_v49f "
            "SET workload_id = 'FORGED_WORKLOAD'",
        ),
        ("open", "DELETE FROM capacity_measurement_open_attempts_v49f"),
        (
            "closed",
            "UPDATE capacity_measurement_operation_terminals_v49f "
            "SET effect_certainty = 'COMPLETE'",
        ),
        ("closed", "DELETE FROM capacity_measurement_operation_terminals_v49f"),
        (
            "closed",
            "INSERT INTO capacity_measurement_open_attempts_v49f("
            "transport_session_id, attempt_id, campaign_manifest_id, "
            "operation_sequence, attempt_receipt_sequence) "
            "SELECT transport_session_id, attempt_id, campaign_manifest_id, "
            "operation_sequence, source_receipt_sequence "
            "FROM capacity_measurement_operation_attempts_v49f",
        ),
    ),
)
def test_attempt_terminal_and_locator_database_mutations_reject(
    lifecycle_database_snapshots: dict[str, Any],
    tmp_path: Path,
    snapshot: str,
    statement: str,
) -> None:
    path = tmp_path / f"mutated-{snapshot}.sqlite3"
    shutil.copy2(lifecycle_database_snapshots[snapshot], path)
    connection = sqlite3.connect(path)
    try:
        connection.execute("PRAGMA foreign_keys = OFF")
        try:
            connection.execute(statement)
        except sqlite3.IntegrityError as exc:
            connection.rollback()
            assert "immutable" in str(exc)
            return
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(
        (PhysicalProjectionV4VerificationError, PhysicalProjectionV4ConfigurationError)
    ):
        PhysicalProjectionStoreV4(path, clock=lambda: T0 + timedelta(seconds=10))


@pytest.mark.parametrize(
    "stage",
    (
        "capacity_terminal_before_canonical_append",
        "after_canonical_record_insert",
        "after_receipt_insert",
        "capacity_terminal_after_canonical_append",
        "capacity_terminal_after_typed_insert",
        "capacity_terminal_after_locator_delete",
        "after_operation_batch_insert",
        "capacity_terminal_after_batch_finish",
        "capacity_terminal_before_commit",
        "before_commit",
        "capacity_terminal_after_rollback",
    ),
)
def test_recovery_terminal_faults_leave_only_atomic_open_or_closed_state(
    lifecycle_database_snapshots: dict[str, Any],
    tmp_path: Path,
    stage: str,
) -> None:
    path = tmp_path / f"recovery-{stage}.sqlite3"
    shutil.copy2(lifecycle_database_snapshots["open"], path)
    attempt_id = lifecycle_database_snapshots["attempt_id"]
    store = PhysicalProjectionStoreV4(
        path,
        clock=lambda: T0 + timedelta(seconds=10),
    )
    try:
        store.claim_transport_runtime_writer_fence(
            lease_token_sha256="f" * 64,
            holder_id=f"v7-edge-{stage}",
        )
        capability = store._claim_capacity_measurement_startup_recovery_v49f()  # noqa: SLF001

        if stage == "capacity_terminal_after_rollback":

            def inject(observed: str) -> None:
                if observed == "capacity_terminal_before_commit":
                    raise _InjectedRecoveryFault(observed)
                if observed == "capacity_terminal_after_rollback":
                    raise _InjectedRecoveryRollbackFault(observed)

            expected_error: type[RuntimeError] = _InjectedRecoveryRollbackFault
        else:

            def inject(observed: str) -> None:
                if observed == stage:
                    raise _InjectedRecoveryFault(observed)

            expected_error = _InjectedRecoveryFault

        store._fault_injector = inject  # noqa: SLF001
        with pytest.raises(expected_error, match=stage):
            store.recover_capacity_measurement_operation_terminal_v49f(
                capability,
                attempt_id,
                idempotency_key="v7-edge-recovery",
            )
        assert not store._connection.in_transaction  # noqa: SLF001
        assert _capacity_identity_counts(store, attempt_id=attempt_id) == (
            1,
            1,
            1,
            0,
            1,
        )
        store.verify()

        store._fault_injector = None  # noqa: SLF001
        recovered = store.recover_capacity_measurement_operation_terminal_v49f(
            capability,
            attempt_id,
            idempotency_key="v7-edge-recovery",
        )
        assert recovered.terminal is not None
        assert recovered.terminal.terminal_trigger is (
            CapacityMeasurementLifecycleTerminalTriggerV49F.RECOVERED_ORPHAN
        )
        assert _capacity_identity_counts(
            store,
            attempt_id=attempt_id,
            terminal_id=str(recovered.terminal.terminal_id),
        ) == (2, 2, 1, 1, 0)
        store.complete_capacity_measurement_startup_recovery_v49f(capability)
        store.verify()
    finally:
        store._fault_injector = None  # noqa: SLF001
        store.close()


def test_receipt_complete_prefix_rejects_valid_but_unexplained_attempt_splice() -> None:
    manifest, _ = _v7_manifest_and_expectation()
    sample = _returned_sample(manifest)
    prefix = sample.recovered_prefix
    foreign_attempt = _attempt(
        manifest,
        attempt_changes={"observer_start_offset_nanoseconds": 31},
    )
    foreign_receipt, foreign_record = _projection_commit(
        foreign_attempt,
        record_kind=A2M_OPERATION_ATTEMPT_RECORD_KIND_V49F_V7,
        identity_id=str(foreign_attempt.attempt_id),
        ledger_id=manifest.projection_authority.projection_ledger_id,
        global_sequence=prefix.projection_receipts[-2].global_sequence + 1,
        previous_receipt_hash=prefix.projection_receipts[-2].receipt_hash,
    )
    assert prefix.terminal is not None
    terminal_receipt, terminal_record = _projection_commit(
        prefix.terminal,
        record_kind=A2M_OPERATION_TERMINAL_RECORD_KIND_V49F_V7,
        identity_id=str(prefix.terminal.terminal_id),
        ledger_id=manifest.projection_authority.projection_ledger_id,
        global_sequence=foreign_receipt.global_sequence + 1,
        previous_receipt_hash=foreign_receipt.receipt_hash,
    )

    with pytest.raises(CanonicalizationError):
        CapacityMeasurementOperationPrefixV49F(
            attempt=prefix.attempt,
            terminal=prefix.terminal,
            new_raw_ingress_commits=prefix.new_raw_ingress_commits,
            raw_dependencies=prefix.raw_dependencies,
            actor_events=prefix.actor_events,
            projection_receipts=(
                *prefix.projection_receipts[:-1],
                foreign_receipt,
                terminal_receipt,
            ),
            projection_records=(
                *prefix.projection_records[:-1],
                foreign_record,
                terminal_record,
            ),
        )


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("effect_certainty", CapacityMeasurementLifecycleEffectCertaintyV49F.COMPLETE),
        (
            "progress_availability",
            CapacityMeasurementLifecycleProgressAvailabilityV49F.UNAVAILABLE,
        ),
        (
            "cancellation_classification",
            CapacityMeasurementLifecycleCancellationV49F.NONE,
        ),
    ),
)
def test_serialized_terminal_classifications_cannot_be_caller_relabelled(
    field: str,
    value: Any,
) -> None:
    manifest, _ = _v7_manifest_and_expectation()
    prefix = _cancelled_sample(manifest).recovered_prefix
    assert prefix.terminal is not None
    forged_terminal = v6_fixtures._forge_exact_record(  # noqa: SLF001
        prefix.terminal,
        **{field: value},
    )

    with pytest.raises(CanonicalizationError):
        replace(prefix, terminal=forged_terminal)


def test_frozen_v7_resource_limit_constants_are_exact() -> None:
    assert CAPACITY_MEASUREMENT_LIFECYCLE_MAXIMUM_PREFIX_BYTES_V49F == 48 * 1024 * 1024
    assert A2M_MAXIMUM_OPERATION_ATTEMPT_BYTES_V49F_V7 == 256 * 1024
    assert A2M_MAXIMUM_OPERATION_TERMINAL_BYTES_V49F_V7 == 256 * 1024
    assert A2M_MAXIMUM_MANIFEST_ARTIFACT_BYTES_V49F == 32 * 1024 * 1024
    assert A2M_MAXIMUM_SAMPLE_RECORD_BYTES_V49F == 64 * 1024 * 1024
    assert A2M_MAXIMUM_SAMPLES_ARTIFACT_BYTES_V49F == 256 * 1024 * 1024
    assert A2M_MAXIMUM_CORRECTNESS_ARTIFACT_BYTES_V49F == 4 * 1024 * 1024
    assert A2M_MAXIMUM_INTEGRITY_ARTIFACT_BYTES_V49F == 1 * 1024 * 1024
    assert A2M_MAXIMUM_ARTIFACT_CLOSURE_BYTES_V49F == 293 * 1024 * 1024
    assert A2M_MAXIMUM_TOTAL_TRIALS_V49F == 100_000
    assert CAPACITY_MEASUREMENT_MAXIMUM_JSON_NESTING_DEPTH_V49F_V7 == 64
    assert CAPACITY_MEASUREMENT_MAXIMUM_JSON_OBJECT_MEMBERS_V49F_V7 == 512
    assert CAPACITY_MEASUREMENT_MAXIMUM_JSON_ARRAY_ELEMENTS_V49F_V7 == 524_288


def test_v7_samples_artifact_length_arithmetic_accepts_exact_and_rejects_one_over() -> (
    None
):
    maximum = A2M_MAXIMUM_SAMPLES_ARTIFACT_BYTES_V49F
    measurement._validate_capacity_measurement_samples_length_v49f_v7(  # noqa: SLF001
        maximum
    )
    assert (
        measurement._accumulate_capacity_measurement_samples_length_v49f_v7(  # noqa: SLF001
            prior_length=maximum - 1,
            sample_record_length=1,
        )
        == maximum
    )
    with pytest.raises(CapacityMeasurementArtifactErrorV49F, match="samples artifact"):
        measurement._validate_capacity_measurement_samples_length_v49f_v7(  # noqa: SLF001
            maximum + 1
        )
    with pytest.raises(CapacityMeasurementArtifactErrorV49F, match="samples artifact"):
        measurement._accumulate_capacity_measurement_samples_length_v49f_v7(  # noqa: SLF001
            prior_length=maximum - 1,
            sample_record_length=2,
        )


def test_v7_artifact_closure_length_arithmetic_accepts_exact_and_rejects_one_over() -> (
    None
):
    maximum = A2M_MAXIMUM_ARTIFACT_CLOSURE_BYTES_V49F
    measurement._validate_capacity_measurement_artifact_closure_length_v49f_v7(  # noqa: SLF001
        maximum
    )
    with pytest.raises(CapacityMeasurementArtifactErrorV49F, match="total byte bound"):
        measurement._validate_capacity_measurement_artifact_closure_length_v49f_v7(  # noqa: SLF001
            maximum + 1
        )


@pytest.mark.parametrize(
    ("artifact_name", "maximum"),
    tuple(sorted(measurement._ARTIFACT_BYTE_LIMITS_V49F.items())),  # noqa: SLF001
)
def test_v7_artifact_member_length_map_rejects_each_member_one_over(
    artifact_name: str,
    maximum: int,
) -> None:
    exact = dict.fromkeys(measurement._BUNDLE_ARTIFACT_NAMES, 0)  # noqa: SLF001
    exact[artifact_name] = maximum
    measurement._validate_capacity_measurement_artifact_member_lengths_v49f_v7(  # noqa: SLF001
        exact
    )
    with pytest.raises(CapacityMeasurementArtifactErrorV49F, match=artifact_name):
        measurement._validate_capacity_measurement_artifact_member_lengths_v49f_v7(  # noqa: SLF001
            {**exact, artifact_name: maximum + 1}
        )


@pytest.mark.parametrize("nested", (False, True))
def test_v7_json_guard_array_elements_accept_exact_and_reject_one_over(
    nested: bool,
) -> None:
    maximum = CAPACITY_MEASUREMENT_MAXIMUM_JSON_ARRAY_ELEMENTS_V49F_V7
    exact_array = b"[" + b"0," * (maximum - 1) + b"0]"
    exact = b'{"nested":' + exact_array + b"}" if nested else exact_array
    validate_capacity_measurement_json_structure_before_parse_v49f_v7(exact)

    over_array = b"[" + b"0," * maximum + b"0]"
    over = b'{"nested":' + over_array + b"}" if nested else over_array
    with pytest.raises(
        CanonicalizationError,
        match=CAPACITY_MEASUREMENT_JSON_ARRAY_ELEMENT_LIMIT_EXCEEDED_V49F_V7,
    ):
        validate_capacity_measurement_json_structure_before_parse_v49f_v7(over)


@pytest.mark.parametrize("nested", (False, True))
def test_v7_json_guard_object_members_accept_exact_and_reject_one_over(
    nested: bool,
) -> None:
    maximum = CAPACITY_MEASUREMENT_MAXIMUM_JSON_OBJECT_MEMBERS_V49F_V7

    def object_bytes(count: int) -> bytes:
        return (
            b"{"
            + b",".join(f'"member_{index}":0'.encode("ascii") for index in range(count))
            + b"}"
        )

    exact_object = object_bytes(maximum)
    exact = b"[" + exact_object + b"]" if nested else exact_object
    validate_capacity_measurement_json_structure_before_parse_v49f_v7(exact)

    over_object = object_bytes(maximum + 1)
    over = b"[" + over_object + b"]" if nested else over_object
    with pytest.raises(
        CanonicalizationError,
        match=CAPACITY_MEASUREMENT_JSON_OBJECT_MEMBER_LIMIT_EXCEEDED_V49F_V7,
    ):
        validate_capacity_measurement_json_structure_before_parse_v49f_v7(over)


def test_v7_json_guard_nesting_depth_accepts_exact_and_rejects_one_over() -> None:
    maximum = CAPACITY_MEASUREMENT_MAXIMUM_JSON_NESTING_DEPTH_V49F_V7
    exact = b"[" * maximum + b"0" + b"]" * maximum
    validate_capacity_measurement_json_structure_before_parse_v49f_v7(exact)

    over = b"[" * (maximum + 1) + b"0" + b"]" * (maximum + 1)
    with pytest.raises(
        CanonicalizationError,
        match=CAPACITY_MEASUREMENT_JSON_DEPTH_LIMIT_EXCEEDED_V49F_V7,
    ):
        validate_capacity_measurement_json_structure_before_parse_v49f_v7(over)


@pytest.mark.parametrize(
    "payload",
    (
        b"]",
        b"[}",
        b"[0",
        b'{"value":0',
        b"[0,]",
        b'{"value":0,}',
        b'["\\x"]',
    ),
)
def test_v7_json_guard_normalizes_malformed_structure(payload: bytes) -> None:
    with pytest.raises(
        CanonicalizationError,
        match=CAPACITY_MEASUREMENT_JSON_MALFORMED_STRUCTURE_V49F_V7,
    ):
        validate_capacity_measurement_json_structure_before_parse_v49f_v7(payload)


def test_v7_json_guard_ignores_structure_inside_strings_and_honors_escapes() -> None:
    payload = canonical_json_bytes(
        {
            "escaped": 'quote=" slash=\\ braces={} brackets=[] comma=, colon=:',
            "literal": "[,]{}:,",
        }
    )
    validate_capacity_measurement_json_structure_before_parse_v49f_v7(payload)
    validate_capacity_measurement_json_structure_before_parse_v49f_v7(
        b'{"punctuation":"[,]{}:,","unicode_brace":"\\u007b"}'
    )


@pytest.mark.parametrize(
    "surface",
    ("manifest_member", "samples_jsonl", "singleton_correctness"),
)
def test_v7_json_guard_runs_on_each_artifact_decode_before_strict_json(
    monkeypatch: pytest.MonkeyPatch,
    surface: str,
) -> None:
    manifest = _v7_manifest_and_expectation()[0] if surface == "samples_jsonl" else None
    parse_started = False

    def forbidden_parse(_: bytes) -> Any:
        nonlocal parse_started
        parse_started = True
        raise AssertionError("strict_json_loads must not run")

    monkeypatch.setattr(measurement, "strict_json_loads", forbidden_parse)
    maximum = CAPACITY_MEASUREMENT_MAXIMUM_JSON_NESTING_DEPTH_V49F_V7
    payload = b"[" * (maximum + 1) + b"0" + b"]" * (maximum + 1) + b"\n"
    with pytest.raises(
        CanonicalizationError,
        match=CAPACITY_MEASUREMENT_JSON_DEPTH_LIMIT_EXCEEDED_V49F_V7,
    ):
        if surface == "samples_jsonl":
            decode_capacity_measurement_samples_jsonl_v49f_v7(
                payload,
                manifest=manifest,
            )
        else:
            record_type = (
                CapacityMeasurementManifestV49FV7
                if surface == "manifest_member"
                else CapacityMeasurementCorrectnessV49FV7
            )
            decode_capacity_measurement_json_v49f_v7(
                payload,
                record_type=record_type,
            )
    assert not parse_started


def test_v7_manifest_guards_embedded_workload_json_before_nested_parse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest, _ = _v7_manifest_and_expectation()
    payload = strict_json_loads(canonical_json_bytes(manifest.as_dict()))
    payload["campaign_manifest_id"] = None
    predecessor = payload["predecessor_manifest_v6"]
    predecessor["campaign_manifest_id"] = None
    maximum = CAPACITY_MEASUREMENT_MAXIMUM_JSON_NESTING_DEPTH_V49F_V7
    predecessor["workloads"][0]["workload_manifest_json"] = (
        "[" * (maximum + 1) + "0" + "]" * (maximum + 1)
    )
    parse_started = False

    def forbidden_parse(_: bytes) -> Any:
        nonlocal parse_started
        parse_started = True
        raise AssertionError("nested strict_json_loads must not run")

    monkeypatch.setattr(measurement, "strict_json_loads", forbidden_parse)
    with pytest.raises(
        CanonicalizationError,
        match=CAPACITY_MEASUREMENT_JSON_DEPTH_LIMIT_EXCEEDED_V49F_V7,
    ):
        CapacityMeasurementManifestV49FV7.from_mapping(payload)
    assert not parse_started


@pytest.mark.parametrize(
    ("surface", "maximum"),
    (
        ("prefix", CAPACITY_MEASUREMENT_LIFECYCLE_MAXIMUM_PREFIX_BYTES_V49F),
        ("attempt", CAPACITY_MEASUREMENT_LIFECYCLE_MAXIMUM_RECORD_BYTES_V49F),
        ("terminal", CAPACITY_MEASUREMENT_LIFECYCLE_MAXIMUM_RECORD_BYTES_V49F),
    ),
)
def test_lifecycle_canonical_byte_limits_accept_exact_and_reject_one_over(
    surface: str,
    maximum: int,
) -> None:
    exact = {"x": "a" * (maximum - len(b'{"x":""}'))}
    assert (
        len(
            lifecycle._bounded_canonical_bytes(  # noqa: SLF001
                exact,
                context=surface,
                maximum=maximum,
            )
        )
        == maximum
    )
    over = {"x": exact["x"] + "a"}
    with pytest.raises(CanonicalizationError, match="canonical bound"):
        lifecycle._bounded_canonical_bytes(  # noqa: SLF001
            over,
            context=surface,
            maximum=maximum,
        )


@pytest.mark.parametrize(
    ("record_type", "maximum"),
    (
        (CapacityMeasurementManifestV49FV7, A2M_MAXIMUM_MANIFEST_ARTIFACT_BYTES_V49F),
        (CapacityMeasurementSampleV49FV7, A2M_MAXIMUM_SAMPLE_RECORD_BYTES_V49F),
        (
            CapacityMeasurementCorrectnessV49FV7,
            A2M_MAXIMUM_CORRECTNESS_ARTIFACT_BYTES_V49F,
        ),
        (
            measurement.CapacityMeasurementIntegrityV49FV7,
            A2M_MAXIMUM_INTEGRITY_ARTIFACT_BYTES_V49F,
        ),
    ),
)
def test_v7_json_member_limits_accept_exact_and_reject_one_over_before_parse(
    monkeypatch: pytest.MonkeyPatch,
    record_type: type[Any],
    maximum: int,
) -> None:
    def parse_reached(_: bytes) -> Any:
        raise _ParseReached

    monkeypatch.setattr(measurement, "strict_json_loads", parse_reached)
    exact = b"0" + b" " * (maximum - 2) + b"\n"
    with pytest.raises(_ParseReached):
        decode_capacity_measurement_json_v49f_v7(exact, record_type=record_type)
    del exact

    over = b" " * maximum + b"\n"
    with pytest.raises(CapacityMeasurementArtifactErrorV49F, match="bounded"):
        decode_capacity_measurement_json_v49f_v7(over, record_type=record_type)


def test_v7_sample_count_and_safe_integer_edges_are_exact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest, _ = _v7_manifest_and_expectation()

    def parse_reached(_: bytes) -> Any:
        raise _ParseReached

    with monkeypatch.context() as patcher:
        patcher.setattr(measurement, "strict_json_loads", parse_reached)
        with pytest.raises(_ParseReached):
            decode_capacity_measurement_samples_jsonl_v49f_v7(
                b"{}\n" * A2M_MAXIMUM_TOTAL_TRIALS_V49F,
                manifest=manifest,
            )
        with pytest.raises(CapacityMeasurementArtifactErrorV49F, match="bounded"):
            decode_capacity_measurement_samples_jsonl_v49f_v7(
                b"{}\n" * (A2M_MAXIMUM_TOTAL_TRIALS_V49F + 1),
                manifest=manifest,
            )

    assert (
        _attempt(
            manifest,
            attempt_changes={"observer_start_offset_nanoseconds": MAX_IJSON_INTEGER},
        ).observer_start_offset_nanoseconds
        == MAX_IJSON_INTEGER
    )
    with pytest.raises(CanonicalizationError, match="I-JSON safe integer"):
        _attempt(
            manifest,
            attempt_changes={
                "observer_start_offset_nanoseconds": MAX_IJSON_INTEGER + 1
            },
        )


def test_exception_class_limit_is_enforced_in_utf8_bytes() -> None:
    exact = "é" * (
        CAPACITY_MEASUREMENT_LIFECYCLE_MAXIMUM_EXCEPTION_CLASS_UTF8_BYTES_V49F // 2
    )
    observation = CapacityMeasurementSameTaskTerminalObservationV49F(
        terminal_trigger=CapacityMeasurementLifecycleTerminalTriggerV49F.RAISED_EXCEPTION,
        surfaced_exception_class=exact,
        exception_class_chain=(exact,),
        exception_message_sha256_chain=(hashlib.sha256(b"").hexdigest(),),
        runtime_state_after="READY",
        observer_end_offset_nanoseconds=1,
        boottime_end_offset_nanoseconds=1,
        loop_time_end_offset_nanoseconds=1,
    )
    assert len(observation.surfaced_exception_class.encode("utf-8")) == 256

    over = exact + "é"
    with pytest.raises(CanonicalizationError, match="256 UTF-8 bytes"):
        CapacityMeasurementSameTaskTerminalObservationV49F(
            terminal_trigger=CapacityMeasurementLifecycleTerminalTriggerV49F.RAISED_EXCEPTION,
            surfaced_exception_class=over,
            exception_class_chain=(over,),
            exception_message_sha256_chain=(hashlib.sha256(b"").hexdigest(),),
            runtime_state_after="READY",
            observer_end_offset_nanoseconds=1,
            boottime_end_offset_nanoseconds=1,
            loop_time_end_offset_nanoseconds=1,
        )


@pytest.mark.parametrize(
    "direction",
    (
        "v7_sample_into_v6",
        "v6_sample_into_v7",
        "v7_bundle_into_v6",
        "v6_bundle_into_v7",
    ),
)
def test_v6_v7_sample_and_bundle_versions_never_auto_upgrade(direction: str) -> None:
    v7_manifest, v7_expectation = _v7_manifest_and_expectation()
    v7_bundle = _bundle(v7_manifest)
    v6_bundle = v6_fixtures._bundle()  # noqa: SLF001

    if direction == "v7_sample_into_v6":
        payload = encode_capacity_measurement_json_v49f_v7(v7_bundle.samples[0])
        with pytest.raises(CanonicalizationError):
            decode_capacity_measurement_json_v49f(
                payload,
                record_type=CapacityMeasurementSampleV49F,
            )
    elif direction == "v6_sample_into_v7":
        payload = encode_capacity_measurement_json_v49f(v6_bundle.samples[0])
        with pytest.raises(CanonicalizationError):
            decode_capacity_measurement_json_v49f_v7(
                payload,
                record_type=CapacityMeasurementSampleV49FV7,
            )
    elif direction == "v7_bundle_into_v6":
        with pytest.raises(
            (CanonicalizationError, CapacityMeasurementArtifactErrorV49F)
        ):
            CapacityMeasurementArtifactBundleV49F.from_artifact_bytes(
                v7_bundle.artifact_bytes()
            )
    else:
        with pytest.raises(
            (CanonicalizationError, CapacityMeasurementArtifactErrorV49F)
        ):
            CapacityMeasurementArtifactBundleV49FV7.from_artifact_bytes(
                v6_bundle.artifact_bytes(),
                expectation=v7_expectation,
            )


def _second_cancelled_sample(
    manifest: CapacityMeasurementManifestV49FV7,
    previous: CapacityMeasurementSampleV49FV7,
) -> CapacityMeasurementSampleV49FV7:
    prior_terminal = previous.terminal
    prior_receipt = previous.recovered_prefix.projection_receipts[-1]
    parser_cursor = previous.attempt.parser_cursor_before
    for event in previous.recovered_prefix.actor_events:
        if event.event_kind.value == "PARSER_TRANSITION":
            parser_cursor = event.payload.cursor_after
    template = _cancelled_sample(manifest)
    attempt = _attempt(
        manifest,
        declaration_changes={
            "sample_sequence": 2,
            "operation_sequence": 2,
            "trial_index": 1,
            "repetition_index": 0,
            "is_warmup": False,
        },
        attempt_changes={
            "previous_operation_terminal_id": prior_terminal.terminal_id,
            "pre_attempt_receipt_sequence": prior_receipt.global_sequence,
            "pre_attempt_receipt_hash": prior_receipt.receipt_hash,
            "baseline_raw_ingress_sequence": prior_terminal.terminal_raw_ingress_sequence,
            "baseline_raw_ingress_commit_id": prior_terminal.terminal_raw_ingress_commit_id,
            "baseline_actor_event_count": prior_terminal.terminal_actor_event_count,
            "baseline_actor_tail_event_id": prior_terminal.terminal_actor_tail_event_id,
            "parser_cursor_before": parser_cursor,
            "parser_cursor_id_before": parser_cursor.parser_cursor_id,
            "runtime_state_before": prior_terminal.runtime_state_after,
        },
    )
    attempt_receipt, attempt_record = _projection_commit(
        attempt,
        record_kind=A2M_OPERATION_ATTEMPT_RECORD_KIND_V49F_V7,
        identity_id=str(attempt.attempt_id),
        ledger_id=manifest.projection_authority.projection_ledger_id,
        global_sequence=prior_receipt.global_sequence + 1,
        previous_receipt_hash=prior_receipt.receipt_hash,
    )
    open_prefix = CapacityMeasurementOperationPrefixV49F(
        attempt=attempt,
        terminal=None,
        new_raw_ingress_commits=(),
        raw_dependencies=(),
        actor_events=(),
        projection_receipts=(attempt_receipt,),
        projection_records=(attempt_record,),
    )
    terminal = replace(
        template.terminal,
        attempt_id=attempt.attempt_id,
        previous_operation_terminal_id=prior_terminal.terminal_id,
        terminal_raw_ingress_sequence=attempt.baseline_raw_ingress_sequence,
        terminal_raw_ingress_commit_id=attempt.baseline_raw_ingress_commit_id,
        terminal_actor_event_count=attempt.baseline_actor_event_count,
        terminal_actor_tail_event_id=attempt.baseline_actor_tail_event_id,
        parser_cursor_id_after=attempt.parser_cursor_id_before,
        runtime_state_after=attempt.runtime_state_before,
        recovered_prefix_id=open_prefix.recovered_prefix_id,
        terminal_id=None,
    )
    terminal_receipt, terminal_record = _projection_commit(
        terminal,
        record_kind=A2M_OPERATION_TERMINAL_RECORD_KIND_V49F_V7,
        identity_id=str(terminal.terminal_id),
        ledger_id=manifest.projection_authority.projection_ledger_id,
        global_sequence=attempt_receipt.global_sequence + 1,
        previous_receipt_hash=attempt_receipt.receipt_hash,
    )
    prefix = CapacityMeasurementOperationPrefixV49F(
        attempt=attempt,
        terminal=terminal,
        new_raw_ingress_commits=(),
        raw_dependencies=(),
        actor_events=(),
        projection_receipts=(attempt_receipt, terminal_receipt),
        projection_records=(attempt_record, terminal_record),
    )
    return CapacityMeasurementSampleV49FV7(
        committed_attempt=CapacityMeasurementCommittedLifecycleRecordV49FV7(
            record=attempt,
            projection_receipt=attempt_receipt,
        ),
        committed_terminal=CapacityMeasurementCommittedLifecycleRecordV49FV7(
            record=terminal,
            projection_receipt=terminal_receipt,
        ),
        recovered_prefix=prefix,
        observation=template.observation,
    )


@pytest.mark.parametrize(
    "mutation",
    ("empty", "missing_first", "reordered", "after_run_end", "short_nonterminal"),
)
def test_v7_structural_sample_stream_closure_rejects_each_invalid_shape(
    mutation: str,
) -> None:
    manifest, _ = _v7_manifest_and_expectation()
    first = _returned_sample(manifest)
    second = _second_cancelled_sample(manifest, first)
    valid = (first, second)
    assert (
        validate_capacity_measurement_samples_v49f_v7(valid, manifest=manifest) == valid
    )
    early_terminal = _cancelled_sample(manifest)
    after_early_terminal = _second_cancelled_sample(manifest, early_terminal)
    candidates = {
        "empty": (),
        "missing_first": (second,),
        "reordered": (second, first),
        "after_run_end": (early_terminal, after_early_terminal),
        "short_nonterminal": (first,),
    }

    with pytest.raises(CanonicalizationError):
        validate_capacity_measurement_samples_v49f_v7(
            candidates[mutation],
            manifest=manifest,
        )


def test_complete_coverage_cannot_be_claimed_after_early_run_ending_terminal() -> None:
    manifest, _ = _v7_manifest_and_expectation()
    bundle = _bundle(manifest)
    forged = replace(
        bundle.correctness,
        schedule_coverage=CapacityMeasurementScheduleCoverageV49FV7.COMPLETE,
        expected_sample_count=1,
        correctness_id=None,
    )

    with pytest.raises(CanonicalizationError):
        CapacityMeasurementArtifactBundleV49FV7.build(
            manifest=manifest,
            samples=bundle.samples,
            correctness=forged,
        )
