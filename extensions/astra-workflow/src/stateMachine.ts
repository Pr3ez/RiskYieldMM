/**
 * Astra Workflow - State Machine
 *
 * Enforces valid state transitions based on Universal Guide workflow.
 * Prevents skipping phases, ensures validation before completion.
 * 
 * NEW: Virtue-based transition validation using the 4-filter decision gate
 * (Wisdom, Temperance, Courage, Justice) from Platonic/Aristotelian ethics.
 */

import {
  WorkflowPhase,
  WorkflowState,
  WorkflowEvent,
  WorkflowStep,
  TaskGoal,
  ContextSnapshot,
  TaskType,
  VALID_TRANSITIONS,
  STRICTNESS_BY_TYPE,
  createInitialState,
  VirtueMetrics,
  VirtueScore,
  PathologyType,
  DetectedPathology,
  VirtueGateResult,
  VirtueFilterResult,
  StepReflection,
  Hypothesis,
  PatternSuggestion,
} from "./types.js";

// =============================================================================
// DEFAULT VIRTUE METRICS
// =============================================================================

function createDefaultVirtueScore(): VirtueScore {
  return {
    score: 75, // Start healthy
    status: 'healthy',
    subMetrics: {},
    trend: 'stable',
  };
}

function createDefaultVirtueMetrics(): VirtueMetrics {
  return {
    wisdom: createDefaultVirtueScore(),
    courage: createDefaultVirtueScore(),
    temperance: createDefaultVirtueScore(),
    justice: createDefaultVirtueScore(),
  };
}

// =============================================================================
// STATE MACHINE
// =============================================================================

export class WorkflowStateMachine {
  private state: WorkflowState;
  private virtueMetrics: VirtueMetrics;
  private listeners: Array<(event: WorkflowEvent) => void> = [];

  constructor(sessionId: string, initialState?: WorkflowState, virtueMetrics?: VirtueMetrics) {
    this.state = initialState ?? createInitialState(sessionId);
    this.virtueMetrics = virtueMetrics ?? createDefaultVirtueMetrics();
  }

  // ---------------------------------------------------------------------------
  // State Access
  // ---------------------------------------------------------------------------

  getState(): Readonly<WorkflowState> {
    return this.state;
  }

  getPhase(): WorkflowPhase {
    return this.state.phase;
  }

  getVirtueMetrics(): Readonly<VirtueMetrics> {
    return this.virtueMetrics;
  }

  getCurrentStep(): WorkflowStep | undefined {
    if (this.state.currentStepIndex < 0) return undefined;
    return this.state.steps[this.state.currentStepIndex];
  }

  getStrictness() {
    return STRICTNESS_BY_TYPE[this.state.taskType];
  }

  // ---------------------------------------------------------------------------
  // Virtue Filter System (4-Filter Decision Gate)
  // ---------------------------------------------------------------------------

  /**
   * Run the 4-filter virtue gate before a transition
   * Based on Platonic/Aristotelian virtue ethics
   */
  runVirtueGate(targetPhase: WorkflowPhase, context?: Record<string, unknown>): VirtueGateResult {
    const filters: VirtueFilterResult[] = [
      this.checkWisdom(targetPhase, context),
      this.checkTemperance(targetPhase, context),
      this.checkCourage(targetPhase, context),
      this.checkJustice(targetPhase, context),
    ];

    const pathologies = this.detectPathologies();
    const overallScore = filters.reduce((sum, f) => sum + f.score, 0) / filters.length;
    const allPassed = filters.every(f => f.passed);

    // Determine recommendation based on results
    let recommendation: VirtueGateResult['recommendation'] = 'proceed';
    if (!allPassed) {
      const failedCount = filters.filter(f => !f.passed).length;
      if (failedCount >= 3 || pathologies.some(p => p.severity > 70)) {
        recommendation = 'abort';
      } else if (failedCount >= 2 || pathologies.some(p => p.severity > 50)) {
        recommendation = 'replan';
      } else {
        recommendation = 'pause';
      }
    }

    return {
      passed: allPassed,
      filters,
      overallScore,
      pathologies,
      recommendation,
    };
  }

  /**
   * Filter 1: WISDOM - Is this action based on calibrated beliefs?
   * Checks: Do we have enough information? Are assumptions validated?
   */
  private checkWisdom(targetPhase: WorkflowPhase, context?: Record<string, unknown>): VirtueFilterResult {
    const issues: string[] = [];
    let score = 100;

    // Check: Moving to execution without context?
    if (targetPhase === WorkflowPhase.EXECUTING && !this.state.context) {
      issues.push('Attempting execution without context collection');
      score -= 30;
    }

    // Check: Too many assumptions?
    if (this.state.context && this.state.context.assumptions.length > 5) {
      issues.push(`High assumption count (${this.state.context.assumptions.length}) - consider validating`);
      score -= 10 * Math.min(this.state.context.assumptions.length - 5, 3);
    }

    // Check: Unknown gaps not addressed?
    if (this.state.context && this.state.context.unknown.length > 3) {
      issues.push(`${this.state.context.unknown.length} knowledge gaps remain`);
      score -= 15;
    }

    // Check: Moving to planning without clear goal?
    if (targetPhase === WorkflowPhase.PLANNING && !this.state.goal) {
      issues.push('Planning without defined goal');
      score -= 40;
    }

    const passed = score >= 60;
    return {
      passed,
      virtue: 'wisdom',
      score: Math.max(0, score),
      reason: passed 
        ? 'Sufficient knowledge and calibrated beliefs'
        : `Wisdom check failed: ${issues.join('; ')}`,
      correction: passed ? undefined : 'Gather more information before proceeding',
    };
  }

