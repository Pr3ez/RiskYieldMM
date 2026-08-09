from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import polars as pl
import pytest

import regression_feature_engineering.walkforward.optimize as optimize_module
from regression_feature_engineering.walkforward.ablation import select_ablation_features
from regression_feature_engineering.walkforward.classification.cli import (
    best_trial,
    model_updates_from_best,
    policy_from_best,
    split_tuning_holdout_windows,
)
from regression_feature_engineering.walkforward.classification.metrics import (
    DECISION_POLICY_BATCH_TOPK_OFFLINE,
    DECISION_POLICY_CAUSAL_SIGNAL_BUDGET,
    DECISION_POLICY_THRESHOLD_ONLY,
    matthews_corrcoef,
    normalize_max_signals_grid,
    pr_auc_average_precision,
    signal_predictions,
    stable_prediction_quality_score,
    stable_signal_quality_score,
    validate_decision_policy_signal_grid,
    window_stability_constraints_reason,
    window_stability_metrics,
)
from regression_feature_engineering.walkforward.classification.runner import (
    SELECTOR_REFIT_VALIDATION_MASK,
    apply_policy_feature_transform,
    fixed_selected_policy_result,
    selected_feature_overlap,
    should_force_bad_objective,
)
from regression_feature_engineering.walkforward.classification.sequence import (
    SEQUENCE_CAUSAL_CNN_V1,
    SequenceEmbeddingConfig,
    append_causal_sequence_embeddings,
    causal_sequence_tensor,
)
from regression_feature_engineering.walkforward.classify import (
    TARGET_BINARY_DOWN_2X_UP,
    TARGET_BINARY_DOWN_2X_UP_ALIAS,
    TARGET_BINARY_UP_2X_DOWN,
    TARGET_BINARY_UP_2X_DOWN_ALIAS,
    binary_metrics,
    binary_target_expr,
    canonical_binary_target_col,
    classification_objective,
    select_decision_threshold,
)
from regression_feature_engineering.walkforward.cnn_feature_diagnostic import (
    feature_family,
    feature_timeframe,
    oriented_topk_lift,
    rank_auc,
    select_cnn_panel,
)
from regression_feature_engineering.walkforward.config import (
    CleanWalkForwardConfig,
    merge_config,
)
from regression_feature_engineering.walkforward.data import (
    build_batch_index,
    build_label_window_index,
    load_joined_batches,
    load_rpf_manifest,
    resolve_context,
)
from regression_feature_engineering.walkforward.decision_bank import (
    SIDE_DOWN,
    SeparateBankConfig,
    build_classifier_outcome_inventory,
    build_separate_bank_plan,
    summarize_separate_bank_plan,
)
from regression_feature_engineering.walkforward.ema_gate import (
    evaluate_timeframe_buffer,
    metrics_from_frame,
)
from regression_feature_engineering.walkforward.ema_regime import (
    EMARegimeWindowConfig,
    build_ema_regime_windows,
    filter_ema_prediction_windows,
)
from regression_feature_engineering.walkforward.evidence_panel import (
    PANEL_HYBRID_DIRECTION_BINARY,
    build_evidence_table,
    select_panel,
)
from regression_feature_engineering.walkforward.metrics import (
    objective_score,
    regression_metrics,
)
from regression_feature_engineering.walkforward.model import (
    CatBoostConfig,
    build_catboost_params,
)
from regression_feature_engineering.walkforward.optimize import (
    STAGES,
    run_optuna_stage,
    run_readiness,
    suggest_stage_config,
)
from regression_feature_engineering.walkforward.panel_select import build_candidate_pool
from regression_feature_engineering.walkforward.policy import (
    ALL_MANIFEST_FEATURES,
    ELASTICNET_LOGISTIC_V1,
    FROZEN_PANEL,
    TARGET_SPECIFIC_V2,
    FeaturePolicyConfig,
    load_panel_features,
    select_features,
)
from regression_feature_engineering.walkforward.regime_gate import (
    GATE_DOWN_DOMINANT,
    GATE_LOW_EDGE,
    GATE_TWO_SIDED,
    GATE_UP_DOMINANT,
    add_gate_target,
    evaluate_gated_decisions,
    gate_score_rows,
    metrics_from_binary_prediction,
    train_gate_thresholds,
)
from regression_feature_engineering.walkforward.signal_bank import (
    HYBRID_RECENT_SIGNAL_BANK,
    SIGNAL_BANK,
    SignalBankConfig,
    build_signal_bank_windows,
)
from regression_feature_engineering.walkforward.windows import (
    RPFWindow,
    build_windows,
    read_windows,
    write_windows,
)

TARGET = "target_reg_direction_extreme_up_share_hvol_v2"


def test_cnn_feature_diagnostic_helpers_identify_family_timeframe_and_rank_signal() -> (
    None
):
    assert feature_family("rpf_spike_15m_up_break_prox_l16_vol") == "spike_breakout"
    assert feature_family("rpf_room_1h_donchian_pos_l16_bnd") == "structural_room"
    assert feature_timeframe("rpf_mem_room_4h_donchian_pos_l16_bnd_lag1") == "4h"
    assert feature_timeframe("rpf_seq_factor_shape_l16_bnd") == "tf_global"

    y = np.asarray([0, 0, 1, 1], dtype=int)
    x = np.asarray([0.1, 0.2, 0.8, 0.9], dtype=float)
    assert rank_auc(y, x) == pytest.approx(1.0)
    assert oriented_topk_lift(y, x, k=2) == pytest.approx(1.0)


def test_cnn_feature_panel_selection_respects_family_and_timeframe_limits() -> None:
    scores = pl.DataFrame(
        {
            "feature": [
                "rpf_spike_15m_a",
                "rpf_spike_15m_b",
                "rpf_room_1h_a",
                "rpf_room_4h_a",
            ],
            "family": [
                "spike_breakout",
                "spike_breakout",
                "structural_room",
                "structural_room",
            ],
            "timeframe": ["15m", "15m", "1h", "4h"],
            "cnn_candidate_score": [0.9, 0.8, 0.7, 0.6],
            "nonconstant_batch_rate": [1.0, 1.0, 1.0, 0.1],
            "drop_reason": [None, None, None, None],
        }
    )

    selected = select_cnn_panel(
        scores,
        selected_count=3,
        per_family_limit=1,
        per_timeframe_limit=1,
        min_nonconstant_batch_rate=0.25,
    )

    assert selected["feature"].to_list() == ["rpf_spike_15m_a", "rpf_room_1h_a"]
    assert selected["selected_rank"].to_list() == [1, 2]


def test_causal_cnn_embeddings_can_use_separate_sequence_panel() -> None:
    pytest.importorskip("torch")
    X_tab_train = np.asarray([[0.0], [1.0], [0.0], [1.0]], dtype="float32")
    X_tab_future = np.asarray([[0.5], [0.2]], dtype="float32")
    X_seq_train = np.asarray(
        [
            [0.0, 0.1],
            [0.2, 0.3],
            [0.8, 0.9],
            [1.0, 1.1],
        ],
        dtype="float32",
    )
    X_seq_future = np.asarray([[1.2, 1.3], [1.4, 1.5]], dtype="float32")
    y = np.asarray([0, 0, 1, 1], dtype=int)
    config = SequenceEmbeddingConfig(
        mode=SEQUENCE_CAUSAL_CNN_V1,
        sequence_length=2,
        embedding_dim=3,
        conv_channels=4,
        kernel_size=2,
        epochs=1,
        batch_size=2,
        max_train_rows=4,
        device="cpu",
    )

    train_out, future_out, diagnostics = append_causal_sequence_embeddings(
        X_train=X_tab_train,
        y_train=y,
        X_future=X_tab_future,
        config=config,
        X_sequence_train=X_seq_train,
        X_sequence_future=X_seq_future,
    )

    assert train_out.shape == (4, 4)
    assert future_out.shape == (2, 4)
    assert diagnostics["sequence_input_features"] == 2
    assert diagnostics["sequence_actual_embedding_dim"] == 3


def _ts(batch: int, row: int) -> datetime:
    return datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(
        hours=batch * 8, minutes=row
    )


def _write_fixture(
    project: Path, *, batches: int = 5, rows: int = 4, label_overlap: bool = False
) -> None:
    feature_root = (
        project / "data/htf_multiasset/btcusdt/regression_path_features_v1/8h_b/1m"
    )
    label_root = (
        project
        / "data/htf_multiasset/btcusdt/htf_4class_labels_reg_distance_horizon_vol_v2/1m"
    )
    feature_root.mkdir(parents=True)
    label_root.mkdir(parents=True)
    feature_cols = ("rpf_signal", "rpf_noise")
    (feature_root / "manifest.json").write_text(
        json.dumps(
            {
                "feature_set": "regression_path_features_v1",
                "root_id": "8h_b",
                "row_count": batches * rows,
                "feature_count": len(feature_cols),
                "feature_columns": list(feature_cols),
                "duplicate_count": 0,
                "null_feature_count": 0,
                "source_fingerprint": "fixture",
            }
        )
    )
    for batch in range(1, batches + 1):
        timestamps = [_ts(batch, row) for row in range(rows)]
        signal = [batch * 0.1 + row * 0.01 for row in range(rows)]
        target = [min(max(value, 0.0), 1.0) for value in signal]
        pl.DataFrame(
            {
                "timestamp": timestamps,
                "batch_id": [batch] * rows,
                "asset_id": ["BTCUSDT"] * rows,
                "root_id": ["8h_b"] * rows,
                "feature_set": ["regression_path_features_v1"] * rows,
                "rpf_align_15m_has_closed_bar": [True] * rows,
                "rpf_signal": signal,
                "rpf_noise": [float(row % 2) for row in range(rows)],
            }
        ).write_parquet(feature_root / f"batch_{batch:04d}.parquet")
        pl.DataFrame(
            {
                "timestamp": timestamps,
                "batch_id": [batch] * rows,
                "target_reg_distance_valid_v2": [True] * rows,
                TARGET: target,
                "label_window_start": [_ts(batch, rows)] * rows,
                "label_window_end": [_ts(batch + 1 if label_overlap else batch, rows)]
                * rows,
                "label_window_batch_id": [batch + 1 if label_overlap else batch] * rows,
                "target_reg_distance_horizon_minutes_v2": [240.0] * rows,
            }
        ).write_parquet(label_root / f"batch_{batch:04d}.parquet")


def _signal_bank_inventory() -> pl.DataFrame:
    rows = []
    for batch in range(1, 21):
        up_rate = 0.45
        down_rate = 0.45
        if batch in {10, 12, 14}:
            up_rate = 0.05
            down_rate = 0.95
        if batch in {9, 11, 13}:
            up_rate = 0.95
            down_rate = 0.05
        rows.append(
            {
                "batch_id": batch,
                "rows": 4,
                "batch_start_ts": _ts(batch, 0),
                "batch_end_ts": _ts(batch, 3),
                "label_window_batch_id_max": batch,
                "label_window_end_max": _ts(batch, 3),
                "up_dom_rate": up_rate,
                "down_dom_rate": down_rate,
                "mixed_rate": max(0.0, 1.0 - up_rate - down_rate),
                "extreme_total_mean": 1.0,
                "extreme_total_q80": 1.0,
                "up_extreme_mean": 1.0,
                "down_extreme_mean": 1.0,
            }
        )
    return pl.DataFrame(rows)


