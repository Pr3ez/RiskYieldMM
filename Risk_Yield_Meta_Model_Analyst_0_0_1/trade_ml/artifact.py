"""Checksummed JSON-only artifacts for the logistic meta-label baseline."""

from __future__ import annotations

import json
import math
import os
import stat
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .contracts import as_utc_datetime, stable_digest, utc_iso
from .model import FittedLogisticBaseline

ARTIFACT_FORMAT = "riskyieldmm_trade_ml_coefficients_v1"
MODEL_FAMILY = "sklearn_logistic_l2_v1"
MAX_ARTIFACT_BYTES = 1_000_000

_ARTIFACT_KEYS = frozenset(
    {
        "artifact_format",
        "model_family",
        "model_version",
        "feature_names",
        "feature_schema_digest",
        "policy_digest",
        "assets",
        "timeframes",
        "scope_digest",
        "trained_through",
        "label_mature_through",
        "created_at",
        "decision_threshold",
        "imputer_strategy",
        "imputer_statistics",
        "scaler_mean",
        "scaler_scale",
        "coefficients",
        "intercept",
        "C",
        "solver",
        "class_weight",
        "max_iter",
        "tol",
        "random_state",
        "training_rows",
        "positive_rows",
        "training_prevalence",
        "n_iter",
        "sklearn_version",
        "evaluation_metrics",
        "checksum",
    }
)


class ArtifactValidationError(ValueError):
    """Artifact contents do not satisfy the frozen production contract."""


class ArtifactChecksumError(ArtifactValidationError):
    """Artifact checksum does not match its canonical payload."""


@dataclass(frozen=True, slots=True)
class LogisticCoefficientArtifact:
    artifact_format: str
    model_family: str
    model_version: str
    feature_names: tuple[str, ...]
    feature_schema_digest: str
    policy_digest: str
    assets: tuple[str, ...]
    timeframes: tuple[str, ...]
    scope_digest: str
    trained_through: datetime
    label_mature_through: datetime
    created_at: datetime
    decision_threshold: float
    imputer_strategy: str
    imputer_statistics: tuple[float, ...]
    scaler_mean: tuple[float, ...]
    scaler_scale: tuple[float, ...]
    coefficients: tuple[float, ...]
    intercept: float
    C: float
    solver: str
    class_weight: None
    max_iter: int
    tol: float
    random_state: int
    training_rows: int
    positive_rows: int
    training_prevalence: float
    n_iter: int
    sklearn_version: str
    evaluation_metrics: dict[str, Any]
    checksum: str

    def __post_init__(self) -> None:
        _validate_artifact(self)

    def payload_without_checksum(self) -> dict[str, Any]:
        return {
            "artifact_format": self.artifact_format,
            "model_family": self.model_family,
            "model_version": self.model_version,
            "feature_names": list(self.feature_names),
            "feature_schema_digest": self.feature_schema_digest,
            "policy_digest": self.policy_digest,
            "assets": list(self.assets),
            "timeframes": list(self.timeframes),
            "scope_digest": self.scope_digest,
            "trained_through": utc_iso(self.trained_through),
            "label_mature_through": utc_iso(self.label_mature_through),
            "created_at": utc_iso(self.created_at),
            "decision_threshold": self.decision_threshold,
            "imputer_strategy": self.imputer_strategy,
            "imputer_statistics": list(self.imputer_statistics),
            "scaler_mean": list(self.scaler_mean),
            "scaler_scale": list(self.scaler_scale),
            "coefficients": list(self.coefficients),
            "intercept": self.intercept,
            "C": self.C,
            "solver": self.solver,
            "class_weight": self.class_weight,
            "max_iter": self.max_iter,
            "tol": self.tol,
            "random_state": self.random_state,
            "training_rows": self.training_rows,
            "positive_rows": self.positive_rows,
            "training_prevalence": self.training_prevalence,
            "n_iter": self.n_iter,
            "sklearn_version": self.sklearn_version,
            "evaluation_metrics": self.evaluation_metrics,
        }

    def as_dict(self) -> dict[str, Any]:
        return {**self.payload_without_checksum(), "checksum": self.checksum}


@dataclass(frozen=True, slots=True)
class ArtifactLoadResult:
    available: bool
    artifact: LogisticCoefficientArtifact | None
    reason: str
    detail: str | None = None


def digest_feature_schema(feature_names: Sequence[str]) -> str:
    """Digest the exact ordered feature-name contract."""

    names = _normalize_feature_names(feature_names)
    return stable_digest({"feature_names": list(names)})


