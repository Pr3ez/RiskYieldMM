from __future__ import annotations

import numpy as np
import polars as pl
import pytest

from regression_feature_engineering.walkforward.rank_signal_regime_diagnostic import (
    CURRENT_OUTCOME_COLUMNS,
    ChangeConfig,
    RegimeConfig,
    RegimeGateConfig,
    TargetMatchConfig,
    assign_past_only_market_regimes,
    assign_past_only_regimes,
    canonical_state_mapping,
    change_feature_columns,
    change_flags_by_window,
    combine_regime_context,
    cusum_calibration_artifact,
    detect_change_events,
    detect_hmm_transition_events,
    detect_market_change_events,
    hmm_filter_diagnostics_artifact,
    hmm_model_selection_artifact,
    hmm_transition_matrix_artifact,
    label_state_profiles,
    label_target_match,
    load_router_run,
    prior_available_batches,
    recursive_cusum_update,
    recursive_required_severity_from_history,
    regime_input_feature_audit,
    regime_signal_quality,
    remap_posterior,
    remap_state_array,
    rolling_standardized_value,
    safe_regime_context,
    simulate_regime_gate,
    sort_router_runs_chronologically,
    state_quality_summary,
    suppression_candidates_from_matches,
    usable_feature_columns,
)


def test_safe_regime_context_excludes_current_prediction_outcomes() -> None:
    raw = pl.DataFrame(
        [
            {
                "source_run": "run_a",
                "source_idx": 0,
                "window_end_offset_steps": 0,
                "outer_window_count": 2,
                "selection_mode": "prequential_reliability_v1",
                "candidate_set": "pruned_reliability_v1",
                "side": "up",
                "candidate_name": "up_rocket_64_v1",
                "step_idx": 10,
                "pred_batch_id": 100,
                "score_mean": 0.1,
                "score_std": 0.01,
                "precision": 1.0,
                "true_positive_count": 3,
                "false_positive_count": 0,
                "positive_count": 10,
            }
        ]
    )

    context = safe_regime_context(raw)

    leaked = CURRENT_OUTCOME_COLUMNS & set(context.columns)
    assert leaked == set()
    assert "score_mean" in context.columns
    assert "precision" not in context.columns


def test_safe_regime_context_live_mode_excludes_current_prediction_batch_context() -> (
    None
):
    raw = pl.DataFrame(
        [
            {
                "source_run": "run_a",
                "source_idx": 0,
                "side": "up",
                "candidate_name": "up_rocket_64_v1",
                "step_idx": 10,
                "pred_batch_id": 100,
                "score_mean": 0.1,
                "score_std": 0.01,
                "batch_state_gate_probability": 0.7,
                "validation_precision_lift": 1.2,
                "recent_candidate_false_discovery_rate": 0.3,
            }
        ]
    )

    context = safe_regime_context(raw, live_safe=True)

    assert "score_mean" not in context.columns
    assert "score_std" not in context.columns
    assert "batch_state_gate_probability" not in context.columns
    assert "validation_precision_lift" in context.columns
    assert "recent_candidate_false_discovery_rate" in context.columns


def test_safe_regime_context_keeps_market_context_features() -> None:
    raw = pl.DataFrame(
        [
            {
                "source_run": "run_a",
                "source_idx": 0,
                "side": "down",
                "candidate_name": "down_rocket_16_diag_v1",
                "step_idx": 1,
                "pred_batch_id": 101,
                "market_volatility_state_mean_last": 0.4,
                "market_volatility_state_mean_last_z": 1.5,
                "true_positive_count": 3,
            }
        ]
    )

    context = safe_regime_context(raw)

    assert "market_volatility_state_mean_last" in context.columns
    assert "market_volatility_state_mean_last_z" in context.columns
    assert "true_positive_count" not in context.columns


def test_prior_available_batches_excludes_current_prediction_batch_by_default() -> None:
    available = (10, 11, 12, 14, 20)

    assert prior_available_batches(
        available, 14, lookback=3, include_current=False
    ) == [10, 11, 12]
    assert prior_available_batches(available, 14, lookback=3, include_current=True) == [
        11,
        12,
        14,
    ]


def test_combine_regime_context_can_use_market_only_features() -> None:
    router = pl.DataFrame(
        [
            {
                "source_run": "run_a",
                "source_idx": 0,
                "side": "up",
                "candidate_name": "up_rocket_64_v1",
                "step_idx": 1,
                "pred_batch_id": 101,
                "score_mean": 0.1,
            }
        ]
    )
    market = pl.DataFrame(
        [
            {
                "source_idx": 0,
                "pred_batch_id": 101,
                "market_liquidity_volume_pressure_mean_last_z": -1.2,
            }
        ]
    )

    out = combine_regime_context(router, market, mode="market_context")

    assert "market_liquidity_volume_pressure_mean_last_z" in out.columns
    assert "score_mean" not in out.columns
    assert out.to_dicts()[0]["candidate_name"] == "up_rocket_64_v1"


