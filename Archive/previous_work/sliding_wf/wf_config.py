# ============================================================================
# WF_CONFIG.PY - Walk-Forward Configuration Constants
# ============================================================================
# All configuration constants, feature groups, and hyperparameters
# ============================================================================

import os
import re
import numpy as np

# ============================================================================
# SIGNAL AGGREGATION CONFIGURATION
# ============================================================================
USE_SIGNAL_AGGREGATION = True

# ============================================================================
# AUTOMATIC WINDOW ESTIMATION TOGGLE
# ============================================================================
USE_AUTOMATIC_WINDOWS = False  # Disabled for fast warmup

# ============================================================================
# WINDOW SIZE MINIMUMS (per statistical requirements)
# ============================================================================
MIN_VAL_WINDOW = 150
MIN_CAL_WINDOW = 100

# Manual fallback values
MANUAL_WF_TRAIN = 1000
MANUAL_WF_VAL = 200
MANUAL_WF_CAL = 150

# ============================================================================
# FEATURE SELECTION CONFIGURATION
# ============================================================================
FEATURE_SELECTION_PERCENT = 40  # Keep top 40% (remove 60%) - aggressive
FEATURE_IMPORTANCE_TYPE = 'PredictionValuesChange'

# Two-phase feature selection with PACF
USE_TWO_PHASE_FEATURE_SELECTION = True
FEATURE_SELECTION_PHASE2_PERCENT = 60  # Keep 60% in phase 2 (remove 40%)
USE_PACF_LAG_SELECTION = True
PACF_MAX_LAGS = 10
PACF_SIGNIFICANCE_LEVEL = 0.05
PACF_MAX_SELECTED_LAGS = 4
FEATURE_LAG_PERIODS_FALLBACK = [1, 2, 3, 5]

# ============================================================================
# MINIMUM SAMPLE THRESHOLDS
# ============================================================================
MIN_SAMPLES_FEATURE_SELECTION = 200
MIN_SAMPLES_PLATT = 100
MIN_SAMPLES_ISOTONIC = 500
MIN_SAMPLES_CLASS_BALANCING = 50

# ============================================================================
# FEATURE SET CONFIGURATION
# ============================================================================
USE_BASE_FEATURES = True
USE_FOCUSED_FEATURES = False

# ============================================================================
# DIRECTION MODEL FEATURES
# ============================================================================
DIRECTION_FEATURE_GROUPS = {
    'top_raw': ['E10', 'M12', 'P6', 'I2', 'P1'],
    'short_vol': ['daily_volatility_lagged', 'ewma_vol_2d', 'realized_vol_2d', 'rolling_max_5d'],
    # ⭐ DUAL EMA FEATURES (Validated leak-free, 0.15-0.21 Q1-Q5 range)
    'dual_ema_direction': ['RSI_ema_long_first', 'Skewness_ema_long_first', 'Volatility_ema_divergence',
                           'Momentum_ema_long_first', 'RSI_ema_divergence', 'returns_ema_long_first'],
    'hmm_signals': ['hmm_regime', 'hmm5_regime', 'MOM_hmm_regime', 'V_hmm_stable_5d', 
                    'V_hmm_stable_3d', 'V_hmm_transitions_10d', 'V_hmm_transitions_5d', 'E_hmm_duration'],
    'hmm_extended': ['E_hmm4_agree', 'month_ensemble_x_hmm5', 'hmm_regime_prob_2', 
                     'M_hmm_regime', 'month_ensemble_x_hmm4'],
    'position_rates': ['hmm_regime_0_pos_rate', 'hmm_regime_3_pos_rate', 'hmm5_regime_1_pos_rate',
                       'current_regime5_pos_rate', 'current_regime_vol_pct'],
    'anomaly_signals': ['HMM4_if_is_anomaly', 'group_if_any_severe', 'group_if_max_severity',
                        'M_if_is_anomaly', 'V_if_is_anomaly', 'P_if_anomaly_score', 'HMM5_if_anomaly_score'],
    'severity_signals': ['P_if_severity', 'HMM4_if_severity'],
    'changepoint_signals': ['V_chg_vol_spike_prob', 'regime_change_vol_spike_prob', 'MOM_chg_vol_spike_prob',
                            'I_chg_dir_reversal_prob', 'changepoint_vol_down', 'cusum_vol_neg_change',
                            'D_chg_dir_reversal_prob', 'P_chg_vol_spike_prob', 'E_chg_vol_spike_prob',
                            'D_chg_vol_spike_prob', 'HMM4_chg_vol_spike_prob'],
    'regime_context': ['high_vol_regime', 'uptrend_regime', 'historical_vol_regime',
                       'kalman_cusum_vol_interact', 'uptrend_regime_200d', 'historical_vol5_regime', 'garch_vol_regime'],
    'momentum_signals': ['month_ensemble', 'dist_from_p05', 'upper_90pct_200d', 'sharpe_like_200d',
                         'vol_adj_momentum_200d', 'momentum_ratio_10_50', 'rolling_min_21d',
                         'momentum_200d', 'momentum_252d', 'ma_200d', 'sharpe_like_252d'],
    'cusum_extended': ['cusum_returns_pos', 'cusum_volatility_pos', 'helper_vol_lr_error', 'cusum_ret_ratio'],
    'reversal_signals': ['reversal_up_50_200', 'reversal_21d', 'reversal_5_21'],
    'additional_raw': ['M8', 'M13', 'V5', 'E20', 'S4'],
    'anomaly_severity': ['anomaly_moderate_severity', 'anomaly_extreme_severity'],
}

