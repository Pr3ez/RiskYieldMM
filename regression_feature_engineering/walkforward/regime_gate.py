"""Compatibility wrapper for exploratory learned regime-gate experiments."""

from __future__ import annotations

from regression_feature_engineering.walkforward.experimental.regime_gate import *  # noqa: F401,F403
from regression_feature_engineering.walkforward.experimental.regime_gate import main


if __name__ == "__main__":
    raise SystemExit(main())
