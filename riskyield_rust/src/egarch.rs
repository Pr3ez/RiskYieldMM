//! EGARCH (Exponential GARCH) asymmetric volatility helper
//! 
//! Captures leverage effect (negative returns increase volatility more).
//! Uses grid search + log-likelihood for parameter estimation.

use rayon::prelude::*;
use std::f64::consts::PI;

/// EGARCH parameters
#[derive(Clone, Copy, Debug)]
pub struct EGARCHParams {
    pub omega: f64,   // Log variance intercept
    pub alpha: f64,   // ARCH coefficient (magnitude)
    pub gamma: f64,   // Leverage coefficient (asymmetry)
    pub beta: f64,    // GARCH coefficient (persistence)
}

impl Default for EGARCHParams {
    fn default() -> Self {
        EGARCHParams {
            omega: 0.0,
            alpha: 0.1,
            gamma: -0.1,
            beta: 0.85,
        }
    }
}

/// E[|ε|] for standard normal ≈ √(2/π)
const EXPECTED_ABS_NORMAL: f64 = 0.7978845608;

/// Compute EGARCH log-likelihood.
/// 
/// ln(σ²_t) = ω + α*(|ε_{t-1}| - E|ε|) + γ*ε_{t-1} + β*ln(σ²_{t-1})
/// 
/// where ε_t = r_t / σ_t (standardized residual)
fn egarch_log_likelihood(
    residuals: &[f64],
    omega: f64,
    alpha: f64,
    gamma: f64,
    beta: f64,
) -> f64 {
    let n = residuals.len();
    if n < 2 {
        return f64::NEG_INFINITY;
    }
    
    // Initialize log variance with sample variance
    let var_sample: f64 = residuals.iter()
        .map(|&r| r * r)
        .sum::<f64>() / n as f64;
    
    if var_sample <= 0.0 {
        return f64::NEG_INFINITY;
    }
    
    let mut log_var = var_sample.ln();
    let mut ll = 0.0;
    
    for t in 1..n {
        // Standardized residual at t-1
        let var_prev = if log_var > -20.0 { log_var.exp() } else { 1e-10 };
        let std_resid = if var_prev > 1e-10 {
            residuals[t - 1] / var_prev.sqrt()
        } else {
            0.0
        };
        
        // EGARCH recursion
        log_var = omega
            + alpha * (std_resid.abs() - EXPECTED_ABS_NORMAL)
            + gamma * std_resid
            + beta * log_var;
        
        // Clip for numerical stability
        log_var = log_var.clamp(-20.0, 10.0);
        
        // Gaussian log-likelihood contribution
        let var_t = log_var.exp();
        ll += -0.5 * ((2.0 * PI).ln() + log_var + residuals[t].powi(2) / var_t);
    }
    
    ll
}

/// Grid search for EGARCH parameters.
/// 
/// Parallelized using rayon for speed.
pub fn estimate_egarch_params(returns: &[f64]) -> EGARCHParams {
    let n = returns.len();
    if n < 30 {
        return EGARCHParams::default();
    }
    
    // Demean returns
    let mean_ret: f64 = returns.iter().sum::<f64>() / n as f64;
    let resid: Vec<f64> = returns.iter().map(|&r| r - mean_ret).collect();
    
    let var_sample: f64 = resid.iter().map(|&r| r * r).sum::<f64>() / n as f64;
    if var_sample <= 1e-10 {
        return EGARCHParams::default();
    }
    
    // Grid search parameters
    let gamma_grid: [f64; 5] = [-0.2, -0.1, -0.05, 0.0, 0.05];
    let beta_grid: [f64; 5] = [0.7, 0.8, 0.85, 0.9, 0.95];
    let alpha_grid: [f64; 4] = [0.05, 0.1, 0.15, 0.2];
    
    // Generate all combinations
    let mut combos: Vec<(f64, f64, f64)> = Vec::with_capacity(100);
    for &gamma in &gamma_grid {
        for &beta in &beta_grid {
            for &alpha in &alpha_grid {
                combos.push((gamma, beta, alpha));
            }
        }
    }
    
    // Evaluate in parallel
    let best = combos.par_iter()
        .map(|&(gamma, beta, alpha)| {
            // Compute implied omega for stationarity
            let omega = (1.0 - beta) * var_sample.ln();
            
            let ll = egarch_log_likelihood(&resid, omega, alpha, gamma, beta);
            
            (ll, EGARCHParams { omega, alpha, gamma, beta })
        })
        .reduce(
            || (f64::NEG_INFINITY, EGARCHParams::default()),
            |a, b| if a.0 > b.0 { a } else { b }
        );
    
    best.1
}

