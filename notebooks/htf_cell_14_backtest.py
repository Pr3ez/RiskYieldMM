# %% [markdown]
# # Cell 14: Walk-Forward Backtest Design
#
# This cell runs the current **multi-model, multi-timeframe, multi-target walk-forward backtest**.
# Configuration is declarative and centralized in Cell 14.
#
# ## Current flow (one step)
#
# For each selected `model / timeframe / target`:
# 1. Select one aligned prediction batch ID.
# 2. Use only history up to `train_end = pred_batch - 1` for optimization and training.
# 3. Run Optuna on train/val slices.
# 4. Train final model with best trial settings.
# 5. Predict the current batch and store metrics + per-row outputs.
#
# Prediction batch rows are excluded from optimization/training (leakage-safe).
#
# ## Module map (where logic lives)
#
# - `scripts/htf_backtest/runner.py`
#   Top-level model orchestrator (`run_walk_forward_backtest_models`), supports one or multiple models in one run.
#
# - `scripts/htf_backtest/configuration.py`
#   Declarative config utilities:
#   - `merge_backtest_specs(base, overrides)` for robust deep-merge
#   - `build_backtest_maps(model_specs_by_model)` to build runner maps
#
# - `scripts/htf_backtest/lightgbm/runner.py`
#   LightGBM walk-forward step loop, resume behavior, artifact writing, summaries.
#
# - `scripts/htf_backtest/lightgbm/utils.py`
#   Shared utilities: data loading, metrics, save/export helpers, search-space dataclasses.
#
# - `scripts/htf_backtest/lightgbm/tf_1m/optimizer.py`
# - `scripts/htf_backtest/lightgbm/tf_5m/optimizer.py`
# - `scripts/htf_backtest/lightgbm/tf_15m/optimizer.py`
#   Timeframe-specific optimization + final training implementations.
#
# - `scripts/htf_backtest/catboost/runner.py`
#   CatBoost walk-forward step loop, resume behavior, artifact writing, summaries.
#
# - `scripts/htf_backtest/catboost/utils.py`
#   Shared utilities for CatBoost optimizer/search-space + persistence.
#
# - `scripts/htf_backtest/catboost/tf_1m/optimizer.py`
# - `scripts/htf_backtest/catboost/tf_5m/optimizer.py`
# - `scripts/htf_backtest/catboost/tf_15m/optimizer.py`
#   Timeframe-specific CatBoost optimization + final training implementations.
#
# ## Configuration pattern used now
#
# 1. Define stable defaults in `MODEL_BACKTEST_SPECS_BASE`.
# 2. Apply run-specific diffs in `MODEL_SPEC_OVERRIDES`.
# 3. Build final spec:
#    `MODEL_BACKTEST_SPECS = merge_backtest_specs(MODEL_BACKTEST_SPECS_BASE, MODEL_SPEC_OVERRIDES)`
# 4. Resolve runtime maps:
#    `RESOLVED_BACKTEST = build_backtest_maps(MODEL_BACKTEST_SPECS)`
# 5. Run:
#    `run_walk_forward_backtest_models(model_specs_by_model=MODEL_BACKTEST_SPECS, ...)`
#
# This gives full control per **model -> timeframe -> target**, including separate Optuna spaces and metrics.
#
# ## Artifact layout (current canonical)
#
# Root:
# - `data/htf_backtest_results/<run_id>/`
#
# Run-level:
# - `run_config.json`
# - `run_summary.json`
# - `run_model_index.json`
#
# Per-step:
# - `<model>/<timeframe>/<target>/batch_XXXX/`
#   - `study.db`, `optimization.json`, `trials.parquet`, `trials.jsonl`
#   - model file (model-specific):
#     - LightGBM: `model.txt`
#     - CatBoost: `model.cbm`
#   - `class_metrics.parquet`
#   - `prediction_metrics.json`
#   - `predictions.parquet`
#   - `batch_metadata.json`
#
# ## Alignment notes
#
# - 1m/5m/15m use the same prediction batch ID per step.
# - Outputs are isolated by model/timeframe/target so studies and artifacts never mix.
# - Optional multi-model runs are controlled by `ACTIVE_MODELS`.
#
#

# %%
# ============================================================================
# CELL 14: HTF WALK-FORWARD BACKTEST (CATBOOST STAGE-1 / STEP-1)
# ============================================================================
#
# Scope of Cell 14:
# - Runs only Stage-1 Step-1 payload collection.
# - No standard backtest / no Optuna studies / no heavy metric tables.
# - Uses fixed run_id folder and resume-in-place behavior.
# - Stage-1 docs:
#   - docs/htf_stage1_logic.md
#   - docs/htf_stage1_artifacts.md
#   - docs/htf_stage1_step2_plan.md
#
# Scope of Cell 15:
# - Runs Stage-1 Step-2 feature pruning + baseline-vs-filtered comparison.
#

import importlib
import json
import sys
from pathlib import Path

if "PROJECT_ROOT" not in dir():
    PROJECT_ROOT = Path("/media/przem/linux_data/RiskYieldMM (Copy)")

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

