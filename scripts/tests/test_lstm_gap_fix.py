#!/usr/bin/env python3
"""
LSTM Gap Fix Comparison Test

Tests two approaches for LSTM sequence continuity:
1. CURRENT: lstm_X_full = train + val (93-bar gap to X_pred)
2. FIX: lstm_X_full_for_seq = train + val + cal (3-bar gap to X_pred)

Runs on all 1bar targets with LSTM-only weights to isolate model performance.
Uses temporal cross-validation to avoid overfit.

Author: Astra
Date: 2026-01-19
"""

import sys
import time
import warnings
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import torch

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


from scripts.target_models.validation.l2_backtest_sync import (
    SyncBacktestConfig,
    _load_config_data,
    _train_lstm_classifier,
    _train_lstm_regressor,
    compute_common_pred_idx_range,
)

# =============================================================================
# CONFIG
# =============================================================================

# All 1bar targets (available in system)
TARGETS_1BAR = [
    "direction_1bar",
    "volatility_1bar",
    "vol_regime_1bar",
]

# Test parameters
N_STEPS = 50  # Number of walk-forward steps (fast test)
TRAIN_WINDOW = 600  # LSTM-optimized window
STEP_SIZE = 5  # Skip steps for speed (every 5th)


@dataclass
class LSTMTestConfig:
    """Minimal config for LSTM testing."""

    train_window: int = 600
    train_ratio: float = 0.70
    val_ratio: float = 0.15
    cal_ratio: float = 0.15
    embargo_bars: int = 3  # 1bar target → 3 bars
    lstm_hidden_size: int = 64
    lstm_num_layers: int = 2
    lstm_lr: float = 0.001
    lstm_epochs: int = 50  # Reduced for speed
    lstm_batch_size: int = 32
    lstm_seq_len: int = 20
    random_state: int = 42


def extract_splits(X: np.ndarray, y: np.ndarray, config: LSTMTestConfig) -> dict:
    """Extract train/val/cal splits with embargo."""
    n = len(X)
    embargo = config.embargo_bars

    # Calculate split points (accounting for embargos)
    available = n - 2 * embargo  # Two embargo gaps
    train_size = int(available * config.train_ratio)
    val_size = int(available * config.val_ratio)
    cal_size = available - train_size - val_size

    # Split boundaries
    train_end = train_size
    val_start = train_end + embargo
    val_end = val_start + val_size
    cal_start = val_end + embargo

    return {
        "X_train": X[:train_end],
        "y_train": y[:train_end],
        "X_val": X[val_start:val_end],
        "y_val": y[val_start:val_end],
        "X_cal": X[cal_start:],
        "y_cal": y[cal_start:],
        "splits_info": {
            "train": (0, train_end),
            "val": (val_start, val_end),
            "cal": (cal_start, n),
            "embargo": embargo,
        },
    }


def test_lstm_classification_current(
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_val: np.ndarray,
    y_val: np.ndarray,
    X_cal: np.ndarray,
    X_pred: np.ndarray,
    config: LSTMTestConfig,
    device: str = "cuda",
) -> tuple[np.ndarray, dict]:
    """
    CURRENT approach: lstm_X_full = train + val (93-bar gap).
    """
    seq_len = config.lstm_seq_len
    n_classes = 3  # down/neutral/up

    # Train LSTM on train+val
    lstm_X_full = np.concatenate([X_train, X_val], axis=0)
    lstm_y_full = np.concatenate([y_train, y_val], axis=0)

    model, scaler, actual_seq_len = _train_lstm_classifier(
        lstm_X_full,
        lstm_y_full,
        n_classes,
        seq_len=seq_len,
        hidden_size=config.lstm_hidden_size,
        num_layers=config.lstm_num_layers,
        lr=config.lstm_lr,
        epochs=config.lstm_epochs,
        batch_size=config.lstm_batch_size,
        device=device,
    )

    # Build prediction sequence (CURRENT: gap exists)
    # lstm_X_full ends at val, X_pred is after cal → gap = cal_size + embargo
    X_pred_scaled = scaler.transform(X_pred.reshape(1, -1))
    lstm_X_full_scaled = scaler.transform(lstm_X_full)

    # Take last (seq_len-1) from lstm_X_full, append X_pred
    if len(lstm_X_full_scaled) >= seq_len - 1:
        X_pred_seq = np.concatenate(
            [lstm_X_full_scaled[-(seq_len - 1) :], X_pred_scaled], axis=0
        )
    else:
        X_pred_seq = np.concatenate([lstm_X_full_scaled, X_pred_scaled], axis=0)
        X_pred_seq = np.pad(X_pred_seq, ((seq_len - len(X_pred_seq), 0), (0, 0)))

    X_pred_seq = X_pred_seq.reshape(1, seq_len, -1)

    # Predict
    model.eval()
    with torch.no_grad():
        pred_tensor = torch.tensor(X_pred_seq, dtype=torch.float32, device=device)
        logits = model(pred_tensor)
        probs = torch.softmax(logits, dim=-1).cpu().numpy()[0]

    gap_size = len(X_cal) + config.embargo_bars
    return probs, {"gap_bars": gap_size, "approach": "current"}


