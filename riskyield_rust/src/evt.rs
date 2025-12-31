//! EVT POT (Extreme Value Theory - Peaks Over Threshold) helper
//! 
//! Tail risk estimation using Generalized Pareto Distribution (GPD).
//! Uses PWM (Probability Weighted Moments) estimator for speed.

use rayon::prelude::*;

/// GPD parameters
#[derive(Clone, Copy, Debug)]
pub struct GPDParams {
    pub xi: f64,    // Shape parameter (tail heaviness)
    pub beta: f64,  // Scale parameter
}

impl Default for GPDParams {
    fn default() -> Self {
        GPDParams { xi: 0.1, beta: 0.01 }
    }
}

/// Fit GPD using Probability Weighted Moments (PWM) estimator.
/// 
/// This is O(n log n) due to sorting, but much faster than MLE
/// which requires iterative optimization.
/// 
/// PWM estimator:
///   a0 = mean(exceedances)
///   a1 = Σ (i/(n-1)) * y_i[sorted] / n
///   ξ = 2 - a0 / (a0 - 2*a1)
///   β = 2 * a0 * a1 / (a0 - 2*a1)
pub fn fit_gpd_pwm(exceedances: &mut [f64]) -> GPDParams {
    let n = exceedances.len();
    if n < 5 {
        return GPDParams::default();
    }
    
    // Sort exceedances for PWM calculation
    exceedances.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
    
    // Compute a0 (mean)
    let a0: f64 = exceedances.iter().sum::<f64>() / n as f64;
    
    // Compute a1 (weighted mean)
    let n_f = n as f64;
    let n_minus_1 = (n - 1) as f64;
    let mut a1 = 0.0;
    for (i, &y) in exceedances.iter().enumerate() {
        let weight = i as f64 / n_minus_1;
        a1 += weight * y;
    }
    a1 /= n_f;
    
    // Compute parameters
    let denom = a0 - 2.0 * a1;
    
    if denom.abs() < 1e-10 {
        // Degenerate case - return exponential (xi ≈ 0)
        return GPDParams { xi: 0.0, beta: a0 };
    }
    
    let xi = 2.0 - a0 / denom;
    let beta = 2.0 * a0 * a1 / denom;
    
    // Validate and clip parameters
    let xi = xi.clamp(-0.5, 1.0);
    let beta = beta.max(1e-10);
    
    GPDParams { xi, beta }
}

/// Compute VaR at probability level p using GPD.
/// 
/// VaR_p = u + (β/ξ) * ((λ_u / (1-p))^ξ - 1)  for ξ ≠ 0
/// VaR_p = u + β * ln(λ_u / (1-p))            for ξ ≈ 0
pub fn compute_var(
    threshold: f64,
    xi: f64,
    beta: f64,
    exceedance_rate: f64,
    p: f64,
) -> f64 {
    if exceedance_rate <= 0.0 || exceedance_rate >= 1.0 {
        return threshold;
    }
    
    let tail_prob = 1.0 - p;
    if tail_prob >= exceedance_rate {
        return threshold * 0.5;
    }
    
    let var = if xi.abs() < 1e-10 {
        // Exponential case
        threshold + beta * (exceedance_rate / tail_prob).ln()
    } else {
        threshold + (beta / xi) * ((exceedance_rate / tail_prob).powf(xi) - 1.0)
    };
    
    var.clamp(0.0, 10.0)
}

/// Compute Expected Shortfall (CVaR) at probability level p.
/// 
/// ES_p = VaR_p / (1 - ξ) + (β - ξ*u) / (1 - ξ)  for ξ < 1
pub fn compute_es(
    threshold: f64,
    xi: f64,
    beta: f64,
    exceedance_rate: f64,
    p: f64,
) -> f64 {
    let var_p = compute_var(threshold, xi, beta, exceedance_rate, p);
    
    if xi >= 1.0 {
        return var_p * 1.5;  // ES is infinite for ξ ≥ 1
    }
    
    let denom = 1.0 - xi;
    let es = var_p / denom + (beta - xi * threshold) / denom;
    
    es.clamp(0.0, 20.0)
}

