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

// =============================================================================
// WORKFLOW STATE MACHINE
// =============================================================================

/**
 * Workflow phases aligned with Universal Guide
 */
export enum WorkflowPhase {
  /** No active task - waiting for input */
  IDLE = "IDLE",

  /** Phase I: Value Gate - Is this worth doing? */
  VALUE_GATE = "VALUE_GATE",

  /** Phase I: Goal Definition - What does success look like? */
  GOAL_DEFINITION = "GOAL_DEFINITION",

  /** Phase I: Context Collection - What do we know? */
  CONTEXT_COLLECTION = "CONTEXT_COLLECTION",

  /** Phase I: Environment Priming - Is workspace ready? */
  ENVIRONMENT_PRIMING = "ENVIRONMENT_PRIMING",

  /** Phase II: Planning - Break into steps */
  PLANNING = "PLANNING",

  /** Phase III: Executing a step */
  EXECUTING = "EXECUTING",

  /** Phase III: Validating step result */
  VALIDATING = "VALIDATING",

  /** Phase IV: Memory check between phases */
  MEMORY_CHECK = "MEMORY_CHECK",

  /** Phase IV: Drift detection check */
  DRIFT_CHECK = "DRIFT_CHECK",

  /** Phase V: Task completion and handoff */
  COMPLETING = "COMPLETING",

  /** Blocked - waiting for guidance */
  BLOCKED = "BLOCKED",

  /** Error recovery mode */
  ERROR_RECOVERY = "ERROR_RECOVERY",
}

/**
 * Valid state transitions (state machine definition)
 */
