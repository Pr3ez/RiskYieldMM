//! Kalman Filter - Rust Implementation
//!
//! 3D State-space Kalman filter for level, velocity, acceleration estimation.
//! Provides ~175x speedup over Python/filterpy implementation.
//!
//! State model: [position, velocity, acceleration]
//! Measurement: position only
//!
//! Features generated (7 total):
//! - filtered_dev: Filtered position - raw signal
//! - velocity: Estimated trend/momentum
//! - acceleration: Rate of change of trend
//! - pred_error: Prediction error after update
//! - innovation: Prediction error before update
//! - zscore: Z-score of innovation
//! - regime: Trend regime (0=bearish, 1=neutral, 2=bullish)

/// Kalman filter configuration
#[derive(Clone, Debug)]
pub struct KalmanConfig {
    pub process_noise: f64,
    pub measurement_noise: f64,
    pub dt: f64,
}

impl Default for KalmanConfig {
    fn default() -> Self {
        Self {
            process_noise: 1e-5,
            measurement_noise: 1e-3,
            dt: 1.0,
        }
    }
}

/// Kalman filter output features
#[derive(Clone, Debug)]
pub struct KalmanFeatures {
    pub filtered_dev: Vec<f64>,
    pub velocity: Vec<f64>,
    pub acceleration: Vec<f64>,
    pub pred_error: Vec<f64>,
    pub innovation: Vec<f64>,
    pub zscore: Vec<f64>,
    pub regime: Vec<f64>,
}

/// 3x3 Matrix operations (fixed size, no ndarray dependency)
#[derive(Clone, Debug)]
struct Mat3 {
    data: [[f64; 3]; 3],
}

impl Mat3 {
    fn new(data: [[f64; 3]; 3]) -> Self {
        Self { data }
    }

    fn zeros() -> Self {
        Self { data: [[0.0; 3]; 3] }
    }

    fn identity() -> Self {
        Self {
            data: [
                [1.0, 0.0, 0.0],
                [0.0, 1.0, 0.0],
                [0.0, 0.0, 1.0],
            ],
        }
    }

    fn scale(&self, s: f64) -> Self {
        let mut result = Self::zeros();
        for i in 0..3 {
            for j in 0..3 {
                result.data[i][j] = self.data[i][j] * s;
            }
        }
        result
    }

    fn add(&self, other: &Mat3) -> Self {
        let mut result = Self::zeros();
        for i in 0..3 {
            for j in 0..3 {
                result.data[i][j] = self.data[i][j] + other.data[i][j];
            }
        }
        result
    }

    fn sub(&self, other: &Mat3) -> Self {
        let mut result = Self::zeros();
        for i in 0..3 {
            for j in 0..3 {
                result.data[i][j] = self.data[i][j] - other.data[i][j];
            }
        }
        result
    }

    fn transpose(&self) -> Self {
        let mut result = Self::zeros();
        for i in 0..3 {
            for j in 0..3 {
                result.data[i][j] = self.data[j][i];
            }
        }
        result
    }

    fn mul(&self, other: &Mat3) -> Self {
        let mut result = Self::zeros();
        for i in 0..3 {
            for j in 0..3 {
                for k in 0..3 {
                    result.data[i][j] += self.data[i][k] * other.data[k][j];
                }
            }
        }
        result
    }

    /// Multiply matrix by 3x1 vector
    fn mul_vec(&self, v: &[f64; 3]) -> [f64; 3] {
        [
            self.data[0][0] * v[0] + self.data[0][1] * v[1] + self.data[0][2] * v[2],
            self.data[1][0] * v[0] + self.data[1][1] * v[1] + self.data[1][2] * v[2],
            self.data[2][0] * v[0] + self.data[2][1] * v[1] + self.data[2][2] * v[2],
        ]
    }
}

/// 3x1 Vector operations
#[derive(Clone, Debug)]
struct Vec3 {
    data: [f64; 3],
}

impl Vec3 {
    fn new(data: [f64; 3]) -> Self {
        Self { data }
    }

