"""
Phase 2: Parameter Research for Strategy Components
====================================================

Systematically tests different parameter combinations to find optimal:
1. Kelly fraction (position sizing aggressiveness)
2. ATR multiplier for TP/SL (exit distances)
3. Max holding bars (time exits)
4. Regime multipliers (leverage adjustment by volatility)

Uses historical backtest predictions + actual returns to simulate strategy.

Usage:
    python -m scripts.strategy.research.parameter_optimizer --experiment kelly
    python -m scripts.strategy.research.parameter_optimizer --experiment atr
    python -m scripts.strategy.research.parameter_optimizer --experiment all
"""

from __future__ import annotations

import argparse
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd

from scripts.strategy.exit_manager import ExitConfig, ExitManager, ExitReason
from scripts.strategy.leverage import LeverageCalculator, LeverageConfig
from scripts.strategy.position_sizing import (
    PositionSizer,
    PositionSizingConfig,
    TradeStats,
)
from scripts.strategy.risk_manager import RiskConfig, RiskManager, RiskState

logger = logging.getLogger(__name__)


@dataclass
class SimulationConfig:
    """Configuration for strategy simulation."""

    # Initial capital
    initial_capital: float = 10000.0

    # Transaction costs
    transaction_cost_bps: float = 10.0  # 10 bps round-trip

    # Slippage model (fraction of ATR)
    slippage_atr_fraction: float = 0.05  # 5% of ATR as slippage

    # Data columns
    return_col: str = "M_P_logReturn_pct_N"
    atr_col: str = "V_atrPct_6_pct_N"
    target_col: str = "y_direction"


@dataclass
class Trade:
    """Record of a completed trade."""

    entry_bar: int
    exit_bar: int
    direction: Literal["LONG", "SHORT"]
    entry_price: float
    exit_price: float
    position_size: float
    pnl: float
    pnl_pct: float
    exit_reason: ExitReason
    bars_held: int
    leverage: float


@dataclass
class SimulationResult:
    """Result from strategy simulation."""

    # Parameters used
    params: dict

    # Performance metrics
    total_return: float
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float
    profit_factor: float
    avg_trade_pnl: float
    n_trades: int
    n_liquidations: int

    # Exit analysis
    exit_distribution: dict[str, int]

    # Trade list
    trades: list[Trade] = field(default_factory=list)

    # Equity curve
    equity_curve: np.ndarray = field(default_factory=lambda: np.array([]))


