from __future__ import annotations

import subprocess
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_pyproject_declares_canonical_dependency_surfaces() -> None:
    pyproject = (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    requirements_ci = (PROJECT_ROOT / "requirements-ci.txt").read_text(
        encoding="utf-8"
    )

    assert "[project]" in pyproject
    assert "dependencies = [" in pyproject
    assert "[project.optional-dependencies]" in pyproject
    assert "ci = [" in pyproject
    assert "dev = [" in pyproject
    assert "research = [" in pyproject
    assert "rust = [" in pyproject

    for dependency in (
        "polars>=1.0",
        "pyarrow>=15",
        "scikit-learn>=1.4",
        "requests>=2.31",
    ):
        assert f'"{dependency}"' in pyproject

    assert requirements_ci.strip() == "-e .[ci]"


def test_no_tracked_backup_files_in_maintained_source_surface() -> None:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=20,
    )

    offenders = [
        path
        for path in result.stdout.splitlines()
        if (
            path.startswith("scripts/")
            or (path.startswith("notebooks/") and not path.startswith("notebooks/notes/"))
        )
        and (
            ".bak" in path
            or path.endswith("_backup.py")
            or "_backup_" in path
        )
    ]

    assert offenders == []
