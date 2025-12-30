/**
 * Astra Workflow - Persistence Layer
 *
 * Dual-write system combining:
 * 1. VS Code Memento API (workspaceState) - fast, runtime state
 * 2. File-based storage - AI-visible, recoverable state
 *
 * Based on research findings from 05-STATE-PERSISTENCE.md:
 * - Memento for runtime (survives extension reload)
 * - File for AI visibility (readable in prompts)
 * - Corruption handling with graceful degradation
 */
import * as vscode from 'vscode';
import { WorkflowState, VirtueMetrics, StateRecoveryResult } from './types.js';
export declare class PersistenceManager {
    private context;
    private workspaceFolder;
    constructor(context: vscode.ExtensionContext);
    /**
     * Save state to Memento (workspaceState)
     */
    saveToMemento(state: WorkflowState, virtueMetrics?: VirtueMetrics): Promise<void>;
    /**
     * Load state from Memento
     */
    loadFromMemento(): StateRecoveryResult;
    /**
     * Clear Memento state
     */
    clearMemento(): Promise<void>;
    /**
     * Get path to state file in workspace
     */
    private getStateFilePath;
    /**
     * Save state to file (for AI visibility)
     */
    saveToFile(state: WorkflowState, virtueMetrics?: VirtueMetrics): Promise<void>;
    /**
     * Load state from file
     */
    loadFromFile(): Promise<StateRecoveryResult>;
    /**
     * Delete state file
     */
    clearFile(): Promise<void>;
    /**
     * Save state to both Memento and file (dual-write)
     */
    save(state: WorkflowState, virtueMetrics?: VirtueMetrics): Promise<void>;
    /**
     * Load state with fallback chain: Memento → File → Default
     */
    load(sessionId: string): Promise<StateRecoveryResult>;
    /**
     * Clear all persisted state
     */
    clear(): Promise<void>;
    /**
     * Restore proper Date objects from serialized state
     */
    private hydrateState;
    /**
     * Get last session metadata
     */
    getLastSessionMetadata(): {
        sessionId: string;
        lastActivity: string;
    } | undefined;
    /**
     * Check if there's a recent session (within last hour)
     */
    hasRecentSession(): boolean;
    /**
     * Check if session.md needs update based on state staleness
     */
    checkSessionMdFreshness(): Promise<'current' | 'stale' | 'missing'>;
}
export declare function createPersistenceManager(context: vscode.ExtensionContext): PersistenceManager;
export declare function getPersistenceManager(): PersistenceManager | undefined;
//# sourceMappingURL=persistence.d.ts.map