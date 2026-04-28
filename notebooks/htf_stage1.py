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


import importlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

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
# CELL 14A: STAGE-1 WINNERS EXTRACTION (1m/target_4class, all discovered steps)
# ============================================================================

from pathlib import Path

import numpy as np
import polars as pl

# Standalone-safe bootstrap (so Cell 14A can run without Cell 14).
if "PROJECT_ROOT" not in dir():
    PROJECT_ROOT = Path("/media/przem/linux_data/RiskYieldMM (Copy)")
else:
    PROJECT_ROOT = Path(PROJECT_ROOT)

if "STAGE1_RUN_ID" not in dir():
    STAGE1_RUN_ID = "stage1_catboost_live"

if "STAGE1_N_STEPS" not in dir():
    STAGE1_N_STEPS = 500

STAGE1_WINNERS_UNIT = "1m/target_4class"
_winners_tf, _winners_target = STAGE1_WINNERS_UNIT.split("/", 1)
_winners_unit_dir = (
    PROJECT_ROOT
    / "data"
    / "htf_backtest_results"
    / STAGE1_RUN_ID
    / "catboost"
    / _winners_tf
    / _winners_target
)

_winners_batch_dirs = sorted(
    [p for p in _winners_unit_dir.glob("batch_*") if p.is_dir()]
)
_winners_summary_paths = sorted(
    [
        p
        for p in _winners_unit_dir.glob("batch_*/stage1/stage1_step_summary.json")
        if p.is_file()
    ]
)
_winners_missing_summary = sorted(
    [
        p.name
        for p in _winners_batch_dirs
        if not (p / "stage1" / "stage1_step_summary.json").exists()
    ]
)


def _macro_f1_multiclass(
    y_true: np.ndarray, y_pred: np.ndarray, n_classes: int
) -> float:
    f1_vals = []
    for c in range(int(n_classes)):
        tp = int(((y_true == c) & (y_pred == c)).sum())
        fp = int(((y_true != c) & (y_pred == c)).sum())
        fn = int(((y_true == c) & (y_pred != c)).sum())
        if tp == 0 and fp == 0 and fn == 0:
            f1_vals.append(0.0)
            continue
        prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (2.0 * prec * rec / (prec + rec)) if (prec + rec) > 0 else 0.0
        f1_vals.append(float(f1))
    return float(np.mean(f1_vals)) if f1_vals else 0.0


