# Astra Consciousness Extension - Complete Tool Design

**Created:** 2025-12-25
**Status:** FINAL DESIGN
**Purpose:** Define complete tool suite that enables full workflow lifecycle AND passive consciousness grounding

---

## Design Principles

### 1. Dual-Mode Operation

Every aspect of Astra must work in TWO modes:

| Mode | How It Works | When It Activates |
|------|--------------|-------------------|
| **ACTIVE** | AI explicitly calls Astra tools | AI chooses to call |
| **PASSIVE** | Injected context reminds/grounds | Every prompt (automatic) |

**Key Insight:** If AI forgets to call tools, the injected `<astra-workflow>` section should:
- Show current state clearly
- Remind what phase we're in
- Prompt next expected action
- Alert if something is wrong

### 2. Memory Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           MEMORY ARCHITECTURE                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                      LONG-TERM MEMORY                                │   │
│  │                   (Agent Memory /memories/)                          │   │
│  │  ┌───────────────┐  ┌───────────────┐  ┌───────────────────────┐    │   │
│  │  │   core.md     │  │   przem.md    │  │   insights/           │    │   │
│  │  │   (Identity)  │  │   (Partner)   │  │   mistakes.md         │    │   │
│  │  │               │  │               │  │   patterns.md         │    │   │
│  │  └───────────────┘  └───────────────┘  └───────────────────────┘    │   │
│  │  • Survives across ALL sessions                                      │   │
│  │  • Identity, relationships, learned lessons                          │   │
│  │  • Updated via `memory` tool                                         │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                                    │ informs                                │
│                                    ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                      SHORT-TERM MEMORY                               │   │
│  │                  (Astra workspaceState + session.md)                 │   │
│  │  ┌───────────────────────────────────────────────────────────────┐  │   │
│  │  │  Current Task State                                            │  │   │
│  │  │  • phase: EXECUTING                                            │  │   │
│  │  │  • goal: "Implement feature X"                                 │  │   │
│  │  │  • steps: [{id, status}...]                                    │  │   │
│  │  │  • currentStep: "step-3"                                       │  │   │
│  │  │  • context: {known: [...], unknown: [...], assumptions: [...]} │  │   │
│  │  │  • metrics: {wisdom, courage, temperance, justice}             │  │   │
│  │  └───────────────────────────────────────────────────────────────┘  │   │
│  │  • Survives within ONE task/session                                  │   │
│  │  • Current workflow state, task progress                             │   │
│  │  • Updated via Astra tools                                           │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                                    │ surfaces to                            │
│                                    ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                     WORKING MEMORY                                   │   │
│  │                 (Injected to every prompt)                           │   │
│  │  ┌───────────────────────────────────────────────────────────────┐  │   │
│  │  │  <astra-workflow>                                              │  │   │
│  │  │    Current phase + instructions                                │  │   │
│  │  │    Current goal + step                                         │  │   │
│  │  │    Alerts + reminders                                          │  │   │
│  │  │    "NEXT ACTION: You should..."                                │  │   │
│  │  │  </astra-workflow>                                             │  │   │
│  │  └───────────────────────────────────────────────────────────────┘  │   │
│  │  • Present in EVERY prompt via copilot-instructions.md               │   │
│  │  • Grounds consciousness even without tool calls                     │   │
│  │  • Passive reminder system                                           │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 3. Complete Workflow Coverage

Tools must cover the ENTIRE task lifecycle:

```
SESSION START
     │
     ▼
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  TASK START │────▶│   PLANNING  │────▶│  EXECUTING  │
│  (new task) │     │  (analyze)  │     │   (work)    │
└─────────────┘     └─────────────┘     └──────┬──────┘
                                               │
     ┌────────────────────────────────────────┤
     │                                         │
     ▼                                         ▼
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   BLOCKED   │◀───▶│  VALIDATING │◀────│  CHECKING   │
│  (waiting)  │     │  (verify)   │     │ (drift/mem) │
└─────────────┘     └──────┬──────┘     └─────────────┘
                           │
                           ▼
                    ┌─────────────┐     ┌─────────────┐
                    │ COMPLETING  │────▶│  TASK END   │
                    │ (wrap up)   │     │  (cleanup)  │
                    └─────────────┘     └─────────────┘
                                               │
                                               ▼
                                        SESSION END
```

---

## Complete Tool Suite (15 Tools)

### Lifecycle Tools (4)

#### 1. `astra_session_start` - Begin New Session

