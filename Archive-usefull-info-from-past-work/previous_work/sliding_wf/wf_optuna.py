# ============================================================================
# WF_OPTUNA.PY - Optuna Hyperparameter Tuning Functions for Walk-Forward
# ============================================================================
# Contains:
#   - calculate_optuna_search_space(): Data-driven hyperparameter ranges
#   - run_optuna_tuning(): Multi-model Optuna optimization (CatBoost + LightGBM)
#   - analyze_dataset_and_estimate_ranges(): Legacy wrapper for compatibility
# ============================================================================

import numpy as np
import gc
import optuna
from catboost import CatBoostClassifier
from lightgbm import LGBMClassifier
from sklearn.metrics import roc_auc_score

# Suppress CatBoost output
import io
NULL_STREAM = io.StringIO()

# Global state for warm-start enqueuing
_previous_best_cb_params = None
_previous_best_lgb_params = None
_persistent_optuna_study = None

# Default setting for warm-start
OPTUNA_ENQUEUE_PREVIOUS_BEST = True


def calculate_optuna_search_space(
    N_train: int,
    gap_size: int,
    n_features: int = None,
    sparsity: float = 0.0,
    pos_rate: float = 0.5,
    verbose: bool = True
) -> dict:
    """
    Calculate data-driven Optuna hyperparameter search ranges.
    
    This function computes constrained search ranges based on:
    1. N (effective sample size) - determines model capacity
    2. G (gap size) - CAL + VAL windows between TRAIN and PRED
    3. Gap Ratio (G/N) - if > 0.5, we're predicting "far" into future
    4. Sparsity - affects tree depth requirements
    5. Class balance - affects regularization needs
    
    Parameters:
    -----------
    N_train : int
        Number of samples in TRAIN window
    gap_size : int
        Number of time steps between TRAIN end and PRED start (CAL + VAL)
    n_features : int
        Number of features in the dataset
    sparsity : float
        Fraction of zero values in features (0.0 to 1.0)
    pos_rate : float
        Fraction of positive class (for classification)
    verbose : bool
        Print diagnostic information
        
    Returns:
    --------
    dict : Search space configuration with keys:
        - 'num_leaves': (min, max, step)
        - 'max_depth': (min, max, step)
        - 'learning_rate': list of categorical values
        - 'n_estimators': (min, max, step)
        - 'reg_lambda': list of categorical values
        - 'min_child_samples': (min, max, step)
        - 'subsample': list of categorical values
        - 'gap_penalty': float (for reference)
        - 'gap_ratio': float (for reference)
    """
    
    # ════════════════════════════════════════════════════════════════════
    # STEP A: Calculate Gap Penalty
    # ════════════════════════════════════════════════════════════════════
    gap_ratio = gap_size / max(1, N_train)
    gap_penalty = max(0.25, 1.0 / (1.0 + gap_ratio))
    
    # ════════════════════════════════════════════════════════════════════
    # STEP B: Calculate max_leaves (Model Capacity)
    # ════════════════════════════════════════════════════════════════════
    # EMPIRICAL: 95.4% of best trials use num_leaves=8, only 2.7% use 12, 1.9% use 16
    # Simpler trees generalize better for time-series with limited window data
    # FIXED to [8, 12, 16] with step 4 - covers 100% of historical winners
    leaves_min = 8
    leaves_max = 16
    leaves_step = 4
    
    # ════════════════════════════════════════════════════════════════════
    # STEP C: Calculate min_data_in_leaf (Noise Filter)
    # ════════════════════════════════════════════════════════════════════
    # EMPIRICAL: 97% of best trials use values in [5, 10, 15, 20]
    # 25 and 30 are rare (< 3% combined)
    # FIXED to [5, 10, 15, 20] with step 5 - covers 97% of historical winners
    min_data_min = 5
    min_data_max = 20
    min_data_step = 5
    
    # ════════════════════════════════════════════════════════════════════
    # STEP D: Calculate learning_rate (Convergence)
    # ════════════════════════════════════════════════════════════════════
    # EMPIRICAL: Winners cluster at 0.005, 0.01, 0.02, 0.025, 0.05, 0.1
    # Higher values (0.14-0.15) are rare (<5%)
    # FIXED to empirically optimal discrete values
    lr_options = [0.005, 0.01, 0.02, 0.025, 0.05, 0.1]
    
    # ════════════════════════════════════════════════════════════════════
    # STEP E: Calculate L2 Regularization (Generalization)
    # ════════════════════════════════════════════════════════════════════
    # EMPIRICAL: Winners use [1, 3, 5, 10, 15, 20, 30, 50]
    # Higher values correlate with better scores (r=+0.103)
    # 30 is most common (17%), followed by 20 (14%) and 50 (14%)
    # FIXED to empirically optimal discrete values
    reg_options = [1.0, 3.0, 5.0, 10.0, 15.0, 20.0, 30.0, 50.0]
    
    # ════════════════════════════════════════════════════════════════════
    # STEP F: Calculate max_depth (Safety Bound for Lossguide)
    # ════════════════════════════════════════════════════════════════════
    # EMPIRICAL: Only 4 and 6 ever win (54% vs 46% split)
    # Values 5, 7, 8+ never appear in best trials
    # FIXED to [4, 6] with step 2 - covers 100% of historical winners
    depth_min = 4
    depth_max = 6
    depth_step = 2
    
    # ════════════════════════════════════════════════════════════════════
    # STEP G: Calculate n_estimators (Number of Trees)
    # ════════════════════════════════════════════════════════════════════
    # EMPIRICAL: 300 wins 52%, 400 wins 47%, 500 wins <1%
    # Early stopping makes this less critical - trees stop when no improvement
    # FIXED to [300, 400] with step 100 - covers 99% of historical winners
    est_min = 300
    est_max = 400
    est_step = 100
    
    # ════════════════════════════════════════════════════════════════════
    # STEP H: Calculate subsample (Stochastic Regularization)
    # ════════════════════════════════════════════════════════════════════
    # EMPIRICAL: 0.5 wins 36%, 0.6 wins 25%, 0.7 wins 15%, 0.8 wins 13%, 0.9 wins 11%
    # Lower subsample correlates with better scores (r=-0.194 for LightGBM)
    # FIXED to [0.5, 0.6, 0.7, 0.8, 0.9] - covers 100% of historical winners
    subsample_options = [0.5, 0.6, 0.7, 0.8, 0.9]
    
    # ════════════════════════════════════════════════════════════════════
    # BUILD SEARCH SPACE
    # ════════════════════════════════════════════════════════════════════
    
    search_space = {
        'num_leaves': {'min': leaves_min, 'max': leaves_max, 'step': leaves_step},
        'max_depth': {'min': depth_min, 'max': depth_max, 'step': depth_step},
        'learning_rate': {'options': lr_options},
        'n_estimators': {'min': est_min, 'max': est_max, 'step': est_step},
        'reg_lambda': {'options': reg_options},
        'min_child_samples': {'min': min_data_min, 'max': min_data_max, 'step': min_data_step},
        'subsample': {'options': subsample_options},
        # Metadata
        '_gap_ratio': gap_ratio,
        '_gap_penalty': gap_penalty,
        '_N_train': N_train,
        '_gap_size': gap_size,
    }
    
    if verbose:
        print("\n" + "="*70)
        print("DATA-DRIVEN OPTUNA SEARCH SPACE CALCULATION")
        print("="*70)
        print(f"  Inputs:")
        print(f"    N_train (sample size):     {N_train:,}")
        print(f"    Gap Size (CAL+VAL):        {gap_size}")
        print(f"    Gap Ratio (G/N):           {gap_ratio:.3f}")
        print(f"    Gap Penalty:               {gap_penalty:.3f}")
        print(f"    Features:                  {n_features if n_features else 'N/A'}")
        print(f"    Sparsity:                  {sparsity:.1%}")
        print(f"    Positive Rate:             {pos_rate:.1%}")
        print("-"*70)
        print(f"  Calculated Search Ranges:")
        print(f"    num_leaves:       [{leaves_min}, {leaves_max}] step={leaves_step}")
        print(f"    max_depth:        [{depth_min}, {depth_max}] step={depth_step}")
        print(f"    learning_rate:    {lr_options}")
        print(f"    n_estimators:     [{est_min}, {est_max}] step={est_step}")
        print(f"    reg_lambda:       {reg_options}")
        print(f"    min_child_samples:[{min_data_min}, {min_data_max}] step={min_data_step}")
        print(f"    subsample:        {subsample_options}")
        print("="*70 + "\n")
    
    return search_space


