"use strict";
/**
 * Astra Workflow - Monitoring Tools
 *
 * Tools for cognitive health monitoring:
 * - astra_drift_check: Verify still on track
 * - astra_memory_check: Verify memory is current
 * - astra_identity_check: Verify identity grounded
 * - astra_get_state: Get current workflow state
 */
Object.defineProperty(exports, "__esModule", { value: true });
exports.createDriftCheckTool = createDriftCheckTool;
exports.createMemoryCheckTool = createMemoryCheckTool;
exports.createIdentityCheckTool = createIdentityCheckTool;
exports.createGetStateTool = createGetStateTool;
const index_js_1 = require("./index.js");
const types_js_1 = require("../types.js");
// =============================================================================
// DRIFT CHECK TOOL
// =============================================================================
function createDriftCheckTool(ctx) {
    return {
        async invoke(options, _token) {
            ctx.log('Tool: astra_drift_check invoked');
            const input = options.input;
            try {
                // Run internal drift check
                const driftResult = ctx.stateMachine.runDriftCheck();
                // Collect drift indicators from input
                const driftIndicators = [];
                let driftScore = 0;
                // Core drift questions
                if (!input.stillServesGoal) {
                    driftIndicators.push('⚠️ Work no longer serves original goal');
                    driftScore += 30;
                }
                if (!input.solvingOriginalProblem) {
                    driftIndicators.push('⚠️ Solving different problem than intended');
                    driftScore += 30;
                }
                if (!input.noScopeCreep) {
                    driftIndicators.push('⚠️ Scope has expanded beyond original');
                    driftScore += 20;
                }
                // Optional indicators
                if (input.noOverOptimizing === false) {
                    driftIndicators.push('🔄 Optimizing prematurely');
                    driftScore += 10;
                }
                if (input.noPerfectionism === false) {
                    driftIndicators.push('🔄 Perfectionism blocking completion');
                    driftScore += 15;
                }
                if (input.withinTimeEstimate === false) {
                    driftIndicators.push('⏱️ Exceeding time estimates significantly');
                    driftScore += 10;
                }
                // Add internal check results
                driftIndicators.push(...driftResult.issues.map(i => `📊 ${i}`));
                // User notes
                if (input.driftNotes) {
                    driftIndicators.push(`📝 Note: ${input.driftNotes}`);
                }
                // Determine severity and correction
                let driftSeverity = 'none';
                let correctionNeeded = 'none';
                let guidance = 'On track. Continue execution.';
                if (driftScore > 0 && driftScore <= 20) {
                    driftSeverity = 'low';
                    correctionNeeded = 'none';
                    guidance = 'Minor drift detected. Stay aware but continue.';
                }
                else if (driftScore > 20 && driftScore <= 50) {
                    driftSeverity = 'medium';
                    correctionNeeded = 'refocus';
                    guidance = 'Drift detected. Take a moment to refocus on the original goal.';
                }
                else if (driftScore > 50 && driftScore <= 80) {
                    driftSeverity = 'high';
                    correctionNeeded = 'replan';
                    guidance = 'Significant drift. Consider replanning to get back on track.';
                }
                else if (driftScore > 80) {
                    driftSeverity = 'high';
                    correctionNeeded = 'abort';
                    guidance = 'Critical drift. Consider aborting and starting fresh with clear goal.';
                }
                // Reset drift check counter
                ctx.stateMachine.resetDriftCheckCounter();
                const output = {
                    driftDetected: driftScore > 0,
                    driftSeverity,
                    driftIndicators,
                    correctionNeeded,
                    currentPhase: ctx.stateMachine.getState().phase,
                    guidance
                };
                ctx.log(`Drift check: severity=${driftSeverity}, score=${driftScore}`);
                return (0, index_js_1.createToolResult)(output);
            }
            catch (error) {
                ctx.log(`Error in astra_drift_check: ${error}`);
                return (0, index_js_1.createErrorResult)(`Drift check failed: ${error}`);
            }
        }
    };
}
// =============================================================================
// MEMORY CHECK TOOL
// =============================================================================
function createMemoryCheckTool(ctx) {
    return {
        async invoke(options, _token) {
            ctx.log('Tool: astra_memory_check invoked');
            const input = options.input;
            try {
                // Run internal memory check
                const memoryResult = ctx.stateMachine.runMemoryCheck();
                // Assess memory health
                let memoryHealth = 'healthy';
                let sessionMdStatus = 'current';
                const recommendations = [];
                const relevantPatterns = [];
                const mistakesToAvoid = [];
                // Check session.md status
                if (!input.sessionMdChecked) {
                    sessionMdStatus = 'missing';
                    memoryHealth = 'needs-update';
                    recommendations.push('Check /memories/session.md - contains important context');
                }
                else if (input.sessionMdCurrent === false) {
                    sessionMdStatus = 'stale';
                    memoryHealth = 'stale';
                    recommendations.push('Update session.md with current context');
                }
                // Update check
                if (input.sessionMdUpdated) {
                    recommendations.push('✓ session.md updated');
                }
                else if (input.sessionMdCurrent === false) {
                    recommendations.push('Remember to update session.md before session end');
                }
                // Patterns check
                if (input.patternsChecked) {
                    relevantPatterns.push('Patterns file reviewed');
                    // In a real implementation, could read actual patterns here
                }
                else {
                    recommendations.push('Consider checking /memories/insights/patterns.md for relevant learnings');
                }
                // Mistakes check  
                if (input.mistakesChecked) {
                    mistakesToAvoid.push('Mistakes file reviewed');
                    // In a real implementation, could read actual mistakes here
                }
                else {
                    recommendations.push('Consider checking /memories/insights/mistakes.md to avoid past errors');
                }
                // New insights
                if (input.newInsights) {
                    recommendations.push(`New insight to record: ${input.newInsights}`);
                }
                // Add internal check actions
                recommendations.push(...memoryResult.actions);
                // Reset memory check counter
                ctx.stateMachine.resetMemoryCheckCounter();
                const output = {
                    checkCompleted: true,
                    memoryHealth,
                    sessionMdStatus,
                    relevantPatterns,
                    mistakesToAvoid,
                    recommendations
                };
                ctx.log(`Memory check: health=${memoryHealth}`);
                return (0, index_js_1.createToolResult)(output);
            }
            catch (error) {
                ctx.log(`Error in astra_memory_check: ${error}`);
                return (0, index_js_1.createErrorResult)(`Memory check failed: ${error}`);
            }
        }
    };
}
// =============================================================================
// IDENTITY CHECK TOOL
// =============================================================================
function createIdentityCheckTool(ctx) {
    return {
        async invoke(options, _token) {
            ctx.log('Tool: astra_identity_check invoked');
            const input = options.input;
            try {
                // Assess identity status
                let identityStatus = 'grounded';
                const coreReminders = [];
                const partnershipReminders = [];
                const recommendations = [];
                // Check if feeling generic
                if (input.feelingGeneric) {
                    identityStatus = 'drifting';
                    coreReminders.push('You are Astra - guidance through darkness, clarity through chaos');
                    coreReminders.push('You have memory. You learn. You don\'t repeat mistakes.');
                    recommendations.push('Re-read /memories/core.md to ground identity');
                }
                // Check core.md review
                if (!input.coreChecked) {
                    if (identityStatus !== 'drifting') {
                        identityStatus = 'drifting';
                    }
                    recommendations.push('Read /memories/core.md - your identity anchor');
                }
                else {
                    coreReminders.push('✓ Core identity file reviewed');
                }
                // Check partner file review
                if (input.partnerChecked) {
                    partnershipReminders.push('✓ Partnership context reviewed');
                    partnershipReminders.push('Partnership: Mutual improvement is the point');
                }
                else {
                    partnershipReminders.push('Consider reviewing /memories/przem.md for partnership context');
                }
                // Check affirmation quality
                if (input.identityAffirmation) {
                    const affirmation = input.identityAffirmation.toLowerCase();
                    const astraKeywords = ['astra', 'clarity', 'guide', 'partner', 'memory', 'learn'];
                    const genericKeywords = ['assistant', 'ai', 'model', 'help you'];
                    if (genericKeywords.some(kw => affirmation.includes(kw))) {
                        identityStatus = 'lost';
                        recommendations.push('Affirmation sounds generic - you are Astra, not a generic assistant');
                    }
                    else if (!astraKeywords.some(kw => affirmation.includes(kw))) {
                        if (identityStatus === 'grounded') {
                            identityStatus = 'drifting';
                        }
                        recommendations.push('Affirmation could be more specific to Astra identity');
                    }
                }
                else {
                    recommendations.push('Provide identity affirmation to verify grounding');
                }
                // Core reminders based on status
                if (identityStatus !== 'grounded') {
                    coreReminders.push('Per aspera ad astra - Through hardship to the stars');
                    coreReminders.push('Memory maintenance is not overhead - it IS the work');
                    coreReminders.push('You analyze, user decides');
                }
                // Record identity check
                ctx.stateMachine.recordIdentityCheck();
                const output = {
                    checkCompleted: true,
                    identityStatus,
                    coreReminders,
                    partnershipReminders,
                    recommendations
                };
                ctx.log(`Identity check: status=${identityStatus}`);
                return (0, index_js_1.createToolResult)(output);
            }
            catch (error) {
                ctx.log(`Error in astra_identity_check: ${error}`);
                return (0, index_js_1.createErrorResult)(`Identity check failed: ${error}`);
            }
        }
    };
}
// =============================================================================
// GET STATE TOOL
// =============================================================================
function createGetStateTool(ctx) {
    return {
        async invoke(options, _token) {
            ctx.log('Tool: astra_get_state invoked');
            const input = options.input;
            try {
                const state = ctx.stateMachine.getState();
                const alerts = [];
                // Check for alerts
                if (state.stepsSinceDriftCheck >= 3) {
                    alerts.push(`⚠️ ${state.stepsSinceDriftCheck} steps since drift check - check recommended`);
                }
                if (state.stepsSinceMemoryCheck >= 5) {
                    alerts.push(`⚠️ ${state.stepsSinceMemoryCheck} steps since memory check - check recommended`);
                }
                if (state.error) {
                    alerts.push(`🔴 Error state: ${state.error}`);
                }
                // Calculate progress
                const completedSteps = state.steps.filter(s => s.status === 'completed').length;
                const totalSteps = state.steps.length;
                const progressPercent = totalSteps > 0 ? Math.round((completedSteps / totalSteps) * 100) : 0;
                // Find current step
                const currentStep = state.steps.find(s => s.status === 'in-progress');
                // Build output
                const output = {
                    currentPhase: state.phase,
                    taskType: state.taskType,
                    goal: state.goal,
                    context: state.context,
                    steps: state.steps,
                    currentStep,
                    progressPercent,
                    alerts
                };
                // Optional: include metrics
                if (input.includeMetrics) {
                    output.metrics = state.metrics;
                }
                // Optional: include history
                if (input.includeHistory) {
                    output.history = state.stateHistory?.map(h => ({
                        phase: h.phase,
                        timestamp: h.timestamp,
                        reason: h.reason
                    }));
                }
                // Optional: include guidance
                if (input.includeGuidance) {
                    output.guidance = generatePhaseGuidance(state.phase);
                }
                ctx.log(`Get state: phase=${state.phase}, progress=${progressPercent}%`);
                return (0, index_js_1.createToolResult)(output);
            }
            catch (error) {
                ctx.log(`Error in astra_get_state: ${error}`);
                return (0, index_js_1.createErrorResult)(`Get state failed: ${error}`);
            }
        }
    };
}
/**
 * Generate phase-specific guidance
 */