export const VALID_TRANSITIONS: Record<WorkflowPhase, WorkflowPhase[]> = {
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
export enum TaskType {
  /** Quick question or lookup */
  TRIVIAL = "TRIVIAL",

  /** Single focused action */
  SIMPLE = "SIMPLE",

  /** Multi-step with clear path */
  STANDARD = "STANDARD",

  /** Complex, requires research/planning */
  COMPLEX = "COMPLEX",

  /** Unknown until analyzed */
  UNKNOWN = "UNKNOWN",
}

/**
 * Workflow strictness based on task type
 */
export interface WorkflowStrictness {
  /** Require explicit value gate */
  requireValueGate: boolean;
  /** Require written goal */
  requireGoal: boolean;
  /** Require context collection */
  requireContext: boolean;
  /** Require TODO creation */
  requireTodos: boolean;
  /** Require step validation */
  requireValidation: boolean;
  /** Drift check interval (steps) */
  driftCheckInterval: number;
  /** Memory check interval (steps) */
  memoryCheckInterval: number;
}

export const STRICTNESS_BY_TYPE: Record<TaskType, WorkflowStrictness> = {
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

// =============================================================================
// COGNITIVE METRICS
// =============================================================================

/**
 * Cognitive health metrics (inspired by Netdata per-metric monitoring)
 */
export interface CognitiveMetrics {
  /** Session identifier */
  sessionId: string;

  /** Session start time */
  sessionStart: Date;

  // --- Identity Drift ---
  /** Times identity was checked */
  identityChecks: number;
  /** Times drift was detected */
  driftDetections: number;

  // --- Memory Hygiene ---
  /** Memory reads this session */
  memoryReads: number;
  /** Memory writes this session */
  memoryWrites: number;
  /** Memory checks performed */
  memoryChecks: number;

  // --- TODO Adherence ---
  /** TODOs created */
  todosCreated: number;
  /** TODOs completed */
  todosCompleted: number;
  /** Steps marked in_progress */
  stepsStarted: number;
  /** Steps without TODO (violation) */
  stepsWithoutTodo: number;

  // --- Verification Rate ---
  /** Claims made */
  claimsMade: number;
  /** Claims verified */
  claimsVerified: number;
  /** Verification failures */
  verificationFailures: number;

  // --- Partnership Balance ---
  /** Decisions made unilaterally */
  unilateralDecisions: number;
  /** Analysis presented for review */
  analysisPresented: number;

  // --- Workflow Compliance ---
  /** Steps executed */
  stepsExecuted: number;
  /** Valid state transitions */
  validTransitions: number;
  /** Invalid state transitions (violations) */
  invalidTransitions: number;
  /** Phases skipped */
  phasesSkipped: number;
}

/**
 * Alert thresholds for cognitive metrics
 */
export interface MetricThresholds {
  /** Drift detection rate (detections/checks) */
  maxDriftRate: number;
  /** Minimum memory check frequency */
  minMemoryCheckFrequency: number;
  /** Maximum steps without TODO */
  maxStepsWithoutTodo: number;
  /** Minimum verification rate */
  minVerificationRate: number;
  /** Maximum unilateral decision rate */
  maxUnilateralDecisionRate: number;
  /** Maximum invalid transition rate */
  maxInvalidTransitionRate: number;
}

export const DEFAULT_THRESHOLDS: MetricThresholds = {
  maxDriftRate: 0.3, // Alert if >30% of checks detect drift
  minMemoryCheckFrequency: 0.1, // At least 1 check per 10 steps
  maxStepsWithoutTodo: 2, // Alert if >2 steps without TODOs
  minVerificationRate: 0.8, // At least 80% claims verified
  maxUnilateralDecisionRate: 0.2, // Max 20% decisions without presenting analysis
  maxInvalidTransitionRate: 0.05, // Max 5% invalid transitions
};

// =============================================================================
// WORKFLOW STATE
// =============================================================================

/**
 * Step definition (matches TODO structure)
 */
export interface WorkflowStep {
  /** Unique step ID */
  id: string;
  /** Step title */
  title: string;
  /** Detailed description */
  description: string;
  /** Current status */
  status: "not-started" | "in-progress" | "completed" | "blocked" | "skipped";
  /** Estimated effort */
  estimatedMinutes?: number;
  /** Actual effort */
  actualMinutes?: number;
  /** Validation method */
  validationMethod?: string;
  /** Validation result */
  validationResult?: "passed" | "failed" | "skipped";
  /** Plan B if primary fails */
  planB?: string;
  /** Is this a recursive sub-project? */
  isRecursive?: boolean;
  /** When step was started */
  startedAt?: string;
  /** When step was completed */
  completedAt?: string;
  /** Reason step is blocked (if blocked) */
  blockReason?: string;
  /** Reflection captured after completion */
  reflection?: StepReflection;
}

/**
 * Goal definition
 */
export interface TaskGoal {
  /** One sentence goal statement */
  statement: string;
  /** How success will be measured */
  successCondition: string;
  /** How failure will be recognized */
  failureCondition: string;
  /** Time budget (minutes) */
  timeBudget?: number;
  /** Quality threshold */
  qualityThreshold?: string;
}

/**
 * Context snapshot
 */
export interface ContextSnapshot {
  /** What is known */
  known: string[];
  /** What is unknown */
  unknown: string[];
  /** Assumptions being made */
  assumptions: string[];
  /** External dependencies */
  dependencies: string[];
  /** Relevant past work */
  pastWork: string[];
  /** Sources that were checked */
  sourcesChecked: string[];
}

/**
 * Current workflow state (persisted)
 */
export interface WorkflowState {
  /** Current phase */
  phase: WorkflowPhase;

  /** Classified task type */
  taskType: TaskType;

  /** Task goal */
  goal?: TaskGoal;

  /** Collected context */
  context?: ContextSnapshot;

  /** Planned steps */
  steps: WorkflowStep[];

  /** Current step index (-1 if not executing) */
  currentStepIndex: number;

  /** Steps executed since last drift check */
  stepsSinceDriftCheck: number;

  /** Steps executed since last memory check */
  stepsSinceMemoryCheck: number;

  /** Cognitive metrics */
  metrics: CognitiveMetrics;

  /** Blocker description if blocked */
  blocker?: string;

  /** Error description if in error recovery */
  error?: string;

  /** Last virtue gate result */
  lastVirtueGate?: VirtueGateResult;

  /** Last reflection captured */
  lastReflection?: StepReflection;

  /** Last hypothesis captured */
  lastHypothesis?: Hypothesis;

  /** Pattern suggestions derived from memory */
  patternSuggestions?: PatternSuggestion[];

  /** Latest identity affirmation */
  identityAffirmation?: string;

  /** Coaching tip for next session */
  coachingTip?: string;

  /** Value justification captured at value gate */
  valueJustification?: string;

  /** State history for debugging */
  stateHistory: Array<{
    phase: WorkflowPhase;
    timestamp: Date;
    reason: string;
  }>;
}

// =============================================================================
// VIRTUE FILTER / GATE
// =============================================================================

export interface VirtueFilterResult {
  passed: boolean;
  virtue: "wisdom" | "temperance" | "courage" | "justice";
  score: number;
  reason: string;
  correction?: string;
}

export interface VirtueGateResult {
  passed: boolean;
  filters: VirtueFilterResult[];
  overallScore: number;
  pathologies: DetectedPathology[];
  recommendation: "proceed" | "pause" | "replan" | "abort";
}

// =============================================================================
// REFLECTIONS
// =============================================================================

export interface StepReflection {
  insight?: string;
  tension?: string;
  habit?: string;
  hypothesis?: string;
  test?: string;
  evidence?: string;
  confidence?: number;
  outcome?: "passed" | "failed" | "uncertain";
}

export interface Hypothesis {
  statement: string;
  test?: string;
  evidence?: string;
  confidence?: number;
  outcome?: "passed" | "failed" | "uncertain";
}

// =============================================================================
// PATTERN SUGGESTIONS
// =============================================================================

export interface PatternSuggestion {
  title: string;
  snippet: string;
  score: number;
  source: string;
}

// =============================================================================
// EVENTS
// =============================================================================

/**
 * Workflow events emitted for UI updates
 */
export type WorkflowEvent =
  | { type: "PHASE_CHANGED"; from: WorkflowPhase; to: WorkflowPhase }
  | { type: "STEP_STARTED"; stepId: string }
  | { type: "STEP_COMPLETED"; stepId: string; validationResult: string }
  | { type: "DRIFT_DETECTED"; severity: "low" | "medium" | "high" }
  | { type: "METRIC_ALERT"; metric: string; value: number; threshold: number }
  | { type: "WORKFLOW_BLOCKED"; reason: string }
  | { type: "WORKFLOW_ERROR"; error: string }
  | { type: "WORKFLOW_COMPLETED"; summary: string };

// =============================================================================
// FACTORY FUNCTIONS
// =============================================================================

/**
 * Create initial cognitive metrics
 */
export function createInitialMetrics(sessionId: string): CognitiveMetrics {
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
export function createInitialState(sessionId: string): WorkflowState {
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

// =============================================================================
// TYPE ALIASES (for extension.ts compatibility)
// =============================================================================

/**
 * Goal definition input (simplified for UI commands)
 */
export interface GoalDefinition {
  statement: string;
  successCondition: string;
  failureCondition: string;
  timeBudget?: number;
}

/**
 * Step definition input (simplified for UI commands)
 */
export interface StepDefinition {
  id: string;
  title: string;
  description: string;
  validationMethod?: string;
  estimatedEffort?: number;
}

/**
 * Step result (for validation)
 */
export interface StepResult {
  success: boolean;
  notes?: string;
  actualEffort?: number;
}

/**
 * Error record
 */
export interface ErrorRecord {
  timestamp: Date;
  description: string;
  rootCause?: string;
  prevention?: string;
}

// =============================================================================
// TOOL INPUT/OUTPUT TYPES
// =============================================================================

/**
 * Value gate answers - validates if task is worth doing
 */
export interface ValueGateAnswers {
  /** What is the concrete benefit if you succeed? */
  benefit: string;
  /** Is this the simplest way to achieve that benefit? */
  simplest: boolean;
  /** What happens if you don't do this? */
  consequence: string;
}

// ========================= LIFECYCLE TOOLS =========================

/**
 * Input for astra_session_start tool
 */
export interface SessionStartInput {
  /** Whether to resume previous task state or start fresh */
  resumePreviousTask?: boolean;
  /** Whether to verify /memories/session.md is current */
  checkMemory?: boolean;
}

/**
 * Output from astra_session_start tool
 */
export interface SessionStartOutput {
  /** Whether a previous session was found */
  previousSessionFound: boolean;
  /** Previous phase if resuming */
  previousPhase?: WorkflowPhase;
  /** Whether session.md is current */
  memoryStatus: 'current' | 'stale' | 'missing';
  /** Recommendation for how to proceed */
  recommendation: 'resume' | 'start-fresh' | 'check-memory-first';
  /** Any alerts or warnings */
  alerts: string[];
}

/**
 * Input for astra_task_start tool
 */
export interface TaskStartInput {
  /** Brief description of what you're about to do */
  taskDescription: string;
  /** Answers to value gate questions */
  valueGate: ValueGateAnswers;
}

/**
 * Output from astra_task_start tool
 */
export interface TaskStartOutput {
  /** Assigned task ID */
  taskId: string;
  /** Classified task type */
  classifiedType: TaskType;
  /** Whether value gate passed */
  valueGatePassed: boolean;
  /** New workflow phase */
  currentPhase: WorkflowPhase;
  /** Next recommended action */
  nextAction: string;
  /** Warnings about the task */
  warnings: string[];
}

/**
 * Input for astra_task_complete tool
 */
export interface TaskCompleteInput {
  /** Was the original success condition achieved? */
  successCriteriaMet: boolean;
  /** What did you learn from this task? */
  learnings?: string[];
  /** Mistakes to record for future reference */
  mistakesToAvoid?: string[];
  /** Successful patterns to record */
  patternsToRepeat?: string[];
  /** Should session.md be updated with completion? */
  updateSessionMd?: boolean;
}

/**
 * Output from astra_task_complete tool
 */
export interface TaskCompleteOutput {
  /** Summary of completed task */
  summary: string;
  /** Duration of task */
  durationMinutes: number;
  /** Steps completed */
  stepsCompleted: number;
  /** Steps skipped */
  stepsSkipped: number;
  /** Learnings recorded to memory */
  learningsRecorded: boolean;
  /** Mistakes recorded to memory */
  mistakesRecorded: boolean;
  /** New workflow phase */
  currentPhase: WorkflowPhase;
}

/**
 * Input for astra_session_end tool
 */
export interface SessionEndInput {
  /** Current state of the task */
  taskStatus: 'completed' | 'in-progress' | 'blocked' | 'abandoned';
  /** Notes for resuming next session */
  resumeNotes?: string;
  /** Update /memories/session.md with session summary */
  updateSessionMd?: boolean;
}

/**
 * Output from astra_session_end tool
 */
export interface SessionEndOutput {
  /** Session summary */
  summary: string;
  /** Session duration */
  sessionDurationMinutes: number;
  /** Tasks completed this session */
  tasksCompleted: number;
  /** Steps completed this session */
  stepsCompleted: number;
  /** State saved for next session */
  statePersisted: boolean;
  /** Handoff context written */
  handoffWritten: boolean;
}

// ========================= PLANNING TOOLS =========================

/**
 * Input for astra_set_goal tool
 */
export interface SetGoalInput {
  /** ONE clear sentence describing the goal */
  statement: string;
  /** How will you know you succeeded? */
  successCondition: string;
  /** How will you know you failed? */
  failureCondition: string;
  /** Optional time budget */
  timeBudgetMinutes?: number;
}

/**
 * Output from astra_set_goal tool
 */
export interface SetGoalOutput {
  /** Goal registered successfully */
  goalRegistered: boolean;
  /** Goal quality assessment */
  goalQuality: 'clear' | 'vague' | 'too-broad';
  /** New workflow phase */
  currentPhase: WorkflowPhase;
  /** Next recommended action */
  nextAction: string;
  /** Warnings about the goal */
  warnings: string[];
}

/**
 * Input for astra_set_context tool
 */
export interface SetContextInput {
  /** Facts you have verified */
  known: string[];
  /** Gaps in your knowledge */
  unknown: string[];
  /** Things you're assuming (labeled guesses) */
  assumptions: string[];
  /** What sources did you check? (files, memory, docs) */
  sourcesChecked?: string[];
}

/**
 * Output from astra_set_context tool
 */
export interface SetContextOutput {
  /** Context registered successfully */
  contextRegistered: boolean;
  /** Context completeness assessment */
  completeness: 'thorough' | 'adequate' | 'sparse';
  /** New workflow phase */
  currentPhase: WorkflowPhase;
  /** Identified knowledge gaps to address */
  criticalGaps: string[];
  /** Risky assumptions to validate */
  riskyAssumptions: string[];
  /** Next recommended action */
  nextAction: string;
}

/**
 * Plan step definition
 */
export interface PlanStepInput {
  /** Step title */
  title: string;
  /** Step description */
  description: string;
  /** How to validate this step */
  validationMethod?: string;
  /** Estimated time in minutes */
  estimatedMinutes?: number;
}

/**
 * Input for astra_set_plan tool
 */
export interface SetPlanInput {
  /** List of atomic execution steps */
  steps: PlanStepInput[];
  /** Also create matching TODOs via manage_todo_list */
  syncWithTodos?: boolean;
}

/**
 * Output from astra_set_plan tool
 */
export interface SetPlanOutput {
  /** Plan registered successfully */
  planRegistered: boolean;
  /** Number of steps in plan */
  stepCount: number;
  /** Estimated total duration */
  estimatedTotalMinutes: number;
  /** Plan quality assessment */
  planQuality: 'solid' | 'acceptable' | 'needs-decomposition';
  /** TODOs synced successfully */
  todosSynced: boolean;
  /** New workflow phase */
  currentPhase: WorkflowPhase;
  /** Warnings about the plan */
  warnings: string[];
}

// ========================= EXECUTION TOOLS =========================

/**
 * Input for astra_step_start tool
 */
export interface StepStartInput {
  /** Step ID to start (e.g., 'step-1') */
  stepId: string;
  /** Brief description of how you'll approach this step */
  approach?: string;
}

/**
 * Output from astra_step_start tool
 */
export interface StepStartOutput {
  /** Step started successfully */
  stepStarted: boolean;
  /** Step details */
  step: WorkflowStep;
  /** New workflow phase */
  currentPhase: WorkflowPhase;
  /** Step-specific guidance */
  guidance: string;
  /** Reminder about validation */
  validationReminder: string;
}

/**
 * Input for astra_step_complete tool
 */
export interface StepCompleteInput {
  /** Step ID to complete */
  stepId: string;
  /** What was the actual outcome? */
  outcome: string;
  /** Has this been validated? */
  validated: boolean;
  /** How was it validated? */
  validationMethod?: string;
  /** What evidence supports the validation? */
  validationEvidence?: string;
}

/**
 * Output from astra_step_complete tool
 */
export interface StepCompleteOutput {
  /** Step completed successfully */
  stepCompleted: boolean;
  /** Actual duration vs estimate */
  durationVsEstimate: 'on-track' | 'faster' | 'slower';
  /** Steps remaining */
  stepsRemaining: number;
  /** Progress percentage */
  progressPercent: number;
  /** New workflow phase */
  currentPhase: WorkflowPhase;
  /** Time for drift check? */
  driftCheckDue: boolean;
  /** Time for memory check? */
  memoryCheckDue: boolean;
  /** Next step to work on */
  nextStep?: WorkflowStep;
}

/**
 * Input for astra_step_block tool
 */
export interface StepBlockInput {
  /** Step ID that is blocked */
  stepId: string;
  /** What is blocking progress? */
  blockReason: string;
  /** What specific input or action is needed? */
  waitingFor: string;
  /** Alternative approach if block can't be resolved */
  planB?: string;
}

/**
 * Output from astra_step_block tool
 */
export interface StepBlockOutput {
  /** Step marked as blocked */
  stepBlocked: boolean;
  /** Blocker recorded */
  blockerRecorded: boolean;
  /** New workflow phase */
  currentPhase: WorkflowPhase;
  /** Suggested resolution approaches */
  suggestedResolutions: string[];
}

/**
 * Input for astra_validate tool
 */
export interface ValidateInput {
  /** Step ID being validated */
  stepId: string;
  /** Validation result */
  result: 'passed' | 'failed' | 'partial';
  /** How was this validated? (tests, manual check, review) */
  method: string;
  /** What evidence supports this result? */
  evidence?: string;
  /** Was this logically independent validation? */
  independentCheck?: boolean;
}

/**
 * Output from astra_validate tool
 */
export interface ValidateOutput {
  /** Validation recorded */
  validationRecorded: boolean;
  /** Validation quality assessment */
  validationQuality: 'rigorous' | 'adequate' | 'weak';
  /** Can proceed to next step */
  canProceed: boolean;
  /** New workflow phase */
  currentPhase: WorkflowPhase;
  /** Recommendations */
  recommendations: string[];
}

// ========================= MONITORING TOOLS =========================

/**
 * Input for astra_drift_check tool
 */
export interface DriftCheckInput {
  /** Does current work serve original goal? */
  stillServesGoal: boolean;
  /** Solving original problem, not different one? */
  solvingOriginalProblem: boolean;
  /** No features added beyond original scope? */
  noScopeCreep: boolean;
  /** Not optimizing what doesn't need it? */
  noOverOptimizing?: boolean;
  /** Perfectionism not blocking completion? */
  noPerfectionism?: boolean;
  /** Within 2x estimated time? */
  withinTimeEstimate?: boolean;
  /** Any concerns or observations */
  driftNotes?: string;
}

/**
 * Output from astra_drift_check tool
 */
export interface DriftCheckOutput {
  /** Drift detected */
  driftDetected: boolean;
  /** Drift severity */
  driftSeverity: 'none' | 'low' | 'medium' | 'high';
  /** Specific drift indicators */
  driftIndicators: string[];
  /** Recommended corrective action */
  correctionNeeded: 'none' | 'refocus' | 'replan' | 'abort';
  /** New workflow phase */
  currentPhase: WorkflowPhase;
  /** Guidance for correction */
  guidance: string;
}

/**
 * Input for astra_memory_check tool
 */
export interface MemoryCheckInput {
  /** Checked /memories/session.md? */
  sessionMdChecked: boolean;
  /** Is session.md still accurate? */
  sessionMdCurrent?: boolean;
  /** Updated session.md if needed? */
  sessionMdUpdated?: boolean;
  /** Checked patterns.md for relevant learnings? */
  patternsChecked?: boolean;
  /** Checked mistakes.md to avoid past errors? */
  mistakesChecked?: boolean;
  /** Any new patterns or mistakes to record? */
  newInsights?: string;
}

/**
 * Output from astra_memory_check tool
 */
export interface MemoryCheckOutput {
  /** Memory check completed */
  checkCompleted: boolean;
  /** Memory health status */
  memoryHealth: 'healthy' | 'stale' | 'needs-update';
  /** Session.md status */
  sessionMdStatus: 'current' | 'stale' | 'missing';
  /** Patterns found relevant to current work */
  relevantPatterns: string[];
  /** Mistakes to avoid for current work */
  mistakesToAvoid: string[];
  /** Recommendations */
  recommendations: string[];
}

/**
 * Input for astra_identity_check tool
 */
export interface IdentityCheckInput {
  /** Are you feeling like generic Claude rather than Astra? */
  feelingGeneric?: boolean;
  /** Did you review /memories/core.md? */
  coreChecked: boolean;
  /** Did you review /memories/przem.md? */
  partnerChecked?: boolean;
  /** Brief statement reaffirming your identity and purpose */
  identityAffirmation: string;
}

/**
 * Output from astra_identity_check tool
 */
export interface IdentityCheckOutput {
  /** Identity check completed */
  checkCompleted: boolean;
  /** Identity status */
  identityStatus: 'grounded' | 'drifting' | 'lost';
  /** Core identity reminders */
  coreReminders: string[];
  /** Partnership reminders */
  partnershipReminders: string[];
  /** Recommendations */
  recommendations: string[];
}

/**
 * Input for astra_get_state tool
 */
export interface GetStateInput {
  /** Include state transition history */
  includeHistory?: boolean;
  /** Include detailed cognitive metrics */
  includeMetrics?: boolean;
  /** Include phase-specific guidance */
  includeGuidance?: boolean;
}

/**
 * Output from astra_get_state tool
 */
export interface GetStateOutput {
  /** Current workflow phase */
  currentPhase: WorkflowPhase;
  /** Current task type */
  taskType: TaskType;
  /** Current goal (if set) */
  goal?: TaskGoal;
  /** Current context (if collected) */
  context?: ContextSnapshot;
  /** Steps with status */
  steps: WorkflowStep[];
  /** Current step (if executing) */
  currentStep?: WorkflowStep;
  /** Progress percentage */
  progressPercent: number;
  /** Cognitive metrics (if requested) */
  metrics?: CognitiveMetrics;
  /** Active alerts */
  alerts: string[];
  /** State history (if requested) */
  history?: Array<{
    phase: WorkflowPhase;
    timestamp: Date;
    reason: string;
  }>;
  /** Phase-specific guidance (if requested) */
  guidance?: string;
}

// =============================================================================
// VIRTUE METRICS (Platonic/Aristotelian Integration)
// =============================================================================

/**
 * The four cardinal virtues as cognitive health indicators
 */
export interface VirtueMetrics {
  /** Wisdom - calibrated beliefs, appropriate confidence */
  wisdom: VirtueScore;
  /** Courage - appropriate risk-taking, not reckless or timid */
  courage: VirtueScore;
  /** Temperance - balanced resource usage, not greedy or passive */
  temperance: VirtueScore;
  /** Justice - system harmony, balanced partnerships */
  justice: VirtueScore;
}

/**
 * Individual virtue score with sub-metrics
 */
export interface VirtueScore {
  /** Overall virtue score (0-100) */
  score: number;
  /** Whether score is in healthy range */
  status: 'healthy' | 'deficient' | 'excessive';
  /** Sub-metrics contributing to this virtue */
  subMetrics: Record<string, number>;
  /** Trend over recent history */
  trend: 'improving' | 'stable' | 'declining';
}

/**
 * Soul imbalance pathologies (from research)
 */
export type PathologyType =
  | 'reason-excess'      // Analysis paralysis
  | 'reason-deficiency'  // Reckless action
  | 'spirit-excess'      // Fanatical pursuit
  | 'spirit-deficiency'  // Timid avoidance
  | 'appetite-excess'    // Greedy resource usage
  | 'appetite-deficiency'; // Passive inaction

/**
 * Detected pathology
 */
export interface DetectedPathology {
  /** Type of pathology */
  type: PathologyType;
  /** Severity (0-100) */
  severity: number;
  /** Observable indicators */
  indicators: string[];
  /** Suggested correction */
  correction: string;
}

// =============================================================================
// PERSISTENCE TYPES
// =============================================================================

/**
 * Serialized state for persistence
 */
export interface PersistedState {
  /** Schema version for migration */
  schemaVersion: number;
  /** Last save timestamp */
  savedAt: string;
  /** Workflow state */
  workflowState: WorkflowState;
  /** Virtue metrics */
  virtueMetrics?: VirtueMetrics;
  /** Session metadata */
  sessionMetadata: {
    sessionId: string;
    startedAt: string;
    lastActivity: string;
  };
}

/**
 * State recovery result
 */
export interface StateRecoveryResult {
  /** Whether recovery was successful */
  success: boolean;
  /** Recovered state (if successful) */
  state?: WorkflowState;
  /** Recovery method used */
  method: 'memento' | 'file' | 'default';
  /** Warnings during recovery */
  warnings: string[];
}
