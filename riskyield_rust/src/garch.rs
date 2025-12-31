//! GARCH(1,1) Volatility Model Implementation
//!
//! Provides:
//! 1. Conditional volatility via GARCH(1,1) recursion
//! 2. Rolling z-score calculation
//! 3. Volatility forecasting

/// Compute GARCH(1,1) conditional variance
///
/// σ²_t = ω + α * r²_{t-1} + β * σ²_{t-1}
///
/// Returns conditional volatility (sqrt of variance)
pub fn garch_conditional_vol(
    returns: &[f64],
    omega: f64,
    alpha: f64,
    beta: f64,
    long_run_var: f64,
) -> Vec<f64> {
    let n = returns.len();
    let mut cond_var = vec![0.0; n];
    
    if n == 0 {
        return cond_var;
    }
    
    // Initialize with long-run variance
    cond_var[0] = long_run_var;
    
    // GARCH recursion
    for t in 1..n {
        let r_sq = returns[t - 1] * returns[t - 1];
        cond_var[t] = omega + alpha * r_sq + beta * cond_var[t - 1];
    }
    
    // Convert to volatility (sqrt), with floor
    cond_var
        .iter()
        .map(|&v| (v.max(1e-10)).sqrt())
        .collect()
}

/// Compute rolling z-score
///
/// zscore[i] = (value[i] - rolling_mean) / rolling_std
pub fn rolling_zscore(values: &[f64], window: usize) -> Vec<f64> {
    let n = values.len();
    let mut zscore = vec![0.0; n];
    
    if n <= window || window == 0 {
        return zscore;
    }
    
    // Efficient rolling stats using cumulative sums
    // For each position i >= window:
    //   mean = (sum of window elements) / window
    //   std = sqrt(sum of squares / window - mean^2)
    
    // Running sum and sum of squares
    let mut sum = 0.0;
    let mut sum_sq = 0.0;
    
    // Initialize with first window
    for i in 0..window {
        sum += values[i];
        sum_sq += values[i] * values[i];
    }
    
    // Compute z-scores for positions >= window
    for i in window..n {
        let mean = sum / window as f64;
        let variance = (sum_sq / window as f64) - mean * mean;
        let std = variance.max(0.0).sqrt() + 1e-10;
        
        zscore[i] = (values[i] - mean) / std;
        
        // Update running sums (slide window)
        let old_val = values[i - window];
        let new_val = values[i];
        sum = sum - old_val + new_val;
        sum_sq = sum_sq - old_val * old_val + new_val * new_val;
    }
    
    zscore
}

/// Compute h-step ahead volatility forecast
///
/// σ²_{t+h|t} = ω(1 + p + ... + p^{h-1}) + p^h * σ²_t
/// where p = α + β (persistence)
pub fn vol_forecast(
    cond_vol: &[f64],
    omega: f64,
    alpha: f64,
    beta: f64,
    horizon: usize,
) -> Vec<f64> {
    let persistence = alpha + beta;
    let horizon_f = horizon as f64;
    
    let sum_factor = if (persistence - 1.0).abs() > 1e-6 {
        (1.0 - persistence.powi(horizon as i32)) / (1.0 - persistence)
    } else {
        horizon_f
    };
    
    let p_h = persistence.powi(horizon as i32);
    
    cond_vol
        .iter()
        .map(|&v| {
            let cond_var = v * v;
            let forecast_var = omega * sum_factor + p_h * cond_var;
            forecast_var.max(1e-10).sqrt()
        })
        .collect()
}

