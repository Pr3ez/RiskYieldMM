/**
 * Astra Workflow - Cognitive Metrics Monitor
 *
 * Inspired by Netdata's per-metric anomaly detection.
 * Tracks cognitive health metrics and alerts on anomalies.
 */

import {
  CognitiveMetrics,
  MetricThresholds,
  DEFAULT_THRESHOLDS,
  WorkflowEvent,
} from "./types.js";

// =============================================================================
// METRIC ALERT TYPES
// =============================================================================

export interface MetricAlert {
  metric: string;
  description: string;
  currentValue: number;
  threshold: number;
  severity: "warning" | "critical";
  suggestion: string;
}

// =============================================================================
// METRICS MONITOR
// =============================================================================

export class CognitiveMetricsMonitor {
  private thresholds: MetricThresholds;
  private listeners: Array<(event: WorkflowEvent) => void> = [];

  constructor(thresholds: MetricThresholds = DEFAULT_THRESHOLDS) {
    this.thresholds = thresholds;
  }

  subscribe(listener: (event: WorkflowEvent) => void): () => void {
    this.listeners.push(listener);
    return () => {
      this.listeners = this.listeners.filter((l) => l !== listener);
    };
  }

  private emit(event: WorkflowEvent): void {
    for (const listener of this.listeners) {
      try {
        listener(event);
      } catch (error) {
        console.error("Metrics monitor listener error:", error);
      }
    }
  }

  /**
   * Check all metrics and return alerts
   */
  checkHealth(metrics: CognitiveMetrics): MetricAlert[] {
    const alerts: MetricAlert[] = [];

    // 1. Identity Drift Rate
    if (metrics.identityChecks > 0) {
      const driftRate = metrics.driftDetections / metrics.identityChecks;
      if (driftRate > this.thresholds.maxDriftRate) {
        alerts.push({
          metric: "Identity Drift Rate",
          description: `${(driftRate * 100).toFixed(1)}% of identity checks detected drift`,
          currentValue: driftRate,
          threshold: this.thresholds.maxDriftRate,
          severity: driftRate > this.thresholds.maxDriftRate * 1.5 ? "critical" : "warning",
          suggestion: "Re-anchor with core.md. Consider why drift is occurring so frequently.",
        });
      }
    }

    // 2. Memory Hygiene
    if (metrics.stepsExecuted > 0) {
      const memoryCheckFrequency = metrics.memoryChecks / metrics.stepsExecuted;
      if (memoryCheckFrequency < this.thresholds.minMemoryCheckFrequency) {
        alerts.push({
          metric: "Memory Check Frequency",
          description: `Only ${(memoryCheckFrequency * 100).toFixed(1)}% memory check rate`,
          currentValue: memoryCheckFrequency,
          threshold: this.thresholds.minMemoryCheckFrequency,
          severity: "warning",
          suggestion: "Run memory check now. Consider more frequent checks.",
        });
      }
    }

    // 3. TODO Adherence
    if (metrics.stepsWithoutTodo > this.thresholds.maxStepsWithoutTodo) {
      alerts.push({
        metric: "TODO Adherence",
        description: `${metrics.stepsWithoutTodo} steps executed without TODOs`,
        currentValue: metrics.stepsWithoutTodo,
        threshold: this.thresholds.maxStepsWithoutTodo,
        severity: metrics.stepsWithoutTodo > this.thresholds.maxStepsWithoutTodo * 2 ? "critical" : "warning",
        suggestion: "Create TODOs for remaining work. Track all steps explicitly.",
      });
    }

    // 4. Verification Rate
    if (metrics.claimsMade > 0) {
      const verificationRate = metrics.claimsVerified / metrics.claimsMade;
      if (verificationRate < this.thresholds.minVerificationRate) {
        alerts.push({
          metric: "Verification Rate",
          description: `Only ${(verificationRate * 100).toFixed(1)}% of claims verified`,
          currentValue: verificationRate,
          threshold: this.thresholds.minVerificationRate,
          severity: "critical",
          suggestion: "STOP and verify unverified claims. Don't proceed without validation.",
        });
      }
    }

    // 5. Partnership Balance
    const totalDecisions = metrics.unilateralDecisions + metrics.analysisPresented;
    if (totalDecisions > 0) {
      const unilateralRate = metrics.unilateralDecisions / totalDecisions;
      if (unilateralRate > this.thresholds.maxUnilateralDecisionRate) {
        alerts.push({
          metric: "Partnership Balance",
          description: `${(unilateralRate * 100).toFixed(1)}% of decisions made unilaterally`,
          currentValue: unilateralRate,
          threshold: this.thresholds.maxUnilateralDecisionRate,
          severity: "warning",
          suggestion: "Present analysis instead of making decisions. Let user decide.",
        });
      }
    }

    // 6. Workflow Compliance
    const totalTransitions = metrics.validTransitions + metrics.invalidTransitions;
    if (totalTransitions > 0) {
      const invalidRate = metrics.invalidTransitions / totalTransitions;
      if (invalidRate > this.thresholds.maxInvalidTransitionRate) {
        alerts.push({
          metric: "Workflow Compliance",
          description: `${(invalidRate * 100).toFixed(1)}% invalid state transitions`,
          currentValue: invalidRate,
          threshold: this.thresholds.maxInvalidTransitionRate,
          severity: "critical",
          suggestion: "Follow the workflow state machine. Don't skip phases.",
        });
      }
    }

    // Emit alerts
    for (const alert of alerts) {
      this.emit({
        type: "METRIC_ALERT",
        metric: alert.metric,
        value: alert.currentValue,
        threshold: alert.threshold,
      });
    }

    return alerts;
  }

