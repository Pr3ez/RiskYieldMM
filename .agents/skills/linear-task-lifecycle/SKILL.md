---
name: linear-task-lifecycle
description: |
  Manage substantial-task issue lifecycle in Linear for this repo. Use when work should be tracked with START/BLOCKER/DONE milestones, issue state transitions (Todo/In Progress/Done), and deterministic final summaries with artifact paths. Do not use for trivial Q&A without deliverables.
---

# Linear Task Lifecycle

## Inputs
- Task title
- Scope and acceptance criteria
- Status transition: `START`, `BLOCKER`, or `DONE`
- Optional artifact paths/URLs and metrics summary
- Optional existing issue id/identifier

## Workflow
1. Resolve project and team from `references/linear_context.md`.
2. If no issue exists, create one in `Codex Execution Log`.
3. Transition state:
   - `START` -> `In Progress`
   - `BLOCKER` -> keep current started state and add blocker comment
   - `DONE` -> `Done`
4. Post milestone comment with deterministic headings.
5. Save local state JSON for reproducibility.

## Comment Contract
- `START`: scope, acceptance criteria
- `BLOCKER`: blocker, impact, unblock condition
- `DONE`: technical summary, key metrics, artifact/file paths, next actions

## Local Artifact
Write `linear_task_state.json` to the chosen output directory.

## Tools
This skill is designed to work with Linear MCP tools:
- create/list/update issue
- create comment
