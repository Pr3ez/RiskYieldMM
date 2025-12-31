//! BOCPD (Bayesian Online Changepoint Detection) helper
//! 
//! Detects regime shifts in real-time using Bayesian inference.
//! This is an online algorithm - O(n × max_run_length).

use std::f64::consts::PI;
use statrs::function::gamma::ln_gamma;

/// Student-t log PDF
#[inline]
fn student_t_logpdf(x: f64, df: f64, loc: f64, scale: f64) -> f64 {
    if scale <= 0.0 || df <= 0.0 {
        return f64::NEG_INFINITY;
    }
    let z = (x - loc) / scale;
    let log_norm = ln_gamma((df + 1.0) / 2.0) 
                 - ln_gamma(df / 2.0) 
                 - 0.5 * (PI * df).ln() 
                 - scale.ln();
    let log_kernel = -((df + 1.0) / 2.0) * (1.0 + z * z / df).ln();
    log_norm + log_kernel
}

/// Output structure for BOCPD features
#[derive(Clone)]
pub struct BOCPDFeatures {
    pub run_length: Vec<f64>,
    pub cp_prob: Vec<f64>,
    pub cp_recent: Vec<f64>,
    pub run_length_norm: Vec<f64>,
    pub regime_age: Vec<f64>,
    pub cp_intensity: Vec<f64>,
    pub stability: Vec<f64>,
}

impl BOCPDFeatures {
    fn new(n: usize) -> Self {
        BOCPDFeatures {
            run_length: vec![0.0; n],
            cp_prob: vec![0.0; n],
            cp_recent: vec![0.0; n],
            run_length_norm: vec![0.0; n],
            regime_age: vec![0.0; n],
            cp_intensity: vec![0.0; n],
            stability: vec![1.0; n],
        }
    }
}

/// Configuration for BOCPD
pub struct BOCPDConfig {
    pub hazard_rate: f64,
    pub max_run_length: usize,
    pub prior_mean: f64,
    pub prior_precision: f64,
    pub prior_alpha: f64,
    pub prior_beta: f64,
    pub cp_threshold: f64,
    pub recent_window: usize,
    pub intensity_window: usize,
}

impl Default for BOCPDConfig {
    fn default() -> Self {
        BOCPDConfig {
            hazard_rate: 1.0 / 250.0,
            max_run_length: 100,
            prior_mean: 0.0,
            prior_precision: 0.1,
            prior_alpha: 1.0,
            prior_beta: 1.0,
            cp_threshold: 0.3,
            recent_window: 5,
            intensity_window: 21,
        }
    }
}

/// Sufficient statistics for Normal-Gamma conjugate prior
struct SufficientStats {
    sum_x: Vec<f64>,
    sum_x2: Vec<f64>,
    counts: Vec<f64>,
}

impl SufficientStats {
    fn new(max_rl: usize) -> Self {
        SufficientStats {
            sum_x: vec![0.0; max_rl + 1],
            sum_x2: vec![0.0; max_rl + 1],
            counts: vec![0.0; max_rl + 1],
        }
    }
    
    fn reset(&mut self) {
        for v in &mut self.sum_x { *v = 0.0; }
        for v in &mut self.sum_x2 { *v = 0.0; }
        for v in &mut self.counts { *v = 0.0; }
    }
}

/// Compute predictive probability under Normal-Gamma prior.
/// The posterior predictive is Student-t distributed.
#[inline]
fn predictive_probability(
    x: f64,
    sum_x: f64,
    sum_x2: f64,
    n: f64,
    prior_mu: f64,
    prior_kappa: f64,
    prior_alpha: f64,
    prior_beta: f64,
) -> f64 {
    if n < 0.5 {
        // No data - use prior
        let df = 2.0 * prior_alpha;
        let loc = prior_mu;
        let scale = (prior_beta / prior_alpha).sqrt();
        return student_t_logpdf(x, df, loc, scale).exp();
    }
    
    // Posterior parameters
    let kappa_n = prior_kappa + n;
    let mu_n = (prior_kappa * prior_mu + sum_x) / kappa_n;
    let alpha_n = prior_alpha + n / 2.0;
    
    // Sum of squared deviations
    let mean_x = sum_x / n;
    let ss = sum_x2 - n * mean_x * mean_x;
    
    let beta_n = prior_beta 
        + 0.5 * ss 
        + (prior_kappa * n * (mean_x - prior_mu).powi(2)) / (2.0 * kappa_n);
    
    // Posterior predictive is Student-t
    let df = 2.0 * alpha_n;
    let loc = mu_n;
    let scale = ((beta_n * (kappa_n + 1.0)) / (alpha_n * kappa_n)).sqrt();
    
    student_t_logpdf(x, df, loc, scale).exp()
}

