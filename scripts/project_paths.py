"""Project-root path helpers.

Centralizes project-root resolution so runtime scripts do not depend on a
machine-local checkout path.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_ROOT_ENV_VAR = "RISKYIELDMM_PROJECT_ROOT"


def _candidate_roots(start: str | Path | None) -> list[Path]:
    if start is None:
        return []

    path = Path(start).expanduser()
    try:
        path = path.resolve()
    except FileNotFoundError:
        path = path.absolute()

    root = path if path.is_dir() else path.parent
    return [root, *root.parents]


def _looks_like_project_root(path: Path) -> bool:
    return (
        (path / "pyproject.toml").is_file()
        and (path / "scripts").is_dir()
        and (path / "README.md").is_file()
    )


def resolve_project_root(
    start: str | Path | None = None,
    *,
    env_var: str = PROJECT_ROOT_ENV_VAR,
) -> Path:
    """Resolve the RiskYieldMM project root.

    Resolution order:
    1. `RISKYIELDMM_PROJECT_ROOT` override, if set.
    2. Upward marker search from `start`.
    3. Upward marker search from the current working directory.
    """
    env_root = os.environ.get(env_var)
    if env_root:
        return Path(env_root).expanduser().resolve()

    seen: set[Path] = set()
    for candidate in [*_candidate_roots(start), *_candidate_roots(Path.cwd())]:
        if candidate in seen:
            continue
        seen.add(candidate)
        if _looks_like_project_root(candidate):
            return candidate

    raise RuntimeError(
        "Could not resolve RiskYieldMM project root. "
        f"Set {env_var} or run from inside the repository."
    )


def ensure_project_root_on_path(
    start: str | Path | None = None,
    *,
    env_var: str = PROJECT_ROOT_ENV_VAR,
) -> Path:
    """Resolve the project root and prepend it to `sys.path` if needed."""
    project_root = resolve_project_root(start=start, env_var=env_var)
    project_root_str = str(project_root)
    if project_root_str not in sys.path:
        sys.path.insert(0, project_root_str)
    return project_root
