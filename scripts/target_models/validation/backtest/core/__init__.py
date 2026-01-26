"""Core layer - Base classes, feature utilities, and pure functions."""

from .base import ModelConfig, ModelProtocol, ModelResult
from .features import apply_feature_selection, extract_per_model_splits

__all__ = [
    # Base classes
    "ModelConfig",
    "ModelResult",
    "ModelProtocol",
    # Feature utilities
    "apply_feature_selection",
    "extract_per_model_splits",
]
