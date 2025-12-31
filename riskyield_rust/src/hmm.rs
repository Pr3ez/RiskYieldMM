//! Gaussian Hidden Markov Model implementation
//!
//! Full Baum-Welch EM algorithm with diagonal covariance.
//! Matches hmmlearn GaussianHMM(covariance_type='diag') API.

use std::f64::consts::PI;

/// Configuration for HMM
pub struct HMMConfig {
    pub n_states: usize,
    pub n_iter: usize,
    pub tol: f64,
    pub min_covar: f64,
}

impl Default for HMMConfig {
    fn default() -> Self {
        Self {
            n_states: 4,
            n_iter: 100,
            tol: 1e-2,
            min_covar: 1e-3,
        }
    }
}

/// Gaussian HMM with diagonal covariance
pub struct GaussianHMM {
    pub n_states: usize,
    pub n_features: usize,
    pub startprob: Vec<f64>,           // [n_states]
    pub transmat: Vec<Vec<f64>>,       // [n_states x n_states]
    pub means: Vec<Vec<f64>>,          // [n_states x n_features]
    pub covars: Vec<Vec<f64>>,         // [n_states x n_features] (diagonal)
    pub min_covar: f64,
    pub converged: bool,
    pub n_iter_done: usize,
}

impl GaussianHMM {
    /// Create new HMM with given dimensions
    pub fn new(n_states: usize, n_features: usize, min_covar: f64) -> Self {
        Self {
            n_states,
            n_features,
            startprob: vec![1.0 / n_states as f64; n_states],
            transmat: vec![vec![1.0 / n_states as f64; n_states]; n_states],
            means: vec![vec![0.0; n_features]; n_states],
            covars: vec![vec![1.0; n_features]; n_states],
            min_covar,
            converged: false,
            n_iter_done: 0,
        }
    }

    /// Initialize parameters from data using k-means++ style initialization
    pub fn initialize_params(&mut self, obs: &[Vec<f64>], seed: u64) {
        let n_samples = obs.len();
        if n_samples == 0 || self.n_features == 0 {
            return;
        }

        // Simple deterministic initialization based on quantiles
        // This is more reproducible than random k-means
        
        // Sort observations by first feature (returns) for deterministic init
        let mut indices: Vec<usize> = (0..n_samples).collect();
        indices.sort_by(|&a, &b| {
            obs[a][0].partial_cmp(&obs[b][0]).unwrap_or(std::cmp::Ordering::Equal)
        });

        // Use seed to add slight variation (for multiple runs)
        let offset = (seed % 17) as usize;
        
        // Assign observations to states based on quantiles
        let chunk_size = n_samples / self.n_states;
        
        // Initialize means from quantile centers
        for state in 0..self.n_states {
            let start = state * chunk_size;
            let end = if state == self.n_states - 1 {
                n_samples
            } else {
                (state + 1) * chunk_size
            };
            
            // Compute mean for this chunk
            let mut mean = vec![0.0; self.n_features];
            let mut count = 0;
            for i in start..end {
                let idx = indices[(i + offset) % n_samples];
                for f in 0..self.n_features {
                    mean[f] += obs[idx][f];
                }
                count += 1;
            }
            if count > 0 {
                for f in 0..self.n_features {
                    mean[f] /= count as f64;
                }
            }
            self.means[state] = mean;
        }

        // Initialize covariances from overall data variance
        let mut overall_mean = vec![0.0; self.n_features];
        for ob in obs {
            for f in 0..self.n_features {
                overall_mean[f] += ob[f];
            }
        }
        for f in 0..self.n_features {
            overall_mean[f] /= n_samples as f64;
        }

        let mut variance = vec![0.0; self.n_features];
        for ob in obs {
            for f in 0..self.n_features {
                let diff = ob[f] - overall_mean[f];
                variance[f] += diff * diff;
            }
        }
        for f in 0..self.n_features {
            variance[f] = (variance[f] / n_samples as f64).max(self.min_covar);
        }

        // Set all states to have this variance initially
        for state in 0..self.n_states {
            self.covars[state] = variance.clone();
        }

        // Initialize uniform startprob and transition matrix
        let uniform = 1.0 / self.n_states as f64;
        self.startprob = vec![uniform; self.n_states];
        
        // Slightly sticky transition matrix (prefer staying in same state)
        let stay_prob = 0.7;
        let leave_prob = (1.0 - stay_prob) / (self.n_states - 1) as f64;
        for i in 0..self.n_states {
            for j in 0..self.n_states {
                self.transmat[i][j] = if i == j { stay_prob } else { leave_prob };
            }
        }
    }