for mod_name in list(sys.modules.keys()):
    if "htf_backtest" in mod_name:
        del sys.modules[mod_name]

from scripts.htf_backtest.catboost.base_optimizer import run_walk_forward_stage1_grid
from scripts.htf_backtest.catboost.stage1_analysis import build_stage1_winner_portfolio
from scripts.htf_backtest.catboost.stage1_optimizer import build_stage1_combo_grid
from scripts.htf_backtest.configuration import build_backtest_maps, merge_backtest_specs

STAGE1_MODEL = "catboost"
if STAGE1_MODEL != "catboost":
    raise ValueError("Cell 14 supports only STAGE1_MODEL='catboost'.")

# ---------------------------------------------------------------------------
# Stable Stage-1 run location
# ---------------------------------------------------------------------------
STAGE1_RUN_ID = "stage1_catboost_live"
STAGE1_RESUME_MODE = "skip_completed"  # "continue" or "skip_completed"
STAGE1_RUN_PATH = PROJECT_ROOT / "data" / "htf_backtest_results" / STAGE1_RUN_ID
STAGE1_RESUME = STAGE1_RUN_PATH.exists()
STAGE1_N_STEPS = 500
STAGE1_QUALITY_ACCURACY_THRESHOLD = 0.70
STAGE1_PROBE_ENABLED = True
STAGE1_PROBE_TIER_SIZES = [8, 8, 8, 8]
STAGE1_PROBE_MAX_EXTRA_CANDIDATES = 32
STAGE1_PROBE_SOURCE_SCOPE = "current+archive"  # current | archive | current+archive
STAGE1_BACKFILL_LOW_QUALITY_COMPLETED = True
STAGE1_PROMOTION_MODE = "global"  # global | step_local | repeat
STAGE1_PROMOTED_COMBO_CAP_PER_UNIT = 8
ALLOW_OVERRIDE_MISMATCH = False

# Targets / classes
CLASS_NAMES_4 = [
    "DOWN_BALANCED",
    "DOWN_EXPANSION",
    "UP_BALANCED",
    "UP_EXPANSION",
]
CLASS_NAMES_BREAKFREE = [
    "UP_ABOVE_BREAKFREE",
    "DOWN_ABOVE_BREAKFREE",
    "IN_BETWEEN_BELOW_BREAKFREE",
]

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

# Manual fallback Stage-1 combo grid (triplets only).
# Triplet format: (fold_count, val_batches_per_fold, train_batches_per_fold)
STAGE1_FALLBACK_MANUAL_TRIPLETS = {
    "1m/target_4class": [(7, 1, 4), (2, 1, 3), (2, 2, 8), (2, 3, 9)],
    "1m/target_breakfree": [(3, 3, 27), (2, 4, 28), (2, 4, 12), (2, 2, 18)],
    "5m/target_4class": [(9, 1, 6), (2, 1, 3), (2, 3, 9), (2, 2, 4)],
    "5m/target_breakfree": [(4, 4, 12), (2, 3, 27), (2, 3, 24), (2, 2, 16)],
    "15m/target_4class": [(4, 1, 4), (2, 2, 10), (2, 2, 4), (2, 2, 6)],
    "15m/target_breakfree": [(5, 2, 18), (2, 4, 28), (2, 4, 32), (2, 4, 12)],
}

# ---------------------------------------------------------------------------
# Auto portfolio builder (winner-only from current + archive_legacy)
# ---------------------------------------------------------------------------
STAGE1_USE_AUTO_PORTFOLIO = True
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
STAGE1_PORTFOLIO_CONTEXT_GRANULARITY = "step"  # "step" or "snapshot"
STAGE1_PORTFOLIO_REQUIRE_70_MEAN_IF_POSSIBLE = True


def _coerce_triplets(value):
    out = []
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