/// Run BOCPD algorithm online.
/// 
/// Uses Normal-Gamma conjugate prior for efficient updates.
pub fn bocpd_online(
    series: &[f64],
    config: &BOCPDConfig,
    prior_mu: f64,
    prior_kappa: f64,
    prior_alpha: f64,
    prior_beta: f64,
) -> BOCPDFeatures {
    let n = series.len();
    let max_rl = config.max_run_length;
    let hazard = config.hazard_rate;
    
    let mut features = BOCPDFeatures::new(n);
    
    // Run length distribution: R[r] = P(r_t = r | x_{1:t})
    let mut r_dist = vec![0.0; max_rl + 1];
    r_dist[0] = 1.0;  // Start with run length 0
    
    // Sufficient statistics for each run length
    let mut stats = SufficientStats::new(max_rl);
    
    // Working arrays
    let mut pred_prob = vec![0.0; max_rl + 1];
    let mut r_new = vec![0.0; max_rl + 1];
    
    for t in 0..n {
        let x = series[t];
        
        // Handle NaN - treat as missing
        if !x.is_finite() {
            features.run_length[t] = if t > 0 { features.run_length[t-1] } else { 0.0 };
            features.cp_prob[t] = 0.0;
            features.stability[t] = 1.0;
            continue;
        }
        
        // Compute predictive probabilities for each run length
        for r in 0..=max_rl {
            if r_dist[r] < 1e-10 {
                pred_prob[r] = 0.0;
                continue;
            }
            
            pred_prob[r] = predictive_probability(
                x,
                stats.sum_x[r],
                stats.sum_x2[r],
                stats.counts[r],
                prior_mu,
                prior_kappa,
                prior_alpha,
                prior_beta,
            );
        }

        // Predictive probability under a NEW segment (uses prior only)
        let prior_pred = predictive_probability(
            x,
            0.0,
            0.0,
            0.0,
            prior_mu,
            prior_kappa,
            prior_alpha,
            prior_beta,
        );
        
        // Growth probabilities: P(r_t = r+1 | r_{t-1} = r) = 1 - hazard
        let mut cp_mass = prior_pred * hazard;
        for r in 0..max_rl {
            let growth = r_dist[r] * pred_prob[r] * (1.0 - hazard);
            r_new[r + 1] = growth;
        }
        
        // Changepoint: reset to r=0
        r_new[0] = cp_mass;
        
        // Normalize
        let total: f64 = r_new.iter().sum();
        if total > 1e-10 {
            for r in r_new.iter_mut() {
                *r /= total;
            }
        } else {
            r_new.iter_mut().for_each(|v| *v = 0.0);
            r_new[0] = 1.0;
        }
        
        // Update sufficient statistics (shift and add)
        // For r=0 (new segment), start fresh
        let mut new_sum_x = vec![0.0; max_rl + 1];
        let mut new_sum_x2 = vec![0.0; max_rl + 1];
        let mut new_counts = vec![0.0; max_rl + 1];
        
        // r=0 starts fresh
        new_sum_x[0] = 0.0;
        new_sum_x2[0] = 0.0;
        new_counts[0] = 0.0;
        
        // For r>0, inherit from r-1 and add new observation
        for r in 1..=max_rl {
            if r_new[r] > 1e-10 {
                new_sum_x[r] = stats.sum_x[r - 1] + x;
                new_sum_x2[r] = stats.sum_x2[r - 1] + x * x;
                new_counts[r] = stats.counts[r - 1] + 1.0;
            }
        }
        
        // Swap
        stats.sum_x = new_sum_x;
        stats.sum_x2 = new_sum_x2;
        stats.counts = new_counts;
        r_dist = r_new.clone();
        
        // Compute expected run length
        let expected_rl: f64 = (0..=max_rl)
            .map(|r| r as f64 * r_dist[r])
            .sum();
        
        features.run_length[t] = expected_rl;
        features.cp_prob[t] = r_dist[0];
        features.stability[t] = 1.0 - r_dist[0];
    }
    
    // Fill run_length_norm and regime_age
    for t in 0..n {
        features.run_length_norm[t] = features.run_length[t] / max_rl as f64;
        features.regime_age[t] = features.run_length[t];
    }
    
    // Compute cp_recent (any CP in last N bars)
    for t in 0..n {
        let start = if t >= config.recent_window { t - config.recent_window + 1 } else { 0 };
        let any_cp = (start..=t).any(|i| features.cp_prob[i] > config.cp_threshold);
        features.cp_recent[t] = if any_cp { 1.0 } else { 0.0 };
    }
    
    // Compute cp_intensity (rolling sum of CP probabilities)
    for t in 0..n {
        let start = if t >= config.intensity_window { t - config.intensity_window + 1 } else { 0 };
        features.cp_intensity[t] = (start..=t)
            .map(|i| features.cp_prob[i])
            .sum();
    }
    
    features
}

#[cfg(test)]
mod tests {
    use super::*;
    
    #[test]
    fn test_lgamma() {
        // lgamma(5) = ln(4!) = ln(24) ≈ 3.178
        let result = ln_gamma(5.0);
        assert!((result - 3.178).abs() < 0.1);
    }
    
    #[test]
    fn test_bocpd() {
        // Create series with a changepoint
        let mut series: Vec<f64> = (0..100).map(|_| 0.0).collect();
        for i in 50..100 {
            series[i] = 5.0;  // Mean shift
        }
        
        let config = BOCPDConfig::default();
        let features = bocpd_online(&series, &config, 0.0, 0.1, 1.0, 1.0);
        
        // Should detect elevated CP probability around t=50
        let max_cp_prob = features.cp_prob.iter().skip(45).take(15).cloned()
            .fold(0.0_f64, |a, b| a.max(b));
        assert!(max_cp_prob > 0.1, "Should detect changepoint, got max_cp={}", max_cp_prob);
    }
}
