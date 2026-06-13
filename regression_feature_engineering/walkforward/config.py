"""Configuration for clean RPF walk-forward optimization."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

from regression_feature_engineering.walkforward.model import CatBoostConfig
from regression_feature_engineering.walkforward.policy import (
    ALL_MANIFEST_FEATURES,
    FROZEN_PANEL,
    TARGET_SPECIFIC_V2,
    FeaturePolicyConfig,
)


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = PACKAGE_ROOT / "configs" / "rpf_clean_walkforward_v1.json"


@dataclass(frozen=True)
class CleanWalkForwardConfig:
    asset: str = "BTCUSDT"
    root: str = "8h/B"
    root_id: str = "8h_b"
    feature_set: str = "regression_path_features_v1"
    target_variant: str = "distance_horizon_vol_v2"
    target_col: str = "target_reg_direction_extreme_up_share_hvol_v2"
    feature_source: str = "regression_only"
    feature_policy: str = ALL_MANIFEST_FEATURES
    feature_ablation: str = "all"
    lookback_batches: int = 120
    val_batches: int = 10
    embargo_batches: int = 0
    n_steps: int = 20
    min_prediction_unique: int = 10
    min_prediction_std: float = 1e-6
    max_collapsed_window_rate: float = 0.25
    min_prediction_to_target_std_ratio: float = 0.10
    policy: FeaturePolicyConfig = FeaturePolicyConfig()
    model: CatBoostConfig = CatBoostConfig()


def load_clean_config(path: Path | None = None) -> CleanWalkForwardConfig:
    path = path or DEFAULT_CONFIG_PATH
    if not path.exists():
        return CleanWalkForwardConfig()
    payload = json.loads(path.read_text())
    policy_payload = payload.get("policy", {})
    model_payload = payload.get("model", {})
    base = CleanWalkForwardConfig(
        asset=str(payload.get("asset", "BTCUSDT")),
        root=str(payload.get("root", "8h/B")),
        root_id=str(payload.get("root_id", "8h_b")),
        feature_set=str(payload.get("feature_set", "regression_path_features_v1")),
        target_variant=str(payload.get("target_variant", "distance_horizon_vol_v2")),
        target_col=str(payload.get("target_col", "target_reg_direction_extreme_up_share_hvol_v2")),
        feature_source=str(payload.get("feature_source", "regression_only")),
        feature_policy=str(payload.get("feature_policy", ALL_MANIFEST_FEATURES)),
        feature_ablation=str(payload.get("feature_ablation", "all")),
        lookback_batches=int(payload.get("lookback_batches", 120)),
        val_batches=int(payload.get("val_batches", 10)),
        embargo_batches=int(payload.get("embargo_batches", 0)),
        n_steps=int(payload.get("n_steps", 20)),
        min_prediction_unique=int(payload.get("min_prediction_unique", 10)),
        min_prediction_std=float(payload.get("min_prediction_std", 1e-6)),
        max_collapsed_window_rate=float(payload.get("max_collapsed_window_rate", 0.25)),
        min_prediction_to_target_std_ratio=float(payload.get("min_prediction_to_target_std_ratio", 0.10)),
        policy=FeaturePolicyConfig(**policy_payload),
        model=CatBoostConfig(**model_payload),
    )
    if base.feature_source != "regression_only":
        raise ValueError("Clean RPF walk-forward only supports feature_source=regression_only")
    if base.feature_policy not in {ALL_MANIFEST_FEATURES, TARGET_SPECIFIC_V2, FROZEN_PANEL}:
        raise ValueError(
            "Clean RPF walk-forward supports feature_policy=all_manifest_features "
            "or feature_policy=target_specific_v2 or feature_policy=frozen_panel"
        )
    return base


def config_to_dict(config: CleanWalkForwardConfig) -> dict[str, Any]:
    payload = asdict(config)
    payload["policy"] = asdict(config.policy)
    payload["model"] = asdict(config.model)
    return payload


def merge_config(config: CleanWalkForwardConfig, **updates: Any) -> CleanWalkForwardConfig:
    policy_updates = updates.pop("policy", None)
    model_updates = updates.pop("model", None)
    if policy_updates:
        config = replace(config, policy=replace(config.policy, **policy_updates))
    if model_updates:
        config = replace(config, model=replace(config.model, **model_updates))
    if updates:
        config = replace(config, **updates)
    return config