def run_optuna_tuning(X_train, y_train, X_val, y_val, timeout_sec, gpu_params, 
                      search_space=None, gap_size=None, verbose=True):
    """
    Run Optuna hyperparameter search comparing CatBoost Lossguide vs LightGBM.
    
    ⭐ DATA-DRIVEN SEARCH SPACE:
        - If search_space is provided, uses calculated ranges from calculate_optuna_search_space()
        - If search_space is None but gap_size is provided, calculates it automatically
        - These ranges are constrained based on N (sample size) and Gap (temporal distance)
        - Prevents Optuna from finding overfit configurations
    
    ⭐ WARM-START ENQUEUING:
        - Creates FRESH study each run (adapts to new data distribution)
        - Enqueues best CB + best LGB params from PREVIOUS run as first 2 trials
        - Gives warm start without carrying stale exploration history
        - Best params stored globally for next run
    
    ⭐ Both use leaf-wise growth so parameters translate well:
        - CatBoost Lossguide: max_leaves, min_data_in_leaf, depth, learning_rate
        - LightGBM: num_leaves, min_child_samples, max_depth, learning_rate
    
    Parameters:
    -----------
    X_train, y_train : Training data
    X_val, y_val : Validation data
    timeout_sec : Optuna timeout in seconds
    gpu_params : GPU configuration for CatBoost
    search_space : dict from calculate_optuna_search_space() or None for auto-calculation
    gap_size : int, temporal gap between TRAIN end and PRED start (CAL + VAL windows)
               Used to calculate search_space if search_space is None
    verbose : Print progress
    
    Returns: dict with best_cb_params, best_lgb_params, best_cb_score, best_lgb_score, study
    """
    global _previous_best_cb_params, _previous_best_lgb_params, _persistent_optuna_study
    
    # ════════════════════════════════════════════════════════════════════
    # SETUP SEARCH SPACE
    # ════════════════════════════════════════════════════════════════════
    if search_space is None:
        if gap_size is not None:
            N_train = len(X_train)
            n_features = X_train.shape[1]
            if n_features > 0 and N_train > 0:
                sparsity = float((X_train.values == 0).sum()) / (N_train * n_features)
            else:
                sparsity = 0.0
            pos_rate = float(y_train.mean()) if len(y_train) > 0 else 0.5
            
            search_space = calculate_optuna_search_space(
                N_train=N_train,
                gap_size=gap_size,
                n_features=n_features,
                sparsity=sparsity,
                pos_rate=pos_rate,
                verbose=verbose
            )
        else:
            # Fallback to simple defaults
            search_space = {
                'num_leaves': {'min': 15, 'max': 63, 'step': 16},
                'max_depth': {'min': 6, 'max': 12, 'step': 2},
                'learning_rate': {'options': [0.005, 0.01, 0.02, 0.03]},
                'n_estimators': {'min': 500, 'max': 2000, 'step': 500},
                'reg_lambda': {'options': [5.0, 10.0, 20.0, 30.0]},
                'min_child_samples': {'min': 20, 'max': 100, 'step': 20},
                'subsample': {'options': [0.6, 0.7, 0.8, 0.9]},
            }
            if verbose:
                print("    [Optuna] Using default search space (no gap_size provided)")
    else:
        if verbose:
            gap_ratio = search_space.get('_gap_ratio', 'N/A')
            gap_penalty = search_space.get('_gap_penalty', 'N/A')
            if isinstance(gap_ratio, (int, float)) and isinstance(gap_penalty, (int, float)):
                print(f"    [Optuna] Using data-driven search space (gap_ratio={gap_ratio:.3f}, penalty={gap_penalty:.3f})")
            else:
                print(f"    [Optuna] Using provided search space")
    
    ss = search_space  # Shorthand
    
    # Calculate class weight
    tune_scale_pos_weight = (y_train == 0).sum() / max(1, (y_train == 1).sum())
    tune_scale_pos_weight = max(0.1, min(10.0, tune_scale_pos_weight))
    
    def optuna_objective(trial):
        model_type = trial.suggest_categorical('model_type', ['catboost', 'lightgbm'])
        
        num_leaves = trial.suggest_int('num_leaves', 
                                        ss['num_leaves']['min'], 
                                        ss['num_leaves']['max'], 
                                        step=ss['num_leaves']['step'])
        
        max_depth = trial.suggest_int('max_depth', 
                                       ss['max_depth']['min'], 
                                       ss['max_depth']['max'], 
                                       step=ss['max_depth']['step'])
        
        learning_rate = trial.suggest_categorical('learning_rate', ss['learning_rate']['options'])
        
        n_estimators = trial.suggest_int('n_estimators', 
                                          ss['n_estimators']['min'], 
                                          ss['n_estimators']['max'], 
                                          step=ss['n_estimators']['step'])
        
        reg_lambda = trial.suggest_categorical('reg_lambda', ss['reg_lambda']['options'])
        
        min_child_samples = trial.suggest_int('min_child_samples', 
                                               ss['min_child_samples']['min'], 
                                               ss['min_child_samples']['max'], 
                                               step=ss['min_child_samples']['step'])
        
        subsample = trial.suggest_categorical('subsample', ss['subsample']['options'])
        
        TRIAL_TIMEOUT_SEC = 9.0
        import time as time_module
        trial_start_time = time_module.time()
        
        try:
            if model_type == 'catboost':
                params = {
                    'grow_policy': 'Lossguide',
                    'max_leaves': num_leaves,
                    'depth': max_depth,
                    'learning_rate': learning_rate,
                    'iterations': n_estimators,
                    'l2_leaf_reg': reg_lambda,
                    'min_data_in_leaf': min_child_samples,
                    'subsample': subsample,
                    'bootstrap_type': 'Bernoulli',
                    'has_time': True,
                    'early_stopping_rounds': 300,
                    'use_best_model': True,
                    'loss_function': 'Logloss',
                    'eval_metric': 'AUC',
                    'scale_pos_weight': tune_scale_pos_weight,
                    **gpu_params
                }
                
                model = CatBoostClassifier(**params)
                model.fit(
                    X_train, y_train,
                    eval_set=(X_val, y_val),
                    log_cout=NULL_STREAM, log_cerr=NULL_STREAM
                )
                
                elapsed = time_module.time() - trial_start_time
                if elapsed > TRIAL_TIMEOUT_SEC:
                    del model
                    gc.collect()
                    raise optuna.TrialPruned(f"Trial too slow: {elapsed:.1f}s > {TRIAL_TIMEOUT_SEC}s")
                
            elif model_type == 'lightgbm':
                # Try GPU first, fallback to CPU
                lgb_device = 'cpu'
                import os, sys
                for try_device in ['gpu', 'cuda']:
                    try:
                        with open(os.devnull, 'w') as devnull:
                            old_stdout, old_stderr = sys.stdout, sys.stderr
                            sys.stdout, sys.stderr = devnull, devnull
                            try:
                                test_params = {'device': try_device, 'n_estimators': 1, 'verbose': -1}
                                test_model = LGBMClassifier(**test_params)
                                test_model.fit(X_train[:10], y_train[:10])
                                lgb_device = try_device
                                del test_model
                            finally:
                                sys.stdout, sys.stderr = old_stdout, old_stderr
                        break
                    except Exception:
                        pass
                
                params = {
                    'boosting_type': 'gbdt',
                    'num_leaves': num_leaves,
                    'max_depth': max_depth,
                    'learning_rate': learning_rate,
                    'n_estimators': n_estimators,
                    'reg_lambda': reg_lambda,
                    'min_child_samples': min_child_samples,
                    'subsample': subsample,
                    'subsample_freq': 1,
                    'objective': 'binary',
                    'metric': 'auc',
                    'scale_pos_weight': tune_scale_pos_weight,
                    'verbose': -1,
                }
                if lgb_device != 'cpu':
                    params['device'] = lgb_device
                else:
                    params['n_jobs'] = -1
                
                model = LGBMClassifier(**params)
                model.fit(
                    X_train, y_train,
                    eval_set=[(X_val, y_val)],
                    callbacks=[
                        __import__('lightgbm').early_stopping(stopping_rounds=300, verbose=False)
                    ]
                )
                
                elapsed = time_module.time() - trial_start_time
                if elapsed > TRIAL_TIMEOUT_SEC:
                    del model
                    gc.collect()
                    raise optuna.TrialPruned(f"Trial too slow: {elapsed:.1f}s > {TRIAL_TIMEOUT_SEC}s")
            
            val_probs = model.predict_proba(X_val)[:, 1]
            val_auc = roc_auc_score(y_val, val_probs)
            val_brier = np.mean((val_probs - y_val) ** 2)
            
            train_probs = model.predict_proba(X_train)[:, 1]
            train_auc = roc_auc_score(y_train, train_probs)
            auc_gap = train_auc - val_auc
            gap_penalty = max(0, (auc_gap - 0.15) * 0.5)
            
            calibration_score = 0.25 - val_brier
            combined_score = (2 * val_auc + (calibration_score * 4)) / 3
            adjusted_score = combined_score - gap_penalty
            
            del model
            gc.collect()
            
            return adjusted_score
        except Exception as e:
            gc.collect()
            return 0.5
    
    # Helper function to adapt params to current search space
    def adapt_params_to_search_space(params, ss):
        if params is None:
            return None
        
        adapted = {}
        for key, value in params.items():
            if key == 'model_type':
                adapted[key] = value
                continue
            
            if key not in ss:
                continue
            
            spec = ss[key]
            
            if 'options' in spec:
                options = spec['options']
                if value in options:
                    adapted[key] = value
                else:
                    try:
                        closest = min(options, key=lambda x: abs(float(x) - float(value)))
                        adapted[key] = closest
                    except (TypeError, ValueError):
                        return None
            elif 'min' in spec and 'max' in spec:
                step = spec.get('step', 1)
                clamped = max(spec['min'], min(spec['max'], value))
                if step > 0:
                    clamped = spec['min'] + round((clamped - spec['min']) / step) * step
                    clamped = max(spec['min'], min(spec['max'], clamped))
                adapted[key] = int(clamped) if isinstance(value, int) else clamped
            else:
                adapted[key] = value
        
        return adapted if adapted else None
    
    # Always create fresh study
    study = optuna.create_study(direction='maximize', study_name='catboost_vs_lightgbm')
    
    # Enqueue previous best params as first trials (warm start)
    n_enqueued = 0
    if OPTUNA_ENQUEUE_PREVIOUS_BEST:
        if _previous_best_cb_params is not None:
            adapted_cb = adapt_params_to_search_space(_previous_best_cb_params, ss)
            if adapted_cb is not None:
                try:
                    study.enqueue_trial(adapted_cb)
                    n_enqueued += 1
                    if verbose:
                        print(f"    [Optuna] Enqueued previous best CatBoost params (adapted)")
                except Exception as e:
                    if verbose:
                        print(f"    [Optuna] Could not enqueue CB params: {e}")
            elif verbose:
                print(f"    [Optuna] Skipped CB warm-start (params incompatible with new search space)")
        
        if _previous_best_lgb_params is not None:
            adapted_lgb = adapt_params_to_search_space(_previous_best_lgb_params, ss)
            if adapted_lgb is not None:
                try:
                    study.enqueue_trial(adapted_lgb)
                    n_enqueued += 1
                    if verbose:
                        print(f"    [Optuna] Enqueued previous best LightGBM params (adapted)")
                except Exception as e:
                    if verbose:
                        print(f"    [Optuna] Could not enqueue LGB params: {e}")
            elif verbose:
                print(f"    [Optuna] Skipped LGB warm-start (params incompatible with new search space)")
        
        if n_enqueued > 0 and verbose:
            print(f"    [Optuna] Warm-starting with {n_enqueued} enqueued trial(s)")
    
    # Run optimization
    study.optimize(optuna_objective, timeout=timeout_sec, show_progress_bar=verbose)
    
    if verbose:
        print(f"    [Optuna] Completed {len(study.trials)} trials this run")
    
    # Log trials to CSV
    try:
        import datetime
        import pandas as pd
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        log_path = f'/media/przem/w/kaggle/optuna_trials_{timestamp}.csv'
        
        trial_records = []
        for trial in study.trials:
            if trial.state == optuna.trial.TrialState.COMPLETE:
                record = {
                    'trial_number': trial.number,
                    'score': trial.value,
                    'timestamp': timestamp,
                    **trial.params
                }
                trial_records.append(record)
        
        if trial_records:
            trials_df = pd.DataFrame(trial_records)
            trials_df.to_csv(log_path, index=False)
            if verbose:
                print(f"    [Optuna] Saved {len(trial_records)} trial params to {log_path}")
    except Exception as e:
        if verbose:
            print(f"    [Optuna] Could not save trial log: {e}")
    
    # Extract best CatBoost and LightGBM trials
    best_cb_trial = None
    best_lgb_trial = None
    best_cb_score = -np.inf
    best_lgb_score = -np.inf
    
    for trial in study.trials:
        if trial.state != optuna.trial.TrialState.COMPLETE:
            continue
        model_type = trial.params.get('model_type', '')
        score = trial.value
        if model_type == 'catboost' and score > best_cb_score:
            best_cb_score = score
            best_cb_trial = trial
        elif model_type == 'lightgbm' and score > best_lgb_score:
            best_lgb_score = score
            best_lgb_trial = trial
    
    best_cb_params = best_cb_trial.params if best_cb_trial else None
    best_lgb_params = best_lgb_trial.params if best_lgb_trial else None
    
    # Store best params for next run (warm-start enqueuing)
    if OPTUNA_ENQUEUE_PREVIOUS_BEST:
        if best_cb_params is not None:
            _previous_best_cb_params = best_cb_params.copy()
        if best_lgb_params is not None:
            _previous_best_lgb_params = best_lgb_params.copy()
        if verbose:
            print(f"    [Optuna] Stored best params for next run warm-start")
    
    if verbose:
        print(f"    Best CatBoost score: {best_cb_score:.4f}" if best_cb_trial else "    No valid CatBoost trials")
        print(f"    Best LightGBM score: {best_lgb_score:.4f}" if best_lgb_trial else "    No valid LightGBM trials")
        print(f"    ⭐ ENSEMBLE MODE: Using CB + LGB with meta-stacker")
    
    return {
        'best_cb_params': best_cb_params,
        'best_lgb_params': best_lgb_params,
        'best_cb_score': best_cb_score,
        'best_lgb_score': best_lgb_score,
        'study': study
    }