    /// Log probability of observation under Gaussian with diagonal covariance
    #[inline]
    fn log_gaussian_pdf(&self, obs: &[f64], state: usize) -> f64 {
        let mut log_prob = -0.5 * self.n_features as f64 * (2.0 * PI).ln();
        
        for f in 0..self.n_features {
            let var = self.covars[state][f].max(self.min_covar);
            let diff = obs[f] - self.means[state][f];
            log_prob -= 0.5 * var.ln();
            log_prob -= 0.5 * diff * diff / var;
        }
        
        log_prob
    }

    /// Compute log emission probabilities for all observations and states
    /// Returns [n_samples x n_states] matrix
    fn compute_log_emission(&self, obs: &[Vec<f64>]) -> Vec<Vec<f64>> {
        let n_samples = obs.len();
        let mut log_emission = vec![vec![0.0; self.n_states]; n_samples];
        
        for t in 0..n_samples {
            for s in 0..self.n_states {
                log_emission[t][s] = self.log_gaussian_pdf(&obs[t], s);
            }
        }
        
        log_emission
    }

    /// Log-sum-exp for numerical stability
    #[inline]
    fn log_sum_exp(values: &[f64]) -> f64 {
        if values.is_empty() {
            return f64::NEG_INFINITY;
        }
        
        let max_val = values.iter().cloned().fold(f64::NEG_INFINITY, f64::max);
        if max_val == f64::NEG_INFINITY {
            return f64::NEG_INFINITY;
        }
        
        let sum: f64 = values.iter().map(|&v| (v - max_val).exp()).sum();
        max_val + sum.ln()
    }

    /// Inline log-sum-exp for small fixed-size arrays (avoids allocation)
    #[inline]
    fn log_sum_exp_inline(&self, values: &[f64]) -> f64 {
        let mut max_val = f64::NEG_INFINITY;
        for &v in values {
            if v > max_val {
                max_val = v;
            }
        }
        if max_val == f64::NEG_INFINITY {
            return f64::NEG_INFINITY;
        }
        
        let mut sum = 0.0;
        for &v in values {
            sum += (v - max_val).exp();
        }
        max_val + sum.ln()
    }

    /// Forward algorithm (alpha pass) - optimized
    /// Returns (log_alpha, log_likelihood)
    fn forward(&self, log_emission: &[Vec<f64>]) -> (Vec<Vec<f64>>, f64) {
        let n_samples = log_emission.len();
        let n_states = self.n_states;
        let mut log_alpha = vec![vec![f64::NEG_INFINITY; n_states]; n_samples];
        
        // Pre-compute log transition matrix
        let log_transmat: Vec<Vec<f64>> = self.transmat
            .iter()
            .map(|row| row.iter().map(|&p| p.max(1e-300).ln()).collect())
            .collect();
        let log_startprob: Vec<f64> = self.startprob.iter().map(|&p| p.max(1e-300).ln()).collect();
        
        // Initialize: alpha_0(s) = pi(s) * b_s(o_0)
        for s in 0..n_states {
            log_alpha[0][s] = log_startprob[s] + log_emission[0][s];
        }
        
        // Pre-allocate work buffer
        let mut log_sum_terms = vec![0.0; n_states];
        
        // Recursion: alpha_t(j) = sum_i[alpha_{t-1}(i) * a_ij] * b_j(o_t)
        for t in 1..n_samples {
            for j in 0..n_states {
                for i in 0..n_states {
                    log_sum_terms[i] = log_alpha[t - 1][i] + log_transmat[i][j];
                }
                log_alpha[t][j] = self.log_sum_exp_inline(&log_sum_terms) + log_emission[t][j];
            }
        }
        
        // Log-likelihood = log(sum_s alpha_T(s))
        let log_likelihood = self.log_sum_exp_inline(&log_alpha[n_samples - 1]);
        
        (log_alpha, log_likelihood)
    }

