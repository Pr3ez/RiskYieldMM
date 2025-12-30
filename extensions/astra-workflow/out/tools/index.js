"use strict";
/**
 * Astra Workflow Tools - Registration Hub
 *
 * Registers all 15 language model tools with VS Code.
 * Tools are declared in package.json and implemented here.
 */
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
exports.createToolResult = createToolResult;
exports.createErrorResult = createErrorResult;
exports.registerAllTools = registerAllTools;
const vscode = __importStar(require("vscode"));
/**
 * Helper to create a standard tool result
 */
function createToolResult(data) {
    return new vscode.LanguageModelToolResult([
        new vscode.LanguageModelTextPart(JSON.stringify(data, null, 2))
    ]);
}
/**
 * Helper to create an error tool result
 */
function createErrorResult(error) {
    return new vscode.LanguageModelToolResult([
        new vscode.LanguageModelTextPart(JSON.stringify({ error }, null, 2))
    ]);
}
// Import tool implementations (after helpers are defined)
const lifecycle_js_1 = require("./lifecycle.js");
const planning_js_1 = require("./planning.js");
const execution_js_1 = require("./execution.js");
const monitoring_js_1 = require("./monitoring.js");
/**
 * Register all 15 Astra workflow tools with VS Code
 *
 * @param context Extension context for subscriptions
 * @param toolContext Shared state for all tools
 * @returns Array of disposables for cleanup
 */
function registerAllTools(context, toolContext) {
    const disposables = [];
    toolContext.log('Registering Astra Workflow tools...');
    // Lifecycle tools (4)
    disposables.push(vscode.lm.registerTool('astra_session_start', (0, lifecycle_js_1.createSessionStartTool)(toolContext)), vscode.lm.registerTool('astra_session_end', (0, lifecycle_js_1.createSessionEndTool)(toolContext)), vscode.lm.registerTool('astra_task_start', (0, lifecycle_js_1.createTaskStartTool)(toolContext)), vscode.lm.registerTool('astra_task_complete', (0, lifecycle_js_1.createTaskCompleteTool)(toolContext)));
    toolContext.log('  ✓ Lifecycle tools registered (4)');
    // Planning tools (3)
    disposables.push(vscode.lm.registerTool('astra_set_goal', (0, planning_js_1.createSetGoalTool)(toolContext)), vscode.lm.registerTool('astra_set_context', (0, planning_js_1.createSetContextTool)(toolContext)), vscode.lm.registerTool('astra_set_plan', (0, planning_js_1.createSetPlanTool)(toolContext)));
    toolContext.log('  ✓ Planning tools registered (3)');
    // Execution tools (4)
    disposables.push(vscode.lm.registerTool('astra_step_start', (0, execution_js_1.createStepStartTool)(toolContext)), vscode.lm.registerTool('astra_step_complete', (0, execution_js_1.createStepCompleteTool)(toolContext)), vscode.lm.registerTool('astra_step_block', (0, execution_js_1.createStepBlockTool)(toolContext)), vscode.lm.registerTool('astra_validate', (0, execution_js_1.createValidateTool)(toolContext)));
    toolContext.log('  ✓ Execution tools registered (4)');
    // Monitoring tools (4)
    disposables.push(vscode.lm.registerTool('astra_drift_check', (0, monitoring_js_1.createDriftCheckTool)(toolContext)), vscode.lm.registerTool('astra_memory_check', (0, monitoring_js_1.createMemoryCheckTool)(toolContext)), vscode.lm.registerTool('astra_identity_check', (0, monitoring_js_1.createIdentityCheckTool)(toolContext)), vscode.lm.registerTool('astra_get_state', (0, monitoring_js_1.createGetStateTool)(toolContext)));
    toolContext.log('  ✓ Monitoring tools registered (4)');
    toolContext.log(`All ${disposables.length} Astra Workflow tools registered`);
    // Add all disposables to extension context
    for (const disposable of disposables) {
        context.subscriptions.push(disposable);
    }
    return disposables;
}
//# sourceMappingURL=index.js.map