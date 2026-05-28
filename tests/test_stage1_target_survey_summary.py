from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import polars as pl

from scripts.analysis.summarize_stage1_target_survey import (
    RunSpec,
    compute_metrics,
    load_selected_predictions,
)


def _write_step(
    project_root: Path,
    *,
    run_id: str,
    target_col: str,
    pred_batch: int,
    winner_key: str | None,
    predictions: pl.DataFrame,
) -> None:
    stage1_dir = (
        project_root
        / "data"
        / "htf_backtest_results"
        / run_id
        / "catboost"
        / "1m"
        / target_col
        / f"batch_{pred_batch}"
        / "stage1"
    )
    stage1_dir.mkdir(parents=True)
    (stage1_dir / "stage1_step_summary.json").write_text(
        json.dumps(
            {
                "pred_batch": pred_batch,
                "winner_combo_key": winner_key,
                "fail_reasons": {"missing_batch:1:train": 1} if winner_key is None else {},
            }
        )
    )
    predictions.write_parquet(stage1_dir / "stage1_pred_batch_predictions.parquet")


def _predictions(pred_batch: int) -> pl.DataFrame:
    start = datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=pred_batch)
    return pl.DataFrame(
        {
            "scope": ["pred_batch"] * 4,
            "action_key": ["winner", "winner", "other", "other"],
            "timestamp": [start, start + timedelta(minutes=1)] * 2,
            "batch_id": [pred_batch] * 4,
            "y_true": [0, 3, 0, 3],
            "y_pred": [0, 3, 3, 0],
            "prob_class_0": [0.8, 0.05, 0.05, 0.8],
            "prob_class_1": [0.05, 0.05, 0.05, 0.05],
            "prob_class_2": [0.05, 0.05, 0.05, 0.05],
            "prob_class_3": [0.1, 0.85, 0.85, 0.1],
        }
    )


def test_survey_summary_uses_selected_action_and_tracks_no_winner(tmp_path: Path) -> None:
    run_id = "target_run"
    target_col = "target_4class_tb_atr_wide_v2"
    _write_step(
        tmp_path,
        run_id=run_id,
        target_col=target_col,
        pred_batch=10,
        winner_key="winner",
        predictions=_predictions(10),
    )
    _write_step(
        tmp_path,
        run_id=run_id,
        target_col=target_col,
        pred_batch=11,
        winner_key=None,
        predictions=_predictions(11).head(0),
    )

    loaded = load_selected_predictions(tmp_path, RunSpec("candidate", run_id, target_col))
    metrics = compute_metrics(loaded.frame)

    assert loaded.attempted_steps == 2
    assert loaded.scorable_steps == 1
    assert loaded.no_winner_steps == (11,)
    assert loaded.fail_reasons == {"missing_batch:1:train": 1}
    assert loaded.frame["action_key"].unique().to_list() == ["winner"]
    assert metrics["accuracy"] == 1.0
    assert metrics["direction_accuracy"] == 1.0
    assert metrics["cross_direction_error"] == 0.0
