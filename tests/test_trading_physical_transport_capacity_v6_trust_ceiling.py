from __future__ import annotations

from riskyieldmm.trading.physical_transport_capacity_measurement_v49f import (
    CapacityMeasurementArtifactBundleV49F,
)
from tests.test_trading_physical_transport_capacity_measurement_v49f import (
    _bundle,
    _samples,
    _unfinalized_correctness,
)


def test_v6_signed_manifest_does_not_authenticate_recomputed_offline_suffix() -> None:
    """Raw V6 manifest provenance must not be widened to its unsigned suffix."""

    original = _bundle()
    manifest = original.manifest

    # No signer or retained runtime capability participates in this alternate
    # closure.  A different, semantically valid observation can be selected and
    # every unsigned downstream identity/member digest recomputed offline.
    alternate_samples = _samples(
        manifest,
        measured_process_rss_bytes=11_000_000,
    )
    alternate = CapacityMeasurementArtifactBundleV49F.build(
        manifest=manifest,
        samples=alternate_samples,
        correctness=_unfinalized_correctness(manifest, alternate_samples),
    )

    original_bytes = original.artifact_bytes()
    alternate_bytes = alternate.artifact_bytes()
    assert original_bytes["manifest.json"] == alternate_bytes["manifest.json"]
    assert original_bytes["samples.jsonl"] != alternate_bytes["samples.jsonl"]
    assert original.evidence_bundle_id != alternate.evidence_bundle_id

    for candidate, artifacts in (
        (original, original_bytes),
        (alternate, alternate_bytes),
    ):
        assert (
            CapacityMeasurementArtifactBundleV49F.from_artifact_bytes(artifacts)
            == candidate
        )
        assert candidate.correctness.passed is False
