# Research: VS Code Extension API

> **Research ID:** research-vscode-api
> **Status:** ✅ COMPLETE
> **Date:** 2025-12-25
> **Purpose:** Understand VS Code extension capabilities for building Astra Consciousness layer

---

## Executive Summary

VS Code provides comprehensive APIs for:
1. **Chat Participants** — Create custom chat agents via `vscode.chat`
2. **Language Model Tools** — Register tools via `vscode.lm.registerTool`
3. **State Persistence** — `globalState` and `workspaceState` via Memento API
4. **Extension Communication** — `extensions.getExtension()` and `extension.exports`
5. **File Watching** — `workspace.createFileSystemWatcher`

**Key Finding:** We can build Astra Workflow as an extension that:
- Persists state across sessions via `workspaceState`
- Watches `copilot-instructions.md` for coordination
- Optionally registers as a chat participant for direct interaction
- Does NOT need to wrap Agent Memory/TODOs — can coordinate via file watching

---

## 1. Chat Participants API (`vscode.chat`)

### Overview
Chat participants allow extensions to create custom agents that respond to `@mentions` in VS Code Chat.

### Key Interface: `ChatParticipant`

```typescript
export interface ChatParticipant {
  readonly id: string;                          // Unique identifier
  iconPath?: IconPath;                          // Visual icon
  requestHandler: ChatRequestHandler;           // Main handler function
  followupProvider?: ChatFollowupProvider;      // Suggest follow-ups
  readonly onDidReceiveFeedback: Event<ChatResultFeedback>;
  dispose(): void;
}
```

### Creating a Chat Participant

```typescript
export function activate(context: vscode.ExtensionContext) {
  // Register the chat participant
  const participant = vscode.chat.createChatParticipant(
    'astra-workflow.astra',  // ID format: <extension>.<name>
    handler
  );
  
  // Set icon
  participant.iconPath = vscode.Uri.joinPath(context.extensionUri, 'icon.png');
  
  // Register for cleanup
  context.subscriptions.push(participant);
}
```

### Request Handler Pattern

```typescript
const handler: vscode.ChatRequestHandler = async (
  request: vscode.ChatRequest,      // User's message
  context: vscode.ChatContext,      // Chat history
  stream: vscode.ChatResponseStream, // Response output
  token: vscode.CancellationToken   // Cancellation
) => {
  // Access chat history
  const previousMessages = context.history.filter(
    h => h instanceof vscode.ChatResponseTurn
  );
  
  // Stream response
  stream.markdown("Processing...");
  stream.progress("Checking workflow state...");
  
  // Can also use buttons, references, etc.
  stream.button({ command: 'astra.showMetrics', title: 'Show Metrics' });
  
  return; // or return { metadata: {...} }
};
```

### ChatResponseStream Methods

| Method | Purpose |
|--------|---------|
| `markdown(value)` | Stream markdown text |
| `progress(value)` | Show progress message |
| `button(command)` | Add clickable button |
| `reference(uri)` | Link to file/location |
| `anchor(uri, title)` | Create anchor link |
| `filetree(value, baseUri)` | Show file tree |

### Relevance to Astra
- **Optional:** We could create `@astra` participant for direct interaction
- **Not required:** Core functionality works via file injection, not chat participation
- **Consideration:** May add complexity without clear benefit

---

## 2. Language Model Tools API (`vscode.lm`)

### Overview
Extensions can register tools that language models can invoke.

### Registering a Tool

```typescript
// In package.json:
{
  "contributes": {
    "languageModelTools": [{
      "name": "astra_getWorkflowState",
      "displayName": "Get Astra Workflow State",
      "description": "Returns current workflow phase and virtue metrics",
      "inputSchema": {
        "type": "object",
        "properties": {}
      }
    }]
  }
}

// In extension code:
vscode.lm.registerTool('astra_getWorkflowState', {
  async invoke(options, token) {
    const state = await getWorkflowState();
    return new vscode.LanguageModelToolResult([
      new vscode.LanguageModelTextPart(JSON.stringify(state))
    ]);
  },
  
  prepareInvocation(options, token) {
    return {
      invocationMessage: 'Checking Astra workflow state...'
    };
  }
});
```

### Tool Interface

```typescript
export interface LanguageModelTool<T> {
  invoke(
    options: LanguageModelToolInvocationOptions<T>,
    token: CancellationToken
  ): ProviderResult<LanguageModelToolResult>;
  
  prepareInvocation?(
    options: LanguageModelToolInvocationPrepareOptions<T>,
    token: CancellationToken
  ): ProviderResult<PreparedToolInvocation>;
}
```

### Relevance to Astra
- **Useful:** Could register tools for querying workflow state
- **Example tools:**
  - `astra_getPhase` — Current workflow phase
  - `astra_getVirtueMetrics` — Current virtue scores
  - `astra_transitionTo` — Request state transition
- **Note:** Tools appear in `lm.tools` list for all extensions to see

---

## 3. State Persistence (Memento API)

### Two Storage Scopes

