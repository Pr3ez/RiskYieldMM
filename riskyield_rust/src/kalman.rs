//! Kalman Filter - Rust Implementation
//!
//! 3D State-space Kalman filter for level, velocity, acceleration estimation.
//! Provides ~175x speedup over Python implementations while preserving the
//! same explicit streaming-state contract as the Python fallback.
//!
//! Source contract:
//! - Kalman (1960): https://www.cs.unc.edu/~welch/kalman/media/pdf/Kalman1960.pdf
//! - helper live-parity rationale:
//!   notebooks/notes/htf_helper_source_backed_validity_audit_2026-04-12.md
//! - streaming-state redesign plan:
//!   notebooks/notes/htf_kalman_streaming_state_implementation_plan_2026-04-13.md
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
//! - zscore: Expanding z-score of innovation
//! - regime: Trend regime from expanding velocity z-score

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

#[derive(Clone, Debug, Default)]
pub struct RunningMoments {
    pub count: usize,
    pub sum: f64,
    pub sum_sq: f64,
}

impl RunningMoments {
    fn update(&mut self, value: f64) -> f64 {
        if !value.is_finite() {
            return 0.0;
        }
        self.count += 1;
        self.sum += value;
        self.sum_sq += value * value;
        let count = self.count as f64;
        let mean = self.sum / count;
        let var = (self.sum_sq / count - mean * mean).max(1e-10);
        (value - mean) / var.sqrt()
    }
}

#[derive(Clone, Debug)]
pub struct KalmanStreamingState {
    pub x: [f64; 3],
    pub p: [[f64; 3]; 3],
    pub innovation_stats: RunningMoments,
    pub velocity_stats: RunningMoments,
}

impl KalmanStreamingState {
    pub fn cold_start(first_observation: f64) -> Self {
        Self {
            x: [first_observation, 0.0, 0.0],
            p: Mat3::identity().data,
            innovation_stats: RunningMoments::default(),
            velocity_stats: RunningMoments::default(),
        }
    }
}

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

    fn mul_vec(&self, v: &[f64; 3]) -> [f64; 3] {
        [
            self.data[0][0] * v[0] + self.data[0][1] * v[1] + self.data[0][2] * v[2],
            self.data[1][0] * v[0] + self.data[1][1] * v[1] + self.data[1][2] * v[2],
            self.data[2][0] * v[0] + self.data[2][1] * v[1] + self.data[2][2] * v[2],
        ]
    }
}

#[derive(Clone, Debug)]
struct Vec3 {
    data: [f64; 3],
}

impl Vec3 {
    fn new(data: [f64; 3]) -> Self {
        Self { data }
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
            data: [self.data[0] * s, self.data[1] * s, self.data[2] * s],
        }
    }
}

struct KalmanFilter {
    x: Vec3,
    p: Mat3,
    f: Mat3,
    q: Mat3,
    r: f64,
}

impl KalmanFilter {
    fn new(config: &KalmanConfig) -> Self {
        let dt = config.dt;
        let q = config.process_noise;

        let f = Mat3::new([
            [1.0, dt, 0.5 * dt * dt],
            [0.0, 1.0, dt],
            [0.0, 0.0, 1.0],
        ]);

        let dt2 = dt * dt;
        let dt3 = dt2 * dt;
        let dt4 = dt3 * dt;
        let dt5 = dt4 * dt;
        let q_matrix = Mat3::new([
            [q * dt5 / 20.0, q * dt4 / 8.0, q * dt3 / 6.0],
            [q * dt4 / 8.0, q * dt3 / 3.0, q * dt2 / 2.0],
            [q * dt3 / 6.0, q * dt2 / 2.0, q * dt],
        ]);

        Self {
            x: Vec3::new([0.0, 0.0, 0.0]),
            p: Mat3::identity(),
            f,
            q: q_matrix,
            r: config.measurement_noise,
        }
    }

    fn from_state(config: &KalmanConfig, state: &KalmanStreamingState) -> Self {
        let mut filter = Self::new(config);
        filter.x = Vec3::new(state.x);
        filter.p = Mat3::new(state.p);
        filter
    }

    fn predict(&mut self) {
        let x_pred = self.f.mul_vec(&self.x.data);
        self.x = Vec3::new(x_pred);

        let f_t = self.f.transpose();
        self.p = self.f.mul(&self.p).mul(&f_t).add(&self.q);
    }

    fn update(&mut self, z: f64) -> (f64, f64) {
        let innovation = z - self.x.data[0];
        let s = self.p.data[0][0] + self.r;
        let k = Vec3::new([
            self.p.data[0][0] / s,
            self.p.data[1][0] / s,
            self.p.data[2][0] / s,
        ]);

        self.x = self.x.add(&k.scale(innovation));

        let kh = Mat3::new([
            [k.data[0], 0.0, 0.0],
            [k.data[1], 0.0, 0.0],
            [k.data[2], 0.0, 0.0],
        ]);
        let i_kh = Mat3::identity().sub(&kh);
        self.p = i_kh.mul(&self.p);

        let pred_error = z - self.x.data[0];
        (innovation, pred_error)
    }
}

