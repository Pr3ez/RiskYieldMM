from __future__ import annotations

import polars as pl

from regression_feature_engineering.walkforward.rank_signal_regime_diagnostic import (
    CURRENT_OUTCOME_COLUMNS,
    ChangeConfig,
    RegimeConfig,
    TargetMatchConfig,
    assign_past_only_regimes,
    change_flags_by_window,
    change_feature_columns,
    combine_regime_context,
    detect_change_events,
    label_target_match,
    prior_available_batches,
    safe_regime_context,
    sort_router_runs_chronologically,
    state_quality_summary,
    suppression_candidates_from_matches,
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

    assert prior_available_batches(available, 14, lookback=3, include_current=False) == [10, 11, 12]
    assert prior_available_batches(available, 14, lookback=3, include_current=True) == [11, 12, 14]


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


def test_change_feature_columns_can_select_market_context() -> None:
    frame = pl.DataFrame(
        {
            "score_mean": [0.1],
            "market_volatility_state_mean_last_z": [2.0],
            "market_volatility_state_mean_last": [0.5],
        }
    )

    assert change_feature_columns(frame, "router_context") == ["score_mean"]
    assert change_feature_columns(frame, "market_context") == ["market_volatility_state_mean_last_z"]
    assert change_feature_columns(frame, "combined") == ["score_mean", "market_volatility_state_mean_last_z"]


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
            pca_components=2,
            min_history_windows=20,
            lookback_windows=20,
            random_seed=7,
            model_mode="gmm_markov",
        ),
    )

    assert out["regime_status"][:20].to_list() == ["insufficient_history"] * 20
    assert "ok" in out["regime_status"][20:].to_list()


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


def test_state_quality_summary_aggregates_signal_quality_by_state() -> None:
    quality = pl.DataFrame(
        [
            {
                "side": "up",
                "candidate_name": "up_rocket_64_v1",
                "regime_model": "gmm_markov_proxy",
                "regime_status": "ok",
                "regime_state": 0,
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

    row = summary.to_dicts()[0]
    assert row["signals"] == 6
    assert row["true_positives"] == 4
    assert row["precision"] == 4 / 6


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
    assert row["cusum_count"] == 1
    assert row["page_hinkley_count"] == 1
    assert row["has_any_change"] is True
    assert row["has_cusum"] is True
    assert row["has_page_hinkley"] is True


def test_label_target_match_and_suppression_candidates() -> None:
    metrics = pl.DataFrame(
        [
            {
                "side": "down",
                "candidate_name": "down_rocket_16_diag_v1",
                "regime_state": 0,
                "signals": 100,
                "precision_lift": 0.95,
                "false_discovery_rate": 0.64,
            },
            {
                "side": "up",
                "candidate_name": "up_rocket_64_v1",
                "regime_state": 1,
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
