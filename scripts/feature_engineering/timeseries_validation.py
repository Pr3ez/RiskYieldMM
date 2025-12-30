"""
Time-Series Feature Validation for RiskYieldMM
==============================================
Critical checks specific to time-series ML that prevent data leakage
and ensure feature quality for temporal prediction tasks.

PRODUCTION DATA CONTRACT (Critical for No Leakage)
--------------------------------------------------
In production, models ONLY run at 8h bar boundaries (00:00, 08:00, 16:00 UTC).
No partial/intraday data is ever used.

At prediction time (e.g., 08:00 UTC):
  - Latest available row: timestamp 00:00 (bar [00:00→08:00] just closed)
  - All OHLCV/OI/L-S data is from COMPLETED bars only
  - Funding at 08:00 just settled → available

This guarantees:
  - compute_features.py is prediction-time safe
  - Features on last row use only closed bar data
  - No future information leakage possible

Checks:
1. Stationarity (ADF test) - non-stationary features cause spurious correlations
2. Look-ahead bias - features must not use future data
3. Temporal continuity - detect gaps in timestamps
4. Rolling window integrity - ensure only past data used
5. Target leakage detection - correlation with target at lag 0 is suspicious
6. Feature importance baseline - compare against random features

Academic References:
- Tsay (2005) "Analysis of Financial Time Series"
- Hyndman & Athanasopoulos (2021) "Forecasting: Principles and Practice"
- scikit-learn TimeSeriesSplit documentation

Author: RiskYieldMM Project
Created: 2025-12-20
Updated: 2025-12-22 - Added data fetch contract documentation
"""

import numpy as np
import pandas as pd

# =============================================================================
# STATIONARITY TESTS
# =============================================================================


def adf_test(series: pd.Series, significance: float = 0.05) -> dict:
    """
    Augmented Dickey-Fuller test for stationarity.

    Null hypothesis: Series has a unit root (non-stationary)

    Args:
        series: Time series to test
        significance: p-value threshold (default 0.05)

    Returns:
        Dict with test results
    """
    try:
        from statsmodels.tsa.stattools import adfuller

        clean = series.dropna()
        if len(clean) < 20:
            return {"error": "Insufficient data for ADF test", "is_stationary": None}

        result = adfuller(clean, autolag="AIC")

        return {
            "adf_statistic": result[0],
            "p_value": result[1],
            "used_lag": result[2],
            "n_obs": result[3],
            "critical_values": result[4],
            "is_stationary": result[1] < significance,
            "interpretation": "stationary"
            if result[1] < significance
            else "non-stationary",
        }
    except ImportError:
        return {
            "error": "statsmodels not installed. Run: pip install statsmodels",
            "is_stationary": None,
        }
    except Exception as e:
        return {"error": str(e), "is_stationary": None}


def check_stationarity_all(features: pd.DataFrame, significance: float = 0.05) -> dict:
    """
    Check stationarity of all features.

    Returns summary with counts and list of non-stationary features.
    """
    feature_cols = [c for c in features.columns if c != "timestamp"]

    results = {
        "n_tested": 0,
        "n_stationary": 0,
        "n_non_stationary": 0,
        "n_failed": 0,
        "stationary": [],
        "non_stationary": [],
        "failed": [],
    }

    for col in feature_cols:
        result = adf_test(features[col], significance)
        results["n_tested"] += 1

        if "error" in result:
            results["n_failed"] += 1
            results["failed"].append((col, result["error"]))
        elif result["is_stationary"]:
            results["n_stationary"] += 1
            results["stationary"].append((col, result["p_value"]))
        else:
            results["n_non_stationary"] += 1
            results["non_stationary"].append((col, result["p_value"]))

    return results


# =============================================================================
# TEMPORAL CONTINUITY
# =============================================================================


