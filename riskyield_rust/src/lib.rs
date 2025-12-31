//! RiskYield Rust - High-performance helper computations
//! 
//! PyO3 bindings for fast L1 helper feature generation.
//! Provides 100-500x speedup over pure Python implementations.

use numpy::{PyArray1, PyArray2, PyArrayMethods, PyReadonlyArray1};
use pyo3::prelude::*;

mod bocpd;
mod cusum;
mod egarch;
mod evt;
mod garch;
mod kalman;
mod ou;

use bocpd::{bocpd_online, BOCPDConfig};
use cusum::{cusum_transform, CUSUMConfig};
use egarch::{
    egarch_rolling_transform, egarch_rolling_transform_full,
    estimate_egarch_params, EGARCHConfig, EGARCHParams,
};
use evt::{evt_rolling_transform, EVTConfig};
use garch::garch_transform;
use kalman::{kalman_transform, KalmanConfig};
use ou::{ou_rolling_transform, OUConfig};

/// Python module for RiskYield Rust helpers
#[pymodule]
fn riskyield_rust(m: &Bound<'_, PyModule>) -> PyResult<()> {
    // OU functions
    m.add_function(wrap_pyfunction!(py_ou_rolling_transform, m)?)?;

    // EVT functions
    m.add_function(wrap_pyfunction!(py_evt_rolling_transform, m)?)?;

    // BOCPD functions
    m.add_function(wrap_pyfunction!(py_bocpd_online, m)?)?;

    // EGARCH functions
    m.add_function(wrap_pyfunction!(py_egarch_rolling_transform, m)?)?;
    m.add_function(wrap_pyfunction!(py_egarch_rolling_transform_full, m)?)?;
    m.add_function(wrap_pyfunction!(py_egarch_estimate_params, m)?)?;

    // CUSUM functions
    m.add_function(wrap_pyfunction!(py_cusum_transform, m)?)?;

    // Kalman functions
    m.add_function(wrap_pyfunction!(py_kalman_transform, m)?)?;

    // GARCH functions
    m.add_function(wrap_pyfunction!(py_garch_transform, m)?)?;

    Ok(())
}

// =============================================================================
// OU Functions
// =============================================================================

/// Compute OU features using rolling AR(1) estimation.
///
/// Args:
///     series: 1D array of observations (e.g., price deviations)
///     rolling_window: Window size for AR(1) estimation (default: 63)
///     zscore_window: Window size for z-score (default: 21)
///     min_halflife: Minimum half-life for OPTIMAL regime (default: 2.0)
///     max_halflife: Maximum half-life for OPTIMAL regime (default: 50.0)
///     phi_threshold: Stationarity threshold (default: 0.99)
///
/// Returns:
///     2D array (n_samples, 8) with columns:
///     [phi, kappa, halflife, zscore, zscore_abs, is_stationary, halflife_regime, reverting]
#[pyfunction]
#[pyo3(signature = (series, rolling_window=63, zscore_window=21, min_halflife=2.0, max_halflife=50.0, phi_threshold=0.99))]
fn py_ou_rolling_transform<'py>(
    py: Python<'py>,
    series: PyReadonlyArray1<f64>,
    rolling_window: usize,
    zscore_window: usize,
    min_halflife: f64,
    max_halflife: f64,
    phi_threshold: f64,
) -> PyResult<Bound<'py, PyArray2<f64>>> {
    let data = series.as_slice().unwrap();

    let config = OUConfig {
        rolling_window,
        zscore_window,
        min_halflife,
        max_halflife,
        phi_stationarity_threshold: phi_threshold,
    };

    let features = ou_rolling_transform(data, &config);

    // Convert to 2D array
    let n = features.phi.len();
    let mut output = vec![0.0; n * 8];

    for i in 0..n {
        output[i * 8 + 0] = features.phi[i];
        output[i * 8 + 1] = features.kappa[i];
        output[i * 8 + 2] = features.halflife[i];
        output[i * 8 + 3] = features.zscore[i];
        output[i * 8 + 4] = features.zscore_abs[i];
        output[i * 8 + 5] = features.is_stationary[i];
        output[i * 8 + 6] = features.halflife_regime[i];
        output[i * 8 + 7] = features.reverting[i];
    }

    PyArray1::from_vec(py, output)
        .reshape([n, 8])
}

