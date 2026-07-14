from __future__ import annotations

import json
import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest

ANALYST_ROOT = (
    Path(__file__).resolve().parents[1] / "Risk_Yield_Meta_Model_Analyst_0_0_1"
)
if str(ANALYST_ROOT) not in sys.path:
    sys.path.insert(0, str(ANALYST_ROOT))

from minute_replay import ProtectedReplayConfig, run_minute_replay  # noqa: E402
from trade_ml.artifact import (  # noqa: E402
    ArtifactChecksumError,
    artifact_deployment_rejection,
    build_coefficient_artifact,
    digest_feature_schema,
    load_artifact,
    load_artifact_safe,
    write_artifact,
)
from trade_ml.features import META_FEATURE_NAMES  # noqa: E402
from trade_ml.inference import load_and_score, score_features  # noqa: E402
from trade_ml.model import (  # noqa: E402
    evaluate_walk_forward,
    fit_logistic_baseline,
)
from trade_ml.splits import (  # noqa: E402
    ExpandingWalkForwardConfig,
    build_expanding_walk_forward,
)

BASE = datetime(2025, 1, 1, tzinfo=timezone.utc)
FEATURE_NAMES = ("signal", "context")
POLICY_DIGEST = "a" * 64


def _times(rows: int) -> tuple[list[datetime], list[datetime]]:
    decisions = [BASE + timedelta(hours=index) for index in range(rows)]
    label_known = [timestamp + timedelta(hours=2) for timestamp in decisions]
    return decisions, label_known


def _training_data(rows: int = 40) -> tuple[np.ndarray, np.ndarray]:
    signal = np.asarray(
        [(-1.5 if index % 2 == 0 else 1.5) for index in range(rows)],
        dtype=float,
    )
    context = np.linspace(-1.0, 1.0, rows)
    context[::11] = np.nan
    X = np.column_stack([signal, context])
    y = (signal > 0.0).astype(int)
    return X, y


def _fitted_and_artifact():
    X, y = _training_data()
    fitted = fit_logistic_baseline(X, y, feature_names=FEATURE_NAMES)
    artifact = build_coefficient_artifact(
        fitted,
        model_version="cusum-meta-logistic-2025-01-08",
        policy_digest=POLICY_DIGEST,
        assets=("BTCUSDT",),
        timeframes=("1h",),
        trained_through=BASE + timedelta(days=5),
        label_mature_through=BASE + timedelta(days=6),
        created_at=BASE + timedelta(days=7),
        decision_threshold=0.55,
        evaluation_metrics={"brier": 0.12, "rows": 20},
    )
    return fitted, artifact


def _deployment_artifact(evaluation_metrics: dict[str, object]):
    X, y = _training_data()
    fitted = fit_logistic_baseline(X, y, feature_names=FEATURE_NAMES)
    return build_coefficient_artifact(
        fitted,
        model_version="deployment-validator-test",
        policy_digest=POLICY_DIGEST,
        assets=("BTCUSDT", "ETHUSDT"),
        timeframes=("1h", "4h"),
        trained_through=BASE + timedelta(days=5),
        label_mature_through=BASE + timedelta(days=6),
        created_at=BASE + timedelta(days=7),
        decision_threshold=0.55,
        evaluation_metrics=evaluation_metrics,
    )


def test_deployment_validator_requires_explicit_exact_selection_promotion() -> None:
    eligible_metrics = {
        "candidate_only": False,
        "auto_promoted": True,
        "walk_forward": {"deployment_eligible": True},
        "deployment_scope": {"eligible_selections": ["BTCUSDT/1h"]},
    }
    eligible = _deployment_artifact(eligible_metrics)

    assert (
        artifact_deployment_rejection(
            eligible,
            asset="btcusdt",
            timeframe="1H",
        )
        is None
    )
    assert (
        artifact_deployment_rejection(
            eligible,
            asset="BTCUSDT",
            timeframe="4h",
        )
        == "selection_not_deployment_eligible"
    )
    assert (
        artifact_deployment_rejection(
            eligible,
            asset="ETHUSDT",
            timeframe="1h",
        )
        == "selection_not_deployment_eligible"
    )
    assert (
        artifact_deployment_rejection(
            eligible,
            asset="CL",
            timeframe="1h",
        )
        == "asset_scope_mismatch"
    )
    assert (
        artifact_deployment_rejection(
            eligible,
            asset="BTCUSDT",
            timeframe="15m",
        )
        == "timeframe_scope_mismatch"
    )


