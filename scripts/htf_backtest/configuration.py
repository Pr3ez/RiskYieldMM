"""
HTF Backtest Configuration Builder
==================================

Utilities to build runner-ready maps from a single declarative config:
model -> timeframe -> target.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


def _deep_merge_dict(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge dictionaries (override wins)."""
    out = deepcopy(base)
    for key, value in override.items():
        if (
            key in out
            and isinstance(out[key], dict)
            and isinstance(value, dict)
        ):
            out[key] = _deep_merge_dict(out[key], value)
        else:
            out[key] = deepcopy(value)
    return out


def _normalize_task_type(task_type: str | None, n_classes: int) -> str:
    if task_type:
        return str(task_type)
    return "binary" if int(n_classes) == 2 else "multiclass"


def merge_backtest_specs(
    base_specs: dict[str, Any],
    override_specs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Deep-merge backtest model specs.

    Typical usage:
    - keep stable defaults in `base_specs`
    - apply run-specific edits in `override_specs`
    - receive a fully merged spec without mutating inputs
    """
    if not isinstance(base_specs, dict) or not base_specs:
        raise ValueError("base_specs must be a non-empty dict")
    if override_specs is None:
        return deepcopy(base_specs)
    if not isinstance(override_specs, dict):
        raise ValueError("override_specs must be a dict or None")
    return _deep_merge_dict(base_specs, override_specs)


def build_backtest_maps(
    model_specs_by_model: dict[str, Any],
    target_registry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Build all backtest config maps from a declarative model spec.

    Expected spec shape:
    {
      "lightgbm": {
        "timeframes": {
          "5m": {
            "shared_optuna": {...},    # optional
            "targets": {
              "target_4class": {
                "n_classes": 4,
                "class_names": [...],
                "feature_source": "target_4class",  # optional, defaults to target key
                "task_type": "multiclass",          # optional
                "optuna": {...},                    # optional target-specific overrides
              }
            }
          }
        }
      }
    }
    """
    if not model_specs_by_model:
        raise ValueError("model_specs_by_model cannot be empty")

    registry = deepcopy(target_registry) if target_registry else {}
    timeframes_by_model: dict[str, list[str]] = {}
    targets_by_model: dict[str, dict[str, list[str]]] = {}
    n_classes_by_model: dict[str, dict[str, dict[str, int]]] = {}
    class_names_by_model: dict[str, dict[str, dict[str, list[str]]]] = {}
    feature_source_by_model: dict[str, dict[str, dict[str, str]]] = {}
    optuna_overrides_by_model: dict[str, dict[str, dict[str, dict[str, Any]]]] = {}

    for model_name, model_spec in model_specs_by_model.items():
        tfs = model_spec.get("timeframes", {})
        if not isinstance(tfs, dict) or not tfs:
            raise ValueError(
                f"model '{model_name}' must define non-empty 'timeframes' dict"
            )

        timeframes_by_model[model_name] = []
        targets_by_model[model_name] = {}
        n_classes_by_model[model_name] = {}
        class_names_by_model[model_name] = {}
        feature_source_by_model[model_name] = {}
        optuna_overrides_by_model[model_name] = {}

        for tf, tf_spec in tfs.items():
            shared_optuna = tf_spec.get("shared_optuna", {})
            targets = tf_spec.get("targets", {})
            if not isinstance(targets, dict) or not targets:
                raise ValueError(
                    f"model '{model_name}' timeframe '{tf}' must define non-empty 'targets' dict"
                )
            if not isinstance(shared_optuna, dict):
                raise ValueError(
                    f"model '{model_name}' timeframe '{tf}' shared_optuna must be a dict"
                )

            timeframes_by_model[model_name].append(tf)
            targets_by_model[model_name][tf] = []
            n_classes_by_model[model_name][tf] = {}
            class_names_by_model[model_name][tf] = {}
            feature_source_by_model[model_name][tf] = {}
            optuna_overrides_by_model[model_name][tf] = {}

            for target_name, target_spec in targets.items():
                if not isinstance(target_spec, dict):
                    raise ValueError(
                        f"model '{model_name}' timeframe '{tf}' target '{target_name}' spec must be a dict"
                    )

                if "n_classes" not in target_spec:
                    raise ValueError(
                        f"model '{model_name}' timeframe '{tf}' target '{target_name}' missing n_classes"
                    )
                if "class_names" not in target_spec:
                    raise ValueError(
                        f"model '{model_name}' timeframe '{tf}' target '{target_name}' missing class_names"
                    )

                n_classes = int(target_spec["n_classes"])
                class_names = list(target_spec["class_names"])
                if n_classes <= 1:
                    raise ValueError(
                        f"model '{model_name}' timeframe '{tf}' target '{target_name}' "
                        f"has invalid n_classes={n_classes}"
                    )
                if len(class_names) != n_classes:
                    raise ValueError(
                        f"model '{model_name}' timeframe '{tf}' target '{target_name}' "
                        f"has class_names len={len(class_names)} but n_classes={n_classes}"
                    )

                feature_source = str(target_spec.get("feature_source", target_name))
                target_optuna = target_spec.get("optuna", {})
                if not isinstance(target_optuna, dict):
                    raise ValueError(
                        f"model '{model_name}' timeframe '{tf}' target '{target_name}' optuna must be a dict"
                    )
                merged_optuna = _deep_merge_dict(shared_optuna, target_optuna)

                targets_by_model[model_name][tf].append(target_name)
                n_classes_by_model[model_name][tf][target_name] = n_classes
                class_names_by_model[model_name][tf][target_name] = class_names
                feature_source_by_model[model_name][tf][target_name] = feature_source
                optuna_overrides_by_model[model_name][tf][target_name] = merged_optuna

                task_type = _normalize_task_type(
                    target_spec.get("task_type"), n_classes
                )
                if target_name not in registry:
                    registry[target_name] = {
                        "task_type": task_type,
                        "n_classes": n_classes,
                        "class_names": class_names,
                    }
                else:
                    existing = registry[target_name]
                    if int(existing.get("n_classes", n_classes)) != n_classes:
                        raise ValueError(
                            f"target_registry mismatch for '{target_name}': "
                            f"n_classes {existing.get('n_classes')} != {n_classes}"
                        )
                    existing_names = list(existing.get("class_names", class_names))
                    if existing_names != class_names:
                        raise ValueError(
                            f"target_registry mismatch for '{target_name}': class_names differ"
                        )

    return {
        "timeframes_by_model": timeframes_by_model,
        "targets_by_model": targets_by_model,
        "n_classes_by_model": n_classes_by_model,
        "class_names_by_model": class_names_by_model,
        "feature_source_by_model": feature_source_by_model,
        "optuna_overrides_by_model": optuna_overrides_by_model,
        "target_registry": registry,
    }


def summarize_backtest_maps(resolved_maps: dict[str, Any]) -> str:
    """Human-readable summary of resolved model/timeframe/target config."""
    lines: list[str] = []
    tfs_map = resolved_maps.get("timeframes_by_model", {})
    targets_map = resolved_maps.get("targets_by_model", {})
    for model_name, tfs in tfs_map.items():
        lines.append(f"{model_name}:")
        for tf in tfs:
            targets = targets_map.get(model_name, {}).get(tf, [])
            lines.append(f"  {tf}: {', '.join(targets)}")
    return "\n".join(lines)