    /// Backward algorithm (beta pass) - optimized
    fn backward(&self, log_emission: &[Vec<f64>]) -> Vec<Vec<f64>> {
        let n_samples = log_emission.len();
        let n_states = self.n_states;
        let mut log_beta = vec![vec![f64::NEG_INFINITY; n_states]; n_samples];
        
        // Pre-compute log transition matrix
        let log_transmat: Vec<Vec<f64>> = self.transmat
            .iter()
            .map(|row| row.iter().map(|&p| p.max(1e-300).ln()).collect())
            .collect();
        
        // Initialize: beta_T(s) = 1 (log = 0)
        for s in 0..n_states {
            log_beta[n_samples - 1][s] = 0.0;
        }
        
        // Pre-allocate work buffer
        let mut log_sum_terms = vec![0.0; n_states];
        
        // Recursion: beta_t(i) = sum_j[a_ij * b_j(o_{t+1}) * beta_{t+1}(j)]
        for t in (0..n_samples - 1).rev() {
            for i in 0..n_states {
                for j in 0..n_states {
                    log_sum_terms[j] = log_transmat[i][j]
                        + log_emission[t + 1][j]
                        + log_beta[t + 1][j];
                }
                log_beta[t][i] = self.log_sum_exp_inline(&log_sum_terms);
            }
        }
        
        log_beta
    }

    /// Compute posteriors (gamma) from forward-backward
    /// gamma[t][s] = P(q_t = s | O)
    fn compute_posteriors(
        &self,
        log_alpha: &[Vec<f64>],
        log_beta: &[Vec<f64>],
        log_likelihood: f64,
    ) -> Vec<Vec<f64>> {
        let n_samples = log_alpha.len();
        let mut gamma = vec![vec![0.0; self.n_states]; n_samples];
        
        for t in 0..n_samples {
            for s in 0..self.n_states {
                let log_gamma = log_alpha[t][s] + log_beta[t][s] - log_likelihood;
                gamma[t][s] = log_gamma.exp().max(1e-300);
            }
            
            // Normalize to ensure sum = 1
            let sum: f64 = gamma[t].iter().sum();
            if sum > 0.0 {
                for s in 0..self.n_states {
                    gamma[t][s] /= sum;
                }
            } else {
                // Fallback to uniform
                for s in 0..self.n_states {
                    gamma[t][s] = 1.0 / self.n_states as f64;
                }
            }
        }
        
        gamma
    }

    /// Compute transition posteriors (xi)
    /// xi[t][i][j] = P(q_t = i, q_{t+1} = j | O)
    fn compute_xi(
        &self,
        log_alpha: &[Vec<f64>],
        log_beta: &[Vec<f64>],
        log_emission: &[Vec<f64>],
        log_likelihood: f64,
    ) -> Vec<Vec<Vec<f64>>> {
        let n_samples = log_alpha.len();
        let mut xi = vec![vec![vec![0.0; self.n_states]; self.n_states]; n_samples - 1];
        // Pre-compute log transition matrix
        let log_transmat: Vec<Vec<f64>> = self.transmat
            .iter()
            .map(|row| row.iter().map(|&p| p.max(1e-300).ln()).collect())
            .collect();
        
        // Pre-allocate log_xi matrix
        let mut log_xi = vec![vec![0.0; self.n_states]; self.n_states];
        let mut log_sum_terms = vec![0.0; self.n_states];
        
        for t in 0..n_samples - 1 {
            // Compute log xi values
            for i in 0..self.n_states {
                for j in 0..self.n_states {
                    log_xi[i][j] = log_alpha[t][i]
                        + log_transmat[i][j]
                        + log_emission[t + 1][j]
                        + log_beta[t + 1][j];
                }
            }
            
            // Find normalizer using nested log_sum_exp
            let mut normalizer = f64::NEG_INFINITY;
            for i in 0..self.n_states {
                let row_lse = self.log_sum_exp_inline(&log_xi[i]);
                normalizer = if normalizer == f64::NEG_INFINITY {
                    row_lse
                } else if row_lse == f64::NEG_INFINITY {
                    normalizer
                } else {
                    let max_v = normalizer.max(row_lse);
                    max_v + ((normalizer - max_v).exp() + (row_lse - max_v).exp()).ln()
                };
            }
            
            // Convert to probabilities
            for i in 0..self.n_states {
                for j in 0..self.n_states {
                    xi[t][i][j] = (log_xi[i][j] - normalizer).exp().max(1e-300);
                }
            }
        }
        
        xi
    }

