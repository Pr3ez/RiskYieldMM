from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import polars as pl
import pytest

from regression_feature_engineering.walkforward.rank_signal_row_diagnostic import (
    RouterInput,
    build_row_rpf_context,
    load_signal_rows,
    safe_row_context_features,
)


def test_load_signal_rows_labels_tp_fp_from_candidate_scores(tmp_path: Path) -> None:
    run = tmp_path / "router"
    _write_router_config(run)
    pl.DataFrame(
        [
            _score_row("down", "down_rocket_16_diag_v1", 10, "2024-01-01T00:00:00+00:00", 1, 1),
            _score_row("down", "down_rocket_16_diag_v1", 10, "2024-01-01T00:01:00+00:00", 1, 0),
            _score_row("down", "down_rocket_16_diag_v1", 10, "2024-01-01T00:02:00+00:00", 0, 1),
        ],
        infer_schema_length=None,
    ).write_parquet(run / "candidate_prediction_scores.parquet")

    rows = load_signal_rows(
        [RouterInput(run, "latest")],
        side="down",
        candidate_names=("down_rocket_16_diag_v1",),
        score_source="candidate_prediction_scores",
    )

    assert rows.height == 2
    assert int(rows["signal_tp"].sum()) == 1
    assert int(rows["signal_fp"].sum()) == 1
    assert set(rows["signal_outcome"].to_list()) == {"tp", "fp"}


def test_safe_row_context_excludes_outcomes() -> None:
    frame = pl.DataFrame(
        [
            {
                "source_run": "run",
                "side": "down",
                "candidate_name": "c",
                "rank_score": 0.2,
                "target_binary": 1,
                "signal_tp": True,
                "signal_fp": False,
            }
        ]
    )

    safe = safe_row_context_features(frame)

    assert "rank_score" in safe.columns
    assert "target_binary" not in safe.columns
    assert "signal_tp" not in safe.columns
    assert "signal_fp" not in safe.columns


def test_row_rpf_context_joins_exact_timestamp_batch(tmp_path: Path) -> None:
    feature_root = tmp_path / "features"
    feature_root.mkdir()
    pl.DataFrame(
        [
            {
                "timestamp": "2024-01-01T00:00:00+00:00",
                "batch_id": 10,
                "rpf_vol_a": 1.0,
                "rpf_vol_b": -3.0,
                "rpf_room_a": 2.0,
            },
            {
                "timestamp": "2024-01-01T00:01:00+00:00",
                "batch_id": 10,
                "rpf_vol_a": 100.0,
                "rpf_vol_b": 100.0,
                "rpf_room_a": 100.0,
            },
        ]
    ).with_columns(pl.col("timestamp").str.to_datetime(time_zone="UTC")).write_parquet(feature_root / "batch_0010.parquet")
    context = SimpleNamespace(
        feature_root=feature_root,
        manifest=SimpleNamespace(feature_columns=("rpf_vol_a", "rpf_vol_b", "rpf_room_a")),
    )
    keys = pl.DataFrame(
        [{"timestamp": "2024-01-01T00:00:00+00:00", "batch_id": 10}]
    ).with_columns(pl.col("timestamp").str.to_datetime(time_zone="UTC"))

    out = build_row_rpf_context(context, keys, max_features_per_family=4).row(0, named=True)

    assert out["row_rpf_volatility_state_feature_count"] == 2
    assert out["row_rpf_volatility_state_mean_abs"] == pytest.approx(2.0)
    assert out["row_rpf_volatility_state_max_abs"] == pytest.approx(3.0)
    assert out["row_rpf_structural_room_mean_abs"] == pytest.approx(2.0)


def _write_router_config(run: Path) -> None:
    run.mkdir(parents=True, exist_ok=True)
    (run / "router_config.json").write_text('{"asset": "BTCUSDT", "root": "8h/B", "window_end_offset_steps": 0}\\n')


def _score_row(side: str, candidate: str, batch_id: int, timestamp: str, decision: int, target_binary: int) -> dict[str, object]:
    return {
        "side": side,
        "candidate_name": candidate,
        "diagnostic": True,
        "candidate_status": "ok",
        "candidate_passed_validation": True,
        "candidate_fail_reasons": "",
        "router_step_idx": batch_id,
        "router_pred_batch_id": batch_id,
        "split": "prediction",
        "target_col": f"rpf_rank_{side}_binary_positive",
        "step_idx": batch_id,
        "pred_batch_id": batch_id,
        "timestamp": timestamp,
        "batch_id": batch_id,
        "target_relevance": 0.8,
        "target_binary": target_binary,
        "rank_score": 0.2,
        "decision": decision,
        "threshold": 0.1,
        "max_signals_per_batch": 3,
        "decision_policy": "causal_threshold_budget",
    }
