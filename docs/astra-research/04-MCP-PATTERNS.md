# MCP Research - Model Context Protocol Patterns

**Status**: ✅ COMPLETE
**Date**: Session research document
**Purpose**: Understand MCP for Astra Consciousness Extension architecture decisions

---

## Executive Summary

MCP (Model Context Protocol) is an **open standard for connecting AI applications to external systems** - described as "USB-C for AI." It provides a standardized way to connect AI apps to data sources, tools, and workflows.

**Key Finding for Astra**: VS Code Copilot Chat already implements MCP internally. Extensions like Agent TODOs use MCP tools via `@modelcontextprotocol/sdk`. Astra can register tools via VS Code's `languageModelTools` contribution point OR implement an MCP server. The `languageModelTools` approach is simpler for VS Code-specific extensions.

---

## 1. MCP Core Architecture

### 1.1 Three Participants

```
┌─────────────────────────────────────────────────────────────────┐
│                     MCP ARCHITECTURE                            │
└─────────────────────────────────────────────────────────────────┘
                              │
          ┌───────────────────┼───────────────────┐
          │                   │                   │
          ▼                   ▼                   ▼
    ┌──────────┐       ┌──────────┐       ┌──────────┐
    │   HOST   │       │  CLIENT  │       │  SERVER  │
    │ (AI App) │◄─────►│(Connector)│◄─────►│ (Tools)  │
    └──────────┘       └──────────┘       └──────────┘
         │                   │                   │
    Claude Desktop     MCP Client         MCP Server
    VS Code Copilot    (in-process)       (local/remote)
```

- **Host**: AI application (Claude Desktop, VS Code with Copilot)
- **Client**: Connector process that maintains connection to server
- **Server**: Provides tools, resources, prompts to clients

### 1.2 Two Layers

| Layer | Purpose | Protocol |
|-------|---------|----------|
| **Data Layer** | JSON-RPC based protocol, lifecycle, primitives | JSON-RPC 2.0 |
| **Transport Layer** | Communication channels, auth | STDIO or Streamable HTTP |

### 1.3 Transports

| Transport | Use Case | Communication |
|-----------|----------|---------------|
| **STDIO** | Local processes on same machine | stdin/stdout pipes |
| **Streamable HTTP** | Remote servers | HTTP POST + Server-Sent Events |

---

## 2. MCP Primitives (The Important Part)

### 2.1 Three Core Server Primitives

| Primitive | Purpose | Discovery | Execution |
|-----------|---------|-----------|-----------|
| **Tools** | Executable functions AI can invoke | `tools/list` | `tools/call` |
| **Resources** | Data sources providing context | `resources/list` | `resources/read` |
| **Prompts** | Reusable templates for LLM interactions | `prompts/list` | `prompts/get` |

### 2.2 Tool Definition Schema

```json
{
  "name": "unique_tool_identifier",
  "title": "Human Readable Name",
  "description": "What the tool does and when to use it",
  "inputSchema": {
    "type": "object",
    "properties": {
      "param1": { "type": "string", "description": "..." }
    },
    "required": ["param1"]
  },
  "outputSchema": { /* optional JSON Schema for output */ },
  "annotations": { /* optional metadata */ }
}
```

### 2.3 Tool Call Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                     TOOL EXECUTION FLOW                         │
└─────────────────────────────────────────────────────────────────┘

1. DISCOVERY                    2. INVOCATION
   Client → Server                 Client → Server
   
   {                               {
     "method": "tools/list"          "method": "tools/call",
   }                                 "params": {
                                       "name": "tool_name",
   Server → Client                     "arguments": { ... }
                                     }
   {                               }
     "result": {
       "tools": [...]              Server → Client
     }                             
   }                               {
                                     "result": {
                                       "content": [...],
                                       "isError": false
                                     }
                                   }