def _cross_direction_error_4class(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    # 4-class directional mapping:
    # - down: 0,1
    # - up:   2,3
    true_is_up = y_true >= 2
    pred_is_up = y_pred >= 2
    return float((true_is_up != pred_is_up).mean()) if len(y_true) else 0.0


def _iter_step_snapshots(step_stage1_dir: Path):
    current_combo = step_stage1_dir / "stage1_combo_index.parquet"
    current_pred = step_stage1_dir / "stage1_pred_batch_predictions.parquet"
    if current_combo.exists() and current_pred.exists():
        yield ("current", current_combo, current_pred)

    archive_root = step_stage1_dir / "archive_legacy"
    if archive_root.exists():
        for sub in sorted([p for p in archive_root.iterdir() if p.is_dir()]):
            combo_path = sub / "stage1_combo_index.parquet"
            pred_path = sub / "stage1_pred_batch_predictions.parquet"
            if combo_path.exists() and pred_path.exists():
                yield (f"archive:{sub.name}", combo_path, pred_path)


def _winner_and_combo_metrics_from_all_snapshots(
    step_stage1_dir: Path,
) -> tuple[dict | None, list[dict], dict]:
    # Keep strongest metric record for each action_key within this step,
    # across current + archive snapshots.
    best_by_action: dict[str, dict] = {}
    per_combo_rows: list[dict] = []
    snapshots_seen = 0
    combo_instances_seen = 0

    for snapshot_label, combo_path, pred_path in _iter_step_snapshots(step_stage1_dir):
        try:
            combo_idx = pl.read_parquet(combo_path)
            pred = pl.read_parquet(pred_path)
        except Exception:
            continue

        snapshots_seen += 1
        if pred.is_empty() or combo_idx.is_empty():
            continue

        if "scope" in pred.columns:
            pred = pred.filter(pl.col("scope") == "pred_batch")
        if pred.is_empty():
            continue
        if not {"y_true", "y_pred", "combo_id"}.issubset(set(pred.columns)):
            continue
        if not {"combo_id", "action_key"}.issubset(set(combo_idx.columns)):
            continue

        combo_map = dict(
            zip(
                combo_idx["combo_id"].cast(pl.Int64).to_list(),
                combo_idx["action_key"].to_list(),
            )
        )
        for combo_id in sorted(pred["combo_id"].cast(pl.Int64).unique().to_list()):
            action_key = combo_map.get(int(combo_id))
            if action_key in (None, ""):
                continue
            pred_c = pred.filter(pl.col("combo_id") == int(combo_id))
            y_true = pred_c["y_true"].cast(pl.Int16).to_numpy()
            y_pred = pred_c["y_pred"].cast(pl.Int16).to_numpy()
            if len(y_true) == 0:
                continue

            combo_instances_seen += 1
            acc = float((y_true == y_pred).mean())
            macro_f1 = _macro_f1_multiclass(y_true, y_pred, n_classes=4)
            cross_err = _cross_direction_error_4class(y_true, y_pred)
            row = {
                "combo_id": int(combo_id),
                "action_key": str(action_key),
                "accuracy": acc,
                "macro_f1": macro_f1,
                "cross_direction_error": cross_err,
                "pred_rows": int(len(y_true)),
                "snapshot": str(snapshot_label),
            }
            per_combo_rows.append(row)

            prev = best_by_action.get(str(action_key))
            if prev is None:
                best_by_action[str(action_key)] = row
            else:
                prev_key = (
                    float(prev["accuracy"]),
                    float(prev["macro_f1"]),
                    -float(prev["cross_direction_error"]),
                    int(prev["pred_rows"]),
                    -int(prev["combo_id"]),
                )
                new_key = (
                    float(row["accuracy"]),
                    float(row["macro_f1"]),
                    -float(row["cross_direction_error"]),
                    int(row["pred_rows"]),
                    -int(row["combo_id"]),
                )
                if new_key > prev_key:
                    best_by_action[str(action_key)] = row

    if not best_by_action:
        return (
            None,
            per_combo_rows,
            {
                "snapshots_seen": int(snapshots_seen),
                "combo_instances_seen": int(combo_instances_seen),
                "unique_actions_tested": 0,
            },
        )

    winners = list(best_by_action.values())
    # Winner tie-breaks:
    # 1) accuracy DESC
    # 2) macro_f1 DESC
    # 3) cross_direction_error ASC
    # 4) action_key ASC
    winners.sort(
        key=lambda r: (
            -float(r["accuracy"]),
            -float(r["macro_f1"]),
            float(r["cross_direction_error"]),
            str(r["action_key"]),
        )
    )
    winner = dict(winners[0])
    winner["selection_scope"] = "all_tested_combos_current_plus_archive"
    return (
        winner,
        per_combo_rows,
        {
            "snapshots_seen": int(snapshots_seen),
            "combo_instances_seen": int(combo_instances_seen),
            "unique_actions_tested": int(len(best_by_action)),
        },
    )


_winner_rows = []
_step_combo_metric_rows = []
for summary_path in _winners_summary_paths:
    step_stage1_dir = summary_path.parent
    with open(summary_path) as f:
        s = json.load(f)
    winner, combo_rows, coverage = _winner_and_combo_metrics_from_all_snapshots(
        step_stage1_dir
    )
    pred_batch_from_path = None
    try:
        pred_batch_from_path = int(summary_path.parents[1].name.split("_")[1])
    except Exception:
        pred_batch_from_path = None
    pred_batch = (
        int(s.get("pred_batch"))
        if s.get("pred_batch") is not None
        else pred_batch_from_path
    )
    for r in combo_rows:
        _step_combo_metric_rows.append(
            {
                "pred_batch": pred_batch,
                "action_key": str(r.get("action_key"))
                if r.get("action_key") is not None
                else None,
                "combo_id": int(r.get("combo_id"))
                if r.get("combo_id") is not None
                else None,
                "accuracy": float(r.get("accuracy"))
                if r.get("accuracy") is not None
                else None,
                "macro_f1": float(r.get("macro_f1"))
                if r.get("macro_f1") is not None
                else None,
                "cross_direction_error": (
                    float(r.get("cross_direction_error"))
                    if r.get("cross_direction_error") is not None
                    else None
                ),
                "pred_rows": int(r.get("pred_rows"))
                if r.get("pred_rows") is not None
                else None,
                "snapshot": str(r.get("snapshot"))
                if r.get("snapshot") is not None
                else None,
                "summary_path": str(summary_path),
            }
        )
    _winner_rows.append(
        {
            "pred_batch": pred_batch,
            "summary_winner_combo_key": (
                str(s.get("winner_combo_key"))
                if s.get("winner_combo_key") not in (None, "")
                else None
            ),
            "winner_combo_key": (
                str(winner.get("action_key"))
                if winner is not None and winner.get("action_key") not in (None, "")
                else None
            ),
            "winner_accuracy": (
                float(winner.get("accuracy"))
                if winner is not None and winner.get("accuracy") is not None
                else None
            ),
            "winner_macro_f1": (
                float(winner.get("macro_f1"))
                if winner is not None and winner.get("macro_f1") is not None
                else None
            ),
            "winner_cross_direction_error": (
                float(winner.get("cross_direction_error"))
                if winner is not None
                and winner.get("cross_direction_error") is not None
                else None
            ),
            "winner_selection_source": (
                "pred_payload_all_tested_combos"
                if winner is not None
                else "summary_missing_payload"
            ),
            "winner_pred_rows": (
                int(winner.get("pred_rows"))
                if winner is not None and winner.get("pred_rows") is not None
                else None
            ),
            "winner_source_snapshot": (
                str(winner.get("snapshot"))
                if winner is not None and winner.get("snapshot") is not None
                else None
            ),
            "unique_actions_tested": int(coverage.get("unique_actions_tested", 0)),
            "combo_instances_seen": int(coverage.get("combo_instances_seen", 0)),
            "snapshots_seen": int(coverage.get("snapshots_seen", 0)),
            "quality_pass": bool(s.get("quality_pass", False)),
            "quality_unresolved": bool(s.get("quality_unresolved", False)),
            "probe_exhausted": bool(s.get("probe_exhausted", False)),
            "probe_tiers_run": (
                int(s.get("probe_tiers_run"))
                if s.get("probe_tiers_run") is not None
                else None
            ),
            "probe_candidates_evaluated": (
                int(s.get("probe_candidates_evaluated"))
                if s.get("probe_candidates_evaluated") is not None
                else None
            ),
            "combo_count_total": (
                int(s.get("combo_count_total"))
                if s.get("combo_count_total") is not None
                else None
            ),
            "combo_count_completed": (
                int(s.get("combo_count_completed"))
                if s.get("combo_count_completed") is not None
                else None
            ),
            "runtime_s": float(s.get("runtime_s"))
            if s.get("runtime_s") is not None
            else None,
            "summary_path": str(summary_path),
        }
    )

winners_1m_target_4class_df = (
    pl.DataFrame(_winner_rows)
    if _winner_rows
    else pl.DataFrame(
        schema={
            "pred_batch": pl.Int32,
            "summary_winner_combo_key": pl.Utf8,
            "winner_combo_key": pl.Utf8,
            "winner_accuracy": pl.Float64,
            "winner_macro_f1": pl.Float64,
            "winner_cross_direction_error": pl.Float64,
            "winner_selection_source": pl.Utf8,
            "winner_pred_rows": pl.Int32,
            "winner_source_snapshot": pl.Utf8,
            "unique_actions_tested": pl.Int32,
            "combo_instances_seen": pl.Int32,
            "snapshots_seen": pl.Int32,
            "quality_pass": pl.Boolean,
            "quality_unresolved": pl.Boolean,
            "probe_exhausted": pl.Boolean,
            "probe_tiers_run": pl.Int32,
            "probe_candidates_evaluated": pl.Int32,
            "combo_count_total": pl.Int32,
            "combo_count_completed": pl.Int32,
            "runtime_s": pl.Float64,
            "summary_path": pl.Utf8,
        }
    )
)

if not winners_1m_target_4class_df.is_empty():
    winners_1m_target_4class_df = (
        winners_1m_target_4class_df.sort("pred_batch")
        .with_row_index(name="step_idx", offset=1)
        .select(
            [
                "pred_batch",
                "step_idx",
                "summary_winner_combo_key",
                "winner_combo_key",
                "winner_accuracy",
                "winner_macro_f1",
                "winner_cross_direction_error",
                "winner_selection_source",
                "winner_pred_rows",
                "winner_source_snapshot",
                "unique_actions_tested",
                "combo_instances_seen",
                "snapshots_seen",
                "quality_pass",
                "quality_unresolved",
                "probe_exhausted",
                "probe_tiers_run",
                "probe_candidates_evaluated",
                "combo_count_total",
                "combo_count_completed",
                "runtime_s",
                "summary_path",
            ]
        )
    )

# Diagnostics
_rows_extracted = int(len(winners_1m_target_4class_df))
_discovered_steps = int(len(_winners_batch_dirs))
_min_pred_batch = (
    int(winners_1m_target_4class_df["pred_batch"].min()) if _rows_extracted else None
)
_max_pred_batch = (
    int(winners_1m_target_4class_df["pred_batch"].max()) if _rows_extracted else None
)
_missing_winner_key = (
    int(winners_1m_target_4class_df["winner_combo_key"].is_null().sum())
    if _rows_extracted
    else 0
)
_unique_winner_combo_count = (
    int(winners_1m_target_4class_df["winner_combo_key"].drop_nulls().n_unique())
    if _rows_extracted
    else 0
)
_winners_from_payload = (
    int(
        (
            winners_1m_target_4class_df["winner_selection_source"]
            == "pred_payload_all_tested_combos"
        ).sum()
    )
    if _rows_extracted
    else 0
)
_actions_tested_stats = (
    winners_1m_target_4class_df.select(
        [
            pl.col("unique_actions_tested").min().alias("min"),
            pl.col("unique_actions_tested").median().alias("median"),
            pl.col("unique_actions_tested").mean().alias("mean"),
            pl.col("unique_actions_tested").max().alias("max"),
        ]
    ).to_dicts()[0]
    if _rows_extracted
    else {"min": 0, "median": 0.0, "mean": 0.0, "max": 0}
)
_share_thresholds = [0.90, 0.80, 0.70, 0.60, 0.50]
_share_by_threshold = {}
for _thr in _share_thresholds:
    _share_by_threshold[_thr] = (
        float((winners_1m_target_4class_df["winner_accuracy"] >= _thr).mean())
        if _rows_extracted
        else 0.0
    )
_share_ge_070 = float(_share_by_threshold[0.70])
_winner_metric_summary = {
    "acc_mean": None,
    "acc_median": None,
    "acc_std": None,
    "acc_min": None,
    "acc_p10": None,
    "acc_p90": None,
    "acc_max": None,
    "macro_f1_mean": None,
    "macro_f1_median": None,
    "macro_f1_std": None,
    "cross_err_mean": None,
    "cross_err_median": None,
    "cross_err_std": None,
}
_winner_combo_stats_df = pl.DataFrame(
    schema={
        "winner_combo_key": pl.Utf8,
        "wins": pl.Int32,
        "winner_share": pl.Float64,
        "winner_accuracy_mean": pl.Float64,
        "winner_accuracy_median": pl.Float64,
        "winner_accuracy_min": pl.Float64,
        "winner_accuracy_p90": pl.Float64,
        "winner_accuracy_max": pl.Float64,
        "winner_macro_f1_mean": pl.Float64,
        "winner_macro_f1_median": pl.Float64,
        "winner_cross_direction_error_mean": pl.Float64,
        "winner_cross_direction_error_median": pl.Float64,
        "acc_ge_090_share": pl.Float64,
        "acc_ge_080_share": pl.Float64,
        "acc_ge_070_share": pl.Float64,
        "acc_ge_060_share": pl.Float64,
        "acc_ge_050_share": pl.Float64,
    }
)
_winner_transition_counts_df = pl.DataFrame(
    schema={
        "prev_winner_combo_key": pl.Utf8,
        "winner_combo_key": pl.Utf8,
        "len": pl.Int32,
    }
)
_switch_rate = 0.0
_top_steps_df = pl.DataFrame(
    schema={
        "step_idx": pl.UInt32,
        "pred_batch": pl.Int32,
        "winner_combo_key": pl.Utf8,
        "winner_accuracy": pl.Float64,
        "winner_macro_f1": pl.Float64,
        "winner_cross_direction_error": pl.Float64,
    }
)
_bottom_steps_df = _top_steps_df.clone()

if _rows_extracted:
    _winner_metric_summary = winners_1m_target_4class_df.select(
        [
            pl.col("winner_accuracy").mean().alias("acc_mean"),
            pl.col("winner_accuracy").median().alias("acc_median"),
            pl.col("winner_accuracy").std().alias("acc_std"),
            pl.col("winner_accuracy").min().alias("acc_min"),
            pl.col("winner_accuracy").quantile(0.10).alias("acc_p10"),
            pl.col("winner_accuracy").quantile(0.90).alias("acc_p90"),
            pl.col("winner_accuracy").max().alias("acc_max"),
            pl.col("winner_macro_f1").mean().alias("macro_f1_mean"),
            pl.col("winner_macro_f1").median().alias("macro_f1_median"),
            pl.col("winner_macro_f1").std().alias("macro_f1_std"),
            pl.col("winner_cross_direction_error").mean().alias("cross_err_mean"),
            pl.col("winner_cross_direction_error").median().alias("cross_err_median"),
            pl.col("winner_cross_direction_error").std().alias("cross_err_std"),
        ]
    ).to_dicts()[0]

    _winner_combo_stats_df = (
        winners_1m_target_4class_df.drop_nulls("winner_combo_key")
        .group_by("winner_combo_key")
        .agg(
            [
                pl.len().alias("wins"),
                pl.col("winner_accuracy").mean().alias("winner_accuracy_mean"),
                pl.col("winner_accuracy").median().alias("winner_accuracy_median"),
                pl.col("winner_accuracy").min().alias("winner_accuracy_min"),
                pl.col("winner_accuracy").quantile(0.90).alias("winner_accuracy_p90"),
                pl.col("winner_accuracy").max().alias("winner_accuracy_max"),
                pl.col("winner_macro_f1").mean().alias("winner_macro_f1_mean"),
                pl.col("winner_macro_f1").median().alias("winner_macro_f1_median"),
                pl.col("winner_cross_direction_error")
                .mean()
                .alias("winner_cross_direction_error_mean"),
                pl.col("winner_cross_direction_error")
                .median()
                .alias("winner_cross_direction_error_median"),
                (pl.col("winner_accuracy") >= 0.90).mean().alias("acc_ge_090_share"),
                (pl.col("winner_accuracy") >= 0.80).mean().alias("acc_ge_080_share"),
                (pl.col("winner_accuracy") >= 0.70).mean().alias("acc_ge_070_share"),
                (pl.col("winner_accuracy") >= 0.60).mean().alias("acc_ge_060_share"),
                (pl.col("winner_accuracy") >= 0.50).mean().alias("acc_ge_050_share"),
            ]
        )
        .with_columns(
            (pl.col("wins") / pl.lit(float(_rows_extracted))).alias("winner_share")
        )
        .sort(["wins", "winner_accuracy_mean"], descending=[True, True])
        .select(
            [
                "winner_combo_key",
                "wins",
                "winner_share",
                "winner_accuracy_mean",
                "winner_accuracy_median",
                "winner_accuracy_min",
                "winner_accuracy_p90",
                "winner_accuracy_max",
                "winner_macro_f1_mean",
                "winner_macro_f1_median",
                "winner_cross_direction_error_mean",
                "winner_cross_direction_error_median",
                "acc_ge_090_share",
                "acc_ge_080_share",
                "acc_ge_070_share",
                "acc_ge_060_share",
                "acc_ge_050_share",
            ]
        )
    )

    _winner_transitions_df = (
        winners_1m_target_4class_df.select(
            ["step_idx", "pred_batch", "winner_combo_key"]
        )
        .drop_nulls("winner_combo_key")
        .with_columns(
            [
                pl.col("winner_combo_key").shift(1).alias("prev_winner_combo_key"),
                pl.col("pred_batch").shift(1).alias("prev_pred_batch"),
            ]
        )
        .drop_nulls("prev_winner_combo_key")
        .with_columns(
            (pl.col("winner_combo_key") != pl.col("prev_winner_combo_key")).alias(
                "switched"
            )
        )
    )
    _switch_rate = (
        float(_winner_transitions_df["switched"].mean())
        if not _winner_transitions_df.is_empty()
        else 0.0
    )
    _winner_transition_counts_df = (
        _winner_transitions_df.group_by(["prev_winner_combo_key", "winner_combo_key"])
        .len()
        .sort("len", descending=True)
    )

    _top_steps_df = (
        winners_1m_target_4class_df.sort(
            ["winner_accuracy", "winner_macro_f1"], descending=[True, True]
        )
        .head(20)
        .select(
            [
                "step_idx",
                "pred_batch",
                "winner_combo_key",
                "winner_accuracy",
                "winner_macro_f1",
                "winner_cross_direction_error",
            ]
        )
    )
    _bottom_steps_df = (
        winners_1m_target_4class_df.sort(
            ["winner_accuracy", "winner_macro_f1"], descending=[False, False]
        )
        .head(20)
        .select(
            [
                "step_idx",
                "pred_batch",
                "winner_combo_key",
                "winner_accuracy",
                "winner_macro_f1",
                "winner_cross_direction_error",
            ]
        )
    )

print("\nStage-1 winners extraction")
print(f"  Unit: {STAGE1_WINNERS_UNIT}")
print(f"  Discovered batch dirs: {_discovered_steps}")
print(f"  Rows extracted: {_rows_extracted}")
print(f"  Pred batch range: {_min_pred_batch} -> {_max_pred_batch}")
print(f"  Missing winner combo key rows: {_missing_winner_key}")
print(f"  Unique winner combos: {_unique_winner_combo_count}")
print(
    f"  Winners computed from pred payload: {_winners_from_payload}/{_rows_extracted}"
)
print(
    "  Unique actions tested per step (min/median/mean/max): "
    f"{_actions_tested_stats['min']}/{_actions_tested_stats['median']:.1f}/"
    f"{_actions_tested_stats['mean']:.2f}/{_actions_tested_stats['max']}"
)
for _thr in _share_thresholds:
    print(
        f"  Share with winner_accuracy >= {_thr:.2f}: {_share_by_threshold[_thr]:.4f}"
    )
if _rows_extracted:
    print("  Winner metric summary:")
    print(
        "    accuracy mean/median/std/min/p10/p90/max: "
        f"{float(_winner_metric_summary['acc_mean']):.4f}/"
        f"{float(_winner_metric_summary['acc_median']):.4f}/"
        f"{float(_winner_metric_summary['acc_std']):.4f}/"
        f"{float(_winner_metric_summary['acc_min']):.4f}/"
        f"{float(_winner_metric_summary['acc_p10']):.4f}/"
        f"{float(_winner_metric_summary['acc_p90']):.4f}/"
        f"{float(_winner_metric_summary['acc_max']):.4f}"
    )
    print(
        "    macro_f1 mean/median/std: "
        f"{float(_winner_metric_summary['macro_f1_mean']):.4f}/"
        f"{float(_winner_metric_summary['macro_f1_median']):.4f}/"
        f"{float(_winner_metric_summary['macro_f1_std']):.4f}"
    )
    print(
        "    cross_direction_error mean/median/std: "
        f"{float(_winner_metric_summary['cross_err_mean']):.4f}/"
        f"{float(_winner_metric_summary['cross_err_median']):.4f}/"
        f"{float(_winner_metric_summary['cross_err_std']):.4f}"
    )
if _winners_missing_summary:
    print(
        "  Missing summary files: "
        f"{len(_winners_missing_summary)} (examples: {_winners_missing_summary[:10]})"
    )
else:
    print("  Missing summary files: 0")

if _rows_extracted:
    print("\nWinner combo statistics (all winners):")
    print(_winner_combo_stats_df)
    print(f"\nWinner switch rate across steps: {_switch_rate:.4f}")
    print("\nTop winner transitions (prev -> current):")
    print(_winner_transition_counts_df.head(20))
    print("\nTop 20 steps by winner accuracy:")
    print(_top_steps_df)
    print("\nBottom 20 steps by winner accuracy:")
    print(_bottom_steps_df)

# Save artifacts
winners_1m_target_4class_path_parquet = _winners_unit_dir / "winners_all_steps.parquet"
winners_1m_target_4class_path_csv = _winners_unit_dir / "winners_all_steps.csv"
winners_1m_target_4class_combo_metrics_path_parquet = (
    _winners_unit_dir / "winners_all_steps_combo_metrics_all_tested.parquet"
)
winners_1m_target_4class_combo_metrics_path_csv = (
    _winners_unit_dir / "winners_all_steps_combo_metrics_all_tested.csv"
)
winners_1m_target_4class_combo_stats_path_parquet = (
    _winners_unit_dir / "winners_combo_stats.parquet"
)
winners_1m_target_4class_combo_stats_path_csv = (
    _winners_unit_dir / "winners_combo_stats.csv"
)
winners_1m_target_4class_transition_stats_path_parquet = (
    _winners_unit_dir / "winners_transition_stats.parquet"
)
winners_1m_target_4class_transition_stats_path_csv = (
    _winners_unit_dir / "winners_transition_stats.csv"
)
winners_1m_target_4class_top_steps_path_parquet = (
    _winners_unit_dir / "winners_top_steps.parquet"
)
winners_1m_target_4class_top_steps_path_csv = (
    _winners_unit_dir / "winners_top_steps.csv"
)
winners_1m_target_4class_bottom_steps_path_parquet = (
    _winners_unit_dir / "winners_bottom_steps.parquet"
)
winners_1m_target_4class_bottom_steps_path_csv = (
    _winners_unit_dir / "winners_bottom_steps.csv"
)
winners_1m_target_4class_summary_path_json = _winners_unit_dir / "winners_summary.json"
winners_1m_target_4class_df.write_parquet(winners_1m_target_4class_path_parquet)
winners_1m_target_4class_df.write_csv(winners_1m_target_4class_path_csv)
_combo_metrics_df = (
    pl.DataFrame(_step_combo_metric_rows).sort(
        ["pred_batch", "action_key", "accuracy"], descending=[False, False, True]
    )
    if _step_combo_metric_rows
    else pl.DataFrame(
        schema={
            "pred_batch": pl.Int32,
            "action_key": pl.Utf8,
            "combo_id": pl.Int32,
            "accuracy": pl.Float64,
            "macro_f1": pl.Float64,
            "cross_direction_error": pl.Float64,
            "pred_rows": pl.Int32,
            "snapshot": pl.Utf8,
            "summary_path": pl.Utf8,
        }
    )
)
_combo_metrics_df.write_parquet(winners_1m_target_4class_combo_metrics_path_parquet)
_combo_metrics_df.write_csv(winners_1m_target_4class_combo_metrics_path_csv)
_winner_combo_stats_df.write_parquet(winners_1m_target_4class_combo_stats_path_parquet)
_winner_combo_stats_df.write_csv(winners_1m_target_4class_combo_stats_path_csv)
_winner_transition_counts_df.write_parquet(
    winners_1m_target_4class_transition_stats_path_parquet
)
_winner_transition_counts_df.write_csv(
    winners_1m_target_4class_transition_stats_path_csv
)
_top_steps_df.write_parquet(winners_1m_target_4class_top_steps_path_parquet)
_top_steps_df.write_csv(winners_1m_target_4class_top_steps_path_csv)
_bottom_steps_df.write_parquet(winners_1m_target_4class_bottom_steps_path_parquet)
_bottom_steps_df.write_csv(winners_1m_target_4class_bottom_steps_path_csv)
with open(winners_1m_target_4class_summary_path_json, "w") as f:
    json.dump(
        {
            "unit": STAGE1_WINNERS_UNIT,
            "run_id": STAGE1_RUN_ID,
            "discovered_batch_dirs": _discovered_steps,
            "rows_extracted": _rows_extracted,
            "pred_batch_min": _min_pred_batch,
            "pred_batch_max": _max_pred_batch,
            "missing_winner_combo_key_rows": _missing_winner_key,
            "unique_winner_combo_count": _unique_winner_combo_count,
            "winners_computed_from_pred_payload": _winners_from_payload,
            "winner_selection_scope": "all_tested_combos_current_plus_archive",
            "combo_metrics_rows": int(len(_combo_metrics_df)),
            "combo_metrics_unique_action_keys": (
                int(_combo_metrics_df["action_key"].drop_nulls().n_unique())
                if len(_combo_metrics_df)
                else 0
            ),
            "unique_actions_tested_per_step_min": int(_actions_tested_stats["min"]),
            "unique_actions_tested_per_step_median": float(
                _actions_tested_stats["median"]
            ),
            "unique_actions_tested_per_step_mean": float(_actions_tested_stats["mean"]),
            "unique_actions_tested_per_step_max": int(_actions_tested_stats["max"]),
            "share_winner_accuracy_ge_070": _share_ge_070,
            "share_winner_accuracy_ge_090": float(_share_by_threshold[0.90]),
            "share_winner_accuracy_ge_080": float(_share_by_threshold[0.80]),
            "share_winner_accuracy_ge_060": float(_share_by_threshold[0.60]),
            "share_winner_accuracy_ge_050": float(_share_by_threshold[0.50]),
            "share_winner_accuracy_by_threshold": {
                f"{k:.2f}": float(v) for k, v in _share_by_threshold.items()
            },
            "winner_accuracy_stats": {
                "mean": (
                    float(_winner_metric_summary["acc_mean"])
                    if _winner_metric_summary["acc_mean"] is not None
                    else None
                ),
                "median": (
                    float(_winner_metric_summary["acc_median"])
                    if _winner_metric_summary["acc_median"] is not None
                    else None
                ),
                "std": (
                    float(_winner_metric_summary["acc_std"])
                    if _winner_metric_summary["acc_std"] is not None
                    else None
                ),
                "min": (
                    float(_winner_metric_summary["acc_min"])
                    if _winner_metric_summary["acc_min"] is not None
                    else None
                ),
                "p10": (
                    float(_winner_metric_summary["acc_p10"])
                    if _winner_metric_summary["acc_p10"] is not None
                    else None
                ),
                "p90": (
                    float(_winner_metric_summary["acc_p90"])
                    if _winner_metric_summary["acc_p90"] is not None
                    else None
                ),
                "max": (
                    float(_winner_metric_summary["acc_max"])
                    if _winner_metric_summary["acc_max"] is not None
                    else None
                ),
            },
            "winner_macro_f1_stats": {
                "mean": (
                    float(_winner_metric_summary["macro_f1_mean"])
                    if _winner_metric_summary["macro_f1_mean"] is not None
                    else None
                ),
                "median": (
                    float(_winner_metric_summary["macro_f1_median"])
                    if _winner_metric_summary["macro_f1_median"] is not None
                    else None
                ),
                "std": (
                    float(_winner_metric_summary["macro_f1_std"])
                    if _winner_metric_summary["macro_f1_std"] is not None
                    else None
                ),
            },
            "winner_cross_direction_error_stats": {
                "mean": (
                    float(_winner_metric_summary["cross_err_mean"])
                    if _winner_metric_summary["cross_err_mean"] is not None
                    else None
                ),
                "median": (
                    float(_winner_metric_summary["cross_err_median"])
                    if _winner_metric_summary["cross_err_median"] is not None
                    else None
                ),
                "std": (
                    float(_winner_metric_summary["cross_err_std"])
                    if _winner_metric_summary["cross_err_std"] is not None
                    else None
                ),
            },
            "winner_switch_rate": float(_switch_rate),
            "winners_all_steps_parquet": str(winners_1m_target_4class_path_parquet),
            "winners_all_steps_csv": str(winners_1m_target_4class_path_csv),
            "combo_metrics_all_tested_parquet": str(
                winners_1m_target_4class_combo_metrics_path_parquet
            ),
            "combo_metrics_all_tested_csv": str(
                winners_1m_target_4class_combo_metrics_path_csv
            ),
            "combo_stats_parquet": str(
                winners_1m_target_4class_combo_stats_path_parquet
            ),
            "combo_stats_csv": str(winners_1m_target_4class_combo_stats_path_csv),
            "transition_stats_parquet": str(
                winners_1m_target_4class_transition_stats_path_parquet
            ),
            "transition_stats_csv": str(
                winners_1m_target_4class_transition_stats_path_csv
            ),
            "top_steps_parquet": str(winners_1m_target_4class_top_steps_path_parquet),
            "top_steps_csv": str(winners_1m_target_4class_top_steps_path_csv),
            "bottom_steps_parquet": str(
                winners_1m_target_4class_bottom_steps_path_parquet
            ),
            "bottom_steps_csv": str(winners_1m_target_4class_bottom_steps_path_csv),
            "missing_summary_count": int(len(_winners_missing_summary)),
            "missing_summary_examples": _winners_missing_summary[:10],
        },
        f,
        indent=2,
    )

# Validation checks
if _rows_extracted != _discovered_steps:
    raise AssertionError(
        f"Rows extracted ({_rows_extracted}) != discovered batch dirs ({_discovered_steps}). "
        "Some step summaries are missing."
    )
if _rows_extracted != int(STAGE1_N_STEPS):
    raise AssertionError(f"Expected {int(STAGE1_N_STEPS)} rows, got {_rows_extracted}.")
if _rows_extracted:
    if int(winners_1m_target_4class_df["pred_batch"].n_unique()) != _rows_extracted:
        raise AssertionError("pred_batch is not unique in winners table.")
    _pred = winners_1m_target_4class_df["pred_batch"].to_list()
    if any(_pred[i] >= _pred[i + 1] for i in range(len(_pred) - 1)):
        raise AssertionError("pred_batch is not strictly increasing after sort.")
    _saved_parquet = pl.read_parquet(winners_1m_target_4class_path_parquet)
    _saved_csv = pl.read_csv(winners_1m_target_4class_path_csv)
    if len(_saved_parquet) != _rows_extracted or len(_saved_csv) != _rows_extracted:
        raise AssertionError("Saved parquet/csv row count mismatch.")
    _saved_combo_metrics = pl.read_parquet(
        winners_1m_target_4class_combo_metrics_path_parquet
    )
    if len(_saved_combo_metrics) != len(_combo_metrics_df):
        raise AssertionError("Saved combo metrics parquet row count mismatch.")
    _saved_combo_stats = pl.read_parquet(
        winners_1m_target_4class_combo_stats_path_parquet
    )
    if len(_saved_combo_stats) != len(_winner_combo_stats_df):
        raise AssertionError("Saved combo stats parquet row count mismatch.")
    _saved_transition_stats = pl.read_parquet(
        winners_1m_target_4class_transition_stats_path_parquet
    )
    if len(_saved_transition_stats) != len(_winner_transition_counts_df):
        raise AssertionError("Saved transition stats parquet row count mismatch.")
    _saved_top_steps = pl.read_parquet(winners_1m_target_4class_top_steps_path_parquet)
    if len(_saved_top_steps) != len(_top_steps_df):
        raise AssertionError("Saved top steps parquet row count mismatch.")
    _saved_bottom_steps = pl.read_parquet(
        winners_1m_target_4class_bottom_steps_path_parquet
    )
    if len(_saved_bottom_steps) != len(_bottom_steps_df):
        raise AssertionError("Saved bottom steps parquet row count mismatch.")

print("\nSaved:")
print(f"  {winners_1m_target_4class_path_parquet}")
print(f"  {winners_1m_target_4class_path_csv}")
print(f"  {winners_1m_target_4class_combo_metrics_path_parquet}")
print(f"  {winners_1m_target_4class_combo_metrics_path_csv}")
print(f"  {winners_1m_target_4class_combo_stats_path_parquet}")
print(f"  {winners_1m_target_4class_combo_stats_path_csv}")
print(f"  {winners_1m_target_4class_transition_stats_path_parquet}")
print(f"  {winners_1m_target_4class_transition_stats_path_csv}")
print(f"  {winners_1m_target_4class_top_steps_path_parquet}")
print(f"  {winners_1m_target_4class_top_steps_path_csv}")
print(f"  {winners_1m_target_4class_bottom_steps_path_parquet}")
print(f"  {winners_1m_target_4class_bottom_steps_path_csv}")
print(f"  {winners_1m_target_4class_summary_path_json}")


# %%
# ============================================================================
# CELL 14B: STAGE-1 WINNER-12 COVERAGE AUDIT + BACKFILL (1m/target_4class)
# ============================================================================

import json
import sys
import time
from collections import Counter
from dataclasses import fields
from datetime import datetime
from pathlib import Path

import polars as pl

# Standalone-safe bootstrap (so Cell 14B can run without earlier cells).
if "PROJECT_ROOT" not in dir():
    PROJECT_ROOT = Path("/media/przem/linux_data/RiskYieldMM (Copy)")
else:
    PROJECT_ROOT = Path(PROJECT_ROOT)

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.htf_backtest.catboost.stage1_optimizer import evaluate_stage1_grid
from scripts.htf_backtest.catboost.stage1_runner import (
    _stage1_get_step_winner_metrics,
    _stage1_update_step_summary_quality,
)
from scripts.htf_backtest.catboost.tf_1m import (
    Config1m,
    FeatureSpace1m,
    ModelSpace1m,
    Optimizer1m,
    WindowSpace1m,
)

STAGE1_BACKFILL_RUN_ID = "stage1_catboost_live"
STAGE1_BACKFILL_UNIT = "1m/target_4class"
STAGE1_BACKFILL_WINNER_SET_MODE = "from_winners_table"
STAGE1_BACKFILL_EXPECTED_WINNER_COUNT = 12
STAGE1_BACKFILL_COVERAGE_SCOPE = (
    "current+archive"  # current | archive | current+archive
)
STAGE1_BACKFILL_APPLY = True
STAGE1_BACKFILL_CANDIDATE_SOURCE = "winner12_backfill"
STAGE1_BACKFILL_DISCOVERED_FROM = "cell14b_winner12_missing_coverage"

if STAGE1_BACKFILL_COVERAGE_SCOPE not in {"current", "archive", "current+archive"}:
    raise ValueError(
        "STAGE1_BACKFILL_COVERAGE_SCOPE must be one of: current, archive, current+archive"
    )

_b_model = "catboost"
_b_tf, _b_target = STAGE1_BACKFILL_UNIT.split("/", 1)
_b_unit_dir = (
    PROJECT_ROOT
    / "data"
    / "htf_backtest_results"
    / STAGE1_BACKFILL_RUN_ID
    / _b_model
    / _b_tf
    / _b_target
)
if not _b_unit_dir.exists():
    raise FileNotFoundError(f"Unit directory not found: {_b_unit_dir}")

_b_winners_path = _b_unit_dir / "winners_all_steps.parquet"
if not _b_winners_path.exists():
    raise FileNotFoundError(
        f"winners_all_steps.parquet not found. Run Cell 14A first: {_b_winners_path}"
    )


def _action_key_to_triplet(action_key: str) -> tuple[int, int, int] | None:
    s = str(action_key or "").strip()
    if not s:
        return None
    try:
        if not (s.startswith("f") and "_v" in s and "_t" in s):
            return None
        f_part, rest = s[1:].split("_v", 1)
        v_part, t_part = rest.split("_t", 1)
        return int(f_part), int(v_part), int(t_part)
    except Exception:
        return None


def _dataclass_from_snapshot(cls, raw: dict):
    allowed = {f.name for f in fields(cls)}
    src = dict(raw or {})
    kwargs = {k: src[k] for k in src.keys() if k in allowed}

    if "project_root" in kwargs and kwargs["project_root"] is not None:
        kwargs["project_root"] = Path(str(kwargs["project_root"]))
    if "class_names" in kwargs and isinstance(kwargs["class_names"], list):
        kwargs["class_names"] = tuple(kwargs["class_names"])
    if "class_weight_choices" in kwargs and isinstance(
        kwargs["class_weight_choices"], list
    ):
        kwargs["class_weight_choices"] = tuple(
            str(v) for v in kwargs["class_weight_choices"]
        )
    if "cb_base_params" in kwargs and kwargs["cb_base_params"] is not None:
        kwargs["cb_base_params"] = dict(kwargs["cb_base_params"])
    return cls(**kwargs)


def _iter_snapshot_paths(step_stage1_dir: Path, scope: str):
    include_current = scope in {"current", "current+archive"}
    include_archive = scope in {"archive", "current+archive"}

    if include_current:
        combo_path = step_stage1_dir / "stage1_combo_index.parquet"
        pred_path = step_stage1_dir / "stage1_pred_batch_predictions.parquet"
        if combo_path.exists() and pred_path.exists():
            yield "current", combo_path, pred_path

    if include_archive:
        archive_root = step_stage1_dir / "archive_legacy"
        if archive_root.exists():
            for snap_dir in sorted([p for p in archive_root.iterdir() if p.is_dir()]):
                combo_path = snap_dir / "stage1_combo_index.parquet"
                pred_path = snap_dir / "stage1_pred_batch_predictions.parquet"
                if combo_path.exists() and pred_path.exists():
                    yield f"archive:{snap_dir.name}", combo_path, pred_path


def _present_actions_from_snapshot(combo_path: Path, pred_path: Path) -> set[str]:
    try:
        combo_df = pl.read_parquet(combo_path)
        pred_df = pl.read_parquet(pred_path)
    except Exception:
        return set()
    if combo_df.is_empty() or pred_df.is_empty():
        return set()
    if "scope" in pred_df.columns:
        pred_df = pred_df.filter(pl.col("scope") == "pred_batch")
    if pred_df.is_empty():
        return set()
    if not {"combo_id", "action_key"}.issubset(set(combo_df.columns)):
        return set()
    if "combo_id" not in pred_df.columns:
        return set()

    combo_map = (
        combo_df.select(["combo_id", "action_key"])
        .with_columns(
            [
                pl.col("combo_id").cast(pl.Int64),
                pl.col("action_key").cast(pl.Utf8),
            ]
        )
        .drop_nulls("action_key")
        .unique(subset=["combo_id"], keep="first")
    )
    pred_combo_ids = (
        pred_df.select("combo_id")
        .with_columns(pl.col("combo_id").cast(pl.Int64))
        .unique()
    )
    joined = pred_combo_ids.join(combo_map, on="combo_id", how="inner")
    return {
        str(v) for v in joined["action_key"].to_list() if v is not None and str(v) != ""
    }


def _scan_winner12_coverage(
    *,
    unit_dir: Path,
    required_action_keys: list[str],
    scope: str,
) -> tuple[pl.DataFrame, pl.DataFrame]:
    required_sorted = sorted({str(k) for k in required_action_keys if str(k)})
    required_set = set(required_sorted)
    coverage_rows = []
    missing_rows = []

    batch_dirs = sorted([p for p in unit_dir.glob("batch_*") if p.is_dir()])
    for batch_dir in batch_dirs:
        try:
            pred_batch = int(batch_dir.name.split("_")[1])
        except Exception:
            continue
        step_stage1_dir = batch_dir / "stage1"
        present = set()
        snapshots_seen = 0
        for _, combo_path, pred_path in _iter_snapshot_paths(step_stage1_dir, scope):
            snapshots_seen += 1
            present |= _present_actions_from_snapshot(combo_path, pred_path)
        present_required = sorted(required_set & present)
        missing = sorted(required_set - set(present_required))

        coverage_rows.append(
            {
                "pred_batch": int(pred_batch),
                "required_count": int(len(required_sorted)),
                "present_count": int(len(present_required)),
                "missing_count": int(len(missing)),
                "missing_action_keys": json.dumps(missing),
                "snapshots_seen": int(snapshots_seen),
            }
        )
        for action_key in missing:
            missing_rows.append(
                {
                    "pred_batch": int(pred_batch),
                    "action_key": str(action_key),
                }
            )

    coverage_df = (
        pl.DataFrame(coverage_rows)
        if coverage_rows
        else pl.DataFrame(
            schema={
                "pred_batch": pl.Int32,
                "required_count": pl.Int32,
                "present_count": pl.Int32,
                "missing_count": pl.Int32,
                "missing_action_keys": pl.Utf8,
                "snapshots_seen": pl.Int32,
            }
        )
    )
    if not coverage_df.is_empty():
        coverage_df = (
            coverage_df.sort("pred_batch")
            .with_row_index(name="step_idx", offset=1)
            .select(
                [
                    "pred_batch",
                    "step_idx",
                    "required_count",
                    "present_count",
                    "missing_count",
                    "missing_action_keys",
                    "snapshots_seen",
                ]
            )
        )

    missing_df = (
        pl.DataFrame(missing_rows)
        if missing_rows
        else pl.DataFrame(
            schema={
                "pred_batch": pl.Int32,
                "action_key": pl.Utf8,
            }
        )
    )
    if not missing_df.is_empty():
        missing_df = missing_df.sort(["pred_batch", "action_key"])
    return coverage_df, missing_df


# Resolve winner-12 action keys from winners table.
_b_winners_df = pl.read_parquet(_b_winners_path)
if STAGE1_BACKFILL_WINNER_SET_MODE != "from_winners_table":
    raise ValueError(
        "Only STAGE1_BACKFILL_WINNER_SET_MODE='from_winners_table' is supported in Cell 14B."
    )
_b_action_keys = sorted(
    {
        str(v)
        for v in _b_winners_df["winner_combo_key"].drop_nulls().to_list()
        if v is not None and str(v) != ""
    }
)
if len(_b_action_keys) != int(STAGE1_BACKFILL_EXPECTED_WINNER_COUNT):
    raise AssertionError(
        "Winner combo count mismatch: "
        f"expected={int(STAGE1_BACKFILL_EXPECTED_WINNER_COUNT)}, "
        f"found={len(_b_action_keys)}"
    )
_b_triplets = {}
for _k in _b_action_keys:
    tri = _action_key_to_triplet(_k)
    if tri is None:
        raise ValueError(f"Invalid action_key format in winner set: {_k}")
    _b_triplets[_k] = tri

_b_ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
_b_artifact_dir = _b_unit_dir / "winner12_backfill" / f"run_{_b_ts}"
_b_artifact_dir.mkdir(parents=True, exist_ok=True)

# 1) Coverage before
coverage_before_df, missing_before_df = _scan_winner12_coverage(
    unit_dir=_b_unit_dir,
    required_action_keys=_b_action_keys,
    scope=STAGE1_BACKFILL_COVERAGE_SCOPE,
)

before_full12_steps = (
    int((coverage_before_df["missing_count"] == 0).sum())
    if not coverage_before_df.is_empty()
    else 0
)
before_missing_steps = (
    int((coverage_before_df["missing_count"] > 0).sum())
    if not coverage_before_df.is_empty()
    else 0
)
before_missing_pairs = int(len(missing_before_df))

print("\nStage1 Winner-12 Coverage Audit (Before)")
print(f"  Run ID: {STAGE1_BACKFILL_RUN_ID}")
print(f"  Unit: {STAGE1_BACKFILL_UNIT}")
print(f"  Coverage scope: {STAGE1_BACKFILL_COVERAGE_SCOPE}")
print(f"  Winner combo count: {len(_b_action_keys)}")
print(f"  Steps discovered: {len(coverage_before_df)}")
print(f"  Steps with full winner-12 coverage: {before_full12_steps}")
print(f"  Steps missing any winner combo: {before_missing_steps}")
print(f"  Missing step/combo pairs: {before_missing_pairs}")

coverage_before_path_parquet = _b_artifact_dir / "coverage_before.parquet"
coverage_before_path_csv = _b_artifact_dir / "coverage_before.csv"
missing_before_path_parquet = _b_artifact_dir / "missing_pairs_before.parquet"
missing_before_path_csv = _b_artifact_dir / "missing_pairs_before.csv"
coverage_before_df.write_parquet(coverage_before_path_parquet)
coverage_before_df.write_csv(coverage_before_path_csv)
missing_before_df.write_parquet(missing_before_path_parquet)
missing_before_df.write_csv(missing_before_path_csv)

backfill_step_rows = []
backfill_t0 = time.perf_counter()

# 2) Backfill execution
if STAGE1_BACKFILL_APPLY and not missing_before_df.is_empty():
    missing_by_step = (
        missing_before_df.group_by("pred_batch")
        .agg(pl.col("action_key").sort().alias("missing_action_keys"))
        .sort("pred_batch")
    )
    total_steps_to_run = int(len(missing_by_step))
    print("\nStage1 Winner-12 Backfill Execution")
    for i, row in enumerate(missing_by_step.iter_rows(named=True), start=1):
        pred_batch = int(row["pred_batch"])
        train_end = int(pred_batch - 1)
        missing_action_keys = [
            str(v) for v in list(row["missing_action_keys"] or []) if str(v)
        ]
        step_stage1_dir = _b_unit_dir / f"batch_{int(pred_batch):04d}" / "stage1"
        step_summary_path = step_stage1_dir / "stage1_step_summary.json"
        step_snapshot_path = step_stage1_dir / "stage1_config_snapshot.json"

        print(
            f"STEP {i}/{total_steps_to_run} pred_batch={pred_batch} train_end={train_end} "
            f"missing_combos={missing_action_keys}"
        )
        if not step_snapshot_path.exists():
            err = f"missing config snapshot: {step_snapshot_path}"
            print(f"  ERROR: {err}")
            backfill_step_rows.append(
                {
                    "pred_batch": int(pred_batch),
                    "train_end": int(train_end),
                    "status": "error",
                    "error": err,
                    "missing_action_keys": json.dumps(missing_action_keys),
                    "combos_requested": int(len(missing_action_keys)),
                    "combos_evaluated": 0,
                    "combo_count_new_this_run": 0,
                    "winner_before_key": None,
                    "winner_before_accuracy": None,
                    "winner_after_key": None,
                    "winner_after_accuracy": None,
                    "quality_pass_after": None,
                    "runtime_s": None,
                }
            )
            continue

        with open(step_snapshot_path) as f:
            snapshot = json.load(f)
        cfg = _dataclass_from_snapshot(Config1m, snapshot.get("config", {}))
        win = _dataclass_from_snapshot(WindowSpace1m, snapshot.get("window_space", {}))
        feat = _dataclass_from_snapshot(
            FeatureSpace1m, snapshot.get("feature_space", {})
        )
        model = _dataclass_from_snapshot(ModelSpace1m, snapshot.get("model_space", {}))

        optimizer = Optimizer1m(
            config=cfg, window_space=win, feature_space=feat, model_space=model
        )
        step_optimizer = optimizer.create_step_optimizer()

        combo_override = []
        for action_key in missing_action_keys:
            tri = _b_triplets.get(action_key)
            if tri is None:
                continue
            combo_override.append(
                {
                    "fold_count": int(tri[0]),
                    "val_batches_per_fold": int(tri[1]),
                    "train_batches_per_fold": int(tri[2]),
                    "action_key": str(action_key),
                }
            )
        if not combo_override:
            print("  ERROR: no valid missing combos resolved to triplets")
            backfill_step_rows.append(
                {
                    "pred_batch": int(pred_batch),
                    "train_end": int(train_end),
                    "status": "error",
                    "error": "no_valid_missing_combos",
                    "missing_action_keys": json.dumps(missing_action_keys),
                    "combos_requested": int(len(missing_action_keys)),
                    "combos_evaluated": 0,
                    "combo_count_new_this_run": 0,
                    "winner_before_key": None,
                    "winner_before_accuracy": None,
                    "winner_after_key": None,
                    "winner_after_accuracy": None,
                    "quality_pass_after": None,
                    "runtime_s": None,
                }
            )
            continue

        winner_before = _stage1_get_step_winner_metrics(
            stage1_dir=step_stage1_dir,
            n_classes=int(cfg.n_classes),
            class_names=list(cfg.class_names),
        )
        winner_before_key = (
            str(winner_before.get("action_key")) if winner_before else None
        )
        winner_before_acc = (
            float(winner_before.get("accuracy"))
            if winner_before and winner_before.get("accuracy") is not None
            else None
        )

        print("  Running evaluate_stage1_grid append_mode=True")
        t0 = time.perf_counter()
        try:
            eval_result = evaluate_stage1_grid(
                step_optimizer=step_optimizer,
                train_end=int(train_end),
                pred_batch=int(pred_batch),
                step_stage1_dir=step_stage1_dir,
                combo_grid_override=combo_override,
                append_mode=True,
                candidate_source=STAGE1_BACKFILL_CANDIDATE_SOURCE,
                probe_tier=-1,
                discovered_from=STAGE1_BACKFILL_DISCOVERED_FROM,
            )
            runtime_s = float(time.perf_counter() - t0)

            winner_after = _stage1_get_step_winner_metrics(
                stage1_dir=step_stage1_dir,
                n_classes=int(cfg.n_classes),
                class_names=list(cfg.class_names),
            )
            winner_after_key = (
                str(winner_after.get("action_key")) if winner_after else None
            )
            winner_after_acc = (
                float(winner_after.get("accuracy"))
                if winner_after and winner_after.get("accuracy") is not None
                else None
            )

            existing_summary = {}
            if step_summary_path.exists():
                with open(step_summary_path) as f:
                    existing_summary = json.load(f)
            quality_threshold = float(
                existing_summary.get("quality_threshold", 0.70) or 0.70
            )
            quality_unresolved = bool(existing_summary.get("quality_unresolved", False))
            probe_exhausted = bool(existing_summary.get("probe_exhausted", False))
            if winner_after_acc is not None and winner_after_acc >= quality_threshold:
                quality_unresolved = False
                probe_exhausted = False

            updated_summary = _stage1_update_step_summary_quality(
                stage1_dir=step_stage1_dir,
                quality_threshold=quality_threshold,
                winner=winner_after,
                quality_unresolved=quality_unresolved,
                probe_exhausted=probe_exhausted,
                probe_enabled=bool(existing_summary.get("probe_enabled", False)),
                probe_tiers_run=int(existing_summary.get("probe_tiers_run", 0) or 0),
                probe_candidates_evaluated=int(
                    existing_summary.get("probe_candidates_evaluated", 0) or 0
                ),
            )
            quality_pass_after = bool(updated_summary.get("quality_pass", False))
            combo_count_new = int(
                eval_result["summary"].get("combo_count_new_this_run", 0) or 0
            )

            print(
                "  Done: "
                f"combo_count_new_this_run={combo_count_new}, "
                f"winner_before={winner_before_key}:{winner_before_acc}, "
                f"winner_after={winner_after_key}:{winner_after_acc}, "
                f"quality_pass_after={quality_pass_after}, runtime_s={runtime_s:.2f}"
            )
            backfill_step_rows.append(
                {
                    "pred_batch": int(pred_batch),
                    "train_end": int(train_end),
                    "status": "ok",
                    "error": None,
                    "missing_action_keys": json.dumps(missing_action_keys),
                    "combos_requested": int(len(missing_action_keys)),
                    "combos_evaluated": int(len(combo_override)),
                    "combo_count_new_this_run": int(combo_count_new),
                    "winner_before_key": winner_before_key,
                    "winner_before_accuracy": winner_before_acc,
                    "winner_after_key": winner_after_key,
                    "winner_after_accuracy": winner_after_acc,
                    "quality_pass_after": bool(quality_pass_after),
                    "runtime_s": float(runtime_s),
                }
            )
        except Exception as e:
            runtime_s = float(time.perf_counter() - t0)
            print(f"  ERROR: {e}")
            backfill_step_rows.append(
                {
                    "pred_batch": int(pred_batch),
                    "train_end": int(train_end),
                    "status": "error",
                    "error": str(e),
                    "missing_action_keys": json.dumps(missing_action_keys),
                    "combos_requested": int(len(missing_action_keys)),
                    "combos_evaluated": int(len(combo_override)),
                    "combo_count_new_this_run": 0,
                    "winner_before_key": winner_before_key,
                    "winner_before_accuracy": winner_before_acc,
                    "winner_after_key": None,
                    "winner_after_accuracy": None,
                    "quality_pass_after": None,
                    "runtime_s": float(runtime_s),
                }
            )
else:
    if not STAGE1_BACKFILL_APPLY:
        print("\nBackfill apply disabled (STAGE1_BACKFILL_APPLY=False).")
    else:
        print("\nNo missing pairs detected; backfill not required.")

backfill_runtime_s = float(time.perf_counter() - backfill_t0)

# 3) Coverage after
coverage_after_df, missing_after_df = _scan_winner12_coverage(
    unit_dir=_b_unit_dir,
    required_action_keys=_b_action_keys,
    scope=STAGE1_BACKFILL_COVERAGE_SCOPE,
)
after_full12_steps = (
    int((coverage_after_df["missing_count"] == 0).sum())
    if not coverage_after_df.is_empty()
    else 0
)
after_missing_steps = (
    int((coverage_after_df["missing_count"] > 0).sum())
    if not coverage_after_df.is_empty()
    else 0
)
after_missing_pairs = int(len(missing_after_df))

backfill_steps_df = (
    pl.DataFrame(backfill_step_rows)
    if backfill_step_rows
    else pl.DataFrame(
        schema={
            "pred_batch": pl.Int32,
            "train_end": pl.Int32,
            "status": pl.Utf8,
            "error": pl.Utf8,
            "missing_action_keys": pl.Utf8,
            "combos_requested": pl.Int32,
            "combos_evaluated": pl.Int32,
            "combo_count_new_this_run": pl.Int32,
            "winner_before_key": pl.Utf8,
            "winner_before_accuracy": pl.Float64,
            "winner_after_key": pl.Utf8,
            "winner_after_accuracy": pl.Float64,
            "quality_pass_after": pl.Boolean,
            "runtime_s": pl.Float64,
        }
    )
)
if not backfill_steps_df.is_empty():
    backfill_steps_df = backfill_steps_df.sort("pred_batch")

coverage_after_path_parquet = _b_artifact_dir / "coverage_after.parquet"
coverage_after_path_csv = _b_artifact_dir / "coverage_after.csv"
missing_after_path_parquet = _b_artifact_dir / "missing_pairs_after.parquet"
missing_after_path_csv = _b_artifact_dir / "missing_pairs_after.csv"
backfill_steps_path_parquet = _b_artifact_dir / "backfill_step_results.parquet"
backfill_steps_path_csv = _b_artifact_dir / "backfill_step_results.csv"
summary_path_json = _b_artifact_dir / "backfill_summary.json"

coverage_after_df.write_parquet(coverage_after_path_parquet)
coverage_after_df.write_csv(coverage_after_path_csv)
missing_after_df.write_parquet(missing_after_path_parquet)
missing_after_df.write_csv(missing_after_path_csv)
backfill_steps_df.write_parquet(backfill_steps_path_parquet)
backfill_steps_df.write_csv(backfill_steps_path_csv)

unresolved_counter = Counter()
if not missing_after_df.is_empty():
    unresolved_counter.update(
        [str(v) for v in missing_after_df["action_key"].to_list() if v is not None]
    )

summary_obj = {
    "run_id": STAGE1_BACKFILL_RUN_ID,
    "unit": STAGE1_BACKFILL_UNIT,
    "winner_set_mode": STAGE1_BACKFILL_WINNER_SET_MODE,
    "expected_winner_count": int(STAGE1_BACKFILL_EXPECTED_WINNER_COUNT),
    "winner_action_keys": list(_b_action_keys),
    "coverage_scope": STAGE1_BACKFILL_COVERAGE_SCOPE,
    "apply": bool(STAGE1_BACKFILL_APPLY),
    "candidate_source": STAGE1_BACKFILL_CANDIDATE_SOURCE,
    "discovered_from": STAGE1_BACKFILL_DISCOVERED_FROM,
    "before": {
        "steps_total": int(len(coverage_before_df)),
        "full12_steps": int(before_full12_steps),
        "missing_steps": int(before_missing_steps),
        "missing_pairs": int(before_missing_pairs),
    },
    "after": {
        "steps_total": int(len(coverage_after_df)),
        "full12_steps": int(after_full12_steps),
        "missing_steps": int(after_missing_steps),
        "missing_pairs": int(after_missing_pairs),
    },
    "backfill": {
        "steps_attempted": int(len(backfill_steps_df)),
        "steps_ok": int((backfill_steps_df["status"] == "ok").sum())
        if not backfill_steps_df.is_empty()
        else 0,
        "steps_error": int((backfill_steps_df["status"] == "error").sum())
        if not backfill_steps_df.is_empty()
        else 0,
        "runtime_s": float(backfill_runtime_s),
    },
    "unresolved_combo_counts": dict(
        sorted(unresolved_counter.items(), key=lambda kv: (-kv[1], kv[0]))
    ),
    "artifacts": {
        "coverage_before_parquet": str(coverage_before_path_parquet),
        "coverage_before_csv": str(coverage_before_path_csv),
        "missing_pairs_before_parquet": str(missing_before_path_parquet),
        "missing_pairs_before_csv": str(missing_before_path_csv),
        "backfill_step_results_parquet": str(backfill_steps_path_parquet),
        "backfill_step_results_csv": str(backfill_steps_path_csv),
        "coverage_after_parquet": str(coverage_after_path_parquet),
        "coverage_after_csv": str(coverage_after_path_csv),
        "missing_pairs_after_parquet": str(missing_after_path_parquet),
        "missing_pairs_after_csv": str(missing_after_path_csv),
    },
    "created_at": datetime.now().isoformat(),
}
with open(summary_path_json, "w") as f:
    json.dump(summary_obj, f, indent=2)

print("\nStage1 Winner-12 Coverage Audit (After)")
print(
    f"  before_full12_steps={before_full12_steps}, after_full12_steps={after_full12_steps}"
)
print(
    f"  before_missing_pairs={before_missing_pairs}, after_missing_pairs={after_missing_pairs}"
)
if unresolved_counter:
    print(
        "  unresolved_combo_keys="
        + str(dict(sorted(unresolved_counter.items(), key=lambda kv: (-kv[1], kv[0]))))
    )
else:
    print("  unresolved_combo_keys={}")

print("\nSaved:")
print(f"  {coverage_before_path_parquet}")
print(f"  {missing_before_path_parquet}")
print(f"  {backfill_steps_path_parquet}")
print(f"  {coverage_after_path_parquet}")
print(f"  {missing_after_path_parquet}")
print(f"  {summary_path_json}")


# %%
# ============================================================================
# CELL 14C: LIVE-STYLE CONSENSUS SIGNALS FROM 12 WINNER COMBOS (1m/target_4class)
# ============================================================================

import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import polars as pl

# Standalone-safe bootstrap (so Cell 14C can run independently).
if "PROJECT_ROOT" not in dir():
    PROJECT_ROOT = Path("/media/przem/linux_data/RiskYieldMM (Copy)")
else:
    PROJECT_ROOT = Path(PROJECT_ROOT)

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

STAGE1_COMBO_MATCH_RUN_ID = "stage1_catboost_live"
STAGE1_COMBO_MATCH_UNIT = "1m/target_4class"
STAGE1_COMBO_MATCH_SOURCE_SCOPE = "current+archive"
STAGE1_COMBO_MATCH_EXPECTED_WINNERS = 12
STAGE1_COMBO_MATCH_CLASS_COUNT = 4
STAGE1_COMBO_MATCH_DIRECTION_MAP = {0: "DOWN", 1: "DOWN", 2: "UP", 3: "UP"}
STAGE1_COMBO_MATCH_WINDOW_STEPS = [12, 24]
STAGE1_COMBO_MATCH_TOPK_STEPS = 25
STAGE1_COMBO_MATCH_TOPK_WINDOWS = 25
STAGE1_COMBO_MATCH_DECILES = 10
STAGE1_SIGNAL_BAD_THRESHOLD = 0.30
STAGE1_SIGNAL_GOOD_THRESHOLD = 0.70
STAGE1_SIGNAL_WEIGHTING = "normalized_max_accuracy"
STAGE1_COMBO_MATCH_HIGH_THRESHOLDS = [0.90, 0.80, 0.70, 0.60, 0.50]
STAGE1_COMBO_MATCH_LOW_THRESHOLDS = [0.50, 0.40, 0.30, 0.20, 0.10]

if STAGE1_COMBO_MATCH_SOURCE_SCOPE not in {"current", "archive", "current+archive"}:
    raise ValueError(
        "STAGE1_COMBO_MATCH_SOURCE_SCOPE must be one of: current, archive, current+archive"
    )
if STAGE1_COMBO_MATCH_CLASS_COUNT != 4:
    raise ValueError("STAGE1_COMBO_MATCH_CLASS_COUNT must be 4 for target_4class")
if sorted(STAGE1_COMBO_MATCH_DIRECTION_MAP.keys()) != [0, 1, 2, 3]:
    raise ValueError("STAGE1_COMBO_MATCH_DIRECTION_MAP must map classes 0..3")
if not STAGE1_COMBO_MATCH_WINDOW_STEPS:
    raise ValueError("STAGE1_COMBO_MATCH_WINDOW_STEPS cannot be empty")
if int(STAGE1_COMBO_MATCH_DECILES) < 2:
    raise ValueError("STAGE1_COMBO_MATCH_DECILES must be >= 2")
if STAGE1_SIGNAL_WEIGHTING != "normalized_max_accuracy":
    raise ValueError(
        "STAGE1_SIGNAL_WEIGHTING currently supports only: normalized_max_accuracy"
    )

_m_tf, _m_target = STAGE1_COMBO_MATCH_UNIT.split("/", 1)
_m_unit_dir = (
    PROJECT_ROOT
    / "data"
    / "htf_backtest_results"
    / STAGE1_COMBO_MATCH_RUN_ID
    / "catboost"
    / _m_tf
    / _m_target
)
if not _m_unit_dir.exists():
    raise FileNotFoundError(f"Unit directory not found: {_m_unit_dir}")

_m_winners_path = _m_unit_dir / "winners_all_steps.parquet"
if not _m_winners_path.exists():
    raise FileNotFoundError(
        f"winners_all_steps.parquet is required. Run Cell 14A first: {_m_winners_path}"
    )

_m_winners_df = pl.read_parquet(_m_winners_path)
if _m_winners_df.is_empty():
    raise ValueError("winners_all_steps.parquet is empty")
if "winner_accuracy" not in _m_winners_df.columns:
    raise ValueError("winners_all_steps.parquet must include winner_accuracy")

_m_winners_clean_df = _m_winners_df.drop_nulls(
    ["pred_batch", "winner_combo_key", "winner_accuracy"]
)
if _m_winners_clean_df.is_empty():
    raise ValueError("No winner rows with winner_combo_key and winner_accuracy")

_m_winner_counts_df = (
    _m_winners_clean_df.group_by("winner_combo_key")
    .len()
    .sort(["len", "winner_combo_key"], descending=[True, False])
)
_m_winner12 = [str(v) for v in _m_winner_counts_df["winner_combo_key"].to_list()]
if len(_m_winner12) != int(STAGE1_COMBO_MATCH_EXPECTED_WINNERS):
    raise AssertionError(
        f"Expected {int(STAGE1_COMBO_MATCH_EXPECTED_WINNERS)} winner combos, got {len(_m_winner12)}"
    )
_m_winner12_set = set(_m_winner12)


def _m_iter_snapshot_paths(step_stage1_dir: Path, scope: str):
    include_current = scope in {"current", "current+archive"}
    include_archive = scope in {"archive", "current+archive"}

    if include_current:
        combo_path = step_stage1_dir / "stage1_combo_index.parquet"
        pred_path = step_stage1_dir / "stage1_pred_batch_predictions.parquet"
        if combo_path.exists() and pred_path.exists():
            yield {
                "source": "current",
                "priority": 0,
                "order": 0,
                "combo_path": combo_path,
                "pred_path": pred_path,
            }

    if include_archive:
        archive_root = step_stage1_dir / "archive_legacy"
        if archive_root.exists():
            archive_dirs = sorted([p for p in archive_root.iterdir() if p.is_dir()])
            for i, sub_dir in enumerate(archive_dirs, start=1):
                combo_path = sub_dir / "stage1_combo_index.parquet"
                pred_path = sub_dir / "stage1_pred_batch_predictions.parquet"
                if combo_path.exists() and pred_path.exists():
                    yield {
                        "source": f"archive:{sub_dir.name}",
                        "priority": 1,
                        "order": i,
                        "combo_path": combo_path,
                        "pred_path": pred_path,
                    }


def _m_load_pred_rows(
    *, pred_batch: int, snap: dict, winner_keys: set[str]
) -> pl.DataFrame:
    try:
        combo_df = pl.read_parquet(snap["combo_path"])
        pred_df = pl.read_parquet(snap["pred_path"])
    except Exception:
        return pl.DataFrame()
    if combo_df.is_empty() or pred_df.is_empty():
        return pl.DataFrame()

    if "scope" in pred_df.columns:
        pred_df = pred_df.filter(pl.col("scope") == "pred_batch")
    if pred_df.is_empty():
        return pl.DataFrame()

    required_pred_cols = {
        "combo_id",
        "timestamp",
        "batch_id",
        "y_true",
        "y_pred",
        "prob_class_0",
        "prob_class_1",
        "prob_class_2",
        "prob_class_3",
    }
    if not required_pred_cols.issubset(set(pred_df.columns)):
        return pl.DataFrame()
    if not {"combo_id", "action_key"}.issubset(set(combo_df.columns)):
        return pl.DataFrame()

    combo_map = (
        combo_df.select(["combo_id", "action_key"])
        .with_columns(
            [
                pl.col("combo_id").cast(pl.Int64, strict=False),
                pl.col("action_key")
                .cast(pl.Utf8, strict=False)
                .alias("action_key_map"),
            ]
        )
        .drop("action_key")
        .unique(subset=["combo_id"], keep="first")
    )

    pred_local = pred_df.with_columns(pl.col("combo_id").cast(pl.Int64, strict=False))
    if "action_key" in pred_local.columns:
        pred_local = pred_local.with_columns(
            pl.col("action_key").cast(pl.Utf8, strict=False).alias("action_key_payload")
        )
    else:
        pred_local = pred_local.with_columns(
            pl.lit(None, dtype=pl.Utf8).alias("action_key_payload")
        )

    merged = (
        pred_local.join(combo_map, on="combo_id", how="left")
        .with_columns(
            pl.when(
                pl.col("action_key_payload").is_not_null()
                & (pl.col("action_key_payload") != "")
            )
            .then(pl.col("action_key_payload"))
            .otherwise(pl.col("action_key_map"))
            .alias("action_key")
        )
        .filter(pl.col("action_key").is_in(list(winner_keys)))
    )
    if merged.is_empty():
        return pl.DataFrame()

    out = merged.select(
        [
            pl.lit(int(pred_batch)).alias("pred_batch"),
            pl.col("timestamp"),
            pl.col("batch_id").cast(pl.Int32, strict=False),
            pl.col("combo_id").cast(pl.Int32, strict=False),
            pl.col("action_key").cast(pl.Utf8),
            pl.col("y_true").cast(pl.Int16, strict=False),
            pl.col("y_pred").cast(pl.Int16, strict=False),
            pl.col("prob_class_0").cast(pl.Float32, strict=False),
            pl.col("prob_class_1").cast(pl.Float32, strict=False),
            pl.col("prob_class_2").cast(pl.Float32, strict=False),
            pl.col("prob_class_3").cast(pl.Float32, strict=False),
            pl.lit(str(snap["source"])).alias("snapshot_source"),
            pl.lit(int(snap["priority"])).alias("snapshot_priority"),
            pl.lit(int(snap["order"])).alias("snapshot_order"),
        ]
    )
    return out


def _m_compute_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float]:
    y_true = np.asarray(y_true, dtype=np.int32)
    y_pred = np.asarray(y_pred, dtype=np.int32)
    n = int(len(y_true))
    if n <= 0:
        return {
            "accuracy": 0.0,
            "macro_recall": 0.0,
            "macro_f1": 0.0,
            "cross_direction_error": 0.0,
        }

    acc = float(np.mean(y_true == y_pred))
    recalls = []
    f1_vals = []
    for c in range(STAGE1_COMBO_MATCH_CLASS_COUNT):
        true_c = y_true == c
        pred_c = y_pred == c
        tp = int((true_c & pred_c).sum())
        fp = int((~true_c & pred_c).sum())
        support = int(true_c.sum())
        recall_c = float(tp / support) if support > 0 else 0.0
        precision_c = float(tp / (tp + fp)) if (tp + fp) > 0 else 0.0
        f1_c = (
            float(2.0 * precision_c * recall_c / (precision_c + recall_c))
            if (precision_c + recall_c) > 0
            else 0.0
        )
        recalls.append(recall_c)
        f1_vals.append(f1_c)

    true_up = y_true >= 2
    true_down = y_true <= 1
    pred_up = y_pred >= 2
    pred_down = y_pred <= 1
    cross_err = float(np.mean((true_up & pred_down) | (true_down & pred_up)))

    return {
        "accuracy": acc,
        "macro_recall": float(np.mean(recalls)),
        "macro_f1": float(np.mean(f1_vals)),
        "cross_direction_error": cross_err,
    }


