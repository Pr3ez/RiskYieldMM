/**
 * Astra Workflow - Instruction Injector
 *
 * Injects workflow state and reminders into copilot instructions.
 * Works with the .github/copilot-instructions.md file.
 * 
 * COORDINATION WITH OTHER EXTENSIONS:
 * - Agent TODOs injects <todos> block at TOP of file
 * - Agent Memory injects TL;DR summary (auto-sync)
 * - Astra injects <astra-workflow> section AFTER </todos> if present
 * 
 * Based on research from 02-AGENT-MEMORY.md and 03-AGENT-TODOS.md
 */

import * as vscode from "vscode";
import * as path from "path";
import { WorkflowStateMachine, VirtueGateResult } from "./stateMachine.js";
import { WorkflowPhase, TaskType, VirtueMetrics, DetectedPathology } from "./types.js";
import { CognitiveMetricsMonitor, MetricAlert } from "./metricsMonitor.js";

// =============================================================================
// INSTRUCTION TEMPLATES
// =============================================================================

const PHASE_INSTRUCTIONS: Record<WorkflowPhase, string> = {
  [WorkflowPhase.IDLE]: `
## ⏸️ WORKFLOW: IDLE
No active task. Waiting for input.
When starting a new task, FIRST run the Value Gate check.
`,

  [WorkflowPhase.VALUE_GATE]: `
## 🚪 WORKFLOW: VALUE GATE
**Ask these questions before proceeding:**
1. "If I succeed, what is the concrete benefit?"
2. "Is this the simplest way to achieve that benefit?"
3. "What happens if I don't do this?" (If "nothing" → STOP)

**Do NOT proceed until value is justified.**
`,

  [WorkflowPhase.GOAL_DEFINITION]: `
## 🎯 WORKFLOW: GOAL DEFINITION
**State the goal in ONE clear sentence.**
Required:
- Success condition: How I'll know it worked
- Failure condition: How I'll know it failed
- Time budget (optional)

**Do NOT proceed without a written goal.**
`,

  [WorkflowPhase.CONTEXT_COLLECTION]: `
## 📚 WORKFLOW: CONTEXT COLLECTION
**Gather all relevant information:**
- Check /memories/session.md
- Check /memories/knowledge/patterns.md
- Check /memories/knowledge/mistakes.md

**List explicitly:**
- KNOWN: [facts]
- UNKNOWN: [gaps]
- ASSUMPTIONS: [labeled guesses]

**Do NOT proceed with missing critical context.**
`,

  [WorkflowPhase.ENVIRONMENT_PRIMING]: `
## 🔧 WORKFLOW: ENVIRONMENT PRIMING
**Verify workspace is ready:**
- All required tools available
- No distracting files/tabs
- Dependencies resolved

**Do NOT start execution with cluttered environment.**
`,

  [WorkflowPhase.PLANNING]: `
## 📝 WORKFLOW: PLANNING
**Create a TODO plan with atomic steps.**
Each step must define:
- What will be done
- Expected output
- Validation method
- Estimated effort

**RECURSIVE RULE:** If step >2 hours or complex, treat as sub-project.

**Do NOT proceed without written plan.**
`,

  [WorkflowPhase.EXECUTING]: `
## ⚡ WORKFLOW: EXECUTING
**For each step:**
1. Confirm prerequisites
2. Create rollback point if risky
3. Mark step in_progress
4. Do the work
5. IMMEDIATELY verify result
6. Mark step complete

**Only ONE step in_progress at a time.**
`,

  [WorkflowPhase.VALIDATING]: `
## ✅ WORKFLOW: VALIDATING
**Validate the step using:**
- Tests (automated or manual)
- Small controlled examples
- Cross-checks against trusted sources
- Logical consistency checks

**At least ONE validation must be logically independent.**

**No validation = work is incomplete.**
`,

  [WorkflowPhase.MEMORY_CHECK]: `
## 🧠 WORKFLOW: MEMORY CHECK
**Review:**
1. /memories/session.md - is it current?
2. Any learnings to add to patterns.md?
3. Any mistakes to add to mistakes.md?
4. Should context be updated?

**Do NOT continue without memory check.**
`,

  [WorkflowPhase.DRIFT_CHECK]: `
## 🎯 WORKFLOW: DRIFT CHECK
**Ask yourself:**
1. Does this still serve the original goal?
2. Am I solving the original problem or a different one?
3. Have I added features not in the original goal?
4. Am I optimizing something that doesn't need optimization?
5. Is perfectionism blocking completion?
6. Have I been working >2x estimated time?

**If YES to any → STOP and reassess.**
`,

  [WorkflowPhase.COMPLETING]: `
## 🏁 WORKFLOW: COMPLETING
**Final checklist:**
- [ ] All steps completed and validated
- [ ] Original success condition met
- [ ] Documentation updated
- [ ] Learnings recorded
- [ ] session.md updated
- [ ] Estimation accuracy reviewed

**Do NOT claim "done" without completing checklist.**
`,

  [WorkflowPhase.BLOCKED]: `
## 🚫 WORKFLOW: BLOCKED
**Execution is BLOCKED.**
**Required actions:**
1. State clearly what is blocking
2. State what information is missing
3. Ask for guidance (don't guess)
4. If no response: Switch to Plan B or park task

**Do NOT proceed under uncertainty.**
`,

  [WorkflowPhase.ERROR_RECOVERY]: `
## ⚠️ WORKFLOW: ERROR RECOVERY
**Error encountered. Recovery steps:**
1. STOP and assess impact
2. How far back does error reach?
3. Choose: Rollback | Patch | Restart
4. Document what went wrong and why
5. Add prevention rule

**Do NOT continue without understanding the error.**
`,
};

