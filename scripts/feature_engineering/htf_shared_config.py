from __future__ import annotations

SHARED_PIPELINE_ARTIFACT_VERSION = "2026-03-06-repair-01"

SHARED_THRESHOLDS_BY_TF: dict[str, dict[str, float]] = {
    "5m": {"BREAKOUT": 1.6, "RISK_RATIO": 2.5},
    "15m": {"BREAKOUT": 2.1, "RISK_RATIO": 2.5},
}

SHARED_DISTANCE_WINDOWS_BY_TF: dict[str, dict[str, int]] = {
    "1m": {
        "dist_avg_high": 240,
        "dist_avg_low": 240,
        "dist_top5_high": 240,
        "dist_bot5_low": 120,
    },
    "5m": {
        "dist_avg_high": 48,
        "dist_avg_low": 48,
        "dist_top5_high": 48,
        "dist_bot5_low": 24,
    },
    "15m": {
        "dist_avg_high": 16,
        "dist_avg_low": 16,
        "dist_top5_high": 16,
        "dist_bot5_low": 8,
    },
}

SHARED_BREAKOUT_THRESHOLD = 2.1
SHARED_RISK_RATIO = 2.5
SHARED_BREAKFREE_THRESHOLD_1M = 0.001
