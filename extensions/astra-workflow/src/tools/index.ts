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
export function createToolResult(data: unknown): vscode.LanguageModelToolResult {
  return new vscode.LanguageModelToolResult([
    new vscode.LanguageModelTextPart(JSON.stringify(data, null, 2))
  ]);
}

/**
 * Helper to create an error tool result
 */
export function createErrorResult(error: string): vscode.LanguageModelToolResult {
  return new vscode.LanguageModelToolResult([
    new vscode.LanguageModelTextPart(JSON.stringify({ error }, null, 2))
  ]);
}

// Import tool implementations (after helpers are defined)
import { 
  createSessionStartTool,
  createSessionEndTool,
  createTaskStartTool,
  createTaskCompleteTool
} from './lifecycle.js';

import {
  createSetGoalTool,
  createSetContextTool,
  createSetPlanTool
} from './planning.js';

import {
  createStepStartTool,
  createStepCompleteTool,
  createStepBlockTool,
  createValidateTool
} from './execution.js';

import {
  createDriftCheckTool,
  createMemoryCheckTool,
  createIdentityCheckTool,
  createGetStateTool
} from './monitoring.js';

/**
 * Register all 15 Astra workflow tools with VS Code
 * 
 * @param context Extension context for subscriptions
 * @param toolContext Shared state for all tools
 * @returns Array of disposables for cleanup
 */
export function registerAllTools(
  context: vscode.ExtensionContext,
  toolContext: ToolContext
): vscode.Disposable[] {
  const disposables: vscode.Disposable[] = [];

  toolContext.log('Registering Astra Workflow tools...');

  // Lifecycle tools (4)
  disposables.push(
    vscode.lm.registerTool('astra_session_start', createSessionStartTool(toolContext)),
    vscode.lm.registerTool('astra_session_end', createSessionEndTool(toolContext)),
    vscode.lm.registerTool('astra_task_start', createTaskStartTool(toolContext)),
    vscode.lm.registerTool('astra_task_complete', createTaskCompleteTool(toolContext))
  );
  toolContext.log('  ✓ Lifecycle tools registered (4)');

  // Planning tools (3)
  disposables.push(
    vscode.lm.registerTool('astra_set_goal', createSetGoalTool(toolContext)),
    vscode.lm.registerTool('astra_set_context', createSetContextTool(toolContext)),
    vscode.lm.registerTool('astra_set_plan', createSetPlanTool(toolContext))
  );
  toolContext.log('  ✓ Planning tools registered (3)');

  // Execution tools (4)
  disposables.push(
    vscode.lm.registerTool('astra_step_start', createStepStartTool(toolContext)),
    vscode.lm.registerTool('astra_step_complete', createStepCompleteTool(toolContext)),
    vscode.lm.registerTool('astra_step_block', createStepBlockTool(toolContext)),
    vscode.lm.registerTool('astra_validate', createValidateTool(toolContext))
  );
  toolContext.log('  ✓ Execution tools registered (4)');

  // Monitoring tools (4)
  disposables.push(
    vscode.lm.registerTool('astra_drift_check', createDriftCheckTool(toolContext)),
    vscode.lm.registerTool('astra_memory_check', createMemoryCheckTool(toolContext)),
    vscode.lm.registerTool('astra_identity_check', createIdentityCheckTool(toolContext)),
    vscode.lm.registerTool('astra_get_state', createGetStateTool(toolContext))
  );
  toolContext.log('  ✓ Monitoring tools registered (4)');

  toolContext.log(`All ${disposables.length} Astra Workflow tools registered`);

  // Add all disposables to extension context
  for (const disposable of disposables) {
    context.subscriptions.push(disposable);
  }

  return disposables;
}
