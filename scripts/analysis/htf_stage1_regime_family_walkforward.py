from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_REPO_BOOTSTRAP_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_BOOTSTRAP_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_BOOTSTRAP_ROOT))

from scripts.project_paths import ensure_project_root_on_path  # noqa: E402

PROJECT_ROOT = ensure_project_root_on_path(Path(__file__))

from scripts.htf_backtest.catboost.stage1_analysis import (  # noqa: E402
    build_stage1_winner_portfolio,
)
from scripts.htf_backtest.catboost.stage1_runner import (  # noqa: E402
    run_walk_forward_stage1_grid,
)
from scripts.htf_backtest.catboost.stage1_multiasset_dataset import (  # noqa: E402
    build_multiasset_stage1_dataset,
    parse_stage1_context_assets,
    parse_stage1_target_assets,
)
from scripts.htf_backtest.catboost.stage1_v2_contract import (  # noqa: E402
    STAGE1_V2_EXECUTION_MODE_FIXED_POLICY,
    STAGE1_V2_EXECUTION_MODE_NESTED,
    STAGE1_V2_EXECUTION_MODE_PARITY,
    STAGE1_VERSION_V1,
    STAGE1_VERSION_V2,
    build_stage1_v2_selector_config,
    normalize_stage1_v2_execution_mode,
    normalize_stage1_version,
)


MODEL_NAME = "catboost"
TF = "1m"
TARGET_COL = "target_4class"
FEATURE_TARGET_COL = TARGET_COL
CLASS_NAMES_4 = [
    "DOWN_BALANCED",
    "DOWN_EXPANSION",
    "UP_BALANCED",
    "UP_EXPANSION",
]

STAGE1_REFERENCE_RUN_ID = "stage1_catboost_live"
STAGE1_QUALITY_ACCURACY_THRESHOLD = 0.70
STAGE1_PROBE_ENABLED = True
STAGE1_PROBE_TIER_SIZES = [8, 8, 8, 8]
STAGE1_PROBE_MAX_EXTRA_CANDIDATES = 32
STAGE1_PROBE_SOURCE_SCOPE = "current+archive"
STAGE1_BACKFILL_LOW_QUALITY_COMPLETED = True
STAGE1_PROMOTION_MODE = "global"
STAGE1_PROMOTED_COMBO_CAP_PER_UNIT = 8

STAGE1_CB_BASE_PARAMS = {
    "loss_function": "MultiClass",
    "eval_metric": "MultiClass",
    "task_type": "GPU",
    "devices": "0",
    "random_seed": 42,
    "allow_writing_files": False,
    "verbose": False,
    "thread_count": -1,
    "bootstrap_type": "Bernoulli",
}

STAGE1_FALLBACK_MANUAL_TRIPLETS = {
    "1m/target_4class": [(7, 1, 4), (2, 1, 3), (2, 2, 8), (2, 3, 9)],
}

STAGE1_PORTFOLIO_REBUILD = False
STAGE1_PORTFOLIO_SOURCE = "current+archive"
STAGE1_PORTFOLIO_DYNAMIC_CAP = 8
STAGE1_PORTFOLIO_MIN_SUPPORT_STEPS = 40
STAGE1_PORTFOLIO_MIN_NEW_HIGHWIN_STEPS = 5
STAGE1_PORTFOLIO_MIN_MEAN_BEST_GAIN = 0.002
STAGE1_PORTFOLIO_MIN_COV70_GAIN = 0.01
STAGE1_PORTFOLIO_HIGH_ACCURACY_THRESHOLD = 0.70
STAGE1_PORTFOLIO_TARGET_HIGH_ACCURACY_COVERAGE = 0.95
STAGE1_PORTFOLIO_OVERLAP_PENALTY = 0.25
STAGE1_PORTFOLIO_CONTEXT_GRANULARITY = "step"
STAGE1_PORTFOLIO_REQUIRE_70_MEAN_IF_POSSIBLE = True
STAGE1_RUNTIME_MODE = "routine"
STAGE1_VERSION = STAGE1_VERSION_V1
STAGE1_V2_EXECUTION_MODE = STAGE1_V2_EXECUTION_MODE_PARITY
STAGE1_V2_SELECTOR_CONFIG = build_stage1_v2_selector_config(
    {
        "feature_selector_method": "recursive_shap",
        "selector_shap_calc_type": "Regular",
        "selector_steps": 3,
        "selector_keep_ratio": 0.7,
        "selector_fold_vote_min_frac": 0.5,
        "selector_step_vote_min_frac": 0.5,
        "min_features_keep": 24,
        "feature_importance_type": "PredictionValuesChange",
        "execution_mode": STAGE1_V2_EXECUTION_MODE,
        "collect_step_diagnostics": True,
        "persist_prediction_rows": True,
    }
)