// =============================================================================
// INSTRUCTION INJECTOR
// =============================================================================

export class InstructionInjector {
  // Old markers for backward compatibility
  private static readonly WORKFLOW_MARKER_START = "<!-- ASTRA_WORKFLOW_START -->";
  private static readonly WORKFLOW_MARKER_END = "<!-- ASTRA_WORKFLOW_END -->";
  
  // New XML-style markers (match Agent TODOs pattern)
  private static readonly ASTRA_TAG_START = "<astra-workflow>";
  private static readonly ASTRA_TAG_END = "</astra-workflow>";
  private static readonly TODOS_TAG_END = "</todos>";

  /**
   * Get the copilot instructions file path
   */
  private static getInstructionsPath(workspaceFolder: vscode.WorkspaceFolder): string {
    return path.join(workspaceFolder.uri.fsPath, ".github", "copilot-instructions.md");
  }

  /**
   * Generate passive reminder based on current phase
   */
  static generatePassiveReminder(phase: WorkflowPhase): string {
    const reminders: Record<WorkflowPhase, string> = {
      [WorkflowPhase.IDLE]: '⏸️ No task active. Run value gate before starting.',
      [WorkflowPhase.VALUE_GATE]: '🚪 VALUE GATE: Ask "Is this worth doing?" before proceeding.',
      [WorkflowPhase.GOAL_DEFINITION]: '🎯 GOAL: Define ONE clear goal with success/failure conditions.',
      [WorkflowPhase.CONTEXT_COLLECTION]: '📚 CONTEXT: Gather KNOWN facts, UNKNOWN gaps, ASSUMPTIONS.',
      [WorkflowPhase.ENVIRONMENT_PRIMING]: '🔧 ENV: Ensure workspace is ready before execution.',
      [WorkflowPhase.PLANNING]: '📝 PLAN: Create atomic steps with validation methods.',
      [WorkflowPhase.EXECUTING]: '⚡ EXEC: Mark step in_progress → Do work → Validate → Complete.',
      [WorkflowPhase.VALIDATING]: '✅ VALIDATE: At least ONE validation must be logically independent.',
      [WorkflowPhase.MEMORY_CHECK]: '🧠 MEMORY: Check session.md, patterns.md, mistakes.md.',
      [WorkflowPhase.DRIFT_CHECK]: '🎯 DRIFT: Does current work still serve original goal?',
      [WorkflowPhase.COMPLETING]: '🏁 COMPLETE: Run final checklist before claiming done.',
      [WorkflowPhase.BLOCKED]: '🚫 BLOCKED: State what is needed, ask for guidance.',
      [WorkflowPhase.ERROR_RECOVERY]: '⚠️ ERROR: Stop, assess, document, prevent recurrence.',
    };
    return reminders[phase] || '';
  }

