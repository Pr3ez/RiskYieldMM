//! OU (Ornstein-Uhlenbeck / AR(1)) rolling estimation
//! 
//! Estimates mean-reversion strength using rolling window AR(1) model.
//! Each sample t gets AR(1) coefficient estimated from window [t-w:t].

use rayon::prelude::*;

/// Estimate AR(1) coefficient from a window of data using OLS.
/// 
/// x_t = φ * x_{t-1} + ε_t
/// φ = Cov(x_t, x_{t-1}) / Var(x_{t-1})
#[inline]
fn estimate_ar1(window: &[f64]) -> f64 {
    let n = window.len();
    if n < 3 {
        return 0.9; // Default fallback
    }
    
    // Compute mean of lagged series (x_{t-1})
    let n_pairs = n - 1;
    let mut sum_lag = 0.0;
    let mut sum_curr = 0.0;
    
    for i in 0..n_pairs {
        sum_lag += window[i];
        sum_curr += window[i + 1];
    }
    
    let mean_lag = sum_lag / n_pairs as f64;
    let mean_curr = sum_curr / n_pairs as f64;
    
    // Compute Cov(x_t, x_{t-1}) and Var(x_{t-1})
    let mut cov = 0.0;
    let mut var_lag = 0.0;
    
    for i in 0..n_pairs {
        let dev_lag = window[i] - mean_lag;
        let dev_curr = window[i + 1] - mean_curr;
        cov += dev_lag * dev_curr;
        var_lag += dev_lag * dev_lag;
    }
    
    if var_lag < 1e-10 {
        return 0.9; // Avoid division by near-zero
    }
    
    let phi = cov / var_lag;
    phi.clamp(-0.999, 0.999)
}

/// Convert AR(1) coefficient to mean-reversion speed κ.
/// κ = -ln(φ)
#[inline]
fn phi_to_kappa(phi: f64) -> f64 {
    if phi <= 0.0 {
        return 10.0; // Very fast mean reversion
    }
    if phi >= 1.0 {
        return 0.001; // No mean reversion (unit root)
    }
    (-phi.ln()).clamp(0.001, 10.0)
}

/// Convert AR(1) coefficient to half-life.
/// t_{1/2} = ln(2) / κ
#[inline]
fn phi_to_halflife(phi: f64) -> f64 {
    let kappa = phi_to_kappa(phi);
    (0.693147 / kappa).clamp(0.1, 1000.0)
}

/// Rolling statistics for z-score calculation
struct RollingStats {
    mean: f64,
    std: f64,
}

impl RollingStats {
    fn compute(window: &[f64]) -> Self {
        let n = window.len() as f64;
        if n < 2.0 {
            return RollingStats { mean: 0.0, std: 1.0 };
        }
        
        let sum: f64 = window.iter().sum();
        let mean = sum / n;
        
        let var: f64 = window.iter()
            .map(|&x| (x - mean).powi(2))
            .sum::<f64>() / n;
        
        RollingStats {
            mean,
            std: var.sqrt().max(1e-8),
        }
    }
}

/// Output structure for OU features
#[derive(Clone)]
pub struct OUFeatures {
    pub phi: Vec<f64>,
    pub kappa: Vec<f64>,
    pub halflife: Vec<f64>,
    pub zscore: Vec<f64>,
    pub zscore_abs: Vec<f64>,
    pub is_stationary: Vec<f64>,
    pub halflife_regime: Vec<f64>,
    pub reverting: Vec<f64>,
}

impl OUFeatures {
    fn new(n: usize) -> Self {
        OUFeatures {
            phi: vec![f64::NAN; n],
            kappa: vec![f64::NAN; n],
            halflife: vec![f64::NAN; n],
            zscore: vec![f64::NAN; n],
            zscore_abs: vec![f64::NAN; n],
            is_stationary: vec![f64::NAN; n],
            halflife_regime: vec![f64::NAN; n],
            reverting: vec![0.0; n],
        }
    }
}

/// Configuration for OU rolling estimation
pub struct OUConfig {
    pub rolling_window: usize,
    pub zscore_window: usize,
    pub min_halflife: f64,
    pub max_halflife: f64,
    pub phi_stationarity_threshold: f64,
}

impl Default for OUConfig {
    fn default() -> Self {
        OUConfig {
            rolling_window: 63,
            zscore_window: 21,
            min_halflife: 2.0,
            max_halflife: 50.0,
            phi_stationarity_threshold: 0.99,
        }
    }
}