/// Compute tail probability P(X > x) using GPD.
pub fn compute_tail_prob(
    threshold: f64,
    xi: f64,
    beta: f64,
    exceedance_rate: f64,
    x: f64,
) -> f64 {
    if x <= threshold {
        return exceedance_rate;
    }
    
    let y = x - threshold;
    
    let survival = if xi.abs() < 1e-10 {
        (-y / beta).exp()
    } else {
        let arg = 1.0 + xi * y / beta;
        if arg <= 0.0 {
            0.0
        } else {
            arg.powf(-1.0 / xi)
        }
    };
    
    (exceedance_rate * survival).clamp(0.0, 1.0)
}

/// Percentile calculation
fn percentile(data: &mut [f64], p: f64) -> f64 {
    if data.is_empty() {
        return 0.0;
    }
    
    data.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
    
    let idx = (p / 100.0 * (data.len() - 1) as f64).round() as usize;
    let idx = idx.min(data.len() - 1);
    data[idx]
}

/// Output structure for EVT features
#[derive(Clone)]
pub struct EVTFeatures {
    pub xi: Vec<f64>,
    pub beta: Vec<f64>,
    pub exceedance_rate: Vec<f64>,
    pub var95: Vec<f64>,
    pub var99: Vec<f64>,
    pub es95: Vec<f64>,
    pub tail_prob_2std: Vec<f64>,
    pub tail_prob_3std: Vec<f64>,
    pub tail_flag: Vec<f64>,
    pub regime: Vec<f64>,
}

impl EVTFeatures {
    fn new(n: usize) -> Self {
        EVTFeatures {
            xi: vec![f64::NAN; n],
            beta: vec![f64::NAN; n],
            exceedance_rate: vec![f64::NAN; n],
            var95: vec![f64::NAN; n],
            var99: vec![f64::NAN; n],
            es95: vec![f64::NAN; n],
            tail_prob_2std: vec![f64::NAN; n],
            tail_prob_3std: vec![f64::NAN; n],
            tail_flag: vec![f64::NAN; n],
            regime: vec![f64::NAN; n],
        }
    }
}

/// Configuration for EVT POT estimation
pub struct EVTConfig {
    pub rolling_window: usize,
    pub threshold_percentile: f64,
    pub min_exceedances: usize,
    pub fat_tail_xi_threshold: f64,
    pub tail_2std_mult: f64,
    pub tail_3std_mult: f64,
    pub use_absolute: bool,
}

impl Default for EVTConfig {
    fn default() -> Self {
        EVTConfig {
            rolling_window: 252,
            threshold_percentile: 95.0,
            min_exceedances: 30,
            fat_tail_xi_threshold: 0.25,
            tail_2std_mult: 2.0,
            tail_3std_mult: 3.0,
            use_absolute: true,
        }
    }
}