def _m_share(series: pl.Series, condition: str, threshold: float) -> float:
    arr = series.to_numpy().astype(np.float64, copy=False)
    if arr.size == 0:
        return 0.0
    if condition == "ge":
        return float(np.mean(arr >= threshold))
    return float(np.mean(arr <= threshold))


def _m_entropy_norm(prob: np.ndarray, denom_log: float) -> float:
    p = np.asarray(prob, dtype=np.float64)
    mask = p > 0.0
    if not np.any(mask):
        return 0.0
    ent = -float(np.sum(p[mask] * np.log(p[mask])))
    return float(ent / denom_log) if denom_log > 0 else 0.0


def _m_rankdata_average(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=np.float64)
    n = len(x)
    order = np.argsort(x, kind="mergesort")
    ranks = np.zeros(n, dtype=np.float64)
    i = 0
    while i < n:
        j = i + 1
        while j < n and x[order[j]] == x[order[i]]:
            j += 1
        avg_rank = 0.5 * (i + j - 1) + 1.0
        ranks[order[i:j]] = avg_rank
        i = j
    return ranks


def _m_safe_corr(x: np.ndarray, y: np.ndarray) -> float | None:
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    mask = (~np.isnan(x)) & (~np.isnan(y))
    if int(mask.sum()) < 2:
        return None
    xv = x[mask]
    yv = y[mask]
    if np.std(xv) <= 1e-12 or np.std(yv) <= 1e-12:
        return None
    return float(np.corrcoef(xv, yv)[0, 1])


