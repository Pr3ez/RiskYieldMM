/**
 * Astra Workflow - Execution Tools
 *
 * Tools for executing planned steps:
 * - astra_step_start: Begin executing a step
 * - astra_step_complete: Mark step as done
 * - astra_step_block: Mark step as blocked
 * - astra_validate: Validate step completion
 */
import * as vscode from 'vscode';
import type { ToolContext } from './index.js';
import { StepStartInput, StepCompleteInput, StepBlockInput, ValidateInput } from '../types.js';
export declare function createStepStartTool(ctx: ToolContext): vscode.LanguageModelTool<StepStartInput>;
export declare function createStepCompleteTool(ctx: ToolContext): vscode.LanguageModelTool<StepCompleteInput>;
export declare function createStepBlockTool(ctx: ToolContext): vscode.LanguageModelTool<StepBlockInput>;
export declare function createValidateTool(ctx: ToolContext): vscode.LanguageModelTool<ValidateInput>;
//# sourceMappingURL=execution.d.ts.map