# ============================================================================
# VOLATILITY MODEL FEATURES
# ============================================================================
VOLATILITY_FEATURE_GROUPS = {
    'top_raw': ['V7', 'E19', 'M1', 'V9', 'V10'],
    # ⭐ DUAL EMA FEATURES (Validated leak-free, 0.90 correlation with forward vol!)
    'dual_ema_volatility': ['Volatility_ema_long_first', 'Volatility_ema_divergence', 'returns_ema_long_first',
                            'Drawdown_ema_short_first', 'RSI_ema_short_first', 'Momentum_ema_long_first',
                            'Volatility_ema_short_first', 'Sharpe_ema_short_first'],
    'hist_vol': ['mean_hist_vol_10', 'mean_hist_vol_21', 'mean_hist_vol_5',
                 'garch_volatility', 'vol_of_vol_14d', 'vol_of_vol_21d'],
    'realized_vol': ['realized_vol_5d', 'realized_vol_7d', 'realized_vol_10d', 'realized_vol_14d',
                     'realized_vol_20d', 'realized_vol_21d', 'realized_vol_30d'],
    'ewma_vol': ['ewma_vol_5d', 'ewma_vol_7d', 'ewma_vol_10d', 'ewma_vol_14d',
                 'ewma_vol_20d', 'ewma_vol_21d', 'ewma_vol_30d'],
    'garch': ['garch_forecast_1d', 'garch_vol_regime', 'garch_variance'],
    'extreme_return_prob': ['regime_change_extreme_ret_prob', 'M_chg_extreme_ret_prob', 'S_chg_extreme_ret_prob',
                            'MOM_chg_extreme_ret_prob', 'HMM4_chg_extreme_ret_prob', 'D_chg_extreme_ret_prob',
                            'HMM5_chg_extreme_ret_prob', 'I_chg_extreme_ret_prob', 'S_chg_combined', 'M_chg_combined'],
    'drawdown': ['max_drawdown_50d', 'max_drawdown_60d', 'max_drawdown_100d',
                 'max_drawdown_21d', 'max_drawdown_14d', 'max_drawdown_200d'],
    'helper_vol': ['helper_vol_lr', 'helper_vol_consensus', 'helper_vol_ewma', 'helper_vol_lr_x_regime',
                   'helper_vol_ewma_absret', 'helper_vol_ewma_x_regime', 'helper_vol_ewma_variance'],
    'range_measures': ['rolling_range_14d', 'rolling_range_10d', 'rolling_range_21d', 'rolling_range_5d',
                       'rolling_min_14d', 'rolling_min_10d', 'rolling_min_5d', 'rolling_min_21d',
                       'lower_10pct_21d', 'lower_5pct_21d'],
    'vol_ma': ['volatility_ma_5', 'volatility_ma_21', 'vol_of_vol_10d', 'current_regime5_vol_pct'],
}