def digest_scope(assets: Sequence[str], timeframes: Sequence[str]) -> str:
    """Digest normalized asset/timeframe membership; order is not semantic."""

    normalized_assets = _normalize_scope_values(assets, field="assets")
    normalized_timeframes = _normalize_scope_values(timeframes, field="timeframes")
    return stable_digest(
        {
            "assets": list(normalized_assets),
            "timeframes": list(normalized_timeframes),
        }
    )


def build_coefficient_artifact(
    fitted: FittedLogisticBaseline,
    *,
    model_version: str,
    policy_digest: str,
    assets: Sequence[str],
    timeframes: Sequence[str],
    trained_through: datetime | str,
    label_mature_through: datetime | str,
    decision_threshold: float,
    feature_schema_digest: str | None = None,
    evaluation_metrics: Mapping[str, Any] | None = None,
    created_at: datetime | str | None = None,
) -> LogisticCoefficientArtifact:
    """Freeze fitted preprocessing and coefficients into a checksummed payload."""

    feature_names = _normalize_feature_names(fitted.feature_names)
    computed_schema_digest = digest_feature_schema(feature_names)
    if (
        feature_schema_digest is not None
        and str(feature_schema_digest) != computed_schema_digest
    ):
        raise ArtifactValidationError(
            "feature_schema_digest does not match fitted feature order"
        )
    normalized_assets = _normalize_scope_values(assets, field="assets")
    normalized_timeframes = _normalize_scope_values(timeframes, field="timeframes")
    trained_at = as_utc_datetime(trained_through, name="trained_through")
    mature_at = as_utc_datetime(label_mature_through, name="label_mature_through")
    created = (
        datetime.now(timezone.utc)
        if created_at is None
        else as_utc_datetime(created_at, name="created_at")
    )
    payload = {
        "artifact_format": ARTIFACT_FORMAT,
        "model_family": MODEL_FAMILY,
        "model_version": str(model_version).strip(),
        "feature_names": list(feature_names),
        "feature_schema_digest": computed_schema_digest,
        "policy_digest": str(policy_digest).strip(),
        "assets": list(normalized_assets),
        "timeframes": list(normalized_timeframes),
        "scope_digest": digest_scope(normalized_assets, normalized_timeframes),
        "trained_through": utc_iso(trained_at),
        "label_mature_through": utc_iso(mature_at),
        "created_at": utc_iso(created),
        "decision_threshold": float(decision_threshold),
        "imputer_strategy": "median",
        "imputer_statistics": list(fitted.imputer_statistics),
        "scaler_mean": list(fitted.scaler_mean),
        "scaler_scale": list(fitted.scaler_scale),
        "coefficients": list(fitted.coefficients),
        "intercept": float(fitted.intercept),
        "C": float(fitted.config.C),
        "solver": "lbfgs",
        "class_weight": None,
        "max_iter": int(fitted.config.max_iter),
        "tol": float(fitted.config.tol),
        "random_state": int(fitted.config.random_state),
        "training_rows": int(fitted.training_rows),
        "positive_rows": int(fitted.positive_rows),
        "training_prevalence": float(fitted.training_prevalence),
        "n_iter": int(fitted.n_iter),
        "sklearn_version": str(fitted.sklearn_version),
        "evaluation_metrics": _json_safe_copy(evaluation_metrics or {}),
    }
    payload["checksum"] = stable_digest(payload)
    return _artifact_from_mapping(payload)