def _ema_regime_inventory() -> pl.DataFrame:
    rows = []
    for batch in range(1, 21):
        above_rate = 0.40
        below_rate = 0.40
        if batch in {9, 11, 13, 17, 18, 19}:
            above_rate = 0.90
            below_rate = 0.05
        if batch in {10, 12, 14, 16}:
            above_rate = 0.05
            below_rate = 0.90
        rows.append(
            {
                "batch_id": batch,
                "rows": 4,
                "batch_start_ts": _ts(batch, 0),
                "batch_end_ts": _ts(batch, 3),
                "label_window_batch_id_max": batch,
                "above_ema_rate": above_rate,
                "below_ema_rate": below_rate,
                "ema_distance_pct_mean": 0.01 if above_rate > below_rate else -0.01,
                "ema_distance_pct_q20": 0.005 if above_rate > below_rate else -0.02,
                "ema_distance_pct_q80": 0.02 if above_rate > below_rate else -0.005,
            }
        )
    return pl.DataFrame(rows)


def test_manifest_loader_uses_feature_columns_and_excludes_diagnostics(
    tmp_path: Path,
) -> None:
    _write_fixture(tmp_path)
    manifest = load_rpf_manifest(
        tmp_path
        / "data/htf_multiasset/btcusdt/regression_path_features_v1/8h_b/1m/manifest.json"
    )

    assert manifest.feature_columns == ("rpf_signal", "rpf_noise")
    assert not any(col.startswith("rpf_align_") for col in manifest.feature_columns)


def test_manifest_loader_rejects_retired_future_derived_session_features(
    tmp_path: Path,
) -> None:
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "feature_columns": [
                    "rpf_signal",
                    "rpf_regime_15m_session_progress_bnd",
                    "rpf_regime_1h_minutes_to_close_bnd",
                    "rpf_regime_4h_session_close_bnd",
                    "rpf_regime_1d_weekly_close_bnd",
                ]
            }
        )
    )

    with pytest.raises(ValueError, match="retired future-derived observed-session"):
        load_rpf_manifest(manifest_path)


def test_load_panel_features_validates_current_feature_universe(tmp_path: Path) -> None:
    panel = tmp_path / "panel.json"
    panel.write_text(json.dumps({"selected_features": ["rpf_a", "rpf_b"]}))

    assert load_panel_features(panel, ("rpf_a", "rpf_b", "rpf_c")) == ("rpf_a", "rpf_b")

    missing_panel = tmp_path / "bad_panel.json"
    missing_panel.write_text(
        json.dumps({"selected_features": ["rpf_a", "rpf_missing"]})
    )
    with pytest.raises(ValueError, match="outside current feature universe"):
        load_panel_features(missing_panel, ("rpf_a", "rpf_b"))


def test_evidence_panel_combines_diagnostics_and_binary_selected_history(
    tmp_path: Path,
) -> None:
    diagnostics = tmp_path / "diag" / "rpf_feature_diagnostic_inventory"
    diagnostics.mkdir(parents=True)
    selected_root = tmp_path / "selected"
    selected_run = selected_root / "rpf_clean_classification" / "run_a"
    selected_run.mkdir(parents=True)
    features = (
        "rpf_accept_12h_return_persist_l48_bnd",
        "rpf_conf_1h_up_volume_impulse_l48_bnd",
        "rpf_room_8h_down_to_low_l16_vol",
        "rpf_vol_tb_vol_z_l1440",
    )
    pl.DataFrame(
        {
            "family": [
                "acceptance_persistence",
                "interaction_confluence",
                "structural_room",
                "volatility_state",
            ],
            "timeframe": ["12h", "1h", "8h", "global"],
            "feature": list(features),
            "target": [
                "target_extreme_up_minus_down",
                "target_extreme_up_minus_down",
                "target_mean_total",
                "target_extreme_total",
            ],
            "max_abs_spearman": [0.26, 0.05, 0.20, 0.70],
            "mean_abs_spearman": [0.26, 0.05, 0.20, 0.70],
            "median_spearman": [0.26, 0.05, 0.20, -0.70],
            "max_rows": [100, 100, 100, 100],
            "diagnostic_sources": [1, 1, 1, 1],
        }
    ).write_parquet(diagnostics / "manifest_feature_correlation_best.parquet")
    pl.DataFrame(
        {
            "family": [
                "acceptance_persistence",
                "interaction_confluence",
                "structural_room",
                "volatility_state",
            ],
            "timeframe": ["12h", "1h", "8h", "global"],
            "feature": list(features),
            "target": [
                "target_extreme_up_minus_down",
                "target_extreme_up_minus_down",
                "target_mean_total",
                "target_extreme_total",
            ],
            "max_abs_bin_spread": [1.20, 0.20, 0.40, 1.60],
            "median_bin_spread": [1.20, 0.20, 0.40, -1.60],
            "max_low_rows": [10, 10, 10, 10],
            "max_high_rows": [10, 10, 10, 10],
            "diagnostic_sources": [1, 1, 1, 1],
        }
    ).write_parquet(diagnostics / "manifest_feature_bin_spread_best.parquet")
    pl.DataFrame(
        {
            "target_col": ["target_cls_extreme_up_ge_2x_down_hvol_v2"] * 3,
            "feature": [
                "rpf_conf_1h_up_volume_impulse_l48_bnd",
                "rpf_conf_1h_up_volume_impulse_l48_bnd",
                "rpf_room_8h_down_to_low_l16_vol",
            ],
            "pred_batch_id": [1, 2, 1],
        }
    ).write_parquet(selected_run / "selected_features.parquet")

    evidence = build_evidence_table(
        diagnostics_root=tmp_path / "diag",
        selected_feature_root=selected_root,
        manifest_features=features,
        target_col="target_cls_extreme_up_ge_2x_down_hvol_v2",
    )
    panel = select_panel(
        evidence,
        panel_kind=PANEL_HYBRID_DIRECTION_BINARY,
        selected_count=3,
        per_family_limit=2,
        min_score=0.0,
    )

    selected = set(panel["feature"].to_list())
    assert "rpf_accept_12h_return_persist_l48_bnd" in selected
    assert "rpf_conf_1h_up_volume_impulse_l48_bnd" in selected
    assert "rpf_vol_tb_vol_z_l1440" not in selected
    assert "direction_side_spearman" in evidence.columns
    assert "direction_side_bin_spread" in evidence.columns


def test_evidence_panel_is_side_aware_for_down_target(tmp_path: Path) -> None:
    diagnostics = tmp_path / "diag" / "rpf_feature_diagnostic_inventory"
    diagnostics.mkdir(parents=True)
    selected_root = tmp_path / "selected"
    features = (
        "rpf_conf_1h_up_volume_impulse_l48_bnd",
        "rpf_conf_1h_down_volume_impulse_l48_bnd",
        "rpf_room_8h_value_dist_l16_vol",
    )
    pl.DataFrame(
        {
            "feature": list(features),
            "target": ["target_extreme_up_minus_down"] * 3,
            "max_abs_spearman": [0.40, 0.35, 0.10],
            "median_spearman": [0.40, -0.35, 0.10],
        }
    ).write_parquet(diagnostics / "manifest_feature_correlation_best.parquet")
    pl.DataFrame(
        {
            "feature": list(features),
            "target": ["target_extreme_up_minus_down"] * 3,
            "max_abs_bin_spread": [0.40, 0.35, 0.10],
            "median_bin_spread": [0.40, -0.35, 0.10],
        }
    ).write_parquet(diagnostics / "manifest_feature_bin_spread_best.parquet")

    evidence = build_evidence_table(
        diagnostics_root=tmp_path / "diag",
        selected_feature_root=selected_root,
        manifest_features=features,
        target_col="target_cls_extreme_down_ge_2x_up_hvol_v2",
    )
    ranked = evidence.sort("hybrid_direction_binary_score", descending=True)[
        "feature"
    ].to_list()

    assert ranked[0] == "rpf_conf_1h_down_volume_impulse_l48_bnd"
    assert (
        evidence.filter(pl.col("feature") == "rpf_conf_1h_down_volume_impulse_l48_bnd")[
            "direction_side_spearman"
        ].item()
        > 0.0
    )
    assert evidence.filter(
        pl.col("feature") == "rpf_conf_1h_up_volume_impulse_l48_bnd"
    )["opposite_side_token_score"].item() == pytest.approx(1.0)


def test_feature_label_join_is_exact_on_timestamp_batch(tmp_path: Path) -> None:
    _write_fixture(tmp_path)
    context = resolve_context(
        project_root=tmp_path, asset="BTCUSDT", root="8h/B", target_col=TARGET
    )
    joined = load_joined_batches(context, [1])

    assert joined.height == 4
    assert {"timestamp", "batch_id", TARGET, "rpf_signal", "rpf_noise"}.issubset(
        joined.columns
    )


def test_sparse_windows_use_available_positions_not_numeric_continuity(
    tmp_path: Path,
) -> None:
    index = pl.DataFrame(
        {
            "rpf_available_pos": [0, 1, 2],
            "batch_id": [10, 11, 20],
            "batch_start_ts": [_ts(1, 0), _ts(2, 0), _ts(3, 0)],
            "batch_end_ts": [_ts(1, 1), _ts(2, 1), _ts(3, 1)],
            "valid_row_count": [4, 4, 4],
        }
    )

    windows = build_windows(index, lookback_batches=1, val_batches=1, n_steps=1)

    assert windows[0].pred_batch_id == 20
    assert windows[0].train_batch_ids == (10,)
    assert windows[0].val_batch_ids == (11,)


def test_batch_index_ignores_extra_feature_columns(tmp_path: Path) -> None:
    _write_fixture(tmp_path)
    path = (
        tmp_path
        / "data/htf_multiasset/btcusdt/regression_path_features_v1/8h_b/1m/batch_0002.parquet"
    )
    frame = pl.read_parquet(path).with_columns(
        pl.lit(1.0).alias("unexpected_extra_feature")
    )
    frame.write_parquet(path)
    context = resolve_context(
        project_root=tmp_path, asset="BTCUSDT", root="8h/B", target_col=TARGET
    )

    index = build_batch_index(context)

    assert index.height == 5
    assert index["batch_id"].to_list() == [1, 2, 3, 4, 5]


def test_frozen_windows_roundtrip(tmp_path: Path) -> None:
    _write_fixture(tmp_path)
    context = resolve_context(
        project_root=tmp_path, asset="BTCUSDT", root="8h/B", target_col=TARGET
    )
    windows = build_windows(
        build_batch_index(context), lookback_batches=2, val_batches=1, n_steps=1
    )
    path = write_windows(tmp_path / "frozen_windows.parquet", windows)

    assert read_windows(path) == windows
    frame = pl.read_parquet(path)
    assert {
        "train_start_ts",
        "val_start_ts",
        "pred_start_ts",
        "train_valid_row_count",
    }.issubset(frame.columns)


def test_feature_selection_uses_train_signal_only() -> None:
    frame = pl.DataFrame(
        {
            TARGET: [0.1, 0.2, 0.3, 0.4, 0.5],
            "rpf_signal": [0.1, 0.2, 0.3, 0.4, 0.5],
            "rpf_noise": [1.0, 0.0, 1.0, 0.0, 1.0],
        }
    )

    result = select_features(
        frame,
        target_col=TARGET,
        feature_columns=("rpf_signal", "rpf_noise"),
        config=FeaturePolicyConfig(
            policy=TARGET_SPECIFIC_V2,
            max_features=1,
            min_selected_features=1,
            min_abs_spearman=0.01,
        ),
    )

    assert result.selected_features == ("rpf_signal",)
    assert result.clip_bounds["rpf_signal"][0] <= 0.1