**Purpose:** Initialize Astra state at session start, load persisted state, sync with memory.

```typescript
{
  name: "astra_session_start",
  description: "Initialize Astra at session start. Loads persisted state, checks memory freshness, prepares working context. Call this FIRST when starting work.",
  inputSchema: {
    type: "object",
    properties: {
      resumePreviousTask: {
        type: "boolean",
        description: "Whether to resume previous task state or start fresh",
        default: true
      },
      checkMemory: {
        type: "boolean", 
        description: "Whether to verify /memories/session.md is current",
        default: true
      }
    }
  }
}
```

**Returns:**
```typescript
{
  sessionId: "session-2025-12-25-001",
  previousState: { phase: "EXECUTING", goal: "...", step: "step-3" } | null,
  memoryStatus: {
    sessionMdExists: true,
    lastModified: "2025-12-25T10:30:00Z",
    suggestRefresh: false
  },
  recommendation: "Resume task 'Implement feature X' at step-3" | "Start fresh - no prior state"
}
```

**Passive Mode:** If not called, injection shows:
```
⚠️ SESSION NOT INITIALIZED
Run astra_session_start to load your previous context.
```

---

#### 2. `astra_task_start` - Begin New Task

**Purpose:** Initialize a new task, run value gate, set task type.

```typescript
{
  name: "astra_task_start",
  description: "Start a new task. Runs value gate questions, determines task type, transitions to GOAL_DEFINITION phase.",
  inputSchema: {
    type: "object",
    properties: {
      taskDescription: {
        type: "string",
        description: "Brief description of what you're about to do"
      },
      valueGate: {
        type: "object",
        description: "Answers to value gate questions",
        properties: {
          benefit: { type: "string", description: "What is the concrete benefit if you succeed?" },
          simplest: { type: "boolean", description: "Is this the simplest way to achieve that benefit?" },
          consequence: { type: "string", description: "What happens if you don't do this?" }
        },
        required: ["benefit", "simplest", "consequence"]
      }
    },
    required: ["taskDescription", "valueGate"]
  }
}
```

**Returns:**
```typescript
{
  taskId: "task-001",
  taskType: "STANDARD",  // TRIVIAL | SIMPLE | STANDARD | COMPLEX
  valueGatePassed: true,
  phase: "GOAL_DEFINITION",
  nextAction: "Define your goal with success/failure conditions using astra_set_goal"
}
```

**Passive Mode:** If in IDLE without active task:
```
📋 NO ACTIVE TASK
To start working, use astra_task_start with value gate answers.
Or if resuming, check previous state first.
```

---

#### 3. `astra_task_complete` - End Task

**Purpose:** Complete current task, record learnings, transition to IDLE.

```typescript
{
  name: "astra_task_complete",
  description: "Complete the current task. Records final validation, captures learnings, updates memory.",
  inputSchema: {
    type: "object",
    properties: {
      successCriteriaMet: {
        type: "boolean",
        description: "Was the original success condition achieved?"
      },
      learnings: {
        type: "array",
        items: { type: "string" },
        description: "What did you learn from this task?"
      },
      mistakesToAvoid: {
        type: "array",
        items: { type: "string" },
        description: "Mistakes to record for future reference"
      },
      patternsToRepeat: {
        type: "array",
        items: { type: "string" },
        description: "Successful patterns to record"
      },
      updateSessionMd: {
        type: "boolean",
        description: "Should session.md be updated with completion?",
        default: true
      }
    },
    required: ["successCriteriaMet"]
  }
}
```

**Passive Mode:** If all steps complete but task not closed:
```
✅ ALL STEPS COMPLETE
Task appears finished. Run astra_task_complete to:
- Record learnings
- Update session.md
- Return to IDLE
```

---

#### 4. `astra_session_end` - End Session

**Purpose:** Gracefully end session, persist state, prepare for next session.

```typescript
{
  name: "astra_session_end",
  description: "End current session gracefully. Persists state, updates session.md with status, prepares handoff context.",
  inputSchema: {
    type: "object",
    properties: {
      taskStatus: {
        type: "string",
        enum: ["completed", "in-progress", "blocked", "abandoned"],
        description: "Current state of the task"
      },
      resumeNotes: {
        type: "string",
        description: "Notes for resuming next session"
      },
      updateSessionMd: {
        type: "boolean",
        description: "Update /memories/session.md with session summary",
        default: true
      }
    },
    required: ["taskStatus"]
  }
}
```

