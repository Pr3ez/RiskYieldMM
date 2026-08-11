"""Compatibility wrapper for the exploratory EMA gate diagnostic."""

from __future__ import annotations

from regression_feature_engineering.walkforward.experimental.ema_gate import *  # noqa: F401,F403
from regression_feature_engineering.walkforward.experimental.ema_gate import main


if __name__ == "__main__":
    raise SystemExit(main())
