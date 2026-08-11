"""Deterministic EMA200 gate evaluation for RPF binary classifier scores."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

from regression_feature_engineering.core.alignment import TIMEFRAME_MINUTES
from regression_feature_engineering.core.paths import canonical_ohlcv_path
from regression_feature_engineering.walkforward.classify import (
    TARGET_BINARY_DOWN_2X_UP,
    TARGET_BINARY_UP_2X_DOWN,
)
from regression_feature_engineering.walkforward.config import load_clean_config
from regression_feature_engineering.walkforward.reports import append_event, write_json, write_markdown, write_stage_status
from scripts.project_paths import ensure_project_root_on_path


PROJECT_ROOT = ensure_project_root_on_path(Path(__file__))
OUTPUT_ROOT = PROJECT_ROOT / "test_output" / "rpf_ema_gate"
DEFAULT_TIMEFRAMES = ("15m", "1h", "4h", "1d")


def main() -> int:
    args = _parse_args()
    config = load_clean_config(args.config)
    asset = str(args.asset or config.asset)
    timeframes = _parse_csv(args.timeframes)
    buffers = tuple(float(value) for value in _parse_csv(args.buffers))
    run_root = _run_root(args)
    run_root.mkdir(parents=True, exist_ok=True)
    events = run_root / "events.jsonl"
    append_event(events, "stage_start", stage="ema_gate", asset=asset, run=str(run_root))
    print(f"[rpf-ema-gate] start asset={asset} run={run_root}", flush=True)

    up_scores = load_classifier_scores(
        Path(args.up_score_path),
        target_col=TARGET_BINARY_UP_2X_DOWN,
        classifier_trial_number=args.up_classifier_trial_number,
    )
    down_scores = load_classifier_scores(
        Path(args.down_score_path),
        target_col=TARGET_BINARY_DOWN_2X_UP,
        classifier_trial_number=args.down_classifier_trial_number,
    )
    scores = pl.concat(
        [
            up_scores.with_columns(pl.lit("up").alias("side")),
            down_scores.with_columns(pl.lit("down").alias("side")),
        ],
        how="vertical",
    )
    if scores.is_empty():
        raise ValueError("No classifier score rows available")
    current_close = load_current_close(asset=asset, data_root=Path(args.data_root))
    joined_scores = scores.join(current_close, on="timestamp", how="inner")
    if joined_scores.is_empty():
        raise ValueError("Classifier scores did not join to canonical 1m current close")

    summary_rows: list[dict[str, Any]] = []
    row_level_paths: list[str] = []
    for timeframe in timeframes:
        ema = load_closed_ema200(asset=asset, timeframe=timeframe, data_root=Path(args.data_root))
        scored = attach_ema_gate(joined_scores, ema, timeframe=timeframe)
        row_path = run_root / f"ema_gate_scores_{timeframe}.parquet"
        scored.write_parquet(row_path)
        row_level_paths.append(str(row_path))
        for buffer in buffers:
            summary_rows.extend(evaluate_timeframe_buffer(scored, timeframe=timeframe, buffer=buffer))

    summary = pl.DataFrame(summary_rows, infer_schema_length=None)
    summary.write_parquet(run_root / "ema_gate_summary.parquet")
    write_json(
        run_root / "config.json",
        {
            "asset": asset,
            "timeframes": timeframes,
            "buffers": buffers,
            "up_score_path": str(args.up_score_path),
            "down_score_path": str(args.down_score_path),
            "up_classifier_trial_number": args.up_classifier_trial_number,
            "down_classifier_trial_number": args.down_classifier_trial_number,
            "row_level_paths": row_level_paths,
            "current_close_source": str(canonical_ohlcv_path(Path(args.data_root), asset, "1m")),
        },
    )
    write_markdown(
        run_root / "report.md",
        title="RPF EMA200 Gate Evaluation",
        sections={
            "Scope": {
                "asset": asset,
                "timeframes": ",".join(timeframes),
                "buffers": ",".join(str(value) for value in buffers),
                "up_score_path": str(args.up_score_path),
                "down_score_path": str(args.down_score_path),
            },
            "Contract": (
                "UP uses current 1m close above the last closed timeframe EMA200. "
                "DOWN uses current 1m close below the last closed timeframe EMA200. "
                "EMA bars are joined by closed-bar timestamp only."
            ),
            "Outputs": {
                "summary": str(run_root / "ema_gate_summary.parquet"),
                "row_scores": row_level_paths,
            },
        },
    )
    write_stage_status(
        run_root / "stage_status.json",
        stage="ema_gate",
        status="ok",
        asset=asset,
        run=str(run_root),
        summary_rows=summary.height,
        timeframes=timeframes,
        buffers=buffers,
    )
    append_event(events, "stage_done", stage="ema_gate", run=str(run_root), summary_rows=summary.height)
    print(f"[rpf-ema-gate] done run={run_root} rows={summary.height}", flush=True)
    return 0


def load_classifier_scores(
    path: Path,
    *,
    target_col: str,
    classifier_trial_number: int | None,
) -> pl.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Classifier score file not found: {path}")
    scores = pl.read_parquet(path)
    if "trial_number" in scores.columns:
        trial = classifier_trial_number
        if trial is None:
            trial = _best_classifier_trial_from_run(path.parent)
        if trial is None:
            raise ValueError(f"Score file has multiple trials and no best_config.json: {path}")
        scores = scores.filter(pl.col("trial_number") == int(trial))
    required = {"timestamp", "batch_id", "target", "prob", "predicted_positive"}
    missing = required - set(scores.columns)
    if missing:
        raise ValueError(f"Classifier score file missing columns {sorted(missing)}: {path}")
    return (
        scores.select(
            [
                "timestamp",
                "batch_id",
                "target",
                "prob",
                "predicted_positive",
                *(["threshold"] if "threshold" in scores.columns else []),
            ]
        )
        .with_columns(
            [
                pl.lit(target_col).alias("target_col"),
                pl.col("target").cast(pl.Int8),
                pl.col("prob").cast(pl.Float64),
                pl.col("predicted_positive").cast(pl.Int8),
            ]
        )
        .sort(["timestamp", "batch_id"])
    )


def load_current_close(*, asset: str, data_root: Path) -> pl.DataFrame:
    path = canonical_ohlcv_path(data_root, asset, "1m")
    return pl.read_parquet(path, columns=["timestamp", "close"]).rename({"close": "current_close"})


def load_closed_ema200(*, asset: str, timeframe: str, data_root: Path) -> pl.DataFrame:
    if timeframe not in TIMEFRAME_MINUTES:
        known = ", ".join(sorted(TIMEFRAME_MINUTES))
        raise ValueError(f"Unsupported timeframe {timeframe!r}; expected one of: {known}")
    path = canonical_ohlcv_path(data_root, asset, timeframe)
    if not path.exists():
        raise FileNotFoundError(f"Canonical OHLCV not found: {path}")
    minutes = TIMEFRAME_MINUTES[timeframe]
    return (
        pl.read_parquet(path, columns=["timestamp", "close"])
        .sort("timestamp")
        .with_row_index("_ema_row_idx")
        .with_columns(
            [
                (pl.col("timestamp") + timedelta(minutes=minutes)).alias("ema_bar_close_ts"),
                pl.col("close").ewm_mean(span=200, adjust=False).alias("_ema200_raw"),
            ]
        )
        .with_columns(
            pl.when(pl.col("_ema_row_idx") >= 199)
            .then(pl.col("_ema200_raw"))
            .otherwise(None)
            .alias("ema200")
        )
        .select(["ema_bar_close_ts", pl.col("close").alias("ema_source_close"), "ema200"])
        .drop_nulls(["ema200"])
        .sort("ema_bar_close_ts")
    )


def attach_ema_gate(scores: pl.DataFrame, ema: pl.DataFrame, *, timeframe: str) -> pl.DataFrame:
    left_order = "_ema_gate_row_order"
    joined = (
        scores.with_row_index(left_order)
        .sort("timestamp")
        .join_asof(ema, left_on="timestamp", right_on="ema_bar_close_ts", strategy="backward")
        .sort(left_order)
        .drop(left_order)
    )
    return joined.with_columns(
        [
            pl.lit(timeframe).alias("ema_timeframe"),
            ((pl.col("current_close") - pl.col("ema200")) / pl.col("ema200")).alias("ema_distance_pct"),
            (pl.col("current_close") > pl.col("ema200")).cast(pl.Int8).alias("price_above_ema200"),
            (pl.col("current_close") < pl.col("ema200")).cast(pl.Int8).alias("price_below_ema200"),
        ]
    )


def evaluate_timeframe_buffer(frame: pl.DataFrame, *, timeframe: str, buffer: float) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for side in ("up", "down"):
        side_frame = frame.filter(pl.col("side") == side)
        if side_frame.is_empty():
            continue
        if side == "up":
            gate_expr = pl.col("ema_distance_pct") > float(buffer)
        else:
            gate_expr = pl.col("ema_distance_pct") < -float(buffer)
        evaluated = side_frame.with_columns(
            [
                gate_expr.cast(pl.Int8).alias("ema_gate_active"),
                ((pl.col("predicted_positive") == 1) & gate_expr).cast(pl.Int8).alias("ema_gated_prediction"),
            ]
        )
        ungated = metrics_from_frame(evaluated, prediction_col="predicted_positive")
        gated = metrics_from_frame(evaluated, prediction_col="ema_gated_prediction")
        gate_active_rate = float(evaluated["ema_gate_active"].mean())
        rows.append(
            {
                "ema_timeframe": timeframe,
                "buffer": float(buffer),
                "side": side,
                "rows": int(evaluated.height),
                "gate_active_rate": gate_active_rate,
                "target_positive_rate_all": float(evaluated["target"].mean()),
                "target_positive_rate_gate_active": _target_rate(evaluated, gate_value=1),
                "target_positive_rate_gate_inactive": _target_rate(evaluated, gate_value=0),
                "ungated_tp": ungated["tp"],
                "ungated_fp": ungated["fp"],
                "ungated_tn": ungated["tn"],
                "ungated_fn": ungated["fn"],
                "ungated_precision": ungated["precision"],
                "ungated_recall": ungated["recall"],
                "ungated_false_positive_rate": ungated["false_positive_rate"],
                "ungated_predicted_positive_rate": ungated["predicted_positive_rate"],
                "gated_tp": gated["tp"],
                "gated_fp": gated["fp"],
                "gated_tn": gated["tn"],
                "gated_fn": gated["fn"],
                "gated_precision": gated["precision"],
                "gated_recall": gated["recall"],
                "gated_false_positive_rate": gated["false_positive_rate"],
                "gated_predicted_positive_rate": gated["predicted_positive_rate"],
                "false_positive_reduction": _relative_reduction(ungated["fp"], gated["fp"]),
                "recall_retained": _safe_ratio(gated["recall"], ungated["recall"]),
                "precision_improvement": _safe_difference(gated["precision"], ungated["precision"]),
            }
        )
    return rows


def metrics_from_frame(frame: pl.DataFrame, *, prediction_col: str) -> dict[str, Any]:
    y = frame["target"].to_numpy().astype(int)
    pred = frame[prediction_col].to_numpy().astype(int)
    positives = y == 1
    negatives = y == 0
    tp = int(np.sum((pred == 1) & positives))
    tn = int(np.sum((pred == 0) & negatives))
    fp = int(np.sum((pred == 1) & negatives))
    fn = int(np.sum((pred == 0) & positives))
    return {
        "tp": tp,
        "tn": tn,
        "fp": fp,
        "fn": fn,
        "precision": _safe_ratio(tp, tp + fp),
        "recall": _safe_ratio(tp, tp + fn),
        "false_positive_rate": _safe_ratio(fp, fp + tn),
        "predicted_positive_rate": float(np.mean(pred)) if len(pred) else None,
    }


def _target_rate(frame: pl.DataFrame, *, gate_value: int) -> float | None:
    subset = frame.filter(pl.col("ema_gate_active") == int(gate_value))
    if subset.is_empty():
        return None
    return float(subset["target"].mean())


def _safe_ratio(numerator: float | int | None, denominator: float | int | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return float(numerator) / float(denominator)


def _relative_reduction(before: int, after: int) -> float | None:
    if before == 0:
        return None
    return float((before - after) / before)


def _safe_difference(after: float | None, before: float | None) -> float | None:
    if after is None or before is None:
        return None
    return float(after - before)


def _parse_csv(raw: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in str(raw).split(",") if part.strip())


def _best_classifier_trial_from_run(run_root: Path) -> int | None:
    best_path = Path(run_root) / "best_config.json"
    if not best_path.exists():
        return None
    payload = json.loads(best_path.read_text())
    best = payload.get("best") or {}
    value = best.get("trial_number")
    return None if value is None else int(value)


def _run_root(args: argparse.Namespace) -> Path:
    now = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return Path(args.output_dir) / f"{now}_ema200_gate"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate deterministic EMA200 gates for RPF binary classifier scores.")
    parser.add_argument("--asset", default=None)
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--data-root", type=Path, default=PROJECT_ROOT / "data")
    parser.add_argument("--up-score-path", type=Path, required=True)
    parser.add_argument("--down-score-path", type=Path, required=True)
    parser.add_argument("--up-classifier-trial-number", type=int, default=None)
    parser.add_argument("--down-classifier-trial-number", type=int, default=None)
    parser.add_argument("--timeframes", default=",".join(DEFAULT_TIMEFRAMES))
    parser.add_argument("--buffers", default="0,0.001,0.0025,0.005")
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_ROOT)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
