"use strict";
/**
 * Astra Workflow - Execution Tools
 *
 * Tools for executing planned steps:
 * - astra_step_start: Begin executing a step
 * - astra_step_complete: Mark step as done
 * - astra_step_block: Mark step as blocked
 * - astra_validate: Validate step completion
 */
Object.defineProperty(exports, "__esModule", { value: true });
exports.createStepStartTool = createStepStartTool;
exports.createStepCompleteTool = createStepCompleteTool;
exports.createStepBlockTool = createStepBlockTool;
exports.createValidateTool = createValidateTool;
const index_js_1 = require("./index.js");
const types_js_1 = require("../types.js");
// =============================================================================
// STEP START TOOL
// =============================================================================
function createStepStartTool(ctx) {
    return {
        async invoke(options, _token) {
            ctx.log('Tool: astra_step_start invoked');
            const input = options.input;
            try {
                const state = ctx.stateMachine.getState();
                // Validate state - should be in PLANNING or EXECUTING phase
                const validPhases = [types_js_1.WorkflowPhase.PLANNING, types_js_1.WorkflowPhase.EXECUTING, types_js_1.WorkflowPhase.VALIDATING];
                if (!validPhases.includes(state.phase)) {
                    return (0, index_js_1.createErrorResult)(`Cannot start step in phase: ${state.phase}. Create a plan first using astra_set_plan.`);
                }
                // Find the step
                const step = state.steps.find(s => s.id === input.stepId);
                if (!step) {
                    const validIds = state.steps.map(s => s.id).join(', ');
                    return (0, index_js_1.createErrorResult)(`Step not found: ${input.stepId}. Valid IDs: ${validIds}`);
                }
                // Check if already in progress
                const currentInProgress = state.steps.find(s => s.status === 'in-progress');
                if (currentInProgress && currentInProgress.id !== input.stepId) {
                    return (0, index_js_1.createErrorResult)(`Another step is in progress: ${currentInProgress.id}. Complete or block current step before starting new one.`);
                }
                // Check if step is already completed
                if (step.status === 'completed') {
                    return (0, index_js_1.createErrorResult)(`Step ${input.stepId} is already completed. Start a different step.`);
                }
                // Start the step
                ctx.stateMachine.startStep(input.stepId);
                const updatedState = ctx.stateMachine.getState();
                const updatedStep = updatedState.steps.find(s => s.id === input.stepId);
                const output = {
                    stepStarted: true,
                    step: updatedStep,
                    currentPhase: updatedState.phase,
                    guidance: `Working on: ${updatedStep.title}\n${updatedStep.description || ''}`,
                    validationReminder: updatedStep.validationMethod
                        ? `Validation: ${updatedStep.validationMethod}`
                        : 'Remember to validate before marking complete'
                };
                ctx.log(`Step started: ${input.stepId}`);
                return (0, index_js_1.createToolResult)(output);
            }
            catch (error) {
                ctx.log(`Error in astra_step_start: ${error}`);
                return (0, index_js_1.createErrorResult)(`Step start failed: ${error}`);
            }
        }
    };
}
// =============================================================================
// STEP COMPLETE TOOL
// =============================================================================
function createStepCompleteTool(ctx) {
    return {
        async invoke(options, _token) {
            ctx.log('Tool: astra_step_complete invoked');
            const input = options.input;
            try {
                const state = ctx.stateMachine.getState();
                // Find the step
                const step = state.steps.find(s => s.id === input.stepId);
                if (!step) {
                    return (0, index_js_1.createErrorResult)(`Step not found: ${input.stepId}`);
                }
                // Check if step is in progress
                if (step.status !== 'in-progress') {
                    return (0, index_js_1.createErrorResult)(`Step ${input.stepId} is not in progress (status: ${step.status}). Start the step first with astra_step_start.`);
                }
                // Validation check
                if (!input.validated) {
                    return (0, index_js_1.createErrorResult)('Step must be validated before completion. Use astra_validate first, then complete with validated: true.');
                }
                // Complete the step
                ctx.stateMachine.completeStep(input.stepId, 'passed');
                const updatedState = ctx.stateMachine.getState();
                const completedSteps = updatedState.steps.filter(s => s.status === 'completed').length;
                const totalSteps = updatedState.steps.length;
                const remainingSteps = totalSteps - completedSteps;
                const progressPercent = Math.round((completedSteps / totalSteps) * 100);
                // Check for drift/memory check due
                const driftCheckDue = updatedState.stepsSinceDriftCheck >= 3;
                const memoryCheckDue = updatedState.stepsSinceMemoryCheck >= 5;
                // Find next step
                const nextStep = updatedState.steps.find(s => s.status === 'not-started');
                // Estimate duration comparison
                let durationVsEstimate = 'on-track';
                if (step.estimatedMinutes && step.startedAt) {
                    const actualMinutes = (Date.now() - new Date(step.startedAt).getTime()) / 60000;
                    if (actualMinutes < step.estimatedMinutes * 0.5) {
                        durationVsEstimate = 'faster';
                    }
                    else if (actualMinutes > step.estimatedMinutes * 1.5) {
                        durationVsEstimate = 'slower';
                    }
                }
                const output = {
                    stepCompleted: true,
                    durationVsEstimate,
                    stepsRemaining: remainingSteps,
                    progressPercent,
                    currentPhase: updatedState.phase,
                    driftCheckDue,
                    memoryCheckDue,
                    nextStep
                };
                ctx.log(`Step completed: ${input.stepId} (${progressPercent}% done)`);
                return (0, index_js_1.createToolResult)(output);
            }
            catch (error) {
                ctx.log(`Error in astra_step_complete: ${error}`);
                return (0, index_js_1.createErrorResult)(`Step complete failed: ${error}`);
            }
        }
    };
}
// =============================================================================
// STEP BLOCK TOOL
// =============================================================================
function createStepBlockTool(ctx) {
    return {
        async invoke(options, _token) {
            ctx.log('Tool: astra_step_block invoked');
            const input = options.input;
            try {
                const state = ctx.stateMachine.getState();
                // Find the step
                const step = state.steps.find(s => s.id === input.stepId);
                if (!step) {
                    return (0, index_js_1.createErrorResult)(`Step not found: ${input.stepId}`);
                }
                // Mark step as blocked
                ctx.stateMachine.blockStep(input.stepId, input.blockReason);
                // Generate resolution suggestions
                const suggestedResolutions = [];
                // Pattern matching on block reason
                const blockLower = input.blockReason.toLowerCase();
                if (blockLower.includes('wait') || blockLower.includes('depend')) {
                    suggestedResolutions.push('Check if dependency can be parallelized');
                    suggestedResolutions.push('Consider working on independent steps first');
                }
                if (blockLower.includes('unclear') || blockLower.includes('need info')) {
                    suggestedResolutions.push('Ask user for clarification');
                    suggestedResolutions.push('Check memory/docs for existing information');
                }
                if (blockLower.includes('error') || blockLower.includes('bug')) {
                    suggestedResolutions.push('Debug the error systematically');
                    suggestedResolutions.push('Check if it\'s a known issue in mistakes.md');
                }
                if (input.planB) {
                    suggestedResolutions.push(`Plan B: ${input.planB}`);
                }
                const output = {
                    stepBlocked: true,
                    blockerRecorded: true,
                    currentPhase: ctx.stateMachine.getState().phase,
                    suggestedResolutions: suggestedResolutions.length > 0
                        ? suggestedResolutions
                        : ['Document the blocker', 'Consider asking for help', 'Move to other steps if possible']
                };
                ctx.log(`Step blocked: ${input.stepId} - ${input.blockReason}`);
                return (0, index_js_1.createToolResult)(output);
            }
            catch (error) {
                ctx.log(`Error in astra_step_block: ${error}`);
                return (0, index_js_1.createErrorResult)(`Step block failed: ${error}`);
            }
        }
    };
}
// =============================================================================
// VALIDATE TOOL
// =============================================================================
function createValidateTool(ctx) {
    return {
        async invoke(options, _token) {
            ctx.log('Tool: astra_validate invoked');
            const input = options.input;
            try {
                const state = ctx.stateMachine.getState();
                const recommendations = [];
                // Find the step
                const step = state.steps.find(s => s.id === input.stepId);
                if (!step) {
                    return (0, index_js_1.createErrorResult)(`Step not found: ${input.stepId}`);
                }
                // Assess validation quality
                let validationQuality = 'adequate';
                // Check method rigor
                const rigorousMethodKeywords = ['test', 'unit', 'integration', 'automated', 'assertion'];
                const weakMethodKeywords = ['manual', 'looks', 'seems', 'think', 'believe'];
                if (rigorousMethodKeywords.some(kw => input.method.toLowerCase().includes(kw))) {
                    validationQuality = 'rigorous';
                }
                else if (weakMethodKeywords.some(kw => input.method.toLowerCase().includes(kw))) {
                    validationQuality = 'weak';
                    recommendations.push('Consider more rigorous validation (tests, assertions)');
                }
                // Check for independent validation
                if (!input.independentCheck) {
                    recommendations.push('Validation may not be independent - same mind created and validated');
                }
                // Check for evidence
                if (!input.evidence || input.evidence.length < 10) {
                    if (validationQuality !== 'weak') {
                        validationQuality = 'adequate';
                    }
                    recommendations.push('Provide specific evidence to support validation result');
                }
                // Determine if can proceed
                const canProceed = input.result === 'passed' ||
                    (input.result === 'partial' && validationQuality !== 'weak');
                if (input.result === 'failed') {
                    recommendations.push('Fix issues before proceeding');
                    recommendations.push('Consider root cause analysis');
                }
                if (input.result === 'partial') {
                    recommendations.push('Document what passed and what remains');
                }
                // Store validation result on step
                // Map 'partial' to 'passed' with a note, since WorkflowStep only supports passed/failed/skipped
                if (step) {
                    step.validationResult = input.result === 'partial' ? 'passed' : input.result;
                    step.validationMethod = input.method;
                }
                const output = {
                    validationRecorded: true,
                    validationQuality,
                    canProceed,
                    currentPhase: ctx.stateMachine.getState().phase,
                    recommendations
                };
                ctx.log(`Validation: ${input.stepId} = ${input.result} (${validationQuality})`);
                return (0, index_js_1.createToolResult)(output);
            }
            catch (error) {
                ctx.log(`Error in astra_validate: ${error}`);
                return (0, index_js_1.createErrorResult)(`Validate failed: ${error}`);
            }
        }
    };
}
//# sourceMappingURL=execution.js.map