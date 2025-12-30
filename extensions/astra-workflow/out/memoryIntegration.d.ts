/**
 * Astra Workflow - Memory Integration
 *
 * Bridges the extension with Agent Memory tool via VS Code commands.
 * Handles session.md, patterns.md, and mistakes.md management.
 */
import * as vscode from "vscode";
import { WorkflowState, WorkflowPhase } from "./types.js";
declare const MEMORY_PATHS: {
    readonly session: "/memories/session.md";
    readonly patterns: "/memories/knowledge/patterns.md";
    readonly mistakes: "/memories/knowledge/mistakes.md";
    readonly core: "/memories/core.md";
    readonly przem: "/memories/przem.md";
};
export interface SessionState {
    lastUpdated: Date;
    currentTask?: string;
    workflowPhase: WorkflowPhase;
    stepProgress: string;
    blockers?: string[];
    lastLearning?: string;
}
export declare class MemoryIntegration {
    private memoryDir;
    constructor();
    /**
     * Build session update content from workflow state
     */
    buildSessionUpdate(state: WorkflowState): string;
    /**
     * Format learning for patterns.md
     */
    formatLearning(pattern: string, context: string, applicability: string): string;
    /**
     * Format mistake for mistakes.md
     */
    formatMistake(description: string, rootCause: string, prevention: string): string;
    /**
     * Generate memory tool commands for session update
     */
    getSessionUpdateCommands(state: WorkflowState): string[];
    /**
     * Get memory view command
     */
    getMemoryViewCommand(path: keyof typeof MEMORY_PATHS): string;
    /**
     * Get memory insert command for new learning
     */
    getLearningInsertCommand(pattern: string, context: string, applicability: string): string[];
    /**
     * Get memory insert command for new mistake
     */
    getMistakeInsertCommand(description: string, rootCause: string, prevention: string): string[];
    /**
     * Get memory check reminder content
     */
    getMemoryCheckReminder(): string;
    /**
     * Get drift check reminder content
     */
    getDriftCheckReminder(): string;
}
export interface TodoItem {
    id: string;
    title: string;
    description: string;
    status: "not-started" | "in-progress" | "completed";
    priority: "low" | "medium" | "high";
    adr?: string;
}
export declare class TodoIntegration {
    /**
     * Convert workflow steps to todo items
     */
    static stepsToTodos(steps: WorkflowState["steps"], goalStatement: string): TodoItem[];
    /**
     * Generate manage_todo_list write command
     */
    static generateTodoWriteCommand(todos: TodoItem[], title: string): {
        operation: "write";
        title: string;
        todoList: TodoItem[];
    };
    /**
     * Generate manage_todo_list read command
     */
    static generateTodoReadCommand(): {
        operation: "read";
    };
}
export declare class WorkspaceMemory {
    private workspaceRoot;
    constructor(workspaceFolder: vscode.WorkspaceFolder);
    /**
     * Read a file from workspace
     */
    readFile(relativePath: string): Promise<string | null>;
    /**
     * Write a file to workspace
     */
    writeFile(relativePath: string, content: string): Promise<void>;
    /**
     * Append to a file in workspace
     */
    appendFile(relativePath: string, content: string): Promise<void>;
    /**
     * Check if file exists
     */
    fileExists(relativePath: string): Promise<boolean>;
}
export {};
//# sourceMappingURL=memoryIntegration.d.ts.map