# Code Documentation Standard

This repository is large enough that comments need to be intentional. The goal
is maintainability, not line-by-line narration.

## What Every Maintained Python File Should Have

1. A module docstring at the top of the file:
   - what this file owns,
   - where it sits in the workflow,
   - important temporal/data-safety assumptions.

2. Public classes and public functions should have docstrings when their
   purpose is not immediately obvious from the name.

3. Complex internal helpers should have a short comment before the block that
   explains why the logic exists.

4. Environment variables, artifact paths, and local/generated data behavior
   should be described near the code that reads or writes them.

5. Look-ahead-sensitive logic must describe the time boundary:
   - what data is allowed,
   - what future-looking data is label-only,
   - what is excluded from model-facing features.

## What To Avoid

- Do not add comments that repeat the line of code.
- Do not explain standard Python syntax.
- Do not hide unclear code behind a long comment; refactor first when possible.
- Do not document generated/local artifact paths as if they are committed data.

## Recommended Module Header Shape

```python
"""Short module purpose.

Workflow position:
- where this module is called from,
- what artifacts it reads/writes,
- what it deliberately does not own.

Temporal/data contract:
- causal inputs,
- label-only future fields,
- local/generated artifact behavior.
"""
```

## Rollout Order

1. Active HTF and multi-asset source workflow.
2. Stage-1 and HTF analysis scripts.
3. Target-model and conformal modules.
4. Legacy/archived research scripts, marked clearly as historical where needed.

Use `scripts/maintenance/audit_python_documentation.py` to produce an inventory
of missing module, class, and function docstrings.