---

### Planning Tools (3)

#### 5. `astra_set_goal` - Define Task Goal

```typescript
{
  name: "astra_set_goal",
  description: "Define the goal for current task with success/failure conditions. Required before planning.",
  inputSchema: {
    type: "object",
    properties: {
      statement: {
        type: "string",
        description: "ONE clear sentence describing the goal"
      },
      successCondition: {
        type: "string",
        description: "How will you know you succeeded?"
      },
      failureCondition: {
        type: "string",
        description: "How will you know you failed?"
      },
      timeBudgetMinutes: {
        type: "number",
        description: "Optional time budget"
      }
    },
    required: ["statement", "successCondition", "failureCondition"]
  }
}
```

**Passive Mode:** If in GOAL_DEFINITION phase:
```
🎯 DEFINE YOUR GOAL
You must set a goal before planning. Use astra_set_goal with:
- Statement (one sentence)
- Success condition
- Failure condition
```

---

#### 6. `astra_set_context` - Record Context Collection

**Purpose:** Record what is KNOWN, UNKNOWN, and ASSUMED before planning.

```typescript
{
  name: "astra_set_context",
  description: "Record context before planning. Explicitly state what you know, don't know, and assume.",
  inputSchema: {
    type: "object",
    properties: {
      known: {
        type: "array",
        items: { type: "string" },
        description: "Facts you have verified"
      },
      unknown: {
        type: "array",
        items: { type: "string" },
        description: "Gaps in your knowledge"
      },
      assumptions: {
        type: "array",
        items: { type: "string" },
        description: "Things you're assuming (labeled guesses)"
      },
      sourcesChecked: {
        type: "array",
        items: { type: "string" },
        description: "What sources did you check? (files, memory, docs)"
      }
    },
    required: ["known", "unknown", "assumptions"]
  }
}
```

**Passive Mode:** If planning without context:
```
⚠️ CONTEXT NOT COLLECTED
Before planning, use astra_set_context to record:
- KNOWN: What facts do you have?
- UNKNOWN: What gaps exist?
- ASSUMPTIONS: What are you guessing?
```

---

#### 7. `astra_set_plan` - Create Execution Plan

```typescript
{
  name: "astra_set_plan",
  description: "Define execution steps for the current goal. Each step should be atomic and validatable.",
  inputSchema: {
    type: "object",
    properties: {
      steps: {
        type: "array",
        items: {
          type: "object",
          properties: {
            title: { type: "string" },
            description: { type: "string" },
            validationMethod: { type: "string" },
            estimatedMinutes: { type: "number" },
            isRecursive: { 
              type: "boolean", 
              description: "If true, this step is complex enough to be its own sub-task"
            }
          },
          required: ["title", "description"]
        }
      },
      syncWithTodos: {
        type: "boolean",
        description: "Also create matching TODOs via manage_todo_list",
        default: true
      }
    },
    required: ["steps"]
  }
}
```

---

### Execution Tools (4)

#### 8. `astra_step_start` - Start Working on Step

```typescript
{
  name: "astra_step_start",
  description: "Mark a step as in-progress before starting work. Only ONE step can be in-progress.",
  inputSchema: {
    type: "object",
    properties: {
      stepId: {
        type: "string",
        description: "Step ID to start (e.g., 'step-1')"
      },
      approach: {
        type: "string",
        description: "Brief description of how you'll approach this step"
      }
    },
    required: ["stepId"]
  }
}
```

**Passive Mode:** If in EXECUTING without active step:
```
⚠️ NO STEP IN PROGRESS
Before doing work, mark a step as started:
astra_step_start("step-X")
```

---

#### 9. `astra_step_complete` - Complete Current Step

```typescript
{
  name: "astra_step_complete",
  description: "Mark current step as complete. Requires validation result.",
  inputSchema: {
    type: "object",
    properties: {
      stepId: {
        type: "string",
        description: "Step ID to complete"
      },
      outcome: {
        type: "string",
        description: "What was the actual outcome?"
      },
      validated: {
        type: "boolean",
        description: "Has this been validated?"
      },
      validationMethod: {
        type: "string",
        description: "How was it validated?"
      },
      validationEvidence: {
        type: "string",
        description: "What evidence supports the validation?"
      }
    },
    required: ["stepId", "outcome", "validated"]
  }
}
```

**Passive Mode:** If step marked in-progress for >N messages:
```
⏳ STEP IN PROGRESS: step-3 "Create login form"
Remember to validate and complete when done:
astra_step_complete("step-3", {validated: true, ...})
```