def test_all_manifest_policy_uses_every_feature_without_clip_bounds() -> None:
    frame = pl.DataFrame(
        {
            TARGET: [0.1, 0.2, 0.3],
            "rpf_signal": [1.0, 2.0, 3.0],
            "rpf_noise": [3.0, 2.0, 1.0],
        }
    )

    result = select_features(
        frame,
        target_col=TARGET,
        feature_columns=("rpf_signal", "rpf_noise"),
        config=FeaturePolicyConfig(policy=ALL_MANIFEST_FEATURES),
    )

    assert result.selected_features == ("rpf_signal", "rpf_noise")
    assert result.clip_bounds == {}
    assert result.detail["final_status"].to_list() == [
        "selected_all_manifest",
        "selected_all_manifest",
    ]


def test_frozen_panel_policy_uses_panel_features_only(tmp_path: Path) -> None:
    panel_path = tmp_path / "selected_panel.json"
    panel_path.write_text(json.dumps({"selected_features": ["rpf_signal"]}))
    frame = pl.DataFrame(
        {
            TARGET: [0.1, 0.2, 0.3],
            "rpf_signal": [1.0, 2.0, 3.0],
            "rpf_noise": [3.0, 2.0, 1.0],
        }
    )

    result = select_features(
        frame,
        target_col=TARGET,
        feature_columns=("rpf_signal", "rpf_noise"),
        config=FeaturePolicyConfig(
            policy=FROZEN_PANEL, frozen_panel_path=str(panel_path)
        ),
    )

    assert result.selected_features == ("rpf_signal",)
    assert result.clip_bounds == {}
    assert (
        result.detail.filter(pl.col("feature") == "rpf_noise")["drop_reason"].item()
        == "not_in_frozen_panel"
    )


def test_elasticnet_logistic_policy_selects_train_predictive_features() -> None:
    y = np.array([0, 0, 0, 1, 1, 1] * 20)
    signal = y.astype(float) * 2.0 - 1.0
    frame = pl.DataFrame(
        {
            "target_cls": y,
            "rpf_signal": signal,
            "rpf_signal_copy": signal * 0.9,
            "rpf_noise": np.tile([0.2, -0.1, 0.4, -0.3, 0.1, -0.2], 20),
            "rpf_constant": np.ones(len(y)),
        }
    )

    result = select_features(
        frame,
        target_col="target_cls",
        feature_columns=("rpf_signal", "rpf_signal_copy", "rpf_noise", "rpf_constant"),
        config=FeaturePolicyConfig(
            policy=ELASTICNET_LOGISTIC_V1,
            max_features=2,
            min_selected_features=1,
            elasticnet_c=1.0,
            elasticnet_l1_ratio=0.8,
            elasticnet_max_iter=500,
            elasticnet_tol=0.001,
        ),
    )

    assert (
        "rpf_signal" in result.selected_features
        or "rpf_signal_copy" in result.selected_features
    )
    assert len(result.selected_features) <= 2
    constant = result.detail.filter(pl.col("feature") == "rpf_constant").row(
        0, named=True
    )
    assert constant["drop_reason"] == "constant_or_invalid_scale"


def test_elasticnet_policy_scaler_feeds_selected_features_to_catboost() -> None:
    y = np.array([0, 0, 0, 1, 1, 1] * 20)
    signal = y.astype(float) * 20.0 + 100.0
    frame = pl.DataFrame(
        {
            "target_cls": y,
            "rpf_signal": signal,
            "rpf_noise": np.tile([0.2, -0.1, 0.4, -0.3, 0.1, -0.2], 20),
        }
    )
    policy = FeaturePolicyConfig(
        policy=ELASTICNET_LOGISTIC_V1,
        max_features=1,
        min_selected_features=1,
        elasticnet_c=1.0,
        elasticnet_l1_ratio=0.8,
        elasticnet_max_iter=500,
        elasticnet_tol=0.001,
    )
    result = select_features(
        frame,
        target_col="target_cls",
        feature_columns=("rpf_signal", "rpf_noise"),
        config=policy,
    )
    selected = result.selected_features
    X_train = frame.select(selected).to_numpy().astype("float64")
    X_val = (
        pl.DataFrame({"rpf_signal": [100.0, 120.0], "rpf_noise": [0.0, 0.0]})
        .select(selected)
        .to_numpy()
        .astype("float64")
    )
    X_pred = (
        pl.DataFrame({"rpf_signal": [110.0], "rpf_noise": [0.0]})
        .select(selected)
        .to_numpy()
        .astype("float64")
    )

    X_train_scaled, X_val_scaled, X_pred_scaled, diagnostics = (
        apply_policy_feature_transform(
            policy=policy,
            policy_result=result,
            selected=selected,
            X_train=X_train,
            X_val=X_val,
            X_pred=X_pred,
        )
    )

    assert diagnostics["feature_transform_policy"] == "elasticnet_train_standardize"
    assert X_train_scaled.shape[1] == len(selected)
    assert np.allclose(X_train_scaled.mean(axis=0), 0.0, atol=1e-9)
    assert np.allclose(X_train_scaled.std(axis=0), 1.0, atol=1e-9)
    assert np.all(np.isfinite(X_val_scaled))
    assert np.all(np.isfinite(X_pred_scaled))


def test_validation_mask_refit_keeps_selected_features_and_train_val_scaler() -> None:
    y = np.array([0, 0, 1, 1] * 10)
    train = pl.DataFrame(
        {
            "target_cls": y,
            "rpf_signal": y.astype(float) * 2.0 + 10.0,
            "rpf_noise": np.linspace(-1.0, 1.0, len(y)),
        }
    )
    validation_result = select_features(
        train,
        target_col="target_cls",
        feature_columns=("rpf_signal", "rpf_noise"),
        config=FeaturePolicyConfig(
            policy=ELASTICNET_LOGISTIC_V1,
            max_features=1,
            min_selected_features=1,
            elasticnet_c=1.0,
            elasticnet_l1_ratio=0.8,
            elasticnet_max_iter=500,
            elasticnet_tol=0.001,
        ),
    )
    selected = validation_result.selected_features
    train_val = pl.concat(
        [
            train,
            pl.DataFrame(
                {
                    "target_cls": [0, 1],
                    "rpf_signal": [20.0, 30.0],
                    "rpf_noise": [5.0, 6.0],
                }
            ),
        ],
        how="vertical",
    )

    prediction_result = fixed_selected_policy_result(
        train_val,
        selected=selected,
        validation_detail=validation_result.detail,
    )

    assert SELECTOR_REFIT_VALIDATION_MASK == "validation_mask"
    assert prediction_result.selected_features == selected
    assert selected_feature_overlap(selected, prediction_result.selected_features)[
        "jaccard"
    ] == pytest.approx(1.0)
    stat = prediction_result.detail.filter(pl.col("feature") == selected[0]).row(
        0, named=True
    )
    assert stat["feature_mean_train"] == pytest.approx(train_val[selected[0]].mean())
    assert stat["feature_std_train"] == pytest.approx(
        train_val[selected[0]].std(ddof=0)
    )


def test_elasticnet_policy_train_only_prefilter_limits_candidates() -> None:
    y = np.array([0, 0, 0, 1, 1, 1] * 20)
    strong = y.astype(float) * 2.0 - 1.0
    weak = np.tile([0.1, -0.2, 0.0, 0.2, -0.1, 0.0], 20)
    frame = pl.DataFrame(
        {
            "target_cls": y,
            "rpf_strong": strong,
            "rpf_weak": weak,
            "rpf_noise": np.sin(np.arange(len(y))),
        }
    )

    result = select_features(
        frame,
        target_col="target_cls",
        feature_columns=("rpf_strong", "rpf_weak", "rpf_noise"),
        config=FeaturePolicyConfig(
            policy=ELASTICNET_LOGISTIC_V1,
            max_features=1,
            min_selected_features=1,
            elasticnet_c=1.0,
            elasticnet_l1_ratio=0.8,
            elasticnet_max_iter=500,
            elasticnet_tol=0.001,
            elasticnet_prefilter_features=1,
        ),
    )

    assert result.selected_features == ("rpf_strong",)
    assert (
        result.detail.filter(pl.col("feature") == "rpf_weak")["drop_reason"].item()
        == "below_elasticnet_prefilter"
    )


def test_causal_sequence_tensor_uses_only_past_and_current_rows() -> None:
    X = np.asarray([[1.0], [2.0], [3.0], [4.0]], dtype=np.float32)
    out = causal_sequence_tensor(X, np.asarray([0, 2, 3]), sequence_length=3)

    assert out.shape == (3, 1, 3)
    assert out[0, 0].tolist() == [0.0, 0.0, 1.0]
    assert out[1, 0].tolist() == [1.0, 2.0, 3.0]
    assert out[2, 0].tolist() == [2.0, 3.0, 4.0]


def test_causal_cnn_embeddings_are_opt_in_and_append_features() -> None:
    torch = pytest.importorskip("torch")
    _ = torch
    X_train = np.asarray(
        [[float(idx), float(idx % 3)] for idx in range(12)],
        dtype=np.float32,
    )
    y_train = np.asarray([0, 0, 1, 1, 0, 1, 0, 1, 0, 1, 0, 1], dtype=np.int64)
    X_future = np.asarray([[12.0, 0.0], [13.0, 1.0]], dtype=np.float32)

    disabled_train, disabled_future, disabled_diag = append_causal_sequence_embeddings(
        X_train=X_train,
        y_train=y_train,
        X_future=X_future,
        config=SequenceEmbeddingConfig(),
    )
    assert disabled_diag["sequence_embedding_enabled"] is False
    assert disabled_train.shape == X_train.shape
    assert disabled_future.shape == X_future.shape

    enabled_train, enabled_future, enabled_diag = append_causal_sequence_embeddings(
        X_train=X_train,
        y_train=y_train,
        X_future=X_future,
        config=SequenceEmbeddingConfig(
            mode=SEQUENCE_CAUSAL_CNN_V1,
            sequence_length=4,
            embedding_dim=3,
            conv_channels=4,
            kernel_size=2,
            epochs=1,
            batch_size=4,
            max_train_rows=8,
            device="cpu",
        ),
    )

    assert enabled_diag["sequence_embedding_enabled"] is True
    assert enabled_diag["sequence_cnn_train_rows"] == 8
    assert enabled_train.shape == (12, 5)
    assert enabled_future.shape == (2, 5)
    assert np.all(np.isfinite(enabled_train))
    assert np.all(np.isfinite(enabled_future))


def test_classification_holdout_split_reserves_latest_windows() -> None:
    windows = [
        RPFWindow(
            step_idx=idx,
            pred_pos=idx,
            pred_batch_id=100 + idx,
            train_batch_ids=(1, 2),
            val_batch_ids=(3,),
            pred_valid_row_count=4,
        )
        for idx in range(5)
    ]

    tuning, holdout = split_tuning_holdout_windows(windows, holdout_steps=2)

    assert [window.pred_batch_id for window in tuning] == [100, 101, 102]
    assert [window.pred_batch_id for window in holdout] == [103, 104]
    assert split_tuning_holdout_windows(windows, holdout_steps=0) == (windows, [])
    with pytest.raises(ValueError, match="leaves no tuning windows"):
        split_tuning_holdout_windows(windows, holdout_steps=5)


