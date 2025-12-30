"""
RiskYieldMM Analysis Package
============================

Modular analysis tools for walk-forward position prediction.

Modules:
- config: Centralized configuration
- data: Data loading and target generation
- features: Feature analysis (domains, importance, IC/ICIR)
- models: Model training and evaluation
- backtest: Walk-forward backtesting
- viz: Visualization utilities

Usage:
    from scripts.analysis import config, data, features, models, backtest

    # Load data with targets
    df = data.load_analysis_data()

    # Analyze features
    ic_results = features.compute_ic_analysis(df)

    # Run backtest
    results = backtest.run_walk_forward(df)
"""

from . import backtest, config, data, features, models, viz

__all__ = ["config", "data", "features", "models", "backtest", "viz"]