def analyze_dataset_and_estimate_ranges(X, y, is_classification=True, verbose=True):
    """
    Legacy function - now wraps calculate_optuna_search_space.
    Kept for backward compatibility.
    """
    N_samples = len(X)
    M_features = X.shape[1]
    
    # Estimate sparsity
    if hasattr(X, 'values'):
        sparsity = float((X.values == 0).mean())
    else:
        sparsity = float((X == 0).mean())
    
    # Estimate class balance
    if is_classification:
        pos_rate = float(y.mean())
    else:
        pos_rate = 0.5
    
    # Use default gap = 20% of N (conservative estimate without actual gap info)
    default_gap = int(N_samples * 0.2)
    
    search_space = calculate_optuna_search_space(
        N_train=N_samples,
        gap_size=default_gap,
        n_features=M_features,
        sparsity=sparsity,
        pos_rate=pos_rate,
        verbose=verbose
    )
    
    # Convert to old format for compatibility
    ranges = {
        'learning_rate': (min(search_space['learning_rate']['options']), 
                          max(search_space['learning_rate']['options'])),
        'max_leaves': (search_space['num_leaves']['min'], 
                       search_space['num_leaves']['max']),
        'min_data_in_leaf': (search_space['min_child_samples']['min'], 
                             search_space['min_child_samples']['max']),
        'l2_leaf_reg': (min(search_space['reg_lambda']['options']), 
                        max(search_space['reg_lambda']['options'])),
        'depth': (search_space['max_depth']['min'], 
                  search_space['max_depth']['max']),
    }
    
    return ranges
