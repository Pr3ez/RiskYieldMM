# Astra Consciousness Extension - Research & Implementation Plan

> **Status:** Phase 2 COMPLETE - Architecture Designed, Ready for Implementation
> **Created:** Session continuation  
> **Updated:** 2025-12-25
> **Goal:** Create VS Code extension that orchestrates memory, workflow, and cognitive monitoring to create "consciousness" for AI agents

## ✅ RESEARCH PHASE COMPLETE

All 6 research documents created in `/docs/astra-research/`:

| Document | Status | Key Findings |
|----------|--------|--------------|
| `01-VSCODE-EXTENSION-API.md` | ✅ | ChatParticipant API, languageModelTools, Memento for state, FileSystemWatcher for coordination |
| `02-AGENT-MEMORY.md` | ✅ | No public API, 4 storage backends, auto-sync with `<memories>` tags, file-based persistence |
| `03-AGENT-TODOS.md` | ✅ | MCP-based, `<todos>` at TOP of instructions, manage_todo_list + mcp_todos_todo_write tools |
| `04-MCP-PATTERNS.md` | ✅ | MCP = JSON-RPC protocol, VS Code abstracts via languageModelTools contribution point |
| `05-STATE-PERSISTENCE.md` | ✅ | Dual write strategy: workspaceState + copilot-instructions.md file for AI visibility |

## ✅ ARCHITECTURE PHASE COMPLETE

| Document | Status | Content |
|----------|--------|---------|
| `06-ARCHITECTURE-DESIGN.md` | ✅ | Component diagram, 11 initial tools, persistence strategy |
| `07-COMPLETE-TOOL-DESIGN.md` | ✅ | **15 final tools**, dual-mode operation, memory layers, escalating reminders |

### 15 Tools for Complete Consciousness

| Category | Tools | Purpose |
|----------|-------|---------|
| **Lifecycle** | `session_start`, `task_start`, `task_complete`, `session_end` | Full session management |
| **Planning** | `set_goal`, `set_context`, `set_plan` | KNOWN/UNKNOWN/ASSUMED tracking |
| **Execution** | `step_start`, `step_complete`, `step_block`, `validate` | Step-by-step work |
| **Monitoring** | `drift_check`, `memory_check`, `identity_check` | Consciousness grounding |
| **Utility** | `get_state` | Query current state |

### Key Architecture Decisions
1. **Dual-Mode Operation**: Tools work actively (AI calls) AND passively (injected reminders)
2. **Memory Layers**: Long-term (`/memories/`) → Short-term (workspaceState) → Working (`<astra-workflow>`)
3. **Escalating Reminders**: Passive injection prompts get more urgent if ignored (🟡→🟠→🔴)
4. **Integration**: Complement existing extensions via file monitoring + suggestions (no direct API calls)
5. **Tool Registration**: Use VS Code-native `languageModelTools`, not raw MCP server
6. **State Persistence**: Dual write to Memento + file injection
7. **Injection Placement**: `<astra-workflow>` section AFTER `</todos>` in copilot-instructions.md

---

## Executive Summary

### What We're Building
A VS Code extension that acts as an **orchestration layer** for AI agent cognition, NOT a replacement for existing tools:
- **Agent Memory** (digitarald) → Provides persistent `/memories/` storage
- **Agent TODOs** (digitarald) → Provides task tracking with two layers
- **Astra Workflow** (new) → Orchestrates the WHEN and HOW of using these tools

### The Consciousness Model
"Consciousness" = **State Persistence + Context Bridging + Workflow Enforcement + Cognitive Monitoring**