class StrategySimulator:
    """
    Simulates trading strategy on historical data.

    Uses backtest predictions (direction model output) combined with
    actual returns to simulate PnL with different parameter settings.
    """

    def __init__(
        self,
        predictions_path: Path,
        dataset_path: Path,
        sim_config: SimulationConfig | None = None,
    ):
        self.sim_config = sim_config or SimulationConfig()

        # Load predictions from backtest
        self.predictions = pd.read_parquet(predictions_path)
        logger.info(f"Loaded {len(self.predictions)} predictions")

        # Load full dataset for returns and ATR
        self.dataset = pd.read_parquet(dataset_path)
        logger.info(f"Loaded dataset with {len(self.dataset)} rows")

        # Align predictions with dataset
        self._align_data()

    def _align_data(self) -> None:
        """Align predictions with dataset to get returns and ATR for each bar."""
        # predictions have pred_idx which is the index into the dataset
        pred_indices = self.predictions["pred_idx"].values

        # Get returns, ATR, and true direction for each prediction
        self.returns = self.dataset.iloc[pred_indices][
            self.sim_config.return_col
        ].values
        self.atr = self.dataset.iloc[pred_indices][self.sim_config.atr_col].values
        self.true_direction = self.predictions["y_true"].values
        self.pred_direction = self.predictions["y_pred"].values
        self.uncertainty = self.predictions.get(
            "uncertainty", pd.Series([1.0] * len(self.predictions))
        ).values

        # For multi-bar simulation, we need forward returns
        # Calculate cumulative returns for different horizons
        all_returns = self.dataset[self.sim_config.return_col].values
        all_atr = self.dataset[self.sim_config.atr_col].values

        self.forward_returns = {}
        self.forward_atr = {}
        max_horizon = 20  # Support up to 20 bars holding

        for h in range(1, max_horizon + 1):
            fwd_ret = np.zeros(len(pred_indices))
            fwd_atr = np.zeros(len(pred_indices))

            for i, idx in enumerate(pred_indices):
                if idx + h < len(all_returns):
                    # Cumulative return over h bars
                    fwd_ret[i] = np.sum(all_returns[idx : idx + h])
                    # Average ATR over h bars
                    fwd_atr[i] = np.mean(all_atr[idx : idx + h])
                else:
                    fwd_ret[i] = np.nan
                    fwd_atr[i] = np.nan

            self.forward_returns[h] = fwd_ret
            self.forward_atr[h] = fwd_atr

        logger.info(f"Computed forward returns for horizons 1-{max_horizon}")

    def simulate(
        self,
        leverage_config: LeverageConfig,
        sizing_config: PositionSizingConfig,
        exit_config: ExitConfig,
        risk_config: RiskConfig,
    ) -> SimulationResult:
        """
        Run strategy simulation with given parameters.

        Returns SimulationResult with performance metrics.
        """
        # Initialize components
        leverage_calc = LeverageCalculator(leverage_config)
        position_sizer = PositionSizer(sizing_config)
        exit_manager = ExitManager(exit_config)
        risk_manager = RiskManager(risk_config)

        # Simulation state
        capital = self.sim_config.initial_capital
        equity_curve = [capital]
        peak_equity = capital
        daily_start = capital
        trades: list[Trade] = []
        consecutive_losses = 0
        n_liquidations = 0

        # Track running trade stats for Kelly calculation
        wins = []
        losses = []

        # Track exit reasons
        exit_counts: dict[str, int] = {}

        i = 0
        while i < len(self.predictions):
            # Check risk manager
            risk_state = RiskState(
                current_equity=capital,
                peak_equity=peak_equity,
                daily_start_equity=daily_start,
                consecutive_losses=consecutive_losses,
            )
            risk_assessment = risk_manager.assess(risk_state)

            if not risk_assessment.can_open_new:
                # Skip this bar, apply cooldown
                equity_curve.append(capital)
                i += 1
                continue

            # Get prediction for this bar
            pred = int(self.pred_direction[i])
            direction = "LONG" if pred == 1 else "SHORT"
            atr_pct = self.atr[i]
            uncertainty = (
                self.uncertainty[i] if not np.isnan(self.uncertainty[i]) else 1.0
            )

            # Calculate leverage (use MEDIUM vol regime - could be enhanced)
            vol_regime = self._estimate_vol_regime(atr_pct)
            leverage_result = leverage_calc.calculate(
                atr_pct=atr_pct,
                vol_regime=vol_regime,
                confidence=1.0 / max(uncertainty, 0.5),
            )

            # Calculate position size
            if len(wins) >= 5 and len(losses) >= 3:
                trade_stats = TradeStats(
                    win_rate=len(wins) / (len(wins) + len(losses)),
                    avg_win=np.mean(wins) if wins else 0.01,
                    avg_loss=abs(np.mean(losses)) if losses else 0.01,
                )
            else:
                # Default conservative stats until we have history
                trade_stats = TradeStats(win_rate=0.55, avg_win=0.02, avg_loss=0.02)

            size_result = position_sizer.calculate(
                capital=capital,
                trade_stats=trade_stats,
                vol_regime=vol_regime,
                confidence=1.0 / max(uncertainty, 0.5),
            )

            # Apply risk assessment multiplier
            position_size = (
                size_result.position_size * risk_assessment.position_multiplier
            )
            actual_leverage = min(
                leverage_result.leverage, position_size / capital * 10
            )

            # Compute exit barriers
            # Use price = 100 as reference (we work with % returns)
            entry_price = 100.0
            barriers = exit_manager.compute_barriers(
                entry_price=entry_price,
                atr=atr_pct * entry_price,  # Convert ATR% to price units
                direction=direction,
            )

            # Simulate trade through time
            bars_held = 0
            high_since = entry_price
            low_since = entry_price
            exit_bar = i
            exit_reason = ExitReason.TIME_EXIT

            for j in range(1, exit_config.max_holding_bars + 1):
                if i + j >= len(self.predictions):
                    break

                bars_held = j

                # Get cumulative return at this point
                cum_return = self.forward_returns.get(j, self.returns)[i]
                if np.isnan(cum_return):
                    break

                # Current price (as % move from entry)
                current_price = entry_price * (1 + cum_return)

                # Update high/low
                high_since = max(high_since, current_price)
                low_since = min(low_since, current_price)

                # Check for liquidation (simplified)
                if direction == "LONG":
                    adverse_move = (entry_price - low_since) / entry_price
                else:
                    adverse_move = (high_since - entry_price) / entry_price

                if adverse_move * actual_leverage > 0.9:  # 90% of margin gone
                    exit_reason = ExitReason.STOP_LOSS
                    exit_bar = i + j
                    n_liquidations += 1
                    break

                # Check exit conditions
                exit_signal = exit_manager.check_exit(
                    current_price=current_price,
                    entry_price=entry_price,
                    barriers=barriers,
                    bars_held=bars_held,
                    high_since_entry=high_since,
                    low_since_entry=low_since,
                    atr=atr_pct * entry_price,
                )

                if exit_signal.should_exit:
                    exit_reason = exit_signal.reason
                    exit_bar = i + j
                    break

            # Calculate PnL
            final_return = self.forward_returns.get(bars_held, self.returns)[i]
            if np.isnan(final_return):
                final_return = self.returns[i]

            if direction == "SHORT":
                final_return = -final_return

            # Apply leverage
            pnl_pct = final_return * actual_leverage

            # Apply transaction costs
            cost = self.sim_config.transaction_cost_bps / 10000 * 2  # Round trip
            slippage = self.sim_config.slippage_atr_fraction * atr_pct * 2
            pnl_pct -= cost + slippage

            # Apply to capital
            pnl = capital * pnl_pct
            capital += pnl
            capital = max(capital, 0)  # Can't go negative

            # Track trade
            trade = Trade(
                entry_bar=i,
                exit_bar=exit_bar,
                direction=direction,
                entry_price=entry_price,
                exit_price=entry_price
                * (1 + final_return if direction == "LONG" else 1 - final_return),
                position_size=position_size,
                pnl=pnl,
                pnl_pct=pnl_pct,
                exit_reason=exit_reason,
                bars_held=bars_held,
                leverage=actual_leverage,
            )
            trades.append(trade)

            # Update stats
            if pnl > 0:
                wins.append(pnl_pct)
                consecutive_losses = 0
            else:
                losses.append(pnl_pct)
                consecutive_losses += 1

            # Track exit reason
            reason_name = (
                exit_reason.value if hasattr(exit_reason, "value") else str(exit_reason)
            )
            exit_counts[reason_name] = exit_counts.get(reason_name, 0) + 1

            # Update equity tracking
            peak_equity = max(peak_equity, capital)
            equity_curve.append(capital)

            # Skip forward by bars held
            i += max(1, bars_held)

        # Calculate metrics
        equity_arr = np.array(equity_curve)
        returns = np.diff(equity_arr) / equity_arr[:-1]
        returns = returns[~np.isnan(returns)]

        if len(returns) > 1 and np.std(returns) > 0:
            sharpe = np.mean(returns) / np.std(returns) * np.sqrt(252 / 8)  # 8h bars
        else:
            sharpe = 0.0

        # Max drawdown
        running_max = np.maximum.accumulate(equity_arr)
        drawdowns = (equity_arr - running_max) / running_max
        max_dd = float(np.min(drawdowns))

        # Win rate
        n_wins = len([t for t in trades if t.pnl > 0])
        n_trades = len(trades)
        win_rate = n_wins / n_trades if n_trades > 0 else 0

        # Profit factor
        gross_profit = sum(t.pnl for t in trades if t.pnl > 0)
        gross_loss = abs(sum(t.pnl for t in trades if t.pnl < 0))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

        # Total return
        total_return = (
            capital - self.sim_config.initial_capital
        ) / self.sim_config.initial_capital

        # Avg trade PnL
        avg_pnl = np.mean([t.pnl for t in trades]) if trades else 0

        # Build result
        params = {
            "kelly_fraction": sizing_config.kelly_fraction,
            "atr_mult_tp": exit_config.atr_multiplier_tp,
            "atr_mult_sl": exit_config.atr_multiplier_sl,
            "max_holding_bars": exit_config.max_holding_bars,
            "max_leverage": leverage_config.max_leverage,
        }

        return SimulationResult(
            params=params,
            total_return=total_return,
            sharpe_ratio=sharpe,
            max_drawdown=max_dd,
            win_rate=win_rate,
            profit_factor=profit_factor,
            avg_trade_pnl=avg_pnl,
            n_trades=n_trades,
            n_liquidations=n_liquidations,
            exit_distribution=exit_counts,
            trades=trades,
            equity_curve=equity_arr,
        )

    def _estimate_vol_regime(self, atr_pct: float) -> str:
        """Estimate volatility regime from ATR."""
        # Use historical distribution of ATR to determine regime
        # These thresholds based on V_atrPct_6_pct_N statistics
        if atr_pct < 0.016:  # 25th percentile
            return "LOW"
        elif atr_pct > 0.031:  # 75th percentile
            return "HIGH"
        else:
            return "MEDIUM"