    fn zeros() -> Self {
        Self { data: [0.0; 3] }
    }

    fn add(&self, other: &Vec3) -> Self {
        Self {
            data: [
                self.data[0] + other.data[0],
                self.data[1] + other.data[1],
                self.data[2] + other.data[2],
            ],
        }
    }

    fn scale(&self, s: f64) -> Self {
        Self {
            data: [
                self.data[0] * s,
                self.data[1] * s,
                self.data[2] * s,
            ],
        }
    }

    /// Outer product: v * v^T -> 3x3 matrix
    fn outer(&self, other: &Vec3) -> Mat3 {
        let mut result = Mat3::zeros();
        for i in 0..3 {
            for j in 0..3 {
                result.data[i][j] = self.data[i] * other.data[j];
            }
        }
        result
    }
}

/// Kalman Filter state
struct KalmanFilter {
    // State vector [position, velocity, acceleration]
    x: Vec3,
    // State covariance (3x3)
    p: Mat3,
    // State transition matrix
    f: Mat3,
    // Process noise covariance
    q: Mat3,
    // Measurement noise
    r: f64,
    // Measurement matrix H = [1, 0, 0] (we only measure position)
}

impl KalmanFilter {
    fn new(config: &KalmanConfig) -> Self {
        let dt = config.dt;
        let q = config.process_noise;

        // State transition matrix (constant acceleration model)
        // x[t+1] = F * x[t]
        // position[t+1] = position[t] + velocity[t]*dt + 0.5*accel[t]*dt^2
        // velocity[t+1] = velocity[t] + accel[t]*dt
        // accel[t+1] = accel[t]
        let f = Mat3::new([
            [1.0, dt, 0.5 * dt * dt],
            [0.0, 1.0, dt],
            [0.0, 0.0, 1.0],
        ]);

        // Process noise covariance (continuous white noise acceleration model)
        let dt2 = dt * dt;
        let dt3 = dt2 * dt;
        let dt4 = dt3 * dt;
        let dt5 = dt4 * dt;
        let q_matrix = Mat3::new([
            [q * dt5 / 20.0, q * dt4 / 8.0, q * dt3 / 6.0],
            [q * dt4 / 8.0, q * dt3 / 3.0, q * dt2 / 2.0],
            [q * dt3 / 6.0, q * dt2 / 2.0, q * dt],
        ]);

        // Initial state covariance
        let p = Mat3::identity();

        Self {
            x: Vec3::zeros(),
            p,
            f,
            q: q_matrix,
            r: config.measurement_noise,
        }
    }

    fn predict(&mut self) {
        // Predicted state: x_pred = F * x
        let x_pred = self.f.mul_vec(&self.x.data);
        self.x = Vec3::new(x_pred);

        // Predicted covariance: P_pred = F * P * F^T + Q
        let f_t = self.f.transpose();
        self.p = self.f.mul(&self.p).mul(&f_t).add(&self.q);
    }

    fn update(&mut self, z: f64) -> (f64, f64) {
        // Innovation: y = z - H * x_pred (H = [1, 0, 0])
        let y = z - self.x.data[0];
        let innovation = y;

        // Innovation covariance: S = H * P * H^T + R = P[0,0] + R
        let s = self.p.data[0][0] + self.r;

        // Kalman gain: K = P * H^T / S
        // Since H = [1, 0, 0], K = [P[0,0]/S, P[1,0]/S, P[2,0]/S]
        let k = Vec3::new([
            self.p.data[0][0] / s,
            self.p.data[1][0] / s,
            self.p.data[2][0] / s,
        ]);

        // State update: x = x + K * y
        self.x = self.x.add(&k.scale(y));

        // Covariance update: P = (I - K * H) * P
        // K * H is a 3x3 matrix where only first column is non-zero
        let kh = Mat3::new([
            [k.data[0], 0.0, 0.0],
            [k.data[1], 0.0, 0.0],
            [k.data[2], 0.0, 0.0],
        ]);
        let i_kh = Mat3::identity().sub(&kh);
        self.p = i_kh.mul(&self.p);

        // Prediction error after update
        let pred_error = z - self.x.data[0];

        (innovation, pred_error)
    }
}