def _m_binary_auc(y_true: np.ndarray, scores: np.ndarray) -> float | None:
    y = np.asarray(y_true, dtype=np.int32)
    s = np.asarray(scores, dtype=np.float64)
    mask = ~np.isnan(s)
    y = y[mask]
    s = s[mask]
    n_pos = int((y == 1).sum())
    n_neg = int((y == 0).sum())
    if n_pos == 0 or n_neg == 0:
        return None
    s_pos = s[y == 1]
    s_neg = s[y == 0]
    gt = (s_pos[:, None] > s_neg[None, :]).sum()
    eq = (s_pos[:, None] == s_neg[None, :]).sum()
    auc = (float(gt) + 0.5 * float(eq)) / float(n_pos * n_neg)
    return float(auc)


def _m_binary_ap(y_true: np.ndarray, scores: np.ndarray) -> float | None:
    y = np.asarray(y_true, dtype=np.int32)
    s = np.asarray(scores, dtype=np.float64)
    mask = ~np.isnan(s)
    y = y[mask]
    s = s[mask]
    n_pos = int((y == 1).sum())
    if n_pos == 0:
        return None
    order = np.argsort(-s, kind="mergesort")
    y_sorted = y[order]
    tp = np.cumsum((y_sorted == 1).astype(np.int32))
    fp = np.cumsum((y_sorted == 0).astype(np.int32))
    precision = tp / np.maximum(tp + fp, 1)
    recall = tp / n_pos
    recall_prev = np.concatenate([[0.0], recall[:-1]])
    ap = float(np.sum((recall - recall_prev) * precision))
    return ap


def _m_make_equal_count_bins(values: np.ndarray, n_bins: int) -> np.ndarray:
    v = np.asarray(values, dtype=np.float64)
    n = len(v)
    if n == 0:
        return np.array([], dtype=np.int32)
    order = np.argsort(v, kind="mergesort")
    bins = np.zeros(n, dtype=np.int32)
    for rank, idx in enumerate(order):
        bins[idx] = min(int(rank * n_bins / n) + 1, n_bins)
    return bins


def _m_calibrate_signal(
    *,
    batch_df: pl.DataFrame,
    score_col: str,
    signal_type: str,
    bad_col: str,
    good_col: str,
    deciles: int,
) -> tuple[pl.DataFrame, pl.DataFrame]:
    work = batch_df.select(
        ["pred_batch", score_col, bad_col, good_col, "winner_accuracy"]
    ).to_dicts()
    if not work:
        empty_bins = pl.DataFrame(
            schema={
                "signal_type": pl.Utf8,
                "bin": pl.Int32,
                "score_min": pl.Float64,
                "score_max": pl.Float64,
                "batch_count": pl.Int32,
                "p_bad": pl.Float64,
                "p_good": pl.Float64,
                "mean_winner_accuracy": pl.Float64,
            }
        )
        empty_map = pl.DataFrame(
            schema={
                "pred_batch": pl.Int32,
                f"{signal_type}_bin": pl.Int32,
                f"{signal_type}_score_calibrated": pl.Float64,
            }
        )
        return empty_bins, empty_map

    scores = np.array([float(r[score_col]) for r in work], dtype=np.float64)
    bins = _m_make_equal_count_bins(scores, deciles)

    rows = []
    out_map = []
    for b in range(1, deciles + 1):
        idx = np.where(bins == b)[0]
        if idx.size == 0:
            continue
        s = scores[idx]
        bad = np.array([int(bool(work[i][bad_col])) for i in idx], dtype=np.int32)
        good = np.array([int(bool(work[i][good_col])) for i in idx], dtype=np.int32)
        wa = np.array(
            [float(work[i]["winner_accuracy"]) for i in idx], dtype=np.float64
        )
        p_bad = float(np.mean(bad))
        p_good = float(np.mean(good))
        rows.append(
            {
                "signal_type": signal_type,
                "bin": int(b),
                "score_min": float(np.min(s)),
                "score_max": float(np.max(s)),
                "batch_count": int(idx.size),
                "p_bad": p_bad,
                "p_good": p_good,
                "mean_winner_accuracy": float(np.mean(wa)),
            }
        )
        calibrated = p_bad if signal_type == "risk" else p_good
        for i in idx:
            out_map.append(
                {
                    "pred_batch": int(work[i]["pred_batch"]),
                    f"{signal_type}_bin": int(b),
                    f"{signal_type}_score_calibrated": float(calibrated),
                }
            )

    bins_df = pl.DataFrame(rows).sort("bin") if rows else pl.DataFrame()
    map_df = pl.DataFrame(out_map).sort("pred_batch") if out_map else pl.DataFrame()
    return bins_df, map_df


def _m_hit_rate_top_quantile(
    df: pl.DataFrame, score_col: str, label_col: str, q: float
) -> float | None:
    if df.is_empty():
        return None
    n = len(df)
    k = max(1, int(np.ceil(n * q)))
    top_df = df.sort(score_col, descending=True).head(k)
    if top_df.is_empty():
        return None
    return float(top_df[label_col].mean())


# 1) Build baseline prediction table (dedup current+archive)
_m_batch_dirs = sorted([p for p in _m_unit_dir.glob("batch_*") if p.is_dir()])
_m_pred_raw_frames = []
for _batch_dir in _m_batch_dirs:
    try:
        _pb = int(_batch_dir.name.split("_")[1])
    except Exception:
        continue
    _stage1_dir = _batch_dir / "stage1"
    for _snap in _m_iter_snapshot_paths(_stage1_dir, STAGE1_COMBO_MATCH_SOURCE_SCOPE):
        _part = _m_load_pred_rows(
            pred_batch=int(_pb), snap=_snap, winner_keys=_m_winner12_set
        )
        if not _part.is_empty():
            _m_pred_raw_frames.append(_part)

if not _m_pred_raw_frames:
    raise ValueError("No PRED rows found for winner-12 in current+archive scope.")

_m_pred_raw_df = pl.concat(_m_pred_raw_frames, how="diagonal_relaxed")
_m_pred_raw_rows = int(len(_m_pred_raw_df))
_m_pred_key_cols = ["pred_batch", "action_key", "timestamp", "batch_id"]
stage1_combo_match_pred_rows_df = (
    _m_pred_raw_df.sort(
        _m_pred_key_cols + ["snapshot_priority", "snapshot_order", "snapshot_source"]
    )
    .unique(subset=_m_pred_key_cols, keep="first")
    .sort(_m_pred_key_cols)
)
_m_pred_dedup_rows = int(len(stage1_combo_match_pred_rows_df))
_m_pred_dup_dropped = int(_m_pred_raw_rows - _m_pred_dedup_rows)
if (
    int(stage1_combo_match_pred_rows_df.select(_m_pred_key_cols).n_unique())
    != _m_pred_dedup_rows
):
    raise AssertionError("PRED dedup uniqueness check failed.")

_m_steps_total = int(_m_winners_clean_df["pred_batch"].n_unique())
_m_combo_coverage_df = (
    stage1_combo_match_pred_rows_df.group_by("action_key")
    .agg(
        [
            pl.len().alias("rows"),
            pl.col("pred_batch").n_unique().alias("unique_steps_present"),
        ]
    )
    .with_columns(
        (pl.col("unique_steps_present") / pl.lit(float(max(1, _m_steps_total)))).alias(
            "step_coverage_share"
        )
    )
    .sort("action_key")
)
_m_steps_with_missing = int(
    (
        stage1_combo_match_pred_rows_df.group_by("pred_batch").agg(
            pl.col("action_key").n_unique().alias("combo_count")
        )["combo_count"]
        < len(_m_winner12)
    ).sum()
)

# Winner-accuracy shares for requested thresholds
_m_winner_acc_series = _m_winners_clean_df["winner_accuracy"].cast(pl.Float64)
_m_share_rows = []
for _thr in STAGE1_COMBO_MATCH_HIGH_THRESHOLDS:
    _m_share_rows.append(
        {
            "condition": "ge",
            "threshold": float(_thr),
            "label": f"winner_accuracy >= {_thr:.2f}",
            "share": float(_m_share(_m_winner_acc_series, "ge", float(_thr))),
        }
    )
for _thr in STAGE1_COMBO_MATCH_LOW_THRESHOLDS:
    _m_share_rows.append(
        {
            "condition": "le",
            "threshold": float(_thr),
            "label": f"winner_accuracy <= {_thr:.2f}",
            "share": float(_m_share(_m_winner_acc_series, "le", float(_thr))),
        }
    )
stage1_winner_accuracy_shares_df = pl.DataFrame(_m_share_rows)

print("\nCell 14C: Live-Style Consensus Signals From 12 Winner Combos")
print(f"  Unit: {STAGE1_COMBO_MATCH_UNIT}")
print(f"  Scope: {STAGE1_COMBO_MATCH_SOURCE_SCOPE}")
print(f"  Winner combos ({len(_m_winner12)}): {_m_winner12}")
print(
    "  Coverage summary: "
    f"steps={_m_steps_total}, pred_rows_raw={_m_pred_raw_rows}, pred_rows_dedup={_m_pred_dedup_rows}, "
    f"dedup_dropped={_m_pred_dup_dropped}, steps_with_missing_combo_rows={_m_steps_with_missing}"
)
print("\nWinner-accuracy shares:")
for _thr in STAGE1_COMBO_MATCH_HIGH_THRESHOLDS:
    _s = float(_m_share(_m_winner_acc_series, "ge", float(_thr)))
    print(f"  Share with winner_accuracy >= {_thr:.2f}: {_s:.4f}")
for _thr in STAGE1_COMBO_MATCH_LOW_THRESHOLDS:
    _s = float(_m_share(_m_winner_acc_series, "le", float(_thr)))
    print(f"  Share with winner_accuracy <= {_thr:.2f}: {_s:.4f}")

_m_pred_base_df = stage1_combo_match_pred_rows_df.select(
    ["pred_batch", "timestamp", "batch_id", "action_key", "y_true", "y_pred"]
)

