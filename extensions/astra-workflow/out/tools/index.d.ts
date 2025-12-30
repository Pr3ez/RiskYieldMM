/**
 * Astra Workflow Tools - Registration Hub
 *
 * Registers all 15 language model tools with VS Code.
 * Tools are declared in package.json and implemented here.
 */
import * as vscode from 'vscode';
import { WorkflowStateMachine } from '../stateMachine.js';
import { CognitiveMetricsMonitor } from '../metricsMonitor.js';
/**
 * Tool context shared across all tools
 */
export interface ToolContext {
    stateMachine: WorkflowStateMachine;
    metricsMonitor: CognitiveMetricsMonitor;
    outputChannel: vscode.OutputChannel;
    log: (message: string) => void;
}
/**
 * Helper to create a standard tool result
 */
export declare function createToolResult(data: unknown): vscode.LanguageModelToolResult;
/**
 * Helper to create an error tool result
 */
export declare function createErrorResult(error: string): vscode.LanguageModelToolResult;
/**
 * Register all 15 Astra workflow tools with VS Code
 *
 * @param context Extension context for subscriptions
 * @param toolContext Shared state for all tools
 * @returns Array of disposables for cleanup
 */
export declare function registerAllTools(context: vscode.ExtensionContext, toolContext: ToolContext): vscode.Disposable[];
//# sourceMappingURL=index.d.ts.map