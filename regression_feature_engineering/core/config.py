"""Configuration loading for regression feature engineering.

The module intentionally exposes metadata and validation helpers only. Feature
materialization will be added after the architecture and contracts are stable.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = PACKAGE_ROOT / "configs" / "regression_feature_engineering_v1.json"


@dataclass(frozen=True)
class RegressionFeatureConfig:
    """Parsed contract for the regression feature workspace."""

    feature_set: str
    target_variant: str
    core_assets: tuple[str, ...]
    roots: tuple[str, ...]
    root_ids: tuple[str, ...]
    targets: tuple[str, ...]
    output_path_template: str
    metadata_version: str


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> RegressionFeatureConfig:
    """Load and validate the active regression feature config."""
    payload = json.loads(path.read_text())
    return RegressionFeatureConfig(
        feature_set=str(payload["feature_set"]),
        target_variant=str(payload["target_variant"]),
        core_assets=tuple(payload["core_assets"]),
        roots=tuple(payload["roots"]),
        root_ids=tuple(payload["root_ids"]),
        targets=tuple(payload["targets"]),
        output_path_template=str(payload["output_path_template"]),
        metadata_version=str(payload["metadata_version"]),
    )