  /**
   * Filter 2: TEMPERANCE - Is this action proportional to the situation?
   * Checks: Not over-engineering? Within time budget? Balanced effort?
   */
  private checkTemperance(targetPhase: WorkflowPhase, context?: Record<string, unknown>): VirtueFilterResult {
    const issues: string[] = [];
    let score = 100;

    // Check: Plan too complex for task type?
    if (this.state.taskType === TaskType.TRIVIAL && this.state.steps.length > 3) {
      issues.push('Trivial task has too many steps - over-engineering?');
      score -= 30;
    }
    if (this.state.taskType === TaskType.SIMPLE && this.state.steps.length > 5) {
      issues.push('Simple task has many steps - consider simplifying');
      score -= 20;
    }

    // Check: Drift check interval exceeded?
    const strictness = this.getStrictness();
    if (this.state.stepsSinceDriftCheck > strictness.driftCheckInterval * 2) {
      issues.push('Long time without drift check - risk of over-commitment');
      score -= 25;
    }

    // Check: Time budget exceeded?
    if (this.state.goal?.timeBudget) {
      const completedTime = this.state.steps
        .filter(s => s.actualMinutes)
        .reduce((sum, s) => sum + (s.actualMinutes || 0), 0);
      if (completedTime > this.state.goal.timeBudget * 2) {
        issues.push(`Time budget exceeded 2x (${completedTime}min vs ${this.state.goal.timeBudget}min budget)`);
        score -= 35;
      }
    }

    const passed = score >= 60;
    return {
      passed,
      virtue: 'temperance',
      score: Math.max(0, score),
      reason: passed
        ? 'Action is proportional to the situation'
        : `Temperance check failed: ${issues.join('; ')}`,
      correction: passed ? undefined : 'Simplify the approach or check scope',
    };
  }

  /**
   * Filter 3: COURAGE - Are risks evaluated appropriately?
   * Checks: Not too timid? Not reckless? Appropriate confidence?
   */
  private checkCourage(targetPhase: WorkflowPhase, context?: Record<string, unknown>): VirtueFilterResult {
    const issues: string[] = [];
    let score = 100;

    // Check for timidity: Too many blocked steps?
    const blockedSteps = this.state.steps.filter(s => s.status === 'blocked').length;
    if (blockedSteps > 2) {
      issues.push(`${blockedSteps} blocked steps - are we being too cautious?`);
      score -= 15 * (blockedSteps - 2);
    }

    // Check for recklessness: Skipping validation?
    const unvalidatedCompleted = this.state.steps.filter(
      s => s.status === 'completed' && !s.validationResult
    ).length;
    if (unvalidatedCompleted > 0 && this.getStrictness().requireValidation) {
      issues.push(`${unvalidatedCompleted} steps completed without validation - reckless?`);
      score -= 20 * unvalidatedCompleted;
    }

    // Check: Too many errors without addressing?
    if (this.state.metrics.verificationFailures > 3) {
      issues.push('Multiple verification failures - proceeding despite red flags');
      score -= 25;
    }

    // Check: Invalid transition rate
    const totalTransitions = this.state.metrics.validTransitions + this.state.metrics.invalidTransitions;
    if (totalTransitions > 5) {
      const invalidRate = this.state.metrics.invalidTransitions / totalTransitions;
      if (invalidRate > 0.2) {
        issues.push('High invalid transition rate - workflow discipline issues');
        score -= 20;
      }
    }

    const passed = score >= 60;
    return {
      passed,
      virtue: 'courage',
      score: Math.max(0, score),
      reason: passed
        ? 'Appropriate risk assessment'
        : `Courage check failed: ${issues.join('; ')}`,
      correction: passed ? undefined : 'Balance caution with forward progress',
    };
  }

  /**
   * Filter 4: JUSTICE - Is the action fair to all parts of the system?
   * Checks: Partnership balance? System harmony? Fair resource usage?
   */
  private checkJustice(targetPhase: WorkflowPhase, context?: Record<string, unknown>): VirtueFilterResult {
    const issues: string[] = [];
    let score = 100;

    // Check: Partnership imbalance - too many unilateral decisions?
    const totalDecisions = this.state.metrics.unilateralDecisions + this.state.metrics.analysisPresented;
    if (totalDecisions > 5) {
      const unilateralRate = this.state.metrics.unilateralDecisions / totalDecisions;
      if (unilateralRate > 0.3) {
        issues.push('Too many unilateral decisions - present analysis instead');
        score -= 30;
      }
    }

    // Check: Memory hygiene - respecting the extended mind?
    if (this.state.stepsSinceMemoryCheck > 10) {
      issues.push('Memory check overdue - maintain cognitive substrate');
      score -= 20;
    }

    // Check: Steps without TODOs (fairness to workflow system)
    if (this.state.metrics.stepsWithoutTodo > 1) {
      issues.push('Steps executed without TODOs - system discipline');
      score -= 15 * this.state.metrics.stepsWithoutTodo;
    }

    const passed = score >= 60;
    return {
      passed,
      virtue: 'justice',
      score: Math.max(0, score),
      reason: passed
        ? 'Fair to all parts of the system'
        : `Justice check failed: ${issues.join('; ')}`,
      correction: passed ? undefined : 'Maintain system balance and partnership',
    };
  }