// =============================================================================
// EVT Functions
// =============================================================================

/// Compute EVT features using rolling GPD estimation.
///
/// Args:
///     returns: 1D array of returns
///     rolling_window: Window size for GPD estimation (default: 252)
///     threshold_percentile: Percentile for exceedance threshold (default: 95.0)
///     min_exceedances: Minimum exceedances for GPD fit (default: 30)
///     fat_tail_threshold: Xi threshold for fat tail flag (default: 0.25)
///     fitted_threshold: Pre-computed threshold from fit() (default: 0.02)
///
/// Returns:
///     2D array (n_samples, 10) with columns:
///     [xi, beta, exceedance_rate, var95, var99, es95, tail_prob_2std, tail_prob_3std, tail_flag, regime]
#[pyfunction]
#[pyo3(signature = (returns, rolling_window=252, threshold_percentile=95.0, min_exceedances=30, fat_tail_threshold=0.25, fitted_threshold=0.02))]
fn py_evt_rolling_transform<'py>(
    py: Python<'py>,
    returns: PyReadonlyArray1<f64>,
    rolling_window: usize,
    threshold_percentile: f64,
    min_exceedances: usize,
    fat_tail_threshold: f64,
    fitted_threshold: f64,
) -> PyResult<Bound<'py, PyArray2<f64>>> {
    let data = returns.as_slice().unwrap();

    let config = EVTConfig {
        rolling_window,
        threshold_percentile,
        min_exceedances,
        fat_tail_xi_threshold: fat_tail_threshold,
        tail_2std_mult: 2.0,
        tail_3std_mult: 3.0,
        use_absolute: true,
    };

    let features = evt_rolling_transform(data, &config, fitted_threshold);

    // Convert to 2D array
    let n = features.xi.len();
    let mut output = vec![0.0; n * 10];

    for i in 0..n {
        output[i * 10 + 0] = features.xi[i];
        output[i * 10 + 1] = features.beta[i];
        output[i * 10 + 2] = features.exceedance_rate[i];
        output[i * 10 + 3] = features.var95[i];
        output[i * 10 + 4] = features.var99[i];
        output[i * 10 + 5] = features.es95[i];
        output[i * 10 + 6] = features.tail_prob_2std[i];
        output[i * 10 + 7] = features.tail_prob_3std[i];
        output[i * 10 + 8] = features.tail_flag[i];
        output[i * 10 + 9] = features.regime[i];
    }

    PyArray1::from_vec(py, output)
        .reshape([n, 10])
}

// =============================================================================
// BOCPD Functions
// =============================================================================

/// Run BOCPD online changepoint detection.
///
/// Args:
///     series: 1D array of observations
///     hazard_rate: Constant hazard rate (default: 1/250)
///     max_run_length: Maximum run length to track (default: 100)
///     prior_mu: Prior mean (default: 0.0)
///     prior_kappa: Prior precision (default: 0.1)
///     prior_alpha: Prior shape (default: 1.0)
///     prior_beta: Prior rate (default: 1.0)
///     cp_threshold: Changepoint probability threshold (default: 0.3)
///     recent_window: Window for recent CP detection (default: 5)
///     intensity_window: Window for CP intensity (default: 21)
///
/// Returns:
///     2D array (n_samples, 7) with columns:
///     [run_length, cp_prob, cp_recent, run_length_norm, regime_age, cp_intensity, stability]
#[pyfunction]
#[pyo3(signature = (series, hazard_rate=0.004, max_run_length=100, prior_mu=0.0, prior_kappa=0.1, prior_alpha=1.0, prior_beta=1.0, cp_threshold=0.3, recent_window=5, intensity_window=21))]
fn py_bocpd_online<'py>(
    py: Python<'py>,
    series: PyReadonlyArray1<f64>,
    hazard_rate: f64,
    max_run_length: usize,
    prior_mu: f64,
    prior_kappa: f64,
    prior_alpha: f64,
    prior_beta: f64,
    cp_threshold: f64,
    recent_window: usize,
    intensity_window: usize,
) -> PyResult<Bound<'py, PyArray2<f64>>> {
    let data = series.as_slice().unwrap();

    let config = BOCPDConfig {
        hazard_rate,
        max_run_length,
        prior_mean: prior_mu,
        prior_precision: prior_kappa,
        prior_alpha,
        prior_beta,
        cp_threshold,
        recent_window,
        intensity_window,
    };

    let features = bocpd_online(data, &config, prior_mu, prior_kappa, prior_alpha, prior_beta);

    // Convert to 2D array
    let n = features.run_length.len();
    let mut output = vec![0.0; n * 7];

    for i in 0..n {
        output[i * 7 + 0] = features.run_length[i];
        output[i * 7 + 1] = features.cp_prob[i];
        output[i * 7 + 2] = features.cp_recent[i];
        output[i * 7 + 3] = features.run_length_norm[i];
        output[i * 7 + 4] = features.regime_age[i];
        output[i * 7 + 5] = features.cp_intensity[i];
        output[i * 7 + 6] = features.stability[i];
    }

    PyArray1::from_vec(py, output)
        .reshape([n, 7])
}