/// Compute EGARCH volatility series given parameters.
pub fn compute_egarch_vol(
    returns: &[f64],
    params: &EGARCHParams,
) -> (Vec<f64>, Vec<f64>) {
    let n = returns.len();
    let mut vol = vec![0.0; n];
    let mut log_vol = vec![0.0; n];
    
    if n == 0 {
        return (vol, log_vol);
    }
    
    // Initialize with unconditional variance
    let var_sample: f64 = returns.iter()
        .map(|&r| r * r)
        .sum::<f64>() / n as f64;
    
    let uncond_log_var = if params.beta.abs() < 0.999 {
        params.omega / (1.0 - params.beta)
    } else {
        var_sample.ln()
    };
    
    let mut log_var = uncond_log_var;
    
    for t in 0..n {
        // Update log variance
        if t > 0 {
            let var_prev = if log_var > -20.0 { log_var.exp() } else { 1e-10 };
            let std_resid = if var_prev > 1e-10 && returns[t-1].is_finite() {
                returns[t - 1] / var_prev.sqrt()
            } else {
                0.0
            };
            
            log_var = params.omega
                + params.alpha * (std_resid.abs() - EXPECTED_ABS_NORMAL)
                + params.gamma * std_resid
                + params.beta * log_var;
            
            log_var = log_var.clamp(-20.0, 10.0);
        }
        
        log_vol[t] = log_var;
        vol[t] = (log_var * 0.5).exp();  // σ = exp(ln(σ²)/2)
    }
    
    (vol, log_vol)
}

/// Output structure for EGARCH features
#[derive(Clone)]
pub struct EGARCHFeatures {
    pub vol: Vec<f64>,
    pub log_vol: Vec<f64>,
    pub asymmetry: Vec<f64>,
    pub persistence: Vec<f64>,
    pub news_impact: Vec<f64>,
    pub vol_zscore: Vec<f64>,
    pub vol_regime: Vec<f64>,
    pub leverage_active: Vec<f64>,
}

impl EGARCHFeatures {
    fn new(n: usize) -> Self {
        EGARCHFeatures {
            vol: vec![f64::NAN; n],
            log_vol: vec![f64::NAN; n],
            asymmetry: vec![f64::NAN; n],
            persistence: vec![f64::NAN; n],
            news_impact: vec![0.0; n],
            vol_zscore: vec![0.0; n],
            vol_regime: vec![1.0; n],  // Default NORMAL
            leverage_active: vec![0.0; n],
        }
    }
}

/// Configuration for EGARCH estimation
pub struct EGARCHConfig {
    pub rolling_window: usize,
    pub low_vol_percentile: f64,
    pub high_vol_percentile: f64,
    pub recent_shock_window: usize,
}

impl Default for EGARCHConfig {
    fn default() -> Self {
        EGARCHConfig {
            rolling_window: 126,
            low_vol_percentile: 25.0,
            high_vol_percentile: 75.0,
            recent_shock_window: 5,
        }
    }
}

