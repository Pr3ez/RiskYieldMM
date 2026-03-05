---
name: research-continuity-orchestrator
description: |
  Enforce continuity for substantial ML research tasks by validating synchronized task state across Linear and Notion before and after runs. Use when starting, updating, or closing substantial tasks to guarantee START/IN_PROGRESS/BLOCKER/DONE transitions and required metadata (Linear issue, Notion page, artifacts/metrics on DONE). Do not use for trivial Q&A.
---

# Research Continuity Orchestrator

## Inputs
- `task_state.json` path
- Optional expected next status

## Workflow
1. Validate task state against `assets/task_state.schema.json`.
2. Run `scripts/state_guard.py` before major run execution.
3. Fail fast if tracking IDs are missing or status transition is invalid.
4. Require metrics/artifacts when status is `DONE`.

## Required Guarantees
- Substantial task has both `linear_issue` and `notion_page`.
- Status history follows: `START -> IN_PROGRESS/BLOCKER -> DONE`.
- `DONE` contains non-empty artifacts and metrics summary.

## Local Artifacts
- `state_guard_report.json` in output directory.

## Tools
- Local validation script only (no external side effects).