/// Full GARCH transform - returns all 8 features
///
/// Features (in order):
/// 0. cond_vol: Conditional volatility
/// 1. vol_forecast: Multi-step forecast  
/// 2. vol_zscore: Z-score relative to rolling history
/// 3. vol_shock: Standardized residuals (return / lagged vol)
/// 4. persistence: Alpha + beta (constant)
/// 5. vol_regime: 0=LOW, 1=MED, 2=HIGH based on thresholds
/// 6. vol_change: Change in conditional vol
/// 7. vol_ratio: Current vol / long-run vol
pub fn garch_transform(
    returns: &[f64],
    omega: f64,
    alpha: f64,
    beta: f64,
    long_run_var: f64,
    forecast_horizon: usize,
    zscore_window: usize,
    regime_low_thresh: f64,
    regime_high_thresh: f64,
    rescale: f64,
) -> GARCHFeatures {
    let n = returns.len();
    
    if n == 0 {
        return GARCHFeatures::empty();
    }
    
    // 1. Conditional volatility
    let cond_vol = garch_conditional_vol(returns, omega, alpha, beta, long_run_var);
    
    // 2. Multi-step forecast
    let vol_forecast_vals = vol_forecast(&cond_vol, omega, alpha, beta, forecast_horizon);
    
    // 3. Volatility z-score
    let vol_zscore = rolling_zscore(&cond_vol, zscore_window);
    
    // 4. Vol shock (standardized residuals)
    let mut vol_shock = vec![0.0; n];
    for t in 1..n {
        vol_shock[t] = returns[t] / (cond_vol[t - 1] + 1e-10);
    }
    
    // 5. Persistence (constant)
    let persistence = alpha + beta;
    let persistence_vec = vec![persistence; n];
    
    // 6. Volatility regime
    let vol_regime: Vec<f64> = cond_vol
        .iter()
        .map(|&v| {
            if v < regime_low_thresh {
                0.0  // LOW
            } else if v > regime_high_thresh {
                2.0  // HIGH
            } else {
                1.0  // MED
            }
        })
        .collect();
    
    // 7. Vol change
    let mut vol_change = vec![0.0; n];
    for t in 1..n {
        vol_change[t] = cond_vol[t] - cond_vol[t - 1];
    }
    
    // 8. Vol ratio (vs long-run)
    let long_run_vol = long_run_var.sqrt();
    let vol_ratio: Vec<f64> = cond_vol
        .iter()
        .map(|&v| v / (long_run_vol + 1e-10))
        .collect();
    
    // Descale cond_vol, vol_forecast, and vol_change back to original units
    let cond_vol_descaled: Vec<f64> = cond_vol.iter().map(|&v| v / rescale).collect();
    let vol_forecast_descaled: Vec<f64> = vol_forecast_vals.iter().map(|&v| v / rescale).collect();
    let vol_change_descaled: Vec<f64> = vol_change.iter().map(|&v| v / rescale).collect();
    
    GARCHFeatures {
        cond_vol: cond_vol_descaled,
        vol_forecast: vol_forecast_descaled,
        vol_zscore,
        vol_shock,
        persistence: persistence_vec,
        vol_regime,
        vol_change: vol_change_descaled,
        vol_ratio,
    }
}

/// Output structure for GARCH features
pub struct GARCHFeatures {
    pub cond_vol: Vec<f64>,
    pub vol_forecast: Vec<f64>,
    pub vol_zscore: Vec<f64>,
    pub vol_shock: Vec<f64>,
    pub persistence: Vec<f64>,
    pub vol_regime: Vec<f64>,
    pub vol_change: Vec<f64>,
    pub vol_ratio: Vec<f64>,
}

impl GARCHFeatures {
    pub fn empty() -> Self {
        Self {
            cond_vol: vec![],
            vol_forecast: vec![],
            vol_zscore: vec![],
            vol_shock: vec![],
            persistence: vec![],
            vol_regime: vec![],
            vol_change: vec![],
            vol_ratio: vec![],
        }
    }
    
    pub fn len(&self) -> usize {
        self.cond_vol.len()
    }
    
    pub fn is_empty(&self) -> bool {
        self.cond_vol.is_empty()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_garch_conditional_vol() {
        // Simple test with known values
        let returns = vec![0.01, -0.02, 0.015, -0.005, 0.01];
        let omega = 0.000001;
        let alpha = 0.1;
        let beta = 0.85;
        let long_run_var = 0.0001;
        
        let vol = garch_conditional_vol(&returns, omega, alpha, beta, long_run_var);
        
        assert_eq!(vol.len(), 5);
        assert!((vol[0] - 0.01).abs() < 1e-6);  // sqrt(0.0001) = 0.01
        // Subsequent values follow recursion
        assert!(vol[1] > 0.0);
    }

    #[test]
    fn test_rolling_zscore() {
        let values = vec![1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0];
        let window = 3;
        
        let zscore = rolling_zscore(&values, window);
        
        assert_eq!(zscore.len(), 10);
        // First 'window' values should be 0
        assert_eq!(zscore[0], 0.0);
        assert_eq!(zscore[1], 0.0);
        assert_eq!(zscore[2], 0.0);
        // Subsequent values should be non-zero
        assert!(zscore[3].abs() > 0.0);
    }

    #[test]
    fn test_vol_forecast() {
        let cond_vol = vec![0.01, 0.012, 0.011, 0.015, 0.013];
        let omega = 0.000001;
        let alpha = 0.1;
        let beta = 0.85;
        let horizon = 5;
        
        let forecast = vol_forecast(&cond_vol, omega, alpha, beta, horizon);
        
        assert_eq!(forecast.len(), 5);
        // All forecasts should be positive
        for f in &forecast {
            assert!(*f > 0.0);
        }
    }
}