| Storage | Scope | Use Case |
|---------|-------|----------|
| `globalState` | All workspaces | User preferences, global metrics |
| `workspaceState` | Current workspace | Project-specific workflow state |

### Memento Interface

```typescript
export interface Memento {
  keys(): readonly string[];           // List all keys
  get<T>(key: string): T | undefined;  // Get value
  get<T>(key: string, defaultValue: T): T;
  update(key: string, value: any): Thenable<void>; // Set value (JSON-safe)
}
```

### Usage Pattern

```typescript
export function activate(context: vscode.ExtensionContext) {
  // Read state
  const workflowState = context.workspaceState.get<WorkflowState>(
    'astra.workflowState',
    { phase: 'IDLE', lastTransition: null }
  );
  
  // Write state
  await context.workspaceState.update('astra.workflowState', {
    phase: 'EXECUTING',
    lastTransition: Date.now()
  });
  
  // Global state with sync
  context.globalState.setKeysForSync(['astra.preferences']);
}
```

### Constraints
- Values must be JSON-serializable (no functions, cycles)
- Using `undefined` as value removes the key
- Updates are asynchronous (returns `Thenable<void>`)

### Storage Decision for Astra

| Data | Storage | Rationale |
|------|---------|-----------|
| Workflow phase | `workspaceState` | Project-specific |
| Virtue metrics | `workspaceState` | Project-specific |
| Pathology history | `workspaceState` | Project-specific |
| User preferences | `globalState` | Cross-project |
| Metric thresholds | `globalState` | User-level config |

---

## 4. Extension Communication

### Getting Another Extension

```typescript
// Get extension by ID
const agentMemory = vscode.extensions.getExtension('digitarald.agent-memory');

if (agentMemory) {
  // Check if active
  if (!agentMemory.isActive) {
    await agentMemory.activate();
  }
  
  // Access exported API (if any)
  const api = agentMemory.exports;
  // Use api...
}
```

### Extension Interface

```typescript
export interface Extension<T> {
  readonly id: string;           // 'publisher.name'
  readonly extensionUri: Uri;
  readonly isActive: boolean;
  readonly packageJSON: any;     // Access package.json
  readonly exports: T;           // Public API (from activate return)
  activate(): Thenable<T>;
}
```

### Exposing API for Other Extensions

```typescript
// In your extension's activate():
export function activate(context: vscode.ExtensionContext) {
  // ... setup code ...
  
  // Return public API
  return {
    getWorkflowState: () => workflowStateMachine.getState(),
    getVirtueMetrics: () => metricsMonitor.getMetrics(),
    onStateChange: workflowStateMachine.onStateChange
  };
}
```

### Relevance to Astra
- **Can check** if Agent Memory/TODOs are installed
- **Unknown:** Whether they expose public APIs
- **Alternative:** File-based coordination (more reliable)

---

## 5. File System Watcher

### Creating a Watcher

```typescript
// Watch copilot-instructions.md for changes
const instructionsWatcher = vscode.workspace.createFileSystemWatcher(
  new vscode.RelativePattern(
    vscode.workspace.workspaceFolders![0],
    '.github/copilot-instructions.md'
  )
);

// Subscribe to events
instructionsWatcher.onDidChange(uri => {
  console.log('Instructions changed:', uri.fsPath);
  // Re-read file, check for conflicts, etc.
});

instructionsWatcher.onDidCreate(uri => {
  console.log('Instructions created:', uri.fsPath);
});

instructionsWatcher.onDidDelete(uri => {
  console.log('Instructions deleted:', uri.fsPath);
});

// Register for cleanup
context.subscriptions.push(instructionsWatcher);
```

### Relevance to Astra
- **Critical:** Watch `copilot-instructions.md` for coordination
- **Use case:** Detect when Agent Memory/TODOs inject their sections
- **Strategy:** Inject Astra section without conflicting

---

## 6. Extension Lifecycle

### Activation Events

```json
// package.json
{
  "activationEvents": [
    "onStartupFinished",           // After VS Code startup
    "workspaceContains:**/*.py",   // When workspace has Python files
    "onCommand:astra.showState",   // When command invoked
    "onView:astra.sidebar"         // When view opened
  ]
}
```

| Event | When |
|-------|------|
| `onStartupFinished` | After VS Code fully started (lazy) |
| `workspaceContains:pattern` | When workspace matches pattern |
| `onCommand:commandId` | When command executed |
| `onView:viewId` | When view is opened |
| `onLanguage:languageId` | When file of language opened |
| `*` | Immediately (avoid!) |

### Activate/Deactivate Pattern

```typescript
export function activate(context: vscode.ExtensionContext) {
  // Called once when extension activates
  // Setup watchers, state machines, etc.
  
  // Return API for other extensions
  return publicApi;
}

export function deactivate() {
  // Called when extension deactivates
  // Cleanup resources
}
```

### Recommendation for Astra
- Use `onStartupFinished` for lazy loading
- Minimize startup impact
- Cleanup properly in `deactivate()`

---

## 7. Architecture Decision

### Integration Strategy: File-Based Coordination

**Decision:** Use **Option D: File-based coordination** for integrating with Agent Memory and Agent TODOs.