pub fn kalman_transform(signal: &[f64], config: &KalmanConfig) -> KalmanFeatures {
    let (features, _) = kalman_transform_with_state(signal, config, None);
    features
}

pub fn kalman_transform_with_state(
    signal: &[f64],
    config: &KalmanConfig,
    initial_state: Option<&KalmanStreamingState>,
) -> (KalmanFeatures, KalmanStreamingState) {
    let n = signal.len();
    let mut filtered_dev = vec![0.0; n];
    let mut velocity = vec![0.0; n];
    let mut acceleration = vec![0.0; n];
    let mut pred_error = vec![0.0; n];
    let mut innovation = vec![0.0; n];
    let mut zscore = vec![0.0; n];
    let mut regime = vec![1.0; n];

    let mut state = if let Some(existing) = initial_state {
        existing.clone()
    } else {
        KalmanStreamingState::cold_start(signal.first().copied().unwrap_or(0.0))
    };

    if n == 0 {
        return (
            KalmanFeatures {
                filtered_dev,
                velocity,
                acceleration,
                pred_error,
                innovation,
                zscore,
                regime,
            },
            state,
        );
    }

    let mut kf = KalmanFilter::from_state(config, &state);

    for i in 0..n {
        let z = signal[i];
        kf.predict();
        let (innov, err) = kf.update(z);

        filtered_dev[i] = kf.x.data[0] - z;
        velocity[i] = kf.x.data[1];
        acceleration[i] = kf.x.data[2];
        pred_error[i] = err;
        innovation[i] = innov;
        zscore[i] = state.innovation_stats.update(innov);

        let velocity_z = state.velocity_stats.update(kf.x.data[1]);
        regime[i] = if velocity_z > 1.0 {
            2.0
        } else if velocity_z < -1.0 {
            0.0
        } else {
            1.0
        };
    }

    state.x = kf.x.data;
    state.p = kf.p.data;

    (
        KalmanFeatures {
            filtered_dev,
            velocity,
            acceleration,
            pred_error,
            innovation,
            zscore,
            regime,
        },
        state,
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    fn assert_close(lhs: f64, rhs: f64, tol: f64) {
        assert!(
            (lhs - rhs).abs() <= tol,
            "lhs={} rhs={} tol={}",
            lhs,
            rhs,
            tol
        );
    }

    #[test]
    fn test_kalman_basic() {
        let signal = vec![1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.4, 1.3, 1.2, 1.1];
        let config = KalmanConfig::default();
        let features = kalman_transform(&signal, &config);
        assert_eq!(features.velocity.len(), signal.len());
        assert_eq!(features.filtered_dev.len(), signal.len());
        assert!(features.velocity[5] > 0.0);
    }

    #[test]
    fn test_state_handoff_matches_one_pass() {
        let signal: Vec<f64> = (0..120)
            .map(|i| 100.0 + (i as f64) * 0.05 + ((i % 7) as f64) * 0.01)
            .collect();
        let config = KalmanConfig::default();

        let (full_features, full_state) = kalman_transform_with_state(&signal, &config, None);
        let (first_features, first_state) = kalman_transform_with_state(&signal[..70], &config, None);
        let (second_features, second_state) =
            kalman_transform_with_state(&signal[70..], &config, Some(&first_state));

        assert_eq!(first_features.velocity.len(), 70);
        assert_eq!(second_features.velocity.len(), 50);

        for idx in 0..50 {
            assert_close(full_features.filtered_dev[70 + idx], second_features.filtered_dev[idx], 1e-10);
            assert_close(full_features.velocity[70 + idx], second_features.velocity[idx], 1e-10);
            assert_close(full_features.acceleration[70 + idx], second_features.acceleration[idx], 1e-10);
            assert_close(full_features.pred_error[70 + idx], second_features.pred_error[idx], 1e-10);
            assert_close(full_features.innovation[70 + idx], second_features.innovation[idx], 1e-10);
            assert_close(full_features.zscore[70 + idx], second_features.zscore[idx], 1e-10);
            assert_close(full_features.regime[70 + idx], second_features.regime[idx], 1e-10);
        }

        for i in 0..3 {
            assert_close(full_state.x[i], second_state.x[i], 1e-10);
            for j in 0..3 {
                assert_close(full_state.p[i][j], second_state.p[i][j], 1e-10);
            }
        }
        assert_eq!(full_state.innovation_stats.count, second_state.innovation_stats.count);
        assert_eq!(full_state.velocity_stats.count, second_state.velocity_stats.count);
        assert_close(full_state.innovation_stats.sum, second_state.innovation_stats.sum, 1e-10);
        assert_close(full_state.innovation_stats.sum_sq, second_state.innovation_stats.sum_sq, 1e-10);
        assert_close(full_state.velocity_stats.sum, second_state.velocity_stats.sum, 1e-10);
        assert_close(full_state.velocity_stats.sum_sq, second_state.velocity_stats.sum_sq, 1e-10);
    }
}