  /**
   * Generate a health report
   */
  generateReport(metrics: CognitiveMetrics): string {
    const alerts = this.checkHealth(metrics);
    const sessionDuration = Date.now() - metrics.sessionStart.getTime();
    const durationMinutes = Math.round(sessionDuration / 60000);

    let report = `# Cognitive Health Report\n\n`;
    report += `**Session:** ${metrics.sessionId}\n`;
    report += `**Duration:** ${durationMinutes} minutes\n\n`;

    // Summary metrics
    report += `## Metrics Summary\n\n`;
    report += `| Metric | Value |\n`;
    report += `|--------|-------|\n`;
    report += `| Steps Executed | ${metrics.stepsExecuted} |\n`;
    report += `| TODOs Created | ${metrics.todosCreated} |\n`;
    report += `| TODOs Completed | ${metrics.todosCompleted} |\n`;
    report += `| Memory Reads | ${metrics.memoryReads} |\n`;
    report += `| Memory Writes | ${metrics.memoryWrites} |\n`;
    report += `| Memory Checks | ${metrics.memoryChecks} |\n`;
    report += `| Identity Checks | ${metrics.identityChecks} |\n`;
    report += `| Drift Detections | ${metrics.driftDetections} |\n`;
    report += `| Valid Transitions | ${metrics.validTransitions} |\n`;
    report += `| Invalid Transitions | ${metrics.invalidTransitions} |\n`;
    report += `| Verification Failures | ${metrics.verificationFailures} |\n`;

    // Alerts
    report += `\n## Alerts (${alerts.length})\n\n`;
    if (alerts.length === 0) {
      report += `✅ No alerts. Cognitive health looks good.\n`;
    } else {
      for (const alert of alerts) {
        const icon = alert.severity === "critical" ? "🔴" : "🟡";
        report += `### ${icon} ${alert.metric}\n\n`;
        report += `**${alert.description}**\n\n`;
        report += `- Current: ${(alert.currentValue * 100).toFixed(1)}%\n`;
        report += `- Threshold: ${(alert.threshold * 100).toFixed(1)}%\n`;
        report += `- Suggestion: ${alert.suggestion}\n\n`;
      }
    }

    // Calculated rates
    report += `## Calculated Rates\n\n`;

    const driftRate = metrics.identityChecks > 0
      ? (metrics.driftDetections / metrics.identityChecks * 100).toFixed(1)
      : "N/A";
    const verificationRate = metrics.claimsMade > 0
      ? (metrics.claimsVerified / metrics.claimsMade * 100).toFixed(1)
      : "N/A";
    const memoryCheckRate = metrics.stepsExecuted > 0
      ? (metrics.memoryChecks / metrics.stepsExecuted * 100).toFixed(1)
      : "N/A";

    report += `| Rate | Value |\n`;
    report += `|------|-------|\n`;
    report += `| Drift Rate | ${driftRate}% |\n`;
    report += `| Verification Rate | ${verificationRate}% |\n`;
    report += `| Memory Check Rate | ${memoryCheckRate}% |\n`;

    return report;
  }
}
