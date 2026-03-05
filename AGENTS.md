# Default Task Tracking Policy

For substantial tasks in this repository, use this tracking workflow by default.

## Linear

- Team: `Riskyieldmetamodelalgorithm`
- Project: `Codex Execution Log`
- Project URL: `https://linear.app/riskyieldmetamodelalgorithm/project/codex-execution-log-21c6e9703030`

Required behavior:
1. Create or update one Linear issue per substantial task.
2. Post milestone comments:
   - `START`
   - `BLOCKER` (only when blocked)
   - `DONE`
3. In the `DONE` comment include:
   - technical summary
   - artifact paths/URLs
   - key metrics (if applicable)

## Notion

- Worklog database: `Codex Worklog - RiskYieldMM`
- Database URL: `https://www.notion.so/2b2ea8036438400ab020835477d248c3`
- Data source ID: `6b08e332-c2fd-4194-a577-237b776cf372`

Required behavior:
1. Add one row per substantial task.
2. Populate fields:
   - `Name`
   - `Status` (`START` / `IN_PROGRESS` / `BLOCKER` / `DONE`)
   - `Scope`
   - `Linear Issue`
   - `Summary`
   - `Artifacts`
   - `Next Actions`
   - `Date`

## Scope Definition

A task is substantial if it includes one or more of:
- code edits affecting behavior
- model training/evaluation runs
- multi-step analysis producing artifacts
- non-trivial debugging/refactoring

For minor Q&A or one-line clarifications, tracking is optional.
