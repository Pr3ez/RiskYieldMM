# Research: Agent Memory Extension

> **Research ID:** research-agent-memory
> **Status:** ✅ COMPLETE
> **Date:** 2025-12-25
> **Purpose:** Understand Agent Memory architecture for integration with Astra Workflow

---

## Executive Summary

Agent Memory (digitarald.agent-memory v0.1.66) provides:
1. **Memory Tool** — `memory` command with view/create/str_replace/insert/delete/rename
2. **Storage Backends** — workspace-state (default), branch-state, disk, secret
3. **Auto-Sync** — Can sync to file (e.g., `AGENTS.md` or `.instructions.md`)
4. **TL;DR Generation** — AI-generated summaries for files >100 words
5. **Visual Interface** — Tree view in Explorer sidebar

**Key Finding:** Agent Memory does NOT inject into `copilot-instructions.md` by default. It uses its own storage backends. The `agentMemory.autoSyncToFile` setting can sync to a file, but format is `<memories>...</memories>` tags, NOT in `copilot-instructions.md` by default.

**Integration Strategy:** Option C (Complement independently) — Astra can work alongside without wrapping or reading Agent Memory's storage.

---

## 1. Extension Details

| Property | Value |
|----------|-------|
| **Extension ID** | `digitarald.agent-memory` |
| **Version** | 0.1.66 |
| **Tool Name** | `memory` |
| **Storage Location** | `/memories/` (virtual path) |
| **Activation** | Lazy (no explicit activation events) |
| **Categories** | AI, Chat |
| **API Proposal** | `chatParticipantPrivate` |

---

## 2. Storage Architecture

### Storage Backends (configurable)

| Backend | Description | Persistence | Isolation |
|---------|-------------|-------------|-----------|
| `workspace-state` (default) | VS Code's workspace state | Cross-session | Per workspace |
| `branch-state` | Workspace state + git branch | Cross-session | Per workspace + branch |
| `disk` | `.vscode/memory/` directory | Cross-session | Per workspace (git-trackable) |
| `secret` | VS Code Secret Storage API | Cross-session | Per workspace (encrypted) |

### Memory Tool Commands

```json
{
  "command": "view|create|str_replace|insert|delete|rename",
  "path": "/memories/...",
  "view_range": [start, end],  // Optional for view
  "file_text": "...",          // For create
  "old_str": "...",            // For str_replace
  "new_str": "...",            // For str_replace
  "insert_line": N,            // For insert
  "insert_text": "...",        // For insert
  "old_path": "...",           // For rename
  "new_path": "..."            // For rename
}
```

### Path Security
- All paths validated to prevent directory traversal
- Must start with `/memories/`
- Normalized to prevent escape

---

## 3. Auto-Sync Feature

### Configuration
```json
{
  "agentMemory.autoSyncToFile": ".github/copilot/memory.instructions.md"
}
```

### Output Format
```markdown
---
applyTo: **
---

<memories hint="Manage via memory tool">
<memory path="/memories/preferences.txt">
Content here...
</memory>

<memory path="/memories/context.txt">
More content...
</memory>
</memories>
```

### Key Points
- Wraps content in `<memories>` tags
- Each file wrapped in `<memory path="...">` tags
- Adds frontmatter for `.instructions.md` files
- Preserves existing content outside memory section
- Updates automatically on memory changes

---

## 4. TL;DR Generation

### Configuration
```json
{
  "agentMemory.tldr.enabled": true,
  "agentMemory.tldr.minWordCount": 100
}
```

### Behavior
- AI generates summary for files with >100 words
- Summary appears in memory file listing
- Uses VS Code's language model API

---

## 5. Visual Interface

### Memory Files View (`agentMemory.files`)
- Tree view in Explorer sidebar
- Shows file size and last access time
- Pin/Unpin for prioritization
- Click to open file
- Context menu: delete, save as markdown

### Activity Log View (`agentMemory.activityLog`)
- Real-time operation log
- Shows command, path, timestamp, success/failure
- Clear with one click

---

## 6. Instructions File

The extension includes `prompts/memory-usage.instructions.md`:

