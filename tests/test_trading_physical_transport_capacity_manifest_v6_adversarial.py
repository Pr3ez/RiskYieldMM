from __future__ import annotations

from dataclasses import fields, replace
from typing import Any

import pytest

import riskyieldmm.trading.physical_transport_capacity_manifest_authority_v49f as authority_contract
import riskyieldmm.trading.physical_transport_capacity_measurement_v49f as measurement
from riskyieldmm.trading.canonical import (
    CanonicalizationError,
    canonical_json_bytes,
    strict_json_loads,
)
from riskyieldmm.trading.ledger_signing import Ed25519CheckpointSigner
from riskyieldmm.trading.physical_transport_capacity_manifest_authority_v49f import (
    AdmittedCapacityMeasurementAuthorityExpectationV49F,
    CapacityMeasurementManifestAuthorityV49F,
    capacity_measurement_authority_subject_signing_payload_v49f,
    derive_capacity_measurement_manifest_authority_subject_id_v49f,
    verify_capacity_measurement_manifest_against_admitted_authority_v49f,
)
from riskyieldmm.trading.physical_transport_capacity_measurement_v49f import (
    CapacityMeasurementManifestV49F,
    CapacityMeasurementSampleV49F,
    decode_capacity_measurement_json_v49f,
    encode_capacity_measurement_json_v49f,
    validate_capacity_measurement_samples_v49f,
)
from riskyieldmm.trading.physical_transport_capacity_source_observation_v49f import (
    SourceObservationSnapshotV49F,
)
from riskyieldmm.trading.physical_transport_v4 import (
    derive_transport_attestation_key_id,
)
from tests.test_trading_physical_transport_capacity_measurement_v49f import (
    _TEST_MANIFEST_SIGNER,
    _forge_exact_record,
    _hash,
    _manifest,
    _samples,
)

_SEMANTIC_HEADERS = frozenset(
    {"canonicalization_version", "measurement_schema_version", "record_domain"}
)