def test_classification_holdout_reconstructs_locked_best_config() -> None:
    base_policy = FeaturePolicyConfig(
        policy=ELASTICNET_LOGISTIC_V1,
        max_features=80,
        min_selected_features=20,
        elasticnet_c=0.03,
        elasticnet_l1_ratio=0.5,
        elasticnet_max_iter=1000,
        elasticnet_tol=0.001,
        elasticnet_class_weight="balanced",
        elasticnet_coef_epsilon=1e-8,
        elasticnet_prefilter_features=160,
    )
    best = {
        "policy_max_features": 120,
        "policy_min_selected_features": 30,
        "elasticnet_c": 0.1,
        "elasticnet_l1_ratio": 0.75,
        "elasticnet_max_iter": 500,
        "elasticnet_tol": 0.01,
        "elasticnet_class_weight": "none",
        "elasticnet_coef_epsilon": 1e-6,
        "elasticnet_prefilter_features": 240,
        "iterations": 400,
        "depth": 3,
        "learning_rate": 0.02,
        "l2_leaf_reg": 30.0,
        "early_stopping_rounds": 50,
        "od_wait": 50,
    }

    policy = policy_from_best(base_policy, best)
    model_updates = model_updates_from_best(best)

    assert policy.max_features == 120
    assert policy.min_selected_features == 30
    assert policy.elasticnet_c == pytest.approx(0.1)
    assert policy.elasticnet_prefilter_features == 240
    assert model_updates == {
        "iterations": 400,
        "depth": 3,
        "learning_rate": 0.02,
        "l2_leaf_reg": 30.0,
        "early_stopping_rounds": 50,
        "od_wait": 50,
    }


def test_classification_best_trial_ignores_rejected_threshold_constraints() -> None:
    trials = [
        {
            "trial_number": 0,
            "status": "rejected:threshold_constraints",
            "objective_direction": "minimize",
            "objective_value": 0.1,
        },
        {
            "trial_number": 1,
            "status": "ok",
            "objective_direction": "minimize",
            "objective_value": 0.3,
        },
    ]

    assert best_trial(trials)["trial_number"] == 1


def test_classification_best_trial_uses_stable_quality_score_even_when_stability_rejected() -> (
    None
):
    trials = [
        {
            "trial_number": 0,
            "status": "ok",
            "objective_metric": "stable_prediction_quality",
            "objective_direction": "maximize",
            "objective_value": -1.0,
        },
        {
            "trial_number": 1,
            "status": "rejected:window_stability",
            "objective_metric": "stable_prediction_quality",
            "objective_direction": "maximize",
            "objective_value": 0.5,
        },
    ]

    assert best_trial(trials)["trial_number"] == 1


def test_panel_candidate_pool_uses_existing_diagnostic_scores(tmp_path: Path) -> None:
    report_root = (
        tmp_path / "test_output/regression_feature_engineering_btcusdt_8h_b_screen"
    )
    report_dir = report_root / "family_btcusdt_8h_b"
    report_dir.mkdir(parents=True)
    pl.DataFrame(
        {
            "feature": ["rpf_room_a", "rpf_room_b", "rpf_vol_a"],
            "target": ["target_extreme_up_minus_down"] * 3,
            "pearson": [0.10, 0.01, 0.03],
            "spearman": [0.20, 0.01, -0.06],
            "abs_spearman": [0.20, 0.01, 0.06],
            "rows": [100, 100, 100],
        }
    ).write_parquet(report_dir / "feature_target_correlations.parquet")
    pl.DataFrame(
        {
            "feature": ["rpf_room_a", "rpf_vol_a"],
            "target": ["target_extreme_up_minus_down", "target_extreme_up_minus_down"],
            "q20": [0.0, 0.0],
            "q80": [1.0, 1.0],
            "low_mean": [0.1, 0.2],
            "high_mean": [0.4, 0.5],
            "high_minus_low": [0.3, 0.3],
            "low_rows": [20, 20],
            "high_rows": [20, 20],
        }
    ).write_parquet(report_dir / "feature_bin_spreads.parquet")

    candidates, _ = build_candidate_pool(
        diagnostics_root=tmp_path / "test_output",
        asset="BTCUSDT",
        root_id="8h_b",
        manifest_features=("rpf_room_a", "rpf_room_b", "rpf_vol_a"),
        candidate_targets=("target_extreme_up_minus_down",),
        candidate_limit=10,
        per_family_limit=10,
        min_abs_spearman=0.02,
        min_bin_spread_abs=0.0,
    )

    assert candidates["feature"].to_list() == ["rpf_room_a", "rpf_vol_a"]


def test_constant_prediction_reports_null_reason() -> None:
    metrics = regression_metrics(np.array([0.1, 0.2, 0.3]), np.array([0.2, 0.2, 0.2]))

    assert metrics["spearman"] is None
    assert metrics["spearman_null_reason"] == "constant_prediction"


def test_binary_up_2x_down_target_rule() -> None:
    frame = pl.DataFrame(
        {
            "target_reg_distance_up_extreme_hvol_v2": [0.0, 1.0, 2.0, 3.0, 1.0],
            "target_reg_distance_down_extreme_hvol_v2": [0.0, 0.0, 1.1, 1.0, 3.0],
        }
    ).with_columns(
        binary_target_expr(TARGET_BINARY_UP_2X_DOWN),
        binary_target_expr(TARGET_BINARY_DOWN_2X_UP),
    )

    assert frame[TARGET_BINARY_UP_2X_DOWN].to_list() == [0, 1, 0, 1, 0]
    assert frame[TARGET_BINARY_DOWN_2X_UP].to_list() == [0, 0, 0, 0, 1]


def test_regime_gate_dominant_target_rules() -> None:
    frame = pl.DataFrame(
        {
            "target_reg_distance_up_extreme_hvol_v2": [0.0, 1.0, 2.0, 3.0, 1.0],
            "target_reg_distance_down_extreme_hvol_v2": [0.0, 0.0, 1.1, 1.0, 3.0],
        }
    )

    up = add_gate_target(frame, gate_target=GATE_UP_DOMINANT, thresholds={})
    down = add_gate_target(frame, gate_target=GATE_DOWN_DOMINANT, thresholds={})

    assert up[GATE_UP_DOMINANT].to_list() == [1, 1, 0, 1, 0]
    assert down[GATE_DOWN_DOMINANT].to_list() == [1, 0, 0, 0, 1]


def test_regime_gate_quantile_targets_use_train_thresholds() -> None:
    train = pl.DataFrame(
        {
            "target_reg_distance_up_extreme_hvol_v2": [1.0, 2.0, 3.0, 4.0],
            "target_reg_distance_down_extreme_hvol_v2": [1.0, 2.0, 3.0, 4.0],
        }
    )
    thresholds = train_gate_thresholds(train, high_quantile=0.75, low_quantile=0.25)
    later = pl.DataFrame(
        {
            "target_reg_distance_up_extreme_hvol_v2": [1.1, 3.5, 4.5],
            "target_reg_distance_down_extreme_hvol_v2": [1.1, 1.0, 4.5],
        }
    )

    two_sided = add_gate_target(
        later, gate_target=GATE_TWO_SIDED, thresholds=thresholds
    )
    low_edge = add_gate_target(later, gate_target=GATE_LOW_EDGE, thresholds=thresholds)

    assert thresholds["up_high"] == pytest.approx(3.25)
    assert thresholds["up_low"] == pytest.approx(1.75)
    assert two_sided[GATE_TWO_SIDED].to_list() == [0, 0, 1]
    assert low_edge[GATE_LOW_EDGE].to_list() == [1, 0, 0]


def test_gate_score_rows_join_keys_are_exact() -> None:
    meta = pl.DataFrame(
        {
            "timestamp": [_ts(1, 0), _ts(1, 1)],
            "batch_id": [1, 1],
        }
    )

    rows = gate_score_rows(
        meta=meta,
        y_true=np.array([0, 1]),
        prob=np.array([0.2, 0.8]),
        threshold=0.5,
        gate_target=GATE_UP_DOMINANT,
        step_idx=7,
        pred_batch_id=11,
    )

    assert rows[0]["timestamp"] == _ts(1, 0)
    assert rows[0]["batch_id"] == 1
    assert rows[1]["gate_active"] == 1
    assert rows[1]["pred_batch_id"] == 11


def test_gated_metrics_match_direct_confusion_matrix(tmp_path: Path) -> None:
    score_path = tmp_path / "classifier_scores.parquet"
    pl.DataFrame(
        {
            "timestamp": [_ts(1, 0), _ts(1, 1), _ts(1, 2), _ts(1, 3)],
            "batch_id": [1, 1, 1, 1],
            "target": [0, 0, 1, 1],
            "prob": [0.9, 0.8, 0.7, 0.1],
        }
    ).write_parquet(score_path)
    gate_scores = [
        {
            "trial_number": 2,
            "timestamp": _ts(1, 0),
            "batch_id": 1,
            "gate_prob": 0.1,
            "gate_active": 0,
            "gate_threshold": 0.5,
        },
        {
            "trial_number": 2,
            "timestamp": _ts(1, 1),
            "batch_id": 1,
            "gate_prob": 0.8,
            "gate_active": 1,
            "gate_threshold": 0.5,
        },
        {
            "trial_number": 2,
            "timestamp": _ts(1, 2),
            "batch_id": 1,
            "gate_prob": 0.8,
            "gate_active": 1,
            "gate_threshold": 0.5,
        },
        {
            "trial_number": 2,
            "timestamp": _ts(1, 3),
            "batch_id": 1,
            "gate_prob": 0.2,
            "gate_active": 0,
            "gate_threshold": 0.5,
        },
    ]

    rows = evaluate_gated_decisions(
        gate_scores=gate_scores,
        best_trial={"trial_number": 2},
        classifier_score_path=score_path,
        classifier_side="up",
        classifier_trial_number=None,
        classifier_threshold=0.5,
    )

    assert rows[0]["ungated_fp"] == 2
    assert rows[0]["ungated_tp"] == 1
    assert rows[0]["gated_fp"] == 1
    assert rows[0]["gated_tp"] == 1
    assert rows[0]["false_positive_reduction"] == pytest.approx(0.5)


def test_metrics_from_binary_prediction() -> None:
    metrics = metrics_from_binary_prediction(
        np.array([0, 0, 1, 1]), np.array([1, 0, 1, 0])
    )

    assert metrics["tp"] == 1
    assert metrics["tn"] == 1
    assert metrics["fp"] == 1
    assert metrics["fn"] == 1
    assert metrics["precision"] == pytest.approx(0.5)


