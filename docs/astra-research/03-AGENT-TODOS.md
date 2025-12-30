# Research: Agent TODOs Extension

> **Research ID:** research-agent-todos
> **Status:** ✅ COMPLETE
> **Date:** 2025-12-25
> **Purpose:** Understand Agent TODOs architecture for integration with Astra Workflow

---

## Executive Summary

Agent TODOs (digitarald.agent-todos v0.0.2) provides:
1. **MCP-Based Tools** — Uses Model Context Protocol for tool registration
2. **Auto-Inject** — Injects `<todos>` block into `copilot-instructions.md`
3. **Visual Interface** — Tree view in dedicated activity bar container
4. **Two Tool Interfaces** — `manage_todo_list` (system) + `mcp_todos_todo_write` (MCP)
5. **Persistence** — State managed internally, synced to file on change

**Key Finding:** Agent TODOs auto-injects `<todos>` block at TOP of `copilot-instructions.md`. The `<todos>` section includes task list with ID, title, description, status, priority, and ADR notes.

**Integration Strategy:** Option C (Complement independently) — Astra injects its own section BELOW the `<todos>` block.

---

## 1. Extension Details

| Property | Value |
|----------|-------|
| **Extension ID** | `digitarald.agent-todos` |
| **Version** | 0.0.2 |
| **Tool Names** | `todo_read`, `todo_write` (MCP) |
| **System Tool** | `manage_todo_list` |
| **Activation** | On MCP server definition provider |
| **Categories** | Other |
| **MCP Dependency** | `@modelcontextprotocol/sdk` v1.16.0 |

---

## 2. Architecture

### MCP Server Integration
Agent TODOs uses **Model Context Protocol** for tool registration:

```json
{
  "mcpServerDefinitionProviders": [{
    "id": "digitarald.agent-todos.mcp-provider",
    "label": "Agent TODOs"
  }]
}
```

