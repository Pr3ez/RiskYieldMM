# State Persistence Research - VS Code Extension Patterns

**Status**: ✅ COMPLETE
**Date**: Session research document
**Purpose**: Determine optimal state persistence strategy for Astra Consciousness Extension

---

## Executive Summary

VS Code provides multiple state persistence mechanisms. For Astra, we need:
1. **Workflow state** (current phase, transitions) - per-workspace
2. **Virtue metrics** (cognitive health) - per-workspace
3. **Learning data** (patterns, mistakes) - could be global or workspace

**Recommended Strategy**: Hybrid approach using `workspaceState` for runtime data and file-based storage for human-readable context (following Agent Memory/TODOs patterns).

---

## 1. VS Code State Persistence Mechanisms

### 1.1 Memento API (Primary for Extensions)

| Storage | Scope | Persistence | Sync |
|---------|-------|-------------|------|
| `context.globalState` | All workspaces | Survives restarts | Can sync across devices |
| `context.workspaceState` | Current workspace only | Survives restarts | Not synced |

```typescript
interface Memento {
  // Get stored keys
  keys(): readonly string[];
  
  // Get value (with optional default)
  get<T>(key: string): T | undefined;
  get<T>(key: string, defaultValue: T): T;
  
  // Store value (must be JSON-serializable, undefined removes key)
  update(key: string, value: any): Thenable<void>;
}
```

**Key Constraints:**
- Values **must be JSON-serializable** (no functions, no cyclic refs)
- No direct "delete" - use `update(key, undefined)`
- Async operation (returns `Thenable<void>`)

### 1.2 Storage URIs (File-Based)

| URI | Purpose | Scope |
|-----|---------|-------|
| `context.storageUri` | Workspace-specific files | Per-workspace |
| `context.globalStorageUri` | Global extension files | All workspaces |

```typescript
// Extension context provides URIs
const workspaceStorageUri = context.storageUri;     // undefined if no workspace
const globalStorageUri = context.globalStorageUri;   // always available

// Read/write files
await vscode.workspace.fs.writeFile(uri, Buffer.from(data, 'utf8'));
const content = await vscode.workspace.fs.readFile(uri);
```

**Use Case:** Large data, binary data, or data that should be user-visible/editable.

### 1.3 Secret Storage

```typescript
interface SecretStorage {
  get(key: string): Thenable<string | undefined>;
  store(key: string, value: string): Thenable<void>;
  delete(key: string): Thenable<void>;
  onDidChange: Event<SecretStorageChangeEvent>;
}
```

**Use Case:** API keys, tokens, sensitive data. Not relevant for Astra workflow state.

### 1.4 Settings (Configuration)

```typescript
// Read settings
const config = vscode.workspace.getConfiguration('astra');
const autoInject = config.get<boolean>('autoInject', true);

// Write settings (requires contributes.configuration in package.json)
await config.update('autoInject', false, ConfigurationTarget.Workspace);
```

**Use Case:** User preferences, not runtime state.

---

## 2. Comparison Matrix

| Aspect | globalState | workspaceState | File (storageUri) | File (globalStorageUri) |
|--------|-------------|----------------|-------------------|------------------------|
| **Scope** | All workspaces | Current workspace | Current workspace | All workspaces |
| **Format** | JSON-serializable | JSON-serializable | Any | Any |
| **Size Limit** | ~512KB practical | ~512KB practical | Filesystem | Filesystem |
| **User Visible** | No | No | Can be | Can be |
| **Sync Capable** | Yes (setKeysForSync) | No | Via external sync | Via external sync |
| **Performance** | Fast | Fast | I/O bound | I/O bound |
| **Survives** | VS Code restarts | VS Code restarts | Disk | Disk |

---

## 3. Existing Extension Patterns

### 3.1 Agent Memory (from 02-AGENT-MEMORY.md)

Uses **4 storage backends**:

| Backend | Location | Use Case |
|---------|----------|----------|
| `workspace-state` | VS Code Memento | Default, per-workspace |
| `branch-state` | VS Code Memento + git branch | Per-branch memory |
| `disk` | Workspace `.memories/` folder | User-visible files |
| `secret` | SecretStorage | Sensitive data |

**Key Insight:** Agent Memory primarily uses **file-based storage** in workspace folder for user visibility. The `/memories/` folder IS the storage.

