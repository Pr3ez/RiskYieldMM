# %% CELL 1: SLIDING WINDOW WALK-FORWARD PREDICTIONS
# ============================================================================
# Walk-Forward Prediction System with 4-Window Architecture
# Layout: [TRAIN] → [CAL] → [VAL] → [PRED]
# Full documentation: WF_DOCS.md
# ============================================================================
#
# ⭐ FAST START: Run wf_warmup.py first to skip initial iterations!
#   python wf_warmup.py --iterations 200 --output wf_checkpoint.pkl
# Then this script will automatically resume from the checkpoint.
# ============================================================================

import gc
import os
import time
import warnings
from dataclasses import dataclass

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

# ============================================================================
# CHECKPOINT RESUME CONFIGURATION
# ============================================================================
# Two modes:
#   FULL_RESUME: Load everything (iteration, TP/FP, Hull, features)
#   FEATURES_ONLY: Load only feature state (calibrators, config history), reset metrics
USE_CHECKPOINT_RESUME = True  # Set to False to always start from scratch
USE_FEATURES_ONLY_RESUME = (
    False  # Set True to load features but reset metrics (TP/FP from 0)
)
CHECKPOINT_PATH = "wf_checkpoint.pkl"  # Path to warmup checkpoint

# ============================================================================
# PRODUCTION MODE CONFIGURATION
# ============================================================================
# Two modes for the walk-forward system:
#   OPTIMIZE MODE (default): Run full backtest from start to end
#   PRODUCTION MODE: Run only last N iterations to prepare state for live predictions
#
# In PRODUCTION MODE:
#   - Runs only last PRODUCTION_WARMUP_ITERATIONS of training data
#   - Builds all required state (calibrators, rolling buffers, position sizing)
#   - Saves checkpoint ready for live predictions
#   - Much faster: ~200 iterations instead of full 758+
#
# ============================================================================
# ⭐ DEPLOYMENT MODE CONFIGURATION
# ============================================================================
# DEPLOY_MODE controls the entire workflow:
#   'backtest'  - Full backtest from scratch (default, for optimization)
#   'warmup'    - Run last N iterations to build state, save checkpoint
#   'live'      - Load checkpoint, make single prediction, save updated state
#   'auto'      - Warmup if no checkpoint exists, else live prediction
#
# Can be overridden via environment variable: WF_DEPLOY_MODE
import os as _os

DEPLOY_MODE = _os.environ.get(
    "WF_DEPLOY_MODE", "backtest"
)  # Options: 'backtest', 'warmup', 'live', 'auto'

# Warmup configuration
WARMUP_ITERATIONS = int(
    _os.environ.get("WARMUP_ITERATIONS", "30")
)  # Iterations to run in warmup mode
DEPLOY_CHECKPOINT_PATH = "deploy_checkpoint.pkl"  # Unified checkpoint path

# Live configuration
LIVE_LAGGED_EVALUATION = True  # Use lagged targets to update TP/FP buffers

# Derived flags (for backward compatibility) - computed AFTER mode resolution
# These will be updated in the DEPLOY MODE ROUTING section
PRODUCTION_MODE = False
LIVE_MODE = False
PRODUCTION_WARMUP_ITERATIONS = WARMUP_ITERATIONS
PRODUCTION_CHECKPOINT_PATH = DEPLOY_CHECKPOINT_PATH
PRODUCTION_AUTO_SAVE = True

# ============================================================================
# FORCE GPU MEMORY CLEANUP (for notebook stability)
# ============================================================================
gc.collect()

# Temporal safeguards: See WF_DOCS.md for detailed leakage prevention rules
try:
    import torch

    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        torch.cuda.synchronize()
        print("Cleared PyTorch GPU cache")
except ImportError:
    pass

from collections import deque

from catboost import CatBoostClassifier, CatBoostRegressor
from lightgbm import LGBMClassifier

# Import signal aggregator for combining weak signals
from signal_aggregator import SignalAggregator
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import r2_score, roc_auc_score
from wf_adaptive_scorer import AdaptiveMultiPeriodScorerV3

# ============================================================================
# IMPORT CONFIGURATION FROM wf_config.py
# ============================================================================
from wf_config import (
    ADAPTIVE_HALF_LIFE,
    ADAPTIVE_LOOKBACK_FOR_P,
    AUC_CONFIDENCE_STRENGTH,
    AUC_MIN_FOR_CONFIDENCE,
    BASIC_FEATURE_PATTERN,
    CALIBRATION_BUFFER_SIZE,
    CALIBRATION_METHOD,
    CONFIG_GRID,
    # Model params base
    DIR_MODEL_PARAMS_BASE,
    DIRECTION_FEATURE_GROUPS,
    DIRECTION_TARGET,
    DRIFT_CHECK_INTERVAL,
    DRIFT_DEPTH_REDUCTION,
    DRIFT_L2_MULTIPLIER,
    DRIFT_PSI_THRESHOLD,
    # Ensemble
    ENSEMBLE_MODE,
    # Feature exclusion
    EXCLUDE_FROM_FEATURES,
    FEATURE_LAG_PERIODS_FALLBACK,
    # Feature selection
    FEATURE_SELECTION_PERCENT,
    FEATURE_SELECTION_PHASE2_PERCENT,
    HALF_LIFE_SAMPLES,
    INSTABILITY_TRANSITION_THRESHOLD,
    MANUAL_WF_CAL,
    MANUAL_WF_TRAIN,
    MANUAL_WF_VAL,
    MAX_ADAPTIVE_HALF_LIFE,
    MAX_TRAIN_SHRINK_RATIO,
    META_BUFFER_MAX_SAMPLES,
    META_BUFFER_MAX_WINDOWS,
    META_STACKER_MAX_DEPTH,
    META_STACKER_MIN_SAMPLES,
    META_STACKER_MIN_SAMPLES_LEAF,
    META_STACKER_N_ESTIMATORS,
    MIN_ADAPTIVE_HALF_LIFE,
    MIN_CAL_WINDOW,
    MIN_CALIBRATION_POSITIVES,
    MIN_CALIBRATION_SAMPLES,
    MIN_SAMPLE_WEIGHT,
    MIN_TRAIN_WINDOW_ADAPTIVE,
    MIN_VAL_WINDOW,
    # Multi-config tracking
    MULTI_CONFIG_TRACKING,
    N_TOP_CONFIGS,
    OPTUNA_RETUNE_ON_DRIFT,
    OPTUNA_RETUNE_TIMEOUT,
    OPTUNA_TIMEOUT_SECONDS,
    PACF_MAX_LAGS,
    PACF_MAX_SELECTED_LAGS,
    PACF_SIGNIFICANCE_LEVEL,
    PARTIAL_DATA_PATH,
    # Data paths
    PREPROCESSED_TRAIN_PATH,
    REGIME_P_MISMATCH_THRESHOLD,
    REGIME_PURITY_THRESHOLD,
    REGIME_THRESHOLD_ADJUSTMENTS,
    ROLLING_WINDOW_SIZE,
    # RSI
    RSI_PERIODS,
    # Shuffle
    SHUFFLE_VAL_CAL_POOL,
    # Threshold settings
    THRESHOLD_METHOD,
    # Adaptive windows
    USE_ADAPTIVE_WINDOWS_PER_ITERATION,
    USE_AUC_CONFIDENCE_ADJUSTMENT,
    # Window settings
    USE_AUTOMATIC_WINDOWS,
    # Feature sets
    USE_BASE_FEATURES,
    # Calibration
    USE_CLASS_BALANCING,
    USE_DRIFT_ADJUSTMENT,
    # Drift detection
    USE_DRIFT_DETECTION,
    USE_FOCUSED_FEATURES,
    USE_GPU,
    # Half-life weighting
    USE_HALF_LIFE_WEIGHTING,
    USE_HGB,
    # Optuna
    USE_OPTUNA_TUNING,
    USE_PACF_LAG_SELECTION,
    USE_PROBABILITY_CALIBRATION,
    # Regime-aware settings
    USE_REGIME_AWARE_TRAIN_SIZING,
    USE_REGIME_POS_RATE_THRESHOLD,
    USE_SIGNAL_AGGREGATION,
    USE_SINGLE_MODEL,
    USE_TWO_PHASE_FEATURE_SELECTION,
    VOL_MODEL_PARAMS_BASE,
    VOLATILITY_FEATURE_GROUPS,
    VOLATILITY_TARGET,
    # GPU setup function
    setup_gpu_params,
)
from wf_features import (
    RSI_PERIODS as WF_RSI_PERIODS,
)

# Import feature engineering functions (refactored)
from wf_features import (
    create_dual_ema_features,
    create_risk_guard_features,
    create_rsi_features,
)
from wf_hull_scorer import HullScorer

# Import Optuna tuning functions (refactored)
from wf_optuna import (
    run_optuna_tuning,
)

# Import new position sizing meta-model
from wf_position_sizing import calculate_position_v2
from wf_position_sizing_v3 import PositionSizingConfig, PositionSizingManager

# Import class modules
from wf_rolling_cal_buffer import RollingCalBuffer
from wf_rolling_meta_buffer import RollingMetaBuffer
from wf_stable_ensemble import StableConfigEnsemble

# Import our diagnostics module
from window_diagnostics import check_drift, compute_diagnostics

# ============================================================================
# GPU CONFIGURATION & MODEL PARAMS (from wf_config)
# ============================================================================
CATBOOST_GPU_PARAMS, USE_GPU = setup_gpu_params()
CATBOOST_VOL_PARAMS = CATBOOST_GPU_PARAMS.copy()

# Build full model params by combining base params with GPU params
DIR_MODEL_PARAMS = {**DIR_MODEL_PARAMS_BASE, **CATBOOST_GPU_PARAMS}
VOL_MODEL_PARAMS = {**VOL_MODEL_PARAMS_BASE, **CATBOOST_VOL_PARAMS}

# %%
# ============================================================================
# LOAD DATA
# ============================================================================
print("\n" + "=" * 80)
print("LOADING DATA")
print("=" * 80)
print("Loading preprocessed data...")
df_train = pd.read_csv(PREPROCESSED_TRAIN_PATH)
print(f"  Loaded training: {len(df_train):,} rows, {len(df_train.columns):,} columns")

# ⭐ Also load partial data for extended historical context in diagnostics
PARTIAL_DATA_PATH = (
    "/media/przem/w/kaggle/preprocessed_data/partial_with_all_features.csv"
)
try:
    df_partial = pd.read_csv(PARTIAL_DATA_PATH)
    print(
        f"  Loaded partial:  {len(df_partial):,} rows (for extended diagnostics context)"
    )
    # Combine for diagnostics - use full historical context
    df_for_diagnostics = pd.concat([df_train, df_partial], ignore_index=True)
    print(f"  Combined for diagnostics: {len(df_for_diagnostics):,} rows total")
except FileNotFoundError:
    print(
        f"  Partial data not found at {PARTIAL_DATA_PATH}, using train only for diagnostics"
    )
    df_for_diagnostics = df_train

# ============================================================================
# COMPUTE AUTOMATIC WINDOW SIZES
# ============================================================================
if USE_AUTOMATIC_WINDOWS:
    print("\n" + "=" * 80)
    print("COMPUTING AUTOMATIC WINDOW SIZES (per statistical requirements)")
    print("=" * 80)

    # ⭐ Compute diagnostics from COMBINED data (train + partial) for better historical context
    diagnostics = compute_diagnostics(
        df_for_diagnostics,
        returns_col="lagged_forward_returns",
        vol_col="volatility_target",
        label_col="direction_target",
        min_val_window=MIN_VAL_WINDOW,
        verbose=True,
    )

    # Extract diagnostic values
    M = diagnostics["M_memory_days"]
    R = diagnostics["R_days_since_break"]
    S = diagnostics["S_seasonality_days"]
    V = diagnostics["V_vol_cycle_days"]
    p = diagnostics["p_positive_rate"]

    # ════════════════════════════════════════════════════════════════
    # WINDOW FORMULAS (per your specification)
    # ════════════════════════════════════════════════════════════════

    # W_train = max(3M, 1.5R, 2S, 2V, 180)
    WF_TRAIN = diagnostics["W_train"]

    # W_val = max(V, S, 30) - for early stopping/HPO only
    WF_VAL = diagnostics["W_val"]

    # W_cal = max(200/p, V, 30) - SEPARATE from val, OOS only
    WF_CAL = max(MIN_CAL_WINDOW, int(np.ceil(200 / p)), V, 30)

    WF_PRED = 1

    # Store diagnostics
    DIAGNOSTICS = diagnostics
    CALIBRATION_METHOD = diagnostics["calibration_method"]

    print("\n  ════════════════════════════════════════════════════════════════")
    print(f"  WINDOW SIZES (computed from M={M}, R={R}, S={S}, V={V}, p={p:.3f}):")
    print("  ════════════════════════════════════════════════════════════════")
    print(f"    W_train = max(3×{M}, 1.5×{R}, 2×{S}, 2×{V}, 180) = {WF_TRAIN}")
    print(f"    W_val   = max({V}, {S}, 30, min={MIN_VAL_WINDOW}) = {WF_VAL}")
    print(f"    W_cal   = max(200/{p:.2f}, {V}, 30) = {WF_CAL}  [OOS for calibration]")
    print("  ════════════════════════════════════════════════════════════════")
    print("\n  ✅ CORRECT STAGE ORDER:")
    print(
        f"      [TRAIN:{WF_TRAIN}] → [CAL:{WF_CAL}] → [VAL:{WF_VAL}] → [PRED:{WF_PRED}]"
    )
    print("           ↓              ↓             ↓            ↓")
    print("       Fit model    Calibrate    Early stop    Apply")
else:
    WF_TRAIN = MANUAL_WF_TRAIN
    WF_VAL = MANUAL_WF_VAL
    WF_CAL = MANUAL_WF_CAL
    WF_PRED = 1
    CALIBRATION_METHOD = "none"  # Calibration disabled
    DIAGNOSTICS = None
    print(f"\n  Using manual windows: TRAIN={WF_TRAIN}, VAL={WF_VAL}, CAL={WF_CAL}")

# Total history needed: TRAIN + VAL + CAL before prediction
MIN_HISTORY = WF_TRAIN + WF_VAL + WF_CAL

# ⭐ Cleanup: free memory from combined diagnostics df if it exists
if "df_for_diagnostics" in dir() and df_for_diagnostics is not df_train:
    del df_for_diagnostics
    gc.collect()
if "df_partial" in dir():
    del df_partial
    gc.collect()

# ============================================================================
# FEATURE EXCLUSION
# ============================================================================
import re

EXCLUDE_FROM_FEATURES = [
    "forward_returns",
    "market_forward_excess_returns",
    "volatility_target",
    "direction_target",
    "date_id",
    "time_id",
    "row_id",
    "date",
    "timestamp",
    "symbol",
    "risk_free_rate",
]

BASIC_FEATURE_PATTERN = re.compile(r"^[A-Z]\d+$")

# ============================================================================
# BUILD FEATURE LIST
# ============================================================================
if USE_FOCUSED_FEATURES:
    # Use curated focused features - SEPARATE for Direction and Volatility
    print("\n" + "=" * 80)
    print("FOCUSED FEATURE MODE - Separate Features for Direction & Volatility")
    print("=" * 80)

    # Build DIRECTION features
    print("\n  DIRECTION FEATURES (regime/signal based, avg |corr|=0.053):")
    direction_features = []
    for group_name, features in DIRECTION_FEATURE_GROUPS.items():
        existing = [f for f in features if f in df_train.columns]
        direction_features.extend(existing)
        print(f"    {group_name:25s}: {len(existing)}/{len(features)}")

    # Build VOLATILITY features
    print("\n  VOLATILITY FEATURES (vol measures, avg |corr|=0.436):")
    volatility_features = []
    for group_name, features in VOLATILITY_FEATURE_GROUPS.items():
        existing = [f for f in features if f in df_train.columns]
        volatility_features.extend(existing)
        print(f"    {group_name:25s}: {len(existing)}/{len(features)}")

    # Store both feature sets
    direction_feature_cols = direction_features
    volatility_feature_cols = volatility_features

    # For backward compatibility, feature_cols = direction (main task)
    feature_cols = direction_features

    print(f"\n  Direction features: {len(direction_feature_cols)}")
    print(f"  Volatility features: {len(volatility_feature_cols)}")
    print(
        f"  Feature overlap: {len(set(direction_feature_cols) & set(volatility_feature_cols))}"
    )

else:
    # Use all computed features for both models
    feature_cols = [
        c
        for c in df_train.columns
        if c not in EXCLUDE_FROM_FEATURES
        and df_train[c].dtype
        in ["float64", "float32", "int64", "int32", "int8", "uint8"]
        and not c.startswith("__")
    ]

    basic_features_count = len(
        [c for c in df_train.columns if BASIC_FEATURE_PATTERN.match(c)]
    )

    if not USE_BASE_FEATURES:
        feature_cols = [c for c in feature_cols if not BASIC_FEATURE_PATTERN.match(c)]
        print(
            f"\n  Using {len(feature_cols)} COMPUTED features (excluding {basic_features_count} basic raw)"
        )
    else:
        print(
            f"\n  Using {len(feature_cols)} features (including {basic_features_count} basic raw)"
        )

    # Use same features for both models in non-focused mode
    direction_feature_cols = feature_cols
    volatility_feature_cols = feature_cols

# Create source_df first
source_df = df_train.copy()
total_rows = len(source_df)

# ════════════════════════════════════════════════════════════════════════════
# ⭐ CREATE LAGGED DIRECTION TARGET (for production-compatible TP/FP tracking)
# ════════════════════════════════════════════════════════════════════════════
# In production, we don't know today's actual outcome - only yesterday's (lagged)
# lagged_direction_target = direction_target from previous day
# This allows us to evaluate yesterday's prediction with known lagged outcome
LAGGED_DIRECTION_TARGET = "lagged_direction_target"
if "lagged_forward_returns" in source_df.columns:
    # Derive from lagged_forward_returns (already available, no leakage)
    source_df[LAGGED_DIRECTION_TARGET] = (
        source_df["lagged_forward_returns"] > 0
    ).astype(int)
    print(f"\n  ✅ Created {LAGGED_DIRECTION_TARGET} from lagged_forward_returns")
    print(
        f"     Distribution: {source_df[LAGGED_DIRECTION_TARGET].value_counts().to_dict()}"
    )
elif "direction_target" in source_df.columns:
    # Alternative: shift direction_target by 1 (same result)
    source_df[LAGGED_DIRECTION_TARGET] = source_df["direction_target"].shift(1)
    print(f"\n  ✅ Created {LAGGED_DIRECTION_TARGET} by shifting direction_target")
else:
    print(
        f"\n  ⚠️ WARNING: Could not create {LAGGED_DIRECTION_TARGET} - missing source columns"
    )
    LAGGED_DIRECTION_TARGET = None

# Use RSI_PERIODS from wf_features.py (imported as WF_RSI_PERIODS)
RSI_PERIODS = WF_RSI_PERIODS

# Apply RSI features (functions imported from wf_features.py)
print("\n" + "=" * 80)
print("RSI FEATURE ENGINEERING (TA-Style Rolling Indicator)")
print("=" * 80)
print("  ✅ Uses lagged_forward_returns (past realized returns, no future leak)")
print("  ✅ EWM calculation is causal (only looks backward in time)")
print("  ✅ Each RSI_t value depends only on data from [t-period, t]")
source_df, rsi_feature_cols = create_rsi_features(
    source_df, returns_col="lagged_forward_returns", periods=RSI_PERIODS
)
print(f"  Created {len(rsi_feature_cols)} RSI features:")
print(f"  Periods: {RSI_PERIODS}")
for col in rsi_feature_cols[:5]:  # Show first 5
    if col in source_df.columns:
        valid_vals = source_df[col].dropna()
        if len(valid_vals) > 0:
            print(
                f"    - {col}: mean={valid_vals.mean():.2f}, std={valid_vals.std():.2f}"
            )
if len(rsi_feature_cols) > 5:
    print(f"    ... and {len(rsi_feature_cols) - 5} more")

# Add RSI features to feature list
feature_cols = feature_cols + rsi_feature_cols
print(
    f"  Total features now: {len(feature_cols)} (added {len(rsi_feature_cols)} RSI features)"
)

# ============================================================================
# DUAL EMA FEATURES (Validated Leak-Free Direction & Volatility Predictors)
# ============================================================================
# These features apply dual EMA aggregation across 180 periods for multiple
# indicator families. Key insight: process periods 1→180 (short_first) vs
# 180→1 (long_first) to capture different temporal patterns.
#
# ⭐ VALIDATED OUT-OF-SAMPLE:
#   - Direction: RSI_ema_long_first (0.21 range), Skewness_ema_long_first (0.20)
#   - Volatility: Volatility_ema_long_first (0.90 corr!), Volatility_ema_divergence (-0.71)
# ============================================================================

# Apply Dual EMA Features (function imported from wf_features.py)
print("\n" + "=" * 80)
print("DUAL EMA FEATURES (Validated Direction & Volatility Predictors)")
print("=" * 80)
print("  ✅ Uses lagged_forward_returns (past realized returns, no future leak)")
print("  ✅ Dual EMA: short→long vs long→short captures different patterns")
print(
    "  ✅ Validated out-of-sample: 0.15-0.21 range (direction), 0.90 corr (volatility)"
)

source_df, dual_ema_feature_cols = create_dual_ema_features(
    source_df, returns_col="lagged_forward_returns", max_period=180
)

print(f"  Created {len(dual_ema_feature_cols)} dual EMA features:")
for col in dual_ema_feature_cols[:6]:  # Show first 6
    if col in source_df.columns:
        valid_vals = source_df[col].dropna()
        if len(valid_vals) > 0:
            print(
                f"    - {col}: mean={valid_vals.mean():.4f}, std={valid_vals.std():.4f}"
            )
if len(dual_ema_feature_cols) > 6:
    print(f"    ... and {len(dual_ema_feature_cols) - 6} more")

# Add dual EMA features to feature list
feature_cols = feature_cols + dual_ema_feature_cols
print(
    f"  Total features now: {len(feature_cols)} (added {len(dual_ema_feature_cols)} dual EMA features)"
)

# ============================================================================
# SIGNAL AGGREGATION CONFIGURATION (NO PRE-FITTING - DONE PER ITERATION)
# ============================================================================
# ⚠️  CRITICAL: Signal aggregator must be fitted PER ITERATION on TRAIN only
# Fitting on full dataset = LEAKAGE (uses future data)
#
# The aggregator will be:
#   1. Fitted on TRAIN window each iteration
#   2. Used to transform TRAIN, VAL, CAL, PRED windows
#   3. Never sees future data
#
aggregated_feature_cols = []  # Will be populated in first iteration

if USE_SIGNAL_AGGREGATION:
    print("\n" + "=" * 80)
    print("SIGNAL AGGREGATION (Per-Iteration on TRAIN - No Leakage)")
    print("=" * 80)
    print("  ✅ Aggregator will be fitted on TRAIN window each iteration")
    print("  ✅ Never sees VAL, CAL, or PRED data during fitting")
    print("  ✅ Creates features dynamically to prevent look-ahead bias")

    # Pre-compute which columns are signal candidates (but don't fit yet)
    signal_candidate_cols = [
        c
        for c in source_df.columns
        if any(
            p in c.lower()
            for p in [
                "anomaly",
                "regime",
                "state",
                "cusum",
                "changepoint",
                "vol_regime",
                "uptrend",
                "downtrend",
                "trend_",
            ]
        )
        and source_df[c].nunique() <= 10
    ]
    print(f"  Found {len(signal_candidate_cols)} signal candidate columns")
    print("  Aggregation will add ~10 meta-features per iteration")


# Apply risk guard features (function imported from wf_features.py)
print("\n" + "=" * 80)
print("RISK GUARD FEATURE ENGINEERING")
print("=" * 80)
source_df, risk_guard_cols = create_risk_guard_features(source_df)
print(f"  Created {len(risk_guard_cols)} risk guard features:")
for col in risk_guard_cols:
    if col in source_df.columns:
        print(
            f"    - {col}: mean={source_df[col].mean():.3f}, std={source_df[col].std():.3f}"
        )

# Add risk guard features to feature list
feature_cols = feature_cols + risk_guard_cols
print(
    f"  Total features now: {len(feature_cols)} (added {len(risk_guard_cols)} risk guards)"
)

engineered_features = rsi_feature_cols + risk_guard_cols
direction_feature_cols = direction_feature_cols + engineered_features
volatility_feature_cols = volatility_feature_cols + engineered_features
print(f"\n  Updated direction features: {len(direction_feature_cols)}")
print(f"  Updated volatility features: {len(volatility_feature_cols)}")


class NullStream:
    def write(self, msg):
        pass

    def flush(self):
        pass


NULL_STREAM = NullStream()

# Optuna settings imported from wf_config
import optuna

optuna.logging.set_verbosity(optuna.logging.WARNING)

# Note: run_optuna_tuning, calculate_optuna_search_space, and
# analyze_dataset_and_estimate_ranges are imported from wf_optuna.py


# Global instances (initialized before main loop)
config_scorer = None  # Will be initialized before walk-forward loop
config_ensemble = None  # Ensemble for probability/signal calculation

# Import utility functions from wf_functions.py
from wf_functions import (
    adjust_threshold_for_regime,
    calculate_half_life_weights,
    calculate_optimal_threshold,
    calculate_scale_pos_weight,
    compute_calibration_stats,
    select_top_features,
)

# ============================================================================
# CHECK IF WE CAN SKIP OPTUNA (checkpoint has params)
# ============================================================================
_skip_optuna = False
_checkpoint_params = None
if USE_CHECKPOINT_RESUME and os.path.exists(CHECKPOINT_PATH):
    try:
        import pickle

        with open(CHECKPOINT_PATH, "rb") as f:
            _checkpoint_params = pickle.load(f)
        if _checkpoint_params.get("catboost_params") and _checkpoint_params.get(
            "lightgbm_params"
        ):
            _skip_optuna = True
            print("\n  ✅ Checkpoint found with model params - SKIPPING Optuna tuning")
            print(f"     Checkpoint: {CHECKPOINT_PATH}")
    except Exception as e:
        print(f"  ⚠️ Could not pre-check checkpoint: {e}")

# ============================================================================
# INITIAL OPTUNA TUNING (on first window) - SKIPPED if checkpoint has params
# ============================================================================
if USE_OPTUNA_TUNING and not _skip_optuna:
    print("\n" + "=" * 80)
    print("OPTUNA HYPERPARAMETER TUNING (1-minute search)")
    print("=" * 80)

    # Use first window for tuning
    tune_pred_start = MIN_HISTORY
    tune_val_end = tune_pred_start
    tune_val_start = tune_val_end - WF_VAL
    tune_cal_end = tune_val_start
    tune_cal_start = tune_cal_end - WF_CAL
    tune_train_end = tune_cal_start
    tune_train_start = tune_train_end - WF_TRAIN

    # Prepare tuning data
    tune_train = source_df.iloc[tune_train_start:tune_train_end]
    tune_val = source_df.iloc[tune_val_start:tune_val_end]

    X_tune_train = tune_train[feature_cols].fillna(0)
    y_tune_train = tune_train[DIRECTION_TARGET]
    X_tune_val = tune_val[feature_cols].fillna(0)
    y_tune_val = tune_val[DIRECTION_TARGET]

    print(
        f"  Tuning window: TRAIN[{tune_train_start}:{tune_train_end}] VAL[{tune_val_start}:{tune_val_end}]"
    )
    print(f"  Train samples: {len(X_tune_train)}, Val samples: {len(X_tune_val)}")
    print(f"  Features: {len(feature_cols)}")

    # ⭐ Use the reusable run_optuna_tuning function - returns BOTH best CB and LGB
    optuna_results = run_optuna_tuning(
        X_tune_train,
        y_tune_train,
        X_tune_val,
        y_tune_val,
        timeout_sec=OPTUNA_TIMEOUT_SECONDS,
        gpu_params=CATBOOST_GPU_PARAMS,
        gap_size=WF_CAL + WF_VAL,
        verbose=True,
    )

    # ════════════════════════════════════════════════════════════════════════════
    # ⭐ ENSEMBLE MODE: Store BOTH CatBoost AND LightGBM params
    # ════════════════════════════════════════════════════════════════════════════
    best_cb_params = optuna_results["best_cb_params"]
    best_lgb_params = optuna_results["best_lgb_params"]

    # CatBoost params (always create, use defaults if no valid trial)
    if best_cb_params:
        CATBOOST_DIR_PARAMS = {
            "grow_policy": "Lossguide",
            "max_leaves": best_cb_params.get("num_leaves", 31),
            "depth": best_cb_params.get("max_depth", 8),
            "learning_rate": best_cb_params.get("learning_rate", 0.01),
            "iterations": best_cb_params.get("n_estimators", 1000),
            "l2_leaf_reg": best_cb_params.get("reg_lambda", 10.0),
            "min_data_in_leaf": best_cb_params.get("min_child_samples", 50),
            "subsample": best_cb_params.get("subsample", 0.8),
            "bootstrap_type": "Bernoulli",
            "has_time": True,
            "early_stopping_rounds": 300,
            "use_best_model": True,
            "loss_function": "Logloss",
            "eval_metric": "AUC",
            **CATBOOST_GPU_PARAMS,
        }
        print(
            f"\n  ✅ CatBoost params from Optuna (score: {optuna_results['best_cb_score']:.4f})"
        )
    else:
        # Fallback defaults
        CATBOOST_DIR_PARAMS = DIR_MODEL_PARAMS.copy()
        print("\n  ⚠️ CatBoost using fallback defaults (no valid Optuna trial)")

    # LightGBM params (always create, use defaults if no valid trial)
    # Detect GPU availability once
    lgb_device = "cpu"
    import os
    import sys

    for try_device in ["gpu", "cuda"]:
        try:
            with open(os.devnull, "w") as devnull:
                old_stdout, old_stderr = sys.stdout, sys.stderr
                sys.stdout, sys.stderr = devnull, devnull
                try:
                    import lightgbm as lgb

                    test_model = LGBMClassifier(
                        device=try_device, n_estimators=1, verbose=-1
                    )
                    lgb_device = try_device
                    del test_model
                finally:
                    sys.stdout, sys.stderr = old_stdout, old_stderr
            break
        except Exception:
            pass

    if best_lgb_params:
        LIGHTGBM_DIR_PARAMS = {
            "boosting_type": "gbdt",
            "num_leaves": best_lgb_params.get("num_leaves", 31),
            "max_depth": best_lgb_params.get("max_depth", 8),
            "learning_rate": best_lgb_params.get("learning_rate", 0.01),
            "n_estimators": best_lgb_params.get("n_estimators", 1000),
            "reg_lambda": best_lgb_params.get("reg_lambda", 10.0),
            "min_child_samples": best_lgb_params.get("min_child_samples", 50),
            "subsample": best_lgb_params.get("subsample", 0.8),
            "subsample_freq": 1,
            "objective": "binary",
            "metric": "auc",
            "verbose": -1,
        }
        if lgb_device != "cpu":
            LIGHTGBM_DIR_PARAMS["device"] = lgb_device
        else:
            LIGHTGBM_DIR_PARAMS["n_jobs"] = -1
        print(
            f"  ✅ LightGBM params from Optuna (score: {optuna_results['best_lgb_score']:.4f}, device: {lgb_device.upper()})"
        )
    else:
        # Fallback defaults
        LIGHTGBM_DIR_PARAMS = {
            "boosting_type": "gbdt",
            "num_leaves": 31,
            "max_depth": 8,
            "learning_rate": 0.01,
            "n_estimators": 1000,
            "reg_lambda": 10.0,
            "min_child_samples": 50,
            "subsample": 0.8,
            "subsample_freq": 1,
            "objective": "binary",
            "metric": "auc",
            "verbose": -1,
            "n_jobs": -1,
        }
        print("  ⚠️ LightGBM using fallback defaults (no valid Optuna trial)")

    # HistGradientBoosting params (not used when USE_HGB=False, but define for safety)
    HISTGB_DIR_PARAMS = {
        "max_iter": 200,
        "max_depth": 10,
        "max_leaf_nodes": 31,
        "min_samples_leaf": 40,
        "learning_rate": 0.02,
        "l2_regularization": 0.1,
    }

    # Also update DIR_MODEL_PARAMS for CatBoost (used in feature selection)
    DIR_MODEL_PARAMS.update(CATBOOST_DIR_PARAMS)

    print("\n  🎯 ENSEMBLE: CatBoost + LightGBM → Meta-Stacker")
    print("=" * 80)