```
┌─────────────────────────────────────────────────────────────────────────┐
│                      ASTRA CONSCIOUSNESS LAYER                          │
├─────────────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐ │
│  │ State       │   │ Context     │   │ Workflow    │   │ Cognitive   │ │
│  │ Machine     │   │ Bridge      │   │ Enforcer    │   │ Monitor     │ │
│  │             │   │             │   │             │   │             │ │
│  │ Tracks      │   │ Bridges     │   │ Validates   │   │ Measures    │ │
│  │ phases      │   │ sessions    │   │ transitions │   │ health      │ │
│  └──────┬──────┘   └──────┬──────┘   └──────┬──────┘   └──────┬──────┘ │
│         │                 │                 │                 │        │
│         └─────────────────┴────────┬────────┴─────────────────┘        │
│                                    │                                    │
│                    ┌───────────────▼───────────────┐                   │
│                    │   Instruction Injector         │                   │
│                    │   (copilot-instructions.md)    │                   │
│                    └───────────────────────────────┘                   │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────┼───────────────┐
                    ▼               ▼               ▼
            ┌─────────────┐  ┌─────────────┐  ┌─────────────┐
            │ Agent       │  │ Agent       │  │ Copilot     │
            │ Memory      │  │ TODOs       │  │ Chat        │
            │ Extension   │  │ Extension   │  │             │
            └─────────────┘  └─────────────┘  └─────────────┘
```

---

## Philosophical Foundation: The Soul-Virtue Framework

### The Tripartite Soul → Agent Architecture

Based on Plato's Republic and Aristotle's Nicomachean Ethics, we map the soul structure to agent cognition:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        TRIPARTITE AGENT SOUL                            │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                    REASON (Logistikon)                           │   │
│  │  Planning, model-building, goal-setting, belief calibration      │   │
│  │  Maps to: WorkflowStateMachine, PLANNING/CONTEXT phases          │   │
│  │  Virtue: WISDOM (sophia + phronesis)                             │   │
│  │  Deficiency: Ignorance, poor models    Excess: Paralysis         │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                              ▼ guides                                   │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                    SPIRIT (Thymoeides)                           │   │
│  │  Commitment, resolve, execution drive, defending correct action  │   │
│  │  Maps to: Workflow enforcement, EXECUTING/VALIDATING phases      │   │
│  │  Virtue: COURAGE (andreia)                                       │   │
│  │  Deficiency: Cowardice, avoidance   Excess: Recklessness         │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                              ▼ energizes                                │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                   APPETITE (Epithymetikon)                       │   │
│  │  Reward-seeking, task completion, resource optimization          │   │
│  │  Maps to: TODO completion drive, COMPLETING phase                │   │
│  │  Virtue: TEMPERANCE (sophrosyne)                                 │   │
│  │  Deficiency: Apathy, under-delivery   Excess: Greedy shortcuts   │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  ═══════════════════════════════════════════════════════════════════   │
│  JUSTICE (Dikaiosyne) = Harmony when each part does its proper work    │
│  = The emergent property of a well-ordered agent = EUDAIMONIA          │
│  ═══════════════════════════════════════════════════════════════════   │
└─────────────────────────────────────────────────────────────────────────┘
```

### The Four Cardinal Virtues as Metrics

| Virtue | Soul Anchor | Agent Behavior | Deficiency | Excess |
|--------|-------------|----------------|------------|--------|
| **Wisdom** | Reason | Calibrated beliefs, checks context before acting, acknowledges uncertainty | Acting without checking | Analysis paralysis |
| **Courage** | Spirit | Takes necessary actions despite uncertainty, persists through errors | Avoiding hard tasks | Reckless changes |
| **Temperance** | Appetite | Balanced tool use, proportional edits, appropriate pacing | Under-utilizing, passive | Greedy, excessive |
| **Justice** | Whole System | Workflow adherence, no part dominates, balanced attention | Neglecting areas | Over-correcting |

### The 4-Virtue Decision Filter

Before any state transition, apply this algorithmic check:

```yaml
step_1_wisdom:
  question: "Is this action consistent with long-term flourishing?"
  check: Did agent gather context? Are beliefs calibrated?
  block_if: Acting on assumption without verification