    /// M-step: Update parameters from posteriors
    fn m_step(&mut self, obs: &[Vec<f64>], gamma: &[Vec<f64>], xi: &Vec<Vec<Vec<f64>>>) {
        let n_samples = obs.len();
        
        // Update start probabilities
        let mut startprob_sum = 0.0;
        for s in 0..self.n_states {
            self.startprob[s] = gamma[0][s].max(1e-300);
            startprob_sum += self.startprob[s];
        }
        for s in 0..self.n_states {
            self.startprob[s] /= startprob_sum;
        }
        
        // Update transition matrix
        for i in 0..self.n_states {
            let mut gamma_sum = 0.0;
            for t in 0..n_samples - 1 {
                gamma_sum += gamma[t][i];
            }
            gamma_sum = gamma_sum.max(1e-300);
            
            let mut row_sum = 0.0;
            for j in 0..self.n_states {
                let mut xi_sum = 0.0;
                for t in 0..n_samples - 1 {
                    xi_sum += xi[t][i][j];
                }
                self.transmat[i][j] = (xi_sum / gamma_sum).max(1e-300);
                row_sum += self.transmat[i][j];
            }
            
            // Normalize row
            if row_sum > 0.0 {
                for j in 0..self.n_states {
                    self.transmat[i][j] /= row_sum;
                }
            }
        }
        
        // Update means and covariances
        for s in 0..self.n_states {
            let mut gamma_sum = 0.0;
            for t in 0..n_samples {
                gamma_sum += gamma[t][s];
            }
            gamma_sum = gamma_sum.max(1e-300);
            
            // Update means
            for f in 0..self.n_features {
                let mut weighted_sum = 0.0;
                for t in 0..n_samples {
                    weighted_sum += gamma[t][s] * obs[t][f];
                }
                self.means[s][f] = weighted_sum / gamma_sum;
            }
            
            // Update covariances (diagonal)
            for f in 0..self.n_features {
                let mut weighted_sq_sum = 0.0;
                for t in 0..n_samples {
                    let diff = obs[t][f] - self.means[s][f];
                    weighted_sq_sum += gamma[t][s] * diff * diff;
                }
                self.covars[s][f] = (weighted_sq_sum / gamma_sum).max(self.min_covar);
            }
        }
    }

    /// Fit HMM using Baum-Welch EM algorithm
    pub fn fit(&mut self, obs: &[Vec<f64>], n_iter: usize, tol: f64, seed: u64) -> f64 {
        if obs.is_empty() {
            return f64::NEG_INFINITY;
        }
        
        // Initialize parameters
        self.initialize_params(obs, seed);
        
        let mut prev_log_likelihood = f64::NEG_INFINITY;
        
        for iter in 0..n_iter {
            // E-step
            let log_emission = self.compute_log_emission(obs);
            let (log_alpha, log_likelihood) = self.forward(&log_emission);
            let log_beta = self.backward(&log_emission);
            
            // Check convergence
            if iter > 0 {
                let improvement = log_likelihood - prev_log_likelihood;
                if improvement.abs() < tol {
                    self.converged = true;
                    self.n_iter_done = iter + 1;
                    return log_likelihood;
                }
            }
            
            prev_log_likelihood = log_likelihood;
            
            // Compute posteriors
            let gamma = self.compute_posteriors(&log_alpha, &log_beta, log_likelihood);
            let xi = self.compute_xi(&log_alpha, &log_beta, &log_emission, log_likelihood);
            
            // M-step
            self.m_step(obs, &gamma, &xi);
            
            self.n_iter_done = iter + 1;
        }
        
        prev_log_likelihood
    }