// =============================================================================
// GARCH Functions
// =============================================================================

/// GARCH(1,1) transform - generates 8 volatility features
///
/// Args:
///     returns: Return series (already rescaled if needed)
///     omega: GARCH omega parameter
///     alpha: GARCH alpha parameter
///     beta: GARCH beta parameter  
///     long_run_var: Long-run variance estimate
///     forecast_horizon: Steps ahead to forecast
///     zscore_window: Window for rolling z-score
///     regime_low_thresh: Vol threshold for LOW regime
///     regime_high_thresh: Vol threshold for HIGH regime
///     rescale: Rescale factor to divide outputs by
///
/// Returns:
///     2D array (n_samples, 8) with features:
///     [cond_vol, vol_forecast, vol_zscore, vol_shock, persistence, vol_regime, vol_change, vol_ratio]
#[pyfunction]
#[pyo3(signature = (
    returns,
    omega,
    alpha,
    beta,
    long_run_var,
    forecast_horizon=1,
    zscore_window=63,
    regime_low_thresh=0.0,
    regime_high_thresh=1.0,
    rescale=1.0
))]
fn py_garch_transform<'py>(
    py: Python<'py>,
    returns: PyReadonlyArray1<f64>,
    omega: f64,
    alpha: f64,
    beta: f64,
    long_run_var: f64,
    forecast_horizon: usize,
    zscore_window: usize,
    regime_low_thresh: f64,
    regime_high_thresh: f64,
    rescale: f64,
) -> PyResult<Bound<'py, PyArray2<f64>>> {
    let data = returns.as_slice().unwrap();

    let features = garch_transform(
        data,
        omega,
        alpha,
        beta,
        long_run_var,
        forecast_horizon,
        zscore_window,
        regime_low_thresh,
        regime_high_thresh,
        rescale,
    );

    // Convert to 2D array (n_samples, 8)
    let n = features.len();
    let mut output = vec![0.0; n * 8];

    for i in 0..n {
        output[i * 8 + 0] = features.cond_vol[i];
        output[i * 8 + 1] = features.vol_forecast[i];
        output[i * 8 + 2] = features.vol_zscore[i];
        output[i * 8 + 3] = features.vol_shock[i];
        output[i * 8 + 4] = features.persistence[i];
        output[i * 8 + 5] = features.vol_regime[i];
        output[i * 8 + 6] = features.vol_change[i];
        output[i * 8 + 7] = features.vol_ratio[i];
    }

    PyArray1::from_vec(py, output)
        .reshape([n, 8])
}
// =============================================================================
// EGARCH Functions
// =============================================================================