elif _skip_optuna and _checkpoint_params:
    # ════════════════════════════════════════════════════════════════════════════
    # ⭐ USE PARAMS FROM CHECKPOINT (Optuna skipped)
    # ════════════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("USING MODEL PARAMS FROM CHECKPOINT (Optuna skipped)")
    print("=" * 80)

    CATBOOST_DIR_PARAMS = _checkpoint_params["catboost_params"]
    LIGHTGBM_DIR_PARAMS = _checkpoint_params["lightgbm_params"]
    HISTGB_DIR_PARAMS = _checkpoint_params.get(
        "histgb_params",
        {
            "max_iter": 200,
            "max_depth": 10,
            "max_leaf_nodes": 31,
            "min_samples_leaf": 40,
            "learning_rate": 0.02,
            "l2_regularization": 0.1,
        },
    )

    print("  ✅ CatBoost params loaded from checkpoint")
    print("  ✅ LightGBM params loaded from checkpoint")
    print("  🎯 ENSEMBLE: CatBoost + LightGBM → Meta-Stacker")
    print("=" * 80)
else:
    # Default params if no Optuna tuning and no checkpoint
    CATBOOST_DIR_PARAMS = DIR_MODEL_PARAMS.copy()
    LIGHTGBM_DIR_PARAMS = {
        "boosting_type": "gbdt",
        "num_leaves": 31,
        "max_depth": 8,
        "learning_rate": 0.01,
        "n_estimators": 1000,
        "reg_lambda": 10.0,
        "min_child_samples": 50,
        "subsample": 0.8,
        "subsample_freq": 1,
        "objective": "binary",
        "metric": "auc",
        "verbose": -1,
        "n_jobs": -1,
    }
    HISTGB_DIR_PARAMS = {
        "max_iter": 200,
        "max_depth": 10,
        "max_leaf_nodes": 31,
        "min_samples_leaf": 40,
        "learning_rate": 0.02,
        "l2_regularization": 0.1,
    }


# ============================================================================
# WALK-FORWARD TRAINING LOOP
# ============================================================================
print("\n" + "=" * 80)
print("WALK-FORWARD TRAINING (Sliding Window - IMPROVED 4-WINDOW ARCHITECTURE)")
print("=" * 80)

print("\n  ⭐ IMPROVED LAYOUT: CAL between TRAIN and VAL")
print(f"      [TRAIN:{WF_TRAIN}] → [CAL:{WF_CAL}] → [VAL:{WF_VAL}] → [PRED:{WF_PRED}]")
print("           ↓              ↓             ↓            ↓")
print("       Fit CB+LGB     Add to buffers Early stop   Apply")
print("                       Fit Platt/each")
print("                       Train LR Meta")
print("")
print("  ✅ ENSEMBLE: CatBoost + LightGBM → LogisticRegression Meta-Stacker")
print("  ✅ Per-model Platt calibration on rolling CAL buffers")
print("  ✅ VAL closest to PRED - meta trained on most recent patterns")

print("\nWalk-Forward Configuration:")
print(
    "  ┌─────────────────────────────────────────────────────────────────────────────┐"
)
print(
    f"  │  TRAIN: {WF_TRAIN:4d}  │  CAL: {WF_CAL:4d}  │  VAL: {WF_VAL:4d}  │  PRED: {WF_PRED:3d}  │  Total: {WF_TRAIN + WF_VAL + WF_CAL + WF_PRED:4d}  │"
)
print(
    "  └─────────────────────────────────────────────────────────────────────────────┘"
)
if USE_AUTOMATIC_WINDOWS and DIAGNOSTICS:
    print(
        f"  Diagnostics: M={DIAGNOSTICS['M_memory_days']}, R={DIAGNOSTICS['R_days_since_break']}, "
        f"S={DIAGNOSTICS['S_seasonality_days']}, V={DIAGNOSTICS['V_vol_cycle_days']}, "
        f"p={DIAGNOSTICS['p_positive_rate']:.3f}"
    )
print(
    f"  Calibration: {CALIBRATION_METHOD.upper()} per model (max {CALIBRATION_BUFFER_SIZE} windows, min {MIN_CALIBRATION_SAMPLES} samples)"
)
print("  Meta Stacker: LogisticRegression (linear combination of 3 calibrated probs)")
print(f"  Threshold: {THRESHOLD_METHOD.upper()} (computed on ensemble CAL probs)")
print(f"  Drift Detection: {'ENABLED' if USE_DRIFT_DETECTION else 'DISABLED'}")
print()

# ============================================================================
# ⭐ DEPLOY MODE ROUTING
# ============================================================================
first_pred_start = MIN_HISTORY
last_pred_start = total_rows - WF_PRED

# Check if checkpoint exists (for 'auto' mode decision)
_checkpoint_exists = os.path.exists(DEPLOY_CHECKPOINT_PATH)

# Resolve 'auto' mode
_effective_mode = DEPLOY_MODE
if DEPLOY_MODE == "auto":
    if _checkpoint_exists:
        _effective_mode = "live"
        print(f"{'=' * 80}")
        print("⭐ AUTO MODE: Checkpoint found → LIVE prediction")
        print(f"{'=' * 80}")
    else:
        _effective_mode = "warmup"
        print(f"{'=' * 80}")
        print("⭐ AUTO MODE: No checkpoint → WARMUP first")
        print(f"{'=' * 80}")
    print()

# Update derived flags based on effective mode/media/przem/w/kaggle/final-2.py
PRODUCTION_MODE = _effective_mode == "warmup"
LIVE_MODE = _effective_mode == "live"

if _effective_mode == "warmup":
    # Warmup mode: run only last N iterations to prepare state
    production_first_pred = max(MIN_HISTORY, last_pred_start - WARMUP_ITERATIONS + 1)
    first_pred_start = production_first_pred
    n_expected_iterations = min(
        WARMUP_ITERATIONS, last_pred_start - first_pred_start + 1
    )

    print(f"{'=' * 80}")
    print("⭐ WARMUP MODE")
    print(f"{'=' * 80}")
    print("  Purpose: Build state for live predictions")
    print(f"  Warmup iterations:    {WARMUP_ITERATIONS}")
    print(
        f"  Starting from row:    {first_pred_start} (skipping first {first_pred_start - MIN_HISTORY} iterations)"
    )
    print(f"  Ending at row:        {last_pred_start + WF_PRED}")
    print(f"  Checkpoint output:    {DEPLOY_CHECKPOINT_PATH}")
    print(f"{'=' * 80}")
    print()
    print("  📋 State that will be built:")
    print("     ✓ Optuna hyperparameters (from drift retune)")
    print("     ✓ Platt calibrators (cb_calibrator, lgb_calibrator)")
    print("     ✓ Meta-stacker (ensemble weights)")
    print(f"     ✓ Rolling TP/FP buffers ({WARMUP_ITERATIONS}/180 filled)")
    print("     ✓ Position sizing V3 state (ratio tracker)")
    print("     ✓ Config scorer EMA/RSI histories")
    print("     ✓ Hull scorer histories (HullB, HullF)")
    print(f"{'=' * 80}")
    print()

elif _effective_mode == "live":
    # Live mode: load checkpoint, make SINGLE prediction on latest data
    n_expected_iterations = 1  # Single prediction
    first_pred_start = last_pred_start  # Only predict on the LAST row

    print(f"{'=' * 80}")
    print("⭐ LIVE MODE")
    print(f"{'=' * 80}")
    print("  Purpose: Make single live prediction")
    print(f"  Checkpoint input:     {DEPLOY_CHECKPOINT_PATH}")
    print(f"  Prediction row:       {first_pred_start}")
    print(
        f"  Lagged evaluation:    {'ENABLED' if LIVE_LAGGED_EVALUATION else 'DISABLED'}"
    )
    print(f"{'=' * 80}")
    print()

    # Force checkpoint resume
    USE_CHECKPOINT_RESUME = True
    CHECKPOINT_PATH = DEPLOY_CHECKPOINT_PATH

else:
    # Backtest mode: full run from scratch
    n_expected_iterations = (last_pred_start - first_pred_start) // WF_PRED + 1

print("Dataset Statistics:")
print(f"  Total rows:               {total_rows:,}")
print(f"  First prediction at row:  {first_pred_start} (after TRAIN+CAL+VAL)")
print(f"  Last prediction ends at:  {total_rows}")
print(f"  Expected iterations:      {n_expected_iterations}")
if PRODUCTION_MODE:
    print("  Mode:                     WARMUP (building state for live)")
elif LIVE_MODE:
    print("  Mode:                     LIVE (single prediction)")
else:
    print("  Mode:                     BACKTEST (full optimization)")
print()

# Storage
walkforward_predictions = []
walkforward_iterations = []
drift_alerts = []
calibration_diagnostics = []  # ⭐ Track Brier/ECE per iteration
model_diversity_metrics = []  # ⭐ Track CB/LGB diversity per iteration

# ════════════════════════════════════════════════════════════════════════════
# ⭐ MULTI-CONFIG PARALLEL TRACKING (config from wf_config.py)
# ════════════════════════════════════════════════════════════════════════════
# Generate all config combinations
from itertools import product


def generate_config_combinations(grid):
    keys = list(grid.keys())
    values = [grid[k] for k in keys]
    configs = []
    for combo in product(*values):
        config = dict(zip(keys, combo))
        # ⭐ Include window variant in name: wo=original, ws=shrunk
        window_suffix = f"_w{config.get('window', 'original')[0]}"
        config_name = f"{config['model'][:3]}_{config['calibration'][:3]}_{config['threshold'][:3]}_auc{int(config['auc_adjust'])}_reg{int(config['regime_thr'])}{window_suffix}"
        config["name"] = config_name
        configs.append(config)
    return configs


ALL_CONFIGS = generate_config_combinations(CONFIG_GRID)
print(f"  Multi-Config Tracking: {len(ALL_CONFIGS)} configurations")
for i, cfg in enumerate(ALL_CONFIGS[:5]):
    print(f"    [{i + 1}] {cfg['name']}")
if len(ALL_CONFIGS) > 5:
    print(f"    ... and {len(ALL_CONFIGS) - 5} more")

# Rolling tracking deques (sizes from wf_config)
rolling_pred_types = deque(maxlen=ROLLING_WINDOW_SIZE)
rolling_actuals = deque(
    maxlen=ROLLING_WINDOW_SIZE
)  # Track actual market outcomes for baseline
rolling_market_returns = deque(
    maxlen=ROLLING_WINDOW_SIZE
)  # Rolling market returns for Mkt%
rolling_strategy_returns = deque(
    maxlen=ROLLING_WINDOW_SIZE
)  # Rolling strategy returns for Ret%

# ════════════════════════════════════════════════════════════════════════════
# ⭐ BENCHMARK vs BASELINE PARALLEL TRACKING
# ════════════════════════════════════════════════════════════════════════════
# Two parallel metrics tracked from the SAME probability/threshold inputs:
#
# BENCHMARK (gates-only, works from iteration 1):
#   - Uses: alpha gate + direction gate ONLY
#   - Position: 0.0 (fail) or 1.0 (pass)
#   - NO EMA/RSI scaling - purely gate-based
#   - Tracked from first iteration for consistent comparison
#
# BASELINE (full, works after ~194 iterations):
#   - Uses: alpha gate + direction gate + EMA/RSI scaling
#   - Position: 0.0-2.0 range with EMA bonus/danger penalty
#   - EMA data not ready until dual_ema_data.has_data=True (~194+ iters)
#   - Before warmup: same as benchmark (gates only, pos=1.0 when pass)
#
# Both track: TP, FP, TN, FN, accuracy, signal counts
# Analysis: Compare accuracy of gates-only vs gates+EMA over time

benchmark_tracker = {
    "tp": 0,
    "fp": 0,
    "tn": 0,
    "fn": 0,  # Total counts
    "signals": 0,  # Total SIGNAL_GENERATED (signal > 0)
    "no_signals": 0,  # Total gate failures (signal = 0)
    "rolling_results": deque(maxlen=ROLLING_WINDOW_SIZE),  # Recent TP/FP/TN/FN
}

baseline_tracker = {
    "tp": 0,
    "fp": 0,
    "tn": 0,
    "fn": 0,  # Total counts
    "signals": 0,  # Total SIGNAL_GENERATED (signal > 0)
    "warmup_signals": 0,  # Signals during warmup (no EMA)
    "full_signals": 0,  # Signals with EMA scaling
    "no_signals": 0,  # Total gate failures (signal = 0)
    "rolling_results": deque(maxlen=ROLLING_WINDOW_SIZE),  # Recent TP/FP/TN/FN
}

# ════════════════════════════════════════════════════════════════════════════
# ⭐ PRODUCTION-COMPATIBLE TP/FP TRACKER (uses lagged outcomes)
# ════════════════════════════════════════════════════════════════════════════
# In production, we don't know TODAY's outcome - only YESTERDAY's (lagged).
# This tracker evaluates YESTERDAY's prediction with today's lagged outcome.
# Flow:
#   - Iter N: Make prediction P_n, store it
# Storage for each config's results (for tracking/display only)
config_results = {
    cfg["name"]: {
        "config": cfg,
        "predictions": [],
        "rolling_tp": 0,
        "rolling_fp": 0,
        "rolling_tn": 0,
        "rolling_fn": 0,
        "total_correct": 0,
        "total_predictions": 0,
        "rolling_pred_types": deque(maxlen=ROLLING_WINDOW_SIZE),
    }
    for cfg in ALL_CONFIGS
}

# \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
# \u2b50 ENSEMBLE: PER-MODEL ROLLING CALIBRATION BUFFERS
# \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
# Each model gets its own buffer for Platt calibration - corrects individual bias
# Before combining with meta-stacker

cb_cal_buffer = RollingCalBuffer(
    max_windows=CALIBRATION_BUFFER_SIZE, max_samples=5000, name="CatBoost"
)
lgb_cal_buffer = RollingCalBuffer(
    max_windows=CALIBRATION_BUFFER_SIZE, max_samples=5000, name="LightGBM"
)
hgb_cal_buffer = RollingCalBuffer(
    max_windows=CALIBRATION_BUFFER_SIZE, max_samples=5000, name="HistGradientBoosting"
)

# ⭐ ROLLING META BUFFER: Accumulates past VAL windows for meta-stacker training
# This gives meta more data and allows it to adapt to changing conditions
meta_buffer = RollingMetaBuffer(
    max_windows=META_BUFFER_MAX_WINDOWS,
    max_samples=META_BUFFER_MAX_SAMPLES,
    name="MetaStacker",
)

cb_calibrator = None  # Platt calibrator for CatBoost
lgb_calibrator = None  # Platt calibrator for LightGBM
meta_stacker = None  # Meta-stacker (trained on rolling VAL buffer)

# ════════════════════════════════════════════════════════════════════════════
# ⭐ ADAPTIVE CONFIG SCORER INITIALIZATION - TWO PARALLEL SCORERS
# ════════════════════════════════════════════════════════════════════════════
# BACKTEST SCORER: Uses instant evaluation (today's actual) - for comparison
config_scorer = AdaptiveMultiPeriodScorerV3(
    min_samples_per_window=3,
    switch_threshold=0.20,  # 20% to switch TO new config
    leave_threshold=0.25,  # 25% to leave current (hysteresis)
    declining_threshold=0.15,  # 15% when current declining
    min_score_floor=2.0,  # Don't switch to weak configs
    switch_cooldown=5,  # Min 5 iters between switches
)

selected_config_name = None  # Will be set by scorer each iteration
print("  Adaptive Config Scorer initialized")

# ⭐ SHORT WINDOW for recent performance-based config selection
RATIO_WINDOW = 10  # Use last 10 iterations for TP/FP ratio (not cumulative 180)

# Initialize the ensemble for probability/signal calculation
config_ensemble = StableConfigEnsemble(
    config_scorer=config_scorer,
    min_ratio=1.05,  # Minimum TP/FP ratio for "stable"
    n_configs=N_TOP_CONFIGS,  # ⭐ Use configurable top N (default 10 for 96 configs)
    min_samples=30,  # Need 30 samples before using config
    ratio_window=RATIO_WINDOW,  # ⭐ Use SHORT window for ratio calculation
)
print(
    f"  Stable Config Ensemble: min_ratio=1.05, n_configs={N_TOP_CONFIGS}, ratio_window={RATIO_WINDOW}"
)

# Initialize Hull competition scorers (TWO separate scoring approaches)
# ⭐ HULL COMPETITION SCORERS - Both use ensemble_signal, different windows
# Run 1 (HullB): Cumulative from iteration 1 - measures full strategy history
# Run 2 (HullF): Rolling 180-day window - measures recent strategy performance
HULL_ROLLING_WINDOW = 180  # HullF uses rolling 180-day window

hull_scorer_benchmark = HullScorer(
    annualization_factor=252,  # Daily returns
    min_samples=1,  # Score immediately from first sample
)
hull_scorer_baseline = HullScorer(
    annualization_factor=252,  # Daily returns
    min_samples=1,  # Score immediately from first sample
)
print(
    f"  Hull Competition Scorers: HullB=cumulative(from iter 1), HullF=rolling({HULL_ROLLING_WINDOW}-day window)"
)

# ⭐ Initialize Position Sizing Manager V3 (clean pipeline)
# Hull-Optimal Mode: Conservative positions, regime-aware, targets consistent Hull score
position_sizing_config = PositionSizingConfig(
    # Basic settings
    ratio_window=50,  # Rolling window for TP/FP
    ratio_ema_alpha=0.1,  # EMA decay (higher = more recent weight)
    ratio_min_trades=10,  # Min trades before using ratio
    alignment_min_configs=3,  # Min configs for alignment
    alignment_weight=1.0,  # Alignment impact
    high_vol_reduction=0.70,  # Reduce in high vol
    base_position=1.0,  # Neutral = 100% equity
    max_position=2.0,  # Max = 2x leverage
    leverage_min_ratio=1.3,  # Need ratio >= 1.3 for leverage
    leverage_min_alignment=0.7,  # Need 70%+ alignment for leverage
    # Hull-Optimal: Enable for consistent Hull score growth
    use_hull_optimal=True,  # ⭐ ENABLED - targets consistent Hull score
    use_regime_override=False,  # Disabled - Hull-optimal handles regime
    use_adaptive_threshold=False,  # Disabled - Hull-optimal handles confidence
    use_hybrid3_sizing=False,  # Disabled - replaced by Hull-optimal
)
position_manager = PositionSizingManager(config=position_sizing_config)
print(
    f"  Position Sizing V3: window={position_sizing_config.ratio_window}, ema_alpha={position_sizing_config.ratio_ema_alpha}"
)

# ⭐ Market buy & hold equity tracker (for comparison)
market_equity = 1.0  # Start at 1.0, same as strategy

# ⭐ PRODUCTION-COMPATIBLE: Pending positions for lagged Hull evaluation
pending_hull_benchmark = None  # Stores position for next iteration's evaluation
pending_hull_baseline = None  # Stores position for next iteration's evaluation


# ⭐ PRODUCTION-COMPATIBLE: Pending predictions for lagged TP/FP evaluation
# In production, we don't know TODAY's outcome - only YESTERDAY's (lagged).
# Flow:
#   - Iter N: Make prediction P_N, store it in pending_*
#   - Iter N+1: Use lagged_direction_target to evaluate P_N → TP/FP/TN/FN
#   - This is production-compatible: we only use data available at prediction time
@dataclass
class PendingPrediction:
    """Stores a prediction awaiting evaluation with next day's lagged data."""

    pred_class: int  # Binary prediction (0 or 1)
    pred_prob: float  # Probability of UP
    threshold: float  # Threshold used for decision
    signal: float  # Position size (0.0-2.0)
    config_name: str  # Selected config
    iteration: int  # Which iteration made this prediction
    timestamp: str  # For logging/debugging
    config_predictions: dict  # Per-config predictions for multi-config evaluation


pending_prediction: PendingPrediction = (
    None  # Yesterday's prediction awaiting evaluation
)

# ============================================================================
# ⭐ CHECKPOINT RESUME: Load state from warmup if available
# ============================================================================
iteration = 0
pred_start = MIN_HISTORY
_checkpoint_loaded = False
_features_only_loaded = False

# OPTION 1: Full resume (load everything including TP/FP, Hull history)
if USE_CHECKPOINT_RESUME and os.path.exists(CHECKPOINT_PATH):
    try:
        from old.warmup_backup.wf_warmup import WarmupCheckpoint, load_checkpoint

        checkpoint = load_checkpoint(CHECKPOINT_PATH)

        if checkpoint is not None:
            # Restore iteration state
            iteration = checkpoint.iteration
            pred_start = checkpoint.pred_start

            # Restore model params
            CATBOOST_DIR_PARAMS = checkpoint.catboost_params
            LIGHTGBM_DIR_PARAMS = checkpoint.lightgbm_params
            HISTGB_DIR_PARAMS = checkpoint.histgb_params

            # Restore calibrators
            cb_calibrator = checkpoint.cb_calibrator
            lgb_calibrator = checkpoint.lgb_calibrator
            meta_stacker = checkpoint.meta_stacker

            # Restore scorer state (keeps LtEMA/StEMA/LtRSI/StRSI continuity)
            if getattr(checkpoint, "config_scorer_state", None):
                config_scorer.restore_state(checkpoint.config_scorer_state)

            # Restore Hull scorer histories
            def _sanitize_hull_history(hist_list):
                return [
                    h
                    for h in hist_list
                    if isinstance(h, dict)
                    and all(
                        k in h for k in ("position", "market_return", "risk_free_rate")
                    )
                ]

            hull_scorer_benchmark.history = _sanitize_hull_history(
                checkpoint.hull_benchmark_history
            )
            hull_scorer_baseline.history = _sanitize_hull_history(
                checkpoint.hull_baseline_history
            )

            # Restore trackers (ensure all expected keys exist)
            benchmark_tracker = checkpoint.benchmark_tracker
            if isinstance(benchmark_tracker.get("rolling_results"), list):
                benchmark_tracker["rolling_results"] = deque(
                    benchmark_tracker["rolling_results"], maxlen=ROLLING_WINDOW_SIZE
                )
            # Ensure all expected keys exist in benchmark_tracker
            benchmark_tracker.setdefault("tp", 0)
            benchmark_tracker.setdefault("fp", 0)
            benchmark_tracker.setdefault("tn", 0)
            benchmark_tracker.setdefault("fn", 0)
            benchmark_tracker.setdefault("signals", 0)
            benchmark_tracker.setdefault("no_signals", 0)
            benchmark_tracker.setdefault(
                "rolling_results", deque(maxlen=ROLLING_WINDOW_SIZE)
            )

            baseline_tracker = checkpoint.baseline_tracker
            if isinstance(baseline_tracker.get("rolling_results"), list):
                baseline_tracker["rolling_results"] = deque(
                    baseline_tracker["rolling_results"], maxlen=ROLLING_WINDOW_SIZE
                )
            # Ensure all expected keys exist in baseline_tracker
            baseline_tracker.setdefault("tp", 0)
            baseline_tracker.setdefault("fp", 0)
            baseline_tracker.setdefault("tn", 0)
            baseline_tracker.setdefault("fn", 0)
            baseline_tracker.setdefault("signals", 0)
            baseline_tracker.setdefault("warmup_signals", 0)
            baseline_tracker.setdefault("full_signals", 0)
            baseline_tracker.setdefault("no_signals", 0)
            baseline_tracker.setdefault(
                "rolling_results", deque(maxlen=ROLLING_WINDOW_SIZE)
            )

            # Restore rolling deques
            rolling_pred_types = deque(
                checkpoint.rolling_pred_types, maxlen=ROLLING_WINDOW_SIZE
            )
            rolling_actuals = deque(
                checkpoint.rolling_actuals, maxlen=ROLLING_WINDOW_SIZE
            )
            rolling_market_returns = deque(
                getattr(checkpoint, "rolling_market_returns", []),
                maxlen=ROLLING_WINDOW_SIZE,
            )
            rolling_strategy_returns = deque(
                getattr(checkpoint, "rolling_strategy_returns", []),
                maxlen=ROLLING_WINDOW_SIZE,
            )

            # ⭐ LIVE MODE: Restore pending prediction for lagged evaluation
            pending_pred_dict = getattr(checkpoint, "pending_prediction", None)
            if pending_pred_dict and isinstance(pending_pred_dict, dict):
                pending_prediction = PendingPrediction(**pending_pred_dict)
            else:
                pending_prediction = None

            # Restore predictions from warmup
            walkforward_predictions = checkpoint.warmup_predictions
            walkforward_iterations = checkpoint.warmup_iterations
            drift_alerts = checkpoint.drift_alerts
            calibration_diagnostics = checkpoint.calibration_diagnostics
            model_diversity_metrics = checkpoint.model_diversity_metrics

            _checkpoint_loaded = True

            print(f"\n{'=' * 80}")
            print(f"✅ FULL RESUME FROM CHECKPOINT: {CHECKPOINT_PATH}")
            print(f"{'=' * 80}")
            print(f"  Starting from iteration: {iteration + 1}")
            print(f"  Predictions loaded: {len(walkforward_predictions)}")
            print(f"  TP: {benchmark_tracker['tp']}, FP: {benchmark_tracker['fp']}")
            print(f"  Checkpoint created: {checkpoint.created_at}")
            print(f"  Warmup time was: {checkpoint.warmup_time_seconds:.1f}s")
            print(f"{'=' * 80}\n")
    except Exception as e:
        print(f"  ⚠️ Failed to load checkpoint: {e}")
        print("  Starting from scratch...")
        iteration = 0
        pred_start = MIN_HISTORY

# OPTION 2: Features-only resume (load calibrators/config history, reset metrics)
elif USE_FEATURES_ONLY_RESUME and os.path.exists(CHECKPOINT_PATH):
    try:
        from old.warmup_backup.wf_warmup import WarmupCheckpoint, load_checkpoint

        checkpoint = load_checkpoint(CHECKPOINT_PATH)

        if checkpoint is not None:
            # ⭐ LOAD ONLY FEATURE-RELATED STATE
            # Model params (from Optuna tuning)
            CATBOOST_DIR_PARAMS = checkpoint.catboost_params
            LIGHTGBM_DIR_PARAMS = checkpoint.lightgbm_params
            HISTGB_DIR_PARAMS = checkpoint.histgb_params

            # Calibrators (for probability calibration)
            cb_calibrator = checkpoint.cb_calibrator
            lgb_calibrator = checkpoint.lgb_calibrator
            meta_stacker = checkpoint.meta_stacker

            # Load scorer state and rebase iterations to start at 0 for fresh metrics
            if getattr(checkpoint, "config_scorer_state", None):
                config_scorer.restore_state(
                    checkpoint.config_scorer_state, rebase_to_zero=True
                )

            # rolling_pred_types for past_ratio gate (optional - can skip early)
            # Keep this for better feature computation
            rolling_pred_types = deque(
                checkpoint.rolling_pred_types, maxlen=ROLLING_WINDOW_SIZE
            )
            rolling_actuals = deque(
                checkpoint.rolling_actuals, maxlen=ROLLING_WINDOW_SIZE
            )
            rolling_market_returns = deque(
                getattr(checkpoint, "rolling_market_returns", []),
                maxlen=ROLLING_WINDOW_SIZE,
            )
            rolling_strategy_returns = deque(
                getattr(checkpoint, "rolling_strategy_returns", []),
                maxlen=ROLLING_WINDOW_SIZE,
            )

            # ⭐ LIVE MODE: Restore pending prediction for lagged evaluation
            pending_pred_dict = getattr(checkpoint, "pending_prediction", None)
            if pending_pred_dict and isinstance(pending_pred_dict, dict):
                pending_prediction = PendingPrediction(**pending_pred_dict)
            else:
                pending_prediction = None

            # ⭐ RESET METRICS-RELATED STATE
            # Start iteration from 0 (fresh metrics)
            iteration = 0
            pred_start = MIN_HISTORY

            # Hull scorers start fresh (clean Sharpe calculation)
            hull_scorer_benchmark.history = []
            hull_scorer_baseline.history = []

            # Trackers reset to 0 (clean TP/FP display)
            # benchmark_tracker already initialized to 0s above
            # baseline_tracker already initialized to 0s above

            # Predictions start fresh
            walkforward_predictions = []
            walkforward_iterations = []
            drift_alerts = []
            calibration_diagnostics = []
            model_diversity_metrics = []

            _features_only_loaded = True

            print(f"\n{'=' * 80}")
            print(f"✅ FEATURES-ONLY RESUME: {CHECKPOINT_PATH}")
            print(f"{'=' * 80}")
            print("  Mode: Load calibrators & config history, reset metrics")
            print("  Starting from iteration: 1 (fresh)")
            print("  TP/FP: 0/0 (reset)")
            print("  Hull scorers: reset (will show from iter 60)")
            print("  Calibrators: loaded from checkpoint")
            if getattr(checkpoint, "config_scorer_state", None):
                print("  Config scorer: EMA/RSI history loaded (rebased)")
            print(f"  rolling_pred_types: {len(rolling_pred_types)} samples loaded")
            print(f"  Checkpoint created: {checkpoint.created_at}")
            print(f"{'=' * 80}\n")
    except Exception as e:
        print(f"  ⚠️ Failed to load features-only checkpoint: {e}")
        print("  Starting from scratch...")
        iteration = 0
        pred_start = MIN_HISTORY