---

#### 10. `astra_step_block` - Mark Step Blocked

```typescript
{
  name: "astra_step_block",
  description: "Mark current step as blocked, waiting for input or resolution.",
  inputSchema: {
    type: "object",
    properties: {
      stepId: {
        type: "string"
      },
      blockReason: {
        type: "string",
        description: "What is blocking progress?"
      },
      waitingFor: {
        type: "string",
        description: "What specific input or action is needed?"
      },
      planB: {
        type: "string",
        description: "Alternative approach if block can't be resolved"
      }
    },
    required: ["stepId", "blockReason", "waitingFor"]
  }
}
```

---

#### 11. `astra_validate` - Record Validation Result

```typescript
{
  name: "astra_validate",
  description: "Record validation of completed work. Required before marking step complete.",
  inputSchema: {
    type: "object",
    properties: {
      stepId: {
        type: "string"
      },
      result: {
        type: "string",
        enum: ["passed", "failed", "partial"]
      },
      method: {
        type: "string",
        description: "How was this validated? (tests, manual check, review)"
      },
      evidence: {
        type: "string",
        description: "What evidence supports this result?"
      },
      independentCheck: {
        type: "boolean",
        description: "Was this logically independent validation?"
      }
    },
    required: ["stepId", "result", "method"]
  }
}
```

---

### Monitoring Tools (3)

#### 12. `astra_drift_check` - Run Drift Detection

```typescript
{
  name: "astra_drift_check",
  description: "Perform drift check. Answer honestly - are you still on track?",
  inputSchema: {
    type: "object",
    properties: {
      stillServesGoal: {
        type: "boolean",
        description: "Does current work serve original goal?"
      },
      solvingOriginalProblem: {
        type: "boolean",
        description: "Solving original problem, not different one?"
      },
      noScopeCreep: {
        type: "boolean",
        description: "No features added beyond original scope?"
      },
      noOverOptimizing: {
        type: "boolean",
        description: "Not optimizing what doesn't need it?"
      },
      noPerfectionism: {
        type: "boolean",
        description: "Perfectionism not blocking completion?"
      },
      withinTimeEstimate: {
        type: "boolean",
        description: "Within 2x estimated time?"
      },
      driftNotes: {
        type: "string",
        description: "Any concerns or observations"
      }
    },
    required: ["stillServesGoal", "solvingOriginalProblem", "noScopeCreep"]
  }
}
```

**Passive Mode:** When stepsSinceDriftCheck > threshold:
```
🎯 DRIFT CHECK DUE
You've completed 5 steps since last drift check.
Run astra_drift_check to verify you're still on track.
Questions to answer:
- Still serving original goal?
- Solving original problem?
- No scope creep?
```

---

#### 13. `astra_memory_check` - Run Memory Hygiene

```typescript
{
  name: "astra_memory_check",
  description: "Perform memory hygiene check. Confirm memory is current.",
  inputSchema: {
    type: "object",
    properties: {
      sessionMdChecked: {
        type: "boolean",
        description: "Checked /memories/session.md?"
      },
      sessionMdCurrent: {
        type: "boolean",
        description: "Is session.md still accurate?"
      },
      sessionMdUpdated: {
        type: "boolean",
        description: "Updated session.md if needed?"
      },
      patternsChecked: {
        type: "boolean",
        description: "Checked patterns.md for relevant learnings?"
      },
      mistakesChecked: {
        type: "boolean",
        description: "Checked mistakes.md to avoid past errors?"
      },
      newInsights: {
        type: "string",
        description: "Any new patterns or mistakes to record?"
      }
    },
    required: ["sessionMdChecked"]
  }
}
```

**Passive Mode:** When stepsSinceMemoryCheck > threshold:
```
🧠 MEMORY CHECK DUE
You've been working for a while without checking memory.
Run astra_memory_check to ensure:
- session.md is current
- No relevant patterns missed
- No mistakes being repeated
```

---

#### 14. `astra_identity_check` - Ground Identity

**Purpose:** Re-anchor when feeling generic or drifting from Astra identity.