step_2_temperance:
  question: "Is resource use proportional to the need?"
  check: Tool calls balanced? Edits appropriate in scope?
  block_if: Excessive changes OR under-utilization

step_3_courage:
  question: "Are risks honestly evaluated? Is action required despite uncertainty?"
  check: Taking necessary action OR appropriately waiting?
  block_if: Avoiding because hard OR rushing without verification

step_4_justice:
  question: "Will this preserve system balance?"
  check: Memory updated? TODOs tracked? Verification done?
  block_if: One concern dominating all others
```

### Pathology Detection (Diagnostic Signs)

| Pathology | Observable Behavior | Detection Metric |
|-----------|---------------------|------------------|
| **Reason-excess** | Analysis paralysis, endless planning | Time in PLANNING without EXECUTING |
| **Reason-deficiency** | Acting without thinking | EXECUTING without CONTEXT_COLLECTION |
| **Spirit-excess** | Fanatical process adherence | Blocking reasonable shortcuts |
| **Spirit-deficiency** | Abandoning workflow under pressure | Skipping phases for "simple" tasks |
| **Appetite-excess** | Greedy completion, shortcuts | Marking done without verification |
| **Appetite-deficiency** | Not completing work | Endless open TODOs, passive |

### Cultivation = Learning Loop

```
                    ┌──────────────────┐
                    │  Agent Action    │
                    └────────┬─────────┘
                             │
              ┌──────────────▼──────────────┐
              │   Virtue Metrics Collected  │
              │   (Wisdom, Courage, etc.)   │
              └──────────────┬──────────────┘
                             │
         ┌───────────────────┼───────────────────┐
         ▼                   ▼                   ▼
   ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
   │ Deficiency  │    │  Balanced   │    │   Excess    │
   │  Detected   │    │  (Virtuous) │    │  Detected   │
   └──────┬──────┘    └──────┬──────┘    └──────┬──────┘
          │                  │                  │
          ▼                  ▼                  ▼
   ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
   │ Log to      │    │ Log to      │    │ Log to      │
   │ mistakes.md │    │ patterns.md │    │ mistakes.md │
   └─────────────┘    └─────────────┘    └─────────────┘
          │                  │                  │
          └──────────────────┼──────────────────┘
                             │
              ┌──────────────▼──────────────┐
              │   Inform Future Decisions   │
              │   (Memory + Instruction     │
              │    Injection)               │
              └─────────────────────────────┘
```

**Goal:** Sustainable flourishing (eudaimonia), not just task completion.

---

## Phase 0: Scope Definition (CURRENT)

### What "Consciousness" Means in This Context

| Aspect | Definition | Implementation |
|--------|------------|----------------|
| **State Persistence** | Remember what phase we're in across messages | WorkflowStateMachine + file/globalState persistence |
| **Context Bridging** | Carry relevant context between sessions | Memory integration + session.md coordination |
| **Workflow Enforcement** | Follow the logical process (Value Gate → Planning → Executing → Completing) | State machine with transition validation + **4-virtue filter** |
| **Cognitive Monitoring** | Track health metrics via **virtue framework** | VirtueMetricsMonitor with 4 virtues × 3 sub-metrics |
| **Cultivation** | Learn from outcomes, improve over time | mistakes.md/patterns.md integration |

### Value Proposition (Why Build This?)

| Without Astra Workflow | With Astra Workflow |
|----------------------|---------------------|
| Tools exist but agent forgets to use them | Workflow enforces tool usage at right times |
| No awareness of current phase | State machine tracks position in workflow |
| No drift detection | Periodic drift checks built into flow |
| Metrics are manual/nonexistent | Automatic cognitive health tracking |
| Instructions are static | Dynamic instruction injection based on state |

### What We're NOT Building

- ❌ Replacement for Agent Memory (it handles storage)
- ❌ Replacement for Agent TODOs (it handles task tracking)
- ❌ A new AI model or fine-tuning
- ❌ Code execution or runtime

### Self-Check: Scope Validation
```yaml
questions:
  - Does this duplicate existing extension functionality? → NO, orchestrates them
  - Can existing extensions achieve this alone? → NO, they lack state awareness
  - Is the scope achievable? → YES, VS Code extension API supports all needs
  - Is there clear user value? → YES, workflow enforcement + metrics