if not _checkpoint_loaded and not _features_only_loaded:
    iteration = 0
    pred_start = MIN_HISTORY

# ============================================================================
# ⭐ PRODUCTION MODE: Override pred_start to start from last N iterations
# ============================================================================
if PRODUCTION_MODE:
    # Calculate production start point (overrides any checkpoint loading)
    production_first_pred = max(
        MIN_HISTORY, (total_rows - WF_PRED) - PRODUCTION_WARMUP_ITERATIONS + 1
    )

    # Warn if checkpoint was loaded in production mode (unusual combination)
    if _checkpoint_loaded:
        print("\n  ⚠️ WARNING: PRODUCTION_MODE=True but checkpoint was loaded!")
        print("     Checkpoint state will be kept (TP/FP, calibrators, etc.)")
        print("     But pred_start will be overridden to production window.")
        print(
            "     This is unusual - consider setting USE_CHECKPOINT_RESUME=False for clean production warmup."
        )

    # Only override if we're starting from before production start
    if pred_start < production_first_pred:
        print(
            f"\n  ⚠️ PRODUCTION MODE: Overriding start from {pred_start} to {production_first_pred}"
        )
        pred_start = production_first_pred
        iteration = 0  # Reset iteration counter for production warmup

    # Also reset all state for clean production warmup
    if not _checkpoint_loaded:
        # Rolling buffers
        rolling_pred_types = deque(maxlen=ROLLING_WINDOW_SIZE)
        rolling_actuals = deque(maxlen=ROLLING_WINDOW_SIZE)
        rolling_market_returns = deque(maxlen=ROLLING_WINDOW_SIZE)
        rolling_strategy_returns = deque(maxlen=ROLLING_WINDOW_SIZE)

        # Prediction storage
        walkforward_predictions = []
        walkforward_iterations = []

        # Hull scorers
        hull_scorer_benchmark.history = []
        hull_scorer_baseline.history = []

        # Benchmark/baseline trackers
        benchmark_tracker = {
            "tp": 0,
            "fp": 0,
            "tn": 0,
            "fn": 0,
            "signals": 0,
            "no_signals": 0,
            "rolling_results": deque(maxlen=ROLLING_WINDOW_SIZE),
        }
        baseline_tracker = {
            "tp": 0,
            "fp": 0,
            "tn": 0,
            "fn": 0,
            "signals": 0,
            "warmup_signals": 0,
            "full_signals": 0,
            "no_signals": 0,
            "rolling_results": deque(maxlen=ROLLING_WINDOW_SIZE),
        }

        # ⭐ Reset config_results (per-config TP/FP tracking)
        config_results = {
            cfg["name"]: {
                "config": cfg,
                "predictions": [],
                "rolling_tp": 0,
                "rolling_fp": 0,
                "rolling_tn": 0,
                "rolling_fn": 0,
                "total_correct": 0,
                "total_predictions": 0,
                "rolling_pred_types": deque(maxlen=ROLLING_WINDOW_SIZE),
            }
            for cfg in ALL_CONFIGS
        }

        # ⭐ Reset position manager V3 (create fresh instance)
        position_manager = PositionSizingManager(config=position_sizing_config)

        # ⭐ Reset config scorer (fresh scoring state)
        config_scorer = AdaptiveMultiPeriodScorerV3(
            min_samples_per_window=3,
            switch_threshold=0.20,
            leave_threshold=0.25,
            declining_threshold=0.15,
            min_score_floor=2.0,
            switch_cooldown=5,
        )

        # ⭐ Reset config ensemble (with short ratio window)
        config_ensemble = StableConfigEnsemble(
            config_scorer=config_scorer,
            min_ratio=1.05,
            n_configs=N_TOP_CONFIGS,
            min_samples=30,
            ratio_window=RATIO_WINDOW,  # ⭐ Use SHORT window for ratio calculation
        )

        # Reset market equity
        market_equity = 1.0

        print("  ✅ Clean state initialized for production warmup")
        print("     - Rolling buffers: reset")
        print(f"     - Config results: reset ({len(ALL_CONFIGS)} configs)")
        print("     - Position manager V3: reset")
        print("     - Config scorer: reset")
        print("     - Hull scorers: reset")

# Print header - organized for readability with proper alignment
print()
print("=" * 185)
print("WALK-FORWARD PROGRESS (ENSEMBLE + ADAPTIVE CONFIG SELECTION)")
print("=" * 215)
# Fixed width columns
print(
    f"{'Iter':<7} {'TRAIN':^12} {'CAL':^12} {'VAL':^12} {'PRED':^12} {'CB':>5} {'LG':>5} {'Config':<20} {'Prob':>5} {'Thr':>5} {'P':>2} {'A':>2} {'Res':>3} {'TP':>4} {'FP':>4} {'Ratio':>6} {'Mkt':>6} {'Sig':>5} {'HullB':>6} {'HullF':>6} {'LtEMA':>6} {'StEMA':>6} {'LtRSI':>5} {'StRSI':>5} {'Time':>5} {'Mkt%':>7} {'Ret%':>7}"
)
print("-" * 215)

