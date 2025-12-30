"use strict";
/**
 * Astra Workflow - Main Extension Entry Point
 *
 * VS Code extension that enforces the Universal Guide workflow methodology.
 * Integrates with Agent Memory and Agent TODOs extensions.
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
exports.activate = activate;
exports.deactivate = deactivate;
const vscode = __importStar(require("vscode"));
const stateMachine_js_1 = require("./stateMachine.js");
const metricsMonitor_js_1 = require("./metricsMonitor.js");
const instructionInjector_js_1 = require("./instructionInjector.js");
const memoryIntegration_js_1 = require("./memoryIntegration.js");
const index_js_1 = require("./tools/index.js");
const types_js_1 = require("./types.js");
// =============================================================================
// EXTENSION STATE
// =============================================================================
let stateMachine;
let metricsMonitor;
let memoryIntegration;
let statusBarItem;
let outputChannel;
let autoSaveTimer = null;
const SESSION_ID = `session-${Date.now()}`;
// =============================================================================
// ACTIVATION
// =============================================================================
async function activate(context) {
    outputChannel = vscode.window.createOutputChannel("Astra Workflow");
    log("Astra Workflow extension activating...");
    // Initialize components
    stateMachine = new stateMachine_js_1.WorkflowStateMachine(SESSION_ID);
    metricsMonitor = createMetricsMonitor();
    memoryIntegration = new memoryIntegration_js_1.MemoryIntegration();
    // Create status bar
    statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 100);
    statusBarItem.command = "astra-workflow.showStatus";
    context.subscriptions.push(statusBarItem);
    updateStatusBar();
    // Register commands
    registerCommands(context);
    // Register Language Model Tools
    const toolContext = {
        stateMachine,
        metricsMonitor,
        outputChannel,
        log
    };
    (0, index_js_1.registerAllTools)(context, toolContext);
    // Start auto-save timer
    startAutoSave(context);
    // Load persisted state
    await loadPersistedState(context);
    // Initial injection
    await updateInstructions();
    log("Astra Workflow extension activated");
    vscode.window.showInformationMessage("Astra Workflow activated");
}
// =============================================================================
// DEACTIVATION
// =============================================================================
async function deactivate() {
    log("Astra Workflow extension deactivating...");
    // Stop timers
    if (autoSaveTimer) {
        clearInterval(autoSaveTimer);
        autoSaveTimer = null;
    }
    // Clean up instructions file
    const workspaceFolder = vscode.workspace.workspaceFolders?.[0];
    if (workspaceFolder) {
        await instructionInjector_js_1.InstructionInjector.removeWorkflowSection(workspaceFolder);
    }
    log("Astra Workflow extension deactivated");
}
// =============================================================================
// COMMAND REGISTRATION
// =============================================================================
function registerCommands(context) {
    const commands = [
        { id: "astra-workflow.startTask", handler: cmdStartTask },
        { id: "astra-workflow.completeTask", handler: cmdCompleteTask },
        { id: "astra-workflow.valueGate", handler: cmdValueGate },
        { id: "astra-workflow.defineGoal", handler: cmdDefineGoal },
        { id: "astra-workflow.createPlan", handler: cmdCreatePlan },
        { id: "astra-workflow.startStep", handler: cmdStartStep },
        { id: "astra-workflow.completeStep", handler: cmdCompleteStep },
        { id: "astra-workflow.validateStep", handler: cmdValidateStep },
        { id: "astra-workflow.driftCheck", handler: cmdDriftCheck },
        { id: "astra-workflow.memoryCheck", handler: cmdMemoryCheck },
        { id: "astra-workflow.showStatus", handler: cmdShowStatus },
        { id: "astra-workflow.reportError", handler: cmdReportError },
        { id: "astra-workflow.resetWorkflow", handler: cmdResetWorkflow },
        { id: "astra-workflow.showDashboard", handler: cmdShowDashboard },
    ];
    for (const cmd of commands) {
        const disposable = vscode.commands.registerCommand(cmd.id, cmd.handler);
        context.subscriptions.push(disposable);
    }
}
// =============================================================================
// COMMAND HANDLERS
// =============================================================================
async function cmdStartTask() {
    log("Command: Start Task");
    const taskDescription = await vscode.window.showInputBox({
        prompt: "What task do you want to start?",
        placeHolder: "e.g., Implement user authentication",
    });
    if (!taskDescription)
        return;
    const taskType = (0, instructionInjector_js_1.detectTaskType)(taskDescription);
    if (taskType === types_js_1.TaskType.TRIVIAL) {
        stateMachine.startTask(types_js_1.TaskType.TRIVIAL);
        vscode.window.showInformationMessage("Trivial task detected. Workflow simplified.");
    }
    else {
        stateMachine.startTask(taskType);
        await cmdValueGate();
    }
    await updateInstructions();
    updateStatusBar();
}
async function cmdValueGate() {
    log("Command: Value Gate");
    const questions = [
        "If you succeed, what is the concrete benefit?",
        "Is this the simplest way to achieve that benefit?",
        'What happens if you don\'t do this? (If "nothing" → STOP)',
    ];
    const answers = [];
    for (const question of questions) {
        const answer = await vscode.window.showInputBox({
            prompt: question,
            placeHolder: "Your answer...",
        });
        if (!answer) {
            vscode.window.showWarningMessage("Value Gate incomplete. Task cancelled.");
            stateMachine.failValueGate("Incomplete answers");
            await updateInstructions();
            return;
        }
        answers.push(answer);
    }
    const lastAnswer = answers[2];
    if (lastAnswer && lastAnswer.toLowerCase().includes("nothing")) {
        const proceed = await vscode.window.showWarningMessage('You said "nothing" happens. Are you sure you want to proceed?', "Yes, proceed", "No, cancel");
        if (proceed !== "Yes, proceed") {
            stateMachine.failValueGate("No value justified");
            await updateInstructions();
            return;
        }
    }
    stateMachine.passValueGate(answers.join(" | "));
    vscode.window.showInformationMessage("Value Gate passed. Define your goal.");
    await updateInstructions();
    updateStatusBar();
}
async function cmdDefineGoal() {
    log("Command: Define Goal");
    const statement = await vscode.window.showInputBox({
        prompt: "State your goal in ONE clear sentence",
        placeHolder: "e.g., Create a login form with email and password validation",
    });
    if (!statement)
        return;
    const successCondition = await vscode.window.showInputBox({
        prompt: "How will you know you succeeded?",
        placeHolder: "e.g., User can log in with valid credentials",
    });
    if (!successCondition)
        return;
    const failureCondition = await vscode.window.showInputBox({
        prompt: "How will you know you failed?",
        placeHolder: "e.g., Login rejects valid credentials",
    });
    if (!failureCondition)
        return;
    const timeBudgetStr = await vscode.window.showInputBox({
        prompt: "Time budget in minutes (optional, press Enter to skip)",
        placeHolder: "e.g., 60",
    });
    const goal = {
        statement,
        successCondition,
        failureCondition,
        timeBudget: timeBudgetStr ? parseInt(timeBudgetStr, 10) : undefined,
    };
    stateMachine.setGoal(goal);
    vscode.window.showInformationMessage("Goal defined. Collect context next.");
    await updateInstructions();
    updateStatusBar();
}
async function cmdCreatePlan() {
    log("Command: Create Plan");
    const steps = [];
    let addingSteps = true;
    while (addingSteps) {
        const stepTitle = await vscode.window.showInputBox({
            prompt: `Step ${steps.length + 1} title (press Escape to finish)`,
            placeHolder: "e.g., Create login form component",
        });
        if (!stepTitle) {
            if (steps.length === 0) {
                vscode.window.showWarningMessage("Plan must have at least one step.");
                continue;
            }
            addingSteps = false;
            continue;
        }
        const stepDescription = (await vscode.window.showInputBox({
            prompt: "Step description",
            placeHolder: "What needs to be done in this step?",
        })) || stepTitle;
        const validationMethod = (await vscode.window.showInputBox({
            prompt: "How will you validate this step?",
            placeHolder: "e.g., Unit tests pass",
        })) || "Manual verification";
        const estimatedEffortStr = await vscode.window.showInputBox({
            prompt: "Estimated effort in minutes (optional)",
            placeHolder: "e.g., 30",
        });
        const step = {
            id: `step-${steps.length + 1}`,
            title: stepTitle,
            description: stepDescription,
            status: "not-started",
            validationMethod: validationMethod,
        };
        if (estimatedEffortStr) {
            step.estimatedMinutes = parseInt(estimatedEffortStr, 10);
        }
        steps.push(step);
    }
    stateMachine.setPlan(steps);
    vscode.window.showInformationMessage(`Plan created with ${steps.length} steps.`);
    await updateInstructions();
    updateStatusBar();
}
async function cmdStartStep() {
    log("Command: Start Step");
    const state = stateMachine.getState();
    const pendingSteps = state.steps.filter((s) => s.status === "not-started");
    if (pendingSteps.length === 0) {
        vscode.window.showWarningMessage("No pending steps to start.");
        return;
    }
    const items = pendingSteps.map((s) => ({
        label: s.id,
        description: s.title,
        detail: s.description,
        stepId: s.id,
    }));
    const selected = await vscode.window.showQuickPick(items, {
        placeHolder: "Select step to start",
    });
    if (!selected)
        return;
    stateMachine.startStep(selected.stepId);
    vscode.window.showInformationMessage(`Started: ${selected.description}`);
    await updateInstructions();
    updateStatusBar();
}
async function cmdValidateStep() {
    log("Command: Validate Step");
    const currentStep = stateMachine.getCurrentStep();
    if (!currentStep) {
        vscode.window.showWarningMessage("No step in progress to validate.");
        return;
    }
    const validationResult = await vscode.window.showQuickPick([
        { label: "✅ Passed", value: "passed" },
        { label: "❌ Failed", value: "failed" },
        { label: "⏭️ Skipped", value: "skipped" },
    ], { placeHolder: `Validation result for: ${currentStep.title}` });
    if (!validationResult)
        return;
    // Store validation result on step (will be used when completing)
    currentStep.validationResult = validationResult.value;
    if (validationResult.value === "passed") {
        vscode.window.showInformationMessage(`Validation passed: ${currentStep.title}`);
    }
    else {
        vscode.window.showWarningMessage(`Validation ${validationResult.value}: ${currentStep.title}`);
    }
    await updateInstructions();
    updateStatusBar();
}
async function cmdCompleteStep() {
    log("Command: Complete Step");
    const currentStep = stateMachine.getCurrentStep();
    if (!currentStep) {
        vscode.window.showWarningMessage("No step in progress.");
        return;
    }
    if (!currentStep.validationResult) {
        const validate = await vscode.window.showWarningMessage("Step must be validated before completing. Validate now?", "Yes", "No");
        if (validate === "Yes") {
            await cmdValidateStep();
            return;
        }
        return;
    }
    stateMachine.completeStep(currentStep.id, currentStep.validationResult);
    const state = stateMachine.getState();
    if (state.stepsSinceDriftCheck >= 3) {
        vscode.window.showWarningMessage(`${state.stepsSinceDriftCheck} steps since drift check. Consider running drift check.`);
    }
    if (state.stepsSinceMemoryCheck >= 5) {
        vscode.window.showWarningMessage(`${state.stepsSinceMemoryCheck} steps since memory check. Consider running memory check.`);
    }
    vscode.window.showInformationMessage(`Completed: ${currentStep.title}`);
    await updateInstructions();
    updateStatusBar();
}
async function cmdDriftCheck() {
    log("Command: Drift Check");
    const result = stateMachine.runDriftCheck();
    outputChannel.appendLine("\n=== DRIFT CHECK RESULTS ===");
    for (const issue of result.issues) {
        outputChannel.appendLine(`⚠️ ${issue}`);
    }
    outputChannel.show();
    if (result.driftDetected) {
        vscode.window.showWarningMessage(`Drift check found ${result.issues.length} potential issues.`);
    }
    else {
        vscode.window.showInformationMessage("No drift detected. Continue!");
    }
    await updateInstructions();
    updateStatusBar();
}
async function cmdMemoryCheck() {
    log("Command: Memory Check");
    const result = stateMachine.runMemoryCheck();
    outputChannel.appendLine("\n=== MEMORY CHECK REMINDER ===");
    for (const action of result.actions) {
        outputChannel.appendLine(`📝 ${action}`);
    }
    outputChannel.show();
    const hasLearning = await vscode.window.showQuickPick(["Yes", "No"], {
        placeHolder: "Did you learn any new patterns this session?",
    });
    if (hasLearning === "Yes") {
        const pattern = await vscode.window.showInputBox({
            prompt: "What pattern did you learn?",
        });
        if (pattern) {
            log(`Learning recorded: ${pattern}`);
        }
    }
    vscode.window.showInformationMessage("Memory check completed.");
    await updateInstructions();
    updateStatusBar();
}
async function cmdCompleteTask() {
    log("Command: Complete Task");
    const state = stateMachine.getState();
    const incompleteSteps = state.steps.filter((s) => s.status !== "completed");
    if (incompleteSteps.length > 0) {
        const proceed = await vscode.window.showWarningMessage(`${incompleteSteps.length} steps are not completed. Complete anyway?`, "Yes", "No");
        if (proceed !== "Yes")
            return;
    }
    const checklistItems = [
        "All steps completed and validated",
        "Original success condition met",
        "Documentation updated",
        "Learnings recorded",
        "session.md updated",
    ];
    let checked = 0;
    for (const item of checklistItems) {
        const result = await vscode.window.showQuickPick(["✅ Done", "⬜ Skipped"], {
            placeHolder: item,
        });
        if (result === "✅ Done")
            checked++;
    }
    stateMachine.complete(`Completed with ${checked}/${checklistItems.length} checklist items`);
    vscode.window.showInformationMessage(`Task completed! ${checked}/${checklistItems.length} checklist items done.`);
    await updateInstructions();
    updateStatusBar();
}
async function cmdShowStatus() {
    log("Command: Show Status");
    const state = stateMachine.getState();
    const panel = vscode.window.createWebviewPanel("astraWorkflowStatus", "Astra Workflow Status", vscode.ViewColumn.Beside, {});
    panel.webview.html = generateStatusHTML(state);
}
async function cmdReportError() {
    log("Command: Report Error");
    const description = await vscode.window.showInputBox({
        prompt: "What error occurred?",
        placeHolder: "Describe the error...",
    });
    if (!description)
        return;
    const rootCause = await vscode.window.showInputBox({
        prompt: "What was the root cause?",
        placeHolder: "e.g., Missed edge case",
    });
    stateMachine.enterErrorRecovery(description);
    vscode.window.showInformationMessage("Error recorded. Now in recovery mode.");
    await updateInstructions();
    updateStatusBar();
}
async function cmdResetWorkflow() {
    log("Command: Reset Workflow");
    const confirm = await vscode.window.showWarningMessage("This will reset all workflow state. Are you sure?", "Yes, reset", "Cancel");
    if (confirm !== "Yes, reset")
        return;
    stateMachine.reset("User requested reset");
    metricsMonitor = createMetricsMonitor();
    vscode.window.showInformationMessage("Workflow reset.");
    await updateInstructions();
    updateStatusBar();
}
async function cmdShowDashboard() {
    log("Command: Show Dashboard");
    const state = stateMachine.getState();
    const metrics = state.metrics;
    outputChannel.appendLine("\n=== ASTRA WORKFLOW DASHBOARD ===");
    outputChannel.appendLine(`Phase: ${state.phase}`);
    outputChannel.appendLine(`Steps: ${state.steps.filter((s) => s.status === "completed").length}/${state.steps.length}`);
    outputChannel.appendLine("\n--- Cognitive Metrics ---");
    outputChannel.appendLine(`Identity checks: ${metrics.identityChecks}`);
    outputChannel.appendLine(`Drift detections: ${metrics.driftDetections}`);
    outputChannel.appendLine(`Memory checks: ${metrics.memoryChecks}`);
    outputChannel.appendLine(`Steps executed: ${metrics.stepsExecuted}`);
    outputChannel.appendLine(`Valid transitions: ${metrics.validTransitions}`);
    outputChannel.appendLine(`Invalid transitions: ${metrics.invalidTransitions}`);
    outputChannel.appendLine(`Steps since drift check: ${state.stepsSinceDriftCheck}`);
    outputChannel.appendLine(`Steps since memory check: ${state.stepsSinceMemoryCheck}`);
    outputChannel.show();
}
// =============================================================================
// HELPER FUNCTIONS
// =============================================================================
function log(message) {
    const timestamp = new Date().toISOString();
    outputChannel.appendLine(`[${timestamp}] ${message}`);
}
function createMetricsMonitor() {
    // Use default thresholds from types.ts
    return new metricsMonitor_js_1.CognitiveMetricsMonitor();
}
function updateStatusBar() {
    const state = stateMachine.getState();
    const phaseEmoji = {
        [types_js_1.WorkflowPhase.IDLE]: "⏸️",
        [types_js_1.WorkflowPhase.VALUE_GATE]: "🚪",
        [types_js_1.WorkflowPhase.GOAL_DEFINITION]: "🎯",
        [types_js_1.WorkflowPhase.CONTEXT_COLLECTION]: "📚",
        [types_js_1.WorkflowPhase.ENVIRONMENT_PRIMING]: "🔧",
        [types_js_1.WorkflowPhase.PLANNING]: "📝",
        [types_js_1.WorkflowPhase.EXECUTING]: "⚡",
        [types_js_1.WorkflowPhase.VALIDATING]: "✅",
        [types_js_1.WorkflowPhase.MEMORY_CHECK]: "🧠",
        [types_js_1.WorkflowPhase.DRIFT_CHECK]: "🎯",
        [types_js_1.WorkflowPhase.COMPLETING]: "🏁",
        [types_js_1.WorkflowPhase.BLOCKED]: "🚫",
        [types_js_1.WorkflowPhase.ERROR_RECOVERY]: "⚠️",
    };
    const emoji = phaseEmoji[state.phase] || "❓";
    const completedSteps = state.steps.filter((s) => s.status === "completed").length;
    const totalSteps = state.steps.length;
    if (totalSteps > 0) {
        statusBarItem.text = `${emoji} Astra: ${state.phase} (${completedSteps}/${totalSteps})`;
    }
    else {
        statusBarItem.text = `${emoji} Astra: ${state.phase}`;
    }
    statusBarItem.tooltip = "Click to show workflow status";
    statusBarItem.show();
}
async function updateInstructions() {
    const workspaceFolder = vscode.workspace.workspaceFolders?.[0];
    if (!workspaceFolder)
        return;
    try {
        await instructionInjector_js_1.InstructionInjector.injectWorkflowSection(workspaceFolder, stateMachine, metricsMonitor);
    }
    catch (error) {
        log(`Error updating instructions: ${error}`);
    }
}
function startAutoSave(context) {
    autoSaveTimer = setInterval(async () => {
        await persistState(context);
    }, 60000);
}
async function persistState(context) {
    const state = stateMachine.getState();
    await context.workspaceState.update("astra-workflow-state", state);
}
async function loadPersistedState(context) {
    const persistedState = context.workspaceState.get("astra-workflow-state");
    if (persistedState) {
        try {
            stateMachine = stateMachine_js_1.WorkflowStateMachine.fromJSON(JSON.stringify(persistedState), SESSION_ID);
            log("Loaded persisted workflow state");
        }
        catch (error) {
            log(`Error loading persisted state: ${error}`);
        }
    }
}
function generateStatusHTML(state) {
    return `
<!DOCTYPE html>
<html>
<head>
  <style>
    body {
      font-family: var(--vscode-font-family);
      padding: 20px;
      color: var(--vscode-foreground);
      background-color: var(--vscode-editor-background);
    }
    .section {
      margin-bottom: 20px;
      padding: 15px;
      border: 1px solid var(--vscode-panel-border);
      border-radius: 4px;
    }
    .section h2 {
      margin-top: 0;
      color: var(--vscode-textLink-foreground);
    }
    .metric {
      display: flex;
      justify-content: space-between;
      padding: 5px 0;
    }
    .step {
      padding: 5px 0;
    }
    .step.completed { color: green; }
    .step.in-progress { color: orange; }
    .step.not-started { color: gray; }
  </style>
</head>
<body>
  <h1>🌟 Astra Workflow Status</h1>
  
  <div class="section">
    <h2>Current Phase</h2>
    <p style="font-size: 1.5em;">${state.phase}</p>
    ${state.goal ? `<p><strong>Goal:</strong> ${state.goal.statement}</p>` : ""}
  </div>
  
  <div class="section">
    <h2>Steps (${state.steps.filter((s) => s.status === "completed").length}/${state.steps.length})</h2>
    ${state.steps
        .map((s) => `
      <div class="step ${s.status}">
        ${s.status === "completed" ? "✅" : s.status === "in-progress" ? "🔄" : "⬜"}
        <strong>${s.id}:</strong> ${s.title}
      </div>
    `)
        .join("")}
  </div>
  
  <div class="section">
    <h2>Counters</h2>
    <div class="metric">
      <span>Steps since drift check:</span>
      <span>${state.stepsSinceDriftCheck}</span>
    </div>
    <div class="metric">
      <span>Steps since memory check:</span>
      <span>${state.stepsSinceMemoryCheck}</span>
    </div>
  </div>
</body>
</html>
  `;
}
//# sourceMappingURL=extension.js.map