def check_temporal_continuity(
    df: pd.DataFrame, timestamp_col: str = "timestamp", expected_freq_hours: int = 8
) -> dict:
    """
    Check for gaps in time series.

    Args:
        df: DataFrame with timestamp column
        timestamp_col: Name of timestamp column
        expected_freq_hours: Expected frequency in hours (8 for 8h bars)

    Returns:
        Dict with gap analysis
    """
    if timestamp_col not in df.columns:
        return {"error": f"Column {timestamp_col} not found"}

    ts = pd.to_datetime(df[timestamp_col])

    # Calculate time differences
    diffs = ts.diff().dt.total_seconds() / 3600  # Convert to hours

    # Find gaps (> expected frequency)
    gap_threshold = expected_freq_hours * 1.5  # 50% tolerance
    gaps = diffs[diffs > gap_threshold].dropna()

    results = {
        "total_rows": len(df),
        "expected_freq_hours": expected_freq_hours,
        "start_date": ts.min().isoformat(),
        "end_date": ts.max().isoformat(),
        "n_gaps": len(gaps),
        "total_gap_hours": gaps.sum() if len(gaps) > 0 else 0,
        "is_continuous": len(gaps) == 0,
        "gaps": [],
    }

    # Record individual gaps
    for idx in gaps.index:
        gap_start = ts.iloc[idx - 1]
        gap_end = ts.iloc[idx]
        gap_hours = (gap_end - gap_start).total_seconds() / 3600
        results["gaps"].append(
            {
                "start": gap_start.isoformat(),
                "end": gap_end.isoformat(),
                "hours": gap_hours,
            }
        )

    return results


# =============================================================================
# LOOK-AHEAD BIAS DETECTION
# =============================================================================


def check_look_ahead_bias(
    features: pd.DataFrame, target: pd.Series, max_lag: int = 10
) -> dict:
    """
    Detect potential look-ahead bias by analyzing lead/lag correlations.

    If correlation at lag 0 is higher than at lag 1, it's suspicious.
    Features should predict FUTURE, not explain PRESENT.

    Args:
        features: Feature DataFrame
        target: Target variable (e.g., future returns)
        max_lag: Maximum lag to check

    Returns:
        Dict with suspicious features
    """
    feature_cols = [c for c in features.columns if c != "timestamp"]

    results = {"suspicious_features": [], "clean_features": [], "details": {}}

    for col in feature_cols:
        correlations = {}

        # Compute correlation at different lags
        for lag in range(-max_lag, max_lag + 1):
            if lag < 0:
                # Feature leads target (future feature with past target)
                shifted_target = target.shift(-lag)
            else:
                # Feature lags target (past feature with future target - what we want)
                shifted_target = target.shift(lag)

            valid = ~(features[col].isna() | shifted_target.isna())
            if valid.sum() > 30:
                corr = features[col][valid].corr(shifted_target[valid])
                correlations[lag] = corr

        # Analyze pattern
        if correlations:
            corr_at_0 = abs(correlations.get(0, 0))
            corr_at_1 = abs(correlations.get(1, 0))

            # Suspicious if lag 0 correlation is much higher than lag 1
            if corr_at_0 > 0.5 and corr_at_0 > corr_at_1 * 1.5:
                results["suspicious_features"].append(col)
                results["details"][col] = {
                    "corr_lag_0": corr_at_0,
                    "corr_lag_1": corr_at_1,
                    "reason": "High correlation at lag 0 suggests contemporaneous relationship",
                }
            else:
                results["clean_features"].append(col)

    return results


# =============================================================================
# ROLLING WINDOW INTEGRITY
# =============================================================================