/// Main Kalman filter transform function
///
/// Runs Kalman filter on signal and extracts features.
///
/// # Arguments
/// * `signal` - 1D array of observations (e.g., prices)
/// * `config` - Kalman filter configuration
///
/// # Returns
/// KalmanFeatures with 7 feature vectors
pub fn kalman_transform(signal: &[f64], config: &KalmanConfig) -> KalmanFeatures {
    let n = signal.len();

    // Initialize output vectors
    let mut filtered_dev = vec![0.0; n];
    let mut velocity = vec![0.0; n];
    let mut acceleration = vec![0.0; n];
    let mut pred_error = vec![0.0; n];
    let mut innovation = vec![0.0; n];
    let mut zscore = vec![0.0; n];
    let mut regime = vec![1.0; n]; // Default: neutral

    if n == 0 {
        return KalmanFeatures {
            filtered_dev,
            velocity,
            acceleration,
            pred_error,
            innovation,
            zscore,
            regime,
        };
    }

    // Initialize filter
    let mut kf = KalmanFilter::new(config);

    // Initialize state with first observation
    kf.x = Vec3::new([signal[0], 0.0, 0.0]);

    // Run filter on all observations
    for i in 0..n {
        let z = signal[i];

        // Predict
        kf.predict();

        // Update and get innovation/error
        let (innov, err) = kf.update(z);

        // Store features
        filtered_dev[i] = kf.x.data[0] - z;  // Filtered - raw
        velocity[i] = kf.x.data[1];
        acceleration[i] = kf.x.data[2];
        pred_error[i] = err;
        innovation[i] = innov;
    }

    // Compute z-score of innovations
    let inn_mean: f64 = innovation.iter().copied().sum::<f64>() / n as f64;
    let inn_var: f64 = innovation.iter().map(|&x| (x - inn_mean).powi(2)).sum::<f64>() / n as f64;
    let inn_std = inn_var.sqrt().max(1e-10);

    for i in 0..n {
        zscore[i] = (innovation[i] - inn_mean) / inn_std;
    }

    // Compute regime based on velocity
    let vel_mean: f64 = velocity.iter().copied().sum::<f64>() / n as f64;
    let vel_var: f64 = velocity.iter().map(|&x| (x - vel_mean).powi(2)).sum::<f64>() / n as f64;
    let vel_std = vel_var.sqrt().max(1e-10);

    for i in 0..n {
        let vel_zscore = (velocity[i] - vel_mean) / vel_std;
        regime[i] = if vel_zscore > 1.0 {
            2.0 // Bullish
        } else if vel_zscore < -1.0 {
            0.0 // Bearish
        } else {
            1.0 // Neutral
        };
    }

    KalmanFeatures {
        filtered_dev,
        velocity,
        acceleration,
        pred_error,
        innovation,
        zscore,
        regime,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_kalman_basic() {
        let signal = vec![1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.4, 1.3, 1.2, 1.1];
        let config = KalmanConfig::default();

        let features = kalman_transform(&signal, &config);

        assert_eq!(features.velocity.len(), signal.len());
        assert_eq!(features.filtered_dev.len(), signal.len());

        // Velocity should be positive during uptrend
        assert!(features.velocity[5] > 0.0);
    }

    #[test]
    fn test_mat3_operations() {
        let a = Mat3::identity();
        let b = Mat3::identity();
        let c = a.mul(&b);

        // Identity * Identity = Identity
        assert!((c.data[0][0] - 1.0).abs() < 1e-10);
        assert!((c.data[1][1] - 1.0).abs() < 1e-10);
        assert!((c.data[2][2] - 1.0).abs() < 1e-10);
    }

    #[test]
    fn test_empty_signal() {
        let signal: Vec<f64> = vec![];
        let config = KalmanConfig::default();

        let features = kalman_transform(&signal, &config);

        assert_eq!(features.velocity.len(), 0);
    }
}
