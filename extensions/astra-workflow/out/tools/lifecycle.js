"use strict";
/**
 * Astra Workflow - Lifecycle Tools
 *
 * Tools for managing workflow session and task lifecycle:
 * - astra_session_start: Initialize new session
 * - astra_session_end: Cleanly close session
 * - astra_task_start: Begin a new task
 * - astra_task_complete: Complete current task
 */
Object.defineProperty(exports, "__esModule", { value: true });
exports.createSessionStartTool = createSessionStartTool;
exports.createSessionEndTool = createSessionEndTool;
exports.createTaskStartTool = createTaskStartTool;
exports.createTaskCompleteTool = createTaskCompleteTool;
const index_js_1 = require("./index.js");
const types_js_1 = require("../types.js");
// =============================================================================
// SESSION START TOOL
// =============================================================================
function createSessionStartTool(ctx) {
    return {
        async invoke(options, _token) {
            ctx.log('Tool: astra_session_start invoked');
            const input = options.input;
            try {
                // Get current state
                const state = ctx.stateMachine.getState();
                const alerts = [];
                // Check if previous session exists
                const previousSessionFound = state.phase !== types_js_1.WorkflowPhase.IDLE;
                // Check memory status
                let memoryStatus = 'current';
                if (input.checkMemory === false) {
                    memoryStatus = 'missing';
                    alerts.push('Memory check skipped - consider verifying session.md');
                }
                // Determine recommendation
                let recommendation = 'start-fresh';
                if (previousSessionFound && input.resumePreviousTask !== false) {
                    recommendation = 'resume';
                    alerts.push(`Previous session found in phase: ${state.phase}`);
                }
                if (memoryStatus !== 'current') {
                    recommendation = 'check-memory-first';
                }
                const output = {
                    previousSessionFound,
                    previousPhase: previousSessionFound ? state.phase : undefined,
                    memoryStatus,
                    recommendation,
                    alerts
                };
                ctx.log(`Session start: found=${previousSessionFound}, recommendation=${recommendation}`);
                return (0, index_js_1.createToolResult)(output);
            }
            catch (error) {
                ctx.log(`Error in astra_session_start: ${error}`);
                return (0, index_js_1.createErrorResult)(`Session start failed: ${error}`);
            }
        }
    };
}
// =============================================================================
// SESSION END TOOL
// =============================================================================
function createSessionEndTool(ctx) {
    return {
        async invoke(options, _token) {
            ctx.log('Tool: astra_session_end invoked');
            const input = options.input;
            try {
                const state = ctx.stateMachine.getState();
                // Calculate session stats
                const completedSteps = state.steps.filter(s => s.status === 'completed').length;
                const sessionStartTime = state.stateHistory?.[0]?.timestamp || new Date();
                const sessionDurationMinutes = Math.round((Date.now() - new Date(sessionStartTime).getTime()) / 60000);
                // Count tasks (simplified - we track one task at a time)
                const tasksCompleted = input.taskStatus === 'completed' ? 1 : 0;
                // Build summary
                let summary = `Session ended with status: ${input.taskStatus}`;
                if (input.resumeNotes) {
                    summary += `. Resume notes: ${input.resumeNotes}`;
                }
                if (state.goal) {
                    summary = `Goal: ${state.goal.statement}. ${summary}`;
                }
                // Handle state persistence (would be done by persistence layer)
                const statePersisted = true;
                const handoffWritten = input.updateSessionMd ?? true;
                // Reset if completed, otherwise keep state for resume
                if (input.taskStatus === 'completed') {
                    ctx.stateMachine.reset('Session ended - task completed');
                }
                const output = {
                    summary,
                    sessionDurationMinutes,
                    tasksCompleted,
                    stepsCompleted: completedSteps,
                    statePersisted,
                    handoffWritten
                };
                ctx.log(`Session ended: status=${input.taskStatus}, duration=${sessionDurationMinutes}m`);
                return (0, index_js_1.createToolResult)(output);
            }
            catch (error) {
                ctx.log(`Error in astra_session_end: ${error}`);
                return (0, index_js_1.createErrorResult)(`Session end failed: ${error}`);
            }
        }
    };
}
// =============================================================================
// TASK START TOOL
// =============================================================================
function createTaskStartTool(ctx) {
    return {
        async invoke(options, _token) {
            ctx.log('Tool: astra_task_start invoked');
            const input = options.input;
            try {
                const state = ctx.stateMachine.getState();
                const warnings = [];
                // Check if already in task
                if (state.phase !== types_js_1.WorkflowPhase.IDLE) {
                    return (0, index_js_1.createErrorResult)(`Cannot start new task while in phase: ${state.phase}. Complete current task first.`);
                }
                // Validate value gate
                const valueGate = input.valueGate;
                let valueGatePassed = true;
                if (!valueGate.benefit || valueGate.benefit.length < 10) {
                    warnings.push('Benefit description is too short - be specific about the value');
                    valueGatePassed = false;
                }
                if (!valueGate.simplest) {
                    warnings.push('This might not be the simplest approach - consider alternatives');
                }
                if (!valueGate.consequence || valueGate.consequence.toLowerCase().includes('nothing')) {
                    warnings.push('If "nothing" happens without this task, reconsider whether it\'s worth doing');
                    valueGatePassed = false;
                }
                // Classify task type based on description
                const descLower = input.taskDescription.toLowerCase();
                let classifiedType = types_js_1.TaskType.STANDARD;
                if (descLower.includes('fix') || descLower.includes('bug')) {
                    classifiedType = types_js_1.TaskType.SIMPLE;
                }
                else if (descLower.includes('refactor') || descLower.includes('clean')) {
                    classifiedType = types_js_1.TaskType.COMPLEX;
                }
                else if (descLower.includes('explore') || descLower.includes('research') || descLower.includes('investigate')) {
                    classifiedType = types_js_1.TaskType.COMPLEX;
                }
                else if (descLower.includes('doc') || descLower.includes('document')) {
                    classifiedType = types_js_1.TaskType.SIMPLE;
                }
                else if (descLower.includes('quick') || descLower.includes('simple') || descLower.includes('trivial')) {
                    classifiedType = types_js_1.TaskType.TRIVIAL;
                }
                // Start task
                ctx.stateMachine.startTask(classifiedType);
                // Pass value gate if valid
                if (valueGatePassed) {
                    ctx.stateMachine.passValueGate(valueGate.benefit);
                }
                // Generate task ID
                const taskId = `task-${Date.now()}`;
                // Determine next action
                const nextAction = valueGatePassed
                    ? 'Define your goal with success/failure conditions using astra_set_goal'
                    : 'Address value gate warnings before proceeding';
                const output = {
                    taskId,
                    classifiedType,
                    valueGatePassed,
                    currentPhase: ctx.stateMachine.getState().phase,
                    nextAction,
                    warnings
                };
                ctx.log(`Task started: ${taskId}, type=${classifiedType}, valueGate=${valueGatePassed}`);
                return (0, index_js_1.createToolResult)(output);
            }
            catch (error) {
                ctx.log(`Error in astra_task_start: ${error}`);
                return (0, index_js_1.createErrorResult)(`Task start failed: ${error}`);
            }
        }
    };
}
// =============================================================================
// TASK COMPLETE TOOL
// =============================================================================
function createTaskCompleteTool(ctx) {
    return {
        async invoke(options, _token) {
            ctx.log('Tool: astra_task_complete invoked');
            const input = options.input;
            try {
                const state = ctx.stateMachine.getState();
                // Check if there's an active task
                if (state.phase === types_js_1.WorkflowPhase.IDLE) {
                    return (0, index_js_1.createErrorResult)('No active task to complete. Start a task first.');
                }
                // Calculate stats
                const stepsCompleted = state.steps.filter(s => s.status === 'completed').length;
                const stepsSkipped = state.steps.filter(s => s.status === 'skipped').length;
                // Calculate duration
                const startTime = state.stateHistory?.[0]?.timestamp || new Date();
                const durationMinutes = Math.round((Date.now() - new Date(startTime).getTime()) / 60000);
                // Record learnings and mistakes
                const learningsRecorded = !!(input.learnings && input.learnings.length > 0) ||
                    !!(input.patternsToRepeat && input.patternsToRepeat.length > 0);
                const mistakesRecorded = !!(input.mistakesToAvoid && input.mistakesToAvoid.length > 0);
                // Build summary
                let summary = state.goal?.statement || 'Task';
                if (input.successCriteriaMet) {
                    summary = `✓ ${summary} - Success criteria met`;
                }
                else {
                    summary = `✗ ${summary} - Success criteria NOT met`;
                }
                // Complete the workflow
                ctx.stateMachine.complete(summary);
                const output = {
                    summary,
                    durationMinutes,
                    stepsCompleted,
                    stepsSkipped,
                    learningsRecorded,
                    mistakesRecorded,
                    currentPhase: ctx.stateMachine.getState().phase
                };
                ctx.log(`Task completed: success=${input.successCriteriaMet}, duration=${durationMinutes}m`);
                return (0, index_js_1.createToolResult)(output);
            }
            catch (error) {
                ctx.log(`Error in astra_task_complete: ${error}`);
                return (0, index_js_1.createErrorResult)(`Task complete failed: ${error}`);
            }
        }
    };
}
//# sourceMappingURL=lifecycle.js.map