def test_combine_regime_context_live_combined_excludes_prediction_score_summary() -> (
    None
):
    router = pl.DataFrame(
        [
            {
                "source_run": "run_a",
                "source_idx": 0,
                "side": "up",
                "candidate_name": "up_rocket_64_v1",
                "step_idx": 1,
                "pred_batch_id": 101,
                "score_mean": 0.1,
                "validation_precision_lift": 1.2,
            }
        ]
    )
    market = pl.DataFrame(
        [
            {
                "source_idx": 0,
                "pred_batch_id": 101,
                "market_liquidity_volume_pressure_mean_last_z": -1.2,
            }
        ]
    )

    out = combine_regime_context(router, market, mode="live_combined")

    assert "score_mean" not in out.columns
    assert "validation_precision_lift" in out.columns
    assert "market_liquidity_volume_pressure_mean_last_z" in out.columns


def test_change_feature_columns_can_select_market_context() -> None:
    frame = pl.DataFrame(
        {
            "score_mean": [0.1],
            "market_volatility_state_mean_last_z": [2.0],
            "market_volatility_state_mean_last": [0.5],
        }
    )

    assert change_feature_columns(frame, "router_context") == ["score_mean"]
    assert change_feature_columns(frame, "market_context") == [
        "market_volatility_state_mean_last_z"
    ]
    assert change_feature_columns(frame, "combined") == [
        "score_mean",
        "market_volatility_state_mean_last_z",
    ]


def test_regime_input_feature_filter_excludes_market_meta_columns() -> None:
    frame = pl.DataFrame(
        {
            "market_context_last_batch_id": [100, 101, 102],
            "market_context_history_batch_count": [20, 20, 20],
            "market_volatility_state_feature_count": [16, 16, 16],
            "market_volatility_state_finite_rate_last_z": [0.0, 1.0, -1.0],
            "market_volatility_state_mean_last_z": [0.1, 0.3, -0.2],
            "market_liquidity_volume_pressure_q50_lookback_mean": [1.0, 1.1, 0.9],
        }
    )

    selected = usable_feature_columns(frame)
    audit = regime_input_feature_audit(frame, selected_features=selected)
    by_name = {row["feature_name"]: row for row in audit.to_dicts()}

    assert "market_volatility_state_mean_last_z" in selected
    assert "market_liquidity_volume_pressure_q50_lookback_mean" in selected
    assert "market_context_last_batch_id" not in selected
    assert "market_volatility_state_finite_rate_last_z" not in selected
    assert by_name["market_context_last_batch_id"]["excluded_reason"] == (
        "market_context_meta_control"
    )
    assert by_name["market_volatility_state_finite_rate_last_z"][
        "excluded_reason"
    ] == "market_context_count_or_quality_control"


def test_assign_past_only_regimes_waits_for_history() -> None:
    rows = [
        {
            "source_run": "run_a",
            "source_idx": 0,
            "window_end_offset_steps": 0,
            "outer_window_count": 8,
            "selection_mode": "prequential_reliability_v1",
            "candidate_set": "pruned_reliability_v1",
            "side": "down",
            "candidate_name": "down_rocket_16_diag_v1",
            "step_idx": i,
            "pred_batch_id": 100 + i,
            "score_mean": float(i),
            "score_std": 0.1 + i * 0.01,
            "current_validation_positive_rate": 0.2 + i * 0.01,
        }
        for i in range(30)
    ]
    context = pl.DataFrame(rows)

    out = assign_past_only_regimes(
        context,
        config=RegimeConfig(
            state_count=2,
            state_count_choices=(2,),
            pca_components=2,
            min_history_windows=20,
            lookback_windows=20,
            refit_interval_windows=1,
            random_seed=7,
            model_mode="gmm_markov",
        ),
    )

    assert out["regime_status"][:20].to_list() == ["insufficient_history"] * 20
    assert "ok" in out["regime_status"][20:].to_list()


def test_assign_past_only_regimes_supports_refit_interval() -> None:
    rows = [
        {
            "source_run": "run_a",
            "source_idx": 0,
            "side": "down",
            "candidate_name": "down_rocket_16_diag_v1",
            "step_idx": i,
            "pred_batch_id": 100 + i,
            "validation_precision_lift": float(i % 7),
            "recent_candidate_false_discovery_rate": float((i % 5) / 10),
            "market_volatility_state_mean_last_z": float(i),
        }
        for i in range(50)
    ]

    out = assign_past_only_regimes(
        pl.DataFrame(rows),
        config=RegimeConfig(
            state_count=2,
            state_count_choices=(2,),
            pca_components=2,
            min_history_windows=20,
            lookback_windows=20,
            refit_interval_windows=10,
            random_seed=7,
            model_mode="gmm_markov",
        ),
    )

    assert out["regime_status"][:20].to_list() == ["insufficient_history"] * 20
    assert "ok" in out["regime_status"][20:].to_list()