def run_kelly_experiment(simulator: StrategySimulator) -> pd.DataFrame:
    """Test different Kelly fractions."""
    kelly_fractions = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50, 0.75, 1.0]

    results = []
    for kf in kelly_fractions:
        logger.info(f"Testing Kelly fraction: {kf}")

        sizing_config = PositionSizingConfig(kelly_fraction=kf)
        leverage_config = LeverageConfig(max_leverage=10.0)
        exit_config = ExitConfig(
            atr_multiplier_tp=2.0,
            atr_multiplier_sl=2.0,
            max_holding_bars=3,
        )
        risk_config = RiskConfig()

        result = simulator.simulate(
            leverage_config=leverage_config,
            sizing_config=sizing_config,
            exit_config=exit_config,
            risk_config=risk_config,
        )

        results.append(
            {
                "kelly_fraction": kf,
                "total_return": result.total_return,
                "sharpe": result.sharpe_ratio,
                "max_dd": result.max_drawdown,
                "win_rate": result.win_rate,
                "profit_factor": result.profit_factor,
                "n_trades": result.n_trades,
                "n_liquidations": result.n_liquidations,
            }
        )

    return pd.DataFrame(results)


def run_atr_experiment(simulator: StrategySimulator) -> pd.DataFrame:
    """Test different ATR multipliers for TP/SL."""
    # Test symmetric and asymmetric configurations
    configs = [
        # Symmetric: TP = SL
        (1.0, 1.0),
        (1.5, 1.5),
        (2.0, 2.0),
        (2.5, 2.5),
        (3.0, 3.0),
        # Asymmetric: TP > SL (let winners run)
        (2.0, 1.0),
        (2.5, 1.5),
        (3.0, 1.5),
        (3.0, 2.0),
        # Asymmetric: SL > TP (tight profit, wide stop)
        (1.0, 2.0),
        (1.5, 2.5),
    ]

    results = []
    for tp_mult, sl_mult in configs:
        logger.info(f"Testing ATR TP={tp_mult}x SL={sl_mult}x")

        sizing_config = PositionSizingConfig(kelly_fraction=0.25)
        leverage_config = LeverageConfig(max_leverage=10.0)
        exit_config = ExitConfig(
            atr_multiplier_tp=tp_mult,
            atr_multiplier_sl=sl_mult,
            max_holding_bars=5,
        )
        risk_config = RiskConfig()

        result = simulator.simulate(
            leverage_config=leverage_config,
            sizing_config=sizing_config,
            exit_config=exit_config,
            risk_config=risk_config,
        )

        results.append(
            {
                "atr_tp": tp_mult,
                "atr_sl": sl_mult,
                "ratio": tp_mult / sl_mult,
                "total_return": result.total_return,
                "sharpe": result.sharpe_ratio,
                "max_dd": result.max_drawdown,
                "win_rate": result.win_rate,
                "profit_factor": result.profit_factor,
                "n_trades": result.n_trades,
                "exit_dist": result.exit_distribution,
            }
        )

    return pd.DataFrame(results)


