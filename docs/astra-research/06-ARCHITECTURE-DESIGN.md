# Astra Consciousness Extension - Architecture Design

**Created:** 2025-01-XX
**Status:** DRAFT
**Purpose:** Define component architecture enabling AI "thinking and reasoning" with state-aware decision making

---

## Executive Summary

The Astra Consciousness Extension transforms a stateless AI agent into a **state-aware cognitive system** by:

1. **Providing tools** the AI can call to manage workflow state
2. **Injecting context** so the AI knows its current state before each response
3. **Tracking metrics** to detect cognitive "health" issues (drift, skipped validation, etc.)
4. **Enforcing workflow** through state machine transitions

**Key Architectural Principle:**  
The AI doesn't "have" consciousness — Astra **provides tools and context that enable conscious-like behavior**.

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                           USER + VS CODE + COPILOT                            │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    copilot-instructions.md                           │   │
│   │  ┌──────────────────┐  ┌──────────────────┐  ┌───────────────────┐  │   │
│   │  │    <todos>       │  │   <memories>     │  │  <astra-workflow> │  │   │
│   │  │ (Agent TODOs)    │  │ (Agent Memory)   │  │  (THIS EXTENSION) │  │   │
│   │  └──────────────────┘  └──────────────────┘  └───────────────────┘  │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                      │                                       │
│                                      ▼                                       │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                      COPILOT/LLM CONTEXT                             │   │
│   │  • Knows current workflow phase                                      │   │
│   │  • Knows current goal & steps                                        │   │
│   │  • Knows cognitive health alerts                                     │   │
│   │  • Has access to Astra tools                                         │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                      │                                       │
│                                      ▼                                       │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    ASTRA TOOLS (languageModelTools)                  │   │
│   │                                                                      │   │
│   │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────┐  │   │
│   │  │ astra_get_state │  │ astra_transition│  │ astra_set_goal      │  │   │
│   │  │ → Phase, Goal,  │  │ → Change phase  │  │ → Define task goal  │  │   │
│   │  │   Alerts, etc.  │  │   with reason   │  │   with conditions   │  │   │
│   │  └─────────────────┘  └─────────────────┘  └─────────────────────┘  │   │
│   │                                                                      │   │
│   │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────┐  │   │
│   │  │ astra_set_plan  │  │astra_step_update│  │ astra_validate      │  │   │
│   │  │ → Create steps  │  │ → Start/complete│  │ → Record validation │  │   │
│   │  │   from TODOs    │  │   workflow steps│  │   result            │  │   │
│   │  └─────────────────┘  └─────────────────┘  └─────────────────────┘  │   │
│   │                                                                      │   │
│   │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────┐  │   │
│   │  │ astra_drift_chk │  │astra_memory_chk │  │ astra_get_guidance  │  │   │
│   │  │ → Run drift     │  │ → Run memory    │  │ → Get phase-specific│  │   │
│   │  │   detection     │  │   hygiene check │  │   instructions      │  │   │
│   │  └─────────────────┘  └─────────────────┘  └─────────────────────┘  │   │
│   │                                                                      │   │
│   │  ┌─────────────────┐  ┌─────────────────┐                           │   │
│   │  │ astra_log_claim │  │ astra_log_decide│                           │   │
│   │  │ → Track claims  │  │ → Track decision│                           │   │
│   │  │   for verify    │  │   patterns      │                           │   │
│   │  └─────────────────┘  └─────────────────┘                           │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                      │                                       │
│                                      ▼                                       │
├──────────────────────────────────────────────────────────────────────────────┤
│                           ASTRA EXTENSION (Internal)                         │
│                                                                              │
│   ┌────────────────────────────────────────────────────────────────────┐    │
│   │                    WorkflowStateMachine                             │    │
│   │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │    │
│   │  │ Phase State  │  │ Transition   │  │ Validation   │              │    │
│   │  │ (IDLE,       │  │ Validator    │  │ Rules        │              │    │
│   │  │  PLANNING,   │  │ (Valid from  │  │ (Strictness  │              │    │
│   │  │  EXECUTING,  │  │  A → B?)     │  │  by TaskType)│              │    │
│   │  │  etc.)       │  │              │  │              │              │    │
│   │  └──────────────┘  └──────────────┘  └──────────────┘              │    │
│   │                                                                     │    │
│   │  ┌──────────────────────────────────────────────────────────────┐  │    │
│   │  │                     Workflow State                            │  │    │
│   │  │  • phase: WorkflowPhase                                       │  │    │
│   │  │  • taskType: TaskType                                         │  │    │
│   │  │  • goal: { statement, successCondition, failureCondition }    │  │    │
│   │  │  • steps: WorkflowStep[]                                      │  │    │
│   │  │  • currentStepIndex: number                                   │  │    │
│   │  │  • context: { known, unknown, assumptions }                   │  │    │
│   │  │  • metrics: CognitiveMetrics                                  │  │    │
│   │  │  • stateHistory: { phase, timestamp, reason }[]               │  │    │
│   │  └──────────────────────────────────────────────────────────────┘  │    │
│   └────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│   ┌────────────────────────────────────────────────────────────────────┐    │
│   │                  CognitiveMetricsMonitor                            │    │
│   │  ┌──────────────────────────────────────────────────────────────┐  │    │
│   │  │ Identity Drift   │ Memory Hygiene  │ TODO Adherence          │  │    │
│   │  │ • identityChecks │ • memoryReads   │ • todosCreated          │  │    │
│   │  │ • driftDetections│ • memoryWrites  │ • todosCompleted        │  │    │
│   │  └──────────────────┴─────────────────┴─────────────────────────┘  │    │
│   │  ┌──────────────────────────────────────────────────────────────┐  │    │
│   │  │ Verification     │ Partnership     │ Workflow Compliance     │  │    │
│   │  │ • claimsMade     │ • unilateral    │ • validTransitions      │  │    │
│   │  │ • claimsVerified │ • analysis      │ • invalidTransitions    │  │    │
│   │  └──────────────────┴─────────────────┴─────────────────────────┘  │    │
│   │                                                                     │    │
│   │  ┌──────────────────────────────────────────────────────────────┐  │    │
│   │  │                  Alert Generation                             │  │    │
│   │  │  threshold.exceeded? → Alert { metric, value, suggestion }   │  │    │
│   │  └──────────────────────────────────────────────────────────────┘  │    │
│   └────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│   ┌────────────────────────────────────────────────────────────────────┐    │
│   │                   InstructionInjector                               │    │
│   │  ┌──────────────────────────────────────────────────────────────┐  │    │
│   │  │ <astra-workflow>                                              │  │    │
│   │  │   • Phase-specific instructions                               │  │    │
│   │  │   • Current goal summary                                      │  │    │
│   │  │   • Current step focus                                        │  │    │
│   │  │   • Progress (X/Y steps)                                      │  │    │
│   │  │   • Active alerts                                             │  │    │
│   │  │   • Counters (steps since drift/memory check)                 │  │    │
│   │  │ </astra-workflow>                                             │  │    │
│   │  └──────────────────────────────────────────────────────────────┘  │    │
│   │                                                                     │    │
│   │  Injection Location: AFTER </todos>, BEFORE user content           │    │
│   └────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│   ┌────────────────────────────────────────────────────────────────────┐    │
│   │                    PersistenceManager                               │    │
│   │  ┌──────────────────────────────────────────────────────────────┐  │    │
│   │  │                    DUAL WRITE STRATEGY                        │  │    │
│   │  │                                                               │  │    │
│   │  │  workspaceState (Memento)     copilot-instructions.md        │  │    │
│   │  │  └── For reliability          └── For AI visibility           │  │    │
│   │  │      • Survives crashes           • Read on every prompt      │  │    │
│   │  │      • Fast reads                 • <astra-workflow> section  │  │    │
│   │  │      • JSON serializable          • Human-readable            │  │    │
│   │  │                                                               │  │    │
│   │  │  On state change → Write to BOTH                              │  │    │
│   │  │  On startup → Load from Memento, inject to instructions       │  │    │
│   │  └──────────────────────────────────────────────────────────────┘  │    │
│   └────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## Tool Definitions (languageModelTools)