def test_ema_gate_evaluates_up_above_and_down_below() -> None:
    frame = pl.DataFrame(
        {
            "timestamp": [_ts(1, idx) for idx in range(8)],
            "batch_id": [1] * 8,
            "side": ["up"] * 4 + ["down"] * 4,
            "target": [1, 0, 1, 0, 1, 0, 1, 0],
            "predicted_positive": [1, 1, 1, 0, 1, 1, 0, 1],
            "ema_distance_pct": [0.01, 0.01, -0.01, 0.01, -0.01, -0.01, -0.01, 0.01],
        }
    )

    rows = evaluate_timeframe_buffer(frame, timeframe="1h", buffer=0.0)
    by_side = {row["side"]: row for row in rows}

    assert by_side["up"]["gated_tp"] == 1
    assert by_side["up"]["gated_fp"] == 1
    assert by_side["up"]["false_positive_reduction"] == pytest.approx(0.0)
    assert by_side["up"]["recall_retained"] == pytest.approx(0.5)
    assert by_side["down"]["gated_tp"] == 1
    assert by_side["down"]["gated_fp"] == 1
    assert by_side["down"]["recall_retained"] == pytest.approx(1.0)


def test_ema_gate_binary_metrics_from_frame() -> None:
    frame = pl.DataFrame({"target": [0, 0, 1, 1], "pred": [1, 0, 1, 0]})

    metrics = metrics_from_frame(frame, prediction_col="pred")

    assert metrics["tp"] == 1
    assert metrics["fp"] == 1
    assert metrics["precision"] == pytest.approx(0.5)


def test_ema_regime_windows_select_mature_matching_batches() -> None:
    base = RPFWindow(
        step_idx=0,
        pred_pos=20,
        pred_batch_id=20,
        train_batch_ids=tuple(range(1, 17)),
        val_batch_ids=(17, 18, 19),
        pred_valid_row_count=4,
    )

    windows, audit = build_ema_regime_windows(
        [base],
        _ema_regime_inventory(),
        config=EMARegimeWindowConfig(
            timeframe="1h",
            side="up",
            dominance_rate=0.8,
            train_batches=2,
            val_batches=2,
            candidate_lookback_batches=20,
            label_maturity_embargo_batches=1,
        ),
    )

    assert windows[0].pred_batch_id == 20
    assert set(windows[0].val_batch_ids) == {17, 18}
    assert set(windows[0].train_batch_ids) == {11, 13}
    assert 19 not in windows[0].train_batch_ids
    assert 19 not in windows[0].val_batch_ids
    assert audit[0]["mature_cutoff_batch_id"] == 18
    assert audit[0]["train_regime_rate_weighted"] == pytest.approx(0.9)
    assert audit[0]["val_regime_rate_weighted"] == pytest.approx(0.9)


def test_ema_prediction_windows_keep_only_active_regime_batches() -> None:
    windows = [
        RPFWindow(
            step_idx=batch,
            pred_pos=batch,
            pred_batch_id=batch,
            train_batch_ids=(1, 2),
            val_batch_ids=(3,),
            pred_valid_row_count=4,
        )
        for batch in (8, 9, 10, 11)
    ]

    eligible = filter_ema_prediction_windows(
        windows,
        _ema_regime_inventory(),
        side="up",
        min_rate=0.8,
    )

    assert [window.pred_batch_id for window in eligible] == [9, 11]


def test_signal_bank_windows_use_only_mature_clean_batches() -> None:
    inventory = _signal_bank_inventory()
    base = RPFWindow(
        step_idx=0,
        pred_pos=20,
        pred_batch_id=20,
        train_batch_ids=tuple(range(1, 17)),
        val_batch_ids=(17, 18, 19),
        pred_valid_row_count=4,
    )

    windows, audit = build_signal_bank_windows(
        [base],
        inventory,
        gate_target=GATE_DOWN_DOMINANT,
        config=SignalBankConfig(
            mode=SIGNAL_BANK,
            positive_batch_min_rate=0.8,
            opposite_batch_max_rate=0.2,
            train_positive_batches=2,
            train_negative_batches=2,
            val_positive_batches=1,
            val_negative_batches=1,
            candidate_lookback_batches=20,
            label_maturity_embargo_batches=1,
        ),
    )

    assert windows[0].pred_batch_id == 20
    assert set(windows[0].train_batch_ids) == {10, 12, 9, 11}
    assert set(windows[0].val_batch_ids) == {14, 13}
    assert max(windows[0].train_batch_ids) <= 18
    assert max(windows[0].val_batch_ids) <= 18
    assert audit[0]["mature_cutoff_batch_id"] == 18
    assert audit[0]["bank_train_positive_count"] == 2
    assert audit[0]["bank_train_negative_count"] == 2


def test_hybrid_signal_bank_adds_recent_mature_batches() -> None:
    inventory = _signal_bank_inventory()
    base = RPFWindow(
        step_idx=0,
        pred_pos=20,
        pred_batch_id=20,
        train_batch_ids=tuple(range(1, 17)),
        val_batch_ids=(17, 18, 19),
        pred_valid_row_count=4,
    )

    windows, audit = build_signal_bank_windows(
        [base],
        inventory,
        gate_target=GATE_DOWN_DOMINANT,
        config=SignalBankConfig(
            mode=HYBRID_RECENT_SIGNAL_BANK,
            positive_batch_min_rate=0.8,
            opposite_batch_max_rate=0.2,
            train_positive_batches=1,
            train_negative_batches=1,
            val_positive_batches=1,
            val_negative_batches=1,
            candidate_lookback_batches=20,
            label_maturity_embargo_batches=1,
            recent_train_batches=2,
            recent_val_batches=2,
        ),
    )

    assert 15 in windows[0].train_batch_ids
    assert 16 in windows[0].train_batch_ids
    assert 17 in windows[0].val_batch_ids
    assert 18 in windows[0].val_batch_ids
    assert 19 not in windows[0].val_batch_ids
    assert audit[0]["max_train_label_window_batch_id"] <= 18
    assert audit[0]["max_val_label_window_batch_id"] <= 18


def test_classifier_outcome_inventory_splits_trust_and_reject_batches(
    tmp_path: Path,
) -> None:
    score_path = tmp_path / "prediction_scores.parquet"
    pl.DataFrame(
        {
            "trial_number": [1] * 8,
            "timestamp": [_ts(1, idx) for idx in range(4)]
            + [_ts(2, idx) for idx in range(4)],
            "batch_id": [1] * 4 + [2] * 4,
            "pred_batch_id": [1] * 4 + [2] * 4,
            "target": [1, 1, 0, 0, 0, 0, 0, 1],
            "prob": [0.9, 0.8, 0.1, 0.2, 0.9, 0.8, 0.7, 0.1],
            "predicted_positive": [1, 1, 0, 0, 1, 1, 1, 0],
        }
    ).write_parquet(score_path)

    inventory = build_classifier_outcome_inventory(
        score_path, classifier_trial_number=1, classifier_threshold=0.5
    )
    rows = {int(row["batch_id"]): row for row in inventory.to_dicts()}

    assert rows[1]["classifier_active_rows"] == 2
    assert rows[1]["trust_tp_rows"] == 2
    assert rows[1]["reject_fp_rows"] == 0
    assert rows[1]["trust_precision_among_active"] == pytest.approx(1.0)
    assert rows[2]["classifier_active_rows"] == 3
    assert rows[2]["trust_tp_rows"] == 0
    assert rows[2]["reject_fp_rows"] == 3
    assert rows[2]["reject_fp_rate_among_active"] == pytest.approx(1.0)


def test_separate_bank_plan_keeps_target_and_gate_banks_causal() -> None:
    target_inventory = _signal_bank_inventory()
    gate_inventory = pl.DataFrame(
        [
            {
                "batch_id": 9,
                "rows": 4,
                "batch_start_ts": _ts(9, 0),
                "batch_end_ts": _ts(9, 3),
                "score_pred_batch_id_min": 9,
                "score_pred_batch_id_max": 9,
                "classifier_active_rows": 4,
                "trust_tp_rows": 4,
                "reject_fp_rows": 0,
                "missed_fn_rows": 0,
                "safe_tn_rows": 0,
                "classifier_target_positive_rate": 1.0,
                "classifier_prob_mean": 0.9,
                "classifier_prob_q80": 0.9,
                "classifier_active_rate": 1.0,
                "trust_precision_among_active": 1.0,
                "reject_fp_rate_among_active": 0.0,
                "missed_fn_rate_all": 0.0,
            },
            {
                "batch_id": 10,
                "rows": 4,
                "batch_start_ts": _ts(10, 0),
                "batch_end_ts": _ts(10, 3),
                "score_pred_batch_id_min": 10,
                "score_pred_batch_id_max": 10,
                "classifier_active_rows": 4,
                "trust_tp_rows": 0,
                "reject_fp_rows": 4,
                "missed_fn_rows": 0,
                "safe_tn_rows": 0,
                "classifier_target_positive_rate": 0.0,
                "classifier_prob_mean": 0.9,
                "classifier_prob_q80": 0.9,
                "classifier_active_rate": 1.0,
                "trust_precision_among_active": 0.0,
                "reject_fp_rate_among_active": 1.0,
                "missed_fn_rate_all": 0.0,
            },
            {
                "batch_id": 19,
                "rows": 4,
                "batch_start_ts": _ts(19, 0),
                "batch_end_ts": _ts(19, 3),
                "score_pred_batch_id_min": 19,
                "score_pred_batch_id_max": 19,
                "classifier_active_rows": 4,
                "trust_tp_rows": 4,
                "reject_fp_rows": 0,
                "missed_fn_rows": 0,
                "safe_tn_rows": 0,
                "classifier_target_positive_rate": 1.0,
                "classifier_prob_mean": 0.9,
                "classifier_prob_q80": 0.9,
                "classifier_active_rate": 1.0,
                "trust_precision_among_active": 1.0,
                "reject_fp_rate_among_active": 0.0,
                "missed_fn_rate_all": 0.0,
            },
        ],
        infer_schema_length=None,
    )
    base = RPFWindow(
        step_idx=0,
        pred_pos=20,
        pred_batch_id=20,
        train_batch_ids=tuple(range(1, 17)),
        val_batch_ids=(17, 18, 19),
        pred_valid_row_count=4,
    )

    plan = build_separate_bank_plan(
        [base],
        target_inventory=target_inventory,
        gate_inventory=gate_inventory,
        side=SIDE_DOWN,
        config=SeparateBankConfig(
            target_train_positive_batches=1,
            target_train_negative_batches=1,
            target_val_positive_batches=1,
            target_val_negative_batches=1,
            gate_train_trust_batches=1,
            gate_train_reject_batches=1,
            gate_val_trust_batches=0,
            gate_val_reject_batches=0,
            gate_min_active_rows=1,
            candidate_lookback_batches=20,
            label_maturity_embargo_batches=1,
        ),
    )
    row = plan.row(0, named=True)

    assert row["mature_cutoff_batch_id"] == 18
    assert 19 not in row["gate_train_batch_ids"]
    assert set(row["gate_train_batch_ids"]) == {9, 10}
    assert row["gate_train_maturity_violation"] is False
    assert row["target_train_maturity_violation"] is False
    assert summarize_separate_bank_plan(plan)["any_maturity_violations"] is False


def test_binary_classification_metrics_are_computed() -> None:
    metrics = binary_metrics(np.array([0, 0, 1, 1]), np.array([0.1, 0.4, 0.7, 0.9]))

    assert metrics["accuracy"] == 1.0
    assert metrics["balanced_accuracy"] == 1.0
    assert metrics["auc"] == 1.0
    assert metrics["logloss"] < 0.4