def write_artifact(
    path: str | os.PathLike[str],
    artifact: LogisticCoefficientArtifact,
) -> Path:
    """Atomically create an immutable JSON artifact.

    Rewriting the same checksum is idempotent.  Replacing a different artifact
    at an existing path is rejected so a model version cannot silently mutate.
    """

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() or destination.is_symlink():
        existing = load_artifact(destination)
        if existing.checksum == artifact.checksum:
            return destination
        raise FileExistsError(
            f"refusing to replace immutable model artifact: {destination}"
        )
    encoded = (
        json.dumps(
            artifact.as_dict(),
            allow_nan=False,
            ensure_ascii=True,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")
    if len(encoded) > MAX_ARTIFACT_BYTES:
        raise ArtifactValidationError("artifact exceeds maximum encoded size")

    temporary = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.tmp")
    descriptor: int | None = None
    try:
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = None
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
        _fsync_directory(destination.parent)
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if temporary.exists():
            temporary.unlink()
    return destination


def load_artifact(
    path: str | os.PathLike[str],
) -> LogisticCoefficientArtifact:
    """Read and fully validate a regular JSON artifact, raising on failure."""

    source = Path(path)
    file_stat = source.lstat()
    if not stat.S_ISREG(file_stat.st_mode):
        raise ArtifactValidationError("artifact path must be a regular file")
    if file_stat.st_size > MAX_ARTIFACT_BYTES:
        raise ArtifactValidationError("artifact exceeds maximum encoded size")
    try:
        raw = source.read_bytes()
    except OSError:
        raise
    try:
        payload = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ArtifactValidationError("artifact is not valid UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise ArtifactValidationError("artifact root must be a JSON object")
    return _artifact_from_mapping(payload)


def load_artifact_safe(
    path: str | os.PathLike[str],
    *,
    expected_feature_names: Sequence[str] | None = None,
    expected_feature_schema_digest: str | None = None,
    expected_policy_digest: str | None = None,
    asset: str | None = None,
    timeframe: str | None = None,
    decision_at: datetime | str | None = None,
    max_model_age: timedelta | None = None,
) -> ArtifactLoadResult:
    """Fail closed with a stable reason instead of exposing partial artifacts."""

    try:
        artifact = load_artifact(path)
    except FileNotFoundError:
        return ArtifactLoadResult(False, None, "artifact_not_found")
    except ArtifactChecksumError as exc:
        return ArtifactLoadResult(False, None, "artifact_checksum_mismatch", str(exc))
    except ArtifactValidationError as exc:
        return ArtifactLoadResult(False, None, "artifact_invalid", str(exc))
    except OSError as exc:
        return ArtifactLoadResult(False, None, "artifact_read_error", str(exc))

    try:
        reason = artifact_context_rejection(
            artifact,
            expected_feature_names=expected_feature_names,
            expected_feature_schema_digest=expected_feature_schema_digest,
            expected_policy_digest=expected_policy_digest,
            asset=asset,
            timeframe=timeframe,
            decision_at=decision_at,
            max_model_age=max_model_age,
        )
    except (TypeError, ValueError) as exc:
        return ArtifactLoadResult(False, None, "invalid_runtime_context", str(exc))
    if reason is not None:
        return ArtifactLoadResult(False, None, reason)
    return ArtifactLoadResult(True, artifact, "ok")


def artifact_context_rejection(
    artifact: LogisticCoefficientArtifact,
    *,
    expected_feature_names: Sequence[str] | None = None,
    expected_feature_schema_digest: str | None = None,
    expected_policy_digest: str | None = None,
    asset: str | None = None,
    timeframe: str | None = None,
    decision_at: datetime | str | None = None,
    max_model_age: timedelta | None = None,
) -> str | None:
    """Return a stable fail-closed reason for runtime context mismatch."""

    if expected_feature_names is not None:
        expected_names = _normalize_feature_names(expected_feature_names)
        if tuple(artifact.feature_names) != expected_names:
            return "feature_names_mismatch"
        names_digest = digest_feature_schema(expected_names)
        if artifact.feature_schema_digest != names_digest:
            return "feature_schema_mismatch"
    if (
        expected_feature_schema_digest is not None
        and artifact.feature_schema_digest != str(expected_feature_schema_digest)
    ):
        return "feature_schema_mismatch"
    if expected_policy_digest is not None and artifact.policy_digest != str(
        expected_policy_digest
    ):
        return "policy_digest_mismatch"
    if asset is not None and not _scope_contains(artifact.assets, asset):
        return "asset_scope_mismatch"
    if timeframe is not None and not _scope_contains(artifact.timeframes, timeframe):
        return "timeframe_scope_mismatch"
    if max_model_age is not None and not isinstance(max_model_age, timedelta):
        return "invalid_max_model_age"
    if max_model_age is not None and decision_at is None:
        return "decision_time_required_for_staleness_check"
    if max_model_age is not None and max_model_age < timedelta(0):
        return "invalid_max_model_age"
    if decision_at is not None:
        decision = as_utc_datetime(decision_at, name="decision_at")
        if decision < artifact.created_at:
            return "artifact_created_after_decision"
        if decision < artifact.label_mature_through:
            return "artifact_labels_mature_after_decision"
        if decision < artifact.trained_through:
            return "artifact_trained_after_decision"
        if (
            max_model_age is not None
            and decision - artifact.trained_through > max_model_age
        ):
            return "artifact_stale"
    return None


def artifact_deployment_rejection(
    artifact: LogisticCoefficientArtifact | None,
    *,
    asset: str,
    timeframe: str,
) -> str | None:
    """Return why an artifact must not control the exact runtime selection.

    Loading and scoring a candidate in shadow mode is intentionally separate
    from authorizing it to veto trades.  Gate mode requires an explicit,
    immutable promotion record at both the global walk-forward level and for
    the normalized ``ASSET/timeframe`` selection.  Wildcards and membership in
    only the artifact's broad training scope are not deployment approval.
    """

    if artifact is None:
        return "artifact_not_configured"

    normalized_asset = str(asset).strip().upper()
    normalized_timeframe = str(timeframe).strip().lower()
    if not normalized_asset:
        raise ValueError("asset must not be empty")
    if not normalized_timeframe:
        raise ValueError("timeframe must not be empty")

    if not _scope_contains(artifact.assets, normalized_asset):
        return "asset_scope_mismatch"
    if not _scope_contains(artifact.timeframes, normalized_timeframe):
        return "timeframe_scope_mismatch"

    metrics = artifact.evaluation_metrics
    if not isinstance(metrics, dict):
        return "deployment_metrics_missing"
    if metrics.get("candidate_only") is not False:
        return "artifact_candidate_only"
    if metrics.get("auto_promoted") is not True:
        return "artifact_not_promoted"

    walk_forward = metrics.get("walk_forward")
    if not isinstance(walk_forward, dict):
        return "walk_forward_deployment_gate_missing"
    if walk_forward.get("deployment_eligible") is not True:
        return "walk_forward_not_deployment_eligible"

    deployment_scope = metrics.get("deployment_scope")
    if not isinstance(deployment_scope, dict):
        return "deployment_scope_missing"
    eligible_selections = deployment_scope.get("eligible_selections")
    if not isinstance(eligible_selections, list):
        return "eligible_selections_missing"

    exact_selection = f"{normalized_asset}/{normalized_timeframe}"
    if exact_selection not in eligible_selections:
        return "selection_not_deployment_eligible"
    return None


def _artifact_from_mapping(payload: Mapping[str, Any]) -> LogisticCoefficientArtifact:
    keys = frozenset(payload)
    if keys != _ARTIFACT_KEYS:
        missing = sorted(_ARTIFACT_KEYS - keys)
        extra = sorted(keys - _ARTIFACT_KEYS)
        raise ArtifactValidationError(
            f"artifact keys do not match schema; missing={missing}, extra={extra}"
        )
    expected_checksum = stable_digest(
        {key: payload[key] for key in payload if key != "checksum"}
    )
    if payload.get("checksum") != expected_checksum:
        raise ArtifactChecksumError("artifact checksum mismatch")
    try:
        return LogisticCoefficientArtifact(
            artifact_format=_json_string(
                payload["artifact_format"], field="artifact_format"
            ),
            model_family=_json_string(payload["model_family"], field="model_family"),
            model_version=_json_string(payload["model_version"], field="model_version"),
            feature_names=_json_string_tuple(
                payload["feature_names"], field="feature_names"
            ),
            feature_schema_digest=_json_string(
                payload["feature_schema_digest"], field="feature_schema_digest"
            ),
            policy_digest=_json_string(payload["policy_digest"], field="policy_digest"),
            assets=_json_string_tuple(payload["assets"], field="assets"),
            timeframes=_json_string_tuple(payload["timeframes"], field="timeframes"),
            scope_digest=_json_string(payload["scope_digest"], field="scope_digest"),
            trained_through=as_utc_datetime(
                payload["trained_through"], name="trained_through"
            ),
            label_mature_through=as_utc_datetime(
                payload["label_mature_through"], name="label_mature_through"
            ),
            created_at=as_utc_datetime(payload["created_at"], name="created_at"),
            decision_threshold=_json_float(
                payload["decision_threshold"], field="decision_threshold"
            ),
            imputer_strategy=_json_string(
                payload["imputer_strategy"], field="imputer_strategy"
            ),
            imputer_statistics=_json_float_tuple(
                payload["imputer_statistics"], field="imputer_statistics"
            ),
            scaler_mean=_json_float_tuple(payload["scaler_mean"], field="scaler_mean"),
            scaler_scale=_json_float_tuple(
                payload["scaler_scale"], field="scaler_scale"
            ),
            coefficients=_json_float_tuple(
                payload["coefficients"], field="coefficients"
            ),
            intercept=_json_float(payload["intercept"], field="intercept"),
            C=_json_float(payload["C"], field="C"),
            solver=_json_string(payload["solver"], field="solver"),
            class_weight=_json_null(payload["class_weight"], field="class_weight"),
            max_iter=_json_int(payload["max_iter"], field="max_iter"),
            tol=_json_float(payload["tol"], field="tol"),
            random_state=_json_int(payload["random_state"], field="random_state"),
            training_rows=_json_int(payload["training_rows"], field="training_rows"),
            positive_rows=_json_int(payload["positive_rows"], field="positive_rows"),
            training_prevalence=_json_float(
                payload["training_prevalence"], field="training_prevalence"
            ),
            n_iter=_json_int(payload["n_iter"], field="n_iter"),
            sklearn_version=_json_string(
                payload["sklearn_version"], field="sklearn_version"
            ),
            evaluation_metrics=_json_object_copy(
                payload["evaluation_metrics"], field="evaluation_metrics"
            ),
            checksum=_json_string(payload["checksum"], field="checksum"),
        )
    except (TypeError, ValueError, KeyError) as exc:
        if isinstance(exc, ArtifactValidationError):
            raise
        raise ArtifactValidationError("artifact field has an invalid type") from exc


def _validate_artifact(artifact: LogisticCoefficientArtifact) -> None:
    if artifact.artifact_format != ARTIFACT_FORMAT:
        raise ArtifactValidationError("unsupported artifact_format")
    if artifact.model_family != MODEL_FAMILY:
        raise ArtifactValidationError("unsupported model_family")
    if not artifact.model_version.strip():
        raise ArtifactValidationError("model_version must not be empty")
    feature_names = _normalize_feature_names(artifact.feature_names)
    if artifact.feature_schema_digest != digest_feature_schema(feature_names):
        raise ArtifactValidationError("feature_schema_digest mismatch")
    if not _is_sha256(artifact.policy_digest):
        raise ArtifactValidationError(
            "policy_digest must be a lowercase SHA-256 digest"
        )
    assets = _normalize_scope_values(artifact.assets, field="assets")
    timeframes = _normalize_scope_values(artifact.timeframes, field="timeframes")
    if artifact.assets != assets or artifact.timeframes != timeframes:
        raise ArtifactValidationError("artifact scope is not canonically ordered")
    if artifact.scope_digest != digest_scope(assets, timeframes):
        raise ArtifactValidationError("scope_digest mismatch")
    if artifact.trained_through > artifact.label_mature_through:
        raise ArtifactValidationError(
            "trained_through cannot exceed label_mature_through"
        )
    if artifact.label_mature_through > artifact.created_at:
        raise ArtifactValidationError(
            "label_mature_through cannot exceed artifact created_at"
        )
    if not math.isfinite(artifact.decision_threshold) or not (
        0.0 < artifact.decision_threshold < 1.0
    ):
        raise ArtifactValidationError(
            "decision_threshold must be strictly within (0, 1)"
        )
    if artifact.imputer_strategy != "median":
        raise ArtifactValidationError("unsupported imputer_strategy")
    vector_length = len(feature_names)
    for field, values in (
        ("imputer_statistics", artifact.imputer_statistics),
        ("scaler_mean", artifact.scaler_mean),
        ("scaler_scale", artifact.scaler_scale),
        ("coefficients", artifact.coefficients),
    ):
        if len(values) != vector_length:
            raise ArtifactValidationError(
                f"{field} length does not match feature_names"
            )
        if any(not math.isfinite(value) for value in values):
            raise ArtifactValidationError(f"{field} contains a non-finite value")
    if any(value <= 0.0 for value in artifact.scaler_scale):
        raise ArtifactValidationError("scaler_scale must be strictly positive")
    if not math.isfinite(artifact.intercept):
        raise ArtifactValidationError("intercept must be finite")
    if not math.isfinite(artifact.C) or artifact.C <= 0.0:
        raise ArtifactValidationError("C must be finite and positive")
    if artifact.solver != "lbfgs":
        raise ArtifactValidationError("unsupported solver")
    if artifact.class_weight is not None:
        raise ArtifactValidationError("class_weight must remain null")
    if artifact.max_iter < 1 or artifact.n_iter < 1:
        raise ArtifactValidationError("iteration counts must be positive")
    if not math.isfinite(artifact.tol) or artifact.tol <= 0.0:
        raise ArtifactValidationError("tol must be finite and positive")
    if artifact.training_rows < 2:
        raise ArtifactValidationError("training_rows must be at least 2")
    if not (0 < artifact.positive_rows < artifact.training_rows):
        raise ArtifactValidationError("training artifact must contain both classes")
    expected_prevalence = artifact.positive_rows / artifact.training_rows
    if not math.isclose(
        artifact.training_prevalence,
        expected_prevalence,
        rel_tol=0.0,
        abs_tol=1e-12,
    ):
        raise ArtifactValidationError("training_prevalence does not match row counts")
    if not artifact.sklearn_version.strip():
        raise ArtifactValidationError("sklearn_version must not be empty")
    _json_safe_copy(artifact.evaluation_metrics)
    if not _is_sha256(artifact.checksum):
        raise ArtifactChecksumError("checksum must be a lowercase SHA-256 digest")
    if artifact.checksum != stable_digest(artifact.payload_without_checksum()):
        raise ArtifactChecksumError("artifact checksum mismatch")


def _normalize_feature_names(feature_names: Sequence[str]) -> tuple[str, ...]:
    names = tuple(str(name).strip() for name in feature_names)
    if not names or any(not name for name in names):
        raise ArtifactValidationError("feature_names must be non-empty strings")
    if len(set(names)) != len(names):
        raise ArtifactValidationError("feature_names must be unique and ordered")
    return names


def _normalize_scope_values(values: Sequence[str], *, field: str) -> tuple[str, ...]:
    normalized = tuple(sorted({str(value).strip() for value in values}))
    if not normalized or any(not value for value in normalized):
        raise ArtifactValidationError(f"{field} must contain non-empty values")
    if "*" in normalized and len(normalized) != 1:
        raise ArtifactValidationError(f"{field} wildcard must be the only value")
    return normalized


def _scope_contains(scope: Sequence[str], value: str) -> bool:
    candidate = str(value).strip()
    return bool(candidate) and ("*" in scope or candidate in scope)


def _is_sha256(value: str) -> bool:
    text = str(value)
    return len(text) == 64 and all(
        character in "0123456789abcdef" for character in text
    )


def _json_safe_copy(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ArtifactValidationError("JSON metadata contains a non-finite float")
        return float(value)
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ArtifactValidationError("JSON metadata keys must be strings")
            if key in result:
                raise ArtifactValidationError(f"duplicate JSON metadata key: {key}")
            result[key] = _json_safe_copy(item)
        return result
    if isinstance(value, (list, tuple)):
        return [_json_safe_copy(item) for item in value]
    raise ArtifactValidationError(
        f"JSON metadata contains unsupported type: {type(value).__name__}"
    )


def _json_string(value: Any, *, field: str) -> str:
    if not isinstance(value, str):
        raise ArtifactValidationError(f"{field} must be a JSON string")
    return value


def _json_string_tuple(value: Any, *, field: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ArtifactValidationError(f"{field} must be a JSON array")
    return tuple(_json_string(item, field=f"{field}[]") for item in value)


def _json_float(value: Any, *, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ArtifactValidationError(f"{field} must be a JSON number")
    number = float(value)
    if not math.isfinite(number):
        raise ArtifactValidationError(f"{field} must be finite")
    return number


def _json_float_tuple(value: Any, *, field: str) -> tuple[float, ...]:
    if not isinstance(value, list):
        raise ArtifactValidationError(f"{field} must be a JSON array")
    return tuple(_json_float(item, field=f"{field}[]") for item in value)


def _json_int(value: Any, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ArtifactValidationError(f"{field} must be a JSON integer")
    return int(value)


def _json_null(value: Any, *, field: str) -> None:
    if value is not None:
        raise ArtifactValidationError(f"{field} must be null")
    return None


def _json_object_copy(value: Any, *, field: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ArtifactValidationError(f"{field} must be a JSON object")
    copied = _json_safe_copy(value)
    if not isinstance(copied, dict):  # Defensive type narrowing.
        raise ArtifactValidationError(f"{field} must be a JSON object")
    return copied


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ArtifactValidationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ArtifactValidationError(f"invalid JSON numeric constant: {value}")


def _fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


__all__ = [
    "ARTIFACT_FORMAT",
    "MAX_ARTIFACT_BYTES",
    "MODEL_FAMILY",
    "ArtifactChecksumError",
    "ArtifactLoadResult",
    "ArtifactValidationError",
    "LogisticCoefficientArtifact",
    "artifact_context_rejection",
    "build_coefficient_artifact",
    "digest_feature_schema",
    "digest_scope",
    "load_artifact",
    "load_artifact_safe",
    "write_artifact",
]
