"""Compatibility wrapper for Optuna RPF binary classification.

Public command:

    python -m regression_feature_engineering.walkforward.classify_optuna
"""

from __future__ import annotations

from regression_feature_engineering.walkforward.classification.optuna_cli import main


if __name__ == "__main__":
    raise SystemExit(main())
