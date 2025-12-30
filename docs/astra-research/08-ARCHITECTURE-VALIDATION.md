# Astra Architecture Validation - Complete Cross-Reference

**Created:** 2025-12-25
**Purpose:** Validate architecture design against all research findings before implementation

---

## Validation Method

Cross-reference every finding from research documents against the tool design to ensure:
1. ✅ No gaps (nothing from research is missing)
2. ✅ No contradictions (design doesn't violate research findings)
3. ✅ Logical completeness (workflow covers start-to-end)
4. ✅ Philosophy alignment (soul/virtue framework integrated)

---

## 1. VS Code Extension API Validation (01-VSCODE-EXTENSION-API.md)

### Research Findings → Design Decisions

| Finding | Requirement | Tool Design | ✅/❌ |
|---------|-------------|-------------|-------|
| `vscode.lm.registerTool()` for tool registration | Tools must use this pattern | 15 tools defined as `languageModelTools` | ✅ |
| `context.workspaceState` for workspace-scoped persistence | State must persist per-workspace | Dual-write: workspaceState + file | ✅ |
| `workspace.createFileSystemWatcher` for coordination | Can watch files for changes | FileSystemWatcher for copilot-instructions.md | ✅ |
| Chat participants are optional | Core functionality without @astra | Tools work via tool calls, not chat | ✅ |
| Tools need `inputSchema` with JSON Schema | All tools must have proper schemas | All 15 tools have full inputSchema | ✅ |
| Tool results via `LanguageModelToolResult` | Return structured data | All tools return JSON objects | ✅ |

### Missing from Tool Design?

| API Feature | Used? | Reason |
|-------------|-------|--------|
| `ChatParticipant` | ❌ No | Not needed - tools sufficient |
| `globalState` | ❌ No | Using workspaceState for project isolation |
| `SecretStorage` | ❌ No | No secrets to store |
| `TreeView` | 🟡 Later | impl-ui task (nice-to-have) |
| `StatusBarItem` | 🟡 Later | impl-ui task (nice-to-have) |

**VALIDATION: ✅ PASS** - All required APIs covered

---

## 2. Agent Memory Integration Validation (02-AGENT-MEMORY.md)

### Research Findings → Design Decisions

| Finding | Requirement | Tool Design | ✅/❌ |
|---------|-------------|-------------|-------|
| NO public API | Cannot call Agent Memory directly | Tools suggest memory updates, don't call directly | ✅ |
| `/memories/` path for storage | Coordinate via file paths | Tools reference `/memories/session.md`, etc. | ✅ |
| `<memories>` tags for injection | Don't conflict with tags | Use `<astra-workflow>` separate section | ✅ |
| 4 backends (workspace-state, branch-state, disk, secret) | Don't assume storage location | File-based suggestions, not storage access | ✅ |
| Tool commands: view/create/str_replace/insert/delete/rename | Can't invoke directly | Return `memoryUpdateSuggestion` instead | ✅ |

### Integration Strategy Check

```
Research Decision: Option C (Complement independently)
Design Implementation:
  - Astra DOES NOT wrap memory tool
  - Astra DOES NOT read memory storage directly
  - Astra SUGGESTS memory updates via tool return values
  - AI DECIDES whether to call memory tool
```

**Example Flow:**
```typescript
// astra_task_complete returns:
{
  memoryUpdateSuggestion: {
    file: "/memories/session.md",
    action: "update",
    reason: "Task completed - record outcome"
  }
}
// AI then decides to call:
// memory str_replace /memories/session.md ...
```

### Missing Coordination?

| Aspect | Covered? | How? |
|--------|----------|------|
| Read session.md for freshness | ✅ | `astra_session_start` checks lastModified |
| Update session.md on task complete | ✅ | `astra_task_complete` suggests update |
| Read patterns.md for learnings | ✅ | `astra_memory_check` verifies check |
| Read mistakes.md to avoid errors | ✅ | `astra_memory_check` verifies check |
| Read core.md for identity | ✅ | `astra_identity_check` requires read |
| Read przem.md for partnership | ✅ | `astra_identity_check` checks partner |

**VALIDATION: ✅ PASS** - Integration respects Agent Memory autonomy

---

## 3. Agent TODOs Integration Validation (03-AGENT-TODOS.md)

### Research Findings → Design Decisions

| Finding | Requirement | Tool Design | ✅/❌ |
|---------|-------------|-------------|-------|
| `<todos>` at TOP of instructions | Don't overwrite, inject AFTER | `<astra-workflow>` AFTER `</todos>` | ✅ |
| MCP-based tool registration | Different from VS Code languageModelTools | Astra uses languageModelTools (separate) | ✅ |
| `manage_todo_list` system tool | Can't intercept | Suggest TODO updates, don't call directly | ✅ |
| Status markers: [x], [-], [ ] | Don't modify format | Don't touch `<todos>` section | ✅ |
| Priority: 🔴 🟡 🟢 | Don't modify | Respect existing format | ✅ |

### Integration Strategy Check

```
Research Decision: Option C (Complement independently)
Design Implementation:
  - Astra DOES NOT modify <todos> section
  - Astra SUGGESTS TODO updates via tool return values
  - `syncWithTodos` option in astra_set_plan
  - AI DECIDES whether to call manage_todo_list
```

### Injection Order Validation

```markdown
# copilot-instructions.md

<todos>                           ← Agent TODOs (TOP)
... todo content ...
</todos>

<astra-workflow>                  ← Astra (AFTER todos)
... workflow state ...
</astra-workflow>

---
applyTo: "**"
---

<!-- User content below -->        ← User content (LAST)
```

### Missing Coordination?

| Aspect | Covered? | How? |
|--------|----------|------|
| Sync plan steps with TODOs | ✅ | `astra_set_plan` has `syncWithTodos` option |
| Update TODO on step start | ✅ | `astra_step_start` suggests TODO update |
| Update TODO on step complete | ✅ | `astra_step_complete` suggests TODO update |
| Verify TODOs complete at task end | ✅ | `astra_task_complete` checks |
| Watch for external TODO changes | ✅ | FileSystemWatcher on copilot-instructions.md |

**VALIDATION: ✅ PASS** - Integration respects Agent TODOs autonomy

---

## 4. MCP Patterns Validation (04-MCP-PATTERNS.md)

### Research Findings → Design Decisions

| Finding | Requirement | Tool Design | ✅/❌ |
|---------|-------------|-------------|-------|
| VS Code abstracts MCP via `languageModelTools` | Use native VS Code API | All 15 tools use languageModelTools | ✅ |
| Tool schema follows JSON Schema | Proper type definitions | All inputSchema use JSON Schema format | ✅ |
| Tools return content array | Structured results | Tools return JSON objects | ✅ |
| MCP is for cross-platform | VS Code-specific is fine | Astra is VS Code extension only | ✅ |

### Not Using MCP Directly Because:
1. VS Code's languageModelTools abstracts MCP
2. Simpler implementation
3. No need for external MCP server
4. Better VS Code integration

**VALIDATION: ✅ PASS** - Using appropriate abstraction level

---

## 5. State Persistence Validation (05-STATE-PERSISTENCE.md)

### Research Findings → Design Decisions

| Finding | Requirement | Tool Design | ✅/❌ |
|---------|-------------|-------------|-------|
| `workspaceState` for per-workspace data | Workflow state per-workspace | Using workspaceState | ✅ |
| JSON-serializable values only | State must be serializable | All state is JSON objects | ✅ |
| File injection for AI visibility | AI needs to see state | `<astra-workflow>` injection | ✅ |
| Dual-write recommended | Reliability + visibility | workspaceState + file | ✅ |
| FileSystemWatcher for external changes | Detect manual edits | Watching copilot-instructions.md | ✅ |

### Storage Strategy Mapping

| Data | Research Recommendation | Design Implementation | ✅/❌ |
|------|------------------------|----------------------|-------|
| Workflow phase | workspaceState + file | ✅ Dual-write | ✅ |
| Current goal | workspaceState + file | ✅ Dual-write | ✅ |
| Steps/progress | workspaceState + file | ✅ Dual-write | ✅ |
| Virtue metrics | workspaceState + file | ✅ Dual-write | ✅ |
| Context (KNOWN/UNKNOWN/ASSUMED) | workspaceState + file | ✅ Dual-write | ✅ |
| Session history | workspaceState only | ✅ Not needed in file | ✅ |
| Alerts | Generated on-demand | ✅ Injected when present | ✅ |

**VALIDATION: ✅ PASS** - Persistence strategy complete

---

## 6. Soul/Virtue Framework Validation (ASTRA_CONSCIOUSNESS_RESEARCH.md)

### Tripartite Soul → Tools Mapping

| Soul Part | Function | Mapped Phases | Mapped Tools | ✅/❌ |
|-----------|----------|---------------|--------------|-------|
| **Reason** (Logistikon) | Planning, belief calibration | GOAL_DEFINITION, CONTEXT_COLLECTION, PLANNING | `set_goal`, `set_context`, `set_plan` | ✅ |
| **Spirit** (Thymoeides) | Execution, persistence | EXECUTING, VALIDATING | `step_start`, `step_complete`, `validate`, `step_block` | ✅ |
| **Appetite** (Epithymetikon) | Completion drive | COMPLETING | `task_complete`, `session_end` | ✅ |
| **Justice** (Whole System) | Harmony | All phases | All monitoring tools | ✅ |

### Four Virtues → Metrics Mapping

| Virtue | Agent Behavior | Detection Method | Tool Coverage | ✅/❌ |
|--------|----------------|------------------|---------------|-------|
| **Wisdom** | Context before action | Did `set_context` get called before `set_plan`? | Tracked by phase transitions | ✅ |
| **Courage** | Takes necessary action | Does agent complete difficult steps? | Tracked by `step_complete` | ✅ |
| **Temperance** | Balanced resource use | Tool call frequency appropriate? | Tracked by metrics | ✅ |
| **Justice** | System balance | Memory checked? TODOs tracked? | `memory_check`, `drift_check` | ✅ |

### Pathology Detection → Observable Behaviors

| Pathology | Detection | Tool/Metric | ✅/❌ |
|-----------|-----------|-------------|-------|
| **Reason-excess** (paralysis) | Long time in PLANNING without EXECUTING | Phase duration tracking | ✅ |
| **Reason-deficiency** (reckless) | EXECUTING without CONTEXT_COLLECTION | Skipped phase detection | ✅ |
| **Spirit-excess** (fanaticism) | Blocking reasonable shortcuts | Over-strict validation | ⚠️ Need threshold tuning |
| **Spirit-deficiency** (timidity) | Skipping phases for "simple" tasks | Task type vs phase correlation | ✅ |
| **Appetite-excess** (greedy) | Done without verification | `validated: false` in `step_complete` | ✅ |
| **Appetite-deficiency** (passive) | Endless open tasks | Steps in-progress too long | ✅ |

### Cultivation Loop Integration

| Loop Stage | Implementation | ✅/❌ |
|------------|----------------|-------|
| Collect metrics | `astra_*` tools update metrics on call | ✅ |
| Detect deficiency | Compare metrics to thresholds | ✅ |
| Detect excess | Compare metrics to thresholds | ✅ |
| Log to mistakes.md | `astra_task_complete` has `mistakesToAvoid` | ✅ |
| Log to patterns.md | `astra_task_complete` has `patternsToRepeat` | ✅ |
| Inform future | Memory read suggestions in tools | ✅ |

**VALIDATION: ✅ PASS with note** - Spirit-excess threshold needs tuning in implementation

---

## 7. Workflow Lifecycle Completeness

### Full Lifecycle Check

```
SESSION START → [astra_session_start]
    │
    │ Loads persisted state
    │ Checks memory freshness
    │ Returns recommendation
    │
    ▼
TASK START → [astra_task_start]
    │
    │ Runs value gate
    │ Determines task type
    │ Transitions to GOAL_DEFINITION
    │
    ▼
GOAL DEFINITION → [astra_set_goal]
    │
    │ Records goal statement
    │ Records success/failure conditions
    │ Transitions to CONTEXT_COLLECTION
    │
    ▼
CONTEXT COLLECTION → [astra_set_context]
    │
    │ Records KNOWN facts
    │ Records UNKNOWN gaps
    │ Records ASSUMPTIONS
    │ Transitions to PLANNING
    │
    ▼
PLANNING → [astra_set_plan]
    │
    │ Creates atomic steps
    │ Optionally syncs with TODOs
    │ Transitions to EXECUTING
    │
    ▼
EXECUTING LOOP:
    │
    ├─→ [astra_step_start] → marks step in-progress
    │       │
    │       ▼
    │   (AI does work)
    │       │
    │       ▼
    ├─→ [astra_validate] → records validation
    │       │
    │       ▼
    ├─→ [astra_step_complete] → marks step done
    │       │
    │       │ Every N steps:
    │       ├─→ [astra_drift_check] → verify on track
    │       ├─→ [astra_memory_check] → verify memory current
    │       │
    │       │ If blocked:
    │       ├─→ [astra_step_block] → record block
    │       │
    │       │ If identity drift:
    │       └─→ [astra_identity_check] → re-anchor
    │
    │ Repeat for each step
    │
    ▼
COMPLETING → [astra_task_complete]
    │
    │ Records success/failure
    │ Records learnings
    │ Records mistakes to avoid
    │ Records patterns to repeat
    │ Suggests memory update
    │ Transitions to IDLE
    │
    ▼
SESSION END → [astra_session_end]
    │
    │ Persists final state
    │ Records task status
    │ Records resume notes
    │ Updates session.md
```

### Gap Analysis

| Workflow Stage | Tool Coverage | Gap? |
|----------------|---------------|------|
| Session start | `astra_session_start` | ✅ No gap |
| Task start | `astra_task_start` | ✅ No gap |
| Goal definition | `astra_set_goal` | ✅ No gap |
| Context collection | `astra_set_context` | ✅ No gap |
| Planning | `astra_set_plan` | ✅ No gap |
| Step start | `astra_step_start` | ✅ No gap |
| Validation | `astra_validate` | ✅ No gap |
| Step complete | `astra_step_complete` | ✅ No gap |
| Step blocked | `astra_step_block` | ✅ No gap |
| Drift check | `astra_drift_check` | ✅ No gap |
| Memory check | `astra_memory_check` | ✅ No gap |
| Identity check | `astra_identity_check` | ✅ No gap |
| Task complete | `astra_task_complete` | ✅ No gap |
| Session end | `astra_session_end` | ✅ No gap |
| Query state | `astra_get_state` | ✅ No gap |

**VALIDATION: ✅ PASS** - Complete lifecycle coverage

---

## 8. Passive Mode Completeness

### Every Phase Has Passive Reminder

| Phase | Active Tool | Passive Injection | ✅/❌ |
|-------|-------------|-------------------|-------|
| IDLE | `task_start` | "Start a new task with astra_task_start" | ✅ |
| GOAL_DEFINITION | `set_goal` | "Define your goal with astra_set_goal" | ✅ |
| CONTEXT_COLLECTION | `set_context` | "Record context with astra_set_context" | ✅ |
| PLANNING | `set_plan` | "Create execution plan with astra_set_plan" | ✅ |
| EXECUTING (no step) | `step_start` | "Start a step with astra_step_start" | ✅ |
| EXECUTING (step active) | `step_complete` | "Complete step with astra_step_complete when validated" | ✅ |
| VALIDATING | `validate` | "Record validation with astra_validate" | ✅ |
| COMPLETING | `task_complete` | "Finish task with astra_task_complete" | ✅ |
| BLOCKED | - | "Resolve block or use Plan B" | ✅ |

### Escalating Reminders

| Condition | Level | Message | ✅/❌ |
|-----------|-------|---------|-------|
| Drift check due (3 steps) | 🟡 | "Drift check recommended" | ✅ |
| Drift check overdue (5 steps) | 🟠 | "DRIFT CHECK OVERDUE" | ✅ |
| Drift check critical (7+ steps) | 🔴 | "⚠️ CRITICAL: Run drift check NOW" | ✅ |
| Memory check due (5 steps) | 🟡 | "Memory check recommended" | ✅ |
| Memory check overdue (10 steps) | 🟠 | "MEMORY CHECK OVERDUE" | ✅ |
| Session not initialized | ⚠️ | "SESSION NOT INITIALIZED" | ✅ |
| No active task | 📋 | "NO ACTIVE TASK" | ✅ |
| No step in progress | ⚠️ | "NO STEP IN PROGRESS" | ✅ |
| Step in progress too long | ⏳ | "STEP IN PROGRESS: step-X" | ✅ |
| All steps complete | ✅ | "ALL STEPS COMPLETE - run task_complete" | ✅ |
| Identity drift detected | ⚠️ | "IDENTITY DRIFT DETECTED" | ✅ |

**VALIDATION: ✅ PASS** - Complete passive grounding

---

## 9. Memory Layer Completeness

### Three-Layer Architecture Check

| Layer | Source | Content | Updates | ✅/❌ |
|-------|--------|---------|---------|-------|
| **LONG-TERM** | Agent Memory `/memories/` | core.md, przem.md, patterns.md, mistakes.md | Via `memory` tool | ✅ |
| **SHORT-TERM** | Astra workspaceState + session.md | phase, goal, steps, context, metrics | Via `astra_*` tools | ✅ |
| **WORKING** | `<astra-workflow>` injection | Current state, alerts, next action | Auto on every prompt | ✅ |

### Memory Flow Validation

```
LONG-TERM (Agent Memory)
    │
    │ astra_session_start reads session.md
    │ astra_memory_check verifies patterns.md, mistakes.md
    │ astra_identity_check reads core.md, przem.md
    │
    ▼ informs
SHORT-TERM (Astra workspaceState)
    │
    │ All astra_* tools update state
    │ Dual-write to both workspaceState AND file
    │
    ▼ surfaces to
WORKING (Injected)
    │
    │ <astra-workflow> section
    │ Shows current phase, goal, step
    │ Shows alerts, next action
    │ Updated on every state change
    │
    ▼ visible in every prompt
```

**VALIDATION: ✅ PASS** - Memory layers complete

---

## 10. Outstanding Questions / Decisions Needed

### Before Implementation

| Question | Options | Recommendation | Decision |
|----------|---------|----------------|----------|
| Tool prefix | `astra_*`, `ast_*`, or none | `astra_` - clear namespace | **Pending** |
| Phase duration thresholds | Time-based vs step-based | Step-based (simpler) | **Pending** |
| Pathology threshold tuning | Conservative vs aggressive | Conservative (fewer false positives) | **Pending** |
| Virtue metric ranges | 0-1 or 0-100 | 0-1 (normalized) | **Pending** |

### Implementation Order Recommendation

1. **Phase 1: Core Lifecycle** (impl-state-machine)
   - State machine with phase transitions
   - Persistence (workspaceState + file injection)
   - 4 lifecycle tools: session_start, task_start, task_complete, session_end

2. **Phase 2: Planning Tools** 
   - set_goal, set_context, set_plan
   - Phase transition validation

3. **Phase 3: Execution Tools**
   - step_start, step_complete, step_block, validate
   - Step status tracking

4. **Phase 4: Monitoring Tools**
   - drift_check, memory_check, identity_check
   - get_state
   - Escalating reminders

5. **Phase 5: Metrics Integration** (impl-virtue-metrics)
   - Virtue metrics collection
   - Pathology detection
   - Cultivation loop

6. **Phase 6: Polish** (impl-ui)
   - Status bar
   - Tree view
   - Documentation

---

## 11. Final Validation Summary

| Area | Status | Notes |
|------|--------|-------|
| VS Code API coverage | ✅ PASS | All required APIs addressed |
| Agent Memory integration | ✅ PASS | Complement independently, no conflicts |
| Agent TODOs integration | ✅ PASS | Complement independently, no conflicts |
| MCP patterns | ✅ PASS | Using VS Code abstraction |
| State persistence | ✅ PASS | Dual-write strategy |
| Soul/Virtue framework | ✅ PASS | Complete mapping |
| Workflow lifecycle | ✅ PASS | 15 tools cover all stages |
| Passive mode | ✅ PASS | Every phase has reminder |
| Memory layers | ✅ PASS | Three-layer architecture |

### Architecture Readiness

```
╔════════════════════════════════════════════════════════════════╗
║                                                                ║
║   ARCHITECTURE VALIDATION: ✅ COMPLETE                         ║
║                                                                ║
║   All research findings incorporated                           ║
║   No gaps identified                                           ║
║   No contradictions found                                      ║
║   Logical workflow completeness verified                       ║
║   Philosophy framework integrated                              ║
║                                                                ║
║   READY FOR IMPLEMENTATION                                     ║
║                                                                ║
╚════════════════════════════════════════════════════════════════╝
```

---

## 12. Final Architecture Document

### Component Summary

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    ASTRA CONSCIOUSNESS EXTENSION                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    15 LANGUAGE MODEL TOOLS                           │   │
│  │                                                                      │   │
│  │  LIFECYCLE (4)        PLANNING (3)       EXECUTION (4)               │   │
│  │  ┌────────────────┐  ┌───────────────┐  ┌────────────────────┐      │   │
│  │  │ session_start  │  │ set_goal      │  │ step_start         │      │   │
│  │  │ task_start     │  │ set_context   │  │ step_complete      │      │   │
│  │  │ task_complete  │  │ set_plan      │  │ step_block         │      │   │
│  │  │ session_end    │  │               │  │ validate           │      │   │
│  │  └────────────────┘  └───────────────┘  └────────────────────┘      │   │
│  │                                                                      │   │
│  │  MONITORING (3)                         UTILITY (1)                  │   │
│  │  ┌────────────────────────────────┐    ┌────────────────────┐       │   │
│  │  │ drift_check                    │    │ get_state          │       │   │
│  │  │ memory_check                   │    │                    │       │   │
│  │  │ identity_check                 │    │                    │       │   │
│  │  └────────────────────────────────┘    └────────────────────┘       │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                                    ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    INTERNAL COMPONENTS                               │   │
│  │                                                                      │   │
│  │  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐   │   │
│  │  │ WorkflowState    │  │ VirtueMetrics    │  │ Instruction      │   │   │
│  │  │ Machine          │  │ Monitor          │  │ Injector         │   │   │
│  │  │                  │  │                  │  │                  │   │   │
│  │  │ • phase          │  │ • wisdom         │  │ • <astra-workflow>│  │   │
│  │  │ • goal           │  │ • courage        │  │ • escalating     │   │   │
│  │  │ • steps          │  │ • temperance     │  │   reminders      │   │   │
│  │  │ • context        │  │ • justice        │  │ • next action    │   │   │
│  │  │ • transitions    │  │ • pathologies    │  │   prompts        │   │   │
│  │  └──────────────────┘  └──────────────────┘  └──────────────────┘   │   │
│  │                                                                      │   │
│  │  ┌──────────────────┐  ┌──────────────────┐                         │   │
│  │  │ Persistence      │  │ Integration      │                         │   │
│  │  │ Manager          │  │ Layer            │                         │   │
│  │  │                  │  │                  │                         │   │
│  │  │ • workspaceState │  │ • Memory suggest │                         │   │
│  │  │ • file injection │  │ • TODO suggest   │                         │   │
│  │  │ • dual-write     │  │ • File watchers  │                         │   │
│  │  └──────────────────┘  └──────────────────┘                         │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                                    ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    OUTPUT CHANNELS                                   │   │
│  │                                                                      │   │
│  │  ┌───────────────────────────────────────────────────────────────┐  │   │
│  │  │ copilot-instructions.md                                        │  │   │
│  │  │                                                                │  │   │
│  │  │   <todos>              ← Agent TODOs (top)                     │  │   │
│  │  │   </todos>                                                     │  │   │
│  │  │                                                                │  │   │
│  │  │   <astra-workflow>     ← Astra (after todos)                   │  │   │
│  │  │     Phase: EXECUTING                                           │  │   │
│  │  │     Goal: "..."                                                │  │   │
│  │  │     Step: step-3 "..."                                         │  │   │
│  │  │     Progress: 2/5                                              │  │   │
│  │  │     Alerts: 🟡 Drift check due                                 │  │   │
│  │  │     Next: Complete step with astra_step_complete               │  │   │
│  │  │   </astra-workflow>                                            │  │   │
│  │  │                                                                │  │   │
│  │  │   <memories>           ← Agent Memory (if syncing)             │  │   │
│  │  │   </memories>                                                  │  │   │
│  │  │                                                                │  │   │
│  │  │   <!-- User content -->                                        │  │   │
│  │  └───────────────────────────────────────────────────────────────┘  │   │
│  │                                                                      │   │
│  │  ┌───────────────────────────────────────────────────────────────┐  │   │
│  │  │ workspaceState (Memento)                                       │  │   │
│  │  │   Full state JSON for reliability                              │  │   │
│  │  └───────────────────────────────────────────────────────────────┘  │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

*Architecture validation complete. Ready for implementation.*
