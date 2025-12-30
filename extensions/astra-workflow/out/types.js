"use strict";
/**
 * Astra Workflow - Core Types
 *
 * Based on Universal Guide V2.1 workflow phases:
 * Phase I: Strategy & Alignment (Value Gate → Goal → Context → Environment)
 * Phase II: Planning & Architecture (TODO Plan)
 * Phase III: Execution & Validation (Execute → Validate)
 * Phase IV: Memory & Maintenance (Memory → Document → Drift Check)
 * Phase V: Completion & Handoff (Communicate → Handoff → Reflect)
 */
Object.defineProperty(exports, "__esModule", { value: true });
exports.DEFAULT_THRESHOLDS = exports.STRICTNESS_BY_TYPE = exports.TaskType = exports.VALID_TRANSITIONS = exports.WorkflowPhase = void 0;
exports.createInitialMetrics = createInitialMetrics;
exports.createInitialState = createInitialState;
// =============================================================================
// WORKFLOW STATE MACHINE
// =============================================================================
/**
 * Workflow phases aligned with Universal Guide
 */
var WorkflowPhase;
(function (WorkflowPhase) {
    /** No active task - waiting for input */
    WorkflowPhase["IDLE"] = "IDLE";
    /** Phase I: Value Gate - Is this worth doing? */
    WorkflowPhase["VALUE_GATE"] = "VALUE_GATE";
    /** Phase I: Goal Definition - What does success look like? */
    WorkflowPhase["GOAL_DEFINITION"] = "GOAL_DEFINITION";
    /** Phase I: Context Collection - What do we know? */
    WorkflowPhase["CONTEXT_COLLECTION"] = "CONTEXT_COLLECTION";
    /** Phase I: Environment Priming - Is workspace ready? */
    WorkflowPhase["ENVIRONMENT_PRIMING"] = "ENVIRONMENT_PRIMING";
    /** Phase II: Planning - Break into steps */
    WorkflowPhase["PLANNING"] = "PLANNING";
    /** Phase III: Executing a step */
    WorkflowPhase["EXECUTING"] = "EXECUTING";
    /** Phase III: Validating step result */
    WorkflowPhase["VALIDATING"] = "VALIDATING";
    /** Phase IV: Memory check between phases */
    WorkflowPhase["MEMORY_CHECK"] = "MEMORY_CHECK";
    /** Phase IV: Drift detection check */
    WorkflowPhase["DRIFT_CHECK"] = "DRIFT_CHECK";
    /** Phase V: Task completion and handoff */
    WorkflowPhase["COMPLETING"] = "COMPLETING";
    /** Blocked - waiting for guidance */
    WorkflowPhase["BLOCKED"] = "BLOCKED";
    /** Error recovery mode */
    WorkflowPhase["ERROR_RECOVERY"] = "ERROR_RECOVERY";
})(WorkflowPhase || (exports.WorkflowPhase = WorkflowPhase = {}));
/**
 * Valid state transitions (state machine definition)
 */
exports.VALID_TRANSITIONS = {
    [WorkflowPhase.IDLE]: [WorkflowPhase.VALUE_GATE],
    [WorkflowPhase.VALUE_GATE]: [
        WorkflowPhase.GOAL_DEFINITION, // Passed value gate
        WorkflowPhase.IDLE, // Failed value gate - stop
    ],
    [WorkflowPhase.GOAL_DEFINITION]: [
        WorkflowPhase.CONTEXT_COLLECTION,
        WorkflowPhase.BLOCKED, // Need clarification
    ],
    [WorkflowPhase.CONTEXT_COLLECTION]: [
        WorkflowPhase.ENVIRONMENT_PRIMING,
        WorkflowPhase.BLOCKED, // Missing critical context
    ],
    [WorkflowPhase.ENVIRONMENT_PRIMING]: [
        WorkflowPhase.PLANNING,
        WorkflowPhase.BLOCKED, // Tools not available
    ],
    [WorkflowPhase.PLANNING]: [
        WorkflowPhase.EXECUTING, // Plan created, start execution
        WorkflowPhase.BLOCKED, // Can't create plan
    ],
    [WorkflowPhase.EXECUTING]: [
        WorkflowPhase.VALIDATING, // Step done, validate
        WorkflowPhase.DRIFT_CHECK, // Periodic drift check
        WorkflowPhase.MEMORY_CHECK, // Periodic memory check
        WorkflowPhase.BLOCKED, // Execution blocked
        WorkflowPhase.ERROR_RECOVERY, // Error encountered
    ],
    [WorkflowPhase.VALIDATING]: [
        WorkflowPhase.EXECUTING, // Validation passed, next step
        WorkflowPhase.COMPLETING, // All steps done
        WorkflowPhase.ERROR_RECOVERY, // Validation failed
    ],
    [WorkflowPhase.MEMORY_CHECK]: [
        WorkflowPhase.EXECUTING, // Continue execution
        WorkflowPhase.DRIFT_CHECK, // Found drift
    ],
    [WorkflowPhase.DRIFT_CHECK]: [
        WorkflowPhase.EXECUTING, // No drift, continue
        WorkflowPhase.PLANNING, // Drift detected, replan
        WorkflowPhase.IDLE, // Major drift, abort
    ],
    [WorkflowPhase.COMPLETING]: [
        WorkflowPhase.IDLE, // Task done
    ],
    [WorkflowPhase.BLOCKED]: [
        WorkflowPhase.GOAL_DEFINITION, // Clarification received
        WorkflowPhase.CONTEXT_COLLECTION,
        WorkflowPhase.ENVIRONMENT_PRIMING,
        WorkflowPhase.PLANNING,
        WorkflowPhase.EXECUTING,
        WorkflowPhase.IDLE, // Gave up
    ],
    [WorkflowPhase.ERROR_RECOVERY]: [
        WorkflowPhase.EXECUTING, // Recovered, continue
        WorkflowPhase.PLANNING, // Need to replan
        WorkflowPhase.BLOCKED, // Can't recover
        WorkflowPhase.IDLE, // Abort
    ],
};
// =============================================================================
// TASK TYPES
// =============================================================================
/**
 * Task classification (affects workflow strictness)
 */
