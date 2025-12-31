//! CUSUM (Cumulative Sum Control Chart) - Rust Implementation
//!
//! High-performance change point detection using CUSUM algorithm.
//! Provides ~200x speedup over Python implementation.
//!
//! Features generated (12 total):
//! - cusum_ret_pos/neg: Cumulative sums for returns
//! - cusum_vol_pos/neg: Cumulative sums for volatility
//! - cp_ret_up/down: Changepoint flags for returns
//! - cp_vol_up/down: Changepoint flags for volatility
//! - cp_any: Any changepoint detected
//! - cp_magnitude: Size of change at detection
//! - days_since_cp: Bars since last changepoint
//! - cp_count_21: Rolling 21-bar changepoint count

use rayon::prelude::*;

/// Configuration for CUSUM algorithm
#[derive(Clone, Debug)]
pub struct CUSUMConfig {
    pub threshold: f64,
    pub drift: f64,
    pub min_spacing: usize,
    pub rolling_window: usize,
}

impl Default for CUSUMConfig {
    fn default() -> Self {
        Self {
            threshold: 2.0,
            drift: 0.0,
            min_spacing: 5,
            rolling_window: 63,
        }
    }
}

/// Result of CUSUM computation for a single series
#[derive(Clone, Debug)]
pub struct CUSUMResult {
    pub cusum_pos: Vec<f64>,
    pub cusum_neg: Vec<f64>,
    pub cp_up: Vec<f64>,
    pub cp_down: Vec<f64>,
}

/// Full CUSUM features output (12 features)
#[derive(Clone, Debug)]
pub struct CUSUMFeatures {
    pub cusum_ret_pos: Vec<f64>,
    pub cusum_ret_neg: Vec<f64>,
    pub cusum_vol_pos: Vec<f64>,
    pub cusum_vol_neg: Vec<f64>,
    pub cp_ret_up: Vec<f64>,
    pub cp_ret_down: Vec<f64>,
    pub cp_vol_up: Vec<f64>,
    pub cp_vol_down: Vec<f64>,
    pub cp_any: Vec<f64>,
    pub cp_magnitude: Vec<f64>,
    pub days_since_cp: Vec<f64>,
    pub cp_count_21: Vec<f64>,
}

/// Compute rolling mean for a window ending at index i (exclusive)
#[inline]
fn rolling_mean(data: &[f64], end: usize, window: usize) -> f64 {
    if end < window {
        // Not enough data, use what we have
        let start = 0;
        let slice = &data[start..end];
        if slice.is_empty() {
            return 0.0;
        }
        let mut sum = 0.0;
        let mut count = 0;
        for &v in slice {
            if v.is_finite() {
                sum += v;
                count += 1;
            }
        }
        if count == 0 { 0.0 } else { sum / count as f64 }
    } else {
        let start = end - window;
        let slice = &data[start..end];
        let mut sum = 0.0;
        let mut count = 0;
        for &v in slice {
            if v.is_finite() {
                sum += v;
                count += 1;
            }
        }
        if count == 0 { 0.0 } else { sum / count as f64 }
    }
}

/// Compute rolling std for a window ending at index i (exclusive)
#[inline]
fn rolling_std(data: &[f64], end: usize, window: usize) -> f64 {
    let mean = rolling_mean(data, end, window);
    
    let (start, n) = if end < window {
        (0, end)
    } else {
        (end - window, window)
    };
    
    if n < 2 {
        return 1e-8;
    }
    
    let slice = &data[start..end];
    let mut sum_sq = 0.0;
    let mut count = 0;
    for &v in slice {
        if v.is_finite() {
            let diff = v - mean;
            sum_sq += diff * diff;
            count += 1;
        }
    }
    
    if count < 2 {
        1e-8
    } else {
        (sum_sq / count as f64).sqrt().max(1e-8)
    }
}

/// Core CUSUM algorithm for a single series
/// 
/// Computes cumulative sums with threshold detection and reset.
pub fn compute_cusum_single(
    series: &[f64],
    baseline_mean: f64,
    baseline_std: f64,
    config: &CUSUMConfig,
) -> CUSUMResult {
    let n = series.len();
    let mut cusum_pos = vec![0.0; n];
    let mut cusum_neg = vec![0.0; n];
    let mut cp_up = vec![0.0; n];
    let mut cp_down = vec![0.0; n];
    
    let threshold = config.threshold;
    let drift = config.drift;
    let min_spacing = config.min_spacing;
    let window = config.rolling_window;
    
    let mut last_cp_idx: i64 = -(min_spacing as i64);
    
    for i in 1..n {
        // Use rolling normalization if enough history, else baseline
        let (local_mean, local_std) = if window > 0 && i >= window {
            (rolling_mean(series, i, window), rolling_std(series, i, window))
        } else {
            (baseline_mean, baseline_std)
        };
        
        // Z-score
        let z = if local_std > 1e-10 {
            (series[i] - local_mean) / local_std
        } else {
            0.0
        };
        
        // CUSUM update
        cusum_pos[i] = (cusum_pos[i - 1] + z - drift).max(0.0);
        cusum_neg[i] = (cusum_neg[i - 1] + z + drift).min(0.0);
        
        // Detection with minimum spacing
        let since_last = i as i64 - last_cp_idx;
        if since_last >= min_spacing as i64 {
            if cusum_pos[i] > threshold {
                cp_up[i] = 1.0;
                cusum_pos[i] = 0.0; // Reset after detection
                last_cp_idx = i as i64;
            } else if cusum_neg[i] < -threshold {
                cp_down[i] = 1.0;
                cusum_neg[i] = 0.0; // Reset after detection
                last_cp_idx = i as i64;
            }
        }
    }
    
    CUSUMResult {
        cusum_pos,
        cusum_neg,
        cp_up,
        cp_down,
    }
}

