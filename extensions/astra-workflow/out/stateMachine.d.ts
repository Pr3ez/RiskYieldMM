/**
 * Astra Workflow - State Machine
 *
 * Enforces valid state transitions based on Universal Guide workflow.
 * Prevents skipping phases, ensures validation before completion.
 *
 * NEW: Virtue-based transition validation using the 4-filter decision gate
 * (Wisdom, Temperance, Courage, Justice) from Platonic/Aristotelian ethics.
 */
import { WorkflowPhase, WorkflowState, WorkflowEvent, WorkflowStep, TaskGoal, ContextSnapshot, TaskType, VirtueMetrics, DetectedPathology } from "./types.js";
/**
 * Result of a virtue filter check
 */
export interface VirtueFilterResult {
    /** Whether the filter passed */
    passed: boolean;
    /** Virtue being checked */
    virtue: 'wisdom' | 'temperance' | 'courage' | 'justice';
    /** Score for this check (0-100) */
    score: number;
    /** Reason for pass/fail */
    reason: string;
    /** Suggested correction if failed */
    correction?: string;
}
/**
 * Result of the 4-filter decision gate
 */
export interface VirtueGateResult {
    /** Whether all filters passed */
    passed: boolean;
    /** Individual filter results */
    filters: VirtueFilterResult[];
    /** Overall virtue score */
    overallScore: number;
    /** Detected pathologies (if any) */
    pathologies: DetectedPathology[];
    /** Recommended action */
    recommendation: 'proceed' | 'pause' | 'replan' | 'abort';
}
export declare class WorkflowStateMachine {
    private state;
    private virtueMetrics;
    private listeners;
    constructor(sessionId: string, initialState?: WorkflowState, virtueMetrics?: VirtueMetrics);
    getState(): Readonly<WorkflowState>;
    getPhase(): WorkflowPhase;
    getVirtueMetrics(): Readonly<VirtueMetrics>;
    getCurrentStep(): WorkflowStep | undefined;
    getStrictness(): import("./types.js").WorkflowStrictness;
    /**
     * Run the 4-filter virtue gate before a transition
     * Based on Platonic/Aristotelian virtue ethics
     */
    runVirtueGate(targetPhase: WorkflowPhase, context?: Record<string, unknown>): VirtueGateResult;
    /**
     * Filter 1: WISDOM - Is this action based on calibrated beliefs?
     * Checks: Do we have enough information? Are assumptions validated?
     */
    private checkWisdom;
    /**
     * Filter 2: TEMPERANCE - Is this action proportional to the situation?
     * Checks: Not over-engineering? Within time budget? Balanced effort?
     */
    private checkTemperance;
    /**
     * Filter 3: COURAGE - Are risks evaluated appropriately?
     * Checks: Not too timid? Not reckless? Appropriate confidence?
     */
    private checkCourage;
    /**
     * Filter 4: JUSTICE - Is the action fair to all parts of the system?
     * Checks: Partnership balance? System harmony? Fair resource usage?
     */
    private checkJustice;
    /**
     * Detect soul imbalance pathologies
     */
    detectPathologies(): DetectedPathology[];
    /**
     * Update virtue metrics based on current behavior
     */
    updateVirtueMetrics(): void;
    private smoothScore;
    private scoreToStatus;
    subscribe(listener: (event: WorkflowEvent) => void): () => void;
    private emit;
    /**
     * Attempt to transition to a new phase
     * @param toPhase Target phase
     * @param reason Reason for transition
     * @param useVirtueGate Whether to run virtue filter check (default: true for non-trivial tasks)
     */
    transition(toPhase: WorkflowPhase, reason: string, useVirtueGate?: boolean): {
        success: boolean;
        error?: string;
        virtueGate?: VirtueGateResult;
    };
    /**
     * Check if transitioning would violate strictness rules
     */
    private checkStrictnessViolation;
    /**
     * Start a new task (IDLE → VALUE_GATE or GOAL_DEFINITION)
     */
    startTask(taskType: TaskType): {
        success: boolean;
        error?: string;
    };
    /**
     * Pass value gate (VALUE_GATE → GOAL_DEFINITION)
     */
    passValueGate(valueJustification: string): {
        success: boolean;
        error?: string;
    };
    /**
     * Fail value gate (VALUE_GATE → IDLE)
     */
    failValueGate(reason: string): {
        success: boolean;
        error?: string;
    };
    /**
     * Set goal (GOAL_DEFINITION → CONTEXT_COLLECTION)
     */
    setGoal(goal: TaskGoal): {
        success: boolean;
        error?: string;
    };
    /**
     * Set context (CONTEXT_COLLECTION → ENVIRONMENT_PRIMING or PLANNING)
     */
    setContext(context: ContextSnapshot): {
        success: boolean;
        error?: string;
    };
    /**
     * Complete environment priming (ENVIRONMENT_PRIMING → PLANNING)
     */
    completeEnvironmentPriming(): {
        success: boolean;
        error?: string;
    };
    /**
     * Set plan (PLANNING → EXECUTING)
     */
    setPlan(steps: WorkflowStep[]): {
        success: boolean;
        error?: string;
    };
    /**
     * Start executing a step
     */
    startStep(stepId: string): {
        success: boolean;
        error?: string;
    };
    /**
     * Complete a step and validate
     */
    completeStep(stepId: string, validationResult: "passed" | "failed" | "skipped"): {
        success: boolean;
        error?: string;
    };
    /**
     * Run drift check
     */
    runDriftCheck(): {
        success: boolean;
        driftDetected: boolean;
        issues: string[];
    };
    /**
     * Run memory check
     */
    runMemoryCheck(): {
        success: boolean;
        actions: string[];
    };
    /**
     * Reset drift check counter (called after drift check completes)
     */
    resetDriftCheckCounter(): void;
    /**
     * Reset memory check counter (called after memory check completes)
     */
    resetMemoryCheckCounter(): void;
    /**
     * Record that an identity check was performed
     */
    recordIdentityCheck(): void;
    /**
     * Block a specific step
     */
    blockStep(stepId: string, reason: string): {
        success: boolean;
        error?: string;
    };
    /**
     * Complete the workflow
     */
    complete(summary: string): {
        success: boolean;
        error?: string;
    };
    /**
     * Enter blocked state
     */
    block(reason: string): {
        success: boolean;
        error?: string;
    };
    /**
     * Unblock and return to previous appropriate phase
     */
    unblock(returnToPhase: WorkflowPhase): {
        success: boolean;
        error?: string;
    };
    /**
     * Enter error recovery
     */
    enterErrorRecovery(error: string): {
        success: boolean;
        error?: string;
    };
    /**
     * Recover from error
     */
    recoverFromError(returnToPhase: WorkflowPhase): {
        success: boolean;
        error?: string;
    };
    /**
     * Reset to idle (emergency reset)
     */
    reset(reason: string): void;
    toJSON(): string;
    static fromJSON(json: string, sessionId: string): WorkflowStateMachine;
    /**
     * Simplified transition using action names
     */
    transitionByAction(action: WorkflowAction): {
        success: boolean;
        error?: string;
    };
    /**
     * Set goal with simplified interface
     */
    setGoalSimple(goal: GoalDefinition): void;
    /**
     * Set steps from step definitions
     */
    setStepsFromDefinitions(steps: StepDefinition[]): void;
    /**
     * Start a specific step by ID
     */
    startStepById(stepId: string): void;
    /**
     * Validate current step
     */
    validateCurrentStep(stepId: string, success: boolean, notes?: string): void;
    /**
     * Complete step with result
     */
    completeStepWithResult(stepId: string, result: StepResult): void;
    /**
     * Complete drift check
     */
    completeDriftCheck(): void;
    /**
     * Complete memory check
     */
    completeMemoryCheck(): void;
    /**
     * Add a learning
     */
    addLearning(learning: string): void;
    /**
     * Add an error record
     */
    addError(error: ErrorRecord): void;
    /**
     * Load state from persisted data
     */
    loadState(state: WorkflowState): void;
}
export type WorkflowAction = "start_task" | "skip_to_execute" | "cancel" | "pass_value_gate" | "define_goal" | "collect_context" | "prime_environment" | "create_plan" | "start_step" | "validate_step" | "complete_step" | "drift_check" | "memory_check" | "complete_task" | "report_error" | "recover" | "block" | "unblock";
import { GoalDefinition, StepDefinition, StepResult, ErrorRecord } from "./types.js";
//# sourceMappingURL=stateMachine.d.ts.map