  /**
   * Generate virtue status summary
   */
  static generateVirtueStatus(virtueMetrics: VirtueMetrics): string {
    const statusIcon = (status: string) => {
      switch (status) {
        case 'healthy': return '✅';
        case 'deficient': return '⚠️';
        case 'excessive': return '🔴';
        default: return '❓';
      }
    };

    return [
      `${statusIcon(virtueMetrics.wisdom.status)} Wisdom: ${virtueMetrics.wisdom.score}`,
      `${statusIcon(virtueMetrics.courage.status)} Courage: ${virtueMetrics.courage.score}`,
      `${statusIcon(virtueMetrics.temperance.status)} Temperance: ${virtueMetrics.temperance.score}`,
      `${statusIcon(virtueMetrics.justice.status)} Justice: ${virtueMetrics.justice.score}`,
    ].join(' | ');
  }

  /**
   * Generate pathology warnings
   */
  static generatePathologyWarnings(pathologies: DetectedPathology[]): string {
    if (pathologies.length === 0) return '';
    
    const warnings = pathologies.map(p => {
      const severityIcon = p.severity > 70 ? '🔴' : p.severity > 50 ? '🟠' : '🟡';
      return `${severityIcon} **${p.type}** (severity: ${p.severity}): ${p.correction}`;
    });
    
    return `\n**⚠️ PATHOLOGY WARNINGS:**\n${warnings.join('\n')}\n`;
  }

  /**
   * Generate <astra-workflow> XML section
   * This format coordinates with Agent TODOs' <todos> section
   */
  static generateAstraWorkflowSection(
    stateMachine: WorkflowStateMachine,
    alerts: MetricAlert[],
    virtueMetrics?: VirtueMetrics,
    pathologies?: DetectedPathology[]
  ): string {
    const state = stateMachine.getState();
    const passiveReminder = this.generatePassiveReminder(state.phase);
    
    let content = `${this.ASTRA_TAG_START}\n`;
    
    // Phase and passive reminder
    content += `## 📍 Phase: ${state.phase}\n`;
    content += `${passiveReminder}\n\n`;
    
    // Virtue metrics (if available)
    if (virtueMetrics) {
      content += `**Virtues:** ${this.generateVirtueStatus(virtueMetrics)}\n`;
    }
    
    // Pathology warnings
    if (pathologies && pathologies.length > 0) {
      content += this.generatePathologyWarnings(pathologies);
    }

    // Current task info
    if (state.goal) {
      content += `\n### Goal\n`;
      content += `**${state.goal.statement}**\n`;
      content += `- ✅ Success: ${state.goal.successCondition}\n`;
      content += `- ❌ Failure: ${state.goal.failureCondition}\n`;
    }

    // Current step
    const currentStep = stateMachine.getCurrentStep();
    if (currentStep) {
      content += `\n### Active Step\n`;
      content += `**[${currentStep.id}] ${currentStep.title}** - ${currentStep.status}\n`;
    }

    // Progress
    if (state.steps.length > 0) {
      const completed = state.steps.filter((s) => s.status === "completed").length;
      const blocked = state.steps.filter((s) => s.status === "blocked").length;
      content += `\n### Progress\n`;
      content += `✅ ${completed}/${state.steps.length} complete`;
      if (blocked > 0) content += ` | 🚫 ${blocked} blocked`;
      content += '\n';
    }

    // Alerts
    if (alerts.length > 0) {
      content += `\n### ⚠️ Alerts\n`;
      for (const alert of alerts) {
        const icon = alert.severity === "critical" ? "🔴" : "🟡";
        content += `${icon} **${alert.metric}**: ${alert.suggestion}\n`;
      }
    }

    // Watchdog timers
    const strictness = stateMachine.getStrictness();
    if (state.stepsSinceDriftCheck >= strictness.driftCheckInterval) {
      content += `\n🎯 **DRIFT CHECK DUE** - ${state.stepsSinceDriftCheck} steps since last check\n`;
    }
    if (state.stepsSinceMemoryCheck >= strictness.memoryCheckInterval) {
      content += `\n🧠 **MEMORY CHECK DUE** - ${state.stepsSinceMemoryCheck} steps since last check\n`;
    }

    content += `\n${this.ASTRA_TAG_END}`;
    return content;
  }