# ============================================================================
# MAIN LOOP
# ============================================================================
while pred_start < total_rows:
    iteration += 1
    iter_start_time = time.time()

    # ─────────────────────────────────────────────────────────────────
    # ⭐ STEP 0A: LAGGED EVALUATION (production-compatible TP/FP tracking)
    # ─────────────────────────────────────────────────────────────────
    # Evaluate YESTERDAY's prediction using TODAY's lagged_direction_target
    # This is the only production-compatible way to update TP/FP buffers
    #
    if LIVE_MODE and LIVE_LAGGED_EVALUATION and pending_prediction is not None:
        # Get lagged target for evaluation (represents yesterday's outcome)
        pred_slice_for_lagged = source_df.iloc[pred_start : pred_start + WF_PRED]

        if (
            LAGGED_DIRECTION_TARGET
            and LAGGED_DIRECTION_TARGET in pred_slice_for_lagged.columns
        ):
            lagged_actual = pred_slice_for_lagged[LAGGED_DIRECTION_TARGET].values[0]

            if not pd.isna(lagged_actual):
                lagged_actual_int = int(lagged_actual)

                # Evaluate pending prediction vs lagged actual
                pp = pending_prediction
                if pp.pred_class == 1 and lagged_actual_int == 1:
                    lagged_pred_type = "TP"
                elif pp.pred_class == 0 and lagged_actual_int == 0:
                    lagged_pred_type = "TN"
                elif pp.pred_class == 1 and lagged_actual_int == 0:
                    lagged_pred_type = "FP"
                else:
                    lagged_pred_type = "FN"

                # Update rolling buffers with lagged result
                rolling_pred_types.append(lagged_pred_type)
                rolling_actuals.append(lagged_actual_int)

                # Update position sizing manager
                if lagged_pred_type in ("TP", "TN", "FP", "FN"):
                    position_manager.update_result(lagged_pred_type)

                if iteration <= 10:
                    print(
                        f"    [LaggedEval] Iter {pp.iteration} pred={pp.pred_class} vs actual={lagged_actual_int} → {lagged_pred_type}"
                    )

        # Clear pending prediction after evaluation
        pending_prediction = None

    # ─────────────────────────────────────────────────────────────────
    # ⭐ STEP 0B: PER-ITERATION ADAPTIVE DIAGNOSTICS & WINDOW SIZING
    # ─────────────────────────────────────────────────────────────────
    # Recalculate diagnostics based on data available UP TO this point
    # This allows the model to adapt to current market regime
    #
    if USE_ADAPTIVE_WINDOWS_PER_ITERATION and iteration > 1:
        # Use data available before prediction point (no look-ahead)
        available_data_end = pred_start  # Data up to but not including pred_start

        # Calculate local positive rate from recent data
        lookback_start = max(0, available_data_end - ADAPTIVE_LOOKBACK_FOR_P)
        local_slice = source_df.iloc[lookback_start:available_data_end]

        if len(local_slice) >= 50 and DIRECTION_TARGET in local_slice.columns:
            local_p = float((local_slice[DIRECTION_TARGET] == 1).mean())

            # Recalculate window sizes based on local p
            # W_cal = max(200/p, V, 30) - more samples needed when p is extreme
            local_WF_CAL = max(
                MIN_CAL_WINDOW, int(np.ceil(200 / max(0.1, local_p))), 30
            )
            local_WF_CAL = min(local_WF_CAL, 500)  # Cap to prevent excessive size

            # Adjust half-life based on regime stability
            # If local p differs significantly from historical p, use shorter half-life
            # (less weight to recent data that may be regime-shifted)
            if ADAPTIVE_HALF_LIFE:
                historical_p = DIAGNOSTICS["p_positive_rate"] if DIAGNOSTICS else 0.55
                p_deviation = abs(local_p - historical_p)

                # More deviation = shorter half-life (less trust in recent patterns)
                # p_deviation of 0.10+ (e.g., 45% vs 55%) triggers shorter half-life
                if p_deviation > 0.08:
                    # Regime shift detected - reduce half-life significantly
                    adaptive_half_life = MIN_ADAPTIVE_HALF_LIFE
                    if iteration <= 10 or iteration % 100 == 0:
                        print(
                            f"    [AdaptiveHL] Regime shift: local_p={local_p:.1%} vs hist={historical_p:.1%} → half_life={adaptive_half_life}"
                        )
                elif p_deviation > 0.04:
                    # Moderate deviation - moderately reduce half-life
                    adaptive_half_life = int(
                        (MIN_ADAPTIVE_HALF_LIFE + MAX_ADAPTIVE_HALF_LIFE) / 2
                    )
                else:
                    # Stable regime - use normal half-life
                    adaptive_half_life = HALF_LIFE_SAMPLES

                # Store for use in weight calculation
                iter_half_life = adaptive_half_life
            else:
                iter_half_life = HALF_LIFE_SAMPLES

            # Update window sizes for this iteration
            iter_WF_CAL = local_WF_CAL
            iter_local_p = local_p
        else:
            # Not enough data, use defaults
            iter_WF_CAL = WF_CAL
            iter_half_life = HALF_LIFE_SAMPLES
            iter_local_p = 0.55
    else:
        # First iteration or adaptive disabled - use global values
        iter_WF_CAL = WF_CAL
        iter_half_life = HALF_LIFE_SAMPLES
        iter_local_p = DIAGNOSTICS["p_positive_rate"] if DIAGNOSTICS else 0.55

    # Use iteration-specific values (may be adapted or global)
    current_WF_CAL = iter_WF_CAL if USE_ADAPTIVE_WINDOWS_PER_ITERATION else WF_CAL
    current_half_life = (
        iter_half_life if USE_ADAPTIVE_WINDOWS_PER_ITERATION else HALF_LIFE_SAMPLES
    )

    # ════════════════════════════════════════════════════════════════════════════
    # ⭐ STEP 0b: READ REGIME STATE FROM PRE-COMPUTED FEATURES
    # ════════════════════════════════════════════════════════════════════════════
    # Read from row BEFORE pred_start (no look-ahead)
    # These features were pre-computed in preprocessing and contain:
    #   - Current regime state (Past Simple)
    #   - Regime duration (Past Perfect - "had been in regime for X days")
    #   - Transition activity (Past Perfect Continuous - "had been transitioning")
    #   - Historical tendency (Habit - "this regime used to have X% UP rate")
    #
    regime_row_idx = pred_start - 1

    # Default values (used if features not available)
    current_hmm_regime = 0
    current_hmm5_regime = 0
    regime_stable = 1
    regime_duration = 100
    transitions_5d = 0
    current_regime_pos_rate = 0.55
    current_regime_vol_pct = 0.5
    days_since_cp = 100

    if regime_row_idx >= 0:
        # Current regime state (Past Simple - "what regime ARE we in")
        if "hmm_regime" in source_df.columns:
            current_hmm_regime = source_df["hmm_regime"].iloc[regime_row_idx]
        if "hmm5_regime" in source_df.columns:
            current_hmm5_regime = source_df["hmm5_regime"].iloc[regime_row_idx]

        # Regime stability (Past Perfect - "had been stable")
        if "hmm_both_stable" in source_df.columns:
            regime_stable = source_df["hmm_both_stable"].iloc[regime_row_idx]
        if "hmm_regime_duration" in source_df.columns:
            regime_duration = source_df["hmm_regime_duration"].iloc[regime_row_idx]

        # Transition activity (Past Perfect Continuous - "had been transitioning")
        if "hmm4_transitions_5d" in source_df.columns:
            transitions_5d = source_df["hmm4_transitions_5d"].iloc[regime_row_idx]

        # Historical tendency of current regime (Habit - "used to")
        if "current_regime_pos_rate" in source_df.columns:
            current_regime_pos_rate = source_df["current_regime_pos_rate"].iloc[
                regime_row_idx
            ]
        if "current_regime_vol_pct" in source_df.columns:
            current_regime_vol_pct = source_df["current_regime_vol_pct"].iloc[
                regime_row_idx
            ]

        # Days since changepoint
        if "cusum_days_since_changepoint" in source_df.columns:
            days_since_cp = source_df["cusum_days_since_changepoint"].iloc[
                regime_row_idx
            ]

    # Store for use in threshold calculation (STEP 8)
    iter_regime_pos_rate = current_regime_pos_rate

    # ════════════════════════════════════════════════════════════════════════════
    # ⭐ STEP 0c: TRAIN WINDOW REGIME COMPATIBILITY CHECK
    # ════════════════════════════════════════════════════════════════════════════
    # Check if proposed TRAIN window has compatible regime composition.
    # If mismatch detected, shrink TRAIN to include only current regime data.
    #
    iter_WF_TRAIN = WF_TRAIN  # Start with global value

    if USE_REGIME_AWARE_TRAIN_SIZING and iteration > 1:
        # Proposed TRAIN window boundaries (before any adjustment)
        proposed_train_end = pred_start - WF_VAL - current_WF_CAL
        proposed_train_start = proposed_train_end - WF_TRAIN
        proposed_train_start = max(0, proposed_train_start)

        if proposed_train_end > proposed_train_start + 50:  # Need minimum data
            # Check regime composition in proposed TRAIN window
            if "hmm_regime" in source_df.columns:
                train_regimes = source_df["hmm_regime"].iloc[
                    proposed_train_start:proposed_train_end
                ]
                regime_purity = float((train_regimes == current_hmm_regime).mean())
            else:
                regime_purity = 1.0  # Assume pure if no regime data

            # Check positive rate in proposed TRAIN vs regime's historical tendency
            train_pos_rate = float(
                source_df[DIRECTION_TARGET]
                .iloc[proposed_train_start:proposed_train_end]
                .mean()
            )
            pos_rate_deviation = abs(train_pos_rate - current_regime_pos_rate)

            # Decision: Should we shrink TRAIN?
            should_shrink = False
            shrink_reasons = []

            if pos_rate_deviation > REGIME_P_MISMATCH_THRESHOLD:
                should_shrink = True
                shrink_reasons.append(f"p_dev={pos_rate_deviation:.2f}")

            if regime_purity < REGIME_PURITY_THRESHOLD:
                should_shrink = True
                shrink_reasons.append(f"purity={regime_purity:.2f}")

            if transitions_5d >= INSTABILITY_TRANSITION_THRESHOLD:
                should_shrink = True
                shrink_reasons.append(f"trans={transitions_5d}")

            if days_since_cp < WF_TRAIN * 0.3:
                # Recent changepoint - use data only from after changepoint
                should_shrink = True
                shrink_reasons.append(f"cp={days_since_cp}d")

            if should_shrink:
                # Calculate minimum acceptable TRAIN size
                min_new_train = int(WF_TRAIN * MAX_TRAIN_SHRINK_RATIO)
                min_new_train = max(min_new_train, MIN_TRAIN_WINDOW_ADAPTIVE)

                # Strategy: Use regime_duration or days_since_cp to determine new size
                if regime_duration > 0 and regime_duration < WF_TRAIN:
                    # Start from when current regime began
                    adjusted_train_size = min(int(regime_duration * 0.9), WF_TRAIN)
                    adjusted_train_size = max(adjusted_train_size, min_new_train)
                elif days_since_cp > 0 and days_since_cp < WF_TRAIN:
                    # Start from after changepoint
                    adjusted_train_size = min(int(days_since_cp * 0.9), WF_TRAIN)
                    adjusted_train_size = max(adjusted_train_size, min_new_train)
                else:
                    # Default shrink to minimum
                    adjusted_train_size = min_new_train

                iter_WF_TRAIN = adjusted_train_size

                if iteration <= 10 or iteration % 100 == 0:
                    print(
                        f"    [RegimeAdapt] TRAIN shrunk: {WF_TRAIN}→{iter_WF_TRAIN} ({', '.join(shrink_reasons)})"
                    )
            else:
                iter_WF_TRAIN = WF_TRAIN
        else:
            iter_WF_TRAIN = WF_TRAIN
    else:
        iter_WF_TRAIN = WF_TRAIN

    # ════════════════════════════════════════════════════════════════════════════
    # ⭐ STEP 0d: COMPUTE BOTH WINDOW VARIANTS FOR DUAL-TRAINING
    # ════════════════════════════════════════════════════════════════════════════
    # ORIGINAL windows: Use full sizes (WF_TRAIN, current_WF_CAL, WF_VAL)
    # SHRUNK windows: Use proportionally shrunk sizes when regime triggers
    #
    # Both variants will be used to train separate models, allowing the config
    # scoring system to determine which window strategy works better.

    # Minimum window sizes for shrunk variant
    MIN_SHRUNK_VAL = 50  # Minimum for early stopping viability
    MIN_SHRUNK_CAL = 100  # Minimum for Platt calibration

    # VARIANT A: ORIGINAL (always full size)
    windows_original = {
        "train": WF_TRAIN,
        "cal": current_WF_CAL,
        "val": WF_VAL,
    }

    # VARIANT B: SHRUNK (proportionally shrunk when regime triggers)
    if iter_WF_TRAIN < WF_TRAIN:
        shrink_ratio = iter_WF_TRAIN / WF_TRAIN
        shrunk_cal = max(MIN_SHRUNK_CAL, int(current_WF_CAL * shrink_ratio))
        shrunk_val = max(MIN_SHRUNK_VAL, int(WF_VAL * shrink_ratio))
        windows_shrunk = {
            "train": iter_WF_TRAIN,
            "cal": shrunk_cal,
            "val": shrunk_val,
        }
        has_shrunk_variant = True
        if iteration <= 10 or iteration % 100 == 0:
            print(
                f"    [WindowVariants] SHRUNK: TRAIN={iter_WF_TRAIN}, CAL={shrunk_cal}, VAL={shrunk_val} (ratio={shrink_ratio:.2f})"
            )
    else:
        # No shrink triggered - shrunk = original (no extra training needed)
        windows_shrunk = windows_original.copy()
        has_shrunk_variant = False

    # Store both for use in training loop
    window_variants = {
        "original": windows_original,
        "shrunk": windows_shrunk,
    }

    # ════════════════════════════════════════════════════════════════════════════
    # ⭐ VALIDATION LOGGING (first 5 iterations)
    # ════════════════════════════════════════════════════════════════════════════
    if iteration <= 5:
        print(
            f"    [WindowValidation] TRAIN={iter_WF_TRAIN}, CAL={current_WF_CAL}, half_life={current_half_life}"
        )
        print(
            f"    [RegimeState] hmm={current_hmm_regime}, stable={regime_stable}, dur={regime_duration}, trans5d={transitions_5d}"
        )
        print(
            f"    [RegimeTendency] regime_pos_rate={current_regime_pos_rate:.3f}, local_p={iter_local_p:.3f}"
        )

    # ─────────────────────────────────────────────────────────────────
    # STEP 1: CALCULATE WINDOW BOUNDARIES (IMPROVED 4-WINDOW ARCHITECTURE)
    # ─────────────────────────────────────────────────────────────────
    # ⭐ IMPROVED LAYOUT: CAL between TRAIN and VAL
    #
    # Layout: [---- TRAIN ----][-- CAL --][-- VAL --][PRED]
    #              ↑               ↑           ↑        ↑
    #         Fit model      Fit Platt   Early stop   Apply
    #         (CB⊆TRAIN)     (unused!)   (most recent)
    #
    # WHY THIS IS BETTER:
    #   1. CAL is closer to TRAIN - calibration on similar data
    #   2. CAL is truly unused - not for training OR early stopping
    #   3. VAL is most recent before PRED - early stopping on fresher patterns
    #   4. Generalizes better to PRED which is closest to VAL
    #
    pred_end = min(pred_start + WF_PRED, total_rows)

    # VAL window is immediately before PRED (for early stopping on most recent data)
    val_end = pred_start
    val_start = val_end - WF_VAL

    # CAL window is before VAL (truly unused gap for calibration)
    # ⭐ Use adaptive CAL size when enabled
    cal_end = val_start
    cal_start = cal_end - current_WF_CAL  # Uses adaptive or global value

    # TRAIN window is before CAL
    # ⭐ Use regime-aware adaptive TRAIN size when enabled
    train_end = cal_start
    train_start = (
        train_end - iter_WF_TRAIN
    )  # Uses adaptive regime-aware value from STEP 0c

    # ⭐ FEATURE SELECTION WINDOW: Use TRAIN + CAL (safe - only removes features)
    fs_start = train_start
    fs_end = cal_end  # TRAIN + CAL (not VAL to keep VAL truly held-out)

    # ⭐ CLASS BALANCE WINDOW: Use TRAIN only (conservative for financial ML)
    cb_start = train_start
    cb_end = train_end  # TRAIN only

    if train_start < 0:
        pred_start += WF_PRED
        continue

    # ⭐ TEMPORAL VERIFICATION: Ensure strict window ordering
    # This is critical for preventing data leakage
    assert (
        train_start
        < train_end
        <= cal_start
        < cal_end
        <= val_start
        < val_end
        <= pred_start
        < pred_end
    ), (
        f"Temporal order violation! TRAIN[{train_start}:{train_end}] CAL[{cal_start}:{cal_end}] "
        f"VAL[{val_start}:{val_end}] PRED[{pred_start}:{pred_end}]"
    )

    actual_train_size = train_end - train_start
    actual_val_size = val_end - val_start
    actual_cal_size = cal_end - cal_start
    actual_pred_size = pred_end - pred_start
    actual_fs_size = fs_end - fs_start  # Feature selection window size
    actual_cb_size = cb_end - cb_start  # Class balance window size

    # ─────────────────────────────────────────────────────────────────
    # STEP 2: EXTRACT DATA SLICES
    # ─────────────────────────────────────────────────────────────────
    train_slice = source_df.iloc[train_start:train_end]
    val_slice = source_df.iloc[val_start:val_end]
    cal_slice = source_df.iloc[cal_start:cal_end]  # SEPARATE from val!
    pred_slice = source_df.iloc[pred_start:pred_end]

    # ⭐ MASTER CHECKLIST: FS = TRAIN+VAL, CB = subset of TRAIN only
    fs_slice = source_df.iloc[fs_start:fs_end]  # Feature selection: TRAIN + VAL
    cb_slice = source_df.iloc[cb_start:cb_end]  # Class balance: SUBSET of TRAIN only

    # ─────────────────────────────────────────────────────────────────
    # STEP 2b: SHUFFLE VAL+CAL POOL (improve statistical representation)
    # ─────────────────────────────────────────────────────────────────
    # Combine VAL and CAL, shuffle together, split back to original sizes.
    # This gives better coverage for both early stopping and calibration.
    # SAFE: rolling features pre-computed, GB models order-invariant.
    #
    if SHUFFLE_VAL_CAL_POOL:
        # Combine VAL and CAL into one pool
        val_cal_combined = pd.concat([val_slice, cal_slice], axis=0)

        # Shuffle with iteration-based seed for reproducibility
        val_cal_shuffled = val_cal_combined.sample(frac=1.0, random_state=iteration)

        # Split back to original sizes (CAL first, then VAL)
        cal_slice = val_cal_shuffled.iloc[:actual_cal_size].copy()
        val_slice = val_cal_shuffled.iloc[
            actual_cal_size : actual_cal_size + actual_val_size
        ].copy()

        if iteration <= 3:
            print(
                f"    [Shuffle] VAL+CAL pool: {len(val_cal_combined)} rows → CAL:{len(cal_slice)}, VAL:{len(val_slice)}"
            )

    # ─────────────────────────────────────────────────────────────────
    # STEP 3: SIGNAL AGGREGATION + FEATURE COMBINATION
    # ─────────────────────────────────────────────────────────────────
    # Combine ALL features + aggregated signals, let model select best
    #
    if USE_SIGNAL_AGGREGATION:
        # Fit aggregator on TRAIN window only (never sees future data)
        iter_signal_aggregator = SignalAggregator()
        iter_signal_aggregator.fit(train_slice, "direction_target", verbose=False)

        # Transform all windows using TRAIN-fitted aggregator
        train_slice_agg = iter_signal_aggregator.add_features_to_df(train_slice.copy())
        val_slice_agg = iter_signal_aggregator.add_features_to_df(val_slice.copy())
        cal_slice_agg = iter_signal_aggregator.add_features_to_df(cal_slice.copy())
        pred_slice_agg = iter_signal_aggregator.add_features_to_df(pred_slice.copy())

        # Get aggregated feature names (first iteration only for logging)
        if iteration == 1:
            aggregated_feature_cols = [
                c for c in train_slice_agg.columns if c.startswith("agg_")
            ]
            # ⭐ COMBINE ALL: base features + computed features + aggregated signals
            all_direction_cols = direction_feature_cols + aggregated_feature_cols
            all_volatility_cols = volatility_feature_cols  # Vol doesn't need signals
        else:
            all_direction_cols = direction_feature_cols + aggregated_feature_cols

        # Direction model uses PRESELECTED direction features + aggregated
        X_train_dir = train_slice_agg[all_direction_cols].fillna(0)
        X_val_dir = val_slice_agg[all_direction_cols].fillna(0)
        X_cal_dir = cal_slice_agg[all_direction_cols].fillna(0)
        X_pred_dir = pred_slice_agg[all_direction_cols].fillna(0)

        # Volatility model uses volatility features (from source, not aggregated)
        X_train_vol = train_slice[volatility_feature_cols].fillna(0)
        X_val_vol = val_slice[volatility_feature_cols].fillna(0)
        X_cal_vol = cal_slice[volatility_feature_cols].fillna(0)
        X_pred_vol = pred_slice[volatility_feature_cols].fillna(0)
    else:
        # No signal aggregation - use preselected features directly

        # Direction model uses direction features
        X_train_dir = train_slice[direction_feature_cols].fillna(0)
        X_val_dir = val_slice[direction_feature_cols].fillna(0)
        X_cal_dir = cal_slice[direction_feature_cols].fillna(0)
        X_pred_dir = pred_slice[direction_feature_cols].fillna(0)

        # Volatility model uses volatility features
        X_train_vol = train_slice[volatility_feature_cols].fillna(0)
        X_val_vol = val_slice[volatility_feature_cols].fillna(0)
        X_cal_vol = cal_slice[volatility_feature_cols].fillna(0)
        X_pred_vol = pred_slice[volatility_feature_cols].fillna(0)

    y_train_dir = train_slice[DIRECTION_TARGET]
    y_val_dir = val_slice[DIRECTION_TARGET]
    y_cal_dir = cal_slice[DIRECTION_TARGET].values  # OOS labels for calibration

    # ⭐ PRODUCTION-SAFE: Handle missing direction_target in PRED slice
    # In live production, forward_returns/direction_target won't exist for current row
    # We still need y_pred_dir for backtest tracking, but it's None in live mode
    if DIRECTION_TARGET in pred_slice.columns:
        y_pred_dir = pred_slice[DIRECTION_TARGET].values
    else:
        y_pred_dir = None  # Not available in live production

    # ⭐ LAGGED DIRECTION TARGET: For production-compatible TP/FP tracking
    # This represents YESTERDAY's actual outcome (known at prediction time in production)
    y_pred_dir_lagged = None
    if LAGGED_DIRECTION_TARGET and LAGGED_DIRECTION_TARGET in pred_slice.columns:
        y_pred_dir_lagged = pred_slice[LAGGED_DIRECTION_TARGET].values

    y_train_vol = train_slice[VOLATILITY_TARGET]
    y_val_vol = val_slice[VOLATILITY_TARGET]
    y_cal_vol = cal_slice[VOLATILITY_TARGET].values  # OOS labels for vol calibration
    y_pred_vol = pred_slice[VOLATILITY_TARGET].values

    # ⭐ RETURNS TARGET: Actual forward returns (continuous, for final regression)
    RETURNS_TARGET = "forward_returns"
    LAGGED_RETURNS_FEATURE = "lagged_forward_returns"

    y_train_ret = (
        train_slice[RETURNS_TARGET].values
        if RETURNS_TARGET in train_slice.columns
        else None
    )
    y_val_ret = (
        val_slice[RETURNS_TARGET].values
        if RETURNS_TARGET in val_slice.columns
        else None
    )
    y_cal_ret = (
        cal_slice[RETURNS_TARGET].values
        if RETURNS_TARGET in cal_slice.columns
        else None
    )
    y_pred_ret = (
        pred_slice[RETURNS_TARGET].values
        if RETURNS_TARGET in pred_slice.columns
        else None
    )

    # Lagged returns as feature (safe - no leakage)
    lagged_ret_train = (
        train_slice[LAGGED_RETURNS_FEATURE].values
        if LAGGED_RETURNS_FEATURE in train_slice.columns
        else np.zeros(len(train_slice))
    )
    lagged_ret_val = (
        val_slice[LAGGED_RETURNS_FEATURE].values
        if LAGGED_RETURNS_FEATURE in val_slice.columns
        else np.zeros(len(val_slice))
    )
    lagged_ret_cal = (
        cal_slice[LAGGED_RETURNS_FEATURE].values
        if LAGGED_RETURNS_FEATURE in cal_slice.columns
        else np.zeros(len(cal_slice))
    )
    lagged_ret_pred = (
        pred_slice[LAGGED_RETURNS_FEATURE].values
        if LAGGED_RETURNS_FEATURE in pred_slice.columns
        else np.zeros(len(pred_slice))
    )

    # Risk-free rate for Hull score calculation
    RISK_FREE_COL = "risk_free_rate"
    risk_free_pred = (
        pred_slice[RISK_FREE_COL].values
        if RISK_FREE_COL in pred_slice.columns
        else np.zeros(len(pred_slice))
    )

    # ⭐ PRODUCTION-SAFE FLAGS: Track what's available for evaluation
    has_pred_target = y_pred_dir is not None  # Can we evaluate direction predictions?
    has_pred_returns = y_pred_ret is not None  # Can we evaluate return predictions?

    # ─────────────────────────────────────────────────────────────────
    # STEP 4: DRIFT DETECTION & AUTOMATIC ADJUSTMENT
    # ─────────────────────────────────────────────────────────────────
    # Check for concept drift and automatically adjust model if detected
    # Adjustments:
    #   - Increase L2 regularization (prevent overfitting to stale patterns)
    #   - Reduce depth (simpler model generalizes better under drift)
    #   - Apply extra confidence shrinkage in predictions
    #
    drift_info = None
    drift_active = False  # Track if drift adjustment should be applied this iteration

    if USE_DRIFT_DETECTION and iteration % DRIFT_CHECK_INTERVAL == 0:
        drift_info = check_drift(
            X_train_dir,
            X_val_dir,
            top_k_features=5,
            psi_threshold=DRIFT_PSI_THRESHOLD,
            verbose=(iteration <= 3 * DRIFT_CHECK_INTERVAL),
        )
        if drift_info["drift_detected"]:
            drift_active = True
            drift_alerts.append(
                {
                    "iteration": iteration,
                    "avg_psi": drift_info["avg_psi"],
                    "max_psi": drift_info["max_psi"],
                    "n_drifted": drift_info["n_drifted_features"],
                }
            )
            if iteration <= 50 or iteration % 100 == 0:
                print(
                    f"    ⚠️ DRIFT DETECTED at iter {iteration}: PSI={drift_info['max_psi']:.3f}, adjusting model..."
                )

    # Carry forward drift status from last check
    if not drift_info and len(drift_alerts) > 0:
        last_drift_iter = drift_alerts[-1]["iteration"]
        if iteration - last_drift_iter < DRIFT_CHECK_INTERVAL * 2:
            drift_active = True  # Still in drift period

    # ─────────────────────────────────────────────────────────────────
    # STEP 4b: DRIFT-TRIGGERED OPTUNA RE-TUNING
    # ─────────────────────────────────────────────────────────────────
    # When drift is detected, re-run Optuna to find better hyperparameters
    # that work on the NEW data distribution
    # ⭐ Fresh study each time but warm-started with previous best params
    #
    if (
        OPTUNA_RETUNE_ON_DRIFT
        and drift_info is not None
        and drift_info["drift_detected"]
    ):
        # ⭐ Use ADAPTIVE gap_size: current_WF_CAL (per-iteration) + WF_VAL
        # This ensures search space constraints match the ACTUAL temporal gap
        iter_gap_size = current_WF_CAL + WF_VAL
        print(
            f"\n    🔄 DRIFT RETUNE: Running Optuna ({OPTUNA_RETUNE_TIMEOUT}s) with warm-start..."
        )
        print(
            f"       Adaptive gap_size={iter_gap_size} (CAL={current_WF_CAL}, VAL={WF_VAL})"
        )

        retune_results = run_optuna_tuning(
            X_train_dir,
            y_train_dir,
            X_val_dir,
            y_val_dir,
            timeout_sec=OPTUNA_RETUNE_TIMEOUT,
            gpu_params=CATBOOST_GPU_PARAMS,
            gap_size=iter_gap_size,  # ⭐ FIXED: Use adaptive window size
            verbose=True,
        )

        # Update both model params with new tuned values
        if retune_results["best_cb_params"]:
            CATBOOST_DIR_PARAMS.update(
                {
                    "max_leaves": retune_results["best_cb_params"].get(
                        "num_leaves", 31
                    ),
                    "depth": retune_results["best_cb_params"].get("max_depth", 8),
                    "learning_rate": retune_results["best_cb_params"].get(
                        "learning_rate", 0.01
                    ),
                    "iterations": retune_results["best_cb_params"].get(
                        "n_estimators", 1000
                    ),
                    "l2_leaf_reg": retune_results["best_cb_params"].get(
                        "reg_lambda", 10.0
                    ),
                }
            )
        if retune_results["best_lgb_params"]:
            LIGHTGBM_DIR_PARAMS.update(
                {
                    "num_leaves": retune_results["best_lgb_params"].get(
                        "num_leaves", 31
                    ),
                    "max_depth": retune_results["best_lgb_params"].get("max_depth", 8),
                    "learning_rate": retune_results["best_lgb_params"].get(
                        "learning_rate", 0.01
                    ),
                    "n_estimators": retune_results["best_lgb_params"].get(
                        "n_estimators", 1000
                    ),
                    "reg_lambda": retune_results["best_lgb_params"].get(
                        "reg_lambda", 10.0
                    ),
                }
            )

        print(
            f"    ✅ Optuna retune complete - CB score: {retune_results['best_cb_score']:.4f}, LGB score: {retune_results['best_lgb_score']:.4f}"
        )
        # Reprint header for easier reading after Optuna output
        print("-" * 215)
        print(
            f"{'Iter':<7} {'TRAIN':^12} {'CAL':^12} {'VAL':^12} {'PRED':^12} {'CB':>5} {'LG':>5} {'Config':<20} {'Prob':>5} {'Thr':>5} {'P':>2} {'A':>2} {'Res':>3} {'TP':>4} {'FP':>4} {'Ratio':>6} {'Mkt':>6} {'Sig':>5} {'HullB':>6} {'HullF':>6} {'LtEMA':>6} {'StEMA':>6} {'LtRSI':>5} {'StRSI':>5} {'Time':>5} {'Mkt%':>7} {'Ret%':>7}"
        )
        print("-" * 215)

    # ─────────────────────────────────────────────────────────────────
    # STEP 5: CLASS BALANCE WEIGHT (from CB window ⊆ TRAIN only)
    # ─────────────────────────────────────────────────────────────────
    # Per MASTER CHECKLIST: Class balance window must be SUBSET of TRAIN
    # Never use VAL/CAL data for class weight estimation
    y_cb_dir = cb_slice[DIRECTION_TARGET]
    scale_pos_weight = calculate_scale_pos_weight(y_cb_dir, verbose=(iteration <= 3))

    # ─────────────────────────────────────────────────────────────────
    # STEP 5b: HALF-LIFE SAMPLE WEIGHTS (temporal decay)
    # ─────────────────────────────────────────────────────────────────
    # Give more weight to recent training samples
    # Works ALONGSIDE class balancing - CatBoost multiplies both
    train_sample_weights = calculate_half_life_weights(
        n_samples=len(X_train_dir),
        half_life=current_half_life,
        min_weight=MIN_SAMPLE_WEIGHT,
        verbose=(iteration <= 3),
    )

    # ─────────────────────────────────────────────────────────────────
    # STEP 6: TRAIN BOTH DIRECTION MODELS (ENSEMBLE: CatBoost + LightGBM)
    # ⭐ Train BOTH models, calibrate each, combine with RF meta-stacker
    # ─────────────────────────────────────────────────────────────────

    # ─────────────────────────────────────────────────────────────────
    # FEATURE SELECTION: Use CatBoost for feature importance
    # ─────────────────────────────────────────────────────────────────

    cb_params = CATBOOST_DIR_PARAMS.copy()
    if USE_CLASS_BALANCING:
        cb_params["scale_pos_weight"] = scale_pos_weight

    # Apply drift adjustment
    if USE_DRIFT_ADJUSTMENT and drift_active:
        cb_params["l2_leaf_reg"] = (
            cb_params.get("l2_leaf_reg", 10) * DRIFT_L2_MULTIPLIER
        )
        cb_params["depth"] = max(2, cb_params.get("depth", 8) - DRIFT_DEPTH_REDUCTION)
        cb_params["iterations"] = max(
            200, int(cb_params.get("iterations", 1000) * 0.75)
        )

    if FEATURE_SELECTION_PERCENT is not None and FEATURE_SELECTION_PERCENT < 100:
        # ════════════════════════════════════════════════════════════════════
        # PHASE 1: Select top N% features from original set
        # ════════════════════════════════════════════════════════════════════
        fs_params = cb_params.copy()
        fs_params["iterations"] = min(300, cb_params.get("iterations", 1000))
        fs_params["early_stopping_rounds"] = 50
        # Remove non-CatBoost keys
        for bad_key in [
            "model_type",
            "max_depth",
            "reg_lambda",
            "n_estimators",
            "min_child_samples",
            "num_leaves",
            "subsample_freq",
            "boosting_type",
            "objective",
            "metric",
            "n_jobs",
        ]:
            fs_params.pop(bad_key, None)

        fs_model = CatBoostClassifier(**fs_params)
        fs_model.fit(
            X_train_dir,
            y_train_dir,
            sample_weight=train_sample_weights,
            eval_set=(X_val_dir, y_val_dir),
            log_cout=NULL_STREAM,
            log_cerr=NULL_STREAM,
        )

        all_dir_features = list(X_train_dir.columns)
        selected_dir_features = select_top_features(
            fs_model,
            all_dir_features,
            FEATURE_SELECTION_PERCENT,
            len(X_train_dir),
            verbose=(iteration <= 3),
        )

        if iteration <= 3:
            print(
                f"    [FeatureSel] Phase 1: {len(all_dir_features)} → {len(selected_dir_features)} features (top {FEATURE_SELECTION_PERCENT}%)"
            )

        del fs_model
        gc.collect()

        # ════════════════════════════════════════════════════════════════════
        # PHASE 2: Create lagged features and re-select
        # ════════════════════════════════════════════════════════════════════
        if USE_TWO_PHASE_FEATURE_SELECTION:

            def compute_pacf_significant_lags(
                series, max_lags=10, alpha=0.05, max_selected=4
            ):
                """Compute PACF and return significant lag periods.

                PACF measures direct correlation between a value and its lag,
                removing the effect of intermediate lags.

                Returns list of significant lag periods (up to max_selected).
                """
                try:
                    from statsmodels.tsa.stattools import pacf

                    # Clean series
                    clean_series = series.dropna()
                    if len(clean_series) < max_lags + 10:
                        return []  # Not enough data

                    # Compute PACF
                    pacf_values = pacf(clean_series, nlags=max_lags, method="ywm")

                    # Significance threshold (approximate 95% CI)
                    n = len(clean_series)
                    conf_bound = 1.96 / np.sqrt(n)

                    # Find significant lags (skip lag 0 which is always 1.0)
                    significant_lags = []
                    for lag in range(1, len(pacf_values)):
                        if abs(pacf_values[lag]) > conf_bound:
                            significant_lags.append((lag, abs(pacf_values[lag])))

                    # Sort by absolute PACF value and take top max_selected
                    significant_lags.sort(key=lambda x: x[1], reverse=True)
                    selected = [lag for lag, _ in significant_lags[:max_selected]]
                    selected.sort()  # Return in order

                    return selected

                except Exception:
                    return []  # Fallback on any error

            def determine_optimal_lags(
                X_train, y_train, selected_features, source_df, train_start, train_end
            ):
                """Determine optimal lag periods using PACF on top features."""
                if not USE_PACF_LAG_SELECTION:
                    return FEATURE_LAG_PERIODS_FALLBACK

                # Collect significant lags from multiple top features
                lag_votes = {}  # lag -> count of features where it's significant

                # Use top 20 features (or fewer if less available)
                n_features_to_check = min(20, len(selected_features))

                for feat in selected_features[:n_features_to_check]:
                    if feat in source_df.columns:
                        series = source_df[feat].iloc[train_start:train_end]
                        sig_lags = compute_pacf_significant_lags(
                            series,
                            max_lags=PACF_MAX_LAGS,
                            alpha=PACF_SIGNIFICANCE_LEVEL,
                            max_selected=PACF_MAX_SELECTED_LAGS,
                        )
                        for lag in sig_lags:
                            lag_votes[lag] = lag_votes.get(lag, 0) + 1

                if not lag_votes:
                    return FEATURE_LAG_PERIODS_FALLBACK

                # Select lags that appear in at least 20% of checked features
                min_votes = max(1, n_features_to_check * 0.2)
                selected_lags = [
                    lag for lag, votes in lag_votes.items() if votes >= min_votes
                ]

                # Sort and limit to max 4
                selected_lags.sort()
                selected_lags = selected_lags[:PACF_MAX_SELECTED_LAGS]

                if not selected_lags:
                    return FEATURE_LAG_PERIODS_FALLBACK

                return selected_lags

            def create_lagged_features_for_window(
                X_df,
                selected_features,
                source_df,
                window_start,
                window_end,
                lag_periods,
            ):
                """Create lagged features for selected features within a window."""
                X_with_lags = X_df[selected_features].copy()

                for feat in selected_features:
                    if feat in source_df.columns:
                        for lag in lag_periods:
                            lag_name = f"{feat}_lag{lag}"
                            # Get lagged values from source_df
                            # For each row in window, we need the value from 'lag' rows before
                            lag_values = []
                            for idx in range(window_start, window_end):
                                lag_idx = idx - lag
                                if lag_idx >= 0 and feat in source_df.columns:
                                    lag_values.append(source_df[feat].iloc[lag_idx])
                                else:
                                    lag_values.append(np.nan)
                            X_with_lags[lag_name] = lag_values

                # Fill NaN with 0 for lagged features (beginning of series)
                X_with_lags = X_with_lags.fillna(0)
                return X_with_lags

            # Determine optimal lags using PACF
            optimal_lag_periods = determine_optimal_lags(
                X_train_dir,
                y_train_dir,
                selected_dir_features,
                source_df,
                train_start,
                train_end,
            )

            if iteration <= 3:
                print(f"    [PACF] Optimal lag periods: {optimal_lag_periods}")

            if len(optimal_lag_periods) > 0:
                # Create lagged features for each window
                X_train_dir_with_lags = create_lagged_features_for_window(
                    X_train_dir,
                    selected_dir_features,
                    source_df,
                    train_start,
                    train_end,
                    optimal_lag_periods,
                )
                X_val_dir_with_lags = create_lagged_features_for_window(
                    X_val_dir,
                    selected_dir_features,
                    source_df,
                    val_start,
                    val_end,
                    optimal_lag_periods,
                )
                X_cal_dir_with_lags = create_lagged_features_for_window(
                    X_cal_dir,
                    selected_dir_features,
                    source_df,
                    cal_start,
                    cal_end,
                    optimal_lag_periods,
                )
                X_pred_dir_with_lags = create_lagged_features_for_window(
                    X_pred_dir,
                    selected_dir_features,
                    source_df,
                    pred_start,
                    pred_end,
                    optimal_lag_periods,
                )

                # Separate lagged features from base features
                lagged_feature_cols = [
                    c for c in X_train_dir_with_lags.columns if "_lag" in c
                ]
                base_feature_cols = [
                    c for c in X_train_dir_with_lags.columns if "_lag" not in c
                ]
                n_lagged = len(lagged_feature_cols)

                if iteration <= 3:
                    print(
                        f"    [FeatureSel] Phase 2: Added lags {optimal_lag_periods} → {len(base_feature_cols)} base + {n_lagged} lagged features"
                    )

                # ════════════════════════════════════════════════════════════════════
                # PHASE 2 STRATEGY: Keep all base features, only select lagged features
                # This prevents losing already-validated base features from Phase 1
                # ════════════════════════════════════════════════════════════════════
                if n_lagged > 0:
                    # Train model on ONLY lagged features to select best ones
                    X_train_lagged_only = X_train_dir_with_lags[lagged_feature_cols]
                    X_val_lagged_only = X_val_dir_with_lags[lagged_feature_cols]

                    fs_model2 = CatBoostClassifier(**fs_params)
                    fs_model2.fit(
                        X_train_lagged_only,
                        y_train_dir,
                        sample_weight=train_sample_weights,
                        eval_set=(X_val_lagged_only, y_val_dir),
                        log_cout=NULL_STREAM,
                        log_cerr=NULL_STREAM,
                    )

                    # Select top lagged features only
                    selected_lagged_features = select_top_features(
                        fs_model2,
                        lagged_feature_cols,
                        FEATURE_SELECTION_PHASE2_PERCENT,
                        len(X_train_lagged_only),
                        verbose=False,
                    )

                    # Final features = ALL base features (from Phase 1) + selected lagged features
                    final_selected_features = (
                        base_feature_cols + selected_lagged_features
                    )

                    if iteration <= 3:
                        print(
                            f"    [FeatureSel] Phase 2: {n_lagged} lagged → {len(selected_lagged_features)} selected (top {FEATURE_SELECTION_PHASE2_PERCENT}%)"
                        )
                        print(
                            f"    [FeatureSel] Final: {len(base_feature_cols)} base (kept) + {len(selected_lagged_features)} lagged = {len(final_selected_features)} total"
                        )

                    del fs_model2
                    gc.collect()
                else:
                    # No lagged features created (shouldn't happen if optimal_lag_periods > 0)
                    final_selected_features = base_feature_cols

                # Use final selected features
                X_train_dir = X_train_dir_with_lags[final_selected_features]
                X_val_dir = X_val_dir_with_lags[final_selected_features]
                X_cal_dir = X_cal_dir_with_lags[final_selected_features]
                X_pred_dir = X_pred_dir_with_lags[final_selected_features]

                gc.collect()
            else:
                # No significant lags found - just use phase 1 selected features
                if iteration <= 3:
                    print(
                        "    [PACF] No significant lags found, using Phase 1 features only"
                    )
                X_train_dir = X_train_dir[selected_dir_features]
                X_val_dir = X_val_dir[selected_dir_features]
                X_cal_dir = X_cal_dir[selected_dir_features]
                X_pred_dir = X_pred_dir[selected_dir_features]
        else:
            # Two-phase disabled - just use phase 1 selected features
            X_train_dir = X_train_dir[selected_dir_features]
            X_val_dir = X_val_dir[selected_dir_features]
            X_cal_dir = X_cal_dir[selected_dir_features]
            X_pred_dir = X_pred_dir[selected_dir_features]

        gc.collect()

    # ════════════════════════════════════════════════════════════════════════
    # TRAIN CATBOOST MODEL
    # ════════════════════════════════════════════════════════════════════════
    cb_train_params = cb_params.copy()
    for bad_key in [
        "model_type",
        "max_depth",
        "reg_lambda",
        "n_estimators",
        "min_child_samples",
        "num_leaves",
        "subsample_freq",
        "boosting_type",
        "objective",
        "metric",
        "n_jobs",
    ]:
        cb_train_params.pop(bad_key, None)

    cb_model = CatBoostClassifier(**cb_train_params)
    cb_model.fit(
        X_train_dir,
        y_train_dir,
        sample_weight=train_sample_weights,
        eval_set=(X_val_dir, y_val_dir),
        log_cout=NULL_STREAM,
        log_cerr=NULL_STREAM,
    )
    cb_best_iter = cb_model.get_best_iteration() or cb_model.tree_count_

    # CatBoost predictions on all windows
    cb_train_probs = cb_model.predict_proba(X_train_dir)[:, 1]
    cb_val_probs = cb_model.predict_proba(X_val_dir)[:, 1]
    cb_cal_probs = cb_model.predict_proba(X_cal_dir)[:, 1]
    cb_pred_probs = cb_model.predict_proba(X_pred_dir)[:, 1]

    del cb_model
    gc.collect()

    # ════════════════════════════════════════════════════════════════════════
    # TRAIN LIGHTGBM MODEL (skipped if USE_SINGLE_MODEL=True)
    # ════════════════════════════════════════════════════════════════════════
    if not USE_SINGLE_MODEL:
        lgb_params = LIGHTGBM_DIR_PARAMS.copy()
        lgb_params["scale_pos_weight"] = (
            scale_pos_weight if USE_CLASS_BALANCING else 1.0
        )

        # Drift adjustment for LightGBM
        if USE_DRIFT_ADJUSTMENT and drift_active:
            lgb_params["reg_lambda"] = (
                lgb_params.get("reg_lambda", 10) * DRIFT_L2_MULTIPLIER
            )
            lgb_params["max_depth"] = max(
                3, lgb_params.get("max_depth", 8) - DRIFT_DEPTH_REDUCTION
            )
            lgb_params["n_estimators"] = max(
                200, int(lgb_params.get("n_estimators", 1000) * 0.75)
            )

        import lightgbm as lgb

        lgb_model = LGBMClassifier(**lgb_params)
        lgb_model.fit(
            X_train_dir,
            y_train_dir,
            sample_weight=train_sample_weights,
            eval_set=[(X_val_dir, y_val_dir)],
            callbacks=[lgb.early_stopping(stopping_rounds=300, verbose=False)],
        )
        lgb_best_iter = (
            lgb_model.best_iteration_
            if hasattr(lgb_model, "best_iteration_")
            else lgb_params["n_estimators"]
        )

        # LightGBM predictions on all windows
        lgb_train_probs = lgb_model.predict_proba(X_train_dir)[:, 1]
        lgb_val_probs = lgb_model.predict_proba(X_val_dir)[:, 1]
        lgb_cal_probs = lgb_model.predict_proba(X_cal_dir)[:, 1]
        lgb_pred_probs = lgb_model.predict_proba(X_pred_dir)[:, 1]

        del lgb_model
        gc.collect()
    else:
        # Single model mode: use CB probs as placeholder for LGB
        lgb_train_probs = cb_train_probs.copy()
        lgb_val_probs = cb_val_probs.copy()
        lgb_cal_probs = cb_cal_probs.copy()
        lgb_pred_probs = cb_pred_probs.copy()
        lgb_best_iter = cb_best_iter

    # ════════════════════════════════════════════════════════════════════════════
    # TRAIN HISTGRADIENTBOOSTING MODEL (only in 'full' ensemble mode)
    # ════════════════════════════════════════════════════════════════════════════
    if USE_HGB and not USE_SINGLE_MODEL:
        from sklearn.ensemble import HistGradientBoostingClassifier as HGB_Base

        # Get HGB params from optuna results or use defaults
        hgb_max_iter = HISTGB_DIR_PARAMS.get("max_iter", 200)
        hgb_max_depth = HISTGB_DIR_PARAMS.get("max_depth", 10)
        hgb_min_samples_leaf = HISTGB_DIR_PARAMS.get("min_samples_leaf", 40)
        hgb_max_leaf_nodes = HISTGB_DIR_PARAMS.get("max_leaf_nodes", 31)
        hgb_learning_rate = HISTGB_DIR_PARAMS.get("learning_rate", 0.02)
        hgb_l2_regularization = HISTGB_DIR_PARAMS.get("l2_regularization", 0.1)

        # Apply drift adjustment (same as CB/LGB)
        if USE_DRIFT_ADJUSTMENT and drift_active:
            hgb_l2_regularization = hgb_l2_regularization * DRIFT_L2_MULTIPLIER
            hgb_max_depth = max(3, hgb_max_depth - DRIFT_DEPTH_REDUCTION)
            hgb_max_iter = max(200, int(hgb_max_iter * 0.75))

        hgb_class_weight = (
            "balanced" if USE_CLASS_BALANCING and scale_pos_weight > 1.5 else None
        )

        # HGB trains on EXACT same X_train_dir as CB/LGB, early stops on X_val_dir
        hgb_model = HGB_Base(
            max_iter=hgb_max_iter,
            max_depth=hgb_max_depth,
            max_leaf_nodes=hgb_max_leaf_nodes,
            min_samples_leaf=hgb_min_samples_leaf,
            learning_rate=hgb_learning_rate,
            l2_regularization=hgb_l2_regularization,
            class_weight=hgb_class_weight,
            early_stopping=True,
            n_iter_no_change=50,
            random_state=42,
        )
        # Use X_val, y_val directly like CB/LGB eval_set
        hgb_model.fit(
            X_train_dir,
            y_train_dir,
            sample_weight=train_sample_weights,
            X_val=X_val_dir,
            y_val=y_val_dir,
        )

        # HistGradientBoosting predictions on all windows
        hgb_train_probs = hgb_model.predict_proba(X_train_dir)[:, 1]
        hgb_val_probs = hgb_model.predict_proba(X_val_dir)[:, 1]
        hgb_cal_probs = hgb_model.predict_proba(X_cal_dir)[:, 1]
        hgb_pred_probs = hgb_model.predict_proba(X_pred_dir)[:, 1]

        del hgb_model
        gc.collect()
    else:
        # CB+LGB mode or single model: use LGB probs as placeholder for HGB
        hgb_train_probs = lgb_train_probs.copy()
        hgb_val_probs = lgb_val_probs.copy()
        hgb_cal_probs = lgb_cal_probs.copy()
        hgb_pred_probs = lgb_pred_probs.copy()

    n_dir_features = len(X_train_dir.columns)

    # ════════════════════════════════════════════════════════════════════════
    # STEP 7: PER-MODEL CALIBRATION (ROLLING BUFFER APPROACH)
    # ════════════════════════════════════════════════════════════════════════
    # Each model gets its own calibration buffer and Platt calibrator.
    # This corrects individual model bias before ensemble combination.

    y_cal_dir_arr = (
        y_cal_dir.values if hasattr(y_cal_dir, "values") else np.array(y_cal_dir)
    )

    # ⚠️ LEAKAGE FIX: Fit calibrator on PAST CAL windows only (buffer before append)
    # Then append current CAL to buffer AFTER calibration (for next iteration)

    # Fit per-model Platt calibrators (on buffer WITHOUT current CAL)
    cb_cal_method = "none"
    lgb_cal_method = "none"
    hgb_cal_method = "none"

    # CatBoost calibrator - fit on PAST data only
    cb_scores, cb_labels = cb_cal_buffer.get_buffer()
    if USE_PROBABILITY_CALIBRATION and cb_cal_buffer.size() >= MIN_CALIBRATION_SAMPLES:
        n_pos = cb_labels.sum()
        n_neg = len(cb_labels) - n_pos
        if n_pos >= MIN_CALIBRATION_POSITIVES and n_neg >= MIN_CALIBRATION_POSITIVES:
            try:
                # Adaptive C: use C=0.1 for small buffers (more regularization), C=1.0 for larger
                platt_C = 0.1 if cb_cal_buffer.size() < 1000 else 1.0
                cb_calibrator = LogisticRegression(
                    solver="lbfgs", max_iter=1000, C=platt_C
                )
                cb_calibrator.fit(cb_scores.reshape(-1, 1), cb_labels)
                cb_cal_method = "platt"
            except Exception:
                cb_calibrator = None

    # LightGBM calibrator (only if multi-model ensemble)
    if not USE_SINGLE_MODEL:
        lgb_scores, lgb_labels = lgb_cal_buffer.get_buffer()
        if (
            USE_PROBABILITY_CALIBRATION
            and lgb_cal_buffer.size() >= MIN_CALIBRATION_SAMPLES
        ):
            n_pos = lgb_labels.sum()
            n_neg = len(lgb_labels) - n_pos
            if (
                n_pos >= MIN_CALIBRATION_POSITIVES
                and n_neg >= MIN_CALIBRATION_POSITIVES
            ):
                try:
                    # Adaptive C: use C=0.1 for small buffers (more regularization), C=1.0 for larger
                    platt_C = 0.1 if lgb_cal_buffer.size() < 1000 else 1.0
                    lgb_calibrator = LogisticRegression(
                        solver="lbfgs", max_iter=1000, C=platt_C
                    )
                    lgb_calibrator.fit(lgb_scores.reshape(-1, 1), lgb_labels)
                    lgb_cal_method = "platt"
                except Exception:
                    lgb_calibrator = None

    # HistGradientBoosting calibrator (only if multi-model ensemble AND USE_HGB)
    if not USE_SINGLE_MODEL and USE_HGB:
        hgb_scores, hgb_labels = hgb_cal_buffer.get_buffer()
        if (
            USE_PROBABILITY_CALIBRATION
            and hgb_cal_buffer.size() >= MIN_CALIBRATION_SAMPLES
        ):
            n_pos = hgb_labels.sum()
            n_neg = len(hgb_labels) - n_pos
            if (
                n_pos >= MIN_CALIBRATION_POSITIVES
                and n_neg >= MIN_CALIBRATION_POSITIVES
            ):
                try:
                    # Adaptive C: use C=0.1 for small buffers (more regularization), C=1.0 for larger
                    platt_C = 0.1 if hgb_cal_buffer.size() < 1000 else 1.0
                    hgb_calibrator = LogisticRegression(
                        solver="lbfgs", max_iter=1000, C=platt_C
                    )
                    hgb_calibrator.fit(hgb_scores.reshape(-1, 1), hgb_labels)
                    hgb_cal_method = "platt"
                except Exception:
                    hgb_calibrator = None

    # Apply per-model calibration to VAL and PRED
    if cb_calibrator is not None:
        cb_val_probs_cal = cb_calibrator.predict_proba(cb_val_probs.reshape(-1, 1))[
            :, 1
        ]
        cb_pred_probs_cal = cb_calibrator.predict_proba(cb_pred_probs.reshape(-1, 1))[
            :, 1
        ]
        cb_cal_probs_cal = cb_calibrator.predict_proba(cb_cal_probs.reshape(-1, 1))[
            :, 1
        ]
    else:
        cb_val_probs_cal = cb_val_probs.copy()
        cb_pred_probs_cal = cb_pred_probs.copy()
        cb_cal_probs_cal = cb_cal_probs.copy()

    if lgb_calibrator is not None:
        lgb_val_probs_cal = lgb_calibrator.predict_proba(lgb_val_probs.reshape(-1, 1))[
            :, 1
        ]
        lgb_pred_probs_cal = lgb_calibrator.predict_proba(
            lgb_pred_probs.reshape(-1, 1)
        )[:, 1]
        lgb_cal_probs_cal = lgb_calibrator.predict_proba(lgb_cal_probs.reshape(-1, 1))[
            :, 1
        ]
    else:
        lgb_val_probs_cal = lgb_val_probs.copy()
        lgb_pred_probs_cal = lgb_pred_probs.copy()
        lgb_cal_probs_cal = lgb_cal_probs.copy()

    # For CB+LGB mode, just copy LGB as placeholder for any HGB references
    hgb_val_probs_cal = lgb_val_probs_cal.copy()
    hgb_pred_probs_cal = lgb_pred_probs_cal.copy()
    hgb_cal_probs_cal = lgb_cal_probs_cal.copy()

    if iteration <= 3:
        print(
            f"    [CalBuffer] CB: {cb_cal_buffer.size()} ({cb_cal_method}), LGB: {lgb_cal_buffer.size()} ({lgb_cal_method})"
        )

    # ════════════════════════════════════════════════════════════════════════
    # STEP 7a2: CALIBRATION DIAGNOSTICS (Brier, ECE)
    # ════════════════════════════════════════════════════════════════════════
    # Track calibration quality improvement per iteration
    if cb_cal_buffer.size() >= MIN_CALIBRATION_SAMPLES:
        cb_cal_stats = compute_calibration_stats(
            cb_cal_probs, cb_cal_probs_cal, y_cal_dir_arr, name="CatBoost"
        )
        lgb_cal_stats = compute_calibration_stats(
            lgb_cal_probs, lgb_cal_probs_cal, y_cal_dir_arr, name="LightGBM"
        )
        if USE_HGB:
            hgb_cal_stats = compute_calibration_stats(
                hgb_cal_probs,
                hgb_cal_probs_cal,
                y_cal_dir_arr,
                name="HistGradientBoosting",
            )
        else:
            # Placeholder for CB+LGB mode
            hgb_cal_stats = {
                "brier_before": 0.0,
                "brier_after": 0.0,
                "ece_before": 0.0,
                "ece_after": 0.0,
            }

        calibration_diagnostics.append(
            {
                "iteration": iteration,
                "cb_brier_before": cb_cal_stats["brier_before"],
                "cb_brier_after": cb_cal_stats["brier_after"],
                "cb_ece_before": cb_cal_stats["ece_before"],
                "cb_ece_after": cb_cal_stats["ece_after"],
                "lgb_brier_before": lgb_cal_stats["brier_before"],
                "lgb_brier_after": lgb_cal_stats["brier_after"],
                "lgb_ece_before": lgb_cal_stats["ece_before"],
                "lgb_ece_after": lgb_cal_stats["ece_after"],
                "hgb_brier_before": hgb_cal_stats["brier_before"],
                "hgb_brier_after": hgb_cal_stats["brier_after"],
                "hgb_ece_before": hgb_cal_stats["ece_before"],
                "hgb_ece_after": hgb_cal_stats["ece_after"],
                "cal_samples": cb_cal_buffer.size(),
            }
        )

        if iteration <= 3:
            print(
                f"    [CalDiag] CB: Brier {cb_cal_stats['brier_before']:.4f}→{cb_cal_stats['brier_after']:.4f}, ECE {cb_cal_stats['ece_before']:.4f}→{cb_cal_stats['ece_after']:.4f}"
            )
            if not USE_SINGLE_MODEL:
                print(
                    f"    [CalDiag] LGB: Brier {lgb_cal_stats['brier_before']:.4f}→{lgb_cal_stats['brier_after']:.4f}, ECE {lgb_cal_stats['ece_before']:.4f}→{lgb_cal_stats['ece_after']:.4f}"
                )
                if USE_HGB:
                    print(
                        f"    [CalDiag] HGB: Brier {hgb_cal_stats['brier_before']:.4f}→{hgb_cal_stats['brier_after']:.4f}, ECE {hgb_cal_stats['ece_before']:.4f}→{hgb_cal_stats['ece_after']:.4f}"
                    )

    # ⚠️ LEAKAGE FIX: Now append current CAL to buffer (for NEXT iteration's calibration)
    # This ensures calibrator is always fitted on strictly PAST data
    cb_cal_buffer.append(cb_cal_probs.copy(), y_cal_dir_arr.copy())
    if not USE_SINGLE_MODEL:
        lgb_cal_buffer.append(lgb_cal_probs.copy(), y_cal_dir_arr.copy())
        if USE_HGB:
            hgb_cal_buffer.append(hgb_cal_probs.copy(), y_cal_dir_arr.copy())

    # ════════════════════════════════════════════════════════════════════════
    # STEP 7b: TRAIN META-STACKER OR USE SINGLE/DUAL MODEL OUTPUT
    # ════════════════════════════════════════════════════════════════════════
    # ENSEMBLE_MODE:
    #   'single_cb': Use CatBoost calibrated probs directly
    #   'cb_lgb':    Combine CB+LGB (average or meta-stacker with 2 features)
    #   'full':      Combine CB+LGB+HGB (meta-stacker with 3 features)

    if USE_SINGLE_MODEL:
        # ⭐ SINGLE MODEL MODE: Use CatBoost calibrated probs directly
        pred_dir_probs = cb_pred_probs_cal.copy()
        cal_dir_probs_calibrated = cb_cal_probs_cal.copy()
        val_dir_probs_calibrated = cb_val_probs_cal.copy()  # For AUC-confidence
        meta_type = "single_cb"

        if iteration <= 3:
            print("    [SingleModel] Using CatBoost only (no meta-stacker)")
    elif ENSEMBLE_MODE == "cb_lgb":
        # ⭐ CB+LGB MODE: Combine CatBoost and LightGBM (no HGB)
        # Get current VAL calibrated probs and labels
        y_meta_val_current = (
            y_val_dir.values if hasattr(y_val_dir, "values") else np.array(y_val_dir)
        )

        # For CB+LGB mode, use a simpler 2-feature meta buffer
        # We'll use simple averaging for CB+LGB (reliable and fast)
        meta_type = "cb_lgb_avg"

        # Simple weighted average: CB and LGB each contribute 50%
        pred_dir_probs = (cb_pred_probs_cal + lgb_pred_probs_cal) / 2.0
        cal_dir_probs_calibrated = (cb_cal_probs_cal + lgb_cal_probs_cal) / 2.0
        val_dir_probs_calibrated = (
            cb_val_probs_cal + lgb_val_probs_cal
        ) / 2.0  # For AUC-confidence

        if iteration <= 3:
            print("    [CB+LGB] Averaging CatBoost + LightGBM predictions")
    else:
        # ⭐ CB+LGB ENSEMBLE MODE: Train LR meta-stacker on rolling VAL buffer
        # Combine calibrated base model probs (CB + LGB) using LogisticRegression meta-learner.
        # Uses ROLLING BUFFER of past VAL windows for more robust training.
        #
        # Per guide: "If VAL too small, use aggregated past VAL windows (rolling meta buffer)"
        # This gives meta more training data and allows adaptation to changing conditions.

        # Get current VAL calibrated probs and labels
        y_meta_val_current = (
            y_val_dir.values if hasattr(y_val_dir, "values") else np.array(y_val_dir)
        )

        # ⭐ Append current VAL to rolling meta buffer (BEFORE training)
        # Buffer accumulates past VAL windows for meta training
        meta_buffer.append(cb_val_probs_cal, lgb_val_probs_cal, y_meta_val_current)

        # Get accumulated buffer for training
        X_meta_buffer, y_meta_buffer = meta_buffer.get_buffer()

        meta_type = "avg"  # Default: simple average for 'full' mode fallback

    if (
        ENSEMBLE_MODE == "full"
        and meta_buffer.size() >= META_STACKER_MIN_SAMPLES
        and len(np.unique(y_meta_buffer)) > 1
    ):
        try:
            # Use RandomForest for meta-stacker
            # - RF can capture non-linear interactions between calibrated probs
            # - 3 features: CB, LGB, HGB calibrated probabilities
            # - Trained on accumulated VAL buffer for robustness
            from sklearn.ensemble import RandomForestClassifier as RF_Meta

            meta_stacker = RF_Meta(
                n_estimators=META_STACKER_N_ESTIMATORS,  # 200 per config
                max_depth=META_STACKER_MAX_DEPTH,  # 6 per config
                min_samples_leaf=META_STACKER_MIN_SAMPLES_LEAF,  # 20 per config
                random_state=42,
                n_jobs=-1,
            )
            meta_stacker.fit(X_meta_buffer, y_meta_buffer)
            meta_type = "rf"

            if iteration <= 3:
                print(
                    f"    [MetaBuffer] Trained on {meta_buffer.size()} samples from {meta_buffer.n_windows()} VAL windows"
                )
        except Exception as e:
            if iteration <= 3:
                print(f"    [Meta] RF failed: {e}, using avg")
            meta_stacker = None
        else:
            if iteration <= 3:
                print(
                    f"    [MetaBuffer] Insufficient samples ({meta_buffer.size()}), using avg"
                )

        # Generate final ensemble predictions (3 features: CB, LGB, HGB)
        X_meta_pred = np.column_stack(
            [cb_pred_probs_cal, lgb_pred_probs_cal, hgb_pred_probs_cal]
        )
        X_meta_cal = np.column_stack(
            [cb_cal_probs_cal, lgb_cal_probs_cal, hgb_cal_probs_cal]
        )
        X_meta_val = np.column_stack(
            [cb_val_probs_cal, lgb_val_probs_cal, hgb_val_probs_cal]
        )

        if meta_stacker is not None and meta_type == "rf":
            pred_dir_probs = meta_stacker.predict_proba(X_meta_pred)[:, 1]
            cal_dir_probs_calibrated = meta_stacker.predict_proba(X_meta_cal)[:, 1]
            val_dir_probs_calibrated = meta_stacker.predict_proba(X_meta_val)[:, 1]
        else:
            # Simple average fallback (equal weight to all 3 models)
            pred_dir_probs = (
                cb_pred_probs_cal + lgb_pred_probs_cal + hgb_pred_probs_cal
            ) / 3.0
            cal_dir_probs_calibrated = (
                cb_cal_probs_cal + lgb_cal_probs_cal + hgb_cal_probs_cal
            ) / 3.0
            val_dir_probs_calibrated = (
                cb_val_probs_cal + lgb_val_probs_cal + hgb_val_probs_cal
            ) / 3.0

    # Ensure pred_dir_probs is defined for all modes
    if "pred_dir_probs" not in dir() or pred_dir_probs is None:
        pred_dir_probs = cb_pred_probs_cal.copy()
        cal_dir_probs_calibrated = cb_cal_probs_cal.copy()
        val_dir_probs_calibrated = cb_val_probs_cal.copy()

    pred_dir_probs = np.clip(pred_dir_probs, 1e-8, 1 - 1e-8)
    cal_dir_probs_calibrated = np.clip(cal_dir_probs_calibrated, 1e-8, 1 - 1e-8)

    # Store raw probs for metrics
    pred_dir_probs_raw = pred_dir_probs.copy()  # Ensemble is already "calibrated"

    # Calculate per-model AUCs for diagnostics
    cb_val_auc = (
        roc_auc_score(y_val_dir, cb_val_probs) if len(np.unique(y_val_dir)) > 1 else 0.5
    )
    if not USE_SINGLE_MODEL:
        lgb_val_auc = (
            roc_auc_score(y_val_dir, lgb_val_probs)
            if len(np.unique(y_val_dir)) > 1
            else 0.5
        )
        if USE_HGB:
            hgb_val_auc = (
                roc_auc_score(y_val_dir, hgb_val_probs)
                if len(np.unique(y_val_dir)) > 1
                else 0.5
            )
        else:
            hgb_val_auc = lgb_val_auc  # Use LGB AUC as placeholder when HGB disabled
    else:
        lgb_val_auc = cb_val_auc  # Placeholder
        hgb_val_auc = cb_val_auc  # Placeholder
    cal_auc = (
        roc_auc_score(y_cal_dir, cal_dir_probs_calibrated)
        if len(np.unique(y_cal_dir)) > 1
        else 0.5
    )

    # ⭐ ENSEMBLE VAL AUC: Use actual ensemble predictions for AUC-confidence
    ensemble_val_auc = (
        roc_auc_score(y_val_dir, val_dir_probs_calibrated)
        if len(np.unique(y_val_dir)) > 1
        else 0.5
    )

    # ════════════════════════════════════════════════════════════════════════
    # STEP 7c: MODEL DIVERSITY TRACKING (only for multi-model ensemble)
    # ════════════════════════════════════════════════════════════════════════
    if not USE_SINGLE_MODEL:
        # Track diversity between base models - higher diversity = better ensemble
        # Low diversity suggests models are redundant

        # Correlation between raw base model predictions on VAL
        corr_cb_lgb = (
            np.corrcoef(cb_val_probs, lgb_val_probs)[0, 1]
            if len(cb_val_probs) > 2
            else 0.0
        )

        if USE_HGB:
            corr_cb_hgb = (
                np.corrcoef(cb_val_probs, hgb_val_probs)[0, 1]
                if len(cb_val_probs) > 2
                else 0.0
            )
            corr_lgb_hgb = (
                np.corrcoef(lgb_val_probs, hgb_val_probs)[0, 1]
                if len(lgb_val_probs) > 2
                else 0.0
            )
            avg_corr = (corr_cb_lgb + corr_cb_hgb + corr_lgb_hgb) / 3.0
        else:
            # CB+LGB mode: only one correlation pair
            corr_cb_hgb = 0.0
            corr_lgb_hgb = 0.0
            avg_corr = corr_cb_lgb

        # Disagreement rate: how often do models NOT agree?
        cb_val_preds = (cb_val_probs > 0.5).astype(int)
        lgb_val_preds = (lgb_val_probs > 0.5).astype(int)

        if USE_HGB:
            hgb_val_preds = (hgb_val_probs > 0.5).astype(int)
            all_agree = (cb_val_preds == lgb_val_preds) & (
                lgb_val_preds == hgb_val_preds
            )
            disagreement_rate = 1.0 - all_agree.mean()  # % where not all 3 agree
            # Prediction spread: average std across 3 models
            stacked_probs = np.column_stack(
                [cb_val_probs, lgb_val_probs, hgb_val_probs]
            )
        else:
            # CB+LGB mode: disagreement is simply when they differ
            all_agree = cb_val_preds == lgb_val_preds
            disagreement_rate = 1.0 - all_agree.mean()  # % where CB and LGB disagree
            # Prediction spread: average std across 2 models
            stacked_probs = np.column_stack([cb_val_probs, lgb_val_probs])

        pred_spread = stacked_probs.std(axis=1).mean()

        # Build metrics dict based on ensemble mode
        if USE_HGB:
            meta_default = 0.33
            model_diversity_metrics.append(
                {
                    "iteration": iteration,
                    "avg_correlation": float(avg_corr),
                    "corr_cb_lgb": float(corr_cb_lgb),
                    "corr_cb_hgb": float(corr_cb_hgb),
                    "corr_lgb_hgb": float(corr_lgb_hgb),
                    "disagreement_rate": float(disagreement_rate),
                    "pred_spread": float(pred_spread),
                    "cb_val_auc": float(cb_val_auc),
                    "lgb_val_auc": float(lgb_val_auc),
                    "hgb_val_auc": float(hgb_val_auc),
                    "meta_type": meta_type,
                    "meta_weight_cb": float(meta_stacker.feature_importances_[0])
                    if meta_stacker is not None
                    and hasattr(meta_stacker, "feature_importances_")
                    else meta_default,
                    "meta_weight_lgb": float(meta_stacker.feature_importances_[1])
                    if meta_stacker is not None
                    and hasattr(meta_stacker, "feature_importances_")
                    else meta_default,
                    "meta_weight_hgb": float(meta_stacker.feature_importances_[2])
                    if meta_stacker is not None
                    and hasattr(meta_stacker, "feature_importances_")
                    else meta_default,
                }
            )
        else:
            # CB+LGB mode: 2 models only
            meta_default = 0.50
            model_diversity_metrics.append(
                {
                    "iteration": iteration,
                    "avg_correlation": float(avg_corr),
                    "corr_cb_lgb": float(corr_cb_lgb),
                    "corr_cb_hgb": 0.0,  # N/A
                    "corr_lgb_hgb": 0.0,  # N/A
                    "disagreement_rate": float(disagreement_rate),
                    "pred_spread": float(pred_spread),
                    "cb_val_auc": float(cb_val_auc),
                    "lgb_val_auc": float(lgb_val_auc),
                    "hgb_val_auc": 0.0,  # N/A
                    "meta_type": meta_type,
                    "meta_weight_cb": float(meta_stacker.feature_importances_[0])
                    if meta_stacker is not None
                    and hasattr(meta_stacker, "feature_importances_")
                    else meta_default,
                    "meta_weight_lgb": float(meta_stacker.feature_importances_[1])
                    if meta_stacker is not None
                    and hasattr(meta_stacker, "feature_importances_")
                    else meta_default,
                    "meta_weight_hgb": 0.0,  # N/A
                }
            )

        # Print diagnostics: first 3 iterations, then every 50th, or after drift retune
        show_diagnostics = (iteration <= 3) or (iteration % 50 == 0)

        if show_diagnostics:
            print(
                f"    [Diversity] AvgCorr={avg_corr:.3f}, Disagree={disagreement_rate:.1%}, Spread={pred_spread:.4f}"
            )
            if USE_HGB:
                print(
                    f"    [Ensemble] CB={cb_val_auc:.3f}, LGB={lgb_val_auc:.3f}, HGB={hgb_val_auc:.3f}, Meta={meta_type}"
                )
                if meta_stacker is not None and hasattr(
                    meta_stacker, "feature_importances_"
                ):
                    imp = meta_stacker.feature_importances_
                    print(
                        f"    [MetaWeights] CB={imp[0]:.1%}, LGB={imp[1]:.1%}, HGB={imp[2]:.1%} (RF importances)"
                    )
                print(
                    f"    [EnsDebug] CB={cb_pred_probs_cal[0]:.3f}, LGB={lgb_pred_probs_cal[0]:.3f}, HGB={hgb_pred_probs_cal[0]:.3f} → Ens={pred_dir_probs[0]:.3f}"
                )
            else:
                # CB+LGB mode
                print(
                    f"    [Ensemble] CB={cb_val_auc:.3f}, LGB={lgb_val_auc:.3f}, Meta={meta_type}"
                )
                if meta_stacker is not None and hasattr(
                    meta_stacker, "feature_importances_"
                ):
                    imp = meta_stacker.feature_importances_
                    print(
                        f"    [MetaWeights] CB={imp[0]:.1%}, LGB={imp[1]:.1%} (RF importances)"
                    )
                print(
                    f"    [EnsDebug] CB={cb_pred_probs_cal[0]:.3f}, LGB={lgb_pred_probs_cal[0]:.3f} → Ens={pred_dir_probs[0]:.3f}"
                )
    else:
        # Single model mode: simple metrics
        if iteration <= 3:
            print(f"    [SingleModel] CB AUC={cb_val_auc:.3f}, CAL AUC={cal_auc:.3f}")

    # ════════════════════════════════════════════════════════════════════════
    # ⭐ STEP 7d: DISAGREEMENT GUARD - Force prediction to 0 when models disagree
    # ════════════════════════════════════════════════════════════════════════
    # If CB and LGB strongly disagree on the PREDICTION sample, this suggests
    # uncertainty/anomaly → safer to abstain (predict 0 = no trade)
    #
    # Rationale: When models are trained on same data but predict opposite,
    # this indicates the sample is near the decision boundary or an outlier.
    # In such cases, it's better to be conservative.

    USE_DISAGREEMENT_GUARD = True
    DISAGREEMENT_THRESHOLD = 0.25  # If |CB - LGB| > this, models strongly disagree

    pred_disagreement = 0.0
    disagreement_guard_triggered = False

    if USE_DISAGREEMENT_GUARD and not USE_SINGLE_MODEL:
        # Calculate disagreement on PRED sample (not VAL)
        # Disagreement = absolute difference between CB and LGB probabilities
        pred_disagreement = np.abs(cb_pred_probs_cal - lgb_pred_probs_cal).mean()

        # Also calculate historical disagreement from VAL for comparison
        val_disagreement = np.abs(cb_val_probs_cal - lgb_val_probs_cal).mean()
        val_disagreement_std = np.abs(cb_val_probs_cal - lgb_val_probs_cal).std()

        # Trigger guard if:
        # 1. Absolute disagreement exceeds threshold, OR
        # 2. Disagreement is > 2 std above VAL average (anomaly)
        disagreement_z_score = (pred_disagreement - val_disagreement) / max(
            val_disagreement_std, 0.01
        )

        if pred_disagreement > DISAGREEMENT_THRESHOLD or disagreement_z_score > 2.0:
            disagreement_guard_triggered = True

        if iteration <= 3:
            print(
                f"    [DisagreementGuard] PRED={pred_disagreement:.3f}, VAL_avg={val_disagreement:.3f}±{val_disagreement_std:.3f}, z={disagreement_z_score:.2f} → {'⚠️ GUARD' if disagreement_guard_triggered else 'OK'}"
            )

    # ─────────────────────────────────────────────────────────────────
    # STEP 7e: THRESHOLD GATES (RARE BUT IMPACTFUL)
    # ─────────────────────────────────────────────────────────────────
    # Gates only activate on EXTREME signals - not continuous scaling!
    # This prevents noise from constant small adjustments.
    #
    # PHILOSOPHY: Most predictions use base threshold. Gates trigger rarely
    # but when they do, they make a meaningful difference.
    #
    USE_RISK_GATE = True  # Block risky entries when risk is extreme
    USE_BULLISH_GATE = True  # Ease entries when conditions are very favorable

    # Get risk and bullish scores for prediction window
    pred_risk_score = source_df.iloc[pred_start:pred_end]["risk_guard_score"].values
    pred_bullish_score = (
        source_df.iloc[pred_start:pred_end]["bullish_boost_score"].values
        if "bullish_boost_score" in source_df.columns
        else np.zeros(1)
    )

    # ─────────────────────────────────────────────────────────────────
    # STEP 8: THRESHOLD CALCULATION (uses calibrated CAL probs)
    # ─────────────────────────────────────────────────────────────────
    # Use CAL set (not VAL) for threshold since CAL has calibrated probs
    # and is the most recent out-of-sample data before prediction
    # ⭐ When USE_REGIME_POS_RATE_THRESHOLD enabled, use iter_regime_pos_rate
    #    instead of CAL set's actual positive rate for threshold methods
    if THRESHOLD_METHOD == "adaptive":
        base_threshold = calculate_optimal_threshold(walkforward_predictions)
    else:
        # Use calibrated CAL probs and CAL labels for threshold
        # This ensures threshold is based on truly out-of-sample calibrated probabilities
        # ⭐ Pass regime_pos_rate when enabled to align threshold with PRED regime
        regime_rate_for_threshold = (
            iter_regime_pos_rate if USE_REGIME_POS_RATE_THRESHOLD else None
        )
        base_threshold = calculate_optimal_threshold(
            cal_dir_probs_calibrated,
            y_cal_dir,
            method=THRESHOLD_METHOD,
            verbose=(iteration <= 3),
            regime_pos_rate=regime_rate_for_threshold,
        )

    # ════════════════════════════════════════════════════════════════════════
    # ⭐ THRESHOLD GATES: STRICT SIGNALS ONLY (< 47% or > 58% UP rate)
    # ════════════════════════════════════════════════════════════════════════
    # Gates only activate on EXTREME signals with proven deviation from base.
    # Signals in 47-58% UP range are noise and excluded.
    #
    # EMPIRICAL ANALYSIS (strict filtering):
    #   - Base UP rate: 55.6%
    #   - RISK >= 0.6:  4.2% trigger, 33.3% UP → STRONG bearish (-22.3%)
    #   - BULLISH >= 0.4 (& risk=0): 13.6% trigger, 62.5% UP → Good bullish (+6.9%)
    #   - NO GATE: 82.1% of data, 55.6% UP (base rate)
    #
    RISK_ACTIVATION_THRESHOLD = 0.3  # Trigger: regime 2, V_trans=2, V_unstable, etc.
    RISK_GATE_BOOST = 0.10  # Fixed +0.10 threshold boost when triggered

    BULLISH_ACTIVATION_THRESHOLD = 0.9  # Trigger: hmm 1→3, mom cross up, etc.
    BULLISH_GATE_REDUCTION = 0.00  # Fixed -0.05 threshold reduction when triggered

    threshold_adjustment = 0.0
    gate_triggered = ""

    if USE_RISK_GATE and len(pred_risk_score) > 0:
        if pred_risk_score[0] >= RISK_ACTIVATION_THRESHOLD:
            threshold_adjustment += RISK_GATE_BOOST
            gate_triggered = "RISK"

    # BULLISH gate: Only when bullish score is high AND no risk signals
    if USE_BULLISH_GATE and len(pred_bullish_score) > 0:
        if (
            pred_bullish_score[0] >= BULLISH_ACTIVATION_THRESHOLD
            and pred_risk_score[0] == 0
        ):
            threshold_adjustment -= BULLISH_GATE_REDUCTION
            gate_triggered = "BULL" if not gate_triggered else gate_triggered + "+BULL"

    optimal_threshold = base_threshold + threshold_adjustment
    optimal_threshold = max(
        0.35, min(0.75, optimal_threshold)
    )  # Cap between 0.35 and 0.75

    if iteration <= 3 and gate_triggered:
        print(
            f"    [ThresholdGate] ⚡ {gate_triggered} TRIGGERED! Risk={pred_risk_score[0]:.2f} Bull={pred_bullish_score[0]:.2f} → {base_threshold:.3f} {threshold_adjustment:+.3f} = {optimal_threshold:.3f}"
        )

    # ════════════════════════════════════════════════════════════════════════
    # ⭐ AUC-CONFIDENCE ADJUSTMENT: Pull threshold toward 0.5 when AUC is low
    # ════════════════════════════════════════════════════════════════════════
    optimal_threshold_before_auc = optimal_threshold  # Store for diagnostics
    auc_adjustment = 0.0
    auc_confidence = 1.0  # Default: full confidence when feature disabled

    if USE_AUC_CONFIDENCE_ADJUSTMENT:
        # ⭐ Use ENSEMBLE VAL AUC (not just CB) for confidence calculation
        # This reflects the actual ensemble performance on validation data
        model_auc = ensemble_val_auc

        # Calculate confidence: 0.5 AUC = 0 confidence, 1.0 AUC = 1 confidence
        if model_auc <= AUC_MIN_FOR_CONFIDENCE:
            auc_confidence = 0.0  # Below minimum = no confidence
        else:
            auc_confidence = min(1.0, (model_auc - 0.5) * 2)  # Maps 0.5→0, 1.0→1

        # Uncertainty is inverse of confidence
        auc_uncertainty = 1.0 - auc_confidence

        # Pull threshold toward 0.5 proportional to uncertainty
        # Positive pull when threshold > 0.5, negative when < 0.5
        auc_adjustment = (
            (0.5 - optimal_threshold) * auc_uncertainty * AUC_CONFIDENCE_STRENGTH
        )
        optimal_threshold = optimal_threshold + auc_adjustment
        optimal_threshold = max(0.35, min(0.75, optimal_threshold))  # Re-apply caps

        if iteration <= 3:
            print(
                f"    [AUC-Confidence] EnsAUC={model_auc:.3f} → conf={auc_confidence:.2f}, uncert={auc_uncertainty:.2f} → thr {optimal_threshold_before_auc:.3f} {auc_adjustment:+.4f} = {optimal_threshold:.3f}"
            )

    # Calculate Direction metrics (ensemble uses per-model AUCs computed above)
    # Use actual ensemble AUC for val_auc
    train_auc = ensemble_val_auc  # Approximate - using ensemble VAL as proxy
    val_auc = ensemble_val_auc  # ⭐ Actual ensemble VAL AUC

    # ⭐ PRODUCTION-SAFE: Handle missing direction_target (None in live mode)
    # Reuse has_pred_target from line 1709, but also handle edge case of empty array
    y_pred_dir_arr = y_pred_dir if y_pred_dir is not None else np.array([])
    has_pred_target = (
        has_pred_target and len(y_pred_dir_arr) > 0
    )  # Refine: also check array not empty

    # Logloss per prediction row (only if we have targets)
    pred_logloss_values = []
    if has_pred_target:
        for i in range(actual_pred_size):
            p = np.clip(pred_dir_probs[i], 1e-15, 1 - 1e-15)
            y_true = y_pred_dir_arr[i]
            ll = -(y_true * np.log(p) + (1 - y_true) * np.log(1 - p))
            pred_logloss_values.append(ll)
        pred_logloss = np.mean(pred_logloss_values)

        pred_brier_values = [
            (pred_dir_probs[i] - y_pred_dir_arr[i]) ** 2
            for i in range(actual_pred_size)
        ]
        pred_brier = np.mean(pred_brier_values)
    else:
        pred_logloss = np.nan
        pred_brier = np.nan

    pred_preds = (pred_dir_probs >= optimal_threshold).astype(int)

    # ⭐ DISAGREEMENT GUARD: Force prediction to 0 when models strongly disagree
    if disagreement_guard_triggered:
        pred_preds = np.zeros_like(pred_preds)  # Force all predictions to 0
        if iteration <= 10:
            print(
                f"    [DisagreementGuard] ⚠️ FORCING PREDICTION TO 0 (disagreement={pred_disagreement:.3f})"
            )

    pred_accuracy = (pred_preds == y_pred_dir_arr).mean() if has_pred_target else np.nan

    # ─────────────────────────────────────────────────────────────────
    # STEP 8: TRAIN VOLATILITY MODEL (separate from direction ensemble)
    # ─────────────────────────────────────────────────────────────────
    # Note: Direction models already cleaned up after predictions
    gc.collect()

    # ⭐ AUTOMATIC DRIFT ADJUSTMENT for volatility model too
    vol_params = VOL_MODEL_PARAMS.copy()
    if USE_DRIFT_ADJUSTMENT and drift_active:
        vol_params["l2_leaf_reg"] = vol_params["l2_leaf_reg"] * DRIFT_L2_MULTIPLIER
        vol_params["depth"] = max(3, vol_params["depth"] - DRIFT_DEPTH_REDUCTION)
        vol_params["iterations"] = max(150, int(vol_params["iterations"] * 0.75))

    # ⭐ Direction→Volatility regime coupling
    # Use META ENSEMBLE output for direction regime (meta already trained)
    if USE_HGB:
        train_dir_regime = (
            (cb_train_probs + lgb_train_probs + hgb_train_probs) / 3.0 > 0.5
        ).astype(float)
        val_dir_regime = (
            (cb_val_probs + lgb_val_probs + hgb_val_probs) / 3.0 > 0.5
        ).astype(float)
        cal_dir_regime = (
            (cb_cal_probs + lgb_cal_probs + hgb_cal_probs) / 3.0 > 0.5
        ).astype(float)
    else:
        # CB+LGB mode
        train_dir_regime = ((cb_train_probs + lgb_train_probs) / 2.0 > 0.5).astype(
            float
        )
        val_dir_regime = ((cb_val_probs + lgb_val_probs) / 2.0 > 0.5).astype(float)
        cal_dir_regime = ((cb_cal_probs + lgb_cal_probs) / 2.0 > 0.5).astype(float)
    pred_dir_regime = (pred_dir_probs > 0.5).astype(float)  # Use meta ensemble output

    # Create enhanced volatility features with direction regime
    X_train_vol_enhanced = X_train_vol.copy()
    X_val_vol_enhanced = X_val_vol.copy()
    X_cal_vol_enhanced = X_cal_vol.copy()
    X_pred_vol_enhanced = X_pred_vol.copy()

    X_train_vol_enhanced["dir_regime"] = train_dir_regime
    X_val_vol_enhanced["dir_regime"] = val_dir_regime
    X_cal_vol_enhanced["dir_regime"] = cal_dir_regime
    X_pred_vol_enhanced["dir_regime"] = pred_dir_regime

    # ─────────────────────────────────────────────────────────────────
    # FEATURE SELECTION FOR VOLATILITY: 2-phase training
    # ─────────────────────────────────────────────────────────────────
    if FEATURE_SELECTION_PERCENT is not None and FEATURE_SELECTION_PERCENT < 100:
        # Phase 1: Quick model to get feature importance
        fs_vol_params = vol_params.copy()
        fs_vol_params["iterations"] = min(200, vol_params["iterations"])
        fs_vol_params["early_stopping_rounds"] = 30

        fs_vol_model = CatBoostRegressor(**fs_vol_params)
        fs_vol_model.fit(
            X_train_vol_enhanced,
            y_train_vol,
            sample_weight=train_sample_weights,  # Half-life temporal weighting
            eval_set=(X_val_vol_enhanced, y_val_vol),
            log_cout=NULL_STREAM,
            log_cerr=NULL_STREAM,
        )

        # Get feature importance and select top N%
        all_vol_features = list(X_train_vol_enhanced.columns)
        selected_vol_features = select_top_features(
            fs_vol_model,
            all_vol_features,
            FEATURE_SELECTION_PERCENT,
            len(X_train_vol_enhanced),
            verbose=(iteration <= 3),
        )

        if iteration == 1:
            print(
                f"    [FeatureSel] Volatility: {len(all_vol_features)} → {len(selected_vol_features)} features"
            )

        # Filter to selected features
        X_train_vol_enhanced = X_train_vol_enhanced[selected_vol_features]
        X_val_vol_enhanced = X_val_vol_enhanced[selected_vol_features]
        X_cal_vol_enhanced = X_cal_vol_enhanced[selected_vol_features]
        X_pred_vol_enhanced = X_pred_vol_enhanced[selected_vol_features]

        del fs_vol_model
        gc.collect()

    # Phase 2 (or only phase): Train final volatility model
    volatility_model = CatBoostRegressor(**vol_params)
    volatility_model.fit(
        X_train_vol_enhanced,
        y_train_vol,
        sample_weight=train_sample_weights,  # Half-life temporal weighting
        eval_set=(X_val_vol_enhanced, y_val_vol),
        log_cout=NULL_STREAM,
        log_cerr=NULL_STREAM,
    )
    vol_best_iter = (
        volatility_model.get_best_iteration() or volatility_model.tree_count_
    )

    # Generate predictions for each window (using enhanced volatility features)
    train_vol_preds = volatility_model.predict(X_train_vol_enhanced)
    val_vol_preds = volatility_model.predict(X_val_vol_enhanced)
    cal_vol_preds = volatility_model.predict(
        X_cal_vol_enhanced
    )  # OOS predictions for vol calibration
    pred_vol_preds = volatility_model.predict(X_pred_vol_enhanced)

    # Post-process volatility (must be positive)
    train_vol_preds = np.maximum(train_vol_preds, 1e-8)
    val_vol_preds = np.maximum(val_vol_preds, 1e-8)
    cal_vol_preds = np.maximum(cal_vol_preds, 1e-8)
    pred_vol_preds_raw = np.maximum(pred_vol_preds, 1e-8)

    # ─────────────────────────────────────────────────────────────────
    # STEP 9: VOLATILITY CALIBRATION (on CAL residuals only - per spec)
    # ─────────────────────────────────────────────────────────────────
    # Per specification: volatility calibration uses residuals from CAL window
    # Never use train/val residuals for calibration
    #
    # Method: Empirical rescaling based on CAL residual distribution
    #   residual = |y_true - y_pred_raw| on CAL window
    #   scale_factor = median(actual_vol) / median(pred_vol) on CAL
    #
    cal_vol_residuals = np.abs(y_cal_vol - cal_vol_preds)
    cal_vol_scale = (
        np.median(y_cal_vol) / np.median(cal_vol_preds)
        if np.median(cal_vol_preds) > 0
        else 1.0
    )
    cal_vol_scale = np.clip(cal_vol_scale, 0.5, 2.0)  # Limit extreme rescaling

    # Apply calibration to prediction
    pred_vol_preds = pred_vol_preds_raw * cal_vol_scale

    # Volatility metrics
    train_r2 = r2_score(y_train_vol, train_vol_preds)
    val_r2 = r2_score(y_val_vol, val_vol_preds)

    y_pred_vol_arr = y_pred_vol
    pred_vol_mae_values = [
        np.abs(pred_vol_preds[i] - y_pred_vol_arr[i]) for i in range(actual_pred_size)
    ]
    pred_vol_mae = np.mean(pred_vol_mae_values)
    pred_vol_mse_values = [
        (pred_vol_preds[i] - y_pred_vol_arr[i]) ** 2 for i in range(actual_pred_size)
    ]
    pred_vol_mse = np.mean(pred_vol_mse_values)

    n_vol_features = len(volatility_feature_cols)

    # ════════════════════════════════════════════════════════════════════════
    # STEP 9b: FINAL RETURNS REGRESSION MODEL
    # ════════════════════════════════════════════════════════════════════════
    # Combine all predictions to predict actual forward_returns (continuous):
    #   Features: CB_prob, LGB_prob, Vol_pred, lagged_returns
    #   Target: forward_returns (actual continuous returns)
    #
    # This leverages:
    #   - Direction ensemble (direction signal)
    #   - Volatility prediction (expected magnitude)
    #   - Lagged returns (momentum/mean-reversion)
    #
    pred_returns = np.zeros(actual_pred_size)
    returns_mae = np.nan

    if y_train_ret is not None and y_val_ret is not None:
        # Build features for returns model: combine all model outputs
        if USE_HGB:
            # TRAIN features (all 3 base models + vol + lagged)
            ensemble_train = (cb_train_probs + lgb_train_probs + hgb_train_probs) / 3.0
            X_ret_train = np.column_stack(
                [
                    ensemble_train,  # Ensemble direction prob (3 models)
                    cb_train_probs,  # CatBoost direction
                    lgb_train_probs,  # LightGBM direction
                    hgb_train_probs,  # HistGradientBoosting direction
                    train_vol_preds,  # Volatility prediction
                    lagged_ret_train,  # Lagged returns (momentum)
                    (ensemble_train - 0.5) * train_vol_preds,  # Direction-weighted vol
                ]
            )

            # VAL features (for early stopping)
            ensemble_val = (cb_val_probs + lgb_val_probs + hgb_val_probs) / 3.0
            X_ret_val = np.column_stack(
                [
                    ensemble_val,
                    cb_val_probs,
                    lgb_val_probs,
                    hgb_val_probs,
                    val_vol_preds,
                    lagged_ret_val,
                    (ensemble_val - 0.5) * val_vol_preds,
                ]
            )

            # PRED features
            X_ret_pred = np.column_stack(
                [
                    pred_dir_probs,  # Ensemble prob (after meta)
                    cb_pred_probs_cal,  # CatBoost calibrated
                    lgb_pred_probs_cal,  # LightGBM calibrated
                    hgb_pred_probs_cal,  # HistGradientBoosting calibrated
                    pred_vol_preds,  # Calibrated volatility
                    lagged_ret_pred,  # Lagged returns
                    (pred_dir_probs - 0.5) * pred_vol_preds,  # Direction-weighted vol
                ]
            )
        else:
            # CB+LGB mode: 2 models only
            ensemble_train = (cb_train_probs + lgb_train_probs) / 2.0
            X_ret_train = np.column_stack(
                [
                    ensemble_train,  # Ensemble direction prob (2 models)
                    cb_train_probs,  # CatBoost direction
                    lgb_train_probs,  # LightGBM direction
                    train_vol_preds,  # Volatility prediction
                    lagged_ret_train,  # Lagged returns (momentum)
                    (ensemble_train - 0.5) * train_vol_preds,  # Direction-weighted vol
                ]
            )

            # VAL features
            ensemble_val = (cb_val_probs + lgb_val_probs) / 2.0
            X_ret_val = np.column_stack(
                [
                    ensemble_val,
                    cb_val_probs,
                    lgb_val_probs,
                    val_vol_preds,
                    lagged_ret_val,
                    (ensemble_val - 0.5) * val_vol_preds,
                ]
            )

            # PRED features
            X_ret_pred = np.column_stack(
                [
                    pred_dir_probs,  # Ensemble prob (after meta)
                    cb_pred_probs_cal,  # CatBoost calibrated
                    lgb_pred_probs_cal,  # LightGBM calibrated
                    pred_vol_preds,  # Calibrated volatility
                    lagged_ret_pred,  # Lagged returns
                    (pred_dir_probs - 0.5) * pred_vol_preds,  # Direction-weighted vol
                ]
            )

        # Train returns regressor (simple, fast)
        returns_model = Ridge(alpha=10.0)  # L2 regularized - stable for small samples
        returns_model.fit(X_ret_train, y_train_ret)

        # Predict forward returns
        pred_returns = returns_model.predict(X_ret_pred)

        # Calculate returns MAE on prediction
        if y_pred_ret is not None:
            returns_mae = np.mean(np.abs(pred_returns - y_pred_ret))

        if iteration <= 3:
            print(
                f"    [Returns] Ridge trained, pred={pred_returns[0]:.5f}, actual={y_pred_ret[0]:.5f}, MAE={returns_mae:.5f}"
            )

        del returns_model

    # ─────────────────────────────────────────────────────────────────
    # STEP 10: GET AGGREGATED SIGNAL VALUES (if enabled)
    # ─────────────────────────────────────────────────────────────────
    agg_signal_values = {}
    if USE_SIGNAL_AGGREGATION and aggregated_feature_cols:
        for col in aggregated_feature_cols:
            if col in X_pred_dir.columns:
                agg_signal_values[col] = X_pred_dir[col].values

    # ─────────────────────────────────────────────────────────────────
    # STEP 10B: SIGNAL AGREEMENT SCORING FOR PRECISION ZONES
    # ─────────────────────────────────────────────────────────────────
    # Based on analysis showing:
    #   - 3+ bearish signals: 40.2% UP (vs 55.6% base) = strong SHORT edge
    #   - 3+ bullish signals: 59.0% UP = modest LONG edge
    #   - Regime filtering can improve precision significantly
    #
    # Count bearish/bullish signals for each prediction row
    bearish_counts = np.zeros(actual_pred_size, dtype=int)
    bullish_counts = np.zeros(actual_pred_size, dtype=int)

    for i in range(actual_pred_size):
        row = pred_slice.iloc[i]

        # Bearish signals: conditions associated with DOWN days
        if "high_vol_regime" in row and row["high_vol_regime"] == 1:
            bearish_counts[i] += 1
        if "group_if_any_severe" in row and row["group_if_any_severe"] == 1:
            bearish_counts[i] += 1
        if "hmm_regime" in row and row["hmm_regime"] == 2:
            bearish_counts[i] += 1
        if "HMM4_if_is_anomaly" in row and row["HMM4_if_is_anomaly"] == 1:
            bearish_counts[i] += 1
        if "uptrend_regime" in row and row["uptrend_regime"] == 0:
            bearish_counts[i] += 1

        # Bullish signals: conditions associated with UP days
        if "high_vol_regime" in row and row["high_vol_regime"] == 0:
            bullish_counts[i] += 1
        if "group_if_any_severe" in row and row["group_if_any_severe"] == 0:
            bullish_counts[i] += 1
        if "uptrend_regime" in row and row["uptrend_regime"] == 1:
            bullish_counts[i] += 1

    def compute_precision_zone(bearish_n, bullish_n, dir_prob, threshold):
        """
        Compute precision zone based on signal agreement.

        Zones:
          HIGH_CONF_LONG:  bullish >= 3 AND prob > threshold → high precision long
          HIGH_CONF_SHORT: bearish >= 3 AND prob < threshold → high precision short
          MODERATE:        some signal agreement
          LOW_CONF:        conflicting signals or no edge → avoid trading
        """
        pred_dir = 1 if dir_prob >= threshold else 0

        if pred_dir == 1 and bullish_n >= 3:
            return "HIGH_CONF_LONG"
        elif pred_dir == 0 and bearish_n >= 3:
            return "HIGH_CONF_SHORT"
        elif pred_dir == 1 and bearish_n >= 2:
            return "LOW_CONF"  # Predicting UP but bearish signals present
        elif pred_dir == 0 and bullish_n >= 2:
            return "LOW_CONF"  # Predicting DOWN but bullish signals present
        elif bullish_n >= 2 or bearish_n >= 2:
            return "MODERATE"
        else:
            return "NEUTRAL"

    # ─────────────────────────────────────────────────────────────────
    # STEP 11: CLASSIFY VOLATILITY REGIME (from predicted volatility)
    # ─────────────────────────────────────────────────────────────────
    # Thresholds based on historical volatility percentiles:
    #   LOW:       < P25 (0.0021) - calm market, good for directional trades
    #   MEDIUM:    P25-P50 (0.0021-0.0055) - normal conditions
    #   HIGH:      P50-P75 (0.0055-0.0105) - elevated risk
    #   VERY_HIGH: P75-P90 (0.0105-0.0171) - high risk, reduce position
    #   EXTREME:   > P90 (0.0171+) - crisis mode, defensive only
    #
    VOL_THRESH_LOW = 0.0021  # P25
    VOL_THRESH_MED = 0.0055  # P50
    VOL_THRESH_HIGH = 0.0105  # P75
    VOL_THRESH_VHIGH = 0.0171  # P90

    def classify_vol_regime(vol_pred):
        """Convert volatility prediction to actionable regime."""
        if vol_pred < VOL_THRESH_LOW:
            return "LOW"
        elif vol_pred < VOL_THRESH_MED:
            return "MEDIUM"
        elif vol_pred < VOL_THRESH_HIGH:
            return "HIGH"
        elif vol_pred < VOL_THRESH_VHIGH:
            return "VERY_HIGH"
        else:
            return "EXTREME"

    # ─────────────────────────────────────────────────────────────────
    # STEP 12: STORE PREDICTIONS
    # ─────────────────────────────────────────────────────────────────
    # Get base rate for regime threshold adjustment (from CAL window)
    cal_base_rate = y_cal_dir.mean()

    for i in range(actual_pred_size):
        risk_score_i = pred_risk_score[i] if i < len(pred_risk_score) else 0
        vol_regime = classify_vol_regime(pred_vol_preds[i])

        # ⭐ REGIME-SPECIFIC THRESHOLD: Adjust based on volatility regime
        # In high vol, be more conservative (shift threshold toward 0.5)
        effective_threshold = adjust_threshold_for_regime(
            base_threshold=optimal_threshold,
            vol_regime=vol_regime,
            base_rate=cal_base_rate,
            verbose=(
                iteration <= 3 and i == 0
            ),  # Only log first sample of early iterations
        )

        # Compute precision zone based on signal agreement
        precision_zone = compute_precision_zone(
            bearish_counts[i],
            bullish_counts[i],
            pred_dir_probs[i],
            effective_threshold,  # Use regime-adjusted threshold
        )

        pred_record = {
            "pred_idx": pred_start + i,
            "direction_proba_raw": pred_dir_probs_raw[i],  # Raw model probability
            "direction_proba_calibrated": pred_dir_probs[
                i
            ],  # After calibration (same as raw when disabled)
            "direction_proba": pred_dir_probs[i],  # Final probability
            "direction_actual": y_pred_dir_arr[i]
            if has_pred_target
            else np.nan,  # ⭐ PRODUCTION-SAFE
            "direction_pred": 1
            if pred_dir_probs[i] >= effective_threshold
            else 0,  # Use regime-adjusted
            "direction_correct": int(
                (pred_dir_probs[i] >= effective_threshold) == y_pred_dir_arr[i]
            )
            if has_pred_target
            else np.nan,  # ⭐ PRODUCTION-SAFE
            "direction_logloss": pred_logloss_values[i] if has_pred_target else np.nan,
            "direction_brier": pred_brier_values[i] if has_pred_target else np.nan,
            "direction_threshold": effective_threshold,  # Store effective (regime-adjusted) threshold
            "direction_threshold_base": optimal_threshold,  # ⭐ Store base threshold for analysis
            "threshold_method": THRESHOLD_METHOD,
            "cb_cal_method": cb_cal_method,  # ⭐ ENSEMBLE: per-model calibration
            "lgb_cal_method": lgb_cal_method,
            "meta_type": meta_type,  # ⭐ ENSEMBLE: meta stacker type
            "cb_pred_prob": cb_pred_probs_cal[
                i
            ],  # ⭐ ENSEMBLE: per-model calibrated probs
            "lgb_pred_prob": lgb_pred_probs_cal[i],
            "model_disagreement": float(
                np.abs(cb_pred_probs_cal[i] - lgb_pred_probs_cal[i])
            ),  # ⭐ Per-sample disagreement
            "disagreement_guard": disagreement_guard_triggered,  # ⭐ Whether guard was triggered
            "risk_guard_score": risk_score_i,  # Risk level at prediction time
            "threshold_adjustment": threshold_adjustment,  # Gate adjustment applied to threshold
            "auc_adjustment": auc_adjustment,  # ⭐ AUC-confidence threshold adjustment
            "auc_confidence": auc_confidence
            if USE_AUC_CONFIDENCE_ADJUSTMENT
            else 1.0,  # Model confidence from AUC
            "drift_active": drift_active,  # ⭐ Track if drift adjustment was applied
            # ⭐ NEW: Precision zone tracking
            "n_bearish_signals": bearish_counts[i],
            "n_bullish_signals": bullish_counts[i],
            "precision_zone": precision_zone,
            "volatility_pred_raw": pred_vol_preds_raw[i],  # Before calibration
            "volatility_pred": pred_vol_preds[i],  # After calibration
            "volatility_regime": vol_regime,  # ⭐ NEW: Volatility regime classification
            "volatility_cal_scale": cal_vol_scale,  # Calibration scale factor
            "volatility_actual": y_pred_vol_arr[i],
            "volatility_ae": pred_vol_mae_values[i],
            # ⭐ RETURNS PREDICTION: Final regression output
            "returns_pred": pred_returns[i],  # Predicted forward returns
            "returns_actual": y_pred_ret[i] if y_pred_ret is not None else np.nan,
            "returns_ae": np.abs(pred_returns[i] - y_pred_ret[i])
            if y_pred_ret is not None
            else np.nan,
            "lagged_returns": lagged_ret_pred[i],  # Input feature for reference
            "iteration": iteration,
        }
        # Add aggregated signal values
        for col in aggregated_feature_cols:
            pred_record[col] = (
                agg_signal_values[col][i] if col in agg_signal_values else np.nan
            )

        walkforward_predictions.append(pred_record)

    iter_elapsed = time.time() - iter_start_time

    walkforward_iterations.append(
        {
            "iteration": iteration,
            "train_start": train_start,
            "train_end": train_end,
            "val_start": val_start,
            "val_end": val_end,
            "cal_start": cal_start,
            "cal_end": cal_end,
            "pred_start": pred_start,
            "pred_end": pred_end,
            "train_auc": train_auc,
            "val_auc": val_auc,
            "cal_auc": cal_auc,
            "cb_val_auc": cb_val_auc,  # ⭐ ENSEMBLE: per-model AUCs
            "lgb_val_auc": lgb_val_auc,
            "ensemble_val_auc": ensemble_val_auc,  # ⭐ Actual ensemble AUC
            "meta_type": meta_type,
            "pred_logloss": pred_logloss,
            "pred_brier": pred_brier,
            "pred_accuracy": pred_accuracy,
            "optimal_threshold": optimal_threshold,
            "threshold_method": THRESHOLD_METHOD,
            "cb_cal_method": cb_cal_method,  # ⭐ ENSEMBLE: per-model calibration
            "lgb_cal_method": lgb_cal_method,
            "pred_disagreement": pred_disagreement,  # ⭐ DISAGREEMENT GUARD: prediction-level
            "disagreement_guard_triggered": disagreement_guard_triggered,
            "train_r2": train_r2,
            "val_r2": val_r2,
            "pred_vol_mae": pred_vol_mae,
            "vol_cal_scale": cal_vol_scale,
            "pred_returns_mae": returns_mae,  # ⭐ RETURNS: prediction MAE
            "cb_best_iter": cb_best_iter,  # ⭐ ENSEMBLE: per-model iterations
            "lgb_best_iter": lgb_best_iter,
            "vol_best_iter": vol_best_iter,
            "iter_time_sec": iter_elapsed,
            "drift_detected": drift_info["drift_detected"] if drift_info else False,
            "drift_active": drift_active,  # ⭐ Track if drift adjustment was applied
        }
    )

    # ════════════════════════════════════════════════════════════════════════
    # ⭐ STORE PREDICTIONS BY WINDOW VARIANT
    # ════════════════════════════════════════════════════════════════════════
    # Store predictions from the training we just completed (uses original windows)
    # These will be used by configs with window='original'
    predictions_by_window = {
        "original": {
            "cb_pred_probs": cb_pred_probs.copy(),
            "cb_cal_probs": cb_cal_probs.copy(),
            "cb_pred_probs_cal": cb_pred_probs_cal.copy(),
            "cb_cal_probs_cal": cb_cal_probs_cal.copy(),
            "lgb_pred_probs": lgb_pred_probs.copy(),
            "lgb_cal_probs": lgb_cal_probs.copy(),
            "lgb_pred_probs_cal": lgb_pred_probs_cal.copy(),
            "lgb_cal_probs_cal": lgb_cal_probs_cal.copy(),
            "y_cal_dir": y_cal_dir.copy()
            if hasattr(y_cal_dir, "copy")
            else np.array(y_cal_dir),
            "cb_val_auc": cb_val_auc,
        }
    }

    # ════════════════════════════════════════════════════════════════════════
    # ⭐ SECOND TRAINING PASS: SHRUNK WINDOW VARIANT (if different from original)
    # ════════════════════════════════════════════════════════════════════════
    # When regime triggers window shrink, train a second set of models on shrunk windows
    # This allows configs to choose between original and shrunk predictions
    if has_shrunk_variant:
        # Get shrunk window sizes
        shrunk_train_size = windows_shrunk["train"]
        shrunk_cal_size = windows_shrunk["cal"]
        shrunk_val_size = windows_shrunk["val"]

        # Calculate shrunk window boundaries (same pred_start/end)
        shrunk_val_end = pred_start
        shrunk_val_start = shrunk_val_end - shrunk_val_size
        shrunk_cal_end = shrunk_val_start
        shrunk_cal_start = shrunk_cal_end - shrunk_cal_size
        shrunk_train_end = shrunk_cal_start
        shrunk_train_start = shrunk_train_end - shrunk_train_size

        # Only proceed if we have valid boundaries
        if shrunk_train_start >= 0:
            # Slice data for shrunk variant
            shrunk_train_slice = source_df.iloc[shrunk_train_start:shrunk_train_end]
            shrunk_val_slice = source_df.iloc[shrunk_val_start:shrunk_val_end]
            shrunk_cal_slice = source_df.iloc[shrunk_cal_start:shrunk_cal_end]
            # pred_slice is same for both variants

            # Shuffle VAL+CAL if enabled
            if SHUFFLE_VAL_CAL_POOL:
                shrunk_val_cal_combined = pd.concat(
                    [shrunk_val_slice, shrunk_cal_slice], axis=0
                )
                shrunk_val_cal_shuffled = shrunk_val_cal_combined.sample(
                    frac=1.0, random_state=iteration + 1000
                )
                shrunk_cal_slice = shrunk_val_cal_shuffled.iloc[:shrunk_cal_size].copy()
                shrunk_val_slice = shrunk_val_cal_shuffled.iloc[
                    shrunk_cal_size : shrunk_cal_size + shrunk_val_size
                ].copy()

            # Use same features as original (already selected)
            # Use reindex to handle missing columns gracefully (fill with 0)
            shrunk_X_train_dir = shrunk_train_slice.reindex(
                columns=X_train_dir.columns, fill_value=0
            ).fillna(0)
            shrunk_X_val_dir = shrunk_val_slice.reindex(
                columns=X_train_dir.columns, fill_value=0
            ).fillna(0)
            shrunk_X_cal_dir = shrunk_cal_slice.reindex(
                columns=X_train_dir.columns, fill_value=0
            ).fillna(0)
            shrunk_X_pred_dir = pred_slice.reindex(
                columns=X_train_dir.columns, fill_value=0
            ).fillna(0)

            shrunk_y_train_dir = shrunk_train_slice[DIRECTION_TARGET]
            shrunk_y_val_dir = shrunk_val_slice[DIRECTION_TARGET]
            shrunk_y_cal_dir = shrunk_cal_slice[DIRECTION_TARGET].values

            # Sample weights for shrunk variant
            shrunk_train_sample_weights = (
                calculate_half_life_weights(
                    len(shrunk_X_train_dir),
                    half_life=current_half_life,
                    min_weight=MIN_SAMPLE_WEIGHT,
                )
                if USE_HALF_LIFE_WEIGHTING
                else None
            )

            # ── TRAIN CATBOOST (shrunk) ──
            shrunk_cb_params = cb_params.copy()
            for bad_key in [
                "model_type",
                "max_depth",
                "reg_lambda",
                "n_estimators",
                "min_child_samples",
                "num_leaves",
                "subsample_freq",
                "boosting_type",
                "objective",
                "metric",
                "n_jobs",
            ]:
                shrunk_cb_params.pop(bad_key, None)

            shrunk_cb_model = CatBoostClassifier(**shrunk_cb_params)
            shrunk_cb_model.fit(
                shrunk_X_train_dir,
                shrunk_y_train_dir,
                sample_weight=shrunk_train_sample_weights,
                eval_set=(shrunk_X_val_dir, shrunk_y_val_dir),
                log_cout=NULL_STREAM,
                log_cerr=NULL_STREAM,
            )

            shrunk_cb_cal_probs = shrunk_cb_model.predict_proba(shrunk_X_cal_dir)[:, 1]
            shrunk_cb_pred_probs = shrunk_cb_model.predict_proba(shrunk_X_pred_dir)[
                :, 1
            ]
            shrunk_cb_val_auc = roc_auc_score(
                shrunk_y_val_dir, shrunk_cb_model.predict_proba(shrunk_X_val_dir)[:, 1]
            )

            del shrunk_cb_model
            gc.collect()

            # ── TRAIN LIGHTGBM (shrunk) ──
            if not USE_SINGLE_MODEL:
                import lightgbm as lgb

                shrunk_lgb_params = LIGHTGBM_DIR_PARAMS.copy()
                shrunk_lgb_params["scale_pos_weight"] = (
                    scale_pos_weight if USE_CLASS_BALANCING else 1.0
                )

                shrunk_lgb_model = LGBMClassifier(**shrunk_lgb_params)
                shrunk_lgb_model.fit(
                    shrunk_X_train_dir,
                    shrunk_y_train_dir,
                    sample_weight=shrunk_train_sample_weights,
                    eval_set=[(shrunk_X_val_dir, shrunk_y_val_dir)],
                    callbacks=[lgb.early_stopping(stopping_rounds=300, verbose=False)],
                )

                shrunk_lgb_cal_probs = shrunk_lgb_model.predict_proba(shrunk_X_cal_dir)[
                    :, 1
                ]
                shrunk_lgb_pred_probs = shrunk_lgb_model.predict_proba(
                    shrunk_X_pred_dir
                )[:, 1]

                del shrunk_lgb_model
                gc.collect()
            else:
                shrunk_lgb_cal_probs = shrunk_cb_cal_probs.copy()
                shrunk_lgb_pred_probs = shrunk_cb_pred_probs.copy()

            # Apply existing calibrators to shrunk predictions
            if cb_calibrator is not None:
                shrunk_cb_pred_probs_cal = cb_calibrator.predict_proba(
                    shrunk_cb_pred_probs.reshape(-1, 1)
                )[:, 1]
                shrunk_cb_cal_probs_cal = cb_calibrator.predict_proba(
                    shrunk_cb_cal_probs.reshape(-1, 1)
                )[:, 1]
            else:
                shrunk_cb_pred_probs_cal = shrunk_cb_pred_probs.copy()
                shrunk_cb_cal_probs_cal = shrunk_cb_cal_probs.copy()

            if lgb_calibrator is not None:
                shrunk_lgb_pred_probs_cal = lgb_calibrator.predict_proba(
                    shrunk_lgb_pred_probs.reshape(-1, 1)
                )[:, 1]
                shrunk_lgb_cal_probs_cal = lgb_calibrator.predict_proba(
                    shrunk_lgb_cal_probs.reshape(-1, 1)
                )[:, 1]
            else:
                shrunk_lgb_pred_probs_cal = shrunk_lgb_pred_probs.copy()
                shrunk_lgb_cal_probs_cal = shrunk_lgb_cal_probs.copy()

            # Store shrunk predictions
            predictions_by_window["shrunk"] = {
                "cb_pred_probs": shrunk_cb_pred_probs,
                "cb_cal_probs": shrunk_cb_cal_probs,
                "cb_pred_probs_cal": shrunk_cb_pred_probs_cal,
                "cb_cal_probs_cal": shrunk_cb_cal_probs_cal,
                "lgb_pred_probs": shrunk_lgb_pred_probs,
                "lgb_cal_probs": shrunk_lgb_cal_probs,
                "lgb_pred_probs_cal": shrunk_lgb_pred_probs_cal,
                "lgb_cal_probs_cal": shrunk_lgb_cal_probs_cal,
                "y_cal_dir": shrunk_y_cal_dir,
                "cb_val_auc": shrunk_cb_val_auc,
            }

            if iteration <= 10 or iteration % 100 == 0:
                print(
                    f"    [ShrunkVariant] Trained: CB_AUC={shrunk_cb_val_auc:.3f} (orig={cb_val_auc:.3f})"
                )
        else:
            # Can't train shrunk variant - use original
            predictions_by_window["shrunk"] = predictions_by_window["original"]
    else:
        # No shrunk variant - use original for both
        predictions_by_window["shrunk"] = predictions_by_window["original"]

    # ════════════════════════════════════════════════════════════════════════
    # ⭐ MULTI-CONFIG PARALLEL EVALUATION
    # ════════════════════════════════════════════════════════════════════════
    # Evaluate all configurations using actual targets (for tracking/display only)
    # ⚠️ NOTE ON DATA FLOW:
    # - actual_label = today's outcome (used for tracking AFTER prediction is made)
    # - config_scorer.update() stores (iteration, tp, fp, tn, fn)
    # - config_scorer.select_best_config() uses only it < current_iter (past data only)
    # - rolling_actuals is updated LATER (line 4179) so market ratio uses past data
    # This ensures no future leakage - tracking is separate from prediction workflow
    # ⭐ PRODUCTION-SAFE: Skip evaluation if no target available
    if MULTI_CONFIG_TRACKING and has_pred_target:
        actual_label = int(y_pred_dir_arr[0])  # Today's actual (for tracking only)

        # ⭐ Collect raw probabilities AND thresholds for all configs (for ensemble signal + V3 alignment)
        config_probs_for_ensemble = {}
        config_thresholds_for_ensemble = {}  # ⭐ NEW: Per-config thresholds

        for cfg in ALL_CONFIGS:
            cfg_name = cfg["name"]

            # ⭐ Select predictions based on window variant
            window_var = cfg.get("window", "original")
            preds = predictions_by_window[window_var]

            # Get predictions for this window variant
            wv_cb_pred_probs = preds["cb_pred_probs"]
            wv_cb_pred_probs_cal = preds["cb_pred_probs_cal"]
            wv_cb_cal_probs = preds["cb_cal_probs"]
            wv_cb_cal_probs_cal = preds["cb_cal_probs_cal"]
            wv_lgb_pred_probs = preds["lgb_pred_probs"]
            wv_lgb_pred_probs_cal = preds["lgb_pred_probs_cal"]
            wv_lgb_cal_probs = preds["lgb_cal_probs"]
            wv_lgb_cal_probs_cal = preds["lgb_cal_probs_cal"]
            wv_y_cal_dir = preds["y_cal_dir"]
            wv_cb_val_auc = preds["cb_val_auc"]

            # Select probability based on model config
            if cfg["model"] == "single":
                # Single model: use CB probs
                if cfg["calibration"] == "none":
                    cfg_prob = wv_cb_pred_probs[0]  # Raw CB
                else:
                    cfg_prob = wv_cb_pred_probs_cal[0]  # Calibrated CB
            else:
                # Ensemble: use combined probs (CB+LGB mode)
                if cfg["calibration"] == "none":
                    cfg_prob = (wv_cb_pred_probs[0] + wv_lgb_pred_probs[0]) / 2.0
                else:
                    cfg_prob = (
                        wv_cb_pred_probs_cal[0] + wv_lgb_pred_probs_cal[0]
                    ) / 2.0

            # Calculate threshold based on config
            if cfg["threshold"] == "quantile_match":
                if cfg["model"] == "single":
                    cfg_cal_probs = (
                        wv_cb_cal_probs_cal
                        if cfg["calibration"] != "none"
                        else wv_cb_cal_probs
                    )
                else:
                    # CB+LGB mode
                    if cfg["calibration"] != "none":
                        cfg_cal_probs = (
                            wv_cb_cal_probs_cal + wv_lgb_cal_probs_cal
                        ) / 2.0
                    else:
                        cfg_cal_probs = (wv_cb_cal_probs + wv_lgb_cal_probs) / 2.0
                pos_rate = np.mean(wv_y_cal_dir)
                cfg_threshold = np.percentile(cfg_cal_probs, (1 - pos_rate) * 100)
            elif cfg["threshold"] == "youden_j":
                cfg_threshold = 0.5  # Simplified - would need full calculation
            elif cfg["threshold"] == "class_balanced":
                cfg_threshold = np.mean(wv_y_cal_dir)
            else:
                cfg_threshold = 0.5

            # Apply AUC adjustment if enabled for this config
            # ⭐ Use window-variant AUC for adjustment
            if cfg["auc_adjust"]:
                cfg_auc_conf = max(0, min(1, (wv_cb_val_auc - 0.5) * 2))
                cfg_auc_uncert = 1.0 - cfg_auc_conf
                cfg_auc_adj = (0.5 - cfg_threshold) * cfg_auc_uncert * 0.5
                cfg_threshold = cfg_threshold + cfg_auc_adj

            # Apply regime adjustment if enabled for this config
            if cfg["regime_thr"]:
                vol_regime = classify_vol_regime(pred_vol_preds[0])
                regime_adj = REGIME_THRESHOLD_ADJUSTMENTS.get(vol_regime, 0.0)
                cfg_threshold = cfg_threshold + regime_adj

            # Clamp threshold
            cfg_threshold = max(0.35, min(0.75, cfg_threshold))

            # ⭐ Store raw probability AND threshold for ensemble signal + V3 alignment
            config_probs_for_ensemble[cfg_name] = cfg_prob
            config_thresholds_for_ensemble[cfg_name] = (
                cfg_threshold  # ⭐ NEW: Per-config threshold
            )

            # Make prediction
            cfg_pred = 1 if cfg_prob >= cfg_threshold else 0

            # Classify result
            if cfg_pred == 1 and actual_label == 1:
                cfg_result = "TP"
            elif cfg_pred == 0 and actual_label == 0:
                cfg_result = "TN"
            elif cfg_pred == 1 and actual_label == 0:
                cfg_result = "FP"
            else:
                cfg_result = "FN"

            # Store result
            config_results[cfg_name]["rolling_pred_types"].append(cfg_result)
            config_results[cfg_name]["predictions"].append(
                {
                    "iteration": iteration,
                    "prob": cfg_prob,
                    "threshold": cfg_threshold,
                    "pred": cfg_pred,
                    "actual": actual_label,
                    "result": cfg_result,
                }
            )

            # Update counters (backtest logging only - for debugging/comparison)
            if cfg_result == "TP":
                config_results[cfg_name]["rolling_tp"] += 1
                config_results[cfg_name]["total_correct"] += 1
            elif cfg_result == "TN":
                config_results[cfg_name]["rolling_tn"] += 1
                config_results[cfg_name]["total_correct"] += 1
            elif cfg_result == "FP":
                config_results[cfg_name]["rolling_fp"] += 1
            else:  # FN
                config_results[cfg_name]["rolling_fn"] += 1
            config_results[cfg_name]["total_predictions"] += 1

            # ⭐ UPDATE SCORER with actual target evaluation (for tracking/display)
            tp_bt = 1 if cfg_result == "TP" else 0
            fp_bt = 1 if cfg_result == "FP" else 0
            tn_bt = 1 if cfg_result == "TN" else 0
            fn_bt = 1 if cfg_result == "FN" else 0
            config_scorer.update(cfg_name, iteration, tp_bt, fp_bt, tn_bt, fn_bt)

        # ⭐ Compute current market ratio (uses rolling actuals for display)
        if len(rolling_actuals) > 10:
            mkt_up = sum(rolling_actuals)
            mkt_down = len(rolling_actuals) - mkt_up
            current_market_ratio = mkt_up / mkt_down if mkt_down > 0 else 2.0
        else:
            current_market_ratio = 1.0  # Neutral until we have history

        # ⭐ SELECT BEST CONFIG FOR THIS ITERATION (uses only past data via it < current_iter filter)
        # V3.1: Use REGIME-ADAPTIVE selection after warmup period
        USE_REGIME_ADAPTIVE_CONFIG = True  # Toggle for regime-adaptive config selection
        if USE_REGIME_ADAPTIVE_CONFIG and iteration >= 50:
            selected_config_name, selection_info = (
                config_scorer.select_regime_adapted_config(
                    iteration, market_ratio=current_market_ratio, n_top=N_TOP_CONFIGS
                )
            )
            # Log regime info periodically
            if iteration <= 10 or iteration % 100 == 0:
                regime_info = selection_info.get("regime_info", {})
                regime = selection_info.get("regime", "STABLE")
                conf = selection_info.get("confidence", 0.0)
                print(
                    f"    [RegimeAdaptive] {regime} (conf={conf:.2f}) → {selection_info.get('decision', 'N/A')}"
                )
        else:
            selected_config_name, selection_info = config_scorer.select_best_config(
                iteration
            )

        # ⭐ Compute gate context for current prediction (index 0)
        # precision_zone and net_signal provide scenario context for signal calculation
        current_precision_zone = compute_precision_zone(
            bearish_counts[0], bullish_counts[0], pred_dir_probs[0], optimal_threshold
        )
        current_net_signal = int(bullish_counts[0] - bearish_counts[0])

        # ════════════════════════════════════════════════════════════════════
        # ⭐ NOTE: dual_ema_data is now calculated AFTER top10_configs below
        # ════════════════════════════════════════════════════════════════════

        # ════════════════════════════════════════════════════════════════════
        # ⭐ BENCHMARK SIGNAL - Gates only, works from iteration 1
        # Uses: alpha gate, direction gate ONLY (no EMA scaling)
        # Purpose: Provides consistent metric from start for fair comparison
        # ════════════════════════════════════════════════════════════════════
        benchmark_signal, benchmark_meta = config_ensemble.calculate_benchmark_signal(
            probability=pred_dir_probs[0],  # Ensemble probability P(UP)
            threshold=optimal_threshold,  # Calibrated threshold
            estimated_return=pred_returns[0] if len(pred_returns) > 0 else 0.0,
            risk_free_rate=risk_free_pred[0] if len(risk_free_pred) > 0 else 0.0,
            verbose=False,
        )

        # ════════════════════════════════════════════════════════════════════
        # ⭐ BASELINE POSITION SIZING (NEW - replaces complex ensemble signal)
        # Uses: alpha gate, direction gate, ratio gate, EMA/RSI scaling
        # Note: EMA scaling only active after we get Top10 configs
        # ════════════════════════════════════════════════════════════════════

        # ⭐ Initialize dual_ema_data with defaults (will be updated after top10_configs)
        dual_ema_data = {
            "has_data": False,
            "long_term_ema": 1.0,
            "short_term_ema": 1.0,
            "long_term_rsi": 50.0,
            "short_term_rsi": 50.0,
        }

        # ⭐ Calculate PAST ratio from rolling_pred_types (before current iter appended)
        # This is used as a gate: only enter position if past ratio >= 1.0
        past_tp = sum(1 for pt in rolling_pred_types if pt == "TP")
        past_fp = sum(1 for pt in rolling_pred_types if pt == "FP")
        if past_fp > 0:
            past_ratio = past_tp / past_fp
        elif past_tp > 0:
            past_ratio = float("inf")  # All TPs, no FPs - very good
        else:
            past_ratio = None  # No data yet - skip ratio gate during warmup

        baseline_signal, baseline_meta = (
            config_ensemble.calculate_position_size_baseline(
                probability=pred_dir_probs[0],  # Ensemble probability P(UP)
                threshold=optimal_threshold,  # Calibrated threshold
                estimated_return=pred_returns[0] if len(pred_returns) > 0 else 0.0,
                risk_free_rate=risk_free_pred[0] if len(risk_free_pred) > 0 else 0.0,
                dual_ema_data=dual_ema_data,
                past_ratio=past_ratio,  # ⭐ Ratio gate: must be >= 1.0
                verbose=False,  # Set True to debug
            )
        )

        # ════════════════════════════════════════════════════════════════════
        # ⭐ META-MODEL POSITION SIZING V3 (Clean modular pipeline)
        # Pipeline: Gate → Rolling EMA Ratio → Top10 Alignment → Vol Adj → Position
        # Goal: Methodical position sizing with adaptable recent performance
        # ════════════════════════════════════════════════════════════════════

        # Extract regime info
        current_pred_row = pred_slice.iloc[0]
        high_vol = int(current_pred_row.get("high_vol_regime", 0)) == 1

        # Build Top10 config predictions list (for V3 alignment calculation)
        # Get Top10 stable configs from the ensemble scorer
        stable_configs = config_ensemble.get_stable_configs(iteration)
        top10_configs = stable_configs[:10] if stable_configs else []

        # ⭐ Extract BEST ratio from Top10 configs for position sizing
        # The position sizing should use the BEST available ratio, not the selected config's ratio
        best_top10_ratio = (
            max((cfg.get("ratio", 1.0) for cfg in top10_configs), default=1.0)
            if top10_configs
            else 1.0
        )

        # ════════════════════════════════════════════════════════════════════
        # ⭐ DUAL EMA/RSI - Use LAST iteration's EMAs (updated AFTER outcome known)
        # LtEMA/StEMA track the strategy's rolling ratio from "Ratio" column
        # They're updated at the END of iteration when we know TP/FP outcome
        # ════════════════════════════════════════════════════════════════════
        # Use cached values from previous iteration (EMAs updated after outcome)

        # ⭐ HULL-OPTIMAL: Calculate rolling strategy vs market performance
        # This helps scale position based on recent performance (winning/losing streak)
        rolling_strategy_vs_market = 0.0  # Default: neutral
        hull_streak_window = 20  # Use last 20 iterations
        if (
            len(rolling_strategy_returns) >= hull_streak_window
            and len(rolling_market_returns) >= hull_streak_window
        ):
            # Compare sum of recent strategy returns vs market returns
            recent_strategy = sum(list(rolling_strategy_returns)[-hull_streak_window:])
            recent_market = sum(list(rolling_market_returns)[-hull_streak_window:])
            rolling_strategy_vs_market = (
                recent_strategy - recent_market
            )  # Positive = beating market

        if len(config_scorer.actual_ratio_history) >= 5:
            ratio_series = [r for _, r in config_scorer.actual_ratio_history]
            lt_alpha = 2.0 / (config_scorer.lt_ema_span + 1)
            st_alpha = 2.0 / (config_scorer.st_ema_span + 1)
            lt_ema = ratio_series[0]
            st_ema = ratio_series[0]
            for r in ratio_series[1:]:
                lt_ema = lt_alpha * r + (1 - lt_alpha) * lt_ema
                st_ema = st_alpha * r + (1 - st_alpha) * st_ema
            # ⭐ HULL-V2: Calculate cumulative market return for market regime detection
            cumulative_market_return = (
                sum(rolling_market_returns) if rolling_market_returns else 0.0
            )
            dual_ema_data = {
                "has_data": True,
                "long_term_ema": lt_ema,
                "short_term_ema": st_ema,
                "long_term_rsi": 50.0,
                "short_term_rsi": 50.0,
                "rolling_strategy_vs_market": rolling_strategy_vs_market,  # ⭐ For Hull-optimal streak scaling
                "cumulative_market_return": cumulative_market_return,  # ⭐ HULL-V2: For market regime detection
            }
        else:
            cumulative_market_return = (
                sum(rolling_market_returns) if rolling_market_returns else 0.0
            )
            dual_ema_data = {
                "has_data": False,
                "long_term_ema": 1.0,
                "short_term_ema": 1.0,
                "long_term_rsi": 50.0,
                "short_term_rsi": 50.0,
                "rolling_strategy_vs_market": rolling_strategy_vs_market,
                "cumulative_market_return": cumulative_market_return,
            }  # ⭐ HULL-V2

        # Build config_predictions list with prob and threshold for each config
        # ⭐ Use per-config thresholds for accurate alignment calculation
        config_predictions_v3 = []
        for cfg in top10_configs:
            cfg_name = cfg["name"]
            cfg_prob = config_probs_for_ensemble.get(cfg_name, 0.5)
            cfg_thr = config_thresholds_for_ensemble.get(
                cfg_name, optimal_threshold
            )  # ⭐ Per-config threshold
            config_predictions_v3.append(
                {
                    "name": cfg_name,  # ⭐ Add name for voting system
                    "prob": cfg_prob,
                    "threshold": cfg_thr,  # ⭐ FIXED: Use per-config threshold, not global
                }
            )

        # ⭐ Update voting roles periodically (every 10 iterations)
        if iteration % 10 == 0 and iteration >= 30:
            # Build config stats from scorer for voting system
            from wf_config_voting import build_config_stats_from_scorer

            config_stats_for_voting = build_config_stats_from_scorer(
                config_scorer, iteration, window=180
            )
            position_manager.update_voting_roles(config_stats_for_voting, iteration)

        # Calculate V3 position (0.0 to 2.0 range)
        meta_signal, meta_signal_meta = position_manager.calculate_position(
            prob_up=pred_dir_probs[0],  # Ensemble probability P(UP)
            threshold=optimal_threshold,  # Calibrated threshold
            config_predictions=config_predictions_v3,  # Top10 config predictions
            high_vol=high_vol,  # Volatility regime flag
            expected_return=pred_returns[0]
            if len(pred_returns) > 0
            else None,  # ⭐ For Alpha Gate
            risk_free_rate=risk_free_pred[0]
            if len(risk_free_pred) > 0
            else 0.0,  # ⭐ For Alpha Gate
            dual_ema_data=dual_ema_data,  # ⭐ LtEMA/StEMA/LtRSI/StRSI for gates and scales
            best_top10_ratio=best_top10_ratio,  # ⭐ Best ratio from Top10 for regime override
            verbose=(iteration <= 210),  # Debug first 210 iterations
        )

        # Also store V2 for comparison (can be removed later)
        market_regime_for_meta = {
            "high_vol_regime": high_vol,
            "uptrend_regime": int(current_pred_row.get("uptrend_regime", 1)),
            "hmm_regime": int(current_pred_row.get("hmm_regime", 1)),
        }
        meta_signal_v2, meta_signal_meta_v2 = calculate_position_v2(
            prob_up=pred_dir_probs[0],
            threshold=optimal_threshold,
            expected_return=pred_returns[0] if len(pred_returns) > 0 else 0.0,
            expected_volatility=pred_vol_preds[0] if len(pred_vol_preds) > 0 else 0.01,
            risk_free_rate=risk_free_pred[0] if len(risk_free_pred) > 0 else 0.0,
            dual_ema_data=dual_ema_data,
            past_ratio=past_ratio,
            market_regime=market_regime_for_meta,
            running_drawdown=0.0,
            verbose=False,  # Silence V2 for comparison only
        )

        # ⭐ Use meta_signal as the primary signal (replaces baseline)
        ensemble_signal = meta_signal
        ensemble_meta = meta_signal_meta

        # ⭐ Also run old method for comparison logging (can be removed later)
        old_ensemble_signal, old_ensemble_meta = (
            config_ensemble.calculate_ensemble_signal(
                config_probs_for_ensemble,
                iteration,
                precision_zone=current_precision_zone,
                net_signal=current_net_signal,
                market_ratio=current_market_ratio,
                verbose=False,
            )
        )

        # ⭐ Add ensemble signal info to iteration record
        walkforward_iterations[-1]["ensemble_signal"] = ensemble_signal
        walkforward_iterations[-1]["ensemble_probability"] = ensemble_meta.get(
            "probability", pred_dir_probs[0]
        )
        walkforward_iterations[-1]["ensemble_weighted_precision"] = ensemble_meta.get(
            "weighted_precision", 0.5
        )
        walkforward_iterations[-1]["ensemble_weighted_p_up"] = old_ensemble_meta.get(
            "weighted_p_up", 0.5
        )  # from old method
        walkforward_iterations[-1]["ensemble_agreement"] = old_ensemble_meta.get(
            "agreement", 0.0
        )  # from old method
        walkforward_iterations[-1]["ensemble_n_stable"] = old_ensemble_meta.get(
            "n_stable", 0
        )  # from old method
        walkforward_iterations[-1]["ensemble_precision_zone"] = current_precision_zone
        walkforward_iterations[-1]["ensemble_net_signal"] = current_net_signal
        walkforward_iterations[-1]["ensemble_market_ratio"] = current_market_ratio
        walkforward_iterations[-1]["ensemble_mkt_adjustment"] = old_ensemble_meta.get(
            "mkt_adjustment", 1.0
        )
        walkforward_iterations[-1]["ensemble_avg_config_ratio"] = old_ensemble_meta.get(
            "avg_config_ratio", 1.0
        )

        # ⭐ BASELINE POSITION SIZING LOGGING (with EMA scaling after ~194 iters)
        walkforward_iterations[-1]["baseline_signal"] = baseline_signal
        walkforward_iterations[-1]["baseline_status"] = baseline_meta.get(
            "status", "UNKNOWN"
        )
        walkforward_iterations[-1]["baseline_gate_failed"] = baseline_meta.get(
            "gate_failed", None
        )
        walkforward_iterations[-1]["baseline_alpha_excess"] = baseline_meta.get(
            "alpha_excess", 0.0
        )
        walkforward_iterations[-1]["baseline_ema_has_data"] = baseline_meta.get(
            "ema_has_data", False
        )
        walkforward_iterations[-1]["baseline_ema_bonus"] = baseline_meta.get(
            "ema_bonus", 0.0
        )
        walkforward_iterations[-1]["baseline_danger_penalty"] = baseline_meta.get(
            "danger_penalty", 0.0
        )
        walkforward_iterations[-1]["old_ensemble_signal"] = (
            old_ensemble_signal  # Compare with old method
        )

        # ⭐ META-MODEL POSITION SIZING V3 LOGGING (Rolling EMA + Alignment)
        walkforward_iterations[-1]["meta_signal"] = meta_signal
        walkforward_iterations[-1]["meta_gate"] = meta_signal_meta.get(
            "step1_gate", "N/A"
        )
        walkforward_iterations[-1]["meta_ratio_factor"] = meta_signal_meta.get(
            "step2_ratio_factor", 0.0
        )
        walkforward_iterations[-1]["meta_ratio_reason"] = meta_signal_meta.get(
            "step2_reason", "N/A"
        )  # NEW
        walkforward_iterations[-1]["meta_inverse_factor"] = meta_signal_meta.get(
            "step5b_inverse_factor", 1.0
        )  # NEW
        walkforward_iterations[-1]["meta_inverse_scale"] = meta_signal_meta.get(
            "step5b_inverse_scale", "N/A"
        )  # NEW
        walkforward_iterations[-1]["meta_alignment_factor"] = meta_signal_meta.get(
            "step3_alignment_factor", 1.0
        )
        walkforward_iterations[-1]["meta_vol_factor"] = meta_signal_meta.get(
            "step4_vol_factor", 1.0
        )
        walkforward_iterations[-1]["meta_vol_regime"] = meta_signal_meta.get(
            "step4_vol_regime", "NORMAL"
        )
        walkforward_iterations[-1]["meta_raw_position"] = meta_signal_meta.get(
            "step6_raw_position", 0.0
        )  # FIXED: was step5
        walkforward_iterations[-1]["meta_can_leverage"] = meta_signal_meta.get(
            "step6_can_leverage", False
        )  # FIXED
        walkforward_iterations[-1]["meta_max_position"] = meta_signal_meta.get(
            "step6_max_position", 1.0
        )  # FIXED
        # Extract nested ratio and alignment metadata
        ratio_meta = meta_signal_meta.get("ratio_meta", {})
        align_meta = meta_signal_meta.get("align_meta", {})
        walkforward_iterations[-1]["meta_rolling_ratio"] = ratio_meta.get(
            "combined_ratio", 0.0
        )
        walkforward_iterations[-1]["meta_rolling_tp"] = ratio_meta.get("tp", 0)
        walkforward_iterations[-1]["meta_rolling_fp"] = ratio_meta.get("fp", 0)
        walkforward_iterations[-1]["meta_alignment"] = align_meta.get("alignment", 0.5)
        walkforward_iterations[-1]["meta_alignment_votes_up"] = align_meta.get(
            "votes_up", 0
        )
        walkforward_iterations[-1]["meta_alignment_n_configs"] = align_meta.get(
            "n_configs", 0
        )
        walkforward_iterations[-1]["meta_signal_v2"] = (
            meta_signal_v2  # V2 for comparison
        )

        # ⭐ BENCHMARK SIGNAL LOGGING (gates-only, works from iteration 1)
        walkforward_iterations[-1]["benchmark_signal"] = benchmark_signal
        walkforward_iterations[-1]["benchmark_status"] = benchmark_meta.get(
            "status", "UNKNOWN"
        )
        walkforward_iterations[-1]["benchmark_gate_failed"] = benchmark_meta.get(
            "gate_failed", None
        )
        walkforward_iterations[-1]["benchmark_alpha_excess"] = benchmark_meta.get(
            "alpha_excess", 0.0
        )

        # ⭐ UPDATE HULL SCORERS - TWO SEPARATE SCORING APPROACHES
        # Run 1 (HullB): Cumulative from iteration 1 - full history
        # Run 2 (HullF): Rolling 180-day window - recent performance only
        # BOTH use ensemble_signal (the actual strategy signal)
        # ⚠️ DATA FLOW FOR HULL SCORE (no future leakage):
        # - lagged_ret_pred[0] = lagged_forward_returns at PRED day = YESTERDAY's return
        # - pending_hull_* = signal from YESTERDAY (stored in previous iteration)
        # - So we're evaluating: (yesterday's position) vs (yesterday's return) ✓
        market_ret_for_hull_lagged = (
            lagged_ret_pred[0] if len(lagged_ret_pred) > 0 else 0.0
        )
        rf_for_hull = risk_free_pred[0] if len(risk_free_pred) > 0 else 0.0

        # ⭐ HULL SCORER LAGGED EVALUATION (pending_hull_* initialized before main loop)
        # Evaluate YESTERDAY's position with today's lagged return
        # Both scorers start from iteration 1 (no start gate)
        if pending_hull_benchmark is not None:
            hull_scorer_benchmark.update(
                position=pending_hull_benchmark,
                market_return=market_ret_for_hull_lagged,
                risk_free_rate=rf_for_hull,
            )

        if pending_hull_baseline is not None:
            hull_scorer_baseline.update(
                position=pending_hull_baseline,
                market_return=market_ret_for_hull_lagged,
                risk_free_rate=rf_for_hull,
            )

        # Store TODAY's position for evaluation in NEXT iteration
        # ⭐ BOTH use ensemble_signal (= meta_signal)
        pending_hull_benchmark = ensemble_signal
        pending_hull_baseline = ensemble_signal

        # Calculate Hull scores
        # HullB: Cumulative (uses all history)
        # HullF: Rolling 180-day window
        hull_bench_score, hull_bench_meta = (
            hull_scorer_benchmark.calculate_score()
        )  # All history
        hull_base_score, hull_base_meta = hull_scorer_baseline.calculate_score(
            window=HULL_ROLLING_WINDOW
        )  # Rolling 180

        # Log both to iteration record
        walkforward_iterations[-1]["hull_bench_score"] = hull_bench_score
        walkforward_iterations[-1]["hull_bench_sharpe"] = hull_bench_meta.get(
            "sharpe", np.nan
        )
        walkforward_iterations[-1]["hull_base_score"] = hull_base_score
        walkforward_iterations[-1]["hull_base_sharpe"] = hull_base_meta.get(
            "sharpe", np.nan
        )
        # Legacy compatibility
        walkforward_iterations[-1]["hull_score"] = hull_base_score
        walkforward_iterations[-1]["hull_sharpe"] = hull_base_meta.get("sharpe", np.nan)
        walkforward_iterations[-1]["hull_vol_penalty"] = hull_base_meta.get(
            "vol_penalty", np.nan
        )
        walkforward_iterations[-1]["hull_return_penalty"] = hull_base_meta.get(
            "return_penalty", np.nan
        )

        # ⭐ EXTENDED HULL ANALYSIS FIELDS (for post-run optimization)
        walkforward_iterations[-1]["hull_strategy_vol"] = hull_base_meta.get(
            "strategy_vol", np.nan
        )
        walkforward_iterations[-1]["hull_market_vol"] = hull_base_meta.get(
            "market_vol", np.nan
        )
        walkforward_iterations[-1]["hull_vol_ratio"] = hull_base_meta.get(
            "vol_ratio", np.nan
        )
        walkforward_iterations[-1]["hull_strategy_excess"] = hull_base_meta.get(
            "strategy_mean_excess", np.nan
        )
        walkforward_iterations[-1]["hull_market_excess"] = hull_base_meta.get(
            "market_mean_excess", np.nan
        )
        walkforward_iterations[-1]["hull_return_gap_pct"] = hull_base_meta.get(
            "return_gap_pct", np.nan
        )
        walkforward_iterations[-1]["hull_avg_position"] = hull_base_meta.get(
            "avg_position", np.nan
        )
        walkforward_iterations[-1]["hull_position_std"] = hull_base_meta.get(
            "position_std", np.nan
        )
        walkforward_iterations[-1]["hull_n_samples"] = hull_base_meta.get(
            "n_samples", 0
        )

        # ⭐ POSITION SIZING COMPONENT LOGGING (for optimization)
        walkforward_iterations[-1]["pos_drawdown_scale"] = meta_signal_meta.get(
            "drawdown_scale", 1.0
        )
        walkforward_iterations[-1]["pos_voting_scale"] = meta_signal_meta.get(
            "voting_scale", 1.0
        )
        walkforward_iterations[-1]["pos_ema_crossover_factor"] = meta_signal_meta.get(
            "step3a_ema_crossover_factor", 1.0
        )
        walkforward_iterations[-1]["pos_ema_quartile_factor"] = meta_signal_meta.get(
            "step3b_ema_quartile_factor", 1.0
        )
        walkforward_iterations[-1]["pos_current_drawdown"] = meta_signal_meta.get(
            "current_drawdown", 0.0
        )
        walkforward_iterations[-1]["pos_current_equity"] = meta_signal_meta.get(
            "equity", 1.0
        )
        walkforward_iterations[-1]["pos_gatekeeper_veto"] = meta_signal_meta.get(
            "gatekeeper_veto", False
        )

        # ⭐ EMA DATA LOGGING (for analysis)
        if dual_ema_data and dual_ema_data.get("has_data", False):
            walkforward_iterations[-1]["ema_lt_ema"] = dual_ema_data.get(
                "long_term_ema", np.nan
            )
            walkforward_iterations[-1]["ema_st_ema"] = dual_ema_data.get(
                "short_term_ema", np.nan
            )
            walkforward_iterations[-1]["ema_lt_rsi"] = dual_ema_data.get(
                "long_term_rsi", np.nan
            )
            walkforward_iterations[-1]["ema_st_rsi"] = dual_ema_data.get(
                "short_term_rsi", np.nan
            )
            walkforward_iterations[-1]["ema_has_data"] = True
        else:
            walkforward_iterations[-1]["ema_lt_ema"] = np.nan
            walkforward_iterations[-1]["ema_st_ema"] = np.nan
            walkforward_iterations[-1]["ema_lt_rsi"] = np.nan
            walkforward_iterations[-1]["ema_st_rsi"] = np.nan
            walkforward_iterations[-1]["ema_has_data"] = False

        # ⭐ MARKET & STRATEGY RETURNS (actual, for Hull optimization)
        lagged_market_ret = lagged_ret_pred[0] if len(lagged_ret_pred) > 0 else np.nan
        walkforward_iterations[-1]["lagged_market_return"] = lagged_market_ret
        walkforward_iterations[-1]["lagged_strategy_return"] = (
            lagged_market_ret * pending_hull_benchmark
            if pending_hull_benchmark is not None
            else np.nan
        )
        walkforward_iterations[-1]["risk_free_rate"] = rf_for_hull

        # ════════════════════════════════════════════════════════════════════
        # ⭐ BENCHMARK vs BASELINE TRACKER UPDATES
        # Uses y_pred_dir_arr[0] as actual outcome (1=UP, 0=DOWN)
        # ════════════════════════════════════════════════════════════════════
        actual_up = int(y_pred_dir_arr[0])  # 1 if market went UP, 0 if DOWN

        # --- BENCHMARK TRACKER (gates-only, signal is 0 or 1) ---
        bench_signaled = benchmark_signal > 0  # True if gates passed (signal=1.0)
        if bench_signaled:
            benchmark_tracker["signals"] += 1
            if actual_up == 1:
                benchmark_tracker["tp"] += 1
                benchmark_tracker["rolling_results"].append("TP")
            else:
                benchmark_tracker["fp"] += 1
                benchmark_tracker["rolling_results"].append("FP")
        else:
            benchmark_tracker["no_signals"] += 1
            if actual_up == 0:
                benchmark_tracker["tn"] += 1
                benchmark_tracker["rolling_results"].append("TN")
            else:
                benchmark_tracker["fn"] += 1
                benchmark_tracker["rolling_results"].append("FN")

        # --- BASELINE TRACKER (gates + EMA, signal is 0.0-2.0) ---
        base_signaled = baseline_signal > 0  # True if gates passed (signal>0)
        base_has_ema = baseline_meta.get("ema_has_data", False)
        if base_signaled:
            baseline_tracker["signals"] += 1
            if base_has_ema:
                baseline_tracker["full_signals"] += 1
            else:
                baseline_tracker["warmup_signals"] += 1
            if actual_up == 1:
                baseline_tracker["tp"] += 1
                baseline_tracker["rolling_results"].append("TP")
            else:
                baseline_tracker["fp"] += 1
                baseline_tracker["rolling_results"].append("FP")
        else:
            baseline_tracker["no_signals"] += 1
            if actual_up == 0:
                baseline_tracker["tn"] += 1
                baseline_tracker["rolling_results"].append("TN")
            else:
                baseline_tracker["fn"] += 1
                baseline_tracker["rolling_results"].append("FN")

        # Log tracker metrics to iteration record
        bench_total = (
            benchmark_tracker["tp"]
            + benchmark_tracker["fp"]
            + benchmark_tracker["tn"]
            + benchmark_tracker["fn"]
        )
        bench_correct = benchmark_tracker["tp"] + benchmark_tracker["tn"]
        bench_acc = bench_correct / bench_total if bench_total > 0 else 0.0
        bench_precision = (
            benchmark_tracker["tp"]
            / (benchmark_tracker["tp"] + benchmark_tracker["fp"])
            if (benchmark_tracker["tp"] + benchmark_tracker["fp"]) > 0
            else 0.0
        )

        base_total = (
            baseline_tracker["tp"]
            + baseline_tracker["fp"]
            + baseline_tracker["tn"]
            + baseline_tracker["fn"]
        )
        base_correct = baseline_tracker["tp"] + baseline_tracker["tn"]
        base_acc = base_correct / base_total if base_total > 0 else 0.0
        base_precision = (
            baseline_tracker["tp"] / (baseline_tracker["tp"] + baseline_tracker["fp"])
            if (baseline_tracker["tp"] + baseline_tracker["fp"]) > 0
            else 0.0
        )

        walkforward_iterations[-1]["benchmark_tp"] = benchmark_tracker["tp"]
        walkforward_iterations[-1]["benchmark_fp"] = benchmark_tracker["fp"]
        walkforward_iterations[-1]["benchmark_tn"] = benchmark_tracker["tn"]
        walkforward_iterations[-1]["benchmark_fn"] = benchmark_tracker["fn"]
        walkforward_iterations[-1]["benchmark_accuracy"] = bench_acc
        walkforward_iterations[-1]["benchmark_precision"] = bench_precision
        walkforward_iterations[-1]["benchmark_signals"] = benchmark_tracker["signals"]

        walkforward_iterations[-1]["baseline_tp"] = baseline_tracker["tp"]
        walkforward_iterations[-1]["baseline_fp"] = baseline_tracker["fp"]
        walkforward_iterations[-1]["baseline_tn"] = baseline_tracker["tn"]
        walkforward_iterations[-1]["baseline_fn"] = baseline_tracker["fn"]
        walkforward_iterations[-1]["baseline_accuracy"] = base_acc
        walkforward_iterations[-1]["baseline_precision"] = base_precision
        walkforward_iterations[-1]["baseline_signals"] = baseline_tracker["signals"]
        walkforward_iterations[-1]["baseline_warmup_signals"] = baseline_tracker[
            "warmup_signals"
        ]
        walkforward_iterations[-1]["baseline_full_signals"] = baseline_tracker[
            "full_signals"
        ]
    elif MULTI_CONFIG_TRACKING and not has_pred_target:
        # ⭐ PRODUCTION MODE: MULTI_CONFIG_TRACKING on but no target available (live prediction)
        # Still calculate signals but skip evaluation/tracking
        ensemble_signal = 1.0  # Default to full position
        ensemble_meta = {"status": "NO_TARGET_FOR_EVALUATION"}
        hull_bench_score = np.nan
        hull_base_score = np.nan
        current_market_ratio = 1.0
        dual_ema_data = {"has_data": False}
        benchmark_signal = 0.0
        benchmark_meta = {}
        baseline_signal = 0.0
        baseline_meta = {}
        selected_config_name = None
        config_probs_for_ensemble = {}
    else:
        # Default signal when multi-config tracking disabled
        ensemble_signal = 1.0
        ensemble_meta = {"status": "MULTI_CONFIG_DISABLED"}
        hull_bench_score = np.nan
        hull_base_score = np.nan
        current_market_ratio = 1.0  # For logging consistency
        dual_ema_data = {"has_data": False}  # No EMA data when tracking disabled
        benchmark_signal = 0.0
        benchmark_meta = {}
        baseline_signal = 0.0
        baseline_meta = {}
        selected_config_name = None  # ⭐ Ensure defined for pending prediction
        config_probs_for_ensemble = {}  # ⭐ Ensure defined for pending prediction

    # ─────────────────────────────────────────────────────────────────
    # STEP 12: PRINT PROGRESS
    # ─────────────────────────────────────────────────────────────────
    pred_class = 1 if pred_dir_probs[0] >= optimal_threshold else 0
    actual_class = (
        int(y_pred_dir_arr[0]) if has_pred_target else np.nan
    )  # ⭐ PRODUCTION-SAFE

    # ⭐ Show prediction type: TP, TN, FP, FN (only if we have target)
    if has_pred_target:
        if pred_class == 1 and actual_class == 1:
            pred_type = "TP"  # True Positive
        elif pred_class == 0 and actual_class == 0:
            pred_type = "TN"  # True Negative
        elif pred_class == 1 and actual_class == 0:
            pred_type = "FP"  # False Positive
        else:
            pred_type = "FN"  # False Negative
    else:
        pred_type = "??"  # Unknown - no target in production

    # ⭐ Update Position Sizing Manager V3 with result (only when we have valid target)
    if has_pred_target and pred_type in ("TP", "TN", "FP", "FN"):
        position_manager.update_result(pred_type)

    # ⭐ Update equity tracking for drawdown protection
    # Get actual market return for this period
    actual_market_return = (
        y_pred_ret[0] if y_pred_ret is not None and len(y_pred_ret) > 0 else 0.0
    )
    # ensemble_signal is the position size (0.0 to 2.0) that was used this iteration
    position_manager.update_equity(
        market_return=actual_market_return,
        position=ensemble_signal,
        verbose=(iteration <= 210),
    )

    # ⭐ Update market buy & hold equity (position=1.0 always)
    market_equity *= 1.0 + actual_market_return

    # ⭐ Track rolling TP/FP ratio over last 180 predictions (only when we have valid target)
    if has_pred_target and pred_type in ("TP", "TN", "FP", "FN"):
        rolling_pred_types.append(pred_type)
    rolling_tp = sum(1 for pt in rolling_pred_types if pt == "TP")
    rolling_fp = sum(1 for pt in rolling_pred_types if pt == "FP")
    if rolling_fp > 0:
        rolling_ratio = rolling_tp / rolling_fp
        ratio_str = f"{rolling_ratio:.2f}"
    elif rolling_tp > 0:
        rolling_ratio = 5.0  # Cap at 5.0 for display
        ratio_str = "∞"
    else:
        rolling_ratio = 1.0  # Neutral
        ratio_str = "-"

    # ⭐ RECORD this iteration's ratio for NEXT iteration's EMA calculation
    # We DON'T update dual_ema_data here - it was already calculated at start of iteration
    # using ONLY past data (before we knew this iteration's outcome)
    if rolling_tp + rolling_fp >= 5:  # Need some samples
        config_scorer.actual_ratio_history.append((iteration, rolling_ratio))

    # ⭐ Track rolling market baseline (actual UP/DOWN ratio) - only when we have valid target
    if has_pred_target and not np.isnan(actual_class):
        rolling_actuals.append(int(actual_class))

    # ⭐ Track rolling returns for Mkt% and Ret% (same window as TP/FP)
    rolling_market_returns.append(actual_market_return)
    # Strategy return for this iteration = position × market_return (simplified, ignoring rf)
    strategy_return_this_iter = (
        ensemble_signal * actual_market_return if ensemble_signal is not None else 0.0
    )
    rolling_strategy_returns.append(strategy_return_this_iter)

    # ⭐ LOG ACTUAL RETURNS FOR HULL OPTIMIZATION
    walkforward_iterations[-1]["actual_market_return"] = actual_market_return
    walkforward_iterations[-1]["actual_strategy_return"] = strategy_return_this_iter
    walkforward_iterations[-1]["position_used"] = ensemble_signal
    walkforward_iterations[-1]["cumulative_market_return"] = sum(rolling_market_returns)
    walkforward_iterations[-1]["cumulative_strategy_return"] = sum(
        rolling_strategy_returns
    )
    walkforward_iterations[-1]["market_equity"] = market_equity
    walkforward_iterations[-1]["strategy_equity"] = (
        position_manager.equity_tracker.equity
        if hasattr(position_manager, "equity_tracker")
        else 1.0
    )

    # Market ratio for display
    if len(rolling_actuals) > 0:
        rolling_up = sum(rolling_actuals)
        rolling_down = len(rolling_actuals) - rolling_up
        if rolling_down > 0:
            market_ratio = rolling_up / rolling_down
            mkt_str = f"{market_ratio:.2f}"
        elif rolling_up > 0:
            mkt_str = "∞"
        else:
            mkt_str = "-"
    else:
        mkt_str = "-"

    # Gate indicator - fixed width
    gate_str = f"⚡{gate_triggered[0]}" if gate_triggered else "--"

    # Format iteration progress - fixed width 7 chars
    iter_str = f"{iteration}/{n_expected_iterations}"

    # Format window ranges - each exactly 12 chars
    train_range = f"[{train_start:4},{train_end:4})"
    cal_range = f"[{cal_start:4},{cal_end:4})"
    val_range = f"[{val_start:4},{val_end:4})"
    pred_range = f"[{pred_start:4},{pred_end:4})"

    # ⭐ Selected config name (truncate to 20 chars for display)
    cfg_display = selected_config_name[:20] if selected_config_name else "none"

    # ⭐ Ensemble signal display
    sig_str = f"{ensemble_signal:.2f}" if ensemble_signal is not None else "-"

    # ⭐ Hull scores display (TWO: benchmark + baseline)
    if MULTI_CONFIG_TRACKING and not np.isnan(hull_bench_score):
        hull_b_str = f"{hull_bench_score:.2f}"
    else:
        hull_b_str = "-"
    if MULTI_CONFIG_TRACKING and not np.isnan(hull_base_score):
        hull_f_str = f"{hull_base_score:.2f}"
    else:
        hull_f_str = "-"

    # ⭐ Dual EMA and RSI display - show as soon as ANY value available (no gating)
    # This shows expanding window values for all rolling periods
    if MULTI_CONFIG_TRACKING and dual_ema_data.get("long_term_ema", 0) > 0:
        lt_ema_str = f"{dual_ema_data['long_term_ema']:.2f}"
        st_ema_str = f"{dual_ema_data['short_term_ema']:.2f}"
        lt_rsi_str = f"{dual_ema_data.get('long_term_rsi', 50):.0f}"
        st_rsi_str = f"{dual_ema_data.get('short_term_rsi', 50):.0f}"
    else:
        lt_ema_str = "-"
        st_ema_str = "-"
        lt_rsi_str = "-"
        st_rsi_str = "-"

    # ⭐ Rolling return % (same window as TP/FP ratio = ROLLING_WINDOW_SIZE)
    # Geometric compounding over rolling window for Mkt% and Ret%
    if len(rolling_market_returns) > 0:
        rolling_mkt_equity = 1.0
        for r in rolling_market_returns:
            rolling_mkt_equity *= 1.0 + r
        rolling_mkt_pct = (rolling_mkt_equity - 1.0) * 100
        mkt_ret_str = f"{rolling_mkt_pct:+.1f}%"
    else:
        mkt_ret_str = "-"

    if len(rolling_strategy_returns) > 0:
        rolling_strat_equity = 1.0
        for r in rolling_strategy_returns:
            rolling_strat_equity *= 1.0 + r
        rolling_strat_pct = (rolling_strat_equity - 1.0) * 100
        ret_str = f"{rolling_strat_pct:+.1f}%"
    else:
        ret_str = "-"

    # Print row with fixed-width columns matching header
    print(
        f"{iter_str:<7} {train_range:^12} {cal_range:^12} {val_range:^12} {pred_range:^12} {cb_val_auc:5.2f} {lgb_val_auc:5.2f} {cfg_display:<20} {pred_dir_probs[0]:5.2f} {optimal_threshold:5.2f} {pred_class:2} {actual_class:2} {pred_type:>3} {rolling_tp:4} {rolling_fp:4} {ratio_str:>6} {mkt_str:>6} {sig_str:>5} {hull_b_str:>6} {hull_f_str:>6} {lt_ema_str:>6} {st_ema_str:>6} {lt_rsi_str:>5} {st_rsi_str:>5} {iter_elapsed:4.1f}s {mkt_ret_str:>7} {ret_str:>7}"
    )

    # ⭐ Print rolling top configs (compact, every iteration)
    # Uses N_TOP_CONFIGS but shows min(10, N_TOP_CONFIGS) for display
    if MULTI_CONFIG_TRACKING and iteration >= 10:
        n_display = min(10, N_TOP_CONFIGS)
        top_cfgs = config_scorer.get_top_configs(iteration, n=n_display)
        top_strs = []
        for cfg_data in top_cfgs[:5]:  # Show first 5 in compact format
            name_short = cfg_data["name"][:12]  # Truncate name
            ratio = cfg_data["ratio"]
            ratio_s = f"{ratio:.1f}" if ratio < 100 else "∞"
            top_strs.append(
                f"{name_short}({cfg_data['tp']}/{cfg_data['fp']}={ratio_s})"
            )
        print(f"    Top{n_display}: {' | '.join(top_strs)}")

    # ════════════════════════════════════════════════════════════════════════
    # ⭐ MULTI-CONFIG PROGRESS SUMMARY (every 50 iterations or at key points)
    # ════════════════════════════════════════════════════════════════════════
    if MULTI_CONFIG_TRACKING and (iteration % 50 == 0 or iteration == 10):
        print(f"\n    {'─' * 100}")
        print(
            f"    📊 MULTI-CONFIG SNAPSHOT @ iter {iteration} | Selected: {selected_config_name} | Switches: {len(config_scorer.switch_history)}"
        )

        # Show BASELINE signal info
        baseline_status = baseline_meta.get("status", "UNKNOWN")
        ema_has_data = baseline_meta.get("ema_has_data", False)

        if baseline_status == "SIGNAL_GENERATED":
            # Full signal with EMA scaling active
            ema_bonus = baseline_meta.get("ema_bonus", 0.0)
            danger_pen = baseline_meta.get("danger_penalty", 0.0)
            alpha_ex = baseline_meta.get("alpha_excess", 0.0)
            print(
                f"    📈 BASELINE Signal: {baseline_signal:.2f} | P(UP): {pred_dir_probs[0]:.1%} >= Thr: {optimal_threshold:.1%} | "
                f"Alpha Excess: {alpha_ex:.5f} | EMA Bonus: {ema_bonus:+.2f} | Danger: {danger_pen:+.2f}"
            )
        elif baseline_status == "SIGNAL_WARMUP":
            # Gates passed but no EMA data yet
            alpha_ex = baseline_meta.get("alpha_excess", 0.0)
            print(
                f"    📈 BASELINE Signal: {baseline_signal:.2f} [WARMUP - EMA not ready, need ~194+ iters] | "
                f"P(UP): {pred_dir_probs[0]:.1%} >= Thr: {optimal_threshold:.1%} | Alpha Excess: {alpha_ex:.5f}"
            )
        else:
            # Gate failed
            gate_failed = baseline_meta.get("gate_failed", "unknown")
            print(
                f"    📈 BASELINE: {baseline_status} (gate: {gate_failed}) → Signal: {baseline_signal:.2f}"
            )

        # Show OLD ensemble for comparison
        if old_ensemble_meta.get("status") == "OK":
            print(
                f"    📊 OLD Ensemble: {old_ensemble_signal:.2f} | P(UP): {old_ensemble_meta.get('weighted_p_up', 0.5):.1%} | "
                f"Agreement: {old_ensemble_meta.get('agreement', 0):.2f} | Using {old_ensemble_meta.get('n_stable', 0)} configs"
            )

        position = config_ensemble.get_position_recommendation(ensemble_signal)
        print(f"    📍 Position: {position}")

        # Show Hull score info (both benchmark and baseline)
        if not np.isnan(hull_bench_score):
            print(
                f"    🎯 Hull Benchmark: {hull_bench_score:.3f} | Hull Baseline: {hull_base_score:.3f}"
            )
            print(
                f"       Sharpe(B): {hull_bench_meta.get('sharpe', 0):.3f} | Sharpe(F): {hull_base_meta.get('sharpe', 0):.3f} | "
                f"Avg Pos(B): {hull_bench_meta.get('avg_position', 1):.2f} | Avg Pos(F): {hull_base_meta.get('avg_position', 1):.2f}"
            )
        else:
            print(
                f"    🎯 Hull Score: building... ({len(hull_scorer_baseline.history)}/{hull_scorer_baseline.min_samples} samples)"
            )

        print(f"    {'─' * 100}")

        # Calculate current metrics for top configs
        snapshot_metrics = []
        for cfg_name, results in config_results.items():
            n = results["total_predictions"]
            if n == 0:
                continue
            tp = results["rolling_tp"]
            fp = results["rolling_fp"]
            tn = results["rolling_tn"]
            fn = results["rolling_fn"]
            acc = results["total_correct"] / n
            prec = tp / (tp + fp) if (tp + fp) > 0 else 0
            ratio = tp / fp if fp > 0 else float("inf") if tp > 0 else 0

            # Get momentum from scorer
            score_data = config_scorer.get_composite_score(cfg_name, iteration)
            mom_signal = score_data.get("momentum_signal", "UNK")[:4]

            snapshot_metrics.append(
                {
                    "name": cfg_name,
                    "acc": acc,
                    "prec": prec,
                    "tp": tp,
                    "fp": fp,
                    "ratio": ratio,
                    "mom": mom_signal,
                    "score": score_data.get("final_score", 0),
                }
            )

        # Sort by TP/FP ratio and show top 5
        snapshot_metrics.sort(
            key=lambda x: x["ratio"] if x["ratio"] != float("inf") else 999,
            reverse=True,
        )

        print(
            f"    {'Config':<40} {'Acc':>6} {'Prec':>6} {'TP':>4} {'FP':>4} {'Ratio':>7} {'Mom':>5} {'Score':>6}"
        )
        for m in snapshot_metrics[:5]:
            ratio_s = f"{m['ratio']:.2f}" if m["ratio"] != float("inf") else "∞"
            print(
                f"    {m['name']:<40} {m['acc']:5.1%} {m['prec']:5.1%} {m['tp']:4} {m['fp']:4} {ratio_s:>7} {m['mom']:>5} {m['score']:6.2f}"
            )

        # Also show worst 2 for comparison
        if len(snapshot_metrics) > 5:
            print(f"    {'... (worst 2):':<40}")
            for m in snapshot_metrics[-2:]:
                ratio_s = f"{m['ratio']:.2f}" if m["ratio"] != float("inf") else "∞"
                print(
                    f"    {m['name']:<40} {m['acc']:5.1%} {m['prec']:5.1%} {m['tp']:4} {m['fp']:4} {ratio_s:>7} {m['mom']:>5} {m['score']:6.2f}"
                )

        print(f"    {'─' * 100}\n")

        # Reprint header for easier reading
        print(
            f"{'Iter':<7} {'TRAIN':^12} {'CAL':^12} {'VAL':^12} {'PRED':^12} {'CB':>5} {'LG':>5} {'Config':<20} {'Prob':>5} {'Thr':>5} {'P':>2} {'A':>2} {'Res':>3} {'TP':>4} {'FP':>4} {'Ratio':>6} {'Mkt':>6} {'Sig':>5} {'HullB':>6} {'HullF':>6} {'LtEMA':>6} {'StEMA':>6} {'LtRSI':>5} {'StRSI':>5} {'Time':>5} {'Mkt%':>7} {'Ret%':>7}"
        )
        print("-" * 215)

    # ─────────────────────────────────────────────────────────────────
    # ⭐ STORE PENDING PREDICTION (for lagged evaluation in next iteration)
    # ─────────────────────────────────────────────────────────────────
    # In LIVE_MODE, we can't evaluate immediately (no target), so we store
    # the prediction for evaluation when lagged_direction_target arrives
    if LIVE_MODE:
        pending_prediction = PendingPrediction(
            pred_class=pred_class,
            pred_prob=float(pred_dir_probs[0]),
            threshold=float(optimal_threshold),
            signal=float(ensemble_signal) if ensemble_signal is not None else 1.0,
            config_name=selected_config_name if selected_config_name else "unknown",
            iteration=iteration,
            timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
            config_predictions=config_probs_for_ensemble
            if MULTI_CONFIG_TRACKING
            else {},
        )

    # Cleanup and advance
    del volatility_model
    gc.collect()
    pred_start = pred_end

