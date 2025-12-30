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
import * as path from 'path';
import {
  WorkflowState,
  VirtueMetrics,
  PersistedState,
  StateRecoveryResult,
  createInitialState,
} from './types.js';

// =============================================================================
// CONSTANTS
// =============================================================================

const SCHEMA_VERSION = 1;
const STATE_KEY = 'astra.workflowState';
const VIRTUE_KEY = 'astra.virtueMetrics';
const SESSION_KEY = 'astra.sessionMetadata';

// =============================================================================
// PERSISTENCE MANAGER
// =============================================================================

export class PersistenceManager {
  private context: vscode.ExtensionContext;
  private workspaceFolder: string | undefined;

  constructor(context: vscode.ExtensionContext) {
    this.context = context;
    this.workspaceFolder = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
  }

  // ---------------------------------------------------------------------------
  // Memento Operations (Primary Storage)
  // ---------------------------------------------------------------------------

  /**
   * Save state to Memento (workspaceState)
   */
  async saveToMemento(state: WorkflowState, virtueMetrics?: VirtueMetrics): Promise<void> {
    try {
      const persistedState: PersistedState = {
        schemaVersion: SCHEMA_VERSION,
        savedAt: new Date().toISOString(),
        workflowState: state,
        virtueMetrics,
        sessionMetadata: {
          sessionId: state.metrics.sessionId,
          startedAt: state.metrics.sessionStart.toISOString(),
          lastActivity: new Date().toISOString(),
        },
      };

      await this.context.workspaceState.update(STATE_KEY, persistedState);
    } catch (error) {
      console.error('Failed to save to Memento:', error);
      throw new Error(`Memento save failed: ${error}`);
    }
  }

  /**
   * Load state from Memento
   */
  loadFromMemento(): StateRecoveryResult {
    try {
      const persisted = this.context.workspaceState.get<PersistedState>(STATE_KEY);
      
      if (!persisted) {
        return {
          success: false,
          method: 'memento',
          warnings: ['No persisted state found in Memento'],
        };
      }

      // Validate schema version
      if (persisted.schemaVersion !== SCHEMA_VERSION) {
        return {
          success: false,
          method: 'memento',
          warnings: [`Schema version mismatch: expected ${SCHEMA_VERSION}, got ${persisted.schemaVersion}`],
        };
      }

      // Restore state with proper date objects
      const state = this.hydrateState(persisted.workflowState);

      return {
        success: true,
        state,
        method: 'memento',
        warnings: [],
      };
    } catch (error) {
      return {
        success: false,
        method: 'memento',
        warnings: [`Memento load error: ${error}`],
      };
    }
  }

  /**
   * Clear Memento state
   */
  async clearMemento(): Promise<void> {
    await this.context.workspaceState.update(STATE_KEY, undefined);
    await this.context.workspaceState.update(VIRTUE_KEY, undefined);
    await this.context.workspaceState.update(SESSION_KEY, undefined);
  }

  // ---------------------------------------------------------------------------
  // File-Based Operations (AI-Visible Storage)
  // ---------------------------------------------------------------------------

  /**
   * Get path to state file in workspace
   */
  private getStateFilePath(): string | undefined {
    if (!this.workspaceFolder) return undefined;
    return path.join(this.workspaceFolder, '.astra', 'workflow-state.json');
  }

  /**
   * Save state to file (for AI visibility)
   */
  async saveToFile(state: WorkflowState, virtueMetrics?: VirtueMetrics): Promise<void> {
    const filePath = this.getStateFilePath();
    if (!filePath) {
      console.warn('No workspace folder - skipping file save');
      return;
    }

    try {
      const persistedState: PersistedState = {
        schemaVersion: SCHEMA_VERSION,
        savedAt: new Date().toISOString(),
        workflowState: state,
        virtueMetrics,
        sessionMetadata: {
          sessionId: state.metrics.sessionId,
          startedAt: state.metrics.sessionStart.toISOString(),
          lastActivity: new Date().toISOString(),
        },
      };

      const dirPath = path.dirname(filePath);
      const dirUri = vscode.Uri.file(dirPath);
      const fileUri = vscode.Uri.file(filePath);

      // Ensure directory exists
      try {
        await vscode.workspace.fs.createDirectory(dirUri);
      } catch {
        // Directory may already exist
      }

      // Write state file
      const content = JSON.stringify(persistedState, null, 2);
      await vscode.workspace.fs.writeFile(fileUri, Buffer.from(content, 'utf8'));
    } catch (error) {
      console.error('Failed to save to file:', error);
      // Don't throw - file save is secondary
    }
  }

  /**
   * Load state from file
   */
  async loadFromFile(): Promise<StateRecoveryResult> {
    const filePath = this.getStateFilePath();
    if (!filePath) {
      return {
        success: false,
        method: 'file',
        warnings: ['No workspace folder available'],
      };
    }

    try {
      const fileUri = vscode.Uri.file(filePath);
      const content = await vscode.workspace.fs.readFile(fileUri);
      const persisted = JSON.parse(content.toString()) as PersistedState;

      // Validate schema version
      if (persisted.schemaVersion !== SCHEMA_VERSION) {
        return {
          success: false,
          method: 'file',
          warnings: [`Schema version mismatch: expected ${SCHEMA_VERSION}, got ${persisted.schemaVersion}`],
        };
      }

      const state = this.hydrateState(persisted.workflowState);

      return {
        success: true,
        state,
        method: 'file',
        warnings: [],
      };
    } catch (error) {
      return {
        success: false,
        method: 'file',
        warnings: [`File load error: ${error}`],
      };
    }
  }