def test_assign_past_only_market_regimes_shares_state_across_candidates() -> None:
    rows = []
    for idx in range(50):
        for side, candidate in [
            ("up", "up_rocket_64_v1"),
            ("down", "down_rocket_16_diag_v1"),
        ]:
            rows.append(
                {
                    "source_run": "run_a",
                    "source_idx": 0,
                    "window_end_offset_steps": 0,
                    "outer_window_count": 50,
                    "selection_mode": "prequential_reliability_v1",
                    "candidate_set": "pruned_reliability_v1",
                    "side": side,
                    "candidate_name": candidate,
                    "step_idx": idx,
                    "pred_batch_id": 100 + idx,
                    "market_volatility_state_mean_last_z": float(idx),
                    "market_liquidity_volume_pressure_mean_last_z": float(idx % 7),
                }
            )
    context = pl.DataFrame(rows)

    out = assign_past_only_market_regimes(
        context,
        config=RegimeConfig(
            state_count=2,
            state_count_choices=(2,),
            pca_components=2,
            min_history_windows=20,
            lookback_windows=20,
            refit_interval_windows=5,
            random_seed=7,
            model_mode="gmm_markov",
        ),
    )

    assigned = out.filter(pl.col("regime_status") == "ok")
    assert not assigned.is_empty()
    state_counts = (
        assigned.group_by("pred_batch_id")
        .agg(pl.col("regime_state").n_unique().alias("state_count"))
        .select("state_count")
        .to_series()
        .to_list()
    )
    assert state_counts
    assert max(state_counts) == 1


def test_detect_market_change_events_duplicates_global_alarm_to_candidates() -> None:
    rows = []
    for idx in range(80):
        value = 0.0 if idx < 60 else 10.0
        for side, candidate in [
            ("up", "up_rocket_64_v1"),
            ("down", "down_rocket_16_diag_v1"),
        ]:
            rows.append(
                {
                    "source_run": "run_a",
                    "source_idx": 0,
                    "side": side,
                    "candidate_name": candidate,
                    "step_idx": idx,
                    "pred_batch_id": 200 + idx,
                    "market_volatility_state_mean_last_z": value,
                }
            )
    context = pl.DataFrame(rows)

    events = detect_market_change_events(
        context,
        config=ChangeConfig(
            lookback_windows=40,
            cusum_z=3.0,
            page_hinkley_delta=0.01,
            page_hinkley_threshold=3.0,
            feature_set="market_context",
            change_detectors=("cusum",),
        ),
    )

    assert not events.is_empty()
    assert set(events["candidate_name"].unique().to_list()) == {
        "up_rocket_64_v1",
        "down_rocket_16_diag_v1",
    }
    assert events["cusum_alarm"].all()
    assert not events["page_hinkley_alarm"].any()


def test_canonical_state_mapping_orders_raw_states_by_centroid() -> None:
    x = np.array(
        [
            [10.0, 0.0],
            [11.0, 0.0],
            [-2.0, 0.0],
            [-1.0, 0.0],
            [3.0, 0.0],
            [4.0, 0.0],
        ]
    )
    raw_states = np.array([1, 1, 2, 2, 0, 0])

    mapping = canonical_state_mapping(x, raw_states, state_count=3)
    remapped = remap_state_array(raw_states, mapping)
    posterior = remap_posterior(np.array([0.7, 0.2, 0.1]), mapping)

    assert mapping == {2: 0, 0: 1, 1: 2}
    assert remapped.tolist() == [2, 2, 0, 0, 1, 1]
    assert posterior.tolist() == [0.1, 0.7, 0.2]


def test_detect_change_events_flags_large_safe_feature_shift() -> None:
    rows = []
    for i in range(80):
        rows.append(
            {
                "source_run": "run_a",
                "source_idx": 0,
                "side": "up",
                "candidate_name": "up_rocket_64_v1",
                "step_idx": i,
                "pred_batch_id": 100 + i,
                "score_mean": 0.0 if i < 50 else 10.0,
                "score_std": 0.1,
            }
        )
    context = pl.DataFrame(rows)

    events = detect_change_events(
        context,
        config=ChangeConfig(
            lookback_windows=30,
            cusum_z=3.0,
            page_hinkley_delta=0.01,
            page_hinkley_threshold=3.0,
        ),
    )

    assert not events.is_empty()
    assert "score_mean" in events["feature"].to_list()


def test_detect_change_events_can_run_cusum_only() -> None:
    rows = []
    for i in range(80):
        rows.append(
            {
                "source_run": "run_a",
                "source_idx": 0,
                "side": "up",
                "candidate_name": "up_rocket_64_v1",
                "step_idx": i,
                "pred_batch_id": 100 + i,
                "score_mean": 0.0 if i < 50 else 10.0,
            }
        )

    events = detect_change_events(
        pl.DataFrame(rows),
        config=ChangeConfig(
            lookback_windows=30,
            cusum_z=3.0,
            page_hinkley_delta=0.01,
            page_hinkley_threshold=3.0,
            change_detectors=("cusum",),
        ),
    )

    assert not events.is_empty()
    assert events["cusum_alarm"].all()
    assert not events["page_hinkley_alarm"].any()
    assert events["market_context_zshift_v1_alarm"].all()


def test_recursive_cusum_update_matches_direct_formula() -> None:
    state = {"s_pos": 0.0, "s_neg": 0.0}

    alarm_1, direction_1 = recursive_cusum_update(state, 1.0, k=0.5, h=1.0)
    alarm_2, direction_2 = recursive_cusum_update(state, 1.0, k=0.5, h=1.0)
    alarm_3, direction_3 = recursive_cusum_update(state, -3.0, k=0.5, h=1.0)

    assert alarm_1 is False
    assert direction_1 is None
    assert alarm_2 is False
    assert direction_2 is None
    assert alarm_3 is True
    assert direction_3 == "negative"