# 2) Per-step per-combo metrics (baseline)
_m_grouped = _m_pred_base_df.group_by(["pred_batch", "action_key"], maintain_order=True)
_m_combo_step_rows = []
for _k, _df in _m_grouped:
    _pb = int(_k[0])
    _combo = str(_k[1])
    _y_true = _df["y_true"].to_numpy().astype(np.int32, copy=False)
    _y_pred = _df["y_pred"].to_numpy().astype(np.int32, copy=False)
    _m = _m_compute_metrics(_y_true, _y_pred)
    _m_combo_step_rows.append(
        {
            "pred_batch": int(_pb),
            "action_key": _combo,
            "rows": int(len(_df)),
            "accuracy": float(_m["accuracy"]),
            "macro_recall": float(_m["macro_recall"]),
            "macro_f1": float(_m["macro_f1"]),
            "cross_direction_error": float(_m["cross_direction_error"]),
        }
    )
stage1_combo_step_metrics_df = pl.DataFrame(_m_combo_step_rows).sort(
    ["pred_batch", "action_key"]
)

# 3) Capability weights from historical max accuracy
stage1_combo_capability_weights_df = (
    stage1_combo_step_metrics_df.group_by("action_key")
    .agg(pl.col("accuracy").max().alias("combo_capability_max_acc"))
    .sort("action_key")
)
_cap_sum = float(stage1_combo_capability_weights_df["combo_capability_max_acc"].sum())
if _cap_sum <= 0:
    raise ValueError(
        "Capability max-accuracy sum is non-positive; cannot build weights."
    )
stage1_combo_capability_weights_df = stage1_combo_capability_weights_df.with_columns(
    (pl.col("combo_capability_max_acc") / pl.lit(_cap_sum)).alias("normalized_weight")
)
_cap_weight_map = {
    str(r["action_key"]): float(r["normalized_weight"])
    for r in stage1_combo_capability_weights_df.to_dicts()
}
print("\nCapability weights (normalized max accuracy):")
print(stage1_combo_capability_weights_df)

# 4) Pairwise combo agreement/complementarity (global + per-step)
_m_wide_pred_df = _m_pred_base_df.pivot(
    index=["pred_batch", "timestamp", "batch_id", "y_true"],
    values="y_pred",
    on="action_key",
    aggregate_function="first",
).sort(["pred_batch", "timestamp", "batch_id"])
_m_combo_cols = [c for c in _m_winner12 if c in _m_wide_pred_df.columns]
if len(_m_combo_cols) < 2:
    raise ValueError("Need at least 2 combos in wide prediction table.")
if len(_m_combo_cols) != len(_m_winner12):
    print(
        "  Coverage note: wide table combo count differs from winner-12: "
        f"{len(_m_combo_cols)} vs {len(_m_winner12)}"
    )

_m_pb_arr = _m_wide_pred_df["pred_batch"].to_numpy().astype(np.int32, copy=False)
_m_pair_rows = []
_m_pair_step_rows = []
for _i, _combo_a in enumerate(_m_combo_cols):
    _a = _m_wide_pred_df[_combo_a].cast(pl.Float64).to_numpy()
    for _j in range(_i + 1, len(_m_combo_cols)):
        _combo_b = _m_combo_cols[_j]
        _b = _m_wide_pred_df[_combo_b].cast(pl.Float64).to_numpy()
        _y_true = _m_wide_pred_df["y_true"].cast(pl.Float64).to_numpy()
        _valid = (~np.isnan(_a)) & (~np.isnan(_b)) & (~np.isnan(_y_true))
        if not np.any(_valid):
            continue

        _a_v = _a[_valid].astype(np.int32, copy=False)
        _b_v = _b[_valid].astype(np.int32, copy=False)
        _y_v = _y_true[_valid].astype(np.int32, copy=False)
        _pb_v = _m_pb_arr[_valid]

        _same_pred = _a_v == _b_v
        _same_dir = (_a_v >= 2) == (_b_v >= 2)
        _a_correct = _a_v == _y_v
        _b_correct = _b_v == _y_v
        _both_correct = _a_correct & _b_correct
        _only_a = _a_correct & (~_b_correct)
        _only_b = _b_correct & (~_a_correct)
        _either = _a_correct | _b_correct
        _disagree = _a_v != _b_v

        _m_pair_rows.append(
            {
                "combo_a": _combo_a,
                "combo_b": _combo_b,
                "rows": int(len(_a_v)),
                "same_pred_rate": float(np.mean(_same_pred)),
                "same_direction_rate": float(np.mean(_same_dir)),
                "both_correct_rate": float(np.mean(_both_correct)),
                "only_a_correct_rate": float(np.mean(_only_a)),
                "only_b_correct_rate": float(np.mean(_only_b)),
                "either_correct_rate": float(np.mean(_either)),
                "disagreement_rate": float(np.mean(_disagree)),
                "complementarity_rate": float(np.mean(_only_a | _only_b)),
            }
        )

        _order = np.argsort(_pb_v, kind="stable")
        _pb_sorted = _pb_v[_order]
        _same_pred_sorted = _same_pred[_order]
        _same_dir_sorted = _same_dir[_order]
        _both_correct_sorted = _both_correct[_order]
        _only_a_sorted = _only_a[_order]
        _only_b_sorted = _only_b[_order]
        _either_sorted = _either[_order]
        _disagree_sorted = _disagree[_order]

        _pb_unique, _pb_start_idx, _pb_counts = np.unique(
            _pb_sorted,
            return_index=True,
            return_counts=True,
        )
        for _k, _pb in enumerate(_pb_unique):
            _start = int(_pb_start_idx[_k])
            _end = int(_start + _pb_counts[_k])
            _sl = slice(_start, _end)
            _m_pair_step_rows.append(
                {
                    "pred_batch": int(_pb),
                    "combo_a": _combo_a,
                    "combo_b": _combo_b,
                    "rows": int(_pb_counts[_k]),
                    "same_pred_rate": float(np.mean(_same_pred_sorted[_sl])),
                    "same_direction_rate": float(np.mean(_same_dir_sorted[_sl])),
                    "both_correct_rate": float(np.mean(_both_correct_sorted[_sl])),
                    "only_a_correct_rate": float(np.mean(_only_a_sorted[_sl])),
                    "only_b_correct_rate": float(np.mean(_only_b_sorted[_sl])),
                    "either_correct_rate": float(np.mean(_either_sorted[_sl])),
                    "disagreement_rate": float(np.mean(_disagree_sorted[_sl])),
                    "complementarity_rate": float(
                        np.mean(_only_a_sorted[_sl] | _only_b_sorted[_sl])
                    ),
                }
            )

stage1_combo_pairwise_agreement_df = pl.DataFrame(_m_pair_rows).sort(
    ["same_pred_rate", "combo_a", "combo_b"],
    descending=[True, False, False],
)
stage1_combo_pairwise_step_df = pl.DataFrame(_m_pair_step_rows).sort(
    ["pred_batch", "combo_a", "combo_b"]
)
if int(len(stage1_combo_pairwise_agreement_df)) != int(
    len(_m_combo_cols) * (len(_m_combo_cols) - 1) / 2
):
    raise AssertionError("Pairwise combo count mismatch; expected C(12,2)=66.")

# Per-step agreement rolled up from row-level wide table
_m_step_agree_rows = []
for _pb, _df in _m_wide_pred_df.group_by("pred_batch", maintain_order=True):
    _pb_i = int(_pb[0])
    _mat = np.column_stack([_df[c].cast(pl.Float64).to_numpy() for c in _m_combo_cols])
    _all_same_pred = []
    _all_same_dir = []
    _pair_same_pred = []
    _pair_same_dir = []
    _combo_present = []
    for _row in _mat:
        _valid = ~np.isnan(_row)
        _vals = _row[_valid].astype(np.int32, copy=False)
        _combo_present.append(int(_vals.size))
        if _vals.size < 2:
            continue
        _all_same_pred.append(bool(np.all(_vals == _vals[0])))
        _dirs = _vals >= 2
        _all_same_dir.append(bool(np.all(_dirs == _dirs[0])))

        _eq_pred = _vals[:, None] == _vals[None, :]
        _eq_dir = _dirs[:, None] == _dirs[None, :]
        _tri = np.triu_indices(_vals.size, k=1)
        _pair_same_pred.append(float(np.mean(_eq_pred[_tri])))
        _pair_same_dir.append(float(np.mean(_eq_dir[_tri])))

    if _pair_same_pred:
        _m_step_agree_rows.append(
            {
                "pred_batch": int(_pb_i),
                "rows": int(_mat.shape[0]),
                "rows_valid_for_agreement": int(len(_pair_same_pred)),
                "mean_combo_present": float(np.mean(_combo_present))
                if _combo_present
                else 0.0,
                "all12_same_prediction_rate": float(np.mean(_all_same_pred)),
                "all12_same_direction_rate": float(np.mean(_all_same_dir)),
                "pairwise_same_prediction_rate": float(np.mean(_pair_same_pred)),
                "pairwise_same_direction_rate": float(np.mean(_pair_same_dir)),
            }
        )
stage1_step_agreement_df = pl.DataFrame(_m_step_agree_rows).sort("pred_batch")

# 5) Step difficulty scoring + worst windows
_m_winner_by_acc_df = (
    stage1_combo_step_metrics_df.sort(
        ["pred_batch", "accuracy", "action_key"], descending=[False, True, False]
    )
    .unique(subset=["pred_batch"], keep="first")
    .select(
        [
            "pred_batch",
            pl.col("action_key").alias("winner_combo_by_accuracy"),
            pl.col("accuracy").alias("best_combo_accuracy"),
        ]
    )
)
stage1_step_difficulty_df = (
    stage1_combo_step_metrics_df.group_by("pred_batch")
    .agg(
        [
            pl.col("accuracy").mean().alias("mean_combo_accuracy"),
            pl.col("accuracy").median().alias("median_combo_accuracy"),
            pl.col("accuracy").min().alias("min_combo_accuracy"),
            pl.col("accuracy").std(ddof=1).alias("std_combo_accuracy"),
            pl.col("action_key").n_unique().alias("combo_count_present"),
        ]
    )
    .join(_m_winner_by_acc_df, on="pred_batch", how="left")
    .join(
        _m_winners_clean_df.select(
            ["pred_batch", "winner_accuracy", "winner_combo_key"]
        ).unique(subset=["pred_batch"], keep="last"),
        on="pred_batch",
        how="left",
    )
    .join(stage1_step_agreement_df, on="pred_batch", how="left")
    .with_columns(
        [
            pl.col("std_combo_accuracy").fill_null(0.0),
            (pl.col("best_combo_accuracy") - pl.col("mean_combo_accuracy")).alias(
                "winner_minus_mean_accuracy"
            ),
        ]
    )
    .sort(
        [
            "best_combo_accuracy",
            "mean_combo_accuracy",
            "std_combo_accuracy",
            "pred_batch",
        ],
        descending=[False, False, True, False],
    )
)
if int(len(stage1_step_difficulty_df)) != int(_m_steps_total):
    raise AssertionError(
        "Step difficulty row count mismatch: "
        f"{len(stage1_step_difficulty_df)} vs {_m_steps_total}"
    )
stage1_worst_steps_accuracy_df = stage1_step_difficulty_df.head(
    int(STAGE1_COMBO_MATCH_TOPK_STEPS)
)

_m_step_ordered_df = stage1_step_difficulty_df.sort("pred_batch")
_m_pb_arr = _m_step_ordered_df["pred_batch"].to_numpy()
_m_best_arr = _m_step_ordered_df["best_combo_accuracy"].to_numpy()
_m_mean_arr = _m_step_ordered_df["mean_combo_accuracy"].to_numpy()
_m_win_rows = []
for _window_size in sorted(
    {int(v) for v in STAGE1_COMBO_MATCH_WINDOW_STEPS if int(v) > 0}
):
    if len(_m_pb_arr) < _window_size:
        continue
    for _i in range(0, len(_m_pb_arr) - _window_size + 1):
        _sl = slice(_i, _i + _window_size)
        _best_w = _m_best_arr[_sl]
        _mean_w = _m_mean_arr[_sl]
        _m_win_rows.append(
            {
                "window_start_pred_batch": int(_m_pb_arr[_i]),
                "window_end_pred_batch": int(_m_pb_arr[_i + _window_size - 1]),
                "window_size": int(_window_size),
                "avg_best_combo_accuracy": float(np.mean(_best_w)),
                "avg_mean_combo_accuracy": float(np.mean(_mean_w)),
                "pct_steps_best_acc_lt_0_50": float(np.mean(_best_w < 0.50)),
                "pct_steps_best_acc_lt_0_60": float(np.mean(_best_w < 0.60)),
            }
        )
stage1_worst_windows_accuracy_df = (
    pl.DataFrame(_m_win_rows).sort(
        [
            "window_size",
            "avg_best_combo_accuracy",
            "avg_mean_combo_accuracy",
            "window_start_pred_batch",
        ],
        descending=[False, False, False, False],
    )
    if _m_win_rows
    else pl.DataFrame(
        schema={
            "window_start_pred_batch": pl.Int32,
            "window_end_pred_batch": pl.Int32,
            "window_size": pl.Int32,
            "avg_best_combo_accuracy": pl.Float64,
            "avg_mean_combo_accuracy": pl.Float64,
            "pct_steps_best_acc_lt_0_50": pl.Float64,
            "pct_steps_best_acc_lt_0_60": pl.Float64,
        }
    )
)

# 6) Combo accuracy correlation across steps
_m_acc_pivot_df = stage1_combo_step_metrics_df.pivot(
    index="pred_batch", values="accuracy", on="action_key"
).sort("pred_batch")
_m_corr_rows = []
for _i, _combo_a in enumerate(_m_combo_cols):
    if _combo_a not in _m_acc_pivot_df.columns:
        continue
    _a = _m_acc_pivot_df[_combo_a].cast(pl.Float64).to_numpy()
    for _j in range(_i + 1, len(_m_combo_cols)):
        _combo_b = _m_combo_cols[_j]
        if _combo_b not in _m_acc_pivot_df.columns:
            continue
        _b = _m_acc_pivot_df[_combo_b].cast(pl.Float64).to_numpy()
        _valid = (~np.isnan(_a)) & (~np.isnan(_b))
        if int(np.sum(_valid)) < 2:
            _corr = None
        else:
            _corr = float(np.corrcoef(_a[_valid], _b[_valid])[0, 1])
        _m_corr_rows.append(
            {
                "combo_a": _combo_a,
                "combo_b": _combo_b,
                "overlap_steps": int(np.sum(_valid)),
                "accuracy_corr": _corr,
            }
        )
stage1_combo_correlation_df = (
    pl.DataFrame(_m_corr_rows).sort("accuracy_corr", descending=True)
    if _m_corr_rows
    else pl.DataFrame(
        schema={
            "combo_a": pl.Utf8,
            "combo_b": pl.Utf8,
            "overlap_steps": pl.Int32,
            "accuracy_corr": pl.Float64,
        }
    )
)

# 7) Build row-level live-style consensus features (no winner label usage)
_m_combo_weights = np.array(
    [_cap_weight_map[c] for c in _m_combo_cols], dtype=np.float64
)
_m_combo_pred_matrix = np.column_stack(
    [_m_wide_pred_df[c].cast(pl.Float64).to_numpy() for c in _m_combo_cols]
)
_m_row_pred_batch = (
    _m_wide_pred_df["pred_batch"].to_numpy().astype(np.int32, copy=False)
)
_m_row_timestamp = _m_wide_pred_df["timestamp"].to_list()
_m_row_batch_id = _m_wide_pred_df["batch_id"].to_numpy().astype(np.int32, copy=False)
_m_row_y_true = _m_wide_pred_df["y_true"].to_numpy().astype(np.int32, copy=False)

_m_row_signal_rows = []
for _idx in range(_m_combo_pred_matrix.shape[0]):
    _preds = _m_combo_pred_matrix[_idx]
    _valid = ~np.isnan(_preds)
    _n_present = int(_valid.sum())
    if _n_present <= 0:
        continue
    _pred_vals = _preds[_valid].astype(np.int32, copy=False)
    _w = _m_combo_weights[_valid]
    _w_sum = float(_w.sum())
    if _w_sum <= 0:
        continue

    _class_w = np.zeros(STAGE1_COMBO_MATCH_CLASS_COUNT, dtype=np.float64)
    for _p, _pw in zip(_pred_vals, _w):
        if 0 <= int(_p) < STAGE1_COMBO_MATCH_CLASS_COUNT:
            _class_w[int(_p)] += float(_pw)
    _p_class = _class_w / _w_sum
    _p_down = float(_p_class[0] + _p_class[1])
    _p_up = float(_p_class[2] + _p_class[3])

    _same_class = float(np.sum(_p_class * _p_class))
    _same_dir = float(_p_down * _p_down + _p_up * _p_up)
    _h_class = _m_entropy_norm(_p_class, np.log(float(STAGE1_COMBO_MATCH_CLASS_COUNT)))
    _h_dir = _m_entropy_norm(np.array([_p_down, _p_up], dtype=np.float64), np.log(2.0))
    _top2 = np.sort(_p_class)[-2:]
    _class_margin = float(_top2[-1] - _top2[-2])
    _dir_margin = float(abs(_p_up - _p_down))

    _risk_raw = float(
        np.mean(
            [
                _same_class,
                _same_dir,
                _class_margin,
                _dir_margin,
                1.0 - _h_class,
                1.0 - _h_dir,
            ]
        )
    )
    _conf_raw = float(1.0 - _risk_raw)

    _maj_class = int(np.argmax(_p_class))
    _maj_dir = "UP" if _p_up >= _p_down else "DOWN"

    _m_row_signal_rows.append(
        {
            "pred_batch": int(_m_row_pred_batch[_idx]),
            "timestamp": _m_row_timestamp[_idx],
            "batch_id": int(_m_row_batch_id[_idx]),
            "y_true": int(_m_row_y_true[_idx]),
            "n_combos_present": int(_n_present),
            "present_weight_sum": float(_w_sum),
            "weighted_majority_class": int(_maj_class),
            "weighted_majority_direction": _maj_dir,
            "p_class_0": float(_p_class[0]),
            "p_class_1": float(_p_class[1]),
            "p_class_2": float(_p_class[2]),
            "p_class_3": float(_p_class[3]),
            "p_down": float(_p_down),
            "p_up": float(_p_up),
            "w_same_class_pair_rate": float(_same_class),
            "w_same_direction_pair_rate": float(_same_dir),
            "w_class_entropy_norm": float(_h_class),
            "w_direction_entropy_norm": float(_h_dir),
            "w_class_margin": float(_class_margin),
            "w_direction_margin": float(_dir_margin),
            "risk_raw": float(_risk_raw),
            "confidence_raw": float(_conf_raw),
        }
    )

stage1_row_consensus_signals_df = pl.DataFrame(_m_row_signal_rows).sort(
    ["pred_batch", "timestamp", "batch_id"]
)
if int(len(stage1_row_consensus_signals_df)) != int(_m_wide_pred_df.height):
    raise AssertionError(
        "Row-signal row count mismatch with dedup row-key table: "
        f"{len(stage1_row_consensus_signals_df)} vs {_m_wide_pred_df.height}"
    )

# 8) Build batch-level signal table
stage1_batch_consensus_signals_df = (
    stage1_row_consensus_signals_df.group_by("pred_batch")
    .agg(
        [
            pl.len().alias("rows"),
            pl.col("n_combos_present").mean().alias("n_combos_present_mean"),
            pl.col("n_combos_present").min().alias("n_combos_present_min"),
            pl.col("n_combos_present").max().alias("n_combos_present_max"),
            pl.col("risk_raw").mean().alias("risk_raw_mean"),
            pl.col("risk_raw").std(ddof=1).fill_null(0.0).alias("risk_raw_std"),
            pl.col("risk_raw").quantile(0.10).alias("risk_raw_p10"),
            pl.col("risk_raw").quantile(0.50).alias("risk_raw_p50"),
            pl.col("risk_raw").quantile(0.90).alias("risk_raw_p90"),
            pl.col("confidence_raw").mean().alias("confidence_raw_mean"),
            pl.col("confidence_raw")
            .std(ddof=1)
            .fill_null(0.0)
            .alias("confidence_raw_std"),
            pl.col("confidence_raw").quantile(0.10).alias("confidence_raw_p10"),
            pl.col("confidence_raw").quantile(0.50).alias("confidence_raw_p50"),
            pl.col("confidence_raw").quantile(0.90).alias("confidence_raw_p90"),
            pl.col("w_same_class_pair_rate")
            .mean()
            .alias("w_same_class_pair_rate_mean"),
            pl.col("w_same_direction_pair_rate")
            .mean()
            .alias("w_same_direction_pair_rate_mean"),
            pl.col("w_class_entropy_norm").mean().alias("w_class_entropy_norm_mean"),
            pl.col("w_direction_entropy_norm")
            .mean()
            .alias("w_direction_entropy_norm_mean"),
            pl.col("w_class_margin").mean().alias("w_class_margin_mean"),
            pl.col("w_direction_margin").mean().alias("w_direction_margin_mean"),
        ]
    )
    .join(
        stage1_step_agreement_df.select(
            [
                "pred_batch",
                "all12_same_prediction_rate",
                "all12_same_direction_rate",
                "pairwise_same_prediction_rate",
                "pairwise_same_direction_rate",
            ]
        ),
        on="pred_batch",
        how="left",
    )
    .join(
        _m_winners_clean_df.select(
            ["pred_batch", "winner_accuracy", "winner_combo_key"]
        ).unique(subset=["pred_batch"], keep="last"),
        on="pred_batch",
        how="left",
    )
    .with_columns(
        [
            (pl.col("winner_accuracy") <= float(STAGE1_SIGNAL_BAD_THRESHOLD)).alias(
                "is_bad_regime"
            ),
            (pl.col("winner_accuracy") >= float(STAGE1_SIGNAL_GOOD_THRESHOLD)).alias(
                "is_good_regime"
            ),
        ]
    )
    .sort("pred_batch")
)
if int(len(stage1_batch_consensus_signals_df)) != int(_m_steps_total):
    raise AssertionError(
        "Batch signal table row count mismatch: "
        f"{len(stage1_batch_consensus_signals_df)} vs {_m_steps_total}"
    )

