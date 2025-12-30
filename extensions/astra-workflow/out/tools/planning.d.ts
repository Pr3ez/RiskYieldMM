/**
 * Astra Workflow - Planning Tools
 *
 * Tools for defining goals, collecting context, and creating plans:
 * - astra_set_goal: Define task goal with success/failure conditions
 * - astra_set_context: Record known/unknown/assumptions
 * - astra_set_plan: Create execution plan with steps
 */
import * as vscode from 'vscode';
import type { ToolContext } from './index.js';
import { SetGoalInput, SetContextInput, SetPlanInput } from '../types.js';
export declare function createSetGoalTool(ctx: ToolContext): vscode.LanguageModelTool<SetGoalInput>;
export declare function createSetContextTool(ctx: ToolContext): vscode.LanguageModelTool<SetContextInput>;
export declare function createSetPlanTool(ctx: ToolContext): vscode.LanguageModelTool<SetPlanInput>;
//# sourceMappingURL=planning.d.ts.map