def test_rolling_robust_z_is_prior_only_and_outlier_resistant() -> None:
    prior = np.array([1.0, 2.0, 3.0, 100.0])

    robust_center, robust_scale, robust_z = rolling_standardized_value(
        prior,
        100.0,
        standardization="rolling_robust_z_v1",
    )
    mean_center, mean_scale, mean_z = rolling_standardized_value(
        prior,
        100.0,
        standardization="rolling_mean_std_v1",
    )

    assert robust_center == 2.5
    assert robust_scale == pytest.approx(1.4826)
    assert robust_z > mean_z
    assert mean_center > robust_center
    assert mean_scale > robust_scale


def test_recursive_required_severity_uses_prior_history_quantile() -> None:
    config = ChangeConfig(
        lookback_windows=20,
        cusum_z=3.0,
        page_hinkley_delta=0.01,
        page_hinkley_threshold=3.0,
        target_event_rate_min=0.05,
        target_event_rate_max=0.25,
    )

    threshold = recursive_required_severity_from_history(
        [float(item) for item in range(100)],
        config=config,
    )

    assert threshold == pytest.approx(94.25)


def test_detect_change_events_can_run_recursive_cusum() -> None:
    rows = []
    for i in range(80):
        rows.append(
            {
                "source_run": "run_a",
                "source_idx": 0,
                "side": "up",
                "candidate_name": "up_rocket_64_v1",
                "step_idx": i,
                "pred_batch_id": 100 + i,
                "score_mean": 0.0 if i < 50 else 4.0,
            }
        )

    events = detect_change_events(
        pl.DataFrame(rows),
        config=ChangeConfig(
            lookback_windows=30,
            cusum_z=3.0,
            page_hinkley_delta=0.01,
            page_hinkley_threshold=3.0,
            recursive_cusum_k=0.25,
            recursive_cusum_h=2.0,
            change_detectors=("market_context_recursive_cusum_v1",),
        ),
    )

    assert not events.is_empty()
    assert events["market_context_recursive_cusum_v1_alarm"].any()
    assert not events["cusum_alarm"].any()


def test_detect_change_events_writes_explicit_detector_rows_on_overlap() -> None:
    rows = []
    for i in range(80):
        rows.append(
            {
                "source_run": "run_a",
                "source_idx": 0,
                "side": "up",
                "candidate_name": "up_rocket_64_v1",
                "step_idx": i,
                "pred_batch_id": 100 + i,
                "score_mean": 0.0 if i < 50 else 4.0,
            }
        )

    events = detect_change_events(
        pl.DataFrame(rows),
        config=ChangeConfig(
            lookback_windows=30,
            cusum_z=3.0,
            page_hinkley_delta=0.01,
            page_hinkley_threshold=3.0,
            recursive_cusum_k=0.25,
            recursive_cusum_h=2.0,
            change_detectors=(
                "market_context_zshift_v1",
                "market_context_recursive_cusum_v1",
            ),
        ),
    )

    detector_names = set(events["detector_name"].unique().to_list())
    assert "market_context_zshift_v1,market_context_recursive_cusum_v1" not in (
        detector_names
    )
    assert "market_context_zshift_v1" in detector_names
    assert "market_context_recursive_cusum_v1" in detector_names

    overlapping_feature_windows = (
        events.group_by(["source_idx", "pred_batch_id", "feature"])
        .agg(pl.col("detector_name").n_unique().alias("detector_count"))
        .filter(pl.col("detector_count") > 1)
    )
    assert not overlapping_feature_windows.is_empty()


def test_detect_hmm_transition_events_fires_on_state_change_stream() -> None:
    rows = []
    for i in range(80):
        for side, candidate in [
            ("up", "up_rocket_64_v1"),
            ("down", "down_rocket_16_diag_v1"),
        ]:
            rows.append(
                {
                    "source_run": "run_a",
                    "source_idx": 0,
                    "side": side,
                    "candidate_name": candidate,
                    "step_idx": i,
                    "pred_batch_id": 100 + i,
                    "regime_status": "ok",
                    "regime_state": 0 if i < 55 else 1,
                    "regime_posterior_max": 0.95 if i < 55 else 0.55,
                    "regime_entropy": 0.05 if i < 55 else 0.8,
                    "regime_transition_probability": 0.9 if i < 55 else 0.05,
                    "regime_changed_from_previous": i == 55,
                }
            )

    events = detect_hmm_transition_events(
        pl.DataFrame(rows),
        config=ChangeConfig(
            lookback_windows=30,
            cusum_z=3.0,
            page_hinkley_delta=0.01,
            page_hinkley_threshold=3.0,
            recursive_cusum_k=0.25,
            recursive_cusum_h=2.0,
            change_detectors=("hmm_transition_cusum_v1",),
        ),
    )

    assert not events.is_empty()
    assert set(events["candidate_name"].unique().to_list()) == {
        "up_rocket_64_v1",
        "down_rocket_16_diag_v1",
    }
    assert events["hmm_transition_cusum_v1_alarm"].any()
    assert events["hmm_state_change_alarm"].any()
    detector_names = set(events["detector_name"].unique().to_list())
    assert "hmm_transition_cusum_v1" in detector_names
    assert "hmm_state_change_marker" in detector_names
    assert not any("," in name for name in detector_names)