  /**
   * Delete state file
   */
  async clearFile(): Promise<void> {
    const filePath = this.getStateFilePath();
    if (!filePath) return;

    try {
      const fileUri = vscode.Uri.file(filePath);
      await vscode.workspace.fs.delete(fileUri);
    } catch {
      // File may not exist
    }
  }

  // ---------------------------------------------------------------------------
  // Dual-Write Operations
  // ---------------------------------------------------------------------------

  /**
   * Save state to both Memento and file (dual-write)
   */
  async save(state: WorkflowState, virtueMetrics?: VirtueMetrics): Promise<void> {
    // Primary: Memento (synchronous, reliable)
    await this.saveToMemento(state, virtueMetrics);

    // Secondary: File (async, AI-visible)
    // Don't await - file save is best-effort
    this.saveToFile(state, virtueMetrics).catch(err => {
      console.warn('File save failed (non-critical):', err);
    });
  }

  /**
   * Load state with fallback chain: Memento → File → Default
   */
  async load(sessionId: string): Promise<StateRecoveryResult> {
    // Try Memento first (fastest, most recent)
    const mementoResult = this.loadFromMemento();
    if (mementoResult.success && mementoResult.state) {
      return mementoResult;
    }

    // Try file as fallback
    const fileResult = await this.loadFromFile();
    if (fileResult.success && fileResult.state) {
      // Restore to Memento for consistency
      await this.saveToMemento(fileResult.state);
      return {
        ...fileResult,
        warnings: [...fileResult.warnings, 'Restored from file backup'],
      };
    }

    // Return default state
    return {
      success: true,
      state: createInitialState(sessionId),
      method: 'default',
      warnings: [
        ...mementoResult.warnings,
        ...fileResult.warnings,
        'No persisted state found - starting fresh',
      ],
    };
  }

  /**
   * Clear all persisted state
   */
  async clear(): Promise<void> {
    await this.clearMemento();
    await this.clearFile();
  }

  // ---------------------------------------------------------------------------
  // State Hydration (Restore Date Objects)
  // ---------------------------------------------------------------------------

  /**
   * Restore proper Date objects from serialized state
   */
  private hydrateState(state: WorkflowState): WorkflowState {
    // Clone to avoid mutating original
    const hydrated = JSON.parse(JSON.stringify(state)) as WorkflowState;

    // Restore sessionStart date
    if (typeof hydrated.metrics.sessionStart === 'string') {
      hydrated.metrics.sessionStart = new Date(hydrated.metrics.sessionStart);
    }

    // Restore stateHistory timestamps
    for (const entry of hydrated.stateHistory) {
      if (typeof entry.timestamp === 'string') {
        entry.timestamp = new Date(entry.timestamp);
      }
    }

    return hydrated;
  }

  // ---------------------------------------------------------------------------
  // Session Metadata
  // ---------------------------------------------------------------------------

  /**
   * Get last session metadata
   */
  getLastSessionMetadata(): { sessionId: string; lastActivity: string } | undefined {
    const persisted = this.context.workspaceState.get<PersistedState>(STATE_KEY);
    return persisted?.sessionMetadata ? {
      sessionId: persisted.sessionMetadata.sessionId,
      lastActivity: persisted.sessionMetadata.lastActivity,
    } : undefined;
  }

  /**
   * Check if there's a recent session (within last hour)
   */
  hasRecentSession(): boolean {
    const metadata = this.getLastSessionMetadata();
    if (!metadata) return false;

    const lastActivity = new Date(metadata.lastActivity);
    const hourAgo = new Date(Date.now() - 60 * 60 * 1000);
    return lastActivity > hourAgo;
  }

  /**
   * Check if session.md needs update based on state staleness
   */
  async checkSessionMdFreshness(): Promise<'current' | 'stale' | 'missing'> {
    if (!this.workspaceFolder) return 'missing';

    const sessionMdPath = path.join(this.workspaceFolder, 'memories', 'session.md');
    
    try {
      const uri = vscode.Uri.file(sessionMdPath);
      const stat = await vscode.workspace.fs.stat(uri);
      
      const hourAgo = Date.now() - 60 * 60 * 1000;
      if (stat.mtime > hourAgo) {
        return 'current';
      }
      return 'stale';
    } catch {
      return 'missing';
    }
  }
}

// =============================================================================
// EXPORT SINGLETON FACTORY
// =============================================================================

let instance: PersistenceManager | undefined;

export function createPersistenceManager(context: vscode.ExtensionContext): PersistenceManager {
  if (!instance) {
    instance = new PersistenceManager(context);
  }
  return instance;
}

export function getPersistenceManager(): PersistenceManager | undefined {
  return instance;
}
