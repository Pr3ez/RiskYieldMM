"""Compatibility wrapper for exploratory separate decision-bank planning."""

from __future__ import annotations

from regression_feature_engineering.walkforward.experimental.decision_bank import *  # noqa: F401,F403
from regression_feature_engineering.walkforward.experimental.decision_bank import main


if __name__ == "__main__":
    raise SystemExit(main())
