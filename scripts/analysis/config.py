"""
Centralized Configuration for Analysis
======================================

All constants, paths, and parameters in one place.
"""

from dataclasses import dataclass
from pathlib import Path

# =============================================================================
# PATHS
# =============================================================================

PROJECT_ROOT = Path("/media/przem/linux_data/RiskYieldMM")
DATA_DIR = PROJECT_ROOT / "data"
PLOTS_DIR = DATA_DIR / "analysis" / "plots"
RESULTS_DIR = DATA_DIR / "analysis" / "results"

# Data files
FEATURES_FILE = DATA_DIR / "features_8h.parquet"
RAW_FILE = DATA_DIR / "merged_8h_raw.parquet"
ANALYSIS_FILE = DATA_DIR / "analysis_8h.parquet"

# Ensure directories exist
PLOTS_DIR.mkdir(parents=True, exist_ok=True)
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# =============================================================================
# FORWARD RETURN HORIZONS
# =============================================================================

FORWARD_HORIZONS: dict[int, str] = {
    1: "8h",  # 1 bar = 8 hours
    3: "24h",  # 3 bars = 1 day
    6: "48h",  # 6 bars = 2 days
    12: "96h",  # 12 bars = 4 days
}

# Maximum lookback/horizon for purge/embargo gaps (prevents look-ahead bias)
MAX_LOOKBACK_BARS: int = 21  # Max rolling window in features (21 bars)
MAX_HORIZON_BARS: int = 12  # Max forward return horizon (12 bars)

# =============================================================================
# WALK-FORWARD CONFIGURATION
# =============================================================================


@dataclass
class WalkForwardConfig:
    """Walk-forward window configuration."""

    train_size: int = 1000  # Training window (bars)
    cal_size: int = 100  # Calibration window
    val_size: int = 100  # Validation window
    pred_size: int = 1  # Prediction window (1 bar at a time)
    step_size: int = 1  # Step size between iterations
    min_train_samples: int = 100  # Minimum samples to train


WF_CONFIG = WalkForwardConfig()

# =============================================================================
# MODEL CONFIGURATION
# =============================================================================


@dataclass
class ModelConfig:
    """Model hyperparameters."""

    random_state: int = 42
    n_cv_splits: int = 5

    # CatBoost direction
    cb_iterations: int = 500
    cb_depth: int = 6
    cb_learning_rate: float = 0.03
    cb_l2_reg: float = 10.0
    cb_early_stopping: int = 50

    # LightGBM direction
    lgb_n_estimators: int = 500
    lgb_max_depth: int = 6
    lgb_learning_rate: float = 0.03
    lgb_reg_lambda: float = 10.0

    # Volatility model
    vol_iterations: int = 500
    vol_depth: int = 6
    vol_learning_rate: float = 0.03

    # Returns regression
    returns_alpha: float = 10.0

    # Sample weighting
    half_life_bars: int = 500
    min_sample_weight: float = 0.1


MODEL_CONFIG = ModelConfig()

# =============================================================================
# POSITION SIZING CONFIGURATION
# =============================================================================


@dataclass
class PositionConfig:
    """Position sizing parameters."""

    max_leverage: float = 2.0
    confidence_threshold: float = 0.55  # Min prob distance from 0.5
    vol_threshold_high: float = 0.02  # High vol threshold
    vol_reduction_floor: float = 0.25  # Min vol multiplier


POSITION_CONFIG = PositionConfig()

# =============================================================================
# ANALYSIS CONFIGURATION
# =============================================================================


@dataclass
class AnalysisConfig:
    """Feature analysis parameters."""

    significance_level: float = 0.05
    top_n_features: int = 20
    ic_rolling_window: int = 126  # ~6 weeks of 8h bars
    ic_min_periods: int = 63
    correlation_threshold: float = 0.9  # For redundancy detection


ANALYSIS_CONFIG = AnalysisConfig()

# =============================================================================
# FEATURE DOMAINS
# =============================================================================

FEATURE_DOMAIN_PREFIXES: dict[str, list[str]] = {
    "Momentum": ["M_P_", "M_N_roc"],
    "Volatility": ["V_"],
    "Trend": ["M_T_"],
    "Oscillator": ["rsi", "stochastic", "pctB"],
    "Funding": ["F_I_"],
    "Premium": ["D_F_"],
    "OpenInterest": ["oi", "openInterest", "L_S_"],
    "Volume": ["volume", "volOi", "L_M_"],
    "Candlestick": ["C_N_", "B_C_"],
    "Sentiment": ["S_", "longShort"],
}

# =============================================================================
# TARGET COLUMN NAMES
# =============================================================================

TARGET_COLS = [
    "y_direction",
    "y_volatility",
    "y_direction_strength",
    "y_forward_return_1",
    "y_forward_return_3",
    "y_forward_return_6",
    "y_forward_return_12",
    "y_vol_regime",
    "y_trend_regime",
]

META_COLS = ["timestamp", "RAW_close", "rolling_vol_21"]