/// Compute days since last changepoint
fn compute_days_since(changepoints: &[f64]) -> Vec<f64> {
    let n = changepoints.len();
    let mut days_since = vec![0.0; n];
    
    let mut last_cp: i64 = -1;
    for i in 0..n {
        if changepoints[i] > 0.0 {
            last_cp = i as i64;
        }
        days_since[i] = if last_cp >= 0 {
            (i as i64 - last_cp) as f64
        } else {
            i as f64
        };
    }
    
    days_since
}

/// Compute rolling sum (efficient O(n) implementation)
fn rolling_sum(arr: &[f64], window: usize) -> Vec<f64> {
    let n = arr.len();
    let mut result = vec![0.0; n];
    
    // Compute cumsum
    let mut cumsum = vec![0.0; n + 1];
    for i in 0..n {
        cumsum[i + 1] = cumsum[i] + arr[i];
    }
    
    // Rolling sum using cumsum difference
    for i in 0..n {
        if i + 1 >= window {
            result[i] = cumsum[i + 1] - cumsum[i + 1 - window];
        } else {
            result[i] = cumsum[i + 1];
        }
    }
    
    result
}

/// Main CUSUM transform function
/// 
/// Computes all 12 CUSUM features for returns and volatility series.
///
/// # Arguments
/// * `returns` - Returns series (column 0)
/// * `volatility` - Volatility series (column 1)
/// * `ret_mean` - Baseline mean for returns (from fit)
/// * `ret_std` - Baseline std for returns (from fit)
/// * `vol_mean` - Baseline mean for volatility (from fit)
/// * `vol_std` - Baseline std for volatility (from fit)
/// * `config` - CUSUM configuration
///
/// # Returns
/// CUSUMFeatures with all 12 feature vectors
pub fn cusum_transform(
    returns: &[f64],
    volatility: &[f64],
    ret_mean: f64,
    ret_std: f64,
    vol_mean: f64,
    vol_std: f64,
    config: &CUSUMConfig,
) -> CUSUMFeatures {
    let n = returns.len();
    
    // Compute CUSUM for returns
    let ret_result = compute_cusum_single(returns, ret_mean, ret_std, config);
    
    // Compute CUSUM for volatility
    let vol_result = compute_cusum_single(volatility, vol_mean, vol_std, config);
    
    // Combined: any changepoint
    let mut cp_any = vec![0.0; n];
    for i in 0..n {
        if ret_result.cp_up[i] > 0.0 
            || ret_result.cp_down[i] > 0.0 
            || vol_result.cp_up[i] > 0.0 
            || vol_result.cp_down[i] > 0.0 
        {
            cp_any[i] = 1.0;
        }
    }
    
    // Compute z-scores for magnitude calculation
    let mut cp_magnitude = vec![0.0; n];
    for i in 0..n {
        if cp_any[i] > 0.0 {
            let ret_zscore = ((returns[i] - ret_mean) / ret_std.max(1e-10)).abs();
            let vol_zscore = ((volatility[i] - vol_mean) / vol_std.max(1e-10)).abs();
            cp_magnitude[i] = ret_zscore.max(vol_zscore);
        }
    }
    
    // Days since last changepoint
    let days_since_cp = compute_days_since(&cp_any);
    
    // Rolling 21-bar changepoint count
    let cp_count_21 = rolling_sum(&cp_any, 21);
    
    CUSUMFeatures {
        cusum_ret_pos: ret_result.cusum_pos,
        cusum_ret_neg: ret_result.cusum_neg,
        cusum_vol_pos: vol_result.cusum_pos,
        cusum_vol_neg: vol_result.cusum_neg,
        cp_ret_up: ret_result.cp_up,
        cp_ret_down: ret_result.cp_down,
        cp_vol_up: vol_result.cp_up,
        cp_vol_down: vol_result.cp_down,
        cp_any,
        cp_magnitude,
        days_since_cp,
        cp_count_21,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_cusum_basic() {
        let series = vec![0.0, 0.1, 0.2, 0.3, 0.5, 0.8, 1.0, 0.9, 0.7, 0.5];
        let config = CUSUMConfig {
            threshold: 2.0,
            drift: 0.0,
            min_spacing: 2,
            rolling_window: 0, // Use baseline only
        };
        
        let result = compute_cusum_single(&series, 0.5, 0.3, &config);
        
        assert_eq!(result.cusum_pos.len(), series.len());
        assert_eq!(result.cusum_neg.len(), series.len());
        assert_eq!(result.cusum_pos[0], 0.0); // First value always 0
    }

    #[test]
    fn test_rolling_sum() {
        let arr = vec![1.0, 0.0, 1.0, 0.0, 0.0, 1.0, 1.0, 0.0];
        let result = rolling_sum(&arr, 3);
        
        assert_eq!(result[0], 1.0); // Just first element
        assert_eq!(result[1], 1.0); // First two elements
        assert_eq!(result[2], 2.0); // [1, 0, 1]
        assert_eq!(result[3], 1.0); // [0, 1, 0]
    }

    #[test]
    fn test_days_since() {
        let cp = vec![0.0, 0.0, 1.0, 0.0, 0.0, 1.0, 0.0];
        let result = compute_days_since(&cp);
        
        assert_eq!(result[0], 0.0); // No CP yet
        assert_eq!(result[1], 1.0);
        assert_eq!(result[2], 0.0); // CP at index 2
        assert_eq!(result[3], 1.0);
        assert_eq!(result[4], 2.0);
        assert_eq!(result[5], 0.0); // CP at index 5
        assert_eq!(result[6], 1.0);
    }
}