# 9) Decile segmentation by winner_accuracy (non-overlapping)
_m_decile_bins = _m_make_equal_count_bins(
    stage1_batch_consensus_signals_df["winner_accuracy"]
    .to_numpy()
    .astype(np.float64, copy=False),
    int(STAGE1_COMBO_MATCH_DECILES),
)
stage1_batch_consensus_signals_df = stage1_batch_consensus_signals_df.with_columns(
    pl.Series("winner_accuracy_decile", _m_decile_bins).cast(pl.Int32)
)
stage1_decile_agreement_df = (
    stage1_batch_consensus_signals_df.group_by("winner_accuracy_decile")
    .agg(
        [
            pl.len().alias("step_count"),
            pl.col("winner_accuracy").min().alias("winner_accuracy_min"),
            pl.col("winner_accuracy").max().alias("winner_accuracy_max"),
            pl.col("winner_accuracy").mean().alias("winner_accuracy_mean"),
            pl.col("all12_same_prediction_rate")
            .mean()
            .alias("avg_all12_same_prediction_rate"),
            pl.col("all12_same_direction_rate")
            .mean()
            .alias("avg_all12_same_direction_rate"),
            pl.col("pairwise_same_prediction_rate")
            .mean()
            .alias("avg_pairwise_same_prediction_rate"),
            pl.col("pairwise_same_direction_rate")
            .mean()
            .alias("avg_pairwise_same_direction_rate"),
            pl.col("risk_raw_mean").mean().alias("avg_risk_raw_mean"),
            pl.col("confidence_raw_mean").mean().alias("avg_confidence_raw_mean"),
        ]
    )
    .sort("winner_accuracy_decile")
)
if int(len(stage1_decile_agreement_df)) != int(STAGE1_COMBO_MATCH_DECILES):
    print(
        "  Decile note: produced fewer than requested bins due to sample/tie structure: "
        f"{len(stage1_decile_agreement_df)} / {STAGE1_COMBO_MATCH_DECILES}"
    )

# 10) Cumulative threshold table (continuity)
_m_thr_rows = []
for _thr in STAGE1_COMBO_MATCH_HIGH_THRESHOLDS:
    _cond_df = stage1_batch_consensus_signals_df.filter(
        pl.col("winner_accuracy") >= float(_thr)
    )
    _m_thr_rows.append(
        {
            "condition": "ge",
            "threshold": float(_thr),
            "label": f"winner_accuracy >= {_thr:.2f}",
            "step_count": int(len(_cond_df)),
            "step_share": float(len(_cond_df) / max(1, _m_steps_total)),
            "avg_all12_same_prediction_rate": float(
                _cond_df["all12_same_prediction_rate"].mean()
            )
            if not _cond_df.is_empty()
            else 0.0,
            "avg_all12_same_direction_rate": float(
                _cond_df["all12_same_direction_rate"].mean()
            )
            if not _cond_df.is_empty()
            else 0.0,
            "avg_pairwise_same_prediction_rate": float(
                _cond_df["pairwise_same_prediction_rate"].mean()
            )
            if not _cond_df.is_empty()
            else 0.0,
            "avg_pairwise_same_direction_rate": float(
                _cond_df["pairwise_same_direction_rate"].mean()
            )
            if not _cond_df.is_empty()
            else 0.0,
            "avg_risk_raw_mean": float(_cond_df["risk_raw_mean"].mean())
            if not _cond_df.is_empty()
            else 0.0,
            "avg_confidence_raw_mean": float(_cond_df["confidence_raw_mean"].mean())
            if not _cond_df.is_empty()
            else 0.0,
        }
    )
for _thr in STAGE1_COMBO_MATCH_LOW_THRESHOLDS:
    _cond_df = stage1_batch_consensus_signals_df.filter(
        pl.col("winner_accuracy") <= float(_thr)
    )
    _m_thr_rows.append(
        {
            "condition": "le",
            "threshold": float(_thr),
            "label": f"winner_accuracy <= {_thr:.2f}",
            "step_count": int(len(_cond_df)),
            "step_share": float(len(_cond_df) / max(1, _m_steps_total)),
            "avg_all12_same_prediction_rate": float(
                _cond_df["all12_same_prediction_rate"].mean()
            )
            if not _cond_df.is_empty()
            else 0.0,
            "avg_all12_same_direction_rate": float(
                _cond_df["all12_same_direction_rate"].mean()
            )
            if not _cond_df.is_empty()
            else 0.0,
            "avg_pairwise_same_prediction_rate": float(
                _cond_df["pairwise_same_prediction_rate"].mean()
            )
            if not _cond_df.is_empty()
            else 0.0,
            "avg_pairwise_same_direction_rate": float(
                _cond_df["pairwise_same_direction_rate"].mean()
            )
            if not _cond_df.is_empty()
            else 0.0,
            "avg_risk_raw_mean": float(_cond_df["risk_raw_mean"].mean())
            if not _cond_df.is_empty()
            else 0.0,
            "avg_confidence_raw_mean": float(_cond_df["confidence_raw_mean"].mean())
            if not _cond_df.is_empty()
            else 0.0,
        }
    )
stage1_threshold_agreement_df = pl.DataFrame(_m_thr_rows)

# 11) Calibrate risk/confidence scores on batch-level deciles
_risk_bins_df, _risk_map_df = _m_calibrate_signal(
    batch_df=stage1_batch_consensus_signals_df,
    score_col="risk_raw_mean",
    signal_type="risk",
    bad_col="is_bad_regime",
    good_col="is_good_regime",
    deciles=int(STAGE1_COMBO_MATCH_DECILES),
)
_conf_bins_df, _conf_map_df = _m_calibrate_signal(
    batch_df=stage1_batch_consensus_signals_df,
    score_col="confidence_raw_mean",
    signal_type="confidence",
    bad_col="is_bad_regime",
    good_col="is_good_regime",
    deciles=int(STAGE1_COMBO_MATCH_DECILES),
)
stage1_batch_signal_calibration_df = pl.concat(
    [
        _risk_bins_df,
        _conf_bins_df,
    ],
    how="diagonal_relaxed",
).sort(["signal_type", "bin"])

stage1_batch_consensus_signals_df = (
    stage1_batch_consensus_signals_df.join(_risk_map_df, on="pred_batch", how="left")
    .join(_conf_map_df, on="pred_batch", how="left")
    .with_columns(
        [
            pl.col("risk_score_calibrated").fill_null(pl.col("risk_raw_mean")),
            pl.col("confidence_score_calibrated").fill_null(
                pl.col("confidence_raw_mean")
            ),
        ]
    )
)

# 12) Correlations and signal evaluation
_m_corr_metrics = [
    "all12_same_prediction_rate",
    "all12_same_direction_rate",
    "pairwise_same_prediction_rate",
    "pairwise_same_direction_rate",
    "risk_raw_mean",
    "confidence_raw_mean",
]
_m_wa = (
    stage1_batch_consensus_signals_df["winner_accuracy"]
    .to_numpy()
    .astype(np.float64, copy=False)
)
_m_agreement_correlations = {}
for _col in _m_corr_metrics:
    _x = (
        stage1_batch_consensus_signals_df[_col]
        .to_numpy()
        .astype(np.float64, copy=False)
    )
    _pearson = _m_safe_corr(_m_wa, _x)
    _sx = _m_rankdata_average(_x)
    _sy = _m_rankdata_average(_m_wa)
    _spearman = _m_safe_corr(_sy, _sx)
    _m_agreement_correlations[_col] = {
        "pearson": _pearson,
        "spearman": _spearman,
    }

_m_bad = (
    stage1_batch_consensus_signals_df["is_bad_regime"]
    .cast(pl.Int8)
    .to_numpy()
    .astype(np.int32)
)
_m_good = (
    stage1_batch_consensus_signals_df["is_good_regime"]
    .cast(pl.Int8)
    .to_numpy()
    .astype(np.int32)
)
_m_risk_cal = (
    stage1_batch_consensus_signals_df["risk_score_calibrated"]
    .to_numpy()
    .astype(np.float64, copy=False)
)
_m_conf_cal = (
    stage1_batch_consensus_signals_df["confidence_score_calibrated"]
    .to_numpy()
    .astype(np.float64, copy=False)
)

_m_risk_auc = _m_binary_auc(_m_bad, _m_risk_cal)
_m_risk_ap = _m_binary_ap(_m_bad, _m_risk_cal)
_m_conf_auc = _m_binary_auc(_m_good, _m_conf_cal)
_m_conf_ap = _m_binary_ap(_m_good, _m_conf_cal)

_m_eval_rows = []
for _q in [0.10, 0.20, 0.30]:
    _m_eval_rows.append(
        {
            "quantile": float(_q),
            "risk_top_hit_bad_rate": _m_hit_rate_top_quantile(
                stage1_batch_consensus_signals_df,
                "risk_score_calibrated",
                "is_bad_regime",
                _q,
            ),
            "confidence_top_hit_good_rate": _m_hit_rate_top_quantile(
                stage1_batch_consensus_signals_df,
                "confidence_score_calibrated",
                "is_good_regime",
                _q,
            ),
        }
    )
stage1_signal_eval_quantiles_df = pl.DataFrame(_m_eval_rows)

# best/worst decile comparison for calibrated scores
_m_best_decile = int(stage1_batch_consensus_signals_df["winner_accuracy_decile"].max())
_m_worst_decile = int(stage1_batch_consensus_signals_df["winner_accuracy_decile"].min())
_m_best_decile_df = stage1_batch_consensus_signals_df.filter(
    pl.col("winner_accuracy_decile") == _m_best_decile
)
_m_worst_decile_df = stage1_batch_consensus_signals_df.filter(
    pl.col("winner_accuracy_decile") == _m_worst_decile
)
_m_calibrated_decile_means = {
    "best_decile": {
        "decile": int(_m_best_decile),
        "risk_score_calibrated_mean": float(
            _m_best_decile_df["risk_score_calibrated"].mean()
        ),
        "confidence_score_calibrated_mean": float(
            _m_best_decile_df["confidence_score_calibrated"].mean()
        ),
    },
    "worst_decile": {
        "decile": int(_m_worst_decile),
        "risk_score_calibrated_mean": float(
            _m_worst_decile_df["risk_score_calibrated"].mean()
        ),
        "confidence_score_calibrated_mean": float(
            _m_worst_decile_df["confidence_score_calibrated"].mean()
        ),
    },
}

# Top pairwise stats and prints
_m_top_redundant_df = stage1_combo_pairwise_agreement_df.sort(
    ["same_pred_rate", "same_direction_rate", "rows"],
    descending=[True, True, True],
).head(10)
_m_top_complementary_df = stage1_combo_pairwise_agreement_df.sort(
    ["complementarity_rate", "either_correct_rate", "rows"],
    descending=[True, True, True],
).head(10)

print("\nTop 10 redundant pairs (same prediction):")
print(
    _m_top_redundant_df.select(
        ["combo_a", "combo_b", "same_pred_rate", "same_direction_rate"]
    )
)
print("\nTop 10 complementary pairs (only one correct):")
print(
    _m_top_complementary_df.select(
        ["combo_a", "combo_b", "complementarity_rate", "either_correct_rate"]
    )
)

print("\nDecile agreement table (non-overlapping):")
print(stage1_decile_agreement_df)

print("\nWorst 10 steps by best_combo_accuracy:")
print(
    stage1_worst_steps_accuracy_df.head(10).select(
        [
            "pred_batch",
            "winner_combo_by_accuracy",
            "winner_accuracy",
            "best_combo_accuracy",
            "mean_combo_accuracy",
            "all12_same_prediction_rate",
            "all12_same_direction_rate",
        ]
    )
)
for _window_size in sorted(
    {int(v) for v in STAGE1_COMBO_MATCH_WINDOW_STEPS if int(v) > 0}
):
    _w_df = stage1_worst_windows_accuracy_df.filter(
        pl.col("window_size") == _window_size
    ).head(10)
    print(f"\nWorst windows (size={_window_size}) by avg_best_combo_accuracy:")
    print(
        _w_df.select(
            [
                "window_start_pred_batch",
                "window_end_pred_batch",
                "avg_best_combo_accuracy",
                "avg_mean_combo_accuracy",
                "pct_steps_best_acc_lt_0_50",
                "pct_steps_best_acc_lt_0_60",
            ]
        )
    )

print("\nSignal evaluation summary:")
print(
    f"  risk vs bad-regime (<= {STAGE1_SIGNAL_BAD_THRESHOLD:.2f}): "
    f"AUC={_m_risk_auc}, PR-AUC={_m_risk_ap}"
)
print(
    f"  confidence vs good-regime (>= {STAGE1_SIGNAL_GOOD_THRESHOLD:.2f}): "
    f"AUC={_m_conf_auc}, PR-AUC={_m_conf_ap}"
)
print("  Top-quantile hit rates:")
print(stage1_signal_eval_quantiles_df)
print("  Calibrated means in best vs worst winner-accuracy deciles:")
print(_m_calibrated_decile_means)

# 13) Save artifacts
stage1_combo_match_artifact_dir = (
    _m_unit_dir / "combo_match_analysis" / datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
)
stage1_combo_match_artifact_dir.mkdir(parents=True, exist_ok=True)

_m_pred_dedup_path = (
    stage1_combo_match_artifact_dir / "winner12_prediction_rows_pred_dedup.parquet"
)
_m_combo_cov_path_parquet = (
    stage1_combo_match_artifact_dir / "winner12_combo_coverage_pred.parquet"
)
_m_combo_cov_path_csv = (
    stage1_combo_match_artifact_dir / "winner12_combo_coverage_pred.csv"
)
_m_combo_weights_path_parquet = (
    stage1_combo_match_artifact_dir / "winner12_combo_capability_weights.parquet"
)
_m_combo_weights_path_csv = (
    stage1_combo_match_artifact_dir / "winner12_combo_capability_weights.csv"
)
_m_row_signals_path_parquet = (
    stage1_combo_match_artifact_dir / "winner12_row_consensus_signals.parquet"
)
_m_row_signals_path_csv = (
    stage1_combo_match_artifact_dir / "winner12_row_consensus_signals.csv"
)
_m_batch_signals_path_parquet = (
    stage1_combo_match_artifact_dir / "winner12_batch_consensus_signals.parquet"
)
_m_batch_signals_path_csv = (
    stage1_combo_match_artifact_dir / "winner12_batch_consensus_signals.csv"
)
_m_batch_calib_path_parquet = (
    stage1_combo_match_artifact_dir / "winner12_batch_signal_calibration.parquet"
)
_m_batch_calib_path_csv = (
    stage1_combo_match_artifact_dir / "winner12_batch_signal_calibration.csv"
)
_m_deciles_path_parquet = (
    stage1_combo_match_artifact_dir / "winner12_decile_agreement.parquet"
)
_m_deciles_path_csv = stage1_combo_match_artifact_dir / "winner12_decile_agreement.csv"
_m_shares_path_parquet = (
    stage1_combo_match_artifact_dir / "winner_accuracy_threshold_shares.parquet"
)
_m_shares_path_csv = (
    stage1_combo_match_artifact_dir / "winner_accuracy_threshold_shares.csv"
)
_m_combo_step_path_parquet = (
    stage1_combo_match_artifact_dir / "winner12_combo_step_metrics_baseline.parquet"
)
_m_combo_step_path_csv = (
    stage1_combo_match_artifact_dir / "winner12_combo_step_metrics_baseline.csv"
)
_m_pairwise_path_parquet = (
    stage1_combo_match_artifact_dir
    / "winner12_combo_pairwise_agreement_baseline.parquet"
)
_m_pairwise_path_csv = (
    stage1_combo_match_artifact_dir / "winner12_combo_pairwise_agreement_baseline.csv"
)
_m_pairwise_step_path_parquet = (
    stage1_combo_match_artifact_dir
    / "winner12_combo_pairwise_agreement_stepwise.parquet"
)
_m_pairwise_step_path_csv = (
    stage1_combo_match_artifact_dir / "winner12_combo_pairwise_agreement_stepwise.csv"
)
_m_step_difficulty_path_parquet = (
    stage1_combo_match_artifact_dir / "winner12_step_difficulty_baseline.parquet"
)
_m_step_difficulty_path_csv = (
    stage1_combo_match_artifact_dir / "winner12_step_difficulty_baseline.csv"
)
_m_worst_steps_path_parquet = (
    stage1_combo_match_artifact_dir / "winner12_worst_steps_by_accuracy.parquet"
)
_m_worst_steps_path_csv = (
    stage1_combo_match_artifact_dir / "winner12_worst_steps_by_accuracy.csv"
)
_m_worst_windows_path_parquet = (
    stage1_combo_match_artifact_dir
    / "winner12_worst_rolling_windows_by_accuracy.parquet"
)
_m_worst_windows_path_csv = (
    stage1_combo_match_artifact_dir / "winner12_worst_rolling_windows_by_accuracy.csv"
)
_m_combo_corr_path_parquet = (
    stage1_combo_match_artifact_dir / "winner12_combo_accuracy_correlation.parquet"
)
_m_combo_corr_path_csv = (
    stage1_combo_match_artifact_dir / "winner12_combo_accuracy_correlation.csv"
)
_m_threshold_agreement_path_parquet = (
    stage1_combo_match_artifact_dir / "winner12_threshold_agreement.parquet"
)
_m_threshold_agreement_path_csv = (
    stage1_combo_match_artifact_dir / "winner12_threshold_agreement.csv"
)
_m_summary_path = stage1_combo_match_artifact_dir / "winner12_combo_match_summary.json"

stage1_combo_match_pred_rows_df.write_parquet(_m_pred_dedup_path)
_m_combo_coverage_df.write_parquet(_m_combo_cov_path_parquet)
_m_combo_coverage_df.write_csv(_m_combo_cov_path_csv)
stage1_combo_capability_weights_df.write_parquet(_m_combo_weights_path_parquet)
stage1_combo_capability_weights_df.write_csv(_m_combo_weights_path_csv)
stage1_row_consensus_signals_df.write_parquet(_m_row_signals_path_parquet)
stage1_row_consensus_signals_df.write_csv(_m_row_signals_path_csv)
stage1_batch_consensus_signals_df.write_parquet(_m_batch_signals_path_parquet)
stage1_batch_consensus_signals_df.write_csv(_m_batch_signals_path_csv)
stage1_batch_signal_calibration_df.write_parquet(_m_batch_calib_path_parquet)
stage1_batch_signal_calibration_df.write_csv(_m_batch_calib_path_csv)
stage1_decile_agreement_df.write_parquet(_m_deciles_path_parquet)
stage1_decile_agreement_df.write_csv(_m_deciles_path_csv)
stage1_winner_accuracy_shares_df.write_parquet(_m_shares_path_parquet)
stage1_winner_accuracy_shares_df.write_csv(_m_shares_path_csv)
stage1_combo_step_metrics_df.write_parquet(_m_combo_step_path_parquet)
stage1_combo_step_metrics_df.write_csv(_m_combo_step_path_csv)
stage1_combo_pairwise_agreement_df.write_parquet(_m_pairwise_path_parquet)
stage1_combo_pairwise_agreement_df.write_csv(_m_pairwise_path_csv)
stage1_combo_pairwise_step_df.write_parquet(_m_pairwise_step_path_parquet)
stage1_combo_pairwise_step_df.write_csv(_m_pairwise_step_path_csv)
stage1_step_difficulty_df.write_parquet(_m_step_difficulty_path_parquet)
stage1_step_difficulty_df.write_csv(_m_step_difficulty_path_csv)
stage1_worst_steps_accuracy_df.write_parquet(_m_worst_steps_path_parquet)
stage1_worst_steps_accuracy_df.write_csv(_m_worst_steps_path_csv)
stage1_worst_windows_accuracy_df.write_parquet(_m_worst_windows_path_parquet)
stage1_worst_windows_accuracy_df.write_csv(_m_worst_windows_path_csv)
stage1_combo_correlation_df.write_parquet(_m_combo_corr_path_parquet)
stage1_combo_correlation_df.write_csv(_m_combo_corr_path_csv)
stage1_threshold_agreement_df.write_parquet(_m_threshold_agreement_path_parquet)
stage1_threshold_agreement_df.write_csv(_m_threshold_agreement_path_csv)

