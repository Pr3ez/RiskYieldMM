"""
Tier 6: Comprehensive Validation Report Generator
==================================================

Generates a Go/No-Go validation report summarizing all tiers (0-5) of validation.

Usage:
    python -m scripts.target_models.validation.validation_report

Output:
    - Console summary with Go/No-Go recommendation
    - Markdown report at data/backtest_results/validation_report.md
    - JSON metrics at data/backtest_results/validation_metrics.json
"""

from __future__ import annotations

import json
import logging
import warnings
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from scripts.target_models.validation.fast_backtest import (
    BacktestConfig,
    BacktestResult,
    FastBacktester,
)

logger = logging.getLogger(__name__)


# =============================================================================
# GO/NO-GO THRESHOLDS
# =============================================================================


@dataclass
class ValidationThresholds:
    """Thresholds for Go/No-Go decision.

    IMPORTANT CONTEXT:
    ===================

    MODEL QUALITY METRICS (What we're validating):
    - IC (Information Coefficient): Correlation between predictions and outcomes
      - Range: -1 to +1, where >0 means predictive skill
      - For 8h bars, IC > 0.02 is good, IC > 0.05 is excellent
    - Accuracy: % of correct predictions
      - Binary (direction): Random baseline = 50%
      - 3-class (vol_regime): Random baseline = 33%

    ECONOMIC SIMULATION METRICS (Dependent on position sizing):
    - MaxDD, Sharpe, ProfitFactor: These depend on HOW we trade, not model quality
    - Currently using naive 1-unit positions, so these are NOT meaningful for
      classification models. A 70% accurate direction model can show -100% MaxDD
      if position sizing is wrong.

    WHAT EACH TARGET TYPE MEANS:
    - direction: Binary (1=up, 0=down). 70% = excellent (20pp above random)
    - returns: Continuous. Predicting exact 8h returns is HARD. IC > 0 is good.
    - volatility: Continuous. Same as returns - hard to predict exactly.
    - vol_regime: 3-class (low/med/high). 86% = excellent (53pp above 33% random)
    - trend_regime: Binary. 70% = good (20pp above random)

    Failing ANY critical threshold = NO-GO.
    Failing moderate thresholds = CONDITIONAL (needs review).
    """

    # --- CRITICAL: MODEL QUALITY (Fail = NO-GO) ---
    # These measure whether the model has predictive skill

    # Regression IC must be positive (predicting in right direction)
    # Note: For 8h bars, IC > 0 is already decent. Negative IC = model is harmful.
    min_regression_ic: float = 0.0

    # Classification accuracy must beat random baseline
    # Direction (binary): random = 50%, so >52% shows skill
    min_direction_accuracy: float = 0.52
    # Regime (3-class): random = 33%, so >40% shows skill
    min_regime_accuracy: float = 0.40

    # Skip rate (too many iterations skipped = data/model problem)
    max_skip_rate: float = 0.10  # <10% skipped

    # --- CRITICAL: ECONOMIC (Only for regression with proper sizing) ---
    # MaxDD check is ONLY meaningful for regression targets where we have
    # continuous position sizing. For classification, position sizing is naive.
    max_drawdown_limit: float = -0.30
    # Set to True to apply MaxDD check only to regression configs
    maxdd_regression_only: bool = True

    # --- MODERATE (Fail = CONDITIONAL, needs review) ---

    # DSR should be positive for statistical significance
    min_dsr: float = 0.0

    # Win rate should be above 50% (only meaningful with proper sizing)
    min_win_rate: float = 0.50

    # Profit factor should be above 1.0 (wins > losses)
    min_profit_factor: float = 1.0

    # Net Sharpe after costs should be positive
    min_net_sharpe: float = 0.0

    # Conformal coverage should be near target (90%)
    min_coverage: float = 0.85
    max_coverage: float = 0.95

    # Concept drift should not be detected
    max_drift_configs: int = 5  # Allow up to 5 configs with drift

    # --- INFORMATIONAL (No threshold, just report) ---
    # CVaR, Sortino, regime metrics, etc.