def test_hmm_artifact_helpers_expand_model_metadata() -> None:
    model_selection_json = (
        '[{"candidate_state_count": 2, "restart": 0, '
        '"selection_mode": "bic_v1", "status": "ok", '
        '"log_likelihood": -10.0, "aic": 40.0, "bic": 50.0, '
        '"selected": true}]'
    )
    regime = pl.DataFrame(
        [
            {
                "source_run": "run_a",
                "source_idx": 0,
                "step_idx": 1,
                "pred_batch_id": 101,
                "side": "up",
                "candidate_name": "up_rocket_64_v1",
                "regime_model": "gaussian_hmm",
                "regime_status": "ok",
                "regime_state": 1,
                "regime_selected_state_count": 2,
                "regime_filter_mode": "causal_forward_v1",
                "regime_log_likelihood": -10.0,
                "regime_aic": 40.0,
                "regime_bic": 50.0,
                "regime_current_log_likelihood": -0.4,
                "regime_posterior_max": 0.8,
                "regime_entropy": 0.3,
                "regime_changed_from_previous": False,
                "regime_transition_probability": 0.7,
                "regime_expected_duration": 5.0,
                "regime_train_state_count": 2,
                "regime_posterior_state_0": 0.2,
                "regime_posterior_state_1": 0.8,
                "regime_model_selection_json": model_selection_json,
                "regime_transition_matrix_json": "[[0.8, 0.2], [0.3, 0.7]]",
            },
            {
                "source_run": "run_a",
                "source_idx": 0,
                "step_idx": 1,
                "pred_batch_id": 101,
                "side": "down",
                "candidate_name": "down_rocket_16_diag_v1",
                "regime_model": "gaussian_hmm",
                "regime_status": "ok",
                "regime_state": 1,
                "regime_selected_state_count": 2,
                "regime_filter_mode": "causal_forward_v1",
                "regime_model_selection_json": model_selection_json,
                "regime_transition_matrix_json": "[[0.8, 0.2], [0.3, 0.7]]",
            },
        ]
    )

    filter_rows = hmm_filter_diagnostics_artifact(regime)
    selection_rows = hmm_model_selection_artifact(regime)
    transition_rows = hmm_transition_matrix_artifact(regime)

    assert filter_rows.height == 1
    assert filter_rows.to_dicts()[0]["regime_filter_mode"] == "causal_forward_v1"
    assert selection_rows.height == 1
    assert selection_rows.to_dicts()[0]["selected"] is True
    assert transition_rows.height == 4
    stay_row = transition_rows.filter(
        (pl.col("from_state") == 0) & (pl.col("to_state") == 0)
    ).to_dicts()[0]
    assert stay_row["expected_duration_from_state"] == pytest.approx(5.0)


def test_cusum_calibration_artifact_reports_recursive_event_rate() -> None:
    context = pl.DataFrame(
        [
            {
                "source_idx": 0,
                "pred_batch_id": 100 + idx,
                "side": "up",
                "candidate_name": "up_rocket_64_v1",
            }
            for idx in range(4)
        ]
    )
    changes = pl.DataFrame(
        [
            {
                "source_idx": 0,
                "pred_batch_id": 101,
                "detector_name": "market_context_recursive_cusum_v1",
                "market_context_recursive_cusum_v1_alarm": True,
            }
        ]
    )
    config = ChangeConfig(
        lookback_windows=20,
        cusum_z=3.0,
        page_hinkley_delta=0.01,
        page_hinkley_threshold=3.0,
        target_event_rate_min=0.05,
        target_event_rate_max=0.25,
    )

    calibration = cusum_calibration_artifact(
        context,
        changes,
        pl.DataFrame(),
        config=config,
    )

    recursive = calibration.filter(
        pl.col("detector_name") == "market_context_recursive_cusum_v1"
    ).to_dicts()[0]
    assert recursive["event_windows"] == 1
    assert recursive["event_window_rate"] == 0.25
    assert recursive["calibration_status"] == "pass"


def test_detect_change_events_rejects_unknown_detector() -> None:
    context = pl.DataFrame(
        [
            {
                "source_run": "run_a",
                "source_idx": 0,
                "side": "up",
                "candidate_name": "up_rocket_64_v1",
                "step_idx": 0,
                "pred_batch_id": 100,
                "score_mean": 0.0,
            }
        ]
    )

    with pytest.raises(ValueError, match="Unsupported change detectors"):
        detect_change_events(
            context,
            config=ChangeConfig(
                lookback_windows=30,
                cusum_z=3.0,
                page_hinkley_delta=0.01,
                page_hinkley_threshold=3.0,
                change_detectors=("bad",),
            ),
        )