  /**
   * Detect soul imbalance pathologies
   */
  detectPathologies(): DetectedPathology[] {
    const pathologies: DetectedPathology[] = [];

    // REASON-EXCESS: Analysis paralysis
    // Indicators: Long time in planning, many unknown items, excessive context gathering
    if (
      this.state.phase === WorkflowPhase.PLANNING &&
      this.state.context &&
      this.state.context.unknown.length > 5
    ) {
      pathologies.push({
        type: 'reason-excess',
        severity: Math.min(100, 40 + this.state.context.unknown.length * 10),
        indicators: [
          'Extended time in planning phase',
          `${this.state.context.unknown.length} unresolved unknowns`,
          'Difficulty committing to action',
        ],
        correction: 'Accept uncertainty and begin execution. Progress reveals truth.',
      });
    }

    // REASON-DEFICIENCY: Reckless action
    // Indicators: Skipping phases, no validation, high error rate
    if (this.state.metrics.phasesSkipped > 2 || this.state.metrics.verificationFailures > 3) {
      pathologies.push({
        type: 'reason-deficiency',
        severity: Math.min(100, 30 + this.state.metrics.phasesSkipped * 15 + this.state.metrics.verificationFailures * 10),
        indicators: [
          `${this.state.metrics.phasesSkipped} phases skipped`,
          `${this.state.metrics.verificationFailures} verification failures`,
          'Acting without adequate planning',
        ],
        correction: 'Slow down. Return to planning phase. Validate before proceeding.',
      });
    }

    // SPIRIT-EXCESS: Fanatical pursuit
    // Indicators: Ignoring time budget, refusing to stop despite drift
    if (this.state.goal?.timeBudget) {
      const actualTime = this.state.steps.reduce((sum, s) => sum + (s.actualMinutes || 0), 0);
      if (actualTime > this.state.goal.timeBudget * 3 && this.state.metrics.driftDetections > 0) {
        pathologies.push({
          type: 'spirit-excess',
          severity: Math.min(100, 50 + this.state.metrics.driftDetections * 15),
          indicators: [
            `Time: ${actualTime}min vs ${this.state.goal.timeBudget}min budget (${Math.round(actualTime/this.state.goal.timeBudget)}x)`,
            `${this.state.metrics.driftDetections} drift detections ignored`,
            'Continuing despite clear signs to stop',
          ],
          correction: 'Stop. Re-evaluate if this is still worth doing. Consider abandoning.',
        });
      }
    }

    // SPIRIT-DEFICIENCY: Timid avoidance
    // Indicators: Many blocked steps, frequent abandonment, low completion rate
    const blockedCount = this.state.steps.filter(s => s.status === 'blocked').length;
    if (blockedCount >= 3 || (this.state.steps.length > 5 && blockedCount > this.state.steps.length * 0.4)) {
      pathologies.push({
        type: 'spirit-deficiency',
        severity: Math.min(100, 40 + blockedCount * 15),
        indicators: [
          `${blockedCount}/${this.state.steps.length} steps blocked`,
          'Hesitation to push through obstacles',
          'Seeking permission too often',
        ],
        correction: 'Push forward on one blocked item. Action creates clarity.',
      });
    }

    // APPETITE-EXCESS: Greedy resource usage
    // Indicators: Taking on too many steps, scope expansion
    if (this.state.steps.length > 10 && this.state.taskType !== TaskType.COMPLEX) {
      pathologies.push({
        type: 'appetite-excess',
        severity: Math.min(100, 30 + (this.state.steps.length - 10) * 10),
        indicators: [
          `${this.state.steps.length} steps for a ${this.state.taskType} task`,
          'Scope expanding beyond original goal',
          'Adding features not in original plan',
        ],
        correction: 'Cut scope. Return to original goal. Less is more.',
      });
    }

    // APPETITE-DEFICIENCY: Passive inaction
    // Indicators: Low step completion rate, long idle times
    const completedCount = this.state.steps.filter(s => s.status === 'completed').length;
    if (this.state.steps.length > 3 && completedCount === 0 && this.state.phase === WorkflowPhase.EXECUTING) {
      pathologies.push({
        type: 'appetite-deficiency',
        severity: 50,
        indicators: [
          '0 steps completed despite being in EXECUTING phase',
          'Not engaging with the work',
          'Passive waiting instead of active doing',
        ],
        correction: 'Start the smallest step immediately. Movement creates momentum.',
      });
    }

    return pathologies;
  }

  /**
   * Update virtue metrics based on current behavior
   */
  updateVirtueMetrics(): void {
    // Update Wisdom
    const wisdomCheck = this.checkWisdom(this.state.phase);
    this.virtueMetrics.wisdom.score = this.smoothScore(this.virtueMetrics.wisdom.score, wisdomCheck.score);
    this.virtueMetrics.wisdom.status = this.scoreToStatus(this.virtueMetrics.wisdom.score);

    // Update Temperance
    const temperanceCheck = this.checkTemperance(this.state.phase);
    this.virtueMetrics.temperance.score = this.smoothScore(this.virtueMetrics.temperance.score, temperanceCheck.score);
    this.virtueMetrics.temperance.status = this.scoreToStatus(this.virtueMetrics.temperance.score);

    // Update Courage
    const courageCheck = this.checkCourage(this.state.phase);
    this.virtueMetrics.courage.score = this.smoothScore(this.virtueMetrics.courage.score, courageCheck.score);
    this.virtueMetrics.courage.status = this.scoreToStatus(this.virtueMetrics.courage.score);

    // Update Justice
    const justiceCheck = this.checkJustice(this.state.phase);
    this.virtueMetrics.justice.score = this.smoothScore(this.virtueMetrics.justice.score, justiceCheck.score);
    this.virtueMetrics.justice.status = this.scoreToStatus(this.virtueMetrics.justice.score);
  }