ROOTS = {
    "8h/B": {
        "regime": "8h",
        "family": "B",
        "features_dir": PROJECT_ROOT / "data" / "htf_with_helpers",
        "labels_dir": PROJECT_ROOT / "data" / "htf_4class_labels",
        "run_id": "stage1_catboost_8h_b_live",
    },
    "8h/C": {
        "regime": "8h",
        "family": "C",
        "features_dir": PROJECT_ROOT / "data" / "htf_with_helpers_shift4h",
        "labels_dir": PROJECT_ROOT / "data" / "htf_4class_labels_shift4h",
        "run_id": "stage1_catboost_8h_c_live",
    },
    "24h/B": {
        "regime": "24h",
        "family": "B",
        "features_dir": PROJECT_ROOT / "data" / "htf_with_helpers_24h",
        "labels_dir": PROJECT_ROOT / "data" / "htf_4class_labels_24h",
        "run_id": "stage1_catboost_24h_b_live",
    },
    "24h/C": {
        "regime": "24h",
        "family": "C",
        "features_dir": PROJECT_ROOT / "data" / "htf_with_helpers_24h_shift12h",
        "labels_dir": PROJECT_ROOT / "data" / "htf_4class_labels_24h_shift12h",
        "run_id": "stage1_catboost_24h_c_live",
    },
    "7d/B": {
        "regime": "7d",
        "family": "B",
        "features_dir": PROJECT_ROOT / "data" / "htf_with_helpers_7d",
        "labels_dir": PROJECT_ROOT / "data" / "htf_4class_labels_7d",
        "run_id": "stage1_catboost_7d_b_live",
    },
    "7d/C": {
        "regime": "7d",
        "family": "C",
        "features_dir": PROJECT_ROOT / "data" / "htf_with_helpers_7d_shift84h",
        "labels_dir": PROJECT_ROOT / "data" / "htf_4class_labels_7d_shift84h",
        "run_id": "stage1_catboost_7d_c_live",
    },
}

OUTPUT_DIR = PROJECT_ROOT / "test_output" / "htf_stage1_regime_family_walkforward"


def _coerce_triplets(value: Any) -> list[tuple[int, int, int]]:
    out: list[tuple[int, int, int]] = []
    if not isinstance(value, list):
        return out
    for item in value:
        if not isinstance(item, (list, tuple)) or len(item) != 3:
            continue
        try:
            out.append((int(item[0]), int(item[1]), int(item[2])))
        except Exception:
            continue
    return out