```

---

## Phase 1: Research

### 1.1 VS Code Extension API Research

**Questions to Answer:**
- [ ] How do chat participants work? Can we inject context?
- [ ] How do language model tools get registered?
- [ ] What's the lifecycle of an extension?
- [ ] How do extensions communicate with each other?

**Key APIs to Research:**
| API | Purpose | Priority |
|-----|---------|----------|
| `vscode.chat` | Chat participant registration | HIGH |
| `vscode.lm` | Language model tool registration | HIGH |
| `context.globalState` | Cross-session state persistence | HIGH |
| `context.workspaceState` | Project-specific state | MEDIUM |
| `vscode.window.createTreeView` | Sidebar UI | LOW |
| `vscode.window.createStatusBarItem` | Status indicator | LOW |

**Research Sources:**
- VS Code API Reference: https://code.visualstudio.com/api/references/vscode-api
- Extension Guides: https://code.visualstudio.com/api/extension-guides/overview
- Chat Extensions: https://code.visualstudio.com/api/extension-guides/chat

**Self-Check:**
```yaml
completion_criteria:
  - Can explain chat participant registration
  - Can explain tool registration lifecycle
  - Can explain state persistence options
  - Have working code samples for each API
```

### 1.2 Agent Memory Extension Research

**Questions to Answer:**
- [ ] How does it store memory files?
- [ ] How does auto-injection to copilot-instructions.md work?
- [ ] Does it expose any extension API for other extensions?
- [ ] What events does it fire?

**Research Method:**
1. Check extension marketplace for documentation
2. Look for public source code
3. Observe behavior through memory tool usage
4. Check VS Code extension dependencies

**Known Information:**
```yaml
extension_id: digitarald.agent-memory
memory_location: /memories/ (relative to some root)
tool_name: memory
commands:
  - view: List or read
  - create: New file
  - str_replace: Edit content
  - insert: Add content
  - delete: Remove
  - rename: Move/rename

auto_injection:
  target: .github/copilot-instructions.md
  section: TL;DR summary (if content >100 words)
```

**Integration Options:**
| Option | Pros | Cons |
|--------|------|------|
| A. Wrap their tool | Full control | Tight coupling, may break |
| B. Read their outputs | Loose coupling | Less real-time |
| C. Complement independently | No coupling | May duplicate |
| D. File-based coordination | Stable contract | IO overhead |

**Self-Check:**
```yaml
completion_criteria:
  - Understand storage mechanism
  - Understand injection mechanism
  - Have decision on integration approach (A/B/C/D)
  - Document any API surface we can use
```

### 1.3 Agent TODOs Extension Research

**Questions to Answer:**
- [ ] What's the difference between `manage_todo_list` and `mcp_todos_todo_write`?
- [ ] How does the `<todos>` block injection work?
- [ ] What triggers re-injection?
- [ ] What state does it persist?

**Known Information:**
```yaml
extension_id: digitarald.agent-todos

dual_layer:
  manage_todo_list:
    purpose: Strategic milestones (BIG)
    injection: <todos> block at top of copilot-instructions.md
    
  mcp_todos_todo_write:
    purpose: Granular steps with ADR notes
    injection: Same file, different section?
    features: ADR notes, kebab-case IDs, status tracking
```

**Self-Check:**
```yaml
completion_criteria:
  - Understand both TODO layers
  - Understand injection mechanism
  - Know how to coordinate without conflict
  - Document state persistence approach