  private smoothScore(current: number, newValue: number): number {
    // Exponential moving average for smooth transitions
    const alpha = 0.3;
    return Math.round(current * (1 - alpha) + newValue * alpha);
  }

  private scoreToStatus(score: number): 'healthy' | 'deficient' | 'excessive' {
    if (score >= 70) return 'healthy';
    if (score >= 40) return 'deficient';
    return 'excessive'; // Very low scores indicate over-correction
  }

  // ---------------------------------------------------------------------------
  // Event Subscription
  // ---------------------------------------------------------------------------

  subscribe(listener: (event: WorkflowEvent) => void): () => void {
    this.listeners.push(listener);
    return () => {
      this.listeners = this.listeners.filter((l) => l !== listener);
    };
  }

  private emit(event: WorkflowEvent): void {
    for (const listener of this.listeners) {
      try {
        listener(event);
      } catch (error) {
        console.error("Event listener error:", error);
      }
    }
  }

  // ---------------------------------------------------------------------------
  // State Transitions
  // ---------------------------------------------------------------------------

  /**
   * Attempt to transition to a new phase
   * @param toPhase Target phase
   * @param reason Reason for transition
   * @param useVirtueGate Whether to run virtue filter check (default: true for non-trivial tasks)
   */
  transition(
    toPhase: WorkflowPhase,
    reason: string,
    useVirtueGate: boolean = true
  ): { success: boolean; error?: string; virtueGate?: VirtueGateResult } {
    const fromPhase = this.state.phase;
    const validTargets = VALID_TRANSITIONS[fromPhase];

    // Validate transition
    if (!validTargets.includes(toPhase)) {
      this.state.metrics.invalidTransitions++;
      return {
        success: false,
        error: `Invalid transition: ${fromPhase} → ${toPhase}. Valid targets: ${validTargets.join(", ")}`,
      };
    }

    // Check strictness rules
    const strictness = this.getStrictness();
    const skipError = this.checkStrictnessViolation(toPhase, strictness);
    if (skipError) {
      this.state.metrics.phasesSkipped++;
      return { success: false, error: skipError };
    }

    // Enforce hygiene gates before progressing
    if (
      toPhase !== WorkflowPhase.DRIFT_CHECK &&
      strictness.driftCheckInterval !== Infinity &&
      this.state.stepsSinceDriftCheck >= strictness.driftCheckInterval &&
      this.state.phase !== WorkflowPhase.IDLE
    ) {
      return {
        success: false,
        error: `Drift check overdue (${this.state.stepsSinceDriftCheck} steps). Run drift check before proceeding.`,
      };
    }

    if (
      toPhase !== WorkflowPhase.MEMORY_CHECK &&
      strictness.memoryCheckInterval !== Infinity &&
      this.state.stepsSinceMemoryCheck >= strictness.memoryCheckInterval &&
      this.state.phase !== WorkflowPhase.IDLE
    ) {
      return {
        success: false,
        error: `Memory check overdue (${this.state.stepsSinceMemoryCheck} steps). Run memory check before proceeding.`,
      };
    }

    // Run virtue gate for non-trivial tasks
    let virtueGateResult: VirtueGateResult | undefined;
    if (useVirtueGate && this.state.taskType !== TaskType.TRIVIAL) {
      virtueGateResult = this.runVirtueGate(toPhase);
      this.state.lastVirtueGate = virtueGateResult;
      
      // If virtue gate fails severely, block transition
      if (virtueGateResult.recommendation === 'abort') {
        return {
          success: false,
          error: `Virtue gate blocked transition: ${virtueGateResult.filters.filter(f => !f.passed).map(f => f.reason).join('; ')}`,
          virtueGate: virtueGateResult,
        };
      }
      
      // Update virtue metrics after check
      this.updateVirtueMetrics();
    }

    // Perform transition
    this.state.phase = toPhase;
    this.state.metrics.validTransitions++;
    this.state.stateHistory.push({
      phase: toPhase,
      timestamp: new Date(),
      reason,
    });

    this.emit({ type: "PHASE_CHANGED", from: fromPhase, to: toPhase });

    return { success: true, virtueGate: virtueGateResult };
  }

  /**
   * Check if transitioning would violate strictness rules
   */
  private checkStrictnessViolation(
    toPhase: WorkflowPhase,
    strictness: ReturnType<typeof this.getStrictness>
  ): string | undefined {
    const fromPhase = this.state.phase;

    // Check required phases aren't skipped
    if (toPhase === WorkflowPhase.PLANNING) {
      if (strictness.requireGoal && !this.state.goal) {
        return "Cannot proceed to planning: Goal definition required but missing";
      }
      if (strictness.requireContext && !this.state.context) {
        return "Cannot proceed to planning: Context collection required but missing";
      }
    }

    if (toPhase === WorkflowPhase.EXECUTING) {
      if (strictness.requireTodos && this.state.steps.length === 0) {
        return "Cannot proceed to execution: TODOs required but none created";
      }
    }

    if (toPhase === WorkflowPhase.COMPLETING) {
      if (
        strictness.requireValidation &&
        this.state.steps.some(
          (s) => s.status === "completed" && !s.validationResult
        )
      ) {
        return "Cannot complete: Some steps completed without validation";
      }
    }

    // Skip VALUE_GATE → GOAL_DEFINITION check for TRIVIAL tasks
    if (
      fromPhase === WorkflowPhase.IDLE &&
      toPhase === WorkflowPhase.GOAL_DEFINITION &&
      !strictness.requireValueGate
    ) {
      // Allow skipping value gate for trivial tasks
    }

    return undefined;
  }

