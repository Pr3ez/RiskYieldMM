"use strict";
/**
 * Astra Workflow - Memory Integration
 *
 * Bridges the extension with Agent Memory tool via VS Code commands.
 * Handles session.md, patterns.md, and mistakes.md management.
 */
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
exports.WorkspaceMemory = exports.TodoIntegration = exports.MemoryIntegration = void 0;
const vscode = __importStar(require("vscode"));
const path = __importStar(require("path"));
// =============================================================================
// MEMORY PATHS
// =============================================================================
const MEMORY_PATHS = {
    session: "/memories/session.md",
    patterns: "/memories/knowledge/patterns.md",
    mistakes: "/memories/knowledge/mistakes.md",
    core: "/memories/core.md",
    przem: "/memories/przem.md",
};
// =============================================================================
// MEMORY INTEGRATION
// =============================================================================
class MemoryIntegration {
    memoryDir = null;
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
    buildSessionUpdate(state) {
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
                const icon = step.status === "completed"
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
    formatLearning(pattern, context, applicability) {
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
    formatMistake(description, rootCause, prevention) {
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
    getSessionUpdateCommands(state) {
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
    getMemoryViewCommand(path) {
        return `memory view ${MEMORY_PATHS[path]}`;
    }
    /**
     * Get memory insert command for new learning
     */
    getLearningInsertCommand(pattern, context, applicability) {
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
    getMistakeInsertCommand(description, rootCause, prevention) {
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
    getMemoryCheckReminder() {
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
    getDriftCheckReminder() {
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
exports.MemoryIntegration = MemoryIntegration;
class TodoIntegration {
    /**
     * Convert workflow steps to todo items
     */
    static stepsToTodos(steps, goalStatement) {
        return steps.map((step) => ({
            id: step.id,
            title: step.title,
            description: step.description,
            status: step.status === "completed"
                ? "completed"
                : step.status === "in-progress"
                    ? "in-progress"
                    : "not-started",
            priority: "high", // All workflow steps are high priority
            adr: step.validationMethod
                ? `Validation: ${step.validationMethod}`
                : undefined,
        }));
    }
    /**
     * Generate manage_todo_list write command
     */
    static generateTodoWriteCommand(todos, title) {
        return {
            operation: "write",
            title,
            todoList: todos,
        };
    }
    /**
     * Generate manage_todo_list read command
     */
    static generateTodoReadCommand() {
        return { operation: "read" };
    }
}
exports.TodoIntegration = TodoIntegration;
// =============================================================================
// WORKSPACE FILE OPERATIONS
// =============================================================================
class WorkspaceMemory {
    workspaceRoot;
    constructor(workspaceFolder) {
        this.workspaceRoot = workspaceFolder.uri.fsPath;
    }
    /**
     * Read a file from workspace
     */
    async readFile(relativePath) {
        try {
            const uri = vscode.Uri.file(path.join(this.workspaceRoot, relativePath));
            const content = await vscode.workspace.fs.readFile(uri);
            return Buffer.from(content).toString("utf8");
        }
        catch {
            return null;
        }
    }
    /**
     * Write a file to workspace
     */
    async writeFile(relativePath, content) {
        const uri = vscode.Uri.file(path.join(this.workspaceRoot, relativePath));
        // Ensure directory exists
        const dirPath = path.dirname(uri.fsPath);
        try {
            await vscode.workspace.fs.createDirectory(vscode.Uri.file(dirPath));
        }
        catch {
            // Directory might exist
        }
        await vscode.workspace.fs.writeFile(uri, Buffer.from(content, "utf8"));
    }
    /**
     * Append to a file in workspace
     */
    async appendFile(relativePath, content) {
        const existing = await this.readFile(relativePath);
        const newContent = existing ? `${existing}\n${content}` : content;
        await this.writeFile(relativePath, newContent);
    }
    /**
     * Check if file exists
     */
    async fileExists(relativePath) {
        try {
            const uri = vscode.Uri.file(path.join(this.workspaceRoot, relativePath));
            await vscode.workspace.fs.stat(uri);
            return true;
        }
        catch {
            return false;
        }
    }
}
exports.WorkspaceMemory = WorkspaceMemory;
//# sourceMappingURL=memoryIntegration.js.map