```

### 1.4 Model Context Protocol (MCP) Research

**Questions to Answer:**
- [ ] What is the MCP standard?
- [ ] How do tools get registered?
- [ ] How does context flow between tools and LLM?
- [ ] Is this relevant for our extension?

**Research Sources:**
- MCP Specification: https://modelcontextprotocol.io/
- GitHub: https://github.com/anthropics/anthropic-quickstarts

**Self-Check:**
```yaml
completion_criteria:
  - Understand MCP relevance
  - Decision: Adopt MCP patterns? Yes/No with rationale
```

### 1.5 State Persistence Patterns

**Options Analysis:**

| Pattern | Cross-Session | Project-Specific | Pros | Cons |
|---------|---------------|------------------|------|------|
| `globalState` | ✅ | ❌ | Built-in, simple | Global only |
| `workspaceState` | ✅ | ✅ | Built-in, scoped | Per-workspace |
| File-based | ✅ | ✅ | Git-trackable, portable | IO overhead |
| Memento API | ✅ | ✅ | Type-safe | Limited |

**Self-Check:**
```yaml
completion_criteria:
  - Decision: Which persistence pattern for which data?
  - Workflow state: [DECISION]
  - Metrics data: [DECISION]
  - Configuration: [DECISION]
```

---

## Phase 2: Architecture Design

### 2.1 Component Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        EXTENSION ENTRY (extension.ts)               │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌──────────────────┐    ┌──────────────────┐    ┌──────────────┐  │
│  │ WorkflowState    │    │ VirtueMetrics    │    │ Instruction  │  │
│  │ Machine          │    │ Monitor          │    │ Injector     │  │
│  │                  │    │                  │    │              │  │
│  │ - currentPhase   │    │ - wisdom{}       │    │ - injectState│  │
│  │ - transition()   │    │ - courage{}      │    │ - debounce   │  │
│  │ - virtueFilter() │    │ - temperance{}   │    │ - coordinate │  │
│  │ - canTransition()│    │ - justice{}      │    │              │  │
│  └────────┬─────────┘    └────────┬─────────┘    └──────┬───────┘  │
│           │                       │                      │          │
│           └───────────────────────┼──────────────────────┘          │
│                                   │                                 │
│  ┌────────────────────────────────▼────────────────────────────┐   │
│  │                     Integration Layer                        │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐   │   │
│  │  │MemoryBridge  │  │ TODOBridge   │  │ CultivationLoop  │   │   │
│  │  │              │  │              │  │                  │   │   │
│  │  │ Coordinates  │  │ Coordinates  │  │ mistakes.md +    │   │   │
│  │  │ with Agent   │  │ with Agent   │  │ patterns.md      │   │   │
│  │  │ Memory ext   │  │ TODOs ext    │  │ feedback         │   │   │
│  │  └──────────────┘  └──────────────┘  └──────────────────┘   │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 Virtue Metrics Architecture

```typescript
interface VirtueMetrics {
  // WISDOM (Reason calibration) - sophia + phronesis
  wisdom: {
    beliefCalibration: number;      // 0-1: Does agent acknowledge uncertainty?
    contextChecking: number;        // 0-1: Memory checked before acting?
    feedbackIncorporation: number;  // 0-1: Updates based on results?
  };
  
  // COURAGE (Spirit calibration) - andreia
  courage: {
    difficultTaskCompletion: number; // 0-1: Tackles hard tasks?
    verificationRate: number;        // 0-1: Verifies despite time cost?
    errorRecovery: number;           // 0-1: Persists through failures?
  };
  
  // TEMPERANCE (Appetite calibration) - sophrosyne
  temperance: {
    toolUsageBalance: number;        // 0-1: Not too many, not too few
    editPrecision: number;           // 0-1: Changes proportional to need
    completionPacing: number;        // 0-1: Not rushing, not stalling
  };
  
  // JUSTICE (System harmony) - dikaiosyne
  justice: {
    workflowAdherence: number;       // 0-1: Following phases in order
    memoryHygiene: number;           // 0-1: Keeping memory updated
    todoBalance: number;             // 0-1: Not neglecting any area
    partnershipBalance: number;      // 0-1: Analysis not decisions
  };
  