@pytest.mark.parametrize(
    ("metrics", "expected_reason"),
    [
        ({}, "artifact_candidate_only"),
        (
            {
                "candidate_only": True,
                "auto_promoted": False,
                "walk_forward": {"deployment_eligible": False},
                "deployment_scope": {"eligible_selections": []},
            },
            "artifact_candidate_only",
        ),
        (
            {
                "candidate_only": False,
                "auto_promoted": False,
                "walk_forward": {"deployment_eligible": True},
                "deployment_scope": {"eligible_selections": ["BTCUSDT/1h"]},
            },
            "artifact_not_promoted",
        ),
        (
            {
                "candidate_only": False,
                "auto_promoted": True,
                "walk_forward": {"deployment_eligible": False},
                "deployment_scope": {"eligible_selections": ["BTCUSDT/1h"]},
            },
            "walk_forward_not_deployment_eligible",
        ),
        (
            {
                "candidate_only": False,
                "auto_promoted": True,
                "walk_forward": {"deployment_eligible": True},
            },
            "deployment_scope_missing",
        ),
    ],
)
def test_deployment_validator_rejects_unpromoted_artifacts(
    metrics: dict[str, object],
    expected_reason: str,
) -> None:
    artifact = _deployment_artifact(metrics)

    assert (
        artifact_deployment_rejection(
            artifact,
            asset="BTCUSDT",
            timeframe="1h",
        )
        == expected_reason
    )


def test_deployment_validator_rejects_missing_artifact() -> None:
    assert (
        artifact_deployment_rejection(
            None,
            asset="BTCUSDT",
            timeframe="1h",
        )
        == "artifact_not_configured"
    )


def test_direct_replay_gate_fails_before_data_use_without_promoted_artifact() -> None:
    with pytest.raises(ValueError, match="artifact_not_configured"):
        run_minute_replay(
            None,  # type: ignore[arg-type] -- proves validation precedes data access
            asset="BTCUSDT",
            timeframe="1h",
            protection=ProtectedReplayConfig(enabled=True),
            meta_filter_mode="gate",
        )

    candidate = _deployment_artifact(
        {
            "candidate_only": True,
            "auto_promoted": False,
            "walk_forward": {"deployment_eligible": False},
            "deployment_scope": {"eligible_selections": []},
        }
    )
    with pytest.raises(ValueError, match="artifact_candidate_only"):
        run_minute_replay(
            None,  # type: ignore[arg-type] -- proves validation precedes data access
            asset="BTCUSDT",
            timeframe="1h",
            protection=ProtectedReplayConfig(enabled=True),
            meta_filter_mode="gate",
            meta_artifact=candidate,
        )


def test_expanding_walk_forward_uses_only_strictly_mature_past_labels() -> None:
    decisions, label_known = _times(12)
    folds = build_expanding_walk_forward(
        decisions,
        label_known,
        config=ExpandingWalkForwardConfig(min_train_rows=3, validation_rows=2),
    )

    assert folds
    assert folds[0].train_indices == (0, 1, 2)
    assert folds[0].validation_indices == (5, 6)
    assert 3 not in folds[0].train_indices  # label is known exactly at validation start
    for fold in folds:
        validation_start = min(decisions[idx] for idx in fold.validation_indices)
        assert all(decisions[idx] < validation_start for idx in fold.train_indices)
        assert all(label_known[idx] < validation_start for idx in fold.train_indices)
        assert max(fold.train_indices) < min(fold.validation_indices)


def test_walk_forward_keeps_simultaneous_cross_asset_decisions_together() -> None:
    decisions = [
        BASE,
        BASE,
        BASE + timedelta(hours=1),
        BASE + timedelta(hours=2),
        BASE + timedelta(hours=3),
        BASE + timedelta(hours=3),
        BASE + timedelta(hours=4),
    ]
    folds = build_expanding_walk_forward(
        decisions,
        decisions,
        config=ExpandingWalkForwardConfig(min_train_rows=2, validation_rows=1),
    )

    simultaneous_fold = next(
        fold
        for fold in folds
        if fold.validation_decision_start == BASE + timedelta(hours=3)
    )
    assert simultaneous_fold.validation_indices == (4, 5)
    assert not set(simultaneous_fold.train_indices).intersection((4, 5))


def test_walk_forward_rejects_label_known_before_decision() -> None:
    with pytest.raises(ValueError, match="cannot precede"):
        build_expanding_walk_forward(
            [BASE, BASE + timedelta(hours=1)],
            [BASE - timedelta(seconds=1), BASE + timedelta(hours=2)],
            config=ExpandingWalkForwardConfig(
                min_train_rows=1,
                validation_rows=1,
            ),
        )