var TaskType;
(function (TaskType) {
    /** Quick question or lookup */
    TaskType["TRIVIAL"] = "TRIVIAL";
    /** Single focused action */
    TaskType["SIMPLE"] = "SIMPLE";
    /** Multi-step with clear path */
    TaskType["STANDARD"] = "STANDARD";
    /** Complex, requires research/planning */
    TaskType["COMPLEX"] = "COMPLEX";
    /** Unknown until analyzed */
    TaskType["UNKNOWN"] = "UNKNOWN";
})(TaskType || (exports.TaskType = TaskType = {}));
exports.STRICTNESS_BY_TYPE = {
    [TaskType.TRIVIAL]: {
        requireValueGate: false,
        requireGoal: false,
        requireContext: false,
        requireTodos: false,
        requireValidation: false,
        driftCheckInterval: Infinity,
        memoryCheckInterval: Infinity,
    },
    [TaskType.SIMPLE]: {
        requireValueGate: false,
        requireGoal: true,
        requireContext: false,
        requireTodos: true,
        requireValidation: true,
        driftCheckInterval: 10,
        memoryCheckInterval: 20,
    },
    [TaskType.STANDARD]: {
        requireValueGate: true,
        requireGoal: true,
        requireContext: true,
        requireTodos: true,
        requireValidation: true,
        driftCheckInterval: 5,
        memoryCheckInterval: 10,
    },
    [TaskType.COMPLEX]: {
        requireValueGate: true,
        requireGoal: true,
        requireContext: true,
        requireTodos: true,
        requireValidation: true,
        driftCheckInterval: 3,
        memoryCheckInterval: 7,
    },
    [TaskType.UNKNOWN]: {
        requireValueGate: true,
        requireGoal: true,
        requireContext: true,
        requireTodos: true,
        requireValidation: true,
        driftCheckInterval: 5,
        memoryCheckInterval: 10,
    },
};
exports.DEFAULT_THRESHOLDS = {
    maxDriftRate: 0.3, // Alert if >30% of checks detect drift
    minMemoryCheckFrequency: 0.1, // At least 1 check per 10 steps
    maxStepsWithoutTodo: 2, // Alert if >2 steps without TODOs
    minVerificationRate: 0.8, // At least 80% claims verified
    maxUnilateralDecisionRate: 0.2, // Max 20% decisions without presenting analysis
    maxInvalidTransitionRate: 0.05, // Max 5% invalid transitions
};
// =============================================================================
// FACTORY FUNCTIONS
// =============================================================================
/**
 * Create initial cognitive metrics
 */
function createInitialMetrics(sessionId) {
    return {
        sessionId,
        sessionStart: new Date(),
        identityChecks: 0,
        driftDetections: 0,
        memoryReads: 0,
        memoryWrites: 0,
        memoryChecks: 0,
        todosCreated: 0,
        todosCompleted: 0,
        stepsStarted: 0,
        stepsWithoutTodo: 0,
        claimsMade: 0,
        claimsVerified: 0,
        verificationFailures: 0,
        unilateralDecisions: 0,
        analysisPresented: 0,
        stepsExecuted: 0,
        validTransitions: 0,
        invalidTransitions: 0,
        phasesSkipped: 0,
    };
}
/**
 * Create initial workflow state
 */
function createInitialState(sessionId) {
    return {
        phase: WorkflowPhase.IDLE,
        taskType: TaskType.UNKNOWN,
        steps: [],
        currentStepIndex: -1,
        stepsSinceDriftCheck: 0,
        stepsSinceMemoryCheck: 0,
        metrics: createInitialMetrics(sessionId),
        stateHistory: [
            {
                phase: WorkflowPhase.IDLE,
                timestamp: new Date(),
                reason: "Initial state",
            },
        ],
    };
}
//# sourceMappingURL=types.js.map