def test_lstm_classification_fixed(
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_val: np.ndarray,
    y_val: np.ndarray,
    X_cal: np.ndarray,
    X_pred: np.ndarray,
    config: LSTMTestConfig,
    device: str = "cuda",
) -> tuple[np.ndarray, dict]:
    """
    FIXED approach: Include X_cal features for prediction sequence only.
    Training still uses train+val (no change to training).
    """
    seq_len = config.lstm_seq_len
    n_classes = 3

    # Train LSTM on train+val (SAME AS CURRENT)
    lstm_X_full = np.concatenate([X_train, X_val], axis=0)
    lstm_y_full = np.concatenate([y_train, y_val], axis=0)

    model, scaler, actual_seq_len = _train_lstm_classifier(
        lstm_X_full,
        lstm_y_full,
        n_classes,
        seq_len=seq_len,
        hidden_size=config.lstm_hidden_size,
        num_layers=config.lstm_num_layers,
        lr=config.lstm_lr,
        epochs=config.lstm_epochs,
        batch_size=config.lstm_batch_size,
        device=device,
    )

    # Build prediction sequence (FIXED: include X_cal features)
    lstm_X_full_for_seq = np.concatenate([X_train, X_val, X_cal], axis=0)
    X_pred_scaled = scaler.transform(X_pred.reshape(1, -1))
    lstm_X_full_seq_scaled = scaler.transform(lstm_X_full_for_seq)

    # Take last (seq_len-1) from extended sequence
    if len(lstm_X_full_seq_scaled) >= seq_len - 1:
        X_pred_seq = np.concatenate(
            [lstm_X_full_seq_scaled[-(seq_len - 1) :], X_pred_scaled], axis=0
        )
    else:
        X_pred_seq = np.concatenate([lstm_X_full_seq_scaled, X_pred_scaled], axis=0)
        X_pred_seq = np.pad(X_pred_seq, ((seq_len - len(X_pred_seq), 0), (0, 0)))

    X_pred_seq = X_pred_seq.reshape(1, seq_len, -1)

    # Predict
    model.eval()
    with torch.no_grad():
        pred_tensor = torch.tensor(X_pred_seq, dtype=torch.float32, device=device)
        logits = model(pred_tensor)
        probs = torch.softmax(logits, dim=-1).cpu().numpy()[0]

    gap_size = config.embargo_bars  # Only embargo gap now
    return probs, {"gap_bars": gap_size, "approach": "fixed"}