def _rehash_manifest_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Recompute the public outer digest so tests reach authority validation."""

    result = strict_json_loads(canonical_json_bytes(payload))
    assert type(result) is dict
    result["campaign_manifest_id"] = measurement._semantic_identity_v49f(  # noqa: SLF001
        domain=measurement.A2M_MANIFEST_DOMAIN_V49F,
        payload={
            name: value
            for name, value in result.items()
            if name not in _SEMANTIC_HEADERS | {"campaign_manifest_id"}
        },
    )
    return result


def _rehash_sample_payload(payload: dict[str, Any]) -> dict[str, Any]:
    result = strict_json_loads(canonical_json_bytes(payload))
    assert type(result) is dict
    result["sample_id"] = measurement._semantic_identity_v49f(  # noqa: SLF001
        domain=measurement.A2M_SAMPLE_DOMAIN_V49F,
        payload={
            name: value
            for name, value in result.items()
            if name not in _SEMANTIC_HEADERS | {"sample_id"}
        },
    )
    return result


def _rehash_authority_payload(payload: dict[str, Any]) -> dict[str, Any]:
    result = strict_json_loads(canonical_json_bytes(payload))
    assert type(result) is dict
    result["manifest_authority_id"] = authority_contract._semantic_identity(  # noqa: SLF001
        domain=authority_contract.A2M_MANIFEST_AUTHORITY_ATTESTATION_DOMAIN_V49F,
        payload={
            name: value
            for name, value in result.items()
            if name not in _SEMANTIC_HEADERS | {"manifest_authority_id"}
        },
    )
    return result


def _resigned_authority(
    manifest: CapacityMeasurementManifestV49F,
    *,
    signer: Ed25519CheckpointSigner = _TEST_MANIFEST_SIGNER,
    **subject_changes: Any,
) -> CapacityMeasurementManifestAuthorityV49F:
    authority = manifest.manifest_authority
    subject = {
        name: getattr(authority, name)
        for name in authority._SUBJECT_FIELDS  # noqa: SLF001
    }
    subject.update(subject_changes)
    subject_id = derive_capacity_measurement_manifest_authority_subject_id_v49f(subject)
    key_id = derive_transport_attestation_key_id(signer.public_key_bytes)
    signature = signer.sign(
        canonical_json_bytes(
            capacity_measurement_authority_subject_signing_payload_v49f(
                authority_subject_id=subject_id,
                deployment_bundle_id=subject["deployment_bundle_id"],
                collector_attestation_key_id=key_id,
                transport_session_id=subject["transport_session_id"],
            )
        )
    )
    return CapacityMeasurementManifestAuthorityV49F(
        **subject,
        authority_subject_id=subject_id,
        signature_algorithm=authority.signature_algorithm,
        collector_attestation_key_id=key_id,
        collector_attestation_public_key_hex=signer.public_key_bytes.hex(),
        signature_hex=signature.hex(),
    )


def _admitted_expectation(
    manifest: CapacityMeasurementManifestV49F,
) -> AdmittedCapacityMeasurementAuthorityExpectationV49F:
    runtime = manifest.runtime_observation
    authority = manifest.manifest_authority
    return AdmittedCapacityMeasurementAuthorityExpectationV49F(
        authority_profile=runtime.authority_profile,
        transport_runtime_schema_version=runtime.transport_runtime_schema_version,
        deployment_bundle_id=runtime.deployment_bundle_id,
        deployment_sequence=runtime.deployment_sequence,
        deployment_trust_root_id=runtime.deployment_trust_root_id,
        environment_id=runtime.environment_id,
        collector_release_manifest_id=runtime.collector_release_manifest_id,
        collector_key_authorization_manifest_id=(
            runtime.collector_key_authorization_manifest_id
        ),
        collector_attestation_key_id=authority.collector_attestation_key_id,
        collector_attestation_public_key_hex=(
            authority.collector_attestation_public_key_hex
        ),
        runtime_environment_manifest_id=runtime.runtime_environment_manifest_id,
        collector_release_name=runtime.collector_release_name,
        collector_release_version=runtime.collector_release_version,
        collector_release_entrypoint=runtime.collector_release_entrypoint,
        release_source_tree_sha256=runtime.declared_source_tree_sha256,
        release_build_artifact_sha256=runtime.declared_build_artifact_sha256,
        tls_websocket_driver_policy_id=runtime.tls_websocket_driver_policy_id,
        transport_capacity_policy_id=runtime.transport_capacity_policy_id,
        clock_source_manifest_id=runtime.clock_source_manifest_id,
    )


@pytest.mark.parametrize(
    "nested_record",
    ("manifest_request", "source_observation", "runtime_observation", "process"),
)
def test_rehashed_nested_record_substitution_cannot_escape_signed_cross_links(
    nested_record: str,
) -> None:
    manifest = _manifest()
    payload = manifest.as_dict()

    if nested_record == "manifest_request":
        replacement = replace(
            manifest.manifest_request,
            campaign_label="v49f-a2m-foreign",
            manifest_request_id=None,
        )
        payload["campaign_label"] = replacement.campaign_label
        payload["manifest_request"] = replacement.as_dict()
        assert replacement.manifest_request_id != (
            manifest.manifest_request.manifest_request_id
        )
    elif nested_record == "source_observation":
        replacement = replace(
            manifest.source_observation,
            repository_root="/workspace/foreign-riskyieldmm",
            source_observation_id=None,
        )
        payload["source_observation"] = replacement.as_dict()
        assert replacement.source_observation_id != (
            manifest.source_observation.source_observation_id
        )
    elif nested_record == "runtime_observation":
        replacement = replace(
            manifest.runtime_observation,
            collector_release_name="riskyieldmm-foreign-collector",
            runtime_observation_id=None,
        )
        payload["runtime_identity_sha256"] = replacement.runtime_observation_id
        payload["runtime_observation"] = replacement.as_dict()
        assert replacement.runtime_observation_id != (
            manifest.runtime_observation.runtime_observation_id
        )
    else:
        replacement = replace(
            manifest.process_environment_observation,
            kernel_version="foreign-kernel-version",
            environment_observation_id=None,
        )
        payload["process_environment_observation"] = replacement.as_dict()
        assert replacement.environment_observation_id != (
            manifest.process_environment_observation.environment_observation_id
        )

    attacked = _rehash_manifest_payload(payload)
    assert attacked["campaign_manifest_id"] != manifest.campaign_manifest_id
    with pytest.raises(
        CanonicalizationError,
        match="signed manifest authority differs from its exact observations",
    ):
        CapacityMeasurementManifestV49F.from_mapping(attacked)


def test_foreign_signature_is_rejected_even_after_authority_and_manifest_rehash() -> (
    None
):
    manifest = _manifest()
    foreign_signer = Ed25519CheckpointSigner.from_private_bytes(bytes(range(1, 33)))
    authority_payload = manifest.manifest_authority.as_dict()
    authority_payload["signature_hex"] = foreign_signer.sign(
        canonical_json_bytes(
            capacity_measurement_authority_subject_signing_payload_v49f(
                authority_subject_id=manifest.manifest_authority.authority_subject_id,
                deployment_bundle_id=manifest.runtime_observation.deployment_bundle_id,
                collector_attestation_key_id=(
                    manifest.runtime_observation.collector_attestation_key_id
                ),
                transport_session_id=manifest.transport_session_id,
            )
        )
    ).hex()
    authority_payload = _rehash_authority_payload(authority_payload)
    payload = manifest.as_dict()
    payload["manifest_authority"] = authority_payload
    attacked = _rehash_manifest_payload(payload)

    with pytest.raises(CanonicalizationError, match="signature is invalid"):
        CapacityMeasurementManifestV49F.from_mapping(attacked)


def test_self_consistent_foreign_key_and_signature_cannot_replace_runtime_key() -> None:
    manifest = _manifest()
    foreign_signer = Ed25519CheckpointSigner.from_private_bytes(bytes(range(32, 64)))
    foreign_authority = _resigned_authority(manifest, signer=foreign_signer)
    assert foreign_authority.collector_attestation_key_id != (
        manifest.runtime_observation.collector_attestation_key_id
    )
    payload = manifest.as_dict()
    payload["manifest_authority"] = foreign_authority.as_dict()
    attacked = _rehash_manifest_payload(payload)

    with pytest.raises(
        CanonicalizationError,
        match="signed manifest authority differs from its exact observations",
    ):
        CapacityMeasurementManifestV49F.from_mapping(attacked)


def test_whole_closure_forgery_needs_an_independent_deployment_expectation() -> None:
    manifest = _manifest()
    runtime = manifest.runtime_observation
    expectation = _admitted_expectation(manifest)
    verify_capacity_measurement_manifest_against_admitted_authority_v49f(
        manifest=manifest,
        expectation=expectation,
    )

    foreign_signer = Ed25519CheckpointSigner.from_private_bytes(bytes(range(32, 64)))
    foreign_key_id = derive_transport_attestation_key_id(
        foreign_signer.public_key_bytes
    )
    foreign_runtime = replace(
        runtime,
        deployment_bundle_id=_hash("7"),
        collector_key_authorization_manifest_id=_hash("8"),
        collector_attestation_key_id=foreign_key_id,
        runtime_observation_id=None,
    )
    foreign_authority = _resigned_authority(
        manifest,
        signer=foreign_signer,
        deployment_bundle_id=foreign_runtime.deployment_bundle_id,
        runtime_observation_id=foreign_runtime.runtime_observation_id,
    )
    foreign_manifest = replace(
        manifest,
        runtime_identity_sha256=foreign_runtime.runtime_observation_id,
        runtime_observation=foreign_runtime,
        manifest_authority=foreign_authority,
        campaign_manifest_id=None,
    )
    assert (
        decode_capacity_measurement_json_v49f(
            encode_capacity_measurement_json_v49f(foreign_manifest),
            record_type=CapacityMeasurementManifestV49F,
        )
        == foreign_manifest
    )
    with pytest.raises(
        CanonicalizationError,
        match="differs from independently admitted deployment",
    ):
        verify_capacity_measurement_manifest_against_admitted_authority_v49f(
            manifest=foreign_manifest,
            expectation=expectation,
        )


@pytest.mark.parametrize(
    ("field", "replacement"),
    (
        ("deployment_sequence", 2),
        ("collector_release_version", "0.0.foreign"),
        ("tls_websocket_driver_policy_id", _hash("7")),
        ("transport_capacity_policy_id", _hash("8")),
        ("clock_source_manifest_id", _hash("9")),
    ),
)
def test_independent_expectation_rejects_resigned_static_deployment_contradiction(
    field: str,
    replacement: Any,
) -> None:
    manifest = _manifest()
    runtime = replace(
        manifest.runtime_observation,
        **{field: replacement, "runtime_observation_id": None},
    )
    authority_changes: dict[str, Any] = {
        "runtime_observation_id": runtime.runtime_observation_id,
    }
    manifest_changes: dict[str, Any] = {
        "runtime_identity_sha256": runtime.runtime_observation_id,
        "runtime_observation": runtime,
        "campaign_manifest_id": None,
    }
    if field == "transport_capacity_policy_id":
        authority_changes[field] = replacement
        manifest_changes[field] = replacement
    authority = _resigned_authority(manifest, **authority_changes)
    attacked = replace(
        manifest,
        manifest_authority=authority,
        **manifest_changes,
    )

    with pytest.raises(
        CanonicalizationError,
        match="differs from independently admitted deployment",
    ):
        verify_capacity_measurement_manifest_against_admitted_authority_v49f(
            manifest=attacked,
            expectation=_admitted_expectation(manifest),
        )


def test_oversized_nanosecond_text_is_rejected_before_integer_conversion() -> None:
    manifest = _manifest()
    payload = strict_json_loads(canonical_json_bytes(manifest.as_dict()))
    assert type(payload) is dict
    payload["monotonic_origin_nanoseconds"] = "9" * 10_000
    with pytest.raises(CanonicalizationError, match="unsigned integer text"):
        CapacityMeasurementManifestV49F.from_mapping(payload)

    with pytest.raises(CanonicalizationError, match="unsigned integer text"):
        replace(
            manifest.process_environment_observation,
            capture_started_monotonic_nanoseconds="9" * 10_000,
            environment_observation_id=None,
        )


def test_design_repetition_and_total_trial_bounds_fail_before_schedule_materialization() -> (
    None
):
    manifest = _manifest()
    with pytest.raises(CanonicalizationError):
        replace(
            manifest.design,
            measured_repetitions=measurement.MAX_IJSON_INTEGER,
            measurement_design_id=None,
        )

    bounded_fields_but_excessive_product = replace(
        manifest.design,
        warmup_repetitions=measurement.A2M_MAXIMUM_WARMUP_REPETITIONS_V49F,
        measured_repetitions=measurement.A2M_MAXIMUM_MEASURED_REPETITIONS_V49F,
        measurement_design_id=None,
    )
    with pytest.raises(CanonicalizationError, match="total-trial bound"):
        _manifest(design=bounded_fields_but_excessive_product)


def test_workload_count_is_bounded_before_corpus_hash_materialization() -> None:
    workload = _manifest().workloads[0]
    with pytest.raises(CanonicalizationError, match="bounded set"):
        measurement.capacity_measurement_workload_corpus_sha256_v49f(
            (workload,) * (measurement.A2M_MAXIMUM_WORKLOADS_V49F + 1)
        )


def test_custom_iterables_are_rejected_without_materialization() -> None:
    class ExplosiveIterable:
        def __iter__(self) -> Any:
            raise AssertionError("untrusted iterable was materialized")

    value = ExplosiveIterable()
    with pytest.raises(CanonicalizationError, match="bounded set"):
        measurement.capacity_measurement_workload_corpus_sha256_v49f(value)  # type: ignore[arg-type]
    with pytest.raises(CanonicalizationError, match="bounded set"):
        measurement.validate_capacity_measurement_samples_v49f(value)  # type: ignore[arg-type]


def test_json_and_jsonl_outer_bounds_precede_record_parsing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        measurement,
        "A2M_MAXIMUM_INTEGRITY_ARTIFACT_BYTES_V49F",
        8,
    )
    with pytest.raises(CanonicalizationError, match="bounded LF-terminated"):
        decode_capacity_measurement_json_v49f(
            b" " * 8 + b"\n",
            record_type=measurement.CapacityMeasurementIntegrityV49F,
        )

    monkeypatch.setattr(measurement, "A2M_MAXIMUM_SAMPLE_RECORD_BYTES_V49F", 8)
    monkeypatch.setattr(measurement, "A2M_MAXIMUM_SAMPLES_ARTIFACT_BYTES_V49F", 64)
    with pytest.raises(CanonicalizationError, match="record exceeds"):
        measurement.decode_capacity_measurement_samples_jsonl_v49f(
            b'{"oversized":true}\n'
        )

    monkeypatch.setattr(measurement, "A2M_MAXIMUM_TOTAL_TRIALS_V49F", 1)
    with pytest.raises(CanonicalizationError, match="record-count bound"):
        measurement.decode_capacity_measurement_samples_jsonl_v49f(b"{}\n{}\n")


def test_bundle_outer_member_bound_precedes_integrity_decode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(
        measurement._ARTIFACT_BYTE_LIMITS_V49F,  # noqa: SLF001
        measurement.INTEGRITY_ARTIFACT_NAME_V49F,
        0,
    )
    artifacts = dict.fromkeys(
        (
            measurement.MANIFEST_ARTIFACT_NAME_V49F,
            measurement.SAMPLES_ARTIFACT_NAME_V49F,
            measurement.CORRECTNESS_ARTIFACT_NAME_V49F,
            measurement.INTEGRITY_ARTIFACT_NAME_V49F,
        ),
        b"x",
    )
    with pytest.raises(CanonicalizationError, match="closure exceeds"):
        measurement.CapacityMeasurementArtifactBundleV49F.from_artifact_bytes(artifacts)


def test_observed_source_mismatch_with_signed_deployment_is_fail_closed() -> None:
    manifest = _manifest()
    mismatched = replace(
        manifest.source_observation,
        deployment_source_tree_sha256=_hash("7"),
        deployment_source_tree_matches=False,
        source_observation_id=None,
    )
    payload = manifest.as_dict()
    payload["source_observation"] = mismatched.as_dict()
    attacked = _rehash_manifest_payload(payload)

    with pytest.raises(
        CanonicalizationError,
        match="observed source differs from the signed deployment source tree",
    ):
        CapacityMeasurementManifestV49F.from_mapping(attacked)

    with pytest.raises(
        CanonicalizationError,
        match="deployment_source_tree_matches differs from compared hashes",
    ):
        replace(mismatched, deployment_source_tree_matches=True)


@pytest.mark.parametrize(
    ("alias_family", "expected_message"),
    (
        ("source", "manifest source aliases differ"),
        ("runtime", "manifest runtime aliases differ"),
        ("environment", "manifest environment aliases differ"),
    ),
)
def test_rehashed_manifest_rejects_source_runtime_and_environment_alias_drift(
    alias_family: str,
    expected_message: str,
) -> None:
    manifest = _manifest()
    payload = manifest.as_dict()
    if alias_family == "source":
        payload["source_revision"] = _hash("7")
    elif alias_family == "runtime":
        payload["transport_session_id"] = _hash("7")
    else:
        payload["environment"] = replace(
            manifest.environment,
            kernel_release="8.0.0-foreign",
            environment_id=None,
        ).as_dict()
    attacked = _rehash_manifest_payload(payload)

    with pytest.raises(CanonicalizationError, match=expected_message):
        CapacityMeasurementManifestV49F.from_mapping(attacked)


@pytest.mark.parametrize(
    ("authority_link", "foreign_identity"),
    (
        ("manifest_request_id", _hash("6")),
        ("source_observation_id", _hash("7")),
        ("runtime_observation_id", _hash("8")),
        ("environment_observation_id", _hash("9")),
    ),
)
def test_validly_resigned_authority_cannot_cross_link_a_foreign_nested_record(
    authority_link: str,
    foreign_identity: str,
) -> None:
    manifest = _manifest()
    foreign_authority = _resigned_authority(
        manifest,
        **{authority_link: foreign_identity},
    )
    assert foreign_authority.manifest_authority_id != (
        manifest.manifest_authority.manifest_authority_id
    )
    payload = manifest.as_dict()
    payload["manifest_authority"] = foreign_authority.as_dict()
    attacked = _rehash_manifest_payload(payload)

    with pytest.raises(
        CanonicalizationError,
        match="signed manifest authority differs from its exact observations",
    ):
        CapacityMeasurementManifestV49F.from_mapping(attacked)


def test_samples_remain_bound_to_manifest_authority_after_full_stream_rehash() -> None:
    manifest = _manifest()
    attacked_samples: list[CapacityMeasurementSampleV49F] = []
    parent_id: str | None = None
    for sample in _samples(manifest):
        payload = sample.as_dict()
        payload["manifest_authority_id"] = _hash("7")
        payload["parent_sample_id"] = parent_id
        attacked_payload = _rehash_sample_payload(payload)
        attacked_sample = CapacityMeasurementSampleV49F.from_mapping(attacked_payload)
        attacked_samples.append(attacked_sample)
        parent_id = attacked_sample.sample_id

    assert validate_capacity_measurement_samples_v49f(tuple(attacked_samples)) == tuple(
        attacked_samples
    )
    with pytest.raises(
        CanonicalizationError,
        match="sample differs from its exact manifest/session identity",
    ):
        validate_capacity_measurement_samples_v49f(
            tuple(attacked_samples), manifest=manifest
        )


@pytest.mark.parametrize(
    "record_type",
    (CapacityMeasurementManifestV49F, CapacityMeasurementSampleV49F),
)
def test_raw_v5_records_are_strictly_rejected_without_implicit_upgrade(
    record_type: type[CapacityMeasurementManifestV49F]
    | type[CapacityMeasurementSampleV49F],
) -> None:
    manifest = _manifest()
    record = (
        manifest
        if record_type is CapacityMeasurementManifestV49F
        else _samples(manifest)[0]
    )
    raw_v6 = encode_capacity_measurement_json_v49f(record)
    raw_v5 = raw_v6.replace(
        measurement.A2M_MEASUREMENT_SCHEMA_VERSION_V49F.encode("ascii"),
        measurement.A2M_LEGACY_DECLARED_PROVENANCE_SCHEMA_VERSION_V49F_V5.encode(
            "ascii"
        ),
    )
    assert raw_v5 != raw_v6
    assert (
        measurement.A2M_LEGACY_DECLARED_PROVENANCE_SCHEMA_VERSION_V49F_V5.encode(
            "ascii"
        )
        in raw_v5
    )

    with pytest.raises(CanonicalizationError, match="schema version|schema_version"):
        decode_capacity_measurement_json_v49f(raw_v5, record_type=record_type)


def test_manifest_rejects_subclassed_nested_record_even_with_identical_fields() -> None:
    manifest = _manifest()

    class ForeignSourceObservation(SourceObservationSnapshotV49F):
        pass

    subclassed = object.__new__(ForeignSourceObservation)
    for item in fields(SourceObservationSnapshotV49F):
        object.__setattr__(
            subclassed,
            item.name,
            getattr(manifest.source_observation, item.name),
        )
    assert subclassed.as_dict() == manifest.source_observation.as_dict()
    forged_manifest = _forge_exact_record(
        manifest,
        source_observation=subclassed,
    )

    with pytest.raises(CanonicalizationError, match="source_observation must be exact"):
        forged_manifest.as_dict()


def test_manifest_and_sample_public_boundaries_revalidate_forged_dataclasses() -> None:
    manifest = _manifest()
    forged_source = _forge_exact_record(
        manifest.source_observation,
        repository_root="/workspace/forged-riskyieldmm",
    )
    forged_manifest = _forge_exact_record(
        manifest,
        source_observation=forged_source,
    )
    with pytest.raises(CanonicalizationError, match="source_observation_id differs"):
        forged_manifest.as_dict()

    sample = _samples(manifest)[0]
    forged_sample = _forge_exact_record(
        sample,
        manifest_authority_id=_hash("7"),
    )
    with pytest.raises(CanonicalizationError, match="sample_id differs"):
        forged_sample.as_dict()