This means:
- Tools registered via MCP standard (not VS Code's native `lm.tools`)
- Can work as standalone MCP server (`npm run mcp-server`)
- Tools appear as `mcp_todos_*` in Copilot

### Two Tool Interfaces

| Tool | Source | Purpose | Format |
|------|--------|---------|--------|
| `manage_todo_list` | VS Code system tool | Strategic operations | `operation: "read" \| "write"` |
| `mcp_todos_todo_write` | MCP server | Granular todo management | Full ADR support |

---

## 3. Auto-Inject Feature

### Configuration
```json
{
  "agentTodos.autoInject": false,  // Default: disabled
  "agentTodos.autoInjectFilePath": ".github/copilot-instructions.md"
}
```

### Injection Format
The `<todos>` block is injected at the TOP of the file:

```markdown
<todos title="Project Name" rule="Review steps frequently...">
- [x] task-id-1: Task Title 1
  _Description or ADR notes_
- [-] task-id-2: Task Title 2 (in progress)
  _Description or ADR notes_  
- [ ] task-id-3: Task Title 3
  _Description or ADR notes_
</todos>

---
applyTo: "**"
---

<!-- Rest of instructions -->
```

### Status Markers
| Marker | Status |
|--------|--------|
| `[x]` | Completed |
| `[-]` | In Progress |
| `[ ]` | Pending/Not Started |

### Priority Indicators
Priorities shown via emoji in the title:
- 🔴 High
- 🟡 Medium  
- 🟢 Low

---

## 4. TODO Schema

```typescript
interface Todo {
  id: string;           // kebab-case identifier (e.g., "impl-auth")
  title: string;        // Short action-oriented label (3-7 words)
  content: string;      // Detailed description
  status: "pending" | "in_progress" | "completed";
  priority: "low" | "medium" | "high";
  adr?: string;         // Architecture Decision Record notes
}

interface TodoList {
  title?: string;       // List title (e.g., project name)
  rule?: string;        // Custom instruction for AI
  todos: Todo[];
}
```

---

## 5. Visual Interface

### Activity Bar Container
- Dedicated icon in activity bar (`$(checklist)`)
- Tree view shows all todos
- Visual status indicators

### Context Menu Actions
- Toggle status (pending → in_progress → completed)
- Set priority (high/medium/low)
- Add/Edit ADR notes
- Delete todo
- Run in Chat

### Tree View Commands
| Command | Description |
|---------|-------------|
| `agentTodos.toggleTodoStatus` | Cycle through status |
| `agentTodos.deleteTodo` | Remove todo |
| `agentTodos.runTodo` | Execute in VS Code Chat |
| `agentTodos.setStatusPending/InProgress/Completed` | Set specific status |
| `agentTodos.setPriorityHigh/Medium/Low` | Set priority |
| `agentTodos.addEditAdr` | Add ADR notes |
| `agentTodos.clearAdr` | Remove ADR notes |

---

## 6. Commands Exposed

| Command | Description |
|---------|-------------|
| `agentTodos.clearTodos` | Clear all todos |
| `agentTodos.refreshTodos` | Refresh view |
| `agentTodos.toggleAutoInject` | Enable auto-inject |
| `agentTodos.toggleAutoInjectEnabled` | Disable auto-inject |
| `agentTodos.saveTodos` | Save to file |
| `agentTodos.loadTodos` | Load from file |
| `agentTodos.startPlanning` | Open planning chat |
| `agentTodos.openSettings` | Open extension settings |

---

## 7. Integration with manage_todo_list

The `manage_todo_list` is a **system tool** (not MCP) that provides:

```typescript
// Operation: read
{
  "operation": "read"
}
// Returns current todo list

// Operation: write
{
  "operation": "write",
  "todoList": [
    {
      "id": "task-id",
      "title": "Task Title",
      "description": "Detailed description",
      "status": "pending" | "in_progress" | "completed"
    }
  ]
}
// Replaces entire todo list
```

**Key behavior:** `manage_todo_list` with `operation: "write"` REPLACES the entire list. Must include all existing todos when updating.

---

## 8. Injection Mechanism Analysis

### Trigger Events
The `<todos>` block is re-injected when:
1. Todo is added/modified/deleted via tool
2. Status changes via UI
3. Priority changes via UI
4. Manual refresh triggered

### File Handling
1. Read existing file content
2. Find existing `<todos>` block (if any)
3. Replace or prepend `<todos>` section
4. Preserve content after `</todos>`

### Section Identification
```markdown
<todos title="..." rule="...">
...
</todos>
```
- Opening tag: `<todos`
- Closing tag: `</todos>`
- Content preserved between tags

---

## 9. No Public API

Similar to Agent Memory, Agent TODOs does **NOT** expose a public API:

```typescript
// This would NOT work
const agentTodos = vscode.extensions.getExtension('digitarald.agent-todos');
const api = agentTodos?.exports; // undefined - no API
```

**Implication:** Must coordinate via file-based approach or independent operation.

---

## 10. Integration Analysis

### Option A: Wrap their tool ❌
- **Pros:** Could intercept todo operations
- **Cons:** No API, MCP-based, complex
- **Verdict:** Not feasible

### Option B: Read their outputs ✅
- **Pros:** Can parse `<todos>` block
- **Cons:** Must watch file for changes
- **Verdict:** **Possible for monitoring**

### Option C: Complement independently ✅
- **Pros:** No coupling, stable
- **Cons:** No direct interaction
- **Verdict:** **Recommended**

### Option D: File-based coordination ✅
- **Pros:** Stable, predictable format
- **Cons:** Must handle concurrent writes
- **Verdict:** **Use for injection coordination**

---

## 11. Integration Decision

**Decision:** Use **Option C + D: Complement independently with file coordination**

**Rationale:**
1. Agent TODOs has no public API
2. `<todos>` block format is predictable
3. Can parse `<todos>` to extract current task (for workflow state)
4. Astra injects own section below `<todos>`
5. File watching prevents conflicts

**Implementation:**
1. Watch `copilot-instructions.md` for changes
2. Parse `<todos>` block to extract current in-progress task
3. Inject `<astra-workflow>` section AFTER `</todos>` and before main content
4. Use debounce to prevent write conflicts

---

## 12. Coordination Strategy

### Copilot Instructions File Layout

```markdown
<todos title="Project Tasks" rule="Review frequently...">
- [-] current-task: Current Task Title
  _ADR notes here_
- [ ] next-task: Next Task
</todos>

<astra-workflow>
## Current Workflow State
- **Phase:** EXECUTING
- **Task:** current-task (from <todos>)
- **Eudaimonia:** 0.72

## Virtue Status
| Virtue | Score | Status |
|--------|-------|--------|
| Wisdom | 0.8 | ✅ Balanced |
...
</astra-workflow>

---
applyTo: "**"
---

<!-- User's custom instructions -->
```

### Parsing <todos> Block

```typescript
function extractCurrentTask(content: string): string | null {
  const todosMatch = content.match(/<todos[^>]*>([\s\S]*?)<\/todos>/);
  if (!todosMatch) return null;
  
  const todosContent = todosMatch[1];
  // Find in-progress task (marked with [-])
  const inProgressMatch = todosContent.match(/- \[-\] ([^:]+):/);
  return inProgressMatch ? inProgressMatch[1].trim() : null;
}
```

---

## 13. Key Differences: manage_todo_list vs mcp_todos_todo_write

| Aspect | manage_todo_list | mcp_todos_todo_write |
|--------|-----------------|---------------------|
| Source | VS Code system | MCP server |
| Schema | Simpler (id, title, description, status) | Full (+ priority, adr) |
| Operation | read/write | write-focused |
| Behavior | Replace entire list | Replace entire list |
| Auto-inject | Triggers update | Triggers update |

**Both tools trigger the same auto-inject mechanism.**

---

## 14. Self-Check: Completion Criteria

| Criterion | Status | Evidence |
|-----------|--------|----------|
| Understand both TODO layers | ✅ | Section 7, 13: manage_todo_list vs mcp_todos |
| Understand injection mechanism | ✅ | Section 3, 8: `<todos>` block at top |
| Know how to coordinate without conflict | ✅ | Section 11, 12: Inject below `</todos>` |
| Document state persistence | ✅ | Section 2: MCP-based, internal state |
| Understand file format | ✅ | Section 3: Status markers, priority emoji |

---

## 15. Open Questions → Next Research

1. **MCP Protocol:** Should Astra use MCP for tool registration? (research-mcp-patterns)
2. **State Persistence:** How does MCP server persist state? (research-state-persistence)

---

## References

- Extension: `~/.vscode/extensions/digitarald.agent-todos-0.0.2/`
- Package.json: Full configuration and commands
- Readme: User documentation and workflow examples
- GitHub: https://github.com/digitarald/vscode-agent-todos

---

*Research completed: 2025-12-25*
*Next: Research MCP patterns (research-mcp-patterns)*