def _resolve_stage1_triplet_grid(
    *,
    project_root: Path,
    reference_run_id: str,
    target_col: str,
    portfolio_rebuild: bool = False,
) -> tuple[list[tuple[int, int, int]], dict[str, Any]]:
    unit_key = f"{TF}/{target_col}"
    fallback_unit_key = f"{TF}/{TARGET_COL}"
    manual_triplets = list(
        STAGE1_FALLBACK_MANUAL_TRIPLETS.get(
            unit_key,
            STAGE1_FALLBACK_MANUAL_TRIPLETS[fallback_unit_key],
        )
    )
    meta_dir = (
        project_root / "data" / "htf_backtest_results" / "stage1_meta" / MODEL_NAME / reference_run_id
    )
    autogen_path = meta_dir / "candidate_triplet_grid_autogen.json"
    portfolio_path = meta_dir / "candidate_portfolio_v2.json"
    build_result = None

    try:
        if portfolio_rebuild or not autogen_path.exists() or not portfolio_path.exists():
            build_result = build_stage1_winner_portfolio(
                run_id_or_path=reference_run_id,
                project_root=project_root,
                model_name=MODEL_NAME,
                source_scope=STAGE1_PORTFOLIO_SOURCE,
                dynamic_cap=STAGE1_PORTFOLIO_DYNAMIC_CAP,
                min_support_steps=STAGE1_PORTFOLIO_MIN_SUPPORT_STEPS,
                min_new_highwin_steps=STAGE1_PORTFOLIO_MIN_NEW_HIGHWIN_STEPS,
                min_mean_best_gain=STAGE1_PORTFOLIO_MIN_MEAN_BEST_GAIN,
                min_cov70_gain=STAGE1_PORTFOLIO_MIN_COV70_GAIN,
                high_accuracy_threshold=STAGE1_PORTFOLIO_HIGH_ACCURACY_THRESHOLD,
                target_high_accuracy_coverage=STAGE1_PORTFOLIO_TARGET_HIGH_ACCURACY_COVERAGE,
                overlap_penalty=STAGE1_PORTFOLIO_OVERLAP_PENALTY,
                context_granularity=STAGE1_PORTFOLIO_CONTEXT_GRANULARITY,
                require_70_mean_if_possible=STAGE1_PORTFOLIO_REQUIRE_70_MEAN_IF_POSSIBLE,
                fallback_triplet_grid_by_unit=STAGE1_FALLBACK_MANUAL_TRIPLETS,
                write_latest=True,
                verbose=False,
            )

        autogen_map = json.loads(autogen_path.read_text()) if autogen_path.exists() else {}
        portfolio_meta = json.loads(portfolio_path.read_text()) if portfolio_path.exists() else {"units": {}}
    except Exception as exc:
        return manual_triplets, {
            "source": "manual_fallback_error",
            "selected_triplets": [list(t) for t in manual_triplets],
            "error": str(exc),
            "build_result": build_result,
        }

    auto_triplets = _coerce_triplets(autogen_map.get(unit_key, []))
    if len(auto_triplets) > int(STAGE1_PORTFOLIO_DYNAMIC_CAP):
        auto_triplets = auto_triplets[: int(STAGE1_PORTFOLIO_DYNAMIC_CAP)]

    unit_meta = portfolio_meta.get("units", {}).get(unit_key, {})
    combo_stats = {}
    for row in unit_meta.get("combo_stats", []):
        if not isinstance(row, dict):
            continue
        combo_stats[str(row.get("combo_key"))] = int(row.get("steps_seen", 0) or 0)

    validated: list[tuple[int, int, int]] = []
    for triplet in auto_triplets:
        combo_key = f"f{triplet[0]}_v{triplet[1]}_t{triplet[2]}"
        if combo_stats.get(combo_key, 0) >= int(STAGE1_PORTFOLIO_MIN_SUPPORT_STEPS):
            validated.append(triplet)

    selected_triplets = validated if validated else manual_triplets
    return selected_triplets, {
        "source": str(unit_meta.get("selected_source", "manual")) if validated else "manual",
        "selected_triplets": [list(t) for t in selected_triplets],
        "manual_metrics": unit_meta.get("manual_metrics"),
        "selected_metrics": unit_meta.get("selected_metrics"),
        "build_result": build_result,
    }


def _build_root_override(
    *,
    features_dir: Path,
    labels_dir: Path,
    target_col: str,
    stage1_triplet_grid: list[tuple[int, int, int]],
    runtime_mode: str,
) -> dict[str, Any]:
    max_train = max(int(t[2]) for t in stage1_triplet_grid)
    max_folds = max(int(t[0]) for t in stage1_triplet_grid)
    max_val = max(int(t[1]) for t in stage1_triplet_grid)
    lookback_min = max(100, max_train + max_folds * max_val + 2)
    runtime_mode = str(runtime_mode).strip().lower()
    if runtime_mode not in {"routine", "adaptive"}:
        raise ValueError("runtime_mode must be 'routine' or 'adaptive'")

    stage1_probe_enabled = bool(STAGE1_PROBE_ENABLED)
    stage1_probe_tier_sizes = list(STAGE1_PROBE_TIER_SIZES)
    stage1_probe_max_extra_candidates = int(STAGE1_PROBE_MAX_EXTRA_CANDIDATES)
    stage1_probe_source_scope = str(STAGE1_PROBE_SOURCE_SCOPE)
    stage1_backfill_low_quality_completed = bool(STAGE1_BACKFILL_LOW_QUALITY_COMPLETED)
    stage1_promotion_mode = str(STAGE1_PROMOTION_MODE)
    stage1_promoted_combo_cap_per_unit = int(STAGE1_PROMOTED_COMBO_CAP_PER_UNIT)

    if runtime_mode == "routine":
        stage1_probe_enabled = False
        stage1_probe_tier_sizes = [0]
        stage1_probe_max_extra_candidates = 0
        stage1_probe_source_scope = "current"
        stage1_backfill_low_quality_completed = False

    return {
        "track_pred_metrics": False,
        "balance_strategy": "none",
        "balance_apply_to": "train",
        "cb_base_params": STAGE1_CB_BASE_PARAMS,
        "optuna_metric": "cross_direction_error",
        "stage1_validity_target_col": target_col,
        "features_dir_override": str(features_dir),
        "labels_dir_override": str(labels_dir),
        "window_space": {
            "lookback_min": lookback_min,
            "lookback_max": 450,
            "window_selection_mode": "stage1_fold_cv",
            "stage1_execution_mode": "fast_grid",
            "stage1_folds_min": 2,
            "stage1_folds_max": 9,
            "stage1_val_batches_min": 1,
            "stage1_val_batches_max": 4,
            "stage1_train_batches_min": 2,
            "stage1_train_batches_max": 36,
            "stage1_stability_lambda": 0.25,
            "stage1_trial_selection_mode": "prediction_batch",
            "embargo_mode": "auto_tf",
            "min_samples_per_class": 150,
            "stage1_triplet_grid": [list(t) for t in stage1_triplet_grid],
        },
        "model_space": {"num_boost_round_min": 300, "num_boost_round_max": 300},
        "stage1_runtime_mode": runtime_mode,
        "stage1_probe_enabled": stage1_probe_enabled,
        "stage1_probe_tier_sizes": stage1_probe_tier_sizes,
        "stage1_probe_max_extra_candidates": stage1_probe_max_extra_candidates,
        "stage1_probe_source_scope": stage1_probe_source_scope,
        "stage1_backfill_low_quality_completed": stage1_backfill_low_quality_completed,
        "stage1_promotion_mode": stage1_promotion_mode,
        "stage1_promoted_combo_cap_per_unit": stage1_promoted_combo_cap_per_unit,
    }