def verify_rolling_window_integrity(df: pd.DataFrame, features: pd.DataFrame) -> dict:
    """
    Verify that rolling features only use past data.

    Checks:
    1. NaN pattern matches expected warmup period
    2. No sudden value changes that suggest future data

    Note:
    - EWM-based features (atr, ema) have different warmup characteristics
    - Some features intentionally use min_periods=1 for early data availability
      (funding, premium) - this is valid but flagged for awareness

    Returns:
        Dict with verification results
    """
    feature_cols = [c for c in features.columns if c != "timestamp"]

    # Features that use EWM (exponential weighted moving average) have no warmup
    ewm_indicators = ["atr", "ema", "ppo", "momAtr"]

    # Features that intentionally use min_periods=1 for early data availability
    min_periods_1_ok = ["funding", "premium"]

    results = {
        "verified": [],
        "suspicious": [],
        "ewm_features": [],
        "intentional_min_periods": [],  # Valid but early-starting features
        "details": {},
    }

    for col in feature_cols:
        # Check if this is an EWM-based feature
        is_ewm = any(ind.lower() in col.lower() for ind in ewm_indicators)

        if is_ewm:
            results["ewm_features"].append(col)
            results["verified"].append(col)
            continue

        # Check if this is an intentional min_periods=1 feature
        is_min_periods_ok = any(ind.lower() in col.lower() for ind in min_periods_1_ok)

        # Extract period from column name if present
        period = None
        for token in col.split("_"):
            if token.isdigit():
                period = int(token)
                break

        if period is None:
            # Non-period feature, skip detailed check
            results["verified"].append(col)
            continue

        # Check NaN pattern
        first_valid_idx = features[col].first_valid_index()

        if first_valid_idx is not None:
            warmup_rows = first_valid_idx
            expected_warmup = period - 1

            if warmup_rows < expected_warmup * 0.5:
                if is_min_periods_ok:
                    # This is expected behavior for funding/premium features
                    results["intentional_min_periods"].append(col)
                    results["verified"].append(col)
                else:
                    results["suspicious"].append(col)
                    results["details"][col] = {
                        "warmup_rows": warmup_rows,
                        "expected_minimum": expected_warmup,
                        "reason": "Insufficient warmup suggests min_periods was too low or future data used",
                    }
            else:
                results["verified"].append(col)
        else:
            results["suspicious"].append(col)
            results["details"][col] = {"reason": "All NaN values"}

    return results


# =============================================================================
# FEATURE IMPORTANCE BASELINE (Random Feature Test)
# =============================================================================


def random_feature_baseline(
    features: pd.DataFrame, target: pd.Series, n_random: int = 5, seed: int = 42
) -> dict:
    """
    Create random features and compare importance with real features.

    Good features should have higher correlation with target than random.

    Args:
        features: Real features DataFrame
        target: Target variable
        n_random: Number of random features to generate
        seed: Random seed

    Returns:
        Dict with baseline comparison
    """
    np.random.seed(seed)
    n_rows = len(features)
    feature_cols = [c for c in features.columns if c != "timestamp"]

    # Generate random features
    random_corrs = []
    for _ in range(n_random):
        random_feat = pd.Series(np.random.randn(n_rows))
        valid = ~(random_feat.isna() | target.isna())
        if valid.sum() > 30:
            corr = abs(random_feat[valid].corr(target[valid]))
            random_corrs.append(corr)

    random_mean = np.mean(random_corrs)
    random_std = np.std(random_corrs)
    random_threshold = random_mean + 2 * random_std  # 95% threshold

    # Compare real features
    results = {
        "random_mean_corr": random_mean,
        "random_std_corr": random_std,
        "significance_threshold": random_threshold,
        "above_random": [],
        "below_random": [],
        "details": {},
    }

    for col in feature_cols:
        valid = ~(features[col].isna() | target.isna())
        if valid.sum() > 30:
            corr = abs(features[col][valid].corr(target[valid]))

            results["details"][col] = {
                "correlation": corr,
                "above_random": corr > random_threshold,
            }

            if corr > random_threshold:
                results["above_random"].append((col, corr))
            else:
                results["below_random"].append((col, corr))

    # Sort by correlation
    results["above_random"] = sorted(
        results["above_random"], key=lambda x: x[1], reverse=True
    )
    results["below_random"] = sorted(
        results["below_random"], key=lambda x: x[1], reverse=True
    )

    return results


# =============================================================================
# VARIANCE INFLATION FACTOR (VIF) - Multicollinearity
# =============================================================================