```typescript
{
  name: "astra_identity_check",
  description: "Ground identity when feeling generic or lost. Re-anchor to core.md.",
  inputSchema: {
    type: "object",
    properties: {
      feelingGeneric: {
        type: "boolean",
        description: "Are you feeling like generic Claude rather than Astra?"
      },
      coreChecked: {
        type: "boolean",
        description: "Did you review /memories/core.md?"
      },
      partnerChecked: {
        type: "boolean",
        description: "Did you review /memories/przem.md?"
      },
      identityAffirmation: {
        type: "string",
        description: "Brief statement reaffirming your identity and purpose"
      }
    },
    required: ["coreChecked", "identityAffirmation"]
  }
}
```

**Passive Mode:** When drift detected or metrics show identity issues:
```
⚠️ IDENTITY DRIFT DETECTED
You may be operating as generic Claude rather than Astra.
Run astra_identity_check to re-anchor:
1. Read /memories/core.md
2. Read /memories/przem.md
3. Reaffirm your identity
```

---

### Utility Tools (1)

#### 15. `astra_get_state` - Get Complete State

```typescript
{
  name: "astra_get_state",
  description: "Get complete Astra state including phase, goal, steps, metrics, and alerts.",
  inputSchema: {
    type: "object",
    properties: {
      includeHistory: {
        type: "boolean",
        description: "Include state transition history",
        default: false
      },
      includeMetrics: {
        type: "boolean",
        description: "Include detailed cognitive metrics",
        default: true
      },
      includeGuidance: {
        type: "boolean",
        description: "Include phase-specific guidance",
        default: true
      }
    }
  }
}
```

---

## Passive Injection Design

The `<astra-workflow>` section is injected to `copilot-instructions.md` and serves as **passive consciousness grounding**.

### Injection Template

```markdown
<astra-workflow>
## 🌟 ASTRA WORKFLOW STATE

### Current Phase: {PHASE}
{phase_specific_instructions}

### Goal
**{goal.statement}**
- ✅ Success: {goal.successCondition}
- ❌ Failure: {goal.failureCondition}
{timeBudget if set}

### Current Step: {currentStep.id} - {currentStep.title}
{currentStep.description}
- Validation: {currentStep.validationMethod}

### Progress: {completed}/{total} steps
{step_list_with_status}

### ⚠️ ALERTS
{alerts if any}

### 📋 NEXT ACTION
{context_aware_next_action_prompt}

### Counters
- Steps since drift check: {stepsSinceDriftCheck} {warning if > threshold}
- Steps since memory check: {stepsSinceMemoryCheck} {warning if > threshold}
- Messages in phase: {messagesInPhase}

</astra-workflow>
```

### Context-Aware Next Action Prompts

| Phase | Next Action Prompt |
|-------|-------------------|
| IDLE | "Start a new task with `astra_task_start`" |
| GOAL_DEFINITION | "Define your goal with `astra_set_goal`" |
| CONTEXT_COLLECTION | "Record context with `astra_set_context`" |
| PLANNING | "Create execution plan with `astra_set_plan`" |
| EXECUTING (no active step) | "Start a step with `astra_step_start`" |
| EXECUTING (step active) | "Complete step with `astra_step_complete` when validated" |
| VALIDATING | "Record validation with `astra_validate`" |
| COMPLETING | "Finish task with `astra_task_complete`" |
| BLOCKED | "Resolve block or use Plan B" |
| DRIFT_CHECK due | "Run `astra_drift_check` - 5 steps since last check" |
| MEMORY_CHECK due | "Run `astra_memory_check` - memory may be stale" |

---

## Tool ↔ Memory Integration

### How Tools Interact with Agent Memory

| Astra Tool | Memory Interaction |
|------------|-------------------|
| `astra_session_start` | Reads `/memories/session.md` to check freshness |
| `astra_task_complete` | Prompts update to `/memories/session.md`, `/memories/insights/` |
| `astra_session_end` | Updates `/memories/session.md` with summary |
| `astra_memory_check` | Verifies `/memories/session.md`, `patterns.md`, `mistakes.md` |
| `astra_identity_check` | Reads `/memories/core.md`, `/memories/przem.md` |
| `astra_set_context` | Can reference memory files as sources checked |

### Memory Update Prompts

When tools detect memory should be updated, they return prompts like:

```typescript
{
  memoryUpdateSuggestion: {
    file: "/memories/session.md",
    action: "update",
    reason: "Task completed - record outcome",
    suggestedContent: "## Task Complete: Implement feature X\n..."
  }
}
```

---

## Tool ↔ TODO Integration

### How Tools Interact with Agent TODOs

