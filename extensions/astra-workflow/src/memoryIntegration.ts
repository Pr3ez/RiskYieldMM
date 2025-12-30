/**
 * Astra Workflow - Memory Integration
 *
 * Bridges the extension with Agent Memory tool via VS Code commands.
 * Handles session.md, patterns.md, and mistakes.md management.
 */

import * as vscode from "vscode";
import * as path from "path";
import { WorkflowState, WorkflowPhase, StepResult } from "./types.js";

// =============================================================================
// MEMORY PATHS
// =============================================================================

const MEMORY_PATHS = {
  session: "/memories/session.md",
  patterns: "/memories/knowledge/patterns.md",
  mistakes: "/memories/knowledge/mistakes.md",
  core: "/memories/core.md",
  przem: "/memories/przem.md",
} as const;

// =============================================================================
// SESSION STATE
// =============================================================================

export interface SessionState {
  lastUpdated: Date;
  currentTask?: string;
  workflowPhase: WorkflowPhase;
  stepProgress: string; // "3/7 steps"
  blockers?: string[];
  lastLearning?: string;
}

// =============================================================================
// MEMORY INTEGRATION
// =============================================================================

export class MemoryIntegration {
  private memoryDir: string | null = null;

  constructor() {
    // Memory directory is typically at project root level
    const workspaceFolder = vscode.workspace.workspaceFolders?.[0];
    if (workspaceFolder) {
      // Agent Memory tool uses /memories/ as root - we need to work with that
      // The tool handles the actual path resolution
      this.memoryDir = "/memories";
    }
  }

  // ===========================================================================
  // SESSION.MD MANAGEMENT
  // ===========================================================================

  /**
   * Build session update content from workflow state
   */
  buildSessionUpdate(state: WorkflowState): string {
    const now = new Date().toISOString();
    let content = `# Session State\n\n`;
    content += `**Updated:** ${now}\n\n`;

    // Current phase
    content += `## Workflow Phase\n`;
    content += `\`${state.phase}\`\n\n`;

    // Goal
    if (state.goal) {
      content += `## Current Goal\n`;
      content += `${state.goal.statement}\n\n`;
      content += `- **Success:** ${state.goal.successCondition}\n`;
      content += `- **Failure:** ${state.goal.failureCondition}\n`;
      if (state.goal.timeBudget) {
        content += `- **Budget:** ${state.goal.timeBudget} minutes\n`;
      }
      content += `\n`;
    }

    // Steps progress
    if (state.steps.length > 0) {
      const completed = state.steps.filter((s) => s.status === "completed").length;
      const inProgress = state.steps.find((s) => s.status === "in-progress");

      content += `## Progress: ${completed}/${state.steps.length}\n\n`;

      for (const step of state.steps) {
        const icon =
          step.status === "completed"
            ? "✅"
            : step.status === "in-progress"
              ? "🔄"
              : "⬜";
        content += `${icon} **${step.id}:** ${step.title}\n`;
      }
      content += `\n`;

      if (inProgress) {
        content += `### Currently Working On\n`;
        content += `${inProgress.description}\n\n`;
      }
    }

    // Metrics
    content += `## Cognitive Metrics\n`;
    content += `- Steps since drift check: ${state.stepsSinceDriftCheck}\n`;
    content += `- Steps since memory check: ${state.stepsSinceMemoryCheck}\n`;
    content += `- Verification failures: ${state.metrics.verificationFailures}\n\n`;

    // Current error (if any)
    if (state.error) {
      content += `## Current Error\n`;
      content += `${state.error}\n\n`;
    }

    // Blocker (if any)
    if (state.blocker) {
      content += `## Blocker\n`;
      content += `${state.blocker}\n\n`;
    }

    return content;
  }

  /**
   * Format learning for patterns.md
   */
  formatLearning(
    pattern: string,
    context: string,
    applicability: string
  ): string {
    const now = new Date().toISOString().split("T")[0];
    return `
### ${pattern}
**Date:** ${now}
**Context:** ${context}
**Applicability:** ${applicability}
`;
  }

  /**
   * Format mistake for mistakes.md
   */
  formatMistake(
    description: string,
    rootCause: string,
    prevention: string
  ): string {
    const now = new Date().toISOString().split("T")[0];
    return `
### ${description}
**Date:** ${now}
**Root Cause:** ${rootCause}
**Prevention:** ${prevention}
`;
  }

  // ===========================================================================
  // MEMORY COMMANDS (via VS Code terminal - agent memory tool)
  // ===========================================================================

  /**
   * Generate memory tool commands for session update
   */
  getSessionUpdateCommands(state: WorkflowState): string[] {
    // These are conceptual - the actual implementation would work with the
    // Agent Memory extension's API or through Copilot's tool interface
    const content = this.buildSessionUpdate(state);
    return [
      `memory str_replace ${MEMORY_PATHS.session}`,
      `// Content to update:`,
      content,
    ];
  }