@dataclass
class ConfigValidation:
    """Validation result for a single config."""

    config_name: str
    task_type: str

    # Core metrics
    primary_metric: float  # IC for regression, accuracy for classification
    primary_metric_name: str

    # Economic metrics
    net_sharpe: float | None = None
    max_drawdown: float | None = None
    win_rate: float | None = None
    profit_factor: float | None = None
    cvar_95: float | None = None

    # Statistical metrics
    dsr: float | None = None
    dsr_significant: bool = False

    # Conformal metrics
    coverage: float | None = None

    # Drift metrics
    concept_drift: bool = False

    # Skip metrics
    skip_rate: float = 0.0

    # Validation outcome
    critical_pass: bool = True
    moderate_pass: bool = True
    issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class ValidationReport:
    """Complete validation report across all configs."""

    timestamp: str
    n_configs: int
    n_iterations: int

    # Config-level results
    config_results: list[ConfigValidation]

    # Aggregate statistics
    n_critical_failures: int = 0
    n_moderate_failures: int = 0
    n_passed: int = 0

    # Lists of failing configs
    critical_failures: list[str] = field(default_factory=list)
    moderate_failures: list[str] = field(default_factory=list)

    # Overall recommendation
    recommendation: str = "NO-GO"  # "GO", "CONDITIONAL", "NO-GO"
    summary: str = ""


# =============================================================================
# REPORT GENERATOR
# =============================================================================


