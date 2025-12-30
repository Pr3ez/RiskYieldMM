"""
Walk-Forward Backtesting Module
===============================

Backtesting infrastructure:
- Position sizing (V3 pipeline)
- Walk-forward iteration
- Performance metrics
- Backtest execution
"""

import numpy as np
import pandas as pd

from . import config, data, models

# =============================================================================
# POSITION SIZING
# =============================================================================


def position_sizer_v3(
    direction_prob: float,
    volatility_pred: float,
    expected_return: float = 0.0,
    cfg: config.PositionConfig | None = None,
) -> tuple[float, int]:
    """
    Position Sizing V3 - simplified version.

    Args:
        direction_prob: P(up) from ensemble
        volatility_pred: Predicted volatility
        expected_return: Expected return (not used in simplified version)
        cfg: Position config

    Returns:
        (position_size, position_direction)
        - size: Float in [0, max_leverage]
        - direction: +1 (long), -1 (short), 0 (flat)
    """
    cfg = cfg or config.POSITION_CONFIG

    # Gate 1: Direction confidence
    confidence_distance = abs(direction_prob - 0.5)
    min_distance = cfg.confidence_threshold - 0.5

    if confidence_distance < min_distance:
        return 0.0, 0  # Flat - not confident enough

    direction = 1 if direction_prob > 0.5 else -1

    # Gate 2: High volatility reduction
    vol_multiplier = 1.0
    if volatility_pred > cfg.vol_threshold_high:
        vol_multiplier = cfg.vol_threshold_high / volatility_pred
        vol_multiplier = max(vol_multiplier, cfg.vol_reduction_floor)

    # Base size from confidence
    confidence = confidence_distance * 2  # Scale to [0, 1]
    base_size = confidence * cfg.max_leverage

    # Apply volatility adjustment
    final_size = base_size * vol_multiplier
    final_size = np.clip(final_size, 0, cfg.max_leverage)

    return final_size, direction


# =============================================================================
# BACKTEST METRICS
# =============================================================================


def compute_backtest_metrics(results_df: pd.DataFrame) -> dict:
    """
    Compute performance metrics from backtest results.

    Args:
        results_df: DataFrame with 'position_return', 'position_dir', etc.

    Returns:
        Dict of performance metrics
    """
    returns = results_df["position_return"]

    # Basic metrics
    total_return = returns.sum()
    avg_return = returns.mean()
    std_return = returns.std()

    # Sharpe (annualized, assuming 3 bars/day for 8h)
    sharpe = (avg_return / std_return) * np.sqrt(3 * 365) if std_return > 0 else 0

    # Win rate
    winning = (returns > 0).sum()
    losing = (returns < 0).sum()
    flat = (returns == 0).sum()
    win_rate = winning / (winning + losing) if (winning + losing) > 0 else 0

    # Max drawdown
    cum_returns = (1 + returns).cumprod()
    running_max = cum_returns.cummax()
    drawdown = (cum_returns - running_max) / running_max
    max_drawdown = drawdown.min()

    # Position metrics
    long_pct = (results_df["position_dir"] == 1).mean()
    short_pct = (results_df["position_dir"] == -1).mean()
    flat_pct = (results_df["position_dir"] == 0).mean()
    avg_size = results_df["position_size"].mean()

    return {
        "total_return": total_return,
        "avg_return": avg_return,
        "std_return": std_return,
        "sharpe": sharpe,
        "win_rate": win_rate,
        "winning_trades": winning,
        "losing_trades": losing,
        "flat_trades": flat,
        "max_drawdown": max_drawdown,
        "pct_long": long_pct,
        "pct_short": short_pct,
        "pct_flat": flat_pct,
        "avg_position_size": avg_size,
    }


# =============================================================================
# WALK-FORWARD BACKTEST
# =============================================================================