### 1. `astra_get_state` - Read Current Workflow State

```typescript
{
  name: "astra_get_state",
  displayName: "Astra: Get Workflow State",
  description: "Get current workflow phase, goal, progress, and cognitive health alerts. Call this at the start of complex tasks to understand where you are.",
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
        default: false
      }
    }
  },
  tags: ["workflow", "state", "consciousness"]
}
```

**Returns:**
```typescript
{
  phase: "EXECUTING",
  taskType: "STANDARD",
  goal: {
    statement: "Implement user authentication",
    successCondition: "User can log in with valid credentials",
    failureCondition: "Login rejects valid credentials"
  },
  currentStep: {
    id: "step-2",
    title: "Create login form component",
    status: "in-progress"
  },
  progress: {
    completed: 1,
    total: 5
  },
  alerts: [
    {
      metric: "Memory Check Frequency",
      severity: "warning",
      suggestion: "Run memory check now"
    }
  ],
  counters: {
    stepsSinceDriftCheck: 3,
    stepsSinceMemoryCheck: 8
  }
}
```

### 2. `astra_transition` - Change Workflow Phase

```typescript
{
  name: "astra_transition",
  displayName: "Astra: Transition Workflow Phase",
  description: "Request a workflow phase transition. Will validate the transition is allowed and return success/failure with reason.",
  inputSchema: {
    type: "object",
    properties: {
      toPhase: {
        type: "string",
        enum: ["IDLE", "VALUE_GATE", "GOAL_DEFINITION", "CONTEXT_COLLECTION", 
               "ENVIRONMENT_PRIMING", "PLANNING", "EXECUTING", "VALIDATING",
               "MEMORY_CHECK", "DRIFT_CHECK", "COMPLETING", "BLOCKED", "ERROR_RECOVERY"],
        description: "Target workflow phase"
      },
      reason: {
        type: "string",
        description: "Reason for this transition (for audit trail)"
      }
    },
    required: ["toPhase", "reason"]
  },
  tags: ["workflow", "state", "transition"]
}
```