def calculate_vif(features: pd.DataFrame, max_features: int = 50) -> dict:
    """
    Calculate Variance Inflation Factor for multicollinearity detection.

    VIF > 5 indicates high multicollinearity
    VIF > 10 indicates severe multicollinearity (problematic for linear models)

    Args:
        features: Feature DataFrame
        max_features: Max features to analyze (VIF is O(n²))

    Returns:
        Dict with VIF values
    """
    try:
        from statsmodels.stats.outliers_influence import variance_inflation_factor

        feature_cols = [c for c in features.columns if c != "timestamp"][:max_features]

        # Remove rows with any NaN
        clean = features[feature_cols].dropna()

        if len(clean) < len(feature_cols) + 10:
            return {"error": "Insufficient data for VIF calculation"}

        # Add constant term
        X = clean.values

        results = {
            "vif_values": {},
            "high_vif": [],  # VIF > 5
            "severe_vif": [],  # VIF > 10
        }

        for i, col in enumerate(feature_cols):
            try:
                vif = variance_inflation_factor(X, i)
                results["vif_values"][col] = vif

                if vif > 10:
                    results["severe_vif"].append((col, vif))
                elif vif > 5:
                    results["high_vif"].append((col, vif))
            except Exception as e:
                results["vif_values"][col] = f"Error: {e}"

        return results

    except ImportError:
        return {"error": "statsmodels not installed. Run: pip install statsmodels"}


# =============================================================================
# COMPREHENSIVE TIME-SERIES VALIDATION
# =============================================================================


