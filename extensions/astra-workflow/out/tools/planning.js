"use strict";
/**
 * Astra Workflow - Planning Tools
 *
 * Tools for defining goals, collecting context, and creating plans:
 * - astra_set_goal: Define task goal with success/failure conditions
 * - astra_set_context: Record known/unknown/assumptions
 * - astra_set_plan: Create execution plan with steps
 */
Object.defineProperty(exports, "__esModule", { value: true });
exports.createSetGoalTool = createSetGoalTool;
exports.createSetContextTool = createSetContextTool;
exports.createSetPlanTool = createSetPlanTool;
const index_js_1 = require("./index.js");
const types_js_1 = require("../types.js");
// =============================================================================
// SET GOAL TOOL
// =============================================================================
function createSetGoalTool(ctx) {
    return {
        async invoke(options, _token) {
            ctx.log('Tool: astra_set_goal invoked');
            const input = options.input;
            try {
                const state = ctx.stateMachine.getState();
                const warnings = [];
                // Validate state - should be in VALUE_GATE or GOAL_DEFINITION phase
                const validPhases = [types_js_1.WorkflowPhase.VALUE_GATE, types_js_1.WorkflowPhase.GOAL_DEFINITION, types_js_1.WorkflowPhase.IDLE];
                if (!validPhases.includes(state.phase)) {
                    return (0, index_js_1.createErrorResult)(`Cannot set goal in phase: ${state.phase}. Complete current phase before setting goal.`);
                }
                // Assess goal quality
                let goalQuality = 'clear';
                // Check for vague language
                const vagueTerms = ['maybe', 'possibly', 'kind of', 'sort of', 'probably', 'might'];
                if (vagueTerms.some(term => input.statement.toLowerCase().includes(term))) {
                    goalQuality = 'vague';
                    warnings.push('Goal contains vague language - be more specific');
                }
                // Check for overly broad scope
                const broadTerms = ['everything', 'all', 'entire', 'complete overhaul', 'refactor everything'];
                if (broadTerms.some(term => input.statement.toLowerCase().includes(term))) {
                    goalQuality = 'too-broad';
                    warnings.push('Goal scope may be too broad - consider breaking down');
                }
                // Check for missing success condition
                if (!input.successCondition || input.successCondition.length < 10) {
                    warnings.push('Success condition is too short - how will you know you succeeded?');
                }
                // Check for missing failure condition
                if (!input.failureCondition || input.failureCondition.length < 10) {
                    warnings.push('Failure condition is too short - how will you know you failed?');
                }
                // Set the goal in state machine
                ctx.stateMachine.setGoal({
                    statement: input.statement,
                    successCondition: input.successCondition,
                    failureCondition: input.failureCondition,
                    timeBudget: input.timeBudgetMinutes
                });
                const newState = ctx.stateMachine.getState();
                const output = {
                    goalRegistered: true,
                    goalQuality,
                    currentPhase: newState.phase,
                    nextAction: goalQuality === 'clear'
                        ? 'Goal set. Now collect context: what do you know, what do you not know, what are you assuming?'
                        : 'Refine your goal to be clearer before proceeding',
                    warnings
                };
                ctx.log(`Goal set: ${input.statement.substring(0, 50)}...`);
                return (0, index_js_1.createToolResult)(output);
            }
            catch (error) {
                ctx.log(`Error in astra_set_goal: ${error}`);
                return (0, index_js_1.createErrorResult)(`Set goal failed: ${error}`);
            }
        }
    };
}
// =============================================================================
// SET CONTEXT TOOL
// =============================================================================
function createSetContextTool(ctx) {
    return {
        async invoke(options, _token) {
            ctx.log('Tool: astra_set_context invoked');
            const input = options.input;
            try {
                const state = ctx.stateMachine.getState();
                // Validate state - should be after goal setting
                const validPhases = [types_js_1.WorkflowPhase.GOAL_DEFINITION, types_js_1.WorkflowPhase.CONTEXT_COLLECTION];
                if (!validPhases.includes(state.phase)) {
                    return (0, index_js_1.createErrorResult)(`Cannot set context in phase: ${state.phase}. Set goal first. Use astra_set_goal before collecting context.`);
                }
                // Assess context completeness
                let completeness = 'adequate';
                const criticalGaps = [];
                const riskyAssumptions = [];
                // Check known facts
                if (input.known.length < 2) {
                    completeness = 'sparse';
                    criticalGaps.push('Very few facts verified - do more research');
                }
                // Check unknown gaps
                if (input.unknown.length === 0) {
                    // No unknowns might be overconfidence
                    criticalGaps.push('No unknowns identified - are you sure you understand everything?');
                }
                else {
                    // Highlight critical unknowns
                    const criticalKeywords = ['how', 'why', 'performance', 'security', 'edge case'];
                    for (const unknown of input.unknown) {
                        if (criticalKeywords.some(kw => unknown.toLowerCase().includes(kw))) {
                            criticalGaps.push(unknown);
                        }
                    }
                }
                // Check assumptions
                if (input.assumptions.length > 0) {
                    // Flag risky assumptions
                    const riskyKeywords = ['should work', 'probably', 'assume', 'hope', 'trust'];
                    for (const assumption of input.assumptions) {
                        if (riskyKeywords.some(kw => assumption.toLowerCase().includes(kw))) {
                            riskyAssumptions.push(assumption);
                        }
                    }
                }
                // Check sources
                if (!input.sourcesChecked || input.sourcesChecked.length === 0) {
                    criticalGaps.push('No sources checked - verify against files, docs, or memory');
                }
                // Upgrade to thorough if good coverage
                if (input.known.length >= 3 && input.unknown.length >= 1 &&
                    input.sourcesChecked && input.sourcesChecked.length >= 2) {
                    completeness = 'thorough';
                }
                // Set context in state machine
                ctx.stateMachine.setContext({
                    known: input.known,
                    unknown: input.unknown,
                    assumptions: input.assumptions,
                    sourcesChecked: input.sourcesChecked || [],
                    dependencies: [],
                    pastWork: []
                });
                const newState = ctx.stateMachine.getState();
                const output = {
                    contextRegistered: true,
                    completeness,
                    currentPhase: newState.phase,
                    criticalGaps,
                    riskyAssumptions,
                    nextAction: completeness === 'sparse'
                        ? 'Context is sparse - gather more information before planning'
                        : 'Context collected. Now create a plan with atomic steps.'
                };
                ctx.log(`Context set: ${input.known.length} known, ${input.unknown.length} unknown, ${input.assumptions.length} assumptions`);
                return (0, index_js_1.createToolResult)(output);
            }
            catch (error) {
                ctx.log(`Error in astra_set_context: ${error}`);
                return (0, index_js_1.createErrorResult)(`Set context failed: ${error}`);
            }
        }
    };
}
// =============================================================================
// SET PLAN TOOL
// =============================================================================
function createSetPlanTool(ctx) {
    return {
        async invoke(options, _token) {
            ctx.log('Tool: astra_set_plan invoked');
            const input = options.input;
            try {
                const state = ctx.stateMachine.getState();
                const warnings = [];
                // Validate state - should be after context collection
                const validPhases = [types_js_1.WorkflowPhase.CONTEXT_COLLECTION, types_js_1.WorkflowPhase.PLANNING];
                if (!validPhases.includes(state.phase)) {
                    return (0, index_js_1.createErrorResult)(`Cannot set plan in phase: ${state.phase}. Collect context first. Use astra_set_context before creating plan.`);
                }
                // Validate steps
                if (!input.steps || input.steps.length === 0) {
                    return (0, index_js_1.createErrorResult)('Plan must have at least one step');
                }
                // Assess plan quality
                let planQuality = 'solid';
                let estimatedTotalMinutes = 0;
                // Convert input steps to workflow steps
                const workflowSteps = input.steps.map((step, index) => {
                    // Estimate time if not provided
                    const estimatedMinutes = step.estimatedMinutes || 30; // Default 30 min
                    estimatedTotalMinutes += estimatedMinutes;
                    // Check step quality
                    if (step.title.length < 5) {
                        warnings.push(`Step ${index + 1}: Title too short`);
                    }
                    if (!step.validationMethod) {
                        warnings.push(`Step ${index + 1}: No validation method defined`);
                    }
                    return {
                        id: `step-${index + 1}`,
                        title: step.title,
                        description: step.description,
                        status: 'not-started',
                        validationMethod: step.validationMethod || 'Manual verification',
                        estimatedMinutes
                    };
                });
                // Check for overly large steps
                const largeSteps = workflowSteps.filter(s => (s.estimatedMinutes || 0) > 120);
                if (largeSteps.length > 0) {
                    planQuality = 'needs-decomposition';
                    warnings.push(`${largeSteps.length} step(s) estimated >2 hours - consider breaking down`);
                }
                // Check total plan size
                if (workflowSteps.length > 10) {
                    planQuality = 'needs-decomposition';
                    warnings.push('Plan has >10 steps - consider splitting into multiple tasks');
                }
                // Acceptable quality if some minor issues
                if (planQuality === 'solid' && warnings.length > 0) {
                    planQuality = 'acceptable';
                }
                // Set plan in state machine
                ctx.stateMachine.setPlan(workflowSteps);
                const newState = ctx.stateMachine.getState();
                // TODO sync handling
                const todosSynced = false;
                if (input.syncWithTodos) {
                    // TODO: Could integrate with manage_todo_list here
                    warnings.push('TODO sync requested - use manage_todo_list to create matching TODOs');
                }
                const output = {
                    planRegistered: true,
                    stepCount: workflowSteps.length,
                    estimatedTotalMinutes,
                    planQuality,
                    todosSynced,
                    currentPhase: newState.phase,
                    warnings
                };
                ctx.log(`Plan set: ${workflowSteps.length} steps, ~${estimatedTotalMinutes} minutes`);
                return (0, index_js_1.createToolResult)(output);
            }
            catch (error) {
                ctx.log(`Error in astra_set_plan: ${error}`);
                return (0, index_js_1.createErrorResult)(`Set plan failed: ${error}`);
            }
        }
    };
}
//# sourceMappingURL=planning.js.map