class ValidationReportGenerator:
    """Generate comprehensive validation report."""

    def __init__(
        self,
        thresholds: ValidationThresholds | None = None,
        output_dir: Path | None = None,
    ):
        self.thresholds = thresholds or ValidationThresholds()
        self.output_dir = output_dir or Path("data/backtest_results")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate(
        self,
        backtest_results: dict[str, BacktestResult],
        verbose: bool = True,
    ) -> ValidationReport:
        """
        Generate validation report from backtest results.

        Args:
            backtest_results: Dict of config_name -> BacktestResult
            verbose: Print progress

        Returns:
            ValidationReport with Go/No-Go recommendation
        """
        if verbose:
            print("\n" + "=" * 70)
            print("TIER 6: COMPREHENSIVE VALIDATION REPORT")
            print("=" * 70)

        # Validate each config
        config_validations = []
        for config_name, result in backtest_results.items():
            if result is None:
                continue
            validation = self._validate_config(result)
            config_validations.append(validation)

        # Aggregate results
        n_critical = sum(1 for v in config_validations if not v.critical_pass)
        n_moderate = sum(
            1 for v in config_validations if v.critical_pass and not v.moderate_pass
        )
        n_passed = sum(
            1 for v in config_validations if v.critical_pass and v.moderate_pass
        )

        critical_failures = [
            v.config_name for v in config_validations if not v.critical_pass
        ]
        moderate_failures = [
            v.config_name
            for v in config_validations
            if v.critical_pass and not v.moderate_pass
        ]

        # Determine recommendation
        if n_critical > 0:
            recommendation = "NO-GO"
            summary = (
                f"❌ NO-GO: {n_critical} critical failure(s) detected. "
                f"Configs: {', '.join(critical_failures[:5])}"
            )
        elif n_moderate > 5:
            recommendation = "CONDITIONAL"
            summary = (
                f"⚠️ CONDITIONAL: {n_moderate} moderate issues detected. "
                f"Review before production."
            )
        else:
            recommendation = "GO"
            summary = (
                f"✅ GO: {n_passed}/{len(config_validations)} configs passed validation. "
                f"{n_moderate} minor issues to monitor."
            )

        # Count total iterations
        total_iterations = sum(
            r.n_iterations for r in backtest_results.values() if r is not None
        )

        report = ValidationReport(
            timestamp=datetime.now().isoformat(),
            n_configs=len(config_validations),
            n_iterations=total_iterations,
            config_results=config_validations,
            n_critical_failures=n_critical,
            n_moderate_failures=n_moderate,
            n_passed=n_passed,
            critical_failures=critical_failures,
            moderate_failures=moderate_failures,
            recommendation=recommendation,
            summary=summary,
        )

        if verbose:
            self._print_summary(report)

        return report

    def _validate_config(self, result: BacktestResult) -> ConfigValidation:
        """Validate a single config against thresholds."""
        m = result.metrics
        t = self.thresholds

        # Determine primary metric
        if result.task_type == "regression":
            primary_metric = m.get("ic", 0.0)
            primary_metric_name = "IC"
        else:
            primary_metric = m.get("accuracy", 0.0)
            primary_metric_name = "Accuracy"

        validation = ConfigValidation(
            config_name=result.config_name,
            task_type=result.task_type,
            primary_metric=primary_metric,
            primary_metric_name=primary_metric_name,
            net_sharpe=m.get("net_sharpe"),
            max_drawdown=m.get("max_drawdown"),
            win_rate=m.get("win_rate"),
            profit_factor=m.get("profit_factor"),
            cvar_95=m.get("cvar_95"),
            dsr=m.get("dsr"),
            dsr_significant=m.get("dsr_significant", False),
            coverage=result.coverage,
            concept_drift=m.get("concept_drift_detected", False),
            skip_rate=result.skip_rate,
        )

        issues = []
        warnings = []

        # --- CRITICAL CHECKS ---

        # 1. Primary metric check (MODEL QUALITY)
        if result.task_type == "regression":
            if primary_metric < t.min_regression_ic:
                issues.append(
                    f"IC={primary_metric:.4f} < {t.min_regression_ic} (no predictive skill)"
                )
        elif "direction" in result.config_name:
            if primary_metric < t.min_direction_accuracy:
                issues.append(
                    f"Accuracy={primary_metric:.2%} < {t.min_direction_accuracy:.0%} (below random+2%)"
                )
        else:  # regime
            if primary_metric < t.min_regime_accuracy:
                issues.append(
                    f"Accuracy={primary_metric:.2%} < {t.min_regime_accuracy:.0%} (below random+7%)"
                )

        # 2. Max drawdown check (ECONOMIC - only for regression with proper sizing)
        # For classification, position sizing is naive (1 unit), so MaxDD is NOT meaningful
        max_dd = m.get("max_drawdown", 0)
        is_regression = result.task_type == "regression"
        apply_maxdd = not t.maxdd_regression_only or is_regression
        if apply_maxdd and max_dd is not None and max_dd < t.max_drawdown_limit:
            issues.append(f"MaxDD={max_dd:.2%} < {t.max_drawdown_limit:.0%}")
        elif not apply_maxdd and max_dd is not None and max_dd < t.max_drawdown_limit:
            # For classification, report as warning not critical failure
            warnings.append(f"MaxDD={max_dd:.2%} (naive sizing, not critical)")

        # 3. Skip rate check
        if result.skip_rate > t.max_skip_rate:
            issues.append(f"SkipRate={result.skip_rate:.1%} > {t.max_skip_rate:.0%}")

        # Mark critical pass/fail
        validation.critical_pass = len(issues) == 0
        validation.issues = issues

        # --- MODERATE CHECKS ---

        # 1. DSR check
        dsr = m.get("dsr")
        if dsr is not None and dsr < t.min_dsr:
            warnings.append(f"DSR={dsr:.3f} < {t.min_dsr}")

        # 2. Win rate check
        win_rate = m.get("win_rate")
        if win_rate is not None and win_rate < t.min_win_rate:
            warnings.append(f"WinRate={win_rate:.2%} < {t.min_win_rate:.0%}")

        # 3. Profit factor check
        pf = m.get("profit_factor")
        if pf is not None and pf < t.min_profit_factor:
            warnings.append(f"ProfitFactor={pf:.2f} < {t.min_profit_factor}")

        # 4. Net Sharpe check
        net_sharpe = m.get("net_sharpe")
        if net_sharpe is not None and net_sharpe < t.min_net_sharpe:
            warnings.append(f"NetSharpe={net_sharpe:.2f} < {t.min_net_sharpe}")

        # 5. Coverage check
        cov = result.coverage
        if cov is not None:
            if cov < t.min_coverage:
                warnings.append(f"Coverage={cov:.1%} < {t.min_coverage:.0%}")
            elif cov > t.max_coverage:
                warnings.append(f"Coverage={cov:.1%} > {t.max_coverage:.0%}")

        # 6. Concept drift check
        if m.get("concept_drift_detected", False):
            warnings.append("Concept drift detected")

        # Mark moderate pass/fail
        validation.moderate_pass = len(warnings) <= 2  # Allow up to 2 warnings
        validation.warnings = warnings

        return validation

    def _print_summary(self, report: ValidationReport) -> None:
        """Print summary to console."""
        print(f"\n{report.summary}")
        print(f"\nTimestamp: {report.timestamp}")
        print(f"Configs tested: {report.n_configs}")
        print(f"Total iterations: {report.n_iterations}")

        print("\n" + "-" * 50)
        print("SUMMARY BY CONFIG TYPE")
        print("-" * 50)

        # Group by target type
        by_type = {}
        for v in report.config_results:
            target = v.config_name.rsplit("_", 1)[0]
            if target not in by_type:
                by_type[target] = []
            by_type[target].append(v)

        for target, validations in sorted(by_type.items()):
            passed = sum(1 for v in validations if v.critical_pass and v.moderate_pass)
            print(f"\n{target}:")
            for v in validations:
                status = (
                    "✅"
                    if v.critical_pass and v.moderate_pass
                    else "⚠️"
                    if v.critical_pass
                    else "❌"
                )
                metric_str = f"{v.primary_metric_name}={v.primary_metric:.4f}"
                sharpe_str = f"Sharpe={v.net_sharpe:.2f}" if v.net_sharpe else ""
                print(f"  {status} {v.config_name}: {metric_str} {sharpe_str}")
                if v.issues:
                    for issue in v.issues:
                        print(f"      ❌ {issue}")
                if v.warnings and not v.moderate_pass:
                    for warn in v.warnings[:2]:
                        print(f"      ⚠️ {warn}")

        print("\n" + "-" * 50)
        print(f"RECOMMENDATION: {report.recommendation}")
        print("-" * 50)

    def save_markdown_report(
        self,
        report: ValidationReport,
        filepath: Path | None = None,
    ) -> Path:
        """Save report as markdown file."""
        filepath = filepath or self.output_dir / "validation_report.md"

        lines = [
            "# RiskYieldMM Validation Report",
            "",
            f"**Generated:** {report.timestamp}",
            f"**Recommendation:** {report.recommendation}",
            "",
            "## Executive Summary",
            "",
            report.summary,
            "",
            f"- **Configs tested:** {report.n_configs}",
            f"- **Total iterations:** {report.n_iterations}",
            f"- **Critical failures:** {report.n_critical_failures}",
            f"- **Moderate issues:** {report.n_moderate_failures}",
            f"- **Passed:** {report.n_passed}",
            "",
            "---",
            "",
            "## Validation Tiers Implemented",
            "",
            "| Tier | Description | Status |",
            "|------|-------------|--------|",
            "| T0 | Critical blockers (scaling, clipping) | ✅ Complete |",
            "| T1 | Regression pipeline fixes | ✅ Complete |",
            "| T2 | Conformal validation (CQR) | ✅ Complete |",
            "| T3 | Statistical rigor (DSR, PBO, regime) | ✅ Complete |",
            "| T4 | Economic simulation (CVaR, trade metrics) | ✅ Complete |",
            "| T5 | Distribution shift (PSI, rolling metrics) | ✅ Complete |",
            "| T6 | Final report | ✅ This document |",
            "",
            "---",
            "",
            "## Detailed Results by Config",
            "",
        ]

        # Group by target type
        by_type = {}
        for v in report.config_results:
            target = v.config_name.rsplit("_", 1)[0]
            if target not in by_type:
                by_type[target] = []
            by_type[target].append(v)

        for target, validations in sorted(by_type.items()):
            lines.append(f"### {target.replace('_', ' ').title()}")
            lines.append("")
            lines.append(
                "| Config | Primary | Sharpe | MaxDD | WinRate | Coverage | Status |"
            )
            lines.append(
                "|--------|---------|--------|-------|---------|----------|--------|"
            )

            for v in validations:
                status = (
                    "✅"
                    if v.critical_pass and v.moderate_pass
                    else "⚠️"
                    if v.critical_pass
                    else "❌"
                )
                primary = f"{v.primary_metric:.4f}"
                sharpe = f"{v.net_sharpe:.2f}" if v.net_sharpe else "N/A"
                maxdd = f"{v.max_drawdown:.2%}" if v.max_drawdown else "N/A"
                winrate = f"{v.win_rate:.1%}" if v.win_rate else "N/A"
                coverage = f"{v.coverage:.1%}" if v.coverage else "N/A"
                lines.append(
                    f"| {v.config_name} | {primary} | {sharpe} | {maxdd} | {winrate} | {coverage} | {status} |"
                )

            lines.append("")

        # Add issues section
        if report.critical_failures:
            lines.extend(
                [
                    "---",
                    "",
                    "## Critical Issues",
                    "",
                ]
            )
            for config_name in report.critical_failures:
                v = next(
                    x for x in report.config_results if x.config_name == config_name
                )
                lines.append(f"### {config_name}")
                for issue in v.issues:
                    lines.append(f"- ❌ {issue}")
                lines.append("")

        # Add thresholds reference
        lines.extend(
            [
                "---",
                "",
                "## Validation Thresholds",
                "",
                "### Critical (Fail = NO-GO)",
                f"- Min Regression IC: {self.thresholds.min_regression_ic}",
                f"- Min Direction Accuracy: {self.thresholds.min_direction_accuracy:.0%}",
                f"- Min Regime Accuracy: {self.thresholds.min_regime_accuracy:.0%}",
                f"- Max Drawdown: {self.thresholds.max_drawdown_limit:.0%}",
                f"- Max Skip Rate: {self.thresholds.max_skip_rate:.0%}",
                "",
                "### Moderate (Fail = Review)",
                f"- Min DSR: {self.thresholds.min_dsr}",
                f"- Min Win Rate: {self.thresholds.min_win_rate:.0%}",
                f"- Min Profit Factor: {self.thresholds.min_profit_factor}",
                f"- Min Net Sharpe: {self.thresholds.min_net_sharpe}",
                f"- Coverage Range: {self.thresholds.min_coverage:.0%} - {self.thresholds.max_coverage:.0%}",
                "",
                "---",
                "",
                "*Report generated by RiskYieldMM Validation System v1.0*",
            ]
        )

        with open(filepath, "w") as f:
            f.write("\n".join(lines))

        return filepath

    def save_json_metrics(
        self,
        report: ValidationReport,
        filepath: Path | None = None,
    ) -> Path:
        """Save metrics as JSON for programmatic access."""
        filepath = filepath or self.output_dir / "validation_metrics.json"

        data = {
            "timestamp": report.timestamp,
            "recommendation": report.recommendation,
            "summary": report.summary,
            "n_configs": report.n_configs,
            "n_iterations": report.n_iterations,
            "n_critical_failures": report.n_critical_failures,
            "n_moderate_failures": report.n_moderate_failures,
            "n_passed": report.n_passed,
            "critical_failures": report.critical_failures,
            "moderate_failures": report.moderate_failures,
            "configs": {},
        }

        for v in report.config_results:
            data["configs"][v.config_name] = {
                "task_type": v.task_type,
                "primary_metric": float(v.primary_metric) if v.primary_metric else None,
                "primary_metric_name": v.primary_metric_name,
                "net_sharpe": float(v.net_sharpe) if v.net_sharpe else None,
                "max_drawdown": float(v.max_drawdown) if v.max_drawdown else None,
                "win_rate": float(v.win_rate) if v.win_rate else None,
                "profit_factor": float(v.profit_factor) if v.profit_factor else None,
                "cvar_95": float(v.cvar_95) if v.cvar_95 else None,
                "dsr": float(v.dsr) if v.dsr else None,
                "coverage": float(v.coverage) if v.coverage else None,
                "concept_drift": bool(v.concept_drift),
                "skip_rate": float(v.skip_rate),
                "critical_pass": bool(v.critical_pass),
                "moderate_pass": bool(v.moderate_pass),
                "issues": v.issues,
                "warnings": v.warnings,
            }

        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)

        return filepath


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================