  /**
   * Generate workflow section content (legacy format for backward compatibility)
   */
  static generateWorkflowSection(
    stateMachine: WorkflowStateMachine,
    alerts: MetricAlert[]
  ): string {
    const state = stateMachine.getState();
    let content = `${this.WORKFLOW_MARKER_START}\n`;

    // Current phase instruction
    content += PHASE_INSTRUCTIONS[state.phase] ?? "";

    // Current task info
    if (state.goal) {
      content += `\n### Current Goal\n`;
      content += `**${state.goal.statement}**\n`;
      content += `- Success: ${state.goal.successCondition}\n`;
      content += `- Failure: ${state.goal.failureCondition}\n`;
      if (state.goal.timeBudget) {
        content += `- Time budget: ${state.goal.timeBudget} minutes\n`;
      }
    }

    // Current step
    const currentStep = stateMachine.getCurrentStep();
    if (currentStep) {
      content += `\n### Current Step\n`;
      content += `**[${currentStep.id}] ${currentStep.title}**\n`;
      content += `${currentStep.description}\n`;
      if (currentStep.validationMethod) {
        content += `- Validation: ${currentStep.validationMethod}\n`;
      }
    }

    // Progress
    if (state.steps.length > 0) {
      const completed = state.steps.filter((s) => s.status === "completed").length;
      content += `\n### Progress: ${completed}/${state.steps.length} steps\n`;
    }

    // Alerts
    if (alerts.length > 0) {
      content += `\n### ⚠️ ALERTS\n`;
      for (const alert of alerts) {
        const icon = alert.severity === "critical" ? "🔴" : "🟡";
        content += `${icon} **${alert.metric}**: ${alert.description}\n`;
        content += `   → ${alert.suggestion}\n`;
      }
    }

    // Counters
    content += `\n### Workflow Counters\n`;
    content += `- Steps since drift check: ${state.stepsSinceDriftCheck}\n`;
    content += `- Steps since memory check: ${state.stepsSinceMemoryCheck}\n`;

    content += `\n${this.WORKFLOW_MARKER_END}`;
    return content;
  }

  /**
   * Find the best insertion point for <astra-workflow>
   * Priority: After </todos> > After title > At start
   */
  private static findInsertionPoint(content: string): number {
    // First choice: After </todos> (coordinate with Agent TODOs)
    const todosEndIdx = content.indexOf(this.TODOS_TAG_END);
    if (todosEndIdx !== -1) {
      return todosEndIdx + this.TODOS_TAG_END.length;
    }
    
    // Second choice: After title (# heading) and first paragraph
    const titleEnd = content.indexOf("\n\n");
    if (titleEnd !== -1) {
      return titleEnd + 2;
    }
    
    // Last resort: At the start
    return 0;
  }

  /**
   * Inject <astra-workflow> section into copilot instructions
   * Coordinates with Agent TODOs by inserting AFTER </todos>
   */
  static async injectAstraSection(
    workspaceFolder: vscode.WorkspaceFolder,
    stateMachine: WorkflowStateMachine,
    metricsMonitor: CognitiveMetricsMonitor,
    virtueMetrics?: VirtueMetrics,
    pathologies?: DetectedPathology[]
  ): Promise<void> {
    const instructionsPath = this.getInstructionsPath(workspaceFolder);
    const uri = vscode.Uri.file(instructionsPath);

    // Read existing content
    let content = "";
    try {
      const fileContent = await vscode.workspace.fs.readFile(uri);
      content = Buffer.from(fileContent).toString("utf8");
    } catch {
      // File doesn't exist, create with basic structure
      content = "# Copilot Instructions\n\n";
    }

    // Generate new astra section
    const alerts = metricsMonitor.checkHealth(stateMachine.getState().metrics);
    const astraSection = this.generateAstraWorkflowSection(
      stateMachine, 
      alerts, 
      virtueMetrics, 
      pathologies
    );

    // Remove existing astra section (if present)
    const astraStartIdx = content.indexOf(this.ASTRA_TAG_START);
    const astraEndIdx = content.indexOf(this.ASTRA_TAG_END);
    
    if (astraStartIdx !== -1 && astraEndIdx !== -1) {
      content =
        content.substring(0, astraStartIdx) +
        content.substring(astraEndIdx + this.ASTRA_TAG_END.length);
      content = content.replace(/\n{3,}/g, "\n\n"); // Clean up extra newlines
    }

    // Also remove legacy markers if present
    const legacyStartIdx = content.indexOf(this.WORKFLOW_MARKER_START);
    const legacyEndIdx = content.indexOf(this.WORKFLOW_MARKER_END);
    
    if (legacyStartIdx !== -1 && legacyEndIdx !== -1) {
      content =
        content.substring(0, legacyStartIdx) +
        content.substring(legacyEndIdx + this.WORKFLOW_MARKER_END.length);
      content = content.replace(/\n{3,}/g, "\n\n");
    }

    // Find best insertion point
    const insertPoint = this.findInsertionPoint(content);
    
    // Insert new section
    content =
      content.substring(0, insertPoint) +
      "\n" + astraSection + "\n" +
      content.substring(insertPoint);

    // Ensure directory exists
    const dirPath = path.dirname(instructionsPath);
    try {
      await vscode.workspace.fs.createDirectory(vscode.Uri.file(dirPath));
    } catch {
      // Directory might already exist
    }

    // Write file
    await vscode.workspace.fs.writeFile(uri, Buffer.from(content, "utf8"));
  }

