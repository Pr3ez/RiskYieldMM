"""Feature quality validation contract."""

VALIDATION_NAME = "feature_quality"
BLOCKED_NAME_PATTERNS = (
    "target_*",
    "tb_*",
    "future_*",
    "label_window_*",
    "*diagnostic*",
)