print("-" * 185)
print(
    f"TOTAL: {iteration} iterations | Switches: {len(config_scorer.switch_history)} | Final Config: {config_scorer.current_config}"
)
print()

# ════════════════════════════════════════════════════════════════════════════
# ⭐ PRODUCTION MODE: Save checkpoint for live predictions
# ════════════════════════════════════════════════════════════════════════════
if PRODUCTION_MODE and PRODUCTION_AUTO_SAVE:
    try:
        from old.warmup_backup.wf_warmup import WarmupCheckpoint, save_checkpoint

        # Build production checkpoint with all state
        production_checkpoint = WarmupCheckpoint(
            iteration=iteration,
            pred_start=pred_start,
            catboost_params=CATBOOST_DIR_PARAMS,
            lightgbm_params=LIGHTGBM_DIR_PARAMS,
            histgb_params=HISTGB_DIR_PARAMS if "HISTGB_DIR_PARAMS" in dir() else {},
            cb_cal_buffer_data=[],  # Not needed for resume
            lgb_cal_buffer_data=[],
            meta_buffer_data=[],
            cb_calibrator=cb_calibrator,
            lgb_calibrator=lgb_calibrator,
            meta_stacker=meta_stacker,
            config_scorer_state=config_scorer.get_state()
            if hasattr(config_scorer, "get_state")
            else {},
            config_results={
                k: {kk: vv for kk, vv in v.items() if kk != "rolling_pred_types"}
                for k, v in config_results.items()
            },
            hull_benchmark_history=hull_scorer_benchmark.history.copy()
            if hasattr(hull_scorer_benchmark, "history")
            else [],
            hull_baseline_history=hull_scorer_baseline.history.copy()
            if hasattr(hull_scorer_baseline, "history")
            else [],
            benchmark_tracker={
                k: v if not isinstance(v, deque) else list(v)
                for k, v in benchmark_tracker.items()
            },
            baseline_tracker={
                k: v if not isinstance(v, deque) else list(v)
                for k, v in baseline_tracker.items()
            },
            rolling_pred_types=list(rolling_pred_types),
            rolling_actuals=list(rolling_actuals),
            rolling_market_returns=list(rolling_market_returns),
            rolling_strategy_returns=list(rolling_strategy_returns),
            warmup_predictions=walkforward_predictions,
            warmup_iterations=walkforward_iterations,
            aggregated_feature_cols=aggregated_feature_cols
            if "aggregated_feature_cols" in dir()
            else [],
            selected_features=[],  # Will be recomputed
            diagnostics=DIAGNOSTICS if DIAGNOSTICS else {},
            drift_alerts=drift_alerts,
            calibration_diagnostics=calibration_diagnostics,
            model_diversity_metrics=model_diversity_metrics,
            # ⭐ LIVE MODE: Pending prediction for lagged evaluation
            pending_prediction=pending_prediction.__dict__
            if pending_prediction
            else None,
            warmup_time_seconds=0.0,  # Not tracked in production mode
            created_at=time.strftime("%Y-%m-%d %H:%M:%S"),
        )

        save_checkpoint(production_checkpoint, DEPLOY_CHECKPOINT_PATH)

        print(f"\n{'=' * 80}")
        print("⭐ WARMUP CHECKPOINT SAVED")
        print(f"{'=' * 80}")
        print(f"  Output: {DEPLOY_CHECKPOINT_PATH}")
        print(f"  Iterations warmed: {iteration}")
        print(f"  TP/FP: {benchmark_tracker['tp']}/{benchmark_tracker['fp']}")
        print(f"  Rolling buffers: {len(rolling_pred_types)}/180 filled")
        print("")
        print("  📋 Ready for live predictions!")
        print("     Next run: Set DEPLOY_MODE='live' or 'auto'")
        print(f"{'=' * 80}\n")

    except Exception as e:
        print(f"\n  ⚠️ Failed to save checkpoint: {e}")
        import traceback

        traceback.print_exc()