### 3.2 Agent TODOs (from 03-AGENT-TODOS.md)

Uses **hybrid approach**:

```typescript
// From package.json
"contributes": {
  "configuration": {
    "properties": {
      "agentTodos.autoInject": {
        "type": "boolean",
        "default": false
      }
    }
  }
}
```

- **Runtime state** (todos list): In-memory + auto-inject to `copilot-instructions.md`
- **User preferences** (autoInject): VS Code configuration
- **Persistence**: Via file injection, not Memento

**Key Insight:** Agent TODOs persists by writing to `copilot-instructions.md`. The file IS the persistence mechanism.

### 3.3 Pattern: File as Source of Truth

Both extensions follow:
```
User-visible file → Source of truth
Extension reads/writes file → State sync
File watchers → Detect external changes
```

---

## 4. Astra State Requirements

### 4.1 What Astra Needs to Persist

| Data Type | Scope | Size | Update Frequency | User Visible |
|-----------|-------|------|------------------|--------------|
| **Workflow Phase** | Workspace | Small | On transitions | Yes (in instructions) |
| **Valid Transitions** | Workspace | Small | On transitions | Yes (in instructions) |
| **Virtue Metrics** | Workspace | Medium | Continuous | Yes (in instructions) |
| **Pathology Detections** | Workspace | Small | On detection | Yes (in instructions) |
| **Learning Data** | Could be global | Medium | On learning events | Maybe |
| **Session Context** | Workspace | Small | Per session | No |

### 4.2 Recommended Storage Strategy

```
┌─────────────────────────────────────────────────────────────────┐
│                 ASTRA STORAGE ARCHITECTURE                      │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                    PRIMARY STORAGE                              │
│                                                                 │
│  copilot-instructions.md                                        │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ <todos>...</todos>                  (Agent TODOs)       │   │
│  │ <memories>...</memories>            (Agent Memory)      │   │
│  │ <astra-workflow>                    (Astra)             │   │
│  │   <phase>research</phase>                               │   │
│  │   <transitions>planning,validation</transitions>        │   │
│  │   <virtue-metrics>                                      │   │
│  │     <wisdom>0.75</wisdom>                               │   │
│  │     <courage>0.80</courage>                             │   │
│  │     <temperance>0.65</temperance>                       │   │
│  │     <justice>0.70</justice>                             │   │
│  │   </virtue-metrics>                                     │   │
│  │   <pathologies>none</pathologies>                       │   │
│  │ </astra-workflow>                                       │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ↓ File watcher detects changes                                │
│  ↓ Extension reads/writes this file                            │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                   BACKUP STORAGE                                │
│                                                                 │
│  context.workspaceState (Memento)                               │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ Key: "astra.workflowState"                              │   │
│  │ Value: {                                                │   │
│  │   phase: "research",                                    │   │
│  │   lastTransition: "2025-01-10T...",                     │   │
│  │   metrics: { wisdom: 0.75, ... },                       │   │
│  │   sessionId: "abc123"                                   │   │
│  │ }                                                       │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  Used for:                                                     │
│  - Fast startup (read before file)                             │
│  - Recovery if file corrupted                                  │
│  - Session tracking                                            │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                 OPTIONAL: LEARNING STORAGE                      │
│                                                                 │
│  context.globalState (Memento)                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ Key: "astra.learningPatterns"                           │   │
│  │ Value: {                                                │   │
│  │   virtuePatterns: [...],                                │   │
│  │   deficiencyPatterns: [...],                            │   │
│  │   lastUpdated: "2025-01-10T..."                         │   │
│  │ }                                                       │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  Used for:                                                     │
│  - Cross-workspace learning                                    │
│  - Can sync via setKeysForSync                                 │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 5. Implementation Patterns

### 5.1 Dual Write Pattern (Recommended)

```typescript
class AstraStateManager {
  private workspaceState: vscode.Memento;
  private instructionsFile: InstructionInjector;
  
  async saveState(state: AstraState): Promise<void> {
    // 1. Write to Memento (fast, reliable backup)
    await this.workspaceState.update('astra.workflowState', state);
    
    // 2. Write to instructions file (visible to AI)
    await this.instructionsFile.updateAstraSection(state);
  }
  