def _resolve_root_run_id(
    root_cfg: dict[str, Any],
    stage1_version: str,
    stage1_v2_execution_mode: str | None = None,
    pred_batch_min: int | None = None,
    pred_batch_max: int | None = None,
) -> str:
    base_run_id = str(root_cfg["run_id"])
    stage1_version = normalize_stage1_version(stage1_version)
    if stage1_version == STAGE1_VERSION_V1:
        return base_run_id
    stage1_v2_execution_mode = normalize_stage1_v2_execution_mode(
        stage1_v2_execution_mode or STAGE1_V2_EXECUTION_MODE
    )
    batch_window_suffix = ""
    if pred_batch_min is not None or pred_batch_max is not None:
        batch_window_suffix = (
            f"_pb{pred_batch_min if pred_batch_min is not None else 'min'}"
            f"_{pred_batch_max if pred_batch_max is not None else 'max'}"
        )
    if base_run_id.endswith("_live"):
        base_prefix = base_run_id[: -len("_live")]
        if stage1_v2_execution_mode == STAGE1_V2_EXECUTION_MODE_NESTED:
            return base_prefix + f"_v2{batch_window_suffix}_live"
        return base_prefix + f"_v2_{stage1_v2_execution_mode}{batch_window_suffix}_live"
    return f"{base_run_id}_{stage1_version}"


