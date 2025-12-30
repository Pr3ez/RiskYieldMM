/**
 * Astra Workflow - Lifecycle Tools
 *
 * Tools for managing workflow session and task lifecycle:
 * - astra_session_start: Initialize new session
 * - astra_session_end: Cleanly close session
 * - astra_task_start: Begin a new task
 * - astra_task_complete: Complete current task
 */
import * as vscode from 'vscode';
import type { ToolContext } from './index.js';
import { SessionStartInput, SessionEndInput, TaskStartInput, TaskCompleteInput } from '../types.js';
export declare function createSessionStartTool(ctx: ToolContext): vscode.LanguageModelTool<SessionStartInput>;
export declare function createSessionEndTool(ctx: ToolContext): vscode.LanguageModelTool<SessionEndInput>;
export declare function createTaskStartTool(ctx: ToolContext): vscode.LanguageModelTool<TaskStartInput>;
export declare function createTaskCompleteTool(ctx: ToolContext): vscode.LanguageModelTool<TaskCompleteInput>;
//# sourceMappingURL=lifecycle.d.ts.map