/// Compute EGARCH features using rolling parameter estimation.
pub fn egarch_rolling_transform(
    returns: &[f64],
    config: &EGARCHConfig,
    fitted_params: &EGARCHParams,
    low_vol_threshold: f64,
    high_vol_threshold: f64,
) -> EGARCHFeatures {
    let n = returns.len();
    let window = config.rolling_window;
    
    if n < window {
        return EGARCHFeatures::new(n);
    }
    
    // Compute volatility using FITTED params (constant across samples)
    let (vol_series, log_vol_series) = compute_egarch_vol(returns, fitted_params);
    
    // Build output
    let mut features = EGARCHFeatures::new(n);
    
    // Copy volatility series
    for t in 0..n {
        features.vol[t] = vol_series[t];
        features.log_vol[t] = log_vol_series[t];
        features.asymmetry[t] = fitted_params.gamma;
        features.persistence[t] = fitted_params.beta;
    }
    
    // Compute news impact per sample
    for t in 1..n {
        if returns[t-1].is_finite() && vol_series[t-1] > 1e-10 {
            let std_resid = returns[t-1] / vol_series[t-1];
            features.news_impact[t] = fitted_params.alpha * (std_resid.abs() - EXPECTED_ABS_NORMAL)
                + fitted_params.gamma * std_resid;
        }
    }
    
    // Compute vol z-score (causal expanding, no look-ahead)
    let mut count = 0.0;
    let mut sum_v = 0.0;
    let mut sum_sq = 0.0;
    for t in 0..n {
        let v = vol_series[t];
        if v.is_finite() && v > 0.0 {
            count += 1.0;
            sum_v += v;
            sum_sq += v * v;
            let mean = sum_v / count;
            let var = (sum_sq / count - mean * mean).max(1e-10);
            let std = var.sqrt().max(1e-8);
            features.vol_zscore[t] = (v - mean) / std;
        }
    }
    
    // Vol regime classification
    for t in 0..n {
        if vol_series[t] < low_vol_threshold {
            features.vol_regime[t] = 0.0;  // LOW
        } else if vol_series[t] > high_vol_threshold {
            features.vol_regime[t] = 2.0;  // HIGH
        } else {
            features.vol_regime[t] = 1.0;  // NORMAL
        }
    }
    
    // Leverage active: recent negative shock (use expanding ret std)
    let mut ret_std_series = vec![1e-8; n];
    let mut r_count = 0.0;
    let mut r_sum = 0.0;
    let mut r_sum_sq = 0.0;
    for t in 0..n {
        let r = returns[t];
        if r.is_finite() {
            r_count += 1.0;
            r_sum += r;
            r_sum_sq += r * r;
            let mean = r_sum / r_count;
            let var = (r_sum_sq / r_count - mean * mean).max(1e-10);
            ret_std_series[t] = var.sqrt().max(1e-8);
        } else if t > 0 {
            ret_std_series[t] = ret_std_series[t - 1];
        }
    }
    
    let shock_window = config.recent_shock_window;
    for t in shock_window..n {
        let recent = &returns[t - shock_window + 1..=t];
        let ret_std = ret_std_series[t];
        let has_neg_shock = recent.iter()
            .any(|&r| r.is_finite() && r < -ret_std);
        features.leverage_active[t] = if has_neg_shock { 1.0 } else { 0.0 };
    }
    
    features
}