def test_binary_metrics_include_cost_and_threshold() -> None:
    metrics = binary_metrics(
        np.array([0, 0, 1, 1]),
        np.array([0.2, 0.8, 0.4, 0.9]),
        threshold=0.5,
        fp_cost=5.0,
        fn_cost=1.0,
    )

    assert metrics["tp"] == 1
    assert metrics["fp"] == 1
    assert metrics["fn"] == 1
    assert metrics["false_positive_rate"] == pytest.approx(0.5)
    assert metrics["false_negative_rate"] == pytest.approx(0.5)
    assert metrics["decision_cost"] == pytest.approx(6.0)
    assert metrics["decision_cost_per_row"] == pytest.approx(1.5)
    assert metrics["signal_count"] == 2
    assert metrics["precision_lift"] == pytest.approx(1.0)
    assert metrics["mcc"] == pytest.approx(0.0)
    assert metrics["pr_auc"] == pytest.approx(
        pr_auc_average_precision(np.array([0, 0, 1, 1]), np.array([0.2, 0.8, 0.4, 0.9]))
    )


def test_binary_target_aliases_match_canonical_rules() -> None:
    frame = pl.DataFrame(
        {
            "target_reg_distance_up_extreme_hvol_v2": [2.0, 1.0, 0.0],
            "target_reg_distance_down_extreme_hvol_v2": [1.0, 3.0, 2.0],
        }
    )

    out = frame.with_columns(
        [
            binary_target_expr(TARGET_BINARY_UP_2X_DOWN),
            binary_target_expr(TARGET_BINARY_UP_2X_DOWN_ALIAS),
            binary_target_expr(TARGET_BINARY_DOWN_2X_UP),
            binary_target_expr(TARGET_BINARY_DOWN_2X_UP_ALIAS),
        ]
    )

    assert (
        canonical_binary_target_col(TARGET_BINARY_UP_2X_DOWN_ALIAS)
        == TARGET_BINARY_UP_2X_DOWN
    )
    assert (
        canonical_binary_target_col(TARGET_BINARY_DOWN_2X_UP_ALIAS)
        == TARGET_BINARY_DOWN_2X_UP
    )
    assert (
        out[TARGET_BINARY_UP_2X_DOWN].to_list()
        == out[TARGET_BINARY_UP_2X_DOWN_ALIAS].to_list()
    )
    assert (
        out[TARGET_BINARY_DOWN_2X_UP].to_list()
        == out[TARGET_BINARY_DOWN_2X_UP_ALIAS].to_list()
    )


def test_pr_auc_mcc_and_precision_lift_for_clean_ranking() -> None:
    y = np.array([1, 0, 1, 0])
    prob = np.array([0.9, 0.8, 0.7, 0.1])
    metrics = binary_metrics(y, prob, threshold=0.75)

    assert metrics["positive_rate"] == pytest.approx(0.5)
    assert metrics["precision"] == pytest.approx(0.5)
    assert metrics["precision_lift"] == pytest.approx(1.0)
    assert matthews_corrcoef(tp=1, tn=1, fp=1, fn=1) == pytest.approx(0.0)
    assert pr_auc_average_precision(y, prob) == pytest.approx((1.0 + 2.0 / 3.0) / 2.0)


def test_validation_threshold_sweep_selects_low_cost_threshold() -> None:
    result = select_decision_threshold(
        np.array([0, 0, 1, 1]),
        np.array([0.2, 0.8, 0.4, 0.9]),
        threshold_mode="validation_sweep",
        fixed_threshold=0.5,
        threshold_grid=(0.3, 0.5, 0.85),
        objective_metric="validation_decision_cost",
        fp_cost=5.0,
        fn_cost=1.0,
        tp_reward=0.0,
        fbeta_beta=0.5,
        min_recall=0.0,
        min_precision=0.0,
        min_predicted_positive_rate=0.0,
        max_false_positive_rate=1.0,
    )

    assert result["threshold"] == pytest.approx(0.85)
    assert result["metrics"]["fp"] == 0
    assert result["metrics"]["fn"] == 1
    assert result["metrics"]["decision_cost"] == pytest.approx(1.0)


def test_signal_predictions_supports_live_safe_and_offline_decision_policies() -> None:
    prob = np.array([0.9, 0.8, 0.7, 0.1])

    assert signal_predictions(prob, threshold=0.5, max_signals=0).tolist() == [
        1,
        1,
        1,
        0,
    ]
    assert signal_predictions(
        prob,
        threshold=0.5,
        max_signals=2,
        decision_policy=DECISION_POLICY_THRESHOLD_ONLY,
    ).tolist() == [1, 1, 1, 0]
    assert signal_predictions(
        np.array([0.6, 0.9, 0.8, 0.1]),
        threshold=0.5,
        max_signals=2,
        decision_policy=DECISION_POLICY_CAUSAL_SIGNAL_BUDGET,
    ).tolist() == [1, 1, 0, 0]
    assert signal_predictions(
        np.array([0.6, 0.9, 0.8, 0.1]),
        threshold=0.5,
        max_signals=2,
        decision_policy=DECISION_POLICY_BATCH_TOPK_OFFLINE,
    ).tolist() == [0, 1, 1, 0]
    assert normalize_max_signals_grid((20, 0, 5, 5, -1)) == (0, 5, 20)


def test_validation_threshold_sweep_selects_signal_cap_when_it_reduces_cost() -> None:
    result = select_decision_threshold(
        np.array([1, 1, 0, 0, 0]),
        np.array([0.9, 0.8, 0.7, 0.6, 0.55]),
        threshold_mode="validation_sweep",
        fixed_threshold=0.5,
        threshold_grid=(0.5,),
        max_signals_grid=(0, 2),
        decision_policy=DECISION_POLICY_BATCH_TOPK_OFFLINE,
        objective_metric="validation_decision_cost",
        fp_cost=5.0,
        fn_cost=1.0,
        tp_reward=0.0,
        fbeta_beta=0.5,
        min_recall=0.0,
        min_precision=0.0,
        min_predicted_positive_rate=0.0,
        max_false_positive_rate=1.0,
    )

    assert result["threshold"] == pytest.approx(0.5)
    assert result["max_signals"] == 2
    assert result["decision_policy"] == DECISION_POLICY_BATCH_TOPK_OFFLINE
    assert result["decision_policy_live_safe"] is False
    assert result["metrics"]["tp"] == 2
    assert result["metrics"]["fp"] == 0
    assert result["metrics"]["decision_cost"] == pytest.approx(0.0)


def test_threshold_only_policy_does_not_use_batch_signal_caps() -> None:
    result = select_decision_threshold(
        np.array([1, 1, 0, 0, 0]),
        np.array([0.9, 0.8, 0.7, 0.6, 0.55]),
        threshold_mode="validation_sweep",
        fixed_threshold=0.5,
        threshold_grid=(0.5,),
        max_signals_grid=(0, 2),
        decision_policy=DECISION_POLICY_THRESHOLD_ONLY,
        objective_metric="validation_decision_cost",
        fp_cost=5.0,
        fn_cost=1.0,
        tp_reward=0.0,
        fbeta_beta=0.5,
        min_recall=0.0,
        min_precision=0.0,
        min_predicted_positive_rate=0.0,
        max_false_positive_rate=1.0,
    )

    assert result["max_signals"] == 0
    assert result["decision_policy"] == DECISION_POLICY_THRESHOLD_ONLY
    assert result["decision_policy_live_safe"] is True
    assert result["metrics"]["tp"] == 2
    assert result["metrics"]["fp"] == 3


def test_cli_signal_cap_validation_rejects_threshold_only_caps() -> None:
    with pytest.raises(ValueError, match="threshold_only ignores caps"):
        validate_decision_policy_signal_grid(DECISION_POLICY_THRESHOLD_ONLY, (0, 5, 10))

    assert validate_decision_policy_signal_grid(
        DECISION_POLICY_THRESHOLD_ONLY, (0,)
    ) == (0,)
    assert validate_decision_policy_signal_grid(
        DECISION_POLICY_CAUSAL_SIGNAL_BUDGET, (10, 0, 5)
    ) == (
        0,
        5,
        10,
    )


def test_stable_prediction_quality_threshold_sweep_uses_stable_score() -> None:
    result = select_decision_threshold(
        np.array([1, 1, 1, 1, 0, 0, 0, 0]),
        np.array([0.9, 0.8, 0.55, 0.45, 0.7, 0.6, 0.4, 0.3]),
        threshold_mode="validation_sweep",
        fixed_threshold=0.5,
        threshold_grid=(0.4, 0.5, 0.75),
        max_signals_grid=(0,),
        objective_metric="stable_prediction_quality",
        fp_cost=5.0,
        fn_cost=1.0,
        tp_reward=0.0,
        fbeta_beta=0.5,
        min_recall=0.0,
        min_precision=0.0,
        min_predicted_positive_rate=0.0,
        max_false_positive_rate=1.0,
    )

    assert result["objective_direction"] == "maximize"
    assert result["objective_value"] == pytest.approx(
        stable_prediction_quality_score(result["metrics"], {})["score"]
    )


def test_classification_objective_supports_minimize_and_maximize() -> None:
    metrics = {
        "logloss": 0.4,
        "decision_cost_per_row": 0.2,
        "precision": 0.8,
        "precision_lift": 1.4,
        "pr_auc": 0.7,
        "mcc": 0.2,
    }

    assert classification_objective(metrics, "validation_logloss") == ("minimize", 0.4)
    assert classification_objective(metrics, "validation_decision_cost") == (
        "minimize",
        0.2,
    )
    assert classification_objective(metrics, "validation_precision") == (
        "maximize",
        0.8,
    )
    assert classification_objective(metrics, "validation_precision_lift") == (
        "maximize",
        1.4,
    )
    assert classification_objective(metrics, "validation_pr_auc") == ("maximize", 0.7)
    assert classification_objective(metrics, "validation_mcc") == ("maximize", 0.2)
    assert (
        classification_objective(metrics, "stable_prediction_quality")[0] == "maximize"
    )
    assert classification_objective(metrics, "stable_signal_quality")[0] == "maximize"


def test_stable_prediction_quality_rewards_signal_and_penalizes_collapse() -> None:
    good_metrics = {
        "rows": 100,
        "positive_rate": 0.20,
        "predicted_positive_rate": 0.12,
        "pr_auc": 0.40,
        "precision_lift": 1.8,
        "fbeta": 0.35,
        "mcc": 0.20,
        "brier": 0.18,
        "decision_cost_per_row": 0.30,
    }
    collapsed_metrics = {
        **good_metrics,
        "predicted_positive_rate": 0.0,
        "precision_lift": 0.0,
        "fbeta": 0.0,
        "mcc": 0.0,
        "decision_cost_per_row": 0.75,
    }
    stable = {
        "zero_positive_window_rate": 0.0,
        "all_positive_window_rate": 0.0,
        "high_fpr_window_rate": 0.0,
        "high_cost_window_rate": 0.0,
    }
    collapsed = {
        "zero_positive_window_rate": 1.0,
        "all_positive_window_rate": 0.0,
        "high_fpr_window_rate": 0.0,
        "high_cost_window_rate": 0.5,
    }

    good = stable_prediction_quality_score(
        good_metrics, stable, threshold_pass_rate=1.0, selected_feature_count_mean=80
    )
    bad = stable_prediction_quality_score(
        collapsed_metrics,
        collapsed,
        threshold_pass_rate=0.5,
        selected_feature_count_mean=320,
    )

    assert good["score"] > bad["score"]
    assert bad["zero_positive_window_rate"] == 1.0
    assert bad["penalty"] > good["penalty"]


