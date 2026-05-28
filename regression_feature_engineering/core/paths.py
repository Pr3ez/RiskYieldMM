"""Path helpers for regression feature artifacts."""

from __future__ import annotations

from pathlib import Path


FEATURE_SET = "regression_path_features_v1"
TARGET_VARIANT = "distance_horizon_vol_v2"


def regression_feature_root(data_root: Path, asset: str, root_id: str) -> Path:
    """Return the future output root for regression path features."""
    return data_root / "htf_multiasset" / asset.lower() / FEATURE_SET / root_id / "1m"

