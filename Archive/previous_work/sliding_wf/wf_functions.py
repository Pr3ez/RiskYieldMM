# ============================================================================
# WF_FUNCTIONS.PY - Walk-Forward Utility Functions
# ============================================================================
# Calibration, thresholding, weighting, and feature selection utilities
# ============================================================================

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.isotonic import IsotonicRegression

# Import configuration constants
from wf_config import (
    USE_CLASS_BALANCING, MIN_SAMPLES_CLASS_BALANCING,
    USE_HALF_LIFE_WEIGHTING, HALF_LIFE_SAMPLES,
    USE_PROBABILITY_CALIBRATION, CALIBRATION_AUC_LOW, CALIBRATION_AUC_HIGH,
    MIN_SAMPLES_PLATT, MIN_SAMPLES_ISOTONIC,
    FIXED_THRESHOLD, MIN_RECALL_CONSTRAINT,
    USE_REGIME_SPECIFIC_THRESHOLDS, REGIME_THRESHOLD_ADJUSTMENTS,
    MIN_SAMPLES_FEATURE_SELECTION, FEATURE_IMPORTANCE_TYPE,
)


# ════════════════════════════════════════════════════════════════════════════
# CALIBRATION METRICS FUNCTIONS
# ════════════════════════════════════════════════════════════════════════════

def compute_brier_score(probs, labels):
    """
    Compute Brier score: mean squared error of probability estimates.
    Brier = (1/N) * sum((prob - label)^2)
    Lower is better: 0 = perfect, 0.25 = random for balanced binary.
    """
    probs = np.asarray(probs).reshape(-1)
    labels = np.asarray(labels).reshape(-1)
    return float(np.mean((probs - labels) ** 2))


def compute_ece(probs, labels, n_bins=10):
    """
    Compute Expected Calibration Error (ECE).
    Measures average difference between predicted probability and actual frequency.
    ECE = sum_b (|B_b|/N) * |acc(B_b) - conf(B_b)|
    Lower is better: 0 = perfectly calibrated.
    """
    probs = np.asarray(probs).reshape(-1)
    labels = np.asarray(labels).reshape(-1)
    
    if len(probs) == 0:
        return 0.0
    
    bin_edges = np.linspace(0, 1, n_bins + 1)
    ece = 0.0
    
    for i in range(n_bins):
        mask = (probs >= bin_edges[i]) & (probs < bin_edges[i + 1])
        if mask.sum() == 0:
            continue
        
        bin_probs = probs[mask]
        bin_labels = labels[mask]
        
        avg_confidence = bin_probs.mean()
        avg_accuracy = bin_labels.mean()
        bin_weight = mask.sum() / len(probs)
        
        ece += bin_weight * abs(avg_accuracy - avg_confidence)
    
    return float(ece)


def compute_calibration_stats(probs_before, probs_after, labels, name='model'):
    """
    Compute calibration statistics before and after calibration.
    Returns dict with Brier, ECE, and improvement metrics.
    """
    brier_before = compute_brier_score(probs_before, labels)
    brier_after = compute_brier_score(probs_after, labels)
    ece_before = compute_ece(probs_before, labels)
    ece_after = compute_ece(probs_after, labels)
    
    return {
        'name': name,
        'brier_before': brier_before,
        'brier_after': brier_after,
        'brier_improvement': brier_before - brier_after,
        'ece_before': ece_before,
        'ece_after': ece_after,
        'ece_improvement': ece_before - ece_after,
        'n_samples': len(labels),
        'positive_rate': float(np.mean(labels)),
    }


# ════════════════════════════════════════════════════════════════════════════
# CLASS BALANCING AND SAMPLE WEIGHTING
# ════════════════════════════════════════════════════════════════════════════

def calculate_scale_pos_weight(labels, verbose=False):
    """Calculate class weight for imbalanced data."""
    if not USE_CLASS_BALANCING:
        return 1.0
    
    labels_arr = labels.values if hasattr(labels, 'values') else np.array(labels)
    n_positive = (labels_arr == 1).sum()
    n_negative = (labels_arr == 0).sum()
    n_total = len(labels_arr)
    
    if n_total < MIN_SAMPLES_CLASS_BALANCING:
        return 1.0
    if n_positive == 0 or n_negative == 0:
        return 1.0
    
    weight = n_negative / n_positive
    weight = max(0.1, min(10.0, weight))
    
    if verbose:
        pos_pct = n_positive / n_total * 100
        print(f"    [ClassBalance] Pos: {n_positive} ({pos_pct:.1f}%) → weight={weight:.3f}")
    
    return weight


