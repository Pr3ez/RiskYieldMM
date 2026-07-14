"""Fail-closed deterministic inference for coefficient-only model artifacts."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from numbers import Real
from pathlib import Path

from .artifact import (
    ArtifactLoadResult,
    LogisticCoefficientArtifact,
    artifact_context_rejection,
    digest_feature_schema,
    load_artifact_safe,
)


@dataclass(frozen=True, slots=True)
class InferenceResult:
    """One explicit gate result; unavailable models always reject the trade."""

    available: bool
    accepted: bool
    probability: float | None
    decision_threshold: float | None
    reason: str
    model_version: str | None
    artifact_checksum: str | None
    missing_features: tuple[str, ...] = ()
    invalid_features: tuple[str, ...] = ()


def score_features(
    artifact: LogisticCoefficientArtifact,
    features: Mapping[str, float | int | None],
    *,
    expected_policy_digest: str,
    asset: str,
    timeframe: str,
    decision_at: datetime | str,
    expected_feature_schema_digest: str | None = None,
    expected_feature_names: Sequence[str] | None = None,
    max_model_age: timedelta | None = None,
) -> InferenceResult:
    """Score an ordered artifact from a named feature mapping.

    Missing features are never inferred from position or aliases.  ``None`` and
    NaN are explicit missing observations and use the artifact's train-only
    median.  Infinite or non-numeric observations fail closed.
    """

    try:
        resolved_names, resolved_schema_digest = _resolve_expected_schema(
            expected_feature_names=expected_feature_names,
            expected_feature_schema_digest=expected_feature_schema_digest,
        )
    except (TypeError, ValueError):
        return _unavailable(artifact, "invalid_expected_feature_schema")
    try:
        context_reason = artifact_context_rejection(
            artifact,
            expected_feature_names=resolved_names,
            expected_feature_schema_digest=resolved_schema_digest,
            expected_policy_digest=expected_policy_digest,
            asset=asset,
            timeframe=timeframe,
            decision_at=decision_at,
            max_model_age=max_model_age,
        )
    except (TypeError, ValueError):
        return _unavailable(artifact, "invalid_inference_context")
    if context_reason is not None:
        return _unavailable(artifact, context_reason)
    if not isinstance(features, Mapping):
        return _unavailable(artifact, "features_not_mapping")

    missing = tuple(name for name in artifact.feature_names if name not in features)
    if missing:
        return InferenceResult(
            available=False,
            accepted=False,
            probability=None,
            decision_threshold=artifact.decision_threshold,
            reason="missing_features",
            model_version=artifact.model_version,
            artifact_checksum=artifact.checksum,
            missing_features=missing,
        )

    values: list[float] = []
    invalid: list[str] = []
    for name in artifact.feature_names:
        value = features[name]
        if value is None:
            values.append(math.nan)
            continue
        if isinstance(value, bool) or not isinstance(value, Real):
            invalid.append(name)
            values.append(math.nan)
            continue
        number = float(value)
        if math.isinf(number):
            invalid.append(name)
            values.append(math.nan)
            continue
        values.append(number)
    if invalid:
        return InferenceResult(
            available=False,
            accepted=False,
            probability=None,
            decision_threshold=artifact.decision_threshold,
            reason="invalid_feature_values",
            model_version=artifact.model_version,
            artifact_checksum=artifact.checksum,
            invalid_features=tuple(invalid),
        )

    logit = float(artifact.intercept)
    for value, median, mean, scale, coefficient in zip(
        values,
        artifact.imputer_statistics,
        artifact.scaler_mean,
        artifact.scaler_scale,
        artifact.coefficients,
        strict=True,
    ):
        imputed = median if math.isnan(value) else value
        standardized = (imputed - mean) / scale
        logit += coefficient * standardized
    probability = _sigmoid(logit)
    accepted = probability >= artifact.decision_threshold
    return InferenceResult(
        available=True,
        accepted=accepted,
        probability=probability,
        decision_threshold=artifact.decision_threshold,
        reason=("accepted" if accepted else "probability_below_threshold"),
        model_version=artifact.model_version,
        artifact_checksum=artifact.checksum,
    )


def load_and_score(
    path: str | Path,
    features: Mapping[str, float | int | None],
    *,
    expected_policy_digest: str,
    asset: str,
    timeframe: str,
    decision_at: datetime | str,
    expected_feature_schema_digest: str | None = None,
    expected_feature_names: Sequence[str] | None = None,
    max_model_age: timedelta | None = None,
) -> InferenceResult:
    """Safely load, validate context, and score without propagating bad state."""

    try:
        resolved_names, resolved_schema_digest = _resolve_expected_schema(
            expected_feature_names=expected_feature_names,
            expected_feature_schema_digest=expected_feature_schema_digest,
        )
    except (TypeError, ValueError):
        return InferenceResult(
            available=False,
            accepted=False,
            probability=None,
            decision_threshold=None,
            reason="invalid_expected_feature_schema",
            model_version=None,
            artifact_checksum=None,
        )
    loaded: ArtifactLoadResult = load_artifact_safe(
        path,
        expected_feature_names=resolved_names,
        expected_feature_schema_digest=resolved_schema_digest,
        expected_policy_digest=expected_policy_digest,
        asset=asset,
        timeframe=timeframe,
        decision_at=decision_at,
        max_model_age=max_model_age,
    )
    if not loaded.available or loaded.artifact is None:
        return InferenceResult(
            available=False,
            accepted=False,
            probability=None,
            decision_threshold=None,
            reason=loaded.reason,
            model_version=None,
            artifact_checksum=None,
        )
    return score_features(
        loaded.artifact,
        features,
        expected_feature_names=resolved_names,
        expected_feature_schema_digest=resolved_schema_digest,
        expected_policy_digest=expected_policy_digest,
        asset=asset,
        timeframe=timeframe,
        decision_at=decision_at,
        max_model_age=max_model_age,
    )


def _resolve_expected_schema(
    *,
    expected_feature_names: Sequence[str] | None,
    expected_feature_schema_digest: str | None,
) -> tuple[tuple[str, ...] | None, str]:
    if expected_feature_names is None and expected_feature_schema_digest is None:
        from .features import META_FEATURE_NAMES

        names: tuple[str, ...] | None = tuple(META_FEATURE_NAMES)
        return names, digest_feature_schema(names)
    names = (
        None
        if expected_feature_names is None
        else tuple(str(name) for name in expected_feature_names)
    )
    if expected_feature_schema_digest is None:
        if names is None:
            raise ValueError("expected feature schema is not specified")
        return names, digest_feature_schema(names)
    digest = str(expected_feature_schema_digest)
    if names is not None and digest_feature_schema(names) != digest:
        raise ValueError(
            "expected_feature_schema_digest does not match expected_feature_names"
        )
    return names, digest


def _unavailable(
    artifact: LogisticCoefficientArtifact,
    reason: str,
) -> InferenceResult:
    return InferenceResult(
        available=False,
        accepted=False,
        probability=None,
        decision_threshold=artifact.decision_threshold,
        reason=reason,
        model_version=artifact.model_version,
        artifact_checksum=artifact.checksum,
    )


def _sigmoid(logit: float) -> float:
    if logit >= 0.0:
        return float(1.0 / (1.0 + math.exp(-logit)))
    exponent = math.exp(logit)
    return float(exponent / (1.0 + exponent))


__all__ = ["InferenceResult", "load_and_score", "score_features"]