def _resolve_stage1_triplet_grid():
    resolved = {
        unit: list(trips) for unit, trips in STAGE1_FALLBACK_MANUAL_TRIPLETS.items()
    }
    report = {
        unit: {
            "source": "manual",
            "selected_triplets": [list(t) for t in trips],
            "manual_metrics": None,
            "selected_metrics": None,
        }
        for unit, trips in STAGE1_FALLBACK_MANUAL_TRIPLETS.items()
    }
    if not STAGE1_USE_AUTO_PORTFOLIO:
        return resolved, report, None

    meta_dir = (
        PROJECT_ROOT
        / "data"
        / "htf_backtest_results"
        / "stage1_meta"
        / "catboost"
        / STAGE1_RUN_ID
    )
    autogen_path = meta_dir / "candidate_triplet_grid_autogen.json"
    portfolio_path = meta_dir / "candidate_portfolio_v2.json"
    build_result = None

    try:
        if (
            STAGE1_PORTFOLIO_REBUILD
            or not autogen_path.exists()
            or not portfolio_path.exists()
        ):
            build_result = build_stage1_winner_portfolio(
                run_id_or_path=STAGE1_RUN_ID,
                project_root=PROJECT_ROOT,
                model_name="catboost",
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

        if autogen_path.exists():
            with open(autogen_path) as f:
                autogen_map = json.load(f)
        else:
            autogen_map = {}
        if portfolio_path.exists():
            with open(portfolio_path) as f:
                portfolio_meta = json.load(f)
        else:
            portfolio_meta = {"units": {}}
    except Exception as e:
        print(f"Stage1 auto-portfolio disabled by error, using manual fallback: {e}")
        return resolved, report, build_result

    unit_meta = portfolio_meta.get("units", {})
    for unit, manual_triplets in STAGE1_FALLBACK_MANUAL_TRIPLETS.items():
        auto_triplets = _coerce_triplets(autogen_map.get(unit, []))
        if len(auto_triplets) == 0:
            continue
        if len(auto_triplets) > int(STAGE1_PORTFOLIO_DYNAMIC_CAP):
            auto_triplets = auto_triplets[: int(STAGE1_PORTFOLIO_DYNAMIC_CAP)]
        u = unit_meta.get(unit, {})
        combo_stats = {}
        for row in u.get("combo_stats", []):
            if not isinstance(row, dict):
                continue
            combo_stats[str(row.get("combo_key"))] = int(row.get("steps_seen", 0) or 0)
        validated = []
        for tri in auto_triplets:
            key = f"f{int(tri[0])}_v{int(tri[1])}_t{int(tri[2])}"
            steps_seen = combo_stats.get(key)
            if steps_seen is None:
                continue
            if steps_seen < int(STAGE1_PORTFOLIO_MIN_SUPPORT_STEPS):
                continue
            validated.append(tri)
        if validated:
            resolved[unit] = validated
        else:
            resolved[unit] = list(manual_triplets)
        report[unit] = {
            "source": (
                str(u.get("selected_source", "auto")) if validated else "manual"
            ),
            "selected_triplets": [
                list(t) for t in (validated if validated else manual_triplets)
            ],
            "manual_metrics": u.get("manual_metrics"),
            "selected_metrics": u.get("selected_metrics"),
        }
    return resolved, report, build_result


(
    STAGE1_TRIPLET_GRID_BY_UNIT,
    STAGE1_PORTFOLIO_REPORT_BY_UNIT,
    STAGE1_PORTFOLIO_BUILD_RESULT,
) = _resolve_stage1_triplet_grid()


def _stage1_tf_spec(
    tf: str, lookback_max: int, min_samples_4: int, min_samples_breakfree: int
):
    triplet_grid_4 = list(STAGE1_TRIPLET_GRID_BY_UNIT.get(f"{tf}/target_4class", []))
    triplet_grid_breakfree = list(
        STAGE1_TRIPLET_GRID_BY_UNIT.get(f"{tf}/target_breakfree", [])
    )
    all_triplets = triplet_grid_4 + triplet_grid_breakfree
    if all_triplets:
        max_train = max(int(t[2]) for t in all_triplets)
        max_folds = max(int(t[0]) for t in all_triplets)
        max_val = max(int(t[1]) for t in all_triplets)
    else:
        max_train, max_folds, max_val = 36, 9, 4
    lookback_min = max(100, max_train + max_folds * max_val + 2)
    return {
        # `shared_optuna` key is reused as a generic config container.
        # Stage-1 runner ignores optuna trials/timeouts.
        "shared_optuna": {
            "track_pred_metrics": False,
            "balance_strategy": "none",
            "balance_apply_to": "train",
            "cb_base_params": STAGE1_CB_BASE_PARAMS,
            "window_space": {
                "lookback_min": lookback_min,
                "lookback_max": lookback_max,
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
            },
            "model_space": {"num_boost_round_min": 300, "num_boost_round_max": 300},
        },
        "targets": {
            "target_4class": {
                "task_type": "multiclass",
                "n_classes": 4,
                "class_names": CLASS_NAMES_4,
                "feature_source": "target_4class",
                "optuna": {
                    "optuna_metric": "cross_direction_error",
                    "stage1_validity_target_col": "target_4class",
                    "window_space": {
                        "min_samples_per_class": min_samples_4,
                        "stage1_triplet_grid": triplet_grid_4,
                    },
                },
            },
            "target_breakfree": {
                "task_type": "multiclass",
                "n_classes": 3,
                "class_names": CLASS_NAMES_BREAKFREE,
                "feature_source": "target_4class",
                "optuna": {
                    "optuna_metric": "macro_f1",
                    "stage1_validity_target_col": "target_4class",
                    "window_space": {
                        "min_samples_per_class": min_samples_breakfree,
                        "stage1_triplet_grid": triplet_grid_breakfree,
                    },
                },
            },
        },
    }


STAGE1_MODEL_BACKTEST_SPECS = merge_backtest_specs(
    {
        "catboost": {
            "timeframes": {
                "1m": _stage1_tf_spec(
                    "1m", lookback_max=450, min_samples_4=150, min_samples_breakfree=150
                ),
                "5m": _stage1_tf_spec(
                    "5m", lookback_max=450, min_samples_4=100, min_samples_breakfree=100
                ),
                "15m": _stage1_tf_spec(
                    "15m", lookback_max=450, min_samples_4=50, min_samples_breakfree=50
                ),
            }
        }
    },
    {},
)
STAGE1_RESOLVED_BACKTEST = build_backtest_maps(STAGE1_MODEL_BACKTEST_SPECS)
TIMEFRAMES_BY_MODEL = STAGE1_RESOLVED_BACKTEST["timeframes_by_model"]
TARGETS_BY_MODEL = STAGE1_RESOLVED_BACKTEST["targets_by_model"]
N_CLASSES_BY_MODEL = STAGE1_RESOLVED_BACKTEST["n_classes_by_model"]
CLASS_NAMES_BY_MODEL = STAGE1_RESOLVED_BACKTEST["class_names_by_model"]
FEATURE_SOURCE_BY_MODEL = STAGE1_RESOLVED_BACKTEST["feature_source_by_model"]
OPTUNA_OVERRIDES_BY_MODEL = STAGE1_RESOLVED_BACKTEST["optuna_overrides_by_model"]
TARGET_REGISTRY = STAGE1_RESOLVED_BACKTEST["target_registry"]


def _print_stage1_setup_summary() -> None:
    print("Resolved stage1 setup:")
    print(f"Run profile: catboost_stage1, run_id={STAGE1_RUN_ID}")
    print(
        f"Resume={bool(STAGE1_RESUME)}, resume_mode={STAGE1_RESUME_MODE}, "
        f"requested_steps={int(STAGE1_N_STEPS)}"
    )
    print(
        "Adaptive winner recovery: "
        f"threshold={STAGE1_QUALITY_ACCURACY_THRESHOLD:.2f}, "
        f"probe_enabled={bool(STAGE1_PROBE_ENABLED)}, "
        f"probe_tiers={STAGE1_PROBE_TIER_SIZES}, "
        f"probe_cap={int(STAGE1_PROBE_MAX_EXTRA_CANDIDATES)}, "
        f"probe_scope={STAGE1_PROBE_SOURCE_SCOPE}, "
        f"backfill={bool(STAGE1_BACKFILL_LOW_QUALITY_COMPLETED)}, "
        f"promotion_mode={STAGE1_PROMOTION_MODE}, "
        f"promotion_cap={int(STAGE1_PROMOTED_COMBO_CAP_PER_UNIT)}"
    )
    if STAGE1_USE_AUTO_PORTFOLIO:
        print(
            "Stage1 portfolio: "
            f"source={STAGE1_PORTFOLIO_SOURCE}, "
            f"dynamic_cap={int(STAGE1_PORTFOLIO_DYNAMIC_CAP)}, "
            f"min_support={int(STAGE1_PORTFOLIO_MIN_SUPPORT_STEPS)}, "
            f"high_acc>={STAGE1_PORTFOLIO_HIGH_ACCURACY_THRESHOLD:.2f}, "
            f"target_cov70={STAGE1_PORTFOLIO_TARGET_HIGH_ACCURACY_COVERAGE:.2f}"
        )
        if STAGE1_PORTFOLIO_BUILD_RESULT is not None:
            print("  portfolio_build=refreshed")
        else:
            print("  portfolio_build=loaded_existing")
    tf_targets = TARGETS_BY_MODEL.get("catboost", {})
    tf_overrides = OPTUNA_OVERRIDES_BY_MODEL.get("catboost", {})
    for tf in TIMEFRAMES_BY_MODEL.get("catboost", []):
        for target_col in tf_targets.get(tf, []):
            target_overrides = {}
            if isinstance(tf_overrides.get(tf, {}), dict):
                target_overrides = tf_overrides[tf].get(target_col, {})
            window_space = dict(target_overrides.get("window_space", {}))
            combos = build_stage1_combo_grid(SimpleNamespace(**window_space))
            unit_key = f"{tf}/{target_col}"
            portfolio_info = STAGE1_PORTFOLIO_REPORT_BY_UNIT.get(unit_key, {})
            source = portfolio_info.get("source", "manual")
            print(
                f"  {unit_key}: source={source}, "
                f"triplets={window_space.get('stage1_triplet_grid', [])}"
            )
            manual_metrics = portfolio_info.get("manual_metrics")
            selected_metrics = portfolio_info.get("selected_metrics")
            if isinstance(manual_metrics, dict) and isinstance(selected_metrics, dict):
                print(
                    "    compare_vs_manual: "
                    f"mean_best_acc={selected_metrics.get('mean_best_acc', 0):.6f} "
                    f"(manual={manual_metrics.get('mean_best_acc', 0):.6f}), "
                    f"cov70={selected_metrics.get('cov70', 0):.6f} "
                    f"(manual={manual_metrics.get('cov70', 0):.6f})"
                )
            print(f"    combinations_per_step={len(combos)}")


def _write_stage1_collection_plan() -> Path:
    from datetime import datetime as _dt

    base_run_dir = PROJECT_ROOT / "data" / "htf_backtest_results" / STAGE1_RUN_ID
    model_dir = base_run_dir / "catboost"
    base_run_dir.mkdir(parents=True, exist_ok=True)
    model_dir.mkdir(parents=True, exist_ok=True)
    required_files = [
        "stage1/stage1_step_summary.json",
        "stage1/stage1_config_snapshot.json",
        "stage1/stage1_combo_index.parquet",
        "stage1/stage1_fold_windows.parquet",
        "stage1/stage1_val_predictions.parquet",
        "stage1/stage1_pred_batch_predictions.parquet",
        "stage1/stage1_predecision_context.json",
        "stage1/stage1_predecision_context.parquet",
        "stage1/stage1_runtime_profile.json",
        "batch_metadata.json",
    ]
    unit_status = {}
    totals = {"complete_steps": 0, "incomplete_steps": 0, "discovered_steps": 0}
    for tf in TIMEFRAMES_BY_MODEL.get("catboost", []):
        for target_col in TARGETS_BY_MODEL.get("catboost", {}).get(tf, []):
            unit_dir = model_dir / tf / str(target_col).replace("/", "_")
            unit_dir.mkdir(parents=True, exist_ok=True)
            complete = 0
            incomplete = 0
            missing_examples = []
            for step_dir in sorted(unit_dir.glob("batch_*")):
                totals["discovered_steps"] += 1
                missing = [p for p in required_files if not (step_dir / p).exists()]
                if missing:
                    incomplete += 1
                    if len(missing_examples) < 5:
                        missing_examples.append(
                            {"batch_dir": step_dir.name, "missing_files": missing}
                        )
                else:
                    complete += 1
            totals["complete_steps"] += complete
            totals["incomplete_steps"] += incomplete
            unit_status[f"{tf}/{target_col}"] = {
                "complete_steps": complete,
                "incomplete_steps": incomplete,
                "missing_examples": missing_examples,
            }
    plan = {
        "generated_at": _dt.utcnow().isoformat() + "Z",
        "run_id": STAGE1_RUN_ID,
        "run_profile": "catboost_stage1",
        "resume": bool(STAGE1_RESUME),
        "resume_mode": str(STAGE1_RESUME_MODE),
        "requested_n_steps": int(STAGE1_N_STEPS),
        "totals": totals,
        "units": unit_status,
        "required_step_files": required_files,
    }
    plan_path = base_run_dir / "stage1_collection_plan.json"
    with open(plan_path, "w") as f:
        json.dump(plan, f, indent=2)
    print(
        "Stage1 collection plan: "
        f"{totals['complete_steps']} complete, {totals['incomplete_steps']} incomplete, "
        f"{totals['discovered_steps']} discovered step folders"
    )
    print(f"Plan file: {plan_path}")
    return plan_path


_print_stage1_setup_summary()
stage1_plan_path = _write_stage1_collection_plan()

results_stage1 = run_walk_forward_stage1_grid(
    n_steps=STAGE1_N_STEPS,
    timeframes=TIMEFRAMES_BY_MODEL["catboost"],
    run_description="Stage-1 fold-grid dataset generation (CatBoost)",
    verbose=True,
    debug_batches=True,
    run_id=STAGE1_RUN_ID,
    resume=bool(STAGE1_RESUME),
    resume_mode=STAGE1_RESUME_MODE,
    allow_override_mismatch=ALLOW_OVERRIDE_MISMATCH,
    model_name="catboost",
    optuna_overrides_by_model=OPTUNA_OVERRIDES_BY_MODEL,
    targets_by_model=TARGETS_BY_MODEL,
    n_classes_by_model=N_CLASSES_BY_MODEL,
    class_names_by_model=CLASS_NAMES_BY_MODEL,
    feature_source_by_model=FEATURE_SOURCE_BY_MODEL,
    target_registry=TARGET_REGISTRY,
    stage1_quality_accuracy_threshold=STAGE1_QUALITY_ACCURACY_THRESHOLD,
    stage1_probe_enabled=STAGE1_PROBE_ENABLED,
    stage1_probe_tier_sizes=STAGE1_PROBE_TIER_SIZES,
    stage1_probe_max_extra_candidates=STAGE1_PROBE_MAX_EXTRA_CANDIDATES,
    stage1_probe_source_scope=STAGE1_PROBE_SOURCE_SCOPE,
    stage1_backfill_low_quality_completed=STAGE1_BACKFILL_LOW_QUALITY_COMPLETED,
    stage1_promotion_mode=STAGE1_PROMOTION_MODE,
    stage1_promoted_combo_cap_per_unit=STAGE1_PROMOTED_COMBO_CAP_PER_UNIT,
)

# %%
# ============================================================================
# CELL 15: HTF WALK-FORWARD BACKTEST (CATBOOST STAGE-1 / STEP-2)
# ============================================================================

import sys
from pathlib import Path

# Allow running Cell 15 independently (without requiring Cell 14 to be executed first).
if "PROJECT_ROOT" not in dir():
    PROJECT_ROOT = Path("/media/przem/linux_data/RiskYieldMM (Copy)")

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Force fresh Stage-1 Step-2 module load in notebook sessions.
# This avoids stale function signatures after code edits.
# Defensive fallback for standalone/partial reruns.
if "importlib" not in globals():
    import importlib
if "inspect" not in globals():
    import inspect
importlib.invalidate_caches()
for _m in list(sys.modules.keys()):
    if _m.startswith("scripts.htf_backtest.catboost.stage1_step2"):
        del sys.modules[_m]
import scripts.htf_backtest.catboost.stage1_step2 as _stage1_step2_mod

_stage1_step2_mod = importlib.reload(_stage1_step2_mod)
run_stage1_step2_feature_pruning = _stage1_step2_mod.run_stage1_step2_feature_pruning
print(
    "Cell 15 loaded stage1_step2 signature:\n"
    f"  {inspect.signature(run_stage1_step2_feature_pruning)}"
)

if "STAGE1_RUN_ID" not in dir():
    STAGE1_RUN_ID = "stage1_catboost_live"


def _recover_stage1_maps_from_artifacts(
    project_root: Path, run_id: str, model_name: str = "catboost"
):
    """
    Rebuild Stage-1 runner maps from stored stage1_config_snapshot.json files.
    Allows running Cell 15 standalone after kernel restart.
    """
    base_dir = project_root / "data" / "htf_backtest_results" / run_id / model_name
    if not base_dir.exists():
        raise FileNotFoundError(f"Stage-1 run folder not found: {base_dir}")

    timeframes = []
    targets_by_tf = {}
    n_classes_by_tf = {}
    class_names_by_tf = {}
    feature_source_by_tf = {}
    overrides_by_tf = {}

    for tf_dir in sorted([p for p in base_dir.iterdir() if p.is_dir()]):
        tf = tf_dir.name
        timeframes.append(tf)
        targets_by_tf[tf] = []
        n_classes_by_tf[tf] = {}
        class_names_by_tf[tf] = {}
        feature_source_by_tf[tf] = {}
        overrides_by_tf[tf] = {}

        for target_dir in sorted([p for p in tf_dir.iterdir() if p.is_dir()]):
            snapshots = sorted(
                target_dir.glob("batch_*/stage1/stage1_config_snapshot.json")
            )
            if not snapshots:
                continue

            # Use latest snapshot for that target dir.
            snap_path = snapshots[-1]
            snap = json.loads(snap_path.read_text())
            cfg = dict(snap.get("config", {}))
            window_space = dict(snap.get("window_space", {}))
            model_space = dict(snap.get("model_space", {}))

            target = str(cfg.get("target", target_dir.name))
            feature_target = str(cfg.get("feature_target", target))
            n_classes = int(
                cfg.get("n_classes", max(2, len(cfg.get("class_names", []))))
            )
            class_names = list(
                cfg.get("class_names", [f"class_{i}" for i in range(n_classes)])
            )
            opt_metric = str(cfg.get("optuna_metric", "macro_f1"))

            if target not in targets_by_tf[tf]:
                targets_by_tf[tf].append(target)
            n_classes_by_tf[tf][target] = n_classes
            class_names_by_tf[tf][target] = class_names
            feature_source_by_tf[tf][target] = feature_target

            ov = {"optuna_metric": opt_metric}
            if window_space:
                ov["window_space"] = window_space
            if model_space:
                ov["model_space"] = model_space
            if "cb_base_params" in cfg and isinstance(cfg["cb_base_params"], dict):
                ov["cb_base_params"] = dict(cfg["cb_base_params"])
            if "exclude_tail_pct" in cfg and cfg["exclude_tail_pct"] is not None:
                ov["exclude_tail_pct"] = float(cfg["exclude_tail_pct"])
            overrides_by_tf[tf][target] = ov

    recovered = {
        "timeframes_by_model": {model_name: sorted(timeframes)},
        "targets_by_model": {model_name: targets_by_tf},
        "n_classes_by_model": {model_name: n_classes_by_tf},
        "class_names_by_model": {model_name: class_names_by_tf},
        "feature_source_by_model": {model_name: feature_source_by_tf},
        "optuna_overrides_by_model": {model_name: overrides_by_tf},
    }
    return recovered


# Cell 15 expects Stage-1 spec/maps prepared in Cell 14.
# If they are missing, recover them directly from stored Stage-1 artifacts.
_cell15_required = {
    "TIMEFRAMES_BY_MODEL",
    "TARGETS_BY_MODEL",
    "N_CLASSES_BY_MODEL",
    "CLASS_NAMES_BY_MODEL",
    "FEATURE_SOURCE_BY_MODEL",
    "OPTUNA_OVERRIDES_BY_MODEL",
}
_cell15_missing = [name for name in sorted(_cell15_required) if name not in dir()]
if _cell15_missing:
    _recovered = _recover_stage1_maps_from_artifacts(
        project_root=PROJECT_ROOT,
        run_id=STAGE1_RUN_ID,
        model_name="catboost",
    )
    TIMEFRAMES_BY_MODEL = _recovered["timeframes_by_model"]
    TARGETS_BY_MODEL = _recovered["targets_by_model"]
    N_CLASSES_BY_MODEL = _recovered["n_classes_by_model"]
    CLASS_NAMES_BY_MODEL = _recovered["class_names_by_model"]
    FEATURE_SOURCE_BY_MODEL = _recovered["feature_source_by_model"]
    OPTUNA_OVERRIDES_BY_MODEL = _recovered["optuna_overrides_by_model"]
    print(
        "Cell 15 bootstrap: recovered Stage-1 maps from artifacts for run "
        f"{STAGE1_RUN_ID}"
    )

# Step-2 uses Stage-1 Step-1 artifacts and compares baseline vs filtered features
# for ALL configured Stage-1 combos per timeframe/target, plus a global mask.
STAGE1_STEP2_SOURCE_RUN = STAGE1_RUN_ID
STAGE1_STEP2_TIMEFRAMES = TIMEFRAMES_BY_MODEL["catboost"]
STAGE1_STEP2_MAX_STEPS_PER_UNIT = 500
STAGE1_STEP2_FEATURE_SELECTOR_METHOD = "recursive_shap"
STAGE1_STEP2_SELECTOR_SHAP_CALC_TYPE = "Regular"  # Regular | Approximate | Exact
STAGE1_STEP2_SELECTOR_STEPS = 3
STAGE1_STEP2_SELECTOR_KEEP_RATIO = 0.7
STAGE1_STEP2_SELECTOR_FOLD_VOTE_MIN_FRAC = 0.5
STAGE1_STEP2_SELECTOR_STEP_VOTE_MIN_FRAC = 0.5
STAGE1_STEP2_NOISY_BOTTOM_QUANTILE = 0.25
STAGE1_STEP2_NOISY_PRESENCE_THRESHOLD = 0.90
STAGE1_STEP2_MIN_FEATURES_KEEP = 24
STAGE1_STEP2_FEATURE_IMPORTANCE_TYPE = "PredictionValuesChange"
STAGE1_STEP2_REWARD_CROSS_ERROR_WEIGHT = 0.5
STAGE1_STEP2_PROMOTION_MIN_REWARD_DELTA = 0.0
STAGE1_STEP2_PROMOTION_MAX_CROSS_ERR_DELTA = 0.01
STAGE1_STEP2_PROMOTION_MIN_MACRO_F1_DELTA = -0.005
STAGE1_STEP2_PROGRESS_EVERY_STEPS = 5
# Keep Step-2 runs isolated by profile to avoid overwriting summaries
# (e.g. smoke/debug runs replacing full 500-step runs).
if (
    STAGE1_STEP2_MAX_STEPS_PER_UNIT is None
    or int(STAGE1_STEP2_MAX_STEPS_PER_UNIT) >= 500
):
    STAGE1_STEP2_RUN_TAG = "full"
else:
    STAGE1_STEP2_RUN_TAG = "smoke"
STAGE1_STEP2_OUTPUT_SUBDIR = f"stage1_step2_{STAGE1_STEP2_RUN_TAG}"
# Use balanced comparison in Step-2 summaries:
# reward = macro_f1 - STAGE1_STEP2_REWARD_CROSS_ERROR_WEIGHT * cross_direction_error
# Alternatives: "selection_metric", "reward"
# For current Stage-1 flow we focus on prediction-batch accuracy.
STAGE1_STEP2_COMPARISON_METRIC_MODE = "accuracy"
STAGE1_STEP2_WINNER_METRIC = "accuracy"
STAGE1_STEP2_NO_WORSE_ACCURACY_GUARD = True
STAGE1_STEP2_SKIP_PRUNE_IF_BASELINE_ACCURACY_GE = 1.0
# Alignment/trace controls:
# - enforce_step1_combo_alignment: require Step-1 combo grid continuity per step
# - enforce_step1_fold_alignment: require full fold_id continuity per selected combo
# - debug_step_selection: print winner/mismatch summary each processed step
# - debug_combo_detail: print per-combo ranges + selected metric while scanning
# - debug_artifact_paths: print output artifact names per combo
STAGE1_STEP2_ENFORCE_COMBO_ALIGNMENT = True
STAGE1_STEP2_ENFORCE_FOLD_ALIGNMENT = True
STAGE1_STEP2_DEBUG_STEP_SELECTION = True
STAGE1_STEP2_DEBUG_COMBO_DETAIL = True
STAGE1_STEP2_DEBUG_ARTIFACT_PATHS = True
# Walk-forward continuity debug for Step-2 (train/val/pred ranges and row counts).
STAGE1_STEP2_DEBUG_WALKFORWARD = True
STAGE1_STEP2_DEBUG_WALKFORWARD_EVERY_STEPS = 1
# Winner-only means each step contributes to the single best combo for that
# timeframe/target; combo feature sets are optimized independently from the
# steps they win. Alternative: "all_combos".
STAGE1_STEP2_COMBO_PROCESSING_MODE = "winner_only"

print(
    "Cell 15 Step-2 output:\n"
    f"  run_id={STAGE1_STEP2_SOURCE_RUN}\n"
    f"  output_subdir={STAGE1_STEP2_OUTPUT_SUBDIR}\n"
    f"  max_steps_per_unit={STAGE1_STEP2_MAX_STEPS_PER_UNIT}\n"
    f"  selector={STAGE1_STEP2_FEATURE_SELECTOR_METHOD}, "
    f"shap={STAGE1_STEP2_SELECTOR_SHAP_CALC_TYPE}, "
    f"steps={STAGE1_STEP2_SELECTOR_STEPS}, "
    f"keep_ratio={STAGE1_STEP2_SELECTOR_KEEP_RATIO}, "
    f"fold_vote={STAGE1_STEP2_SELECTOR_FOLD_VOTE_MIN_FRAC}, "
    f"step_vote={STAGE1_STEP2_SELECTOR_STEP_VOTE_MIN_FRAC}"
)

results_stage1_step2 = run_stage1_step2_feature_pruning(
    stage1_run_id_or_path=STAGE1_STEP2_SOURCE_RUN,
    project_root=PROJECT_ROOT,
    model_name="catboost",
    timeframes=STAGE1_STEP2_TIMEFRAMES,
    targets_by_model=TARGETS_BY_MODEL,
    n_classes_by_model=N_CLASSES_BY_MODEL,
    class_names_by_model=CLASS_NAMES_BY_MODEL,
    feature_source_by_model=FEATURE_SOURCE_BY_MODEL,
    optuna_overrides_by_model=OPTUNA_OVERRIDES_BY_MODEL,
    max_steps_per_unit=STAGE1_STEP2_MAX_STEPS_PER_UNIT,
    feature_selector_method=STAGE1_STEP2_FEATURE_SELECTOR_METHOD,
    selector_shap_calc_type=STAGE1_STEP2_SELECTOR_SHAP_CALC_TYPE,
    selector_steps=STAGE1_STEP2_SELECTOR_STEPS,
    selector_keep_ratio=STAGE1_STEP2_SELECTOR_KEEP_RATIO,
    selector_fold_vote_min_frac=STAGE1_STEP2_SELECTOR_FOLD_VOTE_MIN_FRAC,
    selector_step_vote_min_frac=STAGE1_STEP2_SELECTOR_STEP_VOTE_MIN_FRAC,
    noisy_bottom_quantile=STAGE1_STEP2_NOISY_BOTTOM_QUANTILE,
    noisy_presence_threshold=STAGE1_STEP2_NOISY_PRESENCE_THRESHOLD,
    min_features_keep=STAGE1_STEP2_MIN_FEATURES_KEEP,
    feature_importance_type=STAGE1_STEP2_FEATURE_IMPORTANCE_TYPE,
    reward_cross_error_weight=STAGE1_STEP2_REWARD_CROSS_ERROR_WEIGHT,
    promotion_min_reward_delta=STAGE1_STEP2_PROMOTION_MIN_REWARD_DELTA,
    promotion_max_cross_direction_error_delta=STAGE1_STEP2_PROMOTION_MAX_CROSS_ERR_DELTA,
    promotion_min_macro_f1_delta=STAGE1_STEP2_PROMOTION_MIN_MACRO_F1_DELTA,
    output_subdir=STAGE1_STEP2_OUTPUT_SUBDIR,
    combo_processing_mode=STAGE1_STEP2_COMBO_PROCESSING_MODE,
    progress_every_steps=STAGE1_STEP2_PROGRESS_EVERY_STEPS,
    comparison_metric_mode=STAGE1_STEP2_COMPARISON_METRIC_MODE,
    winner_metric=STAGE1_STEP2_WINNER_METRIC,
    no_worse_accuracy_guard=STAGE1_STEP2_NO_WORSE_ACCURACY_GUARD,
    skip_prune_if_baseline_accuracy_ge=STAGE1_STEP2_SKIP_PRUNE_IF_BASELINE_ACCURACY_GE,
    enforce_step1_combo_alignment=STAGE1_STEP2_ENFORCE_COMBO_ALIGNMENT,
    enforce_step1_fold_alignment=STAGE1_STEP2_ENFORCE_FOLD_ALIGNMENT,
    debug_step_selection=STAGE1_STEP2_DEBUG_STEP_SELECTION,
    debug_combo_detail=STAGE1_STEP2_DEBUG_COMBO_DETAIL,
    debug_artifact_paths=STAGE1_STEP2_DEBUG_ARTIFACT_PATHS,
    debug_walkforward=STAGE1_STEP2_DEBUG_WALKFORWARD,
    debug_walkforward_every_steps=STAGE1_STEP2_DEBUG_WALKFORWARD_EVERY_STEPS,
    verbose=True,
)

print("\nStage-1 Step-2 summary artifact:")
print(results_stage1_step2["artifacts"]["run_summary"])

# %%
