"""
Rolling Conformal Coverage Monitor

Tracks conformal prediction coverage over time with:
1. Rolling coverage calculation
2. Alert system when coverage drops below threshold
3. Regime-conditional coverage tracking
4. Export utilities for analysis

Usage:
    monitor = CoverageMonitor(target_coverage=0.90, alert_threshold=0.85)
    for prediction, actual in stream:
        is_covered = check_coverage(prediction, actual)
        monitor.update(is_covered)
        if monitor.alert_triggered:
            print(f"ALERT: Coverage dropped to {monitor.rolling_coverage:.1%}")
"""

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np


@dataclass
class CoverageAlert:
    """Alert generated when coverage drops below threshold."""

    timestamp_idx: int
    rolling_coverage: float
    threshold: float
    window_size: int
    consecutive_below: int
    severity: str  # "warning", "critical"

    def __repr__(self) -> str:
        return (
            f"CoverageAlert({self.severity}: {self.rolling_coverage:.1%} < "
            f"{self.threshold:.1%} at idx={self.timestamp_idx})"
        )


@dataclass
class CoverageStats:
    """Summary statistics for coverage monitoring."""

    total_samples: int
    overall_coverage: float
    rolling_coverage: float
    min_coverage: float
    max_coverage: float
    coverage_std: float
    n_alerts: int
    time_below_threshold: float  # Fraction of time below threshold
    consecutive_below: int  # Current consecutive periods below


class CoverageMonitor:
    """
    Rolling conformal coverage monitor with alert system.

    Tracks whether conformal predictions are maintaining their
    target coverage rate over a rolling window.

    Attributes:
        target_coverage: Target coverage rate (e.g., 0.90)
        alert_threshold: Coverage below this triggers alerts (e.g., 0.85)
        window_size: Rolling window size for coverage calculation
        min_consecutive: Min consecutive periods below threshold for alert
    """

    def __init__(
        self,
        target_coverage: float = 0.90,
        alert_threshold: float = 0.85,
        critical_threshold: float = 0.75,
        window_size: int = 50,
        min_consecutive: int = 3,
    ):
        """
        Initialize coverage monitor.

        Args:
            target_coverage: Target coverage rate (default 0.90)
            alert_threshold: Warning alert threshold (default 0.85)
            critical_threshold: Critical alert threshold (default 0.75)
            window_size: Rolling window for coverage calc (default 50)
            min_consecutive: Min consecutive low periods for alert (default 3)
        """
        if not 0.5 <= target_coverage <= 0.99:
            raise ValueError("target_coverage must be in [0.5, 0.99]")
        if not alert_threshold < target_coverage:
            raise ValueError("alert_threshold must be < target_coverage")
        if not critical_threshold < alert_threshold:
            raise ValueError("critical_threshold must be < alert_threshold")

        self.target_coverage = target_coverage
        self.alert_threshold = alert_threshold
        self.critical_threshold = critical_threshold
        self.window_size = window_size
        self.min_consecutive = min_consecutive

        # State
        self._covered_history: list[bool] = []
        self._rolling_coverage_history: list[float] = []
        self._alerts: list[CoverageAlert] = []
        self._consecutive_below: int = 0
        self._current_idx: int = 0

        # Callbacks
        self._alert_callbacks: list[Callable[[CoverageAlert], None]] = []

    def update(self, is_covered: bool) -> CoverageAlert | None:
        """
        Update monitor with new observation.

        Args:
            is_covered: Whether the true value was covered by the prediction

        Returns:
            CoverageAlert if an alert was triggered, None otherwise
        """
        self._covered_history.append(is_covered)
        self._current_idx += 1

        # Calculate rolling coverage
        if len(self._covered_history) >= self.window_size:
            window = self._covered_history[-self.window_size :]
            rolling_cov = sum(window) / len(window)
        else:
            rolling_cov = sum(self._covered_history) / len(self._covered_history)

        self._rolling_coverage_history.append(rolling_cov)

        # Check for alerts
        alert = self._check_alert(rolling_cov)
        if alert:
            self._alerts.append(alert)
            for callback in self._alert_callbacks:
                callback(alert)

        return alert

    def update_batch(self, covered_array: np.ndarray) -> list[CoverageAlert]:
        """
        Update monitor with batch of observations.

        Args:
            covered_array: Boolean array indicating coverage for each sample

        Returns:
            List of alerts triggered during batch
        """
        alerts = []
        for is_covered in covered_array:
            alert = self.update(bool(is_covered))
            if alert:
                alerts.append(alert)
        return alerts

    def _check_alert(self, rolling_coverage: float) -> CoverageAlert | None:
        """Check if coverage warrants an alert."""
        # Determine if we're below threshold
        if rolling_coverage < self.critical_threshold:
            self._consecutive_below += 1
            severity = "critical"
        elif rolling_coverage < self.alert_threshold:
            self._consecutive_below += 1
            severity = "warning"
        else:
            self._consecutive_below = 0
            return None

        # Only alert after min_consecutive periods
        if self._consecutive_below >= self.min_consecutive:
            return CoverageAlert(
                timestamp_idx=self._current_idx,
                rolling_coverage=rolling_coverage,
                threshold=(
                    self.critical_threshold
                    if severity == "critical"
                    else self.alert_threshold
                ),
                window_size=self.window_size,
                consecutive_below=self._consecutive_below,
                severity=severity,
            )

        return None

    @property
    def rolling_coverage(self) -> float:
        """Current rolling coverage rate."""
        if not self._rolling_coverage_history:
            return 1.0
        return self._rolling_coverage_history[-1]

    @property
    def overall_coverage(self) -> float:
        """Overall coverage across all samples."""
        if not self._covered_history:
            return 1.0
        return sum(self._covered_history) / len(self._covered_history)

    @property
    def alert_triggered(self) -> bool:
        """Whether an alert is currently active."""
        return self._consecutive_below >= self.min_consecutive

    @property
    def alerts(self) -> list[CoverageAlert]:
        """List of all alerts generated."""
        return self._alerts.copy()

    def register_alert_callback(
        self, callback: Callable[[CoverageAlert], None]
    ) -> None:
        """Register a callback to be called when alerts are triggered."""
        self._alert_callbacks.append(callback)

    def get_stats(self) -> CoverageStats:
        """Get summary statistics."""
        if not self._rolling_coverage_history:
            return CoverageStats(
                total_samples=0,
                overall_coverage=1.0,
                rolling_coverage=1.0,
                min_coverage=1.0,
                max_coverage=1.0,
                coverage_std=0.0,
                n_alerts=0,
                time_below_threshold=0.0,
                consecutive_below=0,
            )

        cov_arr = np.array(self._rolling_coverage_history)
        below_threshold = cov_arr < self.alert_threshold

        return CoverageStats(
            total_samples=len(self._covered_history),
            overall_coverage=self.overall_coverage,
            rolling_coverage=self.rolling_coverage,
            min_coverage=float(np.min(cov_arr)),
            max_coverage=float(np.max(cov_arr)),
            coverage_std=float(np.std(cov_arr)),
            n_alerts=len(self._alerts),
            time_below_threshold=float(np.mean(below_threshold)),
            consecutive_below=self._consecutive_below,
        )

    def get_coverage_history(self) -> np.ndarray:
        """Get full rolling coverage history as array."""
        return np.array(self._rolling_coverage_history)

    def reset(self) -> None:
        """Reset monitor state."""
        self._covered_history = []
        self._rolling_coverage_history = []
        self._alerts = []
        self._consecutive_below = 0
        self._current_idx = 0

    def __repr__(self) -> str:
        stats = self.get_stats()
        alert_str = f", {stats.n_alerts} alerts" if stats.n_alerts > 0 else ""
        return (
            f"CoverageMonitor(n={stats.total_samples}, "
            f"coverage={stats.rolling_coverage:.1%}, "
            f"target={self.target_coverage:.1%}{alert_str})"
        )