def _run_root(
    *,
    root_key: str,
    root_cfg: dict[str, Any],
    target_col: str,
    n_steps: int,
    resume_mode: str,
    stage1_triplet_grid: list[tuple[int, int, int]],
    runtime_mode: str,
    stage1_version: str,
    stage1_v2_selector_config: dict[str, Any] | None,
    pred_batch_min: int | None = None,
    pred_batch_max: int | None = None,
) -> dict[str, Any]:
    stage1_v2_selector_config_local = (
        dict(stage1_v2_selector_config) if stage1_v2_selector_config is not None else None
    )
    stage1_v2_execution_mode = (
        str(stage1_v2_selector_config_local.get("execution_mode"))
        if stage1_v2_selector_config_local is not None
        else None
    )
    run_id = _resolve_root_run_id(
        root_cfg,
        stage1_version,
        stage1_v2_execution_mode=stage1_v2_execution_mode,
        pred_batch_min=pred_batch_min,
        pred_batch_max=pred_batch_max,
    )
    if (
        stage1_version == STAGE1_VERSION_V2
        and stage1_v2_selector_config_local is not None
        and str(stage1_v2_selector_config_local.get("execution_mode"))
        == STAGE1_V2_EXECUTION_MODE_FIXED_POLICY
        and not stage1_v2_selector_config_local.get("fixed_policy_registry_path")
    ):
        source_run_id = _resolve_root_run_id(
            root_cfg,
            STAGE1_VERSION_V2,
            stage1_v2_execution_mode=STAGE1_V2_EXECUTION_MODE_NESTED,
        )
        source_registry_path = (
            PROJECT_ROOT
            / "data"
            / "htf_backtest_results"
            / source_run_id
            / "stage1_v2_fixed_policy_registry.json"
        )
        stage1_v2_selector_config_local["fixed_policy_registry_path"] = str(
            source_registry_path
        )
    run_dir = PROJECT_ROOT / "data" / "htf_backtest_results" / run_id
    overrides = _build_root_override(
        features_dir=Path(root_cfg["features_dir"]),
        labels_dir=Path(root_cfg["labels_dir"]),
        target_col=target_col,
        stage1_triplet_grid=stage1_triplet_grid,
        runtime_mode=runtime_mode,
    )
    result = run_walk_forward_stage1_grid(
        n_steps=n_steps,
        timeframes=[TF],
        run_description=(
            f"HTF Stage-1 {stage1_version} full walk-forward (CatBoost, 1m/{target_col}) "
            f"regime={root_cfg['regime']} family={root_cfg['family']}"
        ),
        verbose=True,
        debug_batches=True,
        run_id=run_id,
        resume=run_dir.exists(),
        resume_mode=resume_mode,
        model_name=MODEL_NAME,
        optuna_overrides_by_model={
            MODEL_NAME: {TF: {target_col: overrides}},
        },
        targets_by_model={MODEL_NAME: {TF: [target_col]}},
        n_classes_by_model={MODEL_NAME: {TF: {target_col: 4}}},
        class_names_by_model={MODEL_NAME: {TF: {target_col: CLASS_NAMES_4}}},
        feature_source_by_model={MODEL_NAME: {TF: {target_col: FEATURE_TARGET_COL}}},
        target_registry={
            target_col: {
                "n_classes": 4,
                "class_names": CLASS_NAMES_4,
            }
        },
        stage1_quality_accuracy_threshold=STAGE1_QUALITY_ACCURACY_THRESHOLD,
        stage1_probe_enabled=STAGE1_PROBE_ENABLED,
        stage1_probe_tier_sizes=STAGE1_PROBE_TIER_SIZES,
        stage1_probe_max_extra_candidates=STAGE1_PROBE_MAX_EXTRA_CANDIDATES,
        stage1_probe_source_scope=STAGE1_PROBE_SOURCE_SCOPE,
        stage1_backfill_low_quality_completed=STAGE1_BACKFILL_LOW_QUALITY_COMPLETED,
        stage1_promotion_mode=STAGE1_PROMOTION_MODE,
        stage1_promoted_combo_cap_per_unit=STAGE1_PROMOTED_COMBO_CAP_PER_UNIT,
        stage1_version=stage1_version,
        stage1_v2_selector_config=stage1_v2_selector_config_local,
        pred_batch_min=pred_batch_min,
        pred_batch_max=pred_batch_max,
    )
    return {
        "root_key": root_key,
        "regime": root_cfg["regime"],
        "family": root_cfg["family"],
        "run_id": run_id,
        "target_col": target_col,
        "feature_target_col": FEATURE_TARGET_COL,
        "features_dir": str(root_cfg["features_dir"]),
        "labels_dir": str(root_cfg["labels_dir"]),
        "resume": run_dir.exists(),
        "n_steps": int(n_steps),
        "runtime_mode": str(runtime_mode),
        "stage1_version": str(stage1_version),
        "stage1_v2_selector_config": stage1_v2_selector_config_local,
        "pred_batch_min": (
            None if pred_batch_min is None else int(pred_batch_min)
        ),
        "pred_batch_max": (
            None if pred_batch_max is None else int(pred_batch_max)
        ),
        "triplet_grid": [list(t) for t in stage1_triplet_grid],
        "result": result,
    }


