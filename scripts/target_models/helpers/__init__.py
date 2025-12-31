"""
Layer 1 Helper Models for Dual-Layer Walk-Forward.

Helper models are unsupervised/semi-supervised models that generate
features for the supervised Layer 2 models. Each helper is trained
on Layer 1 windows and generates predictions for Layer 2 data.

Helpers:
    - HMM4: 4-state market regime detection (9 features)
    - HMM5: 5-state volatility regime detection (10 features)
    - GARCH: Conditional volatility estimation (8 features)
    - IsolationForest: Multi-level anomaly detection (12 features)
    - KalmanFilter: 3D state estimation (7 features)
    - CUSUM: Change point detection (12 features)

Total: ~58 features per target-horizon

Architecture:
    Layer 1 (fit helpers)     Layer 2 (supervised)
    ─────────────────────     ────────────────────
    [train][cal][val]──gap──>[train][cal][val][pred]
                               ↑
                    helper features added here

Usage:
    from scripts.target_models.helpers import (
        create_helper_ensemble,
        HelperEnsemble,
        EnsembleOutput,
    )

    # Create ensemble for specific target-horizon
    ensemble = create_helper_ensemble("volatility", horizon=6)

    # Fit on Layer 1 train data
    ensemble.fit(X_train)

    # Generate features for Layer 2 data
    output = ensemble.transform(X_layer2)
    X_enriched = output.features  # DataFrame with 58 features
"""

from scripts.target_models.helpers.base import BaseHelper, HelperConfig, HelperOutput
from scripts.target_models.helpers.bocpd import BOCPDHelper, create_bocpd_helper
from scripts.target_models.helpers.cusum import CUSUMHelper, create_cusum_helper
from scripts.target_models.helpers.egarch import EGARCHHelper, create_egarch_helper
from scripts.target_models.helpers.ensemble import (
    EnsembleOutput,
    HelperEnsemble,
    create_helper_ensemble,
)
from scripts.target_models.helpers.evt_pot import EVTPOTHelper, create_evt_pot_helper
from scripts.target_models.helpers.garch import GARCHHelper, create_garch_helper
from scripts.target_models.helpers.helper_selection import (
    get_helper_summary,
    get_helpers_for_target,
    get_incremental_helpers,
)
from scripts.target_models.helpers.hmm import (
    HMMHelper,
    MarketRegimeHMM,
    VolatilityRegimeHMM,
    create_market_regime_hmm,
    create_volatility_regime_hmm,
)
from scripts.target_models.helpers.icir_config import (
    DEFAULT_ICIR_CONFIG,
    ICIR_CONFIG_DISABLED,
    ICIR_CONFIG_LENIENT,
    ICIR_CONFIG_STRICT,
    ICIRConfig,
    get_icir_config,
)
from scripts.target_models.helpers.icir_selection import (
    apply_correlation_filter,
    compute_rolling_icir,
    select_features_full_pipeline,
)
from scripts.target_models.helpers.isolation_forest import (
    IsolationForestHelper,
    create_isolation_forest_helper,
)
from scripts.target_models.helpers.kalman import KalmanHelper, create_kalman_helper
from scripts.target_models.helpers.optimized_config_loader import (
    IMPROVED_CONFIGS,
    OptimizedL2Params,
    OptimizedModelParams,
    get_all_optimized_configs,
    get_optimized_icir_config,
    get_optimized_l2_params,
    get_optimized_model_params,
    is_config_optimized,
)
from scripts.target_models.helpers.ou import OUHelper, create_ou_helper

__all__ = [
    # Base classes
    "BaseHelper",
    "HelperConfig",
    "HelperOutput",
    # Ensemble
    "HelperEnsemble",
    "EnsembleOutput",
    "create_helper_ensemble",
    # ICIR configuration
    "ICIRConfig",
    "DEFAULT_ICIR_CONFIG",
    "ICIR_CONFIG_STRICT",
    "ICIR_CONFIG_LENIENT",
    "ICIR_CONFIG_DISABLED",
    "get_icir_config",
    # ICIR selection
    "compute_rolling_icir",
    "apply_correlation_filter",
    "select_features_full_pipeline",
    # Optimized config loader (L2 optimization results)
    "IMPROVED_CONFIGS",
    "OptimizedModelParams",
    "OptimizedL2Params",
    "get_optimized_icir_config",
    "get_optimized_model_params",
    "get_optimized_l2_params",
    "is_config_optimized",
    "get_all_optimized_configs",
    # Helper selection
    "get_helpers_for_target",
    "get_helper_summary",
    "get_incremental_helpers",
    # Individual helpers
    "IsolationForestHelper",
    "create_isolation_forest_helper",
    "CUSUMHelper",
    "create_cusum_helper",
    "GARCHHelper",
    "create_garch_helper",
    "HMMHelper",
    "MarketRegimeHMM",
    "VolatilityRegimeHMM",
    "create_market_regime_hmm",
    "create_volatility_regime_hmm",
    "KalmanHelper",
    "create_kalman_helper",
    # New helpers (v2)
    "EVTPOTHelper",
    "create_evt_pot_helper",
    "OUHelper",
    "create_ou_helper",
    "BOCPDHelper",
    "create_bocpd_helper",
    "EGARCHHelper",
    "create_egarch_helper",
]