def run_walk_forward(
    df: pd.DataFrame,
    feature_cols: list[str] | None = None,
    max_iterations: int = 500,
    verbose: bool = True,
    wf_cfg: config.WalkForwardConfig | None = None,
) -> tuple[pd.DataFrame, dict]:
    """
    Run walk-forward backtest.

    Args:
        df: DataFrame with features, targets, metadata
        feature_cols: Feature column names (auto-detected if None)
        max_iterations: Maximum number of iterations
        verbose: Print progress
        wf_cfg: Walk-forward configuration

    Returns:
        (results_df, metrics_dict)
    """
    wf_cfg = wf_cfg or config.WF_CONFIG

    if feature_cols is None:
        feature_cols = data.get_feature_columns(df)

    # Prepare data
    mask = df["y_direction"].notna()
    X = df.loc[mask, feature_cols].copy()
    y = df.loc[mask, "y_direction"].copy()

    # Calculate starting point
    start_idx = wf_cfg.train_size + wf_cfg.cal_size + wf_cfg.val_size
    total_iterations = min(max_iterations, len(X) - start_idx)

    if verbose:
        print(f"Running {total_iterations} walk-forward iterations...")
        print(
            f"Train: {wf_cfg.train_size}, Cal: {wf_cfg.cal_size}, Val: {wf_cfg.val_size}"
        )

    results = []
    pnl_curve = [0.0]

    for i in range(total_iterations):
        current_idx = start_idx + i

        # Define windows
        train_end = current_idx - wf_cfg.cal_size - wf_cfg.val_size
        train_start = max(0, train_end - wf_cfg.train_size)

        pred_idx = current_idx

        if pred_idx >= len(X):
            break

        # Get training data
        X_train = X.iloc[train_start:train_end]
        y_train = y.iloc[train_start:train_end]
        X_pred = X.iloc[pred_idx : pred_idx + 1]

        if len(X_train) < wf_cfg.min_train_samples:
            continue

        # Train quick model for direction
        try:
            if models.HAS_LIGHTGBM:
                from lightgbm import LGBMClassifier

                quick_model = LGBMClassifier(n_estimators=100, max_depth=4, verbose=-1)
                quick_model.fit(X_train, y_train)
                dir_prob = quick_model.predict_proba(X_pred)[0, 1]
            else:
                dir_prob = 0.5
        except Exception:
            dir_prob = 0.5

        # Get actual return and volatility
        actual_return = df["y_forward_return_1"].iloc[pred_idx]
        if pd.isna(actual_return):
            continue

        # Get volatility estimate
        vol_pred = df["rolling_vol_21"].iloc[pred_idx]
        if pd.isna(vol_pred):
            vol_pred = 0.015

        # Position sizing
        position_size, position_dir = position_sizer_v3(
            direction_prob=dir_prob,
            volatility_pred=vol_pred,
        )

        # Calculate PnL
        position_return = position_dir * position_size * actual_return
        cumulative_pnl = pnl_curve[-1] + position_return
        pnl_curve.append(cumulative_pnl)

        results.append(
            {
                "idx": pred_idx,
                "timestamp": df.index[pred_idx]
                if isinstance(df.index, pd.DatetimeIndex)
                else pred_idx,
                "dir_prob": dir_prob,
                "position_dir": position_dir,
                "position_size": position_size,
                "actual_return": actual_return,
                "position_return": position_return,
                "cumulative_pnl": cumulative_pnl,
            }
        )

        if verbose and (i + 1) % 100 == 0:
            print(f"  Iteration {i + 1}/{total_iterations}, PnL: {cumulative_pnl:.2%}")

    results_df = pd.DataFrame(results)
    metrics = compute_backtest_metrics(results_df) if len(results_df) > 0 else {}

    if verbose and len(results_df) > 0:
        print("\n--- Backtest Summary ---")
        print(f"Final PnL: {metrics['total_return']:.2%}")
        print(f"Sharpe: {metrics['sharpe']:.2f}")
        print(f"Win rate: {metrics['win_rate']:.1%}")

    return results_df, metrics