    /// Predict state probabilities for observations
    pub fn predict_proba(&self, obs: &[Vec<f64>]) -> Vec<Vec<f64>> {
        if obs.is_empty() {
            return vec![];
        }
        
        let log_emission = self.compute_log_emission(obs);
        let (log_alpha, log_likelihood) = self.forward(&log_emission);
        let log_beta = self.backward(&log_emission);
        
        self.compute_posteriors(&log_alpha, &log_beta, log_likelihood)
    }

    /// Predict most likely state sequence using Viterbi algorithm
    pub fn predict(&self, obs: &[Vec<f64>]) -> Vec<usize> {
        if obs.is_empty() {
            return vec![];
        }
        
        let n_samples = obs.len();
        let log_emission = self.compute_log_emission(obs);
        
        // Viterbi algorithm
        let mut log_delta = vec![vec![f64::NEG_INFINITY; self.n_states]; n_samples];
        let mut psi = vec![vec![0usize; self.n_states]; n_samples];
        
        // Initialize
        for s in 0..self.n_states {
            log_delta[0][s] = self.startprob[s].max(1e-300).ln() + log_emission[0][s];
        }
        
        // Recursion
        for t in 1..n_samples {
            for j in 0..self.n_states {
                let mut max_val = f64::NEG_INFINITY;
                let mut max_state = 0;
                
                for i in 0..self.n_states {
                    let val = log_delta[t - 1][i] + self.transmat[i][j].max(1e-300).ln();
                    if val > max_val {
                        max_val = val;
                        max_state = i;
                    }
                }
                
                log_delta[t][j] = max_val + log_emission[t][j];
                psi[t][j] = max_state;
            }
        }
        
        // Backtrack
        let mut states = vec![0usize; n_samples];
        
        // Find best final state
        let mut max_val = f64::NEG_INFINITY;
        for s in 0..self.n_states {
            if log_delta[n_samples - 1][s] > max_val {
                max_val = log_delta[n_samples - 1][s];
                states[n_samples - 1] = s;
            }
        }
        
        // Backtrack
        for t in (0..n_samples - 1).rev() {
            states[t] = psi[t + 1][states[t + 1]];
        }
        
        states
    }

    /// Compute log-likelihood score
    pub fn score(&self, obs: &[Vec<f64>]) -> f64 {
        if obs.is_empty() {
            return f64::NEG_INFINITY;
        }
        
        let log_emission = self.compute_log_emission(obs);
        let (_, log_likelihood) = self.forward(&log_emission);
        log_likelihood
    }
}

/// Output features from HMM transform
pub struct HMMFeatures {
    pub probs: Vec<Vec<f64>>,    // [n_samples x n_states]
    pub states: Vec<usize>,      // [n_samples]
    pub entropy: Vec<f64>,       // [n_samples]
    pub confidence: Vec<f64>,    // [n_samples]
    pub duration: Vec<f64>,      // [n_samples]
    pub change: Vec<f64>,        // [n_samples]
}

impl HMMFeatures {
    pub fn empty(n_states: usize) -> Self {
        Self {
            probs: vec![],
            states: vec![],
            entropy: vec![],
            confidence: vec![],
            duration: vec![],
            change: vec![],
        }
    }
    
    pub fn n_features(&self) -> usize {
        if self.probs.is_empty() {
            0
        } else {
            self.probs[0].len() + 5  // n_states probs + state + entropy + confidence + duration + change
        }
    }
}

