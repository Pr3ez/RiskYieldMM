---
name: notion-ml-worklog
description: |
  Create or update ML worklog entries in the Notion database for this repo with deterministic fields (Date, Name, Status, Scope, Linear URL, Summary, Artifacts, Next Actions). Use when a substantial task needs traceable run documentation. Do not use for ad-hoc notes without structured fields.
---

# Notion ML Worklog

## Inputs
- Date
- Name
- Status: `START`, `IN_PROGRESS`, `BLOCKER`, `DONE`
- Scope
- Linear Issue URL
- Summary
- Artifacts
- Next Actions

## Workflow
1. Load database context from `references/notion_context.md`.
2. Validate required fields using `scripts/worklog_entry.py`.
3. Create or update a row in the Notion worklog data source.
4. Save deterministic local artifact for auditing.

## Local Artifact
Write `notion_worklog_state.json` in output directory.