/// Compute EVT features using rolling GPD estimation.
pub fn evt_rolling_transform(
    returns: &[f64],
    config: &EVTConfig,
    fitted_threshold: f64,
) -> EVTFeatures {
    let n = returns.len();
    let window = config.rolling_window;
    
    if n < window {
        return EVTFeatures::new(n);
    }
    
    // Prepare series (absolute if configured)
    let series: Vec<f64> = if config.use_absolute {
        returns.iter().map(|&x| x.abs()).collect()
    } else {
        returns.to_vec()
    };
    
    // Compute features in parallel
    let results: Vec<(GPDParams, f64, f64, f64, f64, f64, f64)> = (window..n)
        .into_par_iter()
        .map(|t| {
            let win_start = t - window;
            let window_data: Vec<f64> = series[win_start..t]
                .iter()
                .filter(|x| x.is_finite())
                .copied()
                .collect();
            
            let window_returns: Vec<f64> = returns[win_start..t]
                .iter()
                .filter(|x| x.is_finite())
                .copied()
                .collect();
            
            if window_data.len() < 50 {
                return (GPDParams::default(), 0.0, 0.0, 0.0, 0.0, 0.05, 0.01);
            }
            
            // Exceedances above threshold
            let mut exceedances: Vec<f64> = window_data.iter()
                .filter(|&&x| x > fitted_threshold)
                .map(|&x| x - fitted_threshold)
                .collect();
            
            let exceedance_rate = exceedances.len() as f64 / window_data.len() as f64;
            
            // Fit GPD
            let params = if exceedances.len() >= config.min_exceedances {
                fit_gpd_pwm(&mut exceedances)
            } else {
                GPDParams::default()
            };
            
            // Compute VaR/ES
            let var95 = if exceedance_rate > 0.0 {
                compute_var(fitted_threshold, params.xi, params.beta, exceedance_rate, 0.95)
            } else {
                let mut sorted = window_data.clone();
                sorted.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
                sorted[(sorted.len() as f64 * 0.95) as usize]
            };
            
            let var99 = compute_var(fitted_threshold, params.xi, params.beta, exceedance_rate, 0.99);
            let es95 = compute_es(fitted_threshold, params.xi, params.beta, exceedance_rate, 0.95);
            
            // Tail probabilities
            let local_std = if window_returns.len() > 1 {
                let mean: f64 = window_returns.iter().sum::<f64>() / window_returns.len() as f64;
                let var: f64 = window_returns.iter()
                    .map(|&x| (x - mean).powi(2))
                    .sum::<f64>() / window_returns.len() as f64;
                var.sqrt().max(1e-8)
            } else {
                1e-8
            };
            
            let tail_prob_2std = compute_tail_prob(
                fitted_threshold, params.xi, params.beta, exceedance_rate,
                config.tail_2std_mult * local_std,
            );
            let tail_prob_3std = compute_tail_prob(
                fitted_threshold, params.xi, params.beta, exceedance_rate,
                config.tail_3std_mult * local_std,
            );
            
            (params, exceedance_rate, var95, var99, es95, tail_prob_2std, tail_prob_3std)
        })
        .collect();
    
    // Build output
    let mut features = EVTFeatures::new(n);
    
    for (i, &(params, exc_rate, var95, var99, es95, tp2, tp3)) in results.iter().enumerate() {
        let t = window + i;
        
        features.xi[t] = params.xi;
        features.beta[t] = params.beta;
        features.exceedance_rate[t] = exc_rate;
        features.var95[t] = var95;
        features.var99[t] = var99;
        features.es95[t] = es95;
        features.tail_prob_2std[t] = tp2;
        features.tail_prob_3std[t] = tp3;
        
        // Tail flag and regime
        features.tail_flag[t] = if params.xi > config.fat_tail_xi_threshold { 1.0 } else { 0.0 };
        features.regime[t] = features.tail_flag[t];
    }
    
    // Fill early values
    if window < n && features.xi[window].is_finite() {
        for t in 0..window {
            features.xi[t] = features.xi[window];
            features.beta[t] = features.beta[window];
            features.exceedance_rate[t] = 0.0;
            features.var95[t] = features.var95[window];
            features.var99[t] = features.var99[window];
            features.es95[t] = features.es95[window];
            features.tail_prob_2std[t] = 0.05;
            features.tail_prob_3std[t] = 0.01;
            features.tail_flag[t] = features.tail_flag[window];
            features.regime[t] = features.regime[window];
        }
    }
    
    features
}

#[cfg(test)]
mod tests {
    use super::*;
    
    #[test]
    fn test_gpd_pwm() {
        // Generate GPD samples with known parameters
        let mut exceedances: Vec<f64> = (0..100)
            .map(|i| (i as f64 * 0.01).exp() * 0.01)
            .collect();
        
        let params = fit_gpd_pwm(&mut exceedances);
        
        // Just check that we get reasonable values
        assert!(params.xi.is_finite());
        assert!(params.beta > 0.0);
    }
    
    #[test]
    fn test_var_computation() {
        let var = compute_var(0.02, 0.1, 0.01, 0.05, 0.95);
        assert!(var > 0.02); // VaR should be above threshold
        assert!(var < 1.0);  // And reasonably bounded
    }
}
