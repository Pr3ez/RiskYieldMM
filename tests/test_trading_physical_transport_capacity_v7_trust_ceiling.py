from __future__ import annotations

from dataclasses import replace

from riskyieldmm.trading.physical_transport_capacity_measurement_v49f import (
    A2M_POST_RUN_SUFFIX_PROVENANCE_UNATTESTED_V49F_V7,
    CapacityMeasurementArtifactBundleV49FV7,
    _sample_roots_v49f_v7,
    capacity_measurement_sample_stream_sha256_v49f_v7,
)
from tests.test_trading_physical_transport_capacity_measurement_v7_v49f import (
    _bundle,
    _cancelled_sample,
    _v7_manifest_and_expectation,
)


def test_signed_manifest_provenance_does_not_certify_unsigned_sample_suffix() -> None:
    """The admitted signature stops at the baseline, not the sample suffix."""

    manifest, expectation = _v7_manifest_and_expectation()
    original = _bundle(manifest)

    # No signer or retained runtime authority is used after manifest creation.
    # An offline editor can choose different plausible operation clocks and
    # recompute every downstream receipt, semantic identity, root, and digest.
    alternate_sample = _cancelled_sample(
        manifest,
        attempt_changes={"observer_start_offset_nanoseconds": 31},
    )
    alternate_samples = (alternate_sample,)
    raw_root, actor_root, projection_root = _sample_roots_v49f_v7(alternate_samples)
    alternate_correctness = replace(
        original.correctness,
        sample_stream_sha256=capacity_measurement_sample_stream_sha256_v49f_v7(
            alternate_samples,
            manifest=manifest,
        ),
        first_sample_id=alternate_sample.sample_id,
        last_sample_id=alternate_sample.sample_id,
        last_terminal_id=alternate_sample.terminal.terminal_id,
        raw_ingress_root_sha256=raw_root,
        actor_event_root_sha256=actor_root,
        projection_root_sha256=projection_root,
        correctness_id=None,
    )
    alternate = CapacityMeasurementArtifactBundleV49FV7.build(
        manifest=manifest,
        samples=alternate_samples,
        correctness=alternate_correctness,
    )

    original_bytes = original.artifact_bytes()
    alternate_bytes = alternate.artifact_bytes()
    assert original_bytes["manifest.json"] == alternate_bytes["manifest.json"]
    assert original_bytes["samples.jsonl"] != alternate_bytes["samples.jsonl"]
    assert original.correctness.projection_root_sha256 != projection_root
    assert original.evidence_bundle_id != alternate.evidence_bundle_id

    # The independent expectation verifies the shared manifest provenance.
    # Both divergent unsigned suffixes still pass canonical integrity replay.
    for candidate, artifacts in (
        (original, original_bytes),
        (alternate, alternate_bytes),
    ):
        assert (
            CapacityMeasurementArtifactBundleV49FV7.from_artifact_bytes(
                artifacts,
                expectation=expectation,
            )
            == candidate
        )
        assert candidate.correctness.passed is False
        assert (
            A2M_POST_RUN_SUFFIX_PROVENANCE_UNATTESTED_V49F_V7
            in candidate.correctness.failure_codes
        )