# ============================================================================
# CLASS BALANCING AND CALIBRATION
# ============================================================================
USE_CLASS_BALANCING = True
USE_PROBABILITY_CALIBRATION = True
CALIBRATION_METHOD = 'platt'
CALIBRATION_BUFFER_SIZE = 10
MIN_CALIBRATION_SAMPLES = 500
MIN_CALIBRATION_POSITIVES = 100

# Conditional calibration based on AUC
CALIBRATION_AUC_LOW = 0.52   # Below this: calibrate (very weak signal)
CALIBRATION_AUC_HIGH = 0.58  # Above this: calibrate (strong signal)

# ============================================================================
# HALF-LIFE SAMPLE WEIGHTING
# ============================================================================
USE_HALF_LIFE_WEIGHTING = True
HALF_LIFE_SAMPLES = 330
MIN_SAMPLE_WEIGHT = 0.1

# ============================================================================
# DRIFT DETECTION
# ============================================================================
USE_DRIFT_DETECTION = True
DRIFT_CHECK_INTERVAL = 6
DRIFT_PSI_THRESHOLD = 0.10
USE_DRIFT_ADJUSTMENT = True
DRIFT_L2_MULTIPLIER = 1.5
DRIFT_DEPTH_REDUCTION = 1
DRIFT_CONFIDENCE_SHRINK = 0.15

# ============================================================================
# ADAPTIVE WINDOW CONFIGURATION
# ============================================================================
USE_ADAPTIVE_WINDOWS_PER_ITERATION = True
ADAPTIVE_HALF_LIFE = True
ADAPTIVE_LOOKBACK_FOR_P = 300
MIN_ADAPTIVE_HALF_LIFE = 100
MAX_ADAPTIVE_HALF_LIFE = 500

# ============================================================================
# REGIME-AWARE ADAPTIVE WINDOW
# ============================================================================
USE_REGIME_AWARE_TRAIN_SIZING = True
USE_REGIME_POS_RATE_THRESHOLD = True
REGIME_P_MISMATCH_THRESHOLD = 0.10
REGIME_PURITY_THRESHOLD = 0.60
MIN_TRAIN_WINDOW_ADAPTIVE = 200
MAX_TRAIN_SHRINK_RATIO = 0.5
INSTABILITY_TRANSITION_THRESHOLD = 2

# ============================================================================
# SHUFFLE VAL+CAL POOL
# ============================================================================
SHUFFLE_VAL_CAL_POOL = True

# ============================================================================
# THRESHOLD CONFIGURATION
# ============================================================================
THRESHOLD_METHOD = 'quantile_match'
FIXED_THRESHOLD = 0.5
MIN_RECALL_CONSTRAINT = 0.30

# AUC-Confidence threshold adjustment
USE_AUC_CONFIDENCE_ADJUSTMENT = True
AUC_CONFIDENCE_STRENGTH = 0.5
AUC_MIN_FOR_CONFIDENCE = 0.52

# Regime-specific thresholds
USE_REGIME_SPECIFIC_THRESHOLDS = True
REGIME_THRESHOLD_ADJUSTMENTS = {
    'LOW': 0.00,
    'MEDIUM': 0.00,
    'HIGH': 0.00,
    'VERY_HIGH': 0.00,
    'EXTREME': 0.00,
}

# ============================================================================
# DATA PATHS
# ============================================================================
# Original: train_complete_all_features.csv (1841 rows)
# With validation: train_plus_validation.csv (2021 rows = 1841 + 180 validation)
PREPROCESSED_TRAIN_PATH = '/media/przem/w/kaggle/preprocessed_data/train_plus_validation.csv'
PARTIAL_DATA_PATH = '/media/przem/w/kaggle/preprocessed_data/partial_with_all_features.csv'
DIRECTION_TARGET = 'direction_target'
VOLATILITY_TARGET = 'volatility_target'

# ============================================================================
# GPU CONFIGURATION
# ============================================================================
# GPU enabled for faster training
USE_GPU = True  # Re-enabled 2025-12-11