def calculate_half_life_weights(n_samples, half_life=None, min_weight=0.1, verbose=False):
    """
    Calculate exponential decay sample weights giving more importance to recent samples.
    
    Formula: weight[i] = exp(-ln(2) * (n_samples - 1 - i) / half_life)
    
    This gives:
      - Most recent sample (i = n_samples-1): weight = 1.0
      - Sample from half_life ago: weight = 0.5
      - Oldest sample (i = 0): weight = exp(-ln(2) * (n_samples-1) / half_life)
    
    Args:
        n_samples: Number of training samples
        half_life: Number of samples for weight to decay to 50% (default: n_samples/2)
        min_weight: Floor to prevent near-zero weights (default: 0.1)
        verbose: Print weight statistics
    
    Returns:
        np.array of sample weights, length n_samples
    
    Note: Works ALONGSIDE class balancing - CatBoost multiplies sample_weight * scale_pos_weight
    """
    if not USE_HALF_LIFE_WEIGHTING:
        return None  # No sample weights, CatBoost uses default (all 1.0)
    
    if half_life is None:
        half_life = HALF_LIFE_SAMPLES
    
    if half_life <= 0:
        return None
    
    # Calculate decay for each sample position
    # Index 0 = oldest, index n_samples-1 = most recent
    positions = np.arange(n_samples)
    age = n_samples - 1 - positions  # Age: most recent = 0, oldest = n_samples-1
    
    # Exponential decay: weight = exp(-ln(2) * age / half_life)
    decay_rate = np.log(2) / half_life
    weights = np.exp(-decay_rate * age)
    
    # Apply floor to prevent near-zero weights
    weights = np.maximum(weights, min_weight)
    
    if verbose:
        print(f"    [HalfLife] n={n_samples}, half_life={half_life}")
        print(f"    [HalfLife] Weights: oldest={weights[0]:.3f}, median={np.median(weights):.3f}, newest={weights[-1]:.3f}")
    
    return weights


# ════════════════════════════════════════════════════════════════════════════
# PROBABILITY CALIBRATION
# ════════════════════════════════════════════════════════════════════════════

def calibrate_probabilities_adaptive(val_probs, val_labels, pred_probs, 
                                      method='auto', cal_auc=None, verbose=False):
    """
    Calibrate probabilities using appropriate method based on sample size and model skill.
    
    Methods:
      - 'platt': Sigmoid/Platt scaling (works with 100+ samples)
      - 'isotonic': Isotonic regression (needs 500+ samples, 200+ positives)
      - 'auto': Choose based on sample size
      - 'none': Return uncalibrated probabilities
    
    Conditional calibration (USE_PROBABILITY_CALIBRATION == 'conditional'):
      - Only calibrate if AUC < CALIBRATION_AUC_LOW (very weak) 
        OR AUC > CALIBRATION_AUC_HIGH (strong signal)
      - Skip calibration in the "moderate skill" zone where it hurts
    
    REFERENCES:
      - Platt (1999): "Probabilistic Outputs for SVMs"
      - IJCAI: Isotonic needs many samples to avoid overfitting
    """
    # Handle conditional calibration based on model skill
    if USE_PROBABILITY_CALIBRATION == 'conditional' and cal_auc is not None:
        if CALIBRATION_AUC_LOW < cal_auc < CALIBRATION_AUC_HIGH:
            if verbose:
                print(f"    [Calibration] SKIP: CAL AUC={cal_auc:.3f} in 'hurt zone' ({CALIBRATION_AUC_LOW}-{CALIBRATION_AUC_HIGH})")
            return pred_probs, None, 'none'
        elif cal_auc <= CALIBRATION_AUC_LOW:
            if verbose:
                print(f"    [Calibration] Enabled: Very weak signal (AUC={cal_auc:.3f} < {CALIBRATION_AUC_LOW})")
        else:
            if verbose:
                print(f"    [Calibration] Enabled: Strong signal (AUC={cal_auc:.3f} > {CALIBRATION_AUC_HIGH})")
    elif USE_PROBABILITY_CALIBRATION == False or method == 'none':
        return pred_probs, None, 'none'
    
    n_val = len(val_labels)
    n_positive = np.sum(val_labels)
    unique_labels = np.unique(val_labels)
    
    # Need both classes
    if len(unique_labels) < 2:
        if verbose:
            print(f"    [Calibration] SKIP: Only 1 class in validation")
        return pred_probs, None, 'none'
    
    # Auto-select method based on sample size
    if method == 'auto':
        if n_positive >= 200 and n_val >= MIN_SAMPLES_ISOTONIC:
            method = 'isotonic'
        elif n_val >= MIN_SAMPLES_PLATT:
            method = 'platt'
        else:
            if verbose:
                print(f"    [Calibration] SKIP: Only {n_val} val samples (need {MIN_SAMPLES_PLATT})")
            return pred_probs, None, 'none'
    
    try:
        if method == 'isotonic':
            # Isotonic regression - non-parametric, needs many samples
            calibrator = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds='clip')
            calibrator.fit(val_probs, val_labels)
            calibrated = calibrator.predict(pred_probs.reshape(-1))
            if verbose:
                print(f"    [Calibration] Isotonic ({n_val} samples, {int(n_positive)} pos)")
        else:
            # Platt/Sigmoid - parametric, robust for smaller samples
            # FIT on CAL probs + labels, PREDICT on PRED probs
            calibrator = LogisticRegression(solver='lbfgs', max_iter=1000)
            calibrator.fit(val_probs.reshape(-1, 1), val_labels)
            calibrated = calibrator.predict_proba(pred_probs.reshape(-1, 1))[:, 1]
            if verbose:
                print(f"    [Calibration] Platt/Sigmoid ({n_val} samples)")
        
        calibrated = np.clip(calibrated, 1e-8, 1 - 1e-8)
        return calibrated, calibrator, method
        
    except Exception as e:
        if verbose:
            print(f"    [Calibration] FAILED: {e}")
        return pred_probs, None, 'none'


