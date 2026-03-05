---
name: ml-run-contract
description: |
  Validate ML run directories against a strict artifact contract and schema, including required files, metadata, and deterministic naming. Use when verifying experiment output integrity before ranking/reporting. Do not use for model training itself.
---

# ML Run Contract

## Purpose
Enforce run output consistency before downstream analysis.

## Inputs
- Run directory path
- Optional required artifact override list

## Outputs
- `run_manifest.json`
- `run_contract_report.json`

## Workflow
1. Load schema from `assets/run_manifest.schema.json`.
2. Validate required files exist.
3. Validate JSON manifest shape.
4. Emit pass/fail report.

## Shared Templates
- `assets/linear_done_comment_template.md`
- `assets/notion_worklog_row_template.json`
