"""Audit Python files for maintainability documentation gaps.

This is an advisory maintenance tool, not a style gate. It helps us track the
rollout of module/class/function docstrings across a large research codebase
without forcing noisy comments onto every private helper.
"""

from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
from pathlib import Path


DEFAULT_ROOTS = ("scripts", "notebooks", "fetchingByBit", "fetchingMultiAsset")
DEFAULT_EXCLUDE_PARTS = {
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "node_modules",
}


@dataclass(frozen=True)
class FileDocumentationReport:
    """One file-level documentation audit result."""

    path: Path
    has_module_docstring: bool
    public_classes: int
    public_classes_missing_docstring: int
    public_functions: int
    public_functions_missing_docstring: int

    @property
    def needs_attention(self) -> bool:
        return (
            not self.has_module_docstring
            or self.public_classes_missing_docstring > 0
            or self.public_functions_missing_docstring > 0
        )


def _is_public_name(name: str) -> bool:
    return not name.startswith("_")


def _iter_python_files(roots: list[Path]) -> list[Path]:
    files: list[Path] = []
    for root in roots:
        if root.is_file() and root.suffix == ".py":
            files.append(root)
            continue
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            if DEFAULT_EXCLUDE_PARTS.intersection(path.parts):
                continue
            files.append(path)
    return sorted(set(files), key=lambda path: str(path))


def audit_file(path: Path) -> FileDocumentationReport:
    """Parse one Python file and count missing top-level public docstrings."""

    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    has_module_docstring = ast.get_docstring(tree) is not None

    public_classes = 0
    public_classes_missing = 0
    public_functions = 0
    public_functions_missing = 0
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and _is_public_name(node.name):
            public_classes += 1
            if ast.get_docstring(node) is None:
                public_classes_missing += 1
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and _is_public_name(
            node.name
        ):
            public_functions += 1
            if ast.get_docstring(node) is None:
                public_functions_missing += 1

    return FileDocumentationReport(
        path=path,
        has_module_docstring=has_module_docstring,
        public_classes=public_classes,
        public_classes_missing_docstring=public_classes_missing,
        public_functions=public_functions,
        public_functions_missing_docstring=public_functions_missing,
    )


def render_markdown(reports: list[FileDocumentationReport]) -> str:
    """Render audit results as a compact Markdown checklist."""

    total = len(reports)
    needs_attention = [report for report in reports if report.needs_attention]
    lines = [
        "# Python Documentation Audit",
        "",
        f"Files scanned: {total}",
        f"Files needing attention: {len(needs_attention)}",
        "",
        "| File | Module docstring | Public classes missing | Public functions missing |",
        "|---|---:|---:|---:|",
    ]
    for report in needs_attention:
        lines.append(
            "| "
            f"`{report.path}` | "
            f"{'yes' if report.has_module_docstring else 'no'} | "
            f"{report.public_classes_missing_docstring}/{report.public_classes} | "
            f"{report.public_functions_missing_docstring}/{report.public_functions} |"
        )
    lines.append("")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for the documentation audit."""
    parser = argparse.ArgumentParser(
        description="Audit Python module/class/function docstring coverage."
    )
    parser.add_argument(
        "--roots",
        nargs="+",
        default=list(DEFAULT_ROOTS),
        help="Files or directories to scan.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional Markdown output path. Prints to stdout when omitted.",
    )
    return parser.parse_args()


def main() -> int:
    """Run the audit and write Markdown to stdout or `--output`."""
    args = parse_args()
    roots = [Path(root) for root in args.roots]
    reports = [audit_file(path) for path in _iter_python_files(roots)]
    markdown = render_markdown(reports)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(markdown, encoding="utf-8")
    else:
        print(markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