class RegimeAwareCoverageMonitor:
    """
    Coverage monitor that tracks coverage separately by regime.

    Useful for detecting if coverage is worse in certain market conditions.
    """

    def __init__(
        self,
        target_coverage: float = 0.90,
        alert_threshold: float = 0.85,
        window_size: int = 50,
    ):
        """
        Initialize regime-aware monitor.

        Args:
            target_coverage: Target coverage rate
            alert_threshold: Alert threshold
            window_size: Rolling window size
        """
        self.target_coverage = target_coverage
        self.alert_threshold = alert_threshold
        self.window_size = window_size

        self._monitors: dict[str, CoverageMonitor] = {}
        self._global_monitor = CoverageMonitor(
            target_coverage=target_coverage,
            alert_threshold=alert_threshold,
            window_size=window_size,
        )

    def update(
        self, is_covered: bool, regime: str | None = None
    ) -> list[CoverageAlert]:
        """
        Update with observation and optional regime label.

        Args:
            is_covered: Whether true value was covered
            regime: Optional regime label (e.g., "high_vol", "low_vol")

        Returns:
            List of alerts (from global and regime-specific monitors)
        """
        alerts = []

        # Update global monitor
        global_alert = self._global_monitor.update(is_covered)
        if global_alert:
            alerts.append(global_alert)

        # Update regime-specific monitor
        if regime is not None:
            if regime not in self._monitors:
                self._monitors[regime] = CoverageMonitor(
                    target_coverage=self.target_coverage,
                    alert_threshold=self.alert_threshold,
                    window_size=self.window_size,
                )
            regime_alert = self._monitors[regime].update(is_covered)
            if regime_alert:
                alerts.append(regime_alert)

        return alerts

    def get_regime_stats(self) -> dict[str, CoverageStats]:
        """Get stats for each regime."""
        stats = {"global": self._global_monitor.get_stats()}
        for regime, monitor in self._monitors.items():
            stats[regime] = monitor.get_stats()
        return stats

    def get_regime_comparison(self) -> str:
        """Get formatted comparison of coverage across regimes."""
        stats = self.get_regime_stats()
        lines = [
            "Regime Coverage Comparison:",
            "-" * 50,
            f"{'Regime':<15} {'Coverage':>10} {'Min':>10} {'Alerts':>8}",
            "-" * 50,
        ]

        for regime, s in stats.items():
            lines.append(
                f"{regime:<15} {s.rolling_coverage:>10.1%} "
                f"{s.min_coverage:>10.1%} {s.n_alerts:>8}"
            )

        lines.append("-" * 50)
        return "\n".join(lines)

    def __repr__(self) -> str:
        return (
            f"RegimeAwareCoverageMonitor("
            f"global={self._global_monitor.rolling_coverage:.1%}, "
            f"regimes={list(self._monitors.keys())})"
        )