def run_holding_bars_experiment(simulator: StrategySimulator) -> pd.DataFrame:
    """Test different max holding periods."""
    max_bars_list = [1, 2, 3, 5, 7, 10, 15, 20]

    results = []
    for max_bars in max_bars_list:
        logger.info(f"Testing max holding bars: {max_bars}")

        sizing_config = PositionSizingConfig(kelly_fraction=0.25)
        leverage_config = LeverageConfig(max_leverage=10.0)
        exit_config = ExitConfig(
            atr_multiplier_tp=2.0,
            atr_multiplier_sl=2.0,
            max_holding_bars=max_bars,
        )
        risk_config = RiskConfig()

        result = simulator.simulate(
            leverage_config=leverage_config,
            sizing_config=sizing_config,
            exit_config=exit_config,
            risk_config=risk_config,
        )

        # Calculate average bars held and time exit percentage
        avg_bars = np.mean([t.bars_held for t in result.trades]) if result.trades else 0
        time_exits = result.exit_distribution.get("time_exit", 0)
        time_exit_pct = time_exits / result.n_trades if result.n_trades > 0 else 0

        results.append(
            {
                "max_bars": max_bars,
                "avg_bars_held": avg_bars,
                "time_exit_pct": time_exit_pct,
                "total_return": result.total_return,
                "sharpe": result.sharpe_ratio,
                "max_dd": result.max_drawdown,
                "win_rate": result.win_rate,
                "profit_factor": result.profit_factor,
                "n_trades": result.n_trades,
            }
        )

    return pd.DataFrame(results)