def _resolve_fixed_policy_registry_path_for_root(root_cfg: dict[str, Any]) -> str:
    source_run_id = _resolve_root_run_id(
        root_cfg,
        STAGE1_VERSION_V2,
        stage1_v2_execution_mode=STAGE1_V2_EXECUTION_MODE_NESTED,
    )
    return str(
        PROJECT_ROOT
        / "data"
        / "htf_backtest_results"
        / source_run_id
        / "stage1_v2_fixed_policy_registry.json"
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run full HTF CatBoost Stage-1 walk-forward jobs for current "
            "1m/target_4class regime/family roots."
        )
    )
    parser.add_argument(
        "--roots",
        nargs="*",
        choices=sorted(ROOTS),
        default=list(ROOTS),
        help="Subset of regime/family roots to run. Default: all.",
    )
    parser.add_argument(
        "--build-merged-dataset",
        action="store_true",
        help=(
            "Build Stage-1-compatible merged multi-asset roots from "
            "data/htf_multiasset/{asset}/ before planning or running."
        ),
    )
    parser.add_argument(
        "--stage1-target-col",
        default=TARGET_COL,
        help=(
            "Label column to train/evaluate. Feature source remains "
            f"{FEATURE_TARGET_COL}; non-default target columns are for "
            "experimental label roots such as target_4class_tb_atr_v1."
        ),
    )
    parser.add_argument(
        "--target-assets",
        default=None,
        help=(
            "Prediction target assets for merged Stage-1 runs. Use 'core' or a "
            "comma-separated list such as BTCUSDT,ES. Default with "
            "--build-merged-dataset: core."
        ),
    )
    parser.add_argument(
        "--context-assets",
        default=None,
        help=(
            "Context assets joined by exact timestamp for each target. Use "
            "'core-ex-target', 'core', a comma-separated list, or omit for "
            "target-only merged datasets."
        ),
    )
    parser.add_argument(
        "--multiasset-dataset-dir",
        type=Path,
        default=PROJECT_ROOT / "data" / "htf_multiasset_merged",
        help="Output directory for generated merged Stage-1 dataset roots.",
    )
    parser.add_argument(
        "--merged-batch-limit",
        type=int,
        default=None,
        help=(
            "Optional cap on target batches assembled per merged root. Use this "
            "for fast dataset-contract smoke tests; omit for production datasets."
        ),
    )
    parser.add_argument(
        "--merged-batch-min",
        type=int,
        default=None,
        help="Optional minimum target batch id to assemble for merged-dataset smoke tests.",
    )
    parser.add_argument(
        "--merged-batch-max",
        type=int,
        default=None,
        help="Optional maximum target batch id to assemble for merged-dataset smoke tests.",
    )
    parser.add_argument(
        "--include-ta-flags",
        action="store_true",
        help=(
            "Join precomputed TA signal flags from "
            "data/htf_multiasset/{asset}/ta_signal_flags into merged Stage-1 roots."
        ),
    )
    parser.add_argument(
        "--ta-timeframes",
        default="15m,1h,4h,8h,12h,1d",
        help="Comma-separated TA flag timeframes to join when --include-ta-flags is set.",
    )
    parser.add_argument(
        "--ta-signal-set",
        choices=["raw", "compact", "all"],
        default="raw",
        help="TA signal set to join when --include-ta-flags is set.",
    )
    parser.add_argument(
        "--n-steps",
        type=int,
        default=500,
        help="Number of walk-forward prediction batches per root.",
    )
    parser.add_argument(
        "--resume-mode",
        choices=["continue", "skip_completed"],
        default="skip_completed",
        help="Stage-1 resume mode for existing root runs.",
    )
    parser.add_argument(
        "--plan-only",
        action="store_true",
        help="Print resolved root plan and exit without running Stage-1.",
    )
    parser.add_argument(
        "--portfolio-rebuild",
        action="store_true",
        help="Rebuild reference Stage-1 winner portfolio before resolving triplets.",
    )
    parser.add_argument(
        "--runtime-mode",
        choices=["routine", "adaptive"],
        default=STAGE1_RUNTIME_MODE,
        help=(
            "Routine mode disables inactive adaptive probing/promotion for faster "
            "runtime with the current base-grid workflow. Adaptive mode preserves "
            "the current probe/promotion path."
        ),
    )
    parser.add_argument(
        "--stage1-version",
        choices=[STAGE1_VERSION_V1, STAGE1_VERSION_V2],
        default=STAGE1_VERSION,
        help=(
            "Select the Stage-1 implementation. v1 is the current benchmark path. "
            "v2 currently exposes parity-safe foundation wiring and separate run ids."
        ),
    )
    parser.add_argument(
        "--stage1-v2-execution-mode",
        choices=["parity", "nested_selector", "fixed_policy"],
        default=STAGE1_V2_EXECUTION_MODE,
        help=(
            "Execution mode for Stage-1-v2. 'parity' mirrors baseline artifacts, "
            "'nested_selector' runs per-step recursive selection, and "
            "'fixed_policy' replays using a root-level per-combo registry."
        ),
    )
    parser.add_argument(
        "--pred-batch-min",
        type=int,
        default=None,
        help="Optional lower bound for prediction batch ids to evaluate.",
    )
    parser.add_argument(
        "--pred-batch-max",
        type=int,
        default=None,
        help="Optional upper bound for prediction batch ids to evaluate.",
    )
    return parser.parse_args()


