"""Manifest and lineage contracts for regression feature artifacts."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RegressionFeatureManifest:
    """Minimum metadata required beside every regression feature root."""

    feature_set: str
    target_variant: str
    asset: str
    root_id: str
    row_count: int
    duplicate_count: int
    null_feature_count: int
    schema_hash: str
    source_fingerprint: str

