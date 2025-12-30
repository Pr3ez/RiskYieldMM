"""
Target-specific model training and optimization.

This package implements a dual-layer walk-forward ML pipeline for 20 target-horizon
combinations: 5 targets × 4 horizons.

Architecture:
    scripts/target_models/
    ├── __init__.py         # Package exports
    ├── config.py           # Target configs, hyperparameter spaces
    ├── registry.py         # 20 target-horizon registry, data loading
    ├── pipeline.py         # Pipeline orchestrator for all targets
    ├── run_full_eval.py    # Full evaluation script
    ├── ARCHITECTURE.md     # Detailed architecture documentation
    ├── core/               # Walk-forward window management
    │   ├── window.py       # Single-layer walk-forward
    │   └── aligned_dual_window.py  # Dual-layer (L1 helpers → L2 supervised)
    ├── helpers/            # Layer 1: Unsupervised helper models (61 features)
    │   ├── ensemble.py     # HelperEnsemble coordinator
    │   └── *.py            # IF, CUSUM, GARCH, HMM, Kalman helpers
    └── models/             # Layer 2: Supervised model ensemble
        ├── ensemble.py     # ModelEnsemble (CatBoost + LightGBM + Linear)
        └── *.py            # Individual model wrappers

Datasets available in data/datasets/:
    - direction_{1,3,6,12}bar.parquet    — Binary classification (up/down)
    - returns_{1,3,6,12}bar.parquet      — Regression (forward returns)
    - volatility_{1,3,6,12}bar.parquet   — Regression (|forward returns|)
    - vol_regime_{1,3,6,12}bar.parquet   — Multiclass (LOW/MED/HIGH)
    - trend_regime_{1,3,6,12}bar.parquet — Binary classification (up/down trend)

Usage:
    # Validate all 20 targets
    python -m scripts.target_models.registry

    # Run pipeline
    python -m scripts.target_models.pipeline
"""

from .config import TARGETS, CVConfig, TargetConfig
from .pipeline import (
    EnsembleAggregator,
    EnsemblePrediction,
    PipelineConfig,
    PipelineOrchestrator,
    PositionSizer,
    PositionSizingResult,
    TargetPrediction,
    TargetRunner,
    run_full_pipeline,
    run_single_target,
)
from .registry import (
    ALL_HORIZONS,
    ALL_TARGETS,
    TARGET_REGISTRY,
    TargetSpec,
    get_summary_table,
    get_target_spec,
    iterate_all_targets,
    iterate_by_task_type,
    load_all_targets,
    load_target_data,
    load_target_data_polars,
    validate_all_targets,
)

__all__ = [
    # Config
    "CVConfig",
    "TargetConfig",
    "TARGETS",
    # Registry
    "TARGET_REGISTRY",
    "ALL_TARGETS",
    "ALL_HORIZONS",
    "TargetSpec",
    "get_target_spec",
    "load_target_data",
    "load_target_data_polars",
    "load_all_targets",
    "iterate_all_targets",
    "iterate_by_task_type",
    "validate_all_targets",
    "get_summary_table",
    # Pipeline orchestrator
    "PipelineConfig",
    "PipelineOrchestrator",
    "TargetRunner",
    "EnsembleAggregator",
    "PositionSizer",
    "TargetPrediction",
    "EnsemblePrediction",
    "PositionSizingResult",
    "run_full_pipeline",
    "run_single_target",
]