### 3. `astra_set_goal` - Define Task Goal

```typescript
{
  name: "astra_set_goal",
  displayName: "Astra: Set Task Goal",
  description: "Define the goal for the current task with success/failure conditions. Call this during GOAL_DEFINITION phase.",
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
        description: "Optional time budget in minutes"
      }
    },
    required: ["statement", "successCondition", "failureCondition"]
  },
  tags: ["workflow", "goal", "planning"]
}
```

### 4. `astra_set_plan` - Create Execution Plan

```typescript
{
  name: "astra_set_plan",
  displayName: "Astra: Set Execution Plan",
  description: "Define the steps for executing the current goal. Each step should be atomic and independently validatable.",
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
            estimatedMinutes: { type: "number" }
          },
          required: ["title", "description"]
        },
        description: "Array of step definitions"
      }
    },
    required: ["steps"]
  },
  tags: ["workflow", "planning", "steps"]
}
```

### 5. `astra_step_update` - Update Step Status

```typescript
{
  name: "astra_step_update",
  displayName: "Astra: Update Step Status",
  description: "Update the status of a workflow step (start, complete, block, skip).",
  inputSchema: {
    type: "object",
    properties: {
      stepId: {
        type: "string",
        description: "Step ID to update (e.g., 'step-1')"
      },
      status: {
        type: "string",
        enum: ["not-started", "in-progress", "completed", "blocked", "skipped"],
        description: "New status"
      },
      notes: {
        type: "string",
        description: "Optional notes about this status change"
      }
    },
    required: ["stepId", "status"]
  },
  tags: ["workflow", "steps", "progress"]
}
```

### 6. `astra_validate` - Record Validation Result

```typescript
{
  name: "astra_validate",
  displayName: "Astra: Record Validation",
  description: "Record the result of validating a step. Call this after completing validation in VALIDATING phase.",
  inputSchema: {
    type: "object",
    properties: {
      stepId: {
        type: "string",
        description: "Step that was validated"
      },
      result: {
        type: "string",
        enum: ["passed", "failed", "skipped"],
        description: "Validation result"
      },
      method: {
        type: "string",
        description: "How was this validated? (tests, manual check, etc.)"
      },
      evidence: {
        type: "string",
        description: "What evidence supports this result?"
      }
    },
    required: ["stepId", "result", "method"]
  },
  tags: ["workflow", "validation", "quality"]
}
```