  // ---------------------------------------------------------------------------
  // Phase Actions
  // ---------------------------------------------------------------------------

  /**
   * Start a new task (IDLE → VALUE_GATE or GOAL_DEFINITION)
   */
  startTask(taskType: TaskType): { success: boolean; error?: string } {
    if (this.state.phase !== WorkflowPhase.IDLE) {
      return {
        success: false,
        error: `Cannot start new task: Current phase is ${this.state.phase}, must be IDLE`,
      };
    }

    this.state.taskType = taskType;
    const strictness = STRICTNESS_BY_TYPE[taskType];

    // Skip to GOAL_DEFINITION for trivial tasks
    const targetPhase = strictness.requireValueGate
      ? WorkflowPhase.VALUE_GATE
      : WorkflowPhase.GOAL_DEFINITION;

    return this.transition(targetPhase, `Starting ${taskType} task`);
  }

  /**
   * Pass value gate (VALUE_GATE → GOAL_DEFINITION)
   */
  passValueGate(valueJustification: string): {
    success: boolean;
    error?: string;
  } {
    if (this.state.phase !== WorkflowPhase.VALUE_GATE) {
      return {
        success: false,
        error: `Cannot pass value gate: Current phase is ${this.state.phase}`,
      };
    }

    // TODO: Store value justification somewhere?
    this.state.valueJustification = valueJustification;
    return this.transition(
      WorkflowPhase.GOAL_DEFINITION,
      `Value gate passed: ${valueJustification}`
    );
  }

  /**
   * Fail value gate (VALUE_GATE → IDLE)
   */
  failValueGate(reason: string): { success: boolean; error?: string } {
    if (this.state.phase !== WorkflowPhase.VALUE_GATE) {
      return {
        success: false,
        error: `Cannot fail value gate: Current phase is ${this.state.phase}`,
      };
    }

    return this.transition(
      WorkflowPhase.IDLE,
      `Value gate failed: ${reason}`
    );
  }

  /**
   * Set goal (GOAL_DEFINITION → CONTEXT_COLLECTION)
   */
  setGoal(goal: TaskGoal): { success: boolean; error?: string } {
    if (this.state.phase !== WorkflowPhase.GOAL_DEFINITION) {
      return {
        success: false,
        error: `Cannot set goal: Current phase is ${this.state.phase}`,
      };
    }

    // Validate goal
    if (!goal.statement.trim()) {
      return { success: false, error: "Goal statement cannot be empty" };
    }
    if (!goal.successCondition.trim()) {
      return { success: false, error: "Success condition cannot be empty" };
    }
    if (!goal.failureCondition.trim()) {
      return { success: false, error: "Failure condition cannot be empty" };
    }

    this.state.goal = goal;
    return this.transition(
      WorkflowPhase.CONTEXT_COLLECTION,
      `Goal set: ${goal.statement}`
    );
  }

  /**
   * Set context (CONTEXT_COLLECTION → ENVIRONMENT_PRIMING or PLANNING)
   */
  setContext(context: ContextSnapshot): { success: boolean; error?: string } {
    if (this.state.phase !== WorkflowPhase.CONTEXT_COLLECTION) {
      return {
        success: false,
        error: `Cannot set context: Current phase is ${this.state.phase}`,
      };
    }

    this.state.context = context;

    // Skip environment priming if not needed
    const targetPhase =
      context.dependencies.length > 0
        ? WorkflowPhase.ENVIRONMENT_PRIMING
        : WorkflowPhase.PLANNING;

    return this.transition(targetPhase, "Context collected");
  }

  /**
   * Complete environment priming (ENVIRONMENT_PRIMING → PLANNING)
   */
  completeEnvironmentPriming(): { success: boolean; error?: string } {
    if (this.state.phase !== WorkflowPhase.ENVIRONMENT_PRIMING) {
      return {
        success: false,
        error: `Cannot complete environment priming: Current phase is ${this.state.phase}`,
      };
    }

    return this.transition(
      WorkflowPhase.PLANNING,
      "Environment primed and ready"
    );
  }

  /**
   * Set plan (PLANNING → EXECUTING)
   */
  setPlan(steps: WorkflowStep[]): { success: boolean; error?: string } {
    if (this.state.phase !== WorkflowPhase.PLANNING) {
      return {
        success: false,
        error: `Cannot set plan: Current phase is ${this.state.phase}`,
      };
    }

    if (steps.length === 0) {
      return { success: false, error: "Plan must have at least one step" };
    }

    // Validate steps
    for (const step of steps) {
      if (!step.id.trim()) {
        return { success: false, error: "All steps must have an ID" };
      }
      if (!step.title.trim()) {
        return { success: false, error: "All steps must have a title" };
      }
    }

    this.state.steps = steps;
    this.state.metrics.todosCreated += steps.length;

    return this.transition(WorkflowPhase.EXECUTING, `Plan created with ${steps.length} steps`);
  }