def run_regime_multiplier_experiment(simulator: StrategySimulator) -> pd.DataFrame:
    """Test different regime multipliers for position sizing."""
    configs = [
        # (low_mult, med_mult, high_mult)
        (1.0, 1.0, 1.0),  # No regime adjustment
        (1.3, 1.0, 0.7),  # Mild adjustment
        (1.5, 1.0, 0.5),  # Default (research-based)
        (2.0, 1.0, 0.3),  # Aggressive
        (1.5, 1.0, 0.0),  # No trading in HIGH vol
    ]

    results = []
    for low_m, med_m, high_m in configs:
        logger.info(f"Testing regime mults: LOW={low_m}, MED={med_m}, HIGH={high_m}")

        sizing_config = PositionSizingConfig(
            kelly_fraction=0.25,
            regime_multiplier_low=low_m,
            regime_multiplier_medium=med_m,
            regime_multiplier_high=high_m,
        )
        leverage_config = LeverageConfig(max_leverage=10.0)
        exit_config = ExitConfig(
            atr_multiplier_tp=2.0,
            atr_multiplier_sl=2.0,
            max_holding_bars=3,
        )
        risk_config = RiskConfig()

        result = simulator.simulate(
            leverage_config=leverage_config,
            sizing_config=sizing_config,
            exit_config=exit_config,
            risk_config=risk_config,
        )

        results.append(
            {
                "low_mult": low_m,
                "med_mult": med_m,
                "high_mult": high_m,
                "total_return": result.total_return,
                "sharpe": result.sharpe_ratio,
                "max_dd": result.max_drawdown,
                "win_rate": result.win_rate,
                "profit_factor": result.profit_factor,
                "n_trades": result.n_trades,
            }
        )

    return pd.DataFrame(results)