def test_state_quality_summary_aggregates_signal_quality_by_state() -> None:
    quality = pl.DataFrame(
        [
            {
                "side": "up",
                "candidate_name": "up_rocket_64_v1",
                "regime_model": "gmm_markov_proxy",
                "regime_status": "ok",
                "regime_state": 0,
                "regime_selected_state_count": 2,
                "regime_state_key": "k2_s0",
                "rows": 100,
                "positive_count": 40,
                "predicted_positive_count": 4,
                "true_positive_count": 3,
                "false_positive_count": 1,
                "regime_posterior_max": 0.8,
                "regime_entropy": 0.5,
            },
            {
                "side": "up",
                "candidate_name": "up_rocket_64_v1",
                "regime_model": "gmm_markov_proxy",
                "regime_status": "ok",
                "regime_state": 0,
                "regime_selected_state_count": 3,
                "regime_state_key": "k3_s0",
                "rows": 100,
                "positive_count": 40,
                "predicted_positive_count": 2,
                "true_positive_count": 1,
                "false_positive_count": 1,
                "regime_posterior_max": 0.7,
                "regime_entropy": 0.6,
            },
        ]
    )

    summary = state_quality_summary(quality)

    by_key = {row["regime_state_key"]: row for row in summary.to_dicts()}
    assert by_key["k2_s0"]["signals"] == 4
    assert by_key["k2_s0"]["true_positives"] == 3
    assert by_key["k2_s0"]["precision"] == 3 / 4
    assert by_key["k3_s0"]["signals"] == 2
    assert by_key["k3_s0"]["true_positives"] == 1
    assert by_key["k3_s0"]["precision"] == 1 / 2


def test_label_state_profiles_is_deterministic_from_market_features() -> None:
    regime = pl.DataFrame(
        [
            {
                "source_idx": 0,
                "pred_batch_id": 100,
                "regime_status": "ok",
                "regime_state": 0,
                "regime_selected_state_count": 2,
                "regime_state_key": "k2_s0",
                "market_volatility_state_mean_last_z": -0.5,
                "market_temporal_memory_transforms_std_last_z": -0.4,
                "market_liquidity_volume_pressure_std_last_z": -0.2,
            },
            {
                "source_idx": 0,
                "pred_batch_id": 101,
                "regime_status": "ok",
                "regime_state": 1,
                "regime_selected_state_count": 2,
                "regime_state_key": "k2_s1",
                "market_volatility_state_mean_last_z": 0.5,
                "market_temporal_memory_transforms_std_last_z": 0.2,
                "market_liquidity_volume_pressure_std_last_z": 0.3,
            },
        ]
    )

    labels = label_state_profiles(regime)
    by_state = {
        row["regime_state_key"]: row["state_profile_label"] for row in labels.to_dicts()
    }

    assert by_state["k2_s0"] == "quiet_compressed"
    assert by_state["k2_s1"] == "expanded_pressure"


def test_simulate_regime_gate_uses_prior_context_only() -> None:
    rows = []
    for i in range(4):
        rows.append(
            {
                "source_run": "run_a",
                "source_idx": 0,
                "side": "down",
                "candidate_name": "down_none_v1",
                "step_idx": i,
                "pred_batch_id": 100 + i,
                "regime_status": "ok",
                "regime_state": 1,
                "regime_selected_state_count": 2,
                "regime_state_key": "k2_s1",
                "has_market_context_recursive_cusum_v1": False,
                "has_hmm_transition_cusum_v1": False,
                "rows": 100,
                "positive_count": 20,
                "predicted_positive_count": 10,
                "true_positive_count": 8,
                "false_positive_count": 2,
            }
        )
    config = RegimeGateConfig(
        min_context_windows=2,
        min_context_signals=20,
        min_precision_lift=1.1,
        max_fdr=0.58,
        avoid_max_lift=1.0,
        avoid_min_fdr=0.60,
    )

    simulated = simulate_regime_gate(pl.DataFrame(rows), config=config)
    actions = simulated.sort("pred_batch_id")["gate_action"].to_list()

    assert actions[:2] == ["no_history", "no_history"]
    assert actions[2:] == ["allow", "allow"]
    assert simulated.sort("pred_batch_id")["context_type"].to_list()[2] in {
        "regime_state_key",
        "recursive_cusum",
        "hmm_transition_cusum",
        "regime_state_key+recursive_cusum",
        "regime_state_key+hmm_transition_cusum",
    }
    assert simulated.sort("pred_batch_id")["signals_after"].to_list() == [
        0,
        0,
        10,
        10,
    ]


def test_sort_router_runs_chronologically_uses_larger_offset_first(tmp_path) -> None:
    latest = tmp_path / "latest"
    older = tmp_path / "older"
    middle = tmp_path / "middle"
    latest.mkdir()
    older.mkdir()
    middle.mkdir()
    (latest / "router_config.json").write_text('{"window_end_offset_steps": 0}')
    (older / "router_config.json").write_text('{"window_end_offset_steps": 960}')
    (middle / "router_config.json").write_text('{"window_end_offset_steps": 480}')

    sorted_runs = sort_router_runs_chronologically((latest, older, middle))

    assert sorted_runs == [older, middle, latest]