```

### 2.4 Resource Definition

Resources provide **contextual data** (files, database records, API responses):

```json
{
  "uri": "file:///project/src/main.rs",
  "name": "main.rs",
  "description": "Primary application entry point",
  "mimeType": "text/x-rust"
}
```

### 2.5 Prompt Definition

Prompts are **reusable templates** for LLM interactions:

```json
{
  "name": "code_review",
  "title": "Request Code Review",
  "description": "Asks the LLM to analyze code quality",
  "arguments": [
    {
      "name": "code",
      "description": "The code to review",
      "required": true
    }
  ]
}
```

---

## 3. MCP Lifecycle

### 3.1 Initialization Handshake

```
Client → Server: initialize
{
  "protocolVersion": "2025-06-18",
  "capabilities": { "elicitation": {} },
  "clientInfo": { "name": "example-client", "version": "1.0.0" }
}

Server → Client: initialize response
{
  "protocolVersion": "2025-06-18",
  "capabilities": {
    "tools": { "listChanged": true },
    "resources": {}
  },
  "serverInfo": { "name": "example-server", "version": "1.0.0" }
}

Client → Server: notifications/initialized
(no response expected)
```

### 3.2 Capability Negotiation

| Capability | Meaning |
|------------|---------|
| `tools: {}` | Server supports tools |
| `tools: { listChanged: true }` | Server will notify when tools change |
| `resources: {}` | Server supports resources |
| `prompts: {}` | Server supports prompts |

### 3.3 Notifications (Real-time Updates)

```json
{
  "jsonrpc": "2.0",
  "method": "notifications/tools/list_changed"
}
```

No response expected - client should re-fetch `tools/list` after receiving.

---

## 4. MCP in VS Code Context

### 4.1 How VS Code Implements MCP

VS Code Copilot acts as an **MCP Host**. It can connect to:
1. External MCP servers (local or remote)
2. Extension-provided tools via `languageModelTools`

### 4.2 Agent TODOs as MCP Example

From our research in `03-AGENT-TODOS.md`:

```json
{
  "contributes": {
    "mcp": {
      "servers": [
        {
          "label": "Agent TODOs",
          "type": "stdio",
          "command": "node",
          "args": ["${extensionLocation}/dist/mcp.js"]
        }
      ]
    }
  }
}
```

Agent TODOs registers as an MCP server with tools:
- `todo_read` - Read current todos
- `todo_write` - Write/update todos

### 4.3 languageModelTools vs MCP Server

| Approach | Pros | Cons |
|----------|------|------|
| **languageModelTools** | Simpler, VS Code-native, integrated with extension lifecycle | VS Code-specific, less portable |
| **MCP Server** | Portable, works with any MCP client, standard protocol | More complex setup, separate process |

**Decision for Astra**: Use `languageModelTools` for VS Code integration. Can add MCP server later for portability.

---

## 5. Relevance to Astra Extension

### 5.1 How Astra Could Use MCP Concepts

| MCP Concept | Astra Application |
|-------------|-------------------|
| **Tools** | Workflow state management, virtue metrics queries |
| **Resources** | Session context, cognitive state data |
| **Prompts** | Phase-specific instructions, virtue-guided responses |
| **Notifications** | State change alerts, phase transitions |

### 5.2 Astra Tool Candidates

```typescript
// Potential Astra tools (via languageModelTools)
const astraTools = [
  {
    name: "astra_getWorkflowState",
    description: "Get current workflow phase and valid transitions",
    inputSchema: { type: "object", properties: {} }
  },
  {
    name: "astra_transitionPhase",
    description: "Request transition to new workflow phase",
    inputSchema: {
      type: "object",
      properties: {
        targetPhase: { type: "string" },
        justification: { type: "string" }
      }
    }
  },
  {
    name: "astra_getVirtueMetrics",
    description: "Get current virtue-based cognitive health metrics",
    inputSchema: { type: "object", properties: {} }
  },
  {
    name: "astra_reportDrift",
    description: "Report cognitive drift or pathology detection",
    inputSchema: {
      type: "object",
      properties: {
        pathologyType: { type: "string" },
        indicators: { type: "array", items: { type: "string" } }
      }
    }
  }
];
```

### 5.3 Integration Strategy

```
┌─────────────────────────────────────────────────────────────────┐
│                 ASTRA INTEGRATION ARCHITECTURE                  │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                        VS CODE HOST                             │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                    COPILOT CHAT                           │  │
│  └───────────────────┬───────────────────────────────────────┘  │
│                      │                                          │
│  ┌───────────────────┼───────────────────────────────────────┐  │
│  │            languageModelTools Registration                │  │
│  │                     │                                     │  │
│  │  ┌─────────────────┼─────────────────────────────────┐   │  │
│  │  │                 │                                 │   │  │
│  │  ▼                 ▼                 ▼               │   │  │
│  │  memory          todo_read       astra_*             │   │  │
│  │  (Agent Memory)   (Agent TODOs)   (Astra)            │   │  │
│  └──────────────────────────────────────────────────────┘   │  │
│                                                              │  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 6. Key Patterns for Astra

