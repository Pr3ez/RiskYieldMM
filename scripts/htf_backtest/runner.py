"""
Model-Orchestrated HTF Backtest Runner
======================================

Top-level dispatcher that runs one or multiple model-specific HTF backtests
inside the same run_id while keeping artifacts isolated by model/timeframe/target.
"""

from __future__ import annotations

from .configuration import build_backtest_maps


def _resolve_model_runner(model_name: str):
    """Return model-specific run function."""
    if model_name == "lightgbm":
        from .lightgbm.base_optimizer import run_walk_forward_backtest as _runner

        return _runner
    if model_name == "catboost":
        from .catboost.base_optimizer import run_walk_forward_backtest as _runner

        return _runner
    raise ValueError(
        f"Unsupported model '{model_name}'. "
        "Add it to scripts/htf_backtest/runner.py::_resolve_model_runner."
    )


def run_walk_forward_backtest_models(
    *,
    model_names: list[str] | None = None,
    model_name: str = "lightgbm",
    model_specs_by_model: dict | None = None,
    n_steps: int | None = None,
    timeframes: list[str] | None = None,
    timeframes_by_model: dict | None = None,
    run_description: str = "Walk-forward optimization: multi-target classification",
    verbose: bool = True,
    debug_batches: bool = False,
    optuna_overrides: dict | None = None,
    run_id: str | None = None,
    resume: bool = False,
    resume_mode: str = "continue",
    allow_override_mismatch: bool = False,
    optuna_overrides_by_model: dict | None = None,
    targets_by_model: dict | None = None,
    n_classes_by_model: dict | None = None,
    class_names_by_model: dict | None = None,
    feature_source_by_model: dict | None = None,
    target_registry: dict | None = None,
) -> dict:
    """
    Run HTF backtest for one or multiple models.

    Notes:
    - First model uses caller-provided `resume`/`run_id`.
    - Additional models are appended into the same run_id with `resume=True`,
      so outputs remain grouped under one run while isolated per model.
    """
    if model_specs_by_model is not None:
        resolved = build_backtest_maps(
            model_specs_by_model=model_specs_by_model,
            target_registry=target_registry,
        )
        timeframes_by_model = timeframes_by_model or resolved["timeframes_by_model"]
        targets_by_model = targets_by_model or resolved["targets_by_model"]
        n_classes_by_model = n_classes_by_model or resolved["n_classes_by_model"]
        class_names_by_model = (
            class_names_by_model or resolved["class_names_by_model"]
        )
        feature_source_by_model = (
            feature_source_by_model or resolved["feature_source_by_model"]
        )
        optuna_overrides_by_model = (
            optuna_overrides_by_model or resolved["optuna_overrides_by_model"]
        )
        target_registry = target_registry or resolved["target_registry"]
        if model_names is None:
            model_names = list(resolved["timeframes_by_model"].keys())

    active_models = model_names or [model_name]
    if not active_models:
        raise ValueError("model_names cannot be empty")

    # Preserve order while removing duplicates
    deduped_models: list[str] = []
    for m in active_models:
        m = str(m)
        if m not in deduped_models:
            deduped_models.append(m)

    model_results: dict[str, dict] = {}
    effective_run_id = run_id

    for idx, m in enumerate(deduped_models):
        runner = _resolve_model_runner(m)
        model_resume = resume if idx == 0 else True
        model_timeframes = (
            list(timeframes_by_model.get(m))
            if timeframes_by_model and timeframes_by_model.get(m) is not None
            else timeframes
        )

        result = runner(
            n_steps=n_steps,
            timeframes=model_timeframes,
            run_description=run_description,
            verbose=verbose,
            debug_batches=debug_batches,
            optuna_overrides=optuna_overrides,
            run_id=effective_run_id,
            resume=model_resume,
            resume_mode=resume_mode,
            allow_override_mismatch=allow_override_mismatch,
            model_name=m,
            optuna_overrides_by_model=optuna_overrides_by_model,
            targets_by_model=targets_by_model,
            n_classes_by_model=n_classes_by_model,
            class_names_by_model=class_names_by_model,
            feature_source_by_model=feature_source_by_model,
            target_registry=target_registry,
        )

        effective_run_id = result.get("run_id", effective_run_id)
        model_results[m] = result

    # Preserve single-model return shape for backward compatibility.
    if len(deduped_models) == 1:
        return model_results[deduped_models[0]]

    return {
        "run_id": effective_run_id,
        "models": model_results,
    }


def run_walk_forward_backtest(**kwargs) -> dict:
    """
    Backward-compatible alias to model-orchestrated runner.
    """
    return run_walk_forward_backtest_models(**kwargs)