def test_load_router_run_can_use_router_selected_live_stream(tmp_path) -> None:
    run = tmp_path / "router"
    run.mkdir()
    (run / "router_config.json").write_text(
        '{"window_end_offset_steps": 0, "outer_window_count": 2, "selection_mode": "prequential_reliability_v1"}'
    )
    pl.DataFrame(
        [
            {
                "side": "up",
                "step_idx": 1,
                "pred_batch_id": 101,
                "rows": 240,
                "positive_count": 100,
                "predicted_positive_count": 0,
                "true_positive_count": 0,
                "false_positive_count": 0,
                "selected_candidate": None,
            },
            {
                "side": "up",
                "step_idx": 2,
                "pred_batch_id": 102,
                "rows": 240,
                "positive_count": 100,
                "predicted_positive_count": 3,
                "true_positive_count": 2,
                "false_positive_count": 1,
                "selected_candidate": "up_rocket_64_v1",
            },
            {
                "side": "down",
                "step_idx": 1,
                "pred_batch_id": 101,
                "rows": 0,
                "positive_count": 0,
                "predicted_positive_count": 0,
                "true_positive_count": 0,
                "false_positive_count": 0,
                "selected_candidate": None,
            },
        ]
    ).write_parquet(run / "router_window_metrics.parquet")

    out = load_router_run(
        run,
        source_idx=0,
        prediction_source="router_selected",
        router_side_candidates={"up": "up_rocket_64_v1"},
    )

    rows = (
        out.filter((pl.col("side") == "up") & (pl.col("rows") > 0))
        .sort("pred_batch_id")
        .to_dicts()
    )
    assert rows[0]["candidate_name"] == "up_rocket_64_v1"
    assert rows[0]["predicted_positive_count"] == 0
    assert rows[1]["candidate_name"] == "up_rocket_64_v1"
    assert rows[1]["predicted_positive_count"] == 3
    assert rows[1]["prediction_source"] == "router_selected"


def test_load_router_run_effective_selected_prefers_row_rule_active_stream(
    tmp_path,
) -> None:
    run = tmp_path / "router"
    run.mkdir()
    (run / "router_config.json").write_text(
        '{"row_rule_gate": {"output_mode": "active_candidate"}, "selection_mode": "prequential_reliability_v1"}'
    )
    pl.DataFrame(
        [
            {
                "side": "up",
                "step_idx": 1,
                "pred_batch_id": 101,
                "rows": 240,
                "positive_count": 100,
                "predicted_positive_count": 1,
                "true_positive_count": 0,
                "false_positive_count": 1,
                "selected_candidate": "up_rocket_64_v1",
            }
        ]
    ).write_parquet(run / "router_window_metrics.parquet")
    pl.DataFrame(
        [
            {
                "side": "up",
                "candidate_name": "up_rocket_64_v1",
                "selected_candidate": "up_rocket_64_v1",
                "step_idx": 1,
                "pred_batch_id": 101,
                "rows": 240,
                "positive_count": 100,
                "predicted_positive_count": 5,
                "true_positive_count": 4,
                "false_positive_count": 1,
            }
        ]
    ).write_parquet(run / "row_rule_active_window_metrics.parquet")

    out = load_router_run(run, source_idx=0, prediction_source="effective_selected")

    row = out.to_dicts()[0]
    assert row["prediction_source"] == "row_rule_active"
    assert row["requested_prediction_source"] == "effective_selected"
    assert row["predicted_positive_count"] == 5
    assert row["true_positive_count"] == 4


def test_load_router_run_effective_selected_reads_explicit_effective_artifact(
    tmp_path,
) -> None:
    run = tmp_path / "router"
    run.mkdir()
    (run / "router_config.json").write_text(
        '{"row_rule_gate": {"output_mode": "active_candidate"}, "selection_mode": "prequential_reliability_v1"}'
    )
    pl.DataFrame(
        [
            {
                "side": "up",
                "candidate_name": "up_rocket_64_v1",
                "selected_candidate": "up_rocket_64_v1",
                "step_idx": 1,
                "pred_batch_id": 101,
                "rows": 240,
                "positive_count": 100,
                "predicted_positive_count": 7,
                "true_positive_count": 6,
                "false_positive_count": 1,
                "prediction_source": "row_rule_active",
            }
        ]
    ).write_parquet(run / "effective_window_metrics.parquet")
    pl.DataFrame(
        [
            {
                "side": "up",
                "candidate_name": "up_rocket_64_v1",
                "step_idx": 1,
                "pred_batch_id": 101,
                "rows": 240,
                "positive_count": 100,
                "predicted_positive_count": 5,
                "true_positive_count": 4,
                "false_positive_count": 1,
            }
        ]
    ).write_parquet(run / "row_rule_active_window_metrics.parquet")

    out = load_router_run(run, source_idx=0, prediction_source="effective_selected")

    row = out.to_dicts()[0]
    assert row["prediction_source"] == "row_rule_active"
    assert row["requested_prediction_source"] == "effective_selected"
    assert row["predicted_positive_count"] == 7
    assert row["true_positive_count"] == 6


def test_change_flags_by_window_aggregates_cusum_and_page_hinkley() -> None:
    changes = pl.DataFrame(
        [
            {
                "source_run": "run_a",
                "side": "up",
                "candidate_name": "up_rocket_64_v1",
                "step_idx": 1,
                "pred_batch_id": 101,
                "cusum_alarm": True,
                "page_hinkley_alarm": False,
            },
            {
                "source_run": "run_a",
                "side": "up",
                "candidate_name": "up_rocket_64_v1",
                "step_idx": 1,
                "pred_batch_id": 101,
                "cusum_alarm": False,
                "page_hinkley_alarm": True,
            },
        ]
    )

    flags = change_flags_by_window(changes)
    row = flags.to_dicts()[0]

    assert row["change_event_count"] == 2
    assert row["market_context_zshift_v1_count"] == 1
    assert row["page_hinkley_count"] == 1
    assert row["has_any_change"] is True
    assert row["has_market_context_zshift_v1"] is True
    assert "has_cusum" not in flags.columns
    assert row["has_page_hinkley"] is True