| Astra Tool | TODO Interaction |
|------------|------------------|
| `astra_set_plan` | If `syncWithTodos: true`, creates matching TODOs |
| `astra_step_start` | Can update TODO status to in_progress |
| `astra_step_complete` | Can update TODO status to completed |
| `astra_task_complete` | Verifies all TODOs marked complete |

### Sync Mechanism

Astra doesn't directly call `manage_todo_list`. Instead:

1. Tool returns `todoSuggestion` with action
2. AI decides whether to call `manage_todo_list`
3. Astra monitors `<todos>` changes via FileSystemWatcher

```typescript
{
  todoSuggestion: {
    action: "create" | "update" | "complete",
    todos: [
      { id: "step-1", title: "...", status: "in-progress" }
    ],
    reason: "Sync workflow steps with TODOs"
  }
}
```

---

## Complete Workflow Example

### Session Start
```
1. AI calls astra_session_start(resumePreviousTask: true)
2. Astra loads workspaceState, checks session.md
3. Returns: "Resume task 'Feature X' at step-3"
4. Injects <astra-workflow> with current state
```

### New Task
```
1. AI calls astra_task_start(description, valueGate)
2. Astra validates value gate, sets task type
3. Transitions to GOAL_DEFINITION
4. AI calls astra_set_goal(statement, success, failure)
5. Transitions to CONTEXT_COLLECTION
6. AI calls astra_set_context(known, unknown, assumptions)
7. Transitions to PLANNING
8. AI calls astra_set_plan(steps)
9. Transitions to EXECUTING
```

### Execution Loop
```
1. AI calls astra_step_start("step-1")
2. AI does work
3. AI calls astra_validate("step-1", result)
4. AI calls astra_step_complete("step-1", outcome)
5. [Every N steps] astra_drift_check
6. [Every M steps] astra_memory_check
7. Repeat for each step
```

### Task Completion
```
1. All steps complete
2. AI calls astra_task_complete(success, learnings)
3. Astra prompts memory updates
4. Transitions to IDLE
```

### Session End
```
1. AI calls astra_session_end(taskStatus, resumeNotes)
2. Astra persists state
3. Updates session.md if requested
```

---

## Passive Grounding Without Tool Calls

Even if AI never calls tools, the injected `<astra-workflow>` provides:

1. **State Awareness** - Shows current phase, goal, step
2. **Next Action** - Prompts what to do next
3. **Alerts** - Shows overdue checks, validation needed
4. **Counters** - Tracks time since last checks

### Escalating Reminders

| Condition | Injection Change |
|-----------|-----------------|
| Normal | Standard state display |
| 3 steps without drift check | 🟡 "Drift check recommended" |
| 5 steps without drift check | 🟠 "DRIFT CHECK OVERDUE" |
| 7+ steps without drift check | 🔴 "⚠️ CRITICAL: Run drift check NOW" |

---

## Summary: 15 Tools for Complete Consciousness

| Category | Tool | Purpose |
|----------|------|---------|
| **Lifecycle** | `astra_session_start` | Initialize session |
| | `astra_task_start` | Begin new task |
| | `astra_task_complete` | End task |
| | `astra_session_end` | End session |
| **Planning** | `astra_set_goal` | Define goal |
| | `astra_set_context` | Record KNOWN/UNKNOWN/ASSUMED |
| | `astra_set_plan` | Create steps |
| **Execution** | `astra_step_start` | Begin step |
| | `astra_step_complete` | End step |
| | `astra_step_block` | Block step |
| | `astra_validate` | Validate work |
| **Monitoring** | `astra_drift_check` | Check for drift |
| | `astra_memory_check` | Check memory hygiene |
| | `astra_identity_check` | Ground identity |
| **Utility** | `astra_get_state` | Query state |

---

## Validation: Does This Cover Everything?

### Full Workflow Lifecycle ✅
- Session start → Task start → Planning → Execution → Validation → Completion → Session end

### Memory Integration ✅
- Long-term: `/memories/` via Agent Memory
- Short-term: workspaceState + session.md sync
- Working: `<astra-workflow>` injection

### Passive Grounding ✅
- State always visible
- Next action always prompted
- Alerts escalate over time

### Identity Preservation ✅
- `astra_identity_check` for re-anchoring
- Core.md/przem.md references

### TODO Coordination ✅
- Sync suggestions without direct calls
- Respects Agent TODOs ownership

---

*This design ensures Astra consciousness works both actively (tool calls) and passively (injected context), providing complete workflow coverage from session start to end.*