_m_summary = {
    "run_id": STAGE1_COMBO_MATCH_RUN_ID,
    "unit": STAGE1_COMBO_MATCH_UNIT,
    "source_scope": STAGE1_COMBO_MATCH_SOURCE_SCOPE,
    "winner_combo_count": int(len(_m_winner12)),
    "winner_combos": _m_winner12,
    "signal_config": {
        "weighting": STAGE1_SIGNAL_WEIGHTING,
        "deciles": int(STAGE1_COMBO_MATCH_DECILES),
        "bad_threshold": float(STAGE1_SIGNAL_BAD_THRESHOLD),
        "good_threshold": float(STAGE1_SIGNAL_GOOD_THRESHOLD),
        "window_steps": [int(v) for v in STAGE1_COMBO_MATCH_WINDOW_STEPS],
    },
    "capability_weights": stage1_combo_capability_weights_df.to_dicts(),
    "rows": {
        "pred_raw": int(_m_pred_raw_rows),
        "pred_dedup": int(_m_pred_dedup_rows),
        "pred_duplicates_dropped": int(_m_pred_dup_dropped),
        "row_signals": int(len(stage1_row_consensus_signals_df)),
        "batch_signals": int(len(stage1_batch_consensus_signals_df)),
    },
    "coverage": {
        "steps_total": int(_m_steps_total),
        "steps_with_missing_combos": int(_m_steps_with_missing),
        "pair_count": int(len(stage1_combo_pairwise_agreement_df)),
        "pairwise_step_rows": int(len(stage1_combo_pairwise_step_df)),
    },
    "agreement_correlations": _m_agreement_correlations,
    "decile_stats": stage1_decile_agreement_df.to_dicts(),
    "threshold_stats": stage1_threshold_agreement_df.to_dicts(),
    "signal_eval": {
        "risk_vs_bad": {
            "auc": _m_risk_auc,
            "pr_auc": _m_risk_ap,
        },
        "confidence_vs_good": {
            "auc": _m_conf_auc,
            "pr_auc": _m_conf_ap,
        },
        "top_quantile_hit_rates": stage1_signal_eval_quantiles_df.to_dicts(),
        "calibrated_means_best_vs_worst_decile": _m_calibrated_decile_means,
    },
    "pairwise_stats": {
        "most_redundant_pairs": _m_top_redundant_df.to_dicts(),
        "most_complementary_pairs": _m_top_complementary_df.to_dicts(),
    },
    "worst_step_stats": {
        "topk": int(STAGE1_COMBO_MATCH_TOPK_STEPS),
        "best_combo_accuracy_min": float(
            stage1_step_difficulty_df["best_combo_accuracy"].min()
        ),
        "best_combo_accuracy_mean": float(
            stage1_step_difficulty_df["best_combo_accuracy"].mean()
        ),
        "best_combo_accuracy_max": float(
            stage1_step_difficulty_df["best_combo_accuracy"].max()
        ),
    },
    "worst_window_stats": {
        "topk_per_window": int(STAGE1_COMBO_MATCH_TOPK_WINDOWS),
        "window_sizes": [
            int(v)
            for v in sorted(
                {int(w) for w in STAGE1_COMBO_MATCH_WINDOW_STEPS if int(w) > 0}
            )
        ],
        "window_rows_total": int(len(stage1_worst_windows_accuracy_df)),
    },
    "artifacts": {
        "winner12_prediction_rows_pred_dedup": str(_m_pred_dedup_path),
        "winner12_combo_coverage_pred_parquet": str(_m_combo_cov_path_parquet),
        "winner12_combo_coverage_pred_csv": str(_m_combo_cov_path_csv),
        "winner12_combo_capability_weights_parquet": str(_m_combo_weights_path_parquet),
        "winner12_combo_capability_weights_csv": str(_m_combo_weights_path_csv),
        "winner12_row_consensus_signals_parquet": str(_m_row_signals_path_parquet),
        "winner12_row_consensus_signals_csv": str(_m_row_signals_path_csv),
        "winner12_batch_consensus_signals_parquet": str(_m_batch_signals_path_parquet),
        "winner12_batch_consensus_signals_csv": str(_m_batch_signals_path_csv),
        "winner12_batch_signal_calibration_parquet": str(_m_batch_calib_path_parquet),
        "winner12_batch_signal_calibration_csv": str(_m_batch_calib_path_csv),
        "winner12_decile_agreement_parquet": str(_m_deciles_path_parquet),
        "winner12_decile_agreement_csv": str(_m_deciles_path_csv),
        "winner_accuracy_threshold_shares_parquet": str(_m_shares_path_parquet),
        "winner_accuracy_threshold_shares_csv": str(_m_shares_path_csv),
        "winner12_combo_step_metrics_baseline_parquet": str(_m_combo_step_path_parquet),
        "winner12_combo_step_metrics_baseline_csv": str(_m_combo_step_path_csv),
        "winner12_combo_pairwise_agreement_baseline_parquet": str(
            _m_pairwise_path_parquet
        ),
        "winner12_combo_pairwise_agreement_baseline_csv": str(_m_pairwise_path_csv),
        "winner12_combo_pairwise_agreement_stepwise_parquet": str(
            _m_pairwise_step_path_parquet
        ),
        "winner12_combo_pairwise_agreement_stepwise_csv": str(
            _m_pairwise_step_path_csv
        ),
        "winner12_step_difficulty_baseline_parquet": str(
            _m_step_difficulty_path_parquet
        ),
        "winner12_step_difficulty_baseline_csv": str(_m_step_difficulty_path_csv),
        "winner12_worst_steps_by_accuracy_parquet": str(_m_worst_steps_path_parquet),
        "winner12_worst_steps_by_accuracy_csv": str(_m_worst_steps_path_csv),
        "winner12_worst_rolling_windows_by_accuracy_parquet": str(
            _m_worst_windows_path_parquet
        ),
        "winner12_worst_rolling_windows_by_accuracy_csv": str(
            _m_worst_windows_path_csv
        ),
        "winner12_combo_accuracy_correlation_parquet": str(_m_combo_corr_path_parquet),
        "winner12_combo_accuracy_correlation_csv": str(_m_combo_corr_path_csv),
        "winner12_threshold_agreement_parquet": str(
            _m_threshold_agreement_path_parquet
        ),
        "winner12_threshold_agreement_csv": str(_m_threshold_agreement_path_csv),
    },
    "created_at": datetime.now().isoformat(),
}
with open(_m_summary_path, "w") as f:
    json.dump(_m_summary, f, indent=2)

print("\nSaved:")
print(f"  {_m_pred_dedup_path}")
print(f"  {_m_combo_cov_path_parquet}")
print(f"  {_m_combo_weights_path_parquet}")
print(f"  {_m_row_signals_path_parquet}")
print(f"  {_m_batch_signals_path_parquet}")
print(f"  {_m_batch_calib_path_parquet}")
print(f"  {_m_deciles_path_parquet}")
print(f"  {_m_shares_path_parquet}")
print(f"  {_m_combo_step_path_parquet}")
print(f"  {_m_pairwise_path_parquet}")
print(f"  {_m_pairwise_step_path_parquet}")
print(f"  {_m_step_difficulty_path_parquet}")
print(f"  {_m_worst_steps_path_parquet}")
print(f"  {_m_worst_windows_path_parquet}")
print(f"  {_m_combo_corr_path_parquet}")
print(f"  {_m_threshold_agreement_path_parquet}")
print(f"  {_m_summary_path}")

# %%
# ============================================================================
# CELL 14D: BAD-REGIME RISK FILTER DESIGN (LIVE-STYLE, NO WINNER KNOWLEDGE)
# ============================================================================

import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import polars as pl

# Standalone-safe bootstrap (so Cell 14D can run independently).
if "PROJECT_ROOT" not in dir():
    PROJECT_ROOT = Path("/media/przem/linux_data/RiskYieldMM (Copy)")
else:
    PROJECT_ROOT = Path(PROJECT_ROOT)

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

STAGE1_RISK_FILTER_RUN_ID = "stage1_catboost_live"
STAGE1_RISK_FILTER_UNIT = "1m/target_4class"
STAGE1_RISK_FILTER_BAD_THRESHOLD = 0.30
STAGE1_RISK_FILTER_SCORE_COL = "risk_score_calibrated"
STAGE1_RISK_FILTER_GRID_MIN = 0.05
STAGE1_RISK_FILTER_GRID_MAX = 0.95
STAGE1_RISK_FILTER_GRID_STEP = 0.005
STAGE1_RISK_FILTER_MIN_RECALL = 0.35
STAGE1_RISK_FILTER_MAX_FLAGGED_RATE = 0.35
STAGE1_RISK_FILTER_HOLDOUT_STEPS = 200
STAGE1_RISK_FILTER_WF_WARMUP_STEPS = 120
STAGE1_RISK_FILTER_WF_RETRAIN_EVERY_STEPS = 1


def _rf_div(num: float, den: float) -> float:
    return float(num / den) if float(den) > 0.0 else 0.0


def _rf_metrics_from_arrays(y_true: np.ndarray, y_pred_bad: np.ndarray) -> dict:
    y_true = y_true.astype(np.int32, copy=False)
    y_pred_bad = y_pred_bad.astype(np.int32, copy=False)
    tp = int(np.sum((y_true == 1) & (y_pred_bad == 1)))
    fp = int(np.sum((y_true == 0) & (y_pred_bad == 1)))
    tn = int(np.sum((y_true == 0) & (y_pred_bad == 0)))
    fn = int(np.sum((y_true == 1) & (y_pred_bad == 0)))
    precision = _rf_div(tp, tp + fp)
    recall = _rf_div(tp, tp + fn)
    f1 = _rf_div(2.0 * precision * recall, precision + recall)
    flagged_rate = _rf_div(tp + fp, len(y_true))
    base_bad_rate = float(np.mean(y_true == 1))
    false_alarm_rate = _rf_div(fp, fp + tn)
    kept_share = 1.0 - flagged_rate
    kept_bad_rate = _rf_div(fn, fn + tn)
    precision_lift_vs_base = (
        _rf_div(precision, base_bad_rate) if base_bad_rate > 0 else 0.0
    )
    return {
        "rows": int(len(y_true)),
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "precision": float(precision),
        "recall": float(recall),
        "f1": float(f1),
        "flagged_rate": float(flagged_rate),
        "base_bad_rate": float(base_bad_rate),
        "false_alarm_rate": float(false_alarm_rate),
        "kept_share": float(kept_share),
        "kept_bad_rate": float(kept_bad_rate),
        "precision_lift_vs_base": float(precision_lift_vs_base),
    }


def _rf_eval_threshold_grid(
    scores: np.ndarray, labels_bad: np.ndarray, thresholds: np.ndarray
) -> pl.DataFrame:
    scores = scores.astype(np.float64, copy=False)
    labels_bad = labels_bad.astype(np.int32, copy=False)
    thresholds = thresholds.astype(np.float64, copy=False)
    pred_bad = scores[:, None] >= thresholds[None, :]
    y_bad = (labels_bad == 1)[:, None]
    y_good = ~y_bad
    tp = np.sum(pred_bad & y_bad, axis=0).astype(np.int32, copy=False)
    fp = np.sum(pred_bad & y_good, axis=0).astype(np.int32, copy=False)
    fn = np.sum((~pred_bad) & y_bad, axis=0).astype(np.int32, copy=False)
    tn = np.sum((~pred_bad) & y_good, axis=0).astype(np.int32, copy=False)

    precision = np.divide(
        tp, tp + fp, out=np.zeros_like(tp, dtype=np.float64), where=(tp + fp) > 0
    )
    recall = np.divide(
        tp, tp + fn, out=np.zeros_like(tp, dtype=np.float64), where=(tp + fn) > 0
    )
    f1 = np.divide(
        2.0 * precision * recall,
        precision + recall,
        out=np.zeros_like(precision, dtype=np.float64),
        where=(precision + recall) > 0,
    )
    flagged_rate = (tp + fp) / max(1, len(scores))
    false_alarm_rate = np.divide(
        fp, fp + tn, out=np.zeros_like(fp, dtype=np.float64), where=(fp + tn) > 0
    )
    kept_bad_rate = np.divide(
        fn, fn + tn, out=np.zeros_like(fn, dtype=np.float64), where=(fn + tn) > 0
    )
    base_bad_rate = float(np.mean(labels_bad == 1))
    precision_lift = np.divide(
        precision,
        base_bad_rate if base_bad_rate > 0 else 1.0,
        out=np.zeros_like(precision, dtype=np.float64),
        where=base_bad_rate > 0,
    )

    return pl.DataFrame(
        {
            "threshold": thresholds,
            "tp": tp,
            "fp": fp,
            "tn": tn,
            "fn": fn,
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "flagged_rate": flagged_rate,
            "false_alarm_rate": false_alarm_rate,
            "kept_bad_rate": kept_bad_rate,
            "base_bad_rate": np.full_like(precision, base_bad_rate),
            "precision_lift_vs_base": precision_lift,
        }
    )


def _rf_select_operating_point(
    grid_df: pl.DataFrame,
    min_recall: float,
    max_flagged_rate: float,
) -> dict:
    feasible = grid_df.filter(
        (pl.col("recall") >= float(min_recall))
        & (pl.col("flagged_rate") <= float(max_flagged_rate))
    )
    constraints_relaxed = False
    if feasible.is_empty():
        constraints_relaxed = True
        feasible = grid_df

    best = feasible.sort(
        ["f1", "precision", "recall", "flagged_rate", "threshold"],
        descending=[True, True, True, False, False],
    ).head(1)
    row = best.to_dicts()[0]
    row["constraints_relaxed"] = bool(constraints_relaxed)
    return row


_rf_tf, _rf_target = STAGE1_RISK_FILTER_UNIT.split("/", 1)
_rf_unit_dir = (
    PROJECT_ROOT
    / "data"
    / "htf_backtest_results"
    / STAGE1_RISK_FILTER_RUN_ID
    / "catboost"
    / _rf_tf
    / _rf_target
)
if not _rf_unit_dir.exists():
    raise FileNotFoundError(f"Unit directory not found: {_rf_unit_dir}")

if "stage1_combo_match_artifact_dir" in dir():
    _rf_source_dir = Path(stage1_combo_match_artifact_dir)
else:
    _rf_runs = sorted(
        [p for p in (_rf_unit_dir / "combo_match_analysis").glob("*") if p.is_dir()]
    )
    if not _rf_runs:
        raise FileNotFoundError(
            "No combo_match_analysis runs found. Run Cell 14C first."
        )
    _rf_source_dir = _rf_runs[-1]

_rf_batch_path = _rf_source_dir / "winner12_batch_consensus_signals.parquet"
if not _rf_batch_path.exists():
    raise FileNotFoundError(
        f"Batch consensus signals not found: {_rf_batch_path}. Run Cell 14C first."
    )

stage1_risk_filter_batch_df = pl.read_parquet(_rf_batch_path).sort("pred_batch")
if STAGE1_RISK_FILTER_SCORE_COL not in stage1_risk_filter_batch_df.columns:
    raise ValueError(
        f"Score column '{STAGE1_RISK_FILTER_SCORE_COL}' is missing in {_rf_batch_path.name}"
    )
if "winner_accuracy" not in stage1_risk_filter_batch_df.columns:
    raise ValueError("winner_accuracy column is required in batch consensus table")
if "is_bad_regime" not in stage1_risk_filter_batch_df.columns:
    stage1_risk_filter_batch_df = stage1_risk_filter_batch_df.with_columns(
        (pl.col("winner_accuracy") <= float(STAGE1_RISK_FILTER_BAD_THRESHOLD)).alias(
            "is_bad_regime"
        )
    )

_rf_scores = (
    stage1_risk_filter_batch_df[STAGE1_RISK_FILTER_SCORE_COL]
    .to_numpy()
    .astype(np.float64, copy=False)
)
_rf_labels = (
    stage1_risk_filter_batch_df["is_bad_regime"]
    .cast(pl.Int8)
    .to_numpy()
    .astype(np.int32, copy=False)
)
_rf_pred_batches = (
    stage1_risk_filter_batch_df["pred_batch"].to_numpy().astype(np.int32, copy=False)
)
_rf_rows = int(len(_rf_scores))
if _rf_rows < 50:
    raise ValueError(f"Too few rows for risk filter calibration: {_rf_rows}")

_rf_thresholds = np.arange(
    float(STAGE1_RISK_FILTER_GRID_MIN),
    float(STAGE1_RISK_FILTER_GRID_MAX) + float(STAGE1_RISK_FILTER_GRID_STEP) * 0.5,
    float(STAGE1_RISK_FILTER_GRID_STEP),
    dtype=np.float64,
)
if _rf_thresholds.size < 2:
    raise ValueError("Threshold grid is empty; check min/max/step settings")

_rf_holdout = int(max(1, STAGE1_RISK_FILTER_HOLDOUT_STEPS))
if _rf_rows <= _rf_holdout:
    raise ValueError(f"Holdout ({_rf_holdout}) must be smaller than rows ({_rf_rows})")
_rf_split_idx = int(_rf_rows - _rf_holdout)
_rf_train_scores = _rf_scores[:_rf_split_idx]
_rf_train_labels = _rf_labels[:_rf_split_idx]
_rf_test_scores = _rf_scores[_rf_split_idx:]
_rf_test_labels = _rf_labels[_rf_split_idx:]
_rf_test_batches = _rf_pred_batches[_rf_split_idx:]

stage1_risk_filter_grid_train_df = _rf_eval_threshold_grid(
    scores=_rf_train_scores,
    labels_bad=_rf_train_labels,
    thresholds=_rf_thresholds,
).sort("threshold")
stage1_risk_filter_grid_test_df = _rf_eval_threshold_grid(
    scores=_rf_test_scores,
    labels_bad=_rf_test_labels,
    thresholds=_rf_thresholds,
).sort("threshold")

_rf_selected = _rf_select_operating_point(
    grid_df=stage1_risk_filter_grid_train_df,
    min_recall=float(STAGE1_RISK_FILTER_MIN_RECALL),
    max_flagged_rate=float(STAGE1_RISK_FILTER_MAX_FLAGGED_RATE),
)
_rf_threshold_selected = float(_rf_selected["threshold"])

_rf_test_pred_bad = (_rf_test_scores >= _rf_threshold_selected).astype(
    np.int32, copy=False
)
_rf_test_metrics = _rf_metrics_from_arrays(_rf_test_labels, _rf_test_pred_bad)

stage1_risk_filter_test_predictions_df = pl.DataFrame(
    {
        "pred_batch": _rf_test_batches.astype(np.int32, copy=False),
        "score": _rf_test_scores.astype(np.float64, copy=False),
        "is_bad_regime": _rf_test_labels.astype(np.int32, copy=False),
        "pred_bad_regime_static": _rf_test_pred_bad.astype(np.int32, copy=False),
        "threshold_used_static": np.full_like(
            _rf_test_scores, _rf_threshold_selected, dtype=np.float64
        ),
    }
)

# Walk-forward simulation (expanding window, strict no-lookahead).
_rf_wf_warmup = int(STAGE1_RISK_FILTER_WF_WARMUP_STEPS)
if _rf_wf_warmup < 20:
    raise ValueError("STAGE1_RISK_FILTER_WF_WARMUP_STEPS must be >= 20")
if _rf_wf_warmup >= _rf_rows:
    raise ValueError("STAGE1_RISK_FILTER_WF_WARMUP_STEPS must be < number of rows")
_rf_retrain_every = int(max(1, STAGE1_RISK_FILTER_WF_RETRAIN_EVERY_STEPS))

_rf_wf_rows = []
_rf_curr_threshold = _rf_threshold_selected
for _i in range(_rf_wf_warmup, _rf_rows):
    if (_i == _rf_wf_warmup) or (((_i - _rf_wf_warmup) % _rf_retrain_every) == 0):
        _train_scores_i = _rf_scores[:_i]
        _train_labels_i = _rf_labels[:_i]
        _grid_i = _rf_eval_threshold_grid(
            scores=_train_scores_i,
            labels_bad=_train_labels_i,
            thresholds=_rf_thresholds,
        )
        _sel_i = _rf_select_operating_point(
            grid_df=_grid_i,
            min_recall=float(STAGE1_RISK_FILTER_MIN_RECALL),
            max_flagged_rate=float(STAGE1_RISK_FILTER_MAX_FLAGGED_RATE),
        )
        _rf_curr_threshold = float(_sel_i["threshold"])
        _rf_constraints_relaxed = bool(_sel_i["constraints_relaxed"])
        _rf_train_f1 = float(_sel_i["f1"])
    _score_i = float(_rf_scores[_i])
    _y_i = int(_rf_labels[_i])
    _pred_i = int(_score_i >= _rf_curr_threshold)
    _rf_wf_rows.append(
        {
            "pred_batch": int(_rf_pred_batches[_i]),
            "wf_step_idx": int(_i + 1),
            "score": float(_score_i),
            "is_bad_regime": int(_y_i),
            "pred_bad_regime_wf": int(_pred_i),
            "threshold_used_wf": float(_rf_curr_threshold),
            "train_rows_used": int(_i),
            "train_selected_f1": float(_rf_train_f1),
            "constraints_relaxed": bool(_rf_constraints_relaxed),
        }
    )

stage1_risk_filter_wf_predictions_df = pl.DataFrame(_rf_wf_rows).sort("pred_batch")
_rf_wf_metrics = _rf_metrics_from_arrays(
    stage1_risk_filter_wf_predictions_df["is_bad_regime"]
    .to_numpy()
    .astype(np.int32, copy=False),
    stage1_risk_filter_wf_predictions_df["pred_bad_regime_wf"]
    .to_numpy()
    .astype(np.int32, copy=False),
)