def test_stable_signal_quality_rewards_precision_and_repeated_windows() -> None:
    precise_metrics = {
        "rows": 1000,
        "positive_rate": 0.25,
        "predicted_positive_rate": 0.05,
        "precision": 0.85,
        "precision_lift": 3.4,
        "false_positive_rate": 0.01,
        "false_discovery_rate": 0.15,
        "recall": 0.17,
        "mcc": 0.20,
        "decision_cost_per_row": 0.20,
    }
    noisy_metrics = {
        **precise_metrics,
        "predicted_positive_rate": 0.35,
        "precision": 0.35,
        "precision_lift": 1.4,
        "false_positive_rate": 0.22,
        "false_discovery_rate": 0.65,
        "recall": 0.60,
        "mcc": 0.05,
        "decision_cost_per_row": 0.75,
    }
    repeated = {
        "active_signal_window_rate": 0.30,
        "repeated_active_signal_window_rate": 0.25,
        "signal_churn_rate": 0.20,
        "active_signal_window_precision_mean": 0.86,
        "repeated_active_signal_window_precision_mean": 0.88,
        "high_fpr_window_rate": 0.0,
        "high_cost_window_rate": 0.0,
        "all_positive_window_rate": 0.0,
        "low_target_all_positive_window_rate": 0.0,
    }
    noisy = {
        **repeated,
        "active_signal_window_rate": 0.90,
        "repeated_active_signal_window_rate": 0.10,
        "signal_churn_rate": 0.80,
        "active_signal_window_precision_mean": 0.35,
        "repeated_active_signal_window_precision_mean": 0.35,
        "high_fpr_window_rate": 0.40,
        "high_cost_window_rate": 0.30,
    }

    precise = stable_signal_quality_score(
        precise_metrics,
        repeated,
        threshold_pass_rate=1.0,
        selected_feature_count_mean=80,
    )
    noisy_score = stable_signal_quality_score(
        noisy_metrics,
        noisy,
        threshold_pass_rate=1.0,
        selected_feature_count_mean=80,
    )

    assert precise["score"] > noisy_score["score"]
    assert precise["precision_lift_gain"] > noisy_score["precision_lift_gain"]
    assert noisy_score["stability_penalty"] > precise["stability_penalty"]


def test_stable_prediction_quality_is_not_flattened_by_rejection_gates() -> None:
    assert should_force_bad_objective(
        objective_metric="validation_decision_cost",
        threshold_constraints_pass=False,
        prediction_window_stability_pass=True,
    )
    assert should_force_bad_objective(
        objective_metric="validation_decision_cost",
        threshold_constraints_pass=True,
        prediction_window_stability_pass=False,
    )
    assert not should_force_bad_objective(
        objective_metric="stable_prediction_quality",
        threshold_constraints_pass=False,
        prediction_window_stability_pass=False,
    )
    assert not should_force_bad_objective(
        objective_metric="stable_signal_quality",
        threshold_constraints_pass=False,
        prediction_window_stability_pass=False,
    )


def test_prediction_window_stability_counts_collapse_modes() -> None:
    windows = [
        {
            "window_status": "ok",
            "prediction_positive_rate": 0.10,
            "prediction_predicted_positive_rate": 0.0,
            "prediction_recall": 0.0,
            "prediction_false_positive_rate": 0.0,
            "prediction_decision_cost_per_row": 0.2,
        },
        {
            "window_status": "ok",
            "prediction_positive_rate": 0.10,
            "prediction_predicted_positive_rate": 1.0,
            "prediction_recall": 1.0,
            "prediction_false_positive_rate": 1.0,
            "prediction_decision_cost_per_row": 5.0,
        },
        {
            "window_status": "ok",
            "prediction_positive_rate": 0.40,
            "prediction_predicted_positive_rate": 0.2,
            "prediction_recall": 0.5,
            "prediction_false_positive_rate": 0.1,
            "prediction_decision_cost_per_row": 0.4,
        },
        {
            "window_status": "skipped",
            "prediction_positive_rate": 1.0,
            "prediction_predicted_positive_rate": 1.0,
            "prediction_recall": 1.0,
            "prediction_false_positive_rate": 1.0,
            "prediction_decision_cost_per_row": 5.0,
        },
    ]

    stability = window_stability_metrics(
        windows,
        split="prediction",
        all_positive_rate_threshold=0.95,
        high_false_positive_rate_threshold=0.5,
        high_decision_cost_per_row_threshold=1.0,
    )

    assert stability["window_count"] == 3
    assert stability["zero_positive_window_count"] == 1
    assert stability["zero_positive_window_rate"] == pytest.approx(1 / 3)
    assert stability["all_positive_window_count"] == 1
    assert stability["all_positive_window_rate"] == pytest.approx(1 / 3)
    assert stability["high_fpr_window_count"] == 1
    assert stability["high_cost_window_count"] == 1
    assert stability["predicted_positive_rate_max"] == pytest.approx(1.0)
    assert stability["active_signal_window_count"] == 2
    assert stability["active_signal_window_rate"] == pytest.approx(2 / 3)
    assert stability["active_signal_run_length_max"] == 2
    assert stability["repeated_active_signal_window_count"] == 2
    assert stability["signal_churn_count"] == 1

    assert (
        window_stability_constraints_reason(
            stability,
            max_zero_positive_window_rate=0.25,
            max_all_positive_window_rate=1.0,
            max_high_fpr_window_rate=1.0,
            max_high_cost_window_rate=1.0,
        )
        == "too_many_zero_positive_windows"
    )
    assert (
        window_stability_constraints_reason(
            stability,
            max_zero_positive_window_rate=1.0,
            max_all_positive_window_rate=0.25,
            max_high_fpr_window_rate=1.0,
            max_high_cost_window_rate=1.0,
        )
        == "too_many_all_positive_windows"
    )


def test_prediction_window_stability_counts_target_aware_failures() -> None:
    windows = [
        {
            "window_status": "ok",
            "prediction_positive_rate": 0.90,
            "prediction_predicted_positive_rate": 0.0,
            "prediction_recall": 0.0,
            "prediction_false_positive_rate": 0.0,
            "prediction_decision_cost_per_row": 0.9,
        },
        {
            "window_status": "ok",
            "prediction_positive_rate": 0.80,
            "prediction_predicted_positive_rate": 0.20,
            "prediction_recall": 0.10,
            "prediction_false_positive_rate": 0.0,
            "prediction_decision_cost_per_row": 0.6,
        },
        {
            "window_status": "ok",
            "prediction_positive_rate": 0.20,
            "prediction_predicted_positive_rate": 1.0,
            "prediction_recall": 1.0,
            "prediction_false_positive_rate": 1.0,
            "prediction_decision_cost_per_row": 4.0,
        },
    ]

    stability = window_stability_metrics(
        windows,
        split="prediction",
        all_positive_rate_threshold=0.95,
        high_false_positive_rate_threshold=0.5,
        high_decision_cost_per_row_threshold=1.0,
        high_target_positive_rate_threshold=0.70,
        min_high_target_window_recall=0.05,
        min_high_target_window_signal_rate=0.01,
        low_target_positive_rate_threshold=0.35,
    )

    assert stability["high_target_window_count"] == 2
    assert stability["missed_high_target_window_count"] == 1
    assert stability["missed_high_target_window_rate"] == pytest.approx(0.5)
    assert stability["low_target_window_count"] == 1
    assert stability["low_target_all_positive_window_count"] == 1
    assert stability["low_target_all_positive_window_rate"] == pytest.approx(1.0)
    assert (
        window_stability_constraints_reason(
            stability,
            max_zero_positive_window_rate=1.0,
            max_all_positive_window_rate=1.0,
            max_high_fpr_window_rate=1.0,
            max_high_cost_window_rate=1.0,
            max_missed_high_target_window_rate=0.25,
            max_low_target_all_positive_window_rate=1.0,
        )
        == "too_many_missed_high_target_windows"
    )
    assert (
        window_stability_constraints_reason(
            stability,
            max_zero_positive_window_rate=1.0,
            max_all_positive_window_rate=1.0,
            max_high_fpr_window_rate=1.0,
            max_high_cost_window_rate=1.0,
            max_missed_high_target_window_rate=1.0,
            max_low_target_all_positive_window_rate=0.25,
        )
        == "too_many_low_target_all_positive_windows"
    )


def test_optuna_objective_prefers_lower_validation_rmse() -> None:
    better = objective_score({"rmse": 0.10, "spearman": -0.5})
    worse = objective_score({"rmse": 0.20, "spearman": 0.9})

    assert better < worse
    assert objective_score({"rmse": None}) == 1e9


def test_baseline_rmse_formula_matches_direct_numpy() -> None:
    y = np.array([0.0, 0.5, 1.0])

    expected = float(np.sqrt(np.mean((y - 0.5) ** 2)))

    assert optimize_module._rmse_against_constant(y, 0.5) == pytest.approx(expected)
    assert optimize_module._rmse_against_constant(y, None) is None


def test_window_collapse_summary_and_gate() -> None:
    rows = [
        {
            "prediction_window_collapsed": True,
            "prediction_pred_unique": 1,
            "prediction_pred_std": 0.0,
            "prediction_to_target_std_ratio_window": 0.0,
        },
        {
            "prediction_window_collapsed": False,
            "prediction_pred_unique": 20,
            "prediction_pred_std": 0.2,
            "prediction_to_target_std_ratio_window": 0.5,
        },
    ]

    summary = optimize_module._aggregate_collapse_metrics(
        rows,
        {"pred_std": 0.05, "target_std": 1.0, "pred_mean": 0.4, "target_mean": 0.6},
    )

    assert summary["collapsed_window_count"] == 1
    assert summary["collapsed_window_rate"] == 0.5
    assert summary["prediction_pred_unique_min"] == 1
    assert summary["prediction_mean_bias"] == pytest.approx(-0.2)
    assert (
        optimize_module.window_collapse_reason(
            summary,
            max_collapsed_window_rate=0.25,
            min_prediction_to_target_std_ratio=0.10,
        )
        == "high_collapsed_window_rate"
    )


def test_feature_family_ablation_masks_manifest_features() -> None:
    features = ("rpf_vol_a", "rpf_room_a", "rpf_accept_a")

    assert select_ablation_features(features, "all") == features
    assert select_ablation_features(features, "only_volatility_state") == ("rpf_vol_a",)
    assert select_ablation_features(
        features, "group_volatility_state+structural_room"
    ) == ("rpf_vol_a", "rpf_room_a")
    assert select_ablation_features(features, "minus_volatility_state") == (
        "rpf_room_a",
        "rpf_accept_a",
    )


def test_catboost_param_builder_rejects_invalid_sampling_combo() -> None:
    with pytest.raises(ValueError, match="bagging_temperature"):
        build_catboost_params(
            CatBoostConfig(bootstrap_type="Bernoulli", bagging_temperature=1.0),
            task_type="CPU",
        )