def test_lstm_regression_current(
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_val: np.ndarray,
    y_val: np.ndarray,
    X_cal: np.ndarray,
    X_pred: np.ndarray,
    config: LSTMTestConfig,
    device: str = "cuda",
) -> tuple[float, dict]:
    """CURRENT approach for regression."""
    seq_len = config.lstm_seq_len

    lstm_X_full = np.concatenate([X_train, X_val], axis=0)
    lstm_y_full = np.concatenate([y_train, y_val], axis=0)

    model, scaler, actual_seq_len = _train_lstm_regressor(
        lstm_X_full,
        lstm_y_full,
        seq_len=seq_len,
        hidden_size=config.lstm_hidden_size,
        num_layers=config.lstm_num_layers,
        lr=config.lstm_lr,
        epochs=config.lstm_epochs,
        batch_size=config.lstm_batch_size,
        device=device,
    )

    X_pred_scaled = scaler.transform(X_pred.reshape(1, -1))
    lstm_X_full_scaled = scaler.transform(lstm_X_full)

    if len(lstm_X_full_scaled) >= seq_len - 1:
        X_pred_seq = np.concatenate(
            [lstm_X_full_scaled[-(seq_len - 1) :], X_pred_scaled], axis=0
        )
    else:
        X_pred_seq = np.concatenate([lstm_X_full_scaled, X_pred_scaled], axis=0)
        X_pred_seq = np.pad(X_pred_seq, ((seq_len - len(X_pred_seq), 0), (0, 0)))

    X_pred_seq = X_pred_seq.reshape(1, seq_len, -1)

    model.eval()
    with torch.no_grad():
        pred_tensor = torch.tensor(X_pred_seq, dtype=torch.float32, device=device)
        pred = model(pred_tensor).cpu().numpy()[0]

    return pred, {"gap_bars": len(X_cal) + config.embargo_bars, "approach": "current"}


def test_lstm_regression_fixed(
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_val: np.ndarray,
    y_val: np.ndarray,
    X_cal: np.ndarray,
    X_pred: np.ndarray,
    config: LSTMTestConfig,
    device: str = "cuda",
) -> tuple[float, dict]:
    """FIXED approach for regression."""
    seq_len = config.lstm_seq_len

    lstm_X_full = np.concatenate([X_train, X_val], axis=0)
    lstm_y_full = np.concatenate([y_train, y_val], axis=0)

    model, scaler, actual_seq_len = _train_lstm_regressor(
        lstm_X_full,
        lstm_y_full,
        seq_len=seq_len,
        hidden_size=config.lstm_hidden_size,
        num_layers=config.lstm_num_layers,
        lr=config.lstm_lr,
        epochs=config.lstm_epochs,
        batch_size=config.lstm_batch_size,
        device=device,
    )

    # Extended sequence for prediction
    lstm_X_full_for_seq = np.concatenate([X_train, X_val, X_cal], axis=0)
    X_pred_scaled = scaler.transform(X_pred.reshape(1, -1))
    lstm_X_full_seq_scaled = scaler.transform(lstm_X_full_for_seq)

    if len(lstm_X_full_seq_scaled) >= seq_len - 1:
        X_pred_seq = np.concatenate(
            [lstm_X_full_seq_scaled[-(seq_len - 1) :], X_pred_scaled], axis=0
        )
    else:
        X_pred_seq = np.concatenate([lstm_X_full_seq_scaled, X_pred_scaled], axis=0)
        X_pred_seq = np.pad(X_pred_seq, ((seq_len - len(X_pred_seq), 0), (0, 0)))

    X_pred_seq = X_pred_seq.reshape(1, seq_len, -1)

    model.eval()
    with torch.no_grad():
        pred_tensor = torch.tensor(X_pred_seq, dtype=torch.float32, device=device)
        pred = model(pred_tensor).cpu().numpy()[0]

    return pred, {"gap_bars": config.embargo_bars, "approach": "fixed"}