/// Compute EGARCH features using fitted parameters.
///
/// Args:
///     returns: 1D array of returns
///     omega: EGARCH omega parameter
///     alpha: EGARCH alpha parameter
///     gamma: EGARCH gamma (leverage) parameter
///     beta: EGARCH beta (persistence) parameter
///     low_vol_threshold: Threshold for LOW vol regime
///     high_vol_threshold: Threshold for HIGH vol regime
///     recent_shock_window: Window for leverage_active detection (default: 5)
///
/// Returns:
///     2D array (n_samples, 8) with columns:
///     [vol, log_vol, asymmetry, persistence, news_impact, vol_zscore, vol_regime, leverage_active]
#[pyfunction]
#[pyo3(signature = (returns, omega, alpha, gamma, beta, low_vol_threshold, high_vol_threshold, recent_shock_window=5))]
fn py_egarch_rolling_transform<'py>(
    py: Python<'py>,
    returns: PyReadonlyArray1<f64>,
    omega: f64,
    alpha: f64,
    gamma: f64,
    beta: f64,
    low_vol_threshold: f64,
    high_vol_threshold: f64,
    recent_shock_window: usize,
) -> PyResult<Bound<'py, PyArray2<f64>>> {
    let data = returns.as_slice().unwrap();

    let params = EGARCHParams {
        omega,
        alpha,
        gamma,
        beta,
    };

    let config = EGARCHConfig {
        rolling_window: 126,
        low_vol_percentile: 25.0,
        high_vol_percentile: 75.0,
        recent_shock_window,
    };

    let features = egarch_rolling_transform(data, &config, &params, low_vol_threshold, high_vol_threshold);

    // Convert to 2D array
    let n = features.vol.len();
    let mut output = vec![0.0; n * 8];

    for i in 0..n {
        output[i * 8 + 0] = features.vol[i];
        output[i * 8 + 1] = features.log_vol[i];
        output[i * 8 + 2] = features.asymmetry[i];
        output[i * 8 + 3] = features.persistence[i];
        output[i * 8 + 4] = features.news_impact[i];
        output[i * 8 + 5] = features.vol_zscore[i];
        output[i * 8 + 6] = features.vol_regime[i];
        output[i * 8 + 7] = features.leverage_active[i];
    }

    PyArray1::from_vec(py, output)
        .reshape([n, 8])
}

/// Compute EGARCH features with full rolling parameter re-estimation.
///
/// This is slower but more accurate as it re-estimates EGARCH parameters
/// for each rolling window.
///
/// Args:
///     returns: 1D array of returns
///     rolling_window: Window size for parameter estimation (default: 126)
///
/// Returns:
///     2D array (n_samples, 8) with columns:
///     [vol, log_vol, asymmetry, persistence, news_impact, vol_zscore, vol_regime, leverage_active]
#[pyfunction]
#[pyo3(signature = (returns, rolling_window=126))]
fn py_egarch_rolling_transform_full<'py>(
    py: Python<'py>,
    returns: PyReadonlyArray1<f64>,
    rolling_window: usize,
) -> PyResult<Bound<'py, PyArray2<f64>>> {
    let data = returns.as_slice().unwrap();

    let config = EGARCHConfig {
        rolling_window,
        low_vol_percentile: 25.0,
        high_vol_percentile: 75.0,
        recent_shock_window: 5,
    };

    let features = egarch_rolling_transform_full(data, &config);

    // Convert to 2D array
    let n = features.vol.len();
    let mut output = vec![0.0; n * 8];

    for i in 0..n {
        output[i * 8 + 0] = features.vol[i];
        output[i * 8 + 1] = features.log_vol[i];
        output[i * 8 + 2] = features.asymmetry[i];
        output[i * 8 + 3] = features.persistence[i];
        output[i * 8 + 4] = features.news_impact[i];
        output[i * 8 + 5] = features.vol_zscore[i];
        output[i * 8 + 6] = features.vol_regime[i];
        output[i * 8 + 7] = features.leverage_active[i];
    }

    PyArray1::from_vec(py, output)
        .reshape([n, 8])
}

/// Estimate EGARCH parameters from returns.
///
/// Args:
///     returns: 1D array of returns
///
/// Returns:
///     Tuple (omega, alpha, gamma, beta)
#[pyfunction]
fn py_egarch_estimate_params(returns: PyReadonlyArray1<f64>) -> (f64, f64, f64, f64) {
    let data = returns.as_slice().unwrap();
    let params = estimate_egarch_params(data);
    (params.omega, params.alpha, params.gamma, params.beta)
}

// =============================================================================
// CUSUM Functions
// =============================================================================

