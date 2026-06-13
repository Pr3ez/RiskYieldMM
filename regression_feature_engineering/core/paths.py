"""Path helpers for regression feature artifacts."""

from __future__ import annotations

from pathlib import Path


FEATURE_SET = "regression_path_features_v1"
TARGET_VARIANT = "distance_horizon_vol_v2"
REGRESSION_LABEL_SUFFIX = "reg_distance_horizon_vol_v2"


def regression_feature_root(data_root: Path, asset: str, root_id: str) -> Path:
    """Return the future output root for regression path features."""
    return data_root / "htf_multiasset" / asset.lower() / FEATURE_SET / root_id / "1m"


def regression_label_root(data_root: Path, asset: str, layout_label_root: str) -> Path:
    """Return the existing regression target label root for one Stage-1 layout."""

    return data_root / "htf_multiasset" / asset.lower() / f"{layout_label_root}_{REGRESSION_LABEL_SUFFIX}" / "1m"


def canonical_ohlcv_path(data_root: Path, asset: str, timeframe: str) -> Path:
    """Return the canonical OHLCV file for one asset/timeframe."""

    slug = asset.lower()
    return data_root / "htf_multiasset" / slug / "htf_canonical_ohlcv" / timeframe / f"{slug}_{timeframe}_canonical.parquet"