def run_all_experiments(output_dir: Path) -> dict[str, pd.DataFrame]:
    """Run all parameter experiments and save results."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # Initialize simulator
    predictions_path = Path("data/backtest_results/direction_1bar_predictions.parquet")
    dataset_path = Path("data/datasets/direction_1bar.parquet")
    simulator = StrategySimulator(predictions_path, dataset_path)

    results = {}

    # Run experiments
    print("\n" + "=" * 60)
    print("PHASE 2: PARAMETER RESEARCH")
    print("=" * 60)

    print("\n📊 Experiment 1: Kelly Fraction Optimization")
    print("-" * 40)
    kelly_results = run_kelly_experiment(simulator)
    kelly_results.to_csv(output_dir / "kelly_experiment.csv", index=False)
    print(kelly_results.to_string(index=False))
    results["kelly"] = kelly_results

    print("\n📊 Experiment 2: ATR Multiplier Optimization")
    print("-" * 40)
    atr_results = run_atr_experiment(simulator)
    atr_results.to_csv(output_dir / "atr_experiment.csv", index=False)
    print(atr_results.drop(columns=["exit_dist"]).to_string(index=False))
    results["atr"] = atr_results

    print("\n📊 Experiment 3: Max Holding Bars Optimization")
    print("-" * 40)
    holding_results = run_holding_bars_experiment(simulator)
    holding_results.to_csv(output_dir / "holding_bars_experiment.csv", index=False)
    print(holding_results.to_string(index=False))
    results["holding_bars"] = holding_results

    print("\n📊 Experiment 4: Regime Multiplier Calibration")
    print("-" * 40)
    regime_results = run_regime_multiplier_experiment(simulator)
    regime_results.to_csv(output_dir / "regime_multiplier_experiment.csv", index=False)
    print(regime_results.to_string(index=False))
    results["regime"] = regime_results

    # Generate summary
    print("\n" + "=" * 60)
    print("OPTIMAL PARAMETERS SUMMARY")
    print("=" * 60)

    # Best Kelly (by Sharpe)
    best_kelly = kelly_results.loc[kelly_results["sharpe"].idxmax()]
    print(f"\n✅ Best Kelly Fraction: {best_kelly['kelly_fraction']:.2f}")
    print(f"   Sharpe: {best_kelly['sharpe']:.3f}, MaxDD: {best_kelly['max_dd']:.1%}")

    # Best ATR (by Sharpe)
    best_atr = atr_results.loc[atr_results["sharpe"].idxmax()]
    print(f"\n✅ Best ATR Config: TP={best_atr['atr_tp']}x, SL={best_atr['atr_sl']}x")
    print(f"   Sharpe: {best_atr['sharpe']:.3f}, Win Rate: {best_atr['win_rate']:.1%}")

    # Best holding bars (by Sharpe)
    best_holding = holding_results.loc[holding_results["sharpe"].idxmax()]
    print(f"\n✅ Best Max Holding Bars: {int(best_holding['max_bars'])}")
    print(
        f"   Sharpe: {best_holding['sharpe']:.3f}, Avg Bars: {best_holding['avg_bars_held']:.1f}"
    )

    # Best regime config (by Sharpe)
    best_regime = regime_results.loc[regime_results["sharpe"].idxmax()]
    print(
        f"\n✅ Best Regime Multipliers: LOW={best_regime['low_mult']}, MED={best_regime['med_mult']}, HIGH={best_regime['high_mult']}"
    )
    print(f"   Sharpe: {best_regime['sharpe']:.3f}, MaxDD: {best_regime['max_dd']:.1%}")

    # Save summary
    summary = {
        "timestamp": datetime.now().isoformat(),
        "optimal_kelly": float(best_kelly["kelly_fraction"]),
        "optimal_atr_tp": float(best_atr["atr_tp"]),
        "optimal_atr_sl": float(best_atr["atr_sl"]),
        "optimal_max_bars": int(best_holding["max_bars"]),
        "optimal_regime_low": float(best_regime["low_mult"]),
        "optimal_regime_med": float(best_regime["med_mult"]),
        "optimal_regime_high": float(best_regime["high_mult"]),
    }

    with open(output_dir / "optimal_params.json", "w") as f:
        json.dump(summary, f, indent=2)

    return results


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    parser = argparse.ArgumentParser(description="Phase 2: Parameter Research")
    parser.add_argument(
        "--experiment",
        choices=["kelly", "atr", "holding", "regime", "all"],
        default="all",
        help="Which experiment to run",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/strategy_research"),
        help="Output directory for results",
    )

    args = parser.parse_args()

    if args.experiment == "all":
        run_all_experiments(args.output_dir)
    else:
        # Initialize simulator
        predictions_path = Path(
            "data/backtest_results/direction_1bar_predictions.parquet"
        )
        dataset_path = Path("data/datasets/direction_1bar.parquet")
        simulator = StrategySimulator(predictions_path, dataset_path)
        args.output_dir.mkdir(parents=True, exist_ok=True)

        if args.experiment == "kelly":
            results = run_kelly_experiment(simulator)
            results.to_csv(args.output_dir / "kelly_experiment.csv", index=False)
            print(results.to_string(index=False))
        elif args.experiment == "atr":
            results = run_atr_experiment(simulator)
            results.to_csv(args.output_dir / "atr_experiment.csv", index=False)
            print(results.drop(columns=["exit_dist"]).to_string(index=False))
        elif args.experiment == "holding":
            results = run_holding_bars_experiment(simulator)
            results.to_csv(args.output_dir / "holding_bars_experiment.csv", index=False)
            print(results.to_string(index=False))
        elif args.experiment == "regime":
            results = run_regime_multiplier_experiment(simulator)
            results.to_csv(
                args.output_dir / "regime_multiplier_experiment.csv", index=False
            )
            print(results.to_string(index=False))


if __name__ == "__main__":
    main()