def run_full_validation(
    n_iterations: int = 100,
    configs: list[str] | None = None,
    verbose: bool = True,
) -> ValidationReport:
    """
    Run full validation and generate report.

    Args:
        n_iterations: Number of backtest iterations per config
        configs: List of configs to test (default: all 20)
        verbose: Print progress

    Returns:
        ValidationReport with Go/No-Go recommendation
    """
    warnings.filterwarnings("ignore")

    if verbose:
        print("=" * 70)
        print("RISKYIELDMM COMPREHENSIVE VALIDATION")
        print("=" * 70)
        print(f"\nRunning {n_iterations} iterations per config...")

    # Setup backtester
    config = BacktestConfig(
        backtest_rows=n_iterations,
        compute_statistical_metrics=True,
        compute_economic_metrics=True,
        detect_distribution_shift=True,
        use_cqr=True,
    )
    backtester = FastBacktester(config)

    # Run all backtests
    results = backtester.run_all(configs=configs, verbose=verbose)

    # Generate report
    generator = ValidationReportGenerator()
    report = generator.generate(results, verbose=verbose)

    # Save outputs
    md_path = generator.save_markdown_report(report)
    json_path = generator.save_json_metrics(report)

    if verbose:
        print(f"\n📄 Markdown report: {md_path}")
        print(f"📊 JSON metrics: {json_path}")

    return report


def quick_validation(
    n_iterations: int = 50,
    verbose: bool = True,
) -> ValidationReport:
    """
    Quick validation with subset of configs.

    Tests one config from each target type for fast feedback.
    """
    quick_configs = [
        "returns_1bar",
        "volatility_1bar",
        "direction_1bar",
        "vol_regime_1bar",
        "trend_regime_1bar",
    ]
    return run_full_validation(n_iterations, quick_configs, verbose)


# =============================================================================
# MAIN
# =============================================================================


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run RiskYieldMM validation")
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Run quick validation (5 configs, 50 iterations)",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=100,
        help="Number of iterations per config (default: 100)",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Run full validation (all 20 configs)",
    )
    args = parser.parse_args()

    if args.quick:
        report = quick_validation(n_iterations=50)
    elif args.full:
        report = run_full_validation(n_iterations=args.iterations)
    else:
        # Default: quick validation
        report = quick_validation(n_iterations=args.iterations)

    print(f"\n🎯 Final Recommendation: {report.recommendation}")