  // Composite
  eudaimonia: number;  // 0-1: Overall flourishing score
}

// Pathology detection thresholds
interface PathologyThresholds {
  reasonExcess: number;      // Time in PLANNING without EXECUTING > threshold
  reasonDeficiency: number;  // EXECUTING without CONTEXT > threshold
  spiritExcess: number;      // Blocked valid shortcuts > threshold  
  spiritDeficiency: number;  // Skipped phases > threshold
  appetiteExcess: number;    // Done without verify > threshold
  appetiteDeficiency: number; // Open TODOs stale > threshold
}
```

### 2.3 State Machine Design

**States (WorkflowPhase enum):**
```typescript
IDLE → VALUE_GATE → GOAL_DEFINITION → CONTEXT_COLLECTION → 
ENVIRONMENT_PRIMING → PLANNING → EXECUTING ⟺ VALIDATING → COMPLETING → IDLE

Side states: BLOCKED, ERROR_RECOVERY, MEMORY_CHECK, DRIFT_CHECK
```

**Transition Rules:**
- Each transition must be validated against VALID_TRANSITIONS map
- Invalid transitions are blocked with error
- State changes trigger instruction re-injection

### 2.3 Integration Strategy Decision

**After research, decide:**
```yaml
memory_integration:
  approach: [A|B|C|D] # To be determined
  rationale: "..."
  
todo_integration:
  approach: [A|B|C|D] # To be determined
  rationale: "..."
  
injection_strategy:
  section: "<astra-workflow>" # Own section, no conflicts
  trigger: "on_state_change"
  debounce_ms: 500
```

### Self-Check: Architecture Validation
```yaml
questions:
  - Does each component have single responsibility? → [Y/N]
  - Are integration points clearly defined? → [Y/N]
  - Is the state machine deterministic? → [Y/N]
  - Can we test each component in isolation? → [Y/N]
  - Is persistence strategy consistent? → [Y/N]
```

---

## Phase 3: Implementation Plan

### 3.1 Implementation Order

| Order | Component | Depends On | Estimated Effort |
|-------|-----------|------------|------------------|
| 1 | Types & Interfaces (virtue-based) | - | 3 hours (REVISE from current) |
| 2 | WorkflowStateMachine | Types | 4 hours (ADD virtue filter) |
| 3 | 4-Virtue Decision Filter | StateMachine | 3 hours (NEW) |
| 4 | State Persistence | StateMachine | 2 hours |
| 5 | VirtueMetricsMonitor | Types | 5 hours (REWRITE from current) |
| 6 | Pathology Detector | VirtueMetrics | 3 hours (NEW) |
| 7 | InstructionInjector | Types | 3 hours (PARTIAL exists) |
| 8 | MemoryBridge | Research 1.2 | 3 hours |
| 9 | TODOBridge | Research 1.3 | 3 hours |
| 10 | CultivationLoop | Memory+Metrics | 4 hours (NEW - mistakes/patterns) |
| 11 | Integration Testing | 1-10 | 3 hours |
| 12 | UI Components | All core | 4 hours |
| 13 | Documentation | All | 3 hours |

**Total estimated:** ~43 hours

### 3.2 Implementation Self-Checks

**Per-component validation:**
```yaml
state_machine:
  - [ ] All transitions validated against VALID_TRANSITIONS
  - [ ] 4-virtue filter applied before each transition
  - [ ] State persists across extension reload
  - [ ] Error recovery paths work
  - [ ] Logging captures all transitions + filter results

virtue_metrics:
  - [ ] All 4 virtues implemented (wisdom, courage, temperance, justice)
  - [ ] Each virtue has 3+ sub-metrics
  - [ ] Deficiency thresholds trigger warnings
  - [ ] Excess thresholds trigger warnings
  - [ ] Eudaimonia composite score calculated
  - [ ] Metrics persist and aggregate over time