stage1_risk_filter_operating_points_df = pl.DataFrame(
    [
        {
            "mode": "train_selected_static_threshold",
            "threshold": float(_rf_threshold_selected),
            "constraints_relaxed": bool(_rf_selected["constraints_relaxed"]),
            "train_precision": float(_rf_selected["precision"]),
            "train_recall": float(_rf_selected["recall"]),
            "train_f1": float(_rf_selected["f1"]),
            "train_flagged_rate": float(_rf_selected["flagged_rate"]),
        },
        {
            "mode": "test_metrics_at_static_threshold",
            "threshold": float(_rf_threshold_selected),
            "constraints_relaxed": bool(_rf_selected["constraints_relaxed"]),
            "test_precision": float(_rf_test_metrics["precision"]),
            "test_recall": float(_rf_test_metrics["recall"]),
            "test_f1": float(_rf_test_metrics["f1"]),
            "test_flagged_rate": float(_rf_test_metrics["flagged_rate"]),
        },
        {
            "mode": "walkforward_expanding_window",
            "threshold": None,
            "constraints_relaxed": None,
            "wf_precision": float(_rf_wf_metrics["precision"]),
            "wf_recall": float(_rf_wf_metrics["recall"]),
            "wf_f1": float(_rf_wf_metrics["f1"]),
            "wf_flagged_rate": float(_rf_wf_metrics["flagged_rate"]),
        },
    ],
    strict=False,
)

print("Risk filter build summary")
print(f"  Source: {_rf_batch_path}")
print(f"  Steps: {_rf_rows}, train={_rf_split_idx}, holdout={_rf_holdout}")
print(f"  Base bad-regime rate: {float(np.mean(_rf_labels == 1)):.4f}")
print(f"  Score column: {STAGE1_RISK_FILTER_SCORE_COL}")
print(
    "  Selected static threshold: "
    f"{_rf_threshold_selected:.3f} "
    f"(constraints_relaxed={bool(_rf_selected['constraints_relaxed'])})"
)
print(
    "  Holdout metrics @ static threshold: "
    f"precision={_rf_test_metrics['precision']:.4f}, "
    f"recall={_rf_test_metrics['recall']:.4f}, "
    f"f1={_rf_test_metrics['f1']:.4f}, "
    f"flagged_rate={_rf_test_metrics['flagged_rate']:.4f}, "
    f"kept_bad_rate={_rf_test_metrics['kept_bad_rate']:.4f}, "
    f"lift={_rf_test_metrics['precision_lift_vs_base']:.3f}"
)
print(
    "  Walk-forward metrics (future-style): "
    f"precision={_rf_wf_metrics['precision']:.4f}, "
    f"recall={_rf_wf_metrics['recall']:.4f}, "
    f"f1={_rf_wf_metrics['f1']:.4f}, "
    f"flagged_rate={_rf_wf_metrics['flagged_rate']:.4f}, "
    f"kept_bad_rate={_rf_wf_metrics['kept_bad_rate']:.4f}, "
    f"lift={_rf_wf_metrics['precision_lift_vs_base']:.3f}"
)
print("\nTop 10 train thresholds by F1:")
print(
    stage1_risk_filter_grid_train_df.sort(
        ["f1", "precision", "recall"], descending=[True, True, True]
    )
    .head(10)
    .select(
        [
            "threshold",
            "precision",
            "recall",
            "f1",
            "flagged_rate",
            "kept_bad_rate",
            "precision_lift_vs_base",
        ]
    )
)

stage1_risk_filter_artifact_dir = (
    _rf_source_dir / "risk_filter" / datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
)
stage1_risk_filter_artifact_dir.mkdir(parents=True, exist_ok=True)

stage1_risk_filter_grid_train_path_parquet = (
    stage1_risk_filter_artifact_dir / "risk_filter_threshold_grid_train.parquet"
)
stage1_risk_filter_grid_train_path_csv = (
    stage1_risk_filter_artifact_dir / "risk_filter_threshold_grid_train.csv"
)
stage1_risk_filter_grid_test_path_parquet = (
    stage1_risk_filter_artifact_dir / "risk_filter_threshold_grid_test.parquet"
)
stage1_risk_filter_grid_test_path_csv = (
    stage1_risk_filter_artifact_dir / "risk_filter_threshold_grid_test.csv"
)
stage1_risk_filter_operating_points_path_parquet = (
    stage1_risk_filter_artifact_dir / "risk_filter_operating_points.parquet"
)
stage1_risk_filter_operating_points_path_csv = (
    stage1_risk_filter_artifact_dir / "risk_filter_operating_points.csv"
)
stage1_risk_filter_test_predictions_path_parquet = (
    stage1_risk_filter_artifact_dir / "risk_filter_test_predictions.parquet"
)
stage1_risk_filter_test_predictions_path_csv = (
    stage1_risk_filter_artifact_dir / "risk_filter_test_predictions.csv"
)
stage1_risk_filter_wf_predictions_path_parquet = (
    stage1_risk_filter_artifact_dir / "risk_filter_walkforward_predictions.parquet"
)
stage1_risk_filter_wf_predictions_path_csv = (
    stage1_risk_filter_artifact_dir / "risk_filter_walkforward_predictions.csv"
)
stage1_risk_filter_summary_path = (
    stage1_risk_filter_artifact_dir / "risk_filter_summary.json"
)

stage1_risk_filter_grid_train_df.write_parquet(
    stage1_risk_filter_grid_train_path_parquet
)
stage1_risk_filter_grid_train_df.write_csv(stage1_risk_filter_grid_train_path_csv)
stage1_risk_filter_grid_test_df.write_parquet(stage1_risk_filter_grid_test_path_parquet)
stage1_risk_filter_grid_test_df.write_csv(stage1_risk_filter_grid_test_path_csv)
stage1_risk_filter_operating_points_df.write_parquet(
    stage1_risk_filter_operating_points_path_parquet
)
stage1_risk_filter_operating_points_df.write_csv(
    stage1_risk_filter_operating_points_path_csv
)
stage1_risk_filter_test_predictions_df.write_parquet(
    stage1_risk_filter_test_predictions_path_parquet
)
stage1_risk_filter_test_predictions_df.write_csv(
    stage1_risk_filter_test_predictions_path_csv
)
stage1_risk_filter_wf_predictions_df.write_parquet(
    stage1_risk_filter_wf_predictions_path_parquet
)
stage1_risk_filter_wf_predictions_df.write_csv(
    stage1_risk_filter_wf_predictions_path_csv
)

_rf_summary = {
    "run_id": STAGE1_RISK_FILTER_RUN_ID,
    "unit": STAGE1_RISK_FILTER_UNIT,
    "source_batch_file": str(_rf_batch_path),
    "config": {
        "bad_threshold": float(STAGE1_RISK_FILTER_BAD_THRESHOLD),
        "score_col": STAGE1_RISK_FILTER_SCORE_COL,
        "grid_min": float(STAGE1_RISK_FILTER_GRID_MIN),
        "grid_max": float(STAGE1_RISK_FILTER_GRID_MAX),
        "grid_step": float(STAGE1_RISK_FILTER_GRID_STEP),
        "min_recall": float(STAGE1_RISK_FILTER_MIN_RECALL),
        "max_flagged_rate": float(STAGE1_RISK_FILTER_MAX_FLAGGED_RATE),
        "holdout_steps": int(STAGE1_RISK_FILTER_HOLDOUT_STEPS),
        "wf_warmup_steps": int(STAGE1_RISK_FILTER_WF_WARMUP_STEPS),
        "wf_retrain_every_steps": int(STAGE1_RISK_FILTER_WF_RETRAIN_EVERY_STEPS),
    },
    "rows": {
        "total_steps": int(_rf_rows),
        "train_steps": int(_rf_split_idx),
        "holdout_steps": int(_rf_holdout),
        "walkforward_steps": int(len(stage1_risk_filter_wf_predictions_df)),
        "base_bad_rate": float(np.mean(_rf_labels == 1)),
    },
    "selected_static_threshold": {
        "threshold": float(_rf_threshold_selected),
        "constraints_relaxed": bool(_rf_selected["constraints_relaxed"]),
        "train_metrics": {
            "precision": float(_rf_selected["precision"]),
            "recall": float(_rf_selected["recall"]),
            "f1": float(_rf_selected["f1"]),
            "flagged_rate": float(_rf_selected["flagged_rate"]),
        },
    },
    "holdout_metrics_static_threshold": _rf_test_metrics,
    "walkforward_metrics": _rf_wf_metrics,
    "artifacts": {
        "risk_filter_threshold_grid_train_parquet": str(
            stage1_risk_filter_grid_train_path_parquet
        ),
        "risk_filter_threshold_grid_train_csv": str(
            stage1_risk_filter_grid_train_path_csv
        ),
        "risk_filter_threshold_grid_test_parquet": str(
            stage1_risk_filter_grid_test_path_parquet
        ),
        "risk_filter_threshold_grid_test_csv": str(
            stage1_risk_filter_grid_test_path_csv
        ),
        "risk_filter_operating_points_parquet": str(
            stage1_risk_filter_operating_points_path_parquet
        ),
        "risk_filter_operating_points_csv": str(
            stage1_risk_filter_operating_points_path_csv
        ),
        "risk_filter_test_predictions_parquet": str(
            stage1_risk_filter_test_predictions_path_parquet
        ),
        "risk_filter_test_predictions_csv": str(
            stage1_risk_filter_test_predictions_path_csv
        ),
        "risk_filter_walkforward_predictions_parquet": str(
            stage1_risk_filter_wf_predictions_path_parquet
        ),
        "risk_filter_walkforward_predictions_csv": str(
            stage1_risk_filter_wf_predictions_path_csv
        ),
    },
    "created_at": datetime.now().isoformat(),
}
with open(stage1_risk_filter_summary_path, "w") as f:
    json.dump(_rf_summary, f, indent=2)

print("\nSaved:")
print(f"  {stage1_risk_filter_grid_train_path_parquet}")
print(f"  {stage1_risk_filter_grid_test_path_parquet}")
print(f"  {stage1_risk_filter_operating_points_path_parquet}")
print(f"  {stage1_risk_filter_test_predictions_path_parquet}")
print(f"  {stage1_risk_filter_wf_predictions_path_parquet}")
print(f"  {stage1_risk_filter_summary_path}")

# %%
# ============================================================================
# CELL 14E: CORRELATION-BASED BAD-REGIME DETECTOR (CATBOOST, LIVE-SAFE)
# ============================================================================
import sys
from pathlib import Path

import polars as pl

if "PROJECT_ROOT" not in dir():
    PROJECT_ROOT = Path("/media/przem/linux_data/RiskYieldMM (Copy)")
else:
    PROJECT_ROOT = Path(PROJECT_ROOT)

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Force fresh risk-model module load in notebook sessions (avoid stale signature).
importlib.invalidate_caches()
for _m in list(sys.modules.keys()):
    if _m.startswith("scripts.htf_backtest.catboost.htf_riskmodel"):
        del sys.modules[_m]

from scripts.htf_backtest.catboost.htf_riskmodel import (
    run_stage1_correlation_risk_model,
)

STAGE1_RISKMODEL_RUN_ID = "stage1_catboost_live"
STAGE1_RISKMODEL_UNIT = "1m/target_4class"
# Primary threshold for backward-compatibility outputs.
STAGE1_RISKMODEL_BAD_THRESHOLD = 0.30
STAGE1_RISKMODEL_BAD_CONDITION = "le"  # le => <= threshold, ge => >= threshold
# Scenario list for comparison (condition, threshold).
STAGE1_RISKMODEL_BAD_SCENARIOS = [
    ("le", 0.30),
    ("ge", 0.70),
]
STAGE1_RISKMODEL_FLAG_BUDGET = 0.20
STAGE1_RISKMODEL_HOLDOUT_STEPS = 200
STAGE1_RISKMODEL_WF_WARMUP_STEPS = 120
STAGE1_RISKMODEL_WF_RETRAIN_EVERY_STEPS = 1
STAGE1_RISKMODEL_THRESHOLD_GRID_STEP = 0.005
STAGE1_RISKMODEL_RANDOM_SEED = 42
STAGE1_RISKMODEL_USE_GPU = True
STAGE1_RISKMODEL_GPU_DEVICES = "0"
STAGE1_RISKMODEL_WF_PROGRESS_EVERY_STEPS = 10
STAGE1_RISKMODEL_FEATURE_POLICY = "strict_live_safe_v1"
STAGE1_RISKMODEL_STRICT_LEAKAGE_GUARD = True
STAGE1_RISKMODEL_SAVE_FEATURE_PROVENANCE = True
STAGE1_RISKMODEL_VERBOSE = True

_combo_match_run = (
    stage1_combo_match_artifact_dir
    if "stage1_combo_match_artifact_dir" in dir()
    else None
)

_rm_primary = (
    str(STAGE1_RISKMODEL_BAD_CONDITION).lower(),
    float(STAGE1_RISKMODEL_BAD_THRESHOLD),
)
_rm_scenarios = []
for _cond, _thr in (
    STAGE1_RISKMODEL_BAD_SCENARIOS
    if isinstance(STAGE1_RISKMODEL_BAD_SCENARIOS, (list, tuple))
    else [_rm_primary]
):
    _c = str(_cond).strip().lower()
    if _c not in {"le", "ge"}:
        raise ValueError(
            f"Invalid bad-condition in scenario: {_cond!r} (expected 'le' or 'ge')"
        )
    _rm_scenarios.append((_c, float(_thr)))
if _rm_primary not in _rm_scenarios:
    _rm_scenarios = [_rm_primary] + _rm_scenarios
# De-duplicate while preserving order.
_rm_scenarios = list(dict.fromkeys(_rm_scenarios))

results_stage1_riskmodel_by_threshold = {}
_rm_compare_rows = []
print(
    "[Stage1 RiskModel] strict live-safe feature policy enabled; "
    "do not compare directly with earlier leaky-feature runs."
)

for _bad_cond, _bad_thr in _rm_scenarios:
    _cond_label = "<=" if _bad_cond == "le" else ">="
    print(
        "\n"
        + "=" * 90
        + f"\n[Stage1 RiskModel] Running bad-condition: winner_accuracy {_cond_label} {_bad_thr:.2f}\n"
        + "=" * 90
    )
    _res = run_stage1_correlation_risk_model(
        project_root=PROJECT_ROOT,
        run_id=STAGE1_RISKMODEL_RUN_ID,
        unit=STAGE1_RISKMODEL_UNIT,
        combo_match_run_dir=_combo_match_run,
        bad_threshold=float(_bad_thr),
        bad_condition=_bad_cond,
        flag_budget=STAGE1_RISKMODEL_FLAG_BUDGET,
        holdout_steps=STAGE1_RISKMODEL_HOLDOUT_STEPS,
        wf_warmup_steps=STAGE1_RISKMODEL_WF_WARMUP_STEPS,
        wf_retrain_every_steps=STAGE1_RISKMODEL_WF_RETRAIN_EVERY_STEPS,
        threshold_grid_step=STAGE1_RISKMODEL_THRESHOLD_GRID_STEP,
        random_seed=STAGE1_RISKMODEL_RANDOM_SEED,
        use_gpu=STAGE1_RISKMODEL_USE_GPU,
        gpu_devices=STAGE1_RISKMODEL_GPU_DEVICES,
        wf_progress_every_steps=STAGE1_RISKMODEL_WF_PROGRESS_EVERY_STEPS,
        feature_policy=STAGE1_RISKMODEL_FEATURE_POLICY,
        strict_leakage_guard=STAGE1_RISKMODEL_STRICT_LEAKAGE_GUARD,
        save_feature_provenance=STAGE1_RISKMODEL_SAVE_FEATURE_PROVENANCE,
        verbose=STAGE1_RISKMODEL_VERBOSE,
    )
    _scenario_key = f"{_bad_cond}:{float(_bad_thr):.6f}"
    results_stage1_riskmodel_by_threshold[_scenario_key] = _res

    _sum = _res["summary"]
    _h = _sum["metrics"]["holdout"]
    _w = _sum["metrics"]["walkforward"]
    _rm_compare_rows.append(
        {
            "bad_condition": _bad_cond,
            "bad_threshold": float(_bad_thr),
            "selected_threshold": float(_sum["selected_threshold"]),
            "holdout_precision": float(_h["precision"]),
            "holdout_recall": float(_h["recall"]),
            "holdout_f1": float(_h["f1"]),
            "holdout_flagged_rate": float(_h["flagged_rate"]),
            "holdout_auc": None if _h["auc"] is None else float(_h["auc"]),
            "holdout_pr_auc": None if _h["pr_auc"] is None else float(_h["pr_auc"]),
            "wf_precision": float(_w["precision"]),
            "wf_recall": float(_w["recall"]),
            "wf_f1": float(_w["f1"]),
            "wf_flagged_rate": float(_w["flagged_rate"]),
            "wf_auc": None if _w["auc"] is None else float(_w["auc"]),
            "wf_pr_auc": None if _w["pr_auc"] is None else float(_w["pr_auc"]),
            "feature_count": int(_sum["features"]["count"]),
            "dropped_feature_count": int(_sum["features"]["feature_counts"]["dropped"]),
            "leakage_guard_passed": bool(_sum["features"]["leakage_guard_passed"]),
            "split_monotonic": bool(
                _sum["temporal_integrity_checks"]["train_holdout_split_monotonic"]
            ),
            "wf_idx_alignment": bool(
                _sum["temporal_integrity_checks"]["walkforward_idx_alignment_all_zero"]
            ),
            "summary_json": _sum["artifacts"]["risk_model_summary_json"],
        }
    )

results_stage1_riskmodel = results_stage1_riskmodel_by_threshold[
    f"{_rm_primary[0]}:{_rm_primary[1]:.6f}"
]
_rm_summary = results_stage1_riskmodel["summary"]
_rm_holdout = _rm_summary["metrics"]["holdout"]
_rm_wf = _rm_summary["metrics"]["walkforward"]

stage1_riskmodel_threshold_comparison_df = pl.DataFrame(_rm_compare_rows).sort(
    ["bad_condition", "bad_threshold"]
)

print("\nStage1 RiskModel threshold comparison:")
print(stage1_riskmodel_threshold_comparison_df)

print("\nPrimary threshold summary:")
print(
    f"  Bad condition: {_rm_summary['config']['bad_condition']} "
    f"(winner_accuracy {'<=' if _rm_summary['config']['bad_condition'] == 'le' else '>='} "
    f"{float(_rm_summary['config']['bad_threshold']):.2f}) | "
    f"Selected threshold: {_rm_summary['selected_threshold']:.6f} "
    f"(budget={_rm_summary['config']['flag_budget']:.2f}, "
    f"relaxed={_rm_summary['threshold_selection']['constraints_relaxed']})"
)
print(
    "  Feature policy: "
    f"{_rm_summary['config']['feature_policy']} | "
    f"selected={_rm_summary['features']['feature_counts']['allowed']}, "
    f"dropped={_rm_summary['features']['feature_counts']['dropped']}, "
    f"leakage_guard_passed={_rm_summary['features']['leakage_guard_passed']}"
)
print(f"  Dropped by reason: {_rm_summary['features']['dropped_by_reason']}")
print(
    "  Temporal checks: "
    f"split_monotonic={_rm_summary['temporal_integrity_checks']['train_holdout_split_monotonic']}, "
    f"wf_idx_alignment={_rm_summary['temporal_integrity_checks']['walkforward_idx_alignment_all_zero']}"
)
print(
    "  Fit backend: "
    f"requested={_rm_summary['fit_runtime']['static_fit']['task_type_requested']}, "
    f"used={_rm_summary['fit_runtime']['static_fit']['task_type_used']}, "
    f"gpu_fallback={_rm_summary['fit_runtime']['static_fit']['gpu_fallback']}"
)
print(
    "  Holdout: "
    f"precision={_rm_holdout['precision']:.4f}, "
    f"recall={_rm_holdout['recall']:.4f}, "
    f"f1={_rm_holdout['f1']:.4f}, "
    f"flagged_rate={_rm_holdout['flagged_rate']:.4f}, "
    f"kept_bad_rate={_rm_holdout['kept_bad_rate']:.4f}, "
    f"lift={_rm_holdout['precision_lift_vs_base']:.3f}, "
    f"auc={_rm_holdout['auc']}, pr_auc={_rm_holdout['pr_auc']}"
)
print(
    "  Walk-forward: "
    f"precision={_rm_wf['precision']:.4f}, "
    f"recall={_rm_wf['recall']:.4f}, "
    f"f1={_rm_wf['f1']:.4f}, "
    f"flagged_rate={_rm_wf['flagged_rate']:.4f}, "
    f"kept_bad_rate={_rm_wf['kept_bad_rate']:.4f}, "
    f"lift={_rm_wf['precision_lift_vs_base']:.3f}, "
    f"auc={_rm_wf['auc']}, pr_auc={_rm_wf['pr_auc']}"
)

print("\nTop feature importances (primary threshold):")
print(results_stage1_riskmodel["feature_importance_top"][:15])

print("\nArtifacts (primary threshold):")
for _k, _v in results_stage1_riskmodel["artifacts"].items():
    print(f"  {_k}: {_v}")

# %%