# ════════════════════════════════════════════════════════════════════════════
# THRESHOLD CALCULATION
# ════════════════════════════════════════════════════════════════════════════

def calculate_optimal_threshold(val_probs, val_labels, method='youden_j', verbose=False, regime_pos_rate=None):
    """
    Calculate optimal classification threshold from validation data.
    
    Methods:
      - 'class_balanced': threshold = positive_rate (ensures ~balanced predictions)
      - 'youden_j': maximize Youden's J = TPR - FPR (optimal cutoff point)
      - 'f1_optimal': maximize F1 score
      - 'fixed': use FIXED_THRESHOLD
      - 'adaptive': use past prediction mistakes
    
    Args:
      regime_pos_rate: Optional override for positive rate. When provided, this
                       value (from current regime's historical rate) is used
                       instead of the CAL set's actual positive rate. This helps
                       when CAL and PRED are in different regimes.
    
    RATIONALE:
      - With imbalanced classes, 0.5 threshold is NOT optimal
      - Youden's J finds the point that maximizes separation
      - Class-balanced threshold ensures we predict both classes
    """
    val_probs_arr = np.array(val_probs)
    val_labels_arr = np.array(val_labels)
    
    if method == 'fixed':
        return FIXED_THRESHOLD
    
    if method == 'class_balanced':
        # Threshold = positive rate → predicts ~same % as actual
        # Use regime_pos_rate if provided (aligns threshold with PRED regime)
        if regime_pos_rate is not None:
            pos_rate = regime_pos_rate
            source = f"regime_pos_rate={regime_pos_rate:.3f}"
        else:
            pos_rate = np.mean(val_labels_arr)
            source = f"cal_pos_rate={pos_rate:.3f}"
        threshold = pos_rate
        if verbose:
            print(f"    [Threshold] Class-balanced: {threshold:.3f} ({source})")
        return threshold
    
    if method == 'quantile_match':
        # Set threshold so we predict same % of positives as validation has
        # This is the key fix for calibrated probabilities
        # Use regime_pos_rate if provided (aligns threshold with PRED regime)
        if regime_pos_rate is not None:
            pos_rate = regime_pos_rate
            source = f"regime_pos_rate={regime_pos_rate:.3f}"
        else:
            pos_rate = np.mean(val_labels_arr)
            source = f"cal_pos_rate={pos_rate:.3f}"
        # If we want to predict pos_rate% as positive, we need the (1-pos_rate) quantile
        threshold = np.percentile(val_probs_arr, (1 - pos_rate) * 100)
        if verbose:
            n_pred_pos = (val_probs_arr >= threshold).sum()
            print(f"    [Threshold] Quantile-match: {threshold:.3f} ({source}, predicts {n_pred_pos}/{len(val_probs_arr)} = {n_pred_pos/len(val_probs_arr):.1%} pos)")
        return threshold
    
    if method in ['youden_j', 'f1_optimal', 'precision_optimal']:
        # Search for optimal threshold
        thresholds = np.linspace(0.3, 0.7, 41)  # 0.30 to 0.70 in 0.01 steps
        best_threshold = 0.5
        best_score = -np.inf
        
        for thresh in thresholds:
            preds = (val_probs_arr >= thresh).astype(int)
            
            tp = ((preds == 1) & (val_labels_arr == 1)).sum()
            tn = ((preds == 0) & (val_labels_arr == 0)).sum()
            fp = ((preds == 1) & (val_labels_arr == 0)).sum()
            fn = ((preds == 0) & (val_labels_arr == 1)).sum()
            
            # Avoid division by zero
            tpr = tp / (tp + fn) if (tp + fn) > 0 else 0
            fpr = fp / (fp + tn) if (fp + tn) > 0 else 0
            precision = tp / (tp + fp) if (tp + fp) > 0 else 0
            recall = tpr
            
            if method == 'youden_j':
                # Youden's J = Sensitivity + Specificity - 1 = TPR - FPR
                score = tpr - fpr
            elif method == 'precision_optimal':
                # Maximize precision (TP/FP ratio) but require minimum recall
                # This prevents threshold from going too high and missing all positives
                if recall >= MIN_RECALL_CONSTRAINT and (tp + fp) >= 5:
                    score = precision
                else:
                    score = -1  # Invalid: not enough recall or too few predictions
            else:  # f1_optimal
                # F1 = 2 * precision * recall / (precision + recall)
                score = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
            
            if score > best_score:
                best_score = score
                best_threshold = thresh
        
        if verbose:
            print(f"    [Threshold] {method}: {best_threshold:.3f} (score={best_score:.3f})")
        return best_threshold
    
    # Default fallback
    return 0.5