  /**
   * Inject workflow section into copilot instructions (legacy method)
   */
  static async injectWorkflowSection(
    workspaceFolder: vscode.WorkspaceFolder,
    stateMachine: WorkflowStateMachine,
    metricsMonitor: CognitiveMetricsMonitor
  ): Promise<void> {
    // Use new method with astra section
    await this.injectAstraSection(workspaceFolder, stateMachine, metricsMonitor);
  }

  /**
   * Remove workflow section from copilot instructions
   */
  static async removeWorkflowSection(
    workspaceFolder: vscode.WorkspaceFolder
  ): Promise<void> {
    const instructionsPath = this.getInstructionsPath(workspaceFolder);
    const uri = vscode.Uri.file(instructionsPath);

    try {
      const fileContent = await vscode.workspace.fs.readFile(uri);
      let content = Buffer.from(fileContent).toString("utf8");

      // Remove new astra-workflow section
      const astraStartIdx = content.indexOf(this.ASTRA_TAG_START);
      const astraEndIdx = content.indexOf(this.ASTRA_TAG_END);

      if (astraStartIdx !== -1 && astraEndIdx !== -1) {
        content =
          content.substring(0, astraStartIdx) +
          content.substring(astraEndIdx + this.ASTRA_TAG_END.length);
        content = content.replace(/\n{3,}/g, "\n\n");
      }

      // Also remove legacy markers
      const startIdx = content.indexOf(this.WORKFLOW_MARKER_START);
      const endIdx = content.indexOf(this.WORKFLOW_MARKER_END);

      if (startIdx !== -1 && endIdx !== -1) {
        content =
          content.substring(0, startIdx) +
          content.substring(endIdx + this.WORKFLOW_MARKER_END.length);
        content = content.replace(/\n{3,}/g, "\n\n");
      }

      await vscode.workspace.fs.writeFile(uri, Buffer.from(content, "utf8"));
    } catch {
      // File doesn't exist or can't be read
    }
  }
}

// =============================================================================
// TASK TYPE DETECTION
// =============================================================================

/**
 * Simple heuristics to detect task type from user input
 */
export function detectTaskType(input: string): TaskType {
  const lowered = input.toLowerCase();

  // Trivial: Quick questions
  const trivialPatterns = [
    /^what (is|are)/,
    /^how (do|can|to)/,
    /^where (is|are)/,
    /^when (did|do|should)/,
    /^why (is|are|did)/,
    /^show me/,
    /^list/,
    /^explain/,
  ];
  if (trivialPatterns.some((p) => p.test(lowered))) {
    return TaskType.TRIVIAL;
  }

  // Complex: Research, design, architecture
  const complexPatterns = [
    /research/,
    /investigate/,
    /design/,
    /architect/,
    /plan/,
    /strategy/,
    /optimize/,
    /refactor.*entire/,
    /rewrite/,
    /implement.*system/,
    /build.*from scratch/,
  ];
  if (complexPatterns.some((p) => p.test(lowered))) {
    return TaskType.COMPLEX;
  }

  // Simple: Single actions
  const simplePatterns = [
    /^fix/,
    /^add/,
    /^update/,
    /^change/,
    /^rename/,
    /^delete/,
    /^create.*file/,
  ];
  if (simplePatterns.some((p) => p.test(lowered))) {
    return TaskType.SIMPLE;
  }

  // Standard: Multi-step work
  const standardPatterns = [
    /implement/,
    /create/,
    /build/,
    /develop/,
    /write/,
    /generate/,
    /test/,
    /debug/,
  ];
  if (standardPatterns.some((p) => p.test(lowered))) {
    return TaskType.STANDARD;
  }

  return TaskType.UNKNOWN;
}
