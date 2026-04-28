from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


STAGE1_VERSION_V1 = "v1"
STAGE1_VERSION_V2 = "v2"
STAGE1_MODE_PREFIX = "stage1_isolated_"

STAGE1_V2_EXECUTION_MODE_PARITY = "parity"
STAGE1_V2_EXECUTION_MODE_NESTED = "nested_selector"
STAGE1_V2_EXECUTION_MODE_FIXED_POLICY = "fixed_policy"

STAGE1_V2_ARTIFACT_CONTRACT_VERSION = "2026-04-20-stage1-v2-contract-v1"
STAGE1_V2_FIXED_POLICY_ARTIFACT_CONTRACT_VERSION = (
    "2026-04-20-stage1-v2-fixed-policy-v1"
)

STAGE1_V2_ROOT_ARTIFACTS = {
    "run_summary": "stage1_v2_run_summary.json",
    "progress": "stage1_v2_progress.parquet",
    "feature_importance_global": "stage1_v2_feature_importance_global.parquet",
    "feature_mask_global": "stage1_v2_feature_mask_global.parquet",
    "feature_stability": "stage1_v2_feature_stability.parquet",
    "baseline_vs_selected_root": "stage1_v2_baseline_vs_selected_root.parquet",
    "winner_change_summary": "stage1_v2_winner_change_summary.parquet",
}

STAGE1_V2_FIXED_POLICY_ROOT_ARTIFACTS = {
    "registry": "stage1_v2_fixed_policy_registry.json",
    "build_summary": "stage1_v2_fixed_policy_build_summary.json",
    "details_dir": "stage1_v2_fixed_policy_build",
    "per_combo_feature_stats": "stage1_v2_fixed_policy_build/per_combo_feature_stats.parquet",
    "combo_policy_summary": "stage1_v2_fixed_policy_build/combo_policy_summary.parquet",
    "final_mask_features": "stage1_v2_fixed_policy_build/final_mask_features.parquet",
}

STAGE1_V2_STEP_ARTIFACTS = {
    "summary": "stage1_v2_step_summary.json",
    "combo_metrics": "stage1_v2_combo_metrics.parquet",
    "feature_importance_steps": "stage1_v2_feature_importance_steps.parquet",
    "selected_features": "stage1_v2_selected_features.json",
    "selector_fold_outputs": "stage1_v2_selector_fold_outputs.parquet",
    "predictions_baseline": "stage1_v2_pred_batch_predictions_baseline.parquet",
    "predictions_selected": "stage1_v2_pred_batch_predictions_selected.parquet",
}


@dataclass(frozen=True)
class Stage1V2SelectorConfig:
    feature_selector_method: str = "recursive_shap"
    selector_shap_calc_type: str = "Regular"
    selector_steps: int = 3
    selector_keep_ratio: float = 0.7
    selector_fold_vote_min_frac: float = 0.5
    selector_step_vote_min_frac: float = 0.5
    min_features_keep: int = 24
    feature_importance_type: str = "PredictionValuesChange"
    execution_mode: str = STAGE1_V2_EXECUTION_MODE_PARITY
    collect_step_diagnostics: bool = True
    persist_prediction_rows: bool = True
    fixed_policy_registry_path: str | None = None


def normalize_stage1_version(value: Any) -> str:
    token = str(value or STAGE1_VERSION_V1).strip().lower()
    if token not in {STAGE1_VERSION_V1, STAGE1_VERSION_V2}:
        raise ValueError("stage1_version must be 'v1' or 'v2'")
    return token


def normalize_stage1_v2_execution_mode(value: Any) -> str:
    token = str(value or STAGE1_V2_EXECUTION_MODE_PARITY).strip().lower()
    if token not in {
        STAGE1_V2_EXECUTION_MODE_PARITY,
        STAGE1_V2_EXECUTION_MODE_NESTED,
        STAGE1_V2_EXECUTION_MODE_FIXED_POLICY,
    }:
        raise ValueError(
            "stage1_v2 execution_mode must be 'parity', 'nested_selector', or "
            "'fixed_policy'"
        )
    return token


def stage1_mode_name(stage1_version: Any) -> str:
    return f"{STAGE1_MODE_PREFIX}{normalize_stage1_version(stage1_version)}"


def build_stage1_v2_selector_config(
    config: Stage1V2SelectorConfig | dict[str, Any] | None = None,
) -> Stage1V2SelectorConfig:
    if config is None:
        cfg = Stage1V2SelectorConfig()
    elif isinstance(config, Stage1V2SelectorConfig):
        cfg = config
    elif isinstance(config, dict):
        cfg = Stage1V2SelectorConfig(**config)
    else:
        raise TypeError(
            "stage1_v2_selector_config must be None, dict, or Stage1V2SelectorConfig"
        )

    if not (0.0 < float(cfg.selector_keep_ratio) <= 1.0):
        raise ValueError("selector_keep_ratio must be in (0, 1]")
    if not (0.0 < float(cfg.selector_fold_vote_min_frac) <= 1.0):
        raise ValueError("selector_fold_vote_min_frac must be in (0, 1]")
    if not (0.0 < float(cfg.selector_step_vote_min_frac) <= 1.0):
        raise ValueError("selector_step_vote_min_frac must be in (0, 1]")
    if int(cfg.selector_steps) < 1:
        raise ValueError("selector_steps must be >= 1")
    if int(cfg.min_features_keep) < 1:
        raise ValueError("min_features_keep must be >= 1")

    return Stage1V2SelectorConfig(
        feature_selector_method=str(cfg.feature_selector_method).strip().lower(),
        selector_shap_calc_type=str(cfg.selector_shap_calc_type).strip(),
        selector_steps=int(cfg.selector_steps),
        selector_keep_ratio=float(cfg.selector_keep_ratio),
        selector_fold_vote_min_frac=float(cfg.selector_fold_vote_min_frac),
        selector_step_vote_min_frac=float(cfg.selector_step_vote_min_frac),
        min_features_keep=int(cfg.min_features_keep),
        feature_importance_type=str(cfg.feature_importance_type).strip(),
        execution_mode=normalize_stage1_v2_execution_mode(cfg.execution_mode),
        collect_step_diagnostics=bool(cfg.collect_step_diagnostics),
        persist_prediction_rows=bool(cfg.persist_prediction_rows),
        fixed_policy_registry_path=(
            None
            if cfg.fixed_policy_registry_path is None
            or str(cfg.fixed_policy_registry_path).strip() == ""
            else str(cfg.fixed_policy_registry_path).strip()
        ),
    )


def stage1_v2_contract_payload(
    selector_config: Stage1V2SelectorConfig | dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = build_stage1_v2_selector_config(selector_config)
    return {
        "artifact_contract_version": STAGE1_V2_ARTIFACT_CONTRACT_VERSION,
        "execution_mode": str(cfg.execution_mode),
        "selector_config": asdict(cfg),
        "root_artifacts": dict(STAGE1_V2_ROOT_ARTIFACTS),
        "step_artifacts": dict(STAGE1_V2_STEP_ARTIFACTS),
    }


def stage1_v2_fixed_policy_contract_payload() -> dict[str, Any]:
    return {
        "artifact_contract_version": STAGE1_V2_FIXED_POLICY_ARTIFACT_CONTRACT_VERSION,
        "root_artifacts": dict(STAGE1_V2_FIXED_POLICY_ROOT_ARTIFACTS),
    }
