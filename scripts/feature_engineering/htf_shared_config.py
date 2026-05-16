"""Shared HTF model/label configuration constants.

This module keeps artifact-version and label-threshold values out of launchers
and tests. The launcher imports these constants and passes them into
`MultiRegimeHTFConfig`, making each run explicit about the label and feature
contract it used.
"""

from __future__ import annotations

# Bump this when model-facing artifacts must be rebuilt because a feature,
# label, helper, optimizer, or schema contract changed.
SHARED_PIPELINE_ARTIFACT_VERSION = "2026-04-14-prefit-longshort-zscore-fix-01"

# Forward-distance thresholds used by the 4-class HTF target logic.
SHARED_THRESHOLDS_BY_TF: dict[str, dict[str, float]] = {
    "5m": {"BREAKOUT": 1.6, "RISK_RATIO": 2.5},
    "15m": {"BREAKOUT": 2.1, "RISK_RATIO": 2.5},
}

# Past-distance feature windows. Values are timeframe-scaled bar counts, not
# wall-clock durations; the active `1m` target uses the `1m` entry here.
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

# Scalar label thresholds copied into `MultiRegimeHTFConfig` at launch time.
SHARED_BREAKOUT_THRESHOLD = 2.1
SHARED_RISK_RATIO = 2.5
SHARED_BREAKFREE_THRESHOLD_1M = 0.001