def run_lstm_comparison_test(
    target: str,
    n_steps: int = N_STEPS,
    step_size: int = STEP_SIZE,
    verbose: bool = True,
) -> pd.DataFrame:
    """
    Run LSTM comparison test for a single target.

    Uses temporal cross-validation: walk forward through time,
    no shuffling, no look-ahead.
    """
    warnings.filterwarnings("ignore")

    config = LSTMTestConfig()
    device = "cuda" if torch.cuda.is_available() else "cpu"

    is_classification = target.startswith("direction")

    if verbose:
        print(f"\n{'=' * 60}")
        print(f"LSTM Gap Test: {target}")
        print(f"{'=' * 60}")
        print(f"Device: {device}")
        print(f"Steps: {n_steps}, Step size: {step_size}")
        print(f"Window: {config.train_window}, Seq len: {config.lstm_seq_len}")

    # Load data using existing infrastructure
    sync_cfg = SyncBacktestConfig(
        train_window=config.train_window,
        step_size=step_size,
    )

    common_range = compute_common_pred_idx_range(configs=[target])
    data = _load_config_data(target, sync_cfg, common_range=common_range)

    # Convert to numpy arrays for consistent indexing
    X = data.X_features.values.astype(np.float32)
    y = data.y_target.values
    n_samples = len(X)

    if verbose:
        print(f"Total samples: {n_samples}")
        print(f"Features: {X.shape[1]}")

    # Walk-forward test
    results = []
    effective_window = config.train_window
    max_iterations = min(n_steps, (n_samples - effective_window) // step_size)

    if verbose:
        print(f"\nRunning {max_iterations} walk-forward steps...")
        print("-" * 60)

    for step in range(max_iterations):
        step_start = time.time()

        # Window boundaries
        pred_idx = effective_window + step * step_size
        if pred_idx >= n_samples:
            break

        start_idx = pred_idx - effective_window

        # Extract window data
        X_window = X[start_idx:pred_idx]
        y_window = y[start_idx:pred_idx]
        X_pred = X[pred_idx]
        y_true = y[pred_idx]

        # Split into train/val/cal
        splits = extract_splits(X_window, y_window, config)

        try:
            if is_classification:
                # Test CURRENT approach
                probs_current, info_current = test_lstm_classification_current(
                    splits["X_train"],
                    splits["y_train"],
                    splits["X_val"],
                    splits["y_val"],
                    splits["X_cal"],
                    X_pred,
                    config,
                    device,
                )
                pred_current = np.argmax(probs_current)

                # Test FIXED approach
                probs_fixed, info_fixed = test_lstm_classification_fixed(
                    splits["X_train"],
                    splits["y_train"],
                    splits["X_val"],
                    splits["y_val"],
                    splits["X_cal"],
                    X_pred,
                    config,
                    device,
                )
                pred_fixed = np.argmax(probs_fixed)

                # Record
                results.append(
                    {
                        "step": step,
                        "pred_idx": pred_idx,
                        "y_true": int(y_true),
                        # Current
                        "pred_current": pred_current,
                        "correct_current": int(pred_current == int(y_true)),
                        "confidence_current": float(np.max(probs_current)),
                        "gap_current": info_current["gap_bars"],
                        # Fixed
                        "pred_fixed": pred_fixed,
                        "correct_fixed": int(pred_fixed == int(y_true)),
                        "confidence_fixed": float(np.max(probs_fixed)),
                        "gap_fixed": info_fixed["gap_bars"],
                        # Diff
                        "pred_changed": int(pred_current != pred_fixed),
                        "step_time": time.time() - step_start,
                    }
                )

            else:
                # Regression
                pred_current, info_current = test_lstm_regression_current(
                    splits["X_train"],
                    splits["y_train"],
                    splits["X_val"],
                    splits["y_val"],
                    splits["X_cal"],
                    X_pred,
                    config,
                    device,
                )

                pred_fixed, info_fixed = test_lstm_regression_fixed(
                    splits["X_train"],
                    splits["y_train"],
                    splits["X_val"],
                    splits["y_val"],
                    splits["X_cal"],
                    X_pred,
                    config,
                    device,
                )

                results.append(
                    {
                        "step": step,
                        "pred_idx": pred_idx,
                        "y_true": float(y_true),
                        "pred_current": float(pred_current),
                        "error_current": float(abs(pred_current - y_true)),
                        "gap_current": info_current["gap_bars"],
                        "pred_fixed": float(pred_fixed),
                        "error_fixed": float(abs(pred_fixed - y_true)),
                        "gap_fixed": info_fixed["gap_bars"],
                        "pred_diff": float(abs(pred_current - pred_fixed)),
                        "step_time": time.time() - step_start,
                    }
                )

            if verbose and (step + 1) % 10 == 0:
                print(
                    f"  Step {step + 1}/{max_iterations} completed ({time.time() - step_start:.2f}s)"
                )

        except Exception as e:
            print(f"  Step {step}: ERROR - {e}")
            continue

    df = pd.DataFrame(results)

    # Summary
    if verbose and len(df) > 0:
        print("\n" + "=" * 60)
        print("RESULTS SUMMARY")
        print("=" * 60)

        if is_classification:
            acc_current = df["correct_current"].mean()
            acc_fixed = df["correct_fixed"].mean()
            diff_pct = (df["pred_changed"].sum() / len(df)) * 100

            print("\nClassification Accuracy:")
            print(
                f"  CURRENT (gap={df['gap_current'].iloc[0]} bars): {acc_current:.4f} ({acc_current * 100:.2f}%)"
            )
            print(
                f"  FIXED   (gap={df['gap_fixed'].iloc[0]} bars): {acc_fixed:.4f} ({acc_fixed * 100:.2f}%)"
            )
            print(f"\nImprovement: {(acc_fixed - acc_current) * 100:+.2f}%")
            print(f"Predictions changed: {diff_pct:.1f}%")
            print("\nConfidence (mean):")
            print(f"  CURRENT: {df['confidence_current'].mean():.4f}")
            print(f"  FIXED:   {df['confidence_fixed'].mean():.4f}")
        else:
            mse_current = (df["error_current"] ** 2).mean()
            mse_fixed = (df["error_fixed"] ** 2).mean()
            rmse_current = np.sqrt(mse_current)
            rmse_fixed = np.sqrt(mse_fixed)

            print("\nRegression RMSE:")
            print(
                f"  CURRENT (gap={df['gap_current'].iloc[0]} bars): {rmse_current:.6f}"
            )
            print(f"  FIXED   (gap={df['gap_fixed'].iloc[0]} bars): {rmse_fixed:.6f}")
            print(
                f"\nImprovement: {((rmse_current - rmse_fixed) / rmse_current * 100):+.2f}%"
            )
            print(f"Mean prediction diff: {df['pred_diff'].mean():.6f}")

        print(f"\nTotal time: {df['step_time'].sum():.1f}s")
        print(f"Avg step time: {df['step_time'].mean():.2f}s")

    return df


def main():
    """Run full comparison on all 1bar targets."""
    print("\n" + "=" * 70)
    print("LSTM GAP FIX COMPARISON TEST")
    print("Testing: CURRENT (93-bar gap) vs FIXED (3-bar gap)")
    print("=" * 70)

    all_results = {}
    summary = []

    for target in TARGETS_1BAR:
        df = run_lstm_comparison_test(target, n_steps=N_STEPS, step_size=STEP_SIZE)
        all_results[target] = df

        is_cls = target.startswith("direction")

        if is_cls and len(df) > 0:
            summary.append(
                {
                    "target": target,
                    "type": "classification",
                    "metric_current": df["correct_current"].mean(),
                    "metric_fixed": df["correct_fixed"].mean(),
                    "improvement": (
                        df["correct_fixed"].mean() - df["correct_current"].mean()
                    )
                    * 100,
                    "predictions_changed_pct": df["pred_changed"].mean() * 100,
                }
            )
        elif len(df) > 0:
            rmse_cur = np.sqrt((df["error_current"] ** 2).mean())
            rmse_fix = np.sqrt((df["error_fixed"] ** 2).mean())
            summary.append(
                {
                    "target": target,
                    "type": "regression",
                    "metric_current": rmse_cur,
                    "metric_fixed": rmse_fix,
                    "improvement": (rmse_cur - rmse_fix) / rmse_cur * 100,
                    "predictions_changed_pct": (df["pred_diff"] > 1e-6).mean() * 100,
                }
            )

    # Final summary
    print("\n" + "=" * 70)
    print("FINAL SUMMARY")
    print("=" * 70)

    summary_df = pd.DataFrame(summary)
    print(summary_df.to_string(index=False))

    # Save results
    output_dir = Path("data/lstm_gap_test")
    output_dir.mkdir(parents=True, exist_ok=True)

    for target, df in all_results.items():
        df.to_parquet(output_dir / f"{target}_results.parquet")

    summary_df.to_csv(output_dir / "summary.csv", index=False)
    print(f"\nResults saved to: {output_dir}")

    return all_results, summary_df


if __name__ == "__main__":
    main()