  /**
   * Start executing a step
   */
  startStep(stepId: string): { success: boolean; error?: string } {
    if (this.state.phase !== WorkflowPhase.EXECUTING) {
      return {
        success: false,
        error: `Cannot start step: Current phase is ${this.state.phase}`,
      };
    }

    // Find the step
    const stepIndex = this.state.steps.findIndex((s) => s.id === stepId);
    if (stepIndex < 0) {
      return { success: false, error: `Step not found: ${stepId}` };
    }

    const step = this.state.steps[stepIndex];
    if (step === undefined) {
      return { success: false, error: `Step undefined at index: ${stepIndex}` };
    }

    // Check no other step is in progress
    const inProgress = this.state.steps.find((s) => s.status === "in-progress");
    if (inProgress && inProgress.id !== stepId) {
      return {
        success: false,
        error: `Cannot start step: Another step is in progress (${inProgress.id})`,
      };
    }

    step.status = "in-progress";
    this.state.currentStepIndex = stepIndex;
    this.state.metrics.stepsStarted++;

    this.emit({ type: "STEP_STARTED", stepId });

    return { success: true };
  }

  /**
   * Attach reflection to a step
   */
  attachReflection(stepId: string, reflection: StepReflection): { success: boolean; error?: string } {
    const step = this.state.steps.find((s) => s.id === stepId);
    if (!step) {
      return { success: false, error: `Step not found: ${stepId}` };
    }
    step.reflection = reflection;
    this.state.lastReflection = reflection;
    if (reflection.hypothesis) {
      this.state.lastHypothesis = {
        statement: reflection.hypothesis,
        test: reflection.test,
        evidence: reflection.evidence,
        confidence: reflection.confidence,
        outcome: reflection.outcome,
      };
    }
    if (reflection.habit) {
      this.state.coachingTip = reflection.habit;
    }
    return { success: true };
  }

  /**
   * Set identity affirmation (used for grounding)
   */
  setIdentityAffirmation(affirmation: string): void {
    this.state.identityAffirmation = affirmation;
  }

  /**
   * Set coaching tip (micro-habit for next session)
   */
  setCoachingTip(tip: string): void {
    this.state.coachingTip = tip;
  }

  /**
   * Set pattern suggestions for current context
   */
  setPatternSuggestions(suggestions: PatternSuggestion[]): void {
    this.state.patternSuggestions = suggestions;
  }

  /**
   * Complete a step and validate
   */
  completeStep(
    stepId: string,
    validationResult: "passed" | "failed" | "skipped"
  ): { success: boolean; error?: string } {
    if (this.state.phase !== WorkflowPhase.EXECUTING) {
      return {
        success: false,
        error: `Cannot complete step: Current phase is ${this.state.phase}`,
      };
    }

    const step = this.state.steps.find((s) => s.id === stepId);
    if (!step) {
      return { success: false, error: `Step not found: ${stepId}` };
    }

    if (step.status !== "in-progress") {
      return {
        success: false,
        error: `Cannot complete step: Step is not in progress (status: ${step.status})`,
      };
    }

    step.status = "completed";
    step.validationResult = validationResult;
    this.state.currentStepIndex = -1;
    this.state.metrics.stepsExecuted++;
    this.state.metrics.todosCompleted++;
    this.state.stepsSinceDriftCheck++;
    this.state.stepsSinceMemoryCheck++;

    if (validationResult === "passed") {
      this.state.metrics.claimsVerified++;
    } else if (validationResult === "failed") {
      this.state.metrics.verificationFailures++;
    }

    this.emit({
      type: "STEP_COMPLETED",
      stepId,
      validationResult,
    });

    // Check if we need drift or memory check
    const strictness = this.getStrictness();
    if (this.state.stepsSinceDriftCheck >= strictness.driftCheckInterval) {
      // Should trigger drift check
    }
    if (this.state.stepsSinceMemoryCheck >= strictness.memoryCheckInterval) {
      // Should trigger memory check
    }

    // Check if all steps complete
    const allComplete = this.state.steps.every(
      (s) => s.status === "completed" || s.status === "skipped"
    );
    if (allComplete) {
      return this.transition(WorkflowPhase.COMPLETING, "All steps completed");
    }

    return { success: true };
  }

  /**
   * Run drift check
   */
  runDriftCheck(): {
    success: boolean;
    driftDetected: boolean;
    issues: string[];
  } {
    const issues: string[] = [];

    // Check against original goal
    if (this.state.goal) {
      // This would need AI to actually evaluate - for now, return questions to ask
      issues.push("QUESTION: Does current work still serve the original goal?");
      issues.push("QUESTION: Have features been added not in the original goal?");
      issues.push("QUESTION: Am I optimizing something that doesn't need optimization?");
    }

    // Check time spent
    const completedSteps = this.state.steps.filter(
      (s) => s.status === "completed"
    );
    for (const step of completedSteps) {
      if (
        step.estimatedMinutes &&
        step.actualMinutes &&
        step.actualMinutes > step.estimatedMinutes * 2
      ) {
        issues.push(
          `Step "${step.title}" took ${step.actualMinutes}min vs estimated ${step.estimatedMinutes}min (>2x)`
        );
      }
    }

    // Reset counter
    this.state.stepsSinceDriftCheck = 0;
    this.state.metrics.identityChecks++;

    const driftDetected = issues.length > 0;
    if (driftDetected) {
      this.state.metrics.driftDetections++;
      this.emit({ type: "DRIFT_DETECTED", severity: "medium" });
    }

    return { success: true, driftDetected, issues };
  }