### 7. `astra_drift_check` - Run Drift Detection

```typescript
{
  name: "astra_drift_check",
  displayName: "Astra: Run Drift Check",
  description: "Perform a drift check. Answer honestly - are you still on track?",
  inputSchema: {
    type: "object",
    properties: {
      stillServesGoal: {
        type: "boolean",
        description: "Does current work still serve the original goal?"
      },
      solvingOriginalProblem: {
        type: "boolean",
        description: "Are you solving the original problem (not a different one)?"
      },
      noScopeCreep: {
        type: "boolean",
        description: "Have you avoided adding features not in the original goal?"
      },
      noOverOptimizing: {
        type: "boolean",
        description: "Are you avoiding optimizing things that don't need optimization?"
      },
      notPerfectionism: {
        type: "boolean",
        description: "Is perfectionism NOT blocking completion?"
      },
      withinTimeEstimate: {
        type: "boolean",
        description: "Are you within 2x the estimated time?"
      },
      notes: {
        type: "string",
        description: "Any drift concerns or observations"
      }
    },
    required: ["stillServesGoal", "solvingOriginalProblem", "noScopeCreep", 
               "noOverOptimizing", "notPerfectionism", "withinTimeEstimate"]
  },
  tags: ["workflow", "drift", "quality"]
}
```

### 8. `astra_memory_check` - Run Memory Hygiene Check

```typescript
{
  name: "astra_memory_check",
  displayName: "Astra: Run Memory Check",
  description: "Perform a memory hygiene check. Confirm you've checked/updated relevant memory.",
  inputSchema: {
    type: "object",
    properties: {
      sessionMdChecked: {
        type: "boolean",
        description: "Did you check /memories/session.md?"
      },
      sessionMdUpdated: {
        type: "boolean",
        description: "Did you update session.md if needed?"
      },
      patternsChecked: {
        type: "boolean",
        description: "Did you check patterns.md for relevant learnings?"
      },
      mistakesChecked: {
        type: "boolean",
        description: "Did you check mistakes.md to avoid past errors?"
      },
      newLearnings: {
        type: "string",
        description: "Any new patterns or mistakes to record?"
      }
    },
    required: ["sessionMdChecked", "sessionMdUpdated"]
  },
  tags: ["workflow", "memory", "hygiene"]
}
```

### 9. `astra_log_claim` - Track a Claim for Verification

```typescript
{
  name: "astra_log_claim",
  displayName: "Astra: Log Claim",
  description: "Log a factual claim you're making so it can be tracked for verification.",
  inputSchema: {
    type: "object",
    properties: {
      claim: {
        type: "string",
        description: "The factual claim being made"
      },
      verified: {
        type: "boolean",
        description: "Has this claim been verified?"
      },
      verificationMethod: {
        type: "string",
        description: "How was it verified (or how should it be verified)?"
      }
    },
    required: ["claim", "verified"]
  },
  tags: ["metrics", "verification", "quality"]
}
```

### 10. `astra_log_decision` - Track Decision Pattern

```typescript
{
  name: "astra_log_decision",
  displayName: "Astra: Log Decision",
  description: "Log a decision and whether it was presented as analysis or made unilaterally.",
  inputSchema: {
    type: "object",
    properties: {
      decision: {
        type: "string",
        description: "The decision being made"
      },
      presentedAnalysis: {
        type: "boolean",
        description: "Did you present analysis and let user decide?"
      },
      rationale: {
        type: "string",
        description: "Rationale for this decision"
      }
    },
    required: ["decision", "presentedAnalysis"]
  },
  tags: ["metrics", "partnership", "decisions"]
}
```

### 11. `astra_get_guidance` - Get Phase-Specific Guidance