  /**
   * Get memory view command
   */
  getMemoryViewCommand(path: keyof typeof MEMORY_PATHS): string {
    return `memory view ${MEMORY_PATHS[path]}`;
  }

  /**
   * Get memory insert command for new learning
   */
  getLearningInsertCommand(
    pattern: string,
    context: string,
    applicability: string
  ): string[] {
    const content = this.formatLearning(pattern, context, applicability);
    return [
      `memory insert ${MEMORY_PATHS.patterns}`,
      `// Insert line: END`,
      content,
    ];
  }

  /**
   * Get memory insert command for new mistake
   */
  getMistakeInsertCommand(
    description: string,
    rootCause: string,
    prevention: string
  ): string[] {
    const content = this.formatMistake(description, rootCause, prevention);
    return [
      `memory insert ${MEMORY_PATHS.mistakes}`,
      `// Insert line: END`,
      content,
    ];
  }

  // ===========================================================================
  // REMINDERS
  // ===========================================================================

  /**
   * Get memory check reminder content
   */
  getMemoryCheckReminder(): string {
    return `
## 🧠 MEMORY CHECK REQUIRED

Run these memory checks:
1. \`memory view ${MEMORY_PATHS.session}\` - Update if stale
2. \`memory view ${MEMORY_PATHS.patterns}\` - Any new patterns learned?
3. \`memory view ${MEMORY_PATHS.mistakes}\` - Any mistakes to record?

**Do NOT continue without completing memory hygiene.**
`;
  }

  /**
   * Get drift check reminder content
   */
  getDriftCheckReminder(): string {
    return `
## 🎯 DRIFT CHECK REQUIRED

Ask yourself:
1. Does this still serve the **original goal**?
2. Am I solving the **original problem** or a different one?
3. Have I added features **not in the original goal**?
4. Am I **optimizing** something that doesn't need it?
5. Is **perfectionism** blocking completion?

**If YES to any → STOP and reassess.**
`;
  }
}

// =============================================================================
// TODO INTEGRATION (via Agent TODOs)
// =============================================================================

export interface TodoItem {
  id: string;
  title: string;
  description: string;
  status: "not-started" | "in-progress" | "completed";
  priority: "low" | "medium" | "high";
  adr?: string;
}

export class TodoIntegration {
  /**
   * Convert workflow steps to todo items
   */
  static stepsToTodos(
    steps: WorkflowState["steps"],
    goalStatement: string
  ): TodoItem[] {
    return steps.map((step) => ({
      id: step.id,
      title: step.title,
      description: step.description,
      status:
        step.status === "completed"
          ? ("completed" as const)
          : step.status === "in-progress"
            ? ("in-progress" as const)
            : ("not-started" as const),
      priority: "high" as const, // All workflow steps are high priority
      adr: step.validationMethod
        ? `Validation: ${step.validationMethod}`
        : undefined,
    }));
  }

  /**
   * Generate manage_todo_list write command
   */
  static generateTodoWriteCommand(
    todos: TodoItem[],
    title: string
  ): {
    operation: "write";
    title: string;
    todoList: TodoItem[];
  } {
    return {
      operation: "write",
      title,
      todoList: todos,
    };
  }

  /**
   * Generate manage_todo_list read command
   */
  static generateTodoReadCommand(): { operation: "read" } {
    return { operation: "read" };
  }
}

// =============================================================================
// WORKSPACE FILE OPERATIONS
// =============================================================================

export class WorkspaceMemory {
  private workspaceRoot: string;

  constructor(workspaceFolder: vscode.WorkspaceFolder) {
    this.workspaceRoot = workspaceFolder.uri.fsPath;
  }

  /**
   * Read a file from workspace
   */
  async readFile(relativePath: string): Promise<string | null> {
    try {
      const uri = vscode.Uri.file(path.join(this.workspaceRoot, relativePath));
      const content = await vscode.workspace.fs.readFile(uri);
      return Buffer.from(content).toString("utf8");
    } catch {
      return null;
    }
  }

  /**
   * Write a file to workspace
   */
  async writeFile(relativePath: string, content: string): Promise<void> {
    const uri = vscode.Uri.file(path.join(this.workspaceRoot, relativePath));

    // Ensure directory exists
    const dirPath = path.dirname(uri.fsPath);
    try {
      await vscode.workspace.fs.createDirectory(vscode.Uri.file(dirPath));
    } catch {
      // Directory might exist
    }

    await vscode.workspace.fs.writeFile(uri, Buffer.from(content, "utf8"));
  }

  /**
   * Append to a file in workspace
   */
  async appendFile(relativePath: string, content: string): Promise<void> {
    const existing = await this.readFile(relativePath);
    const newContent = existing ? `${existing}\n${content}` : content;
    await this.writeFile(relativePath, newContent);
  }

  /**
   * Check if file exists
   */
  async fileExists(relativePath: string): Promise<boolean> {
    try {
      const uri = vscode.Uri.file(path.join(this.workspaceRoot, relativePath));
      await vscode.workspace.fs.stat(uri);
      return true;
    } catch {
      return false;
    }
  }
}