def test_change_flags_by_window_omits_disabled_page_hinkley() -> None:
    changes = pl.DataFrame(
        [
            {
                "source_run": "run_a",
                "side": "up",
                "candidate_name": "up_rocket_64_v1",
                "step_idx": 1,
                "pred_batch_id": 101,
                "cusum_alarm": True,
                "page_hinkley_alarm": False,
            }
        ]
    )

    flags = change_flags_by_window(changes, detectors=("cusum",))

    assert "market_context_zshift_v1_count" in flags.columns
    assert "has_market_context_zshift_v1" in flags.columns
    assert "has_cusum" not in flags.columns
    assert "page_hinkley_count" not in flags.columns
    assert "has_page_hinkley" not in flags.columns


def test_label_target_match_and_suppression_candidates() -> None:
    metrics = pl.DataFrame(
        [
            {
                "side": "down",
                "candidate_name": "down_rocket_16_diag_v1",
                "regime_state": 0,
                "regime_selected_state_count": 2,
                "regime_state_key": "k2_s0",
                "signals": 100,
                "precision_lift": 0.95,
                "false_discovery_rate": 0.64,
            },
            {
                "side": "up",
                "candidate_name": "up_rocket_64_v1",
                "regime_state": 1,
                "regime_selected_state_count": 2,
                "regime_state_key": "k2_s1",
                "signals": 100,
                "precision_lift": 1.2,
                "false_discovery_rate": 0.5,
            },
        ]
    )
    config = TargetMatchConfig(
        favorable_min_signals=80,
        favorable_min_lift=1.1,
        favorable_max_fdr=0.58,
        avoid_min_signals=80,
        avoid_max_lift=1.0,
        avoid_min_fdr=0.60,
    )

    labeled = label_target_match(metrics, context_type="regime_state", config=config)
    statuses = {(row["side"], row["target_match_status"]) for row in labeled.to_dicts()}
    suppression = suppression_candidates_from_matches(labeled)

    assert ("down", "avoid") in statuses
    assert ("up", "favorable") in statuses
    assert suppression.height == 1
    assert suppression.to_dicts()[0]["side"] == "down"


def test_suppression_candidates_exclude_false_change_flag_contexts() -> None:
    labeled = pl.DataFrame(
        [
            {
                "side": "down",
                "candidate_name": "down_rocket_16_diag_v1",
                "context_type": "change_flag",
                "change_flag": "has_market_context_recursive_cusum_v1",
                "change_flag_value": False,
                "signals": 120,
                "precision_lift": 0.8,
                "false_discovery_rate": 0.7,
                "target_match_status": "avoid",
            },
            {
                "side": "down",
                "candidate_name": "down_rocket_16_diag_v1",
                "context_type": "regime_state_change_flag",
                "regime_state": 2,
                "regime_state_key": "k3_s2",
                "change_flag": "has_page_hinkley",
                "change_flag_value": False,
                "signals": 120,
                "precision_lift": 0.8,
                "false_discovery_rate": 0.7,
                "target_match_status": "avoid",
            },
            {
                "side": "up",
                "candidate_name": "up_rocket_64_v1",
                "context_type": "change_flag",
                "change_flag": "has_market_context_zshift_v1",
                "change_flag_value": True,
                "signals": 120,
                "precision_lift": 0.8,
                "false_discovery_rate": 0.7,
                "target_match_status": "avoid",
            },
            {
                "side": "up",
                "candidate_name": "up_rocket_64_v1",
                "context_type": "change_flag",
                "change_flag": "has_hmm_transition_cusum_v1",
                "change_flag_value": True,
                "signals": 120,
                "precision_lift": 0.8,
                "false_discovery_rate": 0.7,
                "target_match_status": "avoid",
            },
        ]
    )

    suppression = suppression_candidates_from_matches(labeled)

    rows = suppression.to_dicts()
    assert len(rows) == 1
    assert rows[0]["side"] == "up"
    assert rows[0]["change_flag"] == "has_hmm_transition_cusum_v1"
    assert rows[0]["change_flag_value"] is True


def test_regime_signal_quality_preserves_prediction_source_columns() -> None:
    raw = pl.DataFrame(
        [
            {
                "source_run": "run_a",
                "requested_prediction_source": "effective_selected",
                "prediction_source": "row_rule_active",
                "side": "up",
                "candidate_name": "up_rocket_64_v1",
                "step_idx": 1,
                "pred_batch_id": 101,
                "rows": 100,
                "positive_count": 40,
                "predicted_positive_count": 5,
                "true_positive_count": 3,
                "false_positive_count": 2,
            }
        ]
    )
    regime = pl.DataFrame(
        [
            {
                "source_run": "run_a",
                "side": "up",
                "candidate_name": "up_rocket_64_v1",
                "step_idx": 1,
                "pred_batch_id": 101,
                "regime_model": "gmm_markov",
                "regime_status": "ok",
                "regime_state": 2,
            }
        ]
    )

    out = regime_signal_quality(raw, regime)
    row = out.to_dicts()[0]

    assert row["requested_prediction_source"] == "effective_selected"
    assert row["prediction_source"] == "row_rule_active"
    assert row["regime_state"] == 2