def adjust_threshold_for_regime(base_threshold, vol_regime, base_rate=0.5, verbose=False):
    """
    Adjust classification threshold based on volatility regime.
    
    Intuition:
      - In HIGH volatility, predictions are less reliable
        → INCREASE threshold to make it HARDER to predict UP (more conservative)
      - In LOW volatility, conditions are favorable for UP
        → DECREASE threshold slightly to capture extra trades (bullish boost)
    
    Args:
        base_threshold: The standard threshold from calculate_optimal_threshold
        vol_regime: One of 'LOW', 'MEDIUM', 'HIGH', 'VERY_HIGH', 'EXTREME'
        base_rate: The base positive rate (default 0.5)
        verbose: Print adjustment details
    
    Returns:
        Adjusted threshold (higher = harder to buy, lower = easier to buy)
    """
    if not USE_REGIME_SPECIFIC_THRESHOLDS:
        return base_threshold
    
    adjustment = REGIME_THRESHOLD_ADJUSTMENTS.get(vol_regime, 0.0)
    
    if adjustment == 0.0:
        return base_threshold
    
    # Apply adjustment: positive = harder to buy, negative = easier to buy
    adjusted = base_threshold + adjustment
    
    # Cap at reasonable bounds
    adjusted = max(0.35, min(adjusted, 0.85))  # Don't go below 0.35 or above 0.85
    
    if verbose:
        if adjustment > 0:
            print(f"    [RegimeThresh] {vol_regime}: {base_threshold:.3f} + {adjustment:.3f} = {adjusted:.3f} (harder to buy)")
        else:
            print(f"    [RegimeThresh] {vol_regime}: {base_threshold:.3f} {adjustment:.3f} = {adjusted:.3f} (bullish boost)")
    
    return adjusted


# ════════════════════════════════════════════════════════════════════════════
# FEATURE SELECTION
# ════════════════════════════════════════════════════════════════════════════

def select_top_features(model, feature_names, top_percent, n_train_samples, verbose=False):
    """Select top N% features based on importance."""
    if top_percent is None or top_percent >= 100:
        return feature_names
    
    if n_train_samples < MIN_SAMPLES_FEATURE_SELECTION:
        if verbose:
            print(f"    [FeatureSel] SKIP: Only {n_train_samples} samples")
        return feature_names
    
    importance = model.get_feature_importance(type=FEATURE_IMPORTANCE_TYPE)
    feat_imp = list(zip(feature_names, importance))
    feat_imp.sort(key=lambda x: x[1], reverse=True)
    n_keep = max(1, int(len(feature_names) * top_percent / 100))
    
    return [f[0] for f in feat_imp[:n_keep]]
