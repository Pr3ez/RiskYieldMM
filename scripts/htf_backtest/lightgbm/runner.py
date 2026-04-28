"""
Walk-Forward Backtest Runner
=============================

Runs walk-forward backtest for HTF LightGBM classification targets.
Supports multiple targets per timeframe with isolated artifacts/studies.
"""

import json
import time
from collections import defaultdict
from datetime import datetime
from dataclasses import replace
import hashlib
import subprocess
from pathlib import Path

import numpy as np
import polars as pl
import optuna
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    log_loss,
    precision_recall_fscore_support,
)

from .utils import (
    compute_label_distribution,
    export_study_trials,
    get_batch_count,
    get_valid_batches,
    load_batch,
    save_step_results,
    compute_directional_accuracy,
    compute_directional_precision,
    compute_directional_recall,
    compute_cross_direction_error_rate,
    compute_directional_macro_f1,
)

CLASS_NAMES = (
    "DOWN_BALANCED",
    "DOWN_CONT",
    "DOWN_VOLATILE",
    "UP_BALANCED",
    "UP_CONT",
    "UP_VOLATILE",
    "UP_REVERSAL_RISK",
    "DOWN_REVERSAL_RISK",
)

def _safe_git_info(project_root: str) -> dict:
    """Best-effort git info (commit + dirty)."""
    try:
        commit = (
            subprocess.check_output(
                ["git", "-C", project_root, "rev-parse", "HEAD"],
                stderr=subprocess.DEVNULL,
            )
            .decode()
            .strip()
        )
        dirty = (
            subprocess.check_output(
                ["git", "-C", project_root, "status", "--porcelain"],
                stderr=subprocess.DEVNULL,
            )
            .decode()
            .strip()
            != ""
        )
        return {"commit": commit, "dirty": dirty}
    except Exception:
        return {}


def _dir_signature(path: Path, pattern: str = "*.parquet") -> dict:
    """Lightweight directory signature: count + newest mtime."""
    try:
        files = list(path.glob(pattern))
        if not files:
            return {"count": 0, "latest_mtime": None}
        latest = max(f.stat().st_mtime for f in files)
        return {"count": len(files), "latest_mtime": latest}
    except Exception:
        return {"count": None, "latest_mtime": None}


def _config_signature(obj: dict) -> str:
    try:
        payload = json.dumps(obj, sort_keys=True).encode()
        return hashlib.md5(payload).hexdigest()
    except Exception:
        return ""


def _update_run_model_index(
    index_path: Path,
    run_id: str,
    model_name: str,
    timeframe: str,
    target_col: str,
    feature_target_col: str,
    pred_batch: int,
    step: int,
    batch_dir: Path,
    artifacts: dict,
) -> None:
    """Upsert a record for model/timeframe/batch into run_model_index.json."""
    entry = {
        "run_id": run_id,
        "model_name": model_name,
        "timeframe": timeframe,
        "target": target_col,
        "feature_target": feature_target_col,
        "pred_batch": int(pred_batch),
        "step": int(step),
        "batch_dir": str(batch_dir),
        "completed_at": datetime.now().isoformat(),
        "artifacts": artifacts,
    }
    data = {"run_id": run_id, "entries": []}
    if index_path.exists():
        try:
            with open(index_path, "r") as f:
                data = json.load(f)
        except Exception:
            data = {"run_id": run_id, "entries": []}

    entries = data.get("entries", [])
    replaced = False
    for i, e in enumerate(entries):
        if (
            e.get("model_name") == model_name
            and e.get("timeframe") == timeframe
            and e.get("target") == target_col
            and e.get("feature_target") == feature_target_col
            and int(e.get("pred_batch", -1)) == int(pred_batch)
        ):
            entries[i] = entry
            replaced = True
            break
    if not replaced:
        entries.append(entry)
    data["entries"] = entries

    with open(index_path, "w") as f:
        json.dump(data, f, indent=2)


def _write_batch_metadata(
    path: Path,
    run_id: str,
    model_name: str,
    timeframe: str,
    target_col: str,
    feature_target_col: str,
    pred_batch: int,
    train_end: int,
    step: int,
    batch_dir: Path,
    study_name: str,
    study_path: Path,
    start_timestamp,
    end_timestamp,
    optuna_overrides: dict,
    data_signature: dict,
    config_signature: dict,
    git_info: dict,
    metrics: dict,
    artifacts: dict,
) -> None:
    payload = {
        "run_id": run_id,
        "model_name": model_name,
        "timeframe": timeframe,
        "target": target_col,
        "feature_target": feature_target_col,
        "pred_batch": int(pred_batch),
        "train_end": int(train_end),
        "step": int(step),
        "batch_dir": str(batch_dir),
        "study_name": study_name,
        "study_db": str(study_path),
        "batch_start": str(start_timestamp),
        "batch_end": str(end_timestamp),
        "optuna_overrides": optuna_overrides,
        "config_signature": config_signature,
        "data_signature": data_signature,
        "git": git_info,
        "metrics": metrics,
        "artifacts": artifacts,
        "completed_at": datetime.now().isoformat(),
    }
    with open(path, "w") as f:
        json.dump(payload, f, indent=2)


def _format_ascii_table(
    headers: list[str],
    rows: list[list[str]],
    align: list[str] | None = None,
    row_separators: bool = False,
) -> str:
    """Render a simple ASCII table with borders."""
    align = align or ["l"] * len(headers)
    cols = list(zip(*([headers] + rows))) if rows else [headers]
    widths = [max(len(str(v)) for v in col) for col in cols]

    def fmt_cell(val: str, width: int, mode: str) -> str:
        text = str(val)
        return text.rjust(width) if mode == "r" else text.ljust(width)

    border = "+" + "+".join("-" * (w + 2) for w in widths) + "+"
    header_line = (
        "| "
        + " | ".join(fmt_cell(h, widths[i], align[i]) for i, h in enumerate(headers))
        + " |"
    )
    lines = [border, header_line, border]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                fmt_cell(row[i], widths[i], align[i]) for i in range(len(headers))
            )
            + " |"
        )
        if row_separators:
            lines.append(border)
    if not row_separators:
        lines.append(border)
    return "\n".join(lines)


def _format_class_table(
    class_names: tuple[str, ...],
    y_actual: np.ndarray,
    y_pred: np.ndarray,
    class_acc: dict[int, float],
    prec: np.ndarray,
    rec: np.ndarray,
) -> str:
    """Format per-class metrics table for console output."""
    rows: list[list[str]] = []
    for c, name in enumerate(class_names):
        actual_n = int((y_actual == c).sum())
        pred_n = int((y_pred == c).sum())
        acc = class_acc.get(c)
        acc_str = f"{acc:.0%}" if acc is not None else "-"
        prec_str = f"{prec[c]:.0%}" if actual_n > 0 or pred_n > 0 else "-"
        rec_str = f"{rec[c]:.0%}" if actual_n > 0 else "-"
        rows.append([name, str(actual_n), str(pred_n), acc_str, prec_str, rec_str])

    headers = ["Class", "Actual", "Pred", "Acc", "Prec", "Rec"]
    align = ["l", "r", "r", "r", "r", "r"]
    return _format_ascii_table(headers, rows, align=align, row_separators=True)


