"""
CatBoost Stage-1 Runner (Isolated)
==================================

Dedicated walk-forward Stage-1 runner:
- exhaustive fold grid only
- raw payload artifacts only
- no standard Optuna/final-model prediction reporting path
"""

from __future__ import annotations

import json
import time
from collections import defaultdict
from dataclasses import asdict, replace
from datetime import datetime
from pathlib import Path
from typing import Any

import polars as pl

from .stage1_optimizer import build_stage1_combo_grid, evaluate_stage1_grid
from .utils import compute_label_distribution, get_valid_batches


def run_walk_forward_stage1_grid(
    n_steps: int | None = None,
    timeframes: list[str] | None = None,
    run_description: str = "Stage-1 fold-grid dataset generation (CatBoost)",
    verbose: bool = True,
    debug_batches: bool = False,
    optuna_overrides: dict | None = None,
    run_id: str | None = None,
    resume: bool = False,
    resume_mode: str = "continue",
    allow_override_mismatch: bool = False,  # kept for signature compatibility
    model_name: str = "catboost",
    optuna_overrides_by_model: dict | None = None,
    targets_by_model: dict | None = None,
    n_classes_by_model: dict | None = None,
    class_names_by_model: dict | None = None,
    feature_source_by_model: dict | None = None,
    target_registry: dict | None = None,
) -> dict:
    """Run isolated Stage-1 fold grid and store raw payload artifacts."""
    from .tf_1m import Config1m, FeatureSpace1m, ModelSpace1m, Optimizer1m, WindowSpace1m
    from .tf_5m import Config5m, FeatureSpace5m, ModelSpace5m, Optimizer5m, WindowSpace5m
    from .tf_15m import (
        Config15m,
        FeatureSpace15m,
        ModelSpace15m,
        Optimizer15m,
        WindowSpace15m,
    )

    if model_name != "catboost":
        raise ValueError(
            f"run_walk_forward_stage1_grid supports only model_name='catboost', got '{model_name}'"
        )
    if resume_mode not in {"continue", "skip_completed"}:
        raise ValueError("resume_mode must be 'continue' or 'skip_completed'")
    if resume and not run_id:
        raise ValueError("resume=True requires run_id")

    if timeframes is None:
        timeframes = ["1m", "5m", "15m"]

    stage1_print_label_distribution = False

    if optuna_overrides_by_model is not None:
        optuna_overrides = optuna_overrides_by_model.get(model_name, optuna_overrides)

    target_map = (targets_by_model or {}).get(model_name, {}) if targets_by_model else {}
    n_classes_map = (n_classes_by_model or {}).get(model_name, {}) if n_classes_by_model else {}
    class_names_map = (class_names_by_model or {}).get(model_name, {}) if class_names_by_model else {}
    feature_source_map = (
        (feature_source_by_model or {}).get(model_name, {})
        if feature_source_by_model
        else {}
    )

    def _normalize_target_list(value: Any, default_target: str) -> list[str]:
        if value is None:
            return [default_target]
        if isinstance(value, str):
            values = [value]
        elif isinstance(value, (list, tuple, set)):
            values = [str(v) for v in value if v is not None]
        else:
            raise ValueError(f"Invalid target config type: {type(value)}")
        out: list[str] = []
        for v in values:
            if v not in out:
                out.append(v)
        if not out:
            raise ValueError("Target list cannot be empty")
        return out

    def _resolve_n_classes(tf: str, target_col: str, default_n: int) -> int:
        tf_val = (n_classes_map or {}).get(tf)
        if isinstance(tf_val, dict):
            return int(tf_val.get(target_col, default_n))
        if tf_val is None:
            return int(default_n)
        return int(tf_val)

    def _resolve_class_names(
        tf: str,
        target_col: str,
        default_names: list[str],
        n_classes: int,
    ) -> list[str]:
        tf_val = (class_names_map or {}).get(tf, default_names)
        if isinstance(tf_val, dict):
            names = tf_val.get(target_col, default_names)
        else:
            names = tf_val
        names = list(names) if names else []
        if len(names) != n_classes:
            names = [f"class_{i}" for i in range(n_classes)]
        return names

    def _resolve_feature_target(tf: str, target_col: str) -> str:
        tf_val = (feature_source_map or {}).get(tf)
        if isinstance(tf_val, dict):
            return str(tf_val.get(target_col, target_col))
        if isinstance(tf_val, str):
            return tf_val
        return target_col

    override_keys = {
        "optuna_trials",
        "optuna_timeout",
        "optuna_metric",
        "exclude_tail_pct",
        "track_pred_metrics",
        "shuffle_split",
        "shuffle_seed",
        "shuffle_val_ratio",
        "shuffle_batches",
        "shuffle_batches_seed",
        "balance_strategy",
        "balance_apply_to",
        "class_weight_choices",
        "stage1_print_label_distribution",
        "cb_base_params",
        "window_space",
        "feature_space",
        "model_space",
        "stage1_validity_target_col",
    }

    def _resolve_overrides(tf: str, target_col: str) -> dict:
        tf_overrides = (optuna_overrides or {}).get(tf, {})
        if not isinstance(tf_overrides, dict):
            raise ValueError(
                f"Invalid optuna_overrides entry for tf={tf}: {type(tf_overrides)}"
            )
        if any(k in tf_overrides for k in override_keys):
            return tf_overrides
        target_overrides = tf_overrides.get(target_col, {})
        if not isinstance(target_overrides, dict):
            raise ValueError(
                f"Invalid target override for tf={tf}, target={target_col}: {type(target_overrides)}"
            )
        return target_overrides

    def _build_base_components(tf: str):
        if tf == "1m":
            cfg = Config1m()
            win = WindowSpace1m()
            feat = FeatureSpace1m()
            model = ModelSpace1m()
            opt_cls = Optimizer1m
        elif tf == "5m":
            cfg = Config5m()
            win = WindowSpace5m()
            feat = FeatureSpace5m()
            model = ModelSpace5m()
            opt_cls = Optimizer5m
        elif tf == "15m":
            cfg = Config15m()
            win = WindowSpace15m()
            feat = FeatureSpace15m()
            model = ModelSpace15m()
            opt_cls = Optimizer15m
        else:
            raise ValueError(f"Unknown timeframe: {tf}")
        return cfg, win, feat, model, opt_cls

    execution_units = []
    for tf in timeframes:
        base_cfg, _, _, _, _ = _build_base_components(tf)
        tf_targets = _normalize_target_list(target_map.get(tf), base_cfg.target)
        for target_col in tf_targets:
            cfg, win, feat, model, opt_cls = _build_base_components(tf)
            overrides = _resolve_overrides(tf, target_col)

            if "exclude_tail_pct" in overrides:
                cfg = replace(cfg, exclude_tail_pct=overrides["exclude_tail_pct"])
            if "cb_base_params" in overrides:
                merged_cb = dict(cfg.cb_base_params)
                merged_cb.update(dict(overrides["cb_base_params"]))
                cfg = replace(cfg, cb_base_params=merged_cb)
            if "window_space" in overrides:
                win = replace(win, **overrides["window_space"])
            if "feature_space" in overrides:
                feat = replace(feat, **overrides["feature_space"])
            if "model_space" in overrides:
                model = replace(model, **overrides["model_space"])
            if "stage1_print_label_distribution" in overrides:
                stage1_print_label_distribution = bool(
                    overrides["stage1_print_label_distribution"]
                )

            if str(getattr(win, "window_selection_mode", "")) != "stage1_fold_cv":
                raise ValueError(
                    f"Stage-1 runner requires window_selection_mode='stage1_fold_cv'. "
                    f"Got tf={tf}, target={target_col}, mode={getattr(win, 'window_selection_mode', None)}"
                )

            # Stage-1 validation should use a stable completeness mask.
            # Default behavior:
            # - target_4class validates against itself
            # - other targets validate against target_4class unless explicitly overridden
            validity_target_col = overrides.get("stage1_validity_target_col")
            if validity_target_col is None:
                validity_target_col = (
                    target_col if str(target_col) == "target_4class" else "target_4class"
                )
            validity_target_col = str(validity_target_col)

            feature_target_col = _resolve_feature_target(tf, target_col)
            if target_registry and target_col in target_registry:
                target_def = target_registry[target_col]
                n_classes = int(
                    target_def.get(
                        "n_classes",
                        _resolve_n_classes(tf, target_col, cfg.n_classes),
                    )
                )
                class_names = list(
                    target_def.get(
                        "class_names",
                        _resolve_class_names(
                            tf, target_col, list(cfg.class_names), n_classes
                        ),
                    )
                )
            else:
                n_classes = _resolve_n_classes(tf, target_col, cfg.n_classes)
                class_names = _resolve_class_names(
                    tf, target_col, list(cfg.class_names), n_classes
                )

            cfg = replace(
                cfg,
                target=target_col,
                feature_target=feature_target_col,
                n_classes=n_classes,
                class_names=tuple(class_names),
            )
            cfg.cb_base_params = cfg.cb_base_params.copy()
            if int(cfg.n_classes) == 2:
                cfg.cb_base_params["loss_function"] = "Logloss"
                cfg.cb_base_params["eval_metric"] = "Logloss"
            else:
                cfg.cb_base_params["loss_function"] = "MultiClass"
                cfg.cb_base_params["eval_metric"] = "MultiClass"

            optimizer = opt_cls(
                config=cfg,
                window_space=win,
                feature_space=feat,
                model_space=model,
            )
            execution_units.append(
                {
                    "tf": tf,
                    "target_col": target_col,
                    "feature_target_col": feature_target_col,
                    "validity_target_col": validity_target_col,
                    "overrides": overrides,
                    "optimizer": optimizer,
                }
            )

    if not execution_units:
        raise ValueError("No execution units were built.")

    ref_cfg = execution_units[0]["optimizer"].config
    default_run_id = f"stage1_run_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}"
    base_run_dir = ref_cfg.output_dir / (run_id or default_run_id)
    if not run_id:
        run_id = base_run_dir.name
    if resume and not base_run_dir.exists():
        raise FileNotFoundError(f"run_id not found: {base_run_dir}")

    run_config_path = base_run_dir / "run_config.json"
    if run_config_path.exists():
        with open(run_config_path, "r") as f:
            existing_run_config = json.load(f)
        existing_mode = str(existing_run_config.get("mode", ""))
        if existing_mode != "stage1_isolated_v1":
            raise ValueError(
                "run_id points to non-stage1 run. "
                f"Expected mode=stage1_isolated_v1, got mode={existing_mode!r} "
                f"for run_id={run_id}"
            )

    run_dir = base_run_dir / model_name
    run_dir.mkdir(parents=True, exist_ok=True)

    run_config = {
        "run_id": run_id,
        "model_name": model_name,
        "mode": "stage1_isolated_v1",
        "run_description": run_description,
        "timeframes": sorted({u["tf"] for u in execution_units}),
        "targets": {
            tf: sorted({u["target_col"] for u in execution_units if u["tf"] == tf})
            for tf in sorted({u["tf"] for u in execution_units})
        },
        "created_at": datetime.now().isoformat(),
    }
    with open(base_run_dir / "run_config.json", "w") as f:
        json.dump(run_config, f, indent=2)

    if verbose:
        print("=" * 100)
        print("HTF STAGE-1 WALK-FORWARD (CATBOOST, ISOLATED)")
        print("=" * 100)
        print(f"\nRun ID: {run_id}")
        print(f"Description: {run_description}")

        for unit in execution_units:
            tf = unit["tf"]
            cfg = unit["optimizer"].config
            win = unit["optimizer"].window_space
            combos = build_stage1_combo_grid(win)
            val_grid = list(getattr(win, "stage1_val_batches_grid", []) or [])
            if not val_grid:
                val_grid = [int(getattr(win, "stage1_val_batches_per_fold", 1))]
            train_mult_grid = list(getattr(win, "stage1_train_multiplier_grid", []) or [])
            train_grid = list(getattr(win, "stage1_train_batches_grid", []) or [])
            print(f"\n  {tf}/{cfg.target}:")
            if train_mult_grid:
                print(
                    "    stage1_grid: "
                    f"folds={int(win.stage1_folds_min)}-{int(win.stage1_folds_max)}, "
                    f"val_grid={val_grid}, "
                    f"train=val*x{train_mult_grid} "
                    f"(fallback_train_grid={train_grid}), "
                    f"combinations={len(combos)}"
                )
            else:
                print(
                    "    stage1_grid: "
                    f"folds={int(win.stage1_folds_min)}-{int(win.stage1_folds_max)}, "
                    f"val_grid={val_grid}, "
                    f"train_grid={train_grid}, "
                    f"combinations={len(combos)}"
                )
            if stage1_print_label_distribution:
                label_dist = compute_label_distribution(
                    cfg.labels_dir,
                    tf,
                    cfg.target,
                    exclude_tail_pct=cfg.exclude_tail_pct,
                )
                if not label_dist.is_empty():
                    print("    label_distribution:")
                    for row in label_dist.iter_rows(named=True):
                        class_idx = int(row["class_id"])
                        label_name = (
                            cfg.class_names[class_idx]
                            if 0 <= class_idx < len(cfg.class_names)
                            else f"class_{class_idx}"
                        )
                        print(
                            f"      {label_name}: {int(row['count'])} ({float(row['pct']):.1f}%)"
                        )

    valid_by_unit: dict[tuple[str, str], list[int]] = {}
    for unit in execution_units:
        tf = unit["tf"]
        cfg = unit["optimizer"].config
        validity_target_col = str(unit.get("validity_target_col") or cfg.target)
        batches = get_valid_batches(
            cfg.features_dir,
            cfg.labels_dir,
            tf,
            min_rows=None,
            target_col=cfg.target,
            feature_target_col=(cfg.feature_target or cfg.target),
            exclude_tail_pct=cfg.exclude_tail_pct,
            validity_target_col=validity_target_col,
        )
        valid_by_unit[(tf, cfg.target)] = batches
        if verbose:
            total = len(list((cfg.labels_dir / tf).glob("batch_*.parquet")))
            invalid = max(0, total - len(batches))
            validity_note = (
                ""
                if validity_target_col == cfg.target
                else f", validity_target={validity_target_col}"
            )
            print(
                f"  {tf}/{cfg.target}: {len(batches)}/{total} valid batches "
                f"({invalid} below threshold{validity_note})"
            )

    common_valid = None
    for batches in valid_by_unit.values():
        s = set(batches)
        common_valid = s if common_valid is None else (common_valid & s)
    common_valid_desc = sorted(common_valid or [], reverse=True)
    if verbose:
        print(f"  Common valid across all units: {len(common_valid_desc)} batches")

    if not common_valid_desc:
        raise ValueError("No common valid batches across execution units")

    max_lookback_min = max(int(u["optimizer"].window_space.lookback_min) for u in execution_units)
    eligible_desc = [b for b in common_valid_desc if b > max_lookback_min]
    if not eligible_desc:
        raise ValueError(
            f"No valid batches with sufficient training data. Need batch > {max_lookback_min}, have 0 valid."
        )

    max_steps = len(eligible_desc)
    if n_steps is None:
        n_steps = max_steps
    n_steps = min(int(n_steps), max_steps)
    step_batches = list(reversed(eligible_desc[:n_steps]))

    if verbose:
        print(f"\n  Running {n_steps} steps (max possible: {max_steps})")
        print("  Walk direction: oldest_to_newest")
        print(f"  First prediction batch: {step_batches[0]}")
        print(f"  Last prediction batch: {step_batches[-1]}")

    step_results: dict[str, list[dict[str, Any]]] = defaultdict(list)
    model_index_entries: list[dict[str, Any]] = []
    t_start = time.time()

    for step_idx, pred_batch in enumerate(step_batches, start=1):
        train_end = int(pred_batch) - 1
        step_t0 = time.time()
        if verbose:
            print("\n" + "#" * 80)
            print(
                f"#  STEP {step_idx}/{n_steps} | Train batches 1-{train_end} → Predict batch {pred_batch}"
            )
            print("#" * 80)

        for unit in execution_units:
            tf = unit["tf"]
            optimizer = unit["optimizer"]
            cfg = optimizer.config
            target_col = unit["target_col"]
            feature_target_col = unit["feature_target_col"]
            model_key = f"{model_name}/{tf}/{target_col}"
            safe_target = str(target_col).replace("/", "_")
            step_dir = run_dir / tf / safe_target / f"batch_{int(pred_batch):04d}"
            stage1_dir = step_dir / "stage1"
            step_dir.mkdir(parents=True, exist_ok=True)
            stage1_dir.mkdir(parents=True, exist_ok=True)
            summary_path = stage1_dir / "stage1_step_summary.json"

            try:
                if resume and resume_mode == "skip_completed" and summary_path.exists():
                    if verbose:
                        print(f"\n  {model_key}:")
                        print("    Resume: stage1 step already completed; skipping.")
                    continue

                if verbose:
                    print(f"\n  {model_key}:")
                    print("    Running isolated stage1 full-grid payload generation...")

                step_optimizer = optimizer.create_step_optimizer()
                stage1_t0 = time.time()
                result = evaluate_stage1_grid(
                    step_optimizer=step_optimizer,
                    train_end=int(train_end),
                    pred_batch=int(pred_batch),
                    step_stage1_dir=stage1_dir,
                )
                runtime = time.time() - stage1_t0

                snapshot_path = stage1_dir / "stage1_config_snapshot.json"
                with open(snapshot_path, "w") as f:
                    json.dump(result["config_snapshot"], f, indent=2, default=str)

                batch_metadata = {
                    "run_id": run_id,
                    "mode": "stage1_isolated_v1",
                    "model_name": model_name,
                    "timeframe": tf,
                    "target": target_col,
                    "feature_target": feature_target_col,
                    "pred_batch": int(pred_batch),
                    "train_end": int(train_end),
                    "step": int(step_idx),
                    "stage1_summary": result["summary"],
                    "artifacts": result["artifacts"],
                    "completed_at": datetime.now().isoformat(),
                }
                with open(step_dir / "batch_metadata.json", "w") as f:
                    json.dump(batch_metadata, f, indent=2)

                model_index_entries.append(
                    {
                        "model_name": model_name,
                        "timeframe": tf,
                        "target": target_col,
                        "feature_target": feature_target_col,
                        "pred_batch": int(pred_batch),
                        "step": int(step_idx),
                        "batch_dir": str(step_dir),
                        "stage1_summary": result["summary"],
                    }
                )

                step_results[model_key].append(
                    {
                        "step": int(step_idx),
                        "pred_batch": int(pred_batch),
                        "train_end": int(train_end),
                        "runtime_s": float(runtime),
                        "summary": result["summary"],
                    }
                )

                if verbose:
                    s = result["summary"]
                    print(
                        "    Stage1 done: "
                        f"combos={int(s['combo_count_completed'])}/{int(s['combo_count_total'])}, "
                        f"folds={int(s['fold_windows_completed'])}/{int(s['fold_windows_total'])}, "
                        f"val_rows={int(s['val_payload_rows'])}, pred_rows={int(s['pred_payload_rows'])}, "
                        f"time={runtime:.1f}s"
                    )
                    print(
                        "    Saved: stage1_step_summary.json, stage1_combo_index.parquet, "
                        "stage1_fold_windows.parquet, stage1_val_predictions.parquet, "
                        "stage1_pred_batch_predictions.parquet"
                    )
            except Exception as e:
                if verbose:
                    print(f"  {model_key}: ERROR - {e}")
                step_results[model_key].append(
                    {
                        "step": int(step_idx),
                        "pred_batch": int(pred_batch),
                        "train_end": int(train_end),
                        "error": str(e),
                    }
                )

        if verbose:
            print(f"\n  Step {step_idx} completed in {time.time() - step_t0:.1f}s")

    idx_path = base_run_dir / "run_model_index.json"
    if idx_path.exists():
        with open(idx_path, "r") as f:
            idx_data = json.load(f)
    else:
        idx_data = {"run_id": run_id, "entries": []}
    idx_data["entries"].extend(model_index_entries)
    with open(idx_path, "w") as f:
        json.dump(idx_data, f, indent=2)

    final = {
        "run_id": run_id,
        "mode": "stage1_isolated_v1",
        "model_name": model_name,
        "n_steps": int(n_steps),
        "timeframes": sorted({u["tf"] for u in execution_units}),
        "step_batches": [int(b) for b in step_batches],
        "results": {k: v for k, v in step_results.items()},
        "runtime_s": float(time.time() - t_start),
        "completed_at": datetime.now().isoformat(),
    }
    with open(base_run_dir / "run_summary.json", "w") as f:
        json.dump(final, f, indent=2)

    if verbose:
        print("\n" + "#" * 80)
        print("#  STAGE-1 SUMMARY")
        print("#" * 80)
        print(f"Run ID: {run_id}")
        print(f"Runtime: {final['runtime_s']:.1f}s")
        for key, rows in final["results"].items():
            ok = len([r for r in rows if "error" not in r])
            err = len(rows) - ok
            print(f"{key}: steps_ok={ok}, steps_error={err}")

    return final