def test_stage_config_keeps_locked_window_for_core_model() -> None:
    optuna = pytest.importorskip("optuna")
    base = CleanWalkForwardConfig(lookback_batches=222, val_batches=11)
    trial = optuna.trial.FixedTrial(
        {
            "iterations": 100,
            "depth": 3,
            "learning_rate": 0.03,
            "l2_leaf_reg": 10.0,
            "early_stopping_rounds": 20,
            "od_wait": 20,
        }
    )
    args = SimpleNamespace(
        iterations_choices="100",
        depth_choices="3",
        learning_rate_choices="0.03",
        l2_leaf_reg_choices="10",
        early_stopping_rounds_choices="20",
        od_wait_choices="20",
    )

    out = suggest_stage_config(trial, "core_model", base, args)

    assert out.lookback_batches == 222
    assert out.val_batches == 11
    assert out.model.iterations == 100


def test_finite_categorical_stages_use_grid_sampler() -> None:
    optuna = pytest.importorskip("optuna")
    args = SimpleNamespace(
        seed=42,
        lookback_choices="80,120",
        val_choices="8,10",
        embargo_choices="0",
        iterations_choices="400",
        depth_choices="4",
        learning_rate_choices="0.01",
        l2_leaf_reg_choices="100",
        early_stopping_rounds_choices="100",
        od_wait_choices="100",
    )

    assert (
        type(optimize_module._sampler_for_stage(optuna, "geometry", args)).__name__
        == "GridSampler"
    )
    assert (
        type(
            optimize_module._sampler_for_stage(optuna, "baseline_probe", args)
        ).__name__
        == "GridSampler"
    )
    assert (
        type(optimize_module._sampler_for_stage(optuna, "core_model", args)).__name__
        == "GridSampler"
    )
    assert (
        type(optimize_module._sampler_for_stage(optuna, "confirmation", args)).__name__
        == "TPESampler"
    )


def test_trial_config_columns_are_flat_for_audit() -> None:
    config = merge_config(
        CleanWalkForwardConfig(),
        lookback_batches=180,
        val_batches=12,
        feature_ablation="all",
        model={
            "iterations": 800,
            "depth": 4,
            "learning_rate": 0.01,
            "l2_leaf_reg": 200,
        },
    )

    row = optimize_module._trial_config_columns(config)

    assert row["feature_count_mode"] == "all"
    assert row["max_collapsed_window_rate"] == 0.25
    assert row["min_prediction_to_target_std_ratio"] == 0.10
    assert row["lookback_batches"] == 180
    assert row["val_batches"] == 12
    assert row["iterations"] == 800
    assert row["learning_rate"] == 0.01
    assert row["l2_leaf_reg"] == 200.0


def test_clean_rpf_stages_do_not_tune_feature_policy() -> None:
    assert "feature_policy" not in STAGES
    assert "geometry" in STAGES
    assert "core_model" in STAGES
    assert "sampling" in STAGES


def test_stale_base_run_feature_policy_is_overridden_by_current_config() -> None:
    stale = merge_config(
        CleanWalkForwardConfig(),
        lookback_batches=222,
        feature_policy=TARGET_SPECIFIC_V2,
        policy={"policy": TARGET_SPECIFIC_V2, "max_features": 300},
        model={"depth": 5},
    )
    current = merge_config(
        CleanWalkForwardConfig(),
        feature_policy=ALL_MANIFEST_FEATURES,
        policy={"policy": ALL_MANIFEST_FEATURES, "max_features": 0},
    )

    out = optimize_module._apply_current_fixed_contract(stale, current)

    assert out.feature_policy == ALL_MANIFEST_FEATURES
    assert out.policy.policy == ALL_MANIFEST_FEATURES
    assert out.policy.max_features == 0
    assert out.lookback_batches == 222
    assert out.model.depth == 5


def test_readiness_stage_writes_expected_artifacts(tmp_path: Path) -> None:
    _write_fixture(tmp_path)
    context = resolve_context(
        project_root=tmp_path, asset="BTCUSDT", root="8h/B", target_col=TARGET
    )
    config = merge_config(CleanWalkForwardConfig(), policy={"min_selected_features": 1})
    run_root = tmp_path / "out"
    args = SimpleNamespace(
        lookback_batches=2, val_batches=1, embargo_batches=0, n_steps=1
    )

    run_readiness(context, config, run_root, run_root / "events.jsonl", args)

    assert (run_root / "readiness.json").exists()
    assert (run_root / "frozen_windows.parquet").exists()
    assert (run_root / "stage_status.json").exists()
    assert (run_root / "trials.parquet").exists()
    assert (run_root / "best_config.json").exists()
    assert (run_root / "label_window_index.parquet").exists()
    assert (run_root / "window_metrics.parquet").exists()
    readiness = json.loads((run_root / "readiness.json").read_text())
    assert readiness["feature_integrity"]["family_counts"]["unmapped"] == 2
    assert "zero_rate" in readiness["target_summary"]
    window_metrics = pl.read_parquet(run_root / "window_metrics.parquet")
    assert "target_mean_drift_pred_minus_train" in window_metrics.columns


def test_readiness_detects_label_window_overlap(tmp_path: Path) -> None:
    _write_fixture(tmp_path, batches=5, rows=4, label_overlap=True)
    context = resolve_context(
        project_root=tmp_path, asset="BTCUSDT", root="8h/B", target_col=TARGET
    )
    config = merge_config(CleanWalkForwardConfig(), policy={"min_selected_features": 1})
    args = SimpleNamespace(
        lookback_batches=2, val_batches=1, embargo_batches=0, n_steps=1
    )

    with pytest.raises(ValueError, match="label-window safety failed"):
        run_readiness(
            context, config, tmp_path / "out", tmp_path / "out" / "events.jsonl", args
        )


def test_label_window_safety_passes_self_contained_windows(tmp_path: Path) -> None:
    _write_fixture(tmp_path, batches=5, rows=4)
    context = resolve_context(
        project_root=tmp_path, asset="BTCUSDT", root="8h/B", target_col=TARGET
    )
    windows = build_windows(
        build_batch_index(context), lookback_batches=2, val_batches=1, n_steps=1
    )
    summary, rows = optimize_module._label_window_safety(
        windows, build_label_window_index(context), embargo_batches=0
    )

    assert summary["status"] == "pass"
    assert summary["violation_count"] == 0
    assert rows[0]["label_window_violation"] is False


def test_baseline_probe_stage_writes_artifacts_without_stage1_merged_root(
    tmp_path: Path,
) -> None:
    pytest.importorskip("optuna")
    pytest.importorskip("catboost")
    _write_fixture(tmp_path, batches=5, rows=4)
    context = resolve_context(
        project_root=tmp_path, asset="BTCUSDT", root="8h/B", target_col=TARGET
    )
    config = merge_config(
        CleanWalkForwardConfig(min_prediction_unique=0),
        lookback_batches=2,
        val_batches=1,
        n_steps=1,
        policy={
            "policy": TARGET_SPECIFIC_V2,
            "max_features": 1,
            "min_selected_features": 1,
            "min_abs_spearman": 0.01,
        },
        model={"iterations": 5, "depth": 2, "early_stopping_rounds": 2, "od_wait": 2},
    )
    base_run = tmp_path / "readiness"
    args_ready = SimpleNamespace(
        lookback_batches=2, val_batches=1, embargo_batches=0, n_steps=1
    )
    run_readiness(context, config, base_run, base_run / "events.jsonl", args_ready)
    args = SimpleNamespace(
        stage="baseline_probe",
        base_run=base_run,
        n_steps=1,
        n_trials=1,
        timeout=None,
        seed=42,
        task_type="CPU",
        thread_count=-1,
        iterations_choices="5",
        depth_choices="2",
        learning_rate_choices="0.03",
        l2_leaf_reg_choices="10",
        early_stopping_rounds_choices="2",
        od_wait_choices="2",
    )
    run_root = tmp_path / "baseline"

    run_optuna_stage(context, config, run_root, run_root / "events.jsonl", args)

    assert (run_root / "frozen_windows.parquet").exists()
    assert (run_root / "trials.parquet").exists()
    assert (run_root / "best_config.json").exists()
    assert (run_root / "stage_status.json").exists()
    assert (run_root / "window_metrics.parquet").exists()
    trials = pl.read_parquet(run_root / "trials.parquet")
    assert trials["objective_metric"].to_list() == ["validation_rmse"]
    assert trials["objective_direction"].to_list() == ["minimize"]
    for col in (
        "validation_baseline_train_target_mean_rmse",
        "prediction_baseline_train_target_mean_rmse",
        "collapsed_window_rate",
        "prediction_pred_unique_min",
        "ablation_feature_count",
    ):
        assert col in trials.columns
    windows = pl.read_parquet(run_root / "window_metrics.parquet")
    assert "prediction_baseline_constant_0p5_rmse" in windows.columns
    assert "prediction_window_collapsed" in windows.columns


def test_non_geometry_stage_reuses_frozen_windows_without_batch_index_scan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pytest.importorskip("optuna")
    _write_fixture(tmp_path, batches=5, rows=4)
    context = resolve_context(
        project_root=tmp_path, asset="BTCUSDT", root="8h/B", target_col=TARGET
    )
    config = merge_config(
        CleanWalkForwardConfig(min_prediction_unique=0),
        lookback_batches=2,
        val_batches=1,
        n_steps=1,
    )
    base_run = tmp_path / "readiness"
    args_ready = SimpleNamespace(
        lookback_batches=2, val_batches=1, embargo_batches=0, n_steps=1
    )
    run_readiness(context, config, base_run, base_run / "events.jsonl", args_ready)

    def explode_batch_index(*_args: object, **_kwargs: object) -> pl.DataFrame:
        raise AssertionError("non-geometry stages must not rebuild batch index")

    def fake_run_windows(*_args: object, **_kwargs: object) -> dict[str, object]:
        return {
            "validation_metrics": {
                "rows": 4,
                "spearman": 0.1,
                "pearson": 0.1,
                "r2": 0.0,
                "rmse": 0.2,
                "balanced_direction_accuracy_0p5": 0.5,
            },
            "prediction_metrics": {
                "rows": 4,
                "pred_unique": 11,
                "pred_std": 0.2,
                "spearman_null_reason": None,
            },
            "baseline_metrics": {
                "validation_baseline_train_target_mean_rmse": 0.2,
                "prediction_baseline_train_target_mean_rmse": 0.2,
            },
            "collapse_metrics": {
                "collapsed_window_rate": 0.0,
                "prediction_to_target_std_ratio": 0.5,
                "prediction_pred_unique_min": 11,
            },
            "selected_feature_count_min": 20,
            "window_metrics": [{"step_idx": 0, "prediction_rmse": 0.2}],
        }

    monkeypatch.setattr(optimize_module, "build_batch_index", explode_batch_index)
    monkeypatch.setattr(optimize_module, "run_windows", fake_run_windows)
    args = SimpleNamespace(
        stage="baseline_probe",
        base_run=base_run,
        n_steps=1,
        n_trials=1,
        timeout=None,
        seed=42,
        task_type="CPU",
        thread_count=-1,
        iterations_choices="5",
        depth_choices="2",
        learning_rate_choices="0.03",
        l2_leaf_reg_choices="10",
        early_stopping_rounds_choices="2",
        od_wait_choices="2",
    )

    run_optuna_stage(
        context,
        config,
        tmp_path / "baseline",
        tmp_path / "baseline" / "events.jsonl",
        args,
    )

    assert (tmp_path / "baseline" / "trials.parquet").exists()
    assert (tmp_path / "baseline" / "window_metrics.parquet").exists()