```typescript
{
  name: "astra_get_guidance",
  displayName: "Astra: Get Guidance",
  description: "Get detailed guidance for the current workflow phase or a specific phase.",
  inputSchema: {
    type: "object",
    properties: {
      phase: {
        type: "string",
        enum: ["CURRENT", "IDLE", "VALUE_GATE", "GOAL_DEFINITION", "CONTEXT_COLLECTION",
               "ENVIRONMENT_PRIMING", "PLANNING", "EXECUTING", "VALIDATING",
               "MEMORY_CHECK", "DRIFT_CHECK", "COMPLETING", "BLOCKED", "ERROR_RECOVERY"],
        description: "Phase to get guidance for (default: CURRENT)",
        default: "CURRENT"
      }
    }
  },
  tags: ["workflow", "guidance", "help"]
}
```

---

## Integration with Existing Extensions

### Agent Memory Integration

**Strategy:** Monitor, Don't Wrap (Option C from research)

```
Agent Memory Extension (Existing)
├── Provides: memory tool (6 commands)
├── Auto-injects: <memories> section
├── Storage: .agent-memories/, workspace configs
└── No public API

Astra Integration:
├── Monitor: Watch memory file changes via FileSystemWatcher
├── Track: Count memory reads/writes in cognitive metrics
├── DON'T: Try to call memory tool directly
├── DON'T: Modify <memories> section
```