/// Compute OU features using rolling AR(1) estimation.
/// 
/// This is the main entry point for OU feature generation.
/// Parallelized using rayon for performance.
pub fn ou_rolling_transform(
    series: &[f64],
    config: &OUConfig,
) -> OUFeatures {
    let n = series.len();
    let window = config.rolling_window;
    let zscore_window = config.zscore_window;
    
    if n < window {
        return OUFeatures::new(n);
    }
    
    // Compute AR(1) parameters in parallel
    let ar1_results: Vec<(f64, f64, f64)> = (window..n)
        .into_par_iter()
        .map(|t| {
            let win_start = t - window;
            let win_data = &series[win_start..t];
            
            // Filter NaN values
            let clean: Vec<f64> = win_data.iter()
                .filter(|x| x.is_finite())
                .copied()
                .collect();
            
            if clean.len() < 10 {
                return (0.9, phi_to_kappa(0.9), phi_to_halflife(0.9));
            }
            
            let phi = estimate_ar1(&clean);
            let kappa = phi_to_kappa(phi);
            let halflife = phi_to_halflife(phi);
            
            (phi, kappa, halflife)
        })
        .collect();
    
    // Build output
    let mut features = OUFeatures::new(n);
    
    // Fill AR(1) features
    for (i, &(phi, kappa, halflife)) in ar1_results.iter().enumerate() {
        let t = window + i;
        features.phi[t] = phi;
        features.kappa[t] = kappa;
        features.halflife[t] = halflife;
        
        // Stationarity
        features.is_stationary[t] = if phi.abs() < config.phi_stationarity_threshold {
            1.0
        } else {
            0.0
        };
        
        // Half-life regime
        features.halflife_regime[t] = if halflife < config.min_halflife {
            0.0 // TOO_FAST
        } else if halflife > config.max_halflife {
            2.0 // TOO_SLOW
        } else {
            1.0 // OPTIMAL
        };
    }
    
    // Compute z-scores (sequential due to dependency on previous z-score)
    for t in zscore_window..n {
        let win_start = t - zscore_window;
        let win_data = &series[win_start..t];
        
        let stats = RollingStats::compute(win_data);
        
        if series[t].is_finite() {
            let z = (series[t] - stats.mean) / stats.std;
            features.zscore[t] = z;
            features.zscore_abs[t] = z.abs();
            
            // Reverting: z and delta_z have opposite signs
            if t > 0 && series[t - 1].is_finite() {
                let z_prev = (series[t - 1] - stats.mean) / stats.std;
                let delta_z = z - z_prev;
                features.reverting[t] = if z * delta_z < 0.0 { 1.0 } else { 0.0 };
            }
        }
    }
    
    // Fill early values with first valid
    if window < n && features.phi[window].is_finite() {
        let first_phi = features.phi[window];
        let first_kappa = features.kappa[window];
        let first_halflife = features.halflife[window];
        let first_stationary = features.is_stationary[window];
        let first_regime = features.halflife_regime[window];
        
        for t in 0..window {
            features.phi[t] = first_phi;
            features.kappa[t] = first_kappa;
            features.halflife[t] = first_halflife;
            features.is_stationary[t] = first_stationary;
            features.halflife_regime[t] = first_regime;
        }
    }
    
    if zscore_window < n && features.zscore[zscore_window].is_finite() {
        let first_z = features.zscore[zscore_window];
        for t in 0..zscore_window {
            features.zscore[t] = first_z;
            features.zscore_abs[t] = first_z.abs();
        }
    }
    
    features
}

#[cfg(test)]
mod tests {
    use super::*;
    
    #[test]
    fn test_ar1_estimation() {
        // AR(1) with known phi = 0.9
        let mut series = vec![0.0; 100];
        let phi_true = 0.9;
        for i in 1..100 {
            series[i] = phi_true * series[i-1] + 0.1 * (i as f64 % 3.0 - 1.0);
        }
        
        let phi_est = estimate_ar1(&series);
        assert!((phi_est - phi_true).abs() < 0.2, "phi_est={}, expected~{}", phi_est, phi_true);
    }
    
    #[test]
    fn test_ou_transform() {
        let series: Vec<f64> = (0..200).map(|i| (i as f64 * 0.1).sin()).collect();
        let config = OUConfig::default();
        
        let features = ou_rolling_transform(&series, &config);
        
        assert_eq!(features.phi.len(), 200);
        assert!(features.phi[100].is_finite());
        assert!(features.zscore[100].is_finite());
    }
}