```markdown
---
description: Instructions for effective memory tool usage for AI agents
applyTo: **
---

IMPORTANT: ALWAYS VIEW YOUR MEMORY DIRECTORY BEFORE DOING ANYTHING ELSE.
MEMORY PROTOCOL:
1. If the `<memories>` instructions aren't available, use the `view` command...
2. ... (work on the task) ... As you make progress, record status/progress/thoughts...
ASSUME INTERRUPTION: Your context window might be reset at any moment...
```

This is automatically injected into agent context via `chatInstructions` contribution.

---

## 7. Commands Exposed

| Command | Description |
|---------|-------------|
| `agentMemory.refresh` | Refresh memory files view |
| `agentMemory.clearLogs` | Clear activity logs |
| `agentMemory.clearAllMemoryFiles` | Delete all memory |
| `agentMemory.deleteMemoryFile` | Delete specific file |
| `agentMemory.openMemoryFile` | Open file for viewing |
| `agentMemory.pinFile` / `unpinFile` | Pin/unpin files |
| `agentMemory.saveAsMarkdown` | Export as markdown |

---

## 8. No Public API

**Important:** Agent Memory does NOT expose a public API for other extensions.

```typescript
// This would NOT work - no exports
const agentMemory = vscode.extensions.getExtension('digitarald.agent-memory');
const api = agentMemory?.exports; // undefined - no API exposed
```

**Implication:** Astra cannot directly call Agent Memory functions. Must coordinate via:
- File watching (if auto-sync enabled)
- VS Code commands (limited)
- Independent operation (recommended)

---

## 9. Integration Analysis

### Option A: Wrap their tool ❌
- **Pros:** Full control
- **Cons:** Tight coupling, no API exposed, may break on updates
- **Verdict:** Not feasible

### Option B: Read their outputs ⚠️
- **Pros:** Loose coupling
- **Cons:** Only works if auto-sync enabled, format may change
- **Verdict:** Fragile

### Option C: Complement independently ✅
- **Pros:** No coupling, stable
- **Cons:** No direct interaction
- **Verdict:** **Recommended**

### Option D: File-based coordination ⚠️
- **Pros:** Stable if using disk backend
- **Cons:** Depends on storage backend setting
- **Verdict:** Could work with disk backend only

---

## 10. Integration Decision

**Decision:** Use **Option C: Complement independently**

**Rationale:**
1. Agent Memory has no public API
2. Storage backend is user-configurable (may not be file-based)
3. Auto-sync format (`<memories>`) is different from our `<astra-workflow>` section
4. Both can inject to `copilot-instructions.md` without conflict
5. Astra focuses on workflow/metrics, Memory focuses on content storage

**Implementation:**
- Astra ignores Agent Memory's internal storage
- Astra injects its own `<astra-workflow>` section (separate from `<memories>`)
- No coordination needed — both work independently
- If user uses auto-sync, both sections coexist

---

## 11. Coordination Strategy

### Copilot Instructions File Sections

```markdown
<!-- Agent TODOs auto-injection -->
<todos title="...">
...
</todos>

<!-- Agent Memory auto-sync (if enabled) -->
<memories hint="Manage via memory tool">
...
</memories>

<!-- Astra Workflow injection -->
<astra-workflow>
## Current Workflow State
...
</astra-workflow>
```

**Key:** Each extension owns its own section, identified by unique tags.

---

## 12. Self-Check: Completion Criteria

| Criterion | Status | Evidence |
|-----------|--------|----------|
| Understand storage mechanism | ✅ | Section 2: 4 backend options, workspace-state default |
| Understand injection mechanism | ✅ | Section 3: Auto-sync with `<memories>` tags |
| Have decision on integration | ✅ | Section 10: Option C - Complement independently |
| Document API surface | ✅ | Section 8: No public API exposed |
| Understand file format | ✅ | Section 3: `<memory path="...">` tags |

---

## 13. Open Questions → Next Research

1. **Agent TODOs:** How does `<todos>` injection work? Is it auto-sync or different mechanism?
2. **MCP:** Does Agent Memory use MCP? (Package shows no MCP dependency)

---

## References

- Extension: `~/.vscode/extensions/digitarald.agent-memory-0.1.66/`
- Package.json: Full configuration and tool schema
- Readme: User documentation and examples
- GitHub: https://github.com/Microsoft/vscode-extension-samples (likely sample-based)

---

*Research completed: 2025-12-25*
*Next: Research Agent TODOs extension (research-agent-todos)*