/// Compute CUSUM changepoint detection features.
///
/// Args:
///     returns: 1D array of returns
///     volatility: 1D array of volatility (or second series)
///     ret_mean: Baseline mean for returns (from fit)
///     ret_std: Baseline std for returns (from fit)
///     vol_mean: Baseline mean for volatility (from fit)
///     vol_std: Baseline std for volatility (from fit)
///     threshold: Detection threshold in std devs (default: 2.0)
///     drift: Drift term (default: 0.0)
///     min_spacing: Minimum bars between detections (default: 5)
///     rolling_window: Window for rolling normalization (default: 63)
///
/// Returns:
///     2D array (n_samples, 12) with columns:
///     [cusum_ret_pos, cusum_ret_neg, cusum_vol_pos, cusum_vol_neg,
///      cp_ret_up, cp_ret_down, cp_vol_up, cp_vol_down,
///      cp_any, cp_magnitude, days_since_cp, cp_count_21]
#[pyfunction]
#[pyo3(signature = (returns, volatility, ret_mean, ret_std, vol_mean, vol_std, threshold=2.0, drift=0.0, min_spacing=5, rolling_window=63))]
fn py_cusum_transform<'py>(
    py: Python<'py>,
    returns: PyReadonlyArray1<f64>,
    volatility: PyReadonlyArray1<f64>,
    ret_mean: f64,
    ret_std: f64,
    vol_mean: f64,
    vol_std: f64,
    threshold: f64,
    drift: f64,
    min_spacing: usize,
    rolling_window: usize,
) -> PyResult<Bound<'py, PyArray2<f64>>> {
    let ret_data = returns.as_slice().unwrap();
    let vol_data = volatility.as_slice().unwrap();

    let config = CUSUMConfig {
        threshold,
        drift,
        min_spacing,
        rolling_window,
    };

    let features = cusum_transform(ret_data, vol_data, ret_mean, ret_std, vol_mean, vol_std, &config);

    // Convert to 2D array (n_samples, 12)
    let n = features.cusum_ret_pos.len();
    let mut output = vec![0.0; n * 12];

    for i in 0..n {
        output[i * 12 + 0] = features.cusum_ret_pos[i];
        output[i * 12 + 1] = features.cusum_ret_neg[i];
        output[i * 12 + 2] = features.cusum_vol_pos[i];
        output[i * 12 + 3] = features.cusum_vol_neg[i];
        output[i * 12 + 4] = features.cp_ret_up[i];
        output[i * 12 + 5] = features.cp_ret_down[i];
        output[i * 12 + 6] = features.cp_vol_up[i];
        output[i * 12 + 7] = features.cp_vol_down[i];
        output[i * 12 + 8] = features.cp_any[i];
        output[i * 12 + 9] = features.cp_magnitude[i];
        output[i * 12 + 10] = features.days_since_cp[i];
        output[i * 12 + 11] = features.cp_count_21[i];
    }

    PyArray1::from_vec(py, output)
        .reshape([n, 12])
}

// =============================================================================
// Kalman Functions
// =============================================================================

/// Compute Kalman filter features for state estimation.
///
/// Uses a 3D state-space model: [position, velocity, acceleration]
///
/// Args:
///     signal: 1D array of observations (e.g., prices)
///     process_noise: Process noise covariance Q (default: 1e-5)
///     measurement_noise: Measurement noise covariance R (default: 1e-3)
///     dt: Time step (default: 1.0)
///
/// Returns:
///     2D array (n_samples, 7) with columns:
///     [filtered_dev, velocity, acceleration, pred_error, innovation, zscore, regime]
#[pyfunction]
#[pyo3(signature = (signal, process_noise=1e-5, measurement_noise=1e-3, dt=1.0))]
fn py_kalman_transform<'py>(
    py: Python<'py>,
    signal: PyReadonlyArray1<f64>,
    process_noise: f64,
    measurement_noise: f64,
    dt: f64,
) -> PyResult<Bound<'py, PyArray2<f64>>> {
    let data = signal.as_slice().unwrap();

    let config = KalmanConfig {
        process_noise,
        measurement_noise,
        dt,
    };

    let features = kalman_transform(data, &config);

    // Convert to 2D array (n_samples, 7)
    let n = features.velocity.len();
    let mut output = vec![0.0; n * 7];

    for i in 0..n {
        output[i * 7 + 0] = features.filtered_dev[i];
        output[i * 7 + 1] = features.velocity[i];
        output[i * 7 + 2] = features.acceleration[i];
        output[i * 7 + 3] = features.pred_error[i];
        output[i * 7 + 4] = features.innovation[i];
        output[i * 7 + 5] = features.zscore[i];
        output[i * 7 + 6] = features.regime[i];
    }

    PyArray1::from_vec(py, output)
        .reshape([n, 7])
}