**Rationale:**
1. **Stable contract** — Files don't change unexpectedly
2. **No dependency** — Works even if other extensions change
3. **Observable** — Can watch for changes
4. **Portable** — Git-trackable, visible to user

**Implementation:**
1. Watch `copilot-instructions.md` for changes
2. Parse to find existing sections (Agent Memory's TL;DR, Agent TODOs' `<todos>`)
3. Inject Astra section without disturbing others
4. Use `workspaceState` for internal state (not file-based)

### Proposed Section Format

```markdown
<!-- Auto-generated by Astra Workflow - DO NOT EDIT MANUALLY -->
<astra-workflow>
## Current Workflow State
- **Phase:** EXECUTING
- **Task:** impl-virtue-metrics
- **Eudaimonia:** 0.72

## Virtue Status
| Virtue | Score | Status |
|--------|-------|--------|
| Wisdom | 0.8 | ✅ Balanced |
| Courage | 0.6 | ⚠️ Low |
| Temperance | 0.7 | ✅ Balanced |
| Justice | 0.75 | ✅ Balanced |

## Active Warnings
- Spirit-deficiency: Avoiding difficult task for >2 phases
</astra-workflow>
<!-- End Astra Workflow -->
```

---

## 8. Key Code Samples

### Complete Extension Skeleton

```typescript
import * as vscode from 'vscode';

interface WorkflowState {
  phase: string;
  taskId: string | null;
  lastTransition: number;
}

interface VirtueMetrics {
  wisdom: number;
  courage: number;
  temperance: number;
  justice: number;
  eudaimonia: number;
}

let workflowState: WorkflowState;
let virtueMetrics: VirtueMetrics;

export function activate(context: vscode.ExtensionContext) {
  // 1. Load persisted state
  workflowState = context.workspaceState.get<WorkflowState>(
    'astra.workflowState',
    { phase: 'IDLE', taskId: null, lastTransition: 0 }
  );
  
  virtueMetrics = context.workspaceState.get<VirtueMetrics>(
    'astra.virtueMetrics',
    { wisdom: 0.5, courage: 0.5, temperance: 0.5, justice: 0.5, eudaimonia: 0.5 }
  );
  
  // 2. Setup file watcher
  const instructionsWatcher = vscode.workspace.createFileSystemWatcher(
    '**/copilot-instructions.md'
  );
  
  instructionsWatcher.onDidChange(async (uri) => {
    await syncInstructions(uri);
  });
  
  context.subscriptions.push(instructionsWatcher);
  
  // 3. Register commands
  context.subscriptions.push(
    vscode.commands.registerCommand('astra.showState', showState),
    vscode.commands.registerCommand('astra.transition', transitionPhase)
  );
  
  // 4. Initial injection
  injectAstraSection();
  
  // 5. Return public API
  return {
    getWorkflowState: () => workflowState,
    getVirtueMetrics: () => virtueMetrics,
    transitionTo: (phase: string) => transitionPhase(phase)
  };
}

export function deactivate() {
  // Cleanup if needed
}

async function syncInstructions(uri: vscode.Uri) {
  // Read file, check for conflicts, re-inject if needed
}

async function injectAstraSection() {
  // Find copilot-instructions.md
  // Parse existing content
  // Add/update <astra-workflow> section
}

function showState() {
  vscode.window.showInformationMessage(
    `Astra: Phase=${workflowState.phase}, Eudaimonia=${virtueMetrics.eudaimonia}`
  );
}

async function transitionPhase(newPhase: string) {
  // Validate transition
  // Update state
  // Persist
  // Re-inject instructions
}
```

---

## 9. Self-Check: Completion Criteria

| Criterion | Status | Evidence |
|-----------|--------|----------|
| Can explain chat participant registration | ✅ | Section 1: `vscode.chat.createChatParticipant()` |
| Can explain tool registration lifecycle | ✅ | Section 2: `vscode.lm.registerTool()` |
| Can explain state persistence options | ✅ | Section 3: `globalState` vs `workspaceState` |
| Have working code samples | ✅ | Section 8: Complete skeleton |
| Understand extension communication | ✅ | Section 4: `extensions.getExtension()` |
| Understand file watching | ✅ | Section 5: `createFileSystemWatcher()` |
| Made integration decision | ✅ | Section 7: File-based coordination |

---

## 10. Open Questions → Next Research

1. **Agent Memory:** How exactly does it inject into `copilot-instructions.md`? What section format?
2. **Agent TODOs:** What triggers the `<todos>` block update? What's the exact format?
3. **MCP:** Is Model Context Protocol relevant for tool registration?

---

## References

- VS Code API Reference: https://code.visualstudio.com/api/references/vscode-api
- Chat Extensions Guide: https://code.visualstudio.com/api/extension-guides/chat
- Extension Anatomy: https://code.visualstudio.com/api/get-started/extension-anatomy
- Storage: https://code.visualstudio.com/api/extension-capabilities/common-capabilities#data-storage

---

*Research completed: 2025-12-25*
*Next: Research Agent Memory extension (research-agent-memory)*