def test_logistic_baseline_freezes_train_only_imputation_and_scaling() -> None:
    X = np.asarray(
        [
            [0.0, np.nan],
            [1.0, 10.0],
            [2.0, 20.0],
            [3.0, 30.0],
            [4.0, np.nan],
            [5.0, 50.0],
        ]
    )
    y = np.asarray([0, 0, 0, 1, 1, 1])

    fitted = fit_logistic_baseline(X, y, feature_names=FEATURE_NAMES)

    assert fitted.imputer_statistics == pytest.approx((2.5, 25.0))
    assert fitted.scaler_mean == pytest.approx((2.5, 26.6666666667))
    assert fitted.training_prevalence == pytest.approx(0.5)
    assert fitted.positive_rows == 3
    probabilities = fitted.predict_proba([[100.0, None], [-100.0, 25.0]])
    assert probabilities.shape == (2,)
    assert np.all(np.isfinite(probabilities))
    assert np.all((probabilities >= 0.0) & (probabilities <= 1.0))


def test_default_model_and_inference_schema_is_meta_feature_names() -> None:
    generator = np.random.default_rng(42)
    X = generator.normal(size=(80, len(META_FEATURE_NAMES)))
    y = (X[:, 0] + 0.4 * X[:, 1] > 0.0).astype(int)
    fitted = fit_logistic_baseline(X, y)
    artifact = build_coefficient_artifact(
        fitted,
        model_version="default-schema-test",
        policy_digest=POLICY_DIGEST,
        assets=("*",),
        timeframes=("*",),
        trained_through=BASE + timedelta(days=5),
        label_mature_through=BASE + timedelta(days=6),
        created_at=BASE + timedelta(days=7),
        decision_threshold=0.5,
    )

    result = score_features(
        artifact,
        dict(zip(META_FEATURE_NAMES, X[-1], strict=True)),
        expected_policy_digest=POLICY_DIGEST,
        asset="ETHUSDT",
        timeframe="4h",
        decision_at=BASE + timedelta(days=8),
    )

    assert fitted.feature_names == META_FEATURE_NAMES
    assert result.available is True
    assert result.probability == pytest.approx(fitted.predict_proba(X[-1])[0])


def test_walk_forward_evaluation_reports_oof_proper_scores_and_base_rate() -> None:
    X, y = _training_data(64)
    decisions, label_known = _times(len(X))

    evaluation = evaluate_walk_forward(
        X,
        y,
        decisions,
        label_known,
        feature_names=FEATURE_NAMES,
        split_config=ExpandingWalkForwardConfig(
            min_train_rows=12,
            validation_rows=8,
        ),
    )

    assert evaluation.metrics["rows"] > 0
    assert evaluation.metrics["brier"] is not None
    assert evaluation.metrics["log_loss"] is not None
    assert evaluation.metrics["pr_auc"] == pytest.approx(1.0)
    assert evaluation.base_rate_metrics["brier"] is not None
    assert evaluation.controls["brier_improvement_vs_causal_base_rate"] > 0.0
    assert evaluation.controls["log_loss_improvement_vs_causal_base_rate"] > 0.0
    assert evaluation.controls["pr_auc_prevalence_baseline"] == pytest.approx(0.5)
    assert evaluation.controls["pr_auc_lift_over_prevalence"] == pytest.approx(2.0)
    assert any(value is None for value in evaluation.oof_probabilities)
    assert all(
        report.training_label_known_through < report.validation_decision_start
        for report in evaluation.fold_evaluations
    )


def test_json_coefficient_artifact_round_trip_and_manual_score_parity(
    tmp_path: Path,
) -> None:
    fitted, artifact = _fitted_and_artifact()
    path = write_artifact(tmp_path / "model.json", artifact)
    encoded = path.read_text(encoding="utf-8")
    payload = json.loads(encoded)

    assert payload["model_family"] == "sklearn_logistic_l2_v1"
    assert payload["class_weight"] is None
    assert isinstance(payload["coefficients"], list)
    assert "pickle" not in encoded.lower()
    assert load_artifact(path) == artifact
    assert write_artifact(path, artifact) == path

    features = {"signal": 1.25, "context": None}
    result = score_features(
        artifact,
        features,
        expected_feature_schema_digest=digest_feature_schema(FEATURE_NAMES),
        expected_policy_digest=POLICY_DIGEST,
        asset="BTCUSDT",
        timeframe="1h",
        decision_at=BASE + timedelta(days=8),
    )
    expected = fitted.predict_proba([[1.25, None]])[0]
    repeated = score_features(
        artifact,
        features,
        expected_feature_schema_digest=digest_feature_schema(FEATURE_NAMES),
        expected_policy_digest=POLICY_DIGEST,
        asset="BTCUSDT",
        timeframe="1h",
        decision_at=BASE + timedelta(days=8),
    )
    assert result.available is True
    assert result.probability == pytest.approx(expected, abs=1e-15)
    assert repeated == result


