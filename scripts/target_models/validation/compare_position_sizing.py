"""
Compare Position Sizing Strategies with Conformal Prediction
============================================================

Tests three conformal-aware position sizing approaches:
A) Set Size Scaling: Use prediction set size from direction targets
B) Interval Width Scaling: Use prediction interval width from volatility targets
C) Kelly + Uncertainty: Full Kelly formula adjusted by average uncertainty

Uses precomputed fast_backtest results to quickly iterate on position sizing.

Usage:
    python -m scripts.target_models.validation.compare_position_sizing
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd


@dataclass
class PositionSizingConfig:
    """Configuration for position sizing strategies."""

    # Gate threshold
    prob_threshold: float = 0.52

    # Max position size
    max_position: float = 2.0

    # Vol regime reduction
    high_vol_factor: float = 0.7

    # Strategy-specific params
    # Option A: Set size scaling
    set_size_uncertain_factor: float = 0.5  # Factor when set_size > 1

    # Option B: Interval width scaling
    max_interval_width: float = 0.10  # Normalize interval width

    # Option C: Kelly
    kelly_fraction: float = 0.25  # Fractional Kelly


@dataclass
class StrategyResult:
    """Results from a single strategy."""

    name: str
    n_trades: int
    n_long: int
    n_short: int
    n_flat: int

    # PnL metrics
    total_pnl: float
    mean_pnl: float
    sharpe: float
    max_drawdown: float

    # Position stats
    mean_position: float
    mean_position_when_trading: float

    # Conformal impact
    pct_reduced_by_conformal: float  # % of trades where conformal reduced position


class PositionSizingComparison:
    """Compare different position sizing strategies."""

    def __init__(
        self,
        predictions_dir: Path | str = "data/backtest_results",
        config: PositionSizingConfig | None = None,
    ):
        self.predictions_dir = Path(predictions_dir)
        self.config = config or PositionSizingConfig()

        # Loaded data
        self.merged: pd.DataFrame | None = None
        self.returns_actual: pd.Series | None = None

    def load_predictions(self) -> pd.DataFrame:
        """Load and merge predictions from all 20 configs."""

        configs = [
            f"{target}_{horizon}bar"
            for target in [
                "direction",
                "returns",
                "volatility",
                "vol_regime",
                "trend_regime",
            ]
            for horizon in [1, 3, 6, 12]
        ]

        frames = []
        for config_name in configs:
            pred_path = self.predictions_dir / f"{config_name}_predictions.parquet"
            if not pred_path.exists():
                print(f"  Warning: Missing {config_name}")
                continue

            df = pd.read_parquet(pred_path)

            # Standardize columns
            cols = {
                "aligned_pred_idx": "aligned_pred_idx",
                "y_pred": f"{config_name}__y_pred",
                "y_prob": f"{config_name}__y_prob",
                "y_true": f"{config_name}__y_true",
                "uncertainty": f"{config_name}__uncertainty",
                "set_size": f"{config_name}__set_size",
                "interval_width": f"{config_name}__interval_width",
                "covered": f"{config_name}__covered",
            }

            df_renamed = df[["aligned_pred_idx"]].copy()
            for old, new in cols.items():
                if old in df.columns:
                    df_renamed[new] = df[old].values

            df_renamed = df_renamed.set_index("aligned_pred_idx")
            frames.append(df_renamed)

        if not frames:
            raise ValueError("No predictions found!")

        # Merge all on aligned_pred_idx (inner join)
        merged = pd.concat(frames, axis=1, join="inner")
        merged = merged.sort_index()

        print(f"Loaded {len(frames)} configs, {len(merged)} aligned rows")
        self.merged = merged
        return merged

    def _get_direction_consensus(self, row: pd.Series) -> float:
        """Average P(up) across direction horizons."""
        probs = []
        for h in [1, 3, 6, 12]:
            col = f"direction_{h}bar__y_prob"
            if col in row.index and not pd.isna(row[col]):
                probs.append(row[col])
        return np.mean(probs) if probs else 0.5

    def _get_direction_set_sizes(self, row: pd.Series) -> list[float]:
        """Get set sizes from direction targets."""
        sizes = []
        for h in [1, 3, 6, 12]:
            col = f"direction_{h}bar__set_size"
            if col in row.index and not pd.isna(row[col]):
                sizes.append(row[col])
        return sizes

    def _get_volatility_intervals(self, row: pd.Series) -> list[float]:
        """Get interval widths from volatility targets."""
        widths = []
        for h in [1, 3, 6, 12]:
            col = f"volatility_{h}bar__interval_width"
            if col in row.index and not pd.isna(row[col]):
                widths.append(row[col])
        return widths

    def _get_returns_pred(self, row: pd.Series) -> float:
        """Average expected return across horizons."""
        preds = []
        for h in [1, 3, 6, 12]:
            col = f"returns_{h}bar__y_pred"
            if col in row.index and not pd.isna(row[col]):
                preds.append(row[col])
        return np.mean(preds) if preds else 0.0

    def _get_vol_regime_high(self, row: pd.Series) -> bool:
        """Check if majority vol_regime predictions are HIGH (2)."""
        regimes = []
        for h in [1, 3, 6, 12]:
            col = f"vol_regime_{h}bar__y_pred"
            if col in row.index and not pd.isna(row[col]):
                regimes.append(row[col])
        if not regimes:
            return False
        return np.mean([r == 2 for r in regimes]) > 0.5

    def _get_actual_return(self, row: pd.Series) -> float:
        """Get actual return (from direction_1bar y_true mapped to returns)."""
        # We use direction_1bar__y_true as proxy for realized direction
        # Actual PnL = position * direction * some base return
        # For now, use returns_1bar y_true if available
        col = "returns_1bar__y_true"
        if col in row.index and not pd.isna(row[col]):
            return row[col]
        return 0.0

    def strategy_baseline(self, row: pd.Series) -> tuple[float, str, dict]:
        """
        Baseline strategy (current V3 with placeholder ratio_factor).

        Returns: (position_size, direction, metadata)
        """
        cfg = self.config

        direction_prob = self._get_direction_consensus(row)
        is_high_vol = self._get_vol_regime_high(row)

        # Gate check
        if direction_prob < cfg.prob_threshold and direction_prob > (
            1 - cfg.prob_threshold
        ):
            return 0.0, "flat", {"gate": "failed"}

        direction = "long" if direction_prob > 0.5 else "short"

        # V3 factors (current placeholders)
        ratio_factor = 1.0  # Placeholder
        alignment_factor = 0.5 + 0.5 * abs(direction_prob - 0.5) / 0.5
        vol_factor = cfg.high_vol_factor if is_high_vol else 1.0

        raw = 1.0 * ratio_factor * alignment_factor * vol_factor
        final = min(raw, cfg.max_position)

        return (
            final,
            direction,
            {
                "ratio_factor": ratio_factor,
                "alignment_factor": alignment_factor,
                "vol_factor": vol_factor,
                "conformal_reduced": False,
            },
        )

    def strategy_a_set_size(self, row: pd.Series) -> tuple[float, str, dict]:
        """
        Option A: Replace ratio_factor with set size scaling.

        If ANY direction horizon has set_size > 1 (uncertain), reduce position.
        """
        cfg = self.config

        direction_prob = self._get_direction_consensus(row)
        is_high_vol = self._get_vol_regime_high(row)
        set_sizes = self._get_direction_set_sizes(row)

        # Gate check
        if direction_prob < cfg.prob_threshold and direction_prob > (
            1 - cfg.prob_threshold
        ):
            return 0.0, "flat", {"gate": "failed"}

        direction = "long" if direction_prob > 0.5 else "short"

        # Conformal factor from set sizes
        # avg_set_size: 1 = all confident, 2 = all uncertain
        avg_set_size = np.mean(set_sizes) if set_sizes else 1.0
        conformal_factor = 1.0 - (avg_set_size - 1) * (
            1 - cfg.set_size_uncertain_factor
        )
        # set_size=1 → factor=1.0
        # set_size=2 → factor=0.5 (with default set_size_uncertain_factor=0.5)

        # Replace ratio_factor with conformal_factor
        alignment_factor = 0.5 + 0.5 * abs(direction_prob - 0.5) / 0.5
        vol_factor = cfg.high_vol_factor if is_high_vol else 1.0

        raw = 1.0 * conformal_factor * alignment_factor * vol_factor
        final = min(raw, cfg.max_position)

        return (
            final,
            direction,
            {
                "conformal_factor": conformal_factor,
                "avg_set_size": avg_set_size,
                "alignment_factor": alignment_factor,
                "vol_factor": vol_factor,
                "conformal_reduced": conformal_factor < 1.0,
            },
        )

    def strategy_b_interval_width(self, row: pd.Series) -> tuple[float, str, dict]:
        """
        Option B: Use interval width from volatility targets.

        Wider intervals = more uncertainty = reduce position.
        """
        cfg = self.config

        direction_prob = self._get_direction_consensus(row)
        is_high_vol = self._get_vol_regime_high(row)
        interval_widths = self._get_volatility_intervals(row)

        # Gate check
        if direction_prob < cfg.prob_threshold and direction_prob > (
            1 - cfg.prob_threshold
        ):
            return 0.0, "flat", {"gate": "failed"}

        direction = "long" if direction_prob > 0.5 else "short"

        # Conformal factor from interval widths
        if interval_widths:
            avg_width = np.mean(interval_widths)
            # Normalize: wider → lower factor
            width_ratio = min(avg_width / cfg.max_interval_width, 1.0)
            conformal_factor = 1.0 - 0.5 * width_ratio  # At max width, factor = 0.5
        else:
            conformal_factor = 1.0
            avg_width = 0.0

        alignment_factor = 0.5 + 0.5 * abs(direction_prob - 0.5) / 0.5
        vol_factor = cfg.high_vol_factor if is_high_vol else 1.0

        raw = 1.0 * conformal_factor * alignment_factor * vol_factor
        final = min(raw, cfg.max_position)

        return (
            final,
            direction,
            {
                "conformal_factor": conformal_factor,
                "avg_interval_width": avg_width,
                "alignment_factor": alignment_factor,
                "vol_factor": vol_factor,
                "conformal_reduced": conformal_factor < 1.0,
            },
        )

    def strategy_c_kelly_uncertainty(self, row: pd.Series) -> tuple[float, str, dict]:
        """
        Option C: Kelly criterion with uncertainty adjustment.

        kelly_fraction * edge / variance * (1 - uncertainty)
        """
        cfg = self.config

        direction_prob = self._get_direction_consensus(row)
        is_high_vol = self._get_vol_regime_high(row)
        set_sizes = self._get_direction_set_sizes(row)
        interval_widths = self._get_volatility_intervals(row)

        # Gate check
        if direction_prob < cfg.prob_threshold and direction_prob > (
            1 - cfg.prob_threshold
        ):
            return 0.0, "flat", {"gate": "failed"}

        direction = "long" if direction_prob > 0.5 else "short"

        # Combine uncertainties
        avg_set_size = np.mean(set_sizes) if set_sizes else 1.0
        set_uncertainty = avg_set_size - 1  # 0 to 1

        if interval_widths:
            avg_width = np.mean(interval_widths)
            width_uncertainty = min(avg_width / cfg.max_interval_width, 1.0)
        else:
            width_uncertainty = 0.0
            avg_width = 0.0

        # Combined uncertainty (average of both)
        total_uncertainty = 0.5 * set_uncertainty + 0.5 * width_uncertainty

        # Kelly-style position
        # edge = |direction_prob - 0.5| * 2 (scaled to [0, 1])
        edge = abs(direction_prob - 0.5) * 2

        # Simple Kelly: f* = edge (assuming equal win/loss)
        kelly = cfg.kelly_fraction * edge * (1 - total_uncertainty)

        vol_factor = cfg.high_vol_factor if is_high_vol else 1.0
        raw = kelly * vol_factor * cfg.max_position
        final = min(max(raw, 0.0), cfg.max_position)

        return (
            final,
            direction,
            {
                "kelly": kelly,
                "edge": edge,
                "set_uncertainty": set_uncertainty,
                "width_uncertainty": width_uncertainty,
                "total_uncertainty": total_uncertainty,
                "vol_factor": vol_factor,
                "conformal_reduced": total_uncertainty > 0.0,
            },
        )

    def run_strategy(
        self,
        strategy_name: Literal["baseline", "A", "B", "C"],
    ) -> tuple[pd.DataFrame, StrategyResult]:
        """Run a single strategy on all rows."""

        if self.merged is None:
            raise ValueError("Call load_predictions() first")

        strategy_fn = {
            "baseline": self.strategy_baseline,
            "A": self.strategy_a_set_size,
            "B": self.strategy_b_interval_width,
            "C": self.strategy_c_kelly_uncertainty,
        }[strategy_name]

        results = []
        for idx, row in self.merged.iterrows():
            position, direction, meta = strategy_fn(row)
            actual_return = self._get_actual_return(row)

            # PnL calculation
            if direction == "flat":
                pnl = 0.0
            elif direction == "long":
                pnl = position * actual_return
            else:  # short
                pnl = -position * actual_return

            results.append(
                {
                    "aligned_pred_idx": idx,
                    "position": position,
                    "direction": direction,
                    "actual_return": actual_return,
                    "pnl": pnl,
                    **meta,
                }
            )

        df = pd.DataFrame(results).set_index("aligned_pred_idx")

        # Compute summary metrics
        n_trades = (df["direction"] != "flat").sum()
        n_long = (df["direction"] == "long").sum()
        n_short = (df["direction"] == "short").sum()
        n_flat = (df["direction"] == "flat").sum()

        pnl_series = df["pnl"]
        total_pnl = pnl_series.sum()
        mean_pnl = pnl_series.mean()

        # Sharpe (annualized, assuming 3 trades per day for 8h bars)
        if pnl_series.std() > 0:
            sharpe = (pnl_series.mean() / pnl_series.std()) * np.sqrt(3 * 252)
        else:
            sharpe = 0.0

        # Max drawdown
        cumulative = pnl_series.cumsum()
        running_max = cumulative.cummax()
        drawdown = cumulative - running_max
        max_drawdown = drawdown.min()

        # Position stats
        mean_position = df["position"].mean()
        trading_mask = df["direction"] != "flat"
        mean_position_when_trading = (
            df.loc[trading_mask, "position"].mean() if trading_mask.any() else 0.0
        )

        # Conformal impact
        if "conformal_reduced" in df.columns:
            pct_reduced = df["conformal_reduced"].mean() * 100
        else:
            pct_reduced = 0.0

        result = StrategyResult(
            name=strategy_name,
            n_trades=int(n_trades),
            n_long=int(n_long),
            n_short=int(n_short),
            n_flat=int(n_flat),
            total_pnl=total_pnl,
            mean_pnl=mean_pnl,
            sharpe=sharpe,
            max_drawdown=max_drawdown,
            mean_position=mean_position,
            mean_position_when_trading=mean_position_when_trading,
            pct_reduced_by_conformal=pct_reduced,
        )

        return df, result

    def compare_all(self) -> dict[str, StrategyResult]:
        """Run all strategies and compare."""

        if self.merged is None:
            self.load_predictions()

        results = {}
        for name in ["baseline", "A", "B", "C"]:
            print(f"\nRunning strategy {name}...")
            _, result = self.run_strategy(name)
            results[name] = result

            print(
                f"  Trades: {result.n_trades} (L:{result.n_long}, S:{result.n_short}, F:{result.n_flat})"
            )
            print(f"  Total PnL: {result.total_pnl:.4f}")
            print(f"  Sharpe: {result.sharpe:.3f}")
            print(f"  Max DD: {result.max_drawdown:.4f}")
            print(
                f"  Mean Position: {result.mean_position:.3f} (trading: {result.mean_position_when_trading:.3f})"
            )
            print(f"  % Reduced by Conformal: {result.pct_reduced_by_conformal:.1f}%")

        return results

    def summary_table(self, results: dict[str, StrategyResult]) -> pd.DataFrame:
        """Create comparison table."""

        rows = []
        for name, r in results.items():
            rows.append(
                {
                    "Strategy": name,
                    "Trades": r.n_trades,
                    "Long": r.n_long,
                    "Short": r.n_short,
                    "Total PnL": f"{r.total_pnl:.4f}",
                    "Sharpe": f"{r.sharpe:.3f}",
                    "Max DD": f"{r.max_drawdown:.4f}",
                    "Mean Pos": f"{r.mean_position:.3f}",
                    "% Conformal Reduced": f"{r.pct_reduced_by_conformal:.1f}%",
                }
            )

        return pd.DataFrame(rows)


def run_all_fast_backtests(output_dir: Path, verbose: bool = True) -> dict:
    """Run fast_backtest for all 20 configs and save predictions."""

    from scripts.target_models.validation.fast_backtest import (
        BacktestConfig,
        FastBacktester,
    )

    config = BacktestConfig(
        backtest_rows=300,
        output_dir=output_dir,
    )
    backtester = FastBacktester(config)

    # Run all 20 configs
    results = backtester.run_all(verbose=verbose)

    # Save predictions
    output_dir.mkdir(parents=True, exist_ok=True)
    for _config_name, result in results.items():
        if result is not None:
            backtester.save_results(result, output_dir)

    return results


if __name__ == "__main__":
    import argparse
    import warnings

    warnings.filterwarnings("ignore")

    parser = argparse.ArgumentParser(description="Compare position sizing strategies")
    parser.add_argument(
        "--run-backtests",
        action="store_true",
        help="Run fast_backtest for all 20 configs first",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="data/backtest_results",
        help="Directory for backtest results",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)

    if args.run_backtests:
        print("=" * 60)
        print("Running fast_backtest for all 20 configs...")
        print("=" * 60)
        run_all_fast_backtests(output_dir, verbose=True)

    # Compare strategies
    print("\n" + "=" * 60)
    print("Comparing Position Sizing Strategies")
    print("=" * 60)

    comparison = PositionSizingComparison(predictions_dir=output_dir)

    try:
        results = comparison.compare_all()

        print("\n" + "=" * 60)
        print("SUMMARY TABLE")
        print("=" * 60)
        summary = comparison.summary_table(results)
        print(summary.to_string(index=False))

        # Save summary
        summary.to_csv(output_dir / "position_sizing_comparison.csv", index=False)
        print(f"\nSaved to {output_dir / 'position_sizing_comparison.csv'}")

    except ValueError as e:
        print(f"\nError: {e}")
        print("\nRun with --run-backtests to generate predictions first:")
        print(
            "  python -m scripts.target_models.validation.compare_position_sizing --run-backtests"
        )