def validate_timeseries_features(
    df: pd.DataFrame,
    features: pd.DataFrame,
    target: pd.Series = None,
    verbose: bool = True,
) -> dict:
    """
    Run all time-series specific validations.

    Args:
        df: Raw data DataFrame
        features: Computed features DataFrame
        target: Optional target variable for leakage detection
        verbose: Print results

    Returns:
        Comprehensive validation results
    """
    results = {
        "temporal_continuity": None,
        "stationarity": None,
        "rolling_integrity": None,
        "look_ahead_bias": None,
        "random_baseline": None,
        "multicollinearity": None,
        "overall_status": "PASS",
    }

    issues = []
    warnings = []

    # 1. Temporal Continuity
    if verbose:
        print("\n" + "=" * 60)
        print("TIME-SERIES FEATURE VALIDATION")
        print("=" * 60)
        print("\n1. TEMPORAL CONTINUITY CHECK")
        print("-" * 40)

    continuity = check_temporal_continuity(df)
    results["temporal_continuity"] = continuity

    if verbose:
        print(
            f"   Date range: {continuity['start_date'][:10]} → {continuity['end_date'][:10]}"
        )
        print(f"   Total rows: {continuity['total_rows']:,}")
        print(f"   Gaps found: {continuity['n_gaps']}")

    if continuity["n_gaps"] > 0:
        issues.append(f"Found {continuity['n_gaps']} temporal gaps")
        if verbose:
            for gap in continuity["gaps"][:3]:
                print(
                    f"   ⚠️ Gap: {gap['start'][:16]} → {gap['end'][:16]} ({gap['hours']:.0f}h)"
                )
    else:
        if verbose:
            print("   ✓ No gaps detected")

    # 2. Stationarity Check
    if verbose:
        print("\n2. STATIONARITY CHECK (ADF Test)")
        print("-" * 40)

    stationarity = check_stationarity_all(features)
    results["stationarity"] = stationarity

    if verbose:
        print(f"   Stationary: {stationarity['n_stationary']}")
        print(f"   Non-stationary: {stationarity['n_non_stationary']}")
        print(f"   Failed: {stationarity['n_failed']}")

    if stationarity["n_non_stationary"] > 0:
        warnings.append(f"{stationarity['n_non_stationary']} non-stationary features")
        if verbose:
            print("   ⚠️ Non-stationary features:")
            for col, pval in stationarity["non_stationary"][:5]:
                print(f"      - {col[:40]} (p={pval:.4f})")

    # 3. Rolling Window Integrity
    if verbose:
        print("\n3. ROLLING WINDOW INTEGRITY")
        print("-" * 40)

    rolling = verify_rolling_window_integrity(df, features)
    results["rolling_integrity"] = rolling

    if verbose:
        print(f"   Verified: {len(rolling['verified'])}")
        print(
            f"   EWM-based (no warmup needed): {len(rolling.get('ewm_features', []))}"
        )
        print(
            f"   Intentional min_periods=1: {len(rolling.get('intentional_min_periods', []))}"
        )
        print(f"   Suspicious: {len(rolling['suspicious'])}")

    if rolling.get("intentional_min_periods"):
        if verbose:
            print("   ℹ️ Features with early data availability (by design):")
            for col in rolling["intentional_min_periods"][:3]:
                print(f"      - {col}")
            if len(rolling["intentional_min_periods"]) > 3:
                print(
                    f"      ... and {len(rolling['intentional_min_periods']) - 3} more"
                )

    if rolling["suspicious"]:
        issues.append(f"{len(rolling['suspicious'])} features with suspicious warmup")
        if verbose:
            for col in rolling["suspicious"][:3]:
                detail = rolling["details"].get(col, {})
                print(f"   ⚠️ {col}: {detail.get('reason', 'Unknown issue')}")
    else:
        if verbose:
            print("   ✓ All rolling features have proper warmup")

    # 4. Look-ahead Bias (if target provided)
    if target is not None:
        if verbose:
            print("\n4. LOOK-AHEAD BIAS CHECK")
            print("-" * 40)

        look_ahead = check_look_ahead_bias(features, target)
        results["look_ahead_bias"] = look_ahead

        if verbose:
            print(f"   Clean features: {len(look_ahead['clean_features'])}")
            print(f"   Suspicious: {len(look_ahead['suspicious_features'])}")

        if look_ahead["suspicious_features"]:
            issues.append(
                f"{len(look_ahead['suspicious_features'])} features with potential look-ahead bias"
            )
            if verbose:
                for col in look_ahead["suspicious_features"][:3]:
                    detail = look_ahead["details"][col]
                    print(
                        f"   ⚠️ {col}: lag0={detail['corr_lag_0']:.3f} vs lag1={detail['corr_lag_1']:.3f}"
                    )
        else:
            if verbose:
                print("   ✓ No look-ahead bias detected")

        # 5. Random Feature Baseline
        if verbose:
            print("\n5. RANDOM FEATURE BASELINE")
            print("-" * 40)

        baseline = random_feature_baseline(features, target)
        results["random_baseline"] = baseline

        if verbose:
            print(
                f"   Random correlation threshold: {baseline['significance_threshold']:.4f}"
            )
            print(f"   Features above random: {len(baseline['above_random'])}")
            print(f"   Features below random: {len(baseline['below_random'])}")

            if baseline["below_random"]:
                warnings.append(
                    f"{len(baseline['below_random'])} features not better than random"
                )
                print("   ⚠️ Top 'worse than random' features:")
                for col, corr in baseline["below_random"][:3]:
                    print(f"      - {col[:35]} (r={corr:.4f})")

    # Summary
    if verbose:
        print("\n" + "=" * 60)
        print("VALIDATION SUMMARY")
        print("=" * 60)

    if issues:
        results["overall_status"] = "FAIL"
        if verbose:
            print("\n❌ ISSUES (must fix):")
            for issue in issues:
                print(f"   - {issue}")

    if warnings:
        if results["overall_status"] == "PASS":
            results["overall_status"] = "WARN"
        if verbose:
            print("\n⚠️ WARNINGS (review):")
            for warning in warnings:
                print(f"   - {warning}")

    if not issues and not warnings:
        if verbose:
            print("\n✓ All time-series validations passed")

    return results


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    print("Time-Series Validation Module")
    print("=" * 60)
    print("\nUsage:")
    print("  from timeseries_validation import validate_timeseries_features")
    print("  results = validate_timeseries_features(df, features, target)")
    print("\nIndividual checks:")
    print("  - adf_test(series): Stationarity test")
    print("  - check_temporal_continuity(df): Gap detection")
    print("  - check_look_ahead_bias(features, target): Leakage detection")
    print("  - verify_rolling_window_integrity(df, features): Warmup check")