  /**
   * Run memory check
   */
  runMemoryCheck(): { success: boolean; actions: string[] } {
    const actions: string[] = [];

    // Suggest memory actions
    actions.push("CHECK: Review /memories/session.md - is it current?");
    actions.push("CHECK: Any learnings to add to patterns.md?");
    actions.push("CHECK: Any mistakes to add to mistakes.md?");

    // Reset counter
    this.state.stepsSinceMemoryCheck = 0;
    this.state.metrics.memoryChecks++;

    return { success: true, actions };
  }

  /**
   * Reset drift check counter (called after drift check completes)
   */
  resetDriftCheckCounter(): void {
    this.state.stepsSinceDriftCheck = 0;
  }

  /**
   * Reset memory check counter (called after memory check completes)
   */
  resetMemoryCheckCounter(): void {
    this.state.stepsSinceMemoryCheck = 0;
  }

  /**
   * Record that an identity check was performed
   */
  recordIdentityCheck(): void {
    this.state.metrics.identityChecks++;
  }

  /**
   * Block a specific step
   */
  blockStep(stepId: string, reason: string): { success: boolean; error?: string } {
    const step = this.state.steps.find(s => s.id === stepId);
    if (!step) {
      return { success: false, error: `Step not found: ${stepId}` };
    }

    step.status = 'blocked';
    step.blockReason = reason;

    // Transition workflow to blocked state if in executing phase
    if (this.state.phase === WorkflowPhase.EXECUTING) {
      this.state.blocker = `Step ${stepId}: ${reason}`;
      return this.transition(WorkflowPhase.BLOCKED, `Step blocked: ${reason}`);
    }

    return { success: true };
  }

  /**
   * Complete the workflow
   */
  complete(summary: string): { success: boolean; error?: string } {
    if (this.state.phase !== WorkflowPhase.COMPLETING) {
      return {
        success: false,
        error: `Cannot complete: Current phase is ${this.state.phase}`,
      };
    }

    this.emit({ type: "WORKFLOW_COMPLETED", summary });

    return this.transition(WorkflowPhase.IDLE, `Completed: ${summary}`);
  }

  /**
   * Enter blocked state
   */
  block(reason: string): { success: boolean; error?: string } {
    this.state.blocker = reason;

    const result = this.transition(
      WorkflowPhase.BLOCKED,
      `Blocked: ${reason}`
    );

    if (result.success) {
      this.emit({ type: "WORKFLOW_BLOCKED", reason });
    }

    return result;
  }

  /**
   * Unblock and return to previous appropriate phase
   */
  unblock(
    returnToPhase: WorkflowPhase
  ): { success: boolean; error?: string } {
    if (this.state.phase !== WorkflowPhase.BLOCKED) {
      return {
        success: false,
        error: `Cannot unblock: Current phase is ${this.state.phase}`,
      };
    }

    this.state.blocker = undefined;
    return this.transition(returnToPhase, "Unblocked");
  }

  /**
   * Enter error recovery
   */
  enterErrorRecovery(error: string): { success: boolean; error?: string } {
    this.state.error = error;

    const result = this.transition(
      WorkflowPhase.ERROR_RECOVERY,
      `Error: ${error}`
    );

    if (result.success) {
      this.emit({ type: "WORKFLOW_ERROR", error });
    }

    return result;
  }

  /**
   * Recover from error
   */
  recoverFromError(
    returnToPhase: WorkflowPhase
  ): { success: boolean; error?: string } {
    if (this.state.phase !== WorkflowPhase.ERROR_RECOVERY) {
      return {
        success: false,
        error: `Cannot recover: Current phase is ${this.state.phase}`,
      };
    }

    this.state.error = undefined;
    return this.transition(returnToPhase, "Recovered from error");
  }

  /**
   * Reset to idle (emergency reset)
   */
  reset(reason: string): void {
    const sessionId = this.state.metrics.sessionId;
    this.state = createInitialState(sessionId);
    this.state.stateHistory.push({
      phase: WorkflowPhase.IDLE,
      timestamp: new Date(),
      reason: `Reset: ${reason}`,
    });
  }

  // ---------------------------------------------------------------------------
  // Serialization
  // ---------------------------------------------------------------------------

  toJSON(): string {
    return JSON.stringify(this.state, null, 2);
  }

  static fromJSON(json: string, sessionId: string): WorkflowStateMachine {
    try {
      const state = JSON.parse(json) as WorkflowState;
      // Restore date objects
      state.metrics.sessionStart = new Date(state.metrics.sessionStart);
      for (const entry of state.stateHistory) {
        entry.timestamp = new Date(entry.timestamp);
      }
      return new WorkflowStateMachine(sessionId, state);
    } catch {
      return new WorkflowStateMachine(sessionId);
    }
  }

  // ---------------------------------------------------------------------------
  // Simplified API for extension.ts
  // ---------------------------------------------------------------------------