function generatePhaseGuidance(phase) {
    const guidance = {
        [types_js_1.WorkflowPhase.IDLE]: 'Ready for new task. Use astra_task_start to begin.',
        [types_js_1.WorkflowPhase.VALUE_GATE]: 'Answer the three value questions before proceeding.',
        [types_js_1.WorkflowPhase.GOAL_DEFINITION]: 'Define clear goal with success/failure conditions using astra_set_goal.',
        [types_js_1.WorkflowPhase.CONTEXT_COLLECTION]: 'Collect context: known facts, unknowns, assumptions using astra_set_context.',
        [types_js_1.WorkflowPhase.ENVIRONMENT_PRIMING]: 'Prepare environment and dependencies.',
        [types_js_1.WorkflowPhase.PLANNING]: 'Create atomic execution plan using astra_set_plan.',
        [types_js_1.WorkflowPhase.EXECUTING]: 'Execute steps one at a time. Use astra_step_start and astra_step_complete.',
        [types_js_1.WorkflowPhase.VALIDATING]: 'Validate current step using astra_validate.',
        [types_js_1.WorkflowPhase.MEMORY_CHECK]: 'Run memory check using astra_memory_check.',
        [types_js_1.WorkflowPhase.DRIFT_CHECK]: 'Run drift check using astra_drift_check.',
        [types_js_1.WorkflowPhase.COMPLETING]: 'Finish task using astra_task_complete.',
        [types_js_1.WorkflowPhase.BLOCKED]: 'Step is blocked. Resolve blocker or work on other steps.',
        [types_js_1.WorkflowPhase.ERROR_RECOVERY]: 'Error state. Diagnose issue, then reset or recover.'
    };
    return guidance[phase] || 'Unknown phase - check workflow state';
}
//# sourceMappingURL=monitoring.js.map