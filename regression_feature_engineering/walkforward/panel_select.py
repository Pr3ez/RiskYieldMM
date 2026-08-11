"""Compatibility wrapper for experimental SHAP/panel selection work."""

from __future__ import annotations

from regression_feature_engineering.walkforward.experimental.panel_select import *  # noqa: F401,F403
from regression_feature_engineering.walkforward.experimental.panel_select import main


if __name__ == "__main__":
    raise SystemExit(main())