def _build_execution_entries(
    *,
    args: argparse.Namespace,
    selected_roots: list[str],
) -> list[dict[str, Any]]:
    """Resolve legacy or merged multi-asset root configs for this invocation."""
    if not bool(args.build_merged_dataset):
        return [
            {
                "entry_key": root_key,
                "root_key": root_key,
                "root_cfg": ROOTS[root_key],
                "target_asset": None,
                "context_assets": [],
                "context_hash": None,
                "manifest_path": None,
            }
            for root_key in selected_roots
        ]

    target_assets = parse_stage1_target_assets(args.target_assets)
    entries: list[dict[str, Any]] = []
    for target_asset in target_assets:
        context_assets = parse_stage1_context_assets(
            args.context_assets,
            target_asset=target_asset,
        )
        for root_key in selected_roots:
            assembly = build_multiasset_stage1_dataset(
                project_root=PROJECT_ROOT,
                target_asset=target_asset,
                context_assets=context_assets,
                root_key=root_key,
                output_base_dir=Path(args.multiasset_dataset_dir),
                input_base_dir=PROJECT_ROOT / "data" / "htf_multiasset",
                target_col=str(args.stage1_target_col),
                feature_target_col=FEATURE_TARGET_COL,
                include_ta_flags=bool(args.include_ta_flags),
                ta_timeframes=tuple(
                    part.strip()
                    for part in str(args.ta_timeframes).split(",")
                    if part.strip()
                ),
                ta_signal_sets=(str(args.ta_signal_set),),
                max_batches=args.merged_batch_limit,
                batch_id_min=args.merged_batch_min,
                batch_id_max=args.merged_batch_max,
            )
            root_cfg = {
                **ROOTS[root_key],
                "features_dir": assembly.features_dir,
                "labels_dir": assembly.labels_dir,
                "run_id": assembly.run_id,
            }
            entries.append(
                {
                    "entry_key": f"{target_asset}/{root_key}",
                    "root_key": root_key,
                    "root_cfg": root_cfg,
                    "target_asset": target_asset,
                    "context_assets": list(context_assets),
                    "context_hash": assembly.context_hash,
                    "dataset_variant_id": assembly.dataset_variant_id,
                    "manifest_path": str(assembly.manifest_path),
                    "include_ta_flags": bool(args.include_ta_flags),
                }
            )
    return entries


