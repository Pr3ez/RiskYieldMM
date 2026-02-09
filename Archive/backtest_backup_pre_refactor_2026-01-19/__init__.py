"""
Backtest Package - Modular ML Backtest System

This package provides a modular architecture for ML-based backtesting:

Subpackages:
    domain/   - Core config and business entities
    core/     - Pure functions (ensemble, metrics)
    models/   - ML model implementations (LSTM, etc.)
    adapters/ - Data loading and output
    services/ - Orchestration (training, backtest)

Usage:
    from backtest import run_sync_backtest, SyncBacktestConfig
"""

__version__ = "2.0.0"

# Re-exports will be added as modules are extracted
# from .services.backtest import run_sync_backtest
# from .domain.config import SyncBacktestConfig, PerModelConfig