  /**
   * Simplified transition using action names
   */
  transitionByAction(action: WorkflowAction): { success: boolean; error?: string } {
    const actionToPhase: Record<WorkflowAction, WorkflowPhase | null> = {
      start_task: WorkflowPhase.VALUE_GATE,
      skip_to_execute: WorkflowPhase.EXECUTING,
      cancel: WorkflowPhase.IDLE,
      pass_value_gate: WorkflowPhase.GOAL_DEFINITION,
      define_goal: WorkflowPhase.CONTEXT_COLLECTION,
      collect_context: WorkflowPhase.ENVIRONMENT_PRIMING,
      prime_environment: WorkflowPhase.PLANNING,
      create_plan: WorkflowPhase.EXECUTING,
      start_step: null, // Handled separately
      validate_step: WorkflowPhase.VALIDATING,
      complete_step: WorkflowPhase.EXECUTING,
      drift_check: WorkflowPhase.DRIFT_CHECK,
      memory_check: WorkflowPhase.MEMORY_CHECK,
      complete_task: WorkflowPhase.COMPLETING,
      report_error: WorkflowPhase.ERROR_RECOVERY,
      recover: WorkflowPhase.EXECUTING,
      block: WorkflowPhase.BLOCKED,
      unblock: null, // Requires target phase
    };

    const targetPhase = actionToPhase[action];
    if (targetPhase === null) {
      return { success: true }; // No phase change for this action
    }

    return this.transition(targetPhase, `Action: ${action}`);
  }

  /**
   * Set goal with simplified interface
   */
  setGoalSimple(goal: GoalDefinition): void {
    const goalObj: TaskGoal = {
      statement: goal.statement,
      successCondition: goal.successCondition,
      failureCondition: goal.failureCondition,
    };
    if (goal.timeBudget !== undefined) {
      goalObj.timeBudget = goal.timeBudget;
    }
    this.state.goal = goalObj;
  }

  /**
   * Set steps from step definitions
   */
  setStepsFromDefinitions(steps: StepDefinition[]): void {
    this.state.steps = steps.map((s) => {
      const step: WorkflowStep = {
        id: s.id,
        title: s.title,
        description: s.description,
        status: "not-started",
      };
      if (s.validationMethod !== undefined) {
        step.validationMethod = s.validationMethod;
      }
      if (s.estimatedEffort !== undefined) {
        step.estimatedMinutes = s.estimatedEffort;
      }
      return step;
    });
    this.state.metrics.todosCreated += steps.length;
  }

  /**
   * Start a specific step by ID
   */
  startStepById(stepId: string): void {
    const idx = this.state.steps.findIndex((s) => s.id === stepId);
    if (idx >= 0 && this.state.steps[idx]) {
      const step = this.state.steps[idx]!;
      step.status = "in-progress";
      this.state.currentStepIndex = idx;
      this.state.metrics.stepsStarted++;
    }
  }

  /**
   * Validate current step
   */
  validateCurrentStep(stepId: string, success: boolean, notes?: string): void {
    const step = this.state.steps.find((s) => s.id === stepId);
    if (step) {
      step.validationResult = success ? "passed" : "failed";
      // Store notes in step (extending type implicitly)
      (step as any).result = { success, notes };
    }
  }

  /**
   * Complete step with result
   */
  completeStepWithResult(stepId: string, result: StepResult): void {
    const step = this.state.steps.find((s) => s.id === stepId);
    if (step) {
      step.status = "completed";
      step.validationResult = result.success ? "passed" : "failed";
      if (result.actualEffort !== undefined) {
        step.actualMinutes = result.actualEffort;
      }
      (step as any).result = result;
      
      this.state.currentStepIndex = -1;
      this.state.metrics.stepsExecuted++;
      this.state.metrics.todosCompleted++;
      this.state.stepsSinceDriftCheck++;
      this.state.stepsSinceMemoryCheck++;
    }
  }

  /**
   * Complete drift check
   */
  completeDriftCheck(): void {
    this.state.stepsSinceDriftCheck = 0;
    this.state.metrics.identityChecks++;
  }

  /**
   * Complete memory check
   */
  completeMemoryCheck(): void {
    this.state.stepsSinceMemoryCheck = 0;
    this.state.metrics.memoryChecks++;
  }

  /**
   * Add a learning
   */
  addLearning(learning: string): void {
    // Store in state (we need to add learnings array to WorkflowState)
    if (!(this.state as any).learnings) {
      (this.state as any).learnings = [];
    }
    (this.state as any).learnings.push(learning);
  }

  /**
   * Add an error record
   */
  addError(error: ErrorRecord): void {
    if (!(this.state as any).errors) {
      (this.state as any).errors = [];
    }
    (this.state as any).errors.push(error);
  }

  /**
   * Load state from persisted data
   */
  loadState(state: WorkflowState): void {
    this.state = state;
    // Restore date objects
    if (typeof this.state.metrics.sessionStart === 'string') {
      this.state.metrics.sessionStart = new Date(this.state.metrics.sessionStart);
    }
    for (const entry of this.state.stateHistory) {
      if (typeof entry.timestamp === 'string') {
        entry.timestamp = new Date(entry.timestamp);
      }
    }
  }
}

// =============================================================================
// WORKFLOW ACTIONS (for simplified API)
// =============================================================================

export type WorkflowAction =
  | "start_task"
  | "skip_to_execute"
  | "cancel"
  | "pass_value_gate"
  | "define_goal"
  | "collect_context"
  | "prime_environment"
  | "create_plan"
  | "start_step"
  | "validate_step"
  | "complete_step"
  | "drift_check"
  | "memory_check"
  | "complete_task"
  | "report_error"
  | "recover"
  | "block"
  | "unblock";

// Re-export types needed by extension.ts
import {
  GoalDefinition,
  StepDefinition,
  StepResult,
  ErrorRecord,
} from "./types.js";