def test_artifact_checksum_tampering_fails_closed(tmp_path: Path) -> None:
    _, artifact = _fitted_and_artifact()
    path = write_artifact(tmp_path / "model.json", artifact)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["coefficients"][0] += 0.25
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ArtifactChecksumError):
        load_artifact(path)
    loaded = load_artifact_safe(path)
    assert loaded.available is False
    assert loaded.reason == "artifact_checksum_mismatch"
    assert loaded.artifact is None


@pytest.mark.parametrize(
    ("updates", "expected_reason"),
    [
        ({"expected_policy_digest": "b" * 64}, "policy_digest_mismatch"),
        ({"asset": "ETHUSDT"}, "asset_scope_mismatch"),
        ({"timeframe": "4h"}, "timeframe_scope_mismatch"),
        (
            {"expected_feature_schema_digest": "c" * 64},
            "feature_schema_mismatch",
        ),
        (
            {
                "expected_feature_names": tuple(reversed(FEATURE_NAMES)),
            },
            "invalid_expected_feature_schema",
        ),
        (
            {
                "decision_at": BASE + timedelta(days=30),
                "max_model_age": timedelta(days=7),
            },
            "artifact_stale",
        ),
        (
            {"decision_at": BASE + timedelta(days=6, hours=12)},
            "artifact_created_after_decision",
        ),
        ({"decision_at": datetime(2025, 1, 9)}, "invalid_inference_context"),
    ],
)
def test_inference_rejects_policy_schema_scope_and_staleness(
    updates: dict[str, object],
    expected_reason: str,
) -> None:
    _, artifact = _fitted_and_artifact()
    kwargs: dict[str, object] = {
        "expected_feature_schema_digest": digest_feature_schema(FEATURE_NAMES),
        "expected_policy_digest": POLICY_DIGEST,
        "asset": "BTCUSDT",
        "timeframe": "1h",
        "decision_at": BASE + timedelta(days=8),
    }
    kwargs.update(updates)

    result = score_features(artifact, {"signal": 1.0, "context": 0.0}, **kwargs)

    assert result.available is False
    assert result.accepted is False
    assert result.reason == expected_reason
    assert result.probability is None


def test_inference_reports_missing_and_invalid_features() -> None:
    _, artifact = _fitted_and_artifact()
    common = {
        "expected_feature_schema_digest": digest_feature_schema(FEATURE_NAMES),
        "expected_policy_digest": POLICY_DIGEST,
        "asset": "BTCUSDT",
        "timeframe": "1h",
        "decision_at": BASE + timedelta(days=8),
    }

    missing = score_features(artifact, {"signal": 1.0}, **common)
    invalid = score_features(
        artifact,
        {"signal": math.inf, "context": 0.0},
        **common,
    )

    assert missing.reason == "missing_features"
    assert missing.missing_features == ("context",)
    assert invalid.reason == "invalid_feature_values"
    assert invalid.invalid_features == ("signal",)


def test_load_and_score_is_fail_closed_for_missing_and_valid_artifacts(
    tmp_path: Path,
) -> None:
    _, artifact = _fitted_and_artifact()
    common = {
        "features": {"signal": -1.0, "context": 0.0},
        "expected_feature_schema_digest": digest_feature_schema(FEATURE_NAMES),
        "expected_policy_digest": POLICY_DIGEST,
        "asset": "BTCUSDT",
        "timeframe": "1h",
        "decision_at": BASE + timedelta(days=8),
    }

    missing = load_and_score(tmp_path / "missing.json", **common)
    path = write_artifact(tmp_path / "model.json", artifact)
    valid = load_and_score(path, **common)

    assert missing.reason == "artifact_not_found"
    assert missing.available is False
    assert valid.available is True
    assert valid.reason in {"accepted", "probability_below_threshold"}


def test_safe_loader_reports_invalid_runtime_context(tmp_path: Path) -> None:
    _, artifact = _fitted_and_artifact()
    path = write_artifact(tmp_path / "model.json", artifact)

    loaded = load_artifact_safe(path, decision_at="not-a-timestamp")

    assert loaded.available is False
    assert loaded.reason == "invalid_runtime_context"
    assert loaded.artifact is None
