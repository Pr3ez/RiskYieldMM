"""
Output Adapter Module

Contains output handling utilities:
- DualOutput: Write output to both console and log file

Used for capturing backtest logs to file while showing progress.
"""

from __future__ import annotations

import sys
from pathlib import Path


class DualOutput:
    """Write output to both console and log file.

    Usage:
        dual = DualOutput(Path("backtest.log"))
        sys.stdout = dual
        print("This goes to both console and file")
        dual.close()
        sys.stdout = dual.terminal  # Restore original stdout
    """

    def __init__(self, log_path: Path):
        """Initialize dual output.

        Args:
            log_path: Path to log file (created/overwritten)
        """
        self.terminal = sys.stdout
        self.log_file = open(log_path, "w", encoding="utf-8")

    def write(self, message: str) -> None:
        """Write to both terminal and log file."""
        self.terminal.write(message)
        self.log_file.write(message)
        self.log_file.flush()  # Ensure immediate write

    def flush(self) -> None:
        """Flush both outputs."""
        self.terminal.flush()
        self.log_file.flush()

    def close(self) -> None:
        """Close the log file."""
        self.log_file.close()


# Exports
__all__ = ["DualOutput"]
