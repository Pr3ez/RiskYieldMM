/**
 * Astra Workflow - Cognitive Metrics Monitor
 *
 * Inspired by Netdata's per-metric anomaly detection.
 * Tracks cognitive health metrics and alerts on anomalies.
 */
import { CognitiveMetrics, MetricThresholds, WorkflowEvent } from "./types.js";
export interface MetricAlert {
    metric: string;
    description: string;
    currentValue: number;
    threshold: number;
    severity: "warning" | "critical";
    suggestion: string;
}
export declare class CognitiveMetricsMonitor {
    private thresholds;
    private listeners;
    constructor(thresholds?: MetricThresholds);
    subscribe(listener: (event: WorkflowEvent) => void): () => void;
    private emit;
    /**
     * Check all metrics and return alerts
     */
    checkHealth(metrics: CognitiveMetrics): MetricAlert[];
    /**
     * Generate a health report
     */
    generateReport(metrics: CognitiveMetrics): string;
}
//# sourceMappingURL=metricsMonitor.d.ts.map