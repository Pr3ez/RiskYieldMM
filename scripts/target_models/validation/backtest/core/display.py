"""
Robust table display utilities for backtest output.

This module provides a flexible, maintainable way to format console tables.
Column definitions are in one place - change once, works everywhere.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class Column:
    """Single column definition."""

    name: str
    width: int
    align: str = ">"  # '<' left, '>' right, '^' center

    def format_header(self) -> str:
        """Format the column header."""
        if self.align == "<":
            return f"{self.name:<{self.width}}"
        elif self.align == "^":
            return f"{self.name:^{self.width}}"
        else:
            return f"{self.name:>{self.width}}"

    def format_value(self, value: Any, fmt: str = "") -> str:
        """
        Format a value for this column.

        Args:
            value: The value to format
            fmt: Optional format spec (e.g., '.3f', '.1f%')
        """
        if value is None:
            formatted = "-"
        elif fmt:
            # Handle special format specs
            if fmt.endswith("%"):
                # Percentage format: '.1f%' means format as float then add %
                num_fmt = fmt[:-1]
                formatted = f"{value:{num_fmt}}%"
            else:
                formatted = f"{value:{fmt}}"
        else:
            formatted = str(value)

        # Apply alignment
        if self.align == "<":
            return f"{formatted:<{self.width}}"
        elif self.align == "^":
            return f"{formatted:^{self.width}}"
        else:
            return f"{formatted:>{self.width}}"


@dataclass
class TableFormatter:
    """
    Robust table formatter with auto-aligned columns.

    Usage:
        table = TableFormatter(
            columns=[
                Column("Config", 24, "<"),
                Column("Pred", 10, ">"),
                Column("Actual", 10, ">"),
            ],
            separator=" "
        )
        print(table.header())
        print(table.divider())
        print(table.row(["direction_1bar", "BULLISH", "NEUTRAL"]))
    """

    columns: list[Column]
    separator: str = " "
    divider_char: str = "-"

    def __post_init__(self):
        """Calculate total width."""
        self._total_width = sum(c.width for c in self.columns) + len(self.separator) * (
            len(self.columns) - 1
        )

    @property
    def total_width(self) -> int:
        """Total width including separators."""
        return self._total_width

    def header(self) -> str:
        """Generate the header row."""
        return self.separator.join(c.format_header() for c in self.columns)

    def divider(self, char: str | None = None) -> str:
        """Generate a divider line."""
        c = char or self.divider_char
        return c * self._total_width

    def row(self, values: list[Any], formats: list[str] | None = None) -> str:
        """
        Generate a data row.

        Args:
            values: List of values (one per column)
            formats: Optional list of format specs (one per column)
        """
        if len(values) != len(self.columns):
            raise ValueError(f"Expected {len(self.columns)} values, got {len(values)}")

        formats = formats or [""] * len(self.columns)
        if len(formats) != len(self.columns):
            raise ValueError(
                f"Expected {len(self.columns)} formats, got {len(formats)}"
            )

        return self.separator.join(
            col.format_value(val, fmt)
            for col, val, fmt in zip(self.columns, values, formats)
        )


# =============================================================================
# PRE-DEFINED TABLE LAYOUTS
# =============================================================================
# These are the single source of truth for all backtest display tables.
# To modify a table: change it here, and ALL usages update automatically.

# LATEST PRED vs ACTUAL - Classification
PRED_ACTUAL_CLS_TABLE = TableFormatter(
    columns=[
        Column("Config", 22, "<"),
        Column("Pred", 18, ">"),  # Wide enough for TREND_FOLLOW_LONG
        Column("Actual", 18, ">"),  # Wide enough for MEAN_REVERT_SHORT
        Column("Match", 5, ">"),
        Column("|", 1, ">"),
        Column("Correct", 7, ">"),
        Column("Acc%", 6, ">"),
        Column("W_Corr", 6, ">"),  # Weighted correct (e.g., "2.5/3")
        Column("W_Acc%", 7, ">"),
    ],
    separator=" ",
)

# LATEST PRED vs ACTUAL - Regression
PRED_ACTUAL_REG_TABLE = TableFormatter(
    columns=[
        Column("Config", 24, "<"),
        Column("Pred", 10, ">"),
        Column("Actual", 10, ">"),
        Column("Err%", 8, ">"),
        Column("|", 2, ">"),
        Column("Cum Pred", 10, ">"),
        Column("Cum Act", 10, ">"),
        Column("Cum Err%", 9, ">"),
    ],
    separator=" ",
)

# CLASSIFICATION summary table
CLASSIFICATION_TABLE = TableFormatter(
    columns=[
        Column("Config", 24, "<"),
        Column("Ens", 5, ">"),
        Column("CB", 5, ">"),
        Column("LGB", 5, ">"),
        Column("LSTM", 5, ">"),
        Column("Lin", 5, ">"),
        Column("AUC", 5, ">"),
        Column("Prec", 5, ">"),
        Column("Rec", 5, ">"),
        Column("F1", 5, ">"),
        Column("N", 4, ">"),
        Column("W_Acc", 6, ">"),
    ],
    separator=" ",
)

# REGRESSION summary table
REGRESSION_TABLE = TableFormatter(
    columns=[
        Column("Config", 20, "<"),
        Column("Ens_IC", 7, ">"),
        Column("CB_IC", 7, ">"),
        Column("LGB_IC", 7, ">"),
        Column("LSTM_IC", 7, ">"),
        Column("Lin_IC", 7, ">"),
        Column("RMSE", 10, ">"),
        Column("MAE", 10, ">"),
        Column("N", 5, ">"),
    ],
    separator=" ",
)

# RESULTS SUMMARY - Classification
RESULTS_CLS_TABLE = TableFormatter(
    columns=[
        Column("Config", 25, "<"),
        Column("Accuracy", 12, "<"),
        Column("F1", 12, "<"),
        Column("Coverage", 12, "<"),
        Column("N", 8, "<"),
    ],
    separator=" ",
)

# RESULTS SUMMARY - Regression
RESULTS_REG_TABLE = TableFormatter(
    columns=[
        Column("Config", 25, "<"),
        Column("IC", 12, "<"),
        Column("RMSE", 12, "<"),
        Column("Coverage", 12, "<"),
        Column("N", 8, "<"),
    ],
    separator=" ",
)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def format_pct(value: float | None, decimals: int = 1) -> str:
    """Format a percentage value (0-100 scale) with % sign."""
    if value is None:
        return "-"
    return f"{value:.{decimals}f}%"


def format_ratio(n: int, total: int) -> str:
    """Format as 'n/total' with consistent width."""
    return f"{n:>3}/{total:<3}"


def format_float(value: float | None, decimals: int = 3) -> str:
    """Format a float with consistent decimals."""
    if value is None:
        return "-"
    return f"{value:.{decimals}f}"