# ════════════════════════════════════════════════════════════════════════════
# ⭐ LIVE MODE: Save updated checkpoint after prediction
# ════════════════════════════════════════════════════════════════════════════
if LIVE_MODE:
    try:
        from old.warmup_backup.wf_warmup import WarmupCheckpoint, save_checkpoint

        # Build updated checkpoint with new state
        live_checkpoint = WarmupCheckpoint(
            iteration=iteration,
            pred_start=pred_start,
            catboost_params=CATBOOST_DIR_PARAMS,
            lightgbm_params=LIGHTGBM_DIR_PARAMS,
            histgb_params=HISTGB_DIR_PARAMS if "HISTGB_DIR_PARAMS" in dir() else {},
            cb_cal_buffer_data=[],
            lgb_cal_buffer_data=[],
            meta_buffer_data=[],
            cb_calibrator=cb_calibrator,
            lgb_calibrator=lgb_calibrator,
            meta_stacker=meta_stacker,
            config_scorer_state=config_scorer.get_state()
            if hasattr(config_scorer, "get_state")
            else {},
            config_results={
                k: {kk: vv for kk, vv in v.items() if kk != "rolling_pred_types"}
                for k, v in config_results.items()
            },
            hull_benchmark_history=hull_scorer_benchmark.history.copy()
            if hasattr(hull_scorer_benchmark, "history")
            else [],
            hull_baseline_history=hull_scorer_baseline.history.copy()
            if hasattr(hull_scorer_baseline, "history")
            else [],
            benchmark_tracker={
                k: v if not isinstance(v, deque) else list(v)
                for k, v in benchmark_tracker.items()
            },
            baseline_tracker={
                k: v if not isinstance(v, deque) else list(v)
                for k, v in baseline_tracker.items()
            },
            rolling_pred_types=list(rolling_pred_types),
            rolling_actuals=list(rolling_actuals),
            rolling_market_returns=list(rolling_market_returns),
            rolling_strategy_returns=list(rolling_strategy_returns),
            warmup_predictions=walkforward_predictions,
            warmup_iterations=walkforward_iterations,
            aggregated_feature_cols=aggregated_feature_cols
            if "aggregated_feature_cols" in dir()
            else [],
            selected_features=[],
            diagnostics=DIAGNOSTICS if DIAGNOSTICS else {},
            drift_alerts=drift_alerts,
            calibration_diagnostics=calibration_diagnostics,
            model_diversity_metrics=model_diversity_metrics,
            pending_prediction=pending_prediction.__dict__
            if pending_prediction
            else None,
            warmup_time_seconds=0.0,
            created_at=time.strftime("%Y-%m-%d %H:%M:%S"),
        )

        save_checkpoint(live_checkpoint, DEPLOY_CHECKPOINT_PATH)

        # Output live prediction result
        print(f"\n{'=' * 80}")
        print("⭐ LIVE PREDICTION COMPLETE")
        print(f"{'=' * 80}")
        print(f"  Prediction: {'LONG' if pred_class == 1 else 'STAY OUT'}")
        print(f"  Probability: {pred_dir_probs[0]:.1%}")
        print(f"  Threshold:   {optimal_threshold:.1%}")
        print(f"  Signal:      {ensemble_signal:.2f}")
        print(f"  Config:      {selected_config_name}")
        print("")
        print(f"  📋 Checkpoint updated: {DEPLOY_CHECKPOINT_PATH}")
        print("     Pending prediction stored for lagged evaluation")
        print(f"{'=' * 80}\n")

    except Exception as e:
        print(f"\n  ⚠️ Failed to save live checkpoint: {e}")
        import traceback

        traceback.print_exc()