def setup_gpu_params():
    """Setup GPU/CPU parameters for CatBoost."""
    global USE_GPU
    
    if USE_GPU:
        try:
            import subprocess
            result = subprocess.run(['nvidia-smi'], capture_output=True, text=True, timeout=5)
            if result.returncode != 0:
                print("WARNING: nvidia-smi failed, falling back to CPU")
                USE_GPU = False
            else:
                print("GPU detected successfully (nvidia-smi OK)")
        except Exception as e:
            print(f"WARNING: GPU check failed ({e}), falling back to CPU")
            USE_GPU = False
    
    if USE_GPU:
        catboost_params = {
            'task_type': 'GPU',
            'devices': '0',
            'random_seed': 42,
            'logging_level': 'Silent',
            'allow_writing_files': False,
        }
    else:
        catboost_params = {
            'thread_count': os.cpu_count() or 12,
            'task_type': 'CPU',
            'random_seed': 42,
            'logging_level': 'Silent',
            'allow_writing_files': False,
        }
    
    return catboost_params, USE_GPU

# ============================================================================
# MODEL HYPERPARAMETERS (will be combined with GPU params at runtime)
# ============================================================================
DIR_MODEL_PARAMS_BASE = {
    'depth': 16,
    'iterations': 2000,
    'learning_rate': 0.005,
    'l2_leaf_reg': 10.0,
    'min_data_in_leaf': 50,
    'grow_policy': 'Lossguide',
    'max_leaves': 31,
    'has_time': True,
    'bootstrap_type': 'Bernoulli',
    'subsample': 0.8,
    'early_stopping_rounds': 200,
    'use_best_model': True,
    'loss_function': 'Logloss',
    'eval_metric': 'Logloss',
}

VOL_MODEL_PARAMS_BASE = {
    'depth': 16,
    'iterations': 1500,
    'learning_rate': 0.01,
    'l2_leaf_reg': 5.0,
    'min_data_in_leaf': 20,
    'grow_policy': 'Lossguide',
    'max_leaves': 31,
    'has_time': True,
    'bootstrap_type': 'Bernoulli',
    'subsample': 0.8,
    'early_stopping_rounds': 150,
    'use_best_model': True,
    'loss_function': 'RMSE',
    'eval_metric': 'RMSE',
}

# ============================================================================
# FEATURE EXCLUSION
# ============================================================================
EXCLUDE_FROM_FEATURES = [
    'forward_returns',
    'market_forward_excess_returns',
    'volatility_target',
    'direction_target',
    'date_id',
    'time_id',
    'row_id',
    'date',
    'timestamp',
    'symbol',
    'risk_free_rate',
]

BASIC_FEATURE_PATTERN = re.compile(r'^[A-Z]\d+$')

# ============================================================================
# OPTUNA TUNING
# ============================================================================
USE_OPTUNA_TUNING = True
# EMPIRICAL: With 3500x smaller search space (from 80M to 23K combinations),
# 20 seconds (~12 trials) covers 63% of historical winners.
# Warm-start (trials 1-2) wins 18% of the time, so fewer exploration trials needed.
OPTUNA_TIMEOUT_SECONDS = 20
OPTUNA_RETUNE_ON_DRIFT = True
OPTUNA_RETUNE_TIMEOUT = 20
OPTUNA_ENQUEUE_PREVIOUS_BEST = True

# ============================================================================
# ENSEMBLE CONFIGURATION
# ============================================================================
ENSEMBLE_MODE = 'cb_lgb'
USE_SINGLE_MODEL = (ENSEMBLE_MODE == 'single_cb')
USE_HGB = False

# Meta stacker configuration
META_STACKER_MIN_SAMPLES = 50
META_STACKER_N_ESTIMATORS = 200
META_STACKER_MAX_DEPTH = 6
META_STACKER_MIN_SAMPLES_LEAF = 20
META_BUFFER_MAX_WINDOWS = 8
META_BUFFER_MAX_SAMPLES = 8000

# ============================================================================
# MULTI-CONFIG TRACKING
# ============================================================================
MULTI_CONFIG_TRACKING = True
N_TOP_CONFIGS = 10
ROLLING_WINDOW_SIZE = 180

# Config grid for parallel tracking
CONFIG_GRID = {
    'model': ['single', 'ensemble'],
    'calibration': ['none', 'platt'],
    'threshold': ['quantile_match', 'youden_j', 'class_balanced'],
    'auc_adjust': [True, False],
    'regime_thr': [True, False],
    'window': ['original', 'shrunk'],
}

# ============================================================================
# RSI PERIODS
# ============================================================================
RSI_PERIODS = [2, 3, 5, 7, 9, 10, 12, 14, 16, 20, 21, 25, 30, 50]