  async loadState(): Promise<AstraState | null> {
    // Try Memento first (faster)
    const mementoState = this.workspaceState.get<AstraState>('astra.workflowState');
    if (mementoState) {
      return mementoState;
    }
    
    // Fallback: parse from instructions file
    return await this.instructionsFile.parseAstraSection();
  }
}
```

### 5.2 File Watcher Pattern

```typescript
class AstraFileWatcher {
  private watcher: vscode.FileSystemWatcher;
  
  constructor(instructionsPath: string) {
    this.watcher = vscode.workspace.createFileSystemWatcher(
      new vscode.RelativePattern(
        vscode.workspace.workspaceFolders![0],
        instructionsPath
      )
    );
    
    // React to external changes
    this.watcher.onDidChange(uri => this.handleExternalChange(uri));
  }
  
  private async handleExternalChange(uri: vscode.Uri) {
    // Re-read state from file
    const content = await vscode.workspace.fs.readFile(uri);
    const parsed = this.parseAstraSection(content.toString());
    
    // Update internal state if changed externally
    if (this.hasStateChanged(parsed)) {
      this.emit('stateChanged', parsed);
    }
  }
}
```

### 5.3 State Schema

```typescript
interface AstraWorkflowState {
  // Core workflow
  phase: WorkflowPhase;
  validTransitions: WorkflowPhase[];
  lastTransition: string; // ISO timestamp
  transitionHistory: Array<{
    from: WorkflowPhase;
    to: WorkflowPhase;
    timestamp: string;
    reason?: string;
  }>;
  
  // Virtue metrics
  virtueMetrics: {
    wisdom: number;      // 0-1 scale
    courage: number;     // 0-1 scale
    temperance: number;  // 0-1 scale
    justice: number;     // 0-1 scale
    compositeHealth: number; // 0-1 scale
  };
  
  // Pathology tracking
  pathologies: {
    detected: string[];  // e.g., ["reason-excess", "spirit-deficiency"]
    lastCheck: string;   // ISO timestamp
  };
  
  // Session info
  sessionId: string;
  sessionStart: string;  // ISO timestamp
}
```

---

## 6. Decision Summary

### 6.1 Final Recommendations

| Data Type | Storage | Rationale |
|-----------|---------|-----------|
| **Workflow state** | `workspaceState` + `copilot-instructions.md` | Dual write for reliability + AI visibility |
| **Virtue metrics** | `workspaceState` + `copilot-instructions.md` | Same as above |
| **Learning patterns** | `globalState` | Cross-workspace, sync-capable |
| **User preferences** | `configuration` | Standard VS Code pattern |

### 6.2 Key Design Decisions

1. **Primary source of truth**: `copilot-instructions.md` file
   - Human-readable
   - AI can see it
   - Follows existing extension patterns

2. **Backup source**: `workspaceState` Memento
   - Fast reads
   - Survives file corruption
   - No external dependencies

3. **Injection placement**: After `</todos>` section
   - Respects Agent TODOs' priority
   - Doesn't conflict with Agent Memory
   - Clear section separation

4. **Update strategy**: Write-through
   - Always update both Memento and file
   - File watcher for external changes
   - Reconciliation on conflict

---

## 7. Risk Mitigation

### 7.1 Potential Issues

| Risk | Mitigation |
|------|------------|
| File write conflicts | Debounce writes, use file locks if needed |
| Large state data | Keep metrics aggregated, not raw events |
| Parse errors | Schema validation, fallback to Memento |
| Performance | Batch updates, async operations |

### 7.2 Testing Strategy

1. **Unit tests**: State serialization/deserialization
2. **Integration tests**: File watcher behavior
3. **Conflict tests**: Simultaneous writes from multiple sources
4. **Recovery tests**: Corrupted file scenarios

---

## 8. References

- [VS Code Memento API](https://code.visualstudio.com/api/references/vscode-api#Memento)
- [ExtensionContext documentation](https://code.visualstudio.com/api/references/vscode-api#ExtensionContext)
- [FileSystem API](https://code.visualstudio.com/api/references/vscode-api#FileSystem)
- Agent Memory patterns (02-AGENT-MEMORY.md)
- Agent TODOs patterns (03-AGENT-TODOS.md)

---

## 9. Next Steps

- [x] Understand VS Code state APIs ✅
- [x] Analyze existing extension patterns ✅
- [x] Define Astra state schema ✅
- [x] Choose storage strategy ✅
- [ ] Design InstructionInjector component
- [ ] Implement StateManager class
- [ ] Add file watcher for external changes