### 6.1 Tool Registration Pattern

```typescript
// From package.json
{
  "contributes": {
    "languageModelTools": [
      {
        "name": "astra_getWorkflowState",
        "displayName": "Get Workflow State",
        "description": "Get current Astra workflow phase and cognitive metrics",
        "modelDescription": "Use to check current workflow phase, valid transitions, and virtue metrics",
        "inputSchema": { /* JSON Schema */ }
      }
    ]
  }
}

// From extension.ts
vscode.lm.registerTool('astra_getWorkflowState', {
  async invoke(options, token) {
    const state = workflowStateMachine.getCurrentState();
    const metrics = virtueMonitor.getMetrics();
    return new vscode.LanguageModelToolResult([
      new vscode.LanguageModelTextPart(JSON.stringify({ state, metrics }))
    ]);
  }
});
```

### 6.2 Context Injection Pattern

MCP **resources** are analogous to our instruction injection:

```typescript
// Inject workflow context into copilot-instructions.md
const workflowSection = `
<astra-workflow phase="${currentPhase}">
  <valid-transitions>${validTransitions.join(', ')}</valid-transitions>
  <virtue-metrics>
    <wisdom>${metrics.wisdom}</wisdom>
    <courage>${metrics.courage}</courage>
    <temperance>${metrics.temperance}</temperance>
    <justice>${metrics.justice}</justice>
  </virtue-metrics>
</astra-workflow>
`;
```

### 6.3 Notification Pattern

For real-time state changes:

```typescript
// When workflow state changes, notify
onWorkflowStateChange(newState => {
  // Option 1: Update instruction file (file watcher will catch it)
  updateInstructionsFile(newState);
  
  // Option 2: If we implemented MCP server
  // mcpServer.sendNotification('notifications/workflow/state_changed');
});
```

---

## 7. Decision Summary

### 7.1 For Astra Consciousness Extension

| Question | Decision | Rationale |
|----------|----------|-----------|
| Use MCP directly? | **No** - use VS Code APIs | VS Code abstracts MCP via `languageModelTools` |
| Register tools? | **Yes** - via `languageModelTools` | Simpler, native to VS Code |
| Implement MCP server? | **Maybe later** | For portability outside VS Code |
| Follow MCP patterns? | **Yes** | Good architecture patterns apply |

### 7.2 Key Takeaways

1. **MCP is the underlying protocol** that VS Code uses for LLM tools
2. **VS Code abstracts it** via `languageModelTools` contribution point
3. **Agent TODOs uses hybrid approach**: VS Code `languageModelTools` + MCP server
4. **For Astra**: Focus on VS Code-native APIs, follow MCP patterns
5. **Three primitives apply**: Tools (actions), Resources (data), Prompts (templates)

---

## 8. References

- [MCP Specification](https://modelcontextprotocol.io/specification/latest)
- [MCP Architecture](https://modelcontextprotocol.io/docs/learn/architecture)
- [MCP Tools](https://modelcontextprotocol.io/specification/2025-06-18/server/tools)
- [MCP Prompts](https://modelcontextprotocol.io/specification/2025-06-18/server/prompts)
- [VS Code languageModelTools](https://code.visualstudio.com/api/references/contribution-points#contributes.languageModelTools)

---

## 9. Next Steps

- [x] Understand MCP core concepts ✅
- [x] Identify how VS Code implements MCP ✅
- [x] Decide on integration approach ✅
- [ ] Research state persistence patterns (next task)
- [ ] Design Astra tool registrations
- [ ] Implement languageModelTools for Astra
