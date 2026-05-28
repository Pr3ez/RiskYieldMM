"""I/O boundary placeholders for the regression feature workflow.

Future implementation should centralize all reads and writes here so formulas
stay separate from artifact layout policy.
"""

from __future__ import annotations

from pathlib import Path


def ensure_artifact_root(path: Path) -> Path:
    """Return an artifact root path without writing files in scaffold mode."""
    return path