def main() -> int:
    args = _parse_args()
    if bool(args.include_ta_flags) and not bool(args.build_merged_dataset):
        raise ValueError("--include-ta-flags requires --build-merged-dataset")
    selected_roots = list(dict.fromkeys(args.roots))
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    stage1_triplet_grid, triplet_report = _resolve_stage1_triplet_grid(
        project_root=PROJECT_ROOT,
        reference_run_id=STAGE1_REFERENCE_RUN_ID,
        target_col=str(args.stage1_target_col),
        portfolio_rebuild=bool(args.portfolio_rebuild or STAGE1_PORTFOLIO_REBUILD),
    )
    stage1_version = normalize_stage1_version(args.stage1_version)
    stage1_v2_selector_config = None
    if stage1_version == STAGE1_VERSION_V2:
        resolved_stage1_v2_execution_mode = normalize_stage1_v2_execution_mode(
            args.stage1_v2_execution_mode
        )
        if (
            resolved_stage1_v2_execution_mode == STAGE1_V2_EXECUTION_MODE_FIXED_POLICY
            and str(args.runtime_mode) != "routine"
        ):
            raise ValueError(
                "Stage-1-v2 fixed_policy execution requires --runtime-mode routine."
            )
        stage1_v2_selector_config = build_stage1_v2_selector_config(
            {
                **STAGE1_V2_SELECTOR_CONFIG.__dict__,
                "execution_mode": resolved_stage1_v2_execution_mode,
            }
        ).__dict__

    execution_entries = _build_execution_entries(args=args, selected_roots=selected_roots)

    plan = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "reference_run_id": STAGE1_REFERENCE_RUN_ID,
        "selected_roots": selected_roots,
        "build_merged_dataset": bool(args.build_merged_dataset),
        "target_assets": (
            list(parse_stage1_target_assets(args.target_assets))
            if bool(args.build_merged_dataset)
            else []
        ),
        "context_assets_selector": args.context_assets,
        "multiasset_dataset_dir": (
            str(Path(args.multiasset_dataset_dir))
            if bool(args.build_merged_dataset)
            else None
        ),
        "merged_batch_limit": (
            None if args.merged_batch_limit is None else int(args.merged_batch_limit)
        ),
        "merged_batch_min": (
            None if args.merged_batch_min is None else int(args.merged_batch_min)
        ),
        "merged_batch_max": (
            None if args.merged_batch_max is None else int(args.merged_batch_max)
        ),
        "include_ta_flags": bool(args.include_ta_flags),
        "ta_timeframes": [
            part.strip() for part in str(args.ta_timeframes).split(",") if part.strip()
        ]
        if bool(args.include_ta_flags)
        else [],
        "ta_signal_set": str(args.ta_signal_set) if bool(args.include_ta_flags) else None,
        "n_steps": int(args.n_steps),
        "stage1_target_col": str(args.stage1_target_col),
        "feature_target_col": FEATURE_TARGET_COL,
        "resume_mode": str(args.resume_mode),
        "runtime_mode": str(args.runtime_mode),
        "stage1_version": str(stage1_version),
        "pred_batch_min": (
            None if args.pred_batch_min is None else int(args.pred_batch_min)
        ),
        "pred_batch_max": (
            None if args.pred_batch_max is None else int(args.pred_batch_max)
        ),
        "stage1_v2_selector_config": stage1_v2_selector_config,
        "triplet_report": triplet_report,
        "roots": {
            entry["entry_key"]: {
                "root_key": entry["root_key"],
                "target_asset": entry["target_asset"],
                "context_assets": entry["context_assets"],
                "context_hash": entry["context_hash"],
                "dataset_variant_id": entry.get("dataset_variant_id", "base"),
                "manifest_path": entry["manifest_path"],
                "include_ta_flags": entry.get("include_ta_flags", False),
                "target_col": str(args.stage1_target_col),
                "feature_target_col": FEATURE_TARGET_COL,
                "regime": entry["root_cfg"]["regime"],
                "family": entry["root_cfg"]["family"],
                "run_id": _resolve_root_run_id(
                    entry["root_cfg"],
                    stage1_version,
                    stage1_v2_execution_mode=(
                        stage1_v2_selector_config.get("execution_mode")
                        if stage1_v2_selector_config is not None
                        else None
                    ),
                    pred_batch_min=args.pred_batch_min,
                    pred_batch_max=args.pred_batch_max,
                ),
                "features_dir": str(entry["root_cfg"]["features_dir"]),
                "labels_dir": str(entry["root_cfg"]["labels_dir"]),
                "fixed_policy_registry_path": (
                    _resolve_fixed_policy_registry_path_for_root(entry["root_cfg"])
                    if stage1_v2_selector_config is not None
                    and str(stage1_v2_selector_config.get("execution_mode"))
                    == STAGE1_V2_EXECUTION_MODE_FIXED_POLICY
                    else None
                ),
            }
            for entry in execution_entries
        },
    }
    plan_path = OUTPUT_DIR / f"plan_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    plan_path.write_text(json.dumps(plan, indent=2))
    print(json.dumps(plan, indent=2))
    print(f"\nPlan file: {plan_path}")

    if args.plan_only:
        return 0

    summaries: list[dict[str, Any]] = []
    for entry in execution_entries:
        root_key = str(entry["root_key"])
        print("\n" + "=" * 100)
        if entry["target_asset"]:
            print(
                f"RUNNING ROOT {root_key} target={entry['target_asset']} "
                f"context={entry['context_hash']}"
            )
        else:
            print(f"RUNNING ROOT {root_key}")
        print("=" * 100)
        summary = _run_root(
            root_key=root_key,
            root_cfg=entry["root_cfg"],
            target_col=str(args.stage1_target_col),
            n_steps=int(args.n_steps),
            resume_mode=str(args.resume_mode),
            stage1_triplet_grid=stage1_triplet_grid,
            runtime_mode=str(args.runtime_mode),
            stage1_version=str(stage1_version),
            stage1_v2_selector_config=stage1_v2_selector_config,
            pred_batch_min=args.pred_batch_min,
            pred_batch_max=args.pred_batch_max,
        )
        summary.update(
            {
                "entry_key": entry["entry_key"],
                "target_asset": entry["target_asset"],
                "context_assets": entry["context_assets"],
                "context_hash": entry["context_hash"],
                "dataset_variant_id": entry.get("dataset_variant_id", "base"),
                "manifest_path": entry["manifest_path"],
            }
        )
        summaries.append(summary)

    summary_path = OUTPUT_DIR / f"summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    summary_path.write_text(json.dumps(summaries, indent=2, default=str))
    print(f"\nSummary file: {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