/// Compute state duration (how long in current state)
fn compute_duration(states: &[usize]) -> Vec<f64> {
    let n = states.len();
    if n == 0 {
        return vec![];
    }
    
    let mut duration = vec![1.0; n];
    
    for i in 1..n {
        if states[i] == states[i - 1] {
            duration[i] = duration[i - 1] + 1.0;
        } else {
            duration[i] = 1.0;
        }
    }
    
    duration
}

/// Compute state change indicator
fn compute_change(states: &[usize]) -> Vec<f64> {
    let n = states.len();
    if n == 0 {
        return vec![];
    }
    
    let mut change = vec![0.0; n];
    
    for i in 1..n {
        if states[i] != states[i - 1] {
            change[i] = 1.0;
        }
    }
    
    change
}

/// Compute entropy from probabilities
fn compute_entropy(probs: &[Vec<f64>]) -> Vec<f64> {
    probs
        .iter()
        .map(|p| {
            -p.iter()
                .map(|&prob| {
                    if prob > 1e-10 {
                        prob * prob.ln()
                    } else {
                        0.0
                    }
                })
                .sum::<f64>()
        })
        .collect()
}

/// Compute confidence (max probability)
fn compute_confidence(probs: &[Vec<f64>]) -> Vec<f64> {
    probs
        .iter()
        .map(|p| p.iter().cloned().fold(0.0, f64::max))
        .collect()
}

