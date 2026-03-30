"""
RiskYieldMM Analysis Package
============================

Modular analysis tools for walk-forward position prediction.

Modules:
- config: Centralized configuration
- data: Data loading and target generation
- features: Feature analysis (domains, importance, IC/ICIR)
- models: Model training and evaluation

- viz: Visualization utilities

Usage:
    from scripts.analysis import config, data, features, models, backtest

    # Load data with targets
    df = data.load_analysis_data()

    # Analyze features
    ic_results = features.compute_ic_analysis(df)


"""
from . import config, data, features, models

# Keep analysis utilities importable in headless/runtime-only environments
# where plotting dependencies are intentionally absent.
try:
    from . import viz
except ModuleNotFoundError as exc:
    if exc.name not in {"matplotlib", "matplotlib.pyplot"}:
        raise
    viz = None

__all__ = ["config", "data", "features", "models", "viz"]
