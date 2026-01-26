"""
L1 precomputation helper functions for the RiskYieldMM ML pipeline.

These functions support Step 8: L1 Precomputation.
"""

import json

import pandas as pd

from scripts.target_models.core.aligned_dual_window import (
    ExpandingL1Config,
    SlidingL2Config,
    get_l2_config_for_target,
)
from scripts.target_models.validation.l1_precompute import L1PrecomputeConfig


def compute_feasible_iters(
    config_name: str,
    cfg: L1PrecomputeConfig,
    backtest_rows: int | None,
    max_timestamp: pd.Timestamp | None = None,
) -> int:
    """
    Compute the maximum walk-forward iterations possible for a config
    given the data (after dropna) and current window settings.

    If backtest_rows is None, uses the maximum possible.
    Mirrors DualLayerEngine geometry: min warmup + L2 window + horizon.

    Args:
        config_name: Name of the config (e.g., "direction_1bar")
        cfg: L1PrecomputeConfig with paths
        backtest_rows: Requested number of iterations (None = max)
        max_timestamp: Optional max timestamp to truncate data

    Returns:
        Number of feasible iterations
    """
    data_path = cfg.data_dir / f"{config_name}.parquet"
    df = pd.read_parquet(data_path)

    feature_cols = [
        c for c in df.columns if not c.startswith("y_") and c != "timestamp"
    ]
    y_cols = [c for c in df.columns if c.startswith("y_")]
    target = config_name.rsplit("_", 1)[0]
    y_col = f"y_{target}"
    if y_col not in df.columns:
        y_col = y_cols[0] if y_cols else None
    if y_col is None:
        raise ValueError(f"No target column found for {config_name}")

    df = df.dropna(subset=feature_cols + [y_col])
    if max_timestamp is not None:
        df = df[df["timestamp"] <= max_timestamp]

    total_rows = len(df)
    if total_rows == 0:
        return 0

    horizon_part = config_name.rsplit("_", 1)[1]
    horizon = (
        int(horizon_part.replace("bar", ""))
        if "bar" in horizon_part
        else int(horizon_part)
    )

    base_l2 = get_l2_config_for_target(target)
    l2_cfg = SlidingL2Config()
    l2_cfg.window_size = base_l2.window_size
    l2_cfg.train_ratio = base_l2.train_ratio
    l2_cfg.cal_ratio = base_l2.cal_ratio
    l2_cfg.val_ratio = base_l2.val_ratio
    l2_cfg.purge_gap = base_l2.purge_gap
    l2_cfg.pred_size = horizon
    l1_warmup = ExpandingL1Config().min_warmup

    min_required_rows = l1_warmup + l2_cfg.total_size
    min_start = min_required_rows - 1
    last_pred_idx = total_rows - l2_cfg.pred_size
    if last_pred_idx < min_start:
        return 0

    if backtest_rows is None:
        first_pred_idx = min_start
    else:
        desired_start = last_pred_idx - backtest_rows + 1
        first_pred_idx = max(min_start, desired_start)
    return last_pred_idx - first_pred_idx + 1


def check_config_status(
    config_name: str,
    cfg: L1PrecomputeConfig,
    expected_iters: int,
    expected_features: int,
) -> dict:
    """
    Check if config is done with correct settings.

    Args:
        config_name: Name of the config
        cfg: L1PrecomputeConfig with paths
        expected_iters: Expected number of iterations
        expected_features: Expected number of features

    Returns:
        Dict with:
            - status: 'done', 'wrong_iters', 'wrong_features', 'missing'
            - current_iters: int or None
            - current_features: int or None
            - needs_recompute: bool
    """
    metadata_file = cfg.metadata_path(config_name)

    if not metadata_file.exists():
        return {
            "status": "missing",
            "current_iters": None,
            "current_features": None,
            "needs_recompute": True,
        }

    with open(metadata_file) as f:
        meta = json.load(f)

    current_iters = meta.get("total_iterations", 0)
    current_features = meta.get("feature_count", 0)

    # Check iteration count (allow extra iterations; require at least expected)
    if current_iters < expected_iters:
        return {
            "status": "wrong_iters",
            "current_iters": current_iters,
            "current_features": current_features,
            "needs_recompute": True,
        }

    # Check feature count (important for enable_boosting changes)
    if current_features != expected_features:
        return {
            "status": "wrong_features",
            "current_iters": current_iters,
            "current_features": current_features,
            "needs_recompute": True,
        }

    # Both match - config is done
    return {
        "status": "done",
        "current_iters": current_iters,
        "current_features": current_features,
        "needs_recompute": False,
    }