# ════════════════════════════════════════════════════════════════════════════
# ANALYSIS & REPORTING (moved to wf_analysis.py)
# ════════════════════════════════════════════════════════════════════════════
from wf_analysis import run_all_analysis

walkforward_prediction_df = pd.DataFrame(walkforward_predictions)
walkforward_iteration_df = pd.DataFrame(walkforward_iterations)

run_all_analysis(
    config_results=config_results,
    config_scorer=config_scorer,
    MULTI_CONFIG_TRACKING=MULTI_CONFIG_TRACKING,
    walkforward_prediction_df=walkforward_prediction_df,
    walkforward_iteration_df=walkforward_iteration_df,
    iteration=iteration,
    WF_TRAIN=WF_TRAIN,
    WF_VAL=WF_VAL,
    WF_CAL=WF_CAL,
    USE_AUTOMATIC_WINDOWS=USE_AUTOMATIC_WINDOWS,
    DIAGNOSTICS=DIAGNOSTICS,
    drift_alerts=drift_alerts,
    hull_scorer_benchmark=hull_scorer_benchmark,
    hull_scorer_baseline=hull_scorer_baseline,
    USE_SIGNAL_AGGREGATION=USE_SIGNAL_AGGREGATION,
    aggregated_feature_cols=aggregated_feature_cols
    if "aggregated_feature_cols" in dir()
    else [],
    calibration_diagnostics=calibration_diagnostics,
    model_diversity_metrics=model_diversity_metrics,
    benchmark_tracker=benchmark_tracker,
    baseline_tracker=baseline_tracker,
)
# %%
