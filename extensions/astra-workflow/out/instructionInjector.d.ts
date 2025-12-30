/**
 * Astra Workflow - Instruction Injector
 *
 * Injects workflow state and reminders into copilot instructions.
 * Works with the .github/copilot-instructions.md file.
 *
 * COORDINATION WITH OTHER EXTENSIONS:
 * - Agent TODOs injects <todos> block at TOP of file
 * - Agent Memory injects TL;DR summary (auto-sync)
 * - Astra injects <astra-workflow> section AFTER </todos> if present
 *
 * Based on research from 02-AGENT-MEMORY.md and 03-AGENT-TODOS.md
 */
import * as vscode from "vscode";
import { WorkflowStateMachine } from "./stateMachine.js";
import { WorkflowPhase, TaskType, VirtueMetrics, DetectedPathology } from "./types.js";
import { CognitiveMetricsMonitor, MetricAlert } from "./metricsMonitor.js";
export declare class InstructionInjector {
    private static readonly WORKFLOW_MARKER_START;
    private static readonly WORKFLOW_MARKER_END;
    private static readonly ASTRA_TAG_START;
    private static readonly ASTRA_TAG_END;
    private static readonly TODOS_TAG_END;
    /**
     * Get the copilot instructions file path
     */
    private static getInstructionsPath;
    /**
     * Generate passive reminder based on current phase
     */
    static generatePassiveReminder(phase: WorkflowPhase): string;
    /**
     * Generate virtue status summary
     */
    static generateVirtueStatus(virtueMetrics: VirtueMetrics): string;
    /**
     * Generate pathology warnings
     */
    static generatePathologyWarnings(pathologies: DetectedPathology[]): string;
    /**
     * Generate <astra-workflow> XML section
     * This format coordinates with Agent TODOs' <todos> section
     */
    static generateAstraWorkflowSection(stateMachine: WorkflowStateMachine, alerts: MetricAlert[], virtueMetrics?: VirtueMetrics, pathologies?: DetectedPathology[]): string;
    /**
     * Generate workflow section content (legacy format for backward compatibility)
     */
    static generateWorkflowSection(stateMachine: WorkflowStateMachine, alerts: MetricAlert[]): string;
    /**
     * Find the best insertion point for <astra-workflow>
     * Priority: After </todos> > After title > At start
     */
    private static findInsertionPoint;
    /**
     * Inject <astra-workflow> section into copilot instructions
     * Coordinates with Agent TODOs by inserting AFTER </todos>
     */
    static injectAstraSection(workspaceFolder: vscode.WorkspaceFolder, stateMachine: WorkflowStateMachine, metricsMonitor: CognitiveMetricsMonitor, virtueMetrics?: VirtueMetrics, pathologies?: DetectedPathology[]): Promise<void>;
    /**
     * Inject workflow section into copilot instructions (legacy method)
     */
    static injectWorkflowSection(workspaceFolder: vscode.WorkspaceFolder, stateMachine: WorkflowStateMachine, metricsMonitor: CognitiveMetricsMonitor): Promise<void>;
    /**
     * Remove workflow section from copilot instructions
     */
    static removeWorkflowSection(workspaceFolder: vscode.WorkspaceFolder): Promise<void>;
}
/**
 * Simple heuristics to detect task type from user input
 */
export declare function detectTaskType(input: string): TaskType;
//# sourceMappingURL=instructionInjector.d.ts.map