def _to_class_proba_and_pred(raw_pred: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Normalize LightGBM prediction output to class probabilities + class ids."""
    pred = np.asarray(raw_pred)
    if pred.ndim == 1:
        pred_pos = np.clip(pred, 1e-9, 1.0 - 1e-9)
        proba = np.column_stack([1.0 - pred_pos, pred_pos])
        y_pred = (pred_pos >= 0.5).astype(int)
        return proba, y_pred
    proba = pred
    y_pred = proba.argmax(axis=1)
    return proba, y_pred


def _format_confusion_table(
    class_names: tuple[str, ...],
    conf: np.ndarray,
) -> str:
    """Format confusion matrix as ASCII table with signed total percentages.

    Each cell shows % of all predictions. Diagonal cells are prefixed with "+"
    (correct), off-diagonal with "-" (incorrect).
    """
    n = len(class_names)
    headers = ["Actual \\ Pred"] + list(class_names)
    rows: list[list[str]] = []
    total = int(conf.sum())
    for i in range(n):
        row_cells = []
        for j in range(n):
            if total == 0:
                cell = "-"
            else:
                pct = 100.0 * conf[i, j] / total
                sign = "+" if i == j else "-"
                cell = f"{sign}{pct:.1f}%"
            row_cells.append(cell)
        rows.append([class_names[i]] + row_cells)

    align = ["l"] + ["r"] * (len(headers) - 1)
    return _format_ascii_table(headers, rows, align=align, row_separators=True)


def _format_aligned_step_summary(
    step_predictions: dict[tuple[str, str], dict],
    timeframes_order: list[str],
) -> str | None:
    """Create per-target summary on timestamps shared across timeframes in one step."""
    if not step_predictions:
        return None

    targets = sorted({target for (_, target) in step_predictions.keys()})
    sections: list[str] = []

    for target_col in targets:
        available_tfs = [
            tf for tf in timeframes_order if (tf, target_col) in step_predictions
        ]
        if len(available_tfs) < 2:
            continue

        common_ts: set | None = None
        for tf in available_tfs:
            ts_set = set(step_predictions[(tf, target_col)]["timestamps"])
            common_ts = ts_set if common_ts is None else (common_ts & ts_set)

        if not common_ts:
            continue

        rows: list[list[str]] = []
        for tf in available_tfs:
            payload = step_predictions[(tf, target_col)]
            ts = payload["timestamps"]
            y_actual_all = payload["actual"]
            y_pred_all = payload["pred"]
            class_names = payload.get("class_names", ())

            y_actual = np.array(
                [a for t, a in zip(ts, y_actual_all) if t in common_ts], dtype=int
            )
            y_pred = np.array(
                [p for t, p in zip(ts, y_pred_all) if t in common_ts], dtype=int
            )

            if len(y_actual) == 0:
                continue

            acc = float((y_actual == y_pred).mean())
            macro_f1 = float(
                f1_score(y_actual, y_pred, average="macro", zero_division=0)
            )

            dir_acc_str = "-"
            cross_err_str = "-"
            if target_col == "target_4class" and len(class_names) >= 2:
                dir_acc = compute_directional_accuracy(y_actual, y_pred, class_names)
                cross_err = compute_cross_direction_error_rate(
                    y_actual, y_pred, class_names
                )
                dir_acc_str = f"{dir_acc:.1%}"
                cross_err_str = f"{cross_err:.1%}"

            rows.append(
                [
                    tf,
                    str(len(y_actual)),
                    f"{acc:.1%}",
                    f"{macro_f1:.1%}",
                    dir_acc_str,
                    cross_err_str,
                ]
            )

        if not rows:
            continue

        headers = ["TF", "AlignedRows", "Accuracy", "MacroF1", "DirAcc", "CrossErr"]
        align = ["l", "r", "r", "r", "r", "r"]
        ts_sorted = sorted(common_ts)
        sections.append(
            f"{target_col} | common_timestamps={len(ts_sorted)} | "
            f"{ts_sorted[0]} -> {ts_sorted[-1]}"
        )
        sections.append(
            _format_ascii_table(headers, rows, align=align, row_separators=True)
        )

    if not sections:
        return None
    return "\n\n".join(sections)


def run_walk_forward_backtest(
    n_steps: int | None = None,
    timeframes: list[str] | None = None,
    run_description: str = "Walk-forward optimization: multi-target LightGBM classification",
    verbose: bool = True,
    debug_batches: bool = False,
    optuna_overrides: dict | None = None,
    run_id: str | None = None,
    resume: bool = False,
    resume_mode: str = "continue",
    allow_override_mismatch: bool = False,
    model_name: str = "lightgbm",
    optuna_overrides_by_model: dict | None = None,
    targets_by_model: dict | None = None,
    n_classes_by_model: dict | None = None,
    class_names_by_model: dict | None = None,
    feature_source_by_model: dict | None = None,
    target_registry: dict | None = None,
) -> dict:
    """Run multi-timeframe, multi-target walk-forward backtest."""
    # Lazy imports to avoid circular imports
    from .tf_1m import Config1m, FeatureSpace1m, ModelSpace1m, Optimizer1m, WindowSpace1m
    from .tf_5m import Config5m, FeatureSpace5m, ModelSpace5m, Optimizer5m, WindowSpace5m
    from .tf_15m import (
        Config15m,
        FeatureSpace15m,
        ModelSpace15m,
        Optimizer15m,
        WindowSpace15m,
    )

    if resume and not run_id:
        raise ValueError("resume=True requires run_id")

    if resume_mode not in {"continue", "skip_completed"}:
        raise ValueError("resume_mode must be 'continue' or 'skip_completed'")

    if timeframes is None:
        timeframes = ["5m", "15m"]

    # Resolve model-specific overrides if provided
    if optuna_overrides_by_model is not None:
        if model_name not in optuna_overrides_by_model:
            raise ValueError(
                f"optuna_overrides_by_model missing entry for model '{model_name}'"
            )
        optuna_overrides = optuna_overrides_by_model.get(model_name)

    target_map = None
    if targets_by_model is not None:
        if model_name not in targets_by_model:
            raise ValueError(
                f"targets_by_model missing entry for model '{model_name}'"
            )
        target_map = targets_by_model.get(model_name)

    n_classes_map = None
    if n_classes_by_model is not None:
        if model_name not in n_classes_by_model:
            raise ValueError(
                f"n_classes_by_model missing entry for model '{model_name}'"
            )
        n_classes_map = n_classes_by_model.get(model_name)

    class_names_map = None
    if class_names_by_model is not None:
        if model_name not in class_names_by_model:
            raise ValueError(
                f"class_names_by_model missing entry for model '{model_name}'"
            )
        class_names_map = class_names_by_model.get(model_name)

    feature_source_map = None
    if feature_source_by_model is not None:
        if model_name not in feature_source_by_model:
            raise ValueError(
                f"feature_source_by_model missing entry for model '{model_name}'"
            )
        feature_source_map = feature_source_by_model.get(model_name)

    def _normalize_target_list(value, default_target: str) -> list[str]:
        if value is None:
            return [default_target]
        if isinstance(value, str):
            targets = [value]
        elif isinstance(value, (list, tuple, set)):
            targets = [str(v) for v in value if v is not None]
        else:
            raise ValueError(f"Invalid target config type: {type(value)}")
        deduped = []
        for t in targets:
            if t not in deduped:
                deduped.append(t)
        if not deduped:
            raise ValueError("Target list cannot be empty")
        return deduped

    def _normalize_targets_map(raw: dict | None) -> dict[str, list[str]]:
        if not isinstance(raw, dict):
            return {}
        out = {}
        for tf, val in raw.items():
            out[tf] = _normalize_target_list(val, "target_4class")
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
        if tf_val is None:
            return target_col
        raise ValueError(
            f"Invalid feature source config for tf={tf}: {type(tf_val)}"
        )

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
        "window_space",
        "feature_space",
        "model_space",
    }

    def _resolve_overrides(tf: str, target_col: str) -> dict:
        tf_overrides = (optuna_overrides or {}).get(tf, {})
        if not isinstance(tf_overrides, dict):
            raise ValueError(
                f"Invalid optuna_overrides entry for tf={tf}: {type(tf_overrides)}"
            )
        # Backward-compatible shared override shape: {tf: {optuna_trials: ...}}
        if any(k in tf_overrides for k in override_keys):
            return tf_overrides
        # New per-target shape: {tf: {target_a: {...}, target_b: {...}}}
        target_overrides = tf_overrides.get(target_col, {})
        if not isinstance(target_overrides, dict):
            raise ValueError(
                f"Invalid target override for tf={tf}, target={target_col}: "
                f"{type(target_overrides)}"
            )
        return target_overrides

    def _load_parquet_columns(path: Path) -> set[str]:
        try:
            return set(pl.scan_parquet(str(path)).collect_schema().names())
        except Exception:
            return set(pl.read_parquet(path).columns)

    # Load existing run config if resuming
    existing_config = None
    use_model_subdir = True
    base_run_dir = None
    if resume:
        # Use default config to locate output_dir
        tmp_cfg = Config5m()
        base_run_dir = tmp_cfg.output_dir / run_id
        config_path = base_run_dir / "run_config.json"
        if not base_run_dir.exists():
            raise FileNotFoundError(f"run_id not found: {base_run_dir}")
        if not config_path.exists():
            raise FileNotFoundError(f"run_config.json not found in {base_run_dir}")
        with open(config_path, "r") as f:
            existing_config = json.load(f)

        # Backward compatibility for older runs without model info
        stored_model = existing_config.get("model_name")
        models_dict = existing_config.get("models")
        has_model_entry = bool(models_dict and model_name in models_dict)
        has_models_block = models_dict is not None
        if models_dict is not None:
            use_model_subdir = True
        elif stored_model is not None:
            model_name = stored_model
            use_model_subdir = True
        else:
            # Old layout: run_dir/<tf>/batch_xxxx
            use_model_subdir = False

        if has_model_entry:
            stored_tfs = models_dict[model_name].get("timeframes")
            if stored_tfs and timeframes != stored_tfs:
                raise ValueError(
                    f"timeframes mismatch for resume (model={model_name}). "
                    f"run_config has {stored_tfs}, got {timeframes}"
                )
            timeframes = stored_tfs or timeframes
        elif has_models_block:
            # Multi-model run_config is present, but this model has not been added yet.
            # Keep caller-provided model-specific timeframes.
            pass
        else:
            if existing_config.get("timeframes") and timeframes != existing_config.get(
                "timeframes"
            ):
                raise ValueError(
                    f"timeframes mismatch for resume. "
                    f"run_config has {existing_config.get('timeframes')}, got {timeframes}"
                )
            timeframes = existing_config.get("timeframes", timeframes)

        # Resolve optuna overrides for the selected model
        if has_model_entry:
            stored_overrides = models_dict[model_name].get("optuna_overrides", {})
        elif has_models_block:
            # New model added into an existing multi-model run.
            stored_overrides = {}
        else:
            stored_overrides = existing_config.get("optuna_overrides", {})

        if optuna_overrides is None:
            optuna_overrides = stored_overrides
        elif (
            stored_overrides is not None
            and optuna_overrides != stored_overrides
            and not allow_override_mismatch
        ):
            raise ValueError(
                "optuna_overrides mismatch for resume. "
                "Set allow_override_mismatch=True to override."
            )

        # Resolve targets/class config for the selected model
        if has_model_entry:
            stored_targets = models_dict[model_name].get("targets", {})
            stored_n_classes = models_dict[model_name].get("n_classes", {})
            stored_class_names = models_dict[model_name].get("class_names", {})
            stored_feature_sources = models_dict[model_name].get("feature_sources", {})
        elif has_models_block:
            # New model added into an existing multi-model run.
            stored_targets = {}
            stored_n_classes = {}
            stored_class_names = {}
            stored_feature_sources = {}
        else:
            stored_targets = existing_config.get("targets", {})
            stored_n_classes = existing_config.get("n_classes", {})
            stored_class_names = existing_config.get("class_names", {})
            stored_feature_sources = existing_config.get("feature_sources", {})

        if target_map is None:
            target_map = stored_targets
        elif (
            stored_targets
            and _normalize_targets_map(target_map) != _normalize_targets_map(stored_targets)
            and not allow_override_mismatch
        ):
            raise ValueError(
                "targets mismatch for resume. "
                "Set allow_override_mismatch=True to override."
            )

        if n_classes_map is None:
            n_classes_map = stored_n_classes
        elif stored_n_classes and n_classes_map != stored_n_classes and not allow_override_mismatch:
            raise ValueError(
                "n_classes mismatch for resume. "
                "Set allow_override_mismatch=True to override."
            )

        if class_names_map is None:
            class_names_map = stored_class_names
        elif stored_class_names and class_names_map != stored_class_names and not allow_override_mismatch:
            raise ValueError(
                "class_names mismatch for resume. "
                "Set allow_override_mismatch=True to override."
            )

        if feature_source_map is None:
            feature_source_map = stored_feature_sources
        elif (
            stored_feature_sources
            and feature_source_map != stored_feature_sources
            and not allow_override_mismatch
        ):
            raise ValueError(
                "feature_sources mismatch for resume. "
                "Set allow_override_mismatch=True to override."
            )

        if n_steps is None and existing_config.get("n_steps") is not None:
            n_steps = existing_config["n_steps"]
        if existing_config.get("run_description"):
            run_description = existing_config["run_description"]

    # Create run ID for fresh runs
    if not resume:
        run_id = run_id or f"run_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}"

    # Initialize execution units
    optuna_overrides = optuna_overrides or {}
    target_map = target_map or {}
    feature_source_map = feature_source_map or {}

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
            if "optuna_trials" in overrides:
                cfg = replace(cfg, optuna_trials=overrides["optuna_trials"])
            if "optuna_timeout" in overrides:
                cfg = replace(cfg, optuna_timeout=overrides["optuna_timeout"])
            if "optuna_metric" in overrides:
                cfg = replace(cfg, optuna_metric=overrides["optuna_metric"])
            if "exclude_tail_pct" in overrides:
                cfg = replace(cfg, exclude_tail_pct=overrides["exclude_tail_pct"])
            if "track_pred_metrics" in overrides:
                cfg = replace(cfg, track_pred_metrics=overrides["track_pred_metrics"])
            if "shuffle_split" in overrides:
                cfg = replace(cfg, shuffle_split=overrides["shuffle_split"])
            if "shuffle_seed" in overrides:
                cfg = replace(cfg, shuffle_seed=overrides["shuffle_seed"])
            if "shuffle_val_ratio" in overrides:
                cfg = replace(cfg, shuffle_val_ratio=overrides["shuffle_val_ratio"])
            if "shuffle_batches" in overrides:
                cfg = replace(cfg, shuffle_batches=overrides["shuffle_batches"])
            if "shuffle_batches_seed" in overrides:
                cfg = replace(cfg, shuffle_batches_seed=overrides["shuffle_batches_seed"])
            if "balance_strategy" in overrides:
                cfg = replace(cfg, balance_strategy=overrides["balance_strategy"])
            if "balance_apply_to" in overrides:
                cfg = replace(cfg, balance_apply_to=overrides["balance_apply_to"])
            if "class_weight_choices" in overrides:
                cfg = replace(
                    cfg,
                    class_weight_choices=tuple(overrides["class_weight_choices"]),
                )
            if "window_space" in overrides:
                win = replace(win, **overrides["window_space"])
            if "feature_space" in overrides:
                feat = replace(feat, **overrides["feature_space"])
            if "model_space" in overrides:
                model = replace(model, **overrides["model_space"])

            feature_target_col = _resolve_feature_target(tf, target_col)
            task_type = "multiclass"
            if target_registry and target_col in target_registry:
                target_def = target_registry[target_col]
                task_type = target_def.get("task_type", "multiclass")
                if task_type not in {"multiclass", "binary"}:
                    raise ValueError(
                        f"Unsupported task_type '{task_type}' for target '{target_col}'. "
                        "This LightGBM pipeline currently supports classification only."
                    )
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
            cfg.lgb_base_params = cfg.lgb_base_params.copy()
            if task_type == "binary":
                if cfg.n_classes != 2:
                    raise ValueError(
                        f"Binary target '{target_col}' must use n_classes=2, got {cfg.n_classes}"
                    )
                cfg.lgb_base_params["objective"] = "binary"
                cfg.lgb_base_params["metric"] = "binary_logloss"
                cfg.lgb_base_params.pop("num_class", None)
            else:
                cfg.lgb_base_params["objective"] = "multiclass"
                cfg.lgb_base_params["metric"] = "multi_logloss"
                cfg.lgb_base_params["num_class"] = cfg.n_classes

            optimizer = opt_cls(
                config=cfg, window_space=win, feature_space=feat, model_space=model
            )
            execution_units.append(
                {
                    "tf": tf,
                    "target_col": target_col,
                    "feature_target_col": feature_target_col,
                    "task_type": task_type,
                    "overrides": overrides,
                    "optimizer": optimizer,
                }
            )

    if not execution_units:
        raise ValueError("No execution units built. Check timeframes/targets configuration.")

    # Use first config as reference
    ref_config = execution_units[0]["optimizer"].config

    # Paths from config
    features_dir = ref_config.features_dir
    labels_dir = ref_config.labels_dir
    output_dir = ref_config.output_dir

    # Print header
    if verbose:
        print("=" * 100)
        print("HTF WALK-FORWARD BACKTEST (CLASSIFICATION)")
        print("=" * 100)
        print(f"\nRun ID: {run_id}")
        print(f"Model: {model_name}")
        if resume:
            print(f"Resume: True (mode={resume_mode})")
        print(f"Description: {run_description}")

        for unit in execution_units:
            cfg = unit["optimizer"].config
            win = unit["optimizer"].window_space
            print(f"\n  {unit['tf']}/{unit['target_col']} config:")
            print(f"    trials={cfg.optuna_trials}, timeout={cfg.optuna_timeout}s")
            print(
                f"    lookback: {win.lookback_min}-{win.lookback_max}"
            )
            print(f"    lookback_selection: {win.window_selection_mode}")
            if win.window_selection_mode == "deterministic_solver":
                print(
                    "    train_share_bounds: "
                    f"{win.train_share_min:.0%}-{win.train_share_max:.0%}"
                )
                print(
                    f"    embargo: mode={win.embargo_mode}, "
                    f"train_val={win.embargo_train_val_batches}, "
                    f"val_pred={win.embargo_val_pred_batches}"
                )
            print(f"    target: {cfg.target} (classes={cfg.n_classes})")
            if unit["feature_target_col"] != cfg.target:
                print(f"    feature_source: {unit['feature_target_col']}")
            if cfg.exclude_tail_pct and cfg.exclude_tail_pct > 0:
                print(f"    exclude_tail_pct: {cfg.exclude_tail_pct:.2f}")
            if cfg.shuffle_split:
                val_ratio = (
                    cfg.shuffle_val_ratio
                    if cfg.shuffle_val_ratio is not None
                    else (1.0 - cfg.train_val_split)
                )
                print(
                    "    split=shuffle_stratified "
                    f"(val_ratio={val_ratio:.2f}, seed={cfg.shuffle_seed})"
                )
            if cfg.shuffle_batches:
                print(
                    f"    shuffle_batches=True (seed={cfg.shuffle_batches_seed})"
                )
            if cfg.balance_strategy != "none":
                print(
                    f"    balance={cfg.balance_strategy} (apply_to={cfg.balance_apply_to})"
                )
            print(
                f"    optuna_metric: {cfg.optuna_metric} ({cfg.optuna_direction()})"
            )
            dist = compute_label_distribution(
                labels_dir,
                unit["tf"],
                unit["target_col"],
                exclude_tail_pct=cfg.exclude_tail_pct,
            )
            if not dist.is_empty():
                print("    label_distribution (all batches):")
                for row in dist.to_dicts():
                    class_id = int(row["class_id"])
                    name = (
                        cfg.class_names[class_id]
                        if 0 <= class_id < len(cfg.class_names)
                        else f"class_{class_id}"
                    )
                    print(f"      {name}: {int(row['count'])} ({row['pct']:.1f}%)")

    # Create run directory
    if base_run_dir is None:
        base_run_dir = output_dir / run_id
    base_run_dir.mkdir(parents=True, exist_ok=True)

    # Model-specific subdir (for new runs or model-aware runs)
    if use_model_subdir:
        run_dir = base_run_dir / model_name
        run_dir.mkdir(parents=True, exist_ok=True)
    else:
        run_dir = base_run_dir

    # Validate labels contain all requested targets before expensive optimization
    checked_targets = set()
    for unit in execution_units:
        check_key = (unit["tf"], unit["target_col"])
        if check_key in checked_targets:
            continue
        checked_targets.add(check_key)
        tf_dir = labels_dir / unit["tf"]
        label_files = sorted(tf_dir.glob("batch_*.parquet"))
        if not label_files:
            raise ValueError(f"No label files found for timeframe '{unit['tf']}' in {tf_dir}")
        checked = 0
        missing_examples = []
        for label_file in label_files:
            checked += 1
            cols = _load_parquet_columns(label_file)
            if unit["target_col"] not in cols:
                missing_examples.append(label_file.name)
                if len(missing_examples) >= 3:
                    break
        if missing_examples:
            raise ValueError(
                f"Missing target column '{unit['target_col']}' for timeframe '{unit['tf']}' "
                f"(checked {checked}/{len(label_files)} files). "
                f"Examples: {missing_examples}. "
                f"Regenerate labels for timeframe '{unit['tf']}' and target '{unit['target_col']}'."
            )

    # Validate all batches upfront
    if verbose:
        print("\nValidating batches...")
        print("  Note: Validity is based on rows where target >= 0.")
        print(
            "        Minimum valid rows are auto-inferred per timeframe from on-disk data."
        )

    valid_batches = {}
    for unit in execution_units:
        tf = unit["tf"]
        target_col = unit["target_col"]
        feature_target_col = unit["feature_target_col"]
        key = f"{tf}/{target_col}"
        total_count = get_batch_count(labels_dir, tf)
        valid = get_valid_batches(
            features_dir,
            labels_dir,
            tf,
            target_col=target_col,
            feature_target_col=feature_target_col,
            exclude_tail_pct=unit["optimizer"].config.exclude_tail_pct,
            # Use the 4-class validity mask for batch completeness checks.
            validity_target_col="target_4class",
        )
        valid_batches[key] = valid
        invalid_count = total_count - len(valid)
        if verbose:
            print(
                f"  {key}: {len(valid)}/{total_count} valid batches "
                f"({invalid_count} below valid-row threshold)"
            )

    # Use intersection of valid batches across all execution units
    first_unit_key = next(iter(valid_batches.keys()))
    common_valid = set(valid_batches[first_unit_key])
    for unit_key in valid_batches:
        common_valid &= set(valid_batches[unit_key])
    common_valid_desc = sorted(common_valid, reverse=True)
    common_valid_asc = list(reversed(common_valid_desc))

    if verbose:
        print(f"  Common valid across all units: {len(common_valid)} batches")

    # Use MAX lookback_min so all units can train on each shared prediction batch
    max_lookback_min = max(
        unit["optimizer"].window_space.lookback_min for unit in execution_units
    )

    # Filter to batches that have enough training data (batch_idx > lookback_min)
    eligible_batches_desc = [b for b in common_valid_desc if b > max_lookback_min]
    eligible_batches_asc = list(reversed(eligible_batches_desc))

    if not eligible_batches_desc:
        raise ValueError(
            f"No valid batches with sufficient training data. "
            f"Need batch > {max_lookback_min}, have {len(common_valid_desc)} valid batches."
        )

    max_steps = len(eligible_batches_desc)

    if n_steps is None:
        n_steps = max_steps
    else:
        n_steps = min(n_steps, max_steps)

    # Take the most recent n_steps, but walk forward (oldest -> newest)
    step_batches = eligible_batches_asc[-n_steps:]

    if verbose:
        print(f"\n  Running {n_steps} steps (max possible: {max_steps})")
        print("  Walk direction: oldest_to_newest")
        print(f"  First prediction batch: {step_batches[0]}")
        print(f"  Last prediction batch: {step_batches[-1]}")
        print(f"  Lookback_min requirement: {max_lookback_min}")
        if debug_batches:
            if len(step_batches) <= 10:
                print(f"  Step batches: {step_batches}")
            else:
                head = step_batches[:5]
                tail = step_batches[-5:]
                print(f"  Step batches: {head} ... {tail}")

    # Save or update run config
    run_config = existing_config or {}
    run_config.update(
        {
            "run_id": run_id,
            "run_description": run_description,
            "n_steps": n_steps,
            "max_steps": max_steps,
            "walk_direction": "oldest_to_newest",
            "valid_batches_per_unit": {k: len(v) for k, v in valid_batches.items()},
            "eligible_batches": len(eligible_batches_desc),
            "lookback_min": max_lookback_min,
        }
    )
    # Track model-specific settings to avoid mixing across models
    models_dict = run_config.get("models", {})
    model_targets = {}
    model_n_classes = {}
    model_class_names = {}
    model_feature_sources = {}
    model_overrides = {}
    model_timeframes = []
    for unit in execution_units:
        tf = unit["tf"]
        cfg = unit["optimizer"].config
        target_col = unit["target_col"]
        feature_target_col = unit["feature_target_col"]
        model_timeframes.append(tf)
        model_targets.setdefault(tf, [])
        if target_col not in model_targets[tf]:
            model_targets[tf].append(target_col)
        model_n_classes.setdefault(tf, {})[target_col] = int(cfg.n_classes)
        model_class_names.setdefault(tf, {})[target_col] = list(cfg.class_names)
        model_feature_sources.setdefault(tf, {})[target_col] = feature_target_col
        model_overrides.setdefault(tf, {})[target_col] = unit["overrides"]
    model_timeframes = sorted(set(model_timeframes))
    models_dict[model_name] = {
        "timeframes": model_timeframes,
        "optuna_overrides": model_overrides,
        "targets": model_targets,
        "n_classes": model_n_classes,
        "class_names": model_class_names,
        "feature_sources": model_feature_sources,
        "updated_at": datetime.now().isoformat(),
    }
    run_config["models"] = models_dict

    # Backward-compatible fields (single-model runs)
    run_config.setdefault("timeframes", model_timeframes)
    run_config["optuna_overrides"] = model_overrides
    run_config["model_name"] = model_name
    run_config["targets"] = model_targets
    run_config["n_classes"] = model_n_classes
    run_config["class_names"] = model_class_names
    run_config["feature_sources"] = model_feature_sources
    if "started_at" not in run_config:
        run_config["started_at"] = datetime.now().isoformat()
    if resume:
        run_config["resumed_at"] = datetime.now().isoformat()
    with open(base_run_dir / "run_config.json", "w") as f:
        json.dump(run_config, f, indent=2)

    # Storage
    all_results = defaultdict(list)
    all_predictions = defaultdict(list)
    opt_results = {}
    model_class_names = {}

    t_start = time.time()
    run_index_path = base_run_dir / "run_model_index.json"

    for step in range(n_steps):
        step_num = step + 1
        step_start = time.time()
        step_tables = {}
        step_predictions: dict[tuple[str, str], dict] = {}

        # Get pre-validated batch from selected step order (oldest -> newest)
        pred_batch = step_batches[step]
        train_end = pred_batch - 1

        if verbose:
            print()
            print("#" * 80)
            print(
                f"#  STEP {step_num}/{n_steps} | Train batches 1-{train_end} → Predict batch {pred_batch}"
            )
            print("#" * 80)

        for unit in execution_units:
            tf = unit["tf"]
            target_col = unit["target_col"]
            feature_target_col = unit["feature_target_col"]
            optimizer = unit["optimizer"]
            n_classes = int(optimizer.config.n_classes)
            class_names = (
                list(optimizer.config.class_names)
                if getattr(optimizer.config, "class_names", None)
                else []
            )
            if len(class_names) != n_classes:
                # Fallback to generic names if mismatch
                class_names = [f"class_{i}" for i in range(n_classes)]

            model_key = f"{model_name}/{tf}/{target_col}"
            model_class_names[model_key] = class_names

            try:
                if verbose:
                    print(f"\n  {model_key}:")

                # Setup step directory
                safe_target = target_col.replace("/", "_")
                step_dir_new = run_dir / tf / safe_target / f"batch_{pred_batch:04d}"
                step_dir_legacy = run_dir / tf / f"batch_{pred_batch:04d}"
                # New canonical layout: run_dir/<tf>/<target>/batch_xxxx
                if resume and not step_dir_new.exists() and step_dir_legacy.exists():
                    step_dir = step_dir_legacy
                else:
                    step_dir = step_dir_new
                    step_dir.mkdir(parents=True, exist_ok=True)
                study_path = step_dir / "study.db"
                study_name = f"htf_{model_name}_{tf}_{safe_target}_batch_{pred_batch:04d}"

                if resume and study_path.exists():
                    try:
                        storage = f"sqlite:///{study_path}"
                        summaries = optuna.study.get_all_study_summaries(storage=storage)
                        if summaries:
                            study_name = summaries[0].study_name
                    except Exception:
                        pass

                if verbose:
                    print(f"    Study: {study_name}")

                if resume and resume_mode == "skip_completed":
                    prediction_done = (step_dir / "prediction_metrics.json").exists()
                    model_done = (step_dir / "model.txt").exists()
                    if prediction_done and model_done:
                        if verbose:
                            print(
                                "    Resume: batch already completed; skipping per resume_mode='skip_completed'"
                            )
                        continue

                # Load prediction batch (already validated upfront for 8h coverage)
                pred_df = load_batch(
                    features_dir,
                    labels_dir,
                    tf,
                    pred_batch,
                    target_col=target_col,
                    feature_target_col=feature_target_col,
                    exclude_tail_pct=optimizer.config.exclude_tail_pct,
                )
                pred_df = pred_df.filter(pred_df[target_col] >= 0)

                if len(pred_df) == 0:
                    if verbose:
                        print(f"    No valid predictions in batch {pred_batch}")
                    continue

                if debug_batches:
                    batch_ids = pred_df["batch_id"].unique().to_list()
                    if len(batch_ids) != 1 or batch_ids[0] != pred_batch:
                        print(
                            f"    WARNING: Loaded batch_ids={batch_ids} (expected {pred_batch})"
                        )
                    else:
                        print(f"    Batch ID OK: {batch_ids[0]}")

                start_timestamp = pred_df["timestamp"].min()
                end_timestamp = pred_df["timestamp"].max()
                if verbose:
                    print(f"    Batch: {start_timestamp} → {end_timestamp}")

                # Optimization
                cfg = optimizer.config
                if verbose:
                    print(
                        f"    Running optimization (trials={cfg.optuna_trials}, timeout={cfg.optuna_timeout}s)..."
                    )

                opt_start = time.time()
                opt_result = optimizer.optimize_step(
                    train_end=train_end,
                    study_storage_path=study_path,
                    study_name=study_name,
                )

                opt_results[model_key] = opt_result
                if verbose:
                    try:
                        study = opt_result.get("study")
                        n_complete = (
                            len([t for t in study.trials if t.state == optuna.trial.TrialState.COMPLETE])
                            if study is not None
                            else "?"
                        )
                    except Exception:
                        n_complete = "?"
                    print(
                        f"    Optimization completed in {time.time() - opt_start:.1f}s"
                    )
                    print(f"    Completed trials: {n_complete}")
                    metric_name = opt_result.get("optuna_metric", "accuracy")
                    best_score = opt_result.get("best_score", opt_result.get("best_accuracy"))
                    if metric_name == "log_loss":
                        print(f"    Best {metric_name}: {best_score:.4f}")
                    else:
                        print(f"    Best {metric_name}: {best_score:.1%}")
                    if opt_result.get("best_accuracy") is not None:
                        print(f"    Best val accuracy: {opt_result['best_accuracy']:.1%}")
                    if opt_result.get("directional_accuracy") is not None:
                        print(
                            "    Best val directional: "
                            f"Acc={float(opt_result.get('directional_accuracy', 0.0)):.1%}, "
                            f"Prec(up/down)="
                            f"{float(opt_result.get('directional_precision_up', 0.0)):.1%}/"
                            f"{float(opt_result.get('directional_precision_down', 0.0)):.1%}, "
                            f"CrossErr={float(opt_result.get('cross_direction_error', 0.0)):.1%}"
                        )
                    print(f"    Lookback: {opt_result['lookback_batches']} batches")
                    if opt_result.get("train_val_split") is not None:
                        print(
                            "    Estimated split: "
                            f"train={float(opt_result['train_val_split']):.1%}, "
                            f"val={float(opt_result.get('val_ratio', 1.0 - opt_result['train_val_split'])):.1%}"
                        )
                    if opt_result.get("window_selection_mode"):
                        print(
                            f"    Window mode: {opt_result['window_selection_mode']}"
                        )
                    if opt_result.get("reference_distribution_mode"):
                        print(
                            "    Reference dist: "
                            f"mode={opt_result.get('reference_distribution_mode')}, "
                            f"recent_batches={opt_result.get('recent_ref_batches')}, "
                            f"recent_weight={float(opt_result.get('recent_ref_weight', 0.0)):.2f}, "
                            f"active_classes={opt_result.get('active_class_ids', [])}"
                        )
                    if opt_result.get("train_start_batch") is not None:
                        print(
                            "    Window batches: "
                            f"train={opt_result.get('train_start_batch')}-{opt_result.get('train_end_batch')} | "
                            f"val={opt_result.get('val_start_batch')}-{opt_result.get('val_end_batch')}"
                        )
                    if opt_result.get("leakage_guard") is not None:
                        print(f"    leakage_guard={opt_result.get('leakage_guard')}")
                    print(f"    Features: {opt_result['n_features']} selected")

                # Export all trials for analysis (params + metrics)
                export_study_trials(
                    study=opt_result.get("study"),
                    step_dir=step_dir,
                    model_name=model_name,
                    timeframe=tf,
                    target_col=target_col,
                    feature_target_col=feature_target_col,
                    step=step_num,
                    train_end=train_end,
                    pred_batch=pred_batch,
                    start_timestamp=start_timestamp,
                    end_timestamp=end_timestamp,
                )

                # Training
                if verbose:
                    print("    Training model...")
                train_start = time.time()
                model = optimizer.train_model(
                    train_end=train_end, opt_result=opt_result
                )
                if verbose:
                    print(f"    Training completed in {time.time() - train_start:.1f}s")

                # Save results
                saved_files = save_step_results(
                    opt_result=opt_result,
                    model=model,
                    step_dir=step_dir,
                    timeframe=tf,
                    step=step_num,
                    start_timestamp=start_timestamp,
                    end_timestamp=end_timestamp,
                    model_name=model_name,
                    target_col=target_col,
                    class_names=class_names,
                )
                if verbose:
                    print(
                        f"    Saved: {', '.join(f.name for f in saved_files.values())}"
                    )

                # Prediction
                selected_features = opt_result["selected_features"]
                available_features = [
                    f for f in selected_features if f in pred_df.columns
                ]
                X_pred = pred_df.select(available_features).to_numpy()
                y_actual = pred_df[target_col].to_numpy().astype(int)
                timestamps = pred_df["timestamp"].to_list()

                X_pred = np.nan_to_num(X_pred, nan=0.0, posinf=0.0, neginf=0.0)

                proba, y_pred = _to_class_proba_and_pred(model.predict(X_pred))

                acc = accuracy_score(y_actual, y_pred)
                loss = log_loss(y_actual, proba, labels=list(range(n_classes)))

                class_acc = {}
                for c in range(n_classes):
                    mask = y_actual == c
                    if mask.sum() > 0:
                        class_acc[c] = (y_pred[mask] == c).mean()

                prec, rec, _, _ = precision_recall_fscore_support(
                    y_actual,
                    y_pred,
                    labels=list(range(n_classes)),
                    zero_division=0,
                )
                dir_macro_f1_up = compute_directional_macro_f1(
                    y_actual, y_pred, class_names, direction=1
                )
                dir_macro_f1_down = compute_directional_macro_f1(
                    y_actual, y_pred, class_names, direction=0
                )
                dir_acc = compute_directional_accuracy(y_actual, y_pred, class_names)
                dir_prec_up = compute_directional_precision(
                    y_actual, y_pred, class_names, direction=1
                )
                dir_prec_down = compute_directional_precision(
                    y_actual, y_pred, class_names, direction=0
                )
                dir_rec_up = compute_directional_recall(
                    y_actual, y_pred, class_names, direction=1
                )
                dir_rec_down = compute_directional_recall(
                    y_actual, y_pred, class_names, direction=0
                )
                cross_dir_err = compute_cross_direction_error_rate(
                    y_actual, y_pred, class_names
                )
                conf_arr = confusion_matrix(
                    y_actual, y_pred, labels=list(range(n_classes))
                )
                conf = conf_arr.tolist()
                row_sums = conf_arr.sum(axis=1, keepdims=True)
                conf_pct = np.divide(
                    conf_arr.astype(float),
                    row_sums,
                    out=np.zeros_like(conf_arr, dtype=float),
                    where=row_sums != 0,
                ).tolist()

                if verbose:
                    print(f"    Predictions: {len(y_pred)} rows")
                    print(f"    Accuracy: {acc:.1%}, LogLoss: {loss:.4f}")
                    print(
                        "    Per-class: "
                        + ", ".join(
                            f"{class_names[c]}:{v:.0%}"
                            for c, v in sorted(class_acc.items())
                        )
                    )
                    print(
                        "    Per-class P/R: "
                        + ", ".join(
                            f"{class_names[c]}:{prec[c]:.0%}/{rec[c]:.0%}"
                            for c in range(n_classes)
                        )
                    )
                    print(
                        "    Directional: "
                        f"Acc={dir_acc:.1%}, "
                        f"Prec(up/down)={dir_prec_up:.1%}/{dir_prec_down:.1%}, "
                        f"Rec(up/down)={dir_rec_up:.1%}/{dir_rec_down:.1%}, "
                        f"CrossErr={cross_dir_err:.1%}"
                    )
                    class_table = _format_class_table(
                        tuple(class_names), y_actual, y_pred, class_acc, prec, rec
                    )
                    conf_table = _format_confusion_table(
                        tuple(class_names), conf_arr
                    )
                    step_tables[model_key] = (
                        class_table
                        + "\n\n"
                        + "Confusion (% of all predictions, + correct / - incorrect)\n"
                        + conf_table
                    )

                # Save prediction metrics to step folder
                pred_metrics = {
                    "step": step_num,
                    "batch": pred_batch,
                    "model_name": model_name,
                    "timeframe": tf,
                    "target": target_col,
                    "feature_target": feature_target_col,
                    "timestamp_start": str(start_timestamp),
                    "timestamp_end": str(end_timestamp),
                    "class_names": list(class_names),
                    "accuracy": float(acc),
                    "log_loss": float(loss),
                    "n_predictions": len(y_pred),
                    "optuna_metric": opt_result.get("optuna_metric", "accuracy"),
                    "opt_val_score": float(
                        opt_result.get("best_score", opt_result.get("best_accuracy", 0))
                    ),
                    "opt_val_accuracy": (
                        float(opt_result["best_accuracy"])
                        if opt_result.get("best_accuracy") is not None
                        else None
                    ),
                    "opt_val_log_loss": float(opt_result.get("log_loss", 0)),
                    "accuracy_gap": (
                        float(acc - opt_result["best_accuracy"])
                        if opt_result.get("best_accuracy") is not None
                        else None
                    ),
                    "per_class_accuracy": {
                        int(k): float(v) for k, v in class_acc.items()
                    },
                    "per_class_precision": {
                        int(c): float(prec[c]) for c in range(n_classes)
                    },
                    "per_class_recall": {
                        int(c): float(rec[c]) for c in range(n_classes)
                    },
                    "macro_f1_up": float(dir_macro_f1_up),
                    "macro_f1_down": float(dir_macro_f1_down),
                    "directional_accuracy": float(dir_acc),
                    "directional_precision_up": float(dir_prec_up),
                    "directional_precision_down": float(dir_prec_down),
                    "directional_recall_up": float(dir_rec_up),
                    "directional_recall_down": float(dir_rec_down),
                    "cross_direction_error": float(cross_dir_err),
                    "per_class_count": {
                        int(c): int((y_actual == c).sum()) for c in range(n_classes)
                    },
                    "pred_class_distribution": {
                        int(c): int((y_pred == c).sum()) for c in range(n_classes)
                    },
                    "actual_class_distribution": {
                        int(c): int((y_actual == c).sum()) for c in range(n_classes)
                    },
                    "confusion_matrix": conf,
                    "confusion_matrix_pct": conf_pct,
                    "lookback_batches": int(opt_result["lookback_batches"]),
                    "train_val_split": (
                        float(opt_result["train_val_split"])
                        if opt_result.get("train_val_split") is not None
                        else None
                    ),
                    "val_ratio": (
                        float(opt_result["val_ratio"])
                        if opt_result.get("val_ratio") is not None
                        else None
                    ),
                    "window_distribution_score": (
                        float(opt_result["window_distribution_score"])
                        if opt_result.get("window_distribution_score") is not None
                        else None
                    ),
                    "window_selection_mode": opt_result.get("window_selection_mode"),
                    "train_start_batch": (
                        int(opt_result["train_start_batch"])
                        if opt_result.get("train_start_batch") is not None
                        else None
                    ),
                    "train_end_batch": (
                        int(opt_result["train_end_batch"])
                        if opt_result.get("train_end_batch") is not None
                        else None
                    ),
                    "val_start_batch": (
                        int(opt_result["val_start_batch"])
                        if opt_result.get("val_start_batch") is not None
                        else None
                    ),
                    "val_end_batch": (
                        int(opt_result["val_end_batch"])
                        if opt_result.get("val_end_batch") is not None
                        else None
                    ),
                    "embargo_train_val_batches": (
                        int(opt_result["embargo_train_val_batches"])
                        if opt_result.get("embargo_train_val_batches") is not None
                        else None
                    ),
                    "embargo_val_pred_batches": (
                        int(opt_result["embargo_val_pred_batches"])
                        if opt_result.get("embargo_val_pred_batches") is not None
                        else None
                    ),
                    "distribution_mse_train": (
                        float(opt_result["distribution_mse_train"])
                        if opt_result.get("distribution_mse_train") is not None
                        else None
                    ),
                    "distribution_mse_val": (
                        float(opt_result["distribution_mse_val"])
                        if opt_result.get("distribution_mse_val") is not None
                        else None
                    ),
                    "distribution_mse_window": (
                        float(opt_result["distribution_mse_window"])
                        if opt_result.get("distribution_mse_window") is not None
                        else None
                    ),
                    "distribution_mse_train_val": (
                        float(opt_result["distribution_mse_train_val"])
                        if opt_result.get("distribution_mse_train_val") is not None
                        else None
                    ),
                    "reference_distribution_mode": opt_result.get(
                        "reference_distribution_mode"
                    ),
                    "recent_ref_batches": (
                        int(opt_result["recent_ref_batches"])
                        if opt_result.get("recent_ref_batches") is not None
                        else None
                    ),
                    "recent_ref_weight": (
                        float(opt_result["recent_ref_weight"])
                        if opt_result.get("recent_ref_weight") is not None
                        else None
                    ),
                    "active_class_min_frac": (
                        float(opt_result["active_class_min_frac"])
                        if opt_result.get("active_class_min_frac") is not None
                        else None
                    ),
                    "min_val_samples_per_active_class": (
                        int(opt_result["min_val_samples_per_active_class"])
                        if opt_result.get("min_val_samples_per_active_class")
                        is not None
                        else None
                    ),
                    "active_class_ids": [
                        int(c) for c in opt_result.get("active_class_ids", [])
                    ],
                    "reference_distribution": [
                        float(v) for v in opt_result.get("reference_distribution", [])
                    ],
                    "recent_class_counts": [
                        int(v) for v in opt_result.get("recent_class_counts", [])
                    ],
                    "window_class_counts": [
                        int(v) for v in opt_result.get("window_class_counts", [])
                    ],
                    "train_class_counts": [
                        int(v) for v in opt_result.get("train_class_counts", [])
                    ],
                    "val_class_counts": [
                        int(v) for v in opt_result.get("val_class_counts", [])
                    ],
                    "total_class_counts": [
                        int(v) for v in opt_result.get("total_class_counts", [])
                    ],
                    "missing_classes_train": (
                        int(opt_result["missing_classes_train"])
                        if opt_result.get("missing_classes_train") is not None
                        else None
                    ),
                    "missing_classes_val": (
                        int(opt_result["missing_classes_val"])
                        if opt_result.get("missing_classes_val") is not None
                        else None
                    ),
                    "leakage_guard": opt_result.get("leakage_guard"),
                    "n_features": int(opt_result["n_features"]),
                    "class_weight_method": opt_result["class_weight_method"],
                }
                pred_metrics_path = step_dir / "prediction_metrics.json"
                with open(pred_metrics_path, "w") as f:
                    json.dump(pred_metrics, f, indent=2)

                # Save detailed predictions as parquet
                pred_records = []
                for i in range(len(y_pred)):
                    record = {
                        "timestamp": timestamps[i],
                        "actual": int(y_actual[i]),
                        "predicted": int(y_pred[i]),
                        "correct": int(y_pred[i] == y_actual[i]),
                        "confidence": float(proba[i].max()),
                    }
                    for c in range(n_classes):
                        record[f"prob_class_{c}"] = float(proba[i][c])
                    pred_records.append(record)

                pred_df_out = pl.DataFrame(pred_records)
                pred_df_out.write_parquet(step_dir / "predictions.parquet")

                # Save per-step payload to compare timeframes on aligned close timestamps.
                step_predictions[(tf, target_col)] = {
                    "timestamps": list(timestamps),
                    "actual": y_actual.tolist(),
                    "pred": y_pred.tolist(),
                    "class_names": tuple(class_names),
                }

                if verbose:
                    print("    Saved: prediction_metrics.json, predictions.parquet")

                # Batch metadata (for tracking model/timeframe/batch)
                data_sig = {
                    "labels": _dir_signature(labels_dir / tf),
                    "features": _dir_signature(
                        features_dir / tf / feature_target_col,
                        pattern="batch_*.parquet",
                    ),
                }
                config_sig = {
                    "optuna_overrides_tf_target": _config_signature(unit["overrides"]),
                    "optuna_overrides_model": _config_signature(optuna_overrides or {}),
                }
                git_info = _safe_git_info(str(ref_config.project_root))

                artifacts = {
                    "optimization": "optimization.json",
                    "model": "model.txt",
                    "class_metrics": "class_metrics.parquet",
                    "prediction_metrics": "prediction_metrics.json",
                    "predictions": "predictions.parquet",
                    "study_db": "study.db",
                    "trials_parquet": "trials.parquet",
                    "trials_jsonl": "trials.jsonl",
                }
                metrics = {
                    "accuracy": float(acc),
                    "log_loss": float(loss),
                    "n_predictions": len(y_pred),
                    "optuna_metric": pred_metrics["optuna_metric"],
                    "opt_val_score": pred_metrics["opt_val_score"],
                    "opt_val_accuracy": pred_metrics["opt_val_accuracy"],
                    "accuracy_gap": pred_metrics["accuracy_gap"],
                    "per_class_accuracy": pred_metrics["per_class_accuracy"],
                    "per_class_precision": pred_metrics["per_class_precision"],
                    "per_class_recall": pred_metrics["per_class_recall"],
                    "per_class_count": pred_metrics["per_class_count"],
                    "pred_class_distribution": pred_metrics[
                        "pred_class_distribution"
                    ],
                    "actual_class_distribution": pred_metrics[
                        "actual_class_distribution"
                    ],
                    "confusion_matrix": pred_metrics["confusion_matrix"],
                    "class_names": pred_metrics["class_names"],
                    "window_selection_mode": pred_metrics["window_selection_mode"],
                    "train_start_batch": pred_metrics["train_start_batch"],
                    "train_end_batch": pred_metrics["train_end_batch"],
                    "val_start_batch": pred_metrics["val_start_batch"],
                    "val_end_batch": pred_metrics["val_end_batch"],
                    "embargo_train_val_batches": pred_metrics[
                        "embargo_train_val_batches"
                    ],
                    "embargo_val_pred_batches": pred_metrics[
                        "embargo_val_pred_batches"
                    ],
                    "distribution_mse_train": pred_metrics["distribution_mse_train"],
                    "distribution_mse_val": pred_metrics["distribution_mse_val"],
                    "distribution_mse_window": pred_metrics[
                        "distribution_mse_window"
                    ],
                    "distribution_mse_train_val": pred_metrics[
                        "distribution_mse_train_val"
                    ],
                    "directional_accuracy": pred_metrics["directional_accuracy"],
                    "directional_precision_up": pred_metrics["directional_precision_up"],
                    "directional_precision_down": pred_metrics[
                        "directional_precision_down"
                    ],
                    "directional_recall_up": pred_metrics["directional_recall_up"],
                    "directional_recall_down": pred_metrics["directional_recall_down"],
                    "cross_direction_error": pred_metrics["cross_direction_error"],
                    "reference_distribution_mode": pred_metrics[
                        "reference_distribution_mode"
                    ],
                    "recent_ref_batches": pred_metrics["recent_ref_batches"],
                    "recent_ref_weight": pred_metrics["recent_ref_weight"],
                    "active_class_min_frac": pred_metrics["active_class_min_frac"],
                    "min_val_samples_per_active_class": pred_metrics[
                        "min_val_samples_per_active_class"
                    ],
                    "active_class_ids": pred_metrics["active_class_ids"],
                    "reference_distribution": pred_metrics["reference_distribution"],
                    "recent_class_counts": pred_metrics["recent_class_counts"],
                    "window_class_counts": pred_metrics["window_class_counts"],
                    "train_class_counts": pred_metrics["train_class_counts"],
                    "val_class_counts": pred_metrics["val_class_counts"],
                    "total_class_counts": pred_metrics["total_class_counts"],
                    "leakage_guard": pred_metrics["leakage_guard"],
                }
                _write_batch_metadata(
                    path=step_dir / "batch_metadata.json",
                    run_id=run_id,
                    model_name=model_name,
                    timeframe=tf,
                    target_col=target_col,
                    feature_target_col=feature_target_col,
                    pred_batch=pred_batch,
                    train_end=train_end,
                    step=step_num,
                    batch_dir=step_dir,
                    study_name=study_name,
                    study_path=study_path,
                    start_timestamp=start_timestamp,
                    end_timestamp=end_timestamp,
                    optuna_overrides=unit["overrides"],
                    data_signature=data_sig,
                    config_signature=config_sig,
                    git_info=git_info,
                    metrics=metrics,
                    artifacts=artifacts,
                )

                _update_run_model_index(
                    index_path=run_index_path,
                    run_id=run_id,
                    model_name=model_name,
                    timeframe=tf,
                    target_col=target_col,
                    feature_target_col=feature_target_col,
                    pred_batch=pred_batch,
                    step=step_num,
                    batch_dir=step_dir,
                    artifacts=artifacts,
                )

                all_results[model_key].append(
                    {
                        "step": step_num,
                        "batch": pred_batch,
                        "accuracy": acc,
                        "log_loss": loss,
                        "n_predictions": len(y_pred),
                    }
                )

                for i in range(len(y_pred)):
                    all_predictions[model_key].append(
                        {
                            "timestamp": timestamps[i],
                            "pred": int(y_pred[i]),
                            "actual": int(y_actual[i]),
                            "prob_max": float(proba[i].max()),
                        }
                    )

            except Exception as e:
                if verbose:
                    print(f"  {model_key}: ERROR - {e}")
                    import traceback

                    traceback.print_exc()

        if verbose:
            if step_tables:
                print("\n  Step class metrics:")
                for model_key, table in step_tables.items():
                    print(f"\n  {model_key}:")
                    print(table)
            aligned_summary = _format_aligned_step_summary(
                step_predictions=step_predictions,
                timeframes_order=timeframes,
            )
            if aligned_summary:
                print("\n  Step aligned bars summary (shared close timestamps):")
                print(aligned_summary)
            print(f"\n  Step {step_num} completed in {time.time() - step_start:.1f}s")

    # Final summary
    if verbose:
        print()
        print("#" * 80)
        print("#  FINAL SUMMARY")
        print("#" * 80)

        for model_key in all_predictions:
            preds = all_predictions[model_key]
            if not preds:
                continue

            y_pred = np.array([p["pred"] for p in preds])
            y_actual = np.array([p["actual"] for p in preds])
            class_names = model_class_names.get(model_key)
            if not class_names:
                n_classes = int(max(y_pred.max(initial=0), y_actual.max(initial=0)) + 1)
                class_names = [f"class_{i}" for i in range(n_classes)]
            n_classes = len(class_names)

            print(f"\n{model_key}:")
            print(f"  Total predictions: {len(y_pred):,}")
            print(f"  Overall accuracy: {(y_pred == y_actual).mean():.1%}")
            dir_acc = compute_directional_accuracy(y_actual, y_pred, class_names)
            dir_prec_up = compute_directional_precision(
                y_actual, y_pred, class_names, direction=1
            )
            dir_prec_down = compute_directional_precision(
                y_actual, y_pred, class_names, direction=0
            )
            dir_rec_up = compute_directional_recall(
                y_actual, y_pred, class_names, direction=1
            )
            dir_rec_down = compute_directional_recall(
                y_actual, y_pred, class_names, direction=0
            )
            cross_dir_err = compute_cross_direction_error_rate(
                y_actual, y_pred, class_names
            )
            print(
                "  Directional: "
                f"Acc={dir_acc:.1%}, "
                f"Prec(up/down)={dir_prec_up:.1%}/{dir_prec_down:.1%}, "
                f"Rec(up/down)={dir_rec_up:.1%}/{dir_rec_down:.1%}, "
                f"CrossErr={cross_dir_err:.1%}"
            )

            # Overall per-class metrics table
            class_acc = {}
            for c in range(n_classes):
                mask = y_actual == c
                if mask.sum() > 0:
                    class_acc[c] = (y_pred[mask] == c).mean()
            prec, rec, _, _ = precision_recall_fscore_support(
                y_actual,
                y_pred,
                labels=list(range(n_classes)),
                zero_division=0,
            )
            print("\n  Overall class metrics:")
            print(
                _format_class_table(
                    tuple(class_names), y_actual, y_pred, class_acc, prec, rec
                )
            )

            # Overall confusion heatmap
            conf_arr = confusion_matrix(
                y_actual, y_pred, labels=list(range(n_classes))
            )
            print("\n  Overall confusion (% of all predictions, + correct / - incorrect):")
            print(_format_confusion_table(tuple(class_names), conf_arr))

            print("\n  Classification Report:")
            all_labels = list(range(len(class_names)))
            print(
                classification_report(
                    y_actual,
                    y_pred,
                    labels=all_labels,
                    target_names=list(class_names),
                    zero_division=0,
                )
            )

    # Save run summary
    run_summary = {
        "run_id": run_id,
        "completed_at": datetime.now().isoformat(),
        "total_time_seconds": time.time() - t_start,
        "n_steps": n_steps,
        "results": dict(all_results),
    }
    with open(run_dir / "run_summary.json", "w") as f:
        json.dump(run_summary, f, indent=2, default=str)

    if verbose:
        print(f"\nRun summary saved: {run_dir / 'run_summary.json'}")
        print(f"\nTotal time: {time.time() - t_start:.1f}s")

    return {
        "run_id": run_id,
        "results": dict(all_results),
        "predictions": dict(all_predictions),
        "optimization_results": opt_results,
        "run_dir": run_dir,
    }