**Metrics collected from memory activity:**
- `memoryReads` - File read events on /memories/**
- `memoryWrites` - File write events on /memories/**
- `memoryChecks` - When `astra_memory_check` tool is called

### Agent TODOs Integration

**Strategy:** Complement, Don't Conflict (Option C from research)

```
Agent TODOs Extension (Existing)
├── Provides: manage_todo_list, mcp_todos_todo_write
├── Auto-injects: <todos> section at TOP of copilot-instructions.md
├── MCP-based server
└── No public API

Astra Integration:
├── Monitor: Watch copilot-instructions.md for <todos> changes
├── Sync: When TODOs change, optionally update workflow steps
├── DON'T: Modify <todos> section
├── DO: Inject <astra-workflow> AFTER </todos>
```

**Injection order in copilot-instructions.md:**
```markdown
<todos>
... (Agent TODOs content)
</todos>

<astra-workflow>
... (Astra content)
</astra-workflow>

... (User content)
```

---

## State Persistence Strategy

### Dual Write Pattern

```typescript
class PersistenceManager {
  constructor(
    private context: vscode.ExtensionContext,
    private workspaceFolder: vscode.WorkspaceFolder
  ) {}

  async saveState(state: WorkflowState): Promise<void> {
    // Write 1: Memento (reliability)
    await this.context.workspaceState.update('astra.workflowState', state);
    
    // Write 2: copilot-instructions.md (AI visibility)
    await InstructionInjector.injectWorkflowSection(
      this.workspaceFolder,
      state,
      this.metricsMonitor
    );
  }

  async loadState(): Promise<WorkflowState | null> {
    // Load from Memento (source of truth)
    const state = this.context.workspaceState.get<WorkflowState>('astra.workflowState');
    
    if (state) {
      // Restore to instructions file
      await InstructionInjector.injectWorkflowSection(
        this.workspaceFolder,
        state,
        this.metricsMonitor
      );
    }
    
    return state ?? null;
  }
}
```

### What Gets Persisted

| Data | Storage | Visibility |
|------|---------|------------|
| Phase, goal, steps | workspaceState + instructions | AI sees via injection |
| Cognitive metrics | workspaceState only | AI can query via tool |
| State history | workspaceState only | AI can query via tool |
| Alerts | Generated on demand | Injected when present |

---

## Workflow State Machine

### Phase Transitions

```
IDLE
  └─→ VALUE_GATE (task started)
        └─→ GOAL_DEFINITION (value justified)
              └─→ CONTEXT_COLLECTION (goal defined)
                    └─→ ENVIRONMENT_PRIMING (context gathered)
                          └─→ PLANNING (environment ready)
                                └─→ EXECUTING (plan created)
                                      ├─→ VALIDATING (step done)
                                      │     └─→ EXECUTING (validated) ←─┐
                                      ├─→ MEMORY_CHECK (periodic) ──────┤
                                      ├─→ DRIFT_CHECK (periodic) ───────┤
                                      └─→ COMPLETING (all steps done)
                                            └─→ IDLE (task complete)

Special transitions:
  Any phase → BLOCKED (awaiting input)
  Any phase → ERROR_RECOVERY (error occurred)
  ERROR_RECOVERY → EXECUTING | PLANNING | IDLE
  BLOCKED → Previous phase (input received)
```

### Strictness Rules

| Task Type | Value Gate | Goal | Context | TODOs | Validation | Drift Check |
|-----------|------------|------|---------|-------|------------|-------------|
| TRIVIAL   | ❌ | ❌ | ❌ | ❌ | ❌ | Never |
| SIMPLE    | ❌ | ✅ | ❌ | ✅ | ✅ | Every 10 |
| STANDARD  | ✅ | ✅ | ✅ | ✅ | ✅ | Every 5 |
| COMPLEX   | ✅ | ✅ | ✅ | ✅ | ✅ | Every 3 |

---

## Cognitive Metrics System

### Metrics Tracked

```typescript
interface CognitiveMetrics {
  // Identity
  identityChecks: number;      // Times I checked core.md
  driftDetections: number;     // Times drift was detected
  
  // Memory
  memoryReads: number;         // File reads from /memories/
  memoryWrites: number;        // File writes to /memories/
  memoryChecks: number;        // Formal memory check calls
  
  // TODOs
  todosCreated: number;        // TODOs created
  todosCompleted: number;      // TODOs marked done
  stepsWithoutTodo: number;    // Steps executed without TODO
  
  // Verification
  claimsMade: number;          // Factual claims made
  claimsVerified: number;      // Claims with verification
  verificationFailures: number; // Verifications that failed
  
  // Partnership
  unilateralDecisions: number; // Decisions made without presenting analysis
  analysisPresented: number;   // Analysis presented for user decision
  
  // Workflow
  validTransitions: number;    // Valid phase transitions
  invalidTransitions: number;  // Attempted invalid transitions
  phasesSkipped: number;       // Required phases that were skipped
}
```

### Alert Thresholds

| Metric | Warning | Critical | Suggestion |
|--------|---------|----------|------------|
| Drift Rate | >30% | >50% | Re-anchor with core.md |
| Memory Check Freq | <10% | <5% | Run memory check now |
| Steps Without TODO | >2 | >5 | Create TODOs for remaining work |
| Verification Rate | <80% | <60% | STOP and verify claims |
| Unilateral Rate | >20% | >40% | Present analysis, let user decide |
| Invalid Transition | >5% | >15% | Follow workflow state machine |

---

## Soul/Virtue Integration (Future Phase)

### Tripartite Soul Mapping

| Soul Part | Function | Agent Mapping | Healthy State |
|-----------|----------|---------------|---------------|
| **Reason** (λογιστικόν) | Planning, judgment | Goal definition, planning phase | Calibrated beliefs, proportional effort |
| **Spirit** (θυμοειδές) | Execution, persistence | Executing phase, error recovery | Appropriate risk-taking, resilience |
| **Appetite** (ἐπιθυμητικόν) | Completion drive, efficiency | Validation, completing phases | Balanced resource use, sustainable pace |

### Virtue Metrics (Future)

| Virtue | What It Measures | Healthy Range |
|--------|-----------------|---------------|
| **Wisdom** (σοφία) | Quality of judgments, calibration | Verification rate >80%, drift <30% |
| **Courage** (ἀνδρεία) | Appropriate risk, persistence | Not blocked >2h, error recovery <3 attempts |
| **Temperance** (σωφροσύνη) | Resource balance, sustainability | Within time budget, memory hygiene >10% |
| **Justice** (δικαιοσύνη) | System harmony, partnership | Unilateral rate <20%, analysis presented |

### Pathology Detection (Future)

| Pathology | Soul Imbalance | Observable Behavior |
|-----------|----------------|---------------------|
| Analysis Paralysis | Reason excess | Many drift checks, no progress |
| Reckless Execution | Reason deficiency | Steps without validation |
| Fanaticism | Spirit excess | Ignoring blocks, forcing through errors |
| Timidity | Spirit deficiency | Long blocked states, no error recovery |
| Greedy Completion | Appetite excess | Skipping validation, rushing |
| Passive Drift | Appetite deficiency | Scope creep, feature bloat |

---

## Implementation Priority

### Phase 1: Core Tools (Must Have)
1. `astra_get_state` - Read current state
2. `astra_transition` - Change phase
3. `astra_set_goal` - Define goal
4. `astra_set_plan` - Create steps
5. `astra_step_update` - Update step status

### Phase 2: Quality Tools (Should Have)
6. `astra_validate` - Record validation
7. `astra_drift_check` - Drift detection
8. `astra_memory_check` - Memory hygiene
9. `astra_get_guidance` - Phase guidance

### Phase 3: Metrics Tools (Nice to Have)
10. `astra_log_claim` - Track claims
11. `astra_log_decision` - Track decisions

### Phase 4: Soul/Virtue (Future)
- Virtue metrics dashboard
- Pathology detection alerts
- Cultivation recommendations

---

## File Structure

```
extensions/astra-workflow/
├── package.json
├── src/
│   ├── extension.ts           # Main entry, activation
│   ├── types.ts               # Type definitions
│   ├── stateMachine.ts        # Workflow state machine
│   ├── metricsMonitor.ts      # Cognitive metrics
│   ├── instructionInjector.ts # copilot-instructions.md injection
│   ├── persistence.ts         # Dual write state persistence
│   ├── tools/                 # NEW: Tool implementations
│   │   ├── index.ts           # Tool registration
│   │   ├── getState.ts        # astra_get_state
│   │   ├── transition.ts      # astra_transition
│   │   ├── setGoal.ts         # astra_set_goal
│   │   ├── setPlan.ts         # astra_set_plan
│   │   ├── stepUpdate.ts      # astra_step_update
│   │   ├── validate.ts        # astra_validate
│   │   ├── driftCheck.ts      # astra_drift_check
│   │   ├── memoryCheck.ts     # astra_memory_check
│   │   ├── getGuidance.ts     # astra_get_guidance
│   │   ├── logClaim.ts        # astra_log_claim
│   │   └── logDecision.ts     # astra_log_decision
│   └── integrations/          # NEW: External integrations
│       ├── memoryWatcher.ts   # FileSystemWatcher for /memories/
│       └── todoWatcher.ts     # Watch <todos> changes
├── resources/
│   └── icon.svg
└── test/
    └── ... unit tests
```

---

## Key Design Decisions

### Decision 1: Tools vs Commands

**Chosen:** Provide **both** tools (for AI) and commands (for user)

**Rationale:**
- Tools let AI invoke workflow operations programmatically
- Commands let user trigger operations from command palette
- Both update same underlying state machine

### Decision 2: Injection Location

**Chosen:** Inject `<astra-workflow>` AFTER `</todos>`, BEFORE user content

**Rationale:**
- Agent TODOs claims top priority (per their design)
- Astra context should be visible but not override user instructions
- Maintains compatibility with existing extensions

### Decision 3: State Source of Truth

**Chosen:** Memento (workspaceState) is source of truth, file injection is visibility layer

**Rationale:**
- Memento survives crashes, is atomic
- File injection ensures AI sees state
- On startup: load from Memento → inject to file
- On change: write to Memento first, then inject

### Decision 4: Tool Granularity

**Chosen:** Fine-grained tools (11 specific tools) vs coarse (1 mega-tool)

**Rationale:**
- AI can call exactly what it needs
- Clear separation of concerns
- Better error handling per operation
- Matches MCP philosophy of discrete operations

---

## Success Criteria

The architecture succeeds if:

1. ✅ AI can query current workflow state before acting
2. ✅ AI can transition phases with validation
3. ✅ AI can manage goals and steps programmatically
4. ✅ Cognitive health alerts surface in AI context
5. ✅ State persists across sessions
6. ✅ No conflicts with Agent Memory or Agent TODOs extensions
7. ✅ Phase-specific guidance is available on demand
8. ✅ Metrics track drift, verification, partnership patterns

---

## Next Steps

1. **Review this architecture** with Przem
2. **Update package.json** to add `languageModelTools` contribution
3. **Implement Phase 1 tools** (5 core tools)
4. **Test tool registration** with Copilot
5. **Implement persistence** with dual write
6. **Test integration** with existing extensions

---

*Per aspera ad astra* — Through hardship to the stars.