/// Full HMM transform - fits model and returns all features
///
/// Features (in order):
/// 0 to n_states-1: State probabilities
/// n_states: Current state
/// n_states+1: Entropy
/// n_states+2: Confidence (max prob)
/// n_states+3: Duration in current state
/// n_states+4: State change indicator
pub fn hmm_transform(
    returns: &[f64],
    volatility: &[f64],
    n_states: usize,
    n_iter: usize,
    tol: f64,
    min_covar: f64,
    seed: u64,
) -> HMMFeatures {
    let n = returns.len();
    
    if n == 0 || n != volatility.len() {
        return HMMFeatures::empty(n_states);
    }
    
    // Compute mean and std for z-score normalization
    let ret_mean: f64 = returns.iter().sum::<f64>() / n as f64;
    let vol_mean: f64 = volatility.iter().sum::<f64>() / n as f64;
    
    let ret_var: f64 = returns.iter().map(|&r| (r - ret_mean).powi(2)).sum::<f64>() / n as f64;
    let vol_var: f64 = volatility.iter().map(|&v| (v - vol_mean).powi(2)).sum::<f64>() / n as f64;
    
    let ret_std = ret_var.sqrt().max(1e-10);
    let vol_std = vol_var.sqrt().max(1e-10);
    
    // Prepare observations [returns, volatility] with z-score normalization
    let obs: Vec<Vec<f64>> = returns
        .iter()
        .zip(volatility.iter())
        .map(|(&r, &v)| vec![(r - ret_mean) / ret_std, (v - vol_mean) / vol_std])
        .collect();
    
    // Create and fit HMM
    let mut hmm = GaussianHMM::new(n_states, 2, min_covar);
    hmm.fit(&obs, n_iter, tol, seed);
    
    // Get predictions
    let probs = hmm.predict_proba(&obs);
    let states = hmm.predict(&obs);
    
    // Sanitize probabilities
    let probs: Vec<Vec<f64>> = probs
        .into_iter()
        .map(|mut p| {
            let sum: f64 = p.iter().sum();
            if sum > 0.0 && sum.is_finite() {
                for prob in &mut p {
                    *prob /= sum;
                }
            } else {
                p = vec![1.0 / n_states as f64; n_states];
            }
            p
        })
        .collect();
    
    // Compute derived features
    let entropy = compute_entropy(&probs);
    let confidence = compute_confidence(&probs);
    let duration = compute_duration(&states);
    let change = compute_change(&states);
    
    HMMFeatures {
        probs,
        states,
        entropy,
        confidence,
        duration,
        change,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_log_sum_exp() {
        let values = vec![-1.0, -2.0, -3.0];
        let result = GaussianHMM::log_sum_exp(&values);
        
        // Manual calculation: log(e^-1 + e^-2 + e^-3)
        let expected = ((-1.0_f64).exp() + (-2.0_f64).exp() + (-3.0_f64).exp()).ln();
        assert!((result - expected).abs() < 1e-10);
    }

    #[test]
    fn test_gaussian_pdf() {
        let mut hmm = GaussianHMM::new(2, 1, 1e-3);
        hmm.means[0] = vec![0.0];
        hmm.covars[0] = vec![1.0];
        
        // Standard normal at x=0 should give log(1/sqrt(2*pi))
        let log_prob = hmm.log_gaussian_pdf(&[0.0], 0);
        let expected = -0.5 * (2.0 * PI).ln();
        assert!((log_prob - expected).abs() < 1e-10);
    }

    #[test]
    fn test_hmm_fit_and_predict() {
        // Generate simple synthetic data
        let n = 200;
        let mut returns = vec![0.0; n];
        let mut volatility = vec![0.0; n];
        
        // First half: low volatility regime
        for i in 0..n / 2 {
            returns[i] = 0.001;
            volatility[i] = 0.01;
        }
        // Second half: high volatility regime
        for i in n / 2..n {
            returns[i] = -0.002;
            volatility[i] = 0.03;
        }
        
        let features = hmm_transform(&returns, &volatility, 2, 50, 1e-2, 1e-3, 42);
        
        assert_eq!(features.states.len(), n);
        assert_eq!(features.probs.len(), n);
        assert_eq!(features.entropy.len(), n);
        assert_eq!(features.confidence.len(), n);
        assert_eq!(features.duration.len(), n);
        assert_eq!(features.change.len(), n);
        
        // Check that probs sum to 1
        for p in &features.probs {
            let sum: f64 = p.iter().sum();
            assert!((sum - 1.0).abs() < 1e-6);
        }
        
        // Check that confidence is max of probs
        for (i, conf) in features.confidence.iter().enumerate() {
            let max_prob = features.probs[i].iter().cloned().fold(0.0, f64::max);
            assert!((conf - max_prob).abs() < 1e-10);
        }
    }

    #[test]
    fn test_duration_computation() {
        let states = vec![0, 0, 0, 1, 1, 0, 0, 0, 0];
        let duration = compute_duration(&states);
        
        assert_eq!(duration, vec![1.0, 2.0, 3.0, 1.0, 2.0, 1.0, 2.0, 3.0, 4.0]);
    }

    #[test]
    fn test_change_computation() {
        let states = vec![0, 0, 0, 1, 1, 0, 0, 0, 0];
        let change = compute_change(&states);
        
        assert_eq!(change, vec![0.0, 0.0, 0.0, 1.0, 0.0, 1.0, 0.0, 0.0, 0.0]);
    }

    #[test]
    fn test_viterbi() {
        let mut hmm = GaussianHMM::new(2, 1, 1e-3);
        
        // Set up simple model
        hmm.startprob = vec![0.5, 0.5];
        hmm.transmat = vec![vec![0.9, 0.1], vec![0.1, 0.9]];
        hmm.means = vec![vec![0.0], vec![1.0]];
        hmm.covars = vec![vec![0.1], vec![0.1]];
        
        // Observations clearly in state 0 then state 1
        let obs = vec![
            vec![0.1], vec![0.0], vec![-0.1],  // Near state 0
            vec![0.9], vec![1.0], vec![1.1],   // Near state 1
        ];
        
        let states = hmm.predict(&obs);
        
        // First half should be state 0, second half state 1
        assert_eq!(states[0], 0);
        assert_eq!(states[1], 0);
        assert_eq!(states[2], 0);
        assert_eq!(states[3], 1);
        assert_eq!(states[4], 1);
        assert_eq!(states[5], 1);
    }
}