def print_rust_status() -> dict[str, bool]:
    """
    Print Rust backend status for L1 helpers.

    Returns:
        Dict mapping helper name to whether Rust is available
    """
    from scripts.target_models.helpers.bocpd import HAS_RUST as BOCPD_RUST
    from scripts.target_models.helpers.cusum import HAS_RUST as CUSUM_RUST
    from scripts.target_models.helpers.egarch import HAS_RUST as EGARCH_RUST
    from scripts.target_models.helpers.evt_pot import HAS_RUST as EVT_RUST
    from scripts.target_models.helpers.garch import HAS_RUST as GARCH_RUST
    from scripts.target_models.helpers.kalman import HAS_RUST as KALMAN_RUST
    from scripts.target_models.helpers.ou import HAS_RUST as OU_RUST

    print("=" * 60)
    print("RUST BACKEND STATUS")
    print("=" * 60)

    rust_status = {
        "CUSUM": CUSUM_RUST,
        "Kalman": KALMAN_RUST,
        "GARCH": GARCH_RUST,
        "EVT": EVT_RUST,
        "OU": OU_RUST,
        "BOCPD": BOCPD_RUST,
        "EGARCH": EGARCH_RUST,
    }

    speedups = {
        "CUSUM": "156x",
        "Kalman": "487x",
        "GARCH": "224x",
        "EVT": "25x",
        "OU": "30x",
        "BOCPD": "20x",
        "EGARCH": "22x",
    }

    for name, has_rust in rust_status.items():
        status = "✓ Rust" if has_rust else "○ Python"
        if has_rust:
            print(f"  {name:8s}: {status} ({speedups.get(name, '')} speedup)")
        else:
            print(f"  {name:8s}: {status}")

    rust_count = sum(rust_status.values())
    print(f"\n  {rust_count}/7 helpers using Rust backends")
    print("  HMM4, HMM5, IsolationForest use optimized Python (hmmlearn/sklearn)")

    return rust_status


def scan_config_status(
    configs: list[str],
    cfg: L1PrecomputeConfig,
    l1_rows: int | None,
    expected_features: int,
    global_end: pd.Timestamp | None = None,
    verbose: bool = True,
) -> tuple[list[str], list[str]]:
    """
    Pre-scan all configs and report their status.

    Args:
        configs: List of config names
        cfg: L1PrecomputeConfig with paths
        l1_rows: Requested iterations (None = auto)
        expected_features: Expected feature count
        global_end: Optional max timestamp
        verbose: Whether to print status

    Returns:
        Tuple of (to_compute, to_skip) config lists
    """
    if verbose:
        print("\n" + "=" * 60)
        print("PRE-SCAN: CONFIG STATUS")
        print("=" * 60)
        cap_str = "auto" if l1_rows is None else str(l1_rows)
        print(
            f"Target cap: {cap_str} iterations (per-config feasible computed), "
            f"{expected_features} features"
        )
        print()

    to_compute = []
    to_skip = []

    for config_name in configs:
        expected_iters = compute_feasible_iters(config_name, cfg, l1_rows, global_end)
        status = check_config_status(
            config_name, cfg, expected_iters, expected_features
        )

        if status["needs_recompute"]:
            to_compute.append(config_name)
            if verbose:
                if status["status"] == "missing":
                    print(f"  ⚪ {config_name}: MISSING")
                elif status["status"] == "wrong_iters":
                    print(
                        f"  🔄 {config_name}: {status['current_iters']} iters "
                        f"(need {expected_iters})"
                    )
                elif status["status"] == "wrong_features":
                    print(
                        f"  🔧 {config_name}: {status['current_features']} features "
                        f"(need {expected_features})"
                    )
        else:
            to_skip.append(config_name)
            if verbose:
                print(
                    f"  ✅ {config_name}: DONE ({status['current_iters']} iters, "
                    f"{status['current_features']} features)"
                )

    if verbose:
        print()
        print(f"Summary: {len(to_skip)} done, {len(to_compute)} need computation")
        print("=" * 60)

    return to_compute, to_skip