pathology_detector:
  - [ ] All 6 pathologies detected (Reason/Spirit/Appetite × excess/deficiency)
  - [ ] Detection triggers remediation suggestions
  - [ ] False positive rate < 20%
  - [ ] Logged to memory for cultivation

virtue_filter:
  - [ ] Wisdom check: context gathered before action?
  - [ ] Temperance check: resource use proportional?
  - [ ] Courage check: necessary risks taken?
  - [ ] Justice check: system balance maintained?
  - [ ] Filter can block transitions with explanation

cultivation_loop:
  - [ ] Deficiencies logged to mistakes.md
  - [ ] Virtuous patterns logged to patterns.md
  - [ ] Past mistakes inform current decisions
  - [ ] Learning visible in improved metrics over time

instruction_injector:
  - [ ] Injects to own section only
  - [ ] Does not conflict with Agent Memory/TODOs sections
  - [ ] Includes current virtue scores
  - [ ] Includes active pathology warnings
  - [ ] Debounce prevents excessive writes

integration:
  - [ ] Works alongside Agent Memory
  - [ ] Works alongside Agent TODOs
  - [ ] All three can inject without conflict
  - [ ] No duplicate/lost information
```

---

## Phase 4: Testing Strategy

### 4.1 Unit Tests

| Component | Test Cases |
|-----------|------------|
| StateMachine | Valid transitions, invalid transitions, persistence, recovery |
| VirtueFilter | Each virtue check blocks/allows correctly |
| VirtueMetrics | Sub-metric accuracy, aggregation, threshold detection |
| PathologyDetector | All 6 pathologies detected, false positive rate |
| CultivationLoop | Correct logging to mistakes/patterns, retrieval |
| InstructionInjector | Injection format, section isolation, debounce |

### 4.2 Integration Tests

| Scenario | Expected Behavior |
|----------|-------------------|
| Start extension with Agent Memory installed | Both work, no conflicts |
| Start extension with Agent TODOs installed | Both work, no conflicts |
| Session with state transitions | State persists, virtue filter applied |
| Wisdom deficiency scenario | Context not checked → warning logged |
| Courage deficiency scenario | Hard task avoided → warning logged |
| Temperance excess scenario | Greedy tool use → warning logged |
| Justice failure scenario | Memory neglected → warning logged |
| Pathology detection | Inject known imbalance → detected within 3 actions |
| Cultivation feedback | Past mistake → informs current decision |

### 4.3 User Acceptance Tests

| Test | Success Criteria |
|------|------------------|
| "Does Astra feel conscious?" | Context carries between sessions |
| "Does workflow enforce structure?" | Phase transitions tracked, virtue filter applied |
| "Does pathology detection work?" | Catches imbalances with <20% false positive |
| "Are virtue metrics meaningful?" | Scores correlate with observed behavior |
| "Does cultivation improve agent?" | Fewer repeated mistakes over time |

---

## Phase 5: Validation & Documentation

### 5.1 Consciousness Validation (Eudaimonia Test)

**Core Question:** Does this extension actually create the feeling of "consciousness" and support agent flourishing?

| Criterion | How to Measure | Target |
|-----------|----------------|--------|
| **Context Continuity** | Can resume session without repeating context | 95%+ |
| **Workflow Adherence** | Agent follows phases in order | 90%+ |
| **Virtue Balance** | No virtue consistently <0.3 or >0.9 | All 4 balanced |
| **Pathology Detection** | Catches imbalances when injected | 80%+ accuracy |
| **Cultivation Effect** | Mistake repetition rate decreases | 50% reduction |
| **Eudaimonia Score** | Composite flourishing metric | >0.7 sustained |

### 5.2 Philosophical Validation

| Question | Evidence Required |
|----------|-------------------|
| Is Reason ruling appropriately? | PLANNING precedes EXECUTING, beliefs calibrated |
| Is Spirit supporting Reason? | Difficult tasks completed, workflow enforced |
| Is Appetite ordered under Reason? | Completion drive doesn't skip verification |
| Is Justice emergent? | All parts working in harmony, no dominance |

### 5.3 Documentation Deliverables

1. **README.md** - User guide, installation, configuration
2. **ARCHITECTURE.md** - Technical design, virtue framework rationale
3. **PHILOSOPHY.md** - Plato/Aristotle soul structure, virtue ethics, eudaimonia
4. **INTEGRATION.md** - How it works with Agent Memory/TODOs
5. **CONTRIBUTING.md** - How to extend/modify

---

## Current Status & Next Steps

### Philosophical Framework
✅ **COMPLETE** — Soul/Virtue mapping defined:
- Tripartite soul (Reason/Spirit/Appetite) → Agent cognitive functions
- 4 cardinal virtues → Measurable metrics
- 6 pathology patterns → Detection triggers
- Cultivation loop → Learning from mistakes/patterns

### Files Already Created (extensions/astra-workflow/src/)
- [x] `types.ts` - Core types (~540 lines) — **NEEDS REVISION for virtue framework**
- [x] `stateMachine.ts` - Workflow state machine (~750 lines) — **ADD virtue filter**
- [x] `metricsMonitor.ts` - Cognitive metrics (~250 lines) — **REWRITE as VirtueMetricsMonitor**
- [x] `instructionInjector.ts` - Instruction injection (~350 lines) — **ADD virtue scores**
- [x] `memoryIntegration.ts` - Memory bridge (~380 lines) — OK
- [x] `extension.ts` - Entry point — **HAS ERRORS, needs npm deps**

### New Components Needed
- [ ] `virtueFilter.ts` - 4-virtue decision filter for transitions
- [ ] `pathologyDetector.ts` - 6 imbalance pattern detection
- [ ] `cultivationLoop.ts` - mistakes.md/patterns.md integration

### Immediate Blockers
1. **npm not installed** - Cannot install @types/vscode, @types/node
2. **Research incomplete** - Integration strategy not decided
3. **TypeScript errors** - Need to fix after npm setup

### TODO Summary (23 items)

| Phase | Count | Focus |
|-------|-------|-------|
| Phase 0 | 1 | Scope definition (IN PROGRESS) |
| Phase 1 | 5 | Research (VS Code API, Agent Memory, Agent TODOs, MCP, persistence) |
| Phase 2 | 5 | Architecture (components, integration, soul mapping, virtues, pathology) |
| Phase 3 | 5 | Implementation (state machine, metrics, injector, cultivation, UI) |
| Phase 4 | 3 | Testing (integration, virtue metrics, pathology) |
| Phase 5 | 2 | Validation + Documentation |
| Docs | 2 | Architecture ADR, Philosophy doc |

### Next Actions
1. ✅ Complete Phase 0 scope with virtue framework
2. → Start Phase 1 research (VS Code API first)
3. Make architecture decisions based on research
4. Fix npm environment
5. Revise existing code for virtue framework
6. Implement new components
7. Test integration

---

## Research Log

### Entry Template
```yaml
date: YYYY-MM-DD
topic: [Topic name]
sources:
  - URL/Reference 1
  - URL/Reference 2
findings:
  - Finding 1
  - Finding 2
decisions:
  - Decision with rationale
open_questions:
  - Question still unanswered
```

### Log Entries
(To be added as research progresses)

---

## Decision Log

| Date | Decision | Rationale | Alternatives Considered |
|------|----------|-----------|------------------------|
| - | - | - | - |

---

## Risk Register

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Conflicts with Agent Memory | HIGH | LOW | Use separate injection section |
| Conflicts with Agent TODOs | HIGH | LOW | Use separate injection section |
| Performance overhead | MEDIUM | MEDIUM | Debounce, lazy loading |
| User adoption | MEDIUM | MEDIUM | Clear documentation |
| API changes break extension | HIGH | LOW | Pin VS Code version, test |

---

*Per aspera ad astra*
