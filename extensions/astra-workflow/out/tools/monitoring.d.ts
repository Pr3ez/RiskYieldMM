/**
 * Astra Workflow - Monitoring Tools
 *
 * Tools for cognitive health monitoring:
 * - astra_drift_check: Verify still on track
 * - astra_memory_check: Verify memory is current
 * - astra_identity_check: Verify identity grounded
 * - astra_get_state: Get current workflow state
 */
import * as vscode from 'vscode';
import type { ToolContext } from './index.js';
import { DriftCheckInput, MemoryCheckInput, IdentityCheckInput, GetStateInput } from '../types.js';
export declare function createDriftCheckTool(ctx: ToolContext): vscode.LanguageModelTool<DriftCheckInput>;
export declare function createMemoryCheckTool(ctx: ToolContext): vscode.LanguageModelTool<MemoryCheckInput>;
export declare function createIdentityCheckTool(ctx: ToolContext): vscode.LanguageModelTool<IdentityCheckInput>;
export declare function createGetStateTool(ctx: ToolContext): vscode.LanguageModelTool<GetStateInput>;
//# sourceMappingURL=monitoring.d.ts.map