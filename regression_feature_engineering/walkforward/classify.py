"""Compatibility wrapper for the RPF binary classification command.

The implementation lives under `regression_feature_engineering.walkforward.classification`.
Keep this module as the public command surface:

    python -m regression_feature_engineering.walkforward.classify
"""

from __future__ import annotations

from regression_feature_engineering.walkforward.classification.cli import (
    OUTPUT_ROOT,
    PROJECT_ROOT,
    best_trial as _best_trial,
    feature_label as _feature_label,
    main,
    model_choice_grid as _model_choice_grid,
    parse_args as _parse_args,
    run_root_for_args as _run_root,
    write_rows_parquet as _write_rows_parquet,
)
from regression_feature_engineering.walkforward.classification.data import (
    classification_numpy as _classification_numpy,
    classification_numpy_with_meta as _classification_numpy_with_meta,
    classification_score_rows,
    load_joined_classification_batches,
)
from regression_feature_engineering.walkforward.classification.metrics import (
    auc_rank as _auc_rank,
    binary_metrics,
    classification_objective,
    flatten_metrics as _flatten,
    fmt_metric as _fmt_metric,
    matthews_corrcoef as _matthews_corrcoef,
    none_to_bad as _none_to_bad,
    parse_floats as _parse_floats,
    parse_ints as _parse_ints,
    positive_probability as _positive_probability,
    pr_auc_average_precision as _pr_auc_average_precision,
    rankdata_average as _rankdata_average,
    safe_div as _safe_div,
    select_decision_threshold,
    stable_prediction_quality_score,
    threshold_constraints_pass as _threshold_constraints_pass,
    threshold_constraints_reason as _threshold_constraints_reason,
    threshold_values as _threshold_values_from_values,
)
from regression_feature_engineering.walkforward.classification.model import fit_classifier, model_diagnostics
from regression_feature_engineering.walkforward.classification.runner import (
    run_classification_windows,
    skip_model_arrays_reason as _skip_model_arrays_reason,
    skip_window_reason as _skip_window_reason,
)
from regression_feature_engineering.walkforward.classification.targets import (
    DOWN_EXTREME,
    TARGET_BINARY_DOWN_2X_UP,
    TARGET_BINARY_DOWN_2X_UP_ALIAS,
    TARGET_BINARY_UP_2X_DOWN,
    TARGET_BINARY_UP_2X_DOWN_ALIAS,
    UP_EXTREME,
    binary_target_expr,
    canonical_binary_target_col,
    positive_rule_description,
    side_from_target as _side_from_target,
)
from regression_feature_engineering.walkforward.policy import ELASTICNET_LOGISTIC_V1


def _threshold_values(args) -> tuple[float, ...]:
    return _threshold_values_from_values(
        threshold_mode=str(args.threshold_mode),
        decision_threshold=float(args.decision_threshold),
        threshold_grid=str(args.threshold_grid),
    )


__all__ = [
    "DOWN_EXTREME",
    "ELASTICNET_LOGISTIC_V1",
    "OUTPUT_ROOT",
    "PROJECT_ROOT",
    "TARGET_BINARY_DOWN_2X_UP",
    "TARGET_BINARY_DOWN_2X_UP_ALIAS",
    "TARGET_BINARY_UP_2X_DOWN",
    "TARGET_BINARY_UP_2X_DOWN_ALIAS",
    "UP_EXTREME",
    "binary_metrics",
    "binary_target_expr",
    "canonical_binary_target_col",
    "classification_objective",
    "classification_score_rows",
    "fit_classifier",
    "load_joined_classification_batches",
    "main",
    "model_diagnostics",
    "positive_rule_description",
    "run_classification_windows",
    "select_decision_threshold",
    "stable_prediction_quality_score",
]


if __name__ == "__main__":
    raise SystemExit(main())