/// Rolling EGARCH with per-sample parameter re-estimation.
/// 
/// This is the SLOW but accurate version that re-estimates parameters
/// for each rolling window. Use for maximum accuracy.
pub fn egarch_rolling_transform_full(
    returns: &[f64],
    config: &EGARCHConfig,
) -> EGARCHFeatures {
    let n = returns.len();
    let window = config.rolling_window;
    
    if n < window {
        return EGARCHFeatures::new(n);
    }
    
    // Compute rolling parameters in parallel
    let rolling_results: Vec<(EGARCHParams, f64, f64)> = (window..n)
        .into_par_iter()
        .map(|t| {
            let win_start = t - window;
            let win_returns: Vec<f64> = returns[win_start..t]
                .iter()
                .filter(|&&r| r.is_finite())
                .copied()
                .collect();
            
            if win_returns.len() < 30 {
                return (EGARCHParams::default(), f64::NAN, f64::NAN);
            }
            
            // Estimate parameters
            let params = estimate_egarch_params(&win_returns);
            
            // Compute volatility at current point
            let (vol, log_vol) = compute_egarch_vol(&win_returns, &params);
            let last_vol = *vol.last().unwrap_or(&f64::NAN);
            let last_log_vol = *log_vol.last().unwrap_or(&f64::NAN);
            
            (params, last_vol, last_log_vol)
        })
        .collect();
    
    // Build output
    let mut features = EGARCHFeatures::new(n);
    
    // Compute volatility thresholds from first window
    let first_window: Vec<f64> = returns[..window]
        .iter()
        .filter(|&&r| r.is_finite())
        .copied()
        .collect();
    
    let (low_thresh, high_thresh) = if !first_window.is_empty() {
        let init_params = estimate_egarch_params(&first_window);
        let (vol, _) = compute_egarch_vol(&first_window, &init_params);
        let mut sorted_vol: Vec<f64> = vol.iter()
            .filter(|&&v| v.is_finite() && v > 0.0)
            .copied()
            .collect();
        sorted_vol.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
        
        let low_idx = (config.low_vol_percentile / 100.0 * sorted_vol.len() as f64) as usize;
        let high_idx = (config.high_vol_percentile / 100.0 * sorted_vol.len() as f64) as usize;
        
        (
            sorted_vol.get(low_idx).copied().unwrap_or(0.01),
            sorted_vol.get(high_idx.min(sorted_vol.len().saturating_sub(1))).copied().unwrap_or(0.03),
        )
    } else {
        (0.01, 0.03)
    };
    
    // Fill results
    for (i, &(params, vol, log_vol)) in rolling_results.iter().enumerate() {
        let t = window + i;
        
        features.vol[t] = vol;
        features.log_vol[t] = log_vol;
        features.asymmetry[t] = params.gamma;
        features.persistence[t] = params.beta;
        
        // Vol regime
        if vol.is_finite() {
            if vol < low_thresh {
                features.vol_regime[t] = 0.0;
            } else if vol > high_thresh {
                features.vol_regime[t] = 2.0;
            } else {
                features.vol_regime[t] = 1.0;
            }
        }
    }
    
    // Compute news impact and other per-sample features
    for t in 1..n {
        if features.vol[t].is_finite() && features.vol[t-1].is_finite() && features.vol[t-1] > 1e-10 {
            if returns[t-1].is_finite() {
                let std_resid = returns[t-1] / features.vol[t-1];
                let gamma = features.asymmetry[t];
                let alpha = 0.1;  // Use typical alpha for news impact
                features.news_impact[t] = alpha * (std_resid.abs() - EXPECTED_ABS_NORMAL)
                    + gamma * std_resid;
            }
        }
    }
    
    // Vol z-score (causal expanding, no look-ahead)
    let mut count = 0.0;
    let mut sum_v = 0.0;
    let mut sum_sq = 0.0;
    for t in 0..n {
        let v = features.vol[t];
        if v.is_finite() && v > 0.0 {
            count += 1.0;
            sum_v += v;
            sum_sq += v * v;
            let mean = sum_v / count;
            let var = (sum_sq / count - mean * mean).max(1e-10);
            let std = var.sqrt().max(1e-8);
            features.vol_zscore[t] = (v - mean) / std;
        }
    }
    
    // Leverage active (use expanding ret std, no look-ahead)
    let mut ret_std_series = vec![1e-8; n];
    let mut r_count = 0.0;
    let mut r_sum = 0.0;
    let mut r_sum_sq = 0.0;
    for t in 0..n {
        let r = returns[t];
        if r.is_finite() {
            r_count += 1.0;
            r_sum += r;
            r_sum_sq += r * r;
            let mean = r_sum / r_count;
            let var = (r_sum_sq / r_count - mean * mean).max(1e-10);
            ret_std_series[t] = var.sqrt().max(1e-8);
        } else if t > 0 {
            ret_std_series[t] = ret_std_series[t - 1];
        }
    }
    
    let shock_window = config.recent_shock_window;
    for t in shock_window..n {
        let recent = &returns[t - shock_window + 1..=t];
        let ret_std = ret_std_series[t];
        let has_neg_shock = recent.iter()
            .any(|&r| r.is_finite() && r < -ret_std);
        features.leverage_active[t] = if has_neg_shock { 1.0 } else { 0.0 };
    }
    
    // Fill early values
    if window < n && features.vol[window].is_finite() {
        for t in 0..window {
            features.vol[t] = features.vol[window];
            features.log_vol[t] = features.log_vol[window];
            features.asymmetry[t] = features.asymmetry[window];
            features.persistence[t] = features.persistence[window];
            features.vol_regime[t] = features.vol_regime[window];
        }
    }
    
    features
}

#[cfg(test)]
mod tests {
    use super::*;
    
    #[test]
    fn test_egarch_ll() {
        let returns: Vec<f64> = (0..100)
            .map(|i| ((i as f64 * 0.1).sin() * 0.02))
            .collect();
        
        let ll = egarch_log_likelihood(&returns, 0.0, 0.1, -0.1, 0.85);
        assert!(ll.is_finite());
        assert!(ll < 0.0);  // Log-likelihood should be negative
    }
    
    #[test]
    fn test_param_estimation() {
        let returns: Vec<f64> = (0..200)
            .map(|i| ((i as f64 * 0.1).sin() * 0.02))
            .collect();
        
        let params = estimate_egarch_params(&returns);
        
        assert!(params.alpha.is_finite());
        assert!(params.beta.is_finite());
        assert!(params.gamma.is_finite());
        assert!(params.beta > 0.5);  // Should have